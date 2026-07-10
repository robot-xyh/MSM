"""Report generation for offline D6 batch evaluation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .metrics import EpisodeMetrics
from .standard_mapping import (
    STANDARD_MAPPING_CSV_FIELDNAMES,
    STANDARD_MAPPING_VERSION,
    standard_mapping_csv_rows,
    standard_mapping_family_rows,
)


class ReportGenerator:
    """Generate CSV tables, Markdown summaries, and charts."""

    CATEGORIES = {
        "detection": [
            "detection_probability",
            "false_alarm_rate",
            "missed_detection_rate",
        ],
        "tracking": [
            "track_rmse",
            "track_continuity",
            "id_switch_count",
        ],
        "assignment": [
            "duplicate_assignment_count",
            "unassigned_high_threat_count",
        ],
        "degradation": [
            "failover_time",
            "consensus_rounds",
            "degraded_completion_rate",
            "active_degradation_count",
            "active_degradation_precision",
            "active_degradation_label_count",
            "unnecessary_active_degradation_count",
            "passive_failover_count",
            "secondary_node_takeover_count",
            "secondary_reassignment_count",
            "d4_reassign_pending_count",
            "distributed_fallback_count",
            "failover_active_window_delta_s",
        ],
        "terminal": [
            "terminal_association_accuracy",
            "terminal_id_switch_count",
            "ambiguous_fov_event_count",
            "friend_overlap_hold_count",
            "time_to_terminal_lock",
            "terminal_lock_count",
            "multi_view_consensus_rate",
            "cross_view_conflict_count",
            "duplicate_terminal_lock_count",
        ],
        "secondary_sensing": [
            "secondary_network_joint_full_view_frame_rate",
            "secondary_network_mean_coverage_ratio",
            "secondary_single_camera_full_view_frame_rate",
            "cross_view_association_count",
            "secondary_detect_available_but_not_registered_count",
            "cue_pointing_error_mean_deg",
            "cue_pointing_error_rmse_deg",
            "gimbal_pointing_error_mean_deg",
            "gimbal_pointing_error_rmse_deg",
        ],
        "communication": [
            "cross_node_latency_ms",
            "message_drop_rate",
            "out_of_order_count",
            "stale_track_update_count",
            "video_metadata_delivery_rate",
            "bbox_delivery_rate",
            "consensus_latency_s",
        ],
        "guidance": [
            "camera_quality_gate_pass_rate",
            "los_quality_gate_pass_rate",
            "maneuver_margin_gate_pass_rate",
            "terminal_switch_allowed_rate",
            "visual_png_switch_count",
            "terminal_takeover_rate",
            "terminal_switch_reject_count",
            "mode_switch_count",
            "terminal_contract_reject_count",
            "intercept_success_count",
            "collision_intercept_count",
            "range_intercept_count",
            "time_to_intercept_s",
            "min_range_m",
            "gate_reject_count",
        ],
        "safety": [
            "constraint_violation_count",
            "human_override_count",
        ],
        "performance": [
            "module_duration_ms",
            "loop_latency_ms",
            "record_latency_ms",
            "cpu_budget_utilization",
            "gpu_budget_utilization",
            "performance_budget_violation_count",
        ],
    }

    def summarize(self, episodes: Iterable[EpisodeMetrics]) -> list[dict[str, Any]]:
        episode_list = list(episodes)
        rows: list[dict[str, Any]] = []
        for metric_name in EpisodeMetrics.metric_names():
            values = np.array(
                _available_metric_values(episode_list, metric_name),
                dtype=float,
            )
            if values.size == 0:
                rows.append(_empty_summary_row(metric_name))
                continue

            mean = float(np.mean(values))
            std = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
            stderr = std / float(np.sqrt(values.size)) if values.size > 1 else 0.0
            ci_delta = 1.96 * stderr
            rows.append(
                {
                    "metric": metric_name,
                    "count": int(values.size),
                    "mean": mean,
                    "std": std,
                    "stderr": stderr,
                    "ci95_low": mean - ci_delta,
                    "ci95_high": mean + ci_delta,
                    "median": float(np.median(values)),
                    "p05": float(np.percentile(values, 5)),
                    "p95": float(np.percentile(values, 95)),
                }
            )
        return rows

    def write_episode_csv(
        self,
        episodes: Iterable[EpisodeMetrics],
        path: str | Path,
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for episode in episodes:
            row = episode.to_dict()
            row["metadata"] = json.dumps(
                row.get("metadata", {}),
                ensure_ascii=False,
                sort_keys=True,
            )
            rows.append(row)
        fieldnames = [
            "episode_id",
            "seed",
            "batch_seed",
            "scenario_group",
            "metric_scope",
            *EpisodeMetrics.scale_names(),
            "duration",
            "mission_outcome",
            "success_reason",
            "failure_reason",
            "eval_priority",
            "implementation_status",
            "evidence_path",
            "scenario_version",
            "standard_mapping_version",
            "standard_metric_family_summary",
        ] + EpisodeMetrics.metric_names() + ["metadata"]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_standard_mapping_csv(
        self,
        path: str | Path,
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=STANDARD_MAPPING_CSV_FIELDNAMES,
            )
            writer.writeheader()
            writer.writerows(standard_mapping_csv_rows())
        return path

    def write_summary_csv(
        self,
        episodes: Iterable[EpisodeMetrics],
        path: str | Path,
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        episode_list = list(episodes)
        rows = _scoped_summary_rows(
            "all",
            "all",
            "all",
            "all",
            _scale_scope_values(episode_list),
            self.summarize(episode_list),
        )
        for metric_scope, seed, scenario_group, scoped_episodes in (
            _metric_scope_seed_scenario_scale_rows(episode_list)
        ):
            rows.extend(
                _scoped_summary_rows(
                    metric_scope,
                    seed,
                    scenario_group,
                    _batch_seed_range_text(scoped_episodes),
                    _scale_scope_values(scoped_episodes),
                    self.summarize(scoped_episodes),
                )
            )
        fieldnames = [
            "metric_scope",
            "seed",
            "scenario_group",
            "batch_seed",
            *EpisodeMetrics.scale_names(),
            "metric",
            "count",
            "mean",
            "std",
            "stderr",
            "ci95_low",
            "ci95_high",
            "median",
            "p05",
            "p95",
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_markdown_report(
        self,
        episodes: Iterable[EpisodeMetrics],
        path: str | Path,
        title: str = "D6 离线评估报告",
    ) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        episode_list = list(episodes)
        summary_rows = self.summarize(episode_list)
        scenario_rows = _metric_scope_seed_scenario_scale_rows(episode_list)
        secondary_sensing_rows = _secondary_sensing_comparison_rows(episode_list)
        reject_reason_rows = _reject_reason_rows(episode_list)
        mission_rows = _mission_outcome_rows(episode_list)
        performance_rows = _performance_monitoring_rows(episode_list)
        eval_rows = _eval_tracking_rows(episode_list)

        lines = [
            f"# {title}",
            "",
            "本报告由离线记录或合成日志生成。",
            "它不提供实时决策、火控参数、毁伤逻辑、自动处置动作或绕过人工授权的流程。",
            "",
            f"- Episode 数量: {len(episode_list)}",
            f"- 随机种子范围: {_seed_range_text(episode_list)}",
            f"- 场景分组: {', '.join(_ordered_scenario_groups(episode_list)) or 'not recorded'}",
            f"- Metrics scope: {_metric_scope_range_text(episode_list)}",
            f"- Drone count: {_scale_range_text(episode_list, 'drone_count')}",
            f"- Resource count: {_scale_range_text(episode_list, 'resource_count')}",
            f"- Target count: {_scale_range_text(episode_list, 'target_count')}",
            f"- Camera count: {_scale_range_text(episode_list, 'camera_count')}",
            f"- Mission outcome: {_mission_outcome_range_text(episode_list)}",
            f"- EVAL priority: {_eval_priority_range_text(episode_list)}",
            f"- Scenario version: {_scenario_version_range_text(episode_list)}",
            f"- Standard mapping version: {_standard_mapping_version_range_text(episode_list)}",
            "",
            "## Mission Outcome / Root Cause",
            "",
            "| Episode | Outcome | Success reason | Failure reason | Root cause | Top failure causes |",
            "|---|---|---|---|---|---|",
        ]
        for row in mission_rows:
            lines.append(
                "| {episode_id} | {mission_outcome} | {success_reason} | {failure_reason} | {root_cause} | {top_failure_causes} |".format(
                    **row
                )
            )

        lines.extend(
            [
                "",
                "## Performance Monitoring",
                "",
                "| Episode | Module duration ms | Loop latency ms | Record latency ms | CPU budget util | GPU budget util | Budget violations |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in performance_rows:
            lines.append(
                "| {episode_id} | {module_duration_ms:.6g} | {loop_latency_ms:.6g} | {record_latency_ms:.6g} | {cpu_budget_utilization:.6g} | {gpu_budget_utilization:.6g} | {performance_budget_violation_count:.6g} |".format(
                    **row
                )
            )

        lines.extend(
            [
                "",
                "## EVAL Tracking",
                "",
                "| Episode | Priority | Implementation status | Evidence path |",
                "|---|---|---|---|",
            ]
        )
        for row in eval_rows:
            lines.append(
                "| {episode_id} | {eval_priority} | {implementation_status} | {evidence_path} |".format(
                    **row
                )
            )

        lines.extend(
            [
                "",
                "## Standard C-UAS Mapping",
                "",
                f"- Mapping version: {_standard_mapping_version_range_text(episode_list)}",
                f"- Scenario version: {_scenario_version_range_text(episode_list)}",
                "",
                "| Engineering metric | Standard metric family | Standard sources | Implementation status | Evidence requirement |",
                "|---|---|---|---|---|",
            ]
        )
        for row in _standard_mapping_report_rows():
            lines.append(
                "| {engineering_metric} | {standard_metric_family} | {standard_sources} | {implementation_status} | {evidence_requirement} |".format(
                    **row
                )
            )

        lines.extend(
            [
                "",
                "## 1. 汇总表",
                "",
                "| 指标 | 均值 | 标准差 | 95% CI 下界 | 95% CI 上界 | 中位数 | P05 | P95 |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in summary_rows:
            lines.append(
                "| {metric} | {mean} | {std} | {ci95_low} | "
                "{ci95_high} | {median} | {p05} | {p95} |".format(
                    metric=row["metric"],
                    mean=_format_optional_metric(row.get("mean")),
                    std=_format_optional_metric(row.get("std")),
                    ci95_low=_format_optional_metric(row.get("ci95_low")),
                    ci95_high=_format_optional_metric(row.get("ci95_high")),
                    median=_format_optional_metric(row.get("median")),
                    p05=_format_optional_metric(row.get("p05")),
                    p95=_format_optional_metric(row.get("p95")),
                )
            )

        if scenario_rows:
            lines.extend(
                [
                    "",
                    "## 2. 口径/种子/场景分组",
                    "",
                    "| Metrics scope | Seed | 场景 | Drone count | Resource count | Target count | Camera count | Episode 数量 | Batch seed | active_degradation_count | active_degradation_precision | active_degradation_label_count | unnecessary_active_degradation_count | passive_failover_count | mode_switch_count | terminal_contract_reject_count |",
                    "|---|---|---|---|---|---|---|---:|---|---:|---|---:|---:|---:|---:|---:|",
                ]
            )
            for metric_scope, seed, scenario_group, scoped_episodes in scenario_rows:
                lines.append(
                    "| {metric_scope} | {seed} | {scenario_group} | {drone_count} | {resource_count} | {target_count} | {camera_count} | {count} | {batch_seed} | {active:.6g} | {active_precision} | {label_count:.6g} | {unnecessary:.6g} | {passive:.6g} | {mode_switch:.6g} | {contract_reject:.6g} |".format(
                        metric_scope=metric_scope,
                        seed=seed,
                        scenario_group=scenario_group,
                        drone_count=_scale_range_text(scoped_episodes, "drone_count"),
                        resource_count=_scale_range_text(scoped_episodes, "resource_count"),
                        target_count=_scale_range_text(scoped_episodes, "target_count"),
                        camera_count=_scale_range_text(scoped_episodes, "camera_count"),
                        count=len(scoped_episodes),
                        batch_seed=_batch_seed_range_text(scoped_episodes),
                        active=_mean_metric(scoped_episodes, "active_degradation_count"),
                        active_precision=_format_optional_metric(
                            _mean_metric(
                                scoped_episodes,
                                "active_degradation_precision",
                            )
                        ),
                        label_count=_mean_metric(
                            scoped_episodes,
                            "active_degradation_label_count",
                        )
                        or 0.0,
                        unnecessary=_mean_metric(
                            scoped_episodes,
                            "unnecessary_active_degradation_count",
                        ),
                        passive=_mean_metric(scoped_episodes, "passive_failover_count"),
                        mode_switch=_mean_metric(scoped_episodes, "mode_switch_count"),
                        contract_reject=_mean_metric(
                            scoped_episodes,
                            "terminal_contract_reject_count",
                        ),
                    )
                )

        section_number = 3 if scenario_rows else 2
        if secondary_sensing_rows:
            lines.extend(
                [
                    "",
                    f"## {section_number}. 二级视角节点对比",
                    "",
                    "该表仅消费 main/D4/D5 已写盘日志，比较固定俯视二级节点与机动高空侦察云台节点；D6 不参与控制、cue 下发或云台指向。",
                    "",
                    "| Metrics scope | Seed | 场景 | Node type | Drone count | Resource count | Target count | Camera count | Joint full-view rate | Mean coverage ratio | Single-camera full-view rate | Mean cross-view assoc count | Mean detect-not-registered count | Cue error mean deg | Gimbal error mean deg |",
                    "|---|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for row in secondary_sensing_rows:
                lines.append(
                    "| {metric_scope} | {seed} | {scenario_group} | {node_type} | {drone_count} | {resource_count} | {target_count} | {camera_count} | {joint_full_view_rate:.6g} | {mean_coverage_ratio:.6g} | {single_camera_full_view_rate:.6g} | {cross_view_association_count:.6g} | {detect_not_registered_count:.6g} | {cue_error_mean_deg:.6g} | {gimbal_error_mean_deg:.6g} |".format(
                        **row
                    )
                )
            section_number += 1

        if reject_reason_rows:
            lines.extend(
                [
                    "",
                    f"## {section_number}. Reject reason 分布",
                    "",
                    "| Metrics scope | Seed | 场景 | Drone count | Resource count | Target count | Camera count | 分布 | Reason | Count |",
                    "|---|---|---|---|---|---|---|---|---|---:|",
                ]
            )
            for row in reject_reason_rows:
                lines.append(
                    "| {metric_scope} | {seed} | {scenario_group} | {drone_count} | {resource_count} | {target_count} | {camera_count} | {distribution} | {reason} | {count} |".format(
                        **row
                    )
                )
            section_number += 1

        plot_section_number = section_number
        explanation_section_number = section_number + 1
        lines.extend(
            [
                "",
                f"## {plot_section_number}. 图表与曲线",
                "",
                "![探测指标图](plots/detection_metrics.png)",
                "",
                "![跟踪指标图](plots/tracking_metrics.png)",
                "",
                "![分配指标图](plots/assignment_metrics.png)",
                "",
                "![降级指标图](plots/degradation_metrics.png)",
                "",
                "![末端指标图](plots/terminal_metrics.png)",
                "",
                "![二级视角指标图](plots/secondary_sensing_metrics.png)",
                "",
                "![通信指标图](plots/communication_metrics.png)",
                "",
                "![导引门控指标图](plots/guidance_metrics.png)",
                "",
                "![安全指标图](plots/safety_metrics.png)",
                "",
                "![性能指标图](plots/performance_metrics.png)",
                "",
                "![关键指标分布图](plots/selected_metric_distributions.png)",
                "",
                f"## {explanation_section_number}. 解读说明",
                "",
                "- 探测、跟踪、分配、降级、末端配准、通信、导引门控和安全指标分开报告，避免单一命中率掩盖问题。",
                "- 计数类指标应与比例类指标一起检查，少量但严重的安全事件可能被总体成功率掩盖。",
                "- 偏态或长尾指标在形成正式结论前，应使用 bootstrap 或非参数方法复核。",
                "",
            ]
        )

        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def write_plots(
        self,
        episodes: Iterable[EpisodeMetrics],
        output_dir: str | Path,
    ) -> list[Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        episode_list = list(episodes)
        if not episode_list:
            return []

        written: list[Path] = []
        for category, metrics in self.CATEGORIES.items():
            path = output_dir / f"{category}_metrics.png"
            self._write_category_plot(episode_list, category, metrics, path)
            written.append(path)

        path = output_dir / "selected_metric_distributions.png"
        self._write_distribution_plot(
            episode_list,
            [
                "detection_probability",
                "track_rmse",
                "track_continuity",
                "terminal_association_accuracy",
                "constraint_violation_count",
            ],
            path,
        )
        written.append(path)
        return written

    def _write_category_plot(
        self,
        episodes: list[EpisodeMetrics],
        category: str,
        metric_names: list[str],
        path: Path,
    ) -> None:
        means = []
        errors = []
        for metric_name in metric_names:
            values = np.array(
                _available_metric_values(episodes, metric_name),
                dtype=float,
            )
            if values.size == 0:
                means.append(float("nan"))
                errors.append(0.0)
                continue
            means.append(float(np.mean(values)))
            if values.size > 1:
                errors.append(float(1.96 * np.std(values, ddof=1) / np.sqrt(values.size)))
            else:
                errors.append(0.0)

        fig, ax = plt.subplots(figsize=(max(7.0, len(metric_names) * 1.3), 4.5))
        positions = np.arange(len(metric_names))
        ax.bar(positions, means, yerr=errors, capsize=4, color="#4C78A8")
        ax.set_title(f"{category.title()} Metrics")
        ax.set_ylabel("Mean value")
        ax.set_xticks(positions)
        ax.set_xticklabels(metric_names, rotation=30, ha="right")
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)

    def _write_distribution_plot(
        self,
        episodes: list[EpisodeMetrics],
        metric_names: list[str],
        path: Path,
    ) -> None:
        fig, axes = plt.subplots(len(metric_names), 1, figsize=(8, 2.2 * len(metric_names)))
        if len(metric_names) == 1:
            axes = [axes]

        for ax, metric_name in zip(axes, metric_names):
            values = np.array(
                _available_metric_values(episodes, metric_name),
                dtype=float,
            )
            if values.size == 0:
                ax.text(0.5, 0.5, "unavailable", ha="center", va="center")
                ax.set_title(metric_name)
                ax.set_axis_off()
                continue
            ax.hist(values, bins=min(16, max(4, int(np.sqrt(values.size)))), color="#59A14F", alpha=0.85)
            ax.set_title(metric_name)
            ax.grid(axis="y", alpha=0.25)

        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)


def _empty_summary_row(metric_name: str) -> dict[str, Any]:
    return {
        "metric": metric_name,
        "count": 0,
        "mean": None,
        "std": None,
        "stderr": None,
        "ci95_low": None,
        "ci95_high": None,
        "median": None,
        "p05": None,
        "p95": None,
    }


def _scoped_summary_rows(
    metric_scope: str,
    seed: str,
    scenario_group: str,
    batch_seed: str,
    scale_values: dict[str, str],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "metric_scope": metric_scope,
            "seed": seed,
            "scenario_group": scenario_group,
            "batch_seed": batch_seed,
            **scale_values,
            **row,
        }
        for row in rows
    ]


def _metric_scope_seed_scenario_scale_rows(
    episodes: list[EpisodeMetrics],
) -> list[tuple[str, str, str, list[EpisodeMetrics]]]:
    grouped: dict[tuple[str, int, str, tuple[int, ...]], list[EpisodeMetrics]] = {}
    for episode in episodes:
        scale_key = tuple(
            _episode_scale_value(episode, scale_name)
            for scale_name in EpisodeMetrics.scale_names()
        )
        key = (
            _episode_metric_scope_value(episode),
            _episode_seed_sort_value(episode),
            episode.scenario_group,
            scale_key,
        )
        grouped.setdefault(key, []).append(episode)

    rows: list[tuple[str, str, str, list[EpisodeMetrics]]] = []
    for key, scoped in sorted(grouped.items(), key=_grouped_row_sort_key):
        metric_scope, _, scenario_group, _ = key
        rows.append((metric_scope, _seed_range_text(scoped), scenario_group, scoped))
    return rows


def _grouped_row_sort_key(
    item: tuple[tuple[str, int, str, tuple[int, ...]], list[EpisodeMetrics]],
) -> tuple[tuple[int, str], int, tuple[int, str], tuple[int, ...]]:
    key, _ = item
    metric_scope, seed, scenario_group, scale_key = key
    return (
        _metric_scope_sort_key(metric_scope),
        seed,
        _scenario_group_sort_key(scenario_group),
        scale_key,
    )


def _metric_scope_sort_key(metric_scope: str) -> tuple[int, str]:
    preferred = {"execution": 0, "contract": 1, "not_recorded": 2}
    return (preferred.get(metric_scope, 100), metric_scope)


def _scenario_group_sort_key(scenario_group: str) -> tuple[int, str]:
    preferred_order = [
        "normal",
        "secondary_200m",
        "distributed",
        "terminal_handoff_tuned",
        "multi_view_inconsistent",
    ]
    if scenario_group in preferred_order:
        return (preferred_order.index(scenario_group), scenario_group)
    return (len(preferred_order), scenario_group)


def _ordered_scenario_groups(episodes: list[EpisodeMetrics]) -> list[str]:
    preferred_order = [
        "normal",
        "secondary_200m",
        "distributed",
        "terminal_handoff_tuned",
        "multi_view_inconsistent",
    ]
    present = {episode.scenario_group for episode in episodes if episode.scenario_group}
    ordered = [group for group in preferred_order if group in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def _metric_scope_range_text(episodes: list[EpisodeMetrics]) -> str:
    scopes = sorted(
        {_episode_metric_scope_value(episode) for episode in episodes},
        key=_metric_scope_sort_key,
    )
    scopes = [scope for scope in scopes if scope and scope != "not_recorded"]
    if not scopes:
        return "not recorded"
    return ", ".join(scopes)


def _mission_outcome_range_text(episodes: list[EpisodeMetrics]) -> str:
    outcomes = sorted({str(episode.mission_outcome or "failed") for episode in episodes})
    return ", ".join(outcomes) if outcomes else "not recorded"


def _eval_priority_range_text(episodes: list[EpisodeMetrics]) -> str:
    priorities = sorted({str(episode.eval_priority or "not_recorded") for episode in episodes})
    return ", ".join(priorities) if priorities else "not recorded"


def _scenario_version_range_text(episodes: list[EpisodeMetrics]) -> str:
    versions = sorted(
        {
            str(episode.scenario_version)
            for episode in episodes
            if episode.scenario_version
        }
    )
    return ", ".join(versions) if versions else "not recorded"


def _standard_mapping_version_range_text(episodes: list[EpisodeMetrics]) -> str:
    versions = sorted(
        {
            str(episode.standard_mapping_version or STANDARD_MAPPING_VERSION)
            for episode in episodes
        }
    )
    return ", ".join(versions) if versions else STANDARD_MAPPING_VERSION


def _mission_outcome_rows(episodes: list[EpisodeMetrics]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for episode in episodes:
        metadata = episode.metadata or {}
        root_cause = str(metadata.get("root_cause") or "none")
        top_failure_causes = _top_failure_causes_text(
            metadata.get("top_failure_causes"),
        )
        rows.append(
            {
                "episode_id": _markdown_cell(episode.episode_id),
                "mission_outcome": _markdown_cell(episode.mission_outcome),
                "success_reason": _markdown_cell(episode.success_reason or "not recorded"),
                "failure_reason": _markdown_cell(episode.failure_reason or "not recorded"),
                "root_cause": _markdown_cell(root_cause),
                "top_failure_causes": _markdown_cell(top_failure_causes),
            }
        )
    return rows


def _top_failure_causes_text(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "none"
    parts = []
    for item in value[:3]:
        if isinstance(item, Mapping):
            cause = str(item.get("cause") or "unknown")
            score = item.get("score")
            if score is None:
                parts.append(cause)
            else:
                parts.append(f"{cause}({float(score):.3g})")
        else:
            parts.append(str(item))
    return ", ".join(parts) if parts else "none"


def _performance_monitoring_rows(
    episodes: list[EpisodeMetrics],
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for episode in episodes:
        rows.append(
            {
                "episode_id": _markdown_cell(episode.episode_id),
                "module_duration_ms": float(episode.module_duration_ms),
                "loop_latency_ms": float(episode.loop_latency_ms),
                "record_latency_ms": float(episode.record_latency_ms),
                "cpu_budget_utilization": float(episode.cpu_budget_utilization),
                "gpu_budget_utilization": float(episode.gpu_budget_utilization),
                "performance_budget_violation_count": float(
                    episode.performance_budget_violation_count
                ),
            }
        )
    return rows


def _eval_tracking_rows(episodes: list[EpisodeMetrics]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for episode in episodes:
        rows.append(
            {
                "episode_id": _markdown_cell(episode.episode_id),
                "eval_priority": _markdown_cell(episode.eval_priority or "not recorded"),
                "implementation_status": _markdown_cell(
                    episode.implementation_status or "not recorded"
                ),
                "evidence_path": _markdown_cell(episode.evidence_path or "not recorded"),
            }
        )
    return rows


def _standard_mapping_report_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in standard_mapping_family_rows():
        rows.append(
            {
                "engineering_metric": _markdown_cell(row["engineering_metric"]),
                "standard_metric_family": _markdown_cell(
                    row["standard_metric_family"]
                ),
                "standard_sources": _markdown_cell(row["standard_sources"]),
                "implementation_status": _markdown_cell(
                    row["implementation_status"]
                ),
                "evidence_requirement": _markdown_cell(
                    row["evidence_requirement"]
                ),
            }
        )
    return rows


def _markdown_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|")
    return text or "not recorded"


def _scale_scope_values(episodes: list[EpisodeMetrics]) -> dict[str, str]:
    return {
        scale_name: _scale_range_text(episodes, scale_name)
        for scale_name in EpisodeMetrics.scale_names()
    }


def _scale_range_text(episodes: list[EpisodeMetrics], scale_name: str) -> str:
    values = sorted(
        {
            value
            for value in (
                _episode_scale_value(episode, scale_name)
                for episode in episodes
            )
            if value > 0
        }
    )
    if not values:
        return "not recorded"
    if len(values) == 1:
        return str(values[0])
    return f"{values[0]}..{values[-1]}"


def _episode_metric_scope_value(episode: EpisodeMetrics) -> str:
    scope = getattr(episode, "metric_scope", None)
    text = str(scope or "").strip().lower()
    return text or "not_recorded"


def _episode_seed_sort_value(episode: EpisodeMetrics) -> int:
    if episode.seed is None:
        return -1
    return int(episode.seed)


def _episode_scale_value(episode: EpisodeMetrics, scale_name: str) -> int:
    value = getattr(episode, scale_name, 0)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _seed_range_text(episodes: list[EpisodeMetrics]) -> str:
    seeds = sorted(episode.seed for episode in episodes if episode.seed is not None)
    if not seeds:
        return "not recorded"
    if len(seeds) == 1:
        return str(seeds[0])
    return f"{seeds[0]}..{seeds[-1]}"


def _batch_seed_range_text(episodes: list[EpisodeMetrics]) -> str:
    seeds = sorted(episode.batch_seed for episode in episodes if episode.batch_seed is not None)
    if not seeds:
        return "not recorded"
    if len(seeds) == 1:
        return str(seeds[0])
    return f"{seeds[0]}..{seeds[-1]}"


def _available_metric_values(
    episodes: list[EpisodeMetrics],
    metric_name: str,
) -> list[float]:
    return [
        float(value)
        for episode in episodes
        for value in [getattr(episode, metric_name)]
        if value is not None
    ]


def _mean_metric(
    episodes: list[EpisodeMetrics],
    metric_name: str,
) -> float | None:
    values = _available_metric_values(episodes, metric_name)
    if not values:
        return None
    return float(np.mean(values))


def _format_optional_metric(value: Any) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.6g}"


def _secondary_sensing_comparison_rows(
    episodes: list[EpisodeMetrics],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric_scope, seed, scenario_group, scoped_episodes in (
        _metric_scope_seed_scenario_scale_rows(episodes)
    ):
        if not _has_secondary_sensing_data(scoped_episodes):
            continue

        common = {
            "metric_scope": metric_scope,
            "seed": seed,
            "scenario_group": scenario_group,
            "drone_count": _scale_range_text(scoped_episodes, "drone_count"),
            "resource_count": _scale_range_text(scoped_episodes, "resource_count"),
            "target_count": _scale_range_text(scoped_episodes, "target_count"),
            "camera_count": _scale_range_text(scoped_episodes, "camera_count"),
        }
        rows.append(
            {
                **common,
                "node_type": "all_secondary_network",
                "joint_full_view_rate": _mean_metric(
                    scoped_episodes,
                    "secondary_network_joint_full_view_frame_rate",
                ),
                "mean_coverage_ratio": _mean_metric(
                    scoped_episodes,
                    "secondary_network_mean_coverage_ratio",
                ),
                "single_camera_full_view_rate": _mean_metric(
                    scoped_episodes,
                    "secondary_single_camera_full_view_frame_rate",
                ),
                "cross_view_association_count": _mean_metric(
                    scoped_episodes,
                    "cross_view_association_count",
                ),
                "detect_not_registered_count": _mean_metric(
                    scoped_episodes,
                    "secondary_detect_available_but_not_registered_count",
                ),
                "cue_error_mean_deg": _mean_metric(
                    scoped_episodes,
                    "cue_pointing_error_mean_deg",
                ),
                "gimbal_error_mean_deg": _mean_metric(
                    scoped_episodes,
                    "gimbal_pointing_error_mean_deg",
                ),
            }
        )

        node_types = _secondary_node_types_for_group(scoped_episodes)
        for node_type in node_types:
            rows.append(
                {
                    **common,
                    "node_type": node_type,
                    "joint_full_view_rate": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "secondary_network_joint_full_view_frame_rate",
                    ),
                    "mean_coverage_ratio": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "secondary_network_mean_coverage_ratio",
                    ),
                    "single_camera_full_view_rate": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "secondary_single_camera_full_view_frame_rate",
                    ),
                    "cross_view_association_count": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "cross_view_association_count",
                    ),
                    "detect_not_registered_count": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "secondary_detect_available_but_not_registered_count",
                    ),
                    "cue_error_mean_deg": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "cue_pointing_error_mean_deg",
                    ),
                    "gimbal_error_mean_deg": _mean_secondary_node_metric(
                        scoped_episodes,
                        node_type,
                        "gimbal_pointing_error_mean_deg",
                    ),
                }
            )
    return rows


def _has_secondary_sensing_data(episodes: list[EpisodeMetrics]) -> bool:
    metric_names = (
        "secondary_network_joint_full_view_frame_rate",
        "secondary_network_mean_coverage_ratio",
        "secondary_single_camera_full_view_frame_rate",
        "cross_view_association_count",
        "secondary_detect_available_but_not_registered_count",
        "cue_pointing_error_count",
        "gimbal_pointing_error_count",
    )
    if any(any(float(getattr(episode, name)) for name in metric_names) for episode in episodes):
        return True
    return any(_secondary_node_metrics(episode) for episode in episodes)


def _secondary_node_types_for_group(episodes: list[EpisodeMetrics]) -> list[str]:
    present = {
        node_type
        for episode in episodes
        for node_type in _secondary_node_metrics(episode)
    }
    if present:
        present.update({"fixed_downlook_secondary", "mobile_recon_gimbal"})
    preferred = [
        "fixed_downlook_secondary",
        "mobile_recon_gimbal",
        "secondary_network",
    ]
    ordered = [node_type for node_type in preferred if node_type in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def _mean_secondary_node_metric(
    episodes: list[EpisodeMetrics],
    node_type: str,
    metric_name: str,
) -> float:
    values = [
        float(metrics.get(metric_name, 0.0))
        for episode in episodes
        for metrics in [_secondary_node_metrics(episode).get(node_type, {})]
    ]
    return float(np.mean(values)) if values else 0.0


def _secondary_node_metrics(episode: EpisodeMetrics) -> dict[str, Mapping[str, Any]]:
    metadata = episode.metadata or {}
    raw = metadata.get("secondary_sensing_node_type_metrics")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(node_type): metrics
        for node_type, metrics in raw.items()
        if isinstance(metrics, Mapping)
    }


def _reject_reason_rows(episodes: list[EpisodeMetrics]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric_scope, seed, scenario_group, scoped_episodes in (
        _metric_scope_seed_scenario_scale_rows(episodes)
    ):
        distributions = _reject_reason_distributions(scoped_episodes)
        for distribution, reason, count in distributions:
            rows.append(
                {
                    "metric_scope": metric_scope,
                    "seed": seed,
                    "scenario_group": scenario_group,
                    "drone_count": _scale_range_text(scoped_episodes, "drone_count"),
                    "resource_count": _scale_range_text(
                        scoped_episodes,
                        "resource_count",
                    ),
                    "target_count": _scale_range_text(scoped_episodes, "target_count"),
                    "camera_count": _scale_range_text(scoped_episodes, "camera_count"),
                    "distribution": distribution,
                    "reason": reason,
                    "count": count,
                }
            )
    return rows


def _reject_reason_distributions(
    episodes: list[EpisodeMetrics],
) -> list[tuple[str, str, int]]:
    counts: dict[tuple[str, str], int] = {}
    metadata_keys = {
        "terminal_switch_reject_reasons": "terminal_switch_reject_reasons",
        "terminal_switch_reject_reason_pair_counts": (
            "terminal_switch_reject_reason_pair_counts"
        ),
        "terminal_contract_reject_reasons": "terminal_contract_reject_reasons",
    }
    for episode in episodes:
        metadata = episode.metadata or {}
        for metadata_key, label in metadata_keys.items():
            for reason, count in _metadata_count_mapping(
                metadata.get(metadata_key)
            ).items():
                key = (label, reason)
                counts[key] = counts.get(key, 0) + count
    return [
        (distribution, reason, count)
        for (distribution, reason), count in sorted(counts.items())
    ]


def _metadata_count_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for key, raw_count in value.items():
        reason = str(key).strip()
        if not reason:
            continue
        try:
            count = int(float(raw_count))
        except (TypeError, ValueError):
            continue
        counts[reason] = counts.get(reason, 0) + count
    return counts
