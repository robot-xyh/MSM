"""Multi-seed AirSim calibration summaries for offline D6 reports."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .main_bus import load_main_episode_bus_metrics
from .metrics import EpisodeMetrics


GROUP_FIELDS = [
    "metric_scope",
    "seed",
    "scenario",
    "secondary_height_above_targets_m",
    "secondary_fov_degrees",
    "secondary_count",
    "detection_backend",
]

DETECT_TO_REGISTRATION_REASONS = [
    "not_all_targets_visible",
    "network_union_incomplete",
    "projection_invalid",
    "geometry_gate_rejected",
    "stability_window_failed",
    "no_global_binding",
    "stale_or_missing_recon_cue",
    "registered_to_global_track",
]

RECORD_FIELDNAMES = [
    "episode_id",
    "seed",
    "batch_seed",
    "scenario",
    "scenario_group",
    "case_name",
    "metric_scope",
    "drone_count",
    "resource_count",
    "target_count",
    "camera_count",
    "secondary_count",
    "secondary_height_above_targets_m",
    "secondary_fov_degrees",
    "secondary_image_width_px",
    "secondary_image_height_px",
    "secondary_recon_mode",
    "detection_backend",
    "connected",
    "frame_count",
    "image_ok_count",
    "secondary_network_joint_full_view_frame_rate",
    "secondary_network_mean_coverage_ratio",
    "secondary_visible_target_union_ratio",
    "secondary_single_camera_full_view_frame_rate",
    "multi_target_fov_rate",
    "secondary_detect_count",
    "funnel_detect_count",
    "funnel_local_or_recon_cue_count",
    "funnel_multi_support_count",
    "funnel_cross_view_association_count",
    "funnel_terminal_association_count",
    "projection_valid_rate",
    "geometry_gate_pass_rate",
    "registered_candidate_count",
    "stable_cross_view_registration_count",
    "not_registered_count",
    "funnel_breakpoint_reasons",
    "funnel_reject_reason_counts",
    "secondary_gimbal_pointing_ok_rate",
    "cue_pointing_error_mean_m",
    "cue_pointing_error_mean_deg",
    "gimbal_pointing_error_mean_deg",
    "secondary_bbox_area_mean_px",
    "secondary_bbox_area_count",
    "cross_view_registration_count",
    "secondary_detect_available_but_not_registered_count",
    "active_degradation_count",
    "active_degradation_precision",
    "unnecessary_degradation_count",
    "d7_guidance_reject_count",
    "d7_guidance_reject_reason_counts",
    "guidance_law_counts",
    "source_dir",
    "source_files",
]

SUMMARY_FIELDNAMES = [
    *GROUP_FIELDS,
    "episode_count",
    "connected_episode_count",
    "frame_count",
    "image_ok_count",
    "case_names",
    "scenario_groups",
    "drone_count",
    "resource_count",
    "target_count",
    "camera_count",
    "secondary_network_joint_full_view_frame_rate_mean",
    "secondary_network_mean_coverage_ratio_mean",
    "secondary_visible_target_union_ratio_mean",
    "secondary_single_camera_full_view_frame_rate_mean",
    "multi_target_fov_rate_mean",
    "secondary_detect_count",
    "funnel_detect_count",
    "funnel_local_or_recon_cue_count",
    "funnel_multi_support_count",
    "funnel_cross_view_association_count",
    "funnel_terminal_association_count",
    "projection_valid_rate_mean",
    "geometry_gate_pass_rate_mean",
    "registered_candidate_count",
    "stable_cross_view_registration_count",
    "not_registered_count",
    "funnel_reject_reason_counts",
    "funnel_breakpoint_reasons",
    "secondary_gimbal_pointing_ok_rate_mean",
    "cue_pointing_error_mean_m",
    "cue_pointing_error_mean_deg",
    "gimbal_pointing_error_mean_deg",
    "secondary_bbox_area_mean_px",
    "secondary_bbox_area_count",
    "cross_view_registration_count",
    "secondary_detect_available_but_not_registered_count",
    "active_degradation_count",
    "active_degradation_precision_mean",
    "unnecessary_degradation_count",
    "d7_guidance_reject_count",
    "d7_guidance_reject_reason_counts",
    "guidance_law_counts",
    "source_dirs",
]


@dataclass(frozen=True)
class AirSimCalibrationRecord:
    """CSV/JSON-friendly record for one persisted AirSim episode metric scope."""

    episode_id: str
    seed: int | None = None
    batch_seed: int | None = None
    scenario: str = "not_recorded"
    scenario_group: str = "not_recorded"
    case_name: str = "not_recorded"
    metric_scope: str = "not_recorded"
    drone_count: int = 0
    resource_count: int = 0
    target_count: int = 0
    camera_count: int = 0
    secondary_count: int = 0
    secondary_height_above_targets_m: float | None = None
    secondary_fov_degrees: float | None = None
    secondary_image_width_px: int | None = None
    secondary_image_height_px: int | None = None
    secondary_recon_mode: str = "not_recorded"
    detection_backend: str = "not_recorded"
    connected: bool | None = None
    frame_count: int = 0
    image_ok_count: int = 0
    secondary_network_joint_full_view_frame_rate: float | None = None
    secondary_network_mean_coverage_ratio: float | None = None
    secondary_visible_target_union_ratio: float | None = None
    secondary_single_camera_full_view_frame_rate: float | None = None
    multi_target_fov_rate: float | None = None
    secondary_detect_count: int = 0
    funnel_detect_count: int = 0
    funnel_local_or_recon_cue_count: int = 0
    funnel_multi_support_count: int = 0
    funnel_cross_view_association_count: int = 0
    funnel_terminal_association_count: int = 0
    projection_valid_rate: float | None = None
    geometry_gate_pass_rate: float | None = None
    registered_candidate_count: int = 0
    stable_cross_view_registration_count: int = 0
    not_registered_count: int = 0
    funnel_breakpoint_reasons: list[str] = field(default_factory=list)
    funnel_reject_reason_counts: dict[str, int] = field(default_factory=dict)
    secondary_gimbal_pointing_ok_rate: float | None = None
    cue_pointing_error_mean_m: float | None = None
    cue_pointing_error_mean_deg: float | None = None
    gimbal_pointing_error_mean_deg: float | None = None
    secondary_bbox_area_mean_px: float | None = None
    secondary_bbox_area_count: int = 0
    cross_view_registration_count: int = 0
    secondary_detect_available_but_not_registered_count: int = 0
    active_degradation_count: int = 0
    active_degradation_precision: float | None = None
    unnecessary_degradation_count: int = 0
    d7_guidance_reject_count: int = 0
    d7_guidance_reject_reason_counts: dict[str, int] = field(default_factory=dict)
    guidance_law_counts: dict[str, int] = field(default_factory=dict)
    source_dir: str = ""
    source_files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AirSimCalibrationReportGenerator:
    """Generate multi-seed AirSim calibration CSV, JSON, and Markdown reports."""

    def load_records(
        self,
        paths: Iterable[str | Path],
    ) -> list[AirSimCalibrationRecord]:
        return load_airsim_calibration_records(paths)

    def summarize(
        self,
        records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        return summarize_airsim_calibration_records(records)

    def write_record_csv(
        self,
        records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
        path: str | Path,
    ) -> Path:
        return write_airsim_calibration_record_csv(records, path)

    def write_summary_csv(
        self,
        rows: Iterable[Mapping[str, Any]],
        path: str | Path,
    ) -> Path:
        return write_airsim_calibration_summary_csv(rows, path)

    def write_summary_json(
        self,
        rows: Iterable[Mapping[str, Any]],
        path: str | Path,
    ) -> Path:
        return write_airsim_calibration_summary_json(rows, path)

    def write_markdown_report(
        self,
        records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
        rows: Iterable[Mapping[str, Any]],
        path: str | Path,
        *,
        title: str = "D6 AirSim 多 Seed 校准报告",
    ) -> Path:
        return write_airsim_calibration_markdown(records, rows, path, title=title)

    def write_report_bundle(
        self,
        input_paths: Iterable[str | Path],
        output_dir: str | Path,
        *,
        title: str = "D6 AirSim 多 Seed 校准报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        records = self.load_records(input_paths)
        rows = self.summarize(records)
        return {
            "record_csv": self.write_record_csv(
                records,
                output_dir / "airsim_calibration_records.csv",
            ),
            "summary_csv": self.write_summary_csv(
                rows,
                output_dir / "airsim_calibration_summary.csv",
            ),
            "summary_json": self.write_summary_json(
                rows,
                output_dir / "airsim_calibration_summary.json",
            ),
            "markdown": self.write_markdown_report(
                records,
                rows,
                output_dir / "airsim_calibration_report.md",
                title=title,
            ),
        }


def load_airsim_calibration_records(
    paths: Iterable[str | Path],
) -> list[AirSimCalibrationRecord]:
    """Load persisted AirSim calibration artifacts without importing runtime code."""

    episode_dirs = _discover_episode_dirs(paths)
    records: list[AirSimCalibrationRecord] = []
    for episode_dir in sorted(episode_dirs):
        records.extend(_records_from_episode_dir(episode_dir))
    return records


def summarize_airsim_calibration_records(
    records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize records by metric scope plus seed/scenario/geometry/backend."""

    normalized_records = [_record_dict(record) for record in records]
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in normalized_records:
        key = tuple(_group_value(record.get(field)) for field in GROUP_FIELDS)
        grouped.setdefault(key, []).append(record)

    rows: list[dict[str, Any]] = []
    for key, grouped_records in sorted(grouped.items(), key=_summary_sort_key):
        group_values = dict(zip(GROUP_FIELDS, key))
        rows.append(
            {
                **group_values,
                "episode_count": len(grouped_records),
                "connected_episode_count": sum(
                    1 for record in grouped_records if record.get("connected") is True
                ),
                "frame_count": _sum_int(grouped_records, "frame_count"),
                "image_ok_count": _sum_int(grouped_records, "image_ok_count"),
                "case_names": _unique_text_values(grouped_records, "case_name"),
                "scenario_groups": _unique_text_values(grouped_records, "scenario_group"),
                "drone_count": _range_text(grouped_records, "drone_count"),
                "resource_count": _range_text(grouped_records, "resource_count"),
                "target_count": _range_text(grouped_records, "target_count"),
                "camera_count": _range_text(grouped_records, "camera_count"),
                "secondary_network_joint_full_view_frame_rate_mean": _mean_field(
                    grouped_records,
                    "secondary_network_joint_full_view_frame_rate",
                ),
                "secondary_network_mean_coverage_ratio_mean": _mean_field(
                    grouped_records,
                    "secondary_network_mean_coverage_ratio",
                ),
                "secondary_visible_target_union_ratio_mean": _mean_field(
                    grouped_records,
                    "secondary_visible_target_union_ratio",
                ),
                "secondary_single_camera_full_view_frame_rate_mean": _mean_field(
                    grouped_records,
                    "secondary_single_camera_full_view_frame_rate",
                ),
                "multi_target_fov_rate_mean": _mean_field(
                    grouped_records,
                    "multi_target_fov_rate",
                ),
                "secondary_detect_count": _sum_int(
                    grouped_records,
                    "secondary_detect_count",
                ),
                "funnel_detect_count": _sum_int(grouped_records, "funnel_detect_count"),
                "funnel_local_or_recon_cue_count": _sum_int(
                    grouped_records,
                    "funnel_local_or_recon_cue_count",
                ),
                "funnel_multi_support_count": _sum_int(
                    grouped_records,
                    "funnel_multi_support_count",
                ),
                "funnel_cross_view_association_count": _sum_int(
                    grouped_records,
                    "funnel_cross_view_association_count",
                ),
                "funnel_terminal_association_count": _sum_int(
                    grouped_records,
                    "funnel_terminal_association_count",
                ),
                "projection_valid_rate_mean": _mean_field(
                    grouped_records,
                    "projection_valid_rate",
                ),
                "geometry_gate_pass_rate_mean": _mean_field(
                    grouped_records,
                    "geometry_gate_pass_rate",
                ),
                "registered_candidate_count": _sum_int(
                    grouped_records,
                    "registered_candidate_count",
                ),
                "stable_cross_view_registration_count": _sum_int(
                    grouped_records,
                    "stable_cross_view_registration_count",
                ),
                "not_registered_count": _sum_int(grouped_records, "not_registered_count"),
                "funnel_reject_reason_counts": _sum_count_mappings(
                    grouped_records,
                    "funnel_reject_reason_counts",
                ),
                "funnel_breakpoint_reasons": _unique_list_values(
                    grouped_records,
                    "funnel_breakpoint_reasons",
                ),
                "secondary_gimbal_pointing_ok_rate_mean": _mean_field(
                    grouped_records,
                    "secondary_gimbal_pointing_ok_rate",
                ),
                "cue_pointing_error_mean_m": _mean_field(
                    grouped_records,
                    "cue_pointing_error_mean_m",
                ),
                "cue_pointing_error_mean_deg": _mean_field(
                    grouped_records,
                    "cue_pointing_error_mean_deg",
                ),
                "gimbal_pointing_error_mean_deg": _mean_field(
                    grouped_records,
                    "gimbal_pointing_error_mean_deg",
                ),
                "secondary_bbox_area_mean_px": _weighted_mean_field(
                    grouped_records,
                    "secondary_bbox_area_mean_px",
                    "secondary_bbox_area_count",
                ),
                "secondary_bbox_area_count": _sum_int(
                    grouped_records,
                    "secondary_bbox_area_count",
                ),
                "cross_view_registration_count": _sum_int(
                    grouped_records,
                    "cross_view_registration_count",
                ),
                "secondary_detect_available_but_not_registered_count": _sum_int(
                    grouped_records,
                    "secondary_detect_available_but_not_registered_count",
                ),
                "active_degradation_count": _sum_int(
                    grouped_records,
                    "active_degradation_count",
                ),
                "active_degradation_precision_mean": _mean_field(
                    grouped_records,
                    "active_degradation_precision",
                ),
                "unnecessary_degradation_count": _sum_int(
                    grouped_records,
                    "unnecessary_degradation_count",
                ),
                "d7_guidance_reject_count": _sum_int(
                    grouped_records,
                    "d7_guidance_reject_count",
                ),
                "d7_guidance_reject_reason_counts": _sum_count_mappings(
                    grouped_records,
                    "d7_guidance_reject_reason_counts",
                ),
                "guidance_law_counts": _sum_count_mappings(
                    grouped_records,
                    "guidance_law_counts",
                ),
                "source_dirs": _unique_text_values(grouped_records, "source_dir"),
            }
        )
    return rows


