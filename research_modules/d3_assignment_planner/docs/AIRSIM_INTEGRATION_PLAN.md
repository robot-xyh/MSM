# AirSim Integration Plan For D3 Assignment Planner

## Boundary

This plan is limited to offline AirSim playback or software-in-the-loop evaluation that produces human-review candidate assignment plans. It does not include real flight control, hardware drivers, real fire-control parameters, damage logic, autonomous disposition, or authorization bypasses.

## Integration Goal

Connect AirSim-derived simulated observations to the D3 planner interface:

```python
AssignmentPlanner.plan(
    tracks,
    resources,
    timestamp,
    previous_plan,
)
```

The output remains an abstract `AssignmentPlan`. Its default authorization state is `human_authorization_state="required"`, while AirSim validation may set `PlannerConfig.human_authorization_state` to a record-only state such as `"recorded"` for contract testing. D3 does not interpret that field as autonomous disposition authority.

One `AssignmentPlanner` instance is scoped to one AirSim episode. The first planning tick may omit `previous_plan`; every later tick must pass the exact active plan and should pass its version as `expected_previous_version`. A missing or stale predecessor is rejected with `StalePlanError`, and the runtime must retain the active plan rather than treating the rejected call as a new version-1 episode. Create a new planner instance after an episode reset.

## Proposed Data Flow

```text
AirSim log or live simulation tick
  -> observation adapter
  -> abstract TargetTrack list
  -> abstract ResourceState list
  -> AssignmentPlanner
  -> candidate AssignmentPlan
  -> logger / dashboard / human review queue
```

No planner output is sent directly to vehicle control, hardware control, or autonomous action.

## Adapter Responsibilities

Target adapter:

- Assign stable `track_id` values from the simulation track source.
- Normalize covariance quality into `TargetTrack.covariance` in `[0, 1]`.
- Normalize scenario priority into `TargetTrack.threat_score` in `[0, 1]`.
- Convert timing or geometry quality into abstract `window_cost` in `[0, 1]`.
- Compute pair-level `fov_difficulty_by_resource` in `[0, 1]` from simulated visibility or observation geometry.
- Compute pair-level `conflict_risk_by_resource` in `[0, 1]` from abstract resource contention or route overlap proxies.
- Mark `assignable=False` only for tracks that should not enter candidate assignment research.

Resource adapter:

- Assign stable `resource_id` values.
- Map simulated availability into `status`: `available`, `degraded`, `busy`, or `unavailable`.
- Normalize health or readiness proxy into `health_score` in `[0, 1]`.
- Set `operator_hold=True` when a human or scenario script excludes a resource from candidate assignment.
- Provide `busy_until` only as abstract scheduling state.

## Offline Evaluation Modes

1. Log replay:
   - Read saved AirSim telemetry or perception logs.
   - Convert each timestamp into planner inputs.
   - Write `AssignmentPlan` outputs to JSONL/CSV for analysis.

2. Software-in-the-loop simulation:
   - Poll AirSim at a fixed rate such as 2 Hz.
   - Convert state to abstract planner inputs.
   - Display candidate plans and metrics.
   - Do not connect outputs to actuation.

3. Batch parameter sweep:
   - Replay the same AirSim scenario with different `delta`, `min_dwell`, and `CostWeights`.
   - Include `reassignment_switch_penalty` and verify that solver/evidence costs remain single-charged.
   - Compare reassignment count, total accepted-plan cost, unassigned high-priority ratio, and runtime.

## Message Schema Sketch

Input target record:

```json
{
  "track_id": "T01",
  "timestamp": 12.5,
  "threat_score": 0.82,
  "covariance": 0.34,
  "window_cost": 0.41,
  "assignable": true,
  "pair_terms": {
    "R01": {"fov": 0.22, "conflict": 0.10, "feasible": true}
  }
}
```

Input resource record:

```json
{
  "resource_id": "R01",
  "timestamp": 12.5,
  "status": "available",
  "health_score": 0.91,
  "busy_until": 0.0,
  "operator_hold": false
}
```

Output candidate plan record:

```json
{
  "plan_id": "d3-plan-example",
  "version": 42,
  "created_at": 12.5,
  "human_authorization_state": "recorded",
  "metadata": {
    "configured_human_authorization_state": "recorded",
    "effective_human_authorization_state": "recorded",
    "active_plan_owner": "center",
    "replan_reason": "request_center_replan",
    "supersedes_plan_id": "d3-plan-previous",
    "supersedes_plan_version": 41
  },
  "decision_state": "held_by_hysteresis",
  "assignments": [
    {"target_id": "T01", "resource_id": "R03", "cost": 1.73}
  ],
  "unassigned_target_ids": ["T04"],
  "total_cost": 14.2
}
```

## Validation Gates

