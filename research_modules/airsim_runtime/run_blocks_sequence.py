#!/usr/bin/env python3
"""Run staged real Blocks episodes under one AirSim process."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for rel in (
    "research_modules",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from airsim_runtime.models import (
    BlocksEpisodeSpec,
    BlocksSmokeConfig,
    default_actor_target_specs,
    default_2v2_actor_target_specs,
    default_5v5_actor_target_specs,
    default_cv_5v5_actor_target_specs,
    default_cv_5v5_d4d5_stress_actor_target_specs,
    default_cv_5v5_camera_vehicle_names,
    default_cv_5v5_secondary_vehicle_names,
    default_cv_camera_vehicle_names,
    default_cv_secondary_vehicle_names,
    default_interceptor_vehicle_names,
    write_dynamic_computer_vision_settings,
    write_dynamic_multirotor_settings,
)
from airsim_runtime.p1_terminal_closure import (
    TerminalClosureCase,
    build_terminal_closure_cases,
    write_terminal_closure_bundle,
)
from airsim_runtime.p1_cooperative_closure import (
    CooperativeCandidate,
    CooperativeClosureCase,
    build_cooperative_closure_cases,
    build_pair_funnel_rows,
    run_pointmass_candidate_screen,
    write_cooperative_closure_bundle,
)
from airsim_runtime.p1_mot_calibration import (
    MotCalibrationCase,
    build_mot_confirmation_cases,
    build_mot_screening_cases,
    select_backend_thresholds,
    write_mot_execution_index,
)
from airsim_runtime.sequence import (
    D4D5_STRESS_EPISODES,
    DEFAULT_BLOCKS_EPISODES,
    run_blocks_batch_sequences,
    run_blocks_sequence,
)
from d6_evaluation_metrics import (
    AirSimCalibrationReportGenerator,
    CooperativeClosureInputs,
    CooperativeClosureReportGenerator,
    GuidanceLawComparisonReportGenerator,
    P1SystemEvidenceInputs,
    P1SystemEvidenceReportGenerator,
    P1AcceptanceInputs,
    P1AcceptanceReportGenerator,
    ScenarioDefinition,
    ScenarioLibrary,
    load_d7_intercept_outputs,
    load_main_episode_bus_metrics,
)
from d4_distributed_fallback import (
    CommunicationReplayConfig,
    run_p1_communication_fault_matrix,
)
from d3_assignment_planner import (
    CooperativeCandidateObservation,
    build_p1_cooperative_candidate_grid,
    rank_cooperative_candidates,
)

DEFAULT_SETTINGS = "research_modules/airsim_runtime/settings/blocks_smoke_settings.json"
ACTOR_2V2_SETTINGS = "research_modules/airsim_runtime/settings/blocks_2v2_actor_settings.json"
ACTOR_5V5_TUNED_SETTINGS = "research_modules/airsim_runtime/settings/blocks_5v5_actor_tuned_settings.json"
CV_5V5_SETTINGS = "research_modules/airsim_runtime/settings/blocks_cv_5v5_settings.json"
CV_5V5_D4D5_STRESS_SETTINGS = (
    "research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_settings.json"
)
ACTOR_2V2_TUNED_SETTINGS = (
    "research_modules/airsim_runtime/settings/blocks_2v2_actor_tuned_settings.json"
)
CV_5V5_D4D5_STRESS_200M_SETTINGS = (
    "research_modules/airsim_runtime/settings/blocks_cv_5v5_d4d5_stress_200m_settings.json"
)
P1_CALIBRATION_SUITE_VERSION = "p1-d4d5-calibration-suite-v1"
P1_CALIBRATION_THRESHOLD_VERSION = "p1-d4d5-thresholds-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequence-id", default="blocks_sequence_001")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--batch-seeds",
        default=None,
        help="Comma-separated seeds. Runs one sequence per seed using '<sequence-id>_seedNNN'.",
    )
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--dt", type=float, default=0.5)
    parser.add_argument(
        "--clock-speed",
        type=float,
        default=1.0,
        help=(
            "AirSim simulation clock multiplier written to generated settings. "
            "Wall-clock stage timing remains unscaled and is reported separately."
        ),
    )
    parser.add_argument("--output-root", default="research_modules/airsim_runtime/outputs")
    parser.add_argument("--blocks-script", default="Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh")
    parser.add_argument(
        "--settings",
        default=DEFAULT_SETTINGS,
    )
    parser.add_argument(
        "--drone-count",
        type=int,
        default=None,
        help=(
            "Backward-compatible equal-scale shorthand. Main generates N resources "
            "and N actor targets. Do not combine with --resource-count/--target-count."
        ),
    )
    parser.add_argument(
        "--resource-count",
        type=int,
        default=None,
        help="Number of interceptor/ComputerVision resource vehicles for an M-to-N scenario.",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=None,
        help="Number of moved actor targets for an M-to-N scenario.",
    )
    parser.add_argument(
        "--high-threat-resource-count",
        type=int,
        default=3,
        help="Required coalition size for targets above the cooperative threat threshold.",
    )
    parser.add_argument(
        "--enable-cooperative-demand",
        action="store_true",
        help="Enable high-threat cooperative demand even when resource and target counts match.",
    )
    parser.add_argument(
        "--cooperative-high-threat-target-count",
        type=int,
        default=1,
        help="Number of online center tracks assigned the simulated high-threat prior.",
    )
    parser.add_argument(
        "--cooperative-threat-threshold",
        type=float,
        default=0.9,
        help="Threat score at which a target receives the cooperative resource demand.",
    )
    parser.add_argument(
        "--cooperative-coordination-mode",
        choices=("independent", "simultaneous", "sequential", "hybrid"),
        default="hybrid",
        help="Coordination policy for high-threat coalitions.",
    )
    parser.add_argument(
        "--cooperative-primary-count",
        type=int,
        default=2,
        help="Wave-0 primary member count for hybrid cooperative interception.",
    )
    parser.add_argument(
        "--cooperative-wave-gap",
        type=float,
        default=2.0,
        help="Nominal delay in seconds between cooperative interception waves.",
    )
    parser.add_argument(
        "--cooperative-minimum-separation",
        type=float,
        default=0.5,
        help="Minimum temporal separation in seconds between coalition members.",
    )
    parser.add_argument(
        "--terminal-authorization-scope",
        choices=("coalition", "per_primary"),
        default="per_primary",
        help=(
            "Terminal authorization scope for cooperative targets. "
            "per_primary lets each active primary satisfy D5/D7 independently."
        ),
    )
    parser.add_argument(
        "--arrival-coordination-required",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Require cooperative arrival-window coordination. Use "
            "--no-arrival-coordination-required for independent-primary calibration."
        ),
    )
    parser.add_argument(
        "--cooperative-approach-sector-separation",
        type=float,
        default=0.0,
        help=(
            "Initial LOS sector separation in degrees for the first two active "
            "primaries in a cooperative SimpleFlight calibration case."
        ),
    )
    parser.add_argument(
        "--cooperative-pose-via-api",
        action="store_true",
        help=(
            "Apply cooperative initial-position offsets with simSetVehiclePose after "
            "each reset. Used by reset-separated candidate sweeps sharing one settings file."
        ),
    )
    parser.add_argument(
        "--secondary-count",
        type=int,
        default=2,
        help="Number of high recon secondary ComputerVision nodes; use 0 for primary-camera-only tests.",
    )
    parser.add_argument(
        "--actor-2v2",
        action="store_true",
        help="Run two SimpleFlight interceptor resources against two moving non-vehicle actor targets.",
    )
    parser.add_argument(
        "--actor-2v2-active-secondary-visual-png",
        action="store_true",
        help=(
            "Run the dedicated 2v2 active-degradation scenario: center plan, "
            "secondary reassignment, then D5/D7 visual PNG handoff."
        ),
    )
    parser.add_argument(
        "--actor-5v5",
        action="store_true",
        help="Run five SimpleFlight interceptor resources against five moving non-vehicle actor targets.",
    )
    parser.add_argument(
        "--actor-5v5-active-center-replan",
        action="store_true",
        help=(
            "Run controlled 5v5 intercept with D4 active-degradation evidence, "
            "but keep reassignment under the center node as center_plan_v2."
        ),
    )
    parser.add_argument(
        "--cv-5v5",
        action="store_true",
        help="Run five ComputerVision camera resources against five moving actor targets.",
    )
    parser.add_argument(
        "--cv-5v5-d4d5-stress",
        action="store_true",
        help="Run the dedicated 5v5 D5 terminal association and D4 degradation stress sequence.",
    )
    parser.add_argument(
        "--terminal-handoff-tuned",
        action="store_true",
        help="Use the 2v2 tuned terminal visual handoff settings and look-at-target yaw.",
    )
    parser.add_argument(
        "--cv-5v5-d4d5-stress-200m",
        action="store_true",
        help="Run the D4/D5 stress sequence with secondary recon cameras 200 m above targets.",
    )
    parser.add_argument(
        "--p1-calibration-sweep",
        action="store_true",
        help=(
            "Run the P1 D4/D5 AirSim calibration matrix. Each geometry/settings "
            "combination launches Blocks once; seeds inside the same combination "
            "use reset-separated episodes."
        ),
    )
    parser.add_argument(
        "--p1-mot-calibration-sweep",
        action="store_true",
        help=(
            "Run native ByteTrack/BoT-SORT screening and two-camera confirmation. "
            "IoU fallback is disabled and AirSim truth is used only for offline scoring."
        ),
    )
    parser.add_argument(
        "--p1-terminal-closure-sweep",
        action="store_true",
        help=(
            "Run the paired M5N2, png_ttc, and 1-5 frame locked-dropout "
            "P1 closure suite. M5N2 and 2v2 groups use separate Blocks launches "
            "because their vehicle settings differ."
        ),
    )
    parser.add_argument(
        "--p1-terminal-closure-m5n2-only",
        action="store_true",
        help=(
            "Limit --p1-terminal-closure-sweep to the paired M5N2 baseline and "
            "soft-prediction/trend-coast cases; skip png_ttc and dropout families."
        ),
    )
    parser.add_argument(
        "--p1-cooperative-closure-sweep",
        action="store_true",
        help=(
            "Run P1 cooperative-closure-v2: screen the D3 3x3x3 grid with the "
            "D7 point-mass model, then run baseline and the top candidates as "
            "reset-separated M5N2 SimpleFlight episodes."
        ),
    )
    parser.add_argument(
        "--p1-cooperative-candidate-limit",
        type=int,
        default=3,
        help="Number of point-mass candidates promoted to AirSim.",
    )
    parser.add_argument(
        "--p1-dropout-frames",
        default="1,2,3,4,5",
        help="Comma-separated locked-detection dropout frame counts for the terminal closure suite.",
    )
    parser.add_argument(
        "--p1-dropout-start",
        type=float,
        default=0.8,
        help="Locked-dropout injection start time for the terminal closure suite.",
    )
    parser.add_argument(
        "--p1-secondary-heights",
        default="50,100,200",
        help="Comma-separated secondary recon heights above targets for --p1-calibration-sweep.",
    )
    parser.add_argument(
        "--p1-secondary-fovs",
        default="60,80,110",
        help="Comma-separated secondary recon FOV values for --p1-calibration-sweep.",
    )
    parser.add_argument(
        "--p1-secondary-counts",
        default="1,2,3",
        help="Comma-separated secondary recon node counts for --p1-calibration-sweep.",
    )
    parser.add_argument(
        "--p1-secondary-standoffs",
        default="0,5,15",
        help="Comma-separated secondary recon standoff values for --p1-calibration-sweep.",
    )
    parser.add_argument(
        "--secondary-height-above-targets",
        type=float,
        default=None,
        help=(
            "Explicit secondary recon height above targets in meters. Overrides "
            "--cv-5v5-d4d5-stress-200m when provided."
        ),
    )
    parser.add_argument(
        "--mobile-secondary-recon",
        action="store_true",
        help=(
            "Use mobile high-altitude secondary recon UAVs in CV D4/D5 stress mode. "
            "Main moves them by simSetVehiclePose and points their gimbals from radar/GlobalTrack cues."
        ),
    )
    parser.add_argument(
        "--secondary-fov",
        type=float,
        default=None,
        help="Override secondary recon camera FOV in degrees.",
    )
    parser.add_argument(
        "--secondary-width",
        type=int,
        default=None,
        help="Override secondary recon Scene/Depth image width.",
    )
    parser.add_argument(
        "--secondary-height",
        type=int,
        default=None,
        help="Override secondary recon Scene/Depth image height.",
    )
    parser.add_argument(
        "--camera-width",
        type=int,
        default=None,
        help="Override primary ComputerVision camera width.",
    )
    parser.add_argument(
        "--camera-height",
        type=int,
        default=None,
        help="Override primary ComputerVision camera height.",
    )
    parser.add_argument(
        "--camera-fov",
        type=float,
        default=None,
        help="Override primary ComputerVision camera horizontal FOV in degrees.",
    )
    parser.add_argument(
        "--secondary-recon-standoff",
        type=float,
        default=0.0,
        help=(
            "Horizontal NED X standoff from the radar-cued target/sub-cluster centroid for "
            "mobile secondary recon nodes. 0 places the node over the cue."
        ),
    )
    parser.add_argument("--cv-camera-follow-distance", type=float, default=14.0)
    parser.add_argument(
        "--cv-reassignment-time",
        type=float,
        default=None,
        help=(
            "Explicit ComputerVision forced-reassignment time for stress tests. "
            "Normal episodes keep the current D3 assignment when omitted."
        ),
    )
    parser.add_argument("--connection-timeout", type=float, default=90.0)
    parser.add_argument("--client-timeout", type=float, default=2.0)
    parser.add_argument(
        "--execute-intercept",
        action="store_true",
        help="Execute SimpleFlight PN control in episode_006_full_flow.",
    )
    parser.add_argument("--control-dt", type=float, default=0.1)
    parser.add_argument("--intercept-speed", type=float, default=6.0)
    parser.add_argument("--intercept-altitude-z", type=float, default=-2.0)
    parser.add_argument(
        "--intercept-altitude-settle-timeout",
        type=float,
        default=45.0,
        help="Maximum seconds allowed for all interceptors to reach the commanded global NED altitude.",
    )
    parser.add_argument(
        "--intercept-altitude-tolerance",
        type=float,
        default=1.0,
        help="Maximum per-vehicle global NED altitude error before horizontal control starts.",
    )
    parser.add_argument(
        "--intercept-altitude-settle-samples",
        type=int,
        default=3,
        help="Required consecutive in-tolerance altitude samples before horizontal control starts.",
    )
    parser.add_argument(
        "--intercept-radius",
        type=float,
        default=5.0,
        help="3D NED separation at or below which a pair is a range intercept.",
    )
    parser.add_argument("--intercept-max-duration", type=float, default=8.0)
    parser.add_argument("--intercept-terminal-range", type=float, default=8.0)
    parser.add_argument("--intercept-detection-timeout", type=float, default=1.0)
    parser.add_argument(
        "--intercept-abort-on-terminal-acquisition-timeout",
        action="store_true",
        help=(
            "Abort when terminal visual acquisition times out. By default a current "
            "D2 estimate keeps radar PN active while D5 continues reacquisition."
        ),
    )
    parser.add_argument(
        "--intercept-max-turn-rate",
        type=float,
        default=0.9,
        help="D7 terminal PNG turn-rate capacity in rad/s; PNG formulas are unchanged.",
    )
    parser.add_argument(
        "--intercept-max-lateral-accel",
        type=float,
        default=20.0,
        help="D7 terminal PNG lateral-acceleration capacity in m/s^2.",
    )
    parser.add_argument(
        "--intercept-min-maneuver-margin",
        type=float,
        default=0.15,
        help="Minimum normalized D7 maneuver margin required for visual handoff.",
    )
    parser.add_argument(
        "--intercept-detection-dropout-start",
        type=float,
        default=None,
        help="Fault injection: first timestamp at which online visual detections are removed.",
    )
    parser.add_argument(
        "--intercept-detection-dropout-end",
        type=float,
        default=None,
        help="Fault injection: timestamp at which online visual detections resume.",
    )
    parser.add_argument(
        "--terminal-soft-prediction",
        action="store_true",
        help=(
            "Enable the candidate D7 innovation-reject prediction profile. "
            "Identity, plan-version, D4/D5, friend, and duplicate-lock gates remain mandatory."
        ),
    )
    parser.add_argument(
        "--terminal-trend-coast",
        action="store_true",
        help=(
            "Enable the candidate delivery-style horizontal LOS trend coast. "
            "The baseline profile remains the default."
        ),
    )
    parser.add_argument(
        "--guidance-law",
        choices=("pure_pursuit", "radar_pn", "png_vm", "png_ttc"),
        default="png_vm",
        help=(
            "Select the controlled-intercept guidance path. PNG modes use radar PN "
            "until the D3/D4/D5 terminal contract permits visual handoff."
        ),
    )
    parser.add_argument(
        "--guidance-law-sweep",
        action="store_true",
        help=(
            "Run pure_pursuit, radar_pn, png_vm, and png_ttc for the same seed/geometry "
            "under one reset-separated Blocks process."
        ),
    )
    parser.add_argument("--active-degradation-time", type=float, default=1.5)
    parser.add_argument("--secondary-plan-time", type=float, default=2.0)
    parser.add_argument("--center-replan-time", type=float, default=2.0)
    parser.add_argument(
        "--c2-health-mode",
        choices=("normal", "secondary_takeover", "fully_distributed"),
        default="normal",
        help=(
            "Inject C2 health state into captured episode frames without changing "
            "AirSim sensor or geometry data."
        ),
    )
    parser.add_argument(
        "--center-failure-time",
        type=float,
        default=None,
        help="Episode time at which the center becomes unavailable.",
    )
    parser.add_argument(
        "--secondary-failure-time",
        type=float,
        default=None,
        help="Episode time at which secondary nodes become unavailable in fully_distributed mode.",
    )
    parser.add_argument(
        "--coalition-commit-fault",
        choices=(
            "none",
            "missing_ack",
            "stale_epoch",
            "expired_lease",
            "partition",
            "digest_conflict",
            "member_cannot_execute",
        ),
        default="none",
        help="Inject a D4 distributed coalition commit fault for fail-closed validation.",
    )
    parser.add_argument(
        "--intercept-yaw-mode",
        choices=("velocity", "look_at_target"),
        default=None,
        help="Velocity yaw is the legacy mode; look_at_target keeps the camera pointed at the assigned target.",
    )
    parser.add_argument("--target-asset-name", default="Quadrotor1")
    parser.add_argument("--target-scale-m", type=float, default=None)
    parser.add_argument(
        "--actor-target-distance",
        type=float,
        default=None,
        help="Initial NED X distance for actor targets in controlled 5v5 mode.",
    )
    parser.add_argument(
        "--actor-target-spacing",
        type=float,
        default=None,
        help="Initial lateral target spacing for actor targets in controlled 5v5 mode.",
    )
    parser.add_argument(
        "--actor-target-x-spacing",
        type=float,
        default=None,
        help=(
            "Optional longitudinal spacing between generated actor targets. "
            "Set to 0 for a strict lateral 4 m/2 m dense-crossing capture."
        ),
    )
    parser.add_argument(
        "--actor-target-speed-scale",
        type=float,
        default=1.0,
        help="Velocity multiplier for actor targets in controlled 5v5 mode.",
    )
    parser.add_argument("--target-detection-filter", default="MSM_TargetActor_*")
    parser.add_argument(
        "--primary-detection-radius-m",
        type=float,
        default=None,
        help="AirSim simGetDetections radius for interceptor cameras in metres.",
    )
    parser.add_argument(
        "--secondary-detection-radius-m",
        type=float,
        default=None,
        help="AirSim simGetDetections radius for high-recon cameras in metres.",
    )
    parser.add_argument(
        "--detection-warmup-frames",
        type=int,
        default=1,
        help="Discard this many rendered detection frames after each reset/setup.",
    )
    parser.add_argument(
        "--detection-backend",
        choices=("airsim", "yolo"),
        default="airsim",
        help="Use AirSim simGetDetections metadata or D5 YOLOv8+MOT image detection.",
    )
    parser.add_argument(
        "--yolo-weights",
        default="research_modules/d5_terminal_association/best.pt",
        help="YOLOv8 weights path used when --detection-backend yolo.",
    )
    parser.add_argument(
        "--yolo-tracker-backend",
        choices=("bytetrack", "botsort", "iou_fallback"),
        default="bytetrack",
        help="D5 MOT backend requested for YOLO detections.",
    )
    parser.add_argument("--yolo-confidence", type=float, default=0.25)
    parser.add_argument("--yolo-device", default="auto")
    parser.add_argument("--yolo-cpu-budget-ms", type=float, default=None)
    parser.add_argument("--yolo-gpu-budget-ms", type=float, default=None)
    parser.add_argument(
        "--yolo-primary-imgsz",
        type=int,
        default=None,
        help="Optional Ultralytics inference imgsz for interceptor-camera streams.",
    )
    parser.add_argument(
        "--yolo-secondary-imgsz",
        type=int,
        default=None,
        help="Optional Ultralytics inference imgsz for high-recon streams.",
    )
    parser.add_argument(
        "--yolo-offline-truth-eval",
        action="store_true",
        help=(
            "Use AirSim detection boxes only as offline detector scoring labels. "
            "They are never exposed to the online D5 tracker or global binding."
        ),
    )
    parser.add_argument("--no-yolo-native-tracker", action="store_true")
    parser.add_argument("--no-yolo-iou-fallback", action="store_true")
    parser.add_argument("--save-images", action="store_true", help="Persist sampled Scene PNG frames.")
    parser.add_argument(
        "--no-lidar",
        action="store_true",
        help="Skip LiDAR RPC capture for control-focused AirSim calibration runs.",
    )
    parser.add_argument(
        "--full-flow-only",
        action="store_true",
        help="Run only episode_006_full_flow; useful for reset-separated physical calibration batches.",
    )
    parser.add_argument(
        "--blocks-arg",
        action="append",
        default=None,
        help="Extra argument passed to Blocks.sh. Can be repeated.",
    )
    parser.add_argument("--no-nvidia-offload", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.p1_mot_calibration_sweep:
        return _run_p1_mot_calibration_sweep(args)
    if args.p1_cooperative_closure_sweep:
        return _run_p1_cooperative_closure_sweep(args)
    if args.p1_terminal_closure_sweep:
        return _run_p1_terminal_closure_sweep(args)
    if args.p1_calibration_sweep:
        return _run_p1_calibration_sweep(args)
    if args.guidance_law_sweep:
        return _run_guidance_law_sweep(args)
    if args.actor_2v2_active_secondary_visual_png:
        args.actor_2v2 = True
        args.execute_intercept = True
        args.terminal_handoff_tuned = True
        if args.intercept_terminal_range == 8.0:
            args.intercept_terminal_range = 30.0
    if args.actor_5v5_active_center_replan:
        args.actor_5v5 = True
        args.execute_intercept = True
        if args.intercept_terminal_range == 8.0:
            args.intercept_terminal_range = 30.0
        if args.intercept_yaw_mode is None:
            args.intercept_yaw_mode = "look_at_target"
    if args.terminal_handoff_tuned:
        args.actor_2v2 = True
        args.execute_intercept = True
    if args.cv_5v5_d4d5_stress_200m:
        args.cv_5v5_d4d5_stress = True
    selected_modes = [args.actor_2v2, args.actor_5v5, args.cv_5v5, args.cv_5v5_d4d5_stress]
    if sum(1 for selected in selected_modes if selected) > 1:
        raise SystemExit(
            "--actor-2v2, --actor-5v5, --cv-5v5, and --cv-5v5-d4d5-stress are mutually exclusive"
        )
    if (args.cv_5v5 or args.cv_5v5_d4d5_stress) and args.execute_intercept:
        raise SystemExit("ComputerVision 5v5 modes are read-only and cannot be combined with --execute-intercept")
    seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    if len(seeds) == 1:
        results = [_run_one_sequence(args, seed=seeds[0], sequence_id=args.sequence_id)]
    else:
        runs = tuple(
            _build_sequence_run(
                args,
                seed=seed,
                sequence_id=f"{args.sequence_id}_seed{seed:03d}",
            )
            for seed in seeds
        )
        results = list(run_blocks_batch_sequences(runs, batch_id=args.sequence_id))
    for result in results:
        _print_sequence_result(result)
    if args.actor_5v5 and args.execute_intercept:
        _write_5v5_intercept_report(args, results)
    if args.actor_2v2_active_secondary_visual_png:
        _write_2v2_active_secondary_report(args, results)
    if len(results) > 1:
        _write_batch_summary(args, seeds, results)
    return 0


def _run_one_sequence(args: argparse.Namespace, *, seed: int, sequence_id: str):
    base_config, selected_sequence_id, episode_specs = _build_sequence_run(
        args,
        seed=seed,
        sequence_id=sequence_id,
    )
    return run_blocks_sequence(
        base_config,
        sequence_id=selected_sequence_id,
        episode_specs=episode_specs,
    )


def _run_guidance_law_sweep(args: argparse.Namespace) -> int:
    if args.cv_5v5 or args.cv_5v5_d4d5_stress or args.p1_calibration_sweep:
        raise SystemExit("--guidance-law-sweep requires an actor SimpleFlight scenario")
    if not args.actor_2v2 and not args.actor_5v5:
        args.actor_2v2 = True
    args.execute_intercept = True
    if args.actor_2v2:
        args.terminal_handoff_tuned = True
    if args.intercept_terminal_range == 8.0:
        args.intercept_terminal_range = 30.0
    if args.intercept_yaw_mode is None:
        args.intercept_yaw_mode = "look_at_target"

    seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    laws = ("pure_pursuit", "radar_pn", "png_vm", "png_ttc")
    runs = []
    run_index: list[tuple[str, int]] = []
    for law in laws:
        for seed in seeds:
            law_args = copy.deepcopy(args)
            law_args.guidance_law_sweep = False
            law_args.guidance_law = law
            sequence_id = f"{args.sequence_id}_{law}_seed{seed:03d}"
            config, selected_sequence_id, episode_specs = _build_sequence_run(
                law_args,
                seed=seed,
                sequence_id=sequence_id,
            )
            config = replace(
                config,
                metadata={
                    **config.metadata,
                    "guidance_comparison_group": args.sequence_id,
                    "guidance_law": law,
                    "experiment_guidance_law": law,
                    "guidance_law_sweep": True,
                    "scenario_tags": ["simpleflight", "paired_guidance", "same_seed"],
                    "expected_failure_modes": [
                        "terminal_detection_acquisition_timeout",
                        "terminal_visual_lost_after_coast",
                        "maneuver_margin_low",
                        "bbox_near_image_edge",
                    ],
                },
            )
            full_flow_specs = tuple(
                spec for spec in episode_specs if spec.episode_id == "episode_006_full_flow"
            )
            runs.append((config, selected_sequence_id, full_flow_specs or episode_specs))
            run_index.append((law, seed))

    results = list(run_blocks_batch_sequences(tuple(runs), batch_id=args.sequence_id))
    for result in results:
        _print_sequence_result(result)
    outputs = _write_guidance_law_sweep_outputs(
        Path(args.output_root) / args.sequence_id,
        sequence_id=args.sequence_id,
        seeds=seeds,
        laws=laws,
        run_index=run_index,
        results=results,
    )
    scenario_paths = _write_runtime_scenario_library(
        Path(args.output_root) / args.sequence_id / "scenario_library",
        seeds=seeds,
    )
    print(f"guidance_law_sweep_summary={outputs['json'].resolve()}")
    print(f"guidance_law_sweep_report={outputs['markdown'].resolve()}")
    print(f"scenario_library={scenario_paths['json'].resolve()}")
    return 0


def _build_sequence_run(args: argparse.Namespace, *, seed: int, sequence_id: str):
    if float(args.clock_speed) <= 0.0:
        raise SystemExit("--clock-speed must be positive")
    resource_count, target_count, explicit_counts = _resolve_scenario_counts(args)
    _validate_cooperative_options(args)
    settings_path = Path(args.settings)
    if args.actor_2v2 and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(ACTOR_2V2_TUNED_SETTINGS if args.terminal_handoff_tuned else ACTOR_2V2_SETTINGS)
    if args.actor_5v5 and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(ACTOR_5V5_TUNED_SETTINGS)
    if args.cv_5v5 and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(CV_5V5_SETTINGS)
    if args.cv_5v5_d4d5_stress and args.settings == DEFAULT_SETTINGS:
        settings_path = Path(
            CV_5V5_D4D5_STRESS_200M_SETTINGS
            if args.cv_5v5_d4d5_stress_200m
            else CV_5V5_D4D5_STRESS_SETTINGS
        )
    scenario_name = (
        "blocks_actor_2v2_active_secondary_visual_png"
        if args.actor_2v2_active_secondary_visual_png
        else "blocks_actor_5v5_active_center_replan"
        if args.actor_5v5_active_center_replan
        else "blocks_actor_2v2"
        if args.actor_2v2
        else "blocks_actor_5v5"
        if args.actor_5v5
        else "blocks_cv_5v5"
        if args.cv_5v5
        else "blocks_cv_5v5_d4d5_stress"
        if args.cv_5v5_d4d5_stress
        else "blocks_readonly_smoke"
    )
    if explicit_counts:
        legacy_equal_scale = args.drone_count is not None
        scale_name = (
            f"n{resource_count}"
            if legacy_equal_scale
            else f"m{resource_count}_n{target_count}"
        )
        if args.actor_2v2_active_secondary_visual_png:
            scenario_name = f"blocks_actor_{scale_name}_active_secondary_visual_png"
        elif args.actor_5v5_active_center_replan:
            scenario_name = f"blocks_actor_{scale_name}_active_center_replan"
        elif args.actor_2v2 or args.actor_5v5:
            scenario_name = f"blocks_actor_{scale_name}"
        elif args.cv_5v5_d4d5_stress:
            scenario_name = f"blocks_cv_{scale_name}_d4d5_stress"
        elif args.cv_5v5:
            scenario_name = f"blocks_cv_{scale_name}"
    target_scale_m = (
        args.target_scale_m
        if args.target_scale_m is not None
        else 2.0
        if args.terminal_handoff_tuned
        else None
    )
    generated_settings_dir = Path(args.output_root) / sequence_id / "generated_settings"
    detection_filters = tuple(
        dict.fromkeys(
            item
            for item in (args.target_detection_filter, "MSM_TargetActor_*", "Intruder*")
            if item
        )
    )
    actor_config = {}
    if args.actor_2v2:
        actor_resource_count = resource_count or 2
        actor_target_count = target_count or 2
        actor_resources = default_interceptor_vehicle_names(actor_resource_count)
        if explicit_counts:
            settings_path = write_dynamic_multirotor_settings(
                generated_settings_dir
                / f"blocks_actor_m{actor_resource_count}_n{actor_target_count}_settings.json",
                vehicle_names=actor_resources,
                y_spacing_m=args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 16.0,
                tuned_terminal_camera=bool(args.terminal_handoff_tuned),
                fov_degrees=120.0,
                lidar_range_m=60.0 if args.terminal_handoff_tuned else 80.0,
                clock_speed=args.clock_speed,
            )
        actor_config = {
            "camera_vehicle_name": actor_resources[0],
            "camera_vehicle_names": actor_resources,
            "lidar_vehicle_name": actor_resources[0],
            "lidar_vehicle_names": actor_resources,
            "target_vehicle_names": (),
            "resource_vehicle_names": actor_resources,
            "target_actor_specs": (
                default_actor_target_specs(
                    count=actor_target_count,
                    target_z=args.intercept_altitude_z if args.execute_intercept else -2.0,
                    target_distance_m=args.actor_target_distance
                    if args.actor_target_distance is not None
                    else 12.0,
                    target_spacing_m=args.actor_target_spacing
                    if args.actor_target_spacing is not None
                    else 12.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 1.0,
                    target_speed_scale=args.actor_target_speed_scale,
                    x_spacing_m=0.0,
                    x_speed_base_mps=2.0,
                    x_speed_step_mps=0.0,
                    y_speed_span_mps=0.6,
                )
                if explicit_counts
                else default_2v2_actor_target_specs(
                    target_z=args.intercept_altitude_z if args.execute_intercept else -2.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 1.0,
                )
            ),
            "detection_filter_names": detection_filters,
            "metadata": {
                "runtime_mode": (
                    "actor_nvN_active_secondary_visual_png"
                    if args.drone_count is not None
                    and args.actor_2v2_active_secondary_visual_png
                    else "actor_m_to_n_active_secondary_visual_png"
                    if explicit_counts and args.actor_2v2_active_secondary_visual_png
                    else "actor_nvN"
                    if args.drone_count is not None
                    else "actor_m_to_n"
                    if explicit_counts
                    else "actor_2v2"
                ),
                "drone_count": actor_resource_count,
                "resource_count": actor_resource_count,
                "target_count": actor_target_count,
                "terminal_handoff_tuned": bool(args.terminal_handoff_tuned),
                "target_asset_name": args.target_asset_name,
                "active_secondary_visual_png": bool(args.actor_2v2_active_secondary_visual_png),
                "active_degradation_time_s": float(args.active_degradation_time),
                "secondary_plan_time_s": float(args.secondary_plan_time),
                "secondary_node_id": "SEC-01",
            },
        }
    if args.actor_5v5:
        actor_resource_count = resource_count or 5
        actor_target_count = target_count or 5
        actor_5v5_resources = default_interceptor_vehicle_names(actor_resource_count)
        cooperative_positions = _cooperative_primary_vehicle_positions(
            actor_5v5_resources,
            target_count=actor_target_count,
            target_distance_m=(
                args.actor_target_distance
                if args.actor_target_distance is not None
                else 35.0
            ),
            target_spacing_m=(
                args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 10.0
            ),
            default_resource_spacing_m=(
                args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 10.0
            ),
            sector_separation_deg=float(
                args.cooperative_approach_sector_separation
            ),
        )
        cooperative_pose_offsets = _vehicle_position_offsets(
            actor_5v5_resources,
            desired_positions=cooperative_positions,
            default_resource_spacing_m=(
                args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 10.0
            ),
        )
        if explicit_counts:
            settings_path = write_dynamic_multirotor_settings(
                generated_settings_dir
                / f"blocks_actor_m{actor_resource_count}_n{actor_target_count}_settings.json",
                vehicle_names=actor_5v5_resources,
                y_spacing_m=args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 10.0,
                vehicle_positions_ned=(
                    None if args.cooperative_pose_via_api else cooperative_positions
                ),
                tuned_terminal_camera=False,
                fov_degrees=120.0,
                lidar_range_m=80.0,
                clock_speed=args.clock_speed,
            )
        actor_config = {
            "camera_vehicle_name": actor_5v5_resources[0],
            "camera_vehicle_names": actor_5v5_resources,
            "lidar_vehicle_name": actor_5v5_resources[0],
            "lidar_vehicle_names": actor_5v5_resources,
            "target_vehicle_names": (),
            "resource_vehicle_names": actor_5v5_resources,
            "target_actor_specs": (
                default_actor_target_specs(
                    count=actor_target_count,
                    target_z=args.intercept_altitude_z if args.execute_intercept else -5.0,
                    target_distance_m=args.actor_target_distance
                    if args.actor_target_distance is not None
                    else 35.0,
                    target_spacing_m=args.actor_target_spacing
                    if args.actor_target_spacing is not None
                    else 10.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 2.0,
                    target_speed_scale=args.actor_target_speed_scale,
                    x_spacing_m=2.0,
                    x_speed_base_mps=1.2,
                    x_speed_step_mps=0.1,
                    y_speed_span_mps=0.8,
                )
                if explicit_counts
                else default_5v5_actor_target_specs(
                    target_z=args.intercept_altitude_z if args.execute_intercept else -5.0,
                    target_distance_m=args.actor_target_distance
                    if args.actor_target_distance is not None
                    else 35.0,
                    target_spacing_m=args.actor_target_spacing
                    if args.actor_target_spacing is not None
                    else 10.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 2.0,
                    target_speed_scale=args.actor_target_speed_scale,
                )
            ),
            "detection_filter_names": detection_filters,
            "metadata": {
                "runtime_mode": (
                    "actor_nvN"
                    if args.drone_count is not None
                    else "actor_m_to_n"
                    if explicit_counts
                    else "actor_5v5"
                ),
                "drone_count": actor_resource_count,
                "resource_count": actor_resource_count,
                "target_count": actor_target_count,
                "target_asset_name": args.target_asset_name,
                "active_center_replan_visual_png": bool(args.actor_5v5_active_center_replan),
                "active_degradation_time_s": float(args.active_degradation_time),
                "center_replan_time_s": float(args.center_replan_time),
                "center_node_id": "C2",
                "actor_target_distance_m": args.actor_target_distance
                if args.actor_target_distance is not None
                else 35.0,
                "actor_target_spacing_m": args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 10.0,
                "actor_target_speed_scale": args.actor_target_speed_scale,
                "cooperative_approach_sector_separation_deg": float(
                    args.cooperative_approach_sector_separation
                ),
                "cooperative_initial_vehicle_positions_ned": cooperative_positions,
                "cooperative_pose_via_api": bool(args.cooperative_pose_via_api),
                "cooperative_vehicle_pose_offsets_ned": cooperative_pose_offsets,
            },
        }
    if args.cv_5v5 or args.cv_5v5_d4d5_stress:
        cv_resource_count = resource_count or 5
        cv_target_count = target_count or 5
        cv_resources = (
            default_cv_camera_vehicle_names(cv_resource_count)
            if explicit_counts
            else default_cv_5v5_camera_vehicle_names()
        )
        cv_secondaries = (
            ()
            if args.secondary_count == 0
            else default_cv_secondary_vehicle_names(args.secondary_count)
            if explicit_counts or args.secondary_count != 2
            else default_cv_5v5_secondary_vehicle_names()
        )
        secondary_height_above_targets_m = (
            float(args.secondary_height_above_targets)
            if args.secondary_height_above_targets is not None
            else 200.0
            if args.cv_5v5_d4d5_stress_200m
            else 50.0
        )
        default_secondary_fov = (
            80.0
            if args.mobile_secondary_recon
            else 110.0
            if args.cv_5v5_d4d5_stress_200m
            else 140.0
            if args.cv_5v5_d4d5_stress
            else 90.0
        )
        secondary_fov = float(args.secondary_fov if args.secondary_fov is not None else default_secondary_fov)
        secondary_width = int(
            args.secondary_width
            if args.secondary_width is not None
            else 1920
            if args.cv_5v5_d4d5_stress_200m
            else 640
        )
        secondary_height = int(
            args.secondary_height
            if args.secondary_height is not None
            else 1080
            if args.cv_5v5_d4d5_stress_200m
            else 480
        )
        primary_width = int(args.camera_width if args.camera_width is not None else 640)
        primary_height = int(args.camera_height if args.camera_height is not None else 480)
        primary_fov = float(args.camera_fov if args.camera_fov is not None else 90.0)
        if (
            explicit_counts
            or args.secondary_count != 2
            or args.mobile_secondary_recon
            or args.secondary_fov is not None
            or args.secondary_width is not None
            or args.secondary_height is not None
            or args.camera_width is not None
            or args.camera_height is not None
            or args.camera_fov is not None
        ):
            settings_path = write_dynamic_computer_vision_settings(
                generated_settings_dir
                / f"blocks_cv_m{cv_resource_count}_n{cv_target_count}_settings.json",
                camera_vehicle_names=cv_resources,
                secondary_vehicle_names=cv_secondaries,
                camera_spacing_m=args.actor_target_spacing
                if args.actor_target_spacing is not None
                else (20.0 if args.cv_5v5_d4d5_stress else 12.0),
                camera_z=-10.0,
                target_z=-10.0,
                secondary_height_above_targets_m=secondary_height_above_targets_m,
                fov_degrees=primary_fov,
                secondary_fov_degrees=secondary_fov,
                width=primary_width,
                height=primary_height,
                secondary_camera_pitch_deg=0.0
                if args.mobile_secondary_recon
                else -90.0
                if args.cv_5v5_d4d5_stress
                else 0.0,
                secondary_width=secondary_width,
                secondary_height=secondary_height,
                clock_speed=args.clock_speed,
            )
        target_specs = (
            (
                default_actor_target_specs(
                    count=cv_target_count,
                    target_z=-10.0,
                    target_distance_m=args.actor_target_distance
                    if args.actor_target_distance is not None
                    else 50.0,
                    target_spacing_m=args.actor_target_spacing
                    if args.actor_target_spacing is not None
                    else 20.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 10.0,
                    target_speed_scale=args.actor_target_speed_scale,
                    x_spacing_m=0.0,
                    x_speed_base_mps=0.8,
                    x_speed_step_mps=0.1,
                    y_speed_span_mps=0.7,
                )
                if explicit_counts
                else default_cv_5v5_d4d5_stress_actor_target_specs(
                    target_z=-10.0,
                    target_distance_m=args.actor_target_distance
                    if args.actor_target_distance is not None
                    else 50.0,
                    target_spacing_m=args.actor_target_spacing
                    if args.actor_target_spacing is not None
                    else 20.0,
                    target_scale_m=target_scale_m or 10.0,
                    asset_name=args.target_asset_name,
                )
            )
            if args.cv_5v5_d4d5_stress
            else (
                default_actor_target_specs(
                    count=cv_target_count,
                    target_z=-10.0,
                    target_distance_m=args.actor_target_distance
                    if args.actor_target_distance is not None
                    else 35.0,
                    target_spacing_m=args.actor_target_spacing
                    if args.actor_target_spacing is not None
                    else 10.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 1.0,
                    target_speed_scale=args.actor_target_speed_scale,
                    x_spacing_m=(
                        float(args.actor_target_x_spacing)
                        if args.actor_target_x_spacing is not None
                        else 4.0
                    ),
                    x_speed_base_mps=1.4,
                    x_speed_step_mps=0.1,
                    y_speed_span_mps=1.2,
                )
                if explicit_counts
                else default_cv_5v5_actor_target_specs(
                    target_z=-10.0,
                    asset_name=args.target_asset_name,
                    target_scale_m=target_scale_m or 1.0,
                )
            )
        )
        follow_distance = 50.0 if args.cv_5v5_d4d5_stress else args.cv_camera_follow_distance
        actor_config = {
            "camera_vehicle_name": cv_resources[0],
            "camera_vehicle_names": cv_resources,
            "secondary_camera_vehicle_names": cv_secondaries,
            "capture_lidar": False,
            "cv_camera_follow_assignments": True,
            "cv_camera_follow_distance_m": follow_distance,
            "cv_secondary_look_at_enabled": bool(args.mobile_secondary_recon)
            or not bool(args.cv_5v5_d4d5_stress),
            "cv_secondary_mobile_recon_enabled": bool(args.mobile_secondary_recon),
            "cv_secondary_recon_standoff_m": float(args.secondary_recon_standoff),
            "cv_reassignment_time_s": args.cv_reassignment_time,
            "lidar_vehicle_name": cv_resources[0],
            "lidar_vehicle_names": (),
            "target_vehicle_names": (),
            "resource_vehicle_names": cv_resources,
            "target_actor_specs": target_specs,
            "detection_filter_names": detection_filters,
            "detection_radius_cm": int(
                round(
                    (
                        float(args.primary_detection_radius_m)
                        if args.primary_detection_radius_m is not None
                        else (260.0 if args.cv_5v5_d4d5_stress else 160.0)
                    )
                    * 100.0
                )
            ),
            "secondary_detection_radius_cm": int(
                round(
                    (
                        float(args.secondary_detection_radius_m)
                        if args.secondary_detection_radius_m is not None
                        else 300.0
                    )
                    * 100.0
                )
            ),
            "metadata": {
                "runtime_mode": (
                    "computer_vision_nvN_d4d5_stress"
                    if args.drone_count is not None and args.cv_5v5_d4d5_stress
                    else "computer_vision_m_to_n_d4d5_stress"
                    if explicit_counts and args.cv_5v5_d4d5_stress
                    else "computer_vision_nvN"
                    if args.drone_count is not None
                    else "computer_vision_m_to_n"
                    if explicit_counts
                    else "computer_vision_5v5_d4d5_stress"
                    if args.cv_5v5_d4d5_stress
                    else "computer_vision_5v5"
                ),
                "drone_count": cv_resource_count,
                "resource_count": cv_resource_count,
                "target_count": cv_target_count,
                "secondary_camera_vehicle_names": cv_secondaries,
                "d4d5_stress_enabled": bool(args.cv_5v5_d4d5_stress),
                "secondary_recon_mode": (
                    "mobile_recon_gimbal"
                    if args.mobile_secondary_recon
                    else "fixed_downlook_secondary"
                    if args.cv_5v5_d4d5_stress
                    else "fixed_forward_secondary"
                ),
                "secondary_node_role": (
                    "mobile_high_recon"
                    if args.mobile_secondary_recon
                    else "fixed_secondary_recon"
                ),
                "secondary_capability_class": (
                    "mobile_high_recon"
                    if args.mobile_secondary_recon
                    else "fixed_downlook_secondary"
                ),
                "secondary_guidance_source": (
                    "radar_global_track_cue"
                    if args.mobile_secondary_recon
                    else "fixed_camera_mount"
                ),
                "secondary_height_target_m": secondary_height_above_targets_m,
                "secondary_detection_backend": "airsim_detect",
                "secondary_camera_mount_pitch_deg": 0.0
                if args.mobile_secondary_recon
                else -90.0
                if args.cv_5v5_d4d5_stress
                else 0.0,
                "secondary_camera_fov_degrees": secondary_fov,
                "secondary_camera_width": secondary_width,
                "secondary_camera_height": secondary_height,
                "primary_camera_width": primary_width,
                "primary_camera_height": primary_height,
                "primary_camera_fov_degrees": primary_fov,
                "secondary_recon_standoff_m": float(args.secondary_recon_standoff),
                "secondary_look_at_runtime_enabled": bool(args.mobile_secondary_recon)
                or not bool(args.cv_5v5_d4d5_stress),
                "target_asset_name": args.target_asset_name,
                "actor_target_distance_m": args.actor_target_distance
                if args.actor_target_distance is not None
                else 35.0,
                "actor_target_spacing_m": args.actor_target_spacing
                if args.actor_target_spacing is not None
                else 10.0,
                "actor_target_x_spacing_m": args.actor_target_x_spacing
                if args.actor_target_x_spacing is not None
                else 4.0,
            },
        }
    actor_config.setdefault("metadata", {})
    actor_config["metadata"].update(
        {
            "sequence_id": args.sequence_id,
            "guidance_law": args.guidance_law,
            "experiment_guidance_law": args.guidance_law,
            "guidance_comparison_group": args.sequence_id,
            "scenario_tags": [scenario_name, "airsim_blocks"],
            "clock_speed": float(args.clock_speed),
            "c2_health_mode": args.c2_health_mode,
            "coalition_commit_fault": args.coalition_commit_fault,
            "intercept_max_turn_rate_radps": float(args.intercept_max_turn_rate),
            "intercept_max_lateral_accel_mps2": float(args.intercept_max_lateral_accel),
            "intercept_min_maneuver_margin": float(args.intercept_min_maneuver_margin),
            "terminal_authorization_scope": str(args.terminal_authorization_scope),
            "arrival_coordination_required": bool(args.arrival_coordination_required),
            "episode_communication_enabled": bool(
                args.enable_cooperative_demand
                or args.center_failure_time is not None
                or args.secondary_failure_time is not None
                or args.coalition_commit_fault != "none"
                or (
                    explicit_counts
                    and resource_count is not None
                    and target_count is not None
                    and resource_count != target_count
                )
            ),
        }
    )
    if args.center_failure_time is not None:
        actor_config["metadata"]["center_failure_time_s"] = float(
            args.center_failure_time
        )
    if args.secondary_failure_time is not None:
        actor_config["metadata"]["secondary_failure_time_s"] = float(
            args.secondary_failure_time
        )
    actor_config["capture_lidar"] = bool(actor_config.get("capture_lidar", True)) and not args.no_lidar
    base_config = BlocksSmokeConfig(
        scenario_name=scenario_name,
        duration_s=args.duration,
        dt_s=args.dt,
        clock_speed=float(args.clock_speed),
        seed=seed,
        output_root=Path(args.output_root),
        blocks_script=Path(args.blocks_script),
        settings_path=settings_path,
        blocks_args=tuple(args.blocks_arg)
        if args.blocks_arg is not None
        else BlocksSmokeConfig().blocks_args,
        prefer_nvidia_offload=not args.no_nvidia_offload,
        connection_timeout_s=args.connection_timeout,
        client_timeout_s=args.client_timeout,
        client_kind="multirotor" if args.execute_intercept else "vehicle",
        save_images=args.save_images,
        execute_intercept=args.execute_intercept,
        control_dt_s=args.control_dt,
        intercept_speed_mps=args.intercept_speed,
        intercept_altitude_ned_z=args.intercept_altitude_z,
        intercept_altitude_settle_timeout_s=args.intercept_altitude_settle_timeout,
        intercept_altitude_tolerance_m=args.intercept_altitude_tolerance,
        intercept_altitude_settle_samples=args.intercept_altitude_settle_samples,
        intercept_radius_m=args.intercept_radius,
        intercept_max_duration_s=args.intercept_max_duration,
        intercept_terminal_switch_range_m=args.intercept_terminal_range,
        intercept_detection_timeout_s=args.intercept_detection_timeout,
        intercept_abort_on_terminal_acquisition_timeout=bool(
            args.intercept_abort_on_terminal_acquisition_timeout
        ),
        intercept_max_turn_rate_radps=args.intercept_max_turn_rate,
        intercept_max_lateral_accel_mps2=args.intercept_max_lateral_accel,
        intercept_min_maneuver_margin=args.intercept_min_maneuver_margin,
        intercept_detection_dropout_start_s=args.intercept_detection_dropout_start,
        intercept_detection_dropout_end_s=args.intercept_detection_dropout_end,
        intercept_terminal_soft_prediction_enabled=bool(args.terminal_soft_prediction),
        intercept_terminal_trend_coast_enabled=bool(args.terminal_trend_coast),
        intercept_guidance_law=args.guidance_law,
        intercept_yaw_mode=(
            args.intercept_yaw_mode
            or ("look_at_target" if args.terminal_handoff_tuned else "velocity")
        ),
        cooperative_demand_enabled=bool(args.enable_cooperative_demand)
        or bool(
            explicit_counts
            and resource_count is not None
            and target_count is not None
            and resource_count != target_count
        ),
        cooperative_high_threat_target_count=int(args.cooperative_high_threat_target_count),
        cooperative_threat_threshold=float(args.cooperative_threat_threshold),
        high_threat_required_resource_count=int(args.high_threat_resource_count),
        cooperative_coordination_mode=str(args.cooperative_coordination_mode),
        cooperative_primary_count=int(args.cooperative_primary_count),
        cooperative_wave_gap_s=float(args.cooperative_wave_gap),
        cooperative_minimum_separation_s=float(args.cooperative_minimum_separation),
        terminal_authorization_scope=str(args.terminal_authorization_scope),
        arrival_coordination_required=bool(args.arrival_coordination_required),
        target_asset_name=args.target_asset_name,
        target_detection_filter=args.target_detection_filter,
        detection_warmup_frames=int(args.detection_warmup_frames),
        detection_backend=args.detection_backend,
        yolo_weights_path=Path(args.yolo_weights),
        yolo_tracker_backend=args.yolo_tracker_backend,
        yolo_confidence_threshold=args.yolo_confidence,
        yolo_use_native_tracker=not args.no_yolo_native_tracker,
        yolo_allow_iou_fallback=not args.no_yolo_iou_fallback,
        yolo_compute_device=args.yolo_device,
        yolo_cpu_budget_ms=args.yolo_cpu_budget_ms,
        yolo_gpu_budget_ms=args.yolo_gpu_budget_ms,
        yolo_primary_inference_imgsz=args.yolo_primary_imgsz,
        yolo_secondary_inference_imgsz=args.yolo_secondary_imgsz,
        yolo_offline_truth_evaluation=args.yolo_offline_truth_eval,
        **actor_config,
    )
    selected_episode_specs = D4D5_STRESS_EPISODES if args.cv_5v5_d4d5_stress else DEFAULT_BLOCKS_EPISODES
    if args.full_flow_only:
        selected_episode_specs = tuple(
            spec
            for spec in selected_episode_specs
            if spec.episode_id == "episode_006_full_flow"
        )
    episode_specs = tuple(
        replace(spec, scenario_name=scenario_name, duration_s=args.duration, dt_s=args.dt)
        for spec in selected_episode_specs
    )
    return base_config, sequence_id, episode_specs


def _cooperative_primary_vehicle_positions(
    vehicle_names: tuple[str, ...],
    *,
    target_count: int,
    target_distance_m: float,
    target_spacing_m: float,
    default_resource_spacing_m: float,
    sector_separation_deg: float,
) -> dict[str, tuple[float, float, float]] | None:
    """Place the first two primaries symmetrically about target-1's initial LOS."""

    if sector_separation_deg <= 0.0 or len(vehicle_names) < 2 or target_count < 1:
        return None
    if sector_separation_deg >= 180.0:
        raise SystemExit("--cooperative-approach-sector-separation must be below 180")
    center = (len(vehicle_names) - 1) / 2.0
    positions = {
        name: (0.0, (index - center) * default_resource_spacing_m, 0.0)
        for index, name in enumerate(vehicle_names)
    }
    first_target_y = -((target_count - 1) / 2.0) * target_spacing_m
    lateral_offset = target_distance_m * math.tan(
        math.radians(sector_separation_deg / 2.0)
    )
    positions[vehicle_names[0]] = (0.0, first_target_y - lateral_offset, 0.0)
    positions[vehicle_names[1]] = (0.0, first_target_y + lateral_offset, 0.0)
    return positions


