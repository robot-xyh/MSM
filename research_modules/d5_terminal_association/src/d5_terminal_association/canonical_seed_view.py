"""Strict read-only canonical seed views for D5 learning datasets.

The detached view binds an immutable D5 dataset to main's shared numeric-seed
registry.  It changes only the in-memory split label of complete episodes.  It
never rewrites source manifests, graph archives, online streams, or evaluator
labels.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .active_vision_episode_dataset import (
    ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
    LazyActiveVisionEpisodeDataset,
    load_active_vision_episode_dataset_lazy,
)
from .tracklet_dataset import (
    DATASET_SCHEMA_VERSION,
    LoadedTrackletDataset,
    LoadedTrackletEpisode,
    load_tracklet_dataset,
)


CANONICAL_SEED_VIEW_SCHEMA_VERSION = "d5.canonical-seed-split-view.v1"
CANONICAL_SEED_READINESS_SCHEMA_VERSION = "d5.canonical-seed-readiness.v1"
TRACKLET_VIEW_CONSUMER_SCHEMA_VERSION = "d5.tracklet-canonical-view-consumer.v1"
ACTIVE_VISION_VIEW_CONSUMER_SCHEMA_VERSION = (
    "d5.active-vision-canonical-view-consumer.v1"
)
SHARED_SEED_SPLIT_SCHEMA_VERSION = "scalable3d-shared-seed-split-registry-v1"
SHARED_SEED_SPLIT_POLICY_VERSION = "scalable3d-numeric-seed-atomic-split-v1"
TRAINING_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-training-seed-registry-v1"
ORDERING_COMPATIBILITY_VERSION = "d3_numeric_seed_atomic_split_v2"

VALIDATION_DATE = "2026-07-21"
EXPECTED_SPLIT_SEED = 20260720
EXPECTED_VALIDATION_FRACTION = 0.20
EXPECTED_TEST_FRACTION = 0.20
EXPECTED_MINIMUM_TEST_SEED_COUNT = 20
EXPECTED_UNIT = "numeric_seed_atomic_across_modules_scenarios_and_scales"
EXPECTED_CONSUMER_CONTRACT = {
    "original_dataset_mutation_allowed": False,
    "module_local_split_override_allowed": False,
    "cross_module_training_requires_exact_registry": True,
    "reserved_evaluation_seeds_allowed": False,
}

_SPLITS = ("train", "validation", "test")
_SOURCE_REGISTRY_KEYS = {
    "schema_version",
    "git_commit",
    "repository_dirty",
    "schedule_sha256",
    "training_seed_count",
    "training_seeds",
    "reserved_evaluation_seed_count",
    "reserved_evaluation_seeds",
    "overlap_count",
}
_SHARED_REGISTRY_KEYS = {
    "schema_version",
    "policy_version",
    "ordering_compatibility_version",
    "source",
    "unit",
    "split_seed",
    "validation_fraction",
    "test_fraction",
    "minimum_test_seed_count",
    "training_seed_count",
    "reserved_evaluation_seed_count",
    "reserved_evaluation_seeds",
    "training_reserved_overlap_count",
    "split_seed_values",
    "assignments",
    "assignment_sha256",
    "consumer_contract",
    "content_sha256",
}
_SHARED_SOURCE_KEYS = {
    "training_seed_registry_schema_version",
    "training_seed_registry_sha256",
    "git_commit",
    "repository_dirty",
    "schedule_sha256",
}
_VIEW_KEYS = {
    "schema_version",
    "validation_date",
    "consumer",
    "consumer_schema_version",
    "source",
    "training_seed_registry",
    "shared_seed_registry",
    "canonical_split",
    "view_contract",
    "content_sha256",
}


class CanonicalSeedViewError(ValueError):
    """Stable fail-closed error at the D5 canonical split boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def write_tracklet_canonical_seed_view(
    dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    view_manifest_path: str | Path,
) -> tuple[LoadedTrackletDataset, dict[str, Any], str]:
    """Validate the source and write a detached tracklet split view."""

    source = load_tracklet_dataset(dataset_dir)
    payload, assignment = _build_tracklet_view_payload(
        source,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )
    view_sha256 = _write_detached_view(
        payload,
        view_manifest_path,
        source_root=source.root,
    )
    return _apply_tracklet_view(source, payload, assignment, view_sha256), payload, view_sha256


def load_tracklet_canonical_seed_view(
    dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    view_manifest_path: str | Path,
) -> LoadedTrackletDataset:
    """Strictly load a tracklet dataset through an existing detached view."""

    source = load_tracklet_dataset(dataset_dir)
    expected, assignment = _build_tracklet_view_payload(
        source,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )
    _assert_detached_path(view_manifest_path, source.root)
    actual, view_sha256 = _load_detached_view(view_manifest_path)
    _expect_equal(actual, expected, "view_manifest_mismatch")
    return _apply_tracklet_view(source, actual, assignment, view_sha256)


def write_active_vision_canonical_seed_view(
    dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    view_manifest_path: str | Path,
) -> tuple[LazyActiveVisionEpisodeDataset, dict[str, Any], str]:
    """Validate the source and write a detached active-vision split view."""

    source = load_active_vision_episode_dataset_lazy(dataset_dir)
    payload, assignment = _build_active_vision_view_payload(
        source,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )
    view_sha256 = _write_detached_view(
        payload,
        view_manifest_path,
        source_root=source.root,
    )
    return _apply_active_vision_view(source, payload, assignment, view_sha256), payload, view_sha256


