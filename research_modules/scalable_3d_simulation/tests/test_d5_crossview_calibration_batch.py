from __future__ import annotations

import json
from pathlib import Path

import pytest

import research_modules.scalable_3d_simulation.d5_crossview_calibration_batch as batch_module
from research_modules.scalable_3d_simulation.d5_crossview_calibration_batch import (
    D5_CROSSVIEW_FRAME_INDEX_SCHEMA,
    D5_CROSSVIEW_RESERVED_SEEDS,
    D5CrossviewCalibrationBatchOptions,
    D5CrossviewSeedSummary,
    run_d5_crossview_calibration_batch,
)
from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.d5_crossview_calibration import (
    D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION,
)


ROOT = Path(__file__).resolve().parents[3]
CALIBRATION_CONFIG = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d5_crossview_visibility_calibration_v1.json"
)


def _summary(
    *,
    seed: int,
    loaded_model_frames: int = 0,
    rule_frames: int = 4,
    fallback_frames: int = 4,
) -> D5CrossviewSeedSummary:
    return D5CrossviewSeedSummary(
        seed=seed,
        episode_id=f"fixture-{seed}",
        config_sha256=f"{seed:064x}",
        finite_state=True,
        online_truth_use_count=0,
        visual_target_observation_count=12,
        visual_false_alarm_count=0,
        d5_publication_count=4,
        graph_frame_count=4,
        graph_node_count=24,
        graph_edge_count=8,
        candidate_edge_count=8,
        cross_call_camera_reuse_count=3,
        bound_decision_count=6,
        complete_label_frame_count=4,
        incomplete_label_frame_count=0,
        source_link_count=24,
        source_link_coverage_violation_count=0,
        loaded_model_frame_count=loaded_model_frames,
        rule_frame_count=rule_frames,
        fallback_frame_count=fallback_frames,
        max_model_inference_latency_ms=(
            1.5 if loaded_model_frames else None
        ),
    )


