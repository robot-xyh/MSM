# D1 Sensor Fusion Module

Offline research module for radar, acoustic, and EO heterogeneous observation fusion. The module estimates six-state NED `GlobalTrack` objects with covariance.

## Scope

This directory is limited to simulation and offline evaluation. It does not include real fire-control parameters, damage logic, hardware drivers, real vehicle control, automatic action, or bypass of human authorization.

## Runtime

The implementation uses NumPy/SciPy-compatible fallback code and does not require FilterPy or Stone Soup. Optional placeholders are available in `d1_sensor_fusion.compat`.

## Run Tests

From repository root:

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src pytest research_modules/d1_sensor_fusion/tests
```

## Run Full Simulation

```bash
PYTHONPATH=research_modules/d1_sensor_fusion/src \
python3 research_modules/d1_sensor_fusion/scripts/run_simulation.py \
  --targets 3 \
  --duration 60 \
  --dt 0.1 \
  --seed 7 \
  --output research_modules/d1_sensor_fusion/reports
```

The script writes:

- `reports/EXPERIMENT_REPORT.md`
- `reports/tracks_xy.png`
- `reports/rmse_latency_ablation.png`

## Main Interfaces

- `SensorObservation`: canonical sensor input with `measurement_timestamp` and `arrival_timestamp`.
- `FusionAdapter`: EKF fusion and fixed-lag replay. Required methods are `predict_track()`, `update_at_measurement_time()`, `compensate_latency()`, and `_bucket()`.
- `GlobalTrack`: output state `[px, py, pz, vx, vy, vz]`, covariance, timestamp, source support, identity likelihood, and quality level.
