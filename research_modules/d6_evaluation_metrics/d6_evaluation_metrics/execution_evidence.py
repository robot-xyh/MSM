"""Validation contract for canonical post-control D7 execution evidence.

Integrated replay is useful diagnostic evidence, but it is not proof that a
SimpleFlight command was authorized or applied.  This module keeps that
boundary explicit so D6 cannot promote a pre-control ``EpisodeMetrics`` dump
merely because main registered its path under an execution-looking name.
"""

from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re
from typing import Any, Mapping


D7_ACTUAL_EXECUTION_SCHEMA_VERSION = "d7-actual-execution-metrics-v2"
D7_ACTUAL_EXECUTION_PRODUCER = "main_airsim_runtime"
D7_ACTUAL_EXECUTION_STAGE = "post_simpleflight_control"
D7_ACTUAL_EXECUTION_METRIC_SCOPE = "actual_execution"
D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS = (
    "per_persisted_control_command_target_state_measurement_age_stale_and_source"
)

D7_ACTUAL_EXECUTION_METADATA_SOURCES = {
    "plan_ids": "control_commands",
    "plan_versions": "control_commands",
    "owner_node_ids": "control_commands",
}
D7_ACTUAL_EXECUTION_METADATA_SEMANTICS = {
    "plan_ids": "distinct_persisted_control_command_plan_id",
    "plan_versions": "distinct_persisted_positive_integer_plan_version",
    "owner_node_ids": (
        "distinct_nonempty_authoritative_control_command_d4_target_node_id"
    ),
}

D7_ACTUAL_EXECUTION_REQUIRED_COUNT_FIELDS = (
    "contract_evaluated_count",
    "contract_allowed_count",
    "control_evaluated_count",
    "control_allowed_count",
    "terminal_switch_allowed_count",
    "mode_switched_count",
    "physical_intercept_count",
    "pair_physical_success_count",
    "target_intercept_success_count",
    "performance_budget_violation_count",
    "active_degradation_count",
    "secondary_reassignment_count",
    "d4_reassign_pending_count",
    "terminal_lock_count",
    "visual_png_switch_count",
    "visual_png_control_allowed_sample_count",
    "terminal_contract_reject_count",
    "truth_identity_online_use_count",
    "truth_state_online_use_count",
)
D7_ACTUAL_EXECUTION_REQUIRED_ARTIFACTS = (
    "control_commands",
    "intercept_summary",
    "main_episode_bus_metrics",
)

D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS = {
    "active_degradation_count": "unique_command_transition",
    "secondary_reassignment_count": "resource_target_phase_transition",
    "d4_reassign_pending_count": "resource_target_phase_transition",
    "terminal_lock_count": "resource_target_lock_acquisition_transition",
    "visual_png_switch_count": "effective_control_authorized_visual_transition",
    "visual_png_control_allowed_sample_count": (
        "effective_control_authorized_visual_sample"
    ),
    "terminal_contract_reject_count": "persisted_reject_reason_sample",
    "truth_identity_online_use_count": "persisted_command_truth_identity_use_sample",
    "truth_state_online_use_count": "persisted_intercept_summary_safety_count",
}

D7_ACTUAL_EXECUTION_METRIC_SOURCES = {
    **{
        name: "control_commands"
        for name in (
            "contract_evaluated_count",
            "contract_allowed_count",
            "control_evaluated_count",
            "control_allowed_count",
            "terminal_switch_allowed_count",
            "mode_switched_count",
            *D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS,
        )
    },
    **{
        name: "intercept_summary"
        for name in (
            "physical_intercept_count",
            "pair_physical_success_count",
            "target_intercept_success_count",
            "truth_state_online_use_count",
        )
    },
    **{
        name: "main_episode_bus_metrics"
        for name in (
            "performance_sample_count",
            "loop_latency_ms",
            "performance_budget_violation_count",
        )
    },
    "target_state_freshness": "control_commands",
}

_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_TIMESTAMP_ABS_TOLERANCE_S = 1e-9

_TARGET_STATE_FRESHNESS_REQUIRED_FIELDS = (
    "timestamp_s",
    "target_measurement_timestamp_s",
    "target_arrival_timestamp_s",
    "target_measurement_age_s",
    "target_state_stale",
    "target_state_source",
)
_TARGET_STATE_FRESHNESS_SUMMARY_FIELDS = (
    "sample_count",
    "mean_age_s",
    "p95_age_s",
    "max_age_s",
    "stale_count",
    "stale_rate",
    "source_distribution",
)

_CONTROL_REQUIRED_FIELDS = (
    "timestamp_s",
    "resource_id",
    "target_id",
    "terminal_contract_allowed",
    "effective_terminal_contract_allowed",
    "terminal_control_allowed",
    "effective_control_authorized",
    "terminal_switch_allowed",
    "terminal_semantics_version",
    "mode_switched",
    "physical_intercept",
    "d4_action",
    "d4_mode",
    "assignment_phase",
    "d5_decision_state",
    "terminal_locked",
    "guidance_law",
    "mode",
    "terminal_contract_reject_reason",
    "truth_identity_online_use",
    "truth_state_online_use",
    "plan_id",
    "plan_version",
    "d4_target_node_id",
    "target_measurement_timestamp_s",
    "target_arrival_timestamp_s",
    "target_measurement_age_s",
    "target_state_stale",
    "target_state_source",
)


class ActualExecutionEvidenceError(ValueError):
    """Raised when persisted sources cannot prove actual execution evidence."""

    def __init__(self, reasons: list[str] | tuple[str, ...]) -> None:
        self.reasons = tuple(dict.fromkeys(str(reason) for reason in reasons))
        super().__init__(";".join(self.reasons))


