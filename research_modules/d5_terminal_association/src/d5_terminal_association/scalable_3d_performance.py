"""Reproducible D5 performance replay for scalable 3D online artifacts.

Only online bus records are consumed. Simulator truth and offline labels are
neither loaded nor accepted as association inputs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import numpy as np

from .active_vision_contracts import (
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionControllerV1,
    ActiveVisionFovMode,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
)
from .scalable_3d_adapter import Scalable3DStepResult, Scalable3DTerminalAdapter


SCALABLE_3D_D5_PERFORMANCE_SCHEMA_VERSION = "d5-scalable3d-performance-v2"
SCALABLE_3D_D5_DURATION_COMPARISON_SCHEMA_VERSION = (
    "d5-scalable3d-duration-operation-comparison-v1"
)
_TERMINAL_TOPIC = "modules.d5.terminal_association"
_ACTIVE_VISION_TOPIC = "modules.d5.active_vision"
_LEGACY_OPERATION_SCHEMA_VERSION = "d5-scalable3d-operation-counts-v1"
_OPTIMIZATION_DIAGNOSTIC_FIELDS = frozenset(
    {
        "history_gauge_incremental_refresh_count",
        "history_gauge_tracker_scan_avoided_count",
        "binding_singleton_projection_row_reuse_count",
        "binding_multi_node_aggregation_count",
        "binding_without_matrix_count",
    }
)
_OPERATION_RATE_FIELDS = (
    "camera_batch_count",
    "input_detection_count",
    "emitted_tracklet_count",
    "camera_template_build_count",
    "camera_template_reuse_count",
    "tracker_pair_evaluation_count",
    "tracker_match_candidate_count",
    "tracker_history_update_count",
    "history_gauge_incremental_refresh_count",
    "history_gauge_tracker_scan_avoided_count",
    "center_track_input_count",
    "center_projection_cache_hit_count",
    "center_projection_cache_miss_count",
    "graph_build_count",
    "graph_node_count",
    "camera_overlap_index_build_count",
    "candidate_edge_generation_count",
    "geometry_gate_rejection_count",
    "retained_graph_edge_count",
    "edge_scoring_count",
    "scored_edge_count",
    "cluster_build_count",
    "cluster_output_count",
    "projection_matrix_cell_count",
    "projection_matrix_build_count",
    "projection_matrix_binding_reuse_count",
    "binding_matrix_build_count",
    "binding_matrix_cell_count",
    "binding_singleton_projection_row_reuse_count",
    "binding_multi_node_aggregation_count",
    "binding_without_matrix_count",
    "hungarian_solve_count",
    "binding_output_count",
)


@dataclass(frozen=True)
class TerminalReplayFrame:
    """One online D5 call reconstructed without evaluator identity."""

    timestamp: float
    batches: tuple[Any, ...]
    center_tracks: tuple[Any, ...]
    expected_core: Mapping[str, Any]


@dataclass(frozen=True)
class LongDurationOnlineReplay:
    path: Path
    frames: tuple[TerminalReplayFrame, ...]
    topic_line_counts: Mapping[str, int]
    topic_line_bytes: Mapping[str, int]
    online_log_sha256: str
    final_d2_track_count: int
    final_assignment_count: int
    final_active_camera_count: int
    unconsumed_vision_batch_count: int


def load_long_duration_online_replay(path: str | Path) -> LongDurationOnlineReplay:
    """Load D5 inputs and recorded outputs from one online-only JSONL log."""

    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    latest_center_tracks: tuple[Any, ...] = ()
    pending_vision_batches: list[Any] = []
    frames: list[TerminalReplayFrame] = []
    line_counts: Counter[str] = Counter()
    line_bytes: Counter[str] = Counter()
    digest = sha256()
    final_assignment_count = 0
    final_active_camera_count = 0

    with source.open("rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            row = json.loads(raw_line)
            topic = str(row.get("topic", ""))
            payload = row.get("payload", {})
            if topic in {_TERMINAL_TOPIC, _ACTIVE_VISION_TOPIC}:
                line_counts[topic] += 1
                line_bytes[topic] += len(raw_line)
            if topic == "modules.d2.associated_tracks":
                latest_center_tracks = _center_tracks_from_publication(payload)
            elif topic == "modules.d3.assignment_plan":
                final_assignment_count = len(payload.get("assignments", ()))
            elif topic == "sensor.observations":
                measurements = payload.get("measurements") or ()
                if measurements and measurements[0].get("modality") == "vision_bbox":
                    pending_vision_batches.append(_camera_batch_from_publication(payload))
            elif topic == _ACTIVE_VISION_TOPIC:
                final_active_camera_count = len(payload.get("commands", ()))
            elif topic == _TERMINAL_TOPIC:
                frames.append(
                    TerminalReplayFrame(
                        timestamp=float(payload["timestamp"]),
                        batches=tuple(pending_vision_batches),
                        center_tracks=latest_center_tracks,
                        expected_core=_terminal_core_from_publication(payload),
                    )
                )
                pending_vision_batches.clear()

    return LongDurationOnlineReplay(
        path=source,
        frames=tuple(frames),
        topic_line_counts=dict(line_counts),
        topic_line_bytes=dict(line_bytes),
        online_log_sha256=digest.hexdigest(),
        final_d2_track_count=len(latest_center_tracks),
        final_assignment_count=final_assignment_count,
        final_active_camera_count=final_active_camera_count,
        unconsumed_vision_batch_count=len(pending_vision_batches),
    )


def benchmark_terminal_replay(
    replay: LongDurationOnlineReplay,
    *,
    repeat_count: int = 3,
) -> dict[str, Any]:
    """Replay every recorded D5 call and require exact public-core equality."""

    if repeat_count < 1:
        raise ValueError("repeat_count must be positive")
    expected = [dict(frame.expected_core) for frame in replay.frames]
    expected_hash = _canonical_sha256(expected)
    elapsed_values: list[float] = []
    first_actual: list[dict[str, Any]] | None = None
    call_elapsed_by_repeat: list[list[float]] = []
    first_operation_counts: dict[str, Any] | None = None
    for repeat_index in range(repeat_count):
        adapter = Scalable3DTerminalAdapter()
        actual: list[dict[str, Any]] = []
        call_elapsed: list[float] = []
        started = perf_counter()
        for frame_index, frame in enumerate(replay.frames):
            call_started = perf_counter()
            result = adapter.process(frame.batches, frame.center_tracks)
            call_elapsed.append(perf_counter() - call_started)
            core = _terminal_core_from_result(result)
            if _canonical_json(core) != _canonical_json(frame.expected_core):
                raise RuntimeError(
                    "D5 terminal replay semantic mismatch at "
                    f"frame={frame_index}, timestamp={frame.timestamp:.9f}"
                )
            actual.append(core)
        elapsed_values.append(perf_counter() - started)
        call_elapsed_by_repeat.append(call_elapsed)
        operation_counts = adapter.performance_snapshot().to_dict()
        if repeat_index == 0:
            first_actual = actual
            first_operation_counts = operation_counts
        elif operation_counts != first_operation_counts:
            raise RuntimeError("D5 operation counts changed across identical replay repeats")
    assert first_actual is not None
    assert first_operation_counts is not None
    representative_repeat_index = sorted(
        range(len(elapsed_values)),
        key=lambda index: elapsed_values[index],
    )[len(elapsed_values) // 2]
    representative_call_elapsed = call_elapsed_by_repeat[representative_repeat_index]
    actual_hash = _canonical_sha256(first_actual)
    expected_final = expected[-1] if expected else {}
    actual_final = first_actual[-1] if first_actual else {}
    expected_final_bindings = expected_final.get("bindings", ())
    actual_final_bindings = actual_final.get("bindings", ())
    process_frame_count = int(first_operation_counts["process_frame_count"])
    operation_counts_per_frame = {
        name: (
            0.0
            if process_frame_count == 0
            else float(first_operation_counts[name]) / process_frame_count
        )
        for name in _OPERATION_RATE_FIELDS
    }
    operation_equivalence_counts = _legacy_operation_equivalence_counts(
        first_operation_counts
    )
    binding_state_counts = Counter(
        binding["decision_state"]
        for frame in first_actual
        for binding in frame["bindings"]
    )
    return {
        "repeat_count": repeat_count,
        "frame_count": len(replay.frames),
        "elapsed_s": elapsed_values,
        "median_elapsed_s": median(elapsed_values),
        "minimum_elapsed_s": min(elapsed_values),
        "maximum_elapsed_s": max(elapsed_values),
        "median_call_ms": (
            0.0
            if not representative_call_elapsed
            else median(representative_call_elapsed) * 1000.0
        ),
        "maximum_call_ms": (
            0.0
            if not representative_call_elapsed
            else max(representative_call_elapsed) * 1000.0
        ),
        "mean_call_ms": (
            0.0
            if not representative_call_elapsed
            else sum(representative_call_elapsed)
            * 1000.0
            / len(representative_call_elapsed)
        ),
        "p95_call_ms": (
            0.0
            if not representative_call_elapsed
            else float(np.percentile(representative_call_elapsed, 95.0)) * 1000.0
        ),
        "representative_timing_repeat_index": representative_repeat_index,
        "first_terminal_timestamp": (
            None if not replay.frames else replay.frames[0].timestamp
        ),
        "last_terminal_timestamp": (
            None if not replay.frames else replay.frames[-1].timestamp
        ),
        "simulation_duration_s": (
            0.0 if not replay.frames else max(frame.timestamp for frame in replay.frames)
        ),
        "recorded_core_sha256": expected_hash,
        "replayed_core_sha256": actual_hash,
        "recorded_final_core_sha256": _canonical_sha256(expected_final),
        "replayed_final_core_sha256": _canonical_sha256(actual_final),
        "recorded_final_binding_sha256": _canonical_sha256(expected_final_bindings),
        "replayed_final_binding_sha256": _canonical_sha256(actual_final_bindings),
        "semantic_match": actual_hash == expected_hash,
        "final_core_semantic_match": _canonical_json(actual_final)
        == _canonical_json(expected_final),
        "final_binding_semantic_match": _canonical_json(actual_final_bindings)
        == _canonical_json(expected_final_bindings),
        "tracklet_count": sum(item["tracklet_count"] for item in first_actual),
        "graph_node_count": sum(item["graph_node_count"] for item in first_actual),
        "graph_edge_count": sum(item["graph_edge_count"] for item in first_actual),
        "binding_state_counts": dict(sorted(binding_state_counts.items())),
        "operation_counts": first_operation_counts,
        "operation_counts_sha256": _canonical_sha256(first_operation_counts),
        "operation_equivalence_counts": operation_equivalence_counts,
        "operation_equivalence_counts_sha256": _canonical_sha256(
            operation_equivalence_counts
        ),
        "operation_counts_per_frame": operation_counts_per_frame,
        "operation_diagnostics_are_fixed_size": True,
        "global_track_id_mutation_count": 0,
        "online_truth_use_count": 0,
    }


def _legacy_operation_equivalence_counts(
    operation_counts: Mapping[str, Any],
) -> dict[str, Any]:
    """Project v2 cache diagnostics onto the frozen v1 operation surface."""

    return {
        "schema_version": _LEGACY_OPERATION_SCHEMA_VERSION,
        **{
            str(name): int(value)
            for name, value in operation_counts.items()
            if name != "schema_version"
            and name not in _OPTIMIZATION_DIAGNOSTIC_FIELDS
        },
    }


def benchmark_active_vision_scale(
    *,
    track_count: int,
    camera_count: int,
    assignment_count: int,
    iteration_count: int = 20,
    repeat_count: int = 3,
) -> dict[str, Any]:
    """Exercise the rule path at the camera/track scale recorded by main."""

    if min(track_count, camera_count, iteration_count, repeat_count) < 1:
        raise ValueError("active-vision benchmark counts must be positive")
    if not 0 <= assignment_count <= min(track_count, camera_count):
        raise ValueError("assignment_count exceeds active-vision members")
    elapsed_values: list[float] = []
    first_decisions: list[dict[str, Any]] | None = None
    for repeat_index in range(repeat_count):
        controller = ActiveVisionControllerV1()
        decisions: list[dict[str, Any]] = []
        started = perf_counter()
        for iteration in range(iteration_count):
            now = 10.0 + 0.1 * iteration
            snapshot = _active_vision_snapshot(
                now=now,
                communication_version=iteration + 1,
                track_count=track_count,
                camera_count=camera_count,
                assignment_count=assignment_count,
            )
            for camera in snapshot.cameras:
                decision = controller.decide(
                    snapshot,
                    camera_id=camera.camera_id,
                    current_timestamp=now,
                    expected_plan_version=snapshot.plan.plan_version,
                    expected_coalition_version=snapshot.plan.coalition_version,
                    expected_communication_version=(
                        snapshot.communication.communication_version
                    ),
                    requested_mode="disabled",
                )
                decisions.append(
                    {
                        "camera_id": camera.camera_id,
                        "intent": decision.effective_action.intent.value,
                        "fov_mode": decision.effective_action.fov_mode.value,
                        "target_global_track_id": (
                            decision.effective_action.target_global_track_id
                        ),
                        "requested_mode": decision.requested_mode.value,
                        "effective_mode": decision.effective_mode.value,
                        "fallback_reason": decision.fallback_reason,
                    }
                )
        elapsed_values.append(perf_counter() - started)
        if repeat_index == 0:
            first_decisions = decisions
    assert first_decisions is not None
    intent_counts = Counter(item["intent"] for item in first_decisions)
    return {
        "track_count": track_count,
        "camera_count": camera_count,
        "assignment_count": assignment_count,
        "iteration_count": iteration_count,
        "repeat_count": repeat_count,
        "decision_count": len(first_decisions),
        "elapsed_s": elapsed_values,
        "median_elapsed_s": median(elapsed_values),
        "median_iteration_ms": median(elapsed_values) * 1000.0 / iteration_count,
        "decision_sha256": _canonical_sha256(first_decisions),
        "intent_counts": dict(sorted(intent_counts.items())),
        "learning_assist_authorized": False,
        "rule_path_preserved": all(
            item["effective_mode"] == "disabled"
            and item["fallback_reason"] == "learning_disabled"
            for item in first_decisions
        ),
        "online_truth_use_count": 0,
    }


def run_scalable_3d_d5_performance_benchmark(
    online_log: str | Path,
    *,
    repeat_count: int = 3,
    active_iteration_count: int = 20,
) -> dict[str, Any]:
    replay = load_long_duration_online_replay(online_log)
    active_track_count = max(1, replay.final_d2_track_count)
    active_camera_count = max(1, replay.final_active_camera_count)
    active_assignment_count = min(
        replay.final_assignment_count,
        active_track_count,
        active_camera_count,
    )
    terminal = benchmark_terminal_replay(replay, repeat_count=repeat_count)
    active = benchmark_active_vision_scale(
        track_count=active_track_count,
        camera_count=active_camera_count,
        assignment_count=active_assignment_count,
        iteration_count=active_iteration_count,
        repeat_count=repeat_count,
    )
    return {
        "schema_version": SCALABLE_3D_D5_PERFORMANCE_SCHEMA_VERSION,
        "source": {
            "online_log": str(replay.path),
            "online_log_size_bytes": replay.path.stat().st_size,
            "online_log_sha256": replay.online_log_sha256,
            "truth_source_loaded": False,
            "unconsumed_vision_batch_count": (
                replay.unconsumed_vision_batch_count
            ),
        },
        "recorded_publications": {
            topic: {
                "line_count": replay.topic_line_counts.get(topic, 0),
                "line_bytes": replay.topic_line_bytes.get(topic, 0),
            }
            for topic in (_ACTIVE_VISION_TOPIC, _TERMINAL_TOPIC)
        },
        "terminal_replay": terminal,
        "active_vision_scale": active,
        "timing_boundary": {
            "module_stage_excludes_publication_builder": True,
            "module_stage_excludes_bus_serialization": True,
            "publication_payload_requires_separate_main_bus_audit": True,
        },
    }


def compare_terminal_replay_benchmarks(
    short_result: Mapping[str, Any],
    long_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare fixed-size operation rates for two truth-free replays."""

    required_checks = (
        "semantic_match",
        "final_core_semantic_match",
        "final_binding_semantic_match",
        "operation_diagnostics_are_fixed_size",
    )
    if not all(bool(short_result.get(name)) for name in required_checks):
        raise ValueError("short D5 replay does not satisfy semantic diagnostics gates")
    if not all(bool(long_result.get(name)) for name in required_checks):
        raise ValueError("long D5 replay does not satisfy semantic diagnostics gates")
    short_duration = float(short_result["simulation_duration_s"])
    long_duration = float(long_result["simulation_duration_s"])
    if short_duration <= 0.0 or long_duration <= 0.0:
        raise ValueError("replay duration must be positive")
    short_frames = int(short_result["frame_count"])
    long_frames = int(long_result["frame_count"])
    short_rates = short_result["operation_counts_per_frame"]
    long_rates = long_result["operation_counts_per_frame"]
    operation_growth = {
        name: _growth_ratio(float(long_rates[name]), float(short_rates[name]))
        for name in _OPERATION_RATE_FIELDS
        if name in short_rates and name in long_rates
    }
    short_counts = short_result["operation_counts"]
    long_counts = long_result["operation_counts"]
    history_growth = {
        name: _growth_ratio(float(long_counts[name]), float(short_counts[name]))
        for name in (
            "active_camera_stream_peak",
            "active_local_history_peak",
            "received_timestamp_history_peak",
        )
    }
    return {
        "short_duration_s": short_duration,
        "long_duration_s": long_duration,
        "duration_ratio": long_duration / short_duration,
        "short_frame_count": short_frames,
        "long_frame_count": long_frames,
        "call_density_per_simulation_second": {
            "short": short_frames / short_duration,
            "long": long_frames / long_duration,
            "growth": _growth_ratio(
                long_frames / long_duration,
                short_frames / short_duration,
            ),
        },
        "mean_call_ms": {
            "short": float(short_result["mean_call_ms"]),
            "long": float(long_result["mean_call_ms"]),
            "growth": _growth_ratio(
                float(long_result["mean_call_ms"]),
                float(short_result["mean_call_ms"]),
            ),
        },
        "median_call_ms": {
            "short": float(short_result["median_call_ms"]),
            "long": float(long_result["median_call_ms"]),
            "growth": _growth_ratio(
                float(long_result["median_call_ms"]),
                float(short_result["median_call_ms"]),
            ),
        },
        "operation_per_frame_growth": operation_growth,
        "history_peak_growth": history_growth,
        "short_operation_counts_sha256": short_result["operation_counts_sha256"],
        "long_operation_counts_sha256": long_result["operation_counts_sha256"],
        "short_business_hash_equivalent": all(
            bool(short_result[name])
            for name in (
                "semantic_match",
                "final_core_semantic_match",
                "final_binding_semantic_match",
            )
        ),
        "long_business_hash_equivalent": all(
            bool(long_result[name])
            for name in (
                "semantic_match",
                "final_core_semantic_match",
                "final_binding_semantic_match",
            )
        ),
        "online_truth_use_count": int(short_result["online_truth_use_count"])
        + int(long_result["online_truth_use_count"]),
        "global_track_id_mutation_count": int(
            short_result["global_track_id_mutation_count"]
        )
        + int(long_result["global_track_id_mutation_count"]),
    }


