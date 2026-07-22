from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from d6_evaluation_metrics import (
    D5PairedShadowAuditError,
    D5PairedShadowAuditInputs,
    screen_single_feature_separability,
    validate_paired_lineage_records,
)
from d6_evaluation_metrics import d5_paired_shadow_audit as audit_module


_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
_SCALES = (5, 20, 50, 100, 200)


def _metrics(edge_count: int) -> dict[str, float | int]:
    return {
        "true_positive": edge_count,
        "false_positive": 0,
        "false_negative": 0,
        "true_negative": 0,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "false_merge_rate": 0.0,
    }


def _arm(edge_count: int) -> dict[str, object]:
    return {
        "edge": _metrics(edge_count),
        "cluster_pairwise": {
            **_metrics(edge_count),
            "erroneous_merge_pair_count": 0,
            "same_target_split_pair_count": 0,
        },
        "scoring_latency_ms": 0.2,
        "clustering_latency_ms": 0.1,
        "total_latency_ms": 0.3,
        "same_camera_mutual_exclusion_violation_count": 0,
    }


def _full_lineage_fixture() -> tuple[list[dict[str, object]], dict[str, object], dict[str, object]]:
    records: list[dict[str, object]] = []
    episodes: list[dict[str, object]] = []
    for index, (seed, scenario, scale) in enumerate(
        (seed, scenario, scale)
        for seed in range(1000, 1020)
        for scenario in _SCENARIOS
        for scale in _SCALES
    ):
        edge_count = 83 if index < 224 else 82
        uid = f"episode-{index:04d}"
        graph_sha = hashlib.sha256(f"graph:{uid}".encode()).hexdigest()
        label_sha = hashlib.sha256(f"label:{uid}".encode()).hexdigest()
        candidate_sha = hashlib.sha256(f"candidate:{uid}".encode()).hexdigest()
        arrays_sha = hashlib.sha256(f"arrays:{uid}".encode()).hexdigest()
        evaluator_label_sha = hashlib.sha256(f"eval:{uid}".encode()).hexdigest()
        episodes.append(
            {
                "episode_uid": uid,
                "seed": seed,
                "scenario": scenario,
                "scale": scale,
                "edge_count": edge_count,
                "graph_sha256": graph_sha,
                "labels_sha256": label_sha,
            }
        )
        records.append(
            {
                "schema_version": "d5.tracklet-paired-shadow-lineage.v1",
                "episode_uid": uid,
                "seed": seed,
                "scenario": scenario,
                "scale": scale,
                "loaded_graph_instance_count": 1,
                "graph_sha256": graph_sha,
                "control_graph_sha256": graph_sha,
                "model_graph_sha256": graph_sha,
                "labels_sha256": label_sha,
                "control_labels_sha256": label_sha,
                "model_labels_sha256": label_sha,
                "control_candidate_edge_sha256": candidate_sha,
                "model_candidate_edge_sha256": candidate_sha,
                "source_arrays_sha256": arrays_sha,
                "shared_arrays_sha256": arrays_sha,
                "graph_after_control_sha256": arrays_sha,
                "graph_after_model_sha256": arrays_sha,
                "graph_after_clustering_sha256": arrays_sha,
                "evaluator_labels_before_sha256": evaluator_label_sha,
                "evaluator_labels_after_sha256": evaluator_label_sha,
                "graph_identity_match": True,
                "candidate_identity_match": True,
                "label_identity_match": True,
                "truth_scoring_started_after_both_arm_predictions": True,
                "same_camera_candidate_edge_count": 0,
                "candidate_edge_count": edge_count,
                "labeled_candidate_edge_count": edge_count,
                "unlabeled_candidate_edge_count": 0,
                "candidate_recall_numerator": edge_count,
                "candidate_recall_denominator": edge_count,
                "candidate_recall": 1.0,
                "node_count": 2,
                "control": _arm(edge_count),
                "model": _arm(edge_count),
            }
        )
    manifest = {"episodes": episodes}
    report = {
        "graph_identity": {
            "episode_count": 900,
            "same_loaded_graph_sent_to_both_arms_count": 900,
            "graph_identity_match_count": 900,
            "candidate_identity_match_count": 900,
            "label_identity_match_count": 900,
            "graph_identity_ratio": 1.0,
            "candidate_identity_ratio": 1.0,
            "label_identity_ratio": 1.0,
            "model_candidate_edges_added_or_removed": 0,
        }
    }
    return records, manifest, report


def test_single_feature_screen_flags_synthetic_separability() -> None:
    values = np.asarray([0.0] * 30 + [1.0] * 70)
    labels = np.asarray([True] * 30 + [False] * 70)

    result = screen_single_feature_separability(values, labels)

    assert result["near_perfect_separation"] is True
    assert result["best_threshold_rule"]["f1"] == pytest.approx(1.0)
    assert result["best_threshold_rule"]["balanced_accuracy"] == pytest.approx(1.0)
    assert result["univariate_auc"]["best_direction_auc"] == pytest.approx(1.0)


