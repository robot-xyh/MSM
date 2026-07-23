from __future__ import annotations

import cProfile
import hashlib
import json
from pathlib import Path
import pstats
from time import perf_counter
from typing import Any, Mapping, Sequence

import numpy as np

from .long_duration_performance import (
    _coalesced_scan_semantic_digest,
    _json_sha256,
    _semantic_track_snapshot,
)
from .scalable_3d import Scalable3DFusionAdapter, sensor_observations_from_online_batch
from .scan_input import ScanInputOrganizer, SensorScanFrame


TAIL_LATENCY_PERFORMANCE_SCHEMA_VERSION = "d1.tail_latency_performance.v1"

_FUSION_OPERATION_FIELDS = (
    "history_replay_count",
    "origin_replay_count",
    "state_cache_hit_count",
    "state_cache_miss_count",
    "finalization_replay_count",
    "replay_filter_update_count",
    "replay_checkpoint_reuse_count",
    "global_track_materialization_count",
    "sensor_health_snapshot_build_count",
    "association_candidate_pair_count",
    "association_measurement_model_build_count",
    "association_projection_build_count",
    "association_innovation_solve_count",
    "association_radar_track_state_build_count",
    "association_radar_observation_state_build_count",
    "deferred_update_replay_avoidance_count",
)

_FUSION_DIAGNOSTIC_DELTA_FIELDS = (
    "batch_count",
    "scan_batch_count",
    "observation_count",
    "history_replay_count",
    "origin_replay_count",
    "finalization_replay_count",
    "replay_filter_update_count",
    "replay_checkpoint_reuse_count",
    "checkpoint_state_query_count",
    "fixed_lag_rebase_count",
    "fixed_lag_checkpoint_suffix_reuse_count",
    "replay_checkpoint_prefix_fast_path_count",
    "cached_consistency_refresh_count",
    "global_track_materialization_count",
    "sensor_health_snapshot_build_count",
    "association_candidate_pair_count",
    "association_innovation_solve_count",
)

_SCAN_INPUT_PROFILE_SPECS = (
    ("ScanInputOrganizer.ingest", "scan_input.py", "ingest", 400, None),
    (
        "SensorScanFrame.__post_init__",
        "scan_input.py",
        "__post_init__",
        90,
        250,
    ),
    (
        "SensorObservation.__post_init__",
        "types.py",
        "__post_init__",
        75,
        180,
    ),
    (
        "assert_online_observations_identity_free",
        "online_anonymization.py",
        "assert_online_observations_identity_free",
        None,
        None,
    ),
    ("_snapshot_observation", "scan_input.py", "_snapshot_observation", None, None),
    (
        "_frame_snapshot_is_intact",
        "scan_input.py",
        "_frame_snapshot_is_intact",
        None,
        None,
    ),
    ("_claim_for_frame", "scan_input.py", "_claim_for_frame", None, None),
    ("_digest", "scan_input.py", "_digest", None, None),
    ("_json_safe", "scan_input.py", "_json_safe", None, None),
)


