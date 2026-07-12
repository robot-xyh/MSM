from __future__ import annotations

import copy
import math
from pathlib import Path

import pytest

import d1_sensor_fusion.p2_benchmark as p2_benchmark
from d1_sensor_fusion import (
    P2_BENCHMARK_SCHEMA_VERSION,
    load_frozen_governed_replay,
    run_p2_isolated_benchmark,
)


FIXTURE = Path(__file__).parent / "fixtures" / "p2_governed_filter_benchmark_v1.json"


def test_frozen_governed_replay_keeps_truth_offline_and_contract_fields() -> None:
    bundle = load_frozen_governed_replay(FIXTURE)

    assert bundle["manifest"]["working_frame"] == "ned"
    assert bundle["manifest"]["truth_policy"]["online"] == "stripped"
    assert bundle["offline_truth"]["frame_id"] == "ned"
    for record in bundle["records"]:
        assert record["arrival_timestamp"] >= record["measurement_timestamp"]
        assert record["frame_id"] == "ned"
        assert len(record["covariance"]) == len(record["measurement"]) == 4
        assert "offline_truth" not in record
        assert "truth_id" not in record.get("metadata", {})


def test_current_path_reports_rmse_nis_nees_and_elapsed_time() -> None:
    report = run_p2_isolated_benchmark(load_frozen_governed_replay(FIXTURE))

    assert report["schema_version"] == P2_BENCHMARK_SCHEMA_VERSION
    assert report["isolation"] == {
        "frozen_replay": True,
        "working_frame": "ned",
        "truth_usage": "offline_metrics_only",
        "default_online_path_changed": False,
    }
    current = report["backends"][0]
    metrics = current["metrics"]
    assert current["backend_id"] == "numpy_ekf_fixed_lag_current"
    assert current["status"] == "completed"
    assert current["unavailable_reason"] is None
    assert metrics["estimate_count"] == report["replay"]["observation_count"] == 6
    assert metrics["nis_sample_count"] == 5
    assert metrics["nees_sample_count"] == 6
    for name in (
        "position_rmse_m",
        "mean_nis",
        "mean_normalized_nis",
        "mean_nees",
        "mean_normalized_nees",
        "elapsed_ms",
    ):
        assert math.isfinite(metrics[name])
        assert metrics[name] >= 0.0
    assert metrics["position_rmse_m"] < 5.0


def test_optional_adapters_report_unavailable_reason_without_fake_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(p2_benchmark.importlib.util, "find_spec", lambda _name: None)
    report = run_p2_isolated_benchmark(load_frozen_governed_replay(FIXTURE))

    for result in report["backends"][1:]:
        assert result["status"] == "unavailable"
        assert result["dependency_available"] is False
        assert result["adapter_available"] is False
        assert result["unavailable_reason"]
        assert "is not installed" in result["unavailable_reason"]
        assert "no third-party filter was run" in result["unavailable_reason"]
        assert result["metrics"] == {
            "position_rmse_m": None,
            "mean_nis": None,
            "mean_normalized_nis": None,
            "mean_nees": None,
            "mean_normalized_nees": None,
            "elapsed_ms": None,
            "estimate_count": 0,
            "nis_sample_count": 0,
            "nees_sample_count": 0,
        }


def test_benchmark_rejects_truth_leakage_in_online_record() -> None:
    bundle = copy.deepcopy(load_frozen_governed_replay(FIXTURE))
    bundle["records"][0]["metadata"]["truth_id"] = "forbidden-online-label"

    with pytest.raises(ValueError, match="forbidden truth metadata"):
        run_p2_isolated_benchmark(bundle)
