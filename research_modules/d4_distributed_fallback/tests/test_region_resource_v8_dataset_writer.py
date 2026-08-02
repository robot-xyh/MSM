from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Callable

import pytest

import d4_distributed_fallback.region_resource_v8_dataset_writer as writer_module
from d4_distributed_fallback.region_resource_v8_dataset_writer import (
    RegionResourceV8DatasetWriterError,
    V8CleanSourceMetadata,
    V8DatasetWriteResult,
    V8TrainDatasetWriter,
)
from d4_distributed_fallback.region_resource_v8_development_contract import (
    RegionResourceV8ValidationError,
    V8AnonymousRawActorAction,
    V8AnonymousTransferCandidate,
    V8DirectedEdgeState,
    V8NoAuthorityPermissions,
    V8OfflineTransferLabel,
    V8OnlineRegionResourceFrame,
    V8PartitionState,
    V8R0ActionTuple,
    V8R0RegionAction,
    V8RegionResourceState,
    V8RequestScheduleEntry,
    V8Transfer,
    V8TransferClass,
    canonical_v8_json_line,
    canonical_v8_sha256,
    classify_v8_edge_direction,
    expected_v8_directed_edges,
    load_v8_frozen_request,
)


_MODULE_ROOT = Path(__file__).resolve().parents[1]
_REQUEST_ROOT = (
    _MODULE_ROOT
    / "reports"
    / "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)
_REQUEST_PATH = _REQUEST_ROOT / "v8_development_data_request.json"
_REGISTRY_PATH = _REQUEST_ROOT / "v8_development_seed_registry.json"


def _source_metadata() -> V8CleanSourceMetadata:
    return V8CleanSourceMetadata(
        source_scenario_id="scalable-3d-a2-v8-controlled-source",
        source_scenario_version="scalable3d-a2-v8-source-v1",
        source_git_commit="a" * 40,
        source_git_dirty=False,
        source_config_sha256="b" * 64,
    )


def _writer(
    tmp_path: Path,
    *,
    source_metadata: V8CleanSourceMetadata | None = None,
) -> V8TrainDatasetWriter:
    return V8TrainDatasetWriter.from_contract_files(
        dataset_root=tmp_path / "dataset",
        main_schedule_path=tmp_path / "schedule" / "main_schedule.json",
        request_path=_REQUEST_PATH,
        registry_path=_REGISTRY_PATH,
        expected_source_metadata=source_metadata or _source_metadata(),
        schedule_id="controlled-v8-main-schedule-v1",
        dataset_id="controlled-v8-train-source-v1",
    )


def _resume_writer(
    tmp_path: Path,
    staging_root: Path,
    *,
    source_metadata: V8CleanSourceMetadata | None = None,
) -> V8TrainDatasetWriter:
    return V8TrainDatasetWriter.resume_from_contract_files(
        staging_root=staging_root,
        dataset_root=tmp_path / "dataset",
        main_schedule_path=tmp_path / "schedule" / "main_schedule.json",
        request_path=_REQUEST_PATH,
        registry_path=_REGISTRY_PATH,
        expected_source_metadata=source_metadata or _source_metadata(),
        schedule_id="controlled-v8-main-schedule-v1",
        dataset_id="controlled-v8-train-source-v1",
    )


def _rewrite_resume_state(
    path: Path,
    mutate: Callable[[dict[str, object]], None],
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    payload.pop("content_sha256")
    payload["content_sha256"] = canonical_v8_sha256(payload)
    path.write_bytes(canonical_v8_json_line(payload))


def _stage_and_suspend(
    tmp_path: Path,
    *,
    episode_count: int = 2,
) -> tuple[Path, Path]:
    writer = _writer(tmp_path)
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    for index, entry in enumerate(frozen.schedule[:episode_count]):
        frames, labels = _episode_pair(entry, index)
        writer.stage_episode(
            schedule_index=index,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=_source_metadata(),
        )
    state_path = writer.resume_state_path
    staging_root = writer.suspend_for_resume()
    return staging_root, state_path


def _selected_transfers(
    entry: V8RequestScheduleEntry,
) -> tuple[V8Transfer, ...]:
    if entry.requested_target_class == V8TransferClass.HARD_NO_TRANSFER:
        return ()
    direction = (
        "forward"
        if entry.requested_target_class == V8TransferClass.SAFE_FORWARD
        else "reverse"
    )
    result: list[V8Transfer] = []
    seen_sources: set[int] = set()
    for edge_index, (source, target) in enumerate(
        expected_v8_directed_edges(entry.topology_id)
    ):
        if source in seen_sources:
            continue
        if classify_v8_edge_direction(entry.topology_id, source, target) != direction:
            continue
        result.append(
            V8Transfer(
                edge_index=edge_index,
                source_region_index=source,
                target_region_index=target,
                resource_count=1,
            )
        )
        seen_sources.add(source)
        if len(result) == entry.requested_transfer_resource_count:
            return tuple(result)
    raise AssertionError("controlled fixture lacks enough distinct transfer sources")


def _region_gaps(
    entry: V8RequestScheduleEntry,
    transfers: tuple[V8Transfer, ...],
    hard_candidate_source: int | None,
) -> list[int]:
    gaps = [0] * entry.region_count
    transfer_sources = {item.source_region_index for item in transfers}
    for source in transfer_sources:
        gaps[source] = 1

    if entry.supply_demand_condition == "source_surplus_target_deficit":
        positive_index = next(
            index
            for index in range(entry.region_count)
            if index not in transfer_sources and index != hard_candidate_source
        )
        if not transfer_sources:
            gaps[positive_index] = 1
        negative_index = next(
            index
            for index in reversed(range(entry.region_count))
            if index not in transfer_sources and index != positive_index
        )
        gaps[negative_index] = -1
    elif entry.supply_demand_condition == "global_shortage_with_local_candidate_edge":
        if not transfer_sources:
            positive_index = next(
                index
                for index in range(entry.region_count)
                if index != hard_candidate_source
            )
            gaps[positive_index] = 1
        for index in range(entry.region_count):
            if gaps[index] <= 0:
                gaps[index] = -1
    return gaps


def _regions(
    entry: V8RequestScheduleEntry,
    transfers: tuple[V8Transfer, ...],
    hard_candidate_source: int | None,
) -> tuple[V8RegionResourceState, ...]:
    result: list[V8RegionResourceState] = []
    for index, gap in enumerate(_region_gaps(entry, transfers, hard_candidate_source)):
        demand = 1 if gap >= -1 else -gap
        available = demand + gap
        result.append(
            V8RegionResourceState(
                region_index=index,
                region_id=f"region-{index}",
                supply_available=available,
                supply_committed=0,
                supply_reserved=0,
                demand_required=demand,
                demand_weighted=float(demand),
                supply_demand_gap=gap,
                owner_id="Center_1",
                owner_layer="center",
                plan_id="plan-v8-controlled",
                plan_version=1,
                epoch=1,
                lease_expires_at_s=100.0,
                coalition_ack_complete=True,
                owner_active=True,
                fault_fenced=False,
            )
        )
    return tuple(result)


def _edges(
    entry: V8RequestScheduleEntry,
    *,
    partition_edge_index: int | None,
) -> tuple[V8DirectedEdgeState, ...]:
    if entry.communication_condition == "nominal":
        latency, loss = 0.01, 0.0
    else:
        latency, loss = 0.1, 0.1
    return tuple(
        V8DirectedEdgeState(
            edge_index=edge_index,
            source_region_index=source,
            target_region_index=target,
            transfer_capacity=3,
            communication_latency_s=latency,
            communication_loss_rate=loss,
            communication_partition_state=(
                V8PartitionState.PARTITIONED
                if edge_index == partition_edge_index
                else V8PartitionState.CONNECTED
            ),
            communication_available=edge_index != partition_edge_index,
            maneuver_available=True,
        )
        for edge_index, (source, target) in enumerate(
            expected_v8_directed_edges(entry.topology_id)
        )
    )


def _episode_pair(
    entry: V8RequestScheduleEntry,
    schedule_index: int,
    *,
    episode_id: str | None = None,
    frame_indices: tuple[int, ...] | None = None,
) -> tuple[tuple[V8OnlineRegionResourceFrame, ...], tuple[V8OfflineTransferLabel, ...]]:
    episode = episode_id or f"v8-train-{entry.seed}"
    transfers = _selected_transfers(entry)
    edge_pairs = expected_v8_directed_edges(entry.topology_id)
    if entry.requested_target_class == V8TransferClass.HARD_NO_TRANSFER:
        source, target = edge_pairs[0]
        hard_candidate_source: int | None = source
        candidates = (
            V8AnonymousTransferCandidate(
                candidate_index=0,
                edge_index=0,
                source_region_index=source,
                target_region_index=target,
                resource_count=entry.hard_negative_candidate_resource_count,
                activation_score=0.9,
            ),
        )
    else:
        hard_candidate_source = None
        candidates = tuple(
            V8AnonymousTransferCandidate(
                candidate_index=index,
                edge_index=transfer.edge_index,
                source_region_index=transfer.source_region_index,
                target_region_index=transfer.target_region_index,
                resource_count=transfer.resource_count,
                activation_score=0.9,
            )
            for index, transfer in enumerate(transfers)
        )

    if frame_indices is None:
        frame_indices = (
            (0, 1)
            if entry.communication_condition == "partition_then_recovery"
            else (0,)
        )
    transfer_edge_indices = {item.edge_index for item in transfers}
    candidate_edge_indices = {item.edge_index for item in candidates}
    partition_edge = next(
        index
        for index in range(len(edge_pairs))
        if index not in transfer_edge_indices | candidate_edge_indices
    )
    frames: list[V8OnlineRegionResourceFrame] = []
    labels: list[V8OfflineTransferLabel] = []
    for position, frame_index in enumerate(frame_indices):
        partition_index = (
            partition_edge
            if entry.communication_condition == "partition_then_recovery"
            and position == 0
            else None
        )
        frame = V8OnlineRegionResourceFrame(
            frame_id=f"{episode}:{frame_index}",
            episode_id=episode,
            seed=entry.seed,
            split="train",
            frame_index=frame_index,
            measurement_timestamp=float(frame_index),
            arrival_timestamp=float(frame_index) + 0.1,
            topology_id=entry.topology_id,
            region_count=entry.region_count,
            regions=_regions(entry, transfers, hard_candidate_source),
            directed_edges=_edges(entry, partition_edge_index=partition_index),
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
                    for index in range(entry.region_count)
                ),
                transfers=(),
            ),
            raw_actor=V8AnonymousRawActorAction(
                activated=True,
                anonymous_candidates=candidates,
            ),
            projected_transfers=(
                ()
                if entry.requested_target_class == V8TransferClass.HARD_NO_TRANSFER
                else transfers
            ),
            projection_rejection_reasons=(
                ("insufficient_source_surplus",)
                if entry.requested_target_class == V8TransferClass.HARD_NO_TRANSFER
                else ()
            ),
            invariant_failure_reasons=(),
            permissions=V8NoAuthorityPermissions(),
        )
        label = V8OfflineTransferLabel(
            frame_id=frame.frame_id,
            episode_id=frame.episode_id,
            seed=frame.seed,
            split="train",
            frame_index=frame.frame_index,
            online_frame_sha256=frame.content_sha256,
            target_class=entry.requested_target_class,
            expected_projected_transfers=frame.projected_transfers,
            positive_transfer_resource_count=(
                0
                if entry.requested_target_class == V8TransferClass.HARD_NO_TRANSFER
                else entry.requested_transfer_resource_count
            ),
            hard_negative_candidate_resource_count=(
                entry.hard_negative_candidate_resource_count
            ),
            hard_negative_reasons=(
                ("insufficient_source_surplus",)
                if entry.requested_target_class == V8TransferClass.HARD_NO_TRANSFER
                else ()
            ),
            label_source="same_snapshot_r0_deterministic_projection",
        )
        frames.append(frame)
        labels.append(label)
    return tuple(frames), tuple(labels)


