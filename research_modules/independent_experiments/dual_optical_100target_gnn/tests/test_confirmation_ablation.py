from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np
import pytest

from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    RevolutionSnapshot,
    SnapshotTrack,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from dual_optical_online_benchmark.dataset import (
    DATASET_SCHEMA_VERSION as SHARED_DATASET_SCHEMA_VERSION,
)
from dual_optical_100target_gnn.confirmation_ablation import (
    _load_replay_entries,
    run_confirmation_ablation,
)
from dual_optical_100target_gnn.dataset import CAUSAL_DATASET_SCHEMA_VERSION
from dual_optical_100target_gnn.graph import GeometryGate
from dual_optical_100target_gnn.loader import sha256_file
from dual_optical_100target_gnn.online import (
    ONLINE_ROUTE_VERSION,
    OnlineGNNAssociator,
)
from dual_optical_100target_gnn.online_benchmark import freeze_route
from dual_optical_100target_gnn.schema import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CorruptionSummary,
    OnlineGraph,
)


def _snapshot(
    revolution: int,
    *,
    track_ids_a: tuple[str, ...] = ("A-1",),
    track_ids_b: tuple[str, ...] = ("B-1",),
    split: str = "test",
    seed: int = 20260817,
) -> RevolutionSnapshot:
    return RevolutionSnapshot(
        protocol_fingerprint=BenchmarkProtocol().fingerprint,
        seed=seed,
        split=split,
        corruption_level="light",
        revolution_index=revolution,
        cutoff_timestamp=float(revolution * 2),
        camera_ids=("Optical_A", "Optical_B"),
        camera_positions_ned={
            "Optical_A": (0.0, -1000.0, -100.0),
            "Optical_B": (0.0, 1000.0, -100.0),
        },
        focal_length_px=25000.0,
        tracks={
            "Optical_A": tuple(
                SnapshotTrack(
                    track_id,
                    "Optical_A",
                    (),
                    track_state="confirmed",
                )
                for track_id in track_ids_a
            ),
            "Optical_B": tuple(
                SnapshotTrack(
                    track_id,
                    "Optical_B",
                    (),
                    track_state="coasting",
                )
                for track_id in track_ids_b
            ),
        },
        target_count=20,
    )


def _replay_entry(
    snapshot: RevolutionSnapshot,
    snapshot_path: Path,
    *,
    include_label_reference: bool = False,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "seed": snapshot.seed,
        "split": snapshot.split,
        "corruption_level": snapshot.corruption_level,
        "revolution_index": snapshot.revolution_index,
        "snapshot_path": snapshot_path.name,
        "snapshot_sha256": sha256_file(snapshot_path),
        "input_fingerprint": snapshot_fingerprint(snapshot),
    }
    if include_label_reference:
        entry.update(
            {
                "label_path": f"missing-{snapshot.split}-label.json",
                "label_sha256": "b" * 64,
            }
        )
    return entry


def _graph(
    *,
    track_ids_a: tuple[str, ...] = ("A-1",),
    track_ids_b: tuple[str, ...] = ("B-1",),
    edges: tuple[tuple[int, int], ...] = ((0, 0),),
    normalized_residuals: tuple[float, ...] | None = None,
) -> OnlineGraph:
    edge_features = np.zeros((len(edges), len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    residuals = normalized_residuals or tuple(3.0 for _ in edges)
    edge_features[:, EDGE_FEATURE_NAMES.index("normalized_coplanarity_residual")] = residuals
    graph = OnlineGraph(
        seed=20260817,
        corruption_level="light",
        camera_ids=("Optical_A", "Optical_B"),
        track_ids_a=track_ids_a,
        track_ids_b=track_ids_b,
        node_features_a=np.zeros(
            (len(track_ids_a), len(NODE_FEATURE_NAMES)), dtype=np.float32
        ),
        node_features_b=np.zeros(
            (len(track_ids_b), len(NODE_FEATURE_NAMES)), dtype=np.float32
        ),
        edge_index=np.asarray(edges, dtype=np.int64).T,
        edge_features=edge_features,
        geometry_cost=np.zeros(len(edges), dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 1, 0, 1, 0, 0),
    )
    graph.validate()
    return graph


def _associator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    graph: OnlineGraph,
    probability_sequence: list[tuple[float, ...]],
    **kwargs,
) -> OnlineGNNAssociator:
    tmp_path.mkdir(parents=True, exist_ok=True)
    model_config = tmp_path / "model_config.json"
    model_config.write_text(
        json.dumps(
            {
                "node_feature_dim": len(NODE_FEATURE_NAMES),
                "edge_feature_dim": len(EDGE_FEATURE_NAMES),
                "hidden_dim": 8,
                "dropout": 0.0,
            }
        ),
        encoding="utf-8",
    )
    freeze = {
        "model_config": model_config.name,
        "weights": "weights.pt",
        "normalizer": "normalizer.json",
        "selected_route": "learned",
        "selected_unmatched_cost": -math.log(0.5),
        "geometry_gate": asdict(GeometryGate()),
        "model_fingerprint_sha256": "a" * 64,
        "target_count": 20,
    }
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online.verify_freeze_manifest",
        lambda _path: (freeze, tmp_path),
    )
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online.load_weights_only",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online.FeatureNormalizer.load",
        lambda _path: object(),
    )
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online.build_online_graph",
        lambda _episode, _summary, gate: (
            graph,
            {"candidate_edge_count": graph.edge_index.shape[1]},
        ),
    )
    associator = OnlineGNNAssociator("freeze.json", device="cpu", **kwargs)
    sequence = iter(probability_sequence)
    monkeypatch.setattr(
        associator,
        "_probabilities",
        lambda _graph: (np.asarray(next(sequence), dtype=np.float32), 0.0, 0.0),
    )
    return associator


