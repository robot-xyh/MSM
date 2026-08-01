from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest

import d1_sensor_fusion.fusion as fusion_module
from d1_sensor_fusion import (
    ASSOCIATION_RISK_CLASSIFICATION_AUDIT_SCHEMA_VERSION,
    ASSOCIATION_RISK_CLASSIFICATION_CRITERIA,
    ASSOCIATION_RISK_CLASSIFICATION_POLICY_VERSION,
    ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION,
    ASSOCIATION_RISK_CLASSIFICATION_SCHEMA_VERSION,
    AssociationRiskClassificationEvidence,
    AssociationRiskEvidence,
    FusionAdapter,
    SensorObservation,
)
from d1_sensor_fusion.observations import (
    MeasurementModel,
    radar_covariance_from_range,
    radar_h,
)


CAMERA = {
    "position_ned": [0.0, 0.0, 0.0],
    "rotation_world_to_camera": np.eye(3, dtype=float).tolist(),
    "intrinsics": {
        "fx": 1_000.0,
        "fy": 1_000.0,
        "cx": 960.0,
        "cy": 540.0,
        "width": 1_920,
        "height": 1_080,
    },
}


def _radar(index: int, state: np.ndarray, *, scan_id: str = "radar-seed") -> SensorObservation:
    measurement = radar_h(state, np.zeros(3, dtype=float))
    return SensorObservation(
        observation_id=f"anonymous-radar-{index}",
        sensor_id="anonymous-radar",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.05,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(float(measurement[0])),
        confidence=0.95,
        metadata={"sensor_position_ned": [0.0, 0.0, 0.0], "scan_id": scan_id},
    )


def _eo(
    index: int,
    pixel: tuple[float, float] = (960.0, 540.0),
    *,
    bbox: tuple[float, float, float, float] | None = None,
    confidence: float = 0.9,
    truth_marker: str | None = None,
) -> SensorObservation:
    if bbox is None:
        bbox = (940.0 + index, 520.0, 980.0 + index, 560.0)
    metadata = {
        "camera_model": CAMERA,
        "camera_id": "anonymous-camera",
        "scan_id": "eo-risk-scan",
        "bbox": list(bbox),
    }
    if truth_marker is not None:
        metadata["truth_id"] = truth_marker
        metadata["actor_name"] = f"actor-{truth_marker}"
    return SensorObservation(
        observation_id=f"anonymous-eo-{index}",
        sensor_id="anonymous-camera",
        modality="eo",
        measurement_timestamp=0.1,
        arrival_timestamp=0.15,
        frame_id="pixel",
        measurement=np.asarray(pixel, dtype=float),
        covariance=np.eye(2, dtype=float),
        confidence=confidence,
        metadata=metadata,
    )


def _seed(adapter: FusionAdapter, states: list[np.ndarray]) -> None:
    adapter.process_scan_batch(
        [_radar(index, state) for index, state in enumerate(states)],
        materialize_tracks=False,
    )


def _singular_state(x: float = 20.0, y: float = 0.0) -> np.ndarray:
    return np.array([x, y, 0.002, 0.0, 0.0, 0.0], dtype=float)


def _positive_composite_evidence() -> AssociationRiskEvidence:
    adapter = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
    )
    _seed(
        adapter,
        [
            _singular_state(),
            np.array([4.0, 0.0, 100.0, 0.0, 0.0, 0.0], dtype=float),
        ],
    )
    result = adapter.process_scan_batch(
        [
            _eo(
                0,
                bbox=(959.0, 539.0, 961.0, 541.0),
                confidence=0.10,
            )
        ],
        materialize_tracks=False,
    )
    assert len(result.association_risk_evidence) == 1
    return result.association_risk_evidence[0]


def test_00061_type_low_nis_out_of_frame_projection_emits_shadow_evidence() -> None:
    adapter = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
    )
    _seed(adapter, [_singular_state()])

    result = adapter.process_scan_batch([_eo(0)], materialize_tracks=False)

    assert result.summary.accepted_observation_count == 1
    assert len(result.association_risk_evidence) == 1
    assert len(result.association_risk_classifications) == 1
    evidence = result.association_risk_evidence[0]
    edge = next(item for item in evidence.candidate_edges if item.selected)
    assert edge.nis < 1.0e-3
    assert edge.raw_pixel_residual_norm > 1.0e6
    assert edge.forward_depth_m < 0.01
    assert edge.projection_in_frame is False
    assert edge.innovation_covariance_condition_number >= 1.0e8
    assert {
        "projection_out_of_frame",
        "near_projection_singularity",
        "ill_conditioned_innovation",
    }.issubset(evidence.risk_reasons)
    assert evidence.measurement_timestamp == 0.1
    assert evidence.arrival_timestamp == 0.15
    assert evidence.frame_id == "NED"
    assert evidence.online_truth_used is False
    assert evidence.decision == "evidence_only"
    assert result.association_risk_classifications[0].classification == "negative"


