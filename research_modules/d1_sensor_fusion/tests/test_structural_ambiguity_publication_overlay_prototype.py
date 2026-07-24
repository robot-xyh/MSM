from __future__ import annotations

from dataclasses import FrozenInstanceError
from dataclasses import replace
import hashlib
from itertools import permutations
import json
from types import MappingProxyType

import numpy as np
import pytest

import d1_sensor_fusion.structural_ambiguity_publication_overlay_prototype as prototype
from d1_sensor_fusion import (
    ExperimentalCentroidEvidenceDisposition,
    ExperimentalCentroidPublicationOverlayConfig,
    ExperimentalCentroidPublicationState,
    GlobalTrack,
    StructuralAmbiguityCandidateEdge,
    StructuralAmbiguityEvidence,
    StructuralAmbiguityMemberState,
    StructuralAmbiguityObservationEvidence,
    TrackLevel,
    assemble_experimental_centroid_shadow_tracks,
    evaluate_experimental_centroid_publication_overlays,
    prepare_experimental_centroid_canonical_publication,
    run_experimental_centroid_publication_overlay_atomically,
    structural_ambiguity_member_track_token,
    structural_ambiguity_source_key,
)


PUBLISHER = "D1_A1_TEST"
EPOCH = "episode-a1"
CONFIG = ExperimentalCentroidPublicationOverlayConfig(
    centroid_gate_chi2=1.0e9,
    shape_gate_m2=1.0e9,
    max_translation_m=100.0,
)
BASELINE_DECISION_SHA256_BY_MEMBER_COUNT = {
    2: "e71a934f75cce47511d08542f79e471ed1bb80acab36c9403cd9501e2104fc11",
    3: "d8b05fb722f2e42ba88c04abbd5544273d70d58e3d4c3b66478c16b0c819718c",
    5: "9f5d6e9a0a3f02c16a91e00cdda73b87ad0fe331130c943af73f900e325c7609",
}


def _token(prefix: str, value: str) -> str:
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _case(
    count: int,
    *,
    offset: int = 0,
    component_tag: str = "a",
    generation: int = 1,
    translation: np.ndarray | None = None,
) -> tuple[tuple[GlobalTrack, ...], StructuralAmbiguityEvidence]:
    translation = (
        np.array([4.0, -2.0, 1.0])
        if translation is None
        else np.asarray(translation, dtype=float)
    )
    measurement_timestamp = 10.0
    arrival_timestamp = 10.1
    published_at = 10.2
    members: list[StructuralAmbiguityMemberState] = []
    observations: list[StructuralAmbiguityObservationEvidence] = []
    tracks: list[GlobalTrack] = []
    observation_keys: list[str] = []
    for index in range(count):
        local_id = f"local-{offset + index}"
        member_token = structural_ambiguity_member_track_token(
            PUBLISHER,
            EPOCH,
            local_id,
        )
        source_key = structural_ambiguity_source_key(
            PUBLISHER,
            EPOCH,
            member_token,
        )
        position = np.array(
            [
                1_000.0 + 23.0 * index,
                -80.0 + 17.0 * index * index,
                -100.0 - 3.0 * index,
            ]
        )
        state = np.concatenate(
            (position, np.array([12.0 + index, -0.5 * index, 0.25]))
        )
        covariance = np.diag([4.0, 5.0, 6.0, 1.0, 1.5, 2.0])
        members.append(
            StructuralAmbiguityMemberState(
                opaque_member_track_token=member_token,
                source_key=source_key,
                state=state,
                covariance=covariance,
            )
        )
        observation_key = _token(
            "d1-observation-sha256:",
            f"{component_tag}-observation-{offset + index}",
        )
        observation_keys.append(observation_key)
        observations.append(
            StructuralAmbiguityObservationEvidence(
                observation_evidence_key=observation_key,
                position_ned=position + translation,
                covariance_ned=np.diag([1.0, 1.5, 2.0]),
                radial_velocity_observed=False,
                birth_deferred=False,
            )
        )
        tracks.append(
            GlobalTrack(
                global_track_id=f"CENTER-GT-{offset + index}",
                state=state + np.array([2.0, 1.0, -1.0, 0.0, 0.0, 0.0]),
                covariance=np.diag([7.0, 8.0, 9.0, 2.0, 2.5, 3.0]),
                timestamp=published_at,
                track_level=TrackLevel.STABLE,
                source_support={"radar": 3, "acoustic": 1},
                identity_likelihood={"unknown": 0.8, "candidate": 0.2},
                last_nis=1.25,
                metadata={
                    "frame_id": "ned",
                    "published_at": published_at,
                    "measurement_timestamp": measurement_timestamp,
                    "arrival_timestamp": arrival_timestamp,
                    "source_key": source_key,
                    "opaque_member_track_token": member_token,
                    "lineage": {"source": f"anonymous-{offset + index}"},
                    "quality": "stable",
                },
            )
        )

    edges: list[StructuralAmbiguityCandidateEdge] = []
    for index, member in enumerate(members):
        edges.append(
            StructuralAmbiguityCandidateEdge(
                opaque_member_track_token=member.opaque_member_track_token,
                observation_evidence_key=observation_keys[index],
                nis=1.0 + 0.01 * index,
                gate_threshold=20.0,
                edge_roles=(
                    "maximum_matching_allowed",
                    "matched_reference",
                ),
            )
        )
        edges.append(
            StructuralAmbiguityCandidateEdge(
                opaque_member_track_token=member.opaque_member_track_token,
                observation_evidence_key=observation_keys[(index + 1) % count],
                nis=2.0 + 0.01 * index,
                gate_threshold=20.0,
                edge_roles=(
                    "maximum_matching_allowed",
                    "alternating_cycle",
                ),
            )
        )

    component_id = _token(
        "d1-component-sha256:",
        f"{component_tag}-component-{offset}",
    )
    evidence = StructuralAmbiguityEvidence(
        evidence_id=_token(
            "d1-evidence-sha256:",
            f"{component_tag}-evidence-{offset}-{generation}-"
            f"{translation.tolist()}",
        ),
        component_id=component_id,
        component_generation=generation,
        publisher_node_id=PUBLISHER,
        publisher_epoch=EPOCH,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        state_valid_timestamp=measurement_timestamp,
        published_at=published_at,
        sensor_id="anonymous-radar",
        scan_id=_token("d1-scan-sha256:", f"scan-{component_tag}"),
        member_states=tuple(members),
        observations=tuple(observations),
        candidate_edges=tuple(edges),
        component_kinds=("alternating_cycle",),
        member_count=count,
        observation_count=count,
        candidate_edge_count=len(edges),
        free_row_count=0,
        free_column_count=0,
        maximum_matching_cardinality=count,
    )
    return tuple(tracks), evidence


