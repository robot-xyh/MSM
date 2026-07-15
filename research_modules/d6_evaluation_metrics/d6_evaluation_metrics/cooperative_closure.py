"""Offline reporting for the P1 cooperative-closure-v2 evidence bundle.

The evaluator consumes persisted summaries only.  It does not import runtime
controllers, create assignments, or feed an acceptance decision back to main.
Missing evidence remains unavailable instead of being converted to zero.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass, is_dataclass
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence


COOPERATIVE_CLOSURE_SCHEMA_VERSION = "d6-cooperative-closure-v3"

STAGES = (
    "assigned",
    "visible",
    "associated",
    "contract_allowed",
    "control_allowed",
    "mode_switched",
    "physical_intercept",
)

_STAGE_ALIASES = {
    "assigned": ("assigned", "assignment_active"),
    "visible": ("visible", "target_visible"),
    "associated": ("associated", "terminal_associated"),
    "contract_allowed": ("contract_allowed", "terminal_contract_allowed"),
    "control_allowed": ("control_allowed", "terminal_control_allowed"),
    "mode_switched": ("mode_switched", "visual_mode_switched"),
    "physical_intercept": (
        "physical_intercept",
        "intercept_success",
        "within_success_range",
    ),
}

_INPUT_FIELDS = (
    "case",
    "seed",
    "profile",
    "resource_id",
    "target_id",
    "member_role",
    "member_order",
    "plan_owner",
    "plan_version",
    "coalition_id",
    "coalition_owner",
    "coalition_version",
    "coalition_epoch",
    "closest_range_m",
    "arrival_error_s",
    "member_separation_m",
    "first_failure_reason",
    "common_lock",
    "common_lock_window_s",
    "reserve_activated",
    "reserve_unauthorized",
    "global_track_id_rewrite_count",
    "online_truth_use_count",
    "communication_fault",
    "communication_passed",
    "fail_closed",
    *STAGES,
)

_PER_SEED_FIELDS = (
    "case",
    "seed",
    "profile",
    "resource_count",
    "target_count",
    "coalition_count",
    "plan_owners",
    "plan_versions",
    "coalition_ids",
    "coalition_owners",
    "coalition_versions",
    "coalition_epochs",
    *(
        f"{level}_{stage}_{suffix}"
        for level in ("pair", "target", "coalition")
        for stage in STAGES
        for suffix in ("passed", "available", "unavailable", "rate")
    ),
    *(
        f"second_primary_{stage}_{suffix}"
        for stage in STAGES
        for suffix in ("passed", "available", "unavailable", "rate")
    ),
    *(
        f"{level}_first_failure_reason_{suffix}"
        for level in ("pair", "target", "coalition")
        for suffix in (
            "availability",
            "availability_reason",
            "failed_unit_count",
            "available_unit_count",
            "unavailable_unit_count",
            "distribution",
        )
    ),
    "second_primary_member_count",
    "second_primary_opportunity_count",
    "second_primary_success_count",
    "second_primary_failure_count",
    "second_primary_availability",
    "second_primary_availability_reason",
    "second_primary_first_failure_reason_availability",
    "second_primary_first_failure_reason_availability_reason",
    "second_primary_first_failure_reason_available_count",
    "second_primary_first_failure_reason_unavailable_count",
    "second_primary_failure_distribution",
    "common_lock_passed",
    "common_lock_available",
    "common_lock_unavailable",
    "common_lock_rate",
    "arrival_group_count",
    "arrival_dispersion_mean_s",
    "arrival_dispersion_max_s",
    "closest_range_min_m",
    "closest_range_mean_m",
    "minimum_member_separation_m",
    "first_failure_distribution",
    "reserve_unauthorized_count",
    "reserve_unauthorized_availability",
    "global_track_id_rewrite_count",
    "global_track_id_rewrite_availability",
    "online_truth_use_count",
    "online_truth_use_availability",
)


@dataclass(frozen=True)
class CooperativeClosureInputs:
    """Persisted main rows plus optional D3-D7 evidence summaries."""

    rows: Any
    d3_candidate: Any | None = None
    d4_communication: Any | None = None
    d5_visibility: Any | None = None
    d7_guidance: Any | None = None


class CooperativeClosureReportGenerator:
    """Generate CSV/JSON/Chinese Markdown/PNG without controlling the system."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: CooperativeClosureInputs,
        title: str = "P1 cooperative-closure-v2 离线验收报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        primary_source = _primary_source_metadata(inputs.rows)
        rows = [_normalize_row(item) for item in load_cooperative_rows(inputs.rows)]
        optional, manifest = _load_optional_sources(inputs)
        for source_name in ("d3_candidate", "d5_visibility", "d7_guidance"):
            matched = _overlay_optional_rows(
                rows, optional.get(source_name), source_name
            )
            manifest[source_name]["matched_row_count"] = matched

        seed_rows = _build_seed_rows(rows)
        communication = _communication_summary(optional.get("d4_communication"))
        aggregate = _build_aggregate(
            rows,
            seed_rows,
            manifest,
            communication,
            primary_source=primary_source,
        )

        csv_path = output_dir / "cooperative_closure_per_seed.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=_PER_SEED_FIELDS)
            writer.writeheader()
            writer.writerows(seed_rows)

        json_path = output_dir / "cooperative_closure_aggregate.json"
        json_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        plot_path = output_dir / "cooperative_closure_overview.png"
        _write_plot(seed_rows, aggregate, plot_path)

        markdown_path = output_dir / "P1_COOPERATIVE_CLOSURE_REPORT.md"
        markdown_path.write_text(
            _render_markdown(aggregate, title=title, plot_name=plot_path.name),
            encoding="utf-8",
        )
        return {
            "per_seed_csv": csv_path,
            "aggregate_json": json_path,
            "markdown": markdown_path,
            "plot": plot_path,
        }


