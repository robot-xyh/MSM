from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

import numpy as np

from .fusion import FusionAdapter
from .observations import radar_covariance_from_range, radar_h
from .types import GlobalTrack, SensorObservation


OPAQUE_SOURCE_IDENTITY_CACHE_PERFORMANCE_SCHEMA_VERSION = (
    "d1.opaque_source_identity_cache_performance.v1"
)
MINIMUM_MEDIAN_IMPROVEMENT_FRACTION = 0.02
MINIMUM_CANDIDATE_FASTER_FRACTION = 0.70


def compare_opaque_source_identity_cache_variants(
    *,
    repetitions: int = 7,
    track_count: int = 200,
    releases_per_sample: int = 56,
    cache_capacity: int = 1_024,
) -> dict[str, Any]:
    """Run a pre-warmed, interleaved source-only publication benchmark."""

    if repetitions < 7:
        raise ValueError("repetitions must be at least 7")
    if track_count < 1:
        raise ValueError("track_count must be positive")
    if releases_per_sample < 1:
        raise ValueError("releases_per_sample must be positive")
    if cache_capacity < track_count:
        raise ValueError(
            "cache_capacity must cover track_count for the admission benchmark"
        )

    reference = _build_adapter(
        cached=False,
        track_count=track_count,
        cache_capacity=cache_capacity,
    )
    candidate = _build_adapter(
        cached=True,
        track_count=track_count,
        cache_capacity=cache_capacity,
    )

    reference_warmup = reference.global_tracks()
    candidate_warmup = candidate.global_tracks()
    warmup_digest = _track_digest(reference_warmup)
    warmup_equivalent = (
        warmup_digest == _track_digest(candidate_warmup)
    )

    samples: dict[str, list[dict[str, Any]]] = {
        "reference": [],
        "candidate": [],
    }
    for repetition in range(repetitions):
        order = (
            (("reference", reference), ("candidate", candidate))
            if repetition % 2 == 0
            else (("candidate", candidate), ("reference", reference))
        )
        for name, adapter in order:
            samples[name].append(
                _run_sample(
                    adapter,
                    releases_per_sample=releases_per_sample,
                )
            )

    reference_summary = _summarize_samples(samples["reference"])
    candidate_summary = _summarize_samples(samples["candidate"])
    reference_times = [
        float(item["wall_time_s"])
        for item in samples["reference"]
    ]
    candidate_times = [
        float(item["wall_time_s"])
        for item in samples["candidate"]
    ]
    candidate_faster_count = sum(
        candidate_time < reference_time
        for reference_time, candidate_time in zip(
            reference_times,
            candidate_times,
            strict=True,
        )
    )
    candidate_faster_fraction = (
        candidate_faster_count / repetitions
    )
    reference_median = float(
        reference_summary["median_wall_time_s"]
    )
    candidate_median = float(
        candidate_summary["median_wall_time_s"]
    )
    median_improvement_fraction = (
        1.0 - candidate_median / reference_median
        if reference_median > 0.0
        else 0.0
    )

    reference_diagnostics = (
        reference.opaque_source_identity_cache_diagnostics()
    )
    candidate_diagnostics = (
        candidate.opaque_source_identity_cache_diagnostics()
    )
    reference_digests = {
        item["global_track_payload_sha256"]
        for item in samples["reference"]
    }
    candidate_digests = {
        item["global_track_payload_sha256"]
        for item in samples["candidate"]
    }
    semantic_acceptance = {
        "warmup_payload_equivalent": warmup_equivalent,
        "every_sample_payload_equivalent": (
            len(reference_digests) == 1
            and reference_digests == candidate_digests
            and warmup_digest in reference_digests
        ),
        "track_count_preserved": all(
            int(item["track_count"]) == track_count
            for group in samples.values()
            for item in group
        ),
        "reference_counter_conservation": all(
            reference_diagnostics["conservation"].values()
        ),
        "candidate_counter_conservation": all(
            candidate_diagnostics["conservation"].values()
        ),
        "candidate_cache_bounded": (
            int(candidate_diagnostics["cache_entry_count"])
            <= cache_capacity
            and int(
                candidate_diagnostics["operation_counts"][
                    "peak_entry_count"
                ]
            )
            <= cache_capacity
        ),
        "request_count_preserved": (
            int(
                reference_diagnostics["operation_counts"][
                    "request_count"
                ]
            )
            == int(
                candidate_diagnostics["operation_counts"][
                    "request_count"
                ]
            )
        ),
        "candidate_uses_hits_after_warmup": (
            int(
                candidate_diagnostics["operation_counts"][
                    "cache_hit_count"
                ]
            )
            > 0
        ),
    }
    performance_acceptance = {
        "median_improvement_at_least_2_percent": (
            median_improvement_fraction
            >= MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
        ),
        "candidate_faster_fraction_at_least_70_percent": (
            candidate_faster_fraction
            >= MINIMUM_CANDIDATE_FASTER_FRACTION
        ),
    }
    module_threshold_met = bool(
        all(semantic_acceptance.values())
        and all(performance_acceptance.values())
    )

    return {
        "schema_version": (
            OPAQUE_SOURCE_IDENTITY_CACHE_PERFORMANCE_SCHEMA_VERSION
        ),
        "validation_date": "2026-07-25",
        "benchmark_scope": (
            "D1 source-only opaque identity publication hotspot; "
            "not the no-source default path and not a system realtime gate"
        ),
        "configuration": {
            "repetitions": int(repetitions),
            "warmup_count_per_variant": 1,
            "interleaved_order": True,
            "track_count": int(track_count),
            "releases_per_sample": int(releases_per_sample),
            "materializations_per_sample": int(
                track_count * releases_per_sample
            ),
            "publish_opaque_source_key": True,
            "radar_assignment_ambiguity_hold_evidence": False,
            "cache_capacity": int(cache_capacity),
        },
        "preregistered_policy": {
            "minimum_median_improvement_fraction": (
                MINIMUM_MEDIAN_IMPROVEMENT_FRACTION
            ),
            "minimum_candidate_faster_fraction": (
                MINIMUM_CANDIDATE_FASTER_FRACTION
            ),
            "candidate_remains_default_off": True,
        },
        "reference": {
            **reference_summary,
            "diagnostics": reference_diagnostics,
        },
        "candidate": {
            **candidate_summary,
            "diagnostics": candidate_diagnostics,
        },
        "comparison": {
            "median_improvement_fraction": (
                median_improvement_fraction
            ),
            "median_speedup": (
                reference_median / candidate_median
                if candidate_median > 0.0
                else None
            ),
            "candidate_faster_count": int(
                candidate_faster_count
            ),
            "candidate_faster_fraction": (
                candidate_faster_fraction
            ),
            "semantic_acceptance": semantic_acceptance,
            "performance_acceptance": performance_acceptance,
            "module_threshold_met": module_threshold_met,
            "recommend_main_source_only_ab": module_threshold_met,
            "recommend_default_promotion": False,
        },
        "constraints": {
            "state_covariance_timestamp_recomputed_per_publication": True,
            "a95_track_level_last_nis_recomputed_per_publication": True,
            "global_track_count_preserved": True,
            "online_truth_use_count": 0,
            "no_source_default_path_claimed": False,
            "system_realtime_claimed": False,
        },
    }


