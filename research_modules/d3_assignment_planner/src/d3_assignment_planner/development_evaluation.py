"""Auditable development-only evaluation for D3 behavior cloning bundles."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from math import isfinite
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .learning import EDGE_FEATURE_NAMES, FeatureDistributionGuard
from .learning_data import (
    DATASET_FRAMES_FILENAME,
    DATASET_MANIFEST_FILENAME,
    DATASET_SPLITS,
    LearningDatasetManifest,
    LearningFrameRecord,
    compute_split_hash,
    validate_split_integrity,
)
from .native_ppo import SharedEdgeActorCriticPolicy, torch
from .solver import HungarianDemandSlotSolver


FORMAL_DATASET_AUDIT_SCHEMA_V1 = "d3_formal_dataset_audit_v1"
BC_DEVELOPMENT_EVALUATION_SCHEMA_V1 = "d3_bc_development_evaluation_v1"
NOMINAL_SCALES = (5, 20, 50, 100, 200)
_SCALE_PATTERN = re.compile(r"-(\d+)v(\d+)-v\d+$")


def audit_formal_learning_dataset(
    dataset_dir: str | Path,
    manifest: LearningDatasetManifest,
    records: Iterable[LearningFrameRecord],
    *,
    external_holdout_seed_values: Sequence[int] = tuple(range(1000, 1020)),
) -> dict[str, Any]:
    """Recompute the formal dataset contract without modifying its files."""

    dataset = Path(dataset_dir)
    items = tuple(records)
    validate_split_integrity(
        items,
        minimum_unseen_seed_count=manifest.minimum_unseen_seed_count,
    )
    actual_split_hash = compute_split_hash(items)
    actual_frames_sha256 = _file_sha256(dataset / DATASET_FRAMES_FILENAME)
    manifest_sha256 = _file_sha256(dataset / DATASET_MANIFEST_FILENAME)
    seed_splits: dict[int, str] = {}
    episode_splits: dict[tuple[str, int, str], str] = {}
    scale_groups: dict[int, list[LearningFrameRecord]] = defaultdict(list)
    unsupported_scenarios: set[str] = set()
    for record in items:
        prior_seed = seed_splits.setdefault(int(record.seed), record.split)
        if prior_seed != record.split:
            raise ValueError("numeric seed leakage detected during formal audit")
        prior_episode = episode_splits.setdefault(record.episode_group, record.split)
        if prior_episode != record.split:
            raise ValueError("episode leakage detected during formal audit")
        scale = nominal_scale(record)
        if scale is None:
            unsupported_scenarios.add(record.scenario_version)
        else:
            scale_groups[scale].append(record)

    holdout = tuple(int(value) for value in external_holdout_seed_values)
    if tuple(sorted(set(holdout))) != holdout:
        raise ValueError("external holdout seed values must be sorted and unique")
    present_seeds = set(seed_splits)
    holdout_overlap = sorted(present_seeds & set(holdout))
    split_seed_values = {
        split: sorted(seed for seed, assigned in seed_splits.items() if assigned == split)
        for split in DATASET_SPLITS
    }
    split_frame_counts = {
        split: sum(record.split == split for record in items)
        for split in DATASET_SPLITS
    }
    split_episode_counts = {
        split: sum(value == split for value in episode_splits.values())
        for split in DATASET_SPLITS
    }
    scale_coverage: dict[str, Any] = {}
    for scale in NOMINAL_SCALES:
        frames = scale_groups.get(scale, [])
        scale_coverage[str(scale)] = {
            "available": bool(frames),
            "frame_count": len(frames),
            "episode_count": len({record.episode_group for record in frames}),
            "unique_seed_count": len({int(record.seed) for record in frames}),
            "split_frame_counts": {
                split: sum(record.split == split for record in frames)
                for split in DATASET_SPLITS
            },
            "target_count_min": min(
                (len(record.anonymous_targets) for record in frames), default=0
            ),
            "target_count_max": max(
                (len(record.anonymous_targets) for record in frames), default=0
            ),
            "resource_count_min": min(
                (len(record.anonymous_resources) for record in frames), default=0
            ),
            "resource_count_max": max(
                (len(record.anonymous_resources) for record in frames), default=0
            ),
            "candidate_edge_count": sum(
                len(record.candidate_edge_indices) for record in frames
            ),
            "selected_edge_count": sum(
                len(record.rule_selected_edges) for record in frames
            ),
        }

    checks = {
        "schema_matches": manifest.schema_version == "d3_learning_dataset_v2",
        "frames_sha256_matches": actual_frames_sha256 == manifest.frames_sha256,
        "split_hash_matches": actual_split_hash == manifest.split_hash,
        "frame_count_matches": len(items) == manifest.frame_count,
        "episode_count_matches": len(episode_splits) == manifest.episode_count,
        "unique_seed_count_matches": len(seed_splits) == manifest.unique_seed_count,
        "split_frame_counts_match": split_frame_counts
        == dict(manifest.split_frame_counts),
        "split_episode_counts_match": split_episode_counts
        == dict(manifest.split_episode_counts),
        "split_seed_values_match": split_seed_values
        == {
            split: list(manifest.split_seed_values[split]) for split in DATASET_SPLITS
        },
        "numeric_seed_atomic": len(seed_splits) == sum(
            len(values) for values in split_seed_values.values()
        ),
        "episode_atomic": len(episode_splits) == manifest.episode_count,
        "external_holdout_excluded": not holdout_overlap,
        "all_nominal_scales_present": set(scale_groups) == set(NOMINAL_SCALES),
        "scenario_scale_parse_complete": not unsupported_scenarios,
    }
    return {
        "schema_version": FORMAL_DATASET_AUDIT_SCHEMA_V1,
        "dataset_path": str(dataset.resolve()),
        "dataset_manifest_sha256": manifest_sha256,
        "frames_sha256": actual_frames_sha256,
        "split_hash": actual_split_hash,
        "manifest": manifest.to_dict(),
        "actual": {
            "frame_count": len(items),
            "episode_count": len(episode_splits),
            "unique_seed_count": len(seed_splits),
            "split_frame_counts": split_frame_counts,
            "split_episode_counts": split_episode_counts,
            "split_seed_values": split_seed_values,
            "candidate_edge_count": sum(
                len(record.candidate_edge_indices) for record in items
            ),
            "selected_edge_count": sum(
                len(record.rule_selected_edges) for record in items
            ),
        },
        "external_holdout": {
            "seed_values": list(holdout),
            "overlap": holdout_overlap,
            "status": "excluded_not_evaluated",
        },
        "scale_coverage": scale_coverage,
        "unsupported_scenarios": sorted(unsupported_scenarios),
        "checks": checks,
        "all_checks_passed": all(checks.values()),
    }


def evaluate_behavior_cloning_development(
    records: Iterable[LearningFrameRecord],
    policy: SharedEdgeActorCriticPolicy,
    *,
    normalization_mean: Sequence[float],
    normalization_scale: Sequence[float],
    alpha: float = 0.25,
    min_confidence: float = 0.0,
    ood_z_threshold: float = 6.0,
    deadline_s: float = 0.05,
) -> dict[str, Any]:
    """Evaluate BC proposals on all declared splits without granting assist."""

    if torch is None:  # pragma: no cover
        raise ImportError("PyTorch is required for D3 BC development evaluation")
    items = tuple(records)
    validate_split_integrity(items)
    mean = np.asarray(normalization_mean, dtype=np.float32).reshape(-1)
    scale = np.asarray(normalization_scale, dtype=np.float32).reshape(-1)
    if mean.shape != (len(EDGE_FEATURE_NAMES),) or scale.shape != mean.shape:
        raise ValueError("development evaluation normalization shape is invalid")
    if np.any(scale <= 0.0) or not np.all(np.isfinite(mean)) or not np.all(np.isfinite(scale)):
        raise ValueError("development evaluation normalization is invalid")
    if alpha < 0.0 or deadline_s <= 0.0 or ood_z_threshold <= 0.0:
        raise ValueError("development evaluation guardrails are invalid")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("development evaluation confidence is invalid")

    guard = FeatureDistributionGuard(mean=mean, scale=scale)
    solver = HungarianDemandSlotSolver()
    device = next(policy.parameters()).device
    policy.eval()
    ordered = tuple(
        sorted(
            items,
            key=lambda item: (
                item.scenario_version,
                item.seed,
                item.episode,
                item.frame_index,
            ),
        )
    )
    warmup = next((record for record in ordered if len(record.candidate_edge_indices)), None)
    if warmup is not None:
        with torch.no_grad():
            tensor = torch.as_tensor(
                (warmup.candidate_features - mean) / scale,
                dtype=torch.float32,
                device=device,
            )
            policy(tensor, torch.ones(tensor.shape[0], dtype=torch.bool, device=device))

    frame_rows: list[dict[str, Any]] = []
    with torch.no_grad():
        for record in ordered:
            row = _evaluate_frame(
                record,
                policy,
                solver,
                mean=mean,
                scale=scale,
                guard=guard,
                alpha=float(alpha),
                min_confidence=float(min_confidence),
                ood_z_threshold=float(ood_z_threshold),
                deadline_s=float(deadline_s),
                device=device,
            )
            frame_rows.append(row)

    split_metrics = {
        split: _aggregate_rows(
            [row for row in frame_rows if row["split"] == split],
            evidence_scope=(
                "internal_test_not_external_holdout"
                if split == "test"
                else f"development_{split}"
            ),
        )
        for split in DATASET_SPLITS
    }
    scale_metrics = {
        str(scale_value): _aggregate_rows(
            [row for row in frame_rows if row["nominal_scale"] == scale_value],
            evidence_scope="development_all_internal_splits",
        )
        for scale_value in NOMINAL_SCALES
    }
    return {
        "schema_version": BC_DEVELOPMENT_EVALUATION_SCHEMA_V1,
        "evaluation_kind": "paired_rule_vs_bc_shadow",
        "assignment_solver": "hungarian_demand_slots",
        "learning_formula": "C_final=C_rule+alpha*tanh(delta_C)",
        "alpha": float(alpha),
        "guardrails": {
            "min_confidence": float(min_confidence),
            "ood_z_threshold": float(ood_z_threshold),
            "deadline_s": float(deadline_s),
            "fallback": "exact_rule_cost_matrix",
        },
        "admission": {
            "stage": "development",
            "allowed_mode": "shadow",
            "assist_authorized": False,
            "external_holdout_seed_values": list(range(1000, 1020)),
            "external_holdout_status": "not_evaluated",
        },
        "split_metrics": split_metrics,
        "scale_metrics": scale_metrics,
        "frame_count": len(frame_rows),
    }


def nominal_scale(record: LearningFrameRecord) -> int | None:
    match = _SCALE_PATTERN.search(record.scenario_version)
    if match is None or match.group(1) != match.group(2):
        return None
    value = int(match.group(1))
    return value if value in NOMINAL_SCALES else None


def _evaluate_frame(
    record: LearningFrameRecord,
    policy: SharedEdgeActorCriticPolicy,
    solver: HungarianDemandSlotSolver,
    *,
    mean: np.ndarray,
    scale: np.ndarray,
    guard: FeatureDistributionGuard,
    alpha: float,
    min_confidence: float,
    ood_z_threshold: float,
    deadline_s: float,
    device: Any,
) -> dict[str, Any]:
    labels = record.selected_edge_labels.astype(bool)
    proposal_matrix = np.asarray(record.rule_cost_matrix, dtype=float).copy()
    inference_started = perf_counter()
    fallback_reason: str | None = None
    residual = np.empty(0, dtype=float)
    logits = np.empty(0, dtype=float)
    confidence = 0.0
    if not len(record.candidate_edge_indices):
        fallback_reason = "no_candidate_edges"
    else:
        normalized = (record.candidate_features - mean) / scale
        tensor = torch.as_tensor(normalized, dtype=torch.float32, device=device)
        mask = torch.ones(tensor.shape[0], dtype=torch.bool, device=device)
        latent_mean, _, selection, _, _ = policy(tensor, mask)
        residual = (
            policy.residual_bound * torch.tanh(latent_mean)
        ).detach().cpu().numpy().astype(float, copy=False)
        logits = selection.detach().cpu().numpy().astype(float, copy=False)
        confidence = float(torch.sigmoid(torch.abs(selection)).min().item())
        if guard.is_ood(record.candidate_features, z_threshold=ood_z_threshold):
            fallback_reason = "out_of_distribution"
        elif confidence < min_confidence:
            fallback_reason = "low_confidence"
        else:
            adjustment = alpha * np.tanh(residual)
            for offset, (target_index, resource_index) in enumerate(
                record.candidate_edge_indices
            ):
                proposal_matrix[target_index, resource_index] += float(
                    adjustment[offset]
                )
    inference_elapsed_s = perf_counter() - inference_started
    if inference_elapsed_s > deadline_s:
        fallback_reason = "model_timeout"
    if fallback_reason is not None:
        proposal_matrix = np.asarray(record.rule_cost_matrix, dtype=float).copy()

    rule_started = perf_counter()
    rule_outcome = _solve_frame(solver, record, record.rule_cost_matrix)
    rule_solver_elapsed_s = perf_counter() - rule_started
    shadow_started = perf_counter()
    shadow_outcome = _solve_frame(solver, record, proposal_matrix)
    shadow_solver_elapsed_s = perf_counter() - shadow_started

    if len(labels):
        predictions = logits >= 0.0
        edge_correct = int(np.count_nonzero(predictions == labels))
        teacher = np.where(labels, -1.0, 1.0)
        residual_difference = residual - teacher
        abs_difference = np.abs(residual_difference)
        smooth_l1_sum = float(
            np.sum(np.where(abs_difference < 1.0, 0.5 * residual_difference**2, abs_difference - 0.5))
        )
        residual_mse_sum = float(np.sum(residual_difference**2))
        bce_sum = float(
            np.sum(
                np.maximum(logits, 0.0)
                - logits * labels.astype(float)
                + np.log1p(np.exp(-np.abs(logits)))
            )
        )
        rank_numerator, rank_denominator = _ranking_auc_counts(logits, labels)
    else:
        edge_correct = 0
        smooth_l1_sum = residual_mse_sum = bce_sum = 0.0
        rank_numerator = rank_denominator = 0.0

    rule_edges = set(rule_outcome["selected_edges"])
    shadow_edges = set(shadow_outcome["selected_edges"])
    union = rule_edges | shadow_edges
    intersection = rule_edges & shadow_edges
    return {
        "split": record.split,
        "nominal_scale": nominal_scale(record),
        "edge_count": len(labels),
        "selected_label_count": int(np.count_nonzero(labels)),
        "edge_correct_count": edge_correct,
        "edge_bce_sum": bce_sum,
        "residual_smooth_l1_sum": smooth_l1_sum,
        "residual_mse_sum": residual_mse_sum,
        "rank_numerator": float(rank_numerator),
        "rank_denominator": float(rank_denominator),
        "action_exact_match": rule_edges == shadow_edges,
        "action_intersection_count": len(intersection),
        "action_union_count": len(union),
        "rule_cost": float(rule_outcome["objective"]),
        "shadow_cost": float(shadow_outcome["objective"]),
        "demand_slots": int(rule_outcome["demand_slots"]),
        "rule_assigned_slots": int(rule_outcome["assigned_slots"]),
        "shadow_assigned_slots": int(shadow_outcome["assigned_slots"]),
        "high_threat_slots": int(rule_outcome["high_threat_slots"]),
        "rule_high_threat_assigned": int(rule_outcome["high_threat_assigned"]),
        "shadow_high_threat_assigned": int(shadow_outcome["high_threat_assigned"]),
        "rule_duplicate_count": int(rule_outcome["duplicate_count"]),
        "shadow_duplicate_count": int(shadow_outcome["duplicate_count"]),
        "rule_hard_violation_count": int(rule_outcome["hard_violation_count"]),
        "shadow_hard_violation_count": int(shadow_outcome["hard_violation_count"]),
        "rule_churn": int(rule_outcome["churn"]),
        "shadow_churn": int(shadow_outcome["churn"]),
        "inference_ms": inference_elapsed_s * 1000.0,
        "rule_solver_ms": rule_solver_elapsed_s * 1000.0,
        "shadow_solver_ms": shadow_solver_elapsed_s * 1000.0,
        "shadow_total_ms": (inference_elapsed_s + shadow_solver_elapsed_s) * 1000.0,
        "confidence_min": confidence,
        "fallback_reason": fallback_reason,
    }


def _solve_frame(
    solver: HungarianDemandSlotSolver,
    record: LearningFrameRecord,
    matrix: np.ndarray,
) -> dict[str, Any]:
    slot_targets: list[int] = []
    for target_index, demand in enumerate(record.target_demand_slots):
        slot_targets.extend([target_index] * max(1, int(demand)))
    slot_target_array = np.asarray(slot_targets, dtype=int)
    result = solver.solve(
        np.asarray(matrix, dtype=float)[slot_target_array, :],
        record.unassigned_costs[slot_target_array],
        candidate_mask=record.action_mask[slot_target_array, :],
    )
    selected_edges = tuple(
        sorted(
            {
                (slot_targets[item.target_index], int(item.resource_index))
                for item in result.assignments
            }
        )
    )
    assigned_counts = Counter(row for row, _ in selected_edges)
    demand_slots = sum(max(1, int(value)) for value in record.target_demand_slots)
    high_threat_indices = {
        index
        for index, threat in enumerate(record.target_threat_scores)
        if float(threat) >= 0.7
    }
    high_threat_slots = sum(
        max(1, int(record.target_demand_slots[index])) for index in high_threat_indices
    )
    resources = [column for _, column in selected_edges]
    objective = sum(
        float(record.rule_cost_matrix[row, column]) for row, column in selected_edges
    ) + sum(
        max(0, max(1, int(demand)) - assigned_counts[index])
        * float(record.unassigned_costs[index])
        for index, demand in enumerate(record.target_demand_slots)
    )
    return {
        "objective": float(objective),
        "selected_edges": selected_edges,
        "demand_slots": int(demand_slots),
        "assigned_slots": len(selected_edges),
        "high_threat_slots": int(high_threat_slots),
        "high_threat_assigned": sum(
            assigned_counts[index] for index in high_threat_indices
        ),
        "duplicate_count": len(resources) - len(set(resources)),
        "hard_violation_count": sum(
            not bool(record.action_mask[row, column]) for row, column in selected_edges
        ),
        "churn": len(set(selected_edges).symmetric_difference(record.previous_selected_edges)),
    }


def _aggregate_rows(rows: Sequence[Mapping[str, Any]], *, evidence_scope: str) -> dict[str, Any]:
    if not rows:
        return {"available": False, "reason": "no_frames", "evidence_scope": evidence_scope}
    edge_count = sum(int(row["edge_count"]) for row in rows)
    rank_denominator = sum(float(row["rank_denominator"]) for row in rows)
    action_union = sum(int(row["action_union_count"]) for row in rows)
    demand_slots = sum(int(row["demand_slots"]) for row in rows)
    high_threat_slots = sum(int(row["high_threat_slots"]) for row in rows)
    rule_costs = np.asarray([float(row["rule_cost"]) for row in rows], dtype=float)
    shadow_costs = np.asarray([float(row["shadow_cost"]) for row in rows], dtype=float)
    inference = np.asarray([float(row["inference_ms"]) for row in rows], dtype=float)
    rule_solver = np.asarray([float(row["rule_solver_ms"]) for row in rows], dtype=float)
    shadow_total = np.asarray([float(row["shadow_total_ms"]) for row in rows], dtype=float)
    fallback_counts = Counter(
        str(row["fallback_reason"])
        for row in rows
        if row["fallback_reason"] is not None
    )
    return {
        "available": True,
        "evidence_scope": evidence_scope,
        "frame_count": len(rows),
        "edge_count": edge_count,
        "selected_edge_count": sum(int(row["selected_label_count"]) for row in rows),
        "regression": {
            "residual_smooth_l1_mean": _safe_ratio(
                sum(float(row["residual_smooth_l1_sum"]) for row in rows), edge_count
            ),
            "residual_mse_mean": _safe_ratio(
                sum(float(row["residual_mse_sum"]) for row in rows), edge_count
            ),
            "selection_bce_mean": _safe_ratio(
                sum(float(row["edge_bce_sum"]) for row in rows), edge_count
            ),
        },
        "edge_action_consistency": {
            "binary_accuracy": _safe_ratio(
                sum(int(row["edge_correct_count"]) for row in rows), edge_count
            ),
            "ranking_auc": _safe_ratio(
                sum(float(row["rank_numerator"]) for row in rows), rank_denominator
            ),
            "ranking_auc_available": rank_denominator > 0.0,
            "plan_exact_match_rate": float(
                np.mean([bool(row["action_exact_match"]) for row in rows])
            ),
            "plan_edge_jaccard": _safe_ratio(
                sum(int(row["action_intersection_count"]) for row in rows), action_union
            ),
        },
        "plan_cost": {
            "rule_mean": float(np.mean(rule_costs)),
            "bc_shadow_mean": float(np.mean(shadow_costs)),
            "mean_gap": float(np.mean(shadow_costs - rule_costs)),
            "relative_gap": _safe_ratio(
                float(np.sum(shadow_costs - rule_costs)), float(np.sum(rule_costs))
            ),
        },
        "demand_satisfaction": {
            "rule_rate": _safe_ratio(
                sum(int(row["rule_assigned_slots"]) for row in rows), demand_slots
            ),
            "bc_shadow_rate": _safe_ratio(
                sum(int(row["shadow_assigned_slots"]) for row in rows), demand_slots
            ),
            "high_threat_rule_rate": _safe_ratio(
                sum(int(row["rule_high_threat_assigned"]) for row in rows),
                high_threat_slots,
            ),
            "high_threat_bc_shadow_rate": _safe_ratio(
                sum(int(row["shadow_high_threat_assigned"]) for row in rows),
                high_threat_slots,
            ),
            "demand_slot_count": demand_slots,
            "high_threat_slot_count": high_threat_slots,
        },
        "safety": {
            "rule_duplicate_count": sum(int(row["rule_duplicate_count"]) for row in rows),
            "bc_shadow_duplicate_count": sum(
                int(row["shadow_duplicate_count"]) for row in rows
            ),
            "rule_hard_violation_count": sum(
                int(row["rule_hard_violation_count"]) for row in rows
            ),
            "bc_shadow_hard_violation_count": sum(
                int(row["shadow_hard_violation_count"]) for row in rows
            ),
        },
        "reassignment_churn": {
            "rule_mean": float(np.mean([float(row["rule_churn"]) for row in rows])),
            "bc_shadow_mean": float(
                np.mean([float(row["shadow_churn"]) for row in rows])
            ),
        },
        "latency_ms": {
            "model_inference_p50": float(np.percentile(inference, 50)),
            "model_inference_p95": float(np.percentile(inference, 95)),
            "model_inference_p99": float(np.percentile(inference, 99)),
            "model_inference_max": float(np.max(inference)),
            "rule_solver_p95": float(np.percentile(rule_solver, 95)),
            "bc_shadow_total_p95": float(np.percentile(shadow_total, 95)),
        },
        "fallback": {
            "frame_count": sum(fallback_counts.values()),
            "reasons": dict(sorted(fallback_counts.items())),
        },
        "confidence_min": float(min(float(row["confidence_min"]) for row in rows)),
    }


def _ranking_auc_counts(scores: np.ndarray, labels: np.ndarray) -> tuple[float, float]:
    positives = int(np.count_nonzero(labels))
    negatives = int(labels.size) - positives
    if positives == 0 or negatives == 0:
        return 0.0, 0.0
    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(scores.size, dtype=float)
    start = 0
    while start < scores.size:
        stop = start + 1
        while stop < scores.size and sorted_scores[stop] == sorted_scores[start]:
            stop += 1
        ranks[order[start:stop]] = 0.5 * (start + 1 + stop)
        start = stop
    rank_sum = float(np.sum(ranks[labels]))
    numerator = rank_sum - positives * (positives + 1) / 2.0
    denominator = float(positives * negatives)
    return numerator, denominator


def _safe_ratio(numerator: float | int, denominator: float | int) -> float:
    if float(denominator) == 0.0:
        return 0.0
    value = float(numerator) / float(denominator)
    if not isfinite(value):
        raise FloatingPointError("development metric is non-finite")
    return value


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
