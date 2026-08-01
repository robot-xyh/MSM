from __future__ import annotations

import json

import numpy as np
import pytest

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    ASSOCIATION_RISK_CLASSIFICATION_CRITERIA,
    ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION,
    AssociationRiskCandidateEdge,
    AssociationRiskClassificationEvidence,
    AssociationRiskEvidence,
    association_risk_classification_id,
    structural_ambiguity_member_track_token,
    structural_ambiguity_source_key,
)
from research_modules.scalable_3d_simulation.d1_association_risk_calibration import (
    AssociationRiskCalibrationCase,
    run_d1_association_risk_calibration,
)
from research_modules.scalable_3d_simulation.run_d1_association_risk_calibration import (
    _camera_caused_multi_truth_events,
    _discover_diagnostic_cases,
)


def test_calibration_flags_reference_and_preserves_shadow_boundary(tmp_path) -> None:
    control_dir = _write_episode(tmp_path / "control", pathological=False)
    failure_dir = _write_episode(tmp_path / "failure", pathological=True)

    paths = run_d1_association_risk_calibration(
        tmp_path / "output",
        cases=(
            AssociationRiskCalibrationCase("control", control_dir),
            AssociationRiskCalibrationCase(
                "failure",
                failure_dir,
                expected_failure_events=(("CAM-RECON-001", 1.8),),
            ),
        ),
    )

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["evidence_class"] == "development_offline_shadow_calibration"
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert summary["evidence_count"] == 2
    assert summary["warning_count"] == 1
    assert summary["failed_event_recall"] == 1.0
    assert summary["passing_control_warning_rate"] == 0.0
    assert (
        summary["sample_sufficiency"][
            "sufficient_for_shadow_classification_review"
        ]
        is False
    )
    assert summary["sample_sufficiency"]["sufficient_for_enforcement"] is False
    assert summary["recommendation"].startswith("remain_raw_shadow")
    assert summary["online_truth_used"] is False
    assert summary["online_decision_applied"] is False
    assert summary["d1_posterior_changed"] is False
    assert summary["d2_enforcement_changed"] is False
    assert manifest["online_truth_used"] is False
    assert manifest["online_decision_applied"] is False
    rows_text = paths["rows"].read_text(encoding="utf-8")
    assert rows_text.count("\n") == 3
    assert "\r" not in rows_text


def test_calibration_rejects_opaque_source_publication_confounder(tmp_path) -> None:
    episode_dir = _write_episode(tmp_path / "episode", pathological=True)
    manifest_path = episode_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime_profile"]["configuration"][
        "d1_publish_opaque_source_key"
    ] = True
    _write_json(manifest_path, manifest)

    with pytest.raises(ValueError, match="confounds calibration"):
        run_d1_association_risk_calibration(
            tmp_path / "output",
            cases=(AssociationRiskCalibrationCase("episode", episode_dir),),
        )


def test_calibration_records_why_an_expected_event_was_missed(tmp_path) -> None:
    episode_dir = _write_episode(tmp_path / "miss", pathological=False)
    paths = run_d1_association_risk_calibration(
        tmp_path / "miss-output",
        cases=(
            AssociationRiskCalibrationCase(
                "miss",
                episode_dir,
                expected_failure_events=(("CAM-RECON-001", 1.8),),
            ),
        ),
    )

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    diagnostic = summary["cases"][0]["missed_failure_event_diagnostics"][0]
    assert diagnostic["reason"] == "required_composite_criteria_not_met"
    assert diagnostic["unmatched_required_checks"] == [
        "bbox_area_within_limit",
        "confidence_within_limit",
    ]
    assert summary["missed_failure_reason_counts"] == {
        "bbox_area_within_limit": 1,
        "confidence_within_limit": 1,
    }


def test_held_out_requires_and_verifies_online_classification_dto(tmp_path) -> None:
    missing_dir = _write_episode(tmp_path / "missing", pathological=True)
    with pytest.raises(ValueError, match="classifications are incomplete"):
        run_d1_association_risk_calibration(
            tmp_path / "missing-output",
            cases=(
                AssociationRiskCalibrationCase(
                    "missing",
                    missing_dir,
                    expected_failure_events=(("CAM-RECON-001", 1.8),),
                ),
            ),
            validation_role="held_out",
            require_online_classifications=True,
        )

    classified_dir = _write_episode(
        tmp_path / "classified",
        pathological=True,
        include_classification=True,
    )
    paths = run_d1_association_risk_calibration(
        tmp_path / "classified-output",
        cases=(
            AssociationRiskCalibrationCase(
                "classified",
                classified_dir,
                expected_failure_events=(("CAM-RECON-001", 1.8),),
            ),
        ),
        validation_role="held_out",
        require_online_classifications=True,
    )

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["validation_role"] == "held_out"
    assert summary["evidence_class"] == "held_out_offline_shadow_validation"
    report = paths["report"].read_text(encoding="utf-8")
    assert "# D1 光电关联风险独立留出验证" in report
    assert "未达到样本数量下限" in report
    assert summary["online_classification_record_count"] == 1
    assert summary["online_classification_profile_match_count"] == 1
    assert summary["online_classifier_complete"] is True
    assert (
        summary["sample_sufficiency"][
            "held_out_independent_validation_available"
        ]
        is False
    )
    assert summary["sample_sufficiency"]["reason"] == (
        "count_or_performance_requirement_not_met"
    )


