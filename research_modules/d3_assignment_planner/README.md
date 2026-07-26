# D3 Assignment Planner

Centralized rolling `M` target / `N` resource assignment research module.

Boundary: this module only supports offline simulation, evaluation, and human-review candidate planning. It excludes real fire-control parameters, damage logic, flight or hardware drivers, autonomous disposition, and authorization bypasses.

## R0 Rolling-Demand Inventory Guard

On 2026-07-25 the clean-source R0 cell at commit `32b3b40`, scenario
`high_threat_m_to_n`, scale 200, seed 1000, and duration 2.0 s failed at
`t=1.0 s`. Target `GT3D-000021` changed from an empty incomplete `k=1`
coalition to a complete `k=3` candidate. Other coalition membership changes
were still inside dwell, so the global membership hold retained the previous
inventory. Previous-plan scoring had skipped demand compatibility for a
target with no executable assignment; final inventory normalization then
raised `coalition demand does not match current demand`.

The planner now evaluates the previous coalition demand contract before the
empty-assignment branch. A changed required count, primary count, coordination
mode, timing contract, or assignment demand marks the previous plan
incompatible. Hysteresis cannot retain that inventory; the current
solver-produced candidate is rebuilt and still passes the existing capacity,
unique-resource, all-or-none, primary/reserve, stale-plan, and version checks.
The plan records the incompatible target IDs and whether the rebuild was
required and applied.

An exact-configuration development rerun on 2026-07-25 completed 2.0 s with
finite state and zero online truth use. At `t=1.0 s`,
`GT3D-000021` was rebuilt as a complete `k=3` coalition under
`accepted_previous_infeasible`; 197 final assignments used 197 unique
resources, with zero overallocated targets and zero demand-summary mismatch.
The D3 suite passed `464 passed, 1 skipped`; the skip remains the optional
OR-Tools test.

This is implemented and tested development evidence. The failed formal
artifact remains bound to clean commit `32b3b40`; main must rerun the cell and
formal shard from a new clean source commit before marking formal R0 complete.

## Multi-Cycle BC Residual Shadow Evaluation

On 2026-07-25 D3 added an isolated multi-cycle evaluator for the frozen
behavior-cloning residual.  It runs independent rule/control and
residual/treatment planners on the same anonymous tracks, resources, numeric
seed, timestamps, and exogenous events.  Both arms keep the existing
Hungarian or demand-slot Hungarian solver and hard-safe candidate mask.  The
treatment cost matrix is never published to the runtime bus.
Optional `planner_config` and `cost_weights` inputs are applied symmetrically
through separate rule and treatment `CostModel` instances.

The recorded shadow run used reserved seeds 1000-1019 with zero overlap against the 100
training seeds.  Its six scenarios cover a Hungarian switching boundary,
5 resources/3 targets, 3 resources/5 targets, resource failure and recovery,
target addition/removal, and M-to-N demand change.  Across 620 paired cycles:

- the frozen residual changed 580 effective cost matrices;
- 120 cycles and 20/20 seeds produced a different final binding;
- all 20 seeds were identifiable in the controlled Hungarian boundary;
- 40 M-to-N demand-change cycles were out of distribution and restored the
  exact rule matrix;
- duplicate resources, hard-constraint or lineage violations, stale-version
  adoption, and online truth use were all zero;
- inference latency was 0.228 ms at P50 and 0.361 ms at P95 on this host.

Rule churn was 520 and treatment churn was 200, while the treatment plan cost
rescored on the rule matrix was higher by 0.000707 per cycle on average.
This is a measured tradeoff, not a benefit claim.  The evaluator has no
runtime ACK, physical outcome, causal reward, or promotion authority.
`promotion_recommended`, PPO, online assist, online authority, and runtime
publication therefore remain false.  Artifacts are under
`results/multi_cycle_shadow_bc_20260725/`.
Both CSV artifacts use an explicit LF line terminator so repository whitespace
checks do not depend on the platform default.
The artifacts bind the seed registry, bundle manifest, weights, dataset, and
split hashes, but they were generated before these source changes had a clean
commit.  They remain development evidence until a clean-worktree rerun records
the source revision and configuration digest.

## Identity Commitment Admission

`TargetTrack.identity_commitment_state` supports `committed`,
`identity_uncommitted_ambiguity_hold`, and
`identity_uncommitted_after_hold`. Missing values normalize to
`identity_commitment_missing`; unsupported values normalize to
`identity_commitment_unknown`. Both fail closed.

Only committed targets enter the hard-safe candidate mask. An uncommitted
target cannot produce a one-to-one assignment or any M-to-N primary/reserve
slot. Main owns the hold/replan trigger. Once main supplies a revoked state and
requests a new planning tick, D3 removes the target bindings, publishes a
strictly newer candidate plan, and records the reason without mutating the
previous plan or rewriting `global_track_id`.

The AirSim dry-run adapter reads a direct field, an `identity_commitment`
mapping, or metadata. It does not use actor identity or offline labels. On
2026-07-23 the focused file passed 12 tests; the full D3 suite passed
450 tests with one existing optional OR-Tools skip.

Clean scalable-runtime evidence is now available for commit
`7e15dac9cdaf6743999dfe045a70676fd31a17d6`
(`repository_dirty=false`), nominal 200-resource/200-target, 2.2 s, seed 1100.
Both `hold_only` and `hold_plus_centroid` arms published plan v1 with 193
assignments at `t=0.75`. At `t=1.0`, 11 targets previously assigned by v1
became `identity_uncommitted_ambiguity_hold`; D3 bypassed hysteresis for the
safety withdrawal and published v2 with 186 assignments. All 11 targets were
absent from v2. Plan v3 retained 186 assignments at `t=2.0`. From `t>=1.0`,
those targets had zero D3 assignments, D5 active-vision commands, D5 terminal
bindings, and D7 guidance commands.

The runtime diagnostic `d3_identity_commitment_binding_hold_count=13` is a
main binding-hold count across the event; it is not the D3 rejected-target
count, which is 11. This episode did not inject a stale plan. Active stale-plan
injection remains covered by module and AirSim regression tests. The identical
two-arm result validates the runtime safety withdrawal only; it does not prove
an algorithmic benefit from D1 centroid correction or D2 association.

## Layout

- `PLAN.md`: engineering/scientific plan and mathematical formulation.
- `src/d3_assignment_planner/`: Python implementation.
- `src/d3_assignment_planner/fixtures.py`: versioned non-equal, dynamic-event, D5-feedback, and hard-window fixtures.
- `src/d3_assignment_planner/calibration.py`: reusable full/incremental P1 matrix runner and D6-friendly summaries.
- `src/d3_assignment_planner/cooperative_prescreen.py`: versioned M-to-N cooperative candidate grid, observed-result ranking, and current-plan metadata export.
- `src/d3_assignment_planner/learning.py`: optional shared candidate-edge PyTorch residual, behavior-cloning warm-up, shadow/assist inference, masks, and rule fallback.
- `src/d3_assignment_planner/runtime_plan_ack.py`: strict read-only validation of main runtime plan adoption ACKs.
- `src/d3_assignment_planner/isolated_plan_consumption.py`: versioned, replay-safe confirmation that an isolated rollout arm consumed one exact plan; this is not a production runtime ACK.
- `src/d3_assignment_planner/runtime_reward_evidence.py`: hash-bound adopted-window to observed-outcome attribution contract; formal reward remains fail-closed.
- `src/d3_assignment_planner/paired_intervention.py`: strict seed 1000-1019 control/treatment specification, isolated execution receipt, and verified runtime-ACK reference contract.
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

The feedback decision includes `main_action` and `planner_metadata` so main can apply a conservative integration action without local rebinding. The metadata explicitly carries the backward-compatible hold/feasibility/FOV fields plus additive `feedback_constraint_class`, scope, hard-reject flag, and classification reason. `apply_terminal_feedback_to_planner_inputs(...)` classifies ordinary `ambiguous`, `hold`, `reacquire`, geometry/FOV, and detection-instability evidence as `resource_target_edge_soft`: it raises only that edge's FOV cost, keeps D7 on hold, and leaves `ResourceState.operator_hold=False`. `friend_overlap_hold` remains resource-hard, verified-friend evidence is target-hard, and safety identity conflict, duplicate assignment/lock, or explicit feasibility rejection remains fail-closed. Existing metadata names, including nested `resource_update`, remain accepted; a legacy pair hold is downgraded to soft and audited rather than expanded to the whole resource.

The writeback also preserves normalized `terminal_feedback_events` with target,
resource, source plan version, coalition reason/conflict, stable-lock counts, and
the upstream required stable window. Before ordinary cost hysteresis, both
`plan()` and `plan_incremental()` apply a version-matched dwell to coalition
primary membership. `PlannerConfig.transient_feedback_dwell_frames` defaults to
2; the effective window is the maximum of this value and D5's
`required_stable_frames`, so D3 cannot weaken the visual gate. A short
`primary_lock_stability_incomplete` or `reacquire` holds a still-feasible
primary set until that window completes. Completing the frame window does not
bypass ordinary `delta`, `min_dwell`, change-limit, or coalition-member
hysteresis. Duplicate/friendly conflict, wrong
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
without rotating a healthy primary into reserve. The resulting reserve change
is still a candidate and must pass ordinary member/global hysteresis. Any primary failure,
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
- `plan_history_record_from_plan(plan, sequence_index=..., timestamp=..., previous_plan=..., feedback_metadata=...)` -> one canonical `PlanningTickHistoryRecord` per planning tick. `feedback_metadata` is optional and accepts `TerminalFeedbackWriteback.metadata`; otherwise compatible feedback keys are read from `plan.metadata`. Call `to_dict()` before JSONL persistence. The schema is `d3_plan_history_record_v1`, and history order is the lexicographic `[sequence_index, timestamp]` key supplied by main.
- `summarize_assignment_mismatch_replay(...)` -> `AssignmentMismatchReplaySummary(resource_count, target_count, assigned_count, unassigned_high_threat_count, hysteresis_reject_count, stale_reject_count, reassign_count)` for N/M mismatch replay aggregation.
- `summarize_incremental_planning_comparison(...)` -> `IncrementalPlanningComparisonSummary` with incremental/full cost delta, equivalence, latency, change counts, and preserved targets/assignments.
- `summarize_terminal_feedback_calibration(...)` -> advisory `TerminalFeedbackCalibrationSummary` from multi-seed assignment/feedback records. It reports duplicate/friend/fov/geometry reject counts and cost/hysteresis tuning directions, but never rewrites `CostWeights` or `PlannerConfig` defaults.
- `guidance_bindings_from_assignment_plan(...)` -> versioned `AssignmentGuidanceBinding` rows whose metadata includes identity creation and last evaluation timestamps. Binding freshness and `expires_at_s` use `last_evaluated_at_s`, with `created_at` as the fallback for legacy/manual plans. Main supplies the current `plan_id/version` when exporting a secondary binding; a historical plan, an unconfirmed secondary current identity, an inactive takeover, or an expired lease cannot produce an `active/current` D7 binding.
- `prepare_secondary_takeover_plan(...)` -> activates a D4/main-selected takeover candidate only after main supplies sustained `takeover_ready`, activation time, a live lease, and a positive monotonic leader epoch. A same-signature candidate may retain the current center identity; the helper advances identity exactly once for the owner/activation transition. Successful plans audit readiness, activation, supersede, owner, lease, epoch, and `allow_local_rebind=False` in plan, assignment, record, evidence, and binding metadata.
- `continue_active_secondary_plan(...)` -> converts the next ordinary rolling candidate into a same-owner secondary plan without a second takeover. It derives the concrete owner/source from the previous active plan, requires strict version/supersede continuity, sustained readiness, non-regressing epoch, and a live non-regressing lease; main must not hand-build these metadata fields.
- `build_p1_assignment_fixtures()` -> versioned deterministic 5v5, 3v5, 5v3, new-target, resource-failure, high-threat demand-change, D5-feedback, and hard-window inputs. Labels use `resources x targets`; explicit counts and changed IDs are present in fixture metadata.
- `run_p1_assignment_calibration_matrix()` -> paired full/incremental transition rows and aggregate latency/churn/high-threat/coalition-shortfall totals for main/D6.

