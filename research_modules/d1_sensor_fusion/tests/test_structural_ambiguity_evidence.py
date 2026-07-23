from __future__ import annotations

from copy import deepcopy
import json
import math

import numpy as np
import pytest

from d1_sensor_fusion import (
    DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_EPOCH,
    FusionStateUpdateResult,
    Scalable3DFusionAdapter,
    StructuralAmbiguityEvidence,
    STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION,
    STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION,
)
from d1_sensor_fusion.fusion import CHI2_3_999, FusionAdapter
from d1_sensor_fusion.observations import radar_covariance_from_range
from d1_sensor_fusion.types import SensorObservation


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
    labels: tuple[str, ...] | None = None,
) -> tuple[SensorObservation, ...]:
    if labels is None:
        labels = tuple(f"opaque-{scan_index}-{index}" for index in range(len(positions)))
    return tuple(
        _radar(
            label,
            position,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            scan_index=scan_index,
        )
        for label, position in zip(labels, positions, strict=True)
    )


class _PresetRadarCostAdapter(FusionAdapter):
    def __init__(
        self,
        *,
        preset_costs: dict[int, np.ndarray],
        reverse_track_input: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._preset_costs = {
            int(scan): np.asarray(costs, dtype=float).copy()
            for scan, costs in preset_costs.items()
        }
        self._reverse_track_input = bool(reverse_track_input)

    def _radar_scan_cost_matrix(self, track_items, observations) -> np.ndarray:
        scan_index = int(observations[0].metadata["sequence_id"])
        preset = self._preset_costs.get(scan_index)
        if preset is None:
            return super()._radar_scan_cost_matrix(track_items, observations)
        assert preset.shape == (len(track_items), len(observations))
        return preset.copy()

    def _scan_one_to_one_assignments(self, observations, pre_scan_track_ids):
        if self._reverse_track_input:
            pre_scan_track_ids = tuple(reversed(pre_scan_track_ids))
        return super()._scan_one_to_one_assignments(
            observations,
            pre_scan_track_ids,
        )


def _seed_tracks(
    adapter: FusionAdapter,
    positions: tuple[np.ndarray, ...],
    *,
    moving: bool = False,
) -> tuple[str, ...]:
    first = adapter.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )
    second_positions = (
        tuple(position + np.array([10.0, 0.0, 0.0]) for position in positions)
        if moving
        else positions
    )
    second = adapter.process_scan_batch(
        _scan(
            1,
            second_positions,
            measurement_timestamp=0.2,
            arrival_timestamp=0.4,
        )
    )
    assert first.summary.created_track_count == len(positions)
    assert second.summary.updated_track_count == len(positions)
    return tuple(track.global_track_id for track in second.tracks)


def _hold_adapter(
    costs: np.ndarray,
    *,
    reverse_track_input: bool = False,
) -> _PresetRadarCostAdapter:
    return _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-opaque-001",
        preset_costs={2: costs},
        reverse_track_input=reverse_track_input,
    )


