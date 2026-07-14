# D3 Assignment Planner

Centralized rolling `M` target / `N` resource assignment research module.

Boundary: this module only supports offline simulation, evaluation, and human-review candidate planning. It excludes real fire-control parameters, damage logic, flight or hardware drivers, autonomous disposition, and authorization bypasses.

## Layout

- `PLAN.md`: engineering/scientific plan and mathematical formulation.
- `src/d3_assignment_planner/`: Python implementation.
- `src/d3_assignment_planner/fixtures.py`: versioned non-equal, dynamic-event, D5-feedback, and hard-window fixtures.
- `src/d3_assignment_planner/calibration.py`: reusable full/incremental P1 matrix runner and D6-friendly summaries.
- `src/d3_assignment_planner/cooperative_prescreen.py`: versioned M-to-N cooperative candidate grid, observed-result ranking, and current-plan metadata export.
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
coalition member/role changes increment coalition version; executable window
changes increment plan version, while pure cost evaluation preserves it. D7 bindings
carry coalition identity, role, wave, mode, window, and minimum separation, and
only a current committed coalition can produce an active binding.
Changing `primary_resource_count` also changes the coalition demand signature,
increments coalition version, and is exported in binding fields/metadata.
`AssignmentPlan.execution_signature()` additionally covers executable bindings,
coalition state/members, role/wave/windows, owner, and activation/lease semantics.
For both `k=1` and `k>1`, a pure cost/evaluation refresh retains executable
`plan_id/version`, assignment `plan_version`, `created_at`, and coalition
`version/epoch`; it sets `evaluation_refresh_only=True` and updates only
diagnostic costs and `last_evaluated_at_s`. A resource/role/target/owner or
activation change advances executable identity. Secondary takeover is an
explicit new lineage. Plan and assignment metadata keep lineage creation time
in `identity_created_at_s` and the current evaluation tick separately.

OR-Tools is not a default dependency. The isolated P2 benchmark feeds one
unequal-N/M, hybrid primary+reserve, capacity-constrained demand-slot problem
to SciPy Hungarian (capacity-column expansion) and optional OR-Tools min-cost
flow (native resource capacities). Missing dependencies are returned as a
structured `unavailable_reason`; the default planner does not select either
benchmark adapter dynamically.

Run the isolated comparison with:

```bash
python3 research_modules/d3_assignment_planner/simulations/run_p2_capacity_benchmark.py
```

The checked fixture has 4 resources, 3 targets, 5 demand slots, and capacities
`(2, 1, 1, 1)`. SciPy Hungarian returns objective `5.6`. In the current
environment OR-Tools is absent, so its result is `status="unavailable"` rather
than a failed benchmark run. This slot-level comparator checks capacity and
cost equivalence; it does not implement online coalition all-or-none admission.

## Incremental Planning

`AssignmentPlanner.plan_incremental(...)` accepts the current tracks/resources,
the exact published `previous_plan`, declared `changed_track_ids` and
`changed_resource_ids`, timestamp, and expected previous version. Every normal
plan stores deterministic track/resource/demand fingerprints. The incremental
entry compares those snapshots with the declared changes, builds the current
target-resource feasibility graph, and solves only the disconnected component
reachable from changed entities and their previous bindings. Unaffected
feasible assignments and coalition members retain their target/resource,
coalition identity/version, role, and wave; plan-version and evaluation metadata
are refreshed through the standard publication path.

The implementation is deliberately conservative. Missing snapshots, omitted
changed IDs, target/resource set changes, demand changes, expired plans,
time-dependent constraints, or a component that expands to the global problem
run the standard full planner and record `incremental_fallback_reason`. An
expected/current plan-version mismatch remains `StalePlanError` and exposes its
reason through `to_metadata()`; it is not silently replaced. Hysteresis is
applied after the local candidate is merged into the full plan, so relative
gain, dwell, change limits, high-threat release, M-to-N all-or-none admission,
and switch-penalty single charging keep their existing global semantics.

`summarize_incremental_planning_comparison(...)` compares incremental and full
plans by cost, assignment equivalence, latency, target-level change count, and
preserved assignment count. Latency is calibration evidence only; the planner
does not automatically choose a path from one timing sample.

`run_p1_assignment_calibration_matrix(...)` runs the same planner profile over
5v5, 3v5, 5v3, target arrival, resource failure, high-threat demand change,
D5 reserve feedback, and hard-window transitions. Each row reports full versus
incremental latency, churn, unassigned high-threat count, coalition shortfall,
hard-window rejects, equivalence, fallback reason, and role-aware primary
preservation. It is an offline calibration harness and never changes the
default Hungarian/demand-slot path from timing results.

Run the deterministic matrix as JSON with:

