from __future__ import annotations

from pathlib import Path

from integrated_simulation import make_standard_scenario, run_integrated_episode


def test_nominal_5v5_episode_runs_and_writes_outputs(tmp_path: Path) -> None:
    config = make_standard_scenario("nominal_5v5", seed=11, duration_s=5.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    assert result.metrics.detection_probability > 0.7
    assert result.metrics.track_rmse >= 0.0
    assert result.metrics.duplicate_assignment_count == 0
    assert result.metrics.terminal_association_accuracy >= 0.8
    assert result.output_paths["episode_log"].exists()
    assert result.output_paths["report_md"].exists()
    assert result.output_paths["guidance_csv"].exists()
    assert result.guidance_summaries
    assert any(summary["terminal_mode_entered"] for summary in result.guidance_summaries)
    assert any(decision.action == "continue_center" for decision in result.decisions)


def test_center_destroyed_passively_degrades_to_secondary(tmp_path: Path) -> None:
    config = make_standard_scenario("center_destroyed", seed=12, duration_s=6.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    actions = {decision.action for decision in result.decisions}
    modes = {decision.mode for decision in result.decisions}
    assert "passive_failover" in modes
    assert "degrade_to_secondary" in actions
    assert result.metrics.failover_time >= 0.0
    assert result.metrics.consensus_rounds >= 0.0


def test_secondary_destroyed_falls_back_to_distributed(tmp_path: Path) -> None:
    config = make_standard_scenario("secondary_destroyed", seed=13, duration_s=6.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    assert any(
        decision.mode == "passive_failover" and decision.action == "degrade_to_distributed"
        for decision in result.decisions
    )


def test_active_terminal_mismatch_triggers_active_degradation(tmp_path: Path) -> None:
    config = make_standard_scenario("active_terminal_mismatch", seed=14, duration_s=6.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    assert any(
        decision.mode == "active_degradation"
        and decision.action in {"degrade_to_secondary", "degrade_to_distributed"}
        for decision in result.decisions
    )
    assert result.metrics.terminal_association_accuracy < 1.0


def test_friend_overlap_forces_hold_for_review(tmp_path: Path) -> None:
    config = make_standard_scenario("friend_overlap_hold", seed=15, duration_s=6.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    assert any(decision.action == "hold_for_review" for decision in result.decisions)
    assert result.metrics.friend_overlap_hold_count > 0
    assert result.metrics.human_override_count > 0
