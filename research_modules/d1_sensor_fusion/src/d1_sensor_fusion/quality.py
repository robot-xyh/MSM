from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from typing import Iterable

import numpy as np

from .types import (
    FusionQualityRegionSummary,
    FusionQualityRegionWindowSummary,
    LatencyAuditSummary,
    TrackUncertaintySummary,
)


def annotate_covariance_growth_rates(
    current: Iterable[TrackUncertaintySummary],
    previous: Iterable[TrackUncertaintySummary],
) -> list[TrackUncertaintySummary]:
    """Return current track summaries with covariance growth rates filled.

    The rate is the position covariance trace delta divided by publish-time
    delta. Missing previous summaries or non-positive time deltas leave the rate
    as ``None``.
    """

    previous_by_id = {
        _summary_key(summary): summary
        for summary in previous
    }
    annotated: list[TrackUncertaintySummary] = []
    for summary in current:
        previous_summary = previous_by_id.get(_summary_key(summary))
        rate = None
        if previous_summary is not None:
            dt = float(summary.published_at) - float(previous_summary.published_at)
            if dt > 0.0:
                rate = (
                    float(summary.position_covariance_trace)
                    - float(previous_summary.position_covariance_trace)
                ) / dt
        annotated.append(replace(summary, covariance_growth_rate=rate))
    return annotated


def summarize_region_quality_windows(
    region_snapshots: Iterable[Iterable[FusionQualityRegionSummary]],
    latency_audits: Iterable[LatencyAuditSummary] | None = None,
    *,
    covariance_growth_threshold: float = 0.0,
    freshness_growth_threshold: float = 0.0,
    readiness_drop_threshold: float = 0.0,
) -> list[FusionQualityRegionWindowSummary]:
    """Aggregate region-quality snapshots into lightweight trend windows."""

    grouped: dict[str, list[FusionQualityRegionSummary]] = defaultdict(list)
    for snapshot in region_snapshots:
        for summary in snapshot:
            grouped[str(summary.coverage_cell)].append(summary)

    latency_window = _latency_window(latency_audits or ())
    outputs: list[FusionQualityRegionWindowSummary] = []
    for coverage_cell in sorted(grouped):
        summaries = sorted(grouped[coverage_cell], key=lambda item: item.published_at)
        if not summaries:
            continue
        first = summaries[0]
        latest = summaries[-1]
        window_start = float(first.window_start if first.window_start is not None else first.published_at)
        window_end = float(latest.window_end if latest.window_end is not None else latest.published_at)
        dt = max(0.0, window_end - window_start)
        source_gap_modalities = tuple(
            sorted({modality for summary in summaries for modality in summary.source_gap_modalities})
        )
        source_gap_sample_count = sum(1 for summary in summaries if summary.source_gap_modalities)
        stale_track_sample_count = sum(1 for summary in summaries if summary.stale_track_count > 0)
        source_support = Counter()
        for key, value in latest.source_support.items():
            source_support[str(key)] = int(value)

        covariance_growth_rates = [
            float(value)
            for summary in summaries
            for value in (
                summary.mean_covariance_growth_rate,
                summary.max_covariance_growth_rate,
            )
            if value is not None
        ]
        mean_covariance_growth_rate = (
            float(np.mean(covariance_growth_rates)) if covariance_growth_rates else None
        )
        max_covariance_growth_rate = (
            float(max(covariance_growth_rates)) if covariance_growth_rates else None
        )
        mean_a95_growth_rate = _rate(latest.mean_a95_m - first.mean_a95_m, dt)
        measurement_age_growth_rate = _rate(
            latest.max_measurement_age_s - first.max_measurement_age_s,
            dt,
        )
        handover_readiness_delta = (
            float(latest.mean_handover_readiness) - float(first.mean_handover_readiness)
        )

        quality_flags = {
            str(flag)
            for summary in summaries
            for flag in summary.quality_flags
        }
        if source_gap_modalities:
            quality_flags.add("source_gap")
        if stale_track_sample_count > 0:
            quality_flags.add("stale_region")
        if _exceeds_positive(
            mean_covariance_growth_rate,
            threshold=covariance_growth_threshold,
        ) or _exceeds_positive(
            max_covariance_growth_rate,
            threshold=covariance_growth_threshold,
        ) or _exceeds_positive(
            mean_a95_growth_rate,
            threshold=covariance_growth_threshold,
        ):
            quality_flags.add("regional_covariance_growing")
        if _exceeds_positive(
            measurement_age_growth_rate,
            threshold=freshness_growth_threshold,
        ):
            quality_flags.add("freshness_degrading")
        if handover_readiness_delta < -abs(float(readiness_drop_threshold)):
            quality_flags.add("handover_readiness_degrading")
        if latency_window["max_delay_s"] > 0.0:
            quality_flags.add("latency_present")
        if (
            latency_window["oosm_observation_count"] > 0
            or latency_window["stale_observation_count"] > 0
        ):
            quality_flags.add("latency_or_oosm")

        outputs.append(
            FusionQualityRegionWindowSummary(
                coverage_cell=coverage_cell,
                window_start=window_start,
                window_end=window_end,
                sample_count=len(summaries),
                latest_published_at=float(latest.published_at),
                latest_track_count=int(latest.track_count),
                mean_a95_m=float(np.mean([summary.mean_a95_m for summary in summaries])),
                max_a95_m=float(max(summary.max_a95_m for summary in summaries)),
                mean_measurement_age_s=float(
                    np.mean([summary.max_measurement_age_s for summary in summaries])
                ),
                mean_handover_readiness=float(
                    np.mean([summary.mean_handover_readiness for summary in summaries])
                ),
                source_support=dict(source_support),
                source_gap_modalities=source_gap_modalities,
                source_gap_sample_count=source_gap_sample_count,
                stale_track_sample_count=stale_track_sample_count,
                mean_covariance_growth_rate=mean_covariance_growth_rate,
                max_covariance_growth_rate=max_covariance_growth_rate,
                mean_a95_growth_rate_mps=mean_a95_growth_rate,
                measurement_age_growth_rate=measurement_age_growth_rate,
                handover_readiness_delta=handover_readiness_delta,
                latency_observation_count=latency_window["observation_count"],
                oosm_observation_count=latency_window["oosm_observation_count"],
                stale_observation_count=latency_window["stale_observation_count"],
                max_delay_s=latency_window["max_delay_s"],
                mean_delay_s=latency_window["mean_delay_s"],
                quality_flags=tuple(sorted(quality_flags)),
            )
        )
    return outputs


