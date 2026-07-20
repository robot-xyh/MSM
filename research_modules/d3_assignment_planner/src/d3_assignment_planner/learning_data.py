"""Reproducible, identity-free datasets for optional D3 learning research."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .learning import EDGE_FEATURE_NAMES, build_candidate_edge_batch
from .models import AssignmentPlan, PlannerConfig, ResourceState, TargetTrack
from .planner import AssignmentPlanner


LEARNING_DATASET_SCHEMA_V1 = "d3_learning_dataset_v1"
LEARNING_DATASET_SPLIT_POLICY_V1 = "d3_scenario_seed_group_split_v1"
DATASET_MANIFEST_FILENAME = "dataset_manifest.json"
DATASET_FRAMES_FILENAME = "frames.jsonl"
DATASET_SPLITS = ("train", "validation", "test")


@dataclass(frozen=True)
class OfflineRewardComponents:
    """Auditable raw terms used by BC diagnostics and PPO reward shaping."""

    high_threat_coverage: float
    rule_total_cost: float
    unmet_demand_slots: int
    reassignment_churn: int
    plan_expired: int
    safety_rejections: int

    def __post_init__(self) -> None:
        values = (self.high_threat_coverage, self.rule_total_cost)
        if not all(isfinite(float(value)) for value in values):
            raise ValueError("reward components must be finite")
        if not 0.0 <= float(self.high_threat_coverage) <= 1.0:
            raise ValueError("high_threat_coverage must be in [0, 1]")
        if float(self.rule_total_cost) < 0.0:
            raise ValueError("rule_total_cost must be non-negative")
        for name in (
            "unmet_demand_slots",
            "reassignment_churn",
            "plan_expired",
            "safety_rejections",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")

    def weighted_total(
        self,
        *,
        coverage_weight: float = 2.0,
        cost_weight: float = 0.05,
        unmet_weight: float = 2.0,
        churn_weight: float = 0.5,
        expiry_weight: float = 2.0,
        rejection_weight: float = 2.0,
    ) -> float:
        """Return the explicit offline reward used by the native PPO pipeline."""

        return float(
            coverage_weight * self.high_threat_coverage
            - cost_weight * self.rule_total_cost
            - unmet_weight * self.unmet_demand_slots
            - churn_weight * self.reassignment_churn
            - expiry_weight * self.plan_expired
            - rejection_weight * self.safety_rejections
        )

    def to_dict(self) -> dict[str, float | int]:
        return {
            "high_threat_coverage": float(self.high_threat_coverage),
            "rule_total_cost": float(self.rule_total_cost),
            "unmet_demand_slots": int(self.unmet_demand_slots),
            "reassignment_churn": int(self.reassignment_churn),
            "plan_expired": int(self.plan_expired),
            "safety_rejections": int(self.safety_rejections),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OfflineRewardComponents":
        return cls(
            high_threat_coverage=float(value["high_threat_coverage"]),
            rule_total_cost=float(value["rule_total_cost"]),
            unmet_demand_slots=int(value["unmet_demand_slots"]),
            reassignment_churn=int(value["reassignment_churn"]),
            plan_expired=int(value["plan_expired"]),
            safety_rejections=int(value["safety_rejections"]),
        )


@dataclass(frozen=True)
class LearningFrameRecord:
    """One planner frame with sparse actions and no operational identity fields."""

    scenario_version: str
    seed: int
    episode: str
    frame_index: int
    timestamp_s: float
    split: str
    anonymous_targets: tuple[Mapping[str, Any], ...]
    anonymous_resources: tuple[Mapping[str, Any], ...]
    candidate_edge_indices: tuple[tuple[int, int], ...]
    candidate_features: np.ndarray
    action_mask: np.ndarray
    rule_cost_matrix: np.ndarray
    rule_costs: np.ndarray
    unassigned_costs: np.ndarray
    rule_selected_edges: tuple[tuple[int, int], ...]
    previous_selected_edges: tuple[tuple[int, int], ...]
    previous_plan_version: int
    feedback_result: str
    hysteresis_result: str
    hold_label: bool
    replan_label: bool
    advice_allowed: bool
    target_threat_scores: tuple[float, ...]
    target_demand_slots: tuple[int, ...]
    hard_reject_reason_counts: Mapping[str, int]
    reward_components: OfflineRewardComponents

    def __post_init__(self) -> None:
        scenario_version = str(self.scenario_version).strip()
        episode = str(self.episode).strip()
        split = str(self.split).strip().lower()
        if not scenario_version or not episode:
            raise ValueError("scenario_version and episode are required")
        if split not in DATASET_SPLITS:
            raise ValueError(f"unsupported dataset split: {split}")
        if int(self.frame_index) < 0 or int(self.previous_plan_version) < 0:
            raise ValueError("frame and plan versions must be non-negative")
        if not isfinite(float(self.timestamp_s)):
            raise ValueError("timestamp_s must be finite")

        target_count = len(self.anonymous_targets)
        resource_count = len(self.anonymous_resources)
        features = np.asarray(self.candidate_features, dtype=np.float32)
        mask = np.asarray(self.action_mask, dtype=bool)
        matrix = np.asarray(self.rule_cost_matrix, dtype=float)
        rule_costs = np.asarray(self.rule_costs, dtype=float).reshape(-1)
        unassigned = np.asarray(self.unassigned_costs, dtype=float).reshape(-1)
        if features.shape != (len(self.candidate_edge_indices), len(EDGE_FEATURE_NAMES)):
            raise ValueError("candidate_features have the wrong sparse-edge shape")
        if mask.shape != (target_count, resource_count):
            raise ValueError("action_mask has the wrong target-resource shape")
        if matrix.shape != mask.shape:
            raise ValueError("rule_cost_matrix must match action_mask")
        if rule_costs.shape != (len(self.candidate_edge_indices),):
            raise ValueError("rule_costs must match candidate edges")
        if unassigned.shape != (target_count,):
            raise ValueError("unassigned_costs must match target count")
        if len(self.target_threat_scores) != target_count:
            raise ValueError("target_threat_scores must match target count")
        if len(self.target_demand_slots) != target_count:
            raise ValueError("target_demand_slots must match target count")
        if not np.all(np.isfinite(features)) or not np.all(np.isfinite(matrix)):
            raise ValueError("dataset feature and cost matrices must be finite")
        if not np.all(np.isfinite(rule_costs)) or not np.all(np.isfinite(unassigned)):
            raise ValueError("dataset costs must be finite")

        candidate_set = set(self.candidate_edge_indices)
        for edge in candidate_set | set(self.rule_selected_edges) | set(
            self.previous_selected_edges
        ):
            row, column = edge
            if not (0 <= row < target_count and 0 <= column < resource_count):
                raise ValueError("edge index lies outside the frame matrix")
        if candidate_set != set(zip(*np.nonzero(mask))):
            raise ValueError("candidate edges must exactly match the deterministic mask")
        if not set(self.rule_selected_edges).issubset(candidate_set):
            raise ValueError("rule-selected edges must be allowed by the action mask")

        _validate_anonymous_entities(self.anonymous_targets, "target")
        _validate_anonymous_entities(self.anonymous_resources, "resource")
        object.__setattr__(self, "scenario_version", scenario_version)
        object.__setattr__(self, "episode", episode)
        object.__setattr__(self, "split", split)
        object.__setattr__(self, "candidate_features", features)
        object.__setattr__(self, "action_mask", mask)
        object.__setattr__(self, "rule_cost_matrix", matrix)
        object.__setattr__(self, "rule_costs", rule_costs)
        object.__setattr__(self, "unassigned_costs", unassigned)

    @property
    def episode_group(self) -> tuple[str, int, str]:
        return (self.scenario_version, int(self.seed), self.episode)

    @property
    def seed_group(self) -> tuple[str, int]:
        return (self.scenario_version, int(self.seed))

    @property
    def selected_edge_labels(self) -> np.ndarray:
        selected = set(self.rule_selected_edges)
        return np.asarray(
            [edge in selected for edge in self.candidate_edge_indices],
            dtype=np.float32,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEARNING_DATASET_SCHEMA_V1,
            "scenario_version": self.scenario_version,
            "seed": int(self.seed),
            "episode": self.episode,
            "frame_index": int(self.frame_index),
            "timestamp_s": float(self.timestamp_s),
            "split": self.split,
            "anonymous_targets": [dict(value) for value in self.anonymous_targets],
            "anonymous_resources": [dict(value) for value in self.anonymous_resources],
            "candidate_edge_indices": [list(edge) for edge in self.candidate_edge_indices],
            "candidate_features": self.candidate_features.tolist(),
            "action_mask": self.action_mask.tolist(),
            "rule_cost_matrix": self.rule_cost_matrix.tolist(),
            "rule_costs": self.rule_costs.tolist(),
            "unassigned_costs": self.unassigned_costs.tolist(),
            "rule_selected_edges": [list(edge) for edge in self.rule_selected_edges],
            "previous_selected_edges": [list(edge) for edge in self.previous_selected_edges],
            "previous_plan_version": int(self.previous_plan_version),
            "feedback_result": str(self.feedback_result),
            "hysteresis_result": str(self.hysteresis_result),
            "hold_label": bool(self.hold_label),
            "replan_label": bool(self.replan_label),
            "advice_allowed": bool(self.advice_allowed),
            "target_threat_scores": [float(value) for value in self.target_threat_scores],
            "target_demand_slots": [int(value) for value in self.target_demand_slots],
            "hard_reject_reason_counts": {
                str(key): int(value)
                for key, value in sorted(self.hard_reject_reason_counts.items())
            },
            "reward_components": self.reward_components.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LearningFrameRecord":
        if value.get("schema_version") != LEARNING_DATASET_SCHEMA_V1:
            raise ValueError("unsupported D3 learning dataset frame schema")
        return cls(
            scenario_version=str(value["scenario_version"]),
            seed=int(value["seed"]),
            episode=str(value["episode"]),
            frame_index=int(value["frame_index"]),
            timestamp_s=float(value["timestamp_s"]),
            split=str(value["split"]),
            anonymous_targets=tuple(dict(item) for item in value["anonymous_targets"]),
            anonymous_resources=tuple(
                dict(item) for item in value["anonymous_resources"]
            ),
            candidate_edge_indices=tuple(
                (int(item[0]), int(item[1]))
                for item in value["candidate_edge_indices"]
            ),
            candidate_features=np.asarray(value["candidate_features"], dtype=np.float32),
            action_mask=np.asarray(value["action_mask"], dtype=bool),
            rule_cost_matrix=np.asarray(value["rule_cost_matrix"], dtype=float),
            rule_costs=np.asarray(value["rule_costs"], dtype=float),
            unassigned_costs=np.asarray(value["unassigned_costs"], dtype=float),
            rule_selected_edges=tuple(
                (int(item[0]), int(item[1])) for item in value["rule_selected_edges"]
            ),
            previous_selected_edges=tuple(
                (int(item[0]), int(item[1]))
                for item in value["previous_selected_edges"]
            ),
            previous_plan_version=int(value["previous_plan_version"]),
            feedback_result=str(value["feedback_result"]),
            hysteresis_result=str(value["hysteresis_result"]),
            hold_label=bool(value["hold_label"]),
            replan_label=bool(value["replan_label"]),
            advice_allowed=bool(value["advice_allowed"]),
            target_threat_scores=tuple(float(item) for item in value["target_threat_scores"]),
            target_demand_slots=tuple(int(item) for item in value["target_demand_slots"]),
            hard_reject_reason_counts={
                str(key): int(item)
                for key, item in value["hard_reject_reason_counts"].items()
            },
            reward_components=OfflineRewardComponents.from_dict(
                value["reward_components"]
            ),
        )


@dataclass(frozen=True)
class LearningDatasetManifest:
    schema_version: str
    split_policy_version: str
    feature_names: tuple[str, ...]
    split_hash: str
    frame_count: int
    episode_count: int
    split_frame_counts: Mapping[str, int]
    split_seed_groups: Mapping[str, tuple[str, ...]]
    source_kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "split_policy_version": self.split_policy_version,
            "feature_names": list(self.feature_names),
            "split_hash": self.split_hash,
            "frame_count": int(self.frame_count),
            "episode_count": int(self.episode_count),
            "split_frame_counts": {
                split: int(self.split_frame_counts.get(split, 0))
                for split in DATASET_SPLITS
            },
            "split_seed_groups": {
                split: list(self.split_seed_groups.get(split, ()))
                for split in DATASET_SPLITS
            },
            "source_kind": self.source_kind,
            "identity_policy": "anonymous_ordinal_tokens_no_truth_metadata",
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LearningDatasetManifest":
        return cls(
            schema_version=str(value["schema_version"]),
            split_policy_version=str(value["split_policy_version"]),
            feature_names=tuple(str(item) for item in value["feature_names"]),
            split_hash=str(value["split_hash"]),
            frame_count=int(value["frame_count"]),
            episode_count=int(value["episode_count"]),
            split_frame_counts={
                str(key): int(item)
                for key, item in value["split_frame_counts"].items()
            },
            split_seed_groups={
                str(key): tuple(str(item) for item in items)
                for key, items in value["split_seed_groups"].items()
            },
            source_kind=str(value["source_kind"]),
        )


def assign_episode_split(
    scenario_version: str,
    seed: int,
    episode: str | int,
    *,
    train_fraction: float = 0.7,
    validation_fraction: float = 0.15,
) -> str:
    """Assign every episode from one scenario/seed to the same stable split."""

    if not str(scenario_version).strip() or not str(episode).strip():
        raise ValueError("scenario_version and episode are required")
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be in (0, 1)")
    if not 0.0 <= validation_fraction < 1.0 - train_fraction:
        raise ValueError("validation_fraction leaves no test split")
    group = f"{LEARNING_DATASET_SPLIT_POLICY_V1}|{scenario_version}|{int(seed)}"
    unit = int.from_bytes(sha256(group.encode("utf-8")).digest()[:8], "big") / 2**64
    if unit < train_fraction:
        return "train"
    if unit < train_fraction + validation_fraction:
        return "validation"
    return "test"


def validate_split_integrity(records: Iterable[LearningFrameRecord]) -> None:
    """Reject frame/episode splitting and all cross-split seed leakage."""

    episode_splits: dict[tuple[str, int, str], str] = {}
    seed_splits: dict[tuple[str, int], str] = {}
    seen_frames: set[tuple[str, int, str, int]] = set()
    for record in records:
        frame_key = (*record.episode_group, int(record.frame_index))
        if frame_key in seen_frames:
            raise ValueError(f"duplicate dataset frame: {frame_key}")
        seen_frames.add(frame_key)
        prior_episode = episode_splits.setdefault(record.episode_group, record.split)
        if prior_episode != record.split:
            raise ValueError("one episode appears in multiple dataset splits")
        prior_seed = seed_splits.setdefault(record.seed_group, record.split)
        if prior_seed != record.split:
            raise ValueError("one scenario/seed appears in multiple dataset splits")


def compute_split_hash(records: Iterable[LearningFrameRecord]) -> str:
    items = tuple(records)
    validate_split_integrity(items)
    groups = sorted(
        {
            (record.scenario_version, int(record.seed), record.episode, record.split)
            for record in items
        }
    )
    payload = json.dumps(groups, ensure_ascii=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def build_learning_frame_record(
    *,
    scenario_version: str,
    seed: int,
    episode: str | int,
    frame_index: int,
    timestamp_s: float,
    matrix_result: Any,
    tracks: Sequence[TargetTrack],
    resources: Sequence[ResourceState],
    plan: AssignmentPlan,
    previous_plan: AssignmentPlan | None,
    feedback_result: str | None = None,
    advice_interval: int = 5,
) -> LearningFrameRecord:
    """Convert one rule-planner frame into the identity-free dataset contract."""

    if advice_interval < 1:
        raise ValueError("advice_interval must be positive")
    previous_version = 0 if previous_plan is None else int(previous_plan.version)
    batch = build_candidate_edge_batch(
        matrix_result,
        list(tracks),
        list(resources),
        expected_previous_version=previous_version,
        current_plan_version=previous_version,
        previous_plan=previous_plan,
    )
    target_index = {value: index for index, value in enumerate(matrix_result.target_ids)}
    resource_index = {
        value: index for index, value in enumerate(matrix_result.resource_ids)
    }

    def plan_edges(value: AssignmentPlan | None) -> tuple[tuple[int, int], ...]:
        if value is None:
            return ()
        edges = {
            (target_index[item.target_id], resource_index[item.resource_id])
            for item in value.assignments
            if item.target_id in target_index and item.resource_id in resource_index
        }
        return tuple(sorted(edges))

    selected_edges = plan_edges(plan)
    previous_edges = plan_edges(previous_plan)
    required = tuple(track.effective_demand.required_resource_count for track in tracks)
    assigned_by_target = {
        row: sum(1 for edge in selected_edges if edge[0] == row)
        for row in range(len(tracks))
    }
    high_threat_rows = [
        index for index, track in enumerate(tracks) if float(track.threat_score) >= 0.7
    ]
    if high_threat_rows:
        high_threat_coverage = float(
            np.mean(
                [
                    min(1.0, assigned_by_target[row] / max(1, required[row]))
                    for row in high_threat_rows
                ]
            )
        )
    else:
        high_threat_coverage = 1.0
    unmet = sum(
        max(0, required[row] - assigned_by_target[row]) for row in range(len(tracks))
    )
    churn = len(set(selected_edges).symmetric_difference(previous_edges))
    decision = str(plan.decision_state)
    hold_label = decision.startswith("held") or decision == "unchanged"
    replan_label = previous_plan is not None and bool(plan.changed) and not hold_label
    hard_counts = _hard_reject_counts(matrix_result.reject_reasons)
    reward = OfflineRewardComponents(
        high_threat_coverage=high_threat_coverage,
        rule_total_cost=max(0.0, float(plan.total_cost)),
        unmet_demand_slots=unmet,
        reassignment_churn=churn,
        plan_expired=int("stale" in decision or "expired" in decision),
        safety_rejections=int(bool(plan.duplicate_terminal_lock_risk)),
    )
    split = assign_episode_split(scenario_version, seed, episode)
    return LearningFrameRecord(
        scenario_version=scenario_version,
        seed=int(seed),
        episode=str(episode),
        frame_index=int(frame_index),
        timestamp_s=float(timestamp_s),
        split=split,
        anonymous_targets=tuple(
            {
                "token": f"target_{index:04d}",
                "threat_score": float(track.threat_score),
                "covariance_squashed": _squash_nonnegative(track.covariance),
                "window_cost": float(track.window_cost),
                "required_resource_count": int(
                    track.effective_demand.required_resource_count
                ),
                "primary_resource_count": int(
                    track.effective_demand.primary_resource_count
                ),
                "assignable": bool(track.assignable),
            }
            for index, track in enumerate(tracks)
        ),
        anonymous_resources=tuple(
            {
                "token": f"resource_{index:04d}",
                "available": resource.status == "available"
                and not resource.operator_hold,
                "health_score": float(resource.health_score),
                "energy_fraction": float(resource.energy_fraction),
                "availability_score": float(resource.availability_score),
                "current_load": float(resource.current_load),
                "assignment_capacity": int(resource.assignment_capacity),
            }
            for index, resource in enumerate(resources)
        ),
        candidate_edge_indices=batch.edge_indices,
        candidate_features=batch.features,
        action_mask=batch.action_mask.mask,
        rule_cost_matrix=np.asarray(matrix_result.matrix, dtype=float).copy(),
        rule_costs=batch.rule_costs,
        unassigned_costs=np.asarray(matrix_result.unassigned_costs, dtype=float),
        rule_selected_edges=selected_edges,
        previous_selected_edges=previous_edges,
        previous_plan_version=previous_version,
        feedback_result=(
            str(feedback_result)
            if feedback_result is not None
            else str(plan.terminal_feedback_state or "none")
        ),
        hysteresis_result=decision,
        hold_label=hold_label,
        replan_label=replan_label,
        advice_allowed=(int(frame_index) % int(advice_interval) == 0),
        target_threat_scores=tuple(float(track.threat_score) for track in tracks),
        target_demand_slots=required,
        hard_reject_reason_counts=hard_counts,
        reward_components=reward,
    )


def build_latest_learning_frame_record(
    planner: AssignmentPlanner,
    *,
    scenario_version: str,
    seed: int,
    episode: str | int,
    frame_index: int,
    feedback_result: str | None = None,
    advice_interval: int = 5,
) -> LearningFrameRecord:
    """Convert the planner's latest complete local evidence into one record."""

    evidence = planner.latest_planning_evidence
    if not evidence.available:
        raise RuntimeError(
            f"latest D3 planning evidence is unavailable: {evidence.reason}"
        )
    required = (
        evidence.timestamp_s,
        evidence.rule_matrix_result,
        evidence.plan,
    )
    if any(value is None for value in required):
        raise RuntimeError("latest D3 planning evidence is incomplete")
    return build_learning_frame_record(
        scenario_version=scenario_version,
        seed=seed,
        episode=episode,
        frame_index=frame_index,
        timestamp_s=float(evidence.timestamp_s),
        matrix_result=evidence.rule_matrix_result,
        tracks=evidence.tracks,
        resources=evidence.resources,
        plan=evidence.plan,
        previous_plan=evidence.previous_plan,
        feedback_result=feedback_result,
        advice_interval=advice_interval,
    )


