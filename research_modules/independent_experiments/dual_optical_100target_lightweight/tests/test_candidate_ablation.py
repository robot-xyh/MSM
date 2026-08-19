from __future__ import annotations

import json
from dataclasses import asdict, replace

import pytest

from dual_optical_100target_lightweight import ablation, cli
from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    SnapshotTrack,
    SnapshotTrackSample,
    candidate_graph_fingerprint,
)


def _unit_snapshot():
    protocol = BenchmarkProtocol()
    sample = SnapshotTrackSample(
        sweep_index=1,
        timestamp=1.0,
        direction_ned=(1.0, 0.0, 0.0),
        detection_count=1,
        bbox_area_px2=9.0,
        confidence=0.8,
    )
    pair = ("A-1", "B-1")
    summary = {"builder_version": "unit", "retained_pair_count": 1}
    from dual_optical_online_benchmark.contracts import RevolutionSnapshot

    return RevolutionSnapshot(
        protocol_fingerprint=protocol.fingerprint,
        seed=protocol.test_seeds[0],
        split="test",
        corruption_level="medium",
        revolution_index=1,
        cutoff_timestamp=2.0,
        camera_ids=("A", "B"),
        camera_positions_ned={"A": (0.0, 0.0, 0.0), "B": (0.0, 1.0, 0.0)},
        focal_length_px=1000.0,
        tracks={
            "A": (SnapshotTrack("A-1", "A", (sample,)),),
            "B": (SnapshotTrack("B-1", "B", (sample,)),),
        },
        target_count=20,
        tracker_fingerprint="unit-tracker",
        geometry_candidate_pairs=(pair,),
        candidate_graph_fingerprint=candidate_graph_fingerprint((pair,), summary),
        candidate_graph_summary=summary,
    )


def _row(
    mode: str,
    level: str,
    seed: int,
    *,
    recall: float,
    correct: int = 8,
    matches: int = 10,
) -> dict[str, object]:
    precision = correct / matches if matches else 0.0
    f1 = 2.0 * precision * recall / max(precision + recall, 1.0e-12)
    return {
        "mode": mode,
        "seed": seed,
        "corruption_level": level,
        "revolution_index": 3,
        "source_input_fingerprint": f"{seed:064x}",
        "full_pair_count": 10000,
        "evaluated_pair_count": 500 if mode == "shared_allowlist" else 10000,
        "candidate_edge_count": 400 if mode == "shared_allowlist" else 1200,
        "probability_accepted_edge_count": 120,
        "hungarian_selected_count": matches,
        "candidate_true_edge_retention_rate": recall,
        "match_count": matches,
        "correct_match_count": correct,
        "false_association_count": matches - correct,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "deadline_met": True,
        "candidate_generation_ms": 2.0,
        "model_scoring_ms": 1.0,
        "hungarian_assignment_ms": 1.0,
        "confirmation_and_publication_ms": 0.2,
        "end_to_end_ms": 4.2,
    }


def _paired_rows(
    *,
    medium_shared_recall: float = 0.80,
    medium_baseline_recall: float = 0.78,
    heavy_shared_recall: float = 0.72,
    heavy_baseline_recall: float = 0.70,
    shared_correct: int = 8,
) -> list[dict[str, object]]:
    rows = []
    for level, shared_recall, baseline_recall in (
        ("medium", medium_shared_recall, medium_baseline_recall),
        ("heavy", heavy_shared_recall, heavy_baseline_recall),
    ):
        for seed in (101, 102, 103):
            rows.append(
                _row(
                    "shared_allowlist",
                    level,
                    seed,
                    recall=shared_recall,
                    correct=shared_correct,
                )
            )
            rows.append(
                _row(
                    "legacy_all_pairs",
                    level,
                    seed,
                    recall=baseline_recall,
                )
            )
    return rows


def test_promotion_gate_allows_nonnegative_medium_and_heavy_evidence():
    decision = ablation.promotion_decision(
        _paired_rows(), bootstrap_resamples=100, bootstrap_seed=7
    )

    assert decision["promotion_allowed"] is True
    assert decision["stop_before_next_scale"] is False
    assert decision["stop_reasons"] == []


