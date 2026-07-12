"""Offline, availability-aware aggregation for the P1 closure evidence bundle."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, is_dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


P1_ACCEPTANCE_SCHEMA_VERSION = "d6-p1-unified-acceptance-v1"

SOURCE_NAMES = (
    "main_terminal_closure",
    "d1_long_replay",
    "d2_long_replay",
    "d3_assignment_calibration",
    "d4_failover_matrix",
    "d5_visual_calibration",
    "d7_locked_dropout",
    "d7_png_ttc",
    "d7_trend_coast",
)

METRIC_NAMES = (
    "contract_allowed_count",
    "control_allowed_count",
    "mode_switched_count",
    "physical_intercept_count",
    "pair_opportunity_count",
    "pair_success_count",
    "target_opportunity_count",
    "target_success_count",
    "coalition_opportunity_count",
    "coalition_completion_count",
    "terminal_switch_allowed_count",
    "terminal_prediction_count",
    "terminal_delivery_expired_count",
    "terminal_trend_coast_count",
    "ttc_area_jump_reject_count",
    "ttc_bbox_clipping_reject_count",
    "ttc_not_expanding_reject_count",
    "ttc_out_of_range_reject_count",
    "id_switch_count",
    "track_continuity",
    "false_track_count",
    "rmse",
    "nis_mean",
    "nees_mean",
    "online_truth_use_count",
    "wrong_binding_count",
    "command_discontinuity_rate",
    "physical_success_rate",
)

ROW_FIELDS = (
    "source",
    "source_schema_version",
    "family",
    "profile",
    "scenario_id",
    "seed",
    "resource_count",
    "target_count",
    "dropout_frames",
    "case_passed",
    "execution_allowed",
    "fail_closed",
    "incremental_applied",
    "assignment_equivalent",
    "cost_equivalent",
    "ready",
    "evidence_path",
    *METRIC_NAMES,
    *(f"{name}_availability" for name in METRIC_NAMES),
)


@dataclass(frozen=True)
class P1AcceptanceInputs:
    """Optional persisted summaries produced by main and D1-D7.

    Values may be JSON paths, mappings, or dataclass/report objects exposing
    ``to_dict``/``as_dict``. D6 never imports an online module to consume them.
    """

    main_terminal_closure: Any | None = None
    d1_long_replay: Any | None = None
    d2_long_replay: Any | None = None
    d3_assignment_calibration: Any | None = None
    d4_failover_matrix: Any | None = None
    d5_visual_calibration: Any | None = None
    d7_locked_dropout: Any | None = None
    d7_png_ttc: Any | None = None
    d7_trend_coast: Any | None = None


class P1AcceptanceReportGenerator:
    """Generate the second-batch P1 report without controlling AirSim."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: P1AcceptanceInputs,
        title: str = "P1 统一离线验收报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        payloads, source_manifest = _load_sources(inputs)
        rows = _normalize_rows(payloads, source_manifest)
        aggregate = _build_aggregate(payloads, source_manifest, rows)

        csv_path = output_dir / "p1_acceptance_per_seed.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        json_path = output_dir / "p1_acceptance_aggregate.json"
        json_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        plot_path = output_dir / "p1_acceptance_overview.png"
        _write_overview_plot(rows, plot_path)

        markdown_path = output_dir / "P1_UNIFIED_ACCEPTANCE_REPORT.md"
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


def load_p1_acceptance_source(source: Any) -> dict[str, Any]:
    """Load one versioned summary without importing its producer module."""

    if isinstance(source, (str, Path)):
        path = Path(source)
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif isinstance(source, Mapping):
        payload = dict(source)
    elif hasattr(source, "to_dict"):
        payload = source.to_dict()
    elif hasattr(source, "as_dict"):
        payload = source.as_dict()
    elif is_dataclass(source):
        payload = asdict(source)
    else:
        raise TypeError(f"unsupported P1 summary source: {type(source)!r}")
    if not isinstance(payload, Mapping):
        raise ValueError("P1 summary root must be a JSON object")
    return _json_ready(dict(payload))


