from __future__ import annotations

from dataclasses import asdict, replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from dual_optical_100target_gnn.dataset import (
    load_dataset_manifest as load_legacy_manifest,
    load_entry,
    sample_entries,
)
from dual_optical_100target_gnn.graph import GeometryGate
from dual_optical_100target_gnn.schema import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    CorruptionSummary,
    OnlineGraph,
)
from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    LEGACY_SCHEMA_VERSION,
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    benchmark_protocol_for_target_count,
    candidate_graph_fingerprint,
    snapshot_fingerprint,
)
from dual_optical_100target_lightweight import online_benchmark
from dual_optical_100target_lightweight import benchmark_adapter
from dual_optical_100target_lightweight.benchmark_adapter import (
    shared_snapshot_from_dict,
    shared_snapshot_fingerprint,
)
from dual_optical_100target_lightweight.online import RevolutionSnapshot as GraphSnapshot
from dual_optical_100target_lightweight.online_benchmark import (
    freeze_route,
    load_frozen_route,
)
from dual_optical_100target_lightweight.models import LightweightModel
from dual_optical_100target_lightweight.pipeline import ValidationSelectionError


def _entry(
    protocol: BenchmarkProtocol,
    split: str,
    seed: int,
    level: str,
    revolution: int,
) -> dict[str, object]:
    stem = f"{split}/{seed}/{level}/revolution_{revolution:02d}"
    suffix = f"{seed:08d}{revolution:02d}{len(level):02d}".ljust(64, "0")
    return {
        "split": split,
        "seed": seed,
        "corruption_level": level,
        "revolution_index": revolution,
        "snapshot_path": f"snapshots/{stem}.json",
        "snapshot_sha256": suffix,
        "input_fingerprint": snapshot_fingerprint(
            _shared_snapshot(
                protocol,
                seed=seed,
                split=split,
                level=level,
                revolution=revolution,
            )
        ),
        "label_path": f"labels/{stem}.json",
        "label_sha256": ("f" + suffix[1:]),
    }


def _formal_calibration_manifest(protocol: BenchmarkProtocol) -> dict[str, object]:
    entries = [
        _entry(protocol, split, seed, level, revolution)
        for split, seeds in (
            ("train", protocol.train_seeds),
            ("validation", protocol.validation_seeds),
        )
        for seed in seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    ]
    return {
        "schema_version": "dual-optical-online-dataset-v2",
        "phase": "calibration",
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "test_access_allowed": False,
        "tracker_fingerprint": "unit-shared-tracker-v2",
        "entries": entries,
    }


def _unit(values: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(item * item for item in values))
    return tuple(item / norm for item in values)


def _shared_snapshot(
    protocol: BenchmarkProtocol,
    *,
    seed: int,
    split: str,
    level: str,
    revolution: int,
) -> RevolutionSnapshot:
    positions = {
        "Optical_A": (0.0, -1000.0, -100.0),
        "Optical_B": (0.0, 1000.0, -100.0),
    }
    tracks = {}
    for camera_id, origin in positions.items():
        camera_tracks = []
        for target_index, y_value in enumerate((-120.0, 120.0)):
            samples = []
            for sweep in range(1, revolution + 1):
                timestamp = 2.0 * sweep - 0.2
                point = (2500.0 - 50.0 * timestamp, y_value, -95.0)
                direction = _unit(
                    tuple(point[index] - origin[index] for index in range(3))
                )
                samples.append(
                    SnapshotTrackSample(
                        sweep_index=sweep,
                        timestamp=timestamp,
                        direction_ned=direction,
                        detection_count=1,
                        bbox_area_px2=16.0,
                        confidence=0.9,
                    )
                )
            camera_tracks.append(
                SnapshotTrack(
                    track_id=f"{camera_id}-T{target_index}",
                    camera_id=camera_id,
                    samples=tuple(samples),
                )
            )
        tracks[camera_id] = tuple(camera_tracks)
    return RevolutionSnapshot(
        protocol_fingerprint=protocol.fingerprint,
        seed=seed,
        split=split,
        corruption_level=level,
        revolution_index=revolution,
        cutoff_timestamp=float(2 * revolution),
        camera_ids=("Optical_A", "Optical_B"),
        camera_positions_ned=positions,
        focal_length_px=25000.0,
        tracks=tracks,
        tracker_fingerprint="unit-shared-tracker-v2",
        corruption_summary={"retained_sample_count": revolution * 4},
    )


