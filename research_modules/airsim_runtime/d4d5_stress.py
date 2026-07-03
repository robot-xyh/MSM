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
from d5_terminal_association import (
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociation,
    TerminalObservation,
    TerminalObservationBus,
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
) -> D4D5StressAnalysisResult:
    """Generate D5 terminal evidence and D4 degradation decisions from frames."""

    normalized_case = _normalize_case_name(case_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    bus = TerminalObservationBus()
    observations: list[TerminalObservation] = []
    decisions: list[dict[str, Any]] = []
    arbiter = ActiveDegradationArbiter()
    first_frame = frames[0] if frames else None
    geometry = _geometry_summary(first_frame, resource_vehicle_names, secondary_camera_vehicle_names)

    for frame in frames:
        frame_observations = _terminal_observations_for_frame(
            frame,
            case_name=normalized_case,
            resource_vehicle_names=resource_vehicle_names,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
        )
        for observation in frame_observations:
            observations.append(bus.publish(observation))
        decisions.extend(
            _d4_decisions_for_frame(
                frame,
                frame_observations,
                arbiter,
                case_name=normalized_case,
                secondary_camera_vehicle_names=secondary_camera_vehicle_names,
            )
        )

    cross_view = bus.cross_view_associations()
    detection_metrics = _detection_metrics(
        frames,
        resource_vehicle_names=resource_vehicle_names,
        secondary_camera_vehicle_names=secondary_camera_vehicle_names,
    )
    d4_metrics = _d4_metrics(decisions)
    metrics: dict[str, Any] = {
        "case_name": normalized_case,
        "geometry": geometry,
        **detection_metrics,
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
    }

    observation_path = _write_jsonl(
        output_dir / "d5_terminal_observations.jsonl",
        (_terminal_observation_payload(item) for item in observations),
    )
    cross_view_path = _write_json(
        output_dir / "d5_cross_view_associations.json",
        [_jsonable(item) for item in cross_view],
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
            "| Case | D4主动作 | 模式 | 二级节点 | 多目标视场率 | 单二级全局视野 | 二级组全局视野 | 终端准确率 | 歧义事件 |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for metrics in case_metrics:
        lines.append(
            "| {case} | {action} | {mode} | {secondary} | {fov:.2f} | {recon:.2f} | {network:.2f} | {acc:.2f} | {ambiguous} |".format(
                case=metrics.get("case_name", ""),
                action=metrics.get("dominant_d4_action", ""),
                mode=metrics.get("dominant_degradation_mode", ""),
                secondary=metrics.get("selected_secondary_node_id") or "-",
                fov=float(metrics.get("multi_target_fov_rate", 0.0)),
                recon=float(metrics.get("secondary_global_view_rate", 0.0)),
                network=float(metrics.get("secondary_network_global_view_rate", 0.0)),
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
            "- `degrade_to_secondary` 用于验证终端证据持续不一致时，二级系留侦察节点优先于完全分散协商。",
            "- `degrade_to_distributed` 用于验证二级节点不可用或链路过期时，D4 才进入完全无中心的分散模式。",
            "- D5 全程只汇报观测、身份和跨视角风险，不创建或改写 `global_track_id`。",
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
) -> list[TerminalObservation]:
    detections_by_camera = _detections_by_camera(frame.visual_detections)
    observations: list[TerminalObservation] = []
    for index, vehicle_name in enumerate(resource_vehicle_names):
        resource_id = f"INT-{index + 1:02d}"
        assigned_target_id = f"TGT-{index + 1:03d}"
        observed_target_id = assigned_target_id
        decision_state = "locked"
        confidence = 0.93
        ambiguity = 0.08
        reason = "assignment_matches_terminal_evidence"
        mismatch_frames = 0
        non_locked_frames = 0
        if case_name in {"degrade_to_secondary", "degrade_to_distributed"}:
            observed_target_id = f"TGT-{(index + 1) % 5 + 1:03d}"
            decision_state = "hold"
            confidence = 0.42
            ambiguity = 0.82
            reason = "observed_global_track_differs_from_assignment"
            mismatch_frames = 3
            non_locked_frames = 3
        detection = _select_detection(detections_by_camera.get(f"{vehicle_name}:0", ()), observed_target_id)
        local_track = _local_track_from_detection(detection, frame.timestamp) if detection else None
        association = TerminalAssociation(
            assigned_global_track_id=_global_id(assigned_target_id),
            local_track_id=None if local_track is None else local_track.local_track_id,
            association_confidence=confidence,
            ambiguity_score=ambiguity,
            friend_conflict_state="none",
            decision_state=decision_state,
            assignment_version=1,
            reason=reason,
            candidate_costs=[(_global_id(observed_target_id), 0.1 if confidence > 0.8 else 0.8)],
            recon_cue_used=case_name == "degrade_to_secondary",
        )
        recon_cues = _recon_cues(
            frame,
            assigned_target_id=assigned_target_id,
            secondary_camera_vehicle_names=secondary_camera_vehicle_names,
            enabled=case_name != "degrade_to_distributed",
        )
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
                },
            )
        )
    return observations


