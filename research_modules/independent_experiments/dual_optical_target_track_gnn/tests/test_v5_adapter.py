from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

from dual_optical_online_benchmark.contracts import write_snapshot
from dual_optical_online_benchmark.tracking import SharedTrackerConfig
from dual_optical_online_benchmark.v5 import v5_protocol_for_target_count
from dual_optical_online_benchmark.v5_runner import (
    create_diagnostic_tracker_freeze,
    load_diagnostic_tracker_freeze,
    register_v5_model_freeze,
    validate_publication_manifest,
    write_diagnostic_dataset_manifest,
    write_online_test_manifest,
)
from dual_optical_target_track_gnn import v5_adapter

from conftest import make_snapshot, make_track


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _scenario_entries(
    root: Path,
    *,
    target_count: int,
    split: str,
    seed: int,
    corruption_level: str = "clean",
    tracker_fingerprint: str | None = None,
) -> list[dict[str, object]]:
    protocol = v5_protocol_for_target_count(target_count)
    entries: list[dict[str, object]] = []
    for revolution in range(1, 7):
        track_a = make_track(
            "camera_a",
            "A-stable",
            tuple(0.1 + 2.0 * index for index in range(revolution)),
        )
        track_b = make_track(
            "camera_b",
            "B-stable",
            tuple(1.1 + 2.0 * index for index in range(revolution)),
        )
        snapshot = replace(
            make_snapshot(revolution, (track_a,), (track_b,), seed=seed),
            protocol_fingerprint=protocol.fingerprint,
            split=split,
            corruption_level=corruption_level,
            target_count=target_count,
            tracker_fingerprint=(
                tracker_fingerprint or "anonymous-shared-tracker-v1"
            ),
        )
        snapshot_relative = (
            Path("snapshots")
            / split
            / str(seed)
            / corruption_level
            / f"revolution_{revolution:02d}.json"
        )
        snapshot_path = root / snapshot_relative
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_snapshot(snapshot_path, snapshot)
        label_relative = (
            Path("labels")
            / split
            / str(seed)
            / corruption_level
            / f"revolution_{revolution:02d}.json"
        )
        label_path = root / label_relative
        _write_json(
            label_path,
            {
                "schema_version": "dual-optical-online-dataset-v2",
                "offline_truth_only": True,
                "seed": seed,
                "corruption_level": corruption_level,
                "revolution_index": revolution,
                "track_truth_counts": {
                    "A-stable": {"TRUTH-001": revolution},
                    "B-stable": {"TRUTH-001": revolution},
                },
                "truth_heading_groups": {"TRUTH-001": "heading_0_deg"},
            },
        )
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        entries.append(
            {
                "split": split,
                "seed": seed,
                "corruption_level": corruption_level,
                "revolution_index": revolution,
                "snapshot_path": snapshot_relative.as_posix(),
                "snapshot_sha256": _sha256(snapshot_path),
                "input_fingerprint": snapshot_payload["input_fingerprint"],
                "label_path": label_relative.as_posix(),
                "label_sha256": _sha256(label_path),
                "tracker_fingerprint": snapshot.tracker_fingerprint,
            }
        )
    return entries


def _manifest(
    root: Path,
    *,
    target_count: int,
    phase: str,
    entries: list[dict[str, object]],
    filename: str | None = None,
) -> Path:
    protocol = v5_protocol_for_target_count(target_count)
    path = root / (filename or f"{phase}_manifest.json")
    _write_json(
        path,
        {
            "schema_version": "dual-optical-online-dataset-v2",
            "phase": phase,
            "protocol": asdict(protocol),
            "protocol_fingerprint": protocol.fingerprint,
            "test_access_allowed": phase == "test",
            "tracker_fingerprint": entries[0]["tracker_fingerprint"],
            "tracker_freeze": None,
            "tracker_freeze_sha256": None,
            "entries": entries,
        },
    )
    return path


def _calibration_manifest(root: Path, target_count: int) -> Path:
    protocol = v5_protocol_for_target_count(target_count)
    entries: list[dict[str, object]] = []
    for seed in protocol.train_seeds[:4]:
        entries.extend(
            _scenario_entries(
                root,
                target_count=target_count,
                split="train",
                seed=seed,
            )
        )
    for seed in protocol.validation_seeds[:2]:
        entries.extend(
            _scenario_entries(
                root,
                target_count=target_count,
                split="validation",
                seed=seed,
            )
        )
    return _manifest(
        root,
        target_count=target_count,
        phase="calibration",
        entries=entries,
    )