def write_opaque_source_identity_cache_report(
    report: dict[str, Any],
    *,
    json_path: str | Path,
    markdown_path: str | Path,
) -> None:
    json_destination = Path(json_path)
    markdown_destination = Path(markdown_path)
    json_destination.parent.mkdir(parents=True, exist_ok=True)
    markdown_destination.parent.mkdir(parents=True, exist_ok=True)
    json_destination.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    comparison = report["comparison"]
    reference = report["reference"]
    candidate = report["candidate"]
    status = (
        "达到模块门槛"
        if comparison["module_threshold_met"]
        else "性能准入否决"
    )
    markdown_destination.write_text(
        "\n".join(
            (
                "# D1 不透明来源标识缓存微基准",
                "",
                "## 结论",
                "",
                f"- 模块判定：**{status}**。",
                (
                    f"- reference 中位耗时："
                    f"`{reference['median_wall_time_s']:.6f} s`。"
                ),
                (
                    f"- candidate 中位耗时："
                    f"`{candidate['median_wall_time_s']:.6f} s`。"
                ),
                (
                    f"- 中位墙钟改善："
                    f"`{100.0 * comparison['median_improvement_fraction']:.3f}%`。"
                ),
                (
                    f"- candidate 更快比例："
                    f"`{comparison['candidate_faster_count']}/"
                    f"{report['configuration']['repetitions']}`，即 "
                    f"`{100.0 * comparison['candidate_faster_fraction']:.1f}%`。"
                ),
                (
                    "- 预注册门槛：中位改善不低于 `2%`，"
                    "candidate 更快比例不低于 `70%`。"
                ),
                "",
                "## 边界",
                "",
                (
                    "基准显式开启 source-only 不透明来源标识发布，未开启 "
                    "hold。候选只缓存节点、代际和 D1 航迹编号确定的三个"
                    "不可变字符串。"
                ),
                (
                    "无 source-key 的默认路径不调用该缓存。本结果不代表"
                    "默认 R0 主线收益，也不代表系统实时准入。"
                ),
                (
                    "候选保持默认关闭。达到模块门槛时，只建议 main 继续"
                    "进行 clean source-only A/B 矩阵。"
                ),
                "",
            )
        ),
        encoding="utf-8",
    )


