from __future__ import annotations

from dataclasses import replace
import json

import pytest

from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    AssociationPublication,
    BenchmarkProtocol,
    LEGACY_SCHEMA_VERSION,
    PREVIOUS_SCHEMA_VERSION,
    ROUTE_NAMES,
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    read_snapshot,
    snapshot_fingerprint,
    validate_shared_publications,
    write_snapshot,
    benchmark_protocol_for_target_count,
    s180_protocol_for_target_count,
    candidate_graph_fingerprint,
)
from dual_optical_online_benchmark.dataset import sha256_file
from dual_optical_online_benchmark.orchestrator import (
    ALL_ROUTES_FREEZE_SCHEMA,
    _load_routes,
    _main_gate_elimination,
    _positive_validation_metrics,
    validate_freeze_marker,
)
from dual_optical_online_benchmark.tracking import (
    SharedTrackerConfig,
    tracker_freeze_payload,
)


def _snapshot() -> RevolutionSnapshot:
    protocol = BenchmarkProtocol()
    sample = SnapshotTrackSample(0, 1.5, (1.0, 0.0, 0.0), 1, 4.0, 0.9)
    return RevolutionSnapshot(
        protocol.fingerprint,
        20261101,
        "test",
        "light",
        1,
        2.0,
        ("Optical_A", "Optical_B"),
        {"Optical_A": (0.0, -1000.0, -100.0), "Optical_B": (0.0, 1000.0, -100.0)},
        24999.0,
        {
            "Optical_A": (SnapshotTrack("A-1", "Optical_A", (sample,)),),
            "Optical_B": (SnapshotTrack("B-1", "Optical_B", (sample,)),),
        },
    )


def _publication(snapshot: RevolutionSnapshot, route: str) -> AssociationPublication:
    return AssociationPublication(
        route,
        "v1",
        f"{route}-model",
        snapshot.seed,
        snapshot.corruption_level,
        snapshot.revolution_index,
        snapshot.cutoff_timestamp,
        snapshot_fingerprint(snapshot),
        "available",
        (AssociationMatch("A-1", "B-1", 0.2, "raw"),),
        scoring_ms=1.0,
        hungarian_ms=2.0,
        end_to_end_ms=4.0,
    )


def test_formal_protocol_is_24_6_20_and_six_revolutions() -> None:
    protocol = BenchmarkProtocol()
    assert (len(protocol.train_seeds), len(protocol.validation_seeds), len(protocol.test_seeds)) == (24, 6, 20)
    assert protocol.revolution_count == 6
    assert protocol.zero_heading_count == protocol.minus_thirty_heading_count == 50


def test_s180_protocol_has_twelve_one_way_rounds_and_frozen_seeds() -> None:
    protocol = s180_protocol_for_target_count(20)
    assert protocol.scan_mode == "triangle"
    assert protocol.scan_half_span_deg == 90.0
    assert protocol.scan_period_s == 2.0
    assert protocol.association_round_period_s == 1.0
    assert protocol.association_round_count == 12
    assert protocol.mechanical_cycle_count == 6
    assert protocol.corruption_levels == ("clean", "light")
    assert protocol.train_seeds == tuple(range(20283001, 20283009))
    assert protocol.validation_seeds == (20283101, 20283102)
    assert protocol.test_seeds == tuple(range(20283301, 20283306))


def test_s180_snapshot_round_trip_records_dynamic_round_boundary(tmp_path) -> None:
    protocol = s180_protocol_for_target_count(20)
    snapshot = replace(
        _snapshot(),
        protocol_fingerprint=protocol.fingerprint,
        revolution_index=12,
        cutoff_timestamp=12.0,
        association_round_period_s=1.0,
        association_round_count=12,
    )
    path = tmp_path / "s180_round_12.json"
    write_snapshot(path, snapshot)
    loaded = read_snapshot(path)
    assert loaded == snapshot


