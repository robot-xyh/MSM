from __future__ import annotations

import json
from dataclasses import replace

import pytest

from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.learning_export import (
    BatchLearningArtifactWriter,
)
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


def _learning_config() -> ScenarioConfig:
    return ScenarioConfig(
        scenario_name="learning_export_3v3",
        scenario_version="learning-export-3v3-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=1.4,
        seed=31,
        radar_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
        visual_min_bbox_area_px2=0.01,
        recon_visual_min_bbox_area_px2=0.01,
        communication_jitter_s=0.0,
        communication_drop_probability=0.0,
        communication_bandwidth_bytes_per_s=1_000_000_000.0,
    )


def test_episode_exports_separate_d3_d4_d5_learning_artifacts(tmp_path) -> None:
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(capture_learning_artifacts=True)
    )

    result = run_episode(
        _learning_config(),
        module_stack=stack,
        output_dir=tmp_path,
        write_learning_data=True,
    )

    assert result.summary["learning_artifact_capture_enabled"] is True
    assert result.summary["d3_learning_frame_count"] >= 1
    assert result.summary["d4_learning_frame_count"] >= 1
    assert result.summary["d5_learning_graph_frame_count"] >= 1
    export_root = tmp_path / "learning_data"
    summary = json.loads(
        (export_root / "learning_export_summary.json").read_text(encoding="utf-8")
    )
    assert summary["d3"]["exported_frame_count"] >= 1
    assert summary["d4"]["captured_frame_count"] >= 1
    assert summary["d5"]["staged_frame_count"] >= 1
    assert (export_root / "d3_assignment" / "frames.jsonl").is_file()
    assert (export_root / "d4_region_frames.jsonl").is_file()
    graph_files = tuple((export_root / "d5_tracklet_graph" / "graphs").glob("*.npz"))
    label_files = tuple((export_root / "d5_tracklet_graph" / "labels").glob("*.json"))
    assert graph_files
    assert label_files
    assert all(b"TGT-" not in path.read_bytes() for path in graph_files)
    assert any("truth_entity_id" in path.read_text(encoding="utf-8") for path in label_files)
    assert "truth_entity_id" not in (tmp_path / "online_observations.jsonl").read_text(
        encoding="utf-8"
    )


def test_learning_export_rejects_stack_without_capture(tmp_path) -> None:
    with pytest.raises(ValueError, match="capture_learning_artifacts"):
        run_episode(
            _learning_config(),
            module_stack=IntegratedScalableModuleStack(),
            output_dir=tmp_path,
            write_learning_data=True,
        )


def test_batch_export_finalizes_whole_seed_d3_and_d5_datasets(tmp_path) -> None:
    writer = BatchLearningArtifactWriter(tmp_path / "batch_learning")
    for seed in (41, 42, 43):
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(
            replace(_learning_config(), seed=seed),
            module_stack=stack,
            output_dir=tmp_path / f"episode_{seed}",
        )
        writer.stage_episode(
            config=result.config,
            manifest=result.manifest,
            artifacts=stack.learning_artifacts(),
            offline_truth_labels=result.offline_truth_labels,
        )

    paths = writer.finalize()

    assert paths["d3_manifest"].is_file()
    assert paths["d5_manifest"].is_file()
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["episode_count"] == 3
    assert summary["scenario_seed_group_count"] == 3
    assert summary["d3_frame_count"] >= 3
    assert summary["d5_staged_frame_count"] >= 3
    assert summary["d5_dataset_finalized"] is True
