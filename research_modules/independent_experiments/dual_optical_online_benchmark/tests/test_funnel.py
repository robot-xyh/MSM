from dataclasses import asdict
import json
from pathlib import Path

import pytest

from dual_optical_online_benchmark.funnel import evaluate_route_promotion
from dual_optical_online_benchmark.contracts import (
    benchmark_protocol_for_target_count,
    write_json,
)
from dual_optical_online_benchmark.dataset import sha256_file
from dual_optical_online_benchmark.promotion import (
    LEGACY_PROMOTION_SCHEMA,
    PROMOTION_SCHEMA,
    build_promotion_manifest,
    validate_previous_promotion,
)


def _rows(recall: float, precision: float = 0.9, deadline: bool = True):
    rows = []
    protocol = benchmark_protocol_for_target_count(20)
    for seed in protocol.test_seeds:
        for level in ("medium", "heavy"):
            for revolution in range(1, protocol.revolution_count + 1):
                correct = int(round(recall * 100))
                matches = max(correct, int(round(correct / precision)))
                rows.append({
                    "seed": seed,
                    "corruption_level": level,
                    "revolution_index": revolution,
                    "deadline_met": deadline,
                    "on_time_recall": recall if deadline else 0.0,
                    "match_count": matches,
                    "correct_match_count": correct,
                    "false_association_count": matches - correct,
                    "candidate_true_opportunity_count": 100,
                    "duplicate_identity_match_count": 0,
                    "target_count": 20,
                    "protocol_fingerprint": protocol.fingerprint,
                    "input_fingerprint": f"{seed}-{level}-{revolution}",
                })
    return rows


def test_missing_or_unpaired_noisy_evidence_fails_closed() -> None:
    candidate = _rows(0.80)
    baseline = _rows(0.75)
    candidate.pop()
    with pytest.raises(ValueError, match="complete paired"):
        evaluate_route_promotion(
            route_name="gnn",
            target_count=20,
            candidate_rows=candidate,
            baseline_rows=baseline,
            candidate_latency_p95_ms=700.0,
            baseline_latency_p95_ms=650.0,
        )