The plan-history payload stores plan identity/state/counts and owner/source/
secondary epoch/lease once per tick, then deterministically orders assignments
by target, coalition, wave, role, and resource. Each assignment includes role,
activation/active state, coalition identity/version/epoch, validity, scalar cost,
and cost breakdown. The record also contains recoverable ordered coalition
members, hysteresis and membership-change evidence, feedback classifications
with soft/hard counts, costs, stale/rollback/replan audit reasons, and plan
lineage. It uses only JSON-native values; no `truth_id` argument exists and any
truth-named nested metadata key is excluded. `assignment_records_from_plan()`
remains backward compatible, including its offline-only optional truth label.

Main should persist one line per successful planning tick as follows:

```python
history_record = plan_history_record_from_plan(
    plan,
    sequence_index=tick_sequence_index,
    timestamp=planning_timestamp_s,
    previous_plan=previous_plan,
    feedback_metadata=None if writeback is None else writeback.metadata,
)
jsonl_writer.write(history_record.to_dict())
```

D3 defines and validates this record but does not own JSONL storage. The
existing 40-case aggregate predates main persistence of these records, so its
membership/version churn remains `unavailable`; the former pair-hold promotion
is a root-cause lead, not proven causality for those outcomes. A later actual-v2
run has separately proved main persistence and D6 consumption, as recorded
below.

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

Current D3 regression baseline (2026-07-14): `157 passed, 1 skipped` with `python3 -m pytest -q research_modules/d3_assignment_planner/tests`. The five newest deterministic tests cover soft-feedback/round-trip stability, cumulative same-window change budget, cross-window recovery, hard resource failure, missing-target plus another membership hold, plan-level owner change, and history budget export. Earlier plan-history, held-scope/lifecycle, and feedback-governance cases remain covered. The skip is the installed-only OR-Tools benchmark in an environment without the optional dependency.

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

## 2026-07-14 真实 AirSim 计划历史审计

对 `p1_terminal_closure_truthisolated_preflight_v2_20260714_m5n2_baseline_seed001`
的 `episode_006_full_flow` 做了单 seed、349 个 planning tick 的只读复核。D3
初始计划包含 T001 的 2 个 active primary、1 个 standby reserve，以及 T002
的 1 个 active primary。后段 D2 连续产生 T003/T005/T007/T008 等新航迹，最终
current plan 为 T001 三成员、T002 一成员和 T008 一成员，因此执行产物出现 5 个
pair。T008 在 34.4 秒创建、34.5 秒 confirmed、34.6 秒 engageable；D3 不使用
truth，无法把它判定为物理目标或幻影航迹。

审计发现一个 D3-owned P1 合同缺陷：当候选因普通迟滞、联盟成员迟滞或 transient
feedback dwell 被 hold 时，当前输入中的新目标曾被写入 held plan 的
`unassigned_target_ids`，从而使 execution signature 改变并错误推进 plan/version。
修复后 held plan 完整保留上一 current plan 的 assignment、coalition、unassigned
和 incomplete 执行范围；当前候选只进入 `hysteresis_candidate_*`、
`hysteresis_pending_new_target_ids` 等审计字段。候选释放前不获得 current plan
身份。该规则不依赖 truth，不写死 M/N，也不放宽 stale、version 或 coalition 门控。

本次确定性验收标准是 hold 后 plan ID/version 与 execution signature 均不变，同时
仍记录实际输入 `target_count` 和 pending target。若上一已分配目标从当前输入消失，旧计划
直接判为 infeasible 并发布新版本，不允许迟滞继续持有不存在的执行目标。D3 全量结果为 `157 passed,
1 skipped`；唯一 skip 是 optional OR-Tools installed-only benchmark。真实 episode
没有在本任务中重跑。

两个跨模块问题保持开放：AirSim adapter 当前把除 lost/dropped 外的 D2 航迹都标为
assignable，应由 main/D2 准入链只向 D3 提交 engageable 或显式批准的航迹；D3 不以
本地 dwell 掩盖 D2 幻影。其次，D3 最终仍把 INT-01 reserve 输出为 standby/hold，
`intercept_summary.json` 中后续 active 来自 runtime pair 在 primary 变为 reserve
时未撤销旧 active 状态，不属于 D3 reserve activation。

## 2026-07-14 P1 计划抖动预算与统一成本口径

最新 truth-isolated M5N2 baseline seed 001 有 347 条 canonical planning records，
执行版本为 v1..v35。稳定双目标阶段仍约每秒往返换员。记录中的一个代表性 tick
把候选联盟成本写成 `0.8868`、previous 写成 `2.8520`；previous 当前边内含
`2.2` 的 soft-feedback FOV shaping，去除该候选搜索项后 previous 基础执行成本约为
`0.6520`，候选并未达到 20% 改善。该现象证明原 membership gain 比较混用了
search objective 与 execution comparison objective。

planner 现在使用 `d3_hysteresis_current_objective_v1` 同时重评 candidate 和
previous：包含当前 target-resource 基础成本、硬可行性和
`unassigned_cost * required_resource_count`；排除只用于搜索的 switch penalty、
soft-feedback FOV shaping、demand-slot priority 和 role pin。solver/evidence 仍保留
完整 search cost，metadata 同时记录 search/comparison 两套数值，避免再把口径差异
误判为 `delta=0.2` 收益。

`max_changes_per_window` 现在由 plan metadata 延续
`d3_cumulative_window_change_budget_v1`：同一 `window_id` 累加已接受的 assignment
change count，hold/evaluation refresh 不计费，新 window 清零。execution target
缺失、资源硬失效和 plan-level owner/activation/authorization 改变仍立即生成新版本，
预算不足时记录 bypass；成员 primary/reserve 候选本身仍受 coalition hysteresis，
不会借 activation 名义绕过。missing target 与另一联盟 hold 同时出现时，消失目标
不会进入新 assignment、coalition 或 membership audit。

本批只完成确定性实现验收，未重跑 AirSim。D3 全量为 `157 passed, 1 skipped`，零
失败达到接受阈值；剩余 P1 是 main/D2 lifecycle admission、runtime reserve
demotion、至少 10 个同几何 seeds 的 churn/高威胁未分配复验，以及 M5N2 物理
coalition completion 从当前最佳 `5/10` 达到 `8/10`。

## 2026-07-14 Actual-v2 真实 AirSim 证据链

本次只同步 main 已完成的真实 AirSim 证据，不修改 D3 代码、Hungarian/demand-slot、
迟滞、版本或 primary/reserve 语义。两个 seed-1 sequence 的 command CSV、
`d7-actual-execution-metrics-v2` 与 canonical D3 history 使用相同计划身份：

| Case | command/actual/history plan | History | D6 feedback churn |
|---|---|---:|---:|
| tuned 2v2 | `d3-plan-c3cc6d28c365/1` | 24 | 3 |
| M5N2 | `d3-plan-cfdd088a10e1/1` | 214 | 50 |

D6 对两条 history 的可用/不可用 case 为 `2/0`，validation reasons 为空；actual
execution required/available/unavailable case 为 `2/2/0`。因此 D3 计划从 history
到 command 再到 actual metrics 的运行级 P0 可追溯链已关闭。M5N2 的 plan version、
成员和 owner churn 均为 0，但 feedback churn 50 仍是单 seed P1 标定信号，不是
P1 稳定性通过。物理结果为 pair `2/3`、target `2/2`、coalition `0/1`；T001 第二
primary 最近约 11.02 m，未进入 5 m。目标级 `2/2` 不能写成联盟完成。第二 primary
物理闭环和同配置多 seed 复验继续保持 P1。

## 2026-07-15 M5N2 20-Case 计划历史复核

main 在 M5N2 baseline 与 `candidate_soft_prediction_trend_coast` 各完成 10 seeds 后
终止了后续多 seed suite。D3 对这 20 个 case 的
`main_episode_bus/d3_plan_history.json` 做了只读复核：共 `3725` 个 planning tick，
其中 baseline `1869`、candidate `1856`；20/20 个文件的 `record_count` 与实际数组长度
一致，全部记录均为 `d3_plan_history_record_v1`、`assignment_plan_v2`。

每个 tick 都报告动态规模 `resource_count=5`、`target_count=2`，并保持 T001 的
`2 primary + 1 standby reserve` 和 T002 的 `1 primary`，总计 4 个 assignment。
20 个 case 各自只出现一个 `plan_id/version=1`；逐 tick 计划身份、owner 和实际成员
roster 转换均为 0，stale reject 与 rollback 也均为 0。`3555` 条
`membership_change_records` 是候选换员评估，不是实际 churn：其中 `3524` 条由成员
迟滞保持，`31` 条虽通过成员收益/驻留条件，但又由全局迟滞保持，最终未改变 current
plan。由此，canonical history 的写盘和 D3 计划/成员/churn 可用性在本批已闭合，
不再是 `unavailable`。

跨 case 不能写死“第二 primary”的资源编号。19 个 case 的 T001 primary 为
`INT-02/INT-03`，1 个 candidate seed 的 primary 为 `INT-01/INT-02`；D3 文档只按
`target_id + member_role + current plan identity` 统计。系统物理结果为 pair
`12/60`、canonical target `12/40`、coalition `0/20`，第二 primary `0/20` 进入 5 m，
20 个第二 primary 的 `stop_reason` 均为 `collision_stop`。这些结果保留为跨模块 P1：
D3 history 未记录碰撞对象，不能把物理失败归因于分配器；candidate 的配对非退化
判据失败也不等于 D3 算法退化，因为两组的 D3 执行身份和成员均保持稳定。

术语必须分开：`canonical target success` 是 D6 对两个目标的标准目标级统计；
`cooperative target diagnosis` 专指 T001 两个 active primary 与 coalition 的诊断，
不能用前者替代联盟完成。TERM 生效前额外完成的 `png_ttc_2v2_seed001` 不纳入上述
M5N2 聚合；其余 tuned case 未执行，dropout case 数为 0，缺失结果保持
`unavailable`。

本次 D3 证据同步的验收门限是 20/20 history 可读、record count 无缺失、actual
plan/member/owner churn 可计算，且模块测试零失败；结果满足。物理验收门限仍为每个
active primary 进入 5 m，第二 primary 与 coalition 未满足。D3 全量测试为
`157 passed, 1 skipped`，唯一 skip 是 optional OR-Tools installed-only case。

## Scalable 3D Rule And Learning-Assist Path (2026-07-20)

`PlannerConfig.scalable_3d(...)` is an opt-in profile around the existing rule
planner. `TargetTrack` and `ResourceState` accept NED position/velocity,
position covariance, region identifiers, and resource speed/range fields. The
rule cost adds analytic constant-speed 3D intercept time/range, normalized NED
covariance, and region cost. Unreachable edges, exhausted assignment capacity,
declared friendly conflicts, and incompatible regions are hard-masked.

Candidate generation first applies the region/reachability gates and then
retains a deterministic per-target top-k. The effective k is never below the
target's `required_resource_count`, and still-feasible members of the current
published plan are retained so sparsification alone does not force churn. The
solver input remains a deterministic Hungarian/demand-slot matrix with pruned
edges set to the infeasible penalty. For sparse profiles, plan evidence stores
candidate-edge records and reject counts rather than a dense 40,000-edge audit
bundle.

The optional learning interface is `LearningCostAssistant`. It runs one shared
PyTorch MLP over a variable-length candidate-edge feature batch and supports
`shadow` and `assist` modes. Assist mode uses exactly:

```text
C_final = C_rule + alpha * tanh(delta_C)
```

The policy cannot emit assignments or a dense target-by-resource action vector;
Hungarian/demand-slot solving, all-or-none coalition admission, capacity, friend
conflict, and version checks remain deterministic. A stale version is rejected
by `AssignmentPlanner`; standalone residual inference masks a version mismatch.
Model timeout, low confidence, OOD features, invalid output, or model exception
returns the unchanged `C_rule`. `behavior_clone_warmup(...)` is a minimal native
PyTorch supervised warm-up interface, not PPO training or acceptance evidence.

