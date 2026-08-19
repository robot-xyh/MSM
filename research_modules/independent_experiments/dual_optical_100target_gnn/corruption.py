"""Deterministic missed-detection and false-alarm injection."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np

from .schema import (
    AnonymousTrack,
    CAUSAL_TRANSIENT_FALSE_ALARMS_PER_SECOND,
    CorruptionConfig,
    CorruptionSummary,
    OfflineLabels,
    OnlineEpisode,
    TrackSample,
)


_LEVEL_OFFSETS = {"light": 101, "medium": 211, "heavy": 307}


def corruption_seed(episode_seed: int, level: str) -> int:
    if level not in _LEVEL_OFFSETS:
        raise KeyError(f"unknown corruption level: {level}")
    return int((episode_seed * 1009 + _LEVEL_OFFSETS[level]) % (2**32 - 1))


def _keyed_rng(*values: object) -> np.random.Generator:
    payload = "|".join(str(value) for value in values).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(payload).digest()[:8], "little")
    return np.random.default_rng(seed)


def _unit(vector: np.ndarray) -> tuple[float, float, float]:
    vector = np.asarray(vector, dtype=float)
    vector /= max(float(np.linalg.norm(vector)), 1e-12)
    return tuple(float(value) for value in vector)


def _camera_reference(
    tracks: tuple[AnonymousTrack, ...],
) -> tuple[np.ndarray, float, float, dict[int, float]]:
    samples = [sample for track in tracks for sample in track.samples]
    directions = np.asarray([sample.direction_ned for sample in samples], dtype=float)
    reference = np.mean(directions, axis=0)
    reference /= max(float(np.linalg.norm(reference)), 1e-12)
    positive_areas = [sample.bbox_area_px2 for sample in samples if sample.bbox_area_px2 > 0.0]
    area = float(np.median(positive_areas)) if positive_areas else 16.0
    confidence = float(np.median([sample.confidence for sample in samples])) if samples else 0.5
    by_sweep: dict[int, list[float]] = {}
    for sample in samples:
        by_sweep.setdefault(sample.sweep_index, []).append(sample.timestamp)
    sweep_times = {key: float(np.median(value)) for key, value in by_sweep.items()}
    return reference, area, confidence, sweep_times


def _jittered_direction(
    reference: np.ndarray,
    rng: np.random.Generator,
    *,
    noise_std: float,
    drift: np.ndarray | None = None,
    step: int = 0,
) -> tuple[float, float, float]:
    perturbation = rng.normal(0.0, noise_std, size=3)
    if drift is not None:
        perturbation += drift * float(step)
    return _unit(reference + perturbation)


def corrupt_episode(
    episode: OnlineEpisode,
    labels: OfflineLabels,
    config: CorruptionConfig,
) -> tuple[OnlineEpisode, OfflineLabels, CorruptionSummary]:
    """Apply corruption using anonymous track data; labels are copied separately."""

    seed = corruption_seed(episode.seed, config.name)
    rng = np.random.default_rng(seed)
    tracks_out: dict[str, list[AnonymousTrack]] = {
        camera_id: [] for camera_id in episode.camera_ids
    }
    identities = dict(labels.track_identity)
    dropped = 0
    retained = 0
    transient_count = 0
    persistent_count = 0

    for camera_id in episode.camera_ids:
        measured = episode.tracks[camera_id]
        reference, area, confidence, sweep_times = _camera_reference(measured)
        sweep_indices = sorted(sweep_times)

        for track in measured:
            kept = tuple(
                sample
                for sample in track.samples
                if rng.random() >= config.miss_probability
            )
            dropped += len(track.samples) - len(kept)
            retained += len(kept)
            if kept:
                tracks_out[camera_id].append(replace(track, samples=kept))

        for sweep_index in sweep_indices:
            for alarm_index in range(config.transient_false_alarms_per_half_sweep):
                track_id = (
                    f"{camera_id}-FA-I-{config.name[:1].upper()}-"
                    f"S{sweep_index:04d}-{alarm_index:02d}"
                )
                sample = TrackSample(
                    sweep_index=sweep_index,
                    timestamp=sweep_times[sweep_index] + float(rng.normal(0.0, 0.01)),
                    direction_ned=_jittered_direction(
                        reference, rng, noise_std=0.02
                    ),
                    detection_count=1,
                    bbox_area_px2=max(1.0, area * float(rng.uniform(0.4, 1.6))),
                    confidence=float(np.clip(confidence * rng.uniform(0.35, 0.8), 0.05, 0.95)),
                )
                tracks_out[camera_id].append(
                    AnonymousTrack(track_id, camera_id, (sample,), "transient_false_alarm")
                )
                identities[track_id] = None
                transient_count += 1

        for false_index in range(config.persistent_false_tracks_per_camera):
            if len(sweep_indices) < 4:
                raise ValueError("at least four half sweeps are required for persistent false tracks")
            length = min(len(sweep_indices), int(rng.integers(4, min(9, len(sweep_indices)) + 1)))
            start = int(rng.integers(0, len(sweep_indices) - length + 1))
            selected_sweeps = sweep_indices[start : start + length]
            false_reference = np.asarray(
                _jittered_direction(reference, rng, noise_std=0.02), dtype=float
            )
            drift = rng.normal(0.0, 0.0001, size=3)
            samples = []
            for step, sweep_index in enumerate(selected_sweeps):
                samples.append(
                    TrackSample(
                        sweep_index=sweep_index,
                        timestamp=sweep_times[sweep_index] + float(rng.normal(0.0, 0.015)),
                        direction_ned=_jittered_direction(
                            false_reference,
                            rng,
                            noise_std=0.00015,
                            drift=drift,
                            step=step,
                        ),
                        detection_count=1,
                        bbox_area_px2=max(1.0, area * float(rng.uniform(0.55, 1.45))),
                        confidence=float(np.clip(confidence * rng.uniform(0.45, 0.9), 0.05, 0.98)),
                    )
                )
            track_id = f"{camera_id}-FA-P-{config.name[:1].upper()}-{false_index:03d}"
            tracks_out[camera_id].append(
                AnonymousTrack(
                    track_id,
                    camera_id,
                    tuple(samples),
                    "persistent_false_alarm",
                )
            )
            identities[track_id] = None
            persistent_count += 1

    corrupted = replace(
        episode,
        tracks={key: tuple(value) for key, value in tracks_out.items()},
    )
    summary = CorruptionSummary(
        level=config.name,
        corruption_seed=seed,
        dropped_sample_count=dropped,
        retained_sample_count=retained,
        transient_false_track_count=transient_count,
        persistent_false_track_count=persistent_count,
    )
    return (
        corrupted,
        OfflineLabels(identities, labels.expected_identities, labels.source_hashes),
        summary,
    )


def corrupt_episode_causal(
    episode: OnlineEpisode,
    labels: OfflineLabels,
    config: CorruptionConfig,
    *,
    scan_period_s: float = 2.0,
) -> tuple[OnlineEpisode, OfflineLabels, CorruptionSummary]:
    """Create prefix-stable corruption; no early decision depends on future samples."""

    if scan_period_s <= 0.0:
        raise ValueError("scan_period_s must be positive")
    seed = corruption_seed(episode.seed, config.name)
    tracks_out: dict[str, list[AnonymousTrack]] = {
        camera_id: [] for camera_id in episode.camera_ids
    }
    identities = dict(labels.track_identity)
    dropped = retained = transient_count = persistent_count = 0
    alarm_rate = CAUSAL_TRANSIENT_FALSE_ALARMS_PER_SECOND[config.name]

    for camera_id in episode.camera_ids:
        measured = episode.tracks[camera_id]
        source_by_sweep: dict[int, list[TrackSample]] = {}
        for track in measured:
            for sample in track.samples:
                source_by_sweep.setdefault(sample.sweep_index, []).append(sample)
        by_sweep: dict[int, list[TrackSample]] = {}
        for track in measured:
            kept = []
            for sample_index, sample in enumerate(track.samples):
                rng = _keyed_rng(
                    seed,
                    "miss",
                    camera_id,
                    track.track_id,
                    sample_index,
                    f"{sample.timestamp:.9f}",
                )
                if rng.random() < config.miss_probability:
                    dropped += 1
                    continue
                retained += 1
                kept.append(sample)
                by_sweep.setdefault(sample.sweep_index, []).append(sample)
            if kept:
                tracks_out[camera_id].append(replace(track, samples=tuple(kept)))

        sweep_indices = sorted(source_by_sweep)
        for sweep_index in sweep_indices:
            sweep_samples = source_by_sweep[sweep_index]
            directions = np.asarray(
                [sample.direction_ned for sample in sweep_samples], dtype=float
            )
            reference = np.mean(directions, axis=0)
            reference /= max(float(np.linalg.norm(reference)), 1.0e-12)
            positive_areas = [
                sample.bbox_area_px2
                for sample in sweep_samples
                if sample.bbox_area_px2 > 0.0
            ]
            area = float(np.median(positive_areas)) if positive_areas else 16.0
            confidence = float(
                np.median([sample.confidence for sample in sweep_samples])
            )
            timestamp = float(np.median([sample.timestamp for sample in sweep_samples]))
            alarm_count = int(round(alarm_rate * scan_period_s))
            for alarm_index in range(alarm_count):
                rng = _keyed_rng(
                    seed, "transient", camera_id, sweep_index, alarm_index
                )
                track_id = (
                    f"{camera_id}-FA-C-I-{config.name[:1].upper()}-"
                    f"R{sweep_index:04d}-{alarm_index:02d}"
                )
                sample = TrackSample(
                    sweep_index=sweep_index,
                    timestamp=max(0.0, timestamp + float(rng.normal(0.0, 0.01))),
                    direction_ned=_jittered_direction(reference, rng, noise_std=0.02),
                    detection_count=1,
                    bbox_area_px2=max(1.0, area * float(rng.uniform(0.4, 1.6))),
                    confidence=float(
                        np.clip(confidence * rng.uniform(0.35, 0.8), 0.05, 0.95)
                    ),
                )
                tracks_out[camera_id].append(
                    AnonymousTrack(
                        track_id,
                        camera_id,
                        (sample,),
                        "transient_false_alarm",
                    )
                )
                identities[track_id] = None
                transient_count += 1

        for false_index in range(config.persistent_false_tracks_per_camera):
            samples = []
            drift_rng = _keyed_rng(seed, "persistent-drift", camera_id, false_index)
            drift = drift_rng.normal(0.0, 0.0001, size=3)
            for step, sweep_index in enumerate(sweep_indices):
                sweep_samples = source_by_sweep[sweep_index]
                directions = np.asarray(
                    [sample.direction_ned for sample in sweep_samples], dtype=float
                )
                reference = np.mean(directions, axis=0)
                reference /= max(float(np.linalg.norm(reference)), 1.0e-12)
                rng = _keyed_rng(
                    seed, "persistent", camera_id, false_index, sweep_index
                )
                timestamp = float(
                    np.median([sample.timestamp for sample in sweep_samples])
                )
                positive_areas = [
                    sample.bbox_area_px2
                    for sample in sweep_samples
                    if sample.bbox_area_px2 > 0.0
                ]
                area = float(np.median(positive_areas)) if positive_areas else 16.0
                confidence = float(
                    np.median([sample.confidence for sample in sweep_samples])
                )
                samples.append(
                    TrackSample(
                        sweep_index=sweep_index,
                        timestamp=max(0.0, timestamp + float(rng.normal(0.0, 0.015))),
                        direction_ned=_jittered_direction(
                            reference,
                            rng,
                            noise_std=0.00015,
                            drift=drift,
                            step=step,
                        ),
                        detection_count=1,
                        bbox_area_px2=max(1.0, area * float(rng.uniform(0.55, 1.45))),
                        confidence=float(
                            np.clip(confidence * rng.uniform(0.45, 0.9), 0.05, 0.98)
                        ),
                    )
                )
            track_id = f"{camera_id}-FA-C-P-{config.name[:1].upper()}-{false_index:03d}"
            if samples:
                tracks_out[camera_id].append(
                    AnonymousTrack(
                        track_id,
                        camera_id,
                        tuple(samples),
                        "persistent_false_alarm",
                    )
                )
                identities[track_id] = None
                persistent_count += 1

    corrupted = replace(
        episode,
        tracks={key: tuple(value) for key, value in tracks_out.items()},
    )
    summary = CorruptionSummary(
        level=config.name,
        corruption_seed=seed,
        dropped_sample_count=dropped,
        retained_sample_count=retained,
        transient_false_track_count=transient_count,
        persistent_false_track_count=persistent_count,
    )
    return (
        corrupted,
        OfflineLabels(identities, labels.expected_identities, labels.source_hashes),
        summary,
    )
