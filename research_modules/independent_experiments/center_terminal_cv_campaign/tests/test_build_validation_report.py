from __future__ import annotations

import json
from pathlib import Path

from center_terminal_cv_campaign.build_validation_report import build_report


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _campaign(path: Path, target_count: int) -> None:
    _write_json(
        path / "campaign_summary.json",
        {
            "mode": "airsim",
            "target_count": target_count,
            "resource_count": 8,
            "seed": 7,
        },
    )
    _write_json(
        path / "fixtures" / f"fixture_n{target_count}_seed7" / "scenario.json",
        {
            "target_speed_mps": 50.0,
            "target_longest_dimension_m": 3.0,
            "clock_speed": 0.1,
        },
    )
    for experiment in ("search", "center_handover", "crossview"):
        _write_json(path / experiment / "metrics.json", {"target_count": target_count})


def test_build_report_reads_metrics_instead_of_hard_coding_results(tmp_path: Path) -> None:
    smoke = tmp_path / "smoke"
    formal = tmp_path / "formal"
    _campaign(smoke, 5)
    _campaign(formal, 20)
    _write_json(
        formal / "search" / "metrics.json",
        {
            "target_count": 20,
            "discovered_target_count": 18,
            "center_missed_target_count": 4,
            "center_missed_recovered_count": 4,
        },
    )
    _write_json(
        formal / "center_handover" / "metrics.json",
        {"true_binding_count": 16, "false_binding_count": 0},
    )
    _write_json(
        formal / "crossview" / "metrics.json",
        {
            "true_positive_relations": 27,
            "false_positive_relations": 4,
            "false_negative_relations": 3,
            "association_precision": 0.871,
            "association_recall": 0.9,
            "id_switch_count": 1,
        },
    )

    output = build_report(smoke, formal, tmp_path / "REPORT_CN.md")
    text = output.read_text(encoding="utf-8")
    assert "18/20" in text
    assert "正确绑定16" in text
    assert "关联精确率为0.871" in text
    assert "真实AirSim ComputerVision" in text
    assert "先修正通用聚类冲突" not in text
    assert "独立随机种子" in text