Deterministic validation on 2026-07-20 added 13 tests: 3-target/5-resource,
5-target/3-resource, one 200v200 fixture, sparse high-threat M-to-N, 3D cost,
mask/fallback/version cases, and one 32-edge synthetic behavior-cloning batch.
The 200v200 sample assigned 200/200 with 800 candidate edges (2% density) and
800 shared-edge policy actions; one local invocation took 0.621 s. This is a
single functional timing sample, not a real-time benchmark. The full D3 suite
is `170 passed, 1 skipped`, with zero failures as the acceptance threshold and
only the optional OR-Tools installed-only test skipped.

Remaining learning gaps are real D2/D3 trajectory datasets, train/validation
splits, persisted checkpoints, calibrated OOD/confidence thresholds, bounded
preemptive inference, shadow multi-seed non-degradation, and any large-scale PPO
study. `gymnasium` and `stable_baselines3` are absent and are not required by
this implementation. The analytic reachability baseline does not replace D7
dynamics, obstacle/path planning, regional quota policy, or AirSim physical
validation.

## 2026-07-20 200×200 成本构造与区域计划合同

### 稀疏成本构造

此前的 top-k 只压缩了求解和证据输出，规则成本仍先对全部 `N×M` 资源目标对执行
Python 几何计算，并为随后被剪枝的边构造完整字典。同区域 200 resource × 200 target、
每目标 32 条候选边时，实际仍执行 40,000 次边成本和 80,000 次截获量计算。

`PlannerConfig.scalable_3d()` 现默认启用 `enable_vectorized_sparse_costs`。核心三维
位置、速度、协方差、资源状态、区域许可、截获时间和距离由 NumPy 批量计算；规则排序
仍按“成本、resource_id”确定性排序。最终只为 6,400 条候选边生成完整 breakdown，
剪枝边共享拒绝模板。带资源目标字典覆盖或复杂时间窗的输入继续走旧参考路径，保持既有
约束优先级和解释字段。学习残差、有界修正、规则回退和硬门控没有改变。

SciPy `linear_sum_assignment` 仍是默认确定性求解器。候选图不连通时，求解器按二部图
连通分量构造局部矩阵并分别运行 Hungarian；无候选目标直接按未分配成本处理。该分解
不改变全局最优值，因为分量之间没有共享资源边。

2026-07-20 同一进程、同一 200×200 输入、top-32、各重复 5 次的 D3 独立基准如下。
结果保存在 `results/scalable_3d_assignment_benchmark_20260720.json`。

| 路径 | 中位耗时 | 完整边 | 候选边 | Python 全边成本调用 | 分配数 |
|---|---:|---:|---:|---:|---:|
| 旧参考路径 | 1904.261 ms | 40,000 | 6,400 | 40,000 | 200 |
| 向量化稀疏路径 | 85.367 ms | 40,000 | 6,400 | 0 | 200 |

中位加速为 22.307 倍。20×23 逐边语义对照中，矩阵、候选掩码和拒绝原因一致，候选
breakdown 的浮点差在 `1e-11` 容差内。该数据是 D3 独立确定性基准，不代表 D1-D7
全栈实时性能，也不替代多 seed 或 AirSim 物理验收。

### 区域计划

新增 `RegionalAuthorityInput`、`RegionalAuthorityGrant` 和
`RegionalCoalitionCommitEvidence`。D3 不判断是否降级，只接受 D4 已裁决的区域
owner 和成员结果，生成一个普通、可版本校验的 `AssignmentPlan`。同一计划可携带
多个 secondary owner，也可携带 fully distributed peer owner；每条 assignment
记录 region、owner、epoch、lease 和 commit 状态。

发布前必须满足：D4 输入引用当前 `plan_id/version`；区域 epoch 不回退；lease 在
发布时间后有效；每个资源只属于一个目标；成员边仍在 D3 规则候选中；M-to-N 需求
完整。`k=1` 由 D4 已裁决的区域 ownership、epoch、lease、execution_allowed 和唯一
资源成员授权，不要求原子联盟提交；若 D4 同时提供 summary，只接受
`commit_required=False`、`single_member_authorized`、非 atomic、成员授权完整且租约
有效的证据。`k>1` 继续强制 committed、atomic committed、完整 ACK、成员一致且租约
有效。任一条件失败均抛出带 reason 的 `RegionalPlanAuthorityError`，不发布可执行
计划。计划执行变化继续严格递增版本，旧 previous plan 仍由 `StalePlanError` 拒绝。

本轮 D3 全量验收为 `193 passed, 1 skipped`，唯一 skip 是 optional OR-Tools。
区域合同已完成模块级测试，main 尚未把 D4 `RegionalFailoverDecision` 转换并接入
`plan_regional_authority()`；因此多 owner secondary 和 distributed 运行时闭环仍是
待集成，不得写成完整系统已通过。

## 2026-07-20 故障代际 Fence

`AssignmentPlanner.advance_authority_generation(...)` 用于中心或二级节点故障后、D4
重新裁决区域 owner 之前推进 D3 计划代际。调用方必须传入当前已发布计划、单调时间、
精确 `expected_previous_version` 和非空 `fence_reason`。接口复制原计划的 assignment
成员、coalition identity/version、目标身份、owner 和授权状态，只生成新的
`plan_id`、严格递增 `version`，并由 D3 正常发布登记。assignment 中仅同步新的计划
上下文版本；资源-目标绑定不变。

Fence metadata 使用 `d3_fault_authority_generation_fence_v1`，记录原因、来源计划、
fence generation、非重分配和非执行授权。`fault_authority_fence_requires_d4_gate=True`
表示该计划不能自行授权 D7；main/D7 仍必须执行 D4 的 hold/continue 结果。普通相同
执行签名的新身份继续被 `publish_plan()` 拒绝，只有来源、版本和安全标记完整的 fence
可推进。错误 expected version、旧来源、重复 fence 版本和篡改 coalition 均 fail
closed。

2026-07-20 新增 5 个专项测试。D3 全量共 199 项，结果为
`198 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。该结果关闭 D3-owned fence
接口缺口；main 尚需在 50v50 中心故障路径调用该接口，再把新 generation 交给 D4
区域裁决。

## 2026-07-20 可复现 BC/PPO/Shadow 研究管线

本模块现提供完整但默认关闭的学习研究路径。`AssignmentPlanner` 默认仍不构造或加载
模型；规则 Hungarian/`hungarian_demand_slots`、候选 mask、联盟准入、迟滞、计划版本
和 stale 拒绝继续拥有最终决定权。模型只处理当前稀疏候选边，不输出 assignment、
target/resource index、联盟成员、owner、plan version 或 D7 控制量。

### 数据与模型合同

- `learning_data.py` 当前合同为 `d3_learning_dataset_v2`，split policy 为
  `d3_numeric_seed_atomic_split_v2`。采集帧显式标记 `unassigned`；finalize 取得完整唯一
  数值 seed catalog 后，按 seed 数量确定 train/validation/test，scenario version、规模和
  episode 不参与 seed 身份。同一数值 seed 的所有 scenario/scale/episode/frame 必须原子
  进入一个 split，三个数值 seed 集合两两不交。少于 3 个唯一 seed 或 test 少于声明的
  unseen 数时不写 manifest；正式默认声明 20，synthetic smoke 必须显式降为 1。
- v2 manifest 固化唯一 seed 数、逐 split seed/episode/frame 数、split 参数、split hash 和
  canonical `frames.jsonl` SHA256。loader 重算分配与统计并校验完整文件 SHA；v1 dataset、
  v1 scenario/seed split、冲突预分配和任何篡改均明确拒绝，不做静默迁移。
- `write_learning_dataset()` 用临时 SQLite 只保存排序键和 payload 偏移，以磁盘 JSONL
  sidecar 保存单次 canonical 编码结果，再按稳定键流式输出；
  `iter_learning_frame_records()` 可逐行消费 staged JSONL。每帧仍只保存匿名 ordinal
  target/resource 摘要、`E x 12` 候选边特征、mask、规则成本/选边、版本、反馈/迟滞和
  reward 分量，不保存原始 ID、truth actor 或上游 metadata。
- `learning_bundle.py` 保留 `d3_learning_model_bundle_v2` 兼容加载，并对正式开发模型使用
  `d3_learning_model_bundle_v3`。v3 在 feature/policy、split hash、归一化、guardrail、
  dataset/split schema 之外增加 provenance 与 admission。v1 bundle 稳定回退为
  `model_bundle_schema_unsupported`；缺失、损坏、SHA、特征或合同不匹配均返回逐元素相同
  的 `C_rule`，权重只用 `torch.load(..., weights_only=True)`。
- shadow 可加载未晋级 bundle。assist 必须显式调用 `load_model_bundle(...,
  mode="assist")`，且 promotion manifest 同时满足 recommended、至少 20 个未见 test
  seed、安全/成本非退化和零 fallback；仅写一个 true 布尔值不能绕过门控。

### BC、PPO 与 paired shadow

`SharedEdgeActorCriticPolicy` 共享同一 edge encoder，支持任意当前候选数 `E`。每边
actor 输出 bounded residual；value 使用 masked mean-pooled frame context；hold/replan
是按 `advice_allowed` 低频开放的建议。BC 按 frame mini-batch 跨多个 episode 学习规则
选边、规则 residual teacher 和 hold/replan，并输出 train/validation loss 与完整 seed
指标。原生 PyTorch PPO 使用 clipped objective、GAE、value loss、entropy 和 gradient
clip；每次动作经确定性 mask 与 Hungarian demand-slot solver 后，才按规则成本、高威胁
覆盖、未满足槽、churn、过期和安全拒绝重算离线 reward。

`shadow_evaluation.py` 在相同 scenario/seed/frame 上复制同一规则矩阵，分别求解 rule
和 bounded proposal，报告 assignment cost、高威胁 unmet、churn、duplicate/hard
violation、推理 P50/P95 和 fallback reason。unseen 与 whole-seed 指标按全局数值 seed
跨 scenario 聚合，输入必须先通过完整三分合同；shadow 从不改写规则矩阵，也不发布计划。

四个 CLI 子命令为：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli generate-data --output /tmp/d3_data
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli train-bc --dataset /tmp/d3_data --bundle /tmp/d3_bc_bundle
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli train-ppo --dataset /tmp/d3_data --input-bundle /tmp/d3_bc_bundle --bundle /tmp/d3_ppo_bundle
PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m d3_assignment_planner.learning_cli shadow-eval --dataset /tmp/d3_data --bundle /tmp/d3_ppo_bundle --output /tmp/d3_shadow.json
```

### 当前证据边界

此前 30-seed synthetic smoke 的 `23/1/6` split、loss 和 shadow 时延来自 v1
scenario/seed policy，只保留为历史开发记录；v2 loader 与 bundle loader 均拒绝把该产物
解释为当前合同。该段记录的是正式训练前的软件合同阶段；最新正式 loss、成本和时延见
本文末尾的“正式数据行为克隆开发模型”。

软件合同回归覆盖同一数值 seed 在 2v2/5v5 风格 scenario、多个规模和 episode 中复用、
输入逆序确定性、三 split 零交集、唯一 seed/unseen 数不足、split/frame/hash 篡改、v1
dataset/bundle 拒绝、训练和 shadow 的全局 seed 计数。D3 全量收集 244 项，结果为
`243 passed, 1 skipped`；唯一 skip 是 optional OR-Tools installed-only case。

200v200 dense fixture 单帧含 40,000 candidate edge，canonical JSON 约 5,854,691 bytes；
NumPy payload 加 edge tuple 浅层约 5,161,640 bytes。当前 scalable main finalize 已把
`iter_learning_frame_records(staging_path)` 直接传给 writer，不再在调用侧执行
`read_text().splitlines()` 和完整 tuple 构造。正式 900-episode 数据容量、故障/密集场景
最坏值和长期磁盘预算仍需由 main 在 clean tree 上验收。

