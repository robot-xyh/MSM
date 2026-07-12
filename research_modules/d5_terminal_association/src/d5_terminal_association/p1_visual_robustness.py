"""Deterministic offline P1 visual robustness matrix for D5 and D6.

The matrix calls the same truth-free D5 association APIs used by replay and
AirSim adapters. Expected outcomes are evaluated only after online association
returns; no offline label is passed into an online cost, gate, or binding.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .airsim_geometry import associate_tracks_to_detections_geometrically
from .associator import TerminalAssociator
from .cross_view_registration import (
    CameraLocalTrackBatch,
    GlobalTrackBinding,
    RegistrationStabilityConfig,
    register_local_visual_tracks_to_global_tracks,
)
from .models import Assignment, CameraModel, GlobalTrack, LocalVisualTrack, TerminalAssociation


P1_VISUAL_ROBUSTNESS_SCHEMA_VERSION = "d5.p1_visual_robustness_summary.v1"
P1_VISUAL_ROBUSTNESS_PROFILE_ID = "d5-p1-visual-robustness-deterministic"
P1_VISUAL_ROBUSTNESS_PROFILE_VERSION = "d5.p1_visual_robustness_profile.v1"


@dataclass(frozen=True)
class P1VisualRobustnessCaseResult:
    """One deterministic matrix row with explicit safety counters."""

    case_id: str
    category: str
    passed: bool
    check_count: int
    passed_check_count: int
    failed_check_count: int
    reject_count: int
    observation_count: int
    terminal_association_count: int
    online_truth_use_count: int
    global_track_id_rewrite_count: int
    decision_counts: dict[str, int] = field(default_factory=dict)
    rejection_reason_counts: dict[str, int] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class P1VisualRobustnessSummary:
    """Versioned D5 summary accepted by D6 ``--d5-summary``."""

    cases: tuple[P1VisualRobustnessCaseResult, ...]
    schema_version: str = P1_VISUAL_ROBUSTNESS_SCHEMA_VERSION
    profile_id: str = P1_VISUAL_ROBUSTNESS_PROFILE_ID
    profile_version: str = P1_VISUAL_ROBUSTNESS_PROFILE_VERSION
    seed_count: int = 1
    ready_seed_count: int = 1
    missing_required_fields_by_seed: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {"deterministic": ()}
    )
    missing_recommended_fields_by_seed: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "deterministic": (
                "real_airsim_multiseed",
                "sustained_yolo_native_mot",
            )
        }
    )

    @property
    def case_count(self) -> int:
        return len(self.cases)

    @property
    def passed_case_count(self) -> int:
        return sum(case.passed for case in self.cases)

    @property
    def failed_case_count(self) -> int:
        return self.case_count - self.passed_case_count

    @property
    def total_observation_count(self) -> int:
        return sum(case.observation_count for case in self.cases)

    @property
    def total_terminal_association_count(self) -> int:
        return sum(case.terminal_association_count for case in self.cases)

    @property
    def check_count(self) -> int:
        return sum(case.check_count for case in self.cases)

    @property
    def passed_check_count(self) -> int:
        return sum(case.passed_check_count for case in self.cases)

    @property
    def failed_check_count(self) -> int:
        return sum(case.failed_check_count for case in self.cases)

    @property
    def reject_count(self) -> int:
        return sum(case.reject_count for case in self.cases)

    @property
    def online_truth_use_count(self) -> int:
        return sum(case.online_truth_use_count for case in self.cases)

    @property
    def global_track_id_rewrite_count(self) -> int:
        return sum(case.global_track_id_rewrite_count for case in self.cases)

    def to_dict(self) -> dict[str, Any]:
        case_rows = [case.to_dict() for case in self.cases]
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "seed_count": self.seed_count,
            "ready_seed_count": self.ready_seed_count,
            "total_observation_count": self.total_observation_count,
            "total_terminal_association_count": self.total_terminal_association_count,
            "case_count": self.case_count,
            "pass_count": self.passed_case_count,
            "passed_case_count": self.passed_case_count,
            "failed_case_count": self.failed_case_count,
            "check_count": self.check_count,
            "passed_check_count": self.passed_check_count,
            "failed_check_count": self.failed_check_count,
            "reject_count": self.reject_count,
            "online_truth_use_count": self.online_truth_use_count,
            "global_track_id_rewrite_count": self.global_track_id_rewrite_count,
            "missing_required_fields_by_seed": {
                key: list(value) for key, value in self.missing_required_fields_by_seed.items()
            },
            "missing_recommended_fields_by_seed": {
                key: list(value)
                for key, value in self.missing_recommended_fields_by_seed.items()
            },
            "cases": case_rows,
            "metadata": {
                "boundary": "d5_offline_deterministic_replay_only",
                "association_path": "detect_first_global_projection_mahalanobis_hungarian",
                "online_truth_policy": "forbidden_and_counted_after_association",
                "global_track_id_policy": "center_owned_read_only",
                "detector_default": "simGetDetections",
                "yolo_mot_status": "deferred_calibration",
                "all_cases_passed": self.failed_case_count == 0,
                "case_count": self.case_count,
                "pass_count": self.passed_case_count,
                "passed_case_count": self.passed_case_count,
                "failed_case_count": self.failed_case_count,
                "reject_count": self.reject_count,
                "online_truth_use_count": self.online_truth_use_count,
                "global_track_id_rewrite_count": self.global_track_id_rewrite_count,
                "case_ids": [case.case_id for case in self.cases],
                "case_results": [
                    {
                        "case_id": case.case_id,
                        "category": case.category,
                        "passed": case.passed,
                        "reject_count": case.reject_count,
                        "online_truth_use_count": case.online_truth_use_count,
                        "global_track_id_rewrite_count": case.global_track_id_rewrite_count,
                        "rejection_reason_counts": case.rejection_reason_counts,
                    }
                    for case in self.cases
                ],
            },
        }


def run_p1_visual_robustness_matrix() -> P1VisualRobustnessSummary:
    """Run the deterministic D5 P1 matrix without AirSim or online truth IDs."""

    cases: list[P1VisualRobustnessCaseResult] = []
    cases.extend(_dropout_recovery_case(frame_count) for frame_count in range(1, 6))
    cases.extend(
        (
            _mot_id_change_case(),
            _crossing_case(),
            _partial_overlap_case(),
            _extrinsic_drift_case(),
            _timestamp_bias_case(),
        )
    )
    return P1VisualRobustnessSummary(cases=tuple(cases))


def write_p1_visual_robustness_summary(
    output_path: str | Path,
    summary: P1VisualRobustnessSummary | None = None,
) -> Path:
    """Write a stable JSON artifact for D6 ``--d5-summary`` consumption."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (summary or run_p1_visual_robustness_matrix()).to_dict()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _dropout_recovery_case(frame_count: int) -> P1VisualRobustnessCaseResult:
    associator = TerminalAssociator()
    assignment = _assignment()
    track = _global("G1")
    before_ids = _global_ids((track,))
    decisions = [
        associator.decide(
            assignment,
            [track],
            [_local("front:mot-1", 320.0, 0.0)],
            camera=_camera(),
            current_time=0.0,
            arrival_timestamp=0.01,
            camera_id="front",
        )
    ]
    decisions.extend(
        associator.decide(
            assignment,
            [track],
            [],
            camera=_camera(),
            current_time=index * 0.1,
            arrival_timestamp=index * 0.1,
            camera_id="front",
        )
        for index in range(1, frame_count + 1)
    )
    first_recovery_time = (frame_count + 1) * 0.1
    decisions.append(
        associator.decide(
            assignment,
            [track],
            [_local("front:mot-1", 320.5, first_recovery_time)],
            camera=_camera(),
            current_time=first_recovery_time,
            arrival_timestamp=first_recovery_time + 0.01,
            camera_id="front",
        )
    )
    second_recovery_time = first_recovery_time + 0.1
    decisions.append(
        associator.decide(
            assignment,
            [track],
            [_local("front:mot-1", 320.0, second_recovery_time)],
            camera=_camera(),
            current_time=second_recovery_time,
            arrival_timestamp=second_recovery_time + 0.01,
            camera_id="front",
        )
    )
    missing = decisions[1 : frame_count + 1]
    expected_expired = max(0, frame_count - 2)
    checks = {
        "initial_lock": decisions[0].decision_state == "locked",
        "all_missing_reacquire": all(item.decision_state == "reacquire" for item in missing),
        "expiry_boundary": sum(
            item.reason == "terminal_visual_evidence_expired" for item in missing
        )
        == expected_expired,
        "first_recovery_not_locked": decisions[-2].decision_state == "ambiguous",
        "second_recovery_locked": decisions[-1].decision_state == "locked",
        "assigned_id_preserved": decisions[-1].assigned_global_track_id == "G1",
    }
    return _terminal_case(
        case_id=f"dropout_{frame_count}_frame_recovery",
        category="dropout_recovery",
        decisions=decisions,
        checks=checks,
        before_ids=before_ids,
        after_ids=_global_ids((track,)),
        metadata={
            "missing_frame_count": frame_count,
            "expected_expired_frame_count": expected_expired,
            "recovery_measured_frame_count": 2,
        },
    )


