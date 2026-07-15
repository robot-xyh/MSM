"""Offline AirSim-style replay and threshold calibration helpers for D2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

import numpy as np

from .associators import GNNHungarianAssociator
from .d1_governed_adapter import (
    d2_frames_from_d1_governed_replay,
    is_d1_governed_replay_payload,
)
from .dry_run_adapter import run_airsim_dry_run_association
from .metrics import RiskThresholds, classify_risk_summary
from .models import AssociationRiskSummary, TrackerTruthPolicy
from .offline_truth import OfflineTruthLabel, evaluation_frames_with_offline_truth
from .replay_governance import (
    InitializationGovernanceProfile,
    OfflineTruthEvaluation,
    evaluate_offline_truth,
)
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
    threshold_sensitivity_summary: dict[str, Any] = field(default_factory=dict)
    replay_metadata: dict[str, Any] = field(default_factory=dict)
    online_metrics: dict[str, Any] = field(default_factory=dict)
    offline_truth_evaluation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "replay_name": self.replay_name,
            "frame_count": self.frame_count,
            "target_count": self.target_count,
            "association_risk_threshold_version": self.risk_summary.get(
                "association_risk_threshold_version",
                self.risk_summary.get("risk_profile_version", "unversioned"),
            ),
            "replay_metadata": _json_ready(self.replay_metadata),
            "truth_metrics_available": bool(
                self.metrics.get("truth_metrics_available", False)
            ),
            "continuity_available": bool(
                self.metrics.get(
                    "continuity_available",
                    self.metrics.get("truth_metrics_available", False),
                )
            ),
            "global_track_ids": list(self.global_track_ids),
            "metrics": _json_ready(self.metrics),
            "online_metrics": _json_ready(self.online_metrics),
            "offline_truth_evaluation": _json_ready(
                self.offline_truth_evaluation
            ),
            "association_logs": _json_ready(self.association_logs),
            "risk_summary": _json_ready(self.risk_summary),
            "threshold_sensitivity": _json_ready(self.threshold_sensitivity),
            "threshold_sensitivity_summary": _json_ready(
                self.threshold_sensitivity_summary
            ),
        }


def load_airsim_replay_frames(path: str | Path) -> list[dict[str, Any]]:
    """Load offline AirSim-style replay frames from JSON or JSONL.

    Supported payloads are a list of frame dicts, a JSON object with a
    ``frames`` key, a D1 ``serialize_governed_replay`` manifest/records bundle,
    or JSONL records containing either a frame directly or a nested
    ``frame``/``d2_frame``/``airsim_frame`` payload. Non-frame JSONL records
    are ignored so mixed episode logs can be filtered by D2.
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
    replay_metadata: Mapping[str, Any] | None = None,
    default_position_variance: float = 1.0,
    gate_thresholds: Sequence[float] | None = None,
    initialization_profile: InitializationGovernanceProfile | None = None,
    offline_truth_labels: Sequence[OfflineTruthLabel | Mapping[str, Any]] | None = None,
) -> ReplayAssociationReport:
    """Run D2 association on offline replay frames and return a stable report."""

    frame_list = list(frames)
    metadata = _merge_replay_metadata(
        _collect_replay_metadata(frame_list),
        replay_metadata,
    )
    result = run_airsim_dry_run_association(
        frame_list,
        tracker=tracker,
        default_position_variance=default_position_variance,
        isolate_offline_truth=True,
    )
    thresholds = risk_thresholds if risk_thresholds is not None else RiskThresholds()
    evaluation_frames = (
        evaluation_frames_with_offline_truth(frame_list, offline_truth_labels)
        if offline_truth_labels is not None
        else frame_list
    )
    offline_evaluation = evaluate_offline_truth(
        evaluation_frames,
        result,
        profile_name=f"{thresholds.profile_name}_offline_truth",
        profile_version=thresholds.profile_version,
        initialization_profile=initialization_profile,
    )
    metrics = _merge_online_offline_metrics(result.metrics, offline_evaluation)
    association_logs = _annotate_association_logs(
        result.association_logs,
        result=result,
        offline_evaluation=offline_evaluation,
        thresholds=thresholds,
    )
    risk_summary = summarize_replay_risk(
        association_logs,
        metrics,
        thresholds=thresholds,
    )
    sensitivity = (
        run_threshold_sensitivity(
            frame_list,
            gate_thresholds=gate_thresholds,
            risk_thresholds=[thresholds],
            replay_metadata=metadata,
            default_position_variance=default_position_variance,
            initialization_profile=initialization_profile,
        )
        if gate_thresholds is not None
        else []
    )
    sensitivity_summary = _summarize_threshold_sensitivity(sensitivity)
    return ReplayAssociationReport(
        replay_name=replay_name,
        frame_count=len(frame_list),
        target_count=_target_count(frame_list),
        global_track_ids=result.global_track_ids,
        metrics=metrics,
        association_logs=association_logs,
        risk_summary=risk_summary,
        threshold_sensitivity=sensitivity,
        threshold_sensitivity_summary=sensitivity_summary,
        replay_metadata=metadata,
        online_metrics=dict(result.metrics),
        offline_truth_evaluation=offline_evaluation.to_dict(),
    )


