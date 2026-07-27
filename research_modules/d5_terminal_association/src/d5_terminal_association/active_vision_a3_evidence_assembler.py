"""Fail-closed A3 active-vision adoption and paired-window evidence.

The assembler consumes the existing D5 decision, runtime ACK, and camera
feedback contracts.  It does not define a second ACK or pose message and does
not issue commands.  Main remains responsible for routing
``CameraObservationCommand``, publishing ``runtime.camera_command_ack``, and
returning the resulting camera state.

An A3 action is considered adopted only when the learned proposal passes the
deterministic D5 projection, the matching camera command is issued, the
existing :class:`ActiveVisionRuntimeAckV1` reports a non-synthetic application,
and the existing :class:`ActiveVisionCameraFeedbackV1` proves that the same
command version and pose took effect.  A later truth-free physical observation
window and a same-key deterministic R0 window are both required before the
record can be passed to a D6 benefit audit.

No output from this module grants model, camera, assignment, failover, control,
or G1 authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .active_vision_contracts import (
    ActiveVisionActionV1,
    ActiveVisionCameraState,
    ActiveVisionDecisionV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionRuntimeMode,
    assert_truth_free_active_vision_payload,
)
from .active_vision_episode_dataset import (
    ActiveVisionCameraFeedbackV1,
    ActiveVisionRuntimeAckV1,
)
from .sparse_tracklet_graph import (
    CameraLocalTracklet,
    CenterTrackBindingDecision,
    assert_anonymous_online_payload,
)


ACTIVE_VISION_A3_TRACE_SCHEMA_VERSION = "d5.active-vision-a3-adoption-trace.v1"
ACTIVE_VISION_A3_RULE_ARM_TRACE_SCHEMA_VERSION = (
    "d5.active-vision-a3-rule-arm-trace.v1"
)
ACTIVE_VISION_A3_WINDOW_SCHEMA_VERSION = (
    "d5.active-vision-a3-physical-observation-window.v1"
)
ACTIVE_VISION_A3_AUDIT_INPUT_SCHEMA_VERSION = (
    "d5.active-vision-a3-benefit-audit-input.v1"
)
ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION = (
    "d5.active-vision-a3-pairing-disposition.v1"
)
ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION = (
    "d5.active-vision-a3-pairing-disposition.v2"
)
ACTIVE_VISION_A3_CANDIDATE_STAGE_EVIDENCE_SCHEMA_VERSION = (
    "d5.active-vision-a3-candidate-stage-evidence.v1"
)
ACTIVE_VISION_A3_POSE_LINEAGE_SCHEMA_VERSION = (
    "d5.active-vision-a3-camera-pose-lineage.v1"
)
ACTIVE_VISION_A3_BINDING_EVIDENCE_SCHEMA_VERSION = (
    "d5.active-vision-a3-binding-evidence.v1"
)
ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION = (
    "d5.active-vision-a3-anonymous-observation-frame.v1"
)
ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION = (
    "d5.active-vision-a3-anonymous-observation-frame.v2"
)
CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION = (
    "main.camera-observation-command-payload.v1"
)

RUNTIME_OBSERVED_EVIDENCE_KIND = "runtime_observed"
SYNTHETIC_FIXTURE_EVIDENCE_KIND = "synthetic_fixture"
UNAVAILABLE_EVIDENCE_KIND = "unavailable"

_EVIDENCE_KINDS = frozenset(
    {
        RUNTIME_OBSERVED_EVIDENCE_KIND,
        SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        UNAVAILABLE_EVIDENCE_KIND,
    }
)
_MODES = frozenset({"disabled", "shadow", "assist"})
_INTENTS = frozenset({"observe_target", "search_sector", "hold", "reacquire"})
_FOV_MODES = frozenset({"wide", "zoom"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_POSE_TOLERANCE_MAX_DEG = 1.0
_EPS = 1.0e-9
_TRACKLET_KEY_RE = re.compile(r"^[^/:\s]+/[^/:\s]+:[^:\s]+$")
_OBSERVATION_FRAME_TRACKLETS_OBSERVED = "tracklets_observed"
_OBSERVATION_FRAME_PROCESSED_ZERO_DETECTIONS = "processed_zero_detections"
_OBSERVATION_FRAME_STATES = frozenset(
    {
        _OBSERVATION_FRAME_TRACKLETS_OBSERVED,
        _OBSERVATION_FRAME_PROCESSED_ZERO_DETECTIONS,
    }
)
_ANONYMOUS_BINDING_STATE_MAP = MappingProxyType(
    {
        "bound": "locked",
        "ambiguous": "ambiguous",
        "unbound": "reacquire",
    }
)
_PAIRING_KEY_OR_CONFIGURATION_ERROR_CODES = frozenset(
    {
        "candidate_trace_identity_mismatch",
        "candidate_trace_hash_mismatch",
        "candidate_log_hash_mismatch",
        "same_key_r0_identity_mismatch",
        "same_key_r0_duration_mismatch",
    }
)
_A3_ADOPTION_BLOCKER_CODES = frozenset(
    {
        "policy_not_evaluated",
        "command_not_proposed",
        "deterministic_projection_not_accepted",
        "model_command_not_selected",
        "model_command_not_issued",
        "runtime_ack_missing",
        "runtime_ack_simulated_or_nonruntime",
        "runtime_ack_not_applied",
        "camera_feedback_missing",
        "camera_feedback_simulated_or_nonruntime",
        "camera_pose_lineage_missing",
        "camera_pose_lineage_simulated_or_nonruntime",
        "pose_not_applied",
        "online_truth_use_detected",
        "global_track_id_rewrite_detected",
    }
)

_COMMAND_FIELDS = {
    "payload_version",
    "camera_id",
    "resource_id",
    "issued_timestamp",
    "expires_timestamp",
    "plan_version",
    "coalition_version",
    "communication_version",
    "intent",
    "aim_point_ned",
    "horizontal_fov_deg",
    "fov_mode",
    "target_global_track_id",
    "requested_mode",
    "effective_mode",
    "reason",
}


class ActiveVisionA3ProjectionStatus(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ActiveVisionA3CommandSource(str, Enum):
    MODEL_ASSIST = "model_assist"
    DETERMINISTIC_RULE = "deterministic_rule"


class ActiveVisionA3WindowArm(str, Enum):
    A3 = "A3"
    R0 = "R0"


class ActiveVisionA3PairingDispositionCode(str, Enum):
    PAIRABLE = "pairable"
    MODEL_ACTION_NOT_ADOPTED = "model_action_not_adopted"
    CANDIDATE_PHYSICAL_WINDOW_MISSING = "candidate_physical_window_missing"
    SAME_KEY_R0_WINDOW_MISSING = "same_key_r0_window_missing"
    SAME_KEY_R0_DUPLICATE_OR_AMBIGUOUS = (
        "same_key_r0_duplicate_or_ambiguous"
    )
    PAIRING_KEY_OR_CONFIGURATION_MISMATCH = (
        "pairing_key_or_configuration_mismatch"
    )
    CANDIDATE_PHYSICAL_EVIDENCE_INCOMPLETE = (
        "candidate_physical_evidence_incomplete"
    )
    R0_PHYSICAL_EVIDENCE_INCOMPLETE = "r0_physical_evidence_incomplete"
    BENEFIT_OUTCOME_UNAVAILABLE = "benefit_outcome_unavailable"
    EVIDENCE_CONTRACT_INVALID = "evidence_contract_invalid"


class ActiveVisionA3CandidatePhysicalWindowStatus(str, Enum):
    UNKNOWN = "unknown"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class ActiveVisionA3CandidateStageReasonCode(str, Enum):
    RUNTIME_ACK_MISSING = "candidate_runtime_ack_missing"
    RUNTIME_CONFIRMATION_MISSING = "candidate_runtime_confirmation_missing"
    COMMAND_WINDOW_EXPIRED = "candidate_command_window_expired"
    COMMAND_TIMING_MISMATCH = "candidate_command_timing_mismatch"
    CAMERA_FEEDBACK_MISSING = "candidate_camera_feedback_missing"
    ANONYMOUS_OBSERVATION_MISSING = "candidate_anonymous_observation_missing"
    ANONYMOUS_OBSERVATION_INCOMPLETE = (
        "candidate_anonymous_observation_incomplete"
    )
    PHYSICAL_WINDOW_CONFIRMED_MISSING = (
        "candidate_physical_window_confirmed_missing"
    )
    PHYSICAL_WINDOW_INCOMPLETE = "candidate_physical_window_incomplete"


class ActiveVisionA3EvidenceError(ValueError):
    """Stable fail-closed rejection from A3 assembly or strict validation."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class ActiveVisionA3CameraPoseLineage:
    """Versioned runtime camera state used to prove command application."""

    camera_id: str
    resource_id: str
    state_timestamp: float
    yaw_deg: float
    pitch_deg: float
    horizontal_fov_deg: float
    fov_mode: str
    last_plan_version: int
    last_coalition_version: int
    last_communication_version: int
    evidence_kind: str
    source_sequence: int | None = None
    schema_version: str = ACTIVE_VISION_A3_POSE_LINEAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_A3_POSE_LINEAGE_SCHEMA_VERSION:
            _fail("pose_lineage_schema_mismatch", "unsupported pose lineage schema")
        for name in ("camera_id", "resource_id"):
            object.__setattr__(
                self,
                name,
                _token(getattr(self, name), f"pose_lineage.{name}"),
            )
        for name in (
            "state_timestamp",
            "yaw_deg",
            "pitch_deg",
            "horizontal_fov_deg",
        ):
            object.__setattr__(
                self,
                name,
                _finite(getattr(self, name), f"pose_lineage.{name}"),
            )
        if not -180.0 <= self.yaw_deg <= 180.0:
            _fail("pose_lineage_yaw_invalid", "runtime yaw is outside [-180, 180]")
        if not -90.0 <= self.pitch_deg <= 90.0:
            _fail("pose_lineage_pitch_invalid", "runtime pitch is outside [-90, 90]")
        if not 1.0 < self.horizontal_fov_deg < 179.0:
            _fail("pose_lineage_fov_invalid", "runtime FOV is outside (1, 179)")
        object.__setattr__(
            self,
            "fov_mode",
            _choice(self.fov_mode, _FOV_MODES, "pose_lineage.fov_mode"),
        )
        for name in (
            "last_plan_version",
            "last_coalition_version",
            "last_communication_version",
        ):
            object.__setattr__(
                self,
                name,
                _non_negative_int(getattr(self, name), f"pose_lineage.{name}"),
            )
        evidence_kind = _choice(
            self.evidence_kind,
            frozenset(
                {
                    RUNTIME_OBSERVED_EVIDENCE_KIND,
                    SYNTHETIC_FIXTURE_EVIDENCE_KIND,
                }
            ),
            "pose_lineage.evidence_kind",
        )
        object.__setattr__(self, "evidence_kind", evidence_kind)
        source_sequence = (
            None
            if self.source_sequence is None
            else _non_negative_int(
                self.source_sequence,
                "pose_lineage.source_sequence",
            )
        )
        object.__setattr__(self, "source_sequence", source_sequence)
        _assert_truth_free(self)

    @property
    def content_sha256(self) -> str:
        return _sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "state_timestamp": self.state_timestamp,
            "yaw_deg": self.yaw_deg,
            "pitch_deg": self.pitch_deg,
            "horizontal_fov_deg": self.horizontal_fov_deg,
            "fov_mode": self.fov_mode,
            "last_plan_version": self.last_plan_version,
            "last_coalition_version": self.last_coalition_version,
            "last_communication_version": self.last_communication_version,
            "evidence_kind": self.evidence_kind,
            "source_sequence": self.source_sequence,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3CameraPoseLineage:
        _assert_truth_free(payload)
        _expect_fields(
            payload,
            {
                "schema_version",
                "camera_id",
                "resource_id",
                "state_timestamp",
                "yaw_deg",
                "pitch_deg",
                "horizontal_fov_deg",
                "fov_mode",
                "last_plan_version",
                "last_coalition_version",
                "last_communication_version",
                "evidence_kind",
                "source_sequence",
                "content_sha256",
            },
            "pose_lineage",
        )
        item = cls(
            schema_version=payload["schema_version"],
            camera_id=payload["camera_id"],
            resource_id=payload["resource_id"],
            state_timestamp=payload["state_timestamp"],
            yaw_deg=payload["yaw_deg"],
            pitch_deg=payload["pitch_deg"],
            horizontal_fov_deg=payload["horizontal_fov_deg"],
            fov_mode=payload["fov_mode"],
            last_plan_version=payload["last_plan_version"],
            last_coalition_version=payload["last_coalition_version"],
            last_communication_version=payload["last_communication_version"],
            evidence_kind=payload["evidence_kind"],
            source_sequence=payload["source_sequence"],
        )
        if item.to_dict() != dict(payload):
            _fail(
                "pose_lineage_recomputation_mismatch",
                "stored runtime pose lineage or content hash differs from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3BindingEvidence:
    """Anonymous local-cluster state with a read-only center-track reference."""

    cluster_key: str
    global_track_id: str | None
    decision_state: str
    supporting_tracklet_keys: tuple[str, ...]
    schema_version: str = ACTIVE_VISION_A3_BINDING_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_A3_BINDING_EVIDENCE_SCHEMA_VERSION:
            _fail("binding_schema_mismatch", "unsupported A3 binding schema")
        object.__setattr__(
            self,
            "cluster_key",
            _token(self.cluster_key, "binding.cluster_key"),
        )
        object.__setattr__(
            self,
            "global_track_id",
            _optional_token(self.global_track_id, "binding.global_track_id"),
        )
        state = _choice(
            self.decision_state,
            frozenset(_ANONYMOUS_BINDING_STATE_MAP),
            "binding.decision_state",
        )
        keys = tuple(
            _tracklet_key(value, "binding.supporting_tracklet_key")
            for value in self.supporting_tracklet_keys
        )
        if not keys or len(keys) != len(set(keys)):
            _fail(
                "binding_tracklet_keys_invalid",
                "supporting tracklet keys must be non-empty and unique",
            )
        if state == "bound" and self.global_track_id is None:
            _fail(
                "binding_global_reference_missing",
                "bound state requires a center-owned global track reference",
            )
        if state != "bound" and self.global_track_id is not None:
            _fail(
                "binding_global_reference_invalid",
                "ambiguous or unbound state cannot assert a global track reference",
            )
        object.__setattr__(self, "decision_state", state)
        object.__setattr__(self, "supporting_tracklet_keys", keys)
        _assert_truth_free(self)
        _assert_anonymous(
            {
                "cluster_key": self.cluster_key,
                "supporting_tracklet_keys": self.supporting_tracklet_keys,
            }
        )

    @property
    def terminal_state(self) -> str:
        return map_active_vision_binding_state(self.decision_state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "cluster_key": self.cluster_key,
            "global_track_id": self.global_track_id,
            "decision_state": self.decision_state,
            "terminal_state": self.terminal_state,
            "supporting_tracklet_keys": list(self.supporting_tracklet_keys),
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3BindingEvidence:
        _assert_truth_free(payload)
        _expect_fields(
            payload,
            {
                "schema_version",
                "cluster_key",
                "global_track_id",
                "decision_state",
                "terminal_state",
                "supporting_tracklet_keys",
            },
            "binding",
        )
        item = cls(
            schema_version=payload["schema_version"],
            cluster_key=payload["cluster_key"],
            global_track_id=payload["global_track_id"],
            decision_state=payload["decision_state"],
            supporting_tracklet_keys=tuple(payload["supporting_tracklet_keys"]),
        )
        if item.to_dict() != dict(payload):
            _fail(
                "binding_recomputation_mismatch",
                "stored terminal state differs from D5 mapping",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3AnonymousObservationFrame:
    """One post-command anonymous visual frame and its local binding states."""

    frame_key: str
    camera_id: str
    resource_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    plan_version: int
    coalition_version: int
    communication_version: int
    target_global_track_id: str | None
    observed_tracklet_keys: tuple[str, ...]
    bindings: tuple[ActiveVisionA3BindingEvidence, ...]
    evidence_kind: str
    source_sequence: int | None = None
    frame_observation_state: str = _OBSERVATION_FRAME_TRACKLETS_OBSERVED
    center_global_track_ids: tuple[str, ...] = ()
    schema_version: str = ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        schema_version = _token(
            self.schema_version,
            "observation_frame.schema_version",
        )
        if schema_version not in {
            ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION,
            ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION,
        }:
            _fail("observation_frame_schema_mismatch", "unsupported observation frame schema")
        object.__setattr__(self, "schema_version", schema_version)
        for name in ("frame_key", "camera_id", "resource_id"):
            object.__setattr__(
                self,
                name,
                _token(getattr(self, name), f"observation_frame.{name}"),
            )
        measurement = _finite(
            self.measurement_timestamp,
            "observation_frame.measurement_timestamp",
        )
        arrival = _finite(
            self.arrival_timestamp,
            "observation_frame.arrival_timestamp",
        )
        if arrival + _EPS < measurement:
            _fail(
                "observation_frame_time_invalid",
                "arrival timestamp precedes measurement timestamp",
            )
        object.__setattr__(self, "measurement_timestamp", measurement)
        object.__setattr__(self, "arrival_timestamp", arrival)
        for name in ("plan_version", "coalition_version", "communication_version"):
            object.__setattr__(
                self,
                name,
                _non_negative_int(getattr(self, name), f"observation_frame.{name}"),
            )
        object.__setattr__(
            self,
            "target_global_track_id",
            _optional_token(
                self.target_global_track_id,
                "observation_frame.target_global_track_id",
            ),
        )
        keys = tuple(
            _tracklet_key(value, "observation_frame.observed_tracklet_key")
            for value in self.observed_tracklet_keys
        )
        if len(keys) != len(set(keys)):
            _fail(
                "observation_frame_tracklets_invalid",
                "observed tracklet keys must be unique",
            )
        expected_prefix = f"{self.resource_id}/{self.camera_id}:"
        if any(not key.startswith(expected_prefix) for key in keys):
            _fail(
                "observation_frame_membership_mismatch",
                "observed tracklet key does not belong to frame camera/resource",
            )
        bindings = tuple(self.bindings)
        if any(not isinstance(item, ActiveVisionA3BindingEvidence) for item in bindings):
            _fail(
                "observation_frame_binding_type_invalid",
                "frame bindings must use ActiveVisionA3BindingEvidence",
            )
        if len({item.cluster_key for item in bindings}) != len(bindings):
            _fail(
                "observation_frame_bindings_invalid",
                "frame binding cluster keys must be unique",
            )
        try:
            raw_center_ids = tuple(self.center_global_track_ids)
        except TypeError:
            _fail(
                "observation_frame_center_tracks_invalid",
                "center-owned global track IDs must be an iterable",
            )
        if schema_version == ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION:
            if (
                self.frame_observation_state
                != _OBSERVATION_FRAME_TRACKLETS_OBSERVED
                or raw_center_ids
            ):
                _fail(
                    "observation_frame_v1_extension_forbidden",
                    "historical v1 frames cannot carry v2 observation semantics",
                )
            if not keys:
                _fail(
                    "observation_frame_tracklets_invalid",
                    "historical v1 frames require at least one observed tracklet",
                )
            frame_observation_state = _OBSERVATION_FRAME_TRACKLETS_OBSERVED
            center_ids: tuple[str, ...] = ()
        else:
            frame_observation_state = _choice(
                self.frame_observation_state,
                _OBSERVATION_FRAME_STATES,
                "observation_frame.frame_observation_state",
            )
            normalized_center_ids = tuple(
                _token(value, "observation_frame.center_global_track_id")
                for value in raw_center_ids
            )
            if len(normalized_center_ids) != len(set(normalized_center_ids)):
                _fail(
                    "observation_frame_center_tracks_invalid",
                    "center-owned global track IDs must be unique",
                )
            center_ids = tuple(sorted(normalized_center_ids))
            if (
                frame_observation_state
                == _OBSERVATION_FRAME_PROCESSED_ZERO_DETECTIONS
            ):
                if keys or bindings:
                    _fail(
                        "observation_frame_zero_detection_payload_invalid",
                        "processed zero-detection frames cannot contain tracklets or bindings",
                    )
            elif not keys:
                _fail(
                    "observation_frame_tracklets_invalid",
                    "tracklets-observed v2 frames require at least one observed tracklet",
                )
            if (
                self.target_global_track_id is not None
                and self.target_global_track_id not in center_ids
            ):
                _fail(
                    "observation_frame_target_not_center_owned",
                    "target reference is absent from center-owned track candidates",
                )
            if any(
                item.global_track_id is not None
                and item.global_track_id not in center_ids
                for item in bindings
            ):
                _fail(
                    "binding_global_reference_not_center_owned",
                    "binding references a global track absent from center candidates",
                )
        object.__setattr__(self, "observed_tracklet_keys", keys)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(
            self,
            "frame_observation_state",
            frame_observation_state,
        )
        object.__setattr__(self, "center_global_track_ids", center_ids)
        object.__setattr__(
            self,
            "evidence_kind",
            _choice(
                self.evidence_kind,
                frozenset(
                    {
                        RUNTIME_OBSERVED_EVIDENCE_KIND,
                        SYNTHETIC_FIXTURE_EVIDENCE_KIND,
                    }
                ),
                "observation_frame.evidence_kind",
            ),
        )
        source_sequence = (
            None
            if self.source_sequence is None
            else _non_negative_int(
                self.source_sequence,
                "observation_frame.source_sequence",
            )
        )
        if (
            schema_version
            == ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION
            and source_sequence is None
        ):
            _fail(
                "observation_frame_source_sequence_missing",
                "v2 observation frames require an explicit source sequence",
            )
        object.__setattr__(self, "source_sequence", source_sequence)
        _assert_truth_free(self)
        _assert_anonymous(
            {
                "frame_key": self.frame_key,
                "camera_id": self.camera_id,
                "resource_id": self.resource_id,
                "observed_tracklet_keys": self.observed_tracklet_keys,
                "binding_local_support": [
                    {
                        "cluster_key": item.cluster_key,
                        "supporting_tracklet_keys": item.supporting_tracklet_keys,
                    }
                    for item in self.bindings
                ],
            }
        )

    @property
    def relevant_bindings(self) -> tuple[ActiveVisionA3BindingEvidence, ...]:
        observed = set(self.observed_tracklet_keys)
        return tuple(
            item
            for item in self.bindings
            if observed.intersection(item.supporting_tracklet_keys)
        )

    @property
    def association_state(self) -> str | None:
        if (
            self.frame_observation_state
            == _OBSERVATION_FRAME_PROCESSED_ZERO_DETECTIONS
        ):
            return (
                "reacquire"
                if self.target_global_track_id is not None
                else None
            )
        relevant = self.relevant_bindings
        if not relevant:
            return None
        if self.target_global_track_id is not None and any(
            item.decision_state == "bound"
            and item.global_track_id == self.target_global_track_id
            for item in relevant
        ):
            return "locked"
        if any(item.decision_state == "ambiguous" for item in relevant):
            return "ambiguous"
        return "reacquire"

    @property
    def assigned_reference_visible(self) -> bool | None:
        state = self.association_state
        if state is None or self.target_global_track_id is None:
            return None
        return state == "locked"

    @property
    def content_sha256(self) -> str:
        return _sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "frame_key": self.frame_key,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "plan_version": self.plan_version,
            "coalition_version": self.coalition_version,
            "communication_version": self.communication_version,
            "target_global_track_id": self.target_global_track_id,
            "observed_tracklet_keys": list(self.observed_tracklet_keys),
            "bindings": [item.to_dict() for item in self.bindings],
            "association_state": self.association_state,
            "assigned_reference_visible": self.assigned_reference_visible,
            "evidence_kind": self.evidence_kind,
            "source_sequence": self.source_sequence,
        }
        if (
            self.schema_version
            == ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION
        ):
            payload["frame_observation_state"] = self.frame_observation_state
            payload["center_global_track_ids"] = list(
                self.center_global_track_ids
            )
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3AnonymousObservationFrame:
        _assert_truth_free(payload)
        schema_version = payload.get("schema_version")
        if schema_version == ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION:
            version_fields: set[str] = set()
        elif (
            schema_version
            == ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION
        ):
            version_fields = {
                "frame_observation_state",
                "center_global_track_ids",
            }
        else:
            _fail(
                "observation_frame_schema_mismatch",
                "unsupported observation frame schema",
            )
        _expect_fields(
            payload,
            {
                "schema_version",
                "frame_key",
                "camera_id",
                "resource_id",
                "measurement_timestamp",
                "arrival_timestamp",
                "plan_version",
                "coalition_version",
                "communication_version",
                "target_global_track_id",
                "observed_tracklet_keys",
                "bindings",
                "association_state",
                "assigned_reference_visible",
                "evidence_kind",
                "source_sequence",
                "content_sha256",
            }
            | version_fields,
            "observation_frame",
        )
        item = cls(
            schema_version=payload["schema_version"],
            frame_key=payload["frame_key"],
            camera_id=payload["camera_id"],
            resource_id=payload["resource_id"],
            measurement_timestamp=payload["measurement_timestamp"],
            arrival_timestamp=payload["arrival_timestamp"],
            plan_version=payload["plan_version"],
            coalition_version=payload["coalition_version"],
            communication_version=payload["communication_version"],
            target_global_track_id=payload["target_global_track_id"],
            observed_tracklet_keys=tuple(payload["observed_tracklet_keys"]),
            bindings=tuple(
                ActiveVisionA3BindingEvidence.from_mapping(
                    _mapping(binding, "observation_frame.binding")
                )
                for binding in payload["bindings"]
            ),
            evidence_kind=payload["evidence_kind"],
            source_sequence=payload["source_sequence"],
            frame_observation_state=payload.get(
                "frame_observation_state",
                _OBSERVATION_FRAME_TRACKLETS_OBSERVED,
            ),
            center_global_track_ids=tuple(
                payload.get("center_global_track_ids", ())
            ),
        )
        if item.to_dict() != dict(payload):
            _fail(
                "observation_frame_recomputation_mismatch",
                "stored anonymous frame outcome or content hash differs from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3OutcomeEvidence:
    """Truth-free association and assigned-reference coverage after a command."""

    association_outcome_available: bool
    coverage_outcome_available: bool
    observation_frame_count: int
    association_evaluable_frame_count: int | None
    association_locked_count: int | None
    association_ambiguous_count: int | None
    association_hold_count: int | None
    association_reacquire_count: int | None
    assigned_reference_count: int | None
    visible_assigned_reference_count: int | None

    def __post_init__(self) -> None:
        association_available = _strict_bool(
            self.association_outcome_available,
            "outcome.association_outcome_available",
        )
        coverage_available = _strict_bool(
            self.coverage_outcome_available,
            "outcome.coverage_outcome_available",
        )
        frame_count = _non_negative_int(
            self.observation_frame_count,
            "outcome.observation_frame_count",
        )
        if frame_count < 1:
            _fail("physical_window_empty", "physical observation window has no frames")

        association_names = (
            "association_evaluable_frame_count",
            "association_locked_count",
            "association_ambiguous_count",
            "association_hold_count",
            "association_reacquire_count",
        )
        association_values = {
            name: _optional_non_negative_int(
                getattr(self, name),
                f"outcome.{name}",
            )
            for name in association_names
        }
        coverage_names = (
            "assigned_reference_count",
            "visible_assigned_reference_count",
        )
        coverage_values = {
            name: _optional_non_negative_int(
                getattr(self, name),
                f"outcome.{name}",
            )
            for name in coverage_names
        }
        if association_available:
            if any(value is None for value in association_values.values()):
                _fail(
                    "association_outcome_incomplete",
                    "available association outcome requires all association counts",
                )
            if int(association_values["association_evaluable_frame_count"]) < 1:
                _fail(
                    "association_outcome_empty",
                    "association outcome has no evaluable frame",
                )
        elif any(value is not None for value in association_values.values()):
            _fail(
                "association_outcome_state_invalid",
                "unavailable association outcome cannot contain counts",
            )
        if coverage_available:
            if any(value is None for value in coverage_values.values()):
                _fail(
                    "coverage_outcome_incomplete",
                    "available coverage outcome requires both reference counts",
                )
            assigned = int(coverage_values["assigned_reference_count"])
            visible = int(coverage_values["visible_assigned_reference_count"])
            if assigned < 1 or visible > assigned:
                _fail(
                    "coverage_outcome_invalid",
                    "coverage requires 0 <= visible <= assigned and assigned > 0",
                )
        elif any(value is not None for value in coverage_values.values()):
            _fail(
                "coverage_outcome_state_invalid",
                "unavailable coverage outcome cannot contain counts",
            )
        object.__setattr__(
            self,
            "association_outcome_available",
            association_available,
        )
        object.__setattr__(self, "coverage_outcome_available", coverage_available)
        object.__setattr__(self, "observation_frame_count", frame_count)
        for name, value in {**association_values, **coverage_values}.items():
            object.__setattr__(self, name, value)

    @property
    def benefit_outcome_available(self) -> bool:
        return self.association_outcome_available and self.coverage_outcome_available

    @property
    def coverage_fraction(self) -> float | None:
        if not self.coverage_outcome_available:
            return None
        return float(self.visible_assigned_reference_count) / float(
            self.assigned_reference_count
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "association_outcome_available": self.association_outcome_available,
            "coverage_outcome_available": self.coverage_outcome_available,
            "observation_frame_count": self.observation_frame_count,
            "association_evaluable_frame_count": self.association_evaluable_frame_count,
            "association_locked_count": self.association_locked_count,
            "association_ambiguous_count": self.association_ambiguous_count,
            "association_hold_count": self.association_hold_count,
            "association_reacquire_count": self.association_reacquire_count,
            "assigned_reference_count": self.assigned_reference_count,
            "visible_assigned_reference_count": self.visible_assigned_reference_count,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ActiveVisionA3OutcomeEvidence:
        _expect_fields(
            payload,
            {
                "association_outcome_available",
                "coverage_outcome_available",
                "observation_frame_count",
                "association_evaluable_frame_count",
                "association_locked_count",
                "association_ambiguous_count",
                "association_hold_count",
                "association_reacquire_count",
                "assigned_reference_count",
                "visible_assigned_reference_count",
            },
            "outcome",
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True)
class ActiveVisionA3AdoptionTrace:
    """One complete policy-to-camera-feedback trace using existing D5 DTOs."""

    comparison_key: str
    scenario_id: str
    scale: int
    seed: int
    window_index: int
    sample_key: str
    camera_id: str
    resource_id: str
    pairing_context_sha256: str
    source_event_log_sha256: str
    policy_evaluated: bool
    policy_evaluated_timestamp: float | None
    model_fingerprint: str
    bundle_manifest_sha256: str
    bundle_weights_sha256: str
    implementation_sha256: str
    source_git_commit: str
    decision: ActiveVisionDecisionV1
    pre_command_camera_state: ActiveVisionCameraState
    issued_command_payload: Mapping[str, Any] | None
    runtime_ack: ActiveVisionRuntimeAckV1 | None
    camera_feedback: ActiveVisionCameraFeedbackV1 | None
    camera_pose_lineage: ActiveVisionA3CameraPoseLineage | None
    runtime_ack_evidence_kind: str
    camera_feedback_evidence_kind: str
    synthetic_fixture: bool
    pose_tolerance_deg: float = 0.25
    online_truth_use_count: int = 0
    global_track_id_rewrite_count: int = 0
    schema_version: str = ACTIVE_VISION_A3_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_A3_TRACE_SCHEMA_VERSION:
            _fail("trace_schema_mismatch", "unsupported A3 adoption trace schema")
        for name in (
            "comparison_key",
            "scenario_id",
            "sample_key",
            "camera_id",
            "resource_id",
        ):
            object.__setattr__(self, name, _token(getattr(self, name), f"trace.{name}"))
        for name in ("pairing_context_sha256", "source_event_log_sha256"):
            object.__setattr__(
                self,
                name,
                _digest(getattr(self, name), f"trace.{name}"),
            )
        for name in (
            "scale",
            "seed",
            "window_index",
            "online_truth_use_count",
            "global_track_id_rewrite_count",
        ):
            object.__setattr__(
                self,
                name,
                _non_negative_int(getattr(self, name), f"trace.{name}"),
            )
        if self.scale < 1:
            _fail("trace_scale_invalid", "scale must be at least one")
        evaluated = _strict_bool(self.policy_evaluated, "trace.policy_evaluated")
        evaluated_at = _optional_finite(
            self.policy_evaluated_timestamp,
            "trace.policy_evaluated_timestamp",
        )
        if evaluated != (evaluated_at is not None):
            _fail(
                "policy_evaluation_evidence_incomplete",
                "policy evaluation flag and timestamp must be jointly available",
            )
        object.__setattr__(self, "policy_evaluated", evaluated)
        object.__setattr__(self, "policy_evaluated_timestamp", evaluated_at)
        object.__setattr__(
            self,
            "model_fingerprint",
            _token(self.model_fingerprint, "trace.model_fingerprint"),
        )
        for name in (
            "bundle_manifest_sha256",
            "bundle_weights_sha256",
            "implementation_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _digest(getattr(self, name), f"trace.{name}"),
            )
        commit = str(self.source_git_commit).strip().lower()
        if _GIT_COMMIT_RE.fullmatch(commit) is None:
            _fail(
                "source_git_commit_invalid",
                "A3 trace source commit must be a full Git object ID",
            )
        object.__setattr__(self, "source_git_commit", commit)

        if not isinstance(self.decision, ActiveVisionDecisionV1):
            _fail("decision_type_invalid", "trace decision must use ActiveVisionDecisionV1")
        _validate_decision(self.decision)
        if (
            self.policy_evaluated
            and self.decision.model_fingerprint != self.model_fingerprint
        ):
            _fail(
                "policy_fingerprint_mismatch",
                "evaluated decision and frozen model fingerprint differ",
            )
        if not isinstance(self.pre_command_camera_state, ActiveVisionCameraState):
            _fail(
                "camera_state_type_invalid",
                "pre-command state must use ActiveVisionCameraState",
            )
        if (
            self.pre_command_camera_state.camera_id != self.camera_id
            or self.pre_command_camera_state.resource_id != self.resource_id
            or self.decision.effective_action.camera_id != self.camera_id
        ):
            _fail(
                "trace_camera_membership_mismatch",
                "decision, camera state, camera ID, or resource ID disagree",
            )

        command_payload = self.issued_command_payload
        if command_payload is not None:
            command_payload = _validated_command_payload(command_payload)
            _validate_command_against_action(
                command_payload,
                action=self.decision.effective_action,
                requested_mode=self.decision.requested_mode,
                effective_mode=self.decision.effective_mode,
                pre_camera=self.pre_command_camera_state,
                resource_id=self.resource_id,
            )
            command_payload = MappingProxyType(command_payload)
        object.__setattr__(self, "issued_command_payload", command_payload)

        if self.runtime_ack is not None and not isinstance(
            self.runtime_ack,
            ActiveVisionRuntimeAckV1,
        ):
            _fail("runtime_ack_type_invalid", "trace ACK must use ActiveVisionRuntimeAckV1")
        if self.camera_feedback is not None and not isinstance(
            self.camera_feedback,
            ActiveVisionCameraFeedbackV1,
        ):
            _fail(
                "camera_feedback_type_invalid",
                "trace feedback must use ActiveVisionCameraFeedbackV1",
            )
        if self.camera_pose_lineage is not None and not isinstance(
            self.camera_pose_lineage,
            ActiveVisionA3CameraPoseLineage,
        ):
            _fail(
                "camera_pose_lineage_type_invalid",
                "trace pose lineage must use ActiveVisionA3CameraPoseLineage",
            )
        ack_kind = _choice(
            self.runtime_ack_evidence_kind,
            _EVIDENCE_KINDS,
            "trace.runtime_ack_evidence_kind",
        )
        feedback_kind = _choice(
            self.camera_feedback_evidence_kind,
            _EVIDENCE_KINDS,
            "trace.camera_feedback_evidence_kind",
        )
        synthetic = _strict_bool(self.synthetic_fixture, "trace.synthetic_fixture")
        _validate_optional_evidence_kind(self.runtime_ack, ack_kind, "runtime_ack")
        _validate_optional_evidence_kind(
            self.camera_feedback,
            feedback_kind,
            "camera_feedback",
        )
        if self.camera_pose_lineage is not None:
            _validate_pose_lineage_against_feedback(
                self.camera_pose_lineage,
                self.camera_feedback,
            )
        contains_synthetic = (
            ack_kind == SYNTHETIC_FIXTURE_EVIDENCE_KIND
            or feedback_kind == SYNTHETIC_FIXTURE_EVIDENCE_KIND
            or (
                self.camera_pose_lineage is not None
                and self.camera_pose_lineage.evidence_kind
                == SYNTHETIC_FIXTURE_EVIDENCE_KIND
            )
        )
        if synthetic != contains_synthetic:
            _fail(
                "trace_synthetic_state_invalid",
                "synthetic flag must exactly match synthetic ACK/feedback provenance",
            )
        object.__setattr__(self, "runtime_ack_evidence_kind", ack_kind)
        object.__setattr__(self, "camera_feedback_evidence_kind", feedback_kind)
        object.__setattr__(self, "synthetic_fixture", synthetic)

        tolerance = _finite(self.pose_tolerance_deg, "trace.pose_tolerance_deg")
        if not 0.0 < tolerance <= _POSE_TOLERANCE_MAX_DEG:
            _fail(
                "pose_tolerance_invalid",
                f"pose tolerance must be within (0, {_POSE_TOLERANCE_MAX_DEG}] degrees",
            )
        object.__setattr__(self, "pose_tolerance_deg", tolerance)
        _validate_trace_runtime_chain(self)
        _assert_truth_free(self)

    @property
    def target_global_track_id(self) -> str | None:
        return self.decision.effective_action.target_global_track_id

    @property
    def command_proposed(self) -> bool:
        return self.decision.requested_action is not None

    @property
    def deterministic_projection_status(self) -> ActiveVisionA3ProjectionStatus:
        if self.decision.requested_action is None:
            return ActiveVisionA3ProjectionStatus.NOT_EVALUATED
        if self.decision.fallback_reason is None:
            return ActiveVisionA3ProjectionStatus.ACCEPTED
        return ActiveVisionA3ProjectionStatus.REJECTED

    @property
    def command_issued(self) -> bool:
        return self.issued_command_payload is not None

    @property
    def command_source(self) -> ActiveVisionA3CommandSource | None:
        if not self.command_issued:
            return None
        if (
            self.decision.effective_mode is ActiveVisionRuntimeMode.ASSIST
            and self.decision.requested_action is not None
            and _action_sha256(self.decision.requested_action)
            == _action_sha256(self.decision.effective_action)
        ):
            return ActiveVisionA3CommandSource.MODEL_ASSIST
        return ActiveVisionA3CommandSource.DETERMINISTIC_RULE

    @property
    def runtime_ack_applied(self) -> bool:
        ack = self.runtime_ack
        return bool(
            ack is not None
            and ack.accepted
            and ack.status_code in {"accepted", "applied"}
            and self.runtime_ack_evidence_kind == RUNTIME_OBSERVED_EVIDENCE_KIND
            and not self.synthetic_fixture
        )

    @property
    def pose_applied(self) -> bool:
        return _pose_applied(
            action=self.decision.effective_action,
            pre_camera=self.pre_command_camera_state,
            runtime_ack=self.runtime_ack,
            feedback=self.camera_feedback,
            pose_lineage=self.camera_pose_lineage,
            command=self.issued_command_payload,
            ack_kind=self.runtime_ack_evidence_kind,
            feedback_kind=self.camera_feedback_evidence_kind,
            synthetic_fixture=self.synthetic_fixture,
            tolerance_deg=self.pose_tolerance_deg,
        )

    @property
    def layer_status(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "policy_evaluated": self.policy_evaluated,
                "command_proposed": self.command_proposed,
                "deterministic_projection_status": (
                    self.deterministic_projection_status.value
                ),
                "command_issued": self.command_issued,
                "runtime_ack_received": self.runtime_ack is not None,
                "runtime_ack_applied": self.runtime_ack_applied,
                "camera_feedback_received": self.camera_feedback is not None,
                "camera_pose_lineage_received": (
                    self.camera_pose_lineage is not None
                ),
                "pose_applied": self.pose_applied,
            }
        )

    @property
    def adoption_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if not self.policy_evaluated:
            blockers.append("policy_not_evaluated")
        if not self.command_proposed:
            blockers.append("command_not_proposed")
        if self.deterministic_projection_status is not ActiveVisionA3ProjectionStatus.ACCEPTED:
            blockers.append("deterministic_projection_not_accepted")
        if self.command_source is not ActiveVisionA3CommandSource.MODEL_ASSIST:
            blockers.append("model_command_not_selected")
        if not self.command_issued:
            blockers.append("model_command_not_issued")
        if self.runtime_ack is None:
            blockers.append("runtime_ack_missing")
        elif self.runtime_ack_evidence_kind != RUNTIME_OBSERVED_EVIDENCE_KIND:
            blockers.append("runtime_ack_simulated_or_nonruntime")
        elif not self.runtime_ack_applied:
            blockers.append("runtime_ack_not_applied")
        if self.camera_feedback is None:
            blockers.append("camera_feedback_missing")
        elif self.camera_feedback_evidence_kind != RUNTIME_OBSERVED_EVIDENCE_KIND:
            blockers.append("camera_feedback_simulated_or_nonruntime")
        if self.camera_pose_lineage is None:
            blockers.append("camera_pose_lineage_missing")
        elif (
            self.camera_pose_lineage.evidence_kind
            != RUNTIME_OBSERVED_EVIDENCE_KIND
        ):
            blockers.append("camera_pose_lineage_simulated_or_nonruntime")
        if self.camera_feedback is not None and not self.pose_applied:
            blockers.append("pose_not_applied")
        if self.online_truth_use_count:
            blockers.append("online_truth_use_detected")
        if self.global_track_id_rewrite_count:
            blockers.append("global_track_id_rewrite_detected")
        return tuple(blockers)

    @property
    def model_action_adopted(self) -> bool:
        return not self.adoption_blockers

    @property
    def trace_sha256(self) -> str:
        return _sha256_json(self._payload())

    @property
    def command_payload_sha256(self) -> str | None:
        if self.issued_command_payload is None:
            return None
        return _sha256_json(dict(self.issued_command_payload))

    @property
    def runtime_ack_sha256(self) -> str | None:
        if self.runtime_ack is None:
            return None
        return _sha256_json(_runtime_ack_to_payload(self.runtime_ack))

    @property
    def camera_feedback_sha256(self) -> str | None:
        if self.camera_feedback is None:
            return None
        return _sha256_json(_camera_feedback_to_payload(self.camera_feedback))

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scale": self.scale,
            "seed": self.seed,
            "window_index": self.window_index,
            "sample_key": self.sample_key,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "pairing_context_sha256": self.pairing_context_sha256,
            "source_event_log_sha256": self.source_event_log_sha256,
            "policy_evaluated": self.policy_evaluated,
            "policy_evaluated_timestamp": self.policy_evaluated_timestamp,
            "model_fingerprint": self.model_fingerprint,
            "bundle_manifest_sha256": self.bundle_manifest_sha256,
            "bundle_weights_sha256": self.bundle_weights_sha256,
            "implementation_sha256": self.implementation_sha256,
            "source_git_commit": self.source_git_commit,
            "decision": _decision_to_payload(self.decision),
            "pre_command_camera_state": _camera_state_to_payload(
                self.pre_command_camera_state
            ),
            "issued_command_payload": (
                None
                if self.issued_command_payload is None
                else dict(self.issued_command_payload)
            ),
            "issued_command_payload_sha256": self.command_payload_sha256,
            "runtime_ack": (
                None
                if self.runtime_ack is None
                else _runtime_ack_to_payload(self.runtime_ack)
            ),
            "runtime_ack_sha256": self.runtime_ack_sha256,
            "camera_feedback": (
                None
                if self.camera_feedback is None
                else _camera_feedback_to_payload(self.camera_feedback)
            ),
            "camera_feedback_sha256": self.camera_feedback_sha256,
            "camera_pose_lineage": (
                None
                if self.camera_pose_lineage is None
                else self.camera_pose_lineage.to_dict()
            ),
            "runtime_ack_evidence_kind": self.runtime_ack_evidence_kind,
            "camera_feedback_evidence_kind": self.camera_feedback_evidence_kind,
            "synthetic_fixture": self.synthetic_fixture,
            "pose_tolerance_deg": self.pose_tolerance_deg,
            "layer_status": dict(self.layer_status),
            "online_truth_use_count": self.online_truth_use_count,
            "global_track_id_rewrite_count": self.global_track_id_rewrite_count,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["trace_sha256"] = self.trace_sha256
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ActiveVisionA3AdoptionTrace:
        _assert_truth_free(payload)
        _expect_fields(
            payload,
            {
                "schema_version",
                "comparison_key",
                "scenario_id",
                "scale",
                "seed",
                "window_index",
                "sample_key",
                "camera_id",
                "resource_id",
                "pairing_context_sha256",
                "source_event_log_sha256",
                "policy_evaluated",
                "policy_evaluated_timestamp",
                "model_fingerprint",
                "bundle_manifest_sha256",
                "bundle_weights_sha256",
                "implementation_sha256",
                "source_git_commit",
                "decision",
                "pre_command_camera_state",
                "issued_command_payload",
                "issued_command_payload_sha256",
                "runtime_ack",
                "runtime_ack_sha256",
                "camera_feedback",
                "camera_feedback_sha256",
                "camera_pose_lineage",
                "runtime_ack_evidence_kind",
                "camera_feedback_evidence_kind",
                "synthetic_fixture",
                "pose_tolerance_deg",
                "layer_status",
                "online_truth_use_count",
                "global_track_id_rewrite_count",
                "trace_sha256",
            },
            "trace",
        )
        command_payload = payload["issued_command_payload"]
        runtime_ack_payload = payload["runtime_ack"]
        feedback_payload = payload["camera_feedback"]
        pose_lineage_payload = payload["camera_pose_lineage"]
        item = cls(
            schema_version=payload["schema_version"],
            comparison_key=payload["comparison_key"],
            scenario_id=payload["scenario_id"],
            scale=payload["scale"],
            seed=payload["seed"],
            window_index=payload["window_index"],
            sample_key=payload["sample_key"],
            camera_id=payload["camera_id"],
            resource_id=payload["resource_id"],
            pairing_context_sha256=payload["pairing_context_sha256"],
            source_event_log_sha256=payload["source_event_log_sha256"],
            policy_evaluated=payload["policy_evaluated"],
            policy_evaluated_timestamp=payload["policy_evaluated_timestamp"],
            model_fingerprint=payload["model_fingerprint"],
            bundle_manifest_sha256=payload["bundle_manifest_sha256"],
            bundle_weights_sha256=payload["bundle_weights_sha256"],
            implementation_sha256=payload["implementation_sha256"],
            source_git_commit=payload["source_git_commit"],
            decision=_decision_from_payload(
                _mapping(payload["decision"], "trace.decision")
            ),
            pre_command_camera_state=_camera_state_from_payload(
                _mapping(
                    payload["pre_command_camera_state"],
                    "trace.pre_command_camera_state",
                )
            ),
            issued_command_payload=(
                None
                if command_payload is None
                else _mapping(command_payload, "trace.issued_command_payload")
            ),
            runtime_ack=(
                None
                if runtime_ack_payload is None
                else _runtime_ack_from_payload(
                    _mapping(runtime_ack_payload, "trace.runtime_ack")
                )
            ),
            camera_feedback=(
                None
                if feedback_payload is None
                else _camera_feedback_from_payload(
                    _mapping(feedback_payload, "trace.camera_feedback")
                )
            ),
            camera_pose_lineage=(
                None
                if pose_lineage_payload is None
                else ActiveVisionA3CameraPoseLineage.from_mapping(
                    _mapping(
                        pose_lineage_payload,
                        "trace.camera_pose_lineage",
                    )
                )
            ),
            runtime_ack_evidence_kind=payload["runtime_ack_evidence_kind"],
            camera_feedback_evidence_kind=payload[
                "camera_feedback_evidence_kind"
            ],
            synthetic_fixture=payload["synthetic_fixture"],
            pose_tolerance_deg=payload["pose_tolerance_deg"],
            online_truth_use_count=payload["online_truth_use_count"],
            global_track_id_rewrite_count=payload[
                "global_track_id_rewrite_count"
            ],
        )
        expected = item.to_dict()
        if expected != dict(payload):
            if expected["trace_sha256"] != payload.get("trace_sha256"):
                _fail("trace_hash_mismatch", "A3 adoption trace content hash mismatch")
            _fail(
                "trace_recomputation_mismatch",
                "stored command/ACK/feedback hashes or layer status differ from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3RuleArmTrace:
    """Independent deterministic R0 execution without model-trace fields."""

    comparison_key: str
    scenario_id: str
    scale: int
    seed: int
    window_index: int
    sample_key: str
    camera_id: str
    resource_id: str
    pairing_context_sha256: str
    source_event_log_sha256: str
    decision: ActiveVisionDecisionV1
    pre_command_camera_state: ActiveVisionCameraState
    issued_command_payload: Mapping[str, Any]
    runtime_ack: ActiveVisionRuntimeAckV1
    camera_feedback: ActiveVisionCameraFeedbackV1
    camera_pose_lineage: ActiveVisionA3CameraPoseLineage
    runtime_ack_evidence_kind: str
    camera_feedback_evidence_kind: str
    synthetic_fixture: bool = False
    pose_tolerance_deg: float = 0.25
    online_truth_use_count: int = 0
    global_track_id_rewrite_count: int = 0
    schema_version: str = ACTIVE_VISION_A3_RULE_ARM_TRACE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_A3_RULE_ARM_TRACE_SCHEMA_VERSION:
            _fail(
                "r0_trace_schema_mismatch",
                "unsupported deterministic R0 trace schema",
            )
        for name in (
            "comparison_key",
            "scenario_id",
            "sample_key",
            "camera_id",
            "resource_id",
        ):
            object.__setattr__(
                self,
                name,
                _token(getattr(self, name), f"r0_trace.{name}"),
            )
        for name in ("pairing_context_sha256", "source_event_log_sha256"):
            object.__setattr__(
                self,
                name,
                _digest(getattr(self, name), f"r0_trace.{name}"),
            )
        for name in (
            "scale",
            "seed",
            "window_index",
            "online_truth_use_count",
            "global_track_id_rewrite_count",
        ):
            object.__setattr__(
                self,
                name,
                _non_negative_int(getattr(self, name), f"r0_trace.{name}"),
            )
        if self.scale < 1:
            _fail("r0_trace_scale_invalid", "R0 scale must be at least one")
        if self.online_truth_use_count:
            _fail(
                "r0_online_truth_use_forbidden",
                "deterministic R0 cannot use online truth identity",
            )
        if self.global_track_id_rewrite_count:
            _fail(
                "r0_global_track_id_rewrite_forbidden",
                "deterministic R0 cannot create, rewrite, or rebind global_track_id",
            )
        if not isinstance(self.decision, ActiveVisionDecisionV1):
            _fail(
                "r0_decision_type_invalid",
                "R0 rule decision must use ActiveVisionDecisionV1",
            )
        _validate_decision(self.decision)
        _validate_rule_arm_decision(self.decision)
        if not isinstance(self.pre_command_camera_state, ActiveVisionCameraState):
            _fail(
                "r0_camera_state_type_invalid",
                "R0 pre-command state must use ActiveVisionCameraState",
            )
        if (
            self.pre_command_camera_state.camera_id != self.camera_id
            or self.pre_command_camera_state.resource_id != self.resource_id
            or self.decision.effective_action.camera_id != self.camera_id
        ):
            _fail(
                "r0_trace_camera_membership_mismatch",
                "R0 decision, camera state, camera ID, or resource ID disagree",
            )

        command = _validated_command_payload(self.issued_command_payload)
        _validate_command_against_action(
            command,
            action=self.decision.effective_action,
            requested_mode=self.decision.requested_mode,
            effective_mode=self.decision.effective_mode,
            pre_camera=self.pre_command_camera_state,
            resource_id=self.resource_id,
        )
        object.__setattr__(self, "issued_command_payload", MappingProxyType(command))

        if not isinstance(self.runtime_ack, ActiveVisionRuntimeAckV1):
            _fail(
                "r0_runtime_ack_type_invalid",
                "R0 ACK must use ActiveVisionRuntimeAckV1",
            )
        if not isinstance(self.camera_feedback, ActiveVisionCameraFeedbackV1):
            _fail(
                "r0_camera_feedback_type_invalid",
                "R0 feedback must use ActiveVisionCameraFeedbackV1",
            )
        if not isinstance(
            self.camera_pose_lineage,
            ActiveVisionA3CameraPoseLineage,
        ):
            _fail(
                "r0_camera_pose_lineage_type_invalid",
                "R0 pose lineage must use ActiveVisionA3CameraPoseLineage",
            )
        ack_kind = _choice(
            self.runtime_ack_evidence_kind,
            _EVIDENCE_KINDS,
            "r0_trace.runtime_ack_evidence_kind",
        )
        feedback_kind = _choice(
            self.camera_feedback_evidence_kind,
            _EVIDENCE_KINDS,
            "r0_trace.camera_feedback_evidence_kind",
        )
        synthetic = _strict_bool(
            self.synthetic_fixture,
            "r0_trace.synthetic_fixture",
        )
        if (
            ack_kind != RUNTIME_OBSERVED_EVIDENCE_KIND
            or feedback_kind != RUNTIME_OBSERVED_EVIDENCE_KIND
            or self.camera_pose_lineage.evidence_kind
            != RUNTIME_OBSERVED_EVIDENCE_KIND
            or synthetic
        ):
            _fail(
                "r0_runtime_evidence_required",
                "R0 requires independent runtime ACK, feedback, and pose lineage",
            )
        _validate_ack_against_command(
            self.runtime_ack,
            command,
            sample_key=self.sample_key,
        )
        if (
            not self.runtime_ack.accepted
            or self.runtime_ack.status_code not in {"accepted", "applied"}
        ):
            _fail(
                "r0_runtime_ack_not_applied",
                "R0 runtime ACK does not prove command application",
            )
        _validate_pose_lineage_against_feedback(
            self.camera_pose_lineage,
            self.camera_feedback,
        )
        _validate_pose_lineage_against_command(
            self.camera_pose_lineage,
            command,
            runtime_ack=self.runtime_ack,
        )
        if (
            self.camera_feedback.camera_state.camera_id != self.camera_id
            or self.camera_feedback.camera_state.resource_id != self.resource_id
        ):
            _fail(
                "r0_camera_feedback_membership_mismatch",
                "R0 feedback does not match the trace camera/resource",
            )
        if self.camera_feedback.last_accepted_command_version != (
            self.runtime_ack.command_version
        ):
            _fail(
                "r0_ack_feedback_version_mismatch",
                "R0 feedback does not carry the accepted command version",
            )

        tolerance = _finite(
            self.pose_tolerance_deg,
            "r0_trace.pose_tolerance_deg",
        )
        if not 0.0 < tolerance <= _POSE_TOLERANCE_MAX_DEG:
            _fail(
                "pose_tolerance_invalid",
                f"pose tolerance must be within (0, {_POSE_TOLERANCE_MAX_DEG}] degrees",
            )
        object.__setattr__(self, "runtime_ack_evidence_kind", ack_kind)
        object.__setattr__(self, "camera_feedback_evidence_kind", feedback_kind)
        object.__setattr__(self, "synthetic_fixture", False)
        object.__setattr__(self, "pose_tolerance_deg", tolerance)
        if not self.runtime_physical_chain_complete:
            _fail(
                "r0_pose_not_applied",
                "R0 camera feedback does not prove the deterministic rule pose",
            )
        _assert_truth_free(self)

    @property
    def target_global_track_id(self) -> str | None:
        return self.decision.effective_action.target_global_track_id

    @property
    def runtime_physical_chain_complete(self) -> bool:
        return (
            self.runtime_ack.accepted
            and self.runtime_ack.status_code in {"accepted", "applied"}
            and self.runtime_ack_evidence_kind == RUNTIME_OBSERVED_EVIDENCE_KIND
            and self.camera_feedback_evidence_kind
            == RUNTIME_OBSERVED_EVIDENCE_KIND
            and self.camera_pose_lineage.evidence_kind
            == RUNTIME_OBSERVED_EVIDENCE_KIND
            and not self.synthetic_fixture
            and _pose_applied(
                action=self.decision.effective_action,
                pre_camera=self.pre_command_camera_state,
                runtime_ack=self.runtime_ack,
                feedback=self.camera_feedback,
                pose_lineage=self.camera_pose_lineage,
                command=self.issued_command_payload,
                ack_kind=self.runtime_ack_evidence_kind,
                feedback_kind=self.camera_feedback_evidence_kind,
                synthetic_fixture=self.synthetic_fixture,
                tolerance_deg=self.pose_tolerance_deg,
            )
            and self.online_truth_use_count == 0
            and self.global_track_id_rewrite_count == 0
        )

    @property
    def comparison_identity(self) -> tuple[Any, ...]:
        return (
            self.comparison_key,
            self.scenario_id,
            self.scale,
            self.seed,
            self.window_index,
            self.camera_id,
            self.resource_id,
            self.target_global_track_id,
            self.pairing_context_sha256,
            self.decision.plan_version,
            self.decision.coalition_version,
            self.decision.communication_version,
        )

    @property
    def trace_sha256(self) -> str:
        return _sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scale": self.scale,
            "seed": self.seed,
            "window_index": self.window_index,
            "sample_key": self.sample_key,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "pairing_context_sha256": self.pairing_context_sha256,
            "source_event_log_sha256": self.source_event_log_sha256,
            "decision": _decision_to_payload(self.decision),
            "pre_command_camera_state": _camera_state_to_payload(
                self.pre_command_camera_state
            ),
            "issued_command_payload": dict(self.issued_command_payload),
            "runtime_ack": _runtime_ack_to_payload(self.runtime_ack),
            "camera_feedback": _camera_feedback_to_payload(self.camera_feedback),
            "camera_pose_lineage": self.camera_pose_lineage.to_dict(),
            "runtime_ack_evidence_kind": self.runtime_ack_evidence_kind,
            "camera_feedback_evidence_kind": self.camera_feedback_evidence_kind,
            "synthetic_fixture": self.synthetic_fixture,
            "pose_tolerance_deg": self.pose_tolerance_deg,
            "online_truth_use_count": self.online_truth_use_count,
            "global_track_id_rewrite_count": self.global_track_id_rewrite_count,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["trace_sha256"] = self.trace_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3RuleArmTrace:
        _assert_truth_free(payload)
        _expect_fields(
            payload,
            {
                "schema_version",
                "comparison_key",
                "scenario_id",
                "scale",
                "seed",
                "window_index",
                "sample_key",
                "camera_id",
                "resource_id",
                "pairing_context_sha256",
                "source_event_log_sha256",
                "decision",
                "pre_command_camera_state",
                "issued_command_payload",
                "runtime_ack",
                "camera_feedback",
                "camera_pose_lineage",
                "runtime_ack_evidence_kind",
                "camera_feedback_evidence_kind",
                "synthetic_fixture",
                "pose_tolerance_deg",
                "online_truth_use_count",
                "global_track_id_rewrite_count",
                "trace_sha256",
            },
            "r0_trace",
        )
        item = cls(
            schema_version=payload["schema_version"],
            comparison_key=payload["comparison_key"],
            scenario_id=payload["scenario_id"],
            scale=payload["scale"],
            seed=payload["seed"],
            window_index=payload["window_index"],
            sample_key=payload["sample_key"],
            camera_id=payload["camera_id"],
            resource_id=payload["resource_id"],
            pairing_context_sha256=payload["pairing_context_sha256"],
            source_event_log_sha256=payload["source_event_log_sha256"],
            decision=_decision_from_payload(
                _mapping(payload["decision"], "r0_trace.decision")
            ),
            pre_command_camera_state=_camera_state_from_payload(
                _mapping(
                    payload["pre_command_camera_state"],
                    "r0_trace.pre_command_camera_state",
                )
            ),
            issued_command_payload=_mapping(
                payload["issued_command_payload"],
                "r0_trace.issued_command_payload",
            ),
            runtime_ack=_runtime_ack_from_payload(
                _mapping(payload["runtime_ack"], "r0_trace.runtime_ack")
            ),
            camera_feedback=_camera_feedback_from_payload(
                _mapping(payload["camera_feedback"], "r0_trace.camera_feedback")
            ),
            camera_pose_lineage=ActiveVisionA3CameraPoseLineage.from_mapping(
                _mapping(
                    payload["camera_pose_lineage"],
                    "r0_trace.camera_pose_lineage",
                )
            ),
            runtime_ack_evidence_kind=payload["runtime_ack_evidence_kind"],
            camera_feedback_evidence_kind=payload[
                "camera_feedback_evidence_kind"
            ],
            synthetic_fixture=payload["synthetic_fixture"],
            pose_tolerance_deg=payload["pose_tolerance_deg"],
            online_truth_use_count=payload["online_truth_use_count"],
            global_track_id_rewrite_count=payload[
                "global_track_id_rewrite_count"
            ],
        )
        if item.to_dict() != dict(payload):
            if item.trace_sha256 != payload.get("trace_sha256"):
                _fail(
                    "r0_trace_hash_mismatch",
                    "deterministic R0 trace content hash mismatch",
                )
            _fail(
                "r0_trace_recomputation_mismatch",
                "stored R0 command, ACK, feedback, or lineage differs from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3PhysicalObservationWindow:
    """A post-command physical window built from existing action/ACK/feedback DTOs."""

    arm: ActiveVisionA3WindowArm
    comparison_key: str
    scenario_id: str
    scale: int
    seed: int
    window_index: int
    sample_key: str
    camera_id: str
    resource_id: str
    target_global_track_id: str | None
    pairing_context_sha256: str
    source_event_log_sha256: str
    command_source: ActiveVisionA3CommandSource
    effective_action: ActiveVisionActionV1
    pre_command_camera_state: ActiveVisionCameraState
    issued_command_payload: Mapping[str, Any]
    runtime_ack: ActiveVisionRuntimeAckV1
    camera_feedback: ActiveVisionCameraFeedbackV1
    camera_pose_lineage: ActiveVisionA3CameraPoseLineage
    runtime_ack_evidence_kind: str
    camera_feedback_evidence_kind: str
    observation_evidence_kind: str
    synthetic_fixture: bool
    pose_tolerance_deg: float
    window_start_timestamp: float
    window_end_timestamp: float
    first_measurement_timestamp: float
    last_measurement_timestamp: float
    first_arrival_timestamp: float
    last_arrival_timestamp: float
    observation_frames: tuple[ActiveVisionA3AnonymousObservationFrame, ...]
    outcome: ActiveVisionA3OutcomeEvidence
    adoption_trace_sha256: str | None = None
    online_truth_use_count: int = 0
    global_track_id_rewrite_count: int = 0
    schema_version: str = ACTIVE_VISION_A3_WINDOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_A3_WINDOW_SCHEMA_VERSION:
            _fail("window_schema_mismatch", "unsupported A3 physical window schema")
        arm = _enum(ActiveVisionA3WindowArm, self.arm, "window.arm")
        source = _enum(
            ActiveVisionA3CommandSource,
            self.command_source,
            "window.command_source",
        )
        for name in (
            "comparison_key",
            "scenario_id",
            "sample_key",
            "camera_id",
            "resource_id",
        ):
            object.__setattr__(self, name, _token(getattr(self, name), f"window.{name}"))
        target_id = _optional_token(
            self.target_global_track_id,
            "window.target_global_track_id",
        )
        object.__setattr__(self, "target_global_track_id", target_id)
        for name in ("pairing_context_sha256", "source_event_log_sha256"):
            object.__setattr__(
                self,
                name,
                _digest(getattr(self, name), f"window.{name}"),
            )
        for name in (
            "scale",
            "seed",
            "window_index",
            "online_truth_use_count",
            "global_track_id_rewrite_count",
        ):
            object.__setattr__(
                self,
                name,
                _non_negative_int(getattr(self, name), f"window.{name}"),
            )
        if self.scale < 1:
            _fail("window_scale_invalid", "window scale must be at least one")
        if not isinstance(self.effective_action, ActiveVisionActionV1):
            _fail("window_action_type_invalid", "window action must use ActiveVisionActionV1")
        if not isinstance(self.pre_command_camera_state, ActiveVisionCameraState):
            _fail(
                "window_camera_state_type_invalid",
                "window pre-command state must use ActiveVisionCameraState",
            )
        if not isinstance(self.runtime_ack, ActiveVisionRuntimeAckV1):
            _fail("window_ack_type_invalid", "window ACK must use ActiveVisionRuntimeAckV1")
        if not isinstance(self.camera_feedback, ActiveVisionCameraFeedbackV1):
            _fail(
                "window_feedback_type_invalid",
                "window feedback must use ActiveVisionCameraFeedbackV1",
            )
        if not isinstance(
            self.camera_pose_lineage,
            ActiveVisionA3CameraPoseLineage,
        ):
            _fail(
                "window_pose_lineage_type_invalid",
                "window pose lineage must use ActiveVisionA3CameraPoseLineage",
            )
        command = _validated_command_payload(self.issued_command_payload)
        _validate_command_against_action(
            command,
            action=self.effective_action,
            requested_mode=ActiveVisionRuntimeMode(command["requested_mode"]),
            effective_mode=ActiveVisionRuntimeMode(command["effective_mode"]),
            pre_camera=self.pre_command_camera_state,
            resource_id=self.resource_id,
        )
        object.__setattr__(self, "issued_command_payload", MappingProxyType(command))
        if (
            self.effective_action.camera_id != self.camera_id
            or self.pre_command_camera_state.camera_id != self.camera_id
            or self.pre_command_camera_state.resource_id != self.resource_id
            or self.effective_action.target_global_track_id != target_id
        ):
            _fail(
                "window_camera_membership_mismatch",
                "window action, camera, resource, or target reference disagree",
            )
        _validate_ack_against_command(
            self.runtime_ack,
            command,
            sample_key=self.sample_key,
        )
        _validate_pose_lineage_against_feedback(
            self.camera_pose_lineage,
            self.camera_feedback,
        )
        _validate_pose_lineage_against_command(
            self.camera_pose_lineage,
            command,
            runtime_ack=self.runtime_ack,
        )

        ack_kind = _choice(
            self.runtime_ack_evidence_kind,
            _EVIDENCE_KINDS,
            "window.runtime_ack_evidence_kind",
        )
        feedback_kind = _choice(
            self.camera_feedback_evidence_kind,
            _EVIDENCE_KINDS,
            "window.camera_feedback_evidence_kind",
        )
        observation_kind = _choice(
            self.observation_evidence_kind,
            _EVIDENCE_KINDS,
            "window.observation_evidence_kind",
        )
        synthetic = _strict_bool(self.synthetic_fixture, "window.synthetic_fixture")
        if UNAVAILABLE_EVIDENCE_KIND in {ack_kind, feedback_kind, observation_kind}:
            _fail(
                "window_evidence_source_unavailable",
                "physical window cannot contain unavailable ACK, feedback, or observation",
            )
        contains_synthetic = SYNTHETIC_FIXTURE_EVIDENCE_KIND in {
            ack_kind,
            feedback_kind,
            observation_kind,
        } or (
            self.camera_pose_lineage.evidence_kind
            == SYNTHETIC_FIXTURE_EVIDENCE_KIND
        )
        if synthetic != contains_synthetic:
            _fail(
                "window_synthetic_state_invalid",
                "synthetic flag must match ACK/feedback/observation provenance",
            )
        tolerance = _finite(self.pose_tolerance_deg, "window.pose_tolerance_deg")
        if not 0.0 < tolerance <= _POSE_TOLERANCE_MAX_DEG:
            _fail(
                "pose_tolerance_invalid",
                f"pose tolerance must be within (0, {_POSE_TOLERANCE_MAX_DEG}] degrees",
            )
        timestamps = {
            name: _finite(getattr(self, name), f"window.{name}")
            for name in (
                "window_start_timestamp",
                "window_end_timestamp",
                "first_measurement_timestamp",
                "last_measurement_timestamp",
                "first_arrival_timestamp",
                "last_arrival_timestamp",
            )
        }
        if timestamps["window_end_timestamp"] <= timestamps["window_start_timestamp"]:
            _fail("physical_window_time_invalid", "physical window has non-positive duration")
        if not (
            timestamps["window_start_timestamp"]
            <= timestamps["first_measurement_timestamp"]
            <= timestamps["last_measurement_timestamp"]
            <= timestamps["window_end_timestamp"]
        ):
            _fail(
                "measurement_window_time_mismatch",
                "measurement timestamps fall outside or reverse within the window",
            )
        if not (
            timestamps["first_measurement_timestamp"]
            <= timestamps["first_arrival_timestamp"]
            <= timestamps["last_arrival_timestamp"]
        ) or timestamps["last_arrival_timestamp"] + _EPS < timestamps[
            "last_measurement_timestamp"
        ]:
            _fail(
                "arrival_window_time_mismatch",
                "arrival timestamps precede measurements or reverse",
            )
        feedback_timestamp = self.camera_feedback.camera_state.state_timestamp
        if timestamps["window_start_timestamp"] + _EPS < feedback_timestamp:
            _fail(
                "physical_window_precedes_pose",
                "physical observation window starts before post-command feedback",
            )
        frames = tuple(self.observation_frames)
        if not frames or any(
            not isinstance(item, ActiveVisionA3AnonymousObservationFrame)
            for item in frames
        ):
            _fail(
                "physical_window_frames_invalid",
                "physical window requires anonymous observation frames",
            )
        if len({item.frame_key for item in frames}) != len(frames):
            _fail(
                "physical_window_frames_invalid",
                "physical observation frame keys must be unique",
            )
        ordered_frames = tuple(
            sorted(
                frames,
                key=lambda item: (
                    item.measurement_timestamp,
                    item.arrival_timestamp,
                    item.frame_key,
                ),
            )
        )
        expected_versions = (
            self.effective_action.plan_version,
            self.effective_action.coalition_version,
            self.effective_action.communication_version,
        )
        for frame in ordered_frames:
            if (
                frame.camera_id != self.camera_id
                or frame.resource_id != self.resource_id
                or frame.target_global_track_id != self.target_global_track_id
                or (
                    frame.plan_version,
                    frame.coalition_version,
                    frame.communication_version,
                )
                != expected_versions
            ):
                _fail(
                    "physical_window_frame_identity_mismatch",
                    "observation frame camera/resource/target/version differs from command",
                )
            if (
                frame.measurement_timestamp + _EPS < feedback_timestamp
                or frame.measurement_timestamp
                < timestamps["window_start_timestamp"] - _EPS
                or frame.measurement_timestamp
                > timestamps["window_end_timestamp"] + _EPS
            ):
                _fail(
                    "physical_window_frame_time_mismatch",
                    "observation frame is outside the post-command physical window",
                )
        if observation_kind not in {item.evidence_kind for item in ordered_frames}:
            _fail(
                "physical_window_frame_provenance_mismatch",
                "window provenance is absent from its anonymous observation frames",
            )
        if len({item.evidence_kind for item in ordered_frames}) != 1:
            _fail(
                "physical_window_frame_provenance_mismatch",
                "physical window cannot mix runtime and synthetic observation frames",
            )
        expected_timestamps = {
            "first_measurement_timestamp": ordered_frames[0].measurement_timestamp,
            "last_measurement_timestamp": ordered_frames[-1].measurement_timestamp,
            "first_arrival_timestamp": min(
                item.arrival_timestamp for item in ordered_frames
            ),
            "last_arrival_timestamp": max(
                item.arrival_timestamp for item in ordered_frames
            ),
        }
        if any(
            not math.isclose(
                timestamps[name],
                expected,
                rel_tol=0.0,
                abs_tol=_EPS,
            )
            for name, expected in expected_timestamps.items()
        ):
            _fail(
                "physical_window_frame_timestamp_summary_mismatch",
                "stored first/last timestamps differ from observation frames",
            )
        trace_sha = _optional_digest(
            self.adoption_trace_sha256,
            "window.adoption_trace_sha256",
        )
        if arm is ActiveVisionA3WindowArm.A3:
            if source is not ActiveVisionA3CommandSource.MODEL_ASSIST:
                _fail("candidate_command_source_invalid", "A3 window must use model assist")
            if command["effective_mode"] != "assist":
                _fail("candidate_effective_mode_invalid", "A3 window command is not assist")
            if trace_sha is None:
                _fail("adoption_trace_binding_missing", "A3 window requires trace binding")
        else:
            if source is not ActiveVisionA3CommandSource.DETERMINISTIC_RULE:
                _fail("r0_command_source_invalid", "R0 window must use deterministic rule")
            if command["effective_mode"] == "assist":
                _fail("r0_effective_mode_invalid", "R0 window cannot use assist")
            if trace_sha is not None:
                _fail("r0_trace_binding_forbidden", "R0 window cannot bind an A3 trace")
        if not isinstance(self.outcome, ActiveVisionA3OutcomeEvidence):
            _fail("window_outcome_type_invalid", "window outcome has an invalid type")
        expected_outcome = _outcome_from_observation_frames(ordered_frames)
        if self.outcome.to_dict() != expected_outcome.to_dict():
            _fail(
                "physical_window_outcome_recomputation_mismatch",
                "stored association/coverage outcome differs from anonymous frames",
            )
        object.__setattr__(self, "arm", arm)
        object.__setattr__(self, "command_source", source)
        object.__setattr__(self, "runtime_ack_evidence_kind", ack_kind)
        object.__setattr__(self, "camera_feedback_evidence_kind", feedback_kind)
        object.__setattr__(self, "observation_evidence_kind", observation_kind)
        object.__setattr__(self, "synthetic_fixture", synthetic)
        object.__setattr__(self, "pose_tolerance_deg", tolerance)
        object.__setattr__(self, "adoption_trace_sha256", trace_sha)
        object.__setattr__(self, "observation_frames", ordered_frames)
        for name, value in timestamps.items():
            object.__setattr__(self, name, value)
        _assert_truth_free(self)

    @property
    def command_payload_sha256(self) -> str:
        return _sha256_json(dict(self.issued_command_payload))

    @property
    def runtime_ack_sha256(self) -> str:
        return _sha256_json(_runtime_ack_to_payload(self.runtime_ack))

    @property
    def camera_feedback_sha256(self) -> str:
        return _sha256_json(_camera_feedback_to_payload(self.camera_feedback))

    @property
    def effective_action_sha256(self) -> str:
        return _action_sha256(self.effective_action)

    @property
    def window_sha256(self) -> str:
        return _sha256_json(self._payload())

    @property
    def duration_s(self) -> float:
        return self.window_end_timestamp - self.window_start_timestamp

    @property
    def runtime_physical_chain_complete(self) -> bool:
        return (
            self.runtime_ack.accepted
            and self.runtime_ack.status_code in {"accepted", "applied"}
            and self.runtime_ack_evidence_kind == RUNTIME_OBSERVED_EVIDENCE_KIND
            and self.camera_feedback_evidence_kind
            == RUNTIME_OBSERVED_EVIDENCE_KIND
            and self.observation_evidence_kind == RUNTIME_OBSERVED_EVIDENCE_KIND
            and self.camera_pose_lineage.evidence_kind
            == RUNTIME_OBSERVED_EVIDENCE_KIND
            and not self.synthetic_fixture
            and _pose_applied(
                action=self.effective_action,
                pre_camera=self.pre_command_camera_state,
                runtime_ack=self.runtime_ack,
                feedback=self.camera_feedback,
                pose_lineage=self.camera_pose_lineage,
                command=self.issued_command_payload,
                ack_kind=self.runtime_ack_evidence_kind,
                feedback_kind=self.camera_feedback_evidence_kind,
                synthetic_fixture=self.synthetic_fixture,
                tolerance_deg=self.pose_tolerance_deg,
            )
            and self.online_truth_use_count == 0
            and self.global_track_id_rewrite_count == 0
        )

    @property
    def comparison_identity(self) -> tuple[Any, ...]:
        return (
            self.comparison_key,
            self.scenario_id,
            self.scale,
            self.seed,
            self.window_index,
            self.camera_id,
            self.resource_id,
            self.target_global_track_id,
            self.pairing_context_sha256,
            self.effective_action.plan_version,
            self.effective_action.coalition_version,
            self.effective_action.communication_version,
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "arm": self.arm.value,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scale": self.scale,
            "seed": self.seed,
            "window_index": self.window_index,
            "sample_key": self.sample_key,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "target_global_track_id": self.target_global_track_id,
            "pairing_context_sha256": self.pairing_context_sha256,
            "source_event_log_sha256": self.source_event_log_sha256,
            "command_source": self.command_source.value,
            "effective_action": _action_to_payload(self.effective_action),
            "effective_action_sha256": self.effective_action_sha256,
            "pre_command_camera_state": _camera_state_to_payload(
                self.pre_command_camera_state
            ),
            "issued_command_payload": dict(self.issued_command_payload),
            "issued_command_payload_sha256": self.command_payload_sha256,
            "runtime_ack": _runtime_ack_to_payload(self.runtime_ack),
            "runtime_ack_sha256": self.runtime_ack_sha256,
            "camera_feedback": _camera_feedback_to_payload(self.camera_feedback),
            "camera_feedback_sha256": self.camera_feedback_sha256,
            "camera_pose_lineage": self.camera_pose_lineage.to_dict(),
            "runtime_ack_evidence_kind": self.runtime_ack_evidence_kind,
            "camera_feedback_evidence_kind": self.camera_feedback_evidence_kind,
            "observation_evidence_kind": self.observation_evidence_kind,
            "synthetic_fixture": self.synthetic_fixture,
            "pose_tolerance_deg": self.pose_tolerance_deg,
            "window_start_timestamp": self.window_start_timestamp,
            "window_end_timestamp": self.window_end_timestamp,
            "first_measurement_timestamp": self.first_measurement_timestamp,
            "last_measurement_timestamp": self.last_measurement_timestamp,
            "first_arrival_timestamp": self.first_arrival_timestamp,
            "last_arrival_timestamp": self.last_arrival_timestamp,
            "observation_frames": [
                item.to_dict() for item in self.observation_frames
            ],
            "outcome": self.outcome.to_dict(),
            "adoption_trace_sha256": self.adoption_trace_sha256,
            "online_truth_use_count": self.online_truth_use_count,
            "global_track_id_rewrite_count": self.global_track_id_rewrite_count,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["window_sha256"] = self.window_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3PhysicalObservationWindow:
        _assert_truth_free(payload)
        _expect_fields(
            payload,
            {
                "schema_version",
                "arm",
                "comparison_key",
                "scenario_id",
                "scale",
                "seed",
                "window_index",
                "sample_key",
                "camera_id",
                "resource_id",
                "target_global_track_id",
                "pairing_context_sha256",
                "source_event_log_sha256",
                "command_source",
                "effective_action",
                "effective_action_sha256",
                "pre_command_camera_state",
                "issued_command_payload",
                "issued_command_payload_sha256",
                "runtime_ack",
                "runtime_ack_sha256",
                "camera_feedback",
                "camera_feedback_sha256",
                "camera_pose_lineage",
                "runtime_ack_evidence_kind",
                "camera_feedback_evidence_kind",
                "observation_evidence_kind",
                "synthetic_fixture",
                "pose_tolerance_deg",
                "window_start_timestamp",
                "window_end_timestamp",
                "first_measurement_timestamp",
                "last_measurement_timestamp",
                "first_arrival_timestamp",
                "last_arrival_timestamp",
                "observation_frames",
                "outcome",
                "adoption_trace_sha256",
                "online_truth_use_count",
                "global_track_id_rewrite_count",
                "window_sha256",
            },
            "window",
        )
        item = cls(
            schema_version=payload["schema_version"],
            arm=payload["arm"],
            comparison_key=payload["comparison_key"],
            scenario_id=payload["scenario_id"],
            scale=payload["scale"],
            seed=payload["seed"],
            window_index=payload["window_index"],
            sample_key=payload["sample_key"],
            camera_id=payload["camera_id"],
            resource_id=payload["resource_id"],
            target_global_track_id=payload["target_global_track_id"],
            pairing_context_sha256=payload["pairing_context_sha256"],
            source_event_log_sha256=payload["source_event_log_sha256"],
            command_source=payload["command_source"],
            effective_action=_action_from_payload(
                _mapping(payload["effective_action"], "window.effective_action")
            ),
            pre_command_camera_state=_camera_state_from_payload(
                _mapping(
                    payload["pre_command_camera_state"],
                    "window.pre_command_camera_state",
                )
            ),
            issued_command_payload=_mapping(
                payload["issued_command_payload"],
                "window.issued_command_payload",
            ),
            runtime_ack=_runtime_ack_from_payload(
                _mapping(payload["runtime_ack"], "window.runtime_ack")
            ),
            camera_feedback=_camera_feedback_from_payload(
                _mapping(payload["camera_feedback"], "window.camera_feedback")
            ),
            camera_pose_lineage=ActiveVisionA3CameraPoseLineage.from_mapping(
                _mapping(
                    payload["camera_pose_lineage"],
                    "window.camera_pose_lineage",
                )
            ),
            runtime_ack_evidence_kind=payload["runtime_ack_evidence_kind"],
            camera_feedback_evidence_kind=payload[
                "camera_feedback_evidence_kind"
            ],
            observation_evidence_kind=payload["observation_evidence_kind"],
            synthetic_fixture=payload["synthetic_fixture"],
            pose_tolerance_deg=payload["pose_tolerance_deg"],
            window_start_timestamp=payload["window_start_timestamp"],
            window_end_timestamp=payload["window_end_timestamp"],
            first_measurement_timestamp=payload["first_measurement_timestamp"],
            last_measurement_timestamp=payload["last_measurement_timestamp"],
            first_arrival_timestamp=payload["first_arrival_timestamp"],
            last_arrival_timestamp=payload["last_arrival_timestamp"],
            observation_frames=tuple(
                ActiveVisionA3AnonymousObservationFrame.from_mapping(
                    _mapping(item, "window.observation_frame")
                )
                for item in payload["observation_frames"]
            ),
            outcome=ActiveVisionA3OutcomeEvidence.from_mapping(
                _mapping(payload["outcome"], "window.outcome")
            ),
            adoption_trace_sha256=payload["adoption_trace_sha256"],
            online_truth_use_count=payload["online_truth_use_count"],
            global_track_id_rewrite_count=payload[
                "global_track_id_rewrite_count"
            ],
        )
        if item.to_dict() != dict(payload):
            if item.window_sha256 != payload.get("window_sha256"):
                _fail("window_hash_mismatch", "physical observation window hash mismatch")
            _fail(
                "window_recomputation_mismatch",
                "stored action/command/ACK/feedback hashes differ from recomputation",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3CandidateStageEvidence:
    """Explicit runtime inventory used to refine a missing candidate window.

    ``None`` fields are not interpreted as missing unless the corresponding
    inventory-complete flag is true.  Runtime reasons require a complete
    runtime inventory, observation reasons require a complete observation
    inventory, and physical-window reasons require both.  The record is
    diagnostic evidence only; it cannot grant camera, assignment, control, or
    model authority.
    """

    comparison_key: str
    scenario_id: str
    scale: int
    seed: int
    window_index: int
    sample_key: str
    camera_id: str
    resource_id: str
    pairing_context_sha256: str
    adoption_trace_sha256: str
    source_event_log_sha256: str
    inventory_start_timestamp: float
    inventory_end_timestamp: float
    runtime_event_inventory_complete: bool
    command_issued_timestamp: float | None
    command_expires_timestamp: float | None
    runtime_ack_timestamp: float | None
    runtime_ack_applied: bool | None
    camera_feedback_timestamp: float | None
    observation_inventory_complete: bool
    anonymous_observation_frame_count: int | None
    first_measurement_timestamp: float | None
    last_measurement_timestamp: float | None
    first_arrival_timestamp: float | None
    last_arrival_timestamp: float | None
    physical_window_status: ActiveVisionA3CandidatePhysicalWindowStatus
    evidence_kind: str
    schema_version: str = ACTIVE_VISION_A3_CANDIDATE_STAGE_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != ACTIVE_VISION_A3_CANDIDATE_STAGE_EVIDENCE_SCHEMA_VERSION
        ):
            _fail(
                "candidate_stage_evidence_schema_mismatch",
                "unsupported candidate-stage evidence schema",
            )
        for name in (
            "comparison_key",
            "scenario_id",
            "sample_key",
            "camera_id",
            "resource_id",
        ):
            object.__setattr__(
                self,
                name,
                _token(getattr(self, name), f"candidate_stage.{name}"),
            )
        for name in (
            "pairing_context_sha256",
            "adoption_trace_sha256",
            "source_event_log_sha256",
        ):
            object.__setattr__(
                self,
                name,
                _digest(getattr(self, name), f"candidate_stage.{name}"),
            )
        for name in ("scale", "seed", "window_index"):
            object.__setattr__(
                self,
                name,
                _non_negative_int(
                    getattr(self, name),
                    f"candidate_stage.{name}",
                ),
            )
        if self.scale < 1:
            _fail(
                "candidate_stage_scale_invalid",
                "candidate-stage scale must be at least one",
            )

        inventory_start = _finite(
            self.inventory_start_timestamp,
            "candidate_stage.inventory_start_timestamp",
        )
        inventory_end = _finite(
            self.inventory_end_timestamp,
            "candidate_stage.inventory_end_timestamp",
        )
        if inventory_end + _EPS < inventory_start:
            _fail(
                "candidate_stage_inventory_time_invalid",
                "candidate-stage inventory ends before it starts",
            )
        object.__setattr__(self, "inventory_start_timestamp", inventory_start)
        object.__setattr__(self, "inventory_end_timestamp", inventory_end)

        for name in (
            "runtime_event_inventory_complete",
            "observation_inventory_complete",
        ):
            object.__setattr__(
                self,
                name,
                _strict_bool(getattr(self, name), f"candidate_stage.{name}"),
            )

        issued = _optional_finite(
            self.command_issued_timestamp,
            "candidate_stage.command_issued_timestamp",
        )
        expires = _optional_finite(
            self.command_expires_timestamp,
            "candidate_stage.command_expires_timestamp",
        )
        if (issued is None) != (expires is None):
            _fail(
                "candidate_stage_command_time_incomplete",
                "command issue and expiry timestamps must be jointly available",
            )
        if issued is not None and expires <= issued:
            _fail(
                "candidate_stage_command_time_invalid",
                "candidate-stage command has a non-positive lifetime",
            )
        object.__setattr__(self, "command_issued_timestamp", issued)
        object.__setattr__(self, "command_expires_timestamp", expires)

        ack_timestamp = _optional_finite(
            self.runtime_ack_timestamp,
            "candidate_stage.runtime_ack_timestamp",
        )
        ack_applied = (
            None
            if self.runtime_ack_applied is None
            else _strict_bool(
                self.runtime_ack_applied,
                "candidate_stage.runtime_ack_applied",
            )
        )
        if (ack_timestamp is None) != (ack_applied is None):
            _fail(
                "candidate_stage_ack_evidence_incomplete",
                "ACK timestamp and applied state must be jointly available",
            )
        feedback_timestamp = _optional_finite(
            self.camera_feedback_timestamp,
            "candidate_stage.camera_feedback_timestamp",
        )
        if issued is None and (
            ack_timestamp is not None or feedback_timestamp is not None
        ):
            _fail(
                "candidate_stage_runtime_event_without_command",
                "ACK or camera feedback cannot exist without a command event",
            )
        object.__setattr__(self, "runtime_ack_timestamp", ack_timestamp)
        object.__setattr__(self, "runtime_ack_applied", ack_applied)
        object.__setattr__(
            self,
            "camera_feedback_timestamp",
            feedback_timestamp,
        )

        frame_count = _optional_non_negative_int(
            self.anonymous_observation_frame_count,
            "candidate_stage.anonymous_observation_frame_count",
        )
        observation_times = {
            name: _optional_finite(
                getattr(self, name),
                f"candidate_stage.{name}",
            )
            for name in (
                "first_measurement_timestamp",
                "last_measurement_timestamp",
                "first_arrival_timestamp",
                "last_arrival_timestamp",
            )
        }
        if frame_count is None or frame_count == 0:
            if any(value is not None for value in observation_times.values()):
                _fail(
                    "candidate_stage_observation_time_invalid",
                    "zero or unavailable frame count cannot carry frame timestamps",
                )
        elif any(value is None for value in observation_times.values()):
            _fail(
                "candidate_stage_observation_time_incomplete",
                "positive frame count requires first/last measurement and arrival times",
            )
        if self.observation_inventory_complete and frame_count is None:
            _fail(
                "candidate_stage_observation_inventory_incomplete",
                "complete observation inventory requires an explicit frame count",
            )
        object.__setattr__(
            self,
            "anonymous_observation_frame_count",
            frame_count,
        )
        for name, value in observation_times.items():
            object.__setattr__(self, name, value)

        status = _enum(
            ActiveVisionA3CandidatePhysicalWindowStatus,
            self.physical_window_status,
            "candidate_stage.physical_window_status",
        )
        if status is ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE:
            if (
                not self.runtime_event_inventory_complete
                or ack_applied is not True
                or feedback_timestamp is None
                or not self.observation_inventory_complete
                or frame_count is None
                or frame_count < 1
            ):
                _fail(
                    "candidate_stage_complete_state_invalid",
                    "complete physical-window status requires the full "
                    "runtime and observation chain",
                )
        object.__setattr__(self, "physical_window_status", status)
        evidence_kind = _choice(
            self.evidence_kind,
            frozenset({RUNTIME_OBSERVED_EVIDENCE_KIND}),
            "candidate_stage.evidence_kind",
        )
        object.__setattr__(self, "evidence_kind", evidence_kind)
        _assert_truth_free(self)

    @property
    def content_sha256(self) -> str:
        return _sha256_json(self._payload())

    @property
    def comparison_identity(self) -> tuple[Any, ...]:
        return (
            self.comparison_key,
            self.scenario_id,
            self.scale,
            self.seed,
            self.window_index,
            self.sample_key,
            self.camera_id,
            self.resource_id,
            self.pairing_context_sha256,
            self.adoption_trace_sha256,
            self.source_event_log_sha256,
        )

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scale": self.scale,
            "seed": self.seed,
            "window_index": self.window_index,
            "sample_key": self.sample_key,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "pairing_context_sha256": self.pairing_context_sha256,
            "adoption_trace_sha256": self.adoption_trace_sha256,
            "source_event_log_sha256": self.source_event_log_sha256,
            "inventory_start_timestamp": self.inventory_start_timestamp,
            "inventory_end_timestamp": self.inventory_end_timestamp,
            "runtime_event_inventory_complete": (
                self.runtime_event_inventory_complete
            ),
            "command_issued_timestamp": self.command_issued_timestamp,
            "command_expires_timestamp": self.command_expires_timestamp,
            "runtime_ack_timestamp": self.runtime_ack_timestamp,
            "runtime_ack_applied": self.runtime_ack_applied,
            "camera_feedback_timestamp": self.camera_feedback_timestamp,
            "observation_inventory_complete": (
                self.observation_inventory_complete
            ),
            "anonymous_observation_frame_count": (
                self.anonymous_observation_frame_count
            ),
            "first_measurement_timestamp": self.first_measurement_timestamp,
            "last_measurement_timestamp": self.last_measurement_timestamp,
            "first_arrival_timestamp": self.first_arrival_timestamp,
            "last_arrival_timestamp": self.last_arrival_timestamp,
            "physical_window_status": self.physical_window_status.value,
            "evidence_kind": self.evidence_kind,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3CandidateStageEvidence:
        payload = _mapping(payload, "candidate_stage_evidence")
        _assert_truth_free(payload)
        _expect_fields(
            payload,
            {
                "schema_version",
                "comparison_key",
                "scenario_id",
                "scale",
                "seed",
                "window_index",
                "sample_key",
                "camera_id",
                "resource_id",
                "pairing_context_sha256",
                "adoption_trace_sha256",
                "source_event_log_sha256",
                "inventory_start_timestamp",
                "inventory_end_timestamp",
                "runtime_event_inventory_complete",
                "command_issued_timestamp",
                "command_expires_timestamp",
                "runtime_ack_timestamp",
                "runtime_ack_applied",
                "camera_feedback_timestamp",
                "observation_inventory_complete",
                "anonymous_observation_frame_count",
                "first_measurement_timestamp",
                "last_measurement_timestamp",
                "first_arrival_timestamp",
                "last_arrival_timestamp",
                "physical_window_status",
                "evidence_kind",
                "content_sha256",
            },
            "candidate_stage_evidence",
        )
        for name in (
            "schema_version",
            "comparison_key",
            "scenario_id",
            "sample_key",
            "camera_id",
            "resource_id",
            "pairing_context_sha256",
            "adoption_trace_sha256",
            "source_event_log_sha256",
            "physical_window_status",
            "evidence_kind",
            "content_sha256",
        ):
            if type(payload[name]) is not str:
                _fail(
                    "candidate_stage_evidence_field_type_invalid",
                    f"{name} must be a string",
                )
        for name in ("scale", "seed", "window_index"):
            if type(payload[name]) is not int:
                _fail(
                    "candidate_stage_evidence_field_type_invalid",
                    f"{name} must be an integer",
                )
        for name in (
            "runtime_event_inventory_complete",
            "observation_inventory_complete",
        ):
            if type(payload[name]) is not bool:
                _fail(
                    "candidate_stage_evidence_field_type_invalid",
                    f"{name} must be a boolean",
                )
        if (
            payload["runtime_ack_applied"] is not None
            and type(payload["runtime_ack_applied"]) is not bool
        ):
            _fail(
                "candidate_stage_evidence_field_type_invalid",
                "runtime_ack_applied must be a boolean or null",
            )
        if (
            payload["anonymous_observation_frame_count"] is not None
            and type(payload["anonymous_observation_frame_count"]) is not int
        ):
            _fail(
                "candidate_stage_evidence_field_type_invalid",
                "anonymous_observation_frame_count must be an integer or null",
            )
        for name in (
            "inventory_start_timestamp",
            "inventory_end_timestamp",
            "command_issued_timestamp",
            "command_expires_timestamp",
            "runtime_ack_timestamp",
            "camera_feedback_timestamp",
            "first_measurement_timestamp",
            "last_measurement_timestamp",
            "first_arrival_timestamp",
            "last_arrival_timestamp",
        ):
            value = payload[name]
            if value is not None and (
                type(value) not in (int, float) or isinstance(value, bool)
            ):
                _fail(
                    "candidate_stage_evidence_field_type_invalid",
                    f"{name} must be a JSON number or null",
                )
        item = cls(
            **{
                name: payload[name]
                for name in payload
                if name != "content_sha256"
            }
        )
        stored_hash = _digest(
            payload["content_sha256"],
            "candidate_stage_evidence.content_sha256",
        )
        if item.content_sha256 != stored_hash:
            _fail(
                "candidate_stage_evidence_hash_mismatch",
                "candidate-stage evidence hash differs from recomputation",
            )
        if item.to_dict() != dict(payload):
            _fail(
                "candidate_stage_evidence_recomputation_mismatch",
                "stored candidate-stage evidence differs from strict reconstruction",
            )
        return item


@dataclass(frozen=True, slots=True)
class ActiveVisionA3AuditPermissions:
    d6_benefit_audit_input_allowed: bool
    active_vision_assist_authority: bool = False
    camera_command_authority: bool = False
    assignment_authority: bool = False
    failover_authority: bool = False
    control_authority: bool = False
    model_promotion_authority: bool = False
    global_track_id_mutation_authority: bool = False
    g1_authorization_granted: bool = False

    def __post_init__(self) -> None:
        allowed = _strict_bool(
            self.d6_benefit_audit_input_allowed,
            "permissions.d6_benefit_audit_input_allowed",
        )
        object.__setattr__(self, "d6_benefit_audit_input_allowed", allowed)
        for name in (
            "active_vision_assist_authority",
            "camera_command_authority",
            "assignment_authority",
            "failover_authority",
            "control_authority",
            "model_promotion_authority",
            "global_track_id_mutation_authority",
            "g1_authorization_granted",
        ):
            value = _strict_bool(getattr(self, name), f"permissions.{name}")
            if value:
                _fail(
                    "authority_escalation_forbidden",
                    f"A3 evidence cannot grant {name}",
                )
            object.__setattr__(self, name, False)

    def to_dict(self) -> dict[str, bool]:
        return {
            "d6_benefit_audit_input_allowed": self.d6_benefit_audit_input_allowed,
            "active_vision_assist_authority": self.active_vision_assist_authority,
            "camera_command_authority": self.camera_command_authority,
            "assignment_authority": self.assignment_authority,
            "failover_authority": self.failover_authority,
            "control_authority": self.control_authority,
            "model_promotion_authority": self.model_promotion_authority,
            "global_track_id_mutation_authority": self.global_track_id_mutation_authority,
            "g1_authorization_granted": self.g1_authorization_granted,
        }


@dataclass(frozen=True, slots=True)
class ActiveVisionA3BenefitAuditInput:
    adoption_trace: ActiveVisionA3AdoptionTrace
    candidate_window: ActiveVisionA3PhysicalObservationWindow | None
    same_key_r0_window: ActiveVisionA3PhysicalObservationWindow | None
    blocker_codes: tuple[str, ...]
    model_action_adopted: bool
    candidate_physical_window_available: bool
    same_key_r0_window_available: bool
    association_coverage_outcomes_available: bool
    d6_benefit_audit_eligible: bool
    permissions: ActiveVisionA3AuditPermissions
    schema_version: str = ACTIVE_VISION_A3_AUDIT_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ACTIVE_VISION_A3_AUDIT_INPUT_SCHEMA_VERSION:
            _fail("audit_input_schema_mismatch", "unsupported A3 audit input schema")
        if not isinstance(self.adoption_trace, ActiveVisionA3AdoptionTrace):
            _fail("audit_trace_type_invalid", "audit input has an invalid adoption trace")
        for name, value in (
            ("candidate_window", self.candidate_window),
            ("same_key_r0_window", self.same_key_r0_window),
        ):
            if value is not None and not isinstance(
                value,
                ActiveVisionA3PhysicalObservationWindow,
            ):
                _fail("audit_window_type_invalid", f"{name} has an invalid type")
        blockers = tuple(_token(value, "audit.blocker_code") for value in self.blocker_codes)
        if len(blockers) != len(set(blockers)):
            _fail("audit_blockers_invalid", "audit blockers must be unique")
        object.__setattr__(self, "blocker_codes", blockers)
        for name in (
            "model_action_adopted",
            "candidate_physical_window_available",
            "same_key_r0_window_available",
            "association_coverage_outcomes_available",
            "d6_benefit_audit_eligible",
        ):
            object.__setattr__(
                self,
                name,
                _strict_bool(getattr(self, name), f"audit.{name}"),
            )
        if not isinstance(self.permissions, ActiveVisionA3AuditPermissions):
            _fail("audit_permissions_type_invalid", "audit permissions have an invalid type")
        if self.d6_benefit_audit_eligible != (not blockers):
            _fail(
                "audit_eligibility_invalid",
                "D6 benefit eligibility must exactly equal the absence of blockers",
            )
        if (
            self.permissions.d6_benefit_audit_input_allowed
            != self.d6_benefit_audit_eligible
        ):
            _fail(
                "audit_permission_invalid",
                "D6 audit permission must match computed eligibility",
            )

    @property
    def content_sha256(self) -> str:
        return _sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adoption_trace": self.adoption_trace.to_dict(),
            "candidate_window": (
                None if self.candidate_window is None else self.candidate_window.to_dict()
            ),
            "same_key_r0_window": (
                None
                if self.same_key_r0_window is None
                else self.same_key_r0_window.to_dict()
            ),
            "blocker_codes": list(self.blocker_codes),
            "model_action_adopted": self.model_action_adopted,
            "candidate_physical_window_available": (
                self.candidate_physical_window_available
            ),
            "same_key_r0_window_available": self.same_key_r0_window_available,
            "association_coverage_outcomes_available": (
                self.association_coverage_outcomes_available
            ),
            "d6_benefit_audit_eligible": self.d6_benefit_audit_eligible,
            "permissions": self.permissions.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ActiveVisionA3PairingDisposition:
    """Read-only outcome for one candidate-to-R0 pairing attempt."""

    comparison_key: str | None
    scenario_id: str | None
    scale: int | None
    seed: int | None
    window_index: int | None
    sample_key: str | None
    camera_id: str | None
    resource_id: str | None
    target_global_track_id: str | None
    pairing_context_sha256: str | None
    adoption_trace_sha256: str | None
    pairable: bool
    reason_code: ActiveVisionA3PairingDispositionCode
    detail_codes: tuple[str, ...]
    paired_evidence: ActiveVisionA3BenefitAuditInput | None
    candidate_stage_reason_codes: tuple[
        ActiveVisionA3CandidateStageReasonCode, ...
    ] = ()
    candidate_stage_evidence: ActiveVisionA3CandidateStageEvidence | None = None
    schema_version: str = ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in {
            ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION,
            ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION,
        }:
            _fail(
                "pairing_disposition_schema_mismatch",
                "unsupported A3 pairing disposition schema",
            )
        reason = _enum(
            ActiveVisionA3PairingDispositionCode,
            self.reason_code,
            "pairing_disposition.reason_code",
        )
        pairable = _strict_bool(self.pairable, "pairing_disposition.pairable")
        details = tuple(
            _token(value, "pairing_disposition.detail_code")
            for value in self.detail_codes
        )
        if len(details) != len(set(details)):
            _fail(
                "pairing_disposition_details_invalid",
                "pairing disposition detail codes must be unique",
            )
        stage_reasons: list[ActiveVisionA3CandidateStageReasonCode] = []
        for value in self.candidate_stage_reason_codes:
            try:
                stage_reasons.append(
                    ActiveVisionA3CandidateStageReasonCode(value)
                )
            except (TypeError, ValueError):
                _fail(
                    "pairing_disposition_stage_reason_unsupported",
                    f"unsupported candidate-stage reason: {value!r}",
                )
        if len(stage_reasons) != len(set(stage_reasons)):
            _fail(
                "pairing_disposition_stage_reasons_invalid",
                "candidate-stage reason codes must be unique",
            )
        stage_evidence = self.candidate_stage_evidence
        if stage_evidence is not None and not isinstance(
            stage_evidence,
            ActiveVisionA3CandidateStageEvidence,
        ):
            _fail(
                "pairing_disposition_stage_evidence_type_invalid",
                "candidate-stage evidence has an invalid type",
            )
        if (
            self.schema_version
            == ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION
            and (stage_reasons or stage_evidence is not None)
        ):
            _fail(
                "pairing_disposition_legacy_stage_evidence_forbidden",
                "legacy v1 disposition cannot carry candidate-stage evidence",
            )
        expected_stage_reasons = (
            ()
            if stage_evidence is None
            else _candidate_stage_reason_codes(stage_evidence)
        )
        if tuple(stage_reasons) != expected_stage_reasons:
            _fail(
                "pairing_disposition_stage_reason_mismatch",
                "candidate-stage reasons differ from the bound runtime evidence",
            )
        reference_values = (
            self.comparison_key,
            self.scenario_id,
            self.sample_key,
            self.camera_id,
            self.resource_id,
        )
        reference_available = self.adoption_trace_sha256 is not None
        if reference_available:
            for name, value in zip(
                (
                    "comparison_key",
                    "scenario_id",
                    "sample_key",
                    "camera_id",
                    "resource_id",
                ),
                reference_values,
            ):
                object.__setattr__(
                    self,
                    name,
                    _token(value, f"pairing_disposition.{name}"),
                )
            for name in ("scale", "seed", "window_index"):
                object.__setattr__(
                    self,
                    name,
                    _non_negative_int(
                        getattr(self, name),
                        f"pairing_disposition.{name}",
                    ),
                )
            object.__setattr__(
                self,
                "target_global_track_id",
                _optional_token(
                    self.target_global_track_id,
                    "pairing_disposition.target_global_track_id",
                ),
            )
            object.__setattr__(
                self,
                "pairing_context_sha256",
                _digest(
                    self.pairing_context_sha256,
                    "pairing_disposition.pairing_context_sha256",
                ),
            )
            object.__setattr__(
                self,
                "adoption_trace_sha256",
                _digest(
                    self.adoption_trace_sha256,
                    "pairing_disposition.adoption_trace_sha256",
                ),
            )
        elif any(value is not None for value in reference_values) or any(
            value is not None
            for value in (
                self.scale,
                self.seed,
                self.window_index,
                self.target_global_track_id,
                self.pairing_context_sha256,
            )
        ):
            _fail(
                "pairing_disposition_reference_invalid",
                "unvalidated candidate references must remain unavailable",
            )
        if stage_evidence is not None:
            if not reference_available:
                _fail(
                    "pairing_disposition_stage_reference_unavailable",
                    "candidate-stage evidence requires validated candidate references",
                )
            if (
                self.comparison_key,
                self.scenario_id,
                self.scale,
                self.seed,
                self.window_index,
                self.sample_key,
                self.camera_id,
                self.resource_id,
                self.pairing_context_sha256,
                self.adoption_trace_sha256,
            ) != (
                stage_evidence.comparison_key,
                stage_evidence.scenario_id,
                stage_evidence.scale,
                stage_evidence.seed,
                stage_evidence.window_index,
                stage_evidence.sample_key,
                stage_evidence.camera_id,
                stage_evidence.resource_id,
                stage_evidence.pairing_context_sha256,
                stage_evidence.adoption_trace_sha256,
            ):
                _fail(
                    "pairing_disposition_stage_reference_mismatch",
                    "candidate-stage evidence refers to a different candidate trace",
                )

        if pairable != (reason is ActiveVisionA3PairingDispositionCode.PAIRABLE):
            _fail(
                "pairing_disposition_state_invalid",
                "pairable flag and reason code disagree",
            )
        if pairable:
            if stage_reasons:
                _fail(
                    "pairing_disposition_stage_failure_on_pairable",
                    "pairable disposition cannot carry a failed candidate stage",
                )
            if details:
                _fail(
                    "pairing_disposition_details_invalid",
                    "a pairable disposition cannot carry failure detail codes",
                )
            if not isinstance(self.paired_evidence, ActiveVisionA3BenefitAuditInput):
                _fail(
                    "pairing_disposition_evidence_missing",
                    "a pairable disposition requires existing paired evidence",
                )
            if not self.paired_evidence.d6_benefit_audit_eligible:
                _fail(
                    "pairing_disposition_evidence_ineligible",
                    "referenced paired evidence is not D6 benefit-audit eligible",
                )
            if (
                self.adoption_trace_sha256
                != self.paired_evidence.adoption_trace.trace_sha256
            ):
                _fail(
                    "pairing_disposition_trace_mismatch",
                    "paired evidence references a different adoption trace",
                )
            trace = self.paired_evidence.adoption_trace
            if (
                self.comparison_key,
                self.scenario_id,
                self.scale,
                self.seed,
                self.window_index,
                self.sample_key,
                self.camera_id,
                self.resource_id,
                self.target_global_track_id,
                self.pairing_context_sha256,
            ) != (
                trace.comparison_key,
                trace.scenario_id,
                trace.scale,
                trace.seed,
                trace.window_index,
                trace.sample_key,
                trace.camera_id,
                trace.resource_id,
                trace.target_global_track_id,
                trace.pairing_context_sha256,
            ):
                _fail(
                    "pairing_disposition_reference_mismatch",
                    "disposition candidate references differ from paired evidence",
                )
        else:
            if not details:
                _fail(
                    "pairing_disposition_details_missing",
                    "an unpairable disposition requires a diagnostic code",
                )
            if self.paired_evidence is not None:
                _fail(
                    "pairing_disposition_evidence_forbidden",
                    "unpairable dispositions cannot expose paired evidence",
                )
        object.__setattr__(self, "reason_code", reason)
        object.__setattr__(self, "pairable", pairable)
        object.__setattr__(self, "detail_codes", details)
        object.__setattr__(
            self,
            "candidate_stage_reason_codes",
            tuple(stage_reasons),
        )
        object.__setattr__(
            self,
            "candidate_stage_evidence",
            stage_evidence,
        )

    @property
    def content_sha256(self) -> str:
        return _sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "comparison_key": self.comparison_key,
            "scenario_id": self.scenario_id,
            "scale": self.scale,
            "seed": self.seed,
            "window_index": self.window_index,
            "sample_key": self.sample_key,
            "camera_id": self.camera_id,
            "resource_id": self.resource_id,
            "target_global_track_id": self.target_global_track_id,
            "pairing_context_sha256": self.pairing_context_sha256,
            "adoption_trace_sha256": self.adoption_trace_sha256,
            "pairable": self.pairable,
            "reason_code": self.reason_code.value,
            "detail_codes": list(self.detail_codes),
            "paired_evidence": (
                None
                if self.paired_evidence is None
                else self.paired_evidence.to_dict()
            ),
        }
        if (
            self.schema_version
            == ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION
        ):
            payload["candidate_stage_reason_codes"] = [
                value.value for value in self.candidate_stage_reason_codes
            ]
            payload["candidate_stage_evidence"] = (
                None
                if self.candidate_stage_evidence is None
                else self.candidate_stage_evidence.to_dict()
            )
        return payload

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content_sha256"] = self.content_sha256
        return payload

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> ActiveVisionA3PairingDisposition:
        """Strictly reload one persisted disposition artifact."""

        return validate_active_vision_a3_pairing_disposition(payload)


def camera_observation_command_payload(command: Any) -> dict[str, Any]:
    """Convert the existing main ``CameraObservationCommand`` to canonical JSON.

    D5 intentionally uses structural access here instead of importing main.
    Missing or altered fields fail closed.
    """

    required = (
        "camera_id",
        "resource_id",
        "issued_timestamp",
        "expires_timestamp",
        "plan_version",
        "coalition_version",
        "communication_version",
        "intent",
        "aim_point_ned",
        "horizontal_fov_deg",
        "fov_mode",
        "target_global_track_id",
        "requested_mode",
        "effective_mode",
        "reason",
    )
    missing = [name for name in required if not hasattr(command, name)]
    if missing:
        _fail(
            "camera_command_contract_invalid",
            f"CameraObservationCommand is missing fields: {missing}",
        )
    aim_point = getattr(command, "aim_point_ned")
    try:
        aim_values = [float(value) for value in aim_point]
    except (TypeError, ValueError):
        _fail("camera_command_contract_invalid", "aim_point_ned is not a numeric vector")
    payload = {
        "payload_version": CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION,
        **{name: getattr(command, name) for name in required if name != "aim_point_ned"},
        "aim_point_ned": aim_values,
    }
    return _validated_command_payload(payload)


def map_active_vision_binding_state(decision_state: str) -> str:
    """Map D5 anonymous binding state to the terminal association state."""

    state = _choice(
        decision_state,
        frozenset(_ANONYMOUS_BINDING_STATE_MAP),
        "binding.decision_state",
    )
    return _ANONYMOUS_BINDING_STATE_MAP[state]


def active_vision_runtime_ack_from_payload(
    payload: Mapping[str, Any],
    *,
    sample_key: str,
    command_payload: Mapping[str, Any],
) -> ActiveVisionRuntimeAckV1:
    """Strictly adapt one existing ``runtime.camera_command_ack`` payload."""

    _assert_truth_free(payload)
    _expect_fields(
        payload,
        {
            "camera_id",
            "resource_id",
            "issued_timestamp",
            "ack_timestamp",
            "expires_timestamp",
            "plan_version",
            "coalition_version",
            "communication_version",
            "command_version",
            "intent",
            "target_global_track_id",
            "requested_mode",
            "effective_mode",
            "status",
            "reason",
        },
        "runtime_camera_ack",
    )
    command = _validated_command_payload(command_payload)
    status = _choice(
        payload["status"],
        frozenset({"applied", "rejected"}),
        "runtime_camera_ack.status",
    )
    comparisons = {
        "camera_id": command["camera_id"],
        "resource_id": command["resource_id"],
        "issued_timestamp": command["issued_timestamp"],
        "expires_timestamp": command["expires_timestamp"],
        "plan_version": command["plan_version"],
        "coalition_version": command["coalition_version"],
        "communication_version": command["communication_version"],
        "command_version": command["communication_version"],
        "intent": command["intent"],
        "target_global_track_id": command["target_global_track_id"],
        "requested_mode": command["requested_mode"],
        "effective_mode": command["effective_mode"],
    }
    for name, expected in comparisons.items():
        actual = payload[name]
        if isinstance(expected, float):
            matches = math.isclose(
                _finite(actual, f"runtime_camera_ack.{name}"),
                expected,
                rel_tol=0.0,
                abs_tol=_EPS,
            )
        elif isinstance(expected, int):
            matches = (
                _non_negative_int(actual, f"runtime_camera_ack.{name}")
                == expected
            )
        else:
            matches = actual == expected
        if not matches:
            _fail(
                "runtime_ack_command_mismatch",
                f"runtime ACK {name} differs from camera command",
            )
    ack_timestamp = _finite(
        payload["ack_timestamp"],
        "runtime_camera_ack.ack_timestamp",
    )
    if (
        ack_timestamp + _EPS < command["issued_timestamp"]
        or ack_timestamp > command["expires_timestamp"] + _EPS
    ):
        _fail(
            "runtime_ack_time_mismatch",
            "runtime ACK lies outside the camera command lifetime",
        )
    reason = _token(payload["reason"], "runtime_camera_ack.reason")
    if status == "applied" and reason not in {"accepted", "applied"}:
        _fail(
            "runtime_ack_status_mismatch",
            "applied runtime ACK has a non-applied reason",
        )
    if status == "rejected" and reason in {"accepted", "applied"}:
        _fail(
            "runtime_ack_status_mismatch",
            "rejected runtime ACK has an applied reason",
        )
    ack = ActiveVisionRuntimeAckV1(
        sample_key=_token(sample_key, "runtime_camera_ack.sample_key"),
        camera_id=command["camera_id"],
        command_version=command["communication_version"],
        ack_timestamp=ack_timestamp,
        accepted=status == "applied",
        status_code="applied" if status == "applied" else reason,
        plan_version=command["plan_version"],
        coalition_version=command["coalition_version"],
        communication_version=command["communication_version"],
    )
    _validate_ack_against_command(ack, command, sample_key=sample_key)
    return ack


def active_vision_camera_pose_lineage_from_runtime_state(
    runtime_state: Any,
    *,
    evidence_kind: str,
    source_sequence: int | None = None,
) -> ActiveVisionA3CameraPoseLineage:
    """Structurally adapt main's post-command ``CameraRuntimeState``."""

    required = (
        "camera_id",
        "resource_id",
        "timestamp",
        "yaw_deg",
        "pitch_deg",
        "horizontal_fov_deg",
        "fov_mode",
        "last_plan_version",
        "last_coalition_version",
        "last_communication_version",
    )
    missing = [name for name in required if not hasattr(runtime_state, name)]
    if missing:
        _fail(
            "camera_runtime_state_contract_invalid",
            f"CameraRuntimeState is missing fields: {missing}",
        )
    payload = {name: getattr(runtime_state, name) for name in required}
    _assert_truth_free(payload)
    return ActiveVisionA3CameraPoseLineage(
        camera_id=payload["camera_id"],
        resource_id=payload["resource_id"],
        state_timestamp=payload["timestamp"],
        yaw_deg=payload["yaw_deg"],
        pitch_deg=payload["pitch_deg"],
        horizontal_fov_deg=payload["horizontal_fov_deg"],
        fov_mode=payload["fov_mode"],
        last_plan_version=payload["last_plan_version"],
        last_coalition_version=payload["last_coalition_version"],
        last_communication_version=payload["last_communication_version"],
        evidence_kind=evidence_kind,
        source_sequence=source_sequence,
    )


def active_vision_camera_feedback_from_runtime_state(
    runtime_state: Any,
    *,
    pre_command_camera_state: ActiveVisionCameraState,
    evidence_kind: str,
    source_sequence: int | None = None,
) -> tuple[ActiveVisionCameraFeedbackV1, ActiveVisionA3CameraPoseLineage]:
    """Build existing feedback plus independently versioned pose lineage."""

    if not isinstance(pre_command_camera_state, ActiveVisionCameraState):
        _fail(
            "camera_state_type_invalid",
            "pre-command camera state must use ActiveVisionCameraState",
        )
    lineage = active_vision_camera_pose_lineage_from_runtime_state(
        runtime_state,
        evidence_kind=evidence_kind,
        source_sequence=source_sequence,
    )
    if (
        lineage.camera_id != pre_command_camera_state.camera_id
        or lineage.resource_id != pre_command_camera_state.resource_id
    ):
        _fail(
            "camera_runtime_state_membership_mismatch",
            "runtime camera state does not match the pre-command camera/resource",
        )
    feedback = ActiveVisionCameraFeedbackV1(
        camera_state=ActiveVisionCameraState(
            camera_id=lineage.camera_id,
            resource_id=lineage.resource_id,
            state_timestamp=lineage.state_timestamp,
            yaw_deg=lineage.yaw_deg,
            pitch_deg=lineage.pitch_deg,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=pre_command_camera_state.yaw_limits_deg,
            pitch_limits_deg=pre_command_camera_state.pitch_limits_deg,
            max_yaw_rate_deg_s=pre_command_camera_state.max_yaw_rate_deg_s,
            max_pitch_rate_deg_s=pre_command_camera_state.max_pitch_rate_deg_s,
            max_slew_deg_s=pre_command_camera_state.max_slew_deg_s,
            current_fov_mode=ActiveVisionFovMode(lineage.fov_mode),
            supported_fov_modes=pre_command_camera_state.supported_fov_modes,
            wide_horizontal_fov_deg=pre_command_camera_state.wide_horizontal_fov_deg,
            zoom_horizontal_fov_deg=pre_command_camera_state.zoom_horizontal_fov_deg,
            slew_available=pre_command_camera_state.slew_available,
            action_in_progress_until=pre_command_camera_state.action_in_progress_until,
        ),
        last_accepted_command_version=(
            None
            if lineage.last_communication_version == 0
            else lineage.last_communication_version
        ),
    )
    _validate_pose_lineage_against_feedback(lineage, feedback)
    return feedback, lineage


def assemble_active_vision_a3_adoption_trace(
    *,
    comparison_key: str,
    scenario_id: str,
    scale: int,
    seed: int,
    window_index: int,
    sample_key: str,
    pairing_context_sha256: str,
    source_event_log_sha256: str,
    snapshot: Any,
    decision: ActiveVisionDecisionV1,
    issued_command: Any | None,
    runtime_ack_payload: Mapping[str, Any] | ActiveVisionRuntimeAckV1 | None,
    post_command_camera_state: Any | None,
    policy_evaluated: bool,
    policy_evaluated_timestamp: float | None,
    model_fingerprint: str,
    bundle_manifest_sha256: str,
    bundle_weights_sha256: str,
    implementation_sha256: str,
    source_git_commit: str,
    runtime_ack_evidence_kind: str,
    camera_feedback_evidence_kind: str,
    camera_state_source_sequence: int | None = None,
    pose_tolerance_deg: float = 0.25,
    online_truth_use_count: int = 0,
    global_track_id_rewrite_count: int = 0,
) -> ActiveVisionA3AdoptionTrace:
    """Build one A3 trace from the existing snapshot and main runtime DTOs."""

    from .active_vision_contracts import ActiveVisionSnapshotV1

    if not isinstance(snapshot, ActiveVisionSnapshotV1):
        _fail(
            "snapshot_type_invalid",
            "A3 trace assembly requires ActiveVisionSnapshotV1",
        )
    if not isinstance(decision, ActiveVisionDecisionV1):
        _fail(
            "decision_type_invalid",
            "A3 trace assembly requires ActiveVisionDecisionV1",
        )
    _validate_decision(decision)
    versions = (
        snapshot.plan.plan_version,
        snapshot.plan.coalition_version,
        snapshot.communication.communication_version,
    )
    if (
        snapshot.communication.plan_version,
        snapshot.communication.coalition_version,
    ) != versions[:2]:
        _fail(
            "snapshot_version_mismatch",
            "snapshot plan and communication references disagree",
        )
    if (
        decision.plan_version,
        decision.coalition_version,
        decision.communication_version,
    ) != versions:
        _fail(
            "snapshot_decision_version_mismatch",
            "decision versions differ from the active-vision snapshot",
        )
    camera_id = decision.effective_action.camera_id
    pre_camera = snapshot.camera(camera_id)
    center_track_ids = {item.global_track_id for item in snapshot.tracks}
    assigned_track_ids = set(snapshot.assigned_target_ids(camera_id))
    for action in (
        decision.rule_action,
        decision.effective_action,
        decision.requested_action,
    ):
        if action is None or action.target_global_track_id is None:
            continue
        if (
            action.target_global_track_id not in center_track_ids
            or action.target_global_track_id not in assigned_track_ids
        ):
            _fail(
                "decision_target_not_center_assigned",
                "active-vision target is not a center-owned assignment for this camera",
            )
    if snapshot.snapshot_timestamp + _EPS < pre_camera.state_timestamp:
        _fail(
            "snapshot_camera_time_invalid",
            "pre-command camera state follows the snapshot timestamp",
        )

    command_payload = (
        None
        if issued_command is None
        else (
            _validated_command_payload(issued_command)
            if isinstance(issued_command, Mapping)
            else camera_observation_command_payload(issued_command)
        )
    )
    runtime_ack: ActiveVisionRuntimeAckV1 | None = None
    feedback: ActiveVisionCameraFeedbackV1 | None = None
    pose_lineage: ActiveVisionA3CameraPoseLineage | None = None
    if command_payload is not None:
        _validate_command_against_action(
            command_payload,
            action=decision.effective_action,
            requested_mode=decision.requested_mode,
            effective_mode=decision.effective_mode,
            pre_camera=pre_camera,
            resource_id=pre_camera.resource_id,
        )
        if runtime_ack_payload is not None:
            runtime_ack = (
                runtime_ack_payload
                if isinstance(runtime_ack_payload, ActiveVisionRuntimeAckV1)
                else active_vision_runtime_ack_from_payload(
                    runtime_ack_payload,
                    sample_key=sample_key,
                    command_payload=command_payload,
                )
            )
            _validate_ack_against_command(
                runtime_ack,
                command_payload,
                sample_key=sample_key,
            )
        if post_command_camera_state is not None:
            feedback, pose_lineage = active_vision_camera_feedback_from_runtime_state(
                post_command_camera_state,
                pre_command_camera_state=pre_camera,
                evidence_kind=camera_feedback_evidence_kind,
                source_sequence=camera_state_source_sequence,
            )
    elif runtime_ack_payload is not None or post_command_camera_state is not None:
        _fail(
            "runtime_feedback_without_command",
            "runtime ACK or camera state cannot exist without an issued command",
        )

    ack_kind = (
        UNAVAILABLE_EVIDENCE_KIND
        if runtime_ack is None
        else runtime_ack_evidence_kind
    )
    feedback_kind = (
        UNAVAILABLE_EVIDENCE_KIND
        if feedback is None
        else camera_feedback_evidence_kind
    )
    synthetic_fixture = any(
        kind == SYNTHETIC_FIXTURE_EVIDENCE_KIND
        for kind in (
            ack_kind,
            feedback_kind,
            None if pose_lineage is None else pose_lineage.evidence_kind,
        )
    )
    return ActiveVisionA3AdoptionTrace(
        comparison_key=comparison_key,
        scenario_id=scenario_id,
        scale=scale,
        seed=seed,
        window_index=window_index,
        sample_key=sample_key,
        camera_id=camera_id,
        resource_id=pre_camera.resource_id,
        pairing_context_sha256=pairing_context_sha256,
        source_event_log_sha256=source_event_log_sha256,
        policy_evaluated=policy_evaluated,
        policy_evaluated_timestamp=policy_evaluated_timestamp,
        model_fingerprint=model_fingerprint,
        bundle_manifest_sha256=bundle_manifest_sha256,
        bundle_weights_sha256=bundle_weights_sha256,
        implementation_sha256=implementation_sha256,
        source_git_commit=source_git_commit,
        decision=decision,
        pre_command_camera_state=pre_camera,
        issued_command_payload=command_payload,
        runtime_ack=runtime_ack,
        camera_feedback=feedback,
        camera_pose_lineage=pose_lineage,
        runtime_ack_evidence_kind=ack_kind,
        camera_feedback_evidence_kind=feedback_kind,
        synthetic_fixture=synthetic_fixture,
        pose_tolerance_deg=pose_tolerance_deg,
        online_truth_use_count=online_truth_use_count,
        global_track_id_rewrite_count=global_track_id_rewrite_count,
    )


def assemble_active_vision_a3_rule_arm_trace(
    *,
    comparison_key: str,
    scenario_id: str,
    scale: int,
    seed: int,
    window_index: int,
    sample_key: str,
    pairing_context_sha256: str,
    source_event_log_sha256: str,
    snapshot: Any,
    rule_decision: ActiveVisionDecisionV1,
    issued_command: Any,
    runtime_ack_payload: Mapping[str, Any] | ActiveVisionRuntimeAckV1,
    post_command_camera_state: Any,
    runtime_ack_evidence_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
    camera_feedback_evidence_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
    camera_state_source_sequence: int | None = None,
    pose_tolerance_deg: float = 0.25,
    online_truth_use_count: int = 0,
    global_track_id_rewrite_count: int = 0,
) -> ActiveVisionA3RuleArmTrace:
    """Build one independent deterministic R0 trace from runtime events.

    This path deliberately has no model fingerprint, bundle, policy evaluation,
    or candidate adoption input.  Missing command, ACK, or camera feedback is a
    hard rejection rather than an unavailable model trace.
    """

    from .active_vision_contracts import ActiveVisionSnapshotV1

    if not isinstance(snapshot, ActiveVisionSnapshotV1):
        _fail(
            "snapshot_type_invalid",
            "R0 trace assembly requires ActiveVisionSnapshotV1",
        )
    if not isinstance(rule_decision, ActiveVisionDecisionV1):
        _fail(
            "r0_decision_type_invalid",
            "R0 trace assembly requires ActiveVisionDecisionV1",
        )
    _validate_decision(rule_decision)
    _validate_rule_arm_decision(rule_decision)
    versions = (
        snapshot.plan.plan_version,
        snapshot.plan.coalition_version,
        snapshot.communication.communication_version,
    )
    if (
        snapshot.communication.plan_version,
        snapshot.communication.coalition_version,
    ) != versions[:2]:
        _fail(
            "snapshot_version_mismatch",
            "snapshot plan and communication references disagree",
        )
    if (
        rule_decision.plan_version,
        rule_decision.coalition_version,
        rule_decision.communication_version,
    ) != versions:
        _fail(
            "snapshot_decision_version_mismatch",
            "R0 decision versions differ from the active-vision snapshot",
        )
    camera_id = rule_decision.effective_action.camera_id
    try:
        pre_camera = snapshot.camera(camera_id)
    except ValueError:
        _fail(
            "r0_camera_not_in_snapshot",
            "R0 decision camera is absent from the paired exogenous snapshot",
        )
    center_track_ids = {item.global_track_id for item in snapshot.tracks}
    assigned_track_ids = set(snapshot.assigned_target_ids(camera_id))
    target_id = rule_decision.effective_action.target_global_track_id
    if target_id is not None and (
        target_id not in center_track_ids or target_id not in assigned_track_ids
    ):
        _fail(
            "decision_target_not_center_assigned",
            "R0 target is not a center-owned assignment for this camera",
        )
    if snapshot.snapshot_timestamp + _EPS < pre_camera.state_timestamp:
        _fail(
            "snapshot_camera_time_invalid",
            "R0 pre-command camera state follows the snapshot timestamp",
        )
    if issued_command is None:
        _fail(
            "r0_command_missing",
            "R0 trace requires an independently issued deterministic command",
        )
    if runtime_ack_payload is None:
        _fail(
            "r0_runtime_ack_missing",
            "R0 trace requires an independent runtime ACK",
        )
    if post_command_camera_state is None:
        _fail(
            "r0_camera_feedback_missing",
            "R0 trace requires independent post-command camera feedback",
        )

    command_payload = (
        _validated_command_payload(issued_command)
        if isinstance(issued_command, Mapping)
        else camera_observation_command_payload(issued_command)
    )
    _validate_command_against_action(
        command_payload,
        action=rule_decision.effective_action,
        requested_mode=rule_decision.requested_mode,
        effective_mode=rule_decision.effective_mode,
        pre_camera=pre_camera,
        resource_id=pre_camera.resource_id,
    )
    runtime_ack = (
        runtime_ack_payload
        if isinstance(runtime_ack_payload, ActiveVisionRuntimeAckV1)
        else active_vision_runtime_ack_from_payload(
            runtime_ack_payload,
            sample_key=sample_key,
            command_payload=command_payload,
        )
    )
    _validate_ack_against_command(
        runtime_ack,
        command_payload,
        sample_key=sample_key,
    )
    feedback, pose_lineage = active_vision_camera_feedback_from_runtime_state(
        post_command_camera_state,
        pre_command_camera_state=pre_camera,
        evidence_kind=camera_feedback_evidence_kind,
        source_sequence=camera_state_source_sequence,
    )
    return ActiveVisionA3RuleArmTrace(
        comparison_key=comparison_key,
        scenario_id=scenario_id,
        scale=scale,
        seed=seed,
        window_index=window_index,
        sample_key=sample_key,
        camera_id=camera_id,
        resource_id=pre_camera.resource_id,
        pairing_context_sha256=pairing_context_sha256,
        source_event_log_sha256=source_event_log_sha256,
        decision=rule_decision,
        pre_command_camera_state=pre_camera,
        issued_command_payload=command_payload,
        runtime_ack=runtime_ack,
        camera_feedback=feedback,
        camera_pose_lineage=pose_lineage,
        runtime_ack_evidence_kind=runtime_ack_evidence_kind,
        camera_feedback_evidence_kind=camera_feedback_evidence_kind,
        synthetic_fixture=False,
        pose_tolerance_deg=pose_tolerance_deg,
        online_truth_use_count=online_truth_use_count,
        global_track_id_rewrite_count=global_track_id_rewrite_count,
    )


def active_vision_a3_observation_frame(
    *,
    frame_key: str,
    observations: Iterable[CameraLocalTracklet],
    bindings: Iterable[
        CenterTrackBindingDecision | ActiveVisionA3BindingEvidence | Mapping[str, Any]
    ],
    target_global_track_id: str | None,
    center_global_track_ids: Iterable[str],
    plan_version: int,
    coalition_version: int,
    communication_version: int,
    evidence_kind: str,
    source_sequence: int | None = None,
) -> ActiveVisionA3AnonymousObservationFrame:
    """Normalize one anonymous camera frame and center read-only bindings."""

    observation_items = tuple(observations)
    if not observation_items:
        _fail(
            "anonymous_observation_missing",
            "observation frame requires at least one anonymous local tracklet",
        )
    values = tuple(_anonymous_observation_values(item) for item in observation_items)
    camera_ids = {item["camera_id"] for item in values}
    resource_ids = {item["resource_id"] for item in values}
    if len(camera_ids) != 1 or len(resource_ids) != 1:
        _fail(
            "anonymous_observation_membership_mismatch",
            "one observation frame cannot mix cameras or resources",
        )
    measurement_timestamps = {item["measurement_timestamp"] for item in values}
    if len(measurement_timestamps) != 1:
        _fail(
            "anonymous_observation_time_mismatch",
            "one observation frame must use one measurement timestamp",
        )
    arrival_timestamp = max(item["arrival_timestamp"] for item in values)
    allowed_ids = frozenset(
        _token(value, "center_global_track_id")
        for value in center_global_track_ids
    )
    target_id = _optional_token(
        target_global_track_id,
        "observation_frame.target_global_track_id",
    )
    if target_id is not None and target_id not in allowed_ids:
        _fail(
            "observation_frame_target_not_center_owned",
            "target reference is absent from center-owned track candidates",
        )
    normalized_bindings = tuple(
        _binding_evidence(item, allowed_global_track_ids=allowed_ids)
        for item in bindings
    )
    return ActiveVisionA3AnonymousObservationFrame(
        frame_key=frame_key,
        camera_id=next(iter(camera_ids)),
        resource_id=next(iter(resource_ids)),
        measurement_timestamp=next(iter(measurement_timestamps)),
        arrival_timestamp=arrival_timestamp,
        plan_version=plan_version,
        coalition_version=coalition_version,
        communication_version=communication_version,
        target_global_track_id=target_id,
        observed_tracklet_keys=tuple(
            sorted(item["tracklet_key"] for item in values)
        ),
        bindings=normalized_bindings,
        evidence_kind=evidence_kind,
        source_sequence=source_sequence,
    )


def active_vision_a3_zero_detection_frame(
    *,
    frame_key: str,
    camera_id: str,
    resource_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
    plan_version: int,
    coalition_version: int,
    communication_version: int,
    target_global_track_id: str | None,
    center_global_track_ids: Iterable[str],
    evidence_kind: str,
    source_sequence: int,
) -> ActiveVisionA3AnonymousObservationFrame:
    """Record one processed camera frame that produced zero detections."""

    return ActiveVisionA3AnonymousObservationFrame(
        frame_key=frame_key,
        camera_id=camera_id,
        resource_id=resource_id,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        plan_version=plan_version,
        coalition_version=coalition_version,
        communication_version=communication_version,
        target_global_track_id=target_global_track_id,
        observed_tracklet_keys=(),
        bindings=(),
        evidence_kind=evidence_kind,
        source_sequence=source_sequence,
        frame_observation_state=(
            _OBSERVATION_FRAME_PROCESSED_ZERO_DETECTIONS
        ),
        center_global_track_ids=tuple(center_global_track_ids),
        schema_version=(
            ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION
        ),
    )


def assemble_active_vision_a3_physical_observation_window(
    adoption_trace: ActiveVisionA3AdoptionTrace,
    *,
    arm: ActiveVisionA3WindowArm | str,
    observation_frames: Iterable[ActiveVisionA3AnonymousObservationFrame],
    window_start_timestamp: float,
    window_end_timestamp: float,
) -> ActiveVisionA3PhysicalObservationWindow | None:
    """Build a hash-bound physical window; no frames means unavailable."""

    if not isinstance(adoption_trace, ActiveVisionA3AdoptionTrace):
        _fail("assembly_trace_type_invalid", "adoption_trace has an invalid type")
    frames = tuple(observation_frames)
    if not frames:
        return None
    if (
        adoption_trace.issued_command_payload is None
        or adoption_trace.runtime_ack is None
        or adoption_trace.camera_feedback is None
        or adoption_trace.camera_pose_lineage is None
    ):
        return None
    arm_value = _enum(ActiveVisionA3WindowArm, arm, "window.arm")
    command_source = adoption_trace.command_source
    if command_source is None:
        return None
    ordered = tuple(
        sorted(
            frames,
            key=lambda item: (
                item.measurement_timestamp,
                item.arrival_timestamp,
                item.frame_key,
            ),
        )
    )
    evidence_kinds = {item.evidence_kind for item in ordered}
    if len(evidence_kinds) != 1:
        _fail(
            "physical_window_frame_provenance_mismatch",
            "physical window cannot mix runtime and synthetic frames",
        )
    outcome = _outcome_from_observation_frames(ordered)
    return ActiveVisionA3PhysicalObservationWindow(
        arm=arm_value,
        comparison_key=adoption_trace.comparison_key,
        scenario_id=adoption_trace.scenario_id,
        scale=adoption_trace.scale,
        seed=adoption_trace.seed,
        window_index=adoption_trace.window_index,
        sample_key=adoption_trace.sample_key,
        camera_id=adoption_trace.camera_id,
        resource_id=adoption_trace.resource_id,
        target_global_track_id=adoption_trace.target_global_track_id,
        pairing_context_sha256=adoption_trace.pairing_context_sha256,
        source_event_log_sha256=adoption_trace.source_event_log_sha256,
        command_source=command_source,
        effective_action=adoption_trace.decision.effective_action,
        pre_command_camera_state=adoption_trace.pre_command_camera_state,
        issued_command_payload=adoption_trace.issued_command_payload,
        runtime_ack=adoption_trace.runtime_ack,
        camera_feedback=adoption_trace.camera_feedback,
        camera_pose_lineage=adoption_trace.camera_pose_lineage,
        runtime_ack_evidence_kind=adoption_trace.runtime_ack_evidence_kind,
        camera_feedback_evidence_kind=(
            adoption_trace.camera_feedback_evidence_kind
        ),
        observation_evidence_kind=next(iter(evidence_kinds)),
        synthetic_fixture=(
            adoption_trace.synthetic_fixture
            or SYNTHETIC_FIXTURE_EVIDENCE_KIND in evidence_kinds
        ),
        pose_tolerance_deg=adoption_trace.pose_tolerance_deg,
        window_start_timestamp=window_start_timestamp,
        window_end_timestamp=window_end_timestamp,
        first_measurement_timestamp=ordered[0].measurement_timestamp,
        last_measurement_timestamp=ordered[-1].measurement_timestamp,
        first_arrival_timestamp=min(
            item.arrival_timestamp for item in ordered
        ),
        last_arrival_timestamp=max(
            item.arrival_timestamp for item in ordered
        ),
        observation_frames=ordered,
        outcome=outcome,
        adoption_trace_sha256=(
            adoption_trace.trace_sha256
            if arm_value is ActiveVisionA3WindowArm.A3
            else None
        ),
        online_truth_use_count=adoption_trace.online_truth_use_count,
        global_track_id_rewrite_count=(
            adoption_trace.global_track_id_rewrite_count
        ),
    )


def assemble_active_vision_a3_rule_arm_physical_observation_window(
    rule_arm_trace: ActiveVisionA3RuleArmTrace,
    *,
    observation_frames: Iterable[ActiveVisionA3AnonymousObservationFrame],
    window_start_timestamp: float,
    window_end_timestamp: float,
) -> ActiveVisionA3PhysicalObservationWindow | None:
    """Build an R0 window only from an independent deterministic rule trace."""

    if not isinstance(rule_arm_trace, ActiveVisionA3RuleArmTrace):
        _fail(
            "r0_assembly_trace_type_invalid",
            "rule_arm_trace has an invalid type",
        )
    frames = tuple(observation_frames)
    if not frames:
        return None
    ordered = tuple(
        sorted(
            frames,
            key=lambda item: (
                item.measurement_timestamp,
                item.arrival_timestamp,
                item.frame_key,
            ),
        )
    )
    if any(
        not isinstance(item, ActiveVisionA3AnonymousObservationFrame)
        for item in ordered
    ):
        _fail(
            "physical_window_frames_invalid",
            "R0 physical window requires anonymous observation frames",
        )
    evidence_kinds = {item.evidence_kind for item in ordered}
    if evidence_kinds != {RUNTIME_OBSERVED_EVIDENCE_KIND}:
        _fail(
            "r0_observation_runtime_evidence_required",
            "R0 window requires independent runtime observation frames",
        )
    outcome = _outcome_from_observation_frames(ordered)
    return ActiveVisionA3PhysicalObservationWindow(
        arm=ActiveVisionA3WindowArm.R0,
        comparison_key=rule_arm_trace.comparison_key,
        scenario_id=rule_arm_trace.scenario_id,
        scale=rule_arm_trace.scale,
        seed=rule_arm_trace.seed,
        window_index=rule_arm_trace.window_index,
        sample_key=rule_arm_trace.sample_key,
        camera_id=rule_arm_trace.camera_id,
        resource_id=rule_arm_trace.resource_id,
        target_global_track_id=rule_arm_trace.target_global_track_id,
        pairing_context_sha256=rule_arm_trace.pairing_context_sha256,
        source_event_log_sha256=rule_arm_trace.source_event_log_sha256,
        command_source=ActiveVisionA3CommandSource.DETERMINISTIC_RULE,
        effective_action=rule_arm_trace.decision.effective_action,
        pre_command_camera_state=rule_arm_trace.pre_command_camera_state,
        issued_command_payload=rule_arm_trace.issued_command_payload,
        runtime_ack=rule_arm_trace.runtime_ack,
        camera_feedback=rule_arm_trace.camera_feedback,
        camera_pose_lineage=rule_arm_trace.camera_pose_lineage,
        runtime_ack_evidence_kind=rule_arm_trace.runtime_ack_evidence_kind,
        camera_feedback_evidence_kind=(
            rule_arm_trace.camera_feedback_evidence_kind
        ),
        observation_evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        synthetic_fixture=False,
        pose_tolerance_deg=rule_arm_trace.pose_tolerance_deg,
        window_start_timestamp=window_start_timestamp,
        window_end_timestamp=window_end_timestamp,
        first_measurement_timestamp=ordered[0].measurement_timestamp,
        last_measurement_timestamp=ordered[-1].measurement_timestamp,
        first_arrival_timestamp=min(
            item.arrival_timestamp for item in ordered
        ),
        last_arrival_timestamp=max(
            item.arrival_timestamp for item in ordered
        ),
        observation_frames=ordered,
        outcome=outcome,
        adoption_trace_sha256=None,
        online_truth_use_count=rule_arm_trace.online_truth_use_count,
        global_track_id_rewrite_count=(
            rule_arm_trace.global_track_id_rewrite_count
        ),
    )


def assemble_active_vision_a3_evidence(
    adoption_trace: ActiveVisionA3AdoptionTrace,
    *,
    candidate_window: ActiveVisionA3PhysicalObservationWindow | None,
    same_key_r0_window: ActiveVisionA3PhysicalObservationWindow | None,
) -> ActiveVisionA3BenefitAuditInput:
    """Assemble one immutable A3-to-R0 pair without granting runtime authority."""

    if not isinstance(adoption_trace, ActiveVisionA3AdoptionTrace):
        _fail("assembly_trace_type_invalid", "adoption_trace has an invalid type")
    blockers = list(adoption_trace.adoption_blockers)

    if candidate_window is None:
        blockers.append("candidate_physical_window_missing")
    else:
        _validate_candidate_window(adoption_trace, candidate_window)
        if not candidate_window.runtime_physical_chain_complete:
            blockers.append("candidate_physical_chain_incomplete")
        if not candidate_window.outcome.benefit_outcome_available:
            blockers.append("candidate_association_or_coverage_outcome_unavailable")

    if same_key_r0_window is None:
        blockers.append("same_key_r0_window_missing")
    else:
        if candidate_window is not None:
            _validate_same_key_pair(candidate_window, same_key_r0_window)
        elif same_key_r0_window.arm is not ActiveVisionA3WindowArm.R0:
            _fail("r0_arm_invalid", "same-key reference is not an R0 window")
        if not same_key_r0_window.runtime_physical_chain_complete:
            blockers.append("r0_physical_chain_incomplete")
        if not same_key_r0_window.outcome.benefit_outcome_available:
            blockers.append("r0_association_or_coverage_outcome_unavailable")

    blockers = list(dict.fromkeys(blockers))
    outcomes_available = bool(
        candidate_window is not None
        and same_key_r0_window is not None
        and candidate_window.outcome.benefit_outcome_available
        and same_key_r0_window.outcome.benefit_outcome_available
    )
    eligible = not blockers
    return ActiveVisionA3BenefitAuditInput(
        adoption_trace=adoption_trace,
        candidate_window=candidate_window,
        same_key_r0_window=same_key_r0_window,
        blocker_codes=tuple(blockers),
        model_action_adopted=adoption_trace.model_action_adopted,
        candidate_physical_window_available=candidate_window is not None,
        same_key_r0_window_available=same_key_r0_window is not None,
        association_coverage_outcomes_available=outcomes_available,
        d6_benefit_audit_eligible=eligible,
        permissions=ActiveVisionA3AuditPermissions(
            d6_benefit_audit_input_allowed=eligible,
        ),
    )


def assemble_active_vision_a3_paired_evidence(
    adoption_trace: ActiveVisionA3AdoptionTrace,
    *,
    candidate_window: ActiveVisionA3PhysicalObservationWindow | None,
    same_key_r0_windows: Iterable[ActiveVisionA3PhysicalObservationWindow],
) -> ActiveVisionA3BenefitAuditInput:
    """Require a unique independent R0 window before assembling D6 input."""

    windows = tuple(same_key_r0_windows)
    if any(
        not isinstance(item, ActiveVisionA3PhysicalObservationWindow)
        for item in windows
    ):
        _fail(
            "same_key_r0_window_type_invalid",
            "R0 candidates must use ActiveVisionA3PhysicalObservationWindow",
        )
    if len(windows) > 1:
        _fail(
            "same_key_r0_duplicate",
            "exactly one R0 physical window is allowed for a comparison key",
        )
    return assemble_active_vision_a3_evidence(
        adoption_trace,
        candidate_window=candidate_window,
        same_key_r0_window=None if not windows else windows[0],
    )


def attempt_active_vision_a3_pairing(
    adoption_trace: ActiveVisionA3AdoptionTrace | Mapping[str, Any],
    *,
    candidate_window: (
        ActiveVisionA3PhysicalObservationWindow | Mapping[str, Any] | None
    ),
    same_key_r0_windows: Iterable[
        ActiveVisionA3PhysicalObservationWindow | Mapping[str, Any]
    ],
    candidate_stage_evidence: (
        ActiveVisionA3CandidateStageEvidence | Mapping[str, Any] | None
    ) = None,
) -> ActiveVisionA3PairingDisposition:
    """Classify one candidate pairing attempt without changing runtime state.

    The first applicable reason in the documented fail-closed precedence is
    returned as ``reason_code``.  Existing lower-level blockers remain in
    ``detail_codes``.  Missing candidate windows stay coarse unless the caller
    provides a hash-bound, runtime-observed stage inventory.  The optional
    inventory is never reconstructed from later windows or truth labels.
    """

    try:
        trace = _coerce_a3_adoption_trace(adoption_trace)
    except ActiveVisionA3EvidenceError as exc:
        return _pairing_disposition(
            None,
            reason=ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID,
            detail_codes=(exc.code,),
        )

    try:
        stage_evidence = _coerce_a3_candidate_stage_evidence(
            candidate_stage_evidence
        )
        if stage_evidence is not None:
            _validate_candidate_stage_evidence_against_trace(
                stage_evidence,
                trace,
            )
    except ActiveVisionA3EvidenceError as exc:
        return _pairing_disposition(
            trace,
            reason=ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID,
            detail_codes=(exc.code,),
        )

    if not trace.model_action_adopted:
        return _pairing_disposition(
            trace,
            reason=(
                ActiveVisionA3PairingDispositionCode.MODEL_ACTION_NOT_ADOPTED
            ),
            detail_codes=trace.adoption_blockers,
            candidate_stage_evidence=stage_evidence,
        )

    try:
        candidate = _coerce_a3_physical_window(
            candidate_window,
            name="candidate_window",
        )
    except ActiveVisionA3EvidenceError as exc:
        return _pairing_disposition(
            trace,
            reason=ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID,
            detail_codes=(exc.code,),
        )

    try:
        _validate_candidate_stage_evidence_against_window(
            stage_evidence,
            candidate,
        )
    except ActiveVisionA3EvidenceError as exc:
        return _pairing_disposition(
            trace,
            reason=ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID,
            detail_codes=(exc.code,),
        )

    try:
        r0_inputs = tuple(same_key_r0_windows)
    except TypeError:
        return _pairing_disposition(
            trace,
            reason=ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID,
            detail_codes=("same_key_r0_windows_not_iterable",),
        )

    if candidate is None:
        details = ["candidate_physical_window_missing"]
        if not r0_inputs:
            details.append("same_key_r0_window_missing")
        elif len(r0_inputs) > 1:
            details.append("same_key_r0_duplicate")
        return _pairing_disposition(
            trace,
            reason=(
                ActiveVisionA3PairingDispositionCode.CANDIDATE_PHYSICAL_WINDOW_MISSING
            ),
            detail_codes=tuple(details),
            candidate_stage_evidence=stage_evidence,
        )

    if not r0_inputs:
        return _pairing_disposition(
            trace,
            reason=(
                ActiveVisionA3PairingDispositionCode.SAME_KEY_R0_WINDOW_MISSING
            ),
            detail_codes=("same_key_r0_window_missing",),
            candidate_stage_evidence=stage_evidence,
        )
    if len(r0_inputs) > 1:
        return _pairing_disposition(
            trace,
            reason=(
                ActiveVisionA3PairingDispositionCode.SAME_KEY_R0_DUPLICATE_OR_AMBIGUOUS
            ),
            detail_codes=("same_key_r0_duplicate",),
            candidate_stage_evidence=stage_evidence,
        )

    try:
        r0_window = _coerce_a3_physical_window(
            r0_inputs[0],
            name="same_key_r0_window",
        )
        if r0_window is None:
            return _pairing_disposition(
                trace,
                reason=(
                    ActiveVisionA3PairingDispositionCode.SAME_KEY_R0_WINDOW_MISSING
                ),
                detail_codes=("same_key_r0_window_missing",),
                candidate_stage_evidence=stage_evidence,
            )
        paired_evidence = assemble_active_vision_a3_paired_evidence(
            trace,
            candidate_window=candidate,
            same_key_r0_windows=(r0_window,),
        )
    except ActiveVisionA3EvidenceError as exc:
        reason = (
            ActiveVisionA3PairingDispositionCode.PAIRING_KEY_OR_CONFIGURATION_MISMATCH
            if exc.code in _PAIRING_KEY_OR_CONFIGURATION_ERROR_CODES
            else ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID
        )
        return _pairing_disposition(
            trace,
            reason=reason,
            detail_codes=(exc.code,),
            candidate_stage_evidence=stage_evidence,
        )

    if paired_evidence.d6_benefit_audit_eligible:
        return _pairing_disposition(
            trace,
            reason=ActiveVisionA3PairingDispositionCode.PAIRABLE,
            detail_codes=(),
            paired_evidence=paired_evidence,
            candidate_stage_evidence=stage_evidence,
        )

    reason = _pairing_reason_from_blockers(paired_evidence.blocker_codes)
    return _pairing_disposition(
        trace,
        reason=reason,
        detail_codes=paired_evidence.blocker_codes,
        candidate_stage_evidence=stage_evidence,
    )


def validate_active_vision_a3_evidence(
    payload: Mapping[str, Any],
) -> ActiveVisionA3BenefitAuditInput:
    """Strictly reconstruct and recompute an A3 audit input."""

    _assert_truth_free(payload)
    _expect_fields(
        payload,
        {
            "schema_version",
            "adoption_trace",
            "candidate_window",
            "same_key_r0_window",
            "blocker_codes",
            "model_action_adopted",
            "candidate_physical_window_available",
            "same_key_r0_window_available",
            "association_coverage_outcomes_available",
            "d6_benefit_audit_eligible",
            "permissions",
            "content_sha256",
        },
        "audit_input",
    )
    if payload["schema_version"] != ACTIVE_VISION_A3_AUDIT_INPUT_SCHEMA_VERSION:
        _fail("audit_input_schema_mismatch", "unsupported A3 audit input schema")
    trace = ActiveVisionA3AdoptionTrace.from_mapping(
        _mapping(payload["adoption_trace"], "audit_input.adoption_trace")
    )
    candidate = _optional_window(payload["candidate_window"], "candidate_window")
    r0_window = _optional_window(payload["same_key_r0_window"], "same_key_r0_window")
    expected = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=candidate,
        same_key_r0_window=r0_window,
    )
    if expected.to_dict() != dict(payload):
        _fail(
            "audit_input_recomputation_mismatch",
            "stored eligibility, blockers, permissions, or content hash differ from recomputation",
        )
    return expected


def validate_active_vision_a3_pairing_disposition(
    payload: Mapping[str, Any],
) -> ActiveVisionA3PairingDisposition:
    """Strictly reload a persisted disposition without proving its causality.

    This validator proves schema, JSON type, digest, permission, and nested
    evidence consistency.  It cannot independently prove that the stored
    reason is the true physical or causal explanation for an unavailable pair.
    """

    payload = _mapping(payload, "pairing_disposition")
    _assert_truth_free(payload)
    schema_version = payload.get("schema_version")
    if type(schema_version) is not str:
        _fail(
            "pairing_disposition_field_type_invalid",
            "schema_version must be a string",
        )
    if schema_version not in {
        ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION,
        ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION,
    }:
        _fail(
            "pairing_disposition_schema_mismatch",
            "unsupported A3 pairing disposition schema",
        )
    fields = {
        "schema_version",
        "comparison_key",
        "scenario_id",
        "scale",
        "seed",
        "window_index",
        "sample_key",
        "camera_id",
        "resource_id",
        "target_global_track_id",
        "pairing_context_sha256",
        "adoption_trace_sha256",
        "pairable",
        "reason_code",
        "detail_codes",
        "paired_evidence",
        "content_sha256",
    }
    if schema_version == ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION:
        fields.update(
            {
                "candidate_stage_reason_codes",
                "candidate_stage_evidence",
            }
        )
    _expect_fields(
        payload,
        fields,
        "pairing_disposition",
    )
    for name in (
        "comparison_key",
        "scenario_id",
        "sample_key",
        "camera_id",
        "resource_id",
        "target_global_track_id",
        "pairing_context_sha256",
        "adoption_trace_sha256",
    ):
        value = payload[name]
        if value is not None and type(value) is not str:
            _fail(
                "pairing_disposition_field_type_invalid",
                f"{name} must be a string or null",
            )
    for name in ("scale", "seed", "window_index"):
        value = payload[name]
        if value is not None and type(value) is not int:
            _fail(
                "pairing_disposition_field_type_invalid",
                f"{name} must be an integer or null",
            )
    if type(payload["reason_code"]) is not str:
        _fail(
            "pairing_disposition_field_type_invalid",
            "reason_code must be a string",
        )
    if type(payload["content_sha256"]) is not str:
        _fail(
            "pairing_disposition_field_type_invalid",
            "content_sha256 must be a string",
        )
    pairable = _strict_bool(
        payload["pairable"],
        "pairing_disposition.pairable",
    )
    details_payload = payload["detail_codes"]
    if type(details_payload) is not list or any(
        type(value) is not str for value in details_payload
    ):
        _fail(
            "pairing_disposition_details_type_invalid",
            "detail_codes must be a JSON list of strings",
        )

    paired_payload = payload["paired_evidence"]
    paired_evidence: ActiveVisionA3BenefitAuditInput | None
    if pairable:
        if not isinstance(paired_payload, Mapping):
            _fail(
                "pairing_disposition_evidence_missing",
                "pairable disposition requires a paired evidence object",
            )
        paired_evidence = validate_active_vision_a3_evidence(paired_payload)
    else:
        if paired_payload is not None:
            _fail(
                "pairing_disposition_evidence_forbidden",
                "unpairable disposition cannot carry paired evidence",
            )
        paired_evidence = None

    stage_reasons_payload: list[str]
    stage_evidence: ActiveVisionA3CandidateStageEvidence | None
    if schema_version == ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION:
        raw_stage_reasons = payload["candidate_stage_reason_codes"]
        if type(raw_stage_reasons) is not list or any(
            type(value) is not str for value in raw_stage_reasons
        ):
            _fail(
                "pairing_disposition_stage_reasons_type_invalid",
                "candidate_stage_reason_codes must be a JSON list of strings",
            )
        stage_reasons_payload = list(raw_stage_reasons)
        raw_stage_evidence = payload["candidate_stage_evidence"]
        if raw_stage_evidence is None:
            stage_evidence = None
        elif isinstance(raw_stage_evidence, Mapping):
            stage_evidence = ActiveVisionA3CandidateStageEvidence.from_mapping(
                raw_stage_evidence
            )
        else:
            _fail(
                "pairing_disposition_stage_evidence_type_invalid",
                "candidate_stage_evidence must be an object or null",
            )
    else:
        stage_reasons_payload = []
        stage_evidence = None

    expected = ActiveVisionA3PairingDisposition(
        comparison_key=payload["comparison_key"],
        scenario_id=payload["scenario_id"],
        scale=payload["scale"],
        seed=payload["seed"],
        window_index=payload["window_index"],
        sample_key=payload["sample_key"],
        camera_id=payload["camera_id"],
        resource_id=payload["resource_id"],
        target_global_track_id=payload["target_global_track_id"],
        pairing_context_sha256=payload["pairing_context_sha256"],
        adoption_trace_sha256=payload["adoption_trace_sha256"],
        pairable=pairable,
        reason_code=payload["reason_code"],
        detail_codes=tuple(details_payload),
        paired_evidence=paired_evidence,
        candidate_stage_reason_codes=tuple(stage_reasons_payload),
        candidate_stage_evidence=stage_evidence,
        schema_version=schema_version,
    )
    stored_hash = _digest(
        payload["content_sha256"],
        "pairing_disposition.content_sha256",
    )
    if expected.content_sha256 != stored_hash:
        _fail(
            "pairing_disposition_hash_mismatch",
            "pairing disposition content hash differs from recomputation",
        )
    if expected.to_dict() != dict(payload):
        _fail(
            "pairing_disposition_recomputation_mismatch",
            "stored disposition fields differ from strict reconstruction",
        )
    return expected


def validate_active_vision_a3_candidate_stage_evidence(
    payload: Mapping[str, Any],
) -> ActiveVisionA3CandidateStageEvidence:
    """Strictly reload one persisted candidate-stage evidence artifact."""

    return ActiveVisionA3CandidateStageEvidence.from_mapping(payload)


def load_active_vision_a3_evidence(
    path: str | Path,
) -> ActiveVisionA3BenefitAuditInput:
    """Load one strict A3 audit input JSON file."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("audit_input_file_invalid", f"cannot read A3 audit input: {type(exc).__name__}")
    if not isinstance(payload, Mapping):
        _fail("audit_input_type_invalid", "A3 audit input root must be an object")
    return validate_active_vision_a3_evidence(payload)


def _coerce_a3_adoption_trace(
    value: ActiveVisionA3AdoptionTrace | Mapping[str, Any],
) -> ActiveVisionA3AdoptionTrace:
    if isinstance(value, ActiveVisionA3AdoptionTrace):
        return value
    if isinstance(value, Mapping):
        return ActiveVisionA3AdoptionTrace.from_mapping(value)
    _fail(
        "pairing_trace_contract_invalid",
        "pairing attempt requires an A3 adoption trace or its strict mapping",
    )


def _coerce_a3_physical_window(
    value: ActiveVisionA3PhysicalObservationWindow | Mapping[str, Any] | None,
    *,
    name: str,
) -> ActiveVisionA3PhysicalObservationWindow | None:
    if value is None:
        return None
    if isinstance(value, ActiveVisionA3PhysicalObservationWindow):
        return value
    if isinstance(value, Mapping):
        return ActiveVisionA3PhysicalObservationWindow.from_mapping(value)
    _fail(
        "pairing_window_contract_invalid",
        f"{name} must use ActiveVisionA3PhysicalObservationWindow or its strict mapping",
    )


def _coerce_a3_candidate_stage_evidence(
    value: ActiveVisionA3CandidateStageEvidence | Mapping[str, Any] | None,
) -> ActiveVisionA3CandidateStageEvidence | None:
    if value is None:
        return None
    if isinstance(value, ActiveVisionA3CandidateStageEvidence):
        return value
    if isinstance(value, Mapping):
        return ActiveVisionA3CandidateStageEvidence.from_mapping(value)
    _fail(
        "candidate_stage_evidence_contract_invalid",
        "candidate-stage evidence must use its strict DTO or mapping",
    )


def _validate_candidate_stage_evidence_against_trace(
    evidence: ActiveVisionA3CandidateStageEvidence,
    trace: ActiveVisionA3AdoptionTrace,
) -> None:
    expected_identity = (
        trace.comparison_key,
        trace.scenario_id,
        trace.scale,
        trace.seed,
        trace.window_index,
        trace.sample_key,
        trace.camera_id,
        trace.resource_id,
        trace.pairing_context_sha256,
        trace.trace_sha256,
        trace.source_event_log_sha256,
    )
    if evidence.comparison_identity != expected_identity:
        _fail(
            "candidate_stage_trace_reference_mismatch",
            "candidate-stage evidence refers to a different adoption trace",
        )

    command = trace.issued_command_payload
    if command is None:
        if (
            evidence.command_issued_timestamp is not None
            or evidence.command_expires_timestamp is not None
        ):
            _fail(
                "candidate_stage_command_trace_mismatch",
                "candidate-stage command event is absent from the adoption trace",
            )
    else:
        for evidence_value, trace_value in (
            (evidence.command_issued_timestamp, command["issued_timestamp"]),
            (evidence.command_expires_timestamp, command["expires_timestamp"]),
        ):
            if evidence_value is None or not math.isclose(
                evidence_value,
                float(trace_value),
                rel_tol=0.0,
                abs_tol=_EPS,
            ):
                _fail(
                    "candidate_stage_command_trace_mismatch",
                    "candidate-stage command timestamps differ from the adoption trace",
                )

    ack = trace.runtime_ack
    if ack is not None:
        if evidence.runtime_ack_timestamp is None or not math.isclose(
            evidence.runtime_ack_timestamp,
            ack.ack_timestamp,
            rel_tol=0.0,
            abs_tol=_EPS,
        ):
            _fail(
                "candidate_stage_ack_trace_mismatch",
                "candidate-stage ACK timestamp differs from the adoption trace",
            )
        if evidence.runtime_ack_applied != trace.runtime_ack_applied:
            _fail(
                "candidate_stage_ack_trace_mismatch",
                "candidate-stage ACK state differs from the adoption trace",
            )
    elif (
        evidence.runtime_ack_timestamp is not None
        and evidence.runtime_ack_applied is True
        and evidence.command_issued_timestamp is not None
        and evidence.command_expires_timestamp is not None
        and evidence.command_issued_timestamp - _EPS
        <= evidence.runtime_ack_timestamp
        <= evidence.command_expires_timestamp + _EPS
    ):
        _fail(
            "candidate_stage_ack_trace_mismatch",
            "valid applied ACK evidence is absent from the adoption trace",
        )

    feedback = trace.camera_feedback
    if feedback is not None:
        if evidence.camera_feedback_timestamp is None or not math.isclose(
            evidence.camera_feedback_timestamp,
            feedback.camera_state.state_timestamp,
            rel_tol=0.0,
            abs_tol=_EPS,
        ):
            _fail(
                "candidate_stage_feedback_trace_mismatch",
                "candidate-stage camera feedback differs from the adoption trace",
            )
    elif (
        evidence.camera_feedback_timestamp is not None
        and evidence.runtime_ack_timestamp is not None
        and evidence.runtime_ack_applied is True
        and evidence.command_issued_timestamp is not None
        and evidence.command_expires_timestamp is not None
        and evidence.command_issued_timestamp - _EPS
        <= evidence.runtime_ack_timestamp
        <= evidence.command_expires_timestamp + _EPS
        and evidence.camera_feedback_timestamp + _EPS
        >= evidence.runtime_ack_timestamp
    ):
        _fail(
            "candidate_stage_feedback_trace_mismatch",
            "valid post-ACK camera feedback is absent from the adoption trace",
        )


def _validate_candidate_stage_evidence_against_window(
    evidence: ActiveVisionA3CandidateStageEvidence | None,
    candidate_window: ActiveVisionA3PhysicalObservationWindow | None,
) -> None:
    if evidence is None:
        return
    status = evidence.physical_window_status
    if candidate_window is None:
        if status is ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE:
            _fail(
                "candidate_stage_window_presence_mismatch",
                "stage evidence reports a complete candidate window that is unavailable",
            )
        return
    if status in {
        ActiveVisionA3CandidatePhysicalWindowStatus.MISSING,
        ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE,
    }:
        _fail(
            "candidate_stage_window_presence_mismatch",
            "stage evidence reports a failed window while a candidate window exists",
        )
    if _candidate_stage_reason_codes(evidence):
        _fail(
            "candidate_stage_window_failure_mismatch",
            "candidate window exists despite explicit failed-stage evidence",
        )
    if evidence.observation_inventory_complete:
        comparisons = (
            (
                evidence.anonymous_observation_frame_count,
                len(candidate_window.observation_frames),
            ),
            (
                evidence.first_measurement_timestamp,
                candidate_window.first_measurement_timestamp,
            ),
            (
                evidence.last_measurement_timestamp,
                candidate_window.last_measurement_timestamp,
            ),
            (
                evidence.first_arrival_timestamp,
                candidate_window.first_arrival_timestamp,
            ),
            (
                evidence.last_arrival_timestamp,
                candidate_window.last_arrival_timestamp,
            ),
        )
        for actual, expected in comparisons:
            if isinstance(expected, int):
                matches = actual == expected
            else:
                matches = actual is not None and math.isclose(
                    float(actual),
                    float(expected),
                    rel_tol=0.0,
                    abs_tol=_EPS,
                )
            if not matches:
                _fail(
                    "candidate_stage_observation_window_mismatch",
                    "candidate-stage observation inventory differs from the window",
                )


def _candidate_stage_reason_codes(
    evidence: ActiveVisionA3CandidateStageEvidence,
) -> tuple[ActiveVisionA3CandidateStageReasonCode, ...]:
    reasons: list[ActiveVisionA3CandidateStageReasonCode] = []
    runtime_complete = evidence.runtime_event_inventory_complete
    observation_complete = evidence.observation_inventory_complete
    issued = evidence.command_issued_timestamp
    expires = evidence.command_expires_timestamp
    ack = evidence.runtime_ack_timestamp
    feedback = evidence.camera_feedback_timestamp

    if runtime_complete and ack is None:
        reasons.append(ActiveVisionA3CandidateStageReasonCode.RUNTIME_ACK_MISSING)
    if (
        runtime_complete
        and ack is not None
        and evidence.runtime_ack_applied is False
    ):
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.RUNTIME_CONFIRMATION_MISSING
        )
    if runtime_complete and issued is not None and expires is not None:
        if (
            ack is not None
            and ack > expires + _EPS
            or ack is None
            and evidence.inventory_end_timestamp > expires + _EPS
        ):
            reasons.append(
                ActiveVisionA3CandidateStageReasonCode.COMMAND_WINDOW_EXPIRED
            )

    runtime_timing_mismatch = False
    if runtime_complete and issued is not None:
        runtime_timing_mismatch = (
            issued + _EPS < evidence.inventory_start_timestamp
            or issued > evidence.inventory_end_timestamp + _EPS
        )
    if runtime_complete and ack is not None:
        runtime_timing_mismatch = runtime_timing_mismatch or (
            issued is not None and ack + _EPS < issued
        )
        runtime_timing_mismatch = runtime_timing_mismatch or (
            ack + _EPS < evidence.inventory_start_timestamp
            or ack > evidence.inventory_end_timestamp + _EPS
        )
    if runtime_complete and feedback is not None:
        runtime_timing_mismatch = runtime_timing_mismatch or (
            issued is not None and feedback + _EPS < issued
        )
        runtime_timing_mismatch = runtime_timing_mismatch or (
            ack is not None and feedback + _EPS < ack
        )
        runtime_timing_mismatch = runtime_timing_mismatch or (
            feedback + _EPS < evidence.inventory_start_timestamp
            or feedback > evidence.inventory_end_timestamp + _EPS
        )

    observation_timing_mismatch = False
    frame_count = evidence.anonymous_observation_frame_count
    if observation_complete and frame_count is not None and frame_count > 0:
        first_measurement = float(evidence.first_measurement_timestamp)
        last_measurement = float(evidence.last_measurement_timestamp)
        first_arrival = float(evidence.first_arrival_timestamp)
        last_arrival = float(evidence.last_arrival_timestamp)
        observation_timing_mismatch = (
            first_measurement > last_measurement + _EPS
            or first_arrival > last_arrival + _EPS
            or first_arrival + _EPS < first_measurement
            or last_arrival + _EPS < last_measurement
        )
        observation_timing_mismatch = observation_timing_mismatch or (
            runtime_complete
            and feedback is not None
            and first_measurement + _EPS < feedback
        )
        observation_timing_mismatch = observation_timing_mismatch or (
            first_arrival + _EPS < evidence.inventory_start_timestamp
            or last_arrival > evidence.inventory_end_timestamp + _EPS
        )
    if runtime_timing_mismatch or observation_timing_mismatch:
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.COMMAND_TIMING_MISMATCH
        )

    if runtime_complete and feedback is None:
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.CAMERA_FEEDBACK_MISSING
        )
    if observation_complete and frame_count == 0:
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_MISSING
    )
    if (
        observation_complete
        and frame_count is not None
        and frame_count > 0
        and evidence.physical_window_status
        is ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
    ):
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_INCOMPLETE
    )
    if (
        runtime_complete
        and observation_complete
        and evidence.physical_window_status
        is ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
    ):
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.PHYSICAL_WINDOW_CONFIRMED_MISSING
        )
    elif (
        runtime_complete
        and observation_complete
        and evidence.physical_window_status
        is ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
    ):
        reasons.append(
            ActiveVisionA3CandidateStageReasonCode.PHYSICAL_WINDOW_INCOMPLETE
        )
    return tuple(dict.fromkeys(reasons))


def _pairing_disposition(
    trace: ActiveVisionA3AdoptionTrace | None,
    *,
    reason: ActiveVisionA3PairingDispositionCode,
    detail_codes: Iterable[str],
    paired_evidence: ActiveVisionA3BenefitAuditInput | None = None,
    candidate_stage_evidence: ActiveVisionA3CandidateStageEvidence | None = None,
) -> ActiveVisionA3PairingDisposition:
    details = tuple(dict.fromkeys(str(value) for value in detail_codes))
    stage_reasons = (
        ()
        if candidate_stage_evidence is None
        else _candidate_stage_reason_codes(candidate_stage_evidence)
    )
    if trace is None:
        return ActiveVisionA3PairingDisposition(
            comparison_key=None,
            scenario_id=None,
            scale=None,
            seed=None,
            window_index=None,
            sample_key=None,
            camera_id=None,
            resource_id=None,
            target_global_track_id=None,
            pairing_context_sha256=None,
            adoption_trace_sha256=None,
            pairable=reason is ActiveVisionA3PairingDispositionCode.PAIRABLE,
            reason_code=reason,
            detail_codes=details,
            paired_evidence=paired_evidence,
            candidate_stage_reason_codes=stage_reasons,
            candidate_stage_evidence=candidate_stage_evidence,
        )
    return ActiveVisionA3PairingDisposition(
        comparison_key=trace.comparison_key,
        scenario_id=trace.scenario_id,
        scale=trace.scale,
        seed=trace.seed,
        window_index=trace.window_index,
        sample_key=trace.sample_key,
        camera_id=trace.camera_id,
        resource_id=trace.resource_id,
        target_global_track_id=trace.target_global_track_id,
        pairing_context_sha256=trace.pairing_context_sha256,
        adoption_trace_sha256=trace.trace_sha256,
        pairable=reason is ActiveVisionA3PairingDispositionCode.PAIRABLE,
        reason_code=reason,
        detail_codes=details,
        paired_evidence=paired_evidence,
        candidate_stage_reason_codes=stage_reasons,
        candidate_stage_evidence=candidate_stage_evidence,
    )


def _pairing_reason_from_blockers(
    blocker_codes: Iterable[str],
) -> ActiveVisionA3PairingDispositionCode:
    blockers = frozenset(str(value) for value in blocker_codes)
    if "candidate_physical_window_missing" in blockers:
        return (
            ActiveVisionA3PairingDispositionCode.CANDIDATE_PHYSICAL_WINDOW_MISSING
        )
    if "same_key_r0_window_missing" in blockers:
        return ActiveVisionA3PairingDispositionCode.SAME_KEY_R0_WINDOW_MISSING
    if "candidate_physical_chain_incomplete" in blockers:
        return (
            ActiveVisionA3PairingDispositionCode.CANDIDATE_PHYSICAL_EVIDENCE_INCOMPLETE
        )
    if "r0_physical_chain_incomplete" in blockers:
        return ActiveVisionA3PairingDispositionCode.R0_PHYSICAL_EVIDENCE_INCOMPLETE
    if blockers.intersection(
        {
            "candidate_association_or_coverage_outcome_unavailable",
            "r0_association_or_coverage_outcome_unavailable",
        }
    ):
        return ActiveVisionA3PairingDispositionCode.BENEFIT_OUTCOME_UNAVAILABLE
    if blockers.intersection(_A3_ADOPTION_BLOCKER_CODES):
        return ActiveVisionA3PairingDispositionCode.MODEL_ACTION_NOT_ADOPTED
    return ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID


def _validate_trace_runtime_chain(trace: ActiveVisionA3AdoptionTrace) -> None:
    command = trace.issued_command_payload
    ack = trace.runtime_ack
    feedback = trace.camera_feedback
    pose_lineage = trace.camera_pose_lineage
    decision = trace.decision
    if trace.policy_evaluated_timestamp is not None:
        proposal_time = (
            decision.requested_action.issued_timestamp
            if decision.requested_action is not None
            else decision.effective_action.issued_timestamp
        )
        if proposal_time + _EPS < trace.policy_evaluated_timestamp:
            _fail("trace_time_order_invalid", "decision precedes policy evaluation")
    if command is None:
        if ack is not None or feedback is not None or pose_lineage is not None:
            _fail(
                "runtime_feedback_without_command",
                "ACK, feedback, or pose lineage cannot exist without an issued command",
            )
        return
    if ack is not None:
        _validate_ack_against_command(ack, command, sample_key=trace.sample_key)
    if feedback is not None:
        if (
            feedback.camera_state.camera_id != trace.camera_id
            or feedback.camera_state.resource_id != trace.resource_id
        ):
            _fail(
                "camera_feedback_membership_mismatch",
                "camera feedback does not match trace camera/resource",
            )
        if feedback.camera_state.state_timestamp + _EPS < float(
            command["issued_timestamp"]
        ):
            _fail("trace_time_order_invalid", "camera feedback precedes command issue")
        if ack is not None and feedback.camera_state.state_timestamp + _EPS < ack.ack_timestamp:
            _fail("trace_time_order_invalid", "camera feedback precedes runtime ACK")
        if ack is not None and ack.accepted:
            if feedback.last_accepted_command_version != ack.command_version:
                _fail(
                    "ack_feedback_version_mismatch",
                    "accepted ACK version is absent from camera feedback",
                )
def _validate_candidate_window(
    trace: ActiveVisionA3AdoptionTrace,
    window: ActiveVisionA3PhysicalObservationWindow,
) -> None:
    if window.arm is not ActiveVisionA3WindowArm.A3:
        _fail("candidate_arm_invalid", "candidate physical window must use A3 arm")
    trace_identity = (
        trace.comparison_key,
        trace.scenario_id,
        trace.scale,
        trace.seed,
        trace.window_index,
        trace.camera_id,
        trace.resource_id,
        trace.target_global_track_id,
        trace.pairing_context_sha256,
        trace.decision.plan_version,
        trace.decision.coalition_version,
        trace.decision.communication_version,
    )
    if window.comparison_identity != trace_identity:
        _fail(
            "candidate_trace_identity_mismatch",
            "candidate window identity or version differs from adoption trace",
        )
    if window.adoption_trace_sha256 != trace.trace_sha256:
        _fail("candidate_trace_hash_mismatch", "candidate window binds a different trace")
    if window.source_event_log_sha256 != trace.source_event_log_sha256:
        _fail("candidate_log_hash_mismatch", "candidate window binds a different event log")
    if (
        trace.issued_command_payload is None
        or trace.runtime_ack is None
        or trace.camera_feedback is None
    ):
        _fail(
            "candidate_runtime_chain_missing",
            "candidate window cannot exist without trace command/ACK/feedback",
        )
    if (
        window.effective_action_sha256
        != _action_sha256(trace.decision.effective_action)
        or window.command_payload_sha256 != trace.command_payload_sha256
        or window.runtime_ack_sha256 != trace.runtime_ack_sha256
        or window.camera_feedback_sha256 != trace.camera_feedback_sha256
        or trace.camera_pose_lineage is None
        or window.camera_pose_lineage.content_sha256
        != trace.camera_pose_lineage.content_sha256
        or window.runtime_ack_evidence_kind != trace.runtime_ack_evidence_kind
        or window.camera_feedback_evidence_kind
        != trace.camera_feedback_evidence_kind
        or window.synthetic_fixture != trace.synthetic_fixture
        or window.online_truth_use_count != trace.online_truth_use_count
        or window.global_track_id_rewrite_count
        != trace.global_track_id_rewrite_count
    ):
        _fail(
            "candidate_runtime_chain_hash_mismatch",
            "candidate action/command/ACK/feedback differs from adoption trace",
        )


def _validate_same_key_pair(
    candidate: ActiveVisionA3PhysicalObservationWindow,
    r0_window: ActiveVisionA3PhysicalObservationWindow,
) -> None:
    if r0_window.arm is not ActiveVisionA3WindowArm.R0:
        _fail("r0_arm_invalid", "same-key reference is not an R0 window")
    if candidate.comparison_identity != r0_window.comparison_identity:
        _fail(
            "same_key_r0_identity_mismatch",
            "R0 window does not match scenario/scale/seed/camera/window/context/version",
        )
    if not math.isclose(
        candidate.duration_s,
        r0_window.duration_s,
        rel_tol=0.0,
        abs_tol=_EPS,
    ):
        _fail("same_key_r0_duration_mismatch", "candidate and R0 windows differ in duration")
    if candidate.source_event_log_sha256 == r0_window.source_event_log_sha256:
        _fail(
            "same_key_r0_log_reuse",
            "candidate and R0 windows cannot reuse one event log",
        )


def _validate_decision(decision: ActiveVisionDecisionV1) -> None:
    try:
        requested_mode = ActiveVisionRuntimeMode(decision.requested_mode)
        effective_mode = ActiveVisionRuntimeMode(decision.effective_mode)
    except (TypeError, ValueError):
        _fail("decision_mode_invalid", "active-vision decision mode is invalid")
    for name, action in (
        ("rule_action", decision.rule_action),
        ("effective_action", decision.effective_action),
    ):
        if not isinstance(action, ActiveVisionActionV1):
            _fail("decision_action_type_invalid", f"{name} must use ActiveVisionActionV1")
    if decision.requested_action is not None and not isinstance(
        decision.requested_action,
        ActiveVisionActionV1,
    ):
        _fail(
            "decision_action_type_invalid",
            "requested_action must use ActiveVisionActionV1",
        )
    versions = (
        int(decision.plan_version),
        int(decision.coalition_version),
        int(decision.communication_version),
    )
    for action in (
        decision.rule_action,
        decision.effective_action,
        decision.requested_action,
    ):
        if action is None:
            continue
        if (
            action.plan_version,
            action.coalition_version,
            action.communication_version,
        ) != versions:
            _fail("decision_version_mismatch", "decision action versions disagree")
    if decision.rule_action.camera_id != decision.effective_action.camera_id:
        _fail("decision_camera_mismatch", "rule and effective camera IDs differ")
    latency = _finite(decision.inference_latency_ms, "decision.inference_latency_ms")
    if latency < 0.0:
        _fail("decision_latency_invalid", "decision latency must be non-negative")
    if effective_mode is ActiveVisionRuntimeMode.ASSIST:
        if requested_mode is not ActiveVisionRuntimeMode.ASSIST:
            _fail("decision_assist_mode_invalid", "assist was not requested")
        if decision.requested_action is None or decision.fallback_reason is not None:
            _fail("decision_assist_state_invalid", "assist lacks an accepted proposal")
        if _action_sha256(decision.requested_action) != _action_sha256(
            decision.effective_action
        ):
            _fail("decision_assist_action_mismatch", "effective action differs from proposal")


def _validate_rule_arm_decision(decision: ActiveVisionDecisionV1) -> None:
    requested_mode = ActiveVisionRuntimeMode(decision.requested_mode)
    effective_mode = ActiveVisionRuntimeMode(decision.effective_mode)
    if (
        requested_mode is not ActiveVisionRuntimeMode.DISABLED
        or effective_mode is not ActiveVisionRuntimeMode.DISABLED
    ):
        _fail(
            "r0_decision_not_deterministic",
            "R0 must run with learning disabled in both requested and effective modes",
        )
    if decision.requested_action is not None:
        _fail(
            "r0_model_proposal_forbidden",
            "R0 cannot carry a learned-policy proposal",
        )
    if decision.model_fingerprint is not None:
        _fail(
            "r0_model_fingerprint_forbidden",
            "R0 cannot carry a learned-model fingerprint",
        )
    if not math.isclose(
        float(decision.inference_latency_ms),
        0.0,
        rel_tol=0.0,
        abs_tol=_EPS,
    ):
        _fail(
            "r0_model_inference_forbidden",
            "R0 cannot report learned-model inference latency",
        )
    if _action_sha256(decision.rule_action) != _action_sha256(
        decision.effective_action
    ):
        _fail(
            "r0_rule_action_mismatch",
            "R0 effective action must exactly equal its deterministic rule action",
        )


def _validated_command_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    _assert_truth_free(payload)
    _expect_fields(payload, _COMMAND_FIELDS, "camera_command")
    if payload["payload_version"] != CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION:
        _fail("camera_command_payload_version_mismatch", "unsupported command payload")
    result: dict[str, Any] = {
        "payload_version": CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION,
        "camera_id": _token(payload["camera_id"], "camera_command.camera_id"),
        "resource_id": _token(payload["resource_id"], "camera_command.resource_id"),
        "issued_timestamp": _finite(
            payload["issued_timestamp"],
            "camera_command.issued_timestamp",
        ),
        "expires_timestamp": _finite(
            payload["expires_timestamp"],
            "camera_command.expires_timestamp",
        ),
        "plan_version": _non_negative_int(
            payload["plan_version"],
            "camera_command.plan_version",
        ),
        "coalition_version": _non_negative_int(
            payload["coalition_version"],
            "camera_command.coalition_version",
        ),
        "communication_version": _non_negative_int(
            payload["communication_version"],
            "camera_command.communication_version",
        ),
        "intent": _choice(payload["intent"], _INTENTS, "camera_command.intent"),
        "horizontal_fov_deg": _finite(
            payload["horizontal_fov_deg"],
            "camera_command.horizontal_fov_deg",
        ),
        "fov_mode": _choice(
            payload["fov_mode"],
            _FOV_MODES,
            "camera_command.fov_mode",
        ),
        "target_global_track_id": _optional_token(
            payload["target_global_track_id"],
            "camera_command.target_global_track_id",
        ),
        "requested_mode": _choice(
            payload["requested_mode"],
            _MODES,
            "camera_command.requested_mode",
        ),
        "effective_mode": _choice(
            payload["effective_mode"],
            _MODES,
            "camera_command.effective_mode",
        ),
        "reason": _token(payload["reason"], "camera_command.reason"),
    }
    try:
        point = tuple(float(value) for value in payload["aim_point_ned"])
    except (TypeError, ValueError):
        _fail("camera_command_aim_point_invalid", "aim_point_ned must be numeric")
    if len(point) != 3 or not all(math.isfinite(value) for value in point):
        _fail("camera_command_aim_point_invalid", "aim_point_ned must be a finite 3-vector")
    result["aim_point_ned"] = list(point)
    if result["expires_timestamp"] <= result["issued_timestamp"]:
        _fail("camera_command_time_invalid", "command has non-positive lifetime")
    if not 1.0 < result["horizontal_fov_deg"] < 179.0:
        _fail("camera_command_fov_invalid", "command FOV is outside (1, 179)")
    target_required = result["intent"] in {"observe_target", "reacquire"}
    if target_required != (result["target_global_track_id"] is not None):
        _fail("camera_command_target_invalid", "command target reference conflicts with intent")
    if (
        result["requested_mode"] == "disabled"
        and result["effective_mode"] != "disabled"
    ):
        _fail("camera_command_mode_invalid", "disabled request has non-disabled mode")
    if (
        result["effective_mode"] == "assist"
        and result["requested_mode"] != "assist"
    ):
        _fail("camera_command_mode_invalid", "assist command was not requested")
    return result


def _validate_command_against_action(
    command: Mapping[str, Any],
    *,
    action: ActiveVisionActionV1,
    requested_mode: ActiveVisionRuntimeMode,
    effective_mode: ActiveVisionRuntimeMode,
    pre_camera: ActiveVisionCameraState,
    resource_id: str,
) -> None:
    expected_fov = (
        pre_camera.wide_horizontal_fov_deg
        if action.fov_mode is ActiveVisionFovMode.WIDE
        else pre_camera.zoom_horizontal_fov_deg
    )
    comparisons = {
        "camera_id": action.camera_id,
        "resource_id": resource_id,
        "issued_timestamp": action.issued_timestamp,
        "expires_timestamp": action.expires_timestamp,
        "plan_version": action.plan_version,
        "coalition_version": action.coalition_version,
        "communication_version": action.communication_version,
        "intent": action.intent.value,
        "fov_mode": action.fov_mode.value,
        "target_global_track_id": action.target_global_track_id,
        "requested_mode": ActiveVisionRuntimeMode(requested_mode).value,
        "effective_mode": ActiveVisionRuntimeMode(effective_mode).value,
    }
    for name, expected in comparisons.items():
        actual = command[name]
        if isinstance(expected, float):
            if not math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=_EPS):
                _fail(
                    "camera_command_action_mismatch",
                    f"command {name} differs from effective action",
                )
        elif actual != expected:
            _fail(
                "camera_command_action_mismatch",
                f"command {name} differs from effective action",
            )
    if not math.isclose(
        float(command["horizontal_fov_deg"]),
        float(expected_fov),
        rel_tol=0.0,
        abs_tol=_EPS,
    ):
        _fail(
            "camera_command_fov_mismatch",
            "command FOV differs from the effective action FOV mode",
        )


def _validate_ack_against_command(
    ack: ActiveVisionRuntimeAckV1,
    command: Mapping[str, Any],
    *,
    sample_key: str,
) -> None:
    if ack.sample_key != sample_key or ack.camera_id != command["camera_id"]:
        _fail("runtime_ack_identity_mismatch", "ACK sample/camera binding differs")
    if (
        ack.command_version != command["communication_version"]
        or ack.plan_version != command["plan_version"]
        or ack.coalition_version != command["coalition_version"]
        or ack.communication_version != command["communication_version"]
    ):
        _fail("runtime_ack_version_mismatch", "ACK command/plan versions differ")
    if ack.ack_timestamp + _EPS < command["issued_timestamp"]:
        _fail("runtime_ack_time_mismatch", "ACK precedes command issue")
    if ack.ack_timestamp > command["expires_timestamp"] + _EPS:
        _fail("runtime_ack_time_mismatch", "ACK follows command expiry")
    if ack.accepted and ack.status_code not in {"accepted", "applied"}:
        _fail("runtime_ack_status_mismatch", "accepted ACK has a non-applied status")
    if not ack.accepted and ack.status_code in {"accepted", "applied"}:
        _fail("runtime_ack_status_mismatch", "rejected ACK has an applied status")


def _validate_pose_lineage_against_feedback(
    lineage: ActiveVisionA3CameraPoseLineage,
    feedback: ActiveVisionCameraFeedbackV1 | None,
) -> None:
    if feedback is None:
        _fail(
            "camera_pose_lineage_feedback_missing",
            "pose lineage cannot exist without camera feedback",
        )
    state = feedback.camera_state
    expected_horizontal_fov = (
        state.wide_horizontal_fov_deg
        if state.current_fov_mode is ActiveVisionFovMode.WIDE
        else state.zoom_horizontal_fov_deg
    )
    exact = {
        "camera_id": state.camera_id,
        "resource_id": state.resource_id,
        "fov_mode": state.current_fov_mode.value,
    }
    for name, expected in exact.items():
        if getattr(lineage, name) != expected:
            _fail(
                "camera_pose_lineage_feedback_mismatch",
                f"pose lineage {name} differs from camera feedback",
            )
    numeric = {
        "state_timestamp": state.state_timestamp,
        "yaw_deg": state.yaw_deg,
        "pitch_deg": state.pitch_deg,
        "horizontal_fov_deg": expected_horizontal_fov,
    }
    for name, expected in numeric.items():
        if not math.isclose(
            float(getattr(lineage, name)),
            float(expected),
            rel_tol=0.0,
            abs_tol=_EPS,
        ):
            _fail(
                "camera_pose_lineage_feedback_mismatch",
                f"pose lineage {name} differs from camera feedback",
            )


def _validate_pose_lineage_against_command(
    lineage: ActiveVisionA3CameraPoseLineage,
    command: Mapping[str, Any],
    *,
    runtime_ack: ActiveVisionRuntimeAckV1 | None,
) -> None:
    expected = {
        "camera_id": command["camera_id"],
        "resource_id": command["resource_id"],
        "fov_mode": command["fov_mode"],
        "last_plan_version": command["plan_version"],
        "last_coalition_version": command["coalition_version"],
        "last_communication_version": command["communication_version"],
    }
    for name, value in expected.items():
        if getattr(lineage, name) != value:
            _fail(
                "camera_pose_lineage_command_mismatch",
                f"runtime camera state {name} differs from camera command",
            )
    if not math.isclose(
        lineage.horizontal_fov_deg,
        float(command["horizontal_fov_deg"]),
        rel_tol=0.0,
        abs_tol=_EPS,
    ):
        _fail(
            "camera_pose_lineage_command_mismatch",
            "runtime camera FOV differs from camera command",
        )
    if lineage.state_timestamp + _EPS < float(command["issued_timestamp"]):
        _fail(
            "camera_pose_lineage_time_mismatch",
            "runtime camera state precedes camera command",
        )
    if runtime_ack is not None:
        if lineage.state_timestamp + _EPS < runtime_ack.ack_timestamp:
            _fail(
                "camera_pose_lineage_time_mismatch",
                "runtime camera state precedes runtime ACK",
            )
        if lineage.last_communication_version != runtime_ack.command_version:
            _fail(
                "camera_pose_lineage_ack_mismatch",
                "runtime camera state does not carry the ACK command version",
            )


def _pose_applied(
    *,
    action: ActiveVisionActionV1,
    pre_camera: ActiveVisionCameraState,
    runtime_ack: ActiveVisionRuntimeAckV1 | None,
    feedback: ActiveVisionCameraFeedbackV1 | None,
    pose_lineage: ActiveVisionA3CameraPoseLineage | None,
    command: Mapping[str, Any] | None,
    ack_kind: str,
    feedback_kind: str,
    synthetic_fixture: bool,
    tolerance_deg: float,
) -> bool:
    if (
        runtime_ack is None
        or feedback is None
        or pose_lineage is None
        or command is None
        or not runtime_ack.accepted
        or runtime_ack.status_code not in {"accepted", "applied"}
        or ack_kind != RUNTIME_OBSERVED_EVIDENCE_KIND
        or feedback_kind != RUNTIME_OBSERVED_EVIDENCE_KIND
        or pose_lineage.evidence_kind != RUNTIME_OBSERVED_EVIDENCE_KIND
        or synthetic_fixture
        or feedback.last_accepted_command_version != runtime_ack.command_version
    ):
        return False
    try:
        _validate_pose_lineage_against_feedback(pose_lineage, feedback)
        _validate_pose_lineage_against_command(
            pose_lineage,
            command,
            runtime_ack=runtime_ack,
        )
    except ActiveVisionA3EvidenceError:
        return False
    state = feedback.camera_state
    if state.camera_id != pre_camera.camera_id or state.resource_id != pre_camera.resource_id:
        return False
    expected_yaw = _wrap_degrees(pre_camera.yaw_deg + action.yaw_delta_deg)
    expected_pitch = pre_camera.pitch_deg + action.pitch_delta_deg
    yaw_error = abs(_wrap_degrees(state.yaw_deg - expected_yaw))
    pitch_error = abs(state.pitch_deg - expected_pitch)
    return (
        yaw_error <= tolerance_deg
        and pitch_error <= tolerance_deg
        and state.current_fov_mode is action.fov_mode
        and state.state_timestamp + _EPS >= runtime_ack.ack_timestamp
    )


def _decision_to_payload(decision: ActiveVisionDecisionV1) -> dict[str, Any]:
    return {
        "requested_mode": ActiveVisionRuntimeMode(decision.requested_mode).value,
        "effective_mode": ActiveVisionRuntimeMode(decision.effective_mode).value,
        "rule_action": _action_to_payload(decision.rule_action),
        "requested_action": (
            None
            if decision.requested_action is None
            else _action_to_payload(decision.requested_action)
        ),
        "effective_action": _action_to_payload(decision.effective_action),
        "fallback_reason": decision.fallback_reason,
        "inference_latency_ms": float(decision.inference_latency_ms),
        "model_fingerprint": decision.model_fingerprint,
        "plan_version": int(decision.plan_version),
        "coalition_version": int(decision.coalition_version),
        "communication_version": int(decision.communication_version),
    }


def _decision_from_payload(payload: Mapping[str, Any]) -> ActiveVisionDecisionV1:
    _expect_fields(
        payload,
        {
            "requested_mode",
            "effective_mode",
            "rule_action",
            "requested_action",
            "effective_action",
            "fallback_reason",
            "inference_latency_ms",
            "model_fingerprint",
            "plan_version",
            "coalition_version",
            "communication_version",
        },
        "decision",
    )
    requested = payload["requested_action"]
    return ActiveVisionDecisionV1(
        requested_mode=ActiveVisionRuntimeMode(payload["requested_mode"]),
        effective_mode=ActiveVisionRuntimeMode(payload["effective_mode"]),
        rule_action=_action_from_payload(
            _mapping(payload["rule_action"], "decision.rule_action")
        ),
        requested_action=(
            None
            if requested is None
            else _action_from_payload(
                _mapping(requested, "decision.requested_action")
            )
        ),
        effective_action=_action_from_payload(
            _mapping(payload["effective_action"], "decision.effective_action")
        ),
        fallback_reason=(
            None
            if payload["fallback_reason"] is None
            else _token(payload["fallback_reason"], "decision.fallback_reason")
        ),
        inference_latency_ms=_finite(
            payload["inference_latency_ms"],
            "decision.inference_latency_ms",
        ),
        model_fingerprint=(
            None
            if payload["model_fingerprint"] is None
            else _token(payload["model_fingerprint"], "decision.model_fingerprint")
        ),
        plan_version=_non_negative_int(
            payload["plan_version"],
            "decision.plan_version",
        ),
        coalition_version=_non_negative_int(
            payload["coalition_version"],
            "decision.coalition_version",
        ),
        communication_version=_non_negative_int(
            payload["communication_version"],
            "decision.communication_version",
        ),
    )


def _action_to_payload(action: ActiveVisionActionV1) -> dict[str, Any]:
    return {
        "schema_version": action.schema_version,
        "camera_id": action.camera_id,
        "issued_timestamp": action.issued_timestamp,
        "expires_timestamp": action.expires_timestamp,
        "plan_version": action.plan_version,
        "coalition_version": action.coalition_version,
        "communication_version": action.communication_version,
        "intent": action.intent.value,
        "yaw_delta_deg": action.yaw_delta_deg,
        "pitch_delta_deg": action.pitch_delta_deg,
        "fov_mode": action.fov_mode.value,
        "target_global_track_id": action.target_global_track_id,
        "search_sector_deg": (
            None
            if action.search_sector_deg is None
            else list(action.search_sector_deg)
        ),
        "reason": action.reason,
    }


def _action_from_payload(payload: Mapping[str, Any]) -> ActiveVisionActionV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "camera_id",
            "issued_timestamp",
            "expires_timestamp",
            "plan_version",
            "coalition_version",
            "communication_version",
            "intent",
            "yaw_delta_deg",
            "pitch_delta_deg",
            "fov_mode",
            "target_global_track_id",
            "search_sector_deg",
            "reason",
        },
        "action",
    )
    return ActiveVisionActionV1(
        schema_version=payload["schema_version"],
        camera_id=payload["camera_id"],
        issued_timestamp=payload["issued_timestamp"],
        expires_timestamp=payload["expires_timestamp"],
        plan_version=payload["plan_version"],
        coalition_version=payload["coalition_version"],
        communication_version=payload["communication_version"],
        intent=ActiveVisionIntent(payload["intent"]),
        yaw_delta_deg=payload["yaw_delta_deg"],
        pitch_delta_deg=payload["pitch_delta_deg"],
        fov_mode=ActiveVisionFovMode(payload["fov_mode"]),
        target_global_track_id=payload["target_global_track_id"],
        search_sector_deg=payload["search_sector_deg"],
        reason=payload["reason"],
    )


def _action_sha256(action: ActiveVisionActionV1) -> str:
    return _sha256_json(_action_to_payload(action))


def _camera_state_to_payload(state: ActiveVisionCameraState) -> dict[str, Any]:
    return {
        "camera_id": state.camera_id,
        "resource_id": state.resource_id,
        "state_timestamp": state.state_timestamp,
        "yaw_deg": state.yaw_deg,
        "pitch_deg": state.pitch_deg,
        "yaw_rate_deg_s": state.yaw_rate_deg_s,
        "pitch_rate_deg_s": state.pitch_rate_deg_s,
        "yaw_limits_deg": list(state.yaw_limits_deg),
        "pitch_limits_deg": list(state.pitch_limits_deg),
        "max_yaw_rate_deg_s": state.max_yaw_rate_deg_s,
        "max_pitch_rate_deg_s": state.max_pitch_rate_deg_s,
        "max_slew_deg_s": state.max_slew_deg_s,
        "current_fov_mode": state.current_fov_mode.value,
        "supported_fov_modes": [item.value for item in state.supported_fov_modes],
        "wide_horizontal_fov_deg": state.wide_horizontal_fov_deg,
        "zoom_horizontal_fov_deg": state.zoom_horizontal_fov_deg,
        "slew_available": state.slew_available,
        "action_in_progress_until": state.action_in_progress_until,
    }


def _camera_state_from_payload(payload: Mapping[str, Any]) -> ActiveVisionCameraState:
    _expect_fields(
        payload,
        {
            "camera_id",
            "resource_id",
            "state_timestamp",
            "yaw_deg",
            "pitch_deg",
            "yaw_rate_deg_s",
            "pitch_rate_deg_s",
            "yaw_limits_deg",
            "pitch_limits_deg",
            "max_yaw_rate_deg_s",
            "max_pitch_rate_deg_s",
            "max_slew_deg_s",
            "current_fov_mode",
            "supported_fov_modes",
            "wide_horizontal_fov_deg",
            "zoom_horizontal_fov_deg",
            "slew_available",
            "action_in_progress_until",
        },
        "camera_state",
    )
    return ActiveVisionCameraState(
        camera_id=payload["camera_id"],
        resource_id=payload["resource_id"],
        state_timestamp=payload["state_timestamp"],
        yaw_deg=payload["yaw_deg"],
        pitch_deg=payload["pitch_deg"],
        yaw_rate_deg_s=payload["yaw_rate_deg_s"],
        pitch_rate_deg_s=payload["pitch_rate_deg_s"],
        yaw_limits_deg=payload["yaw_limits_deg"],
        pitch_limits_deg=payload["pitch_limits_deg"],
        max_yaw_rate_deg_s=payload["max_yaw_rate_deg_s"],
        max_pitch_rate_deg_s=payload["max_pitch_rate_deg_s"],
        max_slew_deg_s=payload["max_slew_deg_s"],
        current_fov_mode=ActiveVisionFovMode(payload["current_fov_mode"]),
        supported_fov_modes=tuple(
            ActiveVisionFovMode(item) for item in payload["supported_fov_modes"]
        ),
        wide_horizontal_fov_deg=payload["wide_horizontal_fov_deg"],
        zoom_horizontal_fov_deg=payload["zoom_horizontal_fov_deg"],
        slew_available=payload["slew_available"],
        action_in_progress_until=payload["action_in_progress_until"],
    )


def _runtime_ack_to_payload(ack: ActiveVisionRuntimeAckV1) -> dict[str, Any]:
    return {
        "schema_version": ack.schema_version,
        "sample_key": ack.sample_key,
        "camera_id": ack.camera_id,
        "command_version": ack.command_version,
        "ack_timestamp": ack.ack_timestamp,
        "accepted": ack.accepted,
        "status_code": ack.status_code,
        "plan_version": ack.plan_version,
        "coalition_version": ack.coalition_version,
        "communication_version": ack.communication_version,
    }


def _runtime_ack_from_payload(payload: Mapping[str, Any]) -> ActiveVisionRuntimeAckV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "sample_key",
            "camera_id",
            "command_version",
            "ack_timestamp",
            "accepted",
            "status_code",
            "plan_version",
            "coalition_version",
            "communication_version",
        },
        "runtime_ack",
    )
    return ActiveVisionRuntimeAckV1(
        schema_version=payload["schema_version"],
        sample_key=payload["sample_key"],
        camera_id=payload["camera_id"],
        command_version=payload["command_version"],
        ack_timestamp=payload["ack_timestamp"],
        accepted=payload["accepted"],
        status_code=payload["status_code"],
        plan_version=payload["plan_version"],
        coalition_version=payload["coalition_version"],
        communication_version=payload["communication_version"],
    )


def _camera_feedback_to_payload(
    feedback: ActiveVisionCameraFeedbackV1,
) -> dict[str, Any]:
    return {
        "schema_version": feedback.schema_version,
        "camera_state": _camera_state_to_payload(feedback.camera_state),
        "last_accepted_command_version": feedback.last_accepted_command_version,
    }


def _camera_feedback_from_payload(
    payload: Mapping[str, Any],
) -> ActiveVisionCameraFeedbackV1:
    _expect_fields(
        payload,
        {
            "schema_version",
            "camera_state",
            "last_accepted_command_version",
        },
        "camera_feedback",
    )
    return ActiveVisionCameraFeedbackV1(
        schema_version=payload["schema_version"],
        camera_state=_camera_state_from_payload(
            _mapping(payload["camera_state"], "camera_feedback.camera_state")
        ),
        last_accepted_command_version=payload["last_accepted_command_version"],
    )


def _anonymous_observation_values(observation: Any) -> dict[str, Any]:
    required = (
        "resource_id",
        "camera_id",
        "local_track_id",
        "measurement_timestamp",
        "arrival_timestamp",
        "tracklet_key",
    )
    missing = [name for name in required if not hasattr(observation, name)]
    if missing:
        _fail(
            "anonymous_observation_contract_invalid",
            f"visual observation is missing fields: {missing}",
        )
    resource_id = _token(
        getattr(observation, "resource_id"),
        "anonymous_observation.resource_id",
    )
    camera_id = _token(
        getattr(observation, "camera_id"),
        "anonymous_observation.camera_id",
    )
    local_track_id = _token(
        getattr(observation, "local_track_id"),
        "anonymous_observation.local_track_id",
    )
    expected_key = f"{resource_id}/{camera_id}:{local_track_id}"
    tracklet_key = _tracklet_key(
        getattr(observation, "tracklet_key"),
        "anonymous_observation.tracklet_key",
    )
    if tracklet_key != expected_key:
        _fail(
            "anonymous_observation_tracklet_key_mismatch",
            "tracklet key differs from resource/camera/local ID namespace",
        )
    measurement = _finite(
        getattr(observation, "measurement_timestamp"),
        "anonymous_observation.measurement_timestamp",
    )
    arrival = _finite(
        getattr(observation, "arrival_timestamp"),
        "anonymous_observation.arrival_timestamp",
    )
    if arrival + _EPS < measurement:
        _fail(
            "anonymous_observation_time_invalid",
            "arrival timestamp precedes measurement timestamp",
        )
    metadata = getattr(observation, "metadata", {})
    _assert_anonymous(
        {
            "resource_id": resource_id,
            "camera_id": camera_id,
            "local_track_id": local_track_id,
            "tracklet_key": tracklet_key,
            "metadata": metadata,
        }
    )
    return {
        "resource_id": resource_id,
        "camera_id": camera_id,
        "local_track_id": local_track_id,
        "tracklet_key": tracklet_key,
        "measurement_timestamp": measurement,
        "arrival_timestamp": arrival,
    }


def _binding_evidence(
    binding: CenterTrackBindingDecision
    | ActiveVisionA3BindingEvidence
    | Mapping[str, Any],
    *,
    allowed_global_track_ids: frozenset[str],
) -> ActiveVisionA3BindingEvidence:
    if isinstance(binding, ActiveVisionA3BindingEvidence):
        item = binding
    elif isinstance(binding, CenterTrackBindingDecision):
        item = ActiveVisionA3BindingEvidence(
            cluster_key=binding.cluster_key,
            global_track_id=binding.global_track_id,
            decision_state=binding.decision_state,
            supporting_tracklet_keys=tuple(binding.supporting_tracklet_keys),
        )
    elif isinstance(binding, Mapping):
        if binding.get("schema_version") == ACTIVE_VISION_A3_BINDING_EVIDENCE_SCHEMA_VERSION:
            item = ActiveVisionA3BindingEvidence.from_mapping(binding)
        else:
            _assert_truth_free(binding)
            required = {
                "cluster_key",
                "global_track_id",
                "decision_state",
                "supporting_tracklet_keys",
            }
            if not required.issubset(binding):
                _fail(
                    "binding_contract_invalid",
                    "binding mapping lacks cluster/global/state/support fields",
                )
            item = ActiveVisionA3BindingEvidence(
                cluster_key=binding["cluster_key"],
                global_track_id=binding["global_track_id"],
                decision_state=binding["decision_state"],
                supporting_tracklet_keys=tuple(binding["supporting_tracklet_keys"]),
            )
    else:
        _fail(
            "binding_contract_invalid",
            "binding must use a D5 center binding or A3 binding evidence",
        )
    if (
        item.global_track_id is not None
        and item.global_track_id not in allowed_global_track_ids
    ):
        _fail(
            "binding_global_reference_not_center_owned",
            "binding references a global track absent from center candidates",
        )
    return item


def _outcome_from_observation_frames(
    frames: Iterable[ActiveVisionA3AnonymousObservationFrame],
) -> ActiveVisionA3OutcomeEvidence:
    items = tuple(frames)
    if not items:
        _fail(
            "physical_window_empty",
            "physical observation window has no frames",
        )
    states = tuple(item.association_state for item in items)
    evaluable_states = tuple(state for state in states if state is not None)
    association_available = bool(evaluable_states)
    coverage_values = tuple(item.assigned_reference_visible for item in items)
    coverage_available = all(value is not None for value in coverage_values)
    if association_available:
        counts = {
            state: sum(value == state for value in evaluable_states)
            for state in ("locked", "ambiguous", "hold", "reacquire")
        }
        association_evaluable_frame_count: int | None = len(evaluable_states)
    else:
        counts = {
            "locked": None,
            "ambiguous": None,
            "hold": None,
            "reacquire": None,
        }
        association_evaluable_frame_count = None
    return ActiveVisionA3OutcomeEvidence(
        association_outcome_available=association_available,
        coverage_outcome_available=coverage_available,
        observation_frame_count=len(items),
        association_evaluable_frame_count=association_evaluable_frame_count,
        association_locked_count=counts["locked"],
        association_ambiguous_count=counts["ambiguous"],
        association_hold_count=counts["hold"],
        association_reacquire_count=counts["reacquire"],
        assigned_reference_count=(len(items) if coverage_available else None),
        visible_assigned_reference_count=(
            sum(bool(value) for value in coverage_values)
            if coverage_available
            else None
        ),
    )


def _optional_window(
    payload: Any,
    name: str,
) -> ActiveVisionA3PhysicalObservationWindow | None:
    if payload is None:
        return None
    return ActiveVisionA3PhysicalObservationWindow.from_mapping(_mapping(payload, name))


def _validate_optional_evidence_kind(value: Any, kind: str, name: str) -> None:
    if value is None and kind != UNAVAILABLE_EVIDENCE_KIND:
        _fail(
            "evidence_source_state_invalid",
            f"missing {name} must use unavailable provenance",
        )
    if value is not None and kind == UNAVAILABLE_EVIDENCE_KIND:
        _fail(
            "evidence_source_state_invalid",
            f"present {name} cannot use unavailable provenance",
        )


def _expect_fields(
    payload: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    if not isinstance(payload, Mapping):
        _fail("evidence_type_invalid", f"{name} must be an object")
    actual = set(payload)
    if actual != expected:
        _fail(
            "evidence_fields_mismatch",
            f"{name} fields mismatch; missing={sorted(expected - actual)}, "
            f"extra={sorted(actual - expected)}",
        )


def _assert_truth_free(payload: Any) -> None:
    try:
        assert_truth_free_active_vision_payload(payload)
    except ValueError as exc:
        _fail(
            "online_truth_identity_forbidden",
            f"A3 online evidence contains simulator/evaluator identity: {exc}",
        )


def _assert_anonymous(payload: Any) -> None:
    _assert_truth_free(payload)
    try:
        assert_anonymous_online_payload(payload)
    except ValueError as exc:
        _fail(
            "anonymous_visual_identity_forbidden",
            f"A3 visual evidence contains simulator/evaluator identity: {exc}",
        )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("evidence_type_invalid", f"{name} must be an object")
    return value


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        _fail("evidence_boolean_invalid", f"{name} must be a strict boolean")
    return bool(value)


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        _fail("evidence_number_invalid", f"{name} must be finite")
    try:
        result = float(value)
    except (TypeError, ValueError):
        _fail("evidence_number_invalid", f"{name} must be finite")
    if not math.isfinite(result):
        _fail("evidence_number_invalid", f"{name} must be finite")
    return result


def _optional_finite(value: Any, name: str) -> float | None:
    return None if value is None else _finite(value, name)


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _fail("evidence_integer_invalid", f"{name} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        _fail("evidence_integer_invalid", f"{name} must be a non-negative integer")
    if result != value or result < 0:
        _fail("evidence_integer_invalid", f"{name} must be a non-negative integer")
    return result


def _optional_non_negative_int(value: Any, name: str) -> int | None:
    return None if value is None else _non_negative_int(value, name)


def _token(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        _fail("evidence_token_invalid", f"{name} must be non-empty")
    return result


def _optional_token(value: Any, name: str) -> str | None:
    return None if value is None else _token(value, name)


def _tracklet_key(value: Any, name: str) -> str:
    result = _token(value, name)
    if _TRACKLET_KEY_RE.fullmatch(result) is None:
        _fail(
            "tracklet_key_invalid",
            f"{name} must use resource_id/camera_id:local_id",
        )
    _assert_anonymous({"local_tracklet_key": result})
    return result


def _choice(value: Any, choices: frozenset[str], name: str) -> str:
    result = _token(value, name)
    if result not in choices:
        _fail("evidence_choice_invalid", f"{name} has unsupported value {result!r}")
    return result


def _enum(enum_type: type[Enum], value: Any, name: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        _fail("evidence_choice_invalid", f"{name} has an unsupported value")


def _digest(value: Any, name: str) -> str:
    result = str(value).strip().lower()
    if _SHA256_RE.fullmatch(result) is None:
        _fail("evidence_sha256_invalid", f"{name} must be a lowercase SHA256")
    return result


def _optional_digest(value: Any, name: str) -> str | None:
    return None if value is None else _digest(value, name)


def _sha256_json(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _wrap_degrees(value: float) -> float:
    return ((float(value) + 180.0) % 360.0) - 180.0


def _fail(code: str, detail: str) -> None:
    raise ActiveVisionA3EvidenceError(code, detail)


__all__ = [
    "ACTIVE_VISION_A3_AUDIT_INPUT_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_BINDING_EVIDENCE_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_CANDIDATE_STAGE_EVIDENCE_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_PAIRING_DISPOSITION_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_POSE_LINEAGE_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_RULE_ARM_TRACE_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_TRACE_SCHEMA_VERSION",
    "ACTIVE_VISION_A3_WINDOW_SCHEMA_VERSION",
    "CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION",
    "RUNTIME_OBSERVED_EVIDENCE_KIND",
    "SYNTHETIC_FIXTURE_EVIDENCE_KIND",
    "UNAVAILABLE_EVIDENCE_KIND",
    "ActiveVisionA3AdoptionTrace",
    "ActiveVisionA3AnonymousObservationFrame",
    "ActiveVisionA3AuditPermissions",
    "ActiveVisionA3BindingEvidence",
    "ActiveVisionA3BenefitAuditInput",
    "ActiveVisionA3CandidatePhysicalWindowStatus",
    "ActiveVisionA3CandidateStageEvidence",
    "ActiveVisionA3CandidateStageReasonCode",
    "ActiveVisionA3CameraPoseLineage",
    "ActiveVisionA3CommandSource",
    "ActiveVisionA3EvidenceError",
    "ActiveVisionA3OutcomeEvidence",
    "ActiveVisionA3PairingDisposition",
    "ActiveVisionA3PairingDispositionCode",
    "ActiveVisionA3PhysicalObservationWindow",
    "ActiveVisionA3ProjectionStatus",
    "ActiveVisionA3RuleArmTrace",
    "ActiveVisionA3WindowArm",
    "active_vision_a3_observation_frame",
    "active_vision_a3_zero_detection_frame",
    "active_vision_camera_feedback_from_runtime_state",
    "active_vision_camera_pose_lineage_from_runtime_state",
    "active_vision_runtime_ack_from_payload",
    "assemble_active_vision_a3_adoption_trace",
    "assemble_active_vision_a3_evidence",
    "assemble_active_vision_a3_paired_evidence",
    "assemble_active_vision_a3_physical_observation_window",
    "assemble_active_vision_a3_rule_arm_physical_observation_window",
    "assemble_active_vision_a3_rule_arm_trace",
    "attempt_active_vision_a3_pairing",
    "camera_observation_command_payload",
    "load_active_vision_a3_evidence",
    "map_active_vision_binding_state",
    "validate_active_vision_a3_evidence",
    "validate_active_vision_a3_candidate_stage_evidence",
    "validate_active_vision_a3_pairing_disposition",
]
