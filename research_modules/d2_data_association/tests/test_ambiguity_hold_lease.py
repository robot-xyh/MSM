from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import numpy as np
import pytest

from d2_data_association import (
    D1_DEFAULT_PUBLISHER_EPOCH,
    D1_DEFAULT_PUBLISHER_NODE_ID,
    D1_STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION,
    D1_STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION,
    D1_STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION,
    D1_STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE,
    D1_STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE,
    D1_STRUCTURAL_AMBIGUITY_UPDATE_MODE,
    D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION,
    AmbiguityComponent3D,
    AmbiguityComponentValidationError,
    AmbiguityHoldLeaseConfig,
    Detection3D,
    IdentityCommitmentRecoveryConfig,
    ObservationClaimLedgerConfig,
    Scalable3DTracker,
    detections3d_from_d1_global_tracks,
    opaque_d1_member_track_token,
    opaque_d1_source_key,
    opaque_d1_source_track_id,
)


def _digest(prefix: str, value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return f"{prefix}{sha256(payload).hexdigest()}"


def _component_payload(
    member_ids: tuple[str, ...],
    observation_ids: tuple[str, ...],
    timestamp: float,
    generation: int,
    *,
    publisher_node_id: str = D1_DEFAULT_PUBLISHER_NODE_ID,
    publisher_epoch: str = D1_DEFAULT_PUBLISHER_EPOCH,
    arrival_timestamp: float | None = None,
    published_at: float | None = None,
) -> dict[str, object]:
    arrival = (
        timestamp + 0.01
        if arrival_timestamp is None
        else float(arrival_timestamp)
    )
    published = (
        timestamp + 0.02
        if published_at is None
        else float(published_at)
    )
    member_tokens = {
        member_id: opaque_d1_member_track_token(
            publisher_node_id,
            publisher_epoch,
            member_id,
        )
        for member_id in member_ids
    }
    observation_keys = {
        observation_id: _digest(
            "d1-observation-sha256:",
            [publisher_node_id, publisher_epoch, observation_id],
        )
        for observation_id in observation_ids
    }
    component_id = _digest(
        "d1-component-sha256:",
        [
            publisher_node_id,
            publisher_epoch,
            sorted(member_tokens.values()),
        ],
    )
    evidence_id = _digest(
        "d1-evidence-sha256:",
        [
            component_id,
            generation,
            timestamp,
            sorted(observation_keys.values()),
        ],
    )
    scan_id = _digest(
        "d1-scan-sha256:",
        [publisher_node_id, publisher_epoch, timestamp],
    )
    member_states = [
        {
            "opaque_member_track_token": member_tokens[member_id],
            "source_key": opaque_d1_source_key(
                publisher_node_id,
                publisher_epoch,
                member_id,
            ),
            "state": [
                float(index * 10),
                0.0,
                -100.0,
                1.0,
                0.0,
                0.0,
            ],
            "covariance": (np.eye(6, dtype=float) * 2.0).tolist(),
        }
        for index, member_id in enumerate(member_ids)
    ]
    observations = [
        {
            "observation_evidence_key": observation_keys[observation_id],
            "position_ned": [
                float(index * 10),
                0.0,
                -100.0,
            ],
            "covariance_ned": np.eye(3, dtype=float).tolist(),
            "radial_velocity_observed": True,
            "birth_deferred": len(observation_ids) > len(member_ids)
            and index >= len(member_ids),
            "velocity_evidence_used": False,
        }
        for index, observation_id in enumerate(observation_ids)
    ]
    candidate_edges = [
        {
            "opaque_member_track_token": member_tokens[member_id],
            "observation_evidence_key": observation_keys[observation_id],
            "nis": float(member_index + observation_index) * 0.1,
            "gate_threshold": 11.344866730144373,
            "edge_roles": ["maximum_matching_allowed"],
        }
        for member_index, member_id in enumerate(member_ids)
        for observation_index, observation_id in enumerate(observation_ids)
    ]
    cardinality = min(len(member_ids), len(observation_ids))
    return {
        "schema_version": D1_STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "component_id": component_id,
        "component_generation": generation,
        "publisher_node_id": publisher_node_id,
        "publisher_epoch": publisher_epoch,
        "member_token_rule": D1_STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE,
        "source_key_rule": D1_STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE,
        "measurement_timestamp": timestamp,
        "arrival_timestamp": arrival,
        "state_valid_timestamp": timestamp,
        "published_at": published,
        "sensor_id": "RADAR-TEST",
        "scan_id": scan_id,
        "frame_id": "NED",
        "member_states": member_states,
        "observations": observations,
        "candidate_edges": candidate_edges,
        "component_kinds": ["maximum_matching_allowed_edge_component"],
        "member_count": len(member_ids),
        "observation_count": len(observation_ids),
        "candidate_edge_count": len(candidate_edges),
        "free_row_count": len(member_ids) - cardinality,
        "free_column_count": len(observation_ids) - cardinality,
        "maximum_matching_cardinality": cardinality,
        "posterior_update_applied": False,
        "update_mode": D1_STRUCTURAL_AMBIGUITY_UPDATE_MODE,
        "birth_disposition": D1_STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION,
        "component_complete": True,
        "cross_covariance_available": False,
        "policy_version": D1_STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION,
    }


def _source_detection(
    local_track_id: str,
    timestamp: float,
    position_ned: tuple[float, float, float],
    *,
    detection_id: str | None = None,
    publisher_node_id: str = D1_DEFAULT_PUBLISHER_NODE_ID,
    publisher_epoch: str = D1_DEFAULT_PUBLISHER_EPOCH,
    observation_evidence_key: str | None = None,
) -> Detection3D:
    metadata: dict[str, object] = {}
    if observation_evidence_key is not None:
        metadata.update(
            {
                "observation_evidence_key": observation_evidence_key,
                "source_measurement_timestamp": timestamp,
                "latest_sensor_id": "RADAR-TEST",
            }
        )
    return Detection3D(
        detection_id=detection_id or f"detection-{local_track_id}-{timestamp:.3f}",
        measurement_timestamp=timestamp,
        arrival_timestamp=timestamp + 0.01,
        position_ned=np.asarray(position_ned, dtype=float),
        covariance=np.eye(3, dtype=float),
        velocity_ned=np.asarray([1.0, 0.0, 0.0], dtype=float),
        velocity_covariance=np.eye(3, dtype=float),
        source_node_id=publisher_node_id,
        source_track_id=opaque_d1_source_track_id(
            publisher_node_id,
            publisher_epoch,
            local_track_id,
        ),
        metadata=metadata,
    )


def _enabled_tracker(
    *,
    gap_seconds: float = 0.2,
    hard_seconds: float = 0.5,
    max_component_age_seconds: float = 1.0,
) -> Scalable3DTracker:
    return Scalable3DTracker(
        ambiguity_hold_config=AmbiguityHoldLeaseConfig(
            enabled=True,
            gap_seconds=gap_seconds,
            hard_seconds=hard_seconds,
            max_component_age_seconds=max_component_age_seconds,
        )
    )


def test_frozen_d1_opaque_source_contract_vector() -> None:
    token = opaque_d1_member_track_token(
        "D1_FUSION",
        "d1-default-epoch-v1",
        "D1-LOCAL-0007",
    )

    assert token == (
        "d1-track-sha256:"
        "27e6a4b881f841d1daa8419e4dca39e6c0705d5cc08170aae1ba8737fc85a34f"
    )
    assert opaque_d1_source_track_id(
        "D1_FUSION",
        "d1-default-epoch-v1",
        "D1-LOCAL-0007",
    ) == f"d1-default-epoch-v1::{token}"
    assert opaque_d1_source_key(
        "D1_FUSION",
        "d1-default-epoch-v1",
        "D1-LOCAL-0007",
    ) == f"D1_FUSION::d1-default-epoch-v1::{token}"


def test_d1_v1_payload_and_adapter_source_keys_align_exactly() -> None:
    payload = _component_payload(("D1-LOCAL-0007",), ("raw-obs-1",), 1.0, 1)
    component = AmbiguityComponent3D.from_mapping(payload)
    source = SimpleNamespace(
        global_track_id="D1-LOCAL-0007",
        state=np.asarray([1.0, 2.0, -3.0, 4.0, 5.0, 6.0]),
        covariance=np.eye(6, dtype=float),
        timestamp=1.0,
        metadata={"frame_id": "NED", "published_at": 1.0},
    )

    _, detections = detections3d_from_d1_global_tracks(
        [source],
        use_opaque_d1_source_tokens=True,
    )

    assert detections[0].source_key == component.member_source_keys[0]
    assert component.observations[0].observation_evidence_key.startswith(
        "d1-observation-sha256:"
    )
    assert "observation_id" not in component.to_dict()["observations"][0]
    assert "source_namespace" not in component.to_dict()["observations"][0]


def test_d1_adapter_opaque_source_mode_is_default_off_and_serially_equivalent() -> None:
    source = SimpleNamespace(
        global_track_id="UPSTREAM-RANDOM-LOCAL-ID",
        state=np.arange(6, dtype=float),
        covariance=np.eye(6, dtype=float),
        timestamp=2.0,
        metadata={
            "source_node_id": "legacy-node",
            "source_track_id": "legacy-local",
        },
    )

    baseline = detections3d_from_d1_global_tracks([source])[1][0]
    explicit_off = detections3d_from_d1_global_tracks(
        [source],
        use_opaque_d1_source_tokens=False,
        publisher_node_id="IGNORED-NODE",
        publisher_epoch="ignored-epoch",
    )[1][0]

    assert baseline.to_dict() == explicit_off.to_dict()
    assert baseline.source_key == "legacy-node::legacy-local"
    assert "source_publisher_epoch_defaulted" not in baseline.metadata


def test_enabled_adapter_hashes_random_upstream_identity_and_d2_owns_id() -> None:
    upstream = "RANDOM-UPSTREAM-TRUTH-LIKE-TARGET-0042"
    source = SimpleNamespace(
        global_track_id=upstream,
        state=np.asarray([10.0, 0.0, -100.0, 1.0, 0.0, 0.0]),
        covariance=np.eye(6, dtype=float),
        timestamp=0.0,
        metadata={},
    )

    _, detections = detections3d_from_d1_global_tracks(
        [source],
        use_opaque_d1_source_tokens=True,
    )
    result = Scalable3DTracker().step(detections)
    serialized = str(detections[0].to_dict())

    assert upstream not in serialized
    assert detections[0].metadata["upstream_identity_ignored"] is True
    assert detections[0].metadata["source_publisher_epoch_defaulted"] is True
    assert detections[0].metadata[
        "source_publisher_epoch_rotation_required_on_restart"
    ] is True
    assert detections[0].source_key == opaque_d1_source_key(
        D1_DEFAULT_PUBLISHER_NODE_ID,
        D1_DEFAULT_PUBLISHER_EPOCH,
        upstream,
    )
    canonical_id = result.metadata["detection_to_track"][
        detections[0].detection_id
    ]
    assert canonical_id == "GT3D-000001"
    assert upstream not in canonical_id
    assert result.metadata["truth_metrics_available"] is False


@pytest.mark.parametrize(
    ("member_count", "observation_count"),
    [(2, 2), (3, 2), (1, 3)],
)
def test_complete_component_shapes_enter_bounded_hold(
    member_count: int,
    observation_count: int,
) -> None:
    members = tuple(f"local-{index}" for index in range(member_count))
    observations = tuple(f"obs-{index}" for index in range(observation_count))
    payload = _component_payload(members, observations, 0.0, 1)
    tracker = _enabled_tracker()

    result = tracker.step([], 0.0, ambiguity_components=[payload])

    hold = result.metadata["ambiguity_hold"]
    assert hold["accepted_component_count"] == 1
    assert hold["active_component_count"] == 1
    assert hold["reserved_evidence_count"] == observation_count
    assert hold["hold_track_ids"] == []
    assert result.risk_summary is not None
    assert result.risk_summary.association_ambiguity == 1.0


def test_delayed_component_uses_bounded_age_and_d2_consumption_lease_clock() -> None:
    payload = _component_payload(
        ("local-a",),
        ("obs-a",),
        0.4,
        1,
        arrival_timestamp=0.65,
        published_at=0.65,
    )
    component = AmbiguityComponent3D.from_mapping(payload)
    serialized = component.to_dict()
    tracker = _enabled_tracker(max_component_age_seconds=0.5)

    accepted = tracker.step(
        [],
        0.65,
        ambiguity_components=[component],
    )
    hold = accepted.metadata["ambiguity_hold"]
    event = hold["component_events"][-1]
    lease = hold["active_leases"][0]

    assert hold["accepted_component_count"] == 1
    assert event["decision"] == "accepted"
    assert event["time_decision"] == "bounded_delayed_component_within_age"
    assert event["component_age_seconds"] == pytest.approx(0.25)
    assert event["measurement_timestamp"] == 0.4
    assert event["state_valid_timestamp"] == 0.4
    assert event["arrival_timestamp"] == 0.65
    assert event["published_at"] == 0.65
    assert event["d2_consumption_timestamp"] == 0.65
    assert lease["first_seen_timestamp"] == 0.65
    assert lease["last_new_evidence_timestamp"] == 0.65
    assert lease["soft_deadline"] == pytest.approx(0.85)
    assert lease["hard_deadline"] == pytest.approx(1.15)
    assert serialized["measurement_timestamp"] == 0.4
    assert serialized["state_valid_timestamp"] == 0.4
    assert serialized["arrival_timestamp"] == 0.65
    assert serialized["published_at"] == 0.65

    replay = tracker.step([], 0.70, ambiguity_components=[payload])

    replay_hold = replay.metadata["ambiguity_hold"]
    assert replay_hold["rejected_component_count"] == 1
    assert replay_hold["component_events"][-1]["reason"] == "evidence_replay"
    assert replay_hold["active_leases"][0]["soft_deadline"] == pytest.approx(
        0.85
    )


def test_future_component_is_rejected_without_creating_lease() -> None:
    payload = _component_payload(
        ("local-a",),
        ("obs-a",),
        0.70,
        1,
    )
    tracker = _enabled_tracker(max_component_age_seconds=0.5)

    result = tracker.step([], 0.65, ambiguity_components=[payload])

    hold = result.metadata["ambiguity_hold"]
    event = hold["component_events"][-1]
    assert hold["rejected_component_count"] == 1
    assert hold["active_component_count"] == 0
    assert event["reason"] == "component_from_future"
    assert event["time_decision"] == "future_state_valid_timestamp_rejected"
    assert event["component_age_seconds"] == pytest.approx(-0.05)
    assert event["lease_extended"] is False


def test_component_older_than_configured_age_is_rejected() -> None:
    payload = _component_payload(
        ("local-a",),
        ("obs-a",),
        0.40,
        1,
        arrival_timestamp=0.41,
        published_at=0.42,
    )
    tracker = _enabled_tracker(max_component_age_seconds=0.2)

    result = tracker.step([], 0.65, ambiguity_components=[payload])

    hold = result.metadata["ambiguity_hold"]
    event = hold["component_events"][-1]
    assert hold["rejected_component_count"] == 1
    assert hold["active_component_count"] == 0
    assert event["reason"] == "component_stale_age_exceeded"
    assert event["time_decision"] == "stale_component_age_rejected"
    assert event["component_age_seconds"] == pytest.approx(0.25)
    assert event["max_component_age_seconds"] == 0.2


def test_hold_preserves_canonical_track_and_only_predicts_covariance() -> None:
    tracker = _enabled_tracker()
    initial = _source_detection("local-a", 0.0, (0.0, 0.0, -100.0))
    first = tracker.step([initial])
    track_id = first.metadata["detection_to_track"][initial.detection_id]
    track = tracker.tracks[track_id]
    covariance_before = track.covariance.copy()
    hits_before = track.hits
    misses_before = track.misses
    confidence_before = track.identity_confidence
    payload = _component_payload(("local-a",), ("obs-a",), 0.1, 1)
    held_detection = _source_detection(
        "local-a",
        0.1,
        (50.0, 0.0, -100.0),
    )

    result = tracker.step(
        [held_detection],
        ambiguity_components=[payload],
    )
    held_track = tracker.tracks[track_id]

    assert held_track.global_track_id == track_id == "GT3D-000001"
    assert held_track.hits == hits_before
    assert held_track.misses == misses_before
    assert held_track.identity_confidence == confidence_before
    assert np.trace(held_track.covariance) >= np.trace(covariance_before)
    assert np.linalg.eigvalsh(held_track.covariance).min() >= -1.0e-9
    assert held_detection.detection_id not in result.metadata["detection_to_track"]
    assert result.metadata["ambiguity_hold"]["prevented_counts"] == {
        "birth": 0,
        "hit": 1,
        "miss": 1,
        "rebind": 0,
    }
    assert result.metadata["risk_level"] == "high"
    assert result.metadata["id_switch_count"] is None
    commitment = result.metadata["identity_commitment_by_track"][track_id]
    assert commitment["schema_version"] == (
        D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION
    )
    assert commitment["identity_commitment_state"] == (
        "identity_uncommitted_ambiguity_hold"
    )
    assert commitment["ambiguity_component_generation"] == 1
    assert commitment["active_lease_count"] == 1
    assert commitment["source_observation_evidence_key"] is None


def test_unbound_ambiguity_member_cannot_birth() -> None:
    tracker = _enabled_tracker()
    payload = _component_payload(("unbound-local",), ("obs-a",), 0.0, 1)
    detection = _source_detection(
        "unbound-local",
        0.0,
        (0.0, 0.0, -100.0),
    )

    result = tracker.step(
        [detection],
        ambiguity_components=[payload],
    )

    assert tracker.active_tracks() == []
    assert result.metadata["created_track_ids_by_detection"] == {}
    assert result.metadata["ambiguity_hold"]["prevented_counts"]["birth"] == 1


def test_replay_does_not_refresh_soft_lease_and_expiry_restores_miss() -> None:
    tracker = _enabled_tracker(gap_seconds=0.2, hard_seconds=0.5)
    initial = _source_detection("local-a", 0.0, (0.0, 0.0, -100.0))
    first = tracker.step([initial])
    track_id = first.metadata["detection_to_track"][initial.detection_id]
    payload = _component_payload(("local-a",), ("obs-a",), 0.1, 1)
    accepted = tracker.step([], 0.1, ambiguity_components=[payload])
    deadline = accepted.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ]

    replay = tracker.step([], 0.1, ambiguity_components=[payload])
    new_generation_without_new_observation = tracker.step(
        [],
        0.2,
        ambiguity_components=[
            _component_payload(("local-a",), ("obs-a",), 0.2, 2)
        ],
    )
    expired = tracker.step([], deadline + 0.01)

    assert replay.metadata["ambiguity_hold"]["rejected_component_count"] == 1
    assert replay.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ] == deadline
    assert new_generation_without_new_observation.metadata[
        "ambiguity_hold"
    ]["accepted_component_count"] == 1
    assert new_generation_without_new_observation.metadata[
        "ambiguity_hold"
    ]["component_events"][-1]["lease_extended"] is False
    assert new_generation_without_new_observation.metadata[
        "ambiguity_hold"
    ]["active_leases"][0]["soft_deadline"] == deadline
    assert expired.metadata["ambiguity_hold"]["expired_component_count"] == 1
    assert tracker.tracks[track_id].misses == 1
    assert expired.metadata["ambiguity_hold"]["reserved_evidence_count"] == 0
    commitment = expired.metadata["identity_commitment_by_track"][track_id]
    assert commitment["identity_commitment_state"] == (
        "identity_uncommitted_after_hold"
    )
    assert commitment["lease_expiration_reason"] == "soft_deadline_reached"
    assert commitment["source_observation_evidence_key"] is None