def run_threshold_sensitivity(
    frames: Iterable[Any],
    *,
    gate_thresholds: Sequence[float] | None = None,
    risk_thresholds: Sequence[RiskThresholds] | None = None,
    replay_metadata: Mapping[str, Any] | None = None,
    feature_weight: float = 6.0,
    default_position_variance: float = 1.0,
    initialization_profile: InitializationGovernanceProfile | None = None,
) -> list[dict[str, Any]]:
    """Evaluate replay metrics and risk breakdown across threshold profiles."""

    frame_list = list(frames)
    metadata = _merge_replay_metadata(
        _collect_replay_metadata(frame_list),
        replay_metadata,
    )
    gates = tuple(gate_thresholds) if gate_thresholds is not None else (5.99, 9.21, 13.82)
    profiles = tuple(risk_thresholds) if risk_thresholds is not None else (RiskThresholds(),)
    rows: list[dict[str, Any]] = []
    for gate_threshold in gates:
        for thresholds in profiles:
            tracker = Tracker(
                associator=GNNHungarianAssociator(
                    gate_threshold=float(gate_threshold),
                    feature_weight=feature_weight,
                ),
                truth_policy=TrackerTruthPolicy.ONLINE,
            )
            result = run_airsim_dry_run_association(
                frame_list,
                tracker=tracker,
                default_position_variance=default_position_variance,
                isolate_offline_truth=True,
            )
            offline_evaluation = evaluate_offline_truth(
                frame_list,
                result,
                profile_name=f"{thresholds.profile_name}_offline_truth",
                profile_version=thresholds.profile_version,
                initialization_profile=initialization_profile,
            )
            metrics = _merge_online_offline_metrics(
                result.metrics,
                offline_evaluation,
            )
            association_logs = _annotate_association_logs(
                result.association_logs,
                result=result,
                offline_evaluation=offline_evaluation,
                thresholds=thresholds,
            )
            risk_summary = summarize_replay_risk(
                association_logs,
                metrics,
                thresholds=thresholds,
            )
            soft_frame_count = int(risk_summary["soft_risk_frame_count"])
            hard_frame_count = int(risk_summary["hard_risk_frame_count"])
            diagnostics = _summarize_association_log_diagnostics(
                association_logs
            )
            rows.append(
                {
                    "gate_threshold": float(gate_threshold),
                    "risk_profile": thresholds.profile_name,
                    "risk_profile_version": thresholds.profile_version,
                    "association_risk_threshold_version": thresholds.profile_version,
                    "frame_count": len(frame_list),
                    "target_count": _target_count(frame_list),
                    "replay_metadata": _json_ready(metadata),
                    "seed": _metadata_value(metadata, "seed"),
                    "episode_id": _metadata_value(metadata, "episode_id"),
                    "scenario_name": _metadata_value(
                        metadata, "scenario_name", "scenario"
                    ),
                    "drone_count": _metadata_value(metadata, "drone_count"),
                    "id_switch_count": metrics["id_switch_count"],
                    "track_continuity": metrics["track_continuity"],
                    "truth_metrics_available": metrics[
                        "truth_metrics_available"
                    ],
                    "continuity_available": metrics["continuity_available"],
                    "duplicate_assignment_count": metrics[
                        "duplicate_assignment_count"
                    ],
                    "initialization_success_rate": metrics[
                        "initialization_success_rate"
                    ],
                    "mean_initialization_latency_s": metrics[
                        "mean_initialization_latency_s"
                    ],
                    "initialization_profile": metrics["initialization_profile"],
                    "false_track_count": metrics["false_track_count"],
                    "false_track_rate": metrics["false_track_rate"],
                    "nis": metrics["nis"],
                    "nees": metrics["nees"],
                    "offline_truth_evaluation": offline_evaluation.to_dict(),
                    "soft_risk_frame_count": soft_frame_count,
                    "hard_risk_frame_count": hard_frame_count,
                    "max_soft_risk_score": risk_summary["max_soft_risk_score"],
                    "max_hard_risk_score": risk_summary["max_hard_risk_score"],
                    "scenario_tags": _scenario_tags_for_row(
                        {
                            "replay_metadata": metadata,
                            "scenario_name": _metadata_value(
                                metadata, "scenario_name", "scenario"
                            ),
                        }
                    ),
                    "gate_summary": diagnostics["gate_summary"],
                    "motion_risk_summary": diagnostics["motion_risk_summary"],
                    "quality_risk_summary": diagnostics["quality_risk_summary"],
                    "risk_summary": risk_summary,
                }
            )
    return rows


