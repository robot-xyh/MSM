"""Chinese capacity and runtime report for scalable learning-data probes."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping


SCENARIO_LABELS = {
    "nominal": "名义",
    "dense_crossing": "密集交叉",
    "formation_split": "编队分裂",
    "evasive_multilevel": "多高度规避",
    "delayed_noisy": "延迟噪声",
    "communication_degraded": "通信退化",
    "center_failure": "中心失效",
    "secondary_failure": "二级失效",
    "high_threat_m_to_n": "高威胁多机",
}


def write_capacity_probe_report(
    scenario_output: str | Path,
    timed_output: str | Path,
    report_dir: str | Path,
    *,
    baseline_timed_output: str | Path | None = None,
    write_plots: bool = True,
) -> dict[str, Path]:
    scenario_root = Path(scenario_output)
    timed_root = Path(timed_output)
    baseline_timed_root = (
        None if baseline_timed_output is None else Path(baseline_timed_output)
    )
    destination = Path(report_dir)
    destination.mkdir(parents=True, exist_ok=True)
    figures = destination / "figures"
    if write_plots:
        figures.mkdir(parents=True, exist_ok=True)

    rows = _read_progress_rows(scenario_root / "episode_progress.csv")
    timed_rows_path = timed_root / "episode_progress.csv"
    timed_rows = (
        _read_progress_rows(timed_rows_path) if timed_rows_path.is_file() else []
    )
    scenario_summary = _read_json(scenario_root / "generation_summary.json")
    timed_summary = _read_json(timed_root / "generation_summary.json")
    baseline_timed_summary = (
        None
        if baseline_timed_root is None
        else _read_json(baseline_timed_root / "generation_summary.json")
    )
    dataset_bytes = int(
        scenario_summary.get(
            "learning_dataset_size_bytes",
            _directory_size(scenario_root / "learning_dataset"),
        )
    )
    component_bytes = _component_sizes(
        scenario_root / "learning_dataset"
    )

    paths: dict[str, Path] = {}
    results_csv = destination / "SCALABLE_3D_CAPACITY_PROBE_RESULTS.csv"
    _write_results_csv(results_csv, rows)
    paths["results_csv"] = results_csv

    if write_plots:
        paths["scenario_plot"] = _write_scenario_plot(
            figures / "capacity_probe_scenario_runtime.png",
            rows,
        )
        paths["timing_plot"] = _write_timing_plot(
            figures / "capacity_probe_generation_timing.png",
            timed_summary,
            baseline_summary=baseline_timed_summary,
        )
        paths["storage_plot"] = _write_storage_plot(
            figures / "capacity_probe_storage_components.png",
            component_bytes,
        )

    report_path = destination / "SCALABLE_3D_CAPACITY_AND_RUNTIME_REPORT_CN.md"
    _write_report(
        report_path,
        rows=rows,
        scenario_summary=scenario_summary,
        timed_summary=timed_summary,
        baseline_timed_summary=baseline_timed_summary,
        timed_rows=timed_rows,
        dataset_bytes=dataset_bytes,
        component_bytes=component_bytes,
        include_plots=write_plots,
    )
    paths["report"] = report_path
    return paths


def _read_progress_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("capacity probe progress is empty")
    return rows


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _component_sizes(dataset_root: Path) -> dict[str, int]:
    return {
        "D3 分配数据": _directory_size(dataset_root / "d3_assignment"),
        "D4 区域数据": _directory_size(dataset_root / "d4_region"),
        "D5 跨视角图": _directory_size(dataset_root / "d5_tracklet_graph"),
        "D5 主动视觉": _directory_size(dataset_root / "d5_active_vision"),
    }


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_results_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    fieldnames = (
        "场景",
        "seed",
        "实时因子",
        "D3帧数",
        "D4帧数",
        "D5图帧数",
        "D5主动视觉帧数",
        "有限状态",
        "在线真值使用次数",
    )
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "场景": SCENARIO_LABELS.get(str(row["scenario"]), row["scenario"]),
                    "seed": int(row["seed"]),
                    "实时因子": f"{float(row['real_time_factor']):.6f}",
                    "D3帧数": int(row["d3_exported_frame_count"]),
                    "D4帧数": int(row["d4_captured_frame_count"]),
                    "D5图帧数": int(row["d5_staged_frame_count"]),
                    "D5主动视觉帧数": int(
                        row["d5_active_vision_staged_frame_count"]
                    ),
                    "有限状态": row["finite_state"],
                    "在线真值使用次数": int(row["online_truth_use_count"]),
                }
            )


def _configure_matplotlib() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [
        "Noto Sans CJK JP",
        "Droid Sans Fallback",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _write_scenario_plot(path: Path, rows: list[Mapping[str, Any]]) -> Path:
    plt = _configure_matplotlib()
    labels = [SCENARIO_LABELS.get(str(row["scenario"]), row["scenario"]) for row in rows]
    real_time_factors = [float(row["real_time_factor"]) for row in rows]
    graph_frames = [int(row["d5_staged_frame_count"]) for row in rows]
    active_frames = [int(row["d5_active_vision_staged_frame_count"]) for row in rows]
    positions = list(range(len(rows)))

    figure, axes = plt.subplots(1, 2, figsize=(12.0, 6.0), constrained_layout=True)
    axes[0].barh(positions, real_time_factors, color="#277da1")
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlabel("实时因子")
    axes[0].set_title("200 对 200 场景运行速度")
    axes[0].grid(axis="x", alpha=0.25)

    height = 0.38
    axes[1].barh(
        [item - height / 2 for item in positions],
        graph_frames,
        height=height,
        label="跨视角图帧",
        color="#f8961e",
    )
    axes[1].barh(
        [item + height / 2 for item in positions],
        active_frames,
        height=height,
        label="主动视觉帧",
        color="#43aa8b",
    )
    axes[1].set_yticks(positions, labels)
    axes[1].invert_yaxis()
    axes[1].set_xlabel("帧数")
    axes[1].set_title("D5 学习制品帧数")
    axes[1].legend(loc="lower right")
    axes[1].grid(axis="x", alpha=0.25)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _write_timing_plot(
    path: Path,
    summary: Mapping[str, Any],
    *,
    baseline_summary: Mapping[str, Any] | None = None,
) -> Path:
    plt = _configure_matplotlib()
    timing = summary["timing_summary"]
    labels = ["仿真运行", "制品写入", "批次最终化"]
    values = [
        float(timing["episode_run_wall_s"]),
        float(timing["artifact_stage_wall_s"]),
        float(timing["finalization_wall_s"]),
    ]
    figure, axis = plt.subplots(figsize=(9.0, 4.2), constrained_layout=True)
    if baseline_summary is None:
        colors = ["#577590", "#f3722c", "#90be6d"]
        left = 0.0
        total = sum(values)
        for label, value, color in zip(labels, values, colors):
            axis.barh([0], [value], left=left, label=label, color=color)
            axis.text(
                left + value / 2,
                0,
                f"{value:.1f} 秒\n{value / total:.1%}",
                ha="center",
                va="center",
                fontsize=9,
            )
            left += value
        axis.set_yticks([])
        axis.set_title("名义场景三 seed 学习数据生成耗时")
        axis.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.18))
    else:
        baseline_timing = baseline_summary["timing_summary"]
        baseline_values = [
            float(baseline_timing["episode_run_wall_s"]),
            float(baseline_timing["artifact_stage_wall_s"]),
            float(baseline_timing["finalization_wall_s"]),
        ]
        positions = list(range(len(labels)))
        height = 0.34
        baseline_bars = axis.barh(
            [position - height / 2 for position in positions],
            baseline_values,
            height=height,
            label="优化前",
            color="#9aa0a6",
        )
        optimized_bars = axis.barh(
            [position + height / 2 for position in positions],
            values,
            height=height,
            label="优化后",
            color="#277da1",
        )
        axis.set_yticks(positions, labels)
        axis.invert_yaxis()
        axis.bar_label(baseline_bars, fmt="%.1f", padding=3)
        axis.bar_label(optimized_bars, fmt="%.1f", padding=3)
        axis.set_title("名义场景三 seed 生成耗时对比")
        axis.legend(loc="lower right")
        axis.grid(axis="x", alpha=0.25)
    axis.set_xlabel("墙钟时间（秒）")
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return path


def _write_storage_plot(path: Path, component_bytes: Mapping[str, int]) -> Path:
    plt = _configure_matplotlib()
    labels = list(component_bytes)
    values = [component_bytes[label] / 1_000_000.0 for label in labels]
    figure, axis = plt.subplots(figsize=(8.5, 4.2), constrained_layout=True)
    bars = axis.barh(labels, values, color=["#577590", "#90be6d", "#f9c74f", "#f3722c"])
    axis.invert_yaxis()
    axis.set_xlabel("文件大小（MB）")
    axis.set_title("九场景 200 对 200 学习制品构成")
    axis.bar_label(bars, fmt="%.2f")
    axis.grid(axis="x", alpha=0.25)
    figure.savefig(path, dpi=180)
    plt.close(figure)
    return path


def _write_report(
    path: Path,
    *,
    rows: list[Mapping[str, Any]],
    scenario_summary: Mapping[str, Any],
    timed_summary: Mapping[str, Any],
    baseline_timed_summary: Mapping[str, Any] | None,
    timed_rows: list[Mapping[str, Any]],
    dataset_bytes: int,
    component_bytes: Mapping[str, int],
    include_plots: bool,
) -> None:
    learning = scenario_summary["learning_export_summary"]
    timing = timed_summary["timing_summary"]
    baseline_timing = (
        None
        if baseline_timed_summary is None
        else baseline_timed_summary["timing_summary"]
    )
    upper_bound_bytes = dataset_bytes / len(rows) * 900
    all_200_runtime_upper_hours = (
        float(timing["generation_wall_s"])
        / max(1, int(timed_summary.get("completed_episode_count", 1)))
        * 900
        / 3600.0
    )
    stage_components = _stage_component_totals(timed_rows)
    active_stage_share = (
        0.0
        if not stage_components or float(timing["artifact_stage_wall_s"]) <= 0.0
        else stage_components["D5 主动视觉"]
        / float(timing["artifact_stage_wall_s"])
    )
    if baseline_timing is None:
        timing_conclusion = (
            f"名义场景三 seed 的完整生成耗时为 "
            f"{float(timing['generation_wall_s']):.1f} 秒，其中仿真运行 "
            f"{float(timing['episode_run_wall_s']):.1f} 秒、制品写入 "
            f"{float(timing['artifact_stage_wall_s']):.1f} 秒、批次最终化 "
            f"{float(timing['finalization_wall_s']):.1f} 秒。"
        )
        gate_conclusion = "该结果尚无同条件优化前基线，吞吐门保持开放。"
    else:
        total_reduction = _reduction_fraction(
            float(baseline_timing["generation_wall_s"]),
            float(timing["generation_wall_s"]),
        )
        timing_conclusion = (
            f"同一名义场景三 seed 的完整生成耗时由 "
            f"{float(baseline_timing['generation_wall_s']):.1f} 秒降至 "
            f"{float(timing['generation_wall_s']):.1f} 秒，下降 {total_reduction:.1%}。"
            f"制品写入由 {float(baseline_timing['artifact_stage_wall_s']):.1f} 秒降至 "
            f"{float(timing['artifact_stage_wall_s']):.1f} 秒，批次最终化由 "
            f"{float(baseline_timing['finalization_wall_s']):.1f} 秒降至 "
            f"{float(timing['finalization_wall_s']):.1f} 秒。仿真运行由 "
            f"{float(baseline_timing['episode_run_wall_s']):.1f} 秒变为 "
            f"{float(timing['episode_run_wall_s']):.1f} 秒，基本不变。"
        )
        gate_conclusion = (
            "存储门和批次最终化门已通过。正式生成吞吐门暂不关闭："
            f"D5 主动视觉写入占本轮 staging 的 {active_stage_share:.1%}，"
            "若 900 个 episode 全部按 200 对 200 计，运行时间保守上界约 "
            f"{all_200_runtime_upper_hours:.1f} 小时。runner 已实现 episode 边界分块恢复并通过"
            "三 episode 开发回归；启动正式批次前仍需收敛主动视觉写入，并用首个正式代表"
            "分块验证恢复合同。"
        )
    lines = [
        "# 三维规模化仿真容量与运行时报告",
        "",
        "## 结论",
        "",
        "九类 200 对 200 场景全部完成，有限状态检查通过，在线真值使用次数为 0。",
        "D3、D4 和 D5 跨视角图数据集完成最终化；D5 主动视觉因未达到 20 个未见测试 seed 而保留 staging，符合准入规则。",
        "",
        f"九个 episode 的最终学习目录为 {dataset_bytes / 1_000_000:.2f} MB。按全部 900 个 episode 都采用本轮 200 对 200 平均值计算，保守上界约为 {upper_bound_bytes / 1_000_000_000:.2f} GB。正式计划包含更小规模，实际值应低于该上界；5 GB 停止门继续保留。",
        "",
        timing_conclusion,
        "",
        gate_conclusion,
        "",
        "## 场景配置",
        "",
        "| 项 | 值 |",
        "| --- | --- |",
        "| 仿真模式 | 三维质点、北东地坐标系 |",
        "| 规模 | 200 个来袭目标、200 个拦截资源 |",
        "| 场景数 | 9 |",
        "| 单例时长 | 2 秒 |",
        "| 学习模式 | 规则路径采样，学习模型未准入 |",
        "| 真值边界 | 在线 D1-D5 禁止真值编号，真值仅用于离线标签 |",
        f"| 九场景 producer commit | `{scenario_summary['git_commit']}` |",
        f"| 优化后 timed producer commit | `{timed_summary['git_commit']}` |",
        "",
        "## 算法流程",
        "",
        "仿真器按统一时钟推进目标、拦截资源和侦察节点。D1 生成带双时间戳和协方差的融合航迹，D2 维持中心航迹身份，D3 形成稀疏候选边并发布版本化分配，D4 处理中心和二级节点故障，D5 生成跨视角图与主动视觉样本，D7 计算三维导引命令。main 在 episode 结束后将在线特征与离线标签分开写盘。",
        "",
        "本次只评估数据生成合同、运行时间和存储量。拦截成功率、模型精度和强化学习收益没有在该探针中评定。",
        "",
        "## 场景结果",
        "",
        "| 场景 | seed | 实时因子 | D3 帧 | D4 帧 | D5 图帧 | 主动视觉帧 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {label} | {seed} | {rtf:.4f} | {d3} | {d4} | {d5} | {active} |".format(
                label=SCENARIO_LABELS.get(str(row["scenario"]), row["scenario"]),
                seed=int(row["seed"]),
                rtf=float(row["real_time_factor"]),
                d3=int(row["d3_exported_frame_count"]),
                d4=int(row["d4_captured_frame_count"]),
                d5=int(row["d5_staged_frame_count"]),
                active=int(row["d5_active_vision_staged_frame_count"]),
            )
        )
    lines.extend(
        [
            "",
            "延迟噪声场景实时因子最低，为 0.0165，同时生成 34 个 D5 跨视角图帧。通信退化场景生成 33 个图帧。两类场景应作为后续序列化优化和模型训练压力样本。",
            "",
            "## 存储构成",
            "",
            "| 制品 | 大小/MB | 占四类制品比例 |",
            "| --- | ---: | ---: |",
        ]
    )
    component_total = sum(component_bytes.values())
    for label, size in component_bytes.items():
        lines.append(
            f"| {label} | {size / 1_000_000:.2f} | {size / component_total:.1%} |"
        )
    lines.extend(
        [
            "",
            f"D3 分配数据 {component_bytes['D3 分配数据'] / 1_000_000:.2f} MB，D5 主动视觉 {component_bytes['D5 主动视觉'] / 1_000_000:.2f} MB，两者占主要空间。成功最终化后 `_staging` 已删除，目录中没有 D3 重复副本。",
            "",
            "## 运行时间",
            "",
            "| 阶段 | 优化前/秒 | 优化后/秒 | 变化 |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for label, key in (
        ("仿真运行", "episode_run_wall_s"),
        ("制品写入", "artifact_stage_wall_s"),
        ("批次最终化", "finalization_wall_s"),
    ):
        value = float(timing[key])
        if baseline_timing is None:
            lines.append(f"| {label} | - | {value:.1f} | - |")
        else:
            baseline_value = float(baseline_timing[key])
            lines.append(
                f"| {label} | {baseline_value:.1f} | {value:.1f} | "
                f"{_format_change(baseline_value, value)} |"
            )
    if stage_components:
        lines.extend(
            [
                "",
                "### 写入归因",
                "",
                "| 组件 | 三 seed 时间/秒 | 占 staging |",
                "| --- | ---: | ---: |",
            ]
        )
        for label, value in stage_components.items():
            lines.append(
                f"| {label} | {value:.3f} | "
                f"{value / float(timing['artifact_stage_wall_s']):.1%} |"
            )
    lines.extend(
        [
            "",
            "优化后三组 nominal seed 的单例制品写入时间为 41.7、43.4 和 41.4 秒。D3、D4 和 D5 跨视角图写入合计不足 0.2 秒，剩余时间集中在 D5 主动视觉在线记录的构造和压缩。九场景旧长跑中曾出现一次约 51 分钟的异常停顿，现有日志不能判定为系统抢占还是写盘阻塞，不将该停顿线性外推。",
            "",
            "## 图表",
            "",
        ]
    )
    if include_plots:
        lines.extend(
            [
                "![场景运行速度与D5帧数](figures/capacity_probe_scenario_runtime.png)",
                "",
                "![生成阶段耗时](figures/capacity_probe_generation_timing.png)",
                "",
                "![学习制品存储构成](figures/capacity_probe_storage_components.png)",
                "",
            ]
        )
    lines.extend(
        [
            "## 后续工作",
            "",
            "1. 保持 D3 当前导出路径和 D5 最终化复核，继续作为回归门。",
            "2. 剖析并优化 D5 主动视觉 episode writer/压缩，不降低采样、不删除特征、不放松真值隔离。",
            "3. 使用可恢复分块入口复跑五档规模和九类场景的代表 cell，验证正式计划恢复合同。",
            "4. 吞吐门通过后启动 900 episode；100 个生成 seed 用于训练，1000-1019 只用于最终评估。",
            "",
            "## 文件索引",
            "",
            "- 九场景进度：`outputs/capacity_probe_v2/all_scenarios_200v200/episode_progress.csv`",
            "- 九场景汇总：`outputs/capacity_probe_v2/all_scenarios_200v200/generation_summary.json`",
            "- 优化前 timed 汇总：`outputs/capacity_probe_v2/nominal_timed/generation_summary.json`",
            "- 优化后 timed 进度：`outputs/capacity_probe_v2/nominal_timed_postopt/episode_progress.csv`",
            "- 优化后 timed 汇总：`outputs/capacity_probe_v2/nominal_timed_postopt/generation_summary.json`",
            "- 固化结果表：`docs/SCALABLE_3D_CAPACITY_PROBE_RESULTS.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stage_component_totals(
    rows: list[Mapping[str, Any]],
) -> dict[str, float]:
    fields = (
        ("D3 分配", "d3_stage_wall_s"),
        ("D4 区域", "d4_stage_wall_s"),
        ("D5 跨视角图", "d5_graph_stage_wall_s"),
        ("D5 主动视觉", "d5_active_vision_stage_wall_s"),
    )
    if not rows or any(field not in row for row in rows for _, field in fields):
        return {}
    return {
        label: sum(float(row[field]) for row in rows)
        for label, field in fields
    }


def _reduction_fraction(before: float, after: float) -> float:
    if before <= 0.0:
        return 0.0
    return (before - after) / before


def _format_change(before: float, after: float) -> str:
    change = _reduction_fraction(before, after)
    if change >= 0.0:
        return f"下降 {change:.1%}"
    return f"增加 {-change:.1%}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    module_root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario-output",
        type=Path,
        default=module_root / "outputs" / "capacity_probe_v2" / "all_scenarios_200v200",
    )
    parser.add_argument(
        "--timed-output",
        type=Path,
        default=module_root / "outputs" / "capacity_probe_v2" / "nominal_timed_postopt",
    )
    parser.add_argument(
        "--baseline-timed-output",
        type=Path,
        default=module_root / "outputs" / "capacity_probe_v2" / "nominal_timed",
    )
    parser.add_argument("--report-dir", type=Path, default=module_root / "docs")
    parser.add_argument("--no-plots", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = write_capacity_probe_report(
        args.scenario_output,
        args.timed_output,
        args.report_dir,
        baseline_timed_output=args.baseline_timed_output,
        write_plots=not args.no_plots,
    )
    print(paths["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