def test_normal_in_frame_eo_does_not_emit_risk_evidence() -> None:
    adapter = FusionAdapter(association_risk_evidence_shadow=True)
    _seed(
        adapter,
        [np.array([20.0, 0.0, 100.0, 0.0, 0.0, 0.0], dtype=float)],
    )
    expected_pixel = (1_160.0, 540.0)

    result = adapter.process_scan_batch(
        [_eo(0, expected_pixel)],
        materialize_tracks=False,
    )

    assert result.summary.accepted_observation_count == 1
    assert result.association_risk_evidence == ()
    assert result.association_risk_classifications == ()


def test_shadow_keeps_assignments_state_covariance_and_metadata_identical() -> None:
    baseline = FusionAdapter(association_gate=40.0)
    shadow = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
    )
    _seed(baseline, [_singular_state()])
    _seed(shadow, [_singular_state()])

    baseline_result = baseline.process_scan_batch([_eo(0)])
    shadow_result = shadow.process_scan_batch([_eo(0)])
    assert "association_risk_evidence" not in baseline_result.to_dict()
    shadow_payload = shadow_result.to_dict()
    assert len(shadow_payload.pop("association_risk_evidence")) == 1
    assert len(shadow_payload.pop("association_risk_classifications")) == 1

    assert shadow_payload == baseline_result.to_dict()
    assert shadow_result.summary.to_dict() == baseline_result.summary.to_dict()
    assert shadow.tracks["global_track_001"].hits == baseline.tracks["global_track_001"].hits
    assert shadow.tracks["global_track_001"].metadata == baseline.tracks["global_track_001"].metadata


def test_evidence_roundtrip_uses_exact_keys_and_rejects_truth_fields() -> None:
    adapter = FusionAdapter(association_risk_evidence_shadow=True)
    _seed(adapter, [_singular_state()])
    evidence = adapter.process_scan_batch([_eo(0)]).association_risk_evidence[0]
    payload = json.loads(json.dumps(evidence.to_dict()))

    assert set(payload) == {
        "schema_version",
        "evidence_id",
        "publisher_generation",
        "publisher_node_id",
        "publisher_epoch",
        "measurement_timestamp",
        "arrival_timestamp",
        "published_at",
        "sensor_id",
        "modality",
        "scan_id",
        "observation_evidence_key",
        "selected_opaque_member_track_token",
        "selected_source_key",
        "candidate_edges",
        "first_candidate_cost",
        "second_candidate_cost",
        "assignment_margin",
        "valid_candidate_count",
        "top_k_limit",
        "measurement_covariance_px2",
        "bbox_area_px2",
        "confidence",
        "risk_reasons",
        "threshold_profile_version",
        "policy_version",
        "frame_id",
        "measurement_frame_id",
        "decision",
        "mode",
        "online_truth_used",
        "posterior_update_applied",
    }
    assert AssociationRiskEvidence.from_dict(payload).to_dict() == payload
    with_truth = deepcopy(payload)
    with_truth["truth_id"] = "forbidden"
    with pytest.raises(ValueError, match="unknown"):
        AssociationRiskEvidence.from_dict(with_truth)
    nested_truth = deepcopy(payload)
    nested_truth["candidate_edges"][0]["actor_id"] = "forbidden"
    with pytest.raises(ValueError, match="unknown"):
        AssociationRiskEvidence.from_dict(nested_truth)
    bad_candidate_source = deepcopy(payload)
    candidate = bad_candidate_source["candidate_edges"][0]
    candidate["source_key"] = (
        f"wrong-node::{payload['publisher_epoch']}::"
        f"{candidate['opaque_member_track_token']}"
    )
    with pytest.raises(ValueError, match="candidate edge source_key must equal"):
        AssociationRiskEvidence.from_dict(bad_candidate_source)
    bad_selected_source = deepcopy(payload)
    bad_selected_source["selected_source_key"] = (
        f"wrong-node::{payload['publisher_epoch']}::"
        f"{payload['selected_opaque_member_track_token']}"
    )
    with pytest.raises(ValueError, match="selected_source_key must equal"):
        AssociationRiskEvidence.from_dict(bad_selected_source)


