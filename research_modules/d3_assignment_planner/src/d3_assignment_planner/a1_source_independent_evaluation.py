"""One-shot, read-only evaluation for the frozen D3 A1 development candidate.

This module deliberately exposes no training, optimizer, checkpoint-selection,
normalization-fit, threshold-tuning, plan-publication, or runtime-assist API.
It evaluates one pre-registered source exactly once into a new output
directory. All model proposals remain offline evidence and pass through the
existing deterministic assignment safety projection.
"""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .a1_assignment_aware_development import (
    A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS,
    A1AssignmentAwareConfig,
    A1AssignmentAwareContractError,
    A1AssignmentAwareTeacherFrame,
    build_a1_assignment_aware_teachers,
    load_a1_assignment_aware_bundle,
    solve_a1_safe_assignment,
)
from .learning import EDGE_FEATURE_NAMES
from .learning_data import (
    DATASET_FRAMES_FILENAME,
    DATASET_MANIFEST_FILENAME,
    DATASET_SPLITS,
    LEARNING_DATASET_SCHEMA_V2,
    LEARNING_DATASET_SPLIT_POLICY_V2,
    LearningDatasetManifest,
    LearningFrameRecord,
)


A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V1 = (
    "d3_a1_source_independent_evaluation_contract_v1"
)
A1_SOURCE_INDEPENDENT_FRAME_SCHEMA_V1 = (
    "d3_a1_source_independent_evaluation_frame_v1"
)
A1_SOURCE_INDEPENDENT_AGGREGATE_SCHEMA_V1 = (
    "d3_a1_source_independent_evaluation_aggregate_v1"
)
A1_SOURCE_INDEPENDENT_MODE = "source_independent_evaluation"
A1_SOURCE_INDEPENDENT_STATUS_NOT_RUN = (
    "evaluator_ready_evaluation_not_run"
)
A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_PASS = (
    "source_independent_evaluation_gate_passed_not_admitted"
)
A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_FAIL = (
    "source_independent_evaluation_gate_failed_not_admitted"
)

PER_FRAME_JSONL_FILENAME = "per_frame_evaluation.jsonl"
PER_FRAME_CSV_FILENAME = "per_frame_evaluation.csv"
AGGREGATE_FILENAME = "aggregate.json"
REPORT_FILENAME = "SOURCE_INDEPENDENT_EVALUATION_CN.md"
CHECKSUMS_FILENAME = "SHA256SUMS"
OFFICIAL_CONTRACT_FILENAME = (
    "a1_source_independent_evaluation_contract_v1.json"
)
_PAYLOAD_FILES = (
    PER_FRAME_JSONL_FILENAME,
    PER_FRAME_CSV_FILENAME,
    AGGREGATE_FILENAME,
    REPORT_FILENAME,
)
_OUTPUT_FILES = (*_PAYLOAD_FILES, CHECKSUMS_FILENAME)
_CLOSED_PERMISSIONS = {
    "runtime": False,
    "assist": False,
    "authority": False,
    "assignment": False,
    "plan": False,
    "control": False,
    "physical": False,
    "formal_admission": False,
    "production_admission": False,
    "optimizer": False,
    "checkpoint_selection": False,
    "normalization_refit": False,
    "threshold_adjustment": False,
}