def test_v2_snapshot_defaults_to_six_two_second_rounds(tmp_path) -> None:
    snapshot = replace(
        _snapshot(),
        schema_version=PREVIOUS_SCHEMA_VERSION,
        association_round_period_s=2.0,
        association_round_count=6,
    )
    path = tmp_path / "snapshot_v2.json"
    write_snapshot(path, snapshot)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "association_round_period_s" not in payload
    loaded = read_snapshot(path)
    assert loaded.association_round_period_s == 2.0
    assert loaded.association_round_count == 6


def test_scale_protocols_use_isolated_seed_budgets_and_clean_condition() -> None:
    protocols = [
        benchmark_protocol_for_target_count(count)
        for count in (20, 40, 60, 100)
    ]
    for protocol in protocols[:3]:
        assert tuple(map(len, (protocol.train_seeds, protocol.validation_seeds, protocol.test_seeds))) == (8, 2, 5)
    assert tuple(map(len, (protocols[-1].train_seeds, protocols[-1].validation_seeds, protocols[-1].test_seeds))) == (24, 6, 20)
    assert all(protocol.corruption_levels[0] == "clean" for protocol in protocols)
    all_seeds = [seed for protocol in protocols for split in (protocol.train_seeds, protocol.validation_seeds, protocol.test_seeds) for seed in split]
    assert len(all_seeds) == len(set(all_seeds))
    assert not set(protocols[-1].test_seeds) & set(BenchmarkProtocol().test_seeds)
    assert protocols[0].test_seeds == tuple(range(20282301, 20282306))
    assert protocols[1].test_seeds == tuple(range(20284301, 20284306))
    assert protocols[2].test_seeds == tuple(range(20286301, 20286306))
    assert protocols[3].test_seeds == tuple(range(20290201, 20290221))


def test_shared_candidate_graph_round_trip_and_unknown_edge_rejection(tmp_path) -> None:
    snapshot = _snapshot()
    summary = {"builder_version": "covariance-epipolar-topk-v1", "top_k_per_track": 8}
    pairs = (("A-1", "B-1"),)
    snapshot = replace(
        snapshot,
        target_count=20,
        geometry_candidate_pairs=pairs,
        candidate_graph_summary=summary,
        candidate_graph_fingerprint=candidate_graph_fingerprint(pairs, summary),
    )
    path = tmp_path / "shared.json"
    write_snapshot(path, snapshot)
    assert read_snapshot(path) == snapshot
    with pytest.raises(ValueError, match="unknown track"):
        replace(
            snapshot,
            geometry_candidate_pairs=(("A-missing", "B-1"),),
            candidate_graph_fingerprint=candidate_graph_fingerprint(
                (("A-missing", "B-1"),), summary
            ),
        )


def test_snapshot_rejects_future_observation() -> None:
    snapshot = _snapshot()
    future = SnapshotTrackSample(1, 2.1, (1.0, 0.0, 0.0), 1, 4.0, 0.9)
    tracks = dict(snapshot.tracks)
    tracks["Optical_A"] = (SnapshotTrack("A-1", "Optical_A", (future,)),)
    with pytest.raises(ValueError, match="future"):
        replace(snapshot, tracks=tracks)


def test_publications_must_share_snapshot_fingerprint() -> None:
    snapshot = _snapshot()
    publications = [_publication(snapshot, route) for route in ROUTE_NAMES]
    validate_shared_publications(snapshot, publications)
    publications[-1] = replace(publications[-1], input_fingerprint="wrong")
    with pytest.raises(ValueError, match="shared snapshot"):
        validate_shared_publications(snapshot, publications)


def test_publication_rejects_duplicate_assignment() -> None:
    snapshot = _snapshot()
    with pytest.raises(ValueError, match="one-to-one"):
        replace(
            _publication(snapshot, "lightweight"),
            matches=(
                AssociationMatch("A-1", "B-1", 0.2, "raw"),
                AssociationMatch("A-1", "B-2", 0.3, "raw"),
            ),
        )


