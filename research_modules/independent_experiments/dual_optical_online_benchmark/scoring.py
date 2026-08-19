"""Offline-only scoring for frozen online association publications."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import (
    AssociationPublication,
    RevolutionSnapshot,
    ROUTE_NAMES,
    snapshot_fingerprint,
    validate_shared_publications,
)
from .dataset import sha256_file


def _dominant_truth(counts: Mapping[str, int]) -> str | None:
    ranked = sorted(
        ((int(count), str(truth)) for truth, count in counts.items()), reverse=True
    )
    if not ranked or ranked[0][1].startswith("FA-"):
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def score_publication(
    publication: AssociationPublication,
    labels: Mapping[str, Any],
    snapshot: RevolutionSnapshot | None = None,
) -> dict[str, Any]:
    track_counts = labels["track_truth_counts"]
    heading_groups = labels["truth_heading_groups"]
    selected: list[tuple[str, str, str | None, str | None]] = []
    for match in publication.matches:
        truth_a = _dominant_truth(track_counts.get(match.track_a_id, {}))
        truth_b = _dominant_truth(track_counts.get(match.track_b_id, {}))
        selected.append((match.track_a_id, match.track_b_id, truth_a, truth_b))
    correct = [item for item in selected if item[2] is not None and item[2] == item[3]]
    correct_truth = [str(item[2]) for item in correct]
    false_count = len(selected) - len(correct)
    duplicate_count = sum(max(0, count - 1) for count in Counter(correct_truth).values())
    target_count = len(heading_groups)
    precision = len(correct) / len(selected) if selected else 0.0
    recall = len(set(correct_truth)) / max(target_count, 1)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-12)
    candidate_truths: set[str] = set()
    candidate_opportunity_truths: set[str] = set()
    if snapshot is not None:
        camera_a_id, camera_b_id = snapshot.camera_ids
        truths_a = {
            truth
            for track in snapshot.tracks[camera_a_id]
            if (truth := _dominant_truth(track_counts.get(track.track_id, {})))
            is not None
        }
        truths_b = {
            truth
            for track in snapshot.tracks[camera_b_id]
            if (truth := _dominant_truth(track_counts.get(track.track_id, {})))
            is not None
        }
        candidate_opportunity_truths = truths_a & truths_b
        for track_a_id, track_b_id in snapshot.geometry_candidate_pairs:
            truth_a = _dominant_truth(track_counts.get(track_a_id, {}))
            truth_b = _dominant_truth(track_counts.get(track_b_id, {}))
            if truth_a is not None and truth_a == truth_b:
                candidate_truths.add(truth_a)
    by_heading: dict[str, dict[str, Any]] = {}
    for group in ("heading_0_deg", "heading_minus_30_deg"):
        group_targets = {truth for truth, value in heading_groups.items() if value == group}
        found = set(correct_truth) & group_targets
        by_heading[group] = {
            "target_count": len(group_targets),
            "correct_unique_match_count": len(found),
            "recall": len(found) / max(len(group_targets), 1),
        }
    return {
        "route_name": publication.route_name,
        "target_count": snapshot.target_count if snapshot is not None else None,
        "protocol_fingerprint": (
            snapshot.protocol_fingerprint if snapshot is not None else None
        ),
        "split": snapshot.split if snapshot is not None else None,
        "input_fingerprint": (
            snapshot_fingerprint(snapshot) if snapshot is not None else None
        ),
        "seed": publication.seed,
        "corruption_level": publication.corruption_level,
        "revolution_index": publication.revolution_index,
        "availability": publication.availability,
        "deadline_met": publication.deadline_met,
        "on_time_correct_match_count": (
            len(correct) if publication.deadline_met else 0
        ),
        "match_count": len(selected),
        "correct_match_count": len(correct),
        "false_association_count": false_count,
        "duplicate_identity_match_count": duplicate_count,
        "precision": precision,
        "conditional_precision": precision,
        "recall": recall,
        "on_time_recall": recall if publication.deadline_met else 0.0,
        "f1": f1,
        "heading_groups": by_heading,
        "end_to_end_ms": publication.end_to_end_ms,
        "candidate_graph_fingerprint": publication.candidate_graph_fingerprint,
        "candidate_true_opportunity_count": len(candidate_opportunity_truths),
        "candidate_true_retained_count": len(candidate_truths),
        "candidate_true_retention_rate": (
            len(candidate_truths) / max(len(candidate_opportunity_truths), 1)
        ),
        "stage_latencies_ms": dict(publication.stage_latencies_ms),
    }


def aggregate_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"routes": {}}
    active_routes = tuple(
        route for route in ROUTE_NAMES
        if any(row["route_name"] == route for row in rows)
    )
    for route in active_routes:
        route_rows = [row for row in rows if row["route_name"] == route]
        if not route_rows:
            continue
        result["routes"][route] = {
            "publication_count": len(route_rows),
            "availability_rate": sum(
                str(row["availability"]).startswith("available")
                for row in route_rows
            ) / len(route_rows),
            "deadline_met_rate": sum(bool(row["deadline_met"]) for row in route_rows) / len(route_rows),
            "macro_precision": float(np.mean([row["precision"] for row in route_rows])),
            "macro_recall": float(np.mean([row["recall"] for row in route_rows])),
            "macro_on_time_recall": float(
                np.mean([row.get("on_time_recall", 0.0) for row in route_rows])
            ),
            "macro_f1": float(np.mean([row["f1"] for row in route_rows])),
            "mean_candidate_true_retention_rate": float(
                np.mean(
                    [
                        row.get("candidate_true_retention_rate", 0.0)
                        for row in route_rows
                    ]
                )
            ),
            "false_association_count": int(sum(row["false_association_count"] for row in route_rows)),
            "duplicate_identity_match_count": int(sum(row["duplicate_identity_match_count"] for row in route_rows)),
            "latency_p50_ms": float(np.percentile([row["end_to_end_ms"] for row in route_rows], 50)),
            "latency_p95_ms": float(np.percentile([row["end_to_end_ms"] for row in route_rows], 95)),
            "stage_latency_p95_ms": {
                stage: float(
                    np.percentile(
                        [
                            float(row.get("stage_latencies_ms", {}).get(stage, 0.0))
                            for row in route_rows
                        ],
                        95,
                    )
                )
                for stage in sorted(
                    {
                        key
                        for row in route_rows
                        for key in row.get("stage_latencies_ms", {})
                    }
                )
            },
        }
    return result


def load_offline_labels(path: str | Path, expected_sha256: str) -> dict[str, Any]:
    path = Path(path)
    if sha256_file(path) != expected_sha256:
        raise ValueError("offline label hash mismatch during scoring")
    labels = json.loads(path.read_text(encoding="utf-8"))
    if labels.get("offline_truth_only") is not True:
        raise ValueError("scoring file is not marked offline-only")
    return labels


def validate_and_score(
    snapshot: RevolutionSnapshot,
    publications: Sequence[AssociationPublication],
    labels: Mapping[str, Any],
    *,
    expected_routes: Sequence[str] = ROUTE_NAMES,
) -> list[dict[str, Any]]:
    validate_shared_publications(
        snapshot, publications, expected_routes=expected_routes
    )
    return [
        score_publication(publication, labels, snapshot)
        for publication in publications
    ]