def test_next_scale_requires_hashed_immediate_previous_promotion(tmp_path: Path) -> None:
    metrics = tmp_path / "comparison_metrics.json"
    write_json(metrics, {"sealed": True})
    protocol = benchmark_protocol_for_target_count(40)
    payload = {
        "schema_version": PROMOTION_SCHEMA,
        "source_target_count": 20,
        "source_protocol_fingerprint": benchmark_protocol_for_target_count(20).fingerprint,
        "next_target_count": 40,
        "next_protocol_fingerprint": protocol.fingerprint,
        "baseline_route": "epipolar_mht",
        "active_routes": ["epipolar_mht", "gnn"],
        "eligible_routes": ["gnn"],
        "promoted_routes": ["gnn"],
        "preferred_route": "gnn",
        "eliminated_routes": {"epipolar_mht": ["negative"]},
        "decisions": {},
        "metrics_path": str(metrics),
        "metrics_sha256": sha256_file(metrics),
        "reserved_test_used_for_single_promotion_decision": True,
        "reserved_test_used_for_parameter_selection": False,
        "routes_may_not_resurrect": True,
        "promotion_allowed": True,
    }
    import hashlib
    import json

    payload["promotion_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    path = tmp_path / "promotion_manifest.json"
    write_json(path, payload)
    assert validate_previous_promotion(
        path, requested_target_count=40
    )["promoted_routes"] == ["gnn"]

    legacy = dict(payload)
    legacy["schema_version"] = LEGACY_PROMOTION_SCHEMA
    legacy.pop("eligible_routes")
    legacy.pop("preferred_route")
    legacy.pop("promotion_fingerprint_sha256")
    legacy["promotion_fingerprint_sha256"] = hashlib.sha256(
        json.dumps(
            legacy,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    legacy_path = tmp_path / "legacy_promotion_manifest.json"
    write_json(legacy_path, legacy)
    assert validate_previous_promotion(
        legacy_path, requested_target_count=40
    )["promoted_routes"] == ["gnn"]

    payload["promoted_routes"] = []
    write_json(path, payload)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_previous_promotion(path, requested_target_count=40)



def test_promotion_requires_paired_same_input_rows() -> None:
    candidate = _rows(0.80)
    baseline = _rows(0.75)
    candidate[0]["input_fingerprint"] = "foreign"
    with pytest.raises(ValueError, match="same input"):
        evaluate_route_promotion(
            route_name="gnn",
            target_count=20,
            candidate_rows=candidate,
            baseline_rows=baseline,
            candidate_latency_p95_ms=700.0,
            baseline_latency_p95_ms=650.0,
        )


def test_negative_noisy_recall_and_latency_fail_promotion() -> None:
    decision = evaluate_route_promotion(
        route_name="gnn",
        target_count=20,
        candidate_rows=_rows(0.70),
        baseline_rows=_rows(0.75),
        candidate_latency_p95_ms=1200.0,
        baseline_latency_p95_ms=800.0,
    )
    assert not decision.promoted
    assert "medium_heavy_on_time_recall_decreased_2pp" in decision.reasons
    assert "latency_p95_exceeded_1000ms" in decision.reasons


def test_material_recall_gain_with_precision_and_latency_promotes() -> None:
    decision = evaluate_route_promotion(
        route_name="lightweight",
        target_count=20,
        candidate_rows=_rows(0.82, 0.91),
        baseline_rows=_rows(0.70, 0.90),
        candidate_latency_p95_ms=700.0,
        baseline_latency_p95_ms=650.0,
    )
    assert decision.promoted


def test_superglue_can_be_eligible_without_becoming_preferred() -> None:
    decision = evaluate_route_promotion(
        route_name="track_superglue",
        target_count=20,
        candidate_rows=_rows(0.76, 0.90),
        baseline_rows=_rows(0.75, 0.90),
        candidate_latency_p95_ms=750.0,
        baseline_latency_p95_ms=700.0,
        baseline_route_name="gnn",
    )
    assert decision.eligible
    assert decision.promoted
    assert not decision.preferred
    assert "superglue_recall_gain_below_2pp" in decision.preference_reasons


def test_superglue_preference_requires_gain_ci_and_false_rate_gate() -> None:
    decision = evaluate_route_promotion(
        route_name="track_superglue",
        target_count=20,
        candidate_rows=_rows(0.80, 1.0),
        baseline_rows=_rows(0.75, 1.0),
        candidate_latency_p95_ms=750.0,
        baseline_latency_p95_ms=700.0,
        baseline_route_name="gnn",
    )
    assert decision.eligible
    assert decision.preferred
    assert decision.comparison_baseline_route == "gnn"


def test_absolute_recall_floor_blocks_route() -> None:
    decision = evaluate_route_promotion(
        route_name="gnn",
        target_count=20,
        candidate_rows=_rows(0.24, 0.90),
        baseline_rows=_rows(0.24, 0.90),
        candidate_latency_p95_ms=500.0,
        baseline_latency_p95_ms=500.0,
    )
    assert not decision.eligible
    assert "absolute_on_time_recall_below_0_25" in decision.reasons


def test_manifest_keeps_safe_superglue_but_gnn_stays_preferred(tmp_path: Path) -> None:
    protocol = benchmark_protocol_for_target_count(20)
    rows = []
    for route, recall in (("gnn", 0.75), ("track_superglue", 0.76)):
        for row in _rows(recall, 1.0):
            rows.append({**row, "route_name": route})
    metrics = tmp_path / "comparison_metrics.json"
    write_json(
        metrics,
        {
            "protocol": asdict(protocol),
            "protocol_fingerprint": protocol.fingerprint,
            "truth_used_online": False,
            "active_routes": ["gnn", "track_superglue"],
            "rows": rows,
            "aggregate": {
                "routes": {
                    "gnn": {"latency_p95_ms": 700.0},
                    "track_superglue": {"latency_p95_ms": 750.0},
                }
            },
        },
    )
    manifest_path = build_promotion_manifest(metrics)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["eligible_routes"] == ["gnn", "track_superglue"]
    assert payload["promoted_routes"] == payload["eligible_routes"]
    assert payload["preferred_route"] == "gnn"


def test_superglue_cannot_be_preferred_without_same_input_gnn(tmp_path: Path) -> None:
    protocol = benchmark_protocol_for_target_count(20)
    rows = [
        {**row, "route_name": "track_superglue"}
        for row in _rows(0.75, 1.0)
    ]
    metrics = tmp_path / "comparison_metrics_only_superglue.json"
    write_json(
        metrics,
        {
            "protocol": asdict(protocol),
            "protocol_fingerprint": protocol.fingerprint,
            "truth_used_online": False,
            "active_routes": ["track_superglue"],
            "rows": rows,
            "aggregate": {
                "routes": {"track_superglue": {"latency_p95_ms": 750.0}}
            },
        },
    )
    payload = json.loads(
        build_promotion_manifest(metrics).read_text(encoding="utf-8")
    )
    assert payload["eligible_routes"] == ["track_superglue"]
    assert payload["preferred_route"] is None
