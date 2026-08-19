from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import json
import math
from pathlib import Path

import pytest

import dual_optical_40target.online_benchmark as benchmark_module
from dual_optical_40target.core import (
    AssociationConfig,
    CrossCameraCandidate,
    CrossCameraMatch,
    EpipolarEvidence,
    GlobalAssignmentHypothesis,
)
from dual_optical_40target.online import FrozenAssociationParameters
from dual_optical_40target.online_benchmark import (
    ROUTE_DEADLINE_MS,
    CandidatePathAblationRunner,
    FrozenEnhancedGeometryRoute,
    _OfflineCalibrationLabels,
    _WhitelistTemporalAssociator,
    _candidate_score,
    _dominant_truth,
    _geometry_candidate_pairs,
    _load_label_entry,
    _to_internal_snapshot,
    evaluate_20_target_negative_benefit,
)
from dual_optical_online_benchmark.contracts import (
    AssociationPublication,
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    candidate_graph_fingerprint,
)


def _snapshot(*, source_kind: str = "anonymous") -> RevolutionSnapshot:
    sample = SnapshotTrackSample(
        sweep_index=0,
        timestamp=1.0,
        direction_ned=(1.0, 0.0, 0.0),
        detection_count=1,
        bbox_area_px2=4.0,
        confidence=0.9,
    )
    return RevolutionSnapshot(
        protocol_fingerprint="protocol-test",
        seed=20261025,
        split="validation",
        corruption_level="light",
        revolution_index=1,
        cutoff_timestamp=2.0,
        camera_ids=("Optical_A", "Optical_B"),
        camera_positions_ned={
            "Optical_A": (0.0, -1000.0, -100.0),
            "Optical_B": (0.0, 1000.0, -100.0),
        },
        focal_length_px=25_000.0,
        tracks={
            "Optical_A": (
                SnapshotTrack("A-T001", "Optical_A", (sample,), source_kind),
            ),
            "Optical_B": (
                SnapshotTrack("B-T001", "Optical_B", (sample,), source_kind),
            ),
        },
    )


def _route(*, target_count: int | None = None) -> FrozenEnhancedGeometryRoute:
    parameters = FrozenAssociationParameters.freeze(AssociationConfig())
    manifest = {
        "selected_parameters": parameters.to_dict(),
        "model_fingerprint": "model-test",
        "protocol_fingerprint": "protocol-test",
        "shared_tracker_fingerprint": "legacy-unfrozen-tracker",
    }
    if target_count is not None:
        manifest["target_count"] = target_count
    return FrozenEnhancedGeometryRoute(manifest)


def _whitelisted_snapshot(
    revolution_index: int,
    pairs: tuple[tuple[str, str], ...],
) -> object:
    base = _snapshot()
    sample_a = replace(
        base.tracks["Optical_A"][0].samples[0],
        sweep_index=revolution_index - 1,
        timestamp=float(revolution_index * 2 - 1),
    )
    sample_b = replace(sample_a, direction_ned=(0.8, -0.6, 0.0))
    sample_a_2 = replace(
        sample_a, direction_ned=(0.9797958971132712, 0.2, 0.0)
    )
    sample_b_2 = replace(
        sample_b, direction_ned=(0.9110433579144299, -0.4, 0.1)
    )
    tracks = {
        "Optical_A": (
            SnapshotTrack(
                "A-T001",
                "Optical_A",
                tuple(replace(sample_a, sweep_index=index, timestamp=float(index + 1)) for index in range(revolution_index)),
                "anonymous",
            ),
            SnapshotTrack(
                "A-T002",
                "Optical_A",
                tuple(
                    replace(sample_a_2, sweep_index=index, timestamp=float(index + 1))
                    for index in range(revolution_index)
                ),
                "anonymous",
            ),
        ),
        "Optical_B": (
            SnapshotTrack(
                "B-T001",
                "Optical_B",
                tuple(replace(sample_b, sweep_index=index, timestamp=float(index + 1)) for index in range(revolution_index)),
                "anonymous",
            ),
            SnapshotTrack(
                "B-T002",
                "Optical_B",
                tuple(
                    replace(sample_b_2, sweep_index=index, timestamp=float(index + 1))
                    for index in range(revolution_index)
                ),
                "anonymous",
            ),
        ),
    }
    snapshot = replace(
        base,
        revolution_index=revolution_index,
        cutoff_timestamp=float(revolution_index * 2),
        tracks=tracks,
        geometry_candidate_pairs=pairs,
        candidate_graph_fingerprint=candidate_graph_fingerprint(pairs, {}),
        candidate_graph_summary={},
    )
    return snapshot


