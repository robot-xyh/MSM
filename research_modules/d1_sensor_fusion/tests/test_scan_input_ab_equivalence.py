from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from d1_sensor_fusion import (
    SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    SCAN_INPUT_REFERENCE_IMPLEMENTATION,
    ScanInputConfig,
    ScanInputOrganizer,
    SensorObservation,
    SensorScanFrame,
)


def _scan(
    scan_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    *,
    observation_count: int = 2,
    lineage_prefix: str | None = None,
    position_offset_m: float = 0.0,
    metadata_extra: dict[str, Any] | None = None,
) -> SensorScanFrame:
    prefix = lineage_prefix or scan_id
    observations = tuple(
        SensorObservation(
            observation_id=f"{scan_id}-obs-{index:03d}",
            sensor_id="RADAR-AB",
            modality="radar",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=np.array(
                [
                    1_000.0 + 10.0 * index + position_offset_m,
                    0.1,
                    -0.05,
                    3.0,
                ]
            ),
            covariance=np.diag([16.0, 0.01, 0.01, 4.0]),
            confidence=0.9,
            quality_flags=("ab-equivalence",),
            metadata={
                "scan_id": scan_id,
                "coverage_cell": "cell-ab",
                "source_lineage_key": (
                    "explicit",
                    "RADAR-AB",
                    prefix,
                    index,
                ),
                "source_frame_id": "radar_ab_frame",
                **(metadata_extra or {}),
            },
            source_node_id="RADAR-AB",
            target_node_id="D1-FUSION",
            sent_timestamp=measurement_timestamp,
            received_timestamp=arrival_timestamp,
            payload_kind="radar_scan",
        )
        for index in range(observation_count)
    )
    return SensorScanFrame(scan_id=scan_id, observations=observations)


def _claim_snapshot(organizer: ScanInputOrganizer) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            key,
            claim.lineage_digests,
            claim.source_lineage_digest,
            claim.content_digest,
            claim.frame_digest,
            claim.measurement_timestamp,
            claim.arrival_timestamp,
        )
        for key, claim in sorted(organizer._scan_claims.items())
    )


def _run_pair(
    config: ScanInputConfig,
    actions: tuple[tuple[str, Any], ...],
) -> tuple[ScanInputOrganizer, ScanInputOrganizer]:
    reference = ScanInputOrganizer(
        config,
        implementation=SCAN_INPUT_REFERENCE_IMPLEMENTATION,
    )
    candidate = ScanInputOrganizer(
        config,
        implementation=SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    )

    for action, value in actions:
        if action == "ingest":
            reference_result = reference.ingest(value)
            candidate_result = candidate.ingest(value)
        elif action == "advance":
            reference_result = reference.advance_arrival_time(float(value))
            candidate_result = candidate.advance_arrival_time(float(value))
        elif action == "close":
            reference_result = reference.close()
            candidate_result = candidate.close()
        else:
            raise AssertionError(f"unsupported test action: {action}")

        assert reference_result.to_dict() == candidate_result.to_dict()
        assert reference_result.audit.to_dict() == candidate_result.audit.to_dict()
        assert _claim_snapshot(reference) == _claim_snapshot(candidate)

    return reference, candidate


