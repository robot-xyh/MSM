"""Probability-cell construction and deterministic rolling assignment."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from center_terminal_cv_campaign.common.contracts import SourceCueRecord

from .models import (
    AssignmentUtility,
    CameraSearchCommand,
    ProbabilityRegion,
    SearchAssignment,
    SearchCell,
    SearchExperimentConfig,
    SearchResourceState,
)


def _predicted_position(cue: SourceCueRecord, timestamp: float) -> tuple[float, float, float]:
    elapsed = max(0.0, float(timestamp) - float(cue.measurement_timestamp))
    return tuple(
        float(cue.position_ned_m[index] + cue.velocity_ned_mps[index] * elapsed)
        for index in range(3)
    )


def _sigma_extent(cue: SourceCueRecord) -> tuple[float, float, float]:
    return tuple(
        max(30.0, 3.0 * math.sqrt(max(0.0, float(cue.covariance_6x6[index][index]))))
        for index in range(3)
    )


def build_probability_regions_and_cells(
    cues: Sequence[SourceCueRecord],
    config: SearchExperimentConfig,
    *,
    timestamp: float = 0.0,
) -> tuple[tuple[ProbabilityRegion, ...], tuple[SearchCell, ...]]:
    """Create source-directed cells plus corridor cells without source bindings."""

    regions: list[ProbabilityRegion] = []
    cells: list[SearchCell] = []
    for index, cue in enumerate(cues, start=1):
        center = _predicted_position(cue, timestamp)
        extent = _sigma_extent(cue)
        region = ProbabilityRegion(
            region_id=f"REG-SRC-{index:03d}",
            center_ned_m=center,
            half_extent_ned_m=extent,
            probability=float(cue.existence_probability),
            region_kind="source_directed",
            source_track_ids=(cue.source_track_id,),
            valid_until=float(cue.valid_until),
        )
        regions.append(region)
        cells.append(
            SearchCell(
                search_cell_id=f"CELL-SRC-{index:03d}",
                region_id=region.region_id,
                center_ned_m=center,
                look_at_ned_m=center,
                half_extent_ned_m=extent,
                target_probability=region.probability,
                cell_kind="source_directed",
                candidate_source_track_ids=region.source_track_ids,
                valid_until=region.valid_until,
            )
        )

    gap_count = config.gap_cell_count or max(5, int(math.ceil(config.target_count * 0.4)))
    x_min, x_max = config.corridor_x_bounds_m
    y_min, y_max = config.corridor_y_bounds_m
    z_min, z_max = config.corridor_z_bounds_m
    y_count = max(1, int(math.ceil(math.sqrt(gap_count * (y_max - y_min) / (x_max - x_min)))))
    x_count = max(1, int(math.ceil(gap_count / y_count)))
    x_step = (x_max - x_min) / x_count
    y_step = (y_max - y_min) / y_count
    generated = 0
    for x_index in range(x_count):
        for y_index in range(y_count):
            if generated >= gap_count:
                break
            generated += 1
            z_fraction = ((generated - 1) % 3 + 0.5) / 3.0
            center = (
                float(x_min + (x_index + 0.5) * x_step),
                float(y_min + (y_index + 0.5) * y_step),
                float(z_min + z_fraction * (z_max - z_min)),
            )
            probability = max(0.2, 1.0 - 0.8) + 0.12
            region = ProbabilityRegion(
                region_id=f"REG-GAP-{generated:03d}",
                center_ned_m=center,
                half_extent_ned_m=(x_step * 0.5, y_step * 0.5, (z_max - z_min) * 0.5),
                probability=probability,
                region_kind="unbound_gap",
            )
            regions.append(region)
            cells.append(
                SearchCell(
                    search_cell_id=f"CELL-GAP-{generated:03d}",
                    region_id=region.region_id,
                    center_ned_m=center,
                    look_at_ned_m=center,
                    half_extent_ned_m=region.half_extent_ned_m,
                    target_probability=region.probability,
                    cell_kind="unbound_gap",
                )
            )
    return tuple(regions), tuple(cells)


def initial_resource_states(count: int) -> tuple[SearchResourceState, ...]:
    if count <= 0:
        raise ValueError("count must be positive")
    return tuple(
        SearchResourceState(
            camera_id=f"Terminal_CV_{index + 1:02d}",
            position_ned_m=(0.0, 0.0, 0.0),
        )
        for index in range(count)
    )


def _wrap_angle_deg(value: float) -> float:
    return (float(value) + 180.0) % 360.0 - 180.0


def look_angles_deg(origin: Sequence[float], target: Sequence[float]) -> tuple[float, float]:
    delta = np.asarray(target, dtype=float) - np.asarray(origin, dtype=float)
    horizontal = float(np.hypot(delta[0], delta[1]))
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    pitch = math.degrees(math.atan2(float(delta[2]), max(horizontal, 1e-9)))
    return yaw, pitch


@dataclass
class _CoverageState:
    count: int = 0
    last_timestamp: float | None = None


class RollingSearchPlanner:
    """Hungarian resource-to-cell assignment with auditable utility terms."""

    def __init__(
        self,
        config: SearchExperimentConfig,
        resources: Sequence[SearchResourceState],
    ) -> None:
        self.config = config
        self.resources = {resource.camera_id: resource for resource in resources}
        self._coverage: dict[str, _CoverageState] = {}
        self._plan_version = 0
        self.compute_durations_s: list[float] = []

    def _observation_position(self, cell: SearchCell) -> tuple[float, float, float]:
        center = np.asarray(cell.center_ned_m, dtype=float)
        horizontal = center[:2]
        norm = float(np.linalg.norm(horizontal))
        direction = horizontal / norm if norm > 1e-9 else np.asarray((1.0, 0.0))
        position = center.copy()
        position[:2] -= direction * self.config.observation_standoff_m
        return tuple(float(value) for value in position)

    def utility(
        self,
        resource: SearchResourceState,
        cell: SearchCell,
        timestamp: float,
    ) -> AssignmentUtility:
        desired_position = self._observation_position(cell)
        desired_yaw, desired_pitch = look_angles_deg(desired_position, cell.look_at_ned_m)
        slew_delta = math.hypot(
            _wrap_angle_deg(desired_yaw - resource.yaw_deg) / 180.0,
            (desired_pitch - resource.pitch_deg) / 90.0,
        )
        slew_cost = min(1.5, slew_delta)
        arrival_distance = float(
            np.linalg.norm(np.asarray(desired_position) - np.asarray(resource.position_ned_m))
        )
        arrival_cost = min(1.5, arrival_distance / 3000.0)
        coverage = self._coverage.get(cell.search_cell_id, _CoverageState())
        if coverage.last_timestamp is None:
            repeated_cost = 0.0
        else:
            elapsed = max(0.0, timestamp - coverage.last_timestamp)
            repeated_cost = coverage.count / (1.0 + elapsed / 2.0)
        horizontal_footprint = 2.0 * self.config.observation_standoff_m * math.tan(
            math.radians(self.config.horizontal_fov_deg) * 0.5
        )
        region_width = max(1.0, 2.0 * cell.half_extent_ned_m[1])
        visibility = max(0.2, min(1.0, horizontal_footprint / region_width))
        novelty = 1.0 / (1.0 + coverage.count)
        expected_gain = cell.target_probability * visibility * novelty
        total = (
            3.0 * cell.target_probability
            + 4.0 * expected_gain
            - 0.8 * slew_cost
            - 1.0 * arrival_cost
            - 4.0 * repeated_cost
        )
        return AssignmentUtility(
            target_probability=float(cell.target_probability),
            expected_detection_gain=float(expected_gain),
            slew_cost=float(slew_cost),
            arrival_cost=float(arrival_cost),
            repeated_coverage_cost=float(repeated_cost),
            total_utility=float(total),
        )

    def plan(
        self,
        cells: Sequence[SearchCell],
        *,
        timestamp: float,
    ) -> tuple[SearchAssignment, ...]:
        started = time.perf_counter()
        self._plan_version += 1
        resources = [state for state in self.resources.values() if state.available]
        active_cells = [
            cell for cell in cells if cell.valid_until is None or timestamp <= cell.valid_until
        ]
        if not resources:
            return ()
        utility_matrix = np.zeros((len(resources), len(active_cells) + len(resources)), dtype=float)
        utility_records: dict[tuple[int, int], AssignmentUtility] = {}
        for row, resource in enumerate(resources):
            for column, cell in enumerate(active_cells):
                record = self.utility(resource, cell, timestamp)
                utility_records[(row, column)] = record
                utility_matrix[row, column] = record.total_utility
            utility_matrix[row, len(active_cells) :] = -0.05
        rows, columns = linear_sum_assignment(-utility_matrix)
        assignments: list[SearchAssignment] = []
        idle_utility = AssignmentUtility(0.0, 0.0, 0.0, 0.0, 0.0, -0.05)
        for row, column in zip(rows, columns, strict=True):
            resource = resources[int(row)]
            if int(column) < len(active_cells) and utility_matrix[row, column] > -0.05:
                cell = active_cells[int(column)]
                assignments.append(
                    SearchAssignment(
                        plan_version=self._plan_version,
                        assignment_timestamp=float(timestamp),
                        camera_id=resource.camera_id,
                        search_cell_id=cell.search_cell_id,
                        region_id=cell.region_id,
                        utility=utility_records[(int(row), int(column))],
                        assignment_state="assigned",
                    )
                )
            else:
                assignments.append(
                    SearchAssignment(
                        plan_version=self._plan_version,
                        assignment_timestamp=float(timestamp),
                        camera_id=resource.camera_id,
                        search_cell_id=None,
                        region_id=None,
                        utility=idle_utility,
                        assignment_state="idle_no_unique_cell",
                    )
                )
        self.compute_durations_s.append(time.perf_counter() - started)
        return tuple(sorted(assignments, key=lambda item: item.camera_id))

    def command_for(self, assignment: SearchAssignment, cell: SearchCell) -> CameraSearchCommand:
        if assignment.search_cell_id != cell.search_cell_id:
            raise ValueError("assignment and cell do not match")
        position = self._observation_position(cell)
        yaw, pitch = look_angles_deg(position, cell.look_at_ned_m)
        return CameraSearchCommand(
            plan_version=assignment.plan_version,
            camera_id=assignment.camera_id,
            search_cell_id=cell.search_cell_id,
            position_ned_m=position,
            look_at_ned_m=cell.look_at_ned_m,
            yaw_deg=float(yaw),
            pitch_deg=float(pitch),
        )

    def complete_cycle(
        self,
        assignments: Sequence[SearchAssignment],
        commands: Sequence[CameraSearchCommand],
        *,
        timestamp: float,
    ) -> None:
        for assignment in assignments:
            if assignment.search_cell_id is None:
                continue
            state = self._coverage.setdefault(assignment.search_cell_id, _CoverageState())
            state.count += 1
            state.last_timestamp = float(timestamp)
        for command in commands:
            resource = self.resources[command.camera_id]
            resource.position_ned_m = command.position_ned_m
            resource.yaw_deg = command.yaw_deg
            resource.pitch_deg = command.pitch_deg

    def coverage_counts(self) -> dict[str, int]:
        return {cell_id: state.count for cell_id, state in self._coverage.items()}
