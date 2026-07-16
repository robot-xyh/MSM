from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

import numpy as np

from .covariance_contract import validate_sensor_observation_covariance
from .types import SensorObservation

if TYPE_CHECKING:
    from research_modules.integration_contracts import LocalImageTrackObservation


def sensor_observation_from_local_image_track(
    track: LocalImageTrackObservation,
    *,
    observation_id: str | None = None,
) -> SensorObservation | None:
    """Adapt one identity-free camera-local sample into a D1 EO observation.

    Lost samples deliberately produce no observation.  Measured samples are
    revalidated at the D1 boundary because the contract's NumPy arrays and
    metadata mapping can still be mutated after dataclass construction.
    """

    state = str(track.track_state).strip().lower()
    if state == "lost":
        return None
    if state != "measured":
        raise ValueError("local image track_state must be 'measured' or 'lost'")

    sensor_id = _nonempty_text(track.sensor_id, "sensor_id")
    stream_id = _nonempty_text(track.stream_id, "stream_id")
    local_track_id = _nonempty_text(track.local_track_id, "local_track_id")
    local_epoch = int(track.local_epoch)
    if local_epoch < 0:
        raise ValueError("local_epoch must be non-negative")

    spectral_band = str(track.spectral_band).strip().lower()
    if spectral_band not in {"visible", "infrared"}:
        raise ValueError("local image spectral_band must be 'visible' or 'infrared'")

    measurement_timestamp = _finite_timestamp(
        track.measurement_timestamp,
        "measurement_timestamp",
    )
    arrival_timestamp = _finite_timestamp(track.arrival_timestamp, "arrival_timestamp")
    if arrival_timestamp < measurement_timestamp:
        raise ValueError("arrival_timestamp cannot precede measurement_timestamp")

    confidence = float(track.confidence)
    if not np.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("local image confidence must be finite and within [0, 1]")

    center_px = _validated_center_px(track.center_px)
    bbox_xyxy = _validated_bbox_xyxy(track.bbox_xyxy)
    covariance = _validated_pixel_covariance(track.pixel_covariance)
    source_track_key = (
        f"{sensor_id}/{stream_id}/epoch-{local_epoch}/{local_track_id}"
    )
    metadata = _online_safe_metadata(track.metadata)
    metadata.update(
        {
            "sensor_id": sensor_id,
            "stream_id": stream_id,
            "local_track_id": local_track_id,
            "local_epoch": local_epoch,
            "source_track_key": source_track_key,
            "spectral_band": spectral_band,
            "track_state": "measured",
            "bbox_xyxy": bbox_xyxy,
            "center_px": center_px.copy(),
            # A repeated delivery of the same local-track sample has the same
            # lineage, while a later sample from that local track stays unique.
            "source_lineage_key": (
                "local_image_track",
                source_track_key,
                measurement_timestamp.hex(),
            ),
        }
    )

    resolved_observation_id = (
        _deterministic_observation_id(
            sensor_id,
            stream_id,
            local_epoch,
            local_track_id,
            measurement_timestamp,
        )
        if observation_id is None
        else str(observation_id).strip()
    )
    if not resolved_observation_id:
        raise ValueError("observation_id must be non-empty when supplied")

    observation = SensorObservation(
        observation_id=resolved_observation_id,
        sensor_id=sensor_id,
        modality="eo",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="pixel",
        measurement=center_px.copy(),
        covariance=covariance.copy(),
        confidence=confidence,
        quality_flags=tuple(track.quality_flags),
        metadata=metadata,
    )
    validate_sensor_observation_covariance(
        observation,
        context="D1 local image track adapter",
    )
    return observation


def _deterministic_observation_id(
    sensor_id: str,
    stream_id: str,
    local_epoch: int,
    local_track_id: str,
    measurement_timestamp: float,
) -> str:
    fields = (
        quote(sensor_id, safe="._-"),
        quote(stream_id, safe="._-"),
        f"epoch-{local_epoch}",
        quote(local_track_id, safe="._-"),
        f"t-{measurement_timestamp.hex()}",
    )
    return "local-image:" + ":".join(fields)


def _finite_timestamp(value: object, name: str) -> float:
    timestamp = float(value)
    if not np.isfinite(timestamp):
        raise ValueError(f"{name} must be finite")
    return timestamp


def _validated_center_px(value: object) -> np.ndarray:
    if value is None:
        raise ValueError("measured local image tracks require center_px")
    try:
        center = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("center_px must be a numeric 2-vector") from exc
    if center.shape != (2,) or not np.isfinite(center).all():
        raise ValueError("center_px must contain two finite pixel coordinates")
    return center.copy()


def _validated_bbox_xyxy(value: object) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        bbox = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox_xyxy must contain four numeric values") from exc
    if bbox.shape != (4,) or not np.isfinite(bbox).all():
        raise ValueError("bbox_xyxy must contain four finite values")
    x1, y1, x2, y2 = (float(item) for item in bbox)
    if x2 < x1 or y2 < y1:
        raise ValueError("bbox_xyxy must be (x_min, y_min, x_max, y_max)")
    return (x1, y1, x2, y2)


def _validated_pixel_covariance(value: object) -> np.ndarray:
    if value is None:
        raise ValueError("measured local image tracks require pixel_covariance")
    try:
        covariance = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("pixel_covariance must be a numeric 2x2 matrix") from exc
    if covariance.shape != (2, 2):
        raise ValueError("pixel_covariance must have shape (2, 2)")
    if not np.isfinite(covariance).all():
        raise ValueError("pixel_covariance must be finite")
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-9):
        raise ValueError("pixel_covariance must be symmetric")
    if float(np.linalg.eigvalsh(covariance).min()) < -1.0e-9:
        raise ValueError("pixel_covariance must be positive semidefinite")
    return covariance.copy()


def _nonempty_text(value: object, name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must be non-empty")
    return text


def _online_safe_metadata(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("local image metadata must be a mapping")
    metadata = copy.deepcopy(dict(value))
    forbidden = tuple(_forbidden_identity_paths(metadata))
    if forbidden:
        raise ValueError(
            "local image metadata cannot contain global/truth identity: "
            + ", ".join(forbidden)
        )
    return metadata


def _forbidden_identity_paths(value: object, path: str = "metadata"):
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key)
            item_path = f"{path}.{key}"
            if _is_forbidden_identity_key(key):
                yield item_path
            yield from _forbidden_identity_paths(item, item_path)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for index, item in enumerate(value):
            yield from _forbidden_identity_paths(item, f"{path}[{index}]")
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            item_path = f"{path}.{field.name}"
            if _is_forbidden_identity_key(field.name):
                yield item_path
            yield from _forbidden_identity_paths(getattr(value, field.name), item_path)


def _is_forbidden_identity_key(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    components = {item for item in normalized.split("_") if item}
    if normalized in {"global_track_id", "global_id", "identity_id"}:
        return True
    if "truth" in components and components.intersection(
        {"id", "label", "name", "object", "target", "track"}
    ):
        return True
    if "actor" in components and components.intersection({"id", "name"}):
        return True
    if "object" in components and "id" in components:
        return True
    if "target" in components and components.intersection({"id", "name"}):
        return True
    return "segmentation" in components and "id" in components