@pytest.fixture(scope="module")
def finalized_dataset(tmp_path_factory: pytest.TempPathFactory) -> V8DatasetWriteResult:
    root = tmp_path_factory.mktemp("v8-writer-complete")
    writer = _writer(root)
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    resume_index = 17
    for index, entry in enumerate(frozen.schedule[:resume_index]):
        frames, labels = _episode_pair(entry, index)
        writer.stage_episode(
            schedule_index=index,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=_source_metadata(),
        )
    staging_root = writer.suspend_for_resume()
    writer = _resume_writer(root, staging_root)
    assert writer.staged_episode_count == resume_index
    assert writer.next_schedule_index == resume_index
    for index, entry in enumerate(
        frozen.schedule[resume_index:],
        start=resume_index,
    ):
        frames, labels = _episode_pair(entry, index)
        writer.stage_episode(
            schedule_index=index,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=_source_metadata(),
        )
    return writer.finalize()


def test_complete_incremental_stage_finalize_and_strict_round_trip(
    finalized_dataset: V8DatasetWriteResult,
) -> None:
    result = finalized_dataset
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    assert result.main_schedule.entry_count == 324
    assert result.manifest.episode_count == 324
    assert len(result.loaded_dataset.episodes) == 324
    assert result.manifest.validation_seed_allocation == ()
    assert result.manifest.test_seed_allocation == ()
    assert result.manifest.training_count == 0
    assert result.manifest.runtime_connection_count == 0
    assert not any(result.manifest.permissions.to_dict()[name] for name in (
        "assignment",
        "degradation",
        "coalition",
        "takeover",
        "control",
    ))
    for registry, schedule, manifest, loaded in zip(
        frozen.schedule,
        result.main_schedule.entries,
        result.manifest.episodes,
        result.loaded_dataset.episodes,
        strict=True,
    ):
        assert schedule.request_entry == registry
        assert schedule.topology_id == registry.topology_id
        assert schedule.communication_condition == registry.communication_condition
        assert schedule.requested_target_class == registry.requested_target_class
        assert (
            schedule.requested_transfer_resource_count
            == registry.requested_transfer_resource_count
        )
        assert (
            schedule.hard_negative_candidate_resource_count
            == registry.hard_negative_candidate_resource_count
        )
        assert schedule.seed == manifest.seed == loaded.seed == registry.seed
        assert schedule.episode_id == manifest.episode_id == loaded.episode_id
        assert all(frame.topology_id == registry.topology_id for frame in loaded.frames)
        assert all(
            label.target_class == registry.requested_target_class
            for label in loaded.labels
        )


