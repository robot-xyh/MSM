from __future__ import annotations

import argparse
import json
from pathlib import Path

from d1_sensor_fusion import (
    run_structural_ambiguity_centroid_replay_diagnostic,
    write_structural_ambiguity_replay_diagnostic,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run D1's frozen structural-ambiguity centroid boundary diagnostic."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "research_modules/d1_sensor_fusion/reports/"
            "structural_ambiguity_centroid_replay_20260723"
        ),
    )
    args = parser.parse_args()
    report = run_structural_ambiguity_centroid_replay_diagnostic()
    paths = write_structural_ambiguity_replay_diagnostic(
        args.output_dir,
        report,
    )
    print(
        json.dumps(
            {
                "passed": report["acceptance"]["passed"],
                "json": str(paths["json"]),
                "markdown": str(paths["markdown"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
