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


def _d3_full_sample_audit_fixture(
    *,
    d3_manifest_path: Path,
    d3_manifest: dict[str, object],
    training_path: Path,
    shared_path: Path,
    shared: dict[str, object],
) -> dict[str, object]:
    expected_bindings = {
        "batch_export_summary_sha256": _sha_token("d3-batch-export-summary"),
        "dataset_frames_sha256": d3_manifest["frames_sha256"],
        "dataset_manifest_sha256": _sha_file(d3_manifest_path),
        "dataset_split_hash": _sha_token("d3-dataset-split"),
        "episode_progress_sha256": _sha_token("d3-episode-progress"),
        "generation_summary_sha256": _sha_token("d3-generation-summary"),
        "shared_registry_content_sha256": shared["content_sha256"],
        "shared_registry_sha256": _sha_file(shared_path),
        "source_git_commit": _COMMIT,
        "source_schedule_sha256": _SCHEDULE_SHA,
        "training_registry_sha256": _sha_file(training_path),
    }
    actual_bindings = {
        **expected_bindings,
        "shared_registry_assignment_sha256": shared["assignment_sha256"],
        "shared_registry_declared_assignment_sha256": shared[
            "assignment_sha256"
        ],
    }
    source_hashes = {
        "batch_export_summary": expected_bindings[
            "batch_export_summary_sha256"
        ],
        "dataset_frames": expected_bindings["dataset_frames_sha256"],
        "dataset_manifest": expected_bindings["dataset_manifest_sha256"],
        "episode_progress": expected_bindings["episode_progress_sha256"],
        "generation_summary": expected_bindings["generation_summary_sha256"],
        "shared_registry": expected_bindings["shared_registry_sha256"],
        "training_registry": expected_bindings["training_registry_sha256"],
    }
    expected_episode_split = {"train": 540, "validation": 180, "test": 180}
    expected_frame_split = {"train": 962, "validation": 320, "test": 322}
    expected_edge_split = {
        "train": 2_229_182,
        "validation": 721_445,
        "test": 708_188,
    }
    expected_selected_split = {
        "train": 71_425,
        "validation": 23_147,
        "test": 22_732,
    }
    payload: dict[str, object] = {
        "schema_version": "d3.assignment-full-sample-audit.v1",
        "validation_date": "2026-07-21",
        "purpose": "formal_assignment_behavior_cloning_full_sample_admission",
        "source_files": {
            "batch_export_summary": "fixture/batch_export_summary.json",
            "dataset_frames": "fixture/frames.jsonl",
            "dataset_manifest": str(d3_manifest_path),
            "episode_progress": "fixture/episode_progress.csv",
            "generation_summary": "fixture/generation_summary.json",
            "shared_registry": str(shared_path),
            "training_registry": str(training_path),
        },
        "expected_bindings": expected_bindings,
        "actual_bindings": actual_bindings,
        "binding_checks": {
            field: {"actual": value, "expected": value, "passed": True}
            for field, value in expected_bindings.items()
        },
        "artifact_integrity": {
            "dataset_manifest_frames_binding_valid": True,
            "formal_source_data_modified": False,
            "source_artifact_set_sha256": _sha_token("d3-artifact-set"),
            "source_artifacts_unchanged": True,
            "source_file_count": 7,
            "source_hashes_before": source_hashes,
            "source_hashes_after": source_hashes,
        },
        "generation_evidence": {
            "dirty_episode_count": 0,
            "episode_count": 900,
            "exported_frame_count": 1604,
            "finite_episode_count": 900,
            "online_truth_use_count": 0,
            "scale_counts": {
                "5": 180,
                "20": 180,
                "50": 180,
                "100": 180,
                "200": 180,
            },
            "scenario_counts": {
                "center_failure": 100,
                "communication_degraded": 100,
                "delayed_noisy": 100,
                "dense_crossing": 100,
                "evasive_multilevel": 100,
                "formation_split": 100,
                "high_threat_m_to_n": 100,
                "nominal": 100,
                "secondary_failure": 100,
            },
            "unavailable_frame_count": 194,
        },
        "coverage": {
            "actual_episode_counts": expected_episode_split,
            "actual_frame_counts": expected_frame_split,
            "anonymous_resource_record_count": 120_080,
            "anonymous_target_record_count": 118_109,
            "candidate_edge_count": 3_658_815,
            "canonical_episode_counts": {
                "train": 60,
                "validation": 20,
                "test": 20,
            },
            "decision_sample_count": 1604,
            "edge_sample_count": 3_658_815,
            "episode_count": 900,
            "feature_value_count": 43_905_780,
            "frame_count": 1604,
            "resource_target_action_label_count": 3_658_815,
            "selected_resource_target_action_count": 117_304,
            "split_action_label_counts": expected_edge_split,
            "split_candidate_edge_counts": expected_edge_split,
            "split_selected_action_counts": expected_selected_split,
            "training_seed_count": 100,
        },
        "split_and_provenance_audit": {
            "actual_decision_sample_counts": expected_frame_split,
            "actual_source_episode_counts": expected_episode_split,
            "canonical_episode_identity_counts": {
                "train": 60,
                "validation": 20,
                "test": 20,
            },
            "dirty_episode_count": 0,
            "online_truth_use_count": 0,
            "repository_dirty": False,
            "reserved_evaluation_seeds": _RESERVED_SEEDS,
            "reserved_seed_overlap": [],
            "source_git_commit": _COMMIT,
            "source_schedule_sha256": _SCHEDULE_SHA,
        },
        "schema_and_numeric_audit": {
            "all_validated_numeric_features_finite": True,
            "candidate_dimension_mismatch_count": 0,
            "dataset_schema_version": "d3_learning_dataset_v2",
            "feature_value_count": 43_905_780,
            "nonfinite_numeric_value_count": 0,
            "split_policy_version": "d3_numeric_seed_atomic_split_v2",
            "validated_frame_count": 1604,
        },
        "version_and_identity_audit": {
            "anonymous_ordinal_identity_checked_frame_count": 1604,
            "current_plan_owner_binding": "unavailable",
            "current_plan_version_binding": "unavailable",
            "frame_sequence_violation_count": 0,
            "global_track_id_created_or_rewritten": False,
            "global_track_id_illegal_field_count": 0,
            "online_identity_field_occurrence_count": 0,
            "previous_plan_version_regression_count": 0,
            "stale_plan_runtime_rejection_evidence": "unavailable",
            "timestamp_sequence_violation_count": 0,
            "version_checked_frame_count": 1604,
        },
        "action_and_constraint_audit": {
            "action_index_violation_count": 0,
            "candidate_edge_count": 3_658_815,
            "capacity_violation_count": 0,
            "constraint_checked_frame_count": 1604,
            "demand_slot_violation_count": 0,
            "resource_target_action_label_count": 3_658_815,
            "selected_resource_target_action_count": 117_304,
        },
        "acceptance_thresholds": {
            "action_label_count": 3_658_815,
            "actual_episode_counts": expected_episode_split,
            "actual_frame_counts": expected_frame_split,
            "audit_violation_count_maximum": 0,
            "candidate_edge_count": 3_658_815,
            "canonical_episode_counts": {
                "train": 60,
                "validation": 20,
                "test": 20,
            },
            "constraint_violation_count_maximum": 0,
            "decision_sample_count": 1604,
            "dirty_episode_count_maximum": 0,
            "episode_count": 900,
            "global_track_id_illegal_field_count_maximum": 0,
            "online_truth_use_count_maximum": 0,
            "reserved_seed_overlap_maximum": 0,
            "selected_action_count": 117_304,
        },
        "evidence_availability": {
            "causal_or_counterfactual_reward": "unavailable",
            "offline_rule_teacher_reward_component_frame_count": 1604,
            "real_runtime_applied_ack": "unavailable",
            "real_runtime_outcome_attribution": "unavailable",
            "same_seed_paired_shadow_non_degradation": "unavailable",
            "zero_padding_used_for_unavailable_evidence": False,
        },
        "admission": {
            "assignment_full_sample_structural_audit": "complete",
            "assist": False,
            "model_training_performed": False,
            "online_authority": False,
            "overall_status": "partial",
            "ppo": False,
            "rule_cost_and_hungarian_default": True,
            "rule_fallback_required": True,
            "runtime_plan_binding_evidence": "partial",
            "weights_written": False,
        },
        "audit": {
            "passed": True,
            "status": "partial",
            "violation_count": 0,
            "violation_details_truncated": False,
            "violations": [],
        },
        "remaining_gates": [],
    }
    _rehash_content(payload)
    return payload


