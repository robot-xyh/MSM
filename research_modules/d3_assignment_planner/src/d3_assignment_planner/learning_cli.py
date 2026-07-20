"""Command-line entry points for the optional D3 learning research pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from .learning import FeatureDistributionGuard
from .learning_bundle import (
    NormalizedPolicyPredictor,
    load_model_bundle,
    save_model_bundle,
)
from .learning_data import (
    generate_synthetic_learning_dataset,
    load_learning_dataset,
)
from .learning_training import train_behavior_cloning, train_native_ppo
from .native_ppo import SharedEdgeActorCriticPolicy
from .shadow_evaluation import (
    evaluate_shadow_pairs,
    update_bundle_promotion_manifest,
    write_shadow_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="D3 sparse residual BC/PPO/shadow research pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate-data", help="write deterministic 3v5/5v3 synthetic smoke data"
    )
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--seed-start", type=int, default=0)
    generate.add_argument("--seed-count", type=int, default=30)
    generate.add_argument("--episodes-per-seed", type=int, default=2)
    generate.add_argument("--frames-per-episode", type=int, default=4)
    generate.add_argument("--scenario-version", default="d3_synthetic_sparse_v1")

    bc = subparsers.add_parser("train-bc", help="train rule behavior cloning bundle")
    bc.add_argument("--dataset", type=Path, required=True)
    bc.add_argument("--bundle", type=Path, required=True)
    bc.add_argument("--epochs", type=int, default=20)
    bc.add_argument("--mini-batch-frames", type=int, default=8)
    bc.add_argument("--learning-rate", type=float, default=1.0e-3)
    bc.add_argument("--hidden-size", type=int, default=64)
    bc.add_argument("--seed", type=int, default=0)
    _add_guardrail_arguments(bc)

    ppo = subparsers.add_parser("train-ppo", help="train native clipped PPO bundle")
    ppo.add_argument("--dataset", type=Path, required=True)
    ppo.add_argument("--bundle", type=Path, required=True)
    ppo.add_argument("--input-bundle", type=Path)
    ppo.add_argument("--updates", type=int, default=2)
    ppo.add_argument("--epochs-per-update", type=int, default=4)
    ppo.add_argument("--mini-batch-frames", type=int, default=8)
    ppo.add_argument("--learning-rate", type=float, default=3.0e-4)
    ppo.add_argument("--clip-ratio", type=float, default=0.2)
    ppo.add_argument("--hidden-size", type=int, default=64)
    ppo.add_argument("--seed", type=int, default=0)
    _add_guardrail_arguments(ppo)

    shadow = subparsers.add_parser(
        "shadow-eval", help="run same-seed paired rule/shadow evaluation"
    )
    shadow.add_argument("--dataset", type=Path, required=True)
    shadow.add_argument("--bundle", type=Path, required=True)
    shadow.add_argument("--output", type=Path, required=True)
    shadow.add_argument("--split", choices=("validation", "test"), default="test")
    shadow.add_argument("--minimum-unseen-seeds", type=int, default=20)
    shadow.add_argument(
        "--promotion-evidence",
        action="store_true",
        help="mark a non-synthetic dataset as formal promotion evidence",
    )
    shadow.add_argument(
        "--no-update-bundle",
        action="store_true",
        help="do not attach the promotion decision to the bundle manifest",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate-data":
        if args.seed_count < 1:
            raise SystemExit("--seed-count must be positive")
        manifest = generate_synthetic_learning_dataset(
            args.output,
            seeds=tuple(range(args.seed_start, args.seed_start + args.seed_count)),
            episodes_per_seed=args.episodes_per_seed,
            frames_per_episode=args.frames_per_episode,
            scenario_version=args.scenario_version,
        )
        _print_json(manifest.to_dict())
        return 0

    dataset_manifest, records = load_learning_dataset(args.dataset)
    if args.command == "train-bc":
        policy = SharedEdgeActorCriticPolicy(hidden_size=args.hidden_size)
        policy, result = train_behavior_cloning(
            records,
            policy=policy,
            epochs=args.epochs,
            mini_batch_frames=args.mini_batch_frames,
            learning_rate=args.learning_rate,
            seed=args.seed,
        )
        bundle = save_model_bundle(
            args.bundle,
            policy,
            split_hash=dataset_manifest.split_hash,
            normalization_mean=result.normalization_mean,
            normalization_scale=result.normalization_scale,
            training_results=result.to_dict(),
            alpha=args.alpha,
            min_confidence=args.min_confidence,
            ood_z_threshold=args.ood_z_threshold,
            deadline_s=args.deadline_s,
        )
        _print_json(
            {
                "command": args.command,
                "bundle": str(args.bundle),
                "state_dict_sha256": bundle.state_dict_sha256,
                **result.to_dict(),
            }
        )
        return 0

    if args.command == "train-ppo":
        policy: SharedEdgeActorCriticPolicy
        mean: Sequence[float] | None = None
        scale: Sequence[float] | None = None
        prior_results = None
        if args.input_bundle is not None:
            loaded = load_model_bundle(
                args.input_bundle,
                mode="shadow",
                expected_split_hash=dataset_manifest.split_hash,
            )
            if not loaded.loaded or loaded.policy is None or loaded.manifest is None:
                raise SystemExit(
                    f"input bundle unavailable: {loaded.fallback_reason or 'unknown'}"
                )
            policy = loaded.policy
            mean = loaded.manifest.normalization_mean
            scale = loaded.manifest.normalization_scale
            prior_results = dict(loaded.manifest.training_results)
        else:
            policy = SharedEdgeActorCriticPolicy(hidden_size=args.hidden_size)
        policy, result = train_native_ppo(
            records,
            policy=policy,
            updates=args.updates,
            epochs_per_update=args.epochs_per_update,
            mini_batch_frames=args.mini_batch_frames,
            learning_rate=args.learning_rate,
            clip_ratio=args.clip_ratio,
            seed=args.seed,
            normalization_mean=mean,
            normalization_scale=scale,
        )
        training_results = result.to_dict()
        if prior_results is not None:
            training_results = {
                "warm_start": prior_results,
                "ppo": result.to_dict(),
            }
        bundle = save_model_bundle(
            args.bundle,
            policy,
            split_hash=dataset_manifest.split_hash,
            normalization_mean=result.normalization_mean,
            normalization_scale=result.normalization_scale,
            training_results=training_results,
            alpha=args.alpha,
            min_confidence=args.min_confidence,
            ood_z_threshold=args.ood_z_threshold,
            deadline_s=args.deadline_s,
        )
        _print_json(
            {
                "command": args.command,
                "bundle": str(args.bundle),
                "state_dict_sha256": bundle.state_dict_sha256,
                **result.to_dict(),
            }
        )
        return 0

    if args.command == "shadow-eval":
        loaded = load_model_bundle(
            args.bundle,
            mode="shadow",
            expected_split_hash=dataset_manifest.split_hash,
        )
        if not loaded.loaded or loaded.policy is None or loaded.manifest is None:
            raise SystemExit(
                f"shadow bundle unavailable: {loaded.fallback_reason or 'unknown'}"
            )
        manifest = loaded.manifest
        predictor = NormalizedPolicyPredictor(
            loaded.policy,
            manifest.normalization_mean,
            manifest.normalization_scale,
        )
        guard = FeatureDistributionGuard(
            mean=np.asarray(manifest.normalization_mean, dtype=np.float32),
            scale=np.asarray(manifest.normalization_scale, dtype=np.float32),
        )
        evidence_eligible = bool(
            args.promotion_evidence
            and dataset_manifest.source_kind not in {"synthetic", "synthetic_smoke"}
            and args.split == "test"
        )
        report = evaluate_shadow_pairs(
            records,
            predictor,
            alpha=manifest.alpha,
            split=args.split,
            min_confidence=manifest.min_confidence,
            deadline_s=manifest.deadline_s,
            distribution_guard=guard,
            ood_z_threshold=manifest.ood_z_threshold,
            minimum_unseen_seeds=args.minimum_unseen_seeds,
            evidence_eligible=evidence_eligible,
        )
        write_shadow_report(args.output, report)
        if not args.no_update_bundle:
            update_bundle_promotion_manifest(args.bundle, report.promotion_manifest)
        _print_json(
            {
                "command": args.command,
                "output": str(args.output),
                **report.to_dict(include_frames=False),
            }
        )
        return 0
    raise AssertionError(f"unhandled command: {args.command}")


def _add_guardrail_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--alpha", type=float, default=0.25)
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--ood-z-threshold", type=float, default=6.0)
    parser.add_argument("--deadline-s", type=float, default=0.05)


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