def test_risk_identity_matches_published_global_track_source_identity() -> None:
    adapter = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
        publish_opaque_source_key=True,
        publisher_node_id="D1_RISK_TEST_NODE",
        publisher_epoch="episode-risk-binding-001",
    )
    _seed(adapter, [_singular_state()])

    result = adapter.process_scan_batch([_eo(0)])

    evidence = result.association_risk_evidence[0]
    selected_edge = next(edge for edge in evidence.candidate_edges if edge.selected)
    selected_track = next(
        track
        for track in result.tracks
        if track.metadata["opaque_member_track_token"]
        == evidence.selected_opaque_member_track_token
    )
    assert evidence.selected_opaque_member_track_token == (
        selected_track.metadata["opaque_member_track_token"]
    )
    assert evidence.selected_source_key == selected_track.metadata["source_key"]
    assert selected_edge.opaque_member_track_token == (
        selected_track.metadata["opaque_member_track_token"]
    )
    assert selected_edge.source_key == selected_track.metadata["source_key"]
    payload = json.loads(json.dumps(evidence.to_dict()))
    assert AssociationRiskEvidence.from_dict(payload).to_dict() == payload


def test_truth_metadata_does_not_change_online_risk_key_or_decision() -> None:
    left = FusionAdapter(association_risk_evidence_shadow=True)
    right = FusionAdapter(association_risk_evidence_shadow=True)
    _seed(left, [_singular_state()])
    _seed(right, [_singular_state()])

    left_evidence = left.process_scan_batch(
        [_eo(0, truth_marker="left")]
    ).association_risk_evidence[0]
    right_evidence = right.process_scan_batch(
        [_eo(0, truth_marker="right")]
    ).association_risk_evidence[0]

    assert left_evidence.to_dict() == right_evidence.to_dict()
    left_classification = left._latest_association_risk_classifications[0]
    right_classification = right._latest_association_risk_classifications[0]
    assert left_classification.to_dict() == right_classification.to_dict()


def test_observation_risk_keys_are_permutation_stable() -> None:
    adapter = FusionAdapter(association_risk_evidence_shadow=True)
    observations = [_eo(0, (960.0, 540.0)), _eo(1, (980.0, 545.0))]

    forward = adapter._association_risk_observation_keys(observations)
    reverse = adapter._association_risk_observation_keys(list(reversed(observations)))

    assert forward[0] == reverse[1]
    assert forward[1] == reverse[0]


def test_two_hundred_tracks_keep_top_k_and_per_scan_evidence_bounded() -> None:
    adapter = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
        association_risk_top_k=3,
        association_risk_max_evidence_per_scan=2,
    )
    states = [
        _singular_state(10.0 + float(index), 0.05 * float(index))
        for index in range(200)
    ]
    _seed(adapter, states)
    observations = [
        _eo(index, (960.0 + index, 540.0))
        for index in range(6)
    ]

    result = adapter.process_scan_batch(observations, materialize_tracks=False)
    audit = adapter.association_risk_evidence_audit()
    classification_audit = adapter.association_risk_classification_audit()

    assert len(result.association_risk_evidence) == 2
    assert len(result.association_risk_classifications) == 2
    assert all(len(item.candidate_edges) <= 3 for item in result.association_risk_evidence)
    assert all(item.valid_candidate_count > 3 for item in result.association_risk_evidence)
    assert audit["suppressed_by_limit_count"] >= 1
    assert classification_audit["evaluated_raw_evidence_count"] == 2
    assert classification_audit["published_classification_count"] == 2
    assert classification_audit["max_classifications_per_scan"] == 2


