from __future__ import annotations

import csv
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from d3_assignment_planner.assignment_full_sample_audit import (
    ASSIGNMENT_FULL_SAMPLE_AUDIT_SCHEMA_V1,
    AssignmentFullSampleAuditError,
    AssignmentFullSampleAuditExpected,
    audit_assignment_full_sample_dataset,
)
from d3_assignment_planner.learning_data import (
    DATASET_FRAMES_FILENAME,
    DATASET_MANIFEST_FILENAME,
    DATASET_SPLITS,
    assign_seed_splits,
    generate_synthetic_learning_dataset,
    load_learning_dataset,
)
from d3_assignment_planner.shared_seed_registry import (
    SHARED_SEED_SPLIT_POLICY_VERSION,
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    SHARED_SEED_SPLIT_UNIT,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
)


@pytest.fixture()
def formal_fixture(tmp_path: Path) -> dict[str, Any]:
    source = tmp_path / "source"
    dataset = source / "dataset"
    manifest = generate_synthetic_learning_dataset(
        dataset,
        seeds=tuple(range(5)),
        episodes_per_seed=1,
        frames_per_episode=1,
        scenario_version="formal-test-5v5-v1",
    )
    _, records = load_learning_dataset(dataset)
    training_seeds = tuple(range(5))
    reserved_seeds = tuple(range(1000, 1020))
    git_commit = "a" * 40
    schedule_sha = sha256(b"d3-full-sample-test-schedule").hexdigest()
    training = {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": git_commit,
        "repository_dirty": False,
        "schedule_sha256": schedule_sha,
        "training_seed_count": len(training_seeds),
        "training_seeds": list(training_seeds),
        "reserved_evaluation_seed_count": len(reserved_seeds),
        "reserved_evaluation_seeds": list(reserved_seeds),
        "overlap_count": 0,
    }
    training_path = source / "training_seed_registry.json"
    _write_json(training_path, training)
    split_by_seed = dict(
        assign_seed_splits(
            training_seeds,
            split_seed=manifest.split_seed,
            validation_fraction=manifest.validation_fraction,
            test_fraction=manifest.test_fraction,
            minimum_unseen_seed_count=manifest.minimum_unseen_seed_count,
        )
    )
    assignments = [
        {"seed": seed, "split": split_by_seed[seed]}
        for seed in training_seeds
    ]
    shared = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": manifest.split_policy_version,
        "source": {
            "training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
            "training_seed_registry_sha256": _file_sha256(training_path),
            "git_commit": git_commit,
            "repository_dirty": False,
            "schedule_sha256": schedule_sha,
        },
        "unit": SHARED_SEED_SPLIT_UNIT,
        "split_seed": manifest.split_seed,
        "validation_fraction": manifest.validation_fraction,
        "test_fraction": manifest.test_fraction,
        "minimum_test_seed_count": manifest.minimum_unseen_seed_count,
        "training_seed_count": len(training_seeds),
        "reserved_evaluation_seed_count": len(reserved_seeds),
        "reserved_evaluation_seeds": list(reserved_seeds),
        "training_reserved_overlap_count": 0,
        "split_seed_values": {
            split: [
                seed for seed in training_seeds if split_by_seed[seed] == split
            ]
            for split in DATASET_SPLITS
        },
        "assignments": assignments,
        "assignment_sha256": _sha256_json(assignments),
        "consumer_contract": {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
    }
    shared["content_sha256"] = _sha256_json(shared)
    shared_path = source / "shared_seed_registry.json"
    _write_json(shared_path, shared)

    progress_path = source / "episode_progress.csv"
    fieldnames = [
        "sequence",
        "episode_id",
        "scenario_version",
        "scenario",
        "seed",
        "scale",
        "d3_exported_frame_count",
        "d3_unavailable_reason_counts",
        "finite_state",
        "online_truth_use_count",
        "repository_dirty",
    ]
    with progress_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for sequence, record in enumerate(records):
            writer.writerow(
                {
                    "sequence": sequence,
                    "episode_id": record.episode,
                    "scenario_version": record.scenario_version,
                    "scenario": "formal-test",
                    "seed": record.seed,
                    "scale": len(record.anonymous_resources),
                    "d3_exported_frame_count": 1,
                    "d3_unavailable_reason_counts": "{}",
                    "finite_state": True,
                    "online_truth_use_count": 0,
                    "repository_dirty": False,
                }
            )

    split_frame_counts = dict(manifest.split_frame_counts)
    generation = {
        "schema_version": "scalable3d-learning-generation-plan-v1",
        "formal": True,
        "repository_dirty": False,
        "git_commit": git_commit,
        "schedule_sha256": schedule_sha,
        "cell_count": manifest.episode_count,
        "completed_episode_count": manifest.episode_count,
        "generation_seed_count": len(training_seeds),
        "reserved_evaluation_seeds": list(reserved_seeds),
        "learning_export_summary": {
            "episode_count": manifest.episode_count,
            "d3_frame_count": manifest.frame_count,
            "d3_split_frame_counts": split_frame_counts,
        },
    }
    generation_path = source / "generation_summary.json"
    _write_json(generation_path, generation)
    batch = {
        "schema_version": "scalable3d-learning-export-v2",
        "episode_count": manifest.episode_count,
        "scenario_seed_group_count": manifest.episode_count,
        "d3_frame_count": manifest.frame_count,
        "d3_split_frame_counts": split_frame_counts,
        "online_truth_policy": "forbidden",
    }
    batch_path = source / "batch_learning_export_summary.json"
    _write_json(batch_path, batch)
    canonical_counts = {
        split: sum(value == split for value in split_by_seed.values())
        for split in DATASET_SPLITS
    }
    candidate_count = sum(len(record.candidate_edge_indices) for record in records)
    selected_count = sum(len(record.rule_selected_edges) for record in records)
    expected = AssignmentFullSampleAuditExpected(
        dataset_manifest_sha256=_file_sha256(
            dataset / DATASET_MANIFEST_FILENAME
        ),
        dataset_frames_sha256=_file_sha256(dataset / DATASET_FRAMES_FILENAME),
        training_registry_sha256=_file_sha256(training_path),
        shared_registry_sha256=_file_sha256(shared_path),
        generation_summary_sha256=_file_sha256(generation_path),
        episode_progress_sha256=_file_sha256(progress_path),
        batch_export_summary_sha256=_file_sha256(batch_path),
        shared_registry_content_sha256=shared["content_sha256"],
        dataset_split_hash=manifest.split_hash,
        source_git_commit=git_commit,
        source_schedule_sha256=schedule_sha,
        episode_count=manifest.episode_count,
        frame_count=manifest.frame_count,
        candidate_edge_count=candidate_count,
        selected_action_count=selected_count,
        canonical_episode_counts=canonical_counts,
        actual_episode_counts=dict(manifest.split_episode_counts),
        actual_frame_counts=split_frame_counts,
        training_seed_count=len(training_seeds),
        reserved_evaluation_seeds=reserved_seeds,
    )
    return {
        "source": source,
        "dataset": dataset,
        "training": training_path,
        "shared": shared_path,
        "generation": generation_path,
        "progress": progress_path,
        "batch": batch_path,
        "expected": expected,
    }


