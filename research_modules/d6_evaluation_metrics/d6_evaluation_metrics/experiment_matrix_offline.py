"""Offline audit and paired summaries for scalable-3D experiment matrices.

The evaluator reads persisted episode evidence only.  It deliberately owns a
small copy of the supported matrix contract instead of importing main runtime
code, and it never infers a variant or comparison identity from a directory
name.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

import numpy as np


EXPERIMENT_MATRIX_SCHEMA_VERSION = "scalable3d-experiment-matrix-v1"
EXPERIMENT_MATRIX_VARIANTS = ("R0", "G1", "A1", "A2", "A3", "C1", "F1")
EXPERIMENT_MATRIX_BASE_VARIANTS = ("R0", "G1", "A1", "A2", "A3", "C1")
EXPERIMENT_MATRIX_FULL_SYSTEM_SCENARIOS = frozenset(
    {"center_failure", "secondary_failure", "high_threat_m_to_n"}
)

_MATRIX_METADATA_FIELDS = (
    "experiment_matrix_schema",
    "algorithm_variant",
    "comparison_key",
    "full_system_validation",
)
_LEARNING_RUNTIME_SCHEMA = "scalable3d-learning-runtime-v1"
_LEARNING_COMPONENTS = ("d3", "d4", "d5", "d5_active_vision")
_VARIANT_ASSIST_COMPONENTS = {
    "R0": (),
    "G1": ("d5",),
    "A1": ("d3",),
    "A2": ("d4",),
    "A3": ("d5_active_vision",),
    "C1": _LEARNING_COMPONENTS,
    "F1": _LEARNING_COMPONENTS,
}

EXPERIMENT_MATRIX_METRIC_CATEGORIES = {
    "finite": ("finite_state",),
    "online_truth": (
        "online_truth_use_count",
        "online_truth_field_violation_count",
    ),
    "hard_constraints": (
        "d4_advice_resource_quota_conservation_violation_count",
        "d4_advice_formal_decision_mutation_count",
        "d4_region_consumption_invalid_publication_count",
        "d4_region_consumption_summary_consistent",
        "d5_active_vision_target_reference_violation_count",
        "d5_active_vision_online_truth_field_violation_count",
    ),
    "identity_tracking": ("d2_id_switch_count",),
    "assignment": (
        "d3_assignment_count",
        "d3_plan_coverage_rate",
        "d3_backlog_count",
        "d4_region_consumable_count",
        "d4_region_d3_hint_applied_count",
        "d4_advice_control_adoption_count",
    ),
    "cross_view": (
        "d5_binding_count",
        "d5_candidate_edge_count",
        "d5_model_fallback_event_count",
    ),
    "active_vision": (
        "d5_active_vision_command_issued_count",
        "d5_active_vision_assist_adopted_count",
        "d5_active_vision_ack_applied_count",
        "d5_active_vision_ack_rejected_count",
    ),
    "physical_5m": (
        "offline_proximity_within_5m_count",
        "offline_proximity_unique_target_count",
    ),
}


def extract_experiment_matrix_evidence(
    row: dict[str, Any],
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> None:
    """Extract matrix metadata and verify the declared learning execution."""

    metadata = config.get("metadata") if isinstance(config, Mapping) else None
    metadata = metadata if isinstance(metadata, Mapping) else {}
    declared = any(field in metadata for field in _MATRIX_METADATA_FIELDS)
    _put_available(row, "experiment_matrix_declared", declared)
    if not declared:
        reason = "experiment_matrix_metadata_missing"
        for field in _MATRIX_METADATA_FIELDS:
            _put_unavailable(row, field, reason)
        for field in (
            "experiment_matrix_schema_current_match",
            "algorithm_variant_known",
            "algorithm_variant_normalized",
            "comparison_key_contract_match",
            "experiment_matrix_scenario_family",
            "experiment_matrix_scale",
            "experiment_matrix_effective_comparison_key",
            "experiment_matrix_effective_comparison_key_source",
            "full_system_validation_contract_match",
            "experiment_matrix_metadata_valid",
            "variant_runtime_resolution_valid",
            "variant_execution_valid",
            "variant_component_audit_json",
            "variant_execution_failure_reasons_json",
        ):
            _put_unavailable(row, field, reason)
        return

    failures: list[str] = []
    schema = _read_nonempty_string(
        row,
        metadata,
        "experiment_matrix_schema",
        failures,
    )
    if schema is None:
        _put_unavailable(
            row,
            "experiment_matrix_schema_current_match",
            "experiment_matrix_schema_missing_or_invalid",
        )
    else:
        schema_match = schema == EXPERIMENT_MATRIX_SCHEMA_VERSION
        _put_available(row, "experiment_matrix_schema_current_match", schema_match)
        if not schema_match:
            failures.append(
                "experiment_matrix_schema_mismatch:"
                f"expected={EXPERIMENT_MATRIX_SCHEMA_VERSION}:observed={schema}"
            )

    variant = _read_nonempty_string(
        row,
        metadata,
        "algorithm_variant",
        failures,
    )
    if variant is None:
        _put_unavailable(
            row,
            "algorithm_variant_known",
            "algorithm_variant_missing_or_invalid",
        )
        _put_unavailable(
            row,
            "algorithm_variant_normalized",
            "algorithm_variant_missing_or_invalid",
        )
    else:
        known = variant in EXPERIMENT_MATRIX_VARIANTS
        _put_available(row, "algorithm_variant_known", known)
        if known:
            _put_available(row, "algorithm_variant_normalized", variant)
        else:
            _put_unavailable(
                row,
                "algorithm_variant_normalized",
                f"algorithm_variant_unknown:{variant}",
            )
            failures.append(f"algorithm_variant_unknown:{variant}")

    comparison_key = _read_nonempty_string(
        row,
        metadata,
        "comparison_key",
        failures,
    )
    scenario_family = metadata.get("scenario_family")
    if isinstance(scenario_family, str) and scenario_family.strip():
        scenario_family = scenario_family.strip()
        _put_available(row, "experiment_matrix_scenario_family", scenario_family)
    else:
        scenario_family = None
        _put_unavailable(
            row,
            "experiment_matrix_scenario_family",
            "experiment_matrix_scenario_family_missing_or_invalid",
        )

    scale = _explicit_matrix_scale(row)
    if scale is None:
        _put_unavailable(
            row,
            "experiment_matrix_scale",
            "experiment_matrix_scale_unavailable_or_asymmetric",
        )
    else:
        _put_available(row, "experiment_matrix_scale", scale)
    expected_key = _canonical_comparison_key(row, scenario_family, scale)
    if comparison_key is None:
        _put_unavailable(
            row,
            "comparison_key_contract_match",
            "comparison_key_missing_or_invalid",
        )
    elif expected_key is None:
        _put_unavailable(
            row,
            "comparison_key_contract_match",
            "comparison_key_reference_fields_unavailable",
        )
    else:
        key_match = comparison_key == expected_key
        _put_available(row, "comparison_key_contract_match", key_match)
        if not key_match:
            failures.append(
                f"comparison_key_mismatch:expected={expected_key}:observed={comparison_key}"
            )

    if (
        comparison_key is not None
        and row.get("comparison_key_contract_match") is not False
    ):
        _put_available(
            row,
            "experiment_matrix_effective_comparison_key",
            comparison_key,
        )
        _put_available(
            row,
            "experiment_matrix_effective_comparison_key_source",
            "scenario_config.metadata.comparison_key",
        )
    elif expected_key is not None:
        _put_available(
            row,
            "experiment_matrix_effective_comparison_key",
            expected_key,
        )
        _put_available(
            row,
            "experiment_matrix_effective_comparison_key_source",
            "scenario_config.metadata.scenario_family+explicit_scale+seed",
        )
    else:
        _put_unavailable(
            row,
            "experiment_matrix_effective_comparison_key",
            "experiment_matrix_comparison_identity_unavailable",
        )
        _put_unavailable(
            row,
            "experiment_matrix_effective_comparison_key_source",
            "experiment_matrix_comparison_identity_unavailable",
        )

    full_system = metadata.get("full_system_validation")
    if isinstance(full_system, bool):
        _put_available(row, "full_system_validation", full_system)
    else:
        _put_unavailable(
            row,
            "full_system_validation",
            "full_system_validation_missing_or_invalid",
        )
        failures.append("full_system_validation_missing_or_invalid")
    _validate_full_system_flag(row, variant, scenario_family, failures)

    metadata_valid = (
        row.get("experiment_matrix_schema_current_match") is True
        and row.get("algorithm_variant_known") is True
        and row.get("comparison_key_contract_match") is True
        and row.get("full_system_validation_contract_match") is True
    )
    _put_available(row, "experiment_matrix_metadata_valid", metadata_valid)

    runtime, runtime_failures = _select_learning_runtime(config, summary)
    component_audit, runtime_valid, execution_valid, execution_failures = (
        _audit_variant_execution(row, variant, runtime)
    )
    failures.extend(runtime_failures)
    failures.extend(execution_failures)
    if runtime_failures:
        runtime_valid = False
        execution_valid = False
    if not metadata_valid:
        execution_valid = False
    _put_available(row, "variant_runtime_resolution_valid", runtime_valid)
    _put_available(row, "variant_execution_valid", execution_valid)
    _put_available(row, "variant_component_audit_json", component_audit)
    failures = list(dict.fromkeys(failures))
    _put_available(row, "variant_execution_failure_reasons_json", failures)
    row.setdefault("_failure_reasons", []).extend(failures)


def finalize_experiment_matrix_evidence(row: dict[str, Any]) -> tuple[str, ...]:
    """Classify matrix evidence after the generic formal gate is known."""

    if row.get("experiment_matrix_declared") is not True:
        reason = "not_an_experiment_matrix_episode"
        _put_unavailable(row, "experiment_matrix_formal_acceptance_eligible", reason)
        _put_unavailable(row, "experiment_matrix_evidence_class", reason)
        _put_unavailable(
            row,
            "experiment_matrix_formal_failure_reasons_json",
            reason,
        )
        return ()

    reasons = list(row.get("variant_execution_failure_reasons_json") or ())
    if row.get("formal_acceptance_eligible") is not True:
        reasons.append("episode_not_clean_formal_evidence")
    if row.get("experiment_matrix_metadata_valid") is not True:
        reasons.append("experiment_matrix_metadata_not_current_and_complete")
    if row.get("variant_execution_valid") is not True:
        reasons.append("declared_variant_execution_not_valid")
    reasons = list(dict.fromkeys(str(reason) for reason in reasons if str(reason)))
    eligible = not reasons
    _put_available(row, "experiment_matrix_formal_acceptance_eligible", eligible)
    _put_available(row, "experiment_matrix_formal_failure_reasons_json", reasons)
    if eligible:
        evidence_class = "clean_formal"
    elif row.get("repository_dirty") is True:
        evidence_class = "dirty_development"
    else:
        evidence_class = "descriptive_nonformal"
    _put_available(row, "experiment_matrix_evidence_class", evidence_class)
    return tuple(reasons)


def aggregate_experiment_matrix(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    """Summarize matrix cells without shrinking expected cell denominators."""

    matrix_rows = [row for row in rows if row.get("experiment_matrix_declared") is True]
    historical_count = sum(
        row.get("experiment_matrix_declared") is not True for row in rows
    )
    completeness = _matrix_completeness(matrix_rows)
    variant_groups = [
        _variant_summary(
            variant,
            matrix_rows,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
        )
        for variant in EXPERIMENT_MATRIX_VARIANTS
    ]
    descriptive_pairs = _paired_variant_summaries(
        matrix_rows,
        completeness,
        require_formal=False,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_rng_seed=bootstrap_rng_seed,
    )
    formal_pairs = _paired_variant_summaries(
        matrix_rows,
        completeness,
        require_formal=True,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_rng_seed=bootstrap_rng_seed,
    )
    return {
        "schema_version": "d6-scalable3d-experiment-matrix-evaluation-v1",
        "supported_matrix_schema": EXPERIMENT_MATRIX_SCHEMA_VERSION,
        "expected_variants": list(EXPERIMENT_MATRIX_VARIANTS),
        "matrix_episode_count": len(matrix_rows),
        "historical_nonmatrix_episode_count": historical_count,
        "clean_formal_episode_count": sum(
            row.get("experiment_matrix_formal_acceptance_eligible") is True
            for row in matrix_rows
        ),
        "dirty_development_episode_count": sum(
            row.get("experiment_matrix_evidence_class") == "dirty_development"
            for row in matrix_rows
        ),
        "descriptive_nonformal_episode_count": sum(
            row.get("experiment_matrix_evidence_class")
            == "descriptive_nonformal"
            for row in matrix_rows
        ),
        "evidence_class_distribution": dict(
            sorted(
                Counter(
                    str(row.get("experiment_matrix_evidence_class", "unavailable"))
                    for row in matrix_rows
                ).items()
            )
        ),
        "completeness": completeness,
        "metric_categories": {
            category: list(metrics)
            for category, metrics in EXPERIMENT_MATRIX_METRIC_CATEGORIES.items()
        },
        "variant_groups": variant_groups,
        "descriptive_paired_deltas_vs_r0": descriptive_pairs,
        "clean_formal_paired_deltas_vs_r0": formal_pairs,
        "causal_attribution": {
            "availability": "unavailable",
            "reason": (
                "paired_differences_are_not_causal_without_a_complete_formal_"
                "protocol_and_verified_assist_adoption"
            ),
        },
        "denominator_policy": (
            "each observed explicit comparison identity expects R0/G1/A1/A2/A3/C1; "
            "F1 is additionally expected only for center_failure, secondary_failure, "
            "and high_threat_m_to_n"
        ),
        "unobservable_missing_key_limit": (
            "an entirely absent comparison identity cannot be reconstructed without "
            "a separately supplied matrix manifest"
        ),
    }


def render_experiment_matrix_markdown_lines(matrix: Mapping[str, Any]) -> list[str]:
    """Render the matrix-specific evidence section for the Chinese report."""

    completeness = matrix.get("completeness", {})
    lines = [
        "## 算法实验矩阵",
        "",
        (
            f"识别到 {matrix.get('matrix_episode_count', 0)} 个矩阵 episode；"
            f"clean/formal={matrix.get('clean_formal_episode_count', 0)}，"
            f"dirty development={matrix.get('dirty_development_episode_count', 0)}，"
            f"descriptive nonformal={matrix.get('descriptive_nonformal_episode_count', 0)}。"
        ),
        (
            "固定分母完整性为 "
            f"{completeness.get('present_expected_cell_count', 0)}/"
            f"{completeness.get('expected_cell_count', 0)}；"
            f"执行有效 cell 为 {completeness.get('execution_valid_cell_count', 0)}。"
        ),
        "目录名不参与变体和配对身份判断。缺失 cell 保留在固定分母中；无 R0 配对的数据不输出因果结论。",
        "",
        "| 变体 | episodes | seeds | execution valid | clean/formal | dirty dev | finite mean | IDSW mean | coverage mean | D5 binding mean | active assist mean | <=5m mean |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in matrix.get("variant_groups", []):
        metrics = group.get("metric_statistics", {})
        lines.append(
            "| {variant} | {episodes} | {seeds} | {valid} | {formal} | {dirty} | "
            "{finite} | {idsw} | {coverage} | {binding} | {assist} | {physical} |".format(
                variant=group.get("algorithm_variant", "unavailable"),
                episodes=group.get("episode_count", 0),
                seeds=group.get("seed_count", 0),
                valid=group.get("execution_valid_episode_count", 0),
                formal=group.get("clean_formal_episode_count", 0),
                dirty=group.get("dirty_development_episode_count", 0),
                finite=_stat_mean(metrics.get("finite_state")),
                idsw=_stat_mean(metrics.get("d2_id_switch_count")),
                coverage=_stat_mean(metrics.get("d3_plan_coverage_rate")),
                binding=_stat_mean(metrics.get("d5_binding_count")),
                assist=_stat_mean(
                    metrics.get("d5_active_vision_assist_adopted_count")
                ),
                physical=_stat_mean(
                    metrics.get("offline_proximity_within_5m_count")
                ),
            )
        )
    lines.extend(
        [
            "",
            "配对差值按同一 comparison key 计算，方向为变体减 R0。少于两个完整配对时只给描述值，不生成 bootstrap 置信区间。",
            "",
            "| 变体 | 期望配对 | 完整执行配对 | clean/formal 配对 | 描述性配对状态 | 正式配对状态 |",
            "| --- | ---: | ---: | ---: | --- | --- |",
        ]
    )
    formal_by_variant = {
        item.get("algorithm_variant"): item
        for item in matrix.get("clean_formal_paired_deltas_vs_r0", [])
    }
    for item in matrix.get("descriptive_paired_deltas_vs_r0", []):
        formal = formal_by_variant.get(item.get("algorithm_variant"), {})
        lines.append(
            "| {variant} | {expected} | {complete} | {formal_count} | {status} | {formal_status} |".format(
                variant=item.get("algorithm_variant"),
                expected=item.get("expected_pair_count", 0),
                complete=item.get("complete_execution_pair_count", 0),
                formal_count=formal.get("complete_execution_pair_count", 0),
                status=item.get("pairing_status", "unavailable"),
                formal_status=formal.get("pairing_status", "unavailable"),
            )
        )
    if matrix.get("clean_formal_episode_count", 0) == 0:
        lines.extend(
            [
                "",
                "当前没有 clean/formal 矩阵证据。现有结果只能用于开发审计，不能作为正式算法优劣结论。",
            ]
        )
    return lines


def _read_nonempty_string(
    row: dict[str, Any],
    metadata: Mapping[str, Any],
    field: str,
    failures: list[str],
) -> str | None:
    value = metadata.get(field)
    if isinstance(value, str) and value.strip():
        value = value.strip()
        _put_available(row, field, value)
        return value
    reason = f"{field}_missing_or_invalid"
    _put_unavailable(row, field, reason)
    failures.append(reason)
    return None


def _explicit_matrix_scale(row: Mapping[str, Any]) -> int | None:
    target = row.get("target_count")
    resource = row.get("resource_count")
    if not (_is_nonnegative_int(target) and _is_nonnegative_int(resource)):
        return None
    if int(target) <= 0 or int(target) != int(resource):
        return None
    return int(target)


def _canonical_comparison_key(
    row: Mapping[str, Any], scenario_family: str | None, scale: int | None
) -> str | None:
    seed = row.get("seed")
    if scenario_family is None or scale is None or not _is_nonnegative_int(seed):
        return None
    return f"{scenario_family}|{scale}|{int(seed)}"


def _validate_full_system_flag(
    row: dict[str, Any],
    variant: str | None,
    scenario_family: str | None,
    failures: list[str],
) -> None:
    if row.get("full_system_validation_availability") != "available":
        _put_unavailable(
            row,
            "full_system_validation_contract_match",
            "full_system_validation_missing_or_invalid",
        )
        return
    if variant not in EXPERIMENT_MATRIX_VARIANTS:
        _put_unavailable(
            row,
            "full_system_validation_contract_match",
            "algorithm_variant_unknown_for_full_system_validation",
        )
        return
    observed = row.get("full_system_validation")
    expected = variant == "F1"
    valid = observed is expected
    if variant == "F1" and scenario_family not in EXPERIMENT_MATRIX_FULL_SYSTEM_SCENARIOS:
        valid = False
        failures.append(
            f"f1_scenario_not_full_system:{scenario_family or 'unavailable'}"
        )
    if not valid:
        failures.append(
            f"full_system_validation_mismatch:variant={variant}:observed={observed}"
        )
    _put_available(row, "full_system_validation_contract_match", valid)


def _select_learning_runtime(
    config: Mapping[str, Any] | None,
    summary: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any] | None, list[str]]:
    config_metadata = config.get("metadata") if isinstance(config, Mapping) else None
    config_runtime = (
        config_metadata.get("learning_runtime")
        if isinstance(config_metadata, Mapping)
        else None
    )
    diagnostics = (
        summary.get("module_final_diagnostics")
        if isinstance(summary, Mapping)
        else None
    )
    summary_runtime = (
        diagnostics.get("learning_runtime")
        if isinstance(diagnostics, Mapping)
        else None
    )
    failures: list[str] = []
    if not isinstance(config_runtime, Mapping):
        failures.append("matrix_learning_runtime_missing:scenario_config")
    if not isinstance(summary_runtime, Mapping):
        failures.append("matrix_learning_runtime_missing:summary")
    if failures:
        return None, failures
    if _json_ready(config_runtime) != _json_ready(summary_runtime):
        return None, ["matrix_learning_runtime_config_summary_mismatch"]
    if config_runtime.get("schema_version") != _LEARNING_RUNTIME_SCHEMA:
        return None, [
            "matrix_learning_runtime_schema_mismatch:"
            f"{config_runtime.get('schema_version')}"
        ]
    return config_runtime, []


def _audit_variant_execution(
    row: Mapping[str, Any],
    variant: str | None,
    runtime: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], bool, bool, list[str]]:
    if variant not in EXPERIMENT_MATRIX_VARIANTS:
        return {}, False, False, ["variant_execution_unknown_variant"]
    if runtime is None:
        return {}, False, False, ["variant_execution_runtime_unavailable"]

    required = set(_VARIANT_ASSIST_COMPONENTS[variant])
    failures: list[str] = []
    audit: dict[str, Any] = {}
    for component in _LEARNING_COMPONENTS:
        record = runtime.get(component)
        expected_assist = component in required
        item = {
            "expected_assist": expected_assist,
            "requested_mode": None,
            "effective_mode": None,
            "bundle_loaded": None,
            "fallback_reason": None,
            "runtime_valid": False,
            "adoption_evidence_valid": None,
            "adoption_reason": None,
        }
        if not isinstance(record, Mapping):
            failures.append(f"variant_component_diagnostics_missing:{component}")
            audit[component] = item
            continue
        requested = record.get("requested_mode")
        effective = record.get("effective_mode")
        loaded = record.get("bundle_loaded")
        fallback = record.get("fallback_reason")
        item.update(
            requested_mode=requested,
            effective_mode=effective,
            bundle_loaded=loaded,
            fallback_reason=fallback,
        )
        if expected_assist:
            component_failures: list[str] = []
            if loaded is not True:
                component_failures.append(
                    f"variant_required_bundle_not_loaded:{component}"
                )
            if requested != "assist":
                component_failures.append(
                    f"variant_required_assist_not_requested:{component}:{requested}"
                )
            if effective != "assist":
                component_failures.append(
                    f"variant_required_assist_not_effective:{component}:{effective}"
                )
            if fallback is not None:
                component_failures.append(
                    f"variant_required_component_rule_fallback:{component}:{fallback}"
                )
            if component == "d5_active_vision" and record.get("assist_admitted") is not True:
                component_failures.append("variant_active_vision_assist_not_admitted")
            failures.extend(component_failures)
            item["runtime_valid"] = not component_failures
        else:
            component_failures = []
            if requested != "disabled":
                component_failures.append(
                    f"variant_unexpected_requested_mode:{component}:{requested}"
                )
            if effective != "disabled":
                component_failures.append(
                    f"variant_unexpected_effective_mode:{component}:{effective}"
                )
            if loaded is not False:
                component_failures.append(
                    f"variant_unexpected_bundle_loaded:{component}:{loaded}"
                )
            if fallback is not None:
                component_failures.append(
                    f"variant_unexpected_fallback_reason:{component}:{fallback}"
                )
            failures.extend(component_failures)
            item["runtime_valid"] = not component_failures
        audit[component] = item

    runtime_valid = not failures
    for component in required:
        adopted, reason = _component_adoption(row, component)
        audit[component]["adoption_evidence_valid"] = adopted
        audit[component]["adoption_reason"] = reason
        if not adopted:
            failures.append(reason)
    if variant == "R0":
        for component in _LEARNING_COMPONENTS:
            leaked, reason = _unexpected_baseline_adoption(row, component)
            if leaked:
                audit[component]["adoption_evidence_valid"] = False
                audit[component]["adoption_reason"] = reason
                failures.append(reason)
    failures = list(dict.fromkeys(failures))
    return audit, runtime_valid, not failures, failures


def _component_adoption(
    row: Mapping[str, Any], component: str
) -> tuple[bool, str]:
    if component == "d3":
        field = "d3_learning_applied_count"
        if row.get(f"{field}_availability") != "available":
            return False, "variant_assist_adoption_unavailable:d3"
        if int(row.get(field, 0)) <= 0:
            return False, "variant_assist_not_adopted:d3"
        return True, "d3_learning_applied"
    if component == "d4":
        field = "d4_advice_control_adoption_count"
        if row.get(f"{field}_availability") != "available":
            return False, "variant_assist_adoption_unavailable:d4"
        if int(row.get(field, 0)) <= 0:
            return False, "variant_assist_not_adopted:d4"
        return True, "d4_control_adoption_recorded"
    if component == "d5":
        if row.get("d5_probability_source_availability") != "available":
            return False, "variant_assist_adoption_unavailable:d5"
        if row.get("d5_probability_source") != "loaded_edge_model":
            return False, "variant_assist_not_adopted:d5"
        if (
            row.get("d5_model_fallback_event_count_availability") != "available"
            or int(row.get("d5_model_fallback_event_count", 0)) != 0
        ):
            return False, "variant_required_component_rule_fallback:d5"
        return True, "d5_loaded_edge_model_scored"
    field = "d5_active_vision_assist_adopted_count"
    if row.get(f"{field}_availability") != "available":
        return False, "variant_assist_adoption_unavailable:d5_active_vision"
    if int(row.get(field, 0)) <= 0:
        return False, "variant_assist_not_adopted:d5_active_vision"
    return True, "d5_active_vision_assist_adopted"


def _unexpected_baseline_adoption(
    row: Mapping[str, Any], component: str
) -> tuple[bool, str]:
    checks = {
        "d3": ("d3_learning_applied_count",),
        "d4": ("d4_advice_control_adoption_count",),
        "d5_active_vision": ("d5_active_vision_assist_adopted_count",),
    }
    for field in checks.get(component, ()):
        if (
            row.get(f"{field}_availability") == "available"
            and int(row.get(field, 0)) > 0
        ):
            return True, f"r0_unexpected_learning_assist_adoption:{component}"
    if (
        component == "d5"
        and row.get("d5_probability_source_availability") == "available"
        and row.get("d5_probability_source") == "loaded_edge_model"
    ):
        return True, "r0_unexpected_learning_assist_adoption:d5"
    return False, "no_learning_assist_adoption"


def _matrix_completeness(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    keyed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if (
            row.get("experiment_matrix_effective_comparison_key_availability")
            == "available"
        ):
            keyed[str(row["experiment_matrix_effective_comparison_key"])].append(row)
    details: list[dict[str, Any]] = []
    expected_total = present_total = valid_total = duplicate_total = 0
    for key in sorted(keyed):
        key_rows = keyed[key]
        families = {
            str(row["experiment_matrix_scenario_family"])
            for row in key_rows
            if row.get("experiment_matrix_scenario_family_availability") == "available"
        }
        family = next(iter(families)) if len(families) == 1 else None
        expected = list(EXPERIMENT_MATRIX_BASE_VARIANTS)
        if family in EXPERIMENT_MATRIX_FULL_SYSTEM_SCENARIOS:
            expected.append("F1")
        by_variant: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        unexpected: list[str] = []
        for row in key_rows:
            variant = row.get("algorithm_variant_normalized")
            if variant in EXPERIMENT_MATRIX_VARIANTS:
                by_variant[str(variant)].append(row)
            else:
                raw = row.get("algorithm_variant")
                if raw is not None:
                    unexpected.append(str(raw))
        missing = [variant for variant in expected if not by_variant.get(variant)]
        duplicates = {
            variant: len(values)
            for variant, values in by_variant.items()
            if len(values) > 1
        }
        present = sum(bool(by_variant.get(variant)) for variant in expected)
        valid = sum(
            len(by_variant.get(variant, ())) == 1
            and by_variant[variant][0].get("variant_execution_valid") is True
            for variant in expected
        )
        if family not in EXPERIMENT_MATRIX_FULL_SYSTEM_SCENARIOS and by_variant.get("F1"):
            unexpected.append("F1")
        expected_total += len(expected)
        present_total += present
        valid_total += valid
        duplicate_total += sum(count - 1 for count in duplicates.values())
        details.append(
            {
                "comparison_key": key,
                "scenario_family": family,
                "expected_variants": expected,
                "present_variants": sorted(by_variant),
                "missing_variants": missing,
                "duplicate_variant_counts": dict(sorted(duplicates.items())),
                "unexpected_variants": sorted(set(unexpected)),
                "expected_cell_count": len(expected),
                "present_expected_cell_count": present,
                "execution_valid_cell_count": valid,
            }
        )
    if expected_total:
        availability = "available"
        reason = None
        presence_rate = present_total / expected_total
        valid_rate = valid_total / expected_total
    else:
        availability = "unavailable"
        reason = "no_explicit_matrix_comparison_identity"
        presence_rate = None
        valid_rate = None
    return {
        "availability": availability,
        "unavailable_reason": reason,
        "comparison_key_count": len(keyed),
        "expected_cell_count": expected_total,
        "present_expected_cell_count": present_total,
        "execution_valid_cell_count": valid_total,
        "missing_expected_cell_count": expected_total - present_total,
        "invalid_or_missing_execution_cell_count": expected_total - valid_total,
        "duplicate_extra_episode_count": duplicate_total,
        "cell_presence_rate": presence_rate,
        "execution_valid_rate": valid_rate,
        "unkeyed_matrix_episode_count": sum(
            row.get("experiment_matrix_effective_comparison_key_availability")
            != "available"
            for row in rows
        ),
        "details": details,
    }


def _variant_summary(
    variant: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> dict[str, Any]:
    selected = [row for row in rows if row.get("algorithm_variant_normalized") == variant]
    formal = [
        row
        for row in selected
        if row.get("experiment_matrix_formal_acceptance_eligible") is True
    ]
    dirty = [
        row
        for row in selected
        if row.get("experiment_matrix_evidence_class") == "dirty_development"
    ]
    metrics = _matrix_metric_names(selected)
    return {
        "algorithm_variant": variant,
        "episode_count": len(selected),
        "seed_count": len(_seed_set(selected)),
        "execution_valid_episode_count": sum(
            row.get("variant_execution_valid") is True for row in selected
        ),
        "clean_formal_episode_count": len(formal),
        "dirty_development_episode_count": len(dirty),
        "metric_statistics": _statistics_map(
            selected,
            metrics,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
            identity={"variant": variant, "evidence": "all_descriptive"},
        ),
        "clean_formal_metric_statistics": _statistics_map(
            formal,
            metrics,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
            identity={"variant": variant, "evidence": "clean_formal"},
        ),
        "dirty_development_metric_statistics": _statistics_map(
            dirty,
            metrics,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
            identity={"variant": variant, "evidence": "dirty_development"},
        ),
        "stage_timing": _variant_stage_timing(
            selected,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
            identity={"variant": variant, "evidence": "all_descriptive"},
        ),
        "variant_execution_failure_reason_distribution": _counter_from_list_field(
            selected, "variant_execution_failure_reasons_json"
        ),
    }


def _paired_variant_summaries(
    rows: Sequence[Mapping[str, Any]],
    completeness: Mapping[str, Any],
    *,
    require_formal: bool,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
) -> list[dict[str, Any]]:
    keyed: dict[str, dict[str, list[Mapping[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    family_by_key: dict[str, str | None] = {}
    for detail in completeness.get("details", []):
        family_by_key[str(detail["comparison_key"])] = detail.get("scenario_family")
    for row in rows:
        if (
            row.get("experiment_matrix_effective_comparison_key_availability")
            != "available"
            or row.get("algorithm_variant_normalized") not in EXPERIMENT_MATRIX_VARIANTS
        ):
            continue
        key = str(row["experiment_matrix_effective_comparison_key"])
        keyed[key][str(row["algorithm_variant_normalized"])].append(row)

    output: list[dict[str, Any]] = []
    for variant in EXPERIMENT_MATRIX_VARIANTS[1:]:
        eligible_keys = [
            key
            for key in sorted(keyed)
            if variant != "F1"
            or family_by_key.get(key) in EXPERIMENT_MATRIX_FULL_SYSTEM_SCENARIOS
        ]
        pairs: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
        missing_reasons = Counter()
        for key in eligible_keys:
            baseline_rows = keyed[key].get("R0", [])
            variant_rows = keyed[key].get(variant, [])
            if len(baseline_rows) != 1:
                missing_reasons[
                    "r0_missing" if not baseline_rows else "r0_duplicate"
                ] += 1
                continue
            if len(variant_rows) != 1:
                missing_reasons[
                    "variant_missing" if not variant_rows else "variant_duplicate"
                ] += 1
                continue
            baseline = baseline_rows[0]
            treatment = variant_rows[0]
            if baseline.get("variant_execution_valid") is not True:
                missing_reasons["r0_execution_invalid"] += 1
                continue
            if treatment.get("variant_execution_valid") is not True:
                missing_reasons["variant_execution_invalid"] += 1
                continue
            if require_formal and not (
                baseline.get("experiment_matrix_formal_acceptance_eligible") is True
                and treatment.get("experiment_matrix_formal_acceptance_eligible") is True
            ):
                missing_reasons["pair_not_clean_formal"] += 1
                continue
            pairs.append((key, baseline, treatment))

        metric_names = _matrix_metric_names(
            [row for _, baseline, treatment in pairs for row in (baseline, treatment)]
        )
        deltas = {
            metric: _paired_metric_statistics(
                pairs,
                metric,
                expected_pair_count=len(eligible_keys),
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                identity={
                    "variant": variant,
                    "evidence": "clean_formal" if require_formal else "descriptive",
                },
            )
            for metric in metric_names
        }
        if not eligible_keys:
            status = "not_applicable_no_eligible_comparison_keys"
        elif not pairs:
            status = "unavailable_no_complete_execution_pairs"
        elif len(pairs) == 1:
            status = "descriptive_single_pair_no_bootstrap_ci"
        else:
            status = "paired_bootstrap_across_comparison_keys"
        output.append(
            {
                "algorithm_variant": variant,
                "evidence_scope": "clean_formal" if require_formal else "all_descriptive",
                "expected_pair_count": len(eligible_keys),
                "complete_execution_pair_count": len(pairs),
                "pair_completion_rate": (
                    len(pairs) / len(eligible_keys) if eligible_keys else None
                ),
                "paired_comparison_keys": [key for key, _, _ in pairs],
                "incomplete_pair_reason_distribution": dict(
                    sorted(missing_reasons.items())
                ),
                "pairing_status": status,
                "metric_deltas_variant_minus_r0": deltas,
                "causal_attribution": False,
                "causal_attribution_reason": (
                    "paired_delta_only; causal attribution requires a complete formal "
                    "protocol and verified assist adoption"
                ),
            }
        )
    return output


def _matrix_metric_names(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    base = [
        metric
        for metrics in EXPERIMENT_MATRIX_METRIC_CATEGORIES.values()
        for metric in metrics
    ]
    stages = sorted(
        {
            key
            for row in rows
            for key in row
            if key.startswith("stage__")
            and key.endswith(("__wall_time_s", "__mean_wall_time_ms"))
        }
    )
    return tuple(dict.fromkeys((*base, *stages)))


def _statistics_map(
    rows: Sequence[Mapping[str, Any]],
    metrics: Sequence[str],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        metric: _metric_statistics(
            rows,
            metric,
            bootstrap_resamples=bootstrap_resamples,
            bootstrap_rng_seed=bootstrap_rng_seed,
            identity={**identity, "metric": metric},
        )
        for metric in metrics
    }


def _metric_statistics(
    rows: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    values: list[float] = []
    seed_values: dict[int, list[float]] = defaultdict(list)
    unavailable = Counter()
    for row in rows:
        value = row.get(metric)
        if row.get(f"{metric}_availability") == "available" and _is_number(value):
            numeric = float(int(value) if isinstance(value, bool) else value)
            values.append(numeric)
            if _is_nonnegative_int(row.get("seed")):
                seed_values[int(row["seed"])].append(numeric)
        else:
            unavailable[
                str(
                    row.get(f"{metric}_unavailable_reason")
                    or "metric_unavailable_without_reason"
                )
            ] += 1
    if not values:
        return _unavailable_statistics(dict(sorted(unavailable.items())))
    seed_means = [float(np.mean(seed_values[seed])) for seed in sorted(seed_values)]
    low, high, ci_availability, ci_reason = _bootstrap_if_possible(
        seed_means,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_rng_seed=bootstrap_rng_seed,
        identity=identity,
    )
    array = np.asarray(values, dtype=float)
    return {
        "availability": "available",
        "unavailable_reason": None,
        "unavailability_reason_distribution": dict(sorted(unavailable.items())),
        "episode_value_count": len(values),
        "seed_value_count": len(seed_means),
        "mean": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "bootstrap_ci95_low": low,
        "bootstrap_ci95_high": high,
        "bootstrap_availability": ci_availability,
        "bootstrap_unavailable_reason": ci_reason,
    }


def _paired_metric_statistics(
    pairs: Sequence[tuple[str, Mapping[str, Any], Mapping[str, Any]]],
    metric: str,
    *,
    expected_pair_count: int,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    deltas: list[float] = []
    keys: list[str] = []
    unavailable = Counter()
    for key, baseline, treatment in pairs:
        if (
            baseline.get(f"{metric}_availability") != "available"
            or not _is_number(baseline.get(metric))
        ):
            unavailable["r0_metric_unavailable"] += 1
            continue
        if (
            treatment.get(f"{metric}_availability") != "available"
            or not _is_number(treatment.get(metric))
        ):
            unavailable["variant_metric_unavailable"] += 1
            continue
        baseline_value = float(
            int(baseline[metric]) if isinstance(baseline[metric], bool) else baseline[metric]
        )
        treatment_value = float(
            int(treatment[metric]) if isinstance(treatment[metric], bool) else treatment[metric]
        )
        deltas.append(treatment_value - baseline_value)
        keys.append(key)
    if not deltas:
        output = _unavailable_statistics(dict(sorted(unavailable.items())))
        output.update(
            expected_pair_count=expected_pair_count,
            complete_execution_pair_count=len(pairs),
            metric_pair_count=0,
            metric_pair_completeness_rate=(
                0.0 if expected_pair_count else None
            ),
            paired_comparison_keys=[],
        )
        return output
    low, high, ci_availability, ci_reason = _bootstrap_if_possible(
        deltas,
        bootstrap_resamples=bootstrap_resamples,
        bootstrap_rng_seed=bootstrap_rng_seed,
        identity={**identity, "metric": metric},
    )
    array = np.asarray(deltas, dtype=float)
    return {
        "availability": "available",
        "unavailable_reason": None,
        "unavailability_reason_distribution": dict(sorted(unavailable.items())),
        "expected_pair_count": expected_pair_count,
        "complete_execution_pair_count": len(pairs),
        "metric_pair_count": len(deltas),
        "metric_pair_completeness_rate": (
            len(deltas) / expected_pair_count if expected_pair_count else None
        ),
        "paired_comparison_keys": keys,
        "mean_delta_variant_minus_r0": float(np.mean(array)),
        "standard_deviation": float(np.std(array, ddof=0)),
        "minimum": float(np.min(array)),
        "maximum": float(np.max(array)),
        "bootstrap_ci95_low": low,
        "bootstrap_ci95_high": high,
        "bootstrap_availability": ci_availability,
        "bootstrap_unavailable_reason": ci_reason,
    }


def _variant_stage_timing(
    rows: Sequence[Mapping[str, Any]],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    stages = sorted(
        {
            str(stage)
            for row in rows
            for stage in (
                row.get("_stage_records", {}).keys()
                if isinstance(row.get("_stage_records"), Mapping)
                else ()
            )
        }
    )
    output: dict[str, Any] = {}
    for stage in stages:
        slug = _stage_slug(stage)
        output[stage] = {
            field: _metric_statistics(
                rows,
                f"stage__{slug}__{field}",
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_rng_seed=bootstrap_rng_seed,
                identity={**identity, "stage": stage, "metric": field},
            )
            for field in ("call_count", "wall_time_s", "mean_wall_time_ms")
        }
    return output


def _bootstrap_if_possible(
    values: Sequence[float],
    *,
    bootstrap_resamples: int,
    bootstrap_rng_seed: int,
    identity: Mapping[str, Any],
) -> tuple[float | None, float | None, str, str | None]:
    if len(values) < 2:
        return None, None, "unavailable", "single_pair_or_seed_descriptive_only"
    material = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    offset = int.from_bytes(hashlib.sha256(material).digest()[:4], "big")
    rng = np.random.default_rng((bootstrap_rng_seed + offset) % (2**32))
    array = np.asarray(values, dtype=float)
    indices = rng.integers(0, len(array), size=(bootstrap_resamples, len(array)))
    means = np.mean(array[indices], axis=1)
    return (
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
        "available",
        None,
    )


def _unavailable_statistics(reasons: Mapping[str, int]) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "unavailable_reason": "no_available_values",
        "unavailability_reason_distribution": dict(reasons),
        "episode_value_count": 0,
        "seed_value_count": 0,
        "mean": None,
        "standard_deviation": None,
        "minimum": None,
        "maximum": None,
        "bootstrap_ci95_low": None,
        "bootstrap_ci95_high": None,
        "bootstrap_availability": "unavailable",
        "bootstrap_unavailable_reason": "no_available_values",
    }


def _counter_from_list_field(
    rows: Sequence[Mapping[str, Any]], field: str
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        values = row.get(field)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            counter.update(str(value) for value in values)
    return dict(sorted(counter.items()))


def _seed_set(rows: Sequence[Mapping[str, Any]]) -> set[int]:
    return {
        int(row["seed"])
        for row in rows
        if _is_nonnegative_int(row.get("seed"))
    }


def _stat_mean(value: Any) -> str:
    if not isinstance(value, Mapping) or value.get("availability") != "available":
        return "unavailable"
    mean = value.get("mean")
    return f"{float(mean):.6g}" if _is_number(mean) else "unavailable"


def _stage_slug(stage: str) -> str:
    return (
        re.sub(r"[^a-z0-9]+", "_", str(stage).strip().lower()).strip("_")
        or "unnamed"
    )


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float, np.integer, np.floating))
        and not isinstance(value, bool)
        and bool(np.isfinite(float(value)))
    ) or isinstance(value, bool)


def _is_nonnegative_int(value: Any) -> bool:
    return (
        isinstance(value, (int, np.integer))
        and not isinstance(value, bool)
        and int(value) >= 0
    )


def _put_available(row: dict[str, Any], field: str, value: Any) -> None:
    row[field] = _json_ready(value)
    row[f"{field}_availability"] = "available"
    row[f"{field}_unavailable_reason"] = None


def _put_unavailable(row: dict[str, Any], field: str, reason: str) -> None:
    row[field] = None
    row[f"{field}_availability"] = "unavailable"
    row[f"{field}_unavailable_reason"] = str(reason)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


__all__ = [
    "EXPERIMENT_MATRIX_BASE_VARIANTS",
    "EXPERIMENT_MATRIX_FULL_SYSTEM_SCENARIOS",
    "EXPERIMENT_MATRIX_METRIC_CATEGORIES",
    "EXPERIMENT_MATRIX_SCHEMA_VERSION",
    "EXPERIMENT_MATRIX_VARIANTS",
    "aggregate_experiment_matrix",
    "extract_experiment_matrix_evidence",
    "finalize_experiment_matrix_evidence",
    "render_experiment_matrix_markdown_lines",
]