def test_reference_and_candidate_match_mixed_lifecycle_and_digest_contract() -> None:
    base = _scan("scan-base", 0.0, 0.1)
    future = _scan("scan-future", 2.0, 2.1)
    reordered = _scan(
        "scan-reordered",
        1.5,
        2.2,
        lineage_prefix="payload-reordered",
    )
    duplicate = SensorScanFrame(
        scan_id=reordered.scan_id,
        observations=tuple(reversed(reordered.observations)),
    )
    replay = _scan(
        "scan-relay-replay",
        1.5,
        2.3,
        lineage_prefix="payload-reordered",
    )
    conflict = _scan(
        "scan-reordered",
        1.5,
        2.4,
        lineage_prefix="payload-reordered",
        position_offset_m=50.0,
    )
    advance = _scan("scan-advance", 4.0, 4.1)
    too_late = _scan("scan-too-late", 1.0, 4.2)

    reference, candidate = _run_pair(
        ScanInputConfig(max_lateness_s=1.0, max_buffer_residence_s=20.0),
        (
            ("ingest", base),
            ("ingest", future),
            ("ingest", reordered),
            ("ingest", duplicate),
            ("ingest", replay),
            ("ingest", conflict),
            ("ingest", advance),
            ("ingest", too_late),
            ("close", None),
        ),
    )

    audit = candidate.audit_summary()
    assert audit.duplicate_scan_count == 1
    assert audit.replay_scan_count == 1
    assert audit.timestamp_conflict_scan_count == 1
    assert audit.too_late_scan_count == 1
    assert audit.reordered_scan_count == 1
    assert audit.released_scan_count == 4
    assert reference.audit_summary().to_dict() == audit.to_dict()

    reference_diagnostics = reference.performance_diagnostics()
    candidate_diagnostics = candidate.performance_diagnostics()
    assert reference_diagnostics["implementation"] == "reference_v1"
    assert candidate_diagnostics["implementation"] == "candidate_v2"
    assert reference_diagnostics["source_lineage_reconstruction_count"] > 0
    assert candidate_diagnostics["source_lineage_reconstruction_count"] == 0
    assert candidate_diagnostics["cached_source_lineage_reuse_count"] > 0
    assert (
        reference_diagnostics["lineage_sort_key_construction_count"]
        == 2 * candidate_diagnostics["lineage_sort_key_construction_count"]
    )


def test_tampered_lineage_cache_is_rebuilt_with_strict_ab_equivalence() -> None:
    frame = _scan(
        "tampered-lineage-cache",
        0.0,
        0.1,
        observation_count=3,
    )
    expected_lineage_keys = frame.source_lineage_keys
    polluted_lineage_keys = tuple(
        ("polluted-cache", index) for index in range(len(frame.observations))
    )
    object.__setattr__(frame, "_source_lineage_keys", polluted_lineage_keys)

    reference = ScanInputOrganizer(
        implementation=SCAN_INPUT_REFERENCE_IMPLEMENTATION
    )
    candidate = ScanInputOrganizer(
        implementation=SCAN_INPUT_CANDIDATE_IMPLEMENTATION
    )

    reference_ingest = reference.ingest(frame)
    candidate_ingest = candidate.ingest(frame)
    assert reference_ingest.to_dict() == candidate_ingest.to_dict()
    assert _claim_snapshot(reference) == _claim_snapshot(candidate)

    reference_tail = reference.close()
    candidate_tail = candidate.close()
    assert reference_tail.to_dict() == candidate_tail.to_dict()
    assert _claim_snapshot(reference) == _claim_snapshot(candidate)

    for rebuilt in (
        reference_tail.released_scans[0],
        candidate_tail.released_scans[0],
    ):
        assert rebuilt is not frame
        assert rebuilt.source_lineage_keys == expected_lineage_keys
        assert rebuilt.source_lineage_keys != polluted_lineage_keys

    reference_diagnostics = reference.performance_diagnostics()
    candidate_diagnostics = candidate.performance_diagnostics()
    assert reference_diagnostics["validated_frame_reuse_count"] == 0
    assert candidate_diagnostics["validated_frame_reuse_count"] == 0
    assert reference_diagnostics["mutated_frame_rebuild_count"] == 1
    assert candidate_diagnostics["mutated_frame_rebuild_count"] == 1
    assert candidate_diagnostics["cached_source_lineage_reuse_count"] == 3
    assert candidate_diagnostics["source_lineage_reconstruction_count"] == 0