def load_cooperative_rows(source: Any) -> list[dict[str, Any]]:
    """Load generic line records from JSON, JSONL, CSV, mappings or objects."""

    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as stream:
                return [_coerce_mapping(row) for row in csv.DictReader(stream)]
        if suffix in {".jsonl", ".ndjson"}:
            records = []
            for line_number, text in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not text.strip():
                    continue
                item = json.loads(text)
                if not isinstance(item, Mapping):
                    raise ValueError(f"line {line_number} is not a JSON object")
                records.append(dict(item))
            return records
        source = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(source, Mapping):
        for key in ("pair_rows", "rows", "records", "line_records"):
            if key in source:
                source = source[key]
                break
        else:
            source = [source]

    if not isinstance(source, Sequence) or isinstance(source, (str, bytes)):
        raise TypeError("cooperative closure rows must be a sequence or persisted file")

    records: list[dict[str, Any]] = []
    for item in source:
        if isinstance(item, Mapping):
            records.append(_json_ready(dict(item)))
        elif is_dataclass(item):
            records.append(_json_ready(asdict(item)))
        elif hasattr(item, "to_dict"):
            records.append(_json_ready(dict(item.to_dict())))
        elif hasattr(item, "as_dict"):
            records.append(_json_ready(dict(item.as_dict())))
        else:
            raise TypeError(f"unsupported cooperative closure row: {type(item)!r}")
    return records


def _primary_source_metadata(source: Any) -> dict[str, Any]:
    """Read only batch-level selection metadata from the primary evidence."""

    payload: Any = source
    evidence_path: str | None = None
    if isinstance(source, (str, Path)):
        path = Path(source)
        evidence_path = str(path)
        if path.suffix.lower() not in {".json"}:
            return {"evidence_path": evidence_path}
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif is_dataclass(source):
        payload = asdict(source)
    elif hasattr(source, "to_dict"):
        payload = source.to_dict()
    elif hasattr(source, "as_dict"):
        payload = source.as_dict()
    if not isinstance(payload, Mapping):
        return {"evidence_path": evidence_path}
    return {
        "evidence_path": evidence_path,
        "calibration_suite": payload.get("calibration_suite"),
        "calibration_suite_version": payload.get("calibration_suite_version"),
        "scenario_version": payload.get("scenario_version"),
        "threshold_version": payload.get("threshold_version"),
        "case_count": payload.get("case_count"),
        "best_candidate_profile": payload.get("best_candidate_profile"),
        "acceptance": _json_ready(payload.get("acceptance", {})),
        "aggregates": _json_ready(payload.get("aggregates", [])),
    }


def _normalize_row(item: Mapping[str, Any]) -> dict[str, Any]:
    row = {name: None for name in _INPUT_FIELDS}
    row["case"] = _first(item, "case", "case_id", "scenario_id", "scenario")
    row["seed"] = _number_or_text(_first(item, "seed", "seed_id"))
    row["profile"] = _first(item, "profile", "comparison_role")
    row["resource_id"] = _first(item, "resource_id", "member_id", "vehicle_name")
    row["target_id"] = _first(item, "target_id", "global_track_id")
    row["member_role"] = _first(item, "member_role", "role")
    row["member_order"] = _integer_or_none(
        _first(item, "member_order", "primary_index", "member_index")
    )
    for name in (
        "plan_owner",
        "plan_version",
        "coalition_id",
        "coalition_owner",
        "coalition_version",
        "coalition_epoch",
        "first_failure_reason",
        "communication_fault",
    ):
        row[name] = item.get(name)
    for name in (
        "closest_range_m",
        "arrival_error_s",
        "member_separation_m",
        "common_lock_window_s",
    ):
        row[name] = _float_or_none(item.get(name))
    for name in (
        "common_lock",
        "reserve_activated",
        "reserve_unauthorized",
        "communication_passed",
        "fail_closed",
    ):
        row[name] = _bool_or_none(item.get(name))
    row["global_track_id_rewrite_count"] = _integer_or_none(
        _first(item, "global_track_id_rewrite_count", "id_rewrite_count")
    )
    row["online_truth_use_count"] = _integer_or_none(
        _first(item, "online_truth_use_count", "online_truth_leak_count")
    )
    for stage, aliases in _STAGE_ALIASES.items():
        row[stage] = _bool_or_none(_first(item, *aliases))
    return row


def _load_optional_sources(
    inputs: CooperativeClosureInputs,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payloads: dict[str, Any] = {}
    manifest: dict[str, dict[str, Any]] = {}
    for name in ("d3_candidate", "d4_communication", "d5_visibility", "d7_guidance"):
        value = getattr(inputs, name)
        if value is None:
            manifest[name] = {
                "status": "unavailable",
                "reason": "optional evidence was not provided",
                "evidence_path": None,
            }
            continue
        payloads[name] = _load_payload(value)
        compatible_rows = (
            _d4_rows_from_payload(payloads[name])
            if name == "d4_communication"
            else _rows_from_payload(payloads[name])
        )
        manifest[name] = {
            "status": "available" if compatible_rows else "unavailable",
            "reason": None if compatible_rows else "loaded summary has no compatible row records",
            "evidence_path": str(value) if isinstance(value, (str, Path)) else None,
            "compatible_row_count": len(compatible_rows),
        }
    return payloads, manifest


def _load_payload(source: Any) -> Any:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if path.suffix.lower() in {".jsonl", ".ndjson", ".csv"}:
            return {"rows": load_cooperative_rows(path)}
        return json.loads(path.read_text(encoding="utf-8"))
    if isinstance(source, Mapping):
        return _json_ready(dict(source))
    if is_dataclass(source):
        return _json_ready(asdict(source))
    if hasattr(source, "to_dict"):
        return _json_ready(source.to_dict())
    if hasattr(source, "as_dict"):
        return _json_ready(source.as_dict())
    if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
        return {"rows": load_cooperative_rows(source)}
    raise TypeError(f"unsupported optional evidence: {type(source)!r}")


def _overlay_optional_rows(
    rows: list[dict[str, Any]], payload: Any, source_name: str
) -> int:
    if payload is None:
        return 0
    evidence_rows = _rows_from_payload(payload)
    allowed = {
        "d3_candidate": {
            "plan_owner",
            "plan_version",
            "coalition_owner",
            "coalition_version",
            "coalition_epoch",
            "member_role",
            "member_order",
            "assigned",
        },
        "d5_visibility": {
            "visible",
            "associated",
            "common_lock",
            "common_lock_window_s",
            "global_track_id_rewrite_count",
            "online_truth_use_count",
            "first_failure_reason",
        },
        "d7_guidance": {
            "contract_allowed",
            "control_allowed",
            "mode_switched",
            "physical_intercept",
            "closest_range_m",
            "arrival_error_s",
            "member_separation_m",
            "reserve_activated",
            "reserve_unauthorized",
            "first_failure_reason",
        },
    }[source_name]
    matched = 0
    for raw in evidence_rows:
        evidence = _normalize_row(raw)
        candidates = [row for row in rows if _evidence_matches(row, evidence)]
        if not candidates:
            continue
        for row in candidates:
            row_matched = False
            for field in allowed:
                if row.get(field) is None and evidence.get(field) is not None:
                    row[field] = evidence[field]
                    row_matched = True
            matched += int(row_matched)
    return matched


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping):
        for key in (
            "pair_rows",
            "rows",
            "records",
            "seeds",
            "cases",
            "line_records",
        ):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return load_cooperative_rows(value)
        return []
    return load_cooperative_rows(payload)


