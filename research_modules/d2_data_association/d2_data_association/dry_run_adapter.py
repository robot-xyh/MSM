"""Dry-run adapter for synthetic AirSim-style D2 association inputs.

This module intentionally accepts plain Python dictionaries/objects only. It
does not import AirSim and does not call any simulator API.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .associators import GNNHungarianAssociator
from .models import AssociationResult, Detection
from .tracker import Tracker


@dataclass(slots=True)
class DryRunAssociationFrame:
    """Per-frame D2 dry-run output."""

    timestamp: float
    detections: list[Detection]
    association_result: AssociationResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "detections": [detection.to_dict() for detection in self.detections],
            "association_result": self.association_result.to_dict(),
        }


@dataclass(slots=True)
class DryRunAssociationResult:
    """D2 dry-run output for the shared phase-1 episode driver."""

    tracker: Tracker
    frames: list[DryRunAssociationFrame]
    metrics: dict[str, Any]

    @property
    def active_tracks(self) -> list[dict[str, Any]]:
        return [track.to_dict() for track in self.tracker.active_tracks()]

    @property
    def global_track_ids(self) -> list[str]:
        return [track.global_track_id for track in self.tracker.active_tracks()]

    @property
    def association_logs(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.tracker.metrics.association_logs]

    def to_bus_message(self) -> dict[str, Any]:
        """Return a JSON-ready message for an offline data bus."""

        return {
            "module": "D2",
            "active_tracks": self.active_tracks,
            "global_track_ids": self.global_track_ids,
            "association_logs": self.association_logs,
            "metrics": dict(self.metrics),
            "id_switch_count": self.metrics["id_switch_count"],
            "track_continuity": self.metrics["track_continuity"],
        }


def build_default_dry_run_tracker() -> Tracker:
    """Build the default D2 phase-1 dry-run tracker."""

    return Tracker(
        associator=GNNHungarianAssociator(gate_threshold=9.21, feature_weight=6.0)
    )


def detections_from_d1_global_tracks(
    tracks: Iterable[Any],
    *,
    detection_id_prefix: str | None = None,
) -> tuple[float, list[Detection], list[str]]:
    """Convert D1 six-state NED GlobalTrack objects to D2 detections.

    D1 publishes `[north, east, down, vn, ve, vd]` tracks with 6x6 covariance.
    D2 only consumes horizontal association evidence, so this adapter projects
    state and covariance to the N-E plane while preserving sensing and arrival
    timestamps in metadata.
    """

    detections: list[Detection] = []
    truth_ids: list[str] = []
    frame_timestamp: float | None = None
    for track in tracks:
        metadata = dict(_mapping_or_empty(getattr(track, "metadata", {})))
        frame_id = str(metadata.get("frame_id", "ned")).lower()
        if frame_id != "ned":
            raise ValueError(f"D1 GlobalTrack must use NED coordinates, got {frame_id!r}")

        global_track_id = str(getattr(track, "global_track_id"))
        state = np.asarray(getattr(track, "state"), dtype=float).reshape(-1)
        if state.size < 6:
            raise ValueError("D1 GlobalTrack state must contain six NED components")
        covariance = np.asarray(getattr(track, "covariance"), dtype=float)
        if covariance.shape != (6, 6):
            raise ValueError("D1 GlobalTrack covariance must have shape (6, 6)")

        track_timestamp = float(getattr(track, "timestamp"))
        measurement_timestamp = float(
            _first_present(
                track,
                ("measurement_timestamp", "valid_at"),
                metadata.get(
                    "measurement_timestamp",
                    metadata.get("valid_at", track_timestamp),
                ),
            )
        )
        arrival_timestamp = float(
            _first_present(
                track,
                ("arrival_timestamp", "published_at", "received_timestamp"),
                metadata.get(
                    "arrival_timestamp",
                    metadata.get(
                        "published_at",
                        metadata.get("received_timestamp", track_timestamp),
                    ),
                ),
            )
        )
        if frame_timestamp is None or measurement_timestamp > frame_timestamp:
            frame_timestamp = measurement_timestamp

        truth_id = _optional_string(
            metadata.get("truth_id", metadata.get("ground_truth_id"))
        )
        if truth_id is not None:
            truth_ids.append(truth_id)

        detection_id = _optional_string(metadata.get("detection_id"))
        if detection_id is None:
            detection_id = (
                global_track_id
                if detection_id_prefix is None
                else f"{detection_id_prefix}-{global_track_id}"
            )

        detection_metadata = dict(metadata)
        detection_metadata.update(
            {
                "source_format": "d1_global_track",
                "frame_id": "ned",
                "global_track_id": global_track_id,
                "measurement_timestamp": measurement_timestamp,
                "arrival_timestamp": arrival_timestamp,
                "source_track_timestamp": track_timestamp,
                "covariance_projection": "ned_6d_to_xy",
            }
        )
        detections.append(
            Detection(
                detection_id=detection_id,
                timestamp=measurement_timestamp,
                position=state[:2].copy(),
                covariance=covariance[:2, :2].copy(),
                truth_id=truth_id,
                confidence=float(metadata.get("confidence", 1.0)),
                metadata=detection_metadata,
            )
        )

    return float(frame_timestamp or 0.0), detections, sorted(set(truth_ids))


def detections_from_airsim_frame(
    frame: Any,
    *,
    frame_index: int = 0,
    default_position_variance: float = 1.0,
) -> tuple[float, list[Detection], list[str]]:
    """Convert one synthetic AirSim-style frame to D2 detections.

    Accepted frame shapes are intentionally loose:

    - `{"timestamp": t, "detections": [...]}`
    - `{"timestamp": t, "tracks": [...]}`
    - `{"timestamp": t, "objects": [...]}`

    Each item may expose `position`, `position_ned`, `ned`, `location`, or
    top-level `x/y` fields. Only the horizontal x-y plane is passed to D2.
    """

    timestamp = float(
        _first_present(frame, ("measurement_timestamp", "timestamp", "sim_time", "time"), 0.0)
    )
    raw_items = _frame_items(frame)
    detections: list[Detection] = []
    truth_ids: list[str] = []

    for item_index, item in enumerate(raw_items):
        item_timestamp = float(
            _first_present(
                item,
                ("measurement_timestamp", "valid_at", "timestamp", "sim_time", "time"),
                timestamp,
            )
        )
        truth_id = _optional_string(
            _first_present(item, ("truth_id", "ground_truth_id", "object_id", "name"), None)
        )
        if truth_id is not None:
            truth_ids.append(truth_id)

        detection_id = _optional_string(
            _first_present(
                item,
                ("detection_id", "id", "track_id", "global_track_id", "object_id", "name"),
                None,
            )
        )
        if detection_id is None:
            detection_id = f"airsim-dry-run-{frame_index:04d}-{item_index:03d}"

        position_xy = _position_xy(item)
        covariance_xy = _covariance_xy(item, default_position_variance)
        metadata = dict(_mapping_or_empty(_first_present(item, ("metadata",), {})))
        metadata.setdefault("source_format", "airsim_dry_run")
        metadata.setdefault("source_detection_id", detection_id)
        metadata.setdefault("measurement_timestamp", item_timestamp)
        arrival_timestamp = _first_present(
            item,
            ("arrival_timestamp", "published_at", "received_timestamp"),
            metadata.get("arrival_timestamp", metadata.get("published_at", timestamp)),
        )
        metadata.setdefault("arrival_timestamp", float(arrival_timestamp))
        if truth_id is not None:
            metadata.setdefault("truth_id", truth_id)
        global_track_id = _optional_string(
            _first_present(item, ("global_track_id",), None)
        )
        if global_track_id is not None:
            metadata.setdefault("global_track_id", global_track_id)
            metadata.setdefault("frame_id", "ned")
        truth_position = _optional_position_xy(
            _first_present(item, ("truth_position", "ground_truth_position"), None)
        )
        if truth_position is not None:
            metadata["truth_position"] = truth_position.tolist()

        detections.append(
            Detection(
                detection_id=detection_id,
                timestamp=item_timestamp,
                position=position_xy,
                covariance=covariance_xy,
                truth_id=truth_id,
                confidence=float(_first_present(item, ("confidence", "score"), 1.0)),
                metadata=metadata,
                feature=_optional_vector(
                    _first_present(item, ("feature", "embedding", "descriptor"), None)
                ),
            )
        )

    frame_truth_ids = _first_present(frame, ("truth_ids_present", "truth_ids"), None)
    if frame_truth_ids is not None:
        truth_ids = [str(value) for value in frame_truth_ids if value is not None]
    return timestamp, detections, sorted(set(truth_ids))


def run_airsim_dry_run_association(
    frames: Iterable[Any],
    *,
    tracker: Tracker | None = None,
    default_position_variance: float = 1.0,
) -> DryRunAssociationResult:
    """Run the existing D2 Tracker/GNN path on synthetic dry-run frames."""

    active_tracker = tracker if tracker is not None else build_default_dry_run_tracker()
    output_frames: list[DryRunAssociationFrame] = []

    for frame_index, frame in enumerate(frames):
        timestamp, detections, truth_ids = detections_from_airsim_frame(
            frame,
            frame_index=frame_index,
            default_position_variance=default_position_variance,
        )
        association_result = active_tracker.step(
            detections,
            timestamp=timestamp,
            truth_ids_present=truth_ids,
        )
        output_frames.append(
            DryRunAssociationFrame(
                timestamp=timestamp,
                detections=detections,
                association_result=association_result,
            )
        )

    metrics = dict(active_tracker.metrics.summary())
    metrics.setdefault("id_switch_count", active_tracker.metrics.id_switch_count)
    metrics.setdefault("track_continuity", active_tracker.metrics.track_continuity)
    return DryRunAssociationResult(
        tracker=active_tracker,
        frames=output_frames,
        metrics=metrics,
    )


def _frame_items(frame: Any) -> list[Any]:
    if isinstance(frame, Mapping):
        for key in ("detections", "tracks", "objects"):
            if key in frame:
                return list(frame[key])
    for key in ("detections", "tracks", "objects"):
        value = getattr(frame, key, None)
        if value is not None:
            return list(value)
    if isinstance(frame, Sequence) and not isinstance(frame, (str, bytes, bytearray)):
        return list(frame)
    raise ValueError("frame must contain detections, tracks, or objects")


def _position_xy(item: Any) -> np.ndarray:
    value = _first_present(
        item,
        ("position", "position_ned", "ned", "location", "point", "state"),
        None,
    )
    if value is None:
        x = _first_present(item, ("x", "x_val", "px", "north"), None)
        y = _first_present(item, ("y", "y_val", "py", "east"), None)
        if x is None or y is None:
            raise ValueError("detection item must provide x-y position")
        return np.array([float(x), float(y)], dtype=float)
    return _vector_xy(value)


def _optional_position_xy(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    return _vector_xy(value)


def _vector_xy(value: Any) -> np.ndarray:
    if isinstance(value, Mapping):
        x = _first_present(value, ("x", "x_val", "px", "north", "0"), None)
        y = _first_present(value, ("y", "y_val", "py", "east", "1"), None)
        if x is None or y is None:
            raise ValueError("position mapping must provide x/y or north/east")
        return np.array([float(x), float(y)], dtype=float)
    x = _first_present(value, ("x", "x_val", "px", "north"), None)
    y = _first_present(value, ("y", "y_val", "py", "east"), None)
    if x is not None and y is not None:
        return np.array([float(x), float(y)], dtype=float)
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size < 2:
        raise ValueError("position vector must contain at least x and y")
    return array[:2].astype(float)


def _covariance_xy(item: Any, default_position_variance: float) -> np.ndarray:
    value = _first_present(
        item,
        ("covariance", "position_covariance", "covariance_xy", "covariance_ned"),
        None,
    )
    if value is None:
        return np.eye(2, dtype=float) * float(default_position_variance)
    if isinstance(value, Mapping):
        xx = float(_first_present(value, ("xx", "x", "north"), default_position_variance))
        yy = float(_first_present(value, ("yy", "y", "east"), default_position_variance))
        xy = float(_first_present(value, ("xy", "yx"), 0.0))
        return np.array([[xx, xy], [xy, yy]], dtype=float)

    array = np.asarray(value, dtype=float)
    if array.ndim == 0:
        return np.eye(2, dtype=float) * float(array)
    if array.ndim == 1:
        flat = array.reshape(-1)
        if flat.size == 2:
            return np.diag(flat)
        if flat.size == 4:
            return flat.reshape(2, 2)
        if flat.size == 9:
            return flat.reshape(3, 3)[:2, :2]
    if array.ndim == 2 and array.shape[0] >= 2 and array.shape[1] >= 2:
        return array[:2, :2].astype(float)
    raise ValueError("covariance must be scalar, 2-vector, 2x2, or 3x3 compatible")


def _first_present(item: Any, names: tuple[str, ...], default: Any) -> Any:
    if isinstance(item, Mapping):
        for name in names:
            if name in item:
                return item[name]
        return default
    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    return default


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_vector(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=float).reshape(-1)
