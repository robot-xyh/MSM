from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

import dual_optical_online_benchmark.v5_runner as v5_runner_module
from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    benchmark_protocol_for_target_count,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from dual_optical_online_benchmark.dataset import sha256_file, split_for_seed
from dual_optical_online_benchmark.tracking import SharedTrackerConfig
from dual_optical_online_benchmark.v5 import (
    V5_OUTPUT_VERSION,
    V5_TARGET_COUNTS,
    v5_protocol_for_target_count,
)
from dual_optical_online_benchmark.v5_reporting import build_v5_report_payload
from dual_optical_online_benchmark.v5_runner import (
    V5_DIAGNOSTIC_DATASET_SCHEMA,
    V5_MODEL_FREEZE_SCHEMA,
    V5_ONLINE_TEST_MANIFEST_SCHEMA,
    V5_PUBLICATION_MANIFEST_SCHEMA,
    V5_SCALE_SAMPLING_POLICY,
    V5_RUN_SCHEMA,
    V5_ROUTE_NAMES,
    V5Runner,
    build_v5_plan,
    collect_diagnostic_test_raw,
    create_diagnostic_tracker_freeze,
    load_diagnostic_tracker_freeze,
    register_v5_model_freeze,
    validate_diagnostic_dataset_manifest,
    validate_online_test_manifest,
    validate_publication_manifest,
    validate_v5_model_freeze,
    write_diagnostic_dataset_manifest,
    write_online_test_manifest,
)


def _failed_calibration_evidence(path: Path, target_count: int) -> Path:
    protocol = v5_protocol_for_target_count(target_count)
    config = SharedTrackerConfig()
    write_json(
        path,
        {
            "schema_version": "test-calibration-evidence",
            "protocol_fingerprint": protocol.fingerprint,
            "selected_tracker_fingerprint": config.fingerprint,
            "selected_config": asdict(config),
            "acceptance": {
                "accepted": False,
                "checks": {
                    "median_track_purity": True,
                    "heavy_common_confirmed_rate": False,
                },
                "failure_reasons": ["heavy_common_confirmed_rate"],
            },
            "candidates": [
                {
                    "tracker_fingerprint": config.fingerprint,
                    "config": asdict(config),
                    "validation": {"recorded": True},
                }
            ],
            "test_data_accessed": False,
        },
    )
    return path


def _entries(target_count: int, phase: str, fingerprint: str) -> list[dict]:
    protocol = v5_protocol_for_target_count(target_count)
    seeds = (
        protocol.train_seeds + protocol.validation_seeds
        if phase == "calibration"
        else protocol.test_seeds
    )
    return [
        {
            "split": split_for_seed(protocol, seed),
            "seed": seed,
            "corruption_level": level,
            "revolution_index": revolution,
            "snapshot_path": (
                f"snapshots/{split_for_seed(protocol, seed)}/{seed}/{level}/"
                f"revolution_{revolution:02d}.json"
            ),
            "snapshot_sha256": "not-materialized-in-unit-test",
            "input_fingerprint": f"input-{seed}-{level}-{revolution}",
            "label_path": (
                f"labels/{split_for_seed(protocol, seed)}/{seed}/{level}/"
                f"revolution_{revolution:02d}.json"
            ),
            "label_sha256": "not-materialized-in-unit-test",
            "tracker_fingerprint": fingerprint,
        }
        for seed in seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    ]


def _diagnostic_calibration(tmp_path: Path, target_count: int) -> tuple[Path, Path]:
    root = tmp_path / f"target_{target_count}"
    evidence = _failed_calibration_evidence(
        root / "freezes" / "shared_tracker_calibration.json", target_count
    )
    tracker = create_diagnostic_tracker_freeze(
        evidence,
        root / "diagnostic_freezes" / "shared_tracker.json",
        v5_protocol_for_target_count(target_count),
    )
    _, config = load_diagnostic_tracker_freeze(
        tracker, v5_protocol_for_target_count(target_count)
    )
    manifest = write_diagnostic_dataset_manifest(
        root,
        _entries(target_count, "calibration", config.fingerprint),
        v5_protocol_for_target_count(target_count),
        phase="calibration",
        tracker_freeze=tracker,
    )
    return manifest, tracker


