"""Strict replay audit for one D4 readiness-v3 full episode pair."""

from __future__ import annotations

from collections import Counter
import copy
from functools import partial
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any, Mapping, Sequence
import uuid

import numpy as np

from .d4_v3_isolated_paired_audit import (
    D4_V3_ISOLATED_SCOPE,
    D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION,
    D4_V3_ISOLATED_V2_MANIFEST_KEYS,
    D4V3IsolatedPairedAuditError,
    validate_d4_v3_source_provenance,
)
from .runtime_plan_outcome_join import (
    ASSIGNMENT_PLAN_ACK_TOPIC,
    ASSIGNMENT_PLAN_TOPIC,
    D2_EVALUATOR_ONLY_BOUNDED_COAST_BRIDGE_POLICY,
    D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S,
    GUIDANCE_COMMAND_TOPIC,
    RuntimePlanOutcomeJoinInputs,
    _build_identity_index,
    _identity_mapping_for_window,
    _load_truth_state,
    _state_window,
    evaluate_runtime_plan_outcomes,
    load_runtime_plan_outcome_join_inputs,
)


D4_V3_FULL_EPISODE_CHAIN_AUDIT_SCHEMA_VERSION = (
    "d6.d4-v3-full-episode-chain-audit.v2"
)
D4_V3_FULL_EPISODE_CHAIN_AUDIT_DATE = "2026-07-29"
D4_V3_BOUNDED_COAST_BRIDGE_SCHEMA_VERSION = (
    "d6.d4-v3-bounded-coast-bridge.v1"
)
D4_V3_BOUNDED_COAST_BRIDGE_SOURCE_SCHEMA_VERSION = (
    "d6.d4-v3-bounded-coast-bridge-source.v1"
)
D4_V3_BOUNDED_COAST_BRIDGE_POLICY = (
    "offline_confirmed_unmatched_double_anchor_v1"
)

_D2_IDENTITY_MANIFEST_V2 = "scalable3d-offline-identity-evaluation-manifest-v2"
_D2_IDENTITY_EVALUATION_V2 = "d2.scalable3d_identity_evaluation.v2"
_D2_IDENTITY_EVIDENCE_V2 = "d2.scalable3d_identity_evidence.v2"
_D2_IDENTITY_POLICY_V2 = "d2.scalable3d_identity_commitment_policy.v2"
_D2_FRAME_MAPPING_V1 = "d2.scalable3d_global_track_truth_mapping.v1"
_D2_COMMITMENT_V2 = "d2.identity-evidence-commitment.v2"
_D2_COMMITMENT_POLICY_V2 = "d2-structural-ambiguity-commitment-v2"
_D2_TRUTH_LABEL_V2 = "d2.scalable3d_observation_truth.v2"
_RUNTIME_JOIN_V2 = "d6.runtime-plan-outcome-join.v2"
_OFFLINE_TRUTH_V2 = "scalable3d-offline-truth-v2"
_RESOURCE_ID_RE = re.compile(r"^INT-([0-9]{4})$")


