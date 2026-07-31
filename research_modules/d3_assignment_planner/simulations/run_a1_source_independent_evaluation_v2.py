#!/usr/bin/env python3
"""Run the frozen D3 A1 source-independent evaluation v2 contract once."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d3_assignment_planner.a1_source_independent_evaluation import (  # noqa: E402
    A1_SOURCE_INDEPENDENT_MODE,
)
from d3_assignment_planner.a1_source_independent_evaluation_v2 import (  # noqa: E402
    run_a1_source_independent_evaluation_v2,
)


DEFAULT_CONTRACT = (
    MODULE_ROOT
    / "configs"
    / "a1_source_independent_evaluation_contract_v2.json"
)
DEFAULT_BUNDLE = (
    MODULE_ROOT
    / "results"
    / "a1_assignment_aware_development_v1_20260730"
    / "bundle"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--generation-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=(A1_SOURCE_INDEPENDENT_MODE,),
        required=True,
    )
    arguments = parser.parse_args(argv)
    result = run_a1_source_independent_evaluation_v2(
        contract_path=arguments.contract,
        bundle_dir=arguments.bundle,
        generation_root=arguments.generation_root,
        dataset_dir=arguments.dataset,
        output_dir=arguments.output,
        module_root=MODULE_ROOT,
        mode=arguments.mode,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
