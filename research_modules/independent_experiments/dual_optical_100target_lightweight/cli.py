"""Command-line interface for the isolated lightweight baseline."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .ablation import run_candidate_ablation
from .benchmark_adapter import read_shared_snapshot
from .evaluation import evaluate_frozen
from .online_benchmark import freeze_route, load_frozen_route
from .pipeline import TrainingConfig, train_validate_and_freeze
from .reporting import generate_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="双站光电100目标轻量关联独立试验"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="只读取训练/验证集并写出冻结清单")
    train.add_argument("--dataset-manifest", required=True)
    train.add_argument("--output-dir", required=True)
    train.add_argument("--random-seed", type=int, default=20260820)

    evaluate = subparsers.add_parser("evaluate", help="核对冻结清单后读取保留测试集")
    evaluate.add_argument("--freeze-manifest", required=True)
    evaluate.add_argument("--output-dir", required=True)
    evaluate.add_argument("--latency-repeats", type=int, default=20)
    evaluate.add_argument("--bootstrap-resamples", type=int, default=2000)
    evaluate.add_argument("--bootstrap-seed", type=int, default=20260901)

    report = subparsers.add_parser("report", help="生成中文Markdown、图表和Word")
    report.add_argument("--output-dir", required=True)
    report.add_argument("--metrics")
    report.add_argument("--no-word", action="store_true")

    online_train = subparsers.add_parser(
        "online-freeze", help="读取main校准清单并冻结轻量在线路线"
    )
    online_train.add_argument("--dataset-manifest", required=True)
    online_train.add_argument("--output-dir", required=True)

    online_run = subparsers.add_parser(
        "online-run", help="读取冻结模型和main公共快照并发布轻量关联结果"
    )
    online_run.add_argument("--freeze-manifest", required=True)
    online_run.add_argument("--snapshot", required=True)
    online_run.add_argument("--output", required=True)

    ablation = subparsers.add_parser(
        "candidate-ablation",
        help="离线同输入比较共享候选白名单与旧全对全候选",
    )
    ablation.add_argument("--test-manifest", required=True)
    ablation.add_argument("--freeze-manifest", required=True)
    ablation.add_argument("--output-dir", required=True)
    ablation.add_argument("--bootstrap-seed", type=int, default=20260813)
    ablation.add_argument("--bootstrap-resamples", type=int, default=2000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    promotion_blocked = False
    if args.command == "train":
        path = train_validate_and_freeze(
            args.dataset_manifest,
            args.output_dir,
            config=TrainingConfig(random_seed=args.random_seed),
        )
    elif args.command == "evaluate":
        path = evaluate_frozen(
            args.freeze_manifest,
            args.output_dir,
            latency_repeats=args.latency_repeats,
            bootstrap_resamples=args.bootstrap_resamples,
            bootstrap_seed=args.bootstrap_seed,
        )
    elif args.command == "report":
        path = generate_report(
            args.output_dir,
            metrics_path=args.metrics,
            build_word=not args.no_word,
        )
    elif args.command == "online-freeze":
        path = freeze_route(
            Path(args.dataset_manifest),
            Path(args.output_dir),
        )
    elif args.command == "online-run":
        adapter = load_frozen_route(Path(args.freeze_manifest))
        publication = adapter.publish(read_shared_snapshot(args.snapshot))
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(publication), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif args.command == "candidate-ablation":
        path = run_candidate_ablation(
            args.test_manifest,
            args.freeze_manifest,
            args.output_dir,
            bootstrap_seed=args.bootstrap_seed,
            bootstrap_resamples=args.bootstrap_resamples,
        )
        summary = json.loads(path.read_text(encoding="utf-8"))
        promotion_blocked = not bool(
            summary["promotion_gate"]["promotion_allowed"]
        )
    else:
        raise AssertionError(f"unhandled command: {args.command}")
    print(path)
    return 2 if promotion_blocked else 0
