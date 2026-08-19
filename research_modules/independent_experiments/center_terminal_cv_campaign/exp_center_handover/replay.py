"""Read-only adapter for saved AirSim center-handover campaign artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ..common import LocalVisualTrackRecord, SourceCueRecord, SourceCueTruthLabel
from ..common.contracts import LOCAL_TRACK_SCHEMA, SOURCE_CUE_SCHEMA, TRUTH_LABEL_SCHEMA
from ..common.scenario import CampaignScenario
from .fixture import HandoverFixture, LocalTrackTruthLabel
from .geometry import CameraIntrinsics, CameraModel


REPLAY_SCHEMA = "center-terminal-gnn-replay-v1"
CALIBRATION_SCHEMA = "terminal-crossview-calibrations-v1"
CAPTURE_PLAN_SCHEMA = "terminal-crossview-airsim-capture-plan-v1"
FORBIDDEN_AIRSIM_SEED = 20260816

_REQUIRED_PATH_KEYS = (
    "scenario",
    "source_cues",
    "center_local_tracks",
    "center_source_truth",
    "center_local_truth",
    "crossview_calibrations",
    "crossview_capture_plan",
)
_FORBIDDEN_ONLINE_KEYS = (
    "truth",
    "actor",
    "raw_detection_name",
    "global_track_id",
)
_TRUTH_ID_PATTERN = re.compile(r"^TGT-[0-9]+$")


@dataclass(frozen=True)
class ReplayDescriptor:
    manifest_path: Path
    scenario_id: str
    campaign_seed: int
    target_count: int
    resource_count: int
    test_only: bool
    paths: Mapping[str, Path]
    sha256: Mapping[str, str]


def load_replay_fixture(manifest_path: Path | str) -> tuple[HandoverFixture, ReplayDescriptor]:
    """Load only the center-handover fields referenced by a unified replay manifest."""

    descriptor = load_replay_descriptor(manifest_path)
    scenario_raw = _read_json(descriptor.paths["scenario"])
    if not isinstance(scenario_raw, dict):
        raise ValueError("replay scenario must be a JSON object")
    scenario = CampaignScenario(**scenario_raw)
    if scenario.seed != descriptor.campaign_seed:
        raise ValueError("replay campaign_seed does not match scenario seed")
    if scenario.target_count != descriptor.target_count:
        raise ValueError("replay target_count does not match scenario")

    source_rows = _read_jsonl(descriptor.paths["source_cues"])
    local_rows = _read_jsonl(descriptor.paths["center_local_tracks"])
    _assert_online_rows_anonymous(source_rows, artifact="source_cues")
    _assert_online_rows_anonymous(local_rows, artifact="center_local_tracks")
    source_cues = tuple(_source_cue_from_dict(row) for row in source_rows)
    local_records = tuple(_local_track_from_dict(row) for row in local_rows)
    _validate_record_schemas(source_cues, local_records)
    frames = _group_frames(local_records)
    if len(frames) < 3:
        raise ValueError("saved replay needs at least three frames for 2-of-3 confirmation")

    camera_models = _load_camera_models(
        descriptor.paths["crossview_calibrations"],
        descriptor.paths["crossview_capture_plan"],
        local_records,
    )

    # Truth is loaded only after all online records and geometry have been validated.
    source_truth = tuple(
        _source_truth_from_dict(row)
        for row in _read_jsonl(descriptor.paths["center_source_truth"])
    )
    local_truth = tuple(
        _local_truth_from_dict(row)
        for row in _read_jsonl(descriptor.paths["center_local_truth"])
    )
    return (
        HandoverFixture(
            scenario=scenario,
            source_cues=source_cues,
            camera_models=camera_models,
            frames=frames,
            source_truth=source_truth,
            local_truth=local_truth,
            target_truth=(),
        ),
        descriptor,
    )


def load_replay_descriptor(manifest_path: Path | str) -> ReplayDescriptor:
    path = Path(manifest_path).resolve()
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("replay manifest must be a JSON object")
    if raw.get("schema_version") != REPLAY_SCHEMA:
        raise ValueError("unsupported center-handover replay schema")

    paths_raw = raw.get("paths")
    digests_raw = raw.get("sha256")
    if not isinstance(paths_raw, dict) or not isinstance(digests_raw, dict):
        raise ValueError("replay manifest requires paths and sha256 objects")

    resolved: dict[str, Path] = {}
    validated_digests: dict[str, str] = {}
    for key in _REQUIRED_PATH_KEYS:
        value = paths_raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"replay manifest is missing path: {key}")
        relative = Path(value)
        if relative.is_absolute():
            raise ValueError(f"replay path must be relative to the manifest: {key}")
        artifact = (path.parent / relative).resolve()
        if not artifact.is_file():
            raise FileNotFoundError(f"replay artifact does not exist: {artifact}")
        digest = digests_raw.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError(f"replay artifact requires a SHA256 digest: {key}")
        actual = sha256_file(artifact)
        if actual != digest.lower():
            raise ValueError(f"replay SHA256 mismatch for {key}")
        resolved[key] = artifact
        validated_digests[key] = actual

    scenario_id = str(raw.get("scenario_id", "")).strip()
    if not scenario_id:
        raise ValueError("replay scenario_id must be non-empty")
    campaign_seed = _positive_int(raw.get("campaign_seed"), "campaign_seed")
    target_count = _positive_int(raw.get("target_count"), "target_count")
    resource_count = _positive_int(raw.get("resource_count"), "resource_count")
    if not isinstance(raw.get("test_only"), bool):
        raise ValueError("replay test_only must be a boolean")
    return ReplayDescriptor(
        manifest_path=path,
        scenario_id=scenario_id,
        campaign_seed=campaign_seed,
        target_count=target_count,
        resource_count=resource_count,
        test_only=bool(raw["test_only"]),
        paths=resolved,
        sha256=validated_digests,
    )


def reject_replay_as_training_input(manifest_path: Path | str) -> None:
    """Fail closed when someone passes a held-out campaign replay to training."""

    path = Path(manifest_path).resolve()
    raw = _read_json(path)
    if not isinstance(raw, dict) or raw.get("schema_version") != REPLAY_SCHEMA:
        raise ValueError("unsupported center-handover replay schema")
    seed = _positive_int(raw.get("campaign_seed"), "campaign_seed")
    test_only = raw.get("test_only")
    if not isinstance(test_only, bool):
        raise ValueError("replay test_only must be a boolean")
    if test_only or seed == FORBIDDEN_AIRSIM_SEED:
        raise ValueError("test-only or AirSim seed 20260816 replay cannot enter training")
    raise ValueError("the synthetic training CLI does not accept replay training data")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_camera_models(
    calibration_path: Path,
    capture_plan_path: Path,
    local_records: Sequence[LocalVisualTrackRecord],
) -> dict[str, CameraModel]:
    calibrations = _read_json(calibration_path)
    capture_plan = _read_json(capture_plan_path)
    if calibrations.get("schema_version") != CALIBRATION_SCHEMA:
        raise ValueError("unsupported cross-view calibration schema")
    if capture_plan.get("schema_version") != CAPTURE_PLAN_SCHEMA:
        raise ValueError("unsupported cross-view capture-plan schema")
    calibration_rows = calibrations.get("cameras")
    frames = capture_plan.get("frames")
    if not isinstance(calibration_rows, list) or not calibration_rows:
        raise ValueError("cross-view calibrations must contain an intrinsics template")
    if not isinstance(frames, list) or not frames:
        raise ValueError("calibrations and capture plan must contain camera rows")
    for frame in frames:
        if not isinstance(frame, dict) or not isinstance(frame.get("cameras"), list):
            raise ValueError("capture-plan frame is malformed")

    profiles: set[tuple[int, int, float]] = set()
    for row in calibration_rows:
        if not isinstance(row, dict):
            raise ValueError("camera calibration row must be an object")
        profiles.add(
            (
                int(row["width_px"]),
                int(row["height_px"]),
                float(row["horizontal_fov_deg"]),
            )
        )
    if len(profiles) != 1:
        raise ValueError("cross-view calibrations do not define one common camera profile")
    width_px, height_px, horizontal_fov_deg = next(iter(profiles))

    observed_poses: dict[str, tuple[tuple[float, ...], tuple[float, ...]]] = {}
    for record in local_records:
        pose = (
            tuple(float(value) for value in record.ray_origin_ned_m),
            tuple(float(value) for value in record.camera_yaw_pitch_roll_deg),
        )
        previous = observed_poses.setdefault(record.camera_id, pose)
        if not _pose_close(previous, pose):
            raise ValueError(
                f"center camera pose changes across saved frames: {record.camera_id}"
            )
    if not observed_poses:
        raise ValueError("center replay contains no camera-local tracks")

    models: dict[str, CameraModel] = {}
    for camera_id in sorted(observed_poses):
        origin, yaw_pitch_roll = observed_poses[camera_id]
        models[camera_id] = CameraModel(
            camera_id=camera_id,
            intrinsics=CameraIntrinsics(
                width_px=width_px,
                height_px=height_px,
                horizontal_fov_deg=horizontal_fov_deg,
            ),
            body_position_ned_m=origin,  # type: ignore[arg-type]
            body_yaw_pitch_roll_deg=yaw_pitch_roll,  # type: ignore[arg-type]
            gimbal_yaw_pitch_roll_deg=(0.0, 0.0, 0.0),
            camera_offset_body_m=(0.0, 0.0, 0.0),
        )
    return models


def _pose_close(
    left: tuple[tuple[float, ...], tuple[float, ...]],
    right: tuple[tuple[float, ...], tuple[float, ...]],
) -> bool:
    return all(
        abs(a - b) <= tolerance
        for left_vector, right_vector, tolerance in (
            (left[0], right[0], 1.0e-4),
            (left[1], right[1], 1.0e-4),
        )
        for a, b in zip(left_vector, right_vector, strict=True)
    )


def _source_cue_from_dict(row: Mapping[str, Any]) -> SourceCueRecord:
    value = dict(row)
    value["position_ned_m"] = tuple(value["position_ned_m"])
    value["velocity_ned_mps"] = tuple(value["velocity_ned_mps"])
    value["covariance_6x6"] = tuple(tuple(line) for line in value["covariance_6x6"])
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


def _source_truth_from_dict(row: Mapping[str, Any]) -> SourceCueTruthLabel:
    label = SourceCueTruthLabel(**dict(row))
    if label.schema_version != TRUTH_LABEL_SCHEMA:
        raise ValueError("unsupported source truth-label schema")
    return label


def _local_truth_from_dict(row: Mapping[str, Any]) -> LocalTrackTruthLabel:
    allowed = {"camera_id", "local_track_id", "truth_target_id"}
    value = {key: item for key, item in row.items() if key in allowed}
    if set(value) != allowed:
        raise ValueError("center local truth row is malformed")
    return LocalTrackTruthLabel(**value)


def _validate_record_schemas(
    sources: Sequence[SourceCueRecord], locals_: Sequence[LocalVisualTrackRecord]
) -> None:
    if any(row.schema_version != SOURCE_CUE_SCHEMA for row in sources):
        raise ValueError("unsupported source-cue schema in replay")
    if any(row.schema_version != LOCAL_TRACK_SCHEMA for row in locals_):
        raise ValueError("unsupported local-track schema in replay")


def _assert_online_rows_anonymous(rows: Sequence[Mapping[str, Any]], *, artifact: str) -> None:
    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower()
                if any(token in normalized for token in _FORBIDDEN_ONLINE_KEYS):
                    return True
                if walk(item):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(walk(item) for item in value)
        elif isinstance(value, str):
            return bool(_TRUTH_ID_PATTERN.fullmatch(value) or "MSM_TargetActor" in value)
        return False

    if any(walk(row) for row in rows):
        raise ValueError(f"truth or actor identity leaked into online {artifact}")


def _group_frames(
    records: Sequence[LocalVisualTrackRecord],
) -> tuple[tuple[LocalVisualTrackRecord, ...], ...]:
    grouped: dict[float, list[LocalVisualTrackRecord]] = {}
    for record in records:
        grouped.setdefault(float(record.measurement_timestamp), []).append(record)
    return tuple(tuple(grouped[timestamp]) for timestamp in sorted(grouped))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object: {path}")
            rows.append(value)
    return rows


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    result = int(value)
    if result <= 0 or result != value:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _vector3(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three values")
    return tuple(float(item) for item in value)  # type: ignore[return-value]
