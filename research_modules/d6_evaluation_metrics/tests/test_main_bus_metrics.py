from __future__ import annotations

import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    STANDARD_MAPPING_VERSION,
    load_main_episode_bus_metric_files,
    load_main_episode_bus_metrics,
)


def test_load_main_episode_bus_metrics_preserves_execution_scope_and_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main_episode_bus_metrics.json"
    path.write_text(
        json.dumps(
            {
                "metrics": {
                    "episode_id": "seed_007_execution",
                    "seed": 7,
                    "batch_seed": 1007,
                    "scenario_group": "blocks_cv_5v5",
                    "metric_scope": "execution",
                    "drone_count": 3,
                    "resource_count": 3,
                    "target_count": 4,
                    "camera_count": 6,
                    "active_degradation_precision": 0.5,
                    "active_degradation_label_count": 4,
                    "unnecessary_active_degradation_count": 1,
                    "terminal_lock_count": 2,
                    "visual_png_switch_count": 1,
                    "intercept_success_count": 1,
                    "collision_intercept_count": 1,
                    "range_intercept_count": 0,
                    "terminal_switch_reject_count": 2,
                    "gate_reject_count": 2,
                    "secondary_network_joint_full_view_frame_rate": 0.75,
                    "secondary_network_mean_coverage_ratio": 0.8,
                    "secondary_single_camera_full_view_frame_rate": 0.25,
                    "cross_view_association_count": 3,
                    "secondary_detect_available_but_not_registered_count": 1,
                    "cue_pointing_error_mean_deg": 2.0,
                    "gimbal_pointing_error_mean_deg": 1.0,
                    "metadata": {
                        "guidance_law_counts": {"png_vm": 3},
                        "terminal_switch_reject_reasons": {
                            "camera_quality": 2
                        },
                        "terminal_contract_reject_reasons": {
                            "terminal_contract_not_satisfied": 1
                        },
                    },
                },
                "metadata": {
                    "record_counts": {"events": 11},
                    "main_episode_bus_execution_metrics_merged": True,
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    metrics = load_main_episode_bus_metrics(path)

    assert metrics.episode_id == "seed_007_execution"
    assert metrics.seed == 7
    assert metrics.batch_seed == 1007
    assert metrics.scenario_group == "blocks_cv_5v5"
    assert metrics.metric_scope == "execution"
    assert metrics.drone_count == 3
    assert metrics.resource_count == 3
    assert metrics.target_count == 4
    assert metrics.camera_count == 6
    assert metrics.mission_outcome == "partial"
    assert metrics.success_reason == "partial_intercept_success_count=1/4"
    assert metrics.failure_reason == "not_all_required_intercepts_confirmed"
    assert metrics.eval_priority == "P0"
    assert metrics.implementation_status == "implemented"
    assert metrics.evidence_path == str(path)
    assert metrics.active_degradation_precision == pytest.approx(0.5)
    assert metrics.active_degradation_label_count == 4
    assert metrics.unnecessary_active_degradation_count == 1
    assert metrics.terminal_lock_count == 2
    assert metrics.visual_png_switch_count == 1
    assert metrics.intercept_success_count == 1
    assert metrics.secondary_network_joint_full_view_frame_rate == pytest.approx(0.75)
    assert metrics.secondary_network_mean_coverage_ratio == pytest.approx(0.8)
    assert metrics.secondary_single_camera_full_view_frame_rate == pytest.approx(0.25)
    assert metrics.cross_view_association_count == 3
    assert metrics.secondary_detect_available_but_not_registered_count == 1
    assert metrics.cue_pointing_error_mean_deg == pytest.approx(2.0)
    assert metrics.gimbal_pointing_error_mean_deg == pytest.approx(1.0)
    assert metrics.metadata["guidance_law_counts"] == {"png_vm": 3}
    assert metrics.metadata["terminal_switch_reject_reasons"] == {
        "camera_quality": 2
    }
    assert metrics.metadata["terminal_contract_reject_reasons"] == {
        "terminal_contract_not_satisfied": 1
    }
    assert metrics.metadata["main_bus_file_metadata"]["record_counts"] == {
        "events": 11
    }


def test_load_main_episode_bus_metrics_marks_unlabeled_precision_unavailable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main_episode_bus_metrics.json"
    path.write_text(
        json.dumps(
            {
                "metrics": {
                    "episode_id": "unlabeled",
                    "active_degradation_count": 3,
                    "active_degradation_precision": 0.0,
                    "metadata": {"active_degradation_reviewed_count": 0},
                }
            }
        ),
        encoding="utf-8",
    )

    metrics = load_main_episode_bus_metrics(path)

    assert metrics.active_degradation_precision is None
    assert metrics.active_degradation_label_count == 0


def test_load_main_episode_bus_metric_files_infers_contract_scope_from_filename(
    tmp_path: Path,
) -> None:
    execution_path = tmp_path / "main_episode_bus_metrics.json"
    contract_path = tmp_path / "main_episode_bus_contract_metrics.json"
    execution_path.write_text(
        json.dumps({"metrics": {"episode_id": "exec", "metric_scope": "execution"}}),
        encoding="utf-8",
    )
    contract_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "episode_id": "contract",
                    "seed": 8,
                    "scenario_group": "blocks_cv_2v2",
                    "drone_count": 4,
                    "resource_count": 4,
                    "target_count": 3,
                    "camera_count": 5,
                }
            }
        ),
        encoding="utf-8",
    )

    execution, contract = load_main_episode_bus_metric_files(
        [execution_path, contract_path]
    )

    assert execution.metric_scope == "execution"
    assert contract.metric_scope == "contract"
    assert contract.seed == 8
    assert contract.scenario_group == "blocks_cv_2v2"
    assert contract.drone_count == 4
    assert contract.resource_count == 4
    assert contract.target_count == 3
    assert contract.camera_count == 5
    assert contract.mission_outcome == "failed"
    assert contract.failure_reason == "no_success_evidence"


def test_load_main_episode_bus_metrics_backfills_eval_versions_from_metadata(
    tmp_path: Path,
) -> None:
    path = tmp_path / "main_episode_bus_metrics.json"
    path.write_text(
        json.dumps(
            {
                "metrics": {
                    "episode_id": "metadata_versions",
                    "metric_scope": "execution",
                    "metadata": {
                        "scenario_version": "scenario-metadata-v3",
                        "standard_mapping_version": STANDARD_MAPPING_VERSION,
                        "evidence_path": "outputs/evidence/main_episode_bus_metrics.json",
                    },
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    metrics = load_main_episode_bus_metrics(path)

    assert metrics.scenario_version == "scenario-metadata-v3"
    assert metrics.standard_mapping_version == STANDARD_MAPPING_VERSION
    assert metrics.evidence_path == "outputs/evidence/main_episode_bus_metrics.json"
    assert metrics.metadata["scenario_version"] == "scenario-metadata-v3"
    assert metrics.metadata["standard_mapping_version"] == STANDARD_MAPPING_VERSION
    assert metrics.metadata["evidence_path"] == "outputs/evidence/main_episode_bus_metrics.json"
