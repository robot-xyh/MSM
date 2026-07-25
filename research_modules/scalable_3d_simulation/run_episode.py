#!/usr/bin/env python3
"""Run one scalable three-dimensional point-mass baseline episode."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.episode_bus import (
    ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION,
    ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
)
from research_modules.scalable_3d_simulation.learning_runtime import (
    add_learning_runtime_arguments,
    learning_runtime_options_from_args,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.module_stack import (
    D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION,
    D1_CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION,
    D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION,
    D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION,
    IntegratedStackConfig,
    SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
    SCAN_INPUT_REFERENCE_IMPLEMENTATION,
)


DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--drone-count",
        type=int,
        default=None,
        help="set interceptor count; also sets target count unless --target-count is given",
    )
    parser.add_argument("--target-count", type=int, default=None)
    parser.add_argument("--recon-count", type=int, default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research_modules/scalable_3d_simulation/outputs/episode"),
    )
    parser.add_argument("--plot", action="store_true")
    parser.add_argument(
        "--integrated-stack",
        action="store_true",
        help="run the truth-free D1-D7 rule baseline and write commands back to the world",
    )
    parser.add_argument("--gif", action="store_true", help="write a 3D GIF from offline truth")
    parser.add_argument("--mp4", action="store_true", help="write a 3D MP4 when ffmpeg is available")
    parser.add_argument(
        "--export-learning-data",
        action="store_true",
        help="write truth-isolated D3/D4/D5 offline training artifacts",
    )
    parser.add_argument(
        "--d5-recon-track-cues",
        action="store_true",
        help=(
            "give recon cameras truth-free observation cues from the current "
            "versioned assignment plan; disabled by default"
        ),
    )
    parser.add_argument(
        "--d1-radar-assignment-ambiguity-governance-v2",
        action="store_true",
        help=(
            "enable the experimental D1 radar assignment ambiguity v2 policy; "
            "disabled by default"
        ),
    )
    parser.add_argument(
        "--d1-d2-structural-ambiguity-hold",
        action="store_true",
        help=(
            "enable the experimental atomic D1 evidence and D2 bounded-hold "
            "candidate; disabled by default"
        ),
    )
    parser.add_argument(
        "--d1-publish-opaque-source-key",
        action="store_true",
        help=(
            "publish D1 opaque source keys without enabling structural "
            "ambiguity suppression; intended for the source-only control arm"
        ),
    )
    parser.add_argument(
        "--d1-identity-neutral-centroid-correction",
        action="store_true",
        help=(
            "enable the experimental D1 identity-neutral centroid state "
            "correction; requires --d1-d2-structural-ambiguity-hold"
        ),
    )
    parser.add_argument(
        "--d1-centroid-publication-overlay-shadow",
        action="store_true",
        help=(
            "evaluate the detached D1 centroid publication overlay as an "
            "audit-only shadow; requires --d1-d2-structural-ambiguity-hold "
            "and never feeds D2 or D3"
        ),
    )
    parser.add_argument(
        "--d1-scan-input-implementation",
        choices=(
            SCAN_INPUT_REFERENCE_IMPLEMENTATION,
            SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
        ),
        default=SCAN_INPUT_CANDIDATE_IMPLEMENTATION,
        help=(
            "select the D1 scan-input A/B implementation; candidate_v2 is "
            "the default and both arms preserve the same business semantics"
        ),
    )
    parser.add_argument(
        "--d1-publication-metadata-implementation",
        choices=(
            D1_PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION,
            D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION,
        ),
        default=D1_PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION,
        help=(
            "select the D1 GlobalTrack publication metadata A/B "
            "implementation; the formally admitted immutable shared v2 path "
            "is the default and per_track_copy_v1 remains the reference"
        ),
    )
    parser.add_argument(
        "--d1-cv-motion-model-implementation",
        choices=(
            D1_CV_MOTION_MODEL_REFERENCE_IMPLEMENTATION,
            D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION,
        ),
        default=D1_CV_MOTION_MODEL_CANDIDATE_IMPLEMENTATION,
        help=(
            "select D1 constant-velocity model construction; the "
            "formally admitted bounded exact LRU path is the default and the "
            "per-prediction implementation remains an explicit reference"
        ),
    )
    parser.add_argument(
        "--d1-cv-motion-model-cache-capacity",
        type=int,
        default=128,
        help=(
            "set the bounded exact LRU capacity in [1, 4096]; the value is "
            "hashed and audited even when the reference implementation is "
            "selected"
        ),
    )
    parser.add_argument(
        "--online-truth-guard-implementation",
        choices=(
            ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
            ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION,
        ),
        default=ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
        help=(
            "select the main episode-bus recursive truth-isolation guard; "
            "the built-in-specialized candidate is explicit and default-off"
        ),
    )
    add_learning_runtime_arguments(parser)
    return parser.parse_args(argv)


def load_config(path: Path) -> ScenarioConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ScenarioConfig.from_dict(payload)


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    target_count = args.target_count
    if args.drone_count is not None and target_count is None:
        target_count = args.drone_count
    resolved_resource_count = (
        config.resource_count if args.drone_count is None else args.drone_count
    )
    resolved_target_count = config.target_count if target_count is None else target_count
    scale_overridden = args.drone_count is not None or args.target_count is not None
    updates = {
        "resource_count": resolved_resource_count,
        "target_count": resolved_target_count,
        "recon_count": config.recon_count if args.recon_count is None else args.recon_count,
        "duration_s": config.duration_s if args.duration is None else args.duration,
        "seed": config.seed if args.seed is None else args.seed,
    }
    if scale_overridden:
        updates.update(
            {
                "scenario_name": (
                    f"{config.scenario_name}_cli_"
                    f"{resolved_resource_count}v{resolved_target_count}"
                ),
                "scenario_version": (
                    f"{config.scenario_version}-cli-"
                    f"{resolved_resource_count}v{resolved_target_count}"
                ),
            }
        )
    config = replace(config, **updates)
    learning_options = learning_runtime_options_from_args(args)
    module_stack = None
    if args.integrated_stack:
        resolved_runtime = resolve_learning_runtime(
            config,
            learning_options,
            stack_config=IntegratedStackConfig(
                capture_learning_artifacts=args.export_learning_data,
                d5_recon_track_cues_enabled=args.d5_recon_track_cues,
                d1_radar_assignment_ambiguity_governance_v2=(
                    args.d1_radar_assignment_ambiguity_governance_v2
                ),
                d1_d2_structural_ambiguity_hold_enabled=(
                    args.d1_d2_structural_ambiguity_hold
                ),
                d1_publish_opaque_source_key=(
                    args.d1_publish_opaque_source_key
                ),
                d1_identity_neutral_centroid_correction_enabled=(
                    args.d1_identity_neutral_centroid_correction
                ),
                d1_centroid_publication_overlay_shadow_enabled=(
                    args.d1_centroid_publication_overlay_shadow
                ),
                d1_scan_input_implementation=(
                    args.d1_scan_input_implementation
                ),
                d1_publication_metadata_implementation=(
                    args.d1_publication_metadata_implementation
                ),
                d1_cv_motion_model_implementation=(
                    args.d1_cv_motion_model_implementation
                ),
                d1_cv_motion_model_cache_capacity=(
                    args.d1_cv_motion_model_cache_capacity
                ),
            ),
        )
        config = resolved_runtime.config
        module_stack = resolved_runtime.stack
    elif learning_options.requested:
        raise ValueError("optional learning bundles require --integrated-stack")
    elif args.export_learning_data:
        raise ValueError("--export-learning-data requires --integrated-stack")
    animation_formats = tuple(
        name for name, enabled in (("gif", args.gif), ("mp4", args.mp4)) if enabled
    )
    result = run_episode(
        config,
        output_dir=args.output,
        write_plot=args.plot,
        animation_formats=animation_formats,
        module_stack=module_stack,
        write_learning_data=args.export_learning_data,
        online_truth_guard_implementation=(
            args.online_truth_guard_implementation
        ),
    )
    print(f"episode_id={result.manifest.episode_id}")
    print(f"scale={config.resource_count}v{config.target_count}")
    print(f"finite_state={result.summary['finite_state']}")
    print(f"online_truth_use_count={result.summary['online_truth_use_count']}")
    print(f"online_observation_count={result.summary['online_observation_count']}")
    print(f"module_stack_enabled={result.summary['module_stack_enabled']}")
    print(f"real_time_factor={result.summary['real_time_factor']:.3f}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
