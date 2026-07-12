#!/usr/bin/env python3
"""Run the isolated D7 P2 3D guidance benchmark and write CSV/JSON results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d7_proportional_guidance import (  # noqa: E402
    DEFAULT_OPTIONAL_P2_LAWS,
    OptionalP2BenchmarkConfig,
    run_optional_p2_benchmark_suite,
    summarize_optional_p2_benchmark,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run isolated 3D PN/True PN/APN/FRPN point-mass benchmarks."
    )
    parser.add_argument("--seeds", default="7,17,27")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-duration", type=float, default=12.0)
    parser.add_argument("--dt", type=float, default=0.02)
    args = parser.parse_args()

    seeds = tuple(int(item.strip()) for item in args.seeds.split(",") if item.strip())
    if not seeds:
        parser.error("--seeds must contain at least one integer")
    config = OptionalP2BenchmarkConfig(
        dt_s=args.dt,
        max_duration_s=args.max_duration,
    )
    results = run_optional_p2_benchmark_suite(
        seeds=seeds,
        laws=DEFAULT_OPTIONAL_P2_LAWS,
        config=config,
    )
    summary = summarize_optional_p2_benchmark(results)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    result_rows = [result.as_dict() for result in results]
    csv_path = args.output_dir / "optional_p2_benchmark_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[key for key in result_rows[0] if key != "metadata"],
        )
        writer.writeheader()
        writer.writerows(
            {key: value for key, value in row.items() if key != "metadata"}
            for row in result_rows
        )

    bundle = {
        "summary": summary,
        "config": {
            "dt_s": config.dt_s,
            "max_duration_s": config.max_duration_s,
            "navigation_constant": config.navigation_constant,
            "max_acceleration_mps2": config.max_acceleration_mps2,
            "intercept_radius_m": config.intercept_radius_m,
        },
        "results": result_rows,
    }
    json_path = args.output_dir / "optional_p2_benchmark_summary.json"
    json_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path = args.output_dir / "optional_p2_benchmark_report.md"
    report_path.write_text(_render_markdown_report(summary, seeds), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _render_markdown_report(summary: dict[str, object], seeds: tuple[int, ...]) -> str:
    laws = summary["laws"]
    assert isinstance(laws, dict)
    lines = [
        "# D7 P2 隔离式三维导引 Benchmark 报告",
        "",
        f"固定 seeds：{', '.join(str(seed) for seed in seeds)}。本报告只针对离线恒速质点/replay，"
        "不替换 D7 默认在线控制路径，也未修改 png_guidance_delivery。",
        "",
        "| 导引律 | 运行数 | 命中率 | 平均最小脱靶量 (m) | 平均控制努力 (m/s) | 平均耗时 (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for law_name, metrics in laws.items():
        lines.append(
            "| {law} | {runs} | {hit:.3f} | {miss:.3f} | {effort:.3f} | {runtime:.6f} |".format(
                law=law_name,
                runs=metrics["run_count"],
                hit=metrics["hit_rate"],
                miss=metrics["min_miss_distance_m_mean"],
                effort=metrics["control_effort_mps_mean"],
                runtime=metrics["compute_time_s_mean"],
            )
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- `frpn_research_approximation` 是确定性的鲁棒增益调度 PN 研究近似，"
            "不是经过论文逐式复现或模糊规则验证的标准 FRPN。",
            "- 命中表示质点距离进入配置的 intercept radius，不表示 AirSim 或实机物理命中。",
            "- 控制努力定义为加速度模长的时间积分；耗时是 Python 离线计算墙钟时间。",
            "- 所有目标 truth/replay 只用于离线 benchmark，不进入 D3/D4/D5/D7 在线合同。",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