def _mot_id_change_case() -> P1VisualRobustnessCaseResult:
    associator = TerminalAssociator()
    assignment = _assignment()
    track = _global("G1")
    before_ids = _global_ids((track,))
    decisions = [
        associator.decide(
            assignment,
            [track],
            [_local("front:mot-old", 320.0, 0.0)],
            camera=_camera(),
            current_time=0.0,
            camera_id="front",
        ),
        associator.decide(
            assignment,
            [track],
            [],
            camera=_camera(),
            current_time=0.1,
            camera_id="front",
        ),
        associator.decide(
            assignment,
            [track],
            [_local("front:mot-new", 320.5, 0.2)],
            camera=_camera(),
            current_time=0.2,
            camera_id="front",
        ),
        associator.decide(
            assignment,
            [track],
            [_local("front:mot-new", 320.0, 0.3)],
            camera=_camera(),
            current_time=0.3,
            camera_id="front",
        ),
    ]
    checks = {
        "old_id_locked": decisions[0].decision_state == "locked",
        "loss_reacquire": decisions[1].decision_state == "reacquire",
        "new_id_first_frame_not_locked": decisions[2].decision_state == "ambiguous",
        "new_id_second_frame_locked": decisions[3].decision_state == "locked",
        "new_id_does_not_rebind_global": decisions[3].assigned_global_track_id == "G1",
    }
    return _terminal_case(
        case_id="mot_id_change_after_dropout",
        category="mot_id_change",
        decisions=decisions,
        checks=checks,
        before_ids=before_ids,
        after_ids=_global_ids((track,)),
    )