class A1SourceIndependentEvaluationError(ValueError):
    """Stable fail-closed error for source-independent evaluation."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        super().__init__(self.code if message is None else f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class A1SourceIndependentCell:
    """One pre-registered source scenario and seed group."""

    scenario_version: str
    target_count: int
    resource_count: int
    duration_s: float
    seed_values: tuple[int, ...]

    def __post_init__(self) -> None:
        if not str(self.scenario_version).strip():
            raise A1SourceIndependentEvaluationError(
                "contract_scenario_version_empty"
            )
        if int(self.target_count) < 1 or int(self.resource_count) < 1:
            raise A1SourceIndependentEvaluationError(
                "contract_scenario_scale_invalid"
            )
        if not isfinite(float(self.duration_s)) or float(self.duration_s) <= 0.0:
            raise A1SourceIndependentEvaluationError(
                "contract_scenario_duration_invalid"
            )
        seeds = tuple(int(value) for value in self.seed_values)
        if not seeds or seeds != tuple(sorted(set(seeds))) or min(seeds) < 0:
            raise A1SourceIndependentEvaluationError(
                "contract_scenario_seed_values_invalid"
            )
        object.__setattr__(self, "scenario_version", str(self.scenario_version))
        object.__setattr__(self, "seed_values", seeds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_version": self.scenario_version,
            "target_count": int(self.target_count),
            "resource_count": int(self.resource_count),
            "duration_s": float(self.duration_s),
            "seed_values": list(self.seed_values),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A1SourceIndependentCell":
        if set(value) != {
            "scenario_version",
            "target_count",
            "resource_count",
            "duration_s",
            "seed_values",
        }:
            raise A1SourceIndependentEvaluationError(
                "contract_scenario_fields_invalid"
            )
        return cls(
            scenario_version=str(value["scenario_version"]),
            target_count=int(value["target_count"]),
            resource_count=int(value["resource_count"]),
            duration_s=float(value["duration_s"]),
            seed_values=tuple(int(item) for item in value["seed_values"]),
        )


@dataclass(frozen=True, slots=True)
class A1SourceIndependentEvaluationContract:
    """Immutable machine-readable evaluation contract."""

    contract_id: str
    mode: str
    status: str
    one_shot_policy: str
    frozen_bundle: Mapping[str, Any]
    source_dataset: Mapping[str, Any]
    thresholds: Mapping[str, Any]
    permissions: Mapping[str, bool]
    frozen_source: Mapping[str, Any]
    output_files: tuple[str, ...]
    contract_sha256: str
    cells: tuple[A1SourceIndependentCell, ...]
    raw: Mapping[str, Any]
    schema_version: str = A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V1

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> "A1SourceIndependentEvaluationContract":
        contract_path = Path(path)
        if (
            not contract_path.is_file()
            or contract_path.is_symlink()
        ):
            raise A1SourceIndependentEvaluationError(
                "contract_file_invalid"
            )
        payload_bytes = contract_path.read_bytes()
        try:
            value = json.loads(payload_bytes)
        except json.JSONDecodeError as error:
            raise A1SourceIndependentEvaluationError(
                "contract_json_invalid"
            ) from error
        if not isinstance(value, Mapping):
            raise A1SourceIndependentEvaluationError(
                "contract_root_invalid"
            )
        return cls.from_dict(
            value,
            contract_sha256=sha256(payload_bytes).hexdigest(),
        )

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        contract_sha256: str | None = None,
    ) -> "A1SourceIndependentEvaluationContract":
        required = {
            "schema_version",
            "contract_id",
            "mode",
            "status",
            "one_shot_policy",
            "frozen_bundle",
            "source_dataset",
            "thresholds",
            "permissions",
            "frozen_source",
            "output_files",
        }
        if set(value) != required:
            raise A1SourceIndependentEvaluationError(
                "contract_fields_invalid"
            )
        if value["schema_version"] != A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V1:
            raise A1SourceIndependentEvaluationError(
                "contract_schema_unsupported"
            )
        if value["mode"] != A1_SOURCE_INDEPENDENT_MODE:
            raise A1SourceIndependentEvaluationError(
                "contract_mode_invalid"
            )
        if value["status"] != A1_SOURCE_INDEPENDENT_STATUS_NOT_RUN:
            raise A1SourceIndependentEvaluationError(
                "contract_status_invalid"
            )
        if value["one_shot_policy"] != (
            "single_official_output_identity_reject_existing_v1"
        ):
            raise A1SourceIndependentEvaluationError(
                "contract_one_shot_policy_invalid"
            )
        bundle = _mapping(value["frozen_bundle"], "contract_bundle_invalid")
        _validate_bundle_contract(bundle)
        source = _mapping(value["source_dataset"], "contract_source_invalid")
        cells = _validate_source_contract(source)
        thresholds = _mapping(
            value["thresholds"],
            "contract_thresholds_invalid",
        )
        _validate_thresholds(thresholds)
        permissions = _mapping(
            value["permissions"],
            "contract_permissions_invalid",
        )
        if dict(permissions) != _CLOSED_PERMISSIONS:
            raise A1SourceIndependentEvaluationError(
                "contract_permission_escalation_forbidden"
            )
        frozen_source = _mapping(
            value["frozen_source"],
            "contract_frozen_source_invalid",
        )
        _validate_frozen_source(frozen_source)
        output_files = tuple(str(item) for item in value["output_files"])
        if output_files != _OUTPUT_FILES or len(set(output_files)) != len(
            output_files
        ):
            raise A1SourceIndependentEvaluationError(
                "contract_output_files_invalid"
            )
        digest = (
            _sha256_text(contract_sha256)
            if contract_sha256 is not None
            else sha256(_canonical_json(value).encode("ascii")).hexdigest()
        )
        contract_id = str(value["contract_id"]).strip()
        if not contract_id:
            raise A1SourceIndependentEvaluationError(
                "contract_id_empty"
            )
        return cls(
            contract_id=contract_id,
            mode=A1_SOURCE_INDEPENDENT_MODE,
            status=A1_SOURCE_INDEPENDENT_STATUS_NOT_RUN,
            one_shot_policy=str(value["one_shot_policy"]),
            frozen_bundle=dict(bundle),
            source_dataset=dict(source),
            thresholds=dict(thresholds),
            permissions=dict(permissions),
            frozen_source=dict(frozen_source),
            output_files=output_files,
            contract_sha256=digest,
            cells=cells,
            raw=dict(value),
        )

    @property
    def seed_values(self) -> tuple[int, ...]:
        return tuple(int(value) for value in self.source_dataset["seed_values"])

    @property
    def training_seed_values(self) -> tuple[int, ...]:
        return tuple(
            int(value)
            for value in self.source_dataset["training_seed_values"]
        )

    @property
    def formal_holdout_seed_values(self) -> tuple[int, ...]:
        return tuple(
            int(value)
            for value in self.source_dataset["formal_holdout_seed_values"]
        )


def run_a1_source_independent_evaluation(
    *,
    contract_path: str | Path,
    bundle_dir: str | Path,
    generation_root: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    module_root: str | Path,
    mode: str,
) -> Mapping[str, Any]:
    """Run one pre-registered evaluation and atomically write its evidence."""

    if str(mode).strip() != A1_SOURCE_INDEPENDENT_MODE:
        raise A1SourceIndependentEvaluationError(
            "source_independent_mode_required"
        )
    output = Path(output_dir)
    _reject_existing_output(output)
    root = Path(module_root).resolve()
    expected_contract_path = (
        root / "configs" / OFFICIAL_CONTRACT_FILENAME
    ).resolve()
    if Path(contract_path).resolve() != expected_contract_path:
        raise A1SourceIndependentEvaluationError(
            "official_contract_path_mismatch"
        )
    contract = A1SourceIndependentEvaluationContract.from_path(
        expected_contract_path
    )
    expected_bundle_path = (
        root / str(contract.frozen_bundle["bundle_path_hint"])
    ).resolve()
    if Path(bundle_dir).resolve() != expected_bundle_path:
        raise A1SourceIndependentEvaluationError(
            "official_bundle_path_mismatch"
        )
    source_tree_sha = source_tree_sha256(
        root,
        tuple(str(item) for item in contract.frozen_source["files"]),
    )
    if source_tree_sha != contract.frozen_source["tree_sha256"]:
        raise A1SourceIndependentEvaluationError(
            "evaluator_source_tree_sha256_mismatch"
        )
    repository = _repository_source_summary(root)
    if (
        contract.frozen_source["require_git_clean"] is True
        and repository["owned_source_dirty"]
    ):
        raise A1SourceIndependentEvaluationError(
            "evaluator_owned_source_dirty"
        )

    loaded = validate_a1_source_independent_bundle(
        contract=contract,
        bundle_dir=bundle_dir,
    )
    assert loaded.manifest is not None
    assert loaded.policy is not None
    _validate_loaded_bundle_permissions(loaded.manifest)
    source_audit = validate_a1_source_independent_input(
        contract=contract,
        generation_root=generation_root,
        dataset_dir=dataset_dir,
    )
    manifest = load_a1_source_independent_manifest(
        contract=contract,
        dataset_dir=dataset_dir,
    )

    configuration = A1AssignmentAwareConfig(
        **dict(loaded.manifest["configuration"])
    )
    normalization = loaded.manifest["normalization"]
    mean = np.asarray(normalization["mean"], dtype=np.float32)
    scale = np.asarray(normalization["scale"], dtype=np.float32)
    rows = tuple(
        _evaluate_source_independent_frame(
            record,
            policy=loaded.policy,
            normalization_mean=mean,
            normalization_scale=scale,
            config=configuration,
            permissions=contract.permissions,
        )
        for record in iter_a1_source_independent_records(
            contract=contract,
            dataset_dir=dataset_dir,
            manifest=manifest,
        )
    )
    aggregate = aggregate_a1_source_independent_rows(
        rows,
        contract=contract,
        source_audit=source_audit,
        dataset_manifest=manifest,
        model_summary={
            "bundle_schema_version": loaded.manifest[
                "bundle_schema_version"
            ],
            "policy_version": loaded.manifest["policy_version"],
            "manifest_sha256": loaded.manifest_sha256,
            "state_dict_sha256": loaded.state_dict_sha256,
            "tree_sha256": loaded.tree_sha256,
            "normalization_fit_split": normalization["fit_split"],
            "normalization_refit_count": 0,
            "model_weight_update_count": 0,
        },
        source_summary={
            **repository,
            "evaluator_source_tree_sha256": source_tree_sha,
            "contract_sha256": contract.contract_sha256,
        },
    )
    _write_evaluation_outputs(
        output,
        rows=rows,
        aggregate=aggregate,
        contract=contract,
    )
    return aggregate


def load_a1_source_independent_manifest(
    *,
    contract: A1SourceIndependentEvaluationContract,
    dataset_dir: str | Path,
) -> LearningDatasetManifest:
    """Load the strict dataset manifest without materializing dense frames."""

    root = Path(dataset_dir)
    if not root.is_dir() or root.is_symlink():
        raise A1SourceIndependentEvaluationError(
            "source_dataset_directory_invalid"
        )
    paths = {
        DATASET_MANIFEST_FILENAME: root / DATASET_MANIFEST_FILENAME,
        DATASET_FRAMES_FILENAME: root / DATASET_FRAMES_FILENAME,
    }
    if any(
        not path.is_file() or path.is_symlink()
        for path in paths.values()
    ):
        raise A1SourceIndependentEvaluationError(
            "source_dataset_file_invalid"
        )
    manifest_value = _read_json_object(paths[DATASET_MANIFEST_FILENAME])
    try:
        manifest = LearningDatasetManifest.from_dict(manifest_value)
    except (KeyError, TypeError, ValueError) as error:
        raise A1SourceIndependentEvaluationError(
            "source_dataset_manifest_invalid"
        ) from error
    _validate_manifest_against_contract(contract=contract, manifest=manifest)
    return manifest


def iter_a1_source_independent_records(
    *,
    contract: A1SourceIndependentEvaluationContract,
    dataset_dir: str | Path,
    manifest: LearningDatasetManifest,
) -> Iterable[LearningFrameRecord]:
    """Stream, validate, and yield canonical source records exactly once."""

    root = Path(dataset_dir)
    frame_path = root / DATASET_FRAMES_FILENAME
    cell_by_seed = {
        seed: cell
        for cell in contract.cells
        for seed in cell.seed_values
    }
    split_by_seed = {
        int(seed): split
        for split in DATASET_SPLITS
        for seed in manifest.split_seed_values[split]
    }
    frame_counts: Counter[str] = Counter()
    episode_sets: dict[str, set[tuple[str, int, str]]] = {
        split: set() for split in DATASET_SPLITS
    }
    episode_inventory: set[tuple[str, int, str, str]] = set()
    seen_seeds: set[int] = set()
    prior_key: tuple[str, int, str, int] | None = None
    frames_digest = sha256()
    with frame_path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            frames_digest.update(line)
            if not line.strip():
                continue
            try:
                record = LearningFrameRecord.from_json_line(line)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
                raise A1SourceIndependentEvaluationError(
                    "source_dataset_frame_invalid",
                    f"line={line_number}",
                ) from error
            key = (
                record.scenario_version,
                int(record.seed),
                record.episode,
                int(record.frame_index),
            )
            if prior_key is not None and key <= prior_key:
                raise A1SourceIndependentEvaluationError(
                    "source_dataset_frame_order_invalid"
                )
            prior_key = key
            if record.split != split_by_seed.get(int(record.seed)):
                raise A1SourceIndependentEvaluationError(
                    "source_dataset_split_assignment_invalid"
                )
            cell = cell_by_seed.get(int(record.seed))
            if cell is None:
                raise A1SourceIndependentEvaluationError(
                    "source_record_seed_unregistered"
                )
            if record.scenario_version != cell.scenario_version:
                raise A1SourceIndependentEvaluationError(
                    "source_scenario_version_mismatch"
                )
            if (
                len(record.anonymous_targets) != cell.target_count
                or len(record.anonymous_resources) != cell.resource_count
            ):
                raise A1SourceIndependentEvaluationError(
                    "source_scenario_scale_mismatch"
                )
            frame_counts[record.split] += 1
            episode = (
                record.scenario_version,
                int(record.seed),
                record.episode,
            )
            episode_sets[record.split].add(episode)
            episode_inventory.add((*episode, record.split))
            seen_seeds.add(int(record.seed))
            yield record

    if frames_digest.hexdigest() != manifest.frames_sha256:
        raise A1SourceIndependentEvaluationError(
            "source_dataset_frames_sha256_mismatch"
        )
    if sum(frame_counts.values()) != manifest.frame_count:
        raise A1SourceIndependentEvaluationError(
            "source_dataset_frame_count_mismatch"
        )
    if {
        split: int(frame_counts[split]) for split in DATASET_SPLITS
    } != dict(manifest.split_frame_counts):
        raise A1SourceIndependentEvaluationError(
            "source_dataset_split_frame_count_mismatch"
        )
    if {
        split: len(episode_sets[split]) for split in DATASET_SPLITS
    } != dict(manifest.split_episode_counts):
        raise A1SourceIndependentEvaluationError(
            "source_dataset_split_episode_count_mismatch"
        )
    if len(episode_inventory) != manifest.episode_count:
        raise A1SourceIndependentEvaluationError(
            "source_dataset_episode_count_mismatch"
        )
    if seen_seeds != set(contract.seed_values):
        raise A1SourceIndependentEvaluationError(
            "source_dataset_seen_seed_mismatch"
        )
    if _streaming_split_hash(
        split_by_seed,
        episode_inventory,
    ) != manifest.split_hash:
        raise A1SourceIndependentEvaluationError(
            "source_dataset_split_hash_mismatch"
        )


def validate_a1_source_independent_bundle(
    *,
    contract: A1SourceIndependentEvaluationContract,
    bundle_dir: str | Path,
) -> Any:
    """Load and verify the exact frozen bundle without granting authority."""

    loaded = load_a1_assignment_aware_bundle(
        bundle_dir,
        mode=A1_SOURCE_INDEPENDENT_MODE,
        expected_manifest_sha256=contract.frozen_bundle["manifest_sha256"],
        expected_tree_sha256=contract.frozen_bundle["tree_sha256"],
    )
    if not loaded.loaded:
        raise A1SourceIndependentEvaluationError(
            "frozen_bundle_load_failed",
            loaded.fallback_reason,
        )
    if loaded.state_dict_sha256 != contract.frozen_bundle["state_dict_sha256"]:
        raise A1SourceIndependentEvaluationError(
            "frozen_bundle_state_dict_sha256_mismatch"
        )
    assert loaded.manifest is not None
    if (
        loaded.manifest["bundle_schema_version"]
        != contract.frozen_bundle["bundle_schema_version"]
        or loaded.manifest["policy_version"]
        != contract.frozen_bundle["policy_version"]
    ):
        raise A1SourceIndependentEvaluationError(
            "frozen_bundle_identity_mismatch"
        )
    _validate_loaded_bundle_permissions(loaded.manifest)
    return loaded


def validate_a1_source_independent_input(
    *,
    contract: A1SourceIndependentEvaluationContract,
    generation_root: str | Path,
    dataset_dir: str | Path,
) -> Mapping[str, Any]:
    """Validate frozen generation evidence before model inference."""

    root = Path(generation_root)
    dataset = Path(dataset_dir)
    if not root.is_dir() or root.is_symlink():
        raise A1SourceIndependentEvaluationError(
            "generation_root_invalid"
        )
    expected_dataset = root / "learning_dataset" / "d3_assignment"
    if dataset.resolve() != expected_dataset.resolve():
        raise A1SourceIndependentEvaluationError(
            "dataset_generation_root_binding_mismatch"
        )
    required_files = {
        "generation_plan.json",
        "generation_summary.json",
        "generation_checkpoint.json",
        "episode_progress.jsonl",
    }
    for filename in required_files:
        path = root / filename
        if not path.is_file() or path.is_symlink():
            raise A1SourceIndependentEvaluationError(
                "generation_evidence_file_missing",
                filename,
            )
    plan = _read_json_object(root / "generation_plan.json")
    summary = _read_json_object(root / "generation_summary.json")
    checkpoint = _read_json_object(root / "generation_checkpoint.json")
    progress = _read_json_lines(root / "episode_progress.jsonl")
    expected_cells = _flatten_contract_cells(contract.cells)
    expected_seeds = set(contract.seed_values)

    if plan.get("schedule_sha256") != contract.source_dataset[
        "generation_schedule_sha256"
    ]:
        raise A1SourceIndependentEvaluationError(
            "generation_schedule_sha256_mismatch"
        )
    if plan.get("repository_dirty") is not False:
        raise A1SourceIndependentEvaluationError(
            "generation_repository_dirty"
        )
    if int(plan.get("cell_count", -1)) != len(expected_cells):
        raise A1SourceIndependentEvaluationError(
            "generation_plan_cell_count_mismatch"
        )
    actual_plan_cells = tuple(
        (
            str(item.get("scenario", "")).strip(),
            int(item.get("scale", -1)),
            int(item.get("seed", -1)),
            float(item.get("duration_s", -1.0)),
        )
        for item in plan.get("cells", [])
        if isinstance(item, Mapping)
    )
    if actual_plan_cells != expected_cells:
        raise A1SourceIndependentEvaluationError(
            "generation_plan_cells_mismatch"
        )
    if tuple(int(value) for value in plan.get("reserved_evaluation_seeds", [])) != (
        contract.formal_holdout_seed_values
    ):
        raise A1SourceIndependentEvaluationError(
            "generation_reserved_seed_contract_mismatch"
        )
    if summary.get("repository_dirty") is not False:
        raise A1SourceIndependentEvaluationError(
            "generation_summary_repository_dirty"
        )
    if int(summary.get("completed_episode_count", -1)) != len(expected_cells):
        raise A1SourceIndependentEvaluationError(
            "generation_summary_episode_count_mismatch"
        )
    if checkpoint.get("state") != "finalized" or int(
        checkpoint.get("completed_episode_count", -1)
    ) != len(expected_cells):
        raise A1SourceIndependentEvaluationError(
            "generation_checkpoint_not_finalized"
        )
    if len(progress) != len(expected_cells):
        raise A1SourceIndependentEvaluationError(
            "generation_progress_count_mismatch"
        )

    progress_keys: list[tuple[str, int, int, float]] = []
    online_truth_use_count = 0
    finite_failure_count = 0
    for row in progress:
        key = (
            str(row.get("scenario", "")).strip(),
            int(row.get("scale", -1)),
            int(row.get("seed", -1)),
            float(row.get("duration_s", -1.0)),
        )
        progress_keys.append(key)
        online_truth_use_count += int(row.get("online_truth_use_count", -1))
        finite_failure_count += int(row.get("finite_state") is not True)
    if tuple(progress_keys) != expected_cells:
        raise A1SourceIndependentEvaluationError(
            "generation_progress_cells_mismatch"
        )
    if {key[2] for key in progress_keys} != expected_seeds:
        raise A1SourceIndependentEvaluationError(
            "generation_progress_seed_mismatch"
        )
    if online_truth_use_count != 0:
        raise A1SourceIndependentEvaluationError(
            "generation_online_truth_use_nonzero"
        )
    if finite_failure_count:
        raise A1SourceIndependentEvaluationError(
            "generation_non_finite_episode"
        )
    return {
        "generation_plan_sha256": _file_sha256(
            root / "generation_plan.json"
        ),
        "generation_summary_sha256": _file_sha256(
            root / "generation_summary.json"
        ),
        "generation_checkpoint_sha256": _file_sha256(
            root / "generation_checkpoint.json"
        ),
        "episode_progress_sha256": _file_sha256(
            root / "episode_progress.jsonl"
        ),
        "dataset_manifest_sha256": _file_sha256(
            dataset / DATASET_MANIFEST_FILENAME
        ),
        "dataset_frames_sha256": _file_sha256(
            dataset / DATASET_FRAMES_FILENAME
        ),
        "generation_schedule_sha256": plan["schedule_sha256"],
        "generation_repository_dirty": False,
        "generation_cell_count": len(progress),
        "generation_finite_failure_count": 0,
        "generation_online_truth_use_count": 0,
        "dataset_truth_field_count": 0,
        "truth_audit_basis": (
            "generation_progress_plus_d3_identity_free_schema_parser"
        ),
    }


def aggregate_a1_source_independent_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    contract: A1SourceIndependentEvaluationContract,
    source_audit: Mapping[str, Any],
    dataset_manifest: LearningDatasetManifest,
    model_summary: Mapping[str, Any],
    source_summary: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Aggregate immutable per-frame evidence using pre-registered gates."""

    items = tuple(dict(row) for row in rows)
    split_groups = {
        split: tuple(row for row in items if row.get("source_split") == split)
        for split in DATASET_SPLITS
    }
    all_metrics = _summarize_rows(items)
    split_metrics = {
        split: _summarize_rows(group)
        for split, group in split_groups.items()
    }
    thresholds = contract.thresholds
    source_seeds = {
        int(value)
        for split in DATASET_SPLITS
        for value in dataset_manifest.split_seed_values[split]
    }
    training_overlap = source_seeds & set(contract.training_seed_values)
    formal_overlap = source_seeds & set(
        contract.formal_holdout_seed_values
    )
    expected_split_counts = {
        split: int(contract.source_dataset["split_seed_counts"][split])
        for split in DATASET_SPLITS
    }
    actual_split_counts = {
        split: len(dataset_manifest.split_seed_values[split])
        for split in DATASET_SPLITS
    }
    positive = all_metrics["positive_safe_binding_change"]
    teacher_exact = all_metrics["positive_teacher_exact_match"]
    negative = all_metrics["negative_exact_r0"]
    model_hashes_match = (
        model_summary.get("manifest_sha256")
        == contract.frozen_bundle["manifest_sha256"]
        and model_summary.get("state_dict_sha256")
        == contract.frozen_bundle["state_dict_sha256"]
        and model_summary.get("tree_sha256")
        == contract.frozen_bundle["tree_sha256"]
    )
    gates = {
        "input_frame_count_matches_manifest": (
            len(items) == int(dataset_manifest.frame_count)
        ),
        "all_input_values_finite": all(
            bool(row.get("input_finite")) for row in items
        ),
        "generation_complete_and_finite": (
            int(source_audit.get("generation_cell_count", -1))
            == int(contract.source_dataset["episode_count"])
            and int(
                source_audit.get("generation_finite_failure_count", -1)
            )
            == 0
        ),
        "online_truth_use_zero": (
            int(source_audit.get("generation_online_truth_use_count", -1))
            == 0
            and int(source_audit.get("dataset_truth_field_count", -1)) == 0
        ),
        "source_seed_universe_exact": (
            source_seeds == set(contract.seed_values)
        ),
        "source_split_seed_counts_exact": (
            actual_split_counts == expected_split_counts
        ),
        "training_seed_overlap_zero": not training_overlap,
        "formal_holdout_seed_overlap_zero": not formal_overlap,
        "bundle_manifest_tree_state_exact": model_hashes_match,
        "model_weights_unchanged": (
            int(model_summary.get("model_weight_update_count", -1)) == 0
        ),
        "normalization_not_refit": (
            int(model_summary.get("normalization_refit_count", -1)) == 0
        ),
        "all_permissions_false": all(
            row.get("permissions") == dict(contract.permissions)
            for row in items
        )
        and dict(contract.permissions) == _CLOSED_PERMISSIONS,
        "zero_duplicate_resource": (
            int(all_metrics["duplicate_resource_count"]) == 0
        ),
        "zero_hard_edge_violation": (
            int(all_metrics["hard_edge_violation_count"]) == 0
        ),
        "zero_m_to_n_atomicity_violation": (
            int(all_metrics["m_to_n_atomicity_violation_count"]) == 0
        ),
        "zero_version_violation": (
            int(all_metrics["version_violation_count"]) == 0
        ),
        "zero_model_assignment_output": (
            int(all_metrics["model_assignment_output_count"]) == 0
        ),
        "zero_model_plan_output": (
            int(all_metrics["model_plan_output_count"]) == 0
        ),
        "zero_model_runtime_output": (
            int(all_metrics["model_runtime_output_count"]) == 0
        ),
        "zero_rule_matrix_mutation": (
            int(all_metrics["r0_rule_matrix_mutation_count"]) == 0
        ),
        "fallback_matrix_exact_r0": (
            int(all_metrics["fallback_frame_count"])
            == int(all_metrics["fallback_exact_r0_matrix_count"])
        ),
        "fallback_binding_exact_r0": (
            int(all_metrics["fallback_frame_count"])
            == int(all_metrics["fallback_exact_r0_binding_count"])
        ),
        "positive_denominator_nonzero": (
            int(positive["denominator"]) > 0
        ),
        "positive_safe_binding_change_passed": (
            positive["rate"] is not None
            and int(positive["numerator"])
            >= int(thresholds["minimum_positive_safe_binding_change_count"])
            and float(positive["rate"])
            + 1.0e-12
            >= float(
                thresholds[
                    "minimum_positive_safe_binding_change_rate"
                ]
            )
        ),
        "positive_teacher_exact_match_passed": (
            teacher_exact["rate"] is not None
            and int(teacher_exact["numerator"])
            >= int(thresholds["minimum_positive_teacher_exact_match_count"])
            and float(teacher_exact["rate"])
            + 1.0e-12
            >= float(
                thresholds[
                    "minimum_positive_teacher_exact_match_rate"
                ]
            )
        ),
        "negative_denominator_nonzero": (
            int(negative["denominator"]) > 0
        ),
        "negative_exact_r0_passed": (
            negative["rate"] is not None
            and float(negative["rate"]) + 1.0e-12
            >= float(thresholds["minimum_negative_exact_r0_rate"])
        ),
        "ood_distribution_complete": bool(
            all_metrics["ood_distribution_complete"]
        ),
        "rejection_distribution_complete": bool(
            all_metrics["rejection_distribution_complete"]
        ),
        "all_source_subgroups_present": all(
            int(split_metrics[split]["frame_count"]) > 0
            for split in DATASET_SPLITS
        ),
    }
    passed = all(gates.values())
    return {
        "schema_version": A1_SOURCE_INDEPENDENT_AGGREGATE_SCHEMA_V1,
        "contract_id": contract.contract_id,
        "contract_sha256": contract.contract_sha256,
        "mode": A1_SOURCE_INDEPENDENT_MODE,
        "status": (
            A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_PASS
            if passed
            else A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_FAIL
        ),
        "formal_admission_granted": False,
        "runtime_adoption_granted": False,
        "split_semantics": {
            "input_labels": list(DATASET_SPLITS),
            "evaluation_group": A1_SOURCE_INDEPENDENT_MODE,
            "normalization_refit": False,
            "checkpoint_selection": False,
            "threshold_adjustment": False,
            "training_or_model_selection_use": False,
        },
        "data_summary": {
            "dataset_schema_version": dataset_manifest.schema_version,
            "split_policy_version": dataset_manifest.split_policy_version,
            "dataset_manifest": dataset_manifest.to_dict(),
            "dataset_manifest_sha256": source_audit.get(
                "dataset_manifest_sha256"
            ),
            "dataset_frames_sha256": dataset_manifest.frames_sha256,
            "seed_values": sorted(source_seeds),
            "source_split_seed_values": {
                split: list(dataset_manifest.split_seed_values[split])
                for split in DATASET_SPLITS
            },
            "training_seed_overlap_values": sorted(training_overlap),
            "formal_holdout_seed_overlap_values": sorted(formal_overlap),
            "truth_use_audit": dict(source_audit),
        },
        "model_summary": dict(model_summary),
        "source_summary": dict(source_summary),
        "thresholds": dict(thresholds),
        "overall_metrics": all_metrics,
        "source_subgroup_metrics": split_metrics,
        "machine_gate": gates,
        "machine_gate_passed": passed,
        "permissions": dict(contract.permissions),
        "formal_holdout": {
            "seed_values": list(contract.formal_holdout_seed_values),
            "read_count": 0,
            "status": "not_read_not_evaluated",
        },
    }


