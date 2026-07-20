from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.scalable_3d_offline import (
    Scalable3DOfflineEvaluationInputs,
    Scalable3DOfflineReportGenerator,
    evaluate_scalable_3d_episode,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def _envelope(
    sequence: int,
    topic: str,
    timestamp: float,
    payload: dict[str, object],
    schema_version: str,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": topic,
        "source": "D5" if topic.startswith("modules.") else "MAIN-RUNTIME",
        "timestamp": timestamp,
        "schema_version": schema_version,
        "payload": payload,
    }


def _track(index: int) -> dict[str, object]:
    covariance = [[0.0] * 6 for _ in range(6)]
    for axis in range(6):
        covariance[axis][axis] = 1.0
    return {
        "global_track_id": f"GT-{index:04d}",
        "timestamp": 0.1,
        "state_ned": [100.0 + index, 0.0, -50.0, -5.0, 0.0, 0.0],
        "covariance": covariance,
        "track_state": "confirmed",
    }


def _command(
    index: int,
    *,
    requested_mode: str,
    effective_mode: str,
    target_id: str | None = None,
    reason: str = "rule_fresh_assigned_projection",
) -> dict[str, object]:
    intent = "observe_target" if target_id is not None else "search_sector"
    return {
        "camera_id": f"CAM-INT-{index:04d}",
        "resource_id": f"INT-{index:04d}",
        "issued_timestamp": 1.0,
        "expires_timestamp": 1.5,
        "plan_version": 4,
        "coalition_version": 2,
        "communication_version": 7,
        "intent": intent,
        "horizontal_fov_deg": 90.0,
        "fov_mode": "wide",
        "target_global_track_id": target_id,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "reason": reason,
    }


def _ack(
    command: dict[str, object],
    *,
    latency_s: float,
    status: str = "applied",
    reason: str = "accepted",
    target_id: str | None | object = ...,
) -> dict[str, object]:
    fields = {
        key: command[key]
        for key in (
            "camera_id",
            "resource_id",
            "issued_timestamp",
            "expires_timestamp",
            "plan_version",
            "coalition_version",
            "communication_version",
            "intent",
            "target_global_track_id",
            "requested_mode",
            "effective_mode",
        )
    }
    fields["ack_timestamp"] = float(command["issued_timestamp"]) + latency_s
    fields["status"] = status
    fields["reason"] = reason
    if target_id is not ...:
        fields["target_global_track_id"] = target_id
    return fields


def _write_episode(
    directory: Path,
    *,
    commands: list[dict[str, object]] | None,
    acks: list[dict[str, object]],
    physical_proximity: bool = False,
    summary_override: dict[str, object] | None = None,
    seed: int = 1,
) -> Path:
    directory.mkdir(parents=True)
    config = {
        "scenario_name": "dynamic_N_fixture",
        "scenario_version": "active-vision-runtime-v1",
        "seed": seed,
        "target_count": 6,
        "resource_count": 4,
        "recon_count": 1,
        "region_count": 2,
        "visual_enabled": True,
        "d3_policy_version": "d3-rule-v1",
        "d4_policy_version": "d4-rule-v1",
        "d5_model_version": "d5-rule-v1",
        "metadata": {},
        "schema_version": "scalable3d-scenario-v1",
    }
    canonical = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    config_hash = hashlib.sha256(canonical).hexdigest()
    manifest = {
        "episode_id": f"active-vision-s{seed}",
        "git_commit": "0123456789abcdef",
        "repository_dirty": False,
        "config_sha256": config_hash,
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": seed,
        "world_schema": "scalable3d-world-v1",
        "bus_schema": "scalable3d-episode-bus-v1",
        "scenario_schema": "scalable3d-scenario-v1",
        "online_observation_schema": "scalable3d-observation-v1",
        "offline_truth_schema": "scalable3d-offline-truth-v1",
        "d1_model_version": "d1-v1",
        "d2_model_version": "d2-v1",
        "d3_policy_version": config["d3_policy_version"],
        "d4_policy_version": config["d4_policy_version"],
        "d5_model_version": config["d5_model_version"],
        "d7_model_version": "d7-v1",
        "threshold_version": "threshold-v1",
    }
    reason_counts = Counter(
        str(item["reason"]) for item in acks if item["status"] == "rejected"
    )
    summary = {
        "episode_id": manifest["episode_id"],
        "scenario_name": config["scenario_name"],
        "scenario_version": config["scenario_version"],
        "seed": seed,
        "target_count": config["target_count"],
        "resource_count": config["resource_count"],
        "recon_count": config["recon_count"],
        "finite_state": True,
        "online_truth_use_count": 0,
        "camera_command_issued_count": len(commands or []),
        "camera_command_applied_count": sum(
            item["status"] == "applied" for item in acks
        ),
        "camera_command_rejected_count": sum(
            item["status"] == "rejected" for item in acks
        ),
        "camera_command_ack_count": len(acks),
        "camera_command_rejection_reason_counts": dict(reason_counts),
        "module_final_diagnostics": {
            "schema_version": "scalable3d-module-stack-v1",
            "online_truth_use_count": 0,
        },
    }
    if summary_override:
        summary.update(summary_override)

    tracks = [_track(index) for index in range(1, 7)]
    records = [
        _envelope(
            1,
            "modules.d2.associated_tracks",
            0.1,
            {
                "timestamp": 0.1,
                "track_count": len(tracks),
                "tracks": tracks,
                "id_switch_count": None,
                "id_switch_count_available": False,
            },
            "d2-scalable3d-association-v1",
        )
    ]
    sequence = 2
    if commands is not None:
        effective_counts = Counter(str(item["effective_mode"]) for item in commands)
        intent_counts = Counter(str(item["intent"]) for item in commands)
        records.append(
            _envelope(
                sequence,
                "modules.d5.active_vision",
                1.0,
                {
                    "timestamp": 1.0,
                    "command_count": len(commands),
                    "effective_mode_counts": dict(effective_counts),
                    "intent_counts": dict(intent_counts),
                    "commands": commands,
                },
                "d5.active-vision-runtime.v1",
            )
        )
        sequence += 1
    for ack in acks:
        records.append(
            _envelope(
                sequence,
                "runtime.camera_command_ack",
                float(ack["ack_timestamp"]),
                ack,
                "scalable3d-camera-command-ack-v1",
            )
        )
        sequence += 1

    proximity = []
    if physical_proximity:
        proximity.append(
            {
                "timestamp": 2.0,
                "resource_index": 0,
                "target_index": 0,
                "resource_id": "INT-0001",
                "truth_target_id": "TGT-0001",
                "distance_m": 4.0,
            }
        )
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "scenario_config.json", config)
    _write_json(directory / "summary.json", summary)
    _write_jsonl(directory / "online_observations.jsonl", records)
    _write_jsonl(directory / "offline_proximity_intercepts.jsonl", proximity)
    _write_jsonl(directory / "offline_truth_labels.jsonl", [])
    with (directory / "stage_timings.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        csv.DictWriter(
            stream,
            fieldnames=["stage", "call_count", "wall_time_s", "mean_wall_time_ms"],
        ).writeheader()
    return directory