def build_d7_actual_execution_evidence(
    control_commands_path: str | Path,
    intercept_summary_path: str | Path,
    main_episode_bus_metrics_path: str | Path,
    *,
    case_id: str | None = None,
) -> dict[str, Any]:
    """Build one canonical actual-execution envelope from persisted sources.

    This function is intentionally strict.  It does not use integrated replay,
    infer absent counts, or treat a zero-valued default as evidence.  Invalid or
    conflicting sources raise :class:`ActualExecutionEvidenceError`, so main can
    leave the case registration unavailable instead of publishing a partial
    canonical file.
    """

    paths = {
        "control_commands": _required_file(control_commands_path),
        "intercept_summary": _required_file(intercept_summary_path),
        "main_episode_bus_metrics": _required_file(main_episode_bus_metrics_path),
    }
    rows = _read_control_rows(paths["control_commands"])
    summary = _read_json_object(paths["intercept_summary"], "intercept_summary")
    main_bundle = _read_json_object(
        paths["main_episode_bus_metrics"], "main_episode_bus_metrics"
    )
    main_metrics = main_bundle.get("metrics", main_bundle)
    if not isinstance(main_metrics, Mapping):
        raise ActualExecutionEvidenceError(
            ["d7_actual_execution_main_metrics_not_object"]
        )

    reasons: list[str] = []
    _validate_control_schema(rows, reasons)
    _validate_simpleflight_summary(summary, rows, reasons)
    bundle_metadata = main_bundle.get("metadata")
    if not isinstance(bundle_metadata, Mapping):
        reasons.append("d7_actual_execution_main_bundle_metadata_not_object")
    elif bundle_metadata.get("main_episode_bus_execution_metrics_merged") is not True:
        reasons.append("d7_actual_execution_main_bus_not_finalized")

    episode_id = _nonempty_text(main_metrics.get("episode_id"))
    seed = main_metrics.get("seed")
    resource_count = main_metrics.get("resource_count")
    target_count = main_metrics.get("target_count")
    if episode_id is None:
        reasons.append("d7_actual_execution_main_episode_id_missing")
    if not _is_int(seed):
        reasons.append("d7_actual_execution_main_seed_missing")
    if not _is_int(resource_count) or resource_count <= 0:
        reasons.append("d7_actual_execution_main_resource_count_missing")
    if not _is_int(target_count) or target_count <= 0:
        reasons.append("d7_actual_execution_main_target_count_missing")

    main_metadata = main_metrics.get("metadata")
    if not isinstance(main_metadata, Mapping):
        reasons.append("d7_actual_execution_main_metadata_not_object")
        main_metadata = {}
    scenario_config = main_metadata.get("scenario_config")
    scenario_metadata = (
        scenario_config.get("metadata")
        if isinstance(scenario_config, Mapping)
        else None
    )
    persisted_case_id = (
        _nonempty_text(scenario_metadata.get("case_id"))
        if isinstance(scenario_metadata, Mapping)
        else None
    )
    selected_case_id = _nonempty_text(case_id) or persisted_case_id
    if selected_case_id is None:
        reasons.append("d7_actual_execution_case_id_missing")
    if (
        _nonempty_text(case_id) is not None
        and persisted_case_id is not None
        and _nonempty_text(case_id) != persisted_case_id
    ):
        reasons.append("d7_actual_execution_case_id_source_conflict")

    command_metrics, semantics_version = _command_metrics(rows, reasons)
    execution_identity = _execution_identity_metadata(rows, reasons)
    diagnostic_metrics = _actual_diagnostic_metrics(rows, reasons)
    target_state_freshness, _ = _target_state_freshness_summary(rows, reasons)
    physical_metrics = _physical_metrics(summary, rows, command_metrics, reasons)
    performance_metrics = _performance_metrics(
        main_bundle,
        main_metrics,
        reasons,
    )
    _validate_main_execution_consistency(
        main_metrics,
        command_metrics,
        physical_metrics,
        reasons,
    )
    if reasons:
        raise ActualExecutionEvidenceError(reasons)

    metric_values = {
        **command_metrics,
        **diagnostic_metrics,
        "target_state_freshness": target_state_freshness,
        **physical_metrics,
        **performance_metrics,
    }
    metric_sources = {
        **{name: "control_commands" for name in command_metrics},
        **{name: "control_commands" for name in diagnostic_metrics},
        "target_state_freshness": "control_commands",
        **{name: "intercept_summary" for name in physical_metrics},
        **{name: "main_episode_bus_metrics" for name in performance_metrics},
    }
    diagnostic_semantics = D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS
    metric_values["metric_availability"] = {
        name: {
            "status": "available",
            "source_artifact": metric_sources[name],
            "reason": "validated persisted actual-execution source",
            **(
                {"semantics": diagnostic_semantics[name]}
                if name in diagnostic_semantics
                else {
                    "semantics": (
                        D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS
                    ),
                    "source": "control_commands",
                }
                if name == "target_state_freshness"
                else {}
            ),
        }
        for name in metric_sources
    }
    artifacts = {
        name: {
            "path": str(path.resolve()),
            "sha256": _sha256(path),
        }
        for name, path in paths.items()
    }
    payload = {
        "schema": D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
        "episode_id": episode_id,
        "case_id": selected_case_id,
        "seed": seed,
        "resource_count": resource_count,
        "target_count": target_count,
        "producer": D7_ACTUAL_EXECUTION_PRODUCER,
        "execution_stage": D7_ACTUAL_EXECUTION_STAGE,
        "metric_scope": D7_ACTUAL_EXECUTION_METRIC_SCOPE,
        "semantics_version": semantics_version,
        "source_artifacts": artifacts,
        "metrics": metric_values,
        "metadata": {
            **execution_identity,
            "metadata_availability": _execution_identity_availability(
                execution_identity
            ),
            "control_command_row_count": len(rows),
            "raw_mode_switched_count": sum(
                _strict_bool(row.get("mode_switched"), "mode_switched")
                for row in rows
            ),
            "actual_mode_switched_count": command_metrics["mode_switched_count"],
            "actual_diagnostic_semantics": diagnostic_semantics,
            "source_hashes_verified_at_build": True,
        },
    }
    validation = validate_d7_actual_execution_payload(payload)
    if validation["status"] != "available":
        raise ActualExecutionEvidenceError(validation["validation_reasons"])
    return payload


