from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
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
OPAQUE_SOURCE_METADATA_FIELDS = (
    "source_node_id",
    "source_track_id",
    "publisher_epoch",
    "opaque_member_track_token",
    "source_key",
)
OPAQUE_SOURCE_AUDIT_FIELDS = (
    "opaque_source_key_publication_requested",
    "opaque_source_key_publication_enabled",
    "opaque_source_key_publication_mode",
    "opaque_source_key_publisher_node_id",
    "opaque_source_key_publisher_epoch",
)


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


def _neutral_centroid_adapter(
    costs: np.ndarray,
    *,
    reverse_track_input: bool = False,
    **kwargs: object,
) -> _PresetRadarCostAdapter:
    parameters: dict[str, object] = {
        "association_gate": 40.0,
        "radar_assignment_ambiguity_hold_evidence": True,
        "radar_assignment_ambiguity_neutral_centroid_correction": True,
        "publisher_node_id": "D1_TEST_NODE",
        "publisher_epoch": "episode-neutral-centroid-001",
        "neutral_centroid_gate_chi2": 1.0e9,
        "neutral_centroid_shape_gate_m2": 1.0e9,
        "neutral_centroid_max_translation_m": 100.0,
        "preset_costs": {2: costs},
        "reverse_track_input": reverse_track_input,
    }
    parameters.update(kwargs)
    return _PresetRadarCostAdapter(**parameters)


def _assert_same_track_core(left, right) -> None:
    assert left.global_track_id == right.global_track_id
    np.testing.assert_allclose(left.state, right.state)
    np.testing.assert_allclose(left.covariance, right.covariance)
    assert left.timestamp == right.timestamp
    assert left.track_level == right.track_level
    assert left.source_support == right.source_support
    assert left.identity_likelihood == right.identity_likelihood
    assert left.last_nis == right.last_nis


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
        field not in track.metadata
        for track in baseline_result.tracks
        for field in OPAQUE_SOURCE_METADATA_FIELDS
    )
    audit = baseline.association_audit_summary()
    assert audit["opaque_source_key_publication_requested"] is False
    assert audit["opaque_source_key_publication_enabled"] is False
    assert audit["opaque_source_key_publication_mode"] == "disabled"


def test_source_only_mode_publishes_keys_without_changing_association_or_state() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = {2: np.array([[1.0, 2.0], [2.0, 1.0]])}
    baseline = _PresetRadarCostAdapter(
        association_gate=40.0,
        preset_costs=costs,
    )
    source_only = _PresetRadarCostAdapter(
        association_gate=40.0,
        publish_opaque_source_key=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-source-only-001",
        preset_costs=costs,
    )
    _seed_tracks(baseline, positions, moving=True)
    _seed_tracks(source_only, positions, moving=True)
    scan = _scan(
        2,
        tuple(position + np.array([20.0, 0.0, 0.0]) for position in positions),
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    baseline_result = baseline.process_scan_batch(scan)
    source_result = source_only.process_scan_batch(scan)

    assert baseline_result.summary.to_dict() == source_result.summary.to_dict()
    assert source_result.structural_ambiguity_evidence == ()
    assert source_result.summary.accepted_observation_count == 2
    assert source_result.summary.updated_track_count == 2
    assert source_result.summary.created_track_count == 0
    assert len(baseline_result.tracks) == len(source_result.tracks)
    for baseline_track, source_track in zip(
        baseline_result.tracks,
        source_result.tracks,
        strict=True,
    ):
        _assert_same_track_core(baseline_track, source_track)
        for field in OPAQUE_SOURCE_METADATA_FIELDS:
            assert field not in baseline_track.metadata
            assert field in source_track.metadata
        assert source_track.metadata["source_node_id"] == "D1_TEST_NODE"
        assert source_track.metadata["publisher_epoch"] == (
            "episode-source-only-001"
        )
        assert source_track.metadata["source_key"] == (
            f"{source_track.metadata['source_node_id']}::"
            f"{source_track.metadata['source_track_id']}"
        )
        baseline_record = baseline.tracks[baseline_track.global_track_id]
        source_record = source_only.tracks[source_track.global_track_id]
        assert baseline_record.hits == source_record.hits
        assert len(baseline_record.observations) == len(source_record.observations)
        assert baseline_record.association_diagnostics == (
            source_record.association_diagnostics
        )

    baseline_audit = baseline.association_audit_summary()
    source_audit = source_only.association_audit_summary()
    for field in OPAQUE_SOURCE_AUDIT_FIELDS:
        baseline_audit.pop(field)
        source_audit.pop(field)
    assert baseline_audit == source_audit
    assert source_only.association_audit_summary()[
        "opaque_source_key_publication_requested"
    ] is True
    assert source_only.association_audit_summary()[
        "opaque_source_key_publication_enabled"
    ] is True
    assert source_only.association_audit_summary()[
        "opaque_source_key_publication_mode"
    ] == "source_only"
    assert source_only.association_audit_summary()[
        "structural_ambiguity_evidence_component_count"
    ] == 0
    assert source_only.association_audit_summary()[
        "structural_ambiguity_prediction_only_member_count"
    ] == 0


def test_source_only_serialization_is_stable_and_hold_keeps_source_fields() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapters = tuple(
        FusionAdapter(
            publish_opaque_source_key=True,
            publisher_node_id="D1_TEST_NODE",
            publisher_epoch="episode-source-only-stable",
        )
        for _ in range(2)
    )
    results = tuple(
        adapter.process_scan_batch(
            _scan(
                0,
                positions,
                measurement_timestamp=0.0,
                arrival_timestamp=0.2,
            )
        )
        for adapter in adapters
    )
    baseline_result = FusionAdapter().process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )

    assert results[0].to_dict() == results[1].to_dict()
    assert results[0].summary.to_dict() == baseline_result.summary.to_dict()
    assert results[0].summary.created_track_count == 2
    for baseline_track, source_track in zip(
        baseline_result.tracks,
        results[0].tracks,
        strict=True,
    ):
        _assert_same_track_core(baseline_track, source_track)

    hold = FusionAdapter(
        radar_assignment_ambiguity_hold_evidence=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-hold-compatible",
    )
    hold_result = hold.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )
    for track in hold_result.tracks:
        for field in OPAQUE_SOURCE_METADATA_FIELDS:
            assert field in track.metadata
    hold_audit = hold.association_audit_summary()
    assert hold_audit["opaque_source_key_publication_requested"] is False
    assert hold_audit["opaque_source_key_publication_enabled"] is True
    assert hold_audit["opaque_source_key_publication_mode"] == (
        "structural_ambiguity_hold"
    )


