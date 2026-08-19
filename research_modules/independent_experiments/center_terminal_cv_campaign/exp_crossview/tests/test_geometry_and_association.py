from __future__ import annotations

from dataclasses import replace

import pytest

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.association import (
    _UnionFind,
    _attach_short_tracks_by_cluster_consensus,
    _cluster_confirmed_links,
    associate_crossview_tracks,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.config import (
    CrossViewConfig,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.contracts import (
    CandidateEdge,
    PairMatch,
    assert_online_anonymous,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.evaluation import (
    score_with_offline_truth,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.fixture import (
    build_fixture,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_crossview.geometry import (
    closest_ray_intersection,
    pixel_to_world_ray,
)


def _pair_match(left: str, right: str, cost: float) -> PairMatch:
    camera_a, track_a = left.split("::", maxsplit=1)
    camera_b, track_b = right.split("::", maxsplit=1)
    return PairMatch(
        camera_a_id=camera_a,
        track_a_id=track_a,
        camera_b_id=camera_b,
        track_b_id=track_b,
        timestamp=1.0,
        cost=cost,
        decision_state="confirmed",
        confirmation_count=2,
        backend="geometry",
    )


def _short_candidate(
    left: str,
    right: str,
    *,
    samples: int = 2,
    cost: float = 0.04,
) -> CandidateEdge:
    camera_a, track_a = left.split("::", maxsplit=1)
    camera_b, track_b = right.split("::", maxsplit=1)
    return CandidateEdge(
        camera_a_id=camera_a,
        track_a_id=track_a,
        camera_b_id=camera_b,
        track_b_id=track_b,
        reference_timestamp=0.2,
        aligned_sample_count=samples,
        latest_time_offset_s=0.0,
        median_ray_separation_m=0.02,
        median_reprojection_error_px=0.05,
        intersection_angle_deg=2.0,
        motion_fit_error_m=0.0,
        motion_turn_deg=0.0,
        bbox_log_scale_difference=0.05,
        camera_confidence=0.95,
        geometry_cost=cost,
        gate_passed=False,
        reject_reasons=("insufficient_geometry_samples",),
    )


def test_pinhole_backprojection_and_ray_intersection() -> None:
    bundle = build_fixture("two_by_two_crossing", frame_count=4)
    first = bundle.records[0]
    calibration = bundle.calibrations[first.camera_id]
    ray = pixel_to_world_ray(
        first.center_px, calibration, first.camera_yaw_pitch_roll_deg
    )
    assert ray == pytest.approx(first.ray_direction_ned, abs=1.0e-9)

    same_target = bundle.truth.track_to_target[
        f"{first.camera_id}::{first.local_track_id}"
    ]
    other = next(
        record
        for record in bundle.records
        if record.camera_id != first.camera_id
        and record.measurement_timestamp == first.measurement_timestamp
        and bundle.truth.track_to_target[f"{record.camera_id}::{record.local_track_id}"]
        == same_target
    )
    intersection = closest_ray_intersection(
        first.ray_origin_ned_m,
        first.ray_direction_ned,
        other.ray_origin_ned_m,
        other.ray_direction_ned,
    )
    assert intersection.depth_a_m > 0.0
    assert intersection.depth_b_m > 0.0
    assert intersection.separation_m < 1.0


def test_two_camera_two_crossing_targets_do_not_swap_identity() -> None:
    bundle = build_fixture("two_by_two_crossing")
    result = score_with_offline_truth(
        associate_crossview_tracks(bundle.records, bundle.calibrations), bundle.truth
    )
    assert result.metrics.association_precision == 1.0
    assert result.metrics.association_recall == 1.0
    assert result.metrics.id_switch_count == 0
    assert sorted(len(cluster.member_track_keys) for cluster in result.clusters) == [2, 2]


def test_no_common_target_stays_unresolved_without_forced_merge() -> None:
    bundle = build_fixture("no_common_targets")
    result = score_with_offline_truth(
        associate_crossview_tracks(bundle.records, bundle.calibrations), bundle.truth
    )
    assert result.matches == ()
    assert result.clusters == ()
    assert result.metrics.unresolved_track_count == 4
    assert result.metrics.false_positive_relations == 0


def test_partial_overlap_handoff_and_camera_uniqueness() -> None:
    bundle = build_fixture("partial_3cam_5target")
    result = score_with_offline_truth(
        associate_crossview_tracks(bundle.records, bundle.calibrations), bundle.truth
    )
    assert result.metrics.association_precision == 1.0
    assert result.metrics.association_recall >= 0.85
    assert result.metrics.camera_uniqueness_violation_count == 0
    for cluster in result.clusters:
        assert len(cluster.camera_ids) == len(set(cluster.camera_ids))
    handoff_tracks = {
        key
        for key, target_id in bundle.truth.track_to_target.items()
        if target_id == "OFFLINE-T005"
    }
    assert any(
        len(handoff_tracks & set(cluster.member_track_keys)) >= 2
        for cluster in result.clusters
    )


def test_single_edge_cannot_bridge_two_mature_clusters() -> None:
    tracks = ("C1::L1", "C2::L1", "C3::L1", "C4::L1")
    links = (
        _pair_match(tracks[0], tracks[1], 0.02),
        _pair_match(tracks[2], tracks[3], 0.03),
        _pair_match(tracks[0], tracks[2], 0.20),
    )
    union_find, accepted, rejected = _cluster_confirmed_links(
        tracks,
        links,
        CrossViewConfig(),
    )
    assert union_find.find(tracks[0]) == union_find.find(tracks[1])
    assert union_find.find(tracks[2]) == union_find.find(tracks[3])
    assert union_find.find(tracks[0]) != union_find.find(tracks[2])
    assert len(accepted) == 2
    assert rejected == (links[2],)


def test_short_track_requires_independent_mature_cluster_support() -> None:
    mature = ("C1::L1", "C2::L1", "C3::L1")
    short = "C4::L9"
    union_find = _UnionFind((*mature, short))
    assert union_find.union_if_camera_unique(mature[0], mature[1])
    assert union_find.union_if_camera_unique(mature[0], mature[2])
    matches = _attach_short_tracks_by_cluster_consensus(
        union_find,
        {**{key: 5 for key in mature}, short: 2},
        (
            _short_candidate(mature[0], short, samples=2, cost=0.04),
            _short_candidate(mature[1], short, samples=1, cost=0.03),
            _short_candidate(mature[2], short, samples=2, cost=0.05),
        ),
        CrossViewConfig(),
        backend="geometry",
    )
    assert len(matches) == 3
    assert union_find.find(short) == union_find.find(mature[0])
    assert all(match.decision_state == "cluster_confirmed" for match in matches)


def test_short_track_single_support_or_ambiguous_clusters_stays_unresolved() -> None:
    first = ("C1::L1", "C2::L1")
    second = ("C3::L1", "C4::L1")
    short = "C5::L9"
    tracks = (*first, *second, short)
    union_find = _UnionFind(tracks)
    assert union_find.union_if_camera_unique(*first)
    assert union_find.union_if_camera_unique(*second)
    ambiguous_edges = (
        _short_candidate(first[0], short, cost=0.04),
        _short_candidate(first[1], short, cost=0.06),
        _short_candidate(second[0], short, cost=0.06),
        _short_candidate(second[1], short, cost=0.08),
    )
    matches = _attach_short_tracks_by_cluster_consensus(
        union_find,
        {**{key: 5 for key in (*first, *second)}, short: 2},
        ambiguous_edges,
        CrossViewConfig(),
        backend="geometry",
    )
    assert matches == ()
    assert union_find.component_members(short) == {short}

    single_support = _UnionFind((*first, short))
    assert single_support.union_if_camera_unique(*first)
    matches = _attach_short_tracks_by_cluster_consensus(
        single_support,
        {first[0]: 5, first[1]: 5, short: 2},
        (_short_candidate(first[0], short, samples=2),),
        CrossViewConfig(),
        backend="geometry",
    )
    assert matches == ()
    assert single_support.component_members(short) == {short}


def test_short_track_cost_gate_uses_most_informative_relation_snapshot() -> None:
    mature = ("C1::L1", "C2::L1")
    short = "C3::L9"
    union_find = _UnionFind((*mature, short))
    assert union_find.union_if_camera_unique(*mature)
    matches = _attach_short_tracks_by_cluster_consensus(
        union_find,
        {mature[0]: 5, mature[1]: 5, short: 2},
        (
            _short_candidate(mature[0], short, samples=1, cost=0.01),
            _short_candidate(mature[0], short, samples=2, cost=0.20),
            _short_candidate(mature[1], short, samples=2, cost=0.04),
        ),
        CrossViewConfig(),
        backend="geometry",
    )
    assert matches == ()
    assert union_find.component_members(short) == {short}


def test_ten_pixel_threshold_and_continuous_confirmation() -> None:
    bundle = build_fixture("two_by_two_crossing")
    target = next(iter(bundle.truth.track_to_target.values()))
    selected = [
        record
        for record in bundle.records
        if bundle.truth.track_to_target[f"{record.camera_id}::{record.local_track_id}"]
        == target
    ]

    def with_extent(record, extent: float):
        u, v = record.center_px
        return replace(
            record,
            bbox_xyxy=(u - extent / 2.0, v - extent / 2.0, u + extent / 2.0, v + extent / 2.0),
            recognition_extent_px=extent,
            recognized=True,
        )

    below = [with_extent(record, 9.99) for record in selected]
    result_below = associate_crossview_tracks(below, bundle.calibrations)
    assert result_below.metrics.recognized_track_count == 0
    at_threshold = [with_extent(record, 10.0) for record in selected]
    result_at_threshold = associate_crossview_tracks(at_threshold, bundle.calibrations)
    assert result_at_threshold.metrics.recognized_track_count == 2

    # Original geometry reaches the three-sample gate at frame 3, then needs a
    # second agreeing frame before publication.
    timestamps = sorted({record.measurement_timestamp for record in selected})
    first_three = [record for record in selected if record.measurement_timestamp in timestamps[:3]]
    first_four = [record for record in selected if record.measurement_timestamp in timestamps[:4]]
    assert associate_crossview_tracks(first_three, bundle.calibrations).matches == ()
    assert len(associate_crossview_tracks(first_four, bundle.calibrations).matches) == 1


def test_online_truth_marker_is_rejected() -> None:
    bundle = build_fixture("two_by_two_crossing")
    poisoned = replace(bundle.records[0], metadata={"truth_id": "T001"})
    with pytest.raises(ValueError, match="identity-bearing"):
        associate_crossview_tracks((poisoned,), bundle.calibrations)
    assert_online_anonymous(bundle.records[0].to_online_dict())


@pytest.mark.parametrize("target_count", (7, 20))
def test_n_scale_has_no_array_size_or_camera_uniqueness_assumption(target_count: int) -> None:
    bundle = build_fixture("dense_multicamera", target_count=target_count, frame_count=5)
    result = associate_crossview_tracks(bundle.records, bundle.calibrations)
    assert result.metrics.recognized_track_count == len(bundle.truth.track_to_target)
    assert result.metrics.camera_uniqueness_violation_count == 0
    assert all(len(cluster.camera_ids) == len(set(cluster.camera_ids)) for cluster in result.clusters)
    view_counts = {}
    for target_id in bundle.truth.track_to_target.values():
        view_counts[target_id] = view_counts.get(target_id, 0) + 1
    assert set(view_counts.values()) <= {2, 3}


def test_audit_candidate_retention_does_not_change_association_decisions() -> None:
    bundle = build_fixture("partial_3cam_5target")
    detailed = associate_crossview_tracks(
        bundle.records,
        bundle.calibrations,
        output_mode="detailed",
    )
    audit = associate_crossview_tracks(
        bundle.records,
        bundle.calibrations,
        output_mode="audit",
        candidate_sample_limit=2,
    )
    assert audit.matches == detailed.matches
    assert audit.clusters == detailed.clusters
    assert audit.pending_relations == detailed.pending_relations
    assert audit.unresolved_track_keys == detailed.unresolved_track_keys
    assert audit.metrics == detailed.metrics
    assert len(audit.candidates) <= 2
    assert audit.audit.omitted_candidate_count > 0