def write_airsim_calibration_record_csv(
    records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
    path: str | Path,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=RECORD_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_row(_record_dict(record), RECORD_FIELDNAMES))
    return path


def write_airsim_calibration_summary_csv(
    rows: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row, SUMMARY_FIELDNAMES))
    return path


def write_airsim_calibration_summary_json(
    rows: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "group_fields": GROUP_FIELDS,
        "rows": [dict(row) for row in rows],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_airsim_calibration_markdown(
    records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
    rows: Iterable[Mapping[str, Any]],
    path: str | Path,
    *,
    title: str = "D6 AirSim 多 Seed 校准报告",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record_dicts = [_record_dict(record) for record in records]
    summary_rows = [dict(row) for row in rows]

    lines = [
        f"# {title}",
        "",
        "本报告由 D6 离线读取 AirSim runtime 已写盘文件生成；D6 只消费日志，不参与控制、重规划、云台指向或 D7 导引。",
        "",
        f"- Episode/scope 记录数: {len(record_dicts)}",
        f"- 分组字段: {', '.join(GROUP_FIELDS)}",
        f"- Seed 范围: {_range_text(record_dicts, 'seed')}",
        f"- 场景: {', '.join(_unique_text_values(record_dicts, 'scenario')) or 'not_recorded'}",
        f"- Detection backend: {', '.join(_unique_text_values(record_dicts, 'detection_backend')) or 'not_recorded'}",
        "",
        "## 1. 分组摘要",
        "",
        "| Scope | Seed | Scenario | Height m | FOV deg | Secondary count | Backend | Episodes | Coverage mean | Full-view rate | Detect | Stable registration | Not registered | Gimbal OK | Active precision | Unnecessary degradation | D7 reject |",
        "|---|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {height} | {fov} | {secondary_count} | {backend} | {episodes} | {coverage:.6g} | {full_view:.6g} | {detect} | {cross_view} | {not_registered} | {gimbal:.6g} | {active_precision:.6g} | {unnecessary} | {d7_reject} |".format(
                metric_scope=row.get("metric_scope", "not_recorded"),
                seed=row.get("seed", "not_recorded"),
                scenario=row.get("scenario", "not_recorded"),
                height=_format_optional_number(row.get("secondary_height_above_targets_m")),
                fov=_format_optional_number(row.get("secondary_fov_degrees")),
                secondary_count=row.get("secondary_count", "not_recorded"),
                backend=row.get("detection_backend", "not_recorded"),
                episodes=int(row.get("episode_count", 0) or 0),
                coverage=_float_or_zero(
                    row.get("secondary_network_mean_coverage_ratio_mean")
                ),
                full_view=_float_or_zero(
                    row.get("secondary_network_joint_full_view_frame_rate_mean")
                ),
                detect=int(
                    row.get("secondary_detect_count")
                    or row.get("funnel_detect_count", 0)
                    or 0
                ),
                cross_view=int(
                    row.get("stable_cross_view_registration_count")
                    or row.get("cross_view_registration_count", 0)
                    or 0
                ),
                not_registered=int(
                    row.get("not_registered_count")
                    or row.get("secondary_detect_available_but_not_registered_count", 0)
                    or 0
                ),
                gimbal=_float_or_zero(
                    row.get("secondary_gimbal_pointing_ok_rate_mean")
                ),
                active_precision=_float_or_zero(
                    row.get("active_degradation_precision_mean")
                ),
                unnecessary=int(row.get("unnecessary_degradation_count", 0) or 0),
                d7_reject=int(row.get("d7_guidance_reject_count", 0) or 0),
            )
        )

    lines.extend(
        [
            "",
            "## 2. Detect-to-registration Funnel",
            "",
            "该表把二级检测进入 D5 跨视角配准前后的断点展开。`detect_count` 是二级检测机会；`projection_valid_rate` 和 `geometry_gate_pass_rate` 是几何链路质量；`stable_cross_view_registration_count` 是稳定跨视角注册数量。",
            "",
            "| Scope | Seed | Scenario | Breakpoint reasons | Reject/outcome counts | Detect | Projection valid | Gate pass | Candidate | Stable registration | Not registered |",
            "|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {breakpoints} | {rejects} | {detect} | {projection:.6g} | {gate:.6g} | {candidate} | {stable} | {not_registered} |".format(
                metric_scope=row.get("metric_scope", "not_recorded"),
                seed=row.get("seed", "not_recorded"),
                scenario=row.get("scenario", "not_recorded"),
                breakpoints=_compact_json(row.get("funnel_breakpoint_reasons")),
                rejects=_compact_json(row.get("funnel_reject_reason_counts")),
                detect=int(
                    row.get("secondary_detect_count")
                    or row.get("funnel_detect_count", 0)
                    or 0
                ),
                projection=_float_or_zero(row.get("projection_valid_rate_mean")),
                gate=_float_or_zero(row.get("geometry_gate_pass_rate_mean")),
                candidate=int(row.get("registered_candidate_count", 0) or 0),
                stable=int(row.get("stable_cross_view_registration_count", 0) or 0),
                not_registered=int(row.get("not_registered_count", 0) or 0),
            )
        )

    lines.extend(
        [
            "",
            "## 3. D7 Guidance Reject Reason",
            "",
            "| Scope | Seed | Scenario | Reject reason counts | Guidance law counts |",
            "|---|---:|---|---|---|",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {rejects} | {laws} |".format(
                metric_scope=row.get("metric_scope", "not_recorded"),
                seed=row.get("seed", "not_recorded"),
                scenario=row.get("scenario", "not_recorded"),
                rejects=_compact_json(row.get("d7_guidance_reject_reason_counts")),
                laws=_compact_json(row.get("guidance_law_counts")),
            )
        )

    lines.extend(
        [
            "",
            "## 4. 解读口径",
            "",
            "- coverage/full-view/gimbal 指标来自 main/D4/D5 已写盘的 D4D5 stress 或 main bus metadata，用于长期趋势比较。",
            "- active degradation precision 只使用 main/D4 写出的 review label 或后验字段；缺少标签时不会由事件名自证必要性。",
            "- D7 reject reason 同时汇总 terminal switch 与 terminal contract reject 分布，用于 execution/contract 对照。",
            "- 规模字段使用 runtime metrics 或日志中的实际 count 字段；报告不从 `2v2/5v5` 场景名推断目标数、资源数或相机数。",
            "",
            "## 5. 文件索引",
            "",
        ]
    )
    for source_dir in _unique_text_values(record_dicts, "source_dir")[:30]:
        lines.append(f"- {source_dir}")
    if len(_unique_text_values(record_dicts, "source_dir")) > 30:
        lines.append("- ...")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _discover_episode_dirs(paths: Iterable[str | Path]) -> set[Path]:
    episode_dirs: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            episode_dirs.update(_episode_dirs_from_file(path))
        elif path.is_dir():
            if _is_episode_dir(path):
                episode_dirs.add(path.resolve())
            for artifact in path.rglob("*"):
                if artifact.is_file():
                    episode_dirs.update(_episode_dirs_from_file(artifact))
    return episode_dirs


def _episode_dirs_from_file(path: Path) -> set[Path]:
    if path.name in {
        "d4d5_stress_metrics.json",
        "airsim_blocks_summary.json",
        "d5_cross_view_associations.json",
    }:
        return {path.parent.resolve()}
    if path.name in {"main_episode_bus_metrics.json", "main_episode_bus_contract_metrics.json"}:
        return {path.parent.parent.resolve() if path.parent.name == "main_episode_bus" else path.parent.resolve()}
    if path.name in {"blocks_sequence_summary.json", "blocks_batch_summary.json"}:
        return _episode_dirs_from_sequence_summary(path)
    return set()


def _episode_dirs_from_sequence_summary(path: Path) -> set[Path]:
    raw = _load_json(path)
    dirs: set[Path] = set()
    if not isinstance(raw, Mapping):
        return dirs
    for result in raw.get("results", []) or []:
        if not isinstance(result, Mapping):
            continue
        summary_path = _resolve_artifact_path(result.get("summary"), path.parent)
        if summary_path is not None and summary_path.exists():
            dirs.update(_episode_dirs_from_file(summary_path))
    for episode in raw.get("episodes", []) or []:
        if not isinstance(episode, Mapping):
            continue
        output_paths = episode.get("output_paths", {})
        if not isinstance(output_paths, Mapping):
            continue
        for key, value in output_paths.items():
            if key not in {
                "airsim_blocks_summary",
                "d4d5_stress_metrics_json",
                "main_episode_bus_metrics_json",
                "main_episode_bus_contract_metrics_json",
            }:
                continue
            artifact = _resolve_artifact_path(value, path.parent)
            if artifact is not None:
                dirs.update(_episode_dirs_from_file(artifact))
    return dirs


def _is_episode_dir(path: Path) -> bool:
    return any(
        (path / relative).exists()
        for relative in (
            "d4d5_stress_metrics.json",
            "airsim_blocks_summary.json",
            "main_episode_bus/main_episode_bus_metrics.json",
            "main_episode_bus/main_episode_bus_contract_metrics.json",
        )
    )


def _records_from_episode_dir(episode_dir: Path) -> list[AirSimCalibrationRecord]:
    d4d5_path = episode_dir / "d4d5_stress_metrics.json"
    blocks_path = episode_dir / "airsim_blocks_summary.json"
    d4d5 = _load_mapping(d4d5_path)
    blocks = _load_mapping(blocks_path)
    if not d4d5:
        d4d5 = _d4d5_from_blocks(blocks)

    metric_paths = [
        episode_dir / "main_episode_bus" / "main_episode_bus_metrics.json",
        episode_dir / "main_episode_bus" / "main_episode_bus_contract_metrics.json",
    ]
    metrics: list[tuple[EpisodeMetrics | None, Path | None]] = []
    for path in metric_paths:
        if path.exists():
            metrics.append((load_main_episode_bus_metrics(path), path))
    if not metrics:
        metrics.append((None, None))

    return [
        _record_from_artifacts(
            episode_dir=episode_dir,
            d4d5=d4d5,
            blocks=blocks,
            metrics=episode_metrics,
            metrics_path=metrics_path,
            d4d5_path=d4d5_path if d4d5_path.exists() else None,
            blocks_path=blocks_path if blocks_path.exists() else None,
        )
        for episode_metrics, metrics_path in metrics
    ]


def _record_from_artifacts(
    *,
    episode_dir: Path,
    d4d5: Mapping[str, Any],
    blocks: Mapping[str, Any],
    metrics: EpisodeMetrics | None,
    metrics_path: Path | None,
    d4d5_path: Path | None,
    blocks_path: Path | None,
) -> AirSimCalibrationRecord:
    metrics_metadata = dict(metrics.metadata) if metrics is not None else {}
    blocks_metadata = _mapping_value(blocks, "metadata")
    geometry = _mapping_value(d4d5, "geometry")
    funnel = _mapping_value(d4d5, "secondary_detection_funnel_counts")
    bbox_stats = _mapping_value(d4d5, "secondary_bbox_area_px_stats")
    cue_stats = _mapping_value(d4d5, "secondary_cue_pointing_error_m_stats")
    secondary_camera_names = _sequence_value(blocks_metadata.get("secondary_camera_vehicle_names"))
    settings_path = _settings_path(blocks_metadata, episode_dir)
    settings_summary = _secondary_settings_summary(settings_path)

    seed = _first_int(
        _metric_attr(metrics, "seed"),
        _metric_attr(metrics, "batch_seed"),
        d4d5.get("seed"),
        blocks.get("seed"),
        _seed_from_path(episode_dir),
    )
    scenario_group = _first_text(
        _metric_attr(metrics, "scenario_group"),
        d4d5.get("scenario_group"),
        blocks.get("scenario_group"),
        blocks.get("episode_id"),
        episode_dir.name,
    )
    case_name = _first_text(d4d5.get("case_name"), blocks.get("episode_id"), episode_dir.name)
    scenario = _first_text(case_name, scenario_group, "not_recorded") or "not_recorded"
    metric_scope = _first_text(_metric_attr(metrics, "metric_scope"))
    if metric_scope is None or metric_scope == "not_recorded":
        metric_scope = "d4d5_stress" if d4d5 else "not_recorded"

    target_count = _first_int(
        _metric_attr(metrics, "target_count"),
        geometry.get("target_count"),
        blocks_metadata.get("actor_target_count"),
        _nested_int(blocks_metadata, ("first_frame", "truth_count")),
    )
    resource_count = _first_int(
        _metric_attr(metrics, "resource_count"),
        geometry.get("resource_camera_count"),
        _nested_int(blocks_metadata, ("first_frame", "resource_count")),
    )
    camera_count = _first_int(
        _metric_attr(metrics, "camera_count"),
        len(_sequence_value(blocks_metadata.get("camera_vehicle_names"))),
        settings_summary.get("camera_count"),
    )
    drone_count = _first_int(_metric_attr(metrics, "drone_count"), resource_count)

    secondary_count = _first_int(
        geometry.get("secondary_camera_count"),
        d4d5.get("secondary_camera_count"),
        len(secondary_camera_names) if secondary_camera_names else None,
        settings_summary.get("secondary_count"),
    )

    d7_reject_reasons = _guidance_reject_reason_counts(metrics_metadata)
    guidance_laws = _count_mapping(metrics_metadata.get("guidance_law_counts"))
    source_files = _source_files(
        metrics_path=metrics_path,
        d4d5_path=d4d5_path,
        blocks_path=blocks_path,
        settings_path=settings_path,
    )
    funnel_detect_count = int(
        _first_int(
            d4d5.get("secondary_detect_count"),
            funnel.get("secondary_detect_count"),
            funnel.get("detect_count"),
            d4d5.get("secondary_detection_count"),
            0,
        )
        or 0
    )
    raw_funnel_reject_reason_counts = _count_mapping(
        d4d5.get("secondary_detect_to_cross_view_reject_reason_counts")
        or funnel.get("rejection_reason_counts")
    )
    registered_candidate_count = int(
        _first_int(
            d4d5.get("registered_candidate_count"),
            d4d5.get("d5_registered_candidate_count"),
            d4d5.get("secondary_registered_candidate_count"),
            funnel.get("registered_candidate_count"),
            raw_funnel_reject_reason_counts.get("registered_to_global_track"),
            funnel.get("terminal_association_count"),
            0,
        )
        or 0
    )
    stable_cross_view_registration_count = int(
        _first_int(
            d4d5.get("stable_cross_view_registration_count"),
            d4d5.get("stable_cross_view_association_count"),
            funnel.get("stable_cross_view_registration_count"),
            d4d5.get("cross_view_registration_count"),
            d4d5.get("cross_view_association_count"),
            _metric_attr(metrics, "cross_view_association_count"),
            0,
        )
        or 0
    )
    not_registered_count = int(
        _first_int(
            d4d5.get("not_registered_count"),
            d4d5.get("secondary_detect_available_but_not_registered_count"),
            _metric_attr(metrics, "secondary_detect_available_but_not_registered_count"),
            0,
        )
        or 0
    )
    funnel_reject_reason_counts = _normalized_detect_registration_reason_counts(
        raw_funnel_reject_reason_counts,
        registered_candidate_count=registered_candidate_count,
    )
    projection_valid_rate = _projection_valid_rate(
        d4d5=d4d5,
        funnel=funnel,
        reject_counts=raw_funnel_reject_reason_counts,
        detect_count=funnel_detect_count,
    )
    geometry_gate_pass_rate = _geometry_gate_pass_rate(
        d4d5=d4d5,
        funnel=funnel,
        reject_counts=raw_funnel_reject_reason_counts,
        detect_count=funnel_detect_count,
        registered_candidate_count=registered_candidate_count,
    )
    secondary_visible_target_union_ratio = _first_float(
        d4d5.get("secondary_visible_target_union_ratio"),
        d4d5.get("secondary_network_visible_target_union_ratio"),
        d4d5.get("secondary_network_joint_coverage_ratio_mean"),
        d4d5.get("secondary_network_mean_coverage_ratio"),
        _metric_attr(metrics, "secondary_network_mean_coverage_ratio"),
    )

    return AirSimCalibrationRecord(
        episode_id=_first_text(_metric_attr(metrics, "episode_id"), blocks.get("episode_id"), episode_dir.name) or episode_dir.name,
        seed=seed,
        batch_seed=_first_int(_metric_attr(metrics, "batch_seed"), seed),
        scenario=scenario,
        scenario_group=scenario_group or "not_recorded",
        case_name=case_name or "not_recorded",
        metric_scope=metric_scope,
        drone_count=int(drone_count or 0),
        resource_count=int(resource_count or 0),
        target_count=int(target_count or 0),
        camera_count=int(camera_count or 0),
        secondary_count=int(secondary_count or 0),
        secondary_height_above_targets_m=_first_float(
            d4d5.get("secondary_height_above_targets_m"),
            geometry.get("secondary_height_above_targets_m"),
        ),
        secondary_fov_degrees=_first_float(
            d4d5.get("secondary_fov_degrees"),
            d4d5.get("secondary_fov_deg"),
            d4d5.get("secondary_camera_fov_degrees"),
            settings_summary.get("secondary_fov_degrees"),
        ),
        secondary_image_width_px=_first_int(
            d4d5.get("secondary_image_width_px"),
            settings_summary.get("secondary_image_width_px"),
        ),
        secondary_image_height_px=_first_int(
            d4d5.get("secondary_image_height_px"),
            settings_summary.get("secondary_image_height_px"),
        ),
        secondary_recon_mode=_first_text(
            d4d5.get("secondary_recon_mode"),
            d4d5.get("secondary_node_type"),
            _first_sequence_text(d4d5.get("secondary_capability_classes")),
            "not_recorded",
        )
        or "not_recorded",
        detection_backend=_detection_backend(d4d5, blocks_metadata, episode_dir),
        connected=_optional_bool(blocks.get("connected")),
        frame_count=int(_first_int(blocks.get("frame_count"), 0) or 0),
        image_ok_count=int(_first_int(blocks.get("image_ok_count"), 0) or 0),
        secondary_network_joint_full_view_frame_rate=_first_float(
            d4d5.get("secondary_network_joint_full_view_frame_rate"),
            _metric_attr(metrics, "secondary_network_joint_full_view_frame_rate"),
        ),
        secondary_network_mean_coverage_ratio=_first_float(
            d4d5.get("secondary_network_mean_coverage_ratio"),
            d4d5.get("secondary_network_joint_coverage_ratio_mean"),
            _metric_attr(metrics, "secondary_network_mean_coverage_ratio"),
        ),
        secondary_visible_target_union_ratio=secondary_visible_target_union_ratio,
        secondary_single_camera_full_view_frame_rate=_first_float(
            d4d5.get("secondary_single_camera_full_view_frame_rate"),
            _metric_attr(metrics, "secondary_single_camera_full_view_frame_rate"),
        ),
        multi_target_fov_rate=_first_float(d4d5.get("multi_target_fov_rate")),
        secondary_detect_count=funnel_detect_count,
        funnel_detect_count=funnel_detect_count,
        funnel_local_or_recon_cue_count=int(
            _first_int(funnel.get("local_or_recon_cue_count"), 0) or 0
        ),
        funnel_multi_support_count=int(_first_int(funnel.get("multi_support_count"), 0) or 0),
        funnel_cross_view_association_count=int(
            _first_int(
                funnel.get("cross_view_association_count"),
                d4d5.get("cross_view_association_count"),
                0,
            )
            or 0
        ),
        funnel_terminal_association_count=int(
            _first_int(funnel.get("terminal_association_count"), 0) or 0
        ),
        projection_valid_rate=projection_valid_rate,
        geometry_gate_pass_rate=geometry_gate_pass_rate,
        registered_candidate_count=registered_candidate_count,
        stable_cross_view_registration_count=stable_cross_view_registration_count,
        not_registered_count=not_registered_count,
        funnel_breakpoint_reasons=_text_list(
            d4d5.get("secondary_detect_funnel_breakpoint_reasons")
            or funnel.get("breakpoint_reasons")
        ),
        funnel_reject_reason_counts=funnel_reject_reason_counts,
        secondary_gimbal_pointing_ok_rate=_first_float(
            d4d5.get("secondary_gimbal_pointing_ok_rate")
        ),
        cue_pointing_error_mean_m=_first_float(cue_stats.get("mean")),
        cue_pointing_error_mean_deg=_first_float(
            d4d5.get("cue_pointing_error_mean_deg"),
            _metric_attr(metrics, "cue_pointing_error_mean_deg"),
        ),
        gimbal_pointing_error_mean_deg=_first_float(
            d4d5.get("gimbal_pointing_error_mean_deg"),
            _metric_attr(metrics, "gimbal_pointing_error_mean_deg"),
        ),
        secondary_bbox_area_mean_px=_first_float(bbox_stats.get("mean")),
        secondary_bbox_area_count=int(_first_int(bbox_stats.get("count"), 0) or 0),
        cross_view_registration_count=int(
            _first_int(
                d4d5.get("cross_view_association_count"),
                _metric_attr(metrics, "cross_view_association_count"),
                0,
            )
            or 0
        ),
        secondary_detect_available_but_not_registered_count=int(
            _first_int(
                d4d5.get("secondary_detect_available_but_not_registered_count"),
                _metric_attr(
                    metrics,
                    "secondary_detect_available_but_not_registered_count",
                ),
                0,
            )
            or 0
        ),
        active_degradation_count=int(_first_int(_metric_attr(metrics, "active_degradation_count"), 0) or 0),
        active_degradation_precision=_first_float(
            _metric_attr(metrics, "active_degradation_precision")
        ),
        unnecessary_degradation_count=int(
            _first_int(_metric_attr(metrics, "unnecessary_active_degradation_count"), 0)
            or 0
        ),
        d7_guidance_reject_count=sum(d7_reject_reasons.values()),
        d7_guidance_reject_reason_counts=d7_reject_reasons,
        guidance_law_counts=guidance_laws,
        source_dir=str(episode_dir),
        source_files=source_files,
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = _load_json(path)
    return dict(raw) if isinstance(raw, Mapping) else {}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _d4d5_from_blocks(blocks: Mapping[str, Any]) -> dict[str, Any]:
    metadata = blocks.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return {}
    d4d5 = metadata.get("d4d5_stress", {})
    return dict(d4d5) if isinstance(d4d5, Mapping) else {}


def _settings_path(blocks_metadata: Mapping[str, Any], episode_dir: Path) -> Path | None:
    return _resolve_artifact_path(blocks_metadata.get("settings_path"), episode_dir)


def _resolve_artifact_path(value: Any, base_dir: Path) -> Path | None:
    text = _text(value)
    if text is None:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    if path.exists():
        return path
    candidate = base_dir / path
    return candidate


def _secondary_settings_summary(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    raw = _load_json(path)
    if not isinstance(raw, Mapping):
        return {}
    vehicles = raw.get("Vehicles", {})
    if not isinstance(vehicles, Mapping):
        return {}

    fovs: list[float] = []
    widths: list[int] = []
    heights: list[int] = []
    secondary_count = 0
    camera_count = 0
    for vehicle_name, vehicle in vehicles.items():
        if not isinstance(vehicle, Mapping):
            continue
        camera_count += 1
        is_secondary = "secondary" in str(vehicle_name).lower()
        if is_secondary:
            secondary_count += 1
        camera_configs = vehicle.get("Cameras", {})
        if not isinstance(camera_configs, Mapping):
            continue
        for camera in camera_configs.values():
            if not isinstance(camera, Mapping):
                continue
            for capture in camera.get("CaptureSettings", []) or []:
                if not isinstance(capture, Mapping):
                    continue
                if is_secondary:
                    fov = _first_float(capture.get("FOV_Degrees"))
                    width = _first_int(capture.get("Width"))
                    height = _first_int(capture.get("Height"))
                    if fov is not None:
                        fovs.append(fov)
                    if width is not None:
                        widths.append(width)
                    if height is not None:
                        heights.append(height)
    return {
        "camera_count": camera_count,
        "secondary_count": secondary_count,
        "secondary_fov_degrees": _single_or_mean(fovs),
        "secondary_image_width_px": int(_single_or_mean(widths) or 0) or None,
        "secondary_image_height_px": int(_single_or_mean(heights) or 0) or None,
    }


def _source_files(
    *,
    metrics_path: Path | None,
    d4d5_path: Path | None,
    blocks_path: Path | None,
    settings_path: Path | None,
) -> dict[str, str]:
    files = {
        "main_bus_metrics": metrics_path,
        "d4d5_stress_metrics": d4d5_path,
        "airsim_blocks_summary": blocks_path,
        "settings": settings_path if settings_path is not None and settings_path.exists() else None,
    }
    return {key: str(path) for key, path in files.items() if path is not None}


def _guidance_reject_reason_counts(metadata: Mapping[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in (
        "terminal_switch_reject_reasons",
        "terminal_contract_reject_reasons",
        "terminal_switch_reject_reason_pair_counts",
    ):
        for reason, count in _count_mapping(metadata.get(key)).items():
            counts[reason] = counts.get(reason, 0) + count
    return counts


def _detection_backend(
    d4d5: Mapping[str, Any],
    blocks_metadata: Mapping[str, Any],
    episode_dir: Path,
) -> str:
    for mapping in (d4d5, blocks_metadata):
        for key in (
            "detection_backend",
            "detector_backend",
            "target_detection_backend",
            "vision_detection_backend",
        ):
            value = _text(mapping.get(key))
            if value is not None:
                return value
    path_text = str(episode_dir).lower()
    if "yolo" in path_text:
        return "yolo"
    if d4d5:
        return "simGetDetections"
    return "not_recorded"


def _metric_attr(metrics: EpisodeMetrics | None, name: str) -> Any:
    if metrics is None:
        return None
    return getattr(metrics, name, None)


def _mapping_value(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _nested_int(mapping: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return _first_int(value)


def _seed_from_path(path: Path) -> int | None:
    for part in reversed(path.parts):
        match = re.search(r"(?:^|[_-])seed0*([0-9]+)", part, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _first_int(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue
    return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _text(value)
        if text is not None:
            return text
    return None


def _first_sequence_text(value: Any) -> str | None:
    values = _sequence_value(value)
    for item in values:
        text = _text(item)
        if text is not None:
            return text
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, Mapping):
        return [str(key) for key in value if str(key).strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _text(value)
    return [] if text is None else [text]


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok"}:
        return True
    if text in {"false", "f", "no", "n", "0", "fail", "failed"}:
        return False
    return None


def _count_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, raw_count in value.items():
        reason = _text(key)
        if reason is None:
            continue
        count = _first_int(raw_count)
        if count is None:
            continue
        counts[reason] = counts.get(reason, 0) + count
    return counts


def _normalized_detect_registration_reason_counts(
    value: Any,
    *,
    registered_candidate_count: int = 0,
) -> dict[str, int]:
    counts = _count_mapping(value)
    if registered_candidate_count > 0 and "registered_to_global_track" not in counts:
        counts["registered_to_global_track"] = registered_candidate_count
    for reason in DETECT_TO_REGISTRATION_REASONS:
        counts.setdefault(reason, 0)
    return dict(sorted(counts.items()))


def _projection_valid_rate(
    *,
    d4d5: Mapping[str, Any],
    funnel: Mapping[str, Any],
    reject_counts: Mapping[str, int],
    detect_count: int,
) -> float | None:
    explicit_rate = _first_float(
        d4d5.get("projection_valid_rate"),
        d4d5.get("secondary_projection_valid_rate"),
        funnel.get("projection_valid_rate"),
    )
    if explicit_rate is not None:
        return _clamp_rate(explicit_rate)
    valid_count = _first_int(
        d4d5.get("projection_valid_count"),
        d4d5.get("secondary_projection_valid_count"),
        funnel.get("projection_valid_count"),
    )
    total_count = _first_int(
        d4d5.get("projection_candidate_count"),
        d4d5.get("secondary_projection_candidate_count"),
        funnel.get("projection_candidate_count"),
        detect_count,
    )
    if valid_count is not None and total_count and total_count > 0:
        return _clamp_rate(valid_count / total_count)
    if detect_count > 0 and "projection_invalid" in reject_counts:
        return _clamp_rate((detect_count - int(reject_counts.get("projection_invalid", 0))) / detect_count)
    return None


def _geometry_gate_pass_rate(
    *,
    d4d5: Mapping[str, Any],
    funnel: Mapping[str, Any],
    reject_counts: Mapping[str, int],
    detect_count: int,
    registered_candidate_count: int,
) -> float | None:
    explicit_rate = _first_float(
        d4d5.get("geometry_gate_pass_rate"),
        d4d5.get("secondary_geometry_gate_pass_rate"),
        funnel.get("geometry_gate_pass_rate"),
    )
    if explicit_rate is not None:
        return _clamp_rate(explicit_rate)
    pass_count = _first_int(
        d4d5.get("geometry_gate_pass_count"),
        d4d5.get("secondary_geometry_gate_pass_count"),
        funnel.get("geometry_gate_pass_count"),
        registered_candidate_count if registered_candidate_count > 0 else None,
    )
    total_count = _first_int(
        d4d5.get("geometry_gate_candidate_count"),
        d4d5.get("secondary_geometry_gate_candidate_count"),
        funnel.get("geometry_gate_candidate_count"),
        detect_count,
    )
    if pass_count is not None and total_count and total_count > 0:
        return _clamp_rate(pass_count / total_count)
    if detect_count > 0 and "geometry_gate_rejected" in reject_counts:
        return _clamp_rate((detect_count - int(reject_counts.get("geometry_gate_rejected", 0))) / detect_count)
    return None


def _clamp_rate(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _single_or_mean(values: Sequence[float | int]) -> float | None:
    if not values:
        return None
    unique = sorted({float(value) for value in values})
    if len(unique) == 1:
        return unique[0]
    return sum(float(value) for value in values) / len(values)


def _record_dict(record: AirSimCalibrationRecord | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(record, AirSimCalibrationRecord):
        return record.to_dict()
    return dict(record)


def _group_value(value: Any) -> Any:
    if value is None:
        return "not_recorded"
    if isinstance(value, float):
        return round(value, 6)
    text = _text(value)
    return text if text is not None else "not_recorded"


def _summary_sort_key(item: tuple[tuple[Any, ...], list[dict[str, Any]]]) -> tuple[str, ...]:
    return tuple(str(value) for value in item[0])


def _sum_int(records: Sequence[Mapping[str, Any]], field_name: str) -> int:
    total = 0
    for record in records:
        value = _first_int(record.get(field_name))
        if value is not None:
            total += value
    return total


def _mean_field(records: Sequence[Mapping[str, Any]], field_name: str) -> float:
    values = [
        value
        for record in records
        for value in [_first_float(record.get(field_name))]
        if value is not None
    ]
    return sum(values) / len(values) if values else 0.0


def _weighted_mean_field(
    records: Sequence[Mapping[str, Any]],
    value_field: str,
    weight_field: str,
) -> float:
    weighted_sum = 0.0
    total_weight = 0
    fallback_values: list[float] = []
    for record in records:
        value = _first_float(record.get(value_field))
        if value is None:
            continue
        weight = _first_int(record.get(weight_field)) or 0
        if weight > 0:
            weighted_sum += value * weight
            total_weight += weight
        else:
            fallback_values.append(value)
    if total_weight:
        return weighted_sum / total_weight
    return sum(fallback_values) / len(fallback_values) if fallback_values else 0.0


def _sum_count_mappings(records: Sequence[Mapping[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        for key, value in _count_mapping(record.get(field_name)).items():
            counts[key] = counts.get(key, 0) + value
    return dict(sorted(counts.items()))


def _unique_text_values(records: Sequence[Mapping[str, Any]], field_name: str) -> list[str]:
    values = {
        text
        for record in records
        for text in [_text(record.get(field_name))]
        if text is not None and text != "not_recorded"
    }
    return sorted(values)


def _unique_list_values(records: Sequence[Mapping[str, Any]], field_name: str) -> list[str]:
    values: set[str] = set()
    for record in records:
        values.update(_text_list(record.get(field_name)))
    return sorted(values)


def _range_text(records: Sequence[Mapping[str, Any]], field_name: str) -> str:
    values = sorted(
        {
            value
            for record in records
            for value in [_first_int(record.get(field_name))]
            if value is not None and value > 0
        }
    )
    if not values:
        return "not_recorded"
    if len(values) == 1:
        return str(values[0])
    return f"{values[0]}..{values[-1]}"


def _csv_row(row: Mapping[str, Any], fieldnames: Sequence[str]) -> dict[str, Any]:
    return {field: _csv_value(row.get(field)) for field in fieldnames}


def _csv_value(value: Any) -> Any:
    if isinstance(value, (Mapping, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def _compact_json(value: Any) -> str:
    if value in (None, {}, []):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _format_optional_number(value: Any) -> str:
    number = _first_float(value)
    if number is None:
        return "not_recorded"
    return f"{number:.6g}"


def _float_or_zero(value: Any) -> float:
    number = _first_float(value)
    return 0.0 if number is None else number