def _model_freeze(tmp_path: Path) -> tuple[Path, dict[int, Path], dict[int, Path]]:
    calibrations: dict[int, Path] = {}
    trackers: dict[int, Path] = {}
    for target_count in V5_TARGET_COUNTS:
        calibrations[target_count], trackers[target_count] = _diagnostic_calibration(
            tmp_path, target_count
        )
    native = tmp_path / "native" / "model_freeze.json"
    write_json(
        native,
        {
            "schema_version": "target-track-test-native-v1",
            "model_fingerprint": "frozen-model-40-60-100",
            "scale_sampling_policy": V5_SCALE_SAMPLING_POLICY,
            "initialization_count": 5,
            "training_splits": ["train"],
            "selection_splits": ["validation"],
            "test_data_accessed": False,
            "test_labels_accessed": False,
            "acceptance_passed": False,
            "formal_use_allowed": False,
        },
    )
    wrapper = register_v5_model_freeze(
        native,
        calibrations,
        tmp_path / "shared_model" / "v5_model_freeze.json",
    )
    return wrapper, calibrations, trackers


def _materialize_test_snapshots(
    root: Path,
    entries: list[dict],
    target_count: int,
) -> list[dict]:
    protocol = v5_protocol_for_target_count(target_count)
    for entry in entries:
        snapshot = RevolutionSnapshot(
            protocol_fingerprint=protocol.fingerprint,
            seed=int(entry["seed"]),
            split=str(entry["split"]),
            corruption_level=str(entry["corruption_level"]),
            revolution_index=int(entry["revolution_index"]),
            cutoff_timestamp=(
                int(entry["revolution_index"]) * protocol.scan_period_s
            ),
            camera_ids=("Optical_A", "Optical_B"),
            camera_positions_ned={
                "Optical_A": (0.0, -1000.0, -100.0),
                "Optical_B": (0.0, 1000.0, -100.0),
            },
            focal_length_px=25_000.0,
            tracks={"Optical_A": (), "Optical_B": ()},
            target_count=target_count,
            tracker_fingerprint=str(entry["tracker_fingerprint"]),
        )
        snapshot_path = root / str(entry["snapshot_path"])
        write_snapshot(snapshot_path, snapshot)
        entry["snapshot_sha256"] = sha256_file(snapshot_path)
        entry["input_fingerprint"] = snapshot_fingerprint(snapshot)
    return entries


def _diagnostic_test_manifest(
    root: Path,
    *,
    target_count: int,
    tracker: Path,
    model: Path,
) -> Path:
    protocol = v5_protocol_for_target_count(target_count)
    _, tracker_config = load_diagnostic_tracker_freeze(tracker, protocol)
    entries = _materialize_test_snapshots(
        root,
        _entries(target_count, "test", tracker_config.fingerprint),
        target_count,
    )
    return write_diagnostic_dataset_manifest(
        root,
        entries,
        protocol,
        phase="test",
        tracker_freeze=tracker,
        model_freeze=model,
    )


def test_v5_plan_lists_all_scales_seeds_phase_and_no_screenshots(
    tmp_path: Path,
) -> None:
    plan = build_v5_plan(
        repo_root=tmp_path,
        output_parent=tmp_path / "outputs",
        blocks_script=tmp_path / "Blocks.sh",
    )

    assert plan["target_counts"] == [40, 60, 100]
    assert plan["camera_b_scan_phase_offset_s"] == 1.0
    assert plan["phase_zero_control_included"] is False
    assert plan["phase_contribution_isolatable"] is False
    assert plan["screenshots_saved"] is False
    assert Path(plan["output_root"]).name == V5_OUTPUT_VERSION
    for scale in plan["scales"]:
        protocol = v5_protocol_for_target_count(scale["target_count"])
        assert scale["camera_b_scan_phase_offset_s"] == 1.0
        assert scale["seeds"]["train"] == list(protocol.train_seeds)
        assert scale["seeds"]["validation"] == list(protocol.validation_seeds)
        assert scale["seeds"]["test"] == list(protocol.test_seeds)
        assert [item["stage"] for item in scale["stages"]] == [
            "preflight",
            "calibration",
            "test",
        ]
        assert all("save-images" not in item["command"] for item in scale["stages"])


