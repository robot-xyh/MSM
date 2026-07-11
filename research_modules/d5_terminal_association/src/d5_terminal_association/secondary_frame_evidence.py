"""Frame-scoped secondary-camera evidence for D4 arbitration.

The builder in this module deliberately emits one synchronized frame at a
time.  It may inspect a registration result that contains history, but it
filters candidates by ``frame_id`` and never converts episode aggregates into
live takeover evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Iterable, Mapping

from .airsim_cv_adapter import SecondaryCameraFrameCoverage, SecondaryNetworkFrameCoverage
from .cross_view_registration import DetectToGlobalTrackRegistrationResult


_D4_TERMINAL_SUMMARY_FIELDS = (
    "secondary_single_camera_full_view_frame_rate",
    "secondary_network_joint_full_view_frame_rate",
    "secondary_network_mean_coverage_ratio",
    "cue_freshness_s",
    "gimbal_pointing_ok",
    "secondary_coverage_ratio",
    "cross_view_association_count",
    "stable_cross_view_registration_count",
    "not_registered_count",
    "cross_view_conversion_gap",
    "secondary_detect_to_cross_view_reject_reasons",
    "secondary_detect_available_but_not_registered",
    "secondary_detect_to_cross_view_diagnostic",
)

_SAFE_CALIBRATION_METADATA_KEYS = {
    "calibration_health",
    "calibration_health_counts",
    "camera_pose_source",
    "camera_pose_source_counts",
    "drift_warning",
    "drift_warning_count",
    "projection_valid_count",
    "reprojection_error_px",
    "reprojection_error_px_max",
    "reprojection_error_px_mean",
}


@dataclass(frozen=True)
class SecondaryFrameAssociationEvidence:
    """D5 evidence for exactly one synchronized secondary-camera frame.

    Fields named ``*_frame_rate`` intentionally use ``0.0`` or ``1.0`` for
    the current frame because D4's existing ``TerminalAssociationSummary``
    contract uses those names.  ``evidence_scope`` and metadata make the
    single-frame semantics explicit.
    """

    frame_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    detector_backend: str
    tracker_backend: str
    secondary_single_camera_full_view_frame_rate: float
    secondary_network_joint_full_view_frame_rate: float
    secondary_network_mean_coverage_ratio: float
    cue_freshness_s: float | None
    gimbal_pointing_ok: bool | None
    secondary_coverage_ratio: float
    cross_view_association_count: int
    stable_cross_view_registration_count: int
    not_registered_count: int
    cross_view_conversion_gap: float
    secondary_detect_to_cross_view_reject_reasons: tuple[str, ...] = ()
    secondary_detect_available_but_not_registered: bool = False
    secondary_detect_to_cross_view_diagnostic: str | None = None
    evidence_scope: str = "single_synchronized_frame"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.frame_id:
            raise ValueError("frame_id must be non-empty")
        if self.evidence_scope != "single_synchronized_frame":
            raise ValueError("secondary arbitration evidence must remain frame-scoped")
        for name in (
            "measurement_timestamp",
            "arrival_timestamp",
            "secondary_single_camera_full_view_frame_rate",
            "secondary_network_joint_full_view_frame_rate",
            "secondary_network_mean_coverage_ratio",
            "secondary_coverage_ratio",
            "cross_view_conversion_gap",
        ):
            value = float(getattr(self, name))
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.arrival_timestamp < self.measurement_timestamp:
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")
        if self.cue_freshness_s is not None:
            cue_freshness = float(self.cue_freshness_s)
            if not isfinite(cue_freshness) or cue_freshness < 0.0:
                raise ValueError("cue_freshness_s must be finite and non-negative")
            object.__setattr__(self, "cue_freshness_s", cue_freshness)
        for name in (
            "secondary_single_camera_full_view_frame_rate",
            "secondary_network_joint_full_view_frame_rate",
            "secondary_network_mean_coverage_ratio",
            "secondary_coverage_ratio",
        ):
            value = getattr(self, name)
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        for name in (
            "cross_view_association_count",
            "stable_cross_view_registration_count",
            "not_registered_count",
        ):
            value = int(getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "secondary_detect_to_cross_view_reject_reasons",
            tuple(dict.fromkeys(str(item) for item in self.secondary_detect_to_cross_view_reject_reasons)),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_terminal_association_summary_fields(self) -> dict[str, Any]:
        """Return kwargs accepted by D4's existing summary DTO."""

        return {name: getattr(self, name) for name in _D4_TERMINAL_SUMMARY_FIELDS}

    def to_metadata(self) -> dict[str, Any]:
        """Return serializable frame provenance plus D4-consumable fields."""

        return {
            **self.metadata,
            "frame_id": self.frame_id,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "measurement_age_s": self.arrival_timestamp - self.measurement_timestamp,
            "detector_backend": self.detector_backend,
            "tracker_backend": self.tracker_backend,
            "evidence_scope": self.evidence_scope,
            "episode_aggregate_allowed": False,
            "truth_id_online_use": "ignored",
            **self.to_terminal_association_summary_fields(),
        }


