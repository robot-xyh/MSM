#!/usr/bin/env python3
"""Run the strict D6 paired isolated physical evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
for candidate in (REPOSITORY_ROOT, MODULE_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from d6_evaluation_metrics.paired_isolated_physical import (  # noqa: E402
    load_paired_isolated_physical_inputs,
    write_paired_isolated_physical_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "校验隔离 control/treatment 多周期计划消费、D7 控制血缘和五米物理结果，"
            "输出 availability-aware 描述性配对比较"
        )
    )
    parser.add_argument(
        "--inputs-json",
        type=Path,
        required=True,
        help="带版本的输入路径和 SHA-256 清单",
    )
    parser.add_argument(
        "--inputs-sha256",
        required=True,
        help="输入清单文件的带外 SHA-256",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="与所有输入隔离的输出目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = load_paired_isolated_physical_inputs(
        args.inputs_json,
        expected_sha256=args.inputs_sha256,
    )
    paths = write_paired_isolated_physical_report(inputs, args.output_dir)
    print(
        json.dumps(
            {name: str(path) for name, path in sorted(paths.items())},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