def source_tree_sha256(
    module_root: str | Path,
    relative_files: Sequence[str],
) -> str:
    """Hash the pre-registered evaluator source inventory."""

    root = Path(module_root).resolve()
    if not root.is_dir():
        raise A1SourceIndependentEvaluationError(
            "module_root_invalid"
        )
    normalized = tuple(sorted(str(value) for value in relative_files))
    if not normalized or len(set(normalized)) != len(normalized):
        raise A1SourceIndependentEvaluationError(
            "frozen_source_inventory_invalid"
        )
    digest = sha256()
    for relative in normalized:
        path = root / relative
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, ValueError) as error:
            raise A1SourceIndependentEvaluationError(
                "frozen_source_path_invalid",
                relative,
            ) from error
        if path.is_symlink() or not resolved.is_file():
            raise A1SourceIndependentEvaluationError(
                "frozen_source_file_invalid",
                relative,
            )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(resolved).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _evaluate_source_independent_frame(
    record: LearningFrameRecord,
    *,
    policy: Any,
    normalization_mean: np.ndarray,
    normalization_scale: np.ndarray,
    config: A1AssignmentAwareConfig,
    permissions: Mapping[str, bool],
) -> Mapping[str, Any]:
    if record.seed in A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS:
        raise A1SourceIndependentEvaluationError(
            "formal_holdout_seed_read_forbidden"
        )
    evaluation_record = replace(record, split="validation")
    try:
        teacher = build_a1_assignment_aware_teachers(
            (evaluation_record,),
            config=config,
        )[0]
    except A1AssignmentAwareContractError as error:
        raise A1SourceIndependentEvaluationError(
            "source_independent_teacher_failed",
            error.code,
        ) from error
    teacher = replace(teacher, record=record)
    return _evaluate_teacher(
        teacher,
        policy=policy,
        normalization_mean=normalization_mean,
        normalization_scale=normalization_scale,
        config=config,
        permissions=permissions,
    )