def write_learning_dataset(
    output_dir: str | Path,
    records: Iterable[LearningFrameRecord],
    *,
    source_kind: str,
) -> LearningDatasetManifest:
    """Write canonical JSONL and a split manifest without model artifacts."""

    items = tuple(
        sorted(
            records,
            key=lambda item: (
                item.scenario_version,
                int(item.seed),
                item.episode,
                int(item.frame_index),
            ),
        )
    )
    if not items:
        raise ValueError("at least one dataset frame is required")
    validate_split_integrity(items)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frame_path = output / DATASET_FRAMES_FILENAME
    with frame_path.open("w", encoding="utf-8", newline="\n") as stream:
        for record in items:
            stream.write(
                json.dumps(
                    record.to_dict(),
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            stream.write("\n")
    split_counts = {
        split: sum(record.split == split for record in items) for split in DATASET_SPLITS
    }
    split_seed_groups = {
        split: tuple(
            sorted(
                {
                    f"{record.scenario_version}:{record.seed}"
                    for record in items
                    if record.split == split
                }
            )
        )
        for split in DATASET_SPLITS
    }
    manifest = LearningDatasetManifest(
        schema_version=LEARNING_DATASET_SCHEMA_V1,
        split_policy_version=LEARNING_DATASET_SPLIT_POLICY_V1,
        feature_names=EDGE_FEATURE_NAMES,
        split_hash=compute_split_hash(items),
        frame_count=len(items),
        episode_count=len({record.episode_group for record in items}),
        split_frame_counts=split_counts,
        split_seed_groups=split_seed_groups,
        source_kind=str(source_kind),
    )
    with (output / DATASET_MANIFEST_FILENAME).open(
        "w", encoding="utf-8", newline="\n"
    ) as stream:
        json.dump(manifest.to_dict(), stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    return manifest


def load_learning_dataset(
    input_dir: str | Path,
) -> tuple[LearningDatasetManifest, tuple[LearningFrameRecord, ...]]:
    input_path = Path(input_dir)
    with (input_path / DATASET_MANIFEST_FILENAME).open(encoding="utf-8") as stream:
        manifest = LearningDatasetManifest.from_dict(json.load(stream))
    if manifest.schema_version != LEARNING_DATASET_SCHEMA_V1:
        raise ValueError("unsupported D3 learning dataset manifest schema")
    if manifest.feature_names != EDGE_FEATURE_NAMES:
        raise ValueError("dataset feature schema does not match this D3 build")
    records: list[LearningFrameRecord] = []
    with (input_path / DATASET_FRAMES_FILENAME).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                records.append(LearningFrameRecord.from_dict(json.loads(line)))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid dataset frame at line {line_number}") from exc
    items = tuple(records)
    validate_split_integrity(items)
    if len(items) != manifest.frame_count:
        raise ValueError("dataset frame count does not match manifest")
    if compute_split_hash(items) != manifest.split_hash:
        raise ValueError("dataset split hash does not match manifest")
    return manifest, items


def generate_synthetic_learning_dataset(
    output_dir: str | Path,
    *,
    seeds: Sequence[int] = tuple(range(30)),
    episodes_per_seed: int = 2,
    frames_per_episode: int = 4,
    scenario_version: str = "d3_synthetic_sparse_v1",
) -> LearningDatasetManifest:
    """Generate deterministic 3v5/5v3 smoke data; not promotion evidence."""

    if not seeds or episodes_per_seed < 1 or frames_per_episode < 1:
        raise ValueError("seeds, episodes_per_seed, and frames_per_episode are required")
    records: list[LearningFrameRecord] = []
    roster_shapes = ((3, 5), (5, 3))
    for seed in sorted({int(value) for value in seeds}):
        for episode_index in range(int(episodes_per_seed)):
            target_count, resource_count = roster_shapes[(seed + episode_index) % 2]
            rng = np.random.default_rng(seed * 10_007 + episode_index)
            config = PlannerConfig.scalable_3d(
                enable_hysteresis=True,
                min_dwell=0.0,
                max_candidate_edges_per_target=min(4, resource_count),
            )
            planner = AssignmentPlanner(config=config)
            previous_plan: AssignmentPlan | None = None
            base_target_y = rng.uniform(-80.0, 80.0, size=target_count)
            base_resource_y = rng.uniform(-100.0, 100.0, size=resource_count)
            for frame_index in range(int(frames_per_episode)):
                timestamp_s = float(frame_index)
                tracks = [
                    TargetTrack(
                        track_id=f"internal_track_{index}",
                        threat_score=float(0.35 + 0.6 * rng.random()),
                        covariance=float(0.05 + 0.15 * rng.random()),
                        window_cost=float(0.15 * rng.random()),
                        position_ned=(
                            500.0 - 12.0 * frame_index + 15.0 * index,
                            float(base_target_y[index]),
                            -100.0,
                        ),
                        velocity_ned=(-12.0, 0.0, 0.0),
                        region_id="synthetic",
                    )
                    for index in range(target_count)
                ]
                resources = [
                    ResourceState(
                        resource_id=f"internal_resource_{index}",
                        position_ned=(0.0, float(base_resource_y[index]), -100.0),
                        velocity_ned=(0.0, 0.0, 0.0),
                        max_speed_mps=45.0 + 2.0 * (index % 3),
                        health_score=float(0.8 + 0.2 * rng.random()),
                        energy_fraction=float(0.75 + 0.25 * rng.random()),
                        region_id="synthetic",
                    )
                    for index in range(resource_count)
                ]
                plan = planner.plan(
                    tracks,
                    resources,
                    timestamp=timestamp_s,
                    previous_plan=previous_plan,
                    expected_previous_version=(
                        None if previous_plan is None else previous_plan.version
                    ),
                )
                records.append(
                    build_latest_learning_frame_record(
                        planner,
                        scenario_version=scenario_version,
                        seed=seed,
                        episode=f"episode_{episode_index:03d}",
                        frame_index=frame_index,
                    )
                )
                previous_plan = plan
    return write_learning_dataset(output_dir, records, source_kind="synthetic_smoke")


def _validate_anonymous_entities(
    entities: Sequence[Mapping[str, Any]],
    kind: str,
) -> None:
    allowed = {
        "target": {
            "token",
            "threat_score",
            "covariance_squashed",
            "window_cost",
            "required_resource_count",
            "primary_resource_count",
            "assignable",
        },
        "resource": {
            "token",
            "available",
            "health_score",
            "energy_fraction",
            "availability_score",
            "current_load",
            "assignment_capacity",
        },
    }[kind]
    prefix = f"{kind}_"
    for index, entity in enumerate(entities):
        if set(entity) != allowed:
            raise ValueError(f"anonymous {kind} schema contains unsupported fields")
        token = str(entity["token"])
        if token != f"{prefix}{index:04d}":
            raise ValueError(f"anonymous {kind} token is not ordinal")
        lowered_keys = {str(key).lower() for key in entity}
        if any("truth" in key or "actor" in key for key in lowered_keys):
            raise ValueError("truth and actor identity fields are forbidden")


def _hard_reject_counts(
    reject_reasons: Sequence[Sequence[str | None]],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in reject_reasons:
        for reason in row:
            if reason is not None:
                counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items()))


def _squash_nonnegative(value: Any) -> float:
    number = max(0.0, float(value))
    return number / (1.0 + number)