def _d4_corpus_fixture(
    *,
    supplemental: bool,
    source_git_commit: str,
) -> dict[str, object]:
    if supplemental:
        episode_count = 100
        frame_count = 300
        action_count = 1200
        episode_split = {"train": 60, "validation": 20, "test": 20}
        frame_split = {"train": 180, "validation": 60, "test": 60}
        action_split = {"train": 720, "validation": 240, "test": 240}
        action_counts = {
            "hold_true_count": 100,
            "request_replan_true_count": 200,
            "resource_quota_negative_count": 100,
            "resource_quota_nonzero_count": 200,
            "resource_quota_positive_count": 100,
            "resource_quota_zero_count": 1000,
            "transfer_count": 100,
            "transferred_resource_count": 300,
        }
        reward_reason = "supplemental_curriculum_has_no_observed_outcome"
    else:
        episode_count = 900
        frame_count = 1798
        action_count = 14_384
        episode_split = {"train": 540, "validation": 180, "test": 180}
        frame_split = {"train": 1079, "validation": 359, "test": 360}
        action_split = {"train": 8632, "validation": 2872, "test": 2880}
        action_counts = {
            "hold_true_count": 0,
            "request_replan_true_count": 0,
            "resource_quota_negative_count": 0,
            "resource_quota_nonzero_count": 0,
            "resource_quota_positive_count": 0,
            "resource_quota_zero_count": 14_384,
            "transfer_count": 0,
            "transferred_resource_count": 0,
        }
        reward_reason = "d6_episode_outcome_not_joined"
    corpus: dict[str, object] = {
        "classification": (
            "synthetic_rule_teacher_curriculum"
            if supplemental
            else "formal_observation_corpus"
        ),
        "inventory": {
            "episode_count": episode_count,
            "frame_count": frame_count,
            "sample_count": frame_count,
            "action_count": action_count,
            "sample_definition": "one_region_resource_frame",
            "canonical_split": {
                split: {
                    "episode_count": episode_split[split],
                    "frame_count": frame_split[split],
                    "sample_count": frame_split[split],
                    "action_count": action_split[split],
                }
                for split in _SPLITS
            },
        },
        "canonical": {
            "canonical_split": {
                "seed_counts": {"train": 60, "validation": 20, "test": 20},
                "episode_counts": episode_split,
                "frame_counts": frame_split,
                "numeric_seed_atomic": True,
                "reserved_seed_count": 20,
                "reserved_seed_present": False,
            },
            "readiness": {
                "assist_eligible": False,
                "behavior_cloning_view_available": True,
                "development_data_governance_only": True,
                "model_performance_evidence": False,
                "ppo_available": False,
            },
        },
        "numeric_feature_audit": {
            "finite_sample_count": frame_count,
            "nonfinite_path_count": 0,
            "nonfinite_path_examples": [],
            "nonfinite_sample_count": 0,
        },
        "truth_seed_and_dirty_audit": {
            "dirty_episode_count": 0,
            "numeric_seed_atomic": True,
            "numeric_seed_count": 100,
            "online_truth_identifier_count": 0,
            "reserved_evaluation_seed_overlap": [],
            "truth_identifier_path_examples": [],
        },
        "action_coverage": {
            "action_count": action_count,
            **action_counts,
            "rule_teacher_label_count": frame_count,
            "rule_teacher_label_is_runtime_applied_ack": False,
            "target_kind_counts": {"rule": frame_count},
        },
        "safety_and_generation_audit": {
            "cross_region_transfer_legality_checked": True,
            "explicit_pre_projection_action_mask_available": False,
            "explicit_stale_plan_or_lease_rejection_record_available": False,
            "owner_epoch_version_lease_monotonic_episode_count": episode_count,
            "owner_plan_epoch_lease_binding_checked": True,
            "post_projection_recommendation_count": frame_count,
            "post_projection_recommendation_is_runtime_applied_ack": False,
            "resource_quota_conservation_checked": True,
            "safety_invalid_sample_count": 0,
            "safety_valid_sample_count": frame_count,
            "safety_violation_examples": [],
            "version_violation_examples": [],
        },
        "reward_outcome_and_runtime_ack": {
            "observed_outcome_available": False,
            "paired_shadow_available": False,
            "real_runtime_coalition_member_ack_available": False,
            "reward_available_count": 0,
            "reward_unavailable_count": frame_count,
            "reward_unavailable_reason_counts": {reward_reason: frame_count},
        },
        "schema_and_source": {
            "dataset_schema": "d4-region-learning-dataset-v1",
            "dirty_episode_count": 0,
            "feature_schema_counts": {
                "d4-region-resource-features-v1": frame_count
            },
            "frame_schema_counts": {"d4-region-learning-frame-v1": frame_count},
            "recommendation_schema_counts": {
                "d4-region-resource-recommendation-v1": frame_count
            },
            "snapshot_schema_counts": {
                "d4-region-resource-snapshot-v1": frame_count
            },
            "source_config_sha256_episode_counts": {
                _sha_token(f"d4-config-{supplemental}"): episode_count
            },
            "source_git_commit_episode_counts": {
                source_git_commit: episode_count
            },
            "source_schema_counts": {
                "d4-region-learning-source-v1": episode_count
            },
        },
    }
    if supplemental:
        corpus["synthetic_evidence_boundary"] = {
            "action_coverage_evidence": True,
            "attributable_reward_evidence": False,
            "center_or_secondary_takeover_effect_evidence": False,
            "deterministic_safety_constraint_evidence": True,
            "finite_value_evidence": True,
            "network_partition_effect_evidence": False,
            "observed_outcome_evidence": False,
            "real_runtime_coalition_member_ack_evidence": False,
            "structure_and_schema_evidence": True,
        }
    return corpus


