from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_scalable_3d_association_hotpath_benchmark import (
    _cycle_timing_diagnostics,
    _load_online_d1_d2_pairs,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def test_hotpath_loader_uses_latest_d1_across_interleaved_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "online_observations.jsonl"
    d1_first = {"sequence": 1, "source": "D1", "payload": {"tracks": []}}
    d1_latest = {"sequence": 2, "source": "D1", "payload": {"tracks": [1]}}
    d2 = {"sequence": 5, "source": "D2", "payload": {"tracks": [1]}}
    _write_jsonl(
        path,
        [
            d1_first,
            d1_latest,
            {"sequence": 3, "source": "MAIN-RUNTIME"},
            {"sequence": 4, "source": "D5"},
            d2,
        ],
    )

    assert _load_online_d1_d2_pairs(path) == ((d1_latest, d2),)


def test_hotpath_loader_rejects_d2_without_preceding_d1(tmp_path: Path) -> None:
    path = tmp_path / "online_observations.jsonl"
    _write_jsonl(path, [{"sequence": 1, "source": "D2"}])

    with pytest.raises(ValueError, match="has no preceding D1"):
        _load_online_d1_d2_pairs(path)


def test_cycle_timing_is_diagnostic_and_keeps_fixed_work_visible() -> None:
    runs = []
    for timing_offset in (0.0, 0.1):
        records = []
        for cycle_index in range(5):
            adapter = 1.0 + timing_offset + cycle_index * 0.1
            tracker = 2.0 + timing_offset + cycle_index * 0.2
            records.append(
                {
                    "cycle_index": cycle_index,
                    "source_sequence": cycle_index + 10,
                    "timestamp": float(cycle_index),
                    "input_detection_count": 200,
                    "fresh_detection_count": 200,
                    "active_track_count": 200,
                    "candidate_edge_count": 200,
                    "observation_claim_count": (cycle_index + 1) * 200,
                    "adapter_seconds": adapter,
                    "tracker_seconds": tracker,
                    "total_seconds": adapter + tracker,
                }
            )
        runs.append({"cycle_records": records})

    diagnostics = _cycle_timing_diagnostics(runs)

    assert diagnostics["timing_assertion_policy"] == (
        "diagnostic_only_no_wall_clock_pass_fail"
    )
    assert diagnostics["regular_window_comparison"][
        "last_cycle_excluded_as_finalize"
    ] is True
    assert diagnostics["regular_window_comparison"]["early_cycle_indices"] == [
        0,
        1,
    ]
    assert diagnostics["regular_window_comparison"]["late_cycle_indices"] == [
        2,
        3,
    ]
    assert diagnostics["cycles"][4]["observation_claim_count"] == 1000
