"""Versioned offline-truth JSONL contract for D2 replay evaluation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
import json
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment


OFFLINE_TRUTH_SCHEMA_VERSION = "d2-offline-truth-label/v1"


@dataclass(frozen=True, slots=True)
class OfflineTruthLabel:
    """One target's evaluation-only position at one replay frame."""

    episode_id: str
    frame_index: int
    timestamp: float
    truth_id: str
    position: tuple[float, float]
    match_annotation: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = OFFLINE_TRUTH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        episode_id = str(self.episode_id).strip()
        truth_id = str(self.truth_id).strip()
        frame_index = int(self.frame_index)
        timestamp = float(self.timestamp)
        position = tuple(float(value) for value in self.position)
        if self.schema_version != OFFLINE_TRUTH_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported offline truth schema: {self.schema_version!r}"
            )
        if not episode_id:
            raise ValueError("episode_id must not be empty")
        if frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        if not isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        if not truth_id:
            raise ValueError("truth_id must not be empty")
        if len(position) != 2 or not all(isfinite(value) for value in position):
            raise ValueError("position must contain two finite coordinates")
        object.__setattr__(self, "episode_id", episode_id)
        object.__setattr__(self, "frame_index", frame_index)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "truth_id", truth_id)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "match_annotation", dict(self.match_annotation))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "OfflineTruthLabel":
        return cls(
            schema_version=str(
                payload.get("schema_version", OFFLINE_TRUTH_SCHEMA_VERSION)
            ),
            episode_id=str(payload["episode_id"]),
            frame_index=int(payload["frame_index"]),
            timestamp=float(payload["timestamp"]),
            truth_id=str(payload["truth_id"]),
            position=tuple(payload["position"]),
            match_annotation=dict(payload.get("match_annotation", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "frame_index": self.frame_index,
            "timestamp": self.timestamp,
            "truth_id": self.truth_id,
            "position": list(self.position),
        }
        if self.match_annotation:
            payload["match_annotation"] = dict(self.match_annotation)
        return payload


def write_offline_truth_labels_jsonl(
    path: str | Path,
    labels: Iterable[OfflineTruthLabel | Mapping[str, Any]],
) -> None:
    """Write deterministic, one-record-per-target-per-frame truth JSONL."""

    records = _coerce_unique_labels(labels)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(record.to_dict(), sort_keys=True, separators=(",", ":"))
            + "\n"
            for record in records
        )
    )


def load_offline_truth_labels_jsonl(path: str | Path) -> list[OfflineTruthLabel]:
    """Load and validate the frozen D2 offline-truth JSONL contract."""

    records = []
    for line_number, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        payload = json.loads(line)
        if not isinstance(payload, Mapping):
            raise ValueError(f"offline truth line {line_number} must be an object")
        records.append(OfflineTruthLabel.from_mapping(payload))
    if not records:
        raise ValueError("offline truth JSONL contains no labels")
    return _coerce_unique_labels(records)


def extract_offline_truth_labels(
    frames: Sequence[Mapping[str, Any]],
    *,
    episode_id: str | None = None,
) -> list[OfflineTruthLabel]:
    """Extract evaluation labels from a governed fixture before truth stripping."""

    labels: list[OfflineTruthLabel] = []
    for default_frame_index, frame in enumerate(frames):
        frame_index = _frame_index(frame, default_frame_index)
        timestamp = _frame_timestamp(frame, frame_index)
        current_episode_id = episode_id or _frame_episode_id(frame)
        if current_episode_id is None:
            raise ValueError("episode_id is required for offline truth extraction")
        truth_states = frame.get("offline_truth_states", {})
        if not isinstance(truth_states, Mapping):
            raise ValueError("offline_truth_states must be a mapping")
        observed_by_truth: dict[str, str] = {}
        for detection in frame.get("detections", []):
            if not isinstance(detection, Mapping):
                continue
            truth_id = detection.get(
                "offline_truth_label", detection.get("offline_truth_id")
            )
            detection_id = detection.get("detection_id")
            if truth_id is not None and detection_id is not None:
                observed_by_truth[str(truth_id)] = str(detection_id)
        for truth_id, state in sorted(truth_states.items(), key=lambda item: str(item[0])):
            position = np.asarray(state, dtype=float).reshape(-1)
            annotation: dict[str, Any] = {
                "observed": str(truth_id) in observed_by_truth,
            }
            if str(truth_id) in observed_by_truth:
                annotation["source_detection_id"] = observed_by_truth[str(truth_id)]
            labels.append(
                OfflineTruthLabel(
                    episode_id=current_episode_id,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    truth_id=str(truth_id),
                    position=(float(position[0]), float(position[1])),
                    match_annotation=annotation,
                )
            )
    return _coerce_unique_labels(labels)