def _d4_full_sample_audit_fixture(
    *,
    d4_manifest_path: Path,
    d4_manifest: dict[str, object],
    d4_supplemental_path: Path,
    d4_supplemental: dict[str, object],
    training_path: Path,
    shared_path: Path,
) -> dict[str, object]:
    supplemental_binding = d4_supplemental["canonical"]["binding"]
    expected_bindings = {
        "formal_dataset_sha256": d4_manifest["dataset_sha256"],
        "formal_manifest_sha256": _sha_file(d4_manifest_path),
        "formal_source_git_commit": _COMMIT,
        "shared_registry_sha256": _sha_file(shared_path),
        "supplemental_canonical_view_sha256": _sha_token(
            "d4-supplemental-view-file"
        ),
        "supplemental_dataset_sha256": d4_supplemental["dataset"][
            "dataset_sha256"
        ],
        "supplemental_manifest_sha256": supplemental_binding[
            "source_dataset_manifest_file_sha256"
        ],
        "supplemental_source_git_commit": _COMMIT,
        "supplemental_summary_content_sha256": d4_supplemental[
            "content_sha256"
        ],
        "supplemental_summary_file_sha256": _sha_file(d4_supplemental_path),
        "training_registry_sha256": _sha_file(training_path),
    }
    auxiliary_hashes = {
        "shared_seed_registry": _sha_file(shared_path),
        "supplemental_canonical_view": expected_bindings[
            "supplemental_canonical_view_sha256"
        ],
        "supplemental_summary": _sha_file(d4_supplemental_path),
        "training_seed_registry": _sha_file(training_path),
    }
    unavailable = {
        name: {"availability": "unavailable", "status": "pending"}
        for name in (
            "attributable_reward",
            "explicit_pre_projection_action_mask",
            "observed_outcome",
            "real_runtime_coalition_member_ack",
            "same_seed_paired_shadow",
            "stale_plan_epoch_lease_rejection_samples",
        )
    }
    payload: dict[str, object] = {
        "schema": "d4-region-resource-full-sample-admission-audit-v1",
        "validation_date": "2026-07-21",
        "purpose": "d4_formal_and_supplemental_full_sample_admission",
        "audit_mode": "read_only_fail_closed",
        "source_paths": {
            "formal_dataset": "fixture/d4_formal",
            "shared_seed_registry": str(shared_path),
            "supplemental_canonical_view": "fixture/d4_supplemental_view.json",
            "supplemental_dataset": "fixture/d4_supplemental",
            "supplemental_summary": str(d4_supplemental_path),
            "training_seed_registry": str(training_path),
        },
        "expected_bindings": expected_bindings,
        "actual_bindings": expected_bindings,
        "binding_checks": {
            field: {"actual": value, "expected": value, "passed": True}
            for field, value in expected_bindings.items()
        },
        "artifact_integrity": {
            "auxiliary_source_hashes_before": auxiliary_hashes,
            "auxiliary_source_hashes_after": auxiliary_hashes,
            "auxiliary_sources_unchanged_during_audit": True,
            "formal": {
                "artifact_inventory_exact": True,
                "dataset_file_count": 901,
                "episode_sha256_mismatch_count": 0,
                "episode_sha256_verified_count": 900,
                "manifest_episode_file_count": 900,
                "source_unchanged_during_audit": True,
                "tree_sha256": _sha_token("d4-formal-tree"),
            },
            "formal_900_episode_dataset_modified": False,
            "supplemental": {
                "artifact_inventory_exact": True,
                "dataset_file_count": 101,
                "episode_sha256_mismatch_count": 0,
                "episode_sha256_verified_count": 100,
                "manifest_episode_file_count": 100,
                "source_unchanged_during_audit": True,
                "tree_sha256": _sha_token("d4-supplemental-tree"),
            },
        },
        "formal_corpus": _d4_corpus_fixture(
            supplemental=False,
            source_git_commit=_COMMIT,
        ),
        "supplemental_curriculum": _d4_corpus_fixture(
            supplemental=True,
            source_git_commit=_COMMIT,
        ),
        "status": {
            "combined_full_sample": "complete",
            "formal_full_sample": "complete",
            "supplemental_full_sample": "complete",
        },
        "evidence_availability": unavailable,
        "admission": {
            "assist_allowed": False,
            "behavior_cloning_full_sample_audit": "complete",
            "d6_cross_module_learning_admission": "pending_external_audit",
            "deterministic_region_rules_are_only_executable_path": True,
            "lease_epoch_and_safety_projection_remain_mandatory": True,
            "model_training_performed": False,
            "online_authority_allowed": False,
            "ppo_allowed": False,
            "rule_fallback_required": True,
            "weights_written": False,
        },
        "audit": {
            "common_violations": [],
            "fail_closed": True,
            "formal_violations": [],
            "passed": True,
            "supplemental_violations": [],
            "violation_count": 0,
            "violations": [],
        },
        "remaining_gates": [],
    }
    _rehash_content(payload)
    return payload


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
    d3_manifest: dict[str, object] = {
            "schema_version": "d3_learning_dataset_v2",
            "episode_count": 900,
            "frame_count": 1604,
            "unique_seed_count": 100,
            "split_policy_version": "d3_numeric_seed_atomic_split_v2",
            "split_policy": {},
            "split_seed_values": split_values,
            "split_episode_counts": {"train": 540, "validation": 180, "test": 180},
            "split_frame_counts": {"train": 962, "validation": 320, "test": 322},
            "identity_policy": "anonymous_ordinal_tokens_no_truth_metadata",
            "source_kind": "scalable_3d_multi_seed_batch",
            "frames_sha256": _sha_token("d3-frames"),
    }
    _write_json(d3_path, d3_manifest)

    d4_entries: list[dict[str, object]] = []
    for seed in _TRAINING_SEEDS:
        for index in range(9):
            canonical_split = assignment[seed]
            shortened = (
                index == 0
                and canonical_split in {"train", "validation"}
                and seed == split_values[canonical_split][0]
            )
            d4_entries.append(
                {
                    "source": {
                        "seed": seed,
                        "git_dirty": False,
                        "git_commit": _COMMIT,
                    },
                    "split": assignment[seed],
                    "frame_count": 1 if shortened else 2,
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
            "frame_count": 1798,
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
        "frame_count": 1798,
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
            "frame_counts": {"train": 1079, "validation": 359, "test": 360},
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
            "dataset_config_sha256": _sha_token("d5-supplemental-config"),
            "git_commit": _COMMIT,
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
            "view_manifest_sha256": _sha_token("d5-supplemental-view"),
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

    d5_full_expected_bindings = {
        "canonical_view_sha256": d5_supplemental["canonical"][
            "view_manifest_sha256"
        ],
        "dataset_config_sha256": d5_supplemental["source_binding"][
            "dataset_config_sha256"
        ],
        "dataset_manifest_sha256": d5_supplemental["dataset"][
            "manifest_sha256"
        ],
        "shared_registry_sha256": _sha_file(shared_path),
        "source_git_commit": _COMMIT,
        "summary_content_sha256": d5_supplemental["content_sha256"],
        "training_registry_sha256": _sha_file(training_path),
    }
    d5_checksums_sha256 = _sha_token("d5-supplemental-checksums")
    d5_source_hashes = {
        "canonical_view_sha256": d5_full_expected_bindings[
            "canonical_view_sha256"
        ],
        "dataset_checksums_sha256": d5_checksums_sha256,
        "dataset_config_sha256": d5_full_expected_bindings[
            "dataset_config_sha256"
        ],
        "dataset_manifest_sha256": d5_full_expected_bindings[
            "dataset_manifest_sha256"
        ],
        "shared_registry_sha256": d5_full_expected_bindings[
            "shared_registry_sha256"
        ],
        "summary_file_sha256": _sha_file(d5_supplemental_path),
        "training_registry_sha256": d5_full_expected_bindings[
            "training_registry_sha256"
        ],
    }
    d5_full_actual_bindings = {
        **d5_full_expected_bindings,
        "dataset_checksums_sha256": d5_checksums_sha256,
        "summary_file_sha256": _sha_file(d5_supplemental_path),
    }
    d5_full_sample_audit: dict[str, object] = {
        "schema_version": (
            "d5.active-vision-supplemental-bc-full-sample-audit.v1"
        ),
        "validation_date": "2026-07-21",
        "purpose": (
            "supplemental_rule_teacher_behavior_cloning_full_sample_admission"
        ),
        "expected_bindings": d5_full_expected_bindings,
        "actual_bindings": d5_full_actual_bindings,
        "binding_checks": {
            field: {"actual": value, "expected": value, "passed": True}
            for field, value in d5_full_expected_bindings.items()
        },
        "coverage": {
            "episode_count": 100,
            "segment_count": 800,
            "sample_count": 1200,
            "canonical_episode_counts": {
                "train": 60,
                "validation": 20,
                "test": 20,
            },
            "canonical_sample_counts": {
                "train": 720,
                "validation": 240,
                "test": 240,
            },
            "intent_counts": d5_supplemental["coverage"]["intent_counts"],
            "fov_mode_counts": d5_supplemental["coverage"]["fov_mode_counts"],
            "camera_role_counts": d5_supplemental["coverage"][
                "camera_role_counts"
            ],
        },
        "artifact_integrity": {
            "canonical_loader_passed": True,
            "checksum_artifact_set_exact": True,
            "checksummed_file_count": 302,
            "descriptor_manifest_match_count": 100,
            "episode_descriptor_file_count": 100,
            "formal_900_episode_dataset_modified": False,
            "offline_file_count": 100,
            "online_file_count": 100,
            "online_offline_episode_collections_complete": True,
            "sha256_mismatch_file_count": 0,
            "sha256_verified_file_count": 302,
            "source_artifacts_unchanged": True,
            "source_hashes_before": d5_source_hashes,
            "source_hashes_after": d5_source_hashes,
            "strict_lazy_loader_passed": True,
        },
        "behavior_cloning_feature_audit": {
            "sample_count": 1200,
            "finite_feature_sample_count": 1200,
            "nonfinite_feature_sample_count": 0,
            "global_track_id_created_rewritten_or_rebound": False,
            "numeric_seed_atomic": True,
            "reserved_evaluation_seed_overlap": [],
            "version_consistency_checked_sample_count": 1200,
            "version_monotonic_episode_count": 100,
            "canonical_seed_counts": {
                "train": 60,
                "validation": 20,
                "test": 20,
            },
            "canonical_sample_counts": {
                "train": 720,
                "validation": 240,
                "test": 240,
            },
        },
        "truth_seed_and_source_audit": {
            "dirty_episode_count": 0,
            "repository_dirty": False,
            "dirty_source_accepted": False,
            "online_truth_identifier_count": 0,
            "online_truth_used_for_behavior_cloning": False,
            "reserved_seed_overlap": [],
            "reserved_evaluation_seeds": _RESERVED_SEEDS,
            "training_seed_count": 100,
            "synthetic_episode_count": 100,
            "non_synthetic_episode_count": 0,
            "truth_guard_passed_episode_count": 100,
            "formal_900_episode_dataset_modified": False,
        },
        "version_and_identity_audit": {
            "caller_owned_binding_rechecked_for_all_samples": True,
            "d5_created_rewritten_or_rebound_global_track_id": False,
            "global_track_id_created_or_rebound": False,
            "global_track_id_source": "caller_owned_center_reference",
            "communication_and_track_versions_strictly_increasing": True,
            "plan_and_coalition_versions_monotonic": True,
            "sequence_contiguous": True,
            "timestamps_strictly_increasing": True,
            "runtime_mode_counts": {"disabled": 1200},
        },
        "offline_label_availability": supplemental_labels,
        "synthetic_ack_fault_coverage": {
            "counts": {"applied": 400, "rejected": 400, "missing": 400},
            "expected_counts": {
                "applied": 400,
                "rejected": 400,
                "missing": 400,
            },
            "interpretation": "deterministic_fault_injection_coverage_only",
            "real_runtime_distribution_evidence": False,
            "runtime_ack_attribution_available": False,
            "reward_or_outcome_evidence": False,
        },
        "corpus_classification": {
            "formal_observation_corpus": False,
            "supplemental_rule_teacher_data": True,
            "offline_evaluation_labels_available": False,
            "real_runtime_ack_evidence": False,
        },
        "admission": {
            "behavior_cloning_full_sample_audit": "complete",
            "d6_cross_module_learning_admission": "pending_external_audit",
            "model_training_performed": False,
            "weights_written": False,
            "ppo": False,
            "assist": False,
            "online_authority": False,
            "camera_command_authority": False,
            "rule_fallback_required": True,
        },
        "audit": {"passed": True, "violation_count": 0, "violations": []},
    }
    _rehash_content(d5_full_sample_audit)
    d5_full_sample_audit_path = root / "d5_full_sample_audit.json"
    _write_json(d5_full_sample_audit_path, d5_full_sample_audit)

    d3_full_sample_audit = _d3_full_sample_audit_fixture(
        d3_manifest_path=d3_path,
        d3_manifest=d3_manifest,
        training_path=training_path,
        shared_path=shared_path,
        shared=shared,
    )
    d3_full_sample_audit_path = root / "d3_full_sample_audit.json"
    _write_json(d3_full_sample_audit_path, d3_full_sample_audit)

    d4_full_sample_audit = _d4_full_sample_audit_fixture(
        d4_manifest_path=d4_manifest_path,
        d4_manifest=d4_manifest,
        d4_supplemental_path=d4_supplemental_path,
        d4_supplemental=d4_supplemental,
        training_path=training_path,
        shared_path=shared_path,
    )
    d4_full_sample_audit_path = root / "d4_full_sample_audit.json"
    _write_json(d4_full_sample_audit_path, d4_full_sample_audit)

    return CrossModuleLearningAdmissionInputs(
        training_seed_registry_path=training_path,
        shared_seed_registry_path=shared_path,
        d3_formal_manifest_path=d3_path,
        d3_full_sample_audit_path=d3_full_sample_audit_path,
        d3_full_sample_audit_file_sha256=_sha_file(d3_full_sample_audit_path),
        d4_formal_manifest_path=d4_manifest_path,
        d4_formal_canonical_view_path=d4_view_path,
        d4_formal_canonical_view_file_sha256=_sha_file(d4_view_path),
        d4_full_sample_audit_path=d4_full_sample_audit_path,
        d4_full_sample_audit_file_sha256=_sha_file(d4_full_sample_audit_path),
        d5_tracklet_formal_manifest_path=tracklet_manifest_path,
        d5_tracklet_canonical_view_path=tracklet_view_path,
        d5_tracklet_canonical_readiness_path=tracklet_readiness_path,
        d5_active_vision_formal_manifest_path=active_manifest_path,
        d5_active_vision_canonical_view_path=active_view_path,
        d5_active_vision_canonical_readiness_path=active_readiness_path,
        d4_supplemental_summary_path=d4_supplemental_path,
        d5_supplemental_summary_path=d5_supplemental_path,
        d5_supplemental_full_sample_audit_path=d5_full_sample_audit_path,
        d5_supplemental_full_sample_audit_file_sha256=_sha_file(
            d5_full_sample_audit_path
        ),
    )


def _replace(
    inputs: CrossModuleLearningAdmissionInputs, **changes: object
) -> CrossModuleLearningAdmissionInputs:
    values = {
        name: getattr(inputs, name) for name in inputs.__dataclass_fields__
    }
    values.update(changes)
    return CrossModuleLearningAdmissionInputs(**values)


def _rewrite_full_sample_audit(
    inputs: CrossModuleLearningAdmissionInputs,
    module: str,
    payload: dict[str, object],
    *,
    rehash_content: bool = True,
) -> CrossModuleLearningAdmissionInputs:
    if module == "d3":
        path = inputs.d3_full_sample_audit_path
        sha_field = "d3_full_sample_audit_file_sha256"
    elif module == "d4":
        path = inputs.d4_full_sample_audit_path
        sha_field = "d4_full_sample_audit_file_sha256"
    else:  # pragma: no cover - test helper contract
        raise ValueError(f"unsupported module: {module}")
    if rehash_content:
        _rehash_content(payload)
    _write_json(path, payload)
    return _replace(inputs, **{sha_field: _sha_file(path)})


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
    full_sample = payload["evidence_layers"]["full_sample_audits"]
    assert full_sample["status"] == "complete"
    assert full_sample["complete"] is True
    assert full_sample["modules"]["d3_assignment"]["status"] == "complete"
    assert full_sample["modules"]["d4_region"]["status"] == "complete"
    assert (
        full_sample["modules"]["d5_supplemental_active_vision"]["status"]
        == "complete"
    )
    assert (
        full_sample["modules"]["d5_supplemental_active_vision"][
            "verified_artifact_count"
        ]
        == 302
    )
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
            "available": True,
            "status": "complete",
            "reason": "d3_d4_d5_structural_full_sample_audits_complete",
            "module_status": {
                "d3_assignment": "complete",
                "d4_region": "complete",
                "d5_supplemental_active_vision": "complete",
            },
        },
        "ppo_allowed": False,
        "assist_allowed": False,
        "authority_allowed": False,
        "rule_fallback_required": True,
        "status": "structural_full_sample_complete_overall_admission_partial",
        "promotion_blockers": [
            "reward_unavailable",
            "outcome_unavailable",
            "causal_and_counterfactual_evidence_unavailable",
            "runtime_ack_attribution_unavailable",
            "paired_shadow_non_degradation_unavailable",
            "held_out_seed_performance_unavailable",
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
    assert "跨模块结构性全样本状态为 complete" in markdown
    assert "总体准入仍为 partial" in markdown


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
            "--d3-full-sample-audit",
            str(inputs.d3_full_sample_audit_path),
            "--d3-full-sample-audit-sha256",
            inputs.d3_full_sample_audit_file_sha256,
            "--d4-formal-manifest",
            str(inputs.d4_formal_manifest_path),
            "--d4-formal-canonical-view",
            str(inputs.d4_formal_canonical_view_path),
            "--d4-formal-canonical-view-sha256",
            inputs.d4_formal_canonical_view_file_sha256,
            "--d4-full-sample-audit",
            str(inputs.d4_full_sample_audit_path),
            "--d4-full-sample-audit-sha256",
            inputs.d4_full_sample_audit_file_sha256,
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
            "--d5-supplemental-full-sample-audit",
            str(inputs.d5_supplemental_full_sample_audit_path),
            "--d5-supplemental-full-sample-audit-sha256",
            inputs.d5_supplemental_full_sample_audit_file_sha256,
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


def test_d5_full_sample_out_of_band_file_hash_is_required(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    mismatched = _replace(
        inputs,
        d5_supplemental_full_sample_audit_file_sha256="f" * 64,
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(mismatched)
    assert exc.value.code == "d5_full_sample_audit_file_hash_mismatch"


def test_d5_full_sample_content_tamper_fails_closed(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_full_sample_audit_path)
    coverage = value["coverage"]
    assert isinstance(coverage, dict)
    coverage["sample_count"] = 1199
    _write_json(inputs.d5_supplemental_full_sample_audit_path, value)
    rebound = _replace(
        inputs,
        d5_supplemental_full_sample_audit_file_sha256=_sha_file(
            inputs.d5_supplemental_full_sample_audit_path
        ),
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == "d5_full_sample_audit_content_hash_mismatch"


def test_d5_full_sample_source_binding_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_full_sample_audit_path)
    expected = value["expected_bindings"]
    actual = value["actual_bindings"]
    checks = value["binding_checks"]
    assert isinstance(expected, dict)
    assert isinstance(actual, dict)
    assert isinstance(checks, dict)
    wrong = _sha_token("wrong-dataset-manifest")
    expected["dataset_manifest_sha256"] = wrong
    actual["dataset_manifest_sha256"] = wrong
    checks["dataset_manifest_sha256"] = {
        "actual": wrong,
        "expected": wrong,
        "passed": True,
    }
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_full_sample_audit_path, value)
    rebound = _replace(
        inputs,
        d5_supplemental_full_sample_audit_file_sha256=_sha_file(
            inputs.d5_supplemental_full_sample_audit_path
        ),
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == "d5_full_sample_expected_binding_mismatch"


def test_d5_full_sample_cannot_open_assist_authority(tmp_path: Path) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_full_sample_audit_path)
    admission = value["admission"]
    assert isinstance(admission, dict)
    admission["assist"] = True
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_full_sample_audit_path, value)
    rebound = _replace(
        inputs,
        d5_supplemental_full_sample_audit_file_sha256=_sha_file(
            inputs.d5_supplemental_full_sample_audit_path
        ),
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == "d5_full_sample_admission_overstated"


def test_d5_full_sample_synthetic_ack_cannot_become_runtime_evidence(
    tmp_path: Path,
) -> None:
    inputs = _build_fixture(tmp_path)
    value = _read_json(inputs.d5_supplemental_full_sample_audit_path)
    ack = value["synthetic_ack_fault_coverage"]
    assert isinstance(ack, dict)
    ack["real_runtime_distribution_evidence"] = True
    _rehash_content(value)
    _write_json(inputs.d5_supplemental_full_sample_audit_path, value)
    rebound = _replace(
        inputs,
        d5_supplemental_full_sample_audit_file_sha256=_sha_file(
            inputs.d5_supplemental_full_sample_audit_path
        ),
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == "d5_full_sample_synthetic_ack_promoted"


@pytest.mark.parametrize(
    ("module", "field", "expected_code"),
    (
        (
            "d3",
            "d3_full_sample_audit_file_sha256",
            "d3_full_sample_audit_file_hash_mismatch",
        ),
        (
            "d4",
            "d4_full_sample_audit_file_sha256",
            "d4_full_sample_audit_file_hash_mismatch",
        ),
    ),
)
def test_d3_d4_full_sample_out_of_band_file_hash_fails_closed(
    tmp_path: Path,
    module: str,
    field: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    mismatched = _replace(inputs, **{field: "f" * 64})

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(mismatched)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "schema_field", "expected_code"),
    (
        ("d3", "schema_version", "d3_full_sample_audit_schema_mismatch"),
        ("d4", "schema", "d4_full_sample_audit_schema_mismatch"),
    ),
)
def test_d3_d4_full_sample_schema_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    schema_field: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    payload[schema_field] = "tampered-schema"
    rebound = _rewrite_full_sample_audit(inputs, module, payload)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "expected_code"),
    (
        ("d3", "d3_full_sample_audit_content_hash_mismatch"),
        ("d4", "d4_full_sample_audit_content_hash_mismatch"),
    ),
)
def test_d3_d4_full_sample_content_hash_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    payload["purpose"] = "tampered-purpose"
    rebound = _rewrite_full_sample_audit(
        inputs,
        module,
        payload,
        rehash_content=False,
    )

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "expected_code"),
    (
        ("d3", "d3_full_sample_inventory_mismatch"),
        ("d4", "d4_full_sample_inventory_mismatch"),
    ),
)
def test_d3_d4_full_sample_inventory_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    if module == "d3":
        coverage = payload["coverage"]
        assert isinstance(coverage, dict)
        coverage["candidate_edge_count"] = 3_658_814
    else:
        formal = payload["formal_corpus"]
        assert isinstance(formal, dict)
        inventory = formal["inventory"]
        assert isinstance(inventory, dict)
        inventory["sample_count"] = 1797
    rebound = _rewrite_full_sample_audit(inputs, module, payload)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "binding_field", "expected_code"),
    (
        (
            "d3",
            "dataset_manifest_sha256",
            "d3_full_sample_expected_binding_mismatch",
        ),
        (
            "d4",
            "formal_manifest_sha256",
            "d4_full_sample_expected_binding_mismatch",
        ),
    ),
)
def test_d3_d4_full_sample_source_binding_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    binding_field: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    expected = payload["expected_bindings"]
    actual = payload["actual_bindings"]
    checks = payload["binding_checks"]
    assert isinstance(expected, dict)
    assert isinstance(actual, dict)
    assert isinstance(checks, dict)
    wrong = _sha_token(f"wrong-{module}-{binding_field}")
    expected[binding_field] = wrong
    actual[binding_field] = wrong
    checks[binding_field] = {
        "actual": wrong,
        "expected": wrong,
        "passed": True,
    }
    rebound = _rewrite_full_sample_audit(inputs, module, payload)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "expected_code"),
    (
        ("d3", "d3_full_sample_producer_audit_failed"),
        ("d4", "d4_full_sample_status_invalid"),
    ),
)
def test_d3_d4_full_sample_status_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    if module == "d3":
        audit = payload["audit"]
        assert isinstance(audit, dict)
        audit["status"] = "complete"
    else:
        status = payload["status"]
        assert isinstance(status, dict)
        status["combined_full_sample"] = "partial"
    rebound = _rewrite_full_sample_audit(inputs, module, payload)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "expected_code"),
    (
        ("d3", "d3_full_sample_admission_overstated"),
        ("d4", "d4_full_sample_admission_overstated"),
    ),
)
def test_d3_d4_full_sample_admission_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    admission = payload["admission"]
    assert isinstance(admission, dict)
    if module == "d3":
        admission["assist"] = True
    else:
        admission["assist_allowed"] = True
    rebound = _rewrite_full_sample_audit(inputs, module, payload)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code


@pytest.mark.parametrize(
    ("module", "expected_code"),
    (
        ("d3", "d3_full_sample_availability_overstated"),
        ("d4", "d4_full_sample_availability_overstated"),
    ),
)
def test_d3_d4_full_sample_availability_tamper_fails_closed(
    tmp_path: Path,
    module: str,
    expected_code: str,
) -> None:
    inputs = _build_fixture(tmp_path)
    path = (
        inputs.d3_full_sample_audit_path
        if module == "d3"
        else inputs.d4_full_sample_audit_path
    )
    payload = _read_json(path)
    availability = payload["evidence_availability"]
    assert isinstance(availability, dict)
    if module == "d3":
        availability["real_runtime_applied_ack"] = "available"
    else:
        runtime_ack = availability["real_runtime_coalition_member_ack"]
        assert isinstance(runtime_ack, dict)
        runtime_ack["availability"] = "available"
    rebound = _rewrite_full_sample_audit(inputs, module, payload)

    with pytest.raises(CrossModuleLearningAdmissionError) as exc:
        audit_cross_module_learning_data_admission(rebound)
    assert exc.value.code == expected_code
