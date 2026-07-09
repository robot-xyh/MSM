# Integrated Simulation

This package runs an offline 5v5 point-mass integration of D1-D7. It is an
evaluation harness only: it writes synthetic logs, D4 arbitration records, D6
metrics, and plots. It does not include hardware drivers, real vehicle control,
automatic disposition, or authorization bypasses.

## Modules

- D1 fuses delayed radar, acoustic bearing, and EO pixel observations into
  covariance-carrying tracks.
- D2 converts D1 tracks into stable global IDs using GNN/Hungarian association.
- D3 builds versioned rolling assignments with hysteresis.
- D4 evaluates passive failover and active degradation using center health,
  secondary-node availability, D1/D2/D3 uncertainty, and D5 terminal evidence.
- D5 performs conservative terminal visual association without rewriting
  center-owned `global_track_id`. The current runner exercises single-camera
  multi-candidate terminal association, scoped secondary `ReconImageCue`
  behavior, and cross-view evidence contracts; full AirSim multi-camera
  calibration is handled by `research_modules/airsim_runtime/`.
- D6 consumes logs and produces metrics, CSV tables, Markdown reports, and
  charts.
- D7 simulates offline proportional navigation after assignment: radar-track
  midcourse PN followed by visual LOS terminal PN.

## Cross-View Status

The next D5 integration step is a `TerminalObservationBus` or
`TerminalCrossViewFusion` layer. It should accept observations such as
`INT-01/L2` and `INT-02/L1`, keep the local IDs namespaced by resource and
camera, project the same `GlobalTrack` into each camera at its measurement
timestamp, and then report whether both local observations support the same
`global_track_id`.

The intended case is:

```text
INT-01 sees L1,L2,L3 -> candidate G1,G2,G3
INT-02 sees L1,L2,L3 -> candidate G2,G3,G4
```

The fusion layer may produce evidence like `INT-01/L2 + INT-02/L1 -> G2`, but
it must not rewrite `global_track_id`; conflicts are reported as terminal
ambiguity or D4 arbitration inputs.

## Commands

```bash
python3 research_modules/integrated_simulation/run_episode.py --scenario nominal_5v5
python3 research_modules/integrated_simulation/run_batch.py
python3 research_modules/integrated_simulation/generate_global_process_gif.py
```

Outputs are written under `research_modules/integrated_simulation/outputs/`.

The GIF generator writes `global_process_2d.gif`, an explanatory 2D animation
showing multi-sensor observations, fused tracks, data association, central
assignment, radar PN midcourse guidance, secondary-node reassignment, and
visual PN terminal guidance.

## Reports

- `POINT_MASS_FULL_FLOW_TECHNICAL_REPORT.md` documents the current point-mass
  D1-D7 full-flow implementation, algorithm principles, generated figures, and
  result analysis for `outputs/check_current_flow/`.
