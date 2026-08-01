"""Read-only paired episode audit for D1 GlobalTrack A95 materialization.

The evaluator compares complete scalable three-dimensional episodes produced
from the same input.  It permits only the registered D1 implementation
identity, A95 operation counters, and measured performance timings to differ.
It never runs an episode and never mutates producer evidence.
"""

from __future__ import annotations

from collections import Counter
import argparse
import copy
import csv
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from statistics import fmean, median
import sys
from typing import Any, Mapping, Sequence

import numpy as np


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    compare_cross_build_episodes,
)


D1_GLOBAL_TRACK_A95_EPISODE_AB_SCHEMA_VERSION = (
    "d6.d1_global_track_a95_episode_ab_evaluation.v2"
)
D1_GLOBAL_TRACK_A95_PAIR_LIST_SCHEMA_VERSION = (
    "d6.d1_global_track_a95_pair_list.v1"
)
D1_GLOBAL_TRACK_A95_AGGREGATE_SCHEMA_VERSION = (
    "d6.d1_global_track_a95_episode_ab_aggregate.v2"
)
D1_GLOBAL_TRACK_A95_EVALUATOR_BASELINE_COMMIT = (
    "4166fe8e8ab4a9a14cffb275ba0a9ffa50a43dbb"
)

REFERENCE_SELECTOR = "per_track_a95_summary_v1"
CANDIDATE_SELECTOR = "batched_a95_summary_v1"
REFERENCE_IMPLEMENTATION_ID = (
    "d1.publication.global_track_materialization.per_track_a95_summary.v1"
)
CANDIDATE_IMPLEMENTATION_ID = (
    "d1.publication.global_track_materialization.batched_a95_summary.v1"
)
GLOBAL_TRACK_MATERIALIZATION_DIAGNOSTICS_SCHEMA_VERSION = (
    "d1.global_track_materialization_diagnostics.v1"
)

RESERVED_FORMAL_SEEDS = frozenset(range(1000, 1020))
MINIMUM_DESCRIPTIVE_PAIR_COUNT = 7
MINIMUM_CANDIDATE_FASTER_FRACTION = 0.80
MINIMUM_MEDIAN_IMPROVEMENT_PERCENT = 10.0

_REFERENCE_ARM = "reference"
_CANDIDATE_ARM = "candidate"
_ARMS = (_REFERENCE_ARM, _CANDIDATE_ARM)
_SELECTORS = {
    _REFERENCE_ARM: REFERENCE_SELECTOR,
    _CANDIDATE_ARM: CANDIDATE_SELECTOR,
}
_IMPLEMENTATION_IDS = {
    _REFERENCE_ARM: REFERENCE_IMPLEMENTATION_ID,
    _CANDIDATE_ARM: CANDIDATE_IMPLEMENTATION_ID,
}
_CANDIDATE_ENABLED = {_REFERENCE_ARM: False, _CANDIDATE_ARM: True}

_REQUIRED_EPISODE_FILES = (
    "manifest.json",
    "scenario_config.json",
    "summary.json",
    "observation_governance_audit.json",
    "stage_timings.csv",
    "online_observations.jsonl",
    "offline_truth_state.npz",
    "offline_truth_labels.jsonl",
    "offline_proximity_intercepts.jsonl",
)
_A95_OPERATION_FIELDS = frozenset(
    {
        "batched_a95_eigvalsh_call_count",
        "batched_a95_summary_build_count",
        "batched_a95_summary_matrix_count",
        "batched_a95_summary_reuse_count",
        "per_track_a95_summary_call_count",
    }
)
_REQUIRED_COMMON_OPERATION_FIELDS = frozenset(
    {
        "global_tracks_call_count",
        "global_track_metadata_materialization_count",
        "track_quality_summary_request_count",
    }
)
_COMPARISON_KEY_FIELDS = (
    "scenario_name",
    "scenario_version",
    "seed",
    "target_count",
    "resource_count",
    "recon_count",
    "duration_s",
    "config_sha256",
)
_STAGE_TIMING_SCHEMA_VERSION = "scalable3d-stage-timings-v2"
_D1_INCLUSIVE_TIMING_STAGE = "module.d1_fusion"
_DEDICATED_MATERIALIZATION_STAGES = (
    "module.d1_global_track_materialization",
    "module.d1_publication_materialization",
    "module.d1_materialization",
)
_TIMING_FIELDS = frozenset(
    {
        "wall_time_s",
        "mean_wall_time_ms",
        "p50_wall_time_ms",
        "p95_wall_time_ms",
        "max_wall_time_ms",
    }
)
_FORBIDDEN_ONLINE_IDENTITY_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "ground_truth",
        "ground_truth_id",
        "object_id",
        "object_name",
        "truth",
        "truth_id",
        "truth_label",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_CHI2_2_95 = 5.991464547107979
_TREATMENT_MARKER = "D6_REGISTERED_GLOBAL_TRACK_A95_TREATMENT"
_TIMING_MARKER = "D6_ALLOWED_PERFORMANCE_TIMING"
_EPISODE_ID_MARKER = "D6_TREATMENT_DERIVED_EPISODE_ID"
_SENSOR_OBSERVATION_TOPIC = "sensor.observations"
_D1_FUSED_TRACK_TOPIC = "modules.d1.fused_tracks"
_D2_ASSOCIATED_TRACK_TOPIC = "modules.d2.associated_tracks"
_RUNTIME_TRANSPORT_METADATA_KEYS = frozenset(
    {
        "delivery_sequence",
        "delivery_timestamp",
        "delivery_timestamp_s",
        "message_id",
        "plan_payload_sha256",
        "retry_generation",
        "source_guidance_bus_sequence",
        "source_guidance_payload_sha256",
        "source_plan_bus_sequence",
        "source_plan_payload_sha256",
    }
)


class D1GlobalTrackA95EvidenceError(ValueError):
    """Raised when one producer artifact violates the paired evidence contract."""


class _StrictJSONConstantError(ValueError):
    pass


def evaluate_d1_global_track_a95_episode_ab(
    source: str | Path,
    *,
    mismatch_limit: int = 20,
) -> dict[str, Any]:
    """Evaluate a paired directory or an explicit pair-list JSON.

    Pair-local evidence errors become ``unavailable`` rows.  This preserves
    every requested pair in the output without replacing missing metrics with
    zero.  A malformed top-level source returns a fail-closed aggregate with no
    synthetic pair rows.
    """

    if mismatch_limit < 1:
        raise ValueError("mismatch_limit must be positive")
    source_path = Path(source).expanduser().resolve()
    try:
        bindings = _load_pair_bindings(source_path)
    except (D1GlobalTrackA95EvidenceError, OSError, ValueError) as exc:
        return _unavailable_evaluation(source_path, str(exc))

    pairs: list[dict[str, Any]] = []
    for binding in bindings:
        pairs.append(_evaluate_pair(binding, mismatch_limit=mismatch_limit))
    return _aggregate_evaluation(source_path, pairs)


