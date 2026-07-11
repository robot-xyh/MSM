from __future__ import annotations

from dataclasses import fields

import numpy as np
import pytest

from d2_data_association import (
    CorrelationStatus,
    CrossNodeTrackRegistry,
    FusionAction,
    OfflineCrossNodeMetricsEvaluator,
    SourceTrackSummary,
)


def source_track(
    node: str,
    local_id: str,
    *,
    epoch: int = 0,
    measurement_timestamp: float = 0.0,
    arrival_timestamp: float | None = None,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    covariance_scale: float = 0.2,
    quality: float = 0.8,
    lineage: tuple[str, ...] | None = None,
    payload_id: str | None = None,
    correlation_status: CorrelationStatus = CorrelationStatus.UNKNOWN_CORRELATION,
    known_cross_covariance: np.ndarray | None = None,
    current_canonical_id: str | None = None,
    candidate_canonical_ids: tuple[str, ...] = (),
) -> SourceTrackSummary:
    arrival = (
        measurement_timestamp + 0.1
        if arrival_timestamp is None
        else arrival_timestamp
    )
    payload = payload_id or f"{node}:{local_id}:{epoch}:{measurement_timestamp}"
    lineage_ids = lineage or (f"raw:{payload}",)
    return SourceTrackSummary(
        source_node_id=node,
        local_track_id=local_id,
        local_epoch=epoch,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival,
        ned_state=np.array([*position, *velocity], dtype=float),
        ned_covariance=np.eye(6) * covariance_scale,
        quality=quality,
        lineage=lineage_ids,
        correlation_status=correlation_status,
        candidate_canonical_ids=candidate_canonical_ids,
        current_canonical_id=current_canonical_id,
        payload_id=payload,
        known_cross_covariance=known_cross_covariance,
    )


@pytest.mark.parametrize("source_count", [1, 2, 3, 8])
def test_one_canonical_binds_one_two_three_or_n_sources(source_count: int) -> None:
    registry = CrossNodeTrackRegistry()
    tracks = [
        source_track(
            f"node-{index}",
            "local-target",
            position=(0.02 * index, 0.0, 0.0),
        )
        for index in range(source_count)
    ]

    result = registry.process_batch(tracks, fusion_timestamp=0.1)

    assert list(result.canonical_bindings) == ["GT-000001"]
    assert len(result.canonical_bindings["GT-000001"]) == source_count
    assert len(result.created_canonical_ids) == 1


def test_asynchronous_tracks_are_propagated_to_common_fusion_epoch() -> None:
    registry = CrossNodeTrackRegistry()
    tracks = [
        source_track(
            "early-node",
            "T",
            measurement_timestamp=0.0,
            arrival_timestamp=2.0,
            position=(0.0, 0.0, 0.0),
            velocity=(10.0, 0.0, 0.0),
        ),
        source_track(
            "late-node",
            "T",
            measurement_timestamp=1.0,
            arrival_timestamp=2.0,
            position=(10.0, 0.0, 0.0),
            velocity=(10.0, 0.0, 0.0),
        ),
    ]

    result = registry.process_batch(tracks, fusion_timestamp=2.0)

    assert len(result.canonical_bindings) == 1
    assert len(result.matches) == 1
    assert result.matches[0].mahalanobis_squared == pytest.approx(0.0)
    assert result.canonical_snapshots[0].ned_state[0] == pytest.approx(20.0)


def test_crossing_tracks_keep_canonical_ids_using_full_ned_velocity_state() -> None:
    registry = CrossNodeTrackRegistry()
    initial = [
        source_track(
            "node-a",
            "eastbound",
            position=(-10.0, 0.0, 0.0),
            velocity=(10.0, 0.0, 0.0),
        ),
        source_track(
            "node-a",
            "westbound",
            position=(10.0, 0.0, 0.0),
            velocity=(-10.0, 0.0, 0.0),
        ),
        source_track(
            "node-b",
            "track-1",
            position=(-9.9, 0.0, 0.0),
            velocity=(10.0, 0.0, 0.0),
        ),
        source_track(
            "node-b",
            "track-2",
            position=(9.9, 0.0, 0.0),
            velocity=(-10.0, 0.0, 0.0),
        ),
    ]
    first = registry.process_batch(initial, fusion_timestamp=0.1)
    east_id = registry.source_bindings[initial[0].source_key]
    west_id = registry.source_bindings[initial[1].source_key]

    crossing = [
        source_track(
            "node-a",
            "eastbound",
            measurement_timestamp=1.0,
            arrival_timestamp=1.1,
            position=(0.0, 0.0, 0.0),
            velocity=(10.0, 0.0, 0.0),
        ),
        source_track(
            "node-a",
            "westbound",
            measurement_timestamp=1.0,
            arrival_timestamp=1.1,
            position=(0.0, 0.0, 0.0),
            velocity=(-10.0, 0.0, 0.0),
        ),
    ]
    second = registry.process_batch(crossing, fusion_timestamp=1.1)

    assert len(first.canonical_bindings) == 2
    assert not second.created_canonical_ids
    assert registry.source_bindings[crossing[0].source_key] == east_id
    assert registry.source_bindings[crossing[1].source_key] == west_id
    assert second.metrics["cross_node_id_switch_count"] == 0


