"""Assignment-aware, development-only A1 cost-residual candidate.

The candidate in this module is deliberately isolated from the production
planner.  It learns bounded cost corrections, then delegates every discrete
decision to the existing Hungarian demand-slot solver.  Training consumes only
TRAIN frames and checkpoint selection consumes only VALIDATION frames.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
import base64
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import atanh, isfinite
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Protocol, Sequence

import numpy as np

from .learning import EDGE_FEATURE_NAMES, ResidualPrediction
from .learning_data import (
    DATASET_FRAMES_FILENAME,
    DATASET_MANIFEST_FILENAME,
    LEARNING_DATASET_SCHEMA_V2,
    LearningDatasetManifest,
    LearningFrameRecord,
)
from .native_ppo import nn, torch
from .solver import HungarianDemandSlotSolver


A1_ASSIGNMENT_AWARE_POLICY_VERSION_V1 = (
    "d3_a1_assignment_aware_cost_residual_policy_v1"
)
A1_ASSIGNMENT_AWARE_BUNDLE_SCHEMA_V1 = (
    "d3_a1_assignment_aware_development_bundle_v1"
)
A1_ASSIGNMENT_AWARE_TEACHER_SCHEMA_V1 = (
    "d3_a1_assignment_aware_continuity_teacher_v1"
)
A1_ASSIGNMENT_AWARE_EVALUATION_SCHEMA_V1 = (
    "d3_a1_assignment_aware_development_evaluation_v1"
)
A1_ASSIGNMENT_AWARE_BUILD_SCHEMA_V1 = (
    "d3_a1_assignment_aware_reproducible_build_v1"
)
A1_ASSIGNMENT_AWARE_LOADER_SCHEMA_V1 = (
    "d3_a1_assignment_aware_read_only_loader_v1"
)
A1_ASSIGNMENT_AWARE_SCOPE = (
    "development-shadow-only-train-validation-no-formal-holdout"
)
A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS = tuple(range(1000, 1020))
A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME = "manifest.json"
A1_ASSIGNMENT_AWARE_STATE_FILENAME = "state_dict.json"
A1_ASSIGNMENT_AWARE_CHECKSUM_FILENAME = "SHA256SUMS"
_BUNDLE_FILES = frozenset(
    {
        A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME,
        A1_ASSIGNMENT_AWARE_STATE_FILENAME,
        A1_ASSIGNMENT_AWARE_CHECKSUM_FILENAME,
    }
)


class A1AssignmentAwareContractError(ValueError):
    """Stable fail-closed error for the development candidate contract."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = str(code)
        super().__init__(self.code if message is None else f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class A1AssignmentAwareConfig:
    """Frozen development settings; none of these values grant authority."""

    alpha: float = 0.25
    residual_bound: float = 2.0
    hidden_size: int = 32
    epochs: int = 8
    mini_batch_frames: int = 8
    learning_rate: float = 8.0e-4
    seed: int = 20260730
    torch_num_threads: int = 4
    hard_negative_edges_per_target: int = 4
    maximum_sample_edges_per_frame: int = 2048
    maximum_previous_edge_candidates: int = 16
    correction_grid_fractions: tuple[float, ...] = (0.2, 0.4, 0.6, 0.8, 1.0)
    maximum_abs_cost_correction: float = 0.24
    maximum_binding_change_count: int = 8
    maximum_rule_cost_difference: float = 0.10
    maximum_relative_rule_cost_difference: float = 0.002
    minimum_negative_exact_r0_rate: float = 0.90
    ranking_margin: float = 0.01
    positive_gate_weight: float = 4.0
    nonzero_correction_weight: float = 64.0
    residual_loss_weight: float = 1.0
    ranking_loss_weight: float = 4.0
    selection_loss_weight: float = 0.15
    gate_loss_weight: float = 0.5
    ood_z_threshold: float = 12.0

    def __post_init__(self) -> None:
        finite_positive = (
            ("alpha", self.alpha),
            ("residual_bound", self.residual_bound),
            ("learning_rate", self.learning_rate),
            ("maximum_abs_cost_correction", self.maximum_abs_cost_correction),
            ("maximum_rule_cost_difference", self.maximum_rule_cost_difference),
            (
                "maximum_relative_rule_cost_difference",
                self.maximum_relative_rule_cost_difference,
            ),
            ("ranking_margin", self.ranking_margin),
            ("positive_gate_weight", self.positive_gate_weight),
            ("nonzero_correction_weight", self.nonzero_correction_weight),
            ("residual_loss_weight", self.residual_loss_weight),
            ("ranking_loss_weight", self.ranking_loss_weight),
            ("selection_loss_weight", self.selection_loss_weight),
            ("gate_loss_weight", self.gate_loss_weight),
            ("ood_z_threshold", self.ood_z_threshold),
        )
        for name, value in finite_positive:
            if not isfinite(float(value)) or float(value) <= 0.0:
                raise A1AssignmentAwareContractError(f"{name}_invalid")
        positive_ints = (
            ("hidden_size", self.hidden_size),
            ("epochs", self.epochs),
            ("mini_batch_frames", self.mini_batch_frames),
            ("torch_num_threads", self.torch_num_threads),
            (
                "hard_negative_edges_per_target",
                self.hard_negative_edges_per_target,
            ),
            (
                "maximum_sample_edges_per_frame",
                self.maximum_sample_edges_per_frame,
            ),
            (
                "maximum_previous_edge_candidates",
                self.maximum_previous_edge_candidates,
            ),
            (
                "maximum_binding_change_count",
                self.maximum_binding_change_count,
            ),
        )
        for name, value in positive_ints:
            if isinstance(value, bool) or int(value) < 1:
                raise A1AssignmentAwareContractError(f"{name}_invalid")
        fractions = tuple(float(value) for value in self.correction_grid_fractions)
        if (
            not fractions
            or fractions != tuple(sorted(set(fractions)))
            or any(not isfinite(value) or not 0.0 < value <= 1.0 for value in fractions)
        ):
            raise A1AssignmentAwareContractError(
                "correction_grid_fractions_invalid"
            )
        if not 0.0 <= float(self.minimum_negative_exact_r0_rate) <= 1.0:
            raise A1AssignmentAwareContractError(
                "minimum_negative_exact_r0_rate_invalid"
            )
        maximum_realized = float(self.alpha) * np.tanh(float(self.residual_bound))
        if self.maximum_abs_cost_correction > maximum_realized + 1.0e-12:
            raise A1AssignmentAwareContractError(
                "maximum_abs_cost_correction_exceeds_policy_bound"
            )
        object.__setattr__(self, "correction_grid_fractions", fractions)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["correction_grid_fractions"] = list(
            self.correction_grid_fractions
        )
        return payload


@dataclass(frozen=True, slots=True)
class A1SafeAssignmentOutcome:
    """One all-or-none projected solver result."""

    selected_edges: tuple[tuple[int, int], ...]
    objective_on_matrix: float
    objective_on_rule_matrix: float
    assigned_slot_count: int
    high_threat_assigned_slot_count: int
    duplicate_resource_count: int
    hard_edge_violation_count: int
    m_to_n_atomicity_violation_count: int
    churn: int
    removed_incomplete_target_count: int
    solver_name: str = "hungarian_demand_slots"

    @property
    def safety_violation_count(self) -> int:
        return (
            int(self.duplicate_resource_count)
            + int(self.hard_edge_violation_count)
            + int(self.m_to_n_atomicity_violation_count)
        )


class A1SafeAssignmentInput(Protocol):
    """Minimum anonymous frame surface consumed by the safety projection."""

    action_mask: np.ndarray
    rule_cost_matrix: np.ndarray
    target_demand_slots: Sequence[int]
    target_threat_scores: Sequence[float]
    unassigned_costs: np.ndarray
    previous_selected_edges: Sequence[tuple[int, int]]


@dataclass(frozen=True, slots=True)
class A1SafeAssignmentProjection:
    """First Hungarian proposal plus its all-or-none projected outcome."""

    pre_projection_edges: tuple[tuple[int, int], ...]
    outcome: A1SafeAssignmentOutcome


@dataclass(frozen=True, slots=True)
class A1AssignmentAwareTeacherFrame:
    """A deterministic development target derived without external holdout."""

    record: LearningFrameRecord
    r0: A1SafeAssignmentOutcome
    target: A1SafeAssignmentOutcome
    target_cost_corrections: np.ndarray
    sample_edge_offsets: np.ndarray
    promoted_edge_offset: int | None
    demoted_edge_offsets: tuple[int, ...]
    opportunity: bool
    reason: str
    correction_fraction: float
    maximum_abs_cost_correction: float
    binding_change_count: int
    rule_cost_difference: float
    relative_rule_cost_difference: float
    schema_version: str = A1_ASSIGNMENT_AWARE_TEACHER_SCHEMA_V1

    def __post_init__(self) -> None:
        corrections = np.asarray(
            self.target_cost_corrections, dtype=np.float32
        ).reshape(-1)
        offsets = np.asarray(self.sample_edge_offsets, dtype=np.int64).reshape(-1)
        if corrections.shape != (len(self.record.candidate_edge_indices),):
            raise A1AssignmentAwareContractError(
                "teacher_correction_shape_invalid"
            )
        if (
            len(offsets)
            and (
                int(np.min(offsets)) < 0
                or int(np.max(offsets)) >= len(self.record.candidate_edge_indices)
            )
        ):
            raise A1AssignmentAwareContractError("teacher_sample_offset_invalid")
        if len(offsets) != len(set(int(value) for value in offsets)):
            raise A1AssignmentAwareContractError(
                "teacher_sample_offset_duplicate"
            )
        if self.opportunity != (self.r0.selected_edges != self.target.selected_edges):
            raise A1AssignmentAwareContractError(
                "teacher_opportunity_binding_mismatch"
            )
        if self.opportunity and self.promoted_edge_offset is None:
            raise A1AssignmentAwareContractError(
                "teacher_promoted_edge_missing"
            )
        if not self.opportunity and np.any(corrections != 0.0):
            raise A1AssignmentAwareContractError(
                "negative_teacher_correction_nonzero"
            )
        if self.r0.safety_violation_count or self.target.safety_violation_count:
            raise A1AssignmentAwareContractError(
                "teacher_safety_violation"
            )
        object.__setattr__(self, "target_cost_corrections", corrections)
        object.__setattr__(self, "sample_edge_offsets", offsets)


@dataclass(frozen=True, slots=True)
class A1AssignmentAwareTrainingResult:
    """Training result with validation-only checkpoint selection."""

    selected_epoch: int
    development_gate_passed: bool
    selection_reason: str
    train_frame_count: int
    validation_frame_count: int
    train_opportunity_count: int
    validation_opportunity_count: int
    normalization_mean: tuple[float, ...]
    normalization_scale: tuple[float, ...]
    epoch_history: tuple[Mapping[str, Any], ...]
    final_train_metrics: Mapping[str, Any]
    selected_validation_metrics: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": A1_ASSIGNMENT_AWARE_BUILD_SCHEMA_V1,
            "training_kind": "assignment_aware_behavior_cloning",
            "checkpoint_selection_basis": (
                "validation_safe_discrete_binding_change_then_negative_exact_r0"
            ),
            "selected_epoch": int(self.selected_epoch),
            "development_gate_passed": bool(self.development_gate_passed),
            "selection_reason": str(self.selection_reason),
            "train_frame_count": int(self.train_frame_count),
            "validation_frame_count": int(self.validation_frame_count),
            "train_opportunity_count": int(self.train_opportunity_count),
            "validation_opportunity_count": int(
                self.validation_opportunity_count
            ),
            "normalization_mean": list(self.normalization_mean),
            "normalization_scale": list(self.normalization_scale),
            "epoch_history": [dict(value) for value in self.epoch_history],
            "final_train_metrics": dict(self.final_train_metrics),
            "selected_validation_metrics": dict(
                self.selected_validation_metrics
            ),
            "permissions": _closed_permissions(),
        }


