"""Command-line entry point for audited D4 regional behavior cloning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .region_resource_training import (
    RegionBehaviorCloningConfig,
    audit_region_learning_dataset,
    publish_region_behavior_cloning_results,
    train_region_behavior_cloning,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit D4 regional data and train a shadow-only BC model."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="verify a finalized dataset")
    audit.add_argument("--dataset", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)

    train = subparsers.add_parser(
        "train-bc", help="train an audited development behavior-cloning model"
    )
    train.add_argument("--dataset", type=Path, required=True)
    train.add_argument("--output-dir", type=Path, required=True)
    train.add_argument("--seed", type=int, default=20260720)
    train.add_argument("--hidden-dim", type=int, default=64)
    train.add_argument("--message-passing-steps", type=int, default=2)
    train.add_argument("--epochs", type=int, default=80)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--learning-rate", type=float, default=1.0e-3)
    train.add_argument("--weight-decay", type=float, default=1.0e-5)
    train.add_argument("--max-grad-norm", type=float, default=1.0)
    train.add_argument("--patience", type=int, default=12)
    train.add_argument("--device", default="cpu")
    train.add_argument("--torch-num-threads", type=int, default=1)
    train.add_argument(
        "--model-version", default="d4-region-bc-900-development-v1"
    )
    train.add_argument("--d6-audit-frame-count", type=int)
    train.add_argument("--d6-unattributed-transition-frame-count", type=int)
    train.add_argument("--d6-reward-available-count", type=int)
    train.add_argument("--d6-causal-label-available-count", type=int)
    train.add_argument("--d6-counterfactual-available-count", type=int)
    train.add_argument("--d6-audit-artifact-sha256")
    train.add_argument("--replace-output", action="store_true")
    train.add_argument("--tracked-results-dir", type=Path)
    train.add_argument("--bundle-locator")
    train.add_argument("--replace-tracked-results", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        _, report = audit_region_learning_dataset(args.dataset)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "dataset_sha256": report["dataset_sha256"],
                    "episode_count": report["inventory"]["episode_count"],
                    "frame_count": report["inventory"]["frame_count"],
                    "behavior_cloning_development_available": report["readiness"][
                        "behavior_cloning_development_available"
                    ],
                    "ppo_available": report["readiness"]["ppo_available"],
                    "output": str(args.output.resolve()),
                },
                sort_keys=True,
            )
        )
        return 0

    config = RegionBehaviorCloningConfig(
        random_seed=args.seed,
        hidden_dim=args.hidden_dim,
        message_passing_steps=args.message_passing_steps,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        max_grad_norm=args.max_grad_norm,
        early_stopping_patience=args.patience,
        device=args.device,
        torch_num_threads=args.torch_num_threads,
        model_version=args.model_version,
        d6_audit_frame_count=args.d6_audit_frame_count,
        d6_unattributed_transition_frame_count=(
            args.d6_unattributed_transition_frame_count
        ),
        d6_reward_available_count=args.d6_reward_available_count,
        d6_causal_label_available_count=args.d6_causal_label_available_count,
        d6_counterfactual_available_count=args.d6_counterfactual_available_count,
        d6_audit_artifact_sha256=args.d6_audit_artifact_sha256,
    )
    result = train_region_behavior_cloning(
        args.dataset,
        args.output_dir,
        config=config,
        replace_output=args.replace_output,
    )
    tracked_manifest = None
    if args.tracked_results_dir is not None:
        if not args.bundle_locator:
            raise ValueError(
                "--bundle-locator is required with --tracked-results-dir"
            )
        command = " ".join(
            (
                "PYTHONPATH=research_modules/d4_distributed_fallback",
                "python3 -m d4_distributed_fallback.region_resource_training_cli",
                "train-bc",
                f"--dataset {args.dataset}",
                f"--output-dir {args.output_dir}",
                f"--seed {args.seed}",
                f"--hidden-dim {args.hidden_dim}",
                f"--message-passing-steps {args.message_passing_steps}",
                f"--epochs {args.epochs}",
                f"--batch-size {args.batch_size}",
                f"--learning-rate {args.learning_rate}",
                f"--weight-decay {args.weight_decay}",
                f"--max-grad-norm {args.max_grad_norm}",
                f"--patience {args.patience}",
                f"--device {args.device}",
                f"--torch-num-threads {args.torch_num_threads}",
                f"--model-version {args.model_version}",
                f"--d6-audit-frame-count {args.d6_audit_frame_count}",
                (
                    "--d6-unattributed-transition-frame-count "
                    f"{args.d6_unattributed_transition_frame_count}"
                ),
                f"--d6-reward-available-count {args.d6_reward_available_count}",
                (
                    "--d6-causal-label-available-count "
                    f"{args.d6_causal_label_available_count}"
                ),
                (
                    "--d6-counterfactual-available-count "
                    f"{args.d6_counterfactual_available_count}"
                ),
                f"--tracked-results-dir {args.tracked_results_dir}",
                f"--bundle-locator {args.bundle_locator}",
            )
        )
        tracked_manifest = publish_region_behavior_cloning_results(
            result["output_dir"],
            args.tracked_results_dir,
            bundle_locator=args.bundle_locator,
            training_command=command,
            replace_output=args.replace_tracked_results,
        )
    metrics = result["training_metrics"]
    readiness = result["model_readiness"]
    print(
        json.dumps(
            {
                "output_dir": result["output_dir"],
                "state_dict_sha256": readiness["state_dict_sha256"],
                "training_config_sha256": readiness["training_config_sha256"],
                "epochs_completed": metrics["epochs_completed"],
                "best_epoch": metrics["best_epoch"],
                "training_duration_s": metrics["training_duration_s"],
                "maximum_advisor_mode": readiness["maximum_advisor_mode"],
                "assist_eligible": readiness["assist_eligible"],
                "ppo_available": readiness["ppo_available"],
                "tracked_results_manifest": tracked_manifest,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
