"""Cross-module contracts for offline C-UAS research modules.

The helpers in this file are passive adapters. They validate timestamps,
coordinate frames, uncertainty fields, plan versions, and authorization state
before data moves between D1-D6 research modules. They do not issue control,
tasking, or real-world action commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np


EFFECTIVE_AUTHORIZATION_STATES = {
    "authorized",
    "approved",
    "human_approved",
    "operator_approved",
    "recorded",
}


@dataclass(frozen=True)
class CanonicalTrack:
    """Module-neutral track DTO in local NED coordinates."""

    global_track_id: str
    position_ned: np.ndarray
    velocity_ned: np.ndarray
    covariance_6d: np.ndarray
    valid_at: float
    published_at: float
    track_version: int
    frame_id: str = "ned"
    lifecycle_state: str = "unknown"
    quality_state: str = "unknown"
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        if self.frame_id != "ned":
            raise ValueError("CanonicalTrack frame_id must be 'ned'")
        object.__setattr__(self, "position_ned", _vector(self.position_ned, 3, "position_ned"))
        object.__setattr__(self, "velocity_ned", _vector(self.velocity_ned, 3, "velocity_ned"))
        object.__setattr__(self, "covariance_6d", _matrix(self.covariance_6d, (6, 6), "covariance_6d"))

    @property
    def covariance_xy(self) -> np.ndarray:
        return self.covariance_6d[:2, :2].copy()

    @property
    def covariance_xyz(self) -> np.ndarray:
        return self.covariance_6d[:3, :3].copy()

    @property
    def covariance_trace(self) -> float:
        return float(np.trace(self.covariance_6d))


@dataclass(frozen=True)
class AssignmentHandoff:
    """Plan-to-terminal assignment handoff with separate plan and track versions."""

    plan_id: str
    plan_version: int
    resource_id: str
    assigned_global_track_id: str
    track_version: int
    authorization_state: str
    created_at: float
    coalition_id: str | None = None
    coalition_version: int | None = None
    member_role: str = "primary"
    wave_id: int = 0
    required_resource_count: int = 1
    coordination_mode: str = "independent"
    arrival_window_start_s: float | None = None
    arrival_window_end_s: float | None = None
    activation_state: str = "active"

    @property
    def is_authorized(self) -> bool:
        return self.authorization_state.lower() in EFFECTIVE_AUTHORIZATION_STATES


def canonical_track_from_d1(track: Any, track_version: int = 0) -> CanonicalTrack:
    """Validate and convert a D1 GlobalTrack-like object."""

    metadata = dict(getattr(track, "metadata", {}) or {})
    frame_id = metadata.get("frame_id", "ned")
    if frame_id != "ned":
        raise ValueError(f"D1 GlobalTrack must be in NED before integration; got {frame_id!r}")
    state = _vector(getattr(track, "state"), 6, "track.state")
    covariance = _matrix(getattr(track, "covariance"), (6, 6), "track.covariance")
    timestamp = float(getattr(track, "timestamp"))
    return CanonicalTrack(
        global_track_id=str(getattr(track, "global_track_id")),
        position_ned=state[:3],
        velocity_ned=state[3:],
        covariance_6d=covariance,
        valid_at=float(metadata.get("valid_at", timestamp)),
        published_at=float(metadata.get("published_at", timestamp)),
        track_version=int(metadata.get("track_version", track_version)),
        lifecycle_state=str(metadata.get("lifecycle_state", "unknown")),
        quality_state=str(getattr(getattr(track, "track_level", "unknown"), "value", getattr(track, "track_level", "unknown"))),
        metadata=metadata,
    )


def d2_detection_kwargs(
    canonical: CanonicalTrack,
    detection_id: str,
    truth_id: str | None = None,
) -> dict[str, Any]:
    """Return kwargs for constructing a D2 Detection from a canonical track."""

    return {
        "detection_id": detection_id,
        "timestamp": canonical.valid_at,
        "position": canonical.position_ned[:2].copy(),
        "covariance": canonical.covariance_xy,
        "truth_id": truth_id,
        "metadata": {
            "frame_id": "ned",
            "global_track_id": canonical.global_track_id,
            "track_version": canonical.track_version,
            "published_at": canonical.published_at,
        },
    }


def assignment_handoff_from_d3(plan: Any, assignment: Any, track_version: int) -> AssignmentHandoff:
    """Validate a D3 AssignmentPlan/Assignment pair before terminal use."""

    coalition = next(
        (
            item
            for item in getattr(plan, "coalitions", ())
            if getattr(item, "target_id", None) == getattr(assignment, "target_id", None)
        ),
        None,
    )
    member_role = str(getattr(assignment, "member_role", "primary"))
    wave_id = int(getattr(assignment, "wave_id", 0))
    activation_state = str(
        getattr(assignment, "metadata", {}).get(
            "activation_state",
            "active" if member_role == "primary" and wave_id == 0 else "standby",
        )
    )
    handoff = AssignmentHandoff(
        plan_id=str(getattr(plan, "plan_id")),
        plan_version=int(getattr(plan, "version")),
        resource_id=str(getattr(assignment, "resource_id")),
        assigned_global_track_id=str(getattr(assignment, "target_id")),
        track_version=int(track_version),
        authorization_state=str(getattr(plan, "human_authorization_state")),
        created_at=float(getattr(plan, "created_at")),
        coalition_id=getattr(assignment, "coalition_id", None),
        coalition_version=getattr(assignment, "coalition_version", None),
        member_role=member_role,
        wave_id=wave_id,
        required_resource_count=int(getattr(assignment, "required_resource_count", 1)),
        coordination_mode=str(getattr(coalition, "coordination_mode", "independent")),
        arrival_window_start_s=getattr(assignment, "arrival_window_start_s", None),
        arrival_window_end_s=getattr(assignment, "arrival_window_end_s", None),
        activation_state=activation_state,
    )
    if not handoff.is_authorized:
        raise ValueError("assignment handoff is not authorized for terminal locking")
    return handoff


def d5_assignment_kwargs(handoff: AssignmentHandoff) -> dict[str, Any]:
    """Return kwargs for constructing a D5 Assignment."""

    return {
        "assigned_global_track_id": handoff.assigned_global_track_id,
        "assignment_version": handoff.track_version,
        "timestamp": handoff.created_at,
        "require_version_match": True,
        "plan_id": handoff.plan_id,
        "plan_version": handoff.plan_version,
        "authorization_state": handoff.authorization_state,
        "resource_id": handoff.resource_id,
        "coalition_id": handoff.coalition_id,
        "coalition_version": handoff.coalition_version,
        "member_role": handoff.member_role,
        "wave_id": handoff.wave_id,
        "required_resource_count": handoff.required_resource_count,
        "coordination_mode": handoff.coordination_mode,
        "arrival_window_start_s": handoff.arrival_window_start_s,
        "arrival_window_end_s": handoff.arrival_window_end_s,
        "activation_state": handoff.activation_state,
    }


def _vector(value: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.shape != (size,):
        raise ValueError(f"{name} must have shape ({size},), got {array.shape}")
    return array.copy()


def _matrix(value: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    return array.copy()
