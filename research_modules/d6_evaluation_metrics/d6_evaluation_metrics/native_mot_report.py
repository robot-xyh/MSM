"""Offline reporting for real AirSim ByteTrack and BoT-SORT evidence."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


NATIVE_MOT_REPORT_SCHEMA_VERSION = "d6-native-mot-airsim-report-v1"
LEVELS = (
    "discovery_preflight",
    "range_precheck_40_frame_class",
    "confirmation_102_frame",
)
METRICS = (
    "accepted_detection_rate",
    "native_active_frame_rate",
    "local_continuity",
    "terminal_local_id_switch_count",
    "fallback_frame_count",
    "warmup_excluded_p95_latency_ms",
    "offline_detector_precision",
    "offline_detector_recall",
    "native_mot_admitted",
)
CSV_COLUMNS = (
    ("evidence_level", "证据层级"),
    ("evidence_grade_zh", "证据等级说明"),
    ("case_id", "案例ID"),
    ("stage", "原始阶段"),
    ("tracker_backend", "跟踪器"),
    ("target_distance_m", "目标距离_m"),
    ("confidence_threshold", "置信度阈值"),
    ("frame_count", "实际帧数"),
    ("seed", "随机种子"),
    ("camera_width", "相机宽度_px"),
    ("camera_height", "相机高度_px"),
    ("camera_fov_deg", "相机视场角_deg"),
    ("accepted_detection_count", "接受检测数"),
    ("accepted_detection_rate", "检测帧率"),
    ("native_active_frame_rate", "原生MOT激活率"),
    ("local_continuity", "局部航迹连续率"),
    ("terminal_local_id_switch_count", "局部ID切换数"),
    ("fallback_frame_count", "Fallback帧数"),
    ("warmup_excluded_p95_latency_ms", "P95延迟_ms"),
    ("offline_detector_precision", "离线检测精确率"),
    ("offline_detector_recall", "离线检测召回率"),
    ("native_mot_admitted", "是否通过准入"),
    ("rejection_reasons", "准入拒绝原因"),
    ("online_truth_use_count", "在线Truth使用数"),
    ("truth_identity_used_online", "在线是否使用Truth身份"),
    ("global_track_id_rewrite_count", "全局航迹ID改写数"),
    ("source_path", "证据路径"),
    *((f"{name}_availability", f"{name}_可用性") for name in METRICS),
)


@dataclass(frozen=True)
class NativeMotAirSimInputs:
    preflight_rows: str | Path
    range_precheck_rows: str | Path
    confirmation_rows: str | Path


class NativeMotAirSimReportGenerator:
    """Write CSV, JSON, Chinese Markdown, and metric PNG without AirSim control."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: NativeMotAirSimInputs,
        title: str = "P1 AirSim 原生多目标跟踪专项报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rows, manifest = load_native_mot_airsim_rows(inputs)
        summary = summarize_native_mot_airsim_rows(rows, manifest=manifest)

        csv_path = output_dir / "native_mot_cases_zh.csv"
        _write_csv(rows, csv_path)
        json_path = output_dir / "native_mot_summary_zh.json"
        json_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        plot_path = output_dir / "native_mot_metrics_zh.png"
        _write_plot(rows, summary, plot_path)
        markdown_path = output_dir / "P1_NATIVE_MOT_AIRSIM_REPORT.md"
        markdown_path.write_text(
            _render_markdown(
                rows,
                summary,
                title=title,
                plot_name=plot_path.name,
                csv_name=csv_path.name,
                json_name=json_path.name,
            ),
            encoding="utf-8",
        )
        return {
            "cases_csv": csv_path,
            "summary_json": json_path,
            "markdown": markdown_path,
            "plot": plot_path,
        }


