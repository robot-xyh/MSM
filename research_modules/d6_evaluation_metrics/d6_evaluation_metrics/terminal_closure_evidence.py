"""Fail-closed case evidence wiring for terminal-closure suites.

The main runtime owns production and registration of evidence paths. D6 only
loads persisted JSON after a case row names the path explicitly. Missing or
invalid evidence is represented as unavailable; it is never inferred from a
neighbouring output directory and never replaced with zero-valued metrics.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

from .execution_evidence import (
    D7_ACTUAL_EXECUTION_SCHEMA_VERSION,
    D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    validate_d7_actual_execution_payload,
)
from .p1_system_evidence import summarize_d3_canonical_history


TERMINAL_CLOSURE_CASE_EVIDENCE_REGISTRATION_SCHEMA_VERSION = (
    "d6-terminal-closure-case-evidence-registration-v1"
)
D3_CASE_HISTORY_SUITE_SCHEMA_VERSION = "d6-d3-case-history-suite-v1"
D7_EXECUTION_CASE_SUITE_SCHEMA_VERSION = "d6-d7-execution-case-suite-v3"
D7_EXECUTION_STRUCTURAL_SCHEMA_VERSION = D7_ACTUAL_EXECUTION_SCHEMA_VERSION
D7_ACTUAL_EXECUTION_UNAVAILABLE_SCHEMA_VERSION = (
    "d7-actual-execution-unavailable-v1"
)
_D7_EXPORTED_METRICS = (
    "active_degradation_count",
    "secondary_reassignment_count",
    "d4_reassign_pending_count",
    "terminal_lock_count",
    "visual_png_switch_count",
    "visual_png_control_allowed_sample_count",
    "terminal_contract_reject_count",
    "contract_allowed_count",
    "contract_evaluated_count",
    "control_allowed_count",
    "control_evaluated_count",
    "terminal_switch_allowed_count",
    "mode_switched_count",
    "physical_intercept_count",
    "pair_physical_success_count",
    "target_intercept_success_count",
    "coalition_completion_count",
    "truth_identity_online_use_count",
    "truth_state_online_use_count",
)
_D3_CHURN_FIELDS = (
    "plan_version_churn_count",
    "coalition_version_churn_count",
    "coalition_epoch_churn_count",
    "membership_change_count",
    "primary_membership_change_count",
    "reserve_membership_change_count",
    "owner_change_count",
    "feedback_churn_count",
    "soft_feedback_churn_count",
    "hard_feedback_churn_count",
    "latest_soft_feedback_count",
    "latest_hard_feedback_count",
)
_UNSET = object()


def register_terminal_closure_case_evidence(
    row: Mapping[str, Any],
    *,
    d3_plan_history_path: str | Path | None | object = _UNSET,
    d7_execution_metrics_path: str | Path | None | object = _UNSET,
    d7_execution_unavailable_path: str | Path | None | object = _UNSET,
) -> dict[str, Any]:
    """Return a copied main case row with explicit evidence registrations.

    Main can use this helper after producer files are written. A ``None`` path
    is an explicit unavailable registration, not a request for D6 to search a
    directory. Omitted keyword arguments leave the corresponding row field
    unchanged.
    """

    registered = deepcopy(dict(row))
    if d3_plan_history_path is not _UNSET:
        _register_path(
            registered,
            field="d3_plan_history",
            source="d3_plan_history",
            value=d3_plan_history_path,
        )
    if d7_execution_metrics_path is not _UNSET:
        _register_path(
            registered,
            field="d7_execution_metrics",
            source="d7_terminal_execution",
            value=d7_execution_metrics_path,
        )
    if d7_execution_unavailable_path is not _UNSET:
        _register_path(
            registered,
            field="d7_execution_unavailable",
            source="d7_terminal_execution_unavailable",
            value=d7_execution_unavailable_path,
        )
    return registered


def summarize_terminal_closure_case_evidence(
    main_summary: Mapping[str, Any] | None,
    *,
    main_summary_path: str | Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Load and summarize D3/D7 paths registered on main suite rows."""

    rows = _mapping_rows((main_summary or {}).get("rows"))
    base_dir = _summary_base_dir(main_summary_path)
    d3_cases = [
        _load_d3_case(row, row_index=index, base_dir=base_dir)
        for index, row in enumerate(rows)
    ]
    d7_cases = [
        _load_d7_case(row, row_index=index, base_dir=base_dir)
        for index, row in enumerate(rows)
    ]
    _reject_duplicate_bindings(d3_cases, source_name="d3_plan_history")
    _reject_duplicate_bindings(d7_cases, source_name="d7_terminal_execution")
    return {
        "d3_plan_history": _aggregate_d3_cases(d3_cases),
        "d7_terminal_execution": _aggregate_d7_cases(d7_cases),
    }


