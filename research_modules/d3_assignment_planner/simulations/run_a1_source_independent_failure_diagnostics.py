#!/usr/bin/env python3
"""Diagnose the frozen D3 A1 v2 result and freeze a v3 source request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d3_assignment_planner.a1_source_independent_failure_diagnostics import (  # noqa: E402
    A1FailureDiagnosticInputs,
    diagnose_a1_source_independent_v2,
    write_a1_failure_diagnostics,
)


DEFAULT_RESULT = (
    MODULE_ROOT / "results/a1_source_independent_evaluation_v2_20260731"
)
DEFAULT_CONTRACT = (
    MODULE_ROOT / "configs/a1_source_independent_evaluation_contract_v2.json"
)
DEFAULT_BUNDLE = (
    MODULE_ROOT / "results/a1_assignment_aware_development_v1_20260730/bundle"
)
DEFAULT_D6_AUDIT = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/reports/"
    "D3_A1_SOURCE_INDEPENDENT_V2_EXTERNAL_AUDIT_20260731/audit.json"
)
DEFAULT_MAIN_REPORT = REPOSITORY_ROOT / "subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md"
DEFAULT_REQUEST = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_development_data_request_v1.json"
)
DEFAULT_SEED_REGISTRY = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_seed_exclusion_registry_v1.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, default=DEFAULT_RESULT)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--d6-audit", type=Path, default=DEFAULT_D6_AUDIT)
    parser.add_argument("--main-report", type=Path, default=DEFAULT_MAIN_REPORT)
    parser.add_argument("--data-request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--seed-registry", type=Path, default=DEFAULT_SEED_REGISTRY)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--analysis-id",
        default="d3-a1-v2-failure-attribution-v3-source-request-20260801-v1",
    )
    parser.add_argument("--analyzed-at-utc", required=True)
    arguments = parser.parse_args(argv)
    result = diagnose_a1_source_independent_v2(
        A1FailureDiagnosticInputs(
            repository_root=REPOSITORY_ROOT,
            result_dir=arguments.result,
            contract_path=arguments.contract,
            bundle_dir=arguments.bundle,
            d6_audit_path=arguments.d6_audit,
            main_report_path=arguments.main_report,
            data_request_path=arguments.data_request,
            seed_registry_path=arguments.seed_registry,
            analysis_id=arguments.analysis_id,
            analyzed_at_utc=arguments.analyzed_at_utc,
        )
    )
    paths = write_a1_failure_diagnostics(arguments.output, result)
    print(
        json.dumps(
            {
                "status": result.summary["status"],
                "content_sha256": result.summary["content_sha256"],
                "output_files": {name: str(path) for name, path in paths.items()},
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