def test_writer_uses_canonical_bytes_and_separate_exact_inventory(
    finalized_dataset: V8DatasetWriteResult,
) -> None:
    result = finalized_dataset
    assert result.main_schedule_path.read_bytes() == canonical_v8_json_line(
        result.main_schedule.to_dict()
    )
    assert (result.dataset_root / "manifest.json").read_bytes() == (
        canonical_v8_json_line(result.manifest.to_dict())
    )
    first = result.loaded_dataset.episodes[0]
    assert first.online_path.read_bytes() == b"".join(
        canonical_v8_json_line(item.to_dict()) for item in first.frames
    )
    assert first.offline_path.read_bytes() == b"".join(
        canonical_v8_json_line(item.to_dict()) for item in first.labels
    )
    assert first.online_path.parent.name == "online"
    assert first.offline_path.parent.name == "labels"
    files = {path.relative_to(result.dataset_root) for path in result.dataset_root.rglob("*") if path.is_file()}
    assert len(files) == 649
    assert all(path.parts[0] in {"online", "labels"} or path == Path("manifest.json") for path in files)


def test_resume_reloads_order_seed_hash_and_clean_source_state(
    tmp_path: Path,
) -> None:
    staging_root, state_path = _stage_and_suspend(tmp_path, episode_count=3)

    resumed = _resume_writer(tmp_path, staging_root)

    assert resumed.staged_episode_count == 3
    assert resumed.next_schedule_index == 3
    assert tuple(item.schedule_index for item in resumed.staged_episodes) == (0, 1, 2)
    assert tuple(item.seed for item in resumed.staged_episodes) == (
        28100,
        28101,
        28102,
    )
    assert state_path.is_file()
    resumed.abort()
    assert not staging_root.exists()
    assert not state_path.exists()


