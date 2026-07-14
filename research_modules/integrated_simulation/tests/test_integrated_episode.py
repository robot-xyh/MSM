from __future__ import annotations

from pathlib import Path

import integrated_simulation.runner as runner_module
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


def test_centralized_cooperative_3v1_and_5v2_satisfy_atomic_demands(
    tmp_path: Path,
) -> None:
    for scenario_name in ("cooperative_3v1", "cooperative_5v2"):
        output_dir = tmp_path / scenario_name
        config = make_standard_scenario(scenario_name, seed=21, duration_s=5.0)

        result = run_integrated_episode(config, output_dir=output_dir)

        assert result.metrics.target_demand_satisfaction_rate_micro == 1.0
        assert result.metrics.unmet_slot_count == 0
        assert result.metrics.duplicate_assignment_count == 0
        assert result.metrics.erroneous_duplicate_lock_count == 0
        assert result.output_paths["episode_log"].exists()


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


def test_active_terminal_mismatch_requests_assist_then_center_replan(
    tmp_path: Path,
) -> None:
    config = make_standard_scenario("active_terminal_mismatch", seed=14, duration_s=6.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    active_actions = {
        decision.action
        for decision in result.decisions
        if decision.mode == "active_degradation"
    }
    assert "request_secondary_assist" in active_actions
    assert "request_center_replan" in active_actions
    assert not active_actions.intersection(
        {"degrade_to_secondary", "degrade_to_distributed"}
    )
    assert result.metrics.terminal_association_accuracy < 1.0


def test_friend_overlap_forces_hold_for_review(tmp_path: Path) -> None:
    config = make_standard_scenario("friend_overlap_hold", seed=15, duration_s=6.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    assert any(decision.action == "hold_for_review" for decision in result.decisions)
    assert result.metrics.friend_overlap_hold_count > 0
    assert result.metrics.human_override_count > 0


def test_stale_assignment_retains_current_plan_without_version_reset(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_plan = runner_module.AssignmentPlanner.plan
    previous_plan_arguments = []

    def reject_second_plan(self, *args, **kwargs):
        previous_plan = kwargs.get("previous_plan")
        previous_plan_arguments.append(previous_plan)
        if len(previous_plan_arguments) == 2:
            raise runner_module.StalePlanError(
                "injected stale plan",
                reason="stale_previous_version",
                previous_plan_id=previous_plan.plan_id,
                previous_version=previous_plan.version,
                latest_plan_id=previous_plan.plan_id,
                latest_version=previous_plan.version,
            )
        return original_plan(self, *args, **kwargs)

    monkeypatch.setattr(runner_module.AssignmentPlanner, "plan", reject_second_plan)
    config = make_standard_scenario("nominal_5v5", seed=16, duration_s=3.0)

    result = run_integrated_episode(config, output_dir=tmp_path)

    assert len(previous_plan_arguments) >= 3
    assert previous_plan_arguments[0] is None
    assert all(plan is not None for plan in previous_plan_arguments[1:])
    episode_log = result.output_paths["episode_log"].read_text(encoding="utf-8")
    assert '"event_type": "d3_stale_plan_rejected"' in episode_log
