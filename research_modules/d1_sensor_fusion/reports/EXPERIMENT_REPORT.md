# D1 Sensor Fusion Offline Experiment Report

## Scope

This report covers offline research simulation only. It does not include real fire-control parameters, damage logic, vehicle control, hardware drivers, automatic action, or bypass of human authorization.

## Scenario

- Targets: 3
- Baseline: this checked-in report is a historical 3-target baseline; integrated runs size D1 inputs from main `--drone-count N`.
- Duration: 8.0 s
- Base step: 0.50 s
- Seed: 7
- Sensors: delayed range-dependent radar, acoustic bearing with voiceprint hints, EO pixel-box projection.
- Filter: NumPy EKF fallback with fixed-lag measurement-time replay.

## Metrics

| Metric | Value |
|---|---:|
| Compensated RMSE (m) | 2.200 |
| Uncompensated RMSE (m) | 7.732 |
| Compensated track continuity | 0.909 |
| Uncompensated track continuity | 0.909 |
| Compensated grading accuracy | 1.000 |
| Uncompensated grading accuracy | 0.981 |
| Observation count | 153 |
| Mean radar latency (s) | 1.284 |

## Figures

- `tracks_xy.png`
- `rmse_latency_ablation.png`

## Interpretation

The compensated run updates each track at `measurement_timestamp` and replays to the current arrival time. The uncompensated run intentionally updates stale measurements at `arrival_timestamp`, which provides the latency-ablation baseline.