本批没有提交正式权重，没有真实 D2/D3 轨迹训练，没有至少 20 个未见真实/高保真 seed，
也没有 CPU/GPU deadline 分布、AirSim 物理收益或可抢占 timeout 证据。当前结论仅为
管线实现和合成 smoke；规则 Hungarian 继续是唯一默认路径。

本次结果是软件数据合同证据，不是模型性能、AirSim 物理收益或 assist promotion 证据。

## 2026-07-20 单帧只读规划证据

`AssignmentPlanner.latest_planning_evidence` 现返回
`PlanningFrameEvidence`（schema `d3_planning_frame_evidence_v1`）。planner 只保留最近
一次规划尝试：每次 `plan()`、`plan_incremental()` 或
`plan_regional_authority()` 开始时先替换旧帧，成功后保存与该次输入一致的 rule
`CostMatrixResult`、实际送入 solver 的 effective `CostMatrixResult`、计划
`plan_id/version`、规划时间、前序版本，以及构造 `LearningFrameRecord` 所需的
tracks/resources/plan 安全副本。新 episode 仍按既有合同创建新 planner；新实例初始
状态为 `available=False, reason="no_planning_frame"`。

证据明确区分四种 learning 状态：`rule_only`、`shadow_proposal`、
`assist_effective` 和 `rule_fallback`。shadow 的 proposal 是独立只读矩阵，effective
矩阵仍逐元素等于 rule；assist 只把有界 residual 后矩阵标为 effective；timeout、低
置信、OOD、bundle/version 等 fallback 必须保持 effective 与 rule 逐元素相同并给出
`fallback_reason`。solver 名称单独记录，因此 SciPy Hungarian 与 `fallback_dp` 也可
审计，默认 `learning_assistant=None` 和 Hungarian 行为未改变。

该接口只存在于 planner 本地对象，不写入 `AssignmentPlan.metadata`，不定义线上 DTO，
也不上 D4/D7 总线。快照把输入 ID 重映射为 `target_0000/resource_0000`，剥离上游
metadata、node/actor/object/truth alias；NumPy 数据来自独立不可写 buffer，嵌套 mapping
也只读。held、unchanged、forced-replan ack 和有效 regional authority 均保存当前输入
帧；stale/区域拒绝、无矩阵 authority fence、证据不一致或无匹配成本帧的外部 publish
只返回 `available=False` 和明确 reason，不回退到上一帧。

main 可直接调用：

```python
record = build_latest_learning_frame_record(
    planner,
    scenario_version=scenario_version,
    seed=seed,
    episode=episode,
    frame_index=frame_index,
)
```

helper 使用证据中的 timestamp 和 rule matrix，继续输出匿名 ordinal token；调用方不再
调用私有 `_build_search_matrix()`，也不重复构造可能与真实规划不一致的成本矩阵。
2026-07-20 新增 11 个专项测试，覆盖首帧、held/unchanged/forced replan、shadow、
assist、learning/solver fallback、regional 成功与拒绝、失败清旧帧、外部修改隔离及
1x3、3x2、7x4 roster。D3 全量共收集 226 项，结果为
`225 passed, 1 skipped`，零失败达到门限；skip 仍是未安装 optional OR-Tools 的
installed-only case。main 尚未用真实 AirSim episode 导出整 seed 数据，因此这里只
关闭 D3-owned recorder 接口缺口，不构成真实数据、shadow non-degradation 或 assist
晋级证据。

## 2026-07-20 上一轮区域资源提示约束下一轮候选图

普通入口现支持可选关键字 `regional_planning_hint`。D3 自有且冻结的
`RegionalPlanningHint`、`RegionalPlanningConstraint` 和
`RegionalTransferAllowance` 使用 schema `d3_regional_planning_hint_v1`；调用方也可
传入中性 mapping，由严格 `from_mapping()` 解析。该解析不导入 D4 类型，拒绝未知字段
以及 truth/actor/object/target/resource 身份字段。提示携带 advisory identity/version、
created/expiry、精确 source plan、逐区域 owner/epoch/lease、projected、quota delta、
reserve ratio、hold/request-replan 和邻区 transfer allowance。

提示只在显式提供时进入普通规划。D3 要求 source `plan_id/version` 与
`previous_plan` 完全一致，当前 timestamp 同时落在提示与全部区域 lease 内，当前 target/
resource 区域集合可解释，projected quota 总和守恒且与 transfer 净额一致。每个源区按
当前资源数、上一计划全部 assignment/coalition 成员和 post-quota reserve floor 计算
可转移容量；不满足时不把 transfer 当成 0，而是写入明确 fallback reason 后重新执行
原规则路径。

合法提示在规则矩阵和 switch penalty 之后、learning residual 之前约束候选 mask。同区
边保持原规则门控；跨区只开放给该 route 固定大小且互斥的未承诺资源池，因此普通
Hungarian 的资源唯一性直接形成 transfer count 上限。M-to-N role/wave slot 继续复制同一
mask，D5 hard edge、能力/可达性、学习有界代价、迟滞和版本发布均不被绕过。最终
`AssignmentPlan.metadata` 记录 available/considered/applied/rejected、advisory/source
identity、fallback reason、逐 route allowed/actual count 和实际跨区资源总数，供 D6
审计。无提示时规则矩阵、learning 调用和 Hungarian 路径不变。

2026-07-20 新增 14 个确定性 pytest case，覆盖严格解析、无提示等价、1-to-1 实际跨区
选边、8 类非法/过时回退、commit/reserve 保护、M-to-N 两资源 transfer 上限，以及 D5
hard edge 与 learning assist 共存。seed 不适用于该模块 fixture；接受门限为全量零失败。
D3 共收集 240 项，结果为 `239 passed, 1 skipped`，skip 是既有 optional OR-Tools
installed-only case。本批没有运行 AirSim、正式多 seed 性能或物理拦截；main 仍需把
D4 `RegionResourceRecommendation` 显式映射为 D3 DTO，并在 reset-separated episode
中验证时间基准、owner/epoch/lease 和 D6 指标。

## 2026-07-20 Learning 安全复核补正

本轮对可选 BC/PPO/shadow/assist 路径做 fail-closed 复核，不改变默认 Hungarian、
`hungarian_demand_slots`、联盟准入、计划版本或 D7 授权链：

- BC 训练入口只接受 `train`/`validation`，PPO 只接受 `train`；任一训练 API 收到
  `test` frame 都拒绝。CLI 对完整 dataset 的读取只用于内容、哈希和三分合同校验，
  test frame 不进入训练 batch、normalization 或训练期 whole-seed metric；test 仅由显式
  `shadow-eval --split test` 入口消费。
- `LearningFrameRecord.from_dict()` 对 v2 使用完整字段 allow-list；普通扩展必须升级
  schema。解析前递归拒绝 truth/actor/identity、实体 ID、UUID 和 vehicle-name 类字段，
  同时保留已知匿名 ordinal、数值/布尔字段及语义性 hard-reject reason 的兼容策略。
- `candidate_mask` 是候选提示，不是授权。候选索引、assistant 返回 mask 和 solver 消费
  mask 都始终与 `reject_reasons is None` 求交，shape 不一致失败关闭，不能重开 D5、
  可达性、容量或友方冲突 hard edge。
- bundle v2 同时绑定 split hash、canonical `frames.jsonl` SHA256 和
  `state_dict.pt` SHA256。assist 不允许关闭 promotion gate；promotion evidence 必须是
  `d3_shadow_promotion_evidence_v1`、正式 `test` split、`evidence_eligible=true`、
  `paired_rule_residual_shadow`、`rule_cost_matrix_v1`，且三项摘要与 bundle 完全一致。
  布尔和计数字段采用严格类型校验，错配或伪装均回退 `C_rule`。
- residual proposal 仍按 `C_final=C_rule+alpha*tanh(delta_C)` 产生候选方案，但 rule 与
  proposal assignment 的非退化指标都按同一个最终 `C_rule + unassigned_costs` 基准
  重新评分，禁止比较不同矩阵各自的 solver objective。学习输出始终只是受约束提案，
  不能直接授权 assignment、coalition 或 D7 执行。

2026-07-20 全量收集 252 项，结果为 `251 passed, 1 skipped`，接受门限为零失败；唯一
skip 是未安装 optional OR-Tools 的 installed-only benchmark。新增负例覆盖 test-seed
训练拒绝、训练指标隔离、递归 identity/未知字段拒绝、hard-reject mask 求交、frame SHA/
promotion 证据错配、validation/非 eligible/bypass 拒绝和共同规则代价重评分。本轮未训练
或提交正式权重，未运行 AirSim，也没有至少 20 个未见真实/高保真 test seed、正式
promotion、模型收益或物理闭环结论。

## 2026-07-20 200×200 学习帧导出性能复核

本轮只优化 D3 学习帧构造、canonical JSONL 读写和数据集 finalization，不改变
Hungarian、学习残差、硬拒绝掩码、`plan_version`、truth isolation、dataset schema 或
任何输出字段。候选特征构造按目标缓存一次 `effective_demand`；学习帧的硬拒绝计数复用
同一 action-mask 扫描结果。JSONL identity 检查改为迭代遍历容器，避免对密集数值数组
中的每个标量递归调用。

finalization 仍先验证每个 `LearningFrameRecord` 的当前数组、掩码、匿名实体和身份字段，
随后只做一次 canonical 编码。临时 SQLite 保存排序键、payload offset 和 size；payload
写入临时 JSONL。最终排序阶段只读取对应字节并替换唯一受控的 `split=unassigned`
占位符，不再执行第二轮 `json.loads -> from_dict -> replace -> to_dict -> json.dumps`。
正序、逆序输入和旧重编码语义输出逐字节相同，frame SHA256 与 manifest 规则不变。

同机开发微基准使用 200 targets、200 resources、top-32、每帧 6,400 candidate edges、
6 帧。墙钟只作归因证据，不作为单元测试门限。

| 阶段 | 修改前 | 修改后 | 变化 |
|---|---:|---:|---:|
| 单帧 frame build 中位数 | 48.19 ms | 22.99 ms | 2.10× |
| 单帧 JSON decode + validate 中位数 | 95.92 ms | 56.09 ms | 1.71× |
| 6 帧 dataset finalize 中位数 | 910.20 ms | 243.65 ms | 3.74× |
| 匹配 cProfile/Tracemalloc 峰值 | 14,575,699 B | 12,725,690 B | -12.69% |

当前 top-32 帧约 2.20 MB；九场景 D3 正式帧证据总计约 27.86 MB，数据内容和存储量按
要求未压缩或删减。模块局部测得的六帧构造、首次编码、逐行读取和 finalization 合计约
0.87 s，不能把 main 记录的 D3/D4/D5 总耗时全部归因于 D3。

main 随后在干净工作树上复跑 nominal 200v200、seed 930/931/932、每个 episode 2 s。
优化后产物由 commit `4052d9411363c39d52100c0e3a4f60ee88443cab` 生成，清单记录
`repository_dirty=false`。总生成耗时由 467.8007 s 降至 262.2866 s，artifact staging
由 225.9243 s 降至 126.4682 s，总 finalization 由 116.5624 s 降至 7.7377 s；episode
run 为 125.2205 s 与 127.9871 s，基本未变。这里的总 finalization 同时包含 D3、D4、D5，
不能作为 D3 单模块耗时。

分项记录给出的 D3 stage 分别为 0.0917 s、0.1129 s、0.0999 s。D3 数据集共 6 帧，
train/validation/test 各 2 帧，正常最终化，在线真值使用为 0。该证据关闭 D3-owned
重复编码和最终化热点及其跨模块归因问题，但不是正式 900-episode 生成、模型训练、
至少 20 个未见 seed 评估或 AirSim 结果。

可复现命令：

```bash
python3 research_modules/d3_assignment_planner/simulations/run_learning_export_profile.py \
  --count 200 --max-candidate-edges 32 --frame-count 6 --repeat 5
```

结果文件为 `results/scalable_3d_learning_export_profile_20260720.json` 和配对比较 JSON。
D3 全量回归收集 255 项，结果 `254 passed, 1 skipped`；唯一 skip 是 optional OR-Tools。
剩余 CPU 热点是标准库 JSON 对 NumPy 数组执行 `tolist()` 和 canonical `json.dumps()`。
继续减少该部分需要引入新编码依赖或改变持久化格式，因此不在本次无 schema 变化任务中
处理。