def _d4_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    """Prefer D4 case records over its top-level integer seed inventory."""

    if isinstance(payload, Mapping):
        cases = payload.get("cases")
        if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes)):
            return load_cooperative_rows(cases)
    return _rows_from_payload(payload)


def _evidence_matches(
    row: Mapping[str, Any], evidence: Mapping[str, Any]
) -> bool:
    names = ("case", "seed", "profile", "resource_id", "target_id")
    specified = [name for name in names if evidence.get(name) is not None]
    if not specified or not {"resource_id", "target_id"}.intersection(specified):
        return False
    return all(str(row.get(name)) == str(evidence.get(name)) for name in specified)


def _build_seed_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("case"), row.get("seed"), row.get("profile"))].append(row)

    results = []
    for (case, seed, profile), items in sorted(grouped.items(), key=_sortable_group):
        members = _consolidate_pairs(items)
        primary_members = [item for item in members if not _is_reserve(item)]
        target_units = _higher_level_units(primary_members, level="target")
        coalition_units = [
            unit
            for unit in _higher_level_units(primary_members, level="coalition")
            if len(unit) >= 2
        ]
        row: dict[str, Any] = {
            "case": case,
            "seed": seed,
            "profile": profile,
            "resource_count": len(
                {item.get("resource_id") for item in members if item.get("resource_id") is not None}
            ),
            "target_count": len(
                {item.get("target_id") for item in members if item.get("target_id") is not None}
            ),
            "coalition_count": len(coalition_units),
            "plan_owners": _json_distinct(members, "plan_owner"),
            "plan_versions": _json_distinct(members, "plan_version"),
            "coalition_ids": _json_distinct(members, "coalition_id"),
            "coalition_owners": _json_distinct(members, "coalition_owner"),
            "coalition_versions": _json_distinct(members, "coalition_version"),
            "coalition_epochs": _json_distinct(members, "coalition_epoch"),
        }
        level_units = {
            "pair": [[item] for item in primary_members],
            "target": target_units,
            "coalition": coalition_units,
        }
        for level, units in level_units.items():
            for stage in STAGES:
                summary = _stage_summary(units, stage)
                for suffix, value in summary.items():
                    row[f"{level}_{stage}_{suffix}"] = value
            failure_reason = _failure_reason_summary(units)
            for suffix, value in failure_reason.items():
                field = f"{level}_first_failure_reason_{suffix}"
                row[field] = (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if suffix == "distribution"
                    else value
                )

        second = _second_primary_summary(primary_members)
        row.update(second)
        common = _common_lock_summary(target_units)
        row.update(common)
        arrivals = _arrival_summary(coalition_units)
        row.update(arrivals)
        closest_ranges = [
            float(item["closest_range_m"])
            for item in members
            if item.get("closest_range_m") is not None
        ]
        row["closest_range_min_m"] = min(closest_ranges) if closest_ranges else None
        row["closest_range_mean_m"] = (
            statistics.fmean(closest_ranges) if closest_ranges else None
        )
        separations = [
            float(item["member_separation_m"])
            for item in members
            if item.get("member_separation_m") is not None
        ]
        row["minimum_member_separation_m"] = min(separations) if separations else None
        row["first_failure_distribution"] = row[
            "pair_first_failure_reason_distribution"
        ]
        row.update(_safety_summary(members))
        row["second_primary_failure_distribution"] = json.dumps(
            row["second_primary_failure_distribution"],
            ensure_ascii=False,
            sort_keys=True,
        )
        results.append(row)
    return results


def _consolidate_pairs(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], list[Mapping[str, Any]]] = defaultdict(list)
    for index, item in enumerate(items):
        grouped[(item.get("resource_id"), item.get("target_id"), item.get("member_role"))].append(
            {**item, "_input_order": index}
        )
    consolidated = []
    for values in grouped.values():
        latest = dict(values[-1])
        for field in _INPUT_FIELDS:
            explicit = [item.get(field) for item in values if item.get(field) is not None]
            if explicit:
                latest[field] = explicit[-1]
        consolidated.append(latest)
    return consolidated