def _vehicle_position_offsets(
    vehicle_names: tuple[str, ...],
    *,
    desired_positions: dict[str, tuple[float, float, float]] | None,
    default_resource_spacing_m: float,
) -> dict[str, tuple[float, float, float]]:
    if desired_positions is None:
        return {}
    center = (len(vehicle_names) - 1) / 2.0
    offsets: dict[str, tuple[float, float, float]] = {}
    for index, name in enumerate(vehicle_names):
        baseline = (0.0, (index - center) * default_resource_spacing_m, 0.0)
        desired = desired_positions.get(name, baseline)
        offsets[name] = tuple(
            float(desired[axis] - baseline[axis]) for axis in range(3)
        )
    return offsets


def _resolve_scenario_counts(
    args: argparse.Namespace,
) -> tuple[int | None, int | None, bool]:
    if args.drone_count is not None and (
        args.resource_count is not None or args.target_count is not None
    ):
        raise SystemExit(
            "--drone-count cannot be combined with --resource-count or --target-count"
        )
    if args.drone_count is not None:
        if args.drone_count <= 0:
            raise SystemExit("--drone-count must be positive")
        count = int(args.drone_count)
        return count, count, True

    explicit = args.resource_count is not None or args.target_count is not None
    if not explicit:
        return None, None, False
    for name in ("resource_count", "target_count"):
        value = getattr(args, name)
        if value is not None and value <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")

    default_count = (
        2
        if args.actor_2v2
        else 5
        if args.actor_5v5 or args.cv_5v5 or args.cv_5v5_d4d5_stress
        else None
    )
    if default_count is None:
        raise SystemExit(
            "--resource-count/--target-count require an actor or ComputerVision scenario"
        )
    resource_count = (
        int(args.resource_count)
        if args.resource_count is not None
        else default_count
    )
    target_count = (
        int(args.target_count)
        if args.target_count is not None
        else default_count
    )
    return resource_count, target_count, True


