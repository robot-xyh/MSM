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

## Future OR-Tools Path

If AirSim scenarios require resource capacities, target demand, group quotas, or backup plans, implement `MinCostFlowAssignmentSolver` behind the existing solver interface. Keep OR-Tools optional and gate tests so environments without OR-Tools continue to pass.