def write_d7_actual_execution_evidence(
    output_path: str | Path,
    control_commands_path: str | Path,
    intercept_summary_path: str | Path,
    main_episode_bus_metrics_path: str | Path,
    *,
    case_id: str | None = None,
) -> Path:
    """Validate sources and atomically write a canonical execution JSON."""

    output = Path(output_path)
    source_paths = {
        Path(control_commands_path).expanduser().resolve(),
        Path(intercept_summary_path).expanduser().resolve(),
        Path(main_episode_bus_metrics_path).expanduser().resolve(),
    }
    if output.expanduser().resolve() in source_paths:
        raise ActualExecutionEvidenceError(
            ["d7_actual_execution_output_must_be_separate"]
        )
    payload = build_d7_actual_execution_evidence(
        control_commands_path,
        intercept_summary_path,
        main_episode_bus_metrics_path,
        case_id=case_id,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(output)
    return output


def validate_d7_actual_execution_payload(
    payload: Mapping[str, Any],
    *,
    expected_seed: Any = None,
    expected_case_id: str | None = None,
    source_base_dir: str | Path | None = None,
    verify_source_hashes: bool = True,
) -> dict[str, Any]:
    """Validate and normalize one canonical post-control execution envelope.

    The returned ``metrics`` mapping is populated only when every required
    provenance, availability and count invariant is satisfied. Source hashes
    and command-derived values are recomputed by default; callers must opt out
    explicitly for non-formal structural diagnostics. Missing evidence never
    becomes a zero-valued execution result.
    """

    reasons: list[str] = []
    schema = payload.get("schema") or payload.get("schema_version")
    if schema is None:
        reasons.append("d7_actual_execution_schema_missing")
    elif schema != D7_ACTUAL_EXECUTION_SCHEMA_VERSION:
        reasons.append("d7_actual_execution_schema_mismatch")

    _require_nonempty_text(payload, "episode_id", reasons)
    _require_nonempty_text(payload, "case_id", reasons)
    _require_nonempty_text(payload, "semantics_version", reasons)
    if payload.get("producer") != D7_ACTUAL_EXECUTION_PRODUCER:
        reasons.append("d7_actual_execution_producer_invalid")
    if payload.get("execution_stage") != D7_ACTUAL_EXECUTION_STAGE:
        reasons.append("d7_actual_execution_stage_invalid")
    if payload.get("metric_scope") != D7_ACTUAL_EXECUTION_METRIC_SCOPE:
        reasons.append("d7_actual_execution_metric_scope_invalid")

    seed = payload.get("seed")
    if not _is_int(seed):
        reasons.append("d7_actual_execution_seed_invalid")
    elif expected_seed is not None and seed != expected_seed:
        reasons.append("d7_actual_execution_case_seed_mismatch")
    case_id = payload.get("case_id")
    if (
        expected_case_id is not None
        and isinstance(case_id, str)
        and case_id.strip()
        and case_id.strip() != expected_case_id
    ):
        reasons.append("d7_actual_execution_case_id_mismatch")

    for name in ("resource_count", "target_count"):
        value = payload.get(name)
        if not _is_int(value) or value <= 0:
            reasons.append(f"d7_actual_execution_{name}_invalid")

    metadata = payload.get("metadata")
    if not isinstance(metadata, Mapping):
        reasons.append("d7_actual_execution_metadata_not_object")
        metadata = {}
    _validate_execution_identity_metadata(metadata, reasons)

    artifacts = payload.get("source_artifacts")
    resolved_artifacts: dict[str, Path] = {}
    if not isinstance(artifacts, Mapping):
        reasons.append("d7_actual_execution_source_artifacts_not_object")
    else:
        for name in D7_ACTUAL_EXECUTION_REQUIRED_ARTIFACTS:
            artifact = artifacts.get(name)
            if not isinstance(artifact, Mapping):
                reasons.append(f"d7_actual_execution_artifact_missing:{name}")
                continue
            path = artifact.get("path")
            if not isinstance(path, str) or not path.strip():
                reasons.append(f"d7_actual_execution_artifact_path_invalid:{name}")
            digest = artifact.get("sha256")
            if not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
                reasons.append(f"d7_actual_execution_artifact_sha256_invalid:{name}")
            elif verify_source_hashes and isinstance(path, str) and path.strip():
                source_path = _resolve_source_path(path, source_base_dir)
                if source_path is None:
                    reasons.append(f"d7_actual_execution_artifact_file_missing:{name}")
                elif _sha256(source_path).lower() != digest.lower():
                    reasons.append(f"d7_actual_execution_artifact_hash_mismatch:{name}")
                else:
                    resolved_artifacts[name] = source_path

    source_terminal_switch_metrics: dict[str, int] | None = None
    source_target_state_freshness: dict[str, Any] | None = None
    source_target_measurement_age_samples: list[float] | None = None
    control_source = resolved_artifacts.get("control_commands")
    if verify_source_hashes and control_source is not None:
        try:
            identity_rows = _read_execution_validation_rows(control_source)
        except ActualExecutionEvidenceError as exc:
            reasons.extend(exc.reasons)
        else:
            source_reasons: list[str] = []
            source_identity = _execution_identity_metadata(
                identity_rows,
                source_reasons,
            )
            reasons.extend(source_reasons)
            for name, expected in source_identity.items():
                if metadata.get(name) != expected:
                    reasons.append(
                        f"d7_actual_execution_metadata_source_conflict:{name}"
                    )
            source_terminal_switch_metrics = _terminal_switch_source_metrics(
                identity_rows,
                reasons,
            )
            (
                source_target_state_freshness,
                source_target_measurement_age_samples,
            ) = _target_state_freshness_summary(identity_rows, reasons)

    metrics = payload.get("metrics")
    if not isinstance(metrics, Mapping):
        reasons.append("d7_actual_execution_metrics_not_object")
        metrics = {}
    availability = metrics.get("metric_availability")
    if not isinstance(availability, Mapping):
        reasons.append("d7_actual_execution_metric_availability_not_object")
        availability = {}

    _validate_target_state_freshness_metric(metrics, availability, reasons)

    for name in D7_ACTUAL_EXECUTION_REQUIRED_COUNT_FIELDS:
        if not _is_nonnegative_int(metrics.get(name)):
            reasons.append(f"d7_actual_execution_invalid_count:{name}")
        _require_available_metric(
            availability,
            name,
            reasons,
            expected_source=D7_ACTUAL_EXECUTION_METRIC_SOURCES[name],
        )
        expected_semantics = D7_ACTUAL_EXECUTION_DIAGNOSTIC_SEMANTICS.get(name)
        if expected_semantics is not None:
            entry = availability.get(name)
            if not isinstance(entry, Mapping) or entry.get("semantics") != expected_semantics:
                reasons.append(f"d7_actual_execution_metric_semantics_invalid:{name}")

    if source_terminal_switch_metrics is not None:
        for name, expected in source_terminal_switch_metrics.items():
            if metrics.get(name) != expected:
                reasons.append(f"d7_actual_execution_metric_source_conflict:{name}")
    if (
        source_target_state_freshness is not None
        and not _target_state_freshness_equal(
            metrics.get("target_state_freshness"),
            source_target_state_freshness,
        )
    ):
        reasons.append(
            "d7_actual_execution_metric_source_conflict:target_state_freshness"
        )

    sample_count = metrics.get("performance_sample_count")
    if not _is_int(sample_count) or sample_count <= 0:
        reasons.append("d7_actual_execution_performance_sample_count_invalid")
    _require_available_metric(
        availability,
        "performance_sample_count",
        reasons,
        expected_source=D7_ACTUAL_EXECUTION_METRIC_SOURCES[
            "performance_sample_count"
        ],
    )

    loop_latency = metrics.get("loop_latency_ms")
    if not _is_nonnegative_number(loop_latency):
        reasons.append("d7_actual_execution_loop_latency_ms_invalid")
    _require_available_metric(
        availability,
        "loop_latency_ms",
        reasons,
        expected_source=D7_ACTUAL_EXECUTION_METRIC_SOURCES["loop_latency_ms"],
    )

    if _is_nonnegative_int(sample_count):
        violations = metrics.get("performance_budget_violation_count")
        if _is_nonnegative_int(violations) and violations > sample_count:
            reasons.append(
                "d7_actual_execution_performance_violation_exceeds_samples"
            )

    contract_allowed = _count(metrics, "contract_allowed_count")
    contract_evaluated = _count(metrics, "contract_evaluated_count")
    control_allowed = _count(metrics, "control_allowed_count")
    control_evaluated = _count(metrics, "control_evaluated_count")
    terminal_switch_allowed = _count(metrics, "terminal_switch_allowed_count")
    mode_switched = _count(metrics, "mode_switched_count")
    if (
        contract_allowed is not None
        and contract_evaluated is not None
        and contract_allowed > contract_evaluated
    ):
        reasons.append("d7_actual_execution_contract_count_exceeds_denominator")
    if (
        control_allowed is not None
        and control_evaluated is not None
        and control_allowed > control_evaluated
    ):
        reasons.append("d7_actual_execution_control_count_exceeds_denominator")
    if (
        control_allowed is not None
        and contract_allowed is not None
        and control_allowed > contract_allowed
    ):
        reasons.append("d7_actual_execution_control_exceeds_contract")
    if (
        terminal_switch_allowed is not None
        and control_evaluated is not None
        and terminal_switch_allowed > control_evaluated
    ):
        reasons.append(
            "d7_actual_execution_terminal_switch_count_exceeds_denominator"
        )
    if (
        mode_switched is not None
        and control_allowed is not None
        and mode_switched > control_allowed
    ):
        reasons.append("d7_actual_execution_mode_switch_exceeds_control_allowed")

    visual_switch = _count(metrics, "visual_png_switch_count")
    visual_samples = _count(metrics, "visual_png_control_allowed_sample_count")
    if (
        visual_switch is not None
        and visual_samples is not None
        and visual_switch > visual_samples
    ):
        reasons.append("d7_actual_execution_visual_switch_exceeds_visual_samples")
    if (
        visual_switch is not None
        and mode_switched is not None
        and visual_switch > mode_switched
    ):
        reasons.append("d7_actual_execution_visual_switch_exceeds_mode_switch")

    evaluated = contract_evaluated
    for name in (
        "active_degradation_count",
        "secondary_reassignment_count",
        "d4_reassign_pending_count",
        "terminal_lock_count",
        "terminal_contract_reject_count",
        "truth_identity_online_use_count",
    ):
        value = _count(metrics, name)
        if value is not None and evaluated is not None and value > evaluated:
            reasons.append(f"d7_actual_execution_diagnostic_exceeds_rows:{name}")

    reasons = list(dict.fromkeys(reasons))
    source_recomputed = None
    if (
        not reasons
        and source_target_state_freshness is not None
        and source_target_measurement_age_samples is not None
    ):
        source_recomputed = {
            "target_state_freshness": deepcopy(source_target_state_freshness),
            "target_measurement_age_samples_s": list(
                source_target_measurement_age_samples
            ),
        }
    return {
        "status": "available" if not reasons else "unavailable",
        "schema": schema,
        "validation_reasons": reasons,
        "metrics": deepcopy(dict(metrics)) if not reasons else None,
        "metadata": deepcopy(dict(metadata)) if not reasons else None,
        "source_recomputed": source_recomputed,
        "provenance": {
            "producer": payload.get("producer"),
            "execution_stage": payload.get("execution_stage"),
            "metric_scope": payload.get("metric_scope"),
            "semantics_version": payload.get("semantics_version"),
            "source_artifacts": deepcopy(dict(artifacts))
            if isinstance(artifacts, Mapping)
            else None,
        },
    }


def _validate_execution_identity_metadata(
    metadata: Mapping[str, Any],
    reasons: list[str],
) -> None:
    availability = metadata.get("metadata_availability")
    availability = availability if isinstance(availability, Mapping) else {}
    for name in D7_ACTUAL_EXECUTION_METADATA_SOURCES:
        value = metadata.get(name)
        if not isinstance(value, list):
            reasons.append(f"d7_actual_execution_metadata_invalid:{name}")
            continue
        if name != "owner_node_ids" and not value:
            reasons.append(f"d7_actual_execution_metadata_invalid:{name}")
            continue
        if name == "plan_versions":
            valid_items = all(_is_int(item) and item > 0 for item in value)
            canonical = sorted(value) if valid_items else []
        else:
            valid_items = all(
                isinstance(item, str) and item.strip() == item and bool(item)
                for item in value
            )
            canonical = sorted(value) if valid_items else []
        if not valid_items:
            reasons.append(f"d7_actual_execution_metadata_type_invalid:{name}")
        elif value != canonical or len(value) != len(set(value)):
            reasons.append(f"d7_actual_execution_metadata_not_distinct:{name}")

    if not isinstance(metadata.get("metadata_availability"), Mapping):
        reasons.append("d7_actual_execution_metadata_availability_not_object")
        return
    for name, expected_source in D7_ACTUAL_EXECUTION_METADATA_SOURCES.items():
        entry = availability.get(name)
        if not isinstance(entry, Mapping):
            reasons.append(
                f"d7_actual_execution_metadata_availability_missing:{name}"
            )
            continue
        values = metadata.get(name)
        expected_status = (
            "unavailable"
            if name == "owner_node_ids"
            and isinstance(values, list)
            and not values
            else "available"
        )
        if str(entry.get("status", "")).strip().lower() != expected_status:
            reasons.append(f"d7_actual_execution_metadata_not_available:{name}")
        if entry.get("source_artifact") != expected_source:
            reasons.append(f"d7_actual_execution_metadata_source_invalid:{name}")
        if entry.get("semantics") != D7_ACTUAL_EXECUTION_METADATA_SEMANTICS[name]:
            reasons.append(f"d7_actual_execution_metadata_semantics_invalid:{name}")
        if _nonempty_text(entry.get("reason")) is None:
            reasons.append(f"d7_actual_execution_metadata_reason_invalid:{name}")


def _execution_identity_availability(
    identity: Mapping[str, list[Any]],
) -> dict[str, dict[str, str]]:
    availability: dict[str, dict[str, str]] = {}
    for name in D7_ACTUAL_EXECUTION_METADATA_SOURCES:
        values = identity.get(name, [])
        owner_unavailable = name == "owner_node_ids" and not values
        availability[name] = {
            "status": "unavailable" if owner_unavailable else "available",
            "source_artifact": D7_ACTUAL_EXECUTION_METADATA_SOURCES[name],
            "reason": (
                "no authoritative owner observed; no owner-required execution row"
                if owner_unavailable
                else "validated persisted actual-execution source"
            ),
            "semantics": D7_ACTUAL_EXECUTION_METADATA_SEMANTICS[name],
        }
    return availability


def _require_nonempty_text(
    payload: Mapping[str, Any], name: str, reasons: list[str]
) -> None:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        reasons.append(f"d7_actual_execution_{name}_invalid")


def _require_available_metric(
    availability: Mapping[str, Any],
    name: str,
    reasons: list[str],
    *,
    expected_source: str,
) -> None:
    entry = availability.get(name)
    if not isinstance(entry, Mapping):
        reasons.append(f"d7_actual_execution_availability_missing:{name}")
        return
    if str(entry.get("status", "")).strip().lower() != "available":
        reasons.append(f"d7_actual_execution_metric_not_available:{name}")
    source_artifact = entry.get("source_artifact")
    if source_artifact != expected_source:
        reasons.append(f"d7_actual_execution_metric_source_invalid:{name}")


def _count(metrics: Mapping[str, Any], name: str) -> int | None:
    value = metrics.get(name)
    return int(value) if _is_nonnegative_int(value) else None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_nonnegative_int(value: Any) -> bool:
    return _is_int(value) and value >= 0


def _is_nonnegative_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(float(value))
        and float(value) >= 0.0
    )