def _d4_decisions_for_frame(
    frame: AirSimFrame,
    observations: list[TerminalObservation],
    arbiter: ActiveDegradationArbiter,
    *,
    case_name: str,
    secondary_camera_vehicle_names: tuple[str, ...],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    secondary_nodes = _secondary_nodes(case_name, secondary_camera_vehicle_names)
    communications = _communication_summaries(case_name, secondary_nodes, frame.timestamp)
    for observation in observations:
        association = observation.terminal_association
        if association is None:
            continue
        assigned_target_id = str(observation.metadata.get("assigned_target_id", "TGT-001"))
        observed_target_id = str(observation.metadata.get("observed_target_id", assigned_target_id))
        track_uncertainty = TrackUncertaintySummary(
            track_id=_global_id(assigned_target_id),
            coverage_cell="cell-north" if assigned_target_id <= "TGT-003" else "cell-south",
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
        c2_health = C2Health.NORMAL
        decision = arbiter.evaluate(
            track_uncertainty,
            association_risk,
            assignment_validity,
            terminal_summary,
            c2_health,
            secondary_nodes,
            communication_summaries=communications,
            current_time_s=frame.timestamp,
        )
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
    for frame in frames:
        by_camera = _detections_by_camera(frame.visual_detections)
        secondary_frame_objects: set[str] = set()
        for camera_id, detections in by_camera.items():
            per_camera_max[camera_id] = max(per_camera_max[camera_id], len(detections))
            for detection in detections:
                raw_overlap[str(detection.object_id)].add(camera_id)
                if camera_id in {f"{name}:0" for name in secondary_camera_vehicle_names}:
                    secondary_frame_objects.add(str(detection.object_id))
        if len(secondary_frame_objects) >= 5:
            secondary_network_global_frame_count += 1
    primary_camera_ids = tuple(f"{name}:0" for name in resource_vehicle_names)
    secondary_camera_ids = tuple(f"{name}:0" for name in secondary_camera_vehicle_names)
    primary_multi = sum(1 for camera_id in primary_camera_ids if per_camera_max[camera_id] >= 2)
    secondary_global = sum(1 for camera_id in secondary_camera_ids if per_camera_max[camera_id] >= 5)
    return {
        "per_camera_detection_count": dict(sorted(per_camera_max.items())),
        "multi_target_fov_rate": primary_multi / max(len(primary_camera_ids), 1),
        "secondary_global_view_rate": secondary_global / max(len(secondary_camera_ids), 1),
        "secondary_network_global_view_rate": secondary_network_global_frame_count / max(len(frames), 1),
        "cross_view_overlap_count": sum(1 for cameras in raw_overlap.values() if len(cameras) > 1),
        "raw_detection_count": sum(sum(1 for _ in frame.visual_detections) for frame in frames),
    }


def _d4_metrics(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    action_counts = Counter(str(item.get("d4_action", "")) for item in decisions)
    mode_counts = Counter(str(item.get("degradation_mode", "")) for item in decisions)
    selected_secondary = next(
        (item.get("target_node_id") for item in decisions if item.get("target_node_id")),
        None,
    )
    return {
        "d4_decision_count": len(decisions),
        "d4_action_counts": dict(action_counts),
        "degradation_mode_counts": dict(mode_counts),
        "dominant_d4_action": action_counts.most_common(1)[0][0] if action_counts else "",
        "dominant_degradation_mode": mode_counts.most_common(1)[0][0] if mode_counts else "",
        "selected_secondary_node_id": selected_secondary,
    }


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


def _secondary_nodes(case_name: str, secondary_camera_vehicle_names: tuple[str, ...]) -> list[ResourceSummary]:
    if case_name == "degrade_to_distributed":
        return []
    return [
        ResourceSummary(
            node_id=f"SEC-{index + 1:02d}",
            capability_class="tethered_recon_high_res",
            availability_band=AvailabilityBand.HIGH,
            comm_band=CommBand.GOOD,
            takeover_priority=index + 1,
            node_role=NodeRole.SECONDARY_RECON,
            coordinator_only=True,
            coverage_cell="cell-north" if index == 0 else "cell-south",
            epoch=1,
        )
        for index, _ in enumerate(secondary_camera_vehicle_names)
    ]


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
) -> list[ReconImageCue]:
    if not enabled:
        return []
    cues: list[ReconImageCue] = []
    for index, vehicle_name in enumerate(secondary_camera_vehicle_names):
        cues.append(
            ReconImageCue(
                cue_id=f"{frame.episode_id}:{frame.frame_index:04d}:{vehicle_name}:{assigned_target_id}",
                producer_node_id=f"SEC-{index + 1:02d}",
                timestamp=frame.timestamp,
                image_frame_id=f"{vehicle_name}:0:{frame.frame_index:04d}",
                global_track_id=_global_id(assigned_target_id),
                confidence=0.9,
                scoped_resource_ids=(f"INT-{index + 1:02d}", f"INT-{index + 2:02d}"),
                metadata={"source": "secondary_recon_global_view"},
            )
        )
    return cues


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


def _select_detection(
    detections: tuple[AirSimDetectionBox, ...],
    target_id: str,
) -> AirSimDetectionBox | None:
    for detection in detections:
        if str(detection.object_id) == target_id:
            return detection
    return detections[0] if detections else None


def _local_track_from_detection(detection: AirSimDetectionBox, timestamp: float) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=detection.local_track_id,
        center_px=np.asarray(detection.center_px, dtype=float),
        bbox=detection.bbox_xyxy,
        category=detection.classification_hint,
        quality=detection.confidence,
        mot_history_length=int(detection.metadata.get("mot_history_length", 1)),
        timestamp=timestamp,
    )


def _mean_adjacent_spacing(positions: list[np.ndarray]) -> list[float]:
    if len(positions) < 2:
        return []
    return [
        float(np.linalg.norm(positions[index + 1] - positions[index]))
        for index in range(len(positions) - 1)
    ]


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
    lines = [
        f"# D4/D5 5v5 Stress Case - {metrics.get('case_name')}",
        "",
        "## 几何与检测",
        "",
        f"- 平均目标间距：{metrics.get('geometry', {}).get('target_spacing_m', 0.0):.2f} m",
        f"- 平均主镜头间距：{metrics.get('geometry', {}).get('resource_camera_spacing_m', 0.0):.2f} m",
        f"- 平均初始目标距离：{metrics.get('geometry', {}).get('assigned_target_distance_m', 0.0):.2f} m",
        f"- 二级镜头相对目标高度：{metrics.get('geometry', {}).get('secondary_height_above_targets_m', 0.0):.2f} m",
        f"- 多目标视场率：{metrics.get('multi_target_fov_rate', 0.0):.2f}",
        f"- 二级全局视野率：{metrics.get('secondary_global_view_rate', 0.0):.2f}",
        "",
        "## D4 仲裁",
        "",
        f"- 主动作：{metrics.get('dominant_d4_action', '')}",
        f"- 主模式：{metrics.get('dominant_degradation_mode', '')}",
        f"- 选中二级节点：{metrics.get('selected_secondary_node_id') or '-'}",
        f"- 决策数量：{metrics.get('d4_decision_count', 0)}",
        "",
        "## 末端关联",
        "",
        f"- 终端观测数量：{metrics.get('terminal_observation_count', 0)}",
        f"- 终端锁定准确率：{metrics.get('terminal_lock_accuracy', 0.0):.2f}",
        f"- 歧义/保持事件：{metrics.get('ambiguous_fov_event_count', 0)}",
        f"- 重复锁定风险：{metrics.get('duplicate_terminal_lock_risk', False)}",
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