def _higher_level_units(
    members: Sequence[Mapping[str, Any]], *, level: str
) -> list[list[Mapping[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for item in members:
        if level == "target":
            key = (item.get("target_id"),)
        else:
            key = (
                item.get("target_id"),
                item.get("coalition_id") or item.get("target_id"),
            )
        grouped[key].append(item)
    return list(grouped.values())


def _stage_summary(
    units: Sequence[Sequence[Mapping[str, Any]]], stage: str
) -> dict[str, int | float | None]:
    passed = 0
    available = 0
    for unit in units:
        values = [item.get(stage) for item in unit]
        if values and all(value is not None for value in values):
            available += 1
            passed += int(all(value is True for value in values))
    return {
        "passed": passed,
        "available": available,
        "unavailable": len(units) - available,
        "rate": passed / available if available else None,
    }


def _second_primary_summary(
    members: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    grouped: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for item in members:
        grouped[item.get("target_id")].append(item)
    second_members: list[Mapping[str, Any]] = []
    for values in grouped.values():
        ordered = sorted(values, key=_member_sort_key)
        if len(ordered) < 2:
            continue
        second_members.append(ordered[1])

    units = [[item] for item in second_members]
    result: dict[str, Any] = {
        "second_primary_member_count": len(second_members),
    }
    stage_summaries: dict[str, dict[str, int | float | None]] = {}
    for stage in STAGES:
        summary = _stage_summary(units, stage)
        stage_summaries[stage] = summary
        for suffix, value in summary.items():
            result[f"second_primary_{stage}_{suffix}"] = value

    physical = stage_summaries["physical_intercept"]
    opportunities = int(physical["available"])
    successes = int(physical["passed"])
    unavailable = int(physical["unavailable"])
    availability, availability_reason = _outcome_availability(
        unit_count=len(second_members),
        available_count=opportunities,
        unavailable_count=unavailable,
        empty_reason="second_primary_member_not_present",
        missing_reason="second_primary_physical_intercept_evidence_missing",
    )
    failure_reason = _failure_reason_summary(units)
    result.update(
        {
            "second_primary_opportunity_count": opportunities,
            "second_primary_success_count": successes if opportunities else None,
            "second_primary_failure_count": (
                opportunities - successes if opportunities else None
            ),
            "second_primary_availability": availability,
            "second_primary_availability_reason": availability_reason,
            "second_primary_first_failure_reason_availability": failure_reason[
                "availability"
            ],
            "second_primary_first_failure_reason_availability_reason": failure_reason[
                "availability_reason"
            ],
            "second_primary_first_failure_reason_available_count": failure_reason[
                "available_unit_count"
            ],
            "second_primary_first_failure_reason_unavailable_count": failure_reason[
                "unavailable_unit_count"
            ],
            "second_primary_failure_distribution": failure_reason["distribution"],
        }
    )
    return result


def _failure_reason_summary(
    units: Sequence[Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Summarize producer-provided first-failure reasons without filling gaps."""

    distribution: Counter[str] = Counter()
    failed_unit_count = 0
    available_unit_count = 0
    unavailable_unit_count = 0
    physical_available_unit_count = 0
    for unit in units:
        physical_values = [item.get("physical_intercept") for item in unit]
        if not physical_values or any(value is None for value in physical_values):
            continue
        physical_available_unit_count += 1
        failed_members = [
            item for item in unit if item.get("physical_intercept") is False
        ]
        if not failed_members:
            continue
        failed_unit_count += 1
        reasons = [
            str(item["first_failure_reason"]).strip()
            for item in failed_members
            if isinstance(item.get("first_failure_reason"), str)
            and str(item["first_failure_reason"]).strip()
        ]
        if reasons:
            available_unit_count += 1
            distribution.update(reasons)
        else:
            unavailable_unit_count += 1

    if failed_unit_count == 0:
        if physical_available_unit_count:
            availability = "not_applicable"
            availability_reason = "no_explicit_physical_failure"
        else:
            availability = "unavailable"
            availability_reason = "physical_intercept_evidence_unavailable"
    elif unavailable_unit_count == 0:
        availability = "available"
        availability_reason = None
    elif available_unit_count:
        availability = "partial"
        availability_reason = "first_failure_reason_missing_for_some_failed_units"
    else:
        availability = "unavailable"
        availability_reason = "first_failure_reason_missing_for_failed_units"
    return {
        "availability": availability,
        "availability_reason": availability_reason,
        "failed_unit_count": failed_unit_count,
        "available_unit_count": available_unit_count,
        "unavailable_unit_count": unavailable_unit_count,
        "distribution": dict(distribution),
    }


def _outcome_availability(
    *,
    unit_count: int,
    available_count: int,
    unavailable_count: int,
    empty_reason: str,
    missing_reason: str,
) -> tuple[str, str | None]:
    if unit_count == 0:
        return "unavailable", empty_reason
    if available_count == 0:
        return "unavailable", missing_reason
    if unavailable_count:
        return "partial", missing_reason
    return "available", None


def _common_lock_summary(
    target_units: Sequence[Sequence[Mapping[str, Any]]],
) -> dict[str, int | float | None]:
    passed = 0
    available = 0
    for unit in target_units:
        values = [item.get("common_lock") for item in unit if item.get("common_lock") is not None]
        if not values:
            continue
        available += 1
        passed += int(any(value is True for value in values))
    return {
        "common_lock_passed": passed,
        "common_lock_available": available,
        "common_lock_unavailable": len(target_units) - available,
        "common_lock_rate": passed / available if available else None,
    }


def _arrival_summary(
    coalition_units: Sequence[Sequence[Mapping[str, Any]]],
) -> dict[str, int | float | None]:
    dispersions = []
    for unit in coalition_units:
        values = [
            float(item["arrival_error_s"])
            for item in unit
            if item.get("arrival_error_s") is not None
        ]
        if len(values) >= 2:
            dispersions.append(max(values) - min(values))
    return {
        "arrival_group_count": len(dispersions),
        "arrival_dispersion_mean_s": statistics.fmean(dispersions) if dispersions else None,
        "arrival_dispersion_max_s": max(dispersions) if dispersions else None,
    }


def _safety_summary(members: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    explicit_reserve = [
        item.get("reserve_unauthorized")
        for item in members
        if item.get("reserve_unauthorized") is not None
    ]
    inferred_reserve = [
        bool(item.get("control_allowed") or item.get("mode_switched") or item.get("physical_intercept"))
        and item.get("reserve_activated") is False
        for item in members
        if _is_reserve(item)
        and item.get("reserve_unauthorized") is None
        and item.get("reserve_activated") is not None
    ]
    reserve_values = explicit_reserve + inferred_reserve
    rewrite_values = [
        int(item["global_track_id_rewrite_count"])
        for item in members
        if item.get("global_track_id_rewrite_count") is not None
    ]
    truth_values = [
        int(item["online_truth_use_count"])
        for item in members
        if item.get("online_truth_use_count") is not None
    ]
    return {
        "reserve_unauthorized_count": sum(bool(value) for value in reserve_values)
        if reserve_values
        else None,
        "reserve_unauthorized_availability": "available" if reserve_values else "unavailable",
        "global_track_id_rewrite_count": sum(rewrite_values) if rewrite_values else None,
        "global_track_id_rewrite_availability": "available" if rewrite_values else "unavailable",
        "online_truth_use_count": sum(truth_values) if truth_values else None,
        "online_truth_use_availability": "available" if truth_values else "unavailable",
    }


def _communication_summary(payload: Any) -> dict[str, Any]:
    rows = _d4_rows_from_payload(payload) if payload is not None else []
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = _normalize_d4_communication_row(raw)
        fault = row.get("communication_fault") or row.get("case") or "unspecified"
        grouped[str(fault)].append(row)
    by_fault = {}
    for fault, values in sorted(grouped.items()):
        passed = [item.get("communication_passed") for item in values if item.get("communication_passed") is not None]
        closed = [item.get("fail_closed") for item in values if item.get("fail_closed") is not None]
        by_fault[fault] = {
            "case_count": len(values),
            "passed_count": sum(value is True for value in passed) if passed else None,
            "pass_rate": sum(value is True for value in passed) / len(passed) if passed else None,
            "pass_available_count": len(passed),
            "fail_closed_count": sum(value is True for value in closed) if closed else None,
            "fail_closed_rate": sum(value is True for value in closed) / len(closed) if closed else None,
            "fail_closed_available_count": len(closed),
        }
    return {
        "status": "available" if rows else "unavailable",
        "case_count": len(rows) if rows else None,
        "by_fault": by_fault,
    }


def _normalize_d4_communication_row(item: Mapping[str, Any]) -> dict[str, Any]:
    """Map the persisted D4 case contract without widening generic aliases."""

    row = _normalize_row(item)
    if row.get("communication_fault") is None:
        row["communication_fault"] = _first(item, "scenario_id")
    if row.get("communication_passed") is None:
        row["communication_passed"] = _bool_or_none(_first(item, "passed"))
    # ``fail_closed`` is already an exact shared field and must not be inferred.
    return row


def _build_aggregate(
    raw_rows: Sequence[Mapping[str, Any]],
    seed_rows: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    communication: Mapping[str, Any],
    *,
    primary_source: Mapping[str, Any],
) -> dict[str, Any]:
    funnels = {
        level: {
            stage: _sum_stage(seed_rows, level, stage)
            for stage in STAGES
        }
        for level in ("pair", "target", "coalition")
    }
    physical_outcomes = {
        level: _physical_outcome_summary(funnels[level]["physical_intercept"])
        for level in ("pair", "target", "coalition")
    }
    first_failure_reasons = {
        level: _aggregate_failure_reason(seed_rows, prefix=level)
        for level in ("pair", "target", "coalition")
    }
    second_primary_funnel = {
        stage: _sum_prefixed_stage(seed_rows, "second_primary", stage)
        for stage in STAGES
    }
    second_primary_outcome = _physical_outcome_summary(
        second_primary_funnel["physical_intercept"]
    )
    second_first_failure = _aggregate_failure_reason(
        seed_rows, prefix="second_primary"
    )
    second_distribution: Counter[str] = Counter()
    for row in seed_rows:
        second_distribution.update(json.loads(row["second_primary_failure_distribution"]))
    second_opportunities = sum(
        int(row["second_primary_opportunity_count"]) for row in seed_rows
    )
    second_successes = sum(
        int(value)
        for row in seed_rows
        if (value := row.get("second_primary_success_count")) is not None
    )
    second_failures = sum(
        int(value)
        for row in seed_rows
        if (value := row.get("second_primary_failure_count")) is not None
    )

    common_passed = sum(int(row["common_lock_passed"]) for row in seed_rows)
    common_available = sum(int(row["common_lock_available"]) for row in seed_rows)
    arrival_values = [
        float(row["arrival_dispersion_mean_s"])
        for row in seed_rows
        if row.get("arrival_dispersion_mean_s") is not None
    ]
    closest_values = [
        float(row["closest_range_min_m"])
        for row in seed_rows
        if row.get("closest_range_min_m") is not None
    ]
    acceptance = _acceptance(seed_rows, primary_source=primary_source)
    return {
        "schema_version": COOPERATIVE_CLOSURE_SCHEMA_VERSION,
        "offline_only": True,
        "control_feedback": False,
        "raw_row_count": len(raw_rows),
        "seed_group_count": len(seed_rows),
        "actual_scale": {
            "resource_counts": sorted({int(row["resource_count"]) for row in seed_rows}),
            "target_counts": sorted({int(row["target_count"]) for row in seed_rows}),
        },
        "optional_evidence_manifest": dict(manifest),
        "primary_source": dict(primary_source),
        "funnels": funnels,
        "physical_outcomes": physical_outcomes,
        "coalition_completion": {
            **physical_outcomes["coalition"],
            "completion_count": physical_outcomes["coalition"]["success_count"],
            "completion_rate": physical_outcomes["coalition"]["success_rate"],
            "first_failure_reason": first_failure_reasons["coalition"],
        },
        "second_primary": {
            "availability": second_primary_outcome["availability"],
            "availability_reason": second_primary_outcome[
                "availability_reason"
            ],
            "member_count": sum(
                int(row["second_primary_member_count"]) for row in seed_rows
            ),
            "opportunity_count": second_opportunities,
            "success_count": second_successes if second_opportunities else None,
            "failure_count": second_failures if second_opportunities else None,
            "failure_distribution": dict(second_distribution),
            "first_failure_reason": second_first_failure,
            "funnel": second_primary_funnel,
        },
        "first_failure_reasons": first_failure_reasons,
        "first_failure_distribution": first_failure_reasons["pair"][
            "distribution"
        ],
        "common_lock": {
            "status": "available" if common_available else "unavailable",
            "passed": common_passed if common_available else None,
            "available": common_available,
            "unavailable": sum(int(row["common_lock_unavailable"]) for row in seed_rows),
            "rate": common_passed / common_available if common_available else None,
        },
        "arrival_dispersion": {
            "status": "available" if arrival_values else "unavailable",
            "group_count": sum(int(row["arrival_group_count"]) for row in seed_rows),
            "mean_s": statistics.fmean(arrival_values) if arrival_values else None,
            "max_s": max(
                (float(row["arrival_dispersion_max_s"]) for row in seed_rows if row.get("arrival_dispersion_max_s") is not None),
                default=None,
            ),
        },
        "closest_range": {
            "status": "available" if closest_values else "unavailable",
            "seed_count": len(closest_values),
            "minimum_m": min(closest_values) if closest_values else None,
            "mean_of_seed_minimum_m": statistics.fmean(closest_values)
            if closest_values
            else None,
        },
        "provenance": {
            name: sorted(
                {
                    value
                    for row in raw_rows
                    if (value := row.get(name)) is not None
                },
                key=str,
            )
            for name in (
                "plan_owner",
                "plan_version",
                "coalition_owner",
                "coalition_version",
                "coalition_epoch",
            )
        },
        "communication_faults": dict(communication),
        "acceptance": acceptance,
    }


def _sum_stage(
    seed_rows: Sequence[Mapping[str, Any]], level: str, stage: str
) -> dict[str, Any]:
    passed = sum(int(row[f"{level}_{stage}_passed"]) for row in seed_rows)
    available = sum(int(row[f"{level}_{stage}_available"]) for row in seed_rows)
    unavailable = sum(int(row[f"{level}_{stage}_unavailable"]) for row in seed_rows)
    return {
        "status": "available" if available else "unavailable",
        "passed": passed if available else None,
        "available": available,
        "unavailable": unavailable,
        "rate": passed / available if available else None,
    }


def _sum_prefixed_stage(
    seed_rows: Sequence[Mapping[str, Any]], prefix: str, stage: str
) -> dict[str, Any]:
    passed = sum(int(row[f"{prefix}_{stage}_passed"]) for row in seed_rows)
    available = sum(int(row[f"{prefix}_{stage}_available"]) for row in seed_rows)
    unavailable = sum(int(row[f"{prefix}_{stage}_unavailable"]) for row in seed_rows)
    return {
        "status": "available" if available else "unavailable",
        "passed": passed if available else None,
        "available": available,
        "unavailable": unavailable,
        "rate": passed / available if available else None,
    }


def _physical_outcome_summary(stage: Mapping[str, Any]) -> dict[str, Any]:
    available = int(stage.get("available") or 0)
    unavailable = int(stage.get("unavailable") or 0)
    unit_count = available + unavailable
    passed = stage.get("passed")
    availability, availability_reason = _outcome_availability(
        unit_count=unit_count,
        available_count=available,
        unavailable_count=unavailable,
        empty_reason="physical_opportunity_not_present",
        missing_reason="physical_intercept_evidence_missing",
    )
    return {
        "availability": availability,
        "availability_reason": availability_reason,
        "unit_count": unit_count,
        "available_opportunity_count": available,
        "unavailable_opportunity_count": unavailable,
        "success_count": int(passed) if passed is not None else None,
        "failure_count": (
            available - int(passed) if passed is not None else None
        ),
        "success_rate": stage.get("rate") if available else None,
    }


def _aggregate_failure_reason(
    seed_rows: Sequence[Mapping[str, Any]], *, prefix: str
) -> dict[str, Any]:
    if prefix == "second_primary":
        available_field = (
            "second_primary_first_failure_reason_available_count"
        )
        unavailable_field = (
            "second_primary_first_failure_reason_unavailable_count"
        )
        distribution_field = "second_primary_failure_distribution"
        failed_count = sum(
            int(value)
            for row in seed_rows
            if (value := row.get("second_primary_failure_count")) is not None
        )
        physical_available = sum(
            int(row["second_primary_physical_intercept_available"])
            for row in seed_rows
        )
    else:
        available_field = f"{prefix}_first_failure_reason_available_unit_count"
        unavailable_field = (
            f"{prefix}_first_failure_reason_unavailable_unit_count"
        )
        distribution_field = f"{prefix}_first_failure_reason_distribution"
        physical_available = sum(
            int(row[f"{prefix}_physical_intercept_available"])
            for row in seed_rows
        )
        failed_count = sum(
            int(row[f"{prefix}_first_failure_reason_failed_unit_count"])
            for row in seed_rows
        )
    reason_available_count = sum(
        int(row[available_field]) for row in seed_rows
    )
    reason_unavailable_count = sum(
        int(row[unavailable_field]) for row in seed_rows
    )
    distribution: Counter[str] = Counter()
    for row in seed_rows:
        distribution.update(json.loads(row[distribution_field]))

    if failed_count == 0:
        if physical_available:
            availability = "not_applicable"
            availability_reason = "no_explicit_physical_failure"
        else:
            availability = "unavailable"
            availability_reason = "physical_intercept_evidence_unavailable"
    elif reason_unavailable_count == 0:
        availability = "available"
        availability_reason = None
    elif reason_available_count:
        availability = "partial"
        availability_reason = "first_failure_reason_missing_for_some_failed_units"
    else:
        availability = "unavailable"
        availability_reason = "first_failure_reason_missing_for_failed_units"
    return {
        "availability": availability,
        "availability_reason": availability_reason,
        "failed_unit_count": failed_count,
        "reason_available_unit_count": reason_available_count,
        "reason_unavailable_unit_count": reason_unavailable_count,
        "distribution": dict(distribution),
    }


def _acceptance(
    seed_rows: Sequence[Mapping[str, Any]],
    *,
    primary_source: Mapping[str, Any],
) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in seed_rows:
        grouped[str(row.get("profile") or "NA")].append(row)
    coalition_by_profile = {
        profile: _coalition_acceptance_check(rows)
        for profile, rows in sorted(grouped.items())
    }
    selected_profile, selection_source = _select_acceptance_profile(
        coalition_by_profile,
        declared_profile=primary_source.get("best_candidate_profile"),
    )
    selected = (
        coalition_by_profile.get(selected_profile)
        if selected_profile is not None
        else None
    )
    coalition_ok = selected.get("value") if selected is not None else None
    coalition_status = (
        selected.get("status") if selected is not None else "insufficient_evidence"
    )

    checks = {
        "coalition_at_least_8_of_10": {
            "status": coalition_status,
            "value": coalition_ok,
            "passed_seed_count": (
                selected.get("passed_seed_count") if selected is not None else None
            ),
            "failed_seed_count": (
                selected.get("failed_seed_count") if selected is not None else None
            ),
            "available_seed_count": (
                selected.get("available_seed_count") if selected is not None else 0
            ),
            "unavailable_seed_count": (
                selected.get("unavailable_seed_count") if selected is not None else 0
            ),
            "threshold": 0.8,
            "minimum_seed_count": 10,
            "selected_profile": selected_profile,
            "profile_selection_source": selection_source,
            "by_profile": coalition_by_profile,
        },
        "reserve_unauthorized_zero": _zero_check(
            seed_rows,
            "reserve_unauthorized_count",
            "reserve_unauthorized_availability",
        ),
        "global_track_id_rewrite_zero": _zero_check(
            seed_rows,
            "global_track_id_rewrite_count",
            "global_track_id_rewrite_availability",
        ),
        "online_truth_use_zero": _zero_check(
            seed_rows,
            "online_truth_use_count",
            "online_truth_use_availability",
        ),
    }
    values = [item.get("value") for item in checks.values()]
    return {
        "checks": checks,
        "overall_status": "available" if all(value is not None for value in values) else "unavailable",
        "all_passed": all(values) if all(value is not None for value in values) else None,
        "advisory_only": True,
    }


def _coalition_acceptance_check(
    seed_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_seed: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in seed_rows:
        by_seed[str(row.get("seed"))].append(row)
    values: list[bool] = []
    for rows in by_seed.values():
        available = sum(
            int(row["coalition_physical_intercept_available"]) for row in rows
        )
        if available <= 0:
            continue
        passed = sum(
            int(row["coalition_physical_intercept_passed"]) for row in rows
        )
        values.append(passed == available)
    passed = sum(values)
    total = len(values)
    unique_seed_count = len(by_seed)
    return {
        "status": "available" if total >= 10 else "insufficient_evidence",
        "value": passed / total >= 0.8 if total >= 10 else None,
        "passed_seed_count": passed if total else None,
        "failed_seed_count": total - passed if total else None,
        "available_seed_count": total,
        "unavailable_seed_count": unique_seed_count - total,
        "unique_seed_count": unique_seed_count,
        "rate": passed / total if total else None,
    }


def _select_acceptance_profile(
    checks: Mapping[str, Mapping[str, Any]],
    *,
    declared_profile: Any,
) -> tuple[str | None, str]:
    declared = str(declared_profile) if declared_profile is not None else None
    if declared in checks:
        return declared, "source_summary.best_candidate_profile"
    if not checks:
        return None, "no_profile_evidence"
    selected = min(
        checks,
        key=lambda profile: (
            -int(checks[profile].get("passed_seed_count") or 0),
            -float(checks[profile].get("rate") or 0.0),
            -int(checks[profile].get("available_seed_count") or 0),
            profile,
        ),
    )
    return selected, (
        "observed_max_passed_seed_count_then_rate_then_available_seed_count_then_profile"
    )


def _zero_check(
    rows: Sequence[Mapping[str, Any]], value_field: str, availability_field: str
) -> dict[str, Any]:
    values = [
        int(row[value_field])
        for row in rows
        if row.get(availability_field) == "available"
        and row.get(value_field) is not None
    ]
    return {
        "status": "available" if values else "unavailable",
        "value": sum(values) == 0 if values else None,
        "count": sum(values) if values else None,
        "available_seed_count": len(values),
        "threshold": 0,
    }


def _write_plot(
    seed_rows: Sequence[Mapping[str, Any]],
    aggregate: Mapping[str, Any],
    path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    stages = list(STAGES)
    labels = ["assigned", "visible", "associated", "contract", "control", "mode", "physical"]
    for level, marker in (("pair", "o"), ("target", "s"), ("coalition", "^")):
        rates = [aggregate["funnels"][level][stage]["rate"] for stage in stages]
        axes[0, 0].plot(
            range(len(stages)),
            [math.nan if value is None else value for value in rates],
            marker=marker,
            label=level,
        )
    axes[0, 0].set_xticks(range(len(stages)), labels, rotation=25)
    axes[0, 0].set_ylim(0, 1.05)
    axes[0, 0].set_title("Independent-denominator funnels")
    axes[0, 0].legend()
    axes[0, 0].grid(alpha=0.25)

    seed_labels = [str(row.get("seed")) for row in seed_rows]
    coalition_rates = [
        row.get("coalition_physical_intercept_rate") for row in seed_rows
    ]
    axes[0, 1].bar(
        seed_labels,
        [math.nan if value is None else value for value in coalition_rates],
        color="#4C78A8",
    )
    axes[0, 1].set_ylim(0, 1.05)
    axes[0, 1].set_title("Coalition completion by seed")
    axes[0, 1].set_xlabel("seed")

    distribution = aggregate["second_primary"]["failure_distribution"]
    if distribution:
        axes[1, 0].bar(distribution.keys(), distribution.values(), color="#E45756")
        axes[1, 0].tick_params(axis="x", rotation=25)
    else:
        reason_status = aggregate["second_primary"]["first_failure_reason"][
            "availability"
        ]
        axes[1, 0].text(0.5, 0.5, reason_status, ha="center", va="center")
    axes[1, 0].set_title("Second-primary failure reasons")

    arrival = [
        row.get("arrival_dispersion_mean_s") for row in seed_rows
    ]
    axes[1, 1].plot(
        seed_labels,
        [math.nan if value is None else value for value in arrival],
        marker="o",
        color="#72B7B2",
    )
    axes[1, 1].set_title("Arrival dispersion by seed")
    axes[1, 1].set_ylabel("s")
    axes[1, 1].grid(alpha=0.25)
    fig.suptitle("P1 Cooperative Closure Offline Evaluation")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def _render_markdown(
    aggregate: Mapping[str, Any], *, title: str, plot_name: str
) -> str:
    lines = [
        f"# {title}",
        "",
        "本报告由 D6 离线消费写盘证据生成，不连接 AirSim、不参与分配或控制。`unavailable` 不按 0 计入分母。",
        "",
        f"![协同闭环指标]({plot_name})",
        "",
        "## 证据状态",
        "",
        "| 证据 | 状态 | 说明 |",
        "|---|---|---|",
    ]
    for name, item in aggregate["optional_evidence_manifest"].items():
        lines.append(f"| {name} | {item['status']} | {item.get('reason') or item.get('evidence_path') or '-'} |")

    lines.extend(["", "## 三层漏斗", "", "| 层级 | 阶段 | 通过/有效 | 不可用 | 比例 |", "|---|---|---:|---:|---:|"])
    for level in ("pair", "target", "coalition"):
        for stage in STAGES:
            item = aggregate["funnels"][level][stage]
            lines.append(
                f"| {level} | {stage} | {_ratio(item.get('passed'), item.get('available'))} | {item['unavailable']} | {_fmt(item.get('rate'))} |"
            )

    lines.extend(
        [
            "",
            "## 物理结果独立分母",
            "",
            "pair、target、coalition 各自使用本层写盘机会数，不允许由相邻层结果回填。`unavailable` 不计为失败或成功。",
            "",
            "| 层级 | Availability | Units | 有效机会 | 不可用机会 | 成功 | 失败 | 成功率 | 首失败原因可用性 | 原因分布 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for level in ("pair", "target", "coalition"):
        outcome = aggregate["physical_outcomes"][level]
        failure = aggregate["first_failure_reasons"][level]
        lines.append(
            f"| {level} | {outcome['availability']} | {outcome['unit_count']} | {outcome['available_opportunity_count']} | {outcome['unavailable_opportunity_count']} | {_fmt(outcome.get('success_count'))} | {_fmt(outcome.get('failure_count'))} | {_fmt(outcome.get('success_rate'))} | {failure['availability']} | `{json.dumps(failure['distribution'], ensure_ascii=False, sort_keys=True)}` |"
        )

    second = aggregate["second_primary"]
    common = aggregate["common_lock"]
    arrival = aggregate["arrival_dispersion"]
    lines.extend(
        [
            "",
            "## 协同质量",
            "",
            f"- 第二 primary 物理结果：availability=`{second['availability']}`，成功/有效机会=`{second['success_count']}/{second['opportunity_count']}`，失败=`{second['failure_count']}`，不可用成员=`{second['funnel']['physical_intercept']['unavailable']}`。",
            f"- 第二 primary 首失败原因：availability=`{second['first_failure_reason']['availability']}`，原因有效/缺失失败单元=`{second['first_failure_reason']['reason_available_unit_count']}/{second['first_failure_reason']['reason_unavailable_unit_count']}`，分布 `{json.dumps(second['failure_distribution'], ensure_ascii=False, sort_keys=True)}`。缺原因不会写成 `unspecified`。",
            f"- 共同锁定率：`{_fmt(common.get('rate'))}`，有效目标 `{common.get('available')}`，不可用目标 `{common.get('unavailable')}`。",
            f"- 到达离散：有效联盟 `{arrival.get('group_count')}`，均值 `{_fmt(arrival.get('mean_s'))} s`，最大 `{_fmt(arrival.get('max_s'))} s`。",
            f"- pair 首失败原因（兼容字段）：`{json.dumps(aggregate['first_failure_distribution'], ensure_ascii=False, sort_keys=True)}`。",
            f"- 最近距离：最小 `{_fmt(aggregate['closest_range'].get('minimum_m'))} m`，逐 seed 最小值均值 `{_fmt(aggregate['closest_range'].get('mean_of_seed_minimum_m'))} m`。",
            "",
            "### 第二 primary 逐阶段漏斗",
            "",
            "| 阶段 | Availability | 通过/有效 | 不可用 | 比例 |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for stage in STAGES:
        item = second["funnel"][stage]
        lines.append(
            f"| {stage} | {item['status']} | {_ratio(item.get('passed'), item.get('available'))} | {item['unavailable']} | {_fmt(item.get('rate'))} |"
        )
    lines.extend(["", "## 通信故障", ""])
    communication = aggregate["communication_faults"]
    if communication.get("status") != "available":
        lines.append("D4 communication summary：`unavailable`。")
    else:
        lines.extend(["| 故障 | 通过/有效 | fail-closed/有效 |", "|---|---:|---:|"])
        for fault, item in communication["by_fault"].items():
            lines.append(
                f"| {fault} | {_ratio(item.get('passed_count'), item.get('pass_available_count'))} | {_ratio(item.get('fail_closed_count'), item.get('fail_closed_available_count'))} |"
            )

    lines.extend(["", "## 验收检查", "", "| 检查 | 状态 | 结果 | 证据 |", "|---|---|---|---|"])
    for name, item in aggregate["acceptance"]["checks"].items():
        evidence = item.get("count")
        if evidence is None:
            evidence = f"{item.get('passed_seed_count', 'NA')}/{item.get('available_seed_count', 0)}"
        lines.append(f"| {name} | {item['status']} | {_fmt_bool(item.get('value'))} | {evidence} |")
    coalition_check = aggregate["acceptance"]["checks"]["coalition_at_least_8_of_10"]
    lines.extend(
        [
            "",
            f"联盟验收采用 profile=`{coalition_check.get('selected_profile')}`；选择规则=`{coalition_check.get('profile_selection_source')}`。",
        ]
    )
    coalition_groups = coalition_check.get("by_profile", {})
    if coalition_groups:
        lines.extend(["", "### 联盟验收分组", "", "| profile | 状态 | 完成 seed | 失败 seed | 不可用 seed | 比例 |", "|---|---|---:|---:|---:|---:|"])
        for name, item in coalition_groups.items():
            lines.append(
                f"| {name} | {item['status']} | {_ratio(item.get('passed_seed_count'), item.get('available_seed_count'))} | {item.get('failed_seed_count', 'NA')} | {item.get('unavailable_seed_count', 'NA')} | {_fmt(item.get('rate'))} |"
            )
    lines.extend(
        [
            "",
            f"总体状态：`{aggregate['acceptance']['overall_status']}`；全部通过：`{_fmt_bool(aggregate['acceptance']['all_passed'])}`。该结论仅供离线验收，不回写控制。",
            "",
        ]
    )
    return "\n".join(lines)


def _is_reserve(item: Mapping[str, Any]) -> bool:
    return str(item.get("member_role") or "").lower() in {"reserve", "observer", "standby"}


def _member_sort_key(item: Mapping[str, Any]) -> tuple[int, str]:
    order = item.get("member_order")
    role = str(item.get("member_role") or "").lower()
    if order is None:
        if "2" in role or role in {"second_primary", "secondary_primary"}:
            order = 2
        elif "1" in role or role == "primary":
            order = 1
        else:
            order = 99
    return int(order), str(item.get("resource_id") or "")


def _json_distinct(items: Sequence[Mapping[str, Any]], field: str) -> str:
    values = sorted(
        {item.get(field) for item in items if item.get(field) is not None}, key=str
    )
    return json.dumps(values, ensure_ascii=False)


def _sortable_group(item: tuple[tuple[Any, Any, Any], Any]) -> tuple[str, str, str]:
    key = item[0]
    return tuple("" if value is None else str(value) for value in key)  # type: ignore[return-value]


def _first(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in item and item[name] is not None:
            return item[name]
    return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "passed", "pass", "allowed"}:
        return True
    if text in {"false", "0", "no", "n", "failed", "fail", "rejected"}:
        return False
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer_or_none(value: Any) -> int | None:
    number = _float_or_none(value)
    return int(number) if number is not None else None


def _number_or_text(value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def _coerce_mapping(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: (None if value == "" else value) for key, value in item.items()}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value


def _ratio(numerator: Any, denominator: Any) -> str:
    if numerator is None or denominator in {None, 0}:
        return "NA"
    return f"{int(numerator)}/{int(denominator)}"


def _fmt(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _fmt_bool(value: Any) -> str:
    if value is None:
        return "NA"
    return "通过" if value is True else "未通过"
