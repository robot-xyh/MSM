from __future__ import annotations

import json
from pathlib import Path

import pytest

from d3_assignment_planner.learning_cli import main


def test_generate_bc_ppo_and_shadow_cli_pipeline_uses_tmp_bundles(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("torch")
    dataset = tmp_path / "dataset"
    bc_bundle = tmp_path / "bc_bundle"
    ppo_bundle = tmp_path / "ppo_bundle"
    shadow_report = tmp_path / "shadow.json"

    assert main(
        [
            "generate-data",
            "--output",
            str(dataset),
            "--seed-count",
            "30",
            "--episodes-per-seed",
            "1",
            "--frames-per-episode",
            "1",
        ]
    ) == 0
    assert main(
        [
            "train-bc",
            "--dataset",
            str(dataset),
            "--bundle",
            str(bc_bundle),
            "--epochs",
            "1",
            "--mini-batch-frames",
            "16",
            "--hidden-size",
            "8",
            "--min-confidence",
            "0",
        ]
    ) == 0
    assert main(
        [
            "train-ppo",
            "--dataset",
            str(dataset),
            "--input-bundle",
            str(bc_bundle),
            "--bundle",
            str(ppo_bundle),
            "--updates",
            "1",
            "--epochs-per-update",
            "1",
            "--mini-batch-frames",
            "16",
            "--min-confidence",
            "0",
        ]
    ) == 0
    assert main(
        [
            "shadow-eval",
            "--dataset",
            str(dataset),
            "--bundle",
            str(ppo_bundle),
            "--output",
            str(shadow_report),
        ]
    ) == 0
    capsys.readouterr()

    report = json.loads(shadow_report.read_text(encoding="utf-8"))
    bundle_manifest = json.loads(
        (ppo_bundle / "manifest.json").read_text(encoding="utf-8")
    )
    assert report["frame_count"] > 0
    assert report["promotion_manifest"]["promotion_recommended"] is False
    assert report["promotion_manifest"]["promotion_status"] == "unavailable"
    assert bundle_manifest["promotion_manifest"] == report["promotion_manifest"]
