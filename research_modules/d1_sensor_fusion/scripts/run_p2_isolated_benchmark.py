from __future__ import annotations

import argparse
import json
from pathlib import Path

from d1_sensor_fusion.p2_benchmark import (
    load_frozen_governed_replay,
    run_p2_isolated_benchmark,
)


DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "p2_governed_filter_benchmark_v1.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated D1 P2 filter benchmark")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    args = parser.parse_args()
    report = run_p2_isolated_benchmark(load_frozen_governed_replay(args.fixture))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
