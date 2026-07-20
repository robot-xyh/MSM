"""Truth-free contracts for scalable three-dimensional data association."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import numpy as np

from .models import TrackLifecycleState, govern_covariance


STATE_ORDER_3D = ("pN", "pE", "pD", "vN", "vE", "vD")
POSITION_ORDER_3D = STATE_ORDER_3D[:3]
POSITION_H_3D = np.hstack((np.eye(3, dtype=float), np.zeros((3, 3), dtype=float)))


@dataclass(slots=True)
class Detection3D:
    """Anonymous Cartesian NED position observation for the online D2 path.

    The optional velocity can be an independent kinematic measurement or part
    of a correlated six-state source posterior. ``state_estimate_covariance``
    explicitly marks the latter case and preserves its position/velocity cross
    covariance. Association gating always uses the three-dimensional position
    innovation and its 3x3 marginal covariance.
    """

    detection_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    position_ned: np.ndarray
    covariance: np.ndarray
    confidence: float = 1.0
    velocity_ned: np.ndarray | None = None
    velocity_covariance: np.ndarray | None = None
    state_estimate_covariance: np.ndarray | None = None
    source_node_id: str | None = None
    source_track_id: str | None = None
    frame_id: str = "NED"
    metadata: dict[str, Any] = field(default_factory=dict)
    covariance_consistency: dict[str, Any] = field(default_factory=dict)
    state_estimate_covariance_consistency: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.detection_id = str(self.detection_id).strip()
        if not self.detection_id:
            raise ValueError("detection_id must be non-empty")
        self.measurement_timestamp = _finite_timestamp(
            self.measurement_timestamp, "measurement_timestamp"
        )
        self.arrival_timestamp = _finite_timestamp(
            self.arrival_timestamp, "arrival_timestamp"
        )
        if self.arrival_timestamp + 1.0e-12 < self.measurement_timestamp:
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")

        self.position_ned = _finite_vector(self.position_ned, 3, "position_ned")
        self.covariance, self.covariance_consistency = govern_covariance(
            self.covariance,
            (3, 3),
            "3D detection covariance",
        )
        self.confidence = float(self.confidence)
        if not np.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and within [0, 1]")

        if self.velocity_ned is not None:
            self.velocity_ned = _finite_vector(
                self.velocity_ned, 3, "velocity_ned"
            )
            velocity_covariance = (
                np.eye(3, dtype=float) * 25.0
                if self.velocity_covariance is None
                else self.velocity_covariance
            )
            self.velocity_covariance, _ = govern_covariance(
                velocity_covariance,
                (3, 3),
                "3D detection velocity covariance",
            )
            if self.state_estimate_covariance is not None:
                (
                    self.state_estimate_covariance,
                    self.state_estimate_covariance_consistency,
                ) = govern_covariance(
                    self.state_estimate_covariance,
                    (6, 6),
                    "3D source state-estimate covariance",
                )
                if not np.allclose(
                    self.state_estimate_covariance[:3, :3],
                    self.covariance,
                    rtol=1.0e-9,
                    atol=1.0e-10,
                ):
                    raise ValueError(
                        "state_estimate_covariance position marginal must match "
                        "covariance"
                    )
                if not np.allclose(
                    self.state_estimate_covariance[3:, 3:],
                    self.velocity_covariance,
                    rtol=1.0e-9,
                    atol=1.0e-10,
                ):
                    raise ValueError(
                        "state_estimate_covariance velocity marginal must match "
                        "velocity_covariance"
                    )
        elif self.velocity_covariance is not None:
            raise ValueError("velocity_covariance requires velocity_ned")
        elif self.state_estimate_covariance is not None:
            raise ValueError("state_estimate_covariance requires velocity_ned")

        self.source_node_id = _optional_identifier(self.source_node_id)
        self.source_track_id = _optional_identifier(self.source_track_id)
        if self.source_track_id is not None and self.source_node_id is None:
            raise ValueError("source_track_id requires source_node_id")
        self.frame_id = str(self.frame_id).strip().upper()
        if self.frame_id != "NED":
            raise ValueError("Detection3D requires the NED working frame")

        self.metadata = dict(self.metadata)
        assert_online_metadata_truth_free(self.metadata)

    @property
    def timestamp(self) -> float:
        """Compatibility alias for the legacy detection timestamp."""

        return self.measurement_timestamp

    @property
    def position(self) -> np.ndarray:
        """Compatibility alias with explicit NED semantics."""

        return self.position_ned

    @property
    def source_key(self) -> str | None:
        if self.source_node_id is None or self.source_track_id is None:
            return None
        return f"{self.source_node_id}::{self.source_track_id}"

    @property
    def state_estimate(self) -> np.ndarray | None:
        """Return the six-state source estimate when velocity is available."""

        if self.velocity_ned is None:
            return None
        return np.concatenate((self.position_ned, self.velocity_ned))

    def to_dict(self) -> dict[str, Any]:
        return {
            "detection_id": self.detection_id,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "frame_id": self.frame_id,
            "position_ned": self.position_ned.tolist(),
            "covariance": self.covariance.tolist(),
            "confidence": self.confidence,
            "velocity_ned": (
                None if self.velocity_ned is None else self.velocity_ned.tolist()
            ),
            "velocity_covariance": (
                None
                if self.velocity_covariance is None
                else self.velocity_covariance.tolist()
            ),
            "state_estimate_covariance": (
                None
                if self.state_estimate_covariance is None
                else self.state_estimate_covariance.tolist()
            ),
            "source_node_id": self.source_node_id,
            "source_track_id": self.source_track_id,
            "metadata": _json_ready(self.metadata),
            "covariance_consistency": _json_ready(self.covariance_consistency),
            "state_estimate_covariance_consistency": _json_ready(
                self.state_estimate_covariance_consistency
            ),
        }


@dataclass(slots=True)
class GlobalTrack3D:
    """Center-owned CV track with state ``[pN,pE,pD,vN,vE,vD]``."""

    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    timestamp: float
    lifecycle_state: TrackLifecycleState = TrackLifecycleState.TENTATIVE
    hits: int = 0
    consecutive_hits: int = 0
    misses: int = 0
    age: int = 0
    created_at: float = 0.0
    last_update_time: float = 0.0
    last_detection_id: str | None = None
    identity_confidence: float = 0.0
    track_quality: float = 0.0
    association_risk: float = 0.0
    source_track_keys: set[str] = field(default_factory=set)
    history: list[dict[str, Any]] = field(default_factory=list)
    history_limit: int = 32
    covariance_consistency: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.global_track_id = str(self.global_track_id).strip()
        if not self.global_track_id:
            raise ValueError("global_track_id must be non-empty")
        self.state = _finite_vector(self.state, 6, "state")
        self.covariance, self.covariance_consistency = govern_covariance(
            self.covariance,
            (6, 6),
            "3D track covariance",
        )
        self.timestamp = _finite_timestamp(self.timestamp, "timestamp")
        self.created_at = _finite_timestamp(self.created_at, "created_at")
        self.last_update_time = _finite_timestamp(
            self.last_update_time, "last_update_time"
        )
        self.lifecycle_state = TrackLifecycleState(self.lifecycle_state)
        self.history_limit = int(self.history_limit)
        if self.history_limit <= 0:
            raise ValueError("history_limit must be positive")
        self.source_track_keys = {
            str(item) for item in self.source_track_keys if str(item)
        }
        self.track_quality = float(np.clip(self.track_quality, 0.0, 1.0))
        self.association_risk = float(np.clip(self.association_risk, 0.0, 1.0))
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit :]

    @property
    def position_ned(self) -> np.ndarray:
        return self.state[:3]

    @property
    def velocity_ned(self) -> np.ndarray:
        return self.state[3:]

    @property
    def position(self) -> np.ndarray:
        return self.position_ned

    def ensure_covariance_consistency(self) -> None:
        self.covariance, self.covariance_consistency = govern_covariance(
            self.covariance,
            (6, 6),
            "3D track covariance",
        )

    def append_history(
        self,
        event: str,
        detection: Detection3D | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": self.timestamp,
            "event": str(event),
            "state": self.state.tolist(),
            "position_covariance_trace": float(np.trace(self.covariance[:3, :3])),
            "lifecycle_state": self.lifecycle_state.value,
            "hits": self.hits,
            "misses": self.misses,
        }
        if detection is not None:
            entry["detection_id"] = detection.detection_id
        self.history.append(entry)
        overflow = len(self.history) - self.history_limit
        if overflow > 0:
            del self.history[:overflow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "state_order": list(STATE_ORDER_3D),
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
            "timestamp": self.timestamp,
            "lifecycle_state": self.lifecycle_state.value,
            "hits": self.hits,
            "consecutive_hits": self.consecutive_hits,
            "misses": self.misses,
            "age": self.age,
            "created_at": self.created_at,
            "last_update_time": self.last_update_time,
            "last_detection_id": self.last_detection_id,
            "identity_confidence": self.identity_confidence,
            "track_quality": self.track_quality,
            "association_risk": self.association_risk,
            "source_track_keys": sorted(self.source_track_keys),
            "history": _json_ready(self.history),
            "history_limit": self.history_limit,
            "covariance_consistency": _json_ready(self.covariance_consistency),
        }


def detection3d_from_position_measurement(measurement: Any) -> Detection3D:
    """Adapt one duck-typed Cartesian NED measurement without importing main."""

    metadata = dict(_mapping_or_empty(_read(measurement, "metadata", {})))
    assert_online_metadata_truth_free(metadata)
    modality = str(
        _read(measurement, "modality", metadata.get("source_modality", ""))
    ).strip().lower()
    if modality in {
        "acoustic",
        "acoustic_bearing",
        "camera_bbox",
        "eo",
        "radar",
        "radar_spherical",
        "vision_bbox",
    }:
        raise ValueError(
            "D2 requires a Cartesian 3D position measurement; raw radar/visual "
            "input is not Cartesian NED and must first be fused or projected by D1"
        )
    frame_id = str(_read(measurement, "frame_id", metadata.get("frame_id", "NED")))
    value = np.asarray(_read(measurement, "measurement"), dtype=float).reshape(-1)
    covariance = np.asarray(_read(measurement, "covariance"), dtype=float)
    if value.shape != (3,) or covariance.shape != (3, 3):
        raise ValueError(
            "D2 requires a Cartesian 3D position measurement; raw radar/visual "
            "measurements must first be fused or projected by D1"
        )
    order = metadata.get("measurement_order")
    if order is not None:
        normalized = tuple(str(item).strip().lower() for item in order)
        allowed = {
            ("pn", "pe", "pd"),
            ("north", "east", "down"),
            ("north_m", "east_m", "down_m"),
        }
        if normalized not in allowed:
            raise ValueError("measurement_order is not Cartesian NED position")
    return Detection3D(
        detection_id=str(
            _read(
                measurement,
                "observation_id",
                _read(measurement, "detection_id", ""),
            )
        ),
        measurement_timestamp=float(_read(measurement, "measurement_timestamp")),
        arrival_timestamp=float(_read(measurement, "arrival_timestamp")),
        position_ned=value,
        covariance=covariance,
        confidence=float(_read(measurement, "confidence", 1.0)),
        source_node_id=_optional_identifier(metadata.get("source_node_id")),
        source_track_id=_optional_identifier(metadata.get("source_track_id")),
        frame_id=frame_id,
        metadata=metadata,
    )


def detections3d_from_d1_global_tracks(
    tracks: Iterable[Any],
    *,
    detection_id_prefix: str = "d1-3d",
) -> tuple[float, list[Detection3D]]:
    """Adapt D1 six-state tracks while ignoring any upstream global ID value.

    The adapter deliberately allocates anonymous observation IDs by scan order.
    An upstream object's ``global_track_id`` is neither copied nor used as D2's
    canonical identity authority.
    """

    detections: list[Detection3D] = []
    frame_timestamp = 0.0
    for index, item in enumerate(tracks):
        metadata = dict(_mapping_or_empty(_read(item, "metadata", {})))
        assert_online_metadata_truth_free(metadata)
        frame_id = str(metadata.get("frame_id", _read(item, "frame_id", "NED")))
        state = _finite_vector(_read(item, "state"), 6, "D1 track state")
        covariance, _ = govern_covariance(
            _read(item, "covariance"),
            (6, 6),
            "D1 track covariance",
        )
        state_timestamp = _finite_timestamp(_read(item, "timestamp"), "timestamp")
        source_measurement_timestamp = _finite_timestamp(
            _read(
                item,
                "measurement_timestamp",
                metadata.get(
                    "latest_measurement_timestamp",
                    metadata.get("measurement_timestamp", state_timestamp),
                ),
            ),
            "source measurement_timestamp",
        )
        source_arrival_timestamp = _finite_timestamp(
            _read(
                item,
                "arrival_timestamp",
                metadata.get(
                    "latest_arrival_timestamp",
                    metadata.get("arrival_timestamp", state_timestamp),
                ),
            ),
            "source arrival_timestamp",
        )
        if source_arrival_timestamp + 1.0e-12 < source_measurement_timestamp:
            raise ValueError(
                "source arrival_timestamp cannot precede measurement_timestamp"
            )
        published_at = _finite_timestamp(
            metadata.get("published_at", state_timestamp),
            "published_at",
        )
        arrival_timestamp = max(
            state_timestamp,
            source_arrival_timestamp,
            published_at,
        )
        frame_timestamp = max(frame_timestamp, state_timestamp)
        detection_id = str(
            metadata.get(
                "observation_id",
                metadata.get(
                    "detection_id",
                    f"{detection_id_prefix}-{state_timestamp:.9f}-{index:04d}",
                ),
            )
        )
        safe_metadata = dict(metadata)
        safe_metadata.update(
            {
                "source_format": "d1_six_state_track",
                "upstream_identity_ignored": True,
                "state_valid_timestamp": state_timestamp,
                "source_measurement_timestamp": source_measurement_timestamp,
                "source_arrival_timestamp": source_arrival_timestamp,
                "state_order": list(STATE_ORDER_3D),
            }
        )
        detections.append(
            Detection3D(
                detection_id=detection_id,
                measurement_timestamp=state_timestamp,
                arrival_timestamp=arrival_timestamp,
                position_ned=state[:3],
                covariance=covariance[:3, :3],
                confidence=float(metadata.get("confidence", 1.0)),
                velocity_ned=state[3:],
                velocity_covariance=covariance[3:, 3:],
                state_estimate_covariance=covariance,
                source_node_id=_optional_identifier(metadata.get("source_node_id")),
                source_track_id=_optional_identifier(metadata.get("source_track_id")),
                frame_id=frame_id,
                metadata=safe_metadata,
            )
        )
    if detections and any(
        abs(item.measurement_timestamp - frame_timestamp) > 1.0e-9
        for item in detections
    ):
        raise ValueError("D1 track batch must share one state-valid timestamp")
    return frame_timestamp, detections


def assert_online_metadata_truth_free(metadata: Mapping[str, Any]) -> None:
    """Reject evaluator identity recursively at the new online contract edge."""

    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for raw_key, item in value.items():
                key = _normalized_key(raw_key)
                child_path = f"{path}.{raw_key}"
                if _forbidden_online_key(key):
                    violations.append(child_path)
                else:
                    visit(item, child_path)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(metadata, "metadata")
    if violations:
        raise ValueError(
            "online Detection3D metadata contains evaluator or external identity: "
            + ", ".join(sorted(set(violations)))
        )


def _forbidden_online_key(key: str) -> bool:
    collapsed = key.replace("_", "")
    if (
        key == "truth"
        or key.startswith("truth_")
        or key.endswith("_truth_id")
        or "ground_truth" in key
        or "offline_truth" in key
        or "sim_truth" in key
        or "truthid" in collapsed
        or "groundtruth" in collapsed
    ):
        return True
    if key in {
        "airsim_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "entity_id",
        "entity_ids",
        "target_id",
        "target_ids",
        "global_track_id",
        "canonical_id",
    }:
        return True
    if "globaltrackid" in collapsed or "canonicaltrackid" in collapsed:
        return True
    identity_suffixes = ("id", "ids", "identity", "name", "uuid")
    return any(
        collapsed.startswith(domain) and collapsed.endswith(identity_suffixes)
        for domain in ("actor", "object", "entity", "target", "airsim")
    )


def _normalized_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _finite_vector(value: Any, size: int, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite vector with shape ({size},)")
    return array.copy()


def _finite_timestamp(value: Any, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _optional_identifier(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _read(value: Any, name: str, default: Any = ...) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
    elif hasattr(value, name):
        return getattr(value, name)
    if default is ...:
        raise ValueError(f"missing required field: {name}")
    return default


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_ready(item) for item in value]
    return value