def _passing_evidence(track_a_id: str, track_b_id: str) -> EpipolarEvidence:
    return EpipolarEvidence(
        track_a_id=track_a_id,
        track_b_id=track_b_id,
        gate_passed=True,
        rejection_reason="",
        aligned_sample_count=2,
        timestamps_s=(1.0, 2.0),
        residuals_mrad=(0.1, 0.1),
        residual_median_mrad=0.1,
        residual_p90_mrad=0.1,
        residual_mad_mrad=0.0,
        residual_slope_mrad_per_s=0.0,
        intersection_angle_median_deg=20.0,
        normalized_residuals_chi2=(0.1, 0.1),
        normalized_residual_median_chi2=0.1,
        normalized_residual_p90_chi2=0.1,
    )


def _passing_candidate(track_a_id: str, track_b_id: str) -> CrossCameraCandidate:
    return CrossCameraCandidate(
        track_a_id=track_a_id,
        track_b_id=track_b_id,
        valid=True,
        rejection_reason="",
        cost=0.1,
        reprojection_rms_px=1.0,
        reprojection_max_px=1.0,
        ray_residual_rms_m=1.0,
        fitted_speed_mps=50.0,
        median_nearest_time_delta_s=0.0,
        condition_number=10.0,
        observation_count=4,
        inlier_count=4,
        outlier_count=0,
        reference_timestamp=2.0,
        position_ned=(2000.0, 0.0, -100.0),
        velocity_ned=(-50.0, 0.0, 0.0),
    )


@pytest.mark.parametrize(
    ("counts", "expected"),
    (
        ({"TRUTH-001": 5, "FA-001": 1}, "TRUTH-001"),
        ({"TRUTH-001": 5, "TRUTH-002": 5}, None),
        ({"FA-001": 6, "TRUTH-001": 5}, None),
        ({"TRUTH-001": 0}, None),
        ({}, None),
    ),
)
def test_dominant_truth_uses_unique_non_false_alarm_maximum(
    counts: dict[str, int], expected: str | None
) -> None:
    assert _dominant_truth(counts) == expected


def test_final_offline_label_schema_is_loaded_without_candidate_lists(
    tmp_path: Path,
) -> None:
    label_path = tmp_path / "labels.json"
    label_path.write_text(
        json.dumps(
            {
                "track_truth_counts": {
                    "A-T001": {"TRUTH-001": 5, "FA-001": 1},
                    "A-T002": {"TRUTH-001": 3, "TRUTH-002": 3},
                    "A-T003": {"FA-002": 4, "TRUTH-003": 2},
                },
                "truth_heading_groups": {
                    "TRUTH-001": "heading_0_deg",
                    "TRUTH-002": "heading_minus_30_deg",
                },
            }
        ),
        encoding="utf-8",
    )

    labels = _load_label_entry(tmp_path, {"label_path": "labels.json"})

    assert labels.dominant_truth_by_track == {
        "A-T001": "TRUTH-001",
        "A-T002": None,
        "A-T003": None,
    }
    assert labels.truth_heading_groups["TRUTH-001"] == "heading_0_deg"


def test_online_snapshot_requires_anonymous_source_kind() -> None:
    _to_internal_snapshot(_snapshot())

    with pytest.raises(ValueError, match="source_kind must be anonymous"):
        _to_internal_snapshot(_snapshot(source_kind="measured"))