@dataclass(frozen=True, slots=True)
class A1AssignmentAwareLoadResult:
    """Strict read-only candidate load result."""

    loaded: bool
    mode: str
    fallback_reason: str | None
    manifest: Mapping[str, Any] | None
    policy: Any | None
    manifest_sha256: str | None
    state_dict_sha256: str | None
    tree_sha256: str | None
    schema_version: str = A1_ASSIGNMENT_AWARE_LOADER_SCHEMA_V1

    @property
    def assist_authorized(self) -> bool:
        return False

    @property
    def authority_granted(self) -> bool:
        return False

    @property
    def production_admission_granted(self) -> bool:
        return False


if torch is not None and nn is not None:

    class A1AssignmentAwareResidualPolicy(nn.Module):
        """Shared-edge residual policy with a frame-level development gate."""

        policy_version = A1_ASSIGNMENT_AWARE_POLICY_VERSION_V1

        def __init__(
            self,
            *,
            feature_count: int = len(EDGE_FEATURE_NAMES),
            hidden_size: int = 32,
            residual_bound: float = 2.0,
            gate_threshold: float = 0.5,
        ) -> None:
            super().__init__()
            if feature_count != len(EDGE_FEATURE_NAMES):
                raise ValueError("feature_count does not match D3 edge schema")
            if hidden_size < 1 or residual_bound <= 0.0:
                raise ValueError("policy dimensions and residual bound must be positive")
            if not 0.0 < gate_threshold < 1.0:
                raise ValueError("gate_threshold must lie between zero and one")
            self.feature_count = int(feature_count)
            self.hidden_size = int(hidden_size)
            self.residual_bound = float(residual_bound)
            self.gate_threshold = float(gate_threshold)
            self.context_feature_count = self.feature_count * 4 + 8
            self.edge_encoder = nn.Sequential(
                nn.Linear(self.feature_count, self.hidden_size),
                nn.Tanh(),
                nn.Linear(self.hidden_size, self.hidden_size),
                nn.Tanh(),
            )
            self.context_encoder = nn.Sequential(
                nn.Linear(self.context_feature_count, self.hidden_size),
                nn.Tanh(),
            )
            self.residual_head = nn.Linear(self.hidden_size * 2, 1)
            self.selection_head = nn.Linear(self.hidden_size * 2, 1)
            self.gate_head = nn.Linear(self.hidden_size, 1)

        def forward(
            self,
            edge_features: Any,
            frame_context: Any,
        ) -> tuple[Any, Any, Any]:
            if edge_features.ndim != 2 or edge_features.shape[1] != self.feature_count:
                raise ValueError("edge_features have the wrong shape")
            context = frame_context.reshape(-1)
            if context.shape != (self.context_feature_count,):
                raise ValueError("frame_context has the wrong shape")
            edge_hidden = self.edge_encoder(edge_features)
            context_hidden = self.context_encoder(context)
            repeated = context_hidden.reshape(1, -1).expand(
                edge_hidden.shape[0], -1
            )
            fused = torch.cat((edge_hidden, repeated), dim=1)
            latent_residual = self.residual_head(fused).squeeze(-1)
            selection_logits = self.selection_head(fused).squeeze(-1)
            gate_logit = self.gate_head(context_hidden).reshape(())
            return latent_residual, selection_logits, gate_logit

        def predict(self, features: np.ndarray) -> ResidualPrediction:
            matrix = np.asarray(features, dtype=np.float32)
            if matrix.ndim != 2 or matrix.shape[1] != self.feature_count:
                raise ValueError("features have the wrong shared-edge shape")
            if not len(matrix):
                return ResidualPrediction(
                    delta_costs=np.empty(0, dtype=float),
                    confidence=np.empty(0, dtype=float),
                )
            device = next(self.parameters()).device
            context = _frame_context(matrix)
            self.eval()
            with torch.no_grad():
                edge_tensor = torch.as_tensor(
                    matrix, dtype=torch.float32, device=device
                )
                context_tensor = torch.as_tensor(
                    context, dtype=torch.float32, device=device
                )
                latent, _, gate_logit = self(edge_tensor, context_tensor)
                gate_probability = torch.sigmoid(gate_logit)
                gate_active = gate_probability >= self.gate_threshold
                residual = self.residual_bound * torch.tanh(latent)
                residual = torch.where(
                    gate_active, residual, torch.zeros_like(residual)
                )
                confidence = gate_probability.expand_as(residual)
            return ResidualPrediction(
                delta_costs=residual.cpu().numpy(),
                confidence=confidence.cpu().numpy(),
            )

else:

    class A1AssignmentAwareResidualPolicy:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            raise ImportError("PyTorch is required for the D3 A1 candidate")


def load_a1_development_records(
    dataset_dir: str | Path,
) -> tuple[
    LearningDatasetManifest,
    tuple[LearningFrameRecord, ...],
    Mapping[str, Any],
]:
    """Load only TRAIN/VALIDATION records and bind the untouched source bytes."""

    root = Path(dataset_dir)
    manifest_path = root / DATASET_MANIFEST_FILENAME
    frames_path = root / DATASET_FRAMES_FILENAME
    if not manifest_path.is_file() or not frames_path.is_file():
        raise A1AssignmentAwareContractError("development_dataset_file_missing")
    manifest_sha = _file_sha256(manifest_path)
    manifest = LearningDatasetManifest.from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    if manifest.schema_version != LEARNING_DATASET_SCHEMA_V2:
        raise A1AssignmentAwareContractError(
            "development_dataset_schema_unsupported"
        )
    actual_frames_sha = _file_sha256(frames_path)
    if actual_frames_sha != manifest.frames_sha256:
        raise A1AssignmentAwareContractError(
            "development_dataset_frames_sha256_mismatch"
        )
    allowed_seed_values = {
        split: frozenset(int(value) for value in manifest.split_seed_values[split])
        for split in ("train", "validation")
    }
    consumed: list[LearningFrameRecord] = []
    consumed_seed_values: dict[str, set[int]] = {
        "train": set(),
        "validation": set(),
    }
    raw_test_line_count = 0
    with frames_path.open("rb") as handle:
        for line in handle:
            has_train = b'"split":"train"' in line
            has_validation = b'"split":"validation"' in line
            has_test = b'"split":"test"' in line
            if sum((has_train, has_validation, has_test)) != 1:
                raise A1AssignmentAwareContractError(
                    "development_dataset_split_marker_invalid"
                )
            if has_test:
                raw_test_line_count += 1
                continue
            split = "train" if has_train else "validation"
            record = LearningFrameRecord.from_json_line(line)
            if record.split != split:
                raise A1AssignmentAwareContractError(
                    "development_dataset_split_parse_mismatch"
                )
            if record.seed not in allowed_seed_values[split]:
                raise A1AssignmentAwareContractError(
                    "development_dataset_seed_manifest_mismatch"
                )
            if record.seed in A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS:
                raise A1AssignmentAwareContractError(
                    "formal_holdout_seed_consumption_forbidden"
                )
            consumed.append(record)
            consumed_seed_values[split].add(record.seed)
    if not consumed or not consumed_seed_values["train"] or not consumed_seed_values[
        "validation"
    ]:
        raise A1AssignmentAwareContractError(
            "development_train_validation_empty"
        )
    if consumed_seed_values["train"] & consumed_seed_values["validation"]:
        raise A1AssignmentAwareContractError(
            "development_train_validation_seed_leakage"
        )
    expected_counts = manifest.split_frame_counts
    actual_counts = Counter(item.split for item in consumed)
    if any(
        int(actual_counts[split]) != int(expected_counts[split])
        for split in ("train", "validation")
    ):
        raise A1AssignmentAwareContractError(
            "development_split_frame_count_mismatch"
        )
    source = {
        "dataset_schema_version": manifest.schema_version,
        "dataset_manifest_sha256": manifest_sha,
        "dataset_frames_sha256": actual_frames_sha,
        "dataset_split_hash": manifest.split_hash,
        "split_policy_version": manifest.split_policy_version,
        "consumed_splits": ["train", "validation"],
        "optimizer_consumed_splits": ["train"],
        "checkpoint_selection_consumed_splits": ["validation"],
        "train_seed_values": sorted(consumed_seed_values["train"]),
        "validation_seed_values": sorted(consumed_seed_values["validation"]),
        "parsed_test_frame_count": 0,
        "skipped_raw_test_line_count": int(raw_test_line_count),
        "formal_holdout_seed_values": list(
            A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS
        ),
        "formal_holdout_read_count": 0,
        "formal_holdout_status": "not_read_not_evaluated",
    }
    return manifest, tuple(consumed), source


