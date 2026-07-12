from __future__ import annotations

from dataclasses import replace

import pytest

import d5_terminal_association.p2_geometry_benchmark as benchmark
from d5_terminal_association.p2_geometry_benchmark import (
    OpenCvGeometryBenchmarkConfig,
    run_opencv_geometry_perturbation_benchmark,
)


@pytest.mark.skipif(
    not benchmark.opencv_geometry_benchmark_available(),
    reason="OpenCV calib3d unavailable",
)
def test_default_benchmark_recovers_projection_and_gate_quality() -> None:
    result = run_opencv_geometry_perturbation_benchmark()

    assert result.status == "available"
    assert result.metrics["sample_count"] == 48
    assert result.metrics["projection_rmse_post_pnp_px"] < 0.15 * result.metrics[
        "projection_rmse_pre_pnp_px"
    ]
    assert result.metrics["gate_acceptance_rate_post_pnp"] > result.metrics[
        "gate_acceptance_rate_pre_pnp"
    ]
    assert result.metrics["false_acceptance_rate_post_pnp"] < result.metrics[
        "false_acceptance_rate_pre_pnp"
    ]
    assert result.metrics["truth_identity_used_online"] is False
    assert all(record.metadata["offline_truth_only"] for record in result.records)
    assert all(not record.metadata["truth_used_for_gate"] for record in result.records)


@pytest.mark.skipif(
    not benchmark.opencv_geometry_benchmark_available(),
    reason="OpenCV calib3d unavailable",
)
def test_benchmark_is_reproducible_for_fixed_seed() -> None:
    first = run_opencv_geometry_perturbation_benchmark()
    second = run_opencv_geometry_perturbation_benchmark()

    assert first.metrics == second.metrics
    assert first.records == second.records


@pytest.mark.skipif(
    not benchmark.opencv_geometry_benchmark_available(),
    reason="OpenCV calib3d unavailable",
)
def test_timestamp_bias_increases_measurement_and_arrival_projection_error() -> None:
    baseline_config = OpenCvGeometryBenchmarkConfig(
        measurement_timestamp_bias_s=0.0,
        nominal_arrival_latency_s=0.0,
        arrival_timestamp_bias_s=0.0,
    )
    biased_config = replace(
        baseline_config,
        measurement_timestamp_bias_s=0.5,
        nominal_arrival_latency_s=0.4,
        arrival_timestamp_bias_s=0.6,
    )

    baseline = run_opencv_geometry_perturbation_benchmark(baseline_config)
    biased = run_opencv_geometry_perturbation_benchmark(biased_config)

    assert biased.metrics["projection_rmse_post_pnp_px"] > baseline.metrics[
        "projection_rmse_post_pnp_px"
    ]
    assert biased.metrics["projection_rmse_arrival_time_px"] > baseline.metrics[
        "projection_rmse_arrival_time_px"
    ]


@pytest.mark.skipif(
    not benchmark.opencv_geometry_benchmark_available(),
    reason="OpenCV calib3d unavailable",
)
def test_offline_truth_labels_do_not_change_geometry_or_gate_metrics() -> None:
    first = run_opencv_geometry_perturbation_benchmark(
        OpenCvGeometryBenchmarkConfig(offline_truth_label_prefix="truth-A")
    )
    second = run_opencv_geometry_perturbation_benchmark(
        OpenCvGeometryBenchmarkConfig(offline_truth_label_prefix="truth-B")
    )

    assert first.metrics == second.metrics
    assert [record.offline_truth_label for record in first.records] != [
        record.offline_truth_label for record in second.records
    ]
    assert [record.mahalanobis_true_post_pnp for record in first.records] == [
        record.mahalanobis_true_post_pnp for record in second.records
    ]


def test_opencv_unavailable_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark, "_HAS_CV2", False)
    monkeypatch.setattr(benchmark, "cv2", None)

    result = run_opencv_geometry_perturbation_benchmark()

    assert result.status == "unavailable"
    assert result.reason == "opencv_calib3d_unavailable"
    assert result.records == ()
    assert result.metrics == {}
    assert result.metadata["truth_policy"] == "offline_scoring_only"