def test_composite_profile_classifies_boundary_values_positive() -> None:
    adapter = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
    )
    _seed(
        adapter,
        [
            _singular_state(),
            np.array([4.0, 0.0, 100.0, 0.0, 0.0, 0.0], dtype=float),
        ],
    )

    result = adapter.process_scan_batch(
        [
            _eo(
                0,
                bbox=(959.0, 539.0, 961.0, 541.0),
                confidence=0.10,
            )
        ],
        materialize_tracks=False,
    )

    evidence = result.association_risk_evidence[0]
    classification = result.association_risk_classifications[0]
    assert evidence.valid_candidate_count == 2
    assert evidence.bbox_area_px2 == 4.0
    assert evidence.confidence == 0.10
    assert classification.evidence_id == evidence.evidence_id
    assert classification.observation_evidence_key == evidence.observation_evidence_key
    assert classification.selected_source_key == evidence.selected_source_key
    assert classification.measurement_timestamp == evidence.measurement_timestamp
    assert classification.arrival_timestamp == evidence.arrival_timestamp
    assert classification.published_at == evidence.published_at
    assert classification.profile_version == (
        "d1-eo-pathological-projection-composite-development-v2"
    )
    assert classification.profile_version == (
        ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION
    )
    assert classification.classification == "positive"
    assert classification.matched_criteria == ASSOCIATION_RISK_CLASSIFICATION_CRITERIA
    assert classification.unmatched_criteria == ()
    assert classification.mode == "shadow"
    assert classification.decision == "evidence_only"
    assert classification.online_truth_used is False
    assert classification.posterior_update_applied is False

    audit = adapter.association_risk_classification_audit()
    assert audit == {
        "schema_version": ASSOCIATION_RISK_CLASSIFICATION_AUDIT_SCHEMA_VERSION,
        "enabled": True,
        "mode": "shadow",
        "decision": "evidence_only",
        "profile_version": (
            "d1-eo-pathological-projection-composite-development-v2"
        ),
        "evaluated_raw_evidence_count": 1,
        "positive_classification_count": 1,
        "negative_classification_count": 0,
        "published_classification_count": 1,
        "max_classifications_per_scan": 32,
        "online_truth_used": False,
        "posterior_update_applied": False,
    }


def _classify_modified_evidence(
    evidence: AssociationRiskEvidence,
) -> AssociationRiskClassificationEvidence:
    adapter = FusionAdapter(association_risk_evidence_shadow=True)
    return adapter._classify_association_risk_evidence((evidence,))[0]


def test_each_composite_criterion_failure_stays_negative() -> None:
    evidence = _positive_composite_evidence()
    selected = next(edge for edge in evidence.candidate_edges if edge.selected)
    alternatives = tuple(edge for edge in evidence.candidate_edges if not edge.selected)
    assert alternatives

    no_second_candidate = replace(
        evidence,
        candidate_edges=(selected,),
        valid_candidate_count=1,
        second_candidate_cost=None,
        assignment_margin=None,
    )
    selected_in_frame = replace(
        evidence,
        candidate_edges=tuple(
            replace(edge, projection_in_frame=True) if edge.selected else edge
            for edge in evidence.candidate_edges
        ),
    )
    no_in_frame_alternative = replace(
        evidence,
        candidate_edges=tuple(
            edge
            if edge.selected
            else replace(edge, projection_in_frame=False)
            for edge in evidence.candidate_edges
        ),
    )
    oversized_bbox = replace(evidence, bbox_area_px2=4.000001)
    high_confidence = replace(evidence, confidence=0.100001)

    cases = (
        (no_second_candidate, "valid_candidate_count_gte_2"),
        (selected_in_frame, "selected_projection_out_of_frame"),
        (
            no_in_frame_alternative,
            "retained_alternative_projection_in_frame",
        ),
        (oversized_bbox, "bbox_area_px2_lte_4_0"),
        (high_confidence, "confidence_lte_0_10"),
    )
    for modified, failed_criterion in cases:
        classification = _classify_modified_evidence(modified)
        assert classification.classification == "negative"
        assert failed_criterion in classification.unmatched_criteria
        assert failed_criterion not in classification.matched_criteria


def test_classification_roundtrip_uses_exact_independent_contract() -> None:
    evidence = _positive_composite_evidence()
    classification = _classify_modified_evidence(evidence)
    payload = json.loads(json.dumps(classification.to_dict()))

    assert set(payload) == {
        "schema_version",
        "classification_id",
        "evidence_id",
        "publisher_node_id",
        "publisher_epoch",
        "measurement_timestamp",
        "arrival_timestamp",
        "published_at",
        "observation_evidence_key",
        "selected_opaque_member_track_token",
        "selected_source_key",
        "classification",
        "matched_criteria",
        "unmatched_criteria",
        "profile_version",
        "policy_version",
        "decision",
        "mode",
        "online_truth_used",
        "posterior_update_applied",
    }
    assert payload["schema_version"] == ASSOCIATION_RISK_CLASSIFICATION_SCHEMA_VERSION
    assert payload["profile_version"] == ASSOCIATION_RISK_CLASSIFICATION_PROFILE_VERSION
    assert payload["policy_version"] == ASSOCIATION_RISK_CLASSIFICATION_POLICY_VERSION
    assert AssociationRiskClassificationEvidence.from_dict(payload).to_dict() == payload

    with_truth = deepcopy(payload)
    with_truth["truth_id"] = "forbidden"
    with pytest.raises(ValueError, match="unknown"):
        AssociationRiskClassificationEvidence.from_dict(with_truth)

    inconsistent = deepcopy(payload)
    inconsistent["classification"] = "negative"
    with pytest.raises(ValueError, match="positive only"):
        AssociationRiskClassificationEvidence.from_dict(inconsistent)

    tampered_id = deepcopy(payload)
    tampered_id["classification_id"] = (
        "d1-risk-classification-sha256:" + "0" * 64
    )
    with pytest.raises(ValueError, match="does not match"):
        AssociationRiskClassificationEvidence.from_dict(tampered_id)