def build_secondary_frame_association_evidence(
    *,
    frame_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    camera_frames: Iterable[SecondaryCameraFrameCoverage],
    network_frame: SecondaryNetworkFrameCoverage,
    registration_result: DetectToGlobalTrackRegistrationResult,
    detector_backend: str,
    tracker_backend: str,
    cue_timestamp: float | None = None,
    gimbal_pointing_ok: bool | None = None,
    calibration_metadata: Mapping[str, Any] | None = None,
    timestamp_tolerance_s: float = 0.05,
) -> SecondaryFrameAssociationEvidence:
    """Build one frame of secondary visual evidence for D4.

    ``registration_result`` may contain historical candidates.  Only
    candidates whose ``frame_id`` equals the requested synchronized frame are
    consumed.  Camera coverage with another frame ID or timestamp is rejected
    so episode-level summaries cannot accidentally enter live arbitration.
    """

    if not frame_id:
        raise ValueError("frame_id must be non-empty")
    if timestamp_tolerance_s < 0.0:
        raise ValueError("timestamp_tolerance_s must be non-negative")
    measurement_timestamp = float(measurement_timestamp)
    arrival_timestamp = float(arrival_timestamp)
    frames = tuple(camera_frames)
    if not frames:
        raise ValueError("camera_frames must contain the current synchronized frame")
    if network_frame.frame_id != frame_id:
        raise ValueError("network_frame does not match the requested frame_id")
    for camera_frame in frames:
        if camera_frame.frame_id != frame_id:
            raise ValueError("camera_frames must all belong to the requested frame_id")
        if (
            camera_frame.timestamp is not None
            and abs(camera_frame.timestamp - measurement_timestamp) > timestamp_tolerance_s
        ):
            raise ValueError("camera frame timestamp exceeds synchronization tolerance")

    current_candidates = tuple(
        candidate
        for candidate in registration_result.candidates
        if candidate.frame_id == frame_id
        and abs(candidate.timestamp - measurement_timestamp) <= timestamp_tolerance_s
    )
    local_keys = {
        (candidate.resource_id, candidate.camera_id, candidate.local_track_id)
        for candidate in current_candidates
    }
    stable_keys = {
        (candidate.resource_id, candidate.camera_id, candidate.local_track_id)
        for candidate in current_candidates
        if candidate.stable_cross_view_support
    }
    selected_global_ids = {
        candidate.global_track_id
        for candidate in current_candidates
        if candidate.selected and candidate.global_track_id is not None
    }
    stable_count = len(stable_keys)
    not_registered_count = max(0, len(local_keys) - stable_count)
    reject_reasons = tuple(
        dict.fromkeys(
            reason
            for candidate in current_candidates
            if not candidate.stable_cross_view_support
            for reason in candidate.reject_reasons
            if reason != "registered_to_global_track"
        )
    )
    if not_registered_count and not reject_reasons:
        reject_reasons = ("stability_window_failed",)

    detect_count = max(
        len(local_keys),
        sum(int(frame.metadata.get("detection_count", 0)) for frame in frames),
    )
    detect_available_but_not_registered = detect_count > 0 and stable_count == 0
    if detect_available_but_not_registered:
        diagnostic = reject_reasons[0] if reject_reasons else "not_registered_in_current_frame"
    elif not_registered_count:
        diagnostic = "partial_frame_registration"
    else:
        diagnostic = "frame_registration_usable"

    cue_freshness = _cue_freshness_s(
        frames,
        measurement_timestamp=measurement_timestamp,
        cue_timestamp=cue_timestamp,
    )
    resolved_gimbal_ok = _gimbal_pointing_ok(frames, explicit=gimbal_pointing_ok)
    calibration = _frame_calibration_metadata(current_candidates, calibration_metadata)
    ignored_candidate_count = len(registration_result.candidates) - len(current_candidates)

    return SecondaryFrameAssociationEvidence(
        frame_id=frame_id,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        detector_backend=str(detector_backend),
        tracker_backend=str(tracker_backend),
        secondary_single_camera_full_view_frame_rate=(
            1.0 if any(frame.full_view for frame in frames) else 0.0
        ),
        secondary_network_joint_full_view_frame_rate=(1.0 if network_frame.joint_full_view else 0.0),
        secondary_network_mean_coverage_ratio=network_frame.coverage_ratio,
        cue_freshness_s=cue_freshness,
        gimbal_pointing_ok=resolved_gimbal_ok,
        secondary_coverage_ratio=network_frame.coverage_ratio,
        cross_view_association_count=len(selected_global_ids),
        stable_cross_view_registration_count=stable_count,
        not_registered_count=not_registered_count,
        cross_view_conversion_gap=float(max(0, detect_count - stable_count)),
        secondary_detect_to_cross_view_reject_reasons=reject_reasons,
        secondary_detect_available_but_not_registered=detect_available_but_not_registered,
        secondary_detect_to_cross_view_diagnostic=diagnostic,
        metadata={
            "camera_count": len(frames),
            "current_frame_candidate_count": len(current_candidates),
            "ignored_other_frame_candidate_count": ignored_candidate_count,
            "current_frame_detection_count": detect_count,
            "current_frame_selected_global_track_count": len(selected_global_ids),
            "registration_count_semantics": "camera_local_tracks_in_current_frame",
            "coverage_semantics": "current_frame_not_episode_aggregate",
            "backend_metadata": {
                "detector_backend": str(detector_backend),
                "tracker_backend": str(tracker_backend),
                "registration_assignment_backends": tuple(
                    registration_result.metadata.get("assignment_backends", ())
                ),
            },
            "calibration_metadata": calibration,
        },
    )