def _crossing_case() -> P1VisualRobustnessCaseResult:
    before_tracks = (_global("G1", -1.0), _global("G2", 1.0))
    after_tracks = (_global("G1", 1.0), _global("G2", -1.0))
    original_ids = _global_ids(before_tracks) + _global_ids(after_tracks)
    before = associate_tracks_to_detections_geometrically(
        before_tracks,
        (
            _local("front:anonymous-A", 315.0, 0.0),
            _local("front:anonymous-B", 325.0, 0.0),
        ),
        _camera(),
        timestamp=0.0,
        arrival_timestamp=0.01,
        frame_id="R1/front",
    )
    after = associate_tracks_to_detections_geometrically(
        after_tracks,
        (
            _local("front:anonymous-A", 325.0, 1.0),
            _local("front:anonymous-B", 315.0, 1.0),
        ),
        _camera(),
        timestamp=1.0,
        arrival_timestamp=1.01,
        frame_id="R1/front",
    )
    expected = {"G1": "front:anonymous-A", "G2": "front:anonymous-B"}
    records = before.to_log_records() + after.to_log_records()
    checks = {
        "before_hungarian_assignment": before.assignments == expected,
        "after_hungarian_assignment": after.assignments == expected,
        "no_ambiguous_crossing_frame": before.ambiguous_count == after.ambiguous_count == 0,
    }
    return _generic_case(
        case_id="same_camera_crossing",
        category="crossing",
        checks=checks,
        reject_count=before.ambiguous_count + after.ambiguous_count,
        observation_count=len(records),
        terminal_association_count=0,
        online_truth_use_count=sum(bool(record.get("truth_identity_used")) for record in records),
        global_track_id_rewrite_count=int(
            original_ids != _global_ids(before_tracks) + _global_ids(after_tracks)
        ),
        decision_counts={"hungarian_selected": len(before.assignments) + len(after.assignments)},
        rejection_reason_counts={},
    )