def _business_bytes(tracks: tuple[GlobalTrack, ...]) -> bytes:
    return json.dumps(
        [track.to_dict() for track in tracks],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_track_bytes(tracks: tuple[GlobalTrack, ...]) -> bytes:
    return prototype._canonical_json_bytes(
        [track.to_dict() for track in tracks]
    )


def _large_readonly_case() -> tuple[
    tuple[GlobalTrack, ...],
    StructuralAmbiguityEvidence,
]:
    member_tracks, evidence = _case(2)
    filler_tracks, _ = _case(
        198,
        offset=2,
        component_tag="large-fixture",
    )
    tracks = member_tracks + filler_tracks
    for index, track in enumerate(tracks):
        track.metadata["readonly_payload"] = MappingProxyType(
            {
                "calibration": MappingProxyType(
                    {
                        "coefficients": (
                            np.float32(1.25),
                            np.float64(index + 0.5),
                        ),
                        "enabled": True,
                    }
                ),
                "lineage_tuple": ("sensor", index),
                "quality_set": frozenset({"fused", "validated"}),
                "residual_vector": np.array(
                    [index, index + 1, index + 2],
                    dtype=np.float64,
                ),
            }
        )
    return tracks, evidence


@pytest.mark.parametrize("count", (2, 3, 5))
def test_balanced_cycles_accept_uniform_detached_overlay(count: int) -> None:
    tracks, evidence = _case(count)
    before_bytes = _business_bytes(tracks)
    states_before = tuple(track.state.copy() for track in tracks)
    metadata_before = tuple(json.dumps(track.metadata, sort_keys=True) for track in tracks)

    evaluation = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
    )
    decision = evaluation.decisions[0]

    assert decision.decision == "accepted"
    assert decision.reject_reason is None
    assert decision.prototype_status == "experimental_design_prototype_not_online_schema"
    assert decision.state_semantics == "publication_overlay_not_filter_posterior"
    assert decision.cross_covariance_available is False
    assert decision.mutates_filter_history is False
    assert len(decision.member_overlays) == count
    expected_delta = CONFIG.centroid_gain * np.array([4.0, -2.0, 1.0])
    for overlay in decision.member_overlays:
        np.testing.assert_allclose(overlay.delta_position_ned, expected_delta)
        assert float(
            np.linalg.eigvalsh(overlay.delta_position_covariance)[0]
        ) >= -1.0e-12

    shadow = assemble_experimental_centroid_shadow_tracks(tracks, evaluation)
    assert shadow is not tracks
    assert tuple(track.global_track_id for track in shadow) == tuple(
        track.global_track_id for track in tracks
    )
    for original, overlaid in zip(tracks, shadow, strict=True):
        np.testing.assert_allclose(overlaid.state[:3] - original.state[:3], expected_delta)
        np.testing.assert_array_equal(overlaid.state[3:], original.state[3:])
        covariance_delta = overlaid.covariance - original.covariance
        np.testing.assert_array_equal(covariance_delta[3:, :], np.zeros((3, 6)))
        np.testing.assert_array_equal(covariance_delta[:3, 3:], np.zeros((3, 3)))
        assert float(np.linalg.eigvalsh(covariance_delta)[0]) >= -1.0e-12
        assert overlaid.track_level == original.track_level
        assert overlaid.source_support == original.source_support
        assert overlaid.identity_likelihood == original.identity_likelihood
        assert overlaid.metadata == original.metadata
    for left, right in zip(shadow[1:], tracks[1:], strict=True):
        np.testing.assert_allclose(
            left.state[:3] - shadow[0].state[:3],
            right.state[:3] - tracks[0].state[:3],
        )

    assert _business_bytes(tracks) == before_bytes
    for track, state, metadata in zip(
        tracks,
        states_before,
        metadata_before,
        strict=True,
    ):
        np.testing.assert_array_equal(track.state, state)
        assert json.dumps(track.metadata, sort_keys=True) == metadata


