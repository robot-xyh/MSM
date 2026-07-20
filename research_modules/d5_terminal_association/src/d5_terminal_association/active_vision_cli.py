"""Small runtime-preflight CLI for the optional active-vision research path."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from .active_vision_bundle import load_active_vision_model_bundle_for_runtime
from .active_vision_contracts import ActiveVisionRuntimeMode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=tuple(item.value for item in ActiveVisionRuntimeMode),
        default=ActiveVisionRuntimeMode.SHADOW.value,
        help="requested runtime mode; CLI defaults to non-actuating shadow",
    )
    parser.add_argument("--bundle-dir", default=None)
    parser.add_argument("--device", default="cpu")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    requested = ActiveVisionRuntimeMode(args.mode)
    policy = (
        None
        if args.bundle_dir is None
        else load_active_vision_model_bundle_for_runtime(args.bundle_dir, device=args.device)
    )
    if requested is ActiveVisionRuntimeMode.DISABLED:
        effective = ActiveVisionRuntimeMode.DISABLED
        fallback = "learning_disabled"
    elif policy is None or not policy.available:
        effective = (
            ActiveVisionRuntimeMode.SHADOW
            if requested is ActiveVisionRuntimeMode.SHADOW
            else ActiveVisionRuntimeMode.DISABLED
        )
        fallback = "bundle_not_configured" if policy is None else policy.failure_reason
    elif requested is ActiveVisionRuntimeMode.ASSIST and not policy.assist_admitted:
        effective = ActiveVisionRuntimeMode.DISABLED
        fallback = "assist_not_admitted"
    else:
        effective = requested
        fallback = None
    print(
        json.dumps(
            {
                "requested_mode": requested.value,
                "effective_mode": effective.value,
                "fallback_reason": fallback,
                "model_fingerprint": (
                    None if policy is None else policy.model_fingerprint
                ),
                "camera_actions_applied": False,
                "preflight_only": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
