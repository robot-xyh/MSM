"""Fixture and replay persistence with online/offline directory separation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..common.contracts import LocalVisualTrackRecord
from ..common.io import write_json, write_jsonl
from .config import CameraCalibration
from .contracts import OfflineTruthLabels, assert_online_anonymous
from .fixture import FixtureBundle


LOCAL_TRACKS_FILENAME = "local_tracks.jsonl"
CALIBRATIONS_FILENAME = "calibrations.json"
TRUTH_RELATIVE_PATH = Path("truth") / "truth_labels.json"
REPLAY_MANIFEST_SCHEMA = "center-terminal-gnn-replay-v1"
REPLAY_REQUIRED_PATH_KEYS = (
    "crossview_local_tracks",
    "crossview_calibrations",
    "crossview_capture_plan",
    "crossview_truth",
)


@dataclass(frozen=True)
class ReplayManifest:
    manifest_path: Path
    scenario_id: str
    campaign_seed: int
    target_count: int
    resource_count: int
    test_only: bool
    paths: Mapping[str, Path]
    sha256: Mapping[str, str]

    def audit_dict(self) -> dict[str, object]:
        return {
            "schema_version": REPLAY_MANIFEST_SCHEMA,
            "scenario_id": self.scenario_id,
            "campaign_seed": self.campaign_seed,
            "target_count": self.target_count,
            "resource_count": self.resource_count,
            "test_only": self.test_only,
            "verified_path_keys": REPLAY_REQUIRED_PATH_KEYS,
            "sha256": {
                key: self.sha256[key] for key in REPLAY_REQUIRED_PATH_KEYS
            },
        }


@dataclass(frozen=True)
class SavedReplayOnlineInputs:
    records: tuple[LocalVisualTrackRecord, ...]
    calibrations: Mapping[str, CameraCalibration]
    capture_plan: Mapping[str, Any]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_replay_manifest(
    path: Path,
    *,
    verify_hashes: bool = True,
) -> ReplayManifest:
    manifest_path = path.resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != REPLAY_MANIFEST_SCHEMA:
        raise ValueError("unsupported replay manifest schema")
    raw_paths = payload.get("paths")
    raw_hashes = payload.get("sha256")
    if not isinstance(raw_paths, Mapping) or not isinstance(raw_hashes, Mapping):
        raise ValueError("replay manifest paths and sha256 must be objects")
    missing_paths = [key for key in REPLAY_REQUIRED_PATH_KEYS if key not in raw_paths]
    missing_hashes = [key for key in REPLAY_REQUIRED_PATH_KEYS if key not in raw_hashes]
    if missing_paths or missing_hashes:
        raise ValueError(
            "replay manifest is missing required cross-view paths or hashes: "
            + ", ".join((*missing_paths, *missing_hashes))
        )
    resolved_paths: dict[str, Path] = {}
    verified_hashes: dict[str, str] = {}
    for key in REPLAY_REQUIRED_PATH_KEYS:
        raw_path = Path(str(raw_paths[key]))
        resolved = raw_path if raw_path.is_absolute() else manifest_path.parent / raw_path
        resolved = resolved.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"replay path {key} does not exist: {resolved}")
        expected = str(raw_hashes[key]).lower()
        if len(expected) != 64 or any(value not in "0123456789abcdef" for value in expected):
            raise ValueError(f"invalid SHA256 digest for replay path {key}")
        if verify_hashes:
            actual = sha256_file(resolved)
            if actual != expected:
                raise ValueError(f"SHA256 mismatch for replay path {key}")
        resolved_paths[key] = resolved
        verified_hashes[key] = expected
    scenario_id = str(payload.get("scenario_id", "")).strip()
    target_count = int(payload.get("target_count", 0))
    resource_count = int(payload.get("resource_count", 0))
    if not scenario_id or target_count <= 0 or resource_count <= 0:
        raise ValueError("replay scenario and dimensions must be positive")
    if not isinstance(payload.get("test_only"), bool):
        raise ValueError("replay manifest test_only must be boolean")
    return ReplayManifest(
        manifest_path=manifest_path,
        scenario_id=scenario_id,
        campaign_seed=int(payload["campaign_seed"]),
        target_count=target_count,
        resource_count=resource_count,
        test_only=bool(payload["test_only"]),
        paths=resolved_paths,
        sha256=verified_hashes,
    )


def verify_replay_hashes(
    manifest: ReplayManifest,
    path_keys: Sequence[str],
) -> None:
    for key in path_keys:
        if key not in REPLAY_REQUIRED_PATH_KEYS:
            raise ValueError(f"unsupported replay hash key: {key}")
        if sha256_file(manifest.paths[key]) != manifest.sha256[key]:
            raise ValueError(f"SHA256 mismatch for replay path {key}")


def load_online_capture_plan(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "terminal-crossview-airsim-capture-plan-v1":
        raise ValueError("unsupported AirSim capture plan")
    frames = payload.get("frames")
    if not isinstance(frames, list) or not frames:
        raise ValueError("capture plan must contain at least one frame")
    online_frames = []
    for fallback_index, frame in enumerate(frames):
        cameras = []
        for camera in frame.get("cameras", []):
            online_camera = {
                "camera_id": str(camera["camera_id"]),
                "yaw_pitch_roll_deg": tuple(
                    float(value) for value in camera["yaw_pitch_roll_deg"]
                ),
            }
            if "sector_index" in camera:
                online_camera["sector_index"] = int(camera["sector_index"])
            cameras.append(online_camera)
        online_frames.append(
            {
                "frame_index": int(frame.get("frame_index", fallback_index)),
                "cameras": cameras,
            }
        )
    # Deliberately omit detection filters and offline_sector_expectations.
    return {
        "schema_version": "terminal-crossview-airsim-capture-plan-v1",
        "frames": online_frames,
    }


def load_saved_replay_online(manifest: ReplayManifest) -> SavedReplayOnlineInputs:
    verify_replay_hashes(
        manifest,
        (
            "crossview_local_tracks",
            "crossview_calibrations",
            "crossview_capture_plan",
        ),
    )
    records = load_records(manifest.paths["crossview_local_tracks"])
    calibrations = load_calibrations(manifest.paths["crossview_calibrations"])
    if len(calibrations) != manifest.resource_count:
        raise ValueError(
            "replay resource_count does not match cross-view calibrations"
        )
    capture_plan = load_online_capture_plan(
        manifest.paths["crossview_capture_plan"]
    )
    return SavedReplayOnlineInputs(records, calibrations, capture_plan)


def load_saved_replay_truth(manifest: ReplayManifest) -> OfflineTruthLabels:
    verify_replay_hashes(manifest, ("crossview_truth",))
    payload = json.loads(
        manifest.paths["crossview_truth"].read_text(encoding="utf-8")
    )
    if payload.get("offline_truth_only") is not True:
        raise ValueError("saved replay truth is not marked offline-only")
    mapping = payload.get("track_to_target")
    if not isinstance(mapping, Mapping):
        raise ValueError("saved replay truth mapping is invalid")
    return OfflineTruthLabels(
        track_to_target={str(key): str(value) for key, value in mapping.items()},
        target_trajectories_ned_m={},
        scenario_name=manifest.scenario_id,
        seed=manifest.campaign_seed,
        offline_only=True,
    )


def write_fixture(directory: Path, bundle: FixtureBundle) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for record in bundle.records:
        assert_online_anonymous(record.to_online_dict())
    write_jsonl(directory / LOCAL_TRACKS_FILENAME, bundle.records)
    write_json(
        directory / CALIBRATIONS_FILENAME,
        {
            "schema_version": "terminal-crossview-calibrations-v1",
            "cameras": [item.to_dict() for item in bundle.calibrations.values()],
        },
    )
    write_json(directory / TRUTH_RELATIVE_PATH, bundle.truth.to_dict())
    write_json(
        directory / "fixture_manifest.json",
        {
            "schema_version": "terminal-crossview-fixture-v1",
            "scenario_name": bundle.scenario_name,
            "seed": bundle.seed,
            "frame_count": bundle.frame_count,
            "target_count": bundle.target_count,
            "online_tracks": LOCAL_TRACKS_FILENAME,
            "offline_truth": TRUTH_RELATIVE_PATH.as_posix(),
        },
    )
    return directory


def _local_record(payload: Mapping[str, Any]) -> LocalVisualTrackRecord:
    return LocalVisualTrackRecord(
        camera_id=str(payload["camera_id"]),
        local_track_id=str(payload["local_track_id"]),
        measurement_timestamp=float(payload["measurement_timestamp"]),
        arrival_timestamp=float(payload["arrival_timestamp"]),
        bbox_xyxy=tuple(float(value) for value in payload["bbox_xyxy"]),  # type: ignore[arg-type]
        center_px=tuple(float(value) for value in payload["center_px"]),  # type: ignore[arg-type]
        ray_origin_ned_m=tuple(float(value) for value in payload["ray_origin_ned_m"]),  # type: ignore[arg-type]
        ray_direction_ned=tuple(float(value) for value in payload["ray_direction_ned"]),  # type: ignore[arg-type]
        camera_yaw_pitch_roll_deg=tuple(
            float(value) for value in payload["camera_yaw_pitch_roll_deg"]  # type: ignore[arg-type]
        ),
        recognized=bool(payload["recognized"]),
        recognition_extent_px=float(payload["recognition_extent_px"]),
        track_quality=float(payload.get("track_quality", 1.0)),
        schema_version=str(payload.get("schema_version", "center-terminal-local-visual-track-v1")),
        metadata=dict(payload.get("metadata", {})),
    )


def load_records(path: Path) -> tuple[LocalVisualTrackRecord, ...]:
    records: list[LocalVisualTrackRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        assert_online_anonymous(payload)
        records.append(_local_record(payload))
    return tuple(records)


def load_calibrations(path: Path) -> dict[str, CameraCalibration]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result = {
        item.camera_id: item
        for item in (
            CameraCalibration.from_dict(value) for value in payload["cameras"]
        )
    }
    return result


def load_truth(path: Path) -> OfflineTruthLabels:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("offline_only") is not True:
        raise ValueError("truth file is not marked offline-only")
    return OfflineTruthLabels(
        track_to_target=dict(payload["track_to_target"]),
        target_trajectories_ned_m={
            key: tuple(tuple(float(value) for value in row) for row in rows)
            for key, rows in payload["target_trajectories_ned_m"].items()
        },
        scenario_name=str(payload["scenario_name"]),
        seed=int(payload["seed"]),
        offline_only=True,
    )


def load_fixture(
    directory: Path,
) -> tuple[
    tuple[LocalVisualTrackRecord, ...],
    dict[str, CameraCalibration],
    OfflineTruthLabels | None,
]:
    records = load_records(directory / LOCAL_TRACKS_FILENAME)
    calibrations = load_calibrations(directory / CALIBRATIONS_FILENAME)
    truth_path = directory / TRUTH_RELATIVE_PATH
    truth = load_truth(truth_path) if truth_path.exists() else None
    return records, calibrations, truth
