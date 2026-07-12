# AirSim Blocks Runtime

This package runs the first real AirSim Blocks gates. It starts Blocks with a
repository-local settings file, connects through the Python RPC API, samples
vehicle poses, actor targets, scene images, LiDAR metadata, AirSim built-in
detections, scene objects, and replays the captured frames into the existing
D1-D7 integration.

The default path is read-only. When `--execute-intercept` is passed, only
`episode_006_full_flow` enables SimpleFlight API control for the interceptor
vehicles. Intruders remain non-vehicle Unreal actors moved with
`simSetObjectPose`. Target recognition defaults to AirSim `simGetDetections`,
but `--detection-backend yolo` routes in-memory Scene images through D5
YOLOv8 + MOT using `research_modules/d5_terminal_association/best.pt` unless a
different `--yolo-weights` path is supplied. D7 terminal handoff uses the
SimpleFlight-compatible PNG guidance gate: detector boxes must pass bbox,
LOS-rate, visual latency, and maneuver-margin checks before the controller
switches from `radar_midcourse` to
`vision_terminal`.

## Run

```bash
python3 research_modules/airsim_runtime/run_blocks_smoke.py \
  --episode-id blocks_smoke_001 \
  --duration 2.0 \
  --dt 0.5
```

Run the main-managed staged sequence with one Blocks launch and reset between
episodes:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --sequence-id blocks_sequence_001 \
  --duration 2.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

Run multiple random seeds without restarting Blocks for every seed:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --batch-seeds 1,2,3,4,5 \
  --sequence-id blocks_cv_5v5_batch_001 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

When `--batch-seeds` contains more than one seed, main now starts Blocks once,
runs each seed as a separate sequence, resets between sequences/episodes, and
then stops Blocks at the end. The batch summary records
`batch_mode=single_blocks_reset_loop` and
`blocks_launched_once_for_batch=true`.

## N-Drone Parameter

Main now owns the run-size parameter. For AirSim actor/CV scenarios, pass
`--drone-count N`; main generates N resources, N moved actor targets, and a
matching AirSim settings file under the run output directory. D1-D7 consume the
resulting arrays and must not assume a fixed 2v2 or 5v5 size.

For unequal scale, use `--resource-count M --target-count N`. This enables the
centralized cooperative-demand fixture when `M != N`; `--drone-count` remains
the equal-count shorthand and cannot be combined with the two independent
count options. The default high-threat policy is `k=3`, `hybrid 2+1`:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --resource-count 5 \
  --target-count 2 \
  --high-threat-resource-count 3 \
  --cooperative-coordination-mode hybrid \
  --cooperative-primary-count 2 \
  --cooperative-wave-gap 2.0 \
  --sequence-id blocks_cv_m5_n2_cooperative_001 \
  --duration 6.0 \
  --dt 0.5
```

The online fixture assigns the high-threat prior by stable center-owned track
order and never consults AirSim truth IDs. D3 admits complete demand slots only;
D5/D7 keep one state per resource-target pair. If the center is unavailable,
`k>1` currently fails closed with `coalition_fallback_unsupported`; atomic
secondary/distributed coalition formation remains a separate P1 capability.

Examples:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --drone-count 3 \
  --secondary-count 1 \
  --sequence-id blocks_cv_n3_sequence_001 \
  --duration 4.0 \
  --dt 0.5
```

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-5v5 \
  --execute-intercept \
  --drone-count 4 \
  --sequence-id blocks_actor_n4_intercept_001 \
  --duration 8.0 \
  --dt 0.2 \
  --control-dt 0.1
```

For D5 geometric registration:

```bash
python3 research_modules/airsim_runtime/run_d5_geometric_registration.py \
  --drone-count 4 \
  --episode-id d5_cv_n4_geometric_001 \
  --duration 6.0 \
  --dt 0.5
```

Run the first 2v2 actor-target sequence. Intruders are spawned/moved actors,
not SimpleFlight vehicles. The default target-recognition backend is AirSim
`simGetDetections`; add `--detection-backend yolo` to use D5 YOLOv8 + MOT:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-2v2 \
  --sequence-id blocks_2v2_actor_sequence_001 \
  --duration 3.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

YOLOv8 + ByteTrack/BoT-SORT input can be enabled without saving PNG frames:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-2v2 \
  --execute-intercept \
  --detection-backend yolo \
  --yolo-weights research_modules/d5_terminal_association/best.pt \
  --yolo-tracker-backend bytetrack
```

By default, sampled camera frames are checked but not written as PNG files. Add
`--save-images` only when debugging camera views or detection boxes.