def test_resume_rejects_corrupted_episode_hash(tmp_path: Path) -> None:
    staging_root, _ = _stage_and_suspend(tmp_path, episode_count=1)
    online_path = staging_root / "online" / "000_28100.jsonl"
    online_path.write_bytes(online_path.read_bytes() + b"\n")

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_episode_invalid:0:.*sha256_mismatch",
    ):
        _resume_writer(tmp_path, staging_root)


def test_resume_rejects_missing_staged_episode_file(tmp_path: Path) -> None:
    staging_root, _ = _stage_and_suspend(tmp_path, episode_count=1)
    (staging_root / "labels" / "000_28100.jsonl").unlink()

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_file_inventory_mismatch",
    ):
        _resume_writer(tmp_path, staging_root)


def test_resume_rejects_schedule_gap_or_reordering(tmp_path: Path) -> None:
    staging_root, state_path = _stage_and_suspend(tmp_path, episode_count=2)

    def reorder(payload: dict[str, object]) -> None:
        entries = payload["staged_episodes"]
        assert isinstance(entries, list)
        entries.reverse()

    _rewrite_resume_state(state_path, reorder)

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_schedule_gap_or_order_mismatch",
    ):
        _resume_writer(tmp_path, staging_root)


def test_resume_rejects_seed_drift_even_when_state_is_rehashed(
    tmp_path: Path,
) -> None:
    staging_root, state_path = _stage_and_suspend(tmp_path, episode_count=1)

    def drift_seed(payload: dict[str, object]) -> None:
        entries = payload["staged_episodes"]
        assert isinstance(entries, list)
        assert isinstance(entries[0], dict)
        entries[0]["seed"] = 29999

    _rewrite_resume_state(state_path, drift_seed)

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_seed_inventory_mismatch",
    ):
        _resume_writer(tmp_path, staging_root)


