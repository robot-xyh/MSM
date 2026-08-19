#!/usr/bin/env python3
"""Run one frozen-protocol raw AirSim episode under main orchestration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dual_optical_40target.core import CameraSpec, ScenarioConfig
from dual_optical_40target.runtime import DualOpticalAirSimRunner

from .contracts import (
    BenchmarkProtocol,
    benchmark_protocol_for_target_count,
    benchmark_protocol_from_mapping,
)


WORKER_PROTOCOL_SCHEMA = "dual-optical-worker-protocol-v1"


def build_config(
    seed: int,
    api_port: int,
    *,
    gimbal_pose_error_enabled: bool = True,
    protocol: BenchmarkProtocol | None = None,
) -> ScenarioConfig:
    protocol = protocol or BenchmarkProtocol()
    return ScenarioConfig(
        target_count=protocol.target_count,
        seed=int(seed),
        duration_s=protocol.duration_s,
        sample_rate_hz=protocol.sample_rate_hz,
        target_speed_mps=protocol.target_speed_mps,
        scan_period_s=protocol.scan_period_s,
        scan_half_span_deg=protocol.scan_half_span_deg,
        scan_mode=protocol.scan_mode,
        target_motion_profile="split_0_minus30",
        gimbal_pose_error_enabled=bool(gimbal_pose_error_enabled),
        gimbal_fixed_bias_mrad=protocol.gimbal_fixed_bias_rms_mrad,
        gimbal_jitter_rms_mrad=protocol.gimbal_jitter_rms_mrad,
        api_port=int(api_port),
        clock_speed=protocol.clock_speed,
        camera_b_scan_phase_offset_s=protocol.camera_b_scan_phase_offset_s,
        deterministic_step_mode=protocol.deterministic_step_mode,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-port", type=int, default=41451)
    parser.add_argument(
        "--target-count", type=int, choices=(20, 40, 60, 100), default=100
    )
    parser.add_argument("--protocol-file", type=Path, default=None)
    parser.add_argument("--connection-timeout-s", type=float, default=90.0)
    parser.add_argument("--client-timeout-s", type=float, default=10.0)
    parser.add_argument(
        "--disable-gimbal-pose-error",
        action="store_true",
        help="diagnostic preflight only; formal calibration always enables the frozen error model",
    )
    parser.add_argument(
        "--blocks-script",
        type=Path,
        default=Path("Blocks/LinuxBlocks1.8.1/LinuxNoEditor/Blocks.sh"),
    )
    return parser.parse_args()


def load_worker_protocol(
    path: Path | None, *, target_count: int
) -> BenchmarkProtocol:
    if path is None:
        return benchmark_protocol_for_target_count(target_count)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != WORKER_PROTOCOL_SCHEMA:
        raise ValueError("unsupported worker protocol schema")
    protocol = benchmark_protocol_from_mapping(payload["protocol"])
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("worker protocol fingerprint mismatch")
    if protocol.target_count != int(target_count):
        raise ValueError("worker target count does not match protocol file")
    return protocol


def main() -> int:
    args = parse_args()
    protocol = load_worker_protocol(
        args.protocol_file, target_count=args.target_count
    )
    runner = DualOpticalAirSimRunner(
        config=build_config(
            args.seed,
            args.api_port,
            gimbal_pose_error_enabled=not args.disable_gimbal_pose_error,
            protocol=protocol,
        ),
        camera_spec=CameraSpec(),
        output_dir=args.output_dir,
        blocks_script=args.blocks_script,
        launch_blocks=False,
        connection_timeout_s=args.connection_timeout_s,
        client_timeout_s=args.client_timeout_s,
        save_keyframes=False,
    )
    result = runner.run()
    print(result.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
