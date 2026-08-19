"""Versioned online and offline records shared by the three experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]
Vector6 = tuple[float, float, float, float, float, float]
Matrix6 = tuple[Vector6, Vector6, Vector6, Vector6, Vector6, Vector6]

SOURCE_CUE_SCHEMA = "center-terminal-source-cue-v1"
LOCAL_TRACK_SCHEMA = "center-terminal-local-visual-track-v1"
SEARCH_HANDOVER_SCHEMA = "center-terminal-search-handover-v1"
ASSOCIATION_SCHEMA = "center-terminal-association-v1"
TRUTH_LABEL_SCHEMA = "center-terminal-source-cue-truth-v1"


def _text(value: str, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _probability(value: float, name: str) -> float:
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be within [0, 1]")
    return result


@dataclass(frozen=True)
class SourceCueRecord:
    """Anonymous center cue exposed to online search and registration."""

    source_track_id: str
    position_ned_m: Vector3
    velocity_ned_mps: Vector3
    covariance_6x6: Matrix6
    measurement_timestamp: float
    arrival_timestamp: float
    valid_until: float
    existence_probability: float = 0.8
    source_kind: str = "dual_optical_fixture"
    schema_version: str = SOURCE_CUE_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)
    def __post_init__(self) -> None:
        object.__setattr__(self, "source_track_id", _text(self.source_track_id, "source_track_id"))
        if len(self.position_ned_m) != 3 or len(self.velocity_ned_mps) != 3:
            raise ValueError("position and velocity must contain three components")
        if len(self.covariance_6x6) != 6 or any(len(row) != 6 for row in self.covariance_6x6):
            raise ValueError("covariance_6x6 must be 6 by 6")
        if float(self.arrival_timestamp) < float(self.measurement_timestamp):
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")
        if float(self.valid_until) < float(self.measurement_timestamp):
            raise ValueError("valid_until cannot precede measurement_timestamp")
        object.__setattr__(
            self,
            "existence_probability",
            _probability(self.existence_probability, "existence_probability"),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_online_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceCueTruthLabel:
    """Offline-only label used to verify the controlled 80/80 fixture."""

    source_track_id: str
    truth_target_id: str | None
    is_correct_source: bool
    corruption_type: str
    schema_version: str = TRUTH_LABEL_SCHEMA


@dataclass(frozen=True)
class LocalVisualTrackRecord:
    """Anonymous camera-local tracklet produced from AirSim detections."""

    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    bbox_xyxy: tuple[float, float, float, float]
    center_px: Vector2
    ray_origin_ned_m: Vector3
    ray_direction_ned: Vector3
    camera_yaw_pitch_roll_deg: Vector3
    recognized: bool
    recognition_extent_px: float
    track_quality: float = 1.0
    schema_version: str = LOCAL_TRACK_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "camera_id", _text(self.camera_id, "camera_id"))
        object.__setattr__(self, "local_track_id", _text(self.local_track_id, "local_track_id"))
        x1, y1, x2, y2 = (float(value) for value in self.bbox_xyxy)
        if x2 < x1 or y2 < y1:
            raise ValueError("bbox_xyxy must have non-negative width and height")
        if float(self.arrival_timestamp) < float(self.measurement_timestamp):
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")
        object.__setattr__(self, "track_quality", _probability(self.track_quality, "track_quality"))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_online_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchHandoverRecord:
    """Search result handed to the center-to-terminal association experiment."""

    search_cell_id: str
    camera_id: str
    local_track_id: str
    measurement_timestamp: float
    arrival_timestamp: float
    candidate_source_track_ids: tuple[str, ...]
    confirmation_count: int
    status: str
    schema_version: str = SEARCH_HANDOVER_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssociationRecord:
    """Auditable center-to-local or local-to-local association decision."""

    association_id: str
    association_type: str
    left_track_id: str
    right_track_id: str | None
    measurement_timestamp: float
    arrival_timestamp: float
    score: float
    decision_state: str
    reject_reasons: tuple[str, ...] = ()
    geometry_residual: float | None = None
    confirmation_count: int = 0
    schema_version: str = ASSOCIATION_SCHEMA
    metadata: Mapping[str, Any] = field(default_factory=dict)
