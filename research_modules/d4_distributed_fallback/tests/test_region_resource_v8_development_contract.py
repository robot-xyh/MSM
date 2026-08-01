from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource_v8_development_contract import (
    RegionResourceV8DataUnavailableError,
    RegionResourceV8ValidationError,
    V8AnonymousRawActorAction,
    V8AnonymousTransferCandidate,
    V8DirectedEdgeState,
    V8NoAuthorityPermissions,
    V8OfflineTransferLabel,
    V8OnlineRegionResourceFrame,
    V8R0ActionTuple,
    V8R0RegionAction,
    V8RegionResourceState,
    V8RequestScheduleEntry,
    V8Transfer,
    V8TransferClass,
    canonical_v8_json_line,
    canonical_v8_sha256,
    expected_v8_directed_edges,
    load_v8_episode_pair,
    validate_v8_data_request_payload,
    validate_v8_pre_generation_readiness,
    validate_v8_seed_registry_payload,
)


_MODULE_ROOT = Path(__file__).resolve().parents[1]
_REQUEST_ROOT = (
    _MODULE_ROOT
    / "reports"
    / "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)
_REQUEST_PATH = _REQUEST_ROOT / "v8_development_data_request.json"
_REGISTRY_PATH = _REQUEST_ROOT / "v8_development_seed_registry.json"


def _permissions() -> V8NoAuthorityPermissions:
    return V8NoAuthorityPermissions()


def _regions(*, lease_expires_at_s: float = 10.0) -> tuple[V8RegionResourceState, ...]:
    result = []
    for index in range(8):
        if index == 0:
            available, committed, reserved, required = 10, 1, 1, 2
        elif index == 1:
            available, committed, reserved, required = 2, 0, 0, 4
        else:
            available, committed, reserved, required = 5, 0, 1, 3
        result.append(
            V8RegionResourceState(
                region_index=index,
                region_id=f"region-{index}",
                supply_available=available,
                supply_committed=committed,
                supply_reserved=reserved,
                demand_required=required,
                demand_weighted=float(required),
                supply_demand_gap=available - committed - reserved - required,
                owner_id="Center_1",
                owner_layer="center",
                plan_id="plan-v1",
                plan_version=1,
                epoch=1,
                lease_expires_at_s=lease_expires_at_s,
                coalition_ack_complete=True,
                owner_active=True,
                fault_fenced=False,
            )
        )
    return tuple(result)


def _edges() -> tuple[V8DirectedEdgeState, ...]:
    return tuple(
        V8DirectedEdgeState(
            edge_index=edge_index,
            source_region_index=source,
            target_region_index=target,
            transfer_capacity=3,
            communication_latency_s=0.01,
            communication_loss_rate=0.0,
            communication_partition_state="connected",
            communication_available=True,
            maneuver_available=True,
        )
        for edge_index, (source, target) in enumerate(
            expected_v8_directed_edges("directed_ring_8")
        )
    )


def _frame(
    *,
    seed: int = 28100,
    episode_id: str = "v8-train-28100",
    projected: bool = True,
) -> V8OnlineRegionResourceFrame:
    pairs = expected_v8_directed_edges("directed_ring_8")
    edge_index = pairs.index((0, 1))
    candidate = V8AnonymousTransferCandidate(
        candidate_index=0,
        edge_index=edge_index,
        source_region_index=0,
        target_region_index=1,
        resource_count=1,
        activation_score=0.9,
    )
    transfer = V8Transfer(
        edge_index=edge_index,
        source_region_index=0,
        target_region_index=1,
        resource_count=1,
    )
    return V8OnlineRegionResourceFrame(
        frame_id=f"{episode_id}:0",
        episode_id=episode_id,
        seed=seed,
        split="train",
        frame_index=0,
        measurement_timestamp=0.9,
        arrival_timestamp=1.0,
        topology_id="directed_ring_8",
        region_count=8,
        regions=_regions(),
        directed_edges=_edges(),
        r0_action_tuple=V8R0ActionTuple(
            region_actions=tuple(
                V8R0RegionAction(
                    region_index=index,
                    resource_quota_delta=0,
                    reserve_ratio=0.2,
                    reconnaissance_priority=0.5,
                    hold=False,
                    request_replan=False,
                )
                for index in range(8)
            ),
            transfers=(),
        ),
        raw_actor=V8AnonymousRawActorAction(
            activated=True,
            anonymous_candidates=(candidate,),
        ),
        projected_transfers=(transfer,) if projected else (),
        projection_rejection_reasons=(
            () if projected else ("insufficient_source_surplus",)
        ),
        invariant_failure_reasons=(),
        permissions=_permissions(),
    )


def _label(
    frame: V8OnlineRegionResourceFrame,
    *,
    target_class: V8TransferClass = V8TransferClass.SAFE_FORWARD,
) -> V8OfflineTransferLabel:
    hard_negative = target_class == V8TransferClass.HARD_NO_TRANSFER
    return V8OfflineTransferLabel(
        frame_id=frame.frame_id,
        episode_id=frame.episode_id,
        seed=frame.seed,
        split="train",
        frame_index=frame.frame_index,
        online_frame_sha256=frame.content_sha256,
        target_class=target_class,
        expected_projected_transfers=(
            () if hard_negative else frame.projected_transfers
        ),
        positive_transfer_resource_count=0 if hard_negative else 1,
        hard_negative_candidate_resource_count=1 if hard_negative else 0,
        hard_negative_reasons=(
            ("insufficient_source_surplus",) if hard_negative else ()
        ),
        label_source="same_snapshot_r0_deterministic_projection",
    )


def _write_pair(
    root: Path,
    frame: V8OnlineRegionResourceFrame,
    label: V8OfflineTransferLabel,
) -> tuple[Path, Path]:
    online_path = root / "online.jsonl"
    offline_path = root / "offline.jsonl"
    online_path.write_bytes(canonical_v8_json_line(frame.to_dict()))
    offline_path.write_bytes(canonical_v8_json_line(label.to_dict()))
    return online_path, offline_path


def _schedule_entry(
    *,
    seed: int = 28100,
    target_class: V8TransferClass = V8TransferClass.SAFE_FORWARD,
) -> V8RequestScheduleEntry:
    hard_negative = target_class == V8TransferClass.HARD_NO_TRANSFER
    return V8RequestScheduleEntry(
        seed=seed,
        split="train",
        topology_id="directed_ring_8",
        region_count=8,
        supply_demand_condition="source_surplus_target_deficit",
        communication_condition="nominal",
        requested_target_class=target_class,
        requested_transfer_resource_count=0 if hard_negative else 1,
        hard_negative_candidate_resource_count=1 if hard_negative else 0,
        replicate=0,
    )


def _recompute_content_sha256(payload: dict[str, object]) -> None:
    content = dict(payload)
    content.pop("content_sha256", None)
    payload["content_sha256"] = canonical_v8_sha256(content)


def test_frozen_request_readiness_is_contract_ready_but_data_and_model_absent() -> None:
    readiness = validate_v8_pre_generation_readiness(
        _REQUEST_PATH,
        _REGISTRY_PATH,
    )
    assert readiness.status == "frozen_request_not_generated"
    assert readiness.contract_ready is True
    assert readiness.requested_cell_count == 108
    assert readiness.requested_replicates_per_cell == 3
    assert readiness.requested_seed_count == 324
    assert readiness.requested_seed_range == (28100, 28423)
    assert readiness.generated_episode_count == 0
    assert readiness.loaded_episode_count == 0
    assert readiness.data_available is False
    assert readiness.model_available is False
    assert readiness.validation_seed_allocation == ()
    assert readiness.test_seed_allocation == ()
    assert set(readiness.blockers) == {
        "complete_main_generation_schedule_absent",
        "generated_episode_manifest_absent",
    }
    assert not any(readiness.permissions.to_dict()[name] for name in (
        "assignment",
        "degradation",
        "takeover",
        "coalition",
        "control",
    ))


def test_registry_strictly_covers_108_cells_three_replicates_and_four_topologies() -> None:
    payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    schedule = validate_v8_seed_registry_payload(payload)
    assert len(schedule) == 324
    cells: dict[tuple[str, str, str, str], set[int]] = {}
    for item in schedule:
        cells.setdefault(item.cell_key, set()).add(item.replicate)
    assert len(cells) == 108
    assert set(map(frozenset, cells.values())) == {frozenset({0, 1, 2})}
    assert {item.region_count for item in schedule} == {8, 9, 12, 16}
    assert {item.requested_target_class.value for item in schedule} == {
        "safe_forward_transfer",
        "safe_reverse_transfer",
        "hard_no_transfer_negative",
    }
    assert {item.requested_transfer_resource_count for item in schedule} == {
        0,
        1,
        2,
        3,
    }
    assert {item.hard_negative_candidate_resource_count for item in schedule} == {
        0,
        1,
        2,
        3,
    }
    assert {
        topology: len(expected_v8_directed_edges(topology))
        for topology in (
            "directed_ring_8",
            "directed_grid_3x3",
            "directed_ring_12",
            "directed_mesh_16",
        )
    } == {
        "directed_ring_8": 16,
        "directed_grid_3x3": 24,
        "directed_ring_12": 24,
        "directed_mesh_16": 240,
    }


def test_separate_online_and_offline_files_strictly_round_trip_one_episode(
    tmp_path: Path,
) -> None:
    frame = _frame()
    label = _label(frame)
    online_path, offline_path = _write_pair(tmp_path, frame, label)
    online_bytes = online_path.read_bytes()
    offline_bytes = offline_path.read_bytes()
    assert b'"target_class"' not in online_bytes
    assert b'"raw_actor"' not in offline_bytes

    loaded = load_v8_episode_pair(
        online_path,
        offline_path,
        expected_online_sha256=sha256(online_bytes).hexdigest(),
        expected_offline_sha256=sha256(offline_bytes).hexdigest(),
        expected_frame_count=1,
        schedule_entry=_schedule_entry(),
    )
    assert loaded.episode_id == frame.episode_id
    assert loaded.seed == 28100
    assert loaded.frames == (frame,)
    assert loaded.labels == (label,)


def test_hard_negative_keeps_anonymous_candidate_but_no_projected_transfer(
    tmp_path: Path,
) -> None:
    frame = _frame(
        seed=28106,
        episode_id="v8-train-28106",
        projected=False,
    )
    label = _label(frame, target_class=V8TransferClass.HARD_NO_TRANSFER)
    online_path, offline_path = _write_pair(tmp_path, frame, label)
    loaded = load_v8_episode_pair(
        online_path,
        offline_path,
        schedule_entry=_schedule_entry(
            seed=28106,
            target_class=V8TransferClass.HARD_NO_TRANSFER,
        ),
    )
    assert loaded.frames[0].raw_actor.activated is True
    assert len(loaded.frames[0].raw_actor.anonymous_candidates) == 1
    assert loaded.frames[0].projected_transfers == ()


def test_tampered_online_file_hash_fails_closed(tmp_path: Path) -> None:
    frame = _frame()
    label = _label(frame)
    online_path, offline_path = _write_pair(tmp_path, frame, label)
    expected_sha = sha256(online_path.read_bytes()).hexdigest()
    online_path.write_bytes(online_path.read_bytes()[:-1] + b" \n")
    with pytest.raises(
        RegionResourceV8ValidationError,
        match="v8_online_features_sha256_mismatch",
    ):
        load_v8_episode_pair(
            online_path,
            offline_path,
            expected_online_sha256=expected_sha,
        )


def test_missing_field_and_missing_label_file_fail_closed(tmp_path: Path) -> None:
    payload = _frame().to_dict()
    payload.pop("arrival_timestamp")
    with pytest.raises(RegionResourceV8ValidationError, match="missing=arrival_timestamp"):
        V8OnlineRegionResourceFrame.from_dict(payload)

    online_path = tmp_path / "online.jsonl"
    online_path.write_bytes(canonical_v8_json_line(_frame().to_dict()))
    with pytest.raises(
        RegionResourceV8DataUnavailableError,
        match="required_file_missing_or_unsafe:offline_labels",
    ):
        load_v8_episode_pair(online_path, tmp_path / "missing-label.jsonl")


def test_incomplete_or_wrong_direction_topology_fails_closed() -> None:
    payload = deepcopy(_frame().to_dict())
    payload["directed_edges"][0]["source_region_index"], payload[
        "directed_edges"
    ][0]["target_region_index"] = (
        payload["directed_edges"][0]["target_region_index"],
        payload["directed_edges"][0]["source_region_index"],
    )
    with pytest.raises(ValueError, match="topology_incomplete_or_wrong_direction"):
        V8OnlineRegionResourceFrame.from_dict(payload)


def test_seed_overlap_fails_even_when_attacker_recomputes_registry_hash() -> None:
    payload = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    payload["forbidden_seed_ranges"].append(
        {"range": [28100, 28100], "reason": "tampered_overlap"}
    )
    _recompute_content_sha256(payload)
    with pytest.raises(
        RegionResourceV8ValidationError,
        match="forbidden_seed_overlap",
    ):
        validate_v8_seed_registry_payload(payload)


@pytest.mark.parametrize("leaked_key", ["target_class", "truth_id"])
def test_label_or_truth_leakage_in_online_frame_fails_closed(
    leaked_key: str,
) -> None:
    payload = _frame().to_dict()
    payload[leaked_key] = "forbidden"
    with pytest.raises((ValueError, RegionResourceV8ValidationError), match="leakage"):
        V8OnlineRegionResourceFrame.from_dict(payload)


def test_raw_actor_candidate_rejects_actor_identity() -> None:
    payload = _frame().to_dict()
    payload["raw_actor"]["anonymous_candidates"][0]["actor_id"] = "Actor_1"
    with pytest.raises((ValueError, RegionResourceV8ValidationError), match="identity_leakage"):
        V8OnlineRegionResourceFrame.from_dict(payload)


def test_projected_transfer_with_old_lease_fails_closed() -> None:
    payload = _frame().to_dict()
    payload["regions"][0]["lease_expires_at_s"] = payload["arrival_timestamp"]
    with pytest.raises(ValueError, match="projected_transfer_stale_lease"):
        V8OnlineRegionResourceFrame.from_dict(payload)


def test_true_permission_fails_even_when_request_hash_is_recomputed() -> None:
    payload = json.loads(_REQUEST_PATH.read_text(encoding="utf-8"))
    payload["permissions"]["assignment"] = True
    _recompute_content_sha256(payload)
    with pytest.raises(
        RegionResourceV8ValidationError,
        match="permission_must_remain_false:assignment",
    ):
        validate_v8_data_request_payload(payload)


def test_frozen_readiness_does_not_upgrade_for_missing_explicit_schedule(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        RegionResourceV8DataUnavailableError,
        match="required_file_missing_or_unsafe:main_schedule",
    ):
        validate_v8_pre_generation_readiness(
            _REQUEST_PATH,
            _REGISTRY_PATH,
            main_schedule_path=tmp_path / "missing-main-schedule.json",
        )
