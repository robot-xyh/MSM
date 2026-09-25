"""Offline-only truth scoring for anonymous online cross-view products."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from typing import Sequence

from .airsim_adapter import AirSimOfflineDetectionLabel
from .contracts import CrossViewResult, OfflineTruthLabels, split_track_key


def _relation(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _relation_sets(
    result: CrossViewResult,
    truth: OfflineTruthLabels,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    observed = {
        member
        for cluster in result.clusters
        for member in cluster.member_track_keys
    } | set(result.unresolved_track_keys)
    for pending in result.pending_relations:
        observed.update((pending.key_a, pending.key_b))
    available_truth = {
        key: target
        for key, target in truth.track_to_target.items()
        if key in observed
    }
    truth_relations = {
        _relation(left, right)
        for left, right in combinations(sorted(available_truth), 2)
        if split_track_key(left)[0] != split_track_key(right)[0]
        and available_truth[left] == available_truth[right]
    }
    predicted_relations = {
        _relation(left, right)
        for cluster in result.clusters
        for left, right in combinations(cluster.member_track_keys, 2)
    }
    return truth_relations, predicted_relations


def _observed_track_keys(result: CrossViewResult) -> set[str]:
    observed = {
        member
        for cluster in result.clusters
        for member in cluster.member_track_keys
    } | set(result.unresolved_track_keys)
    for pending in result.pending_relations:
        observed.update((pending.key_a, pending.key_b))
    return observed


def build_target_equal_cluster_metrics(
    result: CrossViewResult,
    truth: OfflineTruthLabels,
) -> dict[str, int | float | None]:
    """Score each observable target once, regardless of its number of tracks."""

    observed = _observed_track_keys(result)
    available_truth = {
        key: target
        for key, target in truth.track_to_target.items()
        if key in observed
    }
    tracks_by_target: dict[str, set[str]] = {}
    for key, target in available_truth.items():
        tracks_by_target.setdefault(target, set()).add(key)
    eligible = {
        target: tracks
        for target, tracks in tracks_by_target.items()
        if len({split_track_key(key)[0] for key in tracks}) >= 2
    }
    if not eligible:
        return {
            "opportunity_target_count": 0,
            "target_equal_mean_purity": None,
            "target_equal_mean_completeness": None,
            "independently_correct_target_count": 0,
            "independently_correct_target_rate": None,
            "mixed_identity_target_count": 0,
            "unregistered_opportunity_target_count": 0,
        }

    cluster_members = [set(cluster.member_track_keys) for cluster in result.clusters]
    purities: list[float] = []
    completenesses: list[float] = []
    independently_correct = 0
    unregistered = 0
    mixed_targets: set[str] = set()
    for members in cluster_members:
        identities = {
            available_truth[member]
            for member in members
            if member in available_truth
        }
        if len(identities) > 1:
            mixed_targets.update(identity for identity in identities if identity in eligible)

    for target, target_tracks in sorted(eligible.items()):
        options = []
        for members in cluster_members:
            correct = len(members & target_tracks)
            if correct == 0:
                continue
            labelled_members = {member for member in members if member in available_truth}
            purity = correct / len(labelled_members) if labelled_members else 0.0
            completeness = correct / len(target_tracks)
            options.append((correct, purity, completeness, members, labelled_members))
        if not options:
            purities.append(0.0)
            completenesses.append(0.0)
            unregistered += 1
            continue
        best = max(options, key=lambda item: (item[0], item[1], item[2]))
        correct, purity, completeness, members, labelled_members = best
        purities.append(float(purity))
        completenesses.append(float(completeness))
        if correct < 2:
            unregistered += 1
        if (
            members == target_tracks
            and labelled_members == members
            and purity == 1.0
            and completeness == 1.0
        ):
            independently_correct += 1

    count = len(eligible)
    return {
        "opportunity_target_count": count,
        "target_equal_mean_purity": sum(purities) / count,
        "target_equal_mean_completeness": sum(completenesses) / count,
        "independently_correct_target_count": independently_correct,
        "independently_correct_target_rate": independently_correct / count,
        "mixed_identity_target_count": len(mixed_targets),
        "unregistered_opportunity_target_count": unregistered,
    }


def score_with_offline_truth(
    result: CrossViewResult,
    truth: OfflineTruthLabels,
) -> CrossViewResult:
    if not truth.offline_only:
        raise ValueError("truth labels must be marked offline-only")
    truth_relations, predicted_relations = _relation_sets(result, truth)
    true_positive = len(predicted_relations & truth_relations)
    false_positive = len(predicted_relations - truth_relations)
    false_negative = len(truth_relations - predicted_relations)
    precision = true_positive / len(predicted_relations) if predicted_relations else 1.0
    recall = true_positive / len(truth_relations) if truth_relations else 1.0
    id_switches = sum(
        len(
            {
                truth.track_to_target.get(member)
                for member in cluster.member_track_keys
                if member in truth.track_to_target
            }
        )
        > 1
        for cluster in result.clusters
    )
    target_metrics = build_target_equal_cluster_metrics(result, truth)
    metrics = replace(
        result.metrics,
        true_positive_relations=true_positive,
        false_positive_relations=false_positive,
        false_negative_relations=false_negative,
        association_precision=precision,
        association_recall=recall,
        id_switch_count=id_switches,
        **target_metrics,
        availability={**result.metrics.availability, "truth_metrics": True},
    )
    return replace(result, metrics=metrics)


def build_offline_error_samples(
    result: CrossViewResult,
    truth: OfflineTruthLabels,
    *,
    limit: int = 100,
) -> dict[str, object]:
    if limit < 0:
        raise ValueError("error sample limit cannot be negative")
    truth_relations, predicted_relations = _relation_sets(result, truth)
    false_positive = sorted(predicted_relations - truth_relations)
    false_negative = sorted(truth_relations - predicted_relations)
    samples: list[dict[str, object]] = []
    for kind, relations in (
        ("false_positive_relation", false_positive),
        ("false_negative_relation", false_negative),
    ):
        for left, right in relations:
            if len(samples) >= limit:
                break
            samples.append(
                {
                    "kind": kind,
                    "left_track_key": left,
                    "right_track_key": right,
                    "left_target_id": truth.track_to_target.get(left),
                    "right_target_id": truth.track_to_target.get(right),
                }
            )
    mixed_clusters = []
    for cluster in result.clusters:
        target_ids = sorted(
            {
                truth.track_to_target[member]
                for member in cluster.member_track_keys
                if member in truth.track_to_target
            }
        )
        if len(target_ids) > 1:
            mixed_clusters.append(
                {
                    "cluster_id": cluster.cluster_id,
                    "member_track_keys": cluster.member_track_keys,
                    "target_ids": target_ids,
                }
            )
    for cluster in mixed_clusters:
        if len(samples) >= limit:
            break
        samples.append({"kind": "mixed_identity_cluster", **cluster})
    total_error_count = len(false_positive) + len(false_negative) + len(mixed_clusters)
    return {
        "schema_version": "terminal-crossview-offline-error-samples-v1",
        "offline_only": True,
        "sample_limit": limit,
        "total_error_count": total_error_count,
        "retained_sample_count": len(samples),
        "omitted_sample_count": max(0, total_error_count - len(samples)),
        "counts": {
            "false_positive_relations": len(false_positive),
            "false_negative_relations": len(false_negative),
            "mixed_identity_clusters": len(mixed_clusters),
        },
        "samples": samples,
    }


def build_offline_truth_from_detection_labels(
    labels: Sequence[AirSimOfflineDetectionLabel],
    *,
    scenario_name: str = "airsim_detect",
    seed: int = 0,
) -> OfflineTruthLabels:
    """Build a local-track truth map strictly after online association.

    A local track is scored only when all resolved observations agree on one
    target. Conflicting raw-name labels stay in the audit file and are omitted
    from scoring rather than silently selecting a majority identity.
    """

    resolved_by_track: dict[str, set[str]] = {}
    for label in labels:
        if not label.offline_truth_only:
            raise ValueError("AirSim detection labels must be offline-only")
        if label.resolved_truth_target_id is None:
            continue
        key = f"{label.camera_id}::{label.local_track_id}"
        resolved_by_track.setdefault(key, set()).add(label.resolved_truth_target_id)
    track_to_target = {
        key: next(iter(target_ids))
        for key, target_ids in resolved_by_track.items()
        if len(target_ids) == 1
    }
    return OfflineTruthLabels(
        track_to_target=track_to_target,
        target_trajectories_ned_m={},
        scenario_name=scenario_name,
        seed=int(seed),
        offline_only=True,
    )


def score_from_offline_detection_labels(
    result: CrossViewResult,
    labels: Sequence[AirSimOfflineDetectionLabel],
    *,
    scenario_name: str = "airsim_detect",
    seed: int = 0,
) -> CrossViewResult:
    truth = build_offline_truth_from_detection_labels(
        labels,
        scenario_name=scenario_name,
        seed=seed,
    )
    return score_with_offline_truth(result, truth)
