#!/usr/bin/env python3
"""Run the strict runtime-ACK to offline-outcome join from a hashed spec."""

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

from d6_evaluation_metrics.runtime_plan_outcome_join import (  # noqa: E402
    load_runtime_plan_outcome_join_inputs,
    write_runtime_plan_outcome_join_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "校验运行时分配确认、D2 离线身份、真值状态和五米接近事件，"
            "输出非奖励的配对进展诊断"
        )
    )
    parser.add_argument(
        "--inputs-json",
        type=Path,
        required=True,
        help="带版本的输入路径/SHA-256 清单",
    )
    parser.add_argument(
        "--inputs-sha256",
        required=True,
        help="输入清单文件的 SHA-256（可带 sha256: 前缀）",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="独立输出目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    inputs = load_runtime_plan_outcome_join_inputs(
        args.inputs_json,
        expected_sha256=args.inputs_sha256,
    )
    paths = write_runtime_plan_outcome_join_report(inputs, args.output_dir)
    print(
        json.dumps(
            {name: str(path) for name, path in paths.items()},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
