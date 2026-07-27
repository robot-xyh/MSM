from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from types import SimpleNamespace
from typing import Mapping

import numpy as np
import pytest

from d5_terminal_association import (
    ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION,
    ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION,
    ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION,
    CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION,
    RUNTIME_OBSERVED_EVIDENCE_KIND,
    SYNTHETIC_FIXTURE_EVIDENCE_KIND,
    UNAVAILABLE_EVIDENCE_KIND,
    ActiveVisionA3AdoptionTrace,
    ActiveVisionA3AnonymousObservationFrame,
    ActiveVisionA3BindingEvidence,
    ActiveVisionA3CandidatePhysicalWindowStatus,
    ActiveVisionA3CandidateStageEvidence,
    ActiveVisionA3CandidateStageReasonCode,
    ActiveVisionA3CameraPoseLineage,
    ActiveVisionA3CommandSource,
    ActiveVisionA3EvidenceError,
    ActiveVisionA3OutcomeEvidence,
    ActiveVisionA3PairingDisposition,
    ActiveVisionA3PairingDispositionCode,
    ActiveVisionA3PhysicalObservationWindow,
    ActiveVisionA3RuleArmTrace,
    ActiveVisionA3WindowArm,
    ActiveVisionActionV1,
    ActiveVisionAssignmentReference,
    ActiveVisionCameraFeedbackV1,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionDecisionV1,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionPlanReference,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    ActiveVisionRuntimeAckV1,
    ActiveVisionRuntimeMode,
    CameraLocalTracklet,
    CenterTrackBindingDecision,
    active_vision_a3_observation_frame,
    active_vision_a3_zero_detection_frame,
    assemble_active_vision_a3_adoption_trace,
    assemble_active_vision_a3_evidence,
    assemble_active_vision_a3_paired_evidence,
    assemble_active_vision_a3_physical_observation_window,
    assemble_active_vision_a3_rule_arm_physical_observation_window,
    assemble_active_vision_a3_rule_arm_trace,
    attempt_active_vision_a3_pairing,
    camera_observation_command_payload,
    map_active_vision_binding_state,
    validate_active_vision_a3_evidence,
    validate_active_vision_a3_candidate_stage_evidence,
    validate_active_vision_a3_pairing_disposition,
)


def _digest(token: str) -> str:
    return token * 64


def _payload_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _camera_state(
    *,
    timestamp: float,
    yaw_deg: float,
    pitch_deg: float,
    fov_mode: ActiveVisionFovMode,
) -> ActiveVisionCameraState:
    return ActiveVisionCameraState(
        camera_id="CAM-01",
        resource_id="INT-01",
        state_timestamp=timestamp,
        yaw_deg=yaw_deg,
        pitch_deg=pitch_deg,
        yaw_rate_deg_s=0.0,
        pitch_rate_deg_s=0.0,
        yaw_limits_deg=(-180.0, 180.0),
        pitch_limits_deg=(-89.9, 89.9),
        max_yaw_rate_deg_s=60.0,
        max_pitch_rate_deg_s=60.0,
        max_slew_deg_s=80.0,
        current_fov_mode=fov_mode,
        wide_horizontal_fov_deg=90.0,
        zoom_horizontal_fov_deg=30.0,
    )


def _action(
    *,
    issued: float,
    yaw_delta: float,
    pitch_delta: float,
    fov_mode: ActiveVisionFovMode,
    reason: str,
) -> ActiveVisionActionV1:
    return ActiveVisionActionV1(
        camera_id="CAM-01",
        issued_timestamp=issued,
        expires_timestamp=issued + 0.25,
        plan_version=7,
        coalition_version=3,
        communication_version=11,
        intent=ActiveVisionIntent.OBSERVE_TARGET,
        yaw_delta_deg=yaw_delta,
        pitch_delta_deg=pitch_delta,
        fov_mode=fov_mode,
        target_global_track_id="GT-001",
        reason=reason,
    )


def _decision(
    *,
    issued: float = 1.0,
    assist: bool = True,
    projection_rejected: bool = False,
) -> ActiveVisionDecisionV1:
    rule = _action(
        issued=issued,
        yaw_delta=1.0,
        pitch_delta=0.0,
        fov_mode=ActiveVisionFovMode.WIDE,
        reason="rule_observe",
    )
    proposed = _action(
        issued=issued,
        yaw_delta=2.0,
        pitch_delta=-1.0,
        fov_mode=ActiveVisionFovMode.ZOOM,
        reason="model_observe",
    )
    effective = proposed if assist and not projection_rejected else rule
    return ActiveVisionDecisionV1(
        requested_mode=ActiveVisionRuntimeMode.ASSIST,
        effective_mode=(
            ActiveVisionRuntimeMode.ASSIST
            if assist and not projection_rejected
            else ActiveVisionRuntimeMode.DISABLED
        ),
        rule_action=rule,
        requested_action=proposed,
        effective_action=effective,
        fallback_reason=(
            "low_projection_confidence" if projection_rejected else None
        ),
        inference_latency_ms=2.0,
        model_fingerprint="active-vision-model-v1",
        plan_version=7,
        coalition_version=3,
        communication_version=11,
    )


def _rule_decision(*, issued: float = 10.0) -> ActiveVisionDecisionV1:
    rule = _action(
        issued=issued,
        yaw_delta=1.0,
        pitch_delta=0.0,
        fov_mode=ActiveVisionFovMode.WIDE,
        reason="rule_observe",
    )
    return ActiveVisionDecisionV1(
        requested_mode=ActiveVisionRuntimeMode.DISABLED,
        effective_mode=ActiveVisionRuntimeMode.DISABLED,
        rule_action=rule,
        requested_action=None,
        effective_action=rule,
        fallback_reason="learning_disabled",
        inference_latency_ms=0.0,
        model_fingerprint=None,
        plan_version=7,
        coalition_version=3,
        communication_version=11,
    )


def _snapshot(*, issued: float = 1.0) -> ActiveVisionSnapshotV1:
    return ActiveVisionSnapshotV1(
        snapshot_timestamp=issued,
        plan=ActiveVisionPlanReference(
            plan_version=7,
            coalition_version=3,
            assignments=(
                ActiveVisionAssignmentReference(
                    resource_id="INT-01",
                    camera_id="CAM-01",
                    global_track_id="GT-001",
                ),
            ),
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=11,
            plan_version=7,
            coalition_version=3,
            update_timestamp=issued,
            healthy=True,
        ),
        tracks=(
            ActiveVisionTrackReference(
                global_track_id="GT-001",
                track_version=4,
                measurement_timestamp=issued - 0.05,
            ),
        ),
        cameras=(
            _camera_state(
                timestamp=issued - 0.05,
                yaw_deg=10.0,
                pitch_deg=-5.0,
                fov_mode=ActiveVisionFovMode.WIDE,
            ),
        ),
        projections=(),
    )


def _command_payload(
    action: ActiveVisionActionV1,
    *,
    requested_mode: str,
    effective_mode: str,
) -> dict[str, object]:
    horizontal_fov = (
        90.0 if action.fov_mode is ActiveVisionFovMode.WIDE else 30.0
    )
    return {
        "payload_version": CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION,
        "camera_id": action.camera_id,
        "resource_id": "INT-01",
        "issued_timestamp": action.issued_timestamp,
        "expires_timestamp": action.expires_timestamp,
        "plan_version": action.plan_version,
        "coalition_version": action.coalition_version,
        "communication_version": action.communication_version,
        "intent": action.intent.value,
        "aim_point_ned": [100.0, 20.0, -10.0],
        "horizontal_fov_deg": horizontal_fov,
        "fov_mode": action.fov_mode.value,
        "target_global_track_id": action.target_global_track_id,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "reason": action.reason,
    }


def _runtime_command(
    decision: ActiveVisionDecisionV1 | None = None,
) -> SimpleNamespace:
    selected = decision or _decision()
    payload = _command_payload(
        selected.effective_action,
        requested_mode=selected.requested_mode.value,
        effective_mode=selected.effective_mode.value,
    )
    payload.pop("payload_version")
    payload["aim_point_ned"] = np.asarray(payload["aim_point_ned"], dtype=float)
    return SimpleNamespace(**payload)


def _runtime_ack_payload(
    command: SimpleNamespace,
    *,
    ack_timestamp: float = 1.05,
) -> dict[str, object]:
    return {
        "camera_id": command.camera_id,
        "resource_id": command.resource_id,
        "issued_timestamp": command.issued_timestamp,
        "ack_timestamp": ack_timestamp,
        "expires_timestamp": command.expires_timestamp,
        "plan_version": command.plan_version,
        "coalition_version": command.coalition_version,
        "communication_version": command.communication_version,
        "command_version": command.communication_version,
        "intent": command.intent,
        "target_global_track_id": command.target_global_track_id,
        "requested_mode": command.requested_mode,
        "effective_mode": command.effective_mode,
        "status": "applied",
        "reason": "accepted",
    }


