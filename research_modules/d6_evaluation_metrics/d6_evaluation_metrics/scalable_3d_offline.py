"""Offline evaluation for truth-isolated scalable 3D episode bundles.

This module consumes persisted main-owned artifacts only.  It never imports a
runtime controller, writes to the online bus, or treats evaluator truth as an
online input.  Missing evidence remains null with an explicit availability
reason.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION = (
    "d6-scalable3d-offline-evaluation-v1"
)
SCALABLE_3D_OFFLINE_EVALUATION_DATE = "2026-07-20"
DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES = 2_000
DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED = 20260720
FIVE_METER_THRESHOLD_M = 5.0

_OPTIONAL_TRUTH_ARTIFACT = "offline_truth_labels.jsonl"
_GROUP_FIELDS = (
    "scenario_name",
    "scenario_version",
    "target_count",
    "resource_count",
    "recon_count",
    "camera_count",
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "entity_ids",
        "intercepted_target_indices",
        "offline_truth_labels",
    }
)
_METRIC_FIELDS = (
    "finite_state",
    "formal_acceptance_eligible",
    "online_truth_use_count",
    "online_truth_field_violation_count",
    "d1_track_count",
    "d1_speed_p50_mps",
    "d1_speed_p90_mps",
    "d1_speed_max_mps",
    "d1_velocity_covariance_trace_p50",
    "d1_velocity_covariance_trace_p90",
    "d1_velocity_covariance_trace_max",
    "d2_track_count",
    "d2_speed_p50_mps",
    "d2_speed_p90_mps",
    "d2_speed_max_mps",
    "d2_velocity_covariance_trace_p50",
    "d2_velocity_covariance_trace_p90",
    "d2_velocity_covariance_trace_max",
    "d2_id_switch_count",
    "d3_current_track_count",
    "d3_plan_target_count",
    "d3_assignment_count",
    "d3_assigned_target_count",
    "d3_plan_coverage_rate",
    "d3_backlog_count",
    "d3_min_dwell_hold_event_count",
    "d3_min_dwell_backlog_max",
    "d4_region_count",
    "d4_execution_allowed_region_count",
    "d4_fail_closed_region_count",
    "d4_lease_expired_region_count",
    "d4_commit_count",
    "d5_candidate_edge_count",
    "d5_graph_density",
    "d5_graph_edge_budget",
    "d5_graph_budget_utilization",
    "d5_graph_budget_dropped_count",
    "d5_binding_count",
    "d5_model_fallback_event_count",
    "d7_command_count",
    "d7_hold_count",
    "d7_reject_count",
    "offline_proximity_within_5m_count",
    "offline_proximity_unique_target_count",
    "offline_proximity_identity_evaluable_count",
    "offline_proximity_identity_correct_count",
    "offline_proximity_identity_correct_rate",
)
class Scalable3DOfflineEvaluationError(ValueError):
    """Raised when a persisted episode artifact is malformed or contradictory."""


@dataclass(frozen=True)
class Scalable3DOfflineEvaluationInputs:
    """Explicit episode directories supplied by main."""

    episode_dirs: tuple[Path, ...]

    def __post_init__(self) -> None:
        directories = tuple(Path(value).resolve() for value in self.episode_dirs)
        if not directories:
            raise ValueError("at least one scalable 3D episode directory is required")
        if len(set(directories)) != len(directories):
            raise ValueError("episode directories must be unique")
        object.__setattr__(self, "episode_dirs", directories)


class Scalable3DOfflineReportGenerator:
    """Generate per-episode CSV, aggregate JSON, Chinese Markdown, and a curve."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: Scalable3DOfflineEvaluationInputs,
        bootstrap_resamples: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES,
        bootstrap_rng_seed: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED,
        title: str = "可扩展三维真值隔离 episode 离线评估报告",
    ) -> dict[str, Path]:
        if int(bootstrap_resamples) <= 0:
            raise ValueError("bootstrap_resamples must be positive")
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        rows = [evaluate_scalable_3d_episode(path) for path in inputs.episode_dirs]
        stage_names = sorted(
            {
                stage
                for row in rows
                for stage in row.get("_stage_records", {})
            }
        )
        stage_slugs = [_stage_slug(stage) for stage in stage_names]
        if len(stage_slugs) != len(set(stage_slugs)):
            raise Scalable3DOfflineEvaluationError(
                "stage names collide after CSV column normalization"
            )
        for row in rows:
            _add_stage_columns(row, stage_names)
            _finalize_episode_status(row)

        aggregate = aggregate_scalable_3d_episodes(
            rows,
            bootstrap_resamples=int(bootstrap_resamples),
            bootstrap_rng_seed=int(bootstrap_rng_seed),
        )
        public_rows = [_public_row(row) for row in rows]

        csv_path = output_path / "scalable_3d_offline_per_episode_seed.csv"
        _write_rows_csv(csv_path, public_rows)

        aggregate_path = output_path / "scalable_3d_offline_aggregate.json"
        aggregate_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        plot_path = output_path / "scalable_3d_stage_timing_curves.png"
        _write_stage_timing_curves(aggregate, plot_path)

        markdown_path = output_path / "SCALABLE_3D_OFFLINE_EVALUATION_CN.md"
        markdown_path.write_text(
            render_scalable_3d_offline_markdown(
                public_rows,
                aggregate,
                title=title,
                plot_name=plot_path.name,
            ),
            encoding="utf-8",
        )
        return {
            "per_episode_seed_csv": csv_path,
            "aggregate_json": aggregate_path,
            "markdown": markdown_path,
            "stage_timing_curve": plot_path,
        }


def discover_scalable_3d_episode_dirs(
    *,
    episode_dirs: Iterable[str | Path] = (),
    episode_roots: Iterable[str | Path] = (),
) -> tuple[Path, ...]:
    """Resolve explicit directories and recursively discover manifest-bearing episodes."""

    resolved: list[Path] = [Path(value).resolve() for value in episode_dirs]
    for raw_root in episode_roots:
        root = Path(raw_root).resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"episode root does not exist: {root}")
        resolved.extend(path.parent.resolve() for path in sorted(root.rglob("manifest.json")))
    unique = tuple(dict.fromkeys(resolved))
    if not unique:
        raise ValueError("no scalable 3D episode directories were supplied or discovered")
    return unique


def evaluate_scalable_3d_episode(episode_dir: str | Path) -> dict[str, Any]:
    """Evaluate one persisted episode without importing or calling runtime code."""

    directory = Path(episode_dir).resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"episode directory does not exist: {directory}")

    manifest, manifest_reason = _load_json_object(directory / "manifest.json")
    config, config_reason = _load_json_object(directory / "scenario_config.json")
    summary, summary_reason = _load_json_object(directory / "summary.json")
    online, online_reason = _load_jsonl(directory / "online_observations.jsonl")
    proximity, proximity_reason = _load_jsonl(
        directory / "offline_proximity_intercepts.jsonl"
    )
    stages, stages_reason = _load_stage_timings(directory / "stage_timings.csv")

    row: dict[str, Any] = {
        "evaluation_schema_version": SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION,
        "evaluation_date": SCALABLE_3D_OFFLINE_EVALUATION_DATE,
        "episode_dir": str(directory),
        "_stage_records": stages or {},
        "_stage_file_reason": stages_reason,
        "_failure_reasons": [],
    }
    artifact_reasons = {
        "manifest.json": manifest_reason,
        "scenario_config.json": config_reason,
        "summary.json": summary_reason,
        "stage_timings.csv": stages_reason,
        "online_observations.jsonl": online_reason,
        "offline_proximity_intercepts.jsonl": proximity_reason,
    }
    row["artifact_availability_json"] = {
        name: {
            "availability": "available" if reason is None else "unavailable",
            "unavailable_reason": reason,
        }
        for name, reason in artifact_reasons.items()
    }

    _extract_provenance(row, manifest, config, summary)
    ordered_online = _ordered_online_records(online or [])
    _extract_online_truth_audit(
        row,
        ordered_online,
        summary,
        online_unavailable_reason=online_reason,
    )
    _extract_track_metrics(row, ordered_online, module="d1")
    _extract_track_metrics(row, ordered_online, module="d2")
    _extract_d2_id_switch(row, ordered_online)
    _extract_d3_metrics(row, ordered_online)
    _extract_d4_metrics(row, ordered_online)
    _extract_d5_metrics(row, ordered_online)
    _extract_d7_metrics(row, ordered_online)
    _extract_camera_count(row, config, ordered_online)
    _extract_proximity_metrics(
        row,
        directory=directory,
        proximity_records=proximity,
        proximity_reason=proximity_reason,
        online_records=ordered_online,
    )
    _put_unavailable(
        row,
        "mission_success",
        "five_meter_proximity_is_not_mission_success",
    )
    _add_stage_columns(row, sorted((stages or {}).keys()))
    _finalize_episode_status(row)
    return row