def test_rejections_are_empty_and_return_exact_canonical_sequence() -> None:
    tracks, evidence = _case(3)
    balanced_free = replace(
        evidence,
        free_row_count=1,
        free_column_count=1,
        maximum_matching_cardinality=2,
    )
    unbalanced_edges = tuple(
        edge
        for edge in evidence.candidate_edges
        if edge.observation_evidence_key
        in {
            item.observation_evidence_key
            for item in evidence.observations[:2]
        }
    )
    unbalanced = replace(
        evidence,
        observations=evidence.observations[:2],
        candidate_edges=unbalanced_edges,
        observation_count=2,
        candidate_edge_count=len(unbalanced_edges),
        free_row_count=1,
        free_column_count=0,
        maximum_matching_cardinality=2,
    )
    dense_edges = tuple(
        StructuralAmbiguityCandidateEdge(
            opaque_member_track_token=member.opaque_member_track_token,
            observation_evidence_key=observation.observation_evidence_key,
            nis=1.0,
            gate_threshold=20.0,
            edge_roles=(
                ("matched_reference", "maximum_matching_allowed")
                if member is evidence.member_states[index]
                else ("alternating_cycle", "maximum_matching_allowed")
            ),
        )
        for index, observation in enumerate(evidence.observations)
        for member in evidence.member_states
    )
    non_cycle = replace(
        evidence,
        candidate_edges=dense_edges,
        candidate_edge_count=len(dense_edges),
    )
    nonfinite = StructuralAmbiguityEvidence.from_dict(evidence.to_dict())
    nonfinite.member_states[0].state[0] = np.nan
    identity_tracks = tuple(track.copy() for track in tracks)
    identity_tracks[0].metadata["truth_id"] = "offline-only"

    cases = (
        (
            tracks,
            evidence,
            ExperimentalCentroidEvidenceDisposition(
                oosm_evidence_ids=frozenset({evidence.evidence_id})
            ),
            "oosm_scan",
        ),
        (
            tracks,
            evidence,
            ExperimentalCentroidEvidenceDisposition(
                stale_evidence_ids=frozenset({evidence.evidence_id})
            ),
            "stale_scan",
        ),
        (tracks, unbalanced, None, "unbalanced_component"),
        (tracks, balanced_free, None, "free_row_present"),
        (tracks, non_cycle, None, "component_not_pure_alternating_cycle"),
        (tracks, nonfinite, None, "nonfinite_input"),
        (identity_tracks, evidence, None, "forbidden_identity_metadata"),
    )
    for business_tracks, item, disposition, expected_reason in cases:
        before = _business_bytes(business_tracks)
        evaluation = evaluate_experimental_centroid_publication_overlays(
            business_tracks,
            (item,),
            config=CONFIG,
            disposition=disposition,
        )
        decision = evaluation.decisions[0]
        assert decision.decision == "rejected"
        assert decision.reject_reason == expected_reason
        assert decision.member_overlays == ()
        assembled = assemble_experimental_centroid_shadow_tracks(
            business_tracks,
            evaluation,
        )
        assert assembled is business_tracks
        assert _business_bytes(business_tracks) == before


def test_member_observation_edge_track_and_component_permutations_are_identical() -> None:
    tracks, evidence = _case(3)
    reference = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
    ).decisions[0].canonical_bytes()

    for track_order in permutations(tracks):
        actual = evaluate_experimental_centroid_publication_overlays(
            track_order,
            (evidence,),
            config=CONFIG,
        ).decisions[0].canonical_bytes()
        assert actual == reference
    for member_order in permutations(evidence.member_states):
        actual = evaluate_experimental_centroid_publication_overlays(
            tracks,
            (replace(evidence, member_states=member_order),),
            config=CONFIG,
        ).decisions[0].canonical_bytes()
        assert actual == reference
    for observation_order in permutations(evidence.observations):
        actual = evaluate_experimental_centroid_publication_overlays(
            tracks,
            (replace(evidence, observations=observation_order),),
            config=CONFIG,
        ).decisions[0].canonical_bytes()
        assert actual == reference
    for edge_order in permutations(evidence.candidate_edges):
        actual = evaluate_experimental_centroid_publication_overlays(
            tracks,
            (replace(evidence, candidate_edges=edge_order),),
            config=CONFIG,
        ).decisions[0].canonical_bytes()
        assert actual == reference

    tracks_b, evidence_b = _case(2, offset=20, component_tag="b")
    combined_tracks = tracks + tracks_b
    batch_reference = evaluate_experimental_centroid_publication_overlays(
        combined_tracks,
        (evidence, evidence_b),
        config=CONFIG,
    ).canonical_bytes()
    for component_order in permutations((evidence, evidence_b)):
        actual = evaluate_experimental_centroid_publication_overlays(
            combined_tracks,
            component_order,
            config=CONFIG,
        ).canonical_bytes()
        assert actual == batch_reference


