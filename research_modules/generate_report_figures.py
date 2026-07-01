#!/usr/bin/env python3
"""Generate report figures for the six offline research modules."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent

for path in (
    ROOT / "d2_data_association",
    ROOT / "d4_distributed_fallback",
    ROOT / "d5_terminal_association" / "src",
    ROOT / "d5_terminal_association",
    ROOT / "d5_terminal_association" / "simulations",
):
    sys.path.insert(0, str(path))

from d2_data_association.simulation import run_benchmark  # noqa: E402
from d4_distributed_fallback.simulation import run_failover_simulation  # noqa: E402
from run_terminal_association_sim import run_simulation as run_terminal_simulation  # noqa: E402


def main() -> int:
    write_d2_figures()
    write_d4_figures()
    write_d5_figures()
    return 0


def write_d2_figures() -> None:
    out_dir = ROOT / "d2_data_association" / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = run_benchmark(steps=36, seed=7)
    rows = [result.to_dict() for result in results]
    (out_dir / "benchmark_results.json").write_text(
        json.dumps(rows, indent=2),
        encoding="utf-8",
    )

    scenarios = sorted({row["scenario"] for row in rows})
    associators = ["gnn", "jpda", "mht"]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    width = 0.24
    x = np.arange(len(scenarios))
    colors = {"gnn": "#4C78A8", "jpda": "#F58518", "mht": "#54A24B"}

    for offset, associator in enumerate(associators):
        subset = [row for row in rows if row["associator"] == associator]
        by_scenario = {row["scenario"]: row for row in subset}
        idsw = [by_scenario[scenario]["metrics"]["id_switch_count"] for scenario in scenarios]
        rmse = [by_scenario[scenario]["metrics"]["rmse"] for scenario in scenarios]
        positions = x + (offset - 1) * width
        axes[0].bar(positions, idsw, width=width, label=associator.upper(), color=colors[associator])
        axes[1].plot(
            scenarios,
            rmse,
            marker="o",
            linewidth=2,
            label=associator.upper(),
            color=colors[associator],
        )

    axes[0].set_ylabel("ID switches")
    axes[0].set_title("D2 Association ID Switch Comparison")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(scenarios, rotation=20, ha="right")
    axes[0].grid(axis="y", alpha=0.25)
    axes[0].legend()
    axes[1].set_ylabel("RMSE")
    axes[1].set_title("D2 Tracking RMSE Curves")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(out_dir / "association_idsw_rmse.png", dpi=150)
    plt.close(fig)


def write_d4_figures() -> None:
    out_dir = ROOT / "d4_distributed_fallback" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_losses = [0.0, 0.05, 0.1, 0.2, 0.35]
    rows = []
    for packet_loss in packet_losses:
        metrics = run_failover_simulation(
            node_count=5,
            task_count=4,
            packet_loss=packet_loss,
            seed=11,
        )
        metrics["packet_loss"] = packet_loss
        rows.append(metrics)
    (out_dir / "failover_packet_loss_results.json").write_text(
        json.dumps(rows, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    fig, ax1 = plt.subplots(figsize=(9, 4.8))
    x = np.array(packet_losses)
    failover = np.array([row["takeover_time_s"] or 0.0 for row in rows], dtype=float)
    completion = np.array([row["assignment_completion_rate"] for row in rows], dtype=float)
    rounds = np.array([row["consensus_rounds"] for row in rows], dtype=float)

    ax1.plot(x, failover, marker="o", linewidth=2, color="#4C78A8", label="takeover time")
    ax1.plot(x, rounds, marker="s", linewidth=2, color="#F58518", label="consensus rounds")
    ax1.set_xlabel("Packet loss")
    ax1.set_ylabel("Time / rounds")
    ax1.grid(alpha=0.25)

    ax2 = ax1.twinx()
    ax2.plot(x, completion, marker="^", linewidth=2, color="#54A24B", label="completion rate")
    ax2.set_ylabel("Completion rate")
    ax2.set_ylim(-0.05, 1.05)

    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc="best")
    ax1.set_title("D4 Failover Under Packet Loss")
    fig.tight_layout()
    fig.savefig(out_dir / "failover_packet_loss_curve.png", dpi=150)
    plt.close(fig)


def write_d5_figures() -> None:
    out_dir = ROOT / "d5_terminal_association" / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = run_terminal_simulation(frames=120, seed=7)
    (out_dir / "terminal_timeline_results.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    timeline = metrics["timeline"]
    states = ["locked", "ambiguous", "hold", "reacquire"]
    state_to_value = {state: index for index, state in enumerate(states)}
    x = np.array([item["frame"] for item in timeline], dtype=float)
    y = np.array([state_to_value.get(item["decision"], -1) for item in timeline], dtype=float)
    cumulative_locked = np.cumsum([1 if item["decision"] == "locked" else 0 for item in timeline])
    cumulative_ambiguous = np.cumsum([1 if item["decision"] == "ambiguous" else 0 for item in timeline])
    cumulative_hold = np.cumsum([1 if item["decision"] == "hold" else 0 for item in timeline])
    cumulative_reacquire = np.cumsum([1 if item["decision"] == "reacquire" else 0 for item in timeline])

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    axes[0].step(x, y, where="post", linewidth=1.8, color="#4C78A8")
    axes[0].set_yticks(list(state_to_value.values()))
    axes[0].set_yticklabels(states)
    axes[0].set_title("D5 Terminal Decision Timeline")
    axes[0].grid(alpha=0.25)

    axes[1].plot(x, cumulative_locked, label="locked", linewidth=2)
    axes[1].plot(x, cumulative_ambiguous, label="ambiguous", linewidth=2)
    axes[1].plot(x, cumulative_hold, label="hold", linewidth=2)
    axes[1].plot(x, cumulative_reacquire, label="reacquire", linewidth=2)
    axes[1].set_xlabel("Frame")
    axes[1].set_ylabel("Cumulative count")
    axes[1].set_title("D5 Cumulative Terminal Decisions")
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(out_dir / "terminal_decision_timeline.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