def test_snapshot_round_trip_preserves_fingerprint(tmp_path) -> None:
    snapshot = _snapshot()
    path = tmp_path / "snapshot.json"
    write_snapshot(path, snapshot)
    loaded = read_snapshot(path)
    assert loaded == snapshot
    assert snapshot_fingerprint(loaded) == snapshot_fingerprint(snapshot)


def test_legacy_v1_snapshot_round_trip_uses_legacy_fingerprint(tmp_path) -> None:
    snapshot = replace(
        _snapshot(),
        schema_version=LEGACY_SCHEMA_VERSION,
        tracker_fingerprint="legacy-unfrozen-tracker",
    )
    path = tmp_path / "snapshot_v1.json"
    write_snapshot(path, snapshot)
    loaded = read_snapshot(path)
    assert loaded.schema_version == LEGACY_SCHEMA_VERSION
    assert loaded.tracker_fingerprint == "legacy-unfrozen-tracker"
    assert snapshot_fingerprint(loaded) == snapshot_fingerprint(snapshot)


def test_timeout_publication_cannot_backfill_matches() -> None:
    with pytest.raises(ValueError, match="backfill"):
        replace(_publication(_snapshot(), "gnn"), availability="timeout")


def test_freeze_acceptance_rejects_zero_validation_skill(tmp_path) -> None:
    route_dir = tmp_path / "epipolar_mht"
    route_dir.mkdir()
    manifest = route_dir / "freeze_manifest.json"
    manifest.write_text(
        '{"selected_validation_metrics": {'
        '"f1": 0.0, "correct_association_count": 0, '
        '"false_association_count": 0}}',
        encoding="utf-8",
    )
    evidence = _positive_validation_metrics("epipolar_mht", manifest)
    assert evidence["accepted"] is False
    assert evidence["failure_reason"] == "zero_validation_association_skill"


def test_freeze_acceptance_requires_positive_f1_and_correct_match(tmp_path) -> None:
    route_dir = tmp_path / "epipolar_mht"
    route_dir.mkdir()
    manifest = route_dir / "freeze_manifest.json"
    manifest.write_text(
        '{"selected_validation_metrics": {'
        '"f1": 0.25, "correct_association_count": 2, '
        '"false_association_count": 1}}',
        encoding="utf-8",
    )
    evidence = _positive_validation_metrics("epipolar_mht", manifest)
    assert evidence["accepted"] is True
    assert evidence["validation_selected_count"] == 3


def test_gnn_positive_f1_proves_a_positive_selected_match(tmp_path) -> None:
    route_dir = tmp_path / "gnn"
    route_dir.mkdir()
    selection = route_dir / "validation_selection.json"
    selection.write_text(
        '{"selected_route": "hybrid", "best_by_route": {'
        '"hybrid": {"macro_f1": 0.1}}}',
        encoding="utf-8",
    )
    manifest = route_dir / "freeze_manifest.json"
    manifest.write_text(
        '{"selected_route": "hybrid", '
        '"validation_selection": "validation_selection.json"}',
        encoding="utf-8",
    )
    evidence = _positive_validation_metrics("gnn", manifest)
    assert evidence["accepted"] is True


def test_track_superglue_requires_counted_positive_validation_evidence(tmp_path) -> None:
    route_dir = tmp_path / "track_superglue"
    route_dir.mkdir()
    selection = route_dir / "validation_selection.json"
    selection.write_text(
        '{"selected_validation_metrics": {"macro_f1": 0.2, '
        '"correct_assignment_count": 3, "selected_assignment_count": 4}, '
        '"validation_failed_closed": false}',
        encoding="utf-8",
    )
    manifest = route_dir / "freeze_manifest.json"
    manifest.write_text(
        '{"validation_selection": "validation_selection.json"}',
        encoding="utf-8",
    )
    evidence = _positive_validation_metrics("track_superglue", manifest)
    assert evidence["accepted"] is True
    assert evidence["validation_correct_association_count"] == 3