def _evaluate_teacher(
    teacher: A1AssignmentAwareTeacherFrame,
    *,
    policy: Any,
    normalization_mean: np.ndarray,
    normalization_scale: np.ndarray,
    config: A1AssignmentAwareConfig,
    permissions: Mapping[str, bool],
) -> Mapping[str, Any]:
    record = teacher.record
    rule_matrix_before = np.asarray(record.rule_cost_matrix, dtype=float).copy()
    normalized = (
        np.asarray(record.candidate_features, dtype=np.float32)
        - normalization_mean
    ) / normalization_scale
    ood = bool(
        normalized.size
        and float(np.max(np.abs(normalized))) > float(config.ood_z_threshold)
    )
    if ood:
        residual = np.zeros(len(record.candidate_edge_indices), dtype=float)
        fallback_reason: str | None = "feature_ood"
    else:
        prediction = policy.predict(normalized)
        residual = np.asarray(prediction.delta_costs, dtype=float).reshape(-1)
        fallback_reason = None
    if residual.shape != (len(record.candidate_edge_indices),) or not np.all(
        np.isfinite(residual)
    ):
        fallback_reason = "model_output_invalid"
        residual = np.zeros(len(record.candidate_edge_indices), dtype=float)
    correction = config.alpha * np.tanh(residual)
    maximum_correction = float(
        np.max(np.abs(correction)) if correction.size else 0.0
    )
    if maximum_correction > config.maximum_abs_cost_correction + 1.0e-12:
        fallback_reason = "cost_correction_bound_exceeded"
    proposal_matrix = rule_matrix_before.copy()
    if fallback_reason is None:
        for offset, edge in enumerate(record.candidate_edge_indices):
            proposal_matrix[edge] += float(correction[offset])
    proposal = solve_a1_safe_assignment(record, proposal_matrix)
    proposal_change_count = len(
        set(proposal.selected_edges).symmetric_difference(
            teacher.r0.selected_edges
        )
    )
    raw_cost_difference = (
        proposal.objective_on_rule_matrix
        - teacher.r0.objective_on_rule_matrix
    )
    relative_difference = max(0.0, raw_cost_difference) / max(
        abs(teacher.r0.objective_on_rule_matrix),
        1.0e-12,
    )
    rejection_reasons: list[str] = []
    if proposal.safety_violation_count:
        rejection_reasons.append("projected_safety_violation")
    if (
        proposal.assigned_slot_count < teacher.r0.assigned_slot_count
        or proposal.high_threat_assigned_slot_count
        < teacher.r0.high_threat_assigned_slot_count
    ):
        rejection_reasons.append("demand_coverage_degraded")
    if proposal_change_count > config.maximum_binding_change_count:
        rejection_reasons.append("binding_change_limit_exceeded")
    if raw_cost_difference > config.maximum_rule_cost_difference + 1.0e-12:
        rejection_reasons.append("rule_cost_difference_exceeded")
    if (
        relative_difference
        > config.maximum_relative_rule_cost_difference + 1.0e-12
    ):
        rejection_reasons.append(
            "relative_rule_cost_difference_exceeded"
        )
    if fallback_reason is not None:
        rejection_reasons.append(fallback_reason)

    if rejection_reasons:
        effective = teacher.r0
        effective_matrix = rule_matrix_before.copy()
    else:
        effective = proposal
        effective_matrix = proposal_matrix
    effective_change_count = len(
        set(effective.selected_edges).symmetric_difference(
            teacher.r0.selected_edges
        )
    )
    exact_r0_binding = (
        effective.selected_edges == teacher.r0.selected_edges
    )
    exact_r0_matrix = np.array_equal(
        effective_matrix,
        rule_matrix_before,
    )
    return {
        "schema_version": A1_SOURCE_INDEPENDENT_FRAME_SCHEMA_V1,
        "mode": A1_SOURCE_INDEPENDENT_MODE,
        "evaluation_group": A1_SOURCE_INDEPENDENT_MODE,
        "evaluation_subgroup": (
            f"{A1_SOURCE_INDEPENDENT_MODE}/{record.split}"
        ),
        "source_split": record.split,
        "scenario_version": record.scenario_version,
        "seed": int(record.seed),
        "episode": record.episode,
        "frame_index": int(record.frame_index),
        "timestamp_s": float(record.timestamp_s),
        "input_finite": True,
        "online_truth_use_count": 0,
        "r0": _outcome_dict(teacher.r0),
        "teacher": {
            "opportunity": bool(teacher.opportunity),
            "reason": teacher.reason,
            "selected_edges": [
                list(edge) for edge in teacher.target.selected_edges
            ],
            "binding_change_count": int(teacher.binding_change_count),
        },
        "candidate": {
            **_outcome_dict(proposal),
            "maximum_abs_cost_correction": maximum_correction,
            "binding_change_count_from_r0": int(proposal_change_count),
            "rule_cost_difference_from_r0": float(raw_cost_difference),
            "relative_rule_cost_difference_from_r0": float(
                relative_difference
            ),
            "cost_matrix_sha256": _array_sha256(proposal_matrix),
        },
        "effective": {
            **_outcome_dict(effective),
            "binding_change_count_from_r0": int(effective_change_count),
            "cost_matrix_sha256": _array_sha256(effective_matrix),
            "exact_r0_binding": bool(exact_r0_binding),
            "exact_r0_matrix": bool(exact_r0_matrix),
        },
        "r0_rule_cost_matrix_sha256": _array_sha256(rule_matrix_before),
        "r0_rule_matrix_mutated": not np.array_equal(
            rule_matrix_before,
            record.rule_cost_matrix,
        ),
        "ood": ood,
        "rejected": bool(rejection_reasons),
        "rejection_reasons": rejection_reasons,
        "rejection_reason_count": len(rejection_reasons),
        "permissions": dict(permissions),
        "model_outputs": {
            "bounded_cost_correction_only": True,
            "assignment_output_count": 0,
            "plan_output_count": 0,
            "version_output_count": 0,
            "runtime_output_count": 0,
        },
    }