def test_generation_conflict_capacity_and_state_are_fail_closed_and_bounded() -> None:
    tracks, generation_one = _case(2)
    first = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
    )
    assert first.decisions[0].decision == "accepted"

    duplicate = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        state=first.next_state,
    )
    assert duplicate.decisions[0].reject_reason == "duplicate_evidence_generation"
    assert duplicate.decisions[0].member_overlays == ()

    _, generation_two = _case(2, generation=2)
    newer = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_two,),
        config=CONFIG,
    )
    regressed = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        state=newer.next_state,
    )
    assert regressed.decisions[0].reject_reason == "regressed_evidence_generation"

    _, changed_summary = _case(
        2,
        generation=1,
        translation=np.array([5.0, -2.0, 1.0]),
    )
    conflict = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (changed_summary,),
        config=CONFIG,
        state=first.next_state,
    )
    assert conflict.decisions[0].reject_reason == "generation_summary_conflict"

    tracks_b, evidence_b = _case(2, offset=10, component_tag="b")
    capacity_state = ExperimentalCentroidPublicationState(max_entries=1)
    filled = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        state=capacity_state,
    )
    capacity = evaluate_experimental_centroid_publication_overlays(
        tracks_b,
        (evidence_b,),
        config=CONFIG,
        state=filled.next_state,
    )
    assert capacity.decisions[0].reject_reason == (
        "generation_registry_capacity_reached"
    )
    assert len(capacity.next_state.watermarks) == 1

    bounded = ExperimentalCentroidPublicationState(max_entries=2)
    for generation in range(1, 21):
        _, item = _case(2, generation=generation)
        result = evaluate_experimental_centroid_publication_overlays(
            tracks,
            (item,),
            config=CONFIG,
            state=bounded,
        )
        bounded = result.next_state
        assert len(bounded.watermarks) <= bounded.max_entries
    assert len(bounded.watermarks) == 1


def test_conflicting_components_reject_independent_of_component_order() -> None:
    tracks, first = _case(2, component_tag="first")
    _, second = _case(2, component_tag="second")
    outputs = []
    for order in permutations((first, second)):
        result = evaluate_experimental_centroid_publication_overlays(
            tracks,
            order,
            config=CONFIG,
        )
        outputs.append(result.canonical_bytes())
        assert {
            item.reject_reason for item in result.decisions
        } == {"conflicting_component_membership"}
        assert all(not item.member_overlays for item in result.decisions)
        assert (
            assemble_experimental_centroid_shadow_tracks(tracks, result)
            is tracks
        )
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("count", (2, 3, 5))
def test_prepared_and_legacy_entries_have_identical_decision_bytes(
    count: int,
) -> None:
    tracks, evidence = _case(count)
    legacy = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
    )
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    optimized = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )

    assert optimized.canonical_bytes() == legacy.canonical_bytes()
    assert tuple(
        item.canonical_bytes() for item in optimized.decisions
    ) == tuple(item.canonical_bytes() for item in legacy.decisions)
    assert hashlib.sha256(
        optimized.decisions[0].canonical_bytes()
    ).hexdigest() == BASELINE_DECISION_SHA256_BY_MEMBER_COUNT[count]
    assert prepared.work.full_description_pass_count == 1
    assert prepared.work.track_count == count
    assert prepared.work.validated_track_count == count
    assert prepared.work.full_track_digest_count == count


@pytest.mark.parametrize("count", (2, 3, 5))
def test_atomic_entry_preserves_legacy_decision_bytes(count: int) -> None:
    tracks, evidence = _case(count)
    before = _business_bytes(tracks)
    legacy = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
    )

    result = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (evidence,),
        config=CONFIG,
    )

    assert result.evaluation.canonical_bytes() == legacy.canonical_bytes()
    assert hashlib.sha256(
        result.evaluation.decisions[0].canonical_bytes()
    ).hexdigest() == BASELINE_DECISION_SHA256_BY_MEMBER_COUNT[count]
    assert result.shadow_materialized is True
    assert result.shadow_tracks is not None
    assert result.shadow_publication_digest is not None
    assert result.post_integrity_check.matches is True
    assert result.atomic_failure_reason is None
    assert result.prepared_publication.track_count == count
    assert not hasattr(result.prepared_publication, "_descriptors")
    assert _business_bytes(tracks) == before