def test_two_by_two_publishes_prediction_only_evidence_without_false_birth_count() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _hold_adapter(np.array([[1.0, 2.0], [2.0, 1.0]]))
    track_ids = _seed_tracks(adapter, positions, moving=True)
    before = {
        track_id: (
            adapter.tracks[track_id].hits,
            len(adapter.tracks[track_id].observations),
            adapter.tracks[track_id].current_state.state[3:].copy(),
        )
        for track_id in track_ids
    }

    result = adapter.process_scan_batch(
        _scan(
            2,
            tuple(position + np.array([20.0, 0.0, 0.0]) for position in positions),
            measurement_timestamp=0.4,
            arrival_timestamp=0.65,
        )
    )

    assert result.summary.accepted_observation_count == 0
    assert result.summary.created_track_count == 0
    assert len(result.structural_ambiguity_evidence) == 1
    evidence = result.structural_ambiguity_evidence[0]
    assert evidence.schema_version == STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION
    assert evidence.policy_version == STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION
    assert evidence.member_count == 2
    assert evidence.observation_count == 2
    assert evidence.candidate_edge_count == 4
    assert evidence.free_row_count == 0
    assert evidence.free_column_count == 0
    assert evidence.maximum_matching_cardinality == 2
    assert evidence.component_kinds == ("alternating_cycle",)
    assert evidence.posterior_update_applied is False
    assert evidence.update_mode == "prediction_only"
    assert evidence.cross_covariance_available is False
    assert all(not item.birth_deferred for item in evidence.observations)
    assert all(not item.velocity_evidence_used for item in evidence.observations)
    assert all(not item.radial_velocity_observed for item in evidence.observations)

    matched = [edge for edge in evidence.candidate_edges if edge.nis == 1.0]
    alternatives = [edge for edge in evidence.candidate_edges if edge.nis == 2.0]
    assert len(matched) == 2
    assert len(alternatives) == 2
    assert all(
        edge.edge_roles == ("matched_reference", "maximum_matching_allowed")
        for edge in matched
    )
    assert all(
        edge.edge_roles == ("alternating_cycle", "maximum_matching_allowed")
        for edge in alternatives
    )

    audit = adapter.association_audit_summary()
    assert audit["radar_assignment_ambiguity_observation_suppression_count"] == 0
    assert audit["radar_assignment_ambiguity_track_coast_count"] == 0
    assert audit["structural_ambiguity_evidence_component_count"] == 1
    assert audit["structural_ambiguity_evidence_observation_count"] == 2
    assert audit["structural_ambiguity_evidence_member_count"] == 2
    assert audit["structural_ambiguity_deferred_birth_count"] == 0
    assert audit["structural_ambiguity_prediction_only_member_count"] == 2

    member_tokens = {
        member.opaque_member_track_token: member.source_key
        for member in evidence.member_states
    }
    snapshot_tokens: dict[str, str] = {}
    for track in result.tracks:
        previous_hits, previous_count, previous_velocity = before[
            track.global_track_id
        ]
        record = adapter.tracks[track.global_track_id]
        assert record.hits == previous_hits
        assert len(record.observations) == previous_count
        np.testing.assert_allclose(track.state[3:], previous_velocity)
        token = track.metadata["opaque_member_track_token"]
        source_key = (
            f"{track.metadata['source_node_id']}::"
            f"{track.metadata['source_track_id']}"
        )
        assert track.metadata["publisher_epoch"] == evidence.publisher_epoch
        assert track.metadata["source_key"] == source_key
        snapshot_tokens[token] = source_key
    assert snapshot_tokens == member_tokens

    serialized = json.dumps(evidence.to_dict(), sort_keys=True).lower()
    assert all(word not in serialized for word in ("truth", "actor", "target_id"))
    assert all(track_id not in serialized for track_id in track_ids)
    assert all(
        observation.observation_id not in serialized
        for observation in _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.65,
        )
    )


def test_three_by_two_preserves_free_row_edge_roles_without_deferred_birth() -> None:
    positions = (
        np.array([1_000.0, -250.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 250.0, -100.0]),
    )
    adapter = _hold_adapter(
        np.array(
            [
                [1.58, INVALID_COST],
                [0.80, INVALID_COST],
                [INVALID_COST, 0.50],
            ]
        )
    )
    _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            positions[1:],
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    evidence = result.structural_ambiguity_evidence[0]
    assert result.summary.updated_observation_count == 1
    assert evidence.member_count == 2
    assert evidence.observation_count == 1
    assert evidence.free_row_count == 1
    assert evidence.free_column_count == 0
    assert evidence.maximum_matching_cardinality == 1
    assert all(not item.birth_deferred for item in evidence.observations)
    matched = [
        edge for edge in evidence.candidate_edges
        if "matched_reference" in edge.edge_roles
    ]
    alternate = [
        edge for edge in evidence.candidate_edges
        if "free_row_alternating_path" in edge.edge_roles
    ]
    assert len(matched) == 1
    assert len(alternate) == 1
    assert matched[0].edge_roles == (
        "matched_reference",
        "maximum_matching_allowed",
    )
    assert alternate[0].edge_roles == (
        "free_row_alternating_path",
        "maximum_matching_allowed",
    )
    assert adapter.association_audit_summary()[
        "structural_ambiguity_deferred_birth_count"
    ] == 0


