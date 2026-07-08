from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    IdentityClaim,
    LocalVisualTrack,
    ReconImageCue,
    TerminalAssociation,
    TerminalObservationBus,
    summarize_secondary_visual_coverage_funnel,
)


def _local(local_id: str, center: tuple[float, float] = (320.0, 240.0)) -> LocalVisualTrack:
    return LocalVisualTrack(
        local_track_id=local_id,
        center_px=np.array(center, dtype=float),
        bbox=(center[0] - 4.0, center[1] - 4.0, center[0] + 4.0, center[1] + 4.0),
        quality=0.95,
        mot_history_length=5,
    )


def _locked(global_id: str, local_id: str, cue_used: bool = False) -> TerminalAssociation:
    return TerminalAssociation(
        assigned_global_track_id=global_id,
        local_track_id=local_id,
        association_confidence=0.9,
        ambiguity_score=0.1,
        friend_conflict_state="none",
        decision_state="locked",
        assignment_version=3,
        reason="test_fixture",
        recon_cue_used=cue_used,
    )


def test_cross_view_bus_groups_overlapping_uav_views_without_rewriting_global_ids() -> None:
    bus = TerminalObservationBus()
    submitted_global_ids: list[str] = []

    fixtures = [
        ("UAV1", "G1", "L1"),
        ("UAV1", "G2", "L2"),
        ("UAV1", "G3", "L3"),
        ("UAV2", "G2", "L1"),
        ("UAV2", "G3", "L2"),
        ("UAV2", "G4", "L3"),
    ]
    for resource_id, global_id, local_id in fixtures:
        association = _locked(global_id, local_id)
        submitted_global_ids.append(association.assigned_global_track_id)
        bus.publish_terminal_association(
            resource_id=resource_id,
            source_node_id=resource_id,
            link_type="interceptor_peer",
            timestamp=10.0,
            terminal_association=association,
            local_track=_local(local_id),
            camera_id="front_rgb",
            frame_id=f"{resource_id}/front_rgb",
        )

    by_global_id = {item.global_track_id: item for item in bus.cross_view_associations()}

    assert set(by_global_id) == {"G1", "G2", "G3", "G4"}
    assert by_global_id["G2"].supporting_resource_ids == ("UAV1", "UAV2")
    assert by_global_id["G3"].supporting_resource_ids == ("UAV1", "UAV2")
    assert by_global_id["G2"].local_track_ids == ("UAV1/front_rgb:L2", "UAV2/front_rgb:L1")
    assert by_global_id["G3"].local_track_ids == ("UAV1/front_rgb:L3", "UAV2/front_rgb:L2")
    assert by_global_id["G2"].duplicate_terminal_lock_risk is True
    assert by_global_id["G3"].duplicate_terminal_lock_risk is True
    assert by_global_id["G2"].duplicate_lock_resource_ids == ("UAV1", "UAV2")
    assert by_global_id["G3"].duplicate_lock_resource_ids == ("UAV1", "UAV2")
    assert by_global_id["G2"].metadata["observed_global_track_ids_by_resource"] == {
        "UAV1": ("G1", "G2", "G3"),
        "UAV2": ("G2", "G3", "G4"),
    }

    assert by_global_id["G1"].supporting_resource_ids == ("UAV1",)
    assert by_global_id["G4"].supporting_resource_ids == ("UAV2",)
    assert by_global_id["G1"].duplicate_terminal_lock_risk is False
    assert by_global_id["G4"].duplicate_terminal_lock_risk is False

    funnel = summarize_secondary_visual_coverage_funnel(
        observations=bus.observations(),
        cross_view_associations=by_global_id.values(),
        secondary_camera_ids=("front_rgb",),
    )
    assert funnel.funnel_counts.cross_view_association_count == 4
    assert funnel.funnel_counts.multi_support_count == 2

    assert [obs.terminal_association.assigned_global_track_id for obs in bus.observations()] == submitted_global_ids


def test_bus_preserves_identity_and_recon_cue_metadata_as_passive_evidence() -> None:
    bus = TerminalObservationBus()
    association = _locked("G2", "L2", cue_used=True)
    cue = ReconImageCue(
        cue_id="cue-secondary-1",
        producer_node_id="tethered-recon-1",
        timestamp=10.0,
        image_frame_id="UAV1/front_rgb",
        global_track_id="G2",
        center_px=np.array([320.0, 240.0], dtype=float),
        confidence=0.8,
        scoped_resource_ids=("UAV1",),
        metadata={
            "source_image_frame_id": "tethered-recon-1/wide_rgb",
            "reprojected_to_local_camera": True,
        },
    )
    claim = IdentityClaim(
        platform_id="FRIEND-1",
        claim_type="RemoteID",
        auth_state="verified",
        timestamp=10.0,
        is_friend=True,
    )

    bus.publish_terminal_association(
        resource_id="UAV1",
        source_node_id="secondary-node-1",
        link_type="secondary_relay",
        timestamp=10.0,
        terminal_association=association,
        local_track=_local("L2"),
        identity_claims=[claim],
        recon_image_cues=[cue],
        camera_id="front_rgb",
        frame_id="UAV1/front_rgb",
        arrival_timestamp=10.2,
    )

    observation = bus.observations()[0]
    assert observation.recon_image_cues[0].global_track_id == "G2"
    assert observation.recon_image_cues[0].metadata["reprojected_to_local_camera"] is True
    assert observation.identity_claims[0].platform_id == "FRIEND-1"

    cross_view = bus.cross_view_associations()[0]
    assert cross_view.global_track_id == "G2"
    assert cross_view.recon_cue_used_count == 1
    assert cross_view.source_node_ids == ("secondary-node-1",)
    assert cross_view.link_types == ("secondary_relay",)


def test_local_only_observations_are_stored_but_do_not_create_global_associations() -> None:
    bus = TerminalObservationBus()
    bus.publish_local_track(
        resource_id="UAV1",
        source_node_id="UAV1",
        link_type="interceptor_peer",
        timestamp=12.0,
        local_track=_local("unassigned-local"),
        camera_id="front_rgb",
    )

    assert len(bus.observations()) == 1
    assert bus.cross_view_associations() == []


def test_bus_flags_same_local_track_locked_to_multiple_global_ids() -> None:
    bus = TerminalObservationBus()
    bus.publish_terminal_association(
        resource_id="UAV1",
        source_node_id="UAV1",
        link_type="interceptor_peer",
        timestamp=20.0,
        terminal_association=_locked("G1", "L-shared"),
        local_track=_local("L-shared"),
        camera_id="front_rgb",
        frame_id="UAV1/front_rgb",
    )
    bus.publish_terminal_association(
        resource_id="UAV1",
        source_node_id="UAV1",
        link_type="interceptor_peer",
        timestamp=20.1,
        terminal_association=_locked("G2", "L-shared"),
        local_track=_local("L-shared"),
        camera_id="front_rgb",
        frame_id="UAV1/front_rgb",
    )

    by_global_id = {item.global_track_id: item for item in bus.cross_view_associations()}

    assert by_global_id["G1"].duplicate_terminal_lock_risk is True
    assert by_global_id["G2"].duplicate_terminal_lock_risk is True
    assert by_global_id["G1"].duplicate_local_track_ids == ("UAV1/front_rgb:L-shared",)
    assert by_global_id["G2"].duplicate_local_track_ids == ("UAV1/front_rgb:L-shared",)