def aggregate_scalable_3d_episodes(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES,
    bootstrap_rng_seed: int = DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED,
) -> dict[str, Any]:
    """Aggregate by explicit scenario/version/scale and bootstrap distinct seeds."""

    if int(bootstrap_resamples) <= 0:
        raise ValueError("bootstrap_resamples must be positive")
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(field) for field in _GROUP_FIELDS)].append(row)

    groups: list[dict[str, Any]] = []
    scale_stage_shares: list[dict[str, Any]] = []
    for key in sorted(grouped, key=_sortable_group_key):
        group_rows = grouped[key]
        group_identity = dict(zip(_GROUP_FIELDS, key))
        seeds = sorted(
            {
                int(row["seed"])
                for row in group_rows
                if _is_int_like(row.get("seed"))
            }
        )
        metric_names = _aggregate_metric_names(group_rows)
        metric_statistics = {
            metric: _metric_statistics(
                group_rows,
                metric,
                bootstrap_resamples=int(bootstrap_resamples),
                bootstrap_rng_seed=int(bootstrap_rng_seed),
                group_identity=group_identity,
            )
            for metric in metric_names
        }
        stage_timing = _aggregate_stage_timing(
            group_rows,
            bootstrap_resamples=int(bootstrap_resamples),
            bootstrap_rng_seed=int(bootstrap_rng_seed),
            group_identity=group_identity,
        )
        seed_groups = _aggregate_exact_seed_groups(group_rows, metric_names)
        group = {
            **group_identity,
            "episode_count": len(group_rows),
            "seed_count": len(seeds),
            "seeds": seeds,
            "inference_status": (
                "bootstrap_across_distinct_seed_means"
                if len(seeds) >= 2
                else "descriptive_only_single_seed"
            ),
            "metric_statistics": metric_statistics,
            "stage_timing": stage_timing,
            "failure_reason_distribution": _counter_from_json_field(
                group_rows, "episode_failure_reasons_json"
            ),
            "evidence_unavailability_reason_distribution": (
                _counter_from_json_field(
                    group_rows, "evidence_unavailability_reasons_json"
                )
            ),
            "d4_fail_closed_reason_distribution": _counter_from_mapping_field(
                group_rows, "d4_fail_closed_reasons_json"
            ),
            "d5_fallback_reason_distribution": _counter_from_mapping_field(
                group_rows, "d5_fallback_reason_distribution_json"
            ),
            "d7_reject_reason_distribution": _counter_from_mapping_field(
                group_rows, "d7_reject_reason_distribution_json"
            ),
            "per_seed_groups": seed_groups,
        }
        groups.append(group)
        scale_stage_shares.append(
            {
                **group_identity,
                "episode_count": len(group_rows),
                "seed_count": len(seeds),
                "stages": {
                    stage: values["pooled_wall_time_share"]
                    for stage, values in stage_timing.items()
                },
            }
        )

    return {
        "schema_version": SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION,
        "evaluation_date": SCALABLE_3D_OFFLINE_EVALUATION_DATE,
        "episode_count": len(rows),
        "grouping_fields": list(_GROUP_FIELDS),
        "seed_grouping_field": "seed",
        "bootstrap": {
            "method": "percentile_95_ci_on_distinct_seed_means",
            "resamples": int(bootstrap_resamples),
            "rng_seed": int(bootstrap_rng_seed),
            "single_seed_policy": "descriptive_only_no_ci",
        },
        "formal_acceptance_eligible_episode_count": sum(
            row.get("formal_acceptance_eligible") is True for row in rows
        ),
        "repository_dirty_episode_count": sum(
            row.get("repository_dirty") is True for row in rows
        ),
        "single_seed_group_count": sum(group["seed_count"] < 2 for group in groups),
        "failure_reason_distribution": _counter_from_json_field(
            rows, "episode_failure_reasons_json"
        ),
        "evidence_unavailability_reason_distribution": _counter_from_json_field(
            rows, "evidence_unavailability_reasons_json"
        ),
        "groups": groups,
        "scale_stage_time_shares": scale_stage_shares,
        "physical_outcome_semantics": {
            "offline_proximity_within_5m_count": (
                "offline physical diagnostic only; not mission success"
            ),
            "identity_correctness": (
                "available only with explicit evaluator-side global-track-to-truth mapping"
            ),
        },
    }