def test_two_by_three_counts_only_the_free_column_as_deferred_birth() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    free_position = np.array([1_300.0, -80.0, -100.0])
    adapter = _hold_adapter(
        np.array(
            [
                [1.0, INVALID_COST, 2.0],
                [INVALID_COST, 1.0, INVALID_COST],
            ]
        )
    )
    track_ids = _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            (*positions, free_position),
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    evidence = result.structural_ambiguity_evidence[0]
    assert evidence.member_count == 1
    assert evidence.observation_count == 2
    assert evidence.free_row_count == 0
    assert evidence.free_column_count == 1
    assert evidence.maximum_matching_cardinality == 1
    assert sum(item.birth_deferred for item in evidence.observations) == 1
    matched = [
        edge for edge in evidence.candidate_edges
        if "matched_reference" in edge.edge_roles
    ]
    alternate = [
        edge for edge in evidence.candidate_edges
        if "free_column_alternating_path" in edge.edge_roles
    ]
    assert len(matched) == 1
    assert len(alternate) == 1
    assert matched[0].edge_roles == (
        "matched_reference",
        "maximum_matching_allowed",
    )
    assert alternate[0].edge_roles == (
        "free_column_alternating_path",
        "maximum_matching_allowed",
    )
    assert adapter.association_audit_summary()[
        "structural_ambiguity_deferred_birth_count"
    ] == 1
    assert {track.global_track_id for track in result.tracks} == set(track_ids)


def test_gate_outside_observation_births_while_cycle_evidence_is_retained() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    independent_position = np.array([1_900.0, 900.0, -140.0])
    adapter = _hold_adapter(
        np.array(
            [
                [1.0, 2.0, INVALID_COST],
                [2.0, 1.0, INVALID_COST],
            ]
        )
    )
    track_ids = _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            (*positions, independent_position),
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.created_track_count == 1
    assert len(result.tracks) == len(track_ids) + 1
    assert len(result.structural_ambiguity_evidence) == 1
    assert result.structural_ambiguity_evidence[0].observation_count == 2
    assert adapter.association_audit_summary()[
        "structural_ambiguity_deferred_birth_count"
    ] == 0


def test_unique_matching_and_first_scan_keep_the_existing_paths() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    first_scan_adapter = FusionAdapter(
        radar_assignment_ambiguity_hold_evidence=True
    )
    first = first_scan_adapter.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )
    assert first.summary.created_track_count == 2
    assert first.structural_ambiguity_evidence == ()

    adapter = _hold_adapter(
        np.array(
            [
                [1.0, 2.0],
                [INVALID_COST, 1.0],
            ]
        )
    )
    _seed_tracks(adapter, positions)
    unique = adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )
    assert unique.summary.updated_observation_count == 2
    assert unique.structural_ambiguity_evidence == ()
    assert "structural_ambiguity_evidence" not in unique.to_dict()


def test_evidence_and_edges_are_invariant_to_track_and_observation_order() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    normal = _hold_adapter(np.array([[1.0, 2.0], [2.0, 1.0]]))
    permuted = _hold_adapter(
        np.array([[2.0, 1.0], [1.0, 2.0]]),
        reverse_track_input=True,
    )
    _seed_tracks(normal, positions)
    _seed_tracks(permuted, positions)
    labels = ("opaque-left", "opaque-right")
    normal_scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
        labels=labels,
    )
    permuted_scan = tuple(reversed(normal_scan))

    normal_evidence = normal.process_scan_batch(
        normal_scan
    ).structural_ambiguity_evidence[0]
    permuted_evidence = permuted.process_scan_batch(
        permuted_scan
    ).structural_ambiguity_evidence[0]

    assert normal_evidence.to_dict() == permuted_evidence.to_dict()


def test_observation_names_and_offline_identity_metadata_do_not_change_evidence() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    anonymous = _hold_adapter(np.array([[1.0, 2.0], [2.0, 1.0]]))
    labeled = _hold_adapter(np.array([[1.0, 2.0], [2.0, 1.0]]))
    _seed_tracks(anonymous, positions)
    _seed_tracks(labeled, positions)

    anonymous_scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
        labels=("opaque-a", "opaque-b"),
    )
    labeled_scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
        labels=("target-001", "actor-target-002"),
    )
    for index, observation in enumerate(labeled_scan):
        observation.metadata.update(
            {
                "truth_id": f"truth-{index}",
                "actor_name": f"actor-{index}",
                "d6_target_label": f"offline-{index}",
            }
        )

    anonymous_evidence = anonymous.process_scan_batch(
        anonymous_scan
    ).structural_ambiguity_evidence[0]
    labeled_evidence = labeled.process_scan_batch(
        labeled_scan
    ).structural_ambiguity_evidence[0]

    assert anonymous_evidence.to_dict() == labeled_evidence.to_dict()
    serialized = json.dumps(labeled_evidence.to_dict(), sort_keys=True).lower()
    assert all(
        value not in serialized
        for value in (
            "target-001",
            "actor-target-002",
            "truth-0",
            "truth-1",
            "actor-0",
            "actor-1",
            "offline-0",
            "offline-1",
        )
    )