def _cue_freshness_s(
    frames: tuple[SecondaryCameraFrameCoverage, ...],
    *,
    measurement_timestamp: float,
    cue_timestamp: float | None,
) -> float | None:
    if cue_timestamp is not None:
        return max(0.0, measurement_timestamp - float(cue_timestamp))
    explicit = [
        float(frame.metadata["cue_freshness_s"])
        for frame in frames
        if frame.metadata.get("cue_freshness_s") is not None
    ]
    if explicit:
        return max(explicit)
    cue_times = [
        float(frame.metadata["cue_timestamp"])
        for frame in frames
        if frame.metadata.get("cue_timestamp") is not None
    ]
    if cue_times:
        return max(0.0, measurement_timestamp - min(cue_times))
    return None


def _gimbal_pointing_ok(
    frames: tuple[SecondaryCameraFrameCoverage, ...],
    *,
    explicit: bool | None,
) -> bool | None:
    if explicit is not None:
        return bool(explicit)
    statuses = [
        bool(frame.metadata["gimbal_pointing_ok"])
        for frame in frames
        if frame.metadata.get("gimbal_pointing_ok") is not None
    ]
    if not statuses:
        return None
    return all(statuses)


def _frame_calibration_metadata(
    candidates: tuple[Any, ...],
    supplied: Mapping[str, Any] | None,
) -> dict[str, Any]:
    health_counts: dict[str, int] = {}
    pose_source_counts: dict[str, int] = {}
    drift_count = 0
    for candidate in candidates:
        health = str(getattr(candidate, "calibration_health", "unknown"))
        pose_source = str(getattr(candidate, "camera_pose_source", "unknown"))
        health_counts[health] = health_counts.get(health, 0) + 1
        pose_source_counts[pose_source] = pose_source_counts.get(pose_source, 0) + 1
        drift_count += int(bool(getattr(candidate, "drift_warning", False)))
    metadata: dict[str, Any] = {
        "calibration_health_counts": dict(sorted(health_counts.items())),
        "camera_pose_source_counts": dict(sorted(pose_source_counts.items())),
        "drift_warning_count": drift_count,
    }
    for key, value in (supplied or {}).items():
        if str(key) in _SAFE_CALIBRATION_METADATA_KEYS:
            metadata[str(key)] = value
    return metadata