def test_candidate_score_accepts_shared_cache_by_group() -> None:
    snapshot = _snapshot()
    labels = _OfflineCalibrationLabels(
        track_truth_counts={
            "A-T001": {"TRUTH-001": 1},
            "B-T001": {"TRUTH-001": 1},
        },
        dominant_truth_by_track={
            "A-T001": "TRUTH-001",
            "B-T001": "TRUTH-001",
        },
        truth_heading_groups={"TRUTH-001": "heading_0_deg"},
    )
    shared_cache: dict[tuple[int, str], dict[tuple[str, str], object]] = {}

    metrics = _candidate_score(
        FrozenAssociationParameters.freeze(AssociationConfig()),
        [(snapshot, labels)],
        shared_cache_by_group=shared_cache,
    )

    assert metrics["false_association_count"] == 0
    assert (snapshot.seed, snapshot.corruption_level) in shared_cache


def test_shared_v2_snapshot_converts_rates_covariance_and_track_state() -> None:
    sample = SnapshotTrackSample(
        sweep_index=1,
        timestamp=1.0,
        direction_ned=(1.0, 0.0, 0.0),
        detection_count=2,
        bbox_area_px2=9.0,
        confidence=0.8,
        measurement_covariance_deg2=(0.04, 0.0, 0.0, 0.09),
        state_vector=(0.0, 0.0, 2.0, -3.0),
        state_covariance=tuple(
            4.0 if index % 5 == 0 else 0.0 for index in range(16)
        ),
    )
    base = _snapshot()
    tracks = {
        camera_id: (
            SnapshotTrack(
                f"{camera_id}-T1",
                camera_id,
                (sample,),
                "anonymous",
                track_state="confirmed",
                recent_sweep_hits=(True, False, True),
            ),
        )
        for camera_id in base.camera_ids
    }
    snapshot = replace(base, tracks=tracks, tracker_fingerprint="tracker-v2")

    internal = _to_internal_snapshot(snapshot)
    converted_track = internal.tracks_a[0].to_track()
    converted = converted_track.samples[0]
    scale = (math.pi / 180.0) ** 2
    assert converted.covariance_source == "snapshot_v2"
    assert math.isclose(converted.azimuth_rate_rad_s, math.radians(2.0))
    assert math.isclose(converted.elevation_rate_rad_s, math.radians(-3.0))
    assert math.isclose(converted.measurement_covariance_rad2[0][0], 0.04 * scale)
    assert math.isclose(converted.kinematic_state_covariance[3][3], 4.0 * scale)
    assert converted_track.hit_history == (True, False, True)
    assert converted_track.track_state == "confirmed"


def test_legacy_snapshot_like_objects_receive_conservative_defaults() -> None:
    class LegacySample:
        sweep_index = 0
        timestamp = 1.0
        direction_ned = (1.0, 0.0, 0.0)
        detection_count = 1
        bbox_area_px2 = 4.0

    class LegacyTrack:
        track_id = "A-legacy"
        camera_id = "Optical_A"
        source_kind = "anonymous"
        samples = (LegacySample(),)

    base = _snapshot()
    legacy_a = LegacyTrack()
    legacy_b = LegacyTrack()
    legacy_b.track_id = "B-legacy"
    legacy_b.camera_id = "Optical_B"
    snapshot = replace(
        base,
        tracks={"Optical_A": (legacy_a,), "Optical_B": (legacy_b,)},
        tracker_fingerprint="legacy-unfrozen-tracker",
    )

    internal = _to_internal_snapshot(snapshot)
    converted = internal.tracks_a[0].to_track().samples[0]
    assert converted.covariance_source == "legacy_conservative_default"
    assert converted.azimuth_rate_rad_s == 0.0
    assert converted.elevation_rate_rad_s == 0.0
    assert converted.angular_covariance_rad2[0, 0] > 0.0


