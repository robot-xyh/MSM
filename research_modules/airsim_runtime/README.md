# AirSim Blocks Runtime

## 2026-07-15 M5N2 20-Case Stop And Result

Main completed only the M5N2 portion of
`p1_terminal_timing_funnel_10seed_20260715`: baseline seeds 1-10 and
`candidate_soft_prediction_trend_coast` seeds 1-10. The batch was terminated
after 20/20 M5N2 cases. One `png_ttc_2v2_seed001` case completed during the
process transition before TERM took effect; it is excluded from this M5N2
result and is not a multi-seed result. Dropout completed zero cases, and no
missing outcome may be represented as a zero-valued result.

Both profiles produced `6/30` active-primary physical successes, `6/20`
target successes, and `0/10` coalition completions. The second required
primary reached the 5 m threshold in `0/10` cases for both profiles. Candidate
prediction/control activity increased but paired non-degradation failed, so
soft prediction and trend coast remain candidate-only and disabled by default.
All 20 canonical actual-execution artifacts are available; online truth
identity/state use is zero.

Pooled real timing contains 3805 records per layer. Main bus mean/P95/max is
`349.34/487.40/1305.99 ms`, dominated by D1 fusion. Control tick
mean/P95/max is `1069.45/1254.06/2072.51 ms`, dominated by AirSim frame
sampling; all 3805 outer ticks exceed 100 ms. The outer layer includes bus
processing and must not be added to the inner total. Raw per-case timing is
valid, while suite-level D6 timing remains unavailable until a versioned
multi-episode manifest supports reset frame indices without weakening the
strict single-episode schema.

All 20 second-primary executions ended with `collision_stop`. The stop record
does not yet persist the collision object, contact normal, or member/environment
separation, so this remains a P1 provenance gap rather than evidence that D5
alone caused the physical failure.

Evidence and figures are indexed by
`subagent_reviews/MAIN_M5N2_TIMING_AND_SECOND_PRIMARY_REPORT_20260715.md` and
`outputs/p1_terminal_timing_funnel_10seed_20260715_m5n2/`.

## 2026-07-15 Strict Secondary Readiness Integration

Main no longer treats a secondary heartbeat as sufficient takeover evidence.
The episode communication tick consumes only the previous completed D4
decision and requires the shared D4 readiness contract: explicit episode time,
valid epoch/lease, fresh heartbeat/cue/communication, valid gimbal and coverage
state, network full-view evidence, and sustained readiness. Missing, stale, or
incomplete evidence fails closed. Multiple records for the same secondary are
merged conservatively; conflicting lease epoch or expiry rejects that node
instead of allowing last-write-wins ownership.

The heartbeat-only negative case, complete-readiness positive case, and
conflicting-lease negative case pass. Current deterministic regressions are
`D4 278`, AirSim runtime `147`, and integrated point-mass `7`. No new AirSim
episode was launched for this change. Real network delay, loss, reordering,
clock drift, retransmission, and multi-seed failover timing remain P1.

## 2026-07-14 Actual-Execution Real AirSim Validation

The P0 evidence path has now been exercised in real Blocks for tuned 2v2 and
M5N2 seed 1. Both runs generated `d7_actual_execution_metrics.json` with
schema `d7-actual-execution-metrics-v2`; neither generated an unavailable
artifact. The command CSV, intercept summary, and actual envelope agree on
physical successes (`2/2` for 2v2 and `2/3` active pairs for M5N2), and command,
actual metadata, and canonical D3 history carry the same plan ID. Online truth
identity and state use are both zero.

Direct-run evidence identity follows `case_id > sequence_id > episode_id`.
This keeps independent full-flow sequences distinct even though each contains
an episode named `episode_006_full_flow`. The combined D6 report is under
`outputs/p0_actual_v2_validation_20260714/d6_acceptance/` and reports canonical
actual availability `2/2`. Its overall P1 acceptance remains false because the
two-case P0 smoke does not include the full paired candidate, dropout, and
multi-seed matrix.

M5N2 remains a P1 performance issue: both targets were intercepted by at least
one resource, but the second active primary for the high-threat target reached
only about `11.02 m`, so coalition completion was `0/1`. Loop latency was about
`123.3 ms` for 2v2 and `384.6 ms` for M5N2.

