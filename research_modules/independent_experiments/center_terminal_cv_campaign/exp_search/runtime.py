"""Injectable AirSim adapter and end-to-end search experiment runner."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import math
import time
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from center_terminal_cv_campaign.common.contracts import (
    LocalVisualTrackRecord,
    SearchHandoverRecord,
    SourceCueRecord,
    SourceCueTruthLabel,
)
from center_terminal_cv_campaign.common.recognition import (
    bbox_longest_side_px,
    is_recognizable_bbox,
)
from center_terminal_cv_campaign.common.scenario import TargetTruth

from .models import (
    AnonymousBBoxDetection,
    CameraSearchCommand,
    OfflineDetectionLabel,
    ProbabilityRegion,
    SearchAssignment,
    SearchCell,
    SearchExperimentConfig,
)
from .planner import (
    RollingSearchPlanner,
    build_probability_regions_and_cells,
    initial_resource_states,
)


@dataclass(frozen=True)
class SearchExperimentResult:
    config: SearchExperimentConfig
    fixture_source: str
    regions: tuple[ProbabilityRegion, ...]
    cells: tuple[SearchCell, ...]
    assignments: tuple[SearchAssignment, ...]
    online_detections: tuple[LocalVisualTrackRecord, ...]
    handover_records: tuple[SearchHandoverRecord, ...]
    offline_detection_labels: tuple[OfflineDetectionLabel, ...]
    source_truth_labels: tuple[SourceCueTruthLabel, ...]
    targets: tuple[TargetTruth, ...]
    coverage_counts: Mapping[str, int]
    first_discovery_by_target_s: Mapping[str, float]
    offline_target_diagnostics: Mapping[str, Mapping[str, Any]]
    metrics: Mapping[str, Any]


class AirSimSearchAdapter:
    """Control/read only adapter; it never launches, resets, or closes Blocks."""

    def __init__(
        self,
        config: SearchExperimentConfig,
        *,
        client: Any | None = None,
        airsim_module: Any | None = None,
        truth_name_to_id: Mapping[str, str] | None = None,
        api_port: int = 41451,
    ) -> None:
        self.config = config
        self.client = client
        self.airsim_module = airsim_module
        self.truth_name_to_id = dict(truth_name_to_id or {})
        self.api_port = int(api_port)
        self._commands: dict[str, CameraSearchCommand] = {}
        self._observation_sequence = 0

    def connect(self) -> None:
        if self.airsim_module is None:
            import airsim as airsim_module

            self.airsim_module = airsim_module
        if self.client is None:
            self.client = self.airsim_module.VehicleClient(
                ip="127.0.0.1", port=self.api_port, timeout_value=10
            )
        ping = getattr(self.client, "ping", None)
        if callable(ping) and not ping():
            raise ConnectionError("AirSim client ping failed")

    def configure_detection_filters(self, camera_ids: Sequence[str]) -> None:
        if self.client is None or self.airsim_module is None:
            raise RuntimeError("adapter is not connected")
        image_type = self.airsim_module.ImageType.Scene
        for camera_id in camera_ids:
            self.client.simClearDetectionMeshNames(
                self.config.camera_name, image_type, vehicle_name=camera_id
            )
            self.client.simSetDetectionFilterRadius(
                self.config.camera_name,
                image_type,
                self.config.detection_filter_radius_cm,
                vehicle_name=camera_id,
            )
            for pattern in self.config.target_mesh_patterns:
                self.client.simAddDetectionFilterMeshName(
                    self.config.camera_name, image_type, pattern, vehicle_name=camera_id
                )

    def apply_command(self, command: CameraSearchCommand) -> None:
        if self.client is None or self.airsim_module is None:
            raise RuntimeError("adapter is not connected")
        pose = self.airsim_module.Pose(
            self.airsim_module.Vector3r(*command.position_ned_m),
            self.airsim_module.to_quaternion(
                math.radians(command.pitch_deg), 0.0, math.radians(command.yaw_deg)
            ),
        )
        self.client.simSetVehiclePose(pose, True, vehicle_name=command.camera_id)
        self._commands[command.camera_id] = command

    def begin_frame(self, frame_index: int, timestamp: float) -> None:
        if self.client is None:
            raise RuntimeError("adapter is not connected")
        hook = getattr(self.client, "set_search_frame", None)
        if callable(hook):
            hook(int(frame_index), float(timestamp))

    def capture(
        self,
        camera_id: str,
        *,
        frame_index: int,
        measurement_timestamp: float,
    ) -> tuple[tuple[AnonymousBBoxDetection, ...], tuple[OfflineDetectionLabel, ...]]:
        """Read detections and discard object names before returning online rows."""

        if self.client is None or self.airsim_module is None:
            raise RuntimeError("adapter is not connected")
        rpc_started = time.perf_counter()
        raw_detections = self.client.simGetDetections(
            self.config.camera_name,
            self.airsim_module.ImageType.Scene,
            vehicle_name=camera_id,
        ) or []
        arrival_timestamp = float(measurement_timestamp + (time.perf_counter() - rpc_started))
        online: list[AnonymousBBoxDetection] = []
        offline: list[OfflineDetectionLabel] = []
        for raw in raw_detections:
            bbox = _extract_bbox(raw)
            if bbox is None:
                continue
            self._observation_sequence += 1
            uid = f"OBS-{frame_index:06d}-{camera_id}-{self._observation_sequence:07d}"
            # AirSim's object name is consumed only by this offline resolver and
            # is never copied into the online observation or its metadata.
            truth_id = self.truth_name_to_id.get(str(getattr(raw, "name", "")))
            offline.append(
                OfflineDetectionLabel(
                    detection_uid=uid,
                    truth_target_id=truth_id,
                    is_false_positive=truth_id is None,
                )
            )
            extent = bbox_longest_side_px(bbox)
            online.append(
                AnonymousBBoxDetection(
                    detection_uid=uid,
                    camera_id=camera_id,
                    measurement_timestamp=float(measurement_timestamp),
                    arrival_timestamp=arrival_timestamp,
                    bbox_xyxy=bbox,
                    center_px=((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5),
                    recognition_extent_px=float(extent),
                    recognized=is_recognizable_bbox(
                        bbox, minimum_extent_px=self.config.recognition_extent_px
                    ),
                )
            )
        return tuple(online), tuple(offline)


def _extract_bbox(raw: Any) -> tuple[float, float, float, float] | None:
    box = getattr(raw, "box2D", None)
    minimum = getattr(box, "min", None)
    maximum = getattr(box, "max", None)
    if minimum is None or maximum is None:
        return None
    return (
        float(minimum.x_val),
        float(minimum.y_val),
        float(maximum.x_val),
        float(maximum.y_val),
    )


@dataclass
class _TrackState:
    local_track_id: str
    center_px: tuple[float, float]
    last_frame_index: int
    recognized_streak: int
    confirmed: bool = False


class AnonymousLocalTracker:
    """Small image-plane tracker used only to enforce two-frame confirmation."""

    def __init__(self, config: SearchExperimentConfig) -> None:
        self.config = config
        self._states: dict[tuple[str, str], list[_TrackState]] = {}
        self._sequence = 0

    def update(
        self,
        detections: Sequence[AnonymousBBoxDetection],
        *,
        command: CameraSearchCommand,
        frame_index: int,
    ) -> tuple[tuple[LocalVisualTrackRecord, bool], ...]:
        key = (command.camera_id, command.search_cell_id)
        states = self._states.setdefault(key, [])
        recent = [state for state in states if frame_index - state.last_frame_index <= 1]
        matches: dict[int, _TrackState] = {}
        if detections and recent:
            costs = np.full((len(detections), len(recent)), 1.0e6, dtype=float)
            for row, detection in enumerate(detections):
                for column, state in enumerate(recent):
                    distance = float(
                        np.linalg.norm(np.asarray(detection.center_px) - np.asarray(state.center_px))
                    )
                    if distance <= self.config.local_track_gate_px:
                        costs[row, column] = distance
            rows, columns = linear_sum_assignment(costs)
            for row, column in zip(rows, columns, strict=True):
                if costs[row, column] < 1.0e5:
                    matches[int(row)] = recent[int(column)]

        updates: list[tuple[LocalVisualTrackRecord, bool]] = []
        for index, detection in enumerate(detections):
            state = matches.get(index)
            if state is None:
                self._sequence += 1
                state = _TrackState(
                    local_track_id=f"LVT-{command.camera_id}-{self._sequence:06d}",
                    center_px=detection.center_px,
                    last_frame_index=frame_index,
                    recognized_streak=1 if detection.recognized else 0,
                )
                states.append(state)
            else:
                consecutive = state.last_frame_index == frame_index - 1
                state.recognized_streak = (
                    state.recognized_streak + 1
                    if consecutive and detection.recognized
                    else (1 if detection.recognized else 0)
                )
                state.center_px = detection.center_px
                state.last_frame_index = frame_index
            newly_confirmed = (
                not state.confirmed
                and state.recognized_streak >= self.config.confirmation_frames
            )
            if newly_confirmed:
                state.confirmed = True
            ray = _bbox_ray_ned(detection.center_px, command, self.config)
            record = LocalVisualTrackRecord(
                camera_id=detection.camera_id,
                local_track_id=state.local_track_id,
                measurement_timestamp=detection.measurement_timestamp,
                arrival_timestamp=detection.arrival_timestamp,
                bbox_xyxy=detection.bbox_xyxy,
                center_px=detection.center_px,
                ray_origin_ned_m=command.position_ned_m,
                ray_direction_ned=ray,
                camera_yaw_pitch_roll_deg=(command.yaw_deg, command.pitch_deg, 0.0),
                recognized=detection.recognized,
                recognition_extent_px=detection.recognition_extent_px,
                track_quality=min(1.0, detection.recognition_extent_px / 20.0),
                metadata={
                    "detection_uid": detection.detection_uid,
                    "search_cell_id": command.search_cell_id,
                    "frame_index": int(frame_index),
                    "plan_version": int(command.plan_version),
                    "confirmation_count": int(state.recognized_streak),
                },
            )
            updates.append((record, newly_confirmed))
        return tuple(updates)


def _bbox_ray_ned(
    center_px: Sequence[float],
    command: CameraSearchCommand,
    config: SearchExperimentConfig,
) -> tuple[float, float, float]:
    focal = config.image_width / (
        2.0 * math.tan(math.radians(config.horizontal_fov_deg) * 0.5)
    )
    camera_ray = np.asarray(
        (
            1.0,
            (float(center_px[0]) - config.image_width * 0.5) / focal,
            (float(center_px[1]) - config.image_height * 0.5) / focal,
        ),
        dtype=float,
    )
    camera_ray /= np.linalg.norm(camera_ray)
    yaw = math.radians(command.yaw_deg)
    pitch = math.radians(command.pitch_deg)
    forward = np.asarray(
        (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
    )
    right = np.asarray((-math.sin(yaw), math.cos(yaw), 0.0))
    down = np.cross(forward, right)
    world = camera_ray[0] * forward + camera_ray[1] * right + camera_ray[2] * down
    world /= np.linalg.norm(world)
    return tuple(float(value) for value in world)


class SearchExperimentRunner:
    def __init__(
        self,
        *,
        config: SearchExperimentConfig,
        source_cues: Sequence[SourceCueRecord],
        source_truth_labels: Sequence[SourceCueTruthLabel],
        targets: Sequence[TargetTruth],
        adapter: AirSimSearchAdapter,
        fixture_source: str,
        data_source: str,
        cells: Sequence[SearchCell] | None = None,
    ) -> None:
        self.config = config
        self.source_cues = tuple(source_cues)
        self.source_truth_labels = tuple(source_truth_labels)
        self.targets = tuple(targets)
        self.adapter = adapter
        self.fixture_source = fixture_source
        self.data_source = str(data_source)
        if cells is None:
            self.regions, self.cells = build_probability_regions_and_cells(
                self.source_cues, config
            )
        else:
            self.regions = ()
            self.cells = tuple(cells)

    def run(self) -> SearchExperimentResult:
        resources = initial_resource_states(self.config.resource_count)
        planner = RollingSearchPlanner(self.config, resources)
        tracker = AnonymousLocalTracker(self.config)
        cell_by_id = {cell.search_cell_id: cell for cell in self.cells}
        all_assignments: list[SearchAssignment] = []
        online_records: list[LocalVisualTrackRecord] = []
        offline_labels: list[OfflineDetectionLabel] = []
        handovers: list[SearchHandoverRecord] = []

        self.adapter.connect()
        self.adapter.configure_detection_filters(tuple(resource.camera_id for resource in resources))
        frame_index = 0
        for cycle_index in range(self.config.assignment_cycles):
            cycle_timestamp = (
                cycle_index
                * self.config.frames_per_assignment
                * self.config.frame_interval_s
            )
            assignments = planner.plan(self.cells, timestamp=cycle_timestamp)
            all_assignments.extend(assignments)
            commands: dict[str, CameraSearchCommand] = {}
            for assignment in assignments:
                if assignment.search_cell_id is None:
                    continue
                command = planner.command_for(assignment, cell_by_id[assignment.search_cell_id])
                self.adapter.apply_command(command)
                commands[assignment.camera_id] = command

            for frame_offset in range(self.config.frames_per_assignment):
                timestamp = cycle_timestamp + frame_offset * self.config.frame_interval_s
                self.adapter.begin_frame(frame_index, timestamp)
                for assignment in assignments:
                    command = commands.get(assignment.camera_id)
                    if command is None or assignment.search_cell_id is None:
                        continue
                    detections, labels = self.adapter.capture(
                        assignment.camera_id,
                        frame_index=frame_index,
                        measurement_timestamp=timestamp,
                    )
                    offline_labels.extend(labels)
                    for record, newly_confirmed in tracker.update(
                        detections, command=command, frame_index=frame_index
                    ):
                        online_records.append(record)
                        if newly_confirmed:
                            cell = cell_by_id[command.search_cell_id]
                            handovers.append(
                                SearchHandoverRecord(
                                    search_cell_id=cell.search_cell_id,
                                    camera_id=record.camera_id,
                                    local_track_id=record.local_track_id,
                                    measurement_timestamp=record.measurement_timestamp,
                                    arrival_timestamp=record.arrival_timestamp,
                                    candidate_source_track_ids=cell.candidate_source_track_ids,
                                    confirmation_count=self.config.confirmation_frames,
                                    status="confirmed_visual_target",
                                    metadata={
                                        "plan_version": command.plan_version,
                                        "source_binding_state": "candidate_only",
                                    },
                                )
                            )
                frame_index += 1
            planner.complete_cycle(
                assignments,
                tuple(commands.values()),
                timestamp=cycle_timestamp
                + (self.config.frames_per_assignment - 1) * self.config.frame_interval_s,
            )

        metrics, first_discovery, target_diagnostics = _score_result(
            config=self.config,
            targets=self.targets,
            source_labels=self.source_truth_labels,
            cells=self.cells,
            assignments=all_assignments,
            online_records=online_records,
            handovers=handovers,
            offline_labels=offline_labels,
            coverage_counts=planner.coverage_counts(),
            planner_compute_s=planner.compute_durations_s,
            data_source=self.data_source,
        )
        return SearchExperimentResult(
            config=self.config,
            fixture_source=self.fixture_source,
            regions=self.regions,
            cells=self.cells,
            assignments=tuple(all_assignments),
            online_detections=tuple(online_records),
            handover_records=tuple(handovers),
            offline_detection_labels=tuple(offline_labels),
            source_truth_labels=self.source_truth_labels,
            targets=self.targets,
            coverage_counts=planner.coverage_counts(),
            first_discovery_by_target_s=first_discovery,
            offline_target_diagnostics=target_diagnostics,
            metrics=metrics,
        )


def _score_result(
    *,
    config: SearchExperimentConfig,
    targets: Sequence[TargetTruth],
    source_labels: Sequence[SourceCueTruthLabel],
    cells: Sequence[SearchCell],
    assignments: Sequence[SearchAssignment],
    online_records: Sequence[LocalVisualTrackRecord],
    handovers: Sequence[SearchHandoverRecord],
    offline_labels: Sequence[OfflineDetectionLabel],
    coverage_counts: Mapping[str, int],
    planner_compute_s: Sequence[float],
    data_source: str,
) -> tuple[
    dict[str, Any],
    dict[str, float],
    dict[str, dict[str, Any]],
]:
    detection_truth = {label.detection_uid: label.truth_target_id for label in offline_labels}
    track_truth_votes: dict[str, Counter[str]] = {}
    for record in online_records:
        uid = str(record.metadata.get("detection_uid", ""))
        truth_id = detection_truth.get(uid)
        if truth_id is not None:
            track_truth_votes.setdefault(record.local_track_id, Counter())[truth_id] += 1
    track_truth = {
        track_id: votes.most_common(1)[0][0]
        for track_id, votes in track_truth_votes.items()
        if votes
    }
    confirmed_truth = {
        track_truth[handover.local_track_id]
        for handover in handovers
        if handover.local_track_id in track_truth
    }
    all_truth = {target.truth_target_id for target in targets}
    correct_source_truth = {
        str(label.truth_target_id)
        for label in source_labels
        if label.is_correct_source and label.truth_target_id is not None
    }
    center_missed_truth = all_truth - correct_source_truth
    recovered_missed = confirmed_truth & center_missed_truth
    source_label_map = {label.source_track_id: label for label in source_labels}
    ghost_source_ids = {
        label.source_track_id for label in source_labels if label.corruption_type == "ghost_source"
    }
    false_source_ids = {
        label.source_track_id for label in source_labels if not label.is_correct_source
    }
    ghost_visual_handover_count = sum(
        bool(set(handover.candidate_source_track_ids) & ghost_source_ids)
        for handover in handovers
    )
    false_source_handover_count = sum(
        bool(set(handover.candidate_source_track_ids) & false_source_ids)
        for handover in handovers
    )
    first_discovery: dict[str, float] = {}
    for handover in handovers:
        truth_id = track_truth.get(handover.local_track_id)
        if truth_id is not None:
            first_discovery[truth_id] = min(
                first_discovery.get(truth_id, math.inf), handover.measurement_timestamp
            )
    observations_by_truth: dict[str, list[LocalVisualTrackRecord]] = {}
    for record in online_records:
        uid = str(record.metadata.get("detection_uid", ""))
        truth_id = detection_truth.get(uid)
        if truth_id is not None:
            observations_by_truth.setdefault(truth_id, []).append(record)
    scheduled_cell_ids = {
        assignment.search_cell_id
        for assignment in assignments
        if assignment.search_cell_id is not None
    }
    target_diagnostics: dict[str, dict[str, Any]] = {}
    for target_id in sorted(all_truth):
        correct_source_ids = tuple(
            label.source_track_id
            for label in source_labels
            if label.is_correct_source and label.truth_target_id == target_id
        )
        source_cell_ids = tuple(
            cell.search_cell_id
            for cell in cells
            if set(cell.candidate_source_track_ids) & set(correct_source_ids)
        )
        observations = observations_by_truth.get(target_id, [])
        recognizable_count = sum(record.recognized for record in observations)
        confirmed_count = sum(
            track_truth.get(handover.local_track_id) == target_id for handover in handovers
        )
        if confirmed_count:
            status = "confirmed"
        elif recognizable_count:
            status = "recognized_not_consecutively_confirmed"
        elif observations:
            status = "below_recognition_threshold_only"
        else:
            status = "never_detected"
        target_diagnostics[target_id] = {
            "offline_truth_only": True,
            "status": status,
            "has_correct_source_cue": bool(correct_source_ids),
            "correct_source_track_ids": correct_source_ids,
            "source_search_cell_ids": source_cell_ids,
            "source_cells_scheduled": tuple(
                cell_id in scheduled_cell_ids for cell_id in source_cell_ids
            ),
            "observation_count": len(observations),
            "recognizable_observation_count": recognizable_count,
            "below_threshold_observation_count": len(observations) - recognizable_count,
            "observed_frame_indices": tuple(
                sorted({int(record.metadata.get("frame_index", -1)) for record in observations})
            ),
            "observed_search_cell_ids": tuple(
                sorted({str(record.metadata.get("search_cell_id", "")) for record in observations})
            ),
            "confirmed_handover_count": confirmed_count,
        }
    online_payload = [record.to_online_dict() for record in online_records]
    online_text = json.dumps(online_payload, ensure_ascii=False)
    forbidden_values = [target.actor_name for target in targets] + list(all_truth)
    leakage_count = sum(value in online_text for value in forbidden_values)
    assignment_count = sum(item.search_cell_id is not None for item in assignments)
    coverage_total = sum(coverage_counts.values())
    duplicate_coverage = sum(max(0, count - 1) for count in coverage_counts.values())
    mapped_handover_count = sum(handover.local_track_id in track_truth for handover in handovers)
    metrics: dict[str, Any] = {
        "schema_version": "center-terminal-search-metrics-v1",
        "data_source": str(data_source),
        "target_count": len(targets),
        "resource_count": config.resource_count,
        "source_cue_count": len(source_labels),
        "source_fixture_precision": (
            sum(label.is_correct_source for label in source_labels) / len(source_labels)
            if source_labels
            else 0.0
        ),
        "source_fixture_recall": (
            len(correct_source_truth) / len(targets) if targets else 0.0
        ),
        "search_cell_count": len(cells),
        "covered_cell_count": sum(coverage_counts.get(cell.search_cell_id, 0) > 0 for cell in cells),
        "cell_coverage_rate": (
            sum(coverage_counts.get(cell.search_cell_id, 0) > 0 for cell in cells) / len(cells)
            if cells
            else 0.0
        ),
        "assignment_count": assignment_count,
        "assignment_capacity": config.resource_count * config.assignment_cycles,
        "unassigned_cell_count": sum(
            cell.search_cell_id not in scheduled_cell_ids for cell in cells
        ),
        "duplicate_coverage_rate": duplicate_coverage / coverage_total if coverage_total else 0.0,
        "online_detection_count": len(online_records),
        "recognizable_detection_count": sum(record.recognized for record in online_records),
        "below_ten_pixel_detection_count": sum(not record.recognized for record in online_records),
        "confirmed_handover_count": len(handovers),
        "confirmed_handover_precision": mapped_handover_count / len(handovers) if handovers else 0.0,
        "discovered_target_count": len(confirmed_truth),
        "target_discovery_recall": len(confirmed_truth) / len(targets) if targets else 0.0,
        "detected_target_count": sum(
            diagnostic["observation_count"] > 0 for diagnostic in target_diagnostics.values()
        ),
        "recognized_target_count": sum(
            diagnostic["recognizable_observation_count"] > 0
            for diagnostic in target_diagnostics.values()
        ),
        "recognized_but_unconfirmed_target_count": sum(
            diagnostic["status"] == "recognized_not_consecutively_confirmed"
            for diagnostic in target_diagnostics.values()
        ),
        "below_threshold_only_target_count": sum(
            diagnostic["status"] == "below_recognition_threshold_only"
            for diagnostic in target_diagnostics.values()
        ),
        "never_detected_target_count": sum(
            diagnostic["status"] == "never_detected"
            for diagnostic in target_diagnostics.values()
        ),
        "scheduled_source_but_unconfirmed_target_count": sum(
            diagnostic["status"] != "confirmed"
            and diagnostic["has_correct_source_cue"]
            and any(diagnostic["source_cells_scheduled"])
            for diagnostic in target_diagnostics.values()
        ),
        "center_missed_target_count": len(center_missed_truth),
        "center_missed_recovered_count": len(recovered_missed),
        "center_missed_recovery_recall": (
            len(recovered_missed) / len(center_missed_truth) if center_missed_truth else 1.0
        ),
        "false_positive_confirmed_count": len(handovers) - mapped_handover_count,
        "false_source_handover_count": false_source_handover_count,
        # Search confirms a visual target only. Candidate source IDs are not
        # promoted to source-track bindings in this experiment.
        "ghost_source_confirmed_count": sum(
            handover.status == "source_track_confirmed"
            and bool(set(handover.candidate_source_track_ids) & ghost_source_ids)
            for handover in handovers
        ),
        "ghost_source_visual_handover_count": ghost_visual_handover_count,
        "online_truth_leakage_count": leakage_count,
        "first_discovery_mean_s": (
            float(np.mean(tuple(first_discovery.values()))) if first_discovery else None
        ),
        "planner_compute_mean_ms": (
            float(np.mean(planner_compute_s) * 1000.0) if planner_compute_s else 0.0
        ),
        "planner_compute_max_ms": (
            float(np.max(planner_compute_s) * 1000.0) if planner_compute_s else 0.0
        ),
        "acceptance": {
            "online_truth_leakage_zero": leakage_count == 0,
            "ten_pixel_gate_enabled": config.recognition_extent_px == 10.0,
            "two_frame_confirmation_enabled": config.confirmation_frames == 2,
            "confirmation_retry_margin_frames": (
                config.frames_per_assignment - config.confirmation_frames
            ),
        },
    }
    # Access the map so malformed source-label fixtures are rejected early.
    if len(source_label_map) != len(source_labels):
        raise ValueError("source truth labels contain duplicate source_track_id values")
    return metrics, first_discovery, target_diagnostics