def test_validation_grid_contains_exact_four_chi_square_confidences() -> None:
    from dual_optical_40target.online import association_parameter_grid

    confidences = {
        item.config.covariance_gate_confidence
        for item in association_parameter_grid()
    }
    assert confidences == {0.95, 0.975, 0.99, 0.995}


def test_geometry_candidate_whitelist_is_optional_and_strict() -> None:
    current = _snapshot()
    assert _geometry_candidate_pairs(current) == (None, "")

    legacy = SimpleNamespace(
        **{
            key: value
            for key, value in current.__dict__.items()
            if key
            not in {
                "geometry_candidate_pairs",
                "candidate_graph_fingerprint",
                "candidate_graph_summary",
            }
        }
    )
    assert _geometry_candidate_pairs(legacy) == (None, "")

    explicit_empty = replace(
        current,
        candidate_graph_fingerprint=candidate_graph_fingerprint((), {}),
    )
    pairs, fingerprint = _geometry_candidate_pairs(explicit_empty)
    assert pairs == ()
    assert fingerprint == candidate_graph_fingerprint((), {})

    pairs = (("A-T001", "B-T001"),)
    snapshot = _whitelisted_snapshot(2, pairs)
    normalized, fingerprint = _geometry_candidate_pairs(snapshot)

    assert normalized == pairs
    assert fingerprint == snapshot.candidate_graph_fingerprint

    invalid = SimpleNamespace(
        **{
            **snapshot.__dict__,
            "geometry_candidate_pairs": (("A-T001", "B-UNKNOWN"),),
        }
    )
    with pytest.raises(ValueError, match="unknown or reversed"):
        _geometry_candidate_pairs(invalid)


@pytest.mark.parametrize("target_count", (20, 40, 60, 100))
def test_route_accepts_each_supported_snapshot_target_count(
    target_count: int,
) -> None:
    original = replace(_snapshot(), target_count=target_count)
    payload = original.online_payload()
    restored = RevolutionSnapshot.from_online_payload(payload)
    publication = _route(target_count=target_count).publish(restored)

    assert payload["target_count"] == target_count
    assert restored.target_count == target_count
    assert publication.availability == "available"
    assert publication.rejection_reasons["diagnostic.target_count_missing"] == 0
    assert publication.rejection_reasons[
        f"diagnostic.target_count.{target_count}"
    ] == 1


def test_route_rejects_snapshot_target_count_that_differs_from_freeze() -> None:
    route = _route(target_count=20)

    with pytest.raises(
        ValueError, match="snapshot target_count does not match frozen route"
    ):
        route.publish(replace(_snapshot(), target_count=40))


def test_missing_legacy_target_count_stays_unknown_instead_of_becoming_100() -> None:
    old_payload = _snapshot().online_payload()
    old_payload.pop("target_count")
    old_snapshot = RevolutionSnapshot.from_online_payload(old_payload)

    publication_from_new_freeze = _route(target_count=20).publish(old_snapshot)
    publication_from_old_freeze = _route().publish(
        replace(_snapshot(), target_count=60)
    )

    assert old_snapshot.target_count is None
    assert publication_from_new_freeze.availability == "available"
    assert publication_from_new_freeze.rejection_reasons[
        "diagnostic.target_count_missing"
    ] == 1
    assert "diagnostic.target_count.100" not in (
        publication_from_new_freeze.rejection_reasons
    )
    assert publication_from_old_freeze.availability == "available"
    assert publication_from_old_freeze.rejection_reasons[
        "diagnostic.target_count.60"
    ] == 1


