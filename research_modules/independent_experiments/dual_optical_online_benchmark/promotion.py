"""Hashed, fail-closed route promotion for the target-scale funnel."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ROUTE_NAMES,
    SUPPORTED_TARGET_COUNTS,
    benchmark_protocol_for_target_count,
    benchmark_protocol_from_mapping,
    write_json,
)
from .dataset import sha256_file
from .funnel import decision_payload, evaluate_route_promotion


PROMOTION_SCHEMA = "dual-optical-scale-promotion-v2"
LEGACY_PROMOTION_SCHEMA = "dual-optical-scale-promotion-v1"


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def build_promotion_manifest(
    metrics_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Consume a sealed tier test once and decide which routes may scale up."""

    metrics_path = Path(metrics_path).resolve()
    metrics = _read_json(metrics_path)
    protocol = benchmark_protocol_from_mapping(metrics["protocol"])
    if metrics.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("promotion metrics protocol mismatch")
    if metrics.get("truth_used_online") is not False:
        raise ValueError("promotion metrics do not prove online truth isolation")
    active_routes = tuple(str(value) for value in metrics.get("active_routes", ()))
    if (
        not active_routes
        or len(active_routes) != len(set(active_routes))
        or any(route not in ROUTE_NAMES for route in active_routes)
    ):
        raise ValueError("promotion metrics contain an invalid active-route set")
    rows = list(metrics.get("rows", ()))
    if not rows:
        raise ValueError("promotion metrics contain no scored rows")
    baseline_route = (
        "epipolar_mht" if "epipolar_mht" in active_routes else active_routes[0]
    )
    baseline_rows = [row for row in rows if row.get("route_name") == baseline_route]
    aggregate = metrics.get("aggregate", {}).get("routes", {})
    if baseline_route not in aggregate:
        raise ValueError("promotion metrics lack the deterministic baseline")
    baseline_latency = float(aggregate[baseline_route]["latency_p95_ms"])

    decisions: dict[str, Any] = {}
    eligible: list[str] = []
    eliminated: dict[str, list[str]] = {}
    for route_name in active_routes:
        route_rows = [row for row in rows if row.get("route_name") == route_name]
        if route_name not in aggregate:
            raise ValueError(f"promotion metrics lack aggregate for {route_name}")
        comparison_baseline_route = (
            "gnn"
            if route_name == "track_superglue" and "gnn" in active_routes
            else baseline_route
        )
        comparison_baseline_rows = [
            row
            for row in rows
            if row.get("route_name") == comparison_baseline_route
        ]
        comparison_baseline_latency = float(
            aggregate[comparison_baseline_route]["latency_p95_ms"]
        )
        decision = evaluate_route_promotion(
            route_name=route_name,
            target_count=protocol.target_count,
            candidate_rows=route_rows,
            baseline_rows=comparison_baseline_rows,
            candidate_latency_p95_ms=float(
                aggregate[route_name]["latency_p95_ms"]
            ),
            baseline_latency_p95_ms=comparison_baseline_latency,
            baseline_route_name=comparison_baseline_route,
        )
        decisions[route_name] = decision_payload(decision)
        if decision.eligible:
            eligible.append(route_name)
        else:
            eliminated[route_name] = list(decision.reasons)

    preferred_route: str | None = None
    superglue_decision = decisions.get("track_superglue")
    if (
        "track_superglue" in eligible
        and "gnn" in active_routes
        and isinstance(superglue_decision, Mapping)
        and superglue_decision.get("preferred") is True
    ):
        preferred_route = "track_superglue"
    elif "gnn" in eligible:
        preferred_route = "gnn"
    elif baseline_route in eligible and baseline_route != "track_superglue":
        preferred_route = baseline_route
    elif eligible:
        preferred_route = next(
            (route for route in eligible if route != "track_superglue"), None
        )

    index = SUPPORTED_TARGET_COUNTS.index(protocol.target_count)
    next_target_count = (
        None
        if index == len(SUPPORTED_TARGET_COUNTS) - 1
        else SUPPORTED_TARGET_COUNTS[index + 1]
    )
    next_protocol_fingerprint = (
        None
        if next_target_count is None
        else benchmark_protocol_for_target_count(next_target_count).fingerprint
    )
    payload: dict[str, Any] = {
        "schema_version": PROMOTION_SCHEMA,
        "source_target_count": protocol.target_count,
        "source_protocol_fingerprint": protocol.fingerprint,
        "next_target_count": next_target_count,
        "next_protocol_fingerprint": next_protocol_fingerprint,
        "baseline_route": baseline_route,
        "active_routes": list(active_routes),
        "eligible_routes": eligible,
        # Kept as a read-compatible alias for V1/V3 funnel consumers.
        "promoted_routes": eligible,
        "preferred_route": preferred_route,
        "eliminated_routes": eliminated,
        "decisions": decisions,
        "metrics_path": str(metrics_path),
        "metrics_sha256": sha256_file(metrics_path),
        "reserved_test_used_for_single_promotion_decision": True,
        "reserved_test_used_for_parameter_selection": False,
        "routes_may_not_resurrect": True,
        "promotion_allowed": bool(eligible),
    }
    payload["promotion_fingerprint_sha256"] = _fingerprint(payload)
    path = (
        Path(output_path).resolve()
        if output_path is not None
        else metrics_path.with_name("promotion_manifest.json")
    )
    write_json(path, payload)
    return path


