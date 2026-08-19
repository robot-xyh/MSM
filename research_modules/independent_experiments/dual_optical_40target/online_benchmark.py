"""Public freeze and inference entry points for the enhanced geometry route."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    AssociationPublication,
    RevolutionSnapshot as SharedRevolutionSnapshot,
    SUPPORTED_TARGET_COUNTS,
    SnapshotTrack,
    candidate_graph_fingerprint as shared_candidate_graph_fingerprint,
    snapshot_fingerprint,
)

from .core import (
    BearingSample,
    BearingTrack,
    CrossCameraCandidate,
    CrossCameraMatch,
    EpipolarEvidence,
    _fit_cross_camera_candidate,
    _suppress_duplicate_fragments,
    build_epipolar_evidence,
    k_best_global_assignments,
)
from .online import (
    FrozenAssociationParameters,
    IncrementalTemporalAssociator,
    RevolutionSnapshot,
    association_parameter_grid,
    _SharedPairGeometry,
)


FREEZE_SCHEMA_V1 = "dual-optical-epipolar-mht-freeze-v1"
FREEZE_SCHEMA_V2 = "dual-optical-epipolar-mht-freeze-v2"
ROUTE_NAME = "epipolar_mht"
ROUTE_VERSION = "enhanced-geometry-online-v2"
ROUTE_DEADLINE_MS = 1000.0


def _snapshot_target_count(snapshot: SharedRevolutionSnapshot) -> int | None:
    value = getattr(snapshot, "target_count", None)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("snapshot target_count must be an integer")
    target_count = int(value)
    if float(value) != float(target_count) or target_count not in SUPPORTED_TARGET_COUNTS:
        raise ValueError("snapshot target_count must be one of 20, 40, 60, or 100")
    return target_count


@dataclass(frozen=True)
class _WhitelistAssociationResult:
    selected_matches: tuple[CrossCameraMatch, ...]
    confirmed_matches: tuple[CrossCameraMatch, ...]
    state_by_pair: Mapping[tuple[str, str], str]
    epipolar_evidence: tuple[EpipolarEvidence, ...]
    full_pair_count: int
    whitelist_pair_count: int
    mature_whitelist_pair_count: int
    coarse_gate_pass_count: int
    fit_evaluation_count: int
    screening_elapsed_ms: float
    fitting_elapsed_ms: float
    assignment_elapsed_ms: float
    state_update_elapsed_ms: float
    processing_elapsed_ms: float


@dataclass
class _WhitelistTemporalAssociator:
    """Evaluate only main-provided anonymous pairs and confirm them causally."""

    parameters: FrozenAssociationParameters
    previous_mapping: dict[str, str] = field(default_factory=dict)
    relation_states: dict[tuple[str, str], str] = field(default_factory=dict)
    selection_history: dict[tuple[str, str], list[bool]] = field(
        default_factory=dict
    )
    support_numerators: dict[tuple[str, str], float] = field(default_factory=dict)
    support_denominators: dict[tuple[str, str], float] = field(default_factory=dict)
    last_revolution_index: int = 0
    last_cutoff_timestamp: float = -math.inf

    @property
    def config(self) -> Any:
        return self.parameters.config

    def process_snapshot(
        self,
        snapshot: RevolutionSnapshot,
        candidate_pairs: Sequence[tuple[str, str]],
    ) -> _WhitelistAssociationResult:
        if snapshot.revolution_index <= self.last_revolution_index:
            raise ValueError("revolution snapshots must be strictly increasing")
        if snapshot.cutoff_timestamp <= self.last_cutoff_timestamp:
            raise ValueError("snapshot cutoff timestamps must be strictly increasing")

        started = time.perf_counter()
        tracks_a = tuple(
            item.to_track()
            for item in snapshot.tracks_a
            if len({sample.sweep_index for sample in item.samples})
            >= self.config.minimum_track_sweeps
        )
        tracks_b = tuple(
            item.to_track()
            for item in snapshot.tracks_b
            if len({sample.sweep_index for sample in item.samples})
            >= self.config.minimum_track_sweeps
        )
        track_a_by_id = {track.track_id: track for track in tracks_a}
        track_b_by_id = {track.track_id: track for track in tracks_b}
        mature_pairs = tuple(
            pair
            for pair in candidate_pairs
            if pair[0] in track_a_by_id and pair[1] in track_b_by_id
        )

        evidence_items: list[EpipolarEvidence] = []
        candidate_items: list[CrossCameraCandidate] = []
        screening_elapsed_ms = 0.0
        fitting_elapsed_ms = 0.0
        for track_a_id, track_b_id in mature_pairs:
            track_a = track_a_by_id[track_a_id]
            track_b = track_b_by_id[track_b_id]
            stage_started = time.perf_counter()
            evidence = build_epipolar_evidence(
                track_a,
                track_b,
                config=self.config,
            )
            screening_elapsed_ms += (
                time.perf_counter() - stage_started
            ) * 1000.0
            evidence_items.append(evidence)
            if not evidence.gate_passed:
                continue
            stage_started = time.perf_counter()
            candidate_items.append(
                _fit_cross_camera_candidate(
                    track_a,
                    track_b,
                    expected_speed_mps=self.config.expected_speed_mps,
                    max_time_delta_s=self.config.max_time_delta_s,
                    covariance_gate_confidence=(
                        self.config.covariance_gate_confidence
                    ),
                )
            )
            fitting_elapsed_ms += (
                time.perf_counter() - stage_started
            ) * 1000.0

        assignment_started = time.perf_counter()
        hypotheses = k_best_global_assignments(
            tracks_a,
            tracks_b,
            candidate_items,
            config=self.config,
            previous_mapping=self.previous_mapping,
        )
        current_pairs = set(hypotheses[0].matches) if hypotheses else set()
        pair_supports: dict[tuple[str, str], float] = {}
        for hypothesis in hypotheses:
            for pair in hypothesis.matches:
                pair_supports[pair] = (
                    pair_supports.get(pair, 0.0)
                    + hypothesis.normalized_support
                )
        assignment_elapsed_ms = (
            time.perf_counter() - assignment_started
        ) * 1000.0

        state_started = time.perf_counter()
        gap = max(0, snapshot.revolution_index - self.last_revolution_index - 1)
        for history in self.selection_history.values():
            history.extend(False for _ in range(gap))
            del history[:-self.config.confirmation_window]

        universe = set(self.relation_states) | set(pair_supports) | set(current_pairs)
        for pair in sorted(universe):
            history = self.selection_history.get(pair)
            if history is None:
                implicit_misses = min(
                    snapshot.revolution_index - 1,
                    self.config.confirmation_window - 1,
                )
                history = [False] * implicit_misses
                self.selection_history[pair] = history
            history.append(pair in current_pairs)
            del history[:-self.config.confirmation_window]
            current_support = pair_supports.get(pair, 0.0)
            self.support_numerators[pair] = (
                self.config.history_discount
                * self.support_numerators.get(pair, 0.0)
                + current_support
            )
            self.support_denominators[pair] = (
                self.config.history_discount
                * self.support_denominators.get(pair, 0.0)
                + 1.0
            )
            smoothed_support = self.support_numerators[pair] / max(
                self.support_denominators[pair], 1e-12
            )
            previous_state = self.relation_states.get(pair)
            if pair in current_pairs:
                if (
                    snapshot.revolution_index >= 3
                    and sum(history) >= self.config.confirmation_hits
                    and smoothed_support >= self.config.confirmation_support
                ):
                    state = "confirmed"
                elif previous_state in {"tentative", "pending"}:
                    state = "pending"
                else:
                    state = "tentative"
            elif previous_state in {"confirmed", "coasting"} and any(history):
                state = "coasting"
            else:
                state = "rejected"
            self.relation_states[pair] = state

        self.previous_mapping = (
            dict(hypotheses[0].matches) if hypotheses else self.previous_mapping
        )
        candidate_by_pair = {
            (item.track_a_id, item.track_b_id): item
            for item in candidate_items
        }
        retained_pairs, _suppressions = _suppress_duplicate_fragments(
            tuple(
                pair
                for pair in sorted(current_pairs)
                if pair in candidate_by_pair and candidate_by_pair[pair].valid
            ),
            candidate_by_pair,
            self.relation_states,
            self.config,
        )
        selected_matches = tuple(
            CrossCameraMatch(
                match_id=(
                    f"ONLINE-R{snapshot.revolution_index:03d}-"
                    f"PAIR-{index:03d}"
                ),
                track_a_id=pair[0],
                track_b_id=pair[1],
                cost=candidate_by_pair[pair].cost,
                reference_timestamp=candidate_by_pair[pair].reference_timestamp,
                position_ned=candidate_by_pair[pair].position_ned,
                velocity_ned=candidate_by_pair[pair].velocity_ned,
            )
            for index, pair in enumerate(retained_pairs, start=1)
        )
        confirmed_matches = tuple(
            match
            for match in selected_matches
            if self.relation_states.get(
                (match.track_a_id, match.track_b_id)
            )
            == "confirmed"
        )
        state_update_elapsed_ms = (
            time.perf_counter() - state_started
        ) * 1000.0
        self.last_revolution_index = snapshot.revolution_index
        self.last_cutoff_timestamp = snapshot.cutoff_timestamp
        return _WhitelistAssociationResult(
            selected_matches=selected_matches,
            confirmed_matches=confirmed_matches,
            state_by_pair=dict(self.relation_states),
            epipolar_evidence=tuple(evidence_items),
            full_pair_count=len(tracks_a) * len(tracks_b),
            whitelist_pair_count=len(candidate_pairs),
            mature_whitelist_pair_count=len(mature_pairs),
            coarse_gate_pass_count=sum(
                item.gate_passed for item in evidence_items
            ),
            fit_evaluation_count=len(candidate_items),
            screening_elapsed_ms=screening_elapsed_ms,
            fitting_elapsed_ms=fitting_elapsed_ms,
            assignment_elapsed_ms=assignment_elapsed_ms,
            state_update_elapsed_ms=state_update_elapsed_ms,
            processing_elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )


@dataclass(frozen=True)
class CandidatePathAblationEvidence:
    """Same-snapshot evidence for whitelist versus full-pair processing."""

    input_fingerprint: str
    candidate_graph_fingerprint: str
    execution_order: tuple[str, str]
    whitelist_publication: AssociationPublication
    legacy_full_pair_publication: AssociationPublication

    def __post_init__(self) -> None:
        if not self.candidate_graph_fingerprint:
            raise ValueError("candidate-path ablation requires a shared candidate graph")
        if self.whitelist_publication.input_fingerprint != self.input_fingerprint:
            raise ValueError("whitelist ablation input fingerprint mismatch")
        if self.legacy_full_pair_publication.input_fingerprint != self.input_fingerprint:
            raise ValueError("legacy ablation input fingerprint mismatch")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CandidatePathAblationRunner:
    """Keep independent route states while consuming the exact same snapshot."""

    def __init__(self, freeze_manifest: Mapping[str, Any]) -> None:
        self._whitelist_route = FrozenEnhancedGeometryRoute(freeze_manifest)
        self._legacy_route = FrozenEnhancedGeometryRoute(freeze_manifest)

    def publish(
        self, snapshot: SharedRevolutionSnapshot
    ) -> CandidatePathAblationEvidence:
        pairs, candidate_fingerprint = _geometry_candidate_pairs(snapshot)
        if pairs is None or not candidate_fingerprint:
            raise ValueError(
                "candidate-path ablation requires main's explicit shared whitelist"
            )
        if snapshot.revolution_index % 2:
            order = ("shared_whitelist", "legacy_full_pair")
        else:
            order = ("legacy_full_pair", "shared_whitelist")
        publications: dict[str, AssociationPublication] = {}
        for mode in order:
            route = (
                self._whitelist_route
                if mode == "shared_whitelist"
                else self._legacy_route
            )
            publications[mode] = route._publish_with_candidate_mode(
                snapshot, candidate_mode=mode
            )
        return CandidatePathAblationEvidence(
            input_fingerprint=snapshot_fingerprint(snapshot),
            candidate_graph_fingerprint=candidate_fingerprint,
            execution_order=order,
            whitelist_publication=publications["shared_whitelist"],
            legacy_full_pair_publication=publications["legacy_full_pair"],
        )


def _paired_bootstrap_mean_ci(
    values: Sequence[float],
    *,
    sample_count: int = 2000,
    seed: int = 20260813,
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError("paired bootstrap requires finite nonempty values")
    if array.size == 1:
        value = float(array[0])
        return value, value
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, array.size, size=(sample_count, array.size))
    means = np.mean(array[indices], axis=1)
    return (
        float(np.percentile(means, 2.5)),
        float(np.percentile(means, 97.5)),
    )


def evaluate_20_target_negative_benefit(
    scored_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Decide whether the whitelist route may advance beyond 20 targets.

    Rows must be offline-scored train/validation evidence from the same
    snapshots. Reserved test rows are rejected before any metric is read.
    """

    if not scored_rows:
        raise ValueError("20-target negative-benefit audit has no rows")
    if any(str(row.get("split", "")) == "test" for row in scored_rows):
        raise ValueError("negative-benefit audit must not open reserved test rows")
    invalid_splits = sorted(
        {
            str(row.get("split", ""))
            for row in scored_rows
            if str(row.get("split", "")) not in {"train", "validation"}
        }
    )
    if invalid_splits:
        raise ValueError(f"unsupported negative-benefit splits: {invalid_splits}")
    if any(int(row.get("target_count", -1)) != 20 for row in scored_rows):
        raise ValueError("negative-benefit audit is restricted to 20 targets")

    validation_rows = [
        row
        for row in scored_rows
        if str(row["split"]) == "validation"
        and str(row.get("corruption_level", "")) in {"medium", "heavy"}
    ]
    if not validation_rows:
        raise ValueError("20-target audit requires medium/heavy validation rows")
    grouped: dict[tuple[int, str, int], dict[str, Mapping[str, Any]]] = {}
    for row in validation_rows:
        mode = str(row.get("candidate_mode", ""))
        if mode not in {"shared_whitelist", "legacy_full_pair"}:
            raise ValueError("negative-benefit row has an unknown candidate mode")
        identity = (
            int(row["seed"]),
            str(row["corruption_level"]),
            int(row["revolution_index"]),
        )
        if mode in grouped.setdefault(identity, {}):
            raise ValueError("negative-benefit audit contains duplicate paired rows")
        grouped[identity][mode] = row
    if {identity[1] for identity in grouped} != {"medium", "heavy"}:
        raise ValueError("negative-benefit audit requires both medium and heavy noise")

    paired: list[dict[str, Any]] = []
    for identity, modes in sorted(grouped.items()):
        if set(modes) != {"shared_whitelist", "legacy_full_pair"}:
            raise ValueError("negative-benefit audit has an incomplete candidate pair")
        improved = modes["shared_whitelist"]
        baseline = modes["legacy_full_pair"]
        improved_fingerprint = str(improved.get("input_fingerprint", ""))
        baseline_fingerprint = str(baseline.get("input_fingerprint", ""))
        if (
            not improved_fingerprint
            or improved_fingerprint != baseline_fingerprint
        ):
            raise ValueError("negative-benefit pair did not use the same input")
        paired.append(
            {
                "seed": identity[0],
                "corruption_level": identity[1],
                "revolution_index": identity[2],
                "input_fingerprint": improved_fingerprint,
                "on_time_recall_delta": float(
                    improved["on_time_recall"]
                )
                - float(baseline["on_time_recall"]),
                "improved_match_count": int(improved.get("match_count", 0)),
                "improved_correct_count": int(
                    improved.get("correct_match_count", 0)
                ),
                "improved_false_count": int(
                    improved.get("false_association_count", 0)
                ),
                "baseline_match_count": int(baseline.get("match_count", 0)),
                "baseline_false_count": int(
                    baseline.get("false_association_count", 0)
                ),
                "improved_deadline_met": bool(improved["deadline_met"]),
                "baseline_deadline_met": bool(baseline["deadline_met"]),
                "improved_end_to_end_ms": float(improved["end_to_end_ms"]),
                "baseline_end_to_end_ms": float(baseline["end_to_end_ms"]),
            }
        )

    recall_deltas = [row["on_time_recall_delta"] for row in paired]
    recall_delta_mean = float(np.mean(recall_deltas))
    recall_delta_ci95 = _paired_bootstrap_mean_ci(recall_deltas)
    improved_matches = sum(row["improved_match_count"] for row in paired)
    improved_correct = sum(row["improved_correct_count"] for row in paired)
    improved_false = sum(row["improved_false_count"] for row in paired)
    baseline_matches = sum(row["baseline_match_count"] for row in paired)
    baseline_false = sum(row["baseline_false_count"] for row in paired)
    improved_precision = improved_correct / max(improved_matches, 1)
    improved_false_rate = improved_false / max(improved_matches, 1)
    baseline_false_rate = baseline_false / max(baseline_matches, 1)
    false_rate_delta = improved_false_rate - baseline_false_rate
    improved_deadline_rate = float(
        np.mean([row["improved_deadline_met"] for row in paired])
    )
    baseline_deadline_rate = float(
        np.mean([row["baseline_deadline_met"] for row in paired])
    )
    deadline_rate_delta = improved_deadline_rate - baseline_deadline_rate
    improved_latencies = [row["improved_end_to_end_ms"] for row in paired]
    baseline_latencies = [row["baseline_end_to_end_ms"] for row in paired]
    improved_latency_p95 = float(np.percentile(improved_latencies, 95.0))
    improved_latency_mean = float(np.mean(improved_latencies))
    baseline_latency_mean = float(np.mean(baseline_latencies))
    latency_increase_ratio = (
        improved_latency_mean / baseline_latency_mean - 1.0
        if baseline_latency_mean > 1e-12
        else (float("inf") if improved_latency_mean > 1e-12 else 0.0)
    )

    reasons: list[str] = []
    if recall_delta_mean <= -0.02:
        reasons.append("medium_heavy_on_time_recall_drop_ge_2pp")
    if recall_delta_ci95[1] < 0.0:
        reasons.append("paired_bootstrap_recall_delta_ci95_below_zero")
    if improved_precision < 0.70:
        reasons.append("published_conditional_precision_below_0_70")
    if false_rate_delta > 0.005 and recall_delta_mean < 0.05:
        reasons.append("false_rate_increase_without_5pp_recall_gain")
    if improved_latency_p95 > ROUTE_DEADLINE_MS:
        reasons.append("p95_latency_exceeds_1000ms")
    if deadline_rate_delta < -0.10:
        reasons.append("deadline_met_rate_drop_gt_10pp")
    if recall_delta_mean < 0.02 and latency_increase_ratio > 0.10:
        reasons.append("latency_increase_gt_10pct_without_2pp_recall_gain")

    by_noise = {
        level: {
            "paired_count": sum(
                row["corruption_level"] == level for row in paired
            ),
            "mean_on_time_recall_delta": float(
                np.mean(
                    [
                        row["on_time_recall_delta"]
                        for row in paired
                        if row["corruption_level"] == level
                    ]
                )
            ),
        }
        for level in ("medium", "heavy")
    }
    for level in ("medium", "heavy"):
        if float(by_noise[level]["mean_on_time_recall_delta"]) <= -0.02:
            reasons.append(f"{level}_on_time_recall_drop_ge_2pp")
    return {
        "schema_version": "epipolar-mht-20target-negative-benefit-v1",
        "target_count": 20,
        "selection_split": "validation",
        "noise_levels": ["medium", "heavy"],
        "paired_row_count": len(paired),
        "retain_for_40_target": not reasons,
        "eliminated": bool(reasons),
        "elimination_reasons": reasons,
        "metrics": {
            "mean_on_time_recall_delta": recall_delta_mean,
            "paired_bootstrap_recall_delta_ci95": list(recall_delta_ci95),
            "published_conditional_precision": improved_precision,
            "false_rate_delta": false_rate_delta,
            "deadline_met_rate_delta": deadline_rate_delta,
            "improved_latency_p95_ms": improved_latency_p95,
            "latency_increase_ratio": latency_increase_ratio,
            "by_noise": by_noise,
        },
        "thresholds": {
            "maximum_mean_recall_drop": -0.02,
            "minimum_published_conditional_precision": 0.70,
            "maximum_false_rate_increase_without_5pp_recall_gain": 0.005,
            "maximum_p95_latency_ms": ROUTE_DEADLINE_MS,
            "maximum_deadline_rate_drop": -0.10,
            "maximum_latency_increase_without_2pp_recall_gain": 0.10,
        },
    }


