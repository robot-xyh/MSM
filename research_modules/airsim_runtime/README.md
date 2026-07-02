# AirSim Blocks Runtime

This package runs the first real AirSim Blocks gate. It starts Blocks with a
repository-local settings file, connects through the Python RPC API, samples
vehicle poses, actor targets, scene images, LiDAR metadata, AirSim built-in
detections, scene objects, and replays the captured frames into the existing
D1-D7 integration.

It does not arm, take off, move, or command vehicles. The 2v2 actor scenario
moves only non-vehicle Unreal actors with `simSetObjectPose`.

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

Run the first 2v2 actor-target sequence. Intruders are spawned/moved actors,
not SimpleFlight vehicles, and target recognition uses AirSim `simGetDetections`:

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

Default sequence order:

```text
episode_001_d1_sensor -> reset
episode_002_d2_association -> reset
episode_003_d3_assignment -> reset
episode_004_d5_terminal -> reset
episode_005_d4_degradation -> reset
episode_006_full_flow
```

Use `--no-launch` when Blocks is already running with compatible settings.
By default the launcher adds `-windowed -ResX=640 -ResY=480 -NoVSync` and
NVIDIA PRIME offload environment variables to reduce first-run rendering risk.
The smoke client defaults to AirSim `VehicleClient`, matching the official
camera/LiDAR examples for read-only sensing. Use `--client-kind multirotor`
only when a later control episode intentionally needs multirotor-specific APIs.

The bundled settings use `VehicleType: SimpleFlight`, `ViewMode: NoDisplay`,
`DefaultVehicleState: Inactive`, ground-level `Z: 0`, enabled collisions, and
disabled collision passthrough. This prevents multirotors from falling before
the smoke test has an RPC connection and keeps the main render path light.
Control episodes should explicitly request API control, arm, take off, and
command hover or motion at the start of each episode instead of starting airborne.

Outputs are written under `research_modules/airsim_runtime/outputs/<episode-id>/`,
including `airsim_blocks_summary.json`, raw frame JSONL, sample images, Blocks
stdout/stderr, and integrated replay metrics.

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
  `simGetDetections` for per-camera object detection.
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