def test_early_repeat_confirms_a_a_on_second_revolution(tmp_path, monkeypatch) -> None:
    associator = _associator(
        tmp_path,
        monkeypatch,
        _graph(),
        [(0.95,), (0.95,)],
        confirmation_strategy="early_repeat",
    )
    assert associator.associate(_snapshot(1)).publication.matches == ()
    second = associator.associate(_snapshot(2))
    assert second.publication.matches[0].decision_state == "confirmed"


def test_early_repeat_confirms_a_missing_a_on_third_revolution(
    tmp_path, monkeypatch
) -> None:
    associator = _associator(
        tmp_path,
        monkeypatch,
        _graph(),
        [(0.95,), (0.10,), (0.95,)],
        confirmation_strategy="early_repeat",
    )
    assert associator.associate(_snapshot(1)).publication.matches == ()
    assert associator.associate(_snapshot(2)).publication.matches == ()
    third = associator.associate(_snapshot(3))
    assert third.publication.matches[0].decision_state == "confirmed"


def test_early_repeat_does_not_confirm_changed_pair(tmp_path, monkeypatch) -> None:
    graph = _graph(
        track_ids_b=("B-1", "B-2"),
        edges=((0, 0), (0, 1)),
    )
    associator = _associator(
        tmp_path,
        monkeypatch,
        graph,
        [(0.95, 0.10), (0.10, 0.95)],
        confirmation_strategy="early_repeat",
    )
    assert associator.associate(_snapshot(1, track_ids_b=("B-1", "B-2"))).raw_matches[0].track_b_id == "B-1"
    second = associator.associate(_snapshot(2, track_ids_b=("B-1", "B-2")))
    assert second.raw_matches[0].track_b_id == "B-2"
    assert second.publication.matches == ()


def test_graded_fast_confirmation_requires_probability_and_margin(
    tmp_path, monkeypatch
) -> None:
    graph = _graph(
        track_ids_b=("B-1", "B-2"),
        edges=((0, 0), (0, 1)),
    )
    high_margin = _associator(
        tmp_path / "high",
        monkeypatch,
        graph,
        [(0.90, 0.60)],
        confirmation_strategy="graded",
        graded_probability_threshold=0.8,
        graded_margin=0.2,
    )
    high = high_margin.associate(_snapshot(1, track_ids_b=("B-1", "B-2")))
    assert high.publication.matches[0].decision_state == "fast_confirmed"
    assert high.fast_confirmed_matches == high.publication.matches

    low_margin = _associator(
        tmp_path / "low",
        monkeypatch,
        graph,
        [(0.90, 0.85)],
        confirmation_strategy="graded",
        graded_probability_threshold=0.8,
        graded_margin=0.2,
    )
    low = low_margin.associate(_snapshot(1, track_ids_b=("B-1", "B-2")))
    assert low.publication.matches == ()
    assert low.fast_confirmed_matches == ()

    high_residual = _associator(
        tmp_path / "high_residual",
        monkeypatch,
        _graph(
            track_ids_b=("B-1", "B-2"),
            edges=((0, 0), (0, 1)),
            normalized_residuals=(4.01, 3.0),
        ),
        [(0.90, 0.60)],
        confirmation_strategy="graded",
        graded_probability_threshold=0.8,
        graded_margin=0.2,
    )
    residual_result = high_residual.associate(
        _snapshot(1, track_ids_b=("B-1", "B-2"))
    )
    assert residual_result.publication.matches == ()
    assert residual_result.fast_confirmed_matches == ()


