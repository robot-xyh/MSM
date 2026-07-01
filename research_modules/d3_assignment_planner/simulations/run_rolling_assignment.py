#!/usr/bin/env python3
"""Offline rolling assignment simulation for the D3 planner.

The simulation is intentionally abstract. It evaluates candidate assignment
stability and cost; it does not model physical effects, damage, hardware, or
autonomous execution.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d3_assignment_planner import (  # noqa: E402
    AssignmentPlan,
    AssignmentPlanner,
    CostModel,
    CostWeights,
    PlannerConfig,
    ResourceState,
    TargetTrack,
)
from d3_assignment_planner.solver import HungarianAssignmentSolver  # noqa: E402


@dataclass(frozen=True)
class ScenarioConfig:
    seed: int
    target_count: int
    resource_count: int
    duration_s: float
    hz: float

    @property
    def steps(self) -> int:
        return int(self.duration_s * self.hz)


@dataclass(frozen=True)
class ScenarioSnapshot:
    timestamp: float
    tracks: tuple[TargetTrack, ...]
    resources: tuple[ResourceState, ...]


@dataclass(frozen=True)
class CaseResult:
    name: str
    rows: list[dict[str, float | int | str]]
    summary: dict[str, float | int | str]


class RollingScenario:
    """Deterministic synthetic scenario shared across all planner variants."""

    def __init__(self, config: ScenarioConfig) -> None:
        self.config = config
        rng = np.random.default_rng(config.seed)
        self.target_ids = tuple(f"T{i + 1:02d}" for i in range(config.target_count))
        self.resource_ids = tuple(f"R{j + 1:02d}" for j in range(config.resource_count))
        self.base_threat = rng.uniform(0.35, 0.95, size=config.target_count)
        self.base_covariance = rng.uniform(0.08, 0.35, size=config.target_count)
        self.base_window = rng.uniform(0.15, 0.65, size=config.target_count)
        self.target_phase = rng.uniform(0.0, 2.0 * math.pi, size=config.target_count)
        self.resource_phase = rng.uniform(0.0, 2.0 * math.pi, size=config.resource_count)
        self.pair_phase = rng.uniform(
            0.0,
            2.0 * math.pi,
            size=(config.target_count, config.resource_count),
        )
        self.base_health = rng.uniform(0.72, 1.0, size=config.resource_count)
        self.base_fov = rng.uniform(
            0.05,
            0.75,
            size=(config.target_count, config.resource_count),
        )
        self.base_conflict = rng.uniform(
            0.0,
            0.45,
            size=(config.target_count, config.resource_count),
        )

    def snapshot(self, step: int) -> ScenarioSnapshot:
        timestamp = step / self.config.hz
        tracks: list[TargetTrack] = []
        resources: list[ResourceState] = []

        health_values: list[float] = []
        statuses: list[str] = []
        for j, resource_id in enumerate(self.resource_ids):
            health = float(
                np.clip(
                    self.base_health[j]
                    - 0.12 * (1.0 + math.sin(0.055 * timestamp + self.resource_phase[j]))
                    / 2.0,
                    0.45,
                    1.0,
                )
            )
            outage_wave = math.sin(0.031 * timestamp + self.resource_phase[j] * 1.7)
            if outage_wave > 0.965:
                status = "unavailable"
            elif health < 0.68:
                status = "degraded"
            else:
                status = "available"
            health_values.append(health)
            statuses.append(status)
            resources.append(
                ResourceState(
                    resource_id=resource_id,
                    status=status,
                    health_score=health,
                    load_penalty=0.05
                    * (1.0 + math.sin(0.09 * timestamp + self.resource_phase[j])),
                )
            )

        for i, target_id in enumerate(self.target_ids):
            threat = float(
                np.clip(
                    self.base_threat[i]
                    + 0.15 * math.sin(0.052 * timestamp + self.target_phase[i]),
                    0.05,
                    1.0,
                )
            )
            covariance = float(
                np.clip(
                    self.base_covariance[i]
                    + 0.22
                    * (1.0 + math.sin(0.074 * timestamp + self.target_phase[i] * 0.6))
                    / 2.0,
                    0.0,
                    1.0,
                )
            )
            window_cost = float(
                np.clip(
                    self.base_window[i]
                    + 0.23 * math.sin(0.11 * timestamp + self.target_phase[i] * 1.3),
                    0.0,
                    1.0,
                )
            )
            fov: dict[str, float] = {}
            conflict: dict[str, float] = {}
            feasible: dict[str, bool] = {}
            for j, resource_id in enumerate(self.resource_ids):
                pair_wave = math.sin(0.083 * timestamp + self.pair_phase[i, j])
                fov_value = float(np.clip(self.base_fov[i, j] + 0.22 * pair_wave, 0.0, 1.0))
                conflict_value = float(
                    np.clip(
                        self.base_conflict[i, j]
                        + 0.18
                        * (
                            1.0
                            + math.sin(
                                0.067 * timestamp
                                + self.pair_phase[i, j] * 0.5
                                + self.resource_phase[j]
                            )
                        )
                        / 2.0,
                        0.0,
                        1.0,
                    )
                )
                periodic_block = math.sin(
                    0.041 * timestamp + self.pair_phase[i, j] * 2.1
                ) > 0.985
                fov[resource_id] = fov_value
                conflict[resource_id] = conflict_value
                feasible[resource_id] = (
                    fov_value < 0.96
                    and statuses[j] != "unavailable"
                    and not periodic_block
                )
            tracks.append(
                TargetTrack(
                    track_id=target_id,
                    threat_score=threat,
                    covariance=covariance,
                    window_cost=window_cost,
                    fov_difficulty_by_resource=fov,
                    conflict_risk_by_resource=conflict,
                    feasibility_by_resource=feasible,
                    metadata={"synthetic": True},
                )
            )
        return ScenarioSnapshot(
            timestamp=timestamp,
            tracks=tuple(tracks),
            resources=tuple(resources),
        )


def default_weights() -> CostWeights:
    return CostWeights(
        window=0.7,
        covariance=1.0,
        threat=1.2,
        resource_state=0.9,
        fov=1.4,
        conflict=1.1,
    )


def assignment_change_count(
    previous: AssignmentPlan | None,
    current: AssignmentPlan,
) -> int:
    if previous is None:
        return len(current.assignments)
    old_map = previous.assignment_map()
    new_map = current.assignment_map()
    target_ids = set(old_map) | set(new_map) | set(previous.unassigned_target_ids)
    target_ids |= set(current.unassigned_target_ids)
    return sum(1 for target_id in target_ids if old_map.get(target_id) != new_map.get(target_id))


def run_case(
    name: str,
    scenario: RollingScenario,
    weights: CostWeights,
    config: PlannerConfig,
    allow_scipy: bool,
    collect_rows: bool = True,
) -> CaseResult:
    planner = AssignmentPlanner(
        cost_model=CostModel(weights=weights, config=config),
        solver=HungarianAssignmentSolver(allow_scipy=allow_scipy),
        config=config,
    )
    planner.solver.solve(np.zeros((1, 1), dtype=float), np.ones(1, dtype=float))
    previous: AssignmentPlan | None = None
    rows: list[dict[str, float | int | str]] = []
    runtime_ms: list[float] = []
    total_cost = 0.0
    reassignment_events = 0
    changed_edges_total = 0
    high_threat_total = 0
    high_threat_unassigned = 0

    for step in range(scenario.config.steps):
        snapshot = scenario.snapshot(step)
        start = time.perf_counter()
        plan = planner.plan(
            snapshot.tracks,
            snapshot.resources,
            timestamp=snapshot.timestamp,
            previous_plan=previous,
            window_id=step,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        runtime_ms.append(elapsed_ms)

        changed_edges = assignment_change_count(previous, plan)
        reassignment_event = int(previous is not None and changed_edges > 0)
        reassignment_events += reassignment_event
        changed_edges_total += changed_edges if previous is not None else 0
        total_cost += plan.total_cost

        high_ids = {
            track.track_id
            for track in snapshot.tracks
            if track.threat_score >= config.high_threat_threshold
        }
        unassigned = set(plan.unassigned_target_ids)
        high_threat_total += len(high_ids)
        high_threat_unassigned += len(high_ids & unassigned)

        if collect_rows:
            rows.append(
                {
                    "case": name,
                    "step": step,
                    "time_s": round(snapshot.timestamp, 3),
                    "version": plan.version,
                    "total_cost": plan.total_cost,
                    "candidate_total_cost": (
                        -1.0
                        if plan.candidate_total_cost is None
                        else plan.candidate_total_cost
                    ),
                    "previous_total_cost_current": (
                        -1.0
                        if plan.previous_total_cost_current is None
                        else plan.previous_total_cost_current
                    ),
                    "assignment_count": len(plan.assignments),
                    "unassigned_count": len(plan.unassigned_target_ids),
                    "high_threat_count": len(high_ids),
                    "unassigned_high_threat_count": len(high_ids & unassigned),
                    "reassignment_event": reassignment_event,
                    "changed_edges": changed_edges if previous is not None else 0,
                    "runtime_ms": elapsed_ms,
                    "decision_state": plan.decision_state,
                }
            )
        previous = plan

    high_unassigned_ratio = (
        high_threat_unassigned / high_threat_total if high_threat_total else 0.0
    )
    summary: dict[str, float | int | str] = {
        "case": name,
        "steps": scenario.config.steps,
        "duration_s": scenario.config.duration_s,
        "hz": scenario.config.hz,
        "targets": scenario.config.target_count,
        "resources": scenario.config.resource_count,
        "total_cost": total_cost,
        "mean_cost": total_cost / scenario.config.steps,
        "reassignment_events": reassignment_events,
        "changed_edges_total": changed_edges_total,
        "unassigned_high_threat_ratio": high_unassigned_ratio,
        "unassigned_high_threat_count": high_threat_unassigned,
        "high_threat_count": high_threat_total,
        "runtime_mean_ms": statistics.fmean(runtime_ms),
        "runtime_p95_ms": float(np.percentile(runtime_ms, 95)),
        "runtime_max_ms": max(runtime_ms),
        "delta": config.delta,
        "min_dwell": config.min_dwell,
        "enable_hysteresis": int(config.enable_hysteresis),
    }
    return CaseResult(name=name, rows=rows, summary=summary)


def write_timeseries(path: Path, rows: Iterable[dict[str, float | int | str]]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def json_safe_args(args: argparse.Namespace) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in vars(args).items():
        safe[key] = str(value) if isinstance(value, Path) else value
    return safe


def plot_cost_and_reassignment(results: list[CaseResult], output_path: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for result in results:
        times = [float(row["time_s"]) for row in result.rows]
        costs = [float(row["total_cost"]) for row in result.rows]
        cumulative = np.cumsum([int(row["reassignment_event"]) for row in result.rows])
        axes[0].plot(times, costs, label=result.name, linewidth=1.5)
        axes[1].plot(times, cumulative, label=result.name, linewidth=1.5)

    axes[0].set_ylabel("Accepted plan cost")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend()
    axes[1].set_ylabel("Cumulative reassignments")
    axes[1].set_xlabel("Time (s)")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def run_weight_sensitivity(
    scenario: RollingScenario,
    base_weights: CostWeights,
    base_config: PlannerConfig,
    allow_scipy: bool,
) -> list[dict[str, float | int | str]]:
    rows: list[dict[str, float | int | str]] = []
    terms = ("window", "covariance", "threat", "resource_state", "fov", "conflict")
    multipliers = (0.5, 1.0, 1.5, 2.0)
    for term in terms:
        base_value = getattr(base_weights, term)
        for multiplier in multipliers:
            weights = replace(base_weights, **{term: base_value * multiplier})
            case = run_case(
                name=f"{term}_x{multiplier}",
                scenario=scenario,
                weights=weights,
                config=base_config,
                allow_scipy=allow_scipy,
                collect_rows=False,
            )
            rows.append(
                {
                    "term": term,
                    "multiplier": multiplier,
                    "total_cost": float(case.summary["total_cost"]),
                    "mean_cost": float(case.summary["mean_cost"]),
                    "reassignment_events": int(case.summary["reassignment_events"]),
                    "unassigned_high_threat_ratio": float(
                        case.summary["unassigned_high_threat_ratio"]
                    ),
                    "runtime_mean_ms": float(case.summary["runtime_mean_ms"]),
                }
            )
    return rows


def write_sensitivity_csv(path: Path, rows: list[dict[str, float | int | str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def plot_sensitivity(rows: list[dict[str, float | int | str]], output_path: Path) -> None:
    terms = sorted({str(row["term"]) for row in rows})
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    for term in terms:
        term_rows = [row for row in rows if row["term"] == term]
        term_rows.sort(key=lambda row: float(row["multiplier"]))
        x = [float(row["multiplier"]) for row in term_rows]
        reassign = [int(row["reassignment_events"]) for row in term_rows]
        mean_cost = [float(row["mean_cost"]) for row in term_rows]
        axes[0].plot(x, reassign, marker="o", label=term)
        axes[1].plot(x, mean_cost, marker="o", label=term)
    axes[0].set_ylabel("Reassignment events")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(ncol=3, fontsize=8)
    axes[1].set_ylabel("Mean accepted cost")
    axes[1].set_xlabel("Single-term weight multiplier")
    axes[1].grid(True, alpha=0.25)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_generated_report(
    path: Path,
    summaries: list[dict[str, float | int | str]],
    sensitivity_rows: list[dict[str, float | int | str]],
    artifacts: dict[str, str],
) -> None:
    lines = [
        "# D3 分配仿真自动生成报告",
        "",
        "边界：本报告仅用于离线抽象资源-目标分配评估，不包含真实火控、毁伤、硬件、自动执行或绕过授权逻辑。",
        "",
        "## 1. 场景配置",
        "",
    ]
    first = summaries[0]
    lines.extend(
        [
            f"- 目标数: {first['targets']}",
            f"- 资源数: {first['resources']}",
            f"- 仿真时长: {first['duration_s']} s",
            f"- 决策频率: {first['hz']} Hz",
            f"- 步数: {first['steps']}",
            "",
            "## 2. 主要结果",
            "",
            "| 工况 | 重分配事件 | 总成本 | 平均成本 | 高威胁未分配比例 | 平均耗时 ms | p95 耗时 ms |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        lines.append(
            "| {case} | {reassignment_events} | {total_cost:.3f} | {mean_cost:.3f} | {ratio:.4f} | {runtime_mean:.3f} | {runtime_p95:.3f} |".format(
                case=summary["case"],
                reassignment_events=summary["reassignment_events"],
                total_cost=float(summary["total_cost"]),
                mean_cost=float(summary["mean_cost"]),
                ratio=float(summary["unassigned_high_threat_ratio"]),
                runtime_mean=float(summary["runtime_mean_ms"]),
                runtime_p95=float(summary["runtime_p95_ms"]),
            )
        )

    best_reassignment = min(summaries, key=lambda item: int(item["reassignment_events"]))
    best_cost = min(summaries, key=lambda item: float(item["total_cost"]))
    lines.extend(
        [
            "",
            "## 3. 结果解读",
            "",
            f"- 重分配次数最低的工况：`{best_reassignment['case']}`。",
            f"- 总成本最低的工况：`{best_cost['case']}`。",
            "- 迟滞策略预期会减少重分配事件；当旧计划仍可行时，保持旧计划可能带来少量成本上升。",
            "",
            "## 4. 图表与曲线",
            "",
            "![D3 分配成本与重分配曲线](cost_reassignment.png)",
            "",
            "![D3 权重敏感性曲线](weight_sensitivity.png)",
            "",
            "## 5. 权重敏感性表",
            "",
            "| 代价项 | 权重倍率 | 重分配事件 | 平均成本 | 高威胁未分配比例 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in sensitivity_rows:
        lines.append(
            "| {term} | {multiplier:.1f} | {events} | {mean_cost:.3f} | {ratio:.4f} |".format(
                term=row["term"],
                multiplier=float(row["multiplier"]),
                events=row["reassignment_events"],
                mean_cost=float(row["mean_cost"]),
                ratio=float(row["unassigned_high_threat_ratio"]),
            )
        )
    lines.extend(
        [
            "",
            "## 6. 生成文件",
            "",
        ]
    )
    for label, artifact_path in artifacts.items():
        lines.append(f"- {label}: `{artifact_path}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260630)
    parser.add_argument("--targets", type=int, default=8)
    parser.add_argument("--resources", type=int, default=8)
    parser.add_argument("--duration-s", type=float, default=100.0)
    parser.add_argument("--hz", type=float, default=2.0)
    parser.add_argument("--delta", type=float, default=0.2)
    parser.add_argument("--min-dwell", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Disable SciPy and use the dynamic-programming fallback solver.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not (5 <= args.targets <= 10 and 5 <= args.resources <= 10):
        raise SystemExit("--targets and --resources must both be in the 5-10 range")
    scenario_config = ScenarioConfig(
        seed=args.seed,
        target_count=args.targets,
        resource_count=args.resources,
        duration_s=args.duration_s,
        hz=args.hz,
    )
    scenario = RollingScenario(scenario_config)
    weights = default_weights()
    allow_scipy = not args.force_fallback

    no_hysteresis_config = PlannerConfig(
        enable_hysteresis=False,
        delta=0.0,
        min_dwell=0.0,
        unassigned_base_cost=3.6,
    )
    hysteresis_config = PlannerConfig(
        enable_hysteresis=True,
        delta=args.delta,
        min_dwell=args.min_dwell,
        unassigned_base_cost=3.6,
    )
    results = [
        run_case(
            "no_hysteresis",
            scenario,
            weights,
            no_hysteresis_config,
            allow_scipy=allow_scipy,
        ),
        run_case(
            f"hysteresis_delta_{args.delta:g}",
            scenario,
            weights,
            hysteresis_config,
            allow_scipy=allow_scipy,
        ),
    ]

    output_dir = args.output_dir
    all_rows = [row for result in results for row in result.rows]
    summaries = [result.summary for result in results]
    sensitivity_rows = run_weight_sensitivity(
        scenario,
        weights,
        hysteresis_config,
        allow_scipy=allow_scipy,
    )

    timeseries_path = output_dir / "rolling_assignment_timeseries.csv"
    summary_path = output_dir / "summary.json"
    sensitivity_csv_path = output_dir / "weight_sensitivity.csv"
    cost_plot_path = output_dir / "cost_reassignment.png"
    sensitivity_plot_path = output_dir / "weight_sensitivity.png"
    generated_report_path = output_dir / "EXPERIMENT_REPORT_GENERATED.md"

    write_timeseries(timeseries_path, all_rows)
    write_json(summary_path, {"summaries": summaries, "config": json_safe_args(args)})
    write_sensitivity_csv(sensitivity_csv_path, sensitivity_rows)
    plot_cost_and_reassignment(results, cost_plot_path)
    plot_sensitivity(sensitivity_rows, sensitivity_plot_path)
    write_generated_report(
        generated_report_path,
        summaries,
        sensitivity_rows,
        artifacts={
            "timeseries": str(timeseries_path),
            "summary": str(summary_path),
            "sensitivity_csv": str(sensitivity_csv_path),
            "cost_plot": str(cost_plot_path),
            "sensitivity_plot": str(sensitivity_plot_path),
        },
    )

    print(json.dumps({"summaries": summaries, "output_dir": str(output_dir)}, indent=2))


if __name__ == "__main__":
    main()