def test_whitelist_path_evaluates_only_listed_pairs_and_confirms_two_of_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluated: list[tuple[str, str]] = []

    def fake_evidence(track_a, track_b, *, config):
        del config
        evaluated.append((track_a.track_id, track_b.track_id))
        return _passing_evidence(track_a.track_id, track_b.track_id)

    def fake_fit(track_a, track_b, **kwargs):
        del kwargs
        return _passing_candidate(track_a.track_id, track_b.track_id)

    def fake_assign(tracks_a, tracks_b, candidates, **kwargs):
        del tracks_a, tracks_b, kwargs
        matches = tuple(
            (candidate.track_a_id, candidate.track_b_id)
            for candidate in candidates
        )
        return (
            GlobalAssignmentHypothesis(
                hypothesis_id="HYP-001",
                rank=1,
                total_cost=0.1,
                normalized_support=1.0,
                matches=matches,
                unmatched_a_track_ids=(),
                unmatched_b_track_ids=(),
            ),
        )

    monkeypatch.setattr(benchmark_module, "build_epipolar_evidence", fake_evidence)
    monkeypatch.setattr(benchmark_module, "_fit_cross_camera_candidate", fake_fit)
    monkeypatch.setattr(benchmark_module, "k_best_global_assignments", fake_assign)

    parameters = FrozenAssociationParameters.freeze(AssociationConfig())
    associator = _WhitelistTemporalAssociator(parameters)
    pair = (("A-T001", "B-T001"),)

    second = associator.process_snapshot(
        _to_internal_snapshot(_whitelisted_snapshot(2, pair)), pair
    )
    third = associator.process_snapshot(
        _to_internal_snapshot(_whitelisted_snapshot(3, pair)), pair
    )

    assert evaluated == [pair[0], pair[0]]
    assert second.full_pair_count == 4
    assert second.whitelist_pair_count == 1
    assert second.fit_evaluation_count == 1
    assert second.state_by_pair[pair[0]] == "tentative"
    assert third.state_by_pair[pair[0]] == "confirmed"


def test_publish_uses_whitelist_diagnostics_and_fails_closed_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair = ("A-T001", "B-T001")
    calls = 0

    def fake_process(self, snapshot, candidate_pairs):
        nonlocal calls
        del snapshot
        calls += 1
        assert candidate_pairs == (pair,)
        inherited = bool(self.selection_history)
        self.selection_history[pair] = [True]
        match = CrossCameraMatch(
            match_id="ONLINE-PAIR-001",
            track_a_id=pair[0],
            track_b_id=pair[1],
            cost=0.1,
            reference_timestamp=2.0,
            position_ned=(2000.0, 0.0, -100.0),
            velocity_ned=(-50.0, 0.0, 0.0),
        )
        elapsed = ROUTE_DEADLINE_MS + 1.0 if calls == 1 else 1.0
        return SimpleNamespace(
            selected_matches=(match,),
            state_by_pair={pair: "confirmed" if inherited else "tentative"},
            epipolar_evidence=(_passing_evidence(*pair),),
            full_pair_count=4,
            whitelist_pair_count=1,
            mature_whitelist_pair_count=1,
            coarse_gate_pass_count=1,
            fit_evaluation_count=1,
            screening_elapsed_ms=0.1,
            fitting_elapsed_ms=0.2,
            assignment_elapsed_ms=0.3,
            state_update_elapsed_ms=0.1,
            processing_elapsed_ms=elapsed,
        )

    monkeypatch.setattr(_WhitelistTemporalAssociator, "process_snapshot", fake_process)
    route = _route()

    timed_out = route.publish(_whitelisted_snapshot(2, (pair,)))
    recovered = route.publish(_whitelisted_snapshot(3, (pair,)))

    assert timed_out.availability == "timeout"
    assert timed_out.matches == ()
    assert timed_out.rejection_reasons["deadline_exceeded"] == 1
    assert route._whitelist_associators
    assert recovered.availability == "available"
    assert recovered.matches[0].decision_state == "tentative"
    assert recovered.rejection_reasons[
        "diagnostic.candidate_source.shared_whitelist"
    ] == 1
    assert recovered.rejection_reasons["diagnostic.whitelist_pair_count"] == 1
    assert recovered.rejection_reasons["diagnostic.assignment_elapsed_us"] == 300