def load_active_vision_canonical_seed_view(
    dataset_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    view_manifest_path: str | Path,
) -> LazyActiveVisionEpisodeDataset:
    """Strictly load active-vision episodes through an existing detached view."""

    source = load_active_vision_episode_dataset_lazy(dataset_dir)
    expected, assignment = _build_active_vision_view_payload(
        source,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )
    _assert_detached_path(view_manifest_path, source.root)
    actual, view_sha256 = _load_detached_view(view_manifest_path)
    _expect_equal(actual, expected, "view_manifest_mismatch")
    return _apply_active_vision_view(source, actual, assignment, view_sha256)


def canonical_view_binding(dataset: Any) -> dict[str, Any] | None:
    """Return the verified canonical binding exposed by a loaded view."""

    manifest = getattr(dataset, "manifest", None)
    if not isinstance(manifest, Mapping):
        return None
    value = manifest.get("canonical_seed_view")
    return _plain_json(value) if isinstance(value, Mapping) else None


def tracklet_canonical_readiness(
    dataset: LoadedTrackletDataset,
    *,
    view_manifest: Mapping[str, Any],
    view_manifest_sha256: str,
) -> dict[str, Any]:
    """Run the existing graph readiness gates over canonical split buckets."""

    from .tracklet_training_audit import audit_tracklet_training_readiness

    readiness = audit_tracklet_training_readiness(dataset)
    return {
        "schema_version": CANONICAL_SEED_READINESS_SCHEMA_VERSION,
        "validation_date": VALIDATION_DATE,
        "consumer": "tracklet_graph",
        "view_manifest_sha256": view_manifest_sha256,
        "view_content_sha256": view_manifest["content_sha256"],
        "source_manifest_sha256": view_manifest["source"]["manifest_sha256"],
        "canonical_split": view_manifest["canonical_split"],
        "split_alignment": {
            "status": "pass",
            "joint_training_split_identity_aligned": True,
            "source_manifest_modified": False,
        },
        "training_readiness": readiness["training_readiness"],
        "promotion_readiness": readiness["promotion_readiness"],
        "edge_coverage": readiness["edge_coverage"],
        "split_summaries": readiness["split_summaries"],
        "remaining_blockers": [
            "edge_free_ratio_above_training_gate",
            "negative_candidate_edges_below_training_and_promotion_gates",
            "candidate_recall_not_fully_evaluable",
            "scenario_scale_dual_class_coverage_insufficient",
        ],
        "admission": {
            "g1_assist_eligible": False,
            "status": "fail_closed",
            "deterministic_geometry_fallback_required": True,
        },
    }