def test_source_only_mode_does_not_change_oosm_replay() -> None:
    baseline = FusionAdapter()
    source_only = FusionAdapter(
        publish_opaque_source_key=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-source-only-oosm",
    )
    scans = (
        _scan(
            0,
            (np.array([1_000.0, 0.0, -100.0]),),
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        ),
        _scan(
            2,
            (np.array([1_010.0, 0.0, -100.0]),),
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        ),
        _scan(
            1,
            (np.array([1_005.0, 0.0, -100.0]),),
            measurement_timestamp=0.2,
            arrival_timestamp=0.8,
        ),
    )

    for scan in scans:
        baseline_result = baseline.process_scan_batch(scan)
        source_result = source_only.process_scan_batch(scan)
        assert baseline_result.summary.to_dict() == source_result.summary.to_dict()
        assert source_result.structural_ambiguity_evidence == ()
        assert len(baseline_result.tracks) == len(source_result.tracks)
        for baseline_track, source_track in zip(
            baseline_result.tracks,
            source_result.tracks,
            strict=True,
        ):
            _assert_same_track_core(baseline_track, source_track)

    assert baseline.latency_audit_summary().to_dict() == (
        source_only.latency_audit_summary().to_dict()
    )
    assert baseline.oosm_observation_count == 1
    assert baseline.replay_count == source_only.replay_count
    assert baseline.max_replay_observation_count == (
        source_only.max_replay_observation_count
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


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_opaque_source_key_switch_requires_a_strict_bool(value: object) -> None:
    with pytest.raises(
        TypeError,
        match="publish_opaque_source_key must be a bool",
    ):
        FusionAdapter(publish_opaque_source_key=value)  # type: ignore[arg-type]


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


def test_scalable_adapter_forwards_source_only_publication_switch() -> None:
    adapter = Scalable3DFusionAdapter(
        publish_opaque_source_key=True,
        publisher_node_id="D1_SCALABLE_TEST_NODE",
        publisher_epoch="episode-scalable-source-only",
    )

    result = adapter.process_scan_batch(
        _scan(
            0,
            (np.array([1_000.0, 0.0, -100.0]),),
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )

    assert result.structural_ambiguity_evidence == ()
    assert result.summary.created_track_count == 1
    assert result.tracks[0].metadata["source_node_id"] == (
        "D1_SCALABLE_TEST_NODE"
    )
    audit = adapter.association_audit_summary()
    assert audit["opaque_source_key_publication_enabled"] is True
    assert audit["opaque_source_key_publication_mode"] == "source_only"


def test_neutral_centroid_two_by_two_is_permutation_invariant() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    normal = _neutral_centroid_adapter(
        np.array([[1.0, 2.0], [2.0, 1.0]])
    )
    permuted = _neutral_centroid_adapter(
        np.array([[2.0, 1.0], [1.0, 2.0]]),
        reverse_track_input=True,
    )
    _seed_tracks(normal, positions, moving=True)
    _seed_tracks(permuted, positions, moving=True)
    shifted = tuple(
        position + np.array([35.0, 0.0, 0.0])
        for position in positions
    )
    scan = _scan(
        2,
        shifted,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
        labels=("opaque-left", "opaque-right"),
    )

    normal_result = normal.process_scan_batch(scan)
    permuted_result = permuted.process_scan_batch(tuple(reversed(scan)))

    assert normal_result.summary.to_dict() == permuted_result.summary.to_dict()
    for left, right in zip(
        normal_result.tracks,
        permuted_result.tracks,
        strict=True,
    ):
        _assert_same_track_core(left, right)
    normal_audit = normal.association_audit_summary()
    permuted_audit = permuted.association_audit_summary()
    assert normal_audit == permuted_audit
    assert normal_audit["neutral_centroid_applied_component_count"] == 1
    assert normal_audit["neutral_centroid_applied_member_count"] == 2


def test_neutral_centroid_applies_one_translation_without_identity_updates() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    hold = _hold_adapter(costs)
    candidate = _neutral_centroid_adapter(costs)
    track_ids = _seed_tracks(hold, positions, moving=True)
    assert track_ids == _seed_tracks(candidate, positions, moving=True)
    hold_before = {
        track_id: deepcopy(hold.tracks[track_id])
        for track_id in track_ids
    }
    candidate_before = {
        track_id: deepcopy(candidate.tracks[track_id])
        for track_id in track_ids
    }
    shifted = tuple(
        position + np.array([35.0, 0.0, 0.0])
        for position in positions
    )
    scan = _scan(
        2,
        shifted,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    hold_result = hold.process_scan_batch(scan)
    candidate_result = candidate.process_scan_batch(scan)

    hold_summary = hold_result.summary.to_dict()
    candidate_summary = candidate_result.summary.to_dict()
    assert candidate_summary["state_cache_miss_count"] == (
        hold_summary["state_cache_miss_count"] + len(track_ids)
    )
    candidate_summary["state_cache_miss_count"] = hold_summary[
        "state_cache_miss_count"
    ]
    assert hold_summary == candidate_summary
    assert hold_result.summary.accepted_observation_count == 0
    assert hold_result.summary.created_track_count == 0
    assert [item.global_track_id for item in hold_result.tracks] == list(
        track_ids
    )
    assert [item.global_track_id for item in candidate_result.tracks] == list(
        track_ids
    )

    translations: list[np.ndarray] = []
    for hold_track, candidate_track in zip(
        hold_result.tracks,
        candidate_result.tracks,
        strict=True,
    ):
        track_id = hold_track.global_track_id
        translations.append(
            candidate_track.state[:3] - hold_track.state[:3]
        )
        np.testing.assert_array_equal(
            candidate_track.state[3:],
            hold_track.state[3:],
        )
        assert candidate_track.track_level == hold_track.track_level
        assert candidate_track.source_support == hold_track.source_support
        assert (
            candidate_track.identity_likelihood
            == hold_track.identity_likelihood
        )
        hold_record = hold.tracks[track_id]
        candidate_record = candidate.tracks[track_id]
        assert candidate_record.hits == hold_record.hits
        assert candidate_record.hits == candidate_before[track_id].hits
        assert candidate_record.source_support == hold_record.source_support
        assert (
            candidate_record.identity_likelihood
            == hold_record.identity_likelihood
        )
        assert [
            item.observation_id for item in candidate_record.observations
        ] == [
            item.observation_id
            for item in candidate_before[track_id].observations
        ]
        assert [
            item.source_lineage_key for item in candidate_record.observations
        ] == [
            item.source_lineage_key
            for item in candidate_before[track_id].observations
        ]
        assert len(candidate_record.observations) == len(
            candidate_before[track_id].observations
        )
        assert candidate_record.accepted_observer_scan_keys == (
            candidate_before[track_id].accepted_observer_scan_keys
        )
        assert candidate_record.association_diagnostics == (
            hold_record.association_diagnostics
        )
        assert hold_before[track_id].hits == hold_record.hits

    assert np.linalg.norm(translations[0]) > 0.0
    np.testing.assert_allclose(
        translations[0],
        translations[1],
        atol=1.0e-10,
    )
    np.testing.assert_allclose(
        candidate_result.tracks[0].state[:3]
        - candidate_result.tracks[1].state[:3],
        hold_result.tracks[0].state[:3]
        - hold_result.tracks[1].state[:3],
    )
    evidence = candidate_result.structural_ambiguity_evidence[0]
    assert evidence.posterior_update_applied is False
    assert evidence.update_mode == "prediction_only"
    assert evidence.cross_covariance_available is False
    assert all(not item.velocity_evidence_used for item in evidence.observations)


def test_neutral_centroid_covariance_is_psd_and_never_contracts() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    hold = _hold_adapter(costs)
    candidate = _neutral_centroid_adapter(
        costs,
        neutral_centroid_min_position_variance_m2=0.5,
    )
    _seed_tracks(hold, positions, moving=True)
    _seed_tracks(candidate, positions, moving=True)
    scan = _scan(
        2,
        tuple(
            position + np.array([30.0, 0.0, 0.0])
            for position in positions
        ),
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    hold_result = hold.process_scan_batch(scan)
    candidate_result = candidate.process_scan_batch(scan)

    for posterior in candidate_result.tracks:
        publication_base = candidate._state_at(
            candidate.tracks[posterior.global_track_id],
            candidate.current_time,
        )
        covariance = posterior.covariance
        delta = covariance - publication_base.covariance
        np.testing.assert_allclose(covariance, covariance.T, atol=1.0e-10)
        np.testing.assert_allclose(delta, delta.T, atol=1.0e-10)
        assert np.isfinite(covariance).all()
        assert float(np.linalg.eigvalsh(covariance)[0]) >= -1.0e-8
        assert float(np.linalg.eigvalsh(delta)[0]) >= -1.0e-8
        assert np.all(np.diag(delta)[:3] > 0.0)
        np.testing.assert_allclose(delta[3:, :], 0.0, atol=1.0e-10)
        np.testing.assert_allclose(delta[:, 3:], 0.0, atol=1.0e-10)

    audit = candidate.association_audit_summary()
    assert audit["neutral_centroid_cross_covariance_available"] is False
    assert audit["neutral_centroid_applied_component_count"] == 1


@pytest.mark.parametrize(
    ("costs", "positions", "scan_positions", "expected_reason"),
    (
        (
            np.array(
                [
                    [1.58, INVALID_COST],
                    [0.80, INVALID_COST],
                    [INVALID_COST, 0.50],
                ]
            ),
            (
                np.array([1_000.0, -250.0, -100.0]),
                np.array([1_000.0, 0.0, -100.0]),
                np.array([1_000.0, 250.0, -100.0]),
            ),
            (
                np.array([1_000.0, 0.0, -100.0]),
                np.array([1_000.0, 250.0, -100.0]),
            ),
            "unbalanced_component",
        ),
        (
            np.array(
                [
                    [1.0, INVALID_COST, 2.0],
                    [INVALID_COST, 1.0, INVALID_COST],
                ]
            ),
            (
                np.array([1_000.0, -120.0, -100.0]),
                np.array([1_000.0, 120.0, -100.0]),
            ),
            (
                np.array([1_000.0, -120.0, -100.0]),
                np.array([1_000.0, 120.0, -100.0]),
                np.array([1_300.0, -80.0, -100.0]),
            ),
            "unbalanced_component",
        ),
    ),
)
def test_neutral_centroid_free_rows_and_columns_fail_closed(
    costs: np.ndarray,
    positions: tuple[np.ndarray, ...],
    scan_positions: tuple[np.ndarray, ...],
    expected_reason: str,
) -> None:
    adapter = _neutral_centroid_adapter(costs)
    _seed_tracks(adapter, positions)

    result = adapter.process_scan_batch(
        _scan(
            2,
            scan_positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    assert result.summary.accepted_observation_count <= 1
    audit = adapter.association_audit_summary()
    assert audit["neutral_centroid_applied_component_count"] == 0
    assert audit["neutral_centroid_rejected_component_count"] == 1
    assert audit["latest_neutral_centroid_rejection_reason"] == expected_reason


class _NonPureNeutralCentroidAdapter(_PresetRadarCostAdapter):
    def _scan_one_to_one_assignments(self, observations, pre_scan_track_ids):
        result = super()._scan_one_to_one_assignments(
            observations,
            pre_scan_track_ids,
        )
        altered_by_key = {}
        altered = {}
        for index, ambiguity in result.radar_ambiguities.items():
            key = (
                ambiguity.track_ids,
                ambiguity.observation_indices,
                ambiguity.policy_version,
            )
            changed = altered_by_key.setdefault(
                key,
                replace(
                    ambiguity,
                    component_kinds=(
                        "alternating_cycle",
                        "free_row_alternating_path",
                    ),
                ),
            )
            altered[index] = changed
        return replace(result, radar_ambiguities=altered)


class _RejectSecondNeutralCentroidGenerationAdapter(
    _PresetRadarCostAdapter
):
    def _scan_one_to_one_assignments(self, observations, pre_scan_track_ids):
        result = super()._scan_one_to_one_assignments(
            observations,
            pre_scan_track_ids,
        )
        if int(observations[0].metadata["sequence_id"]) != 3:
            return result
        altered_by_key = {}
        altered = {}
        for index, ambiguity in result.radar_ambiguities.items():
            key = (
                ambiguity.track_ids,
                ambiguity.observation_indices,
                ambiguity.policy_version,
            )
            changed = altered_by_key.setdefault(
                key,
                replace(
                    ambiguity,
                    component_kinds=(
                        "alternating_cycle",
                        "free_row_alternating_path",
                    ),
                ),
            )
            altered[index] = changed
        return replace(result, radar_ambiguities=altered)


def test_neutral_centroid_non_pure_component_fails_closed() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _NonPureNeutralCentroidAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-non-pure",
        preset_costs={2: np.array([[1.0, 2.0], [2.0, 1.0]])},
    )
    _seed_tracks(adapter, positions)

    adapter.process_scan_batch(
        _scan(
            2,
            positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        )
    )

    audit = adapter.association_audit_summary()
    assert audit["neutral_centroid_applied_component_count"] == 0
    assert audit["latest_neutral_centroid_rejection_reason"] == (
        "component_not_pure_alternating_cycle"
    )


def test_new_rejected_generation_removes_older_temporary_correction() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    preset_costs = {2: costs, 3: costs}
    hold = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-rejected-generation",
        preset_costs=preset_costs,
    )
    candidate = _RejectSecondNeutralCentroidGenerationAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-rejected-generation",
        neutral_centroid_gate_chi2=1.0e9,
        neutral_centroid_shape_gate_m2=1.0e9,
        neutral_centroid_max_translation_m=100.0,
        preset_costs=preset_costs,
    )
    track_ids = _seed_tracks(hold, positions, moving=True)
    assert track_ids == _seed_tracks(candidate, positions, moving=True)

    first_positions = tuple(
        hold._state_at(hold.tracks[track_id], 0.4).state[:3]
        + np.array([30.0, 0.0, 0.0])
        for track_id in track_ids
    )
    hold.process_scan_batch(
        _scan(
            2,
            first_positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.65,
        )
    )
    first_candidate = candidate.process_scan_batch(
        _scan(
            2,
            first_positions,
            measurement_timestamp=0.4,
            arrival_timestamp=0.65,
        )
    )
    assert np.linalg.norm(
        first_candidate.tracks[0].state[:3]
        - hold.tracks[track_ids[0]].current_state.state[:3]
    ) > 0.0
    before_rejection = {
        track_id: deepcopy(candidate.tracks[track_id])
        for track_id in track_ids
    }

    second_positions = tuple(
        hold._state_at(hold.tracks[track_id], 0.8).state[:3]
        + np.array([30.0, 0.0, 0.0])
        for track_id in track_ids
    )
    hold_result = hold.process_scan_batch(
        _scan(
            3,
            second_positions,
            measurement_timestamp=0.8,
            arrival_timestamp=1.05,
        )
    )
    candidate_result = candidate.process_scan_batch(
        _scan(
            3,
            second_positions,
            measurement_timestamp=0.8,
            arrival_timestamp=1.05,
        )
    )

    for hold_track, candidate_track in zip(
        hold_result.tracks,
        candidate_result.tracks,
        strict=True,
    ):
        track_id = candidate_track.global_track_id
        exact_base = candidate._state_at(
            candidate.tracks[track_id],
            candidate.current_time,
        )
        np.testing.assert_allclose(
            candidate_track.state,
            exact_base.state,
            atol=1.0e-8,
        )
        assert candidate.tracks[track_id].hits == (
            before_rejection[track_id].hits
        )
        assert [
            item.source_lineage_key
            for item in candidate.tracks[track_id].observations
        ] == [
            item.source_lineage_key
            for item in before_rejection[track_id].observations
        ]
        assert candidate.tracks[track_id].source_support == (
            before_rejection[track_id].source_support
        )
        assert candidate_track.track_level == hold_track.track_level

    audit = candidate.association_audit_summary()
    assert audit["neutral_centroid_applied_component_count"] == 1
    assert audit["neutral_centroid_rejected_component_count"] == 1
    assert audit["latest_neutral_centroid_rejection_reason"] == (
        "component_not_pure_alternating_cycle"
    )


def test_neutral_centroid_ignores_unobserved_radial_velocity_placeholder() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    reference = _neutral_centroid_adapter(costs)
    placeholder = _neutral_centroid_adapter(costs)
    _seed_tracks(reference, positions, moving=True)
    _seed_tracks(placeholder, positions, moving=True)
    scan = _scan(
        2,
        tuple(
            position + np.array([35.0, 0.0, 0.0])
            for position in positions
        ),
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    placeholder_scan = deepcopy(scan)
    placeholder_scan[0].measurement[3] = 50_000.0
    placeholder_scan[1].measurement[3] = -50_000.0

    reference_result = reference.process_scan_batch(scan)
    placeholder_result = placeholder.process_scan_batch(placeholder_scan)

    for left, right in zip(
        reference_result.tracks,
        placeholder_result.tracks,
        strict=True,
    ):
        _assert_same_track_core(left, right)
    assert all(
        not item.radial_velocity_observed
        and not item.velocity_evidence_used
        for item in placeholder_result.structural_ambiguity_evidence[
            0
        ].observations
    )


@pytest.mark.parametrize(
    ("mode", "expected_reason"),
    (
        ("stale", "stale_scan"),
        ("oosm", "oosm_scan"),
        ("duplicate", "duplicate_source_claim"),
        ("conflict", "conflicting_source_claim"),
        ("truth", "forbidden_identity_metadata"),
    ),
)
def test_neutral_centroid_timing_lineage_and_identity_fail_closed(
    mode: str,
    expected_reason: str,
) -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    adapter = _neutral_centroid_adapter(
        np.array([[1.0, 2.0], [2.0, 1.0]])
    )
    _seed_tracks(adapter, positions, moving=True)
    scan_positions = tuple(
        position + np.array([30.0, 0.0, 0.0])
        for position in positions
    )
    if mode == "duplicate":
        scan_positions = (scan_positions[0], scan_positions[0].copy())
    measurement_timestamp = 0.3 if mode == "oosm" else 0.4
    scan = list(
        _scan(
            2,
            scan_positions,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=0.65,
        )
    )
    if mode == "stale":
        scan = [replace(item, stale_after_s=0.05) for item in scan]
    if mode in {"duplicate", "conflict"}:
        for item in scan:
            item.metadata["source_lineage_key"] = (
                "explicit",
                "same-component-claim",
            )
    if mode == "truth":
        scan[0].metadata["truth_id"] = "offline-truth-001"

    result = adapter.process_scan_batch(tuple(scan))

    assert result.summary.accepted_observation_count == 0
    audit = adapter.association_audit_summary()
    assert audit["neutral_centroid_applied_component_count"] == 0
    assert audit["neutral_centroid_rejected_component_count"] == 1
    assert audit["latest_neutral_centroid_rejection_reason"] == expected_reason


class _DoubleApplyNeutralCentroidAdapter(_PresetRadarCostAdapter):
    def _apply_structural_ambiguity_neutral_centroid_corrections(
        self,
        observations,
        result,
        evidence,
        *,
        scan_has_oosm,
        scan_has_stale_observation,
    ):
        kwargs = {
            "scan_has_oosm": scan_has_oosm,
            "scan_has_stale_observation": scan_has_stale_observation,
        }
        super()._apply_structural_ambiguity_neutral_centroid_corrections(
            observations,
            result,
            evidence,
            **kwargs,
        )
        super()._apply_structural_ambiguity_neutral_centroid_corrections(
            observations,
            result,
            evidence,
            **kwargs,
        )


class _CapturingNeutralCentroidAdapter(_PresetRadarCostAdapter):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.neutral_centroid_calls = []

    def _apply_structural_ambiguity_neutral_centroid_corrections(
        self,
        observations,
        result,
        evidence,
        *,
        scan_has_oosm,
        scan_has_stale_observation,
    ):
        self.neutral_centroid_calls.append(
            (
                tuple(observations),
                result,
                evidence,
                bool(scan_has_oosm),
                bool(scan_has_stale_observation),
            )
        )
        return super()._apply_structural_ambiguity_neutral_centroid_corrections(
            observations,
            result,
            evidence,
            scan_has_oosm=scan_has_oosm,
            scan_has_stale_observation=scan_has_stale_observation,
        )


def test_neutral_centroid_same_evidence_generation_is_idempotent() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    normal = _neutral_centroid_adapter(costs)
    repeated = _DoubleApplyNeutralCentroidAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-centroid-001",
        neutral_centroid_gate_chi2=1.0e9,
        neutral_centroid_shape_gate_m2=1.0e9,
        neutral_centroid_max_translation_m=100.0,
        preset_costs={2: costs},
    )
    _seed_tracks(normal, positions, moving=True)
    _seed_tracks(repeated, positions, moving=True)
    scan = _scan(
        2,
        tuple(
            position + np.array([35.0, 0.0, 0.0])
            for position in positions
        ),
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    normal_result = normal.process_scan_batch(scan)
    repeated_result = repeated.process_scan_batch(scan)

    for left, right in zip(
        normal_result.tracks,
        repeated_result.tracks,
        strict=True,
    ):
        _assert_same_track_core(left, right)
    audit = repeated.association_audit_summary()
    assert audit["neutral_centroid_candidate_component_count"] == 2
    assert audit["neutral_centroid_applied_component_count"] == 1
    assert audit["neutral_centroid_duplicate_generation_rejection_count"] == 1
    assert audit["neutral_centroid_rejection_reasons"] == {
        "duplicate_evidence_generation": 1
    }


def test_neutral_centroid_consecutive_generations_replace_temporary_correction() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    preset_costs = {scan_index: costs for scan_index in (2, 3, 4)}
    common = {
        "association_gate": 40.0,
        "radar_assignment_ambiguity_hold_evidence": True,
        "publisher_node_id": "D1_TEST_NODE",
        "publisher_epoch": "episode-neutral-consecutive",
        "preset_costs": preset_costs,
    }
    hold = _PresetRadarCostAdapter(**common)
    candidate = _PresetRadarCostAdapter(
        **common,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        neutral_centroid_gate_chi2=1.0e9,
        neutral_centroid_shape_gate_m2=1.0e9,
        neutral_centroid_max_translation_m=100.0,
    )
    track_ids = _seed_tracks(hold, positions, moving=True)
    assert track_ids == _seed_tracks(candidate, positions, moving=True)

    expected_translation: np.ndarray | None = None
    for scan_index, measurement_timestamp in zip(
        (2, 3, 4),
        (0.4, 0.8, 1.2),
        strict=True,
    ):
        replay_positions = tuple(
            hold._state_at(
                hold.tracks[track_id],
                measurement_timestamp,
            ).state[:3]
            for track_id in track_ids
        )
        scan = _scan(
            scan_index,
            tuple(
                position + np.array([30.0, 0.0, 0.0])
                for position in replay_positions
            ),
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=measurement_timestamp + 0.25,
        )

        hold_result = hold.process_scan_batch(scan)
        candidate_result = candidate.process_scan_batch(scan)
        translations = tuple(
            candidate_track.state[:3] - hold_track.state[:3]
            for hold_track, candidate_track in zip(
                hold_result.tracks,
                candidate_result.tracks,
                strict=True,
            )
        )

        np.testing.assert_allclose(
            translations[0],
            translations[1],
            atol=1.0e-10,
        )
        if expected_translation is None:
            expected_translation = translations[0].copy()
            assert np.linalg.norm(expected_translation) > 0.0
        else:
            np.testing.assert_allclose(
                translations[0],
                expected_translation,
                atol=1.0e-8,
            )
        for hold_track, candidate_track in zip(
            hold_result.tracks,
            candidate_result.tracks,
            strict=True,
        ):
            np.testing.assert_array_equal(
                candidate_track.state[3:],
                hold_track.state[3:],
            )

    audit = candidate.association_audit_summary()
    assert audit["neutral_centroid_rejection_reasons"] == {}
    assert audit["neutral_centroid_applied_component_count"] == 3, audit


def test_neutral_centroid_normal_observation_replaces_temporary_correction() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    ambiguous_costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    unique_costs = np.array([[1.0, INVALID_COST], [INVALID_COST, 1.0]])
    preset_costs = {
        2: ambiguous_costs,
        3: ambiguous_costs,
        4: ambiguous_costs,
        5: unique_costs,
    }
    common = {
        "association_gate": 40.0,
        "radar_assignment_ambiguity_hold_evidence": True,
        "publisher_node_id": "D1_TEST_NODE",
        "publisher_epoch": "episode-neutral-replacement",
        "preset_costs": preset_costs,
    }
    hold = _PresetRadarCostAdapter(**common)
    candidate = _PresetRadarCostAdapter(
        **common,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        neutral_centroid_gate_chi2=1.0e9,
        neutral_centroid_shape_gate_m2=1.0e9,
        neutral_centroid_max_translation_m=100.0,
    )
    track_ids = _seed_tracks(hold, positions, moving=True)
    assert track_ids == _seed_tracks(candidate, positions, moving=True)

    for scan_index, measurement_timestamp in zip(
        (2, 3, 4),
        (0.4, 0.8, 1.2),
        strict=True,
    ):
        replay_positions = tuple(
            hold._state_at(
                hold.tracks[track_id],
                measurement_timestamp,
            ).state[:3]
            for track_id in track_ids
        )
        scan = _scan(
            scan_index,
            tuple(
                position + np.array([30.0, 0.0, 0.0])
                for position in replay_positions
            ),
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=measurement_timestamp + 0.25,
        )
        hold.process_scan_batch(scan)
        candidate.process_scan_batch(scan)

    before = {
        track_id: deepcopy(candidate.tracks[track_id])
        for track_id in track_ids
    }
    probe_timestamp = candidate.current_time + 0.1
    candidate_deltas_before_prediction = {
        track_id: (
            candidate.tracks[track_id].current_state.state[:3]
            - hold.tracks[track_id].current_state.state[:3]
        )
        for track_id in track_ids
    }
    candidate._predict_all_to(probe_timestamp)
    hold._predict_all_to(probe_timestamp)
    for track_id in track_ids:
        np.testing.assert_allclose(
            candidate.tracks[track_id].current_state.state[:3]
            - hold.tracks[track_id].current_state.state[:3],
            candidate_deltas_before_prediction[track_id],
            atol=1.0e-8,
        )
        np.testing.assert_allclose(
            candidate._state_at(
                candidate.tracks[track_id],
                probe_timestamp,
            ).state,
            hold._state_at(
                hold.tracks[track_id],
                probe_timestamp,
            ).state,
            atol=1.0e-8,
        )

    measurement_timestamp = 1.6
    normal_positions = tuple(
        hold._state_at(
            hold.tracks[track_id],
            measurement_timestamp,
        ).state[:3]
        for track_id in track_ids
    )
    normal_scan = _scan(
        5,
        normal_positions,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=1.85,
    )
    hold_result = hold.process_scan_batch(normal_scan)
    candidate_result = candidate.process_scan_batch(normal_scan)

    assert hold_result.summary.accepted_observation_count == 2
    assert candidate_result.summary.accepted_observation_count == 2
    for hold_track, candidate_track in zip(
        hold_result.tracks,
        candidate_result.tracks,
        strict=True,
    ):
        _assert_same_track_core(hold_track, candidate_track)
        track_id = candidate_track.global_track_id
        candidate_record = candidate.tracks[track_id]
        hold_record = hold.tracks[track_id]
        assert candidate_record.hits == before[track_id].hits + 1
        assert candidate_record.hits == hold_record.hits
        assert len(candidate_record.observations) == (
            len(before[track_id].observations) + 1
        )
        assert [
            item.source_lineage_key
            for item in candidate_record.observations
        ] == [
            item.source_lineage_key for item in hold_record.observations
        ]
        assert candidate_record.source_support == hold_record.source_support
        assert candidate_record.source_support["radar"] == (
            before[track_id].source_support["radar"] + 1
        )
        assert candidate_record.association_diagnostics == (
            hold_record.association_diagnostics
        )
        assert candidate_track.track_level == hold_track.track_level

    audit = candidate.association_audit_summary()
    assert audit["neutral_centroid_applied_component_count"] == 3
    assert audit["neutral_centroid_applied_member_count"] == 6
    assert audit["neutral_centroid_generation_registry_current_entry_count"] == 1


def test_neutral_centroid_generation_registry_is_bounded_per_component() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = np.array([[1.0, 2.0], [2.0, 1.0]])
    generations = 24
    adapter = _CapturingNeutralCentroidAdapter(
        association_gate=40.0,
        buffer_horizon=20.0,
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-registry-long",
        neutral_centroid_gate_chi2=1.0e9,
        neutral_centroid_shape_gate_m2=1.0e9,
        neutral_centroid_max_translation_m=100.0,
        neutral_centroid_generation_registry_max_entries=2,
        preset_costs={
            scan_index: costs
            for scan_index in range(2, 2 + generations)
        },
    )
    track_ids = _seed_tracks(adapter, positions, moving=True)

    for offset, scan_index in enumerate(range(2, 2 + generations)):
        measurement_timestamp = 0.4 + 0.4 * offset
        replay_positions = tuple(
            adapter._state_at(
                adapter.tracks[track_id],
                measurement_timestamp,
            ).state[:3]
            for track_id in track_ids
        )
        adapter.process_scan_batch(
            _scan(
                scan_index,
                tuple(
                    position + np.array([20.0, 0.0, 0.0])
                    for position in replay_positions
                ),
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=measurement_timestamp + 0.2,
            )
        )

    assert len(adapter._neutral_centroid_generation_registry) == 1
    watermark = next(
        iter(adapter._neutral_centroid_generation_registry.values())
    )
    assert watermark.max_seen_generation == generations
    assert watermark.max_applied_generation == generations
    before_replay = {
        track_id: adapter.tracks[track_id].current_state.copy()
        for track_id in track_ids
    }
    observations, result, evidence, scan_oosm, scan_stale = (
        adapter.neutral_centroid_calls[-1]
    )
    FusionAdapter._apply_structural_ambiguity_neutral_centroid_corrections(
        adapter,
        list(observations),
        result,
        evidence,
        scan_has_oosm=scan_oosm,
        scan_has_stale_observation=scan_stale,
    )
    regressed_evidence = tuple(
        replace(
            item,
            component_generation=item.component_generation - 1,
        )
        for item in evidence
    )
    FusionAdapter._apply_structural_ambiguity_neutral_centroid_corrections(
        adapter,
        list(observations),
        result,
        regressed_evidence,
        scan_has_oosm=scan_oosm,
        scan_has_stale_observation=scan_stale,
    )

    for track_id in track_ids:
        np.testing.assert_array_equal(
            adapter.tracks[track_id].current_state.state,
            before_replay[track_id].state,
        )
        np.testing.assert_array_equal(
            adapter.tracks[track_id].current_state.covariance,
            before_replay[track_id].covariance,
        )
    audit = adapter.association_audit_summary()
    assert audit["neutral_centroid_generation_registry_current_entry_count"] == 1
    assert audit["neutral_centroid_generation_registry_peak_entry_count"] == 1
    assert audit["neutral_centroid_generation_registry_eviction_count"] == 0
    assert audit["neutral_centroid_duplicate_generation_rejection_count"] == 1
    assert audit["neutral_centroid_regressed_generation_rejection_count"] == 1
    assert audit["neutral_centroid_rejection_reasons"][
        "duplicate_evidence_generation"
    ] == 1
    assert audit["neutral_centroid_rejection_reasons"][
        "regressed_evidence_generation"
    ] == 1


def test_neutral_centroid_registry_capacity_preserves_active_fixed_lag_entries() -> None:
    track_count = 6
    positions = tuple(
        np.array([1_000.0, -250.0 + 100.0 * index, -100.0])
        for index in range(track_count)
    )

    def cycle_costs(left: int, right: int) -> np.ndarray:
        costs = np.full((track_count, track_count), INVALID_COST)
        np.fill_diagonal(costs, 1.0)
        costs[left, right] = 2.0
        costs[right, left] = 2.0
        return costs

    adapter = _CapturingNeutralCentroidAdapter(
        association_gate=40.0,
        buffer_horizon=0.5,
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-registry-capacity",
        neutral_centroid_gate_chi2=1.0e9,
        neutral_centroid_shape_gate_m2=1.0e9,
        neutral_centroid_max_translation_m=100.0,
        neutral_centroid_generation_registry_max_entries=1,
        preset_costs={
            1: np.where(
                np.eye(track_count, dtype=bool),
                1.0,
                INVALID_COST,
            ),
            2: cycle_costs(0, 1),
            3: cycle_costs(2, 3),
            4: cycle_costs(4, 5),
        },
    )
    track_ids = _seed_tracks(adapter, positions, moving=True)
    first_call = None
    for scan_index, measurement_timestamp in (
        (2, 0.4),
        (3, 0.8),
        (4, 1.4),
    ):
        replay_positions = tuple(
            adapter._state_at(
                adapter.tracks[track_id],
                measurement_timestamp,
            ).state[:3]
            for track_id in track_ids
        )
        adapter.process_scan_batch(
            _scan(
                scan_index,
                tuple(
                    position + np.array([15.0, 0.0, 0.0])
                    for position in replay_positions
                ),
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=measurement_timestamp + 0.1,
            )
        )
        if first_call is None:
            first_call = next(
                call
                for call in adapter.neutral_centroid_calls
                if call[2]
            )

    audit = adapter.association_audit_summary()
    assert audit["neutral_centroid_generation_registry_current_entry_count"] == 1
    assert audit["neutral_centroid_generation_registry_peak_entry_count"] == 1
    assert audit["neutral_centroid_generation_registry_eviction_count"] == 1
    assert (
        audit[
            "neutral_centroid_generation_registry_capacity_rejection_count"
        ]
        == 1
    )
    before_old_replay = {
        track_id: adapter.tracks[track_id].current_state.copy()
        for track_id in track_ids
    }
    assert first_call is not None
    observations, result, evidence, scan_oosm, scan_stale = first_call
    FusionAdapter._apply_structural_ambiguity_neutral_centroid_corrections(
        adapter,
        list(observations),
        result,
        evidence,
        scan_has_oosm=scan_oosm,
        scan_has_stale_observation=scan_stale,
    )

    for track_id in track_ids:
        np.testing.assert_array_equal(
            adapter.tracks[track_id].current_state.state,
            before_old_replay[track_id].state,
        )
        np.testing.assert_array_equal(
            adapter.tracks[track_id].current_state.covariance,
            before_old_replay[track_id].covariance,
        )
    audit = adapter.association_audit_summary()
    assert audit["latest_neutral_centroid_rejection_reason"] == (
        "evidence_outside_fixed_lag"
    )
    assert audit["neutral_centroid_generation_registry_current_entry_count"] == 1
    assert audit["neutral_centroid_generation_registry_eviction_count"] == 1


def test_neutral_centroid_default_false_is_strictly_equivalent() -> None:
    positions = (
        np.array([1_000.0, -120.0, -100.0]),
        np.array([1_000.0, 120.0, -100.0]),
    )
    costs = {2: np.array([[1.0, 2.0], [2.0, 1.0]])}
    omitted = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-default-off",
        preset_costs=costs,
    )
    explicit_false = _PresetRadarCostAdapter(
        association_gate=40.0,
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=False,
        publisher_node_id="D1_TEST_NODE",
        publisher_epoch="episode-neutral-default-off",
        preset_costs=costs,
    )
    _seed_tracks(omitted, positions, moving=True)
    _seed_tracks(explicit_false, positions, moving=True)
    scan = _scan(
        2,
        tuple(
            position + np.array([35.0, 0.0, 0.0])
            for position in positions
        ),
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    omitted_result = omitted.process_scan_batch(scan)
    explicit_result = explicit_false.process_scan_batch(scan)

    assert omitted_result.to_dict() == explicit_result.to_dict()
    assert omitted.association_audit_summary() == (
        explicit_false.association_audit_summary()
    )
    assert (
        "neutral_centroid_candidate_component_count"
        not in omitted.association_audit_summary()
    )


def test_neutral_centroid_k_max_and_linear_operation_count() -> None:
    positions = (
        np.array([1_000.0, -200.0, -100.0]),
        np.array([1_000.0, 0.0, -100.0]),
        np.array([1_000.0, 200.0, -100.0]),
    )
    costs = np.full((3, 3), 2.0)
    np.fill_diagonal(costs, 1.0)
    rejected = _neutral_centroid_adapter(
        costs,
        neutral_centroid_max_component_size=2,
    )
    accepted = _neutral_centroid_adapter(
        costs,
        neutral_centroid_max_component_size=3,
    )
    _seed_tracks(rejected, positions, moving=True)
    _seed_tracks(accepted, positions, moving=True)
    scan = _scan(
        2,
        tuple(
            position + np.array([30.0, 0.0, 0.0])
            for position in positions
        ),
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )

    rejected.process_scan_batch(scan)
    accepted.process_scan_batch(scan)

    rejected_audit = rejected.association_audit_summary()
    accepted_audit = accepted.association_audit_summary()
    assert rejected_audit["neutral_centroid_applied_component_count"] == 0
    assert rejected_audit["latest_neutral_centroid_rejection_reason"] == (
        "component_exceeds_k_max"
    )
    assert rejected_audit["neutral_centroid_linear_input_operation_count"] == 0
    assert accepted_audit["neutral_centroid_applied_component_count"] == 1
    assert accepted_audit["neutral_centroid_applied_member_count"] == 3
    assert accepted_audit["neutral_centroid_linear_input_operation_count"] == 6
    assert accepted_audit["max_neutral_centroid_component_size"] == 3


def test_neutral_centroid_200_track_sparse_graph_only_counts_component_inputs() -> None:
    track_count = 200
    positions = tuple(
        np.array(
            [
                2_000.0,
                -1_990.0 + 20.0 * index,
                -100.0,
            ]
        )
        for index in range(track_count)
    )
    costs = np.full((track_count, track_count), INVALID_COST)
    np.fill_diagonal(costs, 1.0)
    costs[0, 1] = 2.0
    costs[1, 0] = 2.0
    adapter = _neutral_centroid_adapter(costs)
    first = adapter.process_scan_batch(
        _scan(
            0,
            positions,
            measurement_timestamp=0.0,
            arrival_timestamp=0.1,
        )
    )
    assert first.summary.created_track_count == track_count

    result = adapter.process_scan_batch(
        _scan(
            2,
            tuple(
                position + np.array([15.0, 0.0, 0.0])
                for position in positions
            ),
            measurement_timestamp=0.2,
            arrival_timestamp=0.3,
        )
    )

    audit = adapter.association_audit_summary()
    assert len(result.tracks) == track_count
    assert result.summary.updated_track_count == track_count - 2
    assert audit["neutral_centroid_candidate_component_count"] == 1
    assert audit["neutral_centroid_applied_component_count"] == 1
    assert audit["neutral_centroid_applied_member_count"] == 2
    assert audit["neutral_centroid_linear_input_operation_count"] == 4
    assert audit["max_neutral_centroid_component_size"] == 2


@pytest.mark.parametrize(
    ("name", "value", "error"),
    (
        (
            "radar_assignment_ambiguity_neutral_centroid_correction",
            1,
            TypeError,
        ),
        ("neutral_centroid_max_component_size", True, TypeError),
        ("neutral_centroid_max_component_size", 1, ValueError),
        ("neutral_centroid_max_component_size", 257, ValueError),
        ("neutral_centroid_gain", "0.5", TypeError),
        ("neutral_centroid_gain", 1.1, ValueError),
        ("neutral_centroid_max_translation_m", 0.0, ValueError),
        ("neutral_centroid_gate_chi2", float("inf"), ValueError),
        ("neutral_centroid_shape_gate_m2", -1.0, ValueError),
        ("neutral_centroid_shape_inflation_scale", -1.0, ValueError),
        ("neutral_centroid_min_position_variance_m2", -1.0, ValueError),
        (
            "neutral_centroid_generation_registry_max_entries",
            True,
            TypeError,
        ),
        (
            "neutral_centroid_generation_registry_max_entries",
            0,
            ValueError,
        ),
        (
            "neutral_centroid_generation_registry_max_entries",
            1_000_001,
            ValueError,
        ),
    ),
)
def test_neutral_centroid_parameters_are_strictly_validated(
    name: str,
    value: object,
    error: type[Exception],
) -> None:
    kwargs = {
        "radar_assignment_ambiguity_hold_evidence": True,
        name: value,
    }
    with pytest.raises(error):
        FusionAdapter(**kwargs)


def test_neutral_centroid_requires_hold_and_rejects_truth_hint_mode() -> None:
    with pytest.raises(ValueError, match="requires"):
        FusionAdapter(
            radar_assignment_ambiguity_neutral_centroid_correction=True
        )
    with pytest.raises(ValueError, match="incompatible"):
        FusionAdapter(
            radar_assignment_ambiguity_hold_evidence=True,
            radar_assignment_ambiguity_neutral_centroid_correction=True,
            use_truth_hints_for_association=True,
        )


def test_scalable_adapter_forwards_neutral_centroid_candidate_switch() -> None:
    adapter = Scalable3DFusionAdapter(
        radar_assignment_ambiguity_hold_evidence=True,
        radar_assignment_ambiguity_neutral_centroid_correction=True,
        neutral_centroid_max_component_size=3,
        neutral_centroid_gain=0.25,
        neutral_centroid_max_translation_m=12.0,
        neutral_centroid_generation_registry_max_entries=17,
    )

    audit = adapter.association_audit_summary()

    assert audit["neutral_centroid_correction_requested"] is True
    assert audit["neutral_centroid_correction_enabled"] is True
    assert audit["neutral_centroid_correction_status"] == (
        "experimental_identity_neutral_centroid_candidate_not_promoted"
    )
    assert audit["neutral_centroid_publication_state_semantics"] == (
        "exact_replay_frame_replacement_v1"
    )
    assert audit["neutral_centroid_generation_registry_policy"] == (
        "per_component_fixed_lag_watermark_hard_capacity_v1"
    )
    assert audit["neutral_centroid_max_component_size"] == 3
    assert audit["neutral_centroid_gain"] == 0.25
    assert audit["neutral_centroid_max_translation_m"] == 12.0
    assert audit["neutral_centroid_generation_registry_max_entries"] == 17
    assert audit["neutral_centroid_generation_registry_current_entry_count"] == 0
    assert audit["neutral_centroid_generation_registry_peak_entry_count"] == 0
    assert audit["neutral_centroid_generation_registry_eviction_count"] == 0