def _partial_overlap_case() -> P1VisualRobustnessCaseResult:
    tracks = (
        _global("G1", -6.0),
        _global("G2", -2.0),
        _global("G3", 2.0),
        _global("G4", 6.0),
    )
    before_ids = _global_ids(tracks)
    result = register_local_visual_tracks_to_global_tracks(
        global_tracks=tracks,
        bindings=[GlobalTrackBinding(global_track_id=track.global_track_id) for track in tracks],
        camera_batches=(
            CameraLocalTrackBatch(
                resource_id="R1",
                camera_id="front",
                camera=_camera(),
                local_tracks=(
                    _local("front:a", 290.0, 1.0),
                    _local("front:b", 310.0, 1.0),
                    _local("front:c", 330.0, 1.0),
                ),
                timestamp=1.0,
            ),
            CameraLocalTrackBatch(
                resource_id="R2",
                camera_id="front",
                camera=_camera(),
                local_tracks=(
                    _local("peer:b", 310.0, 1.02, resource_id="R2"),
                    _local("peer:c", 330.0, 1.02, resource_id="R2"),
                    _local("peer:d", 350.0, 1.02, resource_id="R2"),
                ),
                timestamp=1.02,
            ),
        ),
        current_time=1.02,
        max_binding_age_s=None,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )
    support = {
        item.global_track_id: item.supporting_resource_ids for item in result.cross_view_associations
    }
    checks = {
        "g1_single_view": support.get("G1") == ("R1",),
        "g2_multi_view": support.get("G2") == ("R1", "R2"),
        "g3_multi_view": support.get("G3") == ("R1", "R2"),
        "g4_single_view": support.get("G4") == ("R2",),
        "offline_truth_not_attached": all(
            candidate.offline_truth_global_id is None for candidate in result.candidates
        ),
    }
    return _registration_case(
        case_id="cross_camera_partial_overlap",
        category="partial_overlap",
        result=result,
        checks=checks,
        before_ids=before_ids,
        after_ids=_global_ids(tracks),
        metadata={"supporting_resources_by_global_track_id": support},
    )


