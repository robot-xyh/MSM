from __future__ import annotations

import json

from center_terminal_cv_campaign.aggregate_report import aggregate_campaign


def test_aggregate_keeps_available_and_missing_experiments_explicit(tmp_path) -> None:
    output = tmp_path / "search"
    output.mkdir()
    (output / "metrics.json").write_text(
        json.dumps(
            {
                "target_count": 5,
                "precision": 1.0,
                "recall": 0.8,
                "online_truth_leakage_count": 0,
            }
        ),
        encoding="utf-8",
    )

    paths = aggregate_campaign(tmp_path)
    report = paths["report"].read_text(encoding="utf-8")
    assert "概率区域协同搜索" in report
    assert "中心双光电至机载航迹关联" in report
    assert "缺失" in report
    assert paths["metric_inventory"].exists()
