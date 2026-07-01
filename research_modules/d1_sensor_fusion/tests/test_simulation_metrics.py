from __future__ import annotations

from d1_sensor_fusion.simulation import run_simulation


def test_offline_simulation_metrics_and_latency_ablation() -> None:
    result = run_simulation(
        target_count=1,
        duration_s=20.0,
        dt=0.1,
        seed=13,
        output_dir=None,
        make_plots=False,
        write_report=False,
    )
    metrics = result.metrics
    assert metrics["observation_count"] >= 300
    assert metrics["compensated_rmse_m"] < 3.0
    assert metrics["uncompensated_rmse_m"] > 2.0 * metrics["compensated_rmse_m"]
    assert metrics["compensated_track_continuity"] > 0.9
    assert metrics["compensated_grading_accuracy"] > 0.95
    assert 0.5 <= metrics["mean_radar_latency_s"] <= 2.0