def solve_a1_safe_assignment(
    record: A1SafeAssignmentInput,
    matrix: np.ndarray,
) -> A1SafeAssignmentOutcome:
    """Solve one frame and project every incomplete M-to-N target to zero."""

    return project_a1_safe_assignment(record, matrix).outcome


def project_a1_safe_assignment(
    record: A1SafeAssignmentInput,
    matrix: np.ndarray,
) -> A1SafeAssignmentProjection:
    """Return the initial demand-slot proposal and all-or-none projection."""

    candidate_matrix = np.asarray(matrix, dtype=float)
    if candidate_matrix.shape != record.rule_cost_matrix.shape:
        raise A1AssignmentAwareContractError("solver_matrix_shape_mismatch")
    if not np.all(np.isfinite(candidate_matrix)):
        raise A1AssignmentAwareContractError("solver_matrix_non_finite")
    demand = np.maximum(
        1, np.asarray(record.target_demand_slots, dtype=int).reshape(-1)
    )
    threat = np.asarray(record.target_threat_scores, dtype=float).reshape(-1)
    active_targets = set(range(len(demand)))
    solver = HungarianDemandSlotSolver()
    selected_edges: tuple[tuple[int, int], ...] = ()
    pre_projection_edges: tuple[tuple[int, int], ...] | None = None
    objective_on_matrix = 0.0
    removed_count = 0
    while active_targets:
        slot_targets = [
            target_index
            for target_index in sorted(active_targets)
            for _ in range(int(demand[target_index]))
        ]
        slot_index = np.asarray(slot_targets, dtype=int)
        result = solver.solve(
            candidate_matrix[slot_index, :],
            record.unassigned_costs[slot_index],
            candidate_mask=record.action_mask[slot_index, :],
        )
        proposed = tuple(
            sorted(
                {
                    (
                        int(slot_targets[item.target_index]),
                        int(item.resource_index),
                    )
                    for item in result.assignments
                }
            )
        )
        if pre_projection_edges is None:
            pre_projection_edges = proposed
        assigned_by_target = Counter(row for row, _ in proposed)
        incomplete = [
            target_index
            for target_index in active_targets
            if assigned_by_target[target_index] < int(demand[target_index])
        ]
        if not incomplete:
            selected_edges = proposed
            objective_on_matrix = float(result.objective_value)
            break
        victim = min(
            incomplete,
            key=lambda target_index: (
                float(threat[target_index]),
                int(target_index),
            ),
        )
        active_targets.remove(victim)
        removed_count += 1

    assigned_by_target = Counter(row for row, _ in selected_edges)
    resources = [column for _, column in selected_edges]
    hard_violations = sum(
        not bool(record.action_mask[row, column])
        for row, column in selected_edges
    )
    atomicity_violations = sum(
        assigned_by_target[index] not in (0, int(required))
        for index, required in enumerate(demand)
    )
    objective_on_rule = sum(
        float(record.rule_cost_matrix[row, column])
        for row, column in selected_edges
    ) + sum(
        max(0, int(required) - assigned_by_target[index])
        * float(record.unassigned_costs[index])
        for index, required in enumerate(demand)
    )
    if not active_targets:
        objective_on_matrix = sum(
            int(required) * float(record.unassigned_costs[index])
            for index, required in enumerate(demand)
        )
    high_threat_rows = {
        index
        for index, score in enumerate(record.target_threat_scores)
        if float(score) >= 0.7
    }
    return A1SafeAssignmentProjection(
        pre_projection_edges=(
            () if pre_projection_edges is None else pre_projection_edges
        ),
        outcome=A1SafeAssignmentOutcome(
            selected_edges=selected_edges,
            objective_on_matrix=float(objective_on_matrix),
            objective_on_rule_matrix=float(objective_on_rule),
            assigned_slot_count=len(selected_edges),
            high_threat_assigned_slot_count=sum(
                assigned_by_target[index] for index in high_threat_rows
            ),
            duplicate_resource_count=len(resources) - len(set(resources)),
            hard_edge_violation_count=int(hard_violations),
            m_to_n_atomicity_violation_count=int(atomicity_violations),
            churn=len(
                set(selected_edges).symmetric_difference(
                    record.previous_selected_edges
                )
            ),
            removed_incomplete_target_count=int(removed_count),
        ),
    )


def build_a1_assignment_aware_teachers(
    records: Iterable[LearningFrameRecord],
    *,
    config: A1AssignmentAwareConfig = A1AssignmentAwareConfig(),
) -> tuple[A1AssignmentAwareTeacherFrame, ...]:
    """Build continuity-aware hard alternatives for TRAIN/VALIDATION only."""

    items = tuple(records)
    if not items:
        raise A1AssignmentAwareContractError("teacher_records_empty")
    if any(item.split not in {"train", "validation"} for item in items):
        raise A1AssignmentAwareContractError(
            "teacher_non_development_split_forbidden"
        )
    if any(item.seed in A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS for item in items):
        raise A1AssignmentAwareContractError(
            "teacher_formal_holdout_seed_forbidden"
        )
    output = [
        _build_teacher_frame(record, config)
        for record in sorted(
            items,
            key=lambda value: (
                value.split,
                value.scenario_version,
                value.seed,
                value.episode,
                value.frame_index,
            ),
        )
    ]
    return tuple(output)


def train_a1_assignment_aware_candidate(
    teachers: Iterable[A1AssignmentAwareTeacherFrame],
    *,
    config: A1AssignmentAwareConfig = A1AssignmentAwareConfig(),
) -> tuple[A1AssignmentAwareResidualPolicy, A1AssignmentAwareTrainingResult]:
    """Train on TRAIN and select a checkpoint only from VALIDATION outcomes."""

    if torch is None or nn is None:  # pragma: no cover
        raise ImportError("PyTorch is required for the D3 A1 candidate")
    items = tuple(teachers)
    train_items = tuple(item for item in items if item.record.split == "train")
    validation_items = tuple(
        item for item in items if item.record.split == "validation"
    )
    if not train_items or not validation_items:
        raise A1AssignmentAwareContractError(
            "training_requires_train_and_validation"
        )
    train_seeds = {item.record.seed for item in train_items}
    validation_seeds = {item.record.seed for item in validation_items}
    if train_seeds & validation_seeds:
        raise A1AssignmentAwareContractError(
            "training_validation_seed_leakage"
        )
    if any(
        item.record.seed in A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS
        for item in items
    ):
        raise A1AssignmentAwareContractError(
            "training_formal_holdout_seed_forbidden"
        )

    torch.manual_seed(int(config.seed))
    torch.set_num_threads(int(config.torch_num_threads))
    torch.use_deterministic_algorithms(True)
    rng = np.random.default_rng(int(config.seed))
    mean, scale = _fit_normalization(train_items)
    policy = A1AssignmentAwareResidualPolicy(
        hidden_size=config.hidden_size,
        residual_bound=config.residual_bound,
    )
    optimizer = torch.optim.Adam(policy.parameters(), lr=config.learning_rate)
    epoch_history: list[Mapping[str, Any]] = []
    checkpoints: dict[int, OrderedDict[str, Any]] = {}

    initial_validation = evaluate_a1_assignment_aware_candidate(
        validation_items,
        policy,
        normalization_mean=mean,
        normalization_scale=scale,
        config=config,
        evidence_scope="development_validation_checkpoint_0",
    )
    checkpoints[0] = _cpu_state_dict(policy)
    epoch_history.append(
        {
            "epoch": 0,
            "train_loss_mean": None,
            "validation": initial_validation,
        }
    )

    for epoch in range(1, int(config.epochs) + 1):
        policy.train()
        order = rng.permutation(len(train_items))
        losses: list[float] = []
        for start in range(0, len(train_items), config.mini_batch_frames):
            batch = tuple(
                train_items[int(index)]
                for index in order[start : start + config.mini_batch_frames]
            )
            optimizer.zero_grad()
            loss = _assignment_aware_batch_loss(
                policy,
                batch,
                mean=mean,
                scale=scale,
                config=config,
            )
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()
            losses.append(float(loss.detach().cpu().item()))
        validation = evaluate_a1_assignment_aware_candidate(
            validation_items,
            policy,
            normalization_mean=mean,
            normalization_scale=scale,
            config=config,
            evidence_scope=f"development_validation_checkpoint_{epoch}",
        )
        checkpoints[epoch] = _cpu_state_dict(policy)
        epoch_history.append(
            {
                "epoch": int(epoch),
                "train_loss_mean": float(np.mean(losses)),
                "validation": validation,
            }
        )

    selected_epoch, selection_reason, gate_passed = _select_checkpoint(
        epoch_history,
        config=config,
    )
    policy.load_state_dict(checkpoints[selected_epoch], strict=True)
    final_train = evaluate_a1_assignment_aware_candidate(
        train_items,
        policy,
        normalization_mean=mean,
        normalization_scale=scale,
        config=config,
        evidence_scope="development_train_post_selection_not_checkpoint_selection",
    )
    selected_validation = dict(epoch_history[selected_epoch]["validation"])
    result = A1AssignmentAwareTrainingResult(
        selected_epoch=int(selected_epoch),
        development_gate_passed=bool(gate_passed),
        selection_reason=selection_reason,
        train_frame_count=len(train_items),
        validation_frame_count=len(validation_items),
        train_opportunity_count=sum(item.opportunity for item in train_items),
        validation_opportunity_count=sum(
            item.opportunity for item in validation_items
        ),
        normalization_mean=tuple(float(value) for value in mean),
        normalization_scale=tuple(float(value) for value in scale),
        epoch_history=tuple(epoch_history),
        final_train_metrics=final_train,
        selected_validation_metrics=selected_validation,
    )
    return policy, result