def test_atomic_rejection_post_verifies_without_shadow_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracks, evidence = _case(2)

    def unexpected_assembly(*args: object, **kwargs: object) -> object:
        raise AssertionError("rejected path must not assemble shadow tracks")

    monkeypatch.setattr(
        prototype,
        "_assemble_experimental_centroid_shadow_tracks_from_prepared",
        unexpected_assembly,
    )
    result = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (evidence,),
        config=CONFIG,
        disposition=ExperimentalCentroidEvidenceDisposition(
            oosm_evidence_ids=frozenset({evidence.evidence_id})
        ),
    )

    assert result.evaluation.decisions[0].reject_reason == "oosm_scan"
    assert result.shadow_tracks is None
    assert result.shadow_materialized is False
    assert result.shadow_publication_digest is None
    assert result.atomic_failure_reason is None
    assert result.post_integrity_check.to_dict() == {
        "matches": True,
        "mismatch_reason": None,
        "object_binding_pass_count": 1,
        "full_content_digest_pass_count": 1,
        "track_digest_count": 2,
    }
    assert result.work.shadow_track_copy_count == 0
    assert result.work.shadow_full_track_digest_count == 0
    assert result.work.shadow_publication_digest_count == 0
    json.dumps(result.to_dict(), allow_nan=False, sort_keys=True)

    failure_tracks, failure_evidence = _case(2)
    initial_state = ExperimentalCentroidPublicationState()

    def failed_assembly(*args: object, **kwargs: object) -> object:
        raise RuntimeError("fixture")

    monkeypatch.setattr(
        prototype,
        "_assemble_experimental_centroid_shadow_tracks_from_prepared",
        failed_assembly,
    )
    failure = run_experimental_centroid_publication_overlay_atomically(
        failure_tracks,
        (failure_evidence,),
        state=initial_state,
        config=CONFIG,
    )

    assert failure.atomic_failure_reason == (
        "shadow_assembly_failed:shadow_assembly_exception:RuntimeError"
    )
    assert failure.post_integrity_check.matches is True
    assert failure.shadow_tracks is None
    assert failure.shadow_publication_digest is None
    assert failure.shadow_materialized is False
    assert failure.evaluation.next_state == initial_state
    assert all(
        item.decision == "rejected"
        and item.reject_reason == "atomic_shadow_assembly_failed"
        and not item.member_overlays
        for item in failure.evaluation.decisions
    )
    assert failure.work.shadow_track_copy_count == 0
    assert failure.work.shadow_full_track_digest_count == 0
    assert failure.work.shadow_publication_digest_count == 0


def test_atomic_temporal_and_balance_rejections_remain_fail_closed() -> None:
    tracks, generation_one = _case(2)
    first = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (generation_one,),
        config=CONFIG,
    )
    duplicate = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (generation_one,),
        state=first.evaluation.next_state,
        config=CONFIG,
    )
    assert duplicate.evaluation.decisions[0].reject_reason == (
        "duplicate_evidence_generation"
    )
    assert duplicate.shadow_tracks is None

    _, generation_two = _case(2, generation=2)
    newer = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (generation_two,),
        config=CONFIG,
    )
    regressed = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (generation_one,),
        state=newer.evaluation.next_state,
        config=CONFIG,
    )
    assert regressed.evaluation.decisions[0].reject_reason == (
        "regressed_evidence_generation"
    )
    assert regressed.shadow_tracks is None

    allowed_observations = generation_one.observations[:1]
    allowed_keys = {
        item.observation_evidence_key for item in allowed_observations
    }
    unbalanced_edges = tuple(
        edge
        for edge in generation_one.candidate_edges
        if edge.observation_evidence_key in allowed_keys
    )
    unbalanced = replace(
        generation_one,
        observations=allowed_observations,
        candidate_edges=unbalanced_edges,
        observation_count=1,
        candidate_edge_count=len(unbalanced_edges),
        free_row_count=1,
        maximum_matching_cardinality=1,
    )
    rejected = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (unbalanced,),
        config=CONFIG,
    )
    assert rejected.evaluation.decisions[0].reject_reason == (
        "unbalanced_component"
    )
    assert rejected.shadow_tracks is None
    assert rejected.post_integrity_check.matches is True


