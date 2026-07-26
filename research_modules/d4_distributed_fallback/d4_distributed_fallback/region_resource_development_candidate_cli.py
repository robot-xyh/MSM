"""CLI for the evidence-bound D4 regional development candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .region_resource_development_candidate import (
    REGION_RESOURCE_DEVELOPMENT_CANDIDATE_ID,
    REGION_RESOURCE_DEVELOPMENT_MODEL_VERSION,
    RegionResourceDevelopmentCandidateConfig,
    build_region_resource_development_candidate,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a calibrated D4 development/shadow candidate. "
            "The command cannot emit qualified or assist authority."
        )
    )
    parser.add_argument("--formal-dataset", type=Path, required=True)
    parser.add_argument("--supplemental-dataset", type=Path, required=True)
    parser.add_argument("--training-seed-registry", type=Path, required=True)
    parser.add_argument("--shared-seed-registry", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tracked-report-dir", type=Path)
    parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--message-passing-steps", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=70)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--learning-rate", type=float, default=8.0e-4)
    parser.add_argument("--weight-decay", type=float, default=1.0e-5)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--supplemental-repeat", type=int, default=5)
    parser.add_argument("--nonzero-action-weight", type=float, default=6.0)
    parser.add_argument("--positive-binary-weight", type=float, default=8.0)
    parser.add_argument("--confidence-epochs", type=int, default=50)
    parser.add_argument(
        "--confidence-learning-rate", type=float, default=2.0e-3
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--torch-num-threads", type=int, default=1)
    parser.add_argument(
        "--model-version", default=REGION_RESOURCE_DEVELOPMENT_MODEL_VERSION
    )
    parser.add_argument(
        "--candidate-id", default=REGION_RESOURCE_DEVELOPMENT_CANDIDATE_ID
    )
    parser.add_argument("--replace-output", action="store_true")
    parser.add_argument("--replace-tracked-report", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = RegionResourceDevelopmentCandidateConfig(
        random_seed=args.seed,
        hidden_dim=args.hidden_dim,
        message_passing_steps=args.message_passing_steps,
        epochs=args.epochs,
        early_stopping_patience=args.patience,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        max_grad_norm=args.max_grad_norm,
        supplemental_repeat=args.supplemental_repeat,
        nonzero_continuous_weight=args.nonzero_action_weight,
        positive_binary_weight=args.positive_binary_weight,
        confidence_epochs=args.confidence_epochs,
        confidence_learning_rate=args.confidence_learning_rate,
        model_version=args.model_version,
        candidate_id=args.candidate_id,
        device=args.device,
        torch_num_threads=args.torch_num_threads,
    )
    result = build_region_resource_development_candidate(
        args.formal_dataset,
        args.supplemental_dataset,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
        output_dir=args.output_dir,
        tracked_report_dir=args.tracked_report_dir,
        config=config,
        replace_output=args.replace_output,
        replace_tracked_report=args.replace_tracked_report,
    )
    manifest = result["candidate_manifest"]
    calibration = result["calibration_report"]
    print(
        json.dumps(
            {
                "candidate_id": manifest["candidate_id"],
                "model_version": manifest["model_version"],
                "candidate_manifest_sha256": manifest["content_sha256"],
                "model_state_sha256": manifest["model_state_sha256"],
                "training_seeds": manifest["train_seeds"],
                "validation_seeds": manifest["validation_seeds"],
                "calibration_seeds": manifest["calibration_seeds"],
                "candidate_gate_pass_count": calibration["gate"]["pass_count"],
                "candidate_sample_count": calibration["sample_count"],
                "latency_p95_ms": calibration["latency_ms"]["p95"],
                "ood_rejected_count": calibration["ood"][
                    "hard_gate_rejected_count"
                ],
                "assist_enabled": manifest["assist_enabled"],
                "authority_enabled": manifest["authority_enabled"],
                "output_dir": result["output_dir"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
