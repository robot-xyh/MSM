from __future__ import annotations

from copy import deepcopy
import csv
import hashlib

from d6_evaluation_metrics import (
    D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS,
    D7_ACTUAL_EXECUTION_METADATA_SEMANTICS,
    D7_ACTUAL_EXECUTION_METADATA_SOURCES,
    D7_ACTUAL_EXECUTION_METRIC_SOURCES,
    D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
    D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    EXECUTION_METRICS_MERGE_SCHEMA_VERSION,
    merge_replay_with_execution_metrics,
)


def test_execution_cross_view_overrides_replay_and_preserves_provenance(
    tmp_path,
) -> None:
    replay = {
        "metrics": {
            "episode_id": "episode-001",
            "cross_view_association_count": 0,
            "terminal_lock_count": 1,
            "online_truth_field_violation_count": None,
        },
        "metadata": {
            "source_path": "integrated_replay/metrics.json",
            "plan_ids": ["replay-plan"],
            "plan_versions": [999],
            "owner_node_ids": ["replay-owner"],
        },
    }
    execution = _actual_execution(
        tmp_path,
        {
            "episode_id": "episode-001",
            "cross_view_association_count": 55,
            "terminal_lock_count": 3,
            "online_truth_field_violation_count": 0,
        }
    )
    replay_before = deepcopy(replay)
    execution_before = deepcopy(execution)

    merged = merge_replay_with_execution_metrics(replay, execution)

    assert merged["schema_version"] == EXECUTION_METRICS_MERGE_SCHEMA_VERSION
    assert merged["execution_metrics_merged"] is True
    assert merged["metrics"]["cross_view_association_count"] == 55
    assert merged["metrics"]["terminal_lock_count"] == 3
    assert merged["metrics"]["online_truth_field_violation_count"] == 0
    assert merged["metrics"]["metadata"]["plan_ids"] == ["actual-plan"]
    assert merged["metrics"]["metadata"]["plan_versions"] == [7]
    assert merged["metrics"]["metadata"]["owner_node_ids"] == ["d3_central"]
    assert merged["metrics"]["metadata"]["metadata_availability"]["plan_ids"][
        "source_artifact"
    ] == "control_commands"
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


def test_missing_execution_keeps_available_replay_value_audit_only() -> None:
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
    assert "cross_view_association_count" not in merged["metrics"]
    availability = merged["metrics"]["metric_availability"]
    assert availability["cross_view_association_count"]["status"] == "unavailable"
    assert availability["cross_view_association_count"]["source"] is None
    assert "d7_actual_execution_payload_missing" in availability[
        "cross_view_association_count"
    ]["reason"]
    provenance = merged["metadata"]["execution_metric_provenance"]
    assert provenance["cross_view_association_count"]["replay"]["value"] == 7
    assert provenance["cross_view_association_count"]["selected_source"] is None


def test_missing_execution_does_not_promote_replay_plan_metadata() -> None:
    replay = {
        "metrics": {
            "metadata": {
                "plan_ids": ["replay-plan"],
                "plan_versions": [5],
                "owner_node_ids": ["replay-owner"],
            }
        }
    }

    merged = merge_replay_with_execution_metrics(replay, None)

    metadata = merged["metrics"]["metadata"]
    assert "plan_ids" not in metadata
    assert "plan_versions" not in metadata
    assert "owner_node_ids" not in metadata


def test_replay_not_applicable_does_not_replace_actual_execution_evidence() -> None:
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
    assert availability["physical_intercept_count"]["status"] == "unavailable"
    assert availability["physical_intercept_count"]["source"] is None
    provenance = merged["metadata"]["execution_metric_provenance"]
    assert provenance["physical_intercept_count"]["availability"] == "unavailable"
    assert provenance["physical_intercept_count"]["replay"]["availability"] == (
        "not_applicable"
    )


def test_persisted_and_warmup_inclusive_frame_counts_are_distinct(tmp_path) -> None:
    replay = {
        "metrics": {"episode_id": "episode-003"},
        "metadata": {"clock": {"frame_count": 11}},
    }
    execution = _actual_execution(
        tmp_path,
        {
            "cross_view_association_count": 55,
            "metadata": {"warmup_inclusive_frame_count": 12},
        }
    )

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


def test_raw_integrated_replay_is_rejected_as_execution_authority() -> None:
    replay = {
        "metrics": {
            "mode_switched_count": 17,
            "loop_latency_ms": 0.0,
        }
    }
    raw_pre_control = {
        "episode_id": "episode-001-d7-execution",
        "seed": 1,
        "mode_switched_count": 17,
        "control_allowed_count": 0,
        "loop_latency_ms": 0.0,
        "metadata": {"offline_only": True},
    }

    merged = merge_replay_with_execution_metrics(replay, raw_pre_control)

    assert merged["execution_metrics_merged"] is False
    assert "mode_switched_count" not in merged["metrics"]
    assert "loop_latency_ms" not in merged["metrics"]
    validation = merged["metadata"]["execution_evidence_validation"]
    assert validation["status"] == "unavailable"
    assert "d7_actual_execution_schema_missing" in validation["validation_reasons"]
    assert merged["metadata"]["replay_execution_metrics_audit_only"] is True