@dataclass(frozen=True)
class _OfflineCalibrationLabels:
    """Offline-only labels used during train/validation threshold selection."""

    track_truth_counts: Mapping[str, Mapping[str, int]]
    dominant_truth_by_track: Mapping[str, str | None]
    truth_heading_groups: Mapping[str, str]


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_path(root: Path, relative: object) -> Path:
    value = Path(str(relative))
    if not str(value) or value.is_absolute():
        raise ValueError("dataset artifact path must be nonempty and relative")
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("dataset artifact escapes its root") from exc
    return resolved


def _manifest_entries(
    manifest: Mapping[str, Any], allowed_splits: set[str]
) -> list[dict[str, Any]]:
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("dataset manifest entries must be a list")
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, Mapping):
            raise ValueError("dataset manifest entry must be an object")
        split = str(raw.get("split"))
        normalized_split = "validation" if split == "val" else split
        if normalized_split not in {"train", "validation", "test"}:
            raise ValueError(f"unknown dataset split: {split}")
        if normalized_split in allowed_splits:
            value = dict(raw)
            value["split"] = normalized_split
            normalized.append(value)
    return sorted(
        normalized,
        key=lambda item: (
            item["split"],
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        ),
    )


def _load_snapshot_entry(
    root: Path, entry: Mapping[str, Any]
) -> SharedRevolutionSnapshot:
    path = _safe_path(root, entry["snapshot_path"])
    expected = str(entry.get("snapshot_sha256") or "")
    if expected and _sha256_file(path) != expected:
        raise ValueError(f"snapshot hash mismatch: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    snapshot = SharedRevolutionSnapshot.from_online_payload(payload)
    fingerprint = snapshot_fingerprint(snapshot)
    stored = str(
        entry.get("input_fingerprint")
        or entry.get("input_fingerprint_sha256")
        or payload.get("input_fingerprint")
        or ""
    )
    if stored and stored != fingerprint:
        raise ValueError("snapshot fingerprint does not match its manifest entry")
    if (
        snapshot.seed != int(entry["seed"])
        or snapshot.corruption_level != str(entry["corruption_level"])
        or snapshot.revolution_index != int(entry["revolution_index"])
    ):
        raise ValueError("snapshot identity does not match its manifest entry")
    _require_anonymous_snapshot(snapshot)
    return snapshot


def _dominant_truth(counts: Mapping[str, int]) -> str | None:
    """Return the unique most-observed real identity for one local track."""

    positive_counts = {
        str(identity): int(count)
        for identity, count in counts.items()
        if int(count) > 0
    }
    if not positive_counts:
        return None
    highest_count = max(positive_counts.values())
    winners = sorted(
        identity
        for identity, count in positive_counts.items()
        if count == highest_count
    )
    if len(winners) != 1 or winners[0].startswith("FA-"):
        return None
    return winners[0]


def _load_label_entry(
    root: Path, entry: Mapping[str, Any]
) -> _OfflineCalibrationLabels:
    relative = entry.get("label_path", entry.get("offline_label_path"))
    if relative is None:
        raise ValueError("calibration entry has no offline label path")
    path = _safe_path(root, relative)
    expected = str(entry.get("label_sha256") or entry.get("offline_label_sha256") or "")
    if expected and _sha256_file(path) != expected:
        raise ValueError(f"offline label hash mismatch: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError("enhanced geometry freeze requires JSON track labels")
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_counts = payload.get("track_truth_counts")
    if not isinstance(raw_counts, Mapping):
        raise ValueError("offline labels do not contain track_truth_counts")
    raw_heading_groups = payload.get("truth_heading_groups")
    if not isinstance(raw_heading_groups, Mapping):
        raise ValueError("offline labels do not contain truth_heading_groups")

    track_truth_counts: dict[str, dict[str, int]] = {}
    for raw_track_id, raw_identity_counts in raw_counts.items():
        track_id = str(raw_track_id)
        if not track_id or not isinstance(raw_identity_counts, Mapping):
            raise ValueError("track_truth_counts entries must map track IDs to counts")
        identity_counts: dict[str, int] = {}
        for raw_identity, raw_count in raw_identity_counts.items():
            identity = str(raw_identity)
            if (
                not identity
                or isinstance(raw_count, bool)
                or not isinstance(raw_count, int)
                or raw_count < 0
            ):
                raise ValueError(
                    "offline observation counts must be non-negative integers"
                )
            identity_counts[identity] = int(raw_count)
        track_truth_counts[track_id] = dict(sorted(identity_counts.items()))

    truth_heading_groups = {
        str(truth_id): str(group)
        for truth_id, group in raw_heading_groups.items()
        if str(truth_id) and str(group)
    }
    return _OfflineCalibrationLabels(
        track_truth_counts=track_truth_counts,
        dominant_truth_by_track={
            track_id: _dominant_truth(counts)
            for track_id, counts in track_truth_counts.items()
        },
        truth_heading_groups=dict(sorted(truth_heading_groups.items())),
    )


def _require_anonymous_snapshot(snapshot: SharedRevolutionSnapshot) -> None:
    non_anonymous = sorted(
        track.track_id
        for camera_id in snapshot.camera_ids
        for track in snapshot.tracks[camera_id]
        if track.source_kind != "anonymous"
    )
    if non_anonymous:
        raise ValueError(
            "online snapshot source_kind must be anonymous for every track: "
            + ", ".join(non_anonymous)
        )


def _geometry_candidate_pairs(
    snapshot: SharedRevolutionSnapshot,
) -> tuple[tuple[tuple[str, str], ...] | None, str]:
    """Read and validate main's optional anonymous candidate whitelist."""

    raw_pairs = getattr(snapshot, "geometry_candidate_pairs", None)
    if raw_pairs is None:
        return None, ""
    raw_fingerprint = str(
        getattr(snapshot, "geometry_candidate_graph_fingerprint", "")
        or getattr(snapshot, "candidate_graph_fingerprint", "")
        or getattr(snapshot, "candidate_graph_fingerprint_sha256", "")
        or getattr(snapshot, "geometry_candidate_fingerprint", "")
        or ""
    ).lower()
    summary = dict(getattr(snapshot, "candidate_graph_summary", {}) or {})
    # New contract classes deserialize an omitted legacy field as an empty
    # tuple. Only an empty graph carrying a fingerprint or policy summary is
    # therefore considered an explicit main-owned whitelist.
    if not raw_pairs and not raw_fingerprint and not summary:
        return None, ""
    camera_a_id, camera_b_id = snapshot.camera_ids
    valid_a = {track.track_id for track in snapshot.tracks[camera_a_id]}
    valid_b = {track.track_id for track in snapshot.tracks[camera_b_id]}
    pairs: list[tuple[str, str]] = []
    for raw_pair in raw_pairs:
        if isinstance(raw_pair, Mapping) or hasattr(raw_pair, "track_a_id"):
            track_a_id = (
                raw_pair.get("track_a_id")
                if isinstance(raw_pair, Mapping)
                else getattr(raw_pair, "track_a_id", None)
            )
            track_b_id = (
                raw_pair.get("track_b_id")
                if isinstance(raw_pair, Mapping)
                else getattr(raw_pair, "track_b_id", None)
            )
            if track_a_id is None or track_b_id is None:
                raise ValueError(
                    "geometry_candidate_pairs entries must identify both tracks"
                )
            pair = (str(track_a_id), str(track_b_id))
        else:
            if (
                isinstance(raw_pair, (str, bytes))
                or not isinstance(raw_pair, Sequence)
                or len(raw_pair) != 2
            ):
                raise ValueError(
                    "geometry_candidate_pairs entries must be track pairs"
                )
            pair = (str(raw_pair[0]), str(raw_pair[1]))
        if pair[0] not in valid_a or pair[1] not in valid_b:
            raise ValueError(
                "geometry candidate whitelist contains an unknown or reversed pair"
            )
        pairs.append(pair)
    if len(pairs) != len(set(pairs)):
        raise ValueError("geometry candidate whitelist contains duplicate pairs")
    provided = tuple(pairs)
    normalized = tuple(sorted(provided))
    local_fingerprint = shared_candidate_graph_fingerprint(provided, summary)
    advertised = raw_fingerprint
    if advertised and (
        len(advertised) != 64
        or any(character not in "0123456789abcdef" for character in advertised)
    ):
        raise ValueError("geometry candidate graph fingerprint is not SHA-256")
    if advertised and advertised != local_fingerprint:
        raise ValueError("geometry candidate graph fingerprint mismatch")
    return normalized, advertised or local_fingerprint


def _diagnostic_counter(
    *,
    result: Any,
    candidate_source: str,
    candidate_graph_fingerprint: str,
) -> Counter[str]:
    counter = Counter(
        item.rejection_reason
        for item in result.epipolar_evidence
        if not item.gate_passed and item.rejection_reason
    )
    counter.update(
        {
            f"diagnostic.candidate_source.{candidate_source}": 1,
            "diagnostic.full_pair_count": int(result.full_pair_count),
            "diagnostic.whitelist_pair_count": int(
                getattr(result, "whitelist_pair_count", result.full_pair_count)
            ),
            "diagnostic.mature_whitelist_pair_count": int(
                getattr(
                    result,
                    "mature_whitelist_pair_count",
                    result.full_pair_count,
                )
            ),
            "diagnostic.coarse_gate_pass_count": int(
                result.coarse_gate_pass_count
            ),
            "diagnostic.fit_evaluation_count": int(result.fit_evaluation_count),
            "diagnostic.screening_elapsed_us": max(
                0, int(round(result.screening_elapsed_ms * 1000.0))
            ),
            "diagnostic.fitting_elapsed_us": max(
                0, int(round(result.fitting_elapsed_ms * 1000.0))
            ),
            "diagnostic.assignment_elapsed_us": max(
                0, int(round(result.assignment_elapsed_ms * 1000.0))
            ),
            "diagnostic.state_update_elapsed_us": max(
                0,
                int(
                    round(
                        float(getattr(result, "state_update_elapsed_ms", 0.0))
                        * 1000.0
                    )
                ),
            ),
        }
    )
    if candidate_graph_fingerprint:
        counter["diagnostic.candidate_graph_fingerprint_consumed"] = 1
    return counter


def _to_internal_snapshot(snapshot: SharedRevolutionSnapshot) -> RevolutionSnapshot:
    _require_anonymous_snapshot(snapshot)
    camera_a_id, camera_b_id = snapshot.camera_ids
    snapshot_has_v2_tracker = str(
        getattr(snapshot, "tracker_fingerprint", "legacy-unfrozen-tracker")
    ) != "legacy-unfrozen-tracker"

    def convert_track(track: SnapshotTrack) -> BearingTrack:
        origin = tuple(
            float(value) for value in snapshot.camera_positions_ned[track.camera_id]
        )
        def convert_sample(sample: Any, index: int) -> BearingSample:
            measurement_deg2 = _matrix_from_flat(
                getattr(sample, "measurement_covariance_deg2", None),
                dimension=2,
                default_diagonal=0.001,
            )
            state_vector = tuple(
                float(value)
                for value in getattr(sample, "state_vector", (0.0, 0.0, 0.0, 0.0))
            )
            if len(state_vector) != 4:
                state_vector = (0.0, 0.0, 0.0, 0.0)
            state_covariance_deg2 = _matrix_from_flat(
                getattr(sample, "state_covariance", None),
                dimension=4,
                default_diagonal=1.0,
            )
            pose_covariance_deg2 = _matrix_from_flat(
                getattr(sample, "pose_covariance_deg2", None),
                dimension=2,
                default_diagonal=0.0008207016,
            )
            radians_per_degree_squared = (3.141592653589793 / 180.0) ** 2
            measurement_rad2 = measurement_deg2 * radians_per_degree_squared
            pose_rad2 = pose_covariance_deg2 * radians_per_degree_squared
            state_rad2 = state_covariance_deg2 * radians_per_degree_squared
            has_v2_state = snapshot_has_v2_tracker and all(
                hasattr(sample, name)
                for name in (
                    "measurement_covariance_deg2",
                    "state_vector",
                    "state_covariance",
                )
            )
            return BearingSample(
                camera_id=track.camera_id,
                sweep_index=int(sample.sweep_index),
                timestamp=float(sample.timestamp),
                origin_ned=origin,
                direction_ned=tuple(float(value) for value in sample.direction_ned),
                detection_uids=(
                    f"{track.track_id}-S{index:04d}-"
                    f"N{sample.detection_count:03d}",
                ),
                focal_length_px=float(snapshot.focal_length_px),
                bbox_area_px2=float(sample.bbox_area_px2),
                measurement_covariance_rad2=_matrix_tuple(measurement_rad2),
                pose_covariance_rad2=_matrix_tuple(pose_rad2),
                prediction_covariance_rad2=((0.0, 0.0), (0.0, 0.0)),
                azimuth_rate_rad_s=(
                    float(state_vector[2]) * 3.141592653589793 / 180.0
                ),
                elevation_rate_rad_s=(
                    float(state_vector[3]) * 3.141592653589793 / 180.0
                ),
                kinematic_state_covariance=tuple(
                    tuple(float(value) for value in row) for row in state_rad2
                ),
                covariance_source=(
                    "snapshot_v2"
                    if has_v2_state
                    else "legacy_conservative_default"
                ),
            )

        return BearingTrack(
            track_id=track.track_id,
            camera_id=track.camera_id,
            samples=[
                convert_sample(sample, index)
                for index, sample in enumerate(track.samples)
                if sample.timestamp <= snapshot.cutoff_timestamp + 1e-9
            ],
            hit_history=tuple(
                bool(value)
                for value in getattr(track, "recent_sweep_hits", ())
            ),
            track_state=str(getattr(track, "track_state", "legacy")),
            state_covariance=tuple(
                tuple(float(value) for value in row)
                for row in (
                    _matrix_from_flat(
                        getattr(track.samples[-1], "state_covariance", None)
                        if track.samples
                        else None,
                        dimension=4,
                        default_diagonal=1.0,
                    )
                    * (3.141592653589793 / 180.0) ** 2
                )
            ),
        )

    return RevolutionSnapshot.from_tracks(
        scenario_seed=snapshot.seed,
        corruption_level=snapshot.corruption_level,
        revolution_index=snapshot.revolution_index,
        cutoff_timestamp=snapshot.cutoff_timestamp,
        camera_a_id=camera_a_id,
        camera_b_id=camera_b_id,
        tracks_a=tuple(convert_track(item) for item in snapshot.tracks[camera_a_id]),
        tracks_b=tuple(convert_track(item) for item in snapshot.tracks[camera_b_id]),
    )


def _matrix_from_flat(
    value: Any, *, dimension: int, default_diagonal: float
) -> np.ndarray:
    if value is None:
        return np.eye(dimension, dtype=float) * float(default_diagonal)
    array = np.asarray(value, dtype=float)
    if array.size != dimension * dimension or not np.all(np.isfinite(array)):
        return np.eye(dimension, dtype=float) * float(default_diagonal)
    return array.reshape(dimension, dimension)


def _matrix_tuple(value: Any) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        (float(value[0, 0]), float(value[0, 1])),
        (float(value[1, 0]), float(value[1, 1])),
    )


def _candidate_score(
    config: FrozenAssociationParameters,
    records: Sequence[tuple[SharedRevolutionSnapshot, _OfflineCalibrationLabels]],
    *,
    shared_cache_by_group: dict[
        tuple[int, str], dict[tuple[str, str], _SharedPairGeometry]
    ],
) -> dict[str, Any]:
    grouped: dict[
        tuple[int, str],
        list[tuple[SharedRevolutionSnapshot, _OfflineCalibrationLabels]],
    ] = {}
    for snapshot, labels in records:
        grouped.setdefault((snapshot.seed, snapshot.corruption_level), []).append(
            (snapshot, labels)
        )
    correct = false = duplicate = expected_total = 0
    true_candidate_opportunity_count = 0
    true_candidate_retained_count = 0
    selected_association_count = 0
    elapsed_ms = 0.0
    whitelist_snapshot_count = 0
    legacy_fallback_snapshot_count = 0
    for group_key, group in grouped.items():
        legacy_associator = IncrementalTemporalAssociator(
            config,
            shared_geometry_cache=shared_cache_by_group.setdefault(group_key, {}),
        )
        whitelist_associator = _WhitelistTemporalAssociator(config)
        for snapshot, labels in sorted(group, key=lambda item: item[0].revolution_index):
            candidate_pairs, _candidate_fingerprint = _geometry_candidate_pairs(
                snapshot
            )
            internal = _to_internal_snapshot(snapshot)
            if candidate_pairs is None:
                legacy_fallback_snapshot_count += 1
                result = legacy_associator.process_snapshot(internal)
            else:
                whitelist_snapshot_count += 1
                result = whitelist_associator.process_snapshot(
                    internal, candidate_pairs
                )
            elapsed_ms += result.processing_elapsed_ms
            camera_a_id, camera_b_id = snapshot.camera_ids
            identities_a = {
                identity
                for track in snapshot.tracks[camera_a_id]
                if (identity := labels.dominant_truth_by_track.get(track.track_id))
                is not None
            }
            identities_b = {
                identity
                for track in snapshot.tracks[camera_b_id]
                if (identity := labels.dominant_truth_by_track.get(track.track_id))
                is not None
            }
            expected_identities = identities_a & identities_b
            expected_total += len(expected_identities)
            true_candidate_opportunity_count += len(expected_identities)
            retained_truths: set[str] = set()
            for evidence in result.epipolar_evidence:
                if not evidence.gate_passed:
                    continue
                truth_a = labels.dominant_truth_by_track.get(evidence.track_a_id)
                truth_b = labels.dominant_truth_by_track.get(evidence.track_b_id)
                if truth_a is not None and truth_a == truth_b:
                    retained_truths.add(truth_a)
            true_candidate_retained_count += len(retained_truths)
            matched_identities: list[str] = []
            for match in result.confirmed_matches:
                selected_association_count += 1
                truth_a = labels.dominant_truth_by_track.get(match.track_a_id)
                truth_b = labels.dominant_truth_by_track.get(match.track_b_id)
                if truth_a is not None and truth_a == truth_b:
                    correct += 1
                    matched_identities.append(truth_a)
                else:
                    false += 1
            duplicate += sum(
                max(0, count - 1) for count in Counter(matched_identities).values()
            )
    precision = correct / max(correct + false, 1)
    recall = correct / max(expected_total, 1)
    f1 = 2.0 * precision * recall / max(precision + recall, 1e-12)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "correct_association_count": correct,
        "false_association_count": false,
        "duplicate_identity_count": duplicate,
        "selected_association_count": selected_association_count,
        "true_candidate_opportunity_count": true_candidate_opportunity_count,
        "true_candidate_retained_count": true_candidate_retained_count,
        "true_candidate_retention_rate": (
            true_candidate_retained_count
            / max(true_candidate_opportunity_count, 1)
        ),
        "processing_elapsed_ms": elapsed_ms,
        "shared_whitelist_snapshot_count": whitelist_snapshot_count,
        "legacy_full_pair_fallback_snapshot_count": (
            legacy_fallback_snapshot_count
        ),
    }


