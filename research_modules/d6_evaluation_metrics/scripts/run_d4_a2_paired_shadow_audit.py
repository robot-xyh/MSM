#!/usr/bin/env python3
"""Run the read-only D4 A2/R0 paired-shadow audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d4_a2_paired_shadow_audit import (  # noqa: E402
    audit_d4_a2_paired_shadow,
    write_d4_a2_paired_shadow_audit,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="审计 D4 current-lineage A2 与独立 R0 的逐 seed 影子配对证据。"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = audit_d4_a2_paired_shadow(
        payload,
        artifact_root=args.artifact_root,
    )
    paths = write_d4_a2_paired_shadow_audit(args.output_dir, result)
    print(paths["json"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