def test_actual_execution_rejects_mode_switch_without_effective_control(
    tmp_path,
) -> None:
    execution = _actual_execution(
        tmp_path,
        {
            "control_allowed_count": 0,
            "mode_switched_count": 13,
        }
    )

    merged = merge_replay_with_execution_metrics({}, execution)

    assert merged["execution_metrics_merged"] is False
    validation = merged["metadata"]["execution_evidence_validation"]
    assert "d7_actual_execution_mode_switch_exceeds_control_allowed" in validation[
        "validation_reasons"
    ]


def _actual_execution(tmp_path, overrides: dict | None = None) -> dict:
    metrics = {
        "contract_evaluated_count": 10,
        "contract_allowed_count": 8,
        "control_evaluated_count": 10,
        "control_allowed_count": 6,
        "terminal_switch_allowed_count": 6,
        "mode_switched_count": 4,
        "physical_intercept_count": 2,
        "pair_physical_success_count": 2,
        "target_intercept_success_count": 2,
        "performance_budget_violation_count": 3,
        "performance_sample_count": 10,
        "loop_latency_ms": 42.0,
        "active_degradation_count": 1,
        "secondary_reassignment_count": 1,
        "d4_reassign_pending_count": 1,
        "terminal_lock_count": 2,
        "visual_png_switch_count": 1,
        "visual_png_control_allowed_sample_count": 2,
        "terminal_contract_reject_count": 3,
        "truth_identity_online_use_count": 0,
        "truth_state_online_use_count": 0,
        "target_state_freshness": {
            "sample_count": 10,
            "mean_age_s": 0.1,
            "p95_age_s": 0.1,
            "max_age_s": 0.1,
            "stale_count": 0,
            "stale_rate": 0.0,
            "source_distribution": {"d2_estimated_global_track": 10},
        },
    }
    metrics.update(overrides or {})
    required = (
        "contract_evaluated_count",
        "contract_allowed_count",
        "control_evaluated_count",
        "control_allowed_count",
        "terminal_switch_allowed_count",
        "mode_switched_count",
        "physical_intercept_count",
        "pair_physical_success_count",
        "target_intercept_success_count",
        "performance_budget_violation_count",
        "performance_sample_count",
        "loop_latency_ms",
        "active_degradation_count",
        "secondary_reassignment_count",
        "d4_reassign_pending_count",
        "terminal_lock_count",
        "visual_png_switch_count",
        "visual_png_control_allowed_sample_count",
        "terminal_contract_reject_count",
        "truth_identity_online_use_count",
        "truth_state_online_use_count",
    )
    metrics["metric_availability"] = {
        name: {
            "status": "available",
            "source_artifact": D7_ACTUAL_EXECUTION_METRIC_SOURCES[name],
            **(
                {"semantics": D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS[name]}
                if name in D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS
                else {}
            ),
        }
        for name in required
    }
    metrics["metric_availability"]["target_state_freshness"] = {
        "status": "available",
        "source": "control_commands",
        "source_artifact": "control_commands",
        "reason": "validated persisted actual-execution source",
        "semantics": D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    }
    artifacts = {}
    for name in (
        "control_commands",
        "intercept_summary",
        "main_episode_bus_metrics",
    ):
        path = tmp_path / f"{name}.fixture"
        if name == "control_commands":
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "plan_id",
                        "plan_version",
                        "d4_target_node_id",
                        "effective_control_authorized",
                        "terminal_switch_allowed",
                        "timestamp_s",
                        "target_measurement_timestamp_s",
                        "target_arrival_timestamp_s",
                        "target_measurement_age_s",
                        "target_state_stale",
                        "target_state_source",
                    ),
                )
                writer.writeheader()
                for index, allowed in enumerate((True,) * 6 + (False,) * 4):
                    writer.writerow(
                        {
                            "plan_id": "actual-plan",
                            "plan_version": "7",
                            "d4_target_node_id": "d3_central",
                            "effective_control_authorized": str(allowed),
                            "terminal_switch_allowed": str(allowed),
                            "timestamp_s": str(index + 0.1),
                            "target_measurement_timestamp_s": str(index),
                            "target_arrival_timestamp_s": str(index + 0.05),
                            "target_measurement_age_s": "0.1",
                            "target_state_stale": "False",
                            "target_state_source": "d2_estimated_global_track",
                        }
                    )
        else:
            path.write_text(name, encoding="utf-8")
        artifacts[name] = {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {
        "schema": D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
        "episode_id": "episode-001",
        "case_id": "case-001",
        "seed": 1,
        "resource_count": 5,
        "target_count": 2,
        "producer": "main_airsim_runtime",
        "execution_stage": "post_simpleflight_control",
        "metric_scope": "actual_execution",
        "semantics_version": "d7_terminal_semantics_v2",
        "source_artifacts": artifacts,
        "metrics": metrics,
        "metadata": {
            "source_path": "d7_actual_execution_metrics.json",
            "plan_ids": ["actual-plan"],
            "plan_versions": [7],
            "owner_node_ids": ["d3_central"],
            "metadata_availability": {
                name: {
                    "status": "available",
                    "source_artifact": D7_ACTUAL_EXECUTION_METADATA_SOURCES[name],
                    "reason": "validated persisted actual-execution source",
                    "semantics": D7_ACTUAL_EXECUTION_METADATA_SEMANTICS[name],
                }
                for name in D7_ACTUAL_EXECUTION_METADATA_SOURCES
            },
        },
    }
