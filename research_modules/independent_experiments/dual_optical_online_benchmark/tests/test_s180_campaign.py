from __future__ import annotations

from pathlib import Path

import pytest

from dual_optical_40target.core import scan_yaw_deg, sweep_index
from dual_optical_online_benchmark.cli import _load_protocol
from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    s180_protocol_for_target_count,
)
from dual_optical_online_benchmark.s180_reporting import (
    _configure_plotting,
    _offline_association_diagnostics,
    _summarize,
)
from dual_optical_online_benchmark.tracker_calibration import (
    tracker_candidate_configs,
)
from dual_optical_100target_gnn.training import _expected_shared_revolutions


def test_s180_triangle_scan_reverses_at_one_second_boundary() -> None:
    assert scan_yaw_deg(
        0.0, 0.0, half_span_deg=90.0, period_s=2.0, mode="triangle"
    ) == pytest.approx(-90.0)
    assert scan_yaw_deg(
        1.0, 0.0, half_span_deg=90.0, period_s=2.0, mode="triangle"
    ) == pytest.approx(90.0)
    assert scan_yaw_deg(
        2.0, 0.0, half_span_deg=90.0, period_s=2.0, mode="triangle"
    ) == pytest.approx(-90.0)
    assert [
        sweep_index(value, period_s=2.0, mode="triangle")
        for value in (0.0, 0.999, 1.0, 1.999, 2.0)
    ] == [0, 0, 1, 1, 2]


def test_s180_protocol_files_match_factory() -> None:
    root = Path(__file__).resolve().parents[1] / "protocols"
    for target_count in (20, 40, 60):
        loaded = _load_protocol(
            root / f"s180_targets_{target_count:03d}.json", None
        )
        expected = s180_protocol_for_target_count(target_count)
        assert loaded == expected
        assert loaded.fingerprint == expected.fingerprint


def test_s180_tracker_changes_only_nominal_revisit_period() -> None:
    protocol = s180_protocol_for_target_count(20)
    candidates = tracker_candidate_configs(protocol)
    assert len(candidates) == 1
    config = candidates[0]
    assert config.nominal_sweep_period_s == 1.0
    assert config.maximum_global_hypotheses == 3
    assert config.dormant_retention_sweeps == 3
    assert config.local_k_best == 3
    assert config.maximum_ambiguous_edges == 32


def test_s180_summary_uses_fixed_denominator_and_dynamic_windows() -> None:
    rows = []
    for target_count in (20, 40, 60):
        for route in ("epipolar_mht", "gnn", "track_superglue"):
            for level in ("clean", "light"):
                for round_index in range(1, 13):
                    rows.append(
                        {
                            "target_count": target_count,
                            "route_name": route,
                            "corruption_level": level,
                            "revolution_index": round_index,
                            "match_count": 2,
                            "correct_match_count": 1,
                            "false_association_count": 1,
                            "recall": 1.0 / target_count,
                            "shared_local_truth_count": 2,
                            "fragment_count": 1,
                            "identity_dominance_switch_count": 0,
                            "candidate_pair_count": 4,
                            "single_station_correct_identity_count": 3,
                            "single_station_identity_opportunity_count": 4,
                            "single_station_dominant_observation_count": 18,
                            "single_station_labeled_observation_count": 20,
                            "conditional_dual_correct_pair_count": 1,
                            "conditional_dual_eligible_pair_count": 2,
                            "conditional_dual_correct_identity_count": 1,
                            "conditional_dual_opportunity_identity_count": 2,
                            "end_to_end_ms": 2.0,
                            "deadline_met": True,
                            "timed_out": False,
                            "processing_unavailable": False,
                            "no_confirmed_output": False,
                        }
                    )
    summary = _summarize(rows)
    selected = next(
        item
        for item in summary
        if item["target_count"] == 40
        and item["route_name"] == "gnn"
        and item["corruption_level"] == "light"
        and item["window"] == "rounds_3_to_final"
    )
    assert selected["sample_count"] == 10
    assert selected["association_precision"] == pytest.approx(0.5)
    assert selected["fixed_denominator_coverage"] == pytest.approx(1.0 / 40.0)
    assert selected["single_station_association_coverage"] == pytest.approx(0.75)
    assert selected["single_station_association_precision"] == pytest.approx(0.9)
    assert selected[
        "conditional_dual_station_association_precision"
    ] == pytest.approx(0.5)
    assert selected[
        "conditional_dual_station_association_coverage"
    ] == pytest.approx(0.5)


def test_s180_offline_diagnostics_separate_local_and_conditional_quality() -> None:
    diagnostics = _offline_association_diagnostics(
        camera_track_ids={
            "Optical_A": ("A-1", "A-2", "A-3"),
            "Optical_B": ("B-1", "B-2", "B-3"),
        },
        track_truth_counts={
            "A-1": {"TRUTH-001": 9, "TRUTH-002": 1},
            "A-2": {"TRUTH-002": 4, "TRUTH-003": 6},
            "A-3": {"FA-A-001": 2},
            "B-1": {"TRUTH-001": 10},
            "B-2": {"TRUTH-002": 10},
            "B-3": {"TRUTH-003": 4, "FA-B-001": 1},
        },
        matches=(
            AssociationMatch("A-1", "B-1", 0.9, "confirmed"),
            AssociationMatch("A-2", "B-2", 0.8, "confirmed"),
            AssociationMatch("A-3", "B-3", 0.7, "confirmed"),
        ),
        target_count=3,
    )

    assert diagnostics["single_station_correct_identity_count"] == 3
    assert diagnostics["single_station_identity_opportunity_count"] == 6
    assert diagnostics["single_station_dominant_observation_count"] == 39
    assert diagnostics["single_station_labeled_observation_count"] == 47
    assert diagnostics["conditional_dual_correct_pair_count"] == 1
    assert diagnostics["conditional_dual_eligible_pair_count"] == 1
    assert diagnostics["conditional_dual_correct_identity_count"] == 1
    assert diagnostics["conditional_dual_opportunity_identity_count"] == 1


def test_s180_offline_diagnostics_handle_zero_conditional_opportunity() -> None:
    diagnostics = _offline_association_diagnostics(
        camera_track_ids={"Optical_A": ("A-1",), "Optical_B": ("B-1",)},
        track_truth_counts={
            "A-1": {"TRUTH-001": 10},
            "B-1": {"TRUTH-002": 10},
        },
        matches=(AssociationMatch("A-1", "B-1", 0.9, "confirmed"),),
        target_count=2,
    )

    assert diagnostics["conditional_dual_eligible_pair_count"] == 1
    assert diagnostics["conditional_dual_correct_pair_count"] == 0
    assert diagnostics["conditional_dual_opportunity_identity_count"] == 0
    assert diagnostics["conditional_dual_correct_identity_count"] == 0


def test_s180_frozen_gnn_uses_association_round_period() -> None:
    assert _expected_shared_revolutions(
        {
            "duration_s": 12.0,
            "scan_period_s": 2.0,
            "association_round_period_s": 1.0,
        }
    ) == 12
    assert _expected_shared_revolutions(
        {"duration_s": 12.0, "scan_period_s": 2.0}
    ) == 6


def test_s180_report_uses_an_available_cjk_font() -> None:
    family = _configure_plotting()
    assert family in {
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "AR PL UMing CN",
        "Droid Sans Fallback",
    }