def _runtime_camera_state(
    *,
    timestamp: float = 1.05,
    last_plan_version: int = 7,
    last_coalition_version: int = 3,
    last_communication_version: int = 11,
) -> SimpleNamespace:
    return SimpleNamespace(
        camera_id="CAM-01",
        resource_id="INT-01",
        platform_kind="interceptor",
        timestamp=timestamp,
        yaw_deg=12.0,
        pitch_deg=-6.0,
        horizontal_fov_deg=30.0,
        fov_mode="zoom",
        last_plan_version=last_plan_version,
        last_coalition_version=last_coalition_version,
        last_communication_version=last_communication_version,
    )


def _main_runtime_trace(
    *,
    post_command_camera_state: SimpleNamespace | None | object = ...,
) -> ActiveVisionA3AdoptionTrace:
    decision = _decision()
    command = _runtime_command(decision)
    runtime_state = (
        _runtime_camera_state()
        if post_command_camera_state is ...
        else post_command_camera_state
    )
    return assemble_active_vision_a3_adoption_trace(
        comparison_key="nominal-scale5-seed1000-window0",
        scenario_id="nominal",
        scale=5,
        seed=1000,
        window_index=0,
        sample_key="episode-001:active-vision:000001:CAM-01",
        pairing_context_sha256=_digest("9"),
        source_event_log_sha256=_digest("8"),
        snapshot=_snapshot(),
        decision=decision,
        issued_command=command,
        runtime_ack_payload=_runtime_ack_payload(command),
        post_command_camera_state=runtime_state,
        policy_evaluated=True,
        policy_evaluated_timestamp=0.99,
        model_fingerprint="active-vision-model-v1",
        bundle_manifest_sha256=_digest("a"),
        bundle_weights_sha256=_digest("b"),
        implementation_sha256=_digest("c"),
        source_git_commit="d" * 40,
        runtime_ack_evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        camera_feedback_evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        camera_state_source_sequence=42,
    )


def _main_runtime_rule_trace(
    candidate_trace: ActiveVisionA3AdoptionTrace,
    *,
    rule_decision: ActiveVisionDecisionV1 | None = None,
    runtime_ack_payload: Mapping[str, object] | ActiveVisionRuntimeAckV1 | None | object = ...,
    post_command_camera_state: SimpleNamespace | None | object = ...,
    source_event_log_sha256: str | None = None,
    online_truth_use_count: int = 0,
    global_track_id_rewrite_count: int = 0,
) -> ActiveVisionA3RuleArmTrace:
    decision = rule_decision or _rule_decision()
    command = _runtime_command(decision)
    ack = (
        _runtime_ack_payload(command, ack_timestamp=10.05)
        if runtime_ack_payload is ...
        else runtime_ack_payload
    )
    runtime_state = (
        SimpleNamespace(
            camera_id="CAM-01",
            resource_id="INT-01",
            platform_kind="interceptor",
            timestamp=10.05,
            yaw_deg=11.0,
            pitch_deg=-5.0,
            horizontal_fov_deg=90.0,
            fov_mode="wide",
            last_plan_version=7,
            last_coalition_version=3,
            last_communication_version=11,
        )
        if post_command_camera_state is ...
        else post_command_camera_state
    )
    return assemble_active_vision_a3_rule_arm_trace(
        comparison_key=candidate_trace.comparison_key,
        scenario_id=candidate_trace.scenario_id,
        scale=candidate_trace.scale,
        seed=candidate_trace.seed,
        window_index=candidate_trace.window_index,
        sample_key="episode-r0:active-vision:000001:CAM-01",
        pairing_context_sha256=candidate_trace.pairing_context_sha256,
        source_event_log_sha256=(
            _digest("7")
            if source_event_log_sha256 is None
            else source_event_log_sha256
        ),
        snapshot=_snapshot(issued=10.0),
        rule_decision=decision,
        issued_command=command,
        runtime_ack_payload=ack,
        post_command_camera_state=runtime_state,
        camera_state_source_sequence=142,
        online_truth_use_count=online_truth_use_count,
        global_track_id_rewrite_count=global_track_id_rewrite_count,
    )


def _ack(*, sample_key: str, issued: float) -> ActiveVisionRuntimeAckV1:
    return ActiveVisionRuntimeAckV1(
        sample_key=sample_key,
        camera_id="CAM-01",
        command_version=11,
        ack_timestamp=issued + 0.05,
        accepted=True,
        status_code="accepted",
        plan_version=7,
        coalition_version=3,
        communication_version=11,
    )


def _feedback(
    *,
    timestamp: float,
    yaw_deg: float,
    pitch_deg: float,
    fov_mode: ActiveVisionFovMode,
) -> ActiveVisionCameraFeedbackV1:
    return ActiveVisionCameraFeedbackV1(
        camera_state=_camera_state(
            timestamp=timestamp,
            yaw_deg=yaw_deg,
            pitch_deg=pitch_deg,
            fov_mode=fov_mode,
        ),
        last_accepted_command_version=11,
    )


def _pose_lineage(
    feedback: ActiveVisionCameraFeedbackV1,
    *,
    evidence_kind: str,
) -> ActiveVisionA3CameraPoseLineage:
    state = feedback.camera_state
    horizontal_fov = (
        state.wide_horizontal_fov_deg
        if state.current_fov_mode is ActiveVisionFovMode.WIDE
        else state.zoom_horizontal_fov_deg
    )
    return ActiveVisionA3CameraPoseLineage(
        camera_id=state.camera_id,
        resource_id=state.resource_id,
        state_timestamp=state.state_timestamp,
        yaw_deg=state.yaw_deg,
        pitch_deg=state.pitch_deg,
        horizontal_fov_deg=horizontal_fov,
        fov_mode=state.current_fov_mode.value,
        last_plan_version=7,
        last_coalition_version=3,
        last_communication_version=11,
        evidence_kind=evidence_kind,
        source_sequence=101,
    )


def _trace(
    *,
    decision: ActiveVisionDecisionV1 | None = None,
    runtime_ack: ActiveVisionRuntimeAckV1 | None | object = ...,
    camera_feedback: ActiveVisionCameraFeedbackV1 | None | object = ...,
    ack_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
    feedback_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
    synthetic_fixture: bool = False,
    online_truth_use_count: int = 0,
    command_issued: bool = True,
) -> ActiveVisionA3AdoptionTrace:
    selected = decision or _decision()
    sample_key = "episode-001:active-vision:000001:CAM-01"
    issued = selected.effective_action.issued_timestamp
    ack = _ack(sample_key=sample_key, issued=issued) if runtime_ack is ... else runtime_ack
    feedback = (
        _feedback(
            timestamp=issued + 0.05,
            yaw_deg=12.0 if selected.effective_mode is ActiveVisionRuntimeMode.ASSIST else 11.0,
            pitch_deg=-6.0 if selected.effective_mode is ActiveVisionRuntimeMode.ASSIST else -5.0,
            fov_mode=selected.effective_action.fov_mode,
        )
        if camera_feedback is ...
        else camera_feedback
    )
    if not command_issued:
        ack = None
        feedback = None
        ack_kind = UNAVAILABLE_EVIDENCE_KIND
        feedback_kind = UNAVAILABLE_EVIDENCE_KIND
    return ActiveVisionA3AdoptionTrace(
        comparison_key="nominal-scale5-seed1000-window0",
        scenario_id="nominal",
        scale=5,
        seed=1000,
        window_index=0,
        sample_key=sample_key,
        camera_id="CAM-01",
        resource_id="INT-01",
        pairing_context_sha256=_digest("9"),
        source_event_log_sha256=_digest("8"),
        policy_evaluated=True,
        policy_evaluated_timestamp=issued - 0.01,
        model_fingerprint="active-vision-model-v1",
        bundle_manifest_sha256=_digest("a"),
        bundle_weights_sha256=_digest("b"),
        implementation_sha256=_digest("c"),
        source_git_commit="d" * 40,
        decision=selected,
        pre_command_camera_state=_camera_state(
            timestamp=issued - 0.05,
            yaw_deg=10.0,
            pitch_deg=-5.0,
            fov_mode=ActiveVisionFovMode.WIDE,
        ),
        issued_command_payload=(
            _command_payload(
                selected.effective_action,
                requested_mode=selected.requested_mode.value,
                effective_mode=selected.effective_mode.value,
            )
            if command_issued
            else None
        ),
        runtime_ack=ack,
        camera_feedback=feedback,
        camera_pose_lineage=(
            None
            if feedback is None
            else _pose_lineage(feedback, evidence_kind=feedback_kind)
        ),
        runtime_ack_evidence_kind=ack_kind,
        camera_feedback_evidence_kind=feedback_kind,
        synthetic_fixture=synthetic_fixture,
        pose_tolerance_deg=0.25,
        online_truth_use_count=online_truth_use_count,
    )


def _outcome(*, available: bool = True) -> ActiveVisionA3OutcomeEvidence:
    if not available:
        return ActiveVisionA3OutcomeEvidence(
            association_outcome_available=False,
            coverage_outcome_available=False,
            observation_frame_count=10,
            association_evaluable_frame_count=None,
            association_locked_count=None,
            association_ambiguous_count=None,
            association_hold_count=None,
            association_reacquire_count=None,
            assigned_reference_count=None,
            visible_assigned_reference_count=None,
        )
    return ActiveVisionA3OutcomeEvidence(
        association_outcome_available=True,
        coverage_outcome_available=True,
        observation_frame_count=10,
        association_evaluable_frame_count=10,
        association_locked_count=8,
        association_ambiguous_count=1,
        association_hold_count=0,
        association_reacquire_count=1,
        assigned_reference_count=10,
        visible_assigned_reference_count=8,
    )


def _observation_frames(
    *,
    start_timestamp: float,
    evidence_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
    available: bool = True,
) -> tuple[ActiveVisionA3AnonymousObservationFrame, ...]:
    offsets = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.85)
    frames: list[ActiveVisionA3AnonymousObservationFrame] = []
    for index, offset in enumerate(offsets):
        tracklet_key = f"INT-01/CAM-01:trk-{index:03d}"
        if not available:
            bindings: tuple[ActiveVisionA3BindingEvidence, ...] = ()
        else:
            state = "bound" if index < 8 else "ambiguous" if index == 8 else "unbound"
            bindings = (
                ActiveVisionA3BindingEvidence(
                    cluster_key=f"cluster-{index:03d}",
                    global_track_id="GT-001" if state == "bound" else None,
                    decision_state=state,
                    supporting_tracklet_keys=(tracklet_key,),
                ),
            )
        measurement_timestamp = start_timestamp + offset
        frames.append(
            ActiveVisionA3AnonymousObservationFrame(
                frame_key=f"frame-{start_timestamp:.2f}-{index:03d}",
                camera_id="CAM-01",
                resource_id="INT-01",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=measurement_timestamp + 0.01,
                plan_version=7,
                coalition_version=3,
                communication_version=11,
                target_global_track_id="GT-001",
                observed_tracklet_keys=(tracklet_key,),
                bindings=bindings,
                evidence_kind=evidence_kind,
                source_sequence=200 + index,
            )
        )
    return tuple(frames)


def _local_observation(
    *,
    local_track_id: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> CameraLocalTracklet:
    return CameraLocalTracklet(
        resource_id="INT-01",
        camera_id="CAM-01",
        local_track_id=local_track_id,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        center_px=np.asarray([960.0, 540.0], dtype=float),
        covariance_px=np.diag([4.0, 4.0]),
        bbox_xyxy=(940.0, 520.0, 980.0, 560.0),
        confidence=0.9,
        source_observation_id=f"obs-{local_track_id}",
        metadata={"detector_backend": "anonymous-runtime"},
    )


def _zero_detection_frame(
    *,
    frame_key: str = "zero-frame-001",
    measurement_timestamp: float = 1.15,
    arrival_timestamp: float = 1.16,
    target_global_track_id: str | None = "GT-001",
    center_global_track_ids: tuple[str, ...] = ("GT-001",),
    evidence_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
    source_sequence: int = 300,
) -> ActiveVisionA3AnonymousObservationFrame:
    return active_vision_a3_zero_detection_frame(
        frame_key=frame_key,
        camera_id="CAM-01",
        resource_id="INT-01",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        plan_version=7,
        coalition_version=3,
        communication_version=11,
        target_global_track_id=target_global_track_id,
        center_global_track_ids=center_global_track_ids,
        evidence_kind=evidence_kind,
        source_sequence=source_sequence,
    )


def _candidate_window(
    trace: ActiveVisionA3AdoptionTrace,
    *,
    outcome_available: bool = True,
    observation_kind: str = RUNTIME_OBSERVED_EVIDENCE_KIND,
) -> ActiveVisionA3PhysicalObservationWindow:
    assert trace.runtime_ack is not None
    assert trace.camera_feedback is not None
    assert trace.camera_pose_lineage is not None
    assert trace.issued_command_payload is not None
    frames = _observation_frames(
        start_timestamp=1.15,
        evidence_kind=observation_kind,
        available=outcome_available,
    )
    return ActiveVisionA3PhysicalObservationWindow(
        arm=ActiveVisionA3WindowArm.A3,
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
        source_event_log_sha256=trace.source_event_log_sha256,
        command_source=ActiveVisionA3CommandSource.MODEL_ASSIST,
        effective_action=trace.decision.effective_action,
        pre_command_camera_state=trace.pre_command_camera_state,
        issued_command_payload=trace.issued_command_payload,
        runtime_ack=trace.runtime_ack,
        camera_feedback=trace.camera_feedback,
        camera_pose_lineage=trace.camera_pose_lineage,
        runtime_ack_evidence_kind=trace.runtime_ack_evidence_kind,
        camera_feedback_evidence_kind=trace.camera_feedback_evidence_kind,
        observation_evidence_kind=observation_kind,
        synthetic_fixture=trace.synthetic_fixture,
        pose_tolerance_deg=trace.pose_tolerance_deg,
        window_start_timestamp=1.10,
        window_end_timestamp=2.10,
        first_measurement_timestamp=1.15,
        last_measurement_timestamp=2.00,
        first_arrival_timestamp=1.16,
        last_arrival_timestamp=2.01,
        observation_frames=frames,
        outcome=_outcome(available=outcome_available),
        adoption_trace_sha256=trace.trace_sha256,
        online_truth_use_count=trace.online_truth_use_count,
        global_track_id_rewrite_count=trace.global_track_id_rewrite_count,
    )


def _candidate_stage_evidence(
    trace: ActiveVisionA3AdoptionTrace,
    *,
    runtime_event_inventory_complete: bool = True,
    runtime_ack_timestamp: float | None | object = ...,
    runtime_ack_applied: bool | None | object = ...,
    camera_feedback_timestamp: float | None | object = ...,
    observation_inventory_complete: bool = True,
    anonymous_observation_frame_count: int | None = 0,
    first_measurement_timestamp: float | None = None,
    last_measurement_timestamp: float | None = None,
    first_arrival_timestamp: float | None = None,
    last_arrival_timestamp: float | None = None,
    physical_window_status: ActiveVisionA3CandidatePhysicalWindowStatus = (
        ActiveVisionA3CandidatePhysicalWindowStatus.MISSING
    ),
    inventory_start_timestamp: float = 0.90,
    inventory_end_timestamp: float = 2.20,
) -> ActiveVisionA3CandidateStageEvidence:
    command = trace.issued_command_payload
    ack = trace.runtime_ack
    feedback = trace.camera_feedback
    ack_timestamp = (
        None if ack is None else ack.ack_timestamp
    ) if runtime_ack_timestamp is ... else runtime_ack_timestamp
    ack_applied = (
        None if ack is None else trace.runtime_ack_applied
    ) if runtime_ack_applied is ... else runtime_ack_applied
    feedback_timestamp = (
        None if feedback is None else feedback.camera_state.state_timestamp
    ) if camera_feedback_timestamp is ... else camera_feedback_timestamp
    return ActiveVisionA3CandidateStageEvidence(
        comparison_key=trace.comparison_key,
        scenario_id=trace.scenario_id,
        scale=trace.scale,
        seed=trace.seed,
        window_index=trace.window_index,
        sample_key=trace.sample_key,
        camera_id=trace.camera_id,
        resource_id=trace.resource_id,
        pairing_context_sha256=trace.pairing_context_sha256,
        adoption_trace_sha256=trace.trace_sha256,
        source_event_log_sha256=trace.source_event_log_sha256,
        inventory_start_timestamp=inventory_start_timestamp,
        inventory_end_timestamp=inventory_end_timestamp,
        runtime_event_inventory_complete=runtime_event_inventory_complete,
        command_issued_timestamp=(
            None if command is None else command["issued_timestamp"]
        ),
        command_expires_timestamp=(
            None if command is None else command["expires_timestamp"]
        ),
        runtime_ack_timestamp=ack_timestamp,
        runtime_ack_applied=ack_applied,
        camera_feedback_timestamp=feedback_timestamp,
        observation_inventory_complete=observation_inventory_complete,
        anonymous_observation_frame_count=anonymous_observation_frame_count,
        first_measurement_timestamp=first_measurement_timestamp,
        last_measurement_timestamp=last_measurement_timestamp,
        first_arrival_timestamp=first_arrival_timestamp,
        last_arrival_timestamp=last_arrival_timestamp,
        physical_window_status=physical_window_status,
        evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
    )


def _complete_candidate_stage_evidence(
    trace: ActiveVisionA3AdoptionTrace,
) -> ActiveVisionA3CandidateStageEvidence:
    return _candidate_stage_evidence(
        trace,
        anonymous_observation_frame_count=10,
        first_measurement_timestamp=1.15,
        last_measurement_timestamp=2.00,
        first_arrival_timestamp=1.16,
        last_arrival_timestamp=2.01,
        physical_window_status=(
            ActiveVisionA3CandidatePhysicalWindowStatus.COMPLETE
        ),
    )


def _r0_window(trace: ActiveVisionA3AdoptionTrace) -> ActiveVisionA3PhysicalObservationWindow:
    rule_trace = _main_runtime_rule_trace(trace)
    window = assemble_active_vision_a3_rule_arm_physical_observation_window(
        rule_trace,
        observation_frames=_observation_frames(start_timestamp=10.15),
        window_start_timestamp=10.10,
        window_end_timestamp=11.10,
    )
    assert window is not None
    return window


def _successful_evidence():
    trace = _trace()
    return assemble_active_vision_a3_paired_evidence(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_windows=(_r0_window(trace),),
    )


def _successful_disposition() -> ActiveVisionA3PairingDisposition:
    trace = _trace()
    return attempt_active_vision_a3_pairing(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_windows=(_r0_window(trace),),
    )


def test_actual_adoption_and_same_key_r0_are_d6_audit_eligible() -> None:
    evidence = _successful_evidence()

    assert evidence.model_action_adopted is True
    assert evidence.d6_benefit_audit_eligible is True
    assert evidence.blocker_codes == ()
    assert evidence.adoption_trace.layer_status == {
        "policy_evaluated": True,
        "command_proposed": True,
        "deterministic_projection_status": "accepted",
        "command_issued": True,
        "runtime_ack_received": True,
        "runtime_ack_applied": True,
        "camera_feedback_received": True,
        "camera_pose_lineage_received": True,
        "pose_applied": True,
    }
    permissions = evidence.permissions.to_dict()
    assert permissions["d6_benefit_audit_input_allowed"] is True
    assert all(
        value is False
        for name, value in permissions.items()
        if name != "d6_benefit_audit_input_allowed"
    )


def test_pairing_disposition_references_existing_pairable_evidence() -> None:
    trace = _trace()
    candidate = _candidate_window(trace)
    r0 = _r0_window(trace)

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=candidate,
        same_key_r0_windows=(r0,),
    )

    assert disposition.pairable is True
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.PAIRABLE
    )
    assert disposition.detail_codes == ()
    assert disposition.paired_evidence is not None
    assert disposition.paired_evidence.candidate_window is candidate
    assert disposition.paired_evidence.same_key_r0_window is r0
    assert disposition.adoption_trace_sha256 == trace.trace_sha256
    assert disposition.to_dict()["paired_evidence"]["permissions"] == {
        "d6_benefit_audit_input_allowed": True,
        "active_vision_assist_authority": False,
        "camera_command_authority": False,
        "assignment_authority": False,
        "failover_authority": False,
        "control_authority": False,
        "model_promotion_authority": False,
        "global_track_id_mutation_authority": False,
        "g1_authorization_granted": False,
    }


def test_pairing_disposition_reports_model_action_not_adopted() -> None:
    trace = _trace(decision=_decision(assist=False, projection_rejected=True))

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
    )

    assert disposition.pairable is False
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.MODEL_ACTION_NOT_ADOPTED
    )
    assert "deterministic_projection_not_accepted" in disposition.detail_codes
    assert disposition.paired_evidence is None


def test_pairing_disposition_keeps_missing_candidate_window_coarse() -> None:
    trace = _trace()

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
    )

    assert disposition.pairable is False
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.CANDIDATE_PHYSICAL_WINDOW_MISSING
    )
    assert disposition.detail_codes == ("candidate_physical_window_missing",)
    assert disposition.paired_evidence is None


def test_pairing_disposition_refines_only_explicit_candidate_stage_evidence() -> None:
    trace = _trace()
    stage = _candidate_stage_evidence(trace)

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.CANDIDATE_PHYSICAL_WINDOW_MISSING
    )
    assert disposition.detail_codes == ("candidate_physical_window_missing",)
    assert disposition.candidate_stage_reason_codes == (
        ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_MISSING,
        ActiveVisionA3CandidateStageReasonCode.PHYSICAL_WINDOW_CONFIRMED_MISSING,
    )
    assert disposition.candidate_stage_evidence is stage
    assert disposition.pairable is False
    assert disposition.paired_evidence is None


def test_incomplete_inventory_does_not_guess_candidate_stage() -> None:
    trace = _trace()
    stage = _candidate_stage_evidence(
        trace,
        runtime_event_inventory_complete=False,
        observation_inventory_complete=False,
        anonymous_observation_frame_count=None,
        physical_window_status=(
            ActiveVisionA3CandidatePhysicalWindowStatus.UNKNOWN
        ),
    )

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert disposition.detail_codes == ("candidate_physical_window_missing",)
    assert disposition.candidate_stage_reason_codes == ()


def test_partial_runtime_inventory_only_emits_complete_observation_reason() -> None:
    trace = _trace(
        runtime_ack=None,
        camera_feedback=None,
        ack_kind=UNAVAILABLE_EVIDENCE_KIND,
        feedback_kind=UNAVAILABLE_EVIDENCE_KIND,
    )
    stage = _candidate_stage_evidence(
        trace,
        runtime_event_inventory_complete=False,
        runtime_ack_timestamp=1.10,
        runtime_ack_applied=False,
    )

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert disposition.candidate_stage_reason_codes == (
        ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_MISSING,
    )


def test_partial_observation_inventory_does_not_refine_observation_stage() -> None:
    trace = _trace()
    stage = _candidate_stage_evidence(
        trace,
        observation_inventory_complete=False,
        anonymous_observation_frame_count=2,
        first_measurement_timestamp=1.20,
        last_measurement_timestamp=1.10,
        first_arrival_timestamp=1.21,
        last_arrival_timestamp=1.11,
        physical_window_status=(
            ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
        ),
    )

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert disposition.candidate_stage_reason_codes == ()


def test_candidate_stage_distinguishes_ack_expiry_feedback_and_observation() -> None:
    trace = _trace(
        runtime_ack=None,
        camera_feedback=None,
        ack_kind=UNAVAILABLE_EVIDENCE_KIND,
        feedback_kind=UNAVAILABLE_EVIDENCE_KIND,
    )
    stage = _candidate_stage_evidence(trace)

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.MODEL_ACTION_NOT_ADOPTED
    )
    assert set(disposition.candidate_stage_reason_codes) == {
        ActiveVisionA3CandidateStageReasonCode.RUNTIME_ACK_MISSING,
        ActiveVisionA3CandidateStageReasonCode.COMMAND_WINDOW_EXPIRED,
        ActiveVisionA3CandidateStageReasonCode.CAMERA_FEEDBACK_MISSING,
        ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_MISSING,
        ActiveVisionA3CandidateStageReasonCode.PHYSICAL_WINDOW_CONFIRMED_MISSING,
    }
    assert disposition.pairable is False
    assert disposition.paired_evidence is None


def test_candidate_stage_distinguishes_rejected_runtime_confirmation() -> None:
    trace = _trace(
        runtime_ack=None,
        camera_feedback=None,
        ack_kind=UNAVAILABLE_EVIDENCE_KIND,
        feedback_kind=UNAVAILABLE_EVIDENCE_KIND,
    )
    stage = _candidate_stage_evidence(
        trace,
        runtime_ack_timestamp=1.10,
        runtime_ack_applied=False,
    )

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert (
        ActiveVisionA3CandidateStageReasonCode.RUNTIME_CONFIRMATION_MISSING
        in disposition.candidate_stage_reason_codes
    )
    assert (
        ActiveVisionA3CandidateStageReasonCode.RUNTIME_ACK_MISSING
        not in disposition.candidate_stage_reason_codes
    )


def test_candidate_stage_distinguishes_timing_and_incomplete_window() -> None:
    trace = _trace()
    stage = _candidate_stage_evidence(
        trace,
        anonymous_observation_frame_count=2,
        first_measurement_timestamp=1.00,
        last_measurement_timestamp=1.20,
        first_arrival_timestamp=1.01,
        last_arrival_timestamp=1.21,
        physical_window_status=(
            ActiveVisionA3CandidatePhysicalWindowStatus.INCOMPLETE
        ),
    )

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=stage,
    )

    assert disposition.candidate_stage_reason_codes == (
        ActiveVisionA3CandidateStageReasonCode.COMMAND_TIMING_MISMATCH,
        ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_INCOMPLETE,
        ActiveVisionA3CandidateStageReasonCode.PHYSICAL_WINDOW_INCOMPLETE,
    )
    assert disposition.pairable is False


def test_complete_candidate_stage_evidence_is_pairable_and_permission_neutral() -> None:
    trace = _trace()
    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=_complete_candidate_stage_evidence(trace),
    )

    assert disposition.pairable is True
    assert disposition.candidate_stage_reason_codes == ()
    assert disposition.paired_evidence is not None
    permissions = disposition.paired_evidence.permissions.to_dict()
    assert permissions["d6_benefit_audit_input_allowed"] is True
    assert all(
        value is False
        for name, value in permissions.items()
        if name != "d6_benefit_audit_input_allowed"
    )


def test_pairing_disposition_reports_missing_same_key_r0() -> None:
    trace = _trace()

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_windows=(),
    )

    assert disposition.pairable is False
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.SAME_KEY_R0_WINDOW_MISSING
    )
    assert disposition.detail_codes == ("same_key_r0_window_missing",)
    assert disposition.paired_evidence is None


def test_pairing_disposition_reports_duplicate_or_ambiguous_r0() -> None:
    trace = _trace()
    r0 = _r0_window(trace)

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_windows=(r0, r0),
    )

    assert disposition.pairable is False
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.SAME_KEY_R0_DUPLICATE_OR_AMBIGUOUS
    )
    assert disposition.detail_codes == ("same_key_r0_duplicate",)
    assert disposition.paired_evidence is None


def test_pairing_disposition_reports_key_or_configuration_mismatch() -> None:
    trace = _trace()
    inconsistent_r0 = replace(
        _r0_window(trace),
        comparison_key="other-comparison-key",
    )

    disposition = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_windows=(inconsistent_r0,),
    )

    assert disposition.pairable is False
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.PAIRING_KEY_OR_CONFIGURATION_MISMATCH
    )
    assert disposition.detail_codes == ("same_key_r0_identity_mismatch",)
    assert disposition.paired_evidence is None


def test_pairing_disposition_reports_tampered_evidence_contract() -> None:
    trace = _trace()
    tampered_candidate = _candidate_window(trace).to_dict()
    tampered_candidate["outcome"]["association_locked_count"] = 0

    disposition = attempt_active_vision_a3_pairing(
        trace.to_dict(),
        candidate_window=tampered_candidate,
        same_key_r0_windows=(_r0_window(trace).to_dict(),),
    )

    assert disposition.pairable is False
    assert (
        disposition.reason_code
        is ActiveVisionA3PairingDispositionCode.EVIDENCE_CONTRACT_INVALID
    )
    assert set(disposition.detail_codes).intersection(
        {
            "physical_window_outcome_recomputation_mismatch",
            "window_hash_mismatch",
            "window_recomputation_mismatch",
        }
    )
    assert disposition.paired_evidence is None


@pytest.mark.parametrize("pairable", (True, False))
def test_pairing_disposition_mapping_round_trip_is_strict(
    pairable: bool,
) -> None:
    if pairable:
        original = _successful_disposition()
    else:
        trace = _trace()
        original = attempt_active_vision_a3_pairing(
            trace,
            candidate_window=None,
            same_key_r0_windows=(_r0_window(trace),),
        )
    payload = deepcopy(original.to_dict())

    validated = validate_active_vision_a3_pairing_disposition(payload)
    reconstructed = ActiveVisionA3PairingDisposition.from_mapping(payload)

    assert validated.to_dict() == original.to_dict()
    assert reconstructed.to_dict() == original.to_dict()
    assert validated is not original
    assert reconstructed is not original


def test_candidate_stage_evidence_persisted_round_trip_is_strict() -> None:
    original = _candidate_stage_evidence(_trace())
    payload = deepcopy(original.to_dict())

    validated = validate_active_vision_a3_candidate_stage_evidence(payload)
    reconstructed = ActiveVisionA3CandidateStageEvidence.from_mapping(payload)

    assert validated.to_dict() == original.to_dict()
    assert reconstructed.to_dict() == original.to_dict()
    assert validated is not original
    assert reconstructed is not original


def test_refined_disposition_persisted_round_trip_is_strict() -> None:
    trace = _trace()
    original = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=_candidate_stage_evidence(trace),
    )
    payload = deepcopy(original.to_dict())

    validated = validate_active_vision_a3_pairing_disposition(payload)

    assert validated.to_dict() == original.to_dict()
    assert validated.candidate_stage_reason_codes == (
        ActiveVisionA3CandidateStageReasonCode.ANONYMOUS_OBSERVATION_MISSING,
        ActiveVisionA3CandidateStageReasonCode.PHYSICAL_WINDOW_CONFIRMED_MISSING,
    )


def test_legacy_v1_disposition_remains_strictly_loadable() -> None:
    trace = _trace()
    payload = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
    ).to_dict()
    payload.pop("candidate_stage_reason_codes")
    payload.pop("candidate_stage_evidence")
    payload["schema_version"] = (
        ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION
    )
    payload.pop("content_sha256")
    payload["content_sha256"] = _payload_sha256(payload)

    validated = validate_active_vision_a3_pairing_disposition(payload)

    assert validated.to_dict() == payload
    assert validated.candidate_stage_reason_codes == ()
    assert validated.candidate_stage_evidence is None


def test_legacy_v1_disposition_rejects_v2_stage_fields() -> None:
    trace = _trace()
    payload = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
    ).to_dict()
    payload["schema_version"] = (
        ACTIVE_VISION_A3_PAIRING_DISPOSITION_LEGACY_SCHEMA_VERSION
    )
    payload.pop("content_sha256")
    payload["content_sha256"] = _payload_sha256(payload)

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "evidence_fields_mismatch"


def test_candidate_stage_evidence_tamper_is_rejected() -> None:
    payload = _candidate_stage_evidence(_trace()).to_dict()
    payload["inventory_end_timestamp"] = 3.0

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_candidate_stage_evidence(payload)

    assert exc.value.code == "candidate_stage_evidence_hash_mismatch"


def test_rehashed_candidate_stage_reason_tamper_is_rejected() -> None:
    trace = _trace()
    payload = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=_candidate_stage_evidence(trace),
    ).to_dict()
    payload["candidate_stage_reason_codes"] = [
        ActiveVisionA3CandidateStageReasonCode.RUNTIME_ACK_MISSING.value
    ]
    payload.pop("content_sha256")
    payload["content_sha256"] = _payload_sha256(payload)

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_stage_reason_mismatch"


def test_unknown_candidate_stage_reason_fails_closed() -> None:
    trace = _trace()
    payload = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
        candidate_stage_evidence=_candidate_stage_evidence(trace),
    ).to_dict()
    payload["candidate_stage_reason_codes"] = ["candidate_unknown_stage"]
    payload.pop("content_sha256")
    payload["content_sha256"] = _payload_sha256(payload)

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_stage_reason_unsupported"


def test_pairing_disposition_content_hash_tamper_is_rejected() -> None:
    payload = _successful_disposition().to_dict()
    payload["content_sha256"] = "0" * 64

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_hash_mismatch"


def test_pairing_disposition_rejects_rehashed_reference_mismatch() -> None:
    payload = _successful_disposition().to_dict()
    del payload["content_sha256"]
    payload["comparison_key"] = "rehashed-but-inconsistent"
    payload["content_sha256"] = _payload_sha256(payload)

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_reference_mismatch"


@pytest.mark.parametrize("mutation", ("add", "remove"))
def test_pairing_disposition_exact_fields_are_required(mutation: str) -> None:
    payload = _successful_disposition().to_dict()
    if mutation == "add":
        payload["unexpected_field"] = "forbidden"
    else:
        del payload["reason_code"]

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "evidence_fields_mismatch"


def test_pairable_disposition_requires_paired_evidence() -> None:
    payload = _successful_disposition().to_dict()
    payload["paired_evidence"] = None

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_evidence_missing"


def test_unpairable_disposition_forbids_paired_evidence() -> None:
    trace = _trace()
    payload = attempt_active_vision_a3_pairing(
        trace,
        candidate_window=None,
        same_key_r0_windows=(_r0_window(trace),),
    ).to_dict()
    payload["paired_evidence"] = _successful_evidence().to_dict()

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_evidence_forbidden"


def test_pairing_disposition_rejects_nested_permission_tamper() -> None:
    payload = _successful_disposition().to_dict()
    payload["paired_evidence"]["permissions"]["control_authority"] = True

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "audit_input_recomputation_mismatch"


def test_pairing_disposition_requires_exact_json_field_types() -> None:
    payload = _successful_disposition().to_dict()
    payload["scale"] = 5.0

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_pairing_disposition(payload)

    assert exc.value.code == "pairing_disposition_field_type_invalid"


