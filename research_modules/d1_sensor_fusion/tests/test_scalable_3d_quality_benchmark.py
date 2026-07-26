from __future__ import annotations

import json

import numpy as np
import pytest

from d1_sensor_fusion import (
    D1QualityBenchmarkConfig,
    D1QualityMetric,
    build_anonymous_quality_scenario,
    run_d1_quality_benchmark,
    run_d1_quality_benchmark_batch,
    write_d1_quality_benchmark_outputs,
)
from d1_sensor_fusion.online_anonymization import (
    assert_online_observations_identity_free,
)


@pytest.mark.parametrize("target_count", [5, 20, 50, 100, 200])
def test_quality_scenario_is_scale_parameterized_and_truth_isolated(
    target_count: int,
) -> None:
    config = D1QualityBenchmarkConfig(
        target_count=target_count,
        duration_s=0.61,
        scan_period_s=0.30,
        warmup_s=0.10,
        seed=1200 + target_count,
    )

    online, sidecar = build_anonymous_quality_scenario(config)
    observations = tuple(
        observation
        for scan in online.scans
        for observation in scan.observations
    )

    assert online.entity_count == target_count
    assert len(sidecar.trajectories) == target_count
    assert sidecar.usage == "offline_evaluation_only"
    assert sidecar.content_digest
    assert len(sidecar.lineage_records) == len(observations)
    assert len({item.source_lineage for item in sidecar.lineage_records}) == len(
        sidecar.lineage_records
    )
    assert tuple(scan.arrival_timestamp for scan in online.scans) == tuple(
        sorted(scan.arrival_timestamp for scan in online.scans)
    )
    assert all(
        observation.measurement.shape == (4,)
        and observation.covariance is not None
        and observation.covariance.shape == (4, 4)
        and np.isfinite(observation.measurement).all()
        and np.isfinite(observation.covariance).all()
        and observation.arrival_timestamp >= observation.measurement_timestamp
        for observation in observations
    )
    assert_online_observations_identity_free(
        observations,
        identity_tokens=sidecar.truth_ids,
    )
    serialized_online = repr(online)
    assert all(truth_id not in serialized_online for truth_id in sidecar.truth_ids)
    assert all(
        "truth" not in observation.metadata
        and "actor" not in observation.metadata
        and "object" not in observation.metadata
        and "target_id" not in observation.metadata
        for observation in observations
    )


def test_small_quality_benchmark_reports_lineage_metrics_without_d2_identity() -> None:
    result = run_d1_quality_benchmark(
        D1QualityBenchmarkConfig(
            target_count=5,
            duration_s=1.21,
            scan_period_s=0.30,
            warmup_s=0.20,
            miss_probability=0.25,
            minimum_false_alarm_rate=4.0,
            oosm_probability=0.0,
            seed=1301,
        )
    )

    assert result.online_truth_use_count == 0
    assert result.d2_global_track_id_write_count == 0
    assert result.final_track_count >= 5
    assert result.oosm_observation_count > 0
    assert result.condition_counts["delayed_scan_count"] >= 1
    assert result.condition_counts["missed_detection_count"] > 0
    assert result.condition_counts["false_alarm_observation_count"] > 0
    assert result.metrics["warmup_recall_rate"].available
    assert result.metrics["position_rmse_m"].available
    assert result.metrics["nees_mean"].available
    assert result.metrics["nis_mean"].available
    assert result.metrics["lineage_mapping_coverage_rate"].value == pytest.approx(1.0)
    assert (
        result.metrics["lineage_mapping_coverage_rate"].sample_count
        == result.accepted_observation_count
    )
    assert result.metrics["scan_processing_time_p50_ms"].value >= 0.0
    assert result.metrics["scan_processing_time_p95_ms"].value >= 0.0


def test_unavailable_quality_metric_cannot_zero_fill() -> None:
    metric = D1QualityMetric(
        available=False,
        value=None,
        sample_count=0,
        unit="m",
        reason="no_lineage_aligned_track_truth_pairs",
    )

    assert metric.to_dict()["value"] is None
    assert metric.to_dict()["reason"] == "no_lineage_aligned_track_truth_pairs"
    with pytest.raises(ValueError, match="value=None"):
        D1QualityMetric(
            available=False,
            value=0.0,
            sample_count=0,
            unit="m",
            reason="missing",
        )


def test_twenty_seed_fast_batch_and_output_writer(tmp_path) -> None:
    base = D1QualityBenchmarkConfig(
        target_count=5,
        duration_s=0.61,
        scan_period_s=0.30,
        warmup_s=0.10,
        miss_probability=0.10,
        false_alarm_rate_per_target=0.0,
        minimum_false_alarm_rate=0.0,
        oosm_probability=0.0,
        seed=1,
    )

    batch = run_d1_quality_benchmark_batch(
        target_counts=(5,),
        seeds=range(2000, 2020),
        base_config=base,
    )
    json_path, report_path = write_d1_quality_benchmark_outputs(batch, tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert len(batch.seed_results) == 20
    assert batch.scale_summaries[0].seed_count == 20
    assert payload["seed_result_count"] == 20
    assert payload["constraints"]["online_truth_use_count"] == 0
    assert payload["constraints"]["d2_global_track_id_write_count"] == 0
    assert payload["constraints"]["default_fusion_algorithm_modified"] is False
    assert payload["constraints"]["track_lifecycle_modified"] is False
    assert "D1 可扩展真值隔离质量基准" in report_path.read_text(
        encoding="utf-8"
    )
