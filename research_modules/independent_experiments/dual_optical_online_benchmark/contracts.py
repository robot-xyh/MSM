"""Stable main-owned contracts shared by the isolated association routes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "dual-optical-online-benchmark-v3"
PREVIOUS_SCHEMA_VERSION = "dual-optical-online-benchmark-v2"
LEGACY_SCHEMA_VERSION = "dual-optical-online-benchmark-v1"
CORRUPTION_LEVELS = ("clean", "light", "medium", "heavy")
LEGACY_CORRUPTION_LEVELS = ("light", "medium", "heavy")
S180_CORRUPTION_LEVELS = ("clean", "light")
LEGACY_ROUTE_NAMES = ("epipolar_mht", "lightweight", "gnn")
ROUTE_NAMES = (*LEGACY_ROUTE_NAMES, "track_superglue")
SUPPORTED_TARGET_COUNTS = (20, 40, 60, 100)
SHARED_CANDIDATE_GRAPH_VERSION = "maturity-covariance-epipolar-topk-v2"
CANDIDATE_GATE_CONFIG_VERSION = "candidate-gate-ablation-v1"
CANDIDATE_GATE_STRATEGY_NAMES = ("baseline", "moderate", "wide")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class CandidateGatePolicy:
    """Explicit candidate-gate policy used by derived ablation snapshots."""

    strategy_name: str
    normalized_gate_sigma: float
    top_k_by_target_count: tuple[tuple[int, int], ...]
    config_version: str = CANDIDATE_GATE_CONFIG_VERSION

    def __post_init__(self) -> None:
        if self.strategy_name not in CANDIDATE_GATE_STRATEGY_NAMES:
            raise ValueError("unsupported candidate-gate strategy")
        if self.config_version != CANDIDATE_GATE_CONFIG_VERSION:
            raise ValueError("unsupported candidate-gate config version")
        if not math.isfinite(self.normalized_gate_sigma) or self.normalized_gate_sigma <= 0.0:
            raise ValueError("candidate-gate sigma must be positive and finite")
        target_counts = [int(target_count) for target_count, _ in self.top_k_by_target_count]
        if target_counts != sorted(set(target_counts)):
            raise ValueError("candidate-gate target counts must be unique and sorted")
        if any(int(target_count) <= 0 or int(top_k) <= 0 for target_count, top_k in self.top_k_by_target_count):
            raise ValueError("candidate-gate target counts and top-K values must be positive")

    def top_k(self, target_count: int) -> int:
        values = dict(self.top_k_by_target_count)
        try:
            return int(values[int(target_count)])
        except KeyError as exc:
            raise ValueError(
                f"strategy {self.strategy_name!r} has no top-K for "
                f"target_count={target_count}"
            ) from exc

    @property
    def fingerprint(self) -> str:
        return _sha256(asdict(self))

    @property
    def top_k_policy_text(self) -> str:
        return ",".join(
            f"{target_count}:{top_k}"
            for target_count, top_k in self.top_k_by_target_count
        )


_CANDIDATE_GATE_POLICIES = {
    "baseline": CandidateGatePolicy(
        strategy_name="baseline",
        normalized_gate_sigma=8.0,
        top_k_by_target_count=((20, 8), (40, 10), (60, 12)),
    ),
    "moderate": CandidateGatePolicy(
        strategy_name="moderate",
        normalized_gate_sigma=10.0,
        top_k_by_target_count=((20, 12), (40, 15), (60, 18)),
    ),
    "wide": CandidateGatePolicy(
        strategy_name="wide",
        normalized_gate_sigma=12.0,
        top_k_by_target_count=((20, 16), (40, 20), (60, 24)),
    ),
}


def candidate_gate_policy(strategy_name: str) -> CandidateGatePolicy:
    """Return one frozen named policy without exposing the mutable registry."""

    try:
        return _CANDIDATE_GATE_POLICIES[str(strategy_name)]
    except KeyError as exc:
        raise ValueError(f"unsupported candidate-gate strategy: {strategy_name}") from exc


@dataclass(frozen=True)
class BenchmarkProtocol:
    """Frozen scenario and split definition for the formal comparison."""

    train_seeds: tuple[int, ...] = tuple(range(20270101, 20270125))
    validation_seeds: tuple[int, ...] = tuple(range(20270125, 20270131))
    test_seeds: tuple[int, ...] = tuple(range(20270201, 20270221))
    target_count: int = 100
    target_speed_mps: float = 50.0
    zero_heading_count: int = 50
    minus_thirty_heading_count: int = 50
    duration_s: float = 12.0
    scan_period_s: float = 2.0
    scan_span_deg: float = 360.0
    camera_b_scan_phase_offset_s: float = 0.0
    deterministic_step_mode: str = "legacy_wall_yield"
    sample_rate_hz: float = 100.0
    clock_speed: float = 0.1
    gimbal_fixed_bias_rms_mrad: float = 0.4
    gimbal_jitter_rms_mrad: float = 0.3
    online_deadline_ms: float = 1000.0
    corruption_levels: tuple[str, ...] = LEGACY_CORRUPTION_LEVELS
    scan_profile: str = "continuous_360_v1"
    scan_mode: str = "continuous_360"
    scan_half_span_deg: float = 180.0
    association_round_period_s: float = 2.0

    def __post_init__(self) -> None:
        splits = {
            "train": self.train_seeds,
            "validation": self.validation_seeds,
            "test": self.test_seeds,
        }
        sets = {name: set(values) for name, values in splits.items()}
        if any(len(values) != len(sets[name]) for name, values in splits.items()):
            raise ValueError("benchmark seed splits contain duplicates")
        if sets["train"] & sets["validation"] or sets["train"] & sets["test"] or sets["validation"] & sets["test"]:
            raise ValueError("benchmark seed splits must be disjoint")
        if self.target_count not in SUPPORTED_TARGET_COUNTS:
            raise ValueError("target_count must be one of 20, 40, 60, or 100")
        expected_split_sizes = (24, 6, 20) if self.target_count == 100 else (8, 2, 5)
        actual_split_sizes = (
            len(self.train_seeds),
            len(self.validation_seeds),
            len(self.test_seeds),
        )
        if actual_split_sizes != expected_split_sizes:
            raise ValueError(
                "formal benchmark seed split does not match target scale: "
                f"expected={expected_split_sizes}, actual={actual_split_sizes}"
            )
        if self.zero_heading_count + self.minus_thirty_heading_count != self.target_count:
            raise ValueError("heading groups must cover every target")
        if self.scan_mode not in {"continuous_360", "triangle"}:
            raise ValueError("unsupported scan mode")
        if not self.scan_profile:
            raise ValueError("scan profile cannot be empty")
        if not math.isfinite(self.scan_half_span_deg) or self.scan_half_span_deg <= 0.0:
            raise ValueError("scan half span must be positive and finite")
        if not math.isfinite(self.scan_period_s) or self.scan_period_s <= 0.0:
            raise ValueError("mechanical scan period must be positive and finite")
        if (
            not math.isfinite(self.association_round_period_s)
            or self.association_round_period_s <= 0.0
        ):
            raise ValueError("association round period must be positive and finite")
        round_count = self.duration_s / self.association_round_period_s
        if not math.isclose(round_count, round(round_count), abs_tol=1e-12):
            raise ValueError("duration must contain an integer number of association rounds")
        if self.scan_mode == "continuous_360":
            if not math.isclose(self.scan_half_span_deg, 180.0, abs_tol=1e-12):
                raise ValueError("continuous scan must retain a 180 degree half span")
            if not math.isclose(
                self.association_round_period_s, self.scan_period_s, abs_tol=1e-12
            ):
                raise ValueError("continuous scan publishes once per revolution")
        elif not math.isclose(
            self.association_round_period_s,
            self.scan_period_s * 0.5,
            abs_tol=1e-12,
        ):
            raise ValueError("triangle scan publishes once per one-way pass")
        if not 0.0 <= self.camera_b_scan_phase_offset_s < self.scan_period_s:
            raise ValueError("camera B scan phase offset must remain within one revolution")
        if self.deterministic_step_mode not in {"legacy_wall_yield", "paused_continue"}:
            raise ValueError("unsupported deterministic AirSim step mode")
        if self.corruption_levels not in {
            CORRUPTION_LEVELS,
            LEGACY_CORRUPTION_LEVELS,
            S180_CORRUPTION_LEVELS,
        }:
            raise ValueError("formal corruption levels are fixed")

    @property
    def revolution_count(self) -> int:
        """Compatibility name for the number of association publication rounds."""

        return self.association_round_count

    @property
    def association_round_count(self) -> int:
        return int(round(self.duration_s / self.association_round_period_s))

    @property
    def mechanical_cycle_count(self) -> int:
        return int(round(self.duration_s / self.scan_period_s))

    @property
    def fingerprint(self) -> str:
        values = asdict(self)
        if self.is_legacy_continuous_profile:
            for key in (
                "scan_profile",
                "scan_mode",
                "scan_half_span_deg",
                "association_round_period_s",
            ):
                values.pop(key)
            schema_version = PREVIOUS_SCHEMA_VERSION
        else:
            schema_version = SCHEMA_VERSION
        return _sha256({"schema_version": schema_version, **values})

    @property
    def is_legacy_continuous_profile(self) -> bool:
        return (
            self.scan_profile == "continuous_360_v1"
            and self.scan_mode == "continuous_360"
            and math.isclose(self.scan_half_span_deg, 180.0, abs_tol=1e-12)
            and math.isclose(
                self.association_round_period_s, self.scan_period_s, abs_tol=1e-12
            )
        )


def benchmark_protocol_for_target_count(target_count: int) -> BenchmarkProtocol:
    """Build one isolated tier protocol without reusing the sealed 100-target test set."""

    target_count = int(target_count)
    if target_count not in SUPPORTED_TARGET_COUNTS:
        raise ValueError("target_count must be one of 20, 40, 60, or 100")
    train_count, validation_count, test_count = (
        (24, 6, 20) if target_count == 100 else (8, 2, 5)
    )
    seed_base = 20280000 + target_count * 100
    # V3 held-out episodes at 20/40/60 targets were opened during development.
    # V4 therefore keeps the calibration seeds and moves only those sealed test
    # sets to a new, disjoint +301 range.  The untouched 100-target set already
    # starts at +201 and remains unchanged.
    test_seed_offset = 201 if target_count == 100 else 301
    return BenchmarkProtocol(
        train_seeds=tuple(range(seed_base + 1, seed_base + train_count + 1)),
        validation_seeds=tuple(
            range(seed_base + 101, seed_base + 101 + validation_count)
        ),
        test_seeds=tuple(
            range(seed_base + test_seed_offset, seed_base + test_seed_offset + test_count)
        ),
        target_count=target_count,
        zero_heading_count=target_count // 2,
        minus_thirty_heading_count=target_count - target_count // 2,
        corruption_levels=CORRUPTION_LEVELS,
    )


_S180_SEEDS = {
    20: (
        tuple(range(20283001, 20283009)),
        tuple(range(20283101, 20283103)),
        tuple(range(20283301, 20283306)),
    ),
    40: (
        tuple(range(20285001, 20285009)),
        tuple(range(20285101, 20285103)),
        tuple(range(20285301, 20285306)),
    ),
    60: (
        tuple(range(20287001, 20287009)),
        tuple(range(20287101, 20287103)),
        tuple(range(20287301, 20287306)),
    ),
}


def s180_protocol_for_target_count(target_count: int) -> BenchmarkProtocol:
    """Return the frozen 1-second one-way 180-degree S180 protocol."""

    target_count = int(target_count)
    try:
        train_seeds, validation_seeds, test_seeds = _S180_SEEDS[target_count]
    except KeyError as exc:
        raise ValueError("S180 target_count must be one of 20, 40, or 60") from exc
    return BenchmarkProtocol(
        train_seeds=train_seeds,
        validation_seeds=validation_seeds,
        test_seeds=test_seeds,
        target_count=target_count,
        zero_heading_count=target_count // 2,
        minus_thirty_heading_count=target_count - target_count // 2,
        duration_s=12.0,
        scan_period_s=2.0,
        scan_span_deg=180.0,
        corruption_levels=S180_CORRUPTION_LEVELS,
        scan_profile="s180_triangle_1s_v1",
        scan_mode="triangle",
        scan_half_span_deg=90.0,
        association_round_period_s=1.0,
    )


def benchmark_protocol_from_mapping(values: Mapping[str, Any]) -> BenchmarkProtocol:
    """Restore the exact protocol recorded in a manifest or freeze marker."""

    return BenchmarkProtocol(
        **{
            key: tuple(value)
            if key.endswith("_seeds") or key == "corruption_levels"
            else value
            for key, value in values.items()
        }
    )


@dataclass(frozen=True)
class SnapshotTrackSample:
    sweep_index: int
    timestamp: float
    direction_ned: tuple[float, float, float]
    detection_count: int
    bbox_area_px2: float
    confidence: float
    measurement_covariance_deg2: tuple[float, float, float, float] = (
        0.001,
        0.0,
        0.0,
        0.001,
    )
    state_vector: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    state_covariance: tuple[float, ...] = tuple(float(index % 5 == 0) for index in range(16))
    innovation_mahalanobis2: float = 0.0

    def __post_init__(self) -> None:
        if self.sweep_index < 0 or self.timestamp < 0.0:
            raise ValueError("track sample time fields must be non-negative")
        if len(self.direction_ned) != 3 or not all(math.isfinite(value) for value in self.direction_ned):
            raise ValueError("direction_ned must contain three finite values")
        norm = math.sqrt(sum(value * value for value in self.direction_ned))
        if not math.isclose(norm, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError("direction_ned must be normalized")
        if len(self.measurement_covariance_deg2) != 4 or len(self.state_vector) != 4:
            raise ValueError("snapshot bearing state dimensions are invalid")
        if len(self.state_covariance) != 16:
            raise ValueError("snapshot state covariance must be 4x4")
        if not all(
            math.isfinite(value)
            for value in (
                *self.measurement_covariance_deg2,
                *self.state_vector,
                *self.state_covariance,
                self.innovation_mahalanobis2,
            )
        ):
            raise ValueError("snapshot bearing state contains non-finite values")
        if self.innovation_mahalanobis2 < 0.0:
            raise ValueError("innovation Mahalanobis distance cannot be negative")


@dataclass(frozen=True)
class SnapshotTrack:
    track_id: str
    camera_id: str
    samples: tuple[SnapshotTrackSample, ...]
    source_kind: str = "measured"
    track_state: str = "tentative"
    recent_sweep_hits: tuple[bool, bool, bool] = (False, False, False)
    missed_sweep_count: int = 0
    ambiguity_count: int = 0

    def __post_init__(self) -> None:
        if not self.track_id or not self.camera_id:
            raise ValueError("snapshot track identifiers cannot be empty")
        timestamps = [sample.timestamp for sample in self.samples]
        if timestamps != sorted(timestamps):
            raise ValueError("snapshot track samples must be time ordered")
        if self.track_state not in {
            "tentative",
            "confirmed",
            "coasting",
            "dormant",
            "terminated",
        }:
            raise ValueError("unsupported snapshot track state")
        if len(self.recent_sweep_hits) != 3:
            raise ValueError("snapshot track must carry a three-sweep hit window")
        if self.missed_sweep_count < 0 or self.ambiguity_count < 0:
            raise ValueError("snapshot track counters cannot be negative")


@dataclass(frozen=True)
class RevolutionSnapshot:
    """Anonymous cumulative data available at one revolution boundary."""

    protocol_fingerprint: str
    seed: int
    split: str
    corruption_level: str
    revolution_index: int
    cutoff_timestamp: float
    camera_ids: tuple[str, str]
    camera_positions_ned: Mapping[str, tuple[float, float, float]]
    focal_length_px: float
    tracks: Mapping[str, tuple[SnapshotTrack, ...]]
    target_count: int | None = None
    tracker_fingerprint: str = "legacy-unfrozen-tracker"
    geometry_candidate_pairs: tuple[tuple[str, str], ...] = ()
    candidate_graph_fingerprint: str = ""
    candidate_graph_summary: Mapping[str, int | float | str] = field(
        default_factory=dict
    )
    corruption_summary: Mapping[str, int | float | str] = field(default_factory=dict)
    source_hashes: Mapping[str, str] = field(default_factory=dict)
    association_round_period_s: float = 2.0
    association_round_count: int = 6
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.split not in {"train", "validation", "test"}:
            raise ValueError("invalid benchmark split")
        if self.corruption_level not in CORRUPTION_LEVELS:
            raise ValueError("invalid corruption level")
        if self.association_round_period_s <= 0.0 or self.association_round_count <= 0:
            raise ValueError("snapshot association round definition is invalid")
        if not 1 <= self.revolution_index <= self.association_round_count:
            raise ValueError("revolution_index is outside the association round range")
        expected_cutoff = float(
            self.revolution_index * self.association_round_period_s
        )
        if not math.isclose(self.cutoff_timestamp, expected_cutoff, abs_tol=1e-9):
            raise ValueError("snapshot cutoff does not match revolution boundary")
        if len(self.camera_ids) != 2 or self.camera_ids[0] == self.camera_ids[1]:
            raise ValueError("snapshot requires two distinct cameras")
        if set(self.tracks) != set(self.camera_ids):
            raise ValueError("snapshot tracks do not cover both cameras")
        if self.target_count is not None and self.target_count <= 0:
            raise ValueError("snapshot target_count must be positive")
        if not self.tracker_fingerprint:
            raise ValueError("snapshot must identify its shared tracker")
        if self.schema_version not in {
            SCHEMA_VERSION,
            PREVIOUS_SCHEMA_VERSION,
            LEGACY_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported revolution snapshot schema")
        for camera_id in self.camera_ids:
            if camera_id not in self.camera_positions_ned:
                raise ValueError(f"missing camera position for {camera_id}")
            for track in self.tracks[camera_id]:
                if track.camera_id != camera_id:
                    raise ValueError("snapshot track camera mismatch")
                if any(sample.timestamp > self.cutoff_timestamp + 1e-9 for sample in track.samples):
                    raise ValueError("snapshot contains future observations")
        track_a_ids = {track.track_id for track in self.tracks[self.camera_ids[0]]}
        track_b_ids = {track.track_id for track in self.tracks[self.camera_ids[1]]}
        normalized_pairs = tuple(
            (str(track_a_id), str(track_b_id))
            for track_a_id, track_b_id in self.geometry_candidate_pairs
        )
        if len(normalized_pairs) != len(set(normalized_pairs)):
            raise ValueError("shared candidate graph contains duplicate edges")
        if any(
            track_a_id not in track_a_ids or track_b_id not in track_b_ids
            for track_a_id, track_b_id in normalized_pairs
        ):
            raise ValueError("shared candidate graph references an unknown track")
        expected_graph_fingerprint = candidate_graph_fingerprint(
            normalized_pairs,
            self.candidate_graph_summary,
        )
        if normalized_pairs and self.candidate_graph_fingerprint != expected_graph_fingerprint:
            raise ValueError("shared candidate graph fingerprint mismatch")
        if not normalized_pairs and self.candidate_graph_fingerprint not in {
            "",
            expected_graph_fingerprint,
        }:
            raise ValueError("empty shared candidate graph fingerprint mismatch")

    def online_payload(self) -> dict[str, Any]:
        tracks: dict[str, list[dict[str, Any]]] = {}
        for camera_id in self.camera_ids:
            values: list[dict[str, Any]] = []
            for track in self.tracks[camera_id]:
                if self.schema_version == LEGACY_SCHEMA_VERSION:
                    values.append(
                        {
                            "track_id": track.track_id,
                            "camera_id": track.camera_id,
                            "samples": [
                                {
                                    "sweep_index": sample.sweep_index,
                                    "timestamp": sample.timestamp,
                                    "direction_ned": list(sample.direction_ned),
                                    "detection_count": sample.detection_count,
                                    "bbox_area_px2": sample.bbox_area_px2,
                                    "confidence": sample.confidence,
                                }
                                for sample in track.samples
                            ],
                            "source_kind": track.source_kind,
                        }
                    )
                else:
                    values.append(asdict(track))
            tracks[camera_id] = values
        payload = {
            "schema_version": self.schema_version,
            "protocol_fingerprint": self.protocol_fingerprint,
            "seed": self.seed,
            "split": self.split,
            "corruption_level": self.corruption_level,
            "revolution_index": self.revolution_index,
            "cutoff_timestamp": self.cutoff_timestamp,
            "camera_ids": list(self.camera_ids),
            "camera_positions_ned": {
                key: list(self.camera_positions_ned[key]) for key in sorted(self.camera_positions_ned)
            },
            "focal_length_px": self.focal_length_px,
            "tracks": tracks,
            "target_count": self.target_count,
            "geometry_candidate_pairs": [
                [track_a_id, track_b_id]
                for track_a_id, track_b_id in self.geometry_candidate_pairs
            ],
            "candidate_graph_fingerprint": self.candidate_graph_fingerprint,
            "candidate_graph_summary": dict(self.candidate_graph_summary),
            "corruption_summary": dict(self.corruption_summary),
            "source_hashes": dict(self.source_hashes),
        }
        if self.schema_version in {SCHEMA_VERSION, PREVIOUS_SCHEMA_VERSION}:
            payload["tracker_fingerprint"] = self.tracker_fingerprint
        if self.schema_version == SCHEMA_VERSION:
            payload["association_round_period_s"] = self.association_round_period_s
            payload["association_round_count"] = self.association_round_count
        return payload

    @classmethod
    def from_online_payload(cls, payload: Mapping[str, Any]) -> "RevolutionSnapshot":
        schema_version = payload.get("schema_version")
        if schema_version not in {
            SCHEMA_VERSION,
            PREVIOUS_SCHEMA_VERSION,
            LEGACY_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported revolution snapshot schema")
        camera_ids = tuple(str(value) for value in payload["camera_ids"])
        if len(camera_ids) != 2:
            raise ValueError("snapshot requires exactly two camera IDs")
        tracks = {
            camera_id: tuple(
                SnapshotTrack(
                    track_id=str(track["track_id"]),
                    camera_id=str(track["camera_id"]),
                    source_kind=str(track.get("source_kind", "measured")),
                    track_state=str(track.get("track_state", "tentative")),
                    recent_sweep_hits=tuple(
                        bool(value)
                        for value in track.get(
                            "recent_sweep_hits", (False, False, False)
                        )
                    ),
                    missed_sweep_count=int(track.get("missed_sweep_count", 0)),
                    ambiguity_count=int(track.get("ambiguity_count", 0)),
                    samples=tuple(
                        SnapshotTrackSample(
                            sweep_index=int(sample["sweep_index"]),
                            timestamp=float(sample["timestamp"]),
                            direction_ned=tuple(
                                float(value) for value in sample["direction_ned"]
                            ),
                            detection_count=int(sample["detection_count"]),
                            bbox_area_px2=float(sample["bbox_area_px2"]),
                            confidence=float(sample["confidence"]),
                            measurement_covariance_deg2=tuple(
                                float(value)
                                for value in sample.get(
                                    "measurement_covariance_deg2",
                                    (0.001, 0.0, 0.0, 0.001),
                                )
                            ),
                            state_vector=tuple(
                                float(value)
                                for value in sample.get(
                                    "state_vector", (0.0, 0.0, 0.0, 0.0)
                                )
                            ),
                            state_covariance=tuple(
                                float(value)
                                for value in sample.get(
                                    "state_covariance",
                                    tuple(float(index % 5 == 0) for index in range(16)),
                                )
                            ),
                            innovation_mahalanobis2=float(
                                sample.get("innovation_mahalanobis2", 0.0)
                            ),
                        )
                        for sample in track["samples"]
                    ),
                )
                for track in payload["tracks"][camera_id]
            )
            for camera_id in camera_ids
        }
        return cls(
            protocol_fingerprint=str(payload["protocol_fingerprint"]),
            seed=int(payload["seed"]),
            split=str(payload["split"]),
            corruption_level=str(payload["corruption_level"]),
            revolution_index=int(payload["revolution_index"]),
            cutoff_timestamp=float(payload["cutoff_timestamp"]),
            camera_ids=(camera_ids[0], camera_ids[1]),
            camera_positions_ned={
                str(key): tuple(float(value) for value in values)
                for key, values in payload["camera_positions_ned"].items()
            },
            focal_length_px=float(payload["focal_length_px"]),
            tracks=tracks,
            target_count=(
                None
                if payload.get("target_count") is None
                else int(payload["target_count"])
            ),
            tracker_fingerprint=str(
                payload.get("tracker_fingerprint", "legacy-unfrozen-tracker")
            ),
            geometry_candidate_pairs=tuple(
                (str(pair[0]), str(pair[1]))
                for pair in payload.get("geometry_candidate_pairs", ())
            ),
            candidate_graph_fingerprint=str(
                payload.get("candidate_graph_fingerprint", "")
            ),
            candidate_graph_summary=dict(
                payload.get("candidate_graph_summary", {})
            ),
            corruption_summary=dict(payload.get("corruption_summary", {})),
            source_hashes={
                str(key): str(value)
                for key, value in payload.get("source_hashes", {}).items()
            },
            association_round_period_s=float(
                payload.get("association_round_period_s", 2.0)
            ),
            association_round_count=int(payload.get("association_round_count", 6)),
            schema_version=str(schema_version),
        )


def snapshot_fingerprint(snapshot: RevolutionSnapshot) -> str:
    return _sha256(snapshot.online_payload())


def candidate_graph_fingerprint(
    pairs: Sequence[tuple[str, str]],
    summary: Mapping[str, int | float | str],
) -> str:
    """Fingerprint the anonymous whitelist and the frozen construction policy."""

    return _sha256(
        {
            "version": SHARED_CANDIDATE_GRAPH_VERSION,
            "pairs": [[str(left), str(right)] for left, right in pairs],
            "summary": {
                key: value
                for key, value in summary.items()
                if not str(key).endswith("_ms")
            },
        }
    )


@dataclass(frozen=True)
class AssociationMatch:
    track_a_id: str
    track_b_id: str
    score: float
    decision_state: str


@dataclass(frozen=True)
class AssociationPublication:
    route_name: str
    route_version: str
    model_fingerprint: str
    seed: int
    corruption_level: str
    revolution_index: int
    cutoff_timestamp: float
    input_fingerprint: str
    availability: str
    matches: tuple[AssociationMatch, ...]
    rejection_reasons: Mapping[str, int] = field(default_factory=dict)
    candidate_graph_fingerprint: str = ""
    stage_latencies_ms: Mapping[str, float] = field(default_factory=dict)
    scoring_ms: float = 0.0
    hungarian_ms: float = 0.0
    end_to_end_ms: float = 0.0
    deadline_ms: float = 1000.0

    def __post_init__(self) -> None:
        if self.route_name not in ROUTE_NAMES:
            raise ValueError("invalid route name")
        if self.corruption_level not in CORRUPTION_LEVELS:
            raise ValueError("invalid corruption level")
        if self.revolution_index < 1:
            raise ValueError("invalid revolution index")
        if any(value < 0.0 or not math.isfinite(value) for value in (self.scoring_ms, self.hungarian_ms, self.end_to_end_ms)):
            raise ValueError("publication latency values must be finite and non-negative")
        if any(
            value < 0.0 or not math.isfinite(value)
            for value in self.stage_latencies_ms.values()
        ):
            raise ValueError("publication stage latencies must be finite and non-negative")
        if self.end_to_end_ms + 1e-9 < self.scoring_ms + self.hungarian_ms:
            raise ValueError("end-to-end latency cannot be below measured stages")
        track_a_ids = [match.track_a_id for match in self.matches]
        track_b_ids = [match.track_b_id for match in self.matches]
        if len(track_a_ids) != len(set(track_a_ids)) or len(track_b_ids) != len(set(track_b_ids)):
            raise ValueError("publication violates one-to-one assignment")
        if self.availability == "timeout" and self.matches:
            raise ValueError("timed-out publications cannot backfill matches")

    @property
    def deadline_met(self) -> bool:
        return self.end_to_end_ms <= self.deadline_ms


def publication_fingerprint(publication: AssociationPublication) -> str:
    return _sha256(asdict(publication))


def write_json(path: str | Path, payload: Any) -> None:
    """Write canonical, newline-terminated JSON through an explicit main call."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(_canonical_json(payload) + b"\n")


