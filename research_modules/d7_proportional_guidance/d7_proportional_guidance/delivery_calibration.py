"""Report-only calibration helpers for terminal delivery experiments."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any


D7_DELIVERY_CALIBRATION_BOUNDARY = "d7_p1_terminal_delivery_calibration_report_only"
DEFAULT_DROPOUT_FRAME_COUNTS = (1, 2, 3, 4, 5)
PNG_TTC_REQUIRED_REJECT_CLASSES = (
    "bbox_area_jump",
    "bbox_clipping",
    "area_not_expanding",
    "ttc_out_of_range",
)
PNG_TTC_CONTROLLED_DISTURBANCE_TYPES = (
    "bbox_area_jump",
    "bbox_clipping",
)


def summarize_locked_dropout_matrix(
    records: Iterable[Any],
    *,
    max_prediction_age_s: float = 0.25,
    expected_frame_counts: Iterable[int] = DEFAULT_DROPOUT_FRAME_COUNTS,
) -> dict[str, Any]:
    """Summarize locked detection-dropout rows without authorizing control.

    Frames one and two may only use the image KF for the same identity and
    plan.  Any row older than ``max_prediction_age_s`` must be expired with no
    command.  A higher-rate third-or-later frame may use bounded command coast
    only while it remains inside the same hard age limit.
    """

    if max_prediction_age_s <= 0.0:
        raise ValueError("max_prediction_age_s must be positive")
    rows = [_coerce_record(record) for record in records]
    expected = tuple(sorted({int(value) for value in expected_frame_counts}))
    if any(value < 1 for value in expected):
        raise ValueError("expected_frame_counts must contain positive integers")

    grouped: dict[int, list[dict[str, Any]]] = {value: [] for value in expected}
    for row in rows:
        frame_count = _int_value(row, "terminal_loss_frame_count", "dropout_frame_count")
        if frame_count is not None:
            grouped.setdefault(frame_count, []).append(row)

    matrix: dict[str, Any] = {}
    total_compliant = 0
    total_evaluated = 0
    for frame_count in sorted(grouped):
        frame_rows = grouped[frame_count]
        states = Counter(_text_value(row, "terminal_delivery_state", "state") for row in frame_rows)
        states.pop("", None)
        compliance = [_dropout_row_compliant(row, frame_count, max_prediction_age_s) for row in frame_rows]
        total_compliant += sum(compliance)
        total_evaluated += len(compliance)
        ages = [
            age
            for row in frame_rows
            if (age := _float_value(row, "terminal_prediction_age_s", "measurement_age_s"))
            is not None
        ]
        matrix[str(frame_count)] = {
            "record_count": len(frame_rows),
            "state_counts": dict(states),
            "max_prediction_age_s": max(ages) if ages else None,
            "identity_plan_consistent_count": sum(
                1 for row in frame_rows if _identity_plan_consistent(row)
            ),
            "command_available_count": sum(1 for row in frame_rows if _command_available(row)),
            "compliant_count": sum(compliance),
            "compliance_rate": sum(compliance) / len(compliance) if compliance else 0.0,
        }

    observed = {count for count, frame_rows in grouped.items() if frame_rows}
    rebound_evidence = [
        _bool_value(row, "global_track_id_rebound")
        for row in rows
        if "global_track_id_rebound" in row
    ]
    return {
        "boundary": D7_DELIVERY_CALIBRATION_BOUNDARY,
        "kind": "locked_dropout_matrix",
        "record_count": len(rows),
        "max_prediction_age_s": max_prediction_age_s,
        "expected_frame_counts": list(expected),
        "observed_frame_counts": sorted(observed),
        "matrix_complete": set(expected) <= observed,
        "matrix": matrix,
        "compliant_count": total_compliant,
        "evaluated_count": total_evaluated,
        "all_rows_compliant": total_evaluated > 0 and total_compliant == total_evaluated,
        "identity_plan_inconsistent_count": sum(
            1 for row in rows if not _identity_plan_consistent(row)
        ),
        "global_track_id_rebound_evidence_available": bool(rebound_evidence),
        "global_track_id_rebound_count": (
            sum(value is True for value in rebound_evidence)
            if rebound_evidence
            else None
        ),
        "advisory_only": True,
    }


def summarize_png_ttc_calibration(records: Iterable[Any]) -> dict[str, Any]:
    """Aggregate multi-seed ``png_ttc`` validity and rejection coverage."""

    rows = [_coerce_record(record) for record in records]
    seeds = {
        seed
        for row in rows
        if (seed := _text_value(row, "seed", "random_seed", "run_seed"))
    }
    reject_reasons: Counter[str] = Counter()
    reject_classes: Counter[str] = Counter()
    valid_count = 0
    for row in rows:
        if _bool_value(row, "ttc_valid") is True:
            valid_count += 1
        reason = _text_value(row, "ttc_reject_reason")
        if reason:
            reject_reasons[reason] += 1
            reject_classes[_ttc_reject_class(reason)] += 1

    required_coverage = {
        name: reject_classes[name] > 0 for name in PNG_TTC_REQUIRED_REJECT_CLASSES
    }
    ttc_values = [
        value for row in rows if (value := _float_value(row, "ttc_s")) is not None
    ]
    return {
        "boundary": D7_DELIVERY_CALIBRATION_BOUNDARY,
        "kind": "png_ttc_multiseed",
        "record_count": len(rows),
        "seed_count": len(seeds),
        "seeds": sorted(seeds),
        "ttc_valid_count": valid_count,
        "ttc_valid_rate": valid_count / len(rows) if rows else 0.0,
        "ttc_reject_reasons": dict(reject_reasons),
        "ttc_reject_class_counts": dict(reject_classes),
        "required_reject_coverage": required_coverage,
        "required_reject_coverage_complete": all(required_coverage.values()),
        "ttc_s_min": min(ttc_values) if ttc_values else None,
        "ttc_s_max": max(ttc_values) if ttc_values else None,
        "default_png_vm_changed": False,
        "advisory_only": True,
    }


def summarize_png_ttc_controlled_disturbances(
    records: Iterable[Any],
) -> dict[str, Any]:
    """Verify controlled TTC rejection without changing identity or control gates."""

    rows = [_coerce_record(record) for record in records]
    matrix: dict[str, Any] = {}
    for disturbance_type in PNG_TTC_CONTROLLED_DISTURBANCE_TYPES:
        disturbance_rows = [
            row
            for row in rows
            if _text_value(row, "disturbance_type") == disturbance_type
        ]
        reason_match_count = 0
        control_blocked_count = 0
        radar_fallback_count = 0
        identity_evidence_count = 0
        identity_preserved_count = 0
        row_pass_count = 0
        reasons: Counter[str] = Counter()
        for row in disturbance_rows:
            reason = _text_value(row, "ttc_reject_reason")
            if reason:
                reasons[reason] += 1
            reason_matches = (
                reason == "bbox_area_jump"
                if disturbance_type == "bbox_area_jump"
                else _ttc_reject_class(reason) == "bbox_clipping"
            )
            reason_match_count += int(reason_matches)

            control_allowed = _bool_value(
                row,
                "effective_control_authorized",
                "terminal_control_allowed",
                "terminal_switch_allowed",
            )
            control_blocked = control_allowed is False
            control_blocked_count += int(control_blocked)

            executed_law = _text_value(
                row,
                "executed_guidance_law",
                "guidance_law",
            )
            radar_fallback = executed_law in {"radar_pn", "pn"}
            radar_fallback_count += int(radar_fallback)

            expected_track_id = _text_value(
                row,
                "expected_global_track_id",
                "binding_global_track_id",
            )
            actual_track_id = _text_value(row, "assigned_global_track_id")
            identity_available = bool(expected_track_id and actual_track_id)
            identity_preserved = (
                identity_available and expected_track_id == actual_track_id
            )
            identity_evidence_count += int(identity_available)
            identity_preserved_count += int(identity_preserved)
            row_pass_count += int(
                reason_matches
                and control_blocked
                and radar_fallback
                and identity_preserved
            )

        count = len(disturbance_rows)
        matrix[disturbance_type] = {
            "record_count": count,
            "reject_reason_counts": dict(reasons),
            "reject_reason_match_count": reason_match_count,
            "effective_control_blocked_count": control_blocked_count,
            "radar_pn_fallback_count": radar_fallback_count,
            "identity_evidence_count": identity_evidence_count,
            "identity_preserved_count": identity_preserved_count,
            "compliant_count": row_pass_count,
            "coverage_pass": count > 0 and row_pass_count == count,
        }

    return {
        "boundary": D7_DELIVERY_CALIBRATION_BOUNDARY,
        "kind": "png_ttc_controlled_disturbance_coverage",
        "record_count": len(rows),
        "required_disturbance_types": list(PNG_TTC_CONTROLLED_DISTURBANCE_TYPES),
        "matrix": matrix,
        "coverage_complete": all(
            matrix[name]["coverage_pass"]
            for name in PNG_TTC_CONTROLLED_DISTURBANCE_TYPES
        ),
        "default_png_vm_changed": False,
        "png_ttc_formula_changed": False,
        "d3_d4_d5_gate_bypassed": False,
        "global_track_id_rebound_allowed": False,
        "advisory_only": True,
    }


def evaluate_trend_coast_promotion(
    baseline_records: Iterable[Any],
    candidate_records: Iterable[Any],
) -> dict[str, Any]:
    """Evaluate the fixed fail-closed promotion criteria for trend coast."""

    baseline = [_coerce_record(record) for record in baseline_records]
    candidate = [_coerce_record(record) for record in candidate_records]
    baseline_seeds = {_text_value(row, "seed", "random_seed", "run_seed") for row in baseline}
    candidate_seeds = {_text_value(row, "seed", "random_seed", "run_seed") for row in candidate}
    baseline_seeds.discard("")
    candidate_seeds.discard("")

    baseline_discontinuity = _metric_rate(
        baseline,
        count_names=("command_discontinuity_count",),
        bool_names=("command_discontinuity",),
    )
    candidate_discontinuity = _metric_rate(
        candidate,
        count_names=("command_discontinuity_count",),
        bool_names=("command_discontinuity",),
    )
    baseline_success = _metric_rate(
        baseline,
        count_names=("physical_success_count",),
        bool_names=("physical_success", "intercept_success"),
    )
    candidate_success = _metric_rate(
        candidate,
        count_names=("physical_success_count",),
        bool_names=("physical_success", "intercept_success"),
    )
    wrong_binding_count = sum(
        _int_value(row, "wrong_binding_count") or int(_bool_value(row, "wrong_binding") is True)
        for row in candidate
    )
    trigger_count = sum(
        _int_value(row, "terminal_trend_coast_applied_count")
        or int(_bool_value(row, "terminal_trend_coast_applied") is True)
        for row in candidate
    )

    criteria = {
        "paired_seed_set": bool(baseline_seeds) and baseline_seeds == candidate_seeds,
        "candidate_triggered": trigger_count > 0,
        "wrong_binding_zero": wrong_binding_count == 0,
        "command_discontinuity_not_worse": (
            baseline_discontinuity is not None
            and candidate_discontinuity is not None
            and candidate_discontinuity <= baseline_discontinuity + 1.0e-12
        ),
        "physical_success_not_lower": (
            baseline_success is not None
            and candidate_success is not None
            and candidate_success + 1.0e-12 >= baseline_success
        ),
    }
    return {
        "boundary": D7_DELIVERY_CALIBRATION_BOUNDARY,
        "kind": "trend_coast_promotion",
        "trend_coast_default_enabled": False,
        "baseline_seed_count": len(baseline_seeds),
        "candidate_seed_count": len(candidate_seeds),
        "candidate_trigger_count": trigger_count,
        "candidate_wrong_binding_count": wrong_binding_count,
        "baseline_command_discontinuity_rate": baseline_discontinuity,
        "candidate_command_discontinuity_rate": candidate_discontinuity,
        "baseline_physical_success_rate": baseline_success,
        "candidate_physical_success_rate": candidate_success,
        "criteria": criteria,
        "promotion_recommended": all(criteria.values()),
        "advisory_only": True,
    }


def _dropout_row_compliant(
    row: Mapping[str, Any],
    frame_count: int,
    max_prediction_age_s: float,
) -> bool:
    state = _text_value(row, "terminal_delivery_state", "state")
    age = _float_value(row, "terminal_prediction_age_s", "measurement_age_s")
    if age is None or not _identity_plan_consistent(row):
        return False
    if age > max_prediction_age_s + 1.0e-9:
        return state == "expired" and not _command_available(row)
    if frame_count <= 2:
        return (
            state == "image_kf_predict"
            and _bool_value(row, "terminal_using_extrapolation", "using_extrapolation") is True
            and _command_available(row)
        )
    return state in {"blind_push", "expired"}


def _identity_plan_consistent(row: Mapping[str, Any]) -> bool:
    explicit = _bool_value(row, "identity_plan_consistent", "same_identity_plan")
    if explicit is not None:
        return explicit
    if _bool_value(row, "terminal_lifecycle_reset", "lifecycle_reset") is True:
        return False
    if _bool_value(row, "d3_plan_version_consistent") is False:
        return False
    if _bool_value(row, "d5_lock_consistent") is False:
        return False
    assigned = _text_value(row, "assigned_global_track_id", "target_id")
    d5_assigned = _text_value(row, "d5_assigned_global_track_id")
    return not (assigned and d5_assigned and assigned != d5_assigned)


def _command_available(row: Mapping[str, Any]) -> bool:
    explicit = _bool_value(row, "command_available")
    if explicit is not None:
        return explicit
    return row.get("selected_velocity_ned") is not None or row.get("command") is not None


def _ttc_reject_class(reason: str) -> str:
    if reason.startswith("bbox_") and reason.endswith("_clipped"):
        return "bbox_clipping"
    return reason


def _metric_rate(
    rows: list[dict[str, Any]],
    *,
    count_names: tuple[str, ...],
    bool_names: tuple[str, ...],
) -> float | None:
    if not rows:
        return None
    counts = [_int_value(row, *count_names) for row in rows]
    if any(value is not None for value in counts):
        return sum(value or 0 for value in counts) / len(rows)
    values = [_bool_value(row, *bool_names) for row in rows]
    available = [value for value in values if value is not None]
    if not available:
        return None
    return sum(value is True for value in available) / len(available)


def _coerce_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "as_log_record"):
        row = dict(record.as_log_record())
    elif hasattr(record, "as_dict"):
        row = dict(record.as_dict())
    elif isinstance(record, Mapping):
        row = dict(record)
    else:
        row = dict(vars(record))
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        for key, value in metadata.items():
            row.setdefault(str(key), value)
    return row


def _text_value(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        if hasattr(value, "value"):
            value = value.value
        text = str(value).strip()
        if text:
            return text
    return ""


def _int_value(row: Mapping[str, Any], *names: str) -> int | None:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _float_value(row: Mapping[str, Any], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _bool_value(row: Mapping[str, Any], *names: str) -> bool | None:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "passed", "success"}:
            return True
        if text in {"0", "false", "no", "failed", "failure"}:
            return False
    return None