def test_diagnostic_tracker_freeze_preserves_failure_evidence(
    tmp_path: Path,
) -> None:
    protocol = v5_protocol_for_target_count(40)
    evidence = _failed_calibration_evidence(
        tmp_path / "shared_tracker_calibration.json", 40
    )
    original_hash = sha256_file(evidence)
    formal_path = tmp_path / "shared_tracker.json"
    diagnostic_path = tmp_path / "diagnostic" / "shared_tracker.json"

    freeze = create_diagnostic_tracker_freeze(
        evidence, diagnostic_path, protocol
    )
    payload, config = load_diagnostic_tracker_freeze(freeze, protocol)

    assert sha256_file(evidence) == original_hash
    assert not formal_path.exists()
    assert payload["formal_use_allowed"] is False
    assert payload["acceptance_passed"] is False
    assert payload["diagnostic_only"] is True
    assert payload["source_calibration_evidence_sha256"] == original_hash
    assert payload["source_acceptance"]["accepted"] is False
    assert payload["failure_reasons"] == ["heavy_common_confirmed_rate"]
    assert config.fingerprint == payload["tracker_fingerprint"]
    assert not (tmp_path / "all_routes_frozen.json").exists()


def test_diagnostic_freeze_refuses_positive_acceptance(tmp_path: Path) -> None:
    protocol = v5_protocol_for_target_count(40)
    evidence = _failed_calibration_evidence(tmp_path / "evidence.json", 40)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["acceptance"]["accepted"] = True
    write_json(evidence, payload)

    with pytest.raises(ValueError, match="failed formal acceptance"):
        create_diagnostic_tracker_freeze(
            evidence, tmp_path / "diagnostic.json", protocol
        )


def test_shared_model_freezes_before_any_test_manifest(tmp_path: Path) -> None:
    wrapper, _, trackers = _model_freeze(tmp_path)
    model = validate_v5_model_freeze(wrapper)

    assert model["schema_version"] == V5_MODEL_FREEZE_SCHEMA
    assert model["target_counts"] == [40, 60, 100]
    assert model["training_splits"] == ["train"]
    assert model["selection_splits"] == ["validation"]
    assert model["test_data_accessed"] is False
    assert model["test_labels_accessed"] is False
    assert model["model_frozen_before_test"] is True
    assert model["formal_use_allowed"] is False

    protocol = v5_protocol_for_target_count(40)
    _, tracker_config = load_diagnostic_tracker_freeze(trackers[40], protocol)
    with pytest.raises(RuntimeError, match="frozen V5 model"):
        write_diagnostic_dataset_manifest(
            tmp_path / "target_40_test",
            _entries(40, "test", tracker_config.fingerprint),
            protocol,
            phase="test",
            tracker_freeze=trackers[40],
        )

    manifest = write_diagnostic_dataset_manifest(
        tmp_path / "target_40_test",
        _entries(40, "test", tracker_config.fingerprint),
        protocol,
        phase="test",
        tracker_freeze=trackers[40],
        model_freeze=wrapper,
    )
    payload = validate_diagnostic_dataset_manifest(
        manifest, expected_phase="test", validate_artifacts=False
    )
    assert payload["schema_version"] == V5_DIAGNOSTIC_DATASET_SCHEMA
    assert payload["formal_use_allowed"] is False
    assert payload["model_frozen_before_test"] is True
    assert payload["test_labels_accessed_for_model_selection"] is False


def test_online_test_manifest_physically_excludes_labels_and_binds_model(
    tmp_path: Path,
) -> None:
    model, _, trackers = _model_freeze(tmp_path / "model_fixture")
    full_manifest = _diagnostic_test_manifest(
        tmp_path / "test_dataset",
        target_count=40,
        tracker=trackers[40],
        model=model,
    )

    online_manifest = write_online_test_manifest(full_manifest, model)
    online = validate_online_test_manifest(
        online_manifest,
        expected_model_freeze=model,
    )
    serialized = online_manifest.read_text(encoding="utf-8")
    full = json.loads(full_manifest.read_text(encoding="utf-8"))

    assert online["schema_version"] == V5_ONLINE_TEST_MANIFEST_SCHEMA
    assert online["online_only"] is True
    assert "label_path" not in serialized
    assert "label_sha256" not in serialized
    assert "labels/" not in serialized
    assert all(
        set(entry)
        == {
            "split",
            "seed",
            "corruption_level",
            "revolution_index",
            "snapshot_path",
            "snapshot_sha256",
            "input_fingerprint",
            "tracker_fingerprint",
        }
        for entry in online["entries"]
    )
    assert all("label_path" in entry for entry in full["entries"])
    assert online["model_freeze_sha256"] == sha256_file(model)

    contaminated = dict(online)
    contaminated["entries"] = [dict(online["entries"][0], label_path="labels/test.json")]
    contaminated_path = online_manifest.with_name("contaminated_online.json")
    write_json(contaminated_path, contaminated)
    with pytest.raises(ValueError, match="offline label"):
        validate_online_test_manifest(contaminated_path, validate_artifacts=False)


