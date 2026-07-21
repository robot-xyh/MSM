from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from d3_assignment_planner import (
    EDGE_FEATURE_NAMES,
    MODEL_BUNDLE_SCHEMA_V3,
    SharedEdgeActorCriticPolicy,
    audit_formal_learning_dataset,
    development_shadow_admission,
    evaluate_behavior_cloning_development,
    load_learning_dataset,
    load_model_bundle,
    save_model_bundle,
    train_behavior_cloning,
    write_learning_dataset,
)

from test_learning_dataset_bundle import _record


def _formal_fixture(tmp_path: Path):
    records = tuple(
        _record(
            seed,
            f"episode_{scale}_{seed}",
            scenario=f"nominal-{scale}v{scale}-v1",
        )
        for scale in (5, 20, 50, 100, 200)
        for seed in range(5)
    )
    dataset = tmp_path / "dataset"
    write_learning_dataset(
        dataset,
        records,
        minimum_unseen_seed_count=1,
        source_kind="unit_formal_fixture",
    )
    return dataset, load_learning_dataset(dataset)


def test_formal_audit_checks_all_scales_and_external_holdout_exclusion(
    tmp_path: Path,
) -> None:
    dataset, (manifest, records) = _formal_fixture(tmp_path)

    report = audit_formal_learning_dataset(dataset, manifest, records)

    assert report["all_checks_passed"] is True
    assert report["external_holdout"]["overlap"] == []
    assert set(report["scale_coverage"]) == {"5", "20", "50", "100", "200"}
    assert all(item["available"] for item in report["scale_coverage"].values())


def test_bc_development_evaluator_reports_internal_test_and_scale_latency(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    _, (_, records) = _formal_fixture(tmp_path)
    training_records = tuple(
        record for record in records if record.split in {"train", "validation"}
    )
    policy, training = train_behavior_cloning(
        training_records,
        policy=SharedEdgeActorCriticPolicy(hidden_size=8),
        epochs=1,
        mini_batch_frames=4,
        seed=7,
        positive_class_weight_cap=4.0,
    )

    report = evaluate_behavior_cloning_development(
        records,
        policy,
        normalization_mean=training.normalization_mean,
        normalization_scale=training.normalization_scale,
        min_confidence=0.0,
        ood_z_threshold=100.0,
        deadline_s=1.0,
    )

    assert report["admission"]["assist_authorized"] is False
    assert report["split_metrics"]["test"]["evidence_scope"] == (
        "internal_test_not_external_holdout"
    )
    assert report["split_metrics"]["test"]["safety"][
        "bc_shadow_duplicate_count"
    ] == 0
    assert report["scale_metrics"]["200"]["latency_ms"][
        "model_inference_p95"
    ] >= 0.0
    assert np.isfinite(
        report["split_metrics"]["validation"]["regression"][
            "residual_smooth_l1_mean"
        ]
    )


def test_v3_development_bundle_is_checksum_bound_and_cannot_load_as_assist(
    tmp_path: Path,
) -> None:
    pytest.importorskip("torch")
    bundle = tmp_path / "bundle"
    manifest = save_model_bundle(
        bundle,
        SharedEdgeActorCriticPolicy(hidden_size=8),
        split_hash="1" * 64,
        dataset_frames_sha256="2" * 64,
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES)),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES)),
        training_results={"kind": "unit"},
        provenance={
            "repository_git_commit": "3" * 40,
            "repository_git_commit_role": "dataset_and_training_base_commit",
            "training_worktree_state": "module_changes_present_source_sha256_bound",
            "training_date": "2026-07-20",
            "dataset_manifest_sha256": "4" * 64,
            "training_source_sha256": "5" * 64,
            "training_entrypoint": "unit_test",
        },
        admission=development_shadow_admission(),
        promotion_unavailable_reason="external_holdout_1000_1019_not_evaluated",
    )

    assert manifest.bundle_schema_version == MODEL_BUNDLE_SCHEMA_V3
    assert load_model_bundle(bundle, mode="shadow").loaded is True
    assist = load_model_bundle(bundle, mode="assist")
    assert assist.loaded is False
    assert assist.fallback_reason == "bundle_shadow_only"
    assert manifest.promotion_manifest["reason"] == (
        "external_holdout_1000_1019_not_evaluated"
    )

    manifest_path = bundle / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["promotion_manifest"] = {
        **raw["promotion_manifest"],
        "evaluated_split": "test",
        "evidence_eligible": True,
        "evidence_hashes_bound": True,
        "promotion_recommended": True,
        "promotion_status": "recommended",
        "reason": "paired_unseen_seed_gate_passed",
        "unseen_seed_count": 20,
        "safety_non_degradation": True,
        "assignment_cost_non_degradation": True,
    }
    manifest_path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    still_shadow_only = load_model_bundle(bundle, mode="assist")
    assert still_shadow_only.loaded is False
    assert still_shadow_only.fallback_reason == "bundle_shadow_only"