def test_rule_shadow_assist_and_ack_layers_remain_separate(tmp_path: Path) -> None:
    commands = [
        _command(1, requested_mode="disabled", effective_mode="disabled", target_id="GT-0001"),
        _command(2, requested_mode="shadow", effective_mode="shadow", target_id="GT-0002"),
        _command(3, requested_mode="assist", effective_mode="assist", target_id="GT-0003", reason="model_observe_target"),
    ]
    acks = [
        _ack(commands[0], latency_s=0.01),
        _ack(commands[1], latency_s=0.02),
        _ack(
            commands[2],
            latency_s=0.03,
            status="rejected",
            reason="stale_plan_version",
        ),
    ]
    episode = _write_episode(tmp_path / "layers", commands=commands, acks=acks)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_rule_command_count"] == 2
    assert row["d5_active_vision_shadow_suggestion_count"] == 1
    assert row["d5_active_vision_assist_adopted_count"] == 1
    assert row["d5_active_vision_ack_count"] == 3
    assert row["d5_active_vision_ack_applied_count"] == 2
    assert row["d5_active_vision_ack_rejected_count"] == 1
    assert row["d5_active_vision_rule_applied_count"] == 2
    assert row["d5_active_vision_assist_applied_count"] == 0
    assert row["d5_active_vision_ack_latency_p50_ms"] == pytest.approx(20.0)
    assert row["d5_active_vision_ack_latency_p95_ms"] == pytest.approx(29.0)
    assert row["d5_active_vision_rejected_stale_version_count"] == 1
    assert row["d5_active_vision_target_reference_consistent_count"] == 3
    assert row["d5_active_vision_target_reference_consistency_rate"] == 1.0
    assert row["d5_active_vision_summary_counter_consistent"] is True
    assert row["d5_active_vision_physical_outcome_attribution"] is None
    assert row[
        "d5_active_vision_physical_outcome_attribution_unavailable_reason"
    ] == "no_assist_action_applied"