def _register_path(
    row: dict[str, Any],
    *,
    field: str,
    source: str,
    value: str | Path | None | object,
) -> None:
    path = None if value is None else str(value)
    row[field] = path
    available = bool(path and path.strip())
    reason = None if available else f"{field}_path_not_registered_by_main"
    row[f"{field}_registration"] = {
        "schema": TERMINAL_CLOSURE_CASE_EVIDENCE_REGISTRATION_SCHEMA_VERSION,
        "source": source,
        "status": "registered" if available else "unavailable",
        "path": path,
        "reason": reason,
    }


def _load_d3_case(
    row: Mapping[str, Any], *, row_index: int, base_dir: Path | None
) -> dict[str, Any]:
    case = _case_identity(row, row_index=row_index)
    loaded = _load_registered_json(
        row,
        field="d3_plan_history",
        source="d3_plan_history",
        base_dir=base_dir,
    )
    reasons = list(case["identity_reasons"])
    reasons.extend(loaded["reasons"])
    summary: dict[str, Any] | None = None
    if loaded["payload"] is not None:
        summary = summarize_d3_canonical_history(loaded["payload"])
        reasons.extend(str(reason) for reason in summary["validation_reasons"])
        if (
            case["seed"] is not None
            and summary.get("seed") is not None
            and summary.get("seed") != case["seed"]
        ):
            reasons.append("d3_case_seed_mismatch")
    reasons = list(dict.fromkeys(reasons))
    available = not reasons and summary is not None and summary["status"] == "available"
    return {
        "schema": "d6-d3-case-history-evidence-v1",
        "case_id": case["case_id"],
        "seed": case["seed"],
        "status": "available" if available else "unavailable",
        "evidence_path": loaded["evidence_path"],
        "resolved_evidence_path": loaded["resolved_evidence_path"],
        "wiring_status": loaded["wiring_status"],
        "wiring_reason": loaded["wiring_reason"],
        "validation_reasons": reasons,
        "summary": summary if available else None,
    }


