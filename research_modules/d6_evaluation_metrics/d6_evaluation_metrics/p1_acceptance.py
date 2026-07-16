"""Offline, availability-aware aggregation for the P1 closure evidence bundle."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, is_dataclass
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

from .p1_system_evidence import summarize_d3_canonical_history
from .stage_timing import (
    SINGLE_EPISODE_TIMING_MODE,
    StageTimingInputs,
    evaluate_stage_timing_inputs,
)
from .terminal_closure_evidence import summarize_terminal_closure_case_evidence

P1_ACCEPTANCE_SCHEMA_VERSION = "d6-p1-unified-acceptance-v6"
TERMINAL_METRIC_ENVELOPE_SCHEMA_VERSION = "d6-terminal-metric-envelope-v1"

SOURCE_NAMES = (
    "main_terminal_closure",
    "d1_long_replay",
    "d2_long_replay",
    "d3_assignment_calibration",
    "d3_plan_history",
    "d4_failover_matrix",
    "d5_visual_calibration",
    "d7_terminal_execution",
    "d7_locked_dropout",
    "d7_png_ttc",
    "d7_trend_coast",
)

TERMINAL_METRIC_LAYERS = {
    "contract_allowed_count": "contract",
    "control_allowed_count": "control",
    "terminal_switch_allowed_count": "terminal_switch",
    "mode_switched_count": "mode",
    "physical_intercept_count": "physical",
}

TERMINAL_METRIC_FIELDS = (
    "schema",
    "source",
    "source_schema_version",
    "family",
    "profile",
    "scenario_id",
    "seed",
    "resource_count",
    "target_count",
    "metric_name",
    "layer",
    "value",
    "producer",
    "metric_scope",
    "denominator",
    "lifecycle",
    "status",
    "unavailable_reason",
    "evidence_path",
    "evidence_role",
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
    "loop_latency_ms",
    "performance_budget_violation_count",
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
    "producer",
    "metric_scope",
    "denominator",
    "lifecycle",
    "performance_sample_count",
    "performance_availability_reason",
    "plan_id",
    "plan_version",
    "d3_history_status",
    "d3_history_record_count",
    "d3_history_validation_reasons",
    "primary_membership",
    "reserve_membership",
    "owner",
    "feedback_churn",
    "evidence_path",
    "evidence_role",
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
    d3_plan_history: Any | None = None
    d4_failover_matrix: Any | None = None
    d5_visual_calibration: Any | None = None
    d7_terminal_execution: Any | None = None
    d7_locked_dropout: Any | None = None
    d7_png_ttc: Any | None = None
    d7_trend_coast: Any | None = None
    main_stage_timings: str | Path | None = None
    control_tick_stage_timings: str | Path | None = None
    stage_timing_input_mode: str = SINGLE_EPISODE_TIMING_MODE


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
        main_summary_path = (
            str(inputs.main_terminal_closure)
            if isinstance(inputs.main_terminal_closure, (str, Path))
            else None
        )
        case_evidence = summarize_terminal_closure_case_evidence(
            payloads.get("main_terminal_closure"),
            main_summary_path=main_summary_path,
        )
        source_manifest = _with_case_evidence_manifest(
            source_manifest,
            case_evidence,
            explicit_d3="d3_plan_history" in payloads,
            explicit_d7="d7_terminal_execution" in payloads,
        )
        rows = _normalize_rows(payloads, source_manifest)
        terminal_metric_rows = _normalize_terminal_metric_rows(
            payloads, source_manifest, case_evidence
        )
        aggregate = _build_aggregate(
            payloads,
            source_manifest,
            rows,
            terminal_metric_rows,
            case_evidence,
        )
        aggregate["stage_timing"] = evaluate_stage_timing_inputs(
            StageTimingInputs(
                main_bus=inputs.main_stage_timings,
                control_tick=inputs.control_tick_stage_timings,
                input_mode=inputs.stage_timing_input_mode,
            )
        )

        csv_path = output_dir / "p1_acceptance_per_seed.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=ROW_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(_csv_ready(row) for row in rows)

        seed_json_path = output_dir / "p1_acceptance_per_seed.json"
        seed_json_path.write_text(
            json.dumps(
                {
                    "schema_version": P1_ACCEPTANCE_SCHEMA_VERSION,
                    "rows": rows,
                    "terminal_metric_rows": terminal_metric_rows,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        terminal_csv_path = output_dir / "p1_acceptance_terminal_metrics.csv"
        with terminal_csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=TERMINAL_METRIC_FIELDS,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(_csv_ready(row) for row in terminal_metric_rows)

        json_path = output_dir / "p1_acceptance_aggregate.json"
        json_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        aggregate_csv_path = output_dir / "p1_acceptance_aggregate.csv"
        aggregate_csv_rows = _aggregate_csv_rows(aggregate)
        with aggregate_csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=(
                    "record_type",
                    "source",
                    "case_id",
                    "seed",
                    "layer",
                    "metric_name",
                    "producer",
                    "metric_scope",
                    "lifecycle",
                    "status",
                    "available_count",
                    "unavailable_count",
                    "value_sum",
                    "denominator_sum",
                    "mean",
                    "sample_count",
                    "mean_age_s",
                    "p95_age_s",
                    "max_age_s",
                    "stale_count",
                    "stale_rate",
                    "source_distribution",
                    "metric_availability",
                    "semantics",
                    "reason",
                    "evidence_path",
                ),
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(_csv_ready(row) for row in aggregate_csv_rows)

        plot_path = output_dir / "p1_acceptance_overview.png"
        _write_overview_plot(rows, plot_path)

        markdown_path = output_dir / "P1_UNIFIED_ACCEPTANCE_REPORT.md"
        markdown_path.write_text(
            _render_markdown(aggregate, title=title, plot_name=plot_path.name),
            encoding="utf-8",
        )
        return {
            "per_seed_csv": csv_path,
            "per_seed_json": seed_json_path,
            "terminal_metrics_csv": terminal_csv_path,
            "aggregate_json": json_path,
            "aggregate_csv": aggregate_csv_path,
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


def _with_case_evidence_manifest(
    manifest: Mapping[str, Mapping[str, Any]],
    case_evidence: Mapping[str, Mapping[str, Any]],
    *,
    explicit_d3: bool,
    explicit_d7: bool,
) -> dict[str, dict[str, Any]]:
    enriched = {name: dict(item) for name, item in manifest.items()}
    for source_name, explicit in (
        ("d3_plan_history", explicit_d3),
        ("d7_terminal_execution", explicit_d7),
    ):
        summary = _mapping(case_evidence.get(source_name))
        if explicit or not summary.get("case_count"):
            continue
        reason_counts = _mapping(summary.get("validation_reason_counts"))
        if source_name == "d7_terminal_execution":
            reason_counts = {
                **_mapping(summary.get("wiring_reason_counts")),
                **reason_counts,
            }
        enriched[source_name] = {
            "status": summary.get("status", "unavailable"),
            "schema_version": summary.get("schema"),
            "evidence_path": (
                "main_terminal_closure.rows[*]."
                + (
                    "d3_plan_history"
                    if source_name == "d3_plan_history"
                    else "d7_execution_metrics"
                )
            ),
            "reason": (
                None
                if summary.get("status") == "available"
                else _reason_count_text(reason_counts)
            ),
        }
    return enriched


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
    if payload := payloads.get("d3_plan_history"):
        summary = summarize_d3_canonical_history(payload)
        latest_plan = _mapping(summary.get("latest_plan"))
        rows.append(
            _finish_row(
                {
                    "source": "d3_plan_history",
                    "family": "canonical_plan_history",
                    "scenario_id": summary.get("scenario_name"),
                    "seed": summary.get("seed"),
                    "plan_id": latest_plan.get("plan_id"),
                    "plan_version": latest_plan.get("plan_version"),
                    "d3_history_status": summary.get("status"),
                    "d3_history_record_count": summary.get("record_count"),
                    "d3_history_validation_reasons": summary.get(
                        "validation_reasons"
                    ),
                    "primary_membership": summary.get("primary_membership"),
                    "reserve_membership": summary.get("reserve_membership"),
                    "owner": summary.get("owner"),
                    "feedback_churn": _mapping(summary.get("churn")).get(
                        "feedback_churn_count"
                    ),
                },
                manifest["d3_plan_history"],
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
    if payload := payloads.get("d7_terminal_execution"):
        for item in _terminal_source_rows(payload):
            rows.append(
                _main_row(
                    item,
                    manifest["d7_terminal_execution"],
                    source_name="d7_terminal_execution",
                )
            )
    _append_d7_rows(rows, payloads, manifest)
    return rows


def _main_row(
    item: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    source_name: str = "main_terminal_closure",
) -> dict[str, Any]:
    # The five layers deliberately use only like-named evidence. No terminal
    # switch or pair success value is promoted into another layer. Bare legacy
    # scalars are retained only as unavailable audit records in the dedicated
    # terminal metric CSV.
    performance = _performance_values(item)
    physical = _physical_outcome_values(item)
    context = _mapping(item.get("physical_metric_context"))
    return _finish_row(
        {
            "source": source_name,
            "family": item.get("family"),
            "profile": item.get("profile"),
            "scenario_id": item.get("case_id") or item.get("scenario_id"),
            "seed": item.get("seed"),
            "resource_count": item.get("resource_count"),
            "target_count": item.get("target_count"),
            "dropout_frames": item.get("dropout_frames"),
            "contract_allowed_count": _strict_terminal_metric_value(
                item, "contract_allowed_count"
            ),
            "control_allowed_count": _strict_terminal_metric_value(
                item, "control_allowed_count"
            ),
            "mode_switched_count": _strict_terminal_metric_value(
                item, "mode_switched_count"
            ),
            "physical_intercept_count": _strict_terminal_metric_value(
                item, "physical_intercept_count"
            ),
            "pair_opportunity_count": physical["pair_opportunity_count"],
            "pair_success_count": physical["pair_success_count"],
            "target_opportunity_count": physical["target_opportunity_count"],
            "target_success_count": physical["target_success_count"],
            "coalition_opportunity_count": physical[
                "coalition_opportunity_count"
            ],
            "coalition_completion_count": physical[
                "coalition_completion_count"
            ],
            "terminal_switch_allowed_count": _strict_terminal_metric_value(
                item, "terminal_switch_allowed_count"
            ),
            "terminal_prediction_count": item.get("terminal_prediction_count"),
            "terminal_delivery_expired_count": item.get("terminal_delivery_expired_count"),
            "terminal_trend_coast_count": item.get("terminal_trend_coast_count"),
            "ttc_area_jump_reject_count": item.get("ttc_area_jump_reject_count"),
            "ttc_bbox_clipping_reject_count": item.get("ttc_bbox_clipping_reject_count"),
            "ttc_not_expanding_reject_count": item.get("ttc_not_expanding_reject_count"),
            "ttc_out_of_range_reject_count": item.get("ttc_out_of_range_reject_count"),
            "online_truth_use_count": item.get("online_truth_use_count"),
            "wrong_binding_count": item.get("wrong_binding_count"),
            "command_discontinuity_rate": item.get("command_discontinuity_rate"),
            "physical_success_rate": item.get("physical_success_rate"),
            "producer": context.get("producer"),
            "metric_scope": context.get("metric_scope"),
            "denominator": {
                "pair": physical["pair_opportunity_count"],
                "target": physical["target_opportunity_count"],
                "coalition": physical["coalition_opportunity_count"],
            },
            "lifecycle": context.get("lifecycle"),
            "performance_sample_count": performance["sample_count"],
            "performance_availability_reason": performance["reason"],
            "loop_latency_ms": performance["loop_latency_ms"],
            "performance_budget_violation_count": performance[
                "performance_budget_violation_count"
            ],
            "evidence_path": item.get("control_commands") or item.get("intercept_summary"),
        },
        source,
    )


def _normalize_terminal_metric_rows(
    payloads: Mapping[str, Mapping[str, Any]],
    manifest: Mapping[str, Mapping[str, Any]],
    case_evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_name in (
        "main_terminal_closure",
        "d7_terminal_execution",
        "d7_locked_dropout",
        "d7_trend_coast",
    ):
        payload = payloads.get(source_name)
        if not payload:
            continue
        for item in _terminal_source_rows(payload):
            context = {
                "source": source_name,
                "source_schema_version": manifest[source_name].get(
                    "schema_version"
                ),
                "family": item.get("family"),
                "profile": item.get("profile"),
                "scenario_id": item.get("case_id") or item.get("scenario_id"),
                "seed": item.get("seed"),
                "resource_count": item.get("resource_count"),
                "target_count": item.get("target_count"),
                "evidence_path": (
                    item.get("control_commands")
                    or item.get("intercept_summary")
                    or manifest[source_name].get("evidence_path")
                ),
                "evidence_role": "diagnostic",
            }
            for raw in _terminal_envelopes_from_item(item):
                normalized = _normalize_terminal_metric_envelope(
                    raw,
                    context=context,
                )
                if normalized["status"] == "available":
                    normalized["status"] = "diagnostic"
                    normalized["unavailable_reason"] = (
                        "legacy_or_noncanonical_terminal_metric_diagnostic_only"
                    )
                rows.append(normalized)
    rows.extend(_canonical_actual_terminal_metric_rows(case_evidence))
    return rows


def _canonical_actual_terminal_metric_rows(
    case_evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    suite = _mapping(case_evidence.get("d7_terminal_execution"))
    rows: list[dict[str, Any]] = []
    for case in _mapping_rows(suite.get("by_case_seed")):
        if case.get("status") != "available":
            continue
        metrics = _mapping(case.get("metrics"))
        denominators = {
            "contract_allowed_count": metrics.get("contract_evaluated_count"),
            "control_allowed_count": metrics.get("control_evaluated_count"),
            "terminal_switch_allowed_count": metrics.get(
                "control_evaluated_count"
            ),
            "mode_switched_count": metrics.get("control_evaluated_count"),
            "physical_intercept_count": None,
        }
        context = {
            "source": "d7_terminal_execution",
            "source_schema_version": case.get("detected_payload_schema"),
            "family": case.get("family"),
            "profile": case.get("profile"),
            "scenario_id": case.get("case_id"),
            "seed": case.get("seed"),
            "resource_count": case.get("resource_count"),
            "target_count": case.get("target_count"),
            "evidence_path": case.get("evidence_path"),
            "evidence_role": "canonical_actual_execution",
        }
        for metric_name, denominator in denominators.items():
            rows.append(
                _normalize_terminal_metric_envelope(
                    {
                        "metric_name": metric_name,
                        "value": metrics.get(metric_name),
                        "producer": "main_airsim_runtime",
                        "metric_scope": "actual_execution",
                        "denominator": denominator,
                        "count_only": denominator is None,
                        "lifecycle": "post_simpleflight_control",
                    },
                    context=context,
                )
            )
    return rows


def _terminal_source_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    for name in (
        "rows",
        "summaries",
        "pair_diagnostics",
        "pairs",
        "records",
        "per_seed",
    ):
        rows = _mapping_rows(payload.get(name))
        if rows:
            return rows
    if any(
        name in payload
        for name in (
            *TERMINAL_METRIC_LAYERS,
            "terminal_metrics",
            "terminal_metric_envelopes",
        )
    ):
        return [dict(payload)]
    return []


def _terminal_envelopes_from_item(item: Mapping[str, Any]) -> list[dict[str, Any]]:
    envelopes: list[dict[str, Any]] = []
    explicit_names: set[str] = set()
    for raw in _mapping_rows(item.get("terminal_metrics")):
        name = raw.get("metric_name") or raw.get("name")
        if name is not None:
            explicit_names.add(str(name))
        envelopes.append(raw)
    for name, raw in _mapping(item.get("terminal_metric_envelopes")).items():
        envelope = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
        envelope.setdefault("metric_name", str(name))
        explicit_names.add(str(name))
        envelopes.append(envelope)

    shared = _mapping(item.get("terminal_metric_context"))
    denominators = _mapping(
        item.get("terminal_metric_denominators") or shared.get("denominators")
    )
    for name in TERMINAL_METRIC_LAYERS:
        if name not in item or name in explicit_names:
            continue
        denominator = denominators.get(name)
        if denominator is None:
            denominator = shared.get("denominator", item.get("denominator"))
        envelopes.append(
            {
                "metric_name": name,
                "value": item.get(name),
                "producer": shared.get("producer", item.get("producer")),
                "metric_scope": shared.get(
                    "metric_scope", item.get("metric_scope")
                ),
                "denominator": denominator,
                "lifecycle": shared.get("lifecycle", item.get("lifecycle")),
                "layer": TERMINAL_METRIC_LAYERS[name],
            }
        )
    return envelopes


def _normalize_terminal_metric_envelope(
    raw: Mapping[str, Any], *, context: Mapping[str, Any]
) -> dict[str, Any]:
    metric_name = str(raw.get("metric_name") or raw.get("name") or "")
    expected_layer = TERMINAL_METRIC_LAYERS.get(metric_name)
    layer = raw.get("layer") or expected_layer
    producer = _text_or_none(raw.get("producer"))
    metric_scope = _text_or_none(raw.get("metric_scope"))
    lifecycle = _text_or_none(raw.get("lifecycle"))
    value = _finite_nonnegative_number(raw.get("value"))
    denominator = _finite_nonnegative_number(raw.get("denominator"))
    count_only = raw.get("count_only") is True
    reasons: list[str] = []
    if expected_layer is None:
        reasons.append("unsupported_terminal_metric")
    if raw.get("available") is False:
        reasons.append(str(raw.get("unavailable_reason") or "producer_marked_unavailable"))
    if producer is None:
        reasons.append("producer_missing")
    if metric_scope is None:
        reasons.append("metric_scope_missing")
    if lifecycle is None:
        reasons.append("lifecycle_missing")
    if denominator is None and not count_only:
        reasons.append("denominator_missing_or_invalid")
    elif denominator is not None and denominator <= 0:
        reasons.append("denominator_has_no_samples")
    if value is None:
        reasons.append("metric_value_missing_or_invalid")
    elif denominator is not None and denominator > 0 and value > denominator:
        reasons.append("metric_value_exceeds_denominator")
    if expected_layer is not None and layer != expected_layer:
        reasons.append("terminal_layer_mismatch")
    reasons = list(dict.fromkeys(reasons))
    return {
        "schema": TERMINAL_METRIC_ENVELOPE_SCHEMA_VERSION,
        **context,
        "metric_name": metric_name or None,
        "layer": layer,
        "value": value if not reasons else None,
        "producer": producer,
        "metric_scope": metric_scope,
        "denominator": denominator,
        "lifecycle": lifecycle,
        "status": "available" if not reasons else "unavailable",
        "unavailable_reason": ";".join(reasons) if reasons else None,
        "evidence_role": context.get("evidence_role"),
    }


def _strict_terminal_metric_value(item: Mapping[str, Any], name: str) -> Any:
    normalized = [
        _normalize_terminal_metric_envelope(raw, context={})
        for raw in _terminal_envelopes_from_item(item)
        if str(raw.get("metric_name") or raw.get("name") or "") == name
    ]
    available = [row for row in normalized if row["status"] == "available"]
    return available[0]["value"] if len(available) == 1 else None


def _physical_outcome_values(item: Mapping[str, Any]) -> dict[str, Any]:
    context = _mapping(item.get("physical_metric_context"))
    context_valid = all(
        _text_or_none(context.get(name)) is not None
        for name in ("producer", "metric_scope", "lifecycle")
    )
    values: dict[str, Any] = {}
    for level in ("pair", "target", "coalition"):
        opportunity_name = f"{level}_opportunity_count"
        success_name = (
            "coalition_completion_count"
            if level == "coalition"
            else f"{level}_success_count"
        )
        opportunity = _finite_nonnegative_number(item.get(opportunity_name))
        success = _finite_nonnegative_number(item.get(success_name))
        available = (
            context_valid
            and opportunity is not None
            and opportunity > 0
            and success is not None
            and success <= opportunity
        )
        values[opportunity_name] = opportunity if available else None
        values[success_name] = success if available else None
    return values


def _physical_outcomes_available(item: Mapping[str, Any]) -> bool:
    return any(value is not None for value in _physical_outcome_values(item).values())


def _performance_values(item: Mapping[str, Any]) -> dict[str, Any]:
    performance = _mapping(item.get("performance_metrics")) or dict(item)
    sample_count = _finite_nonnegative_number(
        _first_present(
            performance,
            "sample_count",
            "performance_sample_count",
            "loop_latency_sample_count",
        )
    )
    if sample_count is None or sample_count <= 0:
        return {
            "sample_count": sample_count,
            "loop_latency_ms": None,
            "performance_budget_violation_count": None,
            "reason": "performance_sample_count_missing_or_zero",
        }
    latency = _finite_nonnegative_number(performance.get("loop_latency_ms"))
    violations = _finite_nonnegative_number(
        performance.get("performance_budget_violation_count")
    )
    if violations is not None and violations > sample_count:
        violations = None
    reasons = []
    if latency is None:
        reasons.append("loop_latency_ms_missing_or_invalid")
    if violations is None:
        reasons.append("performance_budget_violation_count_missing_or_invalid")
    return {
        "sample_count": sample_count,
        "loop_latency_ms": latency,
        "performance_budget_violation_count": violations,
        "reason": ";".join(reasons) if reasons else None,
    }


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
    terminal_metric_rows: Sequence[Mapping[str, Any]],
    case_evidence: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    main_rows = [row for row in rows if row.get("source") == "main_terminal_closure"]
    m5n2_rows = [row for row in main_rows if row.get("family") == "m5n2_paired"]
    d2_rows = [row for row in rows if row.get("source") == "d2_long_replay"]
    dropout, png_ttc, trend_coast = _terminal_specialty_summaries(payloads)
    candidate_non_degradation = _candidate_non_degradation_summary(
        m5n2_rows,
        terminal_metric_rows,
        trend_coast,
    )
    trend_coast = _apply_effectiveness_gate(
        trend_coast,
        candidate_non_degradation,
    )
    d7_execution_evidence = _mapping(case_evidence.get("d7_terminal_execution"))
    actual_execution_all_available = d7_execution_evidence.get(
        "actual_execution_all_available"
    )
    main_acceptance_diagnostics = _mapping(
        _mapping(payloads.get("main_terminal_closure")).get("acceptance")
    )
    legacy_gate_has_failure = _contains_explicit_false(main_acceptance_diagnostics)
    required_case_count = int(
        d7_execution_evidence.get("actual_execution_required_case_count") or 0
    )
    overall_acceptance_passed = bool(
        actual_execution_all_available is True and not legacy_gate_has_failure
    )
    acceptance_status = (
        "not_evaluated"
        if required_case_count == 0
        else "pass" if overall_acceptance_passed else "fail"
    )
    return {
        "schema_version": P1_ACCEPTANCE_SCHEMA_VERSION,
        "terminal_metric_envelope_schema": (
            TERMINAL_METRIC_ENVELOPE_SCHEMA_VERSION
        ),
        "offline_only": True,
        "source_manifest": dict(manifest),
        "row_count": len(rows),
        "seed_row_count": sum(row.get("seed") is not None for row in rows),
        "actual_execution_all_available": actual_execution_all_available,
        "overall_acceptance_passed": overall_acceptance_passed,
        "acceptance": {
            "status": acceptance_status,
            "overall_passed": overall_acceptance_passed,
            "actual_execution_all_available": actual_execution_all_available,
            "actual_execution_required_case_count": required_case_count,
            "actual_execution_available_case_count": d7_execution_evidence.get(
                "actual_execution_available_case_count"
            ),
            "actual_execution_unavailable_case_count": d7_execution_evidence.get(
                "actual_execution_unavailable_case_count"
            ),
            "case_availability": d7_execution_evidence.get("by_case_seed", []),
            "legacy_main_acceptance_role": "diagnostic_only",
            "legacy_main_acceptance_has_explicit_failure": legacy_gate_has_failure,
            "legacy_main_acceptance": main_acceptance_diagnostics,
            "offline_physical_outcome_proves_actual_execution_envelope": False,
        },
        "terminal_layers": _terminal_layer_summaries(
            terminal_metric_rows,
            evidence_role="canonical_actual_execution",
            accepted_status="available",
        ),
        "terminal_layer_diagnostics": _terminal_layer_summaries(
            terminal_metric_rows,
            evidence_role="diagnostic",
            accepted_status="diagnostic",
        ),
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
        "candidate_non_degradation": candidate_non_degradation,
        "performance": {
            "loop_latency_ms": _metric_summary(rows, "loop_latency_ms"),
            "performance_budget_violation_count": _metric_summary(
                rows, "performance_budget_violation_count"
            ),
            "availability": {
                "loop_latency_ms": _availability_summary(
                    rows, "loop_latency_ms"
                ),
                "performance_budget_violation_count": _availability_summary(
                    rows, "performance_budget_violation_count"
                ),
            },
        },
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
        "d3_canonical_history": (
            summarize_d3_canonical_history(payloads["d3_plan_history"])
            if "d3_plan_history" in payloads
            else _mapping(case_evidence.get("d3_plan_history"))
        ),
        "d3_canonical_history_cases": _mapping(
            case_evidence.get("d3_plan_history")
        ),
        "d7_execution_evidence": d7_execution_evidence,
        "target_state_freshness": _mapping(
            d7_execution_evidence.get("target_state_freshness")
        ),
        "d4_failover": _mapping(
            _mapping(payloads.get("d4_failover_matrix")).get("summary")
        ),
        "d5_visual": _d5_summary(payloads.get("d5_visual_calibration")),
        "metric_availability": {
            name: _availability_summary(rows, name) for name in METRIC_NAMES
        },
    }


def _terminal_layer_summaries(
    rows: Sequence[Mapping[str, Any]],
    *,
    evidence_role: str,
    accepted_status: str,
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for metric_name, layer in TERMINAL_METRIC_LAYERS.items():
        selected = [
            row
            for row in rows
            if row.get("metric_name") == metric_name
            and row.get("evidence_role") == evidence_role
        ]
        available = [
            row for row in selected if row.get("status") == accepted_status
        ]
        grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
        for row in available:
            key = (
                str(row["source"]),
                str(row["producer"]),
                str(row["metric_scope"]),
                str(row["lifecycle"]),
            )
            grouped.setdefault(key, []).append(row)
        groups = []
        for (source, producer, metric_scope, lifecycle), group_rows in sorted(
            grouped.items()
        ):
            values = [float(row["value"]) for row in group_rows]
            denominators = [
                float(row["denominator"])
                for row in group_rows
                if row.get("denominator") is not None
            ]
            denominator_complete = len(denominators) == len(group_rows)
            denominator_sum = sum(denominators) if denominator_complete else None
            value_sum = sum(values)
            groups.append(
                {
                    "source": source,
                    "producer": producer,
                    "metric_scope": metric_scope,
                    "lifecycle": lifecycle,
                    "available_count": len(group_rows),
                    "value_sum": value_sum,
                    "denominator_sum": denominator_sum,
                    "rate": (
                        value_sum / denominator_sum
                        if denominator_sum is not None and denominator_sum > 0
                        else None
                    ),
                    "mean": value_sum / len(values),
                }
            )
        reason_counts: dict[str, int] = {}
        for row in selected:
            reason = row.get("unavailable_reason")
            if reason:
                reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + 1
        single_group = groups[0] if len(groups) == 1 else None
        summaries[metric_name] = {
            "layer": layer,
            "evidence_role": evidence_role,
            "status": "available" if groups else "unavailable",
            "semantic_group_count": len(groups),
            "available_count": len(available),
            "unavailable_count": len(selected) - len(available),
            "sum": single_group.get("value_sum") if single_group else None,
            "denominator_sum": (
                single_group.get("denominator_sum") if single_group else None
            ),
            "mean": single_group.get("mean") if single_group else None,
            "groups": groups,
            "cross_group_aggregation_prohibited": len(groups) > 1,
            "reason": (
                "multiple producer/scope/lifecycle groups; cross-group sum prohibited"
                if len(groups) > 1
                else None
            ),
            "unavailable_reason_counts": reason_counts,
        }
    return summaries


def _candidate_non_degradation_summary(
    rows: Sequence[Mapping[str, Any]],
    terminal_metric_rows: Sequence[Mapping[str, Any]],
    trend: Mapping[str, Any],
) -> dict[str, Any]:
    paired: list[dict[str, Any]] = []
    by_seed: dict[Any, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        seed = row.get("seed")
        profile = str(row.get("profile") or "")
        if seed is None:
            continue
        role = "baseline" if profile == "baseline" else "candidate" if "candidate" in profile else None
        if role is not None:
            by_seed.setdefault(seed, {})[role] = row
    for seed, profiles in sorted(by_seed.items(), key=lambda pair: str(pair[0])):
        baseline = profiles.get("baseline")
        candidate = profiles.get("candidate")
        if baseline is None or candidate is None:
            continue
        semantic_key = lambda row: (
            row.get("source"),
            row.get("producer"),
            row.get("metric_scope"),
            row.get("lifecycle"),
        )
        if semantic_key(baseline) != semantic_key(candidate):
            continue
        metric_name = next(
            (
                name
                for name in ("target_success_count", "pair_success_count")
                if baseline.get(name) is not None and candidate.get(name) is not None
            ),
            None,
        )
        if metric_name is None:
            continue
        baseline_value = float(baseline[metric_name])
        candidate_value = float(candidate[metric_name])
        paired.append(
            {
                "seed": seed,
                "metric_name": metric_name,
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": candidate_value - baseline_value,
                "producer": baseline.get("producer"),
                "metric_scope": baseline.get("metric_scope"),
                "lifecycle": baseline.get("lifecycle"),
            }
        )

    if not paired:
        paired.extend(_paired_physical_terminal_metrics(terminal_metric_rows))

    baseline_total = sum(row["baseline"] for row in paired) if paired else None
    candidate_total = sum(row["candidate"] for row in paired) if paired else None
    if baseline_total is None and _effectiveness_context_valid(trend):
        baseline_total = _finite_nonnegative_number(
            trend.get("baseline_physical_success_rate")
        )
        candidate_total = _finite_nonnegative_number(
            trend.get("candidate_physical_success_rate")
        )
    trigger_count = _finite_nonnegative_number(trend.get("candidate_trigger_count"))
    non_degradation = (
        None
        if baseline_total is None or candidate_total is None
        else candidate_total >= baseline_total
    )
    if (
        baseline_total is None
        or candidate_total is None
        or trigger_count is None
    ):
        effectiveness_status = "unavailable"
        effectiveness_reason = "effect_or_trigger_evidence_missing"
    elif baseline_total == 0 and candidate_total == 0 and trigger_count == 0:
        effectiveness_status = "inconclusive"
        effectiveness_reason = "baseline_candidate_zero_and_candidate_not_triggered"
    elif trigger_count == 0:
        effectiveness_status = "inconclusive"
        effectiveness_reason = "candidate_mechanism_not_triggered"
    elif candidate_total > baseline_total:
        effectiveness_status = "demonstrated"
        effectiveness_reason = None
    else:
        effectiveness_status = "not_demonstrated"
        effectiveness_reason = "candidate_effect_not_better_than_baseline"
    return {
        "status": (
            "unavailable"
            if non_degradation is None
            else "pass" if non_degradation else "fail"
        ),
        "paired_seed_count": len(paired),
        "paired_rows": paired,
        "baseline_effect": baseline_total,
        "candidate_effect": candidate_total,
        "candidate_trigger_count": trigger_count,
        "effectiveness_evidence": {
            "status": effectiveness_status,
            "reason": effectiveness_reason,
        },
        "promotion_recommended": (
            non_degradation is True and effectiveness_status == "demonstrated"
        ),
    }


def _paired_physical_terminal_metrics(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if row.get("metric_name") == "physical_intercept_count"
        and row.get("status") == "available"
        and row.get("seed") is not None
    ]
    grouped: dict[tuple[Any, str, str, str, str], dict[str, float]] = {}
    for row in selected:
        profile = str(row.get("profile") or "")
        role = "baseline" if profile == "baseline" else "candidate" if "candidate" in profile else None
        if role is None:
            continue
        key = (
            row.get("seed"),
            str(row.get("source")),
            str(row.get("producer")),
            str(row.get("metric_scope")),
            str(row.get("lifecycle")),
        )
        grouped.setdefault(key, {})[role] = float(row["value"])
    return [
        {
            "seed": key[0],
            "metric_name": "physical_intercept_count",
            "source": key[1],
            "producer": key[2],
            "metric_scope": key[3],
            "lifecycle": key[4],
            "baseline": values["baseline"],
            "candidate": values["candidate"],
            "delta": values["candidate"] - values["baseline"],
        }
        for key, values in sorted(grouped.items(), key=lambda pair: str(pair[0]))
        if "baseline" in values and "candidate" in values
    ]


def _apply_effectiveness_gate(
    trend: Mapping[str, Any], comparison: Mapping[str, Any]
) -> dict[str, Any]:
    if not trend:
        return {}
    normalized = dict(trend)
    effectiveness = _mapping(comparison.get("effectiveness_evidence"))
    normalized["effectiveness_evidence"] = effectiveness
    normalized["non_degradation_status"] = comparison.get("status")
    normalized["promotion_recommended"] = bool(
        comparison.get("promotion_recommended")
        and normalized.get("promotion_recommended", True)
    )
    return normalized


def _effectiveness_context_valid(trend: Mapping[str, Any]) -> bool:
    context = _mapping(trend.get("effectiveness_context"))
    return all(
        _text_or_none(context.get(name)) is not None
        for name in ("producer", "metric_scope", "lifecycle")
    ) and (_finite_nonnegative_number(context.get("denominator")) or 0) > 0


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
    available_rows = [
        row
        for row in rows
        if row.get(opportunity_name) is not None
        and float(row[opportunity_name]) > 0
        and row.get(success_name) is not None
    ]
    opportunities = [float(row[opportunity_name]) for row in available_rows]
    successes = [float(row[success_name]) for row in available_rows]
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
            if opportunity_sum is not None
            and opportunity_sum > 0
            and success_sum is not None
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
        "| 来源 | 状态 | Schema | Evidence | Reason |",
        "|---|---|---|---|---|",
    ]
    for name in SOURCE_NAMES:
        item = _mapping(manifest.get(name))
        lines.append(
            f"| `{name}` | {item.get('status', 'unavailable')} | {_fmt(item.get('schema_version'))} | {_fmt(item.get('evidence_path'))} | {_fmt(item.get('reason'))} |"
        )

    acceptance = _mapping(aggregate.get("acceptance"))
    d7_evidence = _mapping(aggregate.get("d7_execution_evidence"))
    lines.extend(
        [
            "",
            "## Actual execution 规范验收门",
            "",
            f"- formal status=`{_fmt(acceptance.get('status'))}`，overall passed=`{_fmt(acceptance.get('overall_passed'))}`，actual execution all available=`{_fmt(acceptance.get('actual_execution_all_available'))}`。",
            f"- required/available/unavailable cases=`{_fmt(acceptance.get('actual_execution_required_case_count'))}/{_fmt(acceptance.get('actual_execution_available_case_count'))}/{_fmt(acceptance.get('actual_execution_unavailable_case_count'))}`。",
            "- 只有校验通过的 `d7-actual-execution-metrics-v2` 能进入正式执行口径。main terminal row 仅作 diagnostics；离线 5 米物理评分可独立报告，但不能证明 actual execution envelope 完整。",
            "",
            "| Case | Seed | Required | Available | Canonical artifact | Evidence | Reasons |",
            "|---|---:|---|---|---|---|---|",
        ]
    )
    for item in _mapping_rows(d7_evidence.get("by_case_seed")):
        lines.append(
            f"| `{_fmt(item.get('case_id'))}` | {_fmt(item.get('seed'))} | {_fmt(item.get('actual_execution_required'))} | {_fmt(item.get('actual_execution_available'))} | {_fmt(item.get('canonical_artifact_kind'))} | {_fmt(item.get('evidence_path'))} | {_fmt(item.get('validation_reasons'))} |"
        )

    freshness = _mapping(aggregate.get("target_state_freshness"))
    freshness_availability = _mapping(freshness.get("metric_availability"))
    lines.extend(
        [
            "",
            "## 目标状态 freshness/stale",
            "",
            "该指标只消费并复算 SHA256 已验证的最终 `control_commands.csv`；任一必需列、数值、时间顺序、age、stale 布尔或 source 非法时，该 case 为 `unavailable`，不补零。",
            "",
            f"- 聚合状态=`{_fmt(freshness.get('status'))}`，availability=`{_fmt(freshness_availability.get('status'))}`，source=`{_fmt(freshness.get('source'))}`，semantics=`{_fmt(freshness.get('semantics'))}`。",
            f"- samples/mean/p95/max age=`{_fmt(freshness.get('sample_count'))}/{_fmt(freshness.get('mean_age_s'))}/{_fmt(freshness.get('p95_age_s'))}/{_fmt(freshness.get('max_age_s'))}` s，stale count/rate=`{_fmt(freshness.get('stale_count'))}/{_fmt(freshness.get('stale_rate'))}`，source distribution=`{_fmt(freshness.get('source_distribution'))}`。",
            "",
            "| Case | Seed | Availability | Samples | Mean age (s) | P95 age (s) | Max age (s) | Stale | Stale rate | Source distribution |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in _mapping_rows(d7_evidence.get("by_case_seed")):
        case_freshness = _mapping(item.get("target_state_freshness"))
        case_availability = _mapping(
            case_freshness.get("metric_availability")
        )
        lines.append(
            f"| `{_fmt(item.get('case_id'))}` | {_fmt(item.get('seed'))} | {_fmt(case_availability.get('status'))} | {_fmt(case_freshness.get('sample_count'))} | {_fmt(case_freshness.get('mean_age_s'))} | {_fmt(case_freshness.get('p95_age_s'))} | {_fmt(case_freshness.get('max_age_s'))} | {_fmt(case_freshness.get('stale_count'))} | {_fmt(case_freshness.get('stale_rate'))} | {_fmt(case_freshness.get('source_distribution'))} |"
        )

    lines.extend(
        [
            "",
            "## 末端五层证据",
            "",
            "| 层级 | 状态 | 语义组 | 可用行 | Sum | Denominator | Mean |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, item in _mapping(aggregate.get("terminal_layers")).items():
        values = _mapping(item)
        lines.append(
            f"| `{name}` | {values.get('status')} | {values.get('semantic_group_count')} | {values.get('available_count')} | {_fmt(values.get('sum'))} | {_fmt(values.get('denominator_sum'))} | {_fmt(values.get('mean'))} |"
        )

    lines.extend(
        [
            "",
            "### Legacy/main diagnostics（不计入正式 actual execution）",
            "",
            "| 层级 | 状态 | 可用诊断行 | Sum | Denominator |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for name, item in _mapping(
        aggregate.get("terminal_layer_diagnostics")
    ).items():
        values = _mapping(item)
        lines.append(
            f"| `{name}` | {values.get('status')} | {values.get('available_count')} | {_fmt(values.get('sum'))} | {_fmt(values.get('denominator_sum'))} |"
        )

    lines.extend(
        [
            "",
            "### 末端指标语义组",
            "",
            "| 指标 | Source | Producer | Scope | Lifecycle | Value | Denominator | Rate |",
            "|---|---|---|---|---|---:|---:|---:|",
        ]
    )
    for name, item in _mapping(aggregate.get("terminal_layers")).items():
        for group in _mapping_rows(_mapping(item).get("groups")):
            lines.append(
                f"| `{name}` | `{group.get('source')}` | `{group.get('producer')}` | `{group.get('metric_scope')}` | `{group.get('lifecycle')}` | {_fmt(group.get('value_sum'))} | {_fmt(group.get('denominator_sum'))} | {_fmt(group.get('rate'))} |"
            )

    lines.extend(
        [
            "",
            "五层只接受同名且 producer/scope/lifecycle 一致的上游证据：D6 不用 contract 推断 control，不用 control 回填 terminal switch，不用 terminal switch 推断 mode switch，也不用 pair success 回填统一 physical intercept。不同语义组的同名指标不比较、不求和、不覆盖。",
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
    candidate = _mapping(aggregate.get("candidate_non_degradation"))
    effectiveness = _mapping(candidate.get("effectiveness_evidence"))
    performance = _mapping(aggregate.get("performance"))
    latency = _mapping(performance.get("loop_latency_ms"))
    budget = _mapping(performance.get("performance_budget_violation_count"))
    d3_cases = _mapping(aggregate.get("d3_canonical_history_cases"))
    stage_timing = _mapping(aggregate.get("stage_timing"))
    timing_layers = _mapping(stage_timing.get("layers"))
    main_timing = _mapping(timing_layers.get("main_bus"))
    control_timing = _mapping(timing_layers.get("control_tick"))
    main_total = _mapping(main_timing.get("total"))
    control_total = _mapping(control_timing.get("total"))
    lines.extend(
        [
            "",
            "## 专项验收",
            "",
            f"- 1-5 帧 dropout：matrix complete=`{_fmt(dropout.get('matrix_complete'))}`，all compliant=`{_fmt(dropout.get('all_rows_compliant'))}`，identity/plan inconsistent=`{_fmt(dropout.get('identity_plan_inconsistent_count'))}`。",
            f"- `png_ttc`：seed count=`{_fmt(png_ttc.get('seed_count'))}`，area jump=`{_fmt(ttc_counts.get('bbox_area_jump'))}`，bbox clipping=`{_fmt(ttc_counts.get('bbox_clipping'))}`，not expanding=`{_fmt(ttc_counts.get('area_not_expanding'))}`，TTC out-of-range=`{_fmt(ttc_counts.get('ttc_out_of_range'))}`，四类拒绝覆盖 complete=`{_fmt(png_ttc.get('required_reject_coverage_complete'))}`。",
            f"- trend coast：candidate triggered=`{_fmt(trend.get('candidate_trigger_count'))}`，wrong binding=`{_fmt(trend.get('candidate_wrong_binding_count'))}`，effectiveness=`{_fmt(_mapping(trend.get('effectiveness_evidence')).get('status'))}`，promotion recommended=`{_fmt(trend.get('promotion_recommended'))}`。",
            f"- candidate non-degradation：status=`{_fmt(candidate.get('status'))}`，baseline/candidate effect=`{_fmt(candidate.get('baseline_effect'))}/{_fmt(candidate.get('candidate_effect'))}`，effectiveness=`{_fmt(effectiveness.get('status'))}`，promotion=`{_fmt(candidate.get('promotion_recommended'))}`。",
            f"- D4 failover：passed/scenarios=`{_fmt(d4.get('passed_count'))}/{_fmt(d4.get('scenario_count'))}`，false degradation=`{_fmt(d4.get('false_degradation_count'))}`。",
            f"- D2 long replay：seed count=`{_fmt(d2.get('seed_count'))}`，IDSW sum=`{_fmt(_mapping(d2.get('id_switch_count')).get('sum'))}`，continuity mean=`{_fmt(_mapping(d2.get('track_continuity')).get('mean'))}`。",
            "",
            "## 性能与可用性",
            "",
            f"- `loop_latency_ms`：status=`{_fmt(latency.get('status'))}`，available/unavailable=`{_fmt(latency.get('available_count'))}/{_fmt(latency.get('unavailable_count'))}`，mean=`{_fmt(latency.get('mean'))}`。",
            f"- `performance_budget_violation_count`：status=`{_fmt(budget.get('status'))}`，available/unavailable=`{_fmt(budget.get('available_count'))}/{_fmt(budget.get('unavailable_count'))}`，sum=`{_fmt(budget.get('sum'))}`。无正样本分母时零值仍为 unavailable。",
            "",
            "### 分阶段延迟证据",
            "",
            f"- 输入模式：`{_fmt(stage_timing.get('input_mode'))}`；case-aware case manifest match=`{_fmt(stage_timing.get('case_manifest_match'))}`；跨 case 总时长=`{_fmt(stage_timing.get('cross_case_total_ms'))}`。",
            f"- `main_bus`：availability=`{_fmt(main_timing.get('availability'))}`，samples=`{_fmt(main_total.get('sample_count'))}`，mean/P95/max=`{_fmt(main_total.get('mean_ms'))}/{_fmt(main_total.get('p95_ms'))}/{_fmt(main_total.get('max_ms'))}` ms，budget violations=`{_fmt(main_timing.get('budget_violation_count'))}`，dominant stage=`{_fmt(main_timing.get('dominant_stage'))}`，reason=`{_fmt(main_timing.get('unavailable_reason'))}`。",
            f"- `control_tick`：availability=`{_fmt(control_timing.get('availability'))}`，samples=`{_fmt(control_total.get('sample_count'))}`，mean/P95/max=`{_fmt(control_total.get('mean_ms'))}/{_fmt(control_total.get('p95_ms'))}/{_fmt(control_total.get('max_ms'))}` ms，budget violations=`{_fmt(control_timing.get('budget_violation_count'))}`，dominant stage=`{_fmt(control_timing.get('dominant_stage'))}`，reason=`{_fmt(control_timing.get('unavailable_reason'))}`。",
            "- main bus 是 control tick 的内部组成部分，两层不相加；case-aware suite 不跨 case 拼接伪连续 episode；旧 artifact 缺 timing 显示 unavailable，不补零。",
            "",
            "## D3 canonical history",
            "",
            f"- suite status=`{_fmt(d3_cases.get('status'))}`，available/unavailable cases=`{_fmt(d3_cases.get('available_case_count'))}/{_fmt(d3_cases.get('unavailable_case_count'))}`，record count sum=`{_fmt(d3_cases.get('record_count'))}`。",
            f"- validation reason counts=`{_fmt(d3_cases.get('validation_reason_counts'))}`。",
            "",
            "| Case | Seed | 状态 | Records | Plan/Version | Owner | Feedback churn | Evidence | Reasons |",
            "|---|---:|---|---:|---|---|---:|---|---|",
        ]
    )
    for item in _mapping_rows(d3_cases.get("by_case_seed")):
        plan = _mapping(item.get("latest_plan"))
        owner = _mapping(item.get("owner"))
        churn = _mapping(item.get("churn"))
        lines.append(
            f"| `{_fmt(item.get('case_id'))}` | {_fmt(item.get('seed'))} | {item.get('status')} | {_fmt(item.get('record_count'))} | {_fmt(plan.get('plan_id'))}/{_fmt(plan.get('plan_version'))} | {_fmt(owner.get('owner_node_id'))} | {_fmt(churn.get('feedback_churn_count'))} | {_fmt(item.get('evidence_path'))} | {_fmt(item.get('validation_reasons'))} |"
        )
    lines.extend(
        [
            "",
            "## D7 execution evidence wiring",
            "",
            f"- status=`{_fmt(d7_evidence.get('status'))}`，available/unavailable cases=`{_fmt(d7_evidence.get('available_case_count'))}/{_fmt(d7_evidence.get('unavailable_case_count'))}`，all paths registered=`{_fmt(d7_evidence.get('all_paths_registered'))}`。",
            f"- wiring reasons=`{_fmt(d7_evidence.get('wiring_reason_counts'))}`；validation reasons=`{_fmt(d7_evidence.get('validation_reason_counts'))}`。缺失路径或结构不匹配不会补零，也不会从相邻目录猜测文件。",
            "",
            "| Case | Seed | 状态 | Wiring | Evidence | Reasons |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for item in _mapping_rows(d7_evidence.get("by_case_seed")):
        lines.append(
            f"| `{_fmt(item.get('case_id'))}` | {_fmt(item.get('seed'))} | {item.get('status')} | {_fmt(item.get('wiring_reason') or item.get('wiring_status'))} | {_fmt(item.get('evidence_path'))} | {_fmt(item.get('validation_reasons'))} |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- pair、target、coalition 使用独立分母，三者不能互相替代。",
            "- `contract_allowed`、`control_allowed`、`terminal_switch_allowed`、`mode_switched`、`physical_intercept` 是五个独立证据层。",
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


def _aggregate_csv_rows(aggregate: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric_name, summary_value in _mapping(
        aggregate.get("terminal_layers")
    ).items():
        summary = _mapping(summary_value)
        groups = _mapping_rows(summary.get("groups"))
        if not groups:
            rows.append(
                {
                    "record_type": "terminal_metric",
                    "layer": summary.get("layer"),
                    "metric_name": metric_name,
                    "status": "unavailable",
                    "available_count": summary.get("available_count"),
                    "unavailable_count": summary.get("unavailable_count"),
                    "reason": summary.get("unavailable_reason_counts"),
                }
            )
            continue
        for group in groups:
            rows.append(
                {
                    "record_type": "terminal_metric",
                    "source": group.get("source"),
                    "layer": summary.get("layer"),
                    "metric_name": metric_name,
                    "producer": group.get("producer"),
                    "metric_scope": group.get("metric_scope"),
                    "lifecycle": group.get("lifecycle"),
                    "status": "available",
                    "available_count": group.get("available_count"),
                    "unavailable_count": summary.get("unavailable_count"),
                    "value_sum": group.get("value_sum"),
                    "denominator_sum": group.get("denominator_sum"),
                    "mean": group.get("mean"),
                }
            )
    for metric_name, summary_value in _mapping(
        aggregate.get("performance")
    ).items():
        if metric_name == "availability":
            continue
        summary = _mapping(summary_value)
        rows.append(
            {
                "record_type": "performance",
                "metric_name": metric_name,
                "status": summary.get("status"),
                "available_count": summary.get("available_count"),
                "unavailable_count": summary.get("unavailable_count"),
                "value_sum": summary.get("sum"),
                "mean": summary.get("mean"),
            }
        )
    candidate = _mapping(aggregate.get("candidate_non_degradation"))
    rows.append(
        {
            "record_type": "candidate_non_degradation",
            "metric_name": "effectiveness_evidence",
            "status": _mapping(candidate.get("effectiveness_evidence")).get(
                "status"
            ),
            "value_sum": candidate.get("candidate_effect"),
            "denominator_sum": candidate.get("baseline_effect"),
            "reason": _mapping(candidate.get("effectiveness_evidence")).get(
                "reason"
            ),
        }
    )
    for source_name, aggregate_name in (
        ("d3_plan_history", "d3_canonical_history_cases"),
        ("d7_terminal_execution", "d7_execution_evidence"),
    ):
        for item in _mapping_rows(
            _mapping(aggregate.get(aggregate_name)).get("by_case_seed")
        ):
            freshness = (
                _mapping(item.get("target_state_freshness"))
                if source_name == "d7_terminal_execution"
                else {}
            )
            rows.append(
                {
                    "record_type": "case_evidence",
                    "source": source_name,
                    "case_id": item.get("case_id"),
                    "seed": item.get("seed"),
                    "status": item.get("status"),
                    "metric_name": (
                        "target_state_freshness" if freshness else None
                    ),
                    "sample_count": freshness.get("sample_count"),
                    "mean_age_s": freshness.get("mean_age_s"),
                    "p95_age_s": freshness.get("p95_age_s"),
                    "max_age_s": freshness.get("max_age_s"),
                    "stale_count": freshness.get("stale_count"),
                    "stale_rate": freshness.get("stale_rate"),
                    "source_distribution": freshness.get(
                        "source_distribution"
                    ),
                    "metric_availability": freshness.get(
                        "metric_availability"
                    ),
                    "semantics": freshness.get("semantics"),
                    "reason": item.get("validation_reasons"),
                    "evidence_path": item.get("evidence_path"),
                }
            )
    freshness = _mapping(aggregate.get("target_state_freshness"))
    rows.append(
        {
            "record_type": "target_state_freshness_aggregate",
            "source": freshness.get("source"),
            "metric_name": "target_state_freshness",
            "status": freshness.get("status"),
            "available_count": freshness.get("available_case_count"),
            "unavailable_count": freshness.get("unavailable_case_count"),
            "sample_count": freshness.get("sample_count"),
            "mean_age_s": freshness.get("mean_age_s"),
            "p95_age_s": freshness.get("p95_age_s"),
            "max_age_s": freshness.get("max_age_s"),
            "stale_count": freshness.get("stale_count"),
            "stale_rate": freshness.get("stale_rate"),
            "source_distribution": freshness.get("source_distribution"),
            "metric_availability": freshness.get("metric_availability"),
            "semantics": freshness.get("semantics"),
        }
    )
    return rows


def _reason_count_text(value: Mapping[str, Any]) -> str | None:
    if not value:
        return None
    return ";".join(f"{name}={count}" for name, count in sorted(value.items()))


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


def _finite_nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        return None
    return normalized


def _text_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _contains_explicit_false(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, Mapping):
        return any(_contains_explicit_false(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_explicit_false(item) for item in value)
    return False


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


def _csv_ready(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (Mapping, list, tuple, set))
            else value
        )
        for key, value in row.items()
    }


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
