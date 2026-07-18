from __future__ import annotations

from collections import defaultdict

import numpy as np
import pytest

from d5_terminal_association import (
    CameraLocalTrackBatch,
    CameraModel,
    GlobalTrack,
    GlobalTrackBinding,
    LocalVisualTrack,
    RegistrationStabilityConfig,
    TerminalObservationBus,
    register_local_visual_tracks_to_global_tracks,
)


_TARGET_X_M = {
    "G1": -48.0,
    "G2": -24.0,
    "G3": 0.0,
    "G4": 24.0,
    "G5": 48.0,
}
_TARGET_CENTER_PX = {
    "G1": (80.0, 240.0),
    "G2": (200.0, 240.0),
    "G3": (320.0, 240.0),
    "G4": (440.0, 240.0),
    "G5": (560.0, 240.0),
}
_LOCAL_ID_BY_RESOURCE_AND_TARGET = {
    "INT-1": {"G1": "5", "G2": "1"},
    "INT-2": {"G2": "1", "G3": "2"},
    "INT-3": {"G3": "G-looks-global-5", "G4": "42"},
    "INT-4": {"G4": "2", "G5": "1"},
    "INT-5": {"G1": "G5", "G5": "1"},
    "RECON-1": {"G1": "101", "G2": "7", "G3": "G1", "G4": "3", "G5": "2"},
}
_PRIMARY_VISIBILITY_BY_FRAME = {
    1: {
        "INT-1": ("G1", "G2"),
        "INT-2": ("G2", "G3"),
        "INT-3": ("G3", "G4"),
        "INT-4": ("G4", "G5"),
        "INT-5": ("G1",),
    },
    2: {
        "INT-1": ("G1", "G2"),
        "INT-2": ("G2", "G3"),
        "INT-3": ("G3",),  # G4 is temporarily outside this primary's view.
        "INT-4": ("G4", "G5"),
        "INT-5": ("G1",),
    },
    3: {
        "INT-1": ("G1", "G2"),
        "INT-2": ("G2", "G3"),
        "INT-3": ("G3", "G4"),
        "INT-4": ("G4", "G5"),
        "INT-5": ("G1", "G5"),  # G5 has only one gate pass on this stream.
    },
}
_WRONG_OFFLINE_TRUTH_ID = {
    "G1": "G5",
    "G2": "G1",
    "G3": "G2",
    "G4": "G3",
    "G5": "G4",
}