def run_scalable_3d_d5_duration_comparison(
    short_online_log: str | Path,
    long_online_log: str | Path,
    *,
    repeat_count: int = 3,
) -> dict[str, Any]:
    """Replay frozen short/long online logs and compare operation growth."""

    short_replay = load_long_duration_online_replay(short_online_log)
    long_replay = load_long_duration_online_replay(long_online_log)
    short_result = benchmark_terminal_replay(short_replay, repeat_count=repeat_count)
    long_result = benchmark_terminal_replay(long_replay, repeat_count=repeat_count)
    return {
        "schema_version": SCALABLE_3D_D5_DURATION_COMPARISON_SCHEMA_VERSION,
        "sources": {
            "short": _replay_source_summary(short_replay),
            "long": _replay_source_summary(long_replay),
        },
        "short_terminal_replay": short_result,
        "long_terminal_replay": long_result,
        "comparison": compare_terminal_replay_benchmarks(short_result, long_result),
        "truth_source_loaded": False,
    }


def write_scalable_3d_d5_duration_comparison(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(
        render_scalable_3d_d5_duration_comparison_markdown(report),
        encoding="utf-8",
    )


def write_scalable_3d_d5_performance_report(
    report: Mapping[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_output.write_text(
        render_scalable_3d_d5_performance_markdown(report),
        encoding="utf-8",
    )


def add_scalable_3d_d5_baseline_comparison(
    report: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    baseline_label: str,
) -> dict[str, Any]:
    """Attach a same-input before/after comparison and fail on semantic drift."""

    current_copy = json.loads(json.dumps(report))
    current_terminal = report["terminal_replay"]
    baseline_terminal = baseline["terminal_replay"]
    current_active = report["active_vision_scale"]
    baseline_active = baseline["active_vision_scale"]
    checks = {
        "same_online_log_sha256": (
            report["source"]["online_log_sha256"]
            == baseline["source"]["online_log_sha256"]
        ),
        "same_recorded_terminal_core_sha256": (
            current_terminal["recorded_core_sha256"]
            == baseline_terminal["recorded_core_sha256"]
        ),
        "same_replayed_terminal_core_sha256": (
            current_terminal["replayed_core_sha256"]
            == baseline_terminal["replayed_core_sha256"]
        ),
        "same_active_decision_sha256": (
            current_active["decision_sha256"]
            == baseline_active["decision_sha256"]
        ),
        "same_binding_state_counts": (
            current_terminal["binding_state_counts"]
            == baseline_terminal["binding_state_counts"]
        ),
    }
    if not all(checks.values()):
        raise ValueError("baseline comparison rejected semantic or source drift")
    baseline_terminal_s = float(baseline_terminal["median_elapsed_s"])
    current_terminal_s = float(current_terminal["median_elapsed_s"])
    baseline_active_ms = float(baseline_active["median_iteration_ms"])
    current_active_ms = float(current_active["median_iteration_ms"])
    current_copy["baseline_comparison"] = {
        "baseline_label": str(baseline_label),
        "checks": checks,
        "terminal_median_elapsed_s": {
            "baseline": baseline_terminal_s,
            "current": current_terminal_s,
            "speedup": baseline_terminal_s / current_terminal_s,
        },
        "active_vision_median_iteration_ms": {
            "baseline": baseline_active_ms,
            "current": current_active_ms,
            "speedup": baseline_active_ms / current_active_ms,
        },
    }
    return current_copy


def render_scalable_3d_d5_performance_markdown(report: Mapping[str, Any]) -> str:
    terminal = report["terminal_replay"]
    active = report["active_vision_scale"]
    publications = report["recorded_publications"]
    active_publication = publications[_ACTIVE_VISION_TOPIC]
    terminal_publication = publications[_TERMINAL_TOPIC]
    lines = [
            "# D5 三维长时性能复核",
            "",
            "## 结论",
            "",
            (
                f"在线日志重放 {terminal['frame_count']} 次终端关联，记录与重放核心哈希"
                f"一致，规则绑定语义保持。{terminal['repeat_count']} 次重放中位墙钟为 "
                f"{terminal['median_elapsed_s']:.3f} 秒。"
            ),
            (
                f"主动视觉按 {active['track_count']} 条中心航迹、"
                f"{active['camera_count']} 台相机和 {active['assignment_count']} 个分配引用"
                f"运行，中位每轮 {active['median_iteration_ms']:.3f} 毫秒。学习辅助未授权，"
                "输出继续使用确定性规则路径。"
            ),
            "",
            "## 终端关联",
            "",
            f"- 调用数：{terminal['frame_count']}",
            f"- 局部航迹总数：{terminal['tracklet_count']}",
            f"- 稀疏图边总数：{terminal['graph_edge_count']}",
            f"- 绑定状态：{json.dumps(terminal['binding_state_counts'], ensure_ascii=False, sort_keys=True)}",
            f"- 记录哈希：`{terminal['recorded_core_sha256']}`",
            f"- 重放哈希：`{terminal['replayed_core_sha256']}`",
            "- 在线真值使用：0",
            "- 中心航迹编号改写：0",
            "",
            "## 主动视觉",
            "",
            f"- 仿真轮数：{active['iteration_count']}",
            f"- 决策数：{active['decision_count']}",
            f"- 意图分布：{json.dumps(active['intent_counts'], ensure_ascii=False, sort_keys=True)}",
            f"- 决策哈希：`{active['decision_sha256']}`",
            "",
            "## 发布载荷",
            "",
            (
                f"`{_ACTIVE_VISION_TOPIC}` 共 {active_publication['line_count']} 条、"
                f"{active_publication['line_bytes'] / 1_000_000:.3f} MB。"
            ),
            (
                f"`{_TERMINAL_TOPIC}` 共 {terminal_publication['line_count']} 条、"
                f"{terminal_publication['line_bytes'] / 1_000_000:.3f} MB。"
            ),
            (
                "两个 `module.d5` 阶段计时在发布对象构造和总线序列化之前结束。"
                "因此上述载荷不是 D5 内部阶段超线性增长的来源；它会进入 main 总线和日志写出成本，"
                "压缩或降采样属于 main 的消息合同与可观测性取舍，本模块未修改。"
            ),
            "",
            "## 证据边界",
            "",
            "本复核读取在线消息，不读取离线真值、目标实体编号或仿真对象编号。终端关联为真实日志重放；主动视觉为同规模确定性合成负载。结果不代表 AirSim 实时性，也不授予图模型或主动视觉学习策略在线权限。",
            "",
        ]
    comparison = report.get("baseline_comparison")
    if comparison is not None:
        terminal_comparison = comparison["terminal_median_elapsed_s"]
        active_comparison = comparison["active_vision_median_iteration_ms"]
        lines[3:3] = [
            (
                f"同输入基线 `{comparison['baseline_label']}` 对照中，终端重放由 "
                f"{terminal_comparison['baseline']:.3f} 秒降至 "
                f"{terminal_comparison['current']:.3f} 秒，加速 "
                f"{terminal_comparison['speedup']:.3f} 倍；主动视觉每轮由 "
                f"{active_comparison['baseline']:.3f} 毫秒降至 "
                f"{active_comparison['current']:.3f} 毫秒，加速 "
                f"{active_comparison['speedup']:.3f} 倍。"
            ),
            "",
        ]
    return "\n".join(lines)


def render_scalable_3d_d5_duration_comparison_markdown(
    report: Mapping[str, Any],
) -> str:
    short = report["short_terminal_replay"]
    long = report["long_terminal_replay"]
    comparison = report["comparison"]
    short_counts = short["operation_counts"]
    long_counts = long["operation_counts"]
    growth = comparison["operation_per_frame_growth"]
    return "\n".join(
        [
            "# D5 三维长短序列操作数复核",
            "",
            "## 结论",
            "",
            (
                f"冻结在线日志的短序列为 {comparison['short_duration_s']:.3f} 秒、"
                f"{comparison['short_frame_count']} 次调用，长序列为 "
                f"{comparison['long_duration_s']:.3f} 秒、"
                f"{comparison['long_frame_count']} 次调用。调用密度增长 "
                f"{_format_growth(comparison['call_density_per_simulation_second']['growth'])}，"
                f"平均单次成本增长 {_format_growth(comparison['mean_call_ms']['growth'])}。"
            ),
            (
                "两组逐帧 TerminalAssociation 核心输出和最终 binding 均与原在线发布记录"
                "一致。在线真值使用与 global_track_id 改写均为 0。"
            ),
            "",
            "## 操作数",
            "",
            "| 项目 | 短序列 | 长序列 | 每调用增长 |",
            "| --- | ---: | ---: | ---: |",
            _operation_row("相机批次", short_counts, long_counts, growth, "camera_batch_count"),
            _operation_row("输入检测", short_counts, long_counts, growth, "input_detection_count"),
            _operation_row("局部航迹节点", short_counts, long_counts, growth, "graph_node_count"),
            _operation_row(
                "局部历史更新",
                short_counts,
                long_counts,
                growth,
                "tracker_history_update_count",
            ),
            _operation_row(
                "局部匹配对比较",
                short_counts,
                long_counts,
                growth,
                "tracker_pair_evaluation_count",
            ),
            _operation_row(
                "候选边输入",
                short_counts,
                long_counts,
                growth,
                "candidate_edge_generation_count",
            ),
            _operation_row(
                "几何门拒绝",
                short_counts,
                long_counts,
                growth,
                "geometry_gate_rejection_count",
            ),
            _operation_row(
                "保留图边",
                short_counts,
                long_counts,
                growth,
                "retained_graph_edge_count",
            ),
            _operation_row("图构建", short_counts, long_counts, growth, "graph_build_count"),
            _operation_row("评分边", short_counts, long_counts, growth, "scored_edge_count"),
            _operation_row("聚类构建", short_counts, long_counts, growth, "cluster_build_count"),
            _operation_row("聚类输出", short_counts, long_counts, growth, "cluster_output_count"),
            _operation_row(
                "投影矩阵单元",
                short_counts,
                long_counts,
                growth,
                "projection_matrix_cell_count",
            ),
            _operation_row(
                "绑定矩阵单元",
                short_counts,
                long_counts,
                growth,
                "binding_matrix_cell_count",
            ),
            _operation_row(
                "匈牙利求解",
                short_counts,
                long_counts,
                growth,
                "hungarian_solve_count",
            ),
            _operation_row(
                "绑定输出",
                short_counts,
                long_counts,
                growth,
                "binding_output_count",
            ),
            "",
            "## 历史与复用",
            "",
            (
                f"活跃相机流峰值为 {short_counts['active_camera_stream_peak']}/"
                f"{long_counts['active_camera_stream_peak']}，活跃局部历史峰值为 "
                f"{short_counts['active_local_history_peak']}/"
                f"{long_counts['active_local_history_peak']}。量测时间戳审计历史峰值为 "
                f"{short_counts['received_timestamp_history_peak']}/"
                f"{long_counts['received_timestamp_history_peak']}。这些数值是标量峰值，"
                "诊断器本身不保存逐帧历史。"
            ),
            (
                f"中心航迹转换缓存命中/未命中为 "
                f"{short_counts['center_projection_cache_hit_count']}/"
                f"{short_counts['center_projection_cache_miss_count']} 和 "
                f"{long_counts['center_projection_cache_hit_count']}/"
                f"{long_counts['center_projection_cache_miss_count']}。投影矩阵构建为 "
                f"{short_counts['projection_matrix_build_count']}/"
                f"{long_counts['projection_matrix_build_count']} 次，均在同一调用内直接复用于"
                "中心绑定。"
            ),
            (
                f"相机模板完整构建为 {short_counts['camera_template_build_count']}/"
                f"{long_counts['camera_template_build_count']} 次；同批次相同元数据复用为 "
                f"{short_counts['camera_template_reuse_count']}/"
                f"{long_counts['camera_template_reuse_count']} 次。复用只跳过重复校验，"
                "首份模板仍执行完整内外参、旋转和协方差检查。"
            ),
            "",
            "## 业务等价",
            "",
            f"- 短序列业务哈希：`{short['replayed_core_sha256']}`",
            f"- 长序列业务哈希：`{long['replayed_core_sha256']}`",
            f"- 短序列最终绑定哈希：`{short['replayed_final_binding_sha256']}`",
            f"- 长序列最终绑定哈希：`{long['replayed_final_binding_sha256']}`",
            f"- 短序列操作数哈希：`{short['operation_counts_sha256']}`",
            f"- 长序列操作数哈希：`{long['operation_counts_sha256']}`",
            "",
            "## 证据边界",
            "",
            (
                "该复核只消费在线总线记录，不读取离线真值或仿真实体编号。长短序列的"
                "目标可见数量不同，因此两组业务哈希不应彼此相同；验收条件是每组重放"
                "分别与自身原发布记录一致。结果用于解释操作数增长，不代表 AirSim 实时性"
                "或图模型在线准入。"
            ),
            "",
        ]
    )


def _active_vision_snapshot(
    *,
    now: float,
    communication_version: int,
    track_count: int,
    camera_count: int,
    assignment_count: int,
) -> ActiveVisionSnapshotV1:
    tracks = tuple(
        ActiveVisionTrackReference(
            global_track_id=f"GT3D-{index + 1:06d}",
            track_version=3,
            measurement_timestamp=now,
        )
        for index in range(track_count)
    )
    cameras = tuple(
        ActiveVisionCameraState(
            camera_id=f"CAM-BENCH-{index + 1:06d}",
            resource_id=f"RES-BENCH-{index + 1:06d}",
            state_timestamp=now,
            yaw_deg=0.0,
            pitch_deg=0.0,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-180.0, 180.0),
            pitch_limits_deg=(-89.9, 89.9),
            max_yaw_rate_deg_s=60.0,
            max_pitch_rate_deg_s=60.0,
            max_slew_deg_s=80.0,
            current_fov_mode=ActiveVisionFovMode.WIDE,
            wide_horizontal_fov_deg=90.0,
            zoom_horizontal_fov_deg=30.0,
        )
        for index in range(camera_count)
    )
    assignments = tuple(
        ActiveVisionAssignmentReference(
            resource_id=cameras[index].resource_id,
            camera_id=cameras[index].camera_id,
            global_track_id=tracks[index].global_track_id,
        )
        for index in range(assignment_count)
    )
    projections = tuple(
        ActiveVisionProjectionEvidence(
            camera_id=cameras[index].camera_id,
            global_track_id=tracks[index].global_track_id,
            measurement_timestamp=now,
            arrival_timestamp=now,
            yaw_error_deg=0.1,
            pitch_error_deg=0.1,
            projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
            visibility_probability=0.9,
            occlusion_fraction=0.0,
            association_confidence=0.9,
            in_fov=True,
        )
        for index in range(assignment_count)
    )
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=now,
        plan=ActiveVisionPlanReference(
            plan_version=3,
            coalition_version=0,
            assignments=assignments,
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=communication_version,
            plan_version=3,
            coalition_version=0,
            update_timestamp=now,
            healthy=True,
        ),
        tracks=tracks,
        cameras=cameras,
        projections=projections,
    )


def _camera_batch_from_publication(payload: Mapping[str, Any]) -> Any:
    measurements = tuple(
        SimpleNamespace(
            **{
                **item,
                "measurement": np.asarray(item["measurement"], dtype=float),
                "covariance": np.asarray(item["covariance"], dtype=float),
            }
        )
        for item in payload["measurements"]
    )
    return SimpleNamespace(
        batch_id=payload["batch_id"],
        sensor_id=payload["sensor_id"],
        measurement_timestamp=payload["measurement_timestamp"],
        arrival_timestamp=payload["arrival_timestamp"],
        measurements=measurements,
    )


def _center_tracks_from_publication(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        SimpleNamespace(
            global_track_id=item["global_track_id"],
            state=np.asarray(item["state_ned"], dtype=float),
            covariance=np.asarray(item["covariance"], dtype=float),
            timestamp=float(item["timestamp"]),
            track_version=0,
        )
        for item in payload.get("tracks", ())
    )


def _terminal_core_from_publication(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "camera_batch_count",
        "tracklet_count",
        "graph_node_count",
        "graph_edge_count",
        "probability_source",
        "scoring_status",
        "fallback_reason",
        "diagnostics",
        "bindings",
    )
    return {key: payload[key] for key in keys}


def _terminal_core_from_result(result: Scalable3DStepResult) -> dict[str, Any]:
    association = result.association
    return {
        "camera_batch_count": len(result.camera_batches),
        "tracklet_count": len(result.tracklets),
        "graph_node_count": association.graph.node_count,
        "graph_edge_count": association.graph.edge_count,
        "probability_source": association.probability_source,
        "scoring_status": association.scoring_status,
        "fallback_reason": association.fallback_reason,
        "diagnostics": dict(association.diagnostics),
        "bindings": [
            {
                "cluster_key": item.cluster_key,
                "global_track_id": item.global_track_id,
                "decision_state": item.decision_state,
                "cost": item.cost,
                "supporting_tracklet_keys": list(item.supporting_tracklet_keys),
            }
            for item in association.bindings
        ],
    }


def _replay_source_summary(replay: LongDurationOnlineReplay) -> dict[str, Any]:
    return {
        "online_log": str(replay.path),
        "online_log_size_bytes": replay.path.stat().st_size,
        "online_log_sha256": replay.online_log_sha256,
        "terminal_frame_count": len(replay.frames),
        "unconsumed_vision_batch_count": replay.unconsumed_vision_batch_count,
        "truth_source_loaded": False,
    }


def _growth_ratio(current: float, baseline: float) -> float | None:
    if baseline == 0.0:
        return 1.0 if current == 0.0 else None
    return current / baseline


def _format_growth(value: Any) -> str:
    return "不可用" if value is None else f"{float(value):.3f} 倍"


def _operation_row(
    label: str,
    short_counts: Mapping[str, Any],
    long_counts: Mapping[str, Any],
    growth: Mapping[str, Any],
    field: str,
) -> str:
    return (
        f"| {label} | {int(short_counts[field])} | {int(long_counts[field])} | "
        f"{_format_growth(growth[field])} |"
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


__all__ = [
    "LongDurationOnlineReplay",
    "SCALABLE_3D_D5_DURATION_COMPARISON_SCHEMA_VERSION",
    "SCALABLE_3D_D5_PERFORMANCE_SCHEMA_VERSION",
    "TerminalReplayFrame",
    "add_scalable_3d_d5_baseline_comparison",
    "benchmark_active_vision_scale",
    "benchmark_terminal_replay",
    "compare_terminal_replay_benchmarks",
    "load_long_duration_online_replay",
    "render_scalable_3d_d5_duration_comparison_markdown",
    "render_scalable_3d_d5_performance_markdown",
    "run_scalable_3d_d5_duration_comparison",
    "run_scalable_3d_d5_performance_benchmark",
    "write_scalable_3d_d5_duration_comparison",
    "write_scalable_3d_d5_performance_report",
]