- Unit tests must pass before AirSim adapter tests.
- Adapter tests should replay a short fixture and verify stable IDs, normalized ranges, and deterministic planner output.
- No output channel may be connected to vehicle control or hardware control.
- Every published candidate plan must preserve the configured `human_authorization_state`; the default remains `"required"`, while record-only AirSim gates may use `"recorded"`.
- Logs must include `decision_state`, version, total cost, and per-assignment cost breakdown.
- When main/D4 requests `request_center_replan`, the next D3 plan must increment version and main/runtime must log `replan_reason`, `supersedes_plan_id`, `supersedes_plan_version`, and `active_plan_owner="center"`.
- After every successful planning tick, main should call `plan_history_record_from_plan(plan, sequence_index=tick_sequence_index, timestamp=planning_timestamp_s, previous_plan=previous_plan, feedback_metadata=None if writeback is None else writeback.metadata).to_dict()` and persist one JSONL object. Ordering is lexicographic `[sequence_index, timestamp]`; plan version is not a tick-order substitute.

## Validation Status Through 2026-07-14

- The real 5v5 calibration completed 60 connected cases: seeds 1-10, secondary heights 50/200 m, and `no_degradation`, `degrade_to_secondary`, and `degrade_to_distributed` cases.
- The historical runtime path has not activated a secondary plan. All 20 requested secondary cases fell back conservatively to distributed operation; 15 of 1300 D4 decisions reached momentary `takeover_ready`, all stopped at `pending_secondary_plan`, and `secondary_plan_active=0`.
- D3 provides the strict activation contract. The current secondary and distributed commit positive cases passed, and missing ACK aborted fail-closed. Stale-center, lease/epoch, and recovery cases remain long-term main/D4 regression and calibration concerns, not open D3 P1 contract work.
- The deterministic 3v5, 5v3, target-arrival, resource-failure, demand-change, and incremental/full suite closes the D3 N/M interface contract. Real non-equal multi-seed replay remains parameter-tuning evidence rather than missing implementation.
- The current 2026-07-11 ComputerVision M-to-N validation used 5 resources, 2 targets, and 10 seeds. T001 achieved two-primary visual consensus with current-plan authorization in 8/10 seeds; seeds 7 and 27 remain regressions. Combined with incremental planning and role-aware primary preservation, the D3 P1 contract layer is closed.
- Real M5N2 SimpleFlight validation has now run. It used `2 primary + 1 standby reserve`, did not require simultaneous primary arrival, and completed 40 episodes: 10 baseline seeds plus 10 seeds for each of three candidates.
- Coalition completion was `0/10` for baseline, `5/10` for the best `20 m / 3 s / 40 deg` profile, and `2/10` and `1/10` for the other two profiles. The best profile did not meet the `8/10` acceptance gate, so cooperative physical closure remains open even though real AirSim execution is no longer pending.
- Plan version, stale-plan rejection, member-role contracts, and reserve standby safety remained in force. The reserve was not authorized as an active primary.
- D3 now classifies ordinary ambiguous/hold/reacquire and geometry/FOV/detection instability as pair-soft feedback. These events raise only the current edge cost and hold D7; they do not set resource-wide `operator_hold`. Friend overlap, verified friend, safety identity conflict, duplicate assignment/lock, explicit feasibility rejection, and genuinely unavailable resources remain fail-closed at their declared scope.
- The 2026-07-14 deterministic acceptance now totals `157 passed, 1 skipped`. The five newest tests add soft-feedback/round-trip stability, cumulative same-window budget, cross-window recovery, hard resource failure, missing plus membership hold, owner fail-closed, and history budget export. Earlier canonical-history and held-scope/lifecycle cases remain covered. The skip remains the optional OR-Tools installed-only case.
- D3 now publishes `d3_plan_history_record_v1` through `PlanningTickHistoryRecord` and `plan_history_record_from_plan(...)`. The whitelist payload contains one tick's plan/count/owner/lineage/cost state, ordered assignments and recoverable coalitions, hysteresis/membership records, feedback classifications/counts, and stale/rollback/replan audit reasons; online truth fields are excluded.
- P2 results remain isolated optional benchmarks and do not select or replace the default Hungarian/demand-slot path.

## Open P1 Calibration Work

- D3 canonical per-planning-tick schema/export is complete. Main still must call it and persist JSONL for each tick; no main/runtime file is changed by this D3 task.
- D6 can expand all 40 M5N2 cases, but the formal aggregate predates main persistence of canonical records. Membership/version churn is therefore still `unavailable` and must not be inferred or filled with zero; D6 consumption is outside this task.
- The former pair-hold-to-resource-hold promotion is a root-cause lead for churn, not proven causality for the 40-case outcomes. Causal attribution requires paired per-tick plan, feedback, classification, and hysteresis records.
- Calibrate D5 feedback weights and `delta`, `min_dwell`, and `reassignment_switch_penalty` from paired per-tick evidence.
- Run dynamic N/M multi-seed cases, including 3v5, 5v3, target arrival, resource loss, and demand changes.
- Do not add a simultaneous-arrival requirement to this P1 acceptance path.

## Future OR-Tools Path

The optional same-input comparator behind `MinCostFlowAssignmentSolver` is implemented and remains outside the default planner and requirements. Environments without OR-Tools report explicit unavailability and keep the core suite green. CP-SAT/MILP coalition references, resource capacities, group quotas, backup resources, multi-window networks, and predictive rolling remain isolated P2/P3 work; they must not replace the Hungarian/demand-slot default path without separate evidence.