The actual envelope validates five independent layers: contract, control,
terminal-switch permission, mode switch, and physical interception. The
terminal-switch count is recomputed from the final command CSV and is not
inferred from control permission. D6 also recomputes target-state freshness
from the source-hash-verified command CSV. The two seed-1 cases provide 656
available samples, pooled mean/P95/max age of about `0.0872/0.2/0.2 s`, zero
stale samples, and only `d2_estimated_global_track` as the online state source.
The remaining P1 is multi-seed distribution and latency calibration, not
schema registration.

## 2026-07-14 Actual-Execution Plan Provenance

After SimpleFlight control completes, main now asks D6 to build
`d7_actual_execution_metrics.json` with schema
`d7-actual-execution-metrics-v2`. The artifact hashes the final command,
intercept-summary, and main-bus metric sources and preserves the plan IDs,
positive plan versions, owner availability, online truth safety counts,
effective visual-control transitions, physical results, and runtime samples.
Integrated replay data is diagnostic only and cannot supply missing execution
provenance.

Plan ID and version are mandatory on each command row. Owner provenance is
required for effectively authorized secondary or distributed execution; an
ordinary center row or a non-authorized transition may leave it unavailable.
The two controlled center/secondary regressions and the full runtime suite now
pass (`142 passed`). The real seed-1 gate described above is complete; the
remaining campaign is the same-configuration multi-seed P1 calibration.

## 2026-07-14 P1 Terminal Semantics Integration

Main now passes stable camera/stream/detector/tracker identity, executable
primary membership, and duplicate-lock risk into D5. D7 guidance events use
the module's canonical `d7_terminal_semantics_v2` record, and SimpleFlight
termination rows force live contract/control fields false while retaining
prior latch/authorization audit fields. The P1 terminal-closure sweep writes
metric envelopes with producer/scope/denominator/lifecycle, physical and
performance context, D3 history paths, D7 execution paths, and automatic D6
suite/per-case reports.

This closes runtime schema wiring only. It does not replace the required real
AirSim rerun for M5N2 second-primary acquisition, 30/50 m visual recall,
native-MOT admission, dropout behavior, physical interception, or loop-latency
calibration.

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

## 2026-07-14 Feedback Contract

The episode bus now separates terminal uncertainty from safety conflicts before
the next D3 planning cycle. Ordinary D5 `ambiguous`, `hold`, and `reacquire`
states are emitted as resource-target edge-soft feedback: they still block the
current pair's visual handoff, but they do not mark the whole interceptor
unavailable. Verified-friend overlap, spoof-suspected identity conflict,
duplicate lock, and explicit assignment conflicts remain fail-closed hard
feedback. Assignment evidence also derives `active` from D3's
`activation_state`, so an unactivated reserve is recorded as standby rather
than active.

This is a contract and regression fix, not new AirSim performance evidence.
The M5N2 `5/10` result remains the pre-fix baseline until main reruns the same
geometry and seeds.

## Online Truth Boundary

The main episode bus now keeps AirSim actor identity out of online D1/D2 DTOs,
delivers observations only after their arrival timestamp, and leaves truthless
D2/D6 metrics unavailable instead of reporting zero. Offline integrated replay
uses an explicit offline truth policy.

The controlled SimpleFlight executor now consumes the D2 estimated target
position, velocity, covariance, measurement timestamp, and arrival timestamp.
The default path, active center replan path, and active secondary takeover path
all use the same truth-isolated control evidence. Active-degradation fixtures
may override D3 plan/version, D4 permission, and D5 lock state, but they cannot
provide target kinematics or actor/object/mesh aliases. Missing or stale target
estimates fail closed.

AirSim actor truth remains available only to synthetic sensor generation,
trajectory plotting, offline global-track-to-truth pairing, and the post-run
three-dimensional 5 m scorer. `truth_state_online_use_count` is distinct from
`truth_identity_online_use_count`; strict integrated paths require both online
uses to be zero. The D7 PN/PNG core formulas were not changed. Runtime and
module regressions close the code-level P0, but historical physical results do
not become truth-isolated evidence retroactively. The same-seed real AirSim
rerun remains a P1 evidence task.

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
`k>1` execution requires the current D4 atomic coalition commit, ACK, epoch,
lease, and digest contract. Missing or conflicting evidence remains fail-closed.

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