## 2026-07-20 正式数据行为克隆开发模型

正式 D3 数据位于三维规模化仿真学习数据目录，只读审计通过。清单包含 900 episode、
1604 帧和 100 个数值 seed，train/validation/internal-test 为 962/320/322 帧，对应
60/20/20 个 seed。canonical frame SHA256 为
`6761d35d6b48639a5eb4f3306f7b3f12ca72352a1028296a0c39a4b90fdb59a2`，split hash 为
`679a9051e8637fad38d935eb685f09dd8abc8d43043a28264dab64b077ac70a2`。外部保留 seed
1000-1019 与当前数据交集为空，也未在本轮评估中消费。

训练使用固定 seed `20260720`、12 epoch、隐藏层 64、Adam 学习率 0.001、8 帧小批次和
正类权重上限 16。正类加权只处理规则已选边约 3.2% 的类别不平衡；学习输出仍是
`C_final=C_rule+alpha*tanh(delta_C)`，`alpha=0.25`。不可达边、硬拒绝、需求槽、容量、
版本、迟滞和 Hungarian 求解不进入学习动作空间。训练损失由 1.083713 降至 0.468781，
验证损失为 0.469243。内部 test 的边排序一致性为 0.8031，计划完全一致率为 0.6770，
平均规则成本差为 +0.022345，相对差约 +0.0091%；需求满足率与 rule-only 同为 0.975689，
重复分配和硬门控违规均为 0，平均重分配 churn 均为 70.1149。

内部 test 模型推理 P50/P95/P99 为 0.506/2.554/2.809 ms。按 5/20/50/100/200 名义规模，
推理 P95 分别为 0.247/0.433/0.860/1.434/2.793 ms。当前 OOD 规则按“单帧任一候选边任一
特征超过 6 个标准差”判定，内部 test 有 163/322 帧回退规则路径。该现象和轻微成本退化
说明模型不能晋级 assist，后续需在外部保留 seed 上重新标定 OOD、confidence 和 deadline。

新 bundle schema 为 `d3_learning_model_bundle_v3`，增加训练日期、数据 manifest SHA、
训练源码 SHA、Git 基线提交、工作树状态和显式 admission。提交 `39b097e...` 是正式数据
生成与训练基线；训练时存在 D3 模块改动，精确源码由 training-source SHA256 绑定。当前
状态固定为 `development/shadow-only`；即使
有人写入 recommended promotion，loader 仍返回 `bundle_shadow_only`。权重 SHA256 为
`e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2`。权重和 bundle 位于
ignored `outputs/formal_bc_development_20260720/bundle`，不进入普通 Git 提交；tracked
`results/formal_bc_development_20260720` 只保留审计、配置、命令、指标报告和定位说明。
当前环境没有 Git LFS，长期权重需由 main 转存到 Git LFS 可用环境或独立制品存储。

复现入口为：

```bash
PYTHONPATH=research_modules/d3_assignment_planner/src python3 \
  research_modules/d3_assignment_planner/simulations/run_formal_bc_development.py \
  --dataset research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/learning_dataset/d3_assignment \
  --output research_modules/d3_assignment_planner/results/formal_bc_development_20260720 \
  --bundle-output research_modules/d3_assignment_planner/outputs/formal_bc_development_20260720/bundle \
  --repository-git-commit 39b097e72487567ac915c2297eaa27eed49ef76b
```

本轮没有启动 PPO，没有更改 AssignmentPlan 版本、`global_track_id` 或 D7 binding。内部
test 是开发集内的独立切分，不是最终 20 个保留 seed 准入。main 下一步必须使用同一冻结
权重运行 seed 1000-1019，并由 D6 独立汇总安全非退化、成本、需求满足、抖动、回退和时延。
新增正式审计、v3 bundle、加权 BC 与开发评估测试后，D3 全量收集 258 项，结果为
`257 passed, 1 skipped`；唯一 skip 仍是 optional OR-Tools installed-only case。

## 2026-07-21 共享 Seed 切分注册表绑定

D3 增加只读共享切分验证边界，用于 C1 跨模块联合训练前的 seed 对齐。默认
`load_learning_dataset(path)` 行为保持不变；只有同时传入 `shared_seed_registry_path` 和
`training_seed_registry_path` 时，loader 才验证 main-owned detached registry。只传一个
路径、schema/policy 不匹配、registry content/assignment SHA 不匹配、源 registry 文件
SHA 不匹配、seed 缺失或增加、保留 seed 混入、同一数值 seed 跨 split，均失败关闭。

正式 900-episode 数据只读验证结果如下：

| 项目 | 结果 |
|---|---|
| 训练 seed | 100，train/validation/internal-test 为 60/20/20 |
| 保留 seed | 1000-1019，与数据交集为 0 |
| registry file SHA256 | `68608d29d1f733beea87f1faf06464fededb68a9c2972c51c10cd4c2160f032f` |
| registry content SHA256 | `29eb6895c4aa570b068f15141cbbbfede3041519117852d1ad48e848a25af146` |
| assignment SHA256 | `31c6a3fc265d088d9958f44d579d8098e2aeab06b0daa60c68452ae4c6d46ab5` |
| source registry SHA256 | `2ab928a476a4430b99326f245222f058bc5be5025158134ba89b01b3dec7815f` |
| 原文件变化 | dataset manifest、frames、共享 registry、源 registry 前后哈希相同 |

通用学习命令和正式行为克隆入口均接受以下参数：

```bash
--shared-seed-registry \
  research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/shared_seed_split_registry_v1/registry.json \
--training-seed-registry \
  research_modules/scalable_3d_simulation/outputs/learning_generation_v1_multibatchfix/training_seed_registry.json
```

启用后，新 bundle 的 `training_results` 和正式训练报告记录
`d3_shared_seed_split_binding_v1`；正式入口另写只读 provenance sidecar。旧 v2/v3 bundle
仍可走非联合开发路径加载，现有正式 BC bundle 和原数据没有原地修改。本项只消除 D3
切分歧义，不构成 assist 晋级证据；状态仍为 `development/shadow-only`，PPO 未启动。
D3 全量回归为 `269 passed, 1 skipped`。

## 2026-07-21 正式分配数据全样本准入审计

新增 `assignment_full_sample_audit.py`，对正式 D3 分配数据执行只读、流式、失败关闭审计。
审计绑定数据清单、883 MiB 帧文件、训练 seed 注册表、共享切分注册表、生成摘要、episode
进度和批量导出摘要共 7 个源文件。所有源文件在扫描前后重新计算 SHA256；输出目录必须
位于正式数据根目录之外。审计逐帧调用 v2 严格解析器，并复核有限数值、候选边与动作
标签维度、动作索引、资源容量、目标需求槽、匿名 token、数值 seed 切分、帧顺序、时间
顺序和前序计划版本单调性。

2026-07-21 的正式结果为：900 个实际 episode、1604 个决策帧、3658815 条候选边、
3658815 条资源-目标动作标签和 117304 条规则选中动作。100 个规范数值 seed 按
60/20/20 切分；场景展开后的实际 episode 为 540/180/180，决策帧为 962/320/322，
不能把三组计数互相替代。43905780 个候选特征值全部有限；容量、需求槽、索引、切分、
前序版本、在线真值和非法 `global_track_id` 违规均为 0。生成进度记录 900/900 个有限
episode、0 个脏 episode、0 次在线真值使用，以及 194 个明确未导出帧原因；没有以前一
帧补数。正式源文件哈希未变化。

数据结构审计状态为 `complete`，总体准入状态为 `partial`。学习帧只有匿名 ordinal token
和 `previous_plan_version`，没有当前计划 owner、当前 plan version 或运行时 stale 拒绝
记录。`reward_components` 是规则代价、覆盖、未满足需求和抖动诊断，不是可归因的运行时
回报。真实 applied ACK、outcome、因果/反事实 reward 和同 seed 配对 shadow 均为
`unavailable`。因此没有训练或写入权重，PPO、assist 和在线权限保持关闭；默认路径继续
使用规则代价与需求槽匈牙利求解。

产物为 `results/assignment_full_sample_audit_20260721.json` 和
`reports/D3_ASSIGNMENT_FULL_SAMPLE_AUDIT_20260721.md`。JSON 文件 SHA256 为
`62a47df8058c0238498f2181229a5f6d45f6d958799eda354f03e25ea24b17fb`，去除
`content_sha256` 字段后的规范内容 SHA256 为
`954f3e96d563412644ec88d1b621e2a58c781af8af99de79b859d22079fc1867`。新增 10 个负例和
正常路径测试；D3 全量收集 280 项，结果为 `279 passed, 1 skipped`，唯一 skip 为可选
OR-Tools 安装检查。

## 2026-07-21 运行计划确认消费合同

D3 新增独立的 `runtime_plan_ack.py`，用于只读消费 main 发布的
`scalable3d-assignment-plan-runtime-ack-v1`。调用方必须同时提供确认载荷、D3 来源
计划的完整总线 envelope、可选 D7 来源命令 envelope 和内存中的预期
`AssignmentPlan`。验证器不导入 main 模块，也不调用规划器或发布计划。

验证链按以下顺序失败关闭：

1. 检查 ACK schema、字段白名单、有限时间和正整数来源序号。
2. 使用 UTF-8、键排序、紧凑分隔符和 `allow_nan=false` 复算 D3/D7 payload
   SHA-256，并与 ACK 中的来源摘要逐项核对。
3. 将 D3 来源计划与预期计划的 plan id/version/schema、目标和资源计数、未分配清单、
   solver、metadata 及全部 assignment 对齐。
4. 对每个资源精确核对 `global_track_id`、coalition id/version、member role 和区域
   owner 字段；重复、缺失、额外或重绑均返回稳定错误码。
5. 将 D7 命令与每条 binding ACK 对齐，再独立重算 fully-bound、control-applied 和
   held 统计。D7 不能借 ACK 改写 D3 的中心航迹身份。

`d3_learning_evidence` 缺字段时保持 unavailable。只有来源计划明确记录
`mode=assist`、`applied=true`、`bundle_loaded=true`，并且上述来源、计划和绑定
检查全部通过时，结果才标记 `runtime_learning_applied_ack_available=true`。
`shadow`、规则教师 `reward_components` 和单纯的运行时计划接受均不满足该条件。
运行 ACK 自报物理结果或 reward 会被拒绝；这两类证据只能由后续 D6 独立 sidecar 提供。

2026-07-21 增加自动化真实 main 集成回归：当前三维集成栈执行 3v3、seed 7、1.2 秒，
总线产生 2 条计划 ACK，公开 D3 consumer 验证最后一条 ACK。最终计划 3 条 binding
全部进入 D7，control-applied 为 3、held 为 0，在线真值使用为 0。该次计划没有学习
mode，验证结果因此保持学习 applied ACK unavailable；物理 outcome 和 reward 也为
unavailable。consumer 源码不导入 main；只有 D3 测试导入 main 集成栈，以避免运行时
耦合和循环导入。

consumer 同时兼容项目现有顶层与 namespaced 两种合法 D3 包路径。兼容检查限定模块名、
类名、精确数据类字段集合和 AssignmentPlan schema，不接受任意鸭子类型。专项 24 项
测试和 D3 全量 304 项均完成，全量结果为 `303 passed, 1 skipped`，唯一 skip 仍是可选
OR-Tools。

该接口已经实现并经当前 producer smoke 验证，但冻结的 900-episode 正式数据生成于
ACK producer 之前，仍没有 current owner/version、applied ACK、outcome 或 reward。
PPO、assist 和在线 authority 继续关闭，规则代价与需求槽 Hungarian 仍是默认执行路径。

## 2026-07-21 已采用计划窗口归因合同