def _load_d7_case(
    row: Mapping[str, Any], *, row_index: int, base_dir: Path | None
) -> dict[str, Any]:
    case = _case_identity(row, row_index=row_index)
    reasons = list(case["identity_reasons"])
    required, requirement_source = _actual_execution_requirement(row)
    unavailable_field, unavailable_path, unavailable_field_reasons = (
        _explicit_unavailable_registration(row)
    )
    reasons.extend(unavailable_field_reasons)
    metrics_path = row.get("d7_execution_metrics")
    metrics_registered = _registered_path(metrics_path)
    unavailable_registered = _registered_path(unavailable_path)
    canonical_kind = "none"
    if metrics_registered and unavailable_registered:
        reasons.append("d7_actual_execution_conflicting_canonical_artifacts")

    if metrics_registered:
        canonical_kind = "metrics"
        loaded = _load_registered_json(
            row,
            field="d7_execution_metrics",
            source="d7_terminal_execution",
            base_dir=base_dir,
        )
    elif unavailable_registered and unavailable_field is not None:
        canonical_kind = "unavailable"
        loaded = _load_registered_json(
            row,
            field=unavailable_field,
            source="d7_terminal_execution_unavailable",
            base_dir=base_dir,
        )
    else:
        loaded = _load_registered_json(
            row,
            field="d7_execution_metrics",
            source="d7_terminal_execution",
            base_dir=base_dir,
        )
    reasons.extend(loaded["reasons"])
    payload = loaded["payload"]
    detected_schema: str | None = None
    metrics: dict[str, Any] | None = None
    target_state_freshness: dict[str, Any] | None = None
    target_measurement_age_samples: list[float] = []
    unavailable_reasons: list[str] = []
    if payload is not None and canonical_kind == "metrics":
        validation = validate_d7_actual_execution_payload(
            payload,
            expected_seed=case["seed"],
            expected_case_id=case["case_id"],
            source_base_dir=(
                Path(loaded["resolved_evidence_path"]).parent
                if loaded["resolved_evidence_path"] is not None
                else None
            ),
            verify_source_hashes=True,
        )
        payload_reasons = validation["validation_reasons"]
        detected_schema = validation["schema"]
        reasons.extend(payload_reasons)
        if not payload_reasons:
            validated_metrics = validation["metrics"] or {}
            metrics = {
                name: validated_metrics.get(name) for name in _D7_EXPORTED_METRICS
            }
            freshness_summary = validated_metrics.get("target_state_freshness")
            metric_availability = validated_metrics.get("metric_availability")
            freshness_availability = (
                metric_availability.get("target_state_freshness")
                if isinstance(metric_availability, Mapping)
                else None
            )
            if isinstance(freshness_summary, Mapping) and isinstance(
                freshness_availability, Mapping
            ):
                target_state_freshness = {
                    **deepcopy(dict(freshness_summary)),
                    "metric_availability": deepcopy(
                        dict(freshness_availability)
                    ),
                    "source": freshness_availability.get("source"),
                    "semantics": freshness_availability.get("semantics"),
                }
            source_recomputed = validation.get("source_recomputed")
            if isinstance(source_recomputed, Mapping):
                samples = source_recomputed.get(
                    "target_measurement_age_samples_s"
                )
                if isinstance(samples, Sequence) and not isinstance(
                    samples, (str, bytes)
                ):
                    target_measurement_age_samples = [
                        float(value) for value in samples
                    ]
    elif payload is not None and canonical_kind == "unavailable":
        detected_schema = _source_schema(payload)
        unavailable_reasons.extend(
            _validate_unavailable_payload(
                payload,
                expected_case_id=case["case_id"],
                expected_seed=case["seed"],
            )
        )
        passthrough = payload.get("reasons")
        if isinstance(passthrough, Sequence) and not isinstance(
            passthrough, (str, bytes)
        ):
            unavailable_reasons.extend(
                str(reason).strip()
                for reason in passthrough
                if isinstance(reason, str) and reason.strip()
            )
        row_reasons = row.get("d7_execution_unavailable_reasons")
        if row_reasons is not None:
            normalized_row_reasons = _normalized_reason_list(row_reasons)
            if normalized_row_reasons is None:
                reasons.append("d7_execution_unavailable_reasons_invalid")
            elif normalized_row_reasons != list(dict.fromkeys(unavailable_reasons)):
                reasons.append("d7_execution_unavailable_reasons_mismatch")
    reasons = list(dict.fromkeys(reasons))
    unavailable_reasons = list(dict.fromkeys(unavailable_reasons))
    available = (
        canonical_kind == "metrics"
        and not reasons
        and payload is not None
        and metrics is not None
        and target_state_freshness is not None
        and bool(target_measurement_age_samples)
    )
    if canonical_kind == "unavailable" and not unavailable_reasons:
        reasons.append("d7_actual_execution_unavailable_reasons_missing")
    validation_reasons = list(
        dict.fromkeys(
            (*reasons, *(unavailable_reasons if canonical_kind == "unavailable" else ()))
        )
    )
    terminal_layer_import_status = "available" if available else "unavailable"
    terminal_layer_import_reason = (
        "canonical_actual_execution_five_layers_validated"
        if available
        else "d7_execution_evidence_unavailable"
    )
    return {
        "schema": "d6-d7-execution-case-evidence-v2",
        "case_id": case["case_id"],
        "seed": case["seed"],
        "family": row.get("family"),
        "profile": row.get("profile"),
        "resource_count": row.get("resource_count"),
        "target_count": row.get("target_count"),
        "status": "available" if available else "unavailable",
        "actual_execution_required": required,
        "actual_execution_requirement_source": requirement_source,
        "actual_execution_available": available,
        "canonical_artifact_kind": canonical_kind,
        "evidence_path": loaded["evidence_path"],
        "resolved_evidence_path": loaded["resolved_evidence_path"],
        "wiring_status": loaded["wiring_status"],
        "wiring_reason": loaded["wiring_reason"],
        "detected_payload_schema": detected_schema,
        "validation_reasons": validation_reasons,
        "canonical_unavailable_reasons": unavailable_reasons,
        "metrics": metrics if available else None,
        "target_state_freshness": (
            target_state_freshness if available else None
        ),
        "_target_measurement_age_samples_s": (
            target_measurement_age_samples if available else []
        ),
        "terminal_layer_import_status": terminal_layer_import_status,
        "terminal_layer_import_reason": terminal_layer_import_reason,
    }