Run the ComputerVision 5v5 D1-D5 replay sequence. All interceptor and secondary
nodes are `ComputerVision` camera vehicles; targets remain spawned/moved actors.
This mode validates fusion, association, assignment, terminal visual
registration, and degradation arbitration without SimpleFlight dynamics:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5 \
  --sequence-id blocks_cv_5v5_sequence_001 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The CV 5v5 settings define `Interceptor_Cam_1..5` plus
`Secondary_Recon_1..2`. Main samples every camera with explicit `vehicle_name`,
records detector boxes, and feeds synthetic radar/acoustic/EO
observations into D1 using the same actor truth with latency and covariance.
LiDAR capture is disabled in this mode because the vehicles are camera-only CV
nodes.
During capture, main also updates CV camera poses with `simSetVehiclePose`.
`Interceptor_Cam_i` follows the currently assigned target at a configurable
standoff distance and the pose orientation is set to look at that target. The
default secondary reassignment swaps the second and third camera targets halfway
through the episode, so both initial assignment and reassignment views are
validated. `Secondary_Recon_1/2` keep overwatch positions and rotate toward
their coverage-cell target centroids.

Run the dedicated D4/D5 5v5 stress sequence:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --cv-5v5-d4d5-stress \
  --sequence-id blocks_cv_5v5_d4d5_stress_001 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

This profile uses `settings/blocks_cv_5v5_d4d5_stress_settings.json`. The five
targets start about 50 m in front of the interceptor cameras, target spacing is
20 m, interceptor camera spacing is 20 m, and the two secondary reconnaissance
cameras are about 50 m above the target layer.
Targets use the Blocks AirSim `Quadrotor1` actor asset by default and a 4 m
visual scale so the default AirSim detector reliably produces multi-target
terminal frames; this profile tests D5/D4 logic, not small-object detection
limits. Pass `--target-asset-name 1M_Cube_Chamfer` only for legacy geometry
baseline replay. Main runs three reset-separated cases: no degradation,
degrade to secondary node, and degrade to distributed mode. Outputs include
`d5_terminal_observations.jsonl`, `d5_cross_view_associations.json`,
`d4_decisions.jsonl`, per-case reports, and the aggregate
`D4_D5_5V5_STRESS_AIRSIM_REPORT.md`.

Run the P1 D4/D5 calibration matrix when the goal is to compare secondary
recon geometry rather than one fixed setting:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-calibration-sweep \
  --sequence-id p1_d4d5_calibration_sweep_001 \
  --batch-seeds 1,2,3 \
  --drone-count 5 \
  --p1-secondary-heights 50,100,200 \
  --p1-secondary-fovs 60,80,110 \
  --p1-secondary-counts 1,2,3 \
  --p1-secondary-standoffs 0,5,15 \
  --duration 6.0 \
  --dt 0.5 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The sweep uses `ComputerVision` D4/D5 stress episodes with mobile secondary
recon enabled. Different height/FOV/secondary-count combinations generate
different AirSim settings, so main launches Blocks once per geometry
combination and runs all requested seeds inside that combination with reset
separation. The top-level output contains `p1_calibration_sweep_summary.json`
and `P1_AIRSIM_CALIBRATION_SWEEP_REPORT.md`, including single-secondary
coverage, network union coverage, detect-to-registration gap, cross-view
association count, gimbal pointing, and bbox size metrics. Main also asks D6
to scan the persisted sequence/episode artifacts and write
`d6_airsim_calibration/airsim_calibration_records.csv`,
`d6_airsim_calibration/airsim_calibration_summary.csv`,
`d6_airsim_calibration/airsim_calibration_summary.json`, and
`d6_airsim_calibration/airsim_calibration_report.md` for the standard
multi-seed reporting path.

Run the first controlled 2v2 intercept. Main still launches Blocks once and
resets between episodes; the first five episodes stay read-only/replay, and the
last episode arms `Interceptor1/2`, takes off, and sends D7 PN velocity commands:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-2v2 \
  --execute-intercept \
  --sequence-id blocks_2v2_actor_intercept_001 \
  --duration 8.0 \
  --dt 0.2 \
  --control-dt 0.1 \
  --intercept-speed 6.0 \
  --intercept-altitude-z -5.0 \
  --intercept-radius 5.0 \
  --intercept-detection-timeout 5.0 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

