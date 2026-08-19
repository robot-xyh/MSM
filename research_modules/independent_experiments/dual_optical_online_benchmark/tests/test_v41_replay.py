from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pytest

import dual_optical_online_benchmark.v41_replay as v41
from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    benchmark_protocol_for_target_count,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from dual_optical_online_benchmark.dataset import sha256_file
from dual_optical_target_track_gnn.contracts import (
    BearingObservation,
    ConfirmedTrackPair,
    TargetHypothesis,
    TargetTrackGraph,
    payload_fingerprint,
)
from dual_optical_target_track_gnn.deterministic import (
    solve_deterministic_assignment,
)
from dual_optical_target_track_gnn.geometry import (
    GeometryFitError,
    weighted_line_of_sight_fit,
)
from dual_optical_target_track_gnn.graph import (
    TargetTrackGate,
    target_track_evidence,
)
from dual_optical_target_track_gnn.contracts import (
    EDGE_FEATURE_NAMES,
    TARGET_FEATURE_NAMES,
    TRACK_FEATURE_NAMES,
)


def _empty_snapshot(seed: int, level: str, revolution: int) -> RevolutionSnapshot:
    protocol = benchmark_protocol_for_target_count(20)
    return RevolutionSnapshot(
        protocol_fingerprint=protocol.fingerprint,
        seed=seed,
        split="test",
        corruption_level=level,
        revolution_index=revolution,
        cutoff_timestamp=revolution * protocol.scan_period_s,
        camera_ids=("Optical_A", "Optical_B"),
        camera_positions_ned={
            "Optical_A": (0.0, -1000.0, -100.0),
            "Optical_B": (0.0, 1000.0, -100.0),
        },
        focal_length_px=25_000.0,
        tracks={"Optical_A": (), "Optical_B": ()},
        target_count=20,
        tracker_fingerprint="b" * 64,
        candidate_graph_fingerprint="",
    )


def _source_fixture(root: Path) -> Path:
    protocol = benchmark_protocol_for_target_count(20)
    source = root / "targets_020"
    dataset = source / "dataset"
    publications = source / "results" / "publications"
    entries = []
    for seed in protocol.test_seeds:
        for level in protocol.corruption_levels:
            for revolution in range(1, protocol.revolution_count + 1):
                snapshot = _empty_snapshot(seed, level, revolution)
                snapshot_path = (
                    dataset
                    / "snapshots"
                    / "test"
                    / str(seed)
                    / level
                    / f"revolution_{revolution:02d}.json"
                )
                write_snapshot(snapshot_path, snapshot)
                publication_path = (
                    publications
                    / str(seed)
                    / level
                    / f"revolution_{revolution:02d}_track_superglue.json"
                )
                write_json(
                    publication_path,
                    {
                        "route_name": "track_superglue",
                        "route_version": "dual-optical-track-superglue-online-v1",
                        "model_fingerprint": "a" * 64,
                        "seed": seed,
                        "corruption_level": level,
                        "revolution_index": revolution,
                        "cutoff_timestamp": snapshot.cutoff_timestamp,
                        "input_fingerprint": snapshot_fingerprint(snapshot),
                        "candidate_graph_fingerprint": "",
                        "availability": "empty_candidate_graph_cpu",
                        "matches": [],
                        "rejection_reasons": {"empty_candidate_graph": 1},
                        "scoring_ms": 0.1,
                        "hungarian_ms": 0.0,
                        "end_to_end_ms": 0.2,
                        "deadline_ms": 1000.0,
                    },
                )
                entries.append(
                    {
                        "split": "test",
                        "seed": seed,
                        "corruption_level": level,
                        "revolution_index": revolution,
                        "snapshot_path": str(snapshot_path.relative_to(dataset)),
                        "snapshot_sha256": sha256_file(snapshot_path),
                        "input_fingerprint": snapshot_fingerprint(snapshot),
                        "label_path": (
                            f"labels/test/{seed}/{level}/revolution_{revolution:02d}.json"
                        ),
                        "label_sha256": "not-opened-by-online-fixture",
                        "tracker_fingerprint": "b" * 64,
                    }
                )
    write_json(
        dataset / "test_manifest.json",
        {
            "schema_version": "dual-optical-online-dataset-v1",
            "phase": "test",
            "protocol": asdict(protocol),
            "protocol_fingerprint": protocol.fingerprint,
            "test_access_allowed": True,
            "entries": entries,
        },
    )
    route_freeze = dataset / "freezes" / "track_superglue" / "freeze_manifest.json"
    write_json(
        route_freeze,
        {
            "schema_version": "dual-optical-track-superglue-freeze-v1",
            "route_name": "track_superglue",
            "route_version": "dual-optical-track-superglue-online-v1",
            "model_fingerprint_sha256": "a" * 64,
            "protocol_fingerprint_sha256": protocol.fingerprint,
            "target_count": 20,
            "artifact_sha256": {},
        },
    )
    write_json(
        dataset / "freezes" / "all_routes_frozen.json",
        {
            "schema_version": "test-all-routes",
            "protocol_fingerprint": protocol.fingerprint,
            "active_routes": ["track_superglue"],
            "routes": {
                "track_superglue": {
                    "freeze_manifest_sha256": sha256_file(route_freeze)
                }
            },
        },
    )
    return source