def test_independent_rule_arm_episode_roundtrip_builds_unique_r0_window() -> None:
    candidate_trace = _main_runtime_trace()
    candidate_frame = active_vision_a3_observation_frame(
        frame_key="candidate-frame-001",
        observations=(
            _local_observation(
                local_track_id="candidate-local-001",
                measurement_timestamp=1.15,
                arrival_timestamp=1.16,
            ),
        ),
        bindings=(
            ActiveVisionA3BindingEvidence(
                cluster_key="candidate-cluster-001",
                global_track_id="GT-001",
                decision_state="bound",
                supporting_tracklet_keys=(
                    "INT-01/CAM-01:candidate-local-001",
                ),
            ),
        ),
        target_global_track_id="GT-001",
        center_global_track_ids=("GT-001",),
        plan_version=7,
        coalition_version=3,
        communication_version=11,
        evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        source_sequence=143,
    )
    candidate_window = assemble_active_vision_a3_physical_observation_window(
        candidate_trace,
        arm=ActiveVisionA3WindowArm.A3,
        observation_frames=(candidate_frame,),
        window_start_timestamp=1.10,
        window_end_timestamp=2.10,
    )
    assert candidate_window is not None

    original_r0_trace = _main_runtime_rule_trace(candidate_trace)
    serialized_r0_trace = deepcopy(original_r0_trace.to_dict())
    assert "model_fingerprint" not in serialized_r0_trace
    assert "bundle_manifest_sha256" not in serialized_r0_trace
    assert "bundle_weights_sha256" not in serialized_r0_trace
    rebuilt_r0_trace = ActiveVisionA3RuleArmTrace.from_mapping(
        serialized_r0_trace
    )
    assert rebuilt_r0_trace is not original_r0_trace
    assert rebuilt_r0_trace.to_dict() == serialized_r0_trace
    assert (
        rebuilt_r0_trace.pairing_context_sha256
        == candidate_trace.pairing_context_sha256
    )
    assert (
        rebuilt_r0_trace.source_event_log_sha256
        != candidate_trace.source_event_log_sha256
    )

    persisted_frames = tuple(
        ActiveVisionA3AnonymousObservationFrame.from_mapping(
            deepcopy(frame.to_dict())
        )
        for frame in _observation_frames(start_timestamp=10.15)
    )
    r0_window = (
        assemble_active_vision_a3_rule_arm_physical_observation_window(
            rebuilt_r0_trace,
            observation_frames=persisted_frames,
            window_start_timestamp=10.10,
            window_end_timestamp=11.10,
        )
    )
    assert r0_window is not None
    evidence = assemble_active_vision_a3_paired_evidence(
        candidate_trace,
        candidate_window=candidate_window,
        same_key_r0_windows=(r0_window,),
    )

    assert r0_window.arm is ActiveVisionA3WindowArm.R0
    assert (
        r0_window.command_source
        is ActiveVisionA3CommandSource.DETERMINISTIC_RULE
    )
    assert r0_window.adoption_trace_sha256 is None
    assert r0_window.runtime_physical_chain_complete is True
    assert evidence.d6_benefit_audit_eligible is True
    assert evidence.permissions.active_vision_assist_authority is False
    assert evidence.permissions.camera_command_authority is False
    assert evidence.permissions.control_authority is False


def test_duplicate_same_key_r0_windows_fail_closed() -> None:
    trace = _trace()
    candidate = _candidate_window(trace)
    r0 = _r0_window(trace)

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        assemble_active_vision_a3_paired_evidence(
            trace,
            candidate_window=candidate,
            same_key_r0_windows=(r0, r0),
        )

    assert exc.value.code == "same_key_r0_duplicate"


def test_r0_rejects_assist_decision_instead_of_reusing_candidate_trace() -> None:
    candidate_trace = _trace()

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        _main_runtime_rule_trace(
            candidate_trace,
            rule_decision=_decision(issued=10.0),
        )

    assert exc.value.code == "r0_decision_not_deterministic"


@pytest.mark.parametrize(
    ("runtime_ack_payload", "post_camera_state", "expected_code"),
    (
        (None, ..., "r0_runtime_ack_missing"),
        (..., None, "r0_camera_feedback_missing"),
    ),
)
def test_r0_incomplete_ack_or_feedback_fails_closed(
    runtime_ack_payload: object,
    post_camera_state: object,
    expected_code: str,
) -> None:
    candidate_trace = _trace()

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        _main_runtime_rule_trace(
            candidate_trace,
            runtime_ack_payload=runtime_ack_payload,
            post_command_camera_state=post_camera_state,
        )

    assert exc.value.code == expected_code


def test_r0_rejected_ack_and_unapplied_pose_fail_closed() -> None:
    candidate_trace = _trace()
    command = _runtime_command(_rule_decision())
    rejected_ack = _runtime_ack_payload(command, ack_timestamp=10.05)
    rejected_ack["status"] = "rejected"
    rejected_ack["reason"] = "runtime_rejected"

    with pytest.raises(ActiveVisionA3EvidenceError) as rejected:
        _main_runtime_rule_trace(
            candidate_trace,
            runtime_ack_payload=rejected_ack,
        )
    assert rejected.value.code == "r0_runtime_ack_not_applied"

    wrong_pose = SimpleNamespace(
        camera_id="CAM-01",
        resource_id="INT-01",
        platform_kind="interceptor",
        timestamp=10.05,
        yaw_deg=10.0,
        pitch_deg=-5.0,
        horizontal_fov_deg=90.0,
        fov_mode="wide",
        last_plan_version=7,
        last_coalition_version=3,
        last_communication_version=11,
    )
    with pytest.raises(ActiveVisionA3EvidenceError) as unapplied:
        _main_runtime_rule_trace(
            candidate_trace,
            post_command_camera_state=wrong_pose,
        )
    assert unapplied.value.code == "r0_pose_not_applied"


@pytest.mark.parametrize(
    ("counter_name", "expected_code"),
    (
        ("online_truth_use_count", "r0_online_truth_use_forbidden"),
        (
            "global_track_id_rewrite_count",
            "r0_global_track_id_rewrite_forbidden",
        ),
    ),
)
def test_r0_truth_use_or_global_id_rewrite_fails_closed(
    counter_name: str,
    expected_code: str,
) -> None:
    candidate_trace = _trace()

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        _main_runtime_rule_trace(candidate_trace, **{counter_name: 1})

    assert exc.value.code == expected_code


def test_missing_ack_cannot_be_adopted() -> None:
    trace = _trace(
        runtime_ack=None,
        camera_feedback=None,
        ack_kind=UNAVAILABLE_EVIDENCE_KIND,
        feedback_kind=UNAVAILABLE_EVIDENCE_KIND,
    )
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=None,
        same_key_r0_window=_r0_window(trace),
    )

    assert evidence.model_action_adopted is False
    assert "runtime_ack_missing" in evidence.blocker_codes
    assert evidence.d6_benefit_audit_eligible is False


def test_ack_without_applied_pose_cannot_be_adopted() -> None:
    trace = _trace(
        camera_feedback=_feedback(
            timestamp=1.05,
            yaw_deg=10.0,
            pitch_deg=-5.0,
            fov_mode=ActiveVisionFovMode.WIDE,
        )
    )
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=None,
        same_key_r0_window=_r0_window(trace),
    )

    assert trace.runtime_ack_applied is True
    assert trace.pose_applied is False
    assert "pose_not_applied" in evidence.blocker_codes
    assert "candidate_physical_window_missing" in evidence.blocker_codes


def test_rule_fallback_and_projection_rejection_are_not_a3_adoption() -> None:
    trace = _trace(decision=_decision(assist=False, projection_rejected=True))
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=None,
        same_key_r0_window=_r0_window(trace),
    )

    assert trace.deterministic_projection_status.value == "rejected"
    assert trace.command_source is ActiveVisionA3CommandSource.DETERMINISTIC_RULE
    assert "deterministic_projection_not_accepted" in evidence.blocker_codes
    assert "model_command_not_selected" in evidence.blocker_codes


def test_missing_candidate_physical_window_fails_closed() -> None:
    trace = _trace()
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=None,
        same_key_r0_window=_r0_window(trace),
    )

    assert evidence.model_action_adopted is True
    assert "candidate_physical_window_missing" in evidence.blocker_codes
    assert evidence.d6_benefit_audit_eligible is False


def test_model_load_and_proposal_without_command_are_not_adoption() -> None:
    trace = _trace(command_issued=False)
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=None,
        same_key_r0_window=_r0_window(trace),
    )

    assert trace.policy_evaluated is True
    assert trace.command_proposed is True
    assert trace.command_issued is False
    assert "model_command_not_issued" in evidence.blocker_codes
    assert evidence.model_action_adopted is False


def test_missing_same_key_r0_window_fails_closed() -> None:
    trace = _trace()
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_window=None,
    )

    assert "same_key_r0_window_missing" in evidence.blocker_codes
    assert evidence.d6_benefit_audit_eligible is False


def test_missing_association_or_coverage_outcome_fails_closed() -> None:
    trace = _trace()
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=_candidate_window(trace, outcome_available=False),
        same_key_r0_window=_r0_window(trace),
    )

    assert (
        "candidate_association_or_coverage_outcome_unavailable"
        in evidence.blocker_codes
    )


def test_synthetic_existing_ack_and_feedback_are_not_adopted() -> None:
    trace = _trace(
        ack_kind=SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        feedback_kind=SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        synthetic_fixture=True,
    )
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=_candidate_window(
            trace,
            observation_kind=SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        ),
        same_key_r0_window=_r0_window(trace),
    )

    assert trace.runtime_ack_applied is False
    assert trace.pose_applied is False
    assert "runtime_ack_simulated_or_nonruntime" in evidence.blocker_codes
    assert "camera_feedback_simulated_or_nonruntime" in evidence.blocker_codes