def test_track_superglue_inline_freeze_selection_is_main_readable(tmp_path) -> None:
    manifest = tmp_path / "freeze_manifest.json"
    manifest.write_text(
        '{"validation_selection": {"macro_f1": 0.2, '
        '"correct_assignment_count": 3, "selected_assignment_count": 4, '
        '"validation_failed_closed": false}}',
        encoding="utf-8",
    )
    evidence = _positive_validation_metrics("track_superglue", manifest)
    assert evidence["accepted"] is True
    assert evidence["evidence_path"] == str(manifest)


def test_lightweight_zero_selection_fails_validation_acceptance(tmp_path) -> None:
    route_dir = tmp_path / "lightweight"
    route_dir.mkdir()
    summary = route_dir / "summary.json"
    summary.write_text(
        '{"selected_overall": {"macro_f1": 0.0, '
        '"correct_count": 0, "selected_count": 0}}',
        encoding="utf-8",
    )
    manifest = route_dir / "freeze_manifest.json"
    manifest.write_text('{"training_summary": "summary.json"}', encoding="utf-8")
    evidence = _positive_validation_metrics("lightweight", manifest)
    assert evidence["accepted"] is False


def test_lightweight_tiny_positive_output_still_fails_validation(tmp_path) -> None:
    route_dir = tmp_path / "lightweight"
    route_dir.mkdir()
    summary = route_dir / "summary.json"
    summary.write_text(
        '{"selected_overall": {"macro_f1": 0.01, '
        '"correct_count": 1, "selected_count": 1}}',
        encoding="utf-8",
    )
    manifest = route_dir / "freeze_manifest.json"
    manifest.write_text('{"training_summary": "summary.json"}', encoding="utf-8")
    evidence = _positive_validation_metrics("lightweight", manifest)
    assert evidence["accepted"] is False
    assert evidence["failure_reason"] == "tiny_validation_association_output"
    elimination = _main_gate_elimination("lightweight", evidence)
    assert elimination["status"] == "eliminated_on_main_validation_gate"
    assert elimination["reason_code"] == "tiny_validation_association_output"


