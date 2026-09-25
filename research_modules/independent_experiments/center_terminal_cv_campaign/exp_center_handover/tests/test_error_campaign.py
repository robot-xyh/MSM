from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.association import (
    AssociationConfig,
    CenterHandoverAssociator,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.error_campaign import (
    NORMAL_ABSOLUTE_P95_Z,
    RADIAL_3D_P95_Z,
    SearchTerminalErrorConfig,
    build_search_terminal_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.geometry import (
    ProjectionUncertainty,
    joint_projection_covariance,
    linearized_joint_projection_covariance,
)


def test_search_terminal_fixture_has_one_correct_source_and_resource_per_target() -> None:
    config = SearchTerminalErrorConfig(
        target_count=20,
        seed=20260820,
        navigation_mode="satellite",
        attitude_mode="normal",
        detection_mode="ideal",
        handover_mode="coarse_hint",
    )
    bundle = build_search_terminal_fixture(config)
    fixture = bundle.handover_fixture

    assert len(fixture.source_cues) == 20
    assert len(fixture.camera_models) == 20
    assert len(fixture.local_truth) == 20
    assert all(label.is_correct_source for label in fixture.source_truth)
    assert all(len(frame) == 20 for frame in fixture.frames)
    assert all(
        track.metadata["search_status"] == "target_already_found"
        and track.metadata.get("coarse_source_track_id")
        for frame in fixture.frames
        for track in frame
    )
    assert not any(
        "truth_target_id" in track.metadata
        for frame in fixture.frames
        for track in frame
    )


def test_error_covariance_encodes_requested_p95_envelopes() -> None:
    config = SearchTerminalErrorConfig(
        target_count=20,
        seed=20260820,
        navigation_mode="visual_navigation",
        attitude_mode="degraded",
        detection_mode="ideal",
        handover_mode="anonymous",
    )
    bundle = build_search_terminal_fixture(config)
    local = bundle.handover_fixture.frames[0][0]
    uncertainty = local.metadata["projection_uncertainty"]
    navigation = np.asarray(uncertainty["navigation_position_covariance_m2"])
    body = np.asarray(uncertainty["body_attitude_covariance_rad2"])
    gimbal = np.asarray(uncertainty["gimbal_angle_covariance_rad2"])

    assert math.sqrt(navigation[0, 0]) * RADIAL_3D_P95_Z == pytest.approx(50.0)
    assert math.degrees(math.sqrt(body[1, 1])) * NORMAL_ABSOLUTE_P95_Z == pytest.approx(5.0)
    expected_yaw_sigma = math.hypot(10.0, 1.0) / NORMAL_ABSOLUTE_P95_Z
    assert math.degrees(math.sqrt(body[0, 0])) == pytest.approx(expected_yaw_sigma)
    assert math.degrees(math.sqrt(gimbal[0, 0])) * NORMAL_ABSOLUTE_P95_Z == pytest.approx(0.5)


def test_invalid_coarse_hint_falls_back_to_global_assignment() -> None:
    config = SearchTerminalErrorConfig(
        target_count=20,
        seed=20260821,
        navigation_mode="satellite",
        attitude_mode="normal",
        detection_mode="ideal",
        handover_mode="coarse_hint",
    )
    fixture = build_search_terminal_fixture(config).handover_fixture
    changed = replace(
        fixture.frames[0][0],
        metadata={**fixture.frames[0][0].metadata, "coarse_source_track_id": "UNKNOWN"},
    )
    first_frame = (changed,) + fixture.frames[0][1:]
    associator = CenterHandoverAssociator(
        fixture.camera_models,
        config=AssociationConfig(
            projection_noise_px=0.25,
            local_measurement_sigma_px=0.25,
            projection_uncertainty_method="linearized",
        ),
        use_coarse_hints=True,
    )
    result = associator.process_frame(fixture.source_cues, first_frame)

    assert result.coarse_hint_count == 20
    assert result.validated_coarse_hint_count <= 19
    assert result.fallback_coarse_hint_count >= 1
    changed_candidates = [
        candidate
        for candidate in result.candidates
        if candidate.local_track_id == changed.local_track_id
    ]
    assert any(candidate.eligible for candidate in changed_candidates)
    assert not any(candidate.coarse_hint_validated for candidate in changed_candidates)


def test_linearized_projection_covariance_tracks_numerical_result() -> None:
    config = SearchTerminalErrorConfig(
        target_count=20,
        seed=20260822,
        navigation_mode="satellite",
        attitude_mode="normal",
        detection_mode="ideal",
        handover_mode="anonymous",
    )
    fixture = build_search_terminal_fixture(config).handover_fixture
    local = fixture.frames[0][0]
    source = fixture.source_cues[0]
    camera = fixture.camera_models[local.camera_id]
    raw = local.metadata["projection_uncertainty"]
    uncertainty = ProjectionUncertainty(**raw)
    source_covariance = np.asarray(source.covariance_6x6)[:3, :3]
    numerical = joint_projection_covariance(
        camera,
        source.position_ned_m,
        source_covariance,
        uncertainty,
    )
    linearized = linearized_joint_projection_covariance(
        camera,
        source.position_ned_m,
        source_covariance,
        uncertainty,
    )

    assert np.all(np.linalg.eigvalsh(linearized) > 0.0)
    assert np.trace(linearized) == pytest.approx(np.trace(numerical), rel=0.25)