def _summary_key(summary: TrackUncertaintySummary) -> str:
    return str(summary.global_track_id or summary.track_id)


def _rate(delta: float, dt: float) -> float | None:
    if dt <= 0.0:
        return None
    return float(delta) / float(dt)


def _exceeds_positive(value: float | None, *, threshold: float) -> bool:
    if value is None:
        return False
    return float(value) > abs(float(threshold))


def _latency_window(audits: Iterable[LatencyAuditSummary]) -> dict[str, float | int]:
    ordered = list(audits)
    if not ordered:
        return {
            "observation_count": 0,
            "oosm_observation_count": 0,
            "stale_observation_count": 0,
            "max_delay_s": 0.0,
            "mean_delay_s": 0.0,
        }
    first = ordered[0]
    latest = ordered[-1]
    if len(ordered) == 1:
        observation_count = int(latest.observation_count)
        oosm_count = int(latest.oosm_observation_count)
        stale_count = int(latest.stale_observation_count)
    else:
        observation_count = max(0, int(latest.observation_count) - int(first.observation_count))
        oosm_count = max(
            0,
            int(latest.oosm_observation_count) - int(first.oosm_observation_count),
        )
        stale_count = max(
            0,
            int(latest.stale_observation_count) - int(first.stale_observation_count),
        )
    return {
        "observation_count": observation_count,
        "oosm_observation_count": oosm_count,
        "stale_observation_count": stale_count,
        "max_delay_s": float(max(audit.max_delay_s for audit in ordered)),
        "mean_delay_s": float(latest.mean_delay_s),
    }
