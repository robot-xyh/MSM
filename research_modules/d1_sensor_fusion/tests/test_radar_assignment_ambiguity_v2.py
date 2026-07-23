from __future__ import annotations

import builtins
import math

import numpy as np
import pytest

from d1_sensor_fusion.fusion import (
    CHI2_3_999,
    RADAR_ASSIGNMENT_AMBIGUITY_CANDIDATE_POLICY_VERSIONS,
    RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION,
    RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION,
    FusionAdapter,
)
from d1_sensor_fusion.observations import radar_covariance_from_range
from d1_sensor_fusion.scalable_3d import Scalable3DFusionAdapter
from d1_sensor_fusion.types import GlobalTrack, SensorObservation


SENSOR_POSITION = np.zeros(3, dtype=float)
INVALID_COST = 1_000.0


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
    return SensorObservation(
        observation_id=token,
        sensor_id="anonymous-radar",
        modality="radar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=np.array(
            [
                range_m,
                math.atan2(float(position[1]), float(position[0])),
                math.atan2(float(-position[2]), max(horizontal_m, 1.0e-9)),
                0.0,
            ],
            dtype=float,
        ),
        covariance=radar_covariance_from_range(range_m),
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


def _assert_track_contract(track: GlobalTrack) -> None:
    assert track.state.shape == (6,)
    assert track.covariance.shape == (6, 6)
    assert np.isfinite(track.state).all()
    assert np.isfinite(track.covariance).all()
    np.testing.assert_allclose(track.covariance, track.covariance.T)
    assert np.linalg.eigvalsh(track.covariance).min() >= -1.0e-8
    assert track.metadata["latest_measurement_timestamp"] <= (
        track.metadata["latest_arrival_timestamp"]
    )


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_v2_governance_requires_a_strict_bool(value: object) -> None:
    with pytest.raises(
        TypeError,
        match="radar_assignment_ambiguity_governance_v2 must be a bool",
    ):
        FusionAdapter(  # type: ignore[arg-type]
            radar_assignment_ambiguity_governance_v2=value
        )


def test_v1_and_v2_cannot_be_enabled_together() -> None:
    with pytest.raises(
        ValueError,
        match="v1 and v2 cannot both be enabled",
    ):
        FusionAdapter(
            radar_assignment_ambiguity_governance=True,
            radar_assignment_ambiguity_governance_v2=True,
        )


def test_scalable_adapter_exposes_the_explicit_v2_policy() -> None:
    adapter = Scalable3DFusionAdapter(
        radar_assignment_ambiguity_governance_v2=True
    )

    audit = adapter.association_audit_summary()

    assert audit["radar_assignment_ambiguity_governance_enabled"] is True
    assert audit["radar_assignment_ambiguity_policy_version"] == (
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
    )
    assert audit["radar_assignment_ambiguity_selected_policy_version"] == (
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
    )
    assert audit[
        "radar_assignment_ambiguity_candidate_policy_versions"
    ] == (
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_VERSION,
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION,
    )
    assert audit[
        "radar_assignment_ambiguity_candidate_policy_versions"
    ] == RADAR_ASSIGNMENT_AMBIGUITY_CANDIDATE_POLICY_VERSIONS
    assert audit["radar_assignment_ambiguity_governance_status"] == (
        "experimental_v2_enabled_rejected_candidate"
    )


def test_v2_default_false_is_identical_to_the_existing_baseline() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = {2: np.array([[2.0, 1.0], [1.0, 2.0]])}
    baseline = _PresetRadarCostAdapter(
        association_gate=40.0,
        preset_costs=costs,
    )
    explicit_false = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=False,
        preset_costs=costs,
    )
    baseline_ids = _seed_tracks(baseline, positions)
    explicit_ids = _seed_tracks(explicit_false, positions)
    scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
    )

    baseline_result = baseline.process_scan_batch(scan)
    explicit_result = explicit_false.process_scan_batch(scan)

    assert baseline_ids == explicit_ids
    assert baseline_result.summary.to_dict() == explicit_result.summary.to_dict()
    assert baseline.association_audit_summary() == (
        explicit_false.association_audit_summary()
    )
    for baseline_track, explicit_track in zip(
        baseline_result.tracks,
        explicit_result.tracks,
    ):
        assert baseline_track.global_track_id == explicit_track.global_track_id
        np.testing.assert_allclose(baseline_track.state, explicit_track.state)
        np.testing.assert_allclose(
            baseline_track.covariance,
            explicit_track.covariance,
        )
        assert [
            item.observation_id
            for item in baseline.tracks[baseline_track.global_track_id].observations
        ] == [
            item.observation_id
            for item in explicit_false.tracks[
                explicit_track.global_track_id
            ].observations
        ]