@pytest.mark.parametrize(
    ("level", "kwargs"),
    (
        (
            "medium",
            {
                "medium_shared_recall": 0.74,
                "medium_baseline_recall": 0.78,
            },
        ),
        (
            "heavy",
            {
                "heavy_shared_recall": 0.66,
                "heavy_baseline_recall": 0.70,
            },
        ),
    ),
)
def test_medium_or_heavy_negative_recall_stops_scale_promotion(level, kwargs):
    decision = ablation.promotion_decision(
        _paired_rows(**kwargs), bootstrap_resamples=100, bootstrap_seed=11
    )

    assert decision["promotion_allowed"] is False
    assert decision["stop_before_next_scale"] is True
    assert f"{level}_shared_allowlist_negative_recall" in decision["stop_reasons"]
    assert decision["levels"][level]["negative_recall_detected"] is True


def test_statistically_negative_recall_stops_even_below_two_point_threshold():
    decision = ablation.promotion_decision(
        _paired_rows(
            heavy_shared_recall=0.69,
            heavy_baseline_recall=0.70,
        ),
        bootstrap_resamples=100,
        bootstrap_seed=13,
    )

    interval = decision["levels"]["heavy"][
        "shared_minus_baseline_recall_95ci"
    ]
    assert interval["point"] > ablation.NEGATIVE_RECALL_DELTA
    assert interval["upper"] < 0.0
    assert decision["promotion_allowed"] is False


def test_missing_noise_evidence_and_precision_below_floor_fail_closed():
    missing = [
        row
        for row in _paired_rows()
        if row["corruption_level"] != "heavy"
    ]
    missing_decision = ablation.promotion_decision(
        missing, bootstrap_resamples=50
    )
    assert missing_decision["promotion_allowed"] is False
    assert "heavy_evidence_missing" in missing_decision["stop_reasons"]

    low_precision = ablation.promotion_decision(
        _paired_rows(shared_correct=6), bootstrap_resamples=50
    )
    assert low_precision["promotion_allowed"] is False
    assert "medium_conditional_precision_below_0.70" in low_precision[
        "stop_reasons"
    ]
    assert "heavy_conditional_precision_below_0.70" in low_precision[
        "stop_reasons"
    ]


def test_paired_ablation_rejects_different_source_snapshots():
    rows = _paired_rows()
    baseline = next(
        row
        for row in rows
        if row["mode"] == "legacy_all_pairs"
        and row["corruption_level"] == "medium"
    )
    baseline["source_input_fingerprint"] = "f" * 64

    with pytest.raises(ValueError, match="identical unique source snapshots"):
        ablation.promotion_decision(rows, bootstrap_resamples=20)


def test_same_input_ablation_changes_candidate_contract_only():
    source = _unit_snapshot()
    shared = ablation._snapshot_for_mode(source, "shared_allowlist")
    legacy = ablation._snapshot_for_mode(source, "legacy_all_pairs")
    shared_values = asdict(shared)
    legacy_values = asdict(legacy)

    for field in (
        "geometry_candidate_pairs",
        "candidate_graph_fingerprint",
        "candidate_graph_summary",
    ):
        shared_values.pop(field)
        legacy_values.pop(field)

    assert shared is source
    assert legacy_values == shared_values
    assert legacy.geometry_candidate_pairs == ()
    assert legacy.candidate_graph_fingerprint == ""
    assert legacy.candidate_graph_summary == {}


def test_unknown_candidate_ablation_mode_is_rejected():
    with pytest.raises(ValueError, match="unsupported candidate ablation mode"):
        ablation._snapshot_for_mode(_unit_snapshot(), "online_all_pairs")


def test_cli_returns_nonzero_when_candidate_route_must_stop(tmp_path, monkeypatch):
    summary_path = tmp_path / "candidate_ablation_summary.json"
    summary_path.write_text(
        json.dumps({"promotion_gate": {"promotion_allowed": False}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli,
        "run_candidate_ablation",
        lambda *args, **kwargs: summary_path,
    )

    return_code = cli.main(
        [
            "candidate-ablation",
            "--test-manifest",
            "test.json",
            "--freeze-manifest",
            "freeze.json",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert return_code == 2
