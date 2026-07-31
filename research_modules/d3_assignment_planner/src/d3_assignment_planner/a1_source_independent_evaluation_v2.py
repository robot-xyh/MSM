"""Version 2 input semantics for the frozen D3 A1 read-only evaluator.

Version 2 keeps the v1 model, thresholds, safety projection, permissions, and
source inventory. It only corrects one input interpretation: a scenario's
configured target count is not the observed number of anonymous D1/D2 tracks.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .a1_assignment_aware_development import A1AssignmentAwareConfig
from . import a1_source_independent_evaluation as v1
from .learning_data import (
    DATASET_FRAMES_FILENAME,
    DATASET_SPLITS,
    LearningDatasetManifest,
    LearningFrameRecord,
)


A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V2 = (
    "d3_a1_source_independent_evaluation_contract_v2"
)
A1_SOURCE_INDEPENDENT_FRAME_SCHEMA_V2 = (
    "d3_a1_source_independent_evaluation_frame_v2"
)
A1_SOURCE_INDEPENDENT_AGGREGATE_SCHEMA_V2 = (
    "d3_a1_source_independent_evaluation_aggregate_v2"
)
A1_SOURCE_INDEPENDENT_STATUS_V2_NOT_RUN = (
    "evaluator_v2_ready_evaluation_not_run"
)
A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_V2_PASS = (
    "source_independent_evaluation_v2_gate_passed_not_admitted"
)
A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_V2_FAIL = (
    "source_independent_evaluation_v2_gate_failed_not_admitted"
)
OFFICIAL_CONTRACT_FILENAME_V2 = (
    "a1_source_independent_evaluation_contract_v2.json"
)

_ONE_SHOT_POLICY_V2 = (
    "single_official_output_identity_reject_existing_v2"
)
_OUTPUT_IDENTITY_V2 = {
    "result_identity": "d3-a1-source-independent-evaluation-result-v2",
    "frame_schema_version": A1_SOURCE_INDEPENDENT_FRAME_SCHEMA_V2,
    "aggregate_schema_version": A1_SOURCE_INDEPENDENT_AGGREGATE_SCHEMA_V2,
    "requires_new_output_directory": True,
}


@dataclass(frozen=True, slots=True)
class A1SourceIndependentCellV2:
    """One source cell with configured and observed target counts separated."""

    scenario_version: str
    configured_scenario_target_count: int
    resource_count: int
    duration_s: float
    seed_values: tuple[int, ...]

    def __post_init__(self) -> None:
        legacy = v1.A1SourceIndependentCell(
            scenario_version=self.scenario_version,
            target_count=self.configured_scenario_target_count,
            resource_count=self.resource_count,
            duration_s=self.duration_s,
            seed_values=self.seed_values,
        )
        object.__setattr__(self, "scenario_version", legacy.scenario_version)
        object.__setattr__(
            self,
            "configured_scenario_target_count",
            int(legacy.target_count),
        )
        object.__setattr__(self, "resource_count", int(legacy.resource_count))
        object.__setattr__(self, "duration_s", float(legacy.duration_s))
        object.__setattr__(self, "seed_values", legacy.seed_values)

    @property
    def target_count(self) -> int:
        """Compatibility view used only for the frozen generation schedule."""

        return int(self.configured_scenario_target_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_version": self.scenario_version,
            "configured_scenario_target_count": int(
                self.configured_scenario_target_count
            ),
            "resource_count": int(self.resource_count),
            "duration_s": float(self.duration_s),
            "seed_values": list(self.seed_values),
        }

    def to_v1_dict(self) -> dict[str, Any]:
        return {
            "scenario_version": self.scenario_version,
            "target_count": int(self.configured_scenario_target_count),
            "resource_count": int(self.resource_count),
            "duration_s": float(self.duration_s),
            "seed_values": list(self.seed_values),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "A1SourceIndependentCellV2":
        required = {
            "scenario_version",
            "configured_scenario_target_count",
            "resource_count",
            "duration_s",
            "seed_values",
        }
        if set(value) != required:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_scenario_fields_invalid"
            )
        return cls(
            scenario_version=str(value["scenario_version"]),
            configured_scenario_target_count=int(
                value["configured_scenario_target_count"]
            ),
            resource_count=int(value["resource_count"]),
            duration_s=float(value["duration_s"]),
            seed_values=tuple(int(item) for item in value["seed_values"]),
        )


@dataclass(frozen=True, slots=True)
class A1SourceIndependentEvaluationContractV2:
    """Immutable v2 contract with the v1 safety and performance policy."""

    contract_id: str
    mode: str
    status: str
    one_shot_policy: str
    frozen_bundle: Mapping[str, Any]
    source_dataset: Mapping[str, Any]
    thresholds: Mapping[str, Any]
    permissions: Mapping[str, bool]
    frozen_source: Mapping[str, Any]
    output_identity: Mapping[str, Any]
    output_files: tuple[str, ...]
    contract_sha256: str
    cells: tuple[A1SourceIndependentCellV2, ...]
    raw: Mapping[str, Any]
    schema_version: str = A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V2

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> "A1SourceIndependentEvaluationContractV2":
        contract_path = Path(path)
        if not contract_path.is_file() or contract_path.is_symlink():
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_file_invalid"
            )
        payload_bytes = contract_path.read_bytes()
        try:
            value = json.loads(payload_bytes)
        except json.JSONDecodeError as error:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_json_invalid"
            ) from error
        if not isinstance(value, Mapping):
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_root_invalid"
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
    ) -> "A1SourceIndependentEvaluationContractV2":
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
            "output_identity",
            "output_files",
        }
        if set(value) != required:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_fields_invalid"
            )
        if value["schema_version"] != A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V2:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_schema_unsupported"
            )
        if value["mode"] != v1.A1_SOURCE_INDEPENDENT_MODE:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_mode_invalid"
            )
        if value["status"] != A1_SOURCE_INDEPENDENT_STATUS_V2_NOT_RUN:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_status_invalid"
            )
        if value["one_shot_policy"] != _ONE_SHOT_POLICY_V2:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_one_shot_policy_invalid"
            )
        output_identity = v1._mapping(
            value["output_identity"],
            "contract_v2_output_identity_invalid",
        )
        if dict(output_identity) != _OUTPUT_IDENTITY_V2:
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_output_identity_invalid"
            )
        source = v1._mapping(
            value["source_dataset"],
            "contract_v2_source_invalid",
        )
        raw_cells = source.get("cells")
        if not isinstance(raw_cells, Sequence) or isinstance(
            raw_cells,
            (str, bytes, bytearray),
        ):
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_source_cells_invalid"
            )
        cells = tuple(
            A1SourceIndependentCellV2.from_dict(item)
            for item in raw_cells
            if isinstance(item, Mapping)
        )
        if len(cells) != len(raw_cells):
            raise v1.A1SourceIndependentEvaluationError(
                "contract_v2_source_cells_invalid"
            )
        source_v1 = {
            **dict(source),
            "cells": [cell.to_v1_dict() for cell in cells],
        }
        v1_payload = {
            "schema_version": v1.A1_SOURCE_INDEPENDENT_CONTRACT_SCHEMA_V1,
            "contract_id": str(value["contract_id"]),
            "mode": value["mode"],
            "status": v1.A1_SOURCE_INDEPENDENT_STATUS_NOT_RUN,
            "one_shot_policy": (
                "single_official_output_identity_reject_existing_v1"
            ),
            "frozen_bundle": value["frozen_bundle"],
            "source_dataset": source_v1,
            "thresholds": value["thresholds"],
            "permissions": value["permissions"],
            "frozen_source": value["frozen_source"],
            "output_files": value["output_files"],
        }
        validated = v1.A1SourceIndependentEvaluationContract.from_dict(
            v1_payload
        )
        digest = (
            v1._sha256_text(contract_sha256)
            if contract_sha256 is not None
            else sha256(v1._canonical_json(value).encode("ascii")).hexdigest()
        )
        return cls(
            contract_id=validated.contract_id,
            mode=v1.A1_SOURCE_INDEPENDENT_MODE,
            status=A1_SOURCE_INDEPENDENT_STATUS_V2_NOT_RUN,
            one_shot_policy=_ONE_SHOT_POLICY_V2,
            frozen_bundle=dict(validated.frozen_bundle),
            source_dataset=dict(source),
            thresholds=dict(validated.thresholds),
            permissions=dict(validated.permissions),
            frozen_source=dict(validated.frozen_source),
            output_identity=dict(output_identity),
            output_files=validated.output_files,
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


def validate_v2_preserves_v1_contract(
    *,
    contract_v2: A1SourceIndependentEvaluationContractV2,
    contract_v1: v1.A1SourceIndependentEvaluationContract,
) -> None:
    """Require v2 to differ only in input-cardinality and output identity."""

    source_v2_as_v1 = {
        **dict(contract_v2.source_dataset),
        "cells": [cell.to_v1_dict() for cell in contract_v2.cells],
    }
    checks = {
        "contract_v2_bundle_differs_from_v1": (
            dict(contract_v2.frozen_bundle)
            == dict(contract_v1.frozen_bundle)
        ),
        "contract_v2_thresholds_differ_from_v1": (
            dict(contract_v2.thresholds)
            == dict(contract_v1.thresholds)
        ),
        "contract_v2_permissions_differ_from_v1": (
            dict(contract_v2.permissions)
            == dict(contract_v1.permissions)
        ),
        "contract_v2_source_inventory_differs_from_v1": (
            source_v2_as_v1 == dict(contract_v1.source_dataset)
        ),
        "contract_v2_output_files_differ_from_v1": (
            tuple(contract_v2.output_files)
            == tuple(contract_v1.output_files)
        ),
    }
    for code, passed in checks.items():
        if not passed:
            raise v1.A1SourceIndependentEvaluationError(code)


def iter_a1_source_independent_records_v2(
    *,
    contract: A1SourceIndependentEvaluationContractV2,
    dataset_dir: str | Path,
    manifest: LearningDatasetManifest,
) -> Iterable[LearningFrameRecord]:
    """Stream v2 records while treating observed target cardinality as dynamic."""

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
            raw: Any = None
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as error:
                _raise_frame_error(
                    "source_dataset_frame_invalid_v2",
                    _raw_frame_context(raw, line_number=line_number),
                    error,
                )
            context = _raw_frame_context(raw, line_number=line_number)
            if not isinstance(raw, Mapping):
                _raise_frame_error(
                    "source_dataset_frame_invalid_v2",
                    context,
                )
            try:
                record = LearningFrameRecord.from_dict(raw)
            except (KeyError, TypeError, ValueError) as error:
                _raise_frame_error(
                    "source_dataset_frame_invalid_v2",
                    context,
                    error,
                )
            context = _record_frame_context(
                record,
                line_number=line_number,
            )
            key = (
                record.scenario_version,
                int(record.seed),
                record.episode,
                int(record.frame_index),
            )
            if prior_key is not None and key <= prior_key:
                _raise_frame_error(
                    "source_dataset_frame_order_invalid",
                    context,
                )
            prior_key = key
            if record.split != split_by_seed.get(int(record.seed)):
                _raise_frame_error(
                    "source_dataset_split_assignment_invalid",
                    context,
                )
            cell = cell_by_seed.get(int(record.seed))
            if cell is None:
                _raise_frame_error(
                    "source_record_seed_unregistered",
                    context,
                )
            context = {
                **context,
                "configured_scenario_target_count": int(
                    cell.configured_scenario_target_count
                ),
                "configured_resource_count": int(cell.resource_count),
            }
            if record.scenario_version != cell.scenario_version:
                _raise_frame_error(
                    "source_scenario_version_mismatch",
                    context,
                )
            if len(record.anonymous_resources) != cell.resource_count:
                _raise_frame_error(
                    "source_configured_resource_count_mismatch_v2",
                    context,
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
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_frames_sha256_mismatch"
        )
    if sum(frame_counts.values()) != manifest.frame_count:
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_frame_count_mismatch"
        )
    if {
        split: int(frame_counts[split]) for split in DATASET_SPLITS
    } != dict(manifest.split_frame_counts):
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_split_frame_count_mismatch"
        )
    if {
        split: len(episode_sets[split]) for split in DATASET_SPLITS
    } != dict(manifest.split_episode_counts):
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_split_episode_count_mismatch"
        )
    if len(episode_inventory) != manifest.episode_count:
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_episode_count_mismatch"
        )
    if seen_seeds != set(contract.seed_values):
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_seen_seed_mismatch"
        )
    if v1._streaming_split_hash(
        split_by_seed,
        episode_inventory,
    ) != manifest.split_hash:
        raise v1.A1SourceIndependentEvaluationError(
            "source_dataset_split_hash_mismatch"
        )


def run_a1_source_independent_evaluation_v2(
    *,
    contract_path: str | Path,
    bundle_dir: str | Path,
    generation_root: str | Path,
    dataset_dir: str | Path,
    output_dir: str | Path,
    module_root: str | Path,
    mode: str,
) -> Mapping[str, Any]:
    """Run the v2 one-shot evaluator after all frozen checks pass."""

    if str(mode).strip() != v1.A1_SOURCE_INDEPENDENT_MODE:
        raise v1.A1SourceIndependentEvaluationError(
            "source_independent_mode_required"
        )
    output = Path(output_dir)
    v1._reject_existing_output(output)
    root = Path(module_root).resolve()
    expected_contract_path = (
        root / "configs" / OFFICIAL_CONTRACT_FILENAME_V2
    ).resolve()
    if Path(contract_path).resolve() != expected_contract_path:
        raise v1.A1SourceIndependentEvaluationError(
            "official_contract_v2_path_mismatch"
        )
    contract = A1SourceIndependentEvaluationContractV2.from_path(
        expected_contract_path
    )
    contract_v1 = v1.A1SourceIndependentEvaluationContract.from_path(
        root / "configs" / v1.OFFICIAL_CONTRACT_FILENAME
    )
    validate_v2_preserves_v1_contract(
        contract_v2=contract,
        contract_v1=contract_v1,
    )
    expected_bundle_path = (
        root / str(contract.frozen_bundle["bundle_path_hint"])
    ).resolve()
    if Path(bundle_dir).resolve() != expected_bundle_path:
        raise v1.A1SourceIndependentEvaluationError(
            "official_bundle_path_mismatch"
        )
    source_tree_sha = v1.source_tree_sha256(
        root,
        tuple(str(item) for item in contract.frozen_source["files"]),
    )
    if source_tree_sha != contract.frozen_source["tree_sha256"]:
        raise v1.A1SourceIndependentEvaluationError(
            "evaluator_source_tree_sha256_mismatch"
        )
    repository = _repository_source_summary_v2(root)
    if (
        contract.frozen_source["require_git_clean"] is True
        and repository["owned_source_dirty"]
    ):
        raise v1.A1SourceIndependentEvaluationError(
            "evaluator_owned_source_dirty"
        )

    loaded = v1.validate_a1_source_independent_bundle(
        contract=contract,
        bundle_dir=bundle_dir,
    )
    assert loaded.manifest is not None
    assert loaded.policy is not None
    source_audit = v1.validate_a1_source_independent_input(
        contract=contract,
        generation_root=generation_root,
        dataset_dir=dataset_dir,
    )
    manifest = v1.load_a1_source_independent_manifest(
        contract=contract,
        dataset_dir=dataset_dir,
    )
    configuration = A1AssignmentAwareConfig(
        **dict(loaded.manifest["configuration"])
    )
    normalization = loaded.manifest["normalization"]
    mean = np.asarray(normalization["mean"], dtype=np.float32)
    scale = np.asarray(normalization["scale"], dtype=np.float32)
    cell_by_seed = {
        seed: cell
        for cell in contract.cells
        for seed in cell.seed_values
    }
    rows = tuple(
        _evaluate_source_independent_frame_v2(
            record,
            configured_scenario_target_count=(
                cell_by_seed[int(record.seed)].configured_scenario_target_count
            ),
            configured_resource_count=(
                cell_by_seed[int(record.seed)].resource_count
            ),
            policy=loaded.policy,
            normalization_mean=mean,
            normalization_scale=scale,
            config=configuration,
            permissions=contract.permissions,
        )
        for record in iter_a1_source_independent_records_v2(
            contract=contract,
            dataset_dir=dataset_dir,
            manifest=manifest,
        )
    )
    aggregate = dict(
        v1.aggregate_a1_source_independent_rows(
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
                "v1_contract_sha256": contract_v1.contract_sha256,
            },
        )
    )
    aggregate["schema_version"] = A1_SOURCE_INDEPENDENT_AGGREGATE_SCHEMA_V2
    aggregate["status"] = (
        A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_V2_PASS
        if aggregate["machine_gate_passed"]
        else A1_SOURCE_INDEPENDENT_OUTPUT_STATUS_V2_FAIL
    )
    aggregate["output_identity"] = dict(contract.output_identity)
    aggregate["input_cardinality_semantics"] = {
        "configured_scenario_target_count": (
            "scenario_configuration_only"
        ),
        "observed_anonymous_target_count": (
            "dynamic_online_d1_d2_track_cardinality"
        ),
        "configured_resource_count": "exact_per_frame_requirement",
    }
    v1._write_evaluation_outputs(
        output,
        rows=rows,
        aggregate=aggregate,
        contract=contract,
    )
    return aggregate


def _evaluate_source_independent_frame_v2(
    record: LearningFrameRecord,
    *,
    configured_scenario_target_count: int,
    configured_resource_count: int,
    policy: Any,
    normalization_mean: np.ndarray,
    normalization_scale: np.ndarray,
    config: A1AssignmentAwareConfig,
    permissions: Mapping[str, bool],
) -> Mapping[str, Any]:
    row = dict(
        v1._evaluate_source_independent_frame(
            record,
            policy=policy,
            normalization_mean=normalization_mean,
            normalization_scale=normalization_scale,
            config=config,
            permissions=permissions,
        )
    )
    row["schema_version"] = A1_SOURCE_INDEPENDENT_FRAME_SCHEMA_V2
    row["input_cardinality"] = {
        "configured_scenario_target_count": int(
            configured_scenario_target_count
        ),
        "observed_anonymous_target_count": len(record.anonymous_targets),
        "configured_resource_count": int(configured_resource_count),
        "observed_anonymous_resource_count": len(
            record.anonymous_resources
        ),
        "rule_cost_matrix_shape": list(record.rule_cost_matrix.shape),
        "action_mask_shape": list(record.action_mask.shape),
        "candidate_edge_count": len(record.candidate_edge_indices),
        "target_demand_slot_count": len(record.target_demand_slots),
    }
    return row


def _repository_source_summary_v2(module_root: Path) -> Mapping[str, Any]:
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
                "simulations/run_a1_source_independent_evaluation_v2.py",
                f"configs/{v1.OFFICIAL_CONTRACT_FILENAME}",
                f"configs/{OFFICIAL_CONTRACT_FILENAME_V2}",
            ],
            cwd=module_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise v1.A1SourceIndependentEvaluationError(
            "repository_source_summary_failed"
        ) from error
    if len(commit) != 40:
        raise v1.A1SourceIndependentEvaluationError(
            "repository_commit_invalid"
        )
    return {
        "repository_git_commit": commit,
        "owned_source_dirty": bool(status),
    }


def _raise_frame_error(
    code: str,
    context: Mapping[str, Any],
    cause: Exception | None = None,
) -> None:
    error = v1.A1SourceIndependentEvaluationError(
        code,
        v1._canonical_json(context),
    )
    if cause is None:
        raise error
    raise error from cause


def _record_frame_context(
    record: LearningFrameRecord,
    *,
    line_number: int,
) -> Mapping[str, Any]:
    return {
        "line_number": int(line_number),
        "scenario": record.scenario_version,
        "seed": int(record.seed),
        "episode": record.episode,
        "frame": int(record.frame_index),
        "observed_anonymous_target_count": len(record.anonymous_targets),
        "observed_anonymous_resource_count": len(
            record.anonymous_resources
        ),
        "rule_cost_matrix_shape": list(record.rule_cost_matrix.shape),
        "action_mask_shape": list(record.action_mask.shape),
    }


def _raw_frame_context(
    value: Any,
    *,
    line_number: int,
) -> Mapping[str, Any]:
    item = value if isinstance(value, Mapping) else {}
    targets = item.get("anonymous_targets")
    resources = item.get("anonymous_resources")
    return {
        "line_number": int(line_number),
        "scenario": _safe_text(item.get("scenario_version")),
        "seed": _safe_integer(item.get("seed")),
        "episode": _safe_text(item.get("episode")),
        "frame": _safe_integer(item.get("frame_index")),
        "observed_anonymous_target_count": _safe_sequence_length(targets),
        "observed_anonymous_resource_count": _safe_sequence_length(resources),
        "rule_cost_matrix_shape": _raw_matrix_shape(
            item.get("rule_cost_matrix")
        ),
        "action_mask_shape": _raw_matrix_shape(item.get("action_mask")),
    }


def _raw_matrix_shape(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return {"rows": None, "column_counts": []}
    valid_rows = [
        row
        for row in value
        if isinstance(row, Sequence)
        and not isinstance(row, (str, bytes, bytearray))
    ]
    column_counts: list[int | None] = sorted(
        {len(row) for row in valid_rows}
    )
    if len(valid_rows) != len(value):
        column_counts.append(None)
    return {
        "rows": len(value),
        "column_counts": column_counts,
    }


def _safe_sequence_length(value: Any) -> int | None:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return None
    return len(value)


def _safe_integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
