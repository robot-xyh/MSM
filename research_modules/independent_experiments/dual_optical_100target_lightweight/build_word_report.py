"""Reuse the proven Markdown-to-Word builder for this isolated report."""

from __future__ import annotations

import argparse
from pathlib import Path

from dual_optical_100target_gnn.build_word_report import build_word_report as _build


def build_word_report(source: str | Path, output: str | Path | None = None) -> Path:
    return _build(source, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    print(build_word_report(args.source, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