def test_camera_failure_event_extraction_uses_offline_d2_causal_evidence() -> None:
    diagnostics = {
        "causal_mapping_events": [
            {
                "reason": "multiple_truth_targets_for_global_track",
                "sensor_transition": {
                    "newest_modalities": ["camera"],
                },
                "source_observations": [
                    {
                        "is_newest_measurement": True,
                        "sensor_modality": "camera",
                        "sensor_id": "CAM-RECON-004",
                        "measurement_timestamp": 1.8,
                    },
                    {
                        "is_newest_measurement": False,
                        "sensor_modality": "radar",
                        "sensor_id": "RADAR-CENTER-001",
                        "measurement_timestamp": 1.6,
                    },
                ],
            },
            {
                "reason": "source_observation_outside_lineage_window",
                "sensor_transition": {
                    "newest_modalities": ["camera"],
                },
                "source_observations": [],
            },
        ]
    }

    assert _camera_caused_multi_truth_events(diagnostics) == (
        ("CAM-RECON-004", 1.8),
    )


def test_diagnostic_discovery_reads_v3_identity_boundary(tmp_path) -> None:
    episode_root = tmp_path / "episodes"
    episode_parent = episode_root / "100v100"
    episode_parent.mkdir(parents=True)
    episode_dir = _write_episode(
        episode_parent / "seed_2000",
        pathological=True,
        include_classification=True,
    )
    diagnostics_root = tmp_path / "diagnostics"
    (diagnostics_root / "episodes").mkdir(parents=True)
    diagnostics = {
        "episode_id": "episode-failure",
        "identity_boundary": {
            "online_truth_isolation_verified": True,
            "usage": "offline_evaluation_only",
            "identity_heuristics_used": False,
        },
        "causal_mapping_events": [
            {
                "reason": "multiple_truth_targets_for_global_track",
                "sensor_transition": {"newest_modalities": ["camera"]},
                "source_observations": [
                    {
                        "is_newest_measurement": True,
                        "sensor_modality": "camera",
                        "sensor_id": "CAM-RECON-001",
                        "measurement_timestamp": 1.8,
                    }
                ],
            }
        ],
    }
    _write_json(
        diagnostics_root
        / "episodes"
        / "episode-failure_identity_blockers.json",
        diagnostics,
    )

    paths, events, skipped = _discover_diagnostic_cases(
        episode_root,
        episode_glob="*/*",
        diagnostics_root=diagnostics_root,
    )

    assert paths == {"100v100__seed_2000": episode_dir}
    assert events == {
        "100v100__seed_2000": [("CAM-RECON-001", 1.8)]
    }
    assert skipped == 0