def validate_previous_promotion(
    path: str | Path,
    *,
    requested_target_count: int,
) -> dict[str, Any]:
    """Reject a higher tier unless the immediately prior tier promoted routes."""

    path = Path(path).resolve()
    payload = _read_json(path)
    schema_version = payload.get("schema_version")
    if schema_version not in {PROMOTION_SCHEMA, LEGACY_PROMOTION_SCHEMA}:
        raise ValueError("unsupported scale-promotion schema")
    stored = str(payload.get("promotion_fingerprint_sha256") or "")
    unsigned = dict(payload)
    unsigned.pop("promotion_fingerprint_sha256", None)
    if stored != _fingerprint(unsigned):
        raise ValueError("scale-promotion fingerprint mismatch")
    if int(payload.get("next_target_count") or -1) != int(requested_target_count):
        raise ValueError("promotion does not authorize the requested target scale")
    expected_protocol = benchmark_protocol_for_target_count(requested_target_count)
    if payload.get("next_protocol_fingerprint") != expected_protocol.fingerprint:
        raise ValueError("promotion targets a foreign next-tier protocol")
    promoted = tuple(str(value) for value in payload.get("promoted_routes", ()))
    if (
        not promoted
        or len(promoted) != len(set(promoted))
        or any(route not in ROUTE_NAMES for route in promoted)
    ):
        raise ValueError("previous scale promoted no valid route")
    if schema_version == PROMOTION_SCHEMA:
        eligible = tuple(str(value) for value in payload.get("eligible_routes", ()))
        if eligible != promoted:
            raise ValueError("eligible_routes and promoted_routes compatibility alias differ")
        preferred = payload.get("preferred_route")
        if preferred is not None and str(preferred) not in eligible:
            raise ValueError("preferred route is not eligible")
        active = tuple(str(value) for value in payload.get("active_routes", ()))
        eliminated = payload.get("eliminated_routes", {})
        if not isinstance(eliminated, Mapping):
            raise ValueError("promotion eliminated_routes must be an object")
        if set(active) != set(eligible).union(str(value) for value in eliminated):
            raise ValueError("promotion decisions do not partition active routes")
    metrics_path = Path(str(payload.get("metrics_path") or ""))
    if not metrics_path.is_file() or sha256_file(metrics_path) != payload.get(
        "metrics_sha256"
    ):
        raise ValueError("previous scale metrics hash mismatch")
    return payload


__all__ = [
    "PROMOTION_SCHEMA",
    "LEGACY_PROMOTION_SCHEMA",
    "build_promotion_manifest",
    "validate_previous_promotion",
]