def render_scalable_3d_offline_markdown(
    rows: Sequence[Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    *,
    title: str,
    plot_name: str,
) -> str:
    """Render a concise Chinese report with explicit evidence boundaries."""

    lines = [
        f"# {title}",
        "",
        f"评估日期：{SCALABLE_3D_OFFLINE_EVALUATION_DATE}",
        "",
        "## 结论",
        "",
        f"本次离线读取 {len(rows)} 个 main-owned episode。评估按 scenario/version、实际 target/resource/recon/camera 数量和 seed 组织，不从 2v2/5v5 名称推断规模。",
        f"正式 provenance 条件可用的 episode 为 {aggregate.get('formal_acceptance_eligible_episode_count', 0)}/{len(rows)}；dirty episode 为 {aggregate.get('repository_dirty_episode_count', 0)}。",
        "五米接近仅是离线物理诊断，不自动代表身份正确、合同许可、控制成功或任务成功。",
        "",
        "## Episode 明细",
        "",
        "| scenario/version | scale T/R/Rc/Cam | seed | finite | dirty | online truth | D1/D2 tracks | D2 IDSW | D3 coverage/backlog | D4 fail-closed | D5 fallback | D7 cmd/hold/reject | <=5m / identity |",
        "| --- | --- | ---: | :---: | :---: | ---: | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        scale = "/".join(
            _fmt(row.get(field))
            for field in ("target_count", "resource_count", "recon_count", "camera_count")
        )
        idsw = _fmt_available(row, "d2_id_switch_count")
        identity = _fmt_available(row, "offline_proximity_identity_correct_rate")
        lines.append(
            "| {scenario}/{version} | {scale} | {seed} | {finite} | {dirty} | {truth} | "
            "{d1}/{d2} | {idsw} | {coverage}/{backlog} | {fail_closed} | {fallback} | "
            "{commands}/{holds}/{rejects} | {proximity}/{identity} |".format(
                scenario=_fmt(row.get("scenario_name")),
                version=_fmt(row.get("scenario_version")),
                scale=scale,
                seed=_fmt(row.get("seed")),
                finite=_fmt_available(row, "finite_state"),
                dirty=_fmt_available(row, "repository_dirty"),
                truth=_fmt_available(row, "online_truth_use_count"),
                d1=_fmt_available(row, "d1_track_count"),
                d2=_fmt_available(row, "d2_track_count"),
                idsw=idsw,
                coverage=_fmt_available(row, "d3_plan_coverage_rate"),
                backlog=_fmt_available(row, "d3_min_dwell_backlog_max"),
                fail_closed=_fmt_available(row, "d4_fail_closed_region_count"),
                fallback=_fmt(row.get("d5_fallback_reason")),
                commands=_fmt_available(row, "d7_command_count"),
                holds=_fmt_available(row, "d7_hold_count"),
                rejects=_fmt_available(row, "d7_reject_count"),
                proximity=_fmt_available(row, "offline_proximity_within_5m_count"),
                identity=identity,
            )
        )

    lines.extend(
        [
            "",
            "## 聚合与不确定性",
            "",
            f"Bootstrap 使用固定 rng_seed={aggregate.get('bootstrap', {}).get('rng_seed')}、resamples={aggregate.get('bootstrap', {}).get('resamples')}，抽样单位为不同 seed 的 episode 均值。",
            "单 seed 分组只标记 descriptive，不生成 bootstrap 置信区间或推断性结论。",
            "",
            "| scenario/version | scale T/R/Rc/Cam | episodes | seeds | 状态 | finite mean | D3 coverage mean | D7 reject mean |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for group in aggregate.get("groups", []):
        metrics = group.get("metric_statistics", {})
        scale = "/".join(
            _fmt(group.get(field))
            for field in ("target_count", "resource_count", "recon_count", "camera_count")
        )
        lines.append(
            "| {scenario}/{version} | {scale} | {episodes} | {seeds} | {status} | {finite} | {coverage} | {reject} |".format(
                scenario=_fmt(group.get("scenario_name")),
                version=_fmt(group.get("scenario_version")),
                scale=scale,
                episodes=group.get("episode_count", 0),
                seeds=group.get("seed_count", 0),
                status=group.get("inference_status", "unavailable"),
                finite=_fmt_stat(metrics.get("finite_state")),
                coverage=_fmt_stat(metrics.get("d3_plan_coverage_rate")),
                reject=_fmt_stat(metrics.get("d7_reject_count")),
            )
        )

    lines.extend(
        [
            "",
            "## 不同规模阶段耗时占比",
            "",
            f"![阶段耗时曲线]({plot_name})",
            "",
            "| scenario/version | scale T/R/Rc/Cam | dominant stage | pooled share |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for item in aggregate.get("scale_stage_time_shares", []):
        stages = item.get("stages", {})
        available = {
            str(stage): value
            for stage, value in stages.items()
            if _is_finite_number(value)
        }
        dominant = max(available, key=available.get) if available else "unavailable"
        share = available.get(dominant)
        scale = "/".join(
            _fmt(item.get(field))
            for field in ("target_count", "resource_count", "recon_count", "camera_count")
        )
        lines.append(
            f"| {_fmt(item.get('scenario_name'))}/{_fmt(item.get('scenario_version'))} | {scale} | {dominant} | {_fmt(share)} |"
        )

    lines.extend(
        [
            "",
            "## 失败与可用性",
            "",
            f"Episode 失败/证据质量原因分布：`{json.dumps(aggregate.get('failure_reason_distribution', {}), ensure_ascii=False, sort_keys=True)}`。",
            f"缺失证据原因分布：`{json.dumps(aggregate.get('evidence_unavailability_reason_distribution', {}), ensure_ascii=False, sort_keys=True)}`。",
            "",
            "## 当前限制",
            "",
            "- 当前 producer 的 offline truth label 只含 observation-to-truth 映射，未显式提供 global_track_id-to-truth 映射时，五米接近身份正确性保持 unavailable。",
            "- D2 明确声明 IDSW unavailable 时，D6 不从轨迹数量、名称或离线真值补算 0。",
            "- D5 `model_missing` 表示确定性几何规则回退，不是学习模型性能证据。",
            "- 报告不把五米接近登记为任务成功；任务成功仍需身份、D4 授权、D7 控制和任务合同的独立证据。",
        ]
    )
    return "\n".join(lines) + "\n"


def _extract_provenance(
    row: dict[str, Any],
    manifest: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> None:
    sources = (("scenario_config", config), ("manifest", manifest), ("summary", summary))
    for field in ("episode_id", "scenario_name", "scenario_version", "seed"):
        value, source, reason = _first_explicit_field(sources, field)
        if field == "seed" and reason is None and not (
            _is_int_like(value) and int(value) >= 0
        ):
            reason = "invalid_nonnegative_integer:seed"
        elif field != "seed" and reason is None and not str(value).strip():
            reason = f"explicit_field_empty:{field}"
        if reason is None:
            if field == "seed":
                value = int(value)
            _put_available(row, field, value)
            row[f"{field}_source"] = source
        else:
            _put_unavailable(row, field, reason)

    for field in ("target_count", "resource_count", "recon_count"):
        value, source, reason = _first_explicit_field(
            (("scenario_config", config), ("summary", summary)), field
        )
        if reason is None and _is_int_like(value) and int(value) >= 0:
            _put_available(row, field, int(value))
            row[f"{field}_source"] = source
        else:
            _put_unavailable(
                row,
                field,
                reason or f"invalid_nonnegative_integer:{field}",
            )

    manifest_fields = (
        "git_commit",
        "repository_dirty",
        "config_sha256",
        "world_schema",
        "bus_schema",
        "scenario_schema",
        "online_observation_schema",
        "offline_truth_schema",
        "d1_model_version",
        "d2_model_version",
        "d3_policy_version",
        "d5_model_version",
        "d7_model_version",
        "threshold_version",
    )
    for field in manifest_fields:
        value = manifest.get(field) if manifest is not None else None
        invalid = value is None
        if field == "repository_dirty" and value is not None:
            invalid = not isinstance(value, bool)
        elif field != "repository_dirty" and value is not None:
            invalid = not str(value).strip()
        if invalid:
            _put_unavailable(row, field, f"manifest_field_missing:{field}")
        else:
            _put_available(row, field, value)

    if config is not None and config.get("schema_version") is not None:
        _put_available(row, "scenario_config_schema", config["schema_version"])
    else:
        _put_unavailable(row, "scenario_config_schema", "scenario_config_schema_missing")
    if summary is not None:
        diagnostics = summary.get("module_final_diagnostics")
        if isinstance(diagnostics, Mapping) and diagnostics.get("schema_version") is not None:
            _put_available(row, "module_stack_schema", diagnostics["schema_version"])
        else:
            _put_unavailable(row, "module_stack_schema", "module_stack_schema_missing")
    else:
        _put_unavailable(row, "module_stack_schema", "summary_json_missing")

    _validate_provenance_consistency(row, manifest, config, summary)
    if config is not None:
        canonical = json.dumps(
            config,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        computed = hashlib.sha256(canonical).hexdigest()
        _put_available(row, "computed_config_sha256", computed)
        if manifest is not None and manifest.get("config_sha256") is not None:
            _put_available(
                row,
                "config_hash_match",
                str(manifest["config_sha256"]) == computed,
            )
        else:
            _put_unavailable(row, "config_hash_match", "manifest_config_sha256_missing")
    else:
        _put_unavailable(row, "computed_config_sha256", "scenario_config_json_missing")
        _put_unavailable(row, "config_hash_match", "scenario_config_json_missing")

    if summary is not None and "finite_state" in summary:
        value = summary.get("finite_state")
        if isinstance(value, bool):
            _put_available(row, "finite_state", value)
        else:
            _put_unavailable(row, "finite_state", "summary_finite_state_not_boolean")
    else:
        _put_unavailable(row, "finite_state", "summary_finite_state_missing")


def _extract_online_truth_audit(
    row: dict[str, Any],
    records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
    *,
    online_unavailable_reason: str | None,
) -> None:
    if summary is not None and "online_truth_use_count" in summary:
        value = summary.get("online_truth_use_count")
        if _is_int_like(value) and int(value) >= 0:
            _put_available(row, "online_truth_use_count", int(value))
        else:
            _put_unavailable(
                row,
                "online_truth_use_count",
                "summary_online_truth_use_count_invalid",
            )
    else:
        _put_unavailable(
            row,
            "online_truth_use_count",
            "summary_online_truth_use_count_missing",
        )
    diagnostics = summary.get("module_final_diagnostics") if summary is not None else None
    if isinstance(diagnostics, Mapping) and "online_truth_use_count" in diagnostics:
        diagnostic_count = diagnostics.get("online_truth_use_count")
        if not (_is_int_like(diagnostic_count) and int(diagnostic_count) >= 0):
            row["_failure_reasons"].append(
                "module_diagnostics_online_truth_use_count_invalid"
            )
        elif (
            row.get("online_truth_use_count_availability") == "available"
            and int(diagnostic_count) != int(row["online_truth_use_count"])
        ):
            row["_failure_reasons"].append("online_truth_use_count_mismatch")
    if online_unavailable_reason is None:
        violations = sum(_count_forbidden_online_fields(record) for record in records)
        _put_available(row, "online_truth_field_violation_count", violations)
        _put_available(row, "online_record_count", len(records))
        _put_available(
            row,
            "online_schema_versions_json",
            dict(
                sorted(
                    Counter(
                        str(record.get("schema_version", "unavailable"))
                        for record in records
                    ).items()
                )
            ),
        )
    else:
        _put_unavailable(
            row,
            "online_truth_field_violation_count",
            online_unavailable_reason,
        )
        _put_unavailable(row, "online_record_count", online_unavailable_reason)
        _put_unavailable(row, "online_schema_versions_json", online_unavailable_reason)


def _extract_track_metrics(
    row: dict[str, Any],
    records: Sequence[Mapping[str, Any]],
    *,
    module: str,
) -> None:
    topic = f"modules.{module}." + (
        "fused_tracks" if module == "d1" else "associated_tracks"
    )
    record = _latest_topic(records, topic)
    fields = (
        f"{module}_speed_p50_mps",
        f"{module}_speed_p90_mps",
        f"{module}_speed_max_mps",
        f"{module}_velocity_covariance_trace_p50",
        f"{module}_velocity_covariance_trace_p90",
        f"{module}_velocity_covariance_trace_max",
    )
    if record is None:
        _put_unavailable(row, f"{module}_track_count", f"{module}_publication_missing")
        for field in fields:
            _put_unavailable(row, field, f"{module}_publication_missing")
        return
    payload = _payload(record)
    tracks = payload.get("tracks")
    declared = payload.get("track_count")
    if isinstance(tracks, list):
        count = len(tracks)
        _put_available(row, f"{module}_track_count", count)
        if _is_int_like(declared) and int(declared) != count:
            row["_failure_reasons"].append(f"{module}_track_count_mismatch")
    elif _is_int_like(declared) and int(declared) >= 0:
        count = int(declared)
        _put_available(row, f"{module}_track_count", count)
        for field in fields:
            _put_unavailable(row, field, f"{module}_track_list_missing")
        return
    else:
        _put_unavailable(row, f"{module}_track_count", f"{module}_track_count_missing")
        for field in fields:
            _put_unavailable(row, field, f"{module}_track_list_missing")
        return

    if not tracks:
        for field in fields:
            _put_unavailable(row, field, f"{module}_no_tracks")
        return

    speeds: list[float] = []
    velocity_traces: list[float] = []
    speed_reason: str | None = None
    covariance_reason: str | None = None
    for track in tracks:
        if not isinstance(track, Mapping):
            speed_reason = f"{module}_track_not_object"
            covariance_reason = speed_reason
            break
        state = track.get("state_ned")
        if not isinstance(state, Sequence) or isinstance(state, (str, bytes)) or len(state) < 6:
            speed_reason = f"{module}_track_state_missing_or_short"
        elif not all(_is_finite_number(value) for value in state[3:6]):
            speed_reason = f"{module}_track_velocity_nonfinite"
        else:
            speeds.append(float(np.linalg.norm(np.asarray(state[3:6], dtype=float))))

        covariance = track.get("covariance")
        try:
            matrix = np.asarray(covariance, dtype=float)
        except (TypeError, ValueError):
            covariance_reason = f"{module}_velocity_covariance_invalid"
        else:
            if (
                matrix.ndim != 2
                or matrix.shape[0] < 6
                or matrix.shape[1] < 6
                or not np.all(np.isfinite(matrix))
            ):
                covariance_reason = f"{module}_velocity_covariance_missing_or_nonfinite"
            else:
                velocity_traces.append(float(np.trace(matrix[3:6, 3:6])))
    if speed_reason is None and len(speeds) == len(tracks):
        _put_distribution(row, f"{module}_speed", speeds, unit_suffix="_mps")
    else:
        for field in fields[:3]:
            _put_unavailable(row, field, speed_reason or f"{module}_track_velocity_incomplete")
    if covariance_reason is None and len(velocity_traces) == len(tracks):
        _put_distribution(
            row,
            f"{module}_velocity_covariance_trace",
            velocity_traces,
            unit_suffix="",
        )
    else:
        for field in fields[3:]:
            _put_unavailable(
                row,
                field,
                covariance_reason or f"{module}_velocity_covariance_incomplete",
            )


def _extract_d2_id_switch(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    record = _latest_topic(records, "modules.d2.associated_tracks")
    if record is None:
        _put_unavailable(row, "d2_id_switch_count", "d2_publication_missing")
        return
    payload = _payload(record)
    available = payload.get("id_switch_count_available")
    value = payload.get("id_switch_count")
    if available is True and _is_int_like(value) and int(value) >= 0:
        _put_available(row, "d2_id_switch_count", int(value))
    elif available is False:
        _put_unavailable(
            row,
            "d2_id_switch_count",
            "producer_declared_id_switch_count_unavailable",
        )
    elif "id_switch_count_available" not in payload:
        _put_unavailable(
            row,
            "d2_id_switch_count",
            "d2_id_switch_availability_field_missing",
        )
    else:
        _put_unavailable(row, "d2_id_switch_count", "d2_id_switch_count_invalid")


def _extract_d3_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    current_d2_count: int | None = None
    timeline: list[dict[str, Any]] = []
    for record in records:
        topic = str(record.get("topic", ""))
        payload = _payload(record)
        if topic == "modules.d2.associated_tracks":
            tracks = payload.get("tracks")
            declared = payload.get("track_count")
            if isinstance(tracks, list):
                current_d2_count = len(tracks)
            elif _is_int_like(declared) and int(declared) >= 0:
                current_d2_count = int(declared)
        elif topic == "modules.d3.assignment_plan":
            timeline.append(_d3_snapshot(payload, current_d2_count))

    fields = (
        "d3_current_track_count",
        "d3_plan_target_count",
        "d3_assignment_count",
        "d3_assigned_target_count",
        "d3_plan_coverage_rate",
        "d3_backlog_count",
        "d3_min_dwell_hold_event_count",
        "d3_min_dwell_backlog_max",
    )
    if not timeline:
        for field in fields:
            _put_unavailable(row, field, "d3_publication_missing")
        for field in (
            "d3_hysteresis_state",
            "d3_hysteresis_reason",
            "d3_hysteresis_reasons_json",
        ):
            _put_unavailable(row, field, "d3_publication_missing")
        return

    latest = timeline[-1]
    for field in fields[:6]:
        value = latest.get(field)
        reason = latest.get(f"{field}_unavailable_reason")
        if reason is None:
            _put_available(row, field, value)
        else:
            _put_unavailable(row, field, reason)

    hysteresis_auditable = all(
        "hysteresis_state" in item["metadata"] for item in timeline
    )
    min_dwell_rows = [item for item in timeline if item["min_dwell_hold"]]
    if hysteresis_auditable:
        _put_available(row, "d3_min_dwell_hold_event_count", len(min_dwell_rows))
    else:
        _put_unavailable(
            row,
            "d3_min_dwell_hold_event_count",
            "d3_hysteresis_state_missing",
        )
    if min_dwell_rows and hysteresis_auditable:
        backlogs = [
            item["d3_backlog_count"]
            for item in min_dwell_rows
            if _is_int_like(item.get("d3_backlog_count"))
        ]
        if len(backlogs) == len(min_dwell_rows):
            _put_available(row, "d3_min_dwell_backlog_max", max(backlogs))
        else:
            _put_unavailable(
                row,
                "d3_min_dwell_backlog_max",
                "d3_min_dwell_hold_backlog_unavailable",
            )
    elif hysteresis_auditable:
        _put_available(row, "d3_min_dwell_backlog_max", 0)
    else:
        _put_unavailable(
            row,
            "d3_min_dwell_backlog_max",
            "d3_hysteresis_state_missing",
        )

    metadata = latest["metadata"]
    for field, key in (
        ("d3_hysteresis_state", "hysteresis_state"),
        ("d3_hysteresis_reason", "hysteresis_reason"),
        ("d3_hysteresis_dwell_time_s", "hysteresis_dwell_time_s"),
        ("d3_hysteresis_min_dwell_s", "hysteresis_min_dwell_s"),
    ):
        if key in metadata and metadata[key] is not None:
            _put_available(row, field, metadata[key])
        else:
            _put_unavailable(row, field, f"d3_metadata_missing:{key}")
    reason_counter: Counter[str] = Counter()
    for item in timeline:
        reason_counter.update(item["hysteresis_reasons"])
    if hysteresis_auditable:
        _put_available(
            row,
            "d3_hysteresis_reasons_json",
            dict(sorted(reason_counter.items())),
        )
    else:
        _put_unavailable(
            row,
            "d3_hysteresis_reasons_json",
            "d3_hysteresis_state_missing",
        )
    row["d3_timeline_publication_count"] = len(timeline)


def _d3_snapshot(payload: Mapping[str, Any], current_d2_count: int | None) -> dict[str, Any]:
    metadata = payload.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    current_count = current_d2_count
    candidate_ids = metadata.get("hysteresis_candidate_target_ids")
    if current_count is None and isinstance(candidate_ids, list):
        current_count = len(candidate_ids)

    assignments = payload.get("assignments")
    declared_assignment_count = payload.get("assignment_count")
    assigned_ids: list[str] | None = None
    if isinstance(assignments, list) and all(isinstance(item, Mapping) for item in assignments):
        raw_ids = [item.get("global_track_id") for item in assignments]
        if all(value is not None and str(value) for value in raw_ids):
            assigned_ids = [str(value) for value in raw_ids]
    assignment_count = (
        len(assignments)
        if isinstance(assignments, list)
        else (
            int(declared_assignment_count)
            if _is_int_like(declared_assignment_count) and int(declared_assignment_count) >= 0
            else None
        )
    )
    plan_target_count = payload.get("target_count")
    if not (_is_int_like(plan_target_count) and int(plan_target_count) >= 0):
        plan_target_count = None
    else:
        plan_target_count = int(plan_target_count)

    unique_assigned = None if assigned_ids is None else len(set(assigned_ids))
    if current_count is not None and unique_assigned is not None and current_count > 0:
        coverage = unique_assigned / current_count
    else:
        coverage = None
    pending = metadata.get("hysteresis_pending_new_target_ids")
    if isinstance(pending, list):
        backlog = len({str(value) for value in pending})
    elif current_count is not None and unique_assigned is not None:
        backlog = max(0, current_count - unique_assigned)
    else:
        backlog = None

    raw_reasons = metadata.get("hysteresis_reasons")
    reasons: tuple[str, ...]
    if isinstance(raw_reasons, Sequence) and not isinstance(raw_reasons, (str, bytes)):
        reasons = tuple(str(value) for value in raw_reasons if str(value))
    elif metadata.get("hysteresis_reason") is not None:
        reasons = (str(metadata["hysteresis_reason"]),)
    else:
        reasons = ()
    min_dwell_hold = str(metadata.get("hysteresis_state", "")).lower() == "held" and (
        "min_dwell_not_met" in reasons or metadata.get("hysteresis_dwell_ok") is False
    )
    return {
        "d3_current_track_count": current_count,
        "d3_current_track_count_unavailable_reason": (
            None if current_count is not None else "d3_current_d2_track_count_unavailable"
        ),
        "d3_plan_target_count": plan_target_count,
        "d3_plan_target_count_unavailable_reason": (
            None if plan_target_count is not None else "d3_plan_target_count_missing"
        ),
        "d3_assignment_count": assignment_count,
        "d3_assignment_count_unavailable_reason": (
            None if assignment_count is not None else "d3_assignment_count_missing"
        ),
        "d3_assigned_target_count": unique_assigned,
        "d3_assigned_target_count_unavailable_reason": (
            None if unique_assigned is not None else "d3_assignment_target_ids_missing"
        ),
        "d3_plan_coverage_rate": coverage,
        "d3_plan_coverage_rate_unavailable_reason": (
            None
            if coverage is not None
            else "d3_current_tracks_or_assignment_target_ids_unavailable"
        ),
        "d3_backlog_count": backlog,
        "d3_backlog_count_unavailable_reason": (
            None if backlog is not None else "d3_backlog_inputs_unavailable"
        ),
        "metadata": metadata,
        "hysteresis_reasons": reasons,
        "min_dwell_hold": min_dwell_hold,
    }


def _extract_d4_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    record = _latest_topic(records, "modules.d4.regional_failover")
    fields = (
        "d4_region_count",
        "d4_execution_allowed_region_count",
        "d4_fail_closed_region_count",
        "d4_lease_expired_region_count",
        "d4_commit_count",
    )
    if record is None:
        for field in fields:
            _put_unavailable(row, field, "d4_publication_missing")
        for field in (
            "d4_owner_records_json",
            "d4_owner_layer_distribution_json",
            "d4_owner_node_ids_json",
            "d4_owner_epochs_json",
            "d4_owner_lease_expires_at_s_json",
            "d4_commit_state_distribution_json",
            "d4_fail_closed_reasons_json",
        ):
            _put_unavailable(row, field, "d4_publication_missing")
        return
    payload = _payload(record)
    regions = payload.get("regions")
    if not isinstance(regions, list) or not all(isinstance(item, Mapping) for item in regions):
        for field in fields:
            _put_unavailable(row, field, "d4_regions_missing_or_invalid")
        return

    timestamp = payload.get("timestamp_s", record.get("timestamp"))
    timestamp_value = float(timestamp) if _is_finite_number(timestamp) else None
    owner_records: list[dict[str, Any]] = []
    layer_counter: Counter[str] = Counter()
    nodes: set[str] = set()
    epochs: list[int] = []
    leases: list[float] = []
    commit_states: Counter[str] = Counter()
    fail_reasons: Counter[str] = Counter()
    execution_allowed = 0
    fail_closed = 0
    lease_expired = 0
    commit_count = 0
    complete_owner_evidence = True
    execution_fields_complete = True
    fail_closed_fields_complete = True
    commit_fields_complete = True
    for region in regions:
        ownership = region.get("ownership")
        ownership = ownership if isinstance(ownership, Mapping) else {}
        layer = ownership.get("owner_layer", region.get("selected_layer"))
        node = ownership.get("owner_id", region.get("selected_secondary_id"))
        epoch = ownership.get("epoch")
        lease = ownership.get("lease_expires_at_s")
        owner_record = {
            "region_id": region.get("region_id"),
            "owner_layer": layer,
            "owner_node_id": node,
            "owner_node_availability": (
                "available" if node is not None else "unavailable"
            ),
            "owner_node_unavailable_reason": (
                None if node is not None else "region_has_no_active_owner_node"
            ),
            "epoch": epoch,
            "lease_expires_at_s": lease,
            "active": ownership.get("active"),
        }
        owner_records.append(owner_record)
        if layer is None:
            complete_owner_evidence = False
        else:
            layer_counter[str(layer)] += 1
        if node is not None:
            nodes.add(str(node))
        if _is_int_like(epoch) and int(epoch) >= 0:
            epochs.append(int(epoch))
        else:
            complete_owner_evidence = False
        if _is_finite_number(lease):
            lease_value = float(lease)
            leases.append(lease_value)
            if timestamp_value is not None and timestamp_value >= lease_value:
                lease_expired += 1
        else:
            complete_owner_evidence = False

        if "execution_allowed" not in region or not isinstance(
            region.get("execution_allowed"), bool
        ):
            execution_fields_complete = False
        elif region.get("execution_allowed") is True:
            execution_allowed += 1
        if "fail_closed" not in region or not isinstance(region.get("fail_closed"), bool):
            fail_closed_fields_complete = False
        elif region.get("fail_closed") is True:
            fail_closed += 1
            region_fail_reasons: set[str] = set()
            reason = region.get("reason")
            if reason is not None:
                region_fail_reasons.add(str(reason))
            rejection_reasons = region.get("rejection_reasons")
            if isinstance(rejection_reasons, list):
                region_fail_reasons.update(
                    str(value) for value in rejection_reasons if str(value)
                )
            if reason is None and not rejection_reasons:
                region_fail_reasons.add("d4_fail_closed_reason_missing")
            fail_reasons.update(region_fail_reasons)
        commits = region.get("coalition_commits")
        if isinstance(commits, list):
            for commit in commits:
                if not isinstance(commit, Mapping):
                    continue
                commit_count += 1
                state = commit.get("state")
                commit_states[str(state) if state is not None else "unavailable"] += 1
                commit_lease = commit.get("lease_expires_at_s")
                if (
                    timestamp_value is not None
                    and _is_finite_number(commit_lease)
                    and timestamp_value >= float(commit_lease)
                ):
                    fail_reasons["coalition_commit_lease_expired"] += 1
        else:
            commit_fields_complete = False

    _put_available(row, "d4_region_count", len(regions))
    if execution_fields_complete:
        _put_available(row, "d4_execution_allowed_region_count", execution_allowed)
    else:
        _put_unavailable(
            row,
            "d4_execution_allowed_region_count",
            "d4_region_execution_allowed_field_missing",
        )
    if fail_closed_fields_complete:
        _put_available(row, "d4_fail_closed_region_count", fail_closed)
    else:
        _put_unavailable(
            row,
            "d4_fail_closed_region_count",
            "d4_region_fail_closed_field_missing",
        )
    if timestamp_value is not None and len(leases) == len(regions):
        _put_available(row, "d4_lease_expired_region_count", lease_expired)
    else:
        _put_unavailable(
            row,
            "d4_lease_expired_region_count",
            "d4_timestamp_or_region_lease_missing",
        )
    if commit_fields_complete:
        _put_available(row, "d4_commit_count", commit_count)
        _put_available(
            row,
            "d4_commit_state_distribution_json",
            dict(sorted(commit_states.items())),
        )
    else:
        _put_unavailable(row, "d4_commit_count", "d4_coalition_commits_field_missing")
        _put_unavailable(
            row,
            "d4_commit_state_distribution_json",
            "d4_coalition_commits_field_missing",
        )
    _put_available(row, "d4_fail_closed_reasons_json", dict(sorted(fail_reasons.items())))
    if complete_owner_evidence:
        _put_available(row, "d4_owner_records_json", owner_records)
        _put_available(
            row,
            "d4_owner_layer_distribution_json",
            dict(sorted(layer_counter.items())),
        )
        _put_available(row, "d4_owner_node_ids_json", sorted(nodes))
        _put_available(row, "d4_owner_epochs_json", sorted(set(epochs)))
        _put_available(row, "d4_owner_lease_expires_at_s_json", sorted(set(leases)))
    else:
        _put_unavailable(row, "d4_owner_records_json", "d4_owner_contract_fields_missing")
        _put_unavailable(
            row,
            "d4_owner_layer_distribution_json",
            "d4_owner_contract_fields_missing",
        )
        _put_unavailable(row, "d4_owner_node_ids_json", "d4_owner_contract_fields_missing")
        _put_unavailable(row, "d4_owner_epochs_json", "d4_owner_contract_fields_missing")
        _put_unavailable(
            row,
            "d4_owner_lease_expires_at_s_json",
            "d4_owner_contract_fields_missing",
        )
    row["d4_latest_timestamp_s"] = timestamp_value


def _extract_d5_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    d5_records = [
        record
        for record in records
        if record.get("topic") == "modules.d5.terminal_association"
    ]
    fields = (
        "d5_candidate_edge_count",
        "d5_graph_density",
        "d5_graph_edge_budget",
        "d5_graph_budget_utilization",
        "d5_graph_budget_dropped_count",
        "d5_binding_count",
        "d5_model_fallback_event_count",
    )
    if not d5_records:
        for field in fields:
            _put_unavailable(row, field, "d5_publication_missing")
        for field in (
            "d5_probability_source",
            "d5_scoring_status",
            "d5_fallback_reason",
            "d5_fallback_reason_distribution_json",
        ):
            _put_unavailable(row, field, "d5_publication_missing")
        return
    latest = _payload(d5_records[-1])
    diagnostics = latest.get("diagnostics")
    diagnostics = diagnostics if isinstance(diagnostics, Mapping) else {}
    candidate_edges = diagnostics.get("candidate_tracklet_edges", latest.get("graph_edge_count"))
    nodes = latest.get("graph_node_count")
    graph_edges = latest.get("graph_edge_count", candidate_edges)
    per_node_cap = diagnostics.get("max_tracklet_candidate_edges_per_node")
    dropped = diagnostics.get("tracklet_candidate_budget_dropped")
    if _is_int_like(candidate_edges) and int(candidate_edges) >= 0:
        _put_available(row, "d5_candidate_edge_count", int(candidate_edges))
    else:
        _put_unavailable(row, "d5_candidate_edge_count", "d5_candidate_edge_count_missing")
    if _is_int_like(nodes) and int(nodes) >= 0 and _is_int_like(graph_edges):
        node_count = int(nodes)
        possible = node_count * max(0, node_count - 1) // 2
        density = 0.0 if possible == 0 and int(graph_edges) == 0 else (
            float(graph_edges) / possible if possible > 0 else None
        )
        if density is not None:
            _put_available(row, "d5_graph_density", density)
        else:
            _put_unavailable(row, "d5_graph_density", "d5_graph_density_undefined")
    else:
        _put_unavailable(row, "d5_graph_density", "d5_graph_node_or_edge_count_missing")
    if _is_int_like(nodes) and _is_int_like(per_node_cap) and int(per_node_cap) >= 0:
        budget = int(nodes) * int(per_node_cap) // 2
        _put_available(row, "d5_graph_edge_budget", budget)
        if _is_int_like(candidate_edges) and budget > 0:
            _put_available(
                row,
                "d5_graph_budget_utilization",
                float(candidate_edges) / budget,
            )
        elif (
            _is_int_like(candidate_edges)
            and budget == 0
            and int(candidate_edges) == 0
        ):
            _put_available(row, "d5_graph_budget_utilization", 0.0)
        else:
            _put_unavailable(
                row,
                "d5_graph_budget_utilization",
                "d5_candidate_edge_count_missing",
            )
    else:
        _put_unavailable(row, "d5_graph_edge_budget", "d5_graph_degree_cap_missing")
        _put_unavailable(
            row,
            "d5_graph_budget_utilization",
            "d5_graph_degree_cap_missing",
        )
    if _is_int_like(dropped) and int(dropped) >= 0:
        _put_available(row, "d5_graph_budget_dropped_count", int(dropped))
    else:
        _put_unavailable(
            row,
            "d5_graph_budget_dropped_count",
            "d5_graph_budget_drop_diagnostic_missing",
        )
    bindings = latest.get("bindings")
    if (
        isinstance(bindings, list)
        and all(isinstance(item, Mapping) for item in bindings)
        and all("global_track_id" in item for item in bindings)
    ):
        _put_available(
            row,
            "d5_binding_count",
            sum(item.get("global_track_id") is not None for item in bindings),
        )
    else:
        _put_unavailable(row, "d5_binding_count", "d5_bindings_missing")
    for field in ("probability_source", "scoring_status", "fallback_reason"):
        value = latest.get(field)
        if value is not None:
            _put_available(row, f"d5_{field}", value)
        elif field == "fallback_reason" and field in latest:
            _put_available(row, "d5_fallback_reason", "none")
        else:
            _put_unavailable(row, f"d5_{field}", f"d5_{field}_missing")
    fallbacks = Counter(
        str(_payload(record).get("fallback_reason"))
        for record in d5_records
        if _payload(record).get("fallback_reason") not in (None, "none", "")
    )
    _put_available(row, "d5_model_fallback_event_count", sum(fallbacks.values()))
    _put_available(
        row,
        "d5_fallback_reason_distribution_json",
        dict(sorted(fallbacks.items())),
    )
    row["d5_camera_batch_count"] = latest.get("camera_batch_count")
    row["d5_diagnostics_json"] = dict(diagnostics)


def _extract_d7_metrics(
    row: dict[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    d7_records = [
        record
        for record in records
        if record.get("topic") == "modules.d7.guidance_commands"
    ]
    if not d7_records:
        for field in ("d7_command_count", "d7_hold_count", "d7_reject_count"):
            _put_unavailable(row, field, "d7_publication_missing")
        _put_unavailable(row, "d7_mode_distribution_json", "d7_publication_missing")
        _put_unavailable(
            row, "d7_reject_reason_distribution_json", "d7_publication_missing"
        )
        return
    commands: list[Mapping[str, Any]] = []
    declared_total = 0
    declared_counts_complete = True
    command_lists_complete = True
    for record in d7_records:
        payload = _payload(record)
        declared = payload.get("command_count")
        if _is_int_like(declared) and int(declared) >= 0:
            declared_total += int(declared)
        else:
            declared_counts_complete = False
        values = payload.get("commands")
        if isinstance(values, list) and all(isinstance(item, Mapping) for item in values):
            commands.extend(values)
        else:
            command_lists_complete = False
    if command_lists_complete:
        _put_available(row, "d7_command_count", len(commands))
    elif declared_counts_complete:
        _put_available(row, "d7_command_count", declared_total)
    else:
        _put_unavailable(row, "d7_command_count", "d7_command_count_missing")
    if not command_lists_complete:
        _put_unavailable(row, "d7_hold_count", "d7_command_list_missing")
        _put_unavailable(row, "d7_reject_count", "d7_command_list_missing")
        _put_unavailable(row, "d7_mode_distribution_json", "d7_command_list_missing")
        _put_unavailable(
            row,
            "d7_reject_reason_distribution_json",
            "d7_command_list_missing",
        )
        return
    if not all("mode" in command and command.get("mode") is not None for command in commands):
        _put_unavailable(row, "d7_hold_count", "d7_command_mode_missing")
        _put_unavailable(row, "d7_reject_count", "d7_command_mode_missing")
        _put_unavailable(row, "d7_mode_distribution_json", "d7_command_mode_missing")
        _put_unavailable(
            row,
            "d7_reject_reason_distribution_json",
            "d7_command_mode_missing",
        )
        return
    modes = Counter(str(command["mode"]) for command in commands)
    hold_commands = [command for command in commands if command.get("mode") == "hold"]
    rejected = [
        command for command in hold_commands if str(command.get("gate_reason", "")).strip()
    ]
    reasons = Counter(str(command["gate_reason"]) for command in rejected)
    _put_available(row, "d7_hold_count", len(hold_commands))
    _put_available(row, "d7_reject_count", len(rejected))
    _put_available(row, "d7_mode_distribution_json", dict(sorted(modes.items())))
    _put_available(
        row,
        "d7_reject_reason_distribution_json",
        dict(sorted(reasons.items())),
    )


def _extract_camera_count(
    row: dict[str, Any],
    config: Mapping[str, Any] | None,
    records: Sequence[Mapping[str, Any]],
) -> None:
    metadata = config.get("metadata") if isinstance(config, Mapping) else None
    explicit = metadata.get("camera_count") if isinstance(metadata, Mapping) else None
    if _is_int_like(explicit) and int(explicit) >= 0:
        _put_available(row, "camera_count", int(explicit))
        row["camera_count_source"] = "scenario_config.metadata.camera_count"
        return
    if isinstance(config, Mapping) and config.get("visual_enabled") is False:
        _put_available(row, "camera_count", 0)
        row["camera_count_source"] = "scenario_config.visual_enabled_false"
        return
    resource_count = row.get("resource_count")
    recon_count = row.get("recon_count")
    if (
        isinstance(config, Mapping)
        and config.get("visual_enabled") is True
        and _is_int_like(resource_count)
        and _is_int_like(recon_count)
    ):
        _put_available(row, "camera_count", int(resource_count) + int(recon_count))
        row["camera_count_source"] = (
            "producer_one_camera_per_resource_and_recon_contract"
        )
        return
    d5_counts = [
        _payload(record).get("camera_batch_count")
        for record in records
        if record.get("topic") == "modules.d5.terminal_association"
    ]
    valid_d5 = [int(value) for value in d5_counts if _is_int_like(value) and int(value) >= 0]
    if valid_d5:
        _put_available(row, "camera_count", max(valid_d5))
        row["camera_count_source"] = "d5_camera_batch_count"
        return
    observed: set[str] = set()
    for record in records:
        payload = _payload(record)
        measurements = payload.get("measurements")
        if record.get("topic") != "sensor.observations" or not isinstance(measurements, list):
            continue
        if any(
            isinstance(item, Mapping) and item.get("modality") == "vision_bbox"
            for item in measurements
        ):
            sensor_id = payload.get("sensor_id")
            if sensor_id is not None:
                observed.add(str(sensor_id))
    if observed:
        _put_available(row, "camera_count", len(observed))
        row["camera_count_source"] = "observed_visual_sensor_ids"
        return
    if _is_int_like(resource_count) and _is_int_like(recon_count):
        _put_available(row, "camera_count", int(resource_count) + int(recon_count))
        row["camera_count_source"] = "producer_one_camera_per_resource_and_recon_contract"
    else:
        _put_unavailable(row, "camera_count", "camera_count_evidence_missing")


def _extract_proximity_metrics(
    row: dict[str, Any],
    *,
    directory: Path,
    proximity_records: Sequence[Mapping[str, Any]] | None,
    proximity_reason: str | None,
    online_records: Sequence[Mapping[str, Any]],
) -> None:
    if proximity_records is None:
        for field in (
            "offline_proximity_within_5m_count",
            "offline_proximity_unique_target_count",
            "offline_proximity_identity_evaluable_count",
            "offline_proximity_identity_correct_count",
            "offline_proximity_identity_correct_rate",
        ):
            _put_unavailable(row, field, proximity_reason or "offline_proximity_file_missing")
        row["offline_truth_labels_read"] = False
        return
    within: list[Mapping[str, Any]] = []
    invalid_distance = False
    for record in proximity_records:
        distance = record.get("distance_m")
        if not _is_finite_number(distance):
            invalid_distance = True
            continue
        if float(distance) <= FIVE_METER_THRESHOLD_M + 1.0e-12:
            within.append(record)
    if invalid_distance:
        _put_unavailable(
            row,
            "offline_proximity_within_5m_count",
            "offline_proximity_distance_missing_or_nonfinite",
        )
        _put_unavailable(
            row,
            "offline_proximity_unique_target_count",
            "offline_proximity_distance_missing_or_nonfinite",
        )
    else:
        _put_available(row, "offline_proximity_within_5m_count", len(within))
        truth_ids = [record.get("truth_target_id") for record in within]
        if all(value is not None for value in truth_ids):
            _put_available(
                row,
                "offline_proximity_unique_target_count",
                len({str(value) for value in truth_ids}),
            )
        elif within:
            _put_unavailable(
                row,
                "offline_proximity_unique_target_count",
                "offline_proximity_truth_target_id_missing",
            )
        else:
            _put_available(row, "offline_proximity_unique_target_count", 0)

    if not within:
        row["offline_truth_labels_read"] = False
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_count",
            "no_five_meter_proximity_events",
        )
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_rate",
            "no_five_meter_proximity_events",
        )
        return

    labels, label_reason = _load_jsonl(directory / _OPTIONAL_TRUTH_ARTIFACT)
    row["offline_truth_labels_read"] = True
    row["offline_truth_labels_read_reason"] = "five_meter_identity_scoring_requested"
    if labels is None:
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_count",
            label_reason or "offline_truth_labels_missing",
        )
        _put_unavailable(
            row,
            "offline_proximity_identity_correct_rate",
            label_reason or "offline_truth_labels_missing",
        )
        return
    truth_map, map_reason = _offline_global_track_truth_map(labels)
    if map_reason is not None:
        _put_available(row, "offline_proximity_identity_evaluable_count", 0)
        _put_unavailable(row, "offline_proximity_identity_correct_count", map_reason)
        _put_unavailable(row, "offline_proximity_identity_correct_rate", map_reason)
        return
    evaluations: list[bool] = []
    for event in within:
        assigned_track = _assigned_track_for_proximity_event(event, online_records)
        truth_target = event.get("truth_target_id")
        if assigned_track is None or truth_target is None or assigned_track not in truth_map:
            continue
        evaluations.append(truth_map[assigned_track] == str(truth_target))
    _put_available(row, "offline_proximity_identity_evaluable_count", len(evaluations))
    if len(evaluations) != len(within):
        reason = "incomplete_offline_assignment_or_global_track_truth_mapping"
        _put_unavailable(row, "offline_proximity_identity_correct_count", reason)
        _put_unavailable(row, "offline_proximity_identity_correct_rate", reason)
    else:
        correct = sum(evaluations)
        _put_available(row, "offline_proximity_identity_correct_count", correct)
        _put_available(
            row,
            "offline_proximity_identity_correct_rate",
            correct / len(evaluations),
        )


def _offline_global_track_truth_map(
    labels: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], str | None]:
    mapping: dict[str, str] = {}
    saw_mapping_field = False
    for label in labels:
        global_track = label.get("global_track_id", label.get("center_global_track_id"))
        truth = label.get("truth_entity_id", label.get("truth_target_id"))
        if global_track is None:
            continue
        saw_mapping_field = True
        if truth is None:
            return {}, "offline_truth_global_track_mapping_truth_id_missing"
        key = str(global_track)
        value = str(truth)
        if key in mapping and mapping[key] != value:
            return {}, "offline_truth_global_track_mapping_conflict"
        mapping[key] = value
    if not saw_mapping_field:
        return {}, "offline_truth_labels_lack_global_track_mapping"
    return mapping, None


def _assigned_track_for_proximity_event(
    event: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> str | None:
    explicit = event.get("assigned_global_track_id", event.get("global_track_id"))
    if explicit is not None:
        return str(explicit)
    timestamp = event.get("timestamp")
    resource_id = event.get("resource_id")
    if not _is_finite_number(timestamp) or resource_id is None:
        return None
    selected: str | None = None
    for record in records:
        if record.get("topic") != "modules.d3.assignment_plan":
            continue
        record_timestamp = record.get("timestamp")
        if not _is_finite_number(record_timestamp) or float(record_timestamp) > float(timestamp):
            continue
        assignments = _payload(record).get("assignments")
        if not isinstance(assignments, list):
            continue
        for assignment in assignments:
            if not isinstance(assignment, Mapping):
                continue
            if str(assignment.get("resource_id")) == str(resource_id):
                value = assignment.get("global_track_id")
                if value is not None:
                    selected = str(value)
    return selected


def _add_stage_columns(row: dict[str, Any], stage_names: Sequence[str]) -> None:
    stages = row.get("_stage_records", {})
    file_reason = row.get("_stage_file_reason")
    for stage in stage_names:
        prefix = f"stage__{_stage_slug(stage)}"
        record = stages.get(stage) if isinstance(stages, Mapping) else None
        for source, suffix in (
            ("call_count", "call_count"),
            ("wall_time_s", "wall_time_s"),
            ("mean_wall_time_ms", "mean_wall_time_ms"),
        ):
            field = f"{prefix}__{suffix}"
            if isinstance(record, Mapping) and record.get(source) is not None:
                _put_available(row, field, record[source])
            else:
                _put_unavailable(row, field, f"stage_metric_missing:{stage}:{source}")
    if file_reason is None:
        _put_available(row, "stage_timings_json", stages)
    else:
        _put_unavailable(row, "stage_timings_json", str(file_reason))


def _finalize_episode_status(row: dict[str, Any]) -> None:
    failures = list(row.get("_failure_reasons", []))
    if row.get("finite_state_availability") == "available" and row.get("finite_state") is False:
        failures.append("non_finite_world_state")
    if (
        row.get("online_truth_use_count_availability") == "available"
        and int(row.get("online_truth_use_count", 0)) > 0
    ):
        failures.append("online_truth_use_nonzero")
    if int(row.get("online_truth_field_violation_count", 0)) > 0:
        failures.append("online_truth_field_violation")
    if row.get("repository_dirty") is True:
        failures.append("repository_dirty_not_formal_evidence")
    if row.get("config_hash_match") is False:
        failures.append("config_hash_mismatch")
    d4_reasons = row.get("d4_fail_closed_reasons_json")
    if isinstance(d4_reasons, Mapping):
        failures.extend(f"d4_fail_closed:{reason}" for reason in d4_reasons)
    failures = list(dict.fromkeys(str(value) for value in failures if str(value)))

    critical_fields = (
        "finite_state",
        "repository_dirty",
        "config_hash_match",
        "online_truth_use_count",
        "online_truth_field_violation_count",
    )
    critical_available = all(
        row.get(f"{field}_availability") == "available" for field in critical_fields
    )
    eligible = (
        critical_available
        and row.get("finite_state") is True
        and row.get("repository_dirty") is False
        and row.get("config_hash_match") is True
        and row.get("online_truth_use_count") == 0
        and row.get("online_truth_field_violation_count") == 0
        and not any(
            reason.startswith(
                (
                    "provenance_field_mismatch:",
                    "d1_track_count_mismatch",
                    "d2_track_count_mismatch",
                )
            )
            for reason in failures
        )
    )
    _put_available(row, "formal_acceptance_eligible", eligible)
    row["episode_failure_reasons_json"] = failures
    unavailable_reasons = sorted(
        {
            str(value)
            for key, value in row.items()
            if key.endswith("_unavailable_reason") and value is not None
        }
    )
    row["evidence_unavailability_reasons_json"] = unavailable_reasons
    row["episode_evidence_status"] = (
        "formal_provenance_ready" if eligible else "descriptive_or_incomplete_evidence"
    )


def _validate_provenance_consistency(
    row: dict[str, Any],
    manifest: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> None:
    for field in ("scenario_name", "scenario_version", "seed"):
        values = [
            value[field]
            for value in (manifest, config, summary)
            if isinstance(value, Mapping) and field in value and value[field] is not None
        ]
        if values and any(value != values[0] for value in values[1:]):
            row["_failure_reasons"].append(f"provenance_field_mismatch:{field}")
    for field in ("target_count", "resource_count", "recon_count"):
        values = [
            value[field]
            for value in (config, summary)
            if isinstance(value, Mapping) and field in value and value[field] is not None
        ]
        if values and any(value != values[0] for value in values[1:]):
            row["_failure_reasons"].append(f"provenance_field_mismatch:{field}")


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Scalable3DOfflineEvaluationError(f"invalid JSON object {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise Scalable3DOfflineEvaluationError(f"JSON artifact is not an object: {path}")
    return dict(value), None


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise Scalable3DOfflineEvaluationError(f"cannot read {path}: {exc}") from exc
    for line_number, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise Scalable3DOfflineEvaluationError(
                f"invalid JSONL {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(value, Mapping):
            raise Scalable3DOfflineEvaluationError(
                f"JSONL record is not an object: {path}:{line_number}"
            )
        records.append(dict(value))
    return records, None


def _load_stage_timings(
    path: Path,
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    records: dict[str, dict[str, Any]] = {}
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            for line_number, record in enumerate(csv.DictReader(stream), start=2):
                stage = str(record.get("stage", "")).strip()
                if not stage:
                    raise Scalable3DOfflineEvaluationError(
                        f"stage name missing at {path}:{line_number}"
                    )
                if stage in records:
                    raise Scalable3DOfflineEvaluationError(
                        f"duplicate stage {stage!r} in {path}"
                    )
                parsed: dict[str, Any] = {}
                for field, converter in (
                    ("call_count", int),
                    ("wall_time_s", float),
                    ("mean_wall_time_ms", float),
                ):
                    raw = record.get(field)
                    if raw in (None, ""):
                        parsed[field] = None
                        continue
                    try:
                        value = converter(raw)
                    except (TypeError, ValueError) as exc:
                        raise Scalable3DOfflineEvaluationError(
                            f"invalid {field} at {path}:{line_number}"
                        ) from exc
                    if not _is_finite_number(value) or value < 0:
                        raise Scalable3DOfflineEvaluationError(
                            f"nonfinite or negative {field} at {path}:{line_number}"
                        )
                    parsed[field] = value
                records[stage] = parsed
    except OSError as exc:
        raise Scalable3DOfflineEvaluationError(f"cannot read {path}: {exc}") from exc
    return records, None


def _ordered_online_records(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized = [dict(record) for record in records]
    return sorted(
        normalized,
        key=lambda record: (
            float(record["timestamp"])
            if _is_finite_number(record.get("timestamp"))
            else math.inf,
            int(record["sequence"])
            if _is_int_like(record.get("sequence"))
            else 2**63 - 1,
        ),
    )


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    return dict(value) if isinstance(value, Mapping) else {}


def _latest_topic(
    records: Sequence[Mapping[str, Any]], topic: str
) -> Mapping[str, Any] | None:
    for record in reversed(records):
        if record.get("topic") == topic:
            return record
    return None


def _count_forbidden_online_fields(value: Any) -> int:
    count = 0
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
                if (
                    normalized in _FORBIDDEN_ONLINE_KEYS
                    or normalized.startswith("truth_")
                    or normalized.endswith("_truth_id")
                    or normalized.endswith("_actor_id")
                ):
                    count += 1
                pending.append(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            pending.extend(item)
    return count


def _put_distribution(
    row: dict[str, Any],
    prefix: str,
    values: Sequence[float],
    *,
    unit_suffix: str,
) -> None:
    array = np.asarray(values, dtype=float)
    for label, value in (
        ("p50", np.percentile(array, 50.0)),
        ("p90", np.percentile(array, 90.0)),
        ("max", np.max(array)),
    ):
        _put_available(row, f"{prefix}_{label}{unit_suffix}", float(value))


def _put_available(row: dict[str, Any], field: str, value: Any) -> None:
    row[field] = _json_ready(value)
    row[f"{field}_availability"] = "available"
    row[f"{field}_unavailable_reason"] = None


def _put_unavailable(row: dict[str, Any], field: str, reason: str) -> None:
    row[field] = None
    row[f"{field}_availability"] = "unavailable"
    row[f"{field}_unavailable_reason"] = str(reason)


def _first_explicit_field(
    sources: Sequence[tuple[str, Mapping[str, Any] | None]], field: str
) -> tuple[Any, str | None, str | None]:
    for source, payload in sources:
        if payload is not None and field in payload and payload[field] is not None:
            return payload[field], source, None
    return None, None, f"explicit_field_missing:{field}"


def _aggregate_metric_names(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    dynamic = {
        key
        for row in rows
        for key in row
        if key.startswith("stage__")
        and not key.endswith(("_availability", "_unavailable_reason"))
    }
    return tuple(dict.fromkeys((*_METRIC_FIELDS, *sorted(dynamic))))


def _metric_statistics(
    rows: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    group_identity: Mapping[str, Any],
) -> dict[str, Any]:
    values: list[float] = []
    seed_values: dict[int, list[float]] = defaultdict(list)
    unavailable = Counter()
    for row in rows:
        value = row.get(metric)
        availability = row.get(f"{metric}_availability")
        if availability == "available" and _is_metric_number(value):
            numeric = float(int(value) if isinstance(value, bool) else value)
            values.append(numeric)
            if _is_int_like(row.get("seed")):
                seed_values[int(row["seed"])].append(numeric)
        else:
            reason = row.get(f"{metric}_unavailable_reason")
            unavailable[str(reason or "metric_unavailable_without_reason")] += 1
    if not values:
        return {
            "availability": "unavailable",
            "unavailable_reason": "no_available_episode_values",
            "unavailability_reason_distribution": dict(sorted(unavailable.items())),
            "episode_value_count": 0,
            "seed_value_count": 0,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "bootstrap_ci95_low": None,
            "bootstrap_ci95_high": None,
            "bootstrap_availability": "unavailable",
            "bootstrap_unavailable_reason": "no_available_episode_values",
        }
    array = np.asarray(values, dtype=float)
    seed_means = [float(np.mean(seed_values[seed])) for seed in sorted(seed_values)]
    if len(seed_means) >= 2:
        seed_material = json.dumps(
            {"group": group_identity, "metric": metric},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        offset = int.from_bytes(hashlib.sha256(seed_material).digest()[:4], "big")
        low, high = _bootstrap_mean_ci(
            seed_means,
            resamples=bootstrap_resamples,
            rng_seed=(int(bootstrap_rng_seed) + offset) % (2**32),
        )
        bootstrap_availability = "available"
        bootstrap_reason = None
    else:
        low = high = None
        bootstrap_availability = "unavailable"
        bootstrap_reason = "single_seed_descriptive_only"
    return {
        "availability": "available",
        "unavailable_reason": None,
        "unavailability_reason_distribution": dict(sorted(unavailable.items())),
        "episode_value_count": len(values),
        "seed_value_count": len(seed_means),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "standard_deviation_semantics": "descriptive_population_std",
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "bootstrap_ci95_low": low,
        "bootstrap_ci95_high": high,
        "bootstrap_availability": bootstrap_availability,
        "bootstrap_unavailable_reason": bootstrap_reason,
        "bootstrap_resamples": bootstrap_resamples,
        "bootstrap_rng_seed": bootstrap_rng_seed,
    }


def _bootstrap_mean_ci(
    values: Sequence[float], *, resamples: int, rng_seed: int
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(int(rng_seed))
    indices = rng.integers(0, len(array), size=(int(resamples), len(array)))
    means = np.mean(array[indices], axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _aggregate_stage_timing(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    group_identity: Mapping[str, Any],
) -> dict[str, Any]:
    stage_names = sorted(
        {
            stage
            for row in rows
            for stage in row.get("_stage_records", {})
        }
    )
    output: dict[str, Any] = {}
    pooled_total = sum(
        float(record.get("wall_time_s"))
        for row in rows
        for record in row.get("_stage_records", {}).values()
        if _is_finite_number(record.get("wall_time_s"))
    )
    for stage in stage_names:
        slug = _stage_slug(stage)
        prefix = f"stage__{slug}"
        shares: list[float] = []
        share_seed_values: dict[int, list[float]] = defaultdict(list)
        pooled_stage = 0.0
        for row in rows:
            stage_map = row.get("_stage_records", {})
            record = stage_map.get(stage) if isinstance(stage_map, Mapping) else None
            if isinstance(record, Mapping) and _is_finite_number(record.get("wall_time_s")):
                pooled_stage += float(record["wall_time_s"])
            episode_total = sum(
                float(item.get("wall_time_s"))
                for item in stage_map.values()
                if isinstance(item, Mapping) and _is_finite_number(item.get("wall_time_s"))
            )
            if (
                isinstance(record, Mapping)
                and _is_finite_number(record.get("wall_time_s"))
                and episode_total > 0.0
            ):
                share = float(record["wall_time_s"]) / episode_total
                shares.append(share)
                if _is_int_like(row.get("seed")):
                    share_seed_values[int(row["seed"])].append(share)
        share_stats = _plain_statistics(shares)
        seed_share_means = [
            float(np.mean(share_seed_values[seed])) for seed in sorted(share_seed_values)
        ]
        if len(seed_share_means) >= 2:
            material = json.dumps(
                {"group": group_identity, "stage": stage, "metric": "share"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            offset = int.from_bytes(hashlib.sha256(material).digest()[:4], "big")
            ci_low, ci_high = _bootstrap_mean_ci(
                seed_share_means,
                resamples=bootstrap_resamples,
                rng_seed=(bootstrap_rng_seed + offset) % (2**32),
            )
            ci_status = "available"
            ci_reason = None
        else:
            ci_low = ci_high = None
            ci_status = "unavailable"
            ci_reason = "single_seed_descriptive_only"
        output[stage] = {
            "call_count": _metric_statistics(
                rows,
                f"{prefix}__call_count",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity=group_identity,
            ),
            "wall_time_s": _metric_statistics(
                rows,
                f"{prefix}__wall_time_s",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity=group_identity,
            ),
            "mean_wall_time_ms": _metric_statistics(
                rows,
                f"{prefix}__mean_wall_time_ms",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                group_identity=group_identity,
            ),
            "pooled_wall_time_share": (
                pooled_stage / pooled_total if pooled_total > 0.0 else None
            ),
            "per_episode_wall_time_share": share_stats,
            "share_bootstrap_ci95_low": ci_low,
            "share_bootstrap_ci95_high": ci_high,
            "share_bootstrap_availability": ci_status,
            "share_bootstrap_unavailable_reason": ci_reason,
        }
    return output


def _aggregate_exact_seed_groups(
    rows: Sequence[Mapping[str, Any]], metric_names: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("seed")].append(row)
    output = []
    for seed in sorted(grouped, key=lambda value: (value is None, value)):
        seed_rows = grouped[seed]
        metrics = {}
        for metric in metric_names:
            values = [
                float(row[metric])
                for row in seed_rows
                if row.get(f"{metric}_availability") == "available"
                and _is_metric_number(row.get(metric))
            ]
            metrics[metric] = _plain_statistics(values)
        output.append(
            {
                "seed": seed,
                "episode_count": len(seed_rows),
                "inference_status": "descriptive_only",
                "metric_statistics": metrics,
            }
        )
    return output


def _plain_statistics(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "availability": "unavailable",
            "count": 0,
            "mean": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "availability": "available",
        "count": len(values),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
    }


def _write_stage_timing_curves(aggregate: Mapping[str, Any], path: Path) -> None:
    groups = list(aggregate.get("groups", []))
    labels = [
        f"T{group.get('target_count')}/R{group.get('resource_count')}\nRc{group.get('recon_count')}/C{group.get('camera_count')}"
        for group in groups
    ]
    stages = sorted(
        {
            stage
            for group in groups
            for stage in group.get("stage_timing", {})
        },
        key=lambda stage: -sum(
            float(group.get("stage_timing", {}).get(stage, {}).get("pooled_wall_time_share") or 0.0)
            for group in groups
        ),
    )[:8]
    figure, (time_axis, share_axis) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    x = np.arange(len(groups), dtype=float)
    colors = plt.get_cmap("tab10")
    for index, stage in enumerate(stages):
        mean_ms = [
            group.get("stage_timing", {})
            .get(stage, {})
            .get("mean_wall_time_ms", {})
            .get("mean")
            for group in groups
        ]
        shares = [
            group.get("stage_timing", {}).get(stage, {}).get("pooled_wall_time_share")
            for group in groups
        ]
        time_axis.plot(
            x,
            [np.nan if value is None else value for value in mean_ms],
            marker="o",
            linewidth=1.5,
            label=stage,
            color=colors(index % 10),
        )
        share_axis.plot(
            x,
            [np.nan if value is None else value for value in shares],
            marker="o",
            linewidth=1.5,
            label=stage,
            color=colors(index % 10),
        )
    if not groups:
        time_axis.text(0.5, 0.5, "No episode groups", ha="center", va="center")
        share_axis.text(0.5, 0.5, "No stage timing evidence", ha="center", va="center")
    time_axis.set_ylabel("Mean call time (ms)")
    time_axis.set_title("Scalable 3D stage timing by explicit scale")
    time_axis.grid(True, alpha=0.25)
    share_axis.set_ylabel("Pooled wall-time share")
    share_axis.set_xlabel("Explicit target/resource/recon/camera counts")
    share_axis.grid(True, alpha=0.25)
    share_axis.set_xticks(x, labels, rotation=0)
    if stages:
        time_axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
        share_axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    figure.tight_layout()
    figure.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(figure)


def _write_rows_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _counter_from_json_field(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(field)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            counter.update(str(item) for item in value)
    return dict(sorted(counter.items()))


def _counter_from_mapping_field(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(field)
        if isinstance(value, Mapping):
            for key, count in value.items():
                if _is_int_like(count):
                    counter[str(key)] += int(count)
    return dict(sorted(counter.items()))


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_ready(item) for item in value]
    return value


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return value


def _stage_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_") or "unnamed"


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(
        value, bool
    ) and math.isfinite(float(value))


def _is_metric_number(value: Any) -> bool:
    return isinstance(value, bool) or _is_finite_number(value)


def _is_int_like(value: Any) -> bool:
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool)


def _sortable_group_key(key: tuple[Any, ...]) -> tuple[Any, ...]:
    scenario_name, scenario_version, *counts = key
    return (
        "" if scenario_name is None else str(scenario_name),
        "" if scenario_version is None else str(scenario_version),
        *(
            (1, math.inf) if value is None else (0, float(value))
            for value in counts
        ),
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _fmt_available(row: Mapping[str, Any], field: str) -> str:
    if row.get(f"{field}_availability") != "available":
        reason = row.get(f"{field}_unavailable_reason")
        return f"unavailable({reason})"
    return _fmt(row.get(field))


def _fmt_stat(value: Any) -> str:
    if not isinstance(value, Mapping) or value.get("availability") != "available":
        return "unavailable"
    return _fmt(value.get("mean"))


__all__ = [
    "DEFAULT_SCALABLE_3D_BOOTSTRAP_RESAMPLES",
    "DEFAULT_SCALABLE_3D_BOOTSTRAP_RNG_SEED",
    "FIVE_METER_THRESHOLD_M",
    "SCALABLE_3D_OFFLINE_EVALUATION_DATE",
    "SCALABLE_3D_OFFLINE_EVALUATION_SCHEMA_VERSION",
    "Scalable3DOfflineEvaluationError",
    "Scalable3DOfflineEvaluationInputs",
    "Scalable3DOfflineReportGenerator",
    "aggregate_scalable_3d_episodes",
    "discover_scalable_3d_episode_dirs",
    "evaluate_scalable_3d_episode",
    "render_scalable_3d_offline_markdown",
]
