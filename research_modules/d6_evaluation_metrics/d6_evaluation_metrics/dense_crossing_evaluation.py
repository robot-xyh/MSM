"""Offline D1/D2 dense-crossing calibration evaluation.

This module consumes persisted evidence only.  It deliberately does not import
D1 or D2 so truth labels and promotion advice cannot enter an online path.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, is_dataclass
import json
import math
from pathlib import Path
import statistics
from typing import Any, Mapping, Sequence


DENSE_CROSSING_EVALUATION_SCHEMA_VERSION = "d6-dense-crossing-evaluation/v1"

METRICS = (
    "id_switch_count",
    "identity_continuity",
    "coverage_continuity",
    "false_track_count",
    "rmse",
    "nis_mean",
    "nees_mean",
    "initialization_latency_s",
    "p95_loop_latency_s",
    "online_truth_leak_count",
)

PER_SEED_FIELDS = (
    "phase",
    "variant_class",
    "variant_id",
    "implementation",
    "implementation_kind",
    "maturity",
    "eligible_for_promotion",
    "exclusion_reason",
    "selected_candidate",
    "seed",
    "scenario_id",
    "scenario_version",
    "target_count",
    *METRICS,
    *(f"{name}_availability" for name in METRICS),
    *(f"{name}_unavailable_reason" for name in METRICS),
)


@dataclass(frozen=True)
class DenseCrossingEvaluationInputs:
    """Versioned D1/D2 files or in-memory summaries.

    ``d2_screening`` is expected to contain at least ten seeds per profile;
    ``d2_confirmation`` is expected to contain at least twenty seeds for the
    baseline and each candidate considered for promotion.
    """

    d1_governed_manifest: Any | None = None
    d1_offline_truth_summary: Any | None = None
    d2_screening: Any | None = None
    d2_confirmation: Any | None = None
    p95_loop_latency_budget_s: float | None = None


class DenseCrossingEvaluationReportGenerator:
    """Create an availability-aware, advisory-only calibration bundle."""

    def write_report_bundle(
        self,
        output_dir: str | Path,
        *,
        inputs: DenseCrossingEvaluationInputs,
        title: str = "D1/D2 密集交叉标定离线评估报告",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        sources, manifest = _load_inputs(inputs)
        rows = []
        rows.extend(_normalize_d2_rows(sources.get("d2_screening"), "screening"))
        rows.extend(
            _normalize_d2_rows(sources.get("d2_confirmation"), "confirmation")
        )
        d1_truth = _d1_truth_isolation_summary(
            sources.get("d1_governed_manifest"),
            sources.get("d1_offline_truth_summary"),
        )
        latency_budget = _resolve_latency_budget(inputs, sources)
        aggregate = _build_aggregate(
            rows,
            source_manifest=manifest,
            d1_truth=d1_truth,
            latency_budget_s=latency_budget,
        )

        csv_path = output_dir / "dense_crossing_per_seed.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=PER_SEED_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

        json_path = output_dir / "dense_crossing_aggregate.json"
        json_path.write_text(
            json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        plot_path = output_dir / "dense_crossing_metrics.png"
        _write_plot(rows, aggregate, plot_path)

        markdown_path = output_dir / "DENSE_CROSSING_CALIBRATION_REPORT.md"
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


def load_dense_crossing_source(source: Any) -> Any:
    """Load JSON/JSONL/CSV or a mapping/dataclass without producer imports."""

    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as stream:
                return {"rows": [dict(row) for row in csv.DictReader(stream)]}
        if suffix in {".jsonl", ".ndjson"}:
            rows = []
            for line_number, text in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not text.strip():
                    continue
                item = json.loads(text)
                if not isinstance(item, Mapping):
                    raise ValueError(f"line {line_number} is not a JSON object")
                rows.append(dict(item))
            return {"rows": rows}
        source = json.loads(path.read_text(encoding="utf-8"))
    elif is_dataclass(source):
        source = asdict(source)
    elif hasattr(source, "to_dict"):
        source = source.to_dict()
    elif hasattr(source, "as_dict"):
        source = source.as_dict()

    if not isinstance(source, (Mapping, Sequence)) or isinstance(
        source, (str, bytes)
    ):
        raise TypeError(f"unsupported dense-crossing source: {type(source)!r}")
    return _json_ready(source)


def _load_inputs(
    inputs: DenseCrossingEvaluationInputs,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    sources: dict[str, Any] = {}
    manifest: dict[str, dict[str, Any]] = {}
    for name in (
        "d1_governed_manifest",
        "d1_offline_truth_summary",
        "d2_screening",
        "d2_confirmation",
    ):
        source = getattr(inputs, name)
        if source is None:
            manifest[name] = {
                "status": "unavailable",
                "schema_version": None,
                "evidence_path": None,
                "reason": "source was not provided",
            }
            continue
        payload = load_dense_crossing_source(source)
        sources[name] = payload
        manifest[name] = {
            "status": "available",
            "schema_version": _schema_version(payload),
            "evidence_path": str(source) if isinstance(source, (str, Path)) else None,
            "reason": None,
        }
    return sources, manifest


def _normalize_d2_rows(payload: Any, phase: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    phase_payloads = [payload]
    if isinstance(payload, Mapping) and isinstance(payload.get(phase), Mapping):
        phase_payloads = [payload[phase]]
        jpda = payload.get("jpda_comparison")
        if isinstance(jpda, Mapping) and isinstance(jpda.get(phase), Mapping):
            phase_payloads.append(jpda[phase])
    raw_rows = []
    for phase_payload in phase_payloads:
        raw_rows.extend(_extract_d2_rows(phase_payload))
    return [_normalize_d2_row(item, phase) for item in raw_rows]


def _extract_d2_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(node: Any, inherited: Mapping[str, Any] | None = None) -> None:
        context = dict(inherited or {})
        if isinstance(node, Mapping):
            configuration = node.get("configuration")
            if isinstance(configuration, Mapping):
                context.update(_context_values(configuration))
            config = node.get("config")
            if isinstance(config, Mapping):
                context.update(_context_values(config))
            context.update(_context_values(node))
            if (
                context.get("best_config_id") is not None
                and context.get("candidate_id") == context.get("best_config_id")
            ):
                context["selected_candidate"] = True

            per_seed = node.get("per_seed")
            if isinstance(per_seed, Sequence) and not isinstance(
                per_seed, (str, bytes)
            ):
                for item in per_seed:
                    if isinstance(item, Mapping):
                        rows.append({**context, **dict(item)})
                return

            traversed = False
            for key in ("runs", "profiles", "candidates", "reports", "rows", "records"):
                child = node.get(key)
                if isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
                    traversed = True
                    for item in child:
                        visit(item, context)
            if traversed:
                return

            results = node.get("results")
            if isinstance(results, Sequence) and not isinstance(results, (str, bytes)):
                for item in results:
                    visit(item, context)
                return

            result = node.get("result")
            if isinstance(result, Mapping):
                visit(result, context)
                return

            if "seed" in node or any(
                key in node
                for key in ("implementation", "algorithm", "online_associator")
            ):
                rows.append({**context, **dict(node)})
            return

        if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            for item in node:
                visit(item, context)

    visit(payload)
    return rows


def _context_values(item: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "algorithm",
        "associator",
        "online_associator",
        "implementation",
        "implementation_kind",
        "framework",
        "comparison_role",
        "profile",
        "profile_name",
        "profile_version",
        "candidate_id",
        "config_id",
        "candidate_rank",
        "best_config_id",
        "selected_candidate",
        "is_baseline",
        "maturity",
        "latency_budget_s",
        "p95_loop_latency_budget_s",
        "scenario_id",
        "scenario_name",
        "scenario_version",
        "target_count",
    )
    result = {key: item[key] for key in keys if key in item}
    if result.get("candidate_id") is None and result.get("config_id") is not None:
        result["candidate_id"] = result["config_id"]
    gate = item.get("gate_profile")
    if isinstance(gate, Mapping):
        result.setdefault("profile_name", gate.get("profile_name"))
        result.setdefault("profile_version", gate.get("profile_version"))
        result.setdefault("gate_threshold", gate.get("mahalanobis_threshold"))
    return result


def _normalize_d2_row(item: Mapping[str, Any], phase: str) -> dict[str, Any]:
    variant_class, maturity, eligible, exclusion_reason = _classify_variant(item)
    variant_id = _variant_id(item, variant_class)
    row: dict[str, Any] = {
        "phase": phase,
        "variant_class": variant_class,
        "variant_id": variant_id,
        "implementation": _first(
            item, "implementation", "algorithm", "online_associator", "associator"
        ),
        "implementation_kind": item.get("implementation_kind"),
        "maturity": maturity,
        "eligible_for_promotion": eligible,
        "exclusion_reason": exclusion_reason,
        "selected_candidate": _bool_or_false(
            _first(item, "selected_candidate", "selected", "is_best_candidate")
        )
        or _integer_or_none(item.get("candidate_rank")) == 1,
        "seed": _number_or_text(item.get("seed")),
        "scenario_id": _first(item, "scenario_id", "scenario_name", "scenario"),
        "scenario_version": item.get("scenario_version"),
        "target_count": _integer_or_none(item.get("target_count")),
    }
    for metric in METRICS:
        value, available, reason = _metric(item, metric)
        row[metric] = value
        row[f"{metric}_availability"] = "available" if available else "unavailable"
        row[f"{metric}_unavailable_reason"] = None if available else reason
    return row


def _classify_variant(item: Mapping[str, Any]) -> tuple[str, str, bool, str | None]:
    text = " ".join(
        str(item.get(key, ""))
        for key in (
            "implementation",
            "implementation_kind",
            "framework",
            "algorithm",
            "associator",
            "online_associator",
            "comparison_role",
            "profile",
            "profile_name",
            "candidate_id",
            "maturity",
        )
    ).lower()
    implementation_kind = str(item.get("implementation_kind", "")).lower()
    end_to_end = item.get("end_to_end_tracker_implemented")
    adapter_smoke = (
        "object_adapter" in text
        or "adapter_smoke" in text
        or "adapter_only" in text
        or (end_to_end is False and any(name in text for name in ("filterpy", "stonesoup")))
    )
    if adapter_smoke:
        return (
            "adapter_smoke",
            "object_adapter_smoke_only",
            False,
            "adapter smoke has no end-to-end identity metrics",
        )
    if "mht" in text:
        return (
            "unsupported_research_variant",
            "research_approximation",
            False,
            "MHT is outside this GNN/JPDA promotion decision",
        )
    if "jpda" in text:
        return "lightweight_jpda", "research_approximation", True, None
    if "gnn" in text or "hungarian" in text:
        baseline = (
            _bool_or_false(item.get("is_baseline"))
            or "baseline" in text
            or str(item.get("comparison_role", "")).lower() == "baseline"
        )
        return (
            "gnn_baseline" if baseline else "gnn_candidate",
            "mainline" if baseline else "candidate_profile",
            True,
            None,
        )
    return (
        "unknown",
        "unclassified",
        False,
        "algorithm maturity or implementation identity is missing",
    )


def _variant_id(item: Mapping[str, Any], variant_class: str) -> str:
    explicit = _first(item, "candidate_id", "variant_id", "profile_id")
    if explicit:
        if variant_class in {
            "lightweight_jpda",
            "adapter_smoke",
            "unsupported_research_variant",
        }:
            return f"{variant_class}:{explicit}"
        return str(explicit)
    profile = _first(item, "profile", "profile_name", "comparison_role")
    version = _first(item, "profile_version", "risk_profile_version")
    gate = item.get("gate_threshold")
    if gate is None and isinstance(item.get("gate_profile"), Mapping):
        gate = item["gate_profile"].get("mahalanobis_threshold")
    parts = [variant_class]
    if profile:
        parts.append(str(profile))
    if version:
        parts.append(str(version))
    if gate is not None:
        parts.append(f"gate-{gate}")
    return ":".join(parts)


def _metric(item: Mapping[str, Any], metric: str) -> tuple[float | int | None, bool, str]:
    aliases = {
        "id_switch_count": ("id_switch_count", "idsw"),
        "identity_continuity": (
            "identity_continuity",
            "track_continuity",
        ),
        "coverage_continuity": ("coverage_continuity",),
        "false_track_count": ("false_track_count",),
        "rmse": ("rmse", "track_rmse"),
        "initialization_latency_s": (
            "mean_initialization_latency_s",
            "initialization_latency_s",
            "init_latency_s",
        ),
        "p95_loop_latency_s": (
            "p95_loop_latency_s",
            "loop_latency_p95_s",
            "p95_latency_s",
            "p95_runtime_per_frame_s",
        ),
        "online_truth_leak_count": (
            "online_truth_leak_count",
            "online_truth_leakage_count",
            "online_truth_isolation_violations",
            "truth_leak_count",
        ),
    }
    if metric in ("nis_mean", "nees_mean"):
        nested_name = metric.split("_", 1)[0]
        nested = item.get(nested_name)
        if isinstance(nested, Mapping):
            available = bool(nested.get("available", False))
            value = _float_or_none(_first(nested, "mean", "value", "average"))
            if available and value is not None:
                return value, True, ""
            return None, False, str(
                nested.get("unavailable_reason")
                or nested.get("reason")
                or f"{nested_name} summary is unavailable"
            )
        value = _float_or_none(item.get(metric))
        if value is not None:
            return value, True, ""
        availability_only = item.get(f"{nested_name}_available")
        if availability_only is True:
            return (
                None,
                False,
                f"{nested_name} availability was provided without a numeric mean",
            )
        return None, False, f"{metric} was not provided"

    value = None
    for name in aliases.get(metric, (metric,)):
        if item.get(name) is not None:
            value = _float_or_none(item.get(name))
            break
    if value is None and metric == "p95_loop_latency_s":
        milliseconds = _float_or_none(
            _first(item, "p95_loop_latency_ms", "loop_latency_p95_ms", "p95_latency_ms")
        )
        value = None if milliseconds is None else milliseconds / 1000.0
    if value is None and metric == "initialization_latency_s":
        milliseconds = _float_or_none(
            _first(item, "mean_initialization_latency_ms", "init_latency_ms")
        )
        value = None if milliseconds is None else milliseconds / 1000.0

    availability = _explicit_metric_availability(item, metric)
    if availability is False:
        return None, False, f"{metric} is explicitly unavailable"
    if metric in (
        "id_switch_count",
        "false_track_count",
        "rmse",
        "online_truth_leak_count",
    ) and item.get("truth_metrics_available") is False:
        return None, False, "offline truth metrics are unavailable"
    if metric in ("identity_continuity", "coverage_continuity") and item.get(
        "continuity_available"
    ) is False:
        return None, False, "continuity metrics are unavailable"
    if value is None:
        return None, False, f"{metric} was not provided"
    if not math.isfinite(value):
        return None, False, f"{metric} is not finite"
    if metric.endswith("count"):
        return int(value), True, ""
    return float(value), True, ""


def _explicit_metric_availability(item: Mapping[str, Any], metric: str) -> bool | None:
    direct = item.get(f"{metric}_available")
    if direct is not None:
        return _bool_or_false(direct)
    availability = item.get("metric_availability")
    if isinstance(availability, Mapping):
        entry = availability.get(metric)
        if isinstance(entry, Mapping):
            status = entry.get("status")
            if status is not None:
                return str(status).lower() == "available"
            if entry.get("available") is not None:
                return _bool_or_false(entry.get("available"))
    return None


def _build_aggregate(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_manifest: Mapping[str, Any],
    d1_truth: Mapping[str, Any],
    latency_budget_s: float | None,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((str(row["phase"]), str(row["variant_id"])), []).append(row)
    groups = [
        _aggregate_group(phase, variant_id, items)
        for (phase, variant_id), items in sorted(grouped.items())
    ]

    best_gnn_id = _select_best_gnn_candidate(groups)
    recommendations = []
    baseline = _confirmation_group(groups, "gnn_baseline")
    for variant_class in ("gnn_candidate", "lightweight_jpda"):
        if variant_class == "gnn_candidate":
            candidate = _group_by_id(groups, "confirmation", best_gnn_id)
            candidate_label = "最佳 GNN candidate"
        else:
            candidate = _best_group(groups, "confirmation", variant_class)
            candidate_label = "轻量 JPDA"
        recommendations.append(
            _promotion_recommendation(
                baseline,
                candidate,
                candidate_label=candidate_label,
                d1_truth=d1_truth,
                latency_budget_s=latency_budget_s,
            )
        )

    excluded = [
        {
            "phase": group["phase"],
            "variant_id": group["variant_id"],
            "variant_class": group["variant_class"],
            "reason": group["exclusion_reasons"],
        }
        for group in groups
        if group["variant_class"] in {"adapter_smoke", "unsupported_research_variant", "unknown"}
    ]
    return {
        "schema_version": DENSE_CROSSING_EVALUATION_SCHEMA_VERSION,
        "advisory_only": True,
        "source_manifest": _json_ready(source_manifest),
        "d1_truth_isolation": _json_ready(d1_truth),
        "latency_budget_s": latency_budget_s,
        "promotion_thresholds": {
            "minimum_screening_seed_count": 10,
            "minimum_confirmation_seed_count": 20,
            "id_switch_relative_reduction_min": 0.30,
            "identity_continuity_absolute_gain_min": 0.10,
            "false_track_relative_increase_max": 0.10,
            "p95_loop_latency_budget_s": latency_budget_s,
            "online_truth_leak_count": 0,
        },
        "row_count": len(rows),
        "groups": groups,
        "best_gnn_candidate_id": best_gnn_id,
        "recommendations": recommendations,
        "excluded_evidence": excluded,
        "failure_reason_distribution": _failure_reason_distribution(
            recommendations, excluded
        ),
    }


def _aggregate_group(
    phase: str, variant_id: str, rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "phase": phase,
        "variant_id": variant_id,
        "variant_class": _single_or_mixed(row["variant_class"] for row in rows),
        "maturity": _single_or_mixed(row["maturity"] for row in rows),
        "seed_count": len({row.get("seed") for row in rows if row.get("seed") is not None}),
        "row_count": len(rows),
        "selected_candidate": any(bool(row.get("selected_candidate")) for row in rows),
        "eligible_for_promotion": all(
            bool(row.get("eligible_for_promotion")) for row in rows
        ),
        "exclusion_reasons": sorted(
            {
                str(row["exclusion_reason"])
                for row in rows
                if row.get("exclusion_reason")
            }
        ),
    }
    for metric in METRICS:
        values = [
            float(row[metric])
            for row in rows
            if row.get(f"{metric}_availability") == "available"
            and row.get(metric) is not None
        ]
        result[metric] = _distribution(values, total_count=len(rows))
    return result


def _select_best_gnn_candidate(groups: Sequence[Mapping[str, Any]]) -> str | None:
    screening = [
        group
        for group in groups
        if group["phase"] == "screening" and group["variant_class"] == "gnn_candidate"
    ]
    if not screening:
        confirmation = [
            group
            for group in groups
            if group["phase"] == "confirmation"
            and group["variant_class"] == "gnn_candidate"
        ]
        screening = confirmation
    explicitly_selected = [group for group in screening if group["selected_candidate"]]
    pool = explicitly_selected or screening
    eligible = [group for group in pool if group["seed_count"] >= (10 if group["phase"] == "screening" else 20)]
    if not eligible:
        return None
    return str(min(eligible, key=_candidate_sort_key)["variant_id"])


def _candidate_sort_key(group: Mapping[str, Any]) -> tuple[float, ...]:
    return (
        _distribution_value(group, "online_truth_leak_count", default=math.inf),
        _distribution_value(group, "id_switch_count", default=math.inf),
        -_distribution_value(group, "identity_continuity", default=-math.inf),
        _distribution_value(group, "false_track_count", default=math.inf),
        _distribution_value(group, "p95_loop_latency_s", key="p95", default=math.inf),
    )


def _promotion_recommendation(
    baseline: Mapping[str, Any] | None,
    candidate: Mapping[str, Any] | None,
    *,
    candidate_label: str,
    d1_truth: Mapping[str, Any],
    latency_budget_s: float | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "candidate_label": candidate_label,
        "baseline_variant_id": None if baseline is None else baseline["variant_id"],
        "candidate_variant_id": None if candidate is None else candidate["variant_id"],
        "status": "unavailable",
        "promote": False,
        "recommendation": "证据不足，保持 GNN/Hungarian 当前主线",
        "checks": {},
        "failure_reasons": [],
    }
    if baseline is None:
        result["failure_reasons"].append("20-seed GNN baseline confirmation missing")
    if candidate is None:
        result["failure_reasons"].append(f"20-seed {candidate_label} confirmation missing")
    if baseline is None or candidate is None:
        return result

    checks: dict[str, dict[str, Any]] = {}
    _seed_check(checks, "baseline_seed_count", baseline, minimum=20)
    _seed_check(checks, "candidate_seed_count", candidate, minimum=20)

    base_idsw = _distribution_value(baseline, "id_switch_count")
    candidate_idsw = _distribution_value(candidate, "id_switch_count")
    if base_idsw is None or candidate_idsw is None:
        checks["id_switch_reduction"] = _unavailable_check("IDSW unavailable")
    elif base_idsw <= 0.0:
        checks["id_switch_reduction"] = {
            "status": "failed",
            "passed": False,
            "value": None,
            "threshold": 0.30,
            "reason": "baseline IDSW is zero; a 30% reduction cannot be demonstrated",
        }
    else:
        reduction = (base_idsw - candidate_idsw) / base_idsw
        checks["id_switch_reduction"] = _check(reduction, 0.30, greater_equal=True)

    base_continuity = _distribution_value(baseline, "identity_continuity")
    candidate_continuity = _distribution_value(candidate, "identity_continuity")
    if base_continuity is None or candidate_continuity is None:
        checks["identity_continuity_gain"] = _unavailable_check(
            "identity continuity unavailable"
        )
    else:
        checks["identity_continuity_gain"] = _check(
            candidate_continuity - base_continuity, 0.10, greater_equal=True
        )

    base_false = _distribution_value(baseline, "false_track_count")
    candidate_false = _distribution_value(candidate, "false_track_count")
    if base_false is None or candidate_false is None:
        checks["false_track_limit"] = _unavailable_check("false track unavailable")
    else:
        limit = base_false * 1.10
        checks["false_track_limit"] = _check(candidate_false, limit, greater_equal=False)

    candidate_latency = _distribution_value(
        candidate, "p95_loop_latency_s", key="p95"
    )
    if latency_budget_s is None:
        checks["p95_loop_latency_budget"] = _unavailable_check(
            "p95 loop latency budget was not provided"
        )
    elif candidate_latency is None:
        checks["p95_loop_latency_budget"] = _unavailable_check(
            "candidate p95 loop latency unavailable"
        )
    else:
        checks["p95_loop_latency_budget"] = _check(
            candidate_latency, latency_budget_s, greater_equal=False
        )

    candidate_truth = candidate["online_truth_leak_count"]
    d1_available = bool(d1_truth.get("available", False))
    d1_leak = d1_truth.get("online_truth_leak_count")
    if not candidate_truth.get("available") or not d1_available:
        checks["truth_isolation"] = _unavailable_check(
            "D1 or D2 online truth leakage evidence unavailable"
        )
    else:
        total_truth_leak = int(round(float(candidate_truth["sum"]))) + int(d1_leak)
        checks["truth_isolation"] = _check(
            float(total_truth_leak), 0.0, greater_equal=False
        )

    result["checks"] = checks
    unavailable = [name for name, check in checks.items() if check["status"] == "unavailable"]
    failed = [name for name, check in checks.items() if check["status"] == "failed"]
    result["failure_reasons"] = unavailable + failed
    if unavailable:
        result["status"] = "unavailable"
    elif failed:
        result["status"] = "failed"
        result["recommendation"] = "未达到晋级门限，保持 GNN/Hungarian 当前主线"
    else:
        result["status"] = "passed"
        result["promote"] = True
        if candidate["variant_class"] == "lightweight_jpda":
            result["recommendation"] = (
                "可晋级隔离候选路径；该实现仍是轻量研究近似，不等于完整 JPDA"
            )
        else:
            result["recommendation"] = "可晋级 GNN 候选参数配置，不改变算法家族"
    return result


def _seed_check(
    checks: dict[str, dict[str, Any]],
    name: str,
    group: Mapping[str, Any],
    *,
    minimum: int,
) -> None:
    checks[name] = _check(float(group["seed_count"]), float(minimum), greater_equal=True)


def _check(value: float, threshold: float, *, greater_equal: bool) -> dict[str, Any]:
    passed = value >= threshold if greater_equal else value <= threshold
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "value": value,
        "threshold": threshold,
        "comparison": ">=" if greater_equal else "<=",
        "reason": None if passed else "threshold not met",
    }


def _unavailable_check(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "passed": False,
        "value": None,
        "threshold": None,
        "reason": reason,
    }


def _d1_truth_isolation_summary(
    manifest: Any | None, offline_truth: Any | None
) -> dict[str, Any]:
    if not isinstance(manifest, Mapping):
        return {
            "available": False,
            "online_truth_leak_count": None,
            "policy": None,
            "offline_truth_available": offline_truth is not None,
            "reason": "D1 governed replay manifest missing",
        }
    metadata = manifest.get("metadata")
    provenance = manifest.get("provenance")
    policy = _first(
        manifest,
        "online_truth_policy",
        "truth_policy",
    )
    if policy is None and isinstance(metadata, Mapping):
        policy = _first(metadata, "online_truth_policy", "truth_policy")
    if policy is None and isinstance(provenance, Mapping):
        policy = _first(provenance, "online_truth_policy", "truth_policy")
        provenance_metadata = provenance.get("metadata")
        if policy is None and isinstance(provenance_metadata, Mapping):
            policy = _first(
                provenance_metadata, "online_truth_policy", "truth_policy"
            )
    leak = _float_or_none(
        _first(
            manifest,
            "online_truth_leak_count",
            "online_truth_leakage_count",
            "online_truth_isolation_violations",
        )
    )
    if leak is None and isinstance(offline_truth, Mapping):
        leak = _float_or_none(
            _first(
                offline_truth,
                "online_truth_leak_count",
                "online_truth_leakage_count",
                "online_truth_isolation_violations",
            )
        )
    policy_safe = str(policy).lower() in {"forbidden", "stripped", "offline_only"}
    offline_available = isinstance(offline_truth, Mapping)
    available = leak is not None or (policy_safe and offline_available)
    return {
        "available": available,
        "online_truth_leak_count": int(leak or 0) if available else None,
        "policy": policy,
        "offline_truth_available": offline_available,
        "offline_truth_schema_version": _schema_version(offline_truth),
        "reason": None
        if available
        else "explicit leak count or safe policy with separate offline truth is missing",
    }


def _resolve_latency_budget(
    inputs: DenseCrossingEvaluationInputs, sources: Mapping[str, Any]
) -> float | None:
    if inputs.p95_loop_latency_budget_s is not None:
        value = float(inputs.p95_loop_latency_budget_s)
        if value <= 0.0 or not math.isfinite(value):
            raise ValueError("p95_loop_latency_budget_s must be positive and finite")
        return value
    for name in ("d2_confirmation", "d2_screening"):
        source = sources.get(name)
        if isinstance(source, Mapping):
            value = _float_or_none(
                _first(source, "p95_loop_latency_budget_s", "latency_budget_s")
            )
            configuration = source.get("configuration")
            if value is None and isinstance(configuration, Mapping):
                value = _float_or_none(
                    _first(
                        configuration,
                        "p95_loop_latency_budget_s",
                        "latency_budget_s",
                    )
                )
            jpda = source.get("jpda_comparison")
            if value is None and isinstance(jpda, Mapping):
                value = _float_or_none(
                    _first(
                        jpda,
                        "same_budget_p95_loop_latency_s",
                        "p95_loop_latency_budget_s",
                    )
                )
            if value is not None and value > 0.0:
                return value
    return None


def _confirmation_group(
    groups: Sequence[Mapping[str, Any]], variant_class: str
) -> Mapping[str, Any] | None:
    return _best_group(groups, "confirmation", variant_class)


def _best_group(
    groups: Sequence[Mapping[str, Any]], phase: str, variant_class: str
) -> Mapping[str, Any] | None:
    matches = [
        group
        for group in groups
        if group["phase"] == phase and group["variant_class"] == variant_class
    ]
    return min(matches, key=_candidate_sort_key) if matches else None


def _group_by_id(
    groups: Sequence[Mapping[str, Any]], phase: str, variant_id: str | None
) -> Mapping[str, Any] | None:
    if variant_id is None:
        return None
    return next(
        (
            group
            for group in groups
            if group["phase"] == phase and group["variant_id"] == variant_id
        ),
        None,
    )


def _distribution(values: Sequence[float], *, total_count: int) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    ordered = sorted(finite)
    return {
        "available": bool(finite),
        "available_seed_count": len(finite),
        "unavailable_seed_count": total_count - len(finite),
        "mean": statistics.fmean(finite) if finite else None,
        "std": statistics.pstdev(finite) if len(finite) > 1 else (0.0 if finite else None),
        "min": min(finite) if finite else None,
        "max": max(finite) if finite else None,
        "p95": _percentile(ordered, 0.95),
        "sum": sum(finite) if finite else None,
    }


def _percentile(ordered: Sequence[float], fraction: float) -> float | None:
    if not ordered:
        return None
    if len(ordered) == 1:
        return float(ordered[0])
    position = fraction * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _distribution_value(
    group: Mapping[str, Any] | None,
    metric: str,
    *,
    key: str = "mean",
    default: float | None = None,
) -> float | None:
    if group is None:
        return default
    distribution = group.get(metric)
    if not isinstance(distribution, Mapping) or not distribution.get("available"):
        return default
    value = _float_or_none(distribution.get(key))
    return default if value is None else value


def _failure_reason_distribution(
    recommendations: Sequence[Mapping[str, Any]], excluded: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for recommendation in recommendations:
        for reason in recommendation.get("failure_reasons", []):
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    for item in excluded:
        reasons = item.get("reason") or ["excluded evidence"]
        for reason in reasons:
            counts[str(reason)] = counts.get(str(reason), 0) + 1
    return dict(sorted(counts.items()))


def _write_plot(
    rows: Sequence[Mapping[str, Any]], aggregate: Mapping[str, Any], path: Path
) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        path.write_bytes(b"")
        return

    selected_ids = {
        recommendation.get("baseline_variant_id")
        for recommendation in aggregate.get("recommendations", [])
    } | {
        recommendation.get("candidate_variant_id")
        for recommendation in aggregate.get("recommendations", [])
    }
    selected_ids.discard(None)
    confirmation = [
        row
        for row in rows
        if row["phase"] == "confirmation" and row["variant_id"] in selected_ids
    ]
    figure, axes = plt.subplots(2, 2, figsize=(11, 7), constrained_layout=True)
    specs = (
        ("id_switch_count", "ID Switch"),
        ("identity_continuity", "Identity continuity"),
        ("false_track_count", "False tracks"),
        ("p95_loop_latency_s", "p95 loop latency (s)"),
    )
    for axis, (metric, label) in zip(axes.flat, specs, strict=True):
        for variant_id in sorted(selected_ids):
            variant_rows = sorted(
                (
                    row
                    for row in confirmation
                    if row["variant_id"] == variant_id
                    and row[f"{metric}_availability"] == "available"
                ),
                key=lambda row: str(row.get("seed")),
            )
            if variant_rows:
                axis.plot(
                    range(len(variant_rows)),
                    [float(row[metric]) for row in variant_rows],
                    marker="o",
                    markersize=2.5,
                    linewidth=1.0,
                    label=str(variant_id),
                )
        axis.set_title(label)
        axis.set_xlabel("confirmation seed index")
        axis.grid(alpha=0.25)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        figure.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=8)
    if not confirmation:
        figure.suptitle("No available 20-seed confirmation evidence")
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _render_markdown(
    aggregate: Mapping[str, Any], *, title: str, plot_name: str
) -> str:
    lines = [f"# {title}", "", "## 结论边界", ""]
    lines.append(
        "本报告仅消费 D1/D2 写盘证据，不参与在线关联或控制。晋级结论只使用 "
        "20-seed confirmation；10-seed screening 只用于选出最佳 GNN 候选。"
    )
    lines.append(
        "轻量 JPDA 始终标记为轻量研究近似；即使通过门限，也不表述为完整 JPDA 实现。"
    )
    lines.extend(["", f"![密集交叉指标曲线]({plot_name})", "", "## 输入证据", ""])
    lines.append("| 来源 | 状态 | schema | 路径/原因 |")
    lines.append("|---|---|---|---|")
    for name, item in aggregate["source_manifest"].items():
        lines.append(
            f"| {name} | {item['status']} | {item.get('schema_version') or 'NA'} | "
            f"{item.get('evidence_path') or item.get('reason') or '-'} |"
        )
    d1 = aggregate["d1_truth_isolation"]
    lines.extend(
        [
            "",
            "## D1 truth 隔离",
            "",
            "| 可用 | 在线泄漏数 | policy | offline truth |",
            "|---:|---:|---|---:|",
            f"| {d1.get('available')} | {d1.get('online_truth_leak_count')} | "
            f"{d1.get('policy') or 'NA'} | {d1.get('offline_truth_available')} |",
            "",
            "## 算法分组",
            "",
            "| 阶段 | 分组 | 类别 | seeds | IDSW | identity continuity | false track | p95 latency |",
            "|---|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for group in aggregate["groups"]:
        lines.append(
            f"| {group['phase']} | {group['variant_id']} | {group['variant_class']} | "
            f"{group['seed_count']} | {_fmt(group['id_switch_count'].get('mean'))} | "
            f"{_fmt(group['identity_continuity'].get('mean'))} | "
            f"{_fmt(group['false_track_count'].get('mean'))} | "
            f"{_fmt(group['p95_loop_latency_s'].get('p95'))} |"
        )
    lines.extend(["", "## 晋级建议", ""])
    for recommendation in aggregate["recommendations"]:
        lines.append(
            f"### {recommendation['candidate_label']}: {recommendation['status']}"
        )
        lines.append("")
        lines.append(recommendation["recommendation"])
        lines.append("")
        lines.append("| 检查项 | 状态 | 数值 | 门限 |")
        lines.append("|---|---|---:|---:|")
        for name, check in recommendation["checks"].items():
            lines.append(
                f"| {name} | {check['status']} | {_fmt(check.get('value'))} | "
                f"{_fmt(check.get('threshold'))} |"
            )
        if recommendation["failure_reasons"]:
            lines.append("")
            lines.append(
                "失败/不可用原因：" + ", ".join(recommendation["failure_reasons"])
            )
        lines.append("")
    lines.extend(["## 排除证据", ""])
    if aggregate["excluded_evidence"]:
        lines.append("| 阶段 | 分组 | 原因 |")
        lines.append("|---|---|---|")
        for item in aggregate["excluded_evidence"]:
            lines.append(
                f"| {item['phase']} | {item['variant_id']} | "
                f"{', '.join(item['reason'])} |"
            )
    else:
        lines.append("无。")
    lines.extend(["", "## 失败原因分布", ""])
    if aggregate["failure_reason_distribution"]:
        for reason, count in aggregate["failure_reason_distribution"].items():
            lines.append(f"- `{reason}`: {count}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def _schema_version(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        value = payload.get("schema_version")
        return None if value is None else str(value)
    return None


def _single_or_mixed(values: Sequence[Any] | Any) -> Any:
    unique = {str(value) for value in values}
    return next(iter(unique)) if len(unique) == 1 else "mixed"


def _first(item: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if item.get(key) is not None:
            return item[key]
    return None


def _bool_or_false(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "available"}
    return bool(value)


def _integer_or_none(value: Any) -> int | None:
    try:
        return None if value is None or value == "" else int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _number_or_text(value: Any) -> Any:
    if value is None:
        return None
    number = _float_or_none(value)
    if number is None:
        return str(value)
    return int(number) if number.is_integer() else number


def _fmt(value: Any) -> str:
    number = _float_or_none(value)
    return "NA" if number is None else f"{number:.4f}"


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