def _load_registered_json(
    row: Mapping[str, Any],
    *,
    field: str,
    source: str,
    base_dir: Path | None,
) -> dict[str, Any]:
    raw_path = row.get(field)
    registration = row.get(f"{field}_registration")
    reasons: list[str] = []
    if registration is not None:
        if not isinstance(registration, Mapping):
            reasons.append(f"{field}_registration_not_object")
        else:
            if registration.get("schema") != (
                TERMINAL_CLOSURE_CASE_EVIDENCE_REGISTRATION_SCHEMA_VERSION
            ):
                reasons.append(f"{field}_registration_schema_mismatch")
            if registration.get("source") != source:
                reasons.append(f"{field}_registration_source_mismatch")
            if registration.get("path") != raw_path:
                reasons.append(f"{field}_registration_path_mismatch")
    if not isinstance(raw_path, (str, Path)) or not str(raw_path).strip():
        reason = f"{field}_path_not_registered_by_main"
        return {
            "payload": None,
            "evidence_path": None,
            "resolved_evidence_path": None,
            "wiring_status": "unavailable",
            "wiring_reason": reason,
            "reasons": list(dict.fromkeys((*reasons, reason))),
        }

    evidence_path = str(raw_path)
    path = _first_existing_path(evidence_path, base_dir=base_dir)
    if path is None:
        reason = f"{field}_file_not_found"
        return {
            "payload": None,
            "evidence_path": evidence_path,
            "resolved_evidence_path": None,
            "wiring_status": "registered",
            "wiring_reason": None,
            "reasons": list(dict.fromkeys((*reasons, reason))),
        }
    if path.suffix.lower() != ".json":
        reasons.append(f"{field}_not_json")
        return {
            "payload": None,
            "evidence_path": evidence_path,
            "resolved_evidence_path": str(path),
            "wiring_status": "registered",
            "wiring_reason": None,
            "reasons": list(dict.fromkeys(reasons)),
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        reasons.append(f"{field}_json_unreadable")
        payload = None
    if payload is not None and not isinstance(payload, Mapping):
        reasons.append(f"{field}_root_not_object")
        payload = None
    return {
        "payload": None if payload is None else dict(payload),
        "evidence_path": evidence_path,
        "resolved_evidence_path": str(path),
        "wiring_status": "registered",
        "wiring_reason": None,
        "reasons": list(dict.fromkeys(reasons)),
    }


def _aggregate_d3_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in cases if item["status"] == "available"]
    by_case_seed = [_flatten_d3_case(item) for item in cases]
    churn_totals = {
        name: sum(
            int(item["summary"]["churn"][name])
            for item in available
            if item["summary"]["churn"].get(name) is not None
        )
        for name in _D3_CHURN_FIELDS
    }
    return {
        "schema": D3_CASE_HISTORY_SUITE_SCHEMA_VERSION,
        "status": _suite_status(cases),
        "validation_reasons": (
            [] if cases else ["history_summary_not_provided"]
        ),
        "aggregation_scope": "case_seed",
        "case_count": len(cases),
        "available_case_count": len(available),
        "unavailable_case_count": len(cases) - len(available),
        "record_count": (
            sum(int(item["summary"]["record_count"]) for item in available)
            if available
            else None
        ),
        "latest_plan": None,
        "primary_membership": None,
        "reserve_membership": None,
        "owner": None,
        "churn": churn_totals if available else None,
        "validation_reason_counts": _reason_counts(cases),
        "by_case_seed": by_case_seed,
        "by_seed": _by_seed(by_case_seed),
    }