def test_truth_pollution_is_rejected_before_field_acceptance() -> None:
    payload = _successful_evidence().to_dict()
    payload["actor_id"] = "intruder-001"

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_evidence(payload)

    assert exc.value.code == "online_truth_identity_forbidden"


def test_online_truth_use_counter_blocks_audit() -> None:
    trace = _trace(online_truth_use_count=1)
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=_candidate_window(trace),
        same_key_r0_window=_r0_window(trace),
    )

    assert "online_truth_use_detected" in evidence.blocker_codes
    assert evidence.d6_benefit_audit_eligible is False


def test_hash_tamper_is_rejected() -> None:
    payload = _successful_evidence().to_dict()
    payload["adoption_trace"]["issued_command_payload"]["aim_point_ned"][0] = 99.0

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_evidence(payload)

    assert exc.value.code in {"trace_hash_mismatch", "trace_recomputation_mismatch"}


def test_ack_version_mismatch_is_rejected() -> None:
    payload = _successful_evidence().to_dict()
    payload["adoption_trace"]["runtime_ack"]["command_version"] = 12

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_evidence(payload)

    assert exc.value.code == "runtime_ack_version_mismatch"


def test_ack_time_before_command_is_rejected() -> None:
    payload = _successful_evidence().to_dict()
    payload["adoption_trace"]["runtime_ack"]["ack_timestamp"] = 0.5

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_evidence(payload)

    assert exc.value.code == "runtime_ack_time_mismatch"


def test_same_key_pair_context_mismatch_is_rejected() -> None:
    trace = _trace()
    r0 = replace(_r0_window(trace), pairing_context_sha256=_digest("6"))

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        assemble_active_vision_a3_evidence(
            trace,
            candidate_window=_candidate_window(trace),
            same_key_r0_window=r0,
        )

    assert exc.value.code == "same_key_r0_identity_mismatch"


def test_same_key_pair_comparison_key_mismatch_is_rejected() -> None:
    trace = _trace()
    r0 = replace(_r0_window(trace), comparison_key="other-comparison-key")

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        assemble_active_vision_a3_paired_evidence(
            trace,
            candidate_window=_candidate_window(trace),
            same_key_r0_windows=(r0,),
        )

    assert exc.value.code == "same_key_r0_identity_mismatch"


def test_same_key_pair_source_event_log_reuse_is_rejected() -> None:
    trace = _trace()
    candidate = _candidate_window(trace)
    r0 = replace(
        _r0_window(trace),
        source_event_log_sha256=candidate.source_event_log_sha256,
    )

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        assemble_active_vision_a3_paired_evidence(
            trace,
            candidate_window=candidate,
            same_key_r0_windows=(r0,),
        )

    assert exc.value.code == "same_key_r0_log_reuse"


def test_r0_cross_camera_and_cross_version_decisions_are_rejected() -> None:
    candidate_trace = _trace()
    base = _rule_decision()
    other_camera_action = replace(base.rule_action, camera_id="CAM-02")
    other_camera_decision = replace(
        base,
        rule_action=other_camera_action,
        effective_action=other_camera_action,
    )
    with pytest.raises(ActiveVisionA3EvidenceError) as camera_error:
        _main_runtime_rule_trace(
            candidate_trace,
            rule_decision=other_camera_decision,
        )
    assert camera_error.value.code == "r0_camera_not_in_snapshot"

    other_version_action = replace(base.rule_action, plan_version=8)
    other_version_decision = replace(
        base,
        rule_action=other_version_action,
        effective_action=other_version_action,
        plan_version=8,
    )
    with pytest.raises(ActiveVisionA3EvidenceError) as version_error:
        _main_runtime_rule_trace(
            candidate_trace,
            rule_decision=other_version_decision,
        )
    assert version_error.value.code == "snapshot_decision_version_mismatch"


def test_same_key_pair_window_duration_mismatch_is_rejected() -> None:
    trace = _trace()
    r0 = replace(_r0_window(trace), window_end_timestamp=11.20)

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        assemble_active_vision_a3_evidence(
            trace,
            candidate_window=_candidate_window(trace),
            same_key_r0_window=r0,
        )

    assert exc.value.code == "same_key_r0_duration_mismatch"


def test_r0_anonymous_frame_requires_both_timestamps() -> None:
    frame_payload = _observation_frames(start_timestamp=10.15)[0].to_dict()
    del frame_payload["arrival_timestamp"]

    with pytest.raises(ActiveVisionA3EvidenceError) as missing:
        ActiveVisionA3AnonymousObservationFrame.from_mapping(frame_payload)
    assert missing.value.code == "evidence_fields_mismatch"

    frame = _observation_frames(start_timestamp=10.15)[0]
    with pytest.raises(ActiveVisionA3EvidenceError) as reversed_time:
        replace(
            frame,
            arrival_timestamp=frame.measurement_timestamp - 0.01,
        )
    assert reversed_time.value.code == "observation_frame_time_invalid"


def test_historical_v1_observation_frame_remains_strict_and_roundtrips() -> None:
    frame = _observation_frames(start_timestamp=10.15)[0]
    payload = frame.to_dict()

    assert (
        payload["schema_version"]
        == ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION
    )
    assert "frame_observation_state" not in payload
    assert "center_global_track_ids" not in payload
    assert (
        ActiveVisionA3AnonymousObservationFrame.from_mapping(payload).to_dict()
        == payload
    )


def test_historical_v1_observation_frame_rejects_empty_tracklets() -> None:
    frame = _observation_frames(start_timestamp=10.15)[0]

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        replace(frame, observed_tracklet_keys=(), bindings=())

    assert exc.value.code == "observation_frame_tracklets_invalid"


def test_v2_zero_detection_frame_roundtrips_without_identity_creation() -> None:
    frame = _zero_detection_frame()
    payload = frame.to_dict()

    assert (
        frame.schema_version
        == ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION
    )
    assert frame.observed_tracklet_keys == ()
    assert frame.bindings == ()
    assert frame.association_state == "reacquire"
    assert frame.assigned_reference_visible is False
    assert payload["frame_observation_state"] == "processed_zero_detections"
    assert payload["center_global_track_ids"] == ["GT-001"]
    assert (
        ActiveVisionA3AnonymousObservationFrame.from_mapping(payload).to_dict()
        == payload
    )


def test_v2_zero_detection_frame_rejects_non_center_target_reference() -> None:
    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        _zero_detection_frame(center_global_track_ids=("GT-002",))

    assert exc.value.code == "observation_frame_target_not_center_owned"


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    (
        ("measurement_timestamp", 1.14),
        ("plan_version", 8),
        ("source_sequence", 301),
        ("evidence_kind", SYNTHETIC_FIXTURE_EVIDENCE_KIND),
        ("content_sha256", "0" * 64),
    ),
)
def test_v2_zero_detection_frame_rejects_rehashed_field_tamper(
    field: str,
    tampered_value: object,
) -> None:
    payload = _zero_detection_frame().to_dict()
    payload[field] = tampered_value

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        ActiveVisionA3AnonymousObservationFrame.from_mapping(payload)

    assert exc.value.code == "observation_frame_recomputation_mismatch"


def test_v2_zero_detection_without_assignment_stays_unavailable() -> None:
    frame = _zero_detection_frame(
        target_global_track_id=None,
        center_global_track_ids=(),
    )

    assert frame.association_state is None
    assert frame.assigned_reference_visible is None


def test_v2_zero_detection_window_reports_reacquire_and_zero_coverage() -> None:
    trace = _main_runtime_trace()
    frame = _zero_detection_frame()
    window = assemble_active_vision_a3_physical_observation_window(
        trace,
        arm=ActiveVisionA3WindowArm.A3,
        observation_frames=(frame,),
        window_start_timestamp=1.10,
        window_end_timestamp=2.10,
    )

    assert window is not None
    assert window.outcome.association_outcome_available is True
    assert window.outcome.association_evaluable_frame_count == 1
    assert window.outcome.association_locked_count == 0
    assert window.outcome.association_ambiguous_count == 0
    assert window.outcome.association_hold_count == 0
    assert window.outcome.association_reacquire_count == 1
    assert window.outcome.coverage_outcome_available is True
    assert window.outcome.assigned_reference_count == 1
    assert window.outcome.visible_assigned_reference_count == 0
    assert window.outcome.coverage_fraction == 0.0
    rebuilt = ActiveVisionA3PhysicalObservationWindow.from_mapping(
        window.to_dict()
    )
    assert rebuilt.to_dict() == window.to_dict()

    audit = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=window,
        same_key_r0_window=None,
    )
    assert not any(audit.permissions.to_dict().values())