def test_direct_confirmation_requires_diagnostic_flag_and_marks_route(
    tmp_path, monkeypatch
) -> None:
    with pytest.raises(ValueError, match="diagnostic_mode=True"):
        OnlineGNNAssociator(
            "missing.json",
            confirmation_strategy="direct_1of1_diagnostic",
        )
    associator = _associator(
        tmp_path,
        monkeypatch,
        _graph(),
        [(0.95,)],
        confirmation_strategy="direct_1of1_diagnostic",
        diagnostic_mode=True,
    )
    result = associator.associate(_snapshot(1))
    assert result.publication.matches[0].decision_state == "diagnostic_direct"
    assert result.publication.route_version.endswith("direct-1of1-diagnostic")
    assert result.diagnostic_mode is True


def test_default_confirmation_remains_legacy_strict(tmp_path, monkeypatch) -> None:
    associator = _associator(
        tmp_path,
        monkeypatch,
        _graph(),
        [(0.95,), (0.95,), (0.95,)],
    )
    assert associator.route_version == ONLINE_ROUTE_VERSION
    assert associator.associate(_snapshot(1)).publication.matches == ()
    assert associator.associate(_snapshot(2)).publication.matches == ()
    result = associator.associate(_snapshot(3))
    assert result.publication.route_version == ONLINE_ROUTE_VERSION
    assert result.publication.matches[0].decision_state == "confirmed"


def test_replay_loader_ignores_offline_label_references(tmp_path) -> None:
    snapshot = _snapshot(1)
    snapshot_path = tmp_path / "snapshot.json"
    write_snapshot(snapshot_path, snapshot)
    manifest_path = tmp_path / "test_manifest.json"
    write_json(
        manifest_path,
        {
            "phase": "test",
            "test_access_allowed": True,
            "entries": [
                {
                    "seed": snapshot.seed,
                    "split": "test",
                    "corruption_level": snapshot.corruption_level,
                    "revolution_index": snapshot.revolution_index,
                    "snapshot_path": snapshot_path.name,
                    "snapshot_sha256": sha256_file(snapshot_path),
                    "input_fingerprint": snapshot_fingerprint(snapshot),
                    "label_path": "does-not-exist.json",
                    "label_sha256": "b" * 64,
                }
            ],
        },
    )
    _, entries, ignored = _load_replay_entries(manifest_path)
    assert len(entries) == 1
    assert ignored == 1


def test_validation_replay_selects_only_validation_and_never_reads_labels(
    tmp_path,
) -> None:
    train_snapshot = _snapshot(1, split="train", seed=20260818)
    validation_snapshot = _snapshot(1, split="validation", seed=20260819)
    train_path = tmp_path / "train_snapshot.json"
    validation_path = tmp_path / "validation_snapshot.json"
    write_snapshot(train_path, train_snapshot)
    write_snapshot(validation_path, validation_snapshot)
    manifest_path = tmp_path / "calibration_manifest.json"
    write_json(
        manifest_path,
        {
            "phase": "calibration",
            "test_access_allowed": False,
            "entries": [
                _replay_entry(
                    train_snapshot,
                    train_path,
                    include_label_reference=True,
                ),
                _replay_entry(
                    validation_snapshot,
                    validation_path,
                    include_label_reference=True,
                ),
            ],
        },
    )

    _, entries, ignored = _load_replay_entries(
        manifest_path,
        input_split="validation",
    )
    assert [item.snapshot.split for item in entries] == ["validation"]
    assert [item.snapshot.seed for item in entries] == [validation_snapshot.seed]
    assert ignored == 2


@pytest.mark.parametrize(
    ("input_split", "phase", "entry_split", "message"),
    [
        ("validation", "test", "test", "requires phase=calibration"),
        ("test", "calibration", "validation", "requires phase=test"),
        ("test", "test", "validation", "only test entries"),
        ("validation", "calibration", "test", "cannot contain test entries"),
        ("validation", "calibration", "train", "no validation entries"),
    ],
)
def test_replay_loader_rejects_wrong_phase_or_split(
    tmp_path,
    input_split,
    phase,
    entry_split,
    message,
) -> None:
    snapshot = _snapshot(1, split=entry_split)
    snapshot_path = tmp_path / "snapshot.json"
    write_snapshot(snapshot_path, snapshot)
    manifest_path = tmp_path / "manifest.json"
    write_json(
        manifest_path,
        {
            "phase": phase,
            "test_access_allowed": phase == "test",
            "entries": [_replay_entry(snapshot, snapshot_path)],
        },
    )
    with pytest.raises(ValueError, match=message):
        _load_replay_entries(manifest_path, input_split=input_split)