```bash
python3 research_modules/d3_assignment_planner/simulations/run_p1_assignment_calibration.py
python3 research_modules/d3_assignment_planner/simulations/run_p1_assignment_calibration.py \
  --output research_modules/d3_assignment_planner/results/p1_assignment_summary.json
```

The `--output` path is optional. When supplied, parent directories are created
and the same formatted `summary.as_dict()` JSON is written to the file and
printed to stdout.

## Cross-Node Contract

`AssignmentPlan` and each `Assignment` expose cross-node metadata for integration dry runs: `source_node_id`, `target_node_id`, `link_type`, `plan_version`, `stale_after_s`, `terminal_feedback_state`, and `duplicate_terminal_lock_risk`. D3 also provides `evaluate_terminal_feedback(...)` to map D5 states into conservative recommendations:

`AssignmentPlanner` is stateful for one episode. Its first `plan(...)` call may use `previous_plan=None` and creates version 1. Stale checks use only the latest published identity. `plan(..., publish=False)` returns a candidate without advancing latest, and `publish_plan(candidate)` publishes a reviewed candidate. After a plan is published, later calls must pass that exact active identity as `previous_plan`; omitting it raises `StalePlanError` with `reason="previous_plan_required"`. Main must create a new planner instance for a new episode; D3 does not provide an implicit reset.

- `ambiguous` / `hold` -> `hold`
- `reacquire` -> `replan`
- `mismatch` or duplicate terminal lock risk -> `secondary_arbitration`

The feedback decision includes `main_action` and `planner_metadata` so main can apply a conservative integration action without local rebinding. The metadata explicitly carries `operator_hold_suggested`, `prohibit_assignment_suggested`, `feasibility_suggestion`, `fov_difficulty_suggestion`, optional `feasibility_by_resource`, optional `fov_difficulty_by_resource`, and optional `prohibited_edges`. `apply_terminal_feedback_to_planner_inputs(...)` maps that metadata into next-round `TargetTrack` and `ResourceState` DTOs: duplicate/explicit prohibited edges become `feasibility_by_resource=False`, fov/friend feedback increases `fov_difficulty_by_resource`, and friend/hold feedback sets `ResourceState.operator_hold`.

The writeback also preserves normalized `terminal_feedback_events` with target,
resource, source plan version, coalition reason/conflict, stable-lock counts, and
the upstream required stable window. Before ordinary cost hysteresis, both
`plan()` and `plan_incremental()` apply a version-matched dwell to coalition
primary membership. `PlannerConfig.transient_feedback_dwell_frames` defaults to
2; the effective window is the maximum of this value and D5's
`required_stable_frames`, so D3 cannot weaken the visual gate. A short
`primary_lock_stability_incomplete` or `reacquire` holds a still-feasible
primary set until that window completes. Duplicate/friendly conflict, wrong
binding, loss, resource unavailability, explicit prohibited edges, or any other
old-plan infeasibility bypass the dwell immediately. Feedback for another plan
version is audit-only and cannot protect or release the current coalition.

Per-member reserve feedback has a separate role-aware rule that does not depend
on coalition reason, stable-window fields, or a role supplied by main. D3 joins
each version-matched target/resource event to the previous plan assignment. If
every previous primary reports `consistent/continue`, at least one previous
reserve reports a soft `hold/hold` or `reacquire/replan`, and all old primary
edges and capabilities remain feasible, the demand-slot matrix pins exactly
that previous primary set. The solver may constrain or replace reserve slots
without rotating a healthy primary into reserve. Any primary failure,
duplicate/friendly/wrong-binding conflict, unavailable primary edge, changed
demand, or stale feedback disables the pin and follows the existing hard-risk
or primary-failure policy.

`ResourceState` also carries P0-B resource detail fields: `energy_fraction`, `availability_score`, `current_load`, `history_failure_rate`, `intercept_feasibility_by_target`, and `intercept_feasibility_score_by_target`. `CostModel` consumes them through `resource_state` subcomponents and hard infeasible flags, so D6-facing cost breakdowns can distinguish energy, availability, load, historical failure, and intercept feasibility causes.

`TargetTrack` supports a lightweight hard time-window baseline through explicit fields or metadata: `hard_time_window`, `time_window_open_at_s`, `time_window_close_at_s`, `time_window_state`, and resource-specific `time_window_by_resource`. When a window is explicitly closed, expired, or not yet open, `CostModel` marks that edge infeasible, sets hard-window reject flags in the breakdown, and `AssignmentPlanner` exports the rejected edge with a readable `reject_reason`; the soft `window_cost` term remains available for ordering open edges.

`compose_threat_score_baseline(...)` provides the P0-C explainable baseline for `TargetTrack.threat_score`. It combines critical-zone proximity, TTC, speed, covariance, and target state into a normalized score with components/reasons metadata. This is a baseline helper only; full outcome-aware dynamic threat assessment remains a P1 model-calibration item.

