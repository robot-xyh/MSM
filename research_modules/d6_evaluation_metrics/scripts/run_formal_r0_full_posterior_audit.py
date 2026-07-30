#!/usr/bin/env python3
"""Run the independent 900-cell formal R0 posterior audit."""

from __future__ import annotations

import argparse
from pathlib import Path

from d6_evaluation_metrics.formal_r0_full_posterior_audit import (
    audit_formal_r0_full_posterior,
    load_formal_r0_full_posterior_audit_inputs,
    write_formal_r0_full_posterior_audit,
    write_formal_r0_full_posterior_docs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the complete clean-source 900-cell formal R0 scope."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--docs-dir", type=Path)
    args = parser.parse_args()

    inputs = load_formal_r0_full_posterior_audit_inputs(args.config)
    result = audit_formal_r0_full_posterior(inputs)
    paths = write_formal_r0_full_posterior_audit(
        args.output_dir,
        result,
    )
    if args.docs_dir is not None:
        for name, path in write_formal_r0_full_posterior_docs(
            args.docs_dir,
            result,
        ).items():
            paths[f"docs_{name}"] = path
    for name, path in paths.items():
        print(f"{name}={path}")
    print(f"verdict={result['verdict']}")
    print(
        "verified_cells="
        f"{result['aggregate']['verified_cell_count']}/"
        f"{result['aggregate']['audit_denominator']}"
    )
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
