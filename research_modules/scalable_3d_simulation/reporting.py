"""Reproducible outputs and Chinese summaries for scalable 3D episodes."""

from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import numpy as np

from .episode_bus import jsonable
from .offline_evaluation import PrewrittenIdentityRecordPaths
from .orchestrator import EpisodeResult


POST_RUN_TIMING_SCHEMA_VERSION = "scalable3d-post-run-timings-v1"
STAGE_TIMING_SCHEMA_VERSION = "scalable3d-stage-timings-v2"
LEARNING_ADOPTION_EVIDENCE_RECORDS_SCHEMA_VERSION = (
    "scalable3d-learning-adoption-evidence-records-v1"
)
ACTIVE_VISION_R0_WINDOW_RECORDS_SCHEMA_VERSION = (
    "scalable3d-active-vision-r0-window-records-v1"
)
ACTIVE_VISION_A3_CANDIDATE_STAGE_RECORDS_SCHEMA_VERSION = (
    "scalable3d-active-vision-a3-candidate-stage-records-v1"
)


def write_episode_outputs(
    result: EpisodeResult,
    output_dir: Path,
    *,
    write_plot: bool = False,
    animation_formats: tuple[str, ...] = (),
) -> dict[str, Path]:
    """Write online logs and evaluator truth into explicitly separate artifacts."""

    post_run_started = perf_counter()
    timings: list[tuple[str, float]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    stage_started = perf_counter()
    paths["manifest"] = _write_json(output_dir / "manifest.json", result.manifest.to_dict())
    paths["scenario_config"] = _write_json(
        output_dir / "scenario_config.json", result.config.to_dict()
    )
    paths["summary"] = _write_json(output_dir / "summary.json", result.summary)
    if result.observation_governance_audit is not None:
        paths["observation_governance_audit"] = _write_json(
            output_dir / "observation_governance_audit.json",
            result.observation_governance_audit,
        )
    if result.learning_adoption_evidence_records is not None:
        evidence_payload = {
            "schema_version": (
                LEARNING_ADOPTION_EVIDENCE_RECORDS_SCHEMA_VERSION
            ),
            "episode_id": result.manifest.episode_id,
            "records": result.learning_adoption_evidence_records,
        }
        evidence_payload["content_sha256"] = _canonical_sha256(
            evidence_payload
        )
        paths["learning_adoption_evidence"] = _write_json(
            output_dir / "learning_adoption_evidence.json",
            evidence_payload,
        )
    if result.active_vision_r0_window_records is not None:
        r0_payload = {
            "schema_version": (
                ACTIVE_VISION_R0_WINDOW_RECORDS_SCHEMA_VERSION
            ),
            "episode_id": result.manifest.episode_id,
            "records": result.active_vision_r0_window_records,
        }
        r0_payload["content_sha256"] = _canonical_sha256(r0_payload)
        paths["active_vision_r0_windows"] = _write_json(
            output_dir / "active_vision_r0_windows.json",
            r0_payload,
        )
    if result.active_vision_a3_candidate_stage_records is not None:
        candidate_stage_payload = {
            "schema_version": (
                ACTIVE_VISION_A3_CANDIDATE_STAGE_RECORDS_SCHEMA_VERSION
            ),
            "episode_id": result.manifest.episode_id,
            "records": result.active_vision_a3_candidate_stage_records,
        }
        candidate_stage_payload["content_sha256"] = _canonical_sha256(
            candidate_stage_payload
        )
        paths["active_vision_a3_candidate_stages"] = _write_json(
            output_dir / "active_vision_a3_candidate_stages.json",
            candidate_stage_payload,
        )
    _append_post_run_timing(timings, "core_metadata", stage_started)

    stage_started = perf_counter()
    paths["communication_dispositions"] = _write_communication_dispositions_jsonl(
        output_dir / "communication_dispositions.jsonl",
        result,
    )
    paths["online_observations"], prewritten_identity_records = _write_online_jsonl(
        output_dir / "online_observations.jsonl",
        result,
        identity_output_dir=output_dir / "offline_identity",
    )
    _append_post_run_timing(timings, "online_bus_and_identity_views", stage_started)

    if result.observation_governance_audit is not None:
        from .observation_governance_reporting import (
            write_episode_observation_governance_outputs,
        )

        stage_started = perf_counter()
        paths.update(
            write_episode_observation_governance_outputs(
                result,
                output_dir / "observation_governance",
                source_bus_path=paths["online_observations"],
            )
        )
        _append_post_run_timing(timings, "observation_governance", stage_started)

    stage_started = perf_counter()
    paths["offline_truth_labels"] = _write_truth_jsonl(
        output_dir / "offline_truth_labels.jsonl", result
    )
    paths["offline_truth_state"] = _write_truth_state_npz(
        output_dir / "offline_truth_state.npz", result
    )
    _append_post_run_timing(timings, "offline_truth_artifacts", stage_started)

    from .offline_evaluation import (
        write_offline_consistency_evaluation,
        write_offline_identity_evaluation,
    )

    stage_started = perf_counter()
    identity_paths = write_offline_identity_evaluation(
        output_dir / "offline_identity",
        episode_id=result.manifest.episode_id,
        messages=result.online_messages,
        offline_truth_labels=result.offline_truth_labels,
        lineage_time_window_s=_identity_evaluation_window_s(result),
        truth_presence_window_s=_identity_evaluation_window_s(result),
        prewritten_records=prewritten_identity_records,
    )
    paths.update(identity_paths)
    _append_post_run_timing(timings, "offline_identity", stage_started)

    stage_started = perf_counter()
    paths.update(
        write_offline_consistency_evaluation(
            output_dir / "offline_consistency",
            manifest=result.manifest,
            consistency_records=result.d1_consistency_evidence_records,
            identity_evaluation_path=identity_paths.get(
                "offline_identity_evaluation"
            ),
            online_source_path=paths["online_observations"],
            truth_state_source_path=paths["offline_truth_state"],
            intruder_ids=result.intruder_ids,
            timestamps=result.timestamps,
            intruder_state_history=result.intruder_state_history,
            timestamp_tolerance_s=_consistency_evaluation_tolerance_s(result),
        )
    )
    _append_post_run_timing(timings, "offline_consistency", stage_started)

    stage_started = perf_counter()
    paths["offline_intercepts"] = _write_intercepts_jsonl(
        output_dir / "offline_proximity_intercepts.jsonl", result
    )
    paths["stage_timings"] = _write_stage_timings(
        output_dir / "stage_timings.csv", result
    )
    _append_post_run_timing(timings, "runtime_artifacts", stage_started)

    from .d6_integration import write_episode_truth_isolated_outputs

    stage_started = perf_counter()
    paths.update(
        write_episode_truth_isolated_outputs(
            result,
            output_dir / "d6_truth_isolated",
            artifact_paths=paths,
        )
    )
    _append_post_run_timing(timings, "d6_truth_isolated", stage_started)

    if int(result.summary.get("assignment_plan_ack_count", 0)) > 0:
        from .d6_integration import write_episode_runtime_plan_outcome_outputs

        stage_started = perf_counter()
        paths.update(
            write_episode_runtime_plan_outcome_outputs(
                result,
                output_dir / "d6_runtime_plan_outcomes",
                artifact_paths=paths,
            )
        )
        _append_post_run_timing(timings, "d6_runtime_plan_outcomes", stage_started)

    stage_started = perf_counter()
    paths["report"] = _write_episode_report(
        output_dir / "SCALABLE_3D_EPISODE_REPORT_CN.md", result
    )
    _append_post_run_timing(timings, "episode_report", stage_started)

    visual_started = perf_counter()
    visual_written = False
    if write_plot:
        visual_written = True
        paths["trajectory_plot"] = _write_trajectory_plot(
            output_dir / "trajectories_3d.png", result
        )
    if animation_formats:
        visual_written = True
        from .animation import write_trajectory_animation

        for raw_format in animation_formats:
            animation_format = str(raw_format).lower().lstrip(".")
            if animation_format not in {"gif", "mp4"}:
                raise ValueError("animation formats must be gif or mp4")
            paths[f"trajectory_{animation_format}"] = write_trajectory_animation(
                result,
                output_dir / f"trajectories_3d.{animation_format}",
            )
    if visual_written:
        _append_post_run_timing(timings, "visual_outputs", visual_started)
    paths["post_run_timings"] = _write_post_run_timings(
        output_dir / "post_run_timings.csv",
        timings,
        total_wall_time_s=perf_counter() - post_run_started,
    )
    return paths


def write_batch_outputs(results: Iterable[EpisodeResult], output_dir: Path) -> dict[str, Path]:
    """Aggregate scale/seed results without mixing online data and truth labels."""

    output_dir.mkdir(parents=True, exist_ok=True)
    episodes = list(results)
    rows = [dict(result.summary) for result in episodes]
    paths: dict[str, Path] = {}
    csv_path = output_dir / "episode_summary.csv"
    fieldnames = sorted({key for row in rows for key in row}) if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(rows)
    paths["episode_summary_csv"] = csv_path
    aggregate = _aggregate_rows(rows)
    paths["aggregate_json"] = _write_json(output_dir / "aggregate.json", aggregate)
    from .d6_integration import write_batch_truth_isolated_outputs

    paths.update(
        write_batch_truth_isolated_outputs(
            episodes,
            output_dir / "d6_truth_isolated_batch",
        )
    )
    report_path = output_dir / "SCALABLE_3D_BATCH_REPORT_CN.md"
    lines = [
        "# 三维质点批量实验报告",
        "",
        "## 结论",
        "",
        f"本批次完成 {len(rows)} 个 episode。下表记录规模、运行耗时、实时倍率和观测数量。",
        "当前数据只证明 main-owned 世界、传感器和日志合同的运行情况，不代表 D1-D7 全闭环性能。",
        "",
        "| 规模 | seed | 有限状态 | 运行时间/s | 实时倍率 | 在线观测数 |",
        "| ---: | ---: | :---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {target_count} | {seed} | {finite_state} | {wall_time_s:.4f} | "
            "{real_time_factor:.3f} | {online_observation_count} |".format(**row)
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths["report"] = report_path
    return paths


def _write_online_jsonl(
    path: Path,
    result: EpisodeResult,
    *,
    identity_output_dir: Path | None = None,
) -> tuple[Path, PrewrittenIdentityRecordPaths | None]:
    d1_topic = "modules.d1.fused_tracks"
    d2_topic = "modules.d2.associated_tracks"
    d1_record_count = sum(
        1 for message in result.online_messages if message.topic == d1_topic
    )
    d2_record_count = sum(
        1 for message in result.online_messages if message.topic == d2_topic
    )
    write_identity_views = (
        identity_output_dir is not None
        and d1_record_count > 0
        and d2_record_count > 0
    )
    prewritten_records: PrewrittenIdentityRecordPaths | None = None
    with ExitStack() as stack:
        stream = stack.enter_context(path.open("w", encoding="utf-8"))
        d1_stream = None
        d2_stream = None
        if write_identity_views:
            identity_output_dir.mkdir(parents=True, exist_ok=True)
            d1_path = identity_output_dir / "online_d1_records.jsonl"
            d2_path = identity_output_dir / "online_d2_records.jsonl"
            d1_stream = stack.enter_context(d1_path.open("w", encoding="utf-8"))
            d2_stream = stack.enter_context(d2_path.open("w", encoding="utf-8"))
            prewritten_records = PrewrittenIdentityRecordPaths(
                d1_path=d1_path,
                d2_path=d2_path,
                d1_record_count=d1_record_count,
                d2_record_count=d2_record_count,
            )
        for message in result.online_messages:
            line = (
                json.dumps(
                    message.to_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
            stream.write(line)
            if message.topic == d1_topic and d1_stream is not None:
                d1_stream.write(line)
            elif message.topic == d2_topic and d2_stream is not None:
                d2_stream.write(line)
    return path, prewritten_records


def _write_truth_jsonl(path: Path, result: EpisodeResult) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for label in result.offline_truth_labels:
            stream.write(
                json.dumps(
                    jsonable(label),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return path


def _write_communication_dispositions_jsonl(
    path: Path,
    result: EpisodeResult,
) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for record in result.communication_disposition_records:
            stream.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return path


def _write_intercepts_jsonl(path: Path, result: EpisodeResult) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for event in result.proximity_intercepts:
            stream.write(
                json.dumps(
                    jsonable(event),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return path


def _write_truth_state_npz(path: Path, result: EpisodeResult) -> Path:
    np.savez_compressed(
        path,
        timestamps=result.timestamps,
        intruder_state=result.intruder_state_history,
        intruder_ids=np.asarray(result.intruder_ids, dtype="U"),
        interceptor_state=result.interceptor_state_history,
        recon_state=result.recon_state_history,
        intruder_active=result.intruder_active_history,
    )
    return path


def _write_stage_timings(path: Path, result: EpisodeResult) -> Path:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "schema_version",
                "stage",
                "call_count",
                "wall_time_s",
                "mean_wall_time_ms",
                "p50_wall_time_ms",
                "p95_wall_time_ms",
                "max_wall_time_ms",
                "distribution_available",
                "distribution_unavailable_reason",
            ],
        )
        writer.writeheader()
        for timing in result.stage_timings:
            writer.writerow(
                {
                    "schema_version": STAGE_TIMING_SCHEMA_VERSION,
                    "stage": timing.stage,
                    "call_count": timing.call_count,
                    "wall_time_s": timing.wall_time_s,
                    "mean_wall_time_ms": timing.mean_wall_time_ms,
                    "p50_wall_time_ms": timing.p50_wall_time_ms,
                    "p95_wall_time_ms": timing.p95_wall_time_ms,
                    "max_wall_time_ms": timing.max_wall_time_ms,
                    "distribution_available": timing.distribution_available,
                    "distribution_unavailable_reason": (
                        timing.distribution_unavailable_reason
                    ),
                }
            )
    return path


def _append_post_run_timing(
    timings: list[tuple[str, float]], stage: str, started: float
) -> None:
    timings.append((stage, perf_counter() - started))


def _write_post_run_timings(
    path: Path,
    timings: Iterable[tuple[str, float]],
    *,
    total_wall_time_s: float,
) -> Path:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["schema_version", "stage", "wall_time_s"],
        )
        writer.writeheader()
        for stage, wall_time_s in timings:
            writer.writerow(
                {
                    "schema_version": POST_RUN_TIMING_SCHEMA_VERSION,
                    "stage": stage,
                    "wall_time_s": wall_time_s,
                }
            )
        writer.writerow(
            {
                "schema_version": POST_RUN_TIMING_SCHEMA_VERSION,
                "stage": "total_before_timing_artifact",
                "wall_time_s": total_wall_time_s,
            }
        )
    return path


def _identity_evaluation_window_s(result: EpisodeResult) -> float:
    return result.config.identity_lineage_freshness_budget_s


def _consistency_evaluation_tolerance_s(result: EpisodeResult) -> float:
    return max(1.0e-9, min(1.0e-6, result.config.physics_dt_s * 1.0e-4))


def _write_episode_report(path: Path, result: EpisodeResult) -> Path:
    summary = result.summary
    timings = {item.stage: item for item in result.stage_timings}
    module_enabled = bool(summary.get("module_stack_enabled", False))
    module_diagnostics = summary.get("module_final_diagnostics", {})
    if module_enabled and isinstance(module_diagnostics, dict):
        module_conclusion = (
            "本次启用 D1-D7 规则集成栈。episode 结束时 D1/D2 航迹数分别为 "
            f"{int(module_diagnostics.get('d1_track_count', 0))}/"
            f"{int(module_diagnostics.get('d2_track_count', 0))}，D3 分配数为 "
            f"{int(module_diagnostics.get('d3_assignment_count', 0))}，D5 当前主动视觉指令数为 "
            f"{int(module_diagnostics.get('d5_active_vision_command_count', 0))}，D7 指令数为 "
            f"{int(module_diagnostics.get('d7_command_count', 0))}。"
        )
        boundary_lines = [
            "当前结果覆盖合成传感器、D1-D5 在线处理、D7 三维命令和世界状态回写。",
            "D5 主动视觉当前执行确定性观察/搜索策略；学习模型、D3 学习策略、D6 正式离线评分和多随机种子统计仍需独立验收。",
        ]
    else:
        module_conclusion = (
            "本次未启用 D1-D7 集成栈，拦截数量不能作为体系闭环结果使用。"
        )
        boundary_lines = [
            "当前结果只覆盖向量化三维环境、合成传感器、异步到达和日志隔离。",
            "D1-D7 算法能力未在本次 episode 中执行。",
        ]
    if bool(summary.get("communication_enabled", False)):
        communication_line = (
            "传感器到融合中心的通信队列发送 "
            f"{int(summary.get('communication_sent_count', 0))} 个批次，投递 "
            f"{int(summary.get('communication_delivered_count', 0))} 个，丢弃 "
            f"{int(summary.get('communication_dropped_count', 0))} 个，结束时仍在途 "
            f"{int(summary.get('communication_pending_count', 0))} 个。"
        )
    else:
        communication_line = "本次关闭传感器通信队列，批次在传感器处理完成后直接交付融合中心。"
    lines = [
        "# 三维质点单次实验报告",
        "",
        "## 结论",
        "",
        f"场景包含 {summary['target_count']} 个来袭目标、{summary['resource_count']} 架拦截资源和 "
        f"{summary['recon_count']} 个高空侦察节点。世界状态有限性检查结果为 "
        f"`{summary['finite_state']}`。",
        f"仿真推进 {summary['simulated_duration_s']:.2f} 秒，墙钟耗时 "
        f"{summary['wall_time_s']:.3f} 秒，实时倍率为 {summary['real_time_factor']:.3f}。",
        module_conclusion,
        f"离线评估侧登记 {summary['intercepted_target_count']} 个五米内唯一接近目标。该计数不自动代表任务身份正确、合同许可或控制成功。",
        "",
        "## 数据合同",
        "",
        f"在线总线写入 {summary['online_observation_count']} 条匿名观测，其中雷达 "
        f"{summary['radar_observation_count']} 条、声学 {summary['acoustic_observation_count']} 条、"
        f"视觉 {summary['visual_observation_count']} 条。",
        f"离线真值标签单独写入 {summary['offline_truth_label_count']} 条；在线真值使用计数为 "
        f"{summary['online_truth_use_count']}。",
        "在线观测保留量测时间、到达时间和协方差。真值状态及观测标签只保存在离线评估文件。",
        communication_line,
        "当前通信队列覆盖传感器到融合中心的批次传输。D1-D7 进程内调用尚未拆成独立网络节点。",
        "相机调度发出 "
        f"{int(summary.get('camera_command_issued_count', 0))} 条命令，确认应用 "
        f"{int(summary.get('camera_command_applied_count', 0))} 条，拒绝 "
        f"{int(summary.get('camera_command_rejected_count', 0))} 条。命令只调整相机指向与视场，不生成分配或全局航迹编号。",
        "main 对 D3 新计划写入 "
        f"{int(summary.get('assignment_plan_ack_count', 0))} 条运行时确认，覆盖 "
        f"{int(summary.get('assignment_plan_binding_ack_count', 0))} 个分配绑定；其中 "
        f"{int(summary.get('assignment_plan_control_applied_count', 0))} 个绑定形成 D7 命令，"
        f"{int(summary.get('assignment_plan_hold_count', 0))} 个绑定保持。该确认只证明计划被运行时消费，不代表物理拦截结果或可归因奖励。",
        "",
        "## 阶段耗时",
        "",
        "| 阶段 | 调用次数 | 总耗时/s | 平均耗时/ms |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name in sorted(timings):
        item = timings[name]
        lines.append(
            f"| {name} | {item.call_count} | {item.wall_time_s:.6f} | "
            f"{item.mean_wall_time_ms:.3f} |"
        )
    lines.extend(
        [
            "",
            "## 当前边界",
            "",
            *boundary_lines,
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_trajectory_plot(path: Path, result: EpisodeResult) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    from .animation import ensure_mplot3d

    ensure_mplot3d(matplotlib)
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(10, 7))
    axis = figure.add_subplot(111, projection="3d")
    target_limit = min(20, result.config.target_count)
    resource_limit = min(20, result.config.resource_count)
    for index in range(target_limit):
        values = result.intruder_state_history[:, index, :3]
        axis.plot(values[:, 0], values[:, 1], -values[:, 2], color="#b33a3a", alpha=0.45)
    for index in range(resource_limit):
        values = result.interceptor_state_history[:, index, :3]
        axis.plot(values[:, 0], values[:, 1], -values[:, 2], color="#286090", alpha=0.45)
    axis.set_xlabel("North / m")
    axis.set_ylabel("East / m")
    axis.set_zlabel("Altitude / m")
    axis.set_title("Scalable 3D point-mass trajectories (first 20 pairs)")
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)
    return path


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"episode_count": 0}
    finite = sum(bool(row.get("finite_state")) for row in rows)
    wall = np.asarray([float(row["wall_time_s"]) for row in rows], dtype=float)
    real_time = np.asarray([float(row["real_time_factor"]) for row in rows], dtype=float)
    return {
        "episode_count": len(rows),
        "finite_episode_count": finite,
        "wall_time_mean_s": float(np.mean(wall)),
        "wall_time_std_s": float(np.std(wall)),
        "real_time_factor_mean": float(np.mean(real_time)),
        "real_time_factor_min": float(np.min(real_time)),
        "online_truth_use_count": int(sum(int(row["online_truth_use_count"]) for row in rows)),
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(
        json.dumps(jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        jsonable(payload),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
