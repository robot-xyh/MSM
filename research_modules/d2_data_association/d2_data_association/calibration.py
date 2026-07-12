"""Deterministic multi-seed dense-crossing calibration for D2."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
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
from .replay_governance import (
    build_dense_crossing_replay_fixture,
    build_long_dense_crossing_replay_fixture,
)
from .tracker import Tracker


CALIBRATION_SCHEMA_VERSION = "d2-dense-crossing-calibration/v1"
LONG_REPLAY_CALIBRATION_SCHEMA_VERSION = "d2-long-replay-calibration/v1"
LONG_REPLAY_SCENARIO_VERSION = "d2-governed-long-replay/v1"


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


@dataclass(frozen=True, slots=True)
class LongReplayCalibrationProfile:
    profile_name: str = "d2_governed_long_replay"
    profile_version: str = "v1"
    scenario_version: str = LONG_REPLAY_SCENARIO_VERSION
    steps: int = 120
    sample_period_s: float = 0.2
    oosm_latency_threshold_s: float = 0.4

    def __post_init__(self) -> None:
        if not self.profile_name or not self.profile_version or not self.scenario_version:
            raise ValueError("long replay profile names and versions must not be empty")
        if self.steps < 40:
            raise ValueError("long replay profile requires at least 40 steps")
        if not np.isfinite(self.sample_period_s) or self.sample_period_s <= 0.0:
            raise ValueError("sample_period_s must be positive and finite")
        if (
            not np.isfinite(self.oosm_latency_threshold_s)
            or self.oosm_latency_threshold_s <= 0.0
        ):
            raise ValueError("oosm_latency_threshold_s must be positive and finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "profile_version": self.profile_version,
            "scenario_version": self.scenario_version,
            "steps": self.steps,
            "sample_period_s": self.sample_period_s,
            "oosm_latency_threshold_s": self.oosm_latency_threshold_s,
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

    return _run_governed_replay_calibration(
        seeds=seeds,
        target_count=target_count,
        steps=steps,
        gate_profile=gate_profile,
        risk_thresholds=risk_thresholds,
        truth_output_directory=truth_output_directory,
        scenario_name="n_target_dense_crossing_occlusion_miss_false_alarm",
        scenario_version="d2-dense-crossing-fixture/v1",
        scenario_tags=(
            "crossing",
            "dense",
            "occlusion",
            "missed_detection",
            "false_alarm",
        ),
        frame_builder=lambda seed: build_dense_crossing_replay_fixture(
            target_count=target_count,
            seed=seed,
            steps=steps,
        ),
        oosm_latency_threshold_s=0.4,
        report_schema_version=CALIBRATION_SCHEMA_VERSION,
    )


def run_long_replay_calibration(
    *,
    seeds: Sequence[int] = tuple(range(10)),
    target_count: int = 5,
    profile: LongReplayCalibrationProfile | None = None,
    gate_profile: GateCalibrationProfile | None = None,
    risk_thresholds: RiskThresholds | None = None,
    truth_output_directory: str | Path | None = None,
) -> DenseCrossingCalibrationReport:
    """Calibrate GNN/Hungarian on long governed replay with OOSM exposure."""

    active_profile = profile or LongReplayCalibrationProfile()
    return _run_governed_replay_calibration(
        seeds=seeds,
        target_count=target_count,
        steps=active_profile.steps,
        gate_profile=gate_profile,
        risk_thresholds=risk_thresholds,
        truth_output_directory=truth_output_directory,
        scenario_name="n_target_long_dense_crossing_occlusion_miss_false_alarm_oosm",
        scenario_version=active_profile.scenario_version,
        scenario_tags=(
            "long_replay",
            "crossing",
            "dense",
            "occlusion",
            "missed_detection",
            "false_alarm",
            "oosm",
        ),
        frame_builder=lambda seed: build_long_dense_crossing_replay_fixture(
            target_count=target_count,
            seed=seed,
            steps=active_profile.steps,
            sample_period_s=active_profile.sample_period_s,
            scenario_version=active_profile.scenario_version,
        ),
        oosm_latency_threshold_s=active_profile.oosm_latency_threshold_s,
        calibration_profile=active_profile.to_dict(),
        report_schema_version=LONG_REPLAY_CALIBRATION_SCHEMA_VERSION,
    )


def _run_governed_replay_calibration(
    *,
    seeds: Sequence[int],
    target_count: int,
    steps: int,
    gate_profile: GateCalibrationProfile | None,
    risk_thresholds: RiskThresholds | None,
    truth_output_directory: str | Path | None,
    scenario_name: str,
    scenario_version: str,
    scenario_tags: Sequence[str],
    frame_builder: Callable[[int], list[dict[str, Any]]],
    oosm_latency_threshold_s: float,
    calibration_profile: Mapping[str, Any] | None = None,
    report_schema_version: str,
) -> DenseCrossingCalibrationReport:
    """Run one versioned governed replay profile across deterministic seeds."""

    normalized_seeds = tuple(int(seed) for seed in seeds)
    if len(normalized_seeds) < 10:
        raise ValueError("governed replay calibration requires at least 10 seeds")
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
        governed_frames = frame_builder(seed)
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
        oosm_diagnostics = _oosm_diagnostics(
            governed_frames,
            latency_threshold_s=oosm_latency_threshold_s,
        )
        deterministic_payload = {
            "seed": seed,
            "target_count": target_count,
            "steps": steps,
            "gate_profile": active_gate.to_dict(),
            "scenario_version": scenario_version,
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
            "measurement_count_min": min(
                (len(frame.get("detections", [])) for frame in online_frames),
                default=0,
            ),
            "measurement_count_max": max(
                (len(frame.get("detections", [])) for frame in online_frames),
                default=0,
            ),
            "scenario_name": scenario_name,
            "scenario_version": scenario_version,
            "scenario_tags": list(scenario_tags),
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
            "coverage_continuity": (
                float(metrics["coverage_continuity"])
                if continuity_available
                else None
            ),
            "false_track_count": (
                int(metrics["false_track_count"]) if truth_available else None
            ),
            "false_track_rate": (
                float(metrics["false_track_rate"]) if truth_available else None
            ),
            "rmse": float(metrics["rmse"]) if truth_available else None,
            "duplicate_assignment_count": int(
                metrics.get("duplicate_assignment_count", 0)
            ),
            "nis": nis,
            "nees": nees,
            "runtime_seconds": runtime_seconds,
            "online_truth_isolation_violations": int(
                metrics.get("online_truth_isolation_violations", 0)
            ),
            "online_truth_leakage_count": int(
                metrics.get("online_truth_isolation_violations", 0)
            ),
            "global_track_id_owner": "d2_center",
            "global_track_id_count": len(report.global_track_ids),
            "online_associator": "GNNHungarianAssociator",
            "optional_associators_in_mainline": [],
            "oosm_diagnostics": oosm_diagnostics,
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
        "scenario": scenario_name,
        "scenario_version": scenario_version,
        "scenario_tags": list(scenario_tags),
        "gate_profile": active_gate.to_dict(),
        "risk_profile": {
            "profile_name": active_risk.profile_name,
            "profile_version": active_risk.profile_version,
        },
        "online_truth_policy": "forbidden",
        "offline_truth_schema_version": OFFLINE_TRUTH_SCHEMA_VERSION,
        "global_track_id_owner": "d2_center",
        "online_associator": "GNNHungarianAssociator",
        "optional_associators_in_mainline": [],
        "calibration_profile": _json_ready(calibration_profile or {}),
    }
    aggregate = summarize_dense_crossing_calibration(per_seed)
    aggregate["risk_calibration_summary"] = summarize_multi_seed_risk_calibration(
        risk_rows
    )
    return DenseCrossingCalibrationReport(
        configuration=configuration,
        per_seed=per_seed,
        aggregate=aggregate,
        schema_version=report_schema_version,
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
        "coverage_continuity": _available_distribution(
            rows,
            "coverage_continuity",
            availability_key="continuity_available",
        ),
        "false_track_count": _available_distribution(
            rows,
            "false_track_count",
            availability_key="truth_metrics_available",
        ),
        "false_track_rate": _available_distribution(
            rows,
            "false_track_rate",
            availability_key="truth_metrics_available",
        ),
        "rmse": _available_distribution(
            rows,
            "rmse",
            availability_key="truth_metrics_available",
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
        "online_truth_leakage_count": sum(
            int(row.get("online_truth_leakage_count", 0)) for row in rows
        ),
        "oosm_exposure": _summarize_oosm_diagnostics(rows),
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
        "scenario_name": seed_row.get("scenario_name"),
        "scenario_version": seed_row.get("scenario_version"),
        "scenario_tags": list(seed_row.get("scenario_tags", [])),
        "frame_count": seed_row["frame_count"],
        "target_count": seed_row["target_count"],
        "gate_threshold": seed_row["gate_profile"]["mahalanobis_threshold"],
        "risk_profile": seed_row["risk_profile"],
        "risk_profile_version": seed_row["risk_profile_version"],
        "association_risk_threshold_version": seed_row[
            "association_risk_threshold_version"
        ],
        "id_switch_count": seed_row["id_switch_count"],
        "track_continuity": seed_row["track_continuity"],
        "duplicate_assignment_count": seed_row["duplicate_assignment_count"],
        "false_track_count": seed_row.get("false_track_count"),
        "rmse": seed_row.get("rmse"),
        "soft_risk_frame_count": risk_summary.get("soft_risk_frame_count", 0),
        "hard_risk_frame_count": risk_summary.get("hard_risk_frame_count", 0),
        "max_soft_risk_score": risk_summary.get("max_soft_risk_score", 0.0),
        "max_hard_risk_score": risk_summary.get("max_hard_risk_score", 0.0),
        "risk_summary": risk_summary,
    }


def _oosm_diagnostics(
    frames: Sequence[Mapping[str, Any]],
    *,
    latency_threshold_s: float,
) -> dict[str, Any]:
    measurement_times = [float(frame["measurement_timestamp"]) for frame in frames]
    arrival_times = [
        float(frame.get("arrival_timestamp", frame["measurement_timestamp"]))
        for frame in frames
    ]
    latencies = [
        arrival - measurement
        for measurement, arrival in zip(measurement_times, arrival_times, strict=True)
    ]
    arrival_inversions = sum(
        current > following
        for current, following in zip(arrival_times, arrival_times[1:])
    )
    measurement_inversions = sum(
        current > following
        for current, following in zip(measurement_times, measurement_times[1:])
    )
    return {
        "available": bool(frames),
        "frame_count": len(frames),
        "measurement_order_monotonic": measurement_inversions == 0,
        "measurement_order_inversion_count": measurement_inversions,
        "arrival_order_inversion_count": arrival_inversions,
        "latency_threshold_s": float(latency_threshold_s),
        "late_measurement_count": sum(
            latency > latency_threshold_s for latency in latencies
        ),
        "mean_latency_s": float(np.mean(latencies)) if latencies else None,
        "max_latency_s": float(np.max(latencies)) if latencies else None,
        "handling_policy": "measurement_time_ordered_after_governance",
    }


def _summarize_oosm_diagnostics(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    diagnostics = [
        dict(row["oosm_diagnostics"])
        for row in rows
        if isinstance(row.get("oosm_diagnostics"), Mapping)
    ]
    return {
        "available": bool(diagnostics),
        "available_seed_count": len(diagnostics),
        "arrival_order_inversion_count": sum(
            int(item.get("arrival_order_inversion_count", 0)) for item in diagnostics
        ),
        "late_measurement_count": sum(
            int(item.get("late_measurement_count", 0)) for item in diagnostics
        ),
        "all_measurement_order_monotonic": all(
            bool(item.get("measurement_order_monotonic", False))
            for item in diagnostics
        ),
        "handling_policy": "measurement_time_ordered_after_governance",
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