def test_after_hold_requires_fresh_original_observation_to_recommit() -> None:
    tracker = Scalable3DTracker(
        ambiguity_hold_config=AmbiguityHoldLeaseConfig(
            enabled=True,
            gap_seconds=0.2,
            hard_seconds=0.5,
        ),
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=0.1,
            max_lateness_seconds=0.1,
        ),
    )
    initial_key = _digest(
        "d1-observation-sha256:",
        ["initial", "local-a"],
    )
    initial = _source_detection(
        "local-a",
        0.0,
        (0.0, 0.0, -100.0),
        observation_evidence_key=initial_key,
    )
    first = tracker.step([initial])
    track_id = first.metadata["detection_to_track"][initial.detection_id]
    confirm_key = _digest(
        "d1-observation-sha256:",
        ["confirm", "local-a"],
    )
    tracker.step(
        [
            _source_detection(
                "local-a",
                0.05,
                (0.05, 0.0, -100.0),
                observation_evidence_key=confirm_key,
            )
        ]
    )
    payload = _component_payload(("local-a",), ("held-obs",), 0.1, 1)
    held = tracker.step([], 0.1, ambiguity_components=[payload])
    deadline = held.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ]
    expired = tracker.step([], deadline + 0.01)

    assert expired.metadata["identity_commitment_by_track"][track_id][
        "identity_commitment_state"
    ] == "identity_uncommitted_after_hold"

    replay = _source_detection(
        "local-a",
        deadline + 0.02,
        (0.1, 0.0, -100.0),
        observation_evidence_key=initial_key,
    )
    replay.metadata["source_measurement_timestamp"] = 0.0
    replay_result = tracker.step([replay])
    assert replay_result.metadata["identity_commitment_by_track"][track_id][
        "identity_commitment_state"
    ] == "identity_uncommitted_after_hold"

    old_key = _digest(
        "d1-observation-sha256:",
        ["old-unique", "local-a"],
    )
    old = _source_detection(
        "local-a",
        deadline + 0.025,
        (0.15, 0.0, -100.0),
        observation_evidence_key=old_key,
    )
    old.metadata["source_measurement_timestamp"] = 0.0
    old_result = tracker.step([old])
    assert old_result.metadata["replay_quarantine_events"][0]["reason"] == (
        "observation_measurement_too_old"
    )
    assert old_result.metadata["identity_commitment_by_track"][track_id][
        "identity_commitment_state"
    ] == "identity_uncommitted_after_hold"

    false_alarm_key = _digest(
        "d1-observation-sha256:",
        ["known-false-alarm", "local-a"],
    )
    false_alarm = _source_detection(
        "local-a",
        deadline + 0.03,
        (0.2, 0.0, -100.0),
        observation_evidence_key=false_alarm_key,
    )
    false_alarm.metadata["identity_evidence_disposition"] = (
        "known_false_alarm"
    )
    false_alarm_result = tracker.step([false_alarm])
    assert false_alarm_result.metadata["identity_commitment_by_track"][
        track_id
    ]["identity_commitment_state"] == "identity_uncommitted_after_hold"
    assert false_alarm_result.metadata[
        "identity_commitment_blocked_recovery_counts_cumulative"
    ]["known_false_alarm"] == 1

    fresh_key = _digest(
        "d1-observation-sha256:",
        ["fresh", "local-a"],
    )
    fresh = _source_detection(
        "local-a",
        deadline + 0.04,
        (0.3, 0.0, -100.0),
        observation_evidence_key=fresh_key,
    )
    recovered = tracker.step([fresh])
    commitment = recovered.metadata["identity_commitment_by_track"][track_id]
    assert commitment["identity_commitment_state"] == "committed"
    assert commitment["reason"] == "fresh_original_observation_accepted"
    assert commitment["source_observation_evidence_key"] == fresh_key
    assert commitment["source_observation_evidence_generation"] == 0