def read_snapshot(path: str | Path) -> RevolutionSnapshot:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    snapshot = RevolutionSnapshot.from_online_payload(payload)
    if payload.get("input_fingerprint") not in {None, snapshot_fingerprint(snapshot)}:
        raise ValueError("stored revolution snapshot fingerprint mismatch")
    return snapshot


def write_snapshot(path: str | Path, snapshot: RevolutionSnapshot) -> None:
    payload = snapshot.online_payload()
    payload["input_fingerprint"] = snapshot_fingerprint(snapshot)
    write_json(path, payload)


def validate_shared_publications(
    snapshot: RevolutionSnapshot,
    publications: Sequence[AssociationPublication],
    *,
    expected_routes: Sequence[str] = ROUTE_NAMES,
) -> None:
    expected = snapshot_fingerprint(snapshot)
    route_names = [item.route_name for item in publications]
    normalized_routes = tuple(str(route) for route in expected_routes)
    if (
        not normalized_routes
        or len(normalized_routes) != len(set(normalized_routes))
        or any(route not in ROUTE_NAMES for route in normalized_routes)
    ):
        raise ValueError("expected publication routes are invalid")
    if sorted(route_names) != sorted(normalized_routes):
        raise ValueError("one publication from each active route is required")
    for item in publications:
        if item.input_fingerprint != expected:
            raise ValueError(f"{item.route_name} did not consume the shared snapshot")
        if (
            snapshot.candidate_graph_fingerprint
            and item.candidate_graph_fingerprint
            and item.candidate_graph_fingerprint
            != snapshot.candidate_graph_fingerprint
        ):
            raise ValueError(
                f"{item.route_name} did not consume the shared candidate graph"
            )
        if item.seed != snapshot.seed or item.corruption_level != snapshot.corruption_level:
            raise ValueError("publication scenario identity does not match snapshot")
        if item.revolution_index != snapshot.revolution_index or not math.isclose(item.cutoff_timestamp, snapshot.cutoff_timestamp, abs_tol=1e-9):
            raise ValueError("publication time boundary does not match snapshot")