def audit_d4_v3_full_episode_chain(
    input_root: str | Path,
    *,
    expected_sha256sums_sha256: str,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    """Replay one hash-bound full control/treatment episode pair."""

    root = Path(input_root).resolve()
    _expect(root.is_dir(), "input_root_unavailable", str(root))
    checksum_path = root / "SHA256SUMS"
    anchor = _sha256_file(checksum_path)
    _expect(
        anchor == _normalise_sha256(expected_sha256sums_sha256),
        "sha256sums_anchor_mismatch",
        "root SHA256SUMS does not match the external anchor",
    )
    checksums = _load_sha256sums(checksum_path, root=root)
    actual_inventory = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != checksum_path
    }
    _expect(
        set(checksums) == actual_inventory,
        "full_episode_inventory_binding_mismatch",
        "every full-episode file must be bound exactly once by SHA256SUMS",
    )
    for relative, digest in checksums.items():
        _expect(
            _sha256_file(root / relative) == digest,
            "source_artifact_sha256_mismatch",
            relative,
        )

    manifest = _load_json(root / "manifest.json", "rollout manifest")
    _require_exact_keys(
        manifest,
        D4_V3_ISOLATED_V2_MANIFEST_KEYS,
        "rollout manifest",
    )
    _expect(
        manifest.get("schema_version")
        == D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION,
        "source_schema_unsupported",
        str(manifest.get("schema_version")),
    )
    _expect(
        manifest.get("scope") == D4_V3_ISOLATED_SCOPE,
        "source_scope_unsupported",
        str(manifest.get("scope")),
    )
    seeds = _integer_sequence(manifest.get("seeds"), "manifest seeds")
    _expect(
        len(seeds) == 1 and len(set(seeds)) == 1,
        "full_episode_seed_cardinality_invalid",
        "one full-chain audit requires exactly one unique seed",
    )
    seed = seeds[0]
    _expect(
        _nonnegative_int(manifest.get("pair_count"), "manifest pair_count") == 1,
        "manifest_pair_count_mismatch",
        "full-chain manifest must contain one pair",
    )
    provenance = validate_d4_v3_source_provenance(
        _mapping(
            manifest.get("source_provenance"),
            "manifest source_provenance",
        ),
        seeds=seeds,
    )
    rows = _load_jsonl(root / "paired_evidence.jsonl", "paired evidence")
    _expect(
        len(rows) == 1
        and _nonnegative_int(rows[0].get("seed"), "paired seed") == seed,
        "paired_evidence_seed_mismatch",
        "paired JSONL must contain the manifest seed exactly once",
    )
    _expect(
        _canonical_sha256(rows)
        == _normalise_sha256(manifest.get("pair_summary_sha256")),
        "pair_summary_sha256_mismatch",
        "manifest does not bind paired JSONL",
    )
    per_seed = _load_json(
        root / f"seed_{seed}" / "paired_evidence.json",
        "per-seed paired evidence",
    )
    _expect(
        per_seed == rows[0],
        "per_seed_jsonl_payload_mismatch",
        str(seed),
    )

    episode_manifest_checks: dict[str, Any] = {}
    for arm in ("control", "treatment"):
        episode_manifest = _load_json(
            root / f"seed_{seed}" / arm / "manifest.json",
            f"{arm} episode manifest",
        )
        expected_digest = _normalise_sha256(
            provenance["episode_manifest_sha256"][str(seed)][arm]
        )
        actual_digest = _canonical_sha256(episode_manifest)
        _expect(
            actual_digest == expected_digest,
            "episode_manifest_provenance_mismatch",
            arm,
        )
        _expect(
            episode_manifest.get("seed") == seed
            and episode_manifest.get("git_commit")
            == provenance["git_commit"]
            and episode_manifest.get("repository_dirty")
            == provenance["repository_dirty"],
            "episode_manifest_source_provenance_mismatch",
            arm,
        )
        episode_manifest_checks[arm] = {
            "canonical_sha256": f"sha256:{actual_digest}",
            "git_commit": episode_manifest["git_commit"],
            "repository_dirty": episode_manifest["repository_dirty"],
            "verified": True,
        }

    repo = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[3]
    )
    workspace_source = _compare_workspace_sources(
        provenance["implementation_file_sha256"],
        repository_root=repo,
    )
    arm_results: dict[str, Any] = {}
    replay_payloads: dict[str, Mapping[str, Any]] = {}
    replay_inputs: dict[str, RuntimePlanOutcomeJoinInputs] = {}
    for arm in ("control", "treatment"):
        summary, replay, inputs = _audit_arm(
            root,
            seed=seed,
            arm=arm,
            checksums=checksums,
        )
        arm_results[arm] = summary
        replay_payloads[arm] = replay
        replay_inputs[arm] = inputs

    chain = _audit_treatment_chain(
        root / f"seed_{seed}" / "treatment" / "online_observations.jsonl",
        replay_payloads["treatment"],
        inputs=replay_inputs["treatment"],
    )
    permissions = _mapping(
        manifest.get("production_permissions"),
        "manifest production_permissions",
    )
    expected_permissions = {
        "runtime_ack",
        "assist",
        "assignment",
        "degradation",
        "takeover",
        "coalition_commit",
        "control",
        "model_promotion",
    }
    _expect(
        set(permissions) == expected_permissions
        and all(value is False for value in permissions.values()),
        "production_permission_impersonation",
        "all production permissions must be explicitly false",
    )
    benefit = _paired_benefit_boundary(
        rows[0],
        duration_s=_positive_number(
            manifest.get("duration_s"),
            "manifest duration_s",
        ),
    )
    return {
        "schema_version": D4_V3_FULL_EPISODE_CHAIN_AUDIT_SCHEMA_VERSION,
        "audit_date": D4_V3_FULL_EPISODE_CHAIN_AUDIT_DATE,
        "input": {
            "root": str(root),
            "sha256sums_sha256": f"sha256:{anchor}",
            "verified_file_count": len(checksums),
            "source_schema_version": manifest["schema_version"],
            "source_scope": manifest["scope"],
            "seed": seed,
        },
        "integrity": {
            "passed": True,
            "root_inventory_fully_bound": True,
            "manifest_bound": True,
            "paired_jsonl_bound": True,
            "per_seed_evidence_bound": True,
            "episode_manifests_bound": True,
            "nonfinite_value_count": 0,
        },
        "source_provenance": {
            **provenance,
            "episode_manifest_replay": episode_manifest_checks,
            "current_workspace_comparison": workspace_source,
            "source_snapshot_reconstruction_required_for_mismatch": (
                not workspace_source["all_match"]
            ),
        },
        "runtime_replay": arm_results,
        "strict_chain": chain,
        "paired_outcome": benefit,
        "authority_boundary": {
            "development_runtime_assignment_ack_observed": (
                chain["accepted_development_ack_count"] > 0
            ),
            "production_runtime_authority": False,
            "production_assignment_authority": False,
            "production_degradation_authority": False,
            "production_takeover_authority": False,
            "production_coalition_commit_authority": False,
            "production_control_authority": False,
            "model_promotion_authority": False,
            "rule_fallback_required": True,
        },
        "evidence_boundary": {
            "single_seed_chain_replay_available": True,
            "final_ten_seed_chain_replay_available": False,
            "positive_benefit_claim_allowed": False,
            "causal_claim_allowed": False,
            "counterfactual_claim_allowed": False,
            "online_truth_use_count": 0,
        },
    }


def _audit_arm(
    root: Path,
    *,
    seed: int,
    arm: str,
    checksums: Mapping[str, str],
) -> tuple[
    dict[str, Any],
    Mapping[str, Any],
    RuntimePlanOutcomeJoinInputs,
]:
    arm_root = root / f"seed_{seed}" / arm
    report_root = arm_root / "d6_runtime_plan_outcomes"
    spec_path = report_root / "input_specification.json"
    spec_relative = spec_path.relative_to(root).as_posix()
    _expect(
        spec_relative in checksums,
        "runtime_input_specification_unbound",
        arm,
    )
    inputs = load_runtime_plan_outcome_join_inputs(
        spec_path,
        expected_sha256=checksums[spec_relative],
    )
    _validate_runtime_input_paths(
        inputs,
        root=root,
        arm_root=arm_root,
        checksums=checksums,
    )
    replay = evaluate_runtime_plan_outcomes(inputs)
    persisted = _load_json(
        report_root / "runtime_plan_outcome_join.json",
        f"{arm} persisted runtime join",
    )
    _validate_persisted_source_paths(
        persisted,
        inputs=inputs,
        root=root,
    )
    literal_exact = replay == persisted
    normalized_replay = _normalise_runtime_join_paths(replay)
    normalized_persisted = _normalise_runtime_join_paths(persisted)
    _expect(
        normalized_replay == normalized_persisted,
        "runtime_join_replay_mismatch",
        f"{arm} differs beyond relocatable source paths",
    )
    audit = _mapping(replay.get("audit"), f"{arm} runtime audit")
    ack = _mapping(
        replay.get("runtime_ack_evidence"),
        f"{arm} runtime ACK evidence",
    )
    admission = _mapping(replay.get("admission"), f"{arm} admission")
    _expect(
        audit.get("passed") is True
        and audit.get("fail_closed") is True
        and ack.get("source_sequence_and_payload_hash_verified") is True
        and ack.get("online_truth_use_count") == 0,
        "runtime_join_audit_not_strict",
        arm,
    )
    _expect(
        admission.get("assist_allowed") is False
        and admission.get("authority_allowed") is False
        and admission.get("ppo_allowed") is False
        and admission.get("rule_fallback_required") is True,
        "runtime_join_admission_open",
        arm,
    )
    return (
        {
            "independent_replay_passed": True,
            "persisted_result_semantically_exact": True,
            "persisted_result_literal_exact": literal_exact,
            "literal_difference_reason": (
                None
                if literal_exact
                else "atomic_staging_source_paths_are_relocatable"
            ),
            "ack_count": ack["ack_count"],
            "binding_count": ack["binding_count"],
            "d4_regional_applied_ack_count": (
                ack["d4_regional_applied_ack_count"]
            ),
            "same_identity_refresh_occurrence_count": (
                ack["same_identity_refresh_occurrence_count"]
            ),
            "source_sequence_and_payload_hash_verified": True,
            "online_truth_use_count": 0,
            "admission_status": admission["status"],
            "rule_fallback_required": True,
            "production_authority": False,
        },
        replay,
        inputs,
    )


