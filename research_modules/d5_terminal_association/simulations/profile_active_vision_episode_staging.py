#!/usr/bin/env python3
"""Profile deterministic D5 active-vision episode staging at high cardinality."""

from __future__ import annotations

import argparse
from collections import Counter
import cProfile
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import pstats
import shutil
import statistics
import sys
import tempfile
import time
from typing import Any


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import d5_terminal_association.active_vision_episode_dataset as dataset  # noqa: E402
from d5_terminal_association.active_vision_contracts import (  # noqa: E402
    ActiveVisionAssignmentReference,
    ActiveVisionCameraState,
    ActiveVisionCommunicationState,
    ActiveVisionDecisionV1,
    ActiveVisionFovMode,
    ActiveVisionPlanReference,
    ActiveVisionProjectionEvidence,
    ActiveVisionRuntimeMode,
    ActiveVisionSnapshotV1,
    ActiveVisionTrackReference,
    DeterministicLookAtScanPolicy,
)


GENERATION_CONFIG = {
    "recording_mode": "whole_episode",
    "policy_source": "deterministic_rule_demonstration",
}
TRACKED_CALLS = (
    "_assert_online_truth_free",
    "_canonical_json_bytes",
    "_feedback_to_payload",
    "_snapshot_to_payload",
    "_stream_object_key",
    "_validate_snapshot_center_references",
    "assert_truth_free_active_vision_payload",
    "sha256_file",
)


