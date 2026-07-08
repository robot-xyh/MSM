"""Offline AirSim-style replay and threshold calibration helpers for D2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

import numpy as np

from .associators import GNNHungarianAssociator
from .dry_run_adapter import run_airsim_dry_run_association
from .metrics import RiskThresholds, classify_risk_summary
from .models import AssociationRiskSummary
from .tracker import Tracker


@dataclass(slots=True)
class ReplayAssociationReport:
    """JSON-ready D2 association replay report."""

    replay_name: str
    frame_count: int
    target_count: int
    global_track_ids: list[str]
    metrics: dict[str, Any]
    association_logs: list[dict[str, Any]]
    risk_summary: dict[str, Any]
    threshold_sensitivity: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_name": self.replay_name,
            "frame_count": self.frame_count,
            "target_count": self.target_count,
            "global_track_ids": list(self.global_track_ids),
            "metrics": _json_ready(self.metrics),
            "association_logs": _json_ready(self.association_logs),
            "risk_summary": _json_ready(self.risk_summary),
            "threshold_sensitivity": _json_ready(self.threshold_sensitivity),
        }


def load_airsim_replay_frames(path: str | Path) -> list[dict[str, Any]]:
    """Load offline AirSim-style replay frames from JSON or JSONL.

    Supported payloads are a list of frame dicts, a JSON object with a
    ``frames`` key, or JSONL records containing either a frame directly or a
    nested ``frame``/``d2_frame``/``airsim_frame`` payload. Non-frame JSONL
    records are ignored so mixed episode logs can be filtered by D2.
    """

    replay_path = Path(path)
    raw_text = replay_path.read_text()
    if replay_path.suffix.lower() == ".jsonl":
        records = [
            json.loads(line)
            for line in raw_text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        frames = [frame for record in records if (frame := _coerce_frame(record))]
    else:
        payload = json.loads(raw_text)
        frames = _frames_from_payload(payload)
    if not frames:
        raise ValueError(f"no AirSim-style replay frames found in {replay_path}")
    return [dict(frame) for frame in frames]


def run_airsim_replay_association(
    frames: Iterable[Any],
    *,
    replay_name: str = "airsim_replay",
    tracker: Tracker | None = None,
    risk_thresholds: RiskThresholds | None = None,
    default_position_variance: float = 1.0,
    gate_thresholds: Sequence[float] | None = None,
) -> ReplayAssociationReport:
    """Run D2 association on offline replay frames and return a stable report."""

    frame_list = list(frames)
    result = run_airsim_dry_run_association(
        frame_list,
        tracker=tracker,
        default_position_variance=default_position_variance,
    )
    thresholds = risk_thresholds if risk_thresholds is not None else RiskThresholds()
    association_logs = result.association_logs
    risk_summary = summarize_replay_risk(
        association_logs,
        result.metrics,
        thresholds=thresholds,
    )
    sensitivity = (
        run_threshold_sensitivity(
            frame_list,
            gate_thresholds=gate_thresholds,
            risk_thresholds=[thresholds],
            default_position_variance=default_position_variance,
        )
        if gate_thresholds is not None
        else []
    )
    return ReplayAssociationReport(
        replay_name=replay_name,
        frame_count=len(frame_list),
        target_count=_target_count(frame_list),
        global_track_ids=result.global_track_ids,
        metrics=dict(result.metrics),
        association_logs=association_logs,
        risk_summary=risk_summary,
        threshold_sensitivity=sensitivity,
    )


def run_threshold_sensitivity(
    frames: Iterable[Any],
    *,
    gate_thresholds: Sequence[float] | None = None,
    risk_thresholds: Sequence[RiskThresholds] | None = None,
    feature_weight: float = 6.0,
    default_position_variance: float = 1.0,
) -> list[dict[str, Any]]:
    """Evaluate replay metrics and risk breakdown across threshold profiles."""

    frame_list = list(frames)
    gates = tuple(gate_thresholds) if gate_thresholds is not None else (5.99, 9.21, 13.82)
    profiles = tuple(risk_thresholds) if risk_thresholds is not None else (RiskThresholds(),)
    rows: list[dict[str, Any]] = []
    for gate_threshold in gates:
        for thresholds in profiles:
            tracker = Tracker(
                associator=GNNHungarianAssociator(
                    gate_threshold=float(gate_threshold),
                    feature_weight=feature_weight,
                )
            )
            result = run_airsim_dry_run_association(
                frame_list,
                tracker=tracker,
                default_position_variance=default_position_variance,
            )
            risk_summary = summarize_replay_risk(
                result.association_logs,
                result.metrics,
                thresholds=thresholds,
            )
            rows.append(
                {
                    "gate_threshold": float(gate_threshold),
                    "risk_profile": thresholds.profile_name,
                    "frame_count": len(frame_list),
                    "target_count": _target_count(frame_list),
                    "id_switch_count": result.metrics["id_switch_count"],
                    "track_continuity": result.metrics["track_continuity"],
                    "duplicate_assignment_count": result.metrics[
                        "duplicate_assignment_count"
                    ],
                    "risk_summary": risk_summary,
                }
            )
    return rows


def summarize_replay_risk(
    association_logs: Iterable[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    *,
    thresholds: RiskThresholds | None = None,
) -> dict[str, Any]:
    """Summarize soft and hard D2 risk evidence for replay/calibration."""

    active_thresholds = thresholds if thresholds is not None else RiskThresholds()
    breakdowns = []
    for log in association_logs:
        risk_payload = log.get("risk_summary")
        if risk_payload is None:
            continue
        breakdowns.append(
            classify_risk_summary(
                _risk_summary_from_payload(risk_payload),
                thresholds=active_thresholds,
            )
        )

    soft_reasons = sorted(
        {reason for item in breakdowns for reason in item.soft_risk_reasons}
    )
    hard_reasons = sorted(
        {reason for item in breakdowns for reason in item.hard_risk_reasons}
    )
    return {
        "thresholds": active_thresholds.to_dict(),
        "soft_risk_frame_count": sum(1 for item in breakdowns if item.has_soft_risk),
        "hard_risk_frame_count": sum(1 for item in breakdowns if item.has_hard_risk),
        "max_soft_risk_score": max(
            (item.soft_risk_score for item in breakdowns), default=0.0
        ),
        "max_hard_risk_score": max(
            (item.hard_risk_score for item in breakdowns), default=0.0
        ),
        "soft_risk_reasons": soft_reasons,
        "hard_risk_reasons": hard_reasons,
        "latest_breakdown": breakdowns[-1].to_dict() if breakdowns else None,
        "id_switch_count": int(metrics.get("id_switch_count", 0)),
        "track_continuity": float(metrics.get("track_continuity", 0.0)),
        "duplicate_assignment_count": int(
            metrics.get("duplicate_assignment_count", 0)
        ),
    }


def write_replay_association_report(
    report: ReplayAssociationReport,
    path: str | Path,
) -> None:
    """Write a JSON replay association report."""

    Path(path).write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True))


def write_association_logs_jsonl(
    association_logs: Iterable[Mapping[str, Any]],
    path: str | Path,
) -> None:
    """Write per-frame D2 association logs as JSONL."""

    lines = [json.dumps(_json_ready(dict(log)), sort_keys=True) for log in association_logs]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""))


def _frames_from_payload(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        for key in ("frames", "replay_frames", "records"):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return [frame for item in value if (frame := _coerce_frame(item))]
        frame = _coerce_frame(payload)
        return [frame] if frame is not None else []
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [frame for item in payload if (frame := _coerce_frame(item))]
    return []


def _coerce_frame(record: Any) -> Mapping[str, Any] | None:
    if not isinstance(record, Mapping):
        return None
    if _is_frame(record):
        return record
    for key in ("frame", "d2_frame", "airsim_frame", "association_frame"):
        value = record.get(key)
        if isinstance(value, Mapping) and _is_frame(value):
            return value
    payload = record.get("payload")
    if isinstance(payload, Mapping) and _is_frame(payload):
        return payload
    return None


def _is_frame(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("detections", "tracks", "objects"))


def _target_count(frames: Sequence[Any]) -> int:
    truth_ids: set[str] = set()
    for frame in frames:
        truth_ids.update(_truth_ids_for_frame(frame))
    return len(truth_ids)


def _truth_ids_for_frame(frame: Any) -> set[str]:
    truth_ids: set[str] = set()
    explicit = _first_present(frame, ("truth_ids_present", "truth_ids"), None)
    if explicit is not None:
        truth_ids.update(str(value) for value in explicit if value is not None)
    for item in _frame_items(frame):
        truth_id = _first_present(
            item,
            ("truth_id", "ground_truth_id", "object_id", "name"),
            None,
        )
        if truth_id is not None:
            truth_ids.add(str(truth_id))
    return truth_ids


def _frame_items(frame: Any) -> list[Any]:
    if isinstance(frame, Mapping):
        for key in ("detections", "tracks", "objects"):
            if key in frame:
                return list(frame[key])
        return []
    for key in ("detections", "tracks", "objects"):
        value = getattr(frame, key, None)
        if value is not None:
            return list(value)
    return []


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


def _risk_summary_from_payload(payload: Mapping[str, Any]) -> AssociationRiskSummary:
    return AssociationRiskSummary(
        timestamp=float(payload.get("timestamp", 0.0)),
        source_node_id=_optional_string(payload.get("source_node_id")),
        link_type=_optional_string(payload.get("link_type")),
        d5_disagreement_count=int(payload.get("d5_disagreement_count", 0)),
        duplicate_track_risk=float(payload.get("duplicate_track_risk", 0.0)),
        association_ambiguity=float(payload.get("association_ambiguity", 0.0)),
        covariance_overlap_rate=float(payload.get("covariance_overlap_rate", 0.0)),
        metadata=dict(payload.get("metadata", {})),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value
