"""Multi-seed AirSim calibration summaries for offline D6 reports."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
import random
import re
import statistics
from typing import Any, Iterable, Mapping, Sequence

from .main_bus import load_main_episode_bus_metrics
from .metrics import EpisodeMetrics
from .standard_mapping import STANDARD_MAPPING_VERSION, standard_mapping_summary


GROUP_FIELDS = [
    "metric_scope",
    "seed",
    "scenario",
    "comparison_role",
    "secondary_height_above_targets_m",
    "secondary_fov_degrees",
    "secondary_count",
    "detection_backend",
]

CROSS_SEED_GROUP_FIELDS = [
    *[field for field in GROUP_FIELDS if field != "seed"],
    "scenario_version",
    "drone_count",
    "resource_count",
    "target_count",
    "camera_count",
]

PAIR_GROUP_FIELDS = [
    "metric_scope",
    "scenario_group",
    "scenario_version",
    "drone_count",
    "resource_count",
    "target_count",
    "camera_count",
    "secondary_height_above_targets_m",
    "secondary_fov_degrees",
    "secondary_count",
    "secondary_image_width_px",
    "secondary_image_height_px",
    "secondary_recon_mode",
    "detection_backend",
]

DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_RNG_SEED = 20260710
MIN_PAIRED_SAMPLES_FOR_CI = 2

CROSS_SEED_METRICS = [
    "secondary_network_joint_full_view_frame_rate",
    "secondary_network_mean_coverage_ratio",
    "secondary_visible_target_union_ratio",
    "secondary_single_camera_full_view_frame_rate",
    "multi_target_fov_rate",
    "projection_valid_rate",
    "geometry_gate_pass_rate",
    "registered_candidate_count",
    "stable_cross_view_registration_count",
    "not_registered_count",
    "active_degradation_count",
    "active_degradation_precision",
    "active_degradation_label_count",
    "unnecessary_degradation_count",
    "d7_guidance_reject_count",
    "intercept_success_count",
    "collision_intercept_count",
    "range_intercept_count",
    "intercept_abort_count",
    "min_range_m",
    "time_to_intercept_s",
    "visual_png_switch_count",
    "terminal_switch_allowed_rate",
    "terminal_takeover_rate",
    "gate_reject_count",
]

PAIRED_COMPARISON_METRICS = list(CROSS_SEED_METRICS)

COUNT_METRICS = {
    "registered_candidate_count",
    "stable_cross_view_registration_count",
    "not_registered_count",
    "active_degradation_count",
    "active_degradation_label_count",
    "unnecessary_degradation_count",
    "d7_guidance_reject_count",
    "intercept_success_count",
    "collision_intercept_count",
    "range_intercept_count",
    "intercept_abort_count",
    "visual_png_switch_count",
    "gate_reject_count",
}

INTERCEPT_OUTCOME_COUNT_METRICS = {
    "intercept_success_count",
    "collision_intercept_count",
    "range_intercept_count",
    "intercept_abort_count",
}

CROSS_SEED_FIELDNAMES = [
    *CROSS_SEED_GROUP_FIELDS,
    "metric",
    "seed_count",
    "seeds",
    "episode_count",
    "value_count",
    "status",
    "sum",
    "opportunity_count",
    "rate",
    "mean",
    "std",
    "min",
    "max",
]

PAIRED_COMPARISON_FIELDNAMES = [
    *PAIR_GROUP_FIELDS,
    "metric",
    "baseline_seed_count",
    "enhanced_seed_count",
    "role_pair_count",
    "pair_count",
    "paired_seeds",
    "missing_baseline_seeds",
    "missing_enhanced_seeds",
    "unavailable_baseline_metric_seeds",
    "unavailable_enhanced_metric_seeds",
    "status",
    "baseline_mean",
    "enhanced_mean",
    "paired_delta_mean",
    "paired_delta_std",
    "effect_size",
    "effect_size_name",
    "bootstrap_ci95_low",
    "bootstrap_ci95_high",
    "bootstrap_resamples",
    "bootstrap_rng_seed",
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
    "comparison_role",
    "scenario_version",
    "standard_mapping_version",
    "standard_metric_family_summary",
    "evidence_path",
    "trend_key",
    "drone_count",
    "resource_count",
    "target_count",
    "camera_count",
    "secondary_count",
    "secondary_height_above_targets_m",
    "secondary_height_bucket",
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
    "active_degradation_label_count",
    "unnecessary_degradation_count",
    "d7_guidance_reject_count",
    "d7_guidance_reject_reason_counts",
    "guidance_law_counts",
    "intercept_success_count",
    "collision_intercept_count",
    "range_intercept_count",
    "intercept_abort_count",
    "min_range_m",
    "time_to_intercept_s",
    "visual_png_switch_count",
    "terminal_switch_allowed_rate",
    "terminal_takeover_rate",
    "gate_reject_count",
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
    "comparison_roles",
    "scenario_versions",
    "standard_mapping_versions",
    "evidence_paths",
    "trend_keys",
    "drone_count",
    "resource_count",
    "target_count",
    "camera_count",
    "secondary_height_buckets",
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
    "active_degradation_label_count",
    "unnecessary_degradation_count",
    "d7_guidance_reject_count",
    "d7_guidance_reject_reason_counts",
    "guidance_law_counts",
    "intercept_success_count",
    "collision_intercept_count",
    "range_intercept_count",
    "intercept_abort_count",
    "min_range_m_mean",
    "time_to_intercept_s_mean",
    "visual_png_switch_count",
    "terminal_switch_allowed_rate_mean",
    "terminal_takeover_rate_mean",
    "gate_reject_count",
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
    comparison_role: str = "not_recorded"
    scenario_version: str = ""
    standard_mapping_version: str = STANDARD_MAPPING_VERSION
    standard_metric_family_summary: str = ""
    evidence_path: str = ""
    trend_key: str = ""
    drone_count: int = 0
    resource_count: int = 0
    target_count: int = 0
    camera_count: int = 0
    secondary_count: int = 0
    secondary_height_above_targets_m: float | None = None
    secondary_height_bucket: str = "not_recorded"
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
    active_degradation_label_count: int = 0
    unnecessary_degradation_count: int = 0
    d7_guidance_reject_count: int = 0
    d7_guidance_reject_reason_counts: dict[str, int] = field(default_factory=dict)
    guidance_law_counts: dict[str, int] = field(default_factory=dict)
    intercept_success_count: int | None = None
    collision_intercept_count: int | None = None
    range_intercept_count: int | None = None
    intercept_abort_count: int | None = None
    min_range_m: float | None = None
    time_to_intercept_s: float | None = None
    visual_png_switch_count: int | None = None
    terminal_switch_allowed_rate: float | None = None
    terminal_takeover_rate: float | None = None
    gate_reject_count: int | None = None
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

    def aggregate_cross_seed(
        self,
        records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        return aggregate_cross_seed_airsim_calibration_records(records)

    def compare_paired(
        self,
        records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
        *,
        bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
        bootstrap_rng_seed: int = DEFAULT_BOOTSTRAP_RNG_SEED,
    ) -> list[dict[str, Any]]:
        return compare_paired_airsim_calibration_records(
            records,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
        )

    def write_standard_mapping_csv(
        self,
        path: str | Path,
    ) -> Path:
        from .reporting import ReportGenerator

        return ReportGenerator().write_standard_mapping_csv(path)

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
        bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
        bootstrap_rng_seed: int = DEFAULT_BOOTSTRAP_RNG_SEED,
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        records = self.load_records(input_paths)
        rows = self.summarize(records)
        aggregate_rows = self.aggregate_cross_seed(records)
        comparison_rows = self.compare_paired(
            records,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
        )
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
            "cross_seed_csv": write_airsim_calibration_cross_seed_csv(
                aggregate_rows,
                output_dir / "airsim_calibration_cross_seed_aggregate.csv",
            ),
            "paired_comparison_csv": write_airsim_calibration_paired_comparison_csv(
                comparison_rows,
                output_dir / "airsim_calibration_paired_comparison.csv",
            ),
            "aggregate_json": write_airsim_calibration_aggregate_json(
                aggregate_rows,
                comparison_rows,
                output_dir / "airsim_calibration_aggregate.json",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
            ),
            "aggregate_markdown": write_airsim_calibration_aggregate_markdown(
                aggregate_rows,
                comparison_rows,
                output_dir / "airsim_calibration_aggregate_report.md",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
            ),
            "standard_mapping_csv": self.write_standard_mapping_csv(
                output_dir / "standard_metric_mapping.csv",
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
                "comparison_roles": _unique_text_values(
                    grouped_records,
                    "comparison_role",
                ),
                "scenario_versions": _unique_text_values(
                    grouped_records,
                    "scenario_version",
                ),
                "standard_mapping_versions": _unique_text_values(
                    grouped_records,
                    "standard_mapping_version",
                ),
                "evidence_paths": _unique_text_values(
                    grouped_records,
                    "evidence_path",
                ),
                "trend_keys": _unique_text_values(grouped_records, "trend_key"),
                "drone_count": _range_text(grouped_records, "drone_count"),
                "resource_count": _range_text(grouped_records, "resource_count"),
                "target_count": _range_text(grouped_records, "target_count"),
                "camera_count": _range_text(grouped_records, "camera_count"),
                "secondary_height_buckets": _unique_text_values(
                    grouped_records,
                    "secondary_height_bucket",
                ),
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
                "active_degradation_precision_mean": _weighted_mean_field(
                    grouped_records,
                    "active_degradation_precision",
                    "active_degradation_label_count",
                    fallback_unweighted=False,
                ),
                "active_degradation_label_count": _sum_int(
                    grouped_records,
                    "active_degradation_label_count",
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
                "intercept_success_count": _sum_int_or_none(
                    grouped_records,
                    "intercept_success_count",
                ),
                "collision_intercept_count": _sum_int_or_none(
                    grouped_records,
                    "collision_intercept_count",
                ),
                "range_intercept_count": _sum_int_or_none(
                    grouped_records,
                    "range_intercept_count",
                ),
                "intercept_abort_count": _sum_int_or_none(
                    grouped_records,
                    "intercept_abort_count",
                ),
                "min_range_m_mean": _mean_field_or_none(
                    grouped_records,
                    "min_range_m",
                ),
                "time_to_intercept_s_mean": _mean_field_or_none(
                    grouped_records,
                    "time_to_intercept_s",
                ),
                "visual_png_switch_count": _sum_int_or_none(
                    grouped_records,
                    "visual_png_switch_count",
                ),
                "terminal_switch_allowed_rate_mean": _mean_field_or_none(
                    grouped_records,
                    "terminal_switch_allowed_rate",
                ),
                "terminal_takeover_rate_mean": _mean_field_or_none(
                    grouped_records,
                    "terminal_takeover_rate",
                ),
                "gate_reject_count": _sum_int_or_none(
                    grouped_records,
                    "gate_reject_count",
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


def aggregate_cross_seed_airsim_calibration_records(
    records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate per-seed values without changing the legacy seed grouping."""

    grouped: dict[tuple[Any, ...], dict[Any, list[dict[str, Any]]]] = {}
    for record in (_record_dict(item) for item in records):
        key = tuple(
            _calibration_group_value(record, field)
            for field in CROSS_SEED_GROUP_FIELDS
        )
        seed_value = _first_int(record.get("seed"))
        seed = seed_value if seed_value is not None else "not_recorded"
        grouped.setdefault(key, {}).setdefault(seed, []).append(record)

    rows: list[dict[str, Any]] = []
    for key, seed_records in sorted(grouped.items(), key=_cross_seed_sort_key):
        group_values = dict(zip(CROSS_SEED_GROUP_FIELDS, key))
        seeds = sorted(seed_records, key=lambda value: str(value))
        episode_count = sum(len(items) for items in seed_records.values())
        for metric in CROSS_SEED_METRICS:
            values = [
                value
                for seed in seeds
                for value in [_aggregate_metric_value(seed_records[seed], metric)]
                if value is not None
            ]
            opportunity_count = _intercept_opportunity_count(
                seed_records,
                metric,
            )
            total = sum(values) if values and metric in COUNT_METRICS else None
            rows.append(
                {
                    **group_values,
                    "metric": metric,
                    "seed_count": len(seeds),
                    "seeds": seeds,
                    "episode_count": episode_count,
                    "value_count": len(values),
                    "status": "available" if values else "unavailable",
                    "sum": total,
                    "opportunity_count": opportunity_count,
                    "rate": (
                        total / opportunity_count
                        if total is not None and opportunity_count
                        else None
                    ),
                    "mean": statistics.fmean(values) if values else None,
                    "std": _sample_std(values),
                    "min": min(values) if values else None,
                    "max": max(values) if values else None,
                }
            )
    return rows