def test_default_off_result_serialization_remains_compatible() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = {2: np.array([[1.0, 2.0], [2.0, 1.0]])}
    baseline = _PresetRadarCostAdapter(
        association_gate=40.0,
        preset_costs=costs,
    )
    explicit_false = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=False,
        preset_costs=costs,
    )
    _seed_tracks(baseline, positions)
    _seed_tracks(explicit_false, positions)
    scan = _scan(
        2,
        positions,
        measurement_timestamp=0.4,
        arrival_timestamp=0.6,
    )

    baseline_result = baseline.process_scan_batch(scan)
    explicit_result = explicit_false.process_scan_batch(scan)

    assert baseline_result.to_dict() == explicit_result.to_dict()
    assert baseline_result.structural_ambiguity_evidence == ()
    assert "structural_ambiguity_evidence" not in baseline_result.to_dict()
    assert all(
        "opaque_member_track_token" not in track.metadata
        for track in baseline_result.tracks
    )


def test_state_only_result_carries_the_same_serializable_evidence() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _hold_adapter(np.array([[1.0, 2.0], [2.0, 1.0]]))
    _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        ),
        materialize_tracks=False,
    )

    assert isinstance(result, FusionStateUpdateResult)
    assert len(result.structural_ambiguity_evidence) == 1
    assert result.to_dict()["structural_ambiguity_evidence"] == [
        result.structural_ambiguity_evidence[0].to_dict()
    ]


def test_evidence_roundtrip_rejects_bad_shape_covariance_and_identity_fields() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _hold_adapter(np.array([[1.0, 2.0], [2.0, 1.0]]))
    _seed_tracks(adapter, positions)
    evidence = adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    ).structural_ambiguity_evidence[0]
    payload = json.loads(json.dumps(evidence.to_dict()))

    restored = StructuralAmbiguityEvidence.from_dict(payload)
    assert restored.to_dict() == evidence.to_dict()

    bad_shape = deepcopy(payload)
    bad_shape["member_states"][0]["state"] = [0.0] * 5
    with pytest.raises(ValueError, match="shape"):
        StructuralAmbiguityEvidence.from_dict(bad_shape)

    bad_covariance = deepcopy(payload)
    bad_covariance["observations"][0]["covariance_ned"][0][0] = -1.0e6
    with pytest.raises(ValueError, match="positive semidefinite"):
        StructuralAmbiguityEvidence.from_dict(bad_covariance)

    identity_field = deepcopy(payload)
    identity_field["truth_id"] = "forbidden"
    with pytest.raises(ValueError, match="unknown"):
        StructuralAmbiguityEvidence.from_dict(identity_field)

    wrong_frame = deepcopy(payload)
    wrong_frame["frame_id"] = "ENU"
    with pytest.raises(ValueError, match="frame_id=NED"):
        StructuralAmbiguityEvidence.from_dict(wrong_frame)


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_hold_evidence_switch_requires_a_strict_bool(value: object) -> None:
    with pytest.raises(
        TypeError,
        match="radar_assignment_ambiguity_hold_evidence must be a bool",
    ):
        FusionAdapter(  # type: ignore[arg-type]
            radar_assignment_ambiguity_hold_evidence=value
        )


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "radar_assignment_ambiguity_governance": True,
            "radar_assignment_ambiguity_hold_evidence": True,
        },
        {
            "radar_assignment_ambiguity_governance_v2": True,
            "radar_assignment_ambiguity_hold_evidence": True,
        },
    ),
)
def test_hold_evidence_is_mutually_exclusive_with_rejected_candidates(
    kwargs: dict[str, bool],
) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        FusionAdapter(**kwargs)


def test_scalable_adapter_exposes_stable_default_publisher_epoch() -> None:
    adapter = Scalable3DFusionAdapter(
        radar_assignment_ambiguity_hold_evidence=True
    )

    audit = adapter.association_audit_summary()

    assert adapter.publisher_epoch == DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_EPOCH
    assert audit["radar_assignment_ambiguity_hold_evidence_enabled"] is True
    assert audit["structural_ambiguity_publisher_epoch"] == (
        DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_EPOCH
    )
    assert audit["structural_ambiguity_evidence_status"] == (
        "experimental_hold_evidence_enabled_pending_main_clean_ab"
    )
