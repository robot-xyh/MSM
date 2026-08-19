from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    snapshot_fingerprint,
)
from dual_optical_target_track_gnn.contracts import (
    PAIR_PUBLICATION_ROUTE,
    PAIR_PUBLICATION_SCHEMA_VERSION,
    ConfirmedTrackPair,
    online_pair_publication_fingerprint,
)


CAMERA_POSITIONS = {
    "camera_a": (0.0, -1000.0, 0.0),
    "camera_b": (0.0, 1000.0, 0.0),
}
TARGET_POSITION = np.asarray((3000.0, 100.0, -120.0), dtype=float)
TARGET_VELOCITY = np.asarray((-50.0, 5.0, 1.0), dtype=float)


def direction_to_target(
    camera_position: Sequence[float],
    timestamp: float,
    *,
    position: np.ndarray = TARGET_POSITION,
    velocity: np.ndarray = TARGET_VELOCITY,
) -> tuple[float, float, float]:
    relative = position + velocity * timestamp - np.asarray(camera_position, dtype=float)
    relative /= np.linalg.norm(relative)
    return tuple(float(value) for value in relative)


def make_track(
    camera_id: str,
    track_id: str,
    timestamps: Sequence[float],
    *,
    camera_positions: Mapping[str, tuple[float, float, float]] = CAMERA_POSITIONS,
    position: np.ndarray = TARGET_POSITION,
    velocity: np.ndarray = TARGET_VELOCITY,
    source_kind: str = "anonymous",
    variance_deg2: float = 1.0e-6,
    direction_override: tuple[float, float, float] | None = None,
) -> SnapshotTrack:
    samples = tuple(
        SnapshotTrackSample(
            sweep_index=max(0, int(math.floor(timestamp / 2.0))),
            timestamp=float(timestamp),
            direction_ned=(
                direction_override
                if direction_override is not None
                else direction_to_target(
                    camera_positions[camera_id],
                    timestamp,
                    position=position,
                    velocity=velocity,
                )
            ),
            detection_count=1,
            bbox_area_px2=25.0,
            confidence=0.9,
            measurement_covariance_deg2=(variance_deg2, 0.0, 0.0, variance_deg2),
            state_vector=(0.0, 0.0, 0.0, 0.0),
            state_covariance=tuple(float(index % 5 == 0) for index in range(16)),
        )
        for timestamp in timestamps
    )
    return SnapshotTrack(
        track_id=track_id,
        camera_id=camera_id,
        samples=samples,
        source_kind=source_kind,
        track_state="confirmed",
        recent_sweep_hits=(True, True, True),
    )


def make_snapshot(
    revolution_index: int,
    tracks_a: Sequence[SnapshotTrack],
    tracks_b: Sequence[SnapshotTrack],
    *,
    camera_positions: Mapping[str, tuple[float, float, float]] = CAMERA_POSITIONS,
    seed: int = 20304001,
) -> RevolutionSnapshot:
    return RevolutionSnapshot(
        protocol_fingerprint="anonymous-v5-protocol",
        seed=seed,
        split="train",
        corruption_level="clean",
        revolution_index=revolution_index,
        cutoff_timestamp=float(revolution_index * 2),
        camera_ids=("camera_a", "camera_b"),
        camera_positions_ned=dict(camera_positions),
        focal_length_px=10000.0,
        tracks={"camera_a": tuple(tracks_a), "camera_b": tuple(tracks_b)},
        target_count=40,
        tracker_fingerprint="anonymous-shared-tracker-v1",
    )


def make_pair_publication(
    snapshot: RevolutionSnapshot,
    track_a_id: str,
    track_b_id: str,
    *,
    decision_state: str = "confirmed",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": PAIR_PUBLICATION_SCHEMA_VERSION,
        "online_anonymous": True,
        "seed": snapshot.seed,
        "protocol_fingerprint": snapshot.protocol_fingerprint,
        "corruption_level": snapshot.corruption_level,
        "revolution_index": snapshot.revolution_index,
        "input_fingerprint": snapshot_fingerprint(snapshot),
        "candidate_graph_fingerprint": snapshot.candidate_graph_fingerprint,
        "route_name": PAIR_PUBLICATION_ROUTE,
        "matches": [
            {
                "track_a_id": track_a_id,
                "track_b_id": track_b_id,
                "rule_cost": 0.1,
                "decision_state": decision_state,
            }
        ],
        "latency_ms": 1.0,
    }
    payload["publication_fingerprint"] = online_pair_publication_fingerprint(payload)
    return payload


def make_confirmed_pair(
    snapshot: RevolutionSnapshot,
    track_a_id: str,
    track_b_id: str,
) -> tuple[ConfirmedTrackPair, dict[str, object]]:
    publication = make_pair_publication(snapshot, track_a_id, track_b_id)
    pair = ConfirmedTrackPair.from_online_publication(
        publication, track_a_id, track_b_id
    )
    return pair, publication