def test_v1_nonempty_and_v2_zero_frames_share_one_runtime_window() -> None:
    trace = _main_runtime_trace()
    observation = _local_observation(
        local_track_id="mixed-local-001",
        measurement_timestamp=1.15,
        arrival_timestamp=1.16,
    )
    v1_frame = active_vision_a3_observation_frame(
        frame_key="mixed-v1-frame",
        observations=(observation,),
        bindings=(
            ActiveVisionA3BindingEvidence(
                cluster_key="mixed-cluster-001",
                global_track_id="GT-001",
                decision_state="bound",
                supporting_tracklet_keys=(observation.tracklet_key,),
            ),
        ),
        target_global_track_id="GT-001",
        center_global_track_ids=("GT-001",),
        plan_version=7,
        coalition_version=3,
        communication_version=11,
        evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        source_sequence=300,
    )
    v2_frame = _zero_detection_frame(
        frame_key="mixed-v2-frame",
        measurement_timestamp=1.25,
        arrival_timestamp=1.26,
        source_sequence=301,
    )
    window = assemble_active_vision_a3_physical_observation_window(
        trace,
        arm=ActiveVisionA3WindowArm.A3,
        observation_frames=(v2_frame, v1_frame),
        window_start_timestamp=1.10,
        window_end_timestamp=2.10,
    )

    assert window is not None
    assert tuple(frame.schema_version for frame in window.observation_frames) == (
        ACTIVE_VISION_A3_OBSERVATION_FRAME_SCHEMA_VERSION,
        ACTIVE_VISION_A3_OBSERVATION_FRAME_V2_SCHEMA_VERSION,
    )
    assert window.outcome.association_locked_count == 1
    assert window.outcome.association_reacquire_count == 1
    assert window.outcome.coverage_fraction == 0.5
    assert (
        ActiveVisionA3PhysicalObservationWindow.from_mapping(
            window.to_dict()
        ).to_dict()
        == window.to_dict()
    )


def test_runtime_window_rejects_mixed_v1_v2_observation_provenance() -> None:
    trace = _main_runtime_trace()
    runtime_frame = _observation_frames(start_timestamp=1.15)[0]
    synthetic_frame = _zero_detection_frame(
        frame_key="synthetic-zero-frame",
        measurement_timestamp=1.25,
        arrival_timestamp=1.26,
        evidence_kind=SYNTHETIC_FIXTURE_EVIDENCE_KIND,
        source_sequence=301,
    )

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        assemble_active_vision_a3_physical_observation_window(
            trace,
            arm=ActiveVisionA3WindowArm.A3,
            observation_frames=(runtime_frame, synthetic_frame),
            window_start_timestamp=1.10,
            window_end_timestamp=2.10,
        )

    assert exc.value.code == "physical_window_frame_provenance_mismatch"


def test_evidence_reconstruction_is_deterministic() -> None:
    evidence = _successful_evidence()
    payload = evidence.to_dict()
    first = validate_active_vision_a3_evidence(deepcopy(payload))
    second = validate_active_vision_a3_evidence(deepcopy(payload))

    assert first.to_dict() == second.to_dict() == payload
    assert first.content_sha256 == second.content_sha256


def test_main_camera_command_structural_adapter_preserves_contract_fields() -> None:
    action = _decision().effective_action
    command = SimpleNamespace(
        camera_id=action.camera_id,
        resource_id="INT-01",
        issued_timestamp=action.issued_timestamp,
        expires_timestamp=action.expires_timestamp,
        plan_version=action.plan_version,
        coalition_version=action.coalition_version,
        communication_version=action.communication_version,
        intent=action.intent.value,
        aim_point_ned=(100.0, 20.0, -10.0),
        horizontal_fov_deg=30.0,
        fov_mode=action.fov_mode.value,
        target_global_track_id=action.target_global_track_id,
        requested_mode="assist",
        effective_mode="assist",
        reason=action.reason,
    )

    payload = camera_observation_command_payload(command)

    assert payload["payload_version"] == CAMERA_OBSERVATION_COMMAND_PAYLOAD_VERSION
    assert payload["camera_id"] == "CAM-01"
    assert payload["aim_point_ned"] == [100.0, 20.0, -10.0]


def test_existing_ack_and_feedback_types_are_retained_in_validated_trace() -> None:
    trace = _trace()
    reconstructed = ActiveVisionA3AdoptionTrace.from_mapping(trace.to_dict())

    assert isinstance(reconstructed.runtime_ack, ActiveVisionRuntimeAckV1)
    assert isinstance(reconstructed.camera_feedback, ActiveVisionCameraFeedbackV1)
    assert isinstance(
        reconstructed.camera_pose_lineage,
        ActiveVisionA3CameraPoseLineage,
    )


def test_main_runtime_public_api_builds_trace_and_anonymous_physical_window() -> None:
    trace = _main_runtime_trace()
    observation = _local_observation(
        local_track_id="local-001",
        measurement_timestamp=1.15,
        arrival_timestamp=1.16,
    )
    frame = active_vision_a3_observation_frame(
        frame_key="frame-001",
        observations=(observation,),
        bindings=(
            CenterTrackBindingDecision(
                cluster_key="cluster-001",
                global_track_id="GT-001",
                cost=1.2,
                decision_state="bound",
                supporting_tracklet_keys=(observation.tracklet_key,),
            ),
        ),
        target_global_track_id="GT-001",
        center_global_track_ids=("GT-001",),
        plan_version=7,
        coalition_version=3,
        communication_version=11,
        evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        source_sequence=43,
    )
    candidate = assemble_active_vision_a3_physical_observation_window(
        trace,
        arm=ActiveVisionA3WindowArm.A3,
        observation_frames=(frame,),
        window_start_timestamp=1.10,
        window_end_timestamp=2.10,
    )

    assert candidate is not None
    assert trace.model_action_adopted is True
    assert trace.command_payload_sha256 is not None
    assert trace.runtime_ack_sha256 is not None
    assert trace.camera_pose_lineage is not None
    assert trace.camera_pose_lineage.source_sequence == 42
    assert frame.association_state == "locked"
    assert candidate.outcome.association_locked_count == 1
    assert candidate.outcome.visible_assigned_reference_count == 1
    evidence = assemble_active_vision_a3_evidence(
        trace,
        candidate_window=candidate,
        same_key_r0_window=_r0_window(trace),
    )
    assert evidence.d6_benefit_audit_eligible is True


@pytest.mark.parametrize(
    ("binding_state", "terminal_state"),
    (
        ("bound", "locked"),
        ("ambiguous", "ambiguous"),
        ("unbound", "reacquire"),
    ),
)
def test_public_binding_state_mapping_is_stable(
    binding_state: str,
    terminal_state: str,
) -> None:
    assert map_active_vision_binding_state(binding_state) == terminal_state


def test_missing_post_command_observation_and_pose_lineage_stay_unavailable() -> None:
    complete = _main_runtime_trace()
    missing_window = assemble_active_vision_a3_physical_observation_window(
        complete,
        arm=ActiveVisionA3WindowArm.A3,
        observation_frames=(),
        window_start_timestamp=1.10,
        window_end_timestamp=2.10,
    )
    assert missing_window is None
    audit = assemble_active_vision_a3_evidence(
        complete,
        candidate_window=missing_window,
        same_key_r0_window=None,
    )
    assert "candidate_physical_window_missing" in audit.blocker_codes
    assert audit.candidate_physical_window_available is False

    no_pose = _main_runtime_trace(post_command_camera_state=None)
    assert no_pose.camera_pose_lineage is None
    assert no_pose.model_action_adopted is False
    assert "camera_pose_lineage_missing" in no_pose.adoption_blockers


def test_runtime_pose_version_mismatch_is_not_adopted() -> None:
    trace = _main_runtime_trace(
        post_command_camera_state=_runtime_camera_state(last_plan_version=8)
    )

    assert trace.pose_applied is False
    assert "pose_not_applied" in trace.adoption_blockers


def test_frame_rejects_non_center_global_reference_without_rebinding() -> None:
    observation = _local_observation(
        local_track_id="local-002",
        measurement_timestamp=1.15,
        arrival_timestamp=1.16,
    )

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        active_vision_a3_observation_frame(
            frame_key="frame-002",
            observations=(observation,),
            bindings=(
                CenterTrackBindingDecision(
                    cluster_key="cluster-002",
                    global_track_id="GT-NOT-CENTER",
                    cost=1.0,
                    decision_state="bound",
                    supporting_tracklet_keys=(observation.tracklet_key,),
                ),
            ),
            target_global_track_id="GT-001",
            center_global_track_ids=("GT-001",),
            plan_version=7,
            coalition_version=3,
            communication_version=11,
            evidence_kind=RUNTIME_OBSERVED_EVIDENCE_KIND,
        )

    assert exc.value.code == "binding_global_reference_not_center_owned"


def test_serialized_window_outcome_cannot_replace_missing_evidence_with_zero() -> None:
    payload = _successful_evidence().to_dict()
    payload["candidate_window"]["outcome"]["association_locked_count"] = 0

    with pytest.raises(ActiveVisionA3EvidenceError) as exc:
        validate_active_vision_a3_evidence(payload)

    assert exc.value.code in {
        "physical_window_outcome_recomputation_mismatch",
        "window_hash_mismatch",
        "window_recomputation_mismatch",
    }