def _build_adapter(
    *,
    cached: bool,
    track_count: int,
    cache_capacity: int,
) -> FusionAdapter:
    adapter = FusionAdapter(
        publish_opaque_source_key=True,
        radar_assignment_ambiguity_hold_evidence=False,
        publisher_node_id="D1-PUBLICATION-BENCHMARK",
        publisher_epoch="source-only-benchmark-20260725",
        cached_opaque_source_identity=cached,
        opaque_source_identity_cache_capacity=cache_capacity,
        immutable_shared_publication_metadata=True,
    )
    observations = []
    for index in range(track_count):
        position = np.array(
            [
                1_000.0 + 80.0 * index,
                -500.0 + 5.0 * (index % 200),
                -100.0 - 2.0 * (index % 5),
            ],
            dtype=float,
        )
        state = np.concatenate((position, np.zeros(3)))
        measurement = radar_h(state, np.zeros(3))
        observations.append(
            SensorObservation(
                observation_id=f"opaque-benchmark-{index:05d}",
                sensor_id="RADAR-OPAQUE-BENCHMARK",
                modality="radar",
                measurement_timestamp=0.0,
                arrival_timestamp=0.2,
                frame_id="ned",
                measurement=measurement,
                covariance=radar_covariance_from_range(
                    float(measurement[0])
                ),
                classification_hint=(
                    "fixed-wing" if index % 2 == 0 else "rotorcraft"
                ),
                confidence=0.9,
                metadata={
                    "sensor_position_ned": np.zeros(3),
                    "scan_id": "opaque-benchmark-birth-scan",
                    "source_lineage_key": (
                        "explicit",
                        "RADAR-OPAQUE-BENCHMARK",
                        "opaque-benchmark-birth-scan",
                        index,
                    ),
                },
            )
        )
    result = adapter.process_scan_batch(tuple(observations))
    if len(result.tracks) != track_count:
        raise RuntimeError(
            "benchmark setup did not create the requested track count"
        )
    return adapter


def _run_sample(
    adapter: FusionAdapter,
    *,
    releases_per_sample: int,
) -> dict[str, Any]:
    tracks: list[GlobalTrack] = []
    started = perf_counter()
    for _ in range(releases_per_sample):
        tracks = adapter.global_tracks()
    wall_time_s = perf_counter() - started
    return {
        "wall_time_s": float(wall_time_s),
        "track_count": len(tracks),
        "global_track_payload_sha256": _track_digest(tracks),
    }


def _summarize_samples(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    wall_times = [
        float(item["wall_time_s"])
        for item in samples
    ]
    return {
        "sample_count": len(samples),
        "wall_time_samples_s": wall_times,
        "median_wall_time_s": float(median(wall_times)),
        "minimum_wall_time_s": float(min(wall_times)),
        "maximum_wall_time_s": float(max(wall_times)),
        "global_track_payload_sha256": (
            samples[0]["global_track_payload_sha256"]
        ),
    }


def _track_digest(tracks: list[GlobalTrack]) -> str:
    payload = json.dumps(
        [track.to_dict() for track in tracks],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the D1 source-only opaque identity cache microbenchmark."
        )
    )
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--track-count", type=int, default=200)
    parser.add_argument("--releases-per-sample", type=int, default=56)
    parser.add_argument("--cache-capacity", type=int, default=1_024)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()

    report = compare_opaque_source_identity_cache_variants(
        repetitions=args.repetitions,
        track_count=args.track_count,
        releases_per_sample=args.releases_per_sample,
        cache_capacity=args.cache_capacity,
    )
    write_opaque_source_identity_cache_report(
        report,
        json_path=args.json_output,
        markdown_path=args.markdown_output,
    )
    print(
        json.dumps(
            report["comparison"],
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