## 2026-07-14 Seed 001 Integration Findings

The persisted M5N2 baseline seed 001 contains 349 D3 planning ticks and 45
published versions. Eight held ticks advanced identity because current-input
unassigned scope leaked into the held plan. D3 now preserves the previous
execution scope and exposes the candidate scope as audit-only metadata. The
acceptance criterion for the next main-owned replay is zero version advances
for `held_by_hysteresis`, `held_by_coalition_membership_hysteresis`, or
`held_by_transient_feedback_dwell` unless owner/lease/activation semantics are
explicitly changed by a coordinated takeover.

The integration owner must also address two non-D3 boundaries before claiming
closure:

1. `target_tracks_from_online_d2(...)` currently marks every state except
   lost/dropped assignable. It must carry lifecycle admission explicitly and
   submit only engageable or separately authorized tracks to D3. No truth ID or
   known target-count filter is allowed.
2. The intercept runtime must demote an already-active pair when its current D3
   binding changes from primary to reserve. D3 emits reserve as standby/hold;
   execution code must not retain an earlier primary active bit.

Run at least 10 same-geometry seeds after integration changes. Persist canonical
history and report plan churn, held-version advances, lifecycle-at-admission,
reserve unauthorized activation, high-threat unassigned count, and stale-plan
rejects. This D3 task ran deterministic module tests only; it did not relaunch
Blocks or replace the recorded episode.

## 2026-07-14 Latest 347-Record Churn Closure

The latest truth-isolated M5N2 baseline seed 001 contains 347 canonical D3
records and executable versions v1 through v35. It still showed approximately
one round-trip membership change per second. A representative record compared
candidate coalition cost `0.8868` with previous cost `2.8520`; the previous
side contained `2.2` of soft-feedback FOV search shaping. On the common base
execution objective the previous side is about `0.6520`, so the candidate does
not satisfy the configured 20 percent gain.

D3 now exports a common comparison-cost schema and a cumulative window-budget
schema. Main must preserve an intentional `window_id` across ticks that belong
to one budget window; a new `window_id` explicitly restores the budget. History
records include comparison/search costs, changes used, candidate changes,
remaining budget, and any hard bypass reason. Missing execution targets,
genuinely unavailable resources, and coordinated plan-level owner/activation
changes still publish a new identity immediately so old bindings become stale.

This D3 task ran deterministic tests only: `157 passed, 1 skipped`, with zero
failures required. Blocks was not relaunched. Main/D6 acceptance remains at
least 10 same-geometry seeds, zero unexplained periodic churn, no increase in
high-threat unassigned targets, zero online truth use, and no unauthorized
reserve execution. Physical coalition completion must still reach `8/10`; the
current best remains `5/10`.

## 2026-07-14 Actual-v2 Evidence Wiring

No D3 algorithm changed in this evidence-only run. Tuned 2v2 seed 1 uses
`d3-plan-c3cc6d28c365/1` across command, actual metrics, and 24 history
records. M5N2 seed 1 uses `d3-plan-cfdd088a10e1/1` across all three and has
214 history records. D6 reports two available history cases, zero unavailable
cases, and no validation reasons, closing the runtime identity chain at P0.

M5N2 feedback churn is 50 while plan-version, membership, and owner churn are
zero. Pair/target/coalition results are `2/3`, `2/2`, and `0/1`; the second
primary reached about 11.02 m. Target success is not coalition completion.
Second-primary 5 m closure and same-configuration multi-seed evidence remain P1.

## 2026-07-15 M5N2 20-Case Integration Status

Main runtime has now persisted canonical D3 history for the completed M5N2
batch: 10 baseline seeds and 10 `candidate_soft_prediction_trend_coast` seeds.
All 20 `d3_plan_history.json` files are readable and contain 3725/3725 valid
records. The previous integration item "main persists per-tick history" is
therefore closed for this batch.

The records show one current plan identity per case, zero plan-version,
coalition-roster, and owner transitions, and zero stale/rollback events. T001
keeps two active primaries and one standby reserve; T002 keeps one active
primary. Candidate membership evaluations are available and auditable, but
none changed the current roster. Runtime and D6 must calculate churn from
consecutive execution identities, not from the number of membership audit
objects.

Remaining integration work is outcome lineage rather than D3 plan persistence:

- record the collision object/category for every `collision_stop` so a terminal
  failure is not attributed to D3 without evidence;
- report `canonical target success` separately from T001 cooperative target,
  second-primary, and coalition diagnostics;
- identify the second primary from the current plan binding, never from a fixed
  vehicle name;
- retain missing tuned/dropout cases as unavailable. The extra
  `png_ttc_2v2_seed001` case is excluded from the M5N2 20-case aggregate.

The physical aggregate remains pair 12/60, canonical target 12/40, coalition
0/20, and second-primary 0/20. The candidate's paired non-degradation failure
does not demonstrate D3 planner degradation because D3 plan/member stability is
the same in both profiles.