Run the controlled 5v5 intercept. This uses five SimpleFlight interceptors
(`Interceptor1..5`) from
`settings/blocks_5v5_actor_tuned_settings.json` and five moved actor targets
(`MSM_TargetActor_1..5`). The target actor asset defaults to the Blocks AirSim
drone mesh `Quadrotor1`, which matches the YOLO UAV detector path better than
the old cube actor. The D7 midcourse law is radar PN; terminal visual PNG is
only entered after the per-pair D3/D4/D5 contract and camera/LOS/maneuver gates
pass:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --actor-5v5 \
  --execute-intercept \
  --sequence-id p1_5v5_intercept_20260703 \
  --duration 8.0 \
  --dt 0.2 \
  --control-dt 0.1 \
  --intercept-speed 6.0 \
  --intercept-altitude-z -5.0 \
  --intercept-radius 5.0 \
  --intercept-terminal-range 8.0 \
  --intercept-detection-timeout 5.0 \
  --intercept-yaw-mode look_at_target \
  --actor-target-distance 20.0 \
  --actor-target-speed-scale 0.25 \
  --target-scale-m 2.0 \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The 5v5 run writes `P1_5V5_INTERCEPT_AIRSIM_REPORT_20260703.md` in the
sequence output directory. Each pair owns an independent D7 visual filter; do
not share terminal PNG state across interceptors.

`--intercept-radius` is a NED three-dimensional Euclidean threshold and is
inclusive; the default `5.0m` produces `range_intercept`, while an assigned
collision remains `collision_intercept`. The detection timeout now applies to
initial terminal acquisition only. After a valid visual handoff, D7 handles a
brief loss with image-KF prediction and bounded command coast; expiry is logged
as `terminal_visual_lost_after_coast`. The example uses `-5m` NED altitude to
keep the intercept path above Blocks scene obstacles; read-only actor runs
still default to `-2m`.

Default sequence order:

```text
episode_001_d1_sensor -> reset
episode_002_d2_association -> reset
episode_003_d3_assignment -> reset
episode_004_d5_terminal -> reset
episode_005_d4_degradation -> reset
episode_006_full_flow
```

## Main Episode Bus

Every Blocks smoke episode now also runs the main-owned episode bus on the
captured `AirSimFrame[]`. This is additive to the older `integrated_replay`:
the bus consumes the same real AirSim frames and writes one D6-compatible
episode log that keeps the D1-D7 runtime state together:

```text
AirSimFrame
-> D1 SensorObservation / GlobalTrack
-> D2 associated tracks, id_switch_count, continuity
-> D3 AssignmentPlan, version, AssignmentGuidanceBinding
-> D5 TerminalAssociation and cross-view terminal observations
-> D4 active/passive degradation decision events
-> D7 PN/PNG guidance records and terminal contract gate state
-> D6 MetricsCollector JSONL
```

The output directory contains:

- `main_episode_bus/main_episode_bus.jsonl`: D6 records with
  `truth_summary`, `track`, `assignment`, `event`, `link`, and `terminal`.
- `main_episode_bus/main_episode_bus_ticks.jsonl`: per-frame D1-D7 debug
  snapshots, including D1 timestamps/covariance, D2 ID metrics, D3 plan
  version, D4 actions, D5 decision states, and D7 gate rejects.
- `main_episode_bus/main_episode_bus_metrics.json`: D6 episode metrics from
  the bus records.
- `main_episode_bus/main_episode_bus_summary.json`: final module summaries and
  record counts.

`airsim_blocks_summary.json` includes the same paths and `main_episode_bus`
metadata. Online D5 association in this bus uses geometric detection data only;
AirSim object IDs are carried only as offline scoring labels.

Use `--no-launch` when Blocks is already running with compatible settings.
By default the launcher adds `-windowed -ResX=640 -ResY=480 -NoVSync` and
NVIDIA PRIME offload environment variables to reduce first-run rendering risk.
The smoke client defaults to AirSim `VehicleClient`, matching the official
camera/LiDAR examples for read-only sensing. `--execute-intercept`
automatically switches the runtime client to AirSim `MultirotorClient`.

The bundled settings use `VehicleType: SimpleFlight`, `ViewMode: NoDisplay`,
`DefaultVehicleState: Inactive`, ground-level `Z: 0`, enabled collisions, and
disabled collision passthrough. This prevents multirotors from falling before
the smoke test has an RPC connection and keeps the main render path light.
Control episodes should explicitly request API control, arm, take off, and
command hover or motion at the start of each episode instead of starting airborne.
For D1-D5 ComputerVision replay, use
`settings/blocks_cv_5v5_settings.json`; those vehicles have no physics, gravity,
LiDAR, arming, or collision behavior.