def test_public_freeze_and_publish_entry_points(
    dataset_manifest, tmp_path, monkeypatch
):
    legacy_manifest, legacy_root = load_legacy_manifest(dataset_manifest)
    source_entry = sample_entries(legacy_manifest, "train")[0]
    source_graph, source_labels = load_entry(
        legacy_root, source_entry, include_labels=True
    )
    assert source_labels is not None
    protocol = BenchmarkProtocol()
    calibration = _formal_calibration_manifest(protocol)
    manifest_path = tmp_path / "calibration_manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")

    opened_snapshots: list[tuple[str, int, str, int]] = []
    opened_labels: list[tuple[str, int, str, int]] = []
    current_entry: dict[str, object] = {}

    def load_manifest(path):
        assert Path(path).resolve() == manifest_path.resolve()
        return calibration

    def read_snapshot(path):
        relative = Path(path).relative_to(tmp_path).parts
        split, seed, level = relative[1], int(relative[2]), relative[3]
        revolution = int(Path(relative[4]).stem.split("_")[-1])
        opened_snapshots.append((split, seed, level, revolution))
        current_entry.clear()
        current_entry.update(
            split=split,
            seed=seed,
            corruption_level=level,
            revolution_index=revolution,
        )
        return _shared_snapshot(
            protocol,
            seed=seed,
            split=split,
            level=level,
            revolution=revolution,
        )

    def build_candidate(snapshot, geometry_gate):
        graph = replace(
            source_graph,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
        )
        return (
            GraphSnapshot.from_graph(
                graph,
                revolution_index=snapshot.revolution_index,
                cutoff_timestamp=snapshot.cutoff_timestamp,
                observation_max_timestamp=snapshot.cutoff_timestamp - 0.1,
            ),
            {},
        )

    def read_labels(path, *, entry, graph):
        assert all(entry[key] == value for key, value in current_entry.items())
        opened_labels.append(
            (
                str(entry["split"]),
                int(entry["seed"]),
                str(entry["corruption_level"]),
                int(entry["revolution_index"]),
            )
        )
        return graph, source_labels, {
            "single_identity_track_count": len(source_labels.identity_a)
            + len(source_labels.identity_b),
            "ambiguous_identity_track_count": 0,
            "empty_identity_track_count": 0,
            "excluded_unknown_edge_count": 0,
        }

    monkeypatch.setattr(online_benchmark, "load_dataset_manifest", load_manifest)
    monkeypatch.setattr(online_benchmark, "read_snapshot", read_snapshot)
    monkeypatch.setattr(online_benchmark, "_build_candidate_snapshot", build_candidate)
    monkeypatch.setattr(online_benchmark, "_read_offline_labels", read_labels)
    original_sha = online_benchmark.sha256_file
    monkeypatch.setattr(
        online_benchmark,
        "sha256_file",
        lambda path: "a" * 64
        if Path(path).resolve() == manifest_path.resolve()
        else original_sha(path),
    )

    freeze_path = freeze_route(manifest_path, tmp_path / "model")
    expected_count = 30 * 3 * 6
    assert len(opened_snapshots) == expected_count
    assert len(opened_labels) == expected_count
    assert {item[0] for item in opened_snapshots} == {"train", "validation"}
    assert all(item[1] not in protocol.test_seeds for item in opened_snapshots)

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    assert freeze["route_name"] == "lightweight"
    assert freeze["protocol_fingerprint"] == protocol.fingerprint
    assert freeze["test_accessed"] is False
    assert freeze["test_paths_opened"] == []
    assert len(freeze["train_inputs"]) == 24 * 3 * 6
    assert len(freeze["validation_inputs"]) == 6 * 3 * 6
    assert len(freeze["frozen_routes"]) == 4
    assert all("parameters" in item["model"] for item in freeze["frozen_routes"])

    label_reads_before_publish = len(opened_labels)
    frozen = load_frozen_route(freeze_path)
    publication = frozen.publish(
        _shared_snapshot(
            protocol,
            seed=protocol.test_seeds[0],
            split="test",
            level="light",
            revolution=4,
        )
    )
    assert len(opened_labels) == label_reads_before_publish
    assert frozen.route_name == "lightweight"
    assert publication.route_name == "lightweight"
    assert publication.input_fingerprint == snapshot_fingerprint(
        _shared_snapshot(
            protocol,
            seed=protocol.test_seeds[0],
            split="test",
            level="light",
            revolution=4,
        )
    )
    assert publication.end_to_end_ms >= publication.scoring_ms + publication.hungarian_ms