Run the frozen P1 terminal-closure suite for comparable M5N2, real
`png_ttc`, and locked 1-5 frame detection dropout evidence:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-terminal-closure-sweep \
  --sequence-id p1_terminal_closure_001 \
  --batch-seeds 1,2,3,4,5,6,7,8,9,10 \
  --p1-dropout-frames 1,2,3,4,5 \
  --control-dt 0.1 \
  --no-lidar \
  --blocks-arg=-windowed \
  --blocks-arg=-ResX=640 \
  --blocks-arg=-ResY=480 \
  --blocks-arg=-NoVSync \
  --blocks-arg=-NoHMD \
  --blocks-arg=-NoSound
```

The M5N2 baseline/candidate cases use the same `z=-30 m`, 35-second
high-clearance geometry. Real `png_ttc` and the dropout matrix use tuned 2v2
camera settings at `z=-5 m` so SimpleFlight can settle at the requested global
NED altitude before horizontal control; dropout starts at 0.8 seconds,
after the stable-lock warm-up and before the usual 5 m intercept. The two
settings families use separate Blocks launches and reset-separated cases. The suite writes
`p1_terminal_closure_summary.json`, `p1_terminal_closure_rows.csv`, and a
Chinese Markdown execution report without saving PNG screenshots.

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
- `main_episode_bus/stage_timings.jsonl`: availability-aware per-frame main-bus
  stage timings (`main-stage-timing-v1`) for communication, D1, D2, D6 track
  recording, D3, coalition commit, D5, D4, D7, and link/cross-view recording.
  A stage that did not run is `not_applicable` with a null duration, not zero.
- `main_episode_bus/d3_plan_history.json`: ordered canonical D3 planning-tick
  records with assignments, primary/reserve activation, coalition
  version/epoch, owner/lease, hysteresis, feedback classification, and costs.
  Non-planning frames do not duplicate this history, and online truth fields
  are excluded.
- `main_episode_bus/main_episode_bus_metrics.json`: D6 episode metrics from
  the bus records.
- `main_episode_bus/main_episode_bus_summary.json`: final module summaries and
  record counts.

SimpleFlight control episodes additionally write `control_tick_timings.jsonl`
with `control-tick-stage-timing-v1`. It separates AirSim frame sampling,
main-bus processing, control-evidence/pair synchronization, and guidance plus
control RPC from the enclosing control tick. Both timing contracts use the
monotonic `perf_counter` clock, retain partial timing on errors, record the
configured budget and unattributed residual, and never feed timing values back
into D1-D7 decisions. Legacy outputs without these files remain unavailable
for stage-level analysis instead of being reconstructed from total latency.

`airsim_blocks_summary.json` includes the same paths and `main_episode_bus`
metadata. Online D5 association in this bus uses geometric detection data only;
AirSim object IDs are carried only as offline scoring labels.

Generate the availability-aware D6 churn report directly from one episode:

```bash
python3 research_modules/d6_evaluation_metrics/scripts/run_p1_system_evidence_report.py \
  --d3-plan-history /path/to/main_episode_bus/d3_plan_history.json \
  --output-dir /path/to/d6_d3_history_report
