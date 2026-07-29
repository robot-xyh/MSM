"""CLI for the clean-lineage D4 A2 development candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .region_resource_current_lineage_candidate import (
    REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID,
    REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION,
    RegionResourceCurrentLineageCandidateConfig,
    build_region_resource_current_lineage_candidate,
    review_region_resource_current_lineage_candidate,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build or review a clean-lineage D4 regional development/shadow "
            "candidate. There is no dirty-worktree or permission bypass."
        )
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--replace-output", action="store_true")
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--message-passing-steps", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=8.0e-4)
    parser.add_argument("--weight-decay", type=float, default=1.0e-5)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--patience", type=int, default=10)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--torch-num-threads", type=int, default=1)
    parser.add_argument(
        "--model-version",
        default=REGION_RESOURCE_CURRENT_LINEAGE_MODEL_VERSION,
    )
    parser.add_argument(
        "--candidate-id",
        default=REGION_RESOURCE_CURRENT_LINEAGE_CANDIDATE_ID,
    )
    parser.add_argument(
        "--created-at-utc",
        default="2026-07-28T00:00:00Z",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.review_only:
        review = review_region_resource_current_lineage_candidate(
            args.output_dir,
            dataset_dir=args.dataset,
            repository_root=args.repository_root,
        )
        print(json.dumps(review.to_dict(), sort_keys=True))
        return 0

    config = RegionResourceCurrentLineageCandidateConfig(
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
        candidate_id=args.candidate_id,
        created_at_utc=args.created_at_utc,
    )
    result = build_region_resource_current_lineage_candidate(
        args.dataset,
        repository_root=args.repository_root,
        output_dir=args.output_dir,
        config=config,
        replace_output=args.replace_output,
    )
    manifest = result["candidate_manifest"]
    review = result["review"]
    print(
        json.dumps(
            {
                "candidate_id": manifest["candidate_id"],
                "model_version": manifest["model_version"],
                "source_identity_sha256": manifest[
                    "source_identity_sha256"
                ],
                "dataset_sha256": manifest["dataset_sha256"],
                "dataset_split_sha256": manifest["dataset_split_sha256"],
                "model_state_sha256": manifest["model_state_sha256"],
                "training_seed_count": len(
                    manifest["split_usage"]["train_seeds"]
                ),
                "validation_seed_count": len(
                    manifest["split_usage"]["validation_seeds"]
                ),
                "test_payload_read_count": manifest["split_usage"][
                    "test_payload_read_count"
                ],
                "calibration_seed_use_count": manifest["split_usage"][
                    "calibration_seed_use_count"
                ],
                "reserved_seed_use_count": manifest["split_usage"][
                    "reserved_seed_use_count"
                ],
                "development_shadow_candidate": manifest[
                    "development_shadow_candidate"
                ],
                "a2_admitted": review["a2_admitted"],
                "authority_granted": review["authority_granted"],
                "control_authority_granted": review[
                    "control_authority_granted"
                ],
                "output_dir": result["output_dir"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