def test_prepared_200_track_readonly_metadata_uses_one_description_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracks, evidence = _large_readonly_case()

    legacy = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
    )
    original_describe = prototype._describe_tracks
    original_integrity_digest = prototype._integrity_track_digest
    describe_call_count = 0
    integrity_digest_count = 0

    def counted_describe(
        values: tuple[GlobalTrack, ...],
    ) -> tuple[object, ...]:
        nonlocal describe_call_count
        describe_call_count += 1
        return original_describe(values)

    def counted_integrity_digest(track: GlobalTrack) -> str:
        nonlocal integrity_digest_count
        integrity_digest_count += 1
        return original_integrity_digest(track)

    monkeypatch.setattr(prototype, "_describe_tracks", counted_describe)
    monkeypatch.setattr(
        prototype,
        "_integrity_track_digest",
        counted_integrity_digest,
    )
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    optimized = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    shadow = assemble_experimental_centroid_shadow_tracks(
        tracks,
        optimized,
        prepared_publication=prepared,
    )

    assert describe_call_count == 1
    assert integrity_digest_count == 400
    assert prepared.work.to_dict() == {
        "full_description_pass_count": 1,
        "track_count": 200,
        "validated_track_count": 200,
        "full_track_digest_count": 200,
        "state_digest_count": 200,
        "covariance_digest_count": 200,
        "publication_digest_count": 1,
    }
    assert optimized.prepared_integrity_check is not None
    assert optimized.prepared_integrity_check.to_dict() == {
        "matches": True,
        "mismatch_reason": None,
        "object_binding_pass_count": 1,
        "full_content_digest_pass_count": 1,
        "track_digest_count": 200,
    }
    assert optimized.canonical_bytes() == legacy.canonical_bytes()
    assert shadow is not tracks
    assert len(shadow) == 200
    assert tuple(item.global_track_id for item in shadow) == tuple(
        item.global_track_id for item in tracks
    )
    for original, copied in zip(tracks, shadow, strict=True):
        np.testing.assert_array_equal(copied.velocity, original.velocity)
        assert prototype._canonical_json_bytes(
            copied.source_support
        ) == prototype._canonical_json_bytes(original.source_support)
        assert prototype._canonical_json_bytes(
            copied.identity_likelihood
        ) == prototype._canonical_json_bytes(original.identity_likelihood)
        assert prototype._canonical_json_bytes(
            copied.metadata
        ) == prototype._canonical_json_bytes(original.metadata)
        assert (
            copied.metadata["readonly_payload"]["residual_vector"]
            is not original.metadata["readonly_payload"]["residual_vector"]
        )
        covariance_delta = copied.covariance - original.covariance
        assert float(np.linalg.eigvalsh(covariance_delta)[0]) >= -1.0e-12
    np.testing.assert_allclose(
        shadow[1].position - shadow[0].position,
        tracks[1].position - tracks[0].position,
    )
    shadow[0].metadata["readonly_payload"]["residual_vector"][0] = -999.0
    assert (
        tracks[0].metadata["readonly_payload"]["residual_vector"][0]
        == 0.0
    )


def test_atomic_200_track_work_and_detached_readonly_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracks, evidence = _large_readonly_case()
    canonical_before = _canonical_track_bytes(tracks)
    legacy = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
    )
    original_describe = prototype._describe_tracks
    original_integrity_digest = prototype._integrity_track_digest
    describe_call_count = 0
    integrity_digest_count = 0

    def counted_describe(
        values: tuple[GlobalTrack, ...],
    ) -> tuple[object, ...]:
        nonlocal describe_call_count
        describe_call_count += 1
        return original_describe(values)

    def counted_integrity_digest(track: GlobalTrack) -> str:
        nonlocal integrity_digest_count
        integrity_digest_count += 1
        return original_integrity_digest(track)

    monkeypatch.setattr(prototype, "_describe_tracks", counted_describe)
    monkeypatch.setattr(
        prototype,
        "_integrity_track_digest",
        counted_integrity_digest,
    )
    result = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (evidence,),
        config=CONFIG,
    )

    assert describe_call_count == 1
    assert integrity_digest_count == 200
    assert result.work.to_dict() == {
        "canonical_full_description_pass_count": 1,
        "canonical_description_track_digest_count": 200,
        "canonical_post_integrity_pass_count": 1,
        "canonical_post_integrity_track_digest_count": 200,
        "shadow_track_copy_count": 200,
        "shadow_full_track_digest_count": 200,
        "shadow_publication_digest_count": 1,
    }
    assert result.prepared_publication.work.to_dict() == {
        "full_description_pass_count": 1,
        "track_count": 200,
        "validated_track_count": 200,
        "full_track_digest_count": 200,
        "state_digest_count": 200,
        "covariance_digest_count": 200,
        "publication_digest_count": 1,
    }
    assert result.evaluation.canonical_bytes() == legacy.canonical_bytes()
    assert result.shadow_materialized is True
    assert result.shadow_tracks is not None
    assert result.shadow_publication_digest is not None
    assert (
        result.shadow_publication_digest
        != result.canonical_publication_digest
    )
    assert _canonical_track_bytes(tracks) == canonical_before

    shadow = result.shadow_tracks
    assert tuple(item.global_track_id for item in shadow) == tuple(
        item.global_track_id for item in tracks
    )
    for original, copied in zip(tracks, shadow, strict=True):
        assert copied is not original
        assert copied.state is not original.state
        assert copied.covariance is not original.covariance
        assert copied.source_support is not original.source_support
        assert copied.identity_likelihood is not original.identity_likelihood
        assert copied.metadata is not original.metadata
        np.testing.assert_array_equal(copied.velocity, original.velocity)
        assert prototype._canonical_json_bytes(
            copied.source_support
        ) == prototype._canonical_json_bytes(original.source_support)
        assert prototype._canonical_json_bytes(
            copied.identity_likelihood
        ) == prototype._canonical_json_bytes(original.identity_likelihood)
        assert prototype._canonical_json_bytes(
            copied.metadata
        ) == prototype._canonical_json_bytes(original.metadata)
        covariance_delta = copied.covariance - original.covariance
        assert float(np.linalg.eigvalsh(covariance_delta)[0]) >= -1.0e-12
    np.testing.assert_allclose(
        shadow[1].position - shadow[0].position,
        tracks[1].position - tracks[0].position,
    )
    assert (
        shadow[0].metadata["readonly_payload"]["residual_vector"]
        is not tracks[0].metadata["readonly_payload"]["residual_vector"]
    )
    shadow_prepared = prepare_experimental_centroid_canonical_publication(
        shadow
    )
    assert (
        result.shadow_publication_digest
        == shadow_prepared.base_publication_digest
    )

    with pytest.raises(FrozenInstanceError):
        result.shadow_materialized = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.prepared_publication.track_count = 0  # type: ignore[misc]
    shadow[0].state[0] += 100.0
    shadow[0].metadata["readonly_payload"]["residual_vector"][0] = -999.0
    assert tracks[0].state[0] != shadow[0].state[0]
    assert (
        tracks[0].metadata["readonly_payload"]["residual_vector"][0]
        == 0.0
    )
    external = result.to_dict()
    assert set(external) == {
        "prototype_status",
        "usage_scope",
        "evaluation",
        "shadow_tracks",
        "prepared_publication",
        "post_integrity_check",
        "canonical_publication_digest",
        "shadow_publication_digest",
        "shadow_materialized",
        "work",
        "atomic_failure_reason",
    }
    serialized = json.dumps(
        external,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert result.canonical_bytes() == serialized
    assert json.loads(serialized) == external
    external["prepared_publication"]["work"]["track_count"] = 0
    assert result.prepared_publication.track_count == 200


def test_prepared_handle_is_immutable_and_mismatch_fails_closed() -> None:
    tracks, evidence = _case(2)
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    accepted = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )

    with pytest.raises(FrozenInstanceError):
        prepared.base_publication_digest = "sha256:" + "0" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        prepared.work.track_count = 0  # type: ignore[misc]
    external = prepared.to_dict()
    external["work"]["track_count"] = 0
    assert prepared.track_count == 2

    equivalent_but_unbound = tuple(track.copy() for track in tracks)
    mismatch = evaluate_experimental_centroid_publication_overlays(
        equivalent_but_unbound,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    assert mismatch.decisions[0].decision == "rejected"
    assert mismatch.decisions[0].reject_reason == (
        "prepared_canonical_publication_mismatch"
    )
    assert (
        assemble_experimental_centroid_shadow_tracks(
            equivalent_but_unbound,
            accepted,
            prepared_publication=prepared,
        )
        is equivalent_but_unbound
    )
    assert (
        assemble_experimental_centroid_shadow_tracks(
            equivalent_but_unbound,
            mismatch,
            prepared_publication=prepared,
        )
        is equivalent_but_unbound
    )


def test_prepared_state_in_place_mutation_fails_closed() -> None:
    tracks, evidence = _case(2)
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    accepted = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    assert accepted.decisions[0].decision == "accepted"

    tracks[0].state[0] += 0.25
    rejected = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )

    assert rejected.decisions[0].decision == "rejected"
    assert rejected.decisions[0].reject_reason == (
        "prepared_canonical_publication_mismatch"
    )
    assert rejected.prepared_integrity_check is not None
    assert rejected.prepared_integrity_check.mismatch_reason == (
        "track_content_digest_mismatch"
    )
    assert (
        assemble_experimental_centroid_shadow_tracks(
            tracks,
            accepted,
            prepared_publication=prepared,
        )
        is tracks
    )


