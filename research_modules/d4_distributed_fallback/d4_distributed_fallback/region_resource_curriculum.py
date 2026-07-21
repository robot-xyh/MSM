"""Deterministic action-coverage curriculum for D4 regional learning.

The curriculum is a separate, truth-free development dataset.  It exercises
the existing rule policy and deterministic projector, then binds the generated
episodes to the shared canonical seed registry through a read-only view.  It
does not alter formal scalable-simulation data, produce rewards, enable PPO,
or authorize online assist.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .canonical_seed_split import (
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
    CanonicalRegionLearningDatasetView,
    audit_canonical_region_learning_split_view,
    load_canonical_region_learning_split_view,
)
from .region_resource import (
    DeterministicResourceProjector,
    RegionResourceEdge,
    RegionResourceNode,
    RegionResourceRecommendation,
    RegionResourceSnapshot,
    RuleRegionResourcePolicy,
)
from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningAvailability,
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningReward,
    RegionLearningSplit,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    stage_region_learning_episode,
)
from .regional_failover import RegionalAuthorityLayer


REGION_ACTION_COVERAGE_CURRICULUM_SCHEMA = (
    "d4-region-action-coverage-curriculum-v1"
)
REGION_ACTION_COVERAGE_CURRICULUM_VERSION = "v1"
REGION_ACTION_COVERAGE_AUDIT_SCHEMA = "d4-region-action-coverage-audit-v1"
REGION_ACTION_COVERAGE_SUMMARY_SCHEMA = "d4-region-action-coverage-summary-v1"
CURRICULUM_FRAME_KINDS = ("hold", "request_replan", "transfer")
CURRICULUM_REWARD_UNAVAILABLE_REASON = (
    "supplemental_curriculum_has_no_observed_outcome"
)

_FORBIDDEN_ONLINE_KEYS = {
    "actor_id",
    "actor_name",
    "actor_truth_id",
    "evaluator_truth",
    "evaluator_truth_id",
    "global_track_id",
    "object_id",
    "object_name",
    "object_truth_id",
    "offline_truth",
    "segmentation_id",
    "target_id",
    "target_truth_id",
    "truth_id",
}


class RegionActionCoverageCurriculumError(RuntimeError):
    """Fail-closed curriculum generation or validation error."""


@dataclass(frozen=True)
class RegionActionCoverageCurriculumConfig:
    """Scale-independent configuration for one deterministic curriculum."""

    region_count: int = 4
    resource_count: int = 17
    frame_interval_s: float = 1.0
    scenario_id: str = "d4-region-action-coverage-curriculum"
    scenario_version: str = REGION_ACTION_COVERAGE_CURRICULUM_VERSION

    def __post_init__(self) -> None:
        if int(self.region_count) < 2:
            raise ValueError("region_count must be at least two")
        if int(self.resource_count) < int(self.region_count) + 2:
            raise ValueError(
                "resource_count must leave at least two transferable resources"
            )
        if float(self.frame_interval_s) <= 0.0:
            raise ValueError("frame_interval_s must be positive")
        if not self.scenario_id or not self.scenario_version:
            raise ValueError("scenario identity must not be empty")

    @property
    def scenario_scale(self) -> str:
        return f"regions-{self.region_count}-resources-{self.resource_count}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REGION_ACTION_COVERAGE_CURRICULUM_SCHEMA,
            "version": REGION_ACTION_COVERAGE_CURRICULUM_VERSION,
            "region_count": int(self.region_count),
            "resource_count": int(self.resource_count),
            "frame_interval_s": float(self.frame_interval_s),
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "frame_kinds": list(CURRICULUM_FRAME_KINDS),
        }


@dataclass(frozen=True)
class GeneratedRegionActionCoverageCurriculum:
    output_dir: Path
    dataset: LoadedRegionLearningDataset
    canonical_view: CanonicalRegionLearningDatasetView
    summary: Mapping[str, Any]


def generate_region_action_coverage_curriculum(
    output_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    created_at_utc: str,
    source_git_commit: str,
    source_repository_dirty: bool,
    config: RegionActionCoverageCurriculumConfig | None = None,
    tracked_summary_path: str | Path | None = None,
) -> GeneratedRegionActionCoverageCurriculum:
    """Generate, freeze, canonicalize, and audit a separate curriculum.

    The destination must not exist.  All artifacts are assembled in a sibling
    temporary directory and published atomically only after every gate passes.
    """

    resolved = config or RegionActionCoverageCurriculumConfig()
    destination = Path(output_dir).resolve()
    source_registry_path = Path(training_seed_registry_path).resolve()
    shared_registry_path = Path(shared_seed_registry_path).resolve()
    if destination.exists():
        raise RegionActionCoverageCurriculumError(
            f"curriculum destination already exists: {destination}"
        )
    if not created_at_utc:
        raise ValueError("created_at_utc must not be empty")
    commit = str(source_git_commit).lower()
    if len(commit) not in {40, 64} or not _is_lower_hex(commit):
        raise ValueError("source_git_commit must be a full hexadecimal id")
    if type(source_repository_dirty) is not bool:
        raise ValueError("source_repository_dirty must be a boolean")

    seed_catalog = _load_training_seed_catalog(source_registry_path)
    training_seeds = seed_catalog["training_seeds"]
    reserved_seeds = seed_catalog["reserved_evaluation_seeds"]
    if set(training_seeds) & set(reserved_seeds):
        raise RegionActionCoverageCurriculumError(
            "training and reserved evaluation seeds overlap"
        )
    source_registry_sha256 = _sha256_file(source_registry_path)
    shared_registry_sha256 = _sha256_file(shared_registry_path)
    config_sha256 = _sha256_json(
        {
            "config": resolved.to_dict(),
            "training_seed_registry_sha256": source_registry_sha256,
            "shared_seed_registry_sha256": shared_registry_sha256,
        }
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-", dir=destination.parent
        )
    )
    try:
        staging_dir = temporary_root / "_staging"
        for seed in training_seeds:
            source = RegionLearningEpisodeSource(
                scenario_id=resolved.scenario_id,
                scenario_version=resolved.scenario_version,
                scenario_scale=resolved.scenario_scale,
                seed=int(seed),
                episode_id=f"{resolved.scenario_id}-seed-{int(seed):06d}",
                git_commit=commit,
                git_dirty=source_repository_dirty,
                config_sha256=config_sha256,
            )
            stage_region_learning_episode(
                staging_dir,
                source,
                build_region_action_coverage_frames(source, resolved),
            )

        dataset_dir = temporary_root / "dataset"
        finalize_region_learning_dataset(
            staging_dir,
            dataset_dir,
            created_at_utc=created_at_utc,
            split_seed=20260720,
            train_fraction=0.60,
            validation_fraction=0.20,
            minimum_unique_seeds=3,
            minimum_unseen_seeds=2,
        )
        shutil.rmtree(staging_dir)
        dataset = load_region_learning_dataset(dataset_dir)
        canonical_view = load_canonical_region_learning_split_view(
            dataset,
            shared_registry_path=shared_registry_path,
            training_seed_registry_path=source_registry_path,
            expected_training_seed_registry_sha256=source_registry_sha256,
        )
        summary = audit_region_action_coverage_curriculum(
            dataset,
            canonical_view=canonical_view,
            config=resolved,
            created_at_utc=created_at_utc,
            source_registry_sha256=source_registry_sha256,
            shared_registry_sha256=shared_registry_sha256,
            config_sha256=config_sha256,
        )
        _write_json(temporary_root / "canonical_split_view.json", summary["canonical"])
        _write_json(temporary_root / "curriculum_summary.json", summary)
        os.replace(temporary_root, destination)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    published_dataset = load_region_learning_dataset(destination / "dataset")
    published_view = load_canonical_region_learning_split_view(
        published_dataset,
        shared_registry_path=shared_registry_path,
        training_seed_registry_path=source_registry_path,
        expected_training_seed_registry_sha256=source_registry_sha256,
    )
    published_summary = _read_json(destination / "curriculum_summary.json")
    if tracked_summary_path is not None:
        _write_json(Path(tracked_summary_path), published_summary)
    return GeneratedRegionActionCoverageCurriculum(
        output_dir=destination,
        dataset=published_dataset,
        canonical_view=published_view,
        summary=published_summary,
    )


def build_region_action_coverage_frames(
    source: RegionLearningEpisodeSource,
    config: RegionActionCoverageCurriculumConfig,
) -> tuple[RegionLearningFrame, ...]:
    """Build one complete episode with hold, replan, and transfer targets."""

    policy = RuleRegionResourcePolicy()
    frames: list[RegionLearningFrame] = []
    for frame_index, frame_kind in enumerate(CURRICULUM_FRAME_KINDS):
        snapshot = _build_curriculum_snapshot(
            source,
            config,
            frame_index=frame_index,
            frame_kind=frame_kind,
        )
        recommendation = policy.recommend(snapshot)
        frames.append(
            RegionLearningFrame(
                frame_index=frame_index,
                timestamp_s=snapshot.timestamp_s,
                snapshot=snapshot,
                target=RegionLearningTarget.available(
                    RegionLearningTargetKind.RULE,
                    recommendation,
                ),
                reward=RegionLearningReward.unavailable(
                    CURRICULUM_REWARD_UNAVAILABLE_REASON
                ),
                recommendation=recommendation,
            )
        )
    return tuple(frames)


def audit_region_action_coverage_curriculum(
    dataset: LoadedRegionLearningDataset,
    *,
    canonical_view: CanonicalRegionLearningDatasetView,
    config: RegionActionCoverageCurriculumConfig,
    created_at_utc: str,
    source_registry_sha256: str,
    shared_registry_sha256: str,
    config_sha256: str,
) -> dict[str, Any]:
    """Audit action diversity, safety, truth isolation, and split governance."""

    canonical_view.assert_source(dataset)
    canonical_audit = audit_canonical_region_learning_split_view(canonical_view)
    all_frames = tuple(canonical_view.iter_frames())
    total_inventory = _action_inventory(all_frames)
    split_inventory = {
        split.value: _action_inventory(canonical_view.iter_frames(split))
        for split in RegionLearningSplit
    }
    hard_violations: list[str] = []
    truth_key_paths: list[str] = []
    projector = DeterministicResourceProjector()
    reward_available_count = 0
    reward_unavailable_count = 0
    for episode in canonical_view.episode_records:
        truth_key_paths.extend(
            _forbidden_key_paths(
                episode.source.to_dict(),
                path=f"episode:{episode.source.episode_id}:source",
            )
        )
        for frame in episode.frames:
            truth_key_paths.extend(
                _forbidden_key_paths(
                    frame.to_dict(),
                    path=(
                        f"episode:{episode.source.episode_id}:frame:{frame.frame_index}"
                    ),
                )
            )
            if (
                frame.reward.availability == RegionLearningAvailability.UNAVAILABLE
                and frame.reward.value is None
                and frame.reward.unavailable_reason
                == CURRICULUM_REWARD_UNAVAILABLE_REASON
            ):
                reward_unavailable_count += 1
            else:
                reward_available_count += 1
            recommendation = frame.target.recommendation
            if recommendation is None:
                hard_violations.append(
                    f"{episode.source.episode_id}:{frame.frame_index}:target_missing"
                )
                continue
            hard_violations.extend(
                _recommendation_safety_violations(
                    frame.snapshot,
                    recommendation,
                    projector=projector,
                    prefix=f"{episode.source.episode_id}:{frame.frame_index}",
                )
            )

    required_actions = (
        "hold_true_count",
        "request_replan_true_count",
        "resource_quota_nonzero_count",
        "transfer_count",
    )
    missing_coverage = [
        name for name in required_actions if total_inventory[name] <= 0
    ]
    split_missing_coverage = {
        split: [name for name in required_actions if inventory[name] <= 0]
        for split, inventory in split_inventory.items()
    }
    split_missing_coverage = {
        split: names for split, names in split_missing_coverage.items() if names
    }
    reserved = set(canonical_view.binding.reserved_evaluation_seeds)
    dataset_seeds = {int(item.source.seed) for item in canonical_view.episode_records}
    reserved_present = sorted(dataset_seeds & reserved)

    violations: list[str] = []
    if hard_violations:
        violations.append("hard_constraint_violation")
    if truth_key_paths:
        violations.append("online_truth_identifier_present")
    if missing_coverage or split_missing_coverage:
        violations.append("required_action_coverage_missing")
    if reward_available_count:
        violations.append("curriculum_reward_was_fabricated")
    if reserved_present:
        violations.append("reserved_evaluation_seed_present")
    if dataset.manifest.availability.ppo_available:
        violations.append("ppo_incorrectly_available")

    content = {
        "schema": REGION_ACTION_COVERAGE_SUMMARY_SCHEMA,
        "curriculum_schema": REGION_ACTION_COVERAGE_CURRICULUM_SCHEMA,
        "created_at_utc": created_at_utc,
        "purpose": "behavior_cloning_and_offline_shadow_evaluation_only",
        "config": config.to_dict(),
        "source_binding": {
            "training_seed_registry_schema": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
            "training_seed_registry_sha256": source_registry_sha256,
            "shared_seed_registry_schema": SHARED_SEED_SPLIT_SCHEMA_VERSION,
            "shared_seed_registry_sha256": shared_registry_sha256,
            "config_sha256": config_sha256,
        },
        "dataset": {
            "schema": dataset.manifest.schema,
            "dataset_sha256": dataset.manifest.dataset_sha256,
            "native_split_sha256": dataset.manifest.split.split_sha256,
            "episode_count": dataset.manifest.availability.episode_count,
            "frame_count": dataset.manifest.availability.frame_count,
            "numeric_seed_count": dataset.manifest.split.unique_seed_count,
            "dirty_episode_count": dataset.manifest.availability.dirty_episode_count,
        },
        "canonical": canonical_audit,
        "action_inventory": {
            "total": total_inventory,
            "by_canonical_split": split_inventory,
            "missing_required_actions": missing_coverage,
            "split_missing_required_actions": split_missing_coverage,
        },
        "safety": {
            "projector_required": True,
            "hard_constraint_violation_count": len(hard_violations),
            "hard_constraint_violations": hard_violations,
            "resource_conservation_verified": not hard_violations,
        },
        "truth_isolation": {
            "online_truth_identifier_count": len(truth_key_paths),
            "forbidden_key_paths": truth_key_paths,
            "reserved_evaluation_seed_count": len(reserved),
            "reserved_evaluation_seed_present_count": len(reserved_present),
            "reserved_evaluation_seeds_present": reserved_present,
        },
        "outcome_and_reward": {
            "outcome_availability": "unavailable",
            "reward_availability": "unavailable",
            "reward_available_count": reward_available_count,
            "reward_unavailable_count": reward_unavailable_count,
            "unavailable_reason": CURRICULUM_REWARD_UNAVAILABLE_REASON,
        },
        "admission": {
            "behavior_cloning_manifest_available": (
                dataset.manifest.availability.behavior_cloning_available
            ),
            "clean_source_required_for_behavior_cloning": True,
            "offline_shadow_evaluation_only": True,
            "ppo_available": False,
            "online_assist_available": False,
            "online_authority_available": False,
            "formal_900_episode_dataset_modified": False,
        },
        "audit": {
            "schema": REGION_ACTION_COVERAGE_AUDIT_SCHEMA,
            "passed": not violations,
            "violations": violations,
        },
    }
    summary = {**content, "content_sha256": _sha256_json(content)}
    if violations:
        raise RegionActionCoverageCurriculumError(
            "curriculum audit failed: " + ",".join(violations)
        )
    return summary


def _build_curriculum_snapshot(
    source: RegionLearningEpisodeSource,
    config: RegionActionCoverageCurriculumConfig,
    *,
    frame_index: int,
    frame_kind: str,
) -> RegionResourceSnapshot:
    if frame_kind not in CURRICULUM_FRAME_KINDS:
        raise ValueError(f"unsupported curriculum frame kind: {frame_kind}")
    region_ids = tuple(
        f"region-{index:03d}" for index in range(int(config.region_count))
    )
    balanced = _balanced_resource_allocation(
        config.resource_count, config.region_count
    )
    hold_index = int(source.seed) % config.region_count
    replan_index = (int(source.seed) + 1) % config.region_count
    transfer_source_index = (int(source.seed) + 2) % config.region_count
    transfer_target_index = (transfer_source_index + 1) % config.region_count
    resources = list(balanced)
    transfer_count = 0
    if frame_kind == "transfer":
        resources = [1] * config.region_count
        resources[transfer_source_index] += config.resource_count - config.region_count
        source_available = resources[transfer_source_index]
        reserve_floor = max(1, int(ceil(0.10 * source_available)))
        transfer_count = min(3, source_available - reserve_floor)
        if transfer_count <= 0:
            raise RegionActionCoverageCurriculumError(
                "configured scale cannot produce a safe transfer"
            )

    timestamp_s = float(frame_index) * float(config.frame_interval_s)
    nodes: list[RegionResourceNode] = []
    for index, region_id in enumerate(region_ids):
        available = int(resources[index])
        reserve = 1
        active_capacity = max(0, available - reserve)
        target_demand = float(active_capacity)
        if frame_kind == "transfer":
            target_demand = 0.0
            if index == transfer_target_index:
                target_demand = float(transfer_count)
        jitter = ((int(source.seed) * 17 + index * 7) % 11) / 100.0
        nodes.append(
            RegionResourceNode(
                region_id=region_id,
                target_demand=target_demand,
                high_threat_backlog=0.0,
                d1_uncertainty=0.10 + jitter,
                d2_uncertainty=0.08 + jitter / 2.0,
                d5_visibility=0.90 - jitter / 2.0,
                d5_consistency=0.92 - jitter / 2.0,
                available_resources=available,
                reserve_resources=reserve,
                committed_resources=0,
                secondary_coverage=0.90,
                secondary_readiness=0.90,
                communication_capacity=50.0,
                communication_latency_s=0.02,
                packet_loss_rate=0.01,
                current_owner_id="CENTER",
                current_owner_layer=RegionalAuthorityLayer.CENTER,
                plan_id=f"curriculum-plan-{int(source.seed):06d}",
                plan_version=1 + int(source.seed) % 7,
                epoch=1 + int(source.seed) % 5,
                lease_expires_at_s=timestamp_s + 120.0,
                assignment_conflict_count=(
                    1
                    if frame_kind == "request_replan" and index == replan_index
                    else 0
                ),
                degradation_failed=(
                    frame_kind == "hold" and index == hold_index
                ),
            )
        )
    edges = _ring_edges(
        region_ids,
        frame_kind=frame_kind,
        transfer_source_index=transfer_source_index,
        transfer_target_index=transfer_target_index,
        transfer_count=transfer_count,
    )
    return RegionResourceSnapshot(
        snapshot_id=(
            f"{source.episode_id}-frame-{frame_index:02d}-{frame_kind}"
        ),
        scenario_id=source.scenario_id,
        scenario_version=source.scenario_version,
        seed=source.seed,
        timestamp_s=timestamp_s,
        regions=tuple(nodes),
        edges=edges,
    )


def _ring_edges(
    region_ids: Sequence[str],
    *,
    frame_kind: str,
    transfer_source_index: int,
    transfer_target_index: int,
    transfer_count: int,
) -> tuple[RegionResourceEdge, ...]:
    pairs = (
        ((0, 1),)
        if len(region_ids) == 2
        else tuple((index, (index + 1) % len(region_ids)) for index in range(len(region_ids)))
    )
    edges: list[RegionResourceEdge] = []
    for edge_index, (source_index, target_index) in enumerate(pairs):
        transfer_edge = bool(
            frame_kind == "transfer"
            and source_index == transfer_source_index
            and target_index == transfer_target_index
        )
        partitioned = frame_kind == "request_replan"
        edges.append(
            RegionResourceEdge(
                source_region_id=region_ids[source_index],
                target_region_id=region_ids[target_index],
                transferable_resources=transfer_count if transfer_edge else 0,
                distance_m=500.0 + 25.0 * edge_index,
                transfer_time_s=10.0 + float(edge_index),
                bandwidth_mbps=20.0,
                communication_available=not partitioned,
                maneuver_available=True,
                partitioned=partitioned,
                bidirectional=True,
                edge_id=f"edge-{edge_index:03d}",
            )
        )
    return tuple(edges)


def _balanced_resource_allocation(
    resource_count: int, region_count: int
) -> tuple[int, ...]:
    quotient, remainder = divmod(int(resource_count), int(region_count))
    return tuple(
        quotient + (1 if index < remainder else 0)
        for index in range(int(region_count))
    )


def _action_inventory(frames: Iterable[RegionLearningFrame]) -> dict[str, int]:
    frame_count = 0
    action_count = 0
    hold_true_count = 0
    request_replan_true_count = 0
    resource_quota_nonzero_count = 0
    transfer_count = 0
    transferred_resource_count = 0
    for frame in frames:
        frame_count += 1
        recommendation = frame.target.recommendation
        if recommendation is None:
            continue
        action_count += len(recommendation.actions)
        hold_true_count += sum(action.hold for action in recommendation.actions)
        request_replan_true_count += sum(
            action.request_replan for action in recommendation.actions
        )
        resource_quota_nonzero_count += sum(
            action.resource_quota_delta != 0 for action in recommendation.actions
        )
        transfer_count += len(recommendation.transfers)
        transferred_resource_count += sum(
            transfer.resource_count for transfer in recommendation.transfers
        )
    return {
        "frame_count": frame_count,
        "action_count": action_count,
        "hold_true_count": hold_true_count,
        "request_replan_true_count": request_replan_true_count,
        "resource_quota_nonzero_count": resource_quota_nonzero_count,
        "transfer_count": transfer_count,
        "transferred_resource_count": transferred_resource_count,
    }


def _recommendation_safety_violations(
    snapshot: RegionResourceSnapshot,
    recommendation: RegionResourceRecommendation,
    *,
    projector: DeterministicResourceProjector,
    prefix: str,
) -> list[str]:
    violations: list[str] = []
    if not recommendation.projected:
        violations.append(f"{prefix}:recommendation_not_projected")
    if recommendation.total_quota_delta != 0:
        violations.append(f"{prefix}:resource_quota_not_conserved")
    if {action.region_id for action in recommendation.actions} != {
        node.region_id for node in snapshot.regions
    }:
        violations.append(f"{prefix}:region_action_inventory_mismatch")
    advisory = projector.build_advisory_contract(snapshot, recommendation)
    violations.extend(
        f"{prefix}:{reason}" for reason in advisory.publication_rejections
    )
    return violations


def _load_training_seed_catalog(path: Path) -> dict[str, tuple[int, ...]]:
    payload = _read_json(path)
    if payload.get("schema_version") != TRAINING_SEED_REGISTRY_SCHEMA_VERSION:
        raise RegionActionCoverageCurriculumError(
            "unsupported training seed registry schema"
        )
    training = _canonical_seed_tuple(payload.get("training_seeds"), "training_seeds")
    reserved = _canonical_seed_tuple(
        payload.get("reserved_evaluation_seeds"),
        "reserved_evaluation_seeds",
        allow_empty=True,
    )
    if int(payload.get("training_seed_count", -1)) != len(training):
        raise RegionActionCoverageCurriculumError("training seed count mismatch")
    if int(payload.get("reserved_evaluation_seed_count", -1)) != len(reserved):
        raise RegionActionCoverageCurriculumError("reserved seed count mismatch")
    if set(training) & set(reserved) or int(payload.get("overlap_count", -1)) != 0:
        raise RegionActionCoverageCurriculumError(
            "training and reserved evaluation seeds overlap"
        )
    return {
        "training_seeds": training,
        "reserved_evaluation_seeds": reserved,
    }


def _canonical_seed_tuple(
    value: Any, name: str, *, allow_empty: bool = False
) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise RegionActionCoverageCurriculumError(f"{name} must be a list")
    if any(type(item) is not int or item < 0 for item in value):
        raise RegionActionCoverageCurriculumError(
            f"{name} must contain non-negative integers"
        )
    result = tuple(value)
    if result != tuple(sorted(set(result))):
        raise RegionActionCoverageCurriculumError(
            f"{name} must be sorted and unique"
        )
    if not result and not allow_empty:
        raise RegionActionCoverageCurriculumError(f"{name} must not be empty")
    return result


def _forbidden_key_paths(value: Any, *, path: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized in _FORBIDDEN_ONLINE_KEYS
                or normalized.startswith("truth_")
                or normalized.endswith("_truth_id")
                or normalized.endswith("_global_track_id")
                or normalized.endswith("_target_id")
                or normalized.endswith("_object_id")
                or normalized.endswith("_actor_name")
                or "evaluator_truth" in normalized
                or "offline_truth" in normalized
            ):
                found.append(f"{path}.{key}")
            found.extend(_forbidden_key_paths(item, path=f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found.extend(_forbidden_key_paths(item, path=f"{path}[{index}]"))
    return found


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegionActionCoverageCurriculumError(
            f"invalid JSON artifact: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise RegionActionCoverageCurriculumError(
            f"JSON artifact must be an object: {path}"
        )
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(serialized, encoding="utf-8")
    os.replace(temporary, path)


def _sha256_json(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_lower_hex(value: str) -> bool:
    return bool(value) and all(character in "0123456789abcdef" for character in value)
