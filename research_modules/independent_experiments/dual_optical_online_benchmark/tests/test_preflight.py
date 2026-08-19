from __future__ import annotations

from pathlib import Path

import pytest

from dual_optical_online_benchmark.batch import (
    PREFLIGHT_SCENARIOS,
    PREFLIGHT_SCHEMA_VERSION,
    PREFLIGHT_SEEDS,
    _preflight_acceptance,
    _preflight_selection_key,
    run_phase,
    validate_preflight_summary,
)
from dual_optical_online_benchmark.contracts import BenchmarkProtocol, write_json
from dual_optical_online_benchmark.tracking import SharedTrackerConfig


def _rows(rate: float = 0.9):
    return [
        {
            "diagnostic_scenario": scenario,
            "seed": seed,
            "median_track_purity": 0.95,
            "common_confirmed_rate": rate,
            "common_confirmed_identity_count": 90,
        }
        for scenario, _, _ in PREFLIGHT_SCENARIOS
        for seed in PREFLIGHT_SEEDS
    ]


def test_preflight_acceptance_requires_complete_3x3_matrix() -> None:
    accepted = _preflight_acceptance(_rows())
    assert accepted["accepted"] is True
    incomplete = _preflight_acceptance(_rows()[:-1])
    assert incomplete["accepted"] is False
    assert "complete_nine_episode_matrix" in incomplete["failure_reasons"]


def test_preflight_prefers_tight_single_hypothesis_after_acceptance() -> None:
    def candidate(gate: float, hypotheses: int, rate: float):
        rows = _rows(rate)
        return {
            "config": {
                "motion_initialization_residual_gate_m": gate,
                "maximum_global_hypotheses": hypotheses,
            },
            "acceptance": _preflight_acceptance(rows),
        }

    candidates = (
        candidate(3.0, 1, 0.86),
        candidate(3.0, 3, 0.95),
        candidate(5.0, 1, 0.94),
    )
    selected = max(candidates, key=_preflight_selection_key)
    assert selected["config"] == {
        "motion_initialization_residual_gate_m": 3.0,
        "maximum_global_hypotheses": 1,
    }


def test_preflight_summary_rejects_failed_or_incomplete_evidence(tmp_path) -> None:
    protocol = BenchmarkProtocol()
    tracker = SharedTrackerConfig()
    path = tmp_path / "preflight_summary.json"
    rows = _rows()
    write_json(
        path,
        {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "protocol_fingerprint": protocol.fingerprint,
            "test_data_accessed": False,
            "selected_tracker_config": tracker.__dict__,
            "shared_tracker_fingerprint": tracker.fingerprint,
            "acceptance": _preflight_acceptance(rows),
            "rows": rows,
        },
    )
    validate_preflight_summary(path, protocol)
    payload = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "protocol_fingerprint": protocol.fingerprint,
        "test_data_accessed": False,
        "acceptance": {"accepted": False},
        "rows": rows,
    }
    write_json(path, payload)
    with pytest.raises(ValueError, match="acceptance"):
        validate_preflight_summary(path, protocol)


def test_formal_calibration_cannot_launch_without_preflight(tmp_path) -> None:
    protocol = BenchmarkProtocol()
    with pytest.raises(RuntimeError, match="preflight"):
        run_phase(
            repo_root=tmp_path,
            output_root=tmp_path / "raw",
            dataset_root=tmp_path / "dataset",
            seeds=protocol.train_seeds + protocol.validation_seeds,
            phase="calibration",
            blocks_script=Path("missing-blocks.sh"),
            preflight_summary=None,
        )
