"""D4/D5 5v5 stress analysis for AirSim ComputerVision replays."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, is_dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
from airsim_dryrun.models import AirSimDetectionBox, AirSimFrame
from d4_distributed_fallback import (
    ActiveDegradationArbiter,
    AssignmentValiditySummary,
    AssociationRiskSummary,
    AvailabilityBand,
    C2Health,
    CommBand,
    CommunicationSummary,
    LinkType,
    NodeRole,
    PayloadKind,
    ResourceSummary,
    TerminalAssociationSummary,
    TerminalDecisionState,
    TrackUncertaintySummary,
)
from d4_distributed_fallback.adapter import D4ArbitrationAdapter
from d5_terminal_association import (
    Assignment,
    CameraLocalTrackBatch,
    CameraModel,
    GlobalTrackBinding,
    GlobalTrack,
    LocalVisualTrack,
    ReconImageCue,
    TerminalObservation,
    TerminalObservationBus,
    TerminalAssociator,
    build_secondary_frame_association_evidence,
    camera_model_from_airsim_camera_info,
    register_local_visual_tracks_to_global_tracks,
    summarize_secondary_visual_coverage_funnel,
)


D4D5_STRESS_CASES = ("no_degradation", "degrade_to_secondary", "degrade_to_distributed")


@dataclass(frozen=True)
class D4D5StressAnalysisResult:
    """Output paths and summary metrics for one D4/D5 stress case."""

    case_name: str
    output_paths: dict[str, Path]
    metrics: dict[str, Any]


def run_d4d5_stress_analysis(
    frames: list[AirSimFrame],
    output_dir: Path,
    *,
    case_name: str,
    resource_vehicle_names: tuple[str, ...],
    secondary_camera_vehicle_names: tuple[str, ...],
    comparison_role: str = "not_recorded",
    active_degradation_review_label: str = "inconclusive",
) -> D4D5StressAnalysisResult:
    """Generate D5 terminal evidence and D4 degradation decisions from frames."""

    normalized_case = _normalize_case_name(case_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    bus = TerminalObservationBus()
    observations: list[TerminalObservation] = []
    decisions: list[dict[str, Any]] = []
    arbiter = ActiveDegradationArbiter()
    d4_adapter = D4ArbitrationAdapter(arbiter)
    terminal_associator = TerminalAssociator()
    first_frame = frames[0] if frames else None
    geometry = _geometry_summary(first_frame, resource_vehicle_names, secondary_camera_vehicle_names)
    active_target_ids = tuple(_global_id(obj.object_id) for obj in first_frame.truth_objects) if first_frame else ()
    secondary_camera_ids = tuple(f"{name}:0" for name in secondary_camera_vehicle_names)
    registration_frame_history: list[AirSimFrame] = []

    for frame in frames:
        frame_observations = _terminal_observations_for_frame(
            frame,
            case_name=normalized_case,
            resource_vehicle_names=resource_vehicle_names,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
            terminal_associator=terminal_associator,
        )
        registration_frame_history.append(frame)
        secondary_registration = _secondary_registration_for_frames(
            registration_frame_history,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
            terminal_associator=terminal_associator,
        )
        current_frame_id = f"{frame.episode_id}:{frame.frame_index:04d}"
        frame_registration_observations = [
            observation
            for observation in secondary_registration.observations
            if observation.frame_id == current_frame_id
        ]
        for observation in frame_observations:
            observations.append(bus.publish(observation))
        for observation in frame_registration_observations:
            observations.append(bus.publish(observation))
        frame_decisions = _d4_decisions_for_frame(
            frame,
            frame_observations,
            d4_adapter,
            case_name=normalized_case,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
            d5_evidence_observations=[
                *frame_observations,
                *frame_registration_observations,
            ],
            secondary_registration=secondary_registration,
        )
        for item in frame_decisions:
            item["comparison_role"] = comparison_role
            item["active_degradation_review_label"] = active_degradation_review_label
            event_metadata = item.get("d4_event_metadata")
            if isinstance(event_metadata, dict):
                event_metadata["active_degradation_review_label"] = (
                    active_degradation_review_label
                )
                event_metadata["review_label"] = active_degradation_review_label
                event_metadata["review_label_source"] = "scenario_ground_truth"
        decisions.extend(frame_decisions)

    sequence_registration = _secondary_registration_for_frames(
        frames,
        secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        terminal_associator=terminal_associator,
    )
    registration_candidates = list(sequence_registration.candidates)
    cross_view = bus.cross_view_associations()
    secondary_funnel = summarize_secondary_visual_coverage_funnel(
        secondary_frames=_secondary_coverage_frames(
            frames,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        ),
        observations=observations,
        cross_view_associations=cross_view,
        active_target_ids=active_target_ids,
        secondary_camera_ids=secondary_camera_ids,
        current_time=frames[-1].timestamp if frames else None,
    )
    secondary_funnel_metrics = _secondary_funnel_metrics(secondary_funnel)
    detection_metrics = _detection_metrics(
        frames,
        resource_vehicle_names=resource_vehicle_names,
        secondary_camera_vehicle_names=secondary_camera_vehicle_names,
    )
    d4_metrics = _d4_metrics(decisions)
    metrics: dict[str, Any] = {
        "case_name": normalized_case,
        "comparison_role": comparison_role,
        "active_degradation_review_label": active_degradation_review_label,
        "geometry": geometry,
        "secondary_height_above_targets_m": geometry.get("secondary_height_above_targets_m", 0.0),
        **detection_metrics,
        **secondary_funnel_metrics,
        **_secondary_guidance_metrics(
            frames,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        ),
        **_secondary_registration_candidate_metrics(registration_candidates),
        **d4_metrics,
        "terminal_observation_count": len(observations),
        "cross_view_association_count": len(cross_view),
        "duplicate_terminal_lock_risk": any(item.duplicate_terminal_lock_risk for item in cross_view),
        "ambiguous_fov_event_count": sum(
            1
            for observation in observations
            if observation.terminal_association is not None
            and observation.terminal_association.decision_state in {"ambiguous", "hold", "reacquire"}
        ),
        "terminal_lock_accuracy": _terminal_lock_accuracy(observations),
        "terminal_associator_call_count": sum(
            1
            for observation in observations
            if observation.metadata.get("terminal_associator_used") is True
        ),
        "terminal_associator_locked_count": _terminal_decision_count(observations, "locked"),
        "terminal_associator_ambiguous_count": _terminal_decision_count(observations, "ambiguous"),
        "terminal_associator_hold_count": _terminal_decision_count(observations, "hold"),
        "terminal_associator_reacquire_count": _terminal_decision_count(observations, "reacquire"),
    }

    observation_path = _write_jsonl(
        output_dir / "d5_terminal_observations.jsonl",
        (_terminal_observation_payload(item) for item in observations),
    )
    cross_view_path = _write_json(
        output_dir / "d5_cross_view_associations.json",
        [_jsonable(item) for item in cross_view],
    )
    candidate_path = _write_jsonl(
        output_dir / "d5_detect_to_global_candidates.jsonl",
        registration_candidates,
    )
    decision_path = _write_jsonl(output_dir / "d4_decisions.jsonl", decisions)
    metrics_path = _write_json(output_dir / "d4d5_stress_metrics.json", metrics)
    report_path = _write_case_report(
        output_dir / "D4_D5_5V5_STRESS_CASE_REPORT.md",
        metrics,
        decisions,
    )
    return D4D5StressAnalysisResult(
        case_name=normalized_case,
        output_paths={
            "d5_terminal_observations_jsonl": observation_path,
            "d5_cross_view_associations_json": cross_view_path,
            "d5_detect_to_global_candidates_jsonl": candidate_path,
            "d4_decisions_jsonl": decision_path,
            "d4d5_stress_metrics_json": metrics_path,
            "d4d5_stress_case_report": report_path,
        },
        metrics=metrics,
    )


def write_d4d5_sequence_report(
    path: Path,
    case_metrics: list[dict[str, Any]],
) -> Path:
    """Write the main-level aggregate D4/D5 stress report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# D4/D5 5v5 AirSim Stress Report",
        "",
        "本报告由 main agent 汇总生成。D5 负责终端多视角证据，D4 负责降级仲裁；main 只做运行编排、日志收集和结果汇总。",
        "",
        "## 场景几何",
    ]
    if case_metrics:
        geometry = case_metrics[0].get("geometry", {})
        lines.extend(
            [
                f"- 目标数量：{geometry.get('target_count', 0)}",
                f"- 拦截镜头数量：{geometry.get('resource_camera_count', 0)}",
                f"- 二级侦察镜头数量：{geometry.get('secondary_camera_count', 0)}",
                f"- 平均目标间距：{geometry.get('target_spacing_m', 0.0):.2f} m",
                f"- 平均主镜头间距：{geometry.get('resource_camera_spacing_m', 0.0):.2f} m",
                f"- 平均初始目标距离：{geometry.get('assigned_target_distance_m', 0.0):.2f} m",
                f"- 二级镜头相对目标高度：{geometry.get('secondary_height_above_targets_m', 0.0):.2f} m",
                "",
            ]
        )
    lines.extend(
        [
            "## 三类降级结果",
            "",
            "| Case | D4主动作 | 模式 | 二级模式 | 云台OK率 | 二级节点 | 多目标视场率 | 单二级全局视野 | 二级网络联合覆盖 | 网络覆盖均值 | detect->cross-view gap | 主要断点 | 二级bbox均值(px^2) | `cross_view_association_count` | `duplicate_terminal_lock_risk` | 终端准确率 | 歧义事件 |",
            "| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for metrics in case_metrics:
        bbox_stats = metrics.get("secondary_bbox_area_px_stats", {})
        reject_counts = metrics.get("secondary_detect_to_cross_view_reject_reason_counts", {})
        top_reject = _top_rejection_reason(reject_counts)
        lines.append(
            "| {case} | {action} | {mode} | {recon_mode} | {gimbal_ok:.2f} | {secondary} | {fov:.2f} | {recon:.2f} | {network:.2f} | {network_mean:.2f} | {gap:.2f} | {top_reject} | {bbox_mean:.2f} | {cross_view} | {duplicate} | {acc:.2f} | {ambiguous} |".format(
                case=metrics.get("case_name", ""),
                action=metrics.get("dominant_d4_action", ""),
                mode=metrics.get("dominant_degradation_mode", ""),
                recon_mode=metrics.get("secondary_recon_mode", "-"),
                gimbal_ok=float(metrics.get("secondary_gimbal_pointing_ok_rate", 0.0)),
                secondary=metrics.get("selected_secondary_node_id") or "-",
                fov=float(metrics.get("multi_target_fov_rate", 0.0)),
                recon=float(metrics.get("secondary_single_camera_full_view_frame_rate", 0.0)),
                network=float(metrics.get("secondary_network_joint_full_view_frame_rate", 0.0)),
                network_mean=float(metrics.get("secondary_network_mean_coverage_ratio", 0.0)),
                gap=float(metrics.get("cross_view_conversion_gap", 0.0)),
                top_reject=top_reject or "-",
                bbox_mean=float(bbox_stats.get("mean", 0.0)),
                cross_view=int(metrics.get("cross_view_association_count", 0)),
                duplicate=bool(metrics.get("duplicate_terminal_lock_risk", False)),
                acc=float(metrics.get("terminal_lock_accuracy", 0.0)),
                ambiguous=int(metrics.get("ambiguous_fov_event_count", 0)),
            )
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- `no_degradation` 用于验证中心分配、终端视觉和二级侦察证据一致时，D4 不触发降级。",
            "- `degrade_to_secondary` 用于验证中心失效后，二级侦察节点优先接管；中心正常时终端不一致只请求观测辅助或中心重规划。",
            "- `degrade_to_distributed` 用于验证中心和二级节点均不可用或链路过期后，D4 才进入完全无中心的分散模式。",
            "- D5 全程只汇报观测、身份和跨视角风险，不创建或改写 `global_track_id`。",
            "- 兼容字段：`secondary_global_view_rate` 等价于单二级全局视野；`secondary_network_global_view_rate` 等价于二级网络联合覆盖。",
            "- 单二级全局视野表示单个二级相机同帧看全目标；二级网络联合覆盖表示所有二级相机同帧目标并集看全目标；`cross_view_association_count` 才表示已形成既有 `global_track_id` 支持。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _terminal_observations_for_frame(
    frame: AirSimFrame,
    *,
    case_name: str,
    resource_vehicle_names: tuple[str, ...],
    secondary_camera_vehicle_names: tuple[str, ...],
    terminal_associator: TerminalAssociator,
) -> list[TerminalObservation]:
    detections_by_camera = _detections_by_camera(frame.visual_detections)
    global_tracks = _global_tracks_from_frame(frame)
    target_ids = [track.global_track_id.removeprefix("G-") for track in global_tracks]
    observations: list[TerminalObservation] = []
    for index, vehicle_name in enumerate(resource_vehicle_names):
        resource_id = f"INT-{index + 1:02d}"
        assigned_target_id = f"TGT-{index + 1:03d}"
        observed_target_id = _observed_target_id(
            assigned_target_id,
            target_ids=target_ids,
            case_name=case_name,
        )
        mismatch_frames = 0 if observed_target_id == assigned_target_id else 3
        non_locked_frames = 0 if observed_target_id == assigned_target_id else 3
        camera = _camera_model_for_resource(frame, vehicle_name, assigned_target_id)
        local_tracks = _local_tracks_for_camera(
            detections_by_camera.get(f"{vehicle_name}:0", ()),
            frame=frame,
            camera=camera,
            global_tracks=global_tracks,
            case_name=case_name,
            assigned_target_id=assigned_target_id,
            observed_target_id=observed_target_id,
            terminal_associator=terminal_associator,
        )
        recon_cues = _recon_cues(
            frame,
            assigned_target_id=assigned_target_id,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
            enabled=case_name != "degrade_to_distributed",
            camera=camera,
            global_tracks=global_tracks,
            terminal_associator=terminal_associator,
            target_resource_id=resource_id,
        )
        assignment = Assignment(
            assigned_global_track_id=_global_id(assigned_target_id),
            assignment_version=1,
            timestamp=frame.timestamp,
            require_version_match=True,
            plan_id=f"{case_name}:plan",
            plan_version=1,
            authorization_state="recorded",
            resource_id=resource_id,
        )
        association = terminal_associator.decide(
            assignment=assignment,
            global_tracks=global_tracks,
            local_tracks=local_tracks,
            identity_claims=[],
            camera=camera,
            current_time=frame.timestamp,
            recon_image_cues=recon_cues,
        )
        local_track = _local_track_by_id(local_tracks, association.local_track_id)
        if local_track is None:
            local_track = local_tracks[0] if local_tracks else None
        observations.append(
            TerminalObservation(
                resource_id=resource_id,
                source_node_id=resource_id,
                link_type="c2_direct" if case_name == "no_degradation" else "interceptor_peer",
                timestamp=frame.timestamp,
                local_track=local_track,
                terminal_association=association,
                recon_image_cues=tuple(recon_cues),
                camera_id=f"{vehicle_name}:0",
                frame_id=f"{frame.episode_id}:{frame.frame_index:04d}",
                arrival_timestamp=frame.timestamp + 0.05,
                metadata={
                    "case_name": case_name,
                    "assigned_target_id": assigned_target_id,
                    "observed_target_id": observed_target_id,
                    "consecutive_mismatch_frames": mismatch_frames,
                    "consecutive_non_locked_frames": non_locked_frames,
                    "terminal_associator_used": True,
                    "terminal_associator_reason": association.reason,
                    "candidate_cost_margin": _candidate_cost_margin(association.candidate_costs),
                    "local_track_count": len(local_tracks),
                    "bbox_schema": "xyxy",
                    "bbox_schema_sources": ("airsim_bbox_xyxy", "yolo_xyxy"),
                },
            )
        )
    return observations


def _global_tracks_from_frame(frame: AirSimFrame) -> list[GlobalTrack]:
    tracks: list[GlobalTrack] = []
    for obj in sorted(frame.truth_objects, key=lambda item: item.object_id):
        covariance = np.asarray(obj.covariance_ned, dtype=float)
        if covariance.shape != (3, 3) or not np.all(np.isfinite(covariance)):
            covariance = np.diag([1.0, 1.0, 1.0])
        tracks.append(
            GlobalTrack(
                global_track_id=_global_id(obj.object_id),
                position=np.asarray(obj.position_ned, dtype=float),
                velocity=np.asarray(obj.velocity_ned, dtype=float),
                covariance=covariance + np.eye(3) * 0.01,
                category=obj.classification_hint or "uav",
                timestamp=frame.timestamp,
                track_version=1,
            )
        )
    return tracks


def _observed_target_id(
    assigned_target_id: str,
    *,
    target_ids: list[str],
    case_name: str,
) -> str:
    if case_name == "no_degradation" or not target_ids:
        return assigned_target_id
    if assigned_target_id not in target_ids:
        return target_ids[0]
    index = target_ids.index(assigned_target_id)
    return target_ids[(index + 1) % len(target_ids)]


def _camera_model_for_resource(
    frame: AirSimFrame,
    vehicle_name: str,
    assigned_target_id: str,
) -> CameraModel:
    camera_info = next((camera for camera in frame.cameras if camera.owner_id == vehicle_name), None)
    target = _truth_object_position(frame, assigned_target_id)
    if camera_info is None:
        resource = next(
            (
                item
                for item in frame.resources
                if item.metadata.get("airsim_vehicle_name") == vehicle_name
                or item.resource_id == vehicle_name
            ),
            None,
        )
        camera_position = np.asarray(resource.position_ned if resource else (0.0, 0.0, 0.0), dtype=float)
        width, height = 640, 480
        fx = fy = 320.0
        cx, cy = width * 0.5, height * 0.5
    else:
        camera_position = np.asarray(camera_info.position_ned, dtype=float)
        width, height = int(camera_info.width), int(camera_info.height)
        fx = float(camera_info.fx if camera_info.fx > 0.0 else max(width, 1) * 0.5)
        fy = float(camera_info.fy if camera_info.fy > 0.0 else max(height, 1) * 0.5)
        cx = float(camera_info.cx if 0.0 < camera_info.cx < width else width * 0.5)
        cy = float(camera_info.cy if 0.0 < camera_info.cy < height else height * 0.5)
    target_position = target if target is not None else camera_position + np.array([1.0, 0.0, 0.0])
    rotation = _look_at_world_to_camera(camera_position, target_position)
    translation = -rotation @ camera_position
    return CameraModel(
        K=np.array(
            [
                [fx, 0.0, cx],
                [0.0, fy, cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=rotation,
        t=translation,
        image_size=(width, height),
        measurement_cov=np.diag([9.0, 9.0]),
    )


def _truth_object_position(frame: AirSimFrame, target_id: str) -> np.ndarray | None:
    for obj in frame.truth_objects:
        if obj.object_id == target_id:
            return np.asarray(obj.position_ned, dtype=float)
    return None


def _look_at_world_to_camera(camera_position: np.ndarray, target_position: np.ndarray) -> np.ndarray:
    forward = _unit_vector(target_position - camera_position, fallback=np.array([1.0, 0.0, 0.0]))
    up_hint = np.array([0.0, 0.0, -1.0], dtype=float)
    right = np.cross(up_hint, forward)
    if np.linalg.norm(right) < 1e-9:
        right = np.cross(np.array([0.0, 1.0, 0.0], dtype=float), forward)
    right = _unit_vector(right, fallback=np.array([0.0, 1.0, 0.0]))
    camera_y = _unit_vector(np.cross(forward, right), fallback=np.array([0.0, 0.0, -1.0]))
    return np.vstack([right, camera_y, forward])


def _unit_vector(vector: np.ndarray, *, fallback: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not np.isfinite(norm) or norm <= 1e-9:
        return fallback.astype(float)
    return np.asarray(vector, dtype=float) / norm


def _local_tracks_for_camera(
    detections: tuple[AirSimDetectionBox, ...],
    *,
    frame: AirSimFrame,
    camera: CameraModel,
    global_tracks: list[GlobalTrack],
    case_name: str,
    assigned_target_id: str,
    observed_target_id: str,
    terminal_associator: TerminalAssociator,
) -> list[LocalVisualTrack]:
    projections = terminal_associator.project_tracks_to_image(
        global_tracks,
        camera,
        timestamp=frame.timestamp,
    )
    local_tracks: list[LocalVisualTrack] = []
    for detection in detections:
        target_id = str(detection.object_id)
        if case_name in {"degrade_to_secondary", "degrade_to_distributed"} and target_id == assigned_target_id:
            continue
        projection = projections.get(_global_id(target_id))
        center_px = np.asarray(detection.center_px, dtype=float)
        if projection is not None and projection.valid and projection.pixel is not None:
            center_px = np.asarray(projection.pixel, dtype=float)
        if case_name in {"degrade_to_secondary", "degrade_to_distributed"} and target_id == observed_target_id:
            # Preserve the mismatched visual evidence as a good local track for
            # a different target. The assigned target is absent, so D5 should
            # naturally return reacquire instead of being told to do so.
            center_px = center_px.copy()
        local_tracks.append(
            _local_track_from_detection(
                detection,
                frame.timestamp,
                center_px=center_px,
                min_mot_history=5,
            )
        )
    return local_tracks


def _local_track_by_id(
    local_tracks: list[LocalVisualTrack],
    local_track_id: str | None,
) -> LocalVisualTrack | None:
    if local_track_id is None:
        return None
    for track in local_tracks:
        if track.local_track_id == local_track_id:
            return track
    return None


def _d4_decisions_for_frame(
    frame: AirSimFrame,
    observations: list[TerminalObservation],
    d4_adapter: D4ArbitrationAdapter,
    *,
    case_name: str,
    secondary_camera_vehicle_names: tuple[str, ...],
    d5_evidence_observations: list[TerminalObservation] | None = None,
    secondary_registration: Any | None = None,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    secondary_nodes = _secondary_nodes(case_name, secondary_camera_vehicle_names, frame=frame)
    communications = _communication_summaries(case_name, secondary_nodes, frame.timestamp)
    d5_evidence = _d5_evidence_for_frame(
        frame,
        d5_evidence_observations if d5_evidence_observations is not None else observations,
        secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        secondary_registration=secondary_registration,
    )
    for observation in observations:
        association = observation.terminal_association
        if association is None:
            continue
        assigned_target_id = str(observation.metadata.get("assigned_target_id", "TGT-001"))
        observed_target_id = str(observation.metadata.get("observed_target_id", assigned_target_id))
        coverage_cell = _coverage_cell_for_target(frame, assigned_target_id)
        track_uncertainty = TrackUncertaintySummary(
            track_id=_global_id(assigned_target_id),
            coverage_cell=coverage_cell,
            position_sigma_m=8.0 if case_name == "no_degradation" else 38.0,
            covariance_trace=300.0 if case_name == "no_degradation" else 1800.0,
            velocity_sigma_mps=0.4 if case_name == "no_degradation" else 1.8,
            measurement_age_s=0.5 if case_name == "no_degradation" else 2.2,
        )
        association_risk = AssociationRiskSummary(
            track_id=_global_id(assigned_target_id),
            ambiguity_score=0.08 if case_name == "no_degradation" else 0.72,
            id_switch_count=0 if case_name == "no_degradation" else 1,
            duplicate_track_count=0,
            track_continuity=0.96 if case_name == "no_degradation" else 0.58,
        )
        assignment_validity = AssignmentValiditySummary(
            global_track_id=_global_id(assigned_target_id),
            assigned_resource_id=observation.resource_id,
            plan_version=1,
            is_current=True,
            plan_age_s=0.5 if case_name == "no_degradation" else 3.5,
            cost_margin=0.42 if case_name == "no_degradation" else 0.06,
        )
        terminal_summary = TerminalAssociationSummary(
            resource_id=observation.resource_id,
            assigned_global_track_id=association.assigned_global_track_id,
            decision_state=TerminalDecisionState(association.decision_state),
            association_confidence=association.association_confidence,
            ambiguity_score=association.ambiguity_score,
            coverage_cell=track_uncertainty.coverage_cell,
            observed_global_track_id=_global_id(observed_target_id),
            consecutive_non_locked_frames=int(observation.metadata.get("consecutive_non_locked_frames", 0)),
            consecutive_mismatch_frames=int(observation.metadata.get("consecutive_mismatch_frames", 0)),
            friend_conflict=False,
            duplicate_terminal_lock=False,
            cross_view_risk_score=0.05 if case_name == "no_degradation" else 0.76,
            cross_view_support_count=1,
        )
        result = d4_adapter.evaluate(
            timestamp=frame.timestamp,
            track=track_uncertainty,
            association_result=association_risk,
            plan=assignment_validity,
            assignment=assignment_validity,
            terminal_association=terminal_summary,
            d5_evidence=d5_evidence,
            c2_health=(
                C2Health.NORMAL
                if case_name == "no_degradation"
                else C2Health.FAILED
            ),
            secondary_nodes=secondary_nodes,
            communication_records=communications,
            coverage_cell=track_uncertainty.coverage_cell,
            resource_id=observation.resource_id,
            global_track_id=_global_id(assigned_target_id),
            observed_global_track_id=_global_id(observed_target_id),
            consecutive_non_locked_frames=int(observation.metadata.get("consecutive_non_locked_frames", 0)),
            consecutive_mismatch_frames=int(observation.metadata.get("consecutive_mismatch_frames", 0)),
            trigger_timestamp=frame.timestamp,
        )
        decision = result.decision
        metrics = decision.to_metrics(
            failover_time=0.0 if decision.action.value == "continue_center" else 1.0,
            secondary_selected_rate=1.0 if decision.target_node_id else 0.0,
            distributed_conflict_count=0,
        )
        summaries.append(
            {
                "timestamp": frame.timestamp,
                "frame_index": frame.frame_index,
                "resource_id": observation.resource_id,
                "assigned_global_track_id": association.assigned_global_track_id,
                "observed_global_track_id": _global_id(observed_target_id),
                "case_name": case_name,
                **metrics,
                "reason": decision.reason,
                "d4_event_metadata": result.record.to_event_metadata(),
                "secondary_detect_available_but_not_registered": (
                    result.record.secondary_detect_available_but_not_registered
                ),
                "secondary_detect_to_cross_view_diagnostic": (
                    result.record.secondary_detect_to_cross_view_diagnostic
                ),
            }
        )
    return summaries


def _detection_metrics(
    frames: list[AirSimFrame],
    *,
    resource_vehicle_names: tuple[str, ...],
    secondary_camera_vehicle_names: tuple[str, ...],
) -> dict[str, Any]:
    per_camera_max: Counter[str] = Counter()
    raw_overlap: dict[str, set[str]] = defaultdict(set)
    secondary_network_global_frame_count = 0
    secondary_bbox_areas: list[float] = []
    secondary_bbox_areas_by_camera: dict[str, list[float]] = defaultdict(list)
    secondary_camera_ids = tuple(f"{name}:0" for name in secondary_camera_vehicle_names)
    secondary_camera_id_set = set(secondary_camera_ids)
    for frame in frames:
        by_camera = _detections_by_camera(frame.visual_detections)
        secondary_frame_objects: set[str] = set()
        for camera_id, detections in by_camera.items():
            per_camera_max[camera_id] = max(per_camera_max[camera_id], len(detections))
            for detection in detections:
                raw_overlap[str(detection.object_id)].add(camera_id)
                if camera_id in secondary_camera_id_set:
                    secondary_frame_objects.add(str(detection.object_id))
                    area = _bbox_area_px(detection.bbox_xyxy)
                    secondary_bbox_areas.append(area)
                    secondary_bbox_areas_by_camera[camera_id].append(area)
        if len(secondary_frame_objects) >= 5:
            secondary_network_global_frame_count += 1
    primary_camera_ids = tuple(f"{name}:0" for name in resource_vehicle_names)
    primary_multi = sum(1 for camera_id in primary_camera_ids if per_camera_max[camera_id] >= 2)
    secondary_global = sum(1 for camera_id in secondary_camera_ids if per_camera_max[camera_id] >= 5)
    return {
        "per_camera_detection_count": dict(sorted(per_camera_max.items())),
        "multi_target_fov_rate": primary_multi / max(len(primary_camera_ids), 1),
        "secondary_global_view_rate": secondary_global / max(len(secondary_camera_ids), 1),
        "secondary_network_global_view_rate": secondary_network_global_frame_count / max(len(frames), 1),
        "secondary_bbox_area_px_stats": _numeric_stats(secondary_bbox_areas),
        "secondary_bbox_area_by_camera_px_stats": {
            camera_id: _numeric_stats(secondary_bbox_areas_by_camera.get(camera_id, []))
            for camera_id in secondary_camera_ids
        },
        "cross_view_overlap_count": sum(1 for cameras in raw_overlap.values() if len(cameras) > 1),
        "raw_detection_count": sum(sum(1 for _ in frame.visual_detections) for frame in frames),
    }


def _secondary_registration_for_frame(
    frame: AirSimFrame,
    *,
    secondary_camera_vehicle_names: tuple[str, ...],
    terminal_associator: TerminalAssociator,
) -> Any:
    global_tracks = _global_tracks_from_frame(frame)
    active_ids = {_global_id(obj.object_id) for obj in frame.truth_objects}
    detections_by_camera = _detections_by_camera(frame.visual_detections)
    secondary_visible_ids = {
        _global_id(detection.object_id)
        for camera_name in secondary_camera_vehicle_names
        for detection in detections_by_camera.get(f"{camera_name}:0", ())
    }
    network_union_complete = bool(active_ids) and active_ids.issubset(secondary_visible_ids)
    batches = _secondary_camera_batches_for_frame(
        frame,
        secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        global_tracks=global_tracks,
        network_union_complete=network_union_complete,
    )
    bindings = tuple(
        GlobalTrackBinding(
            global_track_id=track.global_track_id,
            binding_source="d2_global_track_table",
            timestamp=frame.timestamp,
            authorization_state="authorized",
            metadata={"source": "airsim_stress_global_track"},
        )
        for track in global_tracks
    )
    return register_local_visual_tracks_to_global_tracks(
        global_tracks=global_tracks,
        camera_batches=batches,
        bindings=bindings,
        current_time=frame.timestamp,
        max_binding_age_s=2.0,
        network_union_complete=network_union_complete,
    )


def _secondary_registration_for_frames(
    frames: list[AirSimFrame],
    *,
    secondary_camera_vehicle_names: tuple[str, ...],
    terminal_associator: TerminalAssociator,
) -> Any:
    if not frames:
        return register_local_visual_tracks_to_global_tracks(
            global_tracks=(),
            camera_batches=(),
            bindings=(),
            current_time=0.0,
            max_binding_age_s=None,
            network_union_complete=None,
        )
    reference_tracks = _global_tracks_from_frame(frames[0])
    batches: list[CameraLocalTrackBatch] = []
    for frame in frames:
        global_tracks = _global_tracks_from_frame(frame)
        detections_by_camera = _detections_by_camera(frame.visual_detections)
        active_ids = {_global_id(obj.object_id) for obj in frame.truth_objects}
        secondary_visible_ids = {
            _global_id(detection.object_id)
            for camera_name in secondary_camera_vehicle_names
            for detection in detections_by_camera.get(f"{camera_name}:0", ())
        }
        batches.extend(
            _secondary_camera_batches_for_frame(
                frame,
                secondary_camera_vehicle_names=secondary_camera_vehicle_names,
                global_tracks=global_tracks,
                network_union_complete=bool(active_ids) and active_ids.issubset(secondary_visible_ids),
            )
        )
    bindings = tuple(
        GlobalTrackBinding(
            global_track_id=track.global_track_id,
            binding_source="d2_global_track_table",
            timestamp=None,
            authorization_state="authorized",
            metadata={"source": "airsim_stress_global_track_sequence"},
        )
        for track in reference_tracks
    )
    return register_local_visual_tracks_to_global_tracks(
        global_tracks=reference_tracks,
        camera_batches=batches,
        bindings=bindings,
        current_time=None,
        max_binding_age_s=None,
        network_union_complete=None,
    )


def _secondary_camera_batches_for_frame(
    frame: AirSimFrame,
    *,
    secondary_camera_vehicle_names: tuple[str, ...],
    global_tracks: list[GlobalTrack],
    network_union_complete: bool,
) -> list[CameraLocalTrackBatch]:
    detections_by_camera = _detections_by_camera(frame.visual_detections)
    batches: list[CameraLocalTrackBatch] = []
    for vehicle_name in secondary_camera_vehicle_names:
        camera_id = f"{vehicle_name}:0"
        detections = detections_by_camera.get(camera_id, ())
        camera, camera_pose_source = _camera_model_for_secondary(frame, vehicle_name, global_tracks)
        projections = TerminalAssociator().project_tracks_to_image(
            global_tracks,
            camera,
            timestamp=frame.timestamp,
        )
        local_tracks = tuple(
            _local_track_from_detection(
                detection,
                frame.timestamp,
                center_px=_projected_or_detected_center_px(
                    detection,
                    projections.get(_global_id(detection.object_id)),
                ),
                min_mot_history=3,
            )
            for detection in detections
        )
        truth_by_local = {
            track.local_track_id: _global_id(detection.object_id)
            for track, detection in zip(local_tracks, detections)
        }
        batches.append(
            CameraLocalTrackBatch(
                resource_id=vehicle_name,
                camera_id=camera_id,
                camera=camera,
                local_tracks=local_tracks,
                frame_id=f"{frame.episode_id}:{frame.frame_index:04d}",
                timestamp=frame.timestamp,
                arrival_timestamp=frame.timestamp + 0.05,
                covariance_px=np.diag([9.0, 9.0]),
                source_node_id=vehicle_name,
                link_type="secondary_recon_video_metadata",
                metadata={
                    "is_secondary": True,
                    "camera_pose_source": camera_pose_source,
                    "offline_truth_by_local_track_id": truth_by_local,
                    "network_union_complete": network_union_complete,
                    "truth_id_online_use": "ignored",
                },
            )
        )
    return batches


def _projected_or_detected_center_px(
    detection: AirSimDetectionBox,
    projection: Any | None,
) -> np.ndarray:
    if (
        projection is not None
        and bool(getattr(projection, "valid", False))
        and getattr(projection, "pixel", None) is not None
    ):
        return np.asarray(projection.pixel, dtype=float)
    return np.asarray(detection.center_px, dtype=float)


def _camera_model_for_secondary(
    frame: AirSimFrame,
    vehicle_name: str,
    global_tracks: list[GlobalTrack],
) -> tuple[CameraModel, str]:
    camera_info = next((camera for camera in frame.cameras if camera.owner_id == vehicle_name), None)
    if camera_info is not None:
        try:
            return (
                camera_model_from_airsim_camera_info(
                    camera_info,
                    measurement_sigma_px=9.0,
                ),
                "airsim_camera_pose",
            )
        except Exception:
            pass
    if global_tracks:
        target_position = np.mean([track.position for track in global_tracks], axis=0)
    else:
        target_position = np.array([50.0, 0.0, -10.0], dtype=float)
    if camera_info is None:
        camera_position = np.array([50.0, 0.0, -60.0], dtype=float)
        width, height = 640, 480
        fx = fy = 320.0
        cx, cy = width * 0.5, height * 0.5
    else:
        camera_position = np.asarray(camera_info.position_ned, dtype=float)
        width, height = int(camera_info.width), int(camera_info.height)
        fx = float(camera_info.fx if camera_info.fx > 0.0 else max(width, 1) * 0.5)
        fy = float(camera_info.fy if camera_info.fy > 0.0 else max(height, 1) * 0.5)
        cx = float(camera_info.cx if 0.0 < camera_info.cx < width else width * 0.5)
        cy = float(camera_info.cy if 0.0 < camera_info.cy < height else height * 0.5)
    rotation = _look_at_world_to_camera(camera_position, np.asarray(target_position, dtype=float))
    translation = -rotation @ camera_position
    return (
        CameraModel(
            K=np.array(
                [
                    [fx, 0.0, cx],
                    [0.0, fy, cy],
                    [0.0, 0.0, 1.0],
                ],
                dtype=float,
            ),
            R=rotation,
            t=translation,
            image_size=(width, height),
            measurement_cov=np.diag([9.0, 9.0]),
        ),
        "look_at_fallback",
    )


def _d4_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts = Counter(str(item.get("d4_action", "")) for item in decisions)
    mode_counts = Counter(str(item.get("degradation_mode", "")) for item in decisions)
    diagnostic_counts = Counter(
        str(item.get("secondary_detect_to_cross_view_diagnostic", ""))
        for item in decisions
        if item.get("secondary_detect_to_cross_view_diagnostic")
    )
    selected_secondary = next(
        (item.get("target_node_id") for item in decisions if item.get("target_node_id")),
        None,
    )
    active_decisions = [
        item
        for item in decisions
        if str(item.get("degradation_mode", "")) == "active_degradation"
    ]
    review_labels = [
        str(item.get("active_degradation_review_label", "")).strip().lower()
        for item in active_decisions
    ]
    classified_labels = [
        label for label in review_labels if label in {"necessary", "unnecessary"}
    ]
    necessary_count = sum(label == "necessary" for label in classified_labels)
    unnecessary_count = sum(label == "unnecessary" for label in classified_labels)
    return {
        "d4_decision_count": len(decisions),
        "d4_action_counts": dict(action_counts),
        "degradation_mode_counts": dict(mode_counts),
        "dominant_d4_action": action_counts.most_common(1)[0][0] if action_counts else "",
        "dominant_degradation_mode": mode_counts.most_common(1)[0][0] if mode_counts else "",
        "selected_secondary_node_id": selected_secondary,
        "secondary_detect_available_but_not_registered_count": sum(
            1 for item in decisions if item.get("secondary_detect_available_but_not_registered")
        ),
        "secondary_detect_to_cross_view_diagnostic_counts": dict(diagnostic_counts),
        "active_degradation_count": len(active_decisions),
        "active_degradation_label_count": len(classified_labels),
        "active_degradation_precision": (
            necessary_count / len(classified_labels) if classified_labels else None
        ),
        "unnecessary_degradation_count": unnecessary_count,
    }


def _secondary_coverage_frames(
    frames: list[AirSimFrame],
    *,
    secondary_camera_vehicle_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    secondary_camera_ids = {f"{name}:0" for name in secondary_camera_vehicle_names}
    coverage_frames: list[dict[str, Any]] = []
    for frame in frames:
        active_target_ids = tuple(_global_id(obj.object_id) for obj in frame.truth_objects)
        by_camera = _detections_by_camera(frame.visual_detections)
        guidance_by_vehicle = _secondary_guidance_by_vehicle(frame)
        secondary_cameras: dict[str, dict[str, Any]] = {}
        for camera_id in sorted(secondary_camera_ids):
            detections = by_camera.get(camera_id, ())
            vehicle_name = camera_id.split(":", 1)[0]
            guidance = guidance_by_vehicle.get(vehicle_name, {})
            secondary_cameras[camera_id] = {
                "camera_id": camera_id,
                "resource_id": vehicle_name,
                "timestamp": frame.timestamp,
                "active_target_ids": active_target_ids,
                "visible_target_ids": tuple(_global_id(detection.object_id) for detection in detections),
                "detections": [
                    {
                        "offline_target_id": _global_id(detection.object_id),
                        "bbox_xyxy": detection.bbox_xyxy,
                        "confidence": detection.confidence,
                    }
                    for detection in detections
                ],
                "is_secondary": True,
                "capability_class": guidance.get("capability_class"),
                "cue_source": guidance.get("cue_source"),
                "cue_position_ned": guidance.get("cue_position_ned"),
                "look_at_ned": guidance.get("look_at_ned"),
                "position_ned": guidance.get("position_ned"),
                "coverage_cell": guidance.get("coverage_cell"),
                "gimbal_pointing_ok": guidance.get("gimbal_pointing_ok"),
                "cue_pointing_error_m": guidance.get("cue_pointing_error_m"),
                "gimbal_pointing_metadata": guidance,
            }
        coverage_frames.append(
            {
                "frame_id": f"{frame.episode_id}:{frame.frame_index:04d}",
                "timestamp": frame.timestamp,
                "active_target_ids": active_target_ids,
                "secondary_cameras": secondary_cameras,
            }
        )
    return coverage_frames


def _secondary_guidance_by_vehicle(frame: AirSimFrame) -> dict[str, dict[str, Any]]:
    guidance_items = frame.metadata.get("cv_camera_guidance", [])
    return {
        str(item.get("vehicle_name")): dict(item)
        for item in guidance_items
        if item.get("role") == "secondary_recon_camera" and item.get("vehicle_name")
    }


def _secondary_guidance_metrics(
    frames: list[AirSimFrame],
    *,
    secondary_camera_vehicle_names: tuple[str, ...],
) -> dict[str, Any]:
    secondary_names = set(secondary_camera_vehicle_names)
    guidance_items = [
        dict(item)
        for frame in frames
        for item in frame.metadata.get("cv_camera_guidance", [])
        if item.get("role") == "secondary_recon_camera"
        and str(item.get("vehicle_name")) in secondary_names
    ]
    pointing_errors = [
        float(item.get("cue_pointing_error_m", 0.0))
        for item in guidance_items
        if item.get("cue_pointing_error_m") is not None
    ]
    ok_count = sum(1 for item in guidance_items if item.get("gimbal_pointing_ok") is True)
    capability_classes = sorted(
        {str(item.get("capability_class")) for item in guidance_items if item.get("capability_class")}
    )
    cue_sources = sorted({str(item.get("cue_source")) for item in guidance_items if item.get("cue_source")})
    mobile_count = sum(
        1 for item in guidance_items if str(item.get("capability_class")) == "mobile_high_recon"
    )
    return {
        "secondary_recon_mode": (
            "mobile_recon_gimbal" if mobile_count > 0 else "fixed_downlook_secondary"
        ),
        "secondary_guidance_record_count": len(guidance_items),
        "secondary_gimbal_pointing_ok_rate": ok_count / max(len(guidance_items), 1),
        "secondary_cue_pointing_error_m_stats": _numeric_stats(pointing_errors),
        "secondary_capability_classes": capability_classes,
        "secondary_cue_sources": cue_sources,
    }


def _secondary_registration_candidate_metrics(candidates: list[Any]) -> dict[str, Any]:
    candidate_count = len(candidates)
    selected_count = sum(1 for item in candidates if bool(getattr(item, "selected", False)))
    stable_count = sum(
        1 for item in candidates if bool(getattr(item, "stable_cross_view_support", False))
    )
    gate_pass_count = sum(1 for item in candidates if bool(getattr(item, "gate_passed", False)))
    projection_valid_count = sum(
        1 for item in candidates if bool(getattr(item, "projection_valid", False))
    )
    pose_sources = Counter(
        str(getattr(item, "camera_pose_source", "unknown")) for item in candidates
    )
    reject_counts: Counter[str] = Counter()
    pixel_errors: list[float] = []
    mahalanobis_values: list[float] = []
    for item in candidates:
        for reason in getattr(item, "reject_reasons", ()) or ():
            reject_counts[str(reason)] += 1
        pixel_error = getattr(item, "pixel_error_px", None)
        if pixel_error is not None and np.isfinite(float(pixel_error)):
            pixel_errors.append(float(pixel_error))
        mahalanobis_d2 = getattr(item, "mahalanobis_d2", None)
        if mahalanobis_d2 is not None and np.isfinite(float(mahalanobis_d2)):
            mahalanobis_values.append(float(mahalanobis_d2))
    return {
        "detect_to_global_candidate_count": candidate_count,
        "registered_candidate_count": selected_count,
        "stable_cross_view_registration_count": stable_count,
        "geometry_gate_pass_rate": gate_pass_count / max(candidate_count, 1),
        "projection_valid_rate": projection_valid_count / max(candidate_count, 1),
        "camera_pose_source_counts": dict(sorted(pose_sources.items())),
        "candidate_reject_reason_counts": dict(sorted(reject_counts.items())),
        "candidate_pixel_error_px_stats": _numeric_stats(pixel_errors),
        "candidate_mahalanobis_d2_stats": _numeric_stats(mahalanobis_values),
    }


def _secondary_funnel_metrics(summary: Any) -> dict[str, Any]:
    funnel = summary.funnel_counts
    rejection_counts = dict(summary.rejection_reason_counts)
    success_reason_names = {"registered_to_global_track"}
    rejection_counts = {
        str(reason): int(count)
        for reason, count in rejection_counts.items()
        if str(reason) not in success_reason_names
    }
    reject_reasons = tuple(
        reason for reason, count in rejection_counts.items() if int(count) > 0
    )
    cross_view_gap = max(0, int(funnel.detect_count) - int(funnel.cross_view_association_count))
    return {
        "secondary_single_camera_full_view_frame_rate": (
            summary.secondary_single_camera_full_view_frame_rate
        ),
        "secondary_network_joint_full_view_frame_rate": (
            summary.secondary_network_joint_full_view_frame_rate
        ),
        "secondary_global_view_rate": summary.secondary_single_camera_full_view_frame_rate,
        "secondary_network_global_view_rate": (
            summary.secondary_network_joint_full_view_frame_rate
        ),
        "secondary_camera_frame_visible_target_counts": dict(
            summary.secondary_camera_frame_visible_target_counts
        ),
        "secondary_network_frame_joint_visible_target_counts": dict(
            summary.secondary_network_frame_joint_visible_target_counts
        ),
        "secondary_camera_coverage_ratio_mean": dict(
            summary.secondary_camera_coverage_ratio_mean
        ),
        "secondary_camera_coverage_ratio_min": dict(
            summary.secondary_camera_coverage_ratio_min
        ),
        "secondary_single_camera_coverage_ratio_mean": (
            summary.secondary_single_camera_coverage_ratio_mean
        ),
        "secondary_single_camera_coverage_ratio_min": (
            summary.secondary_single_camera_coverage_ratio_min
        ),
        "secondary_network_joint_coverage_ratio_mean": (
            summary.secondary_network_joint_coverage_ratio_mean
        ),
        "secondary_network_joint_coverage_ratio_min": (
            summary.secondary_network_joint_coverage_ratio_min
        ),
        "secondary_network_mean_coverage_ratio": (
            summary.secondary_network_joint_coverage_ratio_mean
        ),
        "secondary_detection_funnel_counts": _jsonable(funnel),
        "cross_view_association_count": int(funnel.cross_view_association_count),
        "secondary_multi_support_count": int(funnel.multi_support_count),
        "secondary_detect_to_cross_view_reject_reason_counts": rejection_counts,
        "secondary_detect_to_cross_view_reject_reasons": reject_reasons,
        "cross_view_conversion_gap": float(cross_view_gap),
        "secondary_detect_available": int(funnel.detect_count) > 0,
        "secondary_detect_funnel_breakpoint_reasons": tuple(funnel.breakpoint_reasons),
    }


def _d5_evidence_for_frame(
    frame: AirSimFrame,
    observations: list[TerminalObservation],
    *,
    secondary_camera_vehicle_names: tuple[str, ...],
    secondary_registration: Any | None = None,
) -> dict[str, Any]:
    secondary_camera_ids = tuple(f"{name}:0" for name in secondary_camera_vehicle_names)
    frame_bus = TerminalObservationBus()
    for observation in observations:
        frame_bus.publish(observation)
    frame_cross_view = tuple(frame_bus.cross_view_associations())
    summary = summarize_secondary_visual_coverage_funnel(
        secondary_frames=_secondary_coverage_frames(
            [frame],
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        ),
        observations=observations,
        cross_view_associations=frame_cross_view,
        active_target_ids=tuple(_global_id(obj.object_id) for obj in frame.truth_objects),
        secondary_camera_ids=secondary_camera_ids,
        current_time=frame.timestamp,
    )
    metrics = _secondary_funnel_metrics(summary)
    if secondary_registration is not None and summary.camera_frames and summary.network_frames:
        evidence = build_secondary_frame_association_evidence(
            frame_id=f"{frame.episode_id}:{frame.frame_index:04d}",
            measurement_timestamp=frame.timestamp,
            arrival_timestamp=frame.timestamp + 0.05,
            camera_frames=summary.camera_frames,
            network_frame=summary.network_frames[0],
            registration_result=secondary_registration,
            detector_backend=str(frame.metadata.get("detection_backend") or "airsim_detect"),
            tracker_backend=str(frame.metadata.get("tracker_backend") or "camera_local_tracker"),
            cue_timestamp=frame.timestamp,
            calibration_metadata={
                "calibration_health": frame.metadata.get("calibration_health", "available"),
                "camera_pose_source": "airsim_camera_pose",
            },
        )
        metrics.update(evidence.to_terminal_association_summary_fields())
        metrics["frame_evidence"] = evidence.to_metadata()
    metrics["metadata"] = {
        **_jsonable(summary.metadata),
        "evidence_scope": "single_synchronized_frame",
        "episode_aggregate_allowed": False,
    }
    return metrics


def _geometry_summary(
    frame: AirSimFrame | None,
    resource_vehicle_names: tuple[str, ...],
    secondary_camera_vehicle_names: tuple[str, ...],
) -> dict[str, Any]:
    if frame is None:
        return {}
    targets = sorted(frame.truth_objects, key=lambda item: item.position_ned[1])
    resources = sorted(frame.resources, key=lambda item: item.position_ned[1])
    cameras_by_owner = {camera.owner_id: camera for camera in frame.cameras}
    secondaries = [cameras_by_owner[name] for name in secondary_camera_vehicle_names if name in cameras_by_owner]
    target_positions = [np.asarray(item.position_ned, dtype=float) for item in targets]
    resource_positions = [np.asarray(item.position_ned, dtype=float) for item in resources]
    target_spacing = _mean_adjacent_spacing(target_positions)
    resource_spacing = _mean_adjacent_spacing(resource_positions)
    assigned_distances = [
        float(np.linalg.norm(resource_positions[index] - target_positions[index]))
        for index in range(min(len(resource_positions), len(target_positions)))
    ]
    target_z = float(np.mean([position[2] for position in target_positions])) if target_positions else 0.0
    secondary_height = [
        abs(float(camera.position_ned[2]) - target_z)
        for camera in secondaries
    ]
    return {
        "target_count": len(targets),
        "resource_camera_count": len(resource_vehicle_names),
        "secondary_camera_count": len(secondary_camera_vehicle_names),
        "target_spacing_m": float(np.mean(target_spacing)) if target_spacing else 0.0,
        "resource_camera_spacing_m": float(np.mean(resource_spacing)) if resource_spacing else 0.0,
        "assigned_target_distance_m": float(np.mean(assigned_distances)) if assigned_distances else 0.0,
        "secondary_height_above_targets_m": float(np.mean(secondary_height)) if secondary_height else 0.0,
    }


def _secondary_nodes(
    case_name: str,
    secondary_camera_vehicle_names: tuple[str, ...],
    *,
    frame: AirSimFrame | None = None,
) -> list[ResourceSummary]:
    if case_name == "degrade_to_distributed":
        return []
    guidance_by_vehicle = _secondary_guidance_by_vehicle(frame) if frame is not None else {}
    nodes: list[ResourceSummary] = []
    for index, vehicle_name in enumerate(secondary_camera_vehicle_names):
        guidance = guidance_by_vehicle.get(vehicle_name, {})
        capability = str(guidance.get("capability_class") or "fixed_tethered_secondary")
        is_mobile = capability in {"mobile_high_recon", "mobile_secondary_recon"}
        role = NodeRole.MOBILE_HIGH_RECON if is_mobile else NodeRole.FIXED_TETHERED_SECONDARY
        nodes.append(
            ResourceSummary(
                node_id=f"SEC-{index + 1:02d}",
                capability_class=capability,
                availability_band=AvailabilityBand.HIGH,
                comm_band=CommBand.GOOD,
                takeover_priority=index + 1,
                node_role=role,
                coordinator_only=True,
                coverage_cell=str(
                    guidance.get("coverage_cell")
                    or _secondary_coverage_cell_for_index(
                        index,
                        len(secondary_camera_vehicle_names),
                    )
                ),
                cue_freshness_s=(
                    float(guidance["cue_freshness_s"])
                    if guidance.get("cue_freshness_s") is not None
                    else None
                ),
                gimbal_pointing_ok=(
                    bool(guidance["gimbal_pointing_ok"])
                    if guidance.get("gimbal_pointing_ok") is not None
                    else None
                ),
                epoch=1,
            )
        )
    return nodes


def _coverage_cell_for_target(frame: AirSimFrame, target_id: str) -> str:
    for obj in frame.truth_objects:
        if obj.object_id == target_id and obj.coverage_cell:
            return str(obj.coverage_cell)
    return "cell-north" if target_id <= "TGT-003" else "cell-south"


def _secondary_coverage_cell_for_index(index: int, count: int) -> str:
    if int(count) <= 1:
        return "all"
    if int(count) == 2:
        return "cell-north" if int(index) == 0 else "cell-south"
    if int(count) == 3:
        return ("cell-left", "cell-center", "cell-right")[max(0, min(2, int(index)))]
    return f"cell-{int(index) + 1:02d}"


def _communication_summaries(
    case_name: str,
    secondary_nodes: list[ResourceSummary],
    timestamp: float,
) -> list[CommunicationSummary]:
    if case_name == "degrade_to_distributed":
        return []
    return [
        CommunicationSummary(
            source_node_id=node.node_id,
            target_node_id="MAIN-C2",
            relay_node_id=None,
            link_type=LinkType.VIDEO_CUE,
            sent_timestamp=timestamp,
            received_timestamp=timestamp + 0.05,
            payload_kind=PayloadKind.VIDEO_METADATA,
            stale_after_s=1.5,
            sequence_id=f"{case_name}:{node.node_id}:{timestamp:.2f}",
        )
        for node in secondary_nodes
    ]


def _recon_cues(
    frame: AirSimFrame,
    *,
    assigned_target_id: str,
    secondary_camera_vehicle_names: tuple[str, ...],
    enabled: bool,
    camera: CameraModel,
    global_tracks: list[GlobalTrack],
    terminal_associator: TerminalAssociator,
    target_resource_id: str,
) -> list[ReconImageCue]:
    if not enabled:
        return []
    projection = terminal_associator.project_tracks_to_image(
        [track for track in global_tracks if track.global_track_id == _global_id(assigned_target_id)],
        camera,
        timestamp=frame.timestamp,
    ).get(_global_id(assigned_target_id))
    center_px = projection.pixel if projection is not None and projection.valid else None
    cues: list[ReconImageCue] = []
    for index, vehicle_name in enumerate(secondary_camera_vehicle_names):
        cues.append(
            ReconImageCue(
                cue_id=f"{frame.episode_id}:{frame.frame_index:04d}:{vehicle_name}:{assigned_target_id}",
                producer_node_id=f"SEC-{index + 1:02d}",
                timestamp=frame.timestamp,
                image_frame_id=f"{vehicle_name}:0->{target_resource_id}:{frame.frame_index:04d}",
                global_track_id=_global_id(assigned_target_id),
                center_px=center_px,
                confidence=0.9,
                scoped_resource_ids=(target_resource_id,),
                metadata={
                    "source": "secondary_recon_global_view",
                    "reprojected_to_local_camera": center_px is not None,
                    "source_camera_vehicle_name": vehicle_name,
                    "target_resource_id": target_resource_id,
                },
            )
        )
    return cues


def _terminal_decision_count(observations: list[TerminalObservation], decision_state: str) -> int:
    return sum(
        1
        for observation in observations
        if observation.terminal_association is not None
        and observation.terminal_association.decision_state == decision_state
    )


def _terminal_lock_accuracy(observations: list[TerminalObservation]) -> float:
    scored = [
        observation
        for observation in observations
        if observation.terminal_association is not None
        and observation.terminal_association.decision_state == "locked"
    ]
    if not scored:
        return 0.0
    correct = 0
    for observation in scored:
        association = observation.terminal_association
        assert association is not None
        assigned = str(observation.metadata.get("assigned_target_id", ""))
        observed = str(observation.metadata.get("observed_target_id", ""))
        if association.assigned_global_track_id == _global_id(assigned) and assigned == observed:
            correct += 1
    return correct / len(scored)


def _detections_by_camera(detections: tuple[AirSimDetectionBox, ...]) -> dict[str, tuple[AirSimDetectionBox, ...]]:
    grouped: dict[str, list[AirSimDetectionBox]] = defaultdict(list)
    for detection in detections:
        grouped[str(detection.camera_id)].append(detection)
    return {key: tuple(value) for key, value in grouped.items()}


def _local_track_from_detection(
    detection: AirSimDetectionBox,
    timestamp: float,
    *,
    center_px: np.ndarray,
    min_mot_history: int,
) -> LocalVisualTrack:
    bbox = _bbox_with_center(detection.bbox_xyxy, center_px)
    return LocalVisualTrack(
        local_track_id=detection.local_track_id,
        center_px=center_px,
        bbox=bbox,
        category=detection.classification_hint,
        quality=detection.confidence,
        mot_history_length=max(int(detection.metadata.get("mot_history_length", 1)), min_mot_history),
        timestamp=timestamp,
    )


def _bbox_with_center(
    bbox_xyxy: tuple[float, float, float, float],
    center_px: np.ndarray,
) -> tuple[float, float, float, float]:
    x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
    width = max(x2 - x1, 2.0)
    height = max(y2 - y1, 2.0)
    u, v = (float(value) for value in center_px)
    return (
        u - width * 0.5,
        v - height * 0.5,
        u + width * 0.5,
        v + height * 0.5,
    )


def _candidate_cost_margin(candidate_costs: list[tuple[str, float]]) -> float | None:
    if len(candidate_costs) < 2:
        return None
    costs = sorted(float(cost) for _candidate, cost in candidate_costs)
    return costs[1] - costs[0]


def _mean_adjacent_spacing(positions: list[np.ndarray]) -> list[float]:
    if len(positions) < 2:
        return []
    return [
        float(np.linalg.norm(positions[index + 1] - positions[index]))
        for index in range(len(positions) - 1)
    ]


def _bbox_area_px(bbox_xyxy: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = (float(value) for value in bbox_xyxy)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _numeric_stats(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "sum": 0.0,
        }
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "sum": float(np.sum(array)),
    }


def _global_id(target_id: str) -> str:
    return f"G-{target_id}"


def _normalize_case_name(case_name: str) -> str:
    if case_name not in D4D5_STRESS_CASES:
        raise ValueError(f"unsupported D4/D5 stress case: {case_name}")
    return case_name


def _terminal_observation_payload(observation: TerminalObservation) -> dict[str, Any]:
    return _jsonable(observation)


def _write_jsonl(path: Path, payloads) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for payload in payloads:
            stream.write(json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_case_report(path: Path, metrics: dict[str, Any], decisions: list[dict[str, Any]]) -> Path:
    bbox_stats = metrics.get("secondary_bbox_area_px_stats", {})
    reject_counts = metrics.get("secondary_detect_to_cross_view_reject_reason_counts", {})
    top_reject = _top_rejection_reason(reject_counts) or "-"
    lines = [
        f"# D4/D5 5v5 Stress Case - {metrics.get('case_name')}",
        "",
        "## 几何与检测",
        "",
        f"- 平均目标间距：{metrics.get('geometry', {}).get('target_spacing_m', 0.0):.2f} m",
        f"- 平均主镜头间距：{metrics.get('geometry', {}).get('resource_camera_spacing_m', 0.0):.2f} m",
        f"- 平均初始目标距离：{metrics.get('geometry', {}).get('assigned_target_distance_m', 0.0):.2f} m",
        f"- 二级镜头相对目标高度：{metrics.get('geometry', {}).get('secondary_height_above_targets_m', 0.0):.2f} m",
        f"- 二级侦察模式：{metrics.get('secondary_recon_mode', 'fixed_downlook_secondary')}",
        f"- 二级 cue 源：{metrics.get('secondary_cue_sources', [])}",
        f"- 二级云台指向成功率：{metrics.get('secondary_gimbal_pointing_ok_rate', 0.0):.2f}",
        f"- 二级 cue 指向误差统计：{metrics.get('secondary_cue_pointing_error_m_stats', {})}",
        f"- 多目标视场率：{metrics.get('multi_target_fov_rate', 0.0):.2f}",
        f"- 单二级全局视野率 `secondary_single_camera_full_view_frame_rate`：{metrics.get('secondary_single_camera_full_view_frame_rate', 0.0):.2f}",
        f"- 二级网络联合覆盖率 `secondary_network_joint_full_view_frame_rate`：{metrics.get('secondary_network_joint_full_view_frame_rate', 0.0):.2f}",
        f"- 二级网络平均覆盖比例 `secondary_network_mean_coverage_ratio`：{metrics.get('secondary_network_mean_coverage_ratio', 0.0):.2f}",
        f"- 二级 bbox 面积统计 `secondary_bbox_area_px_stats`：count={bbox_stats.get('count', 0)}, min={bbox_stats.get('min', 0.0):.2f}, mean={bbox_stats.get('mean', 0.0):.2f}, median={bbox_stats.get('median', 0.0):.2f}, max={bbox_stats.get('max', 0.0):.2f}",
        "",
        "## 指标合同",
        "",
        f"- `secondary_height_above_targets_m`: {metrics.get('secondary_height_above_targets_m', 0.0):.2f}",
        f"- `secondary_bbox_area_px_stats`: {bbox_stats}",
        f"- `secondary_single_camera_full_view_frame_rate`: {metrics.get('secondary_single_camera_full_view_frame_rate', 0.0):.2f}",
        f"- `secondary_network_joint_full_view_frame_rate`: {metrics.get('secondary_network_joint_full_view_frame_rate', 0.0):.2f}",
        f"- 兼容 alias `secondary_global_view_rate`: {metrics.get('secondary_global_view_rate', 0.0):.2f}",
        f"- 兼容 alias `secondary_network_global_view_rate`: {metrics.get('secondary_network_global_view_rate', 0.0):.2f}",
        f"- `secondary_network_mean_coverage_ratio`: {metrics.get('secondary_network_mean_coverage_ratio', 0.0):.2f}",
        f"- `secondary_recon_mode`: {metrics.get('secondary_recon_mode', 'fixed_downlook_secondary')}",
        f"- `secondary_gimbal_pointing_ok_rate`: {metrics.get('secondary_gimbal_pointing_ok_rate', 0.0):.2f}",
        f"- `secondary_cue_pointing_error_m_stats`: {metrics.get('secondary_cue_pointing_error_m_stats', {})}",
        f"- `secondary_capability_classes`: {metrics.get('secondary_capability_classes', [])}",
        f"- `secondary_cue_sources`: {metrics.get('secondary_cue_sources', [])}",
        f"- `cross_view_association_count`: {metrics.get('cross_view_association_count', 0)}",
        f"- `cross_view_conversion_gap`: {metrics.get('cross_view_conversion_gap', 0.0):.2f}",
        f"- `secondary_detect_to_cross_view_reject_reason_counts`: {reject_counts}",
        f"- 主要断点：{top_reject}",
        f"- `duplicate_terminal_lock_risk`: {metrics.get('duplicate_terminal_lock_risk', False)}",
        "",
        "## D4 仲裁",
        "",
        f"- 主动作：{metrics.get('dominant_d4_action', '')}",
        f"- 主模式：{metrics.get('dominant_degradation_mode', '')}",
        f"- 选中二级节点：{metrics.get('selected_secondary_node_id') or '-'}",
        f"- 决策数量：{metrics.get('d4_decision_count', 0)}",
        f"- 二级 detect 可见但未完成配准次数：{metrics.get('secondary_detect_available_but_not_registered_count', 0)}",
        "",
        "## 末端关联",
        "",
        f"- 终端观测数量：{metrics.get('terminal_observation_count', 0)}",
        f"- 跨视角关联数量 `cross_view_association_count`：{metrics.get('cross_view_association_count', 0)}",
        f"- 终端锁定准确率：{metrics.get('terminal_lock_accuracy', 0.0):.2f}",
        f"- 歧义/保持事件：{metrics.get('ambiguous_fov_event_count', 0)}",
        f"- 重复锁定风险 `duplicate_terminal_lock_risk`：{metrics.get('duplicate_terminal_lock_risk', False)}",
        "",
        "## 决策样例",
        "",
    ]
    for decision in decisions[:8]:
        lines.append(
            f"- t={decision.get('timestamp')}: {decision.get('resource_id')} -> "
            f"{decision.get('d4_action')} ({decision.get('reason')})"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _top_rejection_reason(rejection_counts: Any) -> str:
    if not isinstance(rejection_counts, dict):
        return ""
    ranked = sorted(
        (
            (str(reason), int(count))
            for reason, count in rejection_counts.items()
            if int(count) > 0 and str(reason) != "registered_to_global_track"
        ),
        key=lambda item: (-item[1], item[0]),
    )
    if not ranked:
        return ""
    reason, count = ranked[0]
    return f"{reason}:{count}"


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
