"""Offline fixtures for isolated center-to-terminal handover validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ..common import LocalVisualTrackRecord, SourceCueRecord, SourceCueTruthLabel
from ..common.io import write_json, write_jsonl
from ..common.scenario import (
    CampaignScenario,
    TargetTruth,
    build_source_fixture,
    generate_targets,
)
from .geometry import CameraIntrinsics, CameraModel


@dataclass(frozen=True)
class LocalTrackTruthLabel:
    camera_id: str
    local_track_id: str
    truth_target_id: str


@dataclass(frozen=True)
class HandoverFixture:
    scenario: CampaignScenario
    source_cues: tuple[SourceCueRecord, ...]
    camera_models: Mapping[str, CameraModel]
    frames: tuple[tuple[LocalVisualTrackRecord, ...], ...]
    source_truth: tuple[SourceCueTruthLabel, ...] = ()
    local_truth: tuple[LocalTrackTruthLabel, ...] = ()
    target_truth: tuple[TargetTruth, ...] = ()


def build_offline_fixture(
    *,
    target_count: int = 20,
    seed: int = 20260816,
    source_position_sigma_m: float = 1.0,
    frame_timestamps: Sequence[float] = (0.2, 0.3, 0.4),
) -> HandoverFixture:
    scenario = CampaignScenario(
        target_count=target_count,
        seed=seed,
        source_position_sigma_m=source_position_sigma_m,
    )
    targets = generate_targets(scenario)
    source_cues, source_truth = build_source_fixture(scenario, targets)
    camera_models, target_camera_ids = build_terminal_camera_models(targets)
    frames, local_truth = generate_local_visual_tracks(
        targets,
        camera_models,
        target_camera_ids,
        seed=seed,
        frame_timestamps=frame_timestamps,
    )
    return HandoverFixture(
        scenario=scenario,
        source_cues=source_cues,
        camera_models=camera_models,
        frames=frames,
        source_truth=source_truth,
        local_truth=local_truth,
        target_truth=targets,
    )


def build_terminal_camera_models(
    targets: Sequence[TargetTruth],
    *,
    targets_per_camera: int = 1,
) -> tuple[dict[str, CameraModel], dict[str, str]]:
    if not targets:
        raise ValueError("targets must be non-empty")
    ordered = sorted(targets, key=lambda item: item.start_ned_m[1])
    camera_models: dict[str, CameraModel] = {}
    target_camera_ids: dict[str, str] = {}
    for camera_index, start in enumerate(range(0, len(ordered), targets_per_camera), start=1):
        group = ordered[start : start + targets_per_camera]
        camera_id = f"Terminal_CV_{camera_index:02d}"
        start_positions = np.asarray([target.start_ned_m for target in group], dtype=float)
        camera_position = np.asarray(
            (
                float(np.min(start_positions[:, 0]) - 650.0),
                float(np.mean(start_positions[:, 1])),
                float(np.mean(start_positions[:, 2])),
            )
        )
        aim_point = np.mean(
            np.asarray([target.position_at(0.3) for target in group], dtype=float), axis=0
        )
        yaw, pitch = _look_at_yaw_pitch(camera_position, aim_point)
        camera_models[camera_id] = CameraModel(
            camera_id=camera_id,
            intrinsics=CameraIntrinsics(width_px=1920, height_px=1080, horizontal_fov_deg=19.0),
            body_position_ned_m=tuple(float(value) for value in camera_position),
            body_yaw_pitch_roll_deg=(yaw, pitch, 0.0),
            camera_offset_body_m=(0.5, 0.0, 0.0),
        )
        for target in group:
            target_camera_ids[target.truth_target_id] = camera_id
    return camera_models, target_camera_ids


def generate_local_visual_tracks(
    targets: Sequence[TargetTruth],
    camera_models: Mapping[str, CameraModel],
    target_camera_ids: Mapping[str, str],
    *,
    seed: int,
    frame_timestamps: Sequence[float],
) -> tuple[tuple[tuple[LocalVisualTrackRecord, ...], ...], tuple[LocalTrackTruthLabel, ...]]:
    rng = np.random.default_rng(seed + 104729)
    shuffled_tokens = rng.permutation(np.arange(10_000, 10_000 + len(targets)))
    local_ids = {
        target.truth_target_id: f"LCL-{int(shuffled_tokens[index]):05d}"
        for index, target in enumerate(targets)
    }
    labels = tuple(
        LocalTrackTruthLabel(
            camera_id=target_camera_ids[target.truth_target_id],
            local_track_id=local_ids[target.truth_target_id],
            truth_target_id=target.truth_target_id,
        )
        for target in targets
    )
    frames: list[tuple[LocalVisualTrackRecord, ...]] = []
    for frame_index, timestamp in enumerate(frame_timestamps):
        frame: list[LocalVisualTrackRecord] = []
        for target in targets:
            camera = camera_models[target_camera_ids[target.truth_target_id]]
            position = np.asarray(target.position_at(float(timestamp)), dtype=float)
            ideal_center = camera.project(position)
            center = ideal_center + rng.normal(0.0, 0.25, size=2)
            depth = float(camera.world_to_camera(position)[0])
            longest_extent = camera.intrinsics.focal_x_px * target.longest_dimension_m / depth
            if longest_extent < 10.0:
                raise RuntimeError("offline handover fixture violates the ten-pixel premise")
            width = longest_extent
            height = longest_extent * 0.62
            bbox = (
                float(center[0] - width / 2.0),
                float(center[1] - height / 2.0),
                float(center[0] + width / 2.0),
                float(center[1] + height / 2.0),
            )
            ray = camera.pixel_to_world_ray(tuple(float(value) for value in center))
            frame.append(
                LocalVisualTrackRecord(
                    camera_id=camera.camera_id,
                    local_track_id=local_ids[target.truth_target_id],
                    measurement_timestamp=float(timestamp),
                    arrival_timestamp=float(timestamp) + 0.02,
                    bbox_xyxy=bbox,
                    center_px=tuple(float(value) for value in center),
                    ray_origin_ned_m=tuple(float(value) for value in camera.camera_position_ned_m),
                    ray_direction_ned=tuple(float(value) for value in ray),
                    camera_yaw_pitch_roll_deg=_combined_camera_ypr(camera),
                    recognized=True,
                    recognition_extent_px=float(longest_extent),
                    track_quality=0.95,
                    metadata={
                        "frame_index": frame_index,
                        "center_covariance_px2": ((0.25**2, 0.0), (0.0, 0.25**2)),
                        "detection_source": "offline_fixture",
                    },
                )
            )
        frames.append(tuple(frame))
    return tuple(frames), labels


def write_handover_fixture(path: Path, fixture: HandoverFixture) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / "scenario.json", asdict(fixture.scenario))
    write_jsonl(path / "online" / "source_cues.jsonl", fixture.source_cues)
    write_jsonl(
        path / "online" / "local_tracks.jsonl",
        (record for frame in fixture.frames for record in frame),
    )
    write_json(
        path / "camera_models.json",
        {camera_id: model.to_dict() for camera_id, model in fixture.camera_models.items()},
    )
    if fixture.source_truth:
        write_jsonl(path / "truth" / "source_cue_labels.jsonl", fixture.source_truth)
    if fixture.local_truth:
        write_jsonl(path / "truth" / "local_track_labels.jsonl", fixture.local_truth)
    if fixture.target_truth:
        write_jsonl(path / "truth" / "targets.jsonl", fixture.target_truth)
    return path


def load_handover_fixture(path: Path) -> HandoverFixture:
    scenario = CampaignScenario(**_read_json(path / "scenario.json"))
    source_cues = tuple(
        _source_cue_from_dict(row) for row in _read_jsonl(path / "online" / "source_cues.jsonl")
    )
    source_truth_path = path / "truth" / "source_cue_labels.jsonl"
    target_truth_path = path / "truth" / "targets.jsonl"
    local_truth_path = path / "truth" / "local_track_labels.jsonl"
    source_truth = tuple(
        SourceCueTruthLabel(**row) for row in _read_jsonl(source_truth_path)
    ) if source_truth_path.exists() else ()
    target_truth = tuple(TargetTruth(**row) for row in _read_jsonl(target_truth_path)) if target_truth_path.exists() else ()

    camera_path = path / "camera_models.json"
    local_path = path / "online" / "local_tracks.jsonl"
    if camera_path.exists() and local_path.exists():
        camera_models = {
            key: CameraModel.from_dict(value) for key, value in _read_json(camera_path).items()
        }
        records = tuple(_local_track_from_dict(row) for row in _read_jsonl(local_path))
        frames = _group_frames(records)
        local_truth = tuple(LocalTrackTruthLabel(**row) for row in _read_jsonl(local_truth_path)) if local_truth_path.exists() else ()
    elif target_truth:
        camera_models, target_camera_ids = build_terminal_camera_models(target_truth)
        frames, local_truth = generate_local_visual_tracks(
            target_truth,
            camera_models,
            target_camera_ids,
            seed=scenario.seed,
            frame_timestamps=(0.2, 0.3, 0.4),
        )
    else:
        raise FileNotFoundError(
            "fixture needs camera_models/local_tracks or offline target truth to generate them"
        )
    return HandoverFixture(
        scenario=scenario,
        source_cues=source_cues,
        camera_models=camera_models,
        frames=frames,
        source_truth=source_truth,
        local_truth=local_truth,
        target_truth=target_truth,
    )


def _group_frames(records: Sequence[LocalVisualTrackRecord]) -> tuple[tuple[LocalVisualTrackRecord, ...], ...]:
    grouped: dict[float, list[LocalVisualTrackRecord]] = {}
    for record in records:
        grouped.setdefault(float(record.measurement_timestamp), []).append(record)
    return tuple(tuple(grouped[timestamp]) for timestamp in sorted(grouped))


def _source_cue_from_dict(row: Mapping[str, Any]) -> SourceCueRecord:
    value = dict(row)
    value["position_ned_m"] = tuple(value["position_ned_m"])
    value["velocity_ned_mps"] = tuple(value["velocity_ned_mps"])
    value["covariance_6x6"] = tuple(tuple(item for item in line) for line in value["covariance_6x6"])
    return SourceCueRecord(**value)


def _local_track_from_dict(row: Mapping[str, Any]) -> LocalVisualTrackRecord:
    value = dict(row)
    for key in (
        "bbox_xyxy",
        "center_px",
        "ray_origin_ned_m",
        "ray_direction_ned",
        "camera_yaw_pitch_roll_deg",
    ):
        value[key] = tuple(value[key])
    return LocalVisualTrackRecord(**value)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _look_at_yaw_pitch(origin: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    delta = np.asarray(target, dtype=float) - np.asarray(origin, dtype=float)
    horizontal = math.hypot(float(delta[0]), float(delta[1]))
    yaw = math.degrees(math.atan2(float(delta[1]), float(delta[0])))
    pitch = -math.degrees(math.atan2(float(delta[2]), horizontal))
    return yaw, pitch


def _combined_camera_ypr(camera: CameraModel) -> tuple[float, float, float]:
    body = camera.body_yaw_pitch_roll_deg
    gimbal = camera.gimbal_yaw_pitch_roll_deg
    return tuple(float(body[index] + gimbal[index]) for index in range(3))
