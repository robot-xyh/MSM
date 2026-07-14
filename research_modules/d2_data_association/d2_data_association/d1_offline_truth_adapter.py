"""Adapter for evaluator-only D1 AirSim offline-truth JSON sidecars."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
from typing import Any

from .offline_truth import OfflineTruthLabel


D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION = "d1.airsim_offline_truth.v1"
D1_OFFLINE_TRUTH_ALIGNMENT_SCHEMA_VERSION = "d2.d1_offline_truth_alignment.v1"
D1_OFFLINE_TRUTH_TIMESTAMP_TOLERANCE_S = 1.0e-9


@dataclass(frozen=True, slots=True)
class D1OfflineTruthAlignmentResult:
    """Evaluator labels plus an identity-free sparse-alignment audit."""

    labels: tuple[OfflineTruthLabel, ...]
    summary: Mapping[str, Any]

    def to_dict(self, *, include_labels: bool = False) -> dict[str, Any]:
        result = {"summary": dict(self.summary)}
        if include_labels:
            result["labels"] = [label.to_dict() for label in self.labels]
        return result


def is_d1_airsim_offline_truth_payload(payload: Any) -> bool:
    return (
        isinstance(payload, Mapping)
        and payload.get("schema_version")
        == D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION
    )


def load_d1_airsim_offline_truth_json(
    path: str | Path,
    *,
    replay_frames: Sequence[Mapping[str, Any]],
) -> list[OfflineTruthLabel]:
    """Convert a D1 sidecar to D2 evaluator-only labels.

    The D1 payload carries 3D NED positions and source payload indices.  D2
    associates in horizontal N/E, so the first two coordinates are retained
    and Down is preserved only as an audit annotation.  Frame identity comes
    from timestamp alignment with the already governed D2 replay.
    """

    return list(
        load_d1_airsim_offline_truth_alignment_json(
            path,
            replay_frames=replay_frames,
        ).labels
    )


def load_d1_airsim_offline_truth_alignment_json(
    path: str | Path,
    *,
    replay_frames: Sequence[Mapping[str, Any]],
) -> D1OfflineTruthAlignmentResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return align_d1_airsim_offline_truth(
        payload,
        replay_frames=replay_frames,
    )


def d2_labels_from_d1_airsim_offline_truth(
    payload: Mapping[str, Any],
    *,
    replay_frames: Sequence[Mapping[str, Any]],
) -> list[OfflineTruthLabel]:
    return list(
        align_d1_airsim_offline_truth(
            payload,
            replay_frames=replay_frames,
        ).labels
    )


def align_d1_airsim_offline_truth(
    payload: Mapping[str, Any],
    *,
    replay_frames: Sequence[Mapping[str, Any]],
) -> D1OfflineTruthAlignmentResult:
    """Align only exact replay timestamps and audit valid unmatched samples."""

    if not is_d1_airsim_offline_truth_payload(payload):
        raise ValueError("payload is not a supported D1 AirSim offline truth sidecar")
    if payload.get("evaluator_only") is not True:
        raise ValueError("D1 AirSim offline truth sidecar must be evaluator_only")
    if str(payload.get("frame_id", "")).strip().lower() != "ned":
        raise ValueError("D1 AirSim offline truth sidecar frame_id must be NED")
    samples = payload.get("samples")
    if not isinstance(samples, Sequence) or isinstance(
        samples, (str, bytes, bytearray)
    ):
        raise ValueError("D1 AirSim offline truth samples must be a sequence")
    if not samples:
        raise ValueError("D1 AirSim offline truth sidecar contains no samples")

    frame_index = _build_replay_frame_index(replay_frames)
    labels: list[OfflineTruthLabel] = []
    seen: set[tuple[str, int, str]] = set()
    seen_source_samples: set[tuple[float, int | None, str]] = set()
    source_truth_ids: set[str] = set()
    matched_truth_ids: set[str] = set()
    unmatched_samples: list[dict[str, Any]] = []
    for sample_index, raw_sample in enumerate(samples):
        if not isinstance(raw_sample, Mapping):
            raise ValueError(f"D1 offline truth sample {sample_index} must be an object")
        truth_id = str(raw_sample.get("truth_id", "")).strip()
        if not truth_id:
            raise ValueError(f"D1 offline truth sample {sample_index} has empty truth_id")
        timestamp = _finite_float(
            raw_sample.get("timestamp"),
            field=f"sample {sample_index} timestamp",
        )
        if raw_sample.get("position_availability") != "available":
            raise ValueError(
                f"D1 offline truth sample {sample_index} position is unavailable"
            )
        position = raw_sample.get("position_ned")
        if not isinstance(position, Sequence) or isinstance(
            position, (str, bytes, bytearray)
        ):
            raise ValueError(
                f"D1 offline truth sample {sample_index} position_ned must be a sequence"
            )
        if len(position) != 3:
            raise ValueError(
                f"D1 offline truth sample {sample_index} position_ned must have 3 values"
            )
        position_ned = tuple(
            _finite_float(value, field=f"sample {sample_index} position_ned")
            for value in position
        )
        source_payload_index = raw_sample.get("source_payload_index")
        source_index = (
            None if source_payload_index is None else int(source_payload_index)
        )
        source_key = (timestamp, source_index, truth_id)
        if source_key in seen_source_samples:
            raise ValueError("D1 offline truth sidecar contains duplicate source sample")
        seen_source_samples.add(source_key)
        source_truth_ids.add(truth_id)
        match = _match_replay_frame(
            frame_index,
            timestamp=timestamp,
            source_payload_index=source_index,
        )
        if match is None:
            unmatched_samples.append(
                {
                    "sample_index": sample_index,
                    "timestamp": timestamp,
                    "source_payload_index": source_index,
                    "reason": "no_governed_replay_frame_within_frozen_tolerance",
                }
            )
            continue
        episode_id, matched_frame_index = match
        key = (episode_id, matched_frame_index, truth_id)
        if key in seen:
            raise ValueError(
                "D1 offline truth sidecar contains duplicate episode/frame/truth_id"
            )
        seen.add(key)
        matched_truth_ids.add(truth_id)
        labels.append(
            OfflineTruthLabel(
                episode_id=episode_id,
                frame_index=matched_frame_index,
                timestamp=timestamp,
                truth_id=truth_id,
                position=(position_ned[0], position_ned[1]),
                match_annotation={
                    "offline_only": True,
                    "source_schema_version": D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
                    "source_frame_id": "ned",
                    "source_position_down_m": position_ned[2],
                    "source_payload_index": source_index,
                    "projection": "ned_3d_to_horizontal_ne",
                },
            )
        )
    labels.sort(key=lambda label: (label.episode_id, label.frame_index, label.truth_id))
    declared_sample_count = payload.get("sample_count")
    if declared_sample_count is not None and int(declared_sample_count) != len(samples):
        raise ValueError("D1 offline truth sample_count does not match samples")
    declared_target_count = payload.get("target_count")
    if declared_target_count is not None and int(declared_target_count) != len(source_truth_ids):
        raise ValueError("D1 offline truth target_count does not match source samples")
    if labels and unmatched_samples:
        availability = "partial"
    elif labels:
        availability = "complete"
    else:
        availability = "unavailable"
    summary = {
        "schema_version": D1_OFFLINE_TRUTH_ALIGNMENT_SCHEMA_VERSION,
        "source_schema_version": D1_AIRSIM_OFFLINE_TRUTH_SCHEMA_VERSION,
        "matching_policy": "exact_timestamp_within_frozen_tolerance_no_nearest_neighbor",
        "timestamp_tolerance_s": D1_OFFLINE_TRUTH_TIMESTAMP_TOLERANCE_S,
        "availability": availability,
        "truth_metrics_input_available": bool(labels),
        "source_sample_count": len(samples),
        "matched_sample_count": len(labels),
        "unmatched_sample_count": len(unmatched_samples),
        "source_target_count": len(source_truth_ids),
        "matched_target_count": len(matched_truth_ids),
        "replay_frame_count": len(replay_frames),
        "matched_replay_frame_count": len(
            {(label.episode_id, label.frame_index) for label in labels}
        ),
        "unmatched_reason_counts": {
            "no_governed_replay_frame_within_frozen_tolerance": len(
                unmatched_samples
            )
        }
        if unmatched_samples
        else {},
        "unmatched_samples": unmatched_samples,
        "online_truth_injected": False,
    }
    return D1OfflineTruthAlignmentResult(labels=tuple(labels), summary=summary)


def _build_replay_frame_index(
    replay_frames: Sequence[Mapping[str, Any]],
) -> dict[float, list[tuple[str, int]]]:
    if not replay_frames:
        raise ValueError("D1 offline truth adapter requires governed replay frames")
    result: dict[float, list[tuple[str, int]]] = {}
    for default_index, frame in enumerate(replay_frames):
        timestamp = _finite_float(
            frame.get("measurement_timestamp", frame.get("timestamp")),
            field=f"replay frame {default_index} timestamp",
        )
        metadata = frame.get("replay_metadata", {})
        metadata = metadata if isinstance(metadata, Mapping) else {}
        episode_id = str(
            metadata.get("episode_id", frame.get("episode_id", ""))
        ).strip()
        if not episode_id:
            raise ValueError(f"replay frame {default_index} has no episode_id")
        raw_frame_index = frame.get(
            "frame_index", metadata.get("frame_index", default_index)
        )
        canonical_frame_index = int(raw_frame_index)
        if canonical_frame_index < 0:
            raise ValueError("replay frame_index must be non-negative")
        result.setdefault(timestamp, []).append((episode_id, canonical_frame_index))
    return result


def _match_replay_frame(
    frame_index: Mapping[float, Sequence[tuple[str, int]]],
    *,
    timestamp: float,
    source_payload_index: int | None,
) -> tuple[str, int] | None:
    candidates = [
        candidate
        for frame_timestamp, entries in frame_index.items()
        if abs(frame_timestamp - timestamp)
        <= D1_OFFLINE_TRUTH_TIMESTAMP_TOLERANCE_S
        for candidate in entries
    ]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if source_payload_index is not None:
        indexed = [
            candidate for candidate in candidates if candidate[1] == source_payload_index
        ]
        if len(indexed) == 1:
            return indexed[0]
    raise ValueError(
        f"D1 offline truth timestamp {timestamp} maps to multiple replay frames"
    )


def _finite_float(value: Any, *, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result
