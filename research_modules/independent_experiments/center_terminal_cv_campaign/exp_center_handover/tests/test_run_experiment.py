from __future__ import annotations

import json
from inspect import signature

import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.fixture import (
    build_offline_fixture,
    write_handover_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.run_experiment import (
    parse_args,
    run,
)


def test_public_run_writes_fixed_metrics_report_and_no_truth_leak(tmp_path) -> None:
    fixture_dir = write_handover_fixture(
        tmp_path / "fixture", build_offline_fixture(target_count=20, seed=20260816)
    )
    output_dir = tmp_path / "output"
    result = run(
        fixture_dir=fixture_dir,
        output_dir=output_dir,
        mode="offline",
        association_backend="geometry",
    )
    assert result.paths.metrics == output_dir / "metrics.json"
    assert result.paths.report == output_dir / "REPORT_CN.md"
    metrics = json.loads(result.paths.metrics.read_text(encoding="utf-8"))
    assert metrics["binding_precision"] == 1.0
    assert metrics["binding_recall"] == 1.0
    assert metrics["truth_leakage_count"] == 0
    assert metrics["unregistered_candidate_count_semantics"] == (
        "final_frame_unmatched_camera_local_track_count"
    )
    assert "局部航迹数量" in result.paths.report.read_text(encoding="utf-8")
    assert result.paths.projection_figure.stat().st_size > 0
    assert result.paths.matrix_figure.stat().st_size > 0


def test_cli_exposes_main_integration_arguments(tmp_path) -> None:
    args = parse_args(
        (
            "--fixture-dir",
            str(tmp_path / "fixture"),
            "--output-dir",
            str(tmp_path / "output"),
            "--mode",
            "offline",
            "--association-backend",
            "gnn",
        )
    )
    assert args.fixture_dir == tmp_path / "fixture"
    assert args.replay_manifest is None
    assert args.output_dir == tmp_path / "output"
    assert args.mode == "offline"
    assert args.association_backend == "gnn"


def test_cli_accepts_unified_replay_manifest(tmp_path) -> None:
    args = parse_args(
        (
            "--replay-manifest",
            str(tmp_path / "replay.json"),
            "--output-dir",
            str(tmp_path / "output"),
        )
    )
    assert args.fixture_dir is None
    assert args.replay_manifest == tmp_path / "replay.json"


def test_public_airsim_runner_defaults_to_five_observation_frames() -> None:
    assert signature(run).parameters["frame_timestamps"].default == (
        0.2,
        0.3,
        0.4,
        0.5,
        0.6,
    )


def test_optional_gnn_backend_requires_explicit_saved_model(tmp_path) -> None:
    fixture_dir = write_handover_fixture(
        tmp_path / "fixture", build_offline_fixture(target_count=5, seed=20260816)
    )
    with pytest.raises(ValueError, match="explicit model_path"):
        run(
            fixture_dir=fixture_dir,
            output_dir=tmp_path / "output",
            mode="offline",
            association_backend="gnn",
        )