def test_released_hold_candidate_key_cannot_recommit_until_newer_key_arrives() -> None:
    tracker = Scalable3DTracker(
        ambiguity_hold_config=AmbiguityHoldLeaseConfig(
            enabled=True,
            gap_seconds=0.2,
            hard_seconds=0.5,
        ),
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=1.0,
            max_lateness_seconds=1.0,
        ),
        lost_miss_threshold=10,
        drop_miss_threshold=20,
        tentative_drop_miss_threshold=10,
    )
    initial = _source_detection(
        "local-a",
        0.0,
        (0.0, 0.0, -100.0),
        observation_evidence_key=_digest(
            "d1-observation-sha256:",
            ["recovery-barrier-initial"],
        ),
    )
    first = tracker.step([initial])
    track_id = first.metadata["detection_to_track"][initial.detection_id]
    tracker.step(
        [
            _source_detection(
                "local-a",
                0.05,
                (0.05, 0.0, -100.0),
                observation_evidence_key=_digest(
                    "d1-observation-sha256:",
                    ["recovery-barrier-confirm"],
                ),
            )
        ]
    )

    payload = _component_payload(
        ("local-a",),
        ("held-candidate",),
        0.1,
        1,
    )
    old_candidate_key = str(
        payload["observations"][0]["observation_evidence_key"]
    )
    held = tracker.step([], 0.1, ambiguity_components=[payload])
    held_commitment = held.metadata["identity_commitment_by_track"][track_id]
    assert held_commitment["recovery_blocker_count"] == 1
    assert held_commitment[
        "recovery_not_before_measurement_timestamp"
    ] == pytest.approx(0.1)
    deadline = held.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ]
    expired = tracker.step([], deadline + 0.01)
    assert expired.metadata["ambiguity_hold"]["reserved_evidence_count"] == 0

    old_candidate = _source_detection(
        "local-a",
        deadline + 0.02,
        (0.1, 0.0, -100.0),
        observation_evidence_key=old_candidate_key,
    )
    old_candidate.metadata["source_measurement_timestamp"] = 0.1
    old_result = tracker.step([old_candidate])
    assert old_result.metadata["fresh_detection_count"] == 1
    assert old_result.metadata[
        "identity_commitment_suppressed_association_reason_counts"
    ] == {"blocked_ambiguity_evidence_key": 1}
    assert old_candidate.detection_id not in old_result.metadata[
        "detection_to_track"
    ]
    old_commitment = old_result.metadata[
        "identity_commitment_by_track"
    ][track_id]
    assert old_commitment["identity_commitment_state"] == (
        "identity_uncommitted_after_hold"
    )
    assert old_commitment["source_observation_evidence_key"] is None

    same_time_key = _digest(
        "d1-observation-sha256:",
        ["different-key-same-ambiguity-time"],
    )
    same_time = _source_detection(
        "local-a",
        deadline + 0.03,
        (0.15, 0.0, -100.0),
        observation_evidence_key=same_time_key,
    )
    same_time.metadata["source_measurement_timestamp"] = 0.1
    same_time_result = tracker.step([same_time])
    assert same_time_result.metadata[
        "identity_commitment_suppressed_association_reason_counts"
    ] == {"source_measurement_not_after_ambiguity_watermark": 1}
    assert same_time_result.metadata["identity_commitment_by_track"][track_id][
        "identity_commitment_state"
    ] == "identity_uncommitted_after_hold"

    future_key = _digest(
        "d1-observation-sha256:",
        ["different-key-future-source-time"],
    )
    future = _source_detection(
        "local-a",
        deadline + 0.035,
        (0.18, 0.0, -100.0),
        observation_evidence_key=future_key,
    )
    future.metadata["source_measurement_timestamp"] = deadline + 1.0
    future_result = tracker.step([future])
    assert future_result.metadata[
        "identity_commitment_suppressed_association_reason_counts"
    ] == {"source_measurement_timestamp_from_future": 1}
    assert future_result.metadata["identity_commitment_by_track"][track_id][
        "identity_commitment_state"
    ] == "identity_uncommitted_after_hold"

    newer_key = _digest(
        "d1-observation-sha256:",
        ["different-key-after-ambiguity-time"],
    )
    newer = _source_detection(
        "local-a",
        deadline + 0.04,
        (0.2, 0.0, -100.0),
        observation_evidence_key=newer_key,
    )
    newer.metadata["source_measurement_timestamp"] = 0.11
    recovered = tracker.step([newer])
    commitment = recovered.metadata["identity_commitment_by_track"][track_id]
    assert commitment["identity_commitment_state"] == "committed"
    assert commitment["source_observation_evidence_key"] == newer_key
    assert commitment["recovery_blocker_count"] == 0
    assert commitment["recovery_not_before_measurement_timestamp"] is None
    assert commitment["recovery_blocker_overflow"] is False
    assert recovered.metadata["identity_commitment_recovery_barrier"][
        "stored_blocked_key_count"
    ] == 0


