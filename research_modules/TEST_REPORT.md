# Integrated Test Report

## Scope

This report summarizes integration verification for the six Python research modules. Verification is limited to offline simulation and unit tests.

## Unit Test Results

| Module | Command | Result |
|---|---|---|
| D1 Sensor Fusion | `PYTHONPATH=research_modules/d1_sensor_fusion/src python3 -m pytest -q research_modules/d1_sensor_fusion/tests` | 7 passed |
| D2 Data Association | `PYTHONPATH=research_modules/d2_data_association python3 -m pytest -q research_modules/d2_data_association/tests` | 9 passed |
| D3 Assignment Planner | `PYTHONPATH=research_modules/d3_assignment_planner/src python3 -m pytest -q research_modules/d3_assignment_planner/tests` | 14 passed |
| D4 Distributed Fallback | `PYTHONPATH=research_modules/d4_distributed_fallback python3 -m pytest -q research_modules/d4_distributed_fallback/tests` | 14 passed |
| D5 Terminal Association | `PYTHONPATH=research_modules/d5_terminal_association/src python3 -m pytest -q research_modules/d5_terminal_association/tests` | 15 passed |
| D6 Evaluation Metrics | `PYTHONPATH=research_modules/d6_evaluation_metrics python3 -m pytest -q research_modules/d6_evaluation_metrics/tests` | 10 passed |
| Cross-module Contract | `python3 research_modules/run_all_tests.py` Integration suite | 3 passed |

Total: 72 tests passed.

## Smoke Simulation Results

| Module | Key Result |
|---|---|
| D1 | Latency compensation improved RMSE from 26.522 m to 9.496 m; continuity 0.991 |
| D2 | GNN/JPDA/MHT ran across crossing, formation, occlusion, missed detection, and false alarm scenarios; IDSW is reported for every run |
| D3 | Hysteresis reduced reassignment events from 33 to 12 with high-threat unassigned ratio 0.0 |
| D4 | 5-node degraded coordination converged; secondary reconnaissance nodes are preferred before fully distributed CBBA; takeover time 6.0 s; consensus rounds 5; completion rate 1.0 |
| D5 | Terminal association locked precision 1.0; secondary `ReconImageCue` is scoped to local resources; `global_track_id_mutations` 0 |
| D6 | Batch example generated CSV summaries, Markdown report, JSONL logs, and PNG plots |
| Integration | D1 canonical NED track, D2 detection kwargs, D3 authorization handoff, D5 locked state, and D6 terminal metrics were verified together |

## Report Language And Figures

All six module experiment reports are now written in Chinese and include
Markdown image links to generated curves or plots:

- D1: `tracks_xy.png`, `rmse_latency_ablation.png`
- D2: `association_idsw_rmse.png`
- D3: `cost_reassignment.png`, `weight_sensitivity.png`
- D4: `failover_packet_loss_curve.png`
- D5: `terminal_decision_timeline.png`
- D6: category metric plots and selected metric distributions under `outputs/example_batch/plots/`

All six modules also include a detailed Chinese algorithm and implementation
document at `docs/ALGORITHM_AND_IMPLEMENTATION.md`. The shared documentation
layout is defined in `DOCUMENTATION_STANDARD.md`; each module keeps `README.md`,
`PLAN.md`, a `docs/` index, source/tests, and its existing generated report or
plot directories.

## Known Warnings

Matplotlib emits an `Axes3D` import warning in this environment. The modules generate 2D plots only; the warning does not affect outputs.

## Boundary

The modules do not contain real fire-control parameters, damage effects, live flight-control loops, hardware drivers, automatic disposition logic, or authorization-bypass flows.