def evaluate_a1_assignment_aware_candidate(
    teachers: Iterable[A1AssignmentAwareTeacherFrame],
    policy: A1AssignmentAwareResidualPolicy,
    *,
    normalization_mean: Sequence[float],
    normalization_scale: Sequence[float],
    config: A1AssignmentAwareConfig = A1AssignmentAwareConfig(),
    evidence_scope: str,
) -> dict[str, Any]:
    """Evaluate discrete safe outcomes without granting any runtime permission."""

    items = tuple(teachers)
    if not items:
        raise A1AssignmentAwareContractError("evaluation_frames_empty")
    splits = {item.record.split for item in items}
    if len(splits) != 1 or not splits <= {"train", "validation"}:
        raise A1AssignmentAwareContractError(
            "evaluation_requires_one_development_split"
        )
    if any(
        item.record.seed in A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS
        for item in items
    ):
        raise A1AssignmentAwareContractError(
            "evaluation_formal_holdout_seed_forbidden"
        )
    mean = np.asarray(normalization_mean, dtype=np.float32).reshape(-1)
    scale = np.asarray(normalization_scale, dtype=np.float32).reshape(-1)
    if mean.shape != (len(EDGE_FEATURE_NAMES),) or scale.shape != mean.shape:
        raise A1AssignmentAwareContractError(
            "evaluation_normalization_shape_invalid"
        )
    if np.any(scale <= 0.0) or not np.all(np.isfinite(mean)) or not np.all(
        np.isfinite(scale)
    ):
        raise A1AssignmentAwareContractError(
            "evaluation_normalization_invalid"
        )

    counters: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    binding_change_counts: list[int] = []
    maximum_corrections: list[float] = []
    for teacher in items:
        record = teacher.record
        rule_matrix_before = np.asarray(
            record.rule_cost_matrix, dtype=float
        ).copy()
        normalized = (
            np.asarray(record.candidate_features, dtype=np.float32) - mean
        ) / scale
        if _is_ood(normalized, config.ood_z_threshold):
            residual = np.zeros(
                len(record.candidate_edge_indices), dtype=float
            )
            fallback_reason = "feature_ood"
        else:
            prediction = policy.predict(normalized)
            residual = np.asarray(prediction.delta_costs, dtype=float)
            fallback_reason = None
        correction = config.alpha * np.tanh(residual)
        maximum_correction = float(
            np.max(np.abs(correction)) if len(correction) else 0.0
        )
        maximum_corrections.append(maximum_correction)
        if maximum_correction > config.maximum_abs_cost_correction + 1.0e-12:
            fallback_reason = "cost_correction_bound_exceeded"
        proposal_matrix = rule_matrix_before.copy()
        if fallback_reason is None:
            for offset, edge in enumerate(record.candidate_edge_indices):
                proposal_matrix[edge] += float(correction[offset])
        proposal = solve_a1_safe_assignment(record, proposal_matrix)
        binding_change_count = len(
            set(proposal.selected_edges).symmetric_difference(
                teacher.r0.selected_edges
            )
        )
        raw_cost_difference = (
            proposal.objective_on_rule_matrix
            - teacher.r0.objective_on_rule_matrix
        )
        relative_difference = max(0.0, raw_cost_difference) / max(
            abs(teacher.r0.objective_on_rule_matrix), 1.0e-12
        )
        safety_reasons: list[str] = []
        if proposal.safety_violation_count:
            safety_reasons.append("projected_safety_violation")
        if (
            proposal.assigned_slot_count < teacher.r0.assigned_slot_count
            or proposal.high_threat_assigned_slot_count
            < teacher.r0.high_threat_assigned_slot_count
        ):
            safety_reasons.append("demand_coverage_degraded")
        if binding_change_count > config.maximum_binding_change_count:
            safety_reasons.append("binding_change_limit_exceeded")
        if raw_cost_difference > config.maximum_rule_cost_difference + 1.0e-12:
            safety_reasons.append("rule_cost_difference_exceeded")
        if (
            relative_difference
            > config.maximum_relative_rule_cost_difference + 1.0e-12
        ):
            safety_reasons.append("relative_rule_cost_difference_exceeded")
        if fallback_reason is not None:
            safety_reasons.append(fallback_reason)

        if safety_reasons:
            effective = teacher.r0
            effective_matrix = rule_matrix_before.copy()
            counters["projection_rejection_count"] += 1
            for reason in safety_reasons:
                reason_counts[reason] += 1
        else:
            effective = proposal
            effective_matrix = proposal_matrix
        effective_change_count = len(
            set(effective.selected_edges).symmetric_difference(
                teacher.r0.selected_edges
            )
        )
        binding_change_counts.append(effective_change_count)
        exact_r0 = effective.selected_edges == teacher.r0.selected_edges
        if maximum_correction > 1.0e-12:
            counters["nonzero_cost_correction_frame_count"] += 1
        if effective_change_count:
            counters["safe_binding_change_frame_count"] += 1
        if teacher.opportunity:
            counters["positive_frame_count"] += 1
            if effective_change_count:
                counters["positive_safe_binding_change_frame_count"] += 1
            if effective.selected_edges == teacher.target.selected_edges:
                counters["positive_teacher_exact_match_count"] += 1
        else:
            counters["negative_frame_count"] += 1
            if exact_r0:
                counters["negative_exact_r0_count"] += 1
        counters["duplicate_resource_count"] += (
            effective.duplicate_resource_count
        )
        counters["hard_edge_violation_count"] += (
            effective.hard_edge_violation_count
        )
        counters["m_to_n_atomicity_violation_count"] += (
            effective.m_to_n_atomicity_violation_count
        )
        counters["version_violation_count"] += 0
        counters["model_plan_version_output_count"] += 0
        counters["r0_rule_matrix_mutation_count"] += int(
            not np.array_equal(rule_matrix_before, record.rule_cost_matrix)
        )
        if safety_reasons:
            counters["fallback_frame_count"] += 1
            counters["fallback_exact_r0_matrix_count"] += int(
                np.array_equal(effective_matrix, rule_matrix_before)
            )
            counters["fallback_exact_r0_binding_count"] += int(exact_r0)

    negative_count = counters["negative_frame_count"]
    positive_count = counters["positive_frame_count"]
    fallback_count = counters["fallback_frame_count"]
    negative_exact_rate = (
        1.0
        if negative_count == 0
        else counters["negative_exact_r0_count"] / negative_count
    )
    safety_total = (
        counters["duplicate_resource_count"]
        + counters["hard_edge_violation_count"]
        + counters["m_to_n_atomicity_violation_count"]
        + counters["version_violation_count"]
    )
    machine_gate = {
        "nonzero_cost_correction": (
            counters["nonzero_cost_correction_frame_count"] > 0
        ),
        "nonzero_safe_binding_change": (
            counters["safe_binding_change_frame_count"] > 0
        ),
        "zero_duplicate_resource": counters["duplicate_resource_count"] == 0,
        "zero_hard_edge_violation": counters["hard_edge_violation_count"] == 0,
        "zero_m_to_n_atomicity_violation": (
            counters["m_to_n_atomicity_violation_count"] == 0
        ),
        "zero_version_violation": counters["version_violation_count"] == 0,
        "model_does_not_output_plan_version": (
            counters["model_plan_version_output_count"] == 0
        ),
        "r0_raw_rule_matrix_immutable": (
            counters["r0_rule_matrix_mutation_count"] == 0
        ),
        "fallback_matrix_exact_r0": (
            fallback_count
            == counters["fallback_exact_r0_matrix_count"]
        ),
        "fallback_binding_exact_r0": (
            fallback_count
            == counters["fallback_exact_r0_binding_count"]
        ),
        "negative_exact_r0_rate_passed": (
            negative_exact_rate + 1.0e-12
            >= config.minimum_negative_exact_r0_rate
        ),
        "effective_safety_violation_count_zero": safety_total == 0,
    }
    return {
        "schema_version": A1_ASSIGNMENT_AWARE_EVALUATION_SCHEMA_V1,
        "scope": A1_ASSIGNMENT_AWARE_SCOPE,
        "evidence_scope": str(evidence_scope),
        "split": next(iter(splits)),
        "frame_count": len(items),
        "positive_frame_count": int(positive_count),
        "negative_frame_count": int(negative_count),
        "nonzero_cost_correction_frame_count": int(
            counters["nonzero_cost_correction_frame_count"]
        ),
        "safe_binding_change_frame_count": int(
            counters["safe_binding_change_frame_count"]
        ),
        "positive_safe_binding_change_frame_count": int(
            counters["positive_safe_binding_change_frame_count"]
        ),
        "positive_teacher_exact_match_count": int(
            counters["positive_teacher_exact_match_count"]
        ),
        "negative_exact_r0_count": int(counters["negative_exact_r0_count"]),
        "negative_exact_r0_rate": float(negative_exact_rate),
        "projection_rejection_count": int(
            counters["projection_rejection_count"]
        ),
        "projection_rejection_reason_counts": dict(sorted(reason_counts.items())),
        "fallback_frame_count": int(fallback_count),
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
        "version_violation_count": int(counters["version_violation_count"]),
        "model_plan_version_output_count": int(
            counters["model_plan_version_output_count"]
        ),
        "r0_rule_matrix_mutation_count": int(
            counters["r0_rule_matrix_mutation_count"]
        ),
        "maximum_abs_cost_correction": float(
            max(maximum_corrections, default=0.0)
        ),
        "binding_change_count_max": int(
            max(binding_change_counts, default=0)
        ),
        "machine_gate": machine_gate,
        "machine_gate_passed": all(machine_gate.values()),
        "permissions": _closed_permissions(),
        "formal_holdout": {
            "seed_values": list(A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS),
            "read_count": 0,
            "status": "not_read_not_evaluated",
        },
    }


