"""CLI validation for D4 reserved-seed paired-intervention contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .region_resource_paired_intervention import (
    RegionResourcePairedInterventionManifest,
    RegionResourcePairedInterventionSpecification,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and canonically round-trip D4 paired-intervention JSON. "
            "Validation does not run PPO or claim held-out performance."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate-spec", "validate-manifest"):
        child = subparsers.add_parser(command)
        child.add_argument("--input", type=Path, required=True)
        child.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = _load_json(args.input)
    if not isinstance(payload, dict):
        raise ValueError("paired intervention input must be a JSON object")
    if args.command == "validate-spec":
        contract = RegionResourcePairedInterventionSpecification.from_dict(payload)
    elif args.command == "validate-manifest":
        contract = RegionResourcePairedInterventionManifest.from_dict(payload)
    else:  # pragma: no cover - argparse enforces the command set.
        raise RuntimeError(f"unsupported command: {args.command}")
    _emit(contract.to_dict(), args.output)
    return 0


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit(payload: Any, output: Path | None) -> None:
    serialized = json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