def build_fixture(
    *,
    seed: int,
    camera_count: int,
    track_count: int,
    phase: dict[str, str],
) -> tuple[dataset.ActiveVisionEpisodeRecordV1, dict[str, float]]:
    phase["name"] = "snapshot_build"
    started = time.perf_counter()
    now = 1000.0 + seed
    tracks = tuple(
        ActiveVisionTrackReference(
            global_track_id=f"GT-{seed:03d}-{index:03d}",
            track_version=seed + 1,
            measurement_timestamp=now - 0.05,
        )
        for index in range(track_count)
    )
    cameras = tuple(
        ActiveVisionCameraState(
            camera_id=f"CAM-{index:03d}",
            resource_id=f"RES-{index:03d}",
            state_timestamp=now,
            yaw_deg=float(index % 91),
            pitch_deg=-2.0,
            yaw_rate_deg_s=0.0,
            pitch_rate_deg_s=0.0,
            yaw_limits_deg=(-90.0, 90.0),
            pitch_limits_deg=(-45.0, 30.0),
            max_yaw_rate_deg_s=60.0,
            max_pitch_rate_deg_s=45.0,
            max_slew_deg_s=70.0,
            current_fov_mode=ActiveVisionFovMode.WIDE,
        )
        for index in range(camera_count)
    )
    assignments = tuple(
        ActiveVisionAssignmentReference(
            resource_id=camera.resource_id,
            camera_id=camera.camera_id,
            global_track_id=tracks[index % track_count].global_track_id,
        )
        for index, camera in enumerate(cameras)
    )
    snapshot = ActiveVisionSnapshotV1(
        snapshot_timestamp=now,
        plan=ActiveVisionPlanReference(
            plan_version=seed + 1,
            coalition_version=seed + 2,
            assignments=assignments,
        ),
        communication=ActiveVisionCommunicationState(
            communication_version=seed + 3,
            plan_version=seed + 1,
            coalition_version=seed + 2,
            update_timestamp=now - 0.01,
            healthy=True,
        ),
        tracks=tracks,
        cameras=cameras,
        projections=tuple(
            ActiveVisionProjectionEvidence(
                camera_id=assignment.camera_id,
                global_track_id=assignment.global_track_id,
                measurement_timestamp=now - 0.05,
                arrival_timestamp=now - 0.02,
                yaw_error_deg=3.0,
                pitch_error_deg=-1.0,
                projection_covariance_deg2=(1.0, 0.0, 0.0, 1.0),
                visibility_probability=0.9,
                occlusion_fraction=0.05,
                association_confidence=0.95,
                in_fov=True,
            )
            for assignment in assignments
        ),
    )
    snapshot_seconds = time.perf_counter() - started

    phase["name"] = "sample_build"
    started = time.perf_counter()
    policy = DeterministicLookAtScanPolicy()
    samples = []
    for index, camera in enumerate(snapshot.cameras):
        rule = policy.select_action(
            snapshot,
            camera_id=camera.camera_id,
            current_timestamp=snapshot.snapshot_timestamp,
            expected_plan_version=snapshot.plan.plan_version,
            expected_coalition_version=snapshot.plan.coalition_version,
            expected_communication_version=snapshot.communication.communication_version,
        )
        decision = ActiveVisionDecisionV1(
            requested_mode=ActiveVisionRuntimeMode.SHADOW,
            effective_mode=ActiveVisionRuntimeMode.SHADOW,
            rule_action=rule,
            requested_action=rule,
            effective_action=rule,
            fallback_reason=None,
            inference_latency_ms=0.0,
            model_fingerprint=None,
            plan_version=snapshot.plan.plan_version,
            coalition_version=snapshot.plan.coalition_version,
            communication_version=snapshot.communication.communication_version,
        )
        command_version = seed * 100 + index
        sample_key = f"sample-{seed:03d}-{index:03d}"
        feedback = dataset.ActiveVisionCameraFeedbackV1(
            camera_state=replace(
                camera,
                state_timestamp=snapshot.snapshot_timestamp + 0.02,
            ),
            last_accepted_command_version=command_version,
        )
        ack = dataset.ActiveVisionRuntimeAckV1(
            sample_key=sample_key,
            camera_id=camera.camera_id,
            command_version=command_version,
            ack_timestamp=snapshot.snapshot_timestamp + 0.01,
            accepted=True,
            status_code="applied",
            plan_version=snapshot.plan.plan_version,
            coalition_version=snapshot.plan.coalition_version,
            communication_version=snapshot.communication.communication_version,
        )
        samples.append(
            dataset.active_vision_sample_from_decision(
                sample_key=sample_key,
                observation_key=f"observation-{seed:03d}-{index:03d}",
                sequence_index=index,
                camera_id=camera.camera_id,
                snapshot=snapshot,
                decision=decision,
                camera_feedback=feedback,
                runtime_ack=ack if index % 2 == 0 else None,
            )
        )
    sample_seconds = time.perf_counter() - started

    phase["name"] = "record_build"
    started = time.perf_counter()
    record = dataset.ActiveVisionEpisodeRecordV1(
        scenario_version="unified-3d-v1",
        seed=seed,
        episode_id=f"episode-{seed:03d}",
        source_identity=dataset.ActiveVisionSourceIdentityV1(
            git_commit="a" * 40,
            git_dirty=False,
            config_sha256="b" * 64,
        ),
        samples=tuple(samples),
        synthetic_fixture=True,
    )
    record_seconds = time.perf_counter() - started
    return record, {
        "snapshot_build_seconds": snapshot_seconds,
        "sample_build_seconds": sample_seconds,
        "record_build_seconds": record_seconds,
        "fixture_build_seconds": snapshot_seconds + sample_seconds + record_seconds,
    }