def _required_file(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_file():
        raise ActualExecutionEvidenceError(
            [f"d7_actual_execution_source_file_missing:{path}"]
        )
    return path


def _read_json_object(path: Path, source_name: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActualExecutionEvidenceError(
            [f"d7_actual_execution_{source_name}_json_unreadable"]
        ) from exc
    if not isinstance(payload, Mapping):
        raise ActualExecutionEvidenceError(
            [f"d7_actual_execution_{source_name}_root_not_object"]
        )
    return dict(payload)


def _read_control_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ActualExecutionEvidenceError(
                    ["d7_actual_execution_control_header_missing"]
                )
            missing = [name for name in _CONTROL_REQUIRED_FIELDS if name not in reader.fieldnames]
            if missing:
                raise ActualExecutionEvidenceError(
                    [f"d7_actual_execution_control_column_missing:{name}" for name in missing]
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ActualExecutionEvidenceError(
            ["d7_actual_execution_control_csv_unreadable"]
        ) from exc
    if not rows:
        raise ActualExecutionEvidenceError(
            ["d7_actual_execution_control_rows_missing"]
        )
    return rows


def _read_execution_validation_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ActualExecutionEvidenceError(
                    ["d7_actual_execution_control_header_missing"]
                )
            missing = [
                name
                for name in (
                    "plan_id",
                    "plan_version",
                    "d4_target_node_id",
                    "effective_control_authorized",
                    "terminal_switch_allowed",
                    *_TARGET_STATE_FRESHNESS_REQUIRED_FIELDS,
                )
                if name not in reader.fieldnames
            ]
            if missing:
                raise ActualExecutionEvidenceError(
                    [
                        f"d7_actual_execution_control_column_missing:{name}"
                        for name in missing
                    ]
                )
            rows = [dict(row) for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ActualExecutionEvidenceError(
            ["d7_actual_execution_control_csv_unreadable"]
        ) from exc
    if not rows:
        raise ActualExecutionEvidenceError(
            ["d7_actual_execution_control_rows_missing"]
        )
    return rows


def _terminal_switch_source_metrics(
    rows: list[Mapping[str, Any]], reasons: list[str]
) -> dict[str, int]:
    terminal_switch_allowed_count = 0
    for index, row in enumerate(rows):
        try:
            effective_control = _strict_bool(
                row.get("effective_control_authorized"),
                "effective_control_authorized",
            )
            terminal_switch_allowed = _strict_bool(
                row.get("terminal_switch_allowed"),
                "terminal_switch_allowed",
            )
        except ActualExecutionEvidenceError as exc:
            field = exc.reasons[0].rsplit(":", 1)[-1]
            reasons.append(
                f"d7_actual_execution_control_boolean_invalid:{field}:row{index}"
            )
            continue
        if terminal_switch_allowed != effective_control:
            reasons.append("d7_actual_execution_terminal_switch_source_conflict")
        terminal_switch_allowed_count += int(terminal_switch_allowed)
    return {
        "control_evaluated_count": len(rows),
        "terminal_switch_allowed_count": terminal_switch_allowed_count,
    }


def _target_state_freshness_summary(
    rows: list[Mapping[str, Any]],
    reasons: list[str],
) -> tuple[dict[str, Any], list[float]]:
    ages: list[float] = []
    stale_count = 0
    valid_stale_count = 0
    source_distribution: dict[str, int] = {}

    for index, row in enumerate(rows):
        control_timestamp = _nonnegative_finite_number(row.get("timestamp_s"))
        measurement_timestamp = _nonnegative_finite_number(
            row.get("target_measurement_timestamp_s")
        )
        arrival_timestamp = _nonnegative_finite_number(
            row.get("target_arrival_timestamp_s")
        )
        measurement_age = _nonnegative_finite_number(
            row.get("target_measurement_age_s")
        )
        if control_timestamp is None:
            reasons.append(f"d7_actual_execution_timestamp_invalid:row{index}")
        if measurement_timestamp is None:
            reasons.append(
                "d7_actual_execution_target_measurement_timestamp_invalid:"
                f"row{index}"
            )
        if arrival_timestamp is None:
            reasons.append(
                f"d7_actual_execution_target_arrival_timestamp_invalid:row{index}"
            )
        if measurement_age is None:
            reasons.append(
                f"d7_actual_execution_target_measurement_age_invalid:row{index}"
            )

        if measurement_timestamp is not None and arrival_timestamp is not None:
            if measurement_timestamp - arrival_timestamp > (
                _TIMESTAMP_ABS_TOLERANCE_S
            ):
                reasons.append(
                    "d7_actual_execution_target_measurement_arrival_order_conflict:"
                    f"row{index}"
                )
        if arrival_timestamp is not None and control_timestamp is not None:
            if arrival_timestamp - control_timestamp > _TIMESTAMP_ABS_TOLERANCE_S:
                reasons.append(
                    "d7_actual_execution_target_arrival_control_order_conflict:"
                    f"row{index}"
                )
        if (
            control_timestamp is not None
            and measurement_timestamp is not None
            and measurement_age is not None
            and not isclose(
                measurement_age,
                control_timestamp - measurement_timestamp,
                rel_tol=0.0,
                abs_tol=_TIMESTAMP_ABS_TOLERANCE_S,
            )
        ):
            reasons.append(
                f"d7_actual_execution_target_measurement_age_conflict:row{index}"
            )
        if measurement_age is not None:
            ages.append(measurement_age)

        try:
            stale = _strict_freshness_bool(row.get("target_state_stale"))
        except ActualExecutionEvidenceError:
            reasons.append(
                f"d7_actual_execution_target_state_stale_boolean_invalid:row{index}"
            )
        else:
            valid_stale_count += 1
            stale_count += int(stale)

        source = _nonempty_text(row.get("target_state_source"))
        if source is None:
            reasons.append(
                f"d7_actual_execution_target_state_source_missing:row{index}"
            )
        else:
            source_distribution[source] = source_distribution.get(source, 0) + 1

    complete = (
        len(ages) == len(rows)
        and valid_stale_count == len(rows)
        and sum(source_distribution.values()) == len(rows)
    )
    ordered_ages = sorted(ages)
    return {
        "sample_count": len(rows),
        "mean_age_s": sum(ages) / len(ages) if complete else None,
        "p95_age_s": _linear_percentile(ordered_ages, 0.95) if complete else None,
        "max_age_s": max(ages) if complete else None,
        "stale_count": stale_count if complete else None,
        "stale_rate": stale_count / len(rows) if complete else None,
        "source_distribution": (
            dict(sorted(source_distribution.items())) if complete else None
        ),
    }, ages if complete else []


def _validate_target_state_freshness_metric(
    metrics: Mapping[str, Any],
    availability: Mapping[str, Any],
    reasons: list[str],
) -> None:
    summary = metrics.get("target_state_freshness")
    if not isinstance(summary, Mapping):
        reasons.append("d7_actual_execution_target_state_freshness_not_object")
        summary = {}
    missing = [
        name for name in _TARGET_STATE_FRESHNESS_SUMMARY_FIELDS if name not in summary
    ]
    reasons.extend(
        f"d7_actual_execution_target_state_freshness_field_missing:{name}"
        for name in missing
    )

    sample_count = summary.get("sample_count")
    stale_count = summary.get("stale_count")
    stale_rate = summary.get("stale_rate")
    if not _is_int(sample_count) or sample_count <= 0:
        reasons.append("d7_actual_execution_target_state_sample_count_invalid")
    for name in ("mean_age_s", "p95_age_s", "max_age_s"):
        if not _is_nonnegative_number(summary.get(name)):
            reasons.append(f"d7_actual_execution_target_state_{name}_invalid")
    if not _is_nonnegative_int(stale_count):
        reasons.append("d7_actual_execution_target_state_stale_count_invalid")
    if (
        not _is_nonnegative_number(stale_rate)
        or float(stale_rate) > 1.0
    ):
        reasons.append("d7_actual_execution_target_state_stale_rate_invalid")
    if (
        _is_int(sample_count)
        and sample_count > 0
        and _is_nonnegative_int(stale_count)
    ):
        if stale_count > sample_count:
            reasons.append(
                "d7_actual_execution_target_state_stale_count_exceeds_samples"
            )
        if _is_nonnegative_number(stale_rate) and not isclose(
            float(stale_rate),
            stale_count / sample_count,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            reasons.append("d7_actual_execution_target_state_stale_rate_conflict")

    source_distribution = summary.get("source_distribution")
    if not isinstance(source_distribution, Mapping) or not source_distribution:
        reasons.append(
            "d7_actual_execution_target_state_source_distribution_invalid"
        )
    else:
        valid_distribution = all(
            isinstance(name, str)
            and bool(name.strip())
            and name == name.strip()
            and _is_int(count)
            and count > 0
            for name, count in source_distribution.items()
        )
        if not valid_distribution:
            reasons.append(
                "d7_actual_execution_target_state_source_distribution_invalid"
            )
        elif _is_int(sample_count) and sum(source_distribution.values()) != sample_count:
            reasons.append(
                "d7_actual_execution_target_state_source_distribution_count_conflict"
            )

    mean_age = summary.get("mean_age_s")
    p95_age = summary.get("p95_age_s")
    max_age = summary.get("max_age_s")
    if (
        _is_nonnegative_number(mean_age)
        and _is_nonnegative_number(max_age)
        and float(mean_age) > float(max_age) + _TIMESTAMP_ABS_TOLERANCE_S
    ):
        reasons.append("d7_actual_execution_target_state_mean_age_exceeds_max")
    if (
        _is_nonnegative_number(p95_age)
        and _is_nonnegative_number(max_age)
        and float(p95_age) > float(max_age) + _TIMESTAMP_ABS_TOLERANCE_S
    ):
        reasons.append("d7_actual_execution_target_state_p95_age_exceeds_max")

    _require_available_metric(
        availability,
        "target_state_freshness",
        reasons,
        expected_source="control_commands",
    )
    entry = availability.get("target_state_freshness")
    if not isinstance(entry, Mapping):
        return
    if entry.get("source") != "control_commands":
        reasons.append(
            "d7_actual_execution_metric_source_invalid:target_state_freshness"
        )
    if (
        entry.get("semantics")
        != D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS
    ):
        reasons.append(
            "d7_actual_execution_metric_semantics_invalid:target_state_freshness"
        )


def _target_state_freshness_equal(actual: Any, expected: Mapping[str, Any]) -> bool:
    if not isinstance(actual, Mapping):
        return False
    for name in _TARGET_STATE_FRESHNESS_SUMMARY_FIELDS:
        actual_value = actual.get(name)
        expected_value = expected.get(name)
        if name in {"mean_age_s", "p95_age_s", "max_age_s", "stale_rate"}:
            if not (
                _is_nonnegative_number(actual_value)
                and _is_nonnegative_number(expected_value)
                and isclose(
                    float(actual_value),
                    float(expected_value),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
            ):
                return False
        elif actual_value != expected_value:
            return False
    return True


def _linear_percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    position = (len(values) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return values[lower_index] + fraction * (
        values[upper_index] - values[lower_index]
    )


def _execution_identity_metadata(
    rows: list[Mapping[str, Any]],
    reasons: list[str],
) -> dict[str, list[Any]]:
    plan_ids: set[str] = set()
    plan_versions: set[int] = set()
    owner_node_ids: set[str] = set()
    version_by_plan_id: dict[str, int] = {}

    for index, row in enumerate(rows):
        plan_id = _nonempty_text(row.get("plan_id"))
        owner_node_id = _nonempty_text(row.get("d4_target_node_id"))
        plan_version = _positive_csv_int(row.get("plan_version"))
        if plan_id is None:
            reasons.append(f"d7_actual_execution_plan_id_missing:row{index}")
        if plan_version is None:
            reasons.append(f"d7_actual_execution_plan_version_invalid:row{index}")
        if owner_node_id is None and _row_requires_owner(row, index, reasons):
            reasons.append(f"d7_actual_execution_owner_node_id_missing:row{index}")
        if plan_id is None or plan_version is None:
            continue

        previous_version = version_by_plan_id.get(plan_id)
        if previous_version is not None and previous_version != plan_version:
            reasons.append(
                f"d7_actual_execution_plan_version_conflict:{plan_id}"
            )
        else:
            version_by_plan_id[plan_id] = plan_version
        plan_ids.add(plan_id)
        plan_versions.add(plan_version)
        if owner_node_id is not None:
            owner_node_ids.add(owner_node_id)

    return {
        "plan_ids": sorted(plan_ids),
        "plan_versions": sorted(plan_versions),
        "owner_node_ids": sorted(owner_node_ids),
    }


def _row_requires_owner(
    row: Mapping[str, Any],
    index: int,
    reasons: list[str],
) -> bool:
    effective_raw = row.get("effective_control_authorized")
    effective_control = False
    if effective_raw is not None:
        try:
            effective_control = _strict_bool(
                effective_raw,
                "effective_control_authorized",
            )
        except ActualExecutionEvidenceError:
            reasons.append(
                "d7_actual_execution_control_boolean_invalid:"
                f"effective_control_authorized:row{index}"
            )
    phase = _normalized_state(row.get("assignment_phase"))
    d4_mode = _normalized_state(row.get("d4_mode"))
    d4_action = _normalized_state(row.get("d4_action"))
    active_owner_states = {
        "secondary",
        "secondary_active",
        "secondary_execution",
        "secondary_plan_active",
        "secondary_reassignment",
        "distributed",
        "distributed_active",
        "distributed_execution",
        "distributed_plan_active",
        "distributed_reassignment",
    }
    active_owner_actions = {
        "execute_secondary",
        "execute_distributed",
    }
    return effective_control and (
        phase in active_owner_states
        or d4_mode in active_owner_states
        or d4_action in active_owner_actions
    )


def _validate_control_schema(
    rows: list[dict[str, str]], reasons: list[str]
) -> None:
    previous_timestamp: float | None = None
    for index, row in enumerate(rows):
        for name in (
            "terminal_contract_allowed",
            "effective_terminal_contract_allowed",
            "terminal_control_allowed",
            "effective_control_authorized",
            "terminal_switch_allowed",
            "mode_switched",
            "physical_intercept",
            "truth_identity_online_use",
            "truth_state_online_use",
        ):
            try:
                _strict_bool(row.get(name), name)
            except ActualExecutionEvidenceError:
                reasons.append(
                    f"d7_actual_execution_control_boolean_invalid:{name}:row{index}"
                )
        timestamp = _finite_number(row.get("timestamp_s"))
        if timestamp is None or timestamp < 0.0:
            reasons.append(f"d7_actual_execution_timestamp_invalid:row{index}")
        elif previous_timestamp is not None and timestamp < previous_timestamp:
            reasons.append("d7_actual_execution_timestamp_order_conflict")
        else:
            previous_timestamp = timestamp
        if _nonempty_text(row.get("resource_id")) is None:
            reasons.append(f"d7_actual_execution_resource_id_missing:row{index}")
        if _nonempty_text(row.get("target_id")) is None:
            reasons.append(f"d7_actual_execution_target_id_missing:row{index}")


def _validate_simpleflight_summary(
    summary: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    reasons: list[str],
) -> None:
    if summary.get("control_api_used") is not True:
        reasons.append("d7_actual_execution_control_api_not_used")
    if summary.get("runtime_mode") != "SimpleFlight":
        reasons.append("d7_actual_execution_runtime_mode_not_simpleflight")
    if summary.get("physical_intercept_available") is not True:
        reasons.append("d7_actual_execution_physical_evidence_unavailable")
    record_count = summary.get("record_count")
    if not _is_nonnegative_int(record_count) or record_count != len(rows):
        reasons.append("d7_actual_execution_record_count_conflict")


def _command_metrics(
    rows: list[Mapping[str, Any]], reasons: list[str]
) -> tuple[dict[str, int], str]:
    semantics = {
        _nonempty_text(row.get("terminal_semantics_version")) for row in rows
    }
    if None in semantics or len(semantics) != 1:
        reasons.append("d7_actual_execution_terminal_semantics_conflict")
        semantics_version = ""
    else:
        semantics_version = next(iter(semantics)) or ""

    contract_allowed = 0
    control_allowed = 0
    terminal_switch_allowed = 0
    mode_switched = 0
    for row in rows:
        try:
            raw_contract = _strict_bool(
                row.get("terminal_contract_allowed"),
                "terminal_contract_allowed",
            )
            effective_contract = _strict_bool(
                row.get("effective_terminal_contract_allowed"),
                "effective_terminal_contract_allowed",
            )
            raw_control = _strict_bool(
                row.get("terminal_control_allowed"),
                "terminal_control_allowed",
            )
            effective_control = _strict_bool(
                row.get("effective_control_authorized"),
                "effective_control_authorized",
            )
            switch_allowed = _strict_bool(
                row.get("terminal_switch_allowed"),
                "terminal_switch_allowed",
            )
            switched = _strict_bool(row.get("mode_switched"), "mode_switched")
        except ActualExecutionEvidenceError:
            continue
        if raw_contract != effective_contract:
            reasons.append("d7_actual_execution_contract_source_conflict")
        if raw_control != effective_control:
            reasons.append("d7_actual_execution_control_source_conflict")
        if switch_allowed != effective_control:
            reasons.append("d7_actual_execution_terminal_switch_source_conflict")
        contract_allowed += int(effective_contract)
        control_allowed += int(effective_control)
        terminal_switch_allowed += int(switch_allowed)
        mode_switched += int(switched and effective_control)

    return {
        "contract_evaluated_count": len(rows),
        "contract_allowed_count": contract_allowed,
        "control_evaluated_count": len(rows),
        "control_allowed_count": control_allowed,
        "terminal_switch_allowed_count": terminal_switch_allowed,
        "mode_switched_count": mode_switched,
    }, semantics_version


def _physical_metrics(
    summary: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    command_metrics: Mapping[str, int],
    reasons: list[str],
) -> dict[str, int]:
    values: dict[str, int] = {}
    for name in (
        "success_count",
        "pair_physical_success_count",
        "target_intercept_success_count",
        "truth_state_online_use_count",
    ):
        value = summary.get(name)
        if not _is_nonnegative_int(value):
            reasons.append(f"d7_actual_execution_summary_count_invalid:{name}")
        else:
            values[name] = int(value)
    if (
        "success_count" in values
        and "pair_physical_success_count" in values
        and values["success_count"] != values["pair_physical_success_count"]
    ):
        reasons.append("d7_actual_execution_physical_pair_count_conflict")

    csv_physical_count = 0
    for row in rows:
        try:
            csv_physical_count += int(
                _strict_bool(row.get("physical_intercept"), "physical_intercept")
            )
        except ActualExecutionEvidenceError:
            continue
    pair_success = values.get("pair_physical_success_count", 0)
    target_success = values.get("target_intercept_success_count", 0)
    physical = values.get("success_count", 0)
    if target_success > physical:
        reasons.append("d7_actual_execution_target_success_exceeds_pair_success")
    if csv_physical_count != physical:
        reasons.append("d7_actual_execution_command_physical_count_conflict")
    if physical > command_metrics["control_evaluated_count"]:
        reasons.append("d7_actual_execution_physical_count_exceeds_commands")
    return {
        "physical_intercept_count": physical,
        "pair_physical_success_count": pair_success,
        "target_intercept_success_count": target_success,
        "truth_state_online_use_count": values.get(
            "truth_state_online_use_count", 0
        ),
    }


def _actual_diagnostic_metrics(
    rows: list[Mapping[str, Any]], reasons: list[str]
) -> dict[str, int]:
    active_transitions: set[tuple[float, str, str, str]] = set()
    secondary_reassignment_count = 0
    reassign_pending_count = 0
    terminal_lock_count = 0
    visual_png_switch_count = 0
    visual_png_control_allowed_sample_count = 0
    terminal_contract_reject_count = 0
    truth_identity_online_use_count = 0
    previous_phase: dict[tuple[str, str], str] = {}
    previous_active: dict[tuple[str, str], bool] = {}
    previous_pending: dict[tuple[str, str], bool] = {}
    previous_locked: dict[tuple[str, str], bool] = {}
    previous_visual_authorized: dict[tuple[str, str], bool] = {}

    for row in rows:
        resource_id = _nonempty_text(row.get("resource_id")) or ""
        target_id = _nonempty_text(row.get("target_id")) or ""
        pair = (resource_id, target_id)
        phase = _normalized_state(row.get("assignment_phase"))
        d4_mode = _normalized_state(row.get("d4_mode"))
        d4_action = _normalized_state(row.get("d4_action"))
        timestamp = _finite_number(row.get("timestamp_s")) or 0.0
        plan_id = _nonempty_text(row.get("plan_id")) or ""
        plan_version = _nonempty_text(row.get("plan_version")) or ""
        active = d4_mode == "active_degradation"
        if active and not previous_active.get(pair, False):
            active_transitions.add(
                (timestamp, d4_action, plan_id, plan_version)
            )
        previous_active[pair] = active

        old_phase = previous_phase.get(pair, "")
        if phase == "secondary_reassignment" and old_phase != phase:
            secondary_reassignment_count += 1
        pending = phase in {
            "secondary_reassignment_pending",
            "center_replan_pending",
        } or d4_mode == "reassign_pending" or d4_action in {
            "request_center_replan",
            "reassign",
        }
        if pending and not previous_pending.get(pair, False):
            reassign_pending_count += 1
        previous_pending[pair] = pending
        previous_phase[pair] = phase

        d5_locked = _normalized_state(row.get("d5_decision_state")) == "locked"
        try:
            d7_locked = _strict_bool(row.get("terminal_locked"), "terminal_locked")
        except ActualExecutionEvidenceError:
            d7_locked = False
        locked = d5_locked or d7_locked
        if locked and not previous_locked.get(pair, False):
            terminal_lock_count += 1
        previous_locked[pair] = locked

        try:
            effective_control = _strict_bool(
                row.get("effective_control_authorized"),
                "effective_control_authorized",
            )
            switched = _strict_bool(row.get("mode_switched"), "mode_switched")
        except ActualExecutionEvidenceError:
            effective_control = False
            switched = False
        visual = _is_visual_png_row(row)
        visual_authorized = effective_control and visual
        visual_png_control_allowed_sample_count += int(visual_authorized)
        visual_png_switch_count += int(
            visual_authorized
            and switched
            and not previous_visual_authorized.get(pair, False)
        )
        previous_visual_authorized[pair] = visual_authorized
        terminal_contract_reject_count += int(
            _nonempty_text(row.get("terminal_contract_reject_reason")) is not None
        )
        try:
            truth_identity_online_use_count += int(
                _strict_bool(
                    row.get("truth_identity_online_use"),
                    "truth_identity_online_use",
                )
            )
        except ActualExecutionEvidenceError:
            pass

    if visual_png_switch_count > visual_png_control_allowed_sample_count:
        reasons.append("d7_actual_execution_visual_switch_exceeds_visual_samples")
    return {
        "active_degradation_count": len(active_transitions),
        "secondary_reassignment_count": secondary_reassignment_count,
        "d4_reassign_pending_count": reassign_pending_count,
        "terminal_lock_count": terminal_lock_count,
        "visual_png_switch_count": visual_png_switch_count,
        "visual_png_control_allowed_sample_count": (
            visual_png_control_allowed_sample_count
        ),
        "terminal_contract_reject_count": terminal_contract_reject_count,
        "truth_identity_online_use_count": truth_identity_online_use_count,
    }


def _performance_metrics(
    main_bundle: Mapping[str, Any],
    main_metrics: Mapping[str, Any],
    reasons: list[str],
) -> dict[str, int | float]:
    metadata = main_metrics.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    clock = metadata.get("clock")
    if not isinstance(clock, Mapping):
        reasons.append("d7_actual_execution_performance_clock_missing")
        clock = {}
    sample_count = clock.get("frame_count")
    if not _is_int(sample_count) or sample_count <= 0:
        reasons.append("d7_actual_execution_performance_samples_missing")
        sample_count = 0
    top_metadata = main_bundle.get("metadata")
    top_metadata = top_metadata if isinstance(top_metadata, Mapping) else {}
    record_counts = top_metadata.get("record_counts")
    tick_count = record_counts.get("ticks") if isinstance(record_counts, Mapping) else None
    if not _is_int(tick_count) or tick_count <= 0 or tick_count != sample_count:
        reasons.append("d7_actual_execution_performance_sample_count_conflict")

    loop_latency = main_metrics.get("loop_latency_ms")
    clock_mean = clock.get("mean_processing_duration_s")
    if not _is_nonnegative_number(loop_latency):
        reasons.append("d7_actual_execution_loop_latency_missing")
        loop_latency = 0.0
    if not _is_nonnegative_number(clock_mean):
        reasons.append("d7_actual_execution_clock_mean_missing")
    elif abs(float(loop_latency) - float(clock_mean) * 1000.0) > 1e-6:
        reasons.append("d7_actual_execution_loop_latency_source_conflict")

    violations = main_metrics.get("performance_budget_violation_count")
    if not _is_nonnegative_int(violations):
        reasons.append("d7_actual_execution_performance_violation_count_missing")
        violations = 0
    elif sample_count and violations > sample_count:
        reasons.append("d7_actual_execution_performance_violation_exceeds_samples")
    return {
        "performance_sample_count": int(sample_count),
        "loop_latency_ms": float(loop_latency),
        "performance_budget_violation_count": int(violations),
    }


def _validate_main_execution_consistency(
    main_metrics: Mapping[str, Any],
    command_metrics: Mapping[str, int],
    physical_metrics: Mapping[str, int],
    reasons: list[str],
) -> None:
    for name in ("control_allowed_count", "mode_switched_count"):
        value = main_metrics.get(name)
        if not _is_nonnegative_int(value) or value != command_metrics[name]:
            reasons.append(f"d7_actual_execution_main_{name}_conflict")
    value = main_metrics.get("physical_intercept_count")
    if not _is_nonnegative_int(value) or value != physical_metrics["physical_intercept_count"]:
        reasons.append("d7_actual_execution_main_physical_intercept_count_conflict")


def _strict_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ActualExecutionEvidenceError(
        [f"d7_actual_execution_boolean_invalid:{field}"]
    )


def _strict_freshness_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise ActualExecutionEvidenceError(
        ["d7_actual_execution_boolean_invalid:target_state_stale"]
    )


def _nonempty_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _normalized_state(value: Any) -> str:
    text = _nonempty_text(value)
    return text.lower().replace("-", "_").replace(" ", "_") if text else ""


def _is_visual_png_row(row: Mapping[str, Any]) -> bool:
    guidance_law = _normalized_state(row.get("guidance_law"))
    mode = _normalized_state(row.get("mode"))
    return guidance_law in {
        "png_vm",
        "png_ttc",
        "visual_png",
        "vision_png",
    } or mode in {
        "vision_terminal",
        "visual_png",
        "vision_png",
    }


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _nonnegative_finite_number(value: Any) -> float | None:
    parsed = _finite_number(value)
    return parsed if parsed is not None and parsed >= 0.0 else None


def _positive_csv_int(value: Any) -> int | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if re.fullmatch(r"[1-9][0-9]*", normalized) is None:
        return None
    return int(normalized)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source_path(
    raw_path: str, source_base_dir: str | Path | None
) -> Path | None:
    path = Path(raw_path).expanduser()
    candidates = [path]
    if not path.is_absolute() and source_base_dir is not None:
        candidates.append(Path(source_base_dir) / path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None
