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
    parser.add_argument("--drone-count", type=int, default=None, help="main runtime N for simulated drones/resources")
    parser.add_argument("--nodes", type=int, default=None, help="legacy alias for number of simulated nodes/resources")
    parser.add_argument("--tasks", type=int, default=None, help="number of continuity tasks; defaults to the resolved drone count")
    parser.add_argument("--packet-loss", type=float, default=0.10, help="simulated packet loss in [0, 1]")
    parser.add_argument("--seed", type=int, default=7, help="deterministic random seed")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.drone_count is not None and args.nodes is not None and args.nodes != args.drone_count:
        raise SystemExit("--nodes must match --drone-count when both are provided")
    resolved_node_count = args.drone_count if args.drone_count is not None else args.nodes
    if resolved_node_count is None:
        resolved_node_count = 5
    resolved_task_count = args.tasks if args.tasks is not None else resolved_node_count
    metrics = run_failover_simulation(
        node_count=resolved_node_count,
        task_count=resolved_task_count,
        packet_loss=args.packet_loss,
        seed=args.seed,
    )
    print(metrics_to_json(metrics))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