def test_v2_two_by_two_alternating_cycle_suppresses_the_component() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={2: np.array([[1.0, 2.0], [2.0, 1.0]])},
    )
    track_ids = _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.65,
        )
    )

    assert result.summary.accepted_observation_count == 0
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert all(len(adapter.tracks[track_id].observations) == 2 for track_id in track_ids)
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_governance_enabled"] is True
    assert audit["radar_assignment_ambiguity_policy_version"] == (
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
    )
    assert audit["radar_assignment_ambiguity_selected_policy_version"] == (
        RADAR_ASSIGNMENT_AMBIGUITY_POLICY_V2_VERSION
    )
    assert audit["radar_assignment_ambiguity_governance_status"] == (
        "experimental_v2_enabled_rejected_candidate"
    )
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2
    for track in result.tracks:
        _assert_track_contract(track)
        assert track.metadata[
            "latest_radar_assignment_ambiguity_component_kinds"
        ] == ("alternating_cycle",)
        assert track.metadata[
            "latest_radar_assignment_ambiguity_observation_count"
        ] == 2
        assert track.metadata[
            "latest_radar_assignment_ambiguity_measurement_timestamp"
        ] == pytest.approx(0.4)
        assert track.metadata[
            "latest_radar_assignment_ambiguity_arrival_timestamp"
        ] == pytest.approx(0.65)


def test_v2_three_by_two_free_row_path_coasts_all_related_tracks() -> None:
    positions = (
        np.array([1_000.0, -250.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 250.0, -100.0]),
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={
            2: np.array(
                [
                    [1.58, INVALID_COST],
                    [0.80, INVALID_COST],
                    [INVALID_COST, 0.50],
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

    assert result.summary.accepted_observation_count == 1
    assert result.summary.updated_observation_count == 1
    assert result.summary.unaccepted_observation_count == 1
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert len(adapter.tracks[track_ids[0]].observations) == 2
    assert len(adapter.tracks[track_ids[1]].observations) == 2
    assert adapter.tracks[track_ids[2]].observations[-1].observation_id == (
        scan[1].observation_id
    )
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 1
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2
    for track_id in track_ids[:2]:
        assert adapter.tracks[track_id].metadata[
            "latest_radar_assignment_ambiguity_component_kinds"
        ] == ("free_row_alternating_path",)


def test_v2_two_by_three_free_column_path_suppresses_related_birth() -> None:
    seeded_positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    free_column_position = np.array([1_300.0, -80.0, -100.0])
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={
            2: np.array(
                [
                    [1.0, INVALID_COST, 2.0],
                    [INVALID_COST, 1.0, INVALID_COST],
                ]
            )
        },
    )
    track_ids = _seed_tracks(adapter, seeded_positions)
    scan = _scan(
        2,
        (*seeded_positions, free_column_position),
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
    )

    result = adapter.process_scan_batch(scan)

    assert result.summary.accepted_observation_count == 1
    assert result.summary.updated_observation_count == 1
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert len(adapter.tracks[track_ids[0]].observations) == 2
    assert adapter.tracks[track_ids[1]].observations[-1].observation_id == (
        scan[1].observation_id
    )
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 1
    assert adapter.tracks[track_ids[0]].metadata[
        "latest_radar_assignment_ambiguity_component_kinds"
    ] == ("free_column_alternating_path",)
    assert adapter.tracks[track_ids[0]].metadata[
        "latest_radar_assignment_ambiguity_observation_count"
    ] == 2


def test_v2_unique_maximum_matching_is_not_suppressed() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={
            2: np.array(
                [
                    [1.0, 2.0],
                    [INVALID_COST, 1.0],
                ]
            )
        },
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

    assert result.summary.accepted_observation_count == 2
    assert result.summary.updated_observation_count == 2
    assert result.summary.unaccepted_observation_count == 0
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    assert adapter.association_audit_summary()[
        "radar_assignment_ambiguity_scan_count"
    ] == 0


def test_v2_gate_outside_free_column_remains_an_independent_birth() -> None:
    seeded_positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    new_position = np.array([1_800.0, 900.0, -120.0])
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={
            2: np.array(
                [
                    [1.0, INVALID_COST, INVALID_COST],
                    [INVALID_COST, 1.0, INVALID_COST],
                ]
            )
        },
    )
    track_ids = _seed_tracks(adapter, seeded_positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            (*seeded_positions, new_position),
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.accepted_observation_count == 3
    assert result.summary.updated_observation_count == 2
    assert result.summary.unaccepted_observation_count == 0
    assert result.summary.created_track_count == 1
    assert set(track_ids).issubset(
        {track.global_track_id for track in result.tracks}
    )
    assert adapter.association_audit_summary()[
        "radar_assignment_ambiguity_scan_count"
    ] == 0
    assert all(_assert_track_contract(track) is None for track in result.tracks)


def test_v2_first_scan_without_tracks_births_every_observation() -> None:
    positions = tuple(
        np.array([1_200.0, -200.0 + 100.0 * index, -100.0])
        for index in range(5)
    )
    adapter = FusionAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
    )

    result = adapter.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )

    assert result.summary.accepted_observation_count == 5
    assert result.summary.created_track_count == 5
    assert result.summary.unaccepted_observation_count == 0
    assert len({track.global_track_id for track in result.tracks}) == 5
    assert adapter.association_audit_summary()[
        "radar_assignment_ambiguity_scan_count"
    ] == 0
    assert all(_assert_track_contract(track) is None for track in result.tracks)


def test_v2_repairs_nonmaximum_greedy_fallback_before_decomposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={
            2: np.array(
                [
                    [1.0, 2.0],
                    [1.5, INVALID_COST],
                ]
            )
        },
    )
    track_ids = _seed_tracks(adapter, positions)
    original_import = builtins.__import__

    def import_without_scipy_optimize(name, *args, **kwargs):
        if name == "scipy.optimize":
            raise ImportError("forced fallback")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_scipy_optimize)
    scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
    )

    result = adapter.process_scan_batch(scan)

    assert result.summary.accepted_observation_count == 2
    assert result.summary.updated_observation_count == 2
    assert result.summary.unaccepted_observation_count == 0
    assert result.summary.created_track_count == 0
    assert adapter.tracks[track_ids[0]].observations[-1].observation_id == (
        scan[1].observation_id
    )
    assert adapter.tracks[track_ids[1]].observations[-1].observation_id == (
        scan[0].observation_id
    )
    assert adapter.association_audit_summary()[
        "radar_assignment_ambiguity_scan_count"
    ] == 0