def freeze_a1_assignment_aware_bundle(
    bundle_dir: str | Path,
    policy: A1AssignmentAwareResidualPolicy,
    training_result: A1AssignmentAwareTrainingResult,
    *,
    config: A1AssignmentAwareConfig,
    source_dataset: Mapping[str, Any],
    source_tree_sha256: str,
    repository_git_commit: str,
    build_date: str = "2026-07-30",
) -> Mapping[str, Any]:
    """Write one immutable development/shadow bundle with closed permissions."""

    if torch is None:  # pragma: no cover
        raise ImportError("PyTorch is required for the D3 A1 candidate")
    root = Path(bundle_dir)
    if root.exists() and any(root.iterdir()):
        raise A1AssignmentAwareContractError("bundle_directory_not_empty")
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / A1_ASSIGNMENT_AWARE_STATE_FILENAME
    state_dict = _cpu_state_dict(policy)
    _write_canonical_state_dict(state_path, state_dict)
    state_sha = _file_sha256(state_path)
    manifest = {
        "bundle_schema_version": A1_ASSIGNMENT_AWARE_BUNDLE_SCHEMA_V1,
        "policy_version": A1_ASSIGNMENT_AWARE_POLICY_VERSION_V1,
        "scope": A1_ASSIGNMENT_AWARE_SCOPE,
        "stage": "development",
        "allowed_modes": ["shadow", "source_independent_evaluation"],
        "feature_schema_version": "d3_shared_edge_residual_v1",
        "feature_names": list(EDGE_FEATURE_NAMES),
        "model_config": {
            "feature_count": len(EDGE_FEATURE_NAMES),
            "context_feature_count": len(EDGE_FEATURE_NAMES) * 4 + 8,
            "hidden_size": policy.hidden_size,
            "residual_bound": policy.residual_bound,
            "frame_gate_threshold": policy.gate_threshold,
            "assignment_output": False,
            "plan_version_output": False,
            "cost_correction_formula": (
                "C_final=C_rule+alpha*tanh(delta_C)"
            ),
        },
        "configuration": config.to_dict(),
        "normalization": {
            "mean": list(training_result.normalization_mean),
            "scale": list(training_result.normalization_scale),
            "fit_split": "train",
        },
        "source_dataset": dict(source_dataset),
        "training": {
            "optimizer_consumed_split": "train",
            "checkpoint_selection_consumed_split": "validation",
            "selected_epoch": training_result.selected_epoch,
            "development_gate_passed": (
                training_result.development_gate_passed
            ),
            "selection_reason": training_result.selection_reason,
            "train_frame_count": training_result.train_frame_count,
            "validation_frame_count": training_result.validation_frame_count,
            "train_opportunity_count": (
                training_result.train_opportunity_count
            ),
            "validation_opportunity_count": (
                training_result.validation_opportunity_count
            ),
            "selected_validation_metrics": dict(
                training_result.selected_validation_metrics
            ),
            "final_train_metrics": dict(
                training_result.final_train_metrics
            ),
        },
        "state_dict": {
            "file": A1_ASSIGNMENT_AWARE_STATE_FILENAME,
            "sha256": state_sha,
            "load_policy": "canonical_json_base64_tensor_v1",
        },
        "provenance": {
            "repository_git_commit": _git_sha(repository_git_commit),
            "source_tree_sha256": _sha256_text(source_tree_sha256),
            "build_date": str(build_date),
            "worktree_role": (
                "d3_owned_source_tree_sha256_bound_pending_main_commit"
            ),
        },
        "admission": {
            "status": "development_shadow_only",
            "production_bundle": False,
            "admitted_bundle": False,
            "formal_holdout_status": "not_read_not_evaluated",
            "formal_holdout_seed_values": list(
                A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS
            ),
        },
        "permissions": _closed_permissions(),
        "fallback": {
            "required": True,
            "matrix_policy": "elementwise_exact_raw_rule_cost_matrix",
            "binding_policy": "deterministic_r0_replay",
        },
    }
    manifest_path = root / A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME
    manifest_path.write_text(
        _canonical_json(manifest) + "\n",
        encoding="utf-8",
    )
    checksums = {
        A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME: _file_sha256(manifest_path),
        A1_ASSIGNMENT_AWARE_STATE_FILENAME: state_sha,
    }
    (root / A1_ASSIGNMENT_AWARE_CHECKSUM_FILENAME).write_text(
        "".join(
            f"{digest}  {name}\n"
            for name, digest in sorted(checksums.items())
        ),
        encoding="ascii",
    )
    return {
        "manifest": manifest,
        "manifest_sha256": checksums[
            A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME
        ],
        "state_dict_sha256": state_sha,
        "tree_sha256": a1_assignment_aware_bundle_tree_sha256(root),
    }


