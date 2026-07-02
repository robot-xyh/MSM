# AirSim Dry-Run Interface

This package implements phase 1 of the AirSim plan: syntax and interface
testing without launching AirSim.

## Scope

- `FakeAirSimRuntimeClient` emits deterministic fake frames with NED truth,
  resource states, camera metadata, and image detections.
- `observations_from_airsim_frame()` converts fake frames into D1
  `SensorObservation` records with `measurement_timestamp`,
  `arrival_timestamp`, `frame_id`, and covariance.
- `AirSimDryRunOrchestrator` resets the fake runtime once, injects D1
  observations into the existing integrated runner, and executes the D1-D7
  contract path.
- No module imports `airsim`, starts Unreal, or calls vehicle-control APIs.

## Run

```bash
PYTHONPATH=research_modules:research_modules/d1_sensor_fusion/src:research_modules/d2_data_association:research_modules/d3_assignment_planner/src:research_modules/d4_distributed_fallback:research_modules/d5_terminal_association/src:research_modules/d6_evaluation_metrics:research_modules/d7_proportional_guidance \
python3 research_modules/airsim_dryrun/run_airsim_dry_run.py \
  --scenario nominal_5v5 \
  --episode-id episode_001 \
  --output research_modules/airsim_dryrun/outputs/episode_001
```

## Outputs

The orchestrator writes the normal integrated episode artifacts plus
`airsim_dry_run_summary.json`, which records the fake frame count, module
status, metrics, and `real_airsim_used=false`.
