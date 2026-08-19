"""Causal contracts for the dual-optical online comparison benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import chi2

from .core import (
    AssociationConfig,
    AssociationState,
    AssociationStateRecord,
    AnonymousDetection,
    BearingSample,
    BearingTrack,
    CameraSpec,
    CameraState,
    CrossCameraCandidate,
    CrossCameraMatch,
    EpipolarEvidence,
    FragmentSuppressionRecord,
    GlobalAssignmentHypothesis,
    _fit_cross_camera_candidate,
    _ambiguity_resolution,
    _predicted_track_direction,
    _suppress_duplicate_fragments,
    _track_has_close_neighbor,
    build_epipolar_evidence,
    k_best_global_assignments,
    online_truth_leakage_keys,
)


DETECTION_FRAME_SCHEMA_V1 = "dual-optical-causal-detection-frame-v1"
REVOLUTION_SNAPSHOT_SCHEMA_V1 = "dual-optical-revolution-snapshot-v1"
ONLINE_ASSOCIATION_SCHEMA_V1 = "dual-optical-online-association-v1"
FROZEN_PARAMETERS_SCHEMA_V1 = "dual-optical-frozen-association-parameters-v1"


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256(
        "\x1f".join(str(part) for part in parts).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _stable_uniform(*parts: object) -> float:
    return _stable_seed(*parts) / float(2**64)


@dataclass(frozen=True)
class CorruptionProfile:
    level: str
    miss_probability: float
    instantaneous_false_rate_hz: float
    persistent_false_track_count: int
    persistent_duration_range_s: tuple[float, float] = (2.0, 4.0)

    def __post_init__(self) -> None:
        if not 0.0 <= self.miss_probability < 1.0:
            raise ValueError("miss_probability must be in [0, 1)")
        if self.instantaneous_false_rate_hz < 0.0:
            raise ValueError("false-alarm rate must be non-negative")
        if self.persistent_false_track_count < 0:
            raise ValueError("persistent false-track count must be non-negative")
        low, high = self.persistent_duration_range_s
        if low <= 0.0 or high < low:
            raise ValueError("invalid persistent false-track duration range")


CORRUPTION_PROFILES: Mapping[str, CorruptionProfile] = {
    "light": CorruptionProfile("light", 0.03, 2.0, 0),
    "medium": CorruptionProfile("medium", 0.07, 4.0, 1),
    "heavy": CorruptionProfile("heavy", 0.12, 8.0, 2),
}


@dataclass(frozen=True)
class DetectionFrameSnapshot:
    profile: str
    scenario_seed: int
    camera_state: CameraState
    detections: tuple[AnonymousDetection, ...]
    schema_version: str = DETECTION_FRAME_SCHEMA_V1
    input_fingerprint_sha256: str = ""

    def __post_init__(self) -> None:
        if self.profile not in CORRUPTION_PROFILES:
            raise ValueError(f"unknown corruption profile: {self.profile}")
        if any(item.camera_id != self.camera_state.camera_id for item in self.detections):
            raise ValueError("detection camera does not match nominal CameraState")
        if any(
            item.measurement_timestamp > self.camera_state.timestamp + 1e-9
            for item in self.detections
        ):
            raise ValueError("detection frame contains a future observation")
        payload = self._payload_without_fingerprint()
        leakage = online_truth_leakage_keys([payload])
        if leakage:
            raise ValueError(f"online detection frame contains truth fields: {leakage}")
        expected = _fingerprint(payload)
        if self.input_fingerprint_sha256 and self.input_fingerprint_sha256 != expected:
            raise ValueError("detection frame fingerprint mismatch")
        object.__setattr__(self, "input_fingerprint_sha256", expected)

    def _payload_without_fingerprint(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile,
            "scenario_seed": self.scenario_seed,
            "camera_state": asdict(self.camera_state),
            "detections": [asdict(item) for item in self.detections],
        }

    def to_dict(self) -> dict[str, Any]:
        return self._payload_without_fingerprint() | {
            "input_fingerprint_sha256": self.input_fingerprint_sha256
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass
class _PersistentFalseTrack:
    track_token: str
    start_timestamp: float
    end_timestamp: float
    start_center_px: tuple[float, float]
    velocity_px_s: tuple[float, float]
    extent_px: float


class CausalDetectionPerturber:
    """Derive byte-stable light/medium/heavy streams from one anonymous frame."""

    def __init__(
        self,
        *,
        scenario_seed: int,
        camera_spec: CameraSpec,
        sample_rate_hz: float,
        profiles: Mapping[str, CorruptionProfile] = CORRUPTION_PROFILES,
    ) -> None:
        if sample_rate_hz <= 0.0:
            raise ValueError("sample_rate_hz must be positive")
        self.scenario_seed = int(scenario_seed)
        self.camera_spec = camera_spec
        self.sample_rate_hz = float(sample_rate_hz)
        self.profiles = dict(profiles)
        self._last_frame: dict[tuple[str, str], int] = {}
        self._persistent: dict[tuple[str, str, int], _PersistentFalseTrack] = {}
        self._persistent_generation: dict[tuple[str, str, int], int] = {}

    def update(
        self,
        camera_state: CameraState,
        raw_detections: Sequence[AnonymousDetection],
    ) -> dict[str, DetectionFrameSnapshot]:
        ordered_raw = tuple(sorted(raw_detections, key=lambda item: item.detection_uid))
        if any(item.camera_id != camera_state.camera_id for item in ordered_raw):
            raise ValueError("raw detection camera does not match CameraState")
        if any(
            item.measurement_timestamp > camera_state.timestamp + 1e-9
            for item in ordered_raw
        ):
            raise ValueError("raw frame contains a future observation")
        outputs: dict[str, DetectionFrameSnapshot] = {}
        for level, profile in sorted(self.profiles.items()):
            key = (level, camera_state.camera_id)
            previous = self._last_frame.get(key, -1)
            if camera_state.frame_index <= previous:
                raise ValueError("causal perturber requires strictly increasing frames")
            self._last_frame[key] = camera_state.frame_index
            detections = [
                item
                for item in ordered_raw
                if _stable_uniform(
                    self.scenario_seed, "miss", item.detection_uid
                ) >= profile.miss_probability
            ]
            detections.extend(self._instantaneous_false_detections(profile, camera_state))
            detections.extend(self._persistent_false_detections(profile, camera_state))
            outputs[level] = DetectionFrameSnapshot(
                profile=level,
                scenario_seed=self.scenario_seed,
                camera_state=camera_state,
                detections=tuple(sorted(detections, key=lambda item: item.detection_uid)),
            )
        return outputs

    def _instantaneous_false_detections(
        self, profile: CorruptionProfile, state: CameraState
    ) -> tuple[AnonymousDetection, ...]:
        phase = _stable_uniform(
            self.scenario_seed, profile.level, state.camera_id, "instant-phase"
        )
        rate_per_frame = profile.instantaneous_false_rate_hz / self.sample_rate_hz
        current_total = math.floor((state.frame_index + 1) * rate_per_frame + phase)
        previous_total = math.floor(state.frame_index * rate_per_frame + phase)
        count = max(0, current_total - previous_total)
        return tuple(
            self._make_false_detection(
                profile,
                state,
                token=f"I{state.frame_index:06d}-{index:02d}",
                center_px=self._random_center(
                    profile.level, state.camera_id, state.frame_index, index, "instant"
                ),
                extent_px=3.0
                + 5.0
                * _stable_uniform(
                    self.scenario_seed,
                    profile.level,
                    state.camera_id,
                    state.frame_index,
                    index,
                    "instant-extent",
                ),
            )
            for index in range(count)
        )

    def _persistent_false_detections(
        self, profile: CorruptionProfile, state: CameraState
    ) -> tuple[AnonymousDetection, ...]:
        detections: list[AnonymousDetection] = []
        for slot in range(profile.persistent_false_track_count):
            key = (profile.level, state.camera_id, slot)
            track = self._persistent.get(key)
            if track is None or state.timestamp >= track.end_timestamp:
                generation = self._persistent_generation.get(key, 0)
                self._persistent_generation[key] = generation + 1
                track = self._new_persistent_track(
                    profile, state, slot=slot, generation=generation
                )
                self._persistent[key] = track
            elapsed = state.timestamp - track.start_timestamp
            center = (
                track.start_center_px[0] + track.velocity_px_s[0] * elapsed,
                track.start_center_px[1] + track.velocity_px_s[1] * elapsed,
            )
            margin = track.extent_px * 0.5
            center = (
                min(max(center[0], margin), self.camera_spec.width - margin),
                min(max(center[1], margin), self.camera_spec.height - margin),
            )
            detections.append(
                self._make_false_detection(
                    profile,
                    state,
                    token=f"P{slot:02d}-{track.track_token}",
                    center_px=center,
                    extent_px=track.extent_px,
                )
            )
        return tuple(detections)

    def _new_persistent_track(
        self,
        profile: CorruptionProfile,
        state: CameraState,
        *,
        slot: int,
        generation: int,
    ) -> _PersistentFalseTrack:
        token = f"G{generation:04d}"
        low, high = profile.persistent_duration_range_s
        duration = low + (high - low) * _stable_uniform(
            self.scenario_seed,
            profile.level,
            state.camera_id,
            slot,
            generation,
            "duration",
        )
        center = self._random_center(
            profile.level, state.camera_id, slot, generation, "persistent"
        )
        speed = 8.0 + 16.0 * _stable_uniform(
            self.scenario_seed,
            profile.level,
            state.camera_id,
            slot,
            generation,
            "speed",
        )
        angle = 2.0 * math.pi * _stable_uniform(
            self.scenario_seed,
            profile.level,
            state.camera_id,
            slot,
            generation,
            "direction",
        )
        return _PersistentFalseTrack(
            track_token=token,
            start_timestamp=state.timestamp,
            end_timestamp=state.timestamp + duration,
            start_center_px=center,
            velocity_px_s=(speed * math.cos(angle), speed * math.sin(angle)),
            extent_px=4.0
            + 5.0
            * _stable_uniform(
                self.scenario_seed,
                profile.level,
                state.camera_id,
                slot,
                generation,
                "extent",
            ),
        )

    def _random_center(self, *parts: object) -> tuple[float, float]:
        return (
            0.1 * self.camera_spec.width
            + 0.8
            * self.camera_spec.width
            * _stable_uniform(self.scenario_seed, *parts, "x"),
            0.1 * self.camera_spec.height
            + 0.8
            * self.camera_spec.height
            * _stable_uniform(self.scenario_seed, *parts, "y"),
        )

    def _make_false_detection(
        self,
        profile: CorruptionProfile,
        state: CameraState,
        *,
        token: str,
        center_px: tuple[float, float],
        extent_px: float,
    ) -> AnonymousDetection:
        half = extent_px * 0.5
        return AnonymousDetection(
            detection_uid=(
                f"{state.camera_id}-F{state.frame_index:05d}-"
                f"SYN-{profile.level}-{token}"
            ),
            camera_id=state.camera_id,
            frame_index=state.frame_index,
            measurement_timestamp=state.timestamp,
            arrival_timestamp=state.timestamp,
            bbox_xyxy=(
                center_px[0] - half,
                center_px[1] - half,
                center_px[0] + half,
                center_px[1] + half,
            ),
            center_px=center_px,
            confidence=0.25
            + 0.45
            * _stable_uniform(
                self.scenario_seed,
                profile.level,
                state.camera_id,
                state.frame_index,
                token,
                "confidence",
            ),
        )


def derive_causal_detection_streams(
    frames: Iterable[tuple[CameraState, Sequence[AnonymousDetection]]],
    *,
    scenario_seed: int,
    camera_spec: CameraSpec,
    sample_rate_hz: float,
) -> dict[str, tuple[DetectionFrameSnapshot, ...]]:
    """Derive all profiles deterministically from one ordered anonymous stream."""

    perturber = CausalDetectionPerturber(
        scenario_seed=scenario_seed,
        camera_spec=camera_spec,
        sample_rate_hz=sample_rate_hz,
    )
    result: dict[str, list[DetectionFrameSnapshot]] = {
        level: [] for level in CORRUPTION_PROFILES
    }
    ordered_frames = sorted(
        frames, key=lambda item: (item[0].frame_index, item[0].camera_id)
    )
    for state, detections in ordered_frames:
        derived = perturber.update(state, detections)
        for level, frame in derived.items():
            result[level].append(frame)
    return {level: tuple(values) for level, values in result.items()}


@dataclass(frozen=True)
class BearingTrackSnapshot:
    track_id: str
    camera_id: str
    samples: tuple[BearingSample, ...]
    hit_history: tuple[bool, ...] = ()
    track_state: str = "legacy"
    state_covariance: tuple[tuple[float, ...], ...] = ()

    @classmethod
    def from_track(
        cls, track: BearingTrack, *, cutoff_timestamp: float
    ) -> "BearingTrackSnapshot | None":
        samples = tuple(
            sample
            for sample in track.samples
            if sample.timestamp <= cutoff_timestamp + 1e-9
        )
        if not samples:
            return None
        return cls(
            track.track_id,
            track.camera_id,
            samples,
            track.hit_history,
            track.track_state,
            track.state_covariance,
        )

    def to_track(self) -> BearingTrack:
        return BearingTrack(
            self.track_id,
            self.camera_id,
            list(self.samples),
            self.hit_history,
            self.track_state,
            self.state_covariance,
        )


@dataclass(frozen=True)
class RevolutionSnapshot:
    scenario_seed: int
    corruption_level: str
    revolution_index: int
    cutoff_timestamp: float
    camera_a_id: str
    camera_b_id: str
    tracks_a: tuple[BearingTrackSnapshot, ...]
    tracks_b: tuple[BearingTrackSnapshot, ...]
    schema_version: str = REVOLUTION_SNAPSHOT_SCHEMA_V1
    input_fingerprint_sha256: str = ""

    def __post_init__(self) -> None:
        if self.revolution_index < 0 or self.cutoff_timestamp < 0.0:
            raise ValueError("invalid revolution boundary")
        for track in (*self.tracks_a, *self.tracks_b):
            if any(sample.timestamp > self.cutoff_timestamp + 1e-9 for sample in track.samples):
                raise ValueError("revolution snapshot contains a future sample")
            timestamps = [sample.timestamp for sample in track.samples]
            if timestamps != sorted(timestamps):
                raise ValueError("track samples must be time ordered")
        payload = self._payload_without_fingerprint()
        leakage = online_truth_leakage_keys([payload])
        if leakage:
            raise ValueError(f"online snapshot contains truth fields: {leakage}")
        expected = _fingerprint(payload)
        if self.input_fingerprint_sha256 and self.input_fingerprint_sha256 != expected:
            raise ValueError("revolution snapshot fingerprint mismatch")
        object.__setattr__(self, "input_fingerprint_sha256", expected)

    @classmethod
    def from_tracks(
        cls,
        *,
        scenario_seed: int,
        corruption_level: str,
        revolution_index: int,
        cutoff_timestamp: float,
        camera_a_id: str,
        camera_b_id: str,
        tracks_a: Sequence[BearingTrack],
        tracks_b: Sequence[BearingTrack],
    ) -> "RevolutionSnapshot":
        def freeze(tracks: Sequence[BearingTrack]) -> tuple[BearingTrackSnapshot, ...]:
            snapshots = (
                BearingTrackSnapshot.from_track(
                    track, cutoff_timestamp=cutoff_timestamp
                )
                for track in tracks
            )
            return tuple(
                sorted(
                    (item for item in snapshots if item is not None),
                    key=lambda item: item.track_id,
                )
            )

        return cls(
            scenario_seed=int(scenario_seed),
            corruption_level=str(corruption_level),
            revolution_index=int(revolution_index),
            cutoff_timestamp=float(cutoff_timestamp),
            camera_a_id=str(camera_a_id),
            camera_b_id=str(camera_b_id),
            tracks_a=freeze(tracks_a),
            tracks_b=freeze(tracks_b),
        )

    def _payload_without_fingerprint(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_seed": self.scenario_seed,
            "corruption_level": self.corruption_level,
            "revolution_index": self.revolution_index,
            "cutoff_timestamp": self.cutoff_timestamp,
            "camera_a_id": self.camera_a_id,
            "camera_b_id": self.camera_b_id,
            "tracks_a": [asdict(item) for item in self.tracks_a],
            "tracks_b": [asdict(item) for item in self.tracks_b],
        }

    def to_dict(self) -> dict[str, Any]:
        return self._payload_without_fingerprint() | {
            "input_fingerprint_sha256": self.input_fingerprint_sha256
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class FrozenAssociationParameters:
    association_config: Mapping[str, Any]
    tracker_revisit_gate_deg: float
    selected_on: str
    schema_version: str = FROZEN_PARAMETERS_SCHEMA_V1
    parameter_fingerprint_sha256: str = ""

    def __post_init__(self) -> None:
        if self.tracker_revisit_gate_deg <= 0.0:
            raise ValueError("tracker revisit gate must be positive")
        AssociationConfig(**dict(self.association_config))
        payload = self._payload_without_fingerprint()
        expected = _fingerprint(payload)
        if self.parameter_fingerprint_sha256 and self.parameter_fingerprint_sha256 != expected:
            raise ValueError("frozen parameter fingerprint mismatch")
        object.__setattr__(self, "parameter_fingerprint_sha256", expected)

    @classmethod
    def freeze(
        cls,
        config: AssociationConfig,
        *,
        tracker_revisit_gate_deg: float = 0.45,
        selected_on: str = "validation_only",
    ) -> "FrozenAssociationParameters":
        return cls(asdict(config), tracker_revisit_gate_deg, selected_on)

    @property
    def config(self) -> AssociationConfig:
        return AssociationConfig(**dict(self.association_config))

    def _payload_without_fingerprint(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "association_config": dict(self.association_config),
            "tracker_revisit_gate_deg": self.tracker_revisit_gate_deg,
            "selected_on": self.selected_on,
        }

    def to_dict(self) -> dict[str, Any]:
        return self._payload_without_fingerprint() | {
            "parameter_fingerprint_sha256": self.parameter_fingerprint_sha256
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    def write(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.to_json() + "\n", encoding="utf-8")
        return output

    @classmethod
    def from_json(cls, content: str) -> "FrozenAssociationParameters":
        payload = json.loads(content)
        if payload.get("schema_version") != FROZEN_PARAMETERS_SCHEMA_V1:
            raise ValueError("unsupported frozen parameter schema")
        return cls(
            association_config=dict(payload["association_config"]),
            tracker_revisit_gate_deg=float(payload["tracker_revisit_gate_deg"]),
            selected_on=str(payload["selected_on"]),
            schema_version=str(payload["schema_version"]),
            parameter_fingerprint_sha256=str(
                payload["parameter_fingerprint_sha256"]
            ),
        )

    @classmethod
    def read(cls, path: str | Path) -> "FrozenAssociationParameters":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))


def association_parameter_grid(
    *, base: AssociationConfig | None = None
) -> tuple[FrozenAssociationParameters, ...]:
    """Return the documented validation-only deterministic threshold grid."""

    base_values = asdict(base or AssociationConfig())
    candidates: list[FrozenAssociationParameters] = []
    for revisit_gate in (0.5, 1.0, 1.5, 2.0):
        for covariance_confidence in (0.95, 0.975, 0.99, 0.995):
            for unmatched_cost in (0.8, 1.0, 1.25, 1.5):
                for hits, window in ((2, 3),):
                    values = dict(base_values)
                    values.update(
                        covariance_gate_confidence=covariance_confidence,
                        unmatched_cost=unmatched_cost,
                        confirmation_hits=hits,
                        confirmation_window=window,
                        minimum_track_sweeps=2,
                        top_k=3,
                    )
                    candidates.append(
                        FrozenAssociationParameters.freeze(
                            AssociationConfig(**values),
                            tracker_revisit_gate_deg=revisit_gate,
                            selected_on="validation_grid_candidate",
                        )
                    )
    return tuple(candidates)


@dataclass(frozen=True)
class OnlineAssociationResult:
    revolution_index: int
    cutoff_timestamp: float
    source_snapshot_fingerprint_sha256: str
    parameter_fingerprint_sha256: str
    epipolar_evidence: tuple[EpipolarEvidence, ...]
    fitted_candidates: tuple[CrossCameraCandidate, ...]
    hypotheses: tuple[GlobalAssignmentHypothesis, ...]
    relation_states: tuple[AssociationStateRecord, ...]
    fragment_suppressions: tuple[FragmentSuppressionRecord, ...]
    selected_matches: tuple[CrossCameraMatch, ...]
    confirmed_matches: tuple[CrossCameraMatch, ...]
    unmatched_a_track_ids: tuple[str, ...]
    unmatched_b_track_ids: tuple[str, ...]
    full_pair_count: int
    coarse_gate_pass_count: int
    fit_evaluation_count: int
    cache_hit_count: int
    cache_miss_count: int
    screening_elapsed_ms: float
    fitting_elapsed_ms: float
    assignment_elapsed_ms: float
    processing_elapsed_ms: float
    schema_version: str = ONLINE_ASSOCIATION_SCHEMA_V1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass
class _CachedPair:
    signature_a: str
    signature_b: str
    evidence: EpipolarEvidence
    candidate: CrossCameraCandidate | None


@dataclass
class _SharedPairGeometry:
    approximate_residual_mrad: float
    approximate_normalized_chi2: float
    intersection_angle_deg: float
    raw_evidence: EpipolarEvidence | None = None
    candidates_by_confidence: dict[float, CrossCameraCandidate] = field(
        default_factory=dict
    )


class IncrementalTemporalAssociator:
    """Process one immutable revolution at a time without future observations."""

    def __init__(
        self,
        frozen_parameters: FrozenAssociationParameters,
        *,
        shared_geometry_cache: dict[
            tuple[str, str], _SharedPairGeometry
        ] | None = None,
    ) -> None:
        self.frozen_parameters = frozen_parameters
        self.config = frozen_parameters.config
        self._last_revolution_index = -1
        self._last_cutoff_timestamp = -math.inf
        self._last_snapshot_fingerprint = ""
        self._last_result: OnlineAssociationResult | None = None
        self._pair_cache: dict[tuple[str, str], _CachedPair] = {}
        self._shared_geometry_cache = shared_geometry_cache
        self._mapping_history: dict[tuple[str, str], list[bool]] = {}
        self._relation_states: dict[tuple[str, str], AssociationState] = {}
        self._contradiction_streaks: dict[tuple[str, str], int] = {}
        self._last_selected_timestamp: dict[tuple[str, str], float] = {}
        self._support_numerators: dict[tuple[str, str], float] = {}
        self._support_denominators: dict[tuple[str, str], float] = {}
        self._previous_mapping: dict[str, str] = {}
        self._ambiguity_ages: dict[tuple[str, str], int] = {}

    def process_snapshot(self, snapshot: RevolutionSnapshot) -> OnlineAssociationResult:
        if snapshot.input_fingerprint_sha256 == self._last_snapshot_fingerprint:
            if self._last_result is None:
                raise RuntimeError("idempotent snapshot cache is inconsistent")
            return self._last_result
        if snapshot.revolution_index <= self._last_revolution_index:
            raise ValueError("revolution snapshots must be strictly increasing")
        if snapshot.cutoff_timestamp <= self._last_cutoff_timestamp:
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
        signature_a = {track.track_id: self._track_signature(track) for track in tracks_a}
        signature_b = {track.track_id: self._track_signature(track) for track in tracks_b}
        evidence_items: list[EpipolarEvidence] = []
        candidate_items: list[CrossCameraCandidate] = []
        cache_hits = 0
        cache_misses = 0
        screening_elapsed_ms = 0.0
        fitting_elapsed_ms = 0.0
        active_pairs: set[tuple[str, str]] = set()
        prefilter = _vectorized_coplanarity_prefilter(
            tracks_a,
            tracks_b,
            timestamp=snapshot.cutoff_timestamp,
            gate_mrad=(
                self.config.coplanarity_median_gate_mrad
                * self.config.online_prefilter_multiplier
            ),
        )
        for row, track_a in enumerate(tracks_a):
            for column, track_b in enumerate(tracks_b):
                pair = (track_a.track_id, track_b.track_id)
                active_pairs.add(pair)
                cached = self._pair_cache.get(pair)
                if (
                    cached is not None
                    and cached.signature_a == signature_a[track_a.track_id]
                    and cached.signature_b == signature_b[track_b.track_id]
                ):
                    cache_hits += 1
                    evidence = cached.evidence
                    candidate = cached.candidate
                else:
                    cache_misses += 1
                    candidate = None
                    shared_key = (
                        signature_a[track_a.track_id],
                        signature_b[track_b.track_id],
                    )
                    shared = (
                        None
                        if self._shared_geometry_cache is None
                        else self._shared_geometry_cache.get(shared_key)
                    )
                    if shared is None:
                        (
                            approximate_residual,
                            approximate_normalized_chi2,
                            intersection_angle,
                        ) = prefilter[
                            row, column
                        ]
                        shared = _SharedPairGeometry(
                            approximate_residual_mrad=approximate_residual,
                            approximate_normalized_chi2=approximate_normalized_chi2,
                            intersection_angle_deg=intersection_angle,
                        )
                        if self._shared_geometry_cache is not None:
                            self._shared_geometry_cache[shared_key] = shared
                    approximate_residual = shared.approximate_residual_mrad
                    approximate_normalized_chi2 = (
                        shared.approximate_normalized_chi2
                    )
                    intersection_angle = shared.intersection_angle_deg
                    prefilter_gate = float(
                        chi2.ppf(self.config.covariance_gate_confidence, df=1)
                        * self.config.online_prefilter_multiplier
                    )
                    passed = bool(
                        math.isfinite(approximate_normalized_chi2)
                        and approximate_normalized_chi2 <= prefilter_gate
                    )
                    if passed:
                        if shared.raw_evidence is None:
                            screening_started = time.perf_counter()
                            raw_config = replace(
                                self.config,
                                coplanarity_median_gate_mrad=1.0e9,
                            )
                            shared.raw_evidence = build_epipolar_evidence(
                                track_a, track_b, config=raw_config
                            )
                            screening_elapsed_ms += (
                                time.perf_counter() - screening_started
                            ) * 1000.0
                        evidence = _evidence_for_config(
                            shared.raw_evidence, self.config
                        )
                        if evidence.gate_passed:
                            confidence_key = self.config.covariance_gate_confidence
                            if confidence_key not in shared.candidates_by_confidence:
                                fitting_started = time.perf_counter()
                                shared.candidates_by_confidence[confidence_key] = (
                                    _fit_cross_camera_candidate(
                                    track_a,
                                    track_b,
                                    expected_speed_mps=self.config.expected_speed_mps,
                                    max_time_delta_s=self.config.max_time_delta_s,
                                    covariance_gate_confidence=confidence_key,
                                    )
                                )
                                fitting_elapsed_ms += (
                                    time.perf_counter() - fitting_started
                                ) * 1000.0
                            candidate = shared.candidates_by_confidence[confidence_key]
                    else:
                        evidence = EpipolarEvidence(
                            track_a_id=track_a.track_id,
                            track_b_id=track_b.track_id,
                            gate_passed=False,
                            rejection_reason="online_vectorized_coplanarity_prefilter",
                            aligned_sample_count=1,
                            timestamps_s=(snapshot.cutoff_timestamp,),
                            residuals_mrad=(approximate_residual,),
                            residual_median_mrad=approximate_residual,
                            residual_p90_mrad=approximate_residual,
                            residual_mad_mrad=0.0,
                            residual_slope_mrad_per_s=0.0,
                            intersection_angle_median_deg=intersection_angle,
                            normalized_residuals_chi2=(
                                approximate_normalized_chi2,
                            ),
                            normalized_residual_median_chi2=(
                                approximate_normalized_chi2
                            ),
                            normalized_residual_p90_chi2=(
                                approximate_normalized_chi2
                            ),
                            chi_square_gate=prefilter_gate,
                            covariance_gate_confidence=(
                                self.config.covariance_gate_confidence
                            ),
                            covariance_source="prefilter_track_prediction",
                        )
                    self._pair_cache[pair] = _CachedPair(
                        signature_a[track_a.track_id],
                        signature_b[track_b.track_id],
                        evidence,
                        candidate,
                    )
                evidence_items.append(evidence)
                if candidate is not None:
                    candidate_items.append(candidate)
        for pair in tuple(self._pair_cache):
            if pair not in active_pairs:
                del self._pair_cache[pair]
        assignment_started = time.perf_counter()
        hypotheses = k_best_global_assignments(
            tracks_a,
            tracks_b,
            candidate_items,
            config=self.config,
            previous_mapping=self._previous_mapping,
        )
        current_pairs = set(hypotheses[0].matches) if hypotheses else set()
        pair_supports: dict[tuple[str, str], float] = {}
        for hypothesis in hypotheses:
            for pair in hypothesis.matches:
                pair_supports[pair] = (
                    pair_supports.get(pair, 0.0) + hypothesis.normalized_support
                )
        candidate_by_pair = {
            (item.track_a_id, item.track_b_id): item for item in candidate_items
        }
        active_by_id = {item.track_id: item for item in (*tracks_a, *tracks_b)}
        state_records: list[AssociationStateRecord] = []
        universe = set(self._relation_states) | set(pair_supports) | current_pairs
        smoothed_supports: dict[tuple[str, str], float] = {}
        for pair in sorted(universe):
            current_support = pair_supports.get(pair, 0.0)
            self._support_numerators[pair] = (
                self.config.history_discount
                * self._support_numerators.get(pair, 0.0)
                + current_support
            )
            self._support_denominators[pair] = (
                self.config.history_discount
                * self._support_denominators.get(pair, 0.0)
                + 1.0
            )
            smoothed_supports[pair] = self._support_numerators[pair] / max(
                self._support_denominators[pair], 1e-12
            )
        for pair in sorted(universe):
            current_support = pair_supports.get(pair, 0.0)
            smoothed_support = smoothed_supports[pair]
            history = self._mapping_history.setdefault(pair, [])
            history.append(pair in current_pairs)
            del history[: -self.config.confirmation_window]
            hits = sum(history)
            competing_support = max(
                (
                    support
                    for candidate_pair, support in pair_supports.items()
                    if candidate_pair != pair
                    and (
                        candidate_pair[0] == pair[0]
                        or candidate_pair[1] == pair[1]
                    )
                ),
                default=0.0,
            )
            track_a = active_by_id.get(pair[0])
            track_b = active_by_id.get(pair[1])
            crossing_alert = bool(
                track_a is not None
                and track_b is not None
                and (
                    _track_has_close_neighbor(
                        track_a,
                        tracks_a,
                        snapshot.cutoff_timestamp,
                        self.config.crossing_separation_deg,
                    )
                    or _track_has_close_neighbor(
                        track_b,
                        tracks_b,
                        snapshot.cutoff_timestamp,
                        self.config.crossing_separation_deg,
                    )
                )
            )
            previous_state = self._relation_states.get(pair)
            contradiction = self._contradiction_streaks.get(pair, 0)
            ambiguous = bool(
                crossing_alert
                or competing_support >= self.config.competing_support_gate
            )
            ambiguity_age, ambiguity_resolved, retained_hypothesis_count = (
                _ambiguity_resolution(
                    pair,
                    selected_pairs=current_pairs,
                    pair_supports=pair_supports,
                    smoothed_supports=smoothed_supports,
                    candidate_costs={
                        candidate_pair: candidate_by_pair[candidate_pair].cost
                        for candidate_pair in pair_supports
                        if candidate_pair in candidate_by_pair
                    },
                    previous_age=self._ambiguity_ages.get(pair, 0),
                    ambiguous=ambiguous,
                    config=self.config,
                )
            )
            self._ambiguity_ages[pair] = ambiguity_age
            if pair in current_pairs:
                self._last_selected_timestamp[pair] = snapshot.cutoff_timestamp
                contradiction = 0
                if ambiguous and not ambiguity_resolved:
                    state: AssociationState = "pending"
                    reason = (
                        "crossing_alert"
                        if crossing_alert
                        else "competing_hypothesis"
                    )
                elif previous_state == "confirmed":
                    state = "confirmed"
                    reason = "confirmation_maintained"
                elif (
                    len(history) >= self.config.confirmation_window
                    and hits >= self.config.confirmation_hits
                    and smoothed_support >= self.config.confirmation_support
                ):
                    state = "confirmed"
                    reason = (
                        "ambiguity_resolved_after_two_revolutions"
                        if ambiguity_resolved
                        else "temporal_confirmation"
                    )
                elif previous_state in {"pending", "tentative"}:
                    state = "pending"
                    reason = "confirmation_window_incomplete"
                else:
                    state = "tentative"
                    reason = "first_global_hypothesis"
            else:
                conflicting = any(
                    other[0] == pair[0] or other[1] == pair[1]
                    for other in current_pairs
                )
                if previous_state == "confirmed" and conflicting:
                    contradiction += 1
                    if contradiction >= self.config.contradiction_epochs:
                        state = "pending"
                        reason = "contradictory_revolutions"
                    else:
                        state = "confirmed"
                        reason = "single_contradiction_held"
                elif previous_state in {"confirmed", "coasting"} and not conflicting:
                    last_seen = self._last_selected_timestamp.get(pair, -math.inf)
                    if (
                        snapshot.cutoff_timestamp - last_seen
                        <= self.config.coasting_duration_s + 1e-9
                    ):
                        state = "coasting"
                        reason = "temporarily_unobserved"
                    else:
                        state = "rejected"
                        reason = "coasting_expired"
                else:
                    state = "rejected"
                    reason = "not_in_best_hypothesis"
            self._relation_states[pair] = state
            self._contradiction_streaks[pair] = contradiction
            state_records.append(
                AssociationStateRecord(
                    epoch_index=snapshot.revolution_index,
                    timestamp=snapshot.cutoff_timestamp,
                    track_a_id=pair[0],
                    track_b_id=pair[1],
                    state=state,
                    pair_support=float(current_support),
                    smoothed_support=float(smoothed_support),
                    competing_support=float(competing_support),
                    crossing_alert=crossing_alert,
                    mapping_hits_in_window=hits,
                    contradiction_streak=contradiction,
                    reason=reason,
                    ambiguity_age_revolutions=ambiguity_age,
                    retained_hypothesis_count=retained_hypothesis_count,
                )
            )
        self._previous_mapping = (
            dict(hypotheses[0].matches) if hypotheses else self._previous_mapping
        )
        retained_pairs, suppressions = _suppress_duplicate_fragments(
            tuple(
                pair
                for pair in sorted(current_pairs)
                if pair in candidate_by_pair and candidate_by_pair[pair].valid
            ),
            candidate_by_pair,
            self._relation_states,
            self.config,
        )
        selected: list[CrossCameraMatch] = []
        confirmed: list[CrossCameraMatch] = []
        for pair in retained_pairs:
            candidate = candidate_by_pair[pair]
            match = CrossCameraMatch(
                match_id=f"ONLINE-R{snapshot.revolution_index:03d}-PAIR-{len(selected)+1:03d}",
                track_a_id=pair[0],
                track_b_id=pair[1],
                cost=candidate.cost,
                reference_timestamp=candidate.reference_timestamp,
                position_ned=candidate.position_ned,
                velocity_ned=candidate.velocity_ned,
            )
            selected.append(match)
            if self._relation_states.get(pair) == "confirmed":
                confirmed.append(match)
        matched_a = {item.track_a_id for item in selected}
        matched_b = {item.track_b_id for item in selected}
        assignment_elapsed_ms = (time.perf_counter() - assignment_started) * 1000.0
        result = OnlineAssociationResult(
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            source_snapshot_fingerprint_sha256=snapshot.input_fingerprint_sha256,
            parameter_fingerprint_sha256=(
                self.frozen_parameters.parameter_fingerprint_sha256
            ),
            epipolar_evidence=tuple(evidence_items),
            fitted_candidates=tuple(candidate_items),
            hypotheses=hypotheses,
            relation_states=tuple(state_records),
            fragment_suppressions=suppressions,
            selected_matches=tuple(selected),
            confirmed_matches=tuple(confirmed),
            unmatched_a_track_ids=tuple(
                item.track_id for item in tracks_a if item.track_id not in matched_a
            ),
            unmatched_b_track_ids=tuple(
                item.track_id for item in tracks_b if item.track_id not in matched_b
            ),
            full_pair_count=len(tracks_a) * len(tracks_b),
            coarse_gate_pass_count=sum(item.gate_passed for item in evidence_items),
            fit_evaluation_count=len(candidate_items),
            cache_hit_count=cache_hits,
            cache_miss_count=cache_misses,
            screening_elapsed_ms=screening_elapsed_ms,
            fitting_elapsed_ms=fitting_elapsed_ms,
            assignment_elapsed_ms=assignment_elapsed_ms,
            processing_elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
        self._last_revolution_index = snapshot.revolution_index
        self._last_cutoff_timestamp = snapshot.cutoff_timestamp
        self._last_snapshot_fingerprint = snapshot.input_fingerprint_sha256
        self._last_result = result
        return result

    @staticmethod
    def _track_signature(track: BearingTrack) -> str:
        return _fingerprint(
            {
                "track_id": track.track_id,
                "camera_id": track.camera_id,
                "samples": [asdict(sample) for sample in track.samples],
            }
        )


def _evidence_for_config(
    evidence: EpipolarEvidence, config: AssociationConfig
) -> EpipolarEvidence:
    reasons: list[str] = []
    if evidence.aligned_sample_count < config.min_aligned_samples:
        reasons.append("insufficient_aligned_samples")
    gate = float(chi2.ppf(config.covariance_gate_confidence, df=1))
    if (
        math.isfinite(evidence.normalized_residual_p90_chi2)
        and evidence.normalized_residual_p90_chi2 > gate
    ):
        reasons.append("normalized_coplanarity_chi2")
    if not math.isfinite(evidence.normalized_residual_p90_chi2):
        reasons.append("degenerate_geometry")
    return replace(
        evidence,
        gate_passed=not reasons,
        rejection_reason="|".join(reasons),
        chi_square_gate=gate,
        covariance_gate_confidence=config.covariance_gate_confidence,
    )


def _vectorized_coplanarity_prefilter(
    tracks_a: Sequence[BearingTrack],
    tracks_b: Sequence[BearingTrack],
    *,
    timestamp: float,
    gate_mrad: float,
) -> np.ndarray:
    """Return raw residual, approximate chi-square, and intersection angle."""

    result = np.empty((len(tracks_a), len(tracks_b)), dtype=object)
    if not tracks_a or not tracks_b:
        return result
    directions_a = np.asarray(
        [_predicted_track_direction(item, timestamp) for item in tracks_a], dtype=float
    )
    directions_b = np.asarray(
        [_predicted_track_direction(item, timestamp) for item in tracks_b], dtype=float
    )
    origin_a = np.asarray(tracks_a[0].samples[-1].origin_ned, dtype=float)
    origin_b = np.asarray(tracks_b[0].samples[-1].origin_ned, dtype=float)
    baseline = origin_b - origin_a
    baseline_norm = float(np.linalg.norm(baseline))
    if baseline_norm <= 1e-9:
        raise ValueError("coplanarity prefilter requires a non-zero baseline")
    baseline /= baseline_norm
    normals_a = np.cross(directions_a, baseline)
    normals_b = np.cross(directions_b, baseline)
    norms_a = np.linalg.norm(normals_a, axis=1)
    norms_b = np.linalg.norm(normals_b, axis=1)
    valid_a = norms_a > 1e-9
    valid_b = norms_b > 1e-9
    normalized_a = normals_a / np.maximum(norms_a[:, None], 1e-12)
    normalized_b = normals_b / np.maximum(norms_b[:, None], 1e-12)
    residual_a = np.arcsin(
        np.clip(np.abs(normalized_a @ directions_b.T), 0.0, 1.0)
    )
    residual_b = np.arcsin(
        np.clip(np.abs(directions_a @ normalized_b.T), 0.0, 1.0)
    )
    residuals = 500.0 * (residual_a + residual_b)
    dot_products = np.clip(np.abs(directions_a @ directions_b.T), 0.0, 1.0)
    angles = np.degrees(np.arccos(dot_products))
    valid = valid_a[:, None] & valid_b[None, :]
    residuals = np.where(valid, residuals, float("inf"))
    variances_a = np.asarray(
        [
            float(
                np.max(
                    np.linalg.eigvalsh(
                        item.samples[-1].predicted_angular_covariance_rad2(timestamp)
                    )
                )
            )
            for item in tracks_a
        ],
        dtype=float,
    )
    variances_b = np.asarray(
        [
            float(
                np.max(
                    np.linalg.eigvalsh(
                        item.samples[-1].predicted_angular_covariance_rad2(timestamp)
                    )
                )
            )
            for item in tracks_b
        ],
        dtype=float,
    )
    approximate_variance = np.maximum(
        variances_a[:, None] + variances_b[None, :], 1.0e-12
    )
    normalized_chi2 = np.square(residuals / 1000.0) / approximate_variance
    for row in range(len(tracks_a)):
        for column in range(len(tracks_b)):
            residual = float(residuals[row, column])
            result[row, column] = (
                residual,
                float(normalized_chi2[row, column]),
                float(angles[row, column]),
            )
    return result