def load_a1_assignment_aware_bundle(
    bundle_dir: str | Path,
    *,
    mode: str = "shadow",
    expected_manifest_sha256: str | None = None,
    expected_tree_sha256: str | None = None,
) -> A1AssignmentAwareLoadResult:
    """Load the candidate read-only; assist/authority modes always fail closed."""

    requested_mode = str(mode).strip()
    if requested_mode not in {"shadow", "source_independent_evaluation"}:
        return A1AssignmentAwareLoadResult(
            loaded=False,
            mode=requested_mode,
            fallback_reason="assignment_aware_bundle_mode_forbidden",
            manifest=None,
            policy=None,
            manifest_sha256=None,
            state_dict_sha256=None,
            tree_sha256=None,
        )
    try:
        root = Path(bundle_dir)
        if not root.is_dir() or root.is_symlink():
            raise A1AssignmentAwareContractError("bundle_directory_invalid")
        files = {path.name for path in root.iterdir()}
        if files != _BUNDLE_FILES:
            raise A1AssignmentAwareContractError("bundle_file_set_mismatch")
        if any(path.is_symlink() or not path.is_file() for path in root.iterdir()):
            raise A1AssignmentAwareContractError("bundle_symlink_forbidden")
        checksums = _read_checksums(
            root / A1_ASSIGNMENT_AWARE_CHECKSUM_FILENAME
        )
        if set(checksums) != {
            A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME,
            A1_ASSIGNMENT_AWARE_STATE_FILENAME,
        }:
            raise A1AssignmentAwareContractError(
                "bundle_checksum_inventory_mismatch"
            )
        for filename, digest in checksums.items():
            if _file_sha256(root / filename) != digest:
                raise A1AssignmentAwareContractError(
                    "bundle_file_sha256_mismatch"
                )
        manifest_sha = checksums[A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME]
        tree_sha = a1_assignment_aware_bundle_tree_sha256(root)
        if (
            expected_manifest_sha256 is not None
            and manifest_sha != _sha256_text(expected_manifest_sha256)
        ):
            raise A1AssignmentAwareContractError(
                "bundle_expected_manifest_sha256_mismatch"
            )
        if (
            expected_tree_sha256 is not None
            and tree_sha != _sha256_text(expected_tree_sha256)
        ):
            raise A1AssignmentAwareContractError(
                "bundle_expected_tree_sha256_mismatch"
            )
        manifest = json.loads(
            (root / A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        _validate_assignment_aware_manifest(manifest)
        if manifest["state_dict"]["sha256"] != checksums[
            A1_ASSIGNMENT_AWARE_STATE_FILENAME
        ]:
            raise A1AssignmentAwareContractError(
                "bundle_state_manifest_sha256_mismatch"
            )
        model_config = manifest["model_config"]
        policy = A1AssignmentAwareResidualPolicy(
            feature_count=int(model_config["feature_count"]),
            hidden_size=int(model_config["hidden_size"]),
            residual_bound=float(model_config["residual_bound"]),
            gate_threshold=float(model_config["frame_gate_threshold"]),
        )
        state = _read_canonical_state_dict(
            root / A1_ASSIGNMENT_AWARE_STATE_FILENAME
        )
        policy.load_state_dict(state, strict=True)
        policy.eval()
        return A1AssignmentAwareLoadResult(
            loaded=True,
            mode=requested_mode,
            fallback_reason=None,
            manifest=manifest,
            policy=policy,
            manifest_sha256=manifest_sha,
            state_dict_sha256=checksums[
                A1_ASSIGNMENT_AWARE_STATE_FILENAME
            ],
            tree_sha256=tree_sha,
        )
    except (
        A1AssignmentAwareContractError,
        FileNotFoundError,
        json.JSONDecodeError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        reason = (
            error.code
            if isinstance(error, A1AssignmentAwareContractError)
            else "assignment_aware_bundle_invalid"
        )
        return A1AssignmentAwareLoadResult(
            loaded=False,
            mode=requested_mode,
            fallback_reason=reason,
            manifest=None,
            policy=None,
            manifest_sha256=None,
            state_dict_sha256=None,
            tree_sha256=None,
        )


def a1_assignment_aware_bundle_tree_sha256(bundle_dir: str | Path) -> str:
    """Return a path-independent digest over manifest and model bytes."""

    root = Path(bundle_dir)
    entries = []
    for filename in (
        A1_ASSIGNMENT_AWARE_MANIFEST_FILENAME,
        A1_ASSIGNMENT_AWARE_STATE_FILENAME,
    ):
        entries.append(f"{filename}:{_file_sha256(root / filename)}")
    return sha256(("\n".join(entries) + "\n").encode("ascii")).hexdigest()


def write_a1_assignment_aware_development_output(
    output_dir: str | Path,
    *,
    bundle_a: Mapping[str, Any],
    bundle_b: Mapping[str, Any],
    training_result: A1AssignmentAwareTrainingResult,
    teacher_summary: Mapping[str, Any],
    source_dataset: Mapping[str, Any],
    config: A1AssignmentAwareConfig,
) -> Mapping[str, Any]:
    """Write deterministic development evidence outside the strict bundles."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    reproducible = all(
        bundle_a[key] == bundle_b[key]
        for key in (
            "manifest_sha256",
            "state_dict_sha256",
            "tree_sha256",
        )
    )
    comparison = {
        "schema_version": A1_ASSIGNMENT_AWARE_BUILD_SCHEMA_V1,
        "scope": A1_ASSIGNMENT_AWARE_SCOPE,
        "build_a": {
            key: bundle_a[key]
            for key in (
                "manifest_sha256",
                "state_dict_sha256",
                "tree_sha256",
            )
        },
        "build_b": {
            key: bundle_b[key]
            for key in (
                "manifest_sha256",
                "state_dict_sha256",
                "tree_sha256",
            )
        },
        "byte_reproducible": bool(reproducible),
        "formal_holdout_read_count": 0,
        "permissions": _closed_permissions(),
    }
    artifacts = {
        "reproducibility.json": comparison,
        "teacher_summary.json": dict(teacher_summary),
        "training_result.json": training_result.to_dict(),
        "source_dataset.json": dict(source_dataset),
        "configuration.json": config.to_dict(),
    }
    for filename, payload in artifacts.items():
        (root / filename).write_text(
            _canonical_json(payload) + "\n",
            encoding="utf-8",
        )
    checksums = {
        filename: _file_sha256(root / filename)
        for filename in artifacts
    }
    (root / "ARTIFACT_SHA256SUMS").write_text(
        "".join(
            f"{digest}  {filename}\n"
            for filename, digest in sorted(checksums.items())
        ),
        encoding="ascii",
    )
    return comparison


def summarize_a1_assignment_aware_teachers(
    teachers: Iterable[A1AssignmentAwareTeacherFrame],
) -> Mapping[str, Any]:
    items = tuple(teachers)
    split_rows: dict[str, dict[str, Any]] = {}
    for split in ("train", "validation"):
        rows = tuple(item for item in items if item.record.split == split)
        reasons = Counter(item.reason for item in rows)
        split_rows[split] = {
            "frame_count": len(rows),
            "opportunity_count": sum(item.opportunity for item in rows),
            "negative_count": sum(not item.opportunity for item in rows),
            "reason_counts": dict(sorted(reasons.items())),
            "binding_change_count_distribution": dict(
                sorted(
                    Counter(
                        item.binding_change_count
                        for item in rows
                        if item.opportunity
                    ).items()
                )
            ),
            "maximum_rule_cost_difference": max(
                (item.rule_cost_difference for item in rows),
                default=0.0,
            ),
            "maximum_relative_rule_cost_difference": max(
                (item.relative_rule_cost_difference for item in rows),
                default=0.0,
            ),
        }
    return {
        "schema_version": A1_ASSIGNMENT_AWARE_TEACHER_SCHEMA_V1,
        "scope": A1_ASSIGNMENT_AWARE_SCOPE,
        "split_metrics": split_rows,
        "formal_holdout_read_count": 0,
        "permissions": _closed_permissions(),
    }


def copy_a1_assignment_aware_bundle(
    source: str | Path,
    destination: str | Path,
) -> None:
    """Copy a frozen bundle without following links or mutating its contents."""

    source_path = Path(source)
    destination_path = Path(destination)
    if destination_path.exists():
        raise A1AssignmentAwareContractError(
            "bundle_copy_destination_exists"
        )
    loaded = load_a1_assignment_aware_bundle(
        source_path, mode="source_independent_evaluation"
    )
    if not loaded.loaded:
        raise A1AssignmentAwareContractError(
            "bundle_copy_source_invalid", loaded.fallback_reason
        )
    shutil.copytree(source_path, destination_path, symlinks=False)
    copied = load_a1_assignment_aware_bundle(
        destination_path,
        mode="source_independent_evaluation",
        expected_manifest_sha256=loaded.manifest_sha256,
        expected_tree_sha256=loaded.tree_sha256,
    )
    if not copied.loaded:
        raise A1AssignmentAwareContractError(
            "bundle_copy_verification_failed", copied.fallback_reason
        )


def _build_teacher_frame(
    record: LearningFrameRecord,
    config: A1AssignmentAwareConfig,
) -> A1AssignmentAwareTeacherFrame:
    rule_matrix = np.asarray(record.rule_cost_matrix, dtype=float)
    r0 = solve_a1_safe_assignment(record, rule_matrix)
    if r0.safety_violation_count:
        raise A1AssignmentAwareContractError("r0_safety_violation")
    edge_to_offset = {
        edge: offset
        for offset, edge in enumerate(record.candidate_edge_indices)
    }
    r0_edges = set(r0.selected_edges)
    previous_edges = set(record.previous_selected_edges)
    previous_candidates: list[tuple[float, tuple[int, int]]] = []
    for edge in previous_edges - r0_edges:
        if edge not in edge_to_offset or not bool(record.action_mask[edge]):
            continue
        same_row = [
            float(rule_matrix[selected])
            for selected in r0.selected_edges
            if selected[0] == edge[0]
        ]
        baseline = min(same_row, default=float(rule_matrix[edge]))
        previous_candidates.append(
            (float(rule_matrix[edge]) - baseline, edge)
        )
    previous_candidates.sort(key=lambda value: (value[0], value[1]))

    maximum_realized = min(
        config.maximum_abs_cost_correction,
        config.alpha * float(np.tanh(config.residual_bound)),
    )
    chosen: tuple[
        float,
        tuple[int, int],
        tuple[tuple[int, int], ...],
        A1SafeAssignmentOutcome,
        np.ndarray,
        float,
        float,
        int,
    ] | None = None
    for _, promoted_edge in previous_candidates[
        : config.maximum_previous_edge_candidates
    ]:
        demoted_edges = tuple(
            edge
            for edge in r0.selected_edges
            if edge[0] == promoted_edge[0]
        )
        for fraction in config.correction_grid_fractions:
            correction_value = maximum_realized * float(fraction)
            correction_matrix = np.zeros_like(rule_matrix, dtype=float)
            correction_matrix[promoted_edge] -= correction_value
            for edge in demoted_edges:
                correction_matrix[edge] += correction_value
            candidate = solve_a1_safe_assignment(
                record,
                rule_matrix + correction_matrix,
            )
            binding_change_count = len(
                set(candidate.selected_edges).symmetric_difference(r0_edges)
            )
            raw_difference = (
                candidate.objective_on_rule_matrix
                - r0.objective_on_rule_matrix
            )
            relative_difference = max(0.0, raw_difference) / max(
                abs(r0.objective_on_rule_matrix), 1.0e-12
            )
            if (
                candidate.selected_edges == r0.selected_edges
                or candidate.safety_violation_count
                or candidate.assigned_slot_count < r0.assigned_slot_count
                or candidate.high_threat_assigned_slot_count
                < r0.high_threat_assigned_slot_count
                or candidate.churn >= r0.churn
                or binding_change_count > config.maximum_binding_change_count
                or raw_difference
                > config.maximum_rule_cost_difference + 1.0e-12
                or relative_difference
                > config.maximum_relative_rule_cost_difference + 1.0e-12
            ):
                continue
            target_corrections = np.zeros(
                len(record.candidate_edge_indices), dtype=np.float32
            )
            target_corrections[edge_to_offset[promoted_edge]] = (
                -correction_value
            )
            for edge in demoted_edges:
                offset = edge_to_offset.get(edge)
                if offset is not None:
                    target_corrections[offset] = correction_value
            chosen = (
                float(fraction),
                promoted_edge,
                demoted_edges,
                candidate,
                target_corrections,
                float(raw_difference),
                float(relative_difference),
                int(binding_change_count),
            )
            break
        if chosen is not None:
            break

    if chosen is None:
        target = r0
        target_corrections = np.zeros(
            len(record.candidate_edge_indices), dtype=np.float32
        )
        promoted_offset = None
        demoted_offsets: tuple[int, ...] = ()
        opportunity = False
        reason = (
            "no_previous_binding_challenger"
            if not previous_candidates
            else "no_safe_bounded_continuity_intervention"
        )
        fraction = 0.0
        raw_difference = 0.0
        relative_difference = 0.0
        binding_change_count = 0
    else:
        (
            fraction,
            promoted_edge,
            demoted_edges,
            target,
            target_corrections,
            raw_difference,
            relative_difference,
            binding_change_count,
        ) = chosen
        promoted_offset = edge_to_offset[promoted_edge]
        demoted_offsets = tuple(
            edge_to_offset[edge]
            for edge in demoted_edges
            if edge in edge_to_offset
        )
        opportunity = True
        reason = "safe_continuity_hard_alternative"

    sample_offsets = _sample_edge_offsets(
        record,
        target_edges=target.selected_edges,
        target_corrections=target_corrections,
        config=config,
    )
    return A1AssignmentAwareTeacherFrame(
        record=record,
        r0=r0,
        target=target,
        target_cost_corrections=target_corrections,
        sample_edge_offsets=sample_offsets,
        promoted_edge_offset=promoted_offset,
        demoted_edge_offsets=demoted_offsets,
        opportunity=opportunity,
        reason=reason,
        correction_fraction=float(fraction),
        maximum_abs_cost_correction=float(
            np.max(np.abs(target_corrections))
            if len(target_corrections)
            else 0.0
        ),
        binding_change_count=int(binding_change_count),
        rule_cost_difference=float(raw_difference),
        relative_rule_cost_difference=float(relative_difference),
    )


def _sample_edge_offsets(
    record: LearningFrameRecord,
    *,
    target_edges: Sequence[tuple[int, int]],
    target_corrections: np.ndarray,
    config: A1AssignmentAwareConfig,
) -> np.ndarray:
    edge_to_offset = {
        edge: offset
        for offset, edge in enumerate(record.candidate_edge_indices)
    }
    mandatory = {
        offset
        for offset, value in enumerate(target_corrections)
        if abs(float(value)) > 0.0
    }
    for edge in (
        set(record.rule_selected_edges)
        | set(record.previous_selected_edges)
        | set(target_edges)
    ):
        offset = edge_to_offset.get(edge)
        if offset is not None:
            mandatory.add(offset)
    by_target: dict[int, list[int]] = {}
    for offset, (target_index, _) in enumerate(record.candidate_edge_indices):
        by_target.setdefault(target_index, []).append(offset)
    sampled = set(mandatory)
    for offsets in by_target.values():
        ordered = sorted(
            offsets,
            key=lambda offset: (
                float(record.rule_costs[offset]),
                record.candidate_edge_indices[offset],
            ),
        )
        sampled.update(ordered[: config.hard_negative_edges_per_target])
    if len(sampled) > config.maximum_sample_edges_per_frame:
        retained = set(mandatory)
        remainder = sorted(
            sampled - mandatory,
            key=lambda offset: (
                float(record.rule_costs[offset]),
                record.candidate_edge_indices[offset],
            ),
        )
        capacity = config.maximum_sample_edges_per_frame - len(retained)
        if capacity < 0:
            raise A1AssignmentAwareContractError(
                "mandatory_sample_edges_exceed_limit"
            )
        retained.update(remainder[:capacity])
        sampled = retained
    return np.asarray(sorted(sampled), dtype=np.int64)


def _assignment_aware_batch_loss(
    policy: A1AssignmentAwareResidualPolicy,
    teachers: Sequence[A1AssignmentAwareTeacherFrame],
    *,
    mean: np.ndarray,
    scale: np.ndarray,
    config: A1AssignmentAwareConfig,
) -> Any:
    device = next(policy.parameters()).device
    losses: list[Any] = []
    for teacher in teachers:
        offsets = teacher.sample_edge_offsets
        normalized_full = (
            teacher.record.candidate_features - mean
        ) / scale
        sampled = normalized_full[offsets]
        features = torch.as_tensor(
            sampled, dtype=torch.float32, device=device
        )
        context = torch.as_tensor(
            _frame_context(normalized_full),
            dtype=torch.float32,
            device=device,
        )
        latent, selection_logits, gate_logit = policy(features, context)
        raw_delta = policy.residual_bound * torch.tanh(latent)
        gate_probability = torch.sigmoid(gate_logit)
        predicted_correction = (
            config.alpha * torch.tanh(raw_delta) * gate_probability
        )
        target_correction = torch.as_tensor(
            teacher.target_cost_corrections[offsets],
            dtype=torch.float32,
            device=device,
        )
        correction_weights = torch.where(
            torch.abs(target_correction) > 0.0,
            torch.full_like(
                target_correction, config.nonzero_correction_weight
            ),
            torch.ones_like(target_correction),
        )
        residual_loss = (
            nn.functional.smooth_l1_loss(
                predicted_correction,
                target_correction,
                reduction="none",
            )
            * correction_weights
        ).sum() / correction_weights.sum()

        target_edge_set = set(teacher.target.selected_edges)
        selection_target = torch.as_tensor(
            [
                float(teacher.record.candidate_edge_indices[int(offset)] in target_edge_set)
                for offset in offsets
            ],
            dtype=torch.float32,
            device=device,
        )
        positives = int(torch.count_nonzero(selection_target > 0.5).item())
        negatives = int(selection_target.numel()) - positives
        selection_weight = min(16.0, max(1.0, negatives / max(1, positives)))
        selection_weights = torch.where(
            selection_target > 0.5,
            torch.full_like(selection_target, selection_weight),
            torch.ones_like(selection_target),
        )
        selection_loss = (
            nn.functional.binary_cross_entropy_with_logits(
                selection_logits,
                selection_target,
                reduction="none",
            )
            * selection_weights
        ).sum() / selection_weights.sum()

        gate_target = torch.as_tensor(
            float(teacher.opportunity),
            dtype=torch.float32,
            device=device,
        )
        gate_weight = (
            config.positive_gate_weight if teacher.opportunity else 1.0
        )
        gate_loss = (
            nn.functional.binary_cross_entropy_with_logits(
                gate_logit, gate_target
            )
            * gate_weight
        )

        ranking_loss = torch.zeros((), dtype=features.dtype, device=device)
        if teacher.opportunity and teacher.promoted_edge_offset is not None:
            local = {
                int(global_offset): local_offset
                for local_offset, global_offset in enumerate(offsets)
            }
            promoted_local = local.get(int(teacher.promoted_edge_offset))
            demoted_local = [
                local[offset]
                for offset in teacher.demoted_edge_offsets
                if offset in local
            ]
            if promoted_local is not None and demoted_local:
                sampled_rule_costs = torch.as_tensor(
                    teacher.record.rule_costs[offsets],
                    dtype=torch.float32,
                    device=device,
                )
                final_costs = sampled_rule_costs + predicted_correction
                ranking_loss = torch.stack(
                    [
                        torch.relu(
                            final_costs[promoted_local]
                            - final_costs[index]
                            + config.ranking_margin
                        )
                        for index in demoted_local
                    ]
                ).mean()
        losses.append(
            config.residual_loss_weight * residual_loss
            + config.ranking_loss_weight * ranking_loss
            + config.selection_loss_weight * selection_loss
            + config.gate_loss_weight * gate_loss
        )
    return torch.stack(losses).mean()


def _select_checkpoint(
    epoch_history: Sequence[Mapping[str, Any]],
    *,
    config: A1AssignmentAwareConfig,
) -> tuple[int, str, bool]:
    eligible: list[tuple[tuple[int, int, int, int, int], int]] = []
    for row in epoch_history:
        epoch = int(row["epoch"])
        metrics = row["validation"]
        gate = metrics["machine_gate"]
        mandatory = (
            gate["nonzero_cost_correction"]
            and gate["nonzero_safe_binding_change"]
            and gate["zero_duplicate_resource"]
            and gate["zero_hard_edge_violation"]
            and gate["zero_m_to_n_atomicity_violation"]
            and gate["zero_version_violation"]
            and gate["model_does_not_output_plan_version"]
            and gate["r0_raw_rule_matrix_immutable"]
            and gate["fallback_matrix_exact_r0"]
            and gate["fallback_binding_exact_r0"]
            and metrics["negative_exact_r0_rate"] + 1.0e-12
            >= config.minimum_negative_exact_r0_rate
        )
        if not mandatory:
            continue
        score = (
            int(metrics["positive_safe_binding_change_frame_count"]),
            int(metrics["positive_teacher_exact_match_count"]),
            int(metrics["negative_exact_r0_count"]),
            -int(metrics["projection_rejection_count"]),
            -epoch,
        )
        eligible.append((score, epoch))
    if eligible:
        _, selected = max(eligible)
        return (
            int(selected),
            "validation_safe_binding_change_checkpoint_selected",
            True,
        )
    safest = max(
        epoch_history,
        key=lambda row: (
            int(row["validation"]["negative_exact_r0_count"]),
            -int(row["validation"]["projection_rejection_count"]),
            -int(row["epoch"]),
        ),
    )
    return (
        int(safest["epoch"]),
        "no_validation_checkpoint_crossed_discrete_development_gate",
        False,
    )


def _fit_normalization(
    teachers: Sequence[A1AssignmentAwareTeacherFrame],
) -> tuple[np.ndarray, np.ndarray]:
    count = 0
    total = np.zeros(len(EDGE_FEATURE_NAMES), dtype=np.float64)
    squared = np.zeros(len(EDGE_FEATURE_NAMES), dtype=np.float64)
    for teacher in teachers:
        matrix = np.asarray(
            teacher.record.candidate_features, dtype=np.float64
        )
        count += len(matrix)
        total += np.sum(matrix, axis=0)
        squared += np.sum(matrix * matrix, axis=0)
    if count < 1:
        raise A1AssignmentAwareContractError(
            "normalization_train_edges_empty"
        )
    mean = total / count
    variance = np.maximum(0.0, squared / count - mean * mean)
    scale = np.maximum(np.sqrt(variance), 1.0e-3)
    return mean.astype(np.float32), scale.astype(np.float32)


def _frame_context(normalized_features: np.ndarray) -> np.ndarray:
    matrix = np.asarray(normalized_features, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != len(EDGE_FEATURE_NAMES):
        raise ValueError("normalized feature matrix has the wrong shape")
    if not len(matrix):
        return np.zeros(len(EDGE_FEATURE_NAMES) * 4 + 8, dtype=np.float32)
    previous_mask = matrix[:, 11] > 1.0
    current_cost = matrix[:, 0]
    previous_cost = current_cost[previous_mask]
    other_cost = current_cost[~previous_mask]

    def statistics(values: np.ndarray) -> tuple[float, float, float]:
        if not len(values):
            return (0.0, 0.0, 0.0)
        return (
            float(np.min(values)),
            float(np.mean(values)),
            float(np.max(values)),
        )

    previous_min, previous_mean, previous_max = statistics(previous_cost)
    other_min, other_mean, _ = statistics(other_cost)
    joint = np.asarray(
        (
            float(np.mean(previous_mask)),
            float(np.log1p(np.count_nonzero(previous_mask))),
            previous_min,
            previous_mean,
            previous_max,
            other_min,
            other_mean,
            previous_min - other_min,
        ),
        dtype=np.float32,
    )
    return np.concatenate(
        (
            np.mean(matrix, axis=0),
            np.std(matrix, axis=0),
            np.min(matrix, axis=0),
            np.max(matrix, axis=0),
            joint,
        )
    ).astype(np.float32)


def _is_ood(normalized_features: np.ndarray, z_threshold: float) -> bool:
    matrix = np.asarray(normalized_features, dtype=float)
    return bool(
        not np.all(np.isfinite(matrix))
        or np.any(np.abs(matrix) > float(z_threshold))
    )


def _cpu_state_dict(policy: Any) -> OrderedDict[str, Any]:
    return OrderedDict(
        (
            str(name),
            value.detach().cpu().contiguous().clone(),
        )
        for name, value in sorted(policy.state_dict().items())
    )


def _write_canonical_state_dict(
    path: Path,
    state_dict: Mapping[str, Any],
) -> None:
    tensors = []
    for name, tensor in sorted(state_dict.items()):
        array = np.asarray(tensor.detach().cpu().numpy())
        canonical = np.ascontiguousarray(array.astype(array.dtype.newbyteorder("<")))
        tensors.append(
            {
                "name": str(name),
                "dtype": canonical.dtype.str,
                "shape": list(canonical.shape),
                "data_base64": base64.b64encode(
                    canonical.tobytes(order="C")
                ).decode("ascii"),
            }
        )
    path.write_text(
        _canonical_json(
            {
                "schema_version": (
                    "d3_a1_assignment_aware_canonical_state_dict_v1"
                ),
                "tensors": tensors,
            }
        )
        + "\n",
        encoding="ascii",
    )


def _read_canonical_state_dict(path: Path) -> OrderedDict[str, Any]:
    payload = json.loads(path.read_text(encoding="ascii"))
    if (
        not isinstance(payload, Mapping)
        or set(payload) != {"schema_version", "tensors"}
        or payload["schema_version"]
        != "d3_a1_assignment_aware_canonical_state_dict_v1"
        or not isinstance(payload["tensors"], list)
    ):
        raise A1AssignmentAwareContractError(
            "bundle_state_dict_schema_invalid"
        )
    output: OrderedDict[str, Any] = OrderedDict()
    for item in payload["tensors"]:
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "dtype",
            "shape",
            "data_base64",
        }:
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_fields_invalid"
            )
        name = str(item["name"])
        if not name or name in output:
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_name_invalid"
            )
        dtype = np.dtype(str(item["dtype"]))
        if dtype.kind not in {"f", "i", "u", "b"}:
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_dtype_invalid"
            )
        shape = tuple(int(value) for value in item["shape"])
        if any(value < 0 for value in shape):
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_shape_invalid"
            )
        try:
            raw = base64.b64decode(
                str(item["data_base64"]).encode("ascii"),
                validate=True,
            )
        except (ValueError, UnicodeEncodeError) as error:
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_base64_invalid"
            ) from error
        expected_size = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
        if len(raw) != expected_size:
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_size_invalid"
            )
        array = np.frombuffer(raw, dtype=dtype).reshape(shape).copy()
        if not np.all(np.isfinite(array)):
            raise A1AssignmentAwareContractError(
                "bundle_state_tensor_non_finite"
            )
        output[name] = torch.as_tensor(array)
    return output


def _validate_assignment_aware_manifest(value: Mapping[str, Any]) -> None:
    required = {
        "bundle_schema_version",
        "policy_version",
        "scope",
        "stage",
        "allowed_modes",
        "feature_schema_version",
        "feature_names",
        "model_config",
        "configuration",
        "normalization",
        "source_dataset",
        "training",
        "state_dict",
        "provenance",
        "admission",
        "permissions",
        "fallback",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise A1AssignmentAwareContractError("bundle_manifest_fields_mismatch")
    if (
        value["bundle_schema_version"]
        != A1_ASSIGNMENT_AWARE_BUNDLE_SCHEMA_V1
        or value["policy_version"] != A1_ASSIGNMENT_AWARE_POLICY_VERSION_V1
        or value["scope"] != A1_ASSIGNMENT_AWARE_SCOPE
        or value["stage"] != "development"
        or value["allowed_modes"]
        != ["shadow", "source_independent_evaluation"]
        or value["feature_names"] != list(EDGE_FEATURE_NAMES)
    ):
        raise A1AssignmentAwareContractError("bundle_manifest_identity_invalid")
    if value["permissions"] != _closed_permissions():
        raise A1AssignmentAwareContractError(
            "bundle_permission_escalation_forbidden"
        )
    admission = value["admission"]
    if (
        admission.get("status") != "development_shadow_only"
        or admission.get("production_bundle") is not False
        or admission.get("admitted_bundle") is not False
        or admission.get("formal_holdout_status")
        != "not_read_not_evaluated"
        or admission.get("formal_holdout_seed_values")
        != list(A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS)
    ):
        raise A1AssignmentAwareContractError("bundle_admission_invalid")
    source = value["source_dataset"]
    if (
        source.get("consumed_splits") != ["train", "validation"]
        or source.get("optimizer_consumed_splits") != ["train"]
        or source.get("checkpoint_selection_consumed_splits")
        != ["validation"]
        or int(source.get("parsed_test_frame_count", -1)) != 0
        or int(source.get("formal_holdout_read_count", -1)) != 0
        or source.get("formal_holdout_status")
        != "not_read_not_evaluated"
    ):
        raise A1AssignmentAwareContractError(
            "bundle_source_split_contract_invalid"
        )
    consumed_seeds = {
        *source.get("train_seed_values", []),
        *source.get("validation_seed_values", []),
    }
    if consumed_seeds & set(A1_ASSIGNMENT_AWARE_FORMAL_HOLDOUT_SEEDS):
        raise A1AssignmentAwareContractError(
            "bundle_formal_holdout_seed_overlap"
        )
    fallback = value["fallback"]
    if (
        fallback.get("required") is not True
        or fallback.get("matrix_policy")
        != "elementwise_exact_raw_rule_cost_matrix"
        or fallback.get("binding_policy") != "deterministic_r0_replay"
    ):
        raise A1AssignmentAwareContractError(
            "bundle_fallback_contract_invalid"
        )
    model = value["model_config"]
    if (
        int(model.get("feature_count", -1)) != len(EDGE_FEATURE_NAMES)
        or bool(model.get("assignment_output", True))
        or bool(model.get("plan_version_output", True))
    ):
        raise A1AssignmentAwareContractError(
            "bundle_model_output_contract_invalid"
        )
    normalization = value["normalization"]
    mean = np.asarray(normalization.get("mean"), dtype=float)
    scale = np.asarray(normalization.get("scale"), dtype=float)
    if (
        normalization.get("fit_split") != "train"
        or mean.shape != (len(EDGE_FEATURE_NAMES),)
        or scale.shape != mean.shape
        or not np.all(np.isfinite(mean))
        or not np.all(np.isfinite(scale))
        or np.any(scale <= 0.0)
    ):
        raise A1AssignmentAwareContractError(
            "bundle_normalization_invalid"
        )
    _sha256_text(value["state_dict"]["sha256"])
    _sha256_text(value["provenance"]["source_tree_sha256"])
    _git_sha(value["provenance"]["repository_git_commit"])


def _closed_permissions() -> dict[str, bool]:
    return {
        "assist": False,
        "authority": False,
        "assignment": False,
        "control": False,
        "physical": False,
        "formal_holdout": False,
        "production_admission": False,
        "runtime_publication": False,
    }


def _read_checksums(path: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise A1AssignmentAwareContractError(
                "bundle_checksum_line_invalid"
            )
        digest, filename = parts
        _sha256_text(digest)
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or filename in output
        ):
            raise A1AssignmentAwareContractError(
                "bundle_checksum_filename_invalid"
            )
        output[filename] = digest
    return output


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: Any) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise A1AssignmentAwareContractError("sha256_invalid")
    return text


def _git_sha(value: Any) -> str:
    text = str(value).strip().lower()
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        raise A1AssignmentAwareContractError("git_commit_invalid")
    return text


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