@pytest.mark.parametrize(
    "surface",
    (
        "state",
        "covariance",
        "metadata",
        "source_support",
        "identity_likelihood",
        "global_track_id",
        "timestamp",
        "track_level",
        "last_nis",
    ),
)
def test_atomic_in_call_canonical_mutation_discards_shadow_and_state(
    surface: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracks, evidence = _case(2)
    tracks[0].metadata["calibration"] = {
        "camera": {
            "bias": [0.1, 0.2],
            "axes": np.array([1.0, 0.0, 0.0]),
        }
    }
    initial_state = ExperimentalCentroidPublicationState()
    original_evaluate = (
        prototype._evaluate_experimental_centroid_publication_overlays_from_prepared
    )

    def mutate_after_evaluation(*args: object, **kwargs: object) -> object:
        evaluation = original_evaluate(*args, **kwargs)
        if surface == "state":
            tracks[0].state[0] += 0.25
        elif surface == "covariance":
            tracks[0].covariance[0, 0] += 0.5
        elif surface == "metadata":
            tracks[0].metadata["calibration"]["camera"]["bias"][0] = 9.5
        elif surface == "source_support":
            tracks[0].source_support["radar"] += 1
        elif surface == "identity_likelihood":
            tracks[0].identity_likelihood["unknown"] = 0.7
        elif surface == "global_track_id":
            tracks[0].global_track_id = "CENTER-GT-CHANGED"
        elif surface == "timestamp":
            tracks[0].timestamp += 0.01
        elif surface == "track_level":
            tracks[0].track_level = TrackLevel.COARSE
        else:
            tracks[0].last_nis = 2.5
        return evaluation

    monkeypatch.setattr(
        prototype,
        "_evaluate_experimental_centroid_publication_overlays_from_prepared",
        mutate_after_evaluation,
    )
    result = run_experimental_centroid_publication_overlay_atomically(
        tracks,
        (evidence,),
        state=initial_state,
        config=CONFIG,
    )

    assert result.post_integrity_check.matches is False
    assert result.atomic_failure_reason is not None
    assert result.atomic_failure_reason.startswith("post_integrity_mismatch:")
    assert result.shadow_tracks is None
    assert result.shadow_materialized is False
    assert result.shadow_publication_digest is None
    assert result.evaluation.next_state == initial_state
    assert all(
        item.decision == "rejected"
        and item.reject_reason == "prepared_canonical_publication_mismatch"
        and not item.member_overlays
        for item in result.evaluation.decisions
    )
    assert result.work.canonical_full_description_pass_count == 1
    assert result.work.shadow_track_copy_count == 2


def test_prepared_nested_metadata_in_place_mutation_fails_closed() -> None:
    tracks, evidence = _case(2)
    tracks[0].metadata["calibration"] = {
        "camera": {
            "bias": [0.1, 0.2],
            "axes": np.array([1.0, 0.0, 0.0]),
        }
    }
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    accepted = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    assert accepted.decisions[0].decision == "accepted"

    tracks[0].metadata["calibration"]["camera"]["bias"][0] = 9.5
    rejected = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )

    assert rejected.decisions[0].reject_reason == (
        "prepared_canonical_publication_mismatch"
    )
    assert rejected.prepared_integrity_check is not None
    assert rejected.prepared_integrity_check.mismatch_reason == (
        "track_content_digest_mismatch"
    )
    assert (
        assemble_experimental_centroid_shadow_tracks(
            tracks,
            accepted,
            prepared_publication=prepared,
        )
        is tracks
    )