```

The report rejects duplicate or non-monotonic sequence indices, timestamp
regression, wrapper/record schema mismatch, and histories shorter than two
planning ticks. Rejected evidence remains `unavailable`; it is never converted
to zero churn.

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

## Radar-Direct Midcourse Policy

Normal ComputerVision episodes keep the current center-owned D3 plan unless a
real hard invalidation, center failure, or an explicit stress option is
present. Main publishes `terminal_evidence_applicable=false` while the assigned
resource remains outside `intercept_terminal_switch_range_m`. D4 then records
ordinary D1/D2/D3 soft risk without requesting secondary visual assistance;
stale or infeasible plans, observed ID switches/duplicate tracks, friend
conflict, duplicate terminal lock, and explicit resource/track mismatches keep
their existing fail-closed behavior. D7 remains on radar PN until the normal
D5 terminal contract is applicable and passes.

`--cv-reassignment-time` is reserved for a deliberate camera/association
stress injection. Once its timestamp is reached, the runtime overrides the
live D3/D2 camera pointing command with the configured reassignment geometry
and labels it `explicit_reassignment_stress`. Omitting the option preserves the
live center binding for the complete episode.

The 2026-07-13 real AirSim validation report and evidence are at:

- `subagent_reviews/MAIN_RADAR_DIRECT_ASSIGNMENT_AIRSIM_VALIDATION_REPORT_20260713.md`
- `research_modules/airsim_runtime/outputs/radar_direct_2v2_far_policy_v2_20260713/`
- `research_modules/airsim_runtime/outputs/radar_direct_5v5_yolo_bytetrack_20260713/`
- `research_modules/airsim_runtime/outputs/explicit_cv_reassignment_stress_5v5_v2_20260713/`

## P1 Cooperative Closure V2

`--p1-cooperative-closure-sweep` preserves the frozen terminal-closure v1
suite and creates a separate `p1-cooperative-closure-v2` evidence bundle. Main
first runs the D3 27-profile grid through D7's offline 2D point-mass model,
then promotes three profiles using the fixed safety/coalition/pair/arrival
ordering. Baseline and candidates run as M5N2 SimpleFlight episodes with
`2 primary + 1 reserve`, 35 s duration, NED `z=-30 m`, AirSim detect, PNG-VM,
and the 5 m physical success rule. Soft prediction and trend coast remain off.

Candidate initial sectors are applied after every reset with
`simSetVehiclePose`; reset alone does not reload a new settings file. The
stored frames therefore contain the actual candidate positions rather than
metadata-only geometry. Outputs include the point-mass screen, pair funnel,
pair/target/coalition summary, D4 six-case communication replay, and D6
Chinese report bundle.

For D1/D2 dense-crossing calibration, first collect real CV 5-target episodes,
then pass their full-flow directories to `run_p1_identity_pipeline.py` using
repeated `--episode SEED=PATH`. Main joins frame truth with anonymous sensor
observations, D1 writes truth-isolated governed replay and evaluator-only truth
sidecars, D2 runs the fixed 54-profile 10/20-seed matrix, and D6 produces the
availability-aware identity report. Fewer than 10/20 unique seeds remain
explicitly unavailable and do not promote a candidate.

The current cooperative terminal policy is `per_primary` with arrival-time
coordination disabled. Each active primary must independently pass its own
D3/D4/D5/camera/maneuver gates and is scored against the 5 m NED success
radius. The standby reserve cannot switch until a newer plan explicitly
activates it. D4 atomic ACK/epoch/lease checks remain mandatory after center
loss; a pending, partitioned, or ownerless episode communication state blocks
visual PNG.

Native MOT calibration is available as a separate, non-promoting sweep:

```bash
python3 research_modules/airsim_runtime/run_blocks_sequence.py \
  --p1-mot-calibration-sweep \
  --sequence-id p1_native_mot \
  --yolo-weights research_modules/d5_terminal_association/best.pt
```

Main runs 18 reset-separated single-camera screening cases for ByteTrack and
BoT-SORT at confidence 0.1/0.2/0.3 and range 20/30/50 m, then runs 10 seeds of
two-camera confirmation per selected backend. Cameras use 1920x1080, 90 deg
FOV. IoU fallback is disabled and cannot pass admission. AirSim truth boxes
and actor identity are fetched only after each online result and are consumed
only by D5/D6 offline scoring. Outputs include the execution index, Chinese
Markdown report, and D6 CSV/JSON/PNG report bundle.

For D2 identity calibration, pass nominal 4 m captures with `--episode` and
tight 2 m captures with `--tight-episode`:

```bash
python3 research_modules/airsim_runtime/run_p1_identity_pipeline.py \
  --episode 7=/path/to/nominal_seed007/episode_006_full_flow \
  --tight-episode 7=/path/to/tight_seed007/episode_006_full_flow \
  --output-dir /path/to/p1_identity
```

D1 first freezes both geometries. D2 then creates deterministic, truth-free
dropout, clutter, delayed/noisy, and combined governed replays. Tight geometry
is never synthesized: `tight_crossing` and `combined` require a declared
approximately 2 m AirSim capture. Screening and confirmation require 10 and 20
unique seeds per difficulty profile.

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
