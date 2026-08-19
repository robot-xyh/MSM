"""Offline promotion rules for the 20/40/60/100 target scale funnel."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import ROUTE_NAMES, benchmark_protocol_for_target_count


@dataclass(frozen=True)
class PromotionDecision:
    route_name: str
    target_count: int
    promoted: bool
    eligible: bool
    preferred: bool
    reasons: tuple[str, ...]
    preference_reasons: tuple[str, ...]
    comparison_baseline_route: str
    absolute_on_time_recall: float
    medium_heavy_on_time_recall_delta: float
    paired_delta_ci95: tuple[float, float]
    conditional_precision: float
    false_opportunity_rate_delta: float
    recall_delta: float
    latency_p95_ms: float
    deadline_rate_delta: float
    compute_change_ratio: float
    identity_contract_violations: int


def _mean(rows: Sequence[Mapping[str, Any]], name: str) -> float:
    return float(np.mean([float(row.get(name, 0.0)) for row in rows])) if rows else 0.0


def _paired_bootstrap_ci95(
    deltas: Sequence[float], *, seed: int = 20260813, repeats: int = 4000
) -> tuple[float, float]:
    values = np.asarray(deltas, dtype=float)
    if not values.size:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(repeats, values.size), replace=True)
    means = samples.mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def evaluate_route_promotion(
    *,
    route_name: str,
    target_count: int,
    candidate_rows: Sequence[Mapping[str, Any]],
    baseline_rows: Sequence[Mapping[str, Any]],
    candidate_latency_p95_ms: float,
    baseline_latency_p95_ms: float,
    baseline_route_name: str = "epipolar_mht",
) -> PromotionDecision:
    """Apply the fixed fail-fast rules without selecting on reserved test truth."""

    if route_name not in ROUTE_NAMES:
        raise ValueError("unknown route")
    key = lambda row: (
        int(row["seed"]),
        str(row["corruption_level"]),
        int(row["revolution_index"]),
    )
    for name, rows in (("candidate", candidate_rows), ("baseline", baseline_rows)):
        if not rows:
            raise ValueError(f"{name} promotion evidence is empty")
        keys = [key(row) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{name} promotion evidence contains duplicate rows")
        if any(int(row.get("target_count", target_count)) != target_count for row in rows):
            raise ValueError(f"{name} promotion evidence target_count mismatch")
        protocols = {
            str(row.get("protocol_fingerprint"))
            for row in rows
            if row.get("protocol_fingerprint") is not None
        }
        if len(protocols) > 1:
            raise ValueError(f"{name} promotion evidence mixes protocols")
    candidate = {key(row): row for row in candidate_rows}
    baseline = {key(row): row for row in baseline_rows}
    candidate_noisy = {
        item for item in candidate if item[1] in {"medium", "heavy"}
    }
    baseline_noisy = {
        item for item in baseline if item[1] in {"medium", "heavy"}
    }
    protocol = benchmark_protocol_for_target_count(target_count)
    expected_noisy = {
        (int(seed), level, revolution)
        for seed in protocol.test_seeds
        for level in ("medium", "heavy")
        for revolution in range(1, protocol.revolution_count + 1)
    }
    if (
        candidate_noisy != expected_noisy
        or baseline_noisy != expected_noisy
    ):
        raise ValueError("promotion requires complete paired medium/heavy evidence")
    noisy_keys = sorted(candidate_noisy)
    for item in noisy_keys:
        candidate_fingerprint = candidate[item].get("input_fingerprint")
        baseline_fingerprint = baseline[item].get("input_fingerprint")
        if (
            candidate_fingerprint is not None
            or baseline_fingerprint is not None
        ) and (
            not candidate_fingerprint
            or candidate_fingerprint != baseline_fingerprint
        ):
            raise ValueError("promotion pair did not consume the same input")
    recall_deltas = [
        float(candidate[item].get("on_time_recall", 0.0))
        - float(baseline[item].get("on_time_recall", 0.0))
        for item in noisy_keys
    ]
    recall_delta = float(np.mean(recall_deltas)) if recall_deltas else 0.0
    ci95 = _paired_bootstrap_ci95(recall_deltas)
    selected = sum(int(row.get("match_count", 0)) for row in candidate_rows)
    correct = sum(int(row.get("correct_match_count", 0)) for row in candidate_rows)
    conditional_precision = correct / max(selected, 1)
    candidate_false = sum(
        int(row.get("false_association_count", 0)) for row in candidate_rows
    )
    baseline_false = sum(
        int(row.get("false_association_count", 0)) for row in baseline_rows
    )
    opportunities = sum(
        int(row.get("candidate_true_opportunity_count", 0))
        for row in candidate_rows
    )
    false_opportunity_rate_delta = (candidate_false - baseline_false) / max(
        opportunities, 1
    )
    all_recall_delta = _mean(candidate_rows, "on_time_recall") - _mean(
        baseline_rows, "on_time_recall"
    )
    absolute_on_time_recall = _mean(candidate_rows, "on_time_recall")
    candidate_deadline = _mean(candidate_rows, "deadline_met")
    baseline_deadline = _mean(baseline_rows, "deadline_met")
    deadline_rate_delta = candidate_deadline - baseline_deadline
    compute_change_ratio = (
        candidate_latency_p95_ms / max(baseline_latency_p95_ms, 1.0e-9) - 1.0
    )
    identity_violations = sum(
        int(row.get("duplicate_identity_match_count", 0))
        + int(row.get("truth_leakage_count", 0))
        + int(row.get("one_to_one_violation_count", 0))
        for row in candidate_rows
    )
    reasons: list[str] = []
    if absolute_on_time_recall < 0.25:
        reasons.append("absolute_on_time_recall_below_0_25")
    if recall_delta < -0.02:
        reasons.append("medium_heavy_on_time_recall_decreased_2pp")
    if conditional_precision < 0.70:
        reasons.append("conditional_precision_below_0_70")
    if candidate_latency_p95_ms > 1000.0:
        reasons.append("latency_p95_exceeded_1000ms")
    if identity_violations:
        reasons.append("identity_or_one_to_one_contract_violation")
    preference_reasons: list[str] = []
    if route_name == "track_superglue":
        if all_recall_delta < 0.02:
            preference_reasons.append("superglue_recall_gain_below_2pp")
        if ci95[0] < 0.0:
            preference_reasons.append("superglue_paired_ci95_lower_below_zero")
        if false_opportunity_rate_delta > 0.005:
            preference_reasons.append(
                "superglue_false_opportunity_rate_increased_over_0_005"
            )
    eligible = not reasons
    preferred = eligible and not preference_reasons
    return PromotionDecision(
        route_name=route_name,
        target_count=int(target_count),
        promoted=eligible,
        eligible=eligible,
        preferred=preferred,
        reasons=tuple(reasons),
        preference_reasons=tuple(preference_reasons),
        comparison_baseline_route=str(baseline_route_name),
        absolute_on_time_recall=absolute_on_time_recall,
        medium_heavy_on_time_recall_delta=recall_delta,
        paired_delta_ci95=ci95,
        conditional_precision=conditional_precision,
        false_opportunity_rate_delta=false_opportunity_rate_delta,
        recall_delta=all_recall_delta,
        latency_p95_ms=float(candidate_latency_p95_ms),
        deadline_rate_delta=deadline_rate_delta,
        compute_change_ratio=compute_change_ratio,
        identity_contract_violations=identity_violations,
    )


def decision_payload(decision: PromotionDecision) -> dict[str, Any]:
    return asdict(decision)