def _validate_cooperative_options(args: argparse.Namespace) -> None:
    required = int(args.high_threat_resource_count)
    primary = int(args.cooperative_primary_count)
    if required < 1:
        raise SystemExit("--high-threat-resource-count must be positive")
    if primary < 1 or primary > required:
        raise SystemExit(
            "--cooperative-primary-count must be between 1 and "
            "--high-threat-resource-count"
        )
    if int(args.cooperative_high_threat_target_count) < 0:
        raise SystemExit("--cooperative-high-threat-target-count must be non-negative")
    threshold = float(args.cooperative_threat_threshold)
    if not 0.0 <= threshold <= 1.0:
        raise SystemExit("--cooperative-threat-threshold must be in [0, 1]")
    if float(args.cooperative_wave_gap) < 0.0:
        raise SystemExit("--cooperative-wave-gap must be non-negative")
    if float(args.cooperative_minimum_separation) < 0.0:
        raise SystemExit("--cooperative-minimum-separation must be non-negative")
    sector = float(args.cooperative_approach_sector_separation)
    if not 0.0 <= sector < 180.0:
        raise SystemExit(
            "--cooperative-approach-sector-separation must be in [0, 180)"
        )
    if int(args.p1_cooperative_candidate_limit) <= 0:
        raise SystemExit("--p1-cooperative-candidate-limit must be positive")
    if int(args.detection_warmup_frames) < 0:
        raise SystemExit("--detection-warmup-frames must be non-negative")
    for name in ("camera_width", "camera_height"):
        value = getattr(args, name)
        if value is not None and int(value) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    if args.camera_fov is not None and not 0.0 < float(args.camera_fov) < 180.0:
        raise SystemExit("--camera-fov must be in (0, 180)")
    if float(args.intercept_max_turn_rate) <= 0.0:
        raise SystemExit("--intercept-max-turn-rate must be positive")
    if float(args.intercept_max_lateral_accel) <= 0.0:
        raise SystemExit("--intercept-max-lateral-accel must be positive")
    if not 0.0 <= float(args.intercept_min_maneuver_margin) < 1.0:
        raise SystemExit("--intercept-min-maneuver-margin must be in [0, 1)")
    if (args.intercept_detection_dropout_start is None) != (
        args.intercept_detection_dropout_end is None
    ):
        raise SystemExit("both intercept detection dropout bounds must be provided")
    if args.intercept_detection_dropout_start is not None:
        if float(args.intercept_detection_dropout_start) < 0.0:
            raise SystemExit("--intercept-detection-dropout-start must be non-negative")
        if float(args.intercept_detection_dropout_end) <= float(
            args.intercept_detection_dropout_start
        ):
            raise SystemExit("--intercept-detection-dropout-end must be after start")
    if args.center_failure_time is not None and float(args.center_failure_time) < 0.0:
        raise SystemExit("--center-failure-time must be non-negative")
    if args.secondary_failure_time is not None and float(args.secondary_failure_time) < 0.0:
        raise SystemExit("--secondary-failure-time must be non-negative")
    if (
        args.c2_health_mode == "fully_distributed"
        and args.center_failure_time is not None
        and args.secondary_failure_time is not None
        and float(args.secondary_failure_time) < float(args.center_failure_time)
    ):
        raise SystemExit(
            "--secondary-failure-time must not precede --center-failure-time"
        )


