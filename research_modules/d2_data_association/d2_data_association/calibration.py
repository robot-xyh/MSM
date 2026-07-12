"""Deterministic multi-seed dense-crossing calibration for D2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .associators import GNNHungarianAssociator
from .metrics import RiskThresholds
from .offline_truth import (
    OFFLINE_TRUTH_SCHEMA_VERSION,
    extract_offline_truth_labels,
    strip_offline_truth_from_frames,
    write_offline_truth_labels_jsonl,
)
from .replay import (
    run_airsim_replay_association,
    summarize_multi_seed_risk_calibration,
)
from .replay_governance import build_dense_crossing_replay_fixture
from .tracker import Tracker


CALIBRATION_SCHEMA_VERSION = "d2-dense-crossing-calibration/v1"


@dataclass(frozen=True, slots=True)
class GateCalibrationProfile:
    profile_name: str = "d2_dense_crossing_gate"
    profile_version: str = "v1"
    mahalanobis_threshold: float = 9.21

    def __post_init__(self) -> None:
        if not self.profile_name:
            raise ValueError("gate profile_name must not be empty")
        if not self.profile_version:
            raise ValueError("gate profile_version must not be empty")
        if not np.isfinite(self.mahalanobis_threshold) or self.mahalanobis_threshold <= 0:
            raise ValueError("mahalanobis_threshold must be positive and finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "mahalanobis_threshold": float(self.mahalanobis_threshold),
        }


@dataclass(slots=True)
class DenseCrossingCalibrationReport:
    configuration: dict[str, Any]
    per_seed: list[dict[str, Any]]
    aggregate: dict[str, Any]
    schema_version: str = CALIBRATION_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "configuration": _json_ready(self.configuration),
            "per_seed": _json_ready(self.per_seed),
            "aggregate": _json_ready(self.aggregate),
        }


def run_dense_crossing_calibration(
    *,
    seeds: Sequence[int] = tuple(range(10)),
    target_count: int = 5,
    steps: int = 12,
    gate_profile: GateCalibrationProfile | None = None,
    risk_thresholds: RiskThresholds | None = None,
    truth_output_directory: str | Path | None = None,
) -> DenseCrossingCalibrationReport:
    """Run the governed N-target fixture for at least ten deterministic seeds."""

    normalized_seeds = tuple(int(seed) for seed in seeds)
    if len(normalized_seeds) < 10:
        raise ValueError("dense-crossing calibration requires at least 10 seeds")
    if len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValueError("calibration seeds must be unique")
    active_gate = gate_profile or GateCalibrationProfile()
    active_risk = risk_thresholds or RiskThresholds(
        profile_name="d2_dense_crossing_risk",
        profile_version="v1",
    )
    truth_directory = (
        None if truth_output_directory is None else Path(truth_output_directory)
    )
    per_seed: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []

    for seed in normalized_seeds:
        governed_frames = build_dense_crossing_replay_fixture(
            target_count=target_count,
            seed=seed,
            steps=steps,
        )
        labels = extract_offline_truth_labels(governed_frames)
        online_frames = strip_offline_truth_from_frames(governed_frames)
        episode_id = str(
            online_frames[0]["replay_metadata"]["episode_id"]
        )
        if truth_directory is not None:
            write_offline_truth_labels_jsonl(
                truth_directory / f"{episode_id}.offline_truth_labels.jsonl",
                labels,
            )
        tracker = Tracker(
            associator=GNNHungarianAssociator(
                gate_threshold=active_gate.mahalanobis_threshold,
            )
        )
        report = run_airsim_replay_association(
            online_frames,
            replay_name=episode_id,
            tracker=tracker,
            risk_thresholds=active_risk,
            offline_truth_labels=labels,
        )
        metrics = report.metrics
        truth_available = bool(metrics.get("truth_metrics_available", False))
        continuity_available = bool(metrics.get("continuity_available", False))
        nis = dict(metrics.get("nis", {"available": False, "count": 0}))
        nees = dict(metrics.get("nees", {"available": False, "count": 0}))
        runtime_seconds = float(
            sum(
                float(value)
                for value in report.online_metrics.get(
                    "runtime_seconds_by_associator", {}
                ).values()
            )
        )
        deterministic_payload = {
            "seed": seed,
            "target_count": target_count,
            "steps": steps,
            "gate_profile": active_gate.to_dict(),
            "risk_profile": {
                "profile_name": active_risk.profile_name,
                "profile_version": active_risk.profile_version,
            },
            "online_frames": online_frames,
            "offline_truth_labels": [label.to_dict() for label in labels],
            "identity_metrics": {
                "id_switch_count": metrics.get("id_switch_count"),
                "track_continuity": metrics.get("track_continuity"),
                "duplicate_assignment_count": metrics.get(
                    "duplicate_assignment_count"
                ),
            },
        }
        seed_row = {
            "seed": seed,
            "episode_id": episode_id,
            "frame_count": report.frame_count,
            "target_count": report.target_count,
            "offline_truth_schema_version": OFFLINE_TRUTH_SCHEMA_VERSION,
            "offline_truth_label_count": len(labels),
            "gate_profile": active_gate.to_dict(),
            "risk_profile": active_risk.profile_name,
            "risk_profile_version": active_risk.profile_version,
            "association_risk_threshold_version": active_risk.profile_version,
            "truth_metrics_available": truth_available,
            "continuity_available": continuity_available,
            "id_switch_count": (
                int(metrics["id_switch_count"]) if truth_available else None
            ),
            "track_continuity": (
                float(metrics["track_continuity"])
                if continuity_available
                else None
            ),
            "duplicate_assignment_count": int(
                metrics.get("duplicate_assignment_count", 0)
            ),
            "nis": nis,
            "nees": nees,
            "runtime_seconds": runtime_seconds,
            "online_truth_isolation_violations": int(
                metrics.get("online_truth_isolation_violations", 0)
            ),
            "risk_summary": report.risk_summary,
            "deterministic_signature": _stable_digest(deterministic_payload),
        }
        per_seed.append(seed_row)
        risk_rows.append(_risk_calibration_row(seed_row))

    configuration = {
        "target_count": target_count,
        "steps": steps,
        "seeds": list(normalized_seeds),
        "minimum_seed_count": 10,
        "scenario": "n_target_dense_crossing_occlusion_miss_false_alarm",
        "gate_profile": active_gate.to_dict(),
        "risk_profile": {
            "profile_name": active_risk.profile_name,
            "profile_version": active_risk.profile_version,
        },
        "online_truth_policy": "forbidden",
        "offline_truth_schema_version": OFFLINE_TRUTH_SCHEMA_VERSION,
    }
    aggregate = summarize_dense_crossing_calibration(per_seed)
    aggregate["risk_calibration_summary"] = summarize_multi_seed_risk_calibration(
        risk_rows
    )
    return DenseCrossingCalibrationReport(
        configuration=configuration,
        per_seed=per_seed,
        aggregate=aggregate,
    )


def summarize_dense_crossing_calibration(
    per_seed: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate seed metrics while preserving unavailable states."""

    rows = [dict(row) for row in per_seed]
    return {
        "seed_count": len(rows),
        "seeds": [int(row["seed"]) for row in rows],
        "target_count_distribution": _available_distribution(
            rows, "target_count"
        ),
        "id_switch_count": _available_distribution(
            rows,
            "id_switch_count",
            availability_key="truth_metrics_available",
        ),
        "track_continuity": _available_distribution(
            rows,
            "track_continuity",
            availability_key="continuity_available",
        ),
        "runtime_seconds": _available_distribution(rows, "runtime_seconds"),
        "nis_availability": _nested_availability(rows, "nis"),
        "nees_availability": _nested_availability(rows, "nees"),
        "truth_metrics_available_seed_count": sum(
            bool(row.get("truth_metrics_available", False)) for row in rows
        ),
        "continuity_available_seed_count": sum(
            bool(row.get("continuity_available", False)) for row in rows
        ),
        "online_truth_isolation_violation_count": sum(
            int(row.get("online_truth_isolation_violations", 0)) for row in rows
        ),
        "gate_profiles": _unique_json_values(
            row.get("gate_profile", {}) for row in rows
        ),
        "risk_profiles": sorted(
            {
                (
                    str(row.get("risk_profile", "default")),
                    str(row.get("risk_profile_version", "unversioned")),
                )
                for row in rows
            }
        ),
    }