def _load_bounded_coast_bridge_source(
    inputs: RuntimePlanOutcomeJoinInputs,
    *,
    join: Mapping[str, Any],
) -> dict[str, Any]:
    source = inputs.resolved()
    _expect(
        join.get("schema_version") == _RUNTIME_JOIN_V2,
        "bounded_coast_runtime_join_schema_unsupported",
        str(join.get("schema_version")),
    )
    source_artifacts = _mapping(
        join.get("source_artifacts"),
        "runtime join source_artifacts",
    )
    verified_hashes: dict[str, str] = {}
    for name in (
        "d2_identity_evaluation",
        "offline_truth_state",
        "scenario_config",
    ):
        artifact = getattr(source, name)
        expected = _normalise_sha256(artifact.sha256)
        actual = _sha256_file(artifact.path)
        joined = _mapping(
            source_artifacts.get(name),
            f"runtime join source artifact {name}",
        )
        _expect(
            actual == expected
            and _normalise_sha256(joined.get("sha256")) == expected
            and joined.get("verified") is True,
            "bounded_coast_source_hash_mismatch",
            name,
        )
        verified_hashes[name] = f"sha256:{actual}"

    identity = _load_json(
        source.d2_identity_evaluation.path,
        "D2 identity evaluation",
    )
    _expect(
        identity.get("schema_version") == _D2_IDENTITY_EVALUATION_V2
        and identity.get("policy_version") == _D2_IDENTITY_POLICY_V2,
        "bounded_coast_identity_schema_unsupported",
        str(identity.get("schema_version")),
    )
    configuration = _mapping(
        identity.get("configuration"),
        "D2 identity configuration",
    )
    lineage_window = _positive_number(
        configuration.get("lineage_time_window_s"),
        "D2 lineage_time_window_s",
    )
    _expect(
        lineage_window
        <= D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S + 1.0e-9,
        "bounded_coast_lineage_window_too_large",
        str(lineage_window),
    )
    scenario = _load_json(source.scenario_config.path, "scenario config")
    truth = _load_truth_state(
        source.offline_truth_state.path,
        config=scenario,
    )
    return {
        "schema_version": D4_V3_BOUNDED_COAST_BRIDGE_SOURCE_SCHEMA_VERSION,
        "identity_index": _build_identity_index(identity),
        "truth_state": truth,
        "lineage_time_window_s": lineage_window,
        "source_hashes": verified_hashes,
        "evaluation_only": True,
        "online_bus_write_performed": False,
        "global_track_id_rewrite_performed": False,
    }


def evaluate_d4_v3_bounded_coast_bridge(
    window: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    expected_plan_id: str,
    expected_plan_version: int,
    expected_ack_bus_sequence: int,
) -> dict[str, Any]:
    unavailable = partial(
        _unavailable_bounded_coast_bridge,
        resource_id=window.get("resource_id"),
        global_track_id=window.get("global_track_id"),
    )
    if source.get("schema_version") != (
        D4_V3_BOUNDED_COAST_BRIDGE_SOURCE_SCHEMA_VERSION
    ):
        return unavailable("bounded_coast_source_schema_unsupported")
    if (
        window.get("plan_id") != expected_plan_id
        or window.get("plan_version") != expected_plan_version
        or window.get("ack_bus_sequence") != expected_ack_bus_sequence
    ):
        return unavailable("bounded_coast_runtime_chain_mismatch")
    identity_mapping = window.get("identity_mapping")
    if not isinstance(identity_mapping, Mapping):
        return unavailable("bounded_coast_identity_mapping_missing")
    if not (
        window.get("state_window_available") is False
        and window.get("state_window_reason") == "identity_mapping_unavailable"
        and identity_mapping.get("available") is False
        and identity_mapping.get("reason") == "d2_mapping_unavailable_in_window"
        and identity_mapping.get("online_exposure_allowed") is False
    ):
        return unavailable("bounded_coast_not_an_identity_gap")

    global_track_id = window.get("global_track_id")
    resource_id = window.get("resource_id")
    if not (
        isinstance(global_track_id, str)
        and global_track_id
        and isinstance(resource_id, str)
        and resource_id
    ):
        return unavailable("bounded_coast_binding_identity_invalid")
    try:
        start = _nonnegative_number(
            window.get("window_start_timestamp"),
            "binding window start",
        )
        end = _nonnegative_number(
            window.get("window_end_timestamp"),
            "binding window end",
        )
    except D4V3IsolatedPairedAuditError:
        return unavailable("bounded_coast_window_timestamp_invalid")
    interval = window.get("window_interval")
    if interval not in {"closed", "left_closed_right_open"} or end <= start:
        return unavailable("bounded_coast_window_interval_invalid")

    mapping = _identity_mapping_for_window(
        source["identity_index"],
        global_track_id=global_track_id,
        start=start,
        end=end,
        end_inclusive=interval == "closed",
        allow_evaluator_only_bounded_coast_bridge=True,
    )
    if not (
        mapping.get("available") is True
        and mapping.get("policy") == D4_V3_BOUNDED_COAST_BRIDGE_POLICY
        == D2_EVALUATOR_ONLY_BOUNDED_COAST_BRIDGE_POLICY
        and mapping.get("evaluator_only") is True
        and mapping.get("online_exposure_allowed") is False
        and int(mapping.get("bridged_frame_count", 0)) > 0
    ):
        return unavailable("bounded_coast_identity_policy_rejected")
    anchor_pairs = mapping.get("bridge_anchor_pairs")
    if not isinstance(anchor_pairs, Sequence) or isinstance(
        anchor_pairs,
        (str, bytes, bytearray),
    ):
        return unavailable("bounded_coast_anchor_pairs_invalid")
    max_gap = min(
        float(source["lineage_time_window_s"]),
        D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S,
    )
    if any(
        not isinstance(pair, Mapping)
        or not isinstance(pair.get("anchor_gap_s"), (int, float))
        or isinstance(pair.get("anchor_gap_s"), bool)
        or not math.isfinite(float(pair["anchor_gap_s"]))
        or float(pair["anchor_gap_s"]) > max_gap + 1.0e-9
        for pair in anchor_pairs
    ):
        return unavailable("bounded_coast_anchor_gap_exceeded")

    state = _state_window(
        source["truth_state"],
        resource_id=resource_id,
        truth_target_id=mapping.get("truth_target_id"),
        start=start,
        end=end,
        end_inclusive=interval == "closed",
    )
    if state.get("available") is not True:
        return unavailable(
            str(state.get("reason") or "bounded_coast_state_window_unavailable")
        )
    return {
        "schema_version": D4_V3_BOUNDED_COAST_BRIDGE_SCHEMA_VERSION,
        "available": True,
        "reason": None,
        "policy": D4_V3_BOUNDED_COAST_BRIDGE_POLICY,
        "resource_id": resource_id,
        "global_track_id": global_track_id,
        "truth_target_id": mapping["truth_target_id"],
        "bridged_frame_count": mapping["bridged_frame_count"],
        "anchor_timestamps": mapping["bridge_anchor_timestamps"],
        "anchor_pairs": [dict(pair) for pair in anchor_pairs],
        "lineage_time_window_s": source["lineage_time_window_s"],
        "state_sample_count": state["sample_count"],
        "first_state_timestamp": state["first_timestamp"],
        "last_state_timestamp": state["last_timestamp"],
        "evaluation_only": True,
        "online_exposure_allowed": False,
        "online_bus_write_performed": False,
        "global_track_id_rewrite_performed": False,
        "production_runtime_authority": False,
    }