def test_freeze_rejects_test_manifest(tmp_path, monkeypatch):
    protocol = BenchmarkProtocol()
    manifest_path = tmp_path / "test_manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    payload = {
        "schema_version": "dual-optical-online-dataset-v1",
        "phase": "test",
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "test_access_allowed": True,
        "entries": [],
    }
    monkeypatch.setattr(online_benchmark, "load_dataset_manifest", lambda path: payload)
    with pytest.raises(ValueError, match="calibration manifest"):
        freeze_route(manifest_path, tmp_path / "model")


def test_online_freeze_writes_structured_precision_failure_without_test_access(
    dataset_manifest, tmp_path, monkeypatch
):
    legacy_manifest, legacy_root = load_legacy_manifest(dataset_manifest)
    source_entry = sample_entries(legacy_manifest, "train")[0]
    source_graph, source_labels = load_entry(
        legacy_root, source_entry, include_labels=True
    )
    assert source_labels is not None
    protocol = benchmark_protocol_for_target_count(20)
    calibration = _formal_calibration_manifest(protocol)
    manifest_path = tmp_path / "calibration_manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    selected_entries = [
        next(
            entry
            for entry in calibration["entries"]
            if entry["split"] == split
        )
        for split in ("train", "validation")
    ]
    for entry in selected_entries:
        explicit_scale_snapshot = replace(
            _shared_snapshot(
                protocol,
                seed=int(entry["seed"]),
                split=str(entry["split"]),
                level=str(entry["corruption_level"]),
                revolution=int(entry["revolution_index"]),
            ),
            target_count=20,
        )
        entry["input_fingerprint"] = snapshot_fingerprint(
            explicit_scale_snapshot
        )
    opened_splits = []

    monkeypatch.setattr(
        online_benchmark,
        "load_dataset_manifest",
        lambda path: calibration,
    )
    monkeypatch.setattr(
        online_benchmark,
        "_validate_calibration_entries",
        lambda manifest, frozen_protocol: selected_entries,
    )

    def read_snapshot(path):
        entry = next(
            item
            for item in selected_entries
            if str(path).endswith(str(item["snapshot_path"]))
        )
        opened_splits.append(str(entry["split"]))
        return replace(
            _shared_snapshot(
                protocol,
                seed=int(entry["seed"]),
                split=str(entry["split"]),
                level=str(entry["corruption_level"]),
                revolution=int(entry["revolution_index"]),
            ),
            target_count=20,
        )

    monkeypatch.setattr(online_benchmark, "read_snapshot", read_snapshot)

    def build_candidate(snapshot, geometry_gate):
        graph = replace(
            source_graph,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
        )
        return (
            GraphSnapshot.from_graph(
                graph,
                revolution_index=snapshot.revolution_index,
                cutoff_timestamp=snapshot.cutoff_timestamp,
                observation_max_timestamp=snapshot.cutoff_timestamp - 0.1,
            ),
            {},
        )

    monkeypatch.setattr(
        online_benchmark, "_build_candidate_snapshot", build_candidate
    )
    monkeypatch.setattr(
        online_benchmark,
        "_read_offline_labels",
        lambda path, *, entry, graph: (graph, source_labels, {}),
    )
    model = LightweightModel(
        "platt_geometry_cost",
        {"coefficient": 1.0, "intercept": 0.0, "C": 1.0},
        2,
    )
    monkeypatch.setattr(
        online_benchmark,
        "fit_all_models",
        lambda *args, **kwargs: (model,),
    )
    monkeypatch.setattr(
        online_benchmark,
        "_validation_rows",
        lambda *args, **kwargs: [
            {
                "model_id": model.model_id,
                "model_kind": model.kind,
                "selected_count": 10,
                "correct_count": 6,
                "conditional_precision": 0.60,
                "macro_precision": 0.60,
                "macro_recall": 0.50,
                "macro_f1": 0.545,
                "false_association_count": 4,
                "duplicate_identity_match_count": 0,
                "duplicate_track_assignment_count": 0,
                "probability_threshold": 0.5,
                "unmatched_cost": 0.6,
                "parameter_count": 2,
            }
        ],
    )
    output = tmp_path / "freeze"

    with pytest.raises(ValidationSelectionError, match="structured failure written"):
        freeze_route(manifest_path, output)

    failure_path = output / "freeze_failure.json"
    assert failure_path.is_file()
    assert not (output / "lightweight_freeze_manifest.json").exists()
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure["target_count"] == 20
    assert failure["protocol_fingerprint"] == protocol.fingerprint
    assert failure["reason_code"] == "conditional_precision_floor_not_met"
    assert failure["best_validation_result"]["conditional_precision"] == 0.60
    assert failure["precision_gate_evidence"] == {
        "best_conditional_precision": 0.60,
        "required_minimum": 0.70,
        "shortfall": pytest.approx(0.10),
        "gate_met": False,
        "best_result_order": "conditional_precision_descending_then_recall_f1",
    }
    assert failure["test_accessed"] is False
    assert failure["test_paths_opened"] == []
    assert failure["freeze_manifest_written"] is False
    assert failure["promotion_allowed"] is False
    assert failure["stop_before_next_scale"] is True
    assert sorted(opened_splits) == ["train", "validation"]


