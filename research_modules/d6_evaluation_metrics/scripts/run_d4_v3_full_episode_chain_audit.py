#!/usr/bin/env python3
"""Run the strict D6 replay audit for one D4 v3 full episode pair."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

from d6_evaluation_metrics.d4_v3_full_episode_chain_audit import (  # noqa: E402
    audit_d4_v3_full_episode_chain,
    write_d4_v3_full_episode_chain_audit,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--sha256sums-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = audit_d4_v3_full_episode_chain(
        args.input_root,
        expected_sha256sums_sha256=args.sha256sums_sha256,
    )
    paths = write_d4_v3_full_episode_chain_audit(args.output_dir, result)
    print(f"json={paths['json']}")
    print(f"markdown={paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
