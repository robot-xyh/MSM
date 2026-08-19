"""Command line interface; it never launches AirSim."""

from __future__ import annotations

import argparse
from pathlib import Path

from .build_word_report import build_word_report
from .comparison import compare_files
from .confirmation_ablation import run_confirmation_ablation
from .dataset import prepare_causal_dataset, prepare_dataset
from .evaluation import evaluate_frozen
from .loader import discover_seed_inputs
from .reporting import generate_report
from .schema import CAUSAL_FORMAL_SPLITS, DEFAULT_SPLITS
from .training import TrainingConfig, train_and_freeze
from .online_benchmark import freeze_route
from .online import CONFIRMATION_STRATEGIES
from dual_optical_online_benchmark.contracts import benchmark_protocol_for_target_count


def _inputs(args: argparse.Namespace) -> dict[int, Path]:
    found: dict[int, Path] = {}
    if args.input_root:
        found.update(discover_seed_inputs(args.input_root))
    for value in args.input or []:
        seed_text, separator, path_text = value.partition("=")
        if not separator:
            raise ValueError("--input must use SEED=/episode/path")
        seed = int(seed_text)
        if seed in found:
            raise ValueError(f"duplicate input seed: {seed}")
        found[seed] = Path(path_text).resolve()
    return found


def _split_values(values: list[str] | None, default: tuple[int, ...]) -> tuple[int, ...]:
    if not values:
        return default
    return tuple(int(value) for item in values for value in item.split(",") if value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="build hashed graphs from completed episodes")
    prepare.add_argument("--input-root")
    prepare.add_argument("--input", action="append")
    prepare.add_argument("--dataset-dir", required=True)
    prepare.add_argument("--train-seeds", action="append")
    prepare.add_argument("--val-seeds", action="append")
    prepare.add_argument("--test-seeds", action="append")
    prepare.add_argument("--target-count", type=int, default=100)

    prepare_online = subparsers.add_parser(
        "prepare-online",
        help="build six causal prefixes for the fixed 24/6/20 online protocol",
    )
    prepare_online.add_argument("--input-root")
    prepare_online.add_argument("--input", action="append")
    prepare_online.add_argument("--dataset-dir", required=True)
    prepare_online.add_argument("--train-seeds", action="append")
    prepare_online.add_argument("--val-seeds", action="append")
    prepare_online.add_argument("--test-seeds", action="append")
    prepare_online.add_argument("--target-count", type=int, default=100)

    train = subparsers.add_parser("train", help="train/validate and freeze without opening test files")
    train.add_argument("--dataset-manifest", required=True)
    train.add_argument("--output-dir", required=True)
    train.add_argument("--max-epochs", type=int, default=80)
    train.add_argument("--patience", type=int, default=10)
    train.add_argument("--device", default="auto")

    freeze_online = subparsers.add_parser(
        "freeze-online",
        help="run five fixed initializations and freeze one causal online route",
    )
    freeze_online.add_argument("--dataset-manifest", required=True)
    freeze_online.add_argument("--output-dir", required=True)
    freeze_online.add_argument("--device", default="auto")

    confirmation_ablation = subparsers.add_parser(
        "confirmation-ablation",
        help="replay anonymous test snapshots under a diagnostic confirmation strategy",
    )
    confirmation_ablation.add_argument("--test-manifest", required=True)
    confirmation_ablation.add_argument("--freeze-manifest", required=True)
    confirmation_ablation.add_argument("--output-dir", required=True)
    confirmation_ablation.add_argument(
        "--strategy",
        choices=CONFIRMATION_STRATEGIES,
        required=True,
    )
    confirmation_ablation.add_argument("--device", default="auto")
    confirmation_ablation.add_argument(
        "--split",
        choices=("test", "validation"),
        default="test",
    )
    confirmation_ablation.add_argument("--probability-threshold", type=float)
    confirmation_ablation.add_argument("--margin", type=float)
    confirmation_ablation.add_argument("--diagnostic-mode", action="store_true")

    evaluate = subparsers.add_parser("evaluate", help="evaluate a frozen model on reserved test seeds")
    evaluate.add_argument("--freeze-manifest", required=True)
    evaluate.add_argument("--output-dir", required=True)
    evaluate.add_argument("--latency-repeats", type=int, default=10)
    evaluate.add_argument("--bootstrap-repeats", type=int, default=5000)

    compare = subparsers.add_parser(
        "compare", help="compare the frozen GNN route with an external lightweight export"
    )
    compare.add_argument("--gnn-export", required=True)
    compare.add_argument("--external-baseline-export", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--bootstrap-repeats", type=int, default=5000)
    compare.add_argument("--bootstrap-seed", type=int, default=20260820)

    report = subparsers.add_parser("report", help="generate Chinese Markdown and Word reports")
    report.add_argument("--output-dir", required=True)
    report.add_argument("--metrics")
    report.add_argument("--comparison")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        inputs = _inputs(args)
        splits = {
            "train": _split_values(args.train_seeds, DEFAULT_SPLITS["train"]),
            "val": _split_values(args.val_seeds, DEFAULT_SPLITS["val"]),
            "test": _split_values(args.test_seeds, DEFAULT_SPLITS["test"]),
        }
        print(
            prepare_dataset(
                inputs,
                args.dataset_dir,
                splits=splits,
                expected_target_count=args.target_count,
            )
        )
    elif args.command == "prepare-online":
        inputs = _inputs(args)
        tier = benchmark_protocol_for_target_count(args.target_count)
        splits = {
            "train": _split_values(
                args.train_seeds, tier.train_seeds
            ),
            "val": _split_values(args.val_seeds, tier.validation_seeds),
            "test": _split_values(
                args.test_seeds, tier.test_seeds
            ),
        }
        print(
            prepare_causal_dataset(
                inputs,
                args.dataset_dir,
                splits=splits,
                expected_target_count=args.target_count,
            )
        )
    elif args.command == "train":
        config = TrainingConfig(
            max_epochs=args.max_epochs,
            patience=args.patience,
            device=args.device,
        )
        print(train_and_freeze(args.dataset_manifest, args.output_dir, config=config))
    elif args.command == "freeze-online":
        print(
            freeze_route(
                Path(args.dataset_manifest),
                Path(args.output_dir),
                device=args.device,
            )
        )
    elif args.command == "confirmation-ablation":
        print(
            run_confirmation_ablation(
                args.test_manifest,
                args.freeze_manifest,
                args.output_dir,
                confirmation_strategy=args.strategy,
                device=args.device,
                graded_probability_threshold=args.probability_threshold,
                graded_margin=args.margin,
                diagnostic_mode=args.diagnostic_mode,
                input_split=args.split,
            )
        )
    elif args.command == "evaluate":
        print(
            evaluate_frozen(
                args.freeze_manifest,
                args.output_dir,
                latency_repeats=args.latency_repeats,
                bootstrap_repeats=args.bootstrap_repeats,
            )
        )
    elif args.command == "compare":
        print(
            compare_files(
                args.gnn_export,
                args.external_baseline_export,
                args.output,
                repeats=args.bootstrap_repeats,
                random_seed=args.bootstrap_seed,
            )
        )
    elif args.command == "report":
        report_path = generate_report(
            args.output_dir,
            metrics_path=args.metrics,
            comparison_path=args.comparison,
        )
        print(report_path)
        print(build_word_report(report_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