def _unavailable_bounded_coast_bridge(
    reason: str,
    *,
    resource_id: Any,
    global_track_id: Any,
) -> dict[str, Any]:
    return {
        "schema_version": D4_V3_BOUNDED_COAST_BRIDGE_SCHEMA_VERSION,
        "available": False,
        "reason": reason,
        "policy": D4_V3_BOUNDED_COAST_BRIDGE_POLICY,
        "resource_id": resource_id,
        "global_track_id": global_track_id,
        "truth_target_id": None,
        "bridged_frame_count": 0,
        "anchor_timestamps": [],
        "anchor_pairs": [],
        "evaluation_only": True,
        "online_exposure_allowed": False,
        "online_bus_write_performed": False,
        "global_track_id_rewrite_performed": False,
        "production_runtime_authority": False,
    }


def _audit_treatment_chain(
    online_path: Path,
    join: Mapping[str, Any],
    *,
    inputs: RuntimePlanOutcomeJoinInputs,
) -> dict[str, Any]:
    envelopes = _load_jsonl(online_path, "treatment online observations")
    bridge_source = _load_bounded_coast_bridge_source(inputs, join=join)
    sequences = [
        _positive_int(item.get("sequence"), "online sequence")
        for item in envelopes
    ]
    _expect(
        len(sequences) == len(set(sequences)),
        "duplicate_online_sequence",
        "treatment online bus",
    )
    by_sequence = {item["sequence"]: item for item in envelopes}
    ack_envelopes = [
        item for item in envelopes if item.get("topic") == ASSIGNMENT_PLAN_ACK_TOPIC
    ]
    ack_summary = _mapping(
        join.get("runtime_ack_evidence"),
        "runtime ACK summary",
    )
    _expect(
        len(ack_envelopes) == ack_summary.get("ack_count"),
        "runtime_ack_count_mismatch",
        "online bus and replay summary differ",
    )
    windows = _mapping_sequence(
        join.get("binding_windows"),
        "runtime binding windows",
    )
    applied_chains: list[dict[str, Any]] = []
    accepted_count = 0
    ack_by_identity: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for envelope in ack_envelopes:
        ack = _mapping(envelope.get("payload"), "runtime ACK")
        if ack.get("accepted") is True:
            accepted_count += 1
        key = (
            _required_string(ack, "plan_id", "runtime ACK"),
            _nonnegative_int(ack.get("plan_version"), "ACK plan_version"),
        )
        ack_by_identity.setdefault(key, []).append(envelope)
        regional = _mapping(
            ack.get("d4_regional_hint_evidence"),
            "D4 regional ACK evidence",
        )
        if regional.get("applied") is True:
            applied_chains.append(
                _audit_applied_chain(
                    envelope,
                    by_sequence=by_sequence,
                    envelopes=envelopes,
                    windows=windows,
                    bridge_source=bridge_source,
                )
            )
    _expect(
        len(applied_chains)
        == ack_summary.get("d4_regional_applied_ack_count")
        == 1,
        "d4_applied_chain_count_mismatch",
        "the full chain must contain exactly one applied D4 successor ACK",
    )
    applied = applied_chains[0]
    identity = (applied["successor_plan_id"], applied["successor_plan_version"])
    occurrences = ack_by_identity.get(identity, [])
    _expect(
        len(occurrences) == 2,
        "successor_refresh_occurrence_count_mismatch",
        "applied successor must have one publication and one refresh",
    )
    refresh = _audit_successor_refresh(
        occurrences,
        by_sequence=by_sequence,
        windows=windows,
    )
    return {
        "passed": True,
        "accepted_development_ack_count": accepted_count,
        "d4_regional_applied_chain_count": 1,
        "source_sequence_and_payload_hash_verified": True,
        "d7_guidance_same_chain_verified": True,
        "physical_state_window_coverage_complete": applied[
            "physical_state_window_coverage_complete"
        ],
        "bounded_coast_bridged_window_count": applied[
            "bounded_coast_bridged_window_count"
        ],
        "applied_chain": applied,
        "same_identity_refresh": refresh,
        "production_runtime_authority": False,
    }