def active_vision_canonical_readiness(
    dataset: LazyActiveVisionEpisodeDataset,
    *,
    view_manifest: Mapping[str, Any],
    view_manifest_sha256: str,
    prior_bc_summary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Report split readiness without treating behavior observations as reward."""

    prior: dict[str, Any] | None = None
    prior_sha256: str | None = None
    if prior_bc_summary_path is not None:
        prior_path = Path(prior_bc_summary_path)
        prior = _read_json_object(prior_path, "prior_bc_summary")
        prior_sha256 = _sha256_file(prior_path)
        prior_dataset = prior.get("dataset")
        if not isinstance(prior_dataset, Mapping):
            _fail("prior_bc_summary_dataset_missing", "prior BC summary has no dataset binding")
        _expect_equal(
            prior_dataset.get("manifest_sha256"),
            view_manifest["source"]["manifest_sha256"],
            "prior_bc_summary_source_mismatch",
        )

    data_audit = prior.get("data_audit", {}) if prior is not None else {}
    class_imbalance = data_audit.get("class_imbalance")
    generalization_risks = list(data_audit.get("generalization_risks", ()))
    if not generalization_risks:
        generalization_risks = [
            "behavior_class_balance_requires_bound_full_sample_audit",
            "applied_action_ack_coverage_requires_bound_full_sample_audit",
        ]
    availability = dataset.manifest["availability"]
    reward_blockers = [
        f"{name}_unavailable"
        for name in ("reward", "counterfactual", "causal_label")
        if availability[name]["status"] != "available"
    ]
    return {
        "schema_version": CANONICAL_SEED_READINESS_SCHEMA_VERSION,
        "validation_date": VALIDATION_DATE,
        "consumer": "active_vision",
        "view_manifest_sha256": view_manifest_sha256,
        "view_content_sha256": view_manifest["content_sha256"],
        "source_manifest_sha256": view_manifest["source"]["manifest_sha256"],
        "canonical_split": view_manifest["canonical_split"],
        "prior_behavior_cloning_evidence": {
            "available": prior is not None,
            "file_sha256": prior_sha256,
            "class_imbalance": class_imbalance,
            "intent_counts": data_audit.get("intent_counts"),
            "generalization_risks": generalization_risks,
        },
        "offline_label_availability": availability,
        "split_alignment": {
            "status": "pass",
            "joint_training_split_identity_aligned": True,
            "source_manifest_modified": False,
            "scope": "split_identity_only",
        },
        "remaining_blockers": [
            *generalization_risks,
            "no_applied_action_runtime_ack_attribution",
            *reward_blockers,
            "no_paired_shadow_non_degradation_evidence",
        ],
        "admission": {
            "behavior_cloning_view_available": True,
            "status": "development_shadow_only",
            "assist": False,
            "ppo": False,
            "rule_fallback_required": True,
        },
    }


def write_canonical_readiness(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> tuple[str, str]:
    """Write tracked JSON and concise Chinese readiness evidence."""

    json_file = Path(json_path)
    markdown_file = Path(markdown_path)
    _write_json_atomic(json_file, report)
    _write_text_atomic(markdown_file, _readiness_markdown(report))
    return _sha256_file(json_file), _sha256_file(markdown_file)


def _build_tracklet_view_payload(
    source: LoadedTrackletDataset,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
) -> tuple[dict[str, Any], dict[int, str]]:
    _expect_equal(
        source.manifest.get("schema_version"),
        DATASET_SCHEMA_VERSION,
        "tracklet_source_schema_mismatch",
    )
    assignment, registry = _load_registry_binding(
        training_seed_registry_path,
        shared_seed_registry_path,
    )
    episodes = tuple(source.episodes)
    descriptor_by_uid = _descriptor_by_uid(source.manifest)
    if len(descriptor_by_uid) != len(episodes):
        _fail("source_episode_inventory_mismatch", "tracklet descriptor count changed")
    episode_uids = [episode.graph.episode_uid for episode in episodes]
    _require_unique(episode_uids, "source_episode_duplicate")
    seeds = _validate_dataset_seed_coverage(
        (episode.graph.seed for episode in episodes),
        registry=registry,
    )
    canonical_descriptors = [
        _rebucket_descriptor(descriptor_by_uid[episode.graph.episode_uid], assignment)
        for episode in episodes
    ]
    source_content_sha256 = _source_content_sha256(source.manifest)
    split_sha256 = _canonical_split_sha256(canonical_descriptors)
    training_set_sha256 = _canonical_training_set_sha256(
        canonical_descriptors,
        consumer="tracklet_graph",
    )
    class_balance = {
        split: {
            name: sum(
                episode.class_balance[name]
                for episode in episodes
                if assignment[episode.graph.seed] == split
            )
            for name in (
                "candidate_edges",
                "positive_candidate_edges",
                "negative_candidate_edges",
                "unlabeled_candidate_edges",
            )
        }
        for split in _SPLITS
    }
    canonical_counts = {
        "episode_counts": _counts_by_split(
            (assignment[episode.graph.seed] for episode in episodes)
        ),
        "node_counts": {
            split: sum(
                episode.graph.node_count
                for episode in episodes
                if assignment[episode.graph.seed] == split
            )
            for split in _SPLITS
        },
        "candidate_edge_counts": {
            split: sum(
                episode.graph.edge_count
                for episode in episodes
                if assignment[episode.graph.seed] == split
            )
            for split in _SPLITS
        },
        "class_balance_by_split": class_balance,
    }
    source_schema_versions = {
        key: source.manifest[key]
        for key in (
            "schema_version",
            "graph_schema_version",
            "evaluator_label_schema_version",
            "node_feature_version",
            "edge_feature_version",
        )
    }
    payload = _view_payload(
        consumer="tracklet_graph",
        consumer_schema_version=TRACKLET_VIEW_CONSUMER_SCHEMA_VERSION,
        source_schema_versions=source_schema_versions,
        source_manifest_sha256=source.manifest_sha256,
        source_content_sha256=source_content_sha256,
        source_split_sha256=str(source.manifest["split_sha256"]),
        source_training_set_sha256=str(source.manifest["training_set_sha256"]),
        episode_count=len(episodes),
        seeds=seeds,
        canonical_descriptors=canonical_descriptors,
        canonical_counts=canonical_counts,
        canonical_split_sha256=split_sha256,
        canonical_training_set_sha256=training_set_sha256,
        registry=registry,
    )
    return payload, assignment


def _build_active_vision_view_payload(
    source: LazyActiveVisionEpisodeDataset,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
) -> tuple[dict[str, Any], dict[int, str]]:
    _expect_equal(
        source.manifest.get("schema_version"),
        ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
        "active_vision_source_schema_mismatch",
    )
    assignment, registry = _load_registry_binding(
        training_seed_registry_path,
        shared_seed_registry_path,
    )
    descriptors = tuple(source.episode_descriptors)
    episode_uids = [str(item["episode_uid"]) for item in descriptors]
    _require_unique(episode_uids, "source_episode_duplicate")
    seeds = _validate_dataset_seed_coverage(
        (int(item["seed"]) for item in descriptors),
        registry=registry,
    )
    canonical_descriptors = [
        _rebucket_descriptor(item, assignment) for item in descriptors
    ]
    source_content_sha256 = _source_content_sha256(source.manifest)
    split_sha256 = _canonical_split_sha256(canonical_descriptors)
    training_set_sha256 = _canonical_training_set_sha256(
        canonical_descriptors,
        consumer="active_vision",
    )
    canonical_counts = {
        "episode_counts": _counts_by_split(
            (assignment[int(item["seed"])] for item in descriptors)
        ),
        "sample_counts": {
            split: sum(
                int(item["sample_count"])
                for item in descriptors
                if assignment[int(item["seed"])] == split
            )
            for split in _SPLITS
        },
    }
    source_schema_versions = {
        key: source.manifest[key]
        for key in (
            "schema_version",
            "episode_descriptor_schema_version",
            "episode_record_schema_version",
            "sample_schema_version",
            "snapshot_schema_version",
            "action_schema_version",
            "camera_feedback_schema_version",
            "runtime_ack_schema_version",
            "offline_labels_schema_version",
            "offline_label_schema_version",
        )
    }
    payload = _view_payload(
        consumer="active_vision",
        consumer_schema_version=ACTIVE_VISION_VIEW_CONSUMER_SCHEMA_VERSION,
        source_schema_versions=source_schema_versions,
        source_manifest_sha256=source.manifest_sha256,
        source_content_sha256=source_content_sha256,
        source_split_sha256=str(source.manifest["split_sha256"]),
        source_training_set_sha256=str(source.manifest["training_set_sha256"]),
        episode_count=len(descriptors),
        seeds=seeds,
        canonical_descriptors=canonical_descriptors,
        canonical_counts=canonical_counts,
        canonical_split_sha256=split_sha256,
        canonical_training_set_sha256=training_set_sha256,
        registry=registry,
    )
    return payload, assignment


def _view_payload(
    *,
    consumer: str,
    consumer_schema_version: str,
    source_schema_versions: Mapping[str, Any],
    source_manifest_sha256: str,
    source_content_sha256: str,
    source_split_sha256: str,
    source_training_set_sha256: str,
    episode_count: int,
    seeds: tuple[int, ...],
    canonical_descriptors: Sequence[Mapping[str, Any]],
    canonical_counts: Mapping[str, Any],
    canonical_split_sha256: str,
    canonical_training_set_sha256: str,
    registry: Mapping[str, Any],
) -> dict[str, Any]:
    split_values = registry["shared"]["split_seed_values"]
    reassigned = sum(
        str(item["split"]) != str(item["source_split"])
        for item in canonical_descriptors
    )
    payload: dict[str, Any] = {
        "schema_version": CANONICAL_SEED_VIEW_SCHEMA_VERSION,
        "validation_date": VALIDATION_DATE,
        "consumer": consumer,
        "consumer_schema_version": consumer_schema_version,
        "source": {
            "schema_versions": _plain_json(source_schema_versions),
            "manifest_sha256": _require_sha256(
                source_manifest_sha256, "source_manifest_sha256"
            ),
            "content_sha256": _require_sha256(
                source_content_sha256, "source_content_sha256"
            ),
            "split_sha256": _require_sha256(
                source_split_sha256, "source_split_sha256"
            ),
            "training_set_sha256": _require_sha256(
                source_training_set_sha256, "source_training_set_sha256"
            ),
            "episode_count": int(episode_count),
            "unique_seed_count": len(seeds),
        },
        "training_seed_registry": {
            "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
            "file_sha256": registry["training_file_sha256"],
        },
        "shared_seed_registry": {
            "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
            "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
            "file_sha256": registry["shared_file_sha256"],
            "content_sha256": registry["shared"]["content_sha256"],
            "assignment_sha256": registry["shared"]["assignment_sha256"],
        },
        "canonical_split": {
            "unit": EXPECTED_UNIT,
            "split_seed": EXPECTED_SPLIT_SEED,
            "seed_values": _plain_json(split_values),
            "seed_counts": {name: len(split_values[name]) for name in _SPLITS},
            **_plain_json(canonical_counts),
            "split_sha256": canonical_split_sha256,
            "training_set_sha256": canonical_training_set_sha256,
            "reassigned_episode_count": reassigned,
            "reserved_evaluation_seed_overlap": [],
        },
        "view_contract": {
            "source_manifest_modified": False,
            "source_artifacts_modified": False,
            "complete_episode_rebucket_only": True,
            "sample_copy_allowed": False,
            "online_offline_content_rewrite_allowed": False,
            "default_legacy_loader_unchanged": True,
        },
    }
    payload["content_sha256"] = _sha256_json(payload)
    return payload


def _apply_tracklet_view(
    source: LoadedTrackletDataset,
    payload: Mapping[str, Any],
    assignment: Mapping[int, str],
    view_manifest_sha256: str,
) -> LoadedTrackletDataset:
    episodes = tuple(
        LoadedTrackletEpisode(
            graph=item.graph,
            evaluator_labels=item.evaluator_labels,
            split=assignment[item.graph.seed],
            graph_sha256=item.graph_sha256,
            labels_sha256=item.labels_sha256,
            class_balance=item.class_balance,
            hard_negative_provenance=item.hard_negative_provenance,
        )
        for item in source.episodes
    )
    effective = _effective_manifest(source.manifest, payload, view_manifest_sha256)
    return LoadedTrackletDataset(
        root=source.root,
        manifest=MappingProxyType(effective),
        manifest_sha256=view_manifest_sha256,
        episodes=episodes,
    )


def _apply_active_vision_view(
    source: LazyActiveVisionEpisodeDataset,
    payload: Mapping[str, Any],
    assignment: Mapping[int, str],
    view_manifest_sha256: str,
) -> LazyActiveVisionEpisodeDataset:
    descriptors = tuple(
        _rebucket_descriptor(item, assignment, include_source_split=False)
        for item in source.episode_descriptors
    )
    return LazyActiveVisionEpisodeDataset(
        root=source.root,
        manifest=_effective_manifest(source.manifest, payload, view_manifest_sha256),
        manifest_sha256=view_manifest_sha256,
        episode_descriptors=descriptors,
    )


def _effective_manifest(
    source_manifest: Mapping[str, Any],
    view_manifest: Mapping[str, Any],
    view_manifest_sha256: str,
) -> dict[str, Any]:
    effective = _plain_json(source_manifest)
    assignment = {
        int(seed): split
        for split, seeds in view_manifest["canonical_split"]["seed_values"].items()
        for seed in seeds
    }
    if isinstance(effective.get("episodes"), list):
        effective["episodes"] = [
            _rebucket_descriptor(item, assignment, include_source_split=False)
            for item in effective["episodes"]
        ]
    effective["split_sha256"] = view_manifest["canonical_split"]["split_sha256"]
    effective["training_set_sha256"] = view_manifest["canonical_split"][
        "training_set_sha256"
    ]
    effective["canonical_seed_view"] = {
        "schema_version": view_manifest["schema_version"],
        "consumer_schema_version": view_manifest["consumer_schema_version"],
        "validation_date": view_manifest["validation_date"],
        "view_manifest_sha256": view_manifest_sha256,
        "content_sha256": view_manifest["content_sha256"],
        "source": view_manifest["source"],
        "training_seed_registry": view_manifest["training_seed_registry"],
        "shared_seed_registry": view_manifest["shared_seed_registry"],
        "canonical_split": view_manifest["canonical_split"],
        "view_contract": view_manifest["view_contract"],
    }
    return effective


def _load_registry_binding(
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
) -> tuple[dict[int, str], dict[str, Any]]:
    training_path = Path(training_seed_registry_path)
    shared_path = Path(shared_seed_registry_path)
    training_payload = _read_json_object(training_path, "training_seed_registry")
    training_file_sha256 = _sha256_file(training_path)
    training = _validate_training_seed_registry(training_payload)
    shared_payload = _read_json_object(shared_path, "shared_seed_registry")
    assignment = _validate_shared_registry(
        shared_payload,
        training=training,
        training_file_sha256=training_file_sha256,
    )
    return assignment, {
        "training": training,
        "training_file_sha256": training_file_sha256,
        "shared": shared_payload,
        "shared_file_sha256": _sha256_file(shared_path),
    }


def _validate_training_seed_registry(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != _SOURCE_REGISTRY_KEYS:
        _fail("training_registry_fields_mismatch", "training registry fields changed")
    _expect_equal(
        value.get("schema_version"),
        TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "training_registry_schema_mismatch",
    )
    training = _canonical_seed_catalog(value.get("training_seeds"), "training_seeds")
    reserved = _canonical_seed_catalog(
        value.get("reserved_evaluation_seeds"),
        "reserved_evaluation_seeds",
        allow_empty=True,
    )
    _expect_equal(
        _integer(value.get("training_seed_count"), "training_seed_count"),
        len(training),
        "training_seed_count_mismatch",
    )
    _expect_equal(
        _integer(
            value.get("reserved_evaluation_seed_count"),
            "reserved_evaluation_seed_count",
        ),
        len(reserved),
        "reserved_seed_count_mismatch",
    )
    overlap = sorted(set(training) & set(reserved))
    if overlap or _integer(value.get("overlap_count"), "overlap_count") != 0:
        _fail("training_reserved_seed_overlap", f"overlap={overlap}")
    commit = str(value.get("git_commit", ""))
    if len(commit) != 40 or not _is_lower_hex(commit):
        _fail("training_registry_git_commit_invalid", "invalid Git commit binding")
    if type(value.get("repository_dirty")) is not bool:
        _fail("training_registry_dirty_flag_invalid", "repository_dirty must be boolean")
    schedule = value.get("schedule_sha256")
    if schedule is not None:
        _require_sha256(schedule, "schedule_sha256")
    return {
        "training_seeds": training,
        "reserved_seeds": reserved,
        "git_commit": commit,
        "repository_dirty": value["repository_dirty"],
        "schedule_sha256": schedule,
    }


def _validate_shared_registry(
    value: Mapping[str, Any],
    *,
    training: Mapping[str, Any],
    training_file_sha256: str,
) -> dict[int, str]:
    if set(value) != _SHARED_REGISTRY_KEYS:
        _fail("shared_registry_fields_mismatch", "shared registry fields changed")
    _expect_equal(
        value.get("schema_version"),
        SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "shared_registry_schema_mismatch",
    )
    _expect_equal(
        value.get("policy_version"),
        SHARED_SEED_SPLIT_POLICY_VERSION,
        "shared_registry_policy_mismatch",
    )
    _expect_equal(
        value.get("ordering_compatibility_version"),
        ORDERING_COMPATIBILITY_VERSION,
        "ordering_compatibility_mismatch",
    )
    _expect_equal(value.get("unit"), EXPECTED_UNIT, "shared_registry_unit_mismatch")
    _expect_equal(
        _integer(value.get("split_seed"), "split_seed"),
        EXPECTED_SPLIT_SEED,
        "split_seed_mismatch",
    )
    _expect_equal(
        _number(value.get("validation_fraction"), "validation_fraction"),
        EXPECTED_VALIDATION_FRACTION,
        "validation_fraction_mismatch",
    )
    _expect_equal(
        _number(value.get("test_fraction"), "test_fraction"),
        EXPECTED_TEST_FRACTION,
        "test_fraction_mismatch",
    )
    _expect_equal(
        _integer(value.get("minimum_test_seed_count"), "minimum_test_seed_count"),
        EXPECTED_MINIMUM_TEST_SEED_COUNT,
        "minimum_test_seed_count_mismatch",
    )
    _expect_equal(
        value.get("consumer_contract"),
        EXPECTED_CONSUMER_CONTRACT,
        "consumer_contract_mismatch",
    )
    content_sha256 = _require_sha256(value.get("content_sha256"), "content_sha256")
    unhashed = dict(value)
    unhashed.pop("content_sha256")
    _expect_equal(
        _sha256_json(unhashed),
        content_sha256,
        "shared_registry_content_sha256_mismatch",
    )
    source = value.get("source")
    if not isinstance(source, Mapping) or set(source) != _SHARED_SOURCE_KEYS:
        _fail("shared_registry_source_binding_invalid", "source binding fields changed")
    _expect_equal(
        source.get("training_seed_registry_schema_version"),
        TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "shared_registry_source_schema_mismatch",
    )
    _expect_equal(
        source.get("training_seed_registry_sha256"),
        training_file_sha256,
        "training_registry_sha256_mismatch",
    )
    for field in ("git_commit", "repository_dirty", "schedule_sha256"):
        _expect_equal(
            source.get(field),
            training[field],
            "training_registry_metadata_mismatch",
        )
    training_seeds = training["training_seeds"]
    reserved = training["reserved_seeds"]
    _expect_equal(
        _integer(value.get("training_seed_count"), "training_seed_count"),
        len(training_seeds),
        "shared_training_seed_count_mismatch",
    )
    _expect_equal(
        _integer(
            value.get("reserved_evaluation_seed_count"),
            "reserved_evaluation_seed_count",
        ),
        len(reserved),
        "shared_reserved_seed_count_mismatch",
    )
    _expect_equal(
        value.get("reserved_evaluation_seeds"),
        list(reserved),
        "shared_reserved_seed_catalog_mismatch",
    )
    _expect_equal(
        _integer(
            value.get("training_reserved_overlap_count"),
            "training_reserved_overlap_count",
        ),
        0,
        "shared_reserved_seed_overlap",
    )
    assignments = value.get("assignments")
    if not isinstance(assignments, list):
        _fail("shared_assignments_invalid", "assignments must be a list")
    _expect_equal(
        _sha256_json(assignments),
        _require_sha256(value.get("assignment_sha256"), "assignment_sha256"),
        "shared_assignment_sha256_mismatch",
    )
    assignment: dict[int, str] = {}
    assignment_order: list[int] = []
    for item in assignments:
        if not isinstance(item, Mapping) or set(item) != {"seed", "split"}:
            _fail("shared_assignment_record_invalid", "assignment fields changed")
        seed = _integer(item["seed"], "assignment.seed")
        split = str(item["split"])
        if split not in _SPLITS:
            _fail("shared_assignment_split_invalid", f"invalid split: {split}")
        if seed in assignment:
            _fail("shared_assignment_seed_duplicate", f"duplicate seed: {seed}")
        assignment[seed] = split
        assignment_order.append(seed)
    if assignment_order != list(training_seeds):
        _fail("shared_assignment_seed_catalog_mismatch", "assignment catalog changed")
    reserved_assigned = sorted(set(assignment) & set(reserved))
    if reserved_assigned:
        _fail("reserved_seed_assigned", f"reserved seeds assigned: {reserved_assigned}")
    expected_assignment = _canonical_assignment(training_seeds)
    _expect_equal(
        assignment,
        expected_assignment,
        "shared_assignment_policy_reproduction_mismatch",
    )
    split_values = value.get("split_seed_values")
    expected_values = {
        split: sorted(seed for seed, name in assignment.items() if name == split)
        for split in _SPLITS
    }
    _expect_equal(split_values, expected_values, "shared_split_seed_values_mismatch")
    _expect_equal(
        {split: len(expected_values[split]) for split in _SPLITS},
        {"train": 60, "validation": 20, "test": 20},
        "shared_split_count_mismatch",
    )
    return assignment


def _validate_dataset_seed_coverage(
    seeds: Any,
    *,
    registry: Mapping[str, Any],
) -> tuple[int, ...]:
    observed = tuple(sorted(set(int(seed) for seed in seeds)))
    expected = registry["training"]["training_seeds"]
    reserved = registry["training"]["reserved_seeds"]
    reserved_overlap = sorted(set(observed) & set(reserved))
    if reserved_overlap:
        _fail("reserved_seed_in_dataset", f"reserved seeds present: {reserved_overlap}")
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if missing or extra:
        _fail("dataset_seed_coverage_mismatch", f"missing={missing};extra={extra}")
    return observed


def _canonical_assignment(seeds: Sequence[int]) -> dict[int, str]:
    ordered = sorted(
        seeds,
        key=lambda seed: (
            hashlib.sha256(
                f"{ORDERING_COMPATIBILITY_VERSION}|{EXPECTED_SPLIT_SEED}\0{seed}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            seed,
        ),
    )
    test_count = max(1, min(len(seeds) - 2, round(len(seeds) * 0.20)))
    validation_count = max(
        1,
        min(len(seeds) - test_count - 1, round(len(seeds) * 0.20)),
    )
    if test_count < EXPECTED_MINIMUM_TEST_SEED_COUNT:
        _fail("insufficient_test_seeds", "canonical test split requires 20 seeds")
    return {
        seed: (
            "test"
            if index < test_count
            else "validation"
            if index < test_count + validation_count
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _descriptor_by_uid(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    descriptors = manifest.get("episodes")
    if not isinstance(descriptors, (list, tuple)):
        _fail("source_descriptors_missing", "source manifest has no episode descriptors")
    result: dict[str, Mapping[str, Any]] = {}
    for item in descriptors:
        if not isinstance(item, Mapping):
            _fail("source_descriptor_invalid", "source descriptor is not an object")
        uid = str(item.get("episode_uid", ""))
        if not uid or uid in result:
            _fail("source_episode_duplicate", f"duplicate or empty episode uid: {uid}")
        result[uid] = item
    return result


def _rebucket_descriptor(
    descriptor: Mapping[str, Any],
    assignment: Mapping[int, str],
    *,
    include_source_split: bool = True,
) -> dict[str, Any]:
    result = _plain_json(descriptor)
    source_split = str(result["split"])
    result["split"] = assignment[int(result["seed"])]
    if include_source_split:
        result["source_split"] = source_split
    return result


def _source_content_sha256(manifest: Mapping[str, Any]) -> str:
    payload = _plain_json(manifest)
    payload.pop("split_policy", None)
    payload.pop("split_sha256", None)
    payload.pop("training_set_sha256", None)
    descriptors = payload.get("episodes")
    if not isinstance(descriptors, list):
        _fail("source_descriptors_missing", "source manifest has no episode list")
    for item in descriptors:
        item.pop("split", None)
    payload["episodes"] = sorted(descriptors, key=lambda item: str(item["episode_uid"]))
    return _sha256_json(payload)


def _canonical_split_sha256(descriptors: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "scenario_version": str(item["scenario_version"]),
            "seed": int(item["seed"]),
            "split": str(item["split"]),
        }
        for item in descriptors
    ]
    return _sha256_json(sorted(payload, key=lambda item: item["episode_uid"]))


def _canonical_training_set_sha256(
    descriptors: Sequence[Mapping[str, Any]],
    *,
    consumer: str,
) -> str:
    hash_fields = (
        ("graph_sha256", "labels_sha256")
        if consumer == "tracklet_graph"
        else ("online_sha256", "offline_sha256")
    )
    payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "scenario_version": str(item["scenario_version"]),
            "seed": int(item["seed"]),
            **{field: str(item[field]) for field in hash_fields},
        }
        for item in descriptors
        if item["split"] == "train"
    ]
    return _sha256_json(sorted(payload, key=lambda item: item["episode_uid"]))


def _counts_by_split(values: Any) -> dict[str, int]:
    counts = Counter(str(value) for value in values)
    return {split: int(counts[split]) for split in _SPLITS}


def _write_detached_view(
    payload: Mapping[str, Any],
    output_path: str | Path,
    *,
    source_root: Path,
) -> str:
    output = Path(output_path).resolve()
    _assert_detached_path(output, source_root)
    _validate_view_payload(payload)
    if output.exists():
        existing = _read_json_object(output, "canonical_view_manifest")
        _expect_equal(existing, payload, "existing_view_conflict")
    else:
        _write_json_atomic(output, payload)
    return _sha256_file(output)


def _assert_detached_path(path: str | Path, source_root: str | Path) -> None:
    output = Path(path).resolve()
    source = Path(source_root).resolve()
    if output == source or source in output.parents:
        _fail("source_mutation_forbidden", "view manifest must be detached from source dataset")


def _load_detached_view(path: str | Path) -> tuple[dict[str, Any], str]:
    file_path = Path(path)
    payload = _read_json_object(file_path, "canonical_view_manifest")
    _validate_view_payload(payload)
    return payload, _sha256_file(file_path)


def _validate_view_payload(value: Mapping[str, Any]) -> None:
    if set(value) != _VIEW_KEYS:
        _fail("view_fields_mismatch", "canonical view fields changed")
    _expect_equal(
        value.get("schema_version"),
        CANONICAL_SEED_VIEW_SCHEMA_VERSION,
        "view_schema_mismatch",
    )
    _expect_equal(value.get("validation_date"), VALIDATION_DATE, "view_date_mismatch")
    content = _require_sha256(value.get("content_sha256"), "view_content_sha256")
    unhashed = _plain_json(value)
    unhashed.pop("content_sha256")
    _expect_equal(_sha256_json(unhashed), content, "view_content_sha256_mismatch")
    contract = value.get("view_contract")
    expected_contract = {
        "source_manifest_modified": False,
        "source_artifacts_modified": False,
        "complete_episode_rebucket_only": True,
        "sample_copy_allowed": False,
        "online_offline_content_rewrite_allowed": False,
        "default_legacy_loader_unchanged": True,
    }
    _expect_equal(contract, expected_contract, "view_contract_mismatch")
    canonical = value.get("canonical_split")
    if not isinstance(canonical, Mapping):
        _fail("view_canonical_split_missing", "canonical split is missing")
    _expect_equal(
        canonical.get("seed_counts"),
        {"train": 60, "validation": 20, "test": 20},
        "view_seed_count_mismatch",
    )
    _expect_equal(
        canonical.get("reserved_evaluation_seed_overlap"),
        [],
        "view_reserved_seed_overlap",
    )


def _readiness_markdown(report: Mapping[str, Any]) -> str:
    split = report["canonical_split"]
    counts = split["seed_counts"]
    lines = [
        f"# D5 {('跨视角图' if report['consumer'] == 'tracklet_graph' else '主动视觉')} canonical seed 只读视图",
        "",
        f"验证日期：{report['validation_date']}（America/Los_Angeles）",
        "",
        "## 结论",
        "",
        "共享数值 seed 已按完整 episode 建立只读重分桶视图。原 manifest 和样本制品未修改。",
        f"canonical train/validation/test seed 为 `{counts['train']}/{counts['validation']}/{counts['test']}`，保留 seed `1000-1019` 未进入视图。",
        "",
        "该结果只关闭 D4/D5 等学习消费者之间的 split 身份不一致。模型准入和运行安全门保持失败关闭。",
        "",
        "## 哈希绑定",
        "",
        f"- source manifest SHA256：`{report['source_manifest_sha256']}`",
        f"- view manifest SHA256：`{report['view_manifest_sha256']}`",
        f"- view content SHA256：`{report['view_content_sha256']}`",
        f"- canonical split SHA256：`{split['split_sha256']}`",
        f"- canonical training-set SHA256：`{split['training_set_sha256']}`",
        "",
        "## 计数",
        "",
        f"- episode：`{split['episode_counts']}`",
    ]
    if "sample_counts" in split:
        lines.append(f"- sample：`{split['sample_counts']}`")
    if "candidate_edge_counts" in split:
        lines.append(f"- candidate edge：`{split['candidate_edge_counts']}`")
        edge_coverage = report.get("edge_coverage", {})
        lines.append(
            f"- 全量 edge-free：`{edge_coverage.get('edge_free_episode_count')}/{edge_coverage.get('episode_count')}`（`{edge_coverage.get('edge_free_ratio', 0.0):.2%}`）"
        )
    lines.extend(["", "## 未闭合门", ""])
    for blocker in report["remaining_blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "视图不复制样本，不改变在线/离线内容，也不改变默认旧加载路径。学习输出仍不能创建、改写或换绑 `global_track_id`。几何门控、同相机互斥、版本门和规则回退保持不变。",
            "",
        ]
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer", choices=("tracklet_graph", "active_vision"), required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--training-seed-registry", required=True)
    parser.add_argument("--shared-seed-registry", required=True)
    parser.add_argument("--view-manifest", required=True)
    parser.add_argument("--readiness-json", required=True)
    parser.add_argument("--readiness-markdown", required=True)
    parser.add_argument("--prior-bc-summary", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    common = {
        "training_seed_registry_path": args.training_seed_registry,
        "shared_seed_registry_path": args.shared_seed_registry,
        "view_manifest_path": args.view_manifest,
    }
    if args.consumer == "tracklet_graph":
        dataset, payload, view_sha256 = write_tracklet_canonical_seed_view(
            args.dataset_dir,
            **common,
        )
        report = tracklet_canonical_readiness(
            dataset,
            view_manifest=payload,
            view_manifest_sha256=view_sha256,
        )
    else:
        dataset, payload, view_sha256 = write_active_vision_canonical_seed_view(
            args.dataset_dir,
            **common,
        )
        report = active_vision_canonical_readiness(
            dataset,
            view_manifest=payload,
            view_manifest_sha256=view_sha256,
            prior_bc_summary_path=args.prior_bc_summary,
        )
    json_sha256, markdown_sha256 = write_canonical_readiness(
        report,
        json_path=args.readiness_json,
        markdown_path=args.readiness_markdown,
    )
    print(
        json.dumps(
            {
                "consumer": args.consumer,
                "view_manifest": str(Path(args.view_manifest)),
                "view_manifest_sha256": view_sha256,
                "readiness_json_sha256": json_sha256,
                "readiness_markdown_sha256": markdown_sha256,
                "admission": report["admission"],
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


def _canonical_seed_catalog(
    value: Any,
    name: str,
    *,
    allow_empty: bool = False,
) -> tuple[int, ...]:
    if not isinstance(value, list):
        _fail("seed_catalog_invalid", f"{name} must be a list")
    seeds = tuple(_integer(seed, name) for seed in value)
    if any(seed < 0 for seed in seeds):
        _fail("negative_seed", f"{name} contains a negative seed")
    if not seeds and not allow_empty:
        _fail("seed_catalog_empty", f"{name} is empty")
    if seeds != tuple(sorted(set(seeds))):
        _fail("seed_catalog_not_canonical", f"{name} must be unique and sorted")
    return seeds


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _fail("integer_invalid", f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalSeedViewError("integer_invalid", f"{name} must be an integer") from exc
    if result != value:
        _fail("integer_invalid", f"{name} must be an exact integer")
    return result


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        _fail("number_invalid", f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalSeedViewError("number_invalid", f"{name} must be numeric") from exc
    if not result == result or result in {float("inf"), -float("inf")}:
        _fail("number_invalid", f"{name} must be finite")
    return result


def _require_unique(values: Sequence[str], code: str) -> None:
    if len(values) != len(set(values)):
        _fail(code, "episode identifiers must be unique")


def _require_sha256(value: Any, name: str) -> str:
    text = str(value)
    if len(text) != 64 or not _is_lower_hex(text):
        _fail("sha256_invalid", f"{name} is not a lowercase SHA256")
    return text


def _is_lower_hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalSeedViewError("json_read_failed", f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        _fail("json_object_required", f"{label} must be a JSON object")
    return value


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _plain_json(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    data = _canonical_json_bytes(value) + b"\n"
    _write_bytes_atomic(path, data)


def _write_text_atomic(path: Path, value: str) -> None:
    _write_bytes_atomic(path, value.encode("utf-8"))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _expect_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        _fail(code, f"expected {expected!r}, got {actual!r}")


def _fail(code: str, message: str) -> None:
    raise CanonicalSeedViewError(code, message)


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "ACTIVE_VISION_VIEW_CONSUMER_SCHEMA_VERSION",
    "CANONICAL_SEED_READINESS_SCHEMA_VERSION",
    "CANONICAL_SEED_VIEW_SCHEMA_VERSION",
    "CanonicalSeedViewError",
    "TRACKLET_VIEW_CONSUMER_SCHEMA_VERSION",
    "active_vision_canonical_readiness",
    "canonical_view_binding",
    "load_active_vision_canonical_seed_view",
    "load_tracklet_canonical_seed_view",
    "tracklet_canonical_readiness",
    "write_active_vision_canonical_seed_view",
    "write_canonical_readiness",
    "write_tracklet_canonical_seed_view",
]
