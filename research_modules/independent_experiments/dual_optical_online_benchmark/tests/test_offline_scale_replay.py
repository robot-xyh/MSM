from dataclasses import asdict
import json
from pathlib import Path

import pytest

from dual_optical_100target_lightweight.online_benchmark import (
    _rank_diagnostic_rows,
)
from dual_optical_online_benchmark.offline_scale_replay import (
    _publication_from_mapping,
    _route_arguments,
    build_transferred_superglue_route,
)
from dual_optical_online_benchmark.contracts import (
    benchmark_protocol_for_target_count,
)


def _row(kind: str, precision: float, recall: float) -> dict[str, object]:
    return {
        "model_kind": kind,
        "model_id": kind,
        "selected_count": 10,
        "correct_count": int(round(precision * 10)),
        "conditional_precision": precision,
        "macro_recall": recall,
        "macro_f1": 2.0 * precision * recall / (precision + recall),
        "false_association_count": 10 - int(round(precision * 10)),
        "duplicate_identity_match_count": 0,
        "probability_threshold": 0.5,
        "unmatched_cost": 0.6,
    }


def test_diagnostic_ranking_prefers_reliability_and_marks_nonformal() -> None:
    rows = [
        _row("weighted_geometry", 0.65, 0.60),
        _row("isotonic_geometry_cost", 0.69, 0.30),
    ]
    ranked = _rank_diagnostic_rows(rows)
    assert ranked[0]["model_kind"] == "isotonic_geometry_cost"
    assert ranked[0]["selection_eligible"] is False
    assert ranked[0]["diagnostic_selection_only"] is True


def test_publication_parser_restores_nested_matches() -> None:
    publication = _publication_from_mapping(
        {
            "route_name": "gnn",
            "route_version": "test",
            "model_fingerprint": "abc",
            "seed": 1,
            "corruption_level": "clean",
            "revolution_index": 3,
            "cutoff_timestamp": 6.0,
            "input_fingerprint": "input",
            "availability": "available",
            "matches": [
                {
                    "track_a_id": "A1",
                    "track_b_id": "B1",
                    "score": 0.9,
                    "decision_state": "confirmed",
                }
            ],
            "rejection_reasons": {},
            "end_to_end_ms": 2.0,
            "deadline_ms": 1000.0,
        }
    )
    assert publication.matches[0].track_b_id == "B1"
    assert publication.deadline_met is True


def test_route_arguments_require_all_parts() -> None:
    parsed = _route_arguments(
        ["gnn=/tmp/gnn.json", "track_superglue=/tmp/superglue.json"]
    )
    assert parsed == {
        "gnn": Path("/tmp/gnn.json"),
        "track_superglue": Path("/tmp/superglue.json"),
    }
    with pytest.raises(ValueError, match="ROUTE=/path"):
        _route_arguments(["gnn"])


def test_superglue_transfer_changes_only_scale_protocol(tmp_path: Path) -> None:
    protocol = benchmark_protocol_for_target_count(40)
    source = tmp_path / "freeze_manifest.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "dual-optical-track-superglue-freeze-v1",
                "route_name": "track_superglue",
                "target_count": 20,
                "protocol_fingerprint_sha256": "source-protocol",
                "validation_selection": {"validation_failed_closed": False},
            }
        ),
        encoding="utf-8",
    )
    target = tmp_path / "test_manifest.json"
    target.write_text(
        json.dumps(
            {
                "phase": "test",
                "protocol": asdict(protocol),
                "protocol_fingerprint": protocol.fingerprint,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "transferred_040.json"

    build_transferred_superglue_route(source, target, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["target_count"] == 40
    assert payload["source_target_count"] == 20
    assert payload["protocol_fingerprint_sha256"] == protocol.fingerprint
    assert payload["offline_diagnostic_selection"] is True
    assert payload["formal_use_allowed"] is False