D3 新增 `runtime_reward_evidence.py`，将现有运行计划 ACK 与 D6
`d6.runtime-plan-outcome-join.v1` 离线结果连接为
`d3_runtime_plan_window_reward_evidence_v1`。输入必须包含经过
`validate_assignment_plan_runtime_ack(...)` 验证的 ACK、ACK 总线序号、完整 D6 联接
结果及其外部规范载荷 SHA-256，并明确指定资源和 `global_track_id`。适配器不导入 D6 或
main，不读取文件路径中的真值身份，也不修改计划。

每个输出同时绑定：

- plan id/version、中心/二级 owner、authority epoch；
- D3 来源计划、D7 消费命令和 main ACK 的严格递增总线序号；
- D3/D7 来源载荷 SHA-256、ACK 证据 SHA-256、D6 结果 SHA-256 和 11 项来源文件摘要；
- 资源-航迹、联盟、角色、ACK occurrence、刷新类型、执行签名和不重叠时间窗。

证据层明确分成 command、ACK applied、observed outcome、paired、counterfactual 和
causal。D6 的五米接近事件和有界最优距离进展只保留为离线观测诊断，不能自动写成因果
奖励。现有 `OfflineRewardComponents` 六项仍是规则教师诊断；新合同逐项输出
availability/reason，当前不补零。缺 ACK、owner、来源序号/哈希、字段、窗口，或者出现
窗口重叠、刷新语义错误、版本回退、在线真值使用和自报 reward，均失败关闭。

2026-07-21 的专项测试为 `16 passed`。其中一项运行真实 main 三维质点 3v3、seed 41、
1.2 秒，并消费 main 自动生成的 D6 结果；选定 binding 的命令、采用和结果窗口连接成功，
正式 reward 仍为 unavailable。2026-07-22 按当前调度重放时，总线包含两条来源完整的 ACK：
首条 ACK 有 3 个非保持 binding，末条 ACK 因航迹年龄超过 D7 的 `0.75 s` 门限而以
`global_track_stale` 保持。consumer 先逐条验证 ACK 及其发布时计划快照，再按总线顺序选择
首个非保持 binding 接入 D6；保持 ACK 不作为 `ack_applied` 样本。D3 全量收集 320 项，结果为
`319 passed, 1 skipped`；唯一 skip 是未安装的可选 OR-Tools。Hungarian、
`C_final=C_rule+alpha*tanh(delta_C)`、确定性安全外壳、PPO/assist/authority 状态均未改变。
当前修复后的 2026-07-22 全量回归共 439 项，结果为 `438 passed, 1 skipped, 0 failed`。

仍缺同 seed 配对运行、反事实结果、因果归因、计划级六项运行结果和外部保留 seed 证据。
这些条件闭合前，`formal_d3_runtime_reward` 保持 unavailable，PPO 不启动，规则回退保持
启用。冻结的 900-episode 数据没有新 ACK，未被回填或修改。

## 2026-07-21 保留 Seed 配对干预合同

`paired_intervention.py` 已实现规则基线与学习代价修正的正式实验边界。规范固定使用
seed `1000-1019`，每个 seed 必须同时声明相互隔离的 `control` 和 `treatment` arm。
两条 arm 必须绑定同一场景版本、场景配置、初始世界状态、观测输入快照、D1/D2 lineage、
规则代价配置、D3 bundle、阈值、安全外壳和当前计划版本。control 固定走规则代价加
Hungarian；treatment 只在离线仿真 arm 内允许有界残差影响 Hungarian 输入，且必须声明
动作掩码、可达性、容量、版本、迟滞和安全门均已执行。

规范和 manifest 均可严格 JSON 往返，并通过
`validate-paired-intervention` 命令校验。缺 arm、seed 重复或缺失、任一配对哈希不一致、
bundle/阈值未冻结、stale plan、非有限值、在线真值字段、规则回退关闭和安全门缺失均
失败关闭。输出把 `paired_input_equivalence`、隔离 treatment 是否实际应用、运行时 ACK、
outcome、counterfactual 和 causal 分层；未连接 D6 sidecar 时后三项固定为 unavailable。

本轮只完成合同和失败关闭测试，没有运行正式 20-seed episode，也没有产生性能、收益、
反事实或因果结论。`PPO=false`、`online_assist=false`、`online_authority=false`、
`rule_fallback=true` 保持不变，默认执行路径仍为规则代价与需求槽 Hungarian。2026-07-21
专项结果为 `36 passed`，D3 全量结果为 `355 passed, 1 skipped`；唯一 skip 为未安装的
可选 OR-Tools 检查。

## 2026-07-21 保留 Seed 隔离执行入口

D3 新增 `offline_intervention_execution.py`，把上一节的配对规范落实为可调用的离线执行
入口。main 只需提供完整 `PairedInterventionSpecification`、seed `1000-1019` 对应的
20 个 `PlanningFrameEvidence` 和冻结 bundle 目录。执行器在 D3 内部完成模型读取、规则
臂复放、学习臂复放、Hungarian 求解、迟滞处理、哈希计算和收据组装，不要求 main 复制
manifest、PyTorch 权重或残差模型的加载细节。

执行顺序如下：

1. 重新计算每个匿名规划帧的输入快照 SHA-256，并与 control/treatment 规范逐项核对。
2. 计算规则矩阵和硬安全动作掩码 SHA-256。两条 arm 使用同一矩阵、同一掩码、同一前序
   计划和同一时间戳。
3. 生产 `load_model_bundle(..., mode="shadow")` 先验证 manifest、权重文件、数据合同和
   state dict。离线执行器再核对 manifest 文件 SHA、policy version、development/
   shadow-only 准入、保留 seed 清单和全部权重有限性。
4. control 使用规则矩阵加 Hungarian。treatment 只在
   `offline_simulation_intervention_arm` 内使用
   `C_final=C_rule+alpha*tanh(delta_C)`；分布外输入、低置信度、超时、非有限权重、模型
   异常或 bundle 不一致均回退到同一规则矩阵。
5. 对 20 个 seed 生成一个真实配对评估报告，40 份
   `PairedInterventionExecutionReceipt` 共享该报告哈希，并直接形成
   `PairedInterventionManifest`。输出计划标记为离线、不可发布、无运行时授权。

生产加载器没有放宽。development bundle 直接请求 `mode="assist"` 仍返回
`bundle_shadow_only`；离线 treatment 不构成 PPO、在线 assist 或 authority。执行结果只
包含规则成本、需求缺口、抖动、硬约束、回退和推理时延等 D3 规划层配对指标。runtime
ACK、物理 outcome、counterfactual 和 causal 均明确为 unavailable，仍由 main/D6 后续
生成独立证据。

2026-07-21 的专项测试使用 20 个保留 seed 结构、20 个匿名规划帧和临时冻结 v3
development bundle，实际执行 40 个隔离 arm。7 项测试覆盖正常执行、manifest SHA、
policy version、分布外门控、deadline、非有限权重、输入快照不一致和 JSON 产物；全部
通过。D3 全量收集 363 项，结果为 `362 passed, 1 skipped`，唯一 skip 为未安装的可选
OR-Tools。该结果证明执行入口和失败关闭逻辑可用，尚不等于正式三维主流程已经运行 seed
`1000-1019`，也不形成模型非退化或在线晋级结论。

## 2026-07-21 保留 Seed 控制臂精确重放

main 的 nominal 5v5、2.2 秒保留-seed 源帧暴露了一个重放缺口：匿名化曾清空前序计划的
执行所有权元数据，也没有记录调用时的 `forced_replan`。离线 control planner 因此把
中心所有权误判为新的执行控制变化，绕过迟滞并产生不同 binding。严格
`control_plan_replay_mismatch` 正确阻断了这些帧。

`PlanningFrameEvidence` 现在保留精确重放所需的真值安全状态：计划所有权与激活字段、
人工授权、源/目标节点和链路、同窗口迟滞计数、联盟执行语义以及 `forced_replan`。节点、
资源、目标和联盟身份统一匿名化；仅存在于前序计划的目标或资源使用
`previous_target_*` / `previous_resource_*` 占位符。输入快照 SHA-256 已包含
`forced_replan`。离线执行器从匿名证据恢复 planner 的授权和链路配置，control 需同时
复现 binding、执行签名、版本、窗口、决策状态、changed 标志和 N/M 规模，否则仍以
`control_plan_replay_mismatch` 失败关闭。

专项测试扩展为 9 项。新增 20-seed 真实形态夹具覆盖 5v5 迟滞保持、4→5 目标的
`replan_ack_no_change`、5→4 生命周期移除和前序目标占位符；故意篡改 binding 的负例仍被
严格门拒绝。D3 全量收集 365 项，结果 `364 passed, 1 skipped`，唯一 skip 为可选
OR-Tools。

另以 main 当前源帧和冻结 development bundle 做了不写盘内存复验：20 个 seed、40 个 arm
全部完成，control 状态为 15 个 `unchanged`、3 个 `held_by_hysteresis` 和 2 个
`replan_ack_no_change`，逐 seed binding 与记录帧一致，bundle 正常读取。该复验没有生成
main 正式产物，也没有运行时确认、物理结果、反事实或因果证据。生产 assist 准入、PPO、
在线 authority 和规则回退边界均未改变。

## 2026-07-21 二元特征分布门修复

正式 nominal 5v5、2.2 秒、seed `1000-1019` 的首轮落盘证据中，20 个 treatment 均以
`out_of_distribution` 回退。复核显示 11 个连续特征的最大 z 分数不超过 `1.6229`；唯一
超出旧全局门限的是 `previous_binding=1`。该特征在训练集中的均值为 `0.013906895`、尺度
为 `0.116464332`，按对称高斯公式得到 `z=8.4669`，但其定义域是伯努利端点 `{0, 1}`。

`FeatureDistributionGuard` 现按显式特征语义检查：`previous_binding` 只接受有限的 0 或 1，
允许 `1e-6` 浮点容差，合法端点不参与连续特征 z 门。`0.5`、越界值和非有限值仍判定为
分布外；其余 11 个连续特征继续使用原 `ood_z_threshold=6.0`。bundle loader 显式绑定
manifest 的特征顺序，未修改 manifest、权重或 normalization。

新增 `d3_feature_distribution_assessment_v1` 诊断结果。学习元数据可记录触发特征、候选边
偏移、最大连续 z、对应特征和失败原因，不记录目标、资源或全局航迹身份。原 `is_ood()`
布尔接口保留，现有消费者可以继续使用。

使用原冻结 bundle 和当前源帧完成不写盘复验。20/20 treatment 均进入隔离模型推理，
applied=20、fallback=0；时延最小/均值/P50/P95/最大分别为
`0.238/0.340/0.268/0.692/0.899 ms`。规则与 treatment 的重复分配、硬约束违规和高威胁
未满足均为 0，规则矩阵保持不变。D3 全量收集 373 项，结果为
`372 passed, 1 skipped`；skip 仅为可选 OR-Tools。该证据不包含运行 ACK、物理结果、
反事实或因果结论，PPO、生产 assist、authority 继续关闭，规则回退继续启用。

## 2026-07-21 v2 正式保留 Seed 证据

D3 对 main 生成的 v2 正式目录进行了独立只读复核：
`reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296`。当前源提交为
`78912963b67fe86ee9a8d29186b18a9dd60c460c`，与 20 条 source lineage 一致；20 个源 episode
均为 clean、finite，在线 truth 使用计数为 0。`SHA256SUMS` 文件 SHA256 为
`821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc`，manifest SHA256 为
`d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c`。清单内 5 个文件全部
通过 `sha256sum -c`；D3 执行产物 SHA256 为
`e878cd97f2a0f1c84fbd68b5ee996d0dc6d4e550cce42eab53558a33a120270b`。

20 个 control 和 20 个 treatment inventory 完整。20/20 treatment 均在
`offline_simulation_intervention_arm` 内实际应用学习代价，fallback 为 0；control 与
treatment 的有效代价矩阵 SHA 在 20/20 配对中不同，证明模型改变了隔离求解输入。最终
资源目标 binding 的变化为 0/20。规则与 treatment 的规则评分均值均为
`17.0560260319065`，高威胁未满足、重复分配、硬约束违规和抖动总数均为 0。