def test_publication_manifest_rejects_replaced_online_input_or_model_hash(
    tmp_path: Path,
) -> None:
    model, _, trackers = _model_freeze(tmp_path / "model_fixture")
    full_manifest = _diagnostic_test_manifest(
        tmp_path / "test_dataset",
        target_count=40,
        tracker=trackers[40],
        model=model,
    )
    online_manifest = write_online_test_manifest(full_manifest, model)
    online = validate_online_test_manifest(online_manifest)
    publication_path = tmp_path / "publication.json"
    publication = {
        "schema_version": V5_PUBLICATION_MANIFEST_SCHEMA,
        "routes": list(V5_ROUTE_NAMES),
        "test_labels_accessed": False,
        "online_test_manifest_sha256": sha256_file(online_manifest),
        "online_manifest_fingerprint": online["online_manifest_fingerprint"],
        "model_freeze_sha256": sha256_file(model),
    }
    write_json(publication_path, publication)
    validate_publication_manifest(
        publication_path,
        online_test_manifest=online_manifest,
        model_freeze=model,
    )

    write_json(
        publication_path,
        dict(publication, online_test_manifest_sha256="replaced-input"),
    )
    with pytest.raises(ValueError, match="another online input"):
        validate_publication_manifest(
            publication_path,
            online_test_manifest=online_manifest,
            model_freeze=model,
        )

    write_json(
        publication_path,
        dict(publication, model_freeze_sha256="replaced-model"),
    )
    with pytest.raises(ValueError, match="another model"):
        validate_publication_manifest(
            publication_path,
            online_test_manifest=online_manifest,
            model_freeze=model,
        )


def test_v5_runner_publishes_online_manifest_and_scores_full_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model, _, trackers = _model_freeze(tmp_path / "model_fixture")

    class RecordingAdapter:
        def __init__(self) -> None:
            self.published_from: Path | None = None
            self.scored_from: Path | None = None

        def publish_test(self, **kwargs):
            self.published_from = Path(kwargs["test_manifest"]).resolve()
            online = validate_online_test_manifest(
                self.published_from,
                expected_model_freeze=kwargs["model_freeze"],
            )
            output = Path(kwargs["output_dir"]) / "publication_manifest.json"
            write_json(
                output,
                {
                    "schema_version": V5_PUBLICATION_MANIFEST_SCHEMA,
                    "routes": list(kwargs["routes"]),
                    "test_labels_accessed": False,
                    "online_test_manifest_sha256": sha256_file(
                        self.published_from
                    ),
                    "online_manifest_fingerprint": online[
                        "online_manifest_fingerprint"
                    ],
                    "model_freeze_sha256": sha256_file(kwargs["model_freeze"]),
                },
            )
            return output

        def score_publications(self, **kwargs):
            self.scored_from = Path(kwargs["test_manifest"]).resolve()
            scoring = json.loads(self.scored_from.read_text(encoding="utf-8"))
            assert all("label_path" in entry for entry in scoring["entries"])
            output = Path(kwargs["output_dir"]) / "metrics.json"
            write_json(output, {"schema_version": "test-v5-metrics"})
            return output

    adapter = RecordingAdapter()
    runner = V5Runner.create(
        repo_root=tmp_path,
        output_parent=tmp_path / "outputs",
        blocks_script=tmp_path / "Blocks.sh",
        adapter=adapter,
    )
    dataset_root = runner.output_root / "target_040" / "dataset"
    full_manifest = _diagnostic_test_manifest(
        dataset_root,
        target_count=40,
        tracker=trackers[40],
        model=model,
    )
    state = runner._new_state()
    state["shared_model_freeze"] = str(model)
    state["shared_model_freeze_sha256"] = sha256_file(model)
    state["scales"]["40"] = {
        "tracker_status": "diagnostic",
        "tracker_freeze": str(trackers[40]),
        "tracker_freeze_sha256": sha256_file(trackers[40]),
    }
    runner._save_state(state)
    monkeypatch.setattr(
        v5_runner_module,
        "collect_diagnostic_test_raw",
        lambda **_kwargs: tmp_path / "unused_raw_manifest.json",
    )
    monkeypatch.setattr(
        v5_runner_module,
        "materialize_diagnostic_snapshots",
        lambda *_args, **_kwargs: full_manifest,
    )

    metrics = runner.run_test_scale(40)
    final_state = runner._load_state()
    scale = final_state["scales"]["40"]

    assert metrics.is_file()
    assert adapter.published_from == Path(scale["online_test_manifest"])
    assert adapter.scored_from == full_manifest
    assert Path(scale["scoring_test_manifest"]) == full_manifest
    assert scale["online_test_manifest_sha256"] == sha256_file(
        adapter.published_from
    )
    assert scale["scoring_test_manifest_sha256"] == sha256_file(full_manifest)
    assert scale["test_manifest"] == scale["scoring_test_manifest"]
    assert not (dataset_root / "freezes" / "all_routes_frozen.json").exists()


