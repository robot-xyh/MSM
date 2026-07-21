from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from d6_evaluation_metrics.cross_module_learning_admission import (
    CrossModuleLearningAdmissionError,
    CrossModuleLearningAdmissionInputs,
    audit_cross_module_learning_data_admission,
    write_cross_module_learning_data_admission_report,
)


_COMMIT = "1" * 40
_SCHEDULE_SHA = "2" * 64
_SPLITS = ("train", "validation", "test")
_TRAINING_SEEDS = list(range(100))
_RESERVED_SEEDS = list(range(1000, 1020))


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha_json(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_token(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value) + b"\n")


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rehash_content(value: dict[str, object], field: str = "content_sha256") -> None:
    unsigned = deepcopy(value)
    unsigned.pop(field, None)
    value[field] = _sha_json(unsigned)


def _assignment() -> dict[int, str]:
    ordered = sorted(
        _TRAINING_SEEDS,
        key=lambda seed: (
            hashlib.sha256(
                f"d3_numeric_seed_atomic_split_v2|20260720\0{seed}".encode()
            ).hexdigest(),
            seed,
        ),
    )
    return {
        seed: (
            "test"
            if index < 20
            else "validation"
            if index < 40
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _split_values(assignment: dict[int, str]) -> dict[str, list[int]]:
    return {
        split: sorted(seed for seed, value in assignment.items() if value == split)
        for split in _SPLITS
    }


def _source_content_hash(manifest: dict[str, object]) -> str:
    payload = deepcopy(manifest)
    payload.pop("split_policy", None)
    payload.pop("split_sha256", None)
    payload.pop("training_set_sha256", None)
    descriptors = payload["episodes"]
    assert isinstance(descriptors, list)
    for descriptor in descriptors:
        assert isinstance(descriptor, dict)
        descriptor.pop("split", None)
    payload["episodes"] = sorted(descriptors, key=lambda item: item["episode_uid"])
    return _sha_json(payload)


def _canonical_d5_summary(
    entries: list[dict[str, object]],
    assignment: dict[int, str],
    *,
    consumer: str,
) -> dict[str, object]:
    canonical_entries: list[dict[str, object]] = []
    for entry in entries:
        item = deepcopy(entry)
        item["source_split"] = item["split"]
        item["split"] = assignment[int(item["seed"])]
        canonical_entries.append(item)
    counts = {
        split: sum(item["split"] == split for item in canonical_entries)
        for split in _SPLITS
    }
    result: dict[str, object] = {
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": 20260720,
        "seed_values": _split_values(assignment),
        "seed_counts": {"train": 60, "validation": 20, "test": 20},
        "episode_counts": counts,
    }
    if consumer == "tracklet_graph":
        result["node_counts"] = {
            split: sum(
                int(item["node_count"])
                for item in canonical_entries
                if item["split"] == split
            )
            for split in _SPLITS
        }
        result["candidate_edge_counts"] = {
            split: sum(
                int(item["edge_count"])
                for item in canonical_entries
                if item["split"] == split
            )
            for split in _SPLITS
        }
        names = (
            "candidate_edges",
            "positive_candidate_edges",
            "negative_candidate_edges",
            "unlabeled_candidate_edges",
        )
        result["class_balance_by_split"] = {
            split: {
                name: sum(
                    int(item["class_balance"][name])
                    for item in canonical_entries
                    if item["split"] == split
                )
                for name in names
            }
            for split in _SPLITS
        }
        hash_fields = ("graph_sha256", "labels_sha256")
    else:
        result["sample_counts"] = {
            split: sum(
                int(item["sample_count"])
                for item in canonical_entries
                if item["split"] == split
            )
            for split in _SPLITS
        }
        hash_fields = ("online_sha256", "offline_sha256")
    result["split_sha256"] = _sha_json(
        sorted(
            [
                {
                    "episode_uid": item["episode_uid"],
                    "scenario_version": item["scenario_version"],
                    "seed": item["seed"],
                    "split": item["split"],
                }
                for item in canonical_entries
            ],
            key=lambda item: item["episode_uid"],
        )
    )
    result["training_set_sha256"] = _sha_json(
        sorted(
            [
                {
                    "episode_uid": item["episode_uid"],
                    "scenario_version": item["scenario_version"],
                    "seed": item["seed"],
                    **{field: item[field] for field in hash_fields},
                }
                for item in canonical_entries
                if item["split"] == "train"
            ],
            key=lambda item: item["episode_uid"],
        )
    )
    result["reassigned_episode_count"] = sum(
        source["split"] != canonical["split"]
        for source, canonical in zip(entries, canonical_entries, strict=True)
    )
    result["reserved_evaluation_seed_overlap"] = []
    return result


def _d5_view(
    *,
    consumer: str,
    consumer_schema: str,
    manifest: dict[str, object],
    manifest_path: Path,
    training_path: Path,
    shared_path: Path,
    shared: dict[str, object],
    canonical_split: dict[str, object],
    schema_keys: tuple[str, ...],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "d5.canonical-seed-split-view.v1",
        "validation_date": "2026-07-21",
        "consumer": consumer,
        "consumer_schema_version": consumer_schema,
        "source": {
            "schema_versions": {key: manifest[key] for key in schema_keys},
            "manifest_sha256": _sha_file(manifest_path),
            "content_sha256": _source_content_hash(manifest),
            "split_sha256": manifest["split_sha256"],
            "training_set_sha256": manifest["training_set_sha256"],
            "episode_count": len(manifest["episodes"]),
            "unique_seed_count": 100,
        },
        "training_seed_registry": {
            "schema_version": "scalable3d-training-seed-registry-v1",
            "file_sha256": _sha_file(training_path),
        },
        "shared_seed_registry": {
            "schema_version": "scalable3d-shared-seed-split-registry-v1",
            "policy_version": "scalable3d-numeric-seed-atomic-split-v1",
            "file_sha256": _sha_file(shared_path),
            "content_sha256": shared["content_sha256"],
            "assignment_sha256": shared["assignment_sha256"],
        },
        "canonical_split": canonical_split,
        "view_contract": {
            "source_manifest_modified": False,
            "source_artifacts_modified": False,
            "complete_episode_rebucket_only": True,
            "sample_copy_allowed": False,
            "online_offline_content_rewrite_allowed": False,
            "default_legacy_loader_unchanged": True,
        },
    }
    payload["content_sha256"] = _sha_json(payload)
    return payload


def _label_availability(sample_count: int) -> dict[str, object]:
    return {
        name: {
            "status": "unavailable",
            "sample_count": sample_count,
            "available_sample_count": 0,
        }
        for name in ("reward", "outcome", "counterfactual", "causal_label")
    }


def _build_fixture(tmp_path: Path) -> CrossModuleLearningAdmissionInputs:
    assignment = _assignment()
    split_values = _split_values(assignment)
    root = tmp_path / "evidence"
    training = {
        "schema_version": "scalable3d-training-seed-registry-v1",
        "training_seed_count": 100,
        "training_seeds": _TRAINING_SEEDS,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "overlap_count": 0,
        "git_commit": _COMMIT,
        "repository_dirty": False,
        "schedule_sha256": _SCHEDULE_SHA,
    }
    training_path = root / "training_seed_registry.json"
    _write_json(training_path, training)
    assignment_rows = [
        {"seed": seed, "split": assignment[seed]} for seed in _TRAINING_SEEDS
    ]
    shared: dict[str, object] = {
        "schema_version": "scalable3d-shared-seed-split-registry-v1",
        "policy_version": "scalable3d-numeric-seed-atomic-split-v1",
        "ordering_compatibility_version": "d3_numeric_seed_atomic_split_v2",
        "source": {
            "training_seed_registry_schema_version": (
                "scalable3d-training-seed-registry-v1"
            ),
            "training_seed_registry_sha256": _sha_file(training_path),
            "git_commit": _COMMIT,
            "repository_dirty": False,
            "schedule_sha256": _SCHEDULE_SHA,
        },
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": 20260720,
        "validation_fraction": 0.2,
        "test_fraction": 0.2,
        "minimum_test_seed_count": 20,
        "training_seed_count": 100,
        "reserved_evaluation_seed_count": 20,
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "training_reserved_overlap_count": 0,
        "split_seed_values": split_values,
        "assignments": assignment_rows,
        "assignment_sha256": _sha_json(assignment_rows),
        "consumer_contract": {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
    }
    _rehash_content(shared)
    shared_path = root / "shared_registry.json"
    _write_json(shared_path, shared)

    d3_path = root / "d3_manifest.json"
    _write_json(
        d3_path,
        {
            "schema_version": "d3_learning_dataset_v2",
            "episode_count": 900,
            "frame_count": 1800,
            "unique_seed_count": 100,
            "split_policy_version": "d3_numeric_seed_atomic_split_v2",
            "split_policy": {},
            "split_seed_values": split_values,
            "split_episode_counts": {"train": 540, "validation": 180, "test": 180},
            "split_frame_counts": {"train": 1080, "validation": 360, "test": 360},
            "identity_policy": "anonymous_ordinal_tokens_no_truth_metadata",
            "source_kind": "scalable_3d_multi_seed_batch",
            "frames_sha256": _sha_token("d3-frames"),
        },
    )

    d4_entries: list[dict[str, object]] = []
    for seed in _TRAINING_SEEDS:
        for index in range(9):
            d4_entries.append(
                {
                    "source": {
                        "seed": seed,
                        "git_dirty": False,
                        "git_commit": _COMMIT,
                    },
                    "split": assignment[seed],
                    "frame_count": 2,
                }
            )
    d4_manifest = {
        "schema": "d4-region-learning-dataset-v1",
        "dataset_sha256": _sha_token("d4-dataset"),
        "split": {"split_sha256": _sha_token("d4-native-split")},
        "availability": {
            "behavior_cloning_available": True,
            "ppo_available": False,
            "dirty_episode_count": 0,
            "episode_count": 900,
            "frame_count": 1800,
            "reward_available_count": 0,
        },
        "episodes": d4_entries,
    }
    d4_manifest_path = root / "d4_manifest.json"
    _write_json(d4_manifest_path, d4_manifest)
    d4_binding: dict[str, object] = {
        "schema": "d4-canonical-region-seed-split-view-v1",
        "source_dataset_sha256": d4_manifest["dataset_sha256"],
        "source_dataset_manifest_file_sha256": _sha_file(d4_manifest_path),
        "source_dataset_split_sha256": d4_manifest["split"]["split_sha256"],
        "training_seed_registry_sha256": _sha_file(training_path),
        "shared_registry_file_sha256": _sha_file(shared_path),
        "shared_registry_content_sha256": shared["content_sha256"],
        "assignment_sha256": shared["assignment_sha256"],
        "split_seed": 20260720,
        "train_seeds": split_values["train"],
        "validation_seeds": split_values["validation"],
        "test_seeds": split_values["test"],
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "episode_count": 900,
        "frame_count": 1800,
    }
    d4_binding["view_sha256"] = _sha_json(d4_binding)
    d4_view = {
        "schema": "d4-canonical-region-seed-split-audit-v1",
        "binding": d4_binding,
        "source_split": {
            "episode_counts": {"train": 540, "validation": 180, "test": 180},
            "split_sha256": d4_manifest["split"]["split_sha256"],
        },
        "canonical_split": {
            "seed_counts": {"train": 60, "validation": 20, "test": 20},
            "episode_counts": {"train": 540, "validation": 180, "test": 180},
            "frame_counts": {"train": 1080, "validation": 360, "test": 360},
            "numeric_seed_atomic": True,
            "reserved_seed_count": 20,
            "reserved_seed_present": False,
        },
        "readiness": {
            "behavior_cloning_view_available": True,
            "ppo_available": False,
            "assist_eligible": False,
            "development_data_governance_only": True,
            "model_performance_evidence": False,
        },
    }
    d4_view_path = root / "d4_formal_view.json"
    _write_json(d4_view_path, d4_view)

    tracklet_entries = [
        {
            "episode_uid": f"tracklet-{seed:03d}",
            "scenario_version": "fixture-v1",
            "seed": seed,
            "split": assignment[seed],
            "node_count": 1,
            "edge_count": 1,
            "class_balance": {
                "candidate_edges": 1,
                "positive_candidate_edges": 1,
                "negative_candidate_edges": 0,
                "unlabeled_candidate_edges": 0,
            },
            "graph_sha256": _sha_token(f"graph-{seed}"),
            "labels_sha256": _sha_token(f"labels-{seed}"),
        }
        for seed in _TRAINING_SEEDS
    ]
    tracklet_entries[0]["class_balance"] = {
        "candidate_edges": 1,
        "positive_candidate_edges": 0,
        "negative_candidate_edges": 0,
        "unlabeled_candidate_edges": 1,
    }
    tracklet_manifest = {
        "schema_version": "d5.tracklet-dataset.v2",
        "graph_schema_version": "d5.sparse-tracklet-graph.v1",
        "evaluator_label_schema_version": "d5.tracklet-evaluator-labels.v1",
        "node_feature_version": "d5.tracklet-node-features.v1",
        "edge_feature_version": "d5.tracklet-edge-features.v1",
        "split_policy": {},
        "split_sha256": _sha_token("tracklet-source-split"),
        "training_set_sha256": _sha_token("tracklet-source-training"),
        "episodes": tracklet_entries,
    }
    tracklet_manifest_path = root / "tracklet_manifest.json"
    _write_json(tracklet_manifest_path, tracklet_manifest)
    tracklet_canonical = _canonical_d5_summary(
        tracklet_entries, assignment, consumer="tracklet_graph"
    )
    tracklet_view = _d5_view(
        consumer="tracklet_graph",
        consumer_schema="d5.tracklet-canonical-view-consumer.v1",
        manifest=tracklet_manifest,
        manifest_path=tracklet_manifest_path,
        training_path=training_path,
        shared_path=shared_path,
        shared=shared,
        canonical_split=tracklet_canonical,
        schema_keys=(
            "schema_version",
            "graph_schema_version",
            "evaluator_label_schema_version",
            "node_feature_version",
            "edge_feature_version",
        ),
    )
    tracklet_view_path = root / "tracklet_view.json"
    _write_json(tracklet_view_path, tracklet_view)
    tracklet_readiness_path = root / "tracklet_readiness.json"
    _write_json(
        tracklet_readiness_path,
        {
            "schema_version": "d5.canonical-seed-readiness.v1",
            "validation_date": "2026-07-21",
            "consumer": "tracklet_graph",
            "source_manifest_sha256": _sha_file(tracklet_manifest_path),
            "view_manifest_sha256": _sha_file(tracklet_view_path),
            "view_content_sha256": tracklet_view["content_sha256"],
            "canonical_split": tracklet_canonical,
            "split_alignment": {
                "status": "pass",
                "joint_training_split_identity_aligned": True,
                "source_manifest_modified": False,
            },
            "training_readiness": {"passed": False, "status": "fail_closed"},
            "admission": {
                "g1_assist_eligible": False,
                "status": "fail_closed",
                "deterministic_geometry_fallback_required": True,
            },
        },
    )

    active_entries: list[dict[str, object]] = []
    for seed in _TRAINING_SEEDS:
        for index in range(9):
            uid = f"active-{seed:03d}-{index}"
            active_entries.append(
                {
                    "episode_uid": uid,
                    "scenario_version": "fixture-v1",
                    "seed": seed,
                    "split": assignment[seed],
                    "sample_count": 1,
                    "online_sha256": _sha_token(f"online-{uid}"),
                    "offline_sha256": _sha_token(f"offline-{uid}"),
                    "source_identity": {"git_dirty": False},
                }
            )
    active_manifest = {
        "schema_version": "d5.active-vision-episode-dataset.v3",
        "episode_descriptor_schema_version": "d5.active-vision-episode-descriptor.v2",
        "episode_record_schema_version": "d5.active-vision-episode-record.v2",
        "sample_schema_version": "d5.active-vision-sample.v2",
        "snapshot_schema_version": "d5.active-vision-snapshot.v1",
        "action_schema_version": "d5.active-vision-action.v1",
        "camera_feedback_schema_version": "d5.active-vision-camera-feedback.v1",
        "runtime_ack_schema_version": "d5.active-vision-runtime-ack.v1",
        "offline_labels_schema_version": "d5.active-vision-offline-labels.v1",
        "offline_label_schema_version": "d5.active-vision-offline-label.v1",
        "source_identity_summary": {"dirty_episode_count": 0},
        "availability": _label_availability(900),
        "split_policy": {},
        "split_sha256": _sha_token("active-source-split"),
        "training_set_sha256": _sha_token("active-source-training"),
        "episodes": active_entries,
    }
    active_manifest_path = root / "active_manifest.json"
    _write_json(active_manifest_path, active_manifest)
    active_canonical = _canonical_d5_summary(
        active_entries, assignment, consumer="active_vision"
    )
    active_view = _d5_view(
        consumer="active_vision",
        consumer_schema="d5.active-vision-canonical-view-consumer.v1",
        manifest=active_manifest,
        manifest_path=active_manifest_path,
        training_path=training_path,
        shared_path=shared_path,
        shared=shared,
        canonical_split=active_canonical,
        schema_keys=(
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
        ),
    )
    active_view_path = root / "active_view.json"
    _write_json(active_view_path, active_view)
    active_readiness_path = root / "active_readiness.json"
    _write_json(
        active_readiness_path,
        {
            "schema_version": "d5.canonical-seed-readiness.v1",
            "validation_date": "2026-07-21",
            "consumer": "active_vision",
            "source_manifest_sha256": _sha_file(active_manifest_path),
            "view_manifest_sha256": _sha_file(active_view_path),
            "view_content_sha256": active_view["content_sha256"],
            "canonical_split": active_canonical,
            "offline_label_availability": active_manifest["availability"],
            "split_alignment": {
                "status": "pass",
                "joint_training_split_identity_aligned": True,
                "source_manifest_modified": False,
                "scope": "split_identity_only",
            },
            "admission": {
                "behavior_cloning_view_available": True,
                "status": "development_shadow_only",
                "assist": False,
                "ppo": False,
                "rule_fallback_required": True,
            },
        },
    )

    d4_supplemental_binding: dict[str, object] = {
        "schema": "d4-canonical-region-seed-split-view-v1",
        "source_dataset_sha256": _sha_token("d4-supplemental-dataset"),
        "source_dataset_manifest_file_sha256": _sha_token("d4-supplemental-manifest"),
        "source_dataset_split_sha256": _sha_token("d4-supplemental-native-split"),
        "training_seed_registry_sha256": _sha_file(training_path),
        "shared_registry_file_sha256": _sha_file(shared_path),
        "shared_registry_content_sha256": shared["content_sha256"],
        "assignment_sha256": shared["assignment_sha256"],
        "split_seed": 20260720,
        "train_seeds": split_values["train"],
        "validation_seeds": split_values["validation"],
        "test_seeds": split_values["test"],
        "reserved_evaluation_seeds": _RESERVED_SEEDS,
        "episode_count": 100,
        "frame_count": 300,
    }
    d4_supplemental_binding["view_sha256"] = _sha_json(d4_supplemental_binding)
    d4_supplemental: dict[str, object] = {
        "schema": "d4-region-action-coverage-summary-v1",
        "purpose": "behavior_cloning_and_offline_shadow_evaluation_only",
        "source_binding": {
            "training_seed_registry_schema": "scalable3d-training-seed-registry-v1",
            "training_seed_registry_sha256": _sha_file(training_path),
            "shared_seed_registry_schema": "scalable3d-shared-seed-split-registry-v1",
            "shared_seed_registry_sha256": _sha_file(shared_path),
        },
        "dataset": {
            "schema": "d4-region-learning-dataset-v1",
            "dataset_sha256": d4_supplemental_binding["source_dataset_sha256"],
            "episode_count": 100,
            "frame_count": 300,
            "numeric_seed_count": 100,
            "dirty_episode_count": 0,
        },
        "canonical": {
            "binding": d4_supplemental_binding,
            "canonical_split": {
                "seed_counts": {"train": 60, "validation": 20, "test": 20},
                "episode_counts": {"train": 60, "validation": 20, "test": 20},
                "frame_counts": {"train": 180, "validation": 60, "test": 60},
                "numeric_seed_atomic": True,
                "reserved_seed_count": 20,
                "reserved_seed_present": False,
            },
        },
        "action_inventory": {
            "total": {
                "hold_true_count": 100,
                "request_replan_true_count": 200,
                "resource_quota_nonzero_count": 200,
                "transfer_count": 100,
            }
        },
        "outcome_and_reward": {
            "outcome_availability": "unavailable",
            "reward_availability": "unavailable",
            "reward_available_count": 0,
            "reward_unavailable_count": 300,
        },
        "safety": {
            "hard_constraint_violation_count": 0,
            "resource_conservation_verified": True,
        },
        "truth_isolation": {
            "online_truth_identifier_count": 0,
            "reserved_evaluation_seed_present_count": 0,
        },
        "admission": {
            "behavior_cloning_manifest_available": True,
            "online_assist_available": False,
            "online_authority_available": False,
            "ppo_available": False,
            "formal_900_episode_dataset_modified": False,
        },
        "audit": {"passed": True, "violations": []},
    }
    _rehash_content(d4_supplemental)
    d4_supplemental_path = root / "d4_supplemental.json"
    _write_json(d4_supplemental_path, d4_supplemental)

    supplemental_labels = _label_availability(1200)
    supplemental_labels.update(
        {"all_values_explicitly_unavailable": True, "zero_padding_used": False}
    )
    d5_supplemental: dict[str, object] = {
        "schema_version": "d5.active-vision-supplemental-curriculum-summary.v1",
        "purpose": "synthetic_behavior_cloning_development_and_offline_shadow_only",
        "source_binding": {
            "training_seed_registry_schema_version": (
                "scalable3d-training-seed-registry-v1"
            ),
            "training_seed_registry_sha256": _sha_file(training_path),
            "shared_seed_registry_schema_version": (
                "scalable3d-shared-seed-split-registry-v1"
            ),
            "shared_seed_registry_sha256": _sha_file(shared_path),
            "shared_seed_registry_content_sha256": shared["content_sha256"],
            "shared_seed_registry_assignment_sha256": shared["assignment_sha256"],
            "repository_dirty": False,
        },
        "dataset": {
            "manifest_sha256": _sha_token("d5-supplemental-manifest"),
            "content_sha256": _sha_token("d5-supplemental-content"),
            "episode_count": 100,
            "sample_count": 1200,
            "unique_seed_count": 100,
        },
        "canonical": {
            "split": {
                "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
                "split_seed": 20260720,
                "seed_values": split_values,
                "seed_counts": {"train": 60, "validation": 20, "test": 20},
                "reserved_evaluation_seed_overlap": [],
                "episode_counts": {"train": 60, "validation": 20, "test": 20},
                "sample_counts": {"train": 720, "validation": 240, "test": 240},
            }
        },
        "coverage": {
            "episode_count": 100,
            "segment_count": 800,
            "sample_count": 1200,
            "intent_counts": {
                "hold": 200,
                "observe_target": 600,
                "reacquire": 200,
                "search_sector": 200,
            },
            "fov_mode_counts": {"wide": 1000, "zoom": 200},
            "camera_role_counts": {"interceptor": 600, "recon": 600},
        },
        "ack_fault_coverage": {
            "counts": {"applied": 400, "rejected": 400, "missing": 400},
            "interpretation": "deterministic_fault_injection_coverage_only",
            "runtime_distribution_evidence": False,
            "reward_or_outcome_evidence": False,
        },
        "offline_label_availability": supplemental_labels,
        "truth_seed_and_formal_isolation": {
            "formal_900_episode_dataset_modified": False,
            "online_truth_identifier_count": 0,
            "reserved_seed_overlap": [],
        },
        "version_and_identity_audit": {
            "global_track_id_created_or_rebound": False,
        },
        "admission": {
            "behavior_cloning_view_available": True,
            "behavior_cloning_development_eligible": True,
            "clean_source": True,
            "ppo_available": False,
            "online_assist_available": False,
            "online_authority_available": False,
            "camera_command_authority_available": False,
            "rule_fallback_required": True,
            "synthetic_curriculum_only": True,
        },
        "audit": {"passed": True, "violation_count": 0, "violations": []},
    }
    _rehash_content(d5_supplemental)
    d5_supplemental_path = root / "d5_supplemental.json"
    _write_json(d5_supplemental_path, d5_supplemental)

    return CrossModuleLearningAdmissionInputs(
        training_seed_registry_path=training_path,
        shared_seed_registry_path=shared_path,
        d3_formal_manifest_path=d3_path,
        d4_formal_manifest_path=d4_manifest_path,
        d4_formal_canonical_view_path=d4_view_path,
        d4_formal_canonical_view_file_sha256=_sha_file(d4_view_path),
        d5_tracklet_formal_manifest_path=tracklet_manifest_path,
        d5_tracklet_canonical_view_path=tracklet_view_path,
        d5_tracklet_canonical_readiness_path=tracklet_readiness_path,
        d5_active_vision_formal_manifest_path=active_manifest_path,
        d5_active_vision_canonical_view_path=active_view_path,
        d5_active_vision_canonical_readiness_path=active_readiness_path,
        d4_supplemental_summary_path=d4_supplemental_path,
        d5_supplemental_summary_path=d5_supplemental_path,
    )


def _replace(
    inputs: CrossModuleLearningAdmissionInputs, **changes: object
) -> CrossModuleLearningAdmissionInputs:
    values = {
        name: getattr(inputs, name) for name in inputs.__dataclass_fields__
    }
    values.update(changes)
    return CrossModuleLearningAdmissionInputs(**values)


def test_joint_admission_writes_chinese_reports_and_keeps_control_closed(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    payload = audit_cross_module_learning_data_admission(inputs)

    assert payload["registries"]["split_seed_counts"] == {
        "train": 60,
        "validation": 20,
        "test": 20,
    }
    assert payload["registries"]["reserved_seed_leakage_count"] == 0
    assert payload["action_coverage"]["d4"]["transfer"] == 100
    assert payload["action_coverage"]["d5"]["intent"]["observe_target"] == 600
    assert payload["availability"]["runtime_ack"]["available"] is False
    tracklet_labels = payload["evidence_layers"]["offline_evaluator_labels"][
        "tracklet_association_labels"
    ]
    assert tracklet_labels["status"] == "partial"
    assert tracklet_labels["complete"] is False
    assert tracklet_labels["labeled_count"] == 99
    assert tracklet_labels["unlabeled_count"] == 1
    assert payload["admission_matrix"] == {
        "behavior_cloning_canonical_view_available": True,
        "behavior_cloning_full_sample_audit": {
            "available": False,
            "status": "pending",
            "reason": "manifest_and_summary_level_audit_only",
        },
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "status": "bc_canonical_view_available_full_sample_audit_pending",
        "promotion_blockers": [
            "behavior_cloning_full_sample_audit_pending",
            "reward_unavailable",
            "outcome_unavailable",
            "runtime_ack_attribution_unavailable",
            "paired_shadow_non_degradation_unavailable",
            "d5_tracklet_training_readiness_fail_closed",
        ],
    }

    outputs = write_cross_module_learning_data_admission_report(
        inputs, tmp_path / "report"
    )
    assert outputs["json"].is_file()
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "跨模块学习数据联合准入审计" in markdown
    assert "只代表确定性故障注入覆盖" in markdown
    assert "部分标签不能解释为完整监督语料" in markdown


def test_cli_writes_joint_admission_reports_in_a_fresh_process(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    output_dir = tmp_path / "cli-report"
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_cross_module_learning_admission.py"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--training-seed-registry",
            str(inputs.training_seed_registry_path),
            "--shared-seed-registry",
            str(inputs.shared_seed_registry_path),
            "--d3-formal-manifest",
            str(inputs.d3_formal_manifest_path),
            "--d4-formal-manifest",
            str(inputs.d4_formal_manifest_path),
            "--d4-formal-canonical-view",
            str(inputs.d4_formal_canonical_view_path),
            "--d4-formal-canonical-view-sha256",
            inputs.d4_formal_canonical_view_file_sha256,
            "--d5-tracklet-formal-manifest",
            str(inputs.d5_tracklet_formal_manifest_path),
            "--d5-tracklet-canonical-view",
            str(inputs.d5_tracklet_canonical_view_path),
            "--d5-tracklet-canonical-readiness",
            str(inputs.d5_tracklet_canonical_readiness_path),
            "--d5-active-vision-formal-manifest",
            str(inputs.d5_active_vision_formal_manifest_path),
            "--d5-active-vision-canonical-view",
            str(inputs.d5_active_vision_canonical_view_path),
            "--d5-active-vision-canonical-readiness",
            str(inputs.d5_active_vision_canonical_readiness_path),
            "--d4-supplemental-summary",
            str(inputs.d4_supplemental_summary_path),
            "--d5-supplemental-summary",
            str(inputs.d5_supplemental_summary_path),
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "ok"
    payload = _read_json(output_dir / "cross_module_learning_admission.json")
    assert payload["audit"]["passed"] is True
    assert payload["admission_matrix"]["ppo_allowed"] is False
    assert (output_dir / "cross_module_learning_admission_cn.md").is_file()


def test_report_output_inside_formal_generation_root_fails_before_write(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    generation_root = inputs.training_seed_registry_path.parent

    for output_dir in (generation_root, generation_root / "audit-output"):
        with pytest.raises(CrossModuleLearningAdmissionError) as exc:
            write_cross_module_learning_data_admission_report(inputs, output_dir)
        assert exc.value.code == "output_inside_formal_generation_root"
        assert not (output_dir / "cross_module_learning_admission.json").exists()
        assert not (output_dir / "cross_module_learning_admission_cn.md").exists()


def test_schema_tamper_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_summary_path)
    value["schema_version"] = "wrong-schema"
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_summary_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "d5_supplemental_schema_mismatch"


def test_hash_tamper_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d4_supplemental_summary_path)
    value["purpose"] = "tampered"
    _write_json(inputs.d4_supplemental_summary_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "d4_supplemental_content_hash_mismatch"


def test_wrong_seed_assignment_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d3_formal_manifest_path)
    catalogs = value["split_seed_values"]
    assert isinstance(catalogs, dict)
    train = catalogs["train"]
    test = catalogs["test"]
    assert isinstance(train, list) and isinstance(test, list)
    train[0], test[0] = test[0], train[0]
    _write_json(inputs.d3_formal_manifest_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "d3_formal_seed_assignment_mismatch"


def test_reserved_seed_leakage_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.shared_seed_registry_path)
    assignments = value["assignments"]
    assert isinstance(assignments, list)
    assignments[-1] = {"seed": 1000, "split": assignments[-1]["split"]}
    split_values = value["split_seed_values"]
    assert isinstance(split_values, dict)
    split = assignments[-1]["split"]
    values = split_values[split]
    assert isinstance(values, list)
    values.remove(99)
    values.append(1000)
    values.sort()
    value["assignment_sha256"] = _sha_json(assignments)
    _rehash_content(value)
    _write_json(inputs.shared_seed_registry_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "shared_registry_reserved_seed_leakage"


def test_formal_and_supplemental_source_mix_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    mixed = _replace(
        inputs,
        d4_formal_canonical_view_path=inputs.d4_supplemental_summary_path,
        d4_formal_canonical_view_file_sha256=_sha_file(
            inputs.d4_supplemental_summary_path
        ),
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(mixed)
    assert exc.value.code == "d4_formal_view_schema_mismatch"


def test_synthetic_ack_cannot_claim_runtime_attribution(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_summary_path)
    ack = value["ack_fault_coverage"]
    assert isinstance(ack, dict)
    ack["runtime_distribution_evidence"] = True
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_summary_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "synthetic_ack_claims_runtime_ack"


def test_unavailable_labels_cannot_be_zero_filled_as_available(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_summary_path)
    labels = value["offline_label_availability"]
    assert isinstance(labels, dict)
    reward = labels["reward"]
    assert isinstance(reward, dict)
    reward["status"] = "available"
    reward["available_sample_count"] = 0
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_summary_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "unavailable_label_zero_imputation"


def test_dirty_supplemental_source_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_summary_path)
    source = value["source_binding"]
    assert isinstance(source, dict)
    source["repository_dirty"] = True
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_summary_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "d5_supplemental_dirty_source"


def test_dirty_formal_training_source_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    training = _read_json(inputs.training_seed_registry_path)
    training["repository_dirty"] = True
    _write_json(inputs.training_seed_registry_path, training)

    shared = _read_json(inputs.shared_seed_registry_path)
    source = shared["source"]
    assert isinstance(source, dict)
    source["training_seed_registry_sha256"] = _sha_file(
        inputs.training_seed_registry_path
    )
    source["repository_dirty"] = True
    _rehash_content(shared)
    _write_json(inputs.shared_seed_registry_path, shared)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == "dirty_training_source"


@pytest.mark.parametrize(
    ("field", "expected_code"),
    (
        ("episode_counts", "d4_supplemental_episode_split_mismatch"),
        ("frame_counts", "d4_supplemental_frame_split_mismatch"),
    ),
)
def test_d4_supplemental_canonical_inventory_tamper_fails_closed(
    tmp_path: Path,
    field: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d4_supplemental_summary_path)
    canonical = value["canonical"]
    assert isinstance(canonical, dict)
    split = canonical["canonical_split"]
    assert isinstance(split, dict)
    counts = split[field]
    assert isinstance(counts, dict)
    counts["train"] = int(counts["train"]) - 1
    counts["validation"] = int(counts["validation"]) + 1
    _rehash_content(value)
    _write_json(inputs.d4_supplemental_summary_path, value)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(inputs)
    assert exc.value.code == expected_code


def test_missing_input_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    missing = _replace(
        inputs,
        d5_tracklet_canonical_readiness_path=tmp_path / "missing-readiness.json",
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(missing)
    assert exc.value.code == "input_missing"


def test_d4_formal_out_of_band_file_hash_is_required(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    mismatched = _replace(
        inputs,
        d4_formal_canonical_view_file_sha256="f" * 64,
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(mismatched)
    assert exc.value.code == "d4_formal_view_file_hash_mismatch"