def write_dense_crossing_calibration_report(
    path: str | Path,
    report: DenseCrossingCalibrationReport,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True))


def _risk_calibration_row(seed_row: Mapping[str, Any]) -> dict[str, Any]:
    risk_summary = dict(seed_row.get("risk_summary", {}))
    return {
        "seed": seed_row["seed"],
        "episode_id": seed_row["episode_id"],
        "scenario_name": "n_target_dense_crossing_occlusion_miss_false_alarm",
        "scenario_tags": [
            "crossing",
            "dense",
            "occlusion",
            "missed_detection",
            "false_alarm",
        ],
        "frame_count": seed_row["frame_count"],
        "target_count": seed_row["target_count"],
        "gate_threshold": seed_row["gate_profile"]["mahalanobis_threshold"],
        "risk_profile": seed_row["risk_profile"],
        "risk_profile_version": seed_row["risk_profile_version"],
        "id_switch_count": seed_row["id_switch_count"],
        "track_continuity": seed_row["track_continuity"],
        "duplicate_assignment_count": seed_row["duplicate_assignment_count"],
        "soft_risk_frame_count": risk_summary.get("soft_risk_frame_count", 0),
        "hard_risk_frame_count": risk_summary.get("hard_risk_frame_count", 0),
        "max_soft_risk_score": risk_summary.get("max_soft_risk_score", 0.0),
        "max_hard_risk_score": risk_summary.get("max_hard_risk_score", 0.0),
        "risk_summary": risk_summary,
    }


def _available_distribution(
    rows: Sequence[Mapping[str, Any]],
    key: str,
    *,
    availability_key: str | None = None,
) -> dict[str, Any]:
    values = [
        float(row[key])
        for row in rows
        if row.get(key) is not None
        and (availability_key is None or bool(row.get(availability_key, False)))
        and np.isfinite(float(row[key]))
    ]
    unavailable_count = len(rows) - len(values)
    return {
        "available": bool(values),
        "available_seed_count": len(values),
        "unavailable_seed_count": unavailable_count,
        "count": len(values),
        "mean": float(np.mean(values)) if values else None,
        "std": float(np.std(values)) if values else None,
        "min": float(np.min(values)) if values else None,
        "max": float(np.max(values)) if values else None,
    }


def _nested_availability(
    rows: Sequence[Mapping[str, Any]], key: str
) -> dict[str, Any]:
    available = [
        row
        for row in rows
        if isinstance(row.get(key), Mapping)
        and bool(row[key].get("available", False))
    ]
    return {
        "available": bool(available),
        "available_seed_count": len(available),
        "unavailable_seed_count": len(rows) - len(available),
        "sample_count": sum(int(row[key].get("count", 0)) for row in available),
    }


def _stable_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _json_ready(payload), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unique_json_values(values: Iterable[Any]) -> list[Any]:
    unique = {
        json.dumps(_json_ready(value), sort_keys=True): _json_ready(value)
        for value in values
    }
    return [unique[key] for key in sorted(unique)]


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