def summarize_multi_seed_risk_calibration(
    threshold_rows: Iterable[Mapping[str, Any]],
    *,
    max_mean_id_switch_count: float = 0.0,
    min_mean_track_continuity: float = 0.75,
    max_mean_duplicate_assignment_count: float = 0.0,
    max_mean_hard_risk_frame_rate: float = 0.10,
) -> dict[str, Any]:
    """Aggregate threshold sensitivity rows across seeds/episodes.

    The input is the concatenated output of `run_threshold_sensitivity()` for
    multiple replay seeds. Rows are grouped by gate threshold, risk profile,
    and profile version. The helper reports metric/risk distributions and a
    deterministic recommended profile for D4/D6 threshold governance.
    """

    rows = [dict(row) for row in threshold_rows]
    groups: dict[tuple[float, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (
            float(row.get("gate_threshold", 0.0)),
            str(row.get("risk_profile", "default")),
            str(row.get("risk_profile_version", "unversioned")),
        )
        groups.setdefault(key, []).append(row)

    group_summaries = [
        _summarize_calibration_group(
            key,
            group_rows,
            max_mean_id_switch_count=max_mean_id_switch_count,
            min_mean_track_continuity=min_mean_track_continuity,
            max_mean_duplicate_assignment_count=max_mean_duplicate_assignment_count,
            max_mean_hard_risk_frame_rate=max_mean_hard_risk_frame_rate,
        )
        for key, group_rows in sorted(groups.items())
    ]
    recommended = (
        min(group_summaries, key=_calibration_recommendation_rank)
        if group_summaries
        else None
    )
    return {
        "row_count": len(rows),
        "group_count": len(group_summaries),
        "threshold_sensitivity_summary": _summarize_threshold_sensitivity(rows),
        "selection_criteria": {
            "max_mean_id_switch_count": max_mean_id_switch_count,
            "min_mean_track_continuity": min_mean_track_continuity,
            "max_mean_duplicate_assignment_count": max_mean_duplicate_assignment_count,
            "max_mean_hard_risk_frame_rate": max_mean_hard_risk_frame_rate,
        },
        "groups": group_summaries,
        "recommended": None
        if recommended is None
        else {
            "gate_threshold": recommended["gate_threshold"],
            "risk_profile": recommended["risk_profile"],
            "risk_profile_version": recommended["risk_profile_version"],
            "thresholds": recommended["thresholds"],
            "passes_governance": recommended["passes_governance"],
            "summary": recommended["recommendation_summary"],
        },
    }


def summarize_replay_risk(
    association_logs: Iterable[Mapping[str, Any]],
    metrics: Mapping[str, Any],
    *,
    thresholds: RiskThresholds | None = None,
) -> dict[str, Any]:
    """Summarize soft and hard D2 risk evidence for replay/calibration."""

    active_thresholds = thresholds if thresholds is not None else RiskThresholds()
    log_list = [_log_mapping(log) for log in association_logs]
    breakdowns = []
    for log in log_list:
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
    diagnostics = _summarize_association_log_diagnostics(log_list)
    truth_metrics_available = bool(metrics.get("truth_metrics_available", False))
    continuity_available = bool(
        metrics.get("continuity_available", truth_metrics_available)
    )
    return {
        "risk_profile": active_thresholds.profile_name,
        "risk_profile_version": active_thresholds.profile_version,
        "association_risk_threshold_version": active_thresholds.profile_version,
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
        "id_switch_count": (
            int(metrics["id_switch_count"])
            if truth_metrics_available and metrics.get("id_switch_count") is not None
            else None
        ),
        "track_continuity": (
            float(metrics["track_continuity"])
            if continuity_available and metrics.get("track_continuity") is not None
            else None
        ),
        "truth_metrics_available": truth_metrics_available,
        "truth_metrics_reason": metrics.get("truth_metrics_reason"),
        "continuity_available": continuity_available,
        "continuity_reason": metrics.get("continuity_reason"),
        "duplicate_assignment_count": int(
            metrics.get("duplicate_assignment_count", 0)
        ),
        "gate_summary": diagnostics["gate_summary"],
        "motion_risk_summary": diagnostics["motion_risk_summary"],
        "quality_risk_summary": diagnostics["quality_risk_summary"],
        "motion_quality_risk_summary": {
            "motion": diagnostics["motion_risk_summary"],
            "quality": diagnostics["quality_risk_summary"],
        },
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

    lines = [
        json.dumps(_json_ready(dict(log)), sort_keys=True)
        for log in association_logs
    ]
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""))


def _merge_online_offline_metrics(
    online_metrics: Mapping[str, Any],
    offline_evaluation: OfflineTruthEvaluation,
) -> dict[str, Any]:
    """Keep online operational metrics and overlay truth-only evaluation fields."""

    merged = dict(online_metrics)
    merged.update(offline_evaluation.summary)
    merged["online_truth_isolated"] = True
    merged["offline_truth_profile"] = offline_evaluation.profile_name
    merged["offline_truth_profile_version"] = offline_evaluation.profile_version
    return merged


def _annotate_association_logs(
    association_logs: Sequence[Mapping[str, Any]],
    *,
    result: Any,
    offline_evaluation: OfflineTruthEvaluation,
    thresholds: RiskThresholds,
) -> list[dict[str, Any]]:
    """Attach versioned online governance fields without exposing truth labels."""

    annotated: list[dict[str, Any]] = []
    for frame_index, log in enumerate(association_logs):
        payload = dict(log)
        metadata = dict(payload.get("metadata", {}))
        frame_evaluation = (
            offline_evaluation.frame_metrics[frame_index]
            if frame_index < len(offline_evaluation.frame_metrics)
            else {}
        )
        active_track_count = (
            len(result.frames[frame_index].active_tracks)
            if frame_index < len(result.frames)
            else 0
        )
        detection_count = (
            len(result.frames[frame_index].detections)
            if frame_index < len(result.frames)
            else 0
        )
        metadata.update(
            {
                "risk_profile": thresholds.profile_name,
                "risk_profile_version": thresholds.profile_version,
                "association_risk_threshold_version": thresholds.profile_version,
                "association_log_schema_version": "d2-association-log/v2",
                "online_truth_isolated": True,
                "measurement_count_n": detection_count,
                "active_track_count": active_track_count,
                "nis_available": bool(
                    frame_evaluation.get("nis", {}).get("available", False)
                ),
                "nis": frame_evaluation.get("nis"),
            }
        )
        payload["metadata"] = metadata
        annotated.append(payload)
    return annotated


def _summarize_association_log_diagnostics(
    association_logs: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    logs = [_log_mapping(log) for log in association_logs]
    return {
        "gate_summary": _summarize_gate_diagnostics(logs),
        "motion_risk_summary": _summarize_motion_risk(logs),
        "quality_risk_summary": _summarize_quality_risk(logs),
    }


def _summarize_gate_diagnostics(
    association_logs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    gate_pass_count = 0
    mahalanobis_gate_reject_count = 0
    assignment_above_gate_reject_count = 0
    total_rejected_pair_count = 0
    matched_pair_count = 0
    unmatched_track_count = 0
    unmatched_detection_count = 0
    frame_pass_rates: list[float] = []
    candidate_counts_by_track: list[float] = []
    candidate_counts_by_detection: list[float] = []
    gate_threshold_values: list[float] = []

    for log in association_logs:
        metadata = _merged_log_metadata(log)
        frame_gate_pass_count = int(
            sum(_numeric_values(metadata.get("candidate_counts_by_track", {})))
        )
        rejected_pairs = _sequence_value(log.get("rejected_pairs"))
        frame_mahalanobis_reject_count = sum(
            1 for pair in rejected_pairs if _pair_reason(pair) == "mahalanobis_gate"
        )
        frame_assignment_above_gate_count = sum(
            1
            for pair in rejected_pairs
            if _pair_reason(pair) == "assignment_above_gate"
        )
        frame_total_pair_count = (
            frame_gate_pass_count + frame_mahalanobis_reject_count
        )
        if frame_total_pair_count > 0:
            frame_pass_rates.append(frame_gate_pass_count / frame_total_pair_count)

        gate_pass_count += frame_gate_pass_count
        mahalanobis_gate_reject_count += frame_mahalanobis_reject_count
        assignment_above_gate_reject_count += frame_assignment_above_gate_count
        total_rejected_pair_count += len(rejected_pairs)
        matched_pair_count += len(_sequence_value(log.get("matched_pairs")))
        unmatched_track_count += len(_sequence_value(log.get("unmatched_track_ids")))
        unmatched_detection_count += len(
            _sequence_value(log.get("unmatched_detection_ids"))
        )
        candidate_counts_by_track.extend(
            _numeric_values(metadata.get("candidate_counts_by_track", {}))
        )
        candidate_counts_by_detection.extend(
            _numeric_values(metadata.get("candidate_counts_by_detection", {}))
        )
        gate_threshold_values.extend(
            _numeric_values(metadata.get("gate_thresholds_by_track", {}))
        )

    total_gate_pairs = gate_pass_count + mahalanobis_gate_reject_count
    gate_pass_rate = (
        gate_pass_count / total_gate_pairs if total_gate_pairs > 0 else 0.0
    )
    return {
        "frame_count": len(association_logs),
        "gate_pass_count": gate_pass_count,
        "gate_reject_count": mahalanobis_gate_reject_count,
        "mahalanobis_gate_reject_count": mahalanobis_gate_reject_count,
        "assignment_above_gate_reject_count": assignment_above_gate_reject_count,
        "total_rejected_pair_count": total_rejected_pair_count,
        "total_track_detection_pair_count": total_gate_pairs,
        "gate_pass_rate": float(gate_pass_rate),
        "mean_frame_gate_pass_rate": _mean(frame_pass_rates),
        "matched_pair_count": matched_pair_count,
        "unmatched_track_count": unmatched_track_count,
        "unmatched_detection_count": unmatched_detection_count,
        "candidate_count_by_track": _distribution(candidate_counts_by_track),
        "candidate_count_by_detection": _distribution(candidate_counts_by_detection),
        "gate_threshold": _distribution(gate_threshold_values),
    }


def _summarize_motion_risk(
    association_logs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    motion_threshold = 1.0
    track_motion_values: list[float] = []
    pair_motion_values: list[float] = []
    matrix_motion_values: list[float] = []

    for log in association_logs:
        metadata = _merged_log_metadata(log)
        track_motion_values.extend(
            _numeric_values(metadata.get("motion_consistency_by_track", {}))
        )
        pair_motion_values.extend(
            _numeric_values(metadata.get("motion_consistency_by_pair", {}))
        )
        matrix_motion_values.extend(
            _numeric_values(metadata.get("motion_consistency_cost_matrix", []))
        )

    primary_values = track_motion_values or pair_motion_values or matrix_motion_values
    distribution = _distribution(primary_values)
    return {
        "motion_cost_threshold": motion_threshold,
        "motion_consistency_by_track": _distribution(track_motion_values),
        "motion_consistency_by_pair": _distribution(pair_motion_values),
        "motion_consistency_cost_matrix": _distribution(matrix_motion_values),
        "high_motion_track_frame_count": sum(
            1 for value in track_motion_values if value >= motion_threshold
        ),
        "mean_motion_risk_score": float(min(1.0, distribution["mean"] / 3.0)),
        "max_motion_risk_score": float(min(1.0, distribution["max"] / 3.0)),
        "latest_motion_consistency_by_track": _latest_float_mapping(
            association_logs,
            "motion_consistency_by_track",
        ),
    }


def _summarize_quality_risk(
    association_logs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    low_quality_threshold = 0.50
    high_association_risk_threshold = 0.50
    track_quality_values: list[float] = []
    association_risk_values: list[float] = []

    for log in association_logs:
        metadata = _merged_log_metadata(log)
        track_quality_values.extend(
            _numeric_values(metadata.get("track_quality_by_track", {}))
        )
        association_risk_values.extend(
            _numeric_values(metadata.get("association_risk_by_track", {}))
        )

    risk_distribution = _distribution(association_risk_values)
    return {
        "low_quality_threshold": low_quality_threshold,
        "high_association_risk_threshold": high_association_risk_threshold,
        "track_quality": _distribution(track_quality_values),
        "association_risk": risk_distribution,
        "low_quality_track_frame_count": sum(
            1 for value in track_quality_values if value < low_quality_threshold
        ),
        "high_association_risk_track_frame_count": sum(
            1
            for value in association_risk_values
            if value >= high_association_risk_threshold
        ),
        "mean_quality_risk_score": float(
            min(1.0, max(0.0, 1.0 - _mean(track_quality_values)))
        ),
        "max_association_risk_score": float(risk_distribution["max"]),
        "latest_track_quality_by_track": _latest_float_mapping(
            association_logs,
            "track_quality_by_track",
        ),
        "latest_association_risk_by_track": _latest_float_mapping(
            association_logs,
            "association_risk_by_track",
        ),
    }


def _summarize_threshold_sensitivity(
    threshold_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [dict(row) for row in threshold_rows]
    dense_crossing_rows = [
        row
        for row in rows
        if {"dense", "crossing"} & set(_scenario_tags_for_row(row))
    ]
    return {
        "row_count": len(rows),
        "gate_thresholds": _unique_floats(rows, "gate_threshold"),
        "risk_profiles": _unique_strings(rows, "risk_profile"),
        "risk_profile_versions": _unique_strings(rows, "risk_profile_version"),
        "association_risk_threshold_versions": _unique_strings(
            rows, "association_risk_threshold_version"
        ),
        "scenario_tags": sorted(
            {tag for row in rows for tag in _scenario_tags_for_row(row)}
        ),
        "target_count": _distribution(_float_values(rows, "target_count")),
        "id_switch_count": _distribution(_float_values(rows, "id_switch_count")),
        "track_continuity": _distribution(_float_values(rows, "track_continuity")),
        "duplicate_assignment_count": _distribution(
            _float_values(rows, "duplicate_assignment_count")
        ),
        "soft_risk_frame_rate": _distribution(
            _risk_frame_rates(rows, "soft_risk_frame_count")
        ),
        "hard_risk_frame_rate": _distribution(
            _risk_frame_rates(rows, "hard_risk_frame_count")
        ),
        "dense_crossing_row_count": len(dense_crossing_rows),
        "dense_crossing": _threshold_subset_summary(dense_crossing_rows),
        "recommended": _recommended_threshold_row(rows),
    }


def _threshold_subset_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "gate_thresholds": _unique_floats(rows, "gate_threshold"),
        "risk_profiles": _unique_strings(rows, "risk_profile"),
        "association_risk_threshold_versions": _unique_strings(
            rows, "association_risk_threshold_version"
        ),
        "target_count": _distribution(_float_values(rows, "target_count")),
        "id_switch_count": _distribution(_float_values(rows, "id_switch_count")),
        "track_continuity": _distribution(_float_values(rows, "track_continuity")),
        "duplicate_assignment_count": _distribution(
            _float_values(rows, "duplicate_assignment_count")
        ),
        "soft_risk_frame_rate": _distribution(
            _risk_frame_rates(rows, "soft_risk_frame_count")
        ),
        "hard_risk_frame_rate": _distribution(
            _risk_frame_rates(rows, "hard_risk_frame_count")
        ),
    }


def _recommended_threshold_row(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not rows:
        return None
    row = min(rows, key=_threshold_row_rank)
    keys = (
        "gate_threshold",
        "risk_profile",
        "risk_profile_version",
        "association_risk_threshold_version",
        "target_count",
        "id_switch_count",
        "track_continuity",
        "duplicate_assignment_count",
        "soft_risk_frame_count",
        "hard_risk_frame_count",
        "max_soft_risk_score",
        "max_hard_risk_score",
    )
    return {key: _json_ready(row.get(key)) for key in keys if key in row}


def _threshold_row_rank(row: Mapping[str, Any]) -> tuple[float, ...]:
    frame_count = float(row.get("frame_count", 0.0) or 0.0)
    hard_rate = (
        float(row.get("hard_risk_frame_count", 0.0) or 0.0) / frame_count
        if frame_count > 0
        else 0.0
    )
    soft_rate = (
        float(row.get("soft_risk_frame_count", 0.0) or 0.0) / frame_count
        if frame_count > 0
        else 0.0
    )
    return (
        float(row.get("id_switch_count", 0.0) or 0.0),
        float(row.get("duplicate_assignment_count", 0.0) or 0.0),
        hard_rate,
        -float(row.get("track_continuity", 0.0) or 0.0),
        soft_rate,
        float(row.get("gate_threshold", 0.0) or 0.0),
    )


def _summarize_calibration_group(
    key: tuple[float, str, str],
    rows: Sequence[Mapping[str, Any]],
    *,
    max_mean_id_switch_count: float,
    min_mean_track_continuity: float,
    max_mean_duplicate_assignment_count: float,
    max_mean_hard_risk_frame_rate: float,
) -> dict[str, Any]:
    gate_threshold, risk_profile, risk_profile_version = key
    id_switch_distribution = _distribution(_float_values(rows, "id_switch_count"))
    continuity_distribution = _distribution(_float_values(rows, "track_continuity"))
    duplicate_distribution = _distribution(
        _float_values(rows, "duplicate_assignment_count")
    )
    soft_count_distribution = _distribution(
        _float_values(rows, "soft_risk_frame_count")
    )
    hard_count_distribution = _distribution(
        _float_values(rows, "hard_risk_frame_count")
    )
    soft_rate_distribution = _distribution(
        _risk_frame_rates(rows, "soft_risk_frame_count")
    )
    hard_rate_distribution = _distribution(
        _risk_frame_rates(rows, "hard_risk_frame_count")
    )
    max_soft_score_distribution = _distribution(
        _float_values(rows, "max_soft_risk_score")
    )
    max_hard_score_distribution = _distribution(
        _float_values(rows, "max_hard_risk_score")
    )
    thresholds = _first_thresholds(rows)
    passes_governance = (
        id_switch_distribution["mean"] <= max_mean_id_switch_count
        and continuity_distribution["mean"] >= min_mean_track_continuity
        and duplicate_distribution["mean"] <= max_mean_duplicate_assignment_count
        and hard_rate_distribution["mean"] <= max_mean_hard_risk_frame_rate
    )
    seed_values = sorted(
        {
            str(seed)
            for row in rows
            if (seed := _metadata_value_for_row(row, "seed")) is not None
        }
    )
    scenario_values = sorted(
        {
            str(scenario)
            for row in rows
            if (
                scenario := _metadata_value_for_row(
                    row, "scenario_name", "scenario"
                )
            )
            is not None
        }
    )
    return {
        "gate_threshold": gate_threshold,
        "risk_profile": risk_profile,
        "risk_profile_version": risk_profile_version,
        "thresholds": thresholds,
        "episode_count": len(rows),
        "seed_count": len(seed_values),
        "seeds": seed_values,
        "scenarios": scenario_values,
        "target_count_distribution": _distribution(_float_values(rows, "target_count")),
        "id_switch_count": id_switch_distribution,
        "track_continuity": continuity_distribution,
        "duplicate_assignment_count": duplicate_distribution,
        "soft_risk_frame_count": soft_count_distribution,
        "hard_risk_frame_count": hard_count_distribution,
        "soft_risk_frame_rate": soft_rate_distribution,
        "hard_risk_frame_rate": hard_rate_distribution,
        "max_soft_risk_score": max_soft_score_distribution,
        "max_hard_risk_score": max_hard_score_distribution,
        "soft_risk_reasons": _risk_reasons(rows, "soft_risk_reasons"),
        "hard_risk_reasons": _risk_reasons(rows, "hard_risk_reasons"),
        "passes_governance": passes_governance,
        "recommendation_summary": {
            "mean_id_switch_count": id_switch_distribution["mean"],
            "mean_track_continuity": continuity_distribution["mean"],
            "mean_duplicate_assignment_count": duplicate_distribution["mean"],
            "mean_hard_risk_frame_rate": hard_rate_distribution["mean"],
        },
    }


def _calibration_recommendation_rank(summary: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        0 if summary["passes_governance"] else 1,
        summary["id_switch_count"]["p90"],
        summary["id_switch_count"]["mean"],
        -summary["track_continuity"]["mean"],
        summary["duplicate_assignment_count"]["mean"],
        summary["hard_risk_frame_rate"]["mean"],
        summary["soft_risk_frame_rate"]["mean"],
        summary["gate_threshold"],
        summary["risk_profile"],
        summary["risk_profile_version"],
    )


def _float_values(rows: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _risk_frame_rates(rows: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    rates: list[float] = []
    for row in rows:
        frame_count = float(row.get("frame_count", 0.0) or 0.0)
        if frame_count <= 0.0:
            continue
        rates.append(float(row.get(key, 0.0) or 0.0) / frame_count)
    return rates


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    sorted_values = sorted(float(value) for value in values)
    if not sorted_values:
        return {
            "count": 0,
            "min": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "values": [],
        }
    return {
        "count": len(sorted_values),
        "min": sorted_values[0],
        "p50": _percentile(sorted_values, 0.50),
        "p90": _percentile(sorted_values, 0.90),
        "max": sorted_values[-1],
        "mean": float(sum(sorted_values) / len(sorted_values)),
        "values": sorted_values,
    }


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = max(0.0, min(1.0, fraction)) * (len(sorted_values) - 1)
    lower = int(np.floor(position))
    upper = int(np.ceil(position))
    if lower == upper:
        return float(sorted_values[lower])
    weight = position - lower
    return float(sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight)


def _first_thresholds(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    for row in rows:
        risk_summary = row.get("risk_summary")
        if isinstance(risk_summary, Mapping):
            thresholds = risk_summary.get("thresholds")
            if isinstance(thresholds, Mapping):
                return _json_ready(dict(thresholds))
    return {}


def _risk_reasons(rows: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    reasons: set[str] = set()
    for row in rows:
        risk_summary = row.get("risk_summary")
        if not isinstance(risk_summary, Mapping):
            continue
        value = risk_summary.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            reasons.update(str(item) for item in value)
    return sorted(reasons)


def _log_mapping(log: Any) -> Mapping[str, Any]:
    if isinstance(log, Mapping):
        return log
    to_dict = getattr(log, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        if isinstance(value, Mapping):
            return value
    return {}


def _merged_log_metadata(log: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(_metadata_mapping(log.get("metadata")))
    risk_summary = log.get("risk_summary")
    if isinstance(risk_summary, Mapping):
        metadata.update(_metadata_mapping(risk_summary.get("metadata")))
    return metadata


def _sequence_value(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _pair_reason(pair: Any) -> str | None:
    if isinstance(pair, Mapping):
        value = pair.get("reason")
        return None if value is None else str(value)
    value = getattr(pair, "reason", None)
    return None if value is None else str(value)


def _numeric_values(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, np.ndarray):
        array = np.asarray(value, dtype=float).reshape(-1)
        return [float(item) for item in array if np.isfinite(item)]
    if isinstance(value, Mapping):
        values: list[float] = []
        for item in value.values():
            values.extend(_numeric_values(item))
        return values
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        values = []
        for item in value:
            values.extend(_numeric_values(item))
        return values
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return []
    return [numeric] if np.isfinite(numeric) else []


def _latest_float_mapping(
    association_logs: Sequence[Mapping[str, Any]],
    key: str,
) -> dict[str, float]:
    for log in reversed(association_logs):
        value = _merged_log_metadata(log).get(key)
        if not isinstance(value, Mapping):
            continue
        result: dict[str, float] = {}
        for item_key, item_value in value.items():
            try:
                numeric = float(item_value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(numeric):
                result[str(item_key)] = numeric
        if result:
            return result
    return {}


def _mean(values: Sequence[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _unique_floats(rows: Sequence[Mapping[str, Any]], key: str) -> list[float]:
    return sorted({float(value) for value in _float_values(rows, key)})


def _unique_strings(rows: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    return sorted(
        {
            str(row[key])
            for row in rows
            if key in row and row[key] is not None
        }
    )


def _scenario_tags_for_row(row: Mapping[str, Any]) -> list[str]:
    tags: set[str] = set()
    explicit_tags = row.get("scenario_tags")
    if isinstance(explicit_tags, Sequence) and not isinstance(
        explicit_tags, (str, bytes, bytearray)
    ):
        tags.update(str(tag) for tag in explicit_tags if tag is not None)

    text_values = [
        row.get("replay_name"),
        row.get("scenario_name"),
        row.get("scenario"),
        _metadata_value_for_row(row, "scenario_name", "scenario"),
        _metadata_value_for_row(row, "replay_name"),
    ]
    for value in text_values:
        if value is None:
            continue
        text = str(value).lower()
        if "dense" in text:
            tags.add("dense")
        if "crossing" in text or "cross" in text:
            tags.add("crossing")
    return sorted(tags)


def _metadata_value_for_row(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    metadata = row.get("replay_metadata")
    if isinstance(metadata, Mapping):
        return _metadata_value(metadata, *keys)
    return None


def _frames_from_payload(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        if is_d1_governed_replay_payload(payload):
            return d2_frames_from_d1_governed_replay(payload)
        for key in ("frames", "replay_frames", "records"):
            value = payload.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return [
                    _merge_envelope_metadata(frame, payload)
                    for item in value
                    if (frame := _coerce_frame(item))
                ]
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
    for key in (
        "frame",
        "d2_frame",
        "d2_input",
        "d2_replay_frame",
        "airsim_frame",
        "association_frame",
        "association_input",
        "replay_frame",
        "input_frame",
    ):
        value = record.get(key)
        if isinstance(value, Mapping) and _is_frame(value):
            return _merge_envelope_metadata(value, record)
    payload = record.get("payload")
    if isinstance(payload, Mapping):
        frame = _coerce_frame(payload)
        if frame is not None:
            return _merge_envelope_metadata(frame, record)
    return None


def _is_frame(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("detections", "tracks", "objects"))


def _target_count(frames: Sequence[Any]) -> int:
    truth_ids: set[str] = set()
    explicit_counts: list[int] = []
    max_frame_items = 0
    for frame in frames:
        truth_ids.update(_truth_ids_for_frame(frame))
        explicit_counts.extend(_explicit_target_counts(frame))
        max_frame_items = max(max_frame_items, len(_frame_items(frame)))
    if truth_ids:
        return len(truth_ids)
    if explicit_counts:
        return max(explicit_counts)
    return max_frame_items


def _truth_ids_for_frame(frame: Any) -> set[str]:
    truth_ids: set[str] = set()
    explicit = _first_present(
        frame,
        (
            "truth_ids_present",
            "truth_ids",
            "offline_truth_labels",
            "truth_offline_labels",
            "truth_labels",
        ),
        None,
    )
    truth_ids.update(_truth_label_values(explicit))
    for item in _frame_items(frame):
        truth_id = _first_present(
            item,
            (
                "offline_truth_label",
                "offline_truth_id",
                "truth_label",
                "truth_id",
                "ground_truth_id",
                "truth_object_id",
                "sim_truth_id",
                "actor_name",
                "object_id",
                "name",
            ),
            None,
        )
        if truth_id is not None:
            truth_ids.add(str(truth_id))
    return truth_ids


def _truth_label_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, Mapping):
        return {str(item) for item in value.values() if item is not None}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return {str(item) for item in value if item is not None}
    return {str(value)}


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


def _explicit_target_counts(frame: Any) -> list[int]:
    values = []
    for key in ("target_count", "drone_count", "intruder_count", "object_count"):
        value = _first_present(frame, (key,), None)
        if value is None:
            continue
        try:
            values.append(int(value))
        except (TypeError, ValueError):
            continue
    metadata = _first_present(frame, ("replay_metadata", "metadata"), None)
    if isinstance(metadata, Mapping):
        for key in ("target_count", "drone_count", "intruder_count", "object_count"):
            value = metadata.get(key)
            if value is None:
                continue
            try:
                values.append(int(value))
            except (TypeError, ValueError):
                continue
    return values


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
        truth_metrics_available=bool(payload.get("truth_metrics_available", False)),
        continuity_available=bool(
            payload.get(
                "continuity_available",
                payload.get("truth_metrics_available", False),
            )
        ),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _merge_envelope_metadata(
    frame: Mapping[str, Any],
    envelope: Mapping[str, Any],
) -> Mapping[str, Any]:
    metadata = _extract_replay_metadata(envelope)
    if not metadata:
        return frame
    merged = dict(frame)
    merged["replay_metadata"] = _merge_replay_metadata(
        _metadata_mapping(frame.get("replay_metadata")),
        metadata,
    )
    for key in (
        "seed",
        "episode_id",
        "run_id",
        "scenario_name",
        "scenario",
        "drone_count",
        "target_count",
        "intruder_count",
        "frame_index",
        "frame_id",
        "frame_number",
        "step",
        "tick",
        "measurement_timestamp",
        "arrival_timestamp",
        "threshold_profile_version",
        "risk_profile",
        "risk_profile_version",
        "offline_truth_labels",
        "truth_offline_labels",
        "truth_labels",
    ):
        if key in metadata and key not in merged:
            merged[key] = metadata[key]
    return merged


def _collect_replay_metadata(frames: Sequence[Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for frame in frames:
        if not isinstance(frame, Mapping):
            continue
        frame_metadata = _extract_replay_metadata(frame)
        nested_metadata = _metadata_mapping(frame.get("replay_metadata"))
        metadata = _merge_replay_metadata(metadata, frame_metadata, nested_metadata)
    return metadata


def _extract_replay_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "seed",
        "episode_id",
        "run_id",
        "scenario_name",
        "scenario",
        "drone_count",
        "target_count",
        "intruder_count",
        "replay_name",
        "threshold_profile_version",
        "risk_profile",
        "risk_profile_version",
        "frame_index",
        "frame_id",
        "frame_number",
        "step",
        "tick",
        "measurement_timestamp",
        "arrival_timestamp",
        "offline_truth_labels",
        "truth_offline_labels",
        "truth_labels",
    )
    metadata = {
        key: record[key]
        for key in keys
        if key in record and record[key] is not None
    }
    nested = _metadata_mapping(record.get("metadata"))
    for key in keys:
        if key in nested and nested[key] is not None:
            metadata.setdefault(key, nested[key])
    return metadata


def _merge_replay_metadata(
    *metadata_items: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for metadata in metadata_items:
        if metadata is None:
            continue
        for key, value in metadata.items():
            if value is None:
                continue
            if key not in merged:
                merged[str(key)] = value
                continue
            if merged[key] == value:
                continue
            merged[key] = _append_unique_value(merged[key], value)
    return merged


def _append_unique_value(current: Any, value: Any) -> Any:
    if isinstance(current, list):
        values = list(current)
    else:
        values = [current]
    if value not in values:
        values.append(value)
    return values


def _metadata_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metadata_value(metadata: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metadata:
            return _json_ready(metadata[key])
    return None


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
