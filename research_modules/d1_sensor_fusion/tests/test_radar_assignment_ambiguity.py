from __future__ import annotations

import builtins
import math

import numpy as np
import pytest

from d1_sensor_fusion.ekf import predict_to
from d1_sensor_fusion.fusion import (
    CHI2_3_999,
    RADAR_ASSIGNMENT_AMBIGUITY_CANDIDATE_POLICY_VERSIONS,
    RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION,
    FusionAdapter,
)
from d1_sensor_fusion.observations import radar_covariance_from_range
from d1_sensor_fusion.types import SensorObservation


SENSOR_POSITION = np.zeros(3, dtype=float)


def _radar(
    token: str,
    position_ned: np.ndarray,
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_index: int,
) -> SensorObservation:
    position = np.asarray(position_ned, dtype=float)
    range_m = float(np.linalg.norm(position))
    horizontal_m = float(np.linalg.norm(position[:2]))
    measurement = np.array(
        [
            range_m,
            math.atan2(float(position[1]), float(position[0])),
            math.atan2(float(-position[2]), max(horizontal_m, 1.0e-9)),
            0.0,
        ],
        dtype=float,
    )
    covariance = radar_covariance_from_range(range_m)
    return SensorObservation(
        observation_id=token,
        sensor_id="anonymous-radar",
        modality="radar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=measurement,
        covariance=covariance,
        metadata={
            "sensor_position_ned": SENSOR_POSITION,
            "sequence_id": scan_index,
            "radial_velocity_observed": False,
            "filter_measurement_dimension": 3,
            "filter_innovation_gate_chi2": CHI2_3_999,
            "radial_velocity_placeholder_ignored": True,
            "unobserved_velocity_variance_m2ps2": 25.0,
            "spherical_covariance_to_ned": "analytic_jacobian",
        },
    )


