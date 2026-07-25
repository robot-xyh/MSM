from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from enum import Enum
from typing import Any, Mapping

import numpy as np
import pytest

from d1_sensor_fusion import Scalable3DFusionAdapter
from d1_sensor_fusion.association_sparse_prefilter_performance import (
    _radar_scan,
)
from d1_sensor_fusion.fusion import (
    REPLAY_PREFIX_SUMMARY_CANDIDATE_IMPLEMENTATION_ID,
    REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
    REPLAY_PREFIX_SUMMARY_DEFAULT_SELECTOR,
    REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION,
    REPLAY_PREFIX_SUMMARY_REFERENCE_IMPLEMENTATION_ID,
    REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
    REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION,
    _ReplayPrefixSummary,
)


def _canonical(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _canonical(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _adapter(selector: str) -> Scalable3DFusionAdapter:
    return Scalable3DFusionAdapter(
        association_gate=40.0,
        buffer_horizon=6.0,
        replay_prefix_summary=selector,
    )


def _scan(
    target_count: int,
    measurement_timestamp: float,
    arrival_timestamp: float,
    scan_id: str,
    *,
    gate_first_observation: bool = False,
) -> tuple:
    observations = list(
        _radar_scan(target_count, measurement_timestamp, scan_id)
    )
    for observation in observations:
        observation.arrival_timestamp = float(arrival_timestamp)
    if gate_first_observation:
        observations[0].measurement = observations[0].measurement.copy()
        observations[0].measurement[0] += 0.5
        observations[0].metadata["filter_innovation_gate_chi2"] = 1.0e-12
    return tuple(observations)


def _record_snapshot(adapter: Scalable3DFusionAdapter) -> Any:
    rows = []
    for track_id, record in sorted(adapter.tracks.items()):
        rows.append(
            {
                "track_id": track_id,
                "initial_state": {
                    "state": record.initial_state.state,
                    "covariance": record.initial_state.covariance,
                    "timestamp": record.initial_state.timestamp,
                },
                "current_state": {
                    "state": record.current_state.state,
                    "covariance": record.current_state.covariance,
                    "timestamp": record.current_state.timestamp,
                },
                "initial_observation_id": record.initial_observation_id,
                "observation_ids": [
                    item.observation_id for item in record.observations
                ],
                "archived_observation_ids": [
                    item.observation_id for item in record.archived_observations
                ],
                "recent_nis": tuple(record.recent_nis),
                "metadata": record.metadata,
                "checkpoint_active": record.checkpoint_active,
                "checkpoint_count": record.checkpoint_count,
                "replay_checkpoints": [
                    {
                        "observation_id": item.observation_id,
                        "sort_key": item.sort_key,
                        "posterior_state": item.posterior.state,
                        "posterior_covariance": item.posterior.covariance,
                        "posterior_timestamp": item.posterior.timestamp,
                        "nis": item.nis,
                        "gated": item.gated,
                    }
                    for item in record.replay_checkpoints
                ],
            }
        )
    return _canonical(rows)


def _operation_snapshot(adapter: Scalable3DFusionAdapter) -> Any:
    return _canonical(
        {
            "fusion": adapter.fusion_performance_diagnostics().to_dict(),
            "numerical_jacobian": dict(adapter._numerical_jacobian_operations),
            "covariance_psd": dict(adapter._covariance_psd_check_operations),
            "cv_motion_model": dict(adapter._cv_motion_model_cache_operations),
            "association_modality": adapter.association_sparse_prefilter_diagnostics()[
                "modality_counts"
            ],
        }
    )


def _assert_public_and_internal_equivalence(
    reference: Scalable3DFusionAdapter,
    candidate: Scalable3DFusionAdapter,
) -> None:
    assert _canonical(
        [item.to_dict() for item in reference.global_tracks()]
    ) == _canonical([item.to_dict() for item in candidate.global_tracks()])
    assert _canonical(
        [item.to_dict() for item in reference.consistency_evidence_records()]
    ) == _canonical(
        [item.to_dict() for item in candidate.consistency_evidence_records()]
    )
    assert _record_snapshot(reference) == _record_snapshot(candidate)
    assert _operation_snapshot(reference) == _operation_snapshot(candidate)


def test_selector_is_explicit_default_off_and_schema_is_independent() -> None:
    reference = Scalable3DFusionAdapter()
    config = reference.replay_prefix_summary_execution_config()
    diagnostics = reference.replay_prefix_summary_diagnostics()

    assert REPLAY_PREFIX_SUMMARY_DEFAULT_SELECTOR == (
        REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR
    )
    assert config["candidate_enabled"] is False
    assert config["candidate_default_enabled"] is False
    assert config["selected_implementation_id"] == (
        REPLAY_PREFIX_SUMMARY_REFERENCE_IMPLEMENTATION_ID
    )
    assert diagnostics["schema_version"] == (
        REPLAY_PREFIX_SUMMARY_DIAGNOSTICS_SCHEMA_VERSION
    )
    assert diagnostics["operation_counts"] == {}
    assert "association_sparse_prefilter" not in diagnostics["schema_version"]

    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    candidate_config = candidate.replay_prefix_summary_execution_config()
    assert candidate_config["candidate_enabled"] is True
    assert candidate_config["selected_implementation_id"] == (
        REPLAY_PREFIX_SUMMARY_CANDIDATE_IMPLEMENTATION_ID
    )
    assert candidate_config["summary_schema_version"] == (
        REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION
    )

    with pytest.raises(TypeError, match="string selector"):
        Scalable3DFusionAdapter(replay_prefix_summary=True)
    with pytest.raises(ValueError, match="unsupported replay_prefix_summary"):
        Scalable3DFusionAdapter(replay_prefix_summary="unknown_v1")


def test_summary_candidate_preserves_late_gate_fixed_lag_and_public_outputs() -> None:
    reference = _adapter(REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR)
    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    scans = (
        _scan(2, 0.0, 0.1, "origin"),
        _scan(2, 1.0, 1.1, "nominal"),
        _scan(
            2,
            2.0,
            2.1,
            "gate",
            gate_first_observation=True,
        ),
        _scan(2, 0.5, 2.3, "late-in-window"),
        _scan(2, 7.0, 7.1, "fixed-lag-current"),
        _scan(2, 0.2, 7.3, "pre-checkpoint-late"),
    )

    reference_summaries = []
    candidate_summaries = []
    for scan in scans:
        reference_result = reference.process_scan_batch(scan)
        candidate_result = candidate.process_scan_batch(scan)
        reference_summaries.append(_canonical(reference_result.summary.to_dict()))
        candidate_summaries.append(_canonical(candidate_result.summary.to_dict()))
        assert _canonical(
            [item.to_dict() for item in reference_result.tracks]
        ) == _canonical([item.to_dict() for item in candidate_result.tracks])

    assert candidate_summaries == reference_summaries
    _assert_public_and_internal_equivalence(reference, candidate)
    assert reference.pre_checkpoint_oosm_replay_count == 2
    assert candidate.pre_checkpoint_oosm_replay_count == 2
    assert any(
        item.metadata.get(
            "latest_replay_innovation_gate_rejection_count",
            0,
        )
        > 0
        for item in candidate.tracks.values()
    )
    diagnostics = candidate.replay_prefix_summary_diagnostics()
    assert diagnostics["operation_counts"]["summary_hit_count"] > 0
    assert (
        diagnostics["operation_counts"][
            "lazy_consistency_refresh_logical_record_count"
        ]
        > 0
    )
    assert diagnostics["conservation"]["attempt_partition"] is True
    assert diagnostics["pending_consistency_ledger_count"] == 0


def test_schema_mismatch_falls_back_then_rebuilds_without_semantic_change() -> None:
    reference = _adapter(REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR)
    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    for scan in (
        _scan(1, 0.0, 0.1, "schema-origin"),
        _scan(1, 1.0, 1.1, "schema-update"),
    ):
        reference.process_scan_batch(scan)
        candidate.process_scan_batch(scan)

    candidate_record = next(iter(candidate.tracks.values()))
    summary = candidate_record.replay_prefix_summary
    assert summary is not None
    candidate_record.replay_prefix_summary = replace(
        summary,
        schema_version="d1.fixed_lag_replay_prefix_summary.v999",
    )

    reference_record = next(iter(reference.tracks.values()))
    reference_replay = reference._capture_replay_record(
        reference_record,
        reference.current_time,
    )
    candidate_replay = candidate._capture_replay_record(
        candidate_record,
        candidate.current_time,
    )
    np.testing.assert_array_equal(
        candidate_replay[0].state,
        reference_replay[0].state,
    )
    np.testing.assert_array_equal(
        candidate_replay[0].covariance,
        reference_replay[0].covariance,
    )
    assert candidate_replay[1:] == reference_replay[1:]
    assert candidate_record.replay_prefix_summary is not None
    assert candidate_record.replay_prefix_summary.schema_version == (
        REPLAY_PREFIX_SUMMARY_SCHEMA_VERSION
    )
    _assert_public_and_internal_equivalence(reference, candidate)
    assert (
        candidate.replay_prefix_summary_diagnostics()["fallback_reasons"][
            "summary_schema_version_mismatch"
        ]
        == 1
    )


def test_partial_prefix_and_changed_prefix_use_reference_fallback() -> None:
    reference = _adapter(REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR)
    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    for scan in (
        _scan(1, 0.0, 0.1, "partial-origin"),
        _scan(1, 1.0, 1.1, "partial-one"),
        _scan(1, 2.0, 2.1, "partial-two"),
        _scan(1, 3.0, 3.1, "partial-three"),
    ):
        reference.process_scan_batch(scan)
        candidate.process_scan_batch(scan)

    reference_record = next(iter(reference.tracks.values()))
    candidate_record = next(iter(candidate.tracks.values()))
    reference_partial = reference._capture_replay_record(reference_record, 1.5)
    candidate_partial = candidate._capture_replay_record(candidate_record, 1.5)
    np.testing.assert_array_equal(
        candidate_partial[0].state,
        reference_partial[0].state,
    )
    np.testing.assert_array_equal(
        candidate_partial[0].covariance,
        reference_partial[0].covariance,
    )
    assert candidate_partial[1:] == reference_partial[1:]

    changed = _scan(1, 0.75, 3.3, "changed-prefix")
    reference.process_scan_batch(changed)
    candidate.process_scan_batch(changed)
    _assert_public_and_internal_equivalence(reference, candidate)
    fallback_reasons = candidate.replay_prefix_summary_diagnostics()[
        "fallback_reasons"
    ]
    assert fallback_reasons["incomplete_checkpoint_prefix"] >= 1
    assert fallback_reasons["no_checkpoint_prefix"] >= 1


def test_middle_checkpoint_order_change_invalidates_revision_and_fails_closed() -> None:
    reference = _adapter(REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR)
    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    for scan in (
        _scan(1, 0.0, 0.1, "middle-origin"),
        _scan(1, 1.0, 1.1, "middle-one"),
        _scan(1, 2.0, 2.1, "middle-two"),
        _scan(1, 3.0, 3.1, "middle-three"),
        _scan(1, 4.0, 4.1, "middle-four"),
    ):
        reference.process_scan_batch(scan)
        candidate.process_scan_batch(scan)

    candidate_record = next(iter(candidate.tracks.values()))
    assert len(candidate_record.replay_checkpoints) == 4
    assert candidate_record.replay_prefix_summary is not None
    revision_before = candidate_record.replay_checkpoint_revision
    old_middle_id = candidate_record.replay_checkpoints[1].observation_id

    late_scan = _scan(1, 1.5, 4.3, "middle-order-change")
    late_observation_id = late_scan[0].observation_id
    reference.process_scan_batch(late_scan)
    candidate.process_scan_batch(late_scan)

    assert candidate_record.replay_checkpoint_revision >= revision_before + 2
    checkpoint_ids = [
        item.observation_id for item in candidate_record.replay_checkpoints
    ]
    assert checkpoint_ids.index(late_observation_id) < checkpoint_ids.index(
        old_middle_id
    )
    assert candidate_record.replay_prefix_summary is not None
    assert (
        candidate_record.replay_prefix_summary.checkpoint_revision
        == candidate_record.replay_checkpoint_revision
    )
    assert (
        candidate_record.replay_prefix_summary.checkpoint_observation_ids
        == tuple(checkpoint_ids)
    )
    assert (
        candidate.replay_prefix_summary_diagnostics()["fallback_reasons"][
            "summary_unavailable"
        ]
        >= 1
    )
    _assert_public_and_internal_equivalence(reference, candidate)


def test_no_checkpoint_and_disabled_consistency_refresh_fail_closed() -> None:
    reference = _adapter(REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR)
    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    origin = _scan(1, 0.0, 0.1, "no-checkpoint")
    reference.process_scan_batch(origin)
    candidate.process_scan_batch(origin)
    reference_record = next(iter(reference.tracks.values()))
    candidate_record = next(iter(candidate.tracks.values()))
    reference._capture_replay_record(reference_record, reference.current_time)
    candidate._capture_replay_record(candidate_record, candidate.current_time)
    _assert_public_and_internal_equivalence(reference, candidate)
    assert (
        candidate.replay_prefix_summary_diagnostics()["fallback_reasons"][
            "no_checkpoint_prefix"
        ]
        == 1
    )

    fallback = Scalable3DFusionAdapter(
        replay_prefix_summary=REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR,
        cached_consistency_prefix_refresh=False,
    )
    baseline = Scalable3DFusionAdapter(
        replay_prefix_summary=REPLAY_PREFIX_SUMMARY_REFERENCE_SELECTOR,
        cached_consistency_prefix_refresh=False,
    )
    for scan in (
        _scan(1, 0.0, 0.1, "refresh-origin"),
        _scan(1, 1.0, 1.1, "refresh-update"),
        _scan(1, 2.0, 2.1, "refresh-next"),
    ):
        baseline.process_scan_batch(scan)
        fallback.process_scan_batch(scan)
    _assert_public_and_internal_equivalence(baseline, fallback)
    assert (
        fallback.replay_prefix_summary_diagnostics()["fallback_reasons"][
            "cached_consistency_refresh_disabled"
        ]
        >= 1
    )


def test_summary_payload_is_frozen_and_detached_from_checkpoint_lists() -> None:
    candidate = _adapter(REPLAY_PREFIX_SUMMARY_CANDIDATE_SELECTOR)
    for scan in (
        _scan(1, 0.0, 0.1, "immutable-origin"),
        _scan(1, 1.0, 1.1, "immutable-update"),
    ):
        candidate.process_scan_batch(scan)
    record = next(iter(candidate.tracks.values()))
    summary = record.replay_prefix_summary
    assert isinstance(summary, _ReplayPrefixSummary)
    original_ids = summary.checkpoint_observation_ids

    with pytest.raises(FrozenInstanceError):
        summary.schema_version = "mutated"  # type: ignore[misc]
    record.replay_checkpoints.clear()
    assert summary.checkpoint_observation_ids == original_ids
    assert isinstance(summary.nises, tuple)
    assert isinstance(summary.gated_observation_ids, tuple)
    assert isinstance(summary.consistency_observation_ids, tuple)
