from __future__ import annotations

import numpy as np

from d5_terminal_association import (
    DistributedVisualObservation,
    TerminalCrossViewFusion,
    TerminalCrossViewFusionConfig,
)


def _observation(
    resource_id: str,
    local_track_id: str,
    bearing: tuple[float, float],
    *,
    timestamp: float = 10.0,
    camera_id: str = "front",
    assigned_global_track_id: str | None = None,
    assigned_global_track_stale: bool = False,
    category: str = "uav",
    confidence: float = 0.92,
    bbox_size: float = 20.0,
) -> DistributedVisualObservation:
    center = np.array([320.0 + bearing[0] * 100.0, 240.0 + bearing[1] * 100.0])
    half = bbox_size / 2.0
    return DistributedVisualObservation(
        resource_id=resource_id,
        camera_id=camera_id,
        frame_id=f"{resource_id}/{camera_id}",
        local_track_id=local_track_id,
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.02,
        center_px=center,
        bbox=(center[0] - half, center[1] - half, center[0] + half, center[1] + half),
        bearing=np.array(bearing),
        bearing_rate=np.array([0.01, 0.0]),
        covariance_px=np.diag([4.0, 4.0]),
        category=category,
        confidence=confidence,
        assigned_global_track_id=assigned_global_track_id,
        assigned_global_track_stale=assigned_global_track_stale,
    )


def _fusion() -> TerminalCrossViewFusion:
    return TerminalCrossViewFusion(TerminalCrossViewFusionConfig(max_measurement_time_skew_s=0.5))


def test_two_peers_build_supported_metadata_only_hypothesis_for_same_target() -> None:
    fusion = _fusion()
    observations = [
        _observation("UAV1", "L2", (0.12, 0.01)),
        _observation("UAV2", "R7", (0.125, 0.012), timestamp=10.05),
    ]

    hypotheses = fusion.build_hypotheses(observations=observations)
    associations = fusion.associate(observations=observations)

    assert len(hypotheses) == 1
    assert hypotheses[0].support_state == "supported"
    assert hypotheses[0].support_count == 2
    assert hypotheses[0].assigned_global_track_id is None
    assert associations[0].decision_state == "hypothesis_only"
    assert associations[0].supporting_resource_ids == ("UAV1", "UAV2")


def test_same_local_track_id_on_different_resources_is_namespaced_not_conflicted() -> None:
    fusion = _fusion()
    observations = [
        _observation("UAV1", "track_1", (0.2, 0.0)),
        _observation("UAV2", "track_1", (0.205, 0.002)),
    ]

    association = fusion.associate(observations=observations)[0]

    assert association.local_track_ids == ("UAV1/front:track_1", "UAV2/front:track_1")
    assert association.local_id_conflict is False
    assert association.decision_state == "hypothesis_only"


def test_missing_or_stale_global_track_id_cannot_lock() -> None:
    fusion = _fusion()
    missing = fusion.associate(
        observations=[
            _observation("UAV1", "L1", (0.1, 0.0)),
            _observation("UAV2", "L9", (0.105, 0.0)),
        ]
    )[0]
    stale = fusion.associate(
        observations=[
            _observation("UAV1", "L1", (0.1, 0.0), assigned_global_track_id="G2"),
            _observation("UAV2", "L9", (0.105, 0.0)),
        ],
        stale_assigned_global_track_ids=("G2",),
    )[0]

    assert missing.assigned_global_track_id is None
    assert missing.decision_state == "hypothesis_only"
    assert stale.assigned_global_track_id == "G2"
    assert stale.decision_state == "hold"
    assert stale.reason == "stale_assigned_global_track_id"


def test_duplicate_terminal_lock_risk_is_marked_and_blocks_locked_state() -> None:
    fusion = _fusion()
    association = fusion.associate(
        observations=[
            _observation("UAV1", "L1", (0.1, 0.0), assigned_global_track_id="G2"),
            _observation("UAV2", "L2", (0.104, 0.0), assigned_global_track_id="G2"),
        ],
        current_assigned_global_track_ids=("G2",),
    )[0]

    assert association.duplicate_terminal_lock_risk is True
    assert association.duplicate_lock_resource_ids == ("UAV1", "UAV2")
    assert association.decision_state == "hold"
    assert association.reason == "duplicate_terminal_lock_risk"


def test_single_view_target_is_kept_as_conservative_hypothesis() -> None:
    fusion = _fusion()
    association = fusion.associate(
        observations=[_observation("UAV1", "solo", (0.3, 0.0), assigned_global_track_id="G1")],
        current_assigned_global_track_ids=("G1",),
    )[0]

    assert association.supporting_resource_ids == ("UAV1",)
    assert association.decision_state == "hypothesis_only"
    assert association.reason == "single_view_support"
    assert association.duplicate_terminal_lock_risk is False


def test_n_peer_n_target_inputs_are_not_limited_to_2v2_or_5v5() -> None:
    fusion = _fusion()
    observations = []
    target_bearings = [(-0.4, 0.0), (0.0, 0.02), (0.42, -0.01)]
    for resource_index, resource_id in enumerate(("UAV1", "UAV2", "UAV3")):
        offset = resource_index * 0.004
        for target_index, bearing in enumerate(target_bearings):
            observations.append(
                _observation(
                    resource_id,
                    f"T{target_index}",
                    (bearing[0] + offset, bearing[1]),
                    timestamp=10.0 + resource_index * 0.03,
                    bbox_size=20.0 + target_index,
                )
            )

    associations = fusion.associate(observations=observations)
    multi_peer = [item for item in associations if len(item.supporting_resource_ids) == 3]

    assert len(multi_peer) == 3
    assert all(len(item.local_track_ids) == 3 for item in multi_peer)
    assert all(item.decision_state == "hypothesis_only" for item in multi_peer)