def _scan(
    scan_index: int,
    positions: tuple[np.ndarray, ...],
    *,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> tuple[SensorObservation, ...]:
    return tuple(
        _radar(
            f"opaque-{scan_index}-{index}",
            position,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            scan_index=scan_index,
        )
        for index, position in enumerate(positions)
    )


class _PresetRadarCostAdapter(FusionAdapter):
    def __init__(
        self,
        *,
        preset_costs: dict[int, np.ndarray],
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._preset_costs = {
            int(scan): np.asarray(costs, dtype=float).copy()
            for scan, costs in preset_costs.items()
        }

    def _radar_scan_cost_matrix(
        self,
        track_items,
        observations,
    ) -> np.ndarray:
        scan_index = int(observations[0].metadata["sequence_id"])
        preset = self._preset_costs.get(scan_index)
        if preset is None:
            return super()._radar_scan_cost_matrix(track_items, observations)
        assert preset.shape == (len(track_items), len(observations))
        return preset.copy()


def _seed_tracks(
    adapter: FusionAdapter,
    positions: tuple[np.ndarray, ...],
) -> tuple[str, ...]:
    first = adapter.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )
    second = adapter.process_scan_batch(
        _scan(
            1,
            positions,
            measurement_timestamp=0.2,
            arrival_timestamp=0.4,
        )
    )
    assert first.summary.created_track_count == len(positions)
    assert second.summary.updated_track_count == len(positions)
    return tuple(track.global_track_id for track in second.tracks)


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_ambiguity_governance_requires_a_strict_bool(value: object) -> None:
    with pytest.raises(
        TypeError,
        match="radar_assignment_ambiguity_governance must be a bool",
    ):
        FusionAdapter(radar_assignment_ambiguity_governance=value)  # type: ignore[arg-type]


def test_default_hungarian_swap_and_explicit_v1_suppression() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    crossing_costs = np.array([[2.0, 1.0], [1.0, 2.0]], dtype=float)
    baseline = _PresetRadarCostAdapter(
        association_gate=40.0,
        preset_costs={2: crossing_costs},
    )
    governed = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
        preset_costs={2: crossing_costs},
    )
    baseline_ids = _seed_tracks(baseline, positions)
    governed_ids = _seed_tracks(governed, positions)
    ambiguous_scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    baseline_result = baseline.process_scan_batch(ambiguous_scan)
    governed_before = {
        track.global_track_id: track
        for track in governed.global_tracks()
    }
    governed_state_before = {
        track_id: governed.tracks[track_id].current_state.copy()
        for track_id in governed_ids
    }
    governed_result = governed.process_scan_batch(ambiguous_scan)

    assert baseline_ids == governed_ids
    assert [
        item.observation_id
        for item in baseline.tracks[baseline_ids[0]].observations
    ][-1] == ambiguous_scan[1].observation_id
    assert [
        item.observation_id
        for item in baseline.tracks[baseline_ids[1]].observations
    ][-1] == ambiguous_scan[0].observation_id
    assert baseline_result.summary.accepted_observation_count == 2
    assert baseline_result.summary.updated_observation_count == 2
    assert baseline_result.summary.unaccepted_observation_count == 0
    assert baseline_result.summary.created_track_count == 0
    baseline_audit = baseline.association_audit_summary()
    assert baseline_audit["radar_assignment_ambiguity_governance_enabled"] is False
    assert baseline_audit["radar_assignment_ambiguity_governance_status"] == "disabled"
    assert (
        baseline_audit["radar_assignment_ambiguity_selected_policy_version"]
        is None
    )
    assert baseline_audit[
        "radar_assignment_ambiguity_candidate_policy_versions"
    ] == RADAR_ASSIGNMENT_AMBIGUITY_CANDIDATE_POLICY_VERSIONS
    assert baseline_audit["radar_assignment_ambiguity_scan_count"] == 0
    assert (
        baseline_audit["radar_assignment_ambiguity_policy_version"]
        == RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION
    )

    assert governed_result.summary.accepted_observation_count == 0
    assert governed_result.summary.unaccepted_observation_count == 2
    assert governed_result.summary.updated_observation_count == 0
    assert governed_result.summary.created_track_count == 0
    assert tuple(track.global_track_id for track in governed_result.tracks) == (
        governed_ids
    )
    assert all(
        len(governed.tracks[track_id].observations) == 2
        for track_id in governed_ids
    )
    assert all(
        track.metadata["latest_measurement_timestamp"] == pytest.approx(0.2)
        and track.metadata["latest_arrival_timestamp"] == pytest.approx(0.4)
        and track.metadata[
            "latest_radar_assignment_ambiguity_measurement_timestamp"
        ]
        == pytest.approx(0.4)
        and track.metadata[
            "latest_radar_assignment_ambiguity_arrival_timestamp"
        ]
        == pytest.approx(0.65)
        and track.metadata[
            "latest_radar_assignment_ambiguity_component_size"
        ]
        == 2
        and track.metadata[
            "latest_radar_assignment_ambiguity_policy_version"
        ]
        == RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION
        for track in governed_result.tracks
    )
    for track in governed_result.tracks:
        before = governed_before[track.global_track_id]
        expected = predict_to(
            governed_state_before[track.global_track_id],
            0.65,
            governed.process_noise,
        )
        assert track.timestamp == pytest.approx(0.65)
        assert track.state.shape == (6,)
        assert track.covariance.shape == (6, 6)
        assert np.isfinite(track.state).all()
        assert np.isfinite(track.covariance).all()
        assert np.linalg.eigvalsh(track.covariance).min() >= -1.0e-8
        assert np.trace(track.covariance) >= np.trace(before.covariance)
        np.testing.assert_allclose(track.state, expected.state)
        np.testing.assert_allclose(track.covariance, expected.covariance)

    audit = governed.association_audit_summary()
    assert audit["radar_assignment_ambiguity_governance_enabled"] is True
    assert audit["radar_assignment_ambiguity_selected_policy_version"] == (
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION
    )
    assert (
        audit["radar_assignment_ambiguity_governance_status"]
        == "experimental_enabled"
    )
    assert audit["radar_assignment_ambiguity_scan_count"] == 1
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2
    assert audit["max_radar_assignment_ambiguity_component_size"] == 2
    assert audit["latest_radar_assignment_ambiguity_track_ids"] == governed_ids
    assert (
        audit["radar_assignment_ambiguity_policy_version"]
        == RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION
    )
    assert audit["latest_rejection_reason"] == (
        "radar_assignment_ambiguity_suppressed"
    )
    assert all(
        track.metadata["association_diagnostics"][
            "radar_assignment_ambiguity_suppressed"
        ]
        == 1
        for track in governed_result.tracks
    )
    health = {
        item.sensor_id: item
        for item in governed.sensor_health_summaries()
    }
    assert health["anonymous-radar"].reject_count == 0


