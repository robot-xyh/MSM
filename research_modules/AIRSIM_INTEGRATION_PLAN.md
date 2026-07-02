# AirSim Integration Plan

## Integration Goal

The AirSim phase should wrap the six research modules as ROS 2-compatible nodes or offline replay adapters while preserving their current safety boundary: point-mass or simulated sensing only, no real flight-control or hardware drivers, no damage model, and no automatic disposition workflow.

## Proposed Node Mapping

| Module | ROS 2 Role | Subscribes | Publishes |
|---|---|---|---|
| D1 Sensor Fusion | Fusion node | `/radar/tracks`, `/acoustic/bearings`, `/vision/detections` | `/tracks/fused` |
| D2 Data Association | Tracker node | `/tracks/fused` | `/tracks/associated` |
| D3 Assignment Planner | Central planner node | `/tracks/associated`, `/resources/state` | `/assignment/plan` |
| D4 Distributed Fallback | Failover node | `/c2/heartbeat`, `/assignment/plan`, `/resources/state` | `/degraded/plan` |
| D5 Terminal Association | Terminal association node | `/tracks/associated`, `/assignment/plan`, camera topics, identity topics | `/terminal/associations`, `/terminal/identity_claims` |
| D6 Evaluation Metrics | Offline analysis node | ROS bag / JSONL replay | reports, CSV, plots |

## Time And Frame Rules

Every message should carry:

```text
measurement_timestamp
arrival_timestamp
frame_id
transform_version
covariance
source_id
```

Fusion uses NED as the working state frame. WGS84 remains an external georeference only. ROS 2 `tf2` owns transformations among sensor, body, map, ENU/NED, and camera frames. Use `message_filters::ApproximateTime` for loose alignment and keep D1 OOSM replay logic for delayed measurements.

## AirSim Scenario Progression

1. Offline replay from generated JSONL/CSV logs.
2. AirSim camera-only synthetic detections with known truth boxes.
3. Simulated radar and acoustic topics generated from AirSim truth with controlled noise, delay, and dropout.
4. Multi-target crossing and formation scenarios.
5. Center-node failure injection and degraded-plan replay.
6. Batch logging through D6 with fixed random seeds and scenario metadata.

## Phase 1 Dry-Run Implementation

Implemented package: `research_modules/airsim_dryrun/`.

This phase does not start AirSim. `FakeAirSimRuntimeClient` creates deterministic
frames containing NED truth, resource states, camera metadata, visual detections,
and center/secondary node-health flags. `observations_from_airsim_frame()`
converts those frames into D1 `SensorObservation` records while preserving
`measurement_timestamp`, `arrival_timestamp`, `frame_id`, covariance, and
`real_airsim_used=false`.

`AirSimDryRunOrchestrator` owns the main runtime sequence:

```text
fake reset
-> fake frames
-> D1 observation provider
-> D2 association
-> D3 assignment
-> D5 terminal association
-> D4 degradation arbitration
-> D7 proportional-guidance records
-> D6 metrics and reports
```

Run the current dry-run gate from the repository root:

```bash
python3 research_modules/airsim_dryrun/run_airsim_dry_run.py \
  --scenario nominal_5v5 \
  --episode-id episode_001 \
  --output research_modules/airsim_dryrun/outputs/episode_001
```

The command writes the normal integrated episode artifacts plus
`airsim_dry_run_summary.json`. The summary must keep `real_airsim_used=false`.

## Validation Gates

Before any AirSim run is accepted:

```text
D1 publishes covariance-aware GlobalTrack records.
D2 reports id_switch_count.
D3 AssignmentPlan versions increase monotonically.
D4 degraded plans are marked fallback-only.
D5 never mutates global_track_id locally.
D6 can reproduce all metrics from logs.
```

## Deferred Work

- Replace synthetic radar/acoustic adapters with AirSim plugin outputs when available.
- Add ROS 2 message definitions after schema stabilization.
- Add Stone Soup benchmark adapters for D1/D2 offline comparison.
- Add OR-Tools min-cost-flow backend for D3 if capacity constraints become dominant.
- Add ROS bag export/import for D6 batch analysis.
