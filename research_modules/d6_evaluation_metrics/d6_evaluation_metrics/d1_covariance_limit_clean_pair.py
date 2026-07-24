"""Read-only admission audit for the D1 covariance pair-limit optimization.

The evaluator consumes explicitly paired, persisted scalable-3D episodes.  It
reuses the existing scalable-3D reader for provenance and stage timing, reads
GNU ``time -v`` resource records as an independent process layer, and never
imports D1 or writes to an online/control path.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import fmean
from typing import Any, Mapping, Sequence

from .scalable_3d_offline import evaluate_scalable_3d_episode


D1_COVARIANCE_LIMIT_CLEAN_PAIR_SCHEMA_VERSION = (
    "d6.d1-covariance-limit-clean-pair.v1"
)
D1_COVARIANCE_LIMIT_CLEAN_PAIR_EVALUATION_DATE = "2026-07-24"
D1_COVARIANCE_LIMIT_FUSION_STAGE = "module.d1_fusion"
D1_COVARIANCE_LIMIT_SCAN_INPUT_STAGE = "module.d1_scan_input"
D1_COVARIANCE_LIMIT_MINIMUM_FUSION_IMPROVEMENT_PCT = 5.0
D1_COVARIANCE_LIMIT_MAXIMUM_RSS_INCREASE_PCT = 5.0

_CROSS_BUILD_SCHEMA_VERSION = (
    "scalable3d-cross-build-semantic-equivalence-v1"
)
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_RESOURCE_PATTERNS = {
    "external_elapsed_s": re.compile(
        r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\):\s*(\S+)"
    ),
    "maximum_rss_kib": re.compile(
        r"Maximum resident set size \(kbytes\):\s*(\d+)"
    ),
    "process_exit_status": re.compile(r"Exit status:\s*(-?\d+)"),
}
_PERFORMANCE_METRICS = (
    "d1_fusion_wall_s",
    "d1_fusion_p95_ms",
    "d1_scan_input_wall_s",
    "core_wall_s",
    "external_elapsed_s",
    "maximum_rss_kib",
    "real_time_factor",
)
_REQUIRED_ARM_METRICS = (
    "d1_fusion_wall_s",
    "d1_fusion_p95_ms",
    "core_wall_s",
    "external_elapsed_s",
    "maximum_rss_kib",
    "real_time_factor",
    "process_exit_status",
)


@dataclass(frozen=True)
class D1CovarianceLimitCleanPairInput:
    """Explicit evidence binding for one reference/candidate replay pair."""

    round_id: str
    reference_episode_dir: Path
    candidate_episode_dir: Path
    cross_build_path: Path
    reference_resource_path: Path
    candidate_resource_path: Path

    def __post_init__(self) -> None:
        round_id = str(self.round_id).strip()
        if not round_id:
            raise ValueError("round_id must not be empty")
        object.__setattr__(self, "round_id", round_id)
        for field in (
            "reference_episode_dir",
            "candidate_episode_dir",
            "cross_build_path",
            "reference_resource_path",
            "candidate_resource_path",
        ):
            object.__setattr__(
                self,
                field,
                Path(getattr(self, field)).expanduser().resolve(),
            )


def evaluate_d1_covariance_limit_clean_pairs(
    pairs: Sequence[D1CovarianceLimitCleanPairInput],
    *,
    expected_reference_commit: str,
    expected_candidate_commit: str,
    expected_pair_count: int = 3,
    expected_observation_count: int | None = 2035,
    expected_target_count: int = 200,
    expected_resource_count: int = 200,
    expected_recon_count: int = 2,
    expected_duration_s: float = 2.2,
    minimum_fusion_improvement_pct: float = (
        D1_COVARIANCE_LIMIT_MINIMUM_FUSION_IMPROVEMENT_PCT
    ),
    maximum_rss_increase_pct: float = (
        D1_COVARIANCE_LIMIT_MAXIMUM_RSS_INCREASE_PCT
    ),
) -> dict[str, Any]:
    """Evaluate explicit clean pairs and return a fail-closed admission result."""

    reference_commit = _validated_commit(
        expected_reference_commit, "expected_reference_commit"
    )
    candidate_commit = _validated_commit(
        expected_candidate_commit, "expected_candidate_commit"
    )
    if expected_pair_count <= 0:
        raise ValueError("expected_pair_count must be positive")
    for name, value in (
        ("expected_target_count", expected_target_count),
        ("expected_resource_count", expected_resource_count),
        ("expected_recon_count", expected_recon_count),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if expected_observation_count is not None and (
        not isinstance(expected_observation_count, int)
        or isinstance(expected_observation_count, bool)
        or expected_observation_count < 0
    ):
        raise ValueError(
            "expected_observation_count must be a nonnegative integer or None"
        )
    if not math.isfinite(expected_duration_s) or expected_duration_s <= 0.0:
        raise ValueError("expected_duration_s must be finite and positive")
    if (
        not math.isfinite(minimum_fusion_improvement_pct)
        or minimum_fusion_improvement_pct < 0.0
    ):
        raise ValueError(
            "minimum_fusion_improvement_pct must be finite and nonnegative"
        )
    if (
        not math.isfinite(maximum_rss_increase_pct)
        or maximum_rss_increase_pct < 0.0
    ):
        raise ValueError(
            "maximum_rss_increase_pct must be finite and nonnegative"
        )

    evaluated_pairs = [
        evaluate_d1_covariance_limit_explicit_pair(
            pair,
            expected_reference_commit=reference_commit,
            expected_candidate_commit=candidate_commit,
            expected_observation_count=expected_observation_count,
            expected_target_count=expected_target_count,
            expected_resource_count=expected_resource_count,
            expected_recon_count=expected_recon_count,
            expected_duration_s=expected_duration_s,
        )
        for pair in pairs
    ]
    aggregate_metrics = {
        metric: _aggregate_pair_metric(evaluated_pairs, metric)
        for metric in _PERFORMANCE_METRICS
    }

    common_evidence_checks = _common_evidence_checks(
        evaluated_pairs,
        expected_pair_count=expected_pair_count,
    )
    all_arm_checks = [
        arm["checks"]
        for pair in evaluated_pairs
        for arm in (pair["reference"], pair["candidate"])
    ]
    fusion = aggregate_metrics["d1_fusion_wall_s"]
    fusion_p95 = aggregate_metrics["d1_fusion_p95_ms"]
    core = aggregate_metrics["core_wall_s"]
    rss = aggregate_metrics["maximum_rss_kib"]

    gates = {
        "explicit_pair_count": _gate(
            len(evaluated_pairs) == expected_pair_count,
            (
                None
                if len(evaluated_pairs) == expected_pair_count
                else (
                    f"expected_{expected_pair_count}_pairs_got_"
                    f"{len(evaluated_pairs)}"
                )
            ),
        ),
        "unique_round_ids": _gate_from_check(
            common_evidence_checks["unique_round_ids"]
        ),
        "common_frozen_input": _gate(
            all(
                common_evidence_checks[name]["passed"]
                for name in (
                    "common_seed",
                    "common_config_sha256",
                    "common_runtime_profile_sha256",
                    "common_scenario_version",
                    "common_scale",
                )
            ),
            "rounds_do_not_share_one_frozen_input",
        ),
        "business_semantics_all_pairs": _gate(
            bool(evaluated_pairs)
            and all(
                bool(pair["business_semantics_passed"])
                for pair in evaluated_pairs
            ),
            "one_or_more_pair_semantic_checks_failed",
        ),
        "finite_summary_all_arms": _gate(
            bool(all_arm_checks)
            and all(
                checks["summary_numeric_values_finite"]["passed"]
                and checks["finite_state_true"]["passed"]
                for checks in all_arm_checks
            ),
            "one_or_more_summary_finite_checks_failed",
        ),
        "online_truth_zero_all_arms": _gate(
            bool(all_arm_checks)
            and all(
                checks["online_truth_use_zero"]["passed"]
                for checks in all_arm_checks
            ),
            "one_or_more_online_truth_checks_failed",
        ),
        "process_exit_zero_all_arms": _gate(
            bool(all_arm_checks)
            and all(
                checks["process_exit_zero"]["passed"]
                for checks in all_arm_checks
            ),
            "one_or_more_process_exit_checks_failed",
        ),
        "required_metrics_available": _gate(
            bool(all_arm_checks)
            and all(
                checks["required_metrics_available"]["passed"]
                for checks in all_arm_checks
            ),
            "one_or_more_required_metrics_unavailable",
        ),
        "d1_fusion_three_of_three_faster": _gate(
            _available_aggregate(fusion)
            and fusion["candidate_lower_count"] == expected_pair_count,
            "candidate_d1_fusion_not_faster_in_every_pair",
        ),
        "d1_fusion_aggregate_improvement_at_least_threshold": _gate(
            _available_aggregate(fusion)
            and fusion["improvement_pct"]
            >= minimum_fusion_improvement_pct,
            (
                "candidate_d1_fusion_aggregate_improvement_below_"
                f"{minimum_fusion_improvement_pct:.6g}_pct"
            ),
        ),
        "d1_fusion_p95_aggregate_improved": _gate(
            _available_aggregate(fusion_p95)
            and fusion_p95["candidate_mean"]
            < fusion_p95["reference_mean"],
            "candidate_d1_fusion_p95_not_improved",
        ),
        "core_wall_non_degraded": _gate(
            _available_aggregate(core)
            and core["candidate_mean"] <= core["reference_mean"],
            "candidate_core_wall_mean_degraded",
        ),
        "core_wall_at_least_two_pairs_faster": _gate(
            _available_aggregate(core)
            and core["candidate_lower_count"] >= 2,
            "candidate_core_wall_faster_in_fewer_than_two_pairs",
        ),
        "rss_increase_within_limit": _gate(
            _available_aggregate(rss)
            and rss["relative_change_pct"] <= maximum_rss_increase_pct
            and rss["maximum_pair_relative_increase_pct"]
            <= maximum_rss_increase_pct,
            (
                "candidate_rss_increase_exceeds_"
                f"{maximum_rss_increase_pct:.6g}_pct"
            ),
        ),
    }
    d1_optimization_admitted = all(gate["passed"] for gate in gates.values())
    realtime = aggregate_metrics["real_time_factor"]
    distinct_seeds = sorted(
        {
            int(pair["reference"]["provenance"]["seed"])
            for pair in evaluated_pairs
            if isinstance(pair["reference"]["provenance"].get("seed"), int)
        }
    )
    system_realtime_reasons = [
        "three_dimensional_point_mass_not_airsim",
        "single_seed_repeated_three_times_not_multi_seed",
        "short_2_2_second_replay",
        "rmse_nees_nis_not_evaluated",
    ]
    if _available_aggregate(realtime) and realtime["candidate_mean"] < 1.0:
        system_realtime_reasons.append(
            "candidate_real_time_factor_below_one"
        )
    else:
        system_realtime_reasons.append(
            "system_realtime_capacity_not_established"
        )

    return {
        "schema_version": D1_COVARIANCE_LIMIT_CLEAN_PAIR_SCHEMA_VERSION,
        "evaluation_date": D1_COVARIANCE_LIMIT_CLEAN_PAIR_EVALUATION_DATE,
        "evaluation_role": "d6_independent_read_only_consumer",
        "control_path_participation": False,
        "online_truth_used_for_business": False,
        "scope": {
            "simulation_mode": "three_dimensional_point_mass",
            "airsim_evidence": False,
            "expected_pair_count": expected_pair_count,
            "observed_pair_count": len(evaluated_pairs),
            "distinct_seed_count": len(distinct_seeds),
            "seeds": distinct_seeds,
            "repeat_semantics": "same_seed_three_clean_interleaved_replays",
            "simulated_duration_s": expected_duration_s,
            "target_count": expected_target_count,
            "resource_count": expected_resource_count,
            "recon_count": expected_recon_count,
            "expected_observation_count": expected_observation_count,
            "reference_commit": reference_commit,
            "candidate_commit": candidate_commit,
            "external_elapsed_and_core_wall_are_not_summed": True,
            "d2_d3_d7_stage_fluctuation_attributed_to_d1": False,
        },
        "thresholds": {
            "minimum_d1_fusion_improvement_pct": (
                minimum_fusion_improvement_pct
            ),
            "maximum_rss_increase_pct": maximum_rss_increase_pct,
        },
        "pairs": evaluated_pairs,
        "common_evidence_checks": common_evidence_checks,
        "aggregate_metrics": aggregate_metrics,
        "admission_gates": gates,
        "d1_optimization_admitted": d1_optimization_admitted,
        "system_realtime_gap_closed": False,
        "system_realtime_gap_reasons": system_realtime_reasons,
        "not_evaluated": {
            "multi_seed_generalization": "unavailable_single_seed",
            "airsim_runtime": "not_applicable_point_mass_input",
            "rmse": "unavailable_not_in_admission_input",
            "nees": "unavailable_not_in_admission_input",
            "nis": "unavailable_not_in_admission_input",
        },
    }


def write_d1_covariance_limit_clean_pair_report(
    result: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write machine JSON, per-round CSV, and a Chinese Markdown report."""

    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "d1_covariance_limit_clean_pair_evaluation.json"
    csv_path = directory / "d1_covariance_limit_clean_pair_rounds.csv"
    markdown_path = (
        directory / "D1_COVARIANCE_LIMIT_CLEAN_PAIR_EVALUATION_CN.md"
    )
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_pair_csv(result, csv_path)
    markdown_path.write_text(
        render_d1_covariance_limit_clean_pair_markdown(result),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
    }


