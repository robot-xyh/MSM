from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d3_assignment_planner.a1_v3_data_contract import (
    A1_V3_NEAR_TIE_REASON_MET,
    A1_V3_NEAR_TIE_REASON_NOT_MET,
    A1V3DataContractError,
    A1V3EdgeResidualRank,
    canonical_json_line,
    load_a1_v3_audit_dataset,
)
from d3_assignment_planner.a1_v3_dataset_writer import (
    A1_V3_ADAPTER_EVIDENCE_SCHEMA_V1,
    A1_V3_OFFLINE_SIDECAR_SCHEMA_V1,
    A1V3AdapterFrameEvidence,
    A1V3DatasetWriter,
    A1V3OfflineFrameSidecar,
    build_a1_v3_offline_label,
    build_a1_v3_online_frame,
    load_a1_v3_writer_contract,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_development_data_request_v1.json"
)
EXCLUSION_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_seed_exclusion_registry_v1.json"
)
CONTRACT_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_data_contract_v1.json"
)
GENERATOR_CONFIG_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generator_config_v1.json"
)
MAIN_REGISTRY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_main_allocation_registry_v1.json"
)
SCHEDULE_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generation_schedule_v1.json"
)
GLOBAL_REGISTRY_PATH = (
    MODULE_ROOT.parent
    / "scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)


def _evidence(
    frame_index: int,
    *,
    measurement_timestamp_s: float | None = None,
    arrival_timestamp_s: float | None = None,
    near_tie: bool = True,
) -> A1V3AdapterFrameEvidence:
    measurement = (
        frame_index * 0.1
        if measurement_timestamp_s is None
        else measurement_timestamp_s
    )
    arrival = measurement + 0.01 if arrival_timestamp_s is None else arrival_timestamp_s
    second_cost = 1.001 if near_tie else 1.5
    return A1V3AdapterFrameEvidence(
        frame_index=frame_index,
        measurement_timestamp_s=measurement,
        arrival_timestamp_s=arrival,
        observed_target_count=1,
        observed_resource_count=2,
        candidate_mask_shape=(1, 2),
        candidate_mask_true_edges=((0, 0), (0, 1)),
        rule_cost_matrix=((1.0, second_cost),),
        teacher_edges=((0, 0),),
        candidate_selected_edges=((0, 0),),
        effective_selected_edges=((0, 0),),
        residual_ranking=(
            A1V3EdgeResidualRank(edge=(0, 0), residual=0.0, rank=1),
            A1V3EdgeResidualRank(edge=(0, 1), residual=0.5, rank=2),
        ),
        target_demand_slots=(1,),
        pre_projection_reason_codes=("candidate_available",),
        post_projection_reason_codes=("candidate_accepted",),
    )


def _sidecar(
    frame_index: int,
    *,
    frame_class: str,
    hard_negative: bool = False,
    hard_negative_type: str | None = None,
    with_identity: bool = False,
) -> A1V3OfflineFrameSidecar:
    return A1V3OfflineFrameSidecar(
        frame_index=frame_index,
        frame_class=frame_class,
        hard_negative=hard_negative,
        action_change_type=(
            "single_target_rebind_with_resource_release"
            if frame_class == "positive"
            else "keep_exact_r0"
        ),
        hard_negative_type=hard_negative_type,
        truth_target_labels=("truth-target-0",) if with_identity else (),
        actor_labels=("actor-target-0",) if with_identity else (),
        object_labels=("object-target-0",) if with_identity else (),
        center_global_track_labels=("center-track-0",) if with_identity else (),
    )


def _complete_episode_rows(episode) -> tuple[list, list]:
    hard_count = episode.minimum_hard_negative_frames
    evidence = [_evidence(index) for index in range(9)]
    sidecars = []
    for index in range(9):
        if index < 3:
            sidecars.append(_sidecar(index, frame_class="positive"))
        else:
            hard = 3 <= index < 3 + hard_count
            sidecars.append(
                _sidecar(
                    index,
                    frame_class="negative",
                    hard_negative=hard,
                    hard_negative_type=(
                        "near_tie_but_teacher_keeps_r0" if hard else None
                    ),
                )
            )
    return evidence, sidecars


def _adapter_mapping() -> dict:
    return {
        "schema_version": A1_V3_ADAPTER_EVIDENCE_SCHEMA_V1,
        "frame_index": 0,
        "measurement_timestamp_s": 1.0,
        "arrival_timestamp_s": 1.01,
        "observed_target_count": 1,
        "observed_resource_count": 2,
        "candidate_mask": {
            "shape": [1, 2],
            "true_edges": [[0, 0], [0, 1]],
        },
        "rule_cost_matrix": [[1.0, 1.001]],
        "teacher_edges": [[0, 0]],
        "candidate_selected_edges": [[0, 0]],
        "effective_selected_edges": [[0, 0]],
        "residual_ranking": [
            {"edge": [0, 0], "residual": 0.0, "rank": 1},
            {"edge": [0, 1], "residual": 0.5, "rank": 2},
        ],
        "anonymous_target_demand_slots": [1],
        "pre_projection_reason_codes": ["candidate_available"],
        "post_projection_reason_codes": ["candidate_accepted"],
    }


def _sidecar_mapping() -> dict:
    return {
        "schema_version": A1_V3_OFFLINE_SIDECAR_SCHEMA_V1,
        "frame_index": 0,
        "classification": {
            "frame_class": "negative",
            "hard_negative": False,
            "action_change_type": "keep_exact_r0",
            "hard_negative_type": None,
        },
        "offline_identity_labels": {
            "truth_target_labels": [],
            "actor_labels": [],
            "object_labels": [],
            "center_global_track_labels": [],
        },
    }


def test_builder_uses_distinct_timestamps_and_computed_near_tie_margin() -> None:
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    frame = build_a1_v3_online_frame(episode, _evidence(0))
    assert frame.near_tie_reason_code == A1_V3_NEAR_TIE_REASON_MET
    assert frame.near_tie_qualifying_target_count == 1
    assert frame.near_tie_target_margins[0].absolute_gap == pytest.approx(0.001)
    assert frame.near_tie_target_margins[0].relative_gap == pytest.approx(0.001)

    no_tie = build_a1_v3_online_frame(episode, _evidence(0, near_tie=False))
    assert no_tie.near_tie_reason_code == A1_V3_NEAR_TIE_REASON_NOT_MET
    assert no_tie.near_tie_qualifying_target_count == 0
    with pytest.raises(A1V3DataContractError, match="near_tie_hard_negative"):
        build_a1_v3_offline_label(
            episode,
            no_tie,
            _sidecar(
                0,
                frame_class="negative",
                hard_negative=True,
                hard_negative_type="near_tie_but_teacher_keeps_r0",
            ),
            request=contract.request,
        )

    with pytest.raises(A1V3DataContractError, match="dual_timestamp"):
        build_a1_v3_online_frame(
            episode,
            _evidence(
                0,
                measurement_timestamp_s=2.0,
                arrival_timestamp_s=2.0,
            ),
        )
    near_tie_episode = next(
        item
        for item in contract.schedule.episodes
        if item.scenario_family == "near_tie_hard_negative"
    )
    near_tie_frame = build_a1_v3_online_frame(near_tie_episode, _evidence(0))
    with pytest.raises(A1V3DataContractError, match="hard_negative_type"):
        build_a1_v3_offline_label(
            near_tie_episode,
            near_tie_frame,
            _sidecar(
                0,
                frame_class="negative",
                hard_negative=True,
                hard_negative_type="resource_capacity_conflict",
            ),
            request=contract.request,
        )


def test_adapter_mapping_rejects_missing_fields_and_online_identity() -> None:
    assert A1V3AdapterFrameEvidence.from_mapping(_adapter_mapping()).frame_index == 0
    assert A1V3OfflineFrameSidecar.from_mapping(_sidecar_mapping()).frame_index == 0
    missing = deepcopy(_adapter_mapping())
    del missing["arrival_timestamp_s"]
    with pytest.raises(A1V3DataContractError, match="fields_mismatch"):
        A1V3AdapterFrameEvidence.from_mapping(missing)
    leaked = deepcopy(_adapter_mapping())
    leaked["actor_id"] = "actor-target-0"
    with pytest.raises(A1V3DataContractError, match="fields_mismatch"):
        A1V3AdapterFrameEvidence.from_mapping(leaked)
    value_leak = A1V3AdapterFrameEvidence.from_mapping(_adapter_mapping())
    value_leak = replace(
        value_leak,
        pre_projection_reason_codes=("truth_target_available",),
    )
    contract = load_a1_v3_writer_contract()
    with pytest.raises(A1V3DataContractError, match="identity_value_forbidden"):
        build_a1_v3_online_frame(contract.schedule.episodes[0], value_leak)


def test_stager_preserves_schedule_split_and_rejects_quota_or_duplicates(
    tmp_path: Path,
) -> None:
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    evidence, sidecars = _complete_episode_rows(episode)
    writer = A1V3DatasetWriter(
        tmp_path / "valid",
        dataset_id="a1-v3-writer-unit-valid",
        contract=contract,
    )
    summary = writer.stage_episode(episode, evidence, sidecars)
    assert summary.split == episode.split
    assert summary.frame_count == 9
    assert writer.staged_episode_count == 1
    with pytest.raises(A1V3DataContractError, match="duplicate_episode"):
        writer.stage_episode(episode, evidence, sidecars)

    split_writer = A1V3DatasetWriter(
        tmp_path / "split",
        dataset_id="a1-v3-writer-unit-split",
        contract=contract,
    )
    with pytest.raises(A1V3DataContractError, match="scheduled_episode_drift"):
        split_writer.stage_episode(replace(episode, split="test"), evidence, sidecars)

    quota_writer = A1V3DatasetWriter(
        tmp_path / "quota",
        dataset_id="a1-v3-writer-unit-quota",
        contract=contract,
    )
    with pytest.raises(A1V3DataContractError, match="minimum_not_met"):
        quota_writer.stage_episode(episode, evidence[:-1], sidecars[:-1])

    missing_writer = A1V3DatasetWriter(
        tmp_path / "missing",
        dataset_id="a1-v3-writer-unit-missing",
        contract=contract,
    )
    with pytest.raises(A1V3DataContractError, match="inventory_mismatch"):
        missing_writer.stage_episode(episode, evidence, sidecars[:-1])

    duplicate_writer = A1V3DatasetWriter(
        tmp_path / "duplicate",
        dataset_id="a1-v3-writer-unit-duplicate",
        contract=contract,
    )
    duplicate_evidence = list(evidence)
    duplicate_evidence[-1] = evidence[-2]
    with pytest.raises(A1V3DataContractError, match="duplicate_online_frame"):
        duplicate_writer.stage_episode(episode, duplicate_evidence, sidecars)


def test_resume_validates_stage_and_bound_source_hashes(tmp_path: Path) -> None:
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    evidence, sidecars = _complete_episode_rows(episode)
    output = tmp_path / "resume"
    writer = A1V3DatasetWriter(
        output,
        dataset_id="a1-v3-writer-unit-resume",
        contract=contract,
    )
    writer.stage_episode(episode, evidence, sidecars)
    resumed = A1V3DatasetWriter(
        output,
        dataset_id="a1-v3-writer-unit-resume",
        contract=contract,
    )
    assert resumed.staged_episode_count == 1

    drifted_schedule = replace(
        contract.schedule,
        episodes=tuple(reversed(contract.schedule.episodes)),
    )
    with pytest.raises(A1V3DataContractError, match="session_binding_mismatch"):
        A1V3DatasetWriter(
            output,
            dataset_id="a1-v3-writer-unit-resume",
            contract=replace(contract, schedule=drifted_schedule),
        )

    copied_boundary = tmp_path / "near_tie_boundary.json"
    boundary_source = next(
        item for item in contract.source_files if item.name == "near_tie_boundary"
    )
    copied_boundary.write_bytes(boundary_source.path.read_bytes())
    rebound_sources = tuple(
        replace(item, path=copied_boundary)
        if item.name == "near_tie_boundary"
        else item
        for item in contract.source_files
    )
    rebound_contract = replace(contract, source_files=rebound_sources)
    drift_output = tmp_path / "source-drift"
    A1V3DatasetWriter(
        drift_output,
        dataset_id="a1-v3-writer-unit-source-drift",
        contract=rebound_contract,
    )
    copied_boundary.write_bytes(copied_boundary.read_bytes() + b"\n")
    with pytest.raises(A1V3DataContractError, match="source_hash_drift"):
        A1V3DatasetWriter(
            drift_output,
            dataset_id="a1-v3-writer-unit-source-drift",
            contract=rebound_contract,
        )


@pytest.mark.parametrize("tamper_kind", ("permission", "identity_rewrite"))
def test_resume_rejects_permission_or_identity_provenance_tamper(
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    contract = load_a1_v3_writer_contract()
    episode = contract.schedule.episodes[0]
    evidence, sidecars = _complete_episode_rows(episode)
    output = tmp_path / tamper_kind
    writer = A1V3DatasetWriter(
        output,
        dataset_id=f"a1-v3-writer-unit-{tamper_kind}",
        contract=contract,
    )
    writer.stage_episode(episode, evidence, sidecars)
    stage_path = output / ".a1_v3_staging/episodes/episode-000.json"
    payload = json.loads(stage_path.read_text(encoding="ascii"))
    if tamper_kind == "permission":
        payload["online_frames"][0]["permissions"]["assignment"] = True
    else:
        payload["offline_labels"][0]["identity_provenance"][
            "learning_path_rewritten_global_track_id_count"
        ] = 1
    stage_path.write_bytes(canonical_json_line(payload))
    with pytest.raises(A1V3DataContractError):
        A1V3DatasetWriter(
            output,
            dataset_id=f"a1-v3-writer-unit-{tamper_kind}",
            contract=contract,
        )


def test_full_synthetic_inventory_finalizes_canonical_fixed_split_dataset(
    tmp_path: Path,
) -> None:
    contract = load_a1_v3_writer_contract()
    output = tmp_path / "dataset"
    writer = A1V3DatasetWriter(
        output,
        dataset_id="a1-v3-writer-synthetic-contract-test",
        contract=contract,
    )
    for episode in contract.schedule.episodes:
        evidence, sidecars = _complete_episode_rows(episode)
        writer.stage_episode(episode, evidence, sidecars)
    result = writer.finalize()
    assert result.episode_count == 300
    assert result.unique_seed_count == 300
    assert result.frame_count == 2700
    assert result.positive_frame_count == 900
    assert result.negative_frame_count == 1800
    assert result.hard_negative_frame_count == 450
    assert result.offline_identity_audit_availability == "unavailable"

    manifest_bytes = (output / "dataset_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes.decode("ascii"))
    assert manifest_bytes == canonical_json_line(manifest)
    online_bytes = (output / "online_frames.jsonl").read_bytes()
    offline_bytes = (output / "offline_labels.jsonl").read_bytes()
    assert sha256(online_bytes).hexdigest() == result.online_frames_sha256
    assert sha256(offline_bytes).hexdigest() == result.offline_labels_sha256
    assert manifest["split"]["seed_counts"] == {
        "train": 180,
        "validation": 60,
        "test": 60,
    }
    assert manifest["offline_identity_audit"] == {
        "availability": "unavailable",
        "complete_identity_audit_claimed": False,
        "complete_identity_label_frame_count": 0,
        "partial_identity_label_frame_count": 0,
        "empty_identity_label_frame_count": 2700,
    }
    audit = load_a1_v3_audit_dataset(
        output,
        request_path=REQUEST_PATH,
        exclusion_registry_path=EXCLUSION_PATH,
        contract_path=CONTRACT_PATH,
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
        generator_config_path=GENERATOR_CONFIG_PATH,
        global_registry_path=GLOBAL_REGISTRY_PATH,
    )
    assert audit.manifest.offline_identity_audit_availability == "unavailable"
    assert len(audit.online_frames) == 2700