def test_v2_oosm_ambiguity_preserves_dual_timestamps_and_track_ownership() -> None:
    positions = (
        np.array([1_200.0, -300.0, -120.0]),
        np.array([1_200.0, 300.0, -120.0]),
    )
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={
            5: np.array([[1.0, 2.0], [2.0, 1.0]]),
            10: np.array([[1.0, INVALID_COST], [INVALID_COST, 1.0]]),
        },
    )
    track_ids = _seed_tracks(adapter, positions)
    adapter.process_scan_batch(
        _scan(
            10,
            positions,
            measurement_timestamp=1.0,
            arrival_timestamp=1.2,
        )
    )

    result = adapter.process_scan_batch(
        _scan(
            5,
            positions,
            measurement_timestamp=0.5,
            arrival_timestamp=1.4,
        )
    )

    assert result.summary.accepted_observation_count == 0
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 0
    assert adapter.oosm_observation_count == 2
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    for track in result.tracks:
        _assert_track_contract(track)
        assert track.timestamp == pytest.approx(1.4)
        assert track.metadata["latest_measurement_timestamp"] == pytest.approx(1.0)
        assert track.metadata["latest_arrival_timestamp"] == pytest.approx(1.2)
        assert track.metadata[
            "latest_radar_assignment_ambiguity_measurement_timestamp"
        ] == pytest.approx(0.5)
        assert track.metadata[
            "latest_radar_assignment_ambiguity_arrival_timestamp"
        ] == pytest.approx(1.4)


def test_v2_sparse_two_hundred_track_scan_has_bounded_component_scope() -> None:
    count = 200
    positions = tuple(
        np.array(
            [
                1_500.0 + 5.0 * (index // 20),
                -950.0 + 100.0 * (index % 20),
                -120.0,
            ]
        )
        for index in range(count)
    )
    unique = np.full((count, count), INVALID_COST, dtype=float)
    np.fill_diagonal(unique, 1.0)
    sparse_cycle = unique.copy()
    sparse_cycle[0, 1] = 2.0
    sparse_cycle[1, 0] = 2.0
    adapter = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_governance_v2=True,
        preset_costs={1: unique, 2: sparse_cycle},
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

    assert len(result.tracks) == count
    assert result.summary.accepted_observation_count == count - 2
    assert result.summary.updated_observation_count == count - 2
    assert result.summary.unaccepted_observation_count == 2
    assert result.summary.created_track_count == 0
    assert {track.global_track_id for track in result.tracks} == set(track_ids)
    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_scan_count"] == 1
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 2
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 2
    assert audit["max_radar_assignment_ambiguity_component_size"] == 2
    assert all(_assert_track_contract(track) is None for track in result.tracks)