def analyze_frozen_tail_latency(
    source: str | Path,
    *,
    scan_input_repeat_count: int = 5,
    scan_input_benchmark_scan_count: int = 256,
    profile_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Attribute D1 tail latency and verify safe existing-frame reuse."""

    if scan_input_repeat_count < 1:
        raise ValueError("scan_input_repeat_count must be positive")
    if scan_input_benchmark_scan_count < 1:
        raise ValueError("scan_input_benchmark_scan_count must be positive")

    frames, input_summary = load_frozen_sensor_frames(source)
    profile_dir = None if profile_directory is None else Path(profile_directory)
    fusion_profile_path = (
        None
        if profile_dir is None
        else profile_dir / "d1_fusion_reference.prof"
    )
    reference = _run_pipeline_variant(
        frames,
        variant="organizer_resnapshot_reference",
        resnapshot_existing_frames=True,
        fusion_profile_path=fusion_profile_path,
        capture_tail_rows=False,
    )
    optimized = _run_pipeline_variant(
        frames,
        variant="validated_frame_reuse",
        resnapshot_existing_frames=False,
        capture_tail_rows=True,
    )
    acceptance = _equivalence_acceptance(
        reference,
        optimized,
        input_summary=input_summary,
    )
    benchmark_count = min(len(frames), int(scan_input_benchmark_scan_count))
    timing_distribution = _interleaved_scan_input_distribution(
        frames[:benchmark_count],
        repeat_count=scan_input_repeat_count,
        profile_frames=frames,
        profile_directory=profile_dir,
    )
    return {
        "schema_version": TAIL_LATENCY_PERFORMANCE_SCHEMA_VERSION,
        "input": {
            **input_summary,
            "episode_evidence": _load_episode_evidence(Path(source)),
        },
        "scan_input_comparison": {
            "reference": _compact_pipeline_result(reference),
            "optimized": _compact_pipeline_result(optimized),
            "acceptance": acceptance,
            "passed": all(acceptance.values()),
            "interleaved_distribution": timing_distribution,
        },
        "fusion_tail_attribution": _fusion_tail_attribution(
            optimized["fusion_tail_rows"],
            reference["fusion_profile"],
            optimized["fusion_cumulative_diagnostics"],
        ),
        "constraints": {
            "buffer_horizon_changed": False,
            "observation_drop_enabled": False,
            "scan_frequency_changed": False,
            "association_gate_changed": False,
            "online_truth_use_count": input_summary["online_truth_use_count"],
            "replay_execution_is_clean_full_stack_evidence": False,
            "replay_execution_scope": "current_uncommitted_d1_worktree",
            "airsim_evidence": False,
            "formal_multi_seed_evidence": False,
            "real_time_release_evidence": False,
        },
    }


def load_frozen_sensor_frames(
    source: str | Path,
) -> tuple[tuple[SensorScanFrame, ...], dict[str, Any]]:
    path = Path(source)
    frames: list[SensorScanFrame] = []
    observation_count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record.get("topic") != "sensor.observations":
                continue
            payload = record["payload"]
            observations = sensor_observations_from_online_batch(payload)
            frame = SensorScanFrame.from_observations(
                observations,
                scan_id=str(payload["batch_id"]),
            )
            frames.append(frame)
            observation_count += len(frame.observations)
    if not frames:
        raise ValueError("frozen source contains no sensor.observations records")
    return tuple(frames), {
        "source_path": str(path),
        "source_sha256": _sha256_file(path),
        "input_batch_count": len(frames),
        "input_observation_count": observation_count,
        "online_truth_use_count": 0,
    }


def write_tail_latency_report(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_destination.write_text(
        render_tail_latency_report_cn(report),
        encoding="utf-8",
    )


def render_tail_latency_report_cn(report: Mapping[str, Any]) -> str:
    source = report["input"]
    evidence = source["episode_evidence"]
    comparison = report["scan_input_comparison"]
    reference = comparison["reference"]
    optimized = comparison["optimized"]
    distribution = comparison["interleaved_distribution"]
    fusion = report["fusion_tail_attribution"]
    profile = fusion["profile_selected_functions"]
    scan_profiles = distribution.get("profile_selected_functions", {})
    baseline = evidence.get("stage_timings", {})
    lines = [
        "# D1 nominal 200v200 尾延时归因与扫描输入复用验证",
        "",
        "## 证据边界",
        "",
        f"- 冻结输入：`{source['source_path']}`",
        f"- SHA-256：`{source['source_sha256']}`",
        f"- commit：`{evidence.get('git_commit')}`；clean："
        f"`{not bool(evidence.get('repository_dirty', True))}`",
        f"- 场景：`{evidence.get('scenario_version')}`，seed "
        f"`{evidence.get('seed')}`，{source['input_batch_count']:,} scans / "
        f"{source['input_observation_count']:,} observations。",
        "- 复现入口：`scripts/run_tail_latency_performance.py`；JSON 内记录输入哈希、"
        "交错轮数、扫描数、操作计数、profile 选择项与证据路径。",
        "- 本报告使用冻结三维质点 replay，不是 AirSim、正式多 seed 或实时放行证据。",
        "- clean/commit 只描述冻结输入来源；优化与等价复放运行在当前未提交 D1 "
        "工作区，不是新的 clean full-stack 放行。",
        "",
        "clean episode 原始阶段分位为：D1 fusion "
        f"P50/P95/max `{_stage_triplet(baseline.get('d1_fusion'))} ms`；"
        "scan-input P50/P95/max "
        f"`{_stage_triplet(baseline.get('d1_scan_input'))} ms`。",
        "",
        "## Scan-input 低风险优化",
        "",
        "旧路径在 `SensorScanFrame` 已完成只读深快照、truth/covariance/时间戳/lineage "
        "校验后，organizer 又重建同一帧。新路径先核对轻量完整性封印；帧内对象或标量被替换、"
        "数组恢复可写时回退原完整重建和 fail-closed 校验。",
        "",
        "| 操作数 | 旧路径 | 新路径 |",
        "| --- | ---: | ---: |",
        "| 已验证帧直接复用 | "
        f"{reference['scan_input_performance_diagnostics']['validated_frame_reuse_count']:,} | "
        f"{optimized['scan_input_performance_diagnostics']['validated_frame_reuse_count']:,} |",
        "| organizer 内帧重建 | "
        f"{reference['scan_input_performance_diagnostics']['iterable_frame_build_count']:,} | "
        f"{optimized['scan_input_performance_diagnostics']['iterable_frame_build_count']:,} |",
        "| organizer 内 observation 再快照 | "
        f"{reference['scan_input_performance_diagnostics']['organizer_observation_snapshot_count']:,} | "
        f"{optimized['scan_input_performance_diagnostics']['organizer_observation_snapshot_count']:,} |",
        "",
        f"严格等价验收：`{comparison['passed']}`。逐输入 organizer 结果、逐 fusion posterior、"
        "物化 GlobalTrack、终态、一致性证据、完整 operation totals 和累计诊断均逐项一致。",
        "",
        f"前 {distribution['scan_count']} scans 交错 "
        f"{distribution['repeat_count']} 轮的总耗时 P50/P95：旧路径 "
        f"`{distribution['reference']['p50_s']:.3f}/"
        f"{distribution['reference']['p95_s']:.3f} s`，新路径 "
        f"`{distribution['optimized']['p50_s']:.3f}/"
        f"{distribution['optimized']['p95_s']:.3f} s`。墙钟不参与通过判定。",
        "",
        "| Scan-input 调用链 | 旧路径 cProfile 累计 / s | 新路径 cProfile 累计 / s |",
        "| --- | ---: | ---: |",
    ]
    for function_name in (
        "assert_online_observations_identity_free",
        "SensorScanFrame.__post_init__",
        "SensorObservation.__post_init__",
        "ScanInputOrganizer.ingest",
        "_snapshot_observation",
        "_frame_snapshot_is_intact",
        "_claim_for_frame",
        "_digest",
        "_json_safe",
    ):
        reference_item = scan_profiles.get("reference", {}).get(function_name, {})
        optimized_item = scan_profiles.get("optimized", {}).get(function_name, {})
        lines.append(
            f"| `{function_name}` | "
            f"{float(reference_item.get('cumulative_time_s', 0.0)):.3f} | "
            f"{float(optimized_item.get('cumulative_time_s', 0.0)):.3f} |"
        )
    lines.extend(
        [
            "",
            "## Fusion 归因",
            "",
            f"工作区复放分位 P50/P95/max 为 "
            f"`{fusion['overall']['p50_ms']:.3f}/"
            f"{fusion['overall']['p95_ms']:.3f}/"
            f"{fusion['overall']['max_ms']:.3f} ms`。该绝对值受当次主机负载影响，"
            "只用于与同轮操作数和调用链配对。",
            "",
            "| 路径 | cProfile 累计 / s | 调用数 |",
            "| --- | ---: | ---: |",
        ]
    )
    for function_name in (
        "_scan_one_to_one_assignments",
        "_cached_non_radar_scan_cost_matrix",
        "global_tracks",
        "_to_global_track",
        "_replay_record",
        "_state_at",
        "_state_from_complete_replay_checkpoints",
        "_prune_record",
    ):
        item = profile.get(function_name, {})
        lines.append(
            f"| `{function_name}` | "
            f"{float(item.get('cumulative_time_s', 0.0)):.3f} | "
            f"{int(item.get('primitive_call_count', 0)):,} |"
        )
    radar = fusion["by_modality"].get("radar", {})
    materialized = fusion["by_materialization"].get("true", {})
    state_only = fusion["by_materialization"].get("false", {})
    candidate_peak = fusion["peak_candidate_pair_scan"]
    rebase_peak = fusion["peak_fixed_lag_rebase_scan"]
    lines.extend(
        [
            "",
            f"radar scans 共 {int(radar.get('count', 0))} 次，P95 "
            f"`{float(radar.get('p95_ms', 0.0)):.3f} ms`；物化扫描共 "
            f"{int(materialized.get('count', 0))} 次，P95 "
            f"`{float(materialized.get('p95_ms', 0.0)):.3f} ms`。候选对峰值扫描含 "
            f"{int(candidate_peak['observation_count'])} 条 "
            f"{candidate_peak['modality']} observation、"
            f"{int(candidate_peak['current_track_count'])} 条航迹与 "
            f"{int(candidate_peak['association_candidate_pair_count']):,} 个 candidate "
            f"pairs；rebase 峰值为单扫描 "
            f"{int(rebase_peak['fixed_lag_rebase_count'])} 次。若同一扫描还物化 "
            "GlobalTrack，成本进一步叠加。",
            "",
            "本轮不修改 fusion 数学路径。检查点状态查询已使用完整 replay checkpoint 直接查询，"
            f"同 fusion timestamp 已保持 {int(state_only.get('count', 0))} 次 state-only / "
            f"{int(materialized.get('count', 0))} 次完整物化。继续压缩 "
            "GlobalTrack 共享 audit metadata 或 radar/rebase 路径需要独立合同设计，不能以"
            "缩短窗口、丢观测、降频、放宽门控或 truth 换取性能。",
            "",
        ]
    )
    return "\n".join(lines)


def _run_pipeline_variant(
    frames: Sequence[SensorScanFrame],
    *,
    variant: str,
    resnapshot_existing_frames: bool,
    fusion_profile_path: Path | None = None,
    capture_tail_rows: bool,
) -> dict[str, Any]:
    organizer = ScanInputOrganizer()
    adapter = Scalable3DFusionAdapter()
    scan_input_digests: list[str] = []
    fusion_digests: list[str] = []
    fusion_operation_snapshots: list[dict[str, int]] = []
    fusion_diagnostic_snapshots: list[dict[str, Any]] = []
    fusion_operation_totals = {name: 0 for name in _FUSION_OPERATION_FIELDS}
    fusion_tail_rows: list[dict[str, Any]] = []
    release_group_sizes: list[int] = []
    last_materialized_tracks: Sequence[Any] | None = None
    prior_diagnostics = adapter.fusion_performance_diagnostics().to_dict()
    profiler = cProfile.Profile() if fusion_profile_path is not None else None

    def consume(scans: Sequence[SensorScanFrame]) -> None:
        nonlocal last_materialized_tracks, prior_diagnostics
        group = tuple(scans)
        if not group:
            return
        group_index = len(release_group_sizes)
        release_group_sizes.append(len(group))
        for index, scan in enumerate(group):
            fusion_timestamp = max(
                float(adapter.current_time),
                float(scan.arrival_timestamp),
            )
            next_timestamp = (
                None
                if index + 1 == len(group)
                else max(
                    fusion_timestamp,
                    float(group[index + 1].arrival_timestamp),
                )
            )
            materialize_tracks = bool(
                next_timestamp is None
                or next_timestamp > fusion_timestamp + 1.0e-9
            )
            started = perf_counter()
            if profiler is not None:
                profiler.enable()
            result = adapter.process_scan_batch(
                scan.observations,
                materialize_tracks=materialize_tracks,
            )
            if profiler is not None:
                profiler.disable()
            elapsed_ms = (perf_counter() - started) * 1000.0
            summary = result.summary.to_dict()
            operation_snapshot = {
                name: int(summary[name])
                for name in _FUSION_OPERATION_FIELDS
            }
            fusion_operation_snapshots.append(operation_snapshot)
            for name in _FUSION_OPERATION_FIELDS:
                fusion_operation_totals[name] += operation_snapshot[name]
            diagnostics = adapter.fusion_performance_diagnostics().to_dict()
            fusion_diagnostic_snapshots.append(dict(diagnostics))
            if capture_tail_rows:
                delta = {
                    name: int(diagnostics[name]) - int(prior_diagnostics[name])
                    for name in _FUSION_DIAGNOSTIC_DELTA_FIELDS
                }
                fusion_tail_rows.append(
                    {
                        "elapsed_ms": elapsed_ms,
                        "group_index": group_index,
                        "group_size": len(group),
                        "index_in_group": index,
                        "materialized": materialize_tracks,
                        "sensor_id": scan.sensor_id,
                        "modality": scan.modality,
                        "measurement_timestamp": scan.measurement_timestamp,
                        "arrival_timestamp": scan.arrival_timestamp,
                        "observation_count": len(scan.observations),
                        "current_track_count": diagnostics["current_track_count"],
                        "accepted_observation_count": summary[
                            "accepted_observation_count"
                        ],
                        **delta,
                    }
                )
            prior_diagnostics = diagnostics
            fusion_digests.append(
                _coalesced_scan_semantic_digest(adapter, result)
            )
            if materialize_tracks:
                last_materialized_tracks = result.tracks

    for frame in frames:
        result = _ingest_variant(
            organizer,
            frame,
            resnapshot_existing_frames=resnapshot_existing_frames,
        )
        scan_input_digests.append(_json_sha256(result.to_dict()))
        consume(result.released_scans)
    close_result = organizer.close()
    close_digest = _json_sha256(close_result.to_dict())
    consume(close_result.released_scans)

    if last_materialized_tracks is None:
        raise ValueError("tail-latency pipeline produced no materialized tracks")
    fusion_profile = None
    if profiler is not None and fusion_profile_path is not None:
        fusion_profile_path.parent.mkdir(parents=True, exist_ok=True)
        profiler.dump_stats(str(fusion_profile_path))
        fusion_profile = _fusion_profile_summary(fusion_profile_path)
    return {
        "variant": variant,
        "resnapshot_existing_frames": resnapshot_existing_frames,
        "scan_input_digests": scan_input_digests,
        "scan_input_digests_sha256": _json_sha256(scan_input_digests),
        "scan_input_close_digest": close_digest,
        "scan_input_audit": organizer.audit_summary().to_dict(),
        "scan_input_performance_diagnostics": organizer.performance_diagnostics(),
        "release_group_sizes": release_group_sizes,
        "fusion_digests": fusion_digests,
        "fusion_digests_sha256": _json_sha256(fusion_digests),
        "fusion_operation_snapshots": fusion_operation_snapshots,
        "fusion_operation_snapshots_sha256": _json_sha256(
            fusion_operation_snapshots
        ),
        "fusion_diagnostic_snapshots": fusion_diagnostic_snapshots,
        "fusion_diagnostic_snapshots_sha256": _json_sha256(
            fusion_diagnostic_snapshots
        ),
        "fusion_operation_totals": fusion_operation_totals,
        "fusion_cumulative_diagnostics": (
            adapter.fusion_performance_diagnostics().to_dict()
        ),
        "final_tracks_sha256": _json_sha256(
            _semantic_track_snapshot(last_materialized_tracks)
        ),
        "consistency_evidence_sha256": _json_sha256(
            [item.to_dict() for item in adapter.consistency_evidence_records()]
        ),
        "fusion_tail_rows": fusion_tail_rows,
        "fusion_profile": fusion_profile,
    }


def _ingest_variant(
    organizer: ScanInputOrganizer,
    frame: SensorScanFrame,
    *,
    resnapshot_existing_frames: bool,
) -> Any:
    if resnapshot_existing_frames:
        return organizer.ingest(frame.observations, scan_id=frame.scan_id)
    return organizer.ingest(frame)


def _equivalence_acceptance(
    reference: Mapping[str, Any],
    optimized: Mapping[str, Any],
    *,
    input_summary: Mapping[str, Any],
) -> dict[str, bool]:
    reference_diagnostics = reference["scan_input_performance_diagnostics"]
    optimized_diagnostics = optimized["scan_input_performance_diagnostics"]
    frame_count = int(input_summary["input_batch_count"])
    observation_count = int(input_summary["input_observation_count"])
    return {
        "per_input_scan_result_equivalence": (
            optimized["scan_input_digests"] == reference["scan_input_digests"]
        ),
        "scan_input_close_result_equivalence": (
            optimized["scan_input_close_digest"]
            == reference["scan_input_close_digest"]
        ),
        "scan_input_audit_equivalence": (
            optimized["scan_input_audit"] == reference["scan_input_audit"]
        ),
        "release_group_schedule_equivalence": (
            optimized["release_group_sizes"] == reference["release_group_sizes"]
        ),
        "per_fusion_state_covariance_timestamp_lineage_level_equivalence": (
            optimized["fusion_digests"] == reference["fusion_digests"]
        ),
        "fusion_operation_totals_equivalence": (
            optimized["fusion_operation_totals"]
            == reference["fusion_operation_totals"]
        ),
        "per_fusion_operation_counts_equivalence": (
            optimized["fusion_operation_snapshots"]
            == reference["fusion_operation_snapshots"]
        ),
        "per_fusion_cumulative_diagnostics_equivalence": (
            optimized["fusion_diagnostic_snapshots"]
            == reference["fusion_diagnostic_snapshots"]
        ),
        "fusion_cumulative_diagnostics_equivalence": (
            optimized["fusion_cumulative_diagnostics"]
            == reference["fusion_cumulative_diagnostics"]
        ),
        "final_global_track_equivalence": (
            optimized["final_tracks_sha256"] == reference["final_tracks_sha256"]
        ),
        "consistency_evidence_equivalence": (
            optimized["consistency_evidence_sha256"]
            == reference["consistency_evidence_sha256"]
        ),
        "reference_resnapshots_every_frame": (
            int(reference_diagnostics["iterable_frame_build_count"])
            == frame_count
            and int(
                reference_diagnostics["organizer_observation_snapshot_count"]
            )
            == observation_count
        ),
        "optimized_reuses_every_intact_frame": (
            int(optimized_diagnostics["validated_frame_reuse_count"])
            == frame_count
            and int(optimized_diagnostics["mutated_frame_rebuild_count"]) == 0
            and int(optimized_diagnostics["iterable_frame_build_count"]) == 0
            and int(
                optimized_diagnostics["organizer_observation_snapshot_count"]
            )
            == 0
        ),
        "online_truth_use_count_zero": (
            int(input_summary["online_truth_use_count"]) == 0
        ),
    }


def _compact_pipeline_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "variant",
            "resnapshot_existing_frames",
            "scan_input_digests_sha256",
            "scan_input_close_digest",
            "scan_input_audit",
            "scan_input_performance_diagnostics",
            "release_group_sizes",
            "fusion_digests_sha256",
            "fusion_operation_snapshots_sha256",
            "fusion_diagnostic_snapshots_sha256",
            "fusion_operation_totals",
            "fusion_cumulative_diagnostics",
            "final_tracks_sha256",
            "consistency_evidence_sha256",
        )
    }


def _interleaved_scan_input_distribution(
    frames: Sequence[SensorScanFrame],
    *,
    repeat_count: int,
    profile_frames: Sequence[SensorScanFrame],
    profile_directory: Path | None,
) -> dict[str, Any]:
    _time_scan_input_variant(frames, resnapshot_existing_frames=True)
    _time_scan_input_variant(frames, resnapshot_existing_frames=False)
    samples: dict[str, list[float]] = {"reference": [], "optimized": []}
    per_call: dict[str, list[float]] = {"reference": [], "optimized": []}
    for repeat_index in range(repeat_count):
        order = (
            ("reference", True),
            ("optimized", False),
        )
        if repeat_index % 2:
            order = tuple(reversed(order))
        for name, resnapshot in order:
            result = _time_scan_input_variant(
                frames,
                resnapshot_existing_frames=resnapshot,
            )
            samples[name].append(result["total_wall_time_s"])
            per_call[name].extend(result["per_call_wall_time_ms"])
    result = {
        "scan_count": len(frames),
        "observation_count": sum(len(frame.observations) for frame in frames),
        "repeat_count": repeat_count,
        "execution_order": "alternating_reference_optimized",
        "reference": _distribution_summary(samples["reference"], suffix="s"),
        "optimized": _distribution_summary(samples["optimized"], suffix="s"),
        "reference_per_call": _distribution_summary(
            per_call["reference"],
            suffix="ms",
        ),
        "optimized_per_call": _distribution_summary(
            per_call["optimized"],
            suffix="ms",
        ),
        "p50_speedup": (
            float(np.quantile(samples["reference"], 0.5))
            / float(np.quantile(samples["optimized"], 0.5))
        ),
        "wall_time_used_for_acceptance": False,
    }
    if profile_directory is not None:
        profile_directory.mkdir(parents=True, exist_ok=True)
        profiles = {}
        for name, resnapshot in (
            ("reference", True),
            ("optimized", False),
        ):
            path = profile_directory / f"d1_scan_input_{name}.prof"
            profiles[name] = _profile_scan_input_variant(
                profile_frames,
                resnapshot_existing_frames=resnapshot,
                profile_path=path,
            )
        result["profile_selected_functions"] = {
            name: profile["selected_functions"]
            for name, profile in profiles.items()
        }
        result["profile_total_time_s"] = {
            name: profile["profile_total_time_s"]
            for name, profile in profiles.items()
        }
        result["profile_paths"] = {
            name: profile["profile_path"]
            for name, profile in profiles.items()
        }
        result["profile_timing_used_for_acceptance"] = False
    return result


def _time_scan_input_variant(
    frames: Sequence[SensorScanFrame],
    *,
    resnapshot_existing_frames: bool,
) -> dict[str, Any]:
    organizer = ScanInputOrganizer()
    per_call: list[float] = []
    started_total = perf_counter()
    for frame in frames:
        started = perf_counter()
        _ingest_variant(
            organizer,
            frame,
            resnapshot_existing_frames=resnapshot_existing_frames,
        )
        per_call.append((perf_counter() - started) * 1000.0)
    organizer.close()
    total = perf_counter() - started_total
    return {
        "total_wall_time_s": total,
        "per_call_wall_time_ms": per_call,
        "performance_diagnostics": organizer.performance_diagnostics(),
    }


def _profile_scan_input_variant(
    frames: Sequence[SensorScanFrame],
    *,
    resnapshot_existing_frames: bool,
    profile_path: Path,
) -> dict[str, Any]:
    profiler = cProfile.Profile()
    profiler.enable()
    _time_scan_input_variant(
        frames,
        resnapshot_existing_frames=resnapshot_existing_frames,
    )
    profiler.disable()
    profiler.dump_stats(str(profile_path))
    return _scan_input_profile_summary(profile_path)


def _fusion_tail_attribution(
    rows: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any] | None,
    cumulative_diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("fusion tail attribution requires unprofiled rows")
    modalities = sorted({str(row["modality"]) for row in rows})
    values = np.asarray([float(row["elapsed_ms"]) for row in rows], dtype=float)
    correlations: dict[str, float | None] = {}
    for name in (
        "observation_count",
        "current_track_count",
        "checkpoint_state_query_count",
        "fixed_lag_rebase_count",
        "global_track_materialization_count",
        "association_candidate_pair_count",
        "association_innovation_solve_count",
        "replay_checkpoint_reuse_count",
        "replay_filter_update_count",
        "cached_consistency_refresh_count",
    ):
        series = np.asarray([float(row[name]) for row in rows], dtype=float)
        correlations[name] = (
            None
            if float(np.std(series)) == 0.0
            else float(np.corrcoef(values, series)[0, 1])
        )
    return {
        "overall": _row_timing_summary(rows),
        "by_modality": {
            modality: _row_timing_summary(
                [row for row in rows if row["modality"] == modality]
            )
            for modality in modalities
        },
        "by_materialization": {
            str(flag).lower(): _row_timing_summary(
                [row for row in rows if bool(row["materialized"]) is flag]
            )
            for flag in (False, True)
        },
        "correlation_with_elapsed": correlations,
        "top_20": sorted(
            (dict(row) for row in rows),
            key=lambda row: float(row["elapsed_ms"]),
            reverse=True,
        )[:20],
        "peak_candidate_pair_scan": dict(
            max(
                rows,
                key=lambda row: int(row["association_candidate_pair_count"]),
            )
        ),
        "peak_fixed_lag_rebase_scan": dict(
            max(rows, key=lambda row: int(row["fixed_lag_rebase_count"]))
        ),
        "cumulative_diagnostics": dict(cumulative_diagnostics),
        "profile_selected_functions": (
            {} if profile is None else dict(profile["selected_functions"])
        ),
        "profile_total_time_s": (
            None if profile is None else profile["profile_total_time_s"]
        ),
        "profile_timing_used_as_wall_clock_evidence": False,
    }


def _row_timing_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    values = [float(row["elapsed_ms"]) for row in rows]
    result = _distribution_summary(values, suffix="ms")
    result["count"] = len(rows)
    result["sum_s"] = float(sum(values) / 1000.0)
    return result


def _distribution_summary(
    values: Sequence[float],
    *,
    suffix: str,
) -> dict[str, float | int]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        raise ValueError("distribution requires at least one value")
    return {
        "sample_count": int(array.size),
        f"mean_{suffix}": float(np.mean(array)),
        f"p50_{suffix}": float(np.quantile(array, 0.50)),
        f"p95_{suffix}": float(np.quantile(array, 0.95)),
        f"max_{suffix}": float(np.max(array)),
    }


def _fusion_profile_summary(path: Path) -> dict[str, Any]:
    selected_names = {
        "process_scan_batch",
        "_scan_one_to_one_assignments",
        "_radar_scan_cost_matrix",
        "_cached_non_radar_scan_cost_matrix",
        "_batched_non_radar_scan_cost_matrix",
        "_state_at",
        "_state_from_complete_replay_checkpoints",
        "_replay_record",
        "_prune_record",
        "_filter_update",
        "global_tracks",
        "_to_global_track",
        "covariance_a95",
    }
    return _profile_summary(path, selected_names=selected_names)


def _scan_input_profile_summary(path: Path) -> dict[str, Any]:
    stats = pstats.Stats(str(path)).strip_dirs()
    selected: dict[str, dict[str, float | int]] = {}
    for (filename, line_number, function_name), values in stats.stats.items():
        for label, expected_file, expected_name, minimum_line, maximum_line in (
            _SCAN_INPUT_PROFILE_SPECS
        ):
            if not filename.endswith(expected_file) or function_name != expected_name:
                continue
            if minimum_line is not None and line_number < minimum_line:
                continue
            if maximum_line is not None and line_number >= maximum_line:
                continue
            _accumulate_profile_entry(selected, label, values)
    return {
        "profile_path": str(path),
        "profile_total_time_s": float(stats.total_tt),
        "selected_functions": selected,
    }


def _profile_summary(
    path: Path,
    *,
    selected_names: set[str],
) -> dict[str, Any]:
    stats = pstats.Stats(str(path)).strip_dirs()
    selected: dict[str, dict[str, float | int]] = {}
    for (_, _, function_name), values in stats.stats.items():
        if function_name not in selected_names:
            continue
        _accumulate_profile_entry(selected, function_name, values)
    return {
        "profile_path": str(path),
        "profile_total_time_s": float(stats.total_tt),
        "selected_functions": selected,
    }


def _accumulate_profile_entry(
    selected: dict[str, dict[str, float | int]],
    label: str,
    values: tuple[Any, ...],
) -> None:
    primitive_calls, total_calls, total_time, cumulative_time, _ = values
    entry = selected.setdefault(
        label,
        {
            "primitive_call_count": 0,
            "total_call_count": 0,
            "total_time_s": 0.0,
            "cumulative_time_s": 0.0,
        },
    )
    entry["primitive_call_count"] += int(primitive_calls)
    entry["total_call_count"] += int(total_calls)
    entry["total_time_s"] += float(total_time)
    entry["cumulative_time_s"] += float(cumulative_time)


def _load_episode_evidence(source: Path) -> dict[str, Any]:
    episode_directory = source.parent
    manifest_path = episode_directory / "manifest.json"
    summary_path = episode_directory / "summary.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.exists()
        else {}
    )
    stage_timings = (
        summary.get("module_final_diagnostics", {}).get("stage_timings", {})
    )
    return {
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "summary_path": str(summary_path) if summary_path.exists() else None,
        "git_commit": manifest.get("git_commit"),
        "repository_dirty": manifest.get("repository_dirty"),
        "scenario_name": summary.get("scenario_name", manifest.get("scenario_name")),
        "scenario_version": summary.get(
            "scenario_version",
            manifest.get("scenario_version"),
        ),
        "seed": summary.get("seed", manifest.get("seed")),
        "simulated_duration_s": summary.get("simulated_duration_s"),
        "target_count": summary.get("target_count"),
        "resource_count": summary.get("resource_count"),
        "stage_timings": {
            name: stage_timings.get(name)
            for name in ("d1_fusion", "d1_scan_input")
        },
    }


def _stage_triplet(value: Mapping[str, Any] | None) -> str:
    if not value:
        return "unavailable"
    return (
        f"{float(value['p50_wall_time_ms']):.3f}/"
        f"{float(value['p95_wall_time_ms']):.3f}/"
        f"{float(value['max_wall_time_ms']):.3f}"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