def test_options_fail_closed_before_dataset_finalization(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least three unique seeds"):
        D5CrossviewCalibrationBatchOptions(
            config_path=CALIBRATION_CONFIG,
            output_dir=tmp_path / "one-seed",
            seeds=(1000,),
        )
    with pytest.raises(ValueError, match="formal calibration"):
        D5CrossviewCalibrationBatchOptions(
            config_path=CALIBRATION_CONFIG,
            output_dir=tmp_path / "short-formal",
            seeds=(1000, 1001, 1002),
            formal=True,
        )
    with pytest.raises(ValueError, match="R0 must not load"):
        D5CrossviewCalibrationBatchOptions(
            config_path=CALIBRATION_CONFIG,
            output_dir=tmp_path / "r0-model",
            seeds=(1000, 1001, 1002),
            d5_bundle_dir=tmp_path,
        )
    with pytest.raises(ValueError, match="G1 requires"):
        D5CrossviewCalibrationBatchOptions(
            config_path=CALIBRATION_CONFIG,
            output_dir=tmp_path / "g1-no-model",
            variant="G1",
            seeds=(1000, 1001, 1002),
        )

    formal = D5CrossviewCalibrationBatchOptions(
        config_path=CALIBRATION_CONFIG,
        output_dir=tmp_path / "formal",
        seeds=D5_CROSSVIEW_RESERVED_SEEDS,
        formal=True,
    )
    assert formal.seeds == tuple(range(1000, 1020))


def test_atomic_batch_manifest_records_dirty_state_and_no_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = batch_module._BatchResult(
        source_git_commit="a" * 40,
        source_repository_dirty=True,
        base_config_sha256="b" * 64,
        exogenous_config_sha256="c" * 64,
        dataset_manifest_sha256="d" * 64,
        frame_index_sidecar_sha256="e" * 64,
        frame_index_record_count=12,
        summaries=tuple(_summary(seed=seed) for seed in (1000, 1001, 1002)),
        probability_source_counts={"deterministic_geometry_rule": 12},
        scoring_status_counts={"rule_fallback_model_missing": 12},
        fallback_reason_counts={"model_missing": 12},
    )

    def fake_run(staging: Path, **_: object):
        dataset_root = staging / batch_module.DATASET_DIRECTORY
        dataset_root.mkdir(parents=True)
        (dataset_root / "manifest.json").write_text("{}\n", encoding="utf-8")
        (staging / batch_module.FRAME_INDEX_FILENAME).write_text(
            "{}\n",
            encoding="utf-8",
        )
        return result

    monkeypatch.setattr(batch_module, "_run_batch_into", fake_run)
    output = tmp_path / "batch"
    paths = run_d5_crossview_calibration_batch(
        D5CrossviewCalibrationBatchOptions(
            config_path=CALIBRATION_CONFIG,
            output_dir=output,
            seeds=(1000, 1001, 1002),
        )
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["source_git_commit"] == "a" * 40
    assert manifest["source_repository_dirty"] is True
    assert manifest["config_file"] == (
        "research_modules/scalable_3d_simulation/configs/"
        "d5_crossview_visibility_calibration_v1.json"
    )
    assert manifest["authority"] == {
        "assignment_authority_granted": False,
        "control_authority_granted": False,
        "default_path_change_granted": False,
        "evaluation_only": True,
        "failover_authority_granted": False,
        "model_promotion_granted": False,
    }
    assert paths["checksums"].is_file()
    assert paths["frame_index_sidecar"].is_file()
    assert not tuple(output.parent.glob(f".{output.name}.partial-*"))

    with pytest.raises(FileExistsError):
        run_d5_crossview_calibration_batch(
            D5CrossviewCalibrationBatchOptions(
                config_path=CALIBRATION_CONFIG,
                output_dir=output,
                seeds=(1000, 1001, 1002),
            )
        )


def test_variant_execution_requires_exclusive_rule_or_model_path() -> None:
    r0 = _summary(seed=1000)
    batch_module._validate_variant_execution(r0, "R0")

    g1 = _summary(
        seed=1000,
        loaded_model_frames=4,
        rule_frames=0,
        fallback_frames=0,
    )
    batch_module._validate_variant_execution(g1, "G1")

    with pytest.raises(RuntimeError, match="rule scorer"):
        batch_module._validate_variant_execution(g1, "R0")
    with pytest.raises(RuntimeError, match="model on every frame"):
        batch_module._validate_variant_execution(r0, "G1")


def test_stable_frame_coordinate_is_variant_independent() -> None:
    assert (
        D5_CROSSVIEW_FRAME_INDEX_SCHEMA
        == D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION
    )
    assert batch_module._stable_frame_coordinate(
        "d5-crossview-visible-v1",
        1007,
        42,
    ) == (
        "d5-crossview-calibration:d5-crossview-visible-v1:"
        "seed-1007:frame-000042"
    )


def test_frame_index_sidecar_binds_dataset_manifest(tmp_path: Path) -> None:
    dataset_manifest = tmp_path / "manifest.json"
    dataset_manifest.write_text(
        json.dumps(
            {
                "episodes": [
                    {
                        "episode_uid": "uid-b",
                        "scenario_version": "scenario-v1",
                        "seed": 1001,
                        "hard_negative_provenance": {"frame_index": 7},
                    },
                    {
                        "episode_uid": "uid-a",
                        "scenario_version": "scenario-v1",
                        "seed": 1000,
                        "hard_negative_provenance": {"frame_index": 2},
                    },
                ]
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    sidecar = tmp_path / "frame-index.json"
    count = batch_module._write_frame_index_sidecar(
        sidecar,
        dataset_manifest,
    )
    payload = json.loads(sidecar.read_text(encoding="utf-8"))

    assert count == 2
    assert payload["schema_version"] == D5_CROSSVIEW_FRAME_INDEX_SCHEMA_VERSION
    assert payload["dataset_manifest_sha256"] == batch_module._sha256_file(
        dataset_manifest
    )
    assert payload["records"] == [
        {
            "episode_uid": "uid-a",
            "scenario_version": "scenario-v1",
            "seed": 1000,
            "frame_index": 2,
        },
        {
            "episode_uid": "uid-b",
            "scenario_version": "scenario-v1",
            "seed": 1001,
            "frame_index": 7,
        },
    ]

    duplicate = json.loads(dataset_manifest.read_text(encoding="utf-8"))
    duplicate["episodes"][1]["seed"] = 1001
    duplicate["episodes"][1]["hard_negative_provenance"]["frame_index"] = 7
    dataset_manifest.write_text(
        json.dumps(duplicate, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="coordinate is duplicated"):
        batch_module._write_frame_index_sidecar(
            tmp_path / "duplicate.json",
            dataset_manifest,
        )