def test_greedy_fallback_preserves_fail_closed_cycle_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
        preset_costs={2: np.array([[2.0, 1.0], [1.0, 2.0]])},
    )
    track_ids = _seed_tracks(adapter, positions)
    original_import = builtins.__import__

    def import_without_scipy_optimize(name, *args, **kwargs):
        if name == "scipy.optimize":
            raise ImportError("forced fallback")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_scipy_optimize)
    result = adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.accepted_observation_count == 0
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_scan_count"] == 1
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2


def test_explicit_v1_documents_gate_valid_free_row_path_blocker() -> None:
    positions = (
        np.array([1_000.0, -250.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 250.0, -100.0]),
    )
    invalid = 1_000.0
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
        preset_costs={
            2: np.array(
                [
                    [1.58, invalid],
                    [0.80, invalid],
                    [invalid, 0.50],
                ]
            )
        },
    )
    track_ids = _seed_tracks(adapter, positions)
    scan = _scan(
        2,
        positions[1:],
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
    )

    result = adapter.process_scan_batch(scan)

    assert result.summary.accepted_observation_count == 2
    assert result.summary.updated_observation_count == 2
    assert result.summary.unaccepted_observation_count == 0
    assert result.summary.created_track_count == 0
    assert len(adapter.tracks[track_ids[0]].observations) == 2
    assert adapter.tracks[track_ids[1]].observations[-1].observation_id == (
        scan[0].observation_id
    )
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_governance_enabled"] is True
    assert audit["radar_assignment_ambiguity_scan_count"] == 0
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 0


def test_rectangular_more_tracks_suppresses_only_matched_cycle_rows() -> None:
    positions = (
        np.array([1_000.0, -250.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 250.0, -100.0]),
    )
    invalid = 1_000.0
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
        preset_costs={
            2: np.array(
                [
                    [2.0, 1.0],
                    [1.0, 2.0],
                    [invalid, invalid],
                ]
            )
        },
    )
    track_ids = _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            positions[:2],
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.accepted_observation_count == 0
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert all(len(adapter.tracks[item].observations) == 2 for item in track_ids)
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2


def test_rectangular_more_observations_does_not_birth_suppressed_columns() -> None:
    seeded_positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    new_position = np.array([1_800.0, 900.0, -120.0])
    invalid = 1_000.0
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
        preset_costs={
            2: np.array(
                [
                    [2.0, 1.0, invalid],
                    [1.0, 2.0, invalid],
                ]
            )
        },
    )
    track_ids = _seed_tracks(adapter, seeded_positions)
    scan = _scan(
        2,
        (*seeded_positions, new_position),
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
    )

    result = adapter.process_scan_batch(scan)

    assert result.summary.accepted_observation_count == 1
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 1
    assert len(result.tracks) == 3
    assert all(len(adapter.tracks[item].observations) == 2 for item in track_ids)
    created_id = next(
        track.global_track_id
        for track in result.tracks
        if track.global_track_id not in track_ids
    )
    assert [
        item.observation_id
        for item in adapter.tracks[created_id].observations
    ] == [scan[2].observation_id]
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2