def _selection_key(item: Mapping[str, Any]) -> tuple[float, int, int, float, str]:
    metrics = item["metrics"]
    return (
        float(metrics["f1"]),
        -int(metrics["false_association_count"]),
        -int(metrics["duplicate_identity_count"]),
        -float(metrics["processing_elapsed_ms"]),
        str(item["parameters"]["parameter_fingerprint_sha256"]),
    )


def freeze_route(dataset_manifest: Path, output_dir: Path) -> Path:
    """Select validation-only thresholds and freeze without opening test files."""

    manifest_path = Path(dataset_manifest).resolve()
    root = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    phase = str(manifest.get("phase", "calibration"))
    if phase not in {"calibration", "train_validation"}:
        raise ValueError("freeze requires a calibration-only dataset manifest")
    if bool(manifest.get("test_access_allowed", False)):
        raise ValueError("freeze manifest must not allow test access")
    protocol_fingerprint = str(manifest.get("protocol_fingerprint") or "")
    if not protocol_fingerprint:
        raise ValueError("dataset manifest has no protocol fingerprint")
    entries = _manifest_entries(manifest, {"train", "validation"})
    if not entries or {item["split"] for item in entries} != {"train", "validation"}:
        raise ValueError("freeze requires complete train and validation entries")
    protocol = manifest.get("protocol")
    if not isinstance(protocol, Mapping):
        raise ValueError("dataset manifest has no protocol object")
    declared_target_count = int(protocol.get("target_count", -1))
    if declared_target_count not in SUPPORTED_TARGET_COUNTS:
        raise ValueError("manifest target_count must be one of 20, 40, 60, or 100")
    declared_train_seeds = tuple(int(value) for value in protocol.get("train_seeds", ()))
    declared_validation_seeds = tuple(
        int(value) for value in protocol.get("validation_seeds", ())
    )
    observed_train_seeds = tuple(
        sorted({int(item["seed"]) for item in entries if item["split"] == "train"})
    )
    observed_validation_seeds = tuple(
        sorted(
            {int(item["seed"]) for item in entries if item["split"] == "validation"}
        )
    )
    if (
        not declared_train_seeds
        or not declared_validation_seeds
        or set(observed_train_seeds) != set(declared_train_seeds)
        or set(observed_validation_seeds) != set(declared_validation_seeds)
    ):
        raise ValueError("manifest entries do not match protocol seed splits")
    opened: list[dict[str, Any]] = []
    records: dict[
        str, list[tuple[SharedRevolutionSnapshot, _OfflineCalibrationLabels]]
    ] = {
        "train": [],
        "validation": [],
    }
    input_hashes: dict[str, list[str]] = {"train": [], "validation": []}
    label_hashes: dict[str, list[str]] = {"train": [], "validation": []}
    tracker_fingerprints: set[str] = set()
    for entry in entries:
        split = str(entry["split"])
        snapshot = _load_snapshot_entry(root, entry)
        if snapshot.split != split:
            raise ValueError("snapshot split does not match calibration manifest")
        if snapshot.protocol_fingerprint != protocol_fingerprint:
            raise ValueError("snapshot protocol fingerprint mismatch")
        snapshot_target_count = _snapshot_target_count(snapshot)
        if snapshot_target_count is not None and snapshot_target_count != declared_target_count:
            raise ValueError("snapshot target_count does not match calibration protocol")
        labels = _load_label_entry(root, entry)
        tracker_fingerprints.add(
            str(
                getattr(
                    snapshot, "tracker_fingerprint", "legacy-unfrozen-tracker"
                )
            )
        )
        records[split].append((snapshot, labels))
        input_hashes[split].append(snapshot_fingerprint(snapshot))
        label_hashes[split].append(
            str(entry.get("label_sha256") or entry.get("offline_label_sha256"))
        )
        opened.append(
            {
                "split": split,
                "seed": snapshot.seed,
                "corruption_level": snapshot.corruption_level,
                "revolution_index": snapshot.revolution_index,
                "snapshot_opened": True,
                "offline_label_opened": True,
            }
        )
    declared_tracker_fingerprint = str(manifest.get("tracker_fingerprint") or "")
    if (
        len(tracker_fingerprints) != 1
        or "" in tracker_fingerprints
        or (
            declared_tracker_fingerprint
            and tracker_fingerprints != {declared_tracker_fingerprint}
        )
    ):
        raise ValueError("calibration snapshots do not share the manifest tracker")
    if tracker_fingerprints == {"legacy-unfrozen-tracker"}:
        raise ValueError(
            "formal V2 freeze requires snapshots from one frozen shared tracker"
        )
    # This deterministic route has no learned coefficients. Training inputs are
    # still audited and reserved for future parameter estimation; all threshold
    # selection is performed exclusively on validation records.
    candidates = []
    shared_cache_by_group: dict[
        tuple[int, str], dict[tuple[str, str], _SharedPairGeometry]
    ] = {}
    full_parameter_grid = association_parameter_grid()
    s180_fixed_parameters = (
        str(protocol.get("scan_profile", "")) == "s180_triangle_1s_v1"
    )
    parameter_candidates = (
        (full_parameter_grid[0],) if s180_fixed_parameters else full_parameter_grid
    )
    for parameters in parameter_candidates:
        metrics = _candidate_score(
            parameters,
            records["validation"],
            shared_cache_by_group=shared_cache_by_group,
        )
        candidates.append({"parameters": parameters.to_dict(), "metrics": metrics})
    selected = max(candidates, key=_selection_key)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selected_metrics = selected["metrics"]
    accepted = bool(
        int(selected_metrics["true_candidate_opportunity_count"]) > 0
        and int(selected_metrics["true_candidate_retained_count"]) > 0
        and int(selected_metrics["selected_association_count"]) > 0
        and int(selected_metrics["correct_association_count"]) > 0
        and float(selected_metrics["f1"]) > 0.0
    )
    confidence_evidence = [
        {
            "confidence": float(
                item["parameters"]["association_config"][
                    "covariance_gate_confidence"
                ]
            ),
            "metrics": item["metrics"],
        }
        for item in candidates
        if math.isclose(
            float(item["parameters"]["association_config"]["unmatched_cost"]),
            float(selected["parameters"]["association_config"]["unmatched_cost"]),
        )
    ]
    freeze_payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_V2,
        "route_name": ROUTE_NAME,
        "route_version": ROUTE_VERSION,
        "protocol_fingerprint": protocol_fingerprint,
        "target_count": declared_target_count,
        "dataset_manifest_sha256": _sha256_file(manifest_path),
        "dataset_manifest_path": str(manifest_path),
        "train_input_fingerprint_sha256": _sha256_payload(input_hashes["train"]),
        "validation_input_fingerprint_sha256": _sha256_payload(
            input_hashes["validation"]
        ),
        "train_label_fingerprint_sha256": _sha256_payload(label_hashes["train"]),
        "validation_label_fingerprint_sha256": _sha256_payload(
            label_hashes["validation"]
        ),
        "train_entry_count": len(records["train"]),
        "validation_entry_count": len(records["validation"]),
        "train_seeds_from_manifest_protocol": list(declared_train_seeds),
        "validation_seeds_from_manifest_protocol": list(declared_validation_seeds),
        "shared_tracker_fingerprint": next(iter(tracker_fingerprints)),
        "opened_before_freeze": opened,
        "test_accessed_before_freeze": False,
        "test_snapshot_open_count": 0,
        "test_label_open_count": 0,
        "selection_policy": (
            "fixed_v4_parameters_validation_acceptance_only"
            if s180_fixed_parameters
            else "validation_confirmed_f1_then_false_duplicate_latency"
        ),
        "parameter_search_performed": not s180_fixed_parameters,
        "fixed_parameter_source": (
            "established_v4_epipolar_mht_first_grid_candidate"
            if s180_fixed_parameters
            else None
        ),
        "training_usage": "input_hash_audit_only_no_learned_coefficients",
        "selected_parameters": selected["parameters"],
        "selected_validation_metrics": selected_metrics,
        "validation_acceptance_passed": accepted,
        "validation_acceptance_requirements": {
            "true_candidate_opportunity_count_gt_zero": True,
            "true_candidate_retained_count_gt_zero": True,
            "selected_association_count_gt_zero": True,
            "correct_association_count_gt_zero": True,
            "f1_gt_zero": True,
        },
        "chi_square_confidence_evidence": confidence_evidence,
        "candidate_count": len(candidates),
    }
    freeze_payload["model_fingerprint"] = _sha256_payload(
        {
            "route_name": ROUTE_NAME,
            "route_version": ROUTE_VERSION,
            "protocol_fingerprint": protocol_fingerprint,
            "selected_parameters": selected["parameters"],
        }
    )
    freeze_payload["freeze_fingerprint_sha256"] = _sha256_payload(freeze_payload)
    if not accepted:
        failure_path = output_dir / "freeze_failure.json"
        failure_path.write_bytes(_canonical_json(freeze_payload) + b"\n")
        (output_dir / "freeze_manifest.json").unlink(missing_ok=True)
        raise RuntimeError(
            "enhanced geometry route failed closed on validation evidence; "
            f"see {failure_path}"
        )
    path = output_dir / "freeze_manifest.json"
    path.write_bytes(_canonical_json(freeze_payload) + b"\n")
    (output_dir / "freeze_failure.json").unlink(missing_ok=True)
    return path