def _write_episode(path, *, pathological: bool, include_classification: bool = False):
    path.mkdir()
    (path / "offline_identity").mkdir()
    evidence = _evidence(pathological=pathological)
    classification = _classification(evidence, pathological=pathological)
    _write_json(
        path / "manifest.json",
        {
            "episode_id": f"episode-{'failure' if pathological else 'control'}",
            "runtime_profile": {
                "configuration": {
                    "d1_association_risk_evidence_shadow_enabled": True,
                    "d1_publish_opaque_source_key": False,
                }
            },
        },
    )
    _write_json(
        path / "summary.json",
        {"finite_state": True, "online_truth_use_count": 0},
    )
    _write_json(
        path / "observation_governance_audit.json",
        {
            "d1_association_risk_evidence_audit": {
                "enabled": True,
                "mode": "shadow",
                "decision": "evidence_only",
                "online_truth_used": False,
                "evidence_count": 1,
            },
            **(
                {
                    "d1_association_risk_classification_audit": {
                        "enabled": True,
                        "mode": "shadow",
                        "decision": "evidence_only",
                        "online_truth_used": False,
                        "posterior_update_applied": False,
                        "published_classification_count": 1,
                    }
                }
                if include_classification
                else {}
            ),
        },
    )
    _write_json(
        path / "offline_identity" / "identity_evaluation.json",
        {
            "metrics": {
                "truth_metrics_available": not pathological,
                "truth_metrics_reason": (
                    "multiple_truth_targets_for_global_track"
                    if pathological
                    else None
                ),
            }
        },
    )
    record = {
        "payload": {
            "association_risk_evidence_count": 1,
            "association_risk_evidence": [evidence.to_dict()],
            **(
                {
                    "association_risk_classification_count": 1,
                    "association_risk_classifications": [
                        classification.to_dict()
                    ],
                }
                if include_classification
                else {}
            ),
        }
    }
    (path / "offline_identity" / "online_d1_records.jsonl").write_text(
        json.dumps(record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _classification(
    evidence: AssociationRiskEvidence,
    *,
    pathological: bool,
) -> AssociationRiskClassificationEvidence:
    matched = (
        tuple(ASSOCIATION_RISK_CLASSIFICATION_CRITERIA)
        if pathological
        else tuple(ASSOCIATION_RISK_CLASSIFICATION_CRITERIA[:3])
    )
    unmatched = tuple(
        criterion
        for criterion in ASSOCIATION_RISK_CLASSIFICATION_CRITERIA
        if criterion not in matched
    )
    classification = "positive" if pathological else "negative"
    return AssociationRiskClassificationEvidence(
        classification_id=association_risk_classification_id(
            evidence.evidence_id,
            ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION,
            classification,
            matched,
        ),
        evidence_id=evidence.evidence_id,
        publisher_node_id=evidence.publisher_node_id,
        publisher_epoch=evidence.publisher_epoch,
        measurement_timestamp=evidence.measurement_timestamp,
        arrival_timestamp=evidence.arrival_timestamp,
        published_at=evidence.published_at,
        observation_evidence_key=evidence.observation_evidence_key,
        selected_opaque_member_track_token=(
            evidence.selected_opaque_member_track_token
        ),
        selected_source_key=evidence.selected_source_key,
        classification=classification,
        matched_criteria=matched,
        unmatched_criteria=unmatched,
    )


def _evidence(*, pathological: bool) -> AssociationRiskEvidence:
    node = "D1_FUSION"
    epoch = "main-stack-reset-00000001-v1"
    selected_token = structural_ambiguity_member_track_token(
        node, epoch, "global_track_001"
    )
    alternative_token = structural_ambiguity_member_track_token(
        node, epoch, "global_track_002"
    )
    selected = AssociationRiskCandidateEdge(
        opaque_member_track_token=selected_token,
        source_key=structural_ambiguity_source_key(node, epoch, selected_token),
        rank=1,
        selected=True,
        nis=0.1,
        predicted_pixel=np.array([-2000.0, 400.0]),
        raw_pixel_residual_norm=3000.0,
        forward_depth_m=2.0 if pathological else 25.0,
        projection_in_frame=False,
        image_width_px=3840,
        image_height_px=2160,
        innovation_covariance_min_eigenvalue=1.0,
        innovation_covariance_max_eigenvalue=(
            2.0e6 if pathological else 2.0e4
        ),
        innovation_covariance_condition_number=(
            2.0e6 if pathological else 2.0e4
        ),
        projection_ellipse_major_axis_px=10_000.0,
    )
    alternative = AssociationRiskCandidateEdge(
        opaque_member_track_token=alternative_token,
        source_key=structural_ambiguity_source_key(node, epoch, alternative_token),
        rank=2,
        selected=False,
        nis=1.0 if pathological else 15.0,
        predicted_pixel=np.array([1000.0, 800.0]),
        raw_pixel_residual_norm=15.0,
        forward_depth_m=2000.0,
        projection_in_frame=True,
        image_width_px=3840,
        image_height_px=2160,
        innovation_covariance_min_eigenvalue=1.0,
        innovation_covariance_max_eigenvalue=2.0,
        innovation_covariance_condition_number=2.0,
        projection_ellipse_major_axis_px=4.0,
    )
    first_cost = selected.nis
    second_cost = alternative.nis
    return AssociationRiskEvidence(
        evidence_id=(
            f"d1-risk-sha256:{('a' if pathological else 'b') * 64}"
        ),
        publisher_generation=1,
        publisher_node_id=node,
        publisher_epoch=epoch,
        measurement_timestamp=1.8,
        arrival_timestamp=1.88,
        published_at=1.9,
        sensor_id="CAM-RECON-001",
        modality="eo",
        scan_id=f"d1-risk-scan-sha256:{'c' * 64}",
        observation_evidence_key=f"d1-risk-observation-sha256:{'d' * 64}",
        selected_opaque_member_track_token=selected_token,
        selected_source_key=structural_ambiguity_source_key(
            node, epoch, selected_token
        ),
        candidate_edges=(selected, alternative),
        first_candidate_cost=first_cost,
        second_candidate_cost=second_cost,
        assignment_margin=second_cost - first_cost,
        valid_candidate_count=2,
        top_k_limit=3,
        measurement_covariance_px2=np.eye(2),
        bbox_area_px2=3.0 if pathological else 50.0,
        confidence=0.09 if pathological else 0.15,
        risk_reasons=("multiple_gate_candidates", "projection_out_of_frame"),
    )


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
