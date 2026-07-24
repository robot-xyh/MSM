from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from d1_sensor_fusion import FusionAdapter, sensor_observation_from_local_image_track
from d1_sensor_fusion.observations import radar_covariance_from_range, radar_h
from d1_sensor_fusion.types import (
    GlobalTrack as D1GlobalTrack,
    SensorObservation,
    TrackLevel,
)
from d2_data_association.models import Detection
from d3_assignment_planner import AssignmentPlanner, CostModel, CostWeights, PlannerConfig
from d3_assignment_planner.models import ResourceState, TargetTrack
from d5_terminal_association import Assignment as D5Assignment
from d5_terminal_association import CameraModel, GlobalTrack, LocalVisualTrack, TerminalAssociator
from d6_evaluation_metrics import MetricsCollector, TerminalRecord
from integration_contracts import (
    LocalImageTrackObservation,
    assignment_handoff_from_d3,
    canonical_track_from_d1,
    d2_detection_kwargs,
    d5_assignment_kwargs,
)


def test_d1_canonical_track_can_feed_d2_detection_contract() -> None:
    d1_track = D1GlobalTrack(
        global_track_id="G-1",
        state=np.array([10.0, 2.0, -1.0, 1.0, 0.0, 0.0]),
        covariance=np.eye(6),
        timestamp=3.0,
        track_level=TrackLevel.HANDOVER,
        metadata={"frame_id": "ned", "valid_at": 3.0, "published_at": 3.1, "track_version": 7},
    )

    canonical = canonical_track_from_d1(d1_track)
    detection = Detection(**d2_detection_kwargs(canonical, detection_id="D-1", truth_id="eval-A"))

    assert canonical.global_track_id == "G-1"
    assert canonical.track_version == 7
    assert detection.metadata["frame_id"] == "ned"
    assert detection.metadata["global_track_id"] == "G-1"
    np.testing.assert_allclose(detection.position, np.array([10.0, 2.0]))


def test_d5_local_lineage_reaches_d2_without_pixel_measurements() -> None:
    local_track = LocalImageTrackObservation(
        sensor_id="eo-camera-01",
        stream_id="visible-main",
        local_track_id="local-003",
        local_epoch=2,
        spectral_band="visible",
        measurement_timestamp=0.1,
        arrival_timestamp=0.15,
        center_px=np.array([640.25, 359.75]),
        bbox_xyxy=(620.0, 340.0, 660.0, 380.0),
        pixel_covariance=np.diag([4.0, 4.0]),
        confidence=0.9,
        track_state="measured",
        metadata={"source": "d5_terminal_association"},
    )
    eo_observation = sensor_observation_from_local_image_track(local_track)
    assert eo_observation is not None

    state = np.array([100.0, 0.0, -10.0, 0.0, 0.0, 0.0])
    radar_measurement = radar_h(state, np.zeros(3))
    radar_observation = SensorObservation(
        observation_id="radar-seed",
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.0,
        frame_id="ned",
        measurement=radar_measurement,
        covariance=radar_covariance_from_range(radar_measurement[0]),
        metadata={"sensor_position_ned": np.zeros(3), "scan_id": 0},
    )
    fusion = FusionAdapter()
    fusion.process(radar_observation)
    fused_tracks = fusion.process(eo_observation)

    canonical = canonical_track_from_d1(fused_tracks[0])
    detection = Detection(
        **d2_detection_kwargs(canonical, detection_id="D-from-D1")
    )

    assert detection.metadata["source_track_ids"] == (
        local_track.source_track_key,
    )
    assert detection.metadata["frame_id"] == "ned"
    assert detection.position.shape == (2,)
    assert detection.covariance.shape == (2, 2)
    assert "center_px" not in detection.metadata
    assert "bbox_xyxy" not in detection.metadata
    assert "pixel_covariance" not in detection.metadata
    assert detection.metadata["global_track_id"] != local_track.source_track_key


def test_d3_required_plan_cannot_be_handed_to_d5_for_locking() -> None:
    config = PlannerConfig(enable_hysteresis=False, human_authorization_state="required")
    planner = AssignmentPlanner(
        cost_model=CostModel(
            weights=CostWeights(window=0.0, covariance=0.0, threat=0.0),
            config=config,
        ),
        config=config,
    )
    plan = planner.plan(
        [
            TargetTrack(
                "G-1",
                threat_score=0.5,
                covariance=0.1,
                window_cost=0.1,
                identity_commitment_state="committed",
            )
        ],
        [ResourceState("R-1")],
        timestamp=0.0,
    )

    assert plan.human_authorization_state == "required"
    with pytest.raises(ValueError, match="not authorized"):
        assignment_handoff_from_d3(plan, plan.assignments[0], track_version=3)