def test_single_feature_screen_marks_constant_center_cue_unavailable() -> None:
    values = np.zeros(100)
    labels = np.asarray([True] * 30 + [False] * 70)

    result = screen_single_feature_separability(values, labels)

    assert result["unique_value_count"] == 1
    assert result["univariate_auc"] == {
        "available": False,
        "auc": None,
        "best_direction_auc": None,
        "direction": None,
        "reason": "feature_constant",
    }
    assert result["near_perfect_separation"] is False


def test_lineage_validator_accepts_exact_900_frame_catalog() -> None:
    records, manifest, report = _full_lineage_fixture()

    result = validate_paired_lineage_records(
        records,
        report=report,
        corpus_manifest=manifest,
    )

    assert result["record_count"] == 900
    assert result["candidate_edge_count"] == 74_024
    assert result["control_model_graph_identity_ratio"] == 1.0
    assert result["candidate_edges_added_or_removed"] == 0


def test_lineage_validator_rejects_duplicate_episode() -> None:
    records, manifest, report = _full_lineage_fixture()
    records[1]["episode_uid"] = records[0]["episode_uid"]

    with pytest.raises(D5PairedShadowAuditError) as error:
        validate_paired_lineage_records(
            records,
            report=report,
            corpus_manifest=manifest,
        )

    assert error.value.code == "lineage_duplicate_episode"


def test_lineage_validator_rejects_graph_mutation_between_arms() -> None:
    records, manifest, report = _full_lineage_fixture()
    records[0]["graph_after_model_sha256"] = "f" * 64

    with pytest.raises(D5PairedShadowAuditError) as error:
        validate_paired_lineage_records(
            records,
            report=report,
            corpus_manifest=manifest,
        )

    assert error.value.code == "lineage_graph_mutation_detected"


def test_content_sha_validator_rejects_authenticated_payload_tamper() -> None:
    payload = {"schema_version": "fixture.v1", "value": 3}
    payload["content_sha256"] = audit_module._sha256_json(payload)
    audit_module._validate_content_sha256(payload, "fixture")
    payload["value"] = 4

    with pytest.raises(D5PairedShadowAuditError) as error:
        audit_module._validate_content_sha256(payload, "fixture")

    assert error.value.code == "content_sha256_mismatch"


def test_input_contract_requires_out_of_band_sha256(tmp_path) -> None:
    kwargs = {
        name: tmp_path / name
        for name in (
            "paired_report_path",
            "paired_lineage_path",
            "heldout_corpus_dir",
            "heldout_report_path",
            "model_bundle_dir",
            "d5_source_dir",
            "superseded_report_path",
            "superseded_lineage_path",
            "output_dir",
        )
    }
    kwargs.update(
        {
            name: "a" * 64
            for name in (
                "expected_paired_report_sha256",
                "expected_paired_report_content_sha256",
                "expected_paired_lineage_sha256",
                "expected_corpus_manifest_sha256",
                "expected_corpus_content_sha256",
                "expected_corpus_config_sha256",
                "expected_heldout_report_sha256",
                "expected_heldout_report_content_sha256",
                "expected_bundle_manifest_sha256",
                "expected_bundle_weights_sha256",
                "expected_bundle_checksums_sha256",
                "expected_superseded_report_sha256",
                "expected_superseded_lineage_sha256",
            )
        }
    )
    kwargs["expected_paired_report_sha256"] = "not-a-sha"
    kwargs["audited_at_utc"] = "2026-07-22T00:00:00Z"

    with pytest.raises(D5PairedShadowAuditError) as error:
        D5PairedShadowAuditInputs(**kwargs)

    assert error.value.code == "invalid_out_of_band_sha256"


def test_snapshot_evidence_reports_actual_before_and_after_hashes(tmp_path) -> None:
    critical_paths = {"paired_report": tmp_path / "report.json"}
    implementation_paths = {"d5_source/module.py": tmp_path / "module.py"}
    before = {
        "paired_report": "a" * 64,
        "d5_source/module.py": "b" * 64,
    }
    after = {
        "paired_report": "a" * 64,
        "d5_source/module.py": "c" * 64,
    }

    evidence = audit_module._snapshot_evidence(
        before,
        after,
        critical_paths,
        implementation_paths,
    )

    assert evidence["input_artifact_set_sha256_before"] != evidence[
        "input_artifact_set_sha256_after"
    ]
    assert evidence["critical_file_sha256"] == {"paired_report": "a" * 64}
    assert evidence["critical_file_sha256_after"] == {"paired_report": "a" * 64}
    assert evidence["implementation_binding_count"] == 1
    assert evidence["implementation_file_sha256"] == {
        "d5_source/module.py": "b" * 64
    }
    assert evidence["implementation_file_sha256_after"] == {
        "d5_source/module.py": "c" * 64
    }