`PlannerConfig.reassignment_switch_penalty` is applied before Hungarian/fallback solve. For a target assigned in `previous_plan`, every feasible edge to a different resource receives the penalty; the edge to the same resource does not. Targets without a previous assignment and all unassigned costs are unchanged. The solver input matrix, per-edge breakdown `total`, selected `Assignment.cost`, plan objective, and exported evidence therefore share one cost value, with no post-solve double charge.

D3 also exports:

- `assignment_validity_summary_from_plan(...)` -> `AssignmentValiditySummary(plan_id, version, plan_age_s, assignment_latency_s, cost_margin, stale_plan_version, duplicate_assignment_count, unassigned_high_threat_count, resource_count, target_count, assigned_count, hysteresis_reject_count, stale_reject_count, reassign_count)`.
- `assignment_records_from_plan(...)` and `assignment_evidence_from_plan(...)` -> D6/main outputs containing current plan identity, `identity_created_at_s`, `last_evaluated_at_s`, N/M shape, costs/reject reasons, hysteresis state, secondary audit fields, plus `assignment_profile_schema`, cost/feedback profile id/version, the exact cost-weight snapshot, and planner thresholds. A record without an explicit export timestamp uses `last_evaluated_at_s`, not the stable identity creation time.
- `summarize_assignment_mismatch_replay(...)` -> `AssignmentMismatchReplaySummary(resource_count, target_count, assigned_count, unassigned_high_threat_count, hysteresis_reject_count, stale_reject_count, reassign_count)` for N/M mismatch replay aggregation.
- `summarize_incremental_planning_comparison(...)` -> `IncrementalPlanningComparisonSummary` with incremental/full cost delta, equivalence, latency, change counts, and preserved targets/assignments.
- `summarize_terminal_feedback_calibration(...)` -> advisory `TerminalFeedbackCalibrationSummary` from multi-seed assignment/feedback records. It reports duplicate/friend/fov/geometry reject counts and cost/hysteresis tuning directions, but never rewrites `CostWeights` or `PlannerConfig` defaults.
- `guidance_bindings_from_assignment_plan(...)` -> versioned `AssignmentGuidanceBinding` rows whose metadata includes identity creation and last evaluation timestamps. Binding freshness and `expires_at_s` use `last_evaluated_at_s`, with `created_at` as the fallback for legacy/manual plans. Main supplies the current `plan_id/version` when exporting a secondary binding; a historical plan, an unconfirmed secondary current identity, an inactive takeover, or an expired lease cannot produce an `active/current` D7 binding.
- `prepare_secondary_takeover_plan(...)` -> activates a D4/main-selected takeover candidate only after main supplies sustained `takeover_ready`, activation time, a live lease, and a positive monotonic leader epoch. A same-signature candidate may retain the current center identity; the helper advances identity exactly once for the owner/activation transition. Successful plans audit readiness, activation, supersede, owner, lease, epoch, and `allow_local_rebind=False` in plan, assignment, record, evidence, and binding metadata.
- `continue_active_secondary_plan(...)` -> converts the next ordinary rolling candidate into a same-owner secondary plan without a second takeover. It derives the concrete owner/source from the previous active plan, requires strict version/supersede continuity, sustained readiness, non-regressing epoch, and a live non-regressing lease; main must not hand-build these metadata fields.
- `build_p1_assignment_fixtures()` -> versioned deterministic 5v5, 3v5, 5v3, new-target, resource-failure, high-threat demand-change, D5-feedback, and hard-window inputs. Labels use `resources x targets`; explicit counts and changed IDs are present in fixture metadata.
- `run_p1_assignment_calibration_matrix()` -> paired full/incremental transition rows and aggregate latency/churn/high-threat/coalition-shortfall totals for main/D6.

`PlannerConfig.human_authorization_state` is the source of the plan authorization field. The planner records both `configured_human_authorization_state` and `effective_human_authorization_state` in plan metadata so main can run record-only simulation gates without hard-coding D3 to `"required"`.

For active degradation recovery, D3 does not emit D4 actions itself. Main calls `plan(..., forced_replan=True)` with the current published plan. If executable semantics are unchanged, D3 preserves identity and returns `decision_state="replan_ack_no_change"`; if they change, D3 advances identity once and returns `decision_state="replan_applied"`. Main/runtime integrates these states and any `replan_reason`/supersede metadata. A binding from an applied current plan remains `active/current`; the old published identity is stale.

Main/runtime has connected D5 feedback writeback, center replan owner/version/source recording, secondary owner/version/source recording, and the P1 D4/D5 calibration sweep. For secondary flow, main should request `publish=False`, apply `prepare_secondary_takeover_plan()` or `continue_active_secondary_plan()`, then call `publish_plan()` on the final owner-stamped plan. This prevents an intermediate center candidate from advancing published latest.