def test_identity_recovery_blocker_capacity_overflow_stays_fail_closed() -> None:
    tracker = Scalable3DTracker(
        ambiguity_hold_config=AmbiguityHoldLeaseConfig(
            enabled=True,
            gap_seconds=0.1,
            hard_seconds=0.2,
        ),
        identity_commitment_recovery_config=(
            IdentityCommitmentRecoveryConfig(
                max_blocked_keys_per_track=1,
                max_total_blocked_keys=2,
            )
        ),
        lost_miss_threshold=10,
        drop_miss_threshold=20,
        tentative_drop_miss_threshold=10,
    )
    initial = _source_detection("local-a", 0.0, (0.0, 0.0, -100.0))
    first = tracker.step([initial])
    track_id = first.metadata["detection_to_track"][initial.detection_id]
    payload = _component_payload(
        ("local-a",),
        ("held-a", "held-b"),
        0.1,
        1,
    )
    held = tracker.step([], 0.1, ambiguity_components=[payload])
    held_commitment = held.metadata["identity_commitment_by_track"][track_id]
    assert held_commitment["recovery_blocker_count"] == 1
    assert held_commitment["recovery_blocker_overflow"] is True
    deadline = held.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ]
    tracker.step([], deadline + 0.01)

    future = _source_detection(
        "local-a",
        deadline + 0.02,
        (0.1, 0.0, -100.0),
        observation_evidence_key=_digest(
            "d1-observation-sha256:",
            ["capacity-overflow-future"],
        ),
    )
    result = tracker.step([future])

    assert result.metadata[
        "identity_commitment_suppressed_association_reason_counts"
    ] == {"identity_recovery_blocker_capacity_overflow": 1}
    assert result.metadata["identity_commitment_by_track"][track_id][
        "identity_commitment_state"
    ] == "identity_uncommitted_after_hold"
    assert result.metadata["identity_commitment_recovery_barrier"][
        "overflow_track_count"
    ] == 1