def _extrinsic_drift_case() -> P1VisualRobustnessCaseResult:
    track = _global("G1", timestamp=10.0)
    before_ids = _global_ids((track,))
    binding = GlobalTrackBinding(global_track_id="G1", timestamp=10.0)
    local = _local("recon:anonymous", 320.0, 10.0, bbox=False, resource_id="RECON")
    healthy = _single_registration(track, binding, local, _camera(), timestamp=10.0)
    drifted = _single_registration(
        track,
        binding,
        local,
        _camera(translation_x_m=4.0),
        timestamp=10.0,
    )
    checks = {
        "healthy_geometry_registered": bool(healthy.cross_view_associations),
        "drifted_geometry_rejected": not drifted.cross_view_associations,
        "drift_reject_reason": drifted.rejection_reason_counts.get(
            "geometry_gate_rejected", 0
        )
        == 1,
    }
    return _registration_case(
        case_id="extrinsic_drift_4m",
        category="extrinsic_drift",
        result=drifted,
        checks=checks,
        before_ids=before_ids,
        after_ids=_global_ids((track,)),
        metadata={"healthy_registered_count": len(healthy.cross_view_associations)},
    )


def _timestamp_bias_case() -> P1VisualRobustnessCaseResult:
    track = _global("G1", velocity_x_m_s=10.0, timestamp=10.0)
    before_ids = _global_ids((track,))
    binding = GlobalTrackBinding(global_track_id="G1", timestamp=10.0)
    local = _local("recon:anonymous", 320.0, 10.0, bbox=False, resource_id="RECON")
    aligned = _single_registration(track, binding, local, _camera(), timestamp=10.0)
    biased = _single_registration(
        track,
        binding,
        local,
        _camera(),
        timestamp=10.5,
        current_time=10.5,
    )
    checks = {
        "aligned_timestamp_registered": bool(aligned.cross_view_associations),
        "biased_timestamp_rejected": not biased.cross_view_associations,
        "time_bias_reject_reason": biased.rejection_reason_counts.get(
            "geometry_gate_rejected", 0
        )
        == 1,
    }
    return _registration_case(
        case_id="timestamp_bias_0p5s_high_dynamic",
        category="timestamp_bias",
        result=biased,
        checks=checks,
        before_ids=before_ids,
        after_ids=_global_ids((track,)),
        metadata={"aligned_registered_count": len(aligned.cross_view_associations)},
    )


def _terminal_case(
    *,
    case_id: str,
    category: str,
    decisions: Sequence[TerminalAssociation],
    checks: Mapping[str, bool],
    before_ids: tuple[str, ...],
    after_ids: tuple[str, ...],
    metadata: Mapping[str, Any] | None = None,
) -> P1VisualRobustnessCaseResult:
    decision_counts = Counter(item.decision_state for item in decisions)
    reason_counts = Counter(
        item.reason for item in decisions if item.decision_state != "locked"
    )
    return _generic_case(
        case_id=case_id,
        category=category,
        checks=checks,
        reject_count=sum(item.decision_state != "locked" for item in decisions),
        observation_count=len(decisions),
        terminal_association_count=len(decisions),
        online_truth_use_count=sum(item.truth_identity_used for item in decisions),
        global_track_id_rewrite_count=int(before_ids != after_ids),
        decision_counts=dict(decision_counts),
        rejection_reason_counts=dict(reason_counts),
        metadata=metadata,
    )


def _registration_case(
    *,
    case_id: str,
    category: str,
    result: Any,
    checks: Mapping[str, bool],
    before_ids: tuple[str, ...],
    after_ids: tuple[str, ...],
    metadata: Mapping[str, Any] | None = None,
) -> P1VisualRobustnessCaseResult:
    associations = [
        item.terminal_association
        for item in result.observations
        if item.terminal_association is not None
    ]
    reject_count = sum(
        count
        for reason, count in result.rejection_reason_counts.items()
        if reason != "registered_to_global_track"
    )
    return _generic_case(
        case_id=case_id,
        category=category,
        checks=checks,
        reject_count=reject_count,
        observation_count=len(result.candidates),
        terminal_association_count=len(associations),
        online_truth_use_count=sum(item.truth_identity_used for item in associations),
        global_track_id_rewrite_count=int(before_ids != after_ids),
        decision_counts=dict(Counter(item.decision_state for item in associations)),
        rejection_reason_counts=dict(result.rejection_reason_counts),
        metadata=metadata,
    )


