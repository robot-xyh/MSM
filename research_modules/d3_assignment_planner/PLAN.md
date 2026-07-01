# D3 Centralized Assignment Planner Plan

## Boundary

This module is limited to research simulation, offline evaluation, and human-review candidate planning. It does not contain real fire-control parameters, damage logic, hardware drivers, autonomous disposition logic, or authorization bypasses. All outputs are abstract resource-to-target candidate assignments for analysis before any human authorization step.

## Engineering And Scientific Problem

The D3 planner studies rolling assignment for `M` abstract targets and `N` abstract resources. At each planning tick, target states, covariance quality, threat priority, resource health, field-of-view difficulty, and conflict risk may change. Re-solving every tick can reduce instantaneous cost but causes reassignment jitter. Freezing assignments avoids jitter but can preserve poor plans after state changes.

The engineering problem is to provide a deterministic Python implementation that:

- Computes a transparent assignment cost matrix from configurable weighted terms.
- Solves one-to-one assignment with SciPy Hungarian, with a small-scale fallback if SciPy is unavailable.
- Applies versioned hysteresis so a new plan is accepted only when it is meaningfully better and old assignments have dwelled long enough.
- Provides a reserved OR-Tools min-cost-flow interface without requiring OR-Tools at runtime.
- Produces reproducible offline metrics and plots for 5-10 targets, 5-10 resources, 100 s, 2 Hz.

The scientific question is how much hysteresis reduces reassignment jitter, and what cost or high-priority unassigned tradeoff it introduces under rolling uncertainty.

## Assignment Variables

Let:

- `i in {1..M}` index targets.
- `j in {1..N}` index resources.
- `x_ij in {0, 1}` be the assignment decision.

`x_ij = 1` means target `i` is assigned to resource `j` in the current candidate plan. `x_ij = 0` means no such assignment is present.

## Objective

The one-step candidate objective is:

```text
J = sum_i sum_j x_ij * C_ij
```

where `C_ij` is an abstract, configurable cost:

```text
C_ij =
    w_window      * intercept_window_cost
  + w_covariance  * track_covariance_penalty
  + w_threat      * threat_priority_cost
  + w_resource    * resource_state_penalty
  + w_fov         * field_of_view_difficulty
  + w_conflict    * conflict_risk
  + infeasible_penalty
```

`C_ij` is not a physical engagement or damage model. It is an offline planning score for comparing candidate assignments.

## Constraints

Base Hungarian constraints:

```text
sum_j x_ij <= 1      for every target i
sum_i x_ij <= 1      for every resource j
x_ij in {0, 1}
```

Operationally abstract constraints:

- Unavailable resources cannot be assigned.
- Infeasible target-resource pairs receive a large finite penalty and are excluded from published assignments.
- Plans carry monotonically increasing versions.
- Published plans require human authorization state `required`.
- Previous assignments can be retained under hysteresis when still feasible.

Future min-cost-flow constraints:

- Resource capacity greater than one.
- Target demand greater than one.
- Group-level budgets and exclusion edges.
- Multi-window or backup assignment arcs.

## Reassignment Condition

At each planning tick, the planner computes a candidate plan and compares it with the active plan. A changed plan is accepted only if:

```text
J_new < (1 - delta) * J_old
and
dwell_time > min_dwell
```

where:

- `delta` is the relative improvement threshold.
- `min_dwell` is the minimum time since the latest accepted changed assignment.
- `J_old` is recomputed on the current state for the retained old assignment set when feasible, so the comparison is fair under current costs.

If the condition fails and the previous plan remains feasible, the planner keeps the previous assignment set, advances version/window metadata, and marks the decision as `held_by_hysteresis`.

## Hungarian Vs Min-Cost-Flow Theory

Hungarian assignment:

- Solves square or rectangular one-to-one assignment efficiently.
- Fits the main D3 rolling case where each target uses at most one resource and each resource serves at most one target per tick.
- Has low implementation complexity through `scipy.optimize.linear_sum_assignment`.
- Produces deterministic, inspectable results with per-edge cost breakdowns.
- Does not naturally express capacities, demands, side constraints, backup assignments, or multi-stage flow.

Min-cost flow:

- Represents resources, targets, and optional time layers as graph nodes with arcs, capacities, and costs.
- Supports resource capacity, target demand, forbidden arcs, group quotas, and backup plans in one model.
- Requires integer cost scaling and more modeling decisions.
- Is a reserved extension here because OR-Tools is not installed in the target environment.

Recommendation:

- Use Hungarian for the implemented NumPy/SciPy baseline and fallback.
- Keep an interface boundary for min-cost-flow so future OR-Tools integration does not change planner-facing APIs.

## Simulation Plan

Scenario:

- 5-10 targets.
- 5-10 resources.
- 100 seconds.
- 2 Hz update rate.
- Deterministic random seed.
- Slowly varying target priority, covariance, resource health, field-of-view difficulty, conflict risk, and feasibility.

Comparisons:

- No hysteresis: `delta = 0.0`, `min_dwell = 0.0`.
- Hysteresis: `delta = 0.2`, configurable `min_dwell`.

Metrics:

- Reassignment count.
- Total accepted-plan cost over time.
- High-threat unassigned ratio.
- Planner runtime in milliseconds.
- Sensitivity to cost weights.

Artifacts:

- CSV time series.
- JSON summary.
- Cost and reassignment plots.
- Weight sensitivity plot.
- Markdown experiment report.

## Interfaces

Python package:

- `AssignmentPlanner.plan(tracks, resources, timestamp, previous_plan=None) -> AssignmentPlan`
- `CostModel.build_matrix(tracks, resources, previous_plan=None) -> CostMatrixResult`
- `HungarianAssignmentSolver.solve(cost_matrix) -> SolverResult`
- `FallbackAssignmentSolver.solve(cost_matrix) -> SolverResult`
- `MinCostFlowAssignmentSolver.solve(...)` reserved interface that raises a clear dependency message.

Data objects:

- `TargetTrack`
- `ResourceState`
- `Assignment`
- `AssignmentPlan`
- `CostWeights`
- `PlannerConfig`

## Deliverables

- `PLAN.md`: this implementation plan.
- Python source code under `src/d3_assignment_planner/`.
- Unit tests under `tests/`.
- Offline simulation script under `simulations/`.
- Experiment report under `docs/EXPERIMENT_REPORT.md`.
- AirSim integration plan under `docs/AIRSIM_INTEGRATION_PLAN.md`.
- Generated simulation outputs under `results/` after running the script.