def test_raw_test_collection_fails_before_creating_output_without_model(
    tmp_path: Path,
) -> None:
    output = tmp_path / "must_not_exist"
    with pytest.raises((FileNotFoundError, ValueError)):
        collect_diagnostic_test_raw(
            repo_root=tmp_path,
            output_root=output,
            protocol=v5_protocol_for_target_count(40),
            blocks_script=tmp_path / "Blocks.sh",
            model_freeze=tmp_path / "missing_model.json",
        )
    assert not output.exists()


def test_raw_test_collection_rejects_a_different_post_opening_model(
    tmp_path: Path,
) -> None:
    wrapper, _, _ = _model_freeze(tmp_path)
    protocol = v5_protocol_for_target_count(40)
    output = tmp_path / "runtime"
    opening = output / "diagnostic_test" / "test_opening.json"
    write_json(
        opening,
        {
            "schema_version": "dual-optical-v5-test-opening-v1",
            "protocol_fingerprint": protocol.fingerprint,
            "model_freeze_sha256": "a-different-model",
            "model_frozen_before_test": True,
        },
    )

    with pytest.raises(RuntimeError, match="different model freeze"):
        collect_diagnostic_test_raw(
            repo_root=tmp_path,
            output_root=output,
            protocol=protocol,
            blocks_script=tmp_path / "Blocks.sh",
            model_freeze=wrapper,
        )


def test_report_keeps_formal_and_diagnostic_status_separate(tmp_path: Path) -> None:
    state = {
        "schema_version": V5_RUN_SCHEMA,
        "experiment_profile": "phase180_target_track_gnn_v1",
        "output_version": V5_OUTPUT_VERSION,
        "camera_b_scan_phase_offset_s": 1.0,
        "test_data_used_for_model_selection": False,
        "scales": {
            "40": {
                "tracker_status": "diagnostic",
                "tracker_formal_use_allowed": False,
                "tracker_acceptance_passed": False,
                "tracker_failure_reasons": ["heavy_common_confirmed_rate"],
                "test_status": "diagnostic",
            },
            "60": {
                "tracker_status": "formal",
                "tracker_formal_use_allowed": True,
                "tracker_acceptance_passed": True,
                "test_status": "not_run",
            },
            "100": {},
        },
    }
    report = build_v5_report_payload(state, run_root=tmp_path)

    assert report["phase_contribution_isolatable"] is False
    assert report["scales"][0]["tracker"]["status"] == "diagnostic"
    assert report["scales"][0]["tracker"]["acceptance_passed"] is False
    assert report["scales"][1]["tracker"]["status"] == "formal"
    assert report["scales"][1]["tracker"]["acceptance_passed"] is True


def test_importing_v5_runner_does_not_change_v4_protocol() -> None:
    for target_count in V5_TARGET_COUNTS:
        protocol = benchmark_protocol_for_target_count(target_count)
        assert protocol.camera_b_scan_phase_offset_s == 0.0
        assert protocol.fingerprint != v5_protocol_for_target_count(
            target_count
        ).fingerprint