def _print_sequence_result(result) -> None:
    print(f"sequence_id={result.sequence_id}")
    print(f"connected={result.connected}")
    print(f"episode_count={len(result.episode_results)}")
    for episode in result.episode_results:
        print(
            f"{episode.episode_id}: frames={episode.frame_count} "
            f"vehicles={','.join(episode.vehicle_names)} "
            f"image_ok={episode.image_ok_count} lidar_ok={episode.lidar_ok_count} "
            f"integrated={episode.integrated_result is not None}"
        )
    print(f"summary={result.output_paths['blocks_sequence_summary'].resolve()}")


def _parse_batch_seeds(raw: str | None, *, default: int) -> list[int]:
    if raw is None or not raw.strip():
        return [int(default)]
    seeds = [int(item.strip()) for item in raw.split(",") if item.strip()]
    if not seeds:
        raise SystemExit("--batch-seeds did not contain any integer seeds")
    return seeds


def _run_p1_cooperative_closure_sweep(args: argparse.Namespace) -> int:
    """Screen cooperative candidates offline, then run the top profiles in Blocks."""

    seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    d3_candidates = build_p1_cooperative_candidate_grid()
    main_candidates = tuple(
        CooperativeCandidate(
            candidate_id=candidate.candidate_id,
            terminal_handoff_range_m=candidate.terminal_handoff_range_m,
            primary_arrival_window_width_s=candidate.primary_arrival_window_width_s,
            approach_sector_separation_deg=candidate.approach_sector_separation_deg,
        )
        for candidate in d3_candidates
    )
    screening_rows = run_pointmass_candidate_screen(main_candidates, seeds=seeds)
    observations = tuple(
        CooperativeCandidateObservation(
            candidate_id=str(row["candidate_id"]),
            safety_violation_count=int(row["safety_violation_count"]),
            coalition_completion_count=int(row["coalition_completion_count"]),
            coalition_opportunity_count=int(row["coalition_opportunity_count"]),
            pair_success_count=int(row["pair_success_count"]),
            pair_opportunity_count=int(row["pair_opportunity_count"]),
            arrival_spread_s=float(row["arrival_spread_s"]),
            evidence_source=str(row["evidence_source"]),
            metadata={"suite_version": "p1-cooperative-closure-v2"},
        )
        for row in screening_rows
    )
    ranked = rank_cooperative_candidates(
        d3_candidates,
        observations,
        limit=int(args.p1_cooperative_candidate_limit),
    )
    selected_ids = {row.candidate.candidate_id for row in ranked}
    selected = tuple(
        candidate for candidate in main_candidates if candidate.candidate_id in selected_ids
    )
    cases = build_cooperative_closure_cases(seeds, selected)
    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    screening_path = output_dir / "p1_cooperative_pointmass_screen.json"
    screening_path.write_text(
        json.dumps(
            {
                "schema_version": "main-p1-cooperative-pointmass-screen-v1",
                "suite_version": "p1-cooperative-closure-v2",
                "rows": screening_rows,
                "ranked": [row.as_dict() for row in ranked],
                "selected_candidate_ids": [row.candidate.candidate_id for row in ranked],
                "default_runtime_candidate_changed": False,
                "png_core_formula_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runs = tuple(_build_cooperative_closure_run(args, case) for case in cases)
    results = run_blocks_batch_sequences(
        runs,
        batch_id=f"{args.sequence_id}_m5n2_cooperative_v2",
    )
    pair_rows: list[dict[str, object]] = []
    for case, result in zip(cases, results, strict=True):
        _print_sequence_result(result)
        episode = _controlled_episode_from_result(result)
        if episode is None:
            continue
        summary_path = episode.output_paths.get("intercept_summary")
        commands_path = episode.output_paths.get("control_commands")
        summary = (
            json.loads(Path(summary_path).read_text(encoding="utf-8"))
            if summary_path is not None and Path(summary_path).exists()
            else {"pairs": []}
        )
        commands = _read_csv_rows(commands_path)
        rows = build_pair_funnel_rows(case, summary, commands)
        for row in rows:
            row["connected"] = bool(getattr(result, "connected", False))
            row["intercept_summary"] = (
                None if summary_path is None else str(summary_path)
            )
            row["control_commands"] = (
                None if commands_path is None else str(commands_path)
            )
        pair_rows.extend(rows)

    paths = write_cooperative_closure_bundle(output_dir, cases, pair_rows)
    communication_report = run_p1_communication_fault_matrix(
        CommunicationReplayConfig(
            member_ids=("INT-01", "INT-02", "INT-03"),
            secondary_node_ids=("SEC-01", "SEC-02"),
        ),
        seeds=seeds,
    )
    communication_path = output_dir / "d4_communication_fault_matrix.json"
    communication_path.write_text(
        json.dumps(communication_report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    d6_paths = CooperativeClosureReportGenerator().write_report_bundle(
        output_dir / "d6_cooperative_closure",
        inputs=CooperativeClosureInputs(
            rows=pair_rows,
            d3_candidate=screening_path,
            d4_communication=communication_report.cases,
            d5_visibility=pair_rows,
            d7_guidance=pair_rows,
        ),
    )
    print(f"p1_cooperative_screen={screening_path.resolve()}")
    print(f"p1_cooperative_summary={paths['json'].resolve()}")
    print(f"p1_cooperative_report={paths['markdown'].resolve()}")
    print(f"p1_cooperative_d4_communication={communication_path.resolve()}")
    print(f"p1_cooperative_d6_report={d6_paths['markdown'].resolve()}")
    return 0


def _build_cooperative_closure_run(
    args: argparse.Namespace,
    case: CooperativeClosureCase,
):
    case_args = copy.deepcopy(args)
    case_args.p1_cooperative_closure_sweep = False
    case_args.p1_terminal_closure_sweep = False
    case_args.p1_calibration_sweep = False
    case_args.guidance_law_sweep = False
    case_args.actor_2v2 = False
    case_args.actor_5v5 = True
    case_args.cv_5v5 = False
    case_args.cv_5v5_d4d5_stress = False
    case_args.resource_count = int(case.resource_count)
    case_args.target_count = int(case.target_count)
    case_args.drone_count = None
    case_args.execute_intercept = True
    case_args.full_flow_only = True
    case_args.no_lidar = True
    case_args.duration = float(case.duration_s)
    case_args.intercept_max_duration = float(case.duration_s)
    case_args.intercept_altitude_z = float(case.intercept_altitude_z)
    case_args.intercept_terminal_range = float(
        case.candidate.terminal_handoff_range_m
    )
    case_args.intercept_yaw_mode = "look_at_target"
    case_args.guidance_law = "png_vm"
    case_args.terminal_soft_prediction = False
    case_args.terminal_trend_coast = False
    case_args.enable_cooperative_demand = True
    case_args.high_threat_resource_count = 3
    case_args.cooperative_primary_count = 2
    case_args.cooperative_coordination_mode = "hybrid"
    case_args.cooperative_wave_gap = float(
        case.candidate.primary_arrival_window_width_s
    )
    case_args.cooperative_approach_sector_separation = float(
        case.candidate.approach_sector_separation_deg
    )
    case_args.cooperative_pose_via_api = True
    case_args.settings = DEFAULT_SETTINGS
    sequence_id = f"{args.sequence_id}_{case.case_id}"
    config, selected_sequence_id, episode_specs = _build_sequence_run(
        case_args,
        seed=case.seed,
        sequence_id=sequence_id,
    )
    config = replace(
        config,
        metadata={**config.metadata, **case.metadata()},
    )
    return config, selected_sequence_id, episode_specs


def _read_csv_rows(path: object) -> list[dict[str, str]]:
    if path is None or not Path(path).exists():
        return []
    with Path(path).open("r", encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def _run_p1_terminal_closure_sweep(args: argparse.Namespace) -> int:
    """Run the frozen terminal P1 matrix and write a main-owned execution index."""

    seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    dropout_frames = _parse_int_list(
        args.p1_dropout_frames,
        option_name="--p1-dropout-frames",
    )
    cases = build_terminal_closure_cases(
        seeds,
        dropout_frames=dropout_frames,
        control_dt_s=float(args.control_dt),
        dropout_start_s=float(args.p1_dropout_start),
    )
    cases = _select_terminal_closure_cases(
        cases,
        m5n2_only=bool(args.p1_terminal_closure_m5n2_only),
    )
    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    # M5N2 and tuned 2v2 use different AirSim vehicle/camera settings. Each
    # family launches Blocks once; every case and seed inside it uses reset.
    for settings_family in ("m5n2", "tuned_2v2"):
        selected = tuple(
            case
            for case in cases
            if (case.family != "m5n2_paired") == (settings_family == "tuned_2v2")
        )
        if not selected:
            continue
        runs = tuple(_build_terminal_closure_run(args, case) for case in selected)
        results = run_blocks_batch_sequences(
            runs,
            batch_id=f"{args.sequence_id}_{settings_family}",
        )
        for case, result in zip(selected, results, strict=True):
            _print_sequence_result(result)
            rows.append(_terminal_closure_result_row(case, result))

    paths = write_terminal_closure_bundle(output_dir, cases, rows)
    main_stage_timings = _merge_terminal_closure_stage_timings(
        rows,
        field="main_stage_timings",
        output_path=output_dir / "d6_stage_timing" / "main_bus_stage_timings.jsonl",
    )
    control_tick_stage_timings = _merge_terminal_closure_stage_timings(
        rows,
        field="control_tick_stage_timings",
        output_path=output_dir / "d6_stage_timing" / "control_tick_stage_timings.jsonl",
    )
    d6_suite_paths = P1AcceptanceReportGenerator().write_report_bundle(
        output_dir / "d6_acceptance_suite",
        inputs=P1AcceptanceInputs(
            main_terminal_closure=paths["json"],
            main_stage_timings=main_stage_timings,
            control_tick_stage_timings=control_tick_stage_timings,
        ),
        title="P1 末端闭环统一验收报告",
    )
    for row in rows:
        case_id = str(row.get("case_id") or "unknown_case")
        case_summary = {
            "schema_version": "main-p1-terminal-closure-case-v1",
            "rows": [row],
        }
        d3_history = _existing_path(row.get("d3_plan_history"))
        d7_execution = _existing_path(row.get("d7_execution_metrics"))
        P1AcceptanceReportGenerator().write_report_bundle(
            output_dir / "d6_acceptance_cases" / case_id,
            inputs=P1AcceptanceInputs(
                main_terminal_closure=case_summary,
                d3_plan_history=d3_history,
                d7_terminal_execution=d7_execution,
                main_stage_timings=_existing_path(row.get("main_stage_timings")),
                control_tick_stage_timings=_existing_path(
                    row.get("control_tick_stage_timings")
                ),
            ),
            title=f"P1 末端闭环单场景验收：{case_id}",
        )
    print(f"p1_terminal_closure_summary={paths['json'].resolve()}")
    print(f"p1_terminal_closure_report={paths['markdown'].resolve()}")
    print(f"p1_terminal_closure_d6_report={d6_suite_paths['markdown'].resolve()}")
    return 0


def _select_terminal_closure_cases(
    cases: tuple[TerminalClosureCase, ...],
    *,
    m5n2_only: bool,
) -> tuple[TerminalClosureCase, ...]:
    if not m5n2_only:
        return cases
    return tuple(case for case in cases if case.family == "m5n2_paired")


def _merge_terminal_closure_stage_timings(
    rows: list[dict[str, object]],
    *,
    field: str,
    output_path: Path,
) -> Path | None:
    """Merge one timing layer only when every case registered valid records."""

    output_path.unlink(missing_ok=True)
    merged: list[dict[str, object]] = []
    if not rows:
        return None
    for row in rows:
        raw_path = row.get(field)
        if raw_path in {None, ""}:
            return None
        path = Path(str(raw_path))
        if not path.exists():
            return None
        case_records: list[dict[str, object]] = []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if not isinstance(record, dict):
                    return None
                case_records.append(
                    {
                        **record,
                        "case_id": row.get("case_id"),
                        "family": row.get("family"),
                        "profile": row.get("profile"),
                        "seed": row.get("seed"),
                    }
                )
        if not case_records:
            return None
        merged.extend(case_records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as stream:
        for record in merged:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return output_path


def _build_terminal_closure_run(
    args: argparse.Namespace,
    case: TerminalClosureCase,
):
    case_args = copy.deepcopy(args)
    case_args.p1_terminal_closure_sweep = False
    case_args.p1_calibration_sweep = False
    case_args.guidance_law_sweep = False
    case_args.actor_2v2 = case.family != "m5n2_paired"
    case_args.actor_5v5 = case.family == "m5n2_paired"
    case_args.actor_2v2_active_secondary_visual_png = False
    case_args.actor_5v5_active_center_replan = False
    case_args.cv_5v5 = False
    case_args.cv_5v5_d4d5_stress = False
    case_args.cv_5v5_d4d5_stress_200m = False
    case_args.drone_count = None
    case_args.resource_count = int(case.resource_count)
    case_args.target_count = int(case.target_count)
    case_args.execute_intercept = True
    case_args.full_flow_only = True
    case_args.no_lidar = True
    case_args.duration = float(case.duration_s)
    case_args.intercept_max_duration = float(case.duration_s)
    case_args.intercept_altitude_z = float(case.intercept_altitude_z)
    case_args.intercept_terminal_range = 30.0
    case_args.intercept_yaw_mode = "look_at_target"
    case_args.guidance_law = str(case.guidance_law)
    case_args.terminal_soft_prediction = bool(case.soft_prediction_enabled)
    case_args.terminal_trend_coast = bool(case.trend_coast_enabled)
    case_args.intercept_detection_dropout_start = case.dropout_start_s
    case_args.intercept_detection_dropout_end = case.dropout_end_s
    case_args.terminal_handoff_tuned = case.family != "m5n2_paired"
    case_args.settings = DEFAULT_SETTINGS
    sequence_id = f"{args.sequence_id}_{case.case_id}"
    base_config, selected_sequence_id, episode_specs = _build_sequence_run(
        case_args,
        seed=case.seed,
        sequence_id=sequence_id,
    )
    base_config = replace(
        base_config,
        metadata={**base_config.metadata, **case.metadata()},
    )
    return base_config, selected_sequence_id, episode_specs


def _terminal_closure_result_row(
    case: TerminalClosureCase,
    result: object,
) -> dict[str, object]:
    episode = _controlled_episode_from_result(result)
    summary_path = None if episode is None else episode.output_paths.get("intercept_summary")
    commands_path = None if episode is None else episode.output_paths.get("control_commands")
    main_metrics_path = (
        None
        if episode is None
        else episode.output_paths.get("main_episode_bus_metrics_json")
    )
    d3_history_path = (
        None if episode is None else episode.output_paths.get("d3_plan_history_json")
    )
    d7_execution_path = (
        None if episode is None else episode.output_paths.get("d7_execution_metrics")
    )
    d7_actual_execution_path = (
        None
        if episode is None
        else episode.output_paths.get("d7_actual_execution_metrics")
    )
    d7_actual_unavailable_path = (
        None
        if episode is None
        else episode.output_paths.get("d7_actual_execution_unavailable")
    )
    main_stage_timings_path = (
        None
        if episode is None
        else episode.output_paths.get("main_stage_timings_jsonl")
    )
    control_tick_stage_timings_path = (
        None
        if episode is None
        else episode.output_paths.get("control_tick_timings")
    )
    d7_actual_unavailable = _read_json_mapping(d7_actual_unavailable_path)
    d7_actual_status = (
        "available"
        if d7_actual_execution_path is not None
        and Path(d7_actual_execution_path).exists()
        else "unavailable"
    )
    summary: dict[str, object] = {}
    if summary_path is not None and Path(summary_path).exists():
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    pairs = [pair for pair in summary.get("pairs", []) or [] if isinstance(pair, dict)]
    command_counts = _terminal_closure_command_counts(commands_path)
    main_metrics_payload = _read_json_mapping(main_metrics_path)
    main_metrics = dict(main_metrics_payload.get("metrics", {}) or {})
    main_metrics_metadata = dict(main_metrics_payload.get("metadata", {}) or {})
    record_counts = dict(main_metrics_metadata.get("record_counts", {}) or {})
    d6_metrics = load_d7_intercept_outputs(
        control_commands_path=commands_path,
        intercept_summary_path=summary_path,
    ).compute_episode(
        f"{case.case_id}_truth_isolated_execution",
        seed=case.seed,
        duration=case.duration_s,
    ).to_dict()
    d6_metadata = dict(d6_metrics.get("metadata", {}) or {})
    command_counts["online_truth_use_count"] = max(
        int(command_counts["online_truth_use_count"]),
        int(d6_metrics.get("truth_identity_online_use_count") or 0),
    )
    pair_opportunity_count = d6_metadata.get("pair_physical_opportunity_count")
    target_opportunity_count = d6_metadata.get("target_intercept_opportunity_count")
    coalition_opportunity_count = d6_metadata.get("coalition_opportunity_count")
    live_command_count = int(command_counts.get("live_command_count") or 0)
    terminal_metric_envelopes = {
        name: {
            "metric_name": name,
            "value": command_counts.get(name),
            "producer": "d7_simpleflight_execution",
            "metric_scope": "pair_control_sample",
            "denominator": live_command_count,
            "lifecycle": "live_non_termination",
        }
        for name in (
            "contract_allowed_count",
            "control_allowed_count",
            "terminal_switch_allowed_count",
            "mode_switched_count",
        )
    }
    terminal_metric_envelopes["physical_intercept_count"] = {
        "metric_name": "physical_intercept_count",
        "value": d6_metrics.get("physical_intercept_count"),
        "producer": "offline_truth_distance_scorer",
        "metric_scope": "assigned_active_pair_outcome",
        "denominator": pair_opportunity_count,
        "lifecycle": "episode_final",
    }
    return {
        "schema_version": "main-p1-terminal-closure-row-v3",
        "case_id": case.case_id,
        "family": case.family,
        "profile": case.profile,
        "seed": case.seed,
        "resource_count": case.resource_count,
        "target_count": case.target_count,
        "duration_s": case.duration_s,
        "clock_speed": (summary.get("parameters", {}) or {}).get("clock_speed"),
        "guidance_law": case.guidance_law,
        "dropout_frames": case.dropout_frames,
        "connected": bool(getattr(result, "connected", False)),
        "pair_opportunity_count": pair_opportunity_count,
        "pair_success_count": d6_metrics.get("pair_physical_success_count"),
        "target_opportunity_count": target_opportunity_count,
        "target_success_count": d6_metrics.get("target_intercept_success_count"),
        "coalition_opportunity_count": coalition_opportunity_count,
        "coalition_completion_count": d6_metrics.get("coalition_completion_count"),
        "physical_intercept_count": d6_metrics.get("physical_intercept_count"),
        "truth_identity_online_use_count": d6_metrics.get(
            "truth_identity_online_use_count"
        ),
        "truth_state_online_use_count": d6_metrics.get(
            "truth_state_online_use_count"
        ),
        "online_control_state_source": d6_metadata.get(
            "online_control_state_source"
        ),
        "physical_intercept_source": d6_metadata.get("physical_intercept_source"),
        "physical_metrics_available": bool(
            d6_metadata.get("physical_intercept_evidence_available")
        ),
        "physical_metrics_unavailable_reason": d6_metadata.get(
            "physical_intercept_unavailable_reason"
        ),
        "coalition_completion_availability": d6_metadata.get(
            "coalition_completion_availability"
        ),
        "coalition_completion_unavailable_reason": d6_metadata.get(
            "coalition_completion_unavailable_reason"
        ),
        "reserve_unauthorized_success_count": sum(
            bool(pair.get("physical_success"))
            and str(pair.get("member_role")) == "reserve"
            and str(pair.get("activation_state")) != "active"
            for pair in pairs
        ),
        **command_counts,
        "terminal_metric_envelopes": terminal_metric_envelopes,
        "physical_metric_context": {
            "producer": "offline_truth_distance_scorer",
            "metric_scope": "assigned_active_pair_target_coalition_outcome",
            "lifecycle": "episode_final",
        },
        "performance_metrics": {
            "sample_count": int(record_counts.get("ticks") or 0),
            "loop_latency_ms": main_metrics.get("loop_latency_ms"),
            "performance_budget_violation_count": main_metrics.get(
                "performance_budget_violation_count"
            ),
        },
        "intercept_summary": str(summary_path) if summary_path is not None else None,
        "control_commands": str(commands_path) if commands_path is not None else None,
        "main_episode_bus_metrics": (
            str(main_metrics_path) if main_metrics_path is not None else None
        ),
        "main_stage_timings": (
            str(main_stage_timings_path)
            if main_stage_timings_path is not None
            else None
        ),
        "control_tick_stage_timings": (
            str(control_tick_stage_timings_path)
            if control_tick_stage_timings_path is not None
            else None
        ),
        "d3_plan_history": (
            str(d3_history_path) if d3_history_path is not None else None
        ),
        "d7_execution_metrics": (
            str(d7_execution_path) if d7_execution_path is not None else None
        ),
        "d7_actual_execution_status": d7_actual_status,
        "d7_actual_execution_metrics": (
            str(d7_actual_execution_path)
            if d7_actual_execution_path is not None
            else None
        ),
        "d7_actual_execution_unavailable": (
            str(d7_actual_unavailable_path)
            if d7_actual_unavailable_path is not None
            else None
        ),
        "d7_actual_execution_unavailable_reasons": list(
            d7_actual_unavailable.get("reasons", []) or []
        ),
    }


def _terminal_closure_command_counts(path: object) -> dict[str, int]:
    counts = {
        "command_count": 0,
        "live_command_count": 0,
        "termination_snapshot_count": 0,
        "contract_allowed_count": 0,
        "control_allowed_count": 0,
        "mode_switched_count": 0,
        "terminal_switch_allowed_count": 0,
        "terminal_prediction_count": 0,
        "terminal_delivery_expired_count": 0,
        "terminal_prediction_window_expired_count": 0,
        "terminal_trend_coast_count": 0,
        "online_truth_use_count": 0,
        "ttc_area_jump_reject_count": 0,
        "ttc_bbox_clipping_reject_count": 0,
        "ttc_not_expanding_reject_count": 0,
        "ttc_out_of_range_reject_count": 0,
    }
    if path is None or not Path(path).exists():
        return counts
    previous_mode_by_resource: dict[str, str] = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            counts["command_count"] += 1
            termination_snapshot = _csv_bool(row.get("termination_snapshot"))
            if termination_snapshot:
                counts["termination_snapshot_count"] += 1
                continue
            counts["live_command_count"] += 1
            contract_allowed = _csv_bool(
                row.get("effective_terminal_contract_allowed")
                if row.get("effective_terminal_contract_allowed") not in {None, ""}
                else row.get("terminal_contract_allowed")
            )
            switch_allowed = _csv_bool(
                row.get("effective_control_authorized")
                if row.get("effective_control_authorized") not in {None, ""}
                else row.get("terminal_control_allowed")
                if row.get("terminal_control_allowed") not in {None, ""}
                else row.get("terminal_switch_allowed")
            )
            if contract_allowed:
                counts["contract_allowed_count"] += 1
            if contract_allowed and switch_allowed:
                counts["terminal_switch_allowed_count"] += 1
                counts["control_allowed_count"] += 1
            resource_id = str(row.get("resource_id") or "")
            mode = str(row.get("mode") or "")
            previous_mode = previous_mode_by_resource.get(resource_id)
            if mode == "vision_terminal" and previous_mode not in {None, "vision_terminal"}:
                counts["mode_switched_count"] += 1
            if resource_id and mode:
                previous_mode_by_resource[resource_id] = mode
            state = str(row.get("terminal_delivery_state") or "")
            if state in {"image_kf_predict", "predicted"}:
                counts["terminal_prediction_count"] += 1
            if state == "expired":
                counts["terminal_delivery_expired_count"] += 1
            if str(row.get("terminal_delivery_reason") or "") == (
                "terminal_visual_prediction_window_expired"
            ):
                counts["terminal_prediction_window_expired_count"] += 1
            if _csv_bool(row.get("terminal_trend_coast_applied")):
                counts["terminal_trend_coast_count"] += 1
            if _csv_bool(row.get("truth_identity_online_use")):
                counts["online_truth_use_count"] += 1
            reason = str(row.get("ttc_reject_reason") or "").lower()
            if "area_jump" in reason:
                counts["ttc_area_jump_reject_count"] += 1
            if "clip" in reason or "image_edge" in reason:
                counts["ttc_bbox_clipping_reject_count"] += 1
            if "not_expanding" in reason:
                counts["ttc_not_expanding_reject_count"] += 1
            if "out_of_range" in reason or "max_ttc" in reason:
                counts["ttc_out_of_range_reject_count"] += 1
    return counts


def _read_json_mapping(path: object) -> dict[str, object]:
    resolved = _existing_path(path)
    if resolved is None:
        return {}
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return dict(payload) if isinstance(payload, dict) else {}


def _existing_path(path: object) -> Path | None:
    if path is None:
        return None
    resolved = Path(path)
    return resolved if resolved.exists() else None


def _csv_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _run_p1_mot_calibration_sweep(args: argparse.Namespace) -> int:
    """Run native MOT screening and confirmation in reset-separated CV episodes."""

    if any((args.actor_2v2, args.actor_5v5, args.cv_5v5_d4d5_stress)):
        raise SystemExit(
            "--p1-mot-calibration-sweep cannot be combined with actor or D4/D5 stress modes"
        )
    screening_cases = build_mot_screening_cases(seed=int(args.seed))
    screening_runs = tuple(
        _mot_calibration_case_run(args, case, camera_count=1)
        for case in screening_cases
    )
    screening_results = run_blocks_batch_sequences(
        screening_runs,
        batch_id=f"{args.sequence_id}_screening",
    )
    screening_rows = _native_mot_rows_from_results(screening_cases, screening_results)
    selected = select_backend_thresholds(screening_rows)

    confirmation_seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    if args.batch_seeds is None:
        confirmation_seeds = list(range(int(args.seed), int(args.seed) + 10))
    confirmation_cases = build_mot_confirmation_cases(selected, confirmation_seeds)
    confirmation_results = ()
    confirmation_rows: list[dict[str, object]] = []
    if confirmation_cases:
        confirmation_runs = tuple(
            _mot_calibration_case_run(args, case, camera_count=2)
            for case in confirmation_cases
        )
        confirmation_results = run_blocks_batch_sequences(
            confirmation_runs,
            batch_id=f"{args.sequence_id}_confirmation",
        )
        confirmation_rows = _native_mot_rows_from_results(
            confirmation_cases,
            confirmation_results,
        )

    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    all_cases = (*screening_cases, *confirmation_cases)
    all_rows = [*screening_rows, *confirmation_rows]
    index_path = write_mot_execution_index(
        output_dir / "p1_native_mot_execution_index.json",
        cases=all_cases,
        rows=all_rows,
    )
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "selected_thresholds": selected,
            "screening_case_count": len(screening_cases),
            "confirmation_case_count": len(confirmation_cases),
            "confirmation_seeds": confirmation_seeds,
            "settings_strategy": (
                "one_single_camera_blocks_process_then_one_two_camera_blocks_process; "
                "reset_between_cases"
            ),
            "online_truth_identity_used": False,
            "iou_fallback_admitted": False,
        }
    )
    index_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_path = output_dir / "P1_NATIVE_MOT_AIRSIM_CALIBRATION_REPORT.md"
    report_path.write_text(_native_mot_markdown(payload), encoding="utf-8")
    d6_outputs = P1SystemEvidenceReportGenerator().write_report_bundle(
        output_dir / "d6_native_mot",
        inputs=P1SystemEvidenceInputs(d5_native_mot=index_path),
        title="D6 P1 原生 MOT AirSim 标定汇总",
    )
    for result in (*screening_results, *confirmation_results):
        _print_sequence_result(result)
    print(f"p1_mot_calibration_index={index_path.resolve()}")
    print(f"p1_mot_calibration_report={report_path.resolve()}")
    print(f"p1_mot_d6_report={d6_outputs['markdown'].resolve()}")
    return 0


def _mot_calibration_case_run(
    args: argparse.Namespace,
    case: MotCalibrationCase,
    *,
    camera_count: int,
) -> tuple[BlocksSmokeConfig, str, tuple[BlocksEpisodeSpec, ...]]:
    case_args = copy.copy(args)
    case_args.p1_mot_calibration_sweep = False
    case_args.cv_5v5 = True
    case_args.cv_5v5_d4d5_stress = False
    case_args.cv_5v5_d4d5_stress_200m = False
    case_args.actor_2v2 = False
    case_args.actor_5v5 = False
    case_args.drone_count = None
    case_args.resource_count = int(camera_count)
    case_args.target_count = int(camera_count)
    case_args.duration = float(case.frame_count) * 0.1
    case_args.dt = 0.1
    case_args.no_lidar = True
    case_args.detection_backend = "yolo"
    case_args.yolo_tracker_backend = case.tracker_backend
    case_args.yolo_confidence = float(case.confidence_threshold)
    case_args.no_yolo_native_tracker = False
    case_args.no_yolo_iou_fallback = True
    case_args.yolo_offline_truth_eval = True
    case_args.camera_width = int(case.camera_width)
    case_args.camera_height = int(case.camera_height)
    case_args.camera_fov = float(case.camera_fov_deg)
    case_args.secondary_count = 0
    case_args.actor_target_distance = float(case.target_distance_m)
    case_args.actor_target_spacing = 8.0
    case_args.actor_target_speed_scale = 0.6
    case_args.full_flow_only = False
    sequence_id = f"{args.sequence_id}_{case.case_id}"
    config, selected_sequence_id, _ = _build_sequence_run(
        case_args,
        seed=case.seed,
        sequence_id=sequence_id,
    )
    config = replace(
        config,
        duration_s=case_args.duration,
        dt_s=case_args.dt,
        include_integrated_pipeline=False,
        cv_camera_follow_assignments=False,
        target_actor_specs=tuple(
            replace(
                spec,
                velocity_ned=(
                    0.0,
                    (0.35 if index % 2 == 0 else -0.35),
                    0.0,
                ),
            )
            for index, spec in enumerate(config.target_actor_specs)
        ),
        metadata={
            **dict(config.metadata),
            **case.metadata(),
            "mot_calibration_case_id": case.case_id,
            "mot_target_distance_m": case.target_distance_m,
            "mot_admission_warmup_frames": case.warmup_frames,
            "mot_range_control": "fixed_camera_lateral_target_motion",
        },
    )
    episode = BlocksEpisodeSpec(
        episode_id=f"episode_{case.case_id}",
        focus="D5 native MOT calibration",
        scenario_name="blocks_cv_native_mot_calibration",
        duration_s=case_args.duration,
        dt_s=case_args.dt,
        include_integrated_pipeline=False,
        metadata=case.metadata(),
    )
    return config, selected_sequence_id, (episode,)


def _native_mot_rows_from_results(
    cases: tuple[MotCalibrationCase, ...],
    results: tuple[object, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for case, result in zip(cases, results, strict=True):
        for episode in getattr(result, "episode_results", ()):
            log_path = episode.output_paths.get("blocks_frames_jsonl")
            if log_path is None:
                continue
            summaries = _last_native_mot_summaries(Path(log_path))
            for summary in summaries:
                rows.append(
                    {
                        **case.metadata(),
                        **summary,
                        "tracker_backend": summary.get(
                            "requested_tracker_backend", case.tracker_backend
                        ),
                        "detector_precision": summary.get("offline_detector_precision"),
                        "detector_recall": summary.get("offline_detector_recall"),
                        "local_track_continuity": summary.get("local_continuity"),
                        "online_truth_use_count": 0,
                        "connected": bool(getattr(result, "connected", False)),
                    }
                )
    return rows


def _last_native_mot_summaries(path: Path) -> list[dict[str, object]]:
    last: dict[str, object] | None = None
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                last = json.loads(line)
    if not last:
        return []
    metadata = last.get("metadata") or {}
    if not isinstance(metadata, dict):
        return []
    summaries = metadata.get("native_mot_admission") or []
    return [dict(item) for item in summaries if isinstance(item, dict)]


def _native_mot_markdown(payload: dict[str, object]) -> str:
    rows = payload.get("rows") or []
    admission = payload.get("admission") or []
    admitted = sum(
        1 for item in admission if isinstance(item, dict) and item.get("admitted")
    )
    selected = payload.get("selected_thresholds") or {}
    return "\n".join(
        [
            "# P1 原生 MOT AirSim 标定报告",
            "",
            "## 配置",
            "",
            f"- 筛选工况数：{payload.get('screening_case_count', 0)}",
            f"- 双相机确认工况数：{payload.get('confirmation_case_count', 0)}",
            f"- 结果行数：{len(rows)}",
            f"- 通过准入行数：{admitted}",
            f"- ByteTrack 阈值：{selected.get('bytetrack', '未选出')}",
            f"- BoT-SORT 阈值：{selected.get('botsort', '未选出')}",
            "- IoU fallback：禁止作为真实 MOT 准入结果。",
            "- AirSim actor/truth ID：仅在在线跟踪完成后用于离线评分。",
            "",
            "## 判定",
            "",
            "只有原生激活率、检测精确率/召回率、局部连续性、ID Switch 和 P95 延时全部满足门限，候选后端才可进入主线评审；本脚本不会自动替换默认 detect/GNN 路径。",
            "",
        ]
    )


def _run_p1_calibration_sweep(args: argparse.Namespace) -> int:
    """Run a D4/D5 geometry calibration matrix from main-owned runtime code."""

    if args.actor_2v2 or args.actor_5v5 or args.cv_5v5:
        raise SystemExit("--p1-calibration-sweep cannot be combined with actor or generic CV modes")
    seeds = _parse_batch_seeds(args.batch_seeds, default=args.seed)
    heights = _parse_float_list(args.p1_secondary_heights, option_name="--p1-secondary-heights")
    fovs = _parse_float_list(args.p1_secondary_fovs, option_name="--p1-secondary-fovs")
    secondary_counts = _parse_int_list(args.p1_secondary_counts, option_name="--p1-secondary-counts")
    standoffs = _parse_float_list(args.p1_secondary_standoffs, option_name="--p1-secondary-standoffs")
    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    all_results: list[object] = []
    calibration_rows: list[dict[str, object]] = []
    combo_count = 0

    for height in heights:
        for fov in fovs:
            for secondary_count in secondary_counts:
                for standoff in standoffs:
                    combo_count += 1
                    combo_args = copy.copy(args)
                    combo_args.cv_5v5_d4d5_stress = True
                    combo_args.cv_5v5_d4d5_stress_200m = abs(float(height) - 200.0) < 1e-6
                    combo_args.mobile_secondary_recon = True
                    combo_args.drone_count = args.drone_count if args.drone_count is not None else 5
                    combo_args.secondary_height_above_targets = float(height)
                    combo_args.secondary_fov = float(fov)
                    combo_args.secondary_count = int(secondary_count)
                    combo_args.secondary_recon_standoff = float(standoff)
                    if combo_args.secondary_width is None:
                        combo_args.secondary_width = 1920
                    if combo_args.secondary_height is None:
                        combo_args.secondary_height = 1080
                    combo_args.sequence_id = (
                        f"{args.sequence_id}_h{_token(height)}_f{_token(fov)}"
                        f"_sec{secondary_count}_st{_token(standoff)}"
                    )
                    if len(seeds) == 1:
                        base_config, selected_sequence_id, episode_specs = _with_p1_calibration_metadata(
                            _build_sequence_run(
                                combo_args,
                                seed=seeds[0],
                                sequence_id=combo_args.sequence_id,
                            ),
                            height_m=float(height),
                            fov_deg=float(fov),
                            secondary_count=int(secondary_count),
                            standoff_m=float(standoff),
                        )
                        combo_results = [
                            run_blocks_sequence(
                                base_config,
                                sequence_id=selected_sequence_id,
                                episode_specs=episode_specs,
                            )
                        ]
                    else:
                        runs = tuple(
                            _with_p1_calibration_metadata(
                                _build_sequence_run(
                                    combo_args,
                                    seed=seed,
                                    sequence_id=f"{combo_args.sequence_id}_seed{seed:03d}",
                                ),
                                height_m=float(height),
                                fov_deg=float(fov),
                                secondary_count=int(secondary_count),
                                standoff_m=float(standoff),
                            )
                            for seed in seeds
                        )
                        combo_results = list(
                            run_blocks_batch_sequences(runs, batch_id=combo_args.sequence_id)
                        )
                    all_results.extend(combo_results)
                    calibration_rows.extend(
                        _d4d5_calibration_rows(
                            combo_results,
                            height_m=float(height),
                            fov_deg=float(fov),
                            secondary_count=int(secondary_count),
                            standoff_m=float(standoff),
                        )
                    )
                    for result in combo_results:
                        _print_sequence_result(result)

    report_paths = _write_p1_calibration_sweep_outputs(
        output_dir,
        args=args,
        seeds=seeds,
        combo_count=combo_count,
        rows=calibration_rows,
        results=all_results,
    )
    print(f"p1_calibration_summary={report_paths['json'].resolve()}")
    print(f"p1_calibration_report={report_paths['markdown'].resolve()}")
    if "d6_markdown" in report_paths:
        print(f"d6_calibration_report={report_paths['d6_markdown'].resolve()}")
    return 0


def _with_p1_calibration_metadata(
    run: tuple[BlocksSmokeConfig, str, tuple[BlocksEpisodeSpec, ...]],
    *,
    height_m: float,
    fov_deg: float,
    secondary_count: int,
    standoff_m: float,
):
    base_config, sequence_id, episode_specs = run
    metadata = {
        **dict(base_config.metadata),
        "calibration_suite": "cv_5v5_d4d5_secondary_coverage",
        "calibration_suite_version": P1_CALIBRATION_SUITE_VERSION,
        "threshold_version": P1_CALIBRATION_THRESHOLD_VERSION,
        "p1_secondary_height_m": float(height_m),
        "p1_secondary_fov_deg": float(fov_deg),
        "p1_secondary_count": int(secondary_count),
        "p1_secondary_standoff_m": float(standoff_m),
        "p1_calibration_dimensions": [
            "secondary_height_m",
            "secondary_fov_deg",
            "secondary_count",
            "secondary_standoff_m",
            "seed",
            "d4d5_case",
        ],
        "p1_expected_state_fields": [
            "d3_plan_version",
            "d4_action",
            "d5_decision_state",
            "d7_guidance_mode",
            "secondary_capability_class",
            "active_degradation_review_label",
        ],
    }
    return replace(base_config, metadata=metadata), sequence_id, episode_specs


def _parse_float_list(raw: str, *, option_name: str) -> list[float]:
    values: list[float] = []
    for item in raw.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        values.append(float(stripped))
    if not values:
        raise SystemExit(f"{option_name} did not contain any numeric values")
    return values


def _parse_int_list(raw: str, *, option_name: str) -> list[int]:
    values: list[int] = []
    for item in raw.split(","):
        stripped = item.strip()
        if not stripped:
            continue
        values.append(int(stripped))
    if not values:
        raise SystemExit(f"{option_name} did not contain any integer values")
    if any(value <= 0 for value in values):
        raise SystemExit(f"{option_name} values must be positive")
    return values


def _token(value: float | int) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")


def _d4d5_calibration_rows(
    results: list[object],
    *,
    height_m: float,
    fov_deg: float,
    secondary_count: int,
    standoff_m: float,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in results:
        seed = None
        for episode in getattr(result, "episode_results", ()):
            metrics = episode.metadata.get("d4d5_stress")
            if not metrics:
                continue
            if seed is None:
                seed = _seed_from_sequence_id(str(result.sequence_id))
            rows.append(
                {
                    "calibration_suite": "cv_5v5_d4d5_secondary_coverage",
                    "calibration_suite_version": P1_CALIBRATION_SUITE_VERSION,
                    "threshold_version": P1_CALIBRATION_THRESHOLD_VERSION,
                    "sequence_id": result.sequence_id,
                    "seed": seed,
                    "case_name": metrics.get("case_name"),
                    "connected": bool(result.connected),
                    "height_m": height_m,
                    "fov_deg": fov_deg,
                    "secondary_count": secondary_count,
                    "standoff_m": standoff_m,
                    "d4_action": metrics.get("dominant_d4_action"),
                    "secondary_network_joint_full_view_frame_rate": metrics.get(
                        "secondary_network_joint_full_view_frame_rate", 0.0
                    ),
                    "secondary_network_mean_coverage_ratio": metrics.get(
                        "secondary_network_mean_coverage_ratio", 0.0
                    ),
                    "secondary_single_camera_full_view_frame_rate": metrics.get(
                        "secondary_single_camera_full_view_frame_rate", 0.0
                    ),
                    "secondary_gimbal_pointing_ok_rate": metrics.get(
                        "secondary_gimbal_pointing_ok_rate", 0.0
                    ),
                    "cross_view_association_count": metrics.get("cross_view_association_count", 0),
                    "cross_view_conversion_gap": metrics.get("cross_view_conversion_gap", 0.0),
                    "projection_valid_rate": metrics.get("projection_valid_rate", 0.0),
                    "geometry_gate_pass_rate": metrics.get("geometry_gate_pass_rate", 0.0),
                    "registered_candidate_count": metrics.get("registered_candidate_count", 0),
                    "stable_cross_view_registration_count": metrics.get(
                        "stable_cross_view_registration_count",
                        0,
                    ),
                    "detect_to_global_candidate_count": metrics.get(
                        "detect_to_global_candidate_count",
                        0,
                    ),
                    "secondary_detect_available_but_not_registered": _first_present(
                        metrics,
                        "secondary_detect_available_but_not_registered_count",
                        "secondary_detect_available_but_not_registered",
                        default=0,
                    ),
                    "terminal_lock_accuracy": metrics.get("terminal_lock_accuracy", 0.0),
                    "bbox_mean_px2": (metrics.get("secondary_bbox_area_px_stats") or {}).get("mean", 0.0),
                    "top_reject_reason": _top_rejection_reason(
                        metrics.get("secondary_detect_to_cross_view_reject_reason_counts") or {}
                    ),
                }
            )
    return rows


def _write_p1_calibration_sweep_outputs(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    seeds: list[int],
    combo_count: int,
    rows: list[dict[str, object]],
    results: list[object],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "p1_calibration_sweep_summary.json"
    report_path = output_dir / "P1_AIRSIM_CALIBRATION_SWEEP_REPORT.md"
    payload = {
        "sequence_id": args.sequence_id,
        "calibration_suite": "cv_5v5_d4d5_secondary_coverage",
        "calibration_suite_version": P1_CALIBRATION_SUITE_VERSION,
        "threshold_version": P1_CALIBRATION_THRESHOLD_VERSION,
        "seed_count": len(seeds),
        "seeds": seeds,
        "combination_count": combo_count,
        "row_count": len(rows),
        "settings_strategy": "one_blocks_launch_per_geometry_combo_reset_loop_per_seed_batch",
        "results": [
            {
                "sequence_id": result.sequence_id,
                "connected": bool(result.connected),
                "episode_count": len(result.episode_results),
                "summary": str(result.output_paths.get("blocks_sequence_summary")),
            }
            for result in results
        ],
        "rows": rows,
        "aggregate": _aggregate_calibration_rows(rows),
        "height_comparison": _height_comparison(rows),
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(_p1_calibration_markdown(payload), encoding="utf-8")
    d6_outputs = _write_d6_p1_calibration_report(output_dir, summary_path, results)
    scenario_outputs = _write_runtime_scenario_library(
        output_dir / "scenario_library",
        seeds=seeds,
    )
    payload["d6_report_outputs"] = {key: str(path) for key, path in d6_outputs.items()}
    payload["scenario_library_outputs"] = {
        key: str(path) for key, path in scenario_outputs.items()
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    report_path.write_text(_p1_calibration_markdown(payload), encoding="utf-8")
    return {
        "json": summary_path,
        "markdown": report_path,
        **{f"d6_{key}": path for key, path in d6_outputs.items()},
        **{f"scenario_{key}": path for key, path in scenario_outputs.items()},
    }


def _write_runtime_scenario_library(
    output_dir: Path,
    *,
    seeds: list[int],
) -> dict[str, Path]:
    seed_tuple = tuple(dict.fromkeys(int(seed) for seed in seeds))
    library = ScenarioLibrary(
        (
            ScenarioDefinition(
                scenario_group="blocks_cv_5v5_secondary_takeover",
                scenario_version="p1-secondary-takeover-v2",
                tags=("5v5", "computer_vision", "secondary_takeover"),
                difficulty="stress",
                expected_failure_modes=(
                    "network_union_incomplete",
                    "secondary_readiness_not_sustained",
                    "secondary_plan_lease_expired",
                ),
                seeds=seed_tuple,
                parameters={"target_count": 5, "secondary_heights_m": [50, 200]},
            ),
            ScenarioDefinition(
                scenario_group="blocks_cv_5v5_yolo_mot",
                scenario_version="p1-yolo-mot-v1",
                tags=("5v5", "yolov8", "multicamera", "mot"),
                difficulty="challenging",
                expected_failure_modes=(
                    "detector_miss",
                    "local_id_discontinuity",
                    "cross_view_registration_rejected",
                ),
                seeds=seed_tuple,
                parameters={"tracker_backends": ["bytetrack", "botsort"]},
            ),
            ScenarioDefinition(
                scenario_group="blocks_actor_2v2_guidance_comparison",
                scenario_version="p1-guidance-four-law-v1",
                tags=("2v2", "simpleflight", "same_seed", "guidance"),
                difficulty="challenging",
                expected_failure_modes=(
                    "terminal_detection_acquisition_timeout",
                    "terminal_visual_lost_after_coast",
                    "maneuver_margin_low",
                    "bbox_near_image_edge",
                ),
                seeds=seed_tuple,
                parameters={
                    "guidance_laws": ["pure_pursuit", "radar_pn", "png_vm", "png_ttc"]
                },
            ),
            ScenarioDefinition(
                scenario_group="blocks_cv_5v5_d1_d3_governance",
                scenario_version="p1-d1-d3-governance-v1",
                tags=("5v5", "fusion", "association", "assignment"),
                difficulty="stress",
                expected_failure_modes=(
                    "oosm_latency",
                    "id_switch",
                    "false_track",
                    "unassigned_target",
                ),
                seeds=seed_tuple,
                parameters={"resource_target_scales": ["5v5", "3v5", "5v3"]},
            ),
        )
    )
    return library.write_bundle(output_dir)


def _write_d6_p1_calibration_report(
    output_dir: Path,
    summary_path: Path,
    results: list[object],
) -> dict[str, Path]:
    """Let D6 consume persisted AirSim artifacts and write its standard bundle."""

    input_paths: list[Path] = [summary_path]
    for result in results:
        result_summary = getattr(result, "output_paths", {}).get("blocks_sequence_summary")
        if result_summary is not None:
            input_paths.append(Path(result_summary))
    return AirSimCalibrationReportGenerator().write_report_bundle(
        input_paths,
        output_dir / "d6_airsim_calibration",
        title="D6 P1 AirSim 多 Seed 校准报告",
    )


def _aggregate_calibration_rows(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        return {}
    numeric_keys = (
        "secondary_network_joint_full_view_frame_rate",
        "secondary_network_mean_coverage_ratio",
        "secondary_single_camera_full_view_frame_rate",
        "secondary_gimbal_pointing_ok_rate",
        "cross_view_association_count",
        "cross_view_conversion_gap",
        "projection_valid_rate",
        "geometry_gate_pass_rate",
        "registered_candidate_count",
        "stable_cross_view_registration_count",
        "detect_to_global_candidate_count",
        "secondary_detect_available_but_not_registered",
        "terminal_lock_accuracy",
        "bbox_mean_px2",
    )
    aggregate: dict[str, object] = {"row_count": len(rows)}
    for key in numeric_keys:
        values = [_as_float(row.get(key)) for row in rows]
        aggregate[f"{key}_mean"] = sum(values) / len(values)
        aggregate[f"{key}_max"] = max(values)
        aggregate[f"{key}_min"] = min(values)
    by_case: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_case.setdefault(str(row.get("case_name")), []).append(row)
    aggregate["case_count"] = {case: len(case_rows) for case, case_rows in by_case.items()}
    aggregate["best_network_full_view"] = _best_row(
        rows,
        "secondary_network_joint_full_view_frame_rate",
    )
    aggregate["best_cross_view"] = _best_row(rows, "cross_view_association_count")
    return aggregate


def _height_comparison(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[float, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(_as_float(row.get("height_m")), []).append(row)
    comparison: list[dict[str, object]] = []
    metric_keys = (
        "secondary_network_joint_full_view_frame_rate",
        "secondary_network_mean_coverage_ratio",
        "secondary_single_camera_full_view_frame_rate",
        "projection_valid_rate",
        "geometry_gate_pass_rate",
        "stable_cross_view_registration_count",
        "cross_view_association_count",
        "secondary_detect_available_but_not_registered",
        "bbox_mean_px2",
    )
    for height_m, height_rows in sorted(grouped.items()):
        item: dict[str, object] = {
            "height_m": height_m,
            "row_count": len(height_rows),
            "case_count": len({str(row.get("case_name")) for row in height_rows}),
            "seed_count": len({str(row.get("seed")) for row in height_rows}),
        }
        for key in metric_keys:
            values = [_as_float(row.get(key)) for row in height_rows]
            item[f"{key}_mean"] = sum(values) / len(values) if values else 0.0
        comparison.append(item)
    return comparison


def _p1_calibration_markdown(payload: dict[str, object]) -> str:
    aggregate = payload.get("aggregate") or {}
    rows = payload.get("rows") or []
    height_comparison = payload.get("height_comparison") or []
    lines = [
        "# P1 AirSim 批量校准报告",
        "",
        "本报告由 main runtime 汇总生成。D1-D7 模块各自维护算法和指标，main 只负责 AirSim settings、episode 编排、日志收集和总表。",
        "",
        "## 配置",
        "",
        f"- Sequence ID: `{payload.get('sequence_id')}`",
        f"- Calibration suite: `{payload.get('calibration_suite')}`",
        f"- Suite version: `{payload.get('calibration_suite_version')}`",
        f"- Threshold version: `{payload.get('threshold_version')}`",
        f"- Seeds: `{', '.join(str(seed) for seed in payload.get('seeds', []))}`",
        f"- Geometry combinations: `{payload.get('combination_count')}`",
        f"- Result rows: `{payload.get('row_count')}`",
        f"- Settings strategy: `{payload.get('settings_strategy')}`",
        "",
        "## 总体指标",
        "",
        f"- 二级网络同帧全覆盖均值: `{_fmt(aggregate.get('secondary_network_joint_full_view_frame_rate_mean'))}`",
        f"- 二级网络覆盖率均值: `{_fmt(aggregate.get('secondary_network_mean_coverage_ratio_mean'))}`",
        f"- cross-view association 均值: `{_fmt(aggregate.get('cross_view_association_count_mean'))}`",
        f"- 投影有效率均值: `{_fmt(aggregate.get('projection_valid_rate_mean'))}`",
        f"- 几何门通过率均值: `{_fmt(aggregate.get('geometry_gate_pass_rate_mean'))}`",
        f"- 稳定跨视角注册均值: `{_fmt(aggregate.get('stable_cross_view_registration_count_mean'))}`",
        f"- detect 未注册均值: `{_fmt(aggregate.get('secondary_detect_available_but_not_registered_mean'))}`",
        f"- 云台指向 OK 均值: `{_fmt(aggregate.get('secondary_gimbal_pointing_ok_rate_mean'))}`",
        "",
        "## 高度对比",
        "",
        "| Height | Rows | Seeds | NetworkFullMean | NetworkMeanCoverage | ProjValid | GatePass | StableReg | CrossView | NotRegistered | BBoxMean |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in height_comparison if isinstance(height_comparison, list) else []:
        lines.append(
            "| "
            f"{_fmt(row.get('height_m'))} | "
            f"{row.get('row_count')} | "
            f"{row.get('seed_count')} | "
            f"{_fmt(row.get('secondary_network_joint_full_view_frame_rate_mean'))} | "
            f"{_fmt(row.get('secondary_network_mean_coverage_ratio_mean'))} | "
            f"{_fmt(row.get('projection_valid_rate_mean'))} | "
            f"{_fmt(row.get('geometry_gate_pass_rate_mean'))} | "
            f"{_fmt(row.get('stable_cross_view_registration_count_mean'))} | "
            f"{_fmt(row.get('cross_view_association_count_mean'))} | "
            f"{_fmt(row.get('secondary_detect_available_but_not_registered_mean'))} | "
            f"{_fmt(row.get('bbox_mean_px2_mean'))} |"
        )
    lines.extend(
        [
            "",
        "## 分组合结果",
        "",
        "| Height | FOV | Sec | Standoff | Case | Action | NetworkFull | NetworkMean | ProjValid | GatePass | StableReg | CrossView | NotRegistered | BBoxMean | TopReject |",
        "| ---: | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            f"{_fmt(row.get('height_m'))} | "
            f"{_fmt(row.get('fov_deg'))} | "
            f"{row.get('secondary_count')} | "
            f"{_fmt(row.get('standoff_m'))} | "
            f"{row.get('case_name')} | "
            f"{row.get('d4_action')} | "
            f"{_fmt(row.get('secondary_network_joint_full_view_frame_rate'))} | "
            f"{_fmt(row.get('secondary_network_mean_coverage_ratio'))} | "
            f"{_fmt(row.get('projection_valid_rate'))} | "
            f"{_fmt(row.get('geometry_gate_pass_rate'))} | "
            f"{row.get('stable_cross_view_registration_count')} | "
            f"{row.get('cross_view_association_count')} | "
            f"{row.get('secondary_detect_available_but_not_registered')} | "
            f"{_fmt(row.get('bbox_mean_px2'))} | "
            f"{row.get('top_reject_reason') or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 判读口径",
            "",
            "- `NetworkFull` 是二级网络同帧目标并集全覆盖，不等同于 D5 已配准成功。",
            "- `CrossView` 才表示 D5 形成了可供 D4/D6 消费的跨视角支持。",
            "- `NotRegistered` 高说明二级相机看到了目标，但还没有通过几何/绑定/时间戳门控注册到既有 `global_track_id`。",
            "- 视觉 PNG 仍必须满足 D3 当前 plan、D4 action allowed、D5 locked 且 ID 一致。",
            "",
        ]
    )
    d6_outputs = payload.get("d6_report_outputs") or {}
    if isinstance(d6_outputs, dict) and d6_outputs:
        lines.extend(
            [
                "## D6 标准报告输出",
                "",
                f"- Records CSV: `{d6_outputs.get('record_csv')}`",
                f"- Summary CSV: `{d6_outputs.get('summary_csv')}`",
                f"- Summary JSON: `{d6_outputs.get('summary_json')}`",
                f"- Markdown: `{d6_outputs.get('markdown')}`",
                "",
            ]
        )
    return "\n".join(lines)


def _seed_from_sequence_id(sequence_id: str) -> int | None:
    marker = "_seed"
    if marker not in sequence_id:
        return None
    tail = sequence_id.rsplit(marker, 1)[-1]
    digits = "".join(ch for ch in tail if ch.isdigit())
    return int(digits) if digits else None


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _best_row(rows: list[dict[str, object]], key: str) -> dict[str, object]:
    return dict(max(rows, key=lambda row: _as_float(row.get(key))))


def _top_rejection_reason(reject_counts: dict[str, object]) -> str:
    if not reject_counts:
        return ""
    ranked = [
        (reason, count)
        for reason, count in reject_counts.items()
        if str(reason) != "registered_to_global_track" and _as_float(count) > 0.0
    ]
    if not ranked:
        return ""
    reason, _ = max(ranked, key=lambda item: _as_float(item[1]))
    return str(reason)


def _first_present(mapping: dict[str, object], *keys: str, default: object = None) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


def _write_batch_summary(args: argparse.Namespace, seeds: list[int], results: list[object]) -> Path:
    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "blocks_batch_summary.json"
    payload = {
        "sequence_id": args.sequence_id,
        "batch_mode": "single_blocks_reset_loop",
        "seed_count": len(seeds),
        "seeds": seeds,
        "results": [
            {
                "sequence_id": result.sequence_id,
                "connected": result.connected,
                "episode_count": len(result.episode_results),
                "summary": str(result.output_paths["blocks_sequence_summary"]),
            }
            for result in results
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    report = output_dir / "BATCH_AIRSIM_REPORT.md"
    lines = [
        "# AirSim Batch Report",
        "",
        f"- Sequence prefix: `{args.sequence_id}`",
        "- Batch mode: `single_blocks_reset_loop`",
        f"- Seed count: {len(seeds)}",
        f"- Seeds: {', '.join(str(seed) for seed in seeds)}",
        "",
        "| Run | Connected | Episodes | Summary |",
        "| --- | --- | ---: | --- |",
    ]
    for result in results:
        lines.append(
            f"| `{result.sequence_id}` | {result.connected} | {len(result.episode_results)} | "
            f"`{result.output_paths['blocks_sequence_summary']}` |"
        )
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_guidance_law_sweep_outputs(
    output_dir: Path,
    *,
    sequence_id: str,
    seeds: list[int],
    laws: tuple[str, ...],
    run_index: list[tuple[str, int]],
    results: list[object],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for (law, seed), result in zip(run_index, results, strict=False):
        episode = _controlled_episode_from_result(result)
        summary_path = None if episode is None else episode.output_paths.get("intercept_summary")
        commands_path = None if episode is None else episode.output_paths.get("control_commands")
        summary: dict[str, object] = {}
        if summary_path is not None and Path(summary_path).exists():
            summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
        pairs = list(summary.get("pairs", []) or [])
        min_ranges = [
            float(pair["min_range_m"])
            for pair in pairs
            if isinstance(pair, dict) and pair.get("min_range_m") is not None
        ]
        status_counts: dict[str, int] = {}
        for pair in pairs:
            if not isinstance(pair, dict):
                continue
            status = str(pair.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        command_law_counts: dict[str, int] = {}
        terminal_allowed_count = 0
        command_count = 0
        if commands_path is not None and Path(commands_path).exists():
            with Path(commands_path).open(encoding="utf-8", newline="") as stream:
                for command in csv.DictReader(stream):
                    command_count += 1
                    command_law = str(command.get("guidance_law") or "unknown")
                    command_law_counts[command_law] = command_law_counts.get(command_law, 0) + 1
                    if str(command.get("terminal_switch_allowed") or "").lower() == "true":
                        terminal_allowed_count += 1
        rows.append(
            {
                "sequence_id": result.sequence_id,
                "seed": seed,
                "guidance_law": law,
                "connected": bool(result.connected),
                "pair_count": int(summary.get("pair_count", len(pairs)) or 0),
                "success_count": int(summary.get("success_count", 0) or 0),
                "mean_min_range_m": (
                    sum(min_ranges) / len(min_ranges) if min_ranges else None
                ),
                "status_counts": status_counts,
                "command_count": command_count,
                "command_law_counts": command_law_counts,
                "terminal_switch_allowed_count": terminal_allowed_count,
                "terminal_switch_allowed_rate": (
                    terminal_allowed_count / command_count if command_count else None
                ),
                "intercept_summary": str(summary_path) if summary_path is not None else None,
                "control_commands": str(commands_path) if commands_path is not None else None,
            }
        )
    aggregates = []
    for law in laws:
        selected = [row for row in rows if row["guidance_law"] == law]
        pair_count = sum(int(row["pair_count"]) for row in selected)
        success_count = sum(int(row["success_count"]) for row in selected)
        min_ranges = [
            float(row["mean_min_range_m"])
            for row in selected
            if row["mean_min_range_m"] is not None
        ]
        aggregates.append(
            {
                "guidance_law": law,
                "seed_count": len(selected),
                "pair_count": pair_count,
                "success_count": success_count,
                "success_rate": success_count / pair_count if pair_count else None,
                "mean_min_range_m": sum(min_ranges) / len(min_ranges) if min_ranges else None,
            }
        )
    payload = {
        "sequence_id": sequence_id,
        "batch_mode": "single_blocks_reset_loop",
        "comparison_design": "same_seed_same_geometry",
        "seeds": seeds,
        "guidance_laws": list(laws),
        "rows": rows,
        "aggregates": aggregates,
    }
    json_path = output_dir / "guidance_law_sweep_summary.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_path = output_dir / "GUIDANCE_LAW_SWEEP_REPORT.md"
    lines = [
        "# AirSim 四导引律同 Seed 对照报告",
        "",
        f"- Sequence: `{sequence_id}`",
        "- 运行方式：单次启动 Blocks，按导引律和 seed 重置场景。",
        f"- Seeds: `{', '.join(str(seed) for seed in seeds)}`",
        "- PNG 核心算法未在 main runtime 中修改。",
        "",
        "| 导引律 | Seeds | Pair | 成功 | 成功率 | 平均最小距离 m |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in aggregates:
        success_rate = row["success_rate"]
        mean_range = row["mean_min_range_m"]
        lines.append(
            f"| `{row['guidance_law']}` | {row['seed_count']} | {row['pair_count']} | "
            f"{row['success_count']} | "
            f"{'unavailable' if success_rate is None else f'{float(success_rate):.3f}'} | "
            f"{'unavailable' if mean_range is None else f'{float(mean_range):.3f}'} |"
        )
    lines.extend(
        [
            "",
            "## 口径",
            "",
            "- `pure_pursuit` 和 `radar_pn` 不启用视觉接管。",
            "- `png_vm` 和 `png_ttc` 仅在 D3/D4/D5 合同及视觉质量门限全部通过后切换。",
            "- 本文件是 main 侧执行索引；置信区间、拒绝原因和图表由 D6 bundle 给出。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    episode_metrics = []
    for (law, _seed), result in zip(run_index, results, strict=False):
        episode = _controlled_episode_from_result(result)
        metrics_path = (
            None
            if episode is None
            else episode.output_paths.get("main_episode_bus_metrics_json")
        )
        if metrics_path is not None and Path(metrics_path).exists():
            metrics = load_main_episode_bus_metrics(metrics_path)
            metrics.metadata["experiment_guidance_law"] = law
            metrics.metadata["selected_guidance_law"] = law
            metrics.metadata["guidance_comparison_group"] = sequence_id
            episode_metrics.append(metrics)
    d6_paths = GuidanceLawComparisonReportGenerator().write_bundle(
        episode_metrics,
        output_dir / "d6_guidance_comparison",
        reference_law="radar_pn",
    )
    return {
        "json": json_path,
        "markdown": report_path,
        **{f"d6_{key}": value for key, value in d6_paths.items()},
    }


def _write_5v5_intercept_report(args: argparse.Namespace, results: list[object]) -> Path:
    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "P1_5V5_INTERCEPT_AIRSIM_REPORT_20260703.md"
    lines = [
        "# P1 5v5 AirSim 真拦截测试报告",
        "",
        "## 测试配置",
        "",
        f"- Sequence ID: `{args.sequence_id}`",
        "- Runtime: Blocks + SimpleFlight interceptors + moved actor targets",
        f"- Target detection: {_target_detection_report_line(args)}",
        f"- Duration: `{args.duration}` s, dt: `{args.dt}` s, control dt: `{args.control_dt}` s",
        f"- Intercept speed: `{args.intercept_speed}` m/s",
        f"- Intercept altitude NED Z: `{args.intercept_altitude_z}` m",
        f"- Intercept radius: `{args.intercept_radius}` m",
        f"- Terminal switch range: `{args.intercept_terminal_range}` m",
        f"- Actor target distance: `{args.actor_target_distance if args.actor_target_distance is not None else 35.0}` m",
        f"- Actor target spacing: `{args.actor_target_spacing if args.actor_target_spacing is not None else 10.0}` m",
        f"- Actor target speed scale: `{args.actor_target_speed_scale}`",
        f"- Active center replan: `{bool(args.actor_5v5_active_center_replan)}`",
        f"- Active degradation time: `{args.active_degradation_time}` s",
        f"- Center replan time: `{args.center_replan_time}` s",
        "",
        "## 结果汇总",
        "",
        "| Sequence | Connected | Pair Count | Success | Command Records | Center Replan Events | Summary |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for result in results:
        episode = _controlled_episode_from_result(result)
        intercept = {} if episode is None else episode.metadata.get("intercept", {})
        output_paths = {} if episode is None else episode.output_paths
        summary_path = output_paths.get("intercept_summary")
        center_events_path = output_paths.get("center_replan_events")
        lines.append(
            f"| `{result.sequence_id}` | {result.connected} | "
            f"{intercept.get('pair_count', 0)} | {intercept.get('success_count', 0)} | "
            f"{intercept.get('command_record_count', 0)} | "
            f"`{center_events_path}` | "
            f"`{summary_path}` |"
        )
    lines.extend(["", "## 分 pair 状态", "", "| Resource | Vehicle | Target | Status | Min Range m | Time s | D4 | D5 | Plan | PNG Reject | Abort |", "| --- | --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- |"])
    for result in results:
        episode = _controlled_episode_from_result(result)
        if episode is None:
            continue
        summary_path = episode.output_paths.get("intercept_summary")
        if summary_path is None or not Path(summary_path).exists():
            continue
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
        for pair in summary.get("pairs", []) or []:
            lines.append(
                "| "
                f"{pair.get('resource_id', '')} | "
                f"{pair.get('vehicle_name', '')} | "
                f"{pair.get('target_id', '')} | "
                f"{pair.get('status', '')} | "
                f"{_fmt(pair.get('min_range_m'))} | "
                f"{_fmt(pair.get('time_to_intercept_s'))} | "
                f"{pair.get('d4_action', '')} | "
                f"{pair.get('d5_decision_state', '')} | "
                f"{pair.get('plan_id', '')}/v{pair.get('plan_version', '')} | "
                f"{pair.get('terminal_contract_reject_reason') or pair.get('terminal_switch_reject_reason') or ''} | "
                f"{pair.get('abort_reason') or ''} |"
            )
    lines.extend(["", "## D6 / D7 指标文件", ""])
    for result in results:
        episode = _controlled_episode_from_result(result)
        if episode is None:
            continue
        paths = episode.output_paths
        integrated_paths = {}
        if episode.integrated_result is not None:
            integrated_paths = episode.integrated_result.output_paths
        lines.extend(
            [
                f"- `{result.sequence_id}` control commands: `{paths.get('control_commands')}`",
                f"- `{result.sequence_id}` intercept summary: `{paths.get('intercept_summary')}`",
                f"- `{result.sequence_id}` center replan events: `{paths.get('center_replan_events')}`",
                f"- `{result.sequence_id}` D6 merged metrics: `{integrated_paths.get('d7_execution_metrics')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 结论口径",
            "",
            "- `collision_intercept` 和 `range_intercept` 计为闭环成功。",
            "- `timeout` 表示 SimpleFlight 控制和日志链路完成，但在最大时长内未达到拦截半径或碰撞判据。",
            "- `terminal_switch_allowed`、`terminal_contract_reject_reason` 和 `guidance_law` 以 `control_commands.csv` 为准。",
            "- 本报告只汇总执行结果；完整探测、关联、分配、降级和末端指标以集成 D6 报告为准。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _write_2v2_active_secondary_report(args: argparse.Namespace, results: list[object]) -> Path:
    output_dir = Path(args.output_root) / args.sequence_id
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "P1_2V2_ACTIVE_SECONDARY_VISUAL_PNG_REPORT_20260703.md"
    lines = [
        "# P1 2v2 主动降级-二级重分配-视觉 PNG AirSim 报告",
        "",
        "## 测试配置",
        "",
        f"- Sequence ID: `{args.sequence_id}`",
        "- Runtime: Blocks + SimpleFlight interceptors + moved actor targets",
        f"- Target detection: {_target_detection_report_line(args)}",
        "- Flow: center plan -> D4 active degradation -> secondary plan v2 -> D5 locked -> D7 visual PNG",
        f"- Active degradation time: `{args.active_degradation_time}` s",
        f"- Secondary plan time: `{args.secondary_plan_time}` s",
        f"- Terminal switch range: `{args.intercept_terminal_range}` m",
        f"- Intercept speed: `{args.intercept_speed}` m/s",
        f"- Target asset: `{args.target_asset_name}`",
        "",
        "## 结果汇总",
        "",
        "| Sequence | Connected | Pair Count | Success | PNG Switch | D4 Pending | Secondary Plan | Summary |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for result in results:
        episode = _controlled_episode_from_result(result)
        intercept = {} if episode is None else episode.metadata.get("intercept", {})
        integrated = {} if episode is None or episode.integrated_result is None else episode.integrated_result.metrics
        metadata = integrated.get("metadata", {}) if isinstance(integrated, dict) else {}
        output_paths = {} if episode is None else episode.output_paths
        lines.append(
            f"| `{result.sequence_id}` | {result.connected} | "
            f"{intercept.get('pair_count', 0)} | {intercept.get('success_count', 0)} | "
            f"{integrated.get('visual_png_switch_count', 0) if isinstance(integrated, dict) else 0} | "
            f"{integrated.get('d4_reassign_pending_count', 0) if isinstance(integrated, dict) else 0} | "
            f"{'secondary_plan_v2' if 'secondary_plan_v2' in metadata.get('plan_ids', []) else '-'} | "
            f"`{output_paths.get('intercept_summary')}` |"
        )
    lines.extend(["", "## 分 pair 状态", "", "| Resource | Vehicle | Target | Status | Min Range m | D4 | D5 | Plan | PNG Reject |", "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |"])
    for result in results:
        episode = _controlled_episode_from_result(result)
        if episode is None:
            continue
        summary_path = episode.output_paths.get("intercept_summary")
        if summary_path is None or not Path(summary_path).exists():
            continue
        summary = json.loads(Path(summary_path).read_text(encoding="utf-8"))
        for pair in summary.get("pairs", []) or []:
            lines.append(
                "| "
                f"{pair.get('resource_id', '')} | "
                f"{pair.get('vehicle_name', '')} | "
                f"{pair.get('target_id', '')} | "
                f"{pair.get('status', '')} | "
                f"{_fmt(pair.get('min_range_m'))} | "
                f"{pair.get('d4_action', '')} | "
                f"{pair.get('d5_decision_state', '')} | "
                f"{pair.get('plan_id', '')}/v{pair.get('plan_version', '')} | "
                f"{pair.get('terminal_contract_reject_reason') or pair.get('terminal_switch_reject_reason') or ''} |"
            )
    lines.extend(["", "## 输出文件", ""])
    for result in results:
        episode = _controlled_episode_from_result(result)
        if episode is None:
            continue
        integrated_paths = {} if episode.integrated_result is None else episode.integrated_result.output_paths
        lines.extend(
            [
                f"- `{result.sequence_id}` control commands: `{episode.output_paths.get('control_commands')}`",
                f"- `{result.sequence_id}` secondary events: `{episode.output_paths.get('secondary_reassignment_events')}`",
                f"- `{result.sequence_id}` D6 merged metrics: `{integrated_paths.get('d7_execution_metrics')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## 验收口径",
            "",
            "- `degrade_to_secondary` 阶段应出现 `d4_reassign_pending`，此时 D7 不能进入视觉 PNG。",
            "- `secondary_plan_v2` 生效后，D5 `locked` 且计划一致时，D7 才允许 `guidance_law=png_vm`。",
            "- D5 只输出关联证据，不改写 `global_track_id`。",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def _controlled_episode_from_result(result: object):
    for episode in getattr(result, "episode_results", ()):
        if episode.metadata.get("control_api_used"):
            return episode
    return None


def _target_detection_report_line(args: argparse.Namespace) -> str:
    if getattr(args, "detection_backend", "airsim") == "yolo":
        return (
            "D5 YOLOv8 + MOT in-memory images, "
            f"weights `{args.yolo_weights}`, tracker `{args.yolo_tracker_backend}`, "
            "PNG not saved by default"
        )
    return "AirSim `simGetDetections` metadata, PNG not saved by default"


def _fmt(value: object) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