def _diagnostic_tracker(root: Path, target_count: int) -> Path:
    protocol = v5_protocol_for_target_count(target_count)
    config = SharedTrackerConfig()
    evidence = root / "tracker_calibration_evidence.json"
    _write_json(
        evidence,
        {
            "schema_version": "target-track-adapter-test-evidence-v1",
            "protocol_fingerprint": protocol.fingerprint,
            "selected_tracker_fingerprint": config.fingerprint,
            "selected_config": asdict(config),
            "acceptance": {
                "accepted": False,
                "checks": {"fixture_only": False},
                "failure_reasons": ["fixture_only"],
            },
            "candidates": [
                {
                    "tracker_fingerprint": config.fingerprint,
                    "config": asdict(config),
                }
            ],
            "test_data_accessed": False,
        },
    )
    return create_diagnostic_tracker_freeze(
        evidence,
        root / "diagnostic_tracker_freeze.json",
        protocol,
    )


def _complete_v5_test_manifest(
    root: Path,
    *,
    target_count: int,
    tracker_freeze: Path,
    model_freeze: Path,
) -> Path:
    protocol = v5_protocol_for_target_count(target_count)
    _, tracker = load_diagnostic_tracker_freeze(tracker_freeze, protocol)
    entries: list[dict[str, object]] = []
    for seed in protocol.test_seeds:
        for corruption_level in protocol.corruption_levels:
            entries.extend(
                _scenario_entries(
                    root,
                    target_count=target_count,
                    split="test",
                    seed=seed,
                    corruption_level=corruption_level,
                    tracker_fingerprint=tracker.fingerprint,
                )
            )
    return write_diagnostic_dataset_manifest(
        root,
        entries,
        protocol,
        phase="test",
        tracker_freeze=tracker_freeze,
        model_freeze=model_freeze,
    )