从 20 帧重新计算的推理时延 P50/P95 为 `0.246385/0.310801 ms`，与产物汇总一致。该结果
只证明隔离学习路径已执行且本批最终分配未变化。runtime ACK、physical outcome、
counterfactual 和 causal 全部 unavailable；promotion 状态仍为 unavailable。PPO、线上
assist、authority 保持 false，规则回退保持 true，运行时发布仍被禁止。

## 2026-07-22 D6 Profile-Bound v2 可用性审计

D6 已在提交 `d4e8562` 中作为独立只读消费者完成 profile-bound v2 审计。正式目录为
`research_modules/d6_evaluation_metrics/outputs/reserved_seed_interventions_nominal_5v5_1000_1019_formal_7891296_d6_profile_bound_v2_audit_20260722/`；
`outcome_availability_sidecar.json` 状态为
`pass_offline_assignment_comparison_only`。sidecar 文件 SHA-256 为
`f3852251daf02ec87fe878e7fb80aad6f381d8c0756a5c956a32e737a3871c3b`，规范内容
SHA-256 为 `c02a345c46ddc642dea7fb6bfcfb24184e7dc2a9f35b754c90324d074b445d2d`。

D6 独立复核确认 20/20 isolated treatment applied、0 fallback、20/20 effective cost
matrix changed、0/20 final binding changed。rule 与 treatment 的同帧 assignment cost
mean 均为 `17.0560260319065`；high-threat unmet、duplicate、hard violation 和 churn
均为 0。因此 `same_frame_offline_assignment_comparison` 已标记为 available，D3 的分配层
可用性和独立消费缺口已关闭。

该 sidecar 不包含本正式 artifact set 的 runtime ACK 或干预后的物理状态窗口。
post-intervention physical outcome、paired physical effect/non-degradation、counterfactual、
causal 和 promotion 仍为 unavailable；`PPO=false`、`assist=false`、`authority=false`、
`rule_fallback=true` 保持不变。以上边界不把“最终 binding 未变化”解释为物理无退化或策略
有效。

## 2026-07-22 隔离计划消费合同

D3 新增 `isolated_plan_consumption.py`，供 main 的 control/treatment 克隆世界在开始后续
状态推进前，确认某个隔离 arm 已消费指定 `AssignmentPlan`。构造接口
`build_isolated_plan_consumption_evidence(...)` 绑定 experiment/version、pair/seed/arm、
source snapshot lineage、plan id/version/schema、计划规范载荷 SHA-256、消费周期和时刻、
assignment/binding 数量及 binding inventory SHA-256。计划摘要通过生产 runtime ACK 使用
的同一计划结构检查后计算，但输出使用独立 schema 和
`accepted_by_isolated_simulation_consumer` 状态码。

`IsolatedPlanConsumptionValidator.validate_and_record(...)` 只在完整校验后记账。同一计划
重复消费、低于已消费版本的旧计划、相同版本换 plan id、非单调周期/时刻、错 arm、错
source snapshot、错 receipt、错 payload SHA 或不完整 binding 均失败关闭。证据固定声明
`production_runtime_ack=false`、`isolated_simulation_only=true`、
`control_applied_to_production_world=false`。物理结果、reward 和 causal evidence 均为
false，PPO、online assist、online authority 均关闭，规则回退保持启用。

2026-07-22 专项 8 项和 D3 全量回归已通过，全量结果为
`380 passed, 1 skipped`；skip 仍为可选 OR-Tools。该结果只证明 D3 计划消费合同可供隔离
仿真调用。main 尚未完成 control/treatment 多周期克隆世界、D7 命令 lineage 和干预后
物理状态窗口；D6 尚未据此形成 paired physical effect、counterfactual 或 causal 证据。

## 2026-07-21 离线目标库存兼容修复

真实 reserved-seed 重放在 `seed=1011/1019` 的 control/treatment arm 中触发 4→5 目标且
保持旧绑定。旧计划报告 `target_count=5`，第五个当前目标却未进入未分配或不完整清单，
严格消费因此失败。

离线执行器现于生成 arm 计划编号和回执前，依据当前匿名 `TargetTrack` roster 规范化库存。
零绑定目标同时进入 `unassigned_target_ids` 和 `incomplete_target_ids`；部分 M-to-N 联盟只
进入不完整清单；已退出当前 roster 的旧诊断目标被移除，旧可执行绑定继续失败关闭。
生产 runtime ACK 校验器没有放宽，离线证据仍固定 `production_runtime_ack=false`。

缺失 bundle 的 20-seed 扫描共 40 个 arm，严格计划摘要和隔离消费均为 `40/40`。历史首个
失败 `arm index=22, seed=1011, control` 现保留 4 个绑定，并显式记录 `target_0004` 未分配
且不完整。D3 专项为 `19 passed`，全量为 `382 passed, 1 skipped`；skip 仅为可选 OR-Tools。

## 2026-07-22 在线故障代际目标库存

在线中心规划、增量规划和区域授权规划现统一执行版本化目标库存规范化。迟滞可以保留
已有合法绑定，但当前规划帧中的新增目标必须进入同一计划身份。零执行绑定目标同时进入
`unassigned_target_ids` 和 `incomplete_target_ids`，并生成当前需求摘要。库存变化会生成
新的 `plan_id/version`，即使已有绑定集合没有变化；旧版本随即由发布登记和 stale 检查
拒绝。

`advance_authority_generation()` 会在存在匹配的最近规划上下文时，先按该上下文补齐当前
目标库存，再推进故障代际。previous-only 可执行绑定继续失败关闭。完整联盟要求候选成员
数等于可执行绑定数；不完整联盟保留候选成员数和需求短缺，但所有成员不可执行且不发布
assignment。区域授权可为新增目标发布 `unassigned_fail_closed` 合同，不授予执行权限。
计划在发布前继续调用严格载荷校验，生产 `runtime_plan_ack` 校验规则未放宽。

2026-07-22 回归共收集 386 项，结果为 `385 passed, 1 skipped`；唯一 skip 是未安装的可选
OR-Tools。只读三维质点集成复核使用 `center_failure`、5v5、3.2 秒、seed 1011 和 1019。
两个场景均在故障后得到 2 个可用规划帧，最终计划由 `RECON-001` 持有，版本和二级 epoch
均为 3；4 个旧绑定保持不变，第 5 个目标明确未分配且不完整，5 条需求摘要齐全，严格计划
摘要全部通过，在线真值使用为 0。本轮没有启动 AirSim，也没有改变控制授权或生产 ACK。

## 2026-07-22 故障代际离线重放

`center_failure` 的离线 control replay 现按在线计划顺序执行两步：先使用前序 owner 的规划
配置和冻结规则矩阵重建候选计划，再重放规划证据中已记录的二级接管或二级延续合同。离线
执行不再以记录计划的新 owner 直接求解，因此相同 5/5 绑定可重现
`replan_ack_no_change`、`changed=false` 和对应版本，而不是误报为 `replan_applied`。

authority 重放要求 evidence path 为 `authority_identity_publish`，并严格检查 recorded plan、
前序计划、二级 owner、active/executable 状态、激活时刻、lease、epoch 和 link。重放结果
再次通过 `validated_assignment_plan_payload_sha256()`，随后仍由原
`_control_plan_replay_matches()` 精确比较 binding、execution signature、版本、窗口、决策
状态和规模。匹配器没有放宽，离线证据继续声明非生产 ACK。

真实命令运行 `center_failure`、5v5、3.2 秒、seed 1000-1019 成功。20 个 control 和 20 个
treatment 全部生成，40/40 记录二级 identity replay 和严格计划回执；20 个 control 均为
`replan_ack_no_change`。seed 1011/1019 各保留 4 个绑定，`target_0004` 同时未分配且不完整，
需求摘要为 5 条。在线真值使用为 0，输出清单 5/5 通过 SHA-256。D3 全量共 387 项，结果为
`386 passed, 1 skipped`；本轮仍未生成生产 runtime ACK、AirSim 或物理结果。

## 2026-07-22 区域授权待分配库存

`plan_regional_authority()` 现允许 D4 区域授权只覆盖上一计划中的可执行绑定目标。授权集合
小于当前目标集合时，差集中的每个目标必须由上一计划严格证明为零执行绑定，并同时存在于
`unassigned_target_ids`、`incomplete_target_ids` 和一致的需求摘要中。摘要必须为零分配、
正短缺和未完成状态；已有不完整联盟时也必须为零成员。新增目标、漏掉已分配目标、摘要
篡改、未知授权目标和 previous-only 可执行绑定继续失败关闭。

通过验证的待分配目标只进入新计划库存，不生成区域 assignment、coalition、owner、lease
或 commit。计划元数据分别记录实际授权目标和无授权待分配目标，并把后者标为
`authority_granted=false`、`execution_authorized=false`。已有 4 个绑定保持 D4 的 owner、
epoch、lease 和 commit 约束；严格计划载荷校验规则及生产 runtime ACK 未修改。

模块正反例和 `secondary_failure` 集成回归均已通过。集成场景为 5 个目标、4 个区域授权
绑定、1 个显式待分配目标，时长 4.2 秒，seed 1011/1019；main 测试文件 10 项全部通过。
D3 当前收集 391 项，结果为 `390 passed, 1 skipped`，skip 为可选 OR-Tools。本轮仍是三维
质点合同验证，没有 AirSim、生产 ACK、D7 控制采用或物理拦截证据。

## 2026-07-22 非生产隔离执行计划升版合同

D3 公共接口 `build_isolated_execution_plan(...)` 现显式接收同一
`PlanningFrameEvidence`、`offline_solve_source_plan`、`formal_authority_plan`、本 arm
离线候选、arm specification 和原始 execution receipt。离线求解源固定为规划帧的
`previous_plan`，只用于核对 arm、receipt、候选元数据和输入快照。正式权威计划固定为规划
帧的 `plan`，决定隔离执行计划真正超越的代际和降级权威。

规划帧输入快照摘要、完整帧转换摘要、两个源计划载荷摘要和候选摘要共同进入
`d3.isolated-execution-plan-conversion.v2`。跨帧、跨 seed/arm、调用方替换同 ID/version
载荷、错误前序关系和版本跳跃均失败关闭。同 ID/version 的名义评估刷新可被同一规划帧
证明；版本前进时，正式权威必须是求解源的直接下一代。

输出固定为 `formal_authority_plan.version + 1`，并以
`previous_plan_id=formal_authority_plan.plan_id` 建立单步代际关系。`created_at` 使用正式
权威创建时刻与干预时刻的较大值，再取下一可表示浮点数，保证严格递增。有效期不超过 arm
要求、权威 lease、权威 stale 截止时刻和已有计划有效期中的最早值；没有时间空间时拒绝。

转换只重写计划身份和正式权威的 owner/source/link/epoch/lease 语义。候选 binding、未分配
和不完整目标、联盟、需求摘要及 N/M 规模原样保留并重新通过严格计划校验。隔离消费构造器
必须同时获得规划帧、两个源计划、原候选和转换证据，才能接受升版计划。旧的直接离线消费
路径保持兼容，生产 runtime ACK 和在线 `AssignmentPlanner` 未修改。

新计划固定声明 `isolated_simulation_only=true`、`production_runtime_ack=false`、
`runtime_publication_allowed=false`、`runtime_execution_allowed=false` 和
`online_authority_enabled=false`。该合同不产生生产确认、控制授权、物理结果、奖励或因果
证据。专项 18 项覆盖双源正常往返、同代刷新、版本、前序计划、跨帧、时间、lease、库存、
arm/seed/source 和 truth 篡改。普通 5v5 与 `center_failure` 各自使用 20 个 reserved seed、
40 个 arm 扫描；中心失效帧的求解源版本 1、正式二级权威版本 2、隔离执行版本 3 均通过。
D3 全量结果为 `408 passed, 1 skipped`，唯一 skip 仍为可选 OR-Tools。本轮没有运行 AirSim，
也没有产生 D4 adoption、D7 控制采用或物理结果证据。

## 2026-07-22 区域权威离线重放