def test_future_source_timestamp_cannot_create_a_normal_track() -> None:
    tracker = Scalable3DTracker()
    detection = _source_detection(
        "local-a",
        0.1,
        (0.0, 0.0, -100.0),
        observation_evidence_key=_digest(
            "d1-observation-sha256:",
            ["future-source-birth"],
        ),
    )
    detection.metadata["source_measurement_timestamp"] = 0.2

    result = tracker.step([detection])

    assert tracker.active_tracks() == []
    assert result.metadata["detection_to_track"] == {}
    assert result.metadata["identity_commitment_suppressed_births"] == {
        detection.detection_id: "source_measurement_timestamp_from_future"
    }


def test_identity_commitment_normal_path_and_dynamic_size_do_not_regress() -> None:
    target_count = 37
    tracker = Scalable3DTracker()
    detections = [
        _source_detection(
            f"local-{index}",
            0.0,
            (float(index * 20), 0.0, -100.0),
            observation_evidence_key=_digest(
                "d1-observation-sha256:",
                ["normal", index],
            ),
        )
        for index in range(target_count)
    ]

    result = tracker.step(detections)

    commitments = result.metadata["identity_commitment_by_track"]
    assert len(commitments) == target_count
    assert set(
        item["identity_commitment_state"] for item in commitments.values()
    ) == {"committed"}
    assert set(
        item["association_state"] for item in commitments.values()
    ) == {"created"}


