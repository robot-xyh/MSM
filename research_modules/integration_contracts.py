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

LOCAL_IMAGE_TRACK_STATES = {"measured", "lost"}
LOCAL_IMAGE_SPECTRAL_BANDS = {"visible", "infrared"}


@dataclass(frozen=True)
class LocalImageTrackObservation:
    """Module-neutral, camera-local track sample without global identity."""

    sensor_id: str
    stream_id: str
    local_track_id: str
    local_epoch: int
    spectral_band: str
    measurement_timestamp: float
    arrival_timestamp: float
    center_px: np.ndarray | None
    bbox_xyxy: tuple[float, float, float, float] | None
    pixel_covariance: np.ndarray | None
    confidence: float
    track_state: str
    quality_flags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for name in ("sensor_id", "stream_id", "local_track_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)

        local_epoch = int(self.local_epoch)
        if local_epoch < 0:
            raise ValueError("local_epoch must be non-negative")
        object.__setattr__(self, "local_epoch", local_epoch)

        spectral_band = str(self.spectral_band).strip().lower()
        if spectral_band not in LOCAL_IMAGE_SPECTRAL_BANDS:
            raise ValueError(
                f"spectral_band must be one of {sorted(LOCAL_IMAGE_SPECTRAL_BANDS)}"
            )
        object.__setattr__(self, "spectral_band", spectral_band)

        measurement_timestamp = float(self.measurement_timestamp)
        arrival_timestamp = float(self.arrival_timestamp)
        if not np.isfinite(measurement_timestamp) or not np.isfinite(arrival_timestamp):
            raise ValueError("track timestamps must be finite")
        if arrival_timestamp < measurement_timestamp:
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")
        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)

        confidence = float(self.confidence)
        if not np.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be finite and within [0, 1]")
        object.__setattr__(self, "confidence", confidence)

        track_state = str(self.track_state).strip().lower()
        if track_state not in LOCAL_IMAGE_TRACK_STATES:
            raise ValueError(f"track_state must be one of {sorted(LOCAL_IMAGE_TRACK_STATES)}")
        object.__setattr__(self, "track_state", track_state)

        center = (
            None
            if self.center_px is None
            else _vector(self.center_px, 2, "center_px")
        )
        bbox = _optional_bbox_xyxy(self.bbox_xyxy)
        covariance = (
            None
            if self.pixel_covariance is None
            else _covariance(self.pixel_covariance, (2, 2), "pixel_covariance")
        )
        if track_state == "measured":
            if center is None or covariance is None:
                raise ValueError(
                    "measured local image tracks require center_px and pixel_covariance"
                )
        elif center is not None or bbox is not None or covariance is not None:
            raise ValueError(
                "lost local image tracks cannot carry stale center, bbox, or covariance"
            )
        object.__setattr__(self, "center_px", center)
        object.__setattr__(self, "bbox_xyxy", bbox)
        object.__setattr__(self, "pixel_covariance", covariance)

        quality_flags = tuple(
            dict.fromkeys(str(flag).strip() for flag in self.quality_flags if str(flag).strip())
        )
        object.__setattr__(self, "quality_flags", quality_flags)
        metadata = dict(self.metadata or {})
        forbidden = {
            key
            for key in ("global_track_id", "truth_id", "object_id", "actor_name")
            if metadata.get(key) is not None
        }
        if forbidden:
            raise ValueError(
                "local image observation metadata cannot contain global/truth identity: "
                + ", ".join(sorted(forbidden))
            )
        object.__setattr__(self, "metadata", metadata)

    @property
    def source_track_key(self) -> str:
        """Return an observer-scoped source identity, never a global track ID."""

        return (
            f"{self.sensor_id}/{self.stream_id}/epoch-{self.local_epoch}/"
            f"{self.local_track_id}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "stream_id": self.stream_id,
            "local_track_id": self.local_track_id,
            "local_epoch": self.local_epoch,
            "source_track_key": self.source_track_key,
            "spectral_band": self.spectral_band,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "center_px": (
                None if self.center_px is None else self.center_px.tolist()
            ),
            "bbox_xyxy": (
                None if self.bbox_xyxy is None else list(self.bbox_xyxy)
            ),
            "pixel_covariance": (
                None
                if self.pixel_covariance is None
                else self.pixel_covariance.tolist()
            ),
            "confidence": self.confidence,
            "track_state": self.track_state,
            "quality_flags": list(self.quality_flags),
            "metadata": dict(self.metadata or {}),
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


def _covariance(value: Any, shape: tuple[int, int], name: str) -> np.ndarray:
    array = _matrix(value, shape, name)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must contain only finite values")
    if not np.allclose(array, array.T, rtol=1e-7, atol=1e-9):
        raise ValueError(f"{name} must be symmetric")
    if float(np.min(np.linalg.eigvalsh(array))) < -1e-9:
        raise ValueError(f"{name} must be positive semidefinite")
    return array


def _optional_bbox_xyxy(
    value: Any | None,
) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.shape != (4,) or not np.all(np.isfinite(array)):
        raise ValueError("bbox_xyxy must contain four finite values")
    x1, y1, x2, y2 = (float(item) for item in array)
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox_xyxy must be (x_min, y_min, x_max, y_max)")
    return (x1, y1, x2, y2)