离线执行器现识别 `planning_path=regional_authority`。`PlanningFrameEvidence` 对匿名前序
计划、记录区域计划、帧路径和时刻生成区域权威转换摘要；记录计划或前序计划的载荷发生
变化时，摘要校验先于求解失败关闭。普通中心规划和二级身份发布路径仍把记录输出视为
重放结果，没有改变既有输入快照语义。

区域帧回放从每条已授权 assignment 恢复区域层级、区域号、owner、epoch、lease 和 commit，
再调用线上 `plan_regional_authority()`。因此旧版本、过期租约、旧代际、缺失提交和非法成员
继续使用同一套 D3 校验。显式未分配且不完整的目标不进入授权 DTO，不产生 binding、owner、
lease 或 commit。重放后仍由原精确匹配器核对 binding、完整执行签名、版本、窗口和决策状态。
处理臂不能借学习代价越过记录的区域授权集合或 action mask。

真实三维质点 `secondary_failure` 使用规模 5、时长 3.2 秒和 seed 1000-1019，20 个 control
与 20 个 treatment 均生成。seed 1011/1019 的两个 arm 均保留 4 个绑定，`target_0004`
同时在未分配和不完整清单中，且没有区域 assignment。在线真值使用为 0。离线干预专项为
`23 passed`，D3 全量为 `419 passed, 1 skipped`；skip 仍为可选 OR-Tools。本轮没有运行
AirSim，也没有生成生产 runtime ACK、D4 物理采用或拦截结果。

## 2026-07-22 规划证据性能收敛

200 目标、200 资源、每目标最多 32 条候选边时，规划器仍保留 40,000 单元的确定性求解
矩阵和 6,400 条候选边。原实现对规则矩阵和有效矩阵分别深度匿名化全部单元，即使二者共享
同一 breakdown 结构，也会重复清洗和复制。单次规划约触发 80,200 次 breakdown 清洗，
规划证据成为确定性主耗时。

当前实现按源 breakdown 对象身份缓存只读匿名结果。规则矩阵和有效矩阵共享源结构时复用
同一匿名 breakdown/reject tuple，数值矩阵仍各自保存独立、不可写副本；学习残差形成不同
有效结构时仍分别处理。迟滞比较只复制 hard-safe candidate breakdown，不复制已裁剪或硬
拒绝单元。规则代价、不可达边、资源容量、M-to-N demand slot、Hungarian、迟滞、计划版本、
stale 拒绝、联盟和 D7 binding 合同均未改变。

独立同配置开发基准的向量化中位数由 `2651.953 ms` 降至 `189.111 ms`，加速 `14.023x`；
当前工作树复跑为 `195.716 ms`。cProfile 中 breakdown 清洗由约 `80,200` 次降至 `6,601`
次。完整 seed 42000、2.2 秒、200v200 质点链路的三次 D3 规划由 `7.329949 s` 降至
`1.013593 s`。这些是开发性能证据，不是硬实时验收，也不代表完整 episode 的全部提速均
来自 D3。结果记录见 `results/scalable_3d_planner_hotpath_20260722.json`。

新增测试覆盖 3x5、5x3、200x200、M-to-N 和 previous-plan 多周期语义及操作计数。定向
回归为 `62 passed`；D3 全量选定集为 `422 passed, 1 skipped, 2 deselected`。两项
`global_track_stale` 失败可在未修改 HEAD 复现，属于 main/D7 跨模块既有断点；D3 不通过
放宽 stale 门控处理。完整 200v200 多 seed、AirSim 和物理拦截仍由 main 组织后续验收。

## 2026-07-22 AssignmentPlan 在线成本证据去重

200v200 长时输出中，每条 `modules.d3.assignment_plan` 同时携带
`cost_breakdowns_by_edge` 和内容相同的 `current_cost_breakdowns_by_edge`。只读 seed
42000 样本的一条计划包含 6,304 条边，两份列表各占 4,757,920 字节。仓库消费者检索确认，
前者是 D3、D4/D6 回放使用的规范证据字段，后者没有 Python 消费者。

当前计划元数据使用 `d3_assignment_evidence_v2`。完整边成本只保存在
`cost_breakdowns_by_edge`，同时记录 `d3_cost_breakdowns_by_edge_v1`、条目数、规范
SHA-256、`inline_canonical_single_copy` 和旧字段引用。`assignment_evidence_from_plan()`
优先读取规范字段，并兼容 v1 的双字段或仅旧别名输入；v2 的计数、摘要、存储方式或引用不
一致时拒绝导出。`assignment_plan_v2`、Hungarian、候选集、迟滞、owner、版本、stale、
联盟和执行签名没有改变。

合成 200x200、6,400 候选边计划由 10,466,292 字节降至 5,622,366 字节，减少
4,843,926 字节，即 46.28%。同一测试确认 assignment、稳定签名、执行签名和计划身份一致。
只读 10 秒样本按新字段投影由 9,905,419 字节降至 5,147,795 字节，减少 48.03%；该数字
尚不是新代码完整 episode 复跑结果。新增专项 5 项通过。D3 全量收集 430 项，其中 427 项
通过、1 项因可选 OR-Tools 跳过、2 项为既有跨模块 `global_track_stale` 失败；D3 未放宽
stale 门控。

## 2026-07-22 冻结输入性能归因

新增 `performance_diagnostics.py` 和
`simulations/run_planner_performance_diagnostics.py`。接口使用定长
`D3PlannerOperationCounts` 记录成本矩阵、候选边、候选连通分量、Hungarian 准备矩阵、
计划边物化与规范哈希、迟滞重评分、匿名证据复制和发布校验的结构操作数。墙钟只写入
benchmark JSON/Markdown，不进入 `AssignmentPlan.metadata`、`plan_id`、执行签名或运行时
ACK。

冻结输入为 200 个匿名 GlobalTrack 代理和 200 个资源，seed 42000、top-32，输入
SHA-256 为
`c7c86f22252add5a6e201577ec99baa63050e56d00898e66d514ab3c0c46c7ff`。每帧保留
40,000 个全量目标资源对、6,400 条候选边、一个 200×200 候选连通分量和 80,000 个
Hungarian 准备矩阵单元。首帧匿名证据复制 80,000 个数值单元并访问 40,000 个 breakdown
单元，实际净化 6,401 个共享对象；上一计划帧另访问 6,400 条迟滞边并重评分 400 个绑定。

三次暖启动中，默认首帧/上一计划帧中位端到端为 `274.275/334.735 ms`。上一计划帧的
计划边证据、迟滞和离线匿名证据中位耗时分别为 `82.342/31.602/74.305 ms`，Hungarian
约 `4.460 ms`。关闭离线证据的归因参考为 `223.147 ms`，只说明该证据边界的成本，不是
允许在线关闭证据的新配置。

发布链路在一次规划调用内复用候选执行签名。latest published execution signature 由规划器
自有缓存跨帧保存并作为发布权威；caller previous 只计算一次签名并与该权威值做一致性校验，
不能替代 latest。公共 `publish_plan()` 仍从待发布对象计算 candidate signature。区域接管
先校验 plan id/version 和专用 pending inventory，再执行通用语义一致性校验。上一计划帧中，
默认身份固化/发布边界
为 `2.967/0.156 ms`，重复计算参考为 `15.629/13.246 ms`。默认、重复计算参考和关闭证据
参考的 binding SHA-256、计划版本和规范业务 SHA-256 完全一致；规则代价、Hungarian、
需求槽、迟滞、版本及 D5/D7 binding 未修改。原始结果见
`results/d3_planner_performance_attribution_20260722.json`，中文说明见
`reports/D3_PLANNER_PERFORMANCE_ATTRIBUTION_20260722_CN.md`。

该性能阶段初次收集 439 项，结果为 `436 passed, 1 skipped, 2 failed`。skip 是可选
OR-Tools；两个失败表现为 main/D7 `global_track_stale`。后续 seed 7 由 main 的未消费后验
锁存恢复，seed 41 由本模块修正 ACK 取样口径；当前同一全量集为
`438 passed, 1 skipped, 0 failed`，且没有放宽 stale 门。身份缓存、直接发布、authority
fence、区域错误优先级和性能诊断定向组合为 `46 passed`。

## 2026-07-22 clean 10 秒三种子集成复核

main 已在 clean commit `8f86192` 上完成 200v200、10 秒、seed 42000-42002 复跑。三组
`repository_dirty=false`、`finite_state=true`、`online_truth_use_count=0`。每组均发布
10 份 D3 计划并收到 10 次计划 ACK。D3 assignment 累计墙钟分别为
`3.437/3.319/3.110 s`，均值 `3.289 s`；旧 clean commit `3bac3ff` 的对应均值为
`3.348 s`，变化约 `-1.8%`。

三组的调用次数、计划发布数、计划 ACK，以及 binding ACK、control applied、hold 业务摘要
与旧提交逐 seed 一致。该复跑确认 D1 快照优化没有改变 D3 的计划执行语义。1.8% 的墙钟差异
按基本持平和调度噪声处理，不作为 D3 优化归因、实时能力或晋级依据。

冻结 200x200 benchmark 与本次集成复核是两组独立证据。前者保持默认上一计划帧
`334.735 ms` 等原始数字，用于固定输入下的热点归因；后者记录完整 10 秒 episode 中 10 次
D3 调用的累计墙钟和业务一致性。当前仍未证明 AirSim、物理拦截、长期内存上限或生产实时
能力。

## 2026-07-22 独立运行计划身份等价审计

`AssignmentPlanner` 有意使用 `uuid4` 为每个新执行谱系生成 `d3-plan-*`。因此，同一 seed、
同一输入和同一时间轴交给两个全新的 planner 实例时，首份计划及后续新谱系的原始
`plan_id` 应不同。这个随机身份用于避免不同 episode 或不同发布者把计划误认为同一对象，
不是规划算法的随机动作。单个 planner 实例内，纯成本或评估刷新必须复用原
`plan_id/version`；assignment、owner、activation 或 coalition 执行语义变化时才建立新
谱系。在线计划发布链路中，authority generation fence 是唯一允许“执行签名不变但身份升版”的显式隔离事件，
它必须保留专用原因和前序关系。

跨独立运行比较不得直接比较原始 `plan_id`，也不得递归删除所有 `*_id`。先按 D3 发布记录
的 `sequence_index` 或总线序号排序，对每个原始计划号按首次出现依次映射为
`P0000/P0001/...`。同一原始计划号的刷新继续映射到同一规范号；新计划必须保留
`version=parent.version+1` 和 `previous_plan_id/supersedes_plan_id -> parent` 的关系。
`current_plan_id`、`latest_plan_id`、区域提示的 source plan 引用及 fault fence source 引用
使用同一映射。由计划号拼接出的 binding/decision 标识应在替换计划号后重建，完整 payload
摘要也应对规范载荷重新计算。

下列内容仍须精确一致：计划版本与窗口、执行签名、目标-资源绑定、未分配和不完整目标、
成本与迟滞结果、decision/changed/published 状态、owner/source/link、stale/reject 原因、
coalition id/version/epoch/member/role/wave/commit/lease，以及 resource、target、
`global_track_id` 和节点标识。`coalition_id` 当前由目标标识确定，不属于随机计划身份，不能
归一化。原始 runtime payload SHA-256 包含随机计划号，跨运行不要求相同；同一运行内 ACK
仍必须精确匹配收到的原始摘要。

现有 `canonical_plan_business_sha256(...)` 是冻结 D3 基准的快速业务哈希，只删除少量计划
身份字段，不验证完整前序图、stale 引用或二级 owner 转换，不能单独作为跨模块长时运行的
谱系等价证明。完整算法和字段分类见 `docs/ALGORITHM_AND_IMPLEMENTATION.md`。当前
scalable runtime 的简化 D3 publication 未直接携带顶层 `previous_plan_id`；main 对现有
产物只能在版本连续且发布事件无缺失时用前一份已发布计划推导父关系，并应将证据标记为
`derived`。该简化载荷也不是完整 `AssignmentPlan.execution_signature()` 的序列化形式，
因此现有日志只能证明规范化后的发布业务载荷等价。后续正式审计优先持久化 D3 已提供的
`PlanningTickHistoryRecord`，需要完整签名证明时同时保留规范计划载荷。