def test_new_raw_evidence_extends_only_to_hard_deadline() -> None:
    tracker = _enabled_tracker(gap_seconds=0.2, hard_seconds=0.5)
    tracker.step(
        [_source_detection("local-a", 0.0, (0.0, 0.0, -100.0))]
    )
    first = tracker.step(
        [],
        0.1,
        ambiguity_components=[
            _component_payload(("local-a",), ("obs-1",), 0.1, 1)
        ],
    )
    hard_deadline = first.metadata["ambiguity_hold"]["active_leases"][0][
        "hard_deadline"
    ]
    second = tracker.step(
        [],
        0.25,
        ambiguity_components=[
            _component_payload(("local-a",), ("obs-2",), 0.25, 2)
        ],
    )
    third = tracker.step(
        [],
        0.44,
        ambiguity_components=[
            _component_payload(("local-a",), ("obs-3",), 0.44, 3)
        ],
    )

    assert second.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ] == pytest.approx(0.45)
    assert third.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ] == pytest.approx(hard_deadline)
    expired = tracker.step([], hard_deadline + 0.01)
    assert expired.metadata["ambiguity_hold"]["expired_component_count"] == 1
    exhausted = tracker.step(
        [],
        hard_deadline + 0.01,
        ambiguity_components=[
            _component_payload(
                ("local-a",),
                ("obs-4",),
                hard_deadline + 0.01,
                4,
            )
        ],
    )
    assert exhausted.metadata["ambiguity_hold"]["rejected_component_count"] == 1
    assert exhausted.metadata["ambiguity_hold"]["component_events"][-1][
        "reason"
    ] == "component_hard_cap_exhausted"