def write_d1_global_track_a95_episode_ab_report(
    evaluation: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Write pair CSV, aggregate JSON, and Chinese Markdown."""

    if evaluation.get("schema_version") != (
        D1_GLOBAL_TRACK_A95_EPISODE_AB_SCHEMA_VERSION
    ):
        raise ValueError("unexpected D1 GlobalTrack A95 evaluation schema")
    root = Path(output_dir).expanduser().resolve()
    for pair in _required_sequence(evaluation.get("pairs"), "evaluation pairs"):
        if not isinstance(pair, Mapping):
            raise ValueError("evaluation pair must be a mapping")
        for key in ("reference_episode_dir", "candidate_episode_dir"):
            raw_path = pair.get(key)
            if raw_path is None:
                continue
            evidence_root = Path(str(raw_path)).expanduser().resolve()
            if _is_relative_to(root, evidence_root) or _is_relative_to(
                evidence_root, root
            ):
                raise ValueError(
                    "report output must be independent of producer episode directories"
                )

    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "d1_global_track_a95_pairs.csv"
    json_path = root / "d1_global_track_a95_aggregate.json"
    markdown_path = root / "D1_GLOBAL_TRACK_A95_EPISODE_AB_CN.md"
    _write_pair_csv(csv_path, evaluation)
    json_path.write_text(
        json.dumps(
            dict(evaluation),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_d1_global_track_a95_episode_ab_markdown(evaluation),
        encoding="utf-8",
    )
    return {
        "pairs_csv": csv_path,
        "aggregate_json": json_path,
        "markdown": markdown_path,
    }


def render_d1_global_track_a95_episode_ab_markdown(
    evaluation: Mapping[str, Any],
) -> str:
    """Render the independent paired assessment in Chinese."""

    aggregate = _required_mapping(evaluation.get("aggregate"), "aggregate")
    availability = _required_mapping(
        evaluation.get("availability"), "availability"
    )
    status = str(evaluation.get("status", "unavailable"))
    lines = [
        "# D1 GlobalTrack A95 完整三维 Episode 配对评估",
        "",
        "## 结论",
        "",
        (
            f"本次登记 `{int(aggregate.get('pair_count', 0))}` 对 episode，"
            f"可用 `{int(aggregate.get('available_pair_count', 0))}` 对，"
            f"业务精确等价 `{int(aggregate.get('exact_equivalent_pair_count', 0))}` 对，"
            f"总体状态为 `{status}`。"
        ),
        (
            "评估器只允许两臂的实现身份、A95 操作计数和性能计时不同。"
            "D1 状态、协方差、双时间戳、独立复算 A95、航迹等级、身份谱系、"
            "D2 输入绑定和输出以及在线真值使用均参与失败关闭比较。"
        ),
        (
            "`exogenous_input_equivalent` 只比较场景、离线真值和按稳定身份排序的"
            " `sensor.observations`；总线 sequence、内部模块发布、通信投递时间和"
            "消息顺序归入 `runtime_bus_timing_equivalent`。因此通信时序漂移不会被"
            "误报为初始输入漂移。"
        ),
        "",
    ]
    if not availability.get("available", False):
        lines.extend(
            [
                "输入不可用。原因：",
                "",
                *[
                    f"- `{reason}`"
                    for reason in availability.get("reasons", ())
                ],
                "",
            ]
        )
    sample = _required_mapping(
        aggregate.get("sample_sufficiency", {}), "sample_sufficiency"
    )
    if not sample.get("minimum_pair_count_met", False):
        lines.extend(
            [
                "当前可用 pair 少于 7 对，只能作为接口或小样本描述性证据。"
                "本报告不形成正式晋级、默认切换或系统实时闭合结论。",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "样本数量达到描述性性能门的最低对数。正式晋级仍需 main 预注册实验、"
                "独立复核和默认关闭状态下的审批，本评估器不授予运行权限。",
                "",
            ]
        )

    lines.extend(
        [
            "## 汇总",
            "",
            "| 指标 | 结果 |",
            "| --- | ---: |",
            f"| 可用 pair | {int(aggregate.get('available_pair_count', 0))} |",
            f"| 不可用 pair | {int(aggregate.get('unavailable_pair_count', 0))} |",
            f"| 精确等价率 | {_format_optional_ratio(aggregate.get('exact_equivalence_rate'))} |",
            f"| 外生输入等价率 | {_format_optional_ratio(aggregate.get('exogenous_input_equivalence_rate'))} |",
            f"| 运行时总线时序等价率 | {_format_optional_ratio(aggregate.get('runtime_bus_timing_equivalence_rate'))} |",
            f"| 时序漂移伴随 D1/D2 业务分歧 | {int(aggregate.get('runtime_timing_induced_business_divergence_pair_count', 0))} |",
            f"| 候选更快比例 | {_format_optional_ratio(aggregate.get('candidate_faster_fraction'))} |",
            f"| 墙钟中位改善 | {_format_optional_number(aggregate.get('median_wall_improvement_percent'), suffix='%')} |",
            f"| D1 包含式计时中位改善 | {_format_optional_number(aggregate.get('median_d1_publication_materialization_improvement_percent'), suffix='%')} |",
            f"| Reference 标量 A95 次数 | {_format_optional_integer(aggregate.get('reference_scalar_a95_count'))} |",
            f"| Candidate 批量特征值调用 | {_format_optional_integer(aggregate.get('candidate_batched_eigvalsh_call_count'))} |",
            f"| Candidate 批量矩阵数 | {_format_optional_integer(aggregate.get('candidate_batched_matrix_count'))} |",
            "",
            "D1 包含式计时取自 `stage_timings.csv` 的 `module.d1_fusion`。"
            "该阶段包含扫描更新和 GlobalTrack 发布/物化，当前 runtime 未单列纯物化墙钟。"
            "报告保留此范围说明，不把包含式计时改写为纯物化耗时。",
            "",
            "## 逐对结果",
            "",
            "| Pair | seed | 规模 | 状态 | 外生输入 | 总线时序 | D1/D2 业务 | 操作合同 | 墙钟 Ref/Cand s | D1 Ref/Cand s |",
            "| --- | ---: | ---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: |",
        ]
    )
    for pair in _required_sequence(evaluation.get("pairs"), "pairs"):
        comparison_key = pair.get("comparison_key") or {}
        scale = "-"
        if isinstance(comparison_key, Mapping):
            target_count = comparison_key.get("target_count")
            resource_count = comparison_key.get("resource_count")
            if target_count is not None and resource_count is not None:
                scale = f"{target_count}v{resource_count}"
        lines.append(
            "| `{pair_id}` | {seed} | {scale} | `{status}` | {exogenous} | "
            "{runtime} | {business} | {operations} | {wall} | {d1} |".format(
                pair_id=pair.get("pair_id", "unknown"),
                seed=(
                    "-"
                    if not isinstance(comparison_key, Mapping)
                    else comparison_key.get("seed", "-")
                ),
                scale=scale,
                status=pair.get("status", "unavailable"),
                exogenous=_yes_no_unknown(
                    pair.get("exogenous_input_equivalent")
                ),
                runtime=_yes_no_unknown(
                    pair.get("runtime_bus_timing_equivalent")
                ),
                business=_yes_no_unknown(pair.get("business_equivalent")),
                operations=_yes_no_unknown(pair.get("operation_contract_passed")),
                wall=_format_pair_metric(pair, "wall_time_s"),
                d1=_format_pair_metric(
                    pair, "d1_publication_materialization_inclusive_wall_s"
                ),
            )
        )

    dispositions = Counter(
        str(pair.get("comparison_disposition", "unknown"))
        for pair in _required_sequence(evaluation.get("pairs"), "pairs")
    )
    if dispositions:
        lines.extend(["", "## 比较分类", ""])
        for disposition, count in sorted(dispositions.items()):
            lines.append(f"- `{disposition}`：{count} 对。")

    failures = aggregate.get("failure_reason_counts", {})
    if isinstance(failures, Mapping) and failures:
        lines.extend(["", "## 失败原因", ""])
        for reason, count in sorted(failures.items()):
            lines.append(f"- `{reason}`：{int(count)} 对。")

    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- evaluator 不运行 episode，不修改 producer 目录，不读取保留 seed 1000--1019 的 episode payload。",
            "- formal shard 10--19 与既有 450/900 结论不在本评估器输入范围内。",
            f"- reference 固定为 `{REFERENCE_SELECTOR}`；candidate 固定为 `{CANDIDATE_SELECTOR}`，candidate 继续 default-off。",
            "- 离线 truth 仅用于确认两臂初始状态与场景输入相同；在线总线中的 truth/actor/object 身份键必须为零。",
            "- 小样本结果、单机墙钟和包含式 D1 计时均不能单独证明正式晋级或 200 对 200 实时闭合。",
        ]
    )
    return "\n".join(lines) + "\n"


def _evaluate_pair(
    binding: Mapping[str, Any],
    *,
    mismatch_limit: int,
) -> dict[str, Any]:
    pair_id = str(binding["pair_id"])
    reference_dir = Path(binding["reference_episode_dir"])
    candidate_dir = Path(binding["candidate_episode_dir"])
    base = {
        "pair_id": pair_id,
        "reference_episode_dir": str(reference_dir),
        "candidate_episode_dir": str(candidate_dir),
        "comparison_key": binding.get("comparison_key"),
        "status": "unavailable",
        "available": False,
        "comparison_disposition": "evidence_unavailable",
        "exogenous_input_equivalent": None,
        "runtime_bus_timing_equivalent": None,
        "business_equivalent": None,
        "operation_contract_passed": None,
        "pair_passed": False,
        "failure_reasons": [],
        "reference": None,
        "candidate": None,
        "checks": {},
    }

    try:
        expected_key = binding.get("comparison_key")
        if isinstance(expected_key, Mapping):
            expected_seed = _required_int(
                expected_key.get("seed"), f"{pair_id} comparison key seed"
            )
            if expected_seed in RESERVED_FORMAL_SEEDS:
                raise D1GlobalTrackA95EvidenceError(
                    "reserved_formal_seed_payload_read_forbidden"
                )

        preflight = {
            arm: _preflight_episode_manifest(Path(binding[f"{arm}_episode_dir"]), arm)
            for arm in _ARMS
        }
        episodes = {
            arm: _load_episode(
                Path(binding[f"{arm}_episode_dir"]),
                arm=arm,
                preflight=preflight[arm],
            )
            for arm in _ARMS
        }
        derived_key = _comparison_key(episodes[_REFERENCE_ARM])
        candidate_key = _comparison_key(episodes[_CANDIDATE_ARM])
        if derived_key != candidate_key:
            raise D1GlobalTrackA95EvidenceError(
                "comparison_key_differs_between_arms"
            )
        if expected_key is not None:
            validated_expected_key = _validate_explicit_comparison_key(
                expected_key, pair_id
            )
            if validated_expected_key != derived_key:
                raise D1GlobalTrackA95EvidenceError(
                    "comparison_key_mismatch"
                )
        base["comparison_key"] = derived_key

        fingerprints_before = {
            arm: _episode_fingerprint(episodes[arm]) for arm in _ARMS
        }
        pair_result = _compare_loaded_pair(
            episodes[_REFERENCE_ARM],
            episodes[_CANDIDATE_ARM],
            mismatch_limit=mismatch_limit,
        )
        fingerprints_after = {
            arm: _episode_fingerprint(episodes[arm]) for arm in _ARMS
        }
        if fingerprints_before != fingerprints_after:
            raise D1GlobalTrackA95EvidenceError(
                "producer_evidence_changed_during_evaluation"
            )

        base.update(pair_result)
        base["available"] = bool(pair_result["comparison_available"])
        base["status"] = str(pair_result["pair_status"])
        return base
    except (
        D1GlobalTrackA95EvidenceError,
        FileNotFoundError,
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        base["failure_reasons"] = [_reason_code(exc)]
        return base


def _compare_loaded_pair(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    mismatch_limit: int,
) -> dict[str, Any]:
    reference_dir = Path(reference["root"])
    candidate_dir = Path(candidate["root"])
    cross = compare_cross_build_episodes(
        reference_dir, candidate_dir, mismatch_limit=mismatch_limit
    )

    reference_manifest_normalized = _normalized_manifest(reference)
    candidate_manifest_normalized = _normalized_manifest(candidate)
    reference_summary_normalized = _normalized_summary(reference)
    candidate_summary_normalized = _normalized_summary(candidate)
    reference_governance_normalized = _normalized_governance(reference)
    candidate_governance_normalized = _normalized_governance(candidate)

    reference_online = _audit_required_online_surfaces(reference)
    candidate_online = _audit_required_online_surfaces(candidate)
    exogenous_sensor_equal = (
        reference_online["exogenous_input_surface_sha256"]
        == candidate_online["exogenous_input_surface_sha256"]
    )
    runtime_bus_timing_equal = (
        reference_online["runtime_bus_timing_surface_sha256"]
        == candidate_online["runtime_bus_timing_surface_sha256"]
    )
    d1_surface_equal = (
        reference_online["d1_business_surface_sha256"]
        == candidate_online["d1_business_surface_sha256"]
    )
    d2_surface_equal = (
        reference_online["d2_business_surface_sha256"]
        == candidate_online["d2_business_surface_sha256"]
    )
    timestamp_surface_equal = (
        reference_online["timestamp_surface_sha256"]
        == candidate_online["timestamp_surface_sha256"]
    )

    reference_timing = reference["stage_timing"]
    candidate_timing = candidate["stage_timing"]
    timing_structure_equal = (
        reference_timing["normalized_structure"]
        == candidate_timing["normalized_structure"]
    )

    reference_operations = reference["operation_evidence"]
    candidate_operations = candidate["operation_evidence"]
    operation_checks = _operation_checks(
        reference_operations, candidate_operations
    )
    operation_contract_passed = all(operation_checks.values())

    cross_checks = {
        name: bool(cross["checks"][name])
        for name in (
            "reference_source_clean",
            "candidate_source_clean",
            "same_seed",
            "same_scenario_version",
            "same_duration",
            "same_scenario_config",
            "summary_contract_equal",
            "truth_state_equal",
            "truth_labels_semantically_equal",
            "proximity_events_semantically_equal",
            "plan_lineage_pattern_equal",
            "reference_plan_lineage_valid",
            "candidate_plan_lineage_valid",
            "ack_source_integrity",
            "d4_content_address_integrity",
        )
    }
    association_solve = cross["allowed_performance_diagnostics"][
        "d1_association_innovation_solve_count"
    ]
    checks = {
        **cross_checks,
        "same_git_commit": (
            reference["manifest"]["git_commit"]
            == candidate["manifest"]["git_commit"]
        ),
        "runtime_profile_equal_except_a95_selector": (
            reference["normalized_runtime_profile_sha256"]
            == candidate["normalized_runtime_profile_sha256"]
        ),
        "manifest_equal_except_registered_treatment": (
            reference_manifest_normalized == candidate_manifest_normalized
        ),
        "summary_equal_except_registered_treatment_and_timing": (
            reference_summary_normalized == candidate_summary_normalized
        ),
        "governance_equal_except_registered_treatment": (
            reference_governance_normalized
            == candidate_governance_normalized
        ),
        "stage_timing_structure_equal": timing_structure_equal,
        "exogenous_sensor_observations_equal": exogenous_sensor_equal,
        "d1_global_track_business_surface_equal": d1_surface_equal,
        "d1_double_timestamp_surface_equal": timestamp_surface_equal,
        "d2_input_output_surface_equal": d2_surface_equal,
        "online_truth_key_count_zero": (
            reference_online["forbidden_online_identity_key_count"]
            == candidate_online["forbidden_online_identity_key_count"]
            == 0
        ),
        "online_truth_use_count_zero": (
            int(reference["summary"]["online_truth_use_count"])
            == int(candidate["summary"]["online_truth_use_count"])
            == 0
        ),
        "non_a95_d1_solve_count_equal": (
            int(association_solve["reference_total"])
            == int(association_solve["candidate_total"])
        ),
        "operation_contract_passed": operation_contract_passed,
    }
    exogenous_input_equivalent = all(
        (
            cross_checks["same_scenario_config"],
            cross_checks["truth_state_equal"],
            cross_checks["truth_labels_semantically_equal"],
            exogenous_sensor_equal,
        )
    )
    comparison_available = bool(
        exogenous_input_equivalent
        and checks["runtime_profile_equal_except_a95_selector"]
        and checks["same_git_commit"]
    )
    business_equivalent = None
    if comparison_available:
        business_equivalent = all(
            value
            for name, value in checks.items()
            if name != "operation_contract_passed"
        )

    reference_metrics = _arm_metrics(reference, reference_operations)
    candidate_metrics = _arm_metrics(candidate, candidate_operations)
    wall_improvement = _improvement_percent(
        reference_metrics["wall_time_s"], candidate_metrics["wall_time_s"]
    )
    d1_improvement = _improvement_percent(
        reference_metrics[
            "d1_publication_materialization_inclusive_wall_s"
        ],
        candidate_metrics[
            "d1_publication_materialization_inclusive_wall_s"
        ],
    )
    failure_reasons = [name for name, passed in checks.items() if not passed]
    if not exogenous_input_equivalent:
        comparison_disposition = "incomparable_exogenous_input_mismatch"
        failure_reasons.insert(0, comparison_disposition)
    elif not comparison_available:
        comparison_disposition = "incomparable_execution_profile_mismatch"
        failure_reasons.insert(0, comparison_disposition)
    elif not runtime_bus_timing_equal and not (
        d1_surface_equal and d2_surface_equal and timestamp_surface_equal
    ):
        comparison_disposition = "runtime_timing_induced_business_divergence"
        failure_reasons.insert(0, comparison_disposition)
    elif business_equivalent is False:
        comparison_disposition = "business_behavior_regression"
    elif not runtime_bus_timing_equal:
        comparison_disposition = "business_equivalent_with_runtime_timing_drift"
    else:
        comparison_disposition = "business_and_runtime_timing_equivalent"
    pair_passed = bool(
        comparison_available
        and business_equivalent is True
        and operation_contract_passed
    )
    if not comparison_available:
        pair_status = "incomparable"
    else:
        pair_status = "passed" if pair_passed else "failed"
    return {
        "comparison_available": comparison_available,
        "comparison_disposition": comparison_disposition,
        "pair_status": pair_status,
        "exogenous_input_equivalent": exogenous_input_equivalent,
        "runtime_bus_timing_equivalent": runtime_bus_timing_equal,
        "business_equivalent": business_equivalent,
        "operation_contract_passed": operation_contract_passed,
        "pair_passed": pair_passed,
        "failure_reasons": failure_reasons,
        "checks": dict(sorted(checks.items())),
        "operation_checks": dict(sorted(operation_checks.items())),
        "reference": reference_metrics,
        "candidate": candidate_metrics,
        "wall_improvement_percent": wall_improvement,
        "d1_publication_materialization_improvement_percent": d1_improvement,
        "candidate_faster": (
            candidate_metrics["wall_time_s"] < reference_metrics["wall_time_s"]
        ),
        "business_surface": {
            "reference_exogenous_input_sha256": reference_online[
                "exogenous_input_surface_sha256"
            ],
            "candidate_exogenous_input_sha256": candidate_online[
                "exogenous_input_surface_sha256"
            ],
            "reference_runtime_bus_timing_sha256": reference_online[
                "runtime_bus_timing_surface_sha256"
            ],
            "candidate_runtime_bus_timing_sha256": candidate_online[
                "runtime_bus_timing_surface_sha256"
            ],
            "reference_d1_sha256": reference_online[
                "d1_business_surface_sha256"
            ],
            "candidate_d1_sha256": candidate_online[
                "d1_business_surface_sha256"
            ],
            "reference_d2_sha256": reference_online[
                "d2_business_surface_sha256"
            ],
            "candidate_d2_sha256": candidate_online[
                "d2_business_surface_sha256"
            ],
            "reference_timestamp_sha256": reference_online[
                "timestamp_surface_sha256"
            ],
            "candidate_timestamp_sha256": candidate_online[
                "timestamp_surface_sha256"
            ],
            "d1_track_sample_count": reference_online[
                "d1_track_sample_count"
            ],
            "d1_lineage_record_count": reference_online[
                "d1_lineage_record_count"
            ],
            "d2_track_sample_count": reference_online[
                "d2_track_sample_count"
            ],
            "exogenous_sensor_batch_count": reference_online[
                "exogenous_sensor_batch_count"
            ],
            "runtime_bus_record_count": reference_online[
                "runtime_bus_record_count"
            ],
            "runtime_bus_timing_mismatches": _surface_mismatch_paths(
                reference_online["runtime_bus_timing_surface"],
                candidate_online["runtime_bus_timing_surface"],
                limit=mismatch_limit,
            ),
            "d1_business_mismatches": _surface_mismatch_paths(
                reference_online["d1_business_surface"],
                candidate_online["d1_business_surface"],
                limit=mismatch_limit,
            ),
            "d2_business_mismatches": _surface_mismatch_paths(
                reference_online["d2_business_surface"],
                candidate_online["d2_business_surface"],
                limit=mismatch_limit,
            ),
        },
        "source_sha256": {
            "reference": reference["source_sha256"],
            "candidate": candidate["source_sha256"],
        },
        "cross_build_schema_version": cross["schema_version"],
        "cross_build_normalized_online_payloads_equal": bool(
            cross["online_bus"]["normalized_online_payloads_equal"]
        ),
        "cross_build_mismatches": cross["online_bus"]["mismatches"],
    }


def _preflight_episode_manifest(root: Path, arm: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise D1GlobalTrackA95EvidenceError(f"{arm}_episode_dir_missing")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise D1GlobalTrackA95EvidenceError(f"{arm}_manifest_missing")
    manifest = _load_strict_json_mapping(manifest_path)
    seed = _required_int(manifest.get("seed"), f"{arm} manifest seed")
    if seed in RESERVED_FORMAL_SEEDS:
        raise D1GlobalTrackA95EvidenceError(
            "reserved_formal_seed_payload_read_forbidden"
        )
    return {"root": root, "manifest": manifest, "seed": seed}


def _load_episode(
    root: Path,
    *,
    arm: str,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if root != preflight["root"]:
        raise D1GlobalTrackA95EvidenceError("preflight_root_binding_mismatch")
    paths = {name: root / name for name in _REQUIRED_EPISODE_FILES}
    for name, path in paths.items():
        if not path.is_file():
            raise D1GlobalTrackA95EvidenceError(
                f"required_episode_artifact_missing:{name}"
            )

    manifest = dict(preflight["manifest"])
    scenario = _load_strict_json_mapping(paths["scenario_config.json"])
    summary = _load_strict_json_mapping(paths["summary.json"])
    governance = _load_strict_json_mapping(
        paths["observation_governance_audit.json"]
    )
    _validate_manifest_hashes(manifest, scenario, arm)
    _validate_manifest_identity(manifest, summary, arm)
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"), f"{arm} runtime_profile"
    )
    normalized_runtime_profile = _normalize_runtime_profile(
        runtime_profile, arm=arm
    )
    operation_evidence = _validate_arm_materialization_evidence(
        manifest=manifest,
        summary=summary,
        governance=governance,
        arm=arm,
    )
    stage_timing = _load_stage_timing(paths["stage_timings.csv"])
    wall_time = _required_positive_float(
        summary.get("wall_time_s"), f"{arm} summary wall_time_s"
    )
    real_time_factor = _required_nonnegative_float(
        summary.get("real_time_factor"), f"{arm} summary real_time_factor"
    )
    del wall_time, real_time_factor

    source_sha256 = {
        name: _file_sha256(path) for name, path in sorted(paths.items())
    }
    return {
        "root": root,
        "paths": paths,
        "manifest": manifest,
        "scenario": scenario,
        "summary": summary,
        "governance": governance,
        "stage_timing": stage_timing,
        "operation_evidence": operation_evidence,
        "normalized_runtime_profile": normalized_runtime_profile,
        "normalized_runtime_profile_sha256": _canonical_sha256(
            normalized_runtime_profile
        ),
        "source_sha256": source_sha256,
    }


def _validate_manifest_hashes(
    manifest: Mapping[str, Any],
    scenario: Mapping[str, Any],
    arm: str,
) -> None:
    expected_config = _required_sha256(
        manifest.get("config_sha256"), f"{arm} config_sha256"
    )
    actual_config = _canonical_sha256(scenario)
    if expected_config != actual_config:
        raise D1GlobalTrackA95EvidenceError("scenario_config_sha256_mismatch")
    runtime_profile = _required_mapping(
        manifest.get("runtime_profile"), f"{arm} runtime_profile"
    )
    expected_runtime = _required_sha256(
        manifest.get("runtime_profile_sha256"),
        f"{arm} runtime_profile_sha256",
    )
    actual_runtime = _canonical_sha256(runtime_profile)
    if expected_runtime != actual_runtime:
        raise D1GlobalTrackA95EvidenceError("runtime_profile_sha256_mismatch")


def _validate_manifest_identity(
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    arm: str,
) -> None:
    commit = str(manifest.get("git_commit", "")).strip()
    if _COMMIT_RE.fullmatch(commit) is None:
        raise D1GlobalTrackA95EvidenceError(f"{arm}_git_commit_invalid")
    if manifest.get("repository_dirty") is not False:
        raise D1GlobalTrackA95EvidenceError(f"{arm}_source_not_clean")
    manifest_seed = _required_int(manifest.get("seed"), f"{arm} manifest seed")
    summary_seed = _required_int(summary.get("seed"), f"{arm} summary seed")
    if manifest_seed != summary_seed:
        raise D1GlobalTrackA95EvidenceError(f"{arm}_manifest_summary_seed_mismatch")
    if manifest_seed in RESERVED_FORMAL_SEEDS:
        raise D1GlobalTrackA95EvidenceError(
            "reserved_formal_seed_payload_read_forbidden"
        )
    if _required_int(
        summary.get("online_truth_use_count"),
        f"{arm} online_truth_use_count",
    ) != 0:
        raise D1GlobalTrackA95EvidenceError("online_truth_use_count_nonzero")


def _validate_arm_materialization_evidence(
    *,
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    governance: Mapping[str, Any],
    arm: str,
) -> dict[str, Any]:
    profile = _required_mapping(
        manifest.get("runtime_profile"), f"{arm} runtime_profile"
    )
    profile_config = _required_mapping(
        profile.get("configuration"), f"{arm} runtime profile configuration"
    )
    _expect_equal(
        profile_config.get("d1_global_track_materialization_implementation"),
        _SELECTORS[arm],
        f"{arm} runtime profile selector",
    )
    _validate_execution_config(
        _required_mapping(
            profile.get("d1_global_track_materialization_execution_config"),
            f"{arm} profile execution config",
        ),
        arm=arm,
        context=f"{arm} profile",
    )
    profile_diagnostics = _required_mapping(
        profile.get("d1_global_track_materialization_diagnostics"),
        f"{arm} profile diagnostics",
    )
    _validate_diagnostics_identity(
        profile_diagnostics, arm=arm, context=f"{arm} profile"
    )
    if _required_mapping(
        profile_diagnostics.get("operation_counts"),
        f"{arm} profile operation_counts",
    ):
        raise D1GlobalTrackA95EvidenceError(
            f"{arm}_profile_initial_operation_counts_not_empty"
        )

    summary_diagnostics = _require_final_materialization_fields(
        summary, arm=arm, context=f"{arm} summary"
    )
    final_module = _required_mapping(
        summary.get("module_final_diagnostics"),
        f"{arm} module_final_diagnostics",
    )
    module_diagnostics = _require_final_materialization_fields(
        final_module, arm=arm, context=f"{arm} module_final_diagnostics"
    )
    governance_diagnostics = _require_final_materialization_fields(
        governance, arm=arm, context=f"{arm} governance"
    )
    if not (
        summary_diagnostics == module_diagnostics == governance_diagnostics
    ):
        raise D1GlobalTrackA95EvidenceError(
            f"{arm}_final_materialization_evidence_not_consistent"
        )
    operations = _required_mapping(
        summary_diagnostics.get("operation_counts"),
        f"{arm} final operation_counts",
    )
    missing_common = sorted(
        _REQUIRED_COMMON_OPERATION_FIELDS.difference(operations)
    )
    if missing_common:
        raise D1GlobalTrackA95EvidenceError(
            "missing_required_operation_metrics:" + ",".join(missing_common)
        )
    normalized_operations = {
        str(key): _required_nonnegative_int(value, f"{arm} operation {key}")
        for key, value in operations.items()
    }
    return {
        "diagnostics": copy.deepcopy(dict(summary_diagnostics)),
        "operation_counts": dict(sorted(normalized_operations.items())),
    }


def _require_final_materialization_fields(
    container: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> dict[str, Any]:
    _expect_equal(
        container.get("d1_global_track_materialization_implementation"),
        _SELECTORS[arm],
        f"{context} selector",
    )
    _validate_execution_config(
        _required_mapping(
            container.get("d1_global_track_materialization_execution_config"),
            f"{context} execution config",
        ),
        arm=arm,
        context=context,
    )
    diagnostics = _required_mapping(
        container.get("d1_global_track_materialization_diagnostics"),
        f"{context} diagnostics",
    )
    _validate_diagnostics_identity(diagnostics, arm=arm, context=context)
    return copy.deepcopy(dict(diagnostics))


def _validate_execution_config(
    config: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> None:
    _expect_equal(
        config.get("schema_version"),
        GLOBAL_TRACK_MATERIALIZATION_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} execution schema",
    )
    _expect_equal(config.get("selector"), _SELECTORS[arm], f"{context} selector")
    _expect_equal(
        config.get("implementation_id"),
        _IMPLEMENTATION_IDS[arm],
        f"{context} implementation_id",
    )
    _expect_equal(
        config.get("candidate_enabled"),
        _CANDIDATE_ENABLED[arm],
        f"{context} candidate_enabled",
    )
    if config.get("default_enabled") is not False:
        raise D1GlobalTrackA95EvidenceError(
            f"{context}_candidate_must_remain_default_off"
        )
    if config.get("truth_dependent_inputs_allowed") is not False:
        raise D1GlobalTrackA95EvidenceError(
            f"{context}_truth_dependent_inputs_not_forbidden"
        )


def _validate_diagnostics_identity(
    diagnostics: Mapping[str, Any],
    *,
    arm: str,
    context: str,
) -> None:
    _expect_equal(
        diagnostics.get("schema_version"),
        GLOBAL_TRACK_MATERIALIZATION_DIAGNOSTICS_SCHEMA_VERSION,
        f"{context} diagnostics schema",
    )
    _expect_equal(
        diagnostics.get("global_track_materialization_implementation_id"),
        _IMPLEMENTATION_IDS[arm],
        f"{context} diagnostics implementation_id",
    )
    _expect_equal(
        diagnostics.get("batched_global_track_a95_summary"),
        _CANDIDATE_ENABLED[arm],
        f"{context} diagnostics candidate flag",
    )
    _required_mapping(
        diagnostics.get("operation_counts"),
        f"{context} diagnostics operation_counts",
    )


def _normalize_runtime_profile(
    profile: Mapping[str, Any],
    *,
    arm: str,
) -> dict[str, Any]:
    result = copy.deepcopy(dict(profile))
    configuration = _required_mutable_mapping(
        result.get("configuration"), f"{arm} normalized configuration"
    )
    configuration["d1_global_track_materialization_implementation"] = (
        _TREATMENT_MARKER
    )
    if "d1_global_track_materialization_implementation" in result:
        result["d1_global_track_materialization_implementation"] = (
            _TREATMENT_MARKER
        )
    result["d1_global_track_materialization_execution_config"] = (
        _normalized_execution_config(
            _required_mapping(
                result.get(
                    "d1_global_track_materialization_execution_config"
                ),
                f"{arm} normalized execution config",
            )
        )
    )
    result["d1_global_track_materialization_diagnostics"] = (
        _normalized_diagnostics(
            _required_mapping(
                result.get("d1_global_track_materialization_diagnostics"),
                f"{arm} normalized diagnostics",
            )
        )
    )
    return result


def _normalized_manifest(episode: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(episode["manifest"]))
    result["episode_id"] = _EPISODE_ID_MARKER
    result["runtime_profile_sha256"] = _TREATMENT_MARKER
    result["runtime_profile"] = copy.deepcopy(
        episode["normalized_runtime_profile"]
    )
    return result


def _normalized_summary(episode: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(episode["summary"]))
    result["episode_id"] = _EPISODE_ID_MARKER
    result["wall_time_s"] = _TIMING_MARKER
    result["real_time_factor"] = _TIMING_MARKER
    _normalize_materialization_container(result)
    diagnostics = _required_mutable_mapping(
        result.get("module_final_diagnostics"),
        "normalized module_final_diagnostics",
    )
    _normalize_materialization_container(diagnostics)
    stage_timings = _required_mutable_mapping(
        diagnostics.get("stage_timings"), "normalized stage_timings"
    )
    diagnostics["stage_timings"] = _normalized_stage_timing_mapping(
        stage_timings
    )
    _normalize_registered_materialization_evidence_tree(result)
    alignment = diagnostics.get("d4_current_plan_alignment")
    if isinstance(alignment, dict):
        if "d3_plan_id" in alignment:
            alignment["d3_plan_id"] = _TREATMENT_MARKER
        if isinstance(alignment.get("d4_plan_id_values"), list):
            alignment["d4_plan_id_values"] = [
                _TREATMENT_MARKER for _ in alignment["d4_plan_id_values"]
            ]
    return result


def _normalized_governance(episode: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(episode["governance"]))
    _normalize_materialization_container(result)
    _normalize_registered_materialization_evidence_tree(result)
    return result


def _normalize_registered_materialization_evidence_tree(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "d1_global_track_materialization_implementation":
                value[key] = _TREATMENT_MARKER
            elif key == "d1_global_track_materialization_execution_config":
                value[key] = _normalized_execution_config(
                    _required_mapping(item, key)
                )
            elif key in {
                "d1_global_track_materialization_diagnostics",
                "d1_publication_metadata_diagnostics",
            }:
                value[key] = _normalized_diagnostics(
                    _required_mapping(item, key)
                )
            else:
                _normalize_registered_materialization_evidence_tree(item)
    elif isinstance(value, list):
        for item in value:
            _normalize_registered_materialization_evidence_tree(item)


def _normalize_materialization_container(container: dict[str, Any]) -> None:
    container["d1_global_track_materialization_implementation"] = (
        _TREATMENT_MARKER
    )
    container["d1_global_track_materialization_execution_config"] = (
        _normalized_execution_config(
            _required_mapping(
                container.get(
                    "d1_global_track_materialization_execution_config"
                ),
                "materialization execution config",
            )
        )
    )
    container["d1_global_track_materialization_diagnostics"] = (
        _normalized_diagnostics(
            _required_mapping(
                container.get("d1_global_track_materialization_diagnostics"),
                "materialization diagnostics",
            )
        )
    )


def _normalized_execution_config(config: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(config))
    result["selector"] = _TREATMENT_MARKER
    result["implementation_id"] = _TREATMENT_MARKER
    result["candidate_enabled"] = _TREATMENT_MARKER
    return result


def _normalized_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(diagnostics))
    result["global_track_materialization_implementation_id"] = (
        _TREATMENT_MARKER
    )
    result["batched_global_track_a95_summary"] = _TREATMENT_MARKER
    operations = _required_mutable_mapping(
        result.get("operation_counts"), "normalized operation_counts"
    )
    for key in _A95_OPERATION_FIELDS:
        operations.pop(key, None)
    result["operation_counts"] = operations
    return result


def _normalized_stage_timing_mapping(
    stages: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for stage, raw_record in stages.items():
        record = copy.deepcopy(dict(_required_mapping(raw_record, str(stage))))
        for field in _TIMING_FIELDS:
            if field in record:
                record[field] = _TIMING_MARKER
        result[str(stage)] = record
    return result


def _load_stage_timing(path: Path) -> dict[str, Any]:
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required_columns = {
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
        }
        if reader.fieldnames is None or set(reader.fieldnames) != required_columns:
            raise D1GlobalTrackA95EvidenceError(
                "stage_timing_columns_unavailable_or_unexpected"
            )
        records: dict[str, dict[str, Any]] = {}
        for row_index, row in enumerate(reader, start=2):
            if row.get("schema_version") != _STAGE_TIMING_SCHEMA_VERSION:
                raise D1GlobalTrackA95EvidenceError(
                    f"stage_timing_schema_mismatch_row_{row_index}"
                )
            stage = str(row.get("stage", "")).strip()
            if not stage or stage in records:
                raise D1GlobalTrackA95EvidenceError(
                    "stage_timing_stage_missing_or_duplicate"
                )
            call_count = _parse_nonnegative_int_text(
                row.get("call_count"), f"{stage} call_count"
            )
            if call_count <= 0:
                raise D1GlobalTrackA95EvidenceError(
                    f"stage_timing_call_count_not_positive:{stage}"
                )
            record: dict[str, Any] = {
                "schema_version": row["schema_version"],
                "stage": stage,
                "call_count": call_count,
                "wall_time_s": _parse_nonnegative_float_text(
                    row.get("wall_time_s"), f"{stage} wall_time_s"
                ),
                "mean_wall_time_ms": _parse_nonnegative_float_text(
                    row.get("mean_wall_time_ms"),
                    f"{stage} mean_wall_time_ms",
                ),
                "distribution_available": _parse_bool_text(
                    row.get("distribution_available"),
                    f"{stage} distribution_available",
                ),
                "distribution_unavailable_reason": str(
                    row.get("distribution_unavailable_reason", "")
                ),
            }
            for field in (
                "p50_wall_time_ms",
                "p95_wall_time_ms",
                "max_wall_time_ms",
            ):
                raw = str(row.get(field, "")).strip()
                record[field] = (
                    None
                    if not raw
                    else _parse_nonnegative_float_text(raw, f"{stage} {field}")
                )
            if record["distribution_available"] and any(
                record[field] is None
                for field in (
                    "p50_wall_time_ms",
                    "p95_wall_time_ms",
                    "max_wall_time_ms",
                )
            ):
                raise D1GlobalTrackA95EvidenceError(
                    f"stage_timing_distribution_metric_missing:{stage}"
                )
            records[stage] = record
    if _D1_INCLUSIVE_TIMING_STAGE not in records:
        raise D1GlobalTrackA95EvidenceError(
            "required_metric_unavailable:module.d1_fusion"
        )
    normalized = {
        stage: {
            key: (_TIMING_MARKER if key in _TIMING_FIELDS else value)
            for key, value in record.items()
        }
        for stage, record in sorted(records.items())
    }
    dedicated_stage = next(
        (stage for stage in _DEDICATED_MATERIALIZATION_STAGES if stage in records),
        None,
    )
    return {
        "records": records,
        "normalized_structure": normalized,
        "inclusive_stage": _D1_INCLUSIVE_TIMING_STAGE,
        "dedicated_materialization_stage": dedicated_stage,
    }


def _audit_required_online_surfaces(episode: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(episode["paths"]["online_observations.jsonl"])
    forbidden_count = 0
    sensor_timestamps: dict[str, dict[str, Any]] = {}
    exogenous_input_surface: list[dict[str, Any]] = []
    runtime_bus_timing_surface: list[dict[str, Any]] = []
    d1_surface: list[dict[str, Any]] = []
    d2_surface: list[dict[str, Any]] = []
    timestamp_surface: list[dict[str, Any]] = []
    d1_generations: set[int] = set()
    d1_track_sample_count = 0
    d1_lineage_record_count = 0
    d2_track_sample_count = 0
    record_count = 0

    with path.open("r", encoding="utf-8") as stream:
        for record_index, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = _strict_json_loads(line, f"{path}:{record_index}")
            if not isinstance(value, dict):
                raise D1GlobalTrackA95EvidenceError(
                    f"online_record_not_mapping:{record_index}"
                )
            record = value
            record_count += 1
            forbidden_count += _count_forbidden_online_keys(record)
            runtime_bus_timing_surface.append(
                _canonical_runtime_bus_timing_record(record, record_index)
            )
            _audit_online_record(
                record,
                record_index=record_index,
                sensor_timestamps=sensor_timestamps,
                exogenous_input_surface=exogenous_input_surface,
                d1_surface=d1_surface,
                d2_surface=d2_surface,
                timestamp_surface=timestamp_surface,
                d1_generations=d1_generations,
            )

    if record_count == 0:
        raise D1GlobalTrackA95EvidenceError("online_observations_empty")
    d1_track_sample_count = sum(len(item["tracks"]) for item in d1_surface)
    d1_lineage_record_count = sum(
        len(item["observation_lineage"]) for item in d1_surface
    )
    d2_track_sample_count = sum(len(item["tracks"]) for item in d2_surface)
    if not d1_surface:
        raise D1GlobalTrackA95EvidenceError("d1_publication_evidence_unavailable")
    if not d2_surface:
        raise D1GlobalTrackA95EvidenceError("d2_input_output_evidence_unavailable")
    if not timestamp_surface:
        raise D1GlobalTrackA95EvidenceError("double_timestamp_evidence_unavailable")
    if not exogenous_input_surface:
        raise D1GlobalTrackA95EvidenceError("exogenous_sensor_input_unavailable")

    exogenous_input_surface.sort(key=_canonical_json_bytes)
    timestamp_surface.sort(key=_canonical_json_bytes)
    d1_surface.sort(key=_canonical_json_bytes)
    d2_surface.sort(key=_canonical_json_bytes)
    return {
        "exogenous_input_surface_sha256": _canonical_sha256(
            exogenous_input_surface
        ),
        "runtime_bus_timing_surface_sha256": _canonical_sha256(
            runtime_bus_timing_surface
        ),
        "d1_business_surface_sha256": _canonical_sha256(d1_surface),
        "d2_business_surface_sha256": _canonical_sha256(d2_surface),
        "timestamp_surface_sha256": _canonical_sha256(timestamp_surface),
        "forbidden_online_identity_key_count": forbidden_count,
        "exogenous_sensor_batch_count": len(exogenous_input_surface),
        "runtime_bus_record_count": record_count,
        "d1_track_sample_count": d1_track_sample_count,
        "d1_lineage_record_count": d1_lineage_record_count,
        "d2_track_sample_count": d2_track_sample_count,
        "runtime_bus_timing_surface": runtime_bus_timing_surface,
        "d1_business_surface": d1_surface,
        "d2_business_surface": d2_surface,
    }


def _audit_online_record(
    record: Mapping[str, Any],
    *,
    record_index: int,
    sensor_timestamps: dict[str, dict[str, Any]],
    exogenous_input_surface: list[dict[str, Any]],
    d1_surface: list[dict[str, Any]],
    d2_surface: list[dict[str, Any]],
    timestamp_surface: list[dict[str, Any]],
    d1_generations: set[int],
) -> None:
        topic = _required_text(record.get("topic"), f"online topic {record_index}")
        payload = _required_mapping(
            record.get("payload"), f"online payload {record_index}"
        )
        if topic == _SENSOR_OBSERVATION_TOPIC:
            exogenous_input_surface.append(
                {
                    "schema_version": _required_text(
                        record.get("schema_version"),
                        f"sensor record {record_index} schema_version",
                    ),
                    "topic": topic,
                    "source": _required_text(
                        record.get("source"), f"sensor record {record_index} source"
                    ),
                    "timestamp": _required_nonnegative_float(
                        record.get("timestamp"),
                        f"sensor record {record_index} timestamp",
                    ),
                    "payload": copy.deepcopy(dict(payload)),
                }
            )
            batch_measurement = _required_nonnegative_float(
                payload.get("measurement_timestamp"),
                f"sensor batch {record_index} measurement_timestamp",
            )
            batch_arrival = _required_nonnegative_float(
                payload.get("arrival_timestamp"),
                f"sensor batch {record_index} arrival_timestamp",
            )
            if batch_arrival + 1.0e-12 < batch_measurement:
                raise D1GlobalTrackA95EvidenceError(
                    "sensor_arrival_precedes_measurement"
                )
            measurements = _required_sequence(
                payload.get("measurements"),
                f"sensor batch {record_index} measurements",
            )
            if not measurements:
                raise D1GlobalTrackA95EvidenceError("sensor_batch_empty")
            for measurement in measurements:
                item = _required_mapping(measurement, "sensor measurement")
                observation_id = _required_text(
                    item.get("observation_id"), "sensor observation_id"
                )
                measurement_timestamp = _required_nonnegative_float(
                    item.get("measurement_timestamp"),
                    "sensor measurement_timestamp",
                )
                arrival_timestamp = _required_nonnegative_float(
                    item.get("arrival_timestamp"), "sensor arrival_timestamp"
                )
                if (
                    abs(measurement_timestamp - batch_measurement) > 1.0e-9
                    or abs(arrival_timestamp - batch_arrival) > 1.0e-9
                ):
                    raise D1GlobalTrackA95EvidenceError(
                        "sensor_batch_double_timestamp_binding_mismatch"
                    )
                item_timestamp = {
                    "observation_id": observation_id,
                    "measurement_timestamp": measurement_timestamp,
                    "arrival_timestamp": arrival_timestamp,
                }
                existing = sensor_timestamps.get(observation_id)
                if existing is not None and existing != item_timestamp:
                    raise D1GlobalTrackA95EvidenceError(
                        "observation_timestamp_identity_conflict"
                    )
                sensor_timestamps[observation_id] = item_timestamp
                timestamp_surface.append(item_timestamp)
        elif topic == _D1_FUSED_TRACK_TOPIC:
            generation = payload.get("posterior_generation")
            if generation is not None:
                generation_value = _required_nonnegative_int(
                    generation, "D1 posterior_generation"
                )
                d1_generations.add(generation_value)
            tracks = _required_sequence(payload.get("tracks"), "D1 tracks")
            canonical_tracks = [
                _canonical_track(track, context="D1") for track in tracks
            ]
            lineage = _required_sequence(
                payload.get("observation_lineage"), "D1 observation_lineage"
            )
            canonical_lineage: list[dict[str, Any]] = []
            for item in lineage:
                lineage_item = _required_mapping(item, "D1 lineage record")
                observation_id = _required_text(
                    lineage_item.get("observation_id"),
                    "D1 lineage observation_id",
                )
                source_timestamp = sensor_timestamps.get(observation_id)
                if source_timestamp is None:
                    raise D1GlobalTrackA95EvidenceError(
                        "d1_lineage_source_observation_unavailable"
                    )
                measurement_timestamp = _required_nonnegative_float(
                    lineage_item.get("measurement_timestamp"),
                    "D1 lineage measurement_timestamp",
                )
                if (
                    abs(
                        measurement_timestamp
                        - source_timestamp["measurement_timestamp"]
                    )
                    > 1.0e-9
                ):
                    raise D1GlobalTrackA95EvidenceError(
                        "d1_lineage_measurement_timestamp_mismatch"
                    )
                canonical_lineage.append(
                    {
                        "observation_id": observation_id,
                        "measurement_timestamp": measurement_timestamp,
                        "arrival_timestamp": source_timestamp[
                            "arrival_timestamp"
                        ],
                        "source_lineage": list(
                            _required_sequence(
                                lineage_item.get("source_lineage"),
                                "D1 source_lineage",
                            )
                        ),
                        "replay_generation": _required_nonnegative_int(
                            lineage_item.get("replay_generation"),
                            "D1 replay_generation",
                        ),
                    }
                )
            d1_surface.append(
                {
                    "batch_id": _required_text(
                        payload.get("batch_id"), "D1 batch_id"
                    ),
                    "sensor_id": _required_text(
                        payload.get("sensor_id"), "D1 sensor_id"
                    ),
                    "posterior_generation": generation,
                    "tracks_materialized": _required_bool(
                        payload.get("tracks_materialized"),
                        "D1 tracks_materialized",
                    ),
                    "snapshot_kind": _required_text(
                        payload.get("snapshot_kind"), "D1 snapshot_kind"
                    ),
                    "tracks": canonical_tracks,
                    "observation_lineage": canonical_lineage,
                    "structural_ambiguity_evidence_count": (
                        _required_nonnegative_int(
                            payload.get("structural_ambiguity_evidence_count"),
                            "D1 structural_ambiguity_evidence_count",
                        )
                    ),
                    "structural_ambiguity_evidence": copy.deepcopy(
                        list(
                            _required_sequence(
                                payload.get("structural_ambiguity_evidence"),
                                "D1 structural_ambiguity_evidence",
                            )
                        )
                    ),
                }
            )
        elif topic == _D2_ASSOCIATED_TRACK_TOPIC:
            source_generation = _required_nonnegative_int(
                payload.get("source_d1_posterior_generation"),
                "D2 source_d1_posterior_generation",
            )
            if source_generation not in d1_generations:
                raise D1GlobalTrackA95EvidenceError(
                    "d2_input_not_bound_to_preceding_d1_generation"
                )
            tracks = _required_sequence(payload.get("tracks"), "D2 tracks")
            canonical_tracks = [
                _canonical_track(track, context="D2") for track in tracks
            ]
            id_switch_available = _required_bool(
                payload.get("id_switch_count_available"),
                "D2 id_switch_count_available",
            )
            id_switch_count = payload.get("id_switch_count")
            if id_switch_available:
                id_switch_count = _required_nonnegative_int(
                    id_switch_count, "D2 id_switch_count"
                )
            elif id_switch_count is not None:
                raise D1GlobalTrackA95EvidenceError(
                    "d2_unavailable_id_switch_count_must_be_null"
                )
            d2_surface.append(
                {
                    "source_d1_posterior_generation": source_generation,
                    "tracks": canonical_tracks,
                    "id_switch_count": id_switch_count,
                    "id_switch_count_available": id_switch_available,
                    "identity_lineage": copy.deepcopy(
                        list(
                            _required_sequence(
                                payload.get("identity_lineage"),
                                "D2 identity_lineage",
                            )
                        )
                    ),
                    "identity_lineage_policy": _required_text(
                        payload.get("identity_lineage_policy"),
                        "D2 identity_lineage_policy",
                    ),
                    "association": copy.deepcopy(
                        dict(
                            _required_mapping(
                                payload.get("association"), "D2 association"
                            )
                        )
                    ),
                }
            )


def _canonical_runtime_bus_timing_record(
    record: Mapping[str, Any], record_index: int
) -> dict[str, Any]:
    payload = _required_mapping(
        record.get("payload"), f"online payload {record_index}"
    )
    return {
        "record_index": record_index,
        "sequence": _required_nonnegative_int(
            record.get("sequence"), f"online sequence {record_index}"
        ),
        "topic": _required_text(record.get("topic"), f"online topic {record_index}"),
        "source": _required_text(
            record.get("source"), f"online source {record_index}"
        ),
        "timestamp": _required_nonnegative_float(
            record.get("timestamp"), f"online timestamp {record_index}"
        ),
        "payload_timing_and_transport": _extract_runtime_timing_and_transport(
            payload
        ),
    }


def _extract_runtime_timing_and_transport(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if _is_runtime_timing_or_transport_key(name):
                result[name] = copy.deepcopy(item)
                continue
            nested = _extract_runtime_timing_and_transport(item)
            if nested not in ({}, [], None):
                result[name] = nested
        return result
    if isinstance(value, (list, tuple)):
        result = [_extract_runtime_timing_and_transport(item) for item in value]
        return result if any(item not in ({}, [], None) for item in result) else []
    return None


def _is_runtime_timing_or_transport_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _RUNTIME_TRANSPORT_METADATA_KEYS:
        return True
    if "timestamp" in normalized:
        return True
    return normalized.endswith(
        (
            "_at_s",
            "_until_s",
            "_from_s",
            "_time_s",
            "_latency_s",
            "_latency_ms",
            "_ttl_s",
            "_duration_s",
            "_age_s",
            "_period_s",
            "_grace_s",
        )
    )


def _surface_mismatch_paths(
    reference: Any, candidate: Any, *, limit: int
) -> list[str]:
    paths: list[str] = []
    for path in _difference_paths(reference, candidate):
        paths.append(path)
        if len(paths) >= limit:
            break
    return paths


def _difference_paths(reference: Any, candidate: Any, path: str = "$") -> Any:
    if type(reference) is not type(candidate):
        yield path
        return
    if isinstance(reference, Mapping):
        for key in sorted(set(reference) | set(candidate)):
            child_path = f"{path}.{key}"
            if key not in reference or key not in candidate:
                yield child_path
            else:
                yield from _difference_paths(
                    reference[key], candidate[key], child_path
                )
        return
    if isinstance(reference, list):
        if len(reference) != len(candidate):
            yield f"{path}.length"
        for index, (left, right) in enumerate(zip(reference, candidate)):
            yield from _difference_paths(left, right, f"{path}[{index}]")
        return
    if reference != candidate:
        yield path


def _canonical_track(value: Any, *, context: str) -> dict[str, Any]:
    track = _required_mapping(value, f"{context} track")
    state = np.asarray(track.get("state_ned"), dtype=float)
    covariance = np.asarray(track.get("covariance"), dtype=float)
    if state.shape != (6,) or not np.all(np.isfinite(state)):
        raise D1GlobalTrackA95EvidenceError(
            f"{context.lower()}_track_state_invalid"
        )
    if covariance.shape != (6, 6) or not np.all(np.isfinite(covariance)):
        raise D1GlobalTrackA95EvidenceError(
            f"{context.lower()}_track_covariance_invalid"
        )
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-10):
        raise D1GlobalTrackA95EvidenceError(
            f"{context.lower()}_track_covariance_not_symmetric"
        )
    position_covariance = covariance[:2, :2]
    largest = float(np.linalg.eigvalsh(position_covariance)[-1])
    a95_m = math.sqrt(_CHI2_2_95 * max(largest, 0.0))
    return {
        "global_track_id": _required_text(
            track.get("global_track_id"), f"{context} global_track_id"
        ),
        "timestamp": _required_nonnegative_float(
            track.get("timestamp"), f"{context} track timestamp"
        ),
        "state_ned": state.tolist(),
        "covariance": covariance.tolist(),
        "a95_m_derived_from_xy_covariance": a95_m,
        "track_level": _required_text(
            track.get("track_state"), f"{context} track_state"
        ),
    }


def _operation_checks(
    reference: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, bool]:
    ref = reference["operation_counts"]
    cand = candidate["operation_counts"]
    common_ref = {
        key: value for key, value in ref.items() if key not in _A95_OPERATION_FIELDS
    }
    common_cand = {
        key: value for key, value in cand.items() if key not in _A95_OPERATION_FIELDS
    }
    materialized = int(ref["global_track_metadata_materialization_count"])
    candidate_materialized = int(
        cand["global_track_metadata_materialization_count"]
    )
    reference_scalar = int(ref.get("per_track_a95_summary_call_count", 0))
    candidate_scalar = int(cand.get("per_track_a95_summary_call_count", 0))
    candidate_build = int(cand.get("batched_a95_summary_build_count", 0))
    candidate_eig = int(cand.get("batched_a95_eigvalsh_call_count", 0))
    candidate_matrix = int(cand.get("batched_a95_summary_matrix_count", 0))
    candidate_reuse = int(cand.get("batched_a95_summary_reuse_count", 0))
    return {
        "common_operation_counts_equal": common_ref == common_cand,
        "materialized_track_count_positive": materialized > 0,
        "materialized_track_count_equal": materialized == candidate_materialized,
        "reference_scalar_a95_count_complete": reference_scalar == materialized,
        "reference_batched_a95_count_zero": all(
            int(ref.get(field, 0)) == 0
            for field in _A95_OPERATION_FIELDS
            if field != "per_track_a95_summary_call_count"
        ),
        "candidate_scalar_a95_count_zero": candidate_scalar == 0,
        "candidate_batched_call_exercised": candidate_build > 0 and candidate_eig > 0,
        "candidate_batched_eigvalsh_bounded": 0 < candidate_eig <= candidate_build,
        "candidate_batched_matrix_count_complete": (
            candidate_matrix == candidate_materialized
        ),
        "candidate_batched_reuse_count_complete": (
            candidate_reuse == candidate_materialized
        ),
    }


def _arm_metrics(
    episode: Mapping[str, Any], operations: Mapping[str, Any]
) -> dict[str, Any]:
    counts = operations["operation_counts"]
    timing = episode["stage_timing"]
    inclusive = timing["records"][_D1_INCLUSIVE_TIMING_STAGE]
    dedicated_stage = timing["dedicated_materialization_stage"]
    dedicated_wall = (
        None
        if dedicated_stage is None
        else timing["records"][dedicated_stage]["wall_time_s"]
    )
    return {
        "episode_id": str(
            episode["summary"].get(
                "episode_id", episode["manifest"].get("episode_id", "")
            )
        ),
        "git_commit": str(episode["manifest"]["git_commit"]),
        "selector": episode["summary"][
            "d1_global_track_materialization_implementation"
        ],
        "wall_time_s": float(episode["summary"]["wall_time_s"]),
        "d1_publication_materialization_inclusive_stage": (
            _D1_INCLUSIVE_TIMING_STAGE
        ),
        "d1_publication_materialization_inclusive_wall_s": float(
            inclusive["wall_time_s"]
        ),
        "dedicated_materialization_timing_available": (
            dedicated_stage is not None
        ),
        "dedicated_materialization_stage": dedicated_stage,
        "dedicated_materialization_wall_s": dedicated_wall,
        "scalar_a95_count": int(
            counts.get("per_track_a95_summary_call_count", 0)
        ),
        "batched_build_count": int(
            counts.get("batched_a95_summary_build_count", 0)
        ),
        "batched_eigvalsh_call_count": int(
            counts.get("batched_a95_eigvalsh_call_count", 0)
        ),
        "batched_matrix_count": int(
            counts.get("batched_a95_summary_matrix_count", 0)
        ),
        "batched_reuse_count": int(
            counts.get("batched_a95_summary_reuse_count", 0)
        ),
        "global_tracks_call_count": int(counts["global_tracks_call_count"]),
        "materialized_track_count": int(
            counts["global_track_metadata_materialization_count"]
        ),
    }


def _comparison_key(episode: Mapping[str, Any]) -> dict[str, Any]:
    scenario = episode["scenario"]
    return {
        "scenario_name": _required_text(
            scenario.get("scenario_name"), "scenario_name"
        ),
        "scenario_version": _required_text(
            scenario.get("scenario_version"), "scenario_version"
        ),
        "seed": _required_int(scenario.get("seed"), "scenario seed"),
        "target_count": _required_positive_int(
            scenario.get("target_count"), "target_count"
        ),
        "resource_count": _required_positive_int(
            scenario.get("resource_count"), "resource_count"
        ),
        "recon_count": _required_nonnegative_int(
            scenario.get("recon_count"), "recon_count"
        ),
        "duration_s": _required_positive_float(
            scenario.get("duration_s"), "duration_s"
        ),
        "config_sha256": _required_sha256(
            episode["manifest"].get("config_sha256"), "config_sha256"
        ),
    }


def _validate_explicit_comparison_key(
    value: Any, pair_id: str
) -> dict[str, Any]:
    mapping = _required_mapping(value, f"{pair_id} comparison_key")
    if set(mapping) != set(_COMPARISON_KEY_FIELDS):
        raise D1GlobalTrackA95EvidenceError(
            "comparison_key_fields_invalid"
        )
    return {
        "scenario_name": _required_text(
            mapping.get("scenario_name"), "comparison scenario_name"
        ),
        "scenario_version": _required_text(
            mapping.get("scenario_version"), "comparison scenario_version"
        ),
        "seed": _required_int(mapping.get("seed"), "comparison seed"),
        "target_count": _required_positive_int(
            mapping.get("target_count"), "comparison target_count"
        ),
        "resource_count": _required_positive_int(
            mapping.get("resource_count"), "comparison resource_count"
        ),
        "recon_count": _required_nonnegative_int(
            mapping.get("recon_count"), "comparison recon_count"
        ),
        "duration_s": _required_positive_float(
            mapping.get("duration_s"), "comparison duration_s"
        ),
        "config_sha256": _required_sha256(
            mapping.get("config_sha256"), "comparison config_sha256"
        ),
    }


def _load_pair_bindings(source: Path) -> list[dict[str, Any]]:
    if source.is_file():
        pair_list = _load_strict_json_mapping(source)
        if pair_list.get("schema_version") != (
            D1_GLOBAL_TRACK_A95_PAIR_LIST_SCHEMA_VERSION
        ):
            raise D1GlobalTrackA95EvidenceError("pair_list_schema_mismatch")
        if set(pair_list) != {"schema_version", "pairs"}:
            raise D1GlobalTrackA95EvidenceError("pair_list_fields_invalid")
        raw_pairs = _required_sequence(pair_list.get("pairs"), "pair list pairs")
        if not raw_pairs:
            raise D1GlobalTrackA95EvidenceError("pair_list_empty")
        bindings: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, raw_pair in enumerate(raw_pairs):
            pair = _required_mapping(raw_pair, f"pair {index}")
            if set(pair) != {
                "pair_id",
                "comparison_key",
                "reference_episode_dir",
                "candidate_episode_dir",
            }:
                raise D1GlobalTrackA95EvidenceError("pair_binding_fields_invalid")
            pair_id = _required_text(pair.get("pair_id"), "pair_id")
            if pair_id in seen_ids:
                raise D1GlobalTrackA95EvidenceError("pair_id_duplicate")
            seen_ids.add(pair_id)
            bindings.append(
                {
                    "pair_id": pair_id,
                    "comparison_key": copy.deepcopy(pair["comparison_key"]),
                    "reference_episode_dir": _resolve_explicit_episode_path(
                        source.parent, pair.get("reference_episode_dir")
                    ),
                    "candidate_episode_dir": _resolve_explicit_episode_path(
                        source.parent, pair.get("candidate_episode_dir")
                    ),
                }
            )
        return bindings
    if not source.is_dir():
        raise D1GlobalTrackA95EvidenceError("paired_source_missing")
    arm_seed_bindings = _arm_seed_directory_bindings(source)
    if arm_seed_bindings is not None:
        return arm_seed_bindings
    direct = _directory_pair_binding(source, source.name or "pair-0001")
    if direct is not None:
        return [direct]
    bindings = []
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        if not child.is_dir():
            continue
        binding = _directory_pair_binding(child, child.name)
        if binding is not None:
            bindings.append(binding)
    if not bindings:
        raise D1GlobalTrackA95EvidenceError(
            "paired_directory_contains_no_reference_candidate_pairs"
        )
    return bindings


def _directory_pair_binding(root: Path, pair_id: str) -> dict[str, Any] | None:
    name_pairs = (
        ("reference", "candidate"),
        ("reference_episode", "candidate_episode"),
    )
    for reference_name, candidate_name in name_pairs:
        reference = root / reference_name
        candidate = root / candidate_name
        if (
            reference.is_dir()
            and candidate.is_dir()
            and (reference / "manifest.json").is_file()
            and (candidate / "manifest.json").is_file()
        ):
            return {
                "pair_id": pair_id,
                "comparison_key": None,
                "reference_episode_dir": reference.resolve(),
                "candidate_episode_dir": candidate.resolve(),
            }
    return None


def _arm_seed_directory_bindings(
    root: Path,
) -> list[dict[str, Any]] | None:
    reference_root = root / _REFERENCE_ARM
    candidate_root = root / _CANDIDATE_ARM
    arm_root_exists = reference_root.is_dir() or candidate_root.is_dir()
    if not arm_root_exists:
        return None
    if not reference_root.is_dir() or not candidate_root.is_dir():
        raise D1GlobalTrackA95EvidenceError(
            "reference_candidate_arm_directory_set_incomplete"
        )
    if (reference_root / "manifest.json").is_file() or (
        candidate_root / "manifest.json"
    ).is_file():
        return None

    reference_seeds = _discover_seed_episode_dirs(reference_root, _REFERENCE_ARM)
    candidate_seeds = _discover_seed_episode_dirs(candidate_root, _CANDIDATE_ARM)
    if set(reference_seeds) != set(candidate_seeds):
        missing_candidate = sorted(set(reference_seeds) - set(candidate_seeds))
        missing_reference = sorted(set(candidate_seeds) - set(reference_seeds))
        detail = (
            f"missing_candidate={','.join(missing_candidate) or '-'};"
            f"missing_reference={','.join(missing_reference) or '-'}"
        )
        raise D1GlobalTrackA95EvidenceError(
            f"reference_candidate_seed_directory_set_mismatch:{detail}"
        )
    return [
        {
            "pair_id": seed_name,
            "comparison_key": None,
            "reference_episode_dir": reference_seeds[seed_name],
            "candidate_episode_dir": candidate_seeds[seed_name],
        }
        for seed_name in sorted(
            reference_seeds,
            key=lambda name: int(name.removeprefix("seed_")),
        )
    ]


def _discover_seed_episode_dirs(root: Path, arm: str) -> dict[str, Path]:
    episodes: dict[str, Path] = {}
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or re.fullmatch(r"seed_[0-9]+", child.name) is None:
            continue
        if not (child / "manifest.json").is_file():
            raise D1GlobalTrackA95EvidenceError(
                f"{arm}_seed_manifest_missing:{child.name}"
            )
        episodes[child.name] = child.resolve()
    if not episodes:
        raise D1GlobalTrackA95EvidenceError(
            f"{arm}_arm_contains_no_seed_episode_directories"
        )
    return episodes


def _resolve_explicit_episode_path(base: Path, value: Any) -> Path:
    raw = _required_text(value, "episode path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _aggregate_evaluation(
    source: Path, pairs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    available = [pair for pair in pairs if pair.get("available") is True]
    exact = [pair for pair in available if pair.get("business_equivalent") is True]
    passed = [pair for pair in available if pair.get("pair_passed") is True]
    unavailable = [pair for pair in pairs if pair.get("available") is not True]
    exogenous_equal = [
        pair for pair in pairs if pair.get("exogenous_input_equivalent") is True
    ]
    runtime_timing_equal = [
        pair for pair in available if pair.get("runtime_bus_timing_equivalent") is True
    ]
    runtime_timing_drift = [
        pair for pair in available if pair.get("runtime_bus_timing_equivalent") is False
    ]
    timing_induced_divergence = [
        pair
        for pair in pairs
        if pair.get("comparison_disposition")
        == "runtime_timing_induced_business_divergence"
    ]
    candidate_faster = [pair for pair in available if pair.get("candidate_faster")]
    wall_improvements = [
        float(pair["wall_improvement_percent"]) for pair in available
    ]
    d1_improvements = [
        float(pair["d1_publication_materialization_improvement_percent"])
        for pair in available
    ]
    reason_counts: Counter[str] = Counter()
    for pair in pairs:
        reason_counts.update(str(reason) for reason in pair.get("failure_reasons", ()))

    minimum_count_met = len(available) >= MINIMUM_DESCRIPTIVE_PAIR_COUNT
    faster_fraction = (
        None if not available else len(candidate_faster) / len(available)
    )
    median_wall_improvement = (
        None if not wall_improvements else float(median(wall_improvements))
    )
    descriptive_performance_gates = {
        "minimum_pair_count_met": minimum_count_met,
        "candidate_faster_fraction_at_least_0_80": (
            False
            if faster_fraction is None
            else faster_fraction >= MINIMUM_CANDIDATE_FASTER_FRACTION
        ),
        "median_wall_improvement_at_least_10_percent": (
            False
            if median_wall_improvement is None
            else median_wall_improvement
            >= MINIMUM_MEDIAN_IMPROVEMENT_PERCENT
        ),
        "all_available_pairs_business_exact": (
            bool(available) and len(exact) == len(available)
        ),
        "all_requested_pairs_available": len(unavailable) == 0,
        "all_exogenous_inputs_equivalent": (
            bool(pairs) and len(exogenous_equal) == len(pairs)
        ),
        "all_operation_contracts_passed": (
            bool(available)
            and all(pair.get("operation_contract_passed") for pair in available)
        ),
    }
    aggregate = {
        "schema_version": D1_GLOBAL_TRACK_A95_AGGREGATE_SCHEMA_VERSION,
        "pair_count": len(pairs),
        "available_pair_count": len(available),
        "unavailable_pair_count": len(unavailable),
        "failed_pair_count": len(available) - len(passed),
        "passed_pair_count": len(passed),
        "exact_equivalent_pair_count": len(exact),
        "exact_equivalence_rate": (
            None if not available else len(exact) / len(available)
        ),
        "candidate_faster_pair_count": len(candidate_faster),
        "candidate_faster_fraction": faster_fraction,
        "exogenous_input_equivalent_pair_count": len(exogenous_equal),
        "exogenous_input_equivalence_rate": (
            None if not pairs else len(exogenous_equal) / len(pairs)
        ),
        "runtime_bus_timing_equivalent_pair_count": len(runtime_timing_equal),
        "runtime_bus_timing_equivalence_rate": (
            None if not available else len(runtime_timing_equal) / len(available)
        ),
        "runtime_bus_timing_drift_pair_count": len(runtime_timing_drift),
        "runtime_timing_induced_business_divergence_pair_count": len(
            timing_induced_divergence
        ),
        "reference_wall_time_mean_s": _arm_mean(available, "reference", "wall_time_s"),
        "candidate_wall_time_mean_s": _arm_mean(available, "candidate", "wall_time_s"),
        "reference_d1_publication_materialization_mean_s": _arm_mean(
            available,
            "reference",
            "d1_publication_materialization_inclusive_wall_s",
        ),
        "candidate_d1_publication_materialization_mean_s": _arm_mean(
            available,
            "candidate",
            "d1_publication_materialization_inclusive_wall_s",
        ),
        "median_wall_improvement_percent": median_wall_improvement,
        "median_d1_publication_materialization_improvement_percent": (
            None if not d1_improvements else float(median(d1_improvements))
        ),
        "reference_scalar_a95_count": _arm_sum(
            available, "reference", "scalar_a95_count"
        ),
        "candidate_scalar_a95_count": _arm_sum(
            available, "candidate", "scalar_a95_count"
        ),
        "candidate_batched_build_count": _arm_sum(
            available, "candidate", "batched_build_count"
        ),
        "candidate_batched_eigvalsh_call_count": _arm_sum(
            available, "candidate", "batched_eigvalsh_call_count"
        ),
        "candidate_batched_matrix_count": _arm_sum(
            available, "candidate", "batched_matrix_count"
        ),
        "failure_reason_counts": dict(sorted(reason_counts.items())),
        "sample_sufficiency": {
            "minimum_pair_count": MINIMUM_DESCRIPTIVE_PAIR_COUNT,
            "available_pair_count": len(available),
            "minimum_pair_count_met": minimum_count_met,
            "small_sample": not minimum_count_met,
            "formal_promotion_claimed": False,
        },
        "descriptive_performance_gates": descriptive_performance_gates,
        "formal_admission_decision": "not_authorized_by_this_evaluator",
    }
    evaluation_passed = (
        bool(pairs)
        and not unavailable
        and all(pair.get("pair_passed") is True for pair in pairs)
    )
    return {
        "schema_version": D1_GLOBAL_TRACK_A95_EPISODE_AB_SCHEMA_VERSION,
        "evaluator_baseline_commit": (
            D1_GLOBAL_TRACK_A95_EVALUATOR_BASELINE_COMMIT
        ),
        "source": str(source),
        "status": "passed" if evaluation_passed else "fail_closed",
        "availability": {
            "available": bool(pairs) and not unavailable,
            "reasons": sorted(
                {
                    reason
                    for pair in unavailable
                    for reason in pair.get("failure_reasons", ())
                }
            ),
        },
        "reference_selector": REFERENCE_SELECTOR,
        "candidate_selector": CANDIDATE_SELECTOR,
        "candidate_default_off": True,
        "reserved_formal_seed_payload_read": False,
        "formal_shards_10_19_run": False,
        "existing_formal_450_of_900_conclusion_modified": False,
        "evaluation_passed": evaluation_passed,
        "formal_promotion_supported": False,
        "aggregate": aggregate,
        "pairs": list(pairs),
    }


def _unavailable_evaluation(source: Path, reason: str) -> dict[str, Any]:
    code = _reason_code(D1GlobalTrackA95EvidenceError(reason))
    return {
        "schema_version": D1_GLOBAL_TRACK_A95_EPISODE_AB_SCHEMA_VERSION,
        "evaluator_baseline_commit": (
            D1_GLOBAL_TRACK_A95_EVALUATOR_BASELINE_COMMIT
        ),
        "source": str(source),
        "status": "unavailable",
        "availability": {"available": False, "reasons": [code]},
        "reference_selector": REFERENCE_SELECTOR,
        "candidate_selector": CANDIDATE_SELECTOR,
        "candidate_default_off": True,
        "reserved_formal_seed_payload_read": False,
        "formal_shards_10_19_run": False,
        "existing_formal_450_of_900_conclusion_modified": False,
        "evaluation_passed": False,
        "formal_promotion_supported": False,
        "aggregate": {
            "schema_version": D1_GLOBAL_TRACK_A95_AGGREGATE_SCHEMA_VERSION,
            "pair_count": 0,
            "available_pair_count": 0,
            "unavailable_pair_count": 0,
            "failed_pair_count": 0,
            "passed_pair_count": 0,
            "exact_equivalent_pair_count": 0,
            "exact_equivalence_rate": None,
            "candidate_faster_pair_count": 0,
            "candidate_faster_fraction": None,
            "exogenous_input_equivalent_pair_count": 0,
            "exogenous_input_equivalence_rate": None,
            "runtime_bus_timing_equivalent_pair_count": 0,
            "runtime_bus_timing_equivalence_rate": None,
            "runtime_bus_timing_drift_pair_count": 0,
            "runtime_timing_induced_business_divergence_pair_count": 0,
            "reference_wall_time_mean_s": None,
            "candidate_wall_time_mean_s": None,
            "reference_d1_publication_materialization_mean_s": None,
            "candidate_d1_publication_materialization_mean_s": None,
            "median_wall_improvement_percent": None,
            "median_d1_publication_materialization_improvement_percent": None,
            "reference_scalar_a95_count": None,
            "candidate_scalar_a95_count": None,
            "candidate_batched_build_count": None,
            "candidate_batched_eigvalsh_call_count": None,
            "candidate_batched_matrix_count": None,
            "failure_reason_counts": {code: 1},
            "sample_sufficiency": {
                "minimum_pair_count": MINIMUM_DESCRIPTIVE_PAIR_COUNT,
                "available_pair_count": 0,
                "minimum_pair_count_met": False,
                "small_sample": True,
                "formal_promotion_claimed": False,
            },
            "descriptive_performance_gates": {},
            "formal_admission_decision": "not_authorized_by_this_evaluator",
        },
        "pairs": [],
    }


def _episode_fingerprint(episode: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: {
            "size": path.stat().st_size,
            "mtime_ns": path.stat().st_mtime_ns,
            "sha256": _file_sha256(path),
        }
        for name, path in sorted(episode["paths"].items())
    }


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = _strict_json_loads(line, f"{path}:{line_number}")
            if not isinstance(value, dict):
                raise D1GlobalTrackA95EvidenceError(
                    f"online_record_not_mapping:{line_number}"
                )
            records.append(value)
    if not records:
        raise D1GlobalTrackA95EvidenceError("online_observations_empty")
    return records


def _count_forbidden_online_keys(value: Any) -> int:
    if isinstance(value, Mapping):
        count = sum(
            str(key).strip().lower() in _FORBIDDEN_ONLINE_IDENTITY_KEYS
            for key in value
        )
        return count + sum(_count_forbidden_online_keys(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(_count_forbidden_online_keys(item) for item in value)
    return 0


def _write_pair_csv(path: Path, evaluation: Mapping[str, Any]) -> None:
    fields = (
        "pair_id",
        "scenario_name",
        "scenario_version",
        "seed",
        "target_count",
        "resource_count",
        "recon_count",
        "status",
        "available",
        "comparison_disposition",
        "exogenous_input_equivalent",
        "runtime_bus_timing_equivalent",
        "business_equivalent",
        "operation_contract_passed",
        "pair_passed",
        "reference_wall_time_s",
        "candidate_wall_time_s",
        "wall_improvement_percent",
        "reference_d1_publication_materialization_inclusive_wall_s",
        "candidate_d1_publication_materialization_inclusive_wall_s",
        "d1_publication_materialization_improvement_percent",
        "reference_scalar_a95_count",
        "candidate_scalar_a95_count",
        "candidate_batched_build_count",
        "candidate_batched_eigvalsh_call_count",
        "candidate_batched_matrix_count",
        "failure_reasons",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for pair in _required_sequence(evaluation.get("pairs"), "pairs"):
            key = pair.get("comparison_key") or {}
            reference = pair.get("reference") or {}
            candidate = pair.get("candidate") or {}
            writer.writerow(
                {
                    "pair_id": pair.get("pair_id"),
                    "scenario_name": key.get("scenario_name"),
                    "scenario_version": key.get("scenario_version"),
                    "seed": key.get("seed"),
                    "target_count": key.get("target_count"),
                    "resource_count": key.get("resource_count"),
                    "recon_count": key.get("recon_count"),
                    "status": pair.get("status"),
                    "available": pair.get("available"),
                    "comparison_disposition": pair.get(
                        "comparison_disposition"
                    ),
                    "exogenous_input_equivalent": pair.get(
                        "exogenous_input_equivalent"
                    ),
                    "runtime_bus_timing_equivalent": pair.get(
                        "runtime_bus_timing_equivalent"
                    ),
                    "business_equivalent": pair.get("business_equivalent"),
                    "operation_contract_passed": pair.get(
                        "operation_contract_passed"
                    ),
                    "pair_passed": pair.get("pair_passed"),
                    "reference_wall_time_s": reference.get("wall_time_s"),
                    "candidate_wall_time_s": candidate.get("wall_time_s"),
                    "wall_improvement_percent": pair.get(
                        "wall_improvement_percent"
                    ),
                    "reference_d1_publication_materialization_inclusive_wall_s": reference.get(
                        "d1_publication_materialization_inclusive_wall_s"
                    ),
                    "candidate_d1_publication_materialization_inclusive_wall_s": candidate.get(
                        "d1_publication_materialization_inclusive_wall_s"
                    ),
                    "d1_publication_materialization_improvement_percent": pair.get(
                        "d1_publication_materialization_improvement_percent"
                    ),
                    "reference_scalar_a95_count": reference.get(
                        "scalar_a95_count"
                    ),
                    "candidate_scalar_a95_count": candidate.get(
                        "scalar_a95_count"
                    ),
                    "candidate_batched_build_count": candidate.get(
                        "batched_build_count"
                    ),
                    "candidate_batched_eigvalsh_call_count": candidate.get(
                        "batched_eigvalsh_call_count"
                    ),
                    "candidate_batched_matrix_count": candidate.get(
                        "batched_matrix_count"
                    ),
                    "failure_reasons": ";".join(pair.get("failure_reasons", ())),
                }
            )


def _arm_mean(
    pairs: Sequence[Mapping[str, Any]], arm: str, metric: str
) -> float | None:
    values = [float(pair[arm][metric]) for pair in pairs]
    return None if not values else float(fmean(values))


def _arm_sum(
    pairs: Sequence[Mapping[str, Any]], arm: str, metric: str
) -> int | None:
    return None if not pairs else sum(int(pair[arm][metric]) for pair in pairs)


def _improvement_percent(reference: float, candidate: float) -> float:
    if reference <= 0.0:
        raise D1GlobalTrackA95EvidenceError("reference_timing_not_positive")
    return 100.0 * (float(reference) - float(candidate)) / float(reference)


def _load_strict_json_mapping(path: Path) -> dict[str, Any]:
    value = _strict_json_loads(path.read_text(encoding="utf-8"), str(path))
    if not isinstance(value, dict):
        raise D1GlobalTrackA95EvidenceError(f"expected_json_mapping:{path.name}")
    return value


def _strict_json_loads(text: str, context: str) -> Any:
    def reject_constant(value: str) -> None:
        raise _StrictJSONConstantError(value)

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise D1GlobalTrackA95EvidenceError(
                    f"duplicate_json_key:{context}:{key}"
                )
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            parse_constant=reject_constant,
            object_pairs_hook=no_duplicates,
        )
    except _StrictJSONConstantError as exc:
        raise D1GlobalTrackA95EvidenceError(
            f"non_finite_json_constant:{context}:{exc}"
        ) from exc


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D1GlobalTrackA95EvidenceError(f"required_mapping_unavailable:{name}")
    return value


def _required_mutable_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise D1GlobalTrackA95EvidenceError(
            f"required_mutable_mapping_unavailable:{name}"
        )
    return value


def _required_sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise D1GlobalTrackA95EvidenceError(f"required_sequence_unavailable:{name}")
    return value


def _required_text(value: Any, name: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise D1GlobalTrackA95EvidenceError(f"required_text_unavailable:{name}")
    return result


def _required_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise D1GlobalTrackA95EvidenceError(f"required_integer_unavailable:{name}")
    return int(value)


def _required_nonnegative_int(value: Any, name: str) -> int:
    result = _required_int(value, name)
    if result < 0:
        raise D1GlobalTrackA95EvidenceError(f"negative_integer:{name}")
    return result


def _required_positive_int(value: Any, name: str) -> int:
    result = _required_int(value, name)
    if result <= 0:
        raise D1GlobalTrackA95EvidenceError(f"nonpositive_integer:{name}")
    return result


def _required_nonnegative_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise D1GlobalTrackA95EvidenceError(f"required_numeric_unavailable:{name}")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise D1GlobalTrackA95EvidenceError(f"invalid_nonnegative_numeric:{name}")
    return result


def _required_positive_float(value: Any, name: str) -> float:
    result = _required_nonnegative_float(value, name)
    if result <= 0.0:
        raise D1GlobalTrackA95EvidenceError(f"nonpositive_numeric:{name}")
    return result


def _required_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise D1GlobalTrackA95EvidenceError(f"required_bool_unavailable:{name}")
    return value


def _required_sha256(value: Any, name: str) -> str:
    result = _required_text(value, name)
    if _SHA256_RE.fullmatch(result) is None:
        raise D1GlobalTrackA95EvidenceError(f"invalid_sha256:{name}")
    return result


def _parse_nonnegative_int_text(value: Any, name: str) -> int:
    raw = str(value).strip() if value is not None else ""
    if not raw or not raw.isdigit():
        raise D1GlobalTrackA95EvidenceError(f"invalid_integer_text:{name}")
    return _required_nonnegative_int(int(raw), name)


def _parse_nonnegative_float_text(value: Any, name: str) -> float:
    raw = str(value).strip() if value is not None else ""
    if not raw:
        raise D1GlobalTrackA95EvidenceError(f"missing_numeric_text:{name}")
    try:
        numeric = float(raw)
    except ValueError as exc:
        raise D1GlobalTrackA95EvidenceError(
            f"invalid_numeric_text:{name}"
        ) from exc
    return _required_nonnegative_float(numeric, name)


def _parse_bool_text(value: Any, name: str) -> bool:
    raw = str(value).strip().lower() if value is not None else ""
    if raw not in {"true", "false"}:
        raise D1GlobalTrackA95EvidenceError(f"invalid_bool_text:{name}")
    return raw == "true"


def _expect_equal(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise D1GlobalTrackA95EvidenceError(f"contract_mismatch:{name}")


def _reason_code(exc: BaseException) -> str:
    text = str(exc).strip().replace("\n", " ")
    return text or type(exc).__name__


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _format_optional_ratio(value: Any) -> str:
    return "不可用" if value is None else f"{100.0 * float(value):.3f}%"


def _format_optional_number(value: Any, *, suffix: str = "") -> str:
    return "不可用" if value is None else f"{float(value):.3f}{suffix}"


def _format_optional_integer(value: Any) -> str:
    return "不可用" if value is None else f"{int(value):,}"


def _yes_no_unknown(value: Any) -> str:
    if value is None:
        return "不可用"
    return "是" if value is True else "否"


def _format_pair_metric(pair: Mapping[str, Any], metric: str) -> str:
    reference = pair.get("reference")
    candidate = pair.get("candidate")
    if not isinstance(reference, Mapping) or not isinstance(candidate, Mapping):
        return "不可用"
    left = reference.get(metric)
    right = candidate.get(metric)
    if left is None or right is None:
        return "不可用"
    return f"{float(left):.6f}/{float(right):.6f}"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="独立评估 D1 GlobalTrack A95 reference/candidate paired episodes"
    )
    parser.add_argument(
        "source", help="paired episode 目录或显式 pair-list JSON"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mismatch-limit", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    evaluation = evaluate_d1_global_track_a95_episode_ab(
        args.source, mismatch_limit=args.mismatch_limit
    )
    paths = write_d1_global_track_a95_episode_ab_report(
        evaluation, args.output_dir
    )
    print(f"status={evaluation['status']}")
    for name, path in paths.items():
        print(f"{name}={path}")
    return 0 if evaluation.get("evaluation_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