class FrozenEnhancedGeometryRoute:
    """Stateful online publisher consuming only main-owned anonymous snapshots."""

    def __init__(self, freeze_manifest: Mapping[str, Any]) -> None:
        self.freeze_manifest = dict(freeze_manifest)
        selected = self.freeze_manifest["selected_parameters"]
        self.parameters = FrozenAssociationParameters(
            association_config=dict(selected["association_config"]),
            tracker_revisit_gate_deg=float(selected["tracker_revisit_gate_deg"]),
            selected_on=str(selected["selected_on"]),
            schema_version=str(selected["schema_version"]),
            parameter_fingerprint_sha256=str(
                selected["parameter_fingerprint_sha256"]
            ),
        )
        self.model_fingerprint = str(self.freeze_manifest["model_fingerprint"])
        self.protocol_fingerprint = str(
            self.freeze_manifest["protocol_fingerprint"]
        )
        self.shared_tracker_fingerprint = str(
            self.freeze_manifest["shared_tracker_fingerprint"]
        )
        frozen_target_count = self.freeze_manifest.get("target_count")
        self.target_count = (
            None if frozen_target_count is None else int(frozen_target_count)
        )
        if (
            self.target_count is not None
            and self.target_count not in SUPPORTED_TARGET_COUNTS
        ):
            raise ValueError("frozen target_count is unsupported")
        self._associators: dict[tuple[int, str], IncrementalTemporalAssociator] = {}
        self._whitelist_associators: dict[
            tuple[int, str], _WhitelistTemporalAssociator
        ] = {}

    def publish(
        self, snapshot: SharedRevolutionSnapshot
    ) -> AssociationPublication:
        return self._publish_with_candidate_mode(snapshot, candidate_mode="auto")

    def _publish_with_candidate_mode(
        self,
        snapshot: SharedRevolutionSnapshot,
        *,
        candidate_mode: str,
    ) -> AssociationPublication:
        if candidate_mode not in {
            "auto",
            "shared_whitelist",
            "legacy_full_pair",
        }:
            raise ValueError("unsupported enhanced-route candidate mode")
        snapshot_target_count = _snapshot_target_count(snapshot)
        if (
            self.target_count is not None
            and snapshot_target_count is not None
            and snapshot_target_count != self.target_count
        ):
            raise ValueError("snapshot target_count does not match frozen route")
        if snapshot.protocol_fingerprint != self.protocol_fingerprint:
            raise ValueError("snapshot protocol does not match frozen route")
        if (
            str(getattr(snapshot, "tracker_fingerprint", "legacy-unfrozen-tracker"))
            != self.shared_tracker_fingerprint
        ):
            raise ValueError("snapshot tracker does not match frozen route")
        started = time.perf_counter()
        internal = _to_internal_snapshot(snapshot)
        shared_pairs, candidate_graph_fingerprint = _geometry_candidate_pairs(
            snapshot
        )
        if candidate_mode == "shared_whitelist":
            if shared_pairs is None:
                raise ValueError("forced whitelist mode requires a shared candidate graph")
            candidate_pairs = shared_pairs
        elif candidate_mode == "legacy_full_pair":
            candidate_pairs = None
        else:
            candidate_pairs = shared_pairs
        key = (snapshot.seed, snapshot.corruption_level)
        if candidate_pairs is None:
            candidate_source = "legacy_full_pair_fallback"
            working = self._associators.setdefault(
                key, IncrementalTemporalAssociator(self.parameters)
            )
            result = working.process_snapshot(internal)
            state_by_pair = {
                (item.track_a_id, item.track_b_id): item.state
                for item in result.relation_states
            }
        else:
            candidate_source = "shared_whitelist"
            working = self._whitelist_associators.setdefault(
                key, _WhitelistTemporalAssociator(self.parameters)
            )
            result = working.process_snapshot(internal, candidate_pairs)
            state_by_pair = dict(result.state_by_pair)
        matches = tuple(
            AssociationMatch(
                track_a_id=item.track_a_id,
                track_b_id=item.track_b_id,
                score=float(item.cost),
                decision_state=str(
                    state_by_pair.get(
                        (item.track_a_id, item.track_b_id), "tentative"
                    )
                ),
            )
            for item in result.selected_matches
        )
        rejection_reasons = _diagnostic_counter(
            result=result,
            candidate_source=candidate_source,
            candidate_graph_fingerprint=(
                candidate_graph_fingerprint
                if candidate_source == "shared_whitelist"
                else ""
            ),
        )
        rejection_reasons[
            "diagnostic.target_count_missing"
        ] = int(snapshot_target_count is None)
        if snapshot_target_count is not None:
            rejection_reasons[
                f"diagnostic.target_count.{snapshot_target_count}"
            ] = 1
        if candidate_mode == "legacy_full_pair":
            rejection_reasons["diagnostic.ablation_forced_legacy_full_pair"] = 1
        fitted_candidates = int(result.fit_evaluation_count)
        end_to_end_ms = max(
            (time.perf_counter() - started) * 1000.0,
            result.processing_elapsed_ms,
        )
        timed_out = end_to_end_ms > ROUTE_DEADLINE_MS
        if timed_out:
            availability = "timeout"
            matches = ()
            rejection_reasons["deadline_exceeded"] += 1
            # A timed-out epoch is never committed. Clearing the temporal state
            # prevents a later revolution from backfilling its tentative result.
            self._associators.pop(key, None)
            self._whitelist_associators.pop(key, None)
        elif result.full_pair_count and not fitted_candidates:
            availability = "empty_candidate_graph"
        else:
            availability = "available"
        if not timed_out:
            if candidate_pairs is None:
                self._associators[key] = working
            else:
                self._whitelist_associators[key] = working
        scoring_ms = result.screening_elapsed_ms + result.fitting_elapsed_ms
        hungarian_ms = result.assignment_elapsed_ms
        return AssociationPublication(
            route_name=ROUTE_NAME,
            route_version=ROUTE_VERSION,
            model_fingerprint=self.model_fingerprint,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            input_fingerprint=snapshot_fingerprint(snapshot),
            availability=availability,
            matches=matches,
            rejection_reasons=dict(sorted(rejection_reasons.items())),
            candidate_graph_fingerprint=(
                candidate_graph_fingerprint
                if candidate_source == "shared_whitelist"
                else ""
            ),
            stage_latencies_ms={
                "candidate_screening": float(result.screening_elapsed_ms),
                "candidate_fitting": float(result.fitting_elapsed_ms),
                "global_assignment": float(result.assignment_elapsed_ms),
                "temporal_state_update": float(
                    getattr(result, "state_update_elapsed_ms", 0.0)
                ),
            },
            scoring_ms=scoring_ms,
            hungarian_ms=hungarian_ms,
            end_to_end_ms=max(end_to_end_ms, scoring_ms + hungarian_ms),
            deadline_ms=ROUTE_DEADLINE_MS,
        )


def load_frozen_route(freeze_manifest: Path) -> FrozenEnhancedGeometryRoute:
    path = Path(freeze_manifest).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != FREEZE_SCHEMA_V2:
        raise ValueError("unsupported enhanced geometry freeze manifest")
    stored = str(payload.get("freeze_fingerprint_sha256") or "")
    unsigned = dict(payload)
    unsigned.pop("freeze_fingerprint_sha256", None)
    if stored != _sha256_payload(unsigned):
        raise ValueError("enhanced geometry freeze fingerprint mismatch")
    if payload.get("route_name") != ROUTE_NAME:
        raise ValueError("freeze manifest is not the epipolar_mht route")
    if payload.get("test_accessed_before_freeze") is not False:
        raise ValueError("freeze manifest does not prove test isolation")
    if payload.get("validation_acceptance_passed") is not True:
        raise ValueError("freeze manifest lacks positive validation evidence")
    return FrozenEnhancedGeometryRoute(payload)


def load_candidate_path_ablation_runner(
    freeze_manifest: Path,
) -> CandidatePathAblationRunner:
    """Load one validated freeze into two independent ablation route states."""

    route = load_frozen_route(freeze_manifest)
    return CandidatePathAblationRunner(route.freeze_manifest)