def test_source_binding_is_hard_masked_before_update_and_shadow_birth() -> None:
    tracker = Scalable3DTracker(process_noise_acceleration=0.0)
    first_a = _source_detection("local-a", 0.0, (0.0, 0.0, -100.0))
    first_b = _source_detection("local-b", 0.0, (10.0, 0.0, -100.0))
    first_a.covariance = np.diag([0.01, 100.0, 1.0])
    first_b.covariance = np.diag([0.01, 100.0, 1.0])
    tracker.step([first_a, first_b])
    state_before = {
        track_id: track.state.copy() for track_id, track in tracker.tracks.items()
    }
    swapped_a = _source_detection("local-a", 0.0, (10.0, 0.0, -100.0))
    swapped_b = _source_detection("local-b", 0.0, (0.0, 0.0, -100.0))
    swapped_a.covariance = np.diag([0.01, 100.0, 1.0])
    swapped_b.covariance = np.diag([0.01, 100.0, 1.0])

    result = tracker.step([swapped_a, swapped_b], 0.0)

    assert result.matched_pairs == []
    assert result.metadata["binding_pre_update_rejection_count"] == 2
    assert len(result.metadata["binding_suppressed_births"]) == 2
    assert len(tracker.tracks) == 2
    assert all(track.misses == 1 for track in tracker.tracks.values())
    assert all(
        np.array_equal(track.state, state_before[track_id])
        for track_id, track in tracker.tracks.items()
    )


def test_legal_existing_source_binding_still_updates_original_track() -> None:
    tracker = Scalable3DTracker()
    initial = _source_detection("local-a", 0.0, (0.0, 0.0, -100.0))
    first = tracker.step([initial])
    track_id = first.metadata["detection_to_track"][initial.detection_id]
    follow_up = _source_detection("local-a", 0.1, (0.1, 0.0, -100.0))

    result = tracker.step([follow_up])

    assert result.metadata["detection_to_track"][follow_up.detection_id] == track_id
    assert result.metadata["binding_pre_update_rejection_count"] == 0
    assert tracker.tracks[track_id].hits == 2


def test_default_disabled_tracker_ignores_sidecar_and_matches_baseline() -> None:
    baseline = Scalable3DTracker()
    candidate = Scalable3DTracker()
    initial_baseline = _source_detection(
        "local-a",
        0.0,
        (0.0, 0.0, -100.0),
    )
    initial_candidate = _source_detection(
        "local-a",
        0.0,
        (0.0, 0.0, -100.0),
    )
    baseline.step([initial_baseline])
    candidate.step([initial_candidate])
    next_baseline = _source_detection(
        "local-a",
        0.1,
        (0.1, 0.0, -100.0),
    )
    next_candidate = _source_detection(
        "local-a",
        0.1,
        (0.1, 0.0, -100.0),
    )
    payload = _component_payload(("local-a",), ("obs-a",), 0.1, 1)

    baseline_result = baseline.step([next_baseline])
    candidate_result = candidate.step(
        [next_candidate],
        ambiguity_components=[payload],
    )

    assert candidate_result.metadata["ambiguity_hold"]["enabled"] is False
    assert candidate_result.metadata["ambiguity_hold"][
        "ignored_component_count"
    ] == 1
    assert candidate_result.matched_pairs == baseline_result.matched_pairs
    assert (
        candidate.tracks["GT3D-000001"].to_dict()
        == baseline.tracks["GT3D-000001"].to_dict()
    )


