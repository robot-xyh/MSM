# D3 Assignment Planner

Centralized rolling `M` target / `N` resource assignment research module.

Boundary: this module only supports offline simulation, evaluation, and human-review candidate planning. It excludes real fire-control parameters, damage logic, flight or hardware drivers, autonomous disposition, and authorization bypasses.

## Layout

- `PLAN.md`: engineering/scientific plan and mathematical formulation.
- `src/d3_assignment_planner/`: Python implementation.
- `tests/`: unit tests.
- `simulations/run_rolling_assignment.py`: 100 s, 2 Hz rolling simulation.
- `docs/ALGORITHM_AND_IMPLEMENTATION.md`: Chinese algorithm principles and implementation guide.
- `docs/EXPERIMENT_REPORT.md`: experiment method and latest local results.
- `docs/AIRSIM_INTEGRATION_PLAN.md`: AirSim offline integration plan.
- `results/`: generated CSV, JSON, plots, and generated report after running simulation.

## Test

```bash
cd /home/linux/Documents/MSM/research_modules/d3_assignment_planner
pytest
```

## Simulate

```bash
cd /home/linux/Documents/MSM/research_modules/d3_assignment_planner
python3 simulations/run_rolling_assignment.py
```

Optional fallback-only run:

```bash
python3 simulations/run_rolling_assignment.py --force-fallback
```

The default run uses 8 targets, 8 resources, 100 seconds, and 2 Hz. It compares no hysteresis with `delta=0.2` and `min_dwell=2.0`.

## Cross-Node Contract

`AssignmentPlan` and each `Assignment` expose cross-node metadata for integration dry runs: `source_node_id`, `target_node_id`, `link_type`, `plan_version`, `stale_after_s`, `terminal_feedback_state`, and `duplicate_terminal_lock_risk`. D3 also provides `evaluate_terminal_feedback(...)` to map D5 states into conservative recommendations:

`AssignmentPlanner` is stateful for one episode. Its first `plan(...)` call may use `previous_plan=None` and creates version 1. After the planner remembers an active plan, every later call must pass that exact active plan as `previous_plan`; omitting it raises `StalePlanError` with `reason="previous_plan_required"` and the active `latest_plan_id/latest_version`. Main must create a new planner instance for a new episode; D3 does not provide an implicit reset.

- `ambiguous` / `hold` -> `hold`
- `reacquire` -> `replan`
- `mismatch` or duplicate terminal lock risk -> `secondary_arbitration`

The feedback decision includes `main_action` and `planner_metadata` so main can apply a conservative integration action without local rebinding. The metadata explicitly carries `operator_hold_suggested`, `prohibit_assignment_suggested`, `feasibility_suggestion`, `fov_difficulty_suggestion`, optional `feasibility_by_resource`, optional `fov_difficulty_by_resource`, and optional `prohibited_edges`. `apply_terminal_feedback_to_planner_inputs(...)` maps that metadata into next-round `TargetTrack` and `ResourceState` DTOs: duplicate/explicit prohibited edges become `feasibility_by_resource=False`, fov/friend feedback increases `fov_difficulty_by_resource`, and friend/hold feedback sets `ResourceState.operator_hold`.

`ResourceState` also carries P0-B resource detail fields: `energy_fraction`, `availability_score`, `current_load`, `history_failure_rate`, `intercept_feasibility_by_target`, and `intercept_feasibility_score_by_target`. `CostModel` consumes them through `resource_state` subcomponents and hard infeasible flags, so D6-facing cost breakdowns can distinguish energy, availability, load, historical failure, and intercept feasibility causes.

`TargetTrack` supports a lightweight hard time-window baseline through explicit fields or metadata: `hard_time_window`, `time_window_open_at_s`, `time_window_close_at_s`, `time_window_state`, and resource-specific `time_window_by_resource`. When a window is explicitly closed, expired, or not yet open, `CostModel` marks that edge infeasible, sets hard-window reject flags in the breakdown, and `AssignmentPlanner` exports the rejected edge with a readable `reject_reason`; the soft `window_cost` term remains available for ordering open edges.

`compose_threat_score_baseline(...)` provides the P0-C explainable baseline for `TargetTrack.threat_score`. It combines critical-zone proximity, TTC, speed, covariance, and target state into a normalized score with components/reasons metadata. This is a baseline helper only; full outcome-aware dynamic threat assessment remains a P1 model-calibration item.

`PlannerConfig.reassignment_switch_penalty` is applied before Hungarian/fallback solve. For a target assigned in `previous_plan`, every feasible edge to a different resource receives the penalty; the edge to the same resource does not. Targets without a previous assignment and all unassigned costs are unchanged. The solver input matrix, per-edge breakdown `total`, selected `Assignment.cost`, plan objective, and exported evidence therefore share one cost value, with no post-solve double charge.

D3 also exports:

- `assignment_validity_summary_from_plan(...)` -> `AssignmentValiditySummary(plan_id, version, plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`.
- `assignment_records_from_plan(...)` -> D6-compatible `AssignmentRecord` rows with `timestamp`, `plan_id`, `version`, `resource_id`, `global_track_id`, `cost_breakdown`, `authorization_state`, `active`, `truth_id`, plus multi-seed current-plan fields: `window_id`, `decision_state`, `changed`, `resource_count`, `target_count`, `assigned_count`, `unassigned_high_threat_count`, `hysteresis_reject_count`, `stale_reject_count`, `reassign_count`, `assignment_matrix_shape`, `plan_owner`, `active_plan_owner`, `owner_node_id`, source/target/link, `plan_schema`, `replan_reason`, `takeover_reason`, previous/superseded plan id/version, secondary owner/version/epoch/lease fields, plan costs, `cost_margin`, `stale_after_s`, stale rejection metadata, and hysteresis explanation fields such as `hysteresis_state`, `hysteresis_reason`, `hysteresis_reasons`, `hysteresis_release_reason`, dwell/gain/change-limit flags, and high-threat release evidence.
- `assignment_evidence_from_plan(...)` -> `AssignmentEvidenceExport` with current plan id/version/owner/source fields, resource/target/assigned counts, full current cost matrix, per-edge cost breakdowns, rejected edges with per-edge `reject_reason`, hard-window reject reasons, stale rejection metadata, and secondary owner/source/version/supersede fields for D4/D6 replay.
- `summarize_assignment_mismatch_replay(...)` -> `AssignmentMismatchReplaySummary(resource_count, target_count, assigned_count, unassigned_high_threat_count, hysteresis_reject_count, stale_reject_count, reassign_count)` for N/M mismatch replay aggregation.
- `summarize_terminal_feedback_calibration(...)` -> advisory `TerminalFeedbackCalibrationSummary` from multi-seed assignment/feedback records. It reports duplicate/friend/fov/geometry reject counts and cost/hysteresis tuning directions, but never rewrites `CostWeights` or `PlannerConfig` defaults.
- `guidance_bindings_from_assignment_plan(...)` -> versioned `AssignmentGuidanceBinding` rows. Bindings carry `plan_schema`; D4-published `secondary_plan_v2` plans are bound by plan/version and validity state only.
- `prepare_secondary_takeover_plan(...)` -> stamps a D4/main-selected secondary takeover candidate with `secondary_plan_v2`, owner/source node, superseded center plan id/version, optional leader epoch/lease metadata, and `allow_local_rebind=False`. The helper rejects tied or older secondary versions.

`PlannerConfig.human_authorization_state` is the source of the plan authorization field. The planner records both `configured_human_authorization_state` and `effective_human_authorization_state` in plan metadata so main can run record-only simulation gates without hard-coding D3 to `"required"`.

For active degradation recovery, D3 does not emit D4 actions itself. When main/D4 requests `request_center_replan`, main calls D3 again with the current `previous_plan`; D3 publishes the next `AssignmentPlan.version`, and main/runtime annotates the bus record with `replan_reason`, `supersedes_plan_id`, `supersedes_plan_version`, and `active_plan_owner="center"`. A binding generated from that new current plan remains `active/current`, even when its resource-target pair changed; the old plan is invalidated by the current `plan_id/version` gate. D7 must reject stale, revoked, hold, or explicitly reassigned old bindings, not mislabel the new binding as superseded.

Main/runtime has connected D5 feedback writeback, center replan owner/version/source recording, secondary owner/version/source recording, and the P1 D4/D5 calibration sweep. The 2026-07-10 real AirSim baseline completed 60 connected 5v5 cases across seeds 1-10, 50/200 m secondary heights, and three degradation modes. It confirmed that D3 records can traverse the runtime, but all 20 requested secondary-takeover cases conservatively fell back to distributed operation: only 15 of 1300 D4 decisions reached momentary `takeover_ready`, all remained `pending_secondary_plan`, and `secondary_plan_active=0`. The next D3 work is therefore non-equal N/M replay, D5 feedback weight calibration, dynamic-threat/incremental/time-window calibration, and the cross-module contract from sustained readiness to one current secondary plan. D3 does not own D4 readiness or D6 storage.

Local resources must not rewrite `global_track_id`; D3 publishes versioned candidate plans for review. For `secondary_plan_v2`, D3 does not choose a concrete secondary node or enforce runtime leases; D4/main supplies the issuing node and recovery policy, while D3 validates the plan version and exports owner/source/version binding evidence. Normal operation uses Hungarian assignment. The established P1 OR-Tools scope is an optional same-input min-cost-flow comparator only; capacity, backup-resource, quota, and predictive rolling extensions remain later work. D4 secondary-node arbitration is preferred before CBBA-style fallback.

Current D3 regression baseline: `63 passed` with `python3 -m pytest -q research_modules/d3_assignment_planner/tests`.