def _aggregate_d7_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in cases if item["status"] == "available"]
    required = [item for item in cases if item["actual_execution_required"]]
    required_available = [item for item in required if item["status"] == "available"]
    actual_execution_all_available: bool | None = (
        None
        if not required
        else len(required_available) == len(required)
    )
    by_case_seed = [
        {
            key: deepcopy(value)
            for key, value in item.items()
            if key != "_target_measurement_age_samples_s"
        }
        for item in cases
    ]
    metric_summaries: dict[str, Any] = {}
    for name in _D7_EXPORTED_METRICS:
        values = [
            item["metrics"].get(name)
            for item in available
            if item.get("metrics") is not None
            and _nonnegative_number(item["metrics"].get(name)) is not None
        ]
        metric_summaries[name] = {
            "status": "available" if values else "unavailable",
            "available_case_count": len(values),
            "unavailable_case_count": len(cases) - len(values),
            "sum": sum(values) if values else None,
        }
    return {
        "schema": D7_EXECUTION_CASE_SUITE_SCHEMA_VERSION,
        "status": _suite_status(cases),
        "aggregation_scope": "case_seed",
        "case_count": len(cases),
        "available_case_count": len(available),
        "unavailable_case_count": len(cases) - len(available),
        "actual_execution_required_case_count": len(required),
        "actual_execution_available_case_count": len(required_available),
        "actual_execution_unavailable_case_count": (
            len(required) - len(required_available)
        ),
        "actual_execution_all_available": actual_execution_all_available,
        "actual_execution_gate_status": (
            "not_applicable"
            if actual_execution_all_available is None
            else "pass" if actual_execution_all_available else "fail"
        ),
        "all_paths_registered": bool(cases)
        and all(item["wiring_status"] == "registered" for item in cases),
        "wiring_reason_counts": dict(
            sorted(
                Counter(
                    item["wiring_reason"]
                    for item in cases
                    if item.get("wiring_reason")
                ).items()
            )
        ),
        "validation_reason_counts": _reason_counts(cases),
        "metrics": metric_summaries,
        "target_state_freshness": _aggregate_target_state_freshness(cases),
        "by_case_seed": by_case_seed,
        "by_seed": _by_seed(by_case_seed),
    }