def _camera() -> CameraModel:
    return CameraModel(
        K=np.array(
            [
                [200.0, 0.0, 320.0],
                [0.0, 200.0, 240.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        R=np.eye(3),
        t=np.zeros(3),
        image_size=(640, 480),
        measurement_cov=np.diag([2.0, 2.0]),
    )


def _global_track(global_track_id: str) -> GlobalTrack:
    return GlobalTrack(
        global_track_id=global_track_id,
        position=np.array([_TARGET_X_M[global_track_id], 0.0, 40.0], dtype=float),
        covariance=np.diag([0.01, 0.01, 0.01]),
        category="uav",
        timestamp=1.0,
        track_version=9,
    )


def _local_track(
    resource_id: str,
    global_track_id: str,
    frame: int,
    *,
    detection_source: str,
    detector_backend: str,
    tracker_backend: str,
) -> LocalVisualTrack:
    u, v = _TARGET_CENTER_PX[global_track_id]
    return LocalVisualTrack(
        local_track_id=_LOCAL_ID_BY_RESOURCE_AND_TARGET[resource_id][global_track_id],
        center_px=np.array([u, v], dtype=float),
        bbox=(u - 6.0, v - 6.0, u + 6.0, v + 6.0),
        category="intruder",
        quality=0.96,
        mot_history_length=frame + 1,
        timestamp=float(frame),
        detection_source=detection_source,
        metadata={
            "detector_backend": detector_backend,
            "tracker_backend": tracker_backend,
            "native_mot_id": _LOCAL_ID_BY_RESOURCE_AND_TARGET[resource_id][
                global_track_id
            ],
        },
    )


def _batch(
    resource_id: str,
    target_ids: tuple[str, ...],
    frame: int,
    *,
    recon: bool = False,
    detection_source: str,
    detector_backend: str,
    tracker_backend: str,
) -> CameraLocalTrackBatch:
    local_tracks = tuple(
        _local_track(
            resource_id,
            global_track_id,
            frame,
            detection_source=detection_source,
            detector_backend=detector_backend,
            tracker_backend=tracker_backend,
        )
        for global_track_id in reversed(target_ids)
    )
    return CameraLocalTrackBatch(
        resource_id=resource_id,
        camera_id="recon_rgb" if recon else "front_rgb",
        camera=_camera(),
        local_tracks=local_tracks,
        frame_id=f"{resource_id}-frame-{frame}",
        timestamp=float(frame),
        arrival_timestamp=float(frame) + 0.02,
        source_node_id=resource_id,
        link_type="secondary_relay" if recon else "interceptor_peer",
        metadata={
            "camera_pose_source": "airsim_camera_pose",
            "actor_id": "ActorTruthMustRemainOffline",
            "object_id": "ObjectTruthMustRemainOffline",
            "global_track_id": "GLOBAL_METADATA_MUST_NOT_BIND",
            "truth_global_track_id_by_local_track_id": {
                _LOCAL_ID_BY_RESOURCE_AND_TARGET[resource_id][global_track_id]:
                _WRONG_OFFLINE_TRUTH_ID[global_track_id]
                for global_track_id in target_ids
            },
        },
    )


def _run_five_plus_one_scene(
    *,
    detection_source: str = "yolov8_intruder",
    detector_backend: str = "yolov8",
    tracker_backend: str = "bytetrack",
):
    global_tracks = tuple(
        _global_track(global_track_id) for global_track_id in _TARGET_X_M
    )
    bindings = tuple(
        GlobalTrackBinding(
            global_track_id=track.global_track_id,
            binding_source="d2_d3_current_binding",
            assignment_version=9,
        )
        for track in global_tracks
    )
    batches = []
    for frame, primary_visibility in _PRIMARY_VISIBILITY_BY_FRAME.items():
        batches.extend(
            _batch(
                resource_id,
                target_ids,
                frame,
                detection_source=detection_source,
                detector_backend=detector_backend,
                tracker_backend=tracker_backend,
            )
            for resource_id, target_ids in primary_visibility.items()
        )
        batches.append(
            _batch(
                "RECON-1",
                tuple(_TARGET_X_M),
                frame,
                recon=True,
                detection_source=detection_source,
                detector_backend=detector_backend,
                tracker_backend=tracker_backend,
            )
        )

    return register_local_visual_tracks_to_global_tracks(
        global_tracks=global_tracks,
        bindings=bindings,
        camera_batches=batches,
        current_time=None,
        max_binding_age_s=None,
        network_union_complete=True,
        stability_config=RegistrationStabilityConfig(
            window_frames=3,
            required_gate_passes=2,
        ),
    )


def _selected_candidates(result):
    return tuple(candidate for candidate in result.candidates if candidate.selected)


@pytest.mark.parametrize(
    ("detection_source", "detector_backend", "tracker_backend"),
    (
        ("airsim_builtin_detection", "airsim_detect", "airsim_builtin_tracklet"),
        ("yolov8_intruder", "yolov8", "bytetrack"),
    ),
)
def test_five_primary_partial_views_and_recon_full_view_use_geometric_hungarian_registration(
    detection_source: str,
    detector_backend: str,
    tracker_backend: str,
) -> None:
    result = _run_five_plus_one_scene(
        detection_source=detection_source,
        detector_backend=detector_backend,
        tracker_backend=tracker_backend,
    )
    selected = _selected_candidates(result)

    assert result.metadata["assignment_backends"] == ("scipy_hungarian",)
    assert result.metadata["registered_candidate_count"] == 42
    assert result.metadata["stable_registered_candidate_count"] == 27
    assert result.metadata["unstable_registered_candidate_count"] == 15
    assert result.metadata["global_track_count"] == 5
    assert result.metadata["global_binding_count"] == 5
    assert result.metadata["network_union_complete"] is True
    assert all(
        observation.local_track is None
        or (
            observation.local_track.detection_source == detection_source
            and observation.local_track.metadata["detector_backend"]
            == detector_backend
            and observation.local_track.metadata["tracker_backend"]
            == tracker_backend
        )
        for observation in result.observations
    )

    selected_by_frame_and_resource = defaultdict(list)
    for candidate in selected:
        selected_by_frame_and_resource[
            (int(candidate.timestamp), candidate.resource_id)
        ].append(candidate)
        expected_by_local_id = {
            local_id: global_track_id
            for global_track_id, local_id in _LOCAL_ID_BY_RESOURCE_AND_TARGET[
                candidate.resource_id
            ].items()
        }
        assert candidate.global_track_id == expected_by_local_id[
            candidate.local_track_id
        ]
        assert candidate.gate_passed is True
        assert np.isclose(candidate.mahalanobis_d2, 0.0, atol=1e-20)

    for frame, primary_visibility in _PRIMARY_VISIBILITY_BY_FRAME.items():
        for resource_id, target_ids in primary_visibility.items():
            frame_candidates = selected_by_frame_and_resource[(frame, resource_id)]
            assert {
                candidate.global_track_id for candidate in frame_candidates
            } == set(target_ids)
            assert len(
                {candidate.local_track_id for candidate in frame_candidates}
            ) == len(target_ids)
        recon_candidates = selected_by_frame_and_resource[(frame, "RECON-1")]
        assert {
            candidate.global_track_id for candidate in recon_candidates
        } == set(_TARGET_X_M)

    assert not any(
        candidate.resource_id == "INT-3"
        and candidate.timestamp == 2.0
        and candidate.global_track_id == "G4"
        for candidate in selected
    )

    bus = TerminalObservationBus()
    for observation in result.observations:
        bus.publish(observation)
    by_global_id = {
        association.global_track_id: association
        for association in bus.cross_view_associations()
    }
    assert set(by_global_id) == set(_TARGET_X_M)
    assert by_global_id["G4"].supporting_resource_ids == (
        "INT-3",
        "INT-4",
        "RECON-1",
    )
    assert by_global_id["G4"].reason == "multi_view_support"
    assert by_global_id["G4"].duplicate_terminal_lock_risk is False
    assert "INT-5/front_rgb:G5" in by_global_id["G1"].local_track_ids
    assert "RECON-1/recon_rgb:G1" in by_global_id["G3"].local_track_ids


def test_five_plus_one_stability_truth_isolation_and_local_mot_id_boundaries() -> None:
    result = _run_five_plus_one_scene()
    selected = _selected_candidates(result)

    recon_g1 = sorted(
        (
            candidate
            for candidate in selected
            if candidate.resource_id == "RECON-1"
            and candidate.global_track_id == "G1"
        ),
        key=lambda candidate: candidate.timestamp,
    )
    assert [
        candidate.stable_cross_view_support for candidate in recon_g1
    ] == [False, True, True]
    assert [candidate.stability_pass_count for candidate in recon_g1] == [1, 2, 3]

    temporarily_missing = sorted(
        (
            candidate
            for candidate in selected
            if candidate.resource_id == "INT-3"
            and candidate.global_track_id == "G4"
        ),
        key=lambda candidate: candidate.timestamp,
    )
    assert [candidate.timestamp for candidate in temporarily_missing] == [1.0, 3.0]
    assert [
        candidate.stable_cross_view_support for candidate in temporarily_missing
    ] == [False, True]
    assert [
        candidate.stability_pass_count for candidate in temporarily_missing
    ] == [1, 2]

    insufficient = [
        candidate
        for candidate in selected
        if candidate.resource_id == "INT-5" and candidate.global_track_id == "G5"
    ]
    assert len(insufficient) == 1
    assert insufficient[0].stability_pass_count == 1
    assert insufficient[0].stable_cross_view_support is False
    assert insufficient[0].decision_state == "candidate"
    assert insufficient[0].reject_reasons == ("stability_window_failed",)

    stable_by_global_id = {
        association.global_track_id: association
        for association in result.stable_cross_view_associations
    }
    assert set(stable_by_global_id["G4"].supporting_resource_ids) == {
        "INT-3",
        "INT-4",
        "RECON-1",
    }
    assert set(stable_by_global_id["G5"].supporting_resource_ids) == {
        "INT-4",
        "RECON-1",
    }
    assert "INT-5" not in stable_by_global_id["G5"].supporting_resource_ids

    wrong_local_id = next(
        candidate
        for candidate in selected
        if candidate.resource_id == "INT-5"
        and candidate.local_track_id == "G5"
        and candidate.timestamp == 3.0
    )
    assert wrong_local_id.global_track_id == "G1"
    assert wrong_local_id.offline_truth_global_id == "G5"

    wrong_recon_local_id = next(
        candidate
        for candidate in selected
        if candidate.resource_id == "RECON-1"
        and candidate.local_track_id == "G1"
        and candidate.timestamp == 3.0
    )
    assert wrong_recon_local_id.global_track_id == "G3"
    assert wrong_recon_local_id.offline_truth_global_id == "G2"

    assert all(
        candidate.global_track_id != candidate.offline_truth_global_id
        for candidate in selected
    )
    assert (
        result.metadata["global_id_policy"]
        == "existing_global_track_id_support_only"
    )
    assert result.metadata["truth_id_online_use"] == "ignored"
    assert result.metadata["truth_identity_used"] is False

    online_records = tuple(
        observation.to_runtime_record() for observation in result.observations
    )
    online_text = repr(online_records)
    assert "ActorTruthMustRemainOffline" not in online_text
    assert "ObjectTruthMustRemainOffline" not in online_text
    assert "GLOBAL_METADATA_MUST_NOT_BIND" not in online_text
    assert all(
        observation.terminal_association is None
        or observation.terminal_association.assigned_global_track_id in _TARGET_X_M
        for observation in result.observations
    )
    assert all(
        observation.terminal_association is None
        or observation.terminal_association.truth_identity_used is False
        for observation in result.observations
    )