def test_default_off_publishes_no_raw_or_classification_sidecar() -> None:
    adapter = FusionAdapter(association_gate=40.0)
    _seed(adapter, [_singular_state()])

    result = adapter.process_scan_batch([_eo(0)], materialize_tracks=False)

    assert result.association_risk_evidence == ()
    assert result.association_risk_classifications == ()
    payload = result.to_dict()
    assert "association_risk_evidence" not in payload
    assert "association_risk_classifications" not in payload
    audit = adapter.association_risk_classification_audit()
    assert audit["enabled"] is False
    assert audit["mode"] == "disabled"
    assert audit["evaluated_raw_evidence_count"] == 0
    assert audit["positive_classification_count"] == 0
    assert audit["profile_version"] == (
        "d1-eo-pathological-projection-composite-development-v2"
    )


def test_positive_shadow_classification_keeps_posterior_and_assignment_identical() -> None:
    baseline = FusionAdapter(association_gate=40.0)
    shadow = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
    )
    states = [
        _singular_state(),
        np.array([4.0, 0.0, 100.0, 0.0, 0.0, 0.0], dtype=float),
    ]
    _seed(baseline, states)
    _seed(shadow, states)
    observation = _eo(
        0,
        bbox=(959.0, 539.0, 961.0, 541.0),
        confidence=0.10,
    )

    baseline_result = baseline.process_scan_batch([observation])
    shadow_result = shadow.process_scan_batch([observation])
    shadow_payload = shadow_result.to_dict()
    assert shadow_payload.pop("association_risk_classifications")[0][
        "classification"
    ] == "positive"
    shadow_payload.pop("association_risk_evidence")

    assert shadow_payload == baseline_result.to_dict()
    assert shadow_result.summary.to_dict() == baseline_result.summary.to_dict()
    assert set(shadow.tracks) == set(baseline.tracks)
    for track_id in baseline.tracks:
        left = baseline.tracks[track_id]
        right = shadow.tracks[track_id]
        np.testing.assert_allclose(right.current_state.state, left.current_state.state)
        np.testing.assert_allclose(
            right.current_state.covariance,
            left.current_state.covariance,
        )
        assert right.hits == left.hits
        assert right.metadata == left.metadata


def test_camera_behind_candidate_cannot_interrupt_shadow_fusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = FusionAdapter(association_gate=40.0)
    shadow = FusionAdapter(
        association_gate=40.0,
        association_risk_evidence_shadow=True,
    )
    behind_camera = np.array([0.0, 0.0, -100.0, 0.0, 0.0, 0.0], dtype=float)
    _seed(baseline, [behind_camera])
    _seed(shadow, [behind_camera])
    observation = _eo(0)
    model = MeasurementModel(
        z=observation.measurement.copy(),
        r=observation.covariance.copy(),
        h_fn=lambda state: observation.measurement.copy(),
        h_jacobian_fn=lambda state: np.zeros((2, 6), dtype=float),
    )
    monkeypatch.setattr(
        fusion_module,
        "measurement_model_for",
        lambda *args, **kwargs: model,
    )

    baseline_result = baseline.process_scan_batch([observation])
    shadow_result = shadow.process_scan_batch([observation])

    assert shadow_result.association_risk_evidence == ()
    assert shadow_result.association_risk_classifications == ()
    assert shadow_result.to_dict() == baseline_result.to_dict()
    np.testing.assert_allclose(
        shadow.tracks["global_track_001"].current_state.state,
        baseline.tracks["global_track_001"].current_state.state,
    )
    np.testing.assert_allclose(
        shadow.tracks["global_track_001"].current_state.covariance,
        baseline.tracks["global_track_001"].current_state.covariance,
    )


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_shadow_switch_requires_a_strict_bool(value: object) -> None:
    with pytest.raises(TypeError, match="association_risk_evidence_shadow must be a bool"):
        FusionAdapter(association_risk_evidence_shadow=value)  # type: ignore[arg-type]
