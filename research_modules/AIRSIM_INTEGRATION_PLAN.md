# AirSim Integration Plan

## Current Status (2026-07-13)

The active integration path is the Python AirSim runtime under
`research_modules/airsim_runtime/`, not a ROS 2 deployment. Main owns one
Blocks launch, reset-separated episodes, settings generation, actor target
motion, SimpleFlight interceptor control, runtime-bus routing, log collection,
and D6 report generation. D1-D7 own their adapters and algorithms.

Validated evidence now includes strict 4 m/2 m dense crossing (40 episodes), a
60-case D4 episode-time fault matrix, 40 M5N2 cooperative SimpleFlight episodes,
and an 18-case native MOT screening matrix. The best M5N2 profile completed
`5/10` coalitions and native MOT admitted no candidate, so these remain P1
performance gaps. The default path stays detect + GNN/Hungarian + versioned
Hungarian assignment + conservative D4/D5 gates + existing PN/visual PNG.

## Integration Goal

The current AirSim phase wraps seven research modules through typed Python
adapters and a shared episode state machine. ROS 2-compatible nodes remain a
later deployment option. The safety boundary remains simulated sensing and
SimpleFlight research control only, with no hardware drivers, damage model, or
automatic disposition workflow.

## Proposed Node Mapping

| Module | ROS 2 Role | Subscribes | Publishes |
|---|---|---|---|
| D1 Sensor Fusion | Fusion node | `/radar/tracks`, `/acoustic/bearings`, `/vision/detections` | `/tracks/fused` |
| D2 Data Association | Tracker node | `/tracks/fused` | `/tracks/associated` |
| D3 Assignment Planner | Central planner node | `/tracks/associated`, `/resources/state` | `/assignment/plan` |
| D4 Distributed Fallback | Failover node | `/c2/heartbeat`, `/assignment/plan`, `/resources/state` | `/degraded/plan` |
| D5 Terminal Association | Terminal association node | `/tracks/associated`, `/assignment/plan`, camera topics, identity topics | `/terminal/associations`, `/terminal/identity_claims` |
| D6 Evaluation Metrics | Offline analysis node | ROS bag / JSONL replay | reports, CSV, plots |
| D7 Proportional Guidance | Guidance consumer node | versioned assignment binding, D4 permission, D5 terminal evidence | PN/PNG command abstraction and guidance records |

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

Current completion state:

1. Offline replay and dry-run contracts: complete and retained as regression gates.
2. Real Blocks ComputerVision and SimpleFlight orchestration: implemented.
3. D1/D2 strict dense-crossing calibration: executed; candidate not promoted.
4. D4 episode-time failure injection: executed; real network validation remains open.
5. D3/D5/D7 M5N2 cooperative closure: executed; `5/10` best result remains below acceptance.
6. D5 ByteTrack/BoT-SORT screening: executed; no candidate admitted, detect remains default.
7. D6 seven-source unified evidence report: implemented and generated.

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
- Add ROS 2 message definitions and tf2/message_filters after the current Python schemas and timing contracts stabilize.
- Add Stone Soup benchmark adapters for D1/D2 offline comparison.
- Add OR-Tools min-cost-flow backend for D3 if capacity constraints become dominant.
- Add ROS bag export/import for D6 batch analysis.
- Validate real bandwidth, clock drift, queueing, reordering, retransmission, and hardware links for D4.
- Improve second-primary visual acquisition and 30/50 m detector recall before reconsidering native MOT admission.