def test_candidate_path_ablation_uses_same_input_and_alternates_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, str]] = []

    def fake_publish(self, snapshot, *, candidate_mode):
        del self
        calls.append((snapshot.revolution_index, candidate_mode))
        return AssociationPublication(
            route_name="epipolar_mht",
            route_version="test",
            model_fingerprint="model-test",
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            input_fingerprint=benchmark_module.snapshot_fingerprint(snapshot),
            availability="available",
            matches=(),
            candidate_graph_fingerprint=snapshot.candidate_graph_fingerprint,
            end_to_end_ms=1.0,
        )

    monkeypatch.setattr(
        FrozenEnhancedGeometryRoute,
        "_publish_with_candidate_mode",
        fake_publish,
    )
    runner = CandidatePathAblationRunner(_route().freeze_manifest)

    even = runner.publish(
        _whitelisted_snapshot(2, (("A-T001", "B-T001"),))
    )
    odd = runner.publish(
        _whitelisted_snapshot(3, (("A-T001", "B-T001"),))
    )

    assert even.execution_order == ("legacy_full_pair", "shared_whitelist")
    assert odd.execution_order == ("shared_whitelist", "legacy_full_pair")
    assert (
        even.whitelist_publication.input_fingerprint
        == even.legacy_full_pair_publication.input_fingerprint
        == even.input_fingerprint
    )
    assert calls == [
        (2, "legacy_full_pair"),
        (2, "shared_whitelist"),
        (3, "shared_whitelist"),
        (3, "legacy_full_pair"),
    ]


def _negative_benefit_rows(
    *,
    whitelist_recall: float,
    legacy_recall: float,
    whitelist_correct: int = 8,
    whitelist_false: int = 1,
    whitelist_latency_ms: float = 400.0,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for seed, level in ((20282101, "medium"), (20282102, "heavy")):
        fingerprint = f"{seed:064x}"[-64:]
        for mode, recall, correct, false, latency in (
            (
                "shared_whitelist",
                whitelist_recall,
                whitelist_correct,
                whitelist_false,
                whitelist_latency_ms,
            ),
            ("legacy_full_pair", legacy_recall, 7, 1, 600.0),
        ):
            rows.append(
                {
                    "split": "validation",
                    "target_count": 20,
                    "seed": seed,
                    "corruption_level": level,
                    "revolution_index": 4,
                    "candidate_mode": mode,
                    "input_fingerprint": fingerprint,
                    "on_time_recall": recall,
                    "match_count": correct + false,
                    "correct_match_count": correct,
                    "false_association_count": false,
                    "deadline_met": latency <= ROUTE_DEADLINE_MS,
                    "end_to_end_ms": latency,
                }
            )
    return rows


def test_20_target_negative_benefit_retains_positive_noise_result() -> None:
    result = evaluate_20_target_negative_benefit(
        _negative_benefit_rows(
            whitelist_recall=0.60,
            legacy_recall=0.50,
        )
    )

    assert result["retain_for_40_target"] is True
    assert result["eliminated"] is False
    assert result["elimination_reasons"] == []
    assert result["metrics"]["mean_on_time_recall_delta"] > 0.09


def test_20_target_negative_benefit_eliminates_noisy_regression() -> None:
    result = evaluate_20_target_negative_benefit(
        _negative_benefit_rows(
            whitelist_recall=0.35,
            legacy_recall=0.55,
            whitelist_correct=2,
            whitelist_false=3,
            whitelist_latency_ms=1200.0,
        )
    )

    assert result["retain_for_40_target"] is False
    assert result["eliminated"] is True
    assert "medium_heavy_on_time_recall_drop_ge_2pp" in result[
        "elimination_reasons"
    ]
    assert "published_conditional_precision_below_0_70" in result[
        "elimination_reasons"
    ]
    assert "p95_latency_exceeds_1000ms" in result["elimination_reasons"]


def test_20_target_negative_benefit_rejects_reserved_test_rows() -> None:
    rows = _negative_benefit_rows(
        whitelist_recall=0.60,
        legacy_recall=0.50,
    )
    rows[0]["split"] = "test"

    with pytest.raises(ValueError, match="reserved test"):
        evaluate_20_target_negative_benefit(rows)