def render_d1_covariance_limit_clean_pair_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render a concise Chinese admission report from an evaluated result."""

    admitted = bool(result.get("d1_optimization_admitted"))
    realtime_closed = bool(result.get("system_realtime_gap_closed"))
    metrics = result.get("aggregate_metrics", {})
    lines = [
        "# D1 协方差成对限制向量化准入评估",
        "",
        "## 结论",
        "",
        (
            f"D1 优化准入结论为 **{'通过' if admitted else '不通过'}**。"
            "评估只读取三轮已写盘证据，不参与控制，也不使用离线真值改变业务结果。"
        ),
        (
            "系统实时性缺口"
            f" **{'已关闭' if realtime_closed else '未关闭'}**。"
            "本批是 200 对 200 三维质点、seed 1100 的三次交错 clean 回放，"
            "每次世界时间 2.2 秒；它不是多 seed、AirSim 或实机容量试验。"
        ),
        "",
        "## 聚合结果",
        "",
        "| 指标 | 参考均值 | 候选均值 | 变化 | 候选值更低轮次 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for metric, label, unit in (
        ("d1_fusion_wall_s", "D1 融合累计墙钟", "s"),
        ("d1_fusion_p95_ms", "D1 融合单次 P95", "ms"),
        ("core_wall_s", "核心 episode 墙钟", "s"),
        ("external_elapsed_s", "外部进程 elapsed", "s"),
        ("maximum_rss_kib", "最大常驻内存", "KiB"),
        ("real_time_factor", "实时因子", ""),
        ("d1_scan_input_wall_s", "D1 扫描输入累计墙钟", "s"),
    ):
        aggregate = metrics.get(metric, {})
        if aggregate.get("availability") != "available":
            reason = aggregate.get("reason") or "unavailable"
            lines.append(
                f"| {label} | unavailable | unavailable | {reason} | - |"
            )
            continue
        suffix = f" {unit}" if unit else ""
        lines.append(
            "| "
            f"{label} | {_fmt(aggregate['reference_mean'])}{suffix} | "
            f"{_fmt(aggregate['candidate_mean'])}{suffix} | "
            f"{_fmt(aggregate['relative_change_pct'])}% | "
            f"{aggregate['candidate_lower_count']}/"
            f"{aggregate['pair_count']} |"
        )
    lines.extend(
        [
            "",
            "变化按 `(候选-参考)/参考` 计算，负值表示耗时或内存下降。"
            "D1 融合 P95 是三轮 episode 内 P95 的算术均值，不是跨轮样本池的重新分位数。"
            "核心墙钟与外部进程 elapsed 分层报告，二者没有相加。",
            "",
            "D1 扫描输入是独立阶段，只作描述性核对，不进入协方差成对限制优化准入门。"
            "D2、D3、D7 的单 seed 调度波动也未归因于 D1 算法。",
            "",
            "## 逐轮结果",
            "",
            "| 轮次 | 语义 | D1 融合 s | D1 P95 ms | 核心墙钟 s | 外部 elapsed s | RSS KiB |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for pair in result.get("pairs", []):
        lines.append(
            "| "
            f"{pair.get('round_id', '-')} | "
            f"{'通过' if pair.get('business_semantics_passed') else '失败'} | "
            f"{_pair_values(pair, 'd1_fusion_wall_s')} | "
            f"{_pair_values(pair, 'd1_fusion_p95_ms')} | "
            f"{_pair_values(pair, 'core_wall_s')} | "
            f"{_pair_values(pair, 'external_elapsed_s')} | "
            f"{_pair_values(pair, 'maximum_rss_kib')} |"
        )
    lines.extend(
        [
            "",
            "每个数值单元按“参考 / 候选”排列。",
            "",
            "## 准入门",
            "",
            "| 判据 | 结果 | 原因 |",
            "| --- | --- | --- |",
        ]
    )
    for name, gate in result.get("admission_gates", {}).items():
        lines.append(
            f"| `{name}` | {'通过' if gate.get('passed') else '失败'} | "
            f"{gate.get('reason') or '-'} |"
        )
    lines.extend(
        [
            "",
            "三轮均要求 manifest 为 clean、提交绑定正确、场景配置、seed 和运行配置一致，"
            "summary 数值有限，在线真值使用计数为零，观测数为 2035，进程退出码为零。"
            "cross-build 必须整体通过且规范化在线载荷逐条一致。",
            "",
            "## 证据边界",
            "",
            "- 本批只有 seed 1100 的三次重复，不能估计跨 seed 稳定性。",
            "- 世界时间只有 2.2 秒，候选实时因子仍低于 1，不能关闭系统实时容量缺口。",
            "- 本批没有 AirSim、均方根误差、归一化估计误差平方或归一化创新平方证据。",
            "- 准入仅说明当前冻结输入下的 D1 性能优化满足门限，不代表跟踪精度或拦截效果提升。",
            "",
            "## 文件",
            "",
            "- `d1_covariance_limit_clean_pair_evaluation.json`：完整机器判据和 availability。",
            "- `d1_covariance_limit_clean_pair_rounds.csv`：逐轮参考/候选指标。",
            "- `D1_COVARIANCE_LIMIT_CLEAN_PAIR_EVALUATION_CN.md`：本报告。",
            "",
        ]
    )
    return "\n".join(lines)


def evaluate_d1_covariance_limit_explicit_pair(
    pair: D1CovarianceLimitCleanPairInput,
    *,
    expected_reference_commit: str,
    expected_candidate_commit: str,
    expected_observation_count: int | None,
    expected_target_count: int,
    expected_resource_count: int,
    expected_recon_count: int,
    expected_duration_s: float,
) -> dict[str, Any]:
    reference = _evaluate_arm(
        pair.reference_episode_dir,
        pair.reference_resource_path,
        expected_commit=expected_reference_commit,
        expected_observation_count=expected_observation_count,
        expected_target_count=expected_target_count,
        expected_resource_count=expected_resource_count,
        expected_recon_count=expected_recon_count,
        expected_duration_s=expected_duration_s,
    )
    candidate = _evaluate_arm(
        pair.candidate_episode_dir,
        pair.candidate_resource_path,
        expected_commit=expected_candidate_commit,
        expected_observation_count=expected_observation_count,
        expected_target_count=expected_target_count,
        expected_resource_count=expected_resource_count,
        expected_recon_count=expected_recon_count,
        expected_duration_s=expected_duration_s,
    )
    cross, cross_reason = _load_json_object(pair.cross_build_path)
    cross_checks = _cross_build_checks(
        cross,
        cross_reason=cross_reason,
        pair=pair,
        reference=reference,
        candidate=candidate,
        expected_reference_commit=expected_reference_commit,
        expected_candidate_commit=expected_candidate_commit,
    )
    pair_checks = {
        "same_config_sha256": _same_provenance_check(
            reference, candidate, "config_sha256"
        ),
        "same_seed": _same_provenance_check(reference, candidate, "seed"),
        "same_runtime_profile_sha256": _same_provenance_check(
            reference, candidate, "runtime_profile_sha256"
        ),
        "same_scenario_version": _same_provenance_check(
            reference, candidate, "scenario_version"
        ),
        "same_scale": _gate(
            all(
                reference["provenance"].get(field)
                == candidate["provenance"].get(field)
                for field in ("target_count", "resource_count", "recon_count")
            ),
            "reference_candidate_scale_mismatch",
        ),
        "same_duration": _same_provenance_check(
            reference, candidate, "simulated_duration_s"
        ),
        "same_online_observation_count": _same_metric_check(
            reference, candidate, "online_observation_count"
        ),
    }
    business_semantics_passed = (
        bool(reference["arm_evidence_valid"])
        and bool(candidate["arm_evidence_valid"])
        and all(check["passed"] for check in pair_checks.values())
        and all(check["passed"] for check in cross_checks.values())
    )
    performance = {
        metric: _compare_pair_metric(reference, candidate, metric)
        for metric in _PERFORMANCE_METRICS
    }
    return {
        "round_id": pair.round_id,
        "input_binding": {
            "reference_episode_dir": str(pair.reference_episode_dir),
            "candidate_episode_dir": str(pair.candidate_episode_dir),
            "cross_build_path": str(pair.cross_build_path),
            "reference_resource_path": str(pair.reference_resource_path),
            "candidate_resource_path": str(pair.candidate_resource_path),
        },
        "reference": reference,
        "candidate": candidate,
        "pair_checks": pair_checks,
        "cross_build_checks": cross_checks,
        "business_semantics_passed": business_semantics_passed,
        "performance": performance,
    }


def _evaluate_arm(
    episode_dir: Path,
    resource_path: Path,
    *,
    expected_commit: str,
    expected_observation_count: int | None,
    expected_target_count: int,
    expected_resource_count: int,
    expected_recon_count: int,
    expected_duration_s: float,
) -> dict[str, Any]:
    manifest, manifest_reason = _load_json_object(episode_dir / "manifest.json")
    config, config_reason = _load_json_object(
        episode_dir / "scenario_config.json"
    )
    summary, summary_reason = _load_json_object(episode_dir / "summary.json")
    evaluator_row: Mapping[str, Any] = {}
    evaluator_reason: str | None = None
    try:
        evaluator_row = evaluate_scalable_3d_episode(episode_dir)
    except (OSError, ValueError) as exc:
        evaluator_reason = f"scalable_3d_reader_failed:{type(exc).__name__}:{exc}"

    metrics = {
        "d1_fusion_wall_s": _evaluator_metric(
            evaluator_row,
            "stage__module_d1_fusion__wall_time_s",
            evaluator_reason,
        ),
        "d1_fusion_p95_ms": _evaluator_metric(
            evaluator_row,
            "stage__module_d1_fusion__p95_wall_time_ms",
            evaluator_reason,
        ),
        "d1_fusion_call_count": _evaluator_metric(
            evaluator_row,
            "stage__module_d1_fusion__call_count",
            evaluator_reason,
        ),
        "d1_scan_input_wall_s": _evaluator_metric(
            evaluator_row,
            "stage__module_d1_scan_input__wall_time_s",
            evaluator_reason,
        ),
        "core_wall_s": _mapping_number_metric(
            summary, "wall_time_s", summary_reason
        ),
        "real_time_factor": _mapping_number_metric(
            summary, "real_time_factor", summary_reason
        ),
        "online_observation_count": _mapping_integer_metric(
            summary, "online_observation_count", summary_reason
        ),
        "online_truth_use_count": _mapping_integer_metric(
            summary, "online_truth_use_count", summary_reason
        ),
    }
    resource_metrics = _load_resource_metrics(resource_path)
    metrics.update(resource_metrics)

    provenance = {
        "git_commit": _mapping_value(manifest, "git_commit"),
        "repository_dirty": _mapping_value(
            manifest, "repository_dirty"
        ),
        "config_sha256": _mapping_value(manifest, "config_sha256"),
        "runtime_profile_sha256": _mapping_value(
            manifest, "runtime_profile_sha256"
        ),
        "normalized_config_excluding_seed_duration_sha256": (
            _normalized_config_sha256(config)
        ),
        "d1_d2_structural_ambiguity_hold_enabled": (
            _runtime_profile_flag(
                manifest,
                "d1_d2_structural_ambiguity_hold_enabled",
            )
        ),
        "scenario_name": _mapping_value(manifest, "scenario_name"),
        "scenario_version": _mapping_value(
            manifest, "scenario_version"
        ),
        "seed": _mapping_value(manifest, "seed"),
        "target_count": _first_mapping_value(
            config, summary, "target_count"
        ),
        "resource_count": _first_mapping_value(
            config, summary, "resource_count"
        ),
        "recon_count": _first_mapping_value(
            config, summary, "recon_count"
        ),
        "simulated_duration_s": _first_mapping_value(
            summary, config, "simulated_duration_s", fallback_key="duration_s"
        ),
    }
    computed_config_sha256 = (
        _canonical_sha256(config) if config is not None else None
    )
    computed_runtime_profile_sha256 = None
    if manifest is not None and isinstance(
        manifest.get("runtime_profile"), Mapping
    ):
        computed_runtime_profile_sha256 = _canonical_sha256(
            manifest["runtime_profile"]
        )

    checks = {
        "manifest_available": _gate(
            manifest is not None,
            manifest_reason or "manifest_unavailable",
        ),
        "scenario_config_available": _gate(
            config is not None,
            config_reason or "scenario_config_unavailable",
        ),
        "summary_available": _gate(
            summary is not None,
            summary_reason or "summary_unavailable",
        ),
        "manifest_clean": _gate(
            provenance["repository_dirty"] is False,
            "repository_dirty_not_false",
        ),
        "commit_matches_expected": _gate(
            provenance["git_commit"] == expected_commit,
            "git_commit_mismatch",
        ),
        "config_hash_valid": _gate(
            computed_config_sha256 is not None
            and provenance["config_sha256"] == computed_config_sha256,
            "config_sha256_mismatch_or_unavailable",
        ),
        "runtime_profile_hash_valid": _gate(
            computed_runtime_profile_sha256 is not None
            and provenance["runtime_profile_sha256"]
            == computed_runtime_profile_sha256,
            "runtime_profile_sha256_mismatch_or_unavailable",
        ),
        "summary_numeric_values_finite": _gate(
            summary is not None and _all_numeric_values_finite(summary),
            "summary_contains_nonfinite_value_or_is_unavailable",
        ),
        "finite_state_true": _gate(
            summary is not None and summary.get("finite_state") is True,
            "summary_finite_state_not_true",
        ),
        "online_truth_use_zero": _gate(
            _metric_equals(metrics["online_truth_use_count"], 0),
            "online_truth_use_count_not_zero_or_unavailable",
        ),
        "observation_count_matches_expected": (
            _gate(
                metrics["online_observation_count"]["availability"]
                == "available",
                "online_observation_count_unavailable",
            )
            if expected_observation_count is None
            else _gate(
                _metric_equals(
                    metrics["online_observation_count"],
                    expected_observation_count,
                ),
                (
                    "online_observation_count_not_"
                    f"{expected_observation_count}_or_unavailable"
                ),
            )
        ),
        "scale_matches_expected": _gate(
            provenance["target_count"] == expected_target_count
            and provenance["resource_count"] == expected_resource_count
            and provenance["recon_count"] == expected_recon_count,
            "target_resource_or_recon_count_mismatch",
        ),
        "duration_matches_expected": _gate(
            _finite_close(
                provenance["simulated_duration_s"], expected_duration_s
            ),
            "simulated_duration_mismatch",
        ),
        "process_exit_zero": _gate(
            _metric_equals(metrics["process_exit_status"], 0),
            "process_exit_status_not_zero_or_unavailable",
        ),
        "required_metrics_available": _gate(
            all(
                metrics[name]["availability"] == "available"
                for name in _REQUIRED_ARM_METRICS
            ),
            "required_performance_metric_unavailable",
        ),
    }
    return {
        "episode_dir": str(episode_dir),
        "resource_path": str(resource_path),
        "provenance": provenance,
        "metrics": metrics,
        "checks": checks,
        "arm_evidence_valid": all(check["passed"] for check in checks.values()),
    }


def _cross_build_checks(
    cross: Mapping[str, Any] | None,
    *,
    cross_reason: str | None,
    pair: D1CovarianceLimitCleanPairInput,
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    expected_reference_commit: str,
    expected_candidate_commit: str,
) -> dict[str, dict[str, Any]]:
    reference_cross = (
        cross.get("reference")
        if isinstance(cross, Mapping)
        and isinstance(cross.get("reference"), Mapping)
        else {}
    )
    candidate_cross = (
        cross.get("candidate")
        if isinstance(cross, Mapping)
        and isinstance(cross.get("candidate"), Mapping)
        else {}
    )
    checks = (
        cross.get("checks")
        if isinstance(cross, Mapping)
        and isinstance(cross.get("checks"), Mapping)
        else {}
    )
    online_bus = (
        cross.get("online_bus")
        if isinstance(cross, Mapping)
        and isinstance(cross.get("online_bus"), Mapping)
        else {}
    )
    all_declared_checks_true = bool(checks) and all(
        value is True for value in checks.values()
    )
    return {
        "cross_build_available": _gate(
            cross is not None,
            cross_reason or "cross_build_unavailable",
        ),
        "schema_supported": _gate(
            cross is not None
            and cross.get("schema_version") == _CROSS_BUILD_SCHEMA_VERSION,
            "cross_build_schema_mismatch",
        ),
        "cross_build_passed": _gate(
            cross is not None and cross.get("passed") is True,
            "cross_build_passed_not_true",
        ),
        "all_declared_cross_checks_true": _gate(
            all_declared_checks_true,
            "one_or_more_declared_cross_checks_not_true",
        ),
        "normalized_online_payloads_equal": _gate(
            checks.get("normalized_online_payloads_equal") is True
            and online_bus.get("normalized_online_payloads_equal") is True,
            "normalized_online_payloads_not_equal",
        ),
        "source_clean": _gate(
            checks.get("reference_source_clean") is True
            and checks.get("candidate_source_clean") is True
            and reference_cross.get("repository_dirty") is False
            and candidate_cross.get("repository_dirty") is False,
            "cross_build_source_clean_check_failed",
        ),
        "commit_binding": _gate(
            reference_cross.get("git_commit") == expected_reference_commit
            and candidate_cross.get("git_commit")
            == expected_candidate_commit,
            "cross_build_commit_binding_mismatch",
        ),
        "episode_path_binding": _gate(
            _resolved_path_equal(
                reference_cross.get("episode_dir"),
                pair.reference_episode_dir,
            )
            and _resolved_path_equal(
                candidate_cross.get("episode_dir"),
                pair.candidate_episode_dir,
            ),
            "cross_build_episode_path_binding_mismatch",
        ),
        "provenance_binding": _gate(
            reference_cross.get("seed")
            == reference["provenance"].get("seed")
            and candidate_cross.get("seed")
            == candidate["provenance"].get("seed")
            and reference_cross.get("runtime_profile_sha256")
            == reference["provenance"].get("runtime_profile_sha256")
            and candidate_cross.get("runtime_profile_sha256")
            == candidate["provenance"].get("runtime_profile_sha256")
            and reference_cross.get("scenario_version")
            == reference["provenance"].get("scenario_version")
            and candidate_cross.get("scenario_version")
            == candidate["provenance"].get("scenario_version"),
            "cross_build_provenance_binding_mismatch",
        ),
    }


def _common_evidence_checks(
    pairs: Sequence[Mapping[str, Any]],
    *,
    expected_pair_count: int,
) -> dict[str, dict[str, Any]]:
    round_ids = [str(pair.get("round_id", "")) for pair in pairs]
    checks = {
        "unique_round_ids": _gate(
            len(round_ids) == len(set(round_ids)),
            "duplicate_round_id",
        )
    }
    for check_name, field in (
        ("common_seed", "seed"),
        ("common_config_sha256", "config_sha256"),
        ("common_runtime_profile_sha256", "runtime_profile_sha256"),
        ("common_scenario_version", "scenario_version"),
    ):
        values = [
            arm["provenance"].get(field)
            for pair in pairs
            for arm in (pair["reference"], pair["candidate"])
        ]
        checks[check_name] = _gate(
            len(pairs) == expected_pair_count
            and bool(values)
            and all(value is not None for value in values)
            and len(set(values)) == 1,
            f"{field}_not_common_across_all_arms",
        )
    scales = [
        (
            arm["provenance"].get("target_count"),
            arm["provenance"].get("resource_count"),
            arm["provenance"].get("recon_count"),
        )
        for pair in pairs
        for arm in (pair["reference"], pair["candidate"])
    ]
    checks["common_scale"] = _gate(
        len(pairs) == expected_pair_count
        and bool(scales)
        and all(None not in scale for scale in scales)
        and len(set(scales)) == 1,
        "scale_not_common_across_all_arms",
    )
    return checks


def _compare_pair_metric(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    metric: str,
) -> dict[str, Any]:
    reference_metric = reference["metrics"][metric]
    candidate_metric = candidate["metrics"][metric]
    if (
        reference_metric["availability"] != "available"
        or candidate_metric["availability"] != "available"
    ):
        reasons = [
            str(item.get("reason"))
            for item in (reference_metric, candidate_metric)
            if item.get("availability") != "available"
        ]
        return {
            "availability": "unavailable",
            "reason": ";".join(reasons) or "pair_metric_unavailable",
            "reference": reference_metric.get("value"),
            "candidate": candidate_metric.get("value"),
            "delta_candidate_minus_reference": None,
            "relative_change_pct": None,
            "candidate_lower": None,
        }
    reference_value = float(reference_metric["value"])
    candidate_value = float(candidate_metric["value"])
    relative_change = (
        (candidate_value - reference_value) / reference_value * 100.0
        if reference_value != 0.0
        else None
    )
    return {
        "availability": "available",
        "reason": None,
        "reference": reference_metric["value"],
        "candidate": candidate_metric["value"],
        "delta_candidate_minus_reference": candidate_value - reference_value,
        "relative_change_pct": relative_change,
        "candidate_lower": candidate_value < reference_value,
    }


def _aggregate_pair_metric(
    pairs: Sequence[Mapping[str, Any]],
    metric: str,
) -> dict[str, Any]:
    comparisons = [pair["performance"][metric] for pair in pairs]
    unavailable = [
        str(comparison.get("reason") or "pair_metric_unavailable")
        for comparison in comparisons
        if comparison.get("availability") != "available"
    ]
    if not comparisons or unavailable:
        return {
            "availability": "unavailable",
            "reason": ";".join(unavailable) or "no_pair_metric_samples",
            "pair_count": len(comparisons),
            "reference_mean": None,
            "candidate_mean": None,
            "delta_candidate_minus_reference": None,
            "relative_change_pct": None,
            "improvement_pct": None,
            "candidate_lower_count": None,
            "maximum_pair_relative_increase_pct": None,
        }
    reference_values = [float(item["reference"]) for item in comparisons]
    candidate_values = [float(item["candidate"]) for item in comparisons]
    reference_mean = fmean(reference_values)
    candidate_mean = fmean(candidate_values)
    relative_change = (
        (candidate_mean - reference_mean) / reference_mean * 100.0
        if reference_mean != 0.0
        else None
    )
    pair_relative_changes = [
        float(item["relative_change_pct"])
        for item in comparisons
        if item["relative_change_pct"] is not None
    ]
    return {
        "availability": "available",
        "reason": None,
        "pair_count": len(comparisons),
        "reference_mean": reference_mean,
        "candidate_mean": candidate_mean,
        "delta_candidate_minus_reference": candidate_mean - reference_mean,
        "relative_change_pct": relative_change,
        "improvement_pct": (
            -relative_change if relative_change is not None else None
        ),
        "candidate_lower_count": sum(
            bool(item["candidate_lower"]) for item in comparisons
        ),
        "maximum_pair_relative_increase_pct": (
            max(pair_relative_changes) if pair_relative_changes else None
        ),
    }


def _load_resource_metrics(path: Path) -> dict[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        reason = f"resource_file_unavailable:{type(exc).__name__}"
        return {
            name: _unavailable(reason) for name in _RESOURCE_PATTERNS
        }
    metrics: dict[str, dict[str, Any]] = {}
    for name, pattern in _RESOURCE_PATTERNS.items():
        match = pattern.search(text)
        if match is None:
            metrics[name] = _unavailable(
                f"resource_field_missing:{name}"
            )
            continue
        raw = match.group(1)
        try:
            if name == "external_elapsed_s":
                value: float | int = _parse_elapsed_seconds(raw)
            else:
                value = int(raw)
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("nonfinite resource value")
            if value < 0:
                raise ValueError("negative resource value")
        except ValueError:
            metrics[name] = _unavailable(
                f"resource_field_invalid:{name}:{raw}"
            )
        else:
            metrics[name] = _available(value)
    return metrics


def _parse_elapsed_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1])
        hours = 0
    elif len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    else:
        seconds = float(parts[0])
        hours = 0
        minutes = 0
    if hours < 0 or minutes < 0 or seconds < 0.0 or seconds >= 60.0:
        raise ValueError("invalid elapsed time")
    return hours * 3600.0 + minutes * 60.0 + seconds


def _evaluator_metric(
    row: Mapping[str, Any],
    field: str,
    evaluator_reason: str | None,
) -> dict[str, Any]:
    if evaluator_reason is not None:
        return _unavailable(evaluator_reason)
    if row.get(f"{field}_availability") != "available":
        return _unavailable(
            str(
                row.get(f"{field}_unavailable_reason")
                or f"evaluator_field_unavailable:{field}"
            )
        )
    value = row.get(field)
    if not _is_finite_number(value) or float(value) < 0.0:
        return _unavailable(f"evaluator_field_invalid:{field}")
    return _available(value)


def _mapping_number_metric(
    mapping: Mapping[str, Any] | None,
    field: str,
    mapping_reason: str | None,
) -> dict[str, Any]:
    if mapping is None:
        return _unavailable(mapping_reason or f"mapping_unavailable:{field}")
    value = mapping.get(field)
    if not _is_finite_number(value) or float(value) < 0.0:
        return _unavailable(f"field_invalid_or_missing:{field}")
    return _available(float(value))


def _mapping_integer_metric(
    mapping: Mapping[str, Any] | None,
    field: str,
    mapping_reason: str | None,
) -> dict[str, Any]:
    if mapping is None:
        return _unavailable(mapping_reason or f"mapping_unavailable:{field}")
    value = mapping.get(field)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        return _unavailable(f"field_invalid_or_missing:{field}")
    return _available(value)


def _same_provenance_check(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    field: str,
) -> dict[str, Any]:
    reference_value = reference["provenance"].get(field)
    candidate_value = candidate["provenance"].get(field)
    return _gate(
        reference_value is not None
        and candidate_value is not None
        and reference_value == candidate_value,
        f"reference_candidate_{field}_mismatch_or_unavailable",
    )


def _same_metric_check(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    field: str,
) -> dict[str, Any]:
    reference_metric = reference["metrics"].get(field, {})
    candidate_metric = candidate["metrics"].get(field, {})
    return _gate(
        reference_metric.get("availability") == "available"
        and candidate_metric.get("availability") == "available"
        and reference_metric.get("value") == candidate_metric.get("value"),
        f"reference_candidate_{field}_mismatch_or_unavailable",
    )


def _write_pair_csv(
    result: Mapping[str, Any],
    path: Path,
) -> None:
    fieldnames = [
        "round_id",
        "business_semantics_passed",
        "arm",
        "episode_dir",
        "git_commit",
        "seed",
        "config_sha256",
        "runtime_profile_sha256",
        "d1_fusion_wall_s",
        "d1_fusion_p95_ms",
        "d1_scan_input_wall_s",
        "core_wall_s",
        "external_elapsed_s",
        "maximum_rss_kib",
        "real_time_factor",
        "online_observation_count",
        "online_truth_use_count",
        "process_exit_status",
        "arm_evidence_valid",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for pair in result.get("pairs", []):
            for arm_name in ("reference", "candidate"):
                arm = pair[arm_name]
                metrics = arm["metrics"]
                provenance = arm["provenance"]
                writer.writerow(
                    {
                        "round_id": pair["round_id"],
                        "business_semantics_passed": (
                            pair["business_semantics_passed"]
                        ),
                        "arm": arm_name,
                        "episode_dir": arm["episode_dir"],
                        "git_commit": provenance.get("git_commit"),
                        "seed": provenance.get("seed"),
                        "config_sha256": provenance.get("config_sha256"),
                        "runtime_profile_sha256": provenance.get(
                            "runtime_profile_sha256"
                        ),
                        **{
                            name: metrics[name].get("value")
                            for name in (
                                "d1_fusion_wall_s",
                                "d1_fusion_p95_ms",
                                "d1_scan_input_wall_s",
                                "core_wall_s",
                                "external_elapsed_s",
                                "maximum_rss_kib",
                                "real_time_factor",
                                "online_observation_count",
                                "online_truth_use_count",
                                "process_exit_status",
                            )
                        },
                        "arm_evidence_valid": arm["arm_evidence_valid"],
                    }
                )


def _load_json_object(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"invalid_json:{path.name}:{type(exc).__name__}"
    if not isinstance(value, Mapping):
        return None, f"json_not_object:{path.name}"
    return dict(value), None


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_config_sha256(
    config: Mapping[str, Any] | None,
) -> str | None:
    if config is None:
        return None
    normalized = {
        key: value
        for key, value in config.items()
        if key not in {"seed", "duration_s"}
    }
    return _canonical_sha256(normalized)


def _runtime_profile_flag(
    manifest: Mapping[str, Any] | None,
    field: str,
) -> Any:
    if manifest is None:
        return None
    runtime_profile = manifest.get("runtime_profile")
    if not isinstance(runtime_profile, Mapping):
        return None
    configuration = runtime_profile.get("configuration")
    if not isinstance(configuration, Mapping):
        return None
    return configuration.get(field)


def _all_numeric_values_finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, Mapping):
        return all(_all_numeric_values_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_all_numeric_values_finite(item) for item in value)
    return True


def _mapping_value(
    mapping: Mapping[str, Any] | None,
    field: str,
) -> Any:
    return mapping.get(field) if mapping is not None else None


def _first_mapping_value(
    first: Mapping[str, Any] | None,
    second: Mapping[str, Any] | None,
    field: str,
    *,
    fallback_key: str | None = None,
) -> Any:
    for mapping in (first, second):
        if mapping is None:
            continue
        if field in mapping:
            return mapping[field]
        if fallback_key is not None and fallback_key in mapping:
            return mapping[fallback_key]
    return None


def _available(value: Any) -> dict[str, Any]:
    return {"availability": "available", "value": value, "reason": None}


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "value": None,
        "reason": str(reason),
    }


def _gate(passed: bool, reason: str | None) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "reason": None if passed else str(reason or "gate_failed"),
    }


def _gate_from_check(check: Mapping[str, Any]) -> dict[str, Any]:
    return _gate(bool(check.get("passed")), check.get("reason"))


def _metric_equals(metric: Mapping[str, Any], expected: Any) -> bool:
    return (
        metric.get("availability") == "available"
        and metric.get("value") == expected
    )


def _finite_close(value: Any, expected: float) -> bool:
    return (
        _is_finite_number(value)
        and math.isclose(
            float(value),
            float(expected),
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    )


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _resolved_path_equal(value: Any, expected: Path) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return Path(value).expanduser().resolve() == expected


def _available_aggregate(value: Mapping[str, Any]) -> bool:
    return value.get("availability") == "available"


def _validated_commit(value: str, field: str) -> str:
    normalized = str(value).strip().lower()
    if not _GIT_COMMIT_RE.fullmatch(normalized):
        raise ValueError(f"{field} must be a 40-character hexadecimal commit")
    return normalized


def _fmt(value: Any) -> str:
    if not _is_finite_number(value):
        return "unavailable"
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _pair_values(pair: Mapping[str, Any], metric: str) -> str:
    values = []
    for arm_name in ("reference", "candidate"):
        item = pair[arm_name]["metrics"][metric]
        values.append(
            _fmt(item.get("value"))
            if item.get("availability") == "available"
            else "unavailable"
        )
    return " / ".join(values)


def _parse_pair_argument(values: Sequence[str]) -> D1CovarianceLimitCleanPairInput:
    if len(values) != 6:
        raise ValueError("--pair requires exactly 6 values")
    return D1CovarianceLimitCleanPairInput(
        round_id=values[0],
        reference_episode_dir=Path(values[1]),
        candidate_episode_dir=Path(values[2]),
        cross_build_path=Path(values[3]),
        reference_resource_path=Path(values[4]),
        candidate_resource_path=Path(values[5]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """CLI for an explicitly listed set of clean replay pairs."""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate explicit D1 covariance-limit reference/candidate pairs"
        )
    )
    parser.add_argument("--reference-commit", required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--pair",
        action="append",
        nargs=6,
        metavar=(
            "ROUND",
            "REF_EPISODE",
            "CAND_EPISODE",
            "CROSS_JSON",
            "REF_RESOURCE",
            "CAND_RESOURCE",
        ),
        required=True,
        help=(
            "Explicit pair binding; repeat exactly three times for the formal "
            "gate"
        ),
    )
    args = parser.parse_args(argv)
    inputs = [_parse_pair_argument(values) for values in args.pair]
    result = evaluate_d1_covariance_limit_clean_pairs(
        inputs,
        expected_reference_commit=args.reference_commit,
        expected_candidate_commit=args.candidate_commit,
    )
    paths = write_d1_covariance_limit_clean_pair_report(
        result, args.output_dir
    )
    print(
        json.dumps(
            {
                "d1_optimization_admitted": result[
                    "d1_optimization_admitted"
                ],
                "system_realtime_gap_closed": result[
                    "system_realtime_gap_closed"
                ],
                "outputs": {key: str(path) for key, path in paths.items()},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["d1_optimization_admitted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "D1_COVARIANCE_LIMIT_CLEAN_PAIR_EVALUATION_DATE",
    "D1_COVARIANCE_LIMIT_CLEAN_PAIR_SCHEMA_VERSION",
    "D1_COVARIANCE_LIMIT_FUSION_STAGE",
    "D1_COVARIANCE_LIMIT_MAXIMUM_RSS_INCREASE_PCT",
    "D1_COVARIANCE_LIMIT_MINIMUM_FUSION_IMPROVEMENT_PCT",
    "D1_COVARIANCE_LIMIT_SCAN_INPUT_STAGE",
    "D1CovarianceLimitCleanPairInput",
    "evaluate_d1_covariance_limit_clean_pairs",
    "evaluate_d1_covariance_limit_explicit_pair",
    "render_d1_covariance_limit_clean_pair_markdown",
    "write_d1_covariance_limit_clean_pair_report",
]
