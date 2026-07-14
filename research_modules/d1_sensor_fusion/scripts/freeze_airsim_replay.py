#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d1_sensor_fusion import (  # noqa: E402
    ReplayProvenance,
    file_sha256,
    freeze_airsim_replay_file,
    write_frozen_airsim_replay,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze main-persisted AirSim JSON/JSONL into D1 governed replay files."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--scenario-version", default="1")
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--config-version", default="1")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--target-spacing-m",
        type=float,
        required=True,
        help="Capture-declared target spacing; D1 rejects any payload mismatch.",
    )
    parser.add_argument("--profile-id")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_digest = file_sha256(args.input)
    scenario_payload = {
        "scenario_id": args.scenario_id,
        "scenario_version": args.scenario_version,
        "config_digest": config_digest,
        "seed": args.seed,
        "profile_id": args.profile_id,
    }
    scenario_digest = "sha256:" + hashlib.sha256(
        json.dumps(scenario_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    provenance = ReplayProvenance(
        scenario_id=args.scenario_id,
        scenario_version=args.scenario_version,
        config_id=args.config_id,
        config_digest=config_digest,
        config_version=args.config_version,
        scenario_digest=scenario_digest,
        run_id=f"seed-{args.seed:06d}",
        seed=args.seed,
        source_format="main_airsim_json_or_jsonl",
        producer="d1-freeze-cli",
        metadata={
            **({"profile_id": args.profile_id} if args.profile_id else {}),
            "target_spacing_m": args.target_spacing_m,
        },
    )
    result = freeze_airsim_replay_file(args.input, provenance)
    paths = write_frozen_airsim_replay(args.output_dir, result)
    print(
        "D1 AirSim replay frozen: "
        f"{len(result.records)} records, {result.offline_truth['sample_count']} truth samples, "
        f"output={args.output_dir}"
    )
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
