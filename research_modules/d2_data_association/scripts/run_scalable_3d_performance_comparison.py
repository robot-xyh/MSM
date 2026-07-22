#!/usr/bin/env python3
"""Compare frozen scalable-3D D2 episode semantics and timings."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from d2_data_association.scalable_3d_performance import (
    compare_scalable_3d_d2_performance,
    write_scalable_3d_d2_performance_comparison,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument(
        "--relative-scenario-dir",
        type=Path,
        default=Path("nominal/200v200"),
    )
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()

    report = compare_scalable_3d_d2_performance(
        args.baseline_root,
        args.candidate_root,
        relative_scenario_dir=args.relative_scenario_dir,
        seeds=args.seeds,
    )
    digest = write_scalable_3d_d2_performance_comparison(args.output, report)
    if args.plot is not None:
        _write_plot(args.plot, report)
    print(f"seed_count={report['seed_count']}")
    print(f"all_semantics_equal={report['all_semantics_equal']}")
    print(f"all_online_truth_free={report['all_online_truth_free']}")
    print(f"report_sha256={digest}")
    print(f"output={args.output.resolve()}")
    if args.plot is not None:
        print(f"plot={args.plot.resolve()}")


def _write_plot(path: Path, report: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    path.parent.mkdir(parents=True, exist_ok=True)
    font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
    else:
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    episodes = report["episodes"]
    seeds = [str(item["seed"]) for item in episodes]
    baseline_association = [
        item["timing"]["baseline_association_seconds"] for item in episodes
    ]
    candidate_association = [
        item["timing"]["candidate_association_seconds"] for item in episodes
    ]
    baseline_finalize = [
        item["timing"]["baseline_finalize_seconds"] for item in episodes
    ]
    candidate_finalize = [
        item["timing"]["candidate_finalize_seconds"] for item in episodes
    ]

    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), constrained_layout=True)
    axes[0].plot(seeds, baseline_association, marker="o", label="优化前")
    axes[0].plot(seeds, candidate_association, marker="o", label="优化后")
    axes[0].set_title("常规关联阶段")
    axes[0].set_xlabel("随机种子")
    axes[0].set_ylabel("累计耗时（秒）")
    axes[0].grid(alpha=0.25)
    axes[0].legend()

    axes[1].plot(seeds, baseline_finalize, marker="o", label="优化前")
    axes[1].plot(seeds, candidate_finalize, marker="o", label="优化后")
    axes[1].set_title("尾部收束阶段")
    axes[1].set_xlabel("随机种子")
    axes[1].set_ylabel("累计耗时（秒）")
    axes[1].grid(alpha=0.25)
    axes[1].legend()
    figure.suptitle("D2 200 对 200 五组运行耗时对比")
    figure.savefig(path, dpi=180)
    plt.close(figure)


if __name__ == "__main__":
    main()
