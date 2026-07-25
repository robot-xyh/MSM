from __future__ import annotations

import json

import numpy as np
import pytest

from d1_sensor_fusion import FusionAdapter, SensorObservation
from d1_sensor_fusion.fusion import (
    MAX_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY,
    OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION_ID,
    OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION_ID,
)
from d1_sensor_fusion.observations import (
    radar_covariance_from_range,
    radar_h,
)


_OPERATION_COUNT_KEYS = {
    "request_count",
    "cache_hit_count",
    "cache_miss_count",
    "identity_build_count",
    "cache_eviction_count",
    "reference_bypass_count",
    "peak_entry_count",
    "generation_invalidation_count",
    "generation_invalidated_entry_count",
    "explicit_reset_count",
    "explicit_reset_entry_count",
}


def _radar_scan(
    positions: tuple[tuple[float, float, float], ...],
    *,
    scan_index: int,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> tuple[SensorObservation, ...]:
    observations = []
    scan_id = f"opaque-source-scan-{scan_index:03d}"
    for index, position in enumerate(positions):
        state = np.asarray((*position, 4.0, 0.0, 0.0), dtype=float)
        measurement = radar_h(state, np.zeros(3))
        observations.append(
            SensorObservation(
                observation_id=f"{scan_id}-observation-{index:03d}",
                sensor_id="RADAR-OPAQUE-SOURCE",
                modality="radar",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(
                    float(measurement[0])
                ),
                classification_hint=(
                    "fixed-wing" if index % 2 == 0 else "rotorcraft"
                ),
                confidence=0.85 + 0.01 * index,
                metadata={
                    "sensor_position_ned": np.zeros(3),
                    "scan_id": scan_id,
                    "source_lineage_key": (
                        "explicit",
                        "RADAR-OPAQUE-SOURCE",
                        scan_id,
                        index,
                    ),
                },
            )
        )
    return tuple(observations)


def _adapters(
    *,
    capacity: int = 16,
) -> tuple[FusionAdapter, FusionAdapter]:
    common = {
        "publish_opaque_source_key": True,
        "publisher_node_id": "D1-OPAQUE-SOURCE-TEST",
        "publisher_epoch": "episode-opaque-source-001",
        "opaque_source_identity_cache_capacity": capacity,
    }
    return (
        FusionAdapter(
            **common,
            cached_opaque_source_identity=False,
        ),
        FusionAdapter(
            **common,
            cached_opaque_source_identity=True,
        ),
    )


def _canonical_tracks(tracks: object) -> str:
    return json.dumps(
        [track.to_dict() for track in tracks],
        sort_keys=True,
        separators=(",", ":"),
    )


def _assert_conservation(adapter: FusionAdapter) -> None:
    diagnostics = adapter.opaque_source_identity_cache_diagnostics()
    assert set(diagnostics["operation_counts"]) == _OPERATION_COUNT_KEYS
    assert all(diagnostics["conservation"].values())


def test_candidate_is_explicit_default_off_and_configuration_is_bounded() -> None:
    default = FusionAdapter()
    candidate = FusionAdapter(cached_opaque_source_identity=True)

    assert default.cached_opaque_source_identity is False
    assert (
        default.opaque_source_identity_cache_diagnostics()[
            "implementation_id"
        ]
        == OPAQUE_SOURCE_IDENTITY_REFERENCE_IMPLEMENTATION_ID
    )
    assert (
        candidate.opaque_source_identity_cache_diagnostics()[
            "implementation_id"
        ]
        == OPAQUE_SOURCE_IDENTITY_CANDIDATE_IMPLEMENTATION_ID
    )
    with pytest.raises(
        TypeError,
        match="cached_opaque_source_identity must be a bool",
    ):
        FusionAdapter(cached_opaque_source_identity=1)  # type: ignore[arg-type]
    with pytest.raises(
        TypeError,
        match="cache_capacity must be an integer",
    ):
        FusionAdapter(
            opaque_source_identity_cache_capacity=True  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="must be at least 1"):
        FusionAdapter(opaque_source_identity_cache_capacity=0)
    with pytest.raises(ValueError, match="must be at most"):
        FusionAdapter(
            opaque_source_identity_cache_capacity=(
                MAX_OPAQUE_SOURCE_IDENTITY_CACHE_CAPACITY + 1
            )
        )


def test_cache_is_inert_without_source_publication_or_hold() -> None:
    adapter = FusionAdapter(cached_opaque_source_identity=True)
    result = adapter.process_scan_batch(
        _radar_scan(
            ((1_000.0, 0.0, -100.0),),
            scan_index=0,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )

    assert len(result.tracks) == 1
    diagnostics = adapter.opaque_source_identity_cache_diagnostics()
    assert diagnostics["operation_counts"]["request_count"] == 0
    assert diagnostics["cache_entry_count"] == 0
    _assert_conservation(adapter)


def test_every_publication_is_byte_equivalent_and_does_not_alias_cache() -> None:
    reference, candidate = _adapters()
    positions = (
        (1_000.0, -200.0, -100.0),
        (1_000.0, 200.0, -100.0),
    )

    reference_result = reference.process_scan_batch(
        _radar_scan(
            positions,
            scan_index=0,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )
    candidate_result = candidate.process_scan_batch(
        _radar_scan(
            positions,
            scan_index=0,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        )
    )
    assert _canonical_tracks(candidate_result.tracks) == _canonical_tracks(
        reference_result.tracks
    )

    for _ in range(4):
        assert _canonical_tracks(
            candidate.global_tracks()
        ) == _canonical_tracks(reference.global_tracks())

    published = candidate.global_tracks()[0]
    expected = reference.global_tracks()[0].to_dict()
    published.state[:] = -1.0
    published.covariance[:] = -1.0
    published.source_support["radar"] = 999
    published.identity_likelihood["fixed-wing"] = 999.0
    published.metadata["source_key"] = "mutated"
    published.metadata["opaque_member_track_token"] = "mutated"

    assert candidate.global_tracks()[0].to_dict() == expected
    diagnostics = candidate.opaque_source_identity_cache_diagnostics()
    assert diagnostics["operation_counts"]["cache_hit_count"] > 0
    assert diagnostics["operation_counts"]["cache_miss_count"] == 2
    _assert_conservation(reference)
    _assert_conservation(candidate)


def test_dynamic_record_payloads_remain_fresh_while_identity_cache_hits() -> None:
    reference, candidate = _adapters()
    scan = _radar_scan(
        ((1_000.0, 0.0, -100.0),),
        scan_index=0,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
    )
    reference.process_scan_batch(scan)
    candidate.process_scan_batch(scan)

    for adapter in (reference, candidate):
        record = adapter.tracks["global_track_001"]
        record.metadata["record_revision_probe"] = "updated"
        record.source_support["cooperative_eo"] += 2
        record.identity_likelihood["unknown"] += 0.25
        record.association_diagnostics["manual_gate_probe"] += 1
        record.covariance_limit_reasons["manual_probe"] += 1
        record.covariance_limit_operation_counts[
            "track_covariance_manual_probe_count"
        ] += 3

    before_hits = candidate.opaque_source_identity_cache_diagnostics()[
        "operation_counts"
    ]["cache_hit_count"]
    reference_track = reference.global_tracks()[0]
    candidate_track = candidate.global_tracks()[0]

    assert candidate_track.to_dict() == reference_track.to_dict()
    assert candidate_track.metadata["record_revision_probe"] == "updated"
    assert candidate_track.source_support["cooperative_eo"] == 2
    assert candidate_track.identity_likelihood["unknown"] > 0.0
    assert (
        candidate_track.metadata["association_diagnostics"][
            "manual_gate_probe"
        ]
        == 1
    )
    assert (
        candidate_track.metadata["covariance_limit_operation_counts"][
            "track_covariance_manual_probe_count"
        ]
        == 3
    )
    after_hits = candidate.opaque_source_identity_cache_diagnostics()[
        "operation_counts"
    ]["cache_hit_count"]
    assert after_hits == before_hits + 1
    _assert_conservation(candidate)


def test_node_epoch_and_explicit_reset_force_rebuild() -> None:
    reference, candidate = _adapters()
    scan = _radar_scan(
        ((1_000.0, 0.0, -100.0),),
        scan_index=0,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
    )
    reference.process_scan_batch(scan)
    candidate.process_scan_batch(scan)
    original = candidate.global_tracks()[0].metadata["source_key"]

    for adapter in (reference, candidate):
        adapter.publisher_epoch = "episode-opaque-source-002"
    epoch_reference = reference.global_tracks()[0]
    epoch_candidate = candidate.global_tracks()[0]
    assert epoch_candidate.to_dict() == epoch_reference.to_dict()
    assert epoch_candidate.metadata["source_key"] != original

    for adapter in (reference, candidate):
        adapter.publisher_node_id = "D1-OPAQUE-SOURCE-TEST-B"
    node_reference = reference.global_tracks()[0]
    node_candidate = candidate.global_tracks()[0]
    assert node_candidate.to_dict() == node_reference.to_dict()
    assert node_candidate.metadata["source_key"] != (
        epoch_candidate.metadata["source_key"]
    )

    before_reset = candidate.opaque_source_identity_cache_diagnostics()
    candidate.reset_opaque_source_identity_cache()
    after_reset = candidate.opaque_source_identity_cache_diagnostics()
    assert before_reset["cache_entry_count"] == 1
    assert after_reset["cache_entry_count"] == 0
    assert (
        after_reset["operation_counts"]["explicit_reset_count"]
        == before_reset["operation_counts"]["explicit_reset_count"] + 1
    )
    misses_before = after_reset["operation_counts"]["cache_miss_count"]
    assert candidate.global_tracks()[0].to_dict() == (
        reference.global_tracks()[0].to_dict()
    )
    assert (
        candidate.opaque_source_identity_cache_diagnostics()[
            "operation_counts"
        ]["cache_miss_count"]
        == misses_before + 1
    )
    diagnostics = candidate.opaque_source_identity_cache_diagnostics()
    assert diagnostics["operation_counts"]["generation_invalidation_count"] == 2
    _assert_conservation(candidate)


def test_cache_capacity_is_bounded_and_evictions_preserve_payloads() -> None:
    reference, candidate = _adapters(capacity=2)
    positions = (
        (1_000.0, -400.0, -100.0),
        (1_000.0, 0.0, -100.0),
        (1_000.0, 400.0, -100.0),
    )
    scan = _radar_scan(
        positions,
        scan_index=0,
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
    )
    reference_result = reference.process_scan_batch(scan)
    candidate_result = candidate.process_scan_batch(scan)
    assert _canonical_tracks(candidate_result.tracks) == _canonical_tracks(
        reference_result.tracks
    )
    assert _canonical_tracks(
        candidate.global_tracks()
    ) == _canonical_tracks(reference.global_tracks())

    diagnostics = candidate.opaque_source_identity_cache_diagnostics()
    assert diagnostics["cache_entry_count"] == 2
    assert diagnostics["operation_counts"]["peak_entry_count"] == 2
    assert diagnostics["operation_counts"]["cache_eviction_count"] > 0
    _assert_conservation(candidate)


def test_oosm_birth_and_track_removal_boundaries_remain_equivalent() -> None:
    reference, candidate = _adapters(capacity=8)
    scans = (
        _radar_scan(
            ((1_000.0, 0.0, -100.0),),
            scan_index=0,
            measurement_timestamp=0.0,
            arrival_timestamp=0.2,
        ),
        _radar_scan(
            ((1_008.0, 0.0, -100.0),),
            scan_index=2,
            measurement_timestamp=0.4,
            arrival_timestamp=0.6,
        ),
        _radar_scan(
            ((1_004.0, 0.0, -100.0),),
            scan_index=1,
            measurement_timestamp=0.2,
            arrival_timestamp=0.8,
        ),
        _radar_scan(
            (
                (1_012.0, 0.0, -100.0),
                (4_000.0, 1_000.0, -120.0),
            ),
            scan_index=3,
            measurement_timestamp=0.6,
            arrival_timestamp=0.9,
        ),
    )

    for scan in scans:
        reference_result = reference.process_scan_batch(scan)
        candidate_result = candidate.process_scan_batch(scan)
        assert candidate_result.summary.to_dict() == (
            reference_result.summary.to_dict()
        )
        assert _canonical_tracks(
            candidate_result.tracks
        ) == _canonical_tracks(reference_result.tracks)

    assert reference.pre_checkpoint_oosm_replay_count == (
        candidate.pre_checkpoint_oosm_replay_count
    )
    assert len(candidate.tracks) == len(reference.tracks) == 2
    removed_id = sorted(candidate.tracks)[0]
    del reference.tracks[removed_id]
    del candidate.tracks[removed_id]

    remaining_reference = reference.global_tracks()
    remaining_candidate = candidate.global_tracks()
    assert all(
        track.global_track_id != removed_id
        for track in remaining_candidate
    )
    assert _canonical_tracks(remaining_candidate) == _canonical_tracks(
        remaining_reference
    )
    _assert_conservation(candidate)