Outputs are written under
`research_modules/airsim_runtime/outputs/<sequence-id>/<episode-id>/`,
including `airsim_blocks_summary.json`, raw frame JSONL, camera metadata, Blocks
stdout/stderr, `blocks_sensor_observations.jsonl` D1 replay inputs, integrated
replay metrics, main episode bus JSONL/ticks/metrics/summary, and for controlled episodes:
`intercept_summary.json`, `control_commands.csv`, and
`airsim_3d_intercept_trajectories.png`.
`control_commands.csv` includes D7 `guidance_law`, terminal handoff state,
camera/LOS/maneuver gate booleans, `terminal_switch_reject_reason`,
`terminal_contract_reject_reason`, D4/D5 state fields, and plan/version
metadata. Terminal contract rejects are logged as explicit D7 states such as
`hold`, `reacquire`, or `abort_revoke` where possible.
Camera PNG screenshots are omitted unless `--save-images` is used.
For CV 5v5, the handoff from visual capture to D5 is metadata-only:
`blocks_frames.jsonl` stores per-camera image status, camera pose, detection
bbox, local track id, actor/object id for offline truth evaluation, and
timestamps. D5 consumes the bbox metadata and never rewrites D2/D3
`global_track_id`.

## AirSim Docs And Source Findings

- `docs/settings.md` confirms `SimMode: Multirotor`, `ViewMode: NoDisplay`,
  NED vehicle `X/Y/Z`, per-vehicle `Sensors`, and `ApiServerPort`.
- AirSim source reads the RPC switch from `EnableRpc`; older docs also show
  `RpcEnabled`, so the bundled settings keep both keys for compatibility.
- `docs/simple_flight.md` states SimpleFlight vehicles start armed by default.
  The smoke settings therefore use `DefaultVehicleState: Inactive` and `Z: 0`
  so vehicles do not immediately fall before any control episode starts.
- `docs/multi_vehicle.md` and `PythonClient/multirotor/multi_agent_drone.py`
  show multi-drone settings and per-call `vehicle_name` usage.
- `PythonClient/airsim/client.py` documents that `simGetVehiclePose()` returns
  pose in each vehicle's starting-point frame. The runtime adapter therefore
  adds the settings `X/Y/Z` start offset back into truth/resource positions
  before emitting global NED records.
- `docs/object_detection.md` and `PythonClient/detection/detection.py` show
  `simSetDetectionFilterRadius`, `simAddDetectionFilterMeshName`, and
  `simGetDetections` for per-camera object detection. The runtime can instead
  use D5 YOLOv8 + MOT when `--detection-backend yolo` is selected.
- `PythonClient/environment/create_objects.py` shows `simSpawnObject`, and
  `PythonClient/computer_vision/objects.py` shows `simSetObjectPose` for Blocks
  actors such as `OrangeBall` and `PulsingCone`.
- `docs/lidar.md` and the LiDAR Python examples show that LiDAR is disabled
  unless configured under vehicle `Sensors`, and readback uses `getLidarData`.
- `docs/image_apis.md` and `PythonClient/computer_vision/cv_mode.py` show a
  `ComputerVision` mode that can isolate RPC/camera startup from multirotor
  physics. Use `settings/blocks_cv_rpc_settings.json` for that diagnostic.
- `SimHUD.cpp` calls `initializeSettings()`, `loadLevel()`, `createSimMode()`,
  `createMainWidget()`, `setupInputBindings()`, then `simmode_->startApiServer()`.
  If logs show vehicle creation and engine initialization but no listening RPC
  port, the next suspect is this late API-server startup path.

## Diagnostics

If RPC does not become ready, the launcher now writes:

- `blocks_stdout_stderr.log`: raw Blocks output.
- `blocks_diagnostics.json`: parsed settings path, command-line settings check,
  game mode, engine initialization, vehicle log hits, OpenXR/HMD counts, RPC
  start errors, and local TCP port status.

Useful launch variants while debugging the current packaged Blocks binary:

```bash
python3 research_modules/airsim_runtime/run_blocks_smoke.py \
  --episode-id blocks_minimal_nodisplay_001 \
  --duration 0 \
  --settings research_modules/airsim_runtime/settings/blocks_minimal_settings.json \
  --no-integrated-pipeline \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

```bash
python3 research_modules/airsim_runtime/run_blocks_smoke.py \
  --episode-id blocks_cv_rpc_001 \
  --duration 0 \
  --settings research_modules/airsim_runtime/settings/blocks_cv_rpc_settings.json \
  --camera-vehicle-name "" \
  --target-vehicles "" \
  --resource-vehicles "" \
  --no-integrated-pipeline \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```