def load_native_mot_airsim_rows(
    inputs: NativeMotAirSimInputs,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    specs = zip(
        LEVELS,
        (
            Path(inputs.preflight_rows),
            Path(inputs.range_precheck_rows),
            Path(inputs.confirmation_rows),
        ),
    )
    rows: list[dict[str, Any]] = []
    manifest: dict[str, dict[str, Any]] = {}
    for level, path in specs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise ValueError(f"native MOT evidence must be a JSON array: {path}")
        source_rows = [dict(item) for item in payload if isinstance(item, Mapping)]
        if len(source_rows) != len(payload):
            raise ValueError(f"native MOT evidence contains non-object rows: {path}")
        manifest[level] = {
            "status": "available",
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "row_count": len(source_rows),
            "actual_frame_counts": sorted(
                {int(item["frame_count"]) for item in source_rows if item.get("frame_count") is not None}
            ),
        }
        rows.extend(
            _normalize_row(item, level=level, source_path=path)
            for item in source_rows
        )
    return rows, manifest


def summarize_native_mot_airsim_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    truth_count = sum(int(row.get("online_truth_use_count") or 0) for row in rows)
    truth_identity_count = sum(bool(row.get("truth_identity_used_online")) for row in rows)
    rewrite_count = sum(int(row.get("global_track_id_rewrite_count") or 0) for row in rows)
    confirmations = [row for row in rows if row.get("evidence_level") == LEVELS[2]]
    reasons = Counter(
        reason for row in rows for reason in _sequence(row.get("rejection_reasons"))
    )
    return {
        "schema_version": NATIVE_MOT_REPORT_SCHEMA_VERSION,
        "offline_only": True,
        "airsim_screenshots_saved": False,
        "source_manifest": dict(manifest or {}),
        "comparability_policy": {
            "pool_evidence_levels": False,
            "preflight_role": "discovery_only",
            "range_precheck_role": "nominal_40_frame_short_check_actual_42_frames",
            "confirmation_role": "102_frame_confirmation",
            "statement_zh": "约40帧短检查与102帧确认不是同等级证据，禁止合并样本或用短检查替代确认。",
        },
        "row_count": len(rows),
        "by_evidence_level": {
            level: _group_rows([row for row in rows if row.get("evidence_level") == level])
            for level in LEVELS
        },
        "rejection_reason_counts": dict(reasons),
        "truth_isolation": {
            "status": "pass" if truth_count == truth_identity_count == rewrite_count == 0 else "fail",
            "online_truth_use_count": truth_count,
            "truth_identity_used_online_count": truth_identity_count,
            "global_track_id_rewrite_count": rewrite_count,
            "offline_truth_role": "evaluation_only_after_online_tracking",
        },
        "confirmation_comparison": {
            str(row.get("tracker_backend")): {
                key: row.get(key)
                for key in (
                    "frame_count",
                    "target_distance_m",
                    *METRICS,
                    "rejection_reasons",
                )
            }
            for row in confirmations
        },
        "结论_zh": _conclusions(rows),
    }


def _normalize_row(
    item: Mapping[str, Any], *, level: str, source_path: Path
) -> dict[str, Any]:
    row = dict(item)
    frames = _number(item.get("frame_count"))
    detections = _number(item.get("accepted_detection_count"))
    row["accepted_detection_rate"] = (
        detections / frames if detections is not None and frames not in {None, 0.0} else None
    )
    row.update(
        evidence_level=level,
        evidence_grade_zh={
            LEVELS[0]: "发现性预检（实际32帧）",
            LEVELS[1]: "约40帧距离短检查（实际42帧）",
            LEVELS[2]: "102帧确认试验",
        }[level],
        source_path=str(source_path),
    )
    for metric in METRICS:
        row[f"{metric}_availability"] = (
            "available" if row.get(metric) is not None else "unavailable"
        )
    return row


def _group_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        key = f"{row.get('tracker_backend', 'unknown')}@{_distance(row.get('target_distance_m'))}"
        grouped.setdefault(key, []).append(row)
    return {
        key: {
            "case_count": len(items),
            "actual_frame_counts": sorted({int(row["frame_count"]) for row in items}),
            "confidence_thresholds": sorted({float(row["confidence_threshold"]) for row in items}),
            "metrics": {metric: _metric_summary(items, metric) for metric in METRICS},
            "rejection_reason_counts": dict(
                Counter(
                    reason
                    for row in items
                    for reason in _sequence(row.get("rejection_reasons"))
                )
            ),
        }
        for key, items in sorted(grouped.items())
    }


def _metric_summary(rows: Sequence[Mapping[str, Any]], metric: str) -> dict[str, Any]:
    values = [row.get(metric) for row in rows if row.get(metric) is not None]
    numeric = [float(value) for value in values if isinstance(value, (bool, int, float))]
    return {
        "status": "available" if values else "unavailable",
        "available_count": len(values),
        "unavailable_count": len(rows) - len(values),
        "mean": sum(numeric) / len(numeric) if numeric else None,
        "min": min(numeric) if numeric else None,
        "max": max(numeric) if numeric else None,
        "sum": sum(numeric) if numeric else None,
    }


def _write_csv(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=[label for _, label in CSV_COLUMNS])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {label: _csv_value(row.get(field)) for field, label in CSV_COLUMNS}
            )