def test_duplicate_payload_lineage_and_declared_duplicate_are_rejected() -> None:
    registry = CrossNodeTrackRegistry()
    original = source_track(
        "node-a",
        "T",
        payload_id="message-1",
        lineage=("observation-1",),
    )
    registry.process_batch([original], fusion_timestamp=0.1)

    repeated_payload = source_track(
        "node-a",
        "T",
        measurement_timestamp=0.5,
        arrival_timestamp=0.6,
        payload_id="message-1",
        lineage=("observation-2",),
    )
    repeated_lineage = source_track(
        "node-b",
        "T",
        measurement_timestamp=0.5,
        arrival_timestamp=0.6,
        payload_id="message-2",
        lineage=("observation-1",),
    )
    declared_duplicate = source_track(
        "node-c",
        "T",
        measurement_timestamp=0.5,
        arrival_timestamp=0.6,
        payload_id="message-3",
        correlation_status=CorrelationStatus.DUPLICATE_INFORMATION,
    )
    result = registry.process_batch(
        [repeated_payload, repeated_lineage, declared_duplicate],
        fusion_timestamp=0.6,
    )

    assert [item.reason for item in result.rejected_source_tracks] == [
        "duplicate_payload",
        "duplicate_lineage",
        "declared_duplicate_information",
    ]
    assert all(
        directive.action == FusionAction.REJECT_DUPLICATE_INFORMATION
        for directive in result.fusion_directives
    )
    assert result.metrics["duplicate_payload_rejection_count"] == 3
    assert len(result.canonical_bindings["GT-000001"]) == 1


def test_source_local_id_is_namespaced_and_source_hint_cannot_force_binding() -> None:
    registry = CrossNodeTrackRegistry()
    left = source_track(
        "node-a",
        "same-local-id",
        position=(0.0, 0.0, 0.0),
        current_canonical_id="GT-999999",
    )
    right = source_track(
        "node-b",
        "same-local-id",
        position=(100.0, 0.0, 0.0),
        current_canonical_id="GT-000001",
        candidate_canonical_ids=("GT-000001",),
    )

    result = registry.process_batch([left, right], fusion_timestamp=0.1)

    assert len(result.canonical_bindings) == 2
    assert registry.source_bindings[left.source_key] == "GT-000001"
    assert registry.source_bindings[right.source_key] == "GT-000002"


def test_new_local_epoch_preserves_canonical_id_and_binding_history() -> None:
    registry = CrossNodeTrackRegistry()
    old_tracklet = source_track("node-a", "T", epoch=0)
    first = registry.process_batch([old_tracklet], fusion_timestamp=0.1)
    new_tracklet = source_track(
        "node-a",
        "T",
        epoch=1,
        measurement_timestamp=1.0,
        arrival_timestamp=1.1,
    )
    second = registry.process_batch([new_tracklet], fusion_timestamp=1.1)

    assert first.created_canonical_ids == ("GT-000001",)
    assert not second.created_canonical_ids
    assert registry.source_bindings[new_tracklet.source_key] == "GT-000001"
    assert second.canonical_bindings["GT-000001"] == (
        old_tracklet.source_key,
        new_tracklet.source_key,
    )
    assert [event.event for event in registry.binding_history] == ["created", "bound"]


