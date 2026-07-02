# C-UAS Research Modules Deliverable

This directory contains seven Python research modules plus an end-to-end integration runner for point-mass simulation, offline evaluation, and architecture validation. The modules are intentionally limited to sensing, tracking, assignment, degraded coordination, terminal association, metrics, and offline proportional-guidance studies. They do not implement real fire-control parameters, damage logic, live vehicle control, hardware drivers, automatic disposition, or authorization bypass.

## Module Index

| Module | Directory | Purpose |
|---|---|---|
| D1 | `d1_sensor_fusion/` | Radar/acoustic/EO fusion into covariance-aware `GlobalTrack` records |
| D2 | `d2_data_association/` | Multi-target association with GNN, JPDA, MHT-style baselines and ID switch metrics |
| D3 | `d3_assignment_planner/` | Centralized rolling resource-target assignment with hysteresis |
| D4 | `d4_distributed_fallback/` | Passive C2 failover, active degradation arbitration, secondary-node coordination, and simplified CBBA-style fallback |
| D5 | `d5_terminal_association/` | Terminal visual association, positive cooperative identity checks, and planned cross-view fusion contracts |
| D6 | `d6_evaluation_metrics/` | Offline metrics, batch reports, tables, and plots |
| D7 | `d7_proportional_guidance/` | Offline 2D proportional-navigation studies for radar midcourse and visual terminal phases |
| Main | `integrated_simulation/` | End-to-end 5v5 offline runner that wires D1-D7 through adapters and a shared log stream |

Each D1-D6 module contains its own `PLAN.md`, Python source, tests, simulation entry points, experiment report, and AirSim integration plan.
Detailed Chinese algorithm notes are standardized under each module's
`docs/ALGORITHM_AND_IMPLEMENTATION.md`; see `DOCUMENTATION_STANDARD.md` for the
shared documentation contract.

## Environment

Validated with:

```text
Python 3.12.3
numpy 2.5.0
scipy 1.17.1
matplotlib 3.10.9
pytest 7.4.4
opencv-python 4.13.0
```

`filterpy`, `stonesoup`, and `ortools` are treated as optional future integration dependencies. Runnable fallbacks use NumPy/SciPy and standard Python.

## Run All Tests

```bash
python3 research_modules/run_all_tests.py
```

The script executes each module's pytest suite with the required `PYTHONPATH`.

## Run Smoke Simulations

```bash
python3 research_modules/run_smoke_simulations.py
```

This executes representative simulations for all seven modules plus the integrated 5v5 batch runner and prints the key metrics.

## Run Integrated Simulation

```bash
python3 research_modules/integrated_simulation/run_episode.py --scenario nominal_5v5
python3 research_modules/integrated_simulation/run_batch.py
```

Standard integrated scenarios include `nominal_5v5`, `center_destroyed`,
`secondary_destroyed`, `active_terminal_mismatch`, and `friend_overlap_hold`.
Outputs are written under `research_modules/integrated_simulation/outputs/`.

## Generated Reports

Representative reports and plots are stored inside each module:

```text
d1_sensor_fusion/docs/ALGORITHM_AND_IMPLEMENTATION.md
d1_sensor_fusion/reports/
d2_data_association/docs/ALGORITHM_AND_IMPLEMENTATION.md
d2_data_association/docs/
d3_assignment_planner/docs/ALGORITHM_AND_IMPLEMENTATION.md
d3_assignment_planner/docs/
d3_assignment_planner/results/
d4_distributed_fallback/docs/ALGORITHM_AND_IMPLEMENTATION.md
d4_distributed_fallback/reports/
d5_terminal_association/docs/ALGORITHM_AND_IMPLEMENTATION.md
d5_terminal_association/docs/
d6_evaluation_metrics/docs/ALGORITHM_AND_IMPLEMENTATION.md
d6_evaluation_metrics/outputs/
d7_proportional_guidance/
integrated_simulation/outputs/
```

See `TEST_REPORT.md` for the latest integrated verification results.