def _audit_applied_chain(
    ack_envelope: Mapping[str, Any],
    *,
    by_sequence: Mapping[int, Mapping[str, Any]],
    envelopes: Sequence[Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
    bridge_source: Mapping[str, Any],
) -> dict[str, Any]:
    ack = _mapping(ack_envelope.get("payload"), "applied ACK")
    _expect(
        ack.get("accepted") is True
        and ack.get("fully_bound_to_guidance") is True
        and ack.get("held_binding_count") == 0
        and int(ack.get("control_applied_binding_count", 0)) > 0,
        "applied_runtime_ack_incomplete",
        "D4 successor ACK",
    )
    plan_sequence = _positive_int(
        ack.get("source_plan_bus_sequence"),
        "source plan sequence",
    )
    guidance_sequence = _positive_int(
        ack.get("source_guidance_bus_sequence"),
        "source guidance sequence",
    )
    plan_envelope = _mapping(by_sequence.get(plan_sequence), "source plan")
    guidance_envelope = _mapping(
        by_sequence.get(guidance_sequence),
        "source guidance",
    )
    _expect(
        plan_envelope.get("topic") == ASSIGNMENT_PLAN_TOPIC
        and plan_envelope.get("source") == "D3"
        and guidance_envelope.get("topic") == GUIDANCE_COMMAND_TOPIC
        and guidance_envelope.get("source") == "D7",
        "source_chain_topic_mismatch",
        "ACK source sequence does not identify D3/D7",
    )
    plan = _mapping(plan_envelope.get("payload"), "successor plan")
    guidance = _mapping(guidance_envelope.get("payload"), "source guidance")
    _expect_payload_hash(
        plan,
        ack.get("source_plan_payload_sha256"),
        "source_plan_payload_hash_mismatch",
    )
    _expect_payload_hash(
        guidance,
        ack.get("source_guidance_payload_sha256"),
        "source_guidance_payload_hash_mismatch",
    )
    metadata = _mapping(plan.get("metadata"), "successor metadata")
    regional = _mapping(
        ack.get("d4_regional_hint_evidence"),
        "D4 regional evidence",
    )
    plan_id = _required_string(ack, "plan_id", "applied ACK")
    plan_version = _nonnegative_int(
        ack.get("plan_version"),
        "applied plan_version",
    )
    _expect(
        plan.get("plan_id") == plan_id
        and plan.get("plan_version") == plan_version
        and metadata.get("regional_hint_successor_state")
        == "successor_published"
        and metadata.get("regional_hint_successor_plan_id") == plan_id
        and metadata.get("regional_hint_successor_plan_version") == plan_version
        and metadata.get("regional_hint_successor_advisory_id")
        == regional.get("advisory_id")
        and metadata.get("regional_hint_successor_advisory_version")
        == regional.get("advisory_version")
        and metadata.get("regional_hint_successor_source_plan_id")
        == regional.get("source_plan_id")
        and metadata.get("regional_hint_successor_source_plan_version")
        == regional.get("source_plan_version"),
        "d4_successor_lineage_mismatch",
        "advisory, source plan, successor, and ACK are not one chain",
    )
    authority = (
        ack.get("active_plan_owner"),
        ack.get("owner_node_id"),
        ack.get("authority_epoch"),
        ack.get("lease_expires_at_s"),
    )
    _expect(
        authority
        == (
            metadata.get("active_plan_owner"),
            metadata.get("owner_node_id"),
            metadata.get("authority_epoch"),
            metadata.get("lease_expires_at_s"),
        )
        and isinstance(authority[2], int)
        and authority[2] > 0
        and float(authority[3]) > float(ack.get("ack_timestamp")),
        "successor_authority_scope_mismatch",
        "successor owner/epoch/lease is not preserved in ACK",
    )
    source_candidates = [
        item
        for item in envelopes
        if item.get("topic") == ASSIGNMENT_PLAN_TOPIC
        and isinstance(item.get("payload"), Mapping)
        and item["payload"].get("plan_id") == regional.get("source_plan_id")
        and item["payload"].get("plan_version")
        == regional.get("source_plan_version")
        and int(item.get("sequence", 0)) < plan_sequence
    ]
    _expect(
        len(source_candidates) == 1,
        "source_plan_lineage_ambiguous",
        "D4 successor source plan must resolve uniquely",
    )
    source_plan = _mapping(source_candidates[0].get("payload"), "source plan")
    source_bindings = _plan_bindings(source_plan)
    successor_bindings = _plan_bindings(plan)
    added = sorted(successor_bindings - source_bindings)
    removed = sorted(source_bindings - successor_bindings)
    chain_windows = [
        item
        for item in windows
        if item.get("ack_bus_sequence") == ack_envelope.get("sequence")
    ]
    _expect(
        len(chain_windows) == ack.get("control_applied_binding_count")
        and all(
            item.get("guidance_command_present") is True
            and item.get("control_applied_to_world") is True
            and item.get("held") is False
            for item in chain_windows
        ),
        "d7_guidance_chain_incomplete",
        "not every non-hold binding has a same-chain D7 command",
    )
    available_state_windows = [
        item for item in chain_windows if item.get("state_window_available") is True
    ]
    bridge_results = [
        evaluate_d4_v3_bounded_coast_bridge(
            item,
            source=bridge_source,
            expected_plan_id=plan_id,
            expected_plan_version=plan_version,
            expected_ack_bus_sequence=_positive_int(
                ack_envelope.get("sequence"),
                "applied ACK sequence",
            ),
        )
        for item in chain_windows
        if item.get("state_window_available") is not True
    ]
    accepted_bridges = [
        item for item in bridge_results if item.get("available") is True
    ]
    rejected_bridges = [
        item for item in bridge_results if item.get("available") is not True
    ]
    unavailable_state_windows = [
        {
            "resource_id": item.get("resource_id"),
            "global_track_id": item.get("global_track_id"),
            "reason": item.get("state_window_reason"),
        }
        for item, bridge in zip(
            (
                candidate
                for candidate in chain_windows
                if candidate.get("state_window_available") is not True
            ),
            bridge_results,
        )
        if bridge.get("available") is not True
    ]
    effective_state_window_count = (
        len(available_state_windows) + len(accepted_bridges)
    )
    signatures = {
        _required_string(
            item,
            "execution_signature_sha256",
            "binding window",
        )
        for item in chain_windows
    }
    _expect(
        len(signatures) == 1,
        "binding_window_execution_signature_mismatch",
        "one ACK occurrence must have one execution signature",
    )
    return {
        "advisory_id": regional["advisory_id"],
        "source_plan_id": regional["source_plan_id"],
        "source_plan_version": regional["source_plan_version"],
        "successor_plan_id": plan_id,
        "successor_plan_version": plan_version,
        "ack_bus_sequence": ack_envelope["sequence"],
        "source_plan_bus_sequence": plan_sequence,
        "source_guidance_bus_sequence": guidance_sequence,
        "execution_signature_sha256": next(iter(signatures)),
        "assignment_binding_count": len(successor_bindings),
        "d7_guidance_binding_count": len(chain_windows),
        "non_hold_control_window_count": len(chain_windows),
        "native_physical_state_window_count": len(available_state_windows),
        "bounded_coast_bridged_window_count": len(accepted_bridges),
        "physical_state_window_count": effective_state_window_count,
        "physical_state_window_coverage_complete": (
            effective_state_window_count == len(chain_windows)
        ),
        "physical_state_window_unavailable": unavailable_state_windows,
        "bounded_coast_bridge": {
            "schema_version": D4_V3_BOUNDED_COAST_BRIDGE_SCHEMA_VERSION,
            "policy": D4_V3_BOUNDED_COAST_BRIDGE_POLICY,
            "max_anchor_gap_s": (
                D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S
            ),
            "attempted_window_count": len(bridge_results),
            "accepted_window_count": len(accepted_bridges),
            "rejected_window_count": len(rejected_bridges),
            "accepted": accepted_bridges,
            "rejected": rejected_bridges,
            "evaluation_only": True,
            "online_bus_write_performed": False,
            "global_track_id_rewrite_performed": False,
        },
        "authority_epoch": authority[2],
        "lease_expires_at_s": authority[3],
        "resource_target_action_identifiable": bool(added or removed),
        "binding_additions": [list(item) for item in added],
        "binding_removals": [list(item) for item in removed],
        "action_interpretation": (
            "resource_target_or_coalition_binding_changed"
            if added or removed
            else "successor_acknowledged_but_resource_target_and_coalition_bindings_unchanged"
        ),
        "production_runtime_authority": False,
    }


def _audit_successor_refresh(
    occurrences: Sequence[Mapping[str, Any]],
    *,
    by_sequence: Mapping[int, Mapping[str, Any]],
    windows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(
        occurrences,
        key=lambda item: float(item["payload"]["ack_timestamp"]),
    )
    first, refresh = ordered
    first_ack = _mapping(first.get("payload"), "successor ACK")
    refresh_ack = _mapping(refresh.get("payload"), "successor refresh ACK")
    first_plan = _mapping(
        _mapping(
            by_sequence.get(first_ack["source_plan_bus_sequence"]),
            "successor plan envelope",
        ).get("payload"),
        "successor plan",
    )
    refresh_plan = _mapping(
        _mapping(
            by_sequence.get(refresh_ack["source_plan_bus_sequence"]),
            "refresh plan envelope",
        ).get("payload"),
        "refresh plan",
    )
    first_metadata = _mapping(first_plan.get("metadata"), "successor metadata")
    refresh_metadata = _mapping(refresh_plan.get("metadata"), "refresh metadata")
    _expect(
        first_metadata.get("execution_signature_changed") is True
        and first_metadata.get("evaluation_refresh_only") is False
        and refresh_metadata.get("execution_signature_changed") is False
        and refresh_metadata.get("evaluation_refresh_only") is True
        and refresh_metadata.get("plan_refresh_only") is False
        and refresh_metadata.get("regional_hint_successor_binding_inherited")
        is True,
        "successor_refresh_flags_invalid",
        "same identity refresh does not preserve the successor contract",
    )
    authority_fields = (
        "active_plan_owner",
        "owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
    )
    _expect(
        tuple(first_ack.get(key) for key in authority_fields)
        == tuple(refresh_ack.get(key) for key in authority_fields)
        == tuple(first_metadata.get(key) for key in authority_fields)
        == tuple(refresh_metadata.get(key) for key in authority_fields),
        "successor_refresh_authority_changed",
        "same plan identity refresh changed owner, epoch, or lease",
    )
    signatures: list[str] = []
    for occurrence in ordered:
        occurrence_windows = [
            item
            for item in windows
            if item.get("ack_bus_sequence") == occurrence.get("sequence")
        ]
        values = {
            _required_string(
                item,
                "execution_signature_sha256",
                "refresh binding window",
            )
            for item in occurrence_windows
        }
        _expect(
            len(values) == 1 and occurrence_windows,
            "successor_refresh_signature_unavailable",
            "refresh occurrence lacks a unique execution signature",
        )
        signatures.append(next(iter(values)))
    _expect(
        len(set(signatures)) == 1,
        "successor_refresh_signature_changed",
        "same plan identity refresh changed strict execution signature",
    )
    return {
        "plan_id": first_ack["plan_id"],
        "plan_version": first_ack["plan_version"],
        "occurrence_count": 2,
        "initial_ack_sequence": first["sequence"],
        "refresh_ack_sequence": refresh["sequence"],
        "refresh_kind": "same_identity_evaluation_refresh",
        "authority_scope_preserved": True,
        "successor_lineage_preserved": True,
        "execution_signature_preserved": True,
        "execution_signature_sha256": signatures[0],
    }


def _paired_benefit_boundary(
    row: Mapping[str, Any],
    *,
    duration_s: float,
) -> dict[str, Any]:
    control_intercepts = _nonnegative_int(
        row.get("control_intercept_count"),
        "control intercept count",
    )
    treatment_intercepts = _nonnegative_int(
        row.get("treatment_intercept_count"),
        "treatment intercept count",
    )
    control_distance = _nonnegative_number(
        row.get("control_minimum_distance_m"),
        "control minimum distance",
    )
    treatment_distance = _nonnegative_number(
        row.get("treatment_minimum_distance_m"),
        "treatment minimum distance",
    )
    reasons: list[str] = []
    if control_intercepts == treatment_intercepts == 0:
        reasons.append("no_intercept_observed_within_manifest_horizon")
    if math.isclose(control_distance, treatment_distance, abs_tol=1.0e-9):
        reasons.append("paired_minimum_distance_identical")
    if (
        treatment_intercepts <= control_intercepts
        and treatment_distance >= control_distance - 1.0e-9
    ):
        reasons.append("no_strictly_improved_declared_outcome_metric")
    reasons.append("single_seed_chain_cannot_establish_positive_benefit")
    return {
        "paired_non_degradation": {
            "availability": "available",
            "value": (
                treatment_intercepts >= control_intercepts
                and treatment_distance <= control_distance + 1.0e-9
            ),
            "scope": "declared_intercept_count_and_minimum_distance_only",
        },
        "positive_benefit": {
            "availability": "unavailable",
            "value": False,
            "reasons": reasons,
        },
        "observed": {
            "duration_s": duration_s,
            "control_intercept_count": control_intercepts,
            "treatment_intercept_count": treatment_intercepts,
            "control_minimum_distance_m": control_distance,
            "treatment_minimum_distance_m": treatment_distance,
        },
    }


def _validate_runtime_input_paths(
    inputs: RuntimePlanOutcomeJoinInputs,
    *,
    root: Path,
    arm_root: Path,
    checksums: Mapping[str, str],
) -> None:
    for name, item in inputs.to_dict()["artifacts"].items():
        path = Path(item["path"]).resolve()
        _expect(
            path.is_relative_to(arm_root),
            "runtime_input_outside_arm",
            name,
        )
        relative = path.relative_to(root).as_posix()
        _expect(
            relative in checksums
            and _normalise_sha256(item["sha256"]) == checksums[relative],
            "runtime_input_root_binding_mismatch",
            name,
        )


def _validate_persisted_source_paths(
    persisted: Mapping[str, Any],
    *,
    inputs: RuntimePlanOutcomeJoinInputs,
    root: Path,
) -> None:
    sources = _mapping(
        persisted.get("source_artifacts"),
        "persisted source_artifacts",
    )
    for name, item in inputs.to_dict()["artifacts"].items():
        saved = _mapping(sources.get(name), f"persisted source {name}")
        expected_suffix = Path(item["path"]).resolve().relative_to(root).parts
        saved_parts = Path(_required_string(saved, "path", name)).parts
        _expect(
            len(saved_parts) >= len(expected_suffix)
            and tuple(saved_parts[-len(expected_suffix) :]) == expected_suffix,
            "persisted_source_path_lineage_mismatch",
            name,
        )


def _normalise_runtime_join_paths(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    for item in _mapping(
        result.get("source_artifacts"),
        "runtime source_artifacts",
    ).values():
        _mapping(item, "runtime source artifact")["path"] = "<relocatable>"
    return result


def _compare_workspace_sources(
    declared: Mapping[str, Any],
    *,
    repository_root: Path,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for relative in sorted(declared):
        path = repository_root / relative
        actual = _sha256_file(path) if path.is_file() else None
        expected = _normalise_sha256(declared[relative])
        rows.append(
            {
                "path": relative,
                "expected_sha256": f"sha256:{expected}",
                "current_sha256": (
                    None if actual is None else f"sha256:{actual}"
                ),
                "matches_current_workspace": actual == expected,
            }
        )
    match_count = sum(item["matches_current_workspace"] for item in rows)
    return {
        "available": True,
        "file_count": len(rows),
        "match_count": match_count,
        "mismatch_count": len(rows) - match_count,
        "all_match": match_count == len(rows),
        "files": rows,
        "interpretation": (
            "diagnostic comparison only; the root manifest binds generation-time digests"
        ),
    }


def _plan_bindings(plan: Mapping[str, Any]) -> set[tuple[Any, ...]]:
    result = {
        (
            item.get("resource_id"),
            item.get("global_track_id"),
            item.get("coalition_id"),
            item.get("coalition_version"),
            item.get("member_role"),
        )
        for item in _mapping_sequence(plan.get("assignments"), "plan assignments")
    }
    _expect(
        len(result) == len(plan.get("assignments", [])),
        "duplicate_plan_binding",
        str(plan.get("plan_id")),
    )
    return result


def write_d4_v3_full_episode_chain_audit(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Atomically write JSON, Chinese Markdown, and output checksums."""

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"full-chain audit output exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    try:
        json_path = temporary / "d4_v3_full_episode_chain_audit.json"
        markdown_path = temporary / "D4_V3_FULL_EPISODE_CHAIN_AUDIT_CN.md"
        checksum_path = temporary / "SHA256SUMS"
        json_path.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        markdown_path.write_text(
            render_d4_v3_full_episode_chain_audit_markdown(result),
            encoding="utf-8",
        )
        checksum_path.write_text(
            "".join(
                f"{_sha256_file(path)}  {path.name}\n"
                for path in (markdown_path, json_path)
            ),
            encoding="utf-8",
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "json": output / json_path.name,
        "markdown": output / markdown_path.name,
        "sha256sums": output / checksum_path.name,
    }


def render_d4_v3_full_episode_chain_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the single-seed chain replay result in Chinese."""

    source = _mapping(result["source_provenance"], "source provenance")
    chain = _mapping(result["strict_chain"], "strict chain")
    applied = _mapping(chain["applied_chain"], "applied chain")
    refresh = _mapping(chain["same_identity_refresh"], "refresh")
    paired = _mapping(result["paired_outcome"], "paired outcome")
    observed = _mapping(paired["observed"], "paired observed")
    positive = _mapping(paired["positive_benefit"], "positive benefit")
    bridge = _mapping(applied["bounded_coast_bridge"], "bounded coast bridge")
    control = _mapping(result["runtime_replay"]["control"], "control replay")
    treatment = _mapping(
        result["runtime_replay"]["treatment"],
        "treatment replay",
    )
    return "\n".join(
        [
            "# D4 readiness-v3 完整链路审计",
            "",
            "## 结论",
            "",
            (
                f"seed {result['input']['seed']} 的 control/treatment 运行联接均已"
                "独立重算。除原子写盘暂存路径外，重算结果与持久化结果逐字段一致。"
            ),
            (
                f"D4 advisory、D3 后继计划、开发 ACK、D7 指令和非 hold 控制"
                f"形成同链。D7 绑定为 {applied['d7_guidance_binding_count']} 条，"
                f"原生物理窗口为 {applied['native_physical_state_window_count']} 条，"
                f"evaluator-only bounded coast bridge 为 "
                f"{applied['bounded_coast_bridged_window_count']} 条，"
                f"有效覆盖为 {applied['physical_state_window_count']} 条。"
            ),
            (
                f"同一后继计划的首次发布和 evaluation refresh 使用同一严格签名 "
                f"`{refresh['execution_signature_sha256']}`，权属 epoch 与 lease 未丢失。"
            ),
            (
                "资源—目标及联盟绑定没有变化，实际候选动作不可辨识。"
                "开发 ACK 不产生生产权限。"
            ),
            "",
            "## 来源",
            "",
            f"- 根文件数：{result['input']['verified_file_count']}",
            f"- 来源提交：`{source['git_commit']}`",
            f"- 工作区 dirty：`{str(source['repository_dirty']).lower()}`",
            (
                f"- 关键实现文件：{source['implementation_file_count']} 个，集合摘要 "
                f"`{source['implementation_set_sha256']}`"
            ),
            "",
            "## 运行联接",
            "",
            "| arm | ACK | bindings | D4 applied | refresh | truth use | admission |",
            "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
            (
                f"| control | {control['ack_count']} | {control['binding_count']} | "
                f"{control['d4_regional_applied_ack_count']} | "
                f"{control['same_identity_refresh_occurrence_count']} | 0 | "
                f"{control['admission_status']} |"
            ),
            (
                f"| treatment | {treatment['ack_count']} | "
                f"{treatment['binding_count']} | "
                f"{treatment['d4_regional_applied_ack_count']} | "
                f"{treatment['same_identity_refresh_occurrence_count']} | 0 | "
                f"{treatment['admission_status']} |"
            ),
            "",
            "## 后继链",
            "",
            (
                f"- source：`{applied['source_plan_id']}:v"
                f"{applied['source_plan_version']}`"
            ),
            (
                f"- successor：`{applied['successor_plan_id']}:v"
                f"{applied['successor_plan_version']}`"
            ),
            f"- ACK bus sequence：{applied['ack_bus_sequence']}",
            f"- D7 bus sequence：{applied['source_guidance_bus_sequence']}",
            (
                f"- 物理窗口覆盖完整："
                f"{'是' if applied['physical_state_window_coverage_complete'] else '否'}"
            ),
            (
                f"- bounded coast policy：`{bridge['policy']}`，"
                f"接受 {bridge['accepted_window_count']}，"
                f"拒绝 {bridge['rejected_window_count']}，"
                "仅离线评估且不允许在线暴露"
            ),
            f"- authority epoch：{applied['authority_epoch']}",
            f"- lease 到期：{applied['lease_expires_at_s']} 秒",
            (
                f"- 资源—目标动作可辨识："
                f"{'是' if applied['resource_target_action_identifiable'] else '否'}"
            ),
            "",
            "## 结果边界",
            "",
            (
                f"manifest 时长为 {observed['duration_s']} 秒。control/treatment "
                f"拦截数为 {observed['control_intercept_count']}/"
                f"{observed['treatment_intercept_count']}，最小距离为 "
                f"{observed['control_minimum_distance_m']:.6f}/"
                f"{observed['treatment_minimum_distance_m']:.6f} 米。"
            ),
            (
                "正收益不可用，值为 false。原因："
                + "、".join(positive["reasons"])
                + "。"
            ),
            (
                "生产分配、降级、接管、联盟提交、控制和模型晋级权限均为 false；"
                "admission 保持关闭并要求规则回退。"
            ),
            "",
        ]
    )


def _load_sha256sums(path: Path, *, root: Path) -> dict[str, str]:
    _expect(path.is_file(), "sha256sums_unavailable", str(path))
    result: dict[str, str] = {}
    for index, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        parts = line.split("  ", 1)
        _expect(len(parts) == 2, "sha256sums_line_invalid", str(index))
        relative = parts[1]
        pure = PurePosixPath(relative)
        _expect(
            relative == pure.as_posix()
            and not pure.is_absolute()
            and ".." not in pure.parts
            and relative not in {"", ".", "SHA256SUMS"}
            and relative not in result,
            "sha256sums_path_invalid",
            relative,
        )
        candidate = (root / relative).resolve()
        _expect(
            candidate.is_relative_to(root) and candidate.is_file(),
            "sha256sums_artifact_unavailable",
            relative,
        )
        result[relative] = _normalise_sha256(parts[0])
    _expect(result, "sha256sums_empty", str(path))
    return result


def _load_json(path: Path, context: str) -> dict[str, Any]:
    _expect(path.is_file(), "json_artifact_unavailable", context)
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except D4V3IsolatedPairedAuditError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("json_decode_failed", f"{context}: {type(exc).__name__}")
    return dict(_mapping(value, context))


def _load_jsonl(path: Path, context: str) -> list[dict[str, Any]]:
    _expect(path.is_file(), "jsonl_artifact_unavailable", context)
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        _expect(line and line.strip() == line, "jsonl_line_invalid", str(index))
        try:
            value = json.loads(
                line,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except D4V3IsolatedPairedAuditError:
            raise
        except json.JSONDecodeError as exc:
            _fail("jsonl_decode_failed", f"{context}: {exc.msg}")
        rows.append(dict(_mapping(value, f"{context} line {index}")))
    return rows


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _expect(key not in result, "duplicate_json_key", key)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("nonfinite_json_value", value)


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    _expect(isinstance(value, Mapping), "mapping_required", context)
    return value


def _mapping_sequence(value: Any, context: str) -> list[Mapping[str, Any]]:
    return [
        _mapping(item, f"{context}[{index}]")
        for index, item in enumerate(_sequence(value, context))
    ]


def _sequence(value: Any, context: str) -> Sequence[Any]:
    _expect(
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray)),
        "sequence_required",
        context,
    )
    return value


def _integer_sequence(value: Any, context: str) -> tuple[int, ...]:
    return tuple(
        _nonnegative_int(item, context) for item in _sequence(value, context)
    )


def _required_string(
    value: Mapping[str, Any],
    key: str,
    context: str,
) -> str:
    item = value.get(key)
    _expect(
        isinstance(item, str) and bool(item.strip()),
        "nonempty_string_required",
        f"{context}.{key}",
    )
    return item


def _nonnegative_int(value: Any, context: str) -> int:
    _expect(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        "nonnegative_integer_required",
        context,
    )
    return value


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    _expect(result > 0, "positive_integer_required", context)
    return result


def _nonnegative_number(value: Any, context: str) -> float:
    _expect(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0,
        "nonnegative_number_required",
        context,
    )
    return float(value)


def _positive_number(value: Any, context: str) -> float:
    result = _nonnegative_number(value, context)
    _expect(result > 0.0, "positive_number_required", context)
    return result


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: Sequence[str] | set[str] | frozenset[str],
    context: str,
) -> None:
    _expect(
        set(value) == set(expected),
        "schema_key_mismatch",
        f"{context}: missing={sorted(set(expected) - set(value))}, "
        f"extra={sorted(set(value) - set(expected))}",
    )


def _expect_payload_hash(
    payload: Mapping[str, Any],
    expected: Any,
    code: str,
) -> None:
    _expect(
        _canonical_sha256(payload) == _normalise_sha256(expected),
        code,
        "canonical payload digest mismatch",
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _normalise_sha256(value: Any) -> str:
    text = str(value)
    if text.startswith("sha256:"):
        text = text[7:]
    _expect(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text),
        "sha256_invalid",
        str(value),
    )
    return text


def _sha256_file(path: Path) -> str:
    _expect(path.is_file(), "artifact_unavailable", str(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expect(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise D4V3IsolatedPairedAuditError(code, message)


def _fail(code: str, message: str) -> None:
    raise D4V3IsolatedPairedAuditError(code, message)


__all__ = [
    "D4_V3_BOUNDED_COAST_BRIDGE_POLICY",
    "D4_V3_BOUNDED_COAST_BRIDGE_SCHEMA_VERSION",
    "D4_V3_BOUNDED_COAST_BRIDGE_SOURCE_SCHEMA_VERSION",
    "D4_V3_FULL_EPISODE_CHAIN_AUDIT_DATE",
    "D4_V3_FULL_EPISODE_CHAIN_AUDIT_SCHEMA_VERSION",
    "audit_d4_v3_full_episode_chain",
    "evaluate_d4_v3_bounded_coast_bridge",
    "render_d4_v3_full_episode_chain_audit_markdown",
    "write_d4_v3_full_episode_chain_audit",
]
