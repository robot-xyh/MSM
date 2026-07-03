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

- `ambiguous` / `hold` -> `hold`
- `reacquire` -> `replan`
- `mismatch` or duplicate terminal lock risk -> `secondary_arbitration`

Local resources must not rewrite `global_track_id`; D3 publishes versioned candidate plans for review. Normal operation uses Hungarian assignment, complex constraints should upgrade to OR-Tools Min Cost Flow, and D4 secondary-node arbitration is preferred before CBBA-style fallback.
