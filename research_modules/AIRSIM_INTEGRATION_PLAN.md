# AirSim Integration Plan

## Current Status (2026-07-15)

The active integration path is the Python AirSim runtime under
`research_modules/airsim_runtime/`, not a ROS 2 deployment. Main owns one
Blocks launch, reset-separated episodes, settings generation, actor target
motion, SimpleFlight interceptor control, runtime-bus routing, log collection,
and D6 report generation. D1-D7 own their adapters and algorithms.

The latest real campaign completed the M5N2 portion only: baseline and
soft-prediction/trend-coast candidate each ran seeds 1-10, for 20 reset-separated
SimpleFlight cases. Main requested termination after those cases. One
`png_ttc_2v2_seed001` case completed before TERM took effect, but it is excluded
from this M5N2 evidence set and does not constitute a multi-seed result;
dropout completed zero cases. Both M5N2 profiles produced `6/30` active-primary successes,
`6/20` target successes, and `0/10` coalition completions. The second required
primary reached the 5 m criterion in `0/10` cases for both profiles, so the
candidate remains optional and disabled by default. All 20 actual-execution
artifacts are available and online truth identity/state use remains zero.

The same campaign provides the first real multi-seed stage timing distribution.
Across 3805 ticks, the main-bus inner layer measured mean/P95
`349.34/487.40 ms`, dominated by D1 fusion at about `320.00 ms` mean. The
control-tick outer layer measured `1069.45/1254.06 ms`, dominated by AirSim
frame sampling at about `432.29 ms`; its 100 ms budget violation rate was 100%.
The outer layer contains bus processing, so the two totals are not additive.
Each case's timing JSONL is valid, but the current D6 strict loader treats one
file as one monotonic episode; main therefore still needs a versioned
multi-episode timing manifest instead of concatenating reset frame indices.
See `subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md`.
All 20 second-primary runs ended with `collision_stop`, but the current
artifact does not persist the collision object, normal, or member/environment
separation at the stop. Collision provenance must be added before attributing
the cooperative failure to visual gating or changing D5 thresholds.

The formal post-control evidence path now uses
`d7-actual-execution-metrics-v2`. It is generated only after
`control_commands.csv`, `intercept_summary.json`, and finalized main-bus
metrics exist. Plan IDs and positive plan versions are required on every
persisted command row. Secondary or distributed rows that actually receive
control authority must also provide an owner; center and non-authorized
transition rows may publish owner provenance as unavailable. D6 merge v3 uses
only this validated envelope and never restores plan provenance from the
integrated replay. Deterministic regression is green (`D6 216`, AirSim runtime
`142`, terminal closure `7`, integrated point-mass `7`). Real AirSim seed-1
validation has now produced valid v2 artifacts for tuned 2v2 and M5N2. Both
runs have matching command/summary/actual physical counts, matching
command/history plan IDs, and zero online truth identity/state use. Direct runs
use `case_id > sequence_id > episode_id` so independent sequences remain
distinct in D6 aggregation.

The current P0 contract requires covariance on every online D1 observation and
complete secondary-takeover evidence in D4. Missing or invalid covariance is
rejected before fusion; legacy covariance imputation is offline-only. A D4
secondary cannot become `takeover_ready` without explicit current time,
heartbeat, cue freshness, gimbal state, communication summary, network
full-view evidence, and a lease satisfying `current_time < lease_expiry`.
The point-mass integration now emits explicit synthetic secondary video/data
link summaries instead of relying on missing communication as healthy.
All D4 takeover entry points now use the same strict readiness contract.
Heartbeat alone is insufficient: the episode communication adapter requires
the previous completed D4 decision with valid episode time, epoch/lease,
heartbeat, cue, communication, gimbal, coverage, network full-view, and
sustained-readiness evidence. Missing, stale, incomplete, or conflicting lease
evidence fails closed. A second public-helper audit found that legacy
`None` values for sustained readiness, expected/actual source, or plan/required
lease epoch could previously be treated as merely "not false". The public
handoff and takeover-metadata helpers now require every active-secondary field
to pass exactly, including same-plan maintenance; the adapter no longer derives
a missing plan epoch from the required epoch. Distributed interceptor/peer
commit remains outside this secondary-visual gate. Deterministic validation is
green (`D4 280`, AirSim
runtime `147`, integrated point-mass `7`). This closes the code-level P0 edge;
real RF delay/loss/reordering, clock drift, retransmission, and multi-seed
failover-time measurement remain P1.

The second P1 code batch now carries stable D5 camera/stream/backend identity,
committed primary membership, and duplicate-lock risk through the main episode
bus. D7 records distinguish raw gate, latch, effective contract/control, and
termination snapshots. P1 output rows carry terminal metric scope,
denominators, physical provenance, performance samples, D3 history, and D7
execution paths; D6 suite and per-case report bundles are generated after the
sweep. Seed-1 real AirSim evidence closes the P0 actual-artifact wiring gate;
truth-isolated multi-seed performance validation remains open.

Validated evidence now includes strict 4 m/2 m dense crossing (40 episodes), a
60-case D4 episode-time fault matrix, 40 M5N2 cooperative SimpleFlight episodes,
and an 18-case native MOT screening matrix. The best M5N2 profile completed
`5/10` coalitions and native MOT admitted no candidate, so these remain P1
performance gaps. The default path stays detect + GNN/Hungarian + versioned
Hungarian assignment + conservative D4/D5 gates + existing PN/visual PNG.
The latest direct smoke measured about `123.3 ms` loop latency for 2v2 and
`384.6 ms` for M5N2, with `231` total budget violations. These are improved
over the earlier roughly 1.3 s diagnostic but still exceed the 100 ms target,
so the real-time target remains an open P1. Main runtime now writes two
non-overlapping timing layers: `main-stage-timing-v1` inside the D1-D7 episode
bus and `control-tick-stage-timing-v1` around AirSim sampling, bus processing,
pair synchronization, and guidance/control RPC. Unexecuted stages are
`not_applicable`, errors retain partial timing, and total/residual/budget fields
are persisted to JSONL. This closes the code-level observability gap, not the
performance gap. The new M5N2 multi-seed batch has ranked the dominant stages
and demonstrated that the 100 ms budget is not met; optimization and a later
controlled rerun remain P1.
The actual envelope now supplies five independent formal layers: contract,
control, terminal-switch permission, mode switch, and physical interception.
`terminal_switch_allowed_count` is recomputed directly from the final command
CSV and is never inferred from `control_allowed`. The same source-hash-verified
CSV also supplies the formal target-state freshness/stale summary. Across the
two seed-1 cases, all 656 command rows are available, pooled mean/P95/max age is
about `0.0872/0.2/0.2 s`, stale count is zero, and every source is
`d2_estimated_global_track`. Multi-seed latency and freshness distributions
remain P1; the evidence schema and seed-1 registration are closed.

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