def test_full_sample_audit_accepts_valid_identity_free_fixture(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    report = _run_audit(formal_fixture, tmp_path / "report")

    assert report["schema_version"] == ASSIGNMENT_FULL_SAMPLE_AUDIT_SCHEMA_V1
    assert report["audit"]["passed"] is True
    assert report["audit"]["status"] == "partial"
    assert report["audit"]["violation_count"] == 0
    assert report["admission"]["assignment_full_sample_structural_audit"] == "complete"
    assert report["admission"]["overall_status"] == "partial"
    assert report["admission"]["ppo"] is False
    assert report["admission"]["assist"] is False
    assert report["version_and_identity_audit"]["current_plan_owner_binding"] == "unavailable"
    assert report["version_and_identity_audit"]["current_plan_version_binding"] == "unavailable"
    assert report["evidence_availability"]["real_runtime_applied_ack"] == "unavailable"
    assert report["evidence_availability"]["real_runtime_outcome_attribution"] == "unavailable"
    assert report["evidence_availability"]["causal_or_counterfactual_reward"] == "unavailable"
    content = dict(report)
    declared_hash = content.pop("content_sha256")
    assert _sha256_json(content) == declared_hash


def test_full_sample_audit_rejects_nonfinite_feature(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    expected = _rewrite_first_frame(
        formal_fixture,
        lambda frame: frame["candidate_features"][0].__setitem__(0, float("nan")),
    )
    fixture = {**formal_fixture, "expected": expected}

    report = _run_audit(fixture, tmp_path / "nonfinite-report")

    assert report["audit"]["passed"] is False
    assert any(
        item.startswith("nonfinite_numeric_json:")
        for item in report["audit"]["violations"]
    )
    assert report["admission"]["assignment_full_sample_structural_audit"] == "pending"


def test_full_sample_audit_rejects_split_mismatch(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    def change_split(frame: dict[str, Any]) -> None:
        frame["split"] = next(
            split for split in DATASET_SPLITS if split != frame["split"]
        )

    expected = _rewrite_first_frame(formal_fixture, change_split)
    report = _run_audit(
        {**formal_fixture, "expected": expected},
        tmp_path / "split-report",
    )

    assert report["audit"]["passed"] is False
    assert any(
        item.startswith("frame_split_assignment_mismatch:")
        for item in report["audit"]["violations"]
    )


def test_full_sample_audit_rejects_truth_identity_leakage(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    expected = _rewrite_first_frame(
        formal_fixture,
        lambda frame: frame.__setitem__("truth_actor_id", "target-001"),
    )
    report = _run_audit(
        {**formal_fixture, "expected": expected},
        tmp_path / "truth-report",
    )

    assert report["audit"]["passed"] is False
    assert any(
        item.startswith("online_truth_or_identity_field:")
        for item in report["audit"]["violations"]
    )
    assert report["version_and_identity_audit"]["online_identity_field_occurrence_count"] > 0


@pytest.mark.parametrize(
    ("mutator", "expected_text"),
    [
        (
            lambda frame: frame.__setitem__("previous_plan_version", -1),
            "plan versions must be non-negative",
        ),
        (
            lambda frame: frame["rule_selected_edges"].__setitem__(0, [999, 0]),
            "edge index lies outside",
        ),
    ],
)
def test_full_sample_audit_rejects_version_or_index_error(
    formal_fixture: dict[str, Any],
    tmp_path: Path,
    mutator: Callable[[dict[str, Any]], None],
    expected_text: str,
) -> None:
    expected = _rewrite_first_frame(formal_fixture, mutator)
    report = _run_audit(
        {**formal_fixture, "expected": expected},
        tmp_path / expected_text.split()[0],
    )

    assert report["audit"]["passed"] is False
    assert any(expected_text in item for item in report["audit"]["violations"])


def test_full_sample_audit_rejects_resource_capacity_violation(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    def duplicate_resource(frame: dict[str, Any]) -> None:
        selected = frame["rule_selected_edges"]
        candidates = {tuple(edge) for edge in frame["candidate_edge_indices"]}
        first_target, resource = selected[0]
        replacement = next(
            [target, resource]
            for target in range(len(frame["anonymous_targets"]))
            if target != first_target and (target, resource) in candidates
        )
        selected[1] = replacement

    expected = _rewrite_first_frame(formal_fixture, duplicate_resource)
    report = _run_audit(
        {**formal_fixture, "expected": expected},
        tmp_path / "capacity-report",
    )

    assert report["audit"]["passed"] is False
    assert any(
        item.startswith("resource_capacity_exceeded:")
        for item in report["audit"]["violations"]
    )


def test_full_sample_audit_rejects_unbound_file_tamper(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    frame_path = formal_fixture["dataset"] / DATASET_FRAMES_FILENAME
    frame_path.write_bytes(frame_path.read_bytes() + b"tamper\n")

    report = _run_audit(formal_fixture, tmp_path / "tamper-report")

    assert report["audit"]["passed"] is False
    assert report["binding_checks"]["dataset_frames_sha256"]["passed"] is False
    assert report["artifact_integrity"]["formal_source_data_modified"] is True


def test_full_sample_audit_rejects_descriptor_content_hash_change(
    formal_fixture: dict[str, Any], tmp_path: Path
) -> None:
    generation = json.loads(formal_fixture["generation"].read_text())
    generation["unbound_note"] = "tampered"
    _write_json(formal_fixture["generation"], generation)

    report = _run_audit(formal_fixture, tmp_path / "descriptor-report")

    assert report["audit"]["passed"] is False
    assert report["binding_checks"]["generation_summary_sha256"]["passed"] is False


def test_full_sample_audit_rejects_output_inside_source_root(
    formal_fixture: dict[str, Any]
) -> None:
    with pytest.raises(
        AssignmentFullSampleAuditError,
        match="outside protected source roots",
    ):
        audit_assignment_full_sample_dataset(
            formal_fixture["dataset"],
            training_seed_registry_path=formal_fixture["training"],
            shared_seed_registry_path=formal_fixture["shared"],
            generation_summary_path=formal_fixture["generation"],
            episode_progress_path=formal_fixture["progress"],
            batch_export_summary_path=formal_fixture["batch"],
            output_json_path=formal_fixture["source"] / "audit.json",
            output_markdown_path=formal_fixture["source"] / "audit.md",
            expected=formal_fixture["expected"],
            validation_date="2026-07-21",
        )


def _run_audit(fixture: dict[str, Any], output: Path) -> dict[str, Any]:
    return audit_assignment_full_sample_dataset(
        fixture["dataset"],
        training_seed_registry_path=fixture["training"],
        shared_seed_registry_path=fixture["shared"],
        generation_summary_path=fixture["generation"],
        episode_progress_path=fixture["progress"],
        batch_export_summary_path=fixture["batch"],
        output_json_path=output / "audit.json",
        output_markdown_path=output / "audit.md",
        expected=fixture["expected"],
        validation_date="2026-07-21",
    )


def _rewrite_first_frame(
    fixture: dict[str, Any], mutator: Callable[[dict[str, Any]], None]
) -> AssignmentFullSampleAuditExpected:
    frame_path = fixture["dataset"] / DATASET_FRAMES_FILENAME
    lines = frame_path.read_text(encoding="utf-8").splitlines()
    frame = json.loads(lines[0])
    mutator(frame)
    lines[0] = json.dumps(
        frame,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
    )
    frame_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = fixture["dataset"] / DATASET_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["frames_sha256"] = _file_sha256(frame_path)
    _write_json(manifest_path, manifest)
    return replace(
        fixture["expected"],
        dataset_frames_sha256=_file_sha256(frame_path),
        dataset_manifest_sha256=_file_sha256(manifest_path),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _sha256_json(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