def _aggregate_target_state_freshness(
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    available = [
        item
        for item in cases
        if item.get("status") == "available"
        and isinstance(item.get("target_state_freshness"), Mapping)
        and isinstance(item.get("_target_measurement_age_samples_s"), list)
        and item.get("_target_measurement_age_samples_s")
    ]
    status = _suite_status(available) if len(available) == len(cases) else (
        "partial" if available else "unavailable"
    )
    metric_availability = {
        "status": "available" if available else "unavailable",
        "source": "control_commands" if available else None,
        "source_artifact": "control_commands" if available else None,
        "reason": (
            "pooled from source-hash-verified control command samples"
            if available
            else "no source-hash-verified target-state freshness case"
        ),
        "semantics": D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    }
    if not available:
        return {
            "status": status,
            "available_case_count": 0,
            "unavailable_case_count": len(cases),
            "sample_count": None,
            "mean_age_s": None,
            "p95_age_s": None,
            "max_age_s": None,
            "stale_count": None,
            "stale_rate": None,
            "source_distribution": None,
            "metric_availability": metric_availability,
            "source": None,
            "semantics": D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
        }

    ages = sorted(
        float(value)
        for item in available
        for value in item["_target_measurement_age_samples_s"]
    )
    stale_count = sum(
        int(item["target_state_freshness"]["stale_count"])
        for item in available
    )
    source_distribution: Counter[str] = Counter()
    for item in available:
        source_distribution.update(
            dict(item["target_state_freshness"]["source_distribution"])
        )
    return {
        "status": status,
        "available_case_count": len(available),
        "unavailable_case_count": len(cases) - len(available),
        "sample_count": len(ages),
        "mean_age_s": sum(ages) / len(ages),
        "p95_age_s": _linear_percentile(ages, 0.95),
        "max_age_s": max(ages),
        "stale_count": stale_count,
        "stale_rate": stale_count / len(ages),
        "source_distribution": dict(sorted(source_distribution.items())),
        "metric_availability": metric_availability,
        "source": "control_commands",
        "semantics": D7_ACTUAL_EXECUTION_TARGET_STATE_FRESHNESS_SEMANTICS,
    }


def _actual_execution_requirement(row: Mapping[str, Any]) -> tuple[bool, str]:
    explicit = row.get("actual_execution_required")
    if explicit is True:
        return True, "main_explicit"
    for name in ("execution_mode", "vehicle_mode", "vehicle_type"):
        value = row.get(name)
        if isinstance(value, str) and value.strip().lower() == "simpleflight":
            return True, name
    if any(
        _registered_path(row.get(name))
        for name in (
            "control_commands",
            "intercept_summary",
            "main_episode_bus_metrics",
            "d7_execution_metrics",
            "d7_execution_unavailable",
            "d7_actual_execution_unavailable",
        )
    ):
        return True, "persisted_simpleflight_artifact_registration"
    if explicit is False:
        return False, "main_explicit"
    return False, "not_declared"


def _explicit_unavailable_registration(
    row: Mapping[str, Any],
) -> tuple[str | None, Any, list[str]]:
    candidates = [
        (name, row.get(name))
        for name in (
            "d7_execution_unavailable",
            "d7_actual_execution_unavailable",
        )
        if _registered_path(row.get(name))
    ]
    if not candidates:
        return None, None, []
    distinct = {str(value) for _, value in candidates}
    reasons = (
        ["d7_execution_unavailable_alias_path_mismatch"]
        if len(distinct) > 1
        else []
    )
    return candidates[0][0], candidates[0][1], reasons


def _validate_unavailable_payload(
    payload: Mapping[str, Any],
    *,
    expected_case_id: str,
    expected_seed: int | None,
) -> list[str]:
    reasons: list[str] = []
    if _source_schema(payload) != D7_ACTUAL_EXECUTION_UNAVAILABLE_SCHEMA_VERSION:
        reasons.append("d7_actual_execution_unavailable_schema_mismatch")
    if payload.get("status") != "unavailable":
        reasons.append("d7_actual_execution_unavailable_status_invalid")
    case_id = payload.get("case_id")
    if case_id is not None and case_id != expected_case_id:
        reasons.append("d7_actual_execution_unavailable_case_id_mismatch")
    seed = payload.get("seed")
    if seed is not None and seed != expected_seed:
        reasons.append("d7_actual_execution_unavailable_seed_mismatch")
    normalized = _normalized_reason_list(payload.get("reasons"))
    if normalized is None or not normalized:
        reasons.append("d7_actual_execution_unavailable_reasons_missing")
    return reasons


def _normalized_reason_list(value: Any) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    reasons: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        reasons.append(item.strip())
    return list(dict.fromkeys(reasons))


def _source_schema(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("schema") or payload.get("schema_version")
    return str(value) if value is not None else None


def _registered_path(value: Any) -> bool:
    return isinstance(value, (str, Path)) and bool(str(value).strip())


def _flatten_d3_case(item: Mapping[str, Any]) -> dict[str, Any]:
    summary = item.get("summary") if isinstance(item.get("summary"), Mapping) else {}
    return {
        key: deepcopy(value)
        for key, value in {
            "schema": item.get("schema"),
            "case_id": item.get("case_id"),
            "seed": item.get("seed"),
            "status": item.get("status"),
            "evidence_path": item.get("evidence_path"),
            "resolved_evidence_path": item.get("resolved_evidence_path"),
            "wiring_status": item.get("wiring_status"),
            "wiring_reason": item.get("wiring_reason"),
            "validation_reasons": item.get("validation_reasons"),
            "episode_id": summary.get("episode_id"),
            "scenario_name": summary.get("scenario_name"),
            "record_count": summary.get("record_count"),
            "latest_plan": summary.get("latest_plan"),
            "primary_membership": summary.get("primary_membership"),
            "reserve_membership": summary.get("reserve_membership"),
            "owner": summary.get("owner"),
            "churn": summary.get("churn"),
        }.items()
    }


def _reject_duplicate_bindings(
    cases: list[dict[str, Any]], *, source_name: str
) -> None:
    case_counts = Counter((item["case_id"], item["seed"]) for item in cases)
    path_counts = Counter(
        item["resolved_evidence_path"]
        for item in cases
        if item.get("resolved_evidence_path")
    )
    for item in cases:
        reasons = list(item["validation_reasons"])
        if case_counts[(item["case_id"], item["seed"])] > 1:
            reasons.append(f"{source_name}_duplicate_case_seed_registration")
        path = item.get("resolved_evidence_path")
        if path and path_counts[path] > 1:
            reasons.append(f"{source_name}_evidence_path_reused_across_cases")
        if reasons:
            item["status"] = "unavailable"
            item["validation_reasons"] = list(dict.fromkeys(reasons))
            if "summary" in item:
                item["summary"] = None
            if "metrics" in item:
                item["metrics"] = None
            if "target_state_freshness" in item:
                item["target_state_freshness"] = None
            if "_target_measurement_age_samples_s" in item:
                item["_target_measurement_age_samples_s"] = []


def _case_identity(row: Mapping[str, Any], *, row_index: int) -> dict[str, Any]:
    reasons: list[str] = []
    raw_case_id = row.get("case_id") or row.get("scenario_id")
    if not isinstance(raw_case_id, str) or not raw_case_id.strip():
        case_id = f"row_{row_index:04d}"
        reasons.append("case_id_missing_or_invalid")
    else:
        case_id = raw_case_id.strip()
    seed = row.get("seed")
    if not _is_int(seed):
        reasons.append("case_seed_missing_or_invalid")
        seed = None
    return {
        "case_id": case_id,
        "seed": seed,
        "identity_reasons": reasons,
    }


def _first_existing_path(raw: str, *, base_dir: Path | None) -> Path | None:
    path = Path(raw).expanduser()
    candidates = [path]
    if not path.is_absolute() and base_dir is not None:
        candidates.append(base_dir / path)
    for candidate in candidates:
        if candidate.is_file():
            try:
                return candidate.resolve()
            except OSError:
                return candidate
    return None


def _summary_base_dir(path: str | Path | None) -> Path | None:
    if path is None:
        return None
    candidate = Path(path).expanduser()
    return candidate.parent if candidate.suffix else candidate


def _suite_status(cases: Sequence[Mapping[str, Any]]) -> str:
    available = sum(item.get("status") == "available" for item in cases)
    if available == len(cases) and cases:
        return "available"
    if available:
        return "partial"
    return "unavailable"


def _reason_counts(cases: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(reason)
                for item in cases
                for reason in item.get("validation_reasons", ())
            ).items()
        )
    )


def _by_seed(cases: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[Any, list[Mapping[str, Any]]] = {}
    for item in cases:
        grouped.setdefault(item.get("seed"), []).append(item)
    return [
        {
            "seed": seed,
            "case_count": len(items),
            "available_case_count": sum(
                item.get("status") == "available" for item in items
            ),
            "unavailable_case_count": sum(
                item.get("status") != "available" for item in items
            ),
            "case_ids": [item.get("case_id") for item in items],
        }
        for seed, items in sorted(grouped.items(), key=lambda pair: str(pair[0]))
    ]


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonnegative_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isfinite(float(value)) or value < 0:
        return None
    return value


def _linear_percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    position = (len(values) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(values) - 1)
    fraction = position - lower_index
    return float(values[lower_index]) + fraction * (
        float(values[upper_index]) - float(values[lower_index])
    )
