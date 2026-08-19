#!/usr/bin/env python3
"""Main-owned serial orchestrator for the three independent experiments."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
for relative in (
    "research_modules",
    "research_modules/independent_experiments",
    "research_modules/d1_sensor_fusion/src",
    "research_modules/d2_data_association",
    "research_modules/d3_assignment_planner/src",
    "research_modules/d4_distributed_fallback",
    "research_modules/d5_terminal_association/src",
    "research_modules/d6_evaluation_metrics",
    "research_modules/d7_proportional_guidance",
):
    path = str(ROOT / relative)
    if path not in sys.path:
        sys.path.insert(0, path)

from center_terminal_cv_campaign.actor_controller import CampaignActorClientProxy  # noqa: E402
from center_terminal_cv_campaign.common.io import write_json, write_jsonl  # noqa: E402
from center_terminal_cv_campaign.common.airsim_settings import (  # noqa: E402
    CENTER_CAMERA_NAMES,
    CENTER_HORIZONTAL_FOV_DEG,
    INTERCEPTOR_HORIZONTAL_FOV_DEG,
    interceptor_camera_names,
)
from center_terminal_cv_campaign.common.scenario import TargetTruth  # noqa: E402
from center_terminal_cv_campaign.aggregate_report import aggregate_campaign  # noqa: E402
from center_terminal_cv_campaign.prepare_campaign import (  # noqa: E402
    DEFAULT_OUTPUT_ROOT,
    prepare_fixture,
)


EXPERIMENT_MODULES = {
    "search": "center_terminal_cv_campaign.exp_search.run_experiment",
    "center_handover": "center_terminal_cv_campaign.exp_center_handover.run_experiment",
    "crossview": "center_terminal_cv_campaign.exp_crossview.run_experiment",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-id", default="center_terminal_cv_smoke")
    parser.add_argument(
        "--target-count",
        type=int,
        default=5,
        help="positive multiple of five; required for exact 80/80 source fixtures",
    )
    parser.add_argument("--resource-count", type=int, default=8)
    parser.add_argument("--interceptor-capacity", type=int, default=40)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--mode", choices=("offline", "airsim"), default="offline")
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=tuple(EXPERIMENT_MODULES),
        default=list(EXPERIMENT_MODULES),
    )
    parser.add_argument(
        "--association-backend",
        choices=("geometry", "gnn"),
        default="geometry",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--blocks-script",
        type=Path,
        default=Path("Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"),
    )
    parser.add_argument("--api-port", type=int, default=41451)
    parser.add_argument("--connection-timeout-s", type=float, default=120.0)
    parser.add_argument("--no-launch", action="store_true")
    return parser.parse_args(argv)


def _validate_campaign_scale(args: argparse.Namespace) -> None:
    if args.target_count <= 0 or args.target_count % 5:
        raise ValueError("target_count must be a positive multiple of five")
    if args.resource_count <= 0:
        raise ValueError("resource_count must be positive")
    required_capacity = max(args.target_count, args.resource_count)
    if args.interceptor_capacity < required_capacity:
        raise ValueError(
            "interceptor_capacity must cover both target-specific handover cameras "
            f"and active search resources; need {required_capacity}, got "
            f"{args.interceptor_capacity}"
        )


def build_experiment_command(
    *,
    experiment: str,
    fixture_dir: Path,
    output_dir: Path,
    mode: str,
    target_count: int,
    seed: int,
    api_port: int,
    resource_count: int,
    association_backend: str,
) -> list[str]:
    module = EXPERIMENT_MODULES[experiment]
    command = [
        sys.executable,
        "-m",
        module,
        "--fixture-dir",
        str(fixture_dir),
        "--output-dir",
        str(output_dir),
        "--mode",
        mode,
    ]
    if experiment == "search":
        command.extend(
            (
                "--target-count",
                str(target_count),
                "--seed",
                str(seed),
                "--api-port",
                str(api_port),
                "--resource-count",
                str(resource_count),
            )
        )
    elif experiment == "center_handover":
        command.extend(("--association-backend", association_backend))
    else:
        scenario = "partial_3cam_5target" if target_count == 5 else "dense_multicamera"
        command.extend(
            (
                "--association-backend",
                association_backend,
                "--scenario",
                scenario,
                "--target-count",
                str(target_count),
                "--seed",
                str(seed),
            )
        )
    return command


def _run_experiment_process(
    command: list[str],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    environment = os.environ.copy()
    python_path = [
        str(ROOT / "research_modules"),
        str(ROOT / "research_modules/independent_experiments"),
    ]
    if environment.get("PYTHONPATH"):
        python_path.append(environment["PYTHONPATH"])
    environment["PYTHONPATH"] = os.pathsep.join(python_path)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log_path = output_dir / "runner_stdout_stderr.log"
    log_path.write_text(completed.stdout or "", encoding="utf-8")
    return {
        "command": command,
        "returncode": completed.returncode,
        "wall_duration_s": time.monotonic() - started,
        "log_path": str(log_path),
        "metrics_path": str(output_dir / "metrics.json"),
        "report_path": str(output_dir / "REPORT_CN.md"),
    }


def _load_target_truth(path: Path) -> tuple[TargetTruth, ...]:
    return tuple(
        TargetTruth(**json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _configure_detection_filters(
    client: Any,
    airsim_module: Any,
    camera_ids: tuple[str, ...],
) -> None:
    image_type = airsim_module.ImageType.Scene
    for camera_id in camera_ids:
        client.simClearDetectionMeshNames("0", image_type, vehicle_name=camera_id)
        client.simSetDetectionFilterRadius(
            "0", image_type, 10_000_000.0, vehicle_name=camera_id
        )
        for pattern in ("MSM_TargetActor_*", "MSM_TargetActor*"):
            client.simAddDetectionFilterMeshName(
                "0", image_type, pattern, vehicle_name=camera_id
            )


def _pose_handover_cameras(
    client: Any,
    airsim_module: Any,
    camera_models: Any,
) -> tuple[str, ...]:
    camera_ids: list[str] = []
    for camera_id, model in camera_models.items():
        yaw, pitch, roll = model.body_yaw_pitch_roll_deg
        pose = airsim_module.Pose(
            airsim_module.Vector3r(*model.body_position_ned_m),
            airsim_module.to_quaternion(
                math.radians(pitch), math.radians(roll), math.radians(yaw)
            ),
        )
        result = client.simSetVehiclePose(
            pose,
            ignore_collision=True,
            vehicle_name=camera_id,
        )
        if result is False:
            raise RuntimeError(f"AirSim failed to pose handover camera {camera_id}")
        camera_ids.append(str(camera_id))
    return tuple(camera_ids)


def _run_airsim_experiment(
    *,
    experiment: str,
    fixture_dir: Path,
    common_fixture_dir: Path,
    output_dir: Path,
    runtime: Any,
    targets: tuple[TargetTruth, ...],
    target_count: int,
    seed: int,
    resource_count: int,
    association_backend: str,
) -> dict[str, Any]:
    """Run one episode against the main-owned client and actor time line."""

    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    proxy = CampaignActorClientProxy(runtime.client, runtime.airsim, targets)
    log_path = output_dir / "runner_stdout_stderr.log"
    metrics_path = output_dir / "metrics.json"
    report_path = output_dir / "REPORT_CN.md"
    try:
        proxy.setup_targets()
        if experiment == "search":
            from center_terminal_cv_campaign.exp_search.run_experiment import (
                run_experiment as run_search,
            )

            run_search(
                mode="airsim",
                fixture_dir=common_fixture_dir,
                output_dir=output_dir,
                target_count=target_count,
                resource_count=resource_count,
                seed=seed,
                client=proxy,
                airsim_module=runtime.airsim,
                assignment_cycles=3,
            )
        elif experiment == "center_handover":
            from center_terminal_cv_campaign.exp_center_handover.fixture import (
                load_handover_fixture,
            )
            from center_terminal_cv_campaign.exp_center_handover.run_experiment import (
                run as run_handover,
            )

            handover_fixture = load_handover_fixture(common_fixture_dir)
            camera_ids = _pose_handover_cameras(
                proxy, runtime.airsim, handover_fixture.camera_models
            )
            _configure_detection_filters(proxy, runtime.airsim, camera_ids)
            frame_timestamps = (0.2, 0.3, 0.4, 0.5, 0.6)
            proxy.set_logical_time(frame_timestamps[0])
            result = run_handover(
                fixture_dir=common_fixture_dir,
                output_dir=output_dir,
                mode="airsim",
                association_backend=association_backend,
                airsim_client=proxy,
                frame_timestamps=frame_timestamps,
                frame_delay_s=0.0,
                frame_advance=proxy.set_handover_frame,
            )
            metrics_path = result.paths.metrics
            report_path = result.paths.report
        elif experiment == "crossview":
            from center_terminal_cv_campaign.exp_crossview.run_experiment import (
                run as run_crossview,
            )

            result = run_crossview(
                fixture_dir=fixture_dir,
                output_dir=output_dir,
                mode="airsim",
                association_backend=association_backend,
                client=proxy,
                image_type=runtime.airsim.ImageType.Scene,
                seed=seed,
                target_count=target_count,
                scenario_name=(
                    "partial_3cam_5target"
                    if target_count == 5
                    else "dense_multicamera"
                ),
                frame_advance=proxy.set_crossview_frame,
                actor_name_to_truth_target={
                    target.actor_name: target.truth_target_id for target in targets
                },
                actor_name_aliases=proxy.requested_name_by_actual,
            )
            metrics_path = result.metrics_path
            report_path = result.report_path
        else:  # pragma: no cover - argparse prevents this
            raise ValueError(f"unknown experiment: {experiment}")
        log_path.write_text(
            f"mode=airsim\nexperiment={experiment}\nstatus=completed\n",
            encoding="utf-8",
        )
        returncode = 0
    except Exception:
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        returncode = 1
    finally:
        write_json(output_dir / "truth" / "actor_audit.json", proxy.actor_audit())
        write_jsonl(
            output_dir / "truth" / "actor_motion.jsonl",
            proxy.motion_rows,
        )
        proxy.teardown_targets()
    return {
        "command": ["in_process", experiment],
        "returncode": returncode,
        "wall_duration_s": time.monotonic() - started,
        "log_path": str(log_path),
        "metrics_path": str(metrics_path),
        "report_path": str(report_path),
    }


def _apply_and_audit_camera_fov(
    runtime: Any,
    *,
    interceptor_capacity: int,
    output_path: Path,
) -> Path:
    """Apply FOV through the API because Blocks 1.8 reports 90 deg after settings load."""

    commands: list[dict[str, Any]] = []
    expected = {
        **{name: CENTER_HORIZONTAL_FOV_DEG for name in CENTER_CAMERA_NAMES},
        **{
            name: INTERCEPTOR_HORIZONTAL_FOV_DEG
            for name in interceptor_camera_names(interceptor_capacity)
        },
    }
    for vehicle_name, requested_fov in expected.items():
        command = runtime.set_cv_camera_fov(
            vehicle_name=vehicle_name,
            camera_name="0",
            horizontal_fov_deg=requested_fov,
        )
        info = runtime.client.simGetCameraInfo("0", vehicle_name=vehicle_name)
        command["reported_fov_deg"] = float(info.fov)
        command["fov_verified"] = abs(float(info.fov) - requested_fov) <= 0.1
        commands.append(command)
    payload = {
        "schema_version": "center-terminal-camera-profile-audit-v1",
        "all_verified": all(item["ok"] and item["fov_verified"] for item in commands),
        "commands": commands,
    }
    write_json(output_path, payload)
    if not payload["all_verified"]:
        failed = [item["vehicle_name"] for item in commands if not item["fov_verified"]]
        raise RuntimeError(f"AirSim camera FOV verification failed: {failed}")
    return output_path


def run_campaign(args: argparse.Namespace) -> Path:
    _validate_campaign_scale(args)
    campaign_dir = args.output_root / args.campaign_id
    fixture_paths = prepare_fixture(
        output_root=campaign_dir / "fixtures",
        target_count=args.target_count,
        seed=args.seed,
        interceptor_count=args.interceptor_capacity,
        resource_count=args.resource_count,
        api_port=args.api_port,
    )
    fixture_dir = fixture_paths["fixture_dir"]
    targets = _load_target_truth(fixture_paths["target_truth"])
    process_manager: Any | None = None
    runtime: Any | None = None
    launched = args.mode == "airsim" and not args.no_launch
    if args.mode == "airsim":
        from airsim_runtime.blocks import BlocksProcessManager
        from airsim_runtime.real_runtime import RealAirSimRuntimeClient

        process_manager = BlocksProcessManager(
            blocks_script=args.blocks_script,
            settings_path=fixture_paths["settings"],
            output_dir=campaign_dir / "blocks_process",
            extra_args=(
                "-windowed",
                "-ResX=1280",
                "-ResY=720",
                "-NoVSync",
                "-NoHMD",
                "-NoSound",
            ),
        )
        runtime = RealAirSimRuntimeClient(
            ip="127.0.0.1",
            port=args.api_port,
            timeout_value=10.0,
            client_kind="vehicle",
        )
        if launched:
            process_manager.start()
        runtime.wait_for_connection(args.connection_timeout_s)
        _apply_and_audit_camera_fov(
            runtime,
            interceptor_capacity=args.interceptor_capacity,
            output_path=campaign_dir / "blocks_process" / "initial_camera_profile_audit.json",
        )

    results: dict[str, Any] = {}
    try:
        for experiment in args.experiments:
            if runtime is not None:
                runtime.reset()
                runtime.wait_for_connection(args.connection_timeout_s)
                _apply_and_audit_camera_fov(
                    runtime,
                    interceptor_capacity=args.interceptor_capacity,
                    output_path=campaign_dir
                    / "blocks_process"
                    / f"{experiment}_camera_profile_audit.json",
                )
            output_dir = campaign_dir / experiment
            experiment_fixture_dir = (
                fixture_paths["crossview_fixture_dir"]
                if experiment == "crossview"
                else fixture_dir
            )
            if runtime is None:
                command = build_experiment_command(
                    experiment=experiment,
                    fixture_dir=experiment_fixture_dir,
                    output_dir=output_dir,
                    mode=args.mode,
                    target_count=args.target_count,
                    seed=args.seed,
                    api_port=args.api_port,
                    resource_count=args.resource_count,
                    association_backend=args.association_backend,
                )
                result = _run_experiment_process(command, output_dir=output_dir)
            else:
                result = _run_airsim_experiment(
                    experiment=experiment,
                    fixture_dir=experiment_fixture_dir,
                    common_fixture_dir=fixture_dir,
                    output_dir=output_dir,
                    runtime=runtime,
                    targets=targets,
                    target_count=args.target_count,
                    seed=args.seed,
                    resource_count=args.resource_count,
                    association_backend=args.association_backend,
                )
            results[experiment] = result
            if result["returncode"] != 0:
                raise RuntimeError(
                    f"{experiment} failed with return code {result['returncode']}; "
                    f"see {result['log_path']}"
                )
    finally:
        if process_manager is not None:
            process_manager.write_diagnostics()
            if launched:
                process_manager.stop()

    summary_payload = {
        "schema_version": "center-terminal-campaign-summary-v1",
        "campaign_id": args.campaign_id,
        "mode": args.mode,
        "target_count": args.target_count,
        "resource_count": args.resource_count,
        "seed": args.seed,
        "recognition_rule": "bbox_longest_side_px_gte_10",
        "source_precision": 0.8,
        "source_recall": 0.8,
        "fixture_manifest": str(fixture_paths["manifest"]),
        "experiments": results,
        "all_passed": all(item["returncode"] == 0 for item in results.values()),
    }
    summary_path = write_json(campaign_dir / "campaign_summary.json", summary_payload)
    aggregate_paths = aggregate_campaign(campaign_dir)
    summary_payload.update(
        {
            "aggregate_report_path": str(aggregate_paths["report"]),
            "metric_inventory_path": str(aggregate_paths["metric_inventory"]),
        }
    )
    summary_path = write_json(summary_path, summary_payload)
    return summary_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary_path = run_campaign(args)
    print(f"campaign_summary={summary_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
