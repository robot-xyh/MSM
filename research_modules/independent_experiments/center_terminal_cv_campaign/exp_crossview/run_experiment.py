"""Main-callable runner for offline replay or an already running AirSim instance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from ..common.io import write_json, write_jsonl
from .airsim_adapter import (
    AirSimDetectCollector,
    AirSimOfflineDetectionLabel,
    CameraPoseNED,
    DetectionNameResolver,
)
from .association import associate_crossview_tracks
from .camera_pairs import CAMERA_PAIR_POLICIES, build_camera_pair_plan
from .config import CameraCalibration, CrossViewConfig
from .evaluation import (
    build_offline_truth_from_detection_labels,
    score_with_offline_truth,
)
from .fixture import build_fixture
from .gnn import load_model_bundle
from .replay_io import (
    CALIBRATIONS_FILENAME,
    LOCAL_TRACKS_FILENAME,
    TRUTH_RELATIVE_PATH,
    load_calibrations,
    load_fixture,
    load_online_capture_plan,
    load_replay_manifest,
    load_saved_replay_online,
    load_saved_replay_truth,
    load_truth,
    write_fixture,
)
from .reporting import write_experiment_outputs


FrameAdvance = Callable[[int, float], None]


@dataclass(frozen=True)
class RunArtifacts:
    output_dir: Path
    metrics_path: Path
    report_path: Path
    record_count: int
    association_backend: str
    mode: str
    camera_pair_policy: str
    output_mode: str


def _load_capture_plan(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "terminal-crossview-airsim-capture-plan-v1":
        raise ValueError("unsupported AirSim capture plan")
    if not isinstance(payload.get("frames"), list) or not payload["frames"]:
        raise ValueError("capture plan must contain at least one frame")
    return payload


def _collect_airsim_records(
    fixture_dir: Path,
    calibrations: Mapping[str, CameraCalibration],
    *,
    client: Any | None,
    image_type: Any | None,
    frame_advance: FrameAdvance | None,
    actor_name_to_truth_target: Mapping[str, str] | None,
    actor_name_aliases: Mapping[str, str] | None,
) -> tuple[tuple[object, ...], tuple[AirSimOfflineDetectionLabel, ...]]:
    import airsim as airsim_module

    if client is None:
        client = airsim_module.VehicleClient()
        client.confirmConnection()
    if image_type is None:
        image_type = airsim_module.ImageType.Scene
    plan = _load_capture_plan(fixture_dir / "capture_plan.json")
    collector = AirSimDetectCollector(
        client,
        calibrations,
        image_type=image_type,
        camera_name=str(plan.get("camera_name", "0")),
        name_resolver=DetectionNameResolver(
            actor_name_to_truth_target,
            actor_name_aliases,
        ),
    )
    detection_filter = plan.get("detection_filter", {})
    if detection_filter:
        for camera_id in calibrations:
            collector.configure_detection_filter(
                camera_id,
                radius_cm=float(detection_filter.get("radius_cm", 1000000.0)),
                mesh_names=tuple(str(value) for value in detection_filter.get("mesh_names", ("*",))),
            )
    records = []
    offline_labels: list[AirSimOfflineDetectionLabel] = []
    for frame_index, frame in enumerate(plan["frames"]):
        timestamp = float(frame["measurement_timestamp"])
        if frame_advance is not None:
            frame_advance(frame_index, timestamp)
        for camera in frame["cameras"]:
            camera_id = str(camera["camera_id"])
            pose = CameraPoseNED(
                position_ned_m=tuple(float(value) for value in camera["position_ned_m"]),
                yaw_pitch_roll_deg=tuple(
                    float(value) for value in camera["yaw_pitch_roll_deg"]
                ),
            )
            if bool(plan.get("apply_vehicle_pose", True)):
                yaw, pitch, roll = pose.yaw_pitch_roll_deg
                # ComputerVision entities all start at (0, 0, 0). The capture
                # plan is already in world NED and must not be offset again.
                airsim_pose = airsim_module.Pose(
                    airsim_module.Vector3r(*pose.position_ned_m),
                    airsim_module.to_quaternion(
                        math.radians(pitch),
                        math.radians(roll),
                        math.radians(yaw),
                    ),
                )
                client.simSetVehiclePose(
                    airsim_pose,
                    ignore_collision=True,
                    vehicle_name=camera_id,
                )
            batch = collector.collect_with_offline_labels(
                camera_id,
                measurement_timestamp=timestamp,
                arrival_timestamp=float(frame.get("arrival_timestamp", timestamp + 0.01)),
                pose=pose,
            )
            records.extend(batch.local_tracks)
            offline_labels.extend(batch.offline_labels)
    # The client lifecycle stays with main when it supplied the connection. A
    # locally created VehicleClient has no process to stop; Blocks is untouched.
    return tuple(records), tuple(offline_labels)


def run(
    *,
    fixture_dir: str | Path | None = None,
    replay_manifest: str | Path | None = None,
    output_dir: str | Path,
    mode: str = "offline",
    association_backend: str = "geometry",
    client: Any | None = None,
    image_type: Any | None = None,
    gnn_model_dir: str | Path | None = None,
    scenario_name: str = "partial_3cam_5target",
    seed: int = 20260816,
    target_count: int | None = None,
    config: CrossViewConfig | None = None,
    frame_advance: FrameAdvance | None = None,
    actor_name_to_truth_target: Mapping[str, str] | None = None,
    actor_name_aliases: Mapping[str, str] | None = None,
    camera_pair_policy: str = "full",
    output_mode: str | None = None,
    candidate_sample_limit: int = 200,
    error_sample_limit: int = 100,
) -> RunArtifacts:
    """Run one experiment without launching or resetting AirSim Blocks.

    Main may inject an already connected ``client`` for ``mode='airsim'``.
    ``frame_advance`` is called once at the start of every AirSim capture frame,
    including frame zero, before any camera pose or detection request.
    ``fixture_dir`` holds replay input or the AirSim capture plan, while all
    products are written below ``output_dir``.
    """

    if mode not in {"offline", "airsim"}:
        raise ValueError("mode must be offline or airsim")
    if association_backend not in {"geometry", "gnn"}:
        raise ValueError("association_backend must be geometry or gnn")
    if camera_pair_policy not in CAMERA_PAIR_POLICIES:
        raise ValueError("camera_pair_policy must be full or sector_fov")
    if (fixture_dir is None) == (replay_manifest is None):
        raise ValueError("provide exactly one of fixture_dir or replay_manifest")
    if replay_manifest is not None and mode != "offline":
        raise ValueError("saved replay manifests are available only in offline mode")
    fixture_path = Path(fixture_dir) if fixture_dir is not None else None
    output_path = Path(output_dir)
    resolved_output_mode = output_mode or (
        "audit" if replay_manifest is not None else "detailed"
    )
    if resolved_output_mode not in {"detailed", "audit"}:
        raise ValueError("output_mode must be detailed or audit")
    truth = None
    replay = None
    capture_plan_for_pairs: Mapping[str, Any] | None = None
    offline_detection_labels: tuple[AirSimOfflineDetectionLabel, ...] = ()
    if replay_manifest is not None:
        # Parse paths first. Online inputs verify their own three hashes; the
        # offline truth file is not opened or hashed until association finishes.
        replay = load_replay_manifest(Path(replay_manifest), verify_hashes=False)
        online_inputs = load_saved_replay_online(replay)
        records = online_inputs.records
        calibrations = dict(online_inputs.calibrations)
        capture_plan_for_pairs = online_inputs.capture_plan
        scenario_name = replay.scenario_id
        seed = replay.campaign_seed
    elif mode == "offline":
        assert fixture_path is not None
        if (fixture_path / LOCAL_TRACKS_FILENAME).exists():
            records, calibrations, truth = load_fixture(fixture_path)
        else:
            bundle = build_fixture(
                scenario_name,
                seed=seed,
                target_count=target_count,
            )
            write_fixture(fixture_path, bundle)
            records = bundle.records
            calibrations = dict(bundle.calibrations)
            truth = bundle.truth
        capture_plan_path = fixture_path / "capture_plan.json"
        if capture_plan_path.exists():
            capture_plan_for_pairs = load_online_capture_plan(capture_plan_path)
    else:
        assert fixture_path is not None
        calibrations = load_calibrations(fixture_path / CALIBRATIONS_FILENAME)
        records, offline_detection_labels = _collect_airsim_records(
            fixture_path,
            calibrations,
            client=client,
            image_type=image_type,
            frame_advance=frame_advance,
            actor_name_to_truth_target=actor_name_to_truth_target,
            actor_name_aliases=actor_name_aliases,
        )
        truth_path = fixture_path / TRUTH_RELATIVE_PATH
        fixture_truth = load_truth(truth_path) if truth_path.exists() else None
        derived_truth = build_offline_truth_from_detection_labels(
            offline_detection_labels,
            scenario_name=scenario_name,
            seed=seed,
        )
        truth = derived_truth if derived_truth.track_to_target else fixture_truth
        capture_plan_for_pairs = load_online_capture_plan(
            fixture_path / "capture_plan.json"
        )
        output_path.mkdir(parents=True, exist_ok=True)
        write_jsonl(output_path / "captured_local_tracks.jsonl", records)
        write_jsonl(
            output_path / "truth" / "airsim_detection_labels.jsonl",
            offline_detection_labels,
        )
        write_json(
            output_path / "truth" / "local_track_truth_map.json",
            {
                "schema_version": "terminal-crossview-airsim-local-truth-v1",
                "offline_truth_only": True,
                "track_to_target": derived_truth.track_to_target,
                "resolved_label_count": sum(
                    label.resolved_truth_target_id is not None
                    for label in offline_detection_labels
                ),
                "unresolved_label_count": sum(
                    label.resolved_truth_target_id is None
                    for label in offline_detection_labels
                ),
            },
        )

    scorer = None
    if association_backend == "gnn":
        default_model_root = fixture_path if fixture_path is not None else replay.manifest_path.parent
        model_path = Path(gnn_model_dir) if gnn_model_dir is not None else default_model_root / "gnn_model"
        if not (model_path / "manifest.json").exists():
            raise FileNotFoundError(
                f"GNN model bundle not found at {model_path}; train it on disjoint seeds first"
            )
        scorer = load_model_bundle(model_path, evaluation_seeds=(seed,))
    pair_plan = build_camera_pair_plan(
        calibrations,
        policy=camera_pair_policy,
        capture_plan=capture_plan_for_pairs,
    )
    result = associate_crossview_tracks(
        records,  # type: ignore[arg-type]
        calibrations,
        config=config,
        backend=association_backend,
        scorer=scorer,
        camera_pair_plan=pair_plan,
        output_mode=resolved_output_mode,
        candidate_sample_limit=candidate_sample_limit,
    )
    if replay is not None:
        # Truth is loaded only after the online association result exists.
        truth = load_saved_replay_truth(replay)
    if truth is not None:
        result = score_with_offline_truth(result, truth)
    metrics_path, report_path = write_experiment_outputs(
        output_path,
        result,
        records,  # type: ignore[arg-type]
        truth=truth,
        output_mode=resolved_output_mode,
        error_sample_limit=error_sample_limit,
    )
    if replay is not None:
        write_json(
            output_path / "truth" / "replay_manifest_audit.json",
            replay.audit_dict(),
        )
    return RunArtifacts(
        output_dir=output_path,
        metrics_path=metrics_path,
        report_path=report_path,
        record_count=len(records),
        association_backend=association_backend,
        mode=mode,
        camera_pair_policy=camera_pair_policy,
        output_mode=resolved_output_mode,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the anonymous interceptor cross-view association experiment"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture-dir", type=Path)
    source.add_argument("--replay-manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("offline", "airsim"), default="offline")
    parser.add_argument(
        "--association-backend", choices=("geometry", "gnn"), default="geometry"
    )
    parser.add_argument("--gnn-model-dir", type=Path)
    parser.add_argument(
        "--scenario",
        choices=(
            "two_by_two_crossing",
            "no_common_targets",
            "partial_3cam_5target",
            "dense_multicamera",
        ),
        default="partial_3cam_5target",
    )
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--target-count", type=int)
    parser.add_argument(
        "--camera-pair-policy", choices=CAMERA_PAIR_POLICIES, default="full"
    )
    parser.add_argument("--output-mode", choices=("detailed", "audit"))
    parser.add_argument("--candidate-sample-limit", type=int, default=200)
    parser.add_argument("--error-sample-limit", type=int, default=100)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    artifacts = run(
        fixture_dir=args.fixture_dir,
        replay_manifest=args.replay_manifest,
        output_dir=args.output_dir,
        mode=args.mode,
        association_backend=args.association_backend,
        gnn_model_dir=args.gnn_model_dir,
        scenario_name=args.scenario,
        seed=args.seed,
        target_count=args.target_count,
        camera_pair_policy=args.camera_pair_policy,
        output_mode=args.output_mode,
        candidate_sample_limit=args.candidate_sample_limit,
        error_sample_limit=args.error_sample_limit,
    )
    print(f"metrics: {artifacts.metrics_path}")
    print(f"report: {artifacts.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
