#!/usr/bin/env python3
"""Run the D4 offline failover simulation and print metrics JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from d4_distributed_fallback.simulation import metrics_to_json, run_failover_simulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=5, help="number of simulated nodes, 3 to 5")
    parser.add_argument("--tasks", type=int, default=4, help="number of continuity tasks")
    parser.add_argument("--packet-loss", type=float, default=0.10, help="simulated packet loss in [0, 1]")
    parser.add_argument("--seed", type=int, default=7, help="deterministic random seed")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics = run_failover_simulation(
        node_count=args.nodes,
        task_count=args.tasks,
        packet_loss=args.packet_loss,
        seed=args.seed,
    )
    print(metrics_to_json(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