def compare_paired_airsim_calibration_records(
    records: Iterable[AirSimCalibrationRecord | Mapping[str, Any]],
    *,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_BOOTSTRAP_RNG_SEED,
) -> list[dict[str, Any]]:
    """Compare explicit baseline/enhanced roles using strict seed pairing."""

    if bootstrap_resamples <= 0:
        raise ValueError("bootstrap_resamples must be positive")

    grouped: dict[
        tuple[Any, ...],
        dict[str, dict[int, list[dict[str, Any]]]],
    ] = {}
    for record in (_record_dict(item) for item in records):
        role = _normalize_comparison_role(
            record.get("comparison_role"),
            allow_heuristic=False,
        )
        seed = _first_int(record.get("seed"))
        if role not in {"baseline", "enhanced"} or seed is None:
            continue
        key = tuple(
            _calibration_group_value(record, field) for field in PAIR_GROUP_FIELDS
        )
        grouped.setdefault(key, {}).setdefault(role, {}).setdefault(seed, []).append(
            record
        )

    rows: list[dict[str, Any]] = []
    for key, role_records in sorted(grouped.items(), key=_paired_group_sort_key):
        group_values = dict(zip(PAIR_GROUP_FIELDS, key))
        baseline_records = role_records.get("baseline", {})
        enhanced_records = role_records.get("enhanced", {})
        baseline_seeds = set(baseline_records)
        enhanced_seeds = set(enhanced_records)
        role_pair_seeds = sorted(baseline_seeds & enhanced_seeds)
        missing_baseline = sorted(enhanced_seeds - baseline_seeds)
        missing_enhanced = sorted(baseline_seeds - enhanced_seeds)

        for metric in PAIRED_COMPARISON_METRICS:
            baseline_values = {
                seed: _aggregate_metric_value(items, metric)
                for seed, items in baseline_records.items()
            }
            enhanced_values = {
                seed: _aggregate_metric_value(items, metric)
                for seed, items in enhanced_records.items()
            }
            paired_seeds = [
                seed
                for seed in role_pair_seeds
                if baseline_values.get(seed) is not None
                and enhanced_values.get(seed) is not None
            ]
            unavailable_baseline = [
                seed for seed in role_pair_seeds if baseline_values.get(seed) is None
            ]
            unavailable_enhanced = [
                seed for seed in role_pair_seeds if enhanced_values.get(seed) is None
            ]
            paired_baseline = [float(baseline_values[seed]) for seed in paired_seeds]
            paired_enhanced = [float(enhanced_values[seed]) for seed in paired_seeds]
            deltas = [
                enhanced - baseline
                for baseline, enhanced in zip(paired_baseline, paired_enhanced)
            ]
            delta_std = _sample_std(deltas)
            delta_mean = statistics.fmean(deltas) if deltas else None
            ci_low, ci_high = (None, None)
            if len(deltas) >= MIN_PAIRED_SAMPLES_FOR_CI:
                ci_low, ci_high = _bootstrap_mean_ci(
                    deltas,
                    resamples=bootstrap_resamples,
                    rng_seed=bootstrap_rng_seed,
                )
            effect_size = (
                delta_mean / delta_std
                if delta_mean is not None
                and delta_std is not None
                and delta_std > 0.0
                else None
            )
            rows.append(
                {
                    **group_values,
                    "metric": metric,
                    "baseline_seed_count": len(baseline_seeds),
                    "enhanced_seed_count": len(enhanced_seeds),
                    "role_pair_count": len(role_pair_seeds),
                    "pair_count": len(paired_seeds),
                    "paired_seeds": paired_seeds,
                    "missing_baseline_seeds": missing_baseline,
                    "missing_enhanced_seeds": missing_enhanced,
                    "unavailable_baseline_metric_seeds": unavailable_baseline,
                    "unavailable_enhanced_metric_seeds": unavailable_enhanced,
                    "status": (
                        "available"
                        if len(deltas) >= MIN_PAIRED_SAMPLES_FOR_CI
                        else "descriptive_only"
                        if deltas
                        else "unavailable"
                    ),
                    "baseline_mean": (
                        statistics.fmean(paired_baseline)
                        if paired_baseline
                        else None
                    ),
                    "enhanced_mean": (
                        statistics.fmean(paired_enhanced)
                        if paired_enhanced
                        else None
                    ),
                    "paired_delta_mean": delta_mean,
                    "paired_delta_std": delta_std,
                    "effect_size": effect_size,
                    "effect_size_name": "cohens_dz",
                    "bootstrap_ci95_low": ci_low,
                    "bootstrap_ci95_high": ci_high,
                    "bootstrap_resamples": bootstrap_resamples,
                    "bootstrap_rng_seed": bootstrap_rng_seed,
                }
            )
    return rows