def test_correlation_policy_requests_exact_or_ci_but_never_computes_ci() -> None:
    unknown_registry = CrossNodeTrackRegistry()
    unknown = unknown_registry.process_batch(
        [source_track("node-a", "T"), source_track("node-b", "T")],
        fusion_timestamp=0.1,
    )
    assert [item.action for item in unknown.fusion_directives] == [
        FusionAction.NO_FUSION_SINGLE_SOURCE,
        FusionAction.REQUEST_COVARIANCE_INTERSECTION,
    ]
    assert unknown.canonical_snapshots[0].ned_state[0] == pytest.approx(0.0)

    exact_registry = CrossNodeTrackRegistry()
    exact = exact_registry.process_batch(
        [
            source_track("node-a", "T"),
            source_track(
                "node-b",
                "T",
                correlation_status=CorrelationStatus.EXACT_KNOWN_CORRELATION,
                known_cross_covariance=np.zeros((6, 6)),
            ),
        ],
        fusion_timestamp=0.1,
    )
    assert exact.fusion_directives[-1].action == (
        FusionAction.REQUEST_EXACT_CORRELATED_FUSION
    )
    assert "owned_by_D1" in exact.fusion_directives[-1].reason


def test_covariance_aware_gate_changes_track_to_track_acceptance() -> None:
    low_uncertainty = CrossNodeTrackRegistry()
    low_result = low_uncertainty.process_batch(
        [
            source_track("node-a", "T", covariance_scale=0.01),
            source_track(
                "node-b",
                "T",
                position=(5.0, 0.0, 0.0),
                covariance_scale=0.01,
            ),
        ],
        fusion_timestamp=0.1,
    )
    high_uncertainty = CrossNodeTrackRegistry()
    high_result = high_uncertainty.process_batch(
        [
            source_track("node-a", "T", covariance_scale=10.0),
            source_track(
                "node-b",
                "T",
                position=(5.0, 0.0, 0.0),
                covariance_scale=10.0,
            ),
        ],
        fusion_timestamp=0.1,
    )

    assert len(low_result.canonical_bindings) == 2
    assert len(high_result.canonical_bindings) == 1


def test_offline_metrics_report_precision_recall_duplicate_and_id_switch() -> None:
    registry = CrossNodeTrackRegistry()
    tracks = [
        source_track("node-a", "T", position=(0.0, 0.0, 0.0)),
        source_track("node-b", "T", position=(0.1, 0.0, 0.0)),
        source_track("node-c", "U", position=(100.0, 0.0, 0.0)),
        source_track("node-d", "U", position=(200.0, 0.0, 0.0)),
    ]
    first = registry.process_batch(tracks, fusion_timestamp=0.1)
    evaluator = OfflineCrossNodeMetricsEvaluator()
    evaluator.record_snapshot(
        first,
        {
            tracks[0].source_key: "truth-T",
            tracks[1].source_key: "truth-T",
            tracks[2].source_key: "truth-U",
            tracks[3].source_key: "truth-U",
        },
    )
    summary = evaluator.summary()

    assert summary["truth_metrics_available"] is True
    assert summary["association_precision"] == pytest.approx(1.0)
    assert summary["association_recall"] == pytest.approx(0.5)
    assert summary["canonical_duplicate_count"] == 1

    jumped = source_track(
        "node-a",
        "T",
        measurement_timestamp=1.0,
        arrival_timestamp=1.1,
        position=(1000.0, 0.0, 0.0),
    )
    second = registry.process_batch([jumped], fusion_timestamp=1.1)
    switch_evaluator = OfflineCrossNodeMetricsEvaluator()
    switch_evaluator.record_snapshot(first, {tracks[0].source_key: "truth-T"})
    switch_evaluator.record_snapshot(second, {jumped.source_key: "truth-T"})

    assert second.metrics["cross_node_id_switch_count"] == 1
    assert switch_evaluator.summary()["cross_node_id_switch_count"] == 1


def test_fusion_latency_summary_and_online_truth_isolation() -> None:
    registry = CrossNodeTrackRegistry()
    track = source_track(
        "node-a",
        "T",
        measurement_timestamp=1.0,
        arrival_timestamp=1.4,
    )
    result = registry.process_batch([track], fusion_timestamp=2.0)
    latency = result.metrics["fusion_latency_summary"]

    assert latency["count"] == 1
    assert latency["mean_seconds"] == pytest.approx(1.0)
    assert result.metrics["transport_latency_summary"][
        "mean_seconds"
    ] == pytest.approx(0.4)
    assert result.metrics["registry_queue_latency_summary"][
        "mean_seconds"
    ] == pytest.approx(0.6)
    assert result.metrics["truth_metrics_available"] is False
    assert "truth_id" not in {item.name for item in fields(SourceTrackSummary)}
    assert "truth" not in str(track.to_dict()).lower()
    with pytest.raises(TypeError):
        registry.process_batch(  # type: ignore[call-arg]
            [],
            fusion_timestamp=2.1,
            truth_by_source_track={},
        )