def test_legacy_freeze_marker_cannot_load_for_new_test(tmp_path) -> None:
    marker = tmp_path / "all_routes_frozen.json"
    marker.write_text(
        '{"schema_version": "dual-optical-all-routes-freeze-v1", '
        f'"protocol_fingerprint": "{BenchmarkProtocol().fingerprint}"}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema"):
        _load_routes(marker)


def test_incomplete_current_freeze_marker_cannot_start_test(tmp_path) -> None:
    marker = tmp_path / "all_routes_frozen.json"
    marker.write_text(
        f'{{"schema_version": "{ALL_ROUTES_FREEZE_SCHEMA}", '
        f'"protocol_fingerprint": "{BenchmarkProtocol().fingerprint}", '
        '"all_routes_accepted": true, "active_routes": ["gnn"], '
        '"routes": {}}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="every active route"):
        validate_freeze_marker(marker)


def _valid_freeze_marker(tmp_path):
    tracker_config = SharedTrackerConfig()
    tracker = tmp_path / "shared_tracker.json"
    tracker_payload = tracker_freeze_payload(
        tracker_config,
        calibration_manifest="calibration_manifest.json",
        calibration_manifest_sha256="a" * 64,
        validation_metrics={"acceptance": {"accepted": True}},
    )
    from dual_optical_online_benchmark.contracts import write_json

    write_json(tracker, tracker_payload)
    routes = {}
    for route_name in ("epipolar_mht", "lightweight", "gnn"):
        route_dir = tmp_path / route_name
        route_dir.mkdir()
        manifest = route_dir / "freeze_manifest.json"
        evidence = route_dir / "validation_evidence.json"
        manifest.write_text('{"frozen": true}\n', encoding="utf-8")
        evidence.write_text('{"accepted": true}\n', encoding="utf-8")
        routes[route_name] = {
            "freeze_manifest": str(manifest),
            "freeze_manifest_sha256": sha256_file(manifest),
            "validation_acceptance": {
                "accepted": True,
                "evidence_path": str(evidence),
                "evidence_sha256": sha256_file(evidence),
            },
        }
    marker = tmp_path / "all_routes_frozen.json"
    write_json(
        marker,
        {
            "schema_version": ALL_ROUTES_FREEZE_SCHEMA,
            "protocol_fingerprint": BenchmarkProtocol().fingerprint,
            "all_routes_accepted": True,
            "active_routes": list(routes),
            "tracker_freeze": str(tracker),
            "tracker_freeze_sha256": sha256_file(tracker),
            "tracker_fingerprint": tracker_config.fingerprint,
            "routes": routes,
        },
    )
    return marker, tracker


def _diagnostic_s180_freeze_marker(tmp_path):
    marker, tracker = _valid_freeze_marker(tmp_path)
    from dataclasses import asdict

    from dual_optical_online_benchmark.contracts import write_json

    tracker_payload = json.loads(tracker.read_text(encoding="utf-8"))
    tracker_payload["validation_metrics"]["acceptance"] = {"accepted": False}
    tracker_payload.update(
        {
            "diagnostic_only": True,
            "formal_use_allowed": False,
            "promotion_allowed": False,
        }
    )
    write_json(tracker, tracker_payload)

    protocol = s180_protocol_for_target_count(40)
    marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    marker_payload.update(
        {
            "protocol": asdict(protocol),
            "protocol_fingerprint": protocol.fingerprint,
            "tracker_freeze_sha256": sha256_file(tracker),
            "diagnostic_only": True,
            "formal_use_allowed": False,
            "promotion_allowed": False,
            "tracker_acceptance_passed": False,
        }
    )
    write_json(marker, marker_payload)
    return marker, tracker


def test_s180_diagnostic_freeze_is_explicitly_non_promotable(tmp_path) -> None:
    marker, _ = _diagnostic_s180_freeze_marker(tmp_path)
    payload = validate_freeze_marker(marker)
    assert payload["diagnostic_only"] is True
    assert payload["formal_use_allowed"] is False
    assert payload["promotion_allowed"] is False
    assert payload["tracker_acceptance_passed"] is False


@pytest.mark.parametrize(
    "field",
    ("formal_use_allowed", "promotion_allowed", "tracker_acceptance_passed"),
)
def test_s180_diagnostic_freeze_rejects_capability_escalation(
    tmp_path, field
) -> None:
    marker, _ = _diagnostic_s180_freeze_marker(tmp_path)
    from dual_optical_online_benchmark.contracts import write_json

    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload[field] = True
    write_json(marker, payload)
    with pytest.raises(ValueError, match="diagnostic freeze marker"):
        validate_freeze_marker(marker)


def test_tracker_freeze_hash_tamper_blocks_test_start(tmp_path) -> None:
    marker, tracker = _valid_freeze_marker(tmp_path)
    validate_freeze_marker(marker)
    tracker.write_text('{"tampered": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_freeze_marker(marker)


def test_v4_freeze_marker_remains_read_only_compatible(tmp_path) -> None:
    marker, _ = _valid_freeze_marker(tmp_path)
    import json

    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["schema_version"] = "dual-optical-all-routes-freeze-v4"
    from dual_optical_online_benchmark.contracts import write_json

    write_json(marker, payload)
    assert validate_freeze_marker(marker)["schema_version"].endswith("v4")


def test_foreign_tracker_fingerprint_blocks_test_start(tmp_path) -> None:
    marker, _ = _valid_freeze_marker(tmp_path)
    payload = __import__("json").loads(marker.read_text(encoding="utf-8"))
    payload["tracker_fingerprint"] = "foreign-tracker"
    from dual_optical_online_benchmark.contracts import write_json

    write_json(marker, payload)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_freeze_marker(marker)
