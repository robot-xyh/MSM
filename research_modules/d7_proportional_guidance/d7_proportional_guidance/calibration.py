"""Passive multi-seed guidance calibration summaries for D7 outputs.

This module consumes D7 records that have already been produced by runtime,
offline comparison, or replay paths.  It does not rerun guidance, change
``PngGuidanceConfig`` defaults, call AirSim, or authorize terminal handoff.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import ceil, floor
from typing import Any

from .models import GuidanceConfig
from .vision_png import PngGuidanceConfig


D7_GUIDANCE_CALIBRATION_BOUNDARY = "d7_p1_guidance_calibration_summary_advisory_only"
DEFAULT_CALIBRATION_THRESHOLD_VERSION = "d7-p1-guidance-calibration-advisory-v1"
DEFAULT_CALIBRATION_GUIDANCE_LAWS: tuple[str, ...] = (
    "pn",
    "pure_pursuit",
    "png_vm",
    "png_ttc",
)


@dataclass(frozen=True)
class GuidanceCalibrationThresholds:
    """Versioned advisory threshold values for report-only calibration."""

    version: str = DEFAULT_CALIBRATION_THRESHOLD_VERSION
    terminal_range_m: float | None = None
    min_bbox_area_ratio: float | None = None
    max_visual_latency_s: float | None = None
    min_closing_speed_mps: float | None = None
    min_maneuver_margin: float | None = None
    advisory_only: bool = True
    default_control_law_changed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_guidance_calibration(
    records: Iterable[Any],
    *,
    threshold_version: str = DEFAULT_CALIBRATION_THRESHOLD_VERSION,
    current_thresholds: GuidanceCalibrationThresholds | PngGuidanceConfig | GuidanceConfig | Mapping[str, Any] | None = None,
    expected_guidance_laws: Iterable[str] = DEFAULT_CALIBRATION_GUIDANCE_LAWS,
) -> dict[str, Any]:
    """Summarize multi-seed D7 runtime/comparison/replay records.

    The returned threshold fields are advisory metadata for D6/main reports.
    They intentionally do not mutate default PN/PNG APIs or bypass D3/D4/D5
    terminal gates.
    """

    rows = [_coerce_record(record) for record in records]
    expected_laws = tuple(str(law) for law in expected_guidance_laws)
    law_order = list(dict.fromkeys((*expected_laws, *(_guidance_law(row) for row in rows))))
    grouped = {law: [] for law in law_order}
    for row in rows:
        grouped.setdefault(_guidance_law(row), []).append(row)

    guidance_law_summaries = {
        law: _summarize_law_rows(law_rows)
        for law, law_rows in grouped.items()
    }
    thresholds = _coerce_thresholds(
        current_thresholds,
        version=threshold_version,
    )
    return {
        "boundary": D7_GUIDANCE_CALIBRATION_BOUNDARY,
        "record_count": len(rows),
        "guidance_law_order": law_order,
        "guidance_law_summaries": guidance_law_summaries,
        "threshold_advisory": _build_threshold_advisory(rows, thresholds),
        "benchmark_calibration": _summarize_benchmark_fields(rows),
        "advisory_only": True,
        "default_control_law_changed": False,
        "d3_d4_d5_gate_bypassed": False,
    }


def _summarize_law_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    seeds = {
        seed
        for row in rows
        if (seed := _string_value(row, ("seed", "random_seed", "run_seed"))) is not None
    }
    contract_rejects: Counter[str] = Counter()
    switch_rejects: Counter[str] = Counter()
    all_rejects: Counter[str] = Counter()
    guidance_modes: Counter[str] = Counter()
    handoff_states: Counter[str] = Counter()

    terminal_switch_allowed_samples = 0.0
    terminal_switch_sample_count = 0
    contract_allowed_samples = 0.0
    contract_sample_count = 0
    visual_png_switch_count = 0

    for row in rows:
        if mode := _string_value(row, ("mode", "guidance_mode")):
            guidance_modes[mode] += 1
        if state := _string_value(row, ("terminal_handoff_state", "handoff_state")):
            handoff_states[state] += 1

        contract_rejects.update(_reason_counter(row, "terminal_contract_reject"))
        switch_rejects.update(_reason_counter(row, "terminal_switch_reject"))
        all_rejects.update(_reason_counter(row, "terminal_contract_reject"))
        all_rejects.update(_reason_counter(row, "terminal_switch_reject"))
        all_rejects.update(_reason_counter(row, "reject"))

        sample_count = _sample_count(row)
        if (rate := _numeric_value(row, ("terminal_switch_allowed_rate",))) is not None:
            terminal_switch_allowed_samples += rate * sample_count
            terminal_switch_sample_count += sample_count
        elif (allowed := _bool_value(row, ("terminal_switch_allowed", "visual_png_enabled"))) is not None:
            terminal_switch_allowed_samples += 1.0 if allowed else 0.0
            terminal_switch_sample_count += 1

        if (count := _numeric_value(row, ("terminal_contract_allowed_count",))) is not None:
            contract_allowed_samples += count
            contract_sample_count += sample_count
        elif (allowed := _bool_value(row, ("terminal_contract_allowed",))) is not None:
            contract_allowed_samples += 1.0 if allowed else 0.0
            contract_sample_count += 1

        if (count := _numeric_value(row, ("visual_png_switch_count",))) is not None:
            visual_png_switch_count += int(count)
        elif _bool_value(row, ("visual_png_enabled",)) is True:
            visual_png_switch_count += 1

    return {
        "record_count": len(rows),
        "sample_count": sum(_sample_count(row) for row in rows),
        "seed_count": len(seeds),
        "seeds": sorted(seeds),
        "visual_png_switch_count": visual_png_switch_count,
        "terminal_switch_allowed_rate": (
            terminal_switch_allowed_samples / terminal_switch_sample_count
            if terminal_switch_sample_count
            else 0.0
        ),
        "terminal_contract_allowed_rate": (
            contract_allowed_samples / contract_sample_count
            if contract_sample_count
            else 0.0
        ),
        "terminal_range_m": _numeric_summary(
            _numeric_values(rows, ("terminal_range_m", "terminal_switch_range_m", "range_m", "min_range_m"))
        ),
        "closing_speed_mps": _numeric_summary(_numeric_values(rows, ("closing_speed_mps",))),
        "bbox_gate": {
            "pass_rate": _bool_rate(rows, ("camera_quality_gate_passed", "bbox_gate_passed")),
            "bbox_area_ratio": _numeric_summary(_numeric_values(rows, ("bbox_area_ratio",))),
            "visual_latency_s": _numeric_summary(_numeric_values(rows, ("visual_latency_s",))),
        },
        "los_gate": {
            "pass_rate": _bool_rate(rows, ("los_quality_gate_passed", "los_gate_passed")),
            "los_rate_abs_radps": _numeric_summary(
                abs(value) for value in _numeric_values(rows, ("los_rate_radps",))
            ),
            "los_rate_variance_radps2": _numeric_summary(
                _numeric_values(rows, ("los_rate_variance_radps2",))
            ),
        },
        "maneuver_gate": {
            "pass_rate": _bool_rate(rows, ("maneuver_margin_gate_passed",)),
            "maneuver_margin": _numeric_summary(_numeric_values(rows, ("maneuver_margin",))),
        },
        "terminal_contract_reject_reasons": dict(contract_rejects),
        "terminal_switch_reject_reasons": dict(switch_rejects),
        "reject_reasons": dict(all_rejects),
        "guidance_mode_counts": dict(guidance_modes),
        "terminal_handoff_state_counts": dict(handoff_states),
    }


def _build_threshold_advisory(
    rows: list[dict[str, Any]],
    thresholds: GuidanceCalibrationThresholds,
) -> dict[str, Any]:
    successful_rows = [
        row
        for row in rows
        if _bool_value(row, ("visual_png_enabled", "terminal_switch_allowed", "terminal_mode_entered")) is True
    ]
    basis_rows = successful_rows or rows

    terminal_ranges = _numeric_values(
        basis_rows,
        ("terminal_range_m", "terminal_switch_range_m", "range_m", "min_range_m"),
    )
    bbox_areas = _numeric_values(basis_rows, ("bbox_area_ratio",))
    visual_latencies = _numeric_values(basis_rows, ("visual_latency_s",))
    closing_speeds = _numeric_values(basis_rows, ("closing_speed_mps",))
    maneuver_margins = _numeric_values(basis_rows, ("maneuver_margin",))

    return {
        "version": thresholds.version,
        "advisory_only": True,
        "default_control_law_changed": False,
        "d3_d4_d5_gate_bypassed": False,
        "thresholds": {
            "terminal_range_m": _advisory_field(
                current=thresholds.terminal_range_m,
                suggested=_percentile_or_current(terminal_ranges, 0.50, thresholds.terminal_range_m),
                observed_values=terminal_ranges,
                basis="p50_success_or_all_terminal_range_m",
            ),
            "min_bbox_area_ratio": _advisory_field(
                current=thresholds.min_bbox_area_ratio,
                suggested=_max_current_or_percentile(bbox_areas, 0.10, thresholds.min_bbox_area_ratio),
                observed_values=bbox_areas,
                basis="max_current_or_p10_success_bbox_area_ratio",
            ),
            "max_visual_latency_s": _advisory_field(
                current=thresholds.max_visual_latency_s,
                suggested=_min_current_or_percentile(visual_latencies, 0.90, thresholds.max_visual_latency_s),
                observed_values=visual_latencies,
                basis="min_current_or_p90_success_visual_latency_s",
            ),
            "min_closing_speed_mps": _advisory_field(
                current=thresholds.min_closing_speed_mps,
                suggested=_max_current_or_percentile(closing_speeds, 0.10, thresholds.min_closing_speed_mps),
                observed_values=closing_speeds,
                basis="max_current_or_p10_success_closing_speed_mps",
            ),
            "min_maneuver_margin": _advisory_field(
                current=thresholds.min_maneuver_margin,
                suggested=_max_current_or_percentile(maneuver_margins, 0.10, thresholds.min_maneuver_margin),
                observed_values=maneuver_margins,
                basis="max_current_or_p10_success_maneuver_margin",
            ),
        },
    }


def _summarize_benchmark_fields(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frpn_laws: Counter[str] = Counter()
    for row in rows:
        if law := _string_value(row, ("frpn_guidance_law", "frpn_variant", "benchmark_guidance_law")):
            frpn_laws[law] += 1
    return {
        "benchmark_only": True,
        "default_pn_png_api_replaced": False,
        "three_dimensional_guidance_replaces_default": False,
        "frpn_replaces_default": False,
        "height_delta_m": _numeric_summary(
            _numeric_values(rows, ("height_delta_m", "altitude_delta_m", "vertical_separation_m"))
        ),
        "range_3d_m": _numeric_summary(_numeric_values(rows, ("range_3d_m", "range_3d_estimate_m"))),
        "frpn_benchmark_score": _numeric_summary(
            _numeric_values(rows, ("frpn_benchmark_score", "frpn_score"))
        ),
        "frpn_guidance_law_counts": dict(frpn_laws),
    }


def _coerce_thresholds(
    value: GuidanceCalibrationThresholds | PngGuidanceConfig | GuidanceConfig | Mapping[str, Any] | None,
    *,
    version: str,
) -> GuidanceCalibrationThresholds:
    guidance_defaults = GuidanceConfig()
    png_defaults = PngGuidanceConfig()
    merged: dict[str, Any] = {
        "version": version,
        "terminal_range_m": guidance_defaults.terminal_switch_range_m,
        "min_bbox_area_ratio": png_defaults.min_bbox_area_ratio,
        "max_visual_latency_s": png_defaults.max_visual_latency_s,
        "min_closing_speed_mps": png_defaults.min_closing_speed_mps,
        "min_maneuver_margin": png_defaults.min_maneuver_margin,
    }
    if value is None:
        return GuidanceCalibrationThresholds(**merged)
    if isinstance(value, GuidanceCalibrationThresholds):
        data = value.as_dict()
    elif isinstance(value, PngGuidanceConfig):
        data = {
            "min_bbox_area_ratio": value.min_bbox_area_ratio,
            "max_visual_latency_s": value.max_visual_latency_s,
            "min_closing_speed_mps": value.min_closing_speed_mps,
            "min_maneuver_margin": value.min_maneuver_margin,
        }
    elif isinstance(value, GuidanceConfig):
        data = {"terminal_range_m": value.terminal_switch_range_m}
    elif isinstance(value, Mapping):
        data = dict(value)
    else:
        data = {
            name: getattr(value, name)
            for name in (
                "version",
                "terminal_range_m",
                "min_bbox_area_ratio",
                "max_visual_latency_s",
                "min_closing_speed_mps",
                "min_maneuver_margin",
            )
            if hasattr(value, name)
        }
    merged.update({key: data[key] for key in merged if key in data and data[key] is not None})
    if "version" in data and data["version"]:
        merged["version"] = str(data["version"])
    return GuidanceCalibrationThresholds(**merged)


def _coerce_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "as_log_record"):
        data = dict(record.as_log_record())
    elif hasattr(record, "as_dict"):
        data = dict(record.as_dict())
    elif isinstance(record, Mapping):
        data = dict(record)
    else:
        known_fields = (
            "seed",
            "strategy",
            "guidance_law",
            "mode",
            "sample_count",
            "min_range_m",
            "range_m",
            "terminal_range_m",
            "closing_speed_mps",
            "terminal_switch_allowed",
            "terminal_contract_allowed",
            "terminal_switch_reject_reason",
            "terminal_contract_reject_reason",
            "visual_png_enabled",
            "visual_png_switch_count",
            "camera_quality_gate_passed",
            "los_quality_gate_passed",
            "maneuver_margin_gate_passed",
            "bbox_area_ratio",
            "visual_latency_s",
            "maneuver_margin",
            "height_delta_m",
            "range_3d_m",
            "frpn_benchmark_score",
        )
        data = {
            name: getattr(record, name)
            for name in known_fields
            if hasattr(record, name)
        }
        metadata = getattr(record, "metadata", None)
        if isinstance(metadata, Mapping):
            data["metadata"] = dict(metadata)
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        for key, value in metadata.items():
            data.setdefault(str(key), value)
    return data


def _guidance_law(row: Mapping[str, Any]) -> str:
    strategy = _string_value(row, ("strategy",))
    if strategy:
        return _normalize_guidance_law(strategy)
    candidate = _string_value(row, ("png_guidance_law_candidate",))
    law = _string_value(row, ("guidance_law", "law"))
    if candidate and law in {None, "", "radar_pn", "pn"}:
        return _normalize_guidance_law(candidate)
    return _normalize_guidance_law(law or "pn")


def _normalize_guidance_law(value: str) -> str:
    text = str(value).strip()
    if text == "radar_pn":
        return "pn"
    return text or "pn"


def _reason_counter(row: Mapping[str, Any], prefix: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    plural_names = (
        f"{prefix}_reasons",
        f"{prefix}_reason_counts",
    )
    singular_names = (
        f"{prefix}_reason",
        "reject_reason" if prefix == "reject" else "",
    )
    for name in plural_names:
        value = _lookup(row, name)
        if isinstance(value, Mapping):
            for reason, count in value.items():
                if reason:
                    counter[str(reason)] += int(count)
    for name in singular_names:
        if not name:
            continue
        reason = _string_value(row, (name,))
        if reason:
            counter[reason] += 1
    return counter


def _sample_count(row: Mapping[str, Any]) -> int:
    count = _numeric_value(row, ("sample_count", "steps", "observation_count"))
    if count is None:
        return 1
    return max(1, int(count))


def _bool_rate(rows: list[dict[str, Any]], names: tuple[str, ...]) -> float:
    values = [_bool_value(row, names) for row in rows]
    values = [value for value in values if value is not None]
    return sum(1 for value in values if value) / len(values) if values else 0.0


def _numeric_values(rows: Iterable[Mapping[str, Any]], names: tuple[str, ...]) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = _numeric_value(row, names)
        if value is not None:
            values.append(value)
    return values


def _numeric_value(row: Mapping[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        value = _lookup(row, name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _bool_value(row: Mapping[str, Any], names: tuple[str, ...]) -> bool | None:
    for name in names:
        value = _lookup(row, name)
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "t", "yes", "y", "1", "pass", "passed", "ok", "allowed"}:
            return True
        if text in {"false", "f", "no", "n", "0", "fail", "failed", "reject", "rejected"}:
            return False
    return None


def _string_value(row: Mapping[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = _lookup(row, name)
        if value is None:
            continue
        if hasattr(value, "value"):
            value = value.value
        text = str(value).strip()
        if text:
            return text
    return None


def _lookup(row: Mapping[str, Any], name: str) -> Any:
    if name in row:
        return row[name]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping) and name in metadata:
        return metadata[name]
    return None


def _numeric_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    items = [float(value) for value in values]
    if not items:
        return {
            "observed_count": 0,
            "min": None,
            "p10": None,
            "mean": None,
            "p50": None,
            "p90": None,
            "max": None,
        }
    return {
        "observed_count": len(items),
        "min": min(items),
        "p10": _percentile(items, 0.10),
        "mean": sum(items) / len(items),
        "p50": _percentile(items, 0.50),
        "p90": _percentile(items, 0.90),
        "max": max(items),
    }


def _advisory_field(
    *,
    current: float | None,
    suggested: float | None,
    observed_values: list[float],
    basis: str,
) -> dict[str, Any]:
    return {
        "current": current,
        "suggested": suggested,
        "basis": basis,
        "advisory_only": True,
        "observed": _numeric_summary(observed_values),
    }


def _percentile_or_current(values: list[float], q: float, current: float | None) -> float | None:
    if not values:
        return current
    return _percentile(values, q)


def _max_current_or_percentile(values: list[float], q: float, current: float | None) -> float | None:
    candidate = _percentile_or_current(values, q, current)
    if current is None:
        return candidate
    if candidate is None:
        return current
    return max(float(current), float(candidate))


def _min_current_or_percentile(values: list[float], q: float, current: float | None) -> float | None:
    candidate = _percentile_or_current(values, q, current)
    if current is None:
        return candidate
    if candidate is None:
        return current
    return min(float(current), float(candidate))


def _percentile(values: Iterable[float], q: float) -> float:
    items = sorted(float(value) for value in values)
    if not items:
        raise ValueError("percentile requires at least one value")
    if len(items) == 1:
        return items[0]
    position = (len(items) - 1) * min(1.0, max(0.0, q))
    lower = int(floor(position))
    upper = int(ceil(position))
    if lower == upper:
        return items[lower]
    weight = position - lower
    return items[lower] * (1.0 - weight) + items[upper] * weight