def _write_plot(
    rows: Sequence[Mapping[str, Any]], summary: Mapping[str, Any], path: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    cjk_font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if cjk_font_path.exists():
        font_manager.fontManager.addfont(str(cjk_font_path))
        cjk_family = font_manager.FontProperties(fname=str(cjk_font_path)).get_name()
    else:
        cjk_family = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = [cjk_family, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    short = [row for row in rows if row.get("evidence_level") == LEVELS[1]]
    confirmed = [row for row in rows if row.get("evidence_level") == LEVELS[2]]
    colors = {"bytetrack": "#2563eb", "botsort": "#d97706"}
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.0))
    for backend in ("bytetrack", "botsort"):
        selected = sorted(
            (row for row in short if row.get("tracker_backend") == backend),
            key=lambda row: float(row.get("target_distance_m") or 0),
        )
        distance = [row.get("target_distance_m") for row in selected]
        axes[0, 0].plot(
            distance,
            [row.get("accepted_detection_rate") for row in selected],
            marker="o",
            label=f"{backend} 检测",
            color=colors[backend],
        )
        axes[0, 0].plot(
            distance,
            [row.get("native_active_frame_rate") for row in selected],
            marker="x",
            linestyle="--",
            label=f"{backend} native",
            color=colors[backend],
        )
        axes[0, 1].plot(
            distance,
            [row.get("warmup_excluded_p95_latency_ms") for row in selected],
            marker="o",
            label=backend,
            color=colors[backend],
        )
    axes[0, 0].set(title="约40帧短检查：检测与Native率", xlabel="距离 (m)", ylabel="比例")
    axes[0, 0].set_ylim(-0.03, 1.05)
    axes[0, 0].legend(fontsize=8)
    axes[0, 1].set(title="约40帧短检查：P95处理延迟", xlabel="距离 (m)", ylabel="P95 (ms)")
    axes[0, 1].legend()
    x = list(range(len(confirmed)))
    width = 0.19
    for offset, (field, label) in enumerate(
        (
            ("native_active_frame_rate", "Native率"),
            ("local_continuity", "连续率"),
            ("offline_detector_precision", "Precision"),
            ("offline_detector_recall", "Recall"),
        )
    ):
        axes[1, 0].bar(
            [value + (offset - 1.5) * width for value in x],
            [row.get(field) or 0.0 for row in confirmed],
            width=width,
            label=label,
        )
    axes[1, 0].set_xticks(x, [str(row.get("tracker_backend")) for row in confirmed])
    axes[1, 0].set_ylim(0, 1.05)
    axes[1, 0].set(title="102帧确认：稳定性与离线检测准确性", ylabel="比例")
    axes[1, 0].legend(fontsize=8)
    reasons = Counter(summary.get("rejection_reason_counts", {})).most_common(6)
    reason_labels = {
        "insufficient_frame_count": "帧数不足",
        "native_active_frame_rate_below_threshold": "Native率不足",
        "offline_detector_recall_below_threshold": "离线Recall不足",
        "accepted_detection_count_below_threshold": "检测数不足",
        "local_continuity_unavailable": "Continuity不可用",
        "terminal_local_id_switch_metric_unavailable": "IDSW不可用",
        "offline_detector_precision_unavailable": "Precision不可用",
        "offline_detector_recall_unavailable": "Recall不可用",
        "offline_detector_precision_below_threshold": "离线Precision不足",
    }
    axes[1, 1].barh(
        [reason_labels.get(name, name) for name, _ in reversed(reasons)],
        [count for _, count in reversed(reasons)],
        color="#64748b",
    )
    axes[1, 1].set(title="主要准入拒绝原因", xlabel="案例次数")
    for axis in axes.flat:
        axis.grid(alpha=0.25)
    fig.suptitle("AirSim 原生 ByteTrack / BoT-SORT 分层证据", fontsize=15)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _render_markdown(
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    *,
    title: str,
    plot_name: str,
    csv_name: str,
    json_name: str,
) -> str:
    manifest = summary.get("source_manifest", {})
    lines = [
        f"# {title}",
        "",
        "## 1. 评估范围",
        "",
        "本报告由 D6 离线消费真实 AirSim 已写盘 MOT 结果生成。D6 未启动或控制 AirSim，未保存 AirSim 截图，也未将离线 truth 回流检测或跟踪。",
        "",
        "| 项目 | 配置 |",
        "|---|---|",
        f"| 案例数 | {len(rows)} |",
        f"| 跟踪器 | {', '.join(sorted({str(row.get('tracker_backend')) for row in rows}))} |",
        f"| 距离 | {', '.join(_distance(value) for value in sorted({row.get('target_distance_m') for row in rows}))} |",
        f"| 相机 | {_camera(rows)} |",
        f"| Target asset | {', '.join(sorted({str(row.get('target_asset_name')) for row in rows}))} |",
        f"| Seed | {', '.join(str(value) for value in sorted({row.get('seed') for row in rows}))} |",
        "",
        "## 2. 证据等级",
        "",
        "| 层级 | 原始文件 | 案例数 | 实际帧数 | 用途 |",
        "|---|---|---:|---|---|",
    ]
    roles = {
        LEVELS[0]: "发现性检查，不作准入结论",
        LEVELS[1]: "约40帧距离短检查，筛查20/30/50m可见性",
        LEVELS[2]: "102帧确认，作为本轮较高等级证据",
    }
    for level in LEVELS:
        item = manifest.get(level, {})
        lines.append(
            f"| {level} | `{item.get('path', 'NA')}` | {item.get('row_count', 0)} | {item.get('actual_frame_counts', [])} | {roles[level]} |"
        )
    lines.extend(
        [
            "",
            "> 约40帧 precheck 本次实际记录为每案例 42 帧；confirmation 为每案例 102 帧。二者不能合并为同一统计样本，也不能把短检查的通过或失败当作 102 帧确认结论。32 帧 discovery preflight 的证据等级更低。",
            "",
            "## 3. 约40帧距离短检查",
            "",
            _metric_table([row for row in rows if row.get("evidence_level") == LEVELS[1]]),
            "",
            "20 m 时两个 backend 均在所有帧产生检测并激活原生 MOT，continuity 为 1、IDSW 和 fallback 为 0。30 m 和 50 m 均没有接受检测，native rate 为 0；continuity、precision 和 recall 因无有效样本保持 unavailable，不能写成 0。",
            "",
            "## 4. 102帧确认",
            "",
            _metric_table([row for row in rows if row.get("evidence_level") == LEVELS[2]]),
            "",
            "ByteTrack 与 BoT-SORT 在 20 m 均达到 native rate=1、continuity=1、IDSW=0、fallback=0。ByteTrack P95 延迟更低。两者仍未通过准入，因为离线 precision/recall 均明显低于阈值；原生跟踪链路稳定不等于检测与离线 truth 几何匹配已经合格。",
            "",
            "## 5. 准入拒绝原因",
            "",
            "| 原因 | 案例数 |",
            "|---|---:|",
        ]
    )
    for reason, count in Counter(summary.get("rejection_reason_counts", {})).most_common():
        lines.append(f"| `{reason}` | {count} |")
    truth = summary.get("truth_isolation", {})
    lines.extend(
        [
            "",
            "## 6. Truth 隔离与安全合同",
            "",
            f"- Truth 隔离状态：`{truth.get('status')}`。",
            f"- 在线 truth 使用数：`{truth.get('online_truth_use_count')}`。",
            f"- 在线 truth identity 使用案例数：`{truth.get('truth_identity_used_online_count')}`。",
            f"- `global_track_id` 改写数：`{truth.get('global_track_id_rewrite_count')}`。",
            "- precision/recall 与 IDSW 只在在线跟踪结果形成后使用离线 truth 计算，不进入在线关联。",
            "",
            "## 7. 图表",
            "",
            f"![AirSim 原生 MOT 分层指标]({plot_name})",
            "",
            "## 8. 结果分析",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in summary.get("结论_zh", []))
    lines.extend(
        [
            "",
            "## 9. 文件索引",
            "",
            f"- 中文逐案例 CSV：`{csv_name}`",
            f"- 中文汇总 JSON：`{json_name}`",
            f"- 指标图：`{plot_name}`",
            "- 本报告未生成或保存 AirSim 场景截图。",
            "",
        ]
    )
    return "\n".join(lines)


def _metric_table(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "| Backend | 距离(m) | 帧数 | 检测率 | Native率 | Continuity | IDSW | Fallback | P95(ms) | Precision | Recall | 准入 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(rows, key=lambda item: (item.get("target_distance_m"), item.get("tracker_backend"))):
        values = {
            "backend": row.get("tracker_backend"),
            "distance": _display(row.get("target_distance_m")),
            "frames": _display(row.get("frame_count")),
            "detect": _display(row.get("accepted_detection_rate")),
            "native": _display(row.get("native_active_frame_rate")),
            "continuity": _display(row.get("local_continuity")),
            "idsw": _display(row.get("terminal_local_id_switch_count")),
            "fallback": _display(row.get("fallback_frame_count")),
            "p95": _display(row.get("warmup_excluded_p95_latency_ms")),
            "precision": _display(row.get("offline_detector_precision")),
            "recall": _display(row.get("offline_detector_recall")),
            "admitted": "通过" if row.get("native_mot_admitted") else "拒绝",
        }
        lines.append(
            "| {backend} | {distance} | {frames} | {detect} | {native} | {continuity} | {idsw} | {fallback} | {p95} | {precision} | {recall} | {admitted} |".format(**values)
        )
    return "\n".join(lines)


def _conclusions(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    confirmed = [row for row in rows if row.get("evidence_level") == LEVELS[2]]
    short = [row for row in rows if row.get("evidence_level") == LEVELS[1]]
    byte = next((row for row in confirmed if row.get("tracker_backend") == "bytetrack"), {})
    bot = next((row for row in confirmed if row.get("tracker_backend") == "botsort"), {})
    zero_distance = sorted(
        {row.get("target_distance_m") for row in short if row.get("accepted_detection_count") == 0}
    )
    return [
        "20 m、102帧确认中，ByteTrack 与 BoT-SORT 的原生跟踪激活率和局部连续率均为 1.0，IDSW 与 fallback 均为 0。",
        f"ByteTrack 的 102 帧 P95 为 {_display(byte.get('warmup_excluded_p95_latency_ms'))} ms，BoT-SORT 为 {_display(bot.get('warmup_excluded_p95_latency_ms'))} ms；本轮 ByteTrack 延迟更低。",
        f"约40帧距离短检查中，{', '.join(_distance(value) for value in zero_distance)} 没有接受检测，当前配置尚不支持这些距离档位。",
        "两个 backend 的 102 帧 confirmation 均因离线 precision/recall 低于阈值而拒绝，不能进入默认在线主线。",
        "当前证据支持“20 m 原生 MOT 运行稳定且无本地 ID switch”，不支持“检测准确性已达标”，也不支持 30/50 m 可用性结论。",
        "每帧有检测但离线 precision/recall 偏低，后续应优先核对 truth 框、IoU/几何门限和时间对齐，再决定重训检测器或调整评估标定；不得直接降低安全准入阈值。",
    ]


def _camera(rows: Sequence[Mapping[str, Any]]) -> str:
    return ", ".join(
        sorted(
            {
                f"{row.get('camera_width')}x{row.get('camera_height')} @ {row.get('camera_fov_deg')} deg"
                for row in rows
            }
        )
    )


def _distance(value: Any) -> str:
    number = _number(value)
    return "NA" if number is None else f"{number:g}m"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _csv_value(value: Any) -> Any:
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (list, tuple, dict)) else value


def _display(value: Any) -> str:
    if value is None:
        return "NA"
    return f"{value:.3f}" if isinstance(value, float) else str(value)