def test_online_manifest_recursively_excludes_identity_fields_and_preserves_source(
    tmp_path: Path,
) -> None:
    source = _source_fixture(tmp_path)
    first_publication = sorted((source / "results" / "publications").rglob("*.json"))[0]
    source_hash = sha256_file(first_publication)

    manifest_path = v41.write_v41_online_manifest(source, tmp_path / "output")
    manifest = v41.validate_v41_online_manifest(manifest_path)
    serialized = manifest_path.read_text(encoding="utf-8").lower()

    assert all(marker not in serialized for marker in ("truth", "actor", "label", "global_track_id"))
    assert manifest["formal_use_allowed"] is False
    assert sha256_file(first_publication) == source_hash
    with pytest.raises(ValueError, match="identity-bearing"):
        v41.assert_online_anonymous({"nested": [{"actor_id": "bad"}]})


def test_online_manifest_rejects_path_escape_and_source_hash_tampering(
    tmp_path: Path,
) -> None:
    source = _source_fixture(tmp_path)
    output = tmp_path / "output"
    manifest_path = v41.write_v41_online_manifest(source, output)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["entries"][0]["snapshot_path"] = "../escape.json"
    payload.pop("manifest_fingerprint")
    write_json(
        output / "escaped.json",
        v41._signed_payload(payload, "manifest_fingerprint"),
    )
    with pytest.raises(ValueError, match="escapes"):
        v41.validate_v41_online_manifest(
            output / "escaped.json", validate_artifacts=False
        )

    publication = source / json.loads(manifest_path.read_text())["entries"][0][
        "source_publication_path"
    ]
    original = json.loads(publication.read_text(encoding="utf-8"))
    write_json(publication, dict(original, seed=999))
    with pytest.raises(ValueError, match="hash mismatch"):
        v41.validate_v41_online_manifest(manifest_path)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("seed", 999, "seed"),
        ("revolution_index", 6, "revolution"),
        ("input_fingerprint", "foreign", "input"),
    ),
)
def test_source_publication_rejects_identity_mismatch(
    field: str, value: object, reason: str
) -> None:
    snapshot = _empty_snapshot(20282301, "clean", 1)
    payload = {
        "route_name": "track_superglue",
        "route_version": "dual-optical-track-superglue-online-v1",
        "model_fingerprint": "a" * 64,
        "seed": snapshot.seed,
        "corruption_level": snapshot.corruption_level,
        "revolution_index": snapshot.revolution_index,
        "input_fingerprint": snapshot_fingerprint(snapshot),
        "candidate_graph_fingerprint": snapshot.candidate_graph_fingerprint,
        "matches": [],
    }
    payload[field] = value
    with pytest.raises(ValueError, match=reason):
        v41._validate_source_publication(
            payload, snapshot, model_fingerprint="a" * 64
        )


def test_protocol_mismatch_and_formal_status_fail_closed(tmp_path: Path) -> None:
    source = _source_fixture(tmp_path)
    output = tmp_path / "output"
    manifest_path = v41.write_v41_online_manifest(source, output)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["protocol_fingerprint"] = "foreign"
    payload.pop("manifest_fingerprint")
    write_json(
        output / "bad_protocol.json",
        v41._signed_payload(payload, "manifest_fingerprint"),
    )
    with pytest.raises(ValueError, match="protocol fingerprint"):
        v41.validate_v41_online_manifest(
            output / "bad_protocol.json", validate_artifacts=False
        )

    publications = v41.write_v41_publications(manifest_path, output)
    publication_payload = json.loads(publications.read_text(encoding="utf-8"))
    publication_payload["formal_use_allowed"] = True
    publication_payload.pop("publication_manifest_fingerprint")
    write_json(
        output / "invalid_formal.json",
        v41._signed_payload(
            publication_payload, "publication_manifest_fingerprint"
        ),
    )
    with pytest.raises(ValueError, match="invalid evidence status"):
        v41.validate_v41_publication_manifest(output / "invalid_formal.json")


def test_empty_first_revolution_and_noncausal_pair_fail_closed() -> None:
    hypotheses, sources, failures = v41._hypotheses_for_revolution(
        current_revolution=1,
        snapshots={},
        wrapped_publications={},
        weighted_fit_config=v41.WeightedFitConfig(),
    )
    assert hypotheses == ()
    assert sources == {}
    assert failures == Counter()

    publication = {
        "schema_version": v41.PAIR_PUBLICATION_SCHEMA_VERSION,
        "online_anonymous": True,
        "seed": 1,
        "protocol_fingerprint": "p",
        "corruption_level": "clean",
        "revolution_index": 1,
        "input_fingerprint": "i",
        "candidate_graph_fingerprint": "g",
        "route_name": v41.PAIR_PUBLICATION_ROUTE,
        "matches": [],
        "latency_ms": 0.0,
    }
    publication["publication_fingerprint"] = v41.online_pair_publication_fingerprint(
        publication
    )
    hypotheses, _, _ = v41._hypotheses_for_revolution(
        current_revolution=3,
        snapshots={},
        wrapped_publications={1: publication},
        weighted_fit_config=v41.WeightedFitConfig(),
    )
    assert hypotheses == ()


