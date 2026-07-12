"""Offline truth governance and statistical consistency evaluation for D2 replay."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import sqrt
from typing import Any

import numpy as np
from scipy.stats import chi2

from .dry_run_adapter import DryRunAssociationResult, detections_from_airsim_frame


_TRUTH_METADATA_KEYS = {
    "ground_truth",
    "offline_truth",
    "truth_id",
    "ground_truth_id",
    "offline_truth_id",
    "offline_truth_label",
    "truth_label",
    "truth_label_source",
    "truth_label_usage",
    "truth_position",
    "ground_truth_position",
    "offline_truth_position",
    "truth_state",
    "offline_truth_state",
    "actor_name",
    "sim_truth_id",
}


@dataclass(slots=True)
class OfflineTruthEvaluation:
    """JSON-ready metrics computed after the online association path completes."""

    profile_name: str
    profile_version: str
    frame_metrics: list[dict[str, Any]]
    summary: dict[str, Any]
    truth_label_usage: str = "offline_evaluator_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "truth_label_usage": self.truth_label_usage,
            "frame_metrics": list(self.frame_metrics),
            "summary": dict(self.summary),
        }


@dataclass(frozen=True, slots=True)
class InitializationGovernanceProfile:
    """Versioned M-of-N initialization evaluation profile."""

    profile_name: str = "default_2_of_3"
    profile_version: str = "v1"
    required_hits_m: int = 2
    window_scans_n: int = 3

    def __post_init__(self) -> None:
        if self.required_hits_m <= 0:
            raise ValueError("required_hits_m must be positive")
        if self.window_scans_n < self.required_hits_m:
            raise ValueError("window_scans_n must be >= required_hits_m")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "required_hits_m": self.required_hits_m,
            "window_scans_n": self.window_scans_n,
        }


@dataclass(slots=True)
class _TruthAccumulator:
    first_present_at: dict[str, float] = field(default_factory=dict)
    first_assigned_at: dict[str, float] = field(default_factory=dict)
    first_confirmed_at: dict[str, float] = field(default_factory=dict)
    first_present_frame: dict[str, int] = field(default_factory=dict)
    assigned_frames: dict[str, set[int]] = field(
        default_factory=lambda: defaultdict(set)
    )
    last_truth_to_track: dict[str, str] = field(default_factory=dict)
    truth_frame_count: Counter[str] = field(default_factory=Counter)
    assigned_frame_count: Counter[str] = field(default_factory=Counter)
    stable_frame_count: Counter[str] = field(default_factory=Counter)
    confusion: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    squared_errors: list[float] = field(default_factory=list)
    nis_values: list[float] = field(default_factory=list)
    nees_values: list[float] = field(default_factory=list)
    id_switch_count: int = 0
    duplicate_assignment_count: int = 0
    false_alarm_detection_count: int = 0
    missed_truth_detection_count: int = 0
    track_truth_labels: dict[str, set[str]] = field(
        default_factory=lambda: defaultdict(set)
    )
    false_alarm_track_ids: set[str] = field(default_factory=set)
    all_track_ids: set[str] = field(default_factory=set)


def evaluate_offline_truth(
    raw_frames: Sequence[Any],
    online_result: DryRunAssociationResult,
    *,
    profile_name: str = "offline_truth",
    profile_version: str = "v1",
    initialization_profile: InitializationGovernanceProfile | None = None,
) -> OfflineTruthEvaluation:
    """Evaluate identity and covariance consistency without feeding truth online."""

    if len(raw_frames) != len(online_result.frames):
        raise ValueError("raw frame count must match online result frame count")

    accumulator = _TruthAccumulator()
    init_profile = initialization_profile or InitializationGovernanceProfile()
    frame_metrics: list[dict[str, Any]] = []
    isolation_violations = 0
    for frame_index, (raw_frame, online_frame) in enumerate(
        zip(raw_frames, online_result.frames, strict=True)
    ):
        timestamp = float(online_frame.timestamp)
        evidence = _offline_frame_evidence(
            raw_frame,
            frame_index=frame_index,
            online_detection_ids=[
                detection.detection_id for detection in online_frame.detections
            ],
        )
        tracks_by_id = {
            str(track["global_track_id"]): track for track in online_frame.active_tracks
        }
        accumulator.all_track_ids.update(tracks_by_id)
        detection_to_track = _detection_to_track(online_frame, tracks_by_id)
        nis_by_detection = _nis_by_detection(online_frame)
        frame_nis = list(nis_by_detection.values())
        accumulator.nis_values.extend(frame_nis)

        isolation_violations += _online_truth_isolation_violations(online_frame)
        truth_ids_present = set(evidence["truth_ids_present"])
        observed_truth_ids = set(evidence["truth_by_detection"].values())
        for truth_id in truth_ids_present:
            accumulator.truth_frame_count[truth_id] += 1
            accumulator.first_present_at.setdefault(truth_id, timestamp)
            accumulator.first_present_frame.setdefault(truth_id, frame_index)
        missed_truth_ids = truth_ids_present - observed_truth_ids
        accumulator.missed_truth_detection_count += len(missed_truth_ids)

        assignments_by_truth: dict[str, list[str]] = defaultdict(list)
        frame_nees: list[float] = []
        for detection_id, truth_id in evidence["truth_by_detection"].items():
            track_id = detection_to_track.get(detection_id)
            if track_id is None:
                continue
            assignments_by_truth[truth_id].append(track_id)
            accumulator.track_truth_labels[track_id].add(truth_id)
            accumulator.confusion[truth_id][track_id] += 1
            accumulator.first_assigned_at.setdefault(truth_id, timestamp)

            track = tracks_by_id.get(track_id)
            truth_state = evidence["truth_state_by_id"].get(truth_id)
            if track is not None:
                lifecycle = str(track.get("lifecycle_state", ""))
                if lifecycle in {"confirmed", "engageable"}:
                    accumulator.first_confirmed_at.setdefault(truth_id, timestamp)
                position_error = _position_squared_error(track, truth_state)
                if position_error is not None:
                    accumulator.squared_errors.append(position_error)
                nees = _nees(track, truth_state)
                if nees is not None:
                    accumulator.nees_values.append(nees)
                    frame_nees.append(nees)

        for truth_id, track_ids in assignments_by_truth.items():
            unique_track_ids = sorted(set(track_ids))
            if unique_track_ids:
                accumulator.assigned_frame_count[truth_id] += 1
                accumulator.assigned_frames[truth_id].add(frame_index)
            if len(unique_track_ids) > 1:
                accumulator.duplicate_assignment_count += len(unique_track_ids) - 1
            if not unique_track_ids:
                continue
            representative = unique_track_ids[0]
            previous = accumulator.last_truth_to_track.get(truth_id)
            if previous is not None and previous != representative:
                accumulator.id_switch_count += 1
            else:
                accumulator.stable_frame_count[truth_id] += 1
            accumulator.last_truth_to_track[truth_id] = representative

        false_alarm_ids = set(evidence["false_alarm_detection_ids"])
        accumulator.false_alarm_detection_count += len(false_alarm_ids)
        for detection_id in false_alarm_ids:
            track_id = detection_to_track.get(detection_id)
            if track_id is not None:
                accumulator.false_alarm_track_ids.add(track_id)

        frame_metrics.append(
            {
                "frame_index": frame_index,
                "timestamp": timestamp,
                "measurement_count_n": len(online_frame.detections),
                "truth_target_count_m": len(truth_ids_present),
                "active_track_count": len(tracks_by_id),
                "n_m_detection_delta": len(online_frame.detections)
                - len(truth_ids_present),
                "observed_truth_count": len(observed_truth_ids),
                "missed_truth_count": len(missed_truth_ids),
                "false_alarm_detection_count": len(false_alarm_ids),
                "assigned_truth_count": len(assignments_by_truth),
                "nis": _distribution(frame_nis, degrees_of_freedom=2),
                "nees": _distribution(frame_nees, degrees_of_freedom=4),
            }
        )

    false_track_ids = sorted(
        track_id
        for track_id in accumulator.false_alarm_track_ids
        if not accumulator.track_truth_labels.get(track_id)
    )
    truth_ids = sorted(accumulator.truth_frame_count)
    initialization_latency = {
        truth_id: _latency(
            accumulator.first_present_at.get(truth_id),
            accumulator.first_assigned_at.get(truth_id),
        )
        for truth_id in truth_ids
    }
    confirmation_latency = {
        truth_id: _latency(
            accumulator.first_present_at.get(truth_id),
            accumulator.first_confirmed_at.get(truth_id),
        )
        for truth_id in truth_ids
    }
    coverage_continuity = _mean_ratio(
        accumulator.assigned_frame_count,
        accumulator.truth_frame_count,
    )
    identity_continuity = _mean_ratio(
        accumulator.stable_frame_count,
        accumulator.truth_frame_count,
    )
    m_of_n_pass_by_truth = {
        truth_id: _passes_m_of_n(
            accumulator,
            truth_id,
            profile=init_profile,
        )
        for truth_id in truth_ids
    }
    summary = {
        "frame_count": len(frame_metrics),
        "truth_metrics_available": bool(truth_ids),
        "continuity_available": bool(truth_ids),
        "truth_target_count": len(truth_ids),
        "id_switch_count": accumulator.id_switch_count,
        "track_continuity": identity_continuity,
        "identity_continuity": identity_continuity,
        "coverage_continuity": coverage_continuity,
        "duplicate_assignment_count": accumulator.duplicate_assignment_count,
        "assignment_count": int(
            sum(sum(counts.values()) for counts in accumulator.confusion.values())
        ),
        "confusion_matrix": {
            truth_id: dict(counts)
            for truth_id, counts in sorted(accumulator.confusion.items())
        },
        "rmse": (
            sqrt(sum(accumulator.squared_errors) / len(accumulator.squared_errors))
            if accumulator.squared_errors
            else 0.0
        ),
        "initialization_latency_s_by_truth": initialization_latency,
        "confirmation_latency_s_by_truth": confirmation_latency,
        "mean_initialization_latency_s": _mean_available(initialization_latency),
        "mean_confirmation_latency_s": _mean_available(confirmation_latency),
        "initialization_success_rate": _availability_rate(initialization_latency),
        "confirmation_success_rate": _availability_rate(confirmation_latency),
        "initialization_profile": init_profile.to_dict(),
        "m_of_n_initialization_pass_by_truth": m_of_n_pass_by_truth,
        "m_of_n_initialization_success_rate": (
            sum(m_of_n_pass_by_truth.values()) / len(m_of_n_pass_by_truth)
            if m_of_n_pass_by_truth
            else 0.0
        ),
        "false_alarm_detection_count": accumulator.false_alarm_detection_count,
        "missed_truth_detection_count": accumulator.missed_truth_detection_count,
        "created_track_count": len(accumulator.all_track_ids),
        "false_track_count": len(false_track_ids),
        "false_track_ids": false_track_ids,
        "false_track_rate": (
            len(false_track_ids) / len(accumulator.all_track_ids)
            if accumulator.all_track_ids
            else 0.0
        ),
        "n_m_mismatch_frame_count": sum(
            int(frame["n_m_detection_delta"] != 0) for frame in frame_metrics
        ),
        "nis": _distribution(accumulator.nis_values, degrees_of_freedom=2),
        "nees": _distribution(accumulator.nees_values, degrees_of_freedom=4),
        "online_truth_isolation_violations": isolation_violations,
    }
    return OfflineTruthEvaluation(
        profile_name=profile_name,
        profile_version=profile_version,
        frame_metrics=frame_metrics,
        summary=summary,
    )


def build_5v5_replay_fixture(
    *,
    seed: int = 1,
    steps: int = 12,
    missed_detection_frames: Sequence[int] = (5, 6),
    false_alarm_frames: Sequence[int] = (3, 4, 5),
) -> list[dict[str, Any]]:
    """Backward-compatible five-target calibration fixture."""

    return build_dense_crossing_replay_fixture(
        target_count=5,
        seed=seed,
        steps=steps,
        missed_detection_frames=missed_detection_frames,
        false_alarm_frames=false_alarm_frames,
    )


def build_dense_crossing_replay_fixture(
    *,
    target_count: int = 5,
    seed: int = 1,
    steps: int = 12,
    missed_detection_frames: Sequence[int] = (5, 6),
    false_alarm_frames: Sequence[int] = (3, 4, 5),
) -> list[dict[str, Any]]:
    """Build an N-target dense crossing replay with misses and clutter."""

    if target_count < 2:
        raise ValueError("target_count must be at least 2")
    if steps < 4:
        raise ValueError("steps must be at least 4")
    rng = np.random.default_rng(seed)
    lane_offsets = np.arange(target_count, dtype=float) - (target_count - 1) / 2.0
    directions = np.where(
        np.arange(target_count) < (target_count + 1) // 2,
        1.0,
        -1.0,
    )
    ranges = 15.0 + 0.8 * np.abs(lane_offsets)
    starts = np.column_stack((-directions * ranges, 1.6 * lane_offsets))
    speeds = 2.8 + 0.12 * np.abs(lane_offsets)
    velocities = np.column_stack((directions * speeds, -0.06 * lane_offsets))
    frames: list[dict[str, Any]] = []
    missed_frames = set(int(value) for value in missed_detection_frames)
    clutter_frames = set(int(value) for value in false_alarm_frames)
    missed_target_index = target_count // 2
    truth_ids = [f"target-{index + 1}" for index in range(target_count)]
    scenario_tags = [
        f"{target_count}-target",
        "crossing",
        "dense",
        "occlusion",
        "missed_detection",
        "false_alarm",
    ]
    if target_count == 5:
        scenario_tags.insert(0, "5v5")
    for frame_index in range(steps):
        timestamp = frame_index * 0.5
        detections: list[dict[str, Any]] = []
        truth_states: dict[str, list[float]] = {}
        for target_index, truth_id in enumerate(truth_ids):
            position = starts[target_index] + velocities[target_index] * timestamp
            state = [
                float(position[0]),
                float(position[1]),
                float(velocities[target_index, 0]),
                float(velocities[target_index, 1]),
            ]
            truth_states[truth_id] = state
            if target_index == missed_target_index and frame_index in missed_frames:
                continue
            noisy_position = position + rng.normal(0.0, 0.22, size=2)
            detections.append(
                {
                    "detection_id": f"det-{frame_index:03d}-{target_index + 1}",
                    "position": noisy_position.tolist(),
                    "covariance": [[0.09, 0.0], [0.0, 0.09]],
                    "offline_truth_label": truth_id,
                    "offline_truth_state": state,
                    "offline_truth_position": state[:2],
                    "feature": [
                        1.0 if index == target_index else 0.0
                        for index in range(target_count)
                    ],
                }
            )
        if frame_index in clutter_frames:
            detections.append(
                {
                    "detection_id": f"false-alarm-{frame_index:03d}",
                    "position": [float(30.0 + frame_index), float(-15.0 + frame_index)],
                    "covariance": [[0.16, 0.0], [0.0, 0.16]],
                    "is_false_alarm": True,
                    "confidence": 0.55,
                }
            )
        frames.append(
            {
                "frame_index": frame_index,
                "timestamp": timestamp,
                "measurement_timestamp": timestamp,
                "arrival_timestamp": timestamp + 0.08,
                "detections": detections,
                "truth_ids_present": truth_ids,
                "offline_truth_states": truth_states,
                "replay_metadata": {
                    "seed": seed,
                    "episode_id": f"d2-{target_count}target-{seed:04d}",
                    "scenario_name": (
                        f"{target_count}target_crossing_dense_"
                        "occlusion_missed_detection_false_alarm"
                    ),
                    "scenario_tags": scenario_tags,
                    "target_count": target_count,
                    "drone_count": target_count,
                },
            }
        )
    return frames


def build_long_dense_crossing_replay_fixture(
    *,
    target_count: int = 5,
    seed: int = 1,
    steps: int = 120,
    sample_period_s: float = 0.2,
    scenario_version: str = "d2-governed-long-replay/v1",
) -> list[dict[str, Any]]:
    """Build a governed long replay with repeated crossings and delayed arrivals.

    Frames remain ordered by measurement time because D2 consumes the governed
    output of D1/main. Selected arrival timestamps intentionally overtake later
    measurements so calibration can audit OOSM exposure without pretending that
    D2 implements a raw-measurement rewind filter.
    """

    if target_count < 2:
        raise ValueError("target_count must be at least 2")
    if steps < 40:
        raise ValueError("long replay requires at least 40 steps")
    if not np.isfinite(sample_period_s) or sample_period_s <= 0.0:
        raise ValueError("sample_period_s must be positive and finite")
    if not scenario_version:
        raise ValueError("scenario_version must not be empty")

    rng = np.random.default_rng(seed)
    lane_offsets = np.arange(target_count, dtype=float) - (target_count - 1) / 2.0
    directions = np.where(np.arange(target_count) % 2 == 0, 1.0, -1.0)
    truth_ids = [f"target-{index + 1}" for index in range(target_count)]
    cycle_frames = max(24, min(48, steps // 3))
    angular_rate = 2.0 * np.pi / (cycle_frames * sample_period_s)
    crossing_frames = {
        frame
        for frame in range(steps)
        if min(frame % cycle_frames, cycle_frames - frame % cycle_frames)
        in {cycle_frames // 4 - 1, cycle_frames // 4, cycle_frames // 4 + 1}
        or min(frame % cycle_frames, cycle_frames - frame % cycle_frames)
        in {3 * cycle_frames // 4 - 1, 3 * cycle_frames // 4, 3 * cycle_frames // 4 + 1}
    }
    # Deterministic late arrivals create arrival-order inversions while the
    # governed frame stream remains measurement-time ordered.
    delayed_frames = {
        frame for frame in range(8, steps, 17) if frame + 1 < steps
    }
    frames: list[dict[str, Any]] = []
    scenario_name = (
        f"{target_count}target_long_dense_crossing_occlusion_"
        "missed_detection_false_alarm_oosm"
    )
    scenario_tags = [
        f"{target_count}-target",
        "long_replay",
        "crossing",
        "dense",
        "occlusion",
        "missed_detection",
        "false_alarm",
        "oosm",
    ]

    for frame_index in range(steps):
        timestamp = frame_index * sample_period_s
        phase = angular_rate * timestamp
        nominal_delay = 0.08
        arrival_delay = nominal_delay + (0.65 if frame_index in delayed_frames else 0.0)
        detections: list[dict[str, Any]] = []
        truth_states: dict[str, list[float]] = {}
        for target_index, truth_id in enumerate(truth_ids):
            direction = directions[target_index]
            target_phase = phase + 0.04 * lane_offsets[target_index]
            position = np.array(
                [
                    direction * 18.0 * np.cos(target_phase),
                    1.25 * lane_offsets[target_index]
                    + 0.55 * np.sin(target_phase + 0.3 * target_index),
                ],
                dtype=float,
            )
            velocity = np.array(
                [
                    -direction * 18.0 * angular_rate * np.sin(target_phase),
                    0.55 * angular_rate * np.cos(target_phase + 0.3 * target_index),
                ],
                dtype=float,
            )
            state = [
                float(position[0]),
                float(position[1]),
                float(velocity[0]),
                float(velocity[1]),
            ]
            truth_states[truth_id] = state

            occluded = (
                frame_index in crossing_frames
                and target_index in {target_count // 2, max(0, target_count // 2 - 1)}
            )
            periodic_miss = (frame_index + 3 * target_index + seed) % 53 == 0
            if occluded or periodic_miss:
                continue

            noise_sigma = 0.28 if frame_index in crossing_frames else 0.20
            noisy_position = position + rng.normal(0.0, noise_sigma, size=2)
            detections.append(
                {
                    "detection_id": f"det-{frame_index:04d}-{target_index + 1}",
                    "measurement_timestamp": timestamp,
                    "arrival_timestamp": timestamp + arrival_delay,
                    "position": noisy_position.tolist(),
                    "covariance": [
                        [noise_sigma**2, 0.0],
                        [0.0, noise_sigma**2],
                    ],
                    "offline_truth_label": truth_id,
                    "offline_truth_state": state,
                    "offline_truth_position": state[:2],
                }
            )

        false_alarm_count = 1 + int(frame_index % 22 == 0)
        if frame_index % 7 in {2, 3}:
            for false_index in range(false_alarm_count):
                clutter_position = np.array(
                    [
                        5.0 * np.sin(0.31 * frame_index + false_index),
                        -4.0 + 1.5 * false_index,
                    ]
                ) + rng.normal(0.0, 0.35, size=2)
                detections.append(
                    {
                        "detection_id": (
                            f"false-alarm-{frame_index:04d}-{false_index:02d}"
                        ),
                        "measurement_timestamp": timestamp,
                        "arrival_timestamp": timestamp + arrival_delay,
                        "position": clutter_position.tolist(),
                        "covariance": [[0.25, 0.0], [0.0, 0.25]],
                        "is_false_alarm": True,
                        "confidence": 0.45,
                    }
                )

        frames.append(
            {
                "frame_index": frame_index,
                "timestamp": timestamp,
                "measurement_timestamp": timestamp,
                "arrival_timestamp": timestamp + arrival_delay,
                "detections": detections,
                "truth_ids_present": truth_ids,
                "offline_truth_states": truth_states,
                "replay_metadata": {
                    "seed": seed,
                    "episode_id": f"d2-long-{target_count}target-{seed:04d}",
                    "scenario_name": scenario_name,
                    "scenario_version": scenario_version,
                    "scenario_tags": scenario_tags,
                    "target_count": target_count,
                    "measurement_count": len(detections),
                    "oosm_injected": frame_index in delayed_frames,
                },
            }
        )
    return frames


def _offline_frame_evidence(
    frame: Any,
    *,
    frame_index: int,
    online_detection_ids: Sequence[str],
) -> dict[str, Any]:
    _, detections, explicit_truth_ids = detections_from_airsim_frame(
        frame,
        frame_index=frame_index,
    )
    if len(online_detection_ids) != len(detections):
        raise ValueError("online detection count must match raw replay detection count")
    truth_by_detection = {
        str(online_detection_ids[index]): str(detection.truth_id)
        for index, detection in enumerate(detections)
        if detection.truth_id is not None
    }
    raw_items = _raw_items(frame)
    false_alarm_detection_ids: list[str] = []
    truth_state_by_id = _explicit_truth_states(frame)
    for item_index, item in enumerate(raw_items):
        detection_id = str(online_detection_ids[item_index])
        if bool(_value(item, "is_false_alarm", False)):
            false_alarm_detection_ids.append(detection_id)
        truth_id = truth_by_detection.get(detection_id)
        if truth_id is None:
            continue
        state = _truth_state(item)
        if state is not None:
            truth_state_by_id[truth_id] = state
    return {
        "truth_ids_present": sorted(set(explicit_truth_ids) | set(truth_state_by_id)),
        "truth_by_detection": truth_by_detection,
        "truth_state_by_id": truth_state_by_id,
        "false_alarm_detection_ids": false_alarm_detection_ids,
    }


def _detection_to_track(online_frame: Any, tracks_by_id: Mapping[str, Any]) -> dict[str, str]:
    result = {
        pair.detection_id: pair.track_id
        for pair in online_frame.association_result.matched_pairs
    }
    for track_id, track in tracks_by_id.items():
        detection_id = track.get("last_detection_id")
        if detection_id is not None:
            result.setdefault(str(detection_id), track_id)
    return result


def _nis_by_detection(online_frame: Any) -> dict[str, float]:
    result = online_frame.association_result
    distances = result.distance_matrix
    if distances is None:
        return {}
    track_order = [str(value) for value in result.metadata.get("track_order", [])]
    detection_order = [
        str(value) for value in result.metadata.get("detection_order", [])
    ]
    track_index = {track_id: index for index, track_id in enumerate(track_order)}
    detection_index = {
        detection_id: index for index, detection_id in enumerate(detection_order)
    }
    values: dict[str, float] = {}
    for pair in result.matched_pairs:
        row = track_index.get(pair.track_id)
        col = detection_index.get(pair.detection_id)
        if row is None or col is None:
            continue
        value = float(distances[row, col])
        if np.isfinite(value):
            values[pair.detection_id] = value
    return values


def _online_truth_isolation_violations(online_frame: Any) -> int:
    violations = 0
    for detection in online_frame.detections:
        if detection.truth_id is not None:
            violations += 1
        violations += _forbidden_truth_key_count(detection.metadata)
    for track in online_frame.active_tracks:
        if track.get("truth_id") is not None:
            violations += 1
        violations += _forbidden_truth_key_count(track)
    violations += _forbidden_truth_key_count(
        online_frame.association_result.metadata
    )
    return violations


def _forbidden_truth_key_count(value: Any) -> int:
    if isinstance(value, Mapping):
        count = sum(str(key).lower() in _TRUTH_METADATA_KEYS for key in value)
        return count + sum(_forbidden_truth_key_count(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return sum(_forbidden_truth_key_count(item) for item in value)
    return 0


def _position_squared_error(track: Mapping[str, Any], truth_state: Any) -> float | None:
    if truth_state is None:
        return None
    state = np.asarray(track.get("state"), dtype=float).reshape(-1)
    truth = np.asarray(truth_state, dtype=float).reshape(-1)
    if state.size < 2 or truth.size < 2:
        return None
    residual = state[:2] - truth[:2]
    return float(residual @ residual)


def _nees(track: Mapping[str, Any], truth_state: Any) -> float | None:
    if truth_state is None:
        return None
    state = np.asarray(track.get("state"), dtype=float).reshape(-1)
    truth = np.asarray(truth_state, dtype=float).reshape(-1)
    covariance = np.asarray(track.get("covariance"), dtype=float)
    if state.shape != (4,) or truth.shape != (4,) or covariance.shape != (4, 4):
        return None
    residual = state - truth
    try:
        solved = np.linalg.solve(covariance, residual)
    except np.linalg.LinAlgError:
        solved = np.linalg.pinv(covariance) @ residual
    value = float(residual @ solved)
    return value if np.isfinite(value) else None


def _distribution(values: Sequence[float], *, degrees_of_freedom: int) -> dict[str, Any]:
    finite = [float(value) for value in values if np.isfinite(value)]
    lower = float(chi2.ppf(0.025, degrees_of_freedom))
    upper = float(chi2.ppf(0.975, degrees_of_freedom))
    return {
        "available": bool(finite),
        "count": len(finite),
        "degrees_of_freedom": degrees_of_freedom,
        "mean": float(np.mean(finite)) if finite else None,
        "median": float(np.median(finite)) if finite else None,
        "confidence_level": 0.95,
        "chi_square_lower": lower,
        "chi_square_upper": upper,
        "in_bounds_rate": (
            sum(lower <= value <= upper for value in finite) / len(finite)
            if finite
            else None
        ),
    }


def _mean_ratio(numerator: Counter[str], denominator: Counter[str]) -> float:
    ratios = [
        numerator.get(key, 0) / value
        for key, value in denominator.items()
        if value > 0
    ]
    return float(np.mean(ratios)) if ratios else 0.0


def _latency(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, float(end) - float(start))


def _mean_available(values: Mapping[str, float | None]) -> float | None:
    available = [float(value) for value in values.values() if value is not None]
    return float(np.mean(available)) if available else None


def _availability_rate(values: Mapping[str, float | None]) -> float:
    return (
        sum(value is not None for value in values.values()) / len(values)
        if values
        else 0.0
    )


def _passes_m_of_n(
    accumulator: _TruthAccumulator,
    truth_id: str,
    *,
    profile: InitializationGovernanceProfile,
) -> bool:
    first_frame = accumulator.first_present_frame.get(truth_id)
    if first_frame is None:
        return False
    last_frame = first_frame + profile.window_scans_n
    hits = sum(
        first_frame <= frame_index < last_frame
        for frame_index in accumulator.assigned_frames.get(truth_id, set())
    )
    return hits >= profile.required_hits_m


def _raw_items(frame: Any) -> list[Any]:
    if isinstance(frame, Mapping):
        for key in ("detections", "tracks", "objects"):
            if key in frame:
                return list(frame[key])
    for key in ("detections", "tracks", "objects"):
        value = getattr(frame, key, None)
        if value is not None:
            return list(value)
    return []


def _explicit_truth_states(frame: Any) -> dict[str, list[float]]:
    value = _value(frame, "offline_truth_states", {})
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, list[float]] = {}
    for truth_id, state in value.items():
        array = np.asarray(state, dtype=float).reshape(-1)
        if array.size >= 4:
            result[str(truth_id)] = array[:4].tolist()
    return result


def _item_detection_id(item: Any, frame_index: int, item_index: int) -> str:
    for key in ("detection_id", "id", "track_id", "global_track_id", "object_id", "name"):
        value = _value(item, key, None)
        if value is not None:
            return str(value)
    return f"airsim-dry-run-{frame_index:04d}-{item_index:03d}"


def _truth_state(item: Any) -> list[float] | None:
    for key in ("offline_truth_state", "truth_state", "ground_truth_state"):
        value = _value(item, key, None)
        if value is not None:
            array = np.asarray(value, dtype=float).reshape(-1)
            if array.size >= 4:
                return array[:4].tolist()
    position = _value(item, "offline_truth_position", None)
    velocity = _value(item, "offline_truth_velocity", None)
    if position is None or velocity is None:
        return None
    return (
        np.concatenate(
            [
                np.asarray(position, dtype=float).reshape(-1)[:2],
                np.asarray(velocity, dtype=float).reshape(-1)[:2],
            ]
        )
        .astype(float)
        .tolist()
    )


def _value(item: Any, key: str, default: Any) -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)