def test_authorized_handoff_locks_terminal_and_is_counted_by_d6() -> None:
    config = PlannerConfig(enable_hysteresis=False)
    planner = AssignmentPlanner(
        cost_model=CostModel(
            weights=CostWeights(window=0.0, covariance=0.0, threat=0.0),
            config=config,
        ),
        config=config,
    )
    candidate = planner.plan(
        [
            TargetTrack(
                "G-1",
                threat_score=0.5,
                covariance=0.1,
                window_cost=0.1,
                identity_commitment_state="committed",
            )
        ],
        [ResourceState("R-1")],
        timestamp=0.0,
    )
    authorized = replace(candidate, human_authorization_state="approved")
    handoff = assignment_handoff_from_d3(authorized, authorized.assignments[0], track_version=4)

    associator = TerminalAssociator()
    camera = CameraModel(
        K=np.array([[100.0, 0.0, 320.0], [0.0, 100.0, 240.0], [0.0, 0.0, 1.0]]),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )
    global_track = GlobalTrack(
        global_track_id="G-1",
        position=np.array([0.0, 0.0, 10.0]),
        covariance=np.diag([0.01, 0.01, 0.01]),
        track_version=4,
    )
    local_track = LocalVisualTrack(
        local_track_id="L-1",
        center_px=np.array([320.0, 240.0]),
        bbox=(315.0, 235.0, 325.0, 245.0),
        quality=0.95,
        mot_history_length=5,
    )

    decision = associator.decide(
        D5Assignment(**d5_assignment_kwargs(handoff)),
        [global_track],
        [local_track],
        [],
        camera,
    )

    collector = MetricsCollector()
    collector.add_terminal(
        TerminalRecord(
            timestamp=1.0,
            resource_id="R-1",
            assigned_global_track_id=decision.assigned_global_track_id,
            local_track_id=decision.local_track_id,
            decision_state=decision.decision_state,
            ambiguity_score=decision.ambiguity_score,
            assignment_version=decision.assignment_version,
            expected_global_track_id="G-1",
            association_correct=True,
        )
    )
    metrics = collector.compute_episode("integration", duration=2.0)

    assert decision.decision_state == "locked"
    assert metrics.terminal_association_accuracy == 1.0


def test_local_image_track_observation_carries_uncertainty_and_local_scope() -> None:
    observation = LocalImageTrackObservation(
        sensor_id="eo-camera-01",
        stream_id="visible-main",
        local_track_id="local-003",
        local_epoch=2,
        spectral_band="visible",
        measurement_timestamp=10.0,
        arrival_timestamp=10.08,
        center_px=np.array([120.0, 80.0]),
        bbox_xyxy=(112.0, 72.0, 128.0, 88.0),
        pixel_covariance=np.diag([9.0, 16.0]),
        confidence=0.85,
        track_state="measured",
        quality_flags=("small_bbox",),
    )

    payload = observation.to_dict()
    assert observation.source_track_key == (
        "eo-camera-01/visible-main/epoch-2/local-003"
    )
    assert "global_track_id" not in payload
    assert payload["pixel_covariance"] == [[9.0, 0.0], [0.0, 16.0]]


def test_local_image_track_observation_lost_state_is_fail_closed() -> None:
    lost = LocalImageTrackObservation(
        sensor_id="ir-camera-01",
        stream_id="infrared-main",
        local_track_id="local-004",
        local_epoch=0,
        spectral_band="infrared",
        measurement_timestamp=4.0,
        arrival_timestamp=4.1,
        center_px=None,
        bbox_xyxy=None,
        pixel_covariance=None,
        confidence=0.0,
        track_state="lost",
    )
    assert lost.center_px is None
    assert lost.pixel_covariance is None

    with pytest.raises(ValueError, match="cannot carry stale"):
        LocalImageTrackObservation(
            sensor_id="ir-camera-01",
            stream_id="infrared-main",
            local_track_id="local-004",
            local_epoch=0,
            spectral_band="infrared",
            measurement_timestamp=4.0,
            arrival_timestamp=4.1,
            center_px=np.array([1.0, 2.0]),
            bbox_xyxy=None,
            pixel_covariance=None,
            confidence=0.0,
            track_state="lost",
        )


def test_local_image_track_observation_rejects_global_or_truth_identity() -> None:
    with pytest.raises(ValueError, match="cannot contain global/truth identity"):
        LocalImageTrackObservation(
            sensor_id="eo-camera-01",
            stream_id="visible-main",
            local_track_id="local-001",
            local_epoch=0,
            spectral_band="visible",
            measurement_timestamp=1.0,
            arrival_timestamp=1.0,
            center_px=np.array([10.0, 12.0]),
            bbox_xyxy=None,
            pixel_covariance=np.eye(2),
            confidence=1.0,
            track_state="measured",
            metadata={"global_track_id": "GT-001"},
        )
