from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fusion import covariance_a95
from .types import GlobalTrack, TrackLevel


@dataclass
class EstimateRecord:
    timestamp: float
    track_id: str
    state: np.ndarray
    covariance: np.ndarray
    track_level: TrackLevel
    source_support: dict[str, int]
    truth_id: str | None = None

    @classmethod
    def from_track(cls, track: GlobalTrack) -> "EstimateRecord":
        return cls(
            timestamp=track.timestamp,
            track_id=track.global_track_id,
            state=track.state.copy(),
            covariance=track.covariance.copy(),
            track_level=track.track_level,
            source_support=dict(track.source_support),
            truth_id=track.metadata.get("truth_id"),
        )


def truth_state_at(truth: dict[str, dict[str, np.ndarray]], truth_id: str, timestamp: float) -> np.ndarray:
    item = truth[truth_id]
    times = item["times"]
    states = item["states"]
    timestamp = float(np.clip(timestamp, times[0], times[-1]))
    out = np.array([np.interp(timestamp, times, states[:, dim]) for dim in range(6)], dtype=float)
    return out


def nearest_truth_id(
    truth: dict[str, dict[str, np.ndarray]],
    timestamp: float,
    position: np.ndarray,
) -> str:
    best_id = ""
    best_dist = np.inf
    for truth_id in truth:
        state = truth_state_at(truth, truth_id, timestamp)
        dist = float(np.linalg.norm(position - state[:3]))
        if dist < best_dist:
            best_dist = dist
            best_id = truth_id
    return best_id


def attach_truth_ids(
    estimates: list[EstimateRecord],
    truth: dict[str, dict[str, np.ndarray]],
) -> list[EstimateRecord]:
    out: list[EstimateRecord] = []
    for estimate in estimates:
        truth_id = estimate.truth_id
        if truth_id not in truth:
            truth_id = nearest_truth_id(truth, estimate.timestamp, estimate.state[:3])
        out.append(
            EstimateRecord(
                timestamp=estimate.timestamp,
                track_id=estimate.track_id,
                state=estimate.state,
                covariance=estimate.covariance,
                track_level=estimate.track_level,
                source_support=estimate.source_support,
                truth_id=truth_id,
            )
        )
    return out


def position_rmse(
    estimates: list[EstimateRecord],
    truth: dict[str, dict[str, np.ndarray]],
    warmup_s: float = 3.0,
    end_time: float | None = None,
) -> float:
    errors: list[float] = []
    for estimate in attach_truth_ids(estimates, truth):
        if estimate.timestamp < warmup_s:
            continue
        if end_time is not None and estimate.timestamp > end_time:
            continue
        assert estimate.truth_id is not None
        target = truth_state_at(truth, estimate.truth_id, estimate.timestamp)
        errors.append(float(np.sum((estimate.state[:3] - target[:3]) ** 2)))
    if not errors:
        return float("nan")
    return float(np.sqrt(np.mean(errors)))


def track_continuity(
    estimates: list[EstimateRecord],
    truth: dict[str, dict[str, np.ndarray]],
    duration_s: float,
    bucket_s: float = 0.5,
    warmup_s: float = 3.0,
) -> float:
    estimates = attach_truth_ids(estimates, truth)
    start_bucket = int(np.floor(warmup_s / bucket_s))
    end_bucket = int(np.floor(duration_s / bucket_s))
    expected_bins = max(end_bucket - start_bucket + 1, 1)
    ratios: list[float] = []
    for truth_id in truth:
        bins: set[int] = set()
        for estimate in estimates:
            if estimate.truth_id != truth_id:
                continue
            if estimate.timestamp < warmup_s or estimate.timestamp > duration_s:
                continue
            bins.add(int(np.floor(estimate.timestamp / bucket_s)))
        ratios.append(len(bins) / expected_bins)
    if not ratios:
        return 0.0
    return float(np.mean(ratios))


def grading_accuracy(
    estimates: list[EstimateRecord],
    truth: dict[str, dict[str, np.ndarray]],
    stable_threshold_m: float,
    handover_threshold_m: float,
    warmup_s: float = 3.0,
    end_time: float | None = None,
) -> float:
    total = 0
    correct = 0
    for estimate in attach_truth_ids(estimates, truth):
        if estimate.timestamp < warmup_s:
            continue
        if end_time is not None and estimate.timestamp > end_time:
            continue
        assert estimate.truth_id is not None
        target = truth_state_at(truth, estimate.truth_id, estimate.timestamp)
        error = float(np.linalg.norm(estimate.state[:3] - target[:3]))
        a95 = covariance_a95(estimate.covariance)
        source_count = sum(1 for count in estimate.source_support.values() if count > 0)
        if error <= handover_threshold_m and a95 <= handover_threshold_m and source_count >= 2:
            expected = TrackLevel.HANDOVER
        elif error <= stable_threshold_m and a95 <= stable_threshold_m:
            expected = TrackLevel.STABLE
        else:
            expected = TrackLevel.COARSE
        if estimate.track_level == expected:
            correct += 1
        total += 1
    return float(correct / total) if total else 0.0