def test_v5_adapter_freeze_publish_and_score_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v5_adapter, "TRAINING_MAX_EPOCHS", 1)
    monkeypatch.setattr(v5_adapter, "TRAINING_PATIENCE", 1)
    calibrations = {
        count: _calibration_manifest(tmp_path / f"calibration_{count}", count)
        for count in (40, 60, 100)
    }
    native_path = Path(
        v5_adapter.train_and_freeze(
            calibration_manifests=calibrations,
            output_dir=tmp_path / "model",
            scale_sampling_policy="uniform_over_40_60_100",
            initialization_count=5,
        )
    )
    native = json.loads(native_path.read_text(encoding="utf-8"))
    assert native["test_data_accessed"] is False
    assert native["test_labels_accessed"] is False
    assert native["training_splits"] == ["train"]
    assert native["selection_splits"] == ["validation"]
    assert native["scale_sampling_policy"] == "uniform_over_40_60_100"
    assert native["initialization_count"] == 5
    assert native["model_fingerprint"]
    assert native["acceptance_passed"] is False
    for split in ("train", "validation"):
        counts = [
            native["selected_balanced_example_count"][f"{split}_{count}"]
            for count in (40, 60, 100)
        ]
        assert len(set(counts)) == 1
        assert counts[0] > 0

    wrapper_path = register_v5_model_freeze(
        native_path,
        calibrations,
        tmp_path / "model" / "v5_model_freeze.json",
    )
    loaded_model, loaded_normalizer, loaded_native = (
        v5_adapter._load_v5_frozen_model(wrapper_path)
    )
    assert loaded_model is not None
    assert loaded_normalizer is not None
    assert loaded_native["model_fingerprint"] == native["model_fingerprint"]
    assert (
        loaded_native["freeze_manifest_sha256"]
        == native["freeze_manifest_sha256"]
    )

    test_root = tmp_path / "test_40"
    tracker_freeze = _diagnostic_tracker(test_root / "tracker", 40)
    full_manifest = _complete_v5_test_manifest(
        test_root,
        target_count=40,
        tracker_freeze=tracker_freeze,
        model_freeze=wrapper_path,
    )
    with pytest.raises(ValueError, match="online-only"):
        v5_adapter.publish_test(
            test_manifest=full_manifest,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "must_not_publish",
            routes=("rule_baseline", "gnn_assisted"),
        )
    assert not (tmp_path / "must_not_publish").exists()

    online_manifest = write_online_test_manifest(full_manifest, wrapper_path)
    online = json.loads(online_manifest.read_text(encoding="utf-8"))

    missing_fingerprint = dict(online)
    missing_fingerprint.pop("online_manifest_fingerprint")
    missing_fingerprint_path = test_root / "online_missing_fingerprint.json"
    _write_json(missing_fingerprint_path, missing_fingerprint)
    with pytest.raises(ValueError, match="fingerprint"):
        v5_adapter.publish_test(
            test_manifest=missing_fingerprint_path,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "missing_fingerprint_publications",
            routes=("rule_baseline", "gnn_assisted"),
        )

    wrong_fingerprint = dict(online)
    wrong_fingerprint["online_manifest_fingerprint"] = "f" * 64
    wrong_fingerprint_path = test_root / "online_wrong_fingerprint.json"
    _write_json(wrong_fingerprint_path, wrong_fingerprint)
    with pytest.raises(ValueError, match="fingerprint"):
        v5_adapter.publish_test(
            test_manifest=wrong_fingerprint_path,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "wrong_fingerprint_publications",
            routes=("rule_baseline", "gnn_assisted"),
        )

    not_online_only = dict(online)
    not_online_only["online_only"] = False
    unsigned_not_online = dict(not_online_only)
    unsigned_not_online.pop("online_manifest_fingerprint")
    not_online_only["online_manifest_fingerprint"] = v5_adapter.payload_fingerprint(
        unsigned_not_online
    )
    not_online_only_path = test_root / "not_online_only.json"
    _write_json(not_online_only_path, not_online_only)
    with pytest.raises(ValueError, match="test-input isolation"):
        v5_adapter.publish_test(
            test_manifest=not_online_only_path,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "not_online_only_publications",
            routes=("rule_baseline", "gnn_assisted"),
        )

    wrong_schema = dict(online)
    wrong_schema["schema_version"] = "dual-optical-v5-online-test-manifest-v0"
    unsigned_wrong_schema = dict(wrong_schema)
    unsigned_wrong_schema.pop("online_manifest_fingerprint")
    wrong_schema["online_manifest_fingerprint"] = v5_adapter.payload_fingerprint(
        unsigned_wrong_schema
    )
    wrong_schema_path = test_root / "online_wrong_schema.json"
    _write_json(wrong_schema_path, wrong_schema)
    with pytest.raises(ValueError, match="schema"):
        v5_adapter.publish_test(
            test_manifest=wrong_schema_path,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "wrong_schema_publications",
            routes=("rule_baseline", "gnn_assisted"),
        )

    wrong_model = dict(online)
    wrong_model["model_freeze_sha256"] = "0" * 64
    unsigned_wrong_model = dict(wrong_model)
    unsigned_wrong_model.pop("online_manifest_fingerprint")
    wrong_model["online_manifest_fingerprint"] = v5_adapter.payload_fingerprint(
        unsigned_wrong_model
    )
    wrong_model_path = test_root / "online_wrong_model.json"
    _write_json(wrong_model_path, wrong_model)
    with pytest.raises(ValueError, match="another model"):
        v5_adapter.publish_test(
            test_manifest=wrong_model_path,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "wrong_model_publications",
            routes=("rule_baseline", "gnn_assisted"),
        )

    publication_path = Path(
        v5_adapter.publish_test(
            test_manifest=online_manifest,
            model_freeze=wrapper_path,
            output_dir=tmp_path / "publications",
            routes=("rule_baseline", "gnn_assisted"),
        )
    )
    validated_publication = validate_publication_manifest(
        publication_path,
        online_test_manifest=online_manifest,
        model_freeze=wrapper_path,
    )
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    assert validated_publication == publication
    assert publication["schema_version"] == "dual-optical-v5-publications-v1"
    assert publication["routes"] == ["rule_baseline", "gnn_assisted"]
    assert publication["test_labels_accessed"] is False
    assert (
        publication["online_manifest_fingerprint"]
        == online["online_manifest_fingerprint"]
    )
    assert publication["online_test_manifest_sha256"] == _sha256(online_manifest)
    assert publication["model_freeze_sha256"] == _sha256(wrapper_path)
    scenario_path = (
        publication_path.parent / publication["entries"][0]["scenario_path"]
    )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    encoded = scenario_path.read_text(encoding="utf-8").lower()
    for forbidden in (
        "truth_id",
        "actor_id",
        "global_track_id",
        "label_path",
        "label_sha256",
    ):
        assert forbidden not in encoded
    for revolution in scenario["revolutions"]:
        for camera in revolution["cameras"].values():
            if camera["routes"]:
                assert set(camera["routes"]) == {
                    "rule_baseline",
                    "gnn_assisted",
                }
                assert (
                    camera["routes"]["rule_baseline"]["internal_route"]
                    == "deterministic"
                )
                assert (
                    camera["routes"]["gnn_assisted"]["internal_route"]
                    == "gnn_assisted"
                )

    metrics_path = Path(
        v5_adapter.score_publications(
            publication_manifest=publication_path,
            test_manifest=full_manifest,
            output_dir=tmp_path / "results",
        )
    )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert set(metrics["routes"]) == {"rule_baseline", "gnn_assisted"}
    for route in metrics["routes"].values():
        assert "valid_hypothesis_identity_rate" in route
        assert "current_track_identity_rate" in route
        assert "coverage" in route
        assert "false_match_count" in route
        assert "unmatched_count" in route
        assert "one_to_one_violation_count" in route
        assert "confirmed_count" in route
        assert "latency_p95_ms" in route
    assert metrics["offline_labels_opened_during_scoring"] is True
    assert metrics["test_labels_used_for_model_selection"] is False
    assert metrics["formal_acceptance_claimed"] is False
    assert metrics["acceptance_status"] == "not_assessed"


def test_train_and_freeze_rejects_less_than_five_initializations(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="five"):
        v5_adapter._initialization_seeds(4)
