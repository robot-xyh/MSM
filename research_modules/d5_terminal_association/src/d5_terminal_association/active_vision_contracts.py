"""Versioned, truth-free active-vision contracts and safety projection.

The learned policy can only select camera observation intents.  It cannot
create identities, assign resources, or emit vehicle controls.  Every learned
proposal is projected through the same deterministic camera safety envelope;
failure returns the already-computed rule action.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
import math
import re
import time
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np


ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION = "d5.active-vision-snapshot.v1"
ACTIVE_VISION_ACTION_SCHEMA_VERSION = "d5.active-vision-action.v1"
ACTIVE_VISION_FEATURE_SCHEMA_VERSION = "d5.active-vision-features.v1"
ACTIVE_VISION_ACTION_SPACE_VERSION = "d5.active-vision-actions.v1"

_FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_entity_id",
        "ground_truth",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "entity_id",
        "entity_name",
        "target_truth_id",
        "airsim_id",
    }
)
_TRUTH_LIKE_INPUT_VALUE = re.compile(
    r"truth|actor|object|(?:^|[^a-z0-9])(?:tgt|target(?:drone|uav)?|intruder)[_.\- ]*\d+",
    re.IGNORECASE,
)


class ActiveVisionIntent(str, Enum):
    OBSERVE_TARGET = "observe_target"
    SEARCH_SECTOR = "search_sector"
    HOLD = "hold"
    REACQUIRE = "reacquire"


class ActiveVisionFovMode(str, Enum):
    WIDE = "wide"
    ZOOM = "zoom"


class ActiveVisionRuntimeMode(str, Enum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    ASSIST = "assist"


@dataclass(frozen=True)
class ActiveVisionTrackReference:
    """Read-only reference to one center-owned ``GlobalTrack`` candidate."""

    global_track_id: str
    track_version: int
    measurement_timestamp: float

    def __post_init__(self) -> None:
        track_id = _non_empty(self.global_track_id, "global_track_id")
        version = int(self.track_version)
        if version < 0:
            raise ValueError("track_version must be non-negative")
        object.__setattr__(self, "global_track_id", track_id)
        object.__setattr__(self, "track_version", version)
        object.__setattr__(
            self,
            "measurement_timestamp",
            _finite(self.measurement_timestamp, "measurement_timestamp"),
        )


@dataclass(frozen=True)
class ActiveVisionAssignmentReference:
    """Read-only target membership copied from the current AssignmentPlan."""

    resource_id: str
    camera_id: str
    global_track_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "resource_id", _non_empty(self.resource_id, "resource_id"))
        object.__setattr__(self, "camera_id", _non_empty(self.camera_id, "camera_id"))
        object.__setattr__(
            self,
            "global_track_id",
            _non_empty(self.global_track_id, "global_track_id"),
        )


@dataclass(frozen=True)
class ActiveVisionPlanReference:
    """Versioned, immutable subset of the current center AssignmentPlan."""

    plan_version: int
    coalition_version: int
    assignments: tuple[ActiveVisionAssignmentReference, ...]

    def __post_init__(self) -> None:
        plan_version = int(self.plan_version)
        coalition_version = int(self.coalition_version)
        if plan_version < 0 or coalition_version < 0:
            raise ValueError("plan and coalition versions must be non-negative")
        assignments = tuple(self.assignments)
        keys = tuple((item.camera_id, item.global_track_id) for item in assignments)
        if len(keys) != len(set(keys)):
            raise ValueError("assignment references must be unique per camera and target")
        object.__setattr__(self, "plan_version", plan_version)
        object.__setattr__(self, "coalition_version", coalition_version)
        object.__setattr__(self, "assignments", assignments)

    @property
    def candidate_global_track_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.global_track_id for item in self.assignments}))


@dataclass(frozen=True)
class ActiveVisionCameraState:
    camera_id: str
    resource_id: str
    state_timestamp: float
    yaw_deg: float
    pitch_deg: float
    yaw_rate_deg_s: float
    pitch_rate_deg_s: float
    yaw_limits_deg: tuple[float, float]
    pitch_limits_deg: tuple[float, float]
    max_yaw_rate_deg_s: float
    max_pitch_rate_deg_s: float
    max_slew_deg_s: float
    current_fov_mode: ActiveVisionFovMode
    supported_fov_modes: tuple[ActiveVisionFovMode, ...] = (
        ActiveVisionFovMode.WIDE,
        ActiveVisionFovMode.ZOOM,
    )
    wide_horizontal_fov_deg: float = 90.0
    zoom_horizontal_fov_deg: float = 30.0
    slew_available: bool = True
    action_in_progress_until: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_id", _non_empty(self.camera_id, "camera_id"))
        object.__setattr__(self, "resource_id", _non_empty(self.resource_id, "resource_id"))
        for name in (
            "state_timestamp",
            "yaw_deg",
            "pitch_deg",
            "yaw_rate_deg_s",
            "pitch_rate_deg_s",
            "max_yaw_rate_deg_s",
            "max_pitch_rate_deg_s",
            "max_slew_deg_s",
            "wide_horizontal_fov_deg",
            "zoom_horizontal_fov_deg",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        yaw_limits = _increasing_pair(self.yaw_limits_deg, "yaw_limits_deg")
        pitch_limits = _increasing_pair(self.pitch_limits_deg, "pitch_limits_deg")
        if yaw_limits[0] < -180.0 or yaw_limits[1] > 180.0:
            raise ValueError("yaw limits exceed physical bounds")
        if pitch_limits[0] < -90.0 or pitch_limits[1] > 90.0:
            raise ValueError("pitch limits exceed physical bounds")
        if not yaw_limits[0] <= self.yaw_deg <= yaw_limits[1]:
            raise ValueError("current yaw is outside gimbal limits")
        if not pitch_limits[0] <= self.pitch_deg <= pitch_limits[1]:
            raise ValueError("current pitch is outside gimbal limits")
        if min(self.max_yaw_rate_deg_s, self.max_pitch_rate_deg_s, self.max_slew_deg_s) <= 0.0:
            raise ValueError("gimbal rate limits must be positive")
        if abs(self.yaw_rate_deg_s) > self.max_yaw_rate_deg_s + 1.0e-9:
            raise ValueError("current yaw rate exceeds the camera envelope")
        if abs(self.pitch_rate_deg_s) > self.max_pitch_rate_deg_s + 1.0e-9:
            raise ValueError("current pitch rate exceeds the camera envelope")
        if math.hypot(self.yaw_rate_deg_s, self.pitch_rate_deg_s) > self.max_slew_deg_s + 1.0e-9:
            raise ValueError("current slew rate exceeds the camera envelope")
        if not 0.0 < self.zoom_horizontal_fov_deg <= self.wide_horizontal_fov_deg < 180.0:
            raise ValueError("wide/zoom FOV values are invalid")
        modes = tuple(ActiveVisionFovMode(value) for value in self.supported_fov_modes)
        current_mode = ActiveVisionFovMode(self.current_fov_mode)
        if not modes or len(modes) != len(set(modes)) or current_mode not in modes:
            raise ValueError("supported FOV modes are invalid")
        busy_until = self.action_in_progress_until
        if busy_until is not None:
            busy_until = _finite(busy_until, "action_in_progress_until")
        object.__setattr__(self, "yaw_limits_deg", yaw_limits)
        object.__setattr__(self, "pitch_limits_deg", pitch_limits)
        object.__setattr__(self, "current_fov_mode", current_mode)
        object.__setattr__(self, "supported_fov_modes", modes)
        object.__setattr__(self, "action_in_progress_until", busy_until)


@dataclass(frozen=True)
class ActiveVisionProjectionEvidence:
    """Truth-free image/gimbal projection and visibility evidence."""

    camera_id: str
    global_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    yaw_error_deg: float
    pitch_error_deg: float
    projection_covariance_deg2: tuple[float, float, float, float]
    visibility_probability: float
    occlusion_fraction: float
    association_confidence: float
    in_fov: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_id", _non_empty(self.camera_id, "camera_id"))
        object.__setattr__(
            self,
            "global_track_id",
            _non_empty(self.global_track_id, "global_track_id"),
        )
        measurement = _finite(self.measurement_timestamp, "measurement_timestamp")
        arrival = _finite(self.arrival_timestamp, "arrival_timestamp")
        if arrival + 1.0e-12 < measurement:
            raise ValueError("projection arrival_timestamp precedes measurement_timestamp")
        covariance = np.asarray(self.projection_covariance_deg2, dtype=float).reshape(2, 2)
        if not np.all(np.isfinite(covariance)) or not np.allclose(covariance, covariance.T):
            raise ValueError("projection covariance must be finite and symmetric")
        if float(np.linalg.eigvalsh(covariance).min()) < -1.0e-9:
            raise ValueError("projection covariance must be positive semidefinite")
        for name in ("visibility_probability", "occlusion_fraction", "association_confidence"):
            value = _finite(getattr(self, name), name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "measurement_timestamp", measurement)
        object.__setattr__(self, "arrival_timestamp", arrival)
        object.__setattr__(self, "yaw_error_deg", _finite(self.yaw_error_deg, "yaw_error_deg"))
        object.__setattr__(self, "pitch_error_deg", _finite(self.pitch_error_deg, "pitch_error_deg"))
        object.__setattr__(
            self,
            "projection_covariance_deg2",
            tuple(float(value) for value in covariance.reshape(-1)),
        )

    @property
    def uncertainty_trace_deg2(self) -> float:
        return self.projection_covariance_deg2[0] + self.projection_covariance_deg2[3]


@dataclass(frozen=True)
class FriendlyObservationReservation:
    owner_resource_id: str
    camera_id: str
    communication_version: int
    coalition_version: int
    expires_timestamp: float
    exclusive: bool = True
    global_track_id: str | None = None
    sector_deg: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "owner_resource_id",
            _non_empty(self.owner_resource_id, "owner_resource_id"),
        )
        object.__setattr__(self, "camera_id", _non_empty(self.camera_id, "camera_id"))
        for name in ("communication_version", "coalition_version"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "expires_timestamp",
            _finite(self.expires_timestamp, "expires_timestamp"),
        )
        target_id = None if self.global_track_id is None else _non_empty(
            self.global_track_id, "global_track_id"
        )
        sector = None if self.sector_deg is None else _sector(self.sector_deg)
        if (target_id is None) == (sector is None):
            raise ValueError("friendly reservation requires exactly one target or sector")
        object.__setattr__(self, "global_track_id", target_id)
        object.__setattr__(self, "sector_deg", sector)


@dataclass(frozen=True)
class ActiveVisionCommunicationState:
    communication_version: int
    plan_version: int
    coalition_version: int
    update_timestamp: float
    healthy: bool
    peer_reservations: tuple[FriendlyObservationReservation, ...] = ()

    def __post_init__(self) -> None:
        for name in ("communication_version", "plan_version", "coalition_version"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "update_timestamp",
            _finite(self.update_timestamp, "update_timestamp"),
        )
        object.__setattr__(self, "peer_reservations", tuple(self.peer_reservations))


@dataclass(frozen=True)
class ActiveVisionSnapshotV1:
    """The complete truth-free policy input for a unified 3D episode tick."""

    snapshot_timestamp: float
    plan: ActiveVisionPlanReference
    communication: ActiveVisionCommunicationState
    tracks: tuple[ActiveVisionTrackReference, ...]
    cameras: tuple[ActiveVisionCameraState, ...]
    projections: tuple[ActiveVisionProjectionEvidence, ...]
    schema_version: str = ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("active-vision snapshot schema mismatch")
        timestamp = _finite(self.snapshot_timestamp, "snapshot_timestamp")
        tracks = tuple(self.tracks)
        cameras = tuple(self.cameras)
        projections = tuple(self.projections)
        track_ids = tuple(item.global_track_id for item in tracks)
        camera_ids = tuple(item.camera_id for item in cameras)
        if len(track_ids) != len(set(track_ids)):
            raise ValueError("active-vision track candidates must be unique")
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError("active-vision cameras must be unique")
        if not set(self.plan.candidate_global_track_ids).issubset(track_ids):
            raise ValueError("AssignmentPlan references a target outside GlobalTrack candidates")
        camera_id_set = set(camera_ids)
        track_id_set = set(track_ids)
        if any(item.camera_id not in camera_id_set for item in self.plan.assignments):
            raise ValueError("AssignmentPlan references an unavailable camera")
        resource_by_camera = {item.camera_id: item.resource_id for item in cameras}
        if any(
            resource_by_camera[item.camera_id] != item.resource_id
            for item in self.plan.assignments
        ):
            raise ValueError("AssignmentPlan camera/resource membership is inconsistent")
        projection_keys = tuple((item.camera_id, item.global_track_id) for item in projections)
        if len(projection_keys) != len(set(projection_keys)):
            raise ValueError("projection evidence must be unique per camera and target")
        if any(
            camera_id not in camera_id_set or track_id not in track_id_set
            for camera_id, track_id in projection_keys
        ):
            raise ValueError("projection evidence references a non-candidate member")
        assert_truth_free_active_vision_payload(self)
        object.__setattr__(self, "snapshot_timestamp", timestamp)
        object.__setattr__(self, "tracks", tracks)
        object.__setattr__(self, "cameras", cameras)
        object.__setattr__(self, "projections", projections)

    def camera(self, camera_id: str) -> ActiveVisionCameraState:
        matches = tuple(item for item in self.cameras if item.camera_id == camera_id)
        if len(matches) != 1:
            raise ValueError("camera_id is not a member of the active-vision snapshot")
        return matches[0]

    def projection(
        self, camera_id: str, global_track_id: str
    ) -> ActiveVisionProjectionEvidence | None:
        return next(
            (
                item
                for item in self.projections
                if item.camera_id == camera_id and item.global_track_id == global_track_id
            ),
            None,
        )

    def assigned_target_ids(self, camera_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.global_track_id
                for item in self.plan.assignments
                if item.camera_id == camera_id
            )
        )


@dataclass(frozen=True)
class ActiveVisionActionV1:
    """One bounded camera intent; no vehicle control or assignment fields exist."""

    camera_id: str
    issued_timestamp: float
    expires_timestamp: float
    plan_version: int
    coalition_version: int
    communication_version: int
    intent: ActiveVisionIntent
    yaw_delta_deg: float
    pitch_delta_deg: float
    fov_mode: ActiveVisionFovMode
    target_global_track_id: str | None = None
    search_sector_deg: tuple[float, float, float, float] | None = None
    reason: str = "policy"
    schema_version: str = ACTIVE_VISION_ACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_ACTION_SCHEMA_VERSION:
            raise ValueError("active-vision action schema mismatch")
        object.__setattr__(self, "camera_id", _non_empty(self.camera_id, "camera_id"))
        issued = _finite(self.issued_timestamp, "issued_timestamp")
        expires = _finite(self.expires_timestamp, "expires_timestamp")
        if expires <= issued:
            raise ValueError("active-vision action must have a positive lifetime")
        object.__setattr__(self, "issued_timestamp", issued)
        object.__setattr__(self, "expires_timestamp", expires)
        for name in ("plan_version", "coalition_version", "communication_version"):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        intent = ActiveVisionIntent(self.intent)
        fov_mode = ActiveVisionFovMode(self.fov_mode)
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "fov_mode", fov_mode)
        object.__setattr__(self, "yaw_delta_deg", _finite(self.yaw_delta_deg, "yaw_delta_deg"))
        object.__setattr__(
            self,
            "pitch_delta_deg",
            _finite(self.pitch_delta_deg, "pitch_delta_deg"),
        )
        target_id = None if self.target_global_track_id is None else _non_empty(
            self.target_global_track_id, "target_global_track_id"
        )
        sector = None if self.search_sector_deg is None else _sector(self.search_sector_deg)
        if intent in {ActiveVisionIntent.OBSERVE_TARGET, ActiveVisionIntent.REACQUIRE}:
            if target_id is None or sector is not None:
                raise ValueError("target observation action requires only a candidate target")
        elif intent is ActiveVisionIntent.SEARCH_SECTOR:
            if sector is None or target_id is not None:
                raise ValueError("search action requires only a search sector")
        elif target_id is not None or sector is not None:
            raise ValueError("hold action cannot carry target or sector membership")
        object.__setattr__(self, "target_global_track_id", target_id)
        object.__setattr__(self, "search_sector_deg", sector)
        object.__setattr__(self, "reason", str(self.reason or "policy"))

    @property
    def action_key(self) -> tuple[Any, ...]:
        return (
            self.camera_id,
            self.intent.value,
            self.target_global_track_id,
            self.search_sector_deg,
            round(self.yaw_delta_deg, 9),
            round(self.pitch_delta_deg, 9),
            self.fov_mode.value,
        )


@dataclass(frozen=True)
class ActiveVisionSafetyConfigV1:
    max_evidence_age_s: float = 0.75
    max_communication_age_s: float = 1.0
    reacquire_evidence_age_s: float = 2.0
    action_timeout_s: float = 0.25
    max_gimbal_increment_deg: float = 8.0
    minimum_visibility_probability: float = 0.35
    minimum_association_confidence: float = 0.60
    maximum_occlusion_fraction: float = 0.80
    zoom_max_uncertainty_trace_deg2: float = 9.0
    zoom_stability_window_frames: int = 3
    zoom_minimum_binding_score_margin: float = 0.05
    learned_minimum_confidence: float = 0.55
    model_inference_timeout_ms: float = 50.0
    scan_sectors_deg: tuple[tuple[float, float, float, float], ...] = (
        (-60.0, -20.0, -25.0, 15.0),
        (-20.0, 20.0, -25.0, 15.0),
        (20.0, 60.0, -25.0, 15.0),
    )

    def __post_init__(self) -> None:
        for name in (
            "max_evidence_age_s",
            "max_communication_age_s",
            "reacquire_evidence_age_s",
            "action_timeout_s",
            "max_gimbal_increment_deg",
            "model_inference_timeout_ms",
        ):
            value = _finite(getattr(self, name), name)
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        if self.reacquire_evidence_age_s < self.max_evidence_age_s:
            raise ValueError("reacquire evidence age must cover fresh evidence age")
        for name in (
            "minimum_visibility_probability",
            "minimum_association_confidence",
            "maximum_occlusion_fraction",
            "learned_minimum_confidence",
        ):
            value = _finite(getattr(self, name), name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            object.__setattr__(self, name, value)
        uncertainty = _finite(
            self.zoom_max_uncertainty_trace_deg2,
            "zoom_max_uncertainty_trace_deg2",
        )
        if uncertainty < 0.0:
            raise ValueError("zoom uncertainty threshold must be non-negative")
        object.__setattr__(self, "zoom_max_uncertainty_trace_deg2", uncertainty)
        stable_frames = int(self.zoom_stability_window_frames)
        if (
            isinstance(self.zoom_stability_window_frames, bool)
            or stable_frames < 1
            or stable_frames != self.zoom_stability_window_frames
        ):
            raise ValueError("zoom stability window must contain at least one frame")
        object.__setattr__(self, "zoom_stability_window_frames", stable_frames)
        binding_margin = _finite(
            self.zoom_minimum_binding_score_margin,
            "zoom_minimum_binding_score_margin",
        )
        if not 0.0 <= binding_margin <= 1.0:
            raise ValueError("zoom binding score margin must be in [0, 1]")
        object.__setattr__(self, "zoom_minimum_binding_score_margin", binding_margin)
        sectors = tuple(_sector(value) for value in self.scan_sectors_deg)
        if not sectors:
            raise ValueError("at least one deterministic scan sector is required")
        object.__setattr__(self, "scan_sectors_deg", sectors)


@dataclass(frozen=True)
class ActiveVisionPolicyProposal:
    action: ActiveVisionActionV1 | None
    confidence: float
    inference_latency_ms: float
    model_fingerprint: str | None
    ood: bool = False
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        confidence = _finite(self.confidence, "confidence")
        latency = _finite(self.inference_latency_ms, "inference_latency_ms")
        if not 0.0 <= confidence <= 1.0 or latency < 0.0:
            raise ValueError("proposal confidence/latency is invalid")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "inference_latency_ms", latency)


@runtime_checkable
class ActiveVisionLearnedPolicy(Protocol):
    available: bool
    failure_reason: str | None
    model_fingerprint: str | None
    assist_admitted: bool

    def propose(
        self,
        snapshot: ActiveVisionSnapshotV1,
        *,
        camera_id: str,
        current_timestamp: float,
    ) -> ActiveVisionPolicyProposal:
        ...


@dataclass(frozen=True)
class ActiveVisionDecisionV1:
    requested_mode: ActiveVisionRuntimeMode
    effective_mode: ActiveVisionRuntimeMode
    rule_action: ActiveVisionActionV1
    requested_action: ActiveVisionActionV1 | None
    effective_action: ActiveVisionActionV1
    fallback_reason: str | None
    inference_latency_ms: float
    model_fingerprint: str | None
    plan_version: int
    coalition_version: int
    communication_version: int


@dataclass(frozen=True)
class _BindingStabilityState:
    key: tuple[str, str, int, int]
    stable_frame_count: int
    last_current_timestamp: float
    last_snapshot_timestamp: float
    last_measurement_timestamp: float
    last_arrival_timestamp: float


class DeterministicLookAtScanPolicy:
    """Deterministic look-at/reacquire/scan baseline used for every fallback."""

    def __init__(self, config: ActiveVisionSafetyConfigV1 | None = None) -> None:
        self.config = config or ActiveVisionSafetyConfigV1()
        self._binding_stability_by_camera: dict[str, _BindingStabilityState] = {}

    def select_action(
        self,
        snapshot: ActiveVisionSnapshotV1,
        *,
        camera_id: str,
        current_timestamp: float,
        expected_plan_version: int,
        expected_coalition_version: int,
        expected_communication_version: int,
    ) -> ActiveVisionActionV1:
        now = _finite(current_timestamp, "current_timestamp")
        camera = snapshot.camera(camera_id)
        version_reason = _snapshot_version_failure(
            snapshot,
            now,
            expected_plan_version=expected_plan_version,
            expected_coalition_version=expected_coalition_version,
            expected_communication_version=expected_communication_version,
            config=self.config,
        )
        if version_reason is not None:
            self._reset_binding_stability(camera_id)
            return self.scan_action(
                snapshot,
                camera=camera,
                current_timestamp=now,
                reason=version_reason,
            )
        previous_state = self._binding_stability_by_camera.get(camera_id)
        if (
            snapshot.snapshot_timestamp > now + 1.0e-9
            or (
                previous_state is not None
                and (
                    now + 1.0e-9 < previous_state.last_current_timestamp
                    or snapshot.snapshot_timestamp + 1.0e-9
                    < previous_state.last_snapshot_timestamp
                )
            )
        ):
            self._reset_binding_stability(camera_id)
            return self.scan_action(
                snapshot,
                camera=camera,
                current_timestamp=now,
                reason="policy_time_regression",
            )
        if (
            not camera.slew_available
            or (
                camera.action_in_progress_until is not None
                and camera.action_in_progress_until > now
            )
        ):
            self._reset_binding_stability(camera_id)
            return _action(
                snapshot,
                camera,
                now,
                intent=ActiveVisionIntent.HOLD,
                yaw_delta_deg=0.0,
                pitch_delta_deg=0.0,
                fov_mode=camera.current_fov_mode,
                reason="rule_hold:gimbal_unavailable_or_busy",
                config=self.config,
            )

        fresh: list[ActiveVisionProjectionEvidence] = []
        reacquire: list[ActiveVisionProjectionEvidence] = []
        for track_id in snapshot.assigned_target_ids(camera_id):
            evidence = snapshot.projection(camera_id, track_id)
            if evidence is None:
                continue
            if (
                evidence.measurement_timestamp > now + 1.0e-9
                or evidence.arrival_timestamp > now + 1.0e-9
            ):
                continue
            if _reservation_conflict(
                snapshot,
                camera,
                now,
                target_id=track_id,
                sector=None,
            ):
                continue
            age = max(0.0, now - evidence.measurement_timestamp)
            if (
                age <= self.config.max_evidence_age_s
                and evidence.visibility_probability >= self.config.minimum_visibility_probability
                and evidence.occlusion_fraction <= self.config.maximum_occlusion_fraction
                and evidence.association_confidence >= self.config.minimum_association_confidence
                and evidence.in_fov
            ):
                fresh.append(evidence)
            elif age <= self.config.reacquire_evidence_age_s:
                reacquire.append(evidence)
        if fresh:
            selected = min(
                fresh,
                key=lambda item: (
                    -item.visibility_probability,
                    item.occlusion_fraction,
                    item.uncertainty_trace_deg2,
                    item.global_track_id,
                ),
            )
            if _projection_binding_is_ambiguous(
                selected,
                fresh,
                minimum_margin=self.config.zoom_minimum_binding_score_margin,
            ):
                self._reset_binding_stability(camera_id)
                return self._target_action(
                    snapshot,
                    camera,
                    selected,
                    now,
                    intent=ActiveVisionIntent.REACQUIRE,
                    fov_mode=_wide_or_current(camera),
                    reason="rule_reacquire_ambiguous_assigned_projection",
                )
            stable_frame_count = self._advance_binding_stability(
                snapshot,
                camera_id=camera_id,
                evidence=selected,
                current_timestamp=now,
            )
            binding_stable = (
                stable_frame_count >= self.config.zoom_stability_window_frames
            )
            fov_mode = (
                ActiveVisionFovMode.ZOOM
                if binding_stable
                and selected.uncertainty_trace_deg2
                <= self.config.zoom_max_uncertainty_trace_deg2
                and ActiveVisionFovMode.ZOOM in camera.supported_fov_modes
                else _wide_or_current(camera)
            )
            return self._target_action(
                snapshot,
                camera,
                selected,
                now,
                intent=ActiveVisionIntent.OBSERVE_TARGET,
                fov_mode=fov_mode,
                reason="rule_fresh_assigned_projection",
            )
        if reacquire:
            self._reset_binding_stability(camera_id)
            selected = min(
                reacquire,
                key=lambda item: (
                    max(0.0, now - item.measurement_timestamp),
                    -item.visibility_probability,
                    item.global_track_id,
                ),
            )
            return self._target_action(
                snapshot,
                camera,
                selected,
                now,
                intent=ActiveVisionIntent.REACQUIRE,
                fov_mode=_wide_or_current(camera),
                reason="rule_reacquire_last_projection",
            )
        self._reset_binding_stability(camera_id)
        return self.scan_action(
            snapshot,
            camera=camera,
            current_timestamp=now,
            reason="rule_no_usable_assigned_projection",
        )

    def _advance_binding_stability(
        self,
        snapshot: ActiveVisionSnapshotV1,
        *,
        camera_id: str,
        evidence: ActiveVisionProjectionEvidence,
        current_timestamp: float,
    ) -> int:
        key = (
            camera_id,
            evidence.global_track_id,
            snapshot.plan.plan_version,
            snapshot.plan.coalition_version,
        )
        previous = self._binding_stability_by_camera.get(camera_id)
        if previous is None or previous.key != key:
            count = 1
        elif (
            current_timestamp + 1.0e-9 < previous.last_current_timestamp
            or snapshot.snapshot_timestamp + 1.0e-9
            < previous.last_snapshot_timestamp
            or evidence.measurement_timestamp + 1.0e-9
            < previous.last_measurement_timestamp
            or evidence.arrival_timestamp + 1.0e-9
            < previous.last_arrival_timestamp
        ):
            count = 1
        elif (
            current_timestamp - previous.last_current_timestamp
            > self.config.max_communication_age_s + 1.0e-9
            or snapshot.snapshot_timestamp - previous.last_snapshot_timestamp
            > self.config.max_communication_age_s + 1.0e-9
        ):
            count = 1
        elif (
            current_timestamp > previous.last_current_timestamp + 1.0e-9
            and snapshot.snapshot_timestamp > previous.last_snapshot_timestamp + 1.0e-9
            and evidence.measurement_timestamp
            > previous.last_measurement_timestamp + 1.0e-9
            and evidence.arrival_timestamp > previous.last_arrival_timestamp + 1.0e-9
        ):
            count = previous.stable_frame_count + 1
        else:
            count = previous.stable_frame_count
        self._binding_stability_by_camera[camera_id] = _BindingStabilityState(
            key=key,
            stable_frame_count=count,
            last_current_timestamp=current_timestamp,
            last_snapshot_timestamp=snapshot.snapshot_timestamp,
            last_measurement_timestamp=evidence.measurement_timestamp,
            last_arrival_timestamp=evidence.arrival_timestamp,
        )
        return count

    def _reset_binding_stability(self, camera_id: str) -> None:
        self._binding_stability_by_camera.pop(camera_id, None)

    def scan_action(
        self,
        snapshot: ActiveVisionSnapshotV1,
        *,
        camera: ActiveVisionCameraState,
        current_timestamp: float,
        reason: str,
    ) -> ActiveVisionActionV1:
        sectors = self.config.scan_sectors_deg
        start = (snapshot.plan.plan_version + sum(ord(ch) for ch in camera.camera_id)) % len(sectors)
        for offset in range(len(sectors)):
            sector = _camera_bounded_sector(
                camera, sectors[(start + offset) % len(sectors)]
            )
            if sector is None:
                continue
            if _reservation_conflict(
                snapshot,
                camera,
                current_timestamp,
                target_id=None,
                sector=sector,
            ):
                continue
            yaw_target = (sector[0] + sector[1]) * 0.5
            pitch_target = (sector[2] + sector[3]) * 0.5
            yaw_delta, pitch_delta = _bounded_delta(
                camera,
                yaw_target - camera.yaw_deg,
                pitch_target - camera.pitch_deg,
                self.config,
            )
            return _action(
                snapshot,
                camera,
                current_timestamp,
                intent=ActiveVisionIntent.SEARCH_SECTOR,
                yaw_delta_deg=yaw_delta,
                pitch_delta_deg=pitch_delta,
                fov_mode=_wide_or_current(camera),
                search_sector_deg=sector,
                reason=f"rule_scan:{reason}",
                config=self.config,
            )
        return _action(
            snapshot,
            camera,
            current_timestamp,
            intent=ActiveVisionIntent.HOLD,
            yaw_delta_deg=0.0,
            pitch_delta_deg=0.0,
            fov_mode=camera.current_fov_mode,
            reason=f"rule_hold:friendly_conflict:{reason}",
            config=self.config,
        )

    def _target_action(
        self,
        snapshot: ActiveVisionSnapshotV1,
        camera: ActiveVisionCameraState,
        evidence: ActiveVisionProjectionEvidence,
        now: float,
        *,
        intent: ActiveVisionIntent,
        fov_mode: ActiveVisionFovMode,
        reason: str,
    ) -> ActiveVisionActionV1:
        yaw_delta, pitch_delta = _bounded_delta(
            camera,
            evidence.yaw_error_deg,
            evidence.pitch_error_deg,
            self.config,
        )
        return _action(
            snapshot,
            camera,
            now,
            intent=intent,
            yaw_delta_deg=yaw_delta,
            pitch_delta_deg=pitch_delta,
            fov_mode=fov_mode,
            target_global_track_id=evidence.global_track_id,
            reason=reason,
            config=self.config,
        )


class ActiveVisionControllerV1:
    """Mode arbitration.  Runtime default is disabled; CLI may request shadow."""

    def __init__(
        self,
        *,
        rule_policy: DeterministicLookAtScanPolicy | None = None,
        learned_policy: ActiveVisionLearnedPolicy | None = None,
        safety_config: ActiveVisionSafetyConfigV1 | None = None,
        default_mode: ActiveVisionRuntimeMode = ActiveVisionRuntimeMode.DISABLED,
        clock: Any = time.perf_counter,
    ) -> None:
        self.config = safety_config or ActiveVisionSafetyConfigV1()
        self.rule_policy = rule_policy or DeterministicLookAtScanPolicy(self.config)
        self.learned_policy = learned_policy
        self.default_mode = ActiveVisionRuntimeMode(default_mode)
        self._clock = clock

    def decide(
        self,
        snapshot: ActiveVisionSnapshotV1,
        *,
        camera_id: str,
        current_timestamp: float,
        expected_plan_version: int,
        expected_coalition_version: int,
        expected_communication_version: int,
        requested_mode: ActiveVisionRuntimeMode | str | None = None,
    ) -> ActiveVisionDecisionV1:
        mode = self.default_mode if requested_mode is None else ActiveVisionRuntimeMode(requested_mode)
        rule_action = self.rule_policy.select_action(
            snapshot,
            camera_id=camera_id,
            current_timestamp=current_timestamp,
            expected_plan_version=expected_plan_version,
            expected_coalition_version=expected_coalition_version,
            expected_communication_version=expected_communication_version,
        )
        if mode is ActiveVisionRuntimeMode.DISABLED:
            return self._decision(
                snapshot,
                mode,
                ActiveVisionRuntimeMode.DISABLED,
                rule_action,
                requested_action=None,
                effective_action=rule_action,
                fallback_reason="learning_disabled",
                latency_ms=0.0,
                fingerprint=None,
            )
        policy = self.learned_policy
        if policy is None or not bool(getattr(policy, "available", False)):
            reason = "model_unavailable"
            if policy is not None and getattr(policy, "failure_reason", None):
                reason = str(policy.failure_reason)
            return self._decision(
                snapshot,
                mode,
                ActiveVisionRuntimeMode.SHADOW if mode is ActiveVisionRuntimeMode.SHADOW else ActiveVisionRuntimeMode.DISABLED,
                rule_action,
                requested_action=None,
                effective_action=rule_action,
                fallback_reason=reason,
                latency_ms=0.0,
                fingerprint=getattr(policy, "model_fingerprint", None),
            )

        started = self._clock()
        try:
            proposal = policy.propose(
                snapshot,
                camera_id=camera_id,
                current_timestamp=current_timestamp,
            )
        except Exception as exc:  # Policy failures never escape into camera scheduling.
            elapsed_ms = max(0.0, (self._clock() - started) * 1000.0)
            return self._decision(
                snapshot,
                mode,
                ActiveVisionRuntimeMode.SHADOW if mode is ActiveVisionRuntimeMode.SHADOW else ActiveVisionRuntimeMode.DISABLED,
                rule_action,
                requested_action=None,
                effective_action=rule_action,
                fallback_reason=f"model_exception:{type(exc).__name__}",
                latency_ms=elapsed_ms,
                fingerprint=getattr(policy, "model_fingerprint", None),
            )
        wall_ms = max(0.0, (self._clock() - started) * 1000.0)
        latency_ms = max(wall_ms, proposal.inference_latency_ms)
        try:
            fallback_reason = _proposal_failure(proposal, latency_ms, self.config)
            requested_action = proposal.action
            proposal_fingerprint = proposal.model_fingerprint
        except Exception:
            fallback_reason = "model_proposal_contract_error"
            requested_action = None
            proposal_fingerprint = getattr(policy, "model_fingerprint", None)
        if fallback_reason is None and requested_action is not None:
            fallback_reason = validate_active_vision_action_v1(
                requested_action,
                snapshot,
                camera_id=camera_id,
                current_timestamp=current_timestamp,
                expected_plan_version=expected_plan_version,
                expected_coalition_version=expected_coalition_version,
                expected_communication_version=expected_communication_version,
                config=self.config,
            )
        if mode is ActiveVisionRuntimeMode.SHADOW:
            return self._decision(
                snapshot,
                mode,
                ActiveVisionRuntimeMode.SHADOW,
                rule_action,
                requested_action=requested_action,
                effective_action=rule_action,
                fallback_reason=fallback_reason,
                latency_ms=latency_ms,
                fingerprint=proposal_fingerprint,
            )
        if not bool(getattr(policy, "assist_admitted", False)):
            fallback_reason = fallback_reason or "assist_not_admitted"
        if fallback_reason is not None or requested_action is None:
            return self._decision(
                snapshot,
                mode,
                ActiveVisionRuntimeMode.DISABLED,
                rule_action,
                requested_action=requested_action,
                effective_action=rule_action,
                fallback_reason=fallback_reason or "model_action_missing",
                latency_ms=latency_ms,
                fingerprint=proposal_fingerprint,
            )
        return self._decision(
            snapshot,
            mode,
            ActiveVisionRuntimeMode.ASSIST,
            rule_action,
            requested_action=requested_action,
            effective_action=requested_action,
            fallback_reason=None,
            latency_ms=latency_ms,
            fingerprint=proposal_fingerprint,
        )

    @staticmethod
    def _decision(
        snapshot: ActiveVisionSnapshotV1,
        requested_mode: ActiveVisionRuntimeMode,
        effective_mode: ActiveVisionRuntimeMode,
        rule_action: ActiveVisionActionV1,
        *,
        requested_action: ActiveVisionActionV1 | None,
        effective_action: ActiveVisionActionV1,
        fallback_reason: str | None,
        latency_ms: float,
        fingerprint: str | None,
    ) -> ActiveVisionDecisionV1:
        return ActiveVisionDecisionV1(
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            rule_action=rule_action,
            requested_action=requested_action,
            effective_action=effective_action,
            fallback_reason=fallback_reason,
            inference_latency_ms=float(latency_ms),
            model_fingerprint=fingerprint,
            plan_version=snapshot.plan.plan_version,
            coalition_version=snapshot.plan.coalition_version,
            communication_version=snapshot.communication.communication_version,
        )


def enumerate_safe_action_candidates(
    snapshot: ActiveVisionSnapshotV1,
    *,
    camera_id: str,
    current_timestamp: float,
    config: ActiveVisionSafetyConfigV1 | None = None,
) -> tuple[ActiveVisionActionV1, ...]:
    """Create the finite action set consumed by BC/PPO and online inference."""

    cfg = config or ActiveVisionSafetyConfigV1()
    camera = snapshot.camera(camera_id)
    now = _finite(current_timestamp, "current_timestamp")
    candidates: list[ActiveVisionActionV1] = []
    for track_id in snapshot.assigned_target_ids(camera_id):
        evidence = snapshot.projection(camera_id, track_id)
        if evidence is None:
            continue
        yaw_delta, pitch_delta = _bounded_delta(
            camera,
            evidence.yaw_error_deg,
            evidence.pitch_error_deg,
            cfg,
        )
        for mode in camera.supported_fov_modes:
            candidates.append(
                _action(
                    snapshot,
                    camera,
                    now,
                    intent=ActiveVisionIntent.OBSERVE_TARGET,
                    yaw_delta_deg=yaw_delta,
                    pitch_delta_deg=pitch_delta,
                    fov_mode=mode,
                    target_global_track_id=track_id,
                    reason="learned_candidate_observe",
                    config=cfg,
                )
            )
        candidates.append(
            _action(
                snapshot,
                camera,
                now,
                intent=ActiveVisionIntent.REACQUIRE,
                yaw_delta_deg=yaw_delta,
                pitch_delta_deg=pitch_delta,
                fov_mode=_wide_or_current(camera),
                target_global_track_id=track_id,
                reason="learned_candidate_reacquire",
                config=cfg,
            )
        )
    for configured_sector in cfg.scan_sectors_deg:
        sector = _camera_bounded_sector(camera, configured_sector)
        if sector is None:
            continue
        yaw_target = (sector[0] + sector[1]) * 0.5
        pitch_target = (sector[2] + sector[3]) * 0.5
        yaw_delta, pitch_delta = _bounded_delta(
            camera,
            yaw_target - camera.yaw_deg,
            pitch_target - camera.pitch_deg,
            cfg,
        )
        candidates.append(
            _action(
                snapshot,
                camera,
                now,
                intent=ActiveVisionIntent.SEARCH_SECTOR,
                yaw_delta_deg=yaw_delta,
                pitch_delta_deg=pitch_delta,
                fov_mode=_wide_or_current(camera),
                search_sector_deg=sector,
                reason="learned_candidate_search",
                config=cfg,
            )
        )
    candidates.append(
        _action(
            snapshot,
            camera,
            now,
            intent=ActiveVisionIntent.HOLD,
            yaw_delta_deg=0.0,
            pitch_delta_deg=0.0,
            fov_mode=camera.current_fov_mode,
            reason="learned_candidate_hold",
            config=cfg,
        )
    )
    unique = {item.action_key: item for item in candidates}
    return tuple(unique[key] for key in sorted(unique, key=repr))


def validate_active_vision_action_v1(
    action: ActiveVisionActionV1,
    snapshot: ActiveVisionSnapshotV1,
    *,
    camera_id: str,
    current_timestamp: float,
    expected_plan_version: int,
    expected_coalition_version: int,
    expected_communication_version: int,
    config: ActiveVisionSafetyConfigV1 | None = None,
) -> str | None:
    """Return a stable failure reason, or ``None`` when execution is safe."""

    cfg = config or ActiveVisionSafetyConfigV1()
    now = _finite(current_timestamp, "current_timestamp")
    camera = snapshot.camera(camera_id)
    version_failure = _snapshot_version_failure(
        snapshot,
        now,
        expected_plan_version=expected_plan_version,
        expected_coalition_version=expected_coalition_version,
        expected_communication_version=expected_communication_version,
        config=cfg,
    )
    if version_failure is not None:
        return version_failure
    if action.camera_id != camera_id:
        return "camera_member_mismatch"
    if camera.state_timestamp > now + 1.0e-9:
        return "camera_state_from_future"
    if max(0.0, now - camera.state_timestamp) > cfg.max_evidence_age_s:
        return "camera_state_stale"
    if action.plan_version != expected_plan_version:
        return "stale_action_plan_version"
    if action.coalition_version != expected_coalition_version:
        return "stale_action_coalition_version"
    if action.communication_version != expected_communication_version:
        return "stale_action_communication_version"
    if action.issued_timestamp > now + 1.0e-9 or action.expires_timestamp < now:
        return "action_timeout"
    if action.expires_timestamp - action.issued_timestamp > cfg.action_timeout_s + 1.0e-9:
        return "action_lifetime_exceeds_limit"
    if action.fov_mode not in camera.supported_fov_modes:
        return "unsupported_fov_mode"
    if action.search_sector_deg is not None and (
        action.search_sector_deg[0] < camera.yaw_limits_deg[0] - 1.0e-9
        or action.search_sector_deg[1] > camera.yaw_limits_deg[1] + 1.0e-9
        or action.search_sector_deg[2] < camera.pitch_limits_deg[0] - 1.0e-9
        or action.search_sector_deg[3] > camera.pitch_limits_deg[1] + 1.0e-9
    ):
        return "search_sector_gimbal_limit"
    if camera.action_in_progress_until is not None and camera.action_in_progress_until > now:
        if action.intent is not ActiveVisionIntent.HOLD:
            return "gimbal_busy"
    if not camera.slew_available and (
        abs(action.yaw_delta_deg) > 1.0e-12 or abs(action.pitch_delta_deg) > 1.0e-12
    ):
        return "gimbal_slew_unavailable"
    if max(abs(action.yaw_delta_deg), abs(action.pitch_delta_deg)) > cfg.max_gimbal_increment_deg + 1.0e-9:
        return "gimbal_increment_limit"
    duration = action.expires_timestamp - action.issued_timestamp
    yaw_rate = abs(action.yaw_delta_deg) / duration
    pitch_rate = abs(action.pitch_delta_deg) / duration
    slew_rate = math.hypot(action.yaw_delta_deg, action.pitch_delta_deg) / duration
    if yaw_rate > camera.max_yaw_rate_deg_s + 1.0e-9:
        return "gimbal_yaw_rate_limit"
    if pitch_rate > camera.max_pitch_rate_deg_s + 1.0e-9:
        return "gimbal_pitch_rate_limit"
    if slew_rate > camera.max_slew_deg_s + 1.0e-9:
        return "gimbal_slew_rate_limit"
    next_yaw = camera.yaw_deg + action.yaw_delta_deg
    next_pitch = camera.pitch_deg + action.pitch_delta_deg
    if not camera.yaw_limits_deg[0] <= next_yaw <= camera.yaw_limits_deg[1]:
        return "gimbal_yaw_limit"
    if not camera.pitch_limits_deg[0] <= next_pitch <= camera.pitch_limits_deg[1]:
        return "gimbal_pitch_limit"
    target_id = action.target_global_track_id
    if target_id is not None:
        track_ids = {item.global_track_id for item in snapshot.tracks}
        if target_id not in track_ids or target_id not in snapshot.plan.candidate_global_track_ids:
            return "candidate_target_missing"
        if target_id not in snapshot.assigned_target_ids(camera_id):
            return "target_not_in_current_assignment"
        evidence = snapshot.projection(camera_id, target_id)
        if evidence is None:
            return "projection_evidence_missing"
        if (
            evidence.measurement_timestamp > now + 1.0e-9
            or evidence.arrival_timestamp > now + 1.0e-9
        ):
            return "projection_evidence_from_future"
        age = max(0.0, now - evidence.measurement_timestamp)
        allowed_age = (
            cfg.reacquire_evidence_age_s
            if action.intent is ActiveVisionIntent.REACQUIRE
            else cfg.max_evidence_age_s
        )
        if age > allowed_age:
            return "projection_evidence_stale"
        if action.intent is ActiveVisionIntent.OBSERVE_TARGET:
            if evidence.association_confidence < cfg.minimum_association_confidence:
                return "low_projection_confidence"
            if evidence.visibility_probability < cfg.minimum_visibility_probability:
                return "low_visibility"
            if evidence.occlusion_fraction > cfg.maximum_occlusion_fraction:
                return "occlusion_limit"
    if _reservation_conflict(
        snapshot,
        camera,
        now,
        target_id=target_id,
        sector=action.search_sector_deg,
    ):
        return "friendly_observation_conflict"
    return None


def assert_truth_free_active_vision_payload(payload: Any) -> None:
    """Recursively reject simulator/evaluator identity from policy inputs."""

    violations: list[str] = []
    seen: set[int] = set()

    def visit(value: Any, path: str, *, allow_center_id: bool = False) -> None:
        if isinstance(value, str):
            if not allow_center_id and _TRUTH_LIKE_INPUT_VALUE.search(value):
                violations.append(path)
            return
        if value is None or isinstance(value, (bytes, bool, int, float, np.generic, np.ndarray, Enum)):
            return
        identity = id(value)
        if identity in seen:
            return
        seen.add(identity)
        if is_dataclass(value) and not isinstance(value, type):
            for item in fields(value):
                key = _normalise_key(item.name)
                child = f"{path}.{item.name}"
                if _forbidden_input_key(key):
                    violations.append(child)
                else:
                    visit(
                        getattr(value, item.name),
                        child,
                        allow_center_id=key in {"global_track_id", "target_global_track_id"},
                    )
            return
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                key = _normalise_key(str(raw_key))
                child = f"{path}.{raw_key}"
                if _forbidden_input_key(key):
                    violations.append(child)
                else:
                    visit(
                        item,
                        child,
                        allow_center_id=key in {"global_track_id", "target_global_track_id"},
                    )
            return
        if isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if hasattr(value, "__dict__") and not isinstance(value, type):
            visit(vars(value), path)

    visit(payload, "snapshot")
    if violations:
        raise ValueError(
            "active-vision input contains forbidden truth/actor/object identity fields: "
            + ", ".join(sorted(set(violations)))
        )


def _snapshot_version_failure(
    snapshot: ActiveVisionSnapshotV1,
    now: float,
    *,
    expected_plan_version: int,
    expected_coalition_version: int,
    expected_communication_version: int,
    config: ActiveVisionSafetyConfigV1,
) -> str | None:
    if snapshot.plan.plan_version != int(expected_plan_version):
        return "stale_plan_version"
    if snapshot.plan.coalition_version != int(expected_coalition_version):
        return "stale_coalition_version"
    communication = snapshot.communication
    if communication.update_timestamp > now + 1.0e-9:
        return "communication_timestamp_from_future"
    if communication.communication_version != int(expected_communication_version):
        return "stale_communication_version"
    if communication.plan_version != snapshot.plan.plan_version:
        return "communication_plan_version_mismatch"
    if communication.coalition_version != snapshot.plan.coalition_version:
        return "communication_coalition_version_mismatch"
    if not communication.healthy:
        return "communication_unhealthy"
    if max(0.0, now - communication.update_timestamp) > config.max_communication_age_s:
        return "communication_stale"
    return None


def _proposal_failure(
    proposal: ActiveVisionPolicyProposal,
    latency_ms: float,
    config: ActiveVisionSafetyConfigV1,
) -> str | None:
    if not np.isfinite(proposal.confidence) or not np.isfinite(
        proposal.inference_latency_ms
    ) or not np.isfinite(latency_ms):
        return "model_non_finite_output"
    if proposal.failure_reason:
        return str(proposal.failure_reason)
    if proposal.ood:
        return "model_input_ood"
    if latency_ms > config.model_inference_timeout_ms:
        return "model_inference_timeout"
    if proposal.confidence < config.learned_minimum_confidence:
        return "model_low_confidence"
    if proposal.action is None:
        return "model_action_missing"
    return None


def _action(
    snapshot: ActiveVisionSnapshotV1,
    camera: ActiveVisionCameraState,
    now: float,
    *,
    intent: ActiveVisionIntent,
    yaw_delta_deg: float,
    pitch_delta_deg: float,
    fov_mode: ActiveVisionFovMode,
    reason: str,
    config: ActiveVisionSafetyConfigV1,
    target_global_track_id: str | None = None,
    search_sector_deg: tuple[float, float, float, float] | None = None,
) -> ActiveVisionActionV1:
    return ActiveVisionActionV1(
        camera_id=camera.camera_id,
        issued_timestamp=now,
        expires_timestamp=now + config.action_timeout_s,
        plan_version=snapshot.plan.plan_version,
        coalition_version=snapshot.plan.coalition_version,
        communication_version=snapshot.communication.communication_version,
        intent=intent,
        yaw_delta_deg=yaw_delta_deg,
        pitch_delta_deg=pitch_delta_deg,
        fov_mode=fov_mode,
        target_global_track_id=target_global_track_id,
        search_sector_deg=search_sector_deg,
        reason=reason,
    )


def _bounded_delta(
    camera: ActiveVisionCameraState,
    yaw_delta_deg: float,
    pitch_delta_deg: float,
    config: ActiveVisionSafetyConfigV1,
) -> tuple[float, float]:
    yaw = _finite(yaw_delta_deg, "yaw_delta_deg")
    pitch = _finite(pitch_delta_deg, "pitch_delta_deg")
    duration = config.action_timeout_s
    yaw_limit = min(config.max_gimbal_increment_deg, camera.max_yaw_rate_deg_s * duration)
    pitch_limit = min(config.max_gimbal_increment_deg, camera.max_pitch_rate_deg_s * duration)
    yaw = float(np.clip(yaw, -yaw_limit, yaw_limit))
    pitch = float(np.clip(pitch, -pitch_limit, pitch_limit))
    yaw = float(np.clip(yaw, camera.yaw_limits_deg[0] - camera.yaw_deg, camera.yaw_limits_deg[1] - camera.yaw_deg))
    pitch = float(
        np.clip(
            pitch,
            camera.pitch_limits_deg[0] - camera.pitch_deg,
            camera.pitch_limits_deg[1] - camera.pitch_deg,
        )
    )
    slew = math.hypot(yaw, pitch)
    max_slew = camera.max_slew_deg_s * duration
    if slew > max_slew and slew > 0.0:
        scale = max_slew / slew
        yaw *= scale
        pitch *= scale
    return (float(yaw), float(pitch))


def _projection_binding_is_ambiguous(
    selected: ActiveVisionProjectionEvidence,
    candidates: Sequence[ActiveVisionProjectionEvidence],
    *,
    minimum_margin: float,
) -> bool:
    """Treat near-equal assigned projections as unsafe for narrow FOV."""

    alternatives = tuple(
        item for item in candidates if item.global_track_id != selected.global_track_id
    )
    if not alternatives:
        return False

    def score(item: ActiveVisionProjectionEvidence) -> float:
        return (
            item.association_confidence
            * item.visibility_probability
            * (1.0 - item.occlusion_fraction)
        )

    selected_score = score(selected)
    alternative_score = max(score(item) for item in alternatives)
    return selected_score - alternative_score < minimum_margin - 1.0e-12


def _reservation_conflict(
    snapshot: ActiveVisionSnapshotV1,
    camera: ActiveVisionCameraState,
    now: float,
    *,
    target_id: str | None,
    sector: tuple[float, float, float, float] | None,
) -> bool:
    communication = snapshot.communication
    for reservation in communication.peer_reservations:
        if (
            not reservation.exclusive
            or reservation.expires_timestamp < now
            or reservation.communication_version != communication.communication_version
            or reservation.coalition_version != snapshot.plan.coalition_version
            or reservation.owner_resource_id == camera.resource_id
        ):
            continue
        if target_id is not None and reservation.global_track_id == target_id:
            return True
        if sector is not None and reservation.sector_deg is not None and _sectors_overlap(
            sector, reservation.sector_deg
        ):
            return True
    return False


def _sectors_overlap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> bool:
    return max(left[0], right[0]) < min(left[1], right[1]) and max(
        left[2], right[2]
    ) < min(left[3], right[3])


def _camera_bounded_sector(
    camera: ActiveVisionCameraState,
    sector: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    bounded = (
        max(sector[0], camera.yaw_limits_deg[0]),
        min(sector[1], camera.yaw_limits_deg[1]),
        max(sector[2], camera.pitch_limits_deg[0]),
        min(sector[3], camera.pitch_limits_deg[1]),
    )
    if bounded[0] >= bounded[1] or bounded[2] >= bounded[3]:
        return None
    return bounded


def _wide_or_current(camera: ActiveVisionCameraState) -> ActiveVisionFovMode:
    if ActiveVisionFovMode.WIDE in camera.supported_fov_modes:
        return ActiveVisionFovMode.WIDE
    return camera.current_fov_mode


def _forbidden_input_key(key: str) -> bool:
    return key in _FORBIDDEN_INPUT_KEYS or key.startswith("truth_") or any(
        key.endswith(suffix)
        for suffix in (
            "_actor_id",
            "_actor_name",
            "_object_id",
            "_object_name",
            "_truth_id",
            "_entity_id",
            "_entity_name",
        )
    )


def _normalise_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _non_empty(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _increasing_pair(values: Sequence[float], name: str) -> tuple[float, float]:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (2,) or not np.all(np.isfinite(array)) or array[0] >= array[1]:
        raise ValueError(f"{name} must contain two increasing finite values")
    return (float(array[0]), float(array[1]))


def _sector(values: Sequence[float]) -> tuple[float, float, float, float]:
    array = np.asarray(values, dtype=float).reshape(-1)
    if array.shape != (4,) or not np.all(np.isfinite(array)):
        raise ValueError("search sector must contain four finite values")
    yaw_min, yaw_max, pitch_min, pitch_max = (float(value) for value in array)
    if yaw_min >= yaw_max or pitch_min >= pitch_max:
        raise ValueError("search sector bounds must be increasing")
    if yaw_min < -180.0 or yaw_max > 180.0 or pitch_min < -90.0 or pitch_max > 90.0:
        raise ValueError("search sector exceeds physical angular bounds")
    return (yaw_min, yaw_max, pitch_min, pitch_max)


__all__ = [
    "ACTIVE_VISION_ACTION_SCHEMA_VERSION",
    "ACTIVE_VISION_ACTION_SPACE_VERSION",
    "ACTIVE_VISION_FEATURE_SCHEMA_VERSION",
    "ACTIVE_VISION_SNAPSHOT_SCHEMA_VERSION",
    "ActiveVisionActionV1",
    "ActiveVisionAssignmentReference",
    "ActiveVisionCameraState",
    "ActiveVisionCommunicationState",
    "ActiveVisionControllerV1",
    "ActiveVisionDecisionV1",
    "ActiveVisionFovMode",
    "ActiveVisionIntent",
    "ActiveVisionLearnedPolicy",
    "ActiveVisionPlanReference",
    "ActiveVisionPolicyProposal",
    "ActiveVisionProjectionEvidence",
    "ActiveVisionRuntimeMode",
    "ActiveVisionSafetyConfigV1",
    "ActiveVisionSnapshotV1",
    "ActiveVisionTrackReference",
    "DeterministicLookAtScanPolicy",
    "FriendlyObservationReservation",
    "assert_truth_free_active_vision_payload",
    "enumerate_safe_action_candidates",
    "validate_active_vision_action_v1",
]