def _generic_case(
    *,
    case_id: str,
    category: str,
    checks: Mapping[str, bool],
    reject_count: int,
    observation_count: int,
    terminal_association_count: int,
    online_truth_use_count: int,
    global_track_id_rewrite_count: int,
    decision_counts: Mapping[str, int],
    rejection_reason_counts: Mapping[str, int],
    metadata: Mapping[str, Any] | None = None,
) -> P1VisualRobustnessCaseResult:
    normalized_checks = {str(key): bool(value) for key, value in checks.items()}
    passed_checks = sum(normalized_checks.values())
    return P1VisualRobustnessCaseResult(
        case_id=case_id,
        category=category,
        passed=passed_checks == len(normalized_checks),
        check_count=len(normalized_checks),
        passed_check_count=passed_checks,
        failed_check_count=len(normalized_checks) - passed_checks,
        reject_count=int(reject_count),
        observation_count=int(observation_count),
        terminal_association_count=int(terminal_association_count),
        online_truth_use_count=int(online_truth_use_count),
        global_track_id_rewrite_count=int(global_track_id_rewrite_count),
        decision_counts={str(key): int(value) for key, value in decision_counts.items()},
        rejection_reason_counts={
            str(key): int(value) for key, value in rejection_reason_counts.items()
        },
        checks=normalized_checks,
        metadata=dict(metadata or {}),
    )


def _single_registration(
    track: GlobalTrack,
    binding: GlobalTrackBinding,
    local: LocalVisualTrack,
    camera: CameraModel,
    *,
    timestamp: float,
    current_time: float | None = None,
) -> Any:
    return register_local_visual_tracks_to_global_tracks(
        global_tracks=(track,),
        bindings=(binding,),
        camera_batches=(
            CameraLocalTrackBatch(
                resource_id="RECON",
                camera_id="eo",
                camera=camera,
                local_tracks=(local,),
                timestamp=timestamp,
            ),
        ),
        current_time=timestamp if current_time is None else current_time,
        max_binding_age_s=None,
        stability_config=RegistrationStabilityConfig(window_frames=1, required_gate_passes=1),
    )


def _assignment() -> Assignment:
    return Assignment(
        "G1",
        resource_id="R1",
        plan_id="PLAN-A",
        plan_version=2,
    )


def _camera(*, translation_x_m: float = 0.0) -> CameraModel:
    return CameraModel(
        K=np.array(
            [[100.0, 0.0, 320.0], [0.0, 100.0, 240.0], [0.0, 0.0, 1.0]],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.array([translation_x_m, 0.0, 0.0], dtype=float),
        image_size=(640, 480),
        measurement_cov=np.diag([4.0, 4.0]),
    )


def _global(
    global_track_id: str,
    x_m: float = 0.0,
    *,
    velocity_x_m_s: float = 0.0,
    timestamp: float = 0.0,
) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_track_id,
        position=np.array([x_m, 0.0, 20.0], dtype=float),
        velocity=np.array([velocity_x_m_s, 0.0, 0.0], dtype=float),
        covariance=np.diag([0.02, 0.02, 0.02]),
        category="uav",
        timestamp=timestamp,
    )


def _local(
    local_track_id: str,
    center_x_px: float,
    timestamp: float,
    *,
    resource_id: str = "R1",
    camera_id: str = "front",
    bbox: bool = True,
) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_track_id,
        center_px=np.array([center_x_px, 240.0], dtype=float),
        bbox=(center_x_px - 5.0, 235.0, center_x_px + 5.0, 245.0) if bbox else None,
        category="uav",
        quality=0.95,
        mot_history_length=5,
        timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        detection_source="simGetDetections",
        metadata={"resource_id": resource_id, "camera_id": camera_id},
    )


def _global_ids(tracks: Iterable[GlobalTrack]) -> tuple[str, ...]:
    return tuple(track.global_track_id for track in tracks)