def run_once(*, seed: int, camera_count: int, track_count: int) -> dict[str, Any]:
    phase = {"name": "setup"}
    counts: Counter[tuple[str, str]] = Counter()
    originals = {name: getattr(dataset, name) for name in TRACKED_CALLS}
    for name, original in originals.items():
        def tracked(
            *args: object,
            _name: str = name,
            _original=original,
            **kwargs: object,
        ) -> Any:
            counts[(phase["name"], _name)] += 1
            return _original(*args, **kwargs)

        setattr(dataset, name, tracked)

    temporary_root = Path(tempfile.mkdtemp(prefix="d5-active-vision-profile-"))
    try:
        record, timings = build_fixture(
            seed=seed,
            camera_count=camera_count,
            track_count=track_count,
            phase=phase,
        )
        first = temporary_root / "first"
        phase["name"] = "online_stage"
        started = time.perf_counter()
        descriptor = dataset.stage_active_vision_episode_record(
            first,
            record,
            generation_config=GENERATION_CONFIG,
        )
        timings["online_stage_seconds"] = time.perf_counter() - started

        phase["name"] = "offline_stage"
        started = time.perf_counter()
        descriptor = dataset.stage_active_vision_offline_labels(
            first,
            record.episode_uid,
            dataset.unavailable_active_vision_offline_labels(record),
        )
        timings["offline_stage_seconds"] = time.perf_counter() - started

        online_path = first / str(descriptor["online_file"])
        offline_path = first / str(descriptor["offline_file"])
        phase["name"] = "materialized_load"
        started = time.perf_counter()
        loaded = dataset.load_active_vision_episode_record(online_path)
        timings["materialized_load_seconds"] = time.perf_counter() - started
        phase["name"] = "public_audit"
        started = time.perf_counter()
        audit = dataset.audit_active_vision_episode_record(online_path)
        timings["public_audit_seconds"] = time.perf_counter() - started
        first_encoded = online_path.read_bytes()
        first_decoded = gzip.decompress(first_encoded)
    finally:
        for name, original in originals.items():
            setattr(dataset, name, original)

    try:
        second = temporary_root / "second"
        second_descriptor = dataset.stage_active_vision_episode_record(
            second,
            record,
            generation_config=GENERATION_CONFIG,
        )
        second_encoded = (second / str(second_descriptor["online_file"])).read_bytes()
        second_decoded = gzip.decompress(second_encoded)
        return {
            "timings": timings,
            "call_counts": {
                f"{counted_phase}:{name}": count
                for (counted_phase, name), count in sorted(counts.items())
            },
            "sample_count": len(loaded.samples),
            "unique_snapshot_count": int(audit["unique_snapshot_count"]),
            "unique_camera_feedback_count": int(audit["unique_camera_feedback_count"]),
            "online_gzip_bytes": len(first_encoded),
            "online_decompressed_bytes": len(first_decoded),
            "offline_json_bytes": offline_path.stat().st_size,
            "online_gzip_sha256": hashlib.sha256(first_encoded).hexdigest(),
            "online_decompressed_sha256": hashlib.sha256(first_decoded).hexdigest(),
            "gzip_deterministic": first_encoded == second_encoded,
            "decompressed_byte_equivalent": first_decoded == second_decoded,
        }
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-count", type=int, default=200)
    parser.add_argument("--track-count", type=int, default=400)
    parser.add_argument("--seed", type=int, default=777)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--output",
        type=Path,
        default=MODULE_ROOT / "results" / "active_vision_staging_profile_current.json",
    )
    parser.add_argument("--cprofile-output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.camera_count <= 0 or args.track_count <= 0 or args.repeats <= 0:
        raise SystemExit("camera-count, track-count, and repeats must be positive")
    runs = [
        run_once(
            seed=args.seed,
            camera_count=args.camera_count,
            track_count=args.track_count,
        )
        for _ in range(args.repeats)
    ]
    timing_names = tuple(runs[0]["timings"])
    payload = {
        "schema_version": "d5.active-vision-staging-profile.v1",
        "fixture": {
            "camera_count": args.camera_count,
            "track_count": args.track_count,
            "snapshot_count": 1,
            "sample_count": args.camera_count,
            "seed": args.seed,
            "runtime_ack_fraction": 0.5,
        },
        "gzip_compresslevel": dataset.ACTIVE_VISION_GZIP_COMPRESSLEVEL,
        "repeat_count": args.repeats,
        "median_timings": {
            name: statistics.median(run["timings"][name] for run in runs)
            for name in timing_names
        },
        "runs": runs,
        "acceptance": {
            "gzip_deterministic": all(run["gzip_deterministic"] for run in runs),
            "decompressed_byte_equivalent": all(
                run["decompressed_byte_equivalent"] for run in runs
            ),
            "schema_changed": False,
            "sampling_or_feature_reduction": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.cprofile_output is not None:
        args.cprofile_output.parent.mkdir(parents=True, exist_ok=True)
        profiler = cProfile.Profile()
        profiler.enable()
        run_once(
            seed=args.seed,
            camera_count=args.camera_count,
            track_count=args.track_count,
        )
        profiler.disable()
        profiler.dump_stats(str(args.cprofile_output))
        stats_path = args.cprofile_output.with_suffix(args.cprofile_output.suffix + ".txt")
        with stats_path.open("w", encoding="utf-8") as stream:
            pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
                "cumtime"
            ).print_stats(60)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