def test_ill_conditioned_fit_and_stale_prediction_are_rejected() -> None:
    observations = tuple(
        BearingObservation(
            camera_id=("A" if index % 2 == 0 else "B"),
            track_id=("A1" if index % 2 == 0 else "B1"),
            timestamp=float(index) * 0.1,
            camera_position_ned=(0.0, float(index % 2) * 1000.0, 0.0),
            direction_ned=(1.0, 0.0, 0.0),
            bearing_variance_rad2=1.0e-8,
            source_revolution_index=1,
        )
        for index in range(6)
    )
    with pytest.raises(GeometryFitError):
        weighted_line_of_sight_fit(observations)

    pair = ConfirmedTrackPair(
        revolution_index=1,
        track_a_id="A-seed",
        track_b_id="B-seed",
        publication_fingerprint="a" * 64,
        publication_input_fingerprint="input",
        publication_protocol_fingerprint="protocol",
        publication_seed=1,
    )
    hypothesis = TargetHypothesis(
        hypothesis_id="H-stale",
        created_revolution_index=2,
        reference_timestamp=1.0,
        state_ned=(3000.0, 0.0, -100.0, -50.0, 0.0, 0.0),
        covariance_6x6=tuple(np.eye(6).reshape(-1)),
        support_count=6,
        confirmed_pairs=(pair,),
        fit_rms_mrad=0.1,
        fit_condition_number=10.0,
        last_observation_timestamp=1.0,
    )
    sample = SnapshotTrackSample(
        sweep_index=5,
        timestamp=12.0,
        direction_ned=(1.0, 0.0, 0.0),
        detection_count=1,
        bbox_area_px2=1.0,
        confidence=1.0,
    )
    track = SnapshotTrack(
        track_id="A-current",
        camera_id="Optical_A",
        source_kind="anonymous",
        track_state="confirmed",
        recent_sweep_hits=(True, True, True),
        samples=(sample,),
    )
    evidence = target_track_evidence(
        hypothesis,
        track,
        (0.0, -1000.0, -100.0),
        cutoff_timestamp=12.0,
        gate=TargetTrackGate(
            minimum_track_samples=1, maximum_prediction_age_s=1.0
        ),
    )
    assert not evidence.gate_passed
    assert "prediction_age" in evidence.rejection_reasons


def _manual_graph() -> TargetTrackGraph:
    hypothesis_ids = ("H0", "H1")
    track_ids = ("T0", "T1", "T2")
    edge_index = np.asarray(((0, 1), (0, 1)), dtype=np.int64)
    fingerprint = payload_fingerprint(
        {
            "schema_version": "dual-optical-target-track-gnn-v1",
            "seed": 1,
            "revolution_index": 5,
            "camera_id": "A",
            "edges": [["H0", "T0"], ["H1", "T1"]],
        }
    )
    return TargetTrackGraph(
        seed=1,
        revolution_index=5,
        camera_id="A",
        hypothesis_ids=hypothesis_ids,
        track_ids=track_ids,
        target_features=np.ones((2, len(TARGET_FEATURE_NAMES)), dtype=np.float32),
        track_features=np.ones((3, len(TRACK_FEATURE_NAMES)), dtype=np.float32),
        edge_index=edge_index,
        edge_features=np.ones((2, len(EDGE_FEATURE_NAMES)), dtype=np.float32),
        rule_cost=np.asarray((0.1, 1.5), dtype=np.float32),
        whitelist_fingerprint=fingerprint,
    )


def test_deterministic_hungarian_is_one_to_one_keeps_unmatched_and_cannot_expand() -> None:
    graph = _manual_graph()
    result = solve_deterministic_assignment(graph, unmatched_cost=1.0)

    assert [(item.hypothesis_index, item.track_index) for item in result.selected_pairs] == [
        (0, 0)
    ]
    assert result.unmatched_hypothesis_indices == (1,)
    assert result.unmatched_track_indices == (1, 2)
    assert result.duplicate_assignment_count == 0
    assert all(item.edge_index < graph.edge_index.shape[1] for item in result.selected_pairs)


def test_diagnostic_classifier_never_returns_formal_status() -> None:
    statuses = {
        v41.classify_v41_diagnostic(
            coverage_delta=delta,
            coverage_delta_ci95=(lower, upper),
            false_opportunity_rate_delta=false_delta,
            latency_p95_ms=latency,
            safety_violation_count=violations,
        )[0]
        for delta, lower, upper, false_delta, latency, violations in (
            (0.03, 0.01, 0.05, 0.0, 10.0, 0),
            (0.0, 0.0, 0.01, 0.0, 10.0, 0),
            (-0.1, -0.2, 0.0, 0.0, 10.0, 0),
        )
    }
    assert statuses == {
        "diagnostic_improved",
        "diagnostic_neutral",
        "diagnostic_rejected",
    }
    assert all("formal" not in status for status in statuses)