def test_three_track_alternating_cycle_fails_closed_as_one_component() -> None:
    positions = (
        np.array([1_000.0, -300.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 300.0, -100.0]),
    )
    invalid = 1_000.0
    cycle_costs = np.array(
        [
            [2.0, 1.0, invalid],
            [invalid, 2.0, 1.0],
            [1.0, invalid, 2.0],
        ],
        dtype=float,
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
        preset_costs={2: cycle_costs},
    )
    track_ids = _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.accepted_observation_count == 0
    assert result.summary.unaccepted_observation_count == 3
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert all(len(adapter.tracks[item].observations) == 2 for item in track_ids)
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_scan_count"] == 1
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 3
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 3
    assert audit["max_radar_assignment_ambiguity_component_size"] == 3


def test_gate_unique_formation_updates_without_ambiguity_suppression() -> None:
    positions = (
        np.array([1_000.0, -500.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 500.0, -100.0]),
    )
    adapter = FusionAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
    )
    track_ids = _seed_tracks(adapter, positions)
    moved = tuple(
        position + np.array([2.0, 0.5, 0.0])
        for position in positions
    )

    result = adapter.process_scan_batch(
        _scan(
            2,
            moved,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.accepted_observation_count == 3
    assert result.summary.updated_observation_count == 3
    assert result.summary.unaccepted_observation_count == 0
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert all(adapter.tracks[item].hits == 3 for item in track_ids)
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_scan_count"] == 0
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 0


def test_dense_first_scan_births_all_tracks_without_ambiguity_suppression() -> None:
    positions = tuple(
        np.array([1_500.0, -1_200.0 + 100.0 * index, -120.0])
        for index in range(25)
    )
    adapter = FusionAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
    )

    result = adapter.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )

    assert len(result.tracks) == len(positions)
    assert result.summary.accepted_observation_count == len(positions)
    assert result.summary.created_track_count == len(positions)
    assert result.summary.unaccepted_observation_count == 0
    assert adapter.association_audit_summary()[
        "radar_assignment_ambiguity_scan_count"
    ] == 0


def test_gate_unique_oosm_scan_preserves_dual_timestamps_and_track_ids() -> None:
    positions = (
        np.array([1_200.0, -400.0, -120.0]),
        np.array([1_200.0, 400.0, -120.0]),
    )
    velocities = (
        np.array([4.0, 1.0, 0.0]),
        np.array([-3.0, 1.0, 0.0]),
    )
    adapter = FusionAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance=True,
    )
    first_ids = _seed_tracks(adapter, positions)
    later_positions = tuple(
        position + velocity
        for position, velocity in zip(positions, velocities)
    )
    adapter.process_scan_batch(
        _scan(
            10,
            later_positions,
            measurement_timestamp=1.0,
            arrival_timestamp=1.2,
        )
    )
    delayed_positions = tuple(
        position + 0.5 * velocity
        for position, velocity in zip(positions, velocities)
    )

    delayed = adapter.process_scan_batch(
        _scan(
            5,
            delayed_positions,
            measurement_timestamp=0.5,
            arrival_timestamp=1.4,
        )
    )

    assert {track.global_track_id for track in delayed.tracks} == set(first_ids)
    assert delayed.summary.accepted_observation_count == 2
    assert delayed.summary.updated_observation_count == 2
    assert delayed.summary.created_track_count == 0
    assert adapter.oosm_observation_count == 2
    assert adapter.association_audit_summary()[
        "radar_assignment_ambiguity_scan_count"
    ] == 0
    assert all(
        track.metadata["latest_measurement_timestamp"] == pytest.approx(0.5)
        and track.metadata["latest_arrival_timestamp"] == pytest.approx(1.4)
        and track.timestamp == pytest.approx(1.4)
        for track in delayed.tracks
    )