def test_resume_rejects_clean_source_drift(tmp_path: Path) -> None:
    staging_root, _ = _stage_and_suspend(tmp_path, episode_count=1)
    stale_source = replace(_source_metadata(), source_git_commit="c" * 40)

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_clean_source_mismatch",
    ):
        _resume_writer(
            tmp_path,
            staging_root,
            source_metadata=stale_source,
        )


def test_resume_rejects_permission_escalation_in_rehashed_state(
    tmp_path: Path,
) -> None:
    staging_root, state_path = _stage_and_suspend(tmp_path, episode_count=1)

    def escalate(payload: dict[str, object]) -> None:
        permissions = payload["permissions"]
        assert isinstance(permissions, dict)
        permissions["degradation"] = True

    _rewrite_resume_state(state_path, escalate)

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_permissions_not_all_false",
    ):
        _resume_writer(tmp_path, staging_root)


def test_resume_rejects_state_hash_drift(tmp_path: Path) -> None:
    staging_root, state_path = _stage_and_suspend(tmp_path, episode_count=1)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["dataset_id"] = "tampered-without-rehash"
    state_path.write_bytes(canonical_v8_json_line(payload))

    with pytest.raises(
        RegionResourceV8DatasetWriterError,
        match="v8_writer_resume_state_content_sha256_mismatch",
    ):
        _resume_writer(tmp_path, staging_root)


def test_schedule_publish_failure_rolls_back_to_resumable_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _writer(tmp_path)
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    for index, entry in enumerate(frozen.schedule):
        frames, labels = _episode_pair(entry, index)
        writer.stage_episode(
            schedule_index=index,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=_source_metadata(),
        )
    staging_root = writer.staging_root
    state_path = writer.resume_state_path
    schedule_path = tmp_path / "schedule" / "main_schedule.json"
    original_replace = writer_module.os.replace

    def fail_schedule_publish(source: object, destination: object) -> None:
        if Path(destination).resolve() == schedule_path.resolve():
            raise OSError("controlled schedule publish failure")
        original_replace(source, destination)

    monkeypatch.setattr(writer_module.os, "replace", fail_schedule_publish)
    with pytest.raises(OSError, match="controlled schedule publish failure"):
        writer.finalize()

    assert writer.staged_episode_count == 324
    assert writer.staging_root == staging_root
    assert staging_root.is_dir()
    assert state_path.is_file()
    assert not (tmp_path / "dataset").exists()
    assert not schedule_path.exists()
    assert not (staging_root / "manifest.json").exists()

    writer.suspend_for_resume()
    monkeypatch.setattr(writer_module.os, "replace", original_replace)
    resumed = _resume_writer(tmp_path, staging_root)
    result = resumed.finalize()
    assert result.manifest.episode_count == 324


