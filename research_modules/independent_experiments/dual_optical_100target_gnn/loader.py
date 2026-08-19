"""Load anonymous dual-optical v2/v3 records without leaking offline identity."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .schema import AnonymousTrack, OfflineLabels, OnlineEpisode, TrackSample


_ARTIFACT_ALIASES = {
    "anonymous_detections": ("anonymous_detections", "anonymous_detections_v3"),
    "local_tracks": ("local_tracks", "local_tracks_v3"),
    "local_track_samples": ("local_track_samples", "local_track_samples_v3"),
    "track_scoring": ("track_scoring", "track_scoring_v3"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    parsed = json.loads(value)
    return list(parsed) if isinstance(parsed, list) else []


def _is_true(value: str | bool | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _resolve_artifact(
    root: Path,
    artifacts: dict[str, str],
    logical_name: str,
    *,
    required: bool = True,
) -> Path | None:
    for alias in _ARTIFACT_ALIASES[logical_name]:
        relative = artifacts.get(alias)
        if relative:
            path = root / relative
            if path.is_file():
                return path
    fallback_patterns = {
        "anonymous_detections": ("online/anonymous_detections*.csv",),
        "local_tracks": ("online/local_tracks*.csv",),
        "local_track_samples": ("online/local_track_samples*.csv",),
        "track_scoring": ("truth/track_scoring*.csv", "offline/track_scoring*.csv"),
    }
    for pattern in fallback_patterns[logical_name]:
        matches = sorted(root.glob(pattern))
        if matches:
            return matches[-1]
    if required:
        raise FileNotFoundError(f"missing {logical_name} artifact under {root}")
    return None


def _load_manifest(root: Path) -> tuple[dict[str, Any], Path]:
    path = root / "record_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"record_manifest.json not found under {root}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    version = str(manifest.get("schema_version", ""))
    if not (version.endswith("v2") or version.endswith("v3")):
        raise ValueError(f"unsupported record manifest schema: {version or '<missing>'}")
    return manifest, path


def _load_scenario(root: Path) -> tuple[dict[str, Any], Path]:
    path = root / "scenario.json"
    if not path.is_file():
        raise FileNotFoundError(f"scenario.json not found under {root}")
    return json.loads(path.read_text(encoding="utf-8")), path


def _direction_from_row(row: dict[str, str]) -> tuple[float, float, float]:
    if row.get("direction_ned"):
        values = _json_list(row["direction_ned"])
    else:
        values = [row.get("ray_x_ned"), row.get("ray_y_ned"), row.get("ray_z_ned")]
    direction = np.asarray([float(value) for value in values], dtype=float)
    norm = float(np.linalg.norm(direction))
    if direction.shape != (3,) or norm <= 1e-12:
        raise ValueError("invalid local-track ray direction")
    direction /= norm
    return tuple(float(value) for value in direction)


def _camera_geometry(scenario: dict[str, Any], camera_ids: tuple[str, str]) -> tuple[dict[str, tuple[float, float, float]], float]:
    values = scenario.get("scenario", scenario)
    positions: dict[str, tuple[float, float, float]] = {}
    explicit = scenario.get("camera_positions_ned") or values.get("camera_positions_ned")
    if isinstance(explicit, dict):
        for camera_id in camera_ids:
            item = explicit.get(camera_id)
            if item is not None:
                positions[camera_id] = tuple(float(value) for value in item)
    names = [values.get("camera_a_name"), values.get("camera_b_name")]
    raw_positions = [
        values.get("camera_a_position_ned"),
        values.get("camera_b_position_ned"),
    ]
    for name, position in zip(names, raw_positions):
        if name in camera_ids and position is not None:
            positions[str(name)] = tuple(float(value) for value in position)
    for index, camera_id in enumerate(camera_ids):
        if camera_id not in positions and raw_positions[index] is not None:
            positions[camera_id] = tuple(float(value) for value in raw_positions[index])
    if len(positions) != 2:
        raise ValueError("scenario does not define both camera positions")

    camera = scenario.get("camera", {})
    focal = camera.get("focal_length_px")
    if focal is None:
        width = float(camera.get("width", 1280.0))
        fov_deg = float(camera.get("horizontal_fov_deg", 2.93))
        focal = width / (2.0 * math.tan(math.radians(fov_deg) * 0.5))
    return positions, float(focal)


def load_online_episode(root: str | Path) -> OnlineEpisode:
    """Load online-only fields; this function never opens scoring artifacts."""

    root = Path(root).resolve()
    manifest, manifest_path = _load_manifest(root)
    scenario, scenario_path = _load_scenario(root)
    artifacts = dict(manifest.get("artifacts", {}))
    tracks_path = _resolve_artifact(root, artifacts, "local_tracks")
    samples_path = _resolve_artifact(root, artifacts, "local_track_samples")
    detections_path = _resolve_artifact(
        root, artifacts, "anonymous_detections", required=False
    )
    assert tracks_path is not None and samples_path is not None

    track_rows = _read_csv(tracks_path)
    stable_ids = {
        row["track_id"]
        for row in track_rows
        if "stable" not in row or _is_true(row.get("stable"))
    }
    camera_ids = tuple(sorted({row["camera_id"] for row in track_rows}))
    if len(camera_ids) != 2:
        raise ValueError(f"expected two cameras, found {camera_ids}")
    positions, focal_length_px = _camera_geometry(scenario, camera_ids)  # type: ignore[arg-type]

    detection_stats: dict[str, tuple[float, float]] = {}
    if detections_path is not None:
        for row in _read_csv(detections_path):
            bbox = _json_list(row.get("bbox_xyxy"))
            area = 0.0
            if len(bbox) == 4:
                area = max(0.0, float(bbox[2]) - float(bbox[0])) * max(
                    0.0, float(bbox[3]) - float(bbox[1])
                )
            detection_stats[row["detection_uid"]] = (
                area,
                float(row.get("confidence") or 1.0),
            )

    grouped: dict[str, list[TrackSample]] = {track_id: [] for track_id in stable_ids}
    camera_by_track = {row["track_id"]: row["camera_id"] for row in track_rows}
    for row in _read_csv(samples_path):
        track_id = row["track_id"]
        if track_id not in stable_ids:
            continue
        detection_uids = [str(value) for value in _json_list(row.get("detection_uids"))]
        stats = [detection_stats[uid] for uid in detection_uids if uid in detection_stats]
        areas = [item[0] for item in stats if item[0] > 0.0]
        confidences = [item[1] for item in stats]
        grouped[track_id].append(
            TrackSample(
                sweep_index=int(row.get("sweep_index") or row.get("scan_index") or 0),
                timestamp=float(row.get("measurement_timestamp") or row.get("timestamp") or 0.0),
                direction_ned=_direction_from_row(row),
                detection_count=max(1, len(detection_uids)),
                bbox_area_px2=float(np.mean(areas)) if areas else float(row.get("bbox_area_px2") or 0.0),
                confidence=float(np.mean(confidences)) if confidences else float(row.get("confidence") or 1.0),
            )
        )

    tracks: dict[str, list[AnonymousTrack]] = {camera_id: [] for camera_id in camera_ids}
    for track_id in sorted(grouped):
        samples = tuple(sorted(grouped[track_id], key=lambda item: item.timestamp))
        if not samples:
            continue
        camera_id = camera_by_track[track_id]
        tracks[camera_id].append(AnonymousTrack(track_id, camera_id, samples))

    values = scenario.get("scenario", scenario)
    seed = int(values.get("seed", 0))
    source_paths = [manifest_path, scenario_path, tracks_path, samples_path]
    if detections_path is not None:
        source_paths.append(detections_path)
    return OnlineEpisode(
        seed=seed,
        schema_version=str(manifest["schema_version"]),
        configured_target_count=(
            int(values["target_count"]) if values.get("target_count") is not None else None
        ),
        camera_ids=camera_ids,  # type: ignore[arg-type]
        camera_positions_ned=positions,
        focal_length_px=focal_length_px,
        tracks={key: tuple(value) for key, value in tracks.items()},
        source_hashes={str(path.relative_to(root)): sha256_file(path) for path in source_paths},
    )


def load_offline_labels(root: str | Path, episode: OnlineEpisode) -> OfflineLabels:
    """Load labels separately so online loading cannot expose identity."""

    root = Path(root).resolve()
    manifest, _ = _load_manifest(root)
    path = _resolve_artifact(
        root, dict(manifest.get("artifacts", {})), "track_scoring", required=True
    )
    assert path is not None
    identities: dict[str, str | None] = {}
    for row in _read_csv(path):
        track_id = row.get("track_id", "")
        if not track_id:
            continue
        identity = row.get("majority_truth_id") or row.get("identity") or None
        identities[track_id] = str(identity) if identity else None
    online_ids = {
        track.track_id
        for camera_id in episode.camera_ids
        for track in episode.tracks[camera_id]
    }
    filtered = {track_id: identities.get(track_id) for track_id in online_ids}
    scenario, _ = _load_scenario(root)
    expected_values = {
        str(item["truth_id"])
        for item in scenario.get("target_specs_offline_truth_only", [])
        if isinstance(item, dict) and item.get("truth_id")
    }
    if not expected_values:
        expected_values = {
            identity for identity in filtered.values() if identity is not None
        }
    expected = tuple(sorted(expected_values))
    return OfflineLabels(
        filtered,
        expected,
        {str(path.relative_to(root)): sha256_file(path)},
    )


def discover_seed_inputs(input_root: str | Path) -> dict[int, Path]:
    """Discover compatible episode directories and reject duplicate seeds."""

    root = Path(input_root).resolve()
    candidates: Iterable[Path]
    if (root / "record_manifest.json").is_file():
        candidates = (root,)
    else:
        candidates = (path.parent for path in root.rglob("record_manifest.json"))
    found: dict[int, Path] = {}
    for candidate in sorted(set(candidates)):
        try:
            episode = load_online_episode(candidate)
        except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
            continue
        if episode.seed in found:
            raise ValueError(
                f"duplicate episode seed {episode.seed}: {found[episode.seed]} and {candidate}"
            )
        found[episode.seed] = candidate
    return found