def strip_offline_truth_from_frames(
    frames: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return replay frames with all identity/truth evidence recursively removed."""

    return [_strip_truth_payload(deepcopy(dict(frame))) for frame in frames]


def evaluation_frames_with_offline_truth(
    frames: Sequence[Mapping[str, Any]],
    labels: Iterable[OfflineTruthLabel | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build an evaluator-only view without mutating the online replay frames."""

    clean_frames = strip_offline_truth_from_frames(frames)
    records = _coerce_unique_labels(labels)
    records_by_frame: dict[tuple[str, int], list[OfflineTruthLabel]] = defaultdict(list)
    records_by_truth: dict[tuple[str, str], list[OfflineTruthLabel]] = defaultdict(list)
    for record in records:
        records_by_frame[(record.episode_id, record.frame_index)].append(record)
        records_by_truth[(record.episode_id, record.truth_id)].append(record)
    states = _derived_truth_states(records_by_truth)
    consumed_frame_keys: set[tuple[str, int]] = set()

    for default_frame_index, frame in enumerate(clean_frames):
        frame_index = _frame_index(frame, default_frame_index)
        episode_id = _frame_episode_id(frame)
        if episode_id is None:
            raise ValueError("every replay frame must carry episode_id")
        timestamp = _frame_timestamp(frame, frame_index)
        frame_records = records_by_frame.get((episode_id, frame_index), [])
        consumed_frame_keys.add((episode_id, frame_index))
        for record in frame_records:
            if abs(record.timestamp - timestamp) > 1.0e-9:
                raise ValueError(
                    "offline truth timestamp does not match replay frame: "
                    f"episode={episode_id} frame={frame_index}"
                )
        frame["truth_ids_present"] = [record.truth_id for record in frame_records]
        frame["offline_truth_states"] = {
            record.truth_id: states[(record.episode_id, record.frame_index, record.truth_id)]
            for record in frame_records
        }
        detections = frame.get("detections", [])
        detections_by_id = {
            str(item.get("detection_id")): item
            for item in detections
            if isinstance(item, dict) and item.get("detection_id") is not None
        }
        matched_truth_ids: set[str] = set()
        matched_detection_ids: set[int] = set()
        for record in frame_records:
            annotation = record.match_annotation
            source_detection_id = annotation.get("source_detection_id")
            detection_index = annotation.get("detection_index")
            detection: dict[str, Any] | None = None
            if source_detection_id is not None:
                candidate = detections_by_id.get(str(source_detection_id))
                if candidate is None:
                    raise ValueError(
                        f"offline truth references unknown detection {source_detection_id!r}"
                    )
                detection = candidate
            elif detection_index is not None:
                index = int(detection_index)
                if index < 0 or index >= len(detections):
                    raise ValueError("offline truth detection_index is out of range")
                candidate = detections[index]
                if not isinstance(candidate, dict):
                    raise ValueError("offline truth matched detection must be a mapping")
                detection = candidate
            if detection is None:
                continue
            _attach_truth_to_detection(detection, record, states)
            matched_truth_ids.add(record.truth_id)
            matched_detection_ids.add(id(detection))
        fallback_records = [
            record
            for record in frame_records
            if record.truth_id not in matched_truth_ids
            and bool(record.match_annotation.get("offline_only", False))
        ]
        fallback_detections = [
            detection
            for detection in detections
            if isinstance(detection, dict)
            and id(detection) not in matched_detection_ids
            and _detection_position(detection) is not None
        ]
        if fallback_records and fallback_detections:
            cost_matrix = np.array(
                [
                    [
                        float(
                            np.linalg.norm(
                                np.asarray(record.position, dtype=float)
                                - _detection_position(detection)
                            )
                        )
                        for detection in fallback_detections
                    ]
                    for record in fallback_records
                ],
                dtype=float,
            )
            record_indices, detection_indices = linear_sum_assignment(cost_matrix)
            for record_index, detection_index in zip(
                record_indices, detection_indices, strict=True
            ):
                record = fallback_records[int(record_index)]
                maximum_error = float(
                    record.match_annotation.get("max_position_error_m", 25.0)
                )
                if cost_matrix[record_index, detection_index] > maximum_error:
                    continue
                detection = fallback_detections[int(detection_index)]
                _attach_truth_to_detection(detection, record, states)
                detection["offline_truth_match_method"] = "position_hungarian"
    unmatched_frame_keys = set(records_by_frame) - consumed_frame_keys
    if unmatched_frame_keys:
        raise ValueError(
            "offline truth contains records for unknown replay frames: "
            f"{sorted(unmatched_frame_keys)!r}"
        )
    return clean_frames


def _attach_truth_to_detection(
    detection: dict[str, Any],
    record: OfflineTruthLabel,
    states: Mapping[tuple[str, int, str], list[float]],
) -> None:
    truth_state = states[(record.episode_id, record.frame_index, record.truth_id)]
    detection["offline_truth_label"] = record.truth_id
    detection["offline_truth_position"] = list(record.position)
    detection["offline_truth_state"] = truth_state


def _detection_position(detection: Mapping[str, Any]) -> np.ndarray | None:
    try:
        position = np.asarray(detection.get("position"), dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if position.size < 2 or not np.all(np.isfinite(position[:2])):
        return None
    return position[:2]


def _coerce_unique_labels(
    labels: Iterable[OfflineTruthLabel | Mapping[str, Any]],
) -> list[OfflineTruthLabel]:
    records = [
        label
        if isinstance(label, OfflineTruthLabel)
        else OfflineTruthLabel.from_mapping(label)
        for label in labels
    ]
    records.sort(key=lambda item: (item.episode_id, item.frame_index, item.truth_id))
    keys = [(item.episode_id, item.frame_index, item.truth_id) for item in records]
    if len(keys) != len(set(keys)):
        raise ValueError("offline truth labels contain duplicate episode/frame/truth_id")
    return records


def _derived_truth_states(
    grouped: Mapping[tuple[str, str], Sequence[OfflineTruthLabel]],
) -> dict[tuple[str, int, str], list[float]]:
    states: dict[tuple[str, int, str], list[float]] = {}
    for (episode_id, truth_id), raw_records in grouped.items():
        records = sorted(raw_records, key=lambda item: (item.timestamp, item.frame_index))
        for index, record in enumerate(records):
            if len(records) == 1:
                velocity = np.zeros(2, dtype=float)
            else:
                lower = records[max(0, index - 1)]
                upper = records[min(len(records) - 1, index + 1)]
                delta_t = upper.timestamp - lower.timestamp
                velocity = (
                    np.zeros(2, dtype=float)
                    if abs(delta_t) <= 1.0e-12
                    else (
                        np.asarray(upper.position, dtype=float)
                        - np.asarray(lower.position, dtype=float)
                    )
                    / delta_t
                )
            states[(episode_id, record.frame_index, truth_id)] = [
                record.position[0],
                record.position[1],
                float(velocity[0]),
                float(velocity[1]),
            ]
    return states


def _frame_episode_id(frame: Mapping[str, Any]) -> str | None:
    value = frame.get("episode_id")
    metadata = frame.get("replay_metadata")
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get("episode_id")
    return None if value is None else str(value)


def _frame_index(frame: Mapping[str, Any], default: int) -> int:
    value = frame.get("frame_index")
    metadata = frame.get("replay_metadata")
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get("frame_index")
    return int(default if value is None else value)


def _frame_timestamp(frame: Mapping[str, Any], default: int) -> float:
    value = frame.get("measurement_timestamp", frame.get("timestamp"))
    metadata = frame.get("replay_metadata")
    if value is None and isinstance(metadata, Mapping):
        value = metadata.get("measurement_timestamp", metadata.get("timestamp"))
    return float(default if value is None else value)


_TRUTH_KEYS = {
    "actor_name",
    "ground_truth",
    "ground_truth_id",
    "ground_truth_position",
    "ground_truth_state",
    "offline_truth",
    "offline_truth_id",
    "offline_truth_label",
    "offline_truth_labels",
    "offline_truth_position",
    "offline_truth_state",
    "offline_truth_states",
    "sim_truth_id",
    "truth_id",
    "truth_ids",
    "truth_ids_present",
    "truth_label",
    "truth_labels",
    "truth_offline_labels",
    "truth_position",
    "truth_state",
}


def _strip_truth_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_truth_payload(item)
            for key, item in value.items()
            if str(key).lower() not in _TRUTH_KEYS
        }
    if isinstance(value, list):
        return [_strip_truth_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_truth_payload(item) for item in value]
    return value