def test_replay_loader_never_supports_train(tmp_path) -> None:
    with pytest.raises(ValueError, match="only test or validation"):
        _load_replay_entries(
            tmp_path / "not-opened.json",
            input_split="train",  # type: ignore[arg-type]
        )


def test_ablation_manifest_records_validation_input_split(
    tmp_path, monkeypatch
) -> None:
    snapshot = _snapshot(1, split="validation")
    snapshot_path = tmp_path / "validation_snapshot.json"
    write_snapshot(snapshot_path, snapshot)
    input_manifest = tmp_path / "calibration_manifest.json"
    write_json(
        input_manifest,
        {
            "phase": "calibration",
            "test_access_allowed": False,
            "entries": [
                _replay_entry(
                    snapshot,
                    snapshot_path,
                    include_label_reference=True,
                )
            ],
        },
    )
    freeze_manifest = tmp_path / "freeze_manifest.json"
    freeze_manifest.write_text("{}\n", encoding="utf-8")
    associator = _associator(
        tmp_path / "model",
        monkeypatch,
        _graph(),
        [(0.95,)],
    )
    monkeypatch.setattr(
        "dual_optical_100target_gnn.confirmation_ablation.OnlineGNNAssociator",
        lambda *_args, **_kwargs: associator,
    )

    result_path = run_confirmation_ablation(
        input_manifest,
        freeze_manifest,
        tmp_path / "ablation",
        confirmation_strategy="legacy_strict",
        device="cpu",
        input_split="validation",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["input_split"] == "validation"
    assert result["truth_scoring_performed"] is False
    assert result["truth_fields_accessed"] is False
    assert result["offline_label_references_ignored"] == 1


def test_replay_loader_rejects_truth_fields_in_online_snapshot(tmp_path) -> None:
    snapshot = _snapshot(1)
    snapshot_path = tmp_path / "snapshot.json"
    write_snapshot(snapshot_path, snapshot)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    payload["truth_id"] = "forbidden"
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_path = tmp_path / "test_manifest.json"
    write_json(
        manifest_path,
        {
            "phase": "test",
            "test_access_allowed": True,
            "entries": [
                {
                    "seed": snapshot.seed,
                    "split": "test",
                    "corruption_level": snapshot.corruption_level,
                    "revolution_index": snapshot.revolution_index,
                    "snapshot_path": snapshot_path.name,
                    "snapshot_sha256": sha256_file(snapshot_path),
                    "input_fingerprint": snapshot_fingerprint(snapshot),
                }
            ],
        },
    )
    with pytest.raises(ValueError, match="truth-bearing"):
        _load_replay_entries(manifest_path)


@pytest.mark.parametrize(
    ("schema_version", "expects_prepared"),
    [
        (CAUSAL_DATASET_SCHEMA_VERSION, False),
        (SHARED_DATASET_SCHEMA_VERSION, True),
    ],
)
def test_freeze_route_passes_explicit_device_for_supported_schemas(
    tmp_path, monkeypatch, schema_version, expects_prepared
) -> None:
    captured = {}
    manifest = tmp_path / "calibration_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": schema_version}),
        encoding="utf-8",
    )
    expected = tmp_path / "frozen" / "freeze_manifest.json"
    prepared_marker = object()
    monkeypatch.setattr(
        "dual_optical_100target_gnn.online_benchmark._prepare_shared_calibration",
        lambda _path: prepared_marker,
    )

    def train(path, output_dir, *, config, prepared=None):
        captured["path"] = path
        captured["output_dir"] = output_dir
        captured["device"] = config.device
        captured["prepared"] = prepared
        return expected

    monkeypatch.setattr(
        "dual_optical_100target_gnn.online_benchmark.train_causal_ensemble_and_freeze",
        train,
    )
    result = freeze_route(
        manifest,
        tmp_path / "frozen",
        device="cuda",
    )
    assert result == expected
    assert captured["device"] == "cuda"
    assert (captured["prepared"] is prepared_marker) is expects_prepared