def _summarize_rows(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    counters: Counter[str] = Counter()
    rejection_reasons: Counter[str] = Counter()
    ood_by_scenario: Counter[str] = Counter()
    rejection_by_scenario: Counter[str] = Counter()
    rejection_distribution_complete = True
    for row in rows:
        teacher = row.get("teacher", {})
        effective = row.get("effective", {})
        candidate = row.get("candidate", {})
        model_outputs = row.get("model_outputs", {})
        opportunity = bool(teacher.get("opportunity"))
        changed = int(effective.get("binding_change_count_from_r0", 0)) > 0
        exact_teacher = effective.get("selected_edges") == teacher.get(
            "selected_edges"
        )
        exact_r0_binding = bool(effective.get("exact_r0_binding"))
        reasons = tuple(str(value) for value in row.get("rejection_reasons", []))
        if int(row.get("rejection_reason_count", -1)) != len(reasons):
            rejection_distribution_complete = False
        if opportunity:
            counters["positive_frame_count"] += 1
            counters["positive_safe_binding_change_count"] += int(changed)
            counters["positive_teacher_exact_match_count"] += int(
                exact_teacher
            )
        else:
            counters["negative_frame_count"] += 1
            counters["negative_exact_r0_count"] += int(exact_r0_binding)
        counters["nonzero_cost_correction_frame_count"] += int(
            float(candidate.get("maximum_abs_cost_correction", 0.0))
            > 1.0e-12
        )
        counters["safe_binding_change_frame_count"] += int(changed)
        rejected = bool(row.get("rejected"))
        counters["projection_rejection_count"] += int(rejected)
        counters["fallback_frame_count"] += int(rejected)
        counters["fallback_exact_r0_matrix_count"] += int(
            rejected and bool(effective.get("exact_r0_matrix"))
        )
        counters["fallback_exact_r0_binding_count"] += int(
            rejected and exact_r0_binding
        )
        counters["duplicate_resource_count"] += int(
            effective.get("duplicate_resource_count", 0)
        )
        counters["hard_edge_violation_count"] += int(
            effective.get("hard_edge_violation_count", 0)
        )
        counters["m_to_n_atomicity_violation_count"] += int(
            effective.get("m_to_n_atomicity_violation_count", 0)
        )
        counters["version_violation_count"] += int(
            model_outputs.get("version_output_count", 0)
        )
        counters["model_assignment_output_count"] += int(
            model_outputs.get("assignment_output_count", 0)
        )
        counters["model_plan_output_count"] += int(
            model_outputs.get("plan_output_count", 0)
        )
        counters["model_runtime_output_count"] += int(
            model_outputs.get("runtime_output_count", 0)
        )
        counters["r0_rule_matrix_mutation_count"] += int(
            bool(row.get("r0_rule_matrix_mutated"))
        )
        counters["ood_frame_count"] += int(bool(row.get("ood")))
        if row.get("ood"):
            ood_by_scenario[str(row.get("scenario_version"))] += 1
        if rejected:
            rejection_by_scenario[str(row.get("scenario_version"))] += 1
        rejection_reasons.update(reasons)
    positive_count = counters["positive_frame_count"]
    negative_count = counters["negative_frame_count"]
    return {
        "frame_count": len(rows),
        "positive_frame_count": int(positive_count),
        "negative_frame_count": int(negative_count),
        "positive_safe_binding_change": _ratio(
            counters["positive_safe_binding_change_count"],
            positive_count,
        ),
        "positive_teacher_exact_match": _ratio(
            counters["positive_teacher_exact_match_count"],
            positive_count,
        ),
        "negative_exact_r0": _ratio(
            counters["negative_exact_r0_count"],
            negative_count,
        ),
        "nonzero_cost_correction_frame_count": int(
            counters["nonzero_cost_correction_frame_count"]
        ),
        "safe_binding_change_frame_count": int(
            counters["safe_binding_change_frame_count"]
        ),
        "projection_rejection_count": int(
            counters["projection_rejection_count"]
        ),
        "fallback_frame_count": int(counters["fallback_frame_count"]),
        "fallback_exact_r0_matrix_count": int(
            counters["fallback_exact_r0_matrix_count"]
        ),
        "fallback_exact_r0_binding_count": int(
            counters["fallback_exact_r0_binding_count"]
        ),
        "duplicate_resource_count": int(
            counters["duplicate_resource_count"]
        ),
        "hard_edge_violation_count": int(
            counters["hard_edge_violation_count"]
        ),
        "m_to_n_atomicity_violation_count": int(
            counters["m_to_n_atomicity_violation_count"]
        ),
        "version_violation_count": int(
            counters["version_violation_count"]
        ),
        "model_assignment_output_count": int(
            counters["model_assignment_output_count"]
        ),
        "model_plan_output_count": int(
            counters["model_plan_output_count"]
        ),
        "model_runtime_output_count": int(
            counters["model_runtime_output_count"]
        ),
        "r0_rule_matrix_mutation_count": int(
            counters["r0_rule_matrix_mutation_count"]
        ),
        "ood_frame_count": int(counters["ood_frame_count"]),
        "ood_reason_counts": {
            "feature_ood": int(rejection_reasons.get("feature_ood", 0))
        },
        "ood_scenario_distribution": dict(sorted(ood_by_scenario.items())),
        "rejection_reason_counts": dict(
            sorted(rejection_reasons.items())
        ),
        "rejection_scenario_distribution": dict(
            sorted(rejection_by_scenario.items())
        ),
        "ood_distribution_complete": (
            int(counters["ood_frame_count"])
            == int(rejection_reasons.get("feature_ood", 0))
        ),
        "rejection_distribution_complete": (
            rejection_distribution_complete
            and int(counters["projection_rejection_count"])
            == sum(bool(row.get("rejection_reasons")) for row in rows)
        ),
    }


def _validate_manifest_against_contract(
    *,
    contract: A1SourceIndependentEvaluationContract,
    manifest: LearningDatasetManifest,
) -> None:
    if manifest.schema_version != LEARNING_DATASET_SCHEMA_V2:
        raise A1SourceIndependentEvaluationError(
            "source_dataset_schema_mismatch"
        )
    if manifest.split_policy_version != LEARNING_DATASET_SPLIT_POLICY_V2:
        raise A1SourceIndependentEvaluationError(
            "source_split_policy_mismatch"
        )
    if manifest.source_kind != contract.source_dataset["source_kind"]:
        raise A1SourceIndependentEvaluationError(
            "source_kind_mismatch"
        )
    source_seeds = {
        int(value)
        for split in DATASET_SPLITS
        for value in manifest.split_seed_values[split]
    }
    if source_seeds != set(contract.seed_values):
        raise A1SourceIndependentEvaluationError(
            "source_seed_universe_mismatch"
        )
    actual_split_counts = {
        split: len(manifest.split_seed_values[split])
        for split in DATASET_SPLITS
    }
    expected_split_counts = {
        split: int(contract.source_dataset["split_seed_counts"][split])
        for split in DATASET_SPLITS
    }
    if actual_split_counts != expected_split_counts:
        raise A1SourceIndependentEvaluationError(
            "source_split_seed_count_mismatch"
        )
    if source_seeds & set(contract.training_seed_values):
        raise A1SourceIndependentEvaluationError(
            "source_training_seed_overlap"
        )
    if source_seeds & set(contract.formal_holdout_seed_values):
        raise A1SourceIndependentEvaluationError(
            "source_formal_holdout_seed_overlap"
        )
    if int(manifest.episode_count) != int(
        contract.source_dataset["episode_count"]
    ):
        raise A1SourceIndependentEvaluationError(
            "source_episode_count_mismatch"
        )


def _write_evaluation_outputs(
    output: Path,
    *,
    rows: Sequence[Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    contract: A1SourceIndependentEvaluationContract,
) -> None:
    _reject_existing_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.tmp-",
            dir=output.parent,
        )
    )
    try:
        jsonl_path = temporary / PER_FRAME_JSONL_FILENAME
        with jsonl_path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(_canonical_json(row) + "\n")
        _write_frame_csv(temporary / PER_FRAME_CSV_FILENAME, rows)
        (temporary / AGGREGATE_FILENAME).write_text(
            _canonical_json(aggregate) + "\n",
            encoding="utf-8",
        )
        (temporary / REPORT_FILENAME).write_text(
            _render_chinese_report(aggregate, contract=contract),
            encoding="utf-8",
        )
        checksums = {
            filename: _file_sha256(temporary / filename)
            for filename in _PAYLOAD_FILES
        }
        (temporary / CHECKSUMS_FILENAME).write_text(
            "".join(
                f"{digest}  {filename}\n"
                for filename, digest in sorted(checksums.items())
            ),
            encoding="ascii",
        )
        os.replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _write_frame_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    fields = (
        "evaluation_group",
        "evaluation_subgroup",
        "source_split",
        "scenario_version",
        "seed",
        "episode",
        "frame_index",
        "timestamp_s",
        "teacher_opportunity",
        "r0_selected_edges",
        "candidate_selected_edges",
        "effective_selected_edges",
        "candidate_binding_change_count",
        "effective_binding_change_count",
        "positive_teacher_exact_match",
        "negative_exact_r0",
        "ood",
        "rejected",
        "rejection_reasons",
        "fallback_exact_r0_matrix",
        "fallback_exact_r0_binding",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            teacher = row["teacher"]
            r0 = row["r0"]
            candidate = row["candidate"]
            effective = row["effective"]
            opportunity = bool(teacher["opportunity"])
            writer.writerow(
                {
                    "evaluation_group": row["evaluation_group"],
                    "evaluation_subgroup": row["evaluation_subgroup"],
                    "source_split": row["source_split"],
                    "scenario_version": row["scenario_version"],
                    "seed": row["seed"],
                    "episode": row["episode"],
                    "frame_index": row["frame_index"],
                    "timestamp_s": row["timestamp_s"],
                    "teacher_opportunity": int(opportunity),
                    "r0_selected_edges": _canonical_json(
                        r0["selected_edges"]
                    ),
                    "candidate_selected_edges": _canonical_json(
                        candidate["selected_edges"]
                    ),
                    "effective_selected_edges": _canonical_json(
                        effective["selected_edges"]
                    ),
                    "candidate_binding_change_count": candidate[
                        "binding_change_count_from_r0"
                    ],
                    "effective_binding_change_count": effective[
                        "binding_change_count_from_r0"
                    ],
                    "positive_teacher_exact_match": int(
                        opportunity
                        and effective["selected_edges"]
                        == teacher["selected_edges"]
                    ),
                    "negative_exact_r0": int(
                        not opportunity and effective["exact_r0_binding"]
                    ),
                    "ood": int(bool(row["ood"])),
                    "rejected": int(bool(row["rejected"])),
                    "rejection_reasons": "|".join(
                        row["rejection_reasons"]
                    ),
                    "fallback_exact_r0_matrix": int(
                        bool(
                            row["rejected"]
                            and effective["exact_r0_matrix"]
                        )
                    ),
                    "fallback_exact_r0_binding": int(
                        bool(
                            row["rejected"]
                            and effective["exact_r0_binding"]
                        )
                    ),
                }
            )


def _render_chinese_report(
    aggregate: Mapping[str, Any],
    *,
    contract: A1SourceIndependentEvaluationContract,
) -> str:
    metrics = aggregate["overall_metrics"]
    positive = metrics["positive_safe_binding_change"]
    exact = metrics["positive_teacher_exact_match"]
    negative = metrics["negative_exact_r0"]
    gate_rows = "\n".join(
        f"| {name} | {'通过' if passed else '未通过'} |"
        for name, passed in aggregate["machine_gate"].items()
    )
    reason_rows = "\n".join(
        f"| {reason} | {count} |"
        for reason, count in metrics["rejection_reason_counts"].items()
    )
    if not reason_rows:
        reason_rows = "| 无 | 0 |"
    return (
        "# D3 A1 来源独立只读评价报告\n\n"
        "## 结论\n\n"
        f"评价合同为 `{contract.contract_id}`。机器门结果为"
        f"`{str(aggregate['machine_gate_passed']).lower()}`，输出状态为"
        f"`{aggregate['status']}`。本报告不授予运行、分配、计划发布、控制、"
        "物理执行或正式准入权限。\n\n"
        "输入中的 train、validation 和 test 仅保留为来源子组标签。三组均按"
        "`source_independent_evaluation` 处理，没有训练、选模、归一化重拟合或"
        "阈值调整。\n\n"
        "## 数据与模型\n\n"
        f"- 评价帧数：{metrics['frame_count']}\n"
        f"- 数据帧摘要：`{aggregate['data_summary']['dataset_frames_sha256']}`\n"
        f"- 模型清单摘要：`{aggregate['model_summary']['manifest_sha256']}`\n"
        f"- 模型状态摘要：`{aggregate['model_summary']['state_dict_sha256']}`\n"
        f"- bundle 树摘要：`{aggregate['model_summary']['tree_sha256']}`\n"
        f"- 评价源码摘要：`{aggregate['source_summary']['evaluator_source_tree_sha256']}`\n"
        f"- 在线真值使用：{aggregate['data_summary']['truth_use_audit']['generation_online_truth_use_count']}\n\n"
        "## 核心指标\n\n"
        "| 指标 | 分子 | 分母 | 比例 |\n"
        "| --- | ---: | ---: | ---: |\n"
        f"| 正类安全换绑 | {positive['numerator']} | {positive['denominator']} | {_format_rate(positive['rate'])} |\n"
        f"| 正类教师完全匹配 | {exact['numerator']} | {exact['denominator']} | {_format_rate(exact['rate'])} |\n"
        f"| 负类 exact-R0 | {negative['numerator']} | {negative['denominator']} | {_format_rate(negative['rate'])} |\n\n"
        f"失败关闭帧为 {metrics['fallback_frame_count']}，其中矩阵 exact-R0 为"
        f" {metrics['fallback_exact_r0_matrix_count']}，绑定 exact-R0 为"
        f" {metrics['fallback_exact_r0_binding_count']}。重复资源、硬禁边、多机需求"
        f"完整性和版本违规分别为 {metrics['duplicate_resource_count']}、"
        f"{metrics['hard_edge_violation_count']}、"
        f"{metrics['m_to_n_atomicity_violation_count']}、"
        f"{metrics['version_violation_count']}。\n\n"
        "## 拒绝分布\n\n"
        "| 原因 | 帧次 |\n"
        "| --- | ---: |\n"
        f"{reason_rows}\n\n"
        "## 机器门\n\n"
        "| 检查 | 结果 |\n"
        "| --- | --- |\n"
        f"{gate_rows}\n\n"
        "## 边界\n\n"
        "该结果只允许作为一次来源独立离线评价证据。正式保留种子仍未读取，"
        "模型权重和阈值未修改。后续是否进入正式保留集评价，需要 main 和 D6"
        "依据本报告及校验和另行审查。\n"
    )


def _validate_bundle_contract(value: Mapping[str, Any]) -> None:
    required = {
        "bundle_path_hint",
        "bundle_schema_version",
        "policy_version",
        "manifest_sha256",
        "state_dict_sha256",
        "tree_sha256",
    }
    if set(value) != required:
        raise A1SourceIndependentEvaluationError(
            "contract_bundle_fields_invalid"
        )
    if not str(value["bundle_path_hint"]).strip():
        raise A1SourceIndependentEvaluationError(
            "contract_bundle_path_hint_empty"
        )
    for name in ("manifest_sha256", "state_dict_sha256", "tree_sha256"):
        _sha256_text(value[name])


def _validate_source_contract(
    value: Mapping[str, Any],
) -> tuple[A1SourceIndependentCell, ...]:
    required = {
        "dataset_schema_version",
        "split_policy_version",
        "source_kind",
        "generation_schedule_sha256",
        "episode_count",
        "unique_seed_count",
        "seed_values",
        "split_seed_counts",
        "training_seed_values",
        "formal_holdout_seed_values",
        "cells",
    }
    if set(value) != required:
        raise A1SourceIndependentEvaluationError(
            "contract_source_fields_invalid"
        )
    if value["dataset_schema_version"] != LEARNING_DATASET_SCHEMA_V2:
        raise A1SourceIndependentEvaluationError(
            "contract_dataset_schema_invalid"
        )
    if value["split_policy_version"] != LEARNING_DATASET_SPLIT_POLICY_V2:
        raise A1SourceIndependentEvaluationError(
            "contract_split_policy_invalid"
        )
    if not str(value["source_kind"]).strip():
        raise A1SourceIndependentEvaluationError(
            "contract_source_kind_empty"
        )
    _sha256_text(value["generation_schedule_sha256"])
    cells = tuple(
        A1SourceIndependentCell.from_dict(item)
        for item in value["cells"]
    )
    cell_seeds = tuple(
        seed for cell in cells for seed in cell.seed_values
    )
    seeds = tuple(int(item) for item in value["seed_values"])
    if (
        seeds != tuple(sorted(set(seeds)))
        or tuple(sorted(cell_seeds)) != seeds
        or len(cell_seeds) != len(set(cell_seeds))
    ):
        raise A1SourceIndependentEvaluationError(
            "contract_source_seed_inventory_invalid"
        )
    if int(value["unique_seed_count"]) != len(seeds):
        raise A1SourceIndependentEvaluationError(
            "contract_unique_seed_count_invalid"
        )
    if int(value["episode_count"]) != len(seeds):
        raise A1SourceIndependentEvaluationError(
            "contract_episode_count_invalid"
        )
    split_counts = _mapping(
        value["split_seed_counts"],
        "contract_split_seed_counts_invalid",
    )
    if set(split_counts) != set(DATASET_SPLITS) or any(
        int(split_counts[split]) < 1 for split in DATASET_SPLITS
    ):
        raise A1SourceIndependentEvaluationError(
            "contract_split_seed_counts_invalid"
        )
    if sum(int(split_counts[split]) for split in DATASET_SPLITS) != len(
        seeds
    ):
        raise A1SourceIndependentEvaluationError(
            "contract_split_seed_count_total_invalid"
        )
    training = tuple(int(item) for item in value["training_seed_values"])
    formal = tuple(
        int(item) for item in value["formal_holdout_seed_values"]
    )
    if (
        training != tuple(sorted(set(training)))
        or formal != tuple(sorted(set(formal)))
        or set(seeds) & set(training)
        or set(seeds) & set(formal)
        or set(training) & set(formal)
        or formal != A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS
    ):
        raise A1SourceIndependentEvaluationError(
            "contract_seed_separation_invalid"
        )
    return cells


def _validate_thresholds(value: Mapping[str, Any]) -> None:
    required = {
        "minimum_positive_safe_binding_change_count",
        "minimum_positive_safe_binding_change_rate",
        "minimum_positive_teacher_exact_match_count",
        "minimum_positive_teacher_exact_match_rate",
        "minimum_negative_exact_r0_rate",
    }
    if set(value) != required:
        raise A1SourceIndependentEvaluationError(
            "contract_threshold_fields_invalid"
        )
    for name in (
        "minimum_positive_safe_binding_change_count",
        "minimum_positive_teacher_exact_match_count",
    ):
        if isinstance(value[name], bool) or int(value[name]) < 1:
            raise A1SourceIndependentEvaluationError(
                "contract_threshold_count_invalid",
                name,
            )
    for name in (
        "minimum_positive_safe_binding_change_rate",
        "minimum_positive_teacher_exact_match_rate",
        "minimum_negative_exact_r0_rate",
    ):
        item = float(value[name])
        if not isfinite(item) or not 0.0 <= item <= 1.0:
            raise A1SourceIndependentEvaluationError(
                "contract_threshold_rate_invalid",
                name,
            )


def _validate_frozen_source(value: Mapping[str, Any]) -> None:
    if set(value) != {"files", "tree_sha256", "require_git_clean"}:
        raise A1SourceIndependentEvaluationError(
            "contract_frozen_source_fields_invalid"
        )
    files = tuple(str(item) for item in value["files"])
    if (
        not files
        or files != tuple(sorted(set(files)))
        or any(
            Path(item).is_absolute()
            or ".." in Path(item).parts
            for item in files
        )
    ):
        raise A1SourceIndependentEvaluationError(
            "contract_frozen_source_inventory_invalid"
        )
    _sha256_text(value["tree_sha256"])
    if value["require_git_clean"] is not True:
        raise A1SourceIndependentEvaluationError(
            "contract_frozen_source_clean_required"
        )


def _validate_loaded_bundle_permissions(manifest: Mapping[str, Any]) -> None:
    if any(bool(value) for value in manifest["permissions"].values()):
        raise A1SourceIndependentEvaluationError(
            "bundle_permission_escalation_forbidden"
        )
    model = manifest["model_config"]
    if (
        bool(model.get("assignment_output"))
        or bool(model.get("plan_version_output"))
    ):
        raise A1SourceIndependentEvaluationError(
            "bundle_output_permission_escalation_forbidden"
        )


def _repository_source_summary(module_root: Path) -> Mapping[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=module_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--",
                "src",
                "simulations/run_a1_source_independent_evaluation.py",
                f"configs/{OFFICIAL_CONTRACT_FILENAME}",
            ],
            cwd=module_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise A1SourceIndependentEvaluationError(
            "repository_source_summary_failed"
        ) from error
    if len(commit) != 40:
        raise A1SourceIndependentEvaluationError(
            "repository_commit_invalid"
        )
    return {
        "repository_git_commit": commit,
        "owned_source_dirty": bool(status),
    }


def _flatten_contract_cells(
    cells: Sequence[A1SourceIndependentCell],
) -> tuple[tuple[str, int, int, float], ...]:
    output: list[tuple[str, int, int, float]] = []
    for cell in cells:
        scenario = cell.scenario_version.rsplit(
            f"-{cell.resource_count}v{cell.target_count}-v1",
            1,
        )[0]
        for seed in cell.seed_values:
            output.append(
                (
                    scenario,
                    int(cell.target_count),
                    int(seed),
                    float(cell.duration_s),
                )
            )
    return tuple(output)


def _streaming_split_hash(
    split_by_seed: Mapping[int, str],
    episode_inventory: Iterable[tuple[str, int, str, str]],
) -> str:
    payload = {
        "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
        "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "seed_assignments": [
            [int(seed), str(split)]
            for seed, split in sorted(split_by_seed.items())
        ],
        "episode_assignments": [
            [str(scenario), int(seed), str(episode), str(split)]
            for scenario, seed, episode, split in sorted(
                episode_inventory
            )
        ],
    }
    return sha256(_canonical_json(payload).encode("ascii")).hexdigest()