def test_out_of_order_duplicate_episode_and_duplicate_seed_fail_closed(
    tmp_path: Path,
) -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)

    out_of_order = _writer(tmp_path / "out-of-order")
    frames, labels = _episode_pair(frozen.schedule[1], 1)
    with pytest.raises(RegionResourceV8DatasetWriterError, match="out_of_order"):
        out_of_order.stage_episode(
            schedule_index=1,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=_source_metadata(),
        )
    out_of_order.abort()

    duplicate_episode = _writer(tmp_path / "duplicate-episode")
    first_frames, first_labels = _episode_pair(frozen.schedule[0], 0)
    duplicate_episode.stage_episode(
        schedule_index=0,
        episode_id=first_frames[0].episode_id,
        frames=first_frames,
        labels=first_labels,
        source_metadata=_source_metadata(),
    )
    second_frames, second_labels = _episode_pair(
        frozen.schedule[1],
        1,
        episode_id=first_frames[0].episode_id,
    )
    with pytest.raises(RegionResourceV8DatasetWriterError, match="duplicate_episode"):
        duplicate_episode.stage_episode(
            schedule_index=1,
            episode_id=first_frames[0].episode_id,
            frames=second_frames,
            labels=second_labels,
            source_metadata=_source_metadata(),
        )
    duplicate_episode.abort()

    duplicate_seed = _writer(tmp_path / "duplicate-seed")
    duplicate_seed.stage_episode(
        schedule_index=0,
        episode_id=first_frames[0].episode_id,
        frames=first_frames,
        labels=first_labels,
        source_metadata=_source_metadata(),
    )
    second_frames, _ = _episode_pair(frozen.schedule[1], 1)
    repeated_seed_frame = replace(second_frames[0], seed=frozen.schedule[0].seed)
    repeated_seed_label = V8OfflineTransferLabel(
        frame_id=repeated_seed_frame.frame_id,
        episode_id=repeated_seed_frame.episode_id,
        seed=repeated_seed_frame.seed,
        split="train",
        frame_index=repeated_seed_frame.frame_index,
        online_frame_sha256=repeated_seed_frame.content_sha256,
        target_class=frozen.schedule[1].requested_target_class,
        expected_projected_transfers=repeated_seed_frame.projected_transfers,
        positive_transfer_resource_count=2,
        hard_negative_candidate_resource_count=0,
        hard_negative_reasons=(),
        label_source="same_snapshot_r0_deterministic_projection",
    )
    with pytest.raises(RegionResourceV8DatasetWriterError, match="duplicate_seed"):
        duplicate_seed.stage_episode(
            schedule_index=1,
            episode_id=repeated_seed_frame.episode_id,
            frames=(repeated_seed_frame,),
            labels=(repeated_seed_label,),
            source_metadata=_source_metadata(),
        )
    duplicate_seed.abort()


def test_noncontiguous_frame_and_frame_label_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    entry = frozen.schedule[0]

    noncontiguous = _writer(tmp_path / "noncontiguous")
    frames, labels = _episode_pair(entry, 0, frame_indices=(1,))
    with pytest.raises(RegionResourceV8ValidationError, match="not_contiguous"):
        noncontiguous.stage_episode(
            schedule_index=0,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=_source_metadata(),
        )
    noncontiguous.abort()

    mismatch = _writer(tmp_path / "mismatch")
    frames, labels = _episode_pair(entry, 0)
    wrong_label = replace(labels[0], online_frame_sha256="0" * 64)
    with pytest.raises(RegionResourceV8ValidationError, match="sha256_mismatch"):
        mismatch.stage_episode(
            schedule_index=0,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=(wrong_label,),
            source_metadata=_source_metadata(),
        )
    mismatch.abort()


def test_online_truth_leakage_and_obsolete_source_fail_closed(
    tmp_path: Path,
) -> None:
    class LeakyOnlineFrame(V8OnlineRegionResourceFrame):
        def to_dict(self) -> dict[str, object]:
            payload = super().to_dict()
            payload["truth_id"] = "offline-only"
            return payload

    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    frames, labels = _episode_pair(frozen.schedule[0], 0)
    leaky = LeakyOnlineFrame(**vars(frames[0]))
    writer = _writer(tmp_path / "truth-leak")
    with pytest.raises(RegionResourceV8ValidationError, match="identity_leakage"):
        writer.stage_episode(
            schedule_index=0,
            episode_id=leaky.episode_id,
            frames=(leaky,),
            labels=labels,
            source_metadata=_source_metadata(),
        )
    writer.abort()

    stale_writer = _writer(tmp_path / "stale-source")
    stale = replace(_source_metadata(), source_config_sha256="c" * 64)
    with pytest.raises(RegionResourceV8DatasetWriterError, match="obsolete"):
        stale_writer.stage_episode(
            schedule_index=0,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=stale,
        )
    stale_writer.abort()

    with pytest.raises(RegionResourceV8DatasetWriterError, match="dirty_source"):
        V8CleanSourceMetadata(
            source_scenario_id="scenario",
            source_scenario_version="v1",
            source_git_commit="d" * 40,
            source_git_dirty=True,
            source_config_sha256="e" * 64,
        )


