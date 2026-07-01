#!/usr/bin/env python3
"""Deterministic offline simulation for D5 terminal visual association.

The simulation is image-plane only. It exercises conservative association with
multiple local detections, verified friend overlap, unknown near-gate objects,
and temporary occlusion. It does not contain flight control, fire-control, or
automatic disposition logic.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from d5_terminal_association import (  # noqa: E402
    Assignment,
    CameraModel,
    GlobalTrack,
    IdentityChecker,
    LocalVisualTrack,
    TerminalAssociator,
)


def make_camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [240.0, 0.0, 480.0],
                [0.0, 240.0, 360.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(960, 720),
        measurement_cov=np.diag([9.0, 9.0]),
    )


def bbox_from_center(center: np.ndarray, half_size: float = 8.0) -> tuple[float, float, float, float]:
    u, v = center
    return (float(u - half_size), float(v - half_size), float(u + half_size), float(v + half_size))


def make_global_tracks(frame: int) -> list[GlobalTrack]:
    t = frame / 10.0
    covariance = np.diag([0.04, 0.04, 0.02])
    assigned_position = np.array([-0.6 + 0.035 * frame, 0.15 * np.sin(t), 30.0])
    assigned_velocity = np.array([0.035, 0.015 * np.cos(t), 0.0])

    return [
        GlobalTrack(
            global_track_id="G_ASSIGNED",
            position=assigned_position,
            velocity=assigned_velocity,
            covariance=covariance,
            category="uav",
            timestamp=float(frame),
        ),
        GlobalTrack(
            global_track_id="G_DISTRACTOR",
            position=np.array([5.5 - 0.015 * frame, 1.2, 31.0]),
            velocity=np.array([-0.015, 0.0, 0.0]),
            covariance=covariance,
            category="uav",
            timestamp=float(frame),
        ),
        GlobalTrack(
            global_track_id="G_FRIEND_CENTER_OWNED",
            position=np.array([-3.5 + 0.04 * frame, -1.0, 28.0]),
            velocity=np.array([0.04, 0.0, 0.0]),
            covariance=covariance,
            category="friend",
            timestamp=float(frame),
        ),
    ]


def make_local_tracks_and_claims(
    frame: int,
    associator: TerminalAssociator,
    camera: CameraModel,
    rng: np.random.Generator,
) -> tuple[list[LocalVisualTrack], list[dict[str, Any]], str | None]:
    tracks = make_global_tracks(frame)
    projections = associator.project_tracks_to_image(tracks, camera)
    assigned_projection = projections["G_ASSIGNED"]
    distractor_projection = projections["G_DISTRACTOR"]
    friend_projection = projections["G_FRIEND_CENTER_OWNED"]

    locals_in_view: list[LocalVisualTrack] = []
    raw_claims: list[dict[str, Any]] = []
    expected_assigned_local_id: str | None = None

    assigned_occluded = 52 <= frame <= 60
    if not assigned_occluded:
        center = assigned_projection.pixel + rng.normal(0.0, 0.7, size=2)
        locals_in_view.append(
            LocalVisualTrack(
                local_track_id="L_assigned",
                center_px=center,
                bbox=bbox_from_center(center),
                bearing_rate=assigned_projection.predicted_px_velocity + rng.normal(0.0, 0.3, size=2),
                category="uav",
                quality=0.92,
                mot_history_length=8,
                timestamp=float(frame),
            )
        )
        expected_assigned_local_id = "L_assigned"

    # Unknown object near the assigned projection creates a close-cost ambiguity.
    if 35 <= frame <= 42:
        center = assigned_projection.pixel + np.array([2.0, 0.8]) + rng.normal(0.0, 0.4, size=2)
    else:
        center = assigned_projection.pixel + np.array([42.0, -26.0]) + rng.normal(0.0, 1.0, size=2)
    locals_in_view.append(
        LocalVisualTrack(
            local_track_id="L_unknown",
            center_px=center,
            bbox=bbox_from_center(center, half_size=7.0),
            bearing_rate=np.array([0.0, 0.0]),
            category="uav",
            quality=0.78,
            mot_history_length=4,
            timestamp=float(frame),
        )
    )

    # Distractor remains visible but outside the assigned projection gate.
    center = distractor_projection.pixel + rng.normal(0.0, 0.8, size=2)
    locals_in_view.append(
        LocalVisualTrack(
            local_track_id="L_distractor",
            center_px=center,
            bbox=bbox_from_center(center),
            bearing_rate=distractor_projection.predicted_px_velocity,
            category="uav",
            quality=0.9,
            mot_history_length=8,
            timestamp=float(frame),
        )
    )

    # A verified friend overlaps the assigned projection for several frames.
    if 72 <= frame <= 78:
        center = assigned_projection.pixel + rng.normal(0.0, 0.5, size=2)
    else:
        center = friend_projection.pixel + rng.normal(0.0, 0.8, size=2)
    locals_in_view.append(
        LocalVisualTrack(
            local_track_id="L_friend",
            center_px=center,
            bbox=bbox_from_center(center),
            bearing_rate=friend_projection.predicted_px_velocity,
            category="friend",
            quality=0.96,
            mot_history_length=10,
            timestamp=float(frame),
        )
    )
    raw_claims.append(
        {
            "protocol": "OpenDroneID",
            "platform_id": "FRIEND_SIM_1",
            "local_track_id": "L_friend",
            "center_px": center.tolist(),
            "bbox": bbox_from_center(center),
            "timestamp": float(frame),
            "is_friend": True,
            "signature_valid": True,
        }
    )

    return locals_in_view, raw_claims, expected_assigned_local_id


def run_simulation(frames: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    camera = make_camera()
    checker = IdentityChecker(friendly_platform_ids={"FRIEND_SIM_1"}, max_age_s=2.0)
    associator = TerminalAssociator(identity_checker=checker)
    assignment = Assignment("G_ASSIGNED")

    metrics: dict[str, Any] = {
        "frames": frames,
        "lock_correct": 0,
        "lock_wrong": 0,
        "ambiguous": 0,
        "hold": 0,
        "reacquire": 0,
        "decisions": {},
        "global_track_id_mutations": 0,
    }

    timeline: list[dict[str, Any]] = []

    for frame in range(frames):
        global_tracks = make_global_tracks(frame)
        before_ids = [track.global_track_id for track in global_tracks]
        local_tracks, raw_claims, expected_local_id = make_local_tracks_and_claims(
            frame, associator, camera, rng
        )
        claims = checker.parse_claims(raw_claims, current_time=float(frame))
        decision = associator.decide(assignment, global_tracks, local_tracks, claims, camera)
        after_ids = [track.global_track_id for track in global_tracks]
        if before_ids != after_ids:
            metrics["global_track_id_mutations"] += 1

        state = decision.decision_state
        metrics["decisions"][state] = metrics["decisions"].get(state, 0) + 1
        if state == "locked" and decision.local_track_id == expected_local_id:
            metrics["lock_correct"] += 1
        elif state == "locked":
            metrics["lock_wrong"] += 1
        elif state in {"ambiguous", "hold", "reacquire"}:
            metrics[state] += 1

        timeline.append(
            {
                "frame": frame,
                "decision": decision.decision_state,
                "local_track_id": decision.local_track_id,
                "reason": decision.reason,
                "candidate_costs": decision.candidate_costs,
            }
        )

    lock_total = metrics["lock_correct"] + metrics["lock_wrong"]
    metrics["terminal_association_correct_rate_all_frames"] = (
        metrics["lock_correct"] / frames if frames else 0.0
    )
    metrics["lock_precision"] = metrics["lock_correct"] / lock_total if lock_total else 0.0
    metrics["timeline"] = timeline
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--save-json", type=Path, default=None)
    args = parser.parse_args()

    if args.frames <= 0:
        raise SystemExit("--frames must be positive")

    metrics = run_simulation(frames=args.frames, seed=args.seed)
    compact = {key: value for key, value in metrics.items() if key != "timeline"}
    print(json.dumps(compact, indent=2, sort_keys=True))

    if args.save_json is not None:
        args.save_json.parent.mkdir(parents=True, exist_ok=True)
        args.save_json.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
