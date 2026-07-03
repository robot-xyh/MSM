# D1 Sensor Fusion Module

Offline research module for radar, acoustic, EO, and optional synthetic lidar heterogeneous observation fusion. The module estimates six-state NED `GlobalTrack` objects with covariance.

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

## AirSim Dry-Run Fixture

The module includes a no-AirSim dependency dry-run adapter for integration tests:

```python
from d1_sensor_fusion import (
    make_minimal_airsim_dry_run_fixture,
    observations_from_airsim_dry_run_fixture,
)

fixture = make_minimal_airsim_dry_run_fixture(include_lidar=True)
observations = observations_from_airsim_dry_run_fixture(fixture)
```

The adapter emits `SensorObservation[]` with `measurement_timestamp`, `arrival_timestamp`, `frame_id`, and `covariance` filled for synthetic radar, acoustic, EO, and optional lidar observations.

## Main Interfaces

- `SensorObservation`: canonical sensor input with `measurement_timestamp`, `arrival_timestamp`, optional cross-node communication metadata, and covariance.
- `FusionAdapter`: EKF fusion and fixed-lag replay. Required methods are `predict_track()`, `update_at_measurement_time()`, `compensate_latency()`, and `_bucket()`.
- `GlobalTrack`: output state `[px, py, pz, vx, vy, vz]`, covariance, timestamp, source support, identity likelihood, and quality level.

## Cross-Node Metadata

`SensorObservation` accepts optional communication fields directly or through `metadata`: `source_node_id`, `target_node_id`, `relay_node_id`, `link_type`, `sent_timestamp`, `received_timestamp`, `payload_kind`, `stale_after_s`, and `source_support`. `FusionAdapter` preserves the latest observation communication metadata in `GlobalTrack.metadata` and publishes modality counts in `GlobalTrack.source_support`.

Video/image streams are represented only by derived observations such as bounding boxes, camera metadata, timestamps, and covariance. D1 does not require or store PNG frames.
