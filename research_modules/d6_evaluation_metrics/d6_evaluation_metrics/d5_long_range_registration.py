"""Offline evaluation for D5 long-range visual registration episodes.

The evaluator consumes files written by the main AirSim runtime.  It never
imports D5 runtime code, participates in online association, or grants control
authority.  Missing evidence remains explicitly unavailable.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


D5_LONG_RANGE_REGISTRATION_SCHEMA_VERSION = (
    "d6.d5-long-range-registration-evaluation.v1"
)
D5_LONG_RANGE_REGISTRATION_EVALUATION_DATE = "2026-08-10"

METRIC_NAMES = (
    "measured_short_gap_count",
    "measured_short_gap_total_duration_s",
    "effective_short_gap_fragmentation_count",
    "bounded_coast_event_count",
    "bounded_coast_frame_count",
    "bounded_coast_max_age_s",
    "bounded_coast_same_id_recovery_count",
    "coast_expiry_count",
    "long_reacquisition_count",
    "long_reacquisition_identity_change_count",
    "binding_switch_proposed_count",
    "binding_switch_pending_count",
    "binding_switch_held_count",
    "binding_switch_confirmed_count",
    "binding_switch_expired_count",
    "binding_oscillation_count",
    "geometric_binding_switch_count",
    "crossing_total_count",
    "crossing_evaluable_count",
    "crossing_unavailable_count",
    "crossing_availability_ratio",
    "crossing_unavailable_reasons",
    "crossing_id_switch_count",
    "crossing_track_purity",
    "crossing_track_continuity",
    "association_accuracy",
    "association_evaluable_count",
    "association_wrong_count",
    "id_switch_count",
    "duplicate_assignment_count",
    "online_truth_use_count",
    "global_track_id_rewrite_count",
)

_SUM_METRICS = frozenset(
    {
        "measured_short_gap_count",
        "measured_short_gap_total_duration_s",
        "effective_short_gap_fragmentation_count",
        "bounded_coast_event_count",
        "bounded_coast_frame_count",
        "bounded_coast_same_id_recovery_count",
        "coast_expiry_count",
        "long_reacquisition_count",
        "long_reacquisition_identity_change_count",
        "binding_switch_proposed_count",
        "binding_switch_pending_count",
        "binding_switch_held_count",
        "binding_switch_confirmed_count",
        "binding_switch_expired_count",
        "binding_oscillation_count",
        "geometric_binding_switch_count",
        "crossing_total_count",
        "crossing_evaluable_count",
        "crossing_unavailable_count",
        "crossing_id_switch_count",
        "association_evaluable_count",
        "association_wrong_count",
        "id_switch_count",
        "duplicate_assignment_count",
        "online_truth_use_count",
        "global_track_id_rewrite_count",
    }
)


@dataclass(frozen=True)
class D5LongRangeRegistrationThresholds:
    """Fail-closed structural and actual-crossing thresholds."""

    association_min_accuracy: float = 0.95
    crossing_min_evaluable_count: int = 10
    crossing_min_availability_ratio: float = 0.30

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.association_min_accuracy) <= 1.0:
            raise ValueError("association_min_accuracy must be in [0, 1]")
        if int(self.crossing_min_evaluable_count) < 1:
            raise ValueError("crossing_min_evaluable_count must be positive")
        if not 0.0 <= float(self.crossing_min_availability_ratio) <= 1.0:
            raise ValueError("crossing_min_availability_ratio must be in [0, 1]")


@dataclass(frozen=True)
class D5LongRangeRegistrationEpisode:
    """Loaded, producer-independent evidence for one episode directory."""

    episode_id: str
    requested_dir: Path
    evidence_dir: Path
    artifacts: Mapping[str, Mapping[str, Any]]
    metrics: Mapping[str, Any]
    mot_continuity: Mapping[str, Any]
    associations: tuple[Mapping[str, str], ...]
    temporal_binding_events: tuple[Mapping[str, str], ...]
    dropout_events: tuple[Mapping[str, str], ...]
    online_replay: tuple[Mapping[str, Any], ...]
    offline_truth_sidecar: Mapping[str, Any]
    temporal_association_summary: Mapping[str, Any]


class D5LongRangeRegistrationReportGenerator:
    """Create a complete offline report bundle from episode directories."""

    def __init__(
        self,
        thresholds: D5LongRangeRegistrationThresholds | None = None,
    ) -> None:
        self.thresholds = thresholds or D5LongRangeRegistrationThresholds()

    def write_report_bundle(
        self,
        output_dir: str | Path,
        episode_dirs: str | Path | Sequence[str | Path],
        *,
        title: str = "D5长距离视觉配准离线评估",
    ) -> dict[str, Path]:
        episodes = load_d5_long_range_registration_episodes(episode_dirs)
        result = evaluate_d5_long_range_registration(
            episodes,
            thresholds=self.thresholds,
        )
        return write_d5_long_range_registration_report(
            output_dir,
            result,
            title=title,
        )


def load_d5_long_range_registration_episode(
    episode_dir: str | Path,
) -> D5LongRangeRegistrationEpisode:
    """Load one direct episode directory or a root containing ``coverage_safe``."""

    requested = Path(episode_dir).expanduser().resolve()
    if not requested.is_dir():
        raise FileNotFoundError(f"episode directory does not exist: {requested}")
    evidence_dir = _resolve_evidence_dir(requested)

    metrics, metrics_artifact = _load_json_mapping(evidence_dir / "metrics.json")
    mot, mot_artifact = _load_json_mapping(evidence_dir / "mot_continuity.json")
    associations, associations_artifact = _load_csv_rows(
        evidence_dir / "associations.csv"
    )
    temporal, temporal_artifact = _load_csv_rows(
        evidence_dir / "temporal_binding_events.csv"
    )
    dropout, dropout_artifact = _load_csv_rows(evidence_dir / "dropout_events.csv")
    baseline_manifest, baseline_manifest_artifact = _load_json_mapping(
        evidence_dir / "baseline_manifest.json"
    )
    online_replay, online_replay_artifact = _load_jsonl_objects(
        evidence_dir / "online_replay.jsonl"
    )
    offline_sidecar, offline_sidecar_artifact = _load_json_mapping(
        evidence_dir / "offline_truth_sidecar.json"
    )
    baseline_status = _validate_frozen_baseline(
        evidence_dir,
        baseline_manifest,
        online_replay,
        offline_sidecar,
    )
    if not metrics and baseline_status["availability"] == "available":
        metrics, mot = _frozen_baseline_metrics(baseline_manifest, offline_sidecar)
    artifacts = {
        "metrics": metrics_artifact,
        "mot_continuity": mot_artifact,
        "associations": associations_artifact,
        "temporal_binding_events": temporal_artifact,
        "dropout_events": dropout_artifact,
        "baseline_manifest": baseline_manifest_artifact,
        "online_replay": online_replay_artifact,
        "offline_truth_sidecar": offline_sidecar_artifact,
        "frozen_baseline": baseline_status,
    }
    return D5LongRangeRegistrationEpisode(
        episode_id=(
            requested.parent.name
            if requested.name in {"coverage_safe", "coverage_unsafe"}
            else requested.name
        ),
        requested_dir=requested,
        evidence_dir=evidence_dir,
        artifacts=artifacts,
        metrics=metrics,
        mot_continuity=mot,
        associations=tuple(associations),
        temporal_binding_events=tuple(temporal),
        dropout_events=tuple(dropout),
        online_replay=tuple(online_replay),
        offline_truth_sidecar=offline_sidecar,
        temporal_association_summary=(
            dict(metrics.get("temporal_association", {}))
            if isinstance(metrics.get("temporal_association"), Mapping)
            else {}
        ),
    )


def load_d5_long_range_registration_episodes(
    episode_dirs: str | Path | Sequence[str | Path],
) -> tuple[D5LongRangeRegistrationEpisode, ...]:
    """Load one or more episode directories without importing producer code."""

    if isinstance(episode_dirs, (str, Path)):
        values: Sequence[str | Path] = (episode_dirs,)
    else:
        values = tuple(episode_dirs)
    if not values:
        raise ValueError("at least one episode directory is required")
    episodes = tuple(load_d5_long_range_registration_episode(value) for value in values)
    return episodes


def evaluate_d5_long_range_registration(
    episodes: (
        D5LongRangeRegistrationEpisode
        | str
        | Path
        | Sequence[D5LongRangeRegistrationEpisode | str | Path]
    ),
    *,
    thresholds: D5LongRangeRegistrationThresholds | None = None,
) -> dict[str, Any]:
    """Evaluate loaded v2/v3 episodes with availability-aware fail-closed gates."""

    threshold_config = thresholds or D5LongRangeRegistrationThresholds()
    loaded = _coerce_episodes(episodes)
    episode_results = [
        _evaluate_episode(episode, thresholds=threshold_config) for episode in loaded
    ]
    aggregate_metrics = _aggregate_metrics(
        [item["aggregate"] for item in episode_results],
        scope_label="all episodes",
    )
    cameras = sorted(
        {
            camera
            for episode in episode_results
            for camera in episode["per_camera"]
        }
    )
    aggregate_cameras = {
        camera: {
            "episode_count": sum(camera in item["per_camera"] for item in episode_results),
            "metrics": _aggregate_metrics(
                [
                    item["per_camera"][camera]
                    for item in episode_results
                    if camera in item["per_camera"]
                ],
                scope_label=f"camera {camera}",
            ),
        }
        for camera in cameras
    }
    gates = _evaluate_gates(aggregate_metrics, threshold_config)
    seeds = [_episode_seed(episode.metrics) for episode in loaded]
    available_seeds = [seed for seed in seeds if seed is not None]
    unique_seed_count = len(set(available_seeds)) if len(available_seeds) == len(seeds) else None
    status = "passed" if gates["overall_gate_passed"] else "fail_closed"
    return {
        "schema_version": D5_LONG_RANGE_REGISTRATION_SCHEMA_VERSION,
        "evaluation_date": D5_LONG_RANGE_REGISTRATION_EVALUATION_DATE,
        "evaluation_scope": "offline_d5_long_range_registration_only",
        "online_association_participation": False,
        "control_authority": False,
        "global_track_id_write_authority": False,
        "geometry_preflight_counts_as_actual_crossing": False,
        "thresholds": {
            "association_min_accuracy": threshold_config.association_min_accuracy,
            "crossing_min_evaluable_count": threshold_config.crossing_min_evaluable_count,
            "crossing_min_availability_ratio": threshold_config.crossing_min_availability_ratio,
        },
        "episode_count": len(episode_results),
        "unique_seed_count": unique_seed_count,
        "multi_seed_evidence_available": bool(
            unique_seed_count is not None and unique_seed_count >= 10
        ),
        "episodes": episode_results,
        "aggregate": aggregate_metrics,
        "per_camera": aggregate_cameras,
        "gates": gates,
        "status": status,
        "p1_closed": False,
        "p1_status_reason": (
            "this evaluator does not close P1; main must review at least 10 real "
            "AirSim seeds and cross-module evidence"
        ),
    }


def write_d5_long_range_registration_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
    *,
    title: str = "D5长距离视觉配准离线评估",
) -> dict[str, Path]:
    """Write per-episode CSV, aggregate JSON, Chinese Markdown, and one PNG."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "d5_long_range_registration_per_episode.csv"
    json_path = output / "d5_long_range_registration_aggregate.json"
    markdown_path = output / "D5_LONG_RANGE_REGISTRATION_EVALUATION_REPORT_CN.md"
    plot_path = output / "d5_long_range_registration_summary.png"

    rows = _per_episode_rows(result)
    _write_rows_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_summary_plot(result, plot_path)
    markdown_path.write_text(
        render_d5_long_range_registration_markdown(
            result,
            title=title,
            plot_name=plot_path.name,
        ),
        encoding="utf-8",
    )
    return {
        "per_episode_csv": csv_path,
        "aggregate_json": json_path,
        "markdown": markdown_path,
        "plot": plot_path,
    }