The 2026-07-11 P1 validation used 5 resources, 2 targets, and 10
ComputerVision seeds. T001 achieved two-primary visual consensus with current
plan authorization in 8/10 seeds; seeds 7 and 27 remain regressions. Together
with the incremental planner and role-aware primary-preservation tests, this
closes the D3 P1 contract layer rather than only the earlier demand-slot DTO.
Downstream secondary and distributed commit positive cases passed, and a
missing ACK aborted fail-closed with no D7 permission. The 2026-07-12 PNG
delivery change made no D3 code or behavior change. Its 2v2 candidate reached
20/20 physical pairs and therefore demonstrated a non-regressed one-to-one
chain under the current plan gate. The M5N2 8 s run reached 0/9 active pairs,
but is not comparable to the existing z=-30 m, 35 s high-clearance baseline;
the cooperative physical loop remains open pending a same-geometry,
same-window paired run. P2 remains an isolated optional benchmark and does not
replace the default Hungarian/demand-slot planner.

Local resources must not rewrite `global_track_id`; D3 publishes versioned candidate plans for review. For `secondary_plan_v2`, D3 does not choose a concrete secondary node, renew leases, elect leaders, or perform recovery arbitration. D4/main supplies those decisions; D3 validates the activation snapshot and prevents expired, non-monotonic, or non-current plans from yielding an executable D7 binding. Normal operation uses Hungarian/demand-slot assignment. The optional same-input capacity comparator is implemented and is not an open online P1 dependency. CP-SAT/MILP coalition admission, backup-resource quotas, multi-window flow, and large-scale sweeps remain isolated P2 benchmarks. D4 secondary-node arbitration is preferred before CBBA-style fallback.

Current D3 regression baseline (2026-07-13): `139 passed, 1 skipped` with `python3 -m pytest research_modules/d3_assignment_planner/tests -q -o addopts='' -ra`. The skip is the installed-only OR-Tools benchmark in an environment without the optional dependency.

## Per-primary authorization and coalition membership hysteresis

Cooperative demand now carries the versioned contract
`terminal_authorization_scope="per_primary"` and
`arrival_coordination_required=False`. Each active primary may therefore be
authorized independently by downstream D4/D5/D7 gates; a reserve binding is
explicitly `hold` with `reserve_standby_not_activated` and cannot execute
without a newer plan changing its role.

Per-pair diagnostics use the same contract in both D6 records and D7 binding
metadata. They expose plan owner/version, coalition id/version/epoch, role,
wave, activation, assignment validity, authorization eligibility, plan churn,
rollback detection, and stale-reject count. Only feasible active primaries are
reported as active/eligible; reserve rows remain standby and inactive. A
compatible current-plan evaluation refresh reports zero churn and no rollback
while preserving plan identity and coalition epoch.

For `k>1`, executable members and roles have a separate membership clock.
They remain fixed for at least `PlannerConfig.min_dwell` and may be replaced
only when the previous member set is hard-infeasible, or when the candidate
coalition cost improves by more than `delta` after dwell. Plan metadata exports
the previous/current member sets, reason, target cost comparison, dwell result,
and hold basis. Ordinary compatible cost refreshes preserve both `plan_id` and
plan version; coalition `version/epoch` advances only when a resource or role
actually changes. The Hungarian/demand-slot solver is unchanged.

## P1 Cooperative Candidate Prescreen

`build_p1_cooperative_candidate_grid()` defines the stable 27-candidate grid
used by main's M5N2 paired sweep: terminal handoff range `20/30/40 m`, primary
arrival-window width `3/5/8 s`, and approach-sector separation
`20/40/60 deg`. Candidate IDs are deterministic and do not depend on resource
or target count. `demand_for_cooperative_candidate()` applies only the timing
and audit metadata to an existing `TargetDemand`; required resources, primary
count, hybrid/simultaneous/sequential mode, capability requirements, wave
interval, and minimum separation remain caller-owned.

`export_cooperative_candidate_plan_metadata()` emits candidate ID, current
plan/coalition versions, target/resource IDs, role, wave, arrival window,
minimum separation, and an explicit activation state. A primary is `active`;
a reserve/retry is `standby`. The export rejects a non-current plan, stale
assignment version, or stale/non-committed coalition. It is read-only and does
not activate a reserve or alter Hungarian/demand-slot planning.

`rank_cooperative_candidates()` accepts only complete physical observations
from main/D6. It refuses missing candidate observations instead of estimating
success. Ranking is deterministic: zero safety violations first, then maximum
coalition-completion rate, maximum pair-success rate, minimum arrival spread,
and finally candidate ID as the tie break. The default output is the top three
candidates. D3 therefore supplies experiment design and plan/reachability
metadata; it does not manufacture AirSim outcomes. Same-geometry 10-seed M5N2
execution and the `8/10` coalition-completion acceptance target remain open at
the main/runtime level.
