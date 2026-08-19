#!/usr/bin/env python3
"""Train and freeze the synthetic center-handover sparse GNN on CPU."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PACKAGE_PARENT = Path(__file__).resolve().parents[2]
if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

from center_terminal_cv_campaign.exp_center_handover.gnn import (  # noqa: E402
    TrainingConfig,
    model_manifest_path,
    save_model,
    train_sparse_gnn,
)
from center_terminal_cv_campaign.exp_center_handover.replay import (  # noqa: E402
    reject_replay_as_training_input,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-model", type=Path, required=True)
    parser.add_argument("--train-seeds", type=_integer_list, required=True)
    parser.add_argument("--validation-seeds", type=_integer_list, required=True)
    parser.add_argument("--target-counts", type=_integer_list, default=(20, 40))
    parser.add_argument(
        "--frame-timestamps", type=_float_list, default=(0.2, 0.3, 0.4)
    )
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--learning-rate", type=float, default=2.0e-3)
    parser.add_argument("--random-seed", type=int, default=20260701)
    parser.add_argument("--source-position-sigma-m", type=float, default=12.0)
    parser.add_argument(
        "--train-replay-manifest",
        type=Path,
        help="Fail-closed guard; saved AirSim replay training is not enabled.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.train_replay_manifest is not None:
        reject_replay_as_training_input(args.train_replay_manifest)
    config = TrainingConfig(
        train_seeds=tuple(args.train_seeds),
        validation_seeds=tuple(args.validation_seeds),
        target_counts=tuple(args.target_counts),
        frame_timestamps=tuple(args.frame_timestamps),
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        random_seed=args.random_seed,
        source_position_sigma_m=args.source_position_sigma_m,
        device="cpu",
    )
    model, metrics = train_sparse_gnn(config)
    output = save_model(
        args.output_model,
        model,
        config=config,
        validation_metrics=metrics,
    )
    print(f"model={output.resolve()}")
    print(f"manifest={model_manifest_path(output).resolve()}")
    print("validation=" + json.dumps(metrics, sort_keys=True))
    return 0


def _integer_list(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not result:
        raise argparse.ArgumentTypeError("list cannot be empty")
    return result


def _float_list(value: str) -> tuple[float, ...]:
    try:
        result = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from exc
    if not result:
        raise argparse.ArgumentTypeError("list cannot be empty")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