def _label_test_graph() -> OnlineGraph:
    track_ids_a = (
        "A-real",
        "A-tie",
        "A-fa",
        "A-empty",
        "A-zero",
        "A-missing-heading",
    )
    track_ids_b = ("B-real",)
    edge_index = np.asarray(
        [[index for index in range(len(track_ids_a))], [0] * len(track_ids_a)],
        dtype=np.int64,
    )
    graph = OnlineGraph(
        seed=11,
        corruption_level="light",
        camera_ids=("Optical_A", "Optical_B"),
        track_ids_a=track_ids_a,
        track_ids_b=track_ids_b,
        node_features_a=np.zeros((len(track_ids_a), len(NODE_FEATURE_NAMES)), dtype=np.float32),
        node_features_b=np.zeros((len(track_ids_b), len(NODE_FEATURE_NAMES)), dtype=np.float32),
        edge_index=edge_index,
        edge_features=np.zeros((len(track_ids_a), len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        geometry_cost=np.zeros((len(track_ids_a),), dtype=np.float32),
        corruption_summary=CorruptionSummary("light", 11, 0, 0, 0, 0),
    )
    graph.validate()
    return graph


def test_offline_label_counts_require_unique_real_dominant_truth(tmp_path):
    graph = _label_test_graph()
    label_path = tmp_path / "labels.json"
    label_path.write_text(
        json.dumps(
            {
                "schema_version": "dual-optical-online-dataset-v1",
                "offline_truth_only": True,
                "seed": 11,
                "corruption_level": "light",
                "revolution_index": 2,
                "track_truth_counts": {
                    "A-real": {"TRUTH-001": 5, "TRUTH-002": 3},
                    "A-tie": {"TRUTH-001": 4, "TRUTH-002": 4},
                    "A-fa": {"FA-Optical_A-001": 6, "TRUTH-001": 5},
                    "A-empty": {},
                    "A-zero": {"TRUTH-001": 0, "FA-Optical_A-002": -1},
                    "A-missing-heading": {"TRUTH-999": 3},
                    "B-real": {"TRUTH-001": 7},
                },
                "truth_heading_groups": {
                    "TRUTH-001": "heading_0_deg",
                    "TRUTH-002": "heading_minus_30_deg",
                },
            }
        ),
        encoding="utf-8",
    )
    filtered, labels, diagnostics = online_benchmark._read_offline_labels(
        label_path,
        entry={"seed": 11, "corruption_level": "light", "revolution_index": 2},
        graph=graph,
    )

    assert labels.identity_a == ("TRUTH-001", None, None, None, None, None)
    assert labels.identity_b == ("TRUTH-001",)
    assert filtered.edge_index.tolist() == [[0], [0]]
    assert labels.edge_labels.tolist() == [1.0]
    assert labels.expected_identities == ("TRUTH-001",)
    assert diagnostics == {
        "single_identity_track_count": 2,
        "ambiguous_identity_track_count": 1,
        "empty_identity_track_count": 2,
        "false_alarm_dominant_track_count": 1,
        "missing_heading_group_track_count": 1,
        "excluded_unknown_edge_count": 5,
    }


def test_snapshot_source_kind_is_anonymous_at_both_adapter_boundaries(monkeypatch):
    protocol = BenchmarkProtocol()
    snapshot = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    payload = snapshot.online_payload()
    for camera_tracks in payload["tracks"].values():
        for track in camera_tracks:
            track["source_kind"] = "actor_truth"

    parsed = shared_snapshot_from_dict(payload)
    assert {
        track.source_kind
        for camera_tracks in parsed.tracks.values()
        for track in camera_tracks
    } == {"anonymous"}

    original_build = benchmark_adapter.build_online_graph
    observed_source_kinds: set[str] = set()

    def recording_build(episode, summary, *, gate):
        observed_source_kinds.update(
            track.source_kind
            for camera_tracks in episode.tracks.values()
            for track in camera_tracks
        )
        return original_build(episode, summary, gate=gate)

    monkeypatch.setattr(benchmark_adapter, "build_online_graph", recording_build)
    benchmark_adapter._build_candidate_snapshot(snapshot, asdict(GeometryGate()))
    assert observed_source_kinds == {"anonymous"}


@pytest.mark.parametrize("target_count", (20, 40, 60, 100))
def test_optional_target_count_is_parsed_and_passed_to_online_episode(
    target_count, monkeypatch
):
    protocol = benchmark_protocol_for_target_count(target_count)
    snapshot = replace(
        _shared_snapshot(
            protocol,
            seed=protocol.test_seeds[0],
            split="test",
            level="clean",
            revolution=2,
        ),
        target_count=target_count,
    )
    payload = snapshot.online_payload()
    parsed = shared_snapshot_from_dict(payload)
    observed_target_counts = []
    original_build = benchmark_adapter.build_online_graph

    def recording_build(episode, summary, *, gate):
        observed_target_counts.append(episode.configured_target_count)
        return original_build(episode, summary, gate=gate)

    monkeypatch.setattr(benchmark_adapter, "build_online_graph", recording_build)
    _, diagnostics = benchmark_adapter._build_candidate_snapshot(
        parsed, asdict(GeometryGate())
    )

    assert parsed.target_count == target_count
    assert observed_target_counts == [target_count]
    assert diagnostics["configured_target_count"] == target_count


def test_snapshot_without_target_count_remains_compatible_and_fingerprinted():
    protocol = BenchmarkProtocol()
    snapshot = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    payload = snapshot.online_payload()
    payload.pop("target_count")
    source_fingerprint = benchmark_adapter._canonical_payload_fingerprint(payload)
    payload["input_fingerprint"] = source_fingerprint

    parsed = shared_snapshot_from_dict(payload)
    _, diagnostics = benchmark_adapter._build_candidate_snapshot(
        parsed, asdict(GeometryGate())
    )

    assert parsed.target_count is None
    assert diagnostics["configured_target_count"] == -1
    assert shared_snapshot_fingerprint(parsed) == source_fingerprint


@pytest.mark.parametrize("invalid", (True, 0, -1, 20.0, "20"))
def test_snapshot_target_count_rejects_nonpositive_or_noninteger_values(invalid):
    protocol = BenchmarkProtocol()
    snapshot = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    payload = snapshot.online_payload()
    payload["target_count"] = invalid

    with pytest.raises(ValueError, match="positive integer"):
        shared_snapshot_from_dict(payload)


def test_shared_snapshot_strict_contract_still_rejects_unknown_fields():
    protocol = BenchmarkProtocol()
    snapshot = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    payload = snapshot.online_payload()
    payload["unexpected_scale_hint"] = 100

    with pytest.raises(ValueError, match="fields do not match"):
        shared_snapshot_from_dict(payload)


def test_snapshot_v1_is_read_compatibly_and_v2_covariance_is_propagated(monkeypatch):
    protocol = BenchmarkProtocol()
    v2_snapshot = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    observed = {}
    original_build = benchmark_adapter.build_online_graph

    def recording_build(episode, summary, *, gate):
        track = episode.tracks[episode.camera_ids[0]][0]
        observed[episode.snapshot_contract_version] = track
        return original_build(episode, summary, gate=gate)

    monkeypatch.setattr(benchmark_adapter, "build_online_graph", recording_build)
    benchmark_adapter._build_candidate_snapshot(v2_snapshot, asdict(GeometryGate()))
    assert observed["v2"].angular_velocity_deg_s is not None
    assert observed["v2"].state_covariance is not None
    assert observed["v2"].recent_revolution_hits == (False, False, False)
    assert observed["v2"].samples[0].direction_covariance_mrad2 is not None

    payload = v2_snapshot.online_payload()
    payload["schema_version"] = LEGACY_SCHEMA_VERSION
    payload.pop("tracker_fingerprint")
    for camera_tracks in payload["tracks"].values():
        for track in camera_tracks:
            track["source_kind"] = "anonymous"
            for name in (
                "track_state",
                "recent_sweep_hits",
                "missed_sweep_count",
                "ambiguity_count",
            ):
                track.pop(name)
            for sample in track["samples"]:
                for name in (
                    "measurement_covariance_deg2",
                    "state_vector",
                    "state_covariance",
                    "innovation_mahalanobis2",
                ):
                    sample.pop(name)
    legacy = shared_snapshot_from_dict(payload)
    assert shared_snapshot_fingerprint(legacy) == benchmark_adapter._canonical_payload_fingerprint(payload)
    benchmark_adapter._build_candidate_snapshot(legacy, asdict(GeometryGate()))
    assert observed["v1"].angular_velocity_deg_s is None
    assert observed["v1"].state_covariance is None
    assert observed["v1"].recent_revolution_hits == ()
    assert observed["v1"].samples[0].direction_covariance_mrad2 is None


def test_shared_candidate_allowlist_is_a_hard_boundary_and_fingerprint_is_returned(
    monkeypatch,
):
    protocol = BenchmarkProtocol()
    original = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    pair = ("Optical_A-T0", "Optical_B-T0")
    summary = {"construction": "unit", "candidate_count": 1}
    snapshot = replace(
        original,
        geometry_candidate_pairs=(pair,),
        candidate_graph_summary=summary,
        candidate_graph_fingerprint=candidate_graph_fingerprint((pair,), summary),
    )
    candidate_snapshot, diagnostics = benchmark_adapter._build_candidate_snapshot(
        snapshot, asdict(GeometryGate())
    )
    graph = candidate_snapshot.graph
    graph_pairs = {
        (graph.track_ids_a[index_a], graph.track_ids_b[index_b])
        for index_a, index_b in graph.edge_index.T
    }
    assert graph_pairs <= {pair}
    assert diagnostics["shared_candidate_allowlist_used"] == 1
    assert diagnostics["shared_candidate_allowlist_count"] == 1
    assert diagnostics["evaluated_pair_count"] == 1


def test_explicit_empty_shared_allowlist_does_not_fall_back_to_all_pairs():
    protocol = BenchmarkProtocol()
    original = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    summary = {"construction": "unit", "candidate_count": 0}
    snapshot = replace(
        original,
        geometry_candidate_pairs=(),
        candidate_graph_summary=summary,
        candidate_graph_fingerprint=candidate_graph_fingerprint((), summary),
    )
    candidate_snapshot, diagnostics = benchmark_adapter._build_candidate_snapshot(
        snapshot, asdict(GeometryGate())
    )
    assert candidate_snapshot.graph.edge_index.shape == (2, 0)
    assert diagnostics["shared_candidate_allowlist_used"] == 1
    assert diagnostics["shared_candidate_allowlist_count"] == 0
    assert diagnostics["evaluated_pair_count"] == 0


def test_legacy_snapshot_without_shared_allowlist_uses_compatibility_gate():
    protocol = BenchmarkProtocol()
    snapshot = _shared_snapshot(
        protocol,
        seed=protocol.test_seeds[0],
        split="test",
        level="light",
        revolution=2,
    )
    candidate_snapshot, diagnostics = benchmark_adapter._build_candidate_snapshot(
        snapshot, asdict(GeometryGate())
    )
    assert diagnostics["shared_candidate_allowlist_used"] == 0
    assert diagnostics["geometry_candidate_source"] == "frozen_route_gate_v1_fallback"
    assert diagnostics["evaluated_pair_count"] >= candidate_snapshot.graph.edge_index.shape[1]
