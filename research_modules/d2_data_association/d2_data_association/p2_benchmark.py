"""Isolated optional-framework benchmark on one frozen D2 replay."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from .associators import JPDAAssociator, MHTAssociator
from .compat import (
    filterpy_filter_from_detection,
    probe_optional_dependency,
    to_stonesoup_detection,
)
from .dry_run_adapter import detections_from_airsim_frame
from .metrics import RiskThresholds
from .offline_truth import (
    OFFLINE_TRUTH_SCHEMA_VERSION,
    OfflineTruthLabel,
    strip_offline_truth_from_frames,
)
from .replay import run_airsim_replay_association
from .tracker import Tracker


P2_BENCHMARK_SCHEMA_VERSION = "d2-optional-framework-benchmark/v2"
DEFAULT_BENCHMARK_ADAPTERS = ("filterpy", "stonesoup", "jpda", "mht")


@dataclass(slots=True)
class OptionalBenchmarkResult:
    implementation: str
    framework: str
    implementation_kind: str
    dependency_available: bool
    executed: bool
    reason: str | None
    unavailable_reason: str | None
    dependency_version: str | None
    latency_seconds: float | None
    mean_latency_per_frame_seconds: float | None
    processed_detection_count: int
    id_switch_count: int | None
    id_switch_available: bool
    track_continuity: float | None
    continuity_available: bool
    metric_unavailable_reason: str | None
    full_jpda_implemented: bool = False
    full_mht_implemented: bool = False
    end_to_end_tracker_implemented: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "implementation": self.implementation,
            "framework": self.framework,
            "implementation_kind": self.implementation_kind,
            "dependency_available": self.dependency_available,
            "dependency_version": self.dependency_version,
            "executed": self.executed,
            "reason": self.reason,
            "unavailable_reason": self.unavailable_reason,
            "latency_seconds": self.latency_seconds,
            "mean_latency_per_frame_seconds": self.mean_latency_per_frame_seconds,
            "processed_detection_count": self.processed_detection_count,
            "id_switch_count": self.id_switch_count,
            "id_switch_available": self.id_switch_available,
            "track_continuity": self.track_continuity,
            "continuity_available": self.continuity_available,
            "metric_unavailable_reason": self.metric_unavailable_reason,
            "full_jpda_implemented": self.full_jpda_implemented,
            "full_mht_implemented": self.full_mht_implemented,
            "end_to_end_tracker_implemented": self.end_to_end_tracker_implemented,
        }


@dataclass(slots=True)
class P2BenchmarkReport:
    input_digest: str
    frame_count: int
    target_count: int
    results: list[OptionalBenchmarkResult]
    input_metadata: dict[str, Any]
    truth_schema_version: str = OFFLINE_TRUTH_SCHEMA_VERSION
    schema_version: str = P2_BENCHMARK_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "input_digest": self.input_digest,
            "frame_count": self.frame_count,
            "target_count": self.target_count,
            "input_metadata": self.input_metadata,
            "truth_schema_version": self.truth_schema_version,
            "default_online_path_unchanged": True,
            "results": [result.to_dict() for result in self.results],
            "claims": {
                "full_stonesoup_jpda_implemented": False,
                "full_stonesoup_mht_implemented": False,
                "filterpy_end_to_end_tracker_implemented": False,
            },
        }


def run_optional_framework_benchmark(
    frames: Sequence[Mapping[str, Any]],
    offline_truth_labels: Sequence[OfflineTruthLabel | Mapping[str, Any]],
    *,
    frameworks: Sequence[str] = DEFAULT_BENCHMARK_ADAPTERS,
    risk_thresholds: RiskThresholds | None = None,
) -> P2BenchmarkReport:
    """Compare the D2 baseline and research adapters on one frozen replay."""

    clean_frames = strip_offline_truth_from_frames(frames)
    labels = [
        label
        if isinstance(label, OfflineTruthLabel)
        else OfflineTruthLabel.from_mapping(label)
        for label in offline_truth_labels
    ]
    if not clean_frames:
        raise ValueError("benchmark replay must contain at least one frame")
    if not labels:
        raise ValueError("benchmark requires frozen offline truth labels")
    input_digest = _input_digest(clean_frames, labels)
    baseline_start = perf_counter()
    baseline_report = run_airsim_replay_association(
        clean_frames,
        replay_name="p2_frozen_replay_baseline",
        risk_thresholds=risk_thresholds,
        offline_truth_labels=labels,
    )
    baseline_elapsed = perf_counter() - baseline_start
    truth_available = bool(
        baseline_report.metrics.get("truth_metrics_available", False)
    )
    continuity_available = bool(
        baseline_report.metrics.get("continuity_available", False)
    )
    baseline_metric_unavailable_reason = (
        None
        if truth_available and continuity_available
        else "frozen_offline_truth_metrics_unavailable"
    )
    results = [
        OptionalBenchmarkResult(
            implementation="d2_gnn_hungarian",
            framework="numpy_scipy",
            implementation_kind="end_to_end_replay_association_baseline",
            dependency_available=True,
            dependency_version=None,
            executed=True,
            reason=None,
            unavailable_reason=baseline_metric_unavailable_reason,
            latency_seconds=baseline_elapsed,
            mean_latency_per_frame_seconds=baseline_elapsed / len(clean_frames),
            processed_detection_count=sum(
                len(frame.get("detections", [])) for frame in clean_frames
            ),
            id_switch_count=(
                int(baseline_report.metrics["id_switch_count"])
                if truth_available
                else None
            ),
            id_switch_available=truth_available,
            track_continuity=(
                float(baseline_report.metrics["track_continuity"])
                if continuity_available
                else None
            ),
            continuity_available=continuity_available,
            metric_unavailable_reason=baseline_metric_unavailable_reason,
            end_to_end_tracker_implemented=True,
        )
    ]
    normalized_frameworks = tuple(
        dict.fromkeys(str(value).strip().lower() for value in frameworks)
    )
    for framework in normalized_frameworks:
        if framework not in DEFAULT_BENCHMARK_ADAPTERS:
            raise ValueError(
                f"unsupported optional benchmark framework: {framework!r}"
            )
        if framework in {"jpda", "mht"}:
            results.append(
                _run_research_associator_benchmark(
                    clean_frames,
                    labels,
                    framework,
                    risk_thresholds=risk_thresholds,
                )
            )
        else:
            results.append(_run_object_adapter_benchmark(clean_frames, framework))
    return P2BenchmarkReport(
        input_digest=input_digest,
        frame_count=len(clean_frames),
        target_count=baseline_report.target_count,
        results=results,
        input_metadata=_benchmark_input_metadata(clean_frames),
    )


def write_p2_benchmark_report(
    path: str | Path,
    report: P2BenchmarkReport,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True))


def _run_research_associator_benchmark(
    frames: Sequence[Mapping[str, Any]],
    labels: Sequence[OfflineTruthLabel],
    adapter_name: str,
    *,
    risk_thresholds: RiskThresholds | None,
) -> OptionalBenchmarkResult:
    if adapter_name == "jpda":
        associator = JPDAAssociator(
            gate_threshold=9.21,
            feature_weight=6.0,
            min_marginal_probability=0.30,
            max_joint_hypotheses=4096,
        )
        implementation = "d2_jpda_research_adapter"
    else:
        associator = MHTAssociator(
            gate_threshold=9.21,
            feature_weight=6.0,
            max_hypotheses=16,
            max_history=5,
            max_generated_assignments=512,
        )
        implementation = "d2_mht_research_adapter"
    start = perf_counter()
    try:
        report = run_airsim_replay_association(
            frames,
            replay_name=f"p2_frozen_replay_{adapter_name}",
            tracker=Tracker(associator=associator),
            risk_thresholds=risk_thresholds,
            offline_truth_labels=labels,
        )
    except Exception as exc:
        unavailable_reason = (
            f"research_adapter_execution_failed: {type(exc).__name__}: {exc}"
        )
        return OptionalBenchmarkResult(
            implementation=implementation,
            framework="d2_builtin_research",
            implementation_kind="end_to_end_replay_research_adapter",
            dependency_available=True,
            dependency_version=None,
            executed=False,
            reason=unavailable_reason,
            unavailable_reason=unavailable_reason,
            latency_seconds=None,
            mean_latency_per_frame_seconds=None,
            processed_detection_count=0,
            id_switch_count=None,
            id_switch_available=False,
            track_continuity=None,
            continuity_available=False,
            metric_unavailable_reason=unavailable_reason,
            full_jpda_implemented=False,
            full_mht_implemented=False,
            end_to_end_tracker_implemented=True,
        )
    elapsed = perf_counter() - start
    truth_available = bool(report.metrics.get("truth_metrics_available", False))
    continuity_available = bool(report.metrics.get("continuity_available", False))
    metric_unavailable_reason = (
        None
        if truth_available and continuity_available
        else "frozen_offline_truth_metrics_unavailable"
    )
    return OptionalBenchmarkResult(
        implementation=implementation,
        framework="d2_builtin_research",
        implementation_kind="end_to_end_replay_research_adapter",
        dependency_available=True,
        dependency_version=None,
        executed=True,
        reason=None,
        unavailable_reason=metric_unavailable_reason,
        latency_seconds=elapsed,
        mean_latency_per_frame_seconds=elapsed / len(frames),
        processed_detection_count=sum(
            len(frame.get("detections", [])) for frame in frames
        ),
        id_switch_count=(
            int(report.metrics["id_switch_count"]) if truth_available else None
        ),
        id_switch_available=truth_available,
        track_continuity=(
            float(report.metrics["track_continuity"])
            if continuity_available
            else None
        ),
        continuity_available=continuity_available,
        metric_unavailable_reason=metric_unavailable_reason,
        full_jpda_implemented=False,
        full_mht_implemented=False,
        end_to_end_tracker_implemented=True,
    )


def _run_object_adapter_benchmark(
    frames: Sequence[Mapping[str, Any]],
    framework: str,
) -> OptionalBenchmarkResult:
    status = probe_optional_dependency(framework)
    implementation = (
        "filterpy_cv_object_adapter"
        if framework == "filterpy"
        else "stonesoup_detection_object_adapter"
    )
    common = {
        "implementation": implementation,
        "framework": framework,
        "implementation_kind": "object_adapter_smoke_only",
        "dependency_available": status.available,
        "dependency_version": status.version,
        "id_switch_count": None,
        "id_switch_available": False,
        "track_continuity": None,
        "continuity_available": False,
        "metric_unavailable_reason": "adapter_only_no_end_to_end_association",
    }
    if not status.available:
        return OptionalBenchmarkResult(
            **common,
            executed=False,
            reason=status.reason,
            unavailable_reason=status.reason,
            latency_seconds=None,
            mean_latency_per_frame_seconds=None,
            processed_detection_count=0,
        )

    detections_by_frame = []
    for frame_index, frame in enumerate(frames):
        _, detections, _ = detections_from_airsim_frame(
            frame,
            frame_index=frame_index,
        )
        if any(detection.truth_id is not None for detection in detections):
            raise ValueError("optional benchmark received truth-bearing online detection")
        detections_by_frame.append(detections)
    processed_count = 0
    start = perf_counter()
    try:
        for detections in detections_by_frame:
            for detection in detections:
                if framework == "stonesoup":
                    to_stonesoup_detection(detection)
                else:
                    filter_object = filterpy_filter_from_detection(detection)
                    filter_object.predict()
                    filter_object.update(
                        np.asarray(detection.position, dtype=float).reshape(2, 1)
                    )
                processed_count += 1
    except Exception as exc:
        unavailable_reason = (
            f"adapter_execution_failed: {type(exc).__name__}: {exc}"
        )
        return OptionalBenchmarkResult(
            **common,
            executed=False,
            reason=unavailable_reason,
            unavailable_reason=unavailable_reason,
            latency_seconds=None,
            mean_latency_per_frame_seconds=None,
            processed_detection_count=processed_count,
        )
    elapsed = perf_counter() - start
    return OptionalBenchmarkResult(
        **common,
        executed=True,
        reason=None,
        unavailable_reason="adapter_only_no_end_to_end_association",
        latency_seconds=elapsed,
        mean_latency_per_frame_seconds=elapsed / len(frames),
        processed_detection_count=processed_count,
    )


def _input_digest(
    frames: Sequence[Mapping[str, Any]],
    labels: Iterable[OfflineTruthLabel],
) -> str:
    payload = {
        "frames": frames,
        "offline_truth_labels": [label.to_dict() for label in labels],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _benchmark_input_metadata(
    frames: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    metadata = frames[0].get("replay_metadata", {})
    if not isinstance(metadata, Mapping):
        return {"source_format": "unknown"}
    result = {
        "source_format": str(metadata.get("source_format", "airsim_replay")),
        "episode_id": metadata.get("episode_id"),
        "scenario_name": metadata.get("scenario_name"),
    }
    adapter = metadata.get("d1_governed_adapter")
    if isinstance(adapter, Mapping):
        result["d1_governed_adapter"] = dict(adapter)
    return result
