"""Paired rule-versus-shadow evaluation with deterministic solver ownership."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from math import isfinite
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .learning import FeatureDistributionGuard, ResidualPrediction
from .learning_bundle import (
    MODEL_BUNDLE_MANIFEST_FILENAME,
    PROMOTION_COST_BASIS,
    PROMOTION_EVIDENCE_KIND,
    PROMOTION_EVIDENCE_SCHEMA_V1,
    ModelBundleManifest,
)
from .learning_data import (
    LEARNING_DATASET_SCHEMA_V2,
    LEARNING_DATASET_SPLIT_POLICY_V2,
    LearningFrameRecord,
    compute_split_hash,
    validate_split_integrity,
)
from .solver import HungarianDemandSlotSolver


SHADOW_EVALUATION_SCHEMA_V1 = "d3_shadow_paired_evaluation_v1"
SHADOW_EVALUATION_SCHEMA_V2 = "d3_shadow_paired_evaluation_v2"


@dataclass(frozen=True)
class ShadowFrameMetrics:
    scenario_version: str
    seed: int
    episode: str
    frame_index: int
    rule_assignment_cost: float
    shadow_assignment_cost: float
    rule_high_threat_unmet: int
    shadow_high_threat_unmet: int
    rule_churn: int
    shadow_churn: int
    rule_duplicate_count: int
    shadow_duplicate_count: int
    rule_hard_violation_count: int
    shadow_hard_violation_count: int
    inference_elapsed_ms: float
    fallback_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_version": self.scenario_version,
            "seed": int(self.seed),
            "episode": self.episode,
            "frame_index": int(self.frame_index),
            "rule_assignment_cost": float(self.rule_assignment_cost),
            "shadow_assignment_cost": float(self.shadow_assignment_cost),
            "rule_high_threat_unmet": int(self.rule_high_threat_unmet),
            "shadow_high_threat_unmet": int(self.shadow_high_threat_unmet),
            "rule_churn": int(self.rule_churn),
            "shadow_churn": int(self.shadow_churn),
            "rule_duplicate_count": int(self.rule_duplicate_count),
            "shadow_duplicate_count": int(self.shadow_duplicate_count),
            "rule_hard_violation_count": int(self.rule_hard_violation_count),
            "shadow_hard_violation_count": int(self.shadow_hard_violation_count),
            "inference_elapsed_ms": float(self.inference_elapsed_ms),
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class ShadowEvaluationReport:
    split_hash: str
    dataset_frames_sha256: str
    model_state_dict_sha256: str
    evaluated_split: str
    frame_count: int
    unseen_seed_count: int
    rule_assignment_cost_mean: float
    shadow_assignment_cost_mean: float
    rule_high_threat_unmet_total: int
    shadow_high_threat_unmet_total: int
    rule_churn_mean: float
    shadow_churn_mean: float
    rule_duplicate_count: int
    shadow_duplicate_count: int
    rule_hard_violation_count: int
    shadow_hard_violation_count: int
    inference_p50_ms: float
    inference_p95_ms: float
    fallback_reasons: Mapping[str, int]
    rule_matrix_unchanged: bool
    per_seed_metrics: Mapping[str, Mapping[str, Any]]
    promotion_manifest: Mapping[str, Any]
    frames: tuple[ShadowFrameMetrics, ...]

    def to_dict(self, *, include_frames: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SHADOW_EVALUATION_SCHEMA_V2,
            "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
            "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
            "seed_identity_scope": "numeric_seed_global_across_scenarios",
            "split_hash": self.split_hash,
            "dataset_frames_sha256": self.dataset_frames_sha256,
            "model_state_dict_sha256": self.model_state_dict_sha256,
            "cost_basis": PROMOTION_COST_BASIS,
            "evaluated_split": self.evaluated_split,
            "frame_count": int(self.frame_count),
            "unseen_seed_count": int(self.unseen_seed_count),
            "assignment_cost": {
                "rule_mean": float(self.rule_assignment_cost_mean),
                "shadow_mean": float(self.shadow_assignment_cost_mean),
            },
            "high_threat_unmet": {
                "rule_total": int(self.rule_high_threat_unmet_total),
                "shadow_total": int(self.shadow_high_threat_unmet_total),
            },
            "churn": {
                "rule_mean": float(self.rule_churn_mean),
                "shadow_mean": float(self.shadow_churn_mean),
            },
            "duplicate_hard_violation": {
                "rule_duplicate_count": int(self.rule_duplicate_count),
                "shadow_duplicate_count": int(self.shadow_duplicate_count),
                "rule_hard_violation_count": int(self.rule_hard_violation_count),
                "shadow_hard_violation_count": int(self.shadow_hard_violation_count),
            },
            "inference_ms": {
                "p50": float(self.inference_p50_ms),
                "p95": float(self.inference_p95_ms),
            },
            "fallback_reasons": dict(sorted(self.fallback_reasons.items())),
            "rule_matrix_unchanged": bool(self.rule_matrix_unchanged),
            "per_seed_metrics": {
                key: dict(value) for key, value in sorted(self.per_seed_metrics.items())
            },
            "promotion_manifest": dict(self.promotion_manifest),
        }
        if include_frames:
            payload["frames"] = [item.to_dict() for item in self.frames]
        return payload


@dataclass(frozen=True)
class _SolvedFrame:
    objective: float
    selected_edges: tuple[tuple[int, int], ...]
    high_threat_unmet: int
    churn: int
    duplicate_count: int
    hard_violation_count: int


def evaluate_shadow_pairs(
    records: Iterable[LearningFrameRecord],
    predictor: Any,
    *,
    alpha: float = 0.25,
    split: str = "test",
    min_confidence: float = 0.0,
    deadline_s: float = 0.05,
    distribution_guard: FeatureDistributionGuard | None = None,
    ood_z_threshold: float = 6.0,
    minimum_unseen_seeds: int = 20,
    evidence_eligible: bool = True,
    dataset_frames_sha256: str | None = None,
    model_state_dict_sha256: str | None = None,
    cost_tolerance: float = 1.0e-9,
) -> ShadowEvaluationReport:
    """Evaluate paired matrices; the policy never emits assignment indices."""

    items = tuple(records)
    validate_split_integrity(items)
    split_hash = compute_split_hash(items)
    dataset_sha = "" if dataset_frames_sha256 is None else str(dataset_frames_sha256)
    model_sha = "" if model_state_dict_sha256 is None else str(model_state_dict_sha256)
    for name, value in (
        ("dataset_frames_sha256", dataset_sha),
        ("model_state_dict_sha256", model_sha),
    ):
        if value and not _is_sha256(value):
            raise ValueError(f"{name} must be a lowercase hexadecimal SHA256")
    selected = tuple(item for item in items if item.split == split)
    if not selected:
        raise ValueError(f"shadow evaluation split is empty: {split}")
    if alpha < 0.0 or deadline_s <= 0.0 or ood_z_threshold <= 0.0:
        raise ValueError("shadow alpha/deadline/OOD guardrails are invalid")
    if not 0.0 <= min_confidence <= 1.0 or minimum_unseen_seeds < 1:
        raise ValueError("shadow confidence or seed threshold is invalid")
    solver = HungarianDemandSlotSolver()
    frame_metrics: list[ShadowFrameMetrics] = []
    rule_matrix_unchanged = True
    fallback_counts: dict[str, int] = {}
    for record in sorted(
        selected,
        key=lambda item: (
            item.scenario_version,
            item.seed,
            item.episode,
            item.frame_index,
        ),
    ):
        rule_matrix = np.asarray(record.rule_cost_matrix, dtype=float)
        rule_snapshot = rule_matrix.copy()
        proposal_matrix = rule_matrix.copy()
        started = perf_counter()
        fallback_reason: str | None = None
        if not len(record.candidate_edge_indices):
            fallback_reason = "no_candidate_edges"
        elif distribution_guard is not None and distribution_guard.is_ood(
            record.candidate_features, z_threshold=ood_z_threshold
        ):
            fallback_reason = "out_of_distribution"
        else:
            try:
                prediction = _coerce_prediction(predictor.predict(record.candidate_features))
            except Exception:
                prediction = None
                fallback_reason = "model_error"
            if prediction is not None:
                delta = np.asarray(prediction.delta_costs, dtype=float).reshape(-1)
                confidence = _minimum_confidence(
                    prediction.confidence, len(record.candidate_edge_indices)
                )
                if delta.shape != (len(record.candidate_edge_indices),) or not np.all(
                    np.isfinite(delta)
                ):
                    fallback_reason = "invalid_model_output"
                elif confidence is None:
                    fallback_reason = "invalid_model_output"
                elif confidence < min_confidence:
                    fallback_reason = "low_confidence"
                else:
                    adjustment = float(alpha) * np.tanh(delta)
                    for offset, (row, column) in enumerate(
                        record.candidate_edge_indices
                    ):
                        if not record.action_mask[row, column]:
                            raise AssertionError("policy edge bypassed deterministic mask")
                        proposal_matrix[row, column] = (
                            rule_matrix[row, column] + adjustment[offset]
                        )
        elapsed_s = perf_counter() - started
        if elapsed_s > deadline_s:
            fallback_reason = "model_timeout"
        if fallback_reason is not None:
            proposal_matrix = rule_matrix.copy()
            fallback_counts[fallback_reason] = fallback_counts.get(fallback_reason, 0) + 1
        rule_matrix_unchanged = rule_matrix_unchanged and np.array_equal(
            rule_matrix, rule_snapshot
        )
        rule_outcome = _solve_frame(solver, record, rule_matrix)
        proposal_outcome = _solve_frame(solver, record, proposal_matrix)
        frame_metrics.append(
            ShadowFrameMetrics(
                scenario_version=record.scenario_version,
                seed=record.seed,
                episode=record.episode,
                frame_index=record.frame_index,
                rule_assignment_cost=rule_outcome.objective,
                shadow_assignment_cost=proposal_outcome.objective,
                rule_high_threat_unmet=rule_outcome.high_threat_unmet,
                shadow_high_threat_unmet=proposal_outcome.high_threat_unmet,
                rule_churn=rule_outcome.churn,
                shadow_churn=proposal_outcome.churn,
                rule_duplicate_count=rule_outcome.duplicate_count,
                shadow_duplicate_count=proposal_outcome.duplicate_count,
                rule_hard_violation_count=rule_outcome.hard_violation_count,
                shadow_hard_violation_count=proposal_outcome.hard_violation_count,
                inference_elapsed_ms=elapsed_s * 1000.0,
                fallback_reason=fallback_reason,
            )
        )
    per_seed = _aggregate_per_seed(frame_metrics)
    elapsed = np.asarray(
        [item.inference_elapsed_ms for item in frame_metrics], dtype=float
    )
    rule_cost_mean = float(np.mean([item.rule_assignment_cost for item in frame_metrics]))
    shadow_cost_mean = float(
        np.mean([item.shadow_assignment_cost for item in frame_metrics])
    )
    rule_unmet = sum(item.rule_high_threat_unmet for item in frame_metrics)
    shadow_unmet = sum(item.shadow_high_threat_unmet for item in frame_metrics)
    rule_duplicate = sum(item.rule_duplicate_count for item in frame_metrics)
    shadow_duplicate = sum(item.shadow_duplicate_count for item in frame_metrics)
    rule_hard = sum(item.rule_hard_violation_count for item in frame_metrics)
    shadow_hard = sum(item.shadow_hard_violation_count for item in frame_metrics)
    unseen_seed_count = len({int(item.seed) for item in selected})
    safety_non_degradation = (
        shadow_unmet <= rule_unmet
        and shadow_duplicate <= rule_duplicate
        and shadow_hard <= rule_hard
        and shadow_duplicate == 0
        and shadow_hard == 0
    )
    cost_non_degradation = shadow_cost_mean <= rule_cost_mean + float(cost_tolerance)
    promotion = _promotion_manifest(
        evaluated_split=str(split),
        split_hash=split_hash,
        dataset_frames_sha256=dataset_sha,
        model_state_dict_sha256=model_sha,
        unseen_seed_count=unseen_seed_count,
        minimum_unseen_seeds=minimum_unseen_seeds,
        evidence_eligible=evidence_eligible,
        safety_non_degradation=safety_non_degradation,
        cost_non_degradation=cost_non_degradation,
        fallback_frame_count=sum(fallback_counts.values()),
    )
    return ShadowEvaluationReport(
        split_hash=split_hash,
        dataset_frames_sha256=dataset_sha,
        model_state_dict_sha256=model_sha,
        evaluated_split=str(split),
        frame_count=len(frame_metrics),
        unseen_seed_count=unseen_seed_count,
        rule_assignment_cost_mean=rule_cost_mean,
        shadow_assignment_cost_mean=shadow_cost_mean,
        rule_high_threat_unmet_total=rule_unmet,
        shadow_high_threat_unmet_total=shadow_unmet,
        rule_churn_mean=float(np.mean([item.rule_churn for item in frame_metrics])),
        shadow_churn_mean=float(np.mean([item.shadow_churn for item in frame_metrics])),
        rule_duplicate_count=rule_duplicate,
        shadow_duplicate_count=shadow_duplicate,
        rule_hard_violation_count=rule_hard,
        shadow_hard_violation_count=shadow_hard,
        inference_p50_ms=float(np.percentile(elapsed, 50)),
        inference_p95_ms=float(np.percentile(elapsed, 95)),
        fallback_reasons=dict(sorted(fallback_counts.items())),
        rule_matrix_unchanged=rule_matrix_unchanged,
        per_seed_metrics=per_seed,
        promotion_manifest=promotion,
        frames=tuple(frame_metrics),
    )


def write_shadow_report(path: str | Path, report: ShadowEvaluationReport) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(report.to_dict(), stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")


def update_bundle_promotion_manifest(
    bundle_dir: str | Path,
    promotion_manifest: Mapping[str, Any],
) -> ModelBundleManifest:
    """Attach a paired-evaluation decision without changing verified weights."""

    path = Path(bundle_dir) / MODEL_BUNDLE_MANIFEST_FILENAME
    with path.open(encoding="utf-8") as stream:
        manifest = ModelBundleManifest.from_dict(json.load(stream))
    if (
        promotion_manifest.get("evidence_schema_version")
        != PROMOTION_EVIDENCE_SCHEMA_V1
        or promotion_manifest.get("evidence_kind") != PROMOTION_EVIDENCE_KIND
        or promotion_manifest.get("cost_basis") != PROMOTION_COST_BASIS
        or promotion_manifest.get("dataset_schema_version")
        != manifest.dataset_schema_version
        or promotion_manifest.get("split_policy_version")
        != manifest.split_policy_version
        or promotion_manifest.get("seed_identity_scope")
        != "numeric_seed_global_across_scenarios"
        or promotion_manifest.get("split_hash") != manifest.split_hash
        or promotion_manifest.get("dataset_frames_sha256")
        != manifest.dataset_frames_sha256
        or promotion_manifest.get("model_state_dict_sha256")
        != manifest.state_dict_sha256
        or promotion_manifest.get("evidence_hashes_bound") is not True
    ):
        raise ValueError("promotion evidence hashes or dataset contract do not match bundle")
    updated = replace(manifest, promotion_manifest=dict(promotion_manifest))
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(updated.to_dict(), stream, ensure_ascii=True, indent=2, sort_keys=True)
        stream.write("\n")
    return updated


def _solve_frame(
    solver: HungarianDemandSlotSolver,
    record: LearningFrameRecord,
    matrix: np.ndarray,
) -> _SolvedFrame:
    slot_targets: list[int] = []
    for target_index, demand in enumerate(record.target_demand_slots):
        slot_targets.extend([target_index] * max(1, int(demand)))
    slot_matrix = matrix[np.asarray(slot_targets, dtype=int), :]
    slot_mask = record.action_mask[np.asarray(slot_targets, dtype=int), :]
    slot_unassigned = record.unassigned_costs[np.asarray(slot_targets, dtype=int)]
    result = solver.solve(slot_matrix, slot_unassigned, candidate_mask=slot_mask)
    selected_edges = tuple(
        sorted(
            {
                (slot_targets[item.target_index], int(item.resource_index))
                for item in result.assignments
            }
        )
    )
    assigned_counts = {
        target_index: sum(row == target_index for row, _ in selected_edges)
        for target_index in range(len(record.target_demand_slots))
    }
    high_threat_unmet = sum(
        max(0, int(record.target_demand_slots[index]) - assigned_counts[index])
        for index, threat in enumerate(record.target_threat_scores)
        if float(threat) >= 0.7
    )
    resources = [column for _, column in selected_edges]
    duplicate_count = len(resources) - len(set(resources))
    hard_violation_count = sum(
        not bool(record.action_mask[row, column]) for row, column in selected_edges
    )
    churn = len(set(selected_edges).symmetric_difference(record.previous_selected_edges))
    rule_basis_objective = sum(
        float(record.rule_cost_matrix[row, column]) for row, column in selected_edges
    ) + sum(
        max(0, int(demand) - assigned_counts[index])
        * float(record.unassigned_costs[index])
        for index, demand in enumerate(record.target_demand_slots)
    )
    return _SolvedFrame(
        objective=float(rule_basis_objective),
        selected_edges=selected_edges,
        high_threat_unmet=int(high_threat_unmet),
        churn=int(churn),
        duplicate_count=int(duplicate_count),
        hard_violation_count=int(hard_violation_count),
    )


def _aggregate_per_seed(
    frames: Sequence[ShadowFrameMetrics],
) -> dict[str, Mapping[str, Any]]:
    groups: dict[int, list[ShadowFrameMetrics]] = {}
    for frame in frames:
        groups.setdefault(int(frame.seed), []).append(frame)
    result: dict[str, Mapping[str, Any]] = {}
    for seed, items in sorted(groups.items()):
        key = f"seed:{seed}"
        result[key] = {
            "scenario_versions": sorted({item.scenario_version for item in items}),
            "seed": int(seed),
            "frame_count": len(items),
            "rule_assignment_cost_mean": float(
                np.mean([item.rule_assignment_cost for item in items])
            ),
            "shadow_assignment_cost_mean": float(
                np.mean([item.shadow_assignment_cost for item in items])
            ),
            "rule_high_threat_unmet_total": sum(
                item.rule_high_threat_unmet for item in items
            ),
            "shadow_high_threat_unmet_total": sum(
                item.shadow_high_threat_unmet for item in items
            ),
            "rule_churn_mean": float(np.mean([item.rule_churn for item in items])),
            "shadow_churn_mean": float(np.mean([item.shadow_churn for item in items])),
            "fallback_frame_count": sum(item.fallback_reason is not None for item in items),
        }
    return result


def _promotion_manifest(
    *,
    evaluated_split: str,
    split_hash: str,
    dataset_frames_sha256: str,
    model_state_dict_sha256: str,
    unseen_seed_count: int,
    minimum_unseen_seeds: int,
    evidence_eligible: bool,
    safety_non_degradation: bool,
    cost_non_degradation: bool,
    fallback_frame_count: int,
) -> dict[str, Any]:
    enough_seeds = unseen_seed_count >= minimum_unseen_seeds
    no_fallback = fallback_frame_count == 0
    test_evidence = str(evaluated_split) == "test"
    evidence_hashes_bound = bool(
        _is_sha256(split_hash)
        and _is_sha256(dataset_frames_sha256)
        and _is_sha256(model_state_dict_sha256)
    )
    recommended = bool(
        enough_seeds
        and evidence_eligible
        and test_evidence
        and evidence_hashes_bound
        and safety_non_degradation
        and cost_non_degradation
        and no_fallback
    )
    if recommended:
        status = "recommended"
        reason = "paired_unseen_seed_gate_passed"
    elif not evidence_eligible:
        status = "unavailable"
        reason = "evidence_source_not_promotion_eligible"
    elif not test_evidence:
        status = "unavailable"
        reason = "formal_promotion_requires_test_split"
    elif not enough_seeds:
        status = "unavailable"
        reason = "insufficient_unseen_seed_count"
    elif not evidence_hashes_bound:
        status = "unavailable"
        reason = "promotion_evidence_hashes_unbound"
    elif not no_fallback:
        status = "rejected"
        reason = "shadow_fallback_present"
    elif not safety_non_degradation:
        status = "rejected"
        reason = "safety_non_degradation_failed"
    else:
        status = "rejected"
        reason = "assignment_cost_non_degradation_failed"
    return {
        "evidence_schema_version": PROMOTION_EVIDENCE_SCHEMA_V1,
        "evidence_kind": PROMOTION_EVIDENCE_KIND,
        "cost_basis": PROMOTION_COST_BASIS,
        "dataset_schema_version": LEARNING_DATASET_SCHEMA_V2,
        "split_policy_version": LEARNING_DATASET_SPLIT_POLICY_V2,
        "seed_identity_scope": "numeric_seed_global_across_scenarios",
        "evaluated_split": str(evaluated_split),
        "split_hash": str(split_hash),
        "dataset_frames_sha256": str(dataset_frames_sha256),
        "model_state_dict_sha256": str(model_state_dict_sha256),
        "evidence_hashes_bound": evidence_hashes_bound,
        "promotion_recommended": recommended,
        "promotion_status": status,
        "reason": reason,
        "unseen_seed_count": int(unseen_seed_count),
        "minimum_unseen_seed_count": int(minimum_unseen_seeds),
        "evidence_eligible": bool(evidence_eligible),
        "safety_non_degradation": bool(safety_non_degradation),
        "assignment_cost_non_degradation": bool(cost_non_degradation),
        "fallback_frame_count": int(fallback_frame_count),
    }


def _is_sha256(value: Any) -> bool:
    text = str(value)
    return len(text) == 64 and set(text).issubset(frozenset("0123456789abcdef"))


def _coerce_prediction(value: Any) -> ResidualPrediction:
    if isinstance(value, ResidualPrediction):
        return value
    if isinstance(value, tuple) and len(value) == 2:
        return ResidualPrediction(np.asarray(value[0]), value[1])
    if isinstance(value, Mapping):
        return ResidualPrediction(np.asarray(value["delta_costs"]), value["confidence"])
    raise TypeError("predictor returned an unsupported residual result")


def _minimum_confidence(value: float | np.ndarray, edge_count: int) -> float | None:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size not in {1, edge_count} or not np.all(np.isfinite(array)):
        return None
    if np.any(array < 0.0) or np.any(array > 1.0):
        return None
    result = float(np.min(array))
    return result if isfinite(result) else None