def _load_sources(
    inputs: P1AcceptanceInputs,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    payloads: dict[str, dict[str, Any]] = {}
    manifest: dict[str, dict[str, Any]] = {}
    for source_name in SOURCE_NAMES:
        source = getattr(inputs, source_name)
        evidence_path = str(source) if isinstance(source, (str, Path)) else None
        if source is None:
            manifest[source_name] = {
                "status": "unavailable",
                "schema_version": None,
                "evidence_path": None,
                "reason": "summary was not provided",
            }
            continue
        payload = load_p1_acceptance_source(source)
        schema_version = _source_schema_version(payload)
        payloads[source_name] = payload
        manifest[source_name] = {
            "status": "available",
            "schema_version": schema_version,
            "evidence_path": evidence_path,
            "reason": None,
        }
    return payloads, manifest


def _normalize_rows(
    payloads: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if payload := payloads.get("main_terminal_closure"):
        for item in _mapping_rows(payload.get("rows")):
            rows.append(_main_row(item, manifest["main_terminal_closure"]))
    if payload := payloads.get("d1_long_replay"):
        rows.append(
            _finish_row(
                {
                    "source": "d1_long_replay",
                    "family": "fusion_long_replay",
                    "scenario_id": payload.get("scenario_id"),
                    "seed": payload.get("seed"),
                    "target_count": payload.get("target_count"),
                    "online_truth_use_count": payload.get("online_truth_leak_count"),
                },
                manifest["d1_long_replay"],
            )
        )
    if payload := payloads.get("d2_long_replay"):
        for item in _mapping_rows(payload.get("per_seed")):
            rows.append(
                _finish_row(
                    {
                        "source": "d2_long_replay",
                        "family": "association_long_replay",
                        "scenario_id": item.get("scenario_name"),
                        "seed": item.get("seed"),
                        "target_count": item.get("target_count"),
                        "id_switch_count": item.get("id_switch_count"),
                        "track_continuity": item.get("track_continuity"),
                        "false_track_count": item.get("false_track_count"),
                        "rmse": item.get("rmse"),
                        "nis_mean": _nested_metric(item, "nis", "mean"),
                        "nees_mean": _nested_metric(item, "nees", "mean"),
                        "online_truth_use_count": _first_present(
                            item,
                            "online_truth_leakage_count",
                            "online_truth_isolation_violations",
                        ),
                    },
                    manifest["d2_long_replay"],
                )
            )
    if payload := payloads.get("d3_assignment_calibration"):
        for item in _mapping_rows(payload.get("rows")):
            rows.append(
                _finish_row(
                    {
                        "source": "d3_assignment_calibration",
                        "family": "assignment_calibration",
                        "scenario_id": item.get("scenario_id"),
                        "profile": item.get("scenario_kind"),
                        "resource_count": item.get("resource_count"),
                        "target_count": item.get("target_count"),
                        "incremental_applied": item.get("incremental_applied"),
                        "assignment_equivalent": item.get("assignment_equivalent"),
                        "cost_equivalent": item.get("cost_equivalent"),
                    },
                    manifest["d3_assignment_calibration"],
                )
            )
    if payload := payloads.get("d4_failover_matrix"):
        for item in _mapping_rows(payload.get("cases")):
            rows.append(
                _finish_row(
                    {
                        "source": "d4_failover_matrix",
                        "family": "failover_matrix",
                        "scenario_id": item.get("scenario_id"),
                        "case_passed": item.get("passed"),
                        "execution_allowed": item.get("execution_allowed"),
                        "fail_closed": item.get("fail_closed"),
                    },
                    manifest["d4_failover_matrix"],
                )
            )
    if payload := payloads.get("d5_visual_calibration"):
        for item in _mapping_rows(payload.get("seeds")):
            rows.append(
                _finish_row(
                    {
                        "source": "d5_visual_calibration",
                        "family": "visual_calibration",
                        "seed": item.get("seed_id", item.get("seed")),
                        "ready": _ready_value(item),
                        "wrong_binding_count": item.get("wrong_binding_count"),
                    },
                    manifest["d5_visual_calibration"],
                )
            )
    _append_d7_rows(rows, payloads, manifest)
    return rows


def _main_row(item: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    # The four layers deliberately use only like-named evidence. No terminal
    # switch or pair success value is promoted into another layer.
    return _finish_row(
        {
            "source": "main_terminal_closure",
            "family": item.get("family"),
            "profile": item.get("profile"),
            "scenario_id": item.get("case_id"),
            "seed": item.get("seed"),
            "resource_count": item.get("resource_count"),
            "target_count": item.get("target_count"),
            "dropout_frames": item.get("dropout_frames"),
            "contract_allowed_count": item.get("contract_allowed_count"),
            "control_allowed_count": item.get("control_allowed_count"),
            "mode_switched_count": item.get("mode_switched_count"),
            "physical_intercept_count": item.get("physical_intercept_count"),
            "pair_opportunity_count": item.get("pair_opportunity_count"),
            "pair_success_count": item.get("pair_success_count"),
            "target_opportunity_count": item.get("target_opportunity_count"),
            "target_success_count": item.get("target_success_count"),
            "coalition_opportunity_count": item.get("coalition_opportunity_count"),
            "coalition_completion_count": item.get("coalition_completion_count"),
            "terminal_switch_allowed_count": item.get("terminal_switch_allowed_count"),
            "terminal_prediction_count": item.get("terminal_prediction_count"),
            "terminal_delivery_expired_count": item.get("terminal_delivery_expired_count"),
            "terminal_trend_coast_count": item.get("terminal_trend_coast_count"),
            "ttc_area_jump_reject_count": item.get("ttc_area_jump_reject_count"),
            "ttc_bbox_clipping_reject_count": item.get("ttc_bbox_clipping_reject_count"),
            "ttc_not_expanding_reject_count": item.get("ttc_not_expanding_reject_count"),
            "ttc_out_of_range_reject_count": item.get("ttc_out_of_range_reject_count"),
            "online_truth_use_count": item.get("online_truth_use_count"),
            "evidence_path": item.get("control_commands") or item.get("intercept_summary"),
        },
        source,
    )


def _append_d7_rows(
    rows: list[dict[str, Any]],
    payloads: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
) -> None:
    if payload := payloads.get("d7_locked_dropout"):
        for frame_count, item in sorted(
            _mapping(payload.get("matrix")).items(), key=lambda pair: int(pair[0])
        ):
            values = _mapping(item)
            rows.append(
                _finish_row(
                    {
                        "source": "d7_locked_dropout",
                        "family": "locked_dropout",
                        "profile": f"dropout_{frame_count}_frames",
                        "dropout_frames": int(frame_count),
                        "terminal_prediction_count": _state_count(
                            values, "image_kf_predict"
                        ),
                        "terminal_delivery_expired_count": _state_count(
                            values, "expired"
                        ),
                        "wrong_binding_count": _subtract_or_none(
                            values.get("record_count"),
                            values.get("identity_plan_consistent_count"),
                        ),
                    },
                    manifest["d7_locked_dropout"],
                )
            )
    if payload := payloads.get("d7_png_ttc"):
        class_counts = _mapping(payload.get("ttc_reject_class_counts"))
        rows.append(
            _finish_row(
                {
                    "source": "d7_png_ttc",
                    "family": "png_ttc",
                    "profile": "png_ttc",
                    "ttc_area_jump_reject_count": class_counts.get("bbox_area_jump"),
                    "ttc_bbox_clipping_reject_count": class_counts.get("bbox_clipping"),
                    "ttc_not_expanding_reject_count": class_counts.get("area_not_expanding"),
                    "ttc_out_of_range_reject_count": class_counts.get("ttc_out_of_range"),
                },
                manifest["d7_png_ttc"],
            )
        )
    if payload := payloads.get("d7_trend_coast"):
        rows.append(
            _finish_row(
                {
                    "source": "d7_trend_coast",
                    "family": "trend_coast",
                    "profile": "candidate",
                    "terminal_trend_coast_count": payload.get("candidate_trigger_count"),
                    "wrong_binding_count": payload.get("candidate_wrong_binding_count"),
                    "command_discontinuity_rate": payload.get(
                        "candidate_command_discontinuity_rate"
                    ),
                    "physical_success_rate": payload.get(
                        "candidate_physical_success_rate"
                    ),
                },
                manifest["d7_trend_coast"],
            )
        )


def _finish_row(row: dict[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {field: None for field in ROW_FIELDS}
    normalized.update(row)
    normalized["source_schema_version"] = source.get("schema_version")
    if normalized.get("evidence_path") is None:
        normalized["evidence_path"] = source.get("evidence_path")
    for metric_name in METRIC_NAMES:
        normalized[f"{metric_name}_availability"] = (
            "available" if normalized.get(metric_name) is not None else "unavailable"
        )
    return normalized


def _build_aggregate(
    payloads: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    main_rows = [row for row in rows if row.get("source") == "main_terminal_closure"]
    m5n2_rows = [row for row in main_rows if row.get("family") == "m5n2_paired"]
    d2_rows = [row for row in rows if row.get("source") == "d2_long_replay"]
    dropout, png_ttc, trend_coast = _terminal_specialty_summaries(payloads)
    return {
        "schema_version": P1_ACCEPTANCE_SCHEMA_VERSION,
        "offline_only": True,
        "source_manifest": dict(manifest),
        "row_count": len(rows),
        "seed_row_count": sum(row.get("seed") is not None for row in rows),
        "terminal_layers": {
            name: _metric_summary(main_rows, name)
            for name in (
                "contract_allowed_count",
                "control_allowed_count",
                "mode_switched_count",
                "physical_intercept_count",
            )
        },
        "physical_levels": {
            "pair": _outcome_summary(
                m5n2_rows, "pair_opportunity_count", "pair_success_count"
            ),
            "target": _outcome_summary(
                m5n2_rows, "target_opportunity_count", "target_success_count"
            ),
            "coalition": _outcome_summary(
                m5n2_rows,
                "coalition_opportunity_count",
                "coalition_completion_count",
            ),
        },
        "m5n2_paired": _mapping(
            _mapping(payloads.get("main_terminal_closure")).get("m5n2_paired")
        ),
        "dropout": dropout,
        "png_ttc": png_ttc,
        "trend_coast": trend_coast,
        "d1_fusion": _d1_summary(payloads.get("d1_long_replay")),
        "d2_tracking": {
            "seed_count": len({row.get("seed") for row in d2_rows}),
            "id_switch_count": _metric_summary(d2_rows, "id_switch_count"),
            "track_continuity": _metric_summary(d2_rows, "track_continuity"),
            "false_track_count": _metric_summary(d2_rows, "false_track_count"),
            "rmse": _metric_summary(d2_rows, "rmse"),
            "aggregate": _mapping(
                _mapping(payloads.get("d2_long_replay")).get("aggregate")
            ),
        },
        "d3_assignment": _d3_summary(payloads.get("d3_assignment_calibration")),
        "d4_failover": _mapping(
            _mapping(payloads.get("d4_failover_matrix")).get("summary")
        ),
        "d5_visual": _d5_summary(payloads.get("d5_visual_calibration")),
        "metric_availability": {
            name: _availability_summary(rows, name) for name in METRIC_NAMES
        },
    }


def _terminal_specialty_summaries(
    payloads: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Prefer D7 summaries and fall back to the versioned main suite.

    The fallback only aggregates explicitly persisted fields. It never derives
    contract/control/mode/physical layers from terminal or pair outcomes.
    """

    main = _mapping(payloads.get("main_terminal_closure"))
    dropout = (
        _mapping(payloads.get("d7_locked_dropout"))
        if "d7_locked_dropout" in payloads
        else _dropout_from_main_summary(main)
    )
    png_ttc = (
        _mapping(payloads.get("d7_png_ttc"))
        if "d7_png_ttc" in payloads
        else _png_ttc_from_main_summary(main)
    )
    trend_coast = (
        _mapping(payloads.get("d7_trend_coast"))
        if "d7_trend_coast" in payloads
        else _trend_coast_from_main_summary(main)
    )
    return dropout, png_ttc, trend_coast


def _dropout_from_main_summary(main: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(_mapping(main.get("acceptance")).get("dropout_matrix"))
    source_rows = _mapping_rows(raw.get("rows"))
    if not raw and not source_rows:
        return {}
    matrix: dict[str, Any] = {}
    observed: set[int] = set()
    for row in source_rows:
        frame_count = row.get("dropout_frames")
        if frame_count is None:
            continue
        frame_count = int(frame_count)
        observed.add(frame_count)
        matrix[str(frame_count)] = {
            "record_count": 1,
            "prediction_count": row.get("prediction_count"),
            "prediction_window_expired_count": row.get(
                "prediction_window_expired_count"
            ),
            "expected_prediction_window_expiry": row.get(
                "expected_prediction_window_expiry"
            ),
            "passed": row.get("passed"),
        }
    expected = {1, 2, 3, 4, 5}
    all_compliant = raw.get("all_passed")
    if all_compliant is None and source_rows:
        passed = [row.get("passed") for row in source_rows]
        all_compliant = all(value is True for value in passed)
    return {
        "kind": "locked_dropout_matrix",
        "derived_from": "main_terminal_closure",
        "source_schema_version": _source_schema_version(main),
        "record_count": len(source_rows),
        "expected_frame_counts": sorted(expected),
        "observed_frame_counts": sorted(observed),
        "matrix_complete": expected <= observed,
        "matrix": matrix,
        "all_rows_compliant": all_compliant,
        "identity_plan_inconsistent_count": None,
        "advisory_only": True,
    }


def _png_ttc_from_main_summary(main: Mapping[str, Any]) -> dict[str, Any]:
    rows = [
        row for row in _mapping_rows(main.get("rows")) if row.get("family") == "png_ttc"
    ]
    if not rows:
        return {}
    counts = {
        "bbox_area_jump": _sum_present(rows, "ttc_area_jump_reject_count"),
        "bbox_clipping": _sum_present(rows, "ttc_bbox_clipping_reject_count"),
        "area_not_expanding": _sum_present(rows, "ttc_not_expanding_reject_count"),
        "ttc_out_of_range": _sum_present(rows, "ttc_out_of_range_reject_count"),
    }
    coverage = {
        name: (None if value is None else value > 0) for name, value in counts.items()
    }
    return {
        "kind": "png_ttc_multiseed",
        "derived_from": "main_terminal_closure",
        "source_schema_version": _source_schema_version(main),
        "case_count": len(rows),
        "seed_count": len({row.get("seed") for row in rows if row.get("seed") is not None}),
        "seeds": sorted({row.get("seed") for row in rows if row.get("seed") is not None}),
        "ttc_reject_class_counts": counts,
        "required_reject_coverage": coverage,
        "required_reject_coverage_complete": all(value is True for value in coverage.values()),
        "advisory_only": True,
    }


def _trend_coast_from_main_summary(main: Mapping[str, Any]) -> dict[str, Any]:
    rows = _mapping_rows(main.get("rows"))
    baseline = [
        row
        for row in rows
        if row.get("family") == "m5n2_paired" and row.get("profile") == "baseline"
    ]
    candidate = [
        row
        for row in rows
        if row.get("family") == "m5n2_paired"
        and "candidate" in str(row.get("profile", ""))
    ]
    if not candidate:
        return {}
    trigger_count = _sum_present(candidate, "terminal_trend_coast_count")
    wrong_binding_count = _sum_present(candidate, "wrong_binding_count")
    baseline_discontinuity = _mean_present(
        baseline, "command_discontinuity_rate"
    )
    candidate_discontinuity = _mean_present(
        candidate, "command_discontinuity_rate"
    )
    baseline_physical = _mean_present(baseline, "physical_success_rate")
    candidate_physical = _mean_present(candidate, "physical_success_rate")
    baseline_seeds = {row.get("seed") for row in baseline if row.get("seed") is not None}
    candidate_seeds = {
        row.get("seed") for row in candidate if row.get("seed") is not None
    }
    criteria = {
        "paired_seed_set": bool(baseline_seeds) and baseline_seeds == candidate_seeds,
        "candidate_triggered": None if trigger_count is None else trigger_count > 0,
        "wrong_binding_zero": (
            None if wrong_binding_count is None else wrong_binding_count == 0
        ),
        "command_discontinuity_not_worse": (
            None
            if baseline_discontinuity is None or candidate_discontinuity is None
            else candidate_discontinuity <= baseline_discontinuity
        ),
        "physical_success_not_lower": (
            None
            if baseline_physical is None or candidate_physical is None
            else candidate_physical >= baseline_physical
        ),
    }
    return {
        "kind": "trend_coast_promotion",
        "derived_from": "main_terminal_closure",
        "source_schema_version": _source_schema_version(main),
        "trend_coast_default_enabled": False,
        "baseline_seed_count": len(baseline_seeds),
        "candidate_seed_count": len(candidate_seeds),
        "candidate_trigger_count": trigger_count,
        "candidate_wrong_binding_count": wrong_binding_count,
        "baseline_command_discontinuity_rate": baseline_discontinuity,
        "candidate_command_discontinuity_rate": candidate_discontinuity,
        "baseline_physical_success_rate": baseline_physical,
        "candidate_physical_success_rate": candidate_physical,
        "criteria": criteria,
        "promotion_recommended": all(value is True for value in criteria.values()),
        "advisory_only": True,
    }


def _d1_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    item = _mapping(payload)
    return {
        key: item.get(key)
        for key in (
            "schema_version",
            "scenario_version",
            "seed",
            "target_count",
            "observation_count",
            "event_counts",
            "final_track_count",
            "online_truth_leak_count",
            "metric_availability",
        )
        if key in item
    }


def _d3_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    item = _mapping(payload)
    return {
        key: item.get(key)
        for key in (
            "profile_id",
            "profile_version",
            "scenario_count",
            "transition_count",
            "equivalent_transition_count",
            "incremental_applied_count",
            "fallback_count",
            "incremental_churn_total",
            "full_churn_total",
            "incremental_unassigned_high_threat_total",
            "full_unassigned_high_threat_total",
            "incremental_coalition_shortfall_total",
            "full_coalition_shortfall_total",
        )
        if key in item
    }


def _d5_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    item = _mapping(payload)
    return {
        key: item.get(key)
        for key in (
            "seed_count",
            "ready_seed_count",
            "total_observation_count",
            "total_terminal_association_count",
            "missing_required_fields_by_seed",
            "missing_recommended_fields_by_seed",
            "metadata",
        )
        if key in item
    }


def _metric_summary(rows: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any]:
    values = [float(row[name]) for row in rows if row.get(name) is not None]
    return {
        "status": "available" if values else "unavailable",
        "available_count": len(values),
        "unavailable_count": sum(row.get(name) is None for row in rows),
        "sum": sum(values) if values else None,
        "mean": sum(values) / len(values) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }


def _outcome_summary(
    rows: Sequence[Mapping[str, Any]], opportunity_name: str, success_name: str
) -> dict[str, Any]:
    opportunities = [
        float(row[opportunity_name])
        for row in rows
        if row.get(opportunity_name) is not None
    ]
    successes = [
        float(row[success_name]) for row in rows if row.get(success_name) is not None
    ]
    opportunity_sum = sum(opportunities) if opportunities else None
    success_sum = sum(successes) if successes else None
    rate = (
        success_sum / opportunity_sum
        if success_sum is not None and opportunity_sum not in {None, 0.0}
        else None
    )
    return {
        "status": (
            "available"
            if opportunity_sum is not None and success_sum is not None
            else "unavailable"
        ),
        "opportunity_count": opportunity_sum,
        "success_count": success_sum,
        "success_rate": rate,
    }


def _availability_summary(
    rows: Sequence[Mapping[str, Any]], metric_name: str
) -> dict[str, Any]:
    available = sum(row.get(metric_name) is not None for row in rows)
    return {
        "status": "available" if available else "unavailable",
        "available_row_count": available,
        "unavailable_row_count": len(rows) - available,
    }


def _render_markdown(
    aggregate: Mapping[str, Any], *, title: str, plot_name: str
) -> str:
    manifest = _mapping(aggregate.get("source_manifest"))
    lines = [
        f"# {title}",
        "",
        "本报告由 D6 离线消费 main 与 D1-D7 已写盘 summary 生成，不连接或控制 AirSim。旧日志缺失字段显示为 `unavailable/NA`，不补零。",
        "",
        f"![P1 验收概览]({plot_name})",
        "",
        "## 输入证据",
        "",
        "| 来源 | 状态 | Schema | Evidence |",
        "|---|---|---|---|",
    ]
    for name in SOURCE_NAMES:
        item = _mapping(manifest.get(name))
        lines.append(
            f"| `{name}` | {item.get('status', 'unavailable')} | {_fmt(item.get('schema_version'))} | {_fmt(item.get('evidence_path'))} |"
        )

    lines.extend(
        [
            "",
            "## 末端四层证据",
            "",
            "| 层级 | 状态 | 可用行 | Sum | Mean |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for name, item in _mapping(aggregate.get("terminal_layers")).items():
        values = _mapping(item)
        lines.append(
            f"| `{name}` | {values.get('status')} | {values.get('available_count')} | {_fmt(values.get('sum'))} | {_fmt(values.get('mean'))} |"
        )

    lines.extend(
        [
            "",
            "四层只接受同名上游证据：D6 不用 contract 推断 control，不用 terminal switch 推断 mode switch，也不用 pair success 回填统一 physical intercept。",
            "",
            "## M5N2 物理结果层级",
            "",
            "| 层级 | 状态 | Opportunities | Success | Rate |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for name, item in _mapping(aggregate.get("physical_levels")).items():
        values = _mapping(item)
        lines.append(
            f"| {name} | {values.get('status')} | {_fmt(values.get('opportunity_count'))} | {_fmt(values.get('success_count'))} | {_fmt(values.get('success_rate'))} |"
        )

    dropout = _mapping(aggregate.get("dropout"))
    png_ttc = _mapping(aggregate.get("png_ttc"))
    trend = _mapping(aggregate.get("trend_coast"))
    ttc_counts = _mapping(png_ttc.get("ttc_reject_class_counts"))
    d4 = _mapping(aggregate.get("d4_failover"))
    d2 = _mapping(aggregate.get("d2_tracking"))
    lines.extend(
        [
            "",
            "## 专项验收",
            "",
            f"- 1-5 帧 dropout：matrix complete=`{_fmt(dropout.get('matrix_complete'))}`，all compliant=`{_fmt(dropout.get('all_rows_compliant'))}`，identity/plan inconsistent=`{_fmt(dropout.get('identity_plan_inconsistent_count'))}`。",
            f"- `png_ttc`：seed count=`{_fmt(png_ttc.get('seed_count'))}`，area jump=`{_fmt(ttc_counts.get('bbox_area_jump'))}`，bbox clipping=`{_fmt(ttc_counts.get('bbox_clipping'))}`，not expanding=`{_fmt(ttc_counts.get('area_not_expanding'))}`，TTC out-of-range=`{_fmt(ttc_counts.get('ttc_out_of_range'))}`，四类拒绝覆盖 complete=`{_fmt(png_ttc.get('required_reject_coverage_complete'))}`。",
            f"- trend coast：candidate triggered=`{_fmt(trend.get('candidate_trigger_count'))}`，wrong binding=`{_fmt(trend.get('candidate_wrong_binding_count'))}`，promotion recommended=`{_fmt(trend.get('promotion_recommended'))}`。",
            f"- D4 failover：passed/scenarios=`{_fmt(d4.get('passed_count'))}/{_fmt(d4.get('scenario_count'))}`，false degradation=`{_fmt(d4.get('false_degradation_count'))}`。",
            f"- D2 long replay：seed count=`{_fmt(d2.get('seed_count'))}`，IDSW sum=`{_fmt(_mapping(d2.get('id_switch_count')).get('sum'))}`，continuity mean=`{_fmt(_mapping(d2.get('track_continuity')).get('mean'))}`。",
            "",
            "## 解释边界",
            "",
            "- pair、target、coalition 使用独立分母，三者不能互相替代。",
            "- `contract_allowed`、`control_allowed`、`mode_switched`、`physical_intercept` 是四个独立证据层。",
            "- D2 的 `id_switch_count` 始终显式保留；online truth 只允许用于离线评分 sidecar。",
            "- 本报告中的 D1-D4 合成 replay 只证明接口和回归矩阵可运行，不等价于真实 AirSim 多 seed 闭合。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_overview_plot(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(9.0, 7.0))
    main_rows = [
        row
        for row in rows
        if row.get("source") == "main_terminal_closure"
        and row.get("family") == "m5n2_paired"
    ]
    profiles = sorted({str(row.get("profile")) for row in main_rows if row.get("profile")})
    labels: list[str] = []
    pair_rates: list[float] = []
    target_rates: list[float] = []
    coalition_rates: list[float] = []
    for profile in profiles:
        selected = [row for row in main_rows if str(row.get("profile")) == profile]
        labels.append(profile)
        pair_rates.append(_rate_or_nan(selected, "pair_opportunity_count", "pair_success_count"))
        target_rates.append(_rate_or_nan(selected, "target_opportunity_count", "target_success_count"))
        coalition_rates.append(
            _rate_or_nan(
                selected, "coalition_opportunity_count", "coalition_completion_count"
            )
        )
    if labels:
        positions = list(range(len(labels)))
        axes[0].bar([value - 0.25 for value in positions], pair_rates, 0.25, label="pair")
        axes[0].bar(positions, target_rates, 0.25, label="target")
        axes[0].bar(
            [value + 0.25 for value in positions],
            coalition_rates,
            0.25,
            label="coalition",
        )
        axes[0].set_xticks(positions, labels, rotation=15, ha="right")
        axes[0].set_ylim(0.0, 1.05)
        axes[0].legend()
    else:
        axes[0].text(0.5, 0.5, "M5N2 evidence unavailable", ha="center", va="center")
        axes[0].set_xticks([])
    axes[0].set_title("M5N2 physical outcomes by profile")
    axes[0].set_ylabel("success rate")

    d2_rows = sorted(
        (row for row in rows if row.get("source") == "d2_long_replay"),
        key=lambda row: int(row.get("seed") or 0),
    )
    if d2_rows:
        seeds = [int(row["seed"]) for row in d2_rows]
        idsw = [float(row["id_switch_count"]) for row in d2_rows]
        axes[1].plot(seeds, idsw, marker="o", label="IDSW")
        axes[1].set_xlabel("seed")
        axes[1].set_ylabel("ID switch count")
        twin = axes[1].twinx()
        continuity = [
            float(row["track_continuity"])
            if row.get("track_continuity") is not None
            else float("nan")
            for row in d2_rows
        ]
        twin.plot(seeds, continuity, color="tab:orange", marker="s", label="continuity")
        twin.set_ylim(0.0, 1.05)
        twin.set_ylabel("track continuity")
    else:
        axes[1].text(0.5, 0.5, "D2 replay evidence unavailable", ha="center", va="center")
        axes[1].set_xticks([])
    axes[1].set_title("D2 ID continuity across seeds")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def _rate_or_nan(
    rows: Sequence[Mapping[str, Any]], opportunity: str, success: str
) -> float:
    opportunity_values = [float(row[opportunity]) for row in rows if row.get(opportunity) is not None]
    success_values = [float(row[success]) for row in rows if row.get(success) is not None]
    if not opportunity_values or not success_values or sum(opportunity_values) <= 0.0:
        return float("nan")
    return sum(success_values) / sum(opportunity_values)


def _source_schema_version(payload: Mapping[str, Any]) -> str | None:
    for name in (
        "schema_version",
        "schema",
        "calibration_suite_version",
        "matrix_version",
        "profile_version",
        "boundary",
    ):
        if payload.get(name) is not None:
            return str(payload[name])
    return None


def _nested_metric(item: Mapping[str, Any], name: str, key: str) -> Any:
    return _mapping(item.get(name)).get(key)


def _first_present(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if item.get(name) is not None:
            return item[name]
    return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _state_count(item: Mapping[str, Any], state: str) -> Any:
    return _mapping(item.get("state_counts")).get(state)


def _subtract_or_none(left: Any, right: Any) -> int | None:
    if left is None or right is None:
        return None
    return max(0, int(left) - int(right))


def _sum_present(rows: Sequence[Mapping[str, Any]], name: str) -> int | None:
    values = [row.get(name) for row in rows if row.get(name) is not None]
    return sum(int(value) for value in values) if values else None


def _mean_present(rows: Sequence[Mapping[str, Any]], name: str) -> float | None:
    values = [float(row[name]) for row in rows if row.get(name) is not None]
    return sum(values) / len(values) if values else None


def _ready_value(item: Mapping[str, Any]) -> bool | None:
    if item.get("ready") is not None:
        return bool(item["ready"])
    if "missing_required_fields" in item:
        return not bool(item.get("missing_required_fields"))
    return None


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "NA"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    return value
