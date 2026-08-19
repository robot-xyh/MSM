from __future__ import annotations

import json
import zipfile

from dual_optical_100target_lightweight.evaluation import evaluate_frozen
from dual_optical_100target_lightweight.pipeline import train_validate_and_freeze
from dual_optical_100target_lightweight.reporting import generate_report


def test_fixture_report_is_chinese_illustrated_and_builds_word(tmp_path):
    report = generate_report(tmp_path / "docs")
    text = report.read_text(encoding="utf-8")
    assert "不包含正式100目标测试结果" in text
    assert "AirSim测量、离线腐化和建议门限" in text
    assert len(list((report.parent / "figures").glob("*.png"))) == 3
    word = report.with_suffix(".docx")
    assert word.is_file()
    assert zipfile.is_zipfile(word)


def test_evaluation_report_uses_measured_metrics(dataset_manifest, tmp_path):
    freeze = train_validate_and_freeze(dataset_manifest, tmp_path / "model")
    metrics = evaluate_frozen(
        freeze,
        tmp_path / "evaluation",
        latency_repeats=1,
        bootstrap_resamples=20,
    )
    report = generate_report(tmp_path / "report", metrics_path=metrics, build_word=False)
    text = report.read_text(encoding="utf-8")
    values = json.loads(metrics.read_text(encoding="utf-8"))
    assert f"{values['independent_seed_count']}个独立seed" in text
    assert "不是实测探测器误差分布" in text
    assert "不是设备通用指标" in text
    assert len(list((report.parent / "figures").glob("*.png"))) == 8
