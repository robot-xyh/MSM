from __future__ import annotations

from copy import deepcopy

from d6_evaluation_metrics import (
    EXECUTION_METRICS_MERGE_SCHEMA_VERSION,
    merge_replay_with_execution_metrics,
)


def test_execution_cross_view_overrides_replay_and_preserves_provenance() -> None:
    replay = {
        "metrics": {
            "episode_id": "episode-001",
            "cross_view_association_count": 0,
            "terminal_lock_count": 1,
            "online_truth_field_violation_count": None,
        },
        "metadata": {"source_path": "integrated_replay/metrics.json"},
    }
    execution = {
        "metrics": {
            "episode_id": "episode-001",
            "cross_view_association_count": 55,
            "terminal_lock_count": 3,
            "online_truth_field_violation_count": 0,
        },
        "metadata": {"source_path": "main_episode_bus_metrics.json"},
    }
    replay_before = deepcopy(replay)
    execution_before = deepcopy(execution)

    merged = merge_replay_with_execution_metrics(replay, execution)

    assert merged["schema_version"] == EXECUTION_METRICS_MERGE_SCHEMA_VERSION
    assert merged["execution_metrics_merged"] is True
    assert merged["metrics"]["cross_view_association_count"] == 55
    assert merged["metrics"]["terminal_lock_count"] == 3
    assert merged["metrics"]["online_truth_field_violation_count"] == 0
    provenance = merged["metadata"]["execution_metric_provenance"]
    assert provenance["cross_view_association_count"]["replay"]["value"] == 0
    assert provenance["cross_view_association_count"]["execution"]["value"] == 55
    assert (
        provenance["cross_view_association_count"]["selected_source"]
        == "main_episode_bus_execution"
    )
    assert replay == replay_before
    assert execution == execution_before


def test_missing_execution_keeps_replay_availability_without_fabricating_zero() -> None:
    replay = {
        "metrics": {
            "episode_id": "episode-002",
            "metric_availability": {
                "cross_view_association_count": {
                    "status": "unavailable",
                    "reason": "no cross-view event stream",
                }
            },
        }
    }

    merged = merge_replay_with_execution_metrics(replay, None)

    assert merged["execution_metrics_merged"] is False
    assert "cross_view_association_count" not in merged["metrics"]
    availability = merged["metrics"]["metric_availability"]
    assert availability["cross_view_association_count"]["status"] == "unavailable"
    provenance = merged["metadata"]["execution_metric_provenance"]
    assert provenance["cross_view_association_count"]["availability"] == "unavailable"
    assert provenance["cross_view_association_count"]["execution"]["value"] is None


def test_missing_execution_keeps_available_replay_value() -> None:
    replay = {
        "metrics": {
            "cross_view_association_count": 7,
            "metric_availability": {
                "cross_view_association_count": {
                    "status": "available",
                    "reason": "persisted replay event stream",
                }
            },
        }
    }

    merged = merge_replay_with_execution_metrics(replay, None)

    assert merged["execution_metrics_merged"] is False
    assert merged["metrics"]["cross_view_association_count"] == 7
    availability = merged["metrics"]["metric_availability"]
    assert availability["cross_view_association_count"] == {
        "status": "available",
        "source": "integrated_replay",
        "reason": "persisted replay event stream",
    }


def test_not_applicable_availability_is_preserved() -> None:
    replay = {
        "metrics": {
            "metric_availability": {
                "physical_intercept_count": {
                    "status": "not_applicable",
                    "reason": "ComputerVision episode has no physical control",
                }
            }
        }
    }

    merged = merge_replay_with_execution_metrics(replay, None)

    availability = merged["metrics"]["metric_availability"]
    assert availability["physical_intercept_count"] == {
        "status": "not_applicable",
        "source": "integrated_replay",
        "reason": "ComputerVision episode has no physical control",
    }
    provenance = merged["metadata"]["execution_metric_provenance"]
    assert provenance["physical_intercept_count"]["availability"] == "not_applicable"


def test_persisted_and_warmup_inclusive_frame_counts_are_distinct() -> None:
    replay = {
        "metrics": {"episode_id": "episode-003"},
        "metadata": {"clock": {"frame_count": 11}},
    }
    execution = {
        "metrics": {
            "cross_view_association_count": 55,
            "metadata": {"warmup_inclusive_frame_count": 12},
        }
    }

    merged = merge_replay_with_execution_metrics(replay, execution)

    metadata = merged["metadata"]
    assert metadata["persisted_frame_count"] == 11
    assert metadata["warmup_inclusive_frame_count"] == 12
    assert metadata["frame_count_availability"]["persisted_frame_count"] == {
        "status": "available",
        "source": "integrated_replay.metadata.clock.frame_count",
    }
    assert metadata["frame_count_availability"]["warmup_inclusive_frame_count"] == {
        "status": "available",
        "source": (
            "main_episode_bus_execution.metrics.metadata."
            "warmup_inclusive_frame_count"
        ),
    }
