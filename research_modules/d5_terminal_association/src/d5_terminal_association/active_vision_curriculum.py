"""Deterministic in-memory supplemental curriculum for D5 active vision.

The builder creates one truth-free online episode for one caller-owned seed.
It deliberately does not stage files, create offline labels, or synthesize a
center identity.  Every effective action comes from the existing rule
controller and is passed through the deterministic camera command executor.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
from typing import Any

from .active_vision_camera_executor import (
    ActiveVisionCameraExecutionOutcome,
    ActiveVisionCameraFault,
    DeterministicCameraCommandExecutor,
)
from .active_vision_contracts import (
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionControllerV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSafetyConfigV1,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    DeterministicLookAtScanPolicy,
    assert_truth_free_active_vision_payload,
)
from .active_vision_episode_dataset import (
    ActiveVisionCameraFeedbackV1,
    ActiveVisionEpisodeRecordV2,
    ActiveVisionSourceIdentityV1,
    active_vision_sample_from_decision,
)


ACTIVE_VISION_CURRICULUM_SCHEMA_VERSION = "d5.active-vision-curriculum.v1"
ACTIVE_VISION_CURRICULUM_SUMMARY_SCHEMA_VERSION = (
    "d5.active-vision-curriculum-summary.v1"
)
ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT = 8
ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT = 12

_INTERCEPTOR_ROLE = "interceptor"
_RECON_ROLE = "recon"
_ROLE_ORDER = (_INTERCEPTOR_ROLE, _RECON_ROLE)
_FRAME_INTERVAL_S = 0.1
_SEGMENT_GAP_S = 1.0
_EXECUTION_DELAY_S = 0.05
_FRESH_EVIDENCE_AGE_S = 0.05
_REACQUIRE_EVIDENCE_AGE_S = 1.0
_PORTABLE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+-]*")


@dataclass(frozen=True)
class ActiveVisionCurriculumConfig:
    """Caller-owned identities and version origins for one curriculum episode."""

    global_track_id: str
    scenario_version: str = "d5-active-vision-curriculum-v1"
    episode_id_prefix: str = "active-vision-curriculum"
    interceptor_camera_id: str = "curriculum-interceptor-camera"
    interceptor_resource_id: str = "curriculum-interceptor-resource"
    recon_camera_id: str = "curriculum-recon-camera"
    recon_resource_id: str = "curriculum-recon-resource"
    initial_plan_version: int = 1
    initial_coalition_version: int = 1
    initial_communication_version: int = 1
    initial_track_version: int = 1
    start_timestamp_s: float = 1000.0
    schema_version: str = ACTIVE_VISION_CURRICULUM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_CURRICULUM_SCHEMA_VERSION:
            raise ValueError("active-vision curriculum config schema mismatch")
        for name in (
            "global_track_id",
            "scenario_version",
            "episode_id_prefix",
            "interceptor_camera_id",
            "interceptor_resource_id",
            "recon_camera_id",
            "recon_resource_id",
        ):
            object.__setattr__(self, name, _portable_key(getattr(self, name), name))
        if self.interceptor_camera_id == self.recon_camera_id:
            raise ValueError("interceptor and recon camera IDs must be distinct")
        if self.interceptor_resource_id == self.recon_resource_id:
            raise ValueError("interceptor and recon resource IDs must be distinct")
        for name in (
            "initial_plan_version",
            "initial_coalition_version",
            "initial_communication_version",
            "initial_track_version",
        ):
            object.__setattr__(self, name, _non_negative_integer(getattr(self, name), name))
        start = _finite(self.start_timestamp_s, "start_timestamp_s")
        if start < 0.0:
            raise ValueError("start_timestamp_s must be non-negative")
        if any(start + delta == start for delta in (_EXECUTION_DELAY_S, _FRAME_INTERVAL_S)):
            raise ValueError("start_timestamp_s is too large for the curriculum time resolution")
        object.__setattr__(self, "start_timestamp_s", start)
        assert_truth_free_active_vision_payload(self)

    def to_payload(self) -> dict[str, Any]:
        """Return the stable caller-owned curriculum configuration."""

        return {
            "schema_version": self.schema_version,
            "global_track_id": self.global_track_id,
            "scenario_version": self.scenario_version,
            "episode_id_prefix": self.episode_id_prefix,
            "interceptor_camera_id": self.interceptor_camera_id,
            "interceptor_resource_id": self.interceptor_resource_id,
            "recon_camera_id": self.recon_camera_id,
            "recon_resource_id": self.recon_resource_id,
            "initial_plan_version": self.initial_plan_version,
            "initial_coalition_version": self.initial_coalition_version,
            "initial_communication_version": self.initial_communication_version,
            "initial_track_version": self.initial_track_version,
            "start_timestamp_s": self.start_timestamp_s,
        }


@dataclass(frozen=True)
class ActiveVisionCurriculumSummary:
    """Small deterministic coverage summary; it contains no evaluator labels."""

    episode_uid: str
    seed: int
    episode_count: int
    segment_count: int
    sample_count: int
    camera_count: int
    intent_counts: tuple[tuple[str, int], ...]
    fov_mode_counts: tuple[tuple[str, int], ...]
    camera_role_counts: tuple[tuple[str, int], ...]
    ack_outcome_counts: tuple[tuple[str, int], ...]
    schema_version: str = ACTIVE_VISION_CURRICULUM_SUMMARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_CURRICULUM_SUMMARY_SCHEMA_VERSION:
            raise ValueError("active-vision curriculum summary schema mismatch")
        object.__setattr__(self, "episode_uid", _portable_key(self.episode_uid, "episode_uid"))
        object.__setattr__(self, "seed", _non_negative_integer(self.seed, "seed"))
        for name in (
            "episode_count",
            "segment_count",
            "sample_count",
            "camera_count",
        ):
            object.__setattr__(self, name, _non_negative_integer(getattr(self, name), name))
        for name in (
            "intent_counts",
            "fov_mode_counts",
            "camera_role_counts",
            "ack_outcome_counts",
        ):
            object.__setattr__(self, name, _count_pairs(getattr(self, name), name))
        if self.episode_count != 1:
            raise ValueError("one curriculum build must summarize exactly one episode")
        if self.segment_count != ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT:
            raise ValueError("curriculum segment count mismatch")
        if self.sample_count != ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT:
            raise ValueError("curriculum sample count mismatch")
        if self.camera_count != len(_ROLE_ORDER):
            raise ValueError("curriculum camera count mismatch")
        for counts in (
            self.intent_counts,
            self.fov_mode_counts,
            self.camera_role_counts,
            self.ack_outcome_counts,
        ):
            if sum(count for _, count in counts) != self.sample_count:
                raise ValueError("curriculum summary counts do not match sample_count")

    def to_payload(self) -> dict[str, Any]:
        """Return a stable JSON-compatible summary payload."""

        return {
            "schema_version": self.schema_version,
            "episode_uid": self.episode_uid,
            "seed": self.seed,
            "episode_count": self.episode_count,
            "segment_count": self.segment_count,
            "sample_count": self.sample_count,
            "camera_count": self.camera_count,
            "intent_counts": dict(self.intent_counts),
            "fov_mode_counts": dict(self.fov_mode_counts),
            "camera_role_counts": dict(self.camera_role_counts),
            "ack_outcome_counts": dict(self.ack_outcome_counts),
        }

    def to_json(self) -> str:
        """Serialize the summary with canonical ordering and no non-finite values."""

        return json.dumps(
            self.to_payload(),
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class _SegmentSpec:
    role: str
    intent: ActiveVisionIntent
    expected_fov_modes: tuple[ActiveVisionFovMode, ...]
    faults: tuple[ActiveVisionCameraFault, ...]
    expected_outcomes: tuple[ActiveVisionCameraExecutionOutcome, ...]

    def __post_init__(self) -> None:
        if self.role not in _ROLE_ORDER:
            raise ValueError("unknown curriculum camera role")
        if not (
            len(self.expected_fov_modes)
            == len(self.faults)
            == len(self.expected_outcomes)
        ):
            raise ValueError("curriculum segment vectors must have equal lengths")


_SEGMENTS = (
    _SegmentSpec(
        role=_INTERCEPTOR_ROLE,
        intent=ActiveVisionIntent.HOLD,
        expected_fov_modes=(ActiveVisionFovMode.WIDE,),
        faults=(ActiveVisionCameraFault.NONE,),
        expected_outcomes=(ActiveVisionCameraExecutionOutcome.APPLIED,),
    ),
    _SegmentSpec(
        role=_RECON_ROLE,
        intent=ActiveVisionIntent.HOLD,
        expected_fov_modes=(ActiveVisionFovMode.WIDE,),
        faults=(ActiveVisionCameraFault.CAMERA_UNAVAILABLE,),
        expected_outcomes=(ActiveVisionCameraExecutionOutcome.REJECTED,),
    ),
    _SegmentSpec(
        role=_INTERCEPTOR_ROLE,
        intent=ActiveVisionIntent.OBSERVE_TARGET,
        expected_fov_modes=(
            ActiveVisionFovMode.WIDE,
            ActiveVisionFovMode.WIDE,
            ActiveVisionFovMode.ZOOM,
        ),
        faults=(
            ActiveVisionCameraFault.ACK_MISSING,
            ActiveVisionCameraFault.NONE,
            ActiveVisionCameraFault.CAMERA_BUSY,
        ),
        expected_outcomes=(
            ActiveVisionCameraExecutionOutcome.MISSING,
            ActiveVisionCameraExecutionOutcome.APPLIED,
            ActiveVisionCameraExecutionOutcome.REJECTED,
        ),
    ),
    _SegmentSpec(
        role=_RECON_ROLE,
        intent=ActiveVisionIntent.OBSERVE_TARGET,
        expected_fov_modes=(
            ActiveVisionFovMode.WIDE,
            ActiveVisionFovMode.WIDE,
            ActiveVisionFovMode.ZOOM,
        ),
        faults=(
            ActiveVisionCameraFault.NONE,
            ActiveVisionCameraFault.ACK_MISSING,
            ActiveVisionCameraFault.NONE,
        ),
        expected_outcomes=(
            ActiveVisionCameraExecutionOutcome.APPLIED,
            ActiveVisionCameraExecutionOutcome.MISSING,
            ActiveVisionCameraExecutionOutcome.APPLIED,
        ),
    ),
    _SegmentSpec(
        role=_INTERCEPTOR_ROLE,
        intent=ActiveVisionIntent.REACQUIRE,
        expected_fov_modes=(ActiveVisionFovMode.WIDE,),
        faults=(ActiveVisionCameraFault.CAMERA_UNAVAILABLE,),
        expected_outcomes=(ActiveVisionCameraExecutionOutcome.REJECTED,),
    ),
    _SegmentSpec(
        role=_RECON_ROLE,
        intent=ActiveVisionIntent.REACQUIRE,
        expected_fov_modes=(ActiveVisionFovMode.WIDE,),
        faults=(ActiveVisionCameraFault.ACK_MISSING,),
        expected_outcomes=(ActiveVisionCameraExecutionOutcome.MISSING,),
    ),
    _SegmentSpec(
        role=_INTERCEPTOR_ROLE,
        intent=ActiveVisionIntent.SEARCH_SECTOR,
        expected_fov_modes=(ActiveVisionFovMode.WIDE,),
        faults=(ActiveVisionCameraFault.CAMERA_BUSY,),
        expected_outcomes=(ActiveVisionCameraExecutionOutcome.REJECTED,),
    ),
    _SegmentSpec(
        role=_RECON_ROLE,
        intent=ActiveVisionIntent.SEARCH_SECTOR,
        expected_fov_modes=(ActiveVisionFovMode.WIDE,),
        faults=(ActiveVisionCameraFault.ACK_MISSING,),
        expected_outcomes=(ActiveVisionCameraExecutionOutcome.MISSING,),
    ),
)


def build_active_vision_curriculum_episode(
    seed: int,
    *,
    source_identity: ActiveVisionSourceIdentityV1,
    config: ActiveVisionCurriculumConfig,
) -> tuple[ActiveVisionEpisodeRecordV2, ActiveVisionCurriculumSummary]:
    """Build one fixed multi-segment online episode entirely in memory."""

    seed_value = _non_negative_integer(seed, "seed")
    if not isinstance(source_identity, ActiveVisionSourceIdentityV1):
        raise TypeError("source_identity must be ActiveVisionSourceIdentityV1")
    if not isinstance(config, ActiveVisionCurriculumConfig):
        raise TypeError("config must be ActiveVisionCurriculumConfig")
    assert_truth_free_active_vision_payload(
        {"source_identity": source_identity, "config": config}
    )

    safety_config = ActiveVisionSafetyConfigV1()
    executor = DeterministicCameraCommandExecutor(safety_config)
    feedback_by_role = {
        role: ActiveVisionCameraFeedbackV1(
            camera_state=_initial_camera_state(config, seed_value, role)
        )
        for role in _ROLE_ORDER
    }
    episode_id = f"{config.episode_id_prefix}-{seed_value}"
    samples = []
    intent_counts: Counter[str] = Counter()
    fov_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    ack_counts: Counter[str] = Counter()
    sequence_index = 0
    segment_timestamp = config.start_timestamp_s

    for segment_index, segment in enumerate(_SEGMENTS):
        policy = DeterministicLookAtScanPolicy(safety_config)
        controller = ActiveVisionControllerV1(
            rule_policy=policy,
            safety_config=safety_config,
            default_mode=ActiveVisionRuntimeMode.DISABLED,
        )
        for frame_index, expected_fov in enumerate(segment.expected_fov_modes):
            now = segment_timestamp + frame_index * _FRAME_INTERVAL_S
            plan_version = config.initial_plan_version + segment_index
            coalition_version = config.initial_coalition_version + segment_index
            communication_version = (
                config.initial_communication_version + sequence_index
            )
            snapshot, refreshed_feedback = _build_snapshot(
                seed=seed_value,
                config=config,
                role=segment.role,
                intent=segment.intent,
                sequence_index=sequence_index,
                current_timestamp=now,
                plan_version=plan_version,
                coalition_version=coalition_version,
                communication_version=communication_version,
                feedback_by_role=feedback_by_role,
            )
            camera_id = _camera_id(config, segment.role)
            decision = controller.decide(
                snapshot,
                camera_id=camera_id,
                current_timestamp=now,
                expected_plan_version=plan_version,
                expected_coalition_version=coalition_version,
                expected_communication_version=communication_version,
                requested_mode=ActiveVisionRuntimeMode.DISABLED,
            )
            action = decision.effective_action
            if action.intent is not segment.intent or action.fov_mode is not expected_fov:
                raise RuntimeError(
                    "deterministic rule policy no longer matches the curriculum segment"
                )

            sample_key = f"{episode_id}.sample.{sequence_index:03d}"
            execution = executor.execute(
                snapshot,
                action,
                refreshed_feedback,
                sample_key=sample_key,
                command_version=action.communication_version,
                execution_timestamp=now + _EXECUTION_DELAY_S,
                expected_plan_version=plan_version,
                expected_coalition_version=coalition_version,
                expected_communication_version=communication_version,
                fault=segment.faults[frame_index],
            )
            expected_outcome = segment.expected_outcomes[frame_index]
            if execution.outcome is not expected_outcome:
                raise RuntimeError("camera executor no longer matches curriculum ACK semantics")
            if execution.outcome is not ActiveVisionCameraExecutionOutcome.APPLIED:
                if execution.camera_feedback is not refreshed_feedback:
                    raise RuntimeError("rejected or missing command changed camera feedback")
            feedback_by_role[segment.role] = execution.camera_feedback

            sample = active_vision_sample_from_decision(
                sample_key=sample_key,
                observation_key=f"{episode_id}.observation.{sequence_index:03d}",
                sequence_index=sequence_index,
                camera_id=camera_id,
                snapshot=snapshot,
                decision=decision,
                camera_feedback=execution.camera_feedback,
                runtime_ack=execution.runtime_ack,
            )
            samples.append(sample)
            intent_counts[action.intent.value] += 1
            fov_counts[action.fov_mode.value] += 1
            role_counts[segment.role] += 1
            ack_counts[execution.outcome.value] += 1
            sequence_index += 1
        segment_timestamp = now + _SEGMENT_GAP_S

    record = ActiveVisionEpisodeRecordV2(
        scenario_version=config.scenario_version,
        seed=seed_value,
        episode_id=episode_id,
        source_identity=source_identity,
        samples=tuple(samples),
        synthetic_fixture=True,
    )
    summary = ActiveVisionCurriculumSummary(
        episode_uid=record.episode_uid,
        seed=seed_value,
        episode_count=1,
        segment_count=len(_SEGMENTS),
        sample_count=len(record.samples),
        camera_count=len(_ROLE_ORDER),
        intent_counts=_ordered_counts(
            intent_counts,
            ("hold", "observe_target", "reacquire", "search_sector"),
        ),
        fov_mode_counts=_ordered_counts(fov_counts, ("wide", "zoom")),
        camera_role_counts=_ordered_counts(role_counts, _ROLE_ORDER),
        ack_outcome_counts=_ordered_counts(
            ack_counts,
            ("applied", "rejected", "missing"),
        ),
    )
    _validate_fixed_coverage(summary)
    return record, summary


def _build_snapshot(
    *,
    seed: int,
    config: ActiveVisionCurriculumConfig,
    role: str,
    intent: ActiveVisionIntent,
    sequence_index: int,
    current_timestamp: float,
    plan_version: int,
    coalition_version: int,
    communication_version: int,
    feedback_by_role: dict[str, ActiveVisionCameraFeedbackV1],
) -> tuple[ActiveVisionSnapshotV1, ActiveVisionCameraFeedbackV1]:
    refreshed: dict[str, ActiveVisionCameraFeedbackV1] = {}
    for item_role in _ROLE_ORDER:
        prior = feedback_by_role[item_role]
        state = replace(
            prior.camera_state,
            state_timestamp=current_timestamp,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            slew_available=not (
                item_role == role and intent is ActiveVisionIntent.HOLD
            ),
            action_in_progress_until=None,
        )
        refreshed[item_role] = ActiveVisionCameraFeedbackV1(
            camera_state=state,
            last_accepted_command_version=prior.last_accepted_command_version,
        )

    assignments = tuple(
        ActiveVisionAssignmentReference(
            resource_id=_resource_id(config, item_role),
            camera_id=_camera_id(config, item_role),
            global_track_id=config.global_track_id,
        )
        for item_role in _ROLE_ORDER
    )
    projections: tuple[ActiveVisionProjectionEvidence, ...]
    if intent is ActiveVisionIntent.SEARCH_SECTOR:
        projections = ()
    else:
        evidence_age = (
            _REACQUIRE_EVIDENCE_AGE_S
            if intent is ActiveVisionIntent.REACQUIRE
            else _FRESH_EVIDENCE_AGE_S
        )
        measurement_timestamp = current_timestamp - evidence_age
        projections = (
            ActiveVisionProjectionEvidence(
                camera_id=_camera_id(config, role),
                global_track_id=config.global_track_id,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=measurement_timestamp + 0.02,
                yaw_error_deg=_stable_float(
                    seed,
                    f"{role}:{sequence_index}:yaw-error",
                    2.0,
                    4.5,
                ),
                pitch_error_deg=_stable_float(
                    seed,
                    f"{role}:{sequence_index}:pitch-error",
                    -2.0,
                    -0.5,
                ),
                projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
                visibility_probability=0.92,
                occlusion_fraction=0.08,
                association_confidence=0.96,
                in_fov=True,
            ),
        )
    snapshot = ActiveVisionSnapshotV1(
        snapshot_timestamp=current_timestamp,
        plan=ActiveVisionPlanReference(
            plan_version=plan_version,
            coalition_version=coalition_version,
            assignments=assignments,
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=communication_version,
            plan_version=plan_version,
            coalition_version=coalition_version,
            update_timestamp=current_timestamp - 0.02,
            healthy=True,
        ),
        tracks=(
            ActiveVisionTrackReference(
                global_track_id=config.global_track_id,
                track_version=config.initial_track_version + sequence_index,
                measurement_timestamp=current_timestamp - 0.05,
            ),
        ),
        cameras=tuple(refreshed[item].camera_state for item in _ROLE_ORDER),
        projections=projections,
    )
    return snapshot, refreshed[role]


def _initial_camera_state(
    config: ActiveVisionCurriculumConfig,
    seed: int,
    role: str,
) -> ActiveVisionCameraState:
    yaw_center = -6.0 if role == _INTERCEPTOR_ROLE else 6.0
    return ActiveVisionCameraState(
        camera_id=_camera_id(config, role),
        resource_id=_resource_id(config, role),
        state_timestamp=config.start_timestamp_s,
        yaw_deg=yaw_center + _stable_float(seed, f"{role}:initial-yaw", -1.0, 1.0),
        pitch_deg=_stable_float(seed, f"{role}:initial-pitch", -2.0, -1.0),
        yaw_rate_deg_s=0.0,
        pitch_rate_deg_s=0.0,
        yaw_limits_deg=(-90.0, 90.0),
        pitch_limits_deg=(-45.0, 30.0),
        max_yaw_rate_deg_s=80.0,
        max_pitch_rate_deg_s=60.0,
        max_slew_deg_s=90.0,
        current_fov_mode=ActiveVisionFovMode.WIDE,
    )


def _camera_id(config: ActiveVisionCurriculumConfig, role: str) -> str:
    return (
        config.interceptor_camera_id
        if role == _INTERCEPTOR_ROLE
        else config.recon_camera_id
    )


def _resource_id(config: ActiveVisionCurriculumConfig, role: str) -> str:
    return (
        config.interceptor_resource_id
        if role == _INTERCEPTOR_ROLE
        else config.recon_resource_id
    )


def _stable_float(seed: int, label: str, lower: float, upper: float) -> float:
    digest = hashlib.sha256(f"{seed}:{label}".encode("ascii")).digest()
    fraction = int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)
    return lower + (upper - lower) * fraction


def _ordered_counts(
    counts: Counter[str],
    order: tuple[str, ...],
) -> tuple[tuple[str, int], ...]:
    if set(counts) != set(order):
        raise RuntimeError("curriculum did not cover the required category set")
    return tuple((name, counts[name]) for name in order)


def _validate_fixed_coverage(summary: ActiveVisionCurriculumSummary) -> None:
    expected = {
        "intent_counts": (
            ("hold", 2),
            ("observe_target", 6),
            ("reacquire", 2),
            ("search_sector", 2),
        ),
        "fov_mode_counts": (("wide", 10), ("zoom", 2)),
        "camera_role_counts": (("interceptor", 6), ("recon", 6)),
        "ack_outcome_counts": (
            ("applied", 4),
            ("rejected", 4),
            ("missing", 4),
        ),
    }
    for name, value in expected.items():
        if getattr(summary, name) != value:
            raise RuntimeError(f"fixed curriculum coverage changed: {name}")


def _portable_key(value: Any, name: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result or _PORTABLE_KEY.fullmatch(result) is None:
        raise ValueError(f"{name} must be a non-empty portable key")
    return result


def _finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _non_negative_integer(value: Any, name: str) -> int:
    result = int(value)
    if isinstance(value, bool) or result != value or result < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _count_pairs(value: Any, name: str) -> tuple[tuple[str, int], ...]:
    pairs = tuple(value)
    keys = tuple(str(key) for key, _ in pairs)
    if not pairs or len(keys) != len(set(keys)):
        raise ValueError(f"{name} must contain unique category counts")
    normalized = tuple(
        (_portable_key(key, f"{name}.key"), _non_negative_integer(count, f"{name}.count"))
        for key, count in pairs
    )
    return normalized


__all__ = [
    "ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT",
    "ACTIVE_VISION_CURRICULUM_SCHEMA_VERSION",
    "ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT",
    "ACTIVE_VISION_CURRICULUM_SUMMARY_SCHEMA_VERSION",
    "ActiveVisionCurriculumConfig",
    "ActiveVisionCurriculumSummary",
    "build_active_vision_curriculum_episode",
]
