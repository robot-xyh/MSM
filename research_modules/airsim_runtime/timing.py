"""Stage timing contracts for the main AirSim runtime.

The timing layer is observational only. It never feeds latency measurements
back into assignment, association, degradation, terminal locking, or guidance.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
from pathlib import Path
import time
from typing import Any, Iterator, Sequence


MAIN_BUS_STAGE_NAMES = (
    "communication",
    "d1_fusion",
    "d2_association",
    "d6_track_recording",
    "d3_assignment",
    "coalition_commit",
    "d5_terminal_association",
    "d4_arbitration",
    "d7_guidance_contract",
    "link_and_cross_view_recording",
)

CONTROL_TICK_STAGE_NAMES = (
    "airsim_frame_sample",
    "bus_processing",
    "control_evidence_and_pair_sync",
    "guidance_and_control_rpc",
)


class StageTimingCapture:
    """Capture non-overlapping stage durations against one monotonic clock."""

    def __init__(
        self,
        *,
        schema_version: str,
        scope: str,
        total_stage_name: str,
        stage_names: Sequence[str],
        frame_index: int,
        timestamp_s: float,
        budget_ms: float,
    ) -> None:
        if not math.isfinite(float(budget_ms)) or float(budget_ms) <= 0.0:
            raise ValueError("stage timing budget_ms must be positive and finite")
        if not stage_names or len(set(stage_names)) != len(stage_names):
            raise ValueError("stage_names must be non-empty and unique")
        self.schema_version = str(schema_version)
        self.scope = str(scope)
        self.total_stage_name = str(total_stage_name)
        self.stage_names = tuple(str(name) for name in stage_names)
        self.frame_index = int(frame_index)
        self.timestamp_s = float(timestamp_s)
        self.budget_ms = float(budget_ms)
        self._started = time.perf_counter()
        self._stages_ms: dict[str, float | None] = {
            name: None for name in self.stage_names
        }
        self._stage_status: dict[str, str] = {
            name: "not_applicable" for name in self.stage_names
        }
        self._finalized: dict[str, Any] | None = None

    @contextmanager
    def measure(self, stage_name: str) -> Iterator[None]:
        """Measure one stage, preserving its duration when it raises."""

        if stage_name not in self._stages_ms:
            raise KeyError(f"unknown timing stage: {stage_name}")
        if self._stage_status[stage_name] != "not_applicable":
            raise RuntimeError(f"timing stage already measured: {stage_name}")
        started = time.perf_counter()
        self._stage_status[stage_name] = "executing"
        try:
            yield
        except BaseException:
            self._stage_status[stage_name] = "error"
            raise
        else:
            self._stage_status[stage_name] = "available"
        finally:
            self._stages_ms[stage_name] = max(
                0.0, (time.perf_counter() - started) * 1000.0
            )

    def finalize(self, *, error: BaseException | None = None) -> dict[str, Any]:
        if self._finalized is not None:
            return dict(self._finalized)
        total_ms = max(0.0, (time.perf_counter() - self._started) * 1000.0)
        measured_sum_ms = sum(
            float(value) for value in self._stages_ms.values() if value is not None
        )
        # Timer bookkeeping can only add to the enclosing measurement. Clamp
        # sub-microsecond clock noise rather than publishing a negative residual.
        unattributed_ms = max(0.0, total_ms - measured_sum_ms)
        record = {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "frame_index": self.frame_index,
            "timestamp_s": self.timestamp_s,
            "budget_ms": self.budget_ms,
            "total_stage_name": self.total_stage_name,
            "stages_ms": dict(self._stages_ms),
            "stage_status": dict(self._stage_status),
            "measured_stage_sum_ms": measured_sum_ms,
            "unattributed_ms": unattributed_ms,
            "total_ms": total_ms,
            "budget_exceeded": total_ms > self.budget_ms,
            "error_type": "" if error is None else type(error).__name__,
            "error_message": "" if error is None else str(error),
        }
        self._finalized = record
        return dict(record)


def summarize_stage_timings(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return availability-aware per-stage and total timing distributions."""

    if not records:
        return {
            "schema_version": "main-stage-timing-summary-v1",
            "availability": "unavailable",
            "unavailable_reason": "stage_timing_records_missing",
            "record_count": 0,
            "total": _distribution([]),
            "stages": {},
            "dominant_stage": None,
            "budget_violation_count": None,
        }

    stage_names: list[str] = []
    for record in records:
        for name in dict(record.get("stages_ms", {})):
            if name not in stage_names:
                stage_names.append(name)
    stages: dict[str, Any] = {}
    for name in stage_names:
        values: list[float] = []
        statuses: dict[str, int] = {}
        for record in records:
            status = str(dict(record.get("stage_status", {})).get(name, "missing"))
            statuses[status] = statuses.get(status, 0) + 1
            value = dict(record.get("stages_ms", {})).get(name)
            if status in {"available", "error"} and _finite_nonnegative(value):
                values.append(float(value))
        stages[name] = {
            **_distribution(values),
            "status_counts": statuses,
        }

    total_values = [
        float(record["total_ms"])
        for record in records
        if _finite_nonnegative(record.get("total_ms"))
    ]
    dominant_candidates = [
        (name, data.get("mean_ms"))
        for name, data in stages.items()
        if data.get("mean_ms") is not None
    ]
    dominant_stage = (
        max(dominant_candidates, key=lambda item: float(item[1]))[0]
        if dominant_candidates
        else None
    )
    return {
        "schema_version": "main-stage-timing-summary-v1",
        "availability": "available" if total_values else "unavailable",
        "unavailable_reason": "" if total_values else "valid_total_samples_missing",
        "scope": str(records[0].get("scope", "")),
        "record_count": len(records),
        "total": _distribution(total_values),
        "unattributed": _distribution(
            [
                float(record["unattributed_ms"])
                for record in records
                if _finite_nonnegative(record.get("unattributed_ms"))
            ]
        ),
        "stages": stages,
        "dominant_stage": dominant_stage,
        "budget_violation_count": sum(
            1 for record in records if record.get("budget_exceeded") is True
        ),
        "error_record_count": sum(
            1 for record in records if str(record.get("error_type", ""))
        ),
    }


def write_stage_timings_jsonl(
    path: Path, records: Sequence[dict[str, Any]]
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    clean = sorted(float(value) for value in values if _finite_nonnegative(value))
    if not clean:
        return {
            "availability": "unavailable",
            "sample_count": 0,
            "mean_ms": None,
            "p95_ms": None,
            "max_ms": None,
        }
    return {
        "availability": "available",
        "sample_count": len(clean),
        "mean_ms": sum(clean) / len(clean),
        "p95_ms": _percentile(clean, 0.95),
        "max_ms": clean[-1],
    }


def _percentile(values: Sequence[float], quantile: float) -> float:
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * float(quantile)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(values[lower])
    weight = position - lower
    return float(values[lower] * (1.0 - weight) + values[upper] * weight)


def _finite_nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )
