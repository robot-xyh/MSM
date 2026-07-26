"""Run a deterministic 20-seed D3 checkpoint-selection replay batch.

The batch consumes only explicit, anonymous ``PlanningFrameEvidence`` files
and a frozen development bundle.  It never discovers neighboring files,
publishes a plan, creates a runtime acknowledgement, evaluates a physical
outcome, or grants assignment/control authority.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import csv
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import shutil
import tempfile
import types
from typing import Any, get_args, get_origin, get_type_hints

import numpy as np

from .learning_bundle import (
    MODEL_BUNDLE_MANIFEST_FILENAME,
    ModelBundleManifest,
)
from .models import CostWeights, PlannerConfig
from .offline_intervention_execution import (
    IsolatedLearningInterventionFrameReplay,
    canonical_planning_frame_snapshot_sha256,
    replay_isolated_learning_intervention_frame,
)
from .paired_intervention import PairedInterventionContractError
from .planning_evidence import PlanningFrameEvidence
from .runtime_plan_ack import canonical_runtime_payload_sha256


ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1 = (
    "d3.isolated-learning-intervention-batch-manifest.v1"
)
ANONYMOUS_PLANNING_FRAME_FILE_SCHEMA_V1 = (
    "d3.anonymous-planning-frame-file.v1"
)
ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1 = (
    "d3.isolated-learning-intervention-batch-result.v1"
)
ISOLATED_INTERVENTION_BATCH_FRAME_SUMMARY_SCHEMA_V1 = (
    "d3.isolated-learning-intervention-batch-frame-summary.v1"
)
ISOLATED_INTERVENTION_BATCH_SCOPE = (
    "reserved-seed-first-eligible-selection-no-publication-no-authority"
)
ISOLATED_INTERVENTION_BATCH_SEEDS_V1 = tuple(range(1000, 1020))

BATCH_RESULT_FILENAME = "isolated_intervention_batch.json"
BATCH_PER_SEED_FILENAME = "isolated_intervention_per_seed.csv"
BATCH_REPORT_FILENAME = "D3_ISOLATED_INTERVENTION_BATCH_REPORT_CN.md"
BATCH_CHECKSUMS_FILENAME = "SHA256SUMS"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_BATCH_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
)
_FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
        "physical_outcome",
        "intercept_success",
        "reward",
    }
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "batch_id",
        "evaluated_at",
        "split",
        "source",
        "bundle",
        "planner_config",
        "cost_weights",
        "seeds",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "repository_git_commit",
        "worktree_state",
    }
)
_BUNDLE_FIELDS = frozenset(
    {
        "directory",
        "manifest_sha256",
        "policy_version",
    }
)
_SEED_FIELDS = frozenset({"seed", "frames"})
_FRAME_REFERENCE_FIELDS = frozenset(
    {
        "sequence_index",
        "timestamp_s",
        "path",
        "file_sha256",
        "content_sha256",
    }
)
_FRAME_FILE_FIELDS = frozenset(
    {
        "schema_version",
        "input_snapshot_sha256",
        "content_sha256",
        "planning_frame",
    }
)


@dataclass(frozen=True, slots=True)
class IsolatedInterventionFrameReference:
    """One explicitly listed anonymous planning-frame file."""

    sequence_index: int
    timestamp_s: float
    path: str
    file_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class IsolatedInterventionSeedManifest:
    """Strictly ordered planning-frame inventory for one reserved seed."""

    seed: int
    frames: tuple[IsolatedInterventionFrameReference, ...]


@dataclass(frozen=True, slots=True)
class IsolatedInterventionBatchManifest:
    """Validated outer manifest for the fixed 1000-1019 holdout."""

    batch_id: str
    evaluated_at: str
    repository_git_commit: str
    worktree_state: str
    bundle_directory: str
    bundle_manifest_sha256: str
    policy_version: str
    planner_config: PlannerConfig
    cost_weights: CostWeights
    seeds: tuple[IsolatedInterventionSeedManifest, ...]
    split: str = "test"
    schema_version: str = ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1


def write_anonymous_planning_frame_evidence(
    path: str | Path,
    evidence: PlanningFrameEvidence,
) -> Mapping[str, str]:
    """Write one anonymous frame file without a seed or caller decision."""

    if not isinstance(evidence, PlanningFrameEvidence):
        _fail("batch_frame_type_invalid")
    input_snapshot_sha256 = canonical_planning_frame_snapshot_sha256(evidence)
    frame_payload = _jsonable(evidence)
    _assert_truth_free(frame_payload)
    _assert_all_finite(frame_payload)
    content_sha256 = canonical_runtime_payload_sha256(frame_payload)
    payload = {
        "schema_version": ANONYMOUS_PLANNING_FRAME_FILE_SCHEMA_V1,
        "input_snapshot_sha256": input_snapshot_sha256,
        "content_sha256": content_sha256,
        "planning_frame": frame_payload,
    }
    output = Path(path)
    if output.exists():
        _fail("batch_frame_output_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if temporary.exists():
        _fail("batch_frame_temporary_output_exists")
    try:
        _write_json(temporary, payload)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "file_sha256": _file_sha256(output),
        "content_sha256": content_sha256,
        "input_snapshot_sha256": input_snapshot_sha256,
    }


def load_isolated_intervention_batch_manifest(
    path: str | Path,
) -> IsolatedInterventionBatchManifest:
    """Load an exact clean 20-seed manifest without filesystem discovery."""

    source = Path(path)
    payload = _load_json_file(source, "batch_manifest_load_failed")
    _assert_truth_free(payload)
    _assert_all_finite(payload)
    item = _strict_mapping(
        payload,
        _TOP_LEVEL_FIELDS,
        "batch_manifest_fields_mismatch",
    )
    if item["schema_version"] != ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1:
        _fail("batch_manifest_schema_unsupported")
    batch_id = _required_text(item["batch_id"], "batch_id")
    if _BATCH_ID_PATTERN.fullmatch(batch_id) is None:
        _fail("batch_id_invalid")
    evaluated_at = _validated_utc_timestamp(item["evaluated_at"])
    if item["split"] != "test":
        _fail("batch_split_not_test")

    source_item = _strict_mapping(
        item["source"],
        _SOURCE_FIELDS,
        "batch_source_fields_mismatch",
    )
    repository_git_commit = _required_text(
        source_item["repository_git_commit"],
        "repository_git_commit",
    )
    if _COMMIT_PATTERN.fullmatch(repository_git_commit) is None:
        _fail("batch_source_commit_invalid")
    worktree_state = _required_text(
        source_item["worktree_state"],
        "worktree_state",
    )
    if worktree_state != "clean":
        _fail("batch_source_worktree_not_clean")

    bundle_item = _strict_mapping(
        item["bundle"],
        _BUNDLE_FIELDS,
        "batch_bundle_fields_mismatch",
    )
    bundle_directory = _required_text(
        bundle_item["directory"],
        "bundle_directory",
    )
    bundle_manifest_sha256 = _sha256_text(
        bundle_item["manifest_sha256"],
        "bundle_manifest_sha256",
    )
    policy_version = _required_text(
        bundle_item["policy_version"],
        "policy_version",
    )

    planner_config = _decode_dataclass(
        PlannerConfig,
        item["planner_config"],
        "$.planner_config",
    )
    cost_weights = _decode_dataclass(
        CostWeights,
        item["cost_weights"],
        "$.cost_weights",
    )
    seed_values = _strict_sequence(item["seeds"], "batch_seeds")
    if len(seed_values) != len(ISOLATED_INTERVENTION_BATCH_SEEDS_V1):
        _fail("batch_seed_inventory_incomplete")
    seeds: list[IsolatedInterventionSeedManifest] = []
    seen_paths: set[str] = set()
    for expected_seed, raw_seed in zip(
        ISOLATED_INTERVENTION_BATCH_SEEDS_V1,
        seed_values,
        strict=True,
    ):
        seed_item = _strict_mapping(
            raw_seed,
            _SEED_FIELDS,
            "batch_seed_fields_mismatch",
        )
        seed = _nonnegative_int(seed_item["seed"], "seed")
        if seed != expected_seed:
            _fail("batch_seed_inventory_invalid")
        raw_frames = _strict_sequence(seed_item["frames"], "batch_seed_frames")
        if not raw_frames:
            _fail("batch_seed_frame_inventory_empty")
        frames: list[IsolatedInterventionFrameReference] = []
        previous_sequence = -1
        previous_timestamp = -1.0
        for raw_frame in raw_frames:
            frame_item = _strict_mapping(
                raw_frame,
                _FRAME_REFERENCE_FIELDS,
                "batch_frame_reference_fields_mismatch",
            )
            sequence_index = _nonnegative_int(
                frame_item["sequence_index"],
                "sequence_index",
            )
            timestamp_s = _finite_nonnegative(
                frame_item["timestamp_s"],
                "timestamp_s",
            )
            if (
                sequence_index <= previous_sequence
                or timestamp_s <= previous_timestamp
            ):
                _fail("batch_frame_order_invalid")
            previous_sequence = sequence_index
            previous_timestamp = timestamp_s
            frame_path = _required_text(frame_item["path"], "frame_path")
            if frame_path in seen_paths:
                _fail("batch_frame_path_reused")
            seen_paths.add(frame_path)
            frames.append(
                IsolatedInterventionFrameReference(
                    sequence_index=sequence_index,
                    timestamp_s=timestamp_s,
                    path=frame_path,
                    file_sha256=_sha256_text(
                        frame_item["file_sha256"],
                        "frame_file_sha256",
                    ),
                    content_sha256=_sha256_text(
                        frame_item["content_sha256"],
                        "frame_content_sha256",
                    ),
                )
            )
        seeds.append(
            IsolatedInterventionSeedManifest(
                seed=seed,
                frames=tuple(frames),
            )
        )
    return IsolatedInterventionBatchManifest(
        batch_id=batch_id,
        evaluated_at=evaluated_at,
        repository_git_commit=repository_git_commit,
        worktree_state=worktree_state,
        bundle_directory=bundle_directory,
        bundle_manifest_sha256=bundle_manifest_sha256,
        policy_version=policy_version,
        planner_config=planner_config,
        cost_weights=cost_weights,
        seeds=tuple(seeds),
    )


def run_isolated_intervention_batch(
    manifest_path: str | Path,
    output_dir: str | Path,
) -> Mapping[str, Any]:
    """Replay every explicit frame and atomically publish four audit files."""

    source_path = Path(manifest_path).resolve()
    output = Path(output_dir)
    _assert_output_target_empty(output)
    manifest_file_sha256 = _file_sha256(source_path)
    manifest = load_isolated_intervention_batch_manifest(source_path)
    base_directory = source_path.parent
    bundle_directory = _resolve_explicit_path(
        base_directory,
        manifest.bundle_directory,
        expect_directory=True,
    )
    bundle_manifest_path = bundle_directory / MODEL_BUNDLE_MANIFEST_FILENAME
    if not bundle_manifest_path.is_file():
        _fail("batch_bundle_manifest_missing")
    if _file_sha256(bundle_manifest_path) != manifest.bundle_manifest_sha256:
        _fail("batch_bundle_manifest_sha256_mismatch")
    bundle_manifest_payload = _load_json_file(
        bundle_manifest_path,
        "batch_bundle_manifest_load_failed",
    )
    try:
        bundle_manifest = ModelBundleManifest.from_dict(bundle_manifest_payload)
    except (TypeError, ValueError) as exc:
        _fail("batch_bundle_manifest_invalid", str(exc))
    if bundle_manifest.policy_version != manifest.policy_version:
        _fail("batch_bundle_policy_version_mismatch")
    bundle_admission = bundle_manifest.admission
    try:
        holdout_seeds = tuple(
            int(value)
            for value in bundle_admission.get(
                "external_holdout_seed_values",
                (),
            )
        )
    except (TypeError, ValueError) as exc:
        _fail("batch_bundle_reserved_seed_contract_invalid", str(exc))
    if (
        bundle_manifest.bundle_schema_version
        != "d3_learning_model_bundle_v3"
        or bundle_admission.get("stage") != "development"
        or tuple(bundle_admission.get("allowed_modes", ())) != ("shadow",)
        or bundle_admission.get("assist_authorized") is not False
        or bundle_admission.get("rule_fallback_required") is not True
        or set(ISOLATED_INTERVENTION_BATCH_SEEDS_V1)
        - set(holdout_seeds)
    ):
        _fail("batch_bundle_reserved_seed_contract_invalid")
    state_dict_path = bundle_directory / bundle_manifest.state_dict_file
    if not state_dict_path.is_file():
        _fail("batch_bundle_state_dict_missing")
    if _file_sha256(state_dict_path) != bundle_manifest.state_dict_sha256:
        _fail("batch_bundle_state_dict_sha256_mismatch")

    tracked_inputs: dict[Path, str] = {
        source_path: manifest_file_sha256,
        bundle_manifest_path.resolve(): manifest.bundle_manifest_sha256,
        state_dict_path.resolve(): bundle_manifest.state_dict_sha256,
    }
    seed_results: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    for seed_manifest in manifest.seeds:
        frame_results: list[dict[str, Any]] = []
        eligibility_records = []
        for reference in seed_manifest.frames:
            frame_path = _resolve_explicit_path(
                base_directory,
                reference.path,
                expect_directory=False,
            )
            if frame_path in tracked_inputs:
                _fail("batch_input_path_reused")
            actual_file_sha256 = _file_sha256(frame_path)
            if actual_file_sha256 != reference.file_sha256:
                _fail("batch_frame_file_sha256_mismatch")
            tracked_inputs[frame_path] = actual_file_sha256
            rule_frame = _load_anonymous_planning_frame_file(
                frame_path,
                expected_content_sha256=reference.content_sha256,
            )
            if float(rule_frame.timestamp_s) != reference.timestamp_s:
                _fail("batch_frame_timestamp_mismatch")
            replay = replay_isolated_learning_intervention_frame(
                rule_frame,
                sequence_index=reference.sequence_index,
                bundle_dir=bundle_directory,
                expected_manifest_sha256=manifest.bundle_manifest_sha256,
                expected_policy_version=manifest.policy_version,
                planner_config=manifest.planner_config,
                cost_weights=manifest.cost_weights,
            )
            frame_summary = _stable_frame_summary(
                reference=reference,
                replay=replay,
            )
            frame_results.append(frame_summary)
            eligibility_records.append(replay.eligibility)

        from .learning_intervention_eligibility import (
            select_first_eligible_learning_intervention_frame,
        )

        selected = select_first_eligible_learning_intervention_frame(
            eligibility_records
        )
        selected_frame = (
            None
            if selected is None
            else next(
                item
                for item in frame_results
                if item["sequence_index"] == selected.sequence_index
            )
        )
        status = (
            "eligible_selected"
            if selected_frame is not None
            else "unavailable"
        )
        unavailable_reason = (
            None if selected_frame is not None else "no_eligible_frame"
        )
        seed_payload = {
            "seed": seed_manifest.seed,
            "status": status,
            "unavailable_reason": unavailable_reason,
            "frame_count": len(frame_results),
            "eligible_frame_count": sum(
                item["eligible"] for item in frame_results
            ),
            "first_eligible": (
                None
                if selected_frame is None
                else {
                    "sequence_index": selected_frame["sequence_index"],
                    "timestamp_s": selected_frame["timestamp_s"],
                    "replay_sha256": selected_frame["replay_sha256"],
                    "evidence_sha256": selected_frame["evidence_sha256"],
                }
            ),
            "bundle": {
                "all_frames_loaded": all(
                    item["bundle_loaded"] for item in frame_results
                ),
                "applied_frame_count": sum(
                    item["learning_cost_applied"] for item in frame_results
                ),
                "fallback_frame_count": sum(
                    item["rule_fallback_applied"] for item in frame_results
                ),
                "fallback_reasons": sorted(
                    {
                        str(item["fallback_reason"])
                        for item in frame_results
                        if item["fallback_reason"] is not None
                    }
                ),
            },
            "binding_difference_count": sum(
                int(item["binding_change_count"]) for item in frame_results
            ),
            "safety": {
                "rule_hard_violation_count": sum(
                    int(item["rule_hard_violation_count"])
                    for item in frame_results
                ),
                "treatment_hard_violation_count": sum(
                    int(item["treatment_hard_violation_count"])
                    for item in frame_results
                ),
                "global_track_id_rewrite_count": 0,
            },
            "execution_boundary": _execution_boundary(),
            "frames": frame_results,
        }
        seed_results.append(seed_payload)
        csv_rows.append(_seed_csv_row(seed_payload))

    _verify_inputs_unchanged(tracked_inputs)
    result: dict[str, Any] = {
        "schema_version": ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1,
        "batch_scope": ISOLATED_INTERVENTION_BATCH_SCOPE,
        "batch_id": manifest.batch_id,
        "evaluated_at": manifest.evaluated_at,
        "input_manifest_sha256": manifest_file_sha256,
        "split": manifest.split,
        "source": {
            "repository_git_commit": manifest.repository_git_commit,
            "worktree_state": manifest.worktree_state,
        },
        "bundle": {
            "manifest_sha256": manifest.bundle_manifest_sha256,
            "policy_version": manifest.policy_version,
            "state_dict_sha256": bundle_manifest.state_dict_sha256,
        },
        "configuration": {
            "planner_config_sha256": canonical_runtime_payload_sha256(
                asdict(manifest.planner_config)
            ),
            "cost_weights_sha256": canonical_runtime_payload_sha256(
                asdict(manifest.cost_weights)
            ),
        },
        "seed_contract": {
            "expected_seeds": list(ISOLATED_INTERVENTION_BATCH_SEEDS_V1),
            "seed_count": len(seed_results),
            "eligible_seed_count": sum(
                item["status"] == "eligible_selected" for item in seed_results
            ),
            "unavailable_seed_count": sum(
                item["status"] == "unavailable" for item in seed_results
            ),
        },
        "execution_boundary": _execution_boundary(),
        "seeds": seed_results,
    }
    _assert_truth_free(result)
    _assert_all_finite(result)
    result["content_sha256"] = canonical_runtime_payload_sha256(result)
    _write_batch_outputs_atomically(output, result, csv_rows)
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit batch runner command line."""

    parser = argparse.ArgumentParser(
        description=(
            "Replay a frozen D3 1000-1019 anonymous planning-frame manifest"
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; contract failures return a nonzero status."""

    args = build_parser().parse_args(argv)
    try:
        result = run_isolated_intervention_batch(args.manifest, args.output)
    except PairedInterventionContractError as exc:
        raise SystemExit(f"{exc.code}: {exc}") from exc
    print(
        json.dumps(
            {
                "batch_id": result["batch_id"],
                "content_sha256": result["content_sha256"],
                "eligible_seed_count": result["seed_contract"][
                    "eligible_seed_count"
                ],
                "output": str(args.output),
                "publish": False,
                "production_authority": False,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


def _load_anonymous_planning_frame_file(
    path: Path,
    *,
    expected_content_sha256: str,
) -> PlanningFrameEvidence:
    payload = _load_json_file(path, "batch_frame_load_failed")
    _assert_truth_free(payload)
    _assert_all_finite(payload)
    item = _strict_mapping(
        payload,
        _FRAME_FILE_FIELDS,
        "batch_frame_file_fields_mismatch",
    )
    if item["schema_version"] != ANONYMOUS_PLANNING_FRAME_FILE_SCHEMA_V1:
        _fail("batch_frame_file_schema_unsupported")
    content_sha256 = _sha256_text(
        item["content_sha256"],
        "frame_content_sha256",
    )
    if content_sha256 != expected_content_sha256:
        _fail("batch_frame_content_sha256_mismatch")
    planning_frame_payload = item["planning_frame"]
    if canonical_runtime_payload_sha256(planning_frame_payload) != content_sha256:
        _fail("batch_frame_content_sha256_mismatch")
    frame = _decode_dataclass(
        PlanningFrameEvidence,
        planning_frame_payload,
        "$.planning_frame",
    )
    if canonical_runtime_payload_sha256(_jsonable(frame)) != content_sha256:
        _fail("batch_frame_roundtrip_mismatch")
    input_snapshot_sha256 = _sha256_text(
        item["input_snapshot_sha256"],
        "input_snapshot_sha256",
    )
    if canonical_planning_frame_snapshot_sha256(frame) != input_snapshot_sha256:
        _fail("batch_frame_input_snapshot_sha256_mismatch")
    return frame


def _stable_frame_summary(
    *,
    reference: IsolatedInterventionFrameReference,
    replay: IsolatedLearningInterventionFrameReplay,
) -> dict[str, Any]:
    evidence = replay.eligibility
    evidence_payload = {
        "sequence_index": evidence.sequence_index,
        "timestamp_s": evidence.timestamp_s,
        "planning_path": evidence.planning_path,
        "eligible": evidence.eligible,
        "reason_codes": list(evidence.reason_codes),
        "input_snapshot_sha256": evidence.input_snapshot_sha256,
        "previous_plan_payload_sha256": (
            evidence.previous_plan_payload_sha256
        ),
        "rule_matrix_sha256": evidence.rule_matrix_sha256,
        "treatment_matrix_sha256": evidence.treatment_matrix_sha256,
        "action_mask_sha256": evidence.action_mask_sha256,
        "rule_binding_sha256": evidence.rule_binding_sha256,
        "treatment_binding_sha256": evidence.treatment_binding_sha256,
        "model_applied_edge_count": evidence.model_applied_edge_count,
        "binding_change_count": evidence.binding_change_count,
        "rule_assignment_count": evidence.rule_assignment_count,
        "treatment_assignment_count": evidence.treatment_assignment_count,
        "demand_slot_count": evidence.demand_slot_count,
        "m_to_n_target_count": evidence.m_to_n_target_count,
        "rule_hard_violation_count": evidence.rule_hard_violation_count,
        "treatment_hard_violation_count": (
            evidence.treatment_hard_violation_count
        ),
        "fallback_reason": evidence.fallback_reason,
    }
    evidence_sha256 = canonical_runtime_payload_sha256(evidence_payload)
    effective_result = replay.treatment_frame.effective_matrix_result
    effective_metadata = (
        {} if effective_result is None else effective_result.metadata
    )
    learning_applied = effective_metadata.get("learning_applied") is True
    rule_fallback = replay.treatment_frame.learning_state == "rule_fallback"
    fallback_reason = (
        replay.bundle_fallback_reason
        if replay.bundle_fallback_reason is not None
        else evidence.fallback_reason
    )
    replay_payload = {
        "input_file_sha256": reference.file_sha256,
        "input_content_sha256": reference.content_sha256,
        "input_snapshot_sha256": replay.input_snapshot_sha256,
        "expected_bundle_manifest_sha256": (
            replay.expected_bundle_manifest_sha256
        ),
        "actual_bundle_manifest_sha256": (
            replay.actual_bundle_manifest_sha256
        ),
        "expected_policy_version": replay.expected_policy_version,
        "actual_policy_version": replay.actual_policy_version,
        "bundle_state_dict_sha256": replay.bundle_state_dict_sha256,
        "bundle_loaded": replay.bundle_loaded,
        "bundle_fallback_reason": replay.bundle_fallback_reason,
        "evidence_sha256": evidence_sha256,
        "execution_boundary": _execution_boundary(),
    }
    return {
        "schema_version": (
            ISOLATED_INTERVENTION_BATCH_FRAME_SUMMARY_SCHEMA_V1
        ),
        "sequence_index": reference.sequence_index,
        "timestamp_s": reference.timestamp_s,
        "input_path": reference.path,
        "input_file_sha256": reference.file_sha256,
        "input_content_sha256": reference.content_sha256,
        "replay_sha256": canonical_runtime_payload_sha256(replay_payload),
        "evidence_sha256": evidence_sha256,
        "eligible": evidence.eligible,
        "reason_codes": list(evidence.reason_codes),
        "bundle_loaded": replay.bundle_loaded,
        "learning_cost_applied": learning_applied,
        "rule_fallback_applied": rule_fallback,
        "fallback_reason": fallback_reason,
        "binding_change_count": evidence.binding_change_count,
        "rule_hard_violation_count": evidence.rule_hard_violation_count,
        "treatment_hard_violation_count": (
            evidence.treatment_hard_violation_count
        ),
        "execution_boundary": _execution_boundary(),
    }


def _execution_boundary() -> dict[str, bool | int]:
    return {
        "isolated_simulation_only": True,
        "publish": False,
        "runtime_ack": False,
        "production_assignment_authority": False,
        "production_control_authority": False,
        "physical_outcome_available": False,
        "reward_available": False,
        "global_track_id_rewrite_count": 0,
    }


def _seed_csv_row(seed: Mapping[str, Any]) -> dict[str, Any]:
    first = seed["first_eligible"]
    bundle = seed["bundle"]
    safety = seed["safety"]
    return {
        "seed": seed["seed"],
        "status": seed["status"],
        "unavailable_reason": seed["unavailable_reason"] or "",
        "frame_count": seed["frame_count"],
        "eligible_frame_count": seed["eligible_frame_count"],
        "first_eligible_sequence_index": (
            "" if first is None else first["sequence_index"]
        ),
        "first_eligible_timestamp_s": (
            "" if first is None else first["timestamp_s"]
        ),
        "first_eligible_replay_sha256": (
            "" if first is None else first["replay_sha256"]
        ),
        "first_eligible_evidence_sha256": (
            "" if first is None else first["evidence_sha256"]
        ),
        "all_frames_bundle_loaded": bundle["all_frames_loaded"],
        "learning_applied_frame_count": bundle["applied_frame_count"],
        "rule_fallback_frame_count": bundle["fallback_frame_count"],
        "fallback_reasons": "|".join(bundle["fallback_reasons"]),
        "binding_difference_count": seed["binding_difference_count"],
        "rule_hard_violation_count": safety["rule_hard_violation_count"],
        "treatment_hard_violation_count": safety[
            "treatment_hard_violation_count"
        ],
        "global_track_id_rewrite_count": 0,
        "publish": False,
        "runtime_ack": False,
        "production_assignment_authority": False,
        "production_control_authority": False,
    }


def _write_batch_outputs_atomically(
    output: Path,
    result: Mapping[str, Any],
    csv_rows: Sequence[Mapping[str, Any]],
) -> None:
    output_parent = output.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.staging-",
            dir=output_parent,
        )
    )
    try:
        _write_json(staging / BATCH_RESULT_FILENAME, result)
        _write_csv(staging / BATCH_PER_SEED_FILENAME, csv_rows)
        (staging / BATCH_REPORT_FILENAME).write_text(
            _render_chinese_report(result),
            encoding="utf-8",
            newline="\n",
        )
        checksum_names = (
            BATCH_RESULT_FILENAME,
            BATCH_PER_SEED_FILENAME,
            BATCH_REPORT_FILENAME,
        )
        checksum_text = "".join(
            f"{_file_sha256(staging / name)}  {name}\n"
            for name in checksum_names
        )
        (staging / BATCH_CHECKSUMS_FILENAME).write_text(
            checksum_text,
            encoding="ascii",
            newline="\n",
        )
        _assert_output_target_empty(output)
        if output.exists():
            output.rmdir()
        os.replace(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _render_chinese_report(result: Mapping[str, Any]) -> str:
    contract = result["seed_contract"]
    rows = [
        "| seed | 状态 | 帧数 | 合格帧 | 首个序号 | 绑定变化 | 回退帧 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for seed in result["seeds"]:
        first = seed["first_eligible"]
        status_text = (
            "已选择"
            if seed["status"] == "eligible_selected"
            else "不可用"
        )
        rows.append(
            "| {seed} | {status} | {frames} | {eligible} | {first} | "
            "{binding} | {fallback} |".format(
                seed=seed["seed"],
                status=status_text,
                frames=seed["frame_count"],
                eligible=seed["eligible_frame_count"],
                first="-" if first is None else first["sequence_index"],
                binding=seed["binding_difference_count"],
                fallback=seed["bundle"]["fallback_frame_count"],
            )
        )
    return (
        "# D3 隔离干预批量重放报告\n\n"
        "## 结论\n\n"
        f"本次按固定清单重放 {contract['seed_count']} 个 seed。"
        f"首个合格帧可用 {contract['eligible_seed_count']} 个，"
        f"不可用 {contract['unavailable_seed_count']} 个。"
        "不可用 seed 保留明确原因，没有补选绑定未变化的帧。\n\n"
        "该结果只用于后续物理运行前的检查点选择。计划发布、运行确认、"
        "生产分配权限、控制权限、物理结果和奖励均不可用。\n\n"
        "## 输入\n\n"
        f"- 批次：`{result['batch_id']}`\n"
        f"- 评估时间：`{result['evaluated_at']}`\n"
        f"- 源提交：`{result['source']['repository_git_commit']}`\n"
        f"- 工作树：`{result['source']['worktree_state']}`\n"
        f"- 模型清单：`{result['bundle']['manifest_sha256']}`\n"
        f"- 策略版本：`{result['bundle']['policy_version']}`\n"
        f"- 输入清单摘要：`{result['input_manifest_sha256']}`\n\n"
        "## 逐 seed 结果\n\n"
        + "\n".join(rows)
        + "\n\n## 边界\n\n"
        "- 所有规则组和处理组均在隔离 planner 中以 `publish=false` 运行。\n"
        "- 输出不包含运行 ACK、生产 authority、物理 outcome 或 reward。\n"
        "- 在线真值、Actor 标识和调用方 eligibility 布尔值不允许进入输入。\n"
        "- `global_track_id` 改写计数固定为 0。\n"
    )


def _resolve_explicit_path(
    base: Path,
    raw_path: str,
    *,
    expect_directory: bool,
) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        _fail("batch_explicit_input_missing", str(exc))
    if expect_directory:
        if not resolved.is_dir():
            _fail("batch_explicit_directory_invalid")
    elif not resolved.is_file():
        _fail("batch_explicit_file_invalid")
    return resolved


def _assert_output_target_empty(output: Path) -> None:
    if not output.exists():
        return
    if not output.is_dir():
        _fail("batch_output_not_directory")
    try:
        next(output.iterdir())
    except StopIteration:
        return
    _fail("batch_output_not_empty")


def _verify_inputs_unchanged(expected: Mapping[Path, str]) -> None:
    for path, digest in expected.items():
        if not path.is_file() or _file_sha256(path) != digest:
            _fail("batch_input_changed_during_replay")


def _load_json_file(path: Path, code: str) -> Any:
    def reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                _fail("batch_json_duplicate_key", key)
            output[key] = value
        return output

    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream, object_pairs_hook=reject_duplicate_keys)
    except (OSError, json.JSONDecodeError) as exc:
        _fail(code, str(exc))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            _jsonable(value),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="ascii",
        newline="\n",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        _fail("batch_csv_rows_empty")
    fieldnames = tuple(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            if tuple(row) != fieldnames:
                _fail("batch_csv_schema_mismatch")
            writer.writerow(row)


def _decode_dataclass(cls: type[Any], value: Any, context: str) -> Any:
    if not is_dataclass(cls):
        _fail("batch_decoder_dataclass_required", context)
    item = _mapping(value, context)
    field_items = fields(cls)
    expected_fields = frozenset(field.name for field in field_items)
    if frozenset(item) != expected_fields:
        _fail("batch_dataclass_fields_mismatch", context)
    try:
        hints = get_type_hints(cls)
    except (NameError, TypeError) as exc:
        _fail("batch_dataclass_type_resolution_failed", str(exc))
    decoded = {
        field.name: _decode_value(
            hints.get(field.name, field.type),
            item[field.name],
            f"{context}.{field.name}",
        )
        for field in field_items
    }
    try:
        return cls(**decoded)
    except (TypeError, ValueError) as exc:
        _fail("batch_dataclass_value_invalid", f"{context}: {exc}")


def _decode_value(annotation: Any, value: Any, context: str) -> Any:
    if annotation is Any:
        return _copy_json_value(value, context)
    if annotation is type(None):
        if value is not None:
            _fail("batch_value_type_invalid", context)
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {types.UnionType, getattr(__import__("typing"), "Union")}:
        if value is None and type(None) in args:
            return None
        errors = []
        for option in args:
            if option is type(None):
                continue
            try:
                return _decode_value(option, value, context)
            except PairedInterventionContractError as exc:
                errors.append(exc.code)
        _fail("batch_union_value_invalid", f"{context}: {','.join(errors)}")
    if origin is tuple:
        sequence = _strict_sequence(value, context)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(
                _decode_value(args[0], item, f"{context}[{index}]")
                for index, item in enumerate(sequence)
            )
        if len(sequence) != len(args):
            _fail("batch_tuple_length_invalid", context)
        return tuple(
            _decode_value(item_type, item, f"{context}[{index}]")
            for index, (item_type, item) in enumerate(
                zip(args, sequence, strict=True)
            )
        )
    if origin in {dict, Mapping} or (
        isinstance(origin, type) and issubclass(origin, Mapping)
    ):
        item = _mapping(value, context)
        key_type, value_type = args or (str, Any)
        output = {}
        for key, nested in item.items():
            decoded_key = _decode_value(
                key_type,
                key,
                f"{context}.<key>",
            )
            output[decoded_key] = _decode_value(
                value_type,
                nested,
                f"{context}.{key}",
            )
        return output
    if annotation is np.ndarray:
        sequence = _strict_sequence(value, context)
        dtype = bool if context.endswith(".candidate_mask") else float
        try:
            array = np.asarray(sequence, dtype=dtype)
        except (TypeError, ValueError) as exc:
            _fail("batch_array_invalid", f"{context}: {exc}")
        if array.dtype.kind in "fci" and not np.all(np.isfinite(array)):
            _fail("batch_nonfinite_value", context)
        array = array.copy()
        array.setflags(write=False)
        return array
    if isinstance(annotation, type) and is_dataclass(annotation):
        return _decode_dataclass(annotation, value, context)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return annotation(value)
        except (TypeError, ValueError) as exc:
            _fail("batch_enum_value_invalid", f"{context}: {exc}")
    if annotation is bool:
        if type(value) is not bool:
            _fail("batch_bool_value_invalid", context)
        return value
    if annotation is int:
        return _strict_int(value, context)
    if annotation is float:
        return _finite_number(value, context)
    if annotation is str:
        if not isinstance(value, str):
            _fail("batch_string_value_invalid", context)
        return value
    _fail("batch_annotation_unsupported", f"{context}: {annotation!r}")


def _copy_json_value(value: Any, context: str) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if isinstance(value, float):
        if not isfinite(value):
            _fail("batch_nonfinite_value", context)
        return float(value)
    if isinstance(value, Mapping):
        return {
            str(key): _copy_json_value(item, f"{context}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(
            _copy_json_value(item, f"{context}[{index}]")
            for index, item in enumerate(value)
        )
    _fail("batch_json_value_invalid", context)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _jsonable(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _assert_truth_free(
    value: Any,
    path: str = "$",
) -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _assert_truth_free(
                getattr(value, item.name),
                f"{path}.{item.name}",
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_INPUT_KEYS:
                _fail("batch_forbidden_input_key", f"{path}.{key}")
            _assert_truth_free(
                item,
                f"{path}.{key}",
            )
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            _assert_truth_free(
                item,
                f"{path}[{index}]",
            )


def _assert_all_finite(value: Any, path: str = "$") -> None:
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            _assert_all_finite(getattr(value, item.name), f"{path}.{item.name}")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_all_finite(item, f"{path}.{key}")
        return
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "fci" and not np.all(np.isfinite(value)):
            _fail("batch_nonfinite_value", path)
        return
    if isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            _assert_all_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, (float, np.floating)) and not isfinite(float(value)):
        _fail("batch_nonfinite_value", path)


def _strict_mapping(value: Any, expected: frozenset[str], code: str) -> Mapping[str, Any]:
    item = _mapping(value, code)
    if frozenset(item) != expected:
        _fail(code)
    return item


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("batch_mapping_required", context)
    if any(not isinstance(key, str) for key in value):
        _fail("batch_mapping_key_invalid", context)
    return value


def _strict_sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail("batch_sequence_required", context)
    return value


def _strict_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("batch_integer_invalid", context)
    return int(value)


def _nonnegative_int(value: Any, context: str) -> int:
    result = _strict_int(value, context)
    if result < 0:
        _fail("batch_integer_invalid", context)
    return result


def _finite_number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("batch_number_invalid", context)
    result = float(value)
    if not isfinite(result):
        _fail("batch_nonfinite_value", context)
    return result


def _finite_nonnegative(value: Any, context: str) -> float:
    result = _finite_number(value, context)
    if result < 0.0:
        _fail("batch_number_invalid", context)
    return result


def _required_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("batch_text_invalid", context)
    return value.strip()


def _sha256_text(value: Any, context: str) -> str:
    text = _required_text(value, context)
    if _SHA256_PATTERN.fullmatch(text) is None or len(set(text)) == 1:
        _fail("batch_sha256_invalid", context)
    return text


def _validated_utc_timestamp(value: Any) -> str:
    text = _required_text(value, "evaluated_at")
    if _UTC_TIMESTAMP_PATTERN.fullmatch(text) is None:
        _fail("batch_evaluated_at_invalid")
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        _fail("batch_evaluated_at_invalid", str(exc))
    return text


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        _fail("batch_file_hash_failed", str(exc))
    return digest.hexdigest()


def _fail(code: str, message: str | None = None) -> None:
    raise PairedInterventionContractError(code, message)


__all__ = [
    "ANONYMOUS_PLANNING_FRAME_FILE_SCHEMA_V1",
    "BATCH_CHECKSUMS_FILENAME",
    "BATCH_PER_SEED_FILENAME",
    "BATCH_REPORT_FILENAME",
    "BATCH_RESULT_FILENAME",
    "ISOLATED_INTERVENTION_BATCH_FRAME_SUMMARY_SCHEMA_V1",
    "ISOLATED_INTERVENTION_BATCH_MANIFEST_SCHEMA_V1",
    "ISOLATED_INTERVENTION_BATCH_RESULT_SCHEMA_V1",
    "ISOLATED_INTERVENTION_BATCH_SCOPE",
    "ISOLATED_INTERVENTION_BATCH_SEEDS_V1",
    "IsolatedInterventionBatchManifest",
    "IsolatedInterventionFrameReference",
    "IsolatedInterventionSeedManifest",
    "load_isolated_intervention_batch_manifest",
    "main",
    "run_isolated_intervention_batch",
    "write_anonymous_planning_frame_evidence",
]


if __name__ == "__main__":
    raise SystemExit(main())