def test_applied_assist_and_five_meter_event_do_not_create_causal_attribution(
    tmp_path: Path,
) -> None:
    command = _command(
        1,
        requested_mode="assist",
        effective_mode="assist",
        target_id="GT-0001",
        reason="model_observe_target",
    )
    episode = _write_episode(
        tmp_path / "assist_physical",
        commands=[command],
        acks=[_ack(command, latency_s=0.015)],
        physical_proximity=True,
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_assist_applied_count"] == 1
    assert row["offline_proximity_within_5m_count"] == 1
    assert row["d5_active_vision_physical_outcome_attribution"] is None
    assert row[
        "d5_active_vision_physical_outcome_attribution_unavailable_reason"
    ] == "paired_control_treatment_episode_evidence_missing"


def test_rejection_taxonomy_is_computed_from_observed_ack_reasons(tmp_path: Path) -> None:
    commands = [
        _command(index, requested_mode="disabled", effective_mode="disabled", target_id=f"GT-{index:04d}")
        for index in range(1, 5)
    ]
    reasons = (
        "command_expired",
        "stale_coalition_version",
        "camera_or_resource_unavailable",
        "degenerate_aim_point",
    )
    acks = [
        _ack(command, latency_s=0.01, status="rejected", reason=reason)
        for command, reason in zip(commands, reasons)
    ]
    episode = _write_episode(tmp_path / "taxonomy", commands=commands, acks=acks)

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_rejected_expired_count"] == 1
    assert row["d5_active_vision_rejected_stale_version_count"] == 1
    assert row["d5_active_vision_rejected_camera_unavailable_count"] == 1
    assert row["d5_active_vision_rejected_other_count"] == 1
    assert row["d5_active_vision_rejection_reason_distribution_json"] == dict(
        Counter(reasons)
    )


def test_unknown_track_truth_field_and_ack_rebinding_fail_closed(tmp_path: Path) -> None:
    command = _command(
        1,
        requested_mode="disabled",
        effective_mode="disabled",
        target_id="GT-9999",
    )
    command["truth_id"] = "TGT-0001"
    ack = _ack(command, latency_s=0.01, target_id="GT-0001")
    episode = _write_episode(
        tmp_path / "identity_violation",
        commands=[command],
        acks=[ack],
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_target_reference_violation_count"] == 1
    assert row["d5_active_vision_ack_target_mismatch_count"] == 1
    assert row["d5_active_vision_online_truth_field_violation_count"] == 1
    assert row["online_truth_field_violation_count"] == 1
    assert row["formal_acceptance_eligible"] is False
    assert "d5_active_vision_unknown_center_track_reference" in row[
        "episode_failure_reasons_json"
    ]
    assert "d5_active_vision_ack_target_reference_mismatch" in row[
        "episode_failure_reasons_json"
    ]


def test_missing_active_vision_log_is_unavailable_even_with_zero_summary(
    tmp_path: Path,
) -> None:
    episode = _write_episode(tmp_path / "missing", commands=None, acks=[])

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_command_issued_count"] is None
    assert row["d5_active_vision_command_issued_count_availability"] == "unavailable"
    assert row["d5_active_vision_command_issued_count_unavailable_reason"] == (
        "d5_active_vision_publication_missing"
    )
    assert row["d5_active_vision_ack_count"] is None


def test_missing_preceding_d2_snapshot_does_not_turn_unknown_references_into_zero(
    tmp_path: Path,
) -> None:
    command = _command(
        1,
        requested_mode="disabled",
        effective_mode="disabled",
        target_id="GT-0001",
    )
    episode = _write_episode(
        tmp_path / "missing_d2",
        commands=[command],
        acks=[_ack(command, latency_s=0.01)],
    )
    online_path = episode / "online_observations.jsonl"
    records = [
        json.loads(line)
        for line in online_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _write_jsonl(
        online_path,
        [record for record in records if record["topic"] != "modules.d2.associated_tracks"],
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_target_reference_count"] == 1
    assert row["d5_active_vision_target_reference_evaluable_count"] == 0
    assert row["d5_active_vision_target_reference_consistent_count"] is None
    assert row["d5_active_vision_target_reference_violation_count"] is None
    assert row["d5_active_vision_target_reference_consistency_rate"] is None
    assert row["formal_acceptance_eligible"] is False
    assert "d5_active_vision_center_track_reference_evidence_incomplete" in row[
        "episode_failure_reasons_json"
    ]


def test_summary_counter_conflict_is_visible_and_not_formal_evidence(tmp_path: Path) -> None:
    command = _command(
        1,
        requested_mode="disabled",
        effective_mode="disabled",
        target_id="GT-0001",
    )
    episode = _write_episode(
        tmp_path / "summary_conflict",
        commands=[command],
        acks=[_ack(command, latency_s=0.01)],
        summary_override={"camera_command_issued_count": 2},
    )

    row = evaluate_scalable_3d_episode(episode)

    assert row["d5_active_vision_command_issued_count"] == 1
    assert row["d5_active_vision_summary_counter_consistent"] is False
    assert "d5_active_vision_summary_counter_mismatch" in row[
        "episode_failure_reasons_json"
    ]
    assert row["formal_acceptance_eligible"] is False


def test_report_aggregates_actual_scale_and_active_vision_evidence(tmp_path: Path) -> None:
    episodes = []
    for seed in (1, 2):
        command = _command(
            1,
            requested_mode="disabled",
            effective_mode="disabled",
            target_id="GT-0001",
        )
        episodes.append(
            _write_episode(
                tmp_path / f"seed_{seed}",
                commands=[command],
                acks=[_ack(command, latency_s=0.01 + seed * 0.001)],
                seed=seed,
            )
        )
    outputs = Scalable3DOfflineReportGenerator().write_report_bundle(
        tmp_path / "report",
        inputs=Scalable3DOfflineEvaluationInputs(episode_dirs=tuple(episodes)),
        bootstrap_resamples=50,
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    group = aggregate["groups"][0]
    assert group["target_count"] == 6
    assert group["resource_count"] == 4
    assert group["camera_count"] == 5
    assert group["seed_count"] == 2
    assert group["d5_active_vision_effective_mode_distribution"] == {"disabled": 2}
    assert group["metric_statistics"]["d5_active_vision_ack_applied_count"][
        "mean"
    ] == 1.0
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "D5 主动视觉运行证据" in markdown
    assert "物理结果不从同一 episode 的接近事件归因" in markdown