def test_reference_and_candidate_match_buffer_and_claim_capacity_overflow() -> None:
    buffer_reference, buffer_candidate = _run_pair(
        ScanInputConfig(
            max_lateness_s=100.0,
            max_buffer_residence_s=100.0,
            max_buffered_scans=2,
            max_buffered_observations=20,
        ),
        (
            ("ingest", _scan("buffer-0", 0.0, 0.1)),
            ("ingest", _scan("buffer-1", 1.0, 1.1)),
            ("ingest", _scan("buffer-overflow", 2.0, 2.1)),
            ("close", None),
        ),
    )
    assert buffer_candidate.audit_summary().buffer_overflow_scan_count == 1
    assert (
        buffer_reference.audit_summary().to_dict()
        == buffer_candidate.audit_summary().to_dict()
    )

    claim_reference, claim_candidate = _run_pair(
        ScanInputConfig(
            max_lateness_s=100.0,
            max_buffer_residence_s=100.0,
            max_claimed_scans=1,
            max_claimed_observation_lineages=10,
        ),
        (
            ("ingest", _scan("claim-0", 0.0, 0.1)),
            ("ingest", _scan("claim-overflow", 1.0, 1.1)),
            ("close", None),
        ),
    )
    assert claim_candidate.audit_summary().capacity_overflow_scan_count == 1
    assert (
        claim_reference.audit_summary().to_dict()
        == claim_candidate.audit_summary().to_dict()
    )


def test_reference_and_candidate_match_expiry_event_intermediate_counts() -> None:
    reference, candidate = _run_pair(
        ScanInputConfig(
            max_lateness_s=100.0,
            max_buffer_residence_s=1.0,
        ),
        (
            ("ingest", _scan("expiry-0", 0.0, 0.1, observation_count=2)),
            ("ingest", _scan("expiry-1", 0.1, 0.2, observation_count=3)),
            ("advance", 1.3),
            ("close", None),
        ),
    )

    audit = candidate.audit_summary()
    assert audit.buffer_expired_scan_count == 2
    assert audit.rejected_observation_count == 5
    assert reference.audit_summary().to_dict() == audit.to_dict()


@pytest.mark.parametrize(
    "non_finite_value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_reference_and_candidate_fail_closed_identically_on_non_finite_array(
    non_finite_value: float,
) -> None:
    frame = _scan(
        "non-finite",
        0.0,
        0.1,
        metadata_extra={
            "numeric_payload": np.array([1.0, non_finite_value, 3.0]),
        },
    )
    reference = ScanInputOrganizer(
        implementation=SCAN_INPUT_REFERENCE_IMPLEMENTATION
    )
    candidate = ScanInputOrganizer(
        implementation=SCAN_INPUT_CANDIDATE_IMPLEMENTATION
    )

    exceptions = []
    for organizer in (reference, candidate):
        with pytest.raises(ValueError) as captured:
            organizer.ingest(frame)
        exceptions.append(captured.value)

    assert type(exceptions[0]) is type(exceptions[1])
    assert str(exceptions[0]) == str(exceptions[1])
    assert str(exceptions[0]) == "scan digest input contains non-finite float"
    assert _claim_snapshot(reference) == _claim_snapshot(candidate) == ()
    assert reference.audit_summary().to_dict() == candidate.audit_summary().to_dict()
    assert reference.audit_summary().current_buffered_scan_count == 0
    assert reference.audit_summary().released_scan_count == 0


def test_default_and_explicit_execution_selection_are_manifest_visible() -> None:
    default = ScanInputOrganizer()
    reference = ScanInputOrganizer(
        implementation=SCAN_INPUT_REFERENCE_IMPLEMENTATION
    )

    assert default.execution_config() == {
        "schema_version": "d1.scan_input.execution_config.v1",
        "implementation": "candidate_v2",
        "candidate_is_default": True,
        "reference_implementation": "reference_v1",
        "candidate_implementation": "candidate_v2",
        "event_time_config": ScanInputConfig().to_dict(),
    }
    assert reference.execution_config()["implementation"] == "reference_v1"
    assert reference.performance_diagnostics()["implementation"] == "reference_v1"

    with pytest.raises(ValueError, match="implementation must be one of"):
        ScanInputOrganizer(implementation="unknown")