@pytest.mark.parametrize(
    "surface",
    (
        "covariance",
        "source_support",
        "identity_likelihood",
        "global_track_id",
        "timestamp",
        "track_level",
    ),
)
def test_prepared_other_canonical_surface_mutations_fail_closed(
    surface: str,
) -> None:
    tracks, evidence = _case(2)
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    accepted = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    assert accepted.decisions[0].decision == "accepted"

    if surface == "covariance":
        tracks[0].covariance[0, 0] += 0.5
    elif surface == "source_support":
        tracks[0].source_support["radar"] += 1
    elif surface == "identity_likelihood":
        tracks[0].identity_likelihood["unknown"] = 0.7
    elif surface == "global_track_id":
        tracks[0].global_track_id = "CENTER-GT-CHANGED"
    elif surface == "timestamp":
        tracks[0].timestamp += 0.01
    else:
        tracks[0].track_level = TrackLevel.COARSE

    rejected = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (evidence,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    assert rejected.decisions[0].reject_reason == (
        "prepared_canonical_publication_mismatch"
    )
    assert rejected.prepared_integrity_check is not None
    assert rejected.prepared_integrity_check.matches is False
    assert (
        assemble_experimental_centroid_shadow_tracks(
            tracks,
            accepted,
            prepared_publication=prepared,
        )
        is tracks
    )


def test_prepared_path_keeps_temporal_and_balance_rejections_fail_closed() -> None:
    tracks, generation_one = _case(2)
    prepared = prepare_experimental_centroid_canonical_publication(tracks)
    oosm = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        disposition=ExperimentalCentroidEvidenceDisposition(
            oosm_evidence_ids=frozenset({generation_one.evidence_id})
        ),
        prepared_publication=prepared,
    )
    assert oosm.decisions[0].reject_reason == "oosm_scan"
    assert (
        assemble_experimental_centroid_shadow_tracks(
            tracks,
            oosm,
            prepared_publication=prepared,
        )
        is tracks
    )

    allowed_observations = generation_one.observations[:1]
    allowed_keys = {
        item.observation_evidence_key for item in allowed_observations
    }
    unbalanced_edges = tuple(
        edge
        for edge in generation_one.candidate_edges
        if edge.observation_evidence_key in allowed_keys
    )
    unbalanced = replace(
        generation_one,
        observations=allowed_observations,
        candidate_edges=unbalanced_edges,
        observation_count=1,
        candidate_edge_count=len(unbalanced_edges),
        free_row_count=1,
        maximum_matching_cardinality=1,
    )
    rejected = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (unbalanced,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    assert rejected.decisions[0].reject_reason == "unbalanced_component"
    assert (
        assemble_experimental_centroid_shadow_tracks(
            tracks,
            rejected,
            prepared_publication=prepared,
        )
        is tracks
    )

    first = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    duplicate = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        state=first.next_state,
        prepared_publication=prepared,
    )
    assert duplicate.decisions[0].reject_reason == (
        "duplicate_evidence_generation"
    )
    _, generation_two = _case(2, generation=2)
    newer = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_two,),
        config=CONFIG,
        prepared_publication=prepared,
    )
    regressed = evaluate_experimental_centroid_publication_overlays(
        tracks,
        (generation_one,),
        config=CONFIG,
        state=newer.next_state,
        prepared_publication=prepared,
    )
    assert regressed.decisions[0].reject_reason == (
        "regressed_evidence_generation"
    )
    assert (
        assemble_experimental_centroid_shadow_tracks(
            tracks,
            regressed,
            prepared_publication=prepared,
        )
        is tracks
    )