def render_d5_long_range_registration_markdown(
    result: Mapping[str, Any],
    *,
    title: str = "D5长距离视觉配准离线评估",
    plot_name: str = "d5_long_range_registration_summary.png",
) -> str:
    """Render a concise Chinese report with explicit evidence boundaries."""

    aggregate = result["aggregate"]
    gates = result["gates"]
    lines = [f"# {title}", "", "## 结论", ""]
    if result["status"] == "passed":
        lines.append(
            "本批离线结构门和实际交叉窗口门通过。该结果仍不自动关闭P1，也不形成在线关联或控制许可。"
        )
    else:
        failures = ", ".join(gates["failure_reasons"]) or "证据不完整"
        lines.append(f"本批按失败关闭处理。原因：{failures}。")
    lines.append(
        f"输入共{result['episode_count']}个episode；多seed证据"
        f"{'可用' if result['multi_seed_evidence_available'] else '尚不可用'}。"
        "几何预检只说明场景设计，不计入实际交叉窗口分母。"
    )
    lines.extend(
        [
            "",
            f"![长距离配准综合指标]({plot_name})",
            "",
            "## 汇总指标",
            "",
            "| 指标 | 数值 | 可用性 | 原因/来源 |",
            "|---|---:|---|---|",
        ]
    )
    for name in METRIC_NAMES:
        metric = aggregate[name]
        lines.append(
            f"| {_metric_label(name)} | {_format_value(metric)} | "
            f"{metric['availability']} | {_metric_note(metric)} |"
        )

    lines.extend(["", "## 分相机结果", ""])
    lines.append(
        "| 相机 | 短缺口 | 有效短缺口中断 | 长期重发现 | 身份切换 | "
        "交叉可评分/总数 | 关联准确率 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for camera, camera_entry in sorted(result["per_camera"].items()):
        metrics = camera_entry["metrics"]
        lines.append(
            f"| {camera} | {_format_value(metrics['measured_short_gap_count'])} | "
            f"{_format_value(metrics['effective_short_gap_fragmentation_count'])} | "
            f"{_format_value(metrics['long_reacquisition_count'])} | "
            f"{_format_value(metrics['id_switch_count'])} | "
            f"{_format_value(metrics['crossing_evaluable_count'])}/"
            f"{_format_value(metrics['crossing_total_count'])} | "
            f"{_format_value(metrics['association_accuracy'])} |"
        )

    lines.extend(["", "## 门控", ""])
    lines.append("| 门控项 | 要求 | 结果 | 数值/原因 |")
    lines.append("|---|---|---|---|")
    for name, check in gates["structural_checks"].items():
        lines.append(
            f"| {_metric_label(name)} | {check['requirement']} | {check['status']} | "
            f"{_format_check_value(check)} |"
        )
    crossing = gates["actual_crossing_gate"]
    lines.append(
        "| 实际交叉窗口 | 可评分数不小于"
        f"{crossing['minimum_evaluable_count']}且比例不小于"
        f"{crossing['minimum_availability_ratio']:.2f} | {crossing['status']} | "
        f"{crossing['reason']} |"
    )

    lines.extend(["", "## Episode明细", ""])
    lines.append("| Episode | schema | 准确率 | 短缺口 | 重发现 | 绑定切换 | 交叉窗口 | 状态 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---|")
    for episode in result["episodes"]:
        metrics = episode["aggregate"]
        schemas = episode["schemas"]
        lines.append(
            f"| {episode['episode_id']} | {schemas['metrics'] or '未知'} | "
            f"{_format_value(metrics['association_accuracy'])} | "
            f"{_format_value(metrics['measured_short_gap_count'])} | "
            f"{_format_value(metrics['long_reacquisition_count'])} | "
            f"{_format_value(metrics['geometric_binding_switch_count'])} | "
            f"{_format_value(metrics['crossing_evaluable_count'])}/"
            f"{_format_value(metrics['crossing_total_count'])} | {episode['status']} |"
        )

    lines.extend(["", "## 证据边界", ""])
    lines.append(
        "本报告只消费main写盘的指标、连续性和关联记录。旧v2没有时序绑定与掉检事件时，"
        "保持帧数、保持恢复、绑定振荡等指标标为不可用，不按零处理。"
    )
    lines.append(
        "当前冻结单seed结果即使关联准确率较高，也会因有效短缺口中断、时序证据缺失或"
        "实际交叉窗口不足而失败关闭。报告不声称P1、多seed标定或真实光电识别已经完成。"
    )
    return "\n".join(lines) + "\n"


def _coerce_episodes(
    episodes: Any,
) -> tuple[D5LongRangeRegistrationEpisode, ...]:
    if isinstance(episodes, D5LongRangeRegistrationEpisode):
        return (episodes,)
    if isinstance(episodes, (str, Path)):
        return load_d5_long_range_registration_episodes(episodes)
    values = tuple(episodes)
    if not values:
        raise ValueError("at least one episode is required")
    if all(isinstance(value, D5LongRangeRegistrationEpisode) for value in values):
        return values
    if any(isinstance(value, D5LongRangeRegistrationEpisode) for value in values):
        raise TypeError("do not mix loaded episodes and paths")
    return load_d5_long_range_registration_episodes(values)


def _evaluate_episode(
    episode: D5LongRangeRegistrationEpisode,
    *,
    thresholds: D5LongRangeRegistrationThresholds,
) -> dict[str, Any]:
    mot_aggregate = _mot_aggregate(episode.mot_continuity)
    cameras = _camera_names(episode)
    aggregate = _scope_metrics(
        episode,
        mot_scope=mot_aggregate,
        camera=None,
    )
    per_camera = {
        camera: _scope_metrics(
            episode,
            mot_scope=_mot_camera(episode.mot_continuity, camera),
            camera=camera,
        )
        for camera in cameras
    }
    gates = _evaluate_gates(aggregate, thresholds)
    return {
        "episode_id": episode.episode_id,
        "evidence_dir": str(episode.evidence_dir),
        "schemas": {
            "metrics": _optional_string(episode.metrics.get("schema_version")),
            "mot_continuity": _optional_string(
                episode.mot_continuity.get("schema_version")
            ),
        },
        "artifacts": {name: dict(value) for name, value in episode.artifacts.items()},
        "aggregate": aggregate,
        "per_camera": per_camera,
        "gates": gates,
        "status": "passed" if gates["overall_gate_passed"] else "fail_closed",
    }


def _scope_metrics(
    episode: D5LongRangeRegistrationEpisode,
    *,
    mot_scope: Mapping[str, Any],
    camera: str | None,
) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    scope_name = "aggregate" if camera is None else f"camera:{camera}"
    association_rows = _rows_for_camera(episode.associations, camera)
    temporal_rows = _rows_for_camera(episode.temporal_binding_events, camera)
    dropout_rows = _rows_for_camera(episode.dropout_events, camera)

    metrics.update(
        _gap_metrics(
            episode,
            mot_scope,
            temporal_rows,
            dropout_rows,
            scope_name,
            camera,
        )
    )
    metrics.update(_binding_metrics(episode, temporal_rows, scope_name, camera))
    metrics.update(_crossing_metrics(episode, mot_scope, scope_name))
    metrics.update(
        _association_metrics(episode, association_rows, scope_name, camera)
    )
    metrics.update(
        _safety_metrics(
            episode,
            mot_scope,
            association_rows,
            temporal_rows,
            dropout_rows,
            scope_name,
            camera,
        )
    )
    missing = set(METRIC_NAMES) - set(metrics)
    if missing:
        raise RuntimeError(f"internal metric assembly incomplete: {sorted(missing)}")
    return {name: metrics[name] for name in METRIC_NAMES}


def _gap_metrics(
    episode: D5LongRangeRegistrationEpisode,
    mot_scope: Mapping[str, Any],
    temporal_rows: Sequence[Mapping[str, str]],
    dropout_rows: Sequence[Mapping[str, str]],
    scope_name: str,
    camera: str | None,
) -> dict[str, dict[str, Any]]:
    measured = _metric_from_keys(
        mot_scope,
        ("measured_short_gap_count", "fragmentation_count"),
        source=f"mot_continuity:{scope_name}",
        integer=True,
        missing_reason="mot_short_gap_count_missing",
    )
    if measured["availability"] != "available":
        baseline_count = _baseline_short_gap_count(episode, camera)
        if baseline_count["availability"] == "available":
            measured = baseline_count
    temporal = _derive_temporal_gap_metrics(
        episode,
        temporal_rows,
        dropout_rows,
        scope_name=scope_name,
        camera=camera,
        measured_short_gap_count=measured,
    )
    durations = temporal["measured_short_gap_total_duration_s"]
    if durations["availability"] != "available":
        sidecar_duration = _baseline_short_gap_duration(episode, camera)
        if sidecar_duration["availability"] == "available":
            durations = sidecar_duration
    effective = _metric_from_keys(
        mot_scope,
        ("effective_short_gap_fragmentation_count",),
        source=f"mot_continuity:{scope_name}",
        integer=True,
        missing_reason="effective_short_gap_fragmentation_missing",
    )
    if effective["availability"] != "available":
        derived = temporal["effective_short_gap_fragmentation_count"]
        if derived["availability"] == "available":
            effective = derived
        elif (
            episode.artifacts["temporal_binding_events"].get("availability")
            != "available"
            and episode.artifacts["dropout_events"].get("availability") != "available"
            and measured["availability"] == "available"
        ):
            effective = _available(
                measured["value"],
                f"mot_continuity:{scope_name}:pre_temporal_effective_equals_measured",
            )
    long_count = _metric_from_keys(
        mot_scope,
        ("long_reacquisition_count", "reacquisition_count"),
        source=f"mot_continuity:{scope_name}",
        integer=True,
        missing_reason="long_reacquisition_count_missing",
    )
    long_changed = _metric_from_keys(
        mot_scope,
        (
            "long_reacquisition_identity_change_count",
            "reacquisition_identity_changed_count",
        ),
        source=f"mot_continuity:{scope_name}",
        integer=True,
        missing_reason="long_reacquisition_identity_change_missing",
    )
    return {
        "measured_short_gap_count": measured,
        "measured_short_gap_total_duration_s": durations,
        "effective_short_gap_fragmentation_count": effective,
        "bounded_coast_event_count": temporal["bounded_coast_event_count"],
        "bounded_coast_frame_count": temporal["bounded_coast_frame_count"],
        "bounded_coast_max_age_s": temporal["bounded_coast_max_age_s"],
        "bounded_coast_same_id_recovery_count": temporal[
            "bounded_coast_same_id_recovery_count"
        ],
        "coast_expiry_count": temporal["coast_expiry_count"],
        "long_reacquisition_count": long_count,
        "long_reacquisition_identity_change_count": long_changed,
    }


def _derive_temporal_gap_metrics(
    episode: D5LongRangeRegistrationEpisode,
    temporal_rows: Sequence[Mapping[str, str]],
    dropout_rows: Sequence[Mapping[str, str]],
    *,
    scope_name: str,
    camera: str | None,
    measured_short_gap_count: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    names = (
        "measured_short_gap_total_duration_s",
        "effective_short_gap_fragmentation_count",
        "bounded_coast_event_count",
        "bounded_coast_frame_count",
        "bounded_coast_max_age_s",
        "bounded_coast_same_id_recovery_count",
        "coast_expiry_count",
    )
    temporal_artifact = episode.artifacts["temporal_binding_events"]
    dropout_artifact = episode.artifacts["dropout_events"]
    if temporal_artifact.get("availability") != "available":
        reason = str(
            temporal_artifact.get("reason") or "temporal_binding_events_unavailable"
        )
        return {name: _unavailable(reason) for name in names}
    if dropout_artifact.get("availability") != "available":
        reason = str(dropout_artifact.get("reason") or "dropout_events_unavailable")
        return {name: _unavailable(reason) for name in names}

    required_dropout = {
        "record_type",
        "global_track_id",
        "local_track_id",
        "local_track_state",
        "decision_state",
        "prediction_age_s",
        "last_measurement_timestamp",
        "measurement_timestamp",
        "terminal_authorization_allowed",
    }
    required_temporal = {
        "binding_event",
        "local_track_id",
        "incumbent_global_track_id",
        "candidate_global_track_id",
        "measurement_timestamp",
        "measured_evidence",
        "terminal_authorization_allowed",
    }
    dropout_fields = set(dropout_artifact.get("fieldnames", ()))
    temporal_fields = set(temporal_artifact.get("fieldnames", ()))
    missing_dropout = sorted(required_dropout - dropout_fields)
    missing_temporal = sorted(required_temporal - temporal_fields)
    if missing_dropout or missing_temporal:
        reason = (
            "actual_v3_temporal_fields_missing:"
            f"dropout={missing_dropout},binding={missing_temporal}"
        )
        return {name: _unavailable(reason) for name in names}

    if any(
        str(row.get("record_type", "")) != "temporal_prediction"
        for row in dropout_rows
    ):
        return {
            name: _unavailable("dropout_record_type_not_temporal_prediction")
            for name in names
        }
    if any(
        _parse_bool(row.get("terminal_authorization_allowed")) is not False
        for row in tuple(dropout_rows) + tuple(temporal_rows)
    ):
        return {
            name: _unavailable("temporal_prediction_or_event_authorization_not_false")
            for name in names
        }

    summary_reason = _temporal_summary_consistency_reason(
        episode,
        temporal_rows,
        dropout_rows,
        camera=camera,
    )
    if summary_reason is not None:
        return {name: _unavailable(summary_reason) for name in names}

    valid_dropout_rows: list[Mapping[str, str]] = []
    groups: dict[tuple[Any, ...], list[Mapping[str, str]]] = defaultdict(list)
    for row in dropout_rows:
        decision_state = str(row.get("decision_state", "")).strip().lower()
        local_state = str(row.get("local_track_state", "")).strip().lower()
        global_track_id = _optional_string(row.get("global_track_id"))
        last_measurement = _number(row.get("last_measurement_timestamp"))
        measurement = _number(row.get("measurement_timestamp"))
        age = _number(row.get("prediction_age_s"))
        if decision_state not in {"coast", "reacquire"}:
            continue
        if local_state not in {"predicted", "lost"}:
            return {name: _unavailable("dropout_local_track_state_invalid") for name in names}
        if (
            global_track_id is None
            or last_measurement is None
            or measurement is None
            or age is None
            or age < 0.0
        ):
            return {
                name: _unavailable("bounded_dropout_identity_or_time_missing")
                for name in names
            }
        key = (
            _optional_string(row.get("resource_id")) or "",
            _camera_name(row) or "",
            _optional_string(row.get("stream_id")) or "",
            str(row.get("local_track_id", "")),
            global_track_id,
            float(last_measurement),
        )
        groups[key].append(row)
        valid_dropout_rows.append(row)

    source = f"temporal_event_stream:{scope_name}"
    events_by_track: dict[tuple[str, str, str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in temporal_rows:
        events_by_track[_temporal_track_key(row)].append(row)
    for rows in events_by_track.values():
        rows.sort(key=lambda row: _number(row.get("measurement_timestamp")) or 0.0)

    ordered_groups: dict[tuple[str, str, str, str], list[tuple[tuple[Any, ...], list[Mapping[str, str]]]]] = defaultdict(list)
    for key, rows in groups.items():
        rows.sort(key=lambda row: _number(row.get("measurement_timestamp")) or 0.0)
        track_key = (str(key[0]), str(key[1]), str(key[2]), str(key[3]))
        ordered_groups[track_key].append((key, rows))
    for values in ordered_groups.values():
        values.sort(key=lambda item: float(item[0][-1]))

    durations: list[float] = []
    recovered_count = 0
    expiry_count = 0
    open_count = 0
    for track_key, segments in ordered_groups.items():
        track_events = events_by_track.get(track_key, [])
        for index, (key, rows) in enumerate(segments):
            last_measurement = float(key[-1])
            global_track_id = str(key[-2])
            last_dropout_timestamp = max(
                float(_number(row.get("measurement_timestamp")) or 0.0) for row in rows
            )
            next_start = (
                min(
                    float(_number(row.get("measurement_timestamp")) or math.inf)
                    for row in segments[index + 1][1]
                )
                if index + 1 < len(segments)
                else math.inf
            )
            outcome = _matching_temporal_outcome(
                track_events,
                global_track_id=global_track_id,
                after_timestamp=last_dropout_timestamp,
                before_timestamp=next_start,
            )
            if outcome is None:
                open_count += 1
                continue
            event = str(outcome.get("binding_event", "")).strip().lower()
            age = _number(outcome.get("prediction_age_s"))
            timestamp = _number(outcome.get("measurement_timestamp"))
            duration = age if age is not None else (
                None if timestamp is None else max(0.0, timestamp - last_measurement)
            )
            if duration is None:
                open_count += 1
                continue
            durations.append(float(duration))
            if event == "recovered":
                recovered_count += 1
            elif event == "expired":
                expiry_count += 1

    ages = [_number(row.get("prediction_age_s")) for row in valid_dropout_rows]
    if any(age is None for age in ages):
        return {name: _unavailable("dropout_prediction_age_invalid") for name in names}
    max_age = max((float(age) for age in ages if age is not None), default=0.0)
    event_count = len(groups)
    frame_count = len(valid_dropout_rows)
    measured_value = (
        int(measured_short_gap_count["value"])
        if measured_short_gap_count.get("availability") == "available"
        else None
    )
    if open_count:
        duration_metric = _unavailable("one_or_more_bounded_gaps_have_no_recovery_or_expiry")
        effective = _unavailable("one_or_more_bounded_gaps_have_no_recovery_or_expiry")
    elif measured_value is None:
        duration_metric = _unavailable("measured_short_gap_count_unavailable")
        effective = _available(expiry_count, source)
    elif measured_value != event_count:
        duration_metric = _unavailable(
            "measured_short_gap_count_differs_from_temporal_gap_event_count"
        )
        effective = _unavailable(
            "measured_short_gap_count_differs_from_temporal_gap_event_count"
        )
    else:
        duration_metric = _available(sum(durations), source)
        effective = _available(expiry_count, source)
    return {
        "measured_short_gap_total_duration_s": duration_metric,
        "effective_short_gap_fragmentation_count": effective,
        "bounded_coast_event_count": _available(event_count, source),
        "bounded_coast_frame_count": _available(frame_count, source),
        "bounded_coast_max_age_s": _available(max_age, source),
        "bounded_coast_same_id_recovery_count": _available(recovered_count, source),
        "coast_expiry_count": _available(expiry_count, source),
    }


def _temporal_track_key(row: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _optional_string(row.get("resource_id")) or "",
        _camera_name(row) or "",
        _optional_string(row.get("stream_id")) or "",
        str(row.get("local_track_id", "")),
    )


def _matching_temporal_outcome(
    events: Sequence[Mapping[str, str]],
    *,
    global_track_id: str,
    after_timestamp: float,
    before_timestamp: float,
) -> Mapping[str, str] | None:
    for event in events:
        name = str(event.get("binding_event", "")).strip().lower()
        if name not in {"recovered", "expired"}:
            continue
        timestamp = _number(event.get("measurement_timestamp"))
        if timestamp is None or timestamp + 1e-9 < after_timestamp or timestamp >= before_timestamp:
            continue
        incumbent = _optional_string(event.get("incumbent_global_track_id"))
        candidate = _optional_string(event.get("candidate_global_track_id"))
        if global_track_id not in {incumbent, candidate}:
            continue
        return event
    return None


def _temporal_summary_consistency_reason(
    episode: D5LongRangeRegistrationEpisode,
    temporal_rows: Sequence[Mapping[str, str]],
    dropout_rows: Sequence[Mapping[str, str]],
    *,
    camera: str | None,
) -> str | None:
    if camera is not None or not episode.temporal_association_summary:
        return None
    summary = episode.temporal_association_summary
    checks = {
        "binding_event_count": len(temporal_rows),
        "coasted_record_count": len(dropout_rows),
        "recovery_count": sum(_event_name(row) == "recovered" for row in temporal_rows),
        "expiry_count": sum(_event_name(row) == "expired" for row in temporal_rows),
        "predicted_record_authorization_count": sum(
            _parse_bool(row.get("terminal_authorization_allowed")) is True
            for row in dropout_rows
        ),
        "confirmed_switch_count": sum(
            _event_name(row) == "confirmed" and _is_binding_switch_event(row)
            for row in temporal_rows
        ),
    }
    for key, actual in checks.items():
        if key not in summary:
            continue
        expected = _number(summary.get(key))
        if expected is None or not float(expected).is_integer() or int(expected) != actual:
            return f"metrics_temporal_association_{key}_mismatch"
    declared_counts = summary.get("binding_event_counts")
    if isinstance(declared_counts, Mapping):
        actual_counts = Counter(_event_name(row) for row in temporal_rows)
        normalized: dict[str, int] = {}
        for key, value in declared_counts.items():
            number = _number(value)
            if number is None or not float(number).is_integer():
                return "metrics_temporal_association_binding_event_counts_invalid"
            normalized[str(key)] = int(number)
        if normalized != dict(actual_counts):
            return "metrics_temporal_association_binding_event_counts_mismatch"
    return None


def _baseline_short_gap_duration(
    episode: D5LongRangeRegistrationEpisode,
    camera: str | None,
) -> dict[str, Any]:
    if episode.artifacts["frozen_baseline"].get("availability") != "available":
        return _unavailable("frozen_offline_truth_sidecar_unavailable")
    rows = episode.offline_truth_sidecar.get("short_gaps")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return _unavailable("frozen_short_gap_sidecar_missing")
    selected = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and (camera is None or _camera_name(row) == camera)
    ]
    values = [_number(row.get("gap_s")) for row in selected]
    if any(value is None or value < 0.0 for value in values):
        return _unavailable("frozen_short_gap_duration_invalid")
    return _available(sum(values), "offline_truth_sidecar.json:short_gaps")


def _baseline_short_gap_count(
    episode: D5LongRangeRegistrationEpisode,
    camera: str | None,
) -> dict[str, Any]:
    if episode.artifacts["frozen_baseline"].get("availability") != "available":
        return _unavailable("frozen_offline_truth_sidecar_unavailable")
    rows = episode.offline_truth_sidecar.get("short_gaps")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return _unavailable("frozen_short_gap_sidecar_missing")
    selected = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and (camera is None or _camera_name(row) == camera)
    ]
    return _available(len(selected), "offline_truth_sidecar.json:short_gaps")


def _binding_metrics(
    episode: D5LongRangeRegistrationEpisode,
    rows: Sequence[Mapping[str, str]],
    scope_name: str,
    camera: str | None,
) -> dict[str, dict[str, Any]]:
    artifact = episode.artifacts["temporal_binding_events"]
    names = (
        "binding_switch_proposed_count",
        "binding_switch_pending_count",
        "binding_switch_held_count",
        "binding_switch_confirmed_count",
        "binding_switch_expired_count",
        "binding_oscillation_count",
    )
    if artifact.get("availability") != "available":
        values = {
            name: _unavailable(
                str(artifact.get("reason") or "temporal_binding_events_unavailable")
            )
            for name in names
        }
    else:
        fields = set(artifact.get("fieldnames", ()))
        event_field = _first_present(fields, ("binding_event", "event_type", "event"))
        required_fields = {
            "binding_event",
            "binding_reason",
            "incumbent_global_track_id",
            "candidate_global_track_id",
            "candidate_margin",
            "prediction_age_s",
            "measured_evidence",
            "association_confirmed",
            "terminal_authorization_allowed",
        }
        missing_fields = sorted(required_fields - fields)
        summary_reason = _temporal_summary_consistency_reason(
            episode,
            rows,
            _rows_for_camera(episode.dropout_events, camera),
            camera=camera,
        )
        if event_field is None or missing_fields:
            values = {name: _unavailable("binding_event_field_missing") for name in names}
        elif summary_reason is not None:
            values = {name: _unavailable(summary_reason) for name in names}
        elif any(
            _parse_bool(row.get("terminal_authorization_allowed")) is not False
            for row in rows
        ):
            values = {
                name: _unavailable("temporal_binding_event_authorization_not_false")
                for name in names
            }
        else:
            switch_rows = [row for row in rows if _is_binding_switch_event(row)]
            counts = Counter(str(row.get(event_field, "")).strip().lower() for row in switch_rows)
            source = f"temporal_binding_events:{scope_name}"
            values = {
                f"binding_switch_{state}_count": _available(counts[state], source)
                for state in ("proposed", "pending", "held", "confirmed", "expired")
            }
            values["binding_oscillation_count"] = _available(
                _binding_oscillation_count(switch_rows),
                source,
            )

    if camera is None:
        geometric = _metric_from_keys(
            episode.metrics,
            ("geometric_binding_switch_count",),
            source="metrics.json",
            integer=True,
            missing_reason="geometric_binding_switch_count_missing",
        )
    else:
        per_camera = episode.metrics.get("per_camera")
        camera_metrics = per_camera.get(camera, {}) if isinstance(per_camera, Mapping) else {}
        geometric = _metric_from_keys(
            camera_metrics,
            ("geometric_binding_switch_count",),
            source=f"metrics.json:camera:{camera}",
            integer=True,
            missing_reason="per_camera_geometric_binding_switch_count_missing",
        )
    values["geometric_binding_switch_count"] = geometric
    return values


def _crossing_metrics(
    episode: D5LongRangeRegistrationEpisode,
    mot_scope: Mapping[str, Any],
    scope_name: str,
) -> dict[str, dict[str, Any]]:
    source = f"mot_continuity:{scope_name}:actual"
    total = _metric_from_keys(
        mot_scope,
        ("crossing_actual_window_count", "crossing_window_count"),
        source=source,
        integer=True,
        missing_reason="actual_crossing_window_count_missing",
    )
    evaluable = _metric_from_keys(
        mot_scope,
        ("crossing_actual_evaluable_window_count", "crossing_evaluable_window_count"),
        source=source,
        integer=True,
        missing_reason="actual_crossing_evaluable_count_missing",
    )
    unavailable_count = _metric_from_keys(
        mot_scope,
        (
            "crossing_actual_unavailable_window_count",
            "crossing_not_evaluable_window_count",
        ),
        source=source,
        integer=True,
        missing_reason="actual_crossing_unavailable_count_missing",
    )
    if total["availability"] != "available" and _has_geometry_preflight(episode.metrics):
        reason = "actual_crossing_evidence_missing_geometry_preflight_not_accepted"
        total = _unavailable(reason)
        evaluable = _unavailable(reason)
        unavailable_count = _unavailable(reason)
    if total["availability"] == "available" and evaluable["availability"] == "available":
        ratio = _available(
            evaluable["value"] / total["value"] if total["value"] > 0 else 0.0,
            source,
        )
    else:
        ratio = _unavailable("actual_crossing_total_or_evaluable_count_unavailable")

    window_results = mot_scope.get("crossing_window_results")
    if isinstance(window_results, Sequence) and not isinstance(window_results, (str, bytes)):
        reasons = Counter(
            str(item.get("unavailable_reason") or "unspecified")
            for item in window_results
            if isinstance(item, Mapping)
            and not bool(item.get("availability"))
        )
        reason_metric = _available(dict(sorted(reasons.items())), source)
    else:
        reason_metric = _unavailable("actual_crossing_window_results_missing")

    return {
        "crossing_total_count": total,
        "crossing_evaluable_count": evaluable,
        "crossing_unavailable_count": unavailable_count,
        "crossing_availability_ratio": ratio,
        "crossing_unavailable_reasons": reason_metric,
        "crossing_id_switch_count": _metric_from_keys(
            mot_scope,
            ("crossing_actual_id_switch_count", "crossing_id_switch_count"),
            source=source,
            integer=True,
            missing_reason="actual_crossing_id_switch_count_missing",
        ),
        "crossing_track_purity": _metric_from_keys(
            mot_scope,
            ("crossing_actual_track_purity", "crossing_track_purity"),
            source=source,
            missing_reason="actual_crossing_track_purity_missing",
        ),
        "crossing_track_continuity": _metric_from_keys(
            mot_scope,
            ("crossing_actual_track_continuity", "crossing_track_continuity"),
            source=source,
            missing_reason="actual_crossing_track_continuity_missing",
        ),
    }


def _association_metrics(
    episode: D5LongRangeRegistrationEpisode,
    rows: Sequence[Mapping[str, str]],
    scope_name: str,
    camera: str | None,
) -> dict[str, dict[str, Any]]:
    source = "metrics.json" if camera is None else f"associations.csv:{scope_name}"
    if camera is None:
        accuracy = _metric_from_keys(
            episode.metrics,
            ("association_accuracy",),
            source=source,
            missing_reason="association_accuracy_missing",
        )
        evaluable = _metric_from_keys(
            episode.metrics,
            ("association_evaluable_count",),
            source=source,
            integer=True,
            missing_reason="association_evaluable_count_missing",
        )
        wrong = _metric_from_keys(
            episode.metrics,
            ("association_wrong_count", "association_incorrect_count"),
            source=source,
            integer=True,
            missing_reason="association_wrong_count_missing",
        )
        if (
            wrong["availability"] != "available"
            and accuracy["availability"] == "available"
            and evaluable["availability"] == "available"
        ):
            correct = accuracy["value"] * evaluable["value"]
            rounded = round(correct)
            if math.isclose(correct, rounded, rel_tol=0.0, abs_tol=1e-6):
                wrong = _available(
                    int(evaluable["value"] - rounded),
                    "metrics.json:derived_from_accuracy_and_evaluable",
                )
        if accuracy["availability"] == "available":
            return {
                "association_accuracy": accuracy,
                "association_evaluable_count": evaluable,
                "association_wrong_count": wrong,
            }

    selected = [
        row
        for row in rows
        if _parse_bool(row.get("assignment_selected")) is not False
    ]
    correctness_field = _first_present(
        set(episode.artifacts["associations"].get("fieldnames", ())),
        ("association_correct", "assignment_correct", "is_correct"),
    )
    if correctness_field is None:
        return {
            "association_accuracy": _unavailable(
                "per_camera_association_correctness_missing"
                if camera is not None
                else "association_accuracy_and_row_correctness_missing"
            ),
            "association_evaluable_count": _unavailable(
                "association_correctness_field_missing"
            ),
            "association_wrong_count": _unavailable(
                "association_correctness_field_missing"
            ),
        }
    flags = [_parse_bool(row.get(correctness_field)) for row in selected]
    valid = [flag for flag in flags if flag is not None]
    if not valid:
        unavailable = _unavailable("association_correctness_values_missing")
        return {
            "association_accuracy": unavailable,
            "association_evaluable_count": unavailable,
            "association_wrong_count": unavailable,
        }
    wrong_count = sum(flag is False for flag in valid)
    return {
        "association_accuracy": _available(
            (len(valid) - wrong_count) / len(valid), source
        ),
        "association_evaluable_count": _available(len(valid), source),
        "association_wrong_count": _available(wrong_count, source),
    }


def _safety_metrics(
    episode: D5LongRangeRegistrationEpisode,
    mot_scope: Mapping[str, Any],
    association_rows: Sequence[Mapping[str, str]],
    temporal_rows: Sequence[Mapping[str, str]],
    dropout_rows: Sequence[Mapping[str, str]],
    scope_name: str,
    camera: str | None,
) -> dict[str, dict[str, Any]]:
    idsw = _metric_from_keys(
        mot_scope,
        ("id_switch_count",),
        source=f"mot_continuity:{scope_name}",
        integer=True,
        missing_reason="id_switch_count_missing",
    )
    if camera is None:
        duplicate = _metric_from_keys(
            episode.metrics,
            ("duplicate_assignment_count",),
            source="metrics.json",
            integer=True,
            missing_reason="duplicate_assignment_count_missing",
        )
        truth = _metric_from_keys(
            episode.metrics,
            ("online_truth_use_count", "online_truth_identity_use_count"),
            source="metrics.json",
            integer=True,
            missing_reason="online_truth_use_count_missing",
        )
        rewrite = _metric_from_keys(
            episode.metrics,
            ("global_track_id_rewrite_count",),
            source="metrics.json",
            integer=True,
            missing_reason="global_track_id_rewrite_count_missing",
        )
    else:
        duplicate = _boolean_row_counter(
            association_rows,
            ("duplicate_assignment", "duplicate_assignment_used"),
            f"associations.csv:{scope_name}",
            "per_camera_duplicate_assignment_field_missing",
        )
        truth_rows = tuple(association_rows) + tuple(temporal_rows) + tuple(dropout_rows)
        if episode.online_replay:
            truth_rows = truth_rows + tuple(
                row
                for row in episode.online_replay
                if _camera_name(row) == camera
            )
        truth = _boolean_row_counter(
            truth_rows,
            ("truth_identity_used", "online_truth_used"),
            f"online_rows:{scope_name}",
            "per_camera_online_truth_field_missing",
        )
        rewrite = _boolean_row_counter(
            association_rows,
            ("global_track_id_rewritten", "global_track_id_rewrite"),
            f"associations.csv:{scope_name}",
            "per_camera_global_track_id_rewrite_field_missing",
        )
    return {
        "id_switch_count": idsw,
        "duplicate_assignment_count": duplicate,
        "online_truth_use_count": truth,
        "global_track_id_rewrite_count": rewrite,
    }


def _aggregate_metrics(
    scopes: Sequence[Mapping[str, Mapping[str, Any]]],
    *,
    scope_label: str,
) -> dict[str, dict[str, Any]]:
    if not scopes:
        return {name: _unavailable(f"no scopes for {scope_label}") for name in METRIC_NAMES}
    result: dict[str, dict[str, Any]] = {}
    for name in METRIC_NAMES:
        values = [scope[name] for scope in scopes]
        unavailable = [value for value in values if value["availability"] != "available"]
        if unavailable:
            result[name] = _unavailable(
                f"one_or_more_{scope_label.replace(' ', '_')}_values_unavailable"
            )
            continue
        raw = [value["value"] for value in values]
        source = f"D6 aggregate:{scope_label}"
        if name in _SUM_METRICS:
            result[name] = _available(sum(raw), source)
        elif name == "bounded_coast_max_age_s":
            result[name] = _available(max(raw), source)
        elif name == "crossing_unavailable_reasons":
            reasons: Counter[str] = Counter()
            for mapping in raw:
                reasons.update(mapping)
            result[name] = _available(dict(sorted(reasons.items())), source)
        elif name == "crossing_availability_ratio":
            total = sum(scope["crossing_total_count"]["value"] for scope in scopes)
            evaluable = sum(
                scope["crossing_evaluable_count"]["value"] for scope in scopes
            )
            result[name] = _available(evaluable / total if total else 0.0, source)
        elif name == "association_accuracy":
            count = sum(scope["association_evaluable_count"]["value"] for scope in scopes)
            wrong = sum(scope["association_wrong_count"]["value"] for scope in scopes)
            result[name] = _available((count - wrong) / count if count else 0.0, source)
        elif name in {"crossing_track_purity", "crossing_track_continuity"}:
            weights = [scope["crossing_evaluable_count"]["value"] for scope in scopes]
            weight_sum = sum(weights)
            if weight_sum <= 0:
                result[name] = _unavailable("no_evaluable_actual_crossing_windows")
            else:
                result[name] = _available(
                    sum(value * weight for value, weight in zip(raw, weights, strict=True))
                    / weight_sum,
                    source,
                )
        else:
            result[name] = _unavailable(f"unsupported aggregate rule for {name}")
    return result


def _evaluate_gates(
    metrics: Mapping[str, Mapping[str, Any]],
    thresholds: D5LongRangeRegistrationThresholds,
) -> dict[str, Any]:
    requirements = {
        "id_switch_count": ("= 0", lambda value: value == 0),
        "effective_short_gap_fragmentation_count": (
            "= 0",
            lambda value: value == 0,
        ),
        "binding_oscillation_count": ("= 0", lambda value: value == 0),
        "duplicate_assignment_count": ("= 0", lambda value: value == 0),
        "online_truth_use_count": ("= 0", lambda value: value == 0),
        "global_track_id_rewrite_count": ("= 0", lambda value: value == 0),
        "association_accuracy": (
            f">= {thresholds.association_min_accuracy:.2f}",
            lambda value: value >= thresholds.association_min_accuracy,
        ),
    }
    checks: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for name, (requirement, predicate) in requirements.items():
        metric = metrics[name]
        if metric["availability"] != "available":
            status = "unavailable"
            passed = False
            reason = str(metric.get("reason") or "metric unavailable")
        else:
            passed = bool(predicate(metric["value"]))
            status = "passed" if passed else "failed"
            reason = "threshold satisfied" if passed else "threshold not satisfied"
        checks[name] = {
            "status": status,
            "passed": passed,
            "requirement": requirement,
            "value": metric.get("value"),
            "reason": reason,
        }
        if not passed:
            failures.append(f"{name}:{status}:{reason}")

    crossing_total = metrics["crossing_total_count"]
    crossing_evaluable = metrics["crossing_evaluable_count"]
    crossing_ratio = metrics["crossing_availability_ratio"]
    crossing_available = all(
        item["availability"] == "available"
        for item in (crossing_total, crossing_evaluable, crossing_ratio)
    )
    if not crossing_available:
        crossing_passed = False
        crossing_status = "unavailable"
        crossing_reason = "actual crossing evidence unavailable; geometry preflight is not accepted"
    else:
        crossing_passed = bool(
            crossing_evaluable["value"] >= thresholds.crossing_min_evaluable_count
            and crossing_ratio["value"] >= thresholds.crossing_min_availability_ratio
        )
        crossing_status = "passed" if crossing_passed else "failed"
        crossing_reason = (
            f"actual evaluable={crossing_evaluable['value']}/{crossing_total['value']}, "
            f"ratio={crossing_ratio['value']:.6f}"
        )
    if not crossing_passed:
        failures.append(f"actual_crossing_gate:{crossing_status}:{crossing_reason}")
    structural_passed = all(check["passed"] for check in checks.values())
    return {
        "structural_checks": checks,
        "structural_gate_passed": structural_passed,
        "actual_crossing_gate": {
            "status": crossing_status,
            "passed": crossing_passed,
            "minimum_evaluable_count": thresholds.crossing_min_evaluable_count,
            "minimum_availability_ratio": thresholds.crossing_min_availability_ratio,
            "actual_total_count": crossing_total.get("value"),
            "actual_evaluable_count": crossing_evaluable.get("value"),
            "actual_availability_ratio": crossing_ratio.get("value"),
            "geometry_preflight_accepted": False,
            "reason": crossing_reason,
        },
        "overall_gate_passed": structural_passed and crossing_passed,
        "failure_reasons": failures,
    }


def _resolve_evidence_dir(requested: Path) -> Path:
    direct = requested / "metrics.json"
    nested = requested / "coverage_safe" / "metrics.json"
    if direct.exists() or (requested / "mot_continuity.json").exists():
        return requested
    if nested.exists() or (requested / "coverage_safe" / "mot_continuity.json").exists():
        return requested / "coverage_safe"
    return requested


def _load_json_mapping(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.is_file():
        return {}, {
            "path": str(path),
            "availability": "unavailable",
            "reason": "file_missing",
            "schema_version": None,
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be an object: {path}")
    mapping = dict(value)
    return mapping, {
        "path": str(path),
        "availability": "available",
        "reason": None,
        "schema_version": _optional_string(mapping.get("schema_version")),
    }


def _load_jsonl_objects(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.is_file():
        return [], {
            "path": str(path),
            "availability": "unavailable",
            "reason": "file_missing",
            "row_count": 0,
        }
    rows: list[dict[str, Any]] = []
    for line_number, text in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not text.strip():
            continue
        value = json.loads(text)
        if not isinstance(value, Mapping):
            raise ValueError(f"JSONL line {line_number} is not an object: {path}")
        rows.append(dict(value))
    if not rows:
        return [], {
            "path": str(path),
            "availability": "unavailable",
            "reason": "empty_file_no_records",
            "row_count": 0,
        }
    return rows, {
        "path": str(path),
        "availability": "available",
        "reason": None,
        "row_count": len(rows),
    }


def _validate_frozen_baseline(
    evidence_dir: Path,
    manifest: Mapping[str, Any],
    online_replay: Sequence[Mapping[str, Any]],
    offline_sidecar: Mapping[str, Any],
) -> dict[str, Any]:
    if not manifest:
        return {
            "availability": "unavailable",
            "reason": "baseline_manifest_missing",
            "source": None,
        }
    if not online_replay or not offline_sidecar:
        return {
            "availability": "unavailable",
            "reason": "frozen_online_replay_or_truth_sidecar_missing",
            "source": None,
        }
    if manifest.get("schema_version") != "d5-long-range-baseline-v1":
        return {
            "availability": "unavailable",
            "reason": "unsupported_frozen_baseline_schema",
            "source": None,
        }
    if offline_sidecar.get("offline_truth_only") is not True:
        return {
            "availability": "unavailable",
            "reason": "truth_sidecar_not_offline_only",
            "source": None,
        }
    expected_hashes = manifest.get("frozen_fixture_sha256")
    if not isinstance(expected_hashes, Mapping):
        return {
            "availability": "unavailable",
            "reason": "frozen_fixture_sha256_missing",
            "source": None,
        }
    for name in ("online_replay.jsonl", "offline_truth_sidecar.json"):
        expected = _optional_string(expected_hashes.get(name))
        path = evidence_dir / name
        if expected is None or not path.is_file() or _sha256(path) != expected:
            return {
                "availability": "unavailable",
                "reason": f"frozen_fixture_sha256_mismatch:{name}",
                "source": None,
            }
    expected_count = _number(manifest.get("online_fixture_record_count"))
    if (
        expected_count is None
        or not float(expected_count).is_integer()
        or int(expected_count) != len(online_replay)
    ):
        return {
            "availability": "unavailable",
            "reason": "online_fixture_record_count_mismatch",
            "source": None,
        }
    if any(_parse_bool(row.get("truth_identity_used")) is not False for row in online_replay):
        return {
            "availability": "unavailable",
            "reason": "online_replay_truth_identity_policy_violation",
            "source": None,
        }
    boundary = manifest.get("identity_boundary")
    if not isinstance(boundary, Mapping) or not (
        boundary.get("online_actor_or_object_identity_present") is False
        and boundary.get("truth_sidecar_offline_only") is True
        and boundary.get("global_track_id_center_owned") is True
    ):
        return {
            "availability": "unavailable",
            "reason": "frozen_identity_boundary_invalid",
            "source": None,
        }
    return {
        "availability": "available",
        "reason": None,
        "source": "baseline_manifest+online_replay+offline_truth_sidecar",
    }


def _frozen_baseline_metrics(
    manifest: Mapping[str, Any],
    offline_sidecar: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    core = manifest.get("core_metrics")
    failures = manifest.get("failure_counts")
    if not isinstance(core, Mapping) or not isinstance(failures, Mapping):
        return {}, {}
    incorrect = offline_sidecar.get("incorrect_associations")
    wrong_count = len(incorrect) if isinstance(incorrect, list) else None
    crossing_total = core.get("crossing_window_count")
    crossing_evaluable = core.get("crossing_evaluable_window_count")
    total_number = _number(crossing_total)
    evaluable_number = _number(crossing_evaluable)
    not_evaluable = (
        int(total_number - evaluable_number)
        if total_number is not None
        and evaluable_number is not None
        and float(total_number).is_integer()
        and float(evaluable_number).is_integer()
        else None
    )
    metrics = {
        "schema_version": "d5-long-range-cv-scan-metrics-v2-frozen-sidecar",
        "seed": core.get("seed"),
        "association_accuracy": core.get("association_accuracy"),
        "association_evaluable_count": core.get("association_evaluable_count"),
        "association_wrong_count": wrong_count,
        "id_switch_count": core.get("id_switch_count"),
        "duplicate_assignment_count": core.get("duplicate_assignment_count"),
        "online_truth_identity_use_count": core.get(
            "online_truth_identity_use_count"
        ),
        "global_track_id_rewrite_count": core.get(
            "global_track_id_rewrite_count"
        ),
        "geometric_binding_switch_count": core.get(
            "geometric_binding_switch_count"
        ),
    }
    mot_aggregate = {
        "fragmentation_count": core.get("short_gap_fragmentation_count"),
        "reacquisition_count": core.get("reacquisition_count"),
        "reacquisition_identity_changed_count": core.get("reacquisition_count"),
        "id_switch_count": core.get("id_switch_count"),
        "crossing_window_count": crossing_total,
        "crossing_evaluable_window_count": crossing_evaluable,
        "crossing_not_evaluable_window_count": not_evaluable,
        "crossing_window_results": [
            {"availability": False, "unavailable_reason": reason}
            for reason, count in (
                failures.get("crossing_unavailable_reason_counts", {}) or {}
            ).items()
            for _ in range(int(count))
        ],
    }
    return metrics, {
        "schema_version": "d5-long-range-mot-continuity-v2-frozen-sidecar",
        "aggregate": mot_aggregate,
        "by_camera": {},
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_csv_rows(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not path.is_file():
        return [], {
            "path": str(path),
            "availability": "unavailable",
            "reason": "file_missing",
            "fieldnames": [],
        }
    if path.stat().st_size == 0:
        return [], {
            "path": str(path),
            "availability": "unavailable",
            "reason": "empty_file_no_header",
            "fieldnames": [],
            "row_count": 0,
        }
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            return [], {
                "path": str(path),
                "availability": "unavailable",
                "reason": "empty_file_no_header",
                "fieldnames": [],
                "row_count": 0,
            }
        rows = [dict(row) for row in reader]
    return rows, {
        "path": str(path),
        "availability": "available",
        "reason": None,
        "fieldnames": list(reader.fieldnames),
        "row_count": len(rows),
    }


def _mot_aggregate(mot: Mapping[str, Any]) -> Mapping[str, Any]:
    aggregate = mot.get("aggregate")
    return aggregate if isinstance(aggregate, Mapping) else {}


def _mot_camera(mot: Mapping[str, Any], camera: str) -> Mapping[str, Any]:
    by_camera = mot.get("by_camera")
    if not isinstance(by_camera, Mapping):
        return {}
    value = by_camera.get(camera)
    return value if isinstance(value, Mapping) else {}


def _camera_names(episode: D5LongRangeRegistrationEpisode) -> list[str]:
    names: set[str] = set()
    by_camera = episode.mot_continuity.get("by_camera")
    if isinstance(by_camera, Mapping):
        names.update(str(name) for name in by_camera)
    for rows in (
        episode.associations,
        episode.temporal_binding_events,
        episode.dropout_events,
        episode.online_replay,
    ):
        for row in rows:
            camera = _camera_name(row)
            if camera:
                names.add(camera)
    return sorted(names)


def _rows_for_camera(
    rows: Sequence[Mapping[str, str]], camera: str | None
) -> list[Mapping[str, str]]:
    if camera is None:
        return list(rows)
    return [row for row in rows if _camera_name(row) == camera]


def _camera_name(row: Mapping[str, Any]) -> str | None:
    resource = _optional_string(row.get("resource_id"))
    raw = _optional_string(
        row.get("camera_vehicle_name") or row.get("camera_id") or row.get("camera")
    )
    if resource and (raw is None or raw.isdigit() or raw in {"0", "front_center"}):
        return resource
    if raw and ":" in raw:
        return raw.split(":", 1)[0]
    return raw or resource


def _metric_from_keys(
    mapping: Mapping[str, Any],
    keys: Sequence[str],
    *,
    source: str,
    missing_reason: str,
    integer: bool = False,
) -> dict[str, Any]:
    for key in keys:
        if key not in mapping or mapping[key] is None:
            continue
        value = _number(mapping[key])
        if value is None or (integer and not float(value).is_integer()):
            return _unavailable(f"{key}_invalid")
        if integer:
            value = int(value)
        return _available(value, f"{source}:{key}")
    return _unavailable(missing_reason)


def _boolean_row_counter(
    rows: Sequence[Mapping[str, str]],
    keys: Sequence[str],
    source: str,
    missing_reason: str,
) -> dict[str, Any]:
    fields = {key for row in rows for key in row}
    key = _first_present(fields, keys)
    if key is None:
        return _unavailable(missing_reason)
    values = [_parse_bool(row.get(key)) for row in rows]
    if any(value is None for value in values):
        return _unavailable(f"{key}_contains_invalid_boolean")
    return _available(sum(value is True for value in values), source)


def _is_short_gap_row(row: Mapping[str, str], fields: set[str]) -> bool:
    explicit = _parse_bool(row.get("short_gap")) if "short_gap" in fields else None
    if explicit is not None:
        return explicit
    event = _event_name(row)
    return "short_gap" in event or event in {
        "coast_recovered_same_id",
        "coast_expired",
    }


def _event_name(row: Mapping[str, Any]) -> str:
    for key in ("dropout_event", "binding_event", "event_type", "event", "state"):
        value = _optional_string(row.get(key))
        if value:
            return value.lower()
    return ""


def _is_binding_switch_event(row: Mapping[str, str]) -> bool:
    explicit = _parse_bool(row.get("switch_event"))
    if explicit is not None:
        return explicit
    event = _event_name(row)
    incumbent = _optional_string(row.get("incumbent_global_track_id"))
    candidate = _optional_string(row.get("candidate_global_track_id"))
    if event == "expired":
        return incumbent is not None
    return bool(incumbent and candidate and incumbent != candidate)


def _binding_oscillation_count(rows: Sequence[Mapping[str, str]]) -> int:
    if any("binding_oscillation" in row for row in rows):
        return sum(_parse_bool(row.get("binding_oscillation")) is True for row in rows)
    grouped: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        if _event_name(row) != "confirmed":
            continue
        grouped[(_camera_name(row) or "unknown", str(row.get("local_track_id", "")))].append(row)
    count = 0
    for transitions in grouped.values():
        transitions.sort(key=lambda row: _number(row.get("measurement_timestamp")) or 0.0)
        previous: tuple[str, str] | None = None
        for row in transitions:
            incumbent = _optional_string(row.get("incumbent_global_track_id"))
            candidate = _optional_string(row.get("candidate_global_track_id"))
            if not incumbent or not candidate or incumbent == candidate:
                continue
            current = (incumbent, candidate)
            if previous == (candidate, incumbent):
                count += 1
            previous = current
    return count


def _has_geometry_preflight(metrics: Mapping[str, Any]) -> bool:
    return any("preflight" in str(key).lower() and "crossing" in str(key).lower() for key in metrics)


def _episode_seed(metrics: Mapping[str, Any]) -> int | None:
    for key in ("seed", "scenario_seed", "random_seed"):
        value = _number(metrics.get(key))
        if value is not None and float(value).is_integer():
            return int(value)
    scenario = metrics.get("scenario")
    if isinstance(scenario, Mapping):
        return _episode_seed(scenario)
    return None


def _per_episode_rows(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in result["episodes"]:
        scopes = [("aggregate", None, episode["aggregate"])] + [
            ("camera", camera, metrics)
            for camera, metrics in sorted(episode["per_camera"].items())
        ]
        for scope, camera, metrics in scopes:
            row: dict[str, Any] = {
                "episode_id": episode["episode_id"],
                "evidence_dir": episode["evidence_dir"],
                "scope": scope,
                "camera": camera,
                "status": episode["status"],
            }
            for name in METRIC_NAMES:
                metric = metrics[name]
                value = metric.get("value")
                row[name] = (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, Mapping)
                    else value
                )
                row[f"{name}_availability"] = metric["availability"]
                row[f"{name}_reason"] = metric.get("reason")
            rows.append(row)
    return rows


def _write_rows_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = list(rows[0]) if rows else ["episode_id", "scope", "camera", "status"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_summary_plot(result: Mapping[str, Any], path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        path.write_bytes(_MINIMAL_PNG)
        return
    episodes = result["episodes"]
    labels = [str(item["episode_id"]) for item in episodes]
    x = list(range(len(labels)))
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    _plot_metric_lines(
        axes[0, 0],
        x,
        episodes,
        (
            ("measured_short_gap_count", "measured short gap"),
            ("effective_short_gap_fragmentation_count", "effective fragmentation"),
            ("long_reacquisition_count", "long reacquisition"),
        ),
        "Gap and reacquisition",
    )
    binding_names = (
        "binding_switch_proposed_count",
        "binding_switch_pending_count",
        "binding_switch_held_count",
        "binding_switch_confirmed_count",
        "binding_switch_expired_count",
        "binding_oscillation_count",
    )
    binding_values = [
        _plot_value(result["aggregate"][name]) for name in binding_names
    ]
    axes[0, 1].bar(range(len(binding_names)), binding_values, color="#4C78A8")
    axes[0, 1].set_xticks(
        range(len(binding_names)),
        ["proposed", "pending", "held", "confirmed", "expired", "oscillation"],
        rotation=25,
    )
    axes[0, 1].set_title("Binding events")
    axes[0, 1].grid(axis="y", alpha=0.25)

    _plot_metric_lines(
        axes[1, 0],
        x,
        episodes,
        (
            ("crossing_total_count", "actual total"),
            ("crossing_evaluable_count", "actual evaluable"),
        ),
        "Actual crossing availability",
    )
    ratio_axis = axes[1, 0].twinx()
    ratio_axis.plot(
        x,
        [_plot_value(item["aggregate"]["crossing_availability_ratio"]) for item in episodes],
        color="#E45756",
        marker="s",
        label="availability ratio",
    )
    ratio_axis.set_ylim(0.0, 1.05)

    safety_names = (
        "id_switch_count",
        "duplicate_assignment_count",
        "online_truth_use_count",
        "global_track_id_rewrite_count",
    )
    safety_values = [_plot_value(result["aggregate"][name]) for name in safety_names]
    axes[1, 1].bar(
        range(len(safety_names)),
        safety_values,
        color=["#F58518", "#54A24B", "#B279A2", "#FF9DA6"],
    )
    axes[1, 1].set_xticks(
        range(len(safety_names)),
        ["IDSW", "duplicate", "truth use", "GT rewrite"],
        rotation=20,
    )
    axes[1, 1].set_title("Safety counters")
    accuracy_axis = axes[1, 1].twinx()
    accuracy = result["aggregate"]["association_accuracy"]
    if accuracy["availability"] == "available":
        accuracy_axis.axhline(
            float(accuracy["value"]), color="#4C78A8", linewidth=2, label="accuracy"
        )
    accuracy_axis.set_ylim(0.0, 1.05)
    accuracy_axis.set_ylabel("association accuracy")
    axes[1, 1].grid(axis="y", alpha=0.25)

    for axis in (axes[0, 0], axes[1, 0]):
        axis.set_xticks(x, labels, rotation=20, ha="right")
    figure.suptitle("D5 long-range registration offline evaluation")
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _plot_metric_lines(
    axis: Any,
    x: Sequence[int],
    episodes: Sequence[Mapping[str, Any]],
    specs: Sequence[tuple[str, str]],
    title: str,
) -> None:
    for name, label in specs:
        axis.plot(
            x,
            [_plot_value(item["aggregate"][name]) for item in episodes],
            marker="o",
            linewidth=1.4,
            label=label,
        )
    axis.set_title(title)
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)


def _plot_value(metric: Mapping[str, Any]) -> float:
    if metric.get("availability") != "available":
        return math.nan
    value = _number(metric.get("value"))
    return float(value) if value is not None else math.nan


def _available(value: Any, source: str) -> dict[str, Any]:
    return {
        "availability": "available",
        "value": value,
        "reason": None,
        "source": source,
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "value": None,
        "reason": str(reason),
        "source": None,
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _first_present(values: Iterable[str], candidates: Sequence[str]) -> str | None:
    value_set = set(values)
    return next((candidate for candidate in candidates if candidate in value_set), None)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_value(metric: Mapping[str, Any]) -> str:
    if metric.get("availability") != "available":
        return "不可用"
    value = metric.get("value")
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _format_check_value(check: Mapping[str, Any]) -> str:
    if check.get("value") is None:
        return str(check.get("reason") or "不可用")
    value = check["value"]
    return f"{value:.6f}" if isinstance(value, float) else str(value)


def _metric_note(metric: Mapping[str, Any]) -> str:
    return str(metric.get("reason") or metric.get("source") or "")


def _metric_label(name: str) -> str:
    labels = {
        "measured_short_gap_count": "实测短缺口数",
        "measured_short_gap_total_duration_s": "实测短缺口总时长(秒)",
        "effective_short_gap_fragmentation_count": "有效短缺口中断数",
        "bounded_coast_event_count": "有界保持事件数",
        "bounded_coast_frame_count": "有界保持帧数",
        "bounded_coast_max_age_s": "最大保持时长(秒)",
        "bounded_coast_same_id_recovery_count": "同编号恢复数",
        "coast_expiry_count": "保持过期数",
        "long_reacquisition_count": "长期重发现数",
        "long_reacquisition_identity_change_count": "长期重发现编号变化数",
        "binding_switch_proposed_count": "绑定切换提出数",
        "binding_switch_pending_count": "绑定切换待确认数",
        "binding_switch_held_count": "绑定切换保持数",
        "binding_switch_confirmed_count": "绑定切换确认数",
        "binding_switch_expired_count": "绑定切换过期数",
        "binding_oscillation_count": "绑定振荡数",
        "geometric_binding_switch_count": "几何绑定切换数",
        "crossing_total_count": "实际交叉窗口总数",
        "crossing_evaluable_count": "实际交叉可评分数",
        "crossing_unavailable_count": "实际交叉不可评分数",
        "crossing_availability_ratio": "实际交叉可评分比例",
        "crossing_unavailable_reasons": "实际交叉不可评分原因",
        "crossing_id_switch_count": "交叉窗口身份切换数",
        "crossing_track_purity": "交叉窗口轨迹纯度",
        "crossing_track_continuity": "交叉窗口轨迹连续性",
        "association_accuracy": "关联准确率",
        "association_evaluable_count": "可评分关联数",
        "association_wrong_count": "错误关联数",
        "id_switch_count": "身份切换数",
        "duplicate_assignment_count": "重复分配数",
        "online_truth_use_count": "在线真值使用数",
        "global_track_id_rewrite_count": "全局航迹编号改写数",
    }
    return labels.get(name, name)


_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDAT\x08\xd7c\xf8\xcf"
    b"\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


__all__ = [
    "D5_LONG_RANGE_REGISTRATION_EVALUATION_DATE",
    "D5_LONG_RANGE_REGISTRATION_SCHEMA_VERSION",
    "D5LongRangeRegistrationEpisode",
    "D5LongRangeRegistrationReportGenerator",
    "D5LongRangeRegistrationThresholds",
    "evaluate_d5_long_range_registration",
    "load_d5_long_range_registration_episode",
    "load_d5_long_range_registration_episodes",
    "render_d5_long_range_registration_markdown",
    "write_d5_long_range_registration_report",
]