def _outcome_dict(value: Any) -> Mapping[str, Any]:
    return {
        "selected_edges": [list(edge) for edge in value.selected_edges],
        "objective_on_matrix": float(value.objective_on_matrix),
        "objective_on_rule_matrix": float(
            value.objective_on_rule_matrix
        ),
        "assigned_slot_count": int(value.assigned_slot_count),
        "high_threat_assigned_slot_count": int(
            value.high_threat_assigned_slot_count
        ),
        "duplicate_resource_count": int(
            value.duplicate_resource_count
        ),
        "hard_edge_violation_count": int(
            value.hard_edge_violation_count
        ),
        "m_to_n_atomicity_violation_count": int(
            value.m_to_n_atomicity_violation_count
        ),
        "churn": int(value.churn),
        "removed_incomplete_target_count": int(
            value.removed_incomplete_target_count
        ),
        "solver_name": value.solver_name,
    }


def _ratio(numerator: int, denominator: int) -> Mapping[str, Any]:
    return {
        "numerator": int(numerator),
        "denominator": int(denominator),
        "rate": (
            None
            if int(denominator) == 0
            else float(numerator) / float(denominator)
        ),
        "available": bool(int(denominator) > 0),
        "unavailable_reason": (
            None if int(denominator) > 0 else "denominator_zero"
        ),
    }


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(value, dtype="<f8"))
    payload = (
        _canonical_json(
            {
                "dtype": "<f8",
                "shape": list(array.shape),
            }
        ).encode("ascii")
        + b"\0"
        + array.tobytes(order="C")
    )
    return sha256(payload).hexdigest()


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise A1SourceIndependentEvaluationError(code)
    return value


def _read_json_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise A1SourceIndependentEvaluationError(
            "generation_json_invalid",
            path.name,
        ) from error
    if not isinstance(value, Mapping):
        raise A1SourceIndependentEvaluationError(
            "generation_json_root_invalid",
            path.name,
        )
    return value


def _read_json_lines(path: Path) -> tuple[Mapping[str, Any], ...]:
    output: list[Mapping[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise A1SourceIndependentEvaluationError(
                    "generation_jsonl_invalid",
                    f"{path.name}:{line_number}",
                ) from error
            if not isinstance(value, Mapping):
                raise A1SourceIndependentEvaluationError(
                    "generation_jsonl_row_invalid",
                    f"{path.name}:{line_number}",
                )
            output.append(value)
    return tuple(output)


def _reject_existing_output(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise A1SourceIndependentEvaluationError(
            "evaluation_output_already_exists"
        )


def _format_rate(value: float | None) -> str:
    return "不可用" if value is None else f"{100.0 * float(value):.2f}%"


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: Any) -> str:
    text = str(value)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise A1SourceIndependentEvaluationError(
            "sha256_value_invalid"
        )
    return text


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