def write_airsim_calibration_cross_seed_csv(
    rows: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> Path:
    return _write_rows_csv(rows, path, CROSS_SEED_FIELDNAMES)


def write_airsim_calibration_paired_comparison_csv(
    rows: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> Path:
    return _write_rows_csv(rows, path, PAIRED_COMPARISON_FIELDNAMES)


def write_airsim_calibration_aggregate_json(
    aggregate_rows: Iterable[Mapping[str, Any]],
    comparison_rows: Iterable[Mapping[str, Any]],
    path: str | Path,
    *,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_BOOTSTRAP_RNG_SEED,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cross_seed_group_fields": CROSS_SEED_GROUP_FIELDS,
        "pair_group_fields": PAIR_GROUP_FIELDS,
        "bootstrap": {
            "method": "paired_seed_mean_percentile",
            "confidence_level": 0.95,
            "minimum_pair_count": MIN_PAIRED_SAMPLES_FOR_CI,
            "resamples": bootstrap_resamples,
            "rng_seed": bootstrap_rng_seed,
        },
        "cross_seed_rows": [dict(row) for row in aggregate_rows],
        "paired_comparison_rows": [dict(row) for row in comparison_rows],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def write_airsim_calibration_aggregate_markdown(
    aggregate_rows: Iterable[Mapping[str, Any]],
    comparison_rows: Iterable[Mapping[str, Any]],
    path: str | Path,
    *,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_BOOTSTRAP_RNG_SEED,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    aggregate = [dict(row) for row in aggregate_rows]
    comparisons = [dict(row) for row in comparison_rows]
    lines = [
        "# D6 AirSim 跨 Seed 聚合与配对比较",
        "",
        "本报告由 D6 离线消费已写盘日志；D6 不参与控制、重规划、云台指向或导引。",
        "",
        f"- Cross-seed 分组字段: {', '.join(CROSS_SEED_GROUP_FIELDS)}",
        f"- Pair 分组字段: {', '.join(PAIR_GROUP_FIELDS)} + seed",
        f"- Bootstrap: percentile 95% CI, resamples={bootstrap_resamples}, rng_seed={bootstrap_rng_seed}",
        f"- Inferential minimum: pair_count >= {MIN_PAIRED_SAMPLES_FOR_CI}; one pair is descriptive_only and has no CI/effect size.",
        "- Effect size: paired Cohen's dz；paired delta = enhanced - baseline。",
        "",
        "## Cross-seed Aggregate",
        "",
        "| Scope | Scenario | Role | Geometry/backend | Actual scale | Metric | Seeds | Values | Status | Total | Opportunity | Rate | Mean | Std |",
        "|---|---|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for row in aggregate:
        lines.append(
            "| {scope} | {scenario} | {role} | {geometry} | {scale} | {metric} | {seed_count} | {value_count} | {status} | {total} | {opportunity} | {rate} | {mean} | {std} |".format(
                scope=_markdown_cell(row.get("metric_scope")),
                scenario=_markdown_cell(row.get("scenario")),
                role=_markdown_cell(row.get("comparison_role")),
                geometry=_markdown_cell(_aggregate_geometry_text(row)),
                scale=_markdown_cell(_scale_text(row)),
                metric=_markdown_cell(row.get("metric")),
                seed_count=int(row.get("seed_count", 0) or 0),
                value_count=int(row.get("value_count", 0) or 0),
                status=_markdown_cell(row.get("status")),
                total=_format_available_number(row.get("sum")),
                opportunity=_format_available_number(row.get("opportunity_count")),
                rate=_format_available_number(row.get("rate")),
                mean=_format_available_number(row.get("mean")),
                std=_format_available_number(row.get("std")),
            )
        )

    lines.extend(
        [
            "",
            "## Interception Outcome",
            "",
            "该表只汇总有 intercept_summary/D7 execution evidence 的 `intercept_success_count`。分母来自同一 scope、同一实际规模组内各有效 seed 的 `target_count` 总和；execution 是执行结果，contract 是独立合同诊断，不混合计算。",
            "",
            "| Scope | Scenario | Seeds | Scale | Success / opportunity | Success rate |",
            "|---|---|---:|---|---:|---:|",
        ]
    )
    success_rows = [
        row
        for row in aggregate
        if row.get("metric") == "intercept_success_count"
        and row.get("status") == "available"
        and _first_int(row.get("opportunity_count")) is not None
    ]
    for row in success_rows:
        success_total = _first_float(row.get("sum"))
        opportunity_count = _first_int(row.get("opportunity_count"))
        outcome = (
            f"{int(success_total)}/{opportunity_count}"
            if success_total is not None and opportunity_count
            else "unavailable"
        )
        lines.append(
            "| {scope} | {scenario} | {seed_count} | {scale} | {outcome} | {rate} |".format(
                scope=_markdown_cell(row.get("metric_scope")),
                scenario=_markdown_cell(row.get("scenario")),
                seed_count=int(row.get("seed_count", 0) or 0),
                scale=_markdown_cell(_scale_text(row)),
                outcome=outcome,
                rate=_format_available_number(row.get("rate")),
            )
        )
    if not success_rows:
        lines.append("| unavailable | unavailable | 0 | unavailable | unavailable | unavailable |")

    lines.extend(
        [
            "",
            "## Paired Baseline vs Enhanced",
            "",
            "仅显式 `comparison_role=baseline|enhanced` 参与配对。相同 seed 还必须匹配稳定 scenario_group、scenario_version、实际 N/M/camera count、几何和 detection backend；case_name 只保留审计。",
            "",
            "| Scope | Scenario group | Geometry/backend | Actual scale | Metric | Pair count | Missing baseline seeds | Missing enhanced seeds | Delta mean | Delta std | Cohen's dz | Bootstrap 95% CI |",
            "|---|---|---|---|---|---:|---|---|---:|---:|---:|---|",
        ]
    )
    for row in comparisons:
        lines.append(
            "| {scope} | {scenario} | {geometry} | {scale} | {metric} | {pair_count} | {missing_baseline} | {missing_enhanced} | {delta_mean} | {delta_std} | {effect_size} | [{ci_low}, {ci_high}] |".format(
                scope=_markdown_cell(row.get("metric_scope")),
                scenario=_markdown_cell(row.get("scenario_group")),
                geometry=_markdown_cell(_aggregate_geometry_text(row)),
                scale=_markdown_cell(_scale_text(row)),
                metric=_markdown_cell(row.get("metric")),
                pair_count=int(row.get("pair_count", 0) or 0),
                missing_baseline=_markdown_cell(
                    _compact_json(row.get("missing_baseline_seeds")) or "[]"
                ),
                missing_enhanced=_markdown_cell(
                    _compact_json(row.get("missing_enhanced_seeds")) or "[]"
                ),
                delta_mean=_format_available_number(row.get("paired_delta_mean")),
                delta_std=_format_available_number(row.get("paired_delta_std")),
                effect_size=_format_available_number(row.get("effect_size")),
                ci_low=_format_available_number(row.get("bootstrap_ci95_low")),
                ci_high=_format_available_number(row.get("bootstrap_ci95_high")),
            )
        )

    lines.extend(
        [
            "",
            "## Availability Contract",
            "",
            "- `active_degradation_precision` 只以可分类 review label 样本为分母。",
            "- `active_degradation_label_count=0` 时 precision 为 `unavailable`，JSON 为 `null`，CSV 留空。",
            "- `scenario_version` 原值保留在 records；跨 seed/配对分组仅移除其中的 seed 参数，防止同一版本被按 seed 拆组。",
            "- D6 不从事件名、2v2/5v5 场景名或未标注 active degradation 推断必要性。",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
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
    height_comparison_rows = _height_50_200_comparison_rows(summary_rows)
    coverage_funnel_rows = _coverage_funnel_rows(summary_rows)
    baseline_rows = _baseline_enhanced_rows(summary_rows)

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
        f"- Scenario version: {', '.join(_unique_text_values(record_dicts, 'scenario_version')) or 'not_recorded'}",
        f"- Standard mapping version: {', '.join(_unique_text_values(record_dicts, 'standard_mapping_version')) or STANDARD_MAPPING_VERSION}",
        "",
        "## 1. 分组摘要",
        "",
        "| Scope | Seed | Scenario | Role | Height m | FOV deg | Secondary count | Backend | Scale | Episodes | Coverage mean | Full-view rate | Detect | Stable registration | Not registered | Gimbal OK | Active precision | Label count | Unnecessary degradation | D7 reject | Evidence paths |",
        "|---|---:|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {role} | {height} | {fov} | {secondary_count} | {backend} | {scale} | {episodes} | {coverage:.6g} | {full_view:.6g} | {detect} | {cross_view} | {not_registered} | {gimbal:.6g} | {active_precision} | {label_count} | {unnecessary} | {d7_reject} | {evidence} |".format(
                metric_scope=row.get("metric_scope", "not_recorded"),
                seed=row.get("seed", "not_recorded"),
                scenario=row.get("scenario", "not_recorded"),
                role=_summary_text(row, "comparison_roles"),
                height=_format_optional_number(row.get("secondary_height_above_targets_m")),
                fov=_format_optional_number(row.get("secondary_fov_degrees")),
                secondary_count=row.get("secondary_count", "not_recorded"),
                backend=row.get("detection_backend", "not_recorded"),
                scale=_scale_text(row),
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
                active_precision=_format_available_number(
                    row.get("active_degradation_precision_mean")
                ),
                label_count=int(row.get("active_degradation_label_count", 0) or 0),
                unnecessary=int(row.get("unnecessary_degradation_count", 0) or 0),
                d7_reject=int(row.get("d7_guidance_reject_count", 0) or 0),
                evidence=_summary_text(row, "evidence_paths"),
            )
        )

    lines.extend(
        [
            "",
            "## 2. 50m vs 200m Secondary Coverage",
            "",
            "该表按相同 scope/seed/scenario/role/FOV/secondary count/backend/actual scale 对齐 50m 与 200m 二级高度，缺失高度保留 `not_recorded`，不从场景名推断规模。",
            "",
            "| Scope | Seed | Scenario | Role | FOV deg | Secondary count | Backend | Scale | Coverage 50m | Coverage 200m | Delta 200m-50m | Full-view 50m | Full-view 200m | Stable reg 50m | Stable reg 200m | Not reg 50m | Not reg 200m | D7 reject 50m | D7 reject 200m |",
            "|---|---:|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if height_comparison_rows:
        for row in height_comparison_rows:
            lines.append(
                "| {metric_scope} | {seed} | {scenario} | {comparison_role} | {fov} | {secondary_count} | {backend} | {scale} | {coverage_50m} | {coverage_200m} | {coverage_delta} | {full_view_50m} | {full_view_200m} | {stable_50m} | {stable_200m} | {not_registered_50m} | {not_registered_200m} | {d7_reject_50m} | {d7_reject_200m} |".format(
                    **row
                )
            )
    else:
        lines.append(
            "| not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded |"
        )

    lines.extend(
        [
            "",
            "## 3. Coverage Funnel",
            "",
            "该表把二级覆盖、可见并集、full-view、检测、投影、几何门控、稳定注册和未注册数量串成同一漏斗，便于长期趋势跟踪。",
            "",
            "| Scope | Seed | Scenario | Role | Height bucket | Coverage mean | Visible union | Joint full-view | Single-camera full-view | Multi-target FOV | Detect | Projection valid | Gate pass | Stable registration | Not registered | Trend key |",
            "|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in coverage_funnel_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {comparison_role} | {height_bucket} | {coverage:.6g} | {visible_union:.6g} | {joint_full_view:.6g} | {single_full_view:.6g} | {multi_target_fov:.6g} | {detect} | {projection:.6g} | {gate:.6g} | {stable} | {not_registered} | {trend_key} |".format(
                **row
            )
        )

    lines.extend(
        [
            "",
            "## 4. Detect-to-registration Funnel",
            "",
            "该表把二级检测进入 D5 跨视角配准前后的断点展开。`detect_count` 是二级检测机会；`projection_valid_rate` 和 `geometry_gate_pass_rate` 是几何链路质量；`stable_cross_view_registration_count` 是稳定跨视角注册数量。",
            "",
            "| Scope | Seed | Scenario | Role | Breakpoint reasons | Reject/outcome counts | Detect | Projection valid | Gate pass | Candidate | Stable registration | Not registered |",
            "|---|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {role} | {breakpoints} | {rejects} | {detect} | {projection:.6g} | {gate:.6g} | {candidate} | {stable} | {not_registered} |".format(
                metric_scope=row.get("metric_scope", "not_recorded"),
                seed=row.get("seed", "not_recorded"),
                scenario=row.get("scenario", "not_recorded"),
                role=_summary_text(row, "comparison_roles"),
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
            "## 5. Baseline vs Enhanced",
            "",
            "该表只消费日志中显式写出的 baseline/enhanced role；缺少 role 时不会由 D6 把场景规模或 2v2/5v5 名称解释成对照组。",
            "",
            "| Scope | Seed | Scenario | Height bucket | FOV deg | Secondary count | Backend | Scale | Baseline coverage | Enhanced coverage | Delta enhanced-baseline | Baseline stable reg | Enhanced stable reg | Baseline not reg | Enhanced not reg | Baseline active precision | Enhanced active precision | Baseline unnecessary | Enhanced unnecessary | Baseline D7 reject | Enhanced D7 reject | Evidence paths |",
            "|---|---:|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    if baseline_rows:
        for row in baseline_rows:
            lines.append(
                "| {metric_scope} | {seed} | {scenario} | {height_bucket} | {fov} | {secondary_count} | {backend} | {scale} | {baseline_coverage} | {enhanced_coverage} | {coverage_delta} | {baseline_stable} | {enhanced_stable} | {baseline_not_registered} | {enhanced_not_registered} | {baseline_active_precision} | {enhanced_active_precision} | {baseline_unnecessary} | {enhanced_unnecessary} | {baseline_d7_reject} | {enhanced_d7_reject} | {evidence_paths} |".format(
                    **row
                )
            )
    else:
        lines.append(
            "| not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded | not_recorded |"
        )

    lines.extend(
        [
            "",
            "## 6. D7 Guidance Reject Reason",
            "",
            "| Scope | Seed | Scenario | Role | Reject reason counts | Guidance law counts |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {metric_scope} | {seed} | {scenario} | {role} | {rejects} | {laws} |".format(
                metric_scope=row.get("metric_scope", "not_recorded"),
                seed=row.get("seed", "not_recorded"),
                scenario=row.get("scenario", "not_recorded"),
                role=_summary_text(row, "comparison_roles"),
                rejects=_compact_json(row.get("d7_guidance_reject_reason_counts")),
                laws=_compact_json(row.get("guidance_law_counts")),
            )
        )

    mapping_summary = standard_mapping_summary()
    family_counts = mapping_summary.get("family_counts", {})
    sources = mapping_summary.get("standard_sources", [])
    families = mapping_summary.get("standard_metric_families", [])
    lines.extend(
        [
            "",
            "## 7. Standard C-UAS Mapping",
            "",
            f"- Mapping version: {mapping_summary['version']}",
            f"- 标准来源: {', '.join(sources) if sources else 'not_recorded'}",
            f"- 覆盖的指标族: {', '.join(families) if families else 'not_recorded'}",
            "",
            "| Metric family | Mapped metric count |",
            "|---|---:|",
        ]
    )
    for family in families:
        lines.append(f"| {_markdown_cell(family)} | {int(family_counts.get(family, 0) or 0)} |")

    lines.extend(
        [
            "",
            "## 8. 解读口径",
            "",
            "- coverage/full-view/gimbal 指标来自 main/D4/D5 已写盘的 D4D5 stress 或 main bus metadata，用于长期趋势比较。",
            "- active degradation precision 只使用 main/D4 写出的 review label 或后验字段；缺少标签时不会由事件名自证必要性。",
            "- D7 reject reason 同时汇总 terminal switch 与 terminal contract reject 分布，用于 execution/contract 对照。",
            "- baseline vs enhanced 只使用显式 comparison role；D6 不接 TrackEval、Stone Soup、SCRIMMAGE 或在线控制接口。",
            "- 规模字段使用 runtime metrics 或日志中的实际 count 字段；报告不从 `2v2/5v5` 场景名推断目标数、资源数或相机数。",
            "",
            "## 9. 文件索引",
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
    scenario_version = _first_text(
        _metric_attr(metrics, "scenario_version"),
        metrics_metadata.get("scenario_version"),
        d4d5.get("scenario_version"),
        blocks_metadata.get("scenario_version"),
    ) or ""
    standard_mapping_version = _first_text(
        _metric_attr(metrics, "standard_mapping_version"),
        metrics_metadata.get("standard_mapping_version"),
        d4d5.get("standard_mapping_version"),
        blocks_metadata.get("standard_mapping_version"),
        STANDARD_MAPPING_VERSION,
    ) or STANDARD_MAPPING_VERSION
    standard_metric_family_summary = _first_text(
        _metric_attr(metrics, "standard_metric_family_summary"),
        metrics_metadata.get("standard_metric_family_summary"),
        d4d5.get("standard_metric_family_summary"),
        blocks_metadata.get("standard_metric_family_summary"),
    ) or ""
    # The persisted metrics file is the authoritative evidence for this row.
    # In particular, a contract payload can inherit the execution evidence path
    # upstream; preferring ``metrics_path`` keeps the two scopes auditable.
    evidence_path = _first_text(
        str(metrics_path) if metrics_path is not None else None,
        _metric_attr(metrics, "evidence_path"),
        metrics_metadata.get("evidence_path"),
        d4d5.get("evidence_path"),
        blocks_metadata.get("evidence_path"),
        str(metrics_path) if metrics_path is not None else None,
        str(d4d5_path) if d4d5_path is not None else None,
        str(blocks_path) if blocks_path is not None else None,
    ) or ""
    comparison_role = _comparison_role(
        metrics_metadata=metrics_metadata,
        d4d5=d4d5,
        blocks_metadata=blocks_metadata,
        scenario=scenario,
        scenario_group=scenario_group,
        case_name=case_name,
    )

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
    intercept_execution_available = _has_intercept_execution_evidence(
        episode_dir=episode_dir,
        metadata=metrics_metadata,
    )
    intercept_abort_count = (
        _intercept_abort_count(metrics_metadata)
        if intercept_execution_available
        else None
    )
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
    secondary_height_above_targets_m = _first_float(
        d4d5.get("secondary_height_above_targets_m"),
        geometry.get("secondary_height_above_targets_m"),
    )
    secondary_fov_degrees = _first_float(
        d4d5.get("secondary_fov_degrees"),
        d4d5.get("secondary_fov_deg"),
        d4d5.get("secondary_camera_fov_degrees"),
        settings_summary.get("secondary_fov_degrees"),
    )
    active_degradation_label_count = _first_int(
        d4d5.get("active_degradation_label_count"),
        d4d5.get("active_degradation_reviewed_count"),
        _active_degradation_label_count(metrics),
        0,
    ) or 0
    trend_key = _trend_key(
        metric_scope=metric_scope,
        scenario=scenario,
        comparison_role=comparison_role,
        scenario_version=scenario_version,
        drone_count=drone_count,
        resource_count=resource_count,
        target_count=target_count,
        camera_count=camera_count,
        secondary_count=secondary_count,
        secondary_height_above_targets_m=secondary_height_above_targets_m,
        secondary_fov_degrees=secondary_fov_degrees,
        detection_backend=_detection_backend(d4d5, blocks_metadata, episode_dir),
    )

    return AirSimCalibrationRecord(
        episode_id=_first_text(_metric_attr(metrics, "episode_id"), blocks.get("episode_id"), episode_dir.name) or episode_dir.name,
        seed=seed,
        batch_seed=_first_int(_metric_attr(metrics, "batch_seed"), seed),
        scenario=scenario,
        scenario_group=scenario_group or "not_recorded",
        case_name=case_name or "not_recorded",
        metric_scope=metric_scope,
        comparison_role=comparison_role,
        scenario_version=scenario_version,
        standard_mapping_version=standard_mapping_version,
        standard_metric_family_summary=standard_metric_family_summary,
        evidence_path=evidence_path,
        trend_key=trend_key,
        drone_count=int(drone_count or 0),
        resource_count=int(resource_count or 0),
        target_count=int(target_count or 0),
        camera_count=int(camera_count or 0),
        secondary_count=int(secondary_count or 0),
        secondary_height_above_targets_m=secondary_height_above_targets_m,
        secondary_height_bucket=_secondary_height_bucket(
            secondary_height_above_targets_m
        ),
        secondary_fov_degrees=secondary_fov_degrees,
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
        active_degradation_count=int(
            _first_int(
                d4d5.get("active_degradation_count"),
                _metric_attr(metrics, "active_degradation_count"),
                0,
            )
            or 0
        ),
        active_degradation_precision=(
            _first_float(
                d4d5.get("active_degradation_precision"),
                _metric_attr(metrics, "active_degradation_precision"),
            )
            if active_degradation_label_count > 0
            else None
        ),
        active_degradation_label_count=active_degradation_label_count,
        unnecessary_degradation_count=int(
            _first_int(
                d4d5.get("unnecessary_active_degradation_count"),
                d4d5.get("unnecessary_degradation_count"),
                _metric_attr(metrics, "unnecessary_active_degradation_count"),
                0,
            )
            or 0
        ),
        d7_guidance_reject_count=sum(d7_reject_reasons.values()),
        d7_guidance_reject_reason_counts=d7_reject_reasons,
        guidance_law_counts=guidance_laws,
        intercept_success_count=_available_metric_int(
            metrics,
            "intercept_success_count",
            available=intercept_execution_available,
        ),
        collision_intercept_count=_available_metric_int(
            metrics,
            "collision_intercept_count",
            available=intercept_execution_available,
        ),
        range_intercept_count=_available_metric_int(
            metrics,
            "range_intercept_count",
            available=intercept_execution_available,
        ),
        intercept_abort_count=intercept_abort_count,
        min_range_m=_available_metric_float(
            metrics,
            "min_range_m",
            available=intercept_execution_available,
        ),
        time_to_intercept_s=_available_metric_float(
            metrics,
            "time_to_intercept_s",
            available=intercept_execution_available,
        ),
        visual_png_switch_count=_available_metric_int(
            metrics,
            "visual_png_switch_count",
            available=intercept_execution_available,
        ),
        terminal_switch_allowed_rate=_available_metric_float(
            metrics,
            "terminal_switch_allowed_rate",
            available=intercept_execution_available,
        ),
        terminal_takeover_rate=_available_metric_float(
            metrics,
            "terminal_takeover_rate",
            available=intercept_execution_available,
        ),
        gate_reject_count=_available_metric_int(
            metrics,
            "gate_reject_count",
            available=intercept_execution_available,
        ),
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


def _comparison_role(
    *,
    metrics_metadata: Mapping[str, Any],
    d4d5: Mapping[str, Any],
    blocks_metadata: Mapping[str, Any],
    scenario: str,
    scenario_group: str | None,
    case_name: str | None,
) -> str:
    for mapping in (metrics_metadata, d4d5, blocks_metadata):
        for key in (
            "comparison_role",
            "baseline_enhanced_role",
            "baseline_or_enhanced",
            "calibration_role",
            "scenario_role",
            "experiment_arm",
            "variant_role",
            "treatment",
        ):
            role = _normalize_comparison_role(mapping.get(key), allow_heuristic=True)
            if role != "not_recorded":
                return role

    for value in (case_name, scenario, scenario_group):
        role = _normalize_comparison_role(value, allow_heuristic=False)
        if role != "not_recorded":
            return role
    return "not_recorded"


def _normalize_comparison_role(value: Any, *, allow_heuristic: bool) -> str:
    text = _text(value)
    if text is None:
        return "not_recorded"
    normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
    explicit_baseline = {"baseline", "base", "control", "reference"}
    explicit_enhanced = {
        "enhanced",
        "treatment",
        "candidate",
        "variant",
        "improved",
        "p1_enhanced",
    }
    if normalized in explicit_baseline:
        return "baseline"
    if normalized in explicit_enhanced:
        return "enhanced"
    if allow_heuristic:
        if "baseline" in normalized or normalized.startswith("control_"):
            return "baseline"
        if "enhanced" in normalized or normalized.startswith("candidate_"):
            return "enhanced"
    return "not_recorded"


def _secondary_height_bucket(value: Any) -> str:
    height = _first_float(value)
    if height is None:
        return "not_recorded"
    rounded = int(round(height))
    if abs(height - 50.0) <= 5.0:
        return "secondary_50m"
    if abs(height - 200.0) <= 10.0:
        return "secondary_200m"
    return f"secondary_{rounded}m"


def _trend_key(
    *,
    metric_scope: str,
    scenario: str,
    comparison_role: str,
    scenario_version: str,
    drone_count: int | None,
    resource_count: int | None,
    target_count: int | None,
    camera_count: int | None,
    secondary_count: int | None,
    secondary_height_above_targets_m: float | None,
    secondary_fov_degrees: float | None,
    detection_backend: str,
) -> str:
    scale = (
        f"d{int(drone_count or 0)}"
        f"_r{int(resource_count or 0)}"
        f"_t{int(target_count or 0)}"
        f"_c{int(camera_count or 0)}"
    )
    geometry = (
        f"h{_format_optional_number(secondary_height_above_targets_m)}"
        f"_fov{_format_optional_number(secondary_fov_degrees)}"
        f"_sec{int(secondary_count or 0)}"
    )
    parts = [
        metric_scope or "not_recorded",
        scenario or "not_recorded",
        comparison_role or "not_recorded",
        scenario_version or "unversioned",
        geometry,
        detection_backend or "not_recorded",
        scale,
    ]
    return "|".join(_key_part(part) for part in parts)


def _key_part(value: Any) -> str:
    text = str(value or "not_recorded").strip().lower()
    text = text.replace("-", "_")
    text = re.sub(r"[^a-z0-9_.=-]+", "_", text)
    return text.strip("_") or "not_recorded"


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


def _has_intercept_execution_evidence(
    *,
    episode_dir: Path,
    metadata: Mapping[str, Any],
) -> bool:
    if (episode_dir / "intercept_summary.json").is_file():
        return True
    if (episode_dir / "control_commands.csv").is_file():
        return True
    for key in ("intercept_summary_pair_count", "intercept_summary_success_count"):
        if metadata.get(key) is not None and _first_int(metadata.get(key)) is not None:
            return True
    for key in ("intercept_pair_event_count", "d7_control_command_event_count"):
        count = _first_int(metadata.get(key))
        if count is not None and count > 0:
            return True
    return bool(_count_mapping(metadata.get("intercept_status_counts")))


def _intercept_abort_count(metadata: Mapping[str, Any]) -> int:
    status_counts = _count_mapping(metadata.get("intercept_status_counts"))
    return sum(
        count
        for status, count in status_counts.items()
        if "abort" in status.strip().lower().replace("-", "_")
    )


def _available_metric_int(
    metrics: EpisodeMetrics | None,
    name: str,
    *,
    available: bool,
) -> int | None:
    if not available or metrics is None:
        return None
    value = _first_int(_metric_attr(metrics, name))
    return int(value) if value is not None else None


def _available_metric_float(
    metrics: EpisodeMetrics | None,
    name: str,
    *,
    available: bool,
) -> float | None:
    if not available or metrics is None:
        return None
    return _first_float(_metric_attr(metrics, name))


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


def _active_degradation_label_count(metrics: EpisodeMetrics | None) -> int:
    if metrics is None:
        return 0
    metadata = metrics.metadata if isinstance(metrics.metadata, Mapping) else {}
    for value in (
        getattr(metrics, "active_degradation_label_count", None),
        metadata.get("active_degradation_label_count"),
        metadata.get("active_degradation_reviewed_count"),
        metadata.get("review_label_count"),
    ):
        count = _first_int(value)
        if count is not None and count > 0:
            return count
    return 0


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


_SCENARIO_SEED_COMPONENT = re.compile(
    r"^(?:batch[_-]?)?seed(?:[_=-]?\d+)$",
    flags=re.IGNORECASE,
)


def _calibration_group_value(record: Mapping[str, Any], field_name: str) -> Any:
    value = record.get(field_name)
    if field_name == "scenario_version":
        value = _stable_scenario_version(value)
    return _group_value(value)


def _stable_scenario_version(value: Any) -> str | None:
    """Remove only run-specific seed components from a version string."""

    text = _text(value)
    if text is None:
        return None
    components = [
        component
        for component in text.split(":")
        if component and _SCENARIO_SEED_COMPONENT.fullmatch(component) is None
    ]
    return ":".join(components) or "seed_parameterized"


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


def _sum_int_or_none(
    records: Sequence[Mapping[str, Any]],
    field_name: str,
) -> int | None:
    values = [
        value
        for record in records
        for value in [_first_int(record.get(field_name))]
        if value is not None
    ]
    return sum(values) if values else None


def _mean_field(records: Sequence[Mapping[str, Any]], field_name: str) -> float:
    values = [
        value
        for record in records
        for value in [_first_float(record.get(field_name))]
        if value is not None
    ]
    return sum(values) / len(values) if values else 0.0


def _mean_field_or_none(
    records: Sequence[Mapping[str, Any]],
    field_name: str,
) -> float | None:
    values = [
        value
        for record in records
        for value in [_first_float(record.get(field_name))]
        if value is not None
    ]
    return sum(values) / len(values) if values else None


def _weighted_mean_field(
    records: Sequence[Mapping[str, Any]],
    value_field: str,
    weight_field: str,
    *,
    fallback_unweighted: bool = True,
) -> float | None:
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
    if fallback_unweighted and fallback_values:
        return sum(fallback_values) / len(fallback_values)
    return None


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


def _height_50_200_comparison_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    grouped: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        bucket = _summary_height_bucket(row)
        if bucket not in {"secondary_50m", "secondary_200m"}:
            continue
        key = (
            row.get("metric_scope", "not_recorded"),
            row.get("seed", "not_recorded"),
            row.get("scenario", "not_recorded"),
            _summary_text(row, "comparison_roles"),
            row.get("secondary_fov_degrees", "not_recorded"),
            row.get("secondary_count", "not_recorded"),
            row.get("detection_backend", "not_recorded"),
            _scale_text(row),
        )
        grouped.setdefault(key, {})[bucket] = row

    comparison_rows: list[dict[str, str]] = []
    for key, bucket_rows in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        metric_scope, seed, scenario, comparison_role, fov, secondary_count, backend, scale = key
        row_50 = bucket_rows.get("secondary_50m")
        row_200 = bucket_rows.get("secondary_200m")
        coverage_50 = _optional_summary_float(
            row_50,
            "secondary_network_mean_coverage_ratio_mean",
        )
        coverage_200 = _optional_summary_float(
            row_200,
            "secondary_network_mean_coverage_ratio_mean",
        )
        comparison_rows.append(
            {
                "metric_scope": _markdown_cell(metric_scope),
                "seed": _markdown_cell(seed),
                "scenario": _markdown_cell(scenario),
                "comparison_role": _markdown_cell(comparison_role),
                "fov": _markdown_cell(_format_optional_number(fov)),
                "secondary_count": _markdown_cell(secondary_count),
                "backend": _markdown_cell(backend),
                "scale": _markdown_cell(scale),
                "coverage_50m": _format_optional_cell(coverage_50),
                "coverage_200m": _format_optional_cell(coverage_200),
                "coverage_delta": _format_delta_cell(coverage_200, coverage_50),
                "full_view_50m": _format_optional_cell(
                    _optional_summary_float(
                        row_50,
                        "secondary_network_joint_full_view_frame_rate_mean",
                    )
                ),
                "full_view_200m": _format_optional_cell(
                    _optional_summary_float(
                        row_200,
                        "secondary_network_joint_full_view_frame_rate_mean",
                    )
                ),
                "stable_50m": _format_optional_cell(
                    _optional_summary_int(row_50, "stable_cross_view_registration_count")
                ),
                "stable_200m": _format_optional_cell(
                    _optional_summary_int(row_200, "stable_cross_view_registration_count")
                ),
                "not_registered_50m": _format_optional_cell(
                    _optional_summary_int(row_50, "not_registered_count")
                ),
                "not_registered_200m": _format_optional_cell(
                    _optional_summary_int(row_200, "not_registered_count")
                ),
                "d7_reject_50m": _format_optional_cell(
                    _optional_summary_int(row_50, "d7_guidance_reject_count")
                ),
                "d7_reject_200m": _format_optional_cell(
                    _optional_summary_int(row_200, "d7_guidance_reject_count")
                ),
            }
        )
    return comparison_rows


def _coverage_funnel_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "metric_scope": _markdown_cell(row.get("metric_scope", "not_recorded")),
            "seed": _markdown_cell(row.get("seed", "not_recorded")),
            "scenario": _markdown_cell(row.get("scenario", "not_recorded")),
            "comparison_role": _markdown_cell(_summary_text(row, "comparison_roles")),
            "height_bucket": _markdown_cell(_summary_height_bucket(row)),
            "coverage": _float_or_zero(
                row.get("secondary_network_mean_coverage_ratio_mean")
            ),
            "visible_union": _float_or_zero(
                row.get("secondary_visible_target_union_ratio_mean")
            ),
            "joint_full_view": _float_or_zero(
                row.get("secondary_network_joint_full_view_frame_rate_mean")
            ),
            "single_full_view": _float_or_zero(
                row.get("secondary_single_camera_full_view_frame_rate_mean")
            ),
            "multi_target_fov": _float_or_zero(row.get("multi_target_fov_rate_mean")),
            "detect": int(
                row.get("secondary_detect_count")
                or row.get("funnel_detect_count", 0)
                or 0
            ),
            "projection": _float_or_zero(row.get("projection_valid_rate_mean")),
            "gate": _float_or_zero(row.get("geometry_gate_pass_rate_mean")),
            "stable": int(row.get("stable_cross_view_registration_count", 0) or 0),
            "not_registered": int(row.get("not_registered_count", 0) or 0),
            "trend_key": _markdown_cell(_summary_text(row, "trend_keys")),
        }
        for row in rows
    ]


def _baseline_enhanced_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    grouped: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        role = _summary_role(row)
        if role not in {"baseline", "enhanced"}:
            continue
        key = (
            row.get("metric_scope", "not_recorded"),
            row.get("seed", "not_recorded"),
            row.get("scenario", "not_recorded"),
            _summary_height_bucket(row),
            row.get("secondary_fov_degrees", "not_recorded"),
            row.get("secondary_count", "not_recorded"),
            row.get("detection_backend", "not_recorded"),
            _scale_text(row),
        )
        grouped.setdefault(key, {})[role] = row

    comparison_rows: list[dict[str, str]] = []
    for key, role_rows in sorted(grouped.items(), key=lambda item: tuple(str(v) for v in item[0])):
        metric_scope, seed, scenario, height_bucket, fov, secondary_count, backend, scale = key
        baseline = role_rows.get("baseline")
        enhanced = role_rows.get("enhanced")
        baseline_coverage = _optional_summary_float(
            baseline,
            "secondary_network_mean_coverage_ratio_mean",
        )
        enhanced_coverage = _optional_summary_float(
            enhanced,
            "secondary_network_mean_coverage_ratio_mean",
        )
        evidence_paths = sorted(
            {
                value
                for row in (baseline, enhanced)
                if row is not None
                for value in _summary_values(row, "evidence_paths")
            }
        )
        comparison_rows.append(
            {
                "metric_scope": _markdown_cell(metric_scope),
                "seed": _markdown_cell(seed),
                "scenario": _markdown_cell(scenario),
                "height_bucket": _markdown_cell(height_bucket),
                "fov": _markdown_cell(_format_optional_number(fov)),
                "secondary_count": _markdown_cell(secondary_count),
                "backend": _markdown_cell(backend),
                "scale": _markdown_cell(scale),
                "baseline_coverage": _format_optional_cell(baseline_coverage),
                "enhanced_coverage": _format_optional_cell(enhanced_coverage),
                "coverage_delta": _format_delta_cell(
                    enhanced_coverage,
                    baseline_coverage,
                ),
                "baseline_stable": _format_optional_cell(
                    _optional_summary_int(
                        baseline,
                        "stable_cross_view_registration_count",
                    )
                ),
                "enhanced_stable": _format_optional_cell(
                    _optional_summary_int(
                        enhanced,
                        "stable_cross_view_registration_count",
                    )
                ),
                "baseline_not_registered": _format_optional_cell(
                    _optional_summary_int(baseline, "not_registered_count")
                ),
                "enhanced_not_registered": _format_optional_cell(
                    _optional_summary_int(enhanced, "not_registered_count")
                ),
                "baseline_active_precision": _format_available_number(
                    _optional_summary_float(
                        baseline,
                        "active_degradation_precision_mean",
                    )
                ),
                "enhanced_active_precision": _format_available_number(
                    _optional_summary_float(
                        enhanced,
                        "active_degradation_precision_mean",
                    )
                ),
                "baseline_unnecessary": _format_optional_cell(
                    _optional_summary_int(baseline, "unnecessary_degradation_count")
                ),
                "enhanced_unnecessary": _format_optional_cell(
                    _optional_summary_int(enhanced, "unnecessary_degradation_count")
                ),
                "baseline_d7_reject": _format_optional_cell(
                    _optional_summary_int(baseline, "d7_guidance_reject_count")
                ),
                "enhanced_d7_reject": _format_optional_cell(
                    _optional_summary_int(enhanced, "d7_guidance_reject_count")
                ),
                "evidence_paths": _markdown_cell(", ".join(evidence_paths)),
            }
        )
    return comparison_rows


def _summary_role(row: Mapping[str, Any]) -> str:
    for value in _summary_values(row, "comparison_roles"):
        role = _normalize_comparison_role(value, allow_heuristic=True)
        if role != "not_recorded":
            return role
    return "not_recorded"


def _summary_height_bucket(row: Mapping[str, Any]) -> str:
    for value in _summary_values(row, "secondary_height_buckets"):
        text = _text(value)
        if text is not None:
            return text
    return _secondary_height_bucket(row.get("secondary_height_above_targets_m"))


def _summary_text(row: Mapping[str, Any], field_name: str) -> str:
    values = _summary_values(row, field_name)
    if not values:
        return "not_recorded"
    return ", ".join(values)


def _summary_values(row: Mapping[str, Any], field_name: str) -> list[str]:
    value = row.get(field_name)
    if isinstance(value, (list, tuple, set)):
        return sorted(
            {
                text
                for item in value
                for text in [_text(item)]
                if text is not None and text != "not_recorded"
            }
        )
    if isinstance(value, str):
        text = value.strip()
        if not text or text == "not_recorded":
            return []
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return [text]
            if isinstance(parsed, list):
                return sorted(str(item) for item in parsed if str(item).strip())
        return [text]
    text = _text(value)
    return [] if text is None or text == "not_recorded" else [text]


def _scale_text(row: Mapping[str, Any]) -> str:
    return (
        f"d={row.get('drone_count', 'not_recorded')}/"
        f"r={row.get('resource_count', 'not_recorded')}/"
        f"t={row.get('target_count', 'not_recorded')}/"
        f"c={row.get('camera_count', 'not_recorded')}"
    )


def _optional_summary_float(
    row: Mapping[str, Any] | None,
    field_name: str,
) -> float | None:
    if row is None:
        return None
    return _first_float(row.get(field_name))


def _optional_summary_int(
    row: Mapping[str, Any] | None,
    field_name: str,
) -> int | None:
    if row is None:
        return None
    return _first_int(row.get(field_name))


def _format_optional_cell(value: Any) -> str:
    if value is None:
        return "not_recorded"
    number = _first_float(value)
    if number is None:
        return _markdown_cell(value)
    return f"{number:.6g}"


def _format_delta_cell(lhs: float | None, rhs: float | None) -> str:
    if lhs is None or rhs is None:
        return "not_recorded"
    return f"{(lhs - rhs):.6g}"


def _cross_seed_sort_key(
    item: tuple[tuple[Any, ...], dict[Any, list[dict[str, Any]]]],
) -> tuple[str, ...]:
    return tuple(str(value) for value in item[0])


def _paired_group_sort_key(
    item: tuple[
        tuple[Any, ...],
        dict[str, dict[int, list[dict[str, Any]]]],
    ],
) -> tuple[str, ...]:
    return tuple(str(value) for value in item[0])


def _aggregate_metric_value(
    records: Sequence[Mapping[str, Any]],
    metric: str,
) -> float | None:
    if metric == "active_degradation_precision":
        weighted_sum = 0.0
        label_count = 0
        for record in records:
            precision = _finite_float(record.get(metric))
            count = _first_int(record.get("active_degradation_label_count")) or 0
            if precision is None or count <= 0:
                continue
            weighted_sum += precision * count
            label_count += count
        return weighted_sum / label_count if label_count else None

    values = [
        value
        for record in records
        for value in [_finite_float(record.get(metric))]
        if value is not None
    ]
    if not values:
        return None
    if metric in COUNT_METRICS:
        return float(sum(values))
    return statistics.fmean(values)


def _intercept_opportunity_count(
    seed_records: Mapping[Any, Sequence[Mapping[str, Any]]],
    metric: str,
) -> int | None:
    if metric not in INTERCEPT_OUTCOME_COUNT_METRICS:
        return None
    opportunity_count = 0
    for records in seed_records.values():
        for record in records:
            if _finite_float(record.get(metric)) is None:
                continue
            target_count = _first_int(record.get("target_count"))
            if target_count is not None and target_count > 0:
                opportunity_count += target_count
    return opportunity_count or None


def _finite_float(value: Any) -> float | None:
    number = _first_float(value)
    if number is None or not math.isfinite(number):
        return None
    return number


def _sample_std(values: Sequence[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return statistics.stdev(values)


def _bootstrap_mean_ci(
    values: Sequence[float],
    *,
    resamples: int,
    rng_seed: int,
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    rng = random.Random(rng_seed)
    sample_count = len(values)
    bootstrap_means = sorted(
        statistics.fmean(values[rng.randrange(sample_count)] for _ in range(sample_count))
        for _ in range(resamples)
    )
    return (
        _percentile(bootstrap_means, 0.025),
        _percentile(bootstrap_means, 0.975),
    )


def _percentile(sorted_values: Sequence[float], quantile: float) -> float:
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(sorted_values[lower])
    fraction = position - lower
    return float(
        sorted_values[lower]
        + (sorted_values[upper] - sorted_values[lower]) * fraction
    )


def _write_rows_csv(
    rows: Iterable[Mapping[str, Any]],
    path: str | Path,
    fieldnames: Sequence[str],
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row, fieldnames))
    return path


def _aggregate_geometry_text(row: Mapping[str, Any]) -> str:
    return (
        f"h={_format_optional_number(row.get('secondary_height_above_targets_m'))},"
        f"fov={_format_optional_number(row.get('secondary_fov_degrees'))},"
        f"sec={row.get('secondary_count', 'not_recorded')},"
        f"backend={row.get('detection_backend', 'not_recorded')}"
    )


def _format_available_number(value: Any) -> str:
    number = _finite_float(value)
    return "unavailable" if number is None else f"{number:.6g}"


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


def _markdown_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|")
    return text or "not_recorded"


def _format_optional_number(value: Any) -> str:
    number = _first_float(value)
    if number is None:
        return "not_recorded"
    return f"{number:.6g}"


def _float_or_zero(value: Any) -> float:
    number = _first_float(value)
    return 0.0 if number is None else number