def test_bad_component_never_extends_active_lease() -> None:
    tracker = _enabled_tracker(gap_seconds=0.2, hard_seconds=0.5)
    tracker.step(
        [_source_detection("local-a", 0.0, (0.0, 0.0, -100.0))]
    )
    accepted = tracker.step(
        [],
        0.1,
        ambiguity_components=[
            _component_payload(("local-a",), ("obs-1",), 0.1, 1)
        ],
    )
    deadline = accepted.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ]
    malformed = _component_payload(("local-a",), ("obs-2",), 0.2, 2)
    malformed["posterior_update_applied"] = True

    rejected = tracker.step([], 0.2, ambiguity_components=[malformed])
    expired = tracker.step([], deadline + 0.01)

    assert rejected.metadata["ambiguity_hold"]["rejected_component_count"] == 1
    assert rejected.metadata["ambiguity_hold"]["active_leases"][0][
        "soft_deadline"
    ] == deadline
    assert expired.metadata["ambiguity_hold"]["expired_component_count"] == 1


def test_truth_key_and_missing_covariance_fail_closed() -> None:
    payload = _component_payload(("local-a",), ("obs-a",), 0.0, 1)
    truth_payload = deepcopy(payload)
    truth_payload["truth_id"] = "forbidden"
    missing_covariance = deepcopy(payload)
    del missing_covariance["member_states"][0]["covariance"]
    missing_publisher_epoch = deepcopy(payload)
    del missing_publisher_epoch["publisher_epoch"]

    with pytest.raises(AmbiguityComponentValidationError):
        AmbiguityComponent3D.from_mapping(truth_payload)
    with pytest.raises(AmbiguityComponentValidationError):
        AmbiguityComponent3D.from_mapping(missing_covariance)
    with pytest.raises(AmbiguityComponentValidationError):
        AmbiguityComponent3D.from_mapping(missing_publisher_epoch)

    tracker = _enabled_tracker()
    result = tracker.step(
        [],
        0.0,
        ambiguity_components=[
            truth_payload,
            missing_covariance,
            missing_publisher_epoch,
        ],
    )
    assert result.metadata["ambiguity_hold"]["rejected_component_count"] == 3
    assert result.metadata["ambiguity_hold"]["active_component_count"] == 0


def test_opaque_observation_reservation_blocks_anonymous_rebirth() -> None:
    tracker = _enabled_tracker()
    payload = _component_payload(("unbound-local",), ("obs-a",), 0.0, 1)
    observation_key = payload["observations"][0][
        "observation_evidence_key"
    ]
    detection = Detection3D(
        detection_id="anonymous-component-observation",
        measurement_timestamp=0.0,
        arrival_timestamp=0.01,
        position_ned=np.asarray([0.0, 0.0, -100.0]),
        covariance=np.eye(3, dtype=float),
        metadata={
            "observation_evidence_key": observation_key,
            "source_measurement_timestamp": 0.0,
            "latest_sensor_id": "RADAR-TEST",
        },
    )

    result = tracker.step(
        [detection],
        ambiguity_components=[payload],
    )

    assert tracker.active_tracks() == []
    assert result.metadata["replay_quarantined_detection_count"] == 1
    assert result.metadata["replay_quarantine_events"][0]["reason"] == (
        "observation_reserved_ambiguous"
    )
    assert result.metadata["observation_claim_ledger"][
        "claim_status_counts"
    ]["reserved_ambiguous"] == 1


def test_incompatible_components_cannot_reserve_same_opaque_evidence() -> None:
    first = _component_payload(("local-a",), ("shared-observation",), 0.0, 1)
    second = _component_payload(("local-b",), ("shared-observation",), 0.0, 1)
    tracker = _enabled_tracker()

    result = tracker.step(
        [],
        0.0,
        ambiguity_components=[first, second],
    )

    hold = result.metadata["ambiguity_hold"]
    assert hold["accepted_component_count"] == 1
    assert hold["rejected_component_count"] == 1
    assert hold["reserved_evidence_count"] == 1
    assert hold["component_events"][-1]["reason"] == (
        "observation_reserved_by_incompatible_component"
    )


def test_publisher_epoch_rotation_rejects_return_to_retired_epoch() -> None:
    tracker = _enabled_tracker()
    first = _component_payload(
        ("local-a",),
        ("obs-1",),
        0.0,
        1,
        publisher_epoch="epoch-1",
    )
    second = _component_payload(
        ("local-a",),
        ("obs-2",),
        0.1,
        1,
        publisher_epoch="epoch-2",
    )
    rollback = _component_payload(
        ("local-a",),
        ("obs-3",),
        0.2,
        2,
        publisher_epoch="epoch-1",
    )

    tracker.step([], 0.0, ambiguity_components=[first])
    rotated = tracker.step([], 0.1, ambiguity_components=[second])
    rejected = tracker.step([], 0.2, ambiguity_components=[rollback])

    assert rotated.metadata["ambiguity_hold"]["expired_component_count"] == 1
    assert rotated.metadata["ambiguity_hold"]["accepted_component_count"] == 1
    assert rejected.metadata["ambiguity_hold"]["rejected_component_count"] == 1
    assert rejected.metadata["ambiguity_hold"]["component_events"][-1][
        "reason"
    ] == "publisher_epoch_rollback"
