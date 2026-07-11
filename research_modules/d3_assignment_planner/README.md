# D3 Assignment Planner

Centralized rolling `M` target / `N` resource assignment research module.

Boundary: this module only supports offline simulation, evaluation, and human-review candidate planning. It excludes real fire-control parameters, damage logic, flight or hardware drivers, autonomous disposition, and authorization bypasses.

## Layout

- `PLAN.md`: engineering/scientific plan and mathematical formulation.
- `src/d3_assignment_planner/`: Python implementation.
- `src/d3_assignment_planner/fixtures.py`: versioned 5v5/3v5/5v3/new-target/resource-failure calibration fixtures.
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

## M-to-N Demand Slots

`AssignmentPlan` now publishes `assignment_plan_v2`. A `TargetTrack` with no
`demand` keeps the original `k=1`, `independent`, Hungarian behavior. An
explicit `TargetDemand()` selects the high-threat research default `k=3`,
`hybrid`: two `primary` members in wave 0 and one `reserve` in wave 1.
`TargetDemand.primary_resource_count` controls that split and defaults to 2;
main's `--cooperative-primary-count` should be passed into this field. It must
satisfy `1 <= primary_resource_count <= required_resource_count`. The implicit
and explicit independent `k=1` demand uses `primary_resource_count=1`.

The `hungarian_demand_slots` path expands each target into role/wave/capability
slots, prioritizes higher-threat targets, and performs all-or-none admission.
An incomplete coalition publishes no executable `Assignment`; its
`CoalitionPlan` and `DemandSatisfactionSummary` retain candidate members plus
`demand_required`, `demand_assigned`, `demand_shortfall`, and completion state.
`simultaneous`, `sequential`, `hybrid`, and `independent` scheduling modes are
supported. Arrival windows, wave interval, minimum separation, and required
capability counts are explicit demand fields.

Use `assignments_by_target()` for multiplicity and `assignment_by_resource()`
for the resource index. The legacy `assignment_map()` remains valid for
one-to-one plans and raises `ValueError` for multi-resource targets. Stable
assignment signatures drive hysteresis, change counts, and switch penalties;
coalition member/role/window changes increment coalition version. D7 bindings
carry coalition identity, role, wave, mode, window, and minimum separation, and
only a current committed coalition can produce an active binding.
Changing `primary_resource_count` also changes the coalition demand signature,
increments coalition version, and is exported in binding fields/metadata.
`AssignmentPlan.execution_signature()` additionally covers executable bindings,
coalition state/members, role/wave/windows, owner, and activation/lease semantics.
Only a change to that signature advances `plan_id/version`; an ordinary refresh
with the same signature retains `plan_id`, `version`, `created_at`, and each
assignment's `plan_version`, and returns `changed=False`. Plan and assignment
metadata use `identity_created_at_s` for that stable identity creation time and
`last_evaluated_at_s` for the current `plan()` timestamp. A no-change or forced
no-change refresh advances only `last_evaluated_at_s`; a real identity change
sets both timestamps to the new planning timestamp.

OR-Tools is not a default dependency. `MinCostFlowAssignmentSolver` is an
optional same-input benchmark and reports a clear unavailable state when
`ortools` is absent; the default planner does not select it.

## Cross-Node Contract

`AssignmentPlan` and each `Assignment` expose cross-node metadata for integration dry runs: `source_node_id`, `target_node_id`, `link_type`, `plan_version`, `stale_after_s`, `terminal_feedback_state`, and `duplicate_terminal_lock_risk`. D3 also provides `evaluate_terminal_feedback(...)` to map D5 states into conservative recommendations:

`AssignmentPlanner` is stateful for one episode. Its first `plan(...)` call may use `previous_plan=None` and creates version 1. Stale checks use only the latest published identity. `plan(..., publish=False)` returns a candidate without advancing latest, and `publish_plan(candidate)` publishes a reviewed candidate. After a plan is published, later calls must pass that exact active identity as `previous_plan`; omitting it raises `StalePlanError` with `reason="previous_plan_required"`. Main must create a new planner instance for a new episode; D3 does not provide an implicit reset.

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
- `assignment_records_from_plan(...)` and `assignment_evidence_from_plan(...)` -> D6/main outputs containing current plan identity, `identity_created_at_s`, `last_evaluated_at_s`, N/M shape, costs/reject reasons, hysteresis state, secondary audit fields, plus `assignment_profile_schema`, cost/feedback profile id/version, the exact cost-weight snapshot, and planner thresholds. A record without an explicit export timestamp uses `last_evaluated_at_s`, not the stable identity creation time.
- `summarize_assignment_mismatch_replay(...)` -> `AssignmentMismatchReplaySummary(resource_count, target_count, assigned_count, unassigned_high_threat_count, hysteresis_reject_count, stale_reject_count, reassign_count)` for N/M mismatch replay aggregation.
- `summarize_terminal_feedback_calibration(...)` -> advisory `TerminalFeedbackCalibrationSummary` from multi-seed assignment/feedback records. It reports duplicate/friend/fov/geometry reject counts and cost/hysteresis tuning directions, but never rewrites `CostWeights` or `PlannerConfig` defaults.
- `guidance_bindings_from_assignment_plan(...)` -> versioned `AssignmentGuidanceBinding` rows whose metadata includes identity creation and last evaluation timestamps. Binding freshness and `expires_at_s` use `last_evaluated_at_s`, with `created_at` as the fallback for legacy/manual plans. Main supplies the current `plan_id/version` when exporting a secondary binding; a historical plan, an unconfirmed secondary current identity, an inactive takeover, or an expired lease cannot produce an `active/current` D7 binding.
- `prepare_secondary_takeover_plan(...)` -> activates a D4/main-selected takeover candidate only after main supplies sustained `takeover_ready`, activation time, a live lease, and a positive monotonic leader epoch. A same-signature candidate may retain the current center identity; the helper advances identity exactly once for the owner/activation transition. Successful plans audit readiness, activation, supersede, owner, lease, epoch, and `allow_local_rebind=False` in plan, assignment, record, evidence, and binding metadata.
- `continue_active_secondary_plan(...)` -> converts the next ordinary rolling candidate into a same-owner secondary plan without a second takeover. It derives the concrete owner/source from the previous active plan, requires strict version/supersede continuity, sustained readiness, non-regressing epoch, and a live non-regressing lease; main must not hand-build these metadata fields.
- `build_p1_assignment_fixtures()` -> versioned deterministic 5v5, 3v5, 5v3, new-target, and resource-failure inputs. Labels use `resources x targets`; explicit counts are also present in fixture metadata.

`PlannerConfig.human_authorization_state` is the source of the plan authorization field. The planner records both `configured_human_authorization_state` and `effective_human_authorization_state` in plan metadata so main can run record-only simulation gates without hard-coding D3 to `"required"`.

For active degradation recovery, D3 does not emit D4 actions itself. Main calls `plan(..., forced_replan=True)` with the current published plan. If executable semantics are unchanged, D3 preserves identity and returns `decision_state="replan_ack_no_change"`; if they change, D3 advances identity once and returns `decision_state="replan_applied"`. Main/runtime integrates these states and any `replan_reason`/supersede metadata. A binding from an applied current plan remains `active/current`; the old published identity is stale.

Main/runtime has connected D5 feedback writeback, center replan owner/version/source recording, secondary owner/version/source recording, and the P1 D4/D5 calibration sweep. For secondary flow, main should request `publish=False`, apply `prepare_secondary_takeover_plan()` or `continue_active_secondary_plan()`, then call `publish_plan()` on the final owner-stamped plan. This prevents an intermediate center candidate from advancing published latest.

The 2026-07-11 no-truth integration smoke test ran three short real AirSim 5v5 episodes with every D2 `truth_id=None`. D3 still produced assignment coverage `1.0`, monotonically versioned plans, and valid D5/D7 bindings from center-owned D2 track IDs. This verifies the online D2-to-D3 contract without actor/truth identity, but it is single-seed, short-duration evidence only. Non-equal N/M replay, real multi-seed calibration, and D5 feedback weight/hysteresis calibration remain open P1 work owned across main/D3/D6.

Local resources must not rewrite `global_track_id`; D3 publishes versioned candidate plans for review. For `secondary_plan_v2`, D3 does not choose a concrete secondary node, renew leases, elect leaders, or perform recovery arbitration. D4/main supplies those decisions; D3 validates the activation snapshot and prevents expired, non-monotonic, or non-current plans from yielding an executable D7 binding. Normal operation uses Hungarian assignment. The established P1 OR-Tools scope is an optional same-input min-cost-flow comparator only; capacity, backup-resource, quota, and predictive rolling extensions remain later work. D4 secondary-node arbitration is preferred before CBBA-style fallback.

Current D3 regression baseline: `104 passed, 1 skipped` with `python3 -m pytest research_modules/d3_assignment_planner/tests -q -o addopts='' -ra`. The skip is the installed-only OR-Tools benchmark in an environment without the optional dependency.