def test_finalize_rejects_missing_episode_inventory(tmp_path: Path) -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    writer = _writer(tmp_path / "missing")
    frames, labels = _episode_pair(frozen.schedule[0], 0)
    writer.stage_episode(
        schedule_index=0,
        episode_id=frames[0].episode_id,
        frames=frames,
        labels=labels,
        source_metadata=_source_metadata(),
    )
    with pytest.raises(RegionResourceV8DatasetWriterError, match="missing_frozen"):
        writer.finalize()
    writer.abort()
    assert not (tmp_path / "missing" / "dataset").exists()
    assert not (tmp_path / "missing" / "schedule" / "main_schedule.json").exists()


def test_scenario_name_cannot_replace_partition_recovery_evidence(
    tmp_path: Path,
) -> None:
    claimed_source = replace(
        _source_metadata(),
        source_scenario_id="claims-partition-then-recovery",
    )
    writer = _writer(tmp_path / "claimed-partition", source_metadata=claimed_source)
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    partition_index = next(
        index
        for index, entry in enumerate(frozen.schedule)
        if entry.communication_condition == "partition_then_recovery"
    )
    for index, entry in enumerate(frozen.schedule[:partition_index]):
        frames, labels = _episode_pair(entry, index)
        writer.stage_episode(
            schedule_index=index,
            episode_id=frames[0].episode_id,
            frames=frames,
            labels=labels,
            source_metadata=claimed_source,
        )

    entry = frozen.schedule[partition_index]
    frames, labels = _episode_pair(entry, partition_index)
    no_partition_frames = tuple(
        replace(frame, directed_edges=_edges(entry, partition_edge_index=None))
        for frame in frames
    )
    rebound_labels = tuple(
        replace(label, online_frame_sha256=frame.content_sha256)
        for frame, label in zip(no_partition_frames, labels, strict=True)
    )
    with pytest.raises(
        RegionResourceV8ValidationError,
        match="communication_condition_not_observed:partition_then_recovery",
    ):
        writer.stage_episode(
            schedule_index=partition_index,
            episode_id=no_partition_frames[0].episode_id,
            frames=no_partition_frames,
            labels=rebound_labels,
            source_metadata=claimed_source,
        )
    writer.abort()


def test_scenario_name_cannot_replace_requested_transfer_count_evidence(
    tmp_path: Path,
) -> None:
    claimed_source = replace(
        _source_metadata(),
        source_scenario_id="claims-safe-forward-two-resources",
    )
    writer = _writer(tmp_path / "claimed-transfer", source_metadata=claimed_source)
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    first_frames, first_labels = _episode_pair(frozen.schedule[0], 0)
    writer.stage_episode(
        schedule_index=0,
        episode_id=first_frames[0].episode_id,
        frames=first_frames,
        labels=first_labels,
        source_metadata=claimed_source,
    )

    entry = frozen.schedule[1]
    frames, _ = _episode_pair(entry, 1)
    original = frames[0]
    one_transfer = (original.projected_transfers[0],)
    one_candidate = (original.raw_actor.anonymous_candidates[0],)
    insufficient_frame = replace(
        original,
        raw_actor=V8AnonymousRawActorAction(
            activated=True,
            anonymous_candidates=one_candidate,
        ),
        projected_transfers=one_transfer,
    )
    insufficient_label = V8OfflineTransferLabel(
        frame_id=insufficient_frame.frame_id,
        episode_id=insufficient_frame.episode_id,
        seed=insufficient_frame.seed,
        split="train",
        frame_index=insufficient_frame.frame_index,
        online_frame_sha256=insufficient_frame.content_sha256,
        target_class=entry.requested_target_class,
        expected_projected_transfers=one_transfer,
        positive_transfer_resource_count=1,
        hard_negative_candidate_resource_count=0,
        hard_negative_reasons=(),
        label_source="same_snapshot_r0_deterministic_projection",
    )
    with pytest.raises(
        RegionResourceV8ValidationError,
        match="schedule_positive_transfer_count_missing",
    ):
        writer.stage_episode(
            schedule_index=1,
            episode_id=insufficient_frame.episode_id,
            frames=(insufficient_frame,),
            labels=(insufficient_label,),
            source_metadata=claimed_source,
        )
    writer.abort()
