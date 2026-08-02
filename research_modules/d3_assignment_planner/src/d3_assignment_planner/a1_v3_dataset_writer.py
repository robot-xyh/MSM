"""Strict producer-facing evidence builder and writer for A1 v3.

This module is a data-contract utility.  It does not run the planner, publish
an assignment plan, authorize generation, or grant any runtime permission.
Main remains responsible for producing scalable three-dimensional episodes
and for obtaining a separately frozen execution authorization.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
from typing import Any

from .a1_v3_data_contract import (
    A1_V3_CELL_SPLIT_SEED_COUNTS,
    A1_V3_DATASET_MANIFEST_SCHEMA_V1,
    A1_V3_MANIFEST_FILENAME,
    A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
    A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
    A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
    A1_V3_NEAR_TIE_REASON_MET,
    A1_V3_NEAR_TIE_REASON_NOT_MET,
    A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR,
    A1_V3_OFFLINE_LABELS_FILENAME,
    A1_V3_OFFLINE_LABEL_SCHEMA_V1,
    A1_V3_ONLINE_FRAMES_FILENAME,
    A1_V3_ONLINE_FRAME_SCHEMA_V1,
    A1_V3_PERMISSION_FIELDS,
    A1_V3_SPLITS,
    A1_V3_SPLIT_PERCENT,
    A1_V3_SPLIT_POLICY_V1,
    A1_V3_SPLIT_SEED_COUNTS,
    A1_V3_TRAINING_FEATURE_SCHEMA_V1,
    A1_V3_TRAINING_TARGET_SCHEMA_V1,
    DEFAULT_A1_V3_DATA_CONTRACT_PATH,
    DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
    DEFAULT_A1_V3_GENERATION_SCHEDULE_PATH,
    DEFAULT_A1_V3_GENERATOR_CONFIG_PATH,
    DEFAULT_A1_V3_GLOBAL_SEED_REGISTRY_PATH,
    DEFAULT_A1_V3_MAIN_SEED_REGISTRY_PATH,
    DEFAULT_A1_V3_REQUEST_PATH,
    A1V3ContractDescriptor,
    A1V3DataContractError,
    A1V3EdgeResidualRank,
    A1V3FrameSource,
    A1V3FrozenRequest,
    A1V3GenerationSchedule,
    A1V3GeneratorConfig,
    A1V3GlobalAllocation,
    A1V3OfflineLabel,
    A1V3OnlineFrame,
    A1V3ScheduledEpisode,
    A1V3SeedRegistry,
    action_mask_content_sha256,
    canonical_json_bytes,
    canonical_json_line,
    canonical_json_sha256,
    compute_a1_v3_near_tie_target_margins,
    load_a1_v3_contract_descriptor,
    load_a1_v3_exclusion_registry,
    load_a1_v3_frozen_request,
    load_a1_v3_generation_schedule,
    load_a1_v3_generator_config,
    load_a1_v3_global_seed_allocation,
    load_a1_v3_main_seed_registry,
)
from .a1_v3_sidecar_classification import (
    A1_V3_SIDECAR_CLASSIFIER_LOGICAL_PATH,
    DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH,
    A1V3SidecarClassificationPolicy,
    derive_a1_v3_frame_classifications,
    load_a1_v3_sidecar_classification_policy,
)


A1_V3_ADAPTER_EVIDENCE_SCHEMA_V1 = "d3_a1_v3_adapter_frame_evidence_v1"
A1_V3_OFFLINE_SIDECAR_SCHEMA_V1 = "d3_a1_v3_offline_frame_sidecar_v1"
A1_V3_WRITER_SESSION_SCHEMA_V1 = "d3_a1_v3_writer_session_v1"
A1_V3_STAGED_EPISODE_SCHEMA_V1 = "d3_a1_v3_staged_episode_v1"

_STAGING_DIRECTORY = ".a1_v3_staging"
_STAGING_SESSION_FILENAME = "session.json"
_STAGING_EPISODE_DIRECTORY = "episodes"
_DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
DEFAULT_A1_V3_NEAR_TIE_BOUNDARY_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs/a1_source_independent_v3_near_tie_boundary_v1.json"
)


@dataclass(frozen=True)
class A1V3AdapterFrameEvidence:
    """Identity-free fields supplied by main for one planning frame."""

    frame_index: int
    measurement_timestamp_s: float
    arrival_timestamp_s: float
    observed_target_count: int
    observed_resource_count: int
    candidate_mask_shape: tuple[int, int]
    candidate_mask_true_edges: tuple[tuple[int, int], ...]
    rule_cost_matrix: tuple[tuple[float, ...], ...]
    teacher_edges: tuple[tuple[int, int], ...]
    candidate_selected_edges: tuple[tuple[int, int], ...]
    effective_selected_edges: tuple[tuple[int, int], ...]
    residual_ranking: tuple[A1V3EdgeResidualRank, ...]
    target_demand_slots: tuple[int, ...]
    pre_projection_reason_codes: tuple[str, ...]
    post_projection_reason_codes: tuple[str, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "A1V3AdapterFrameEvidence":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "frame_index",
                "measurement_timestamp_s",
                "arrival_timestamp_s",
                "observed_target_count",
                "observed_resource_count",
                "candidate_mask",
                "rule_cost_matrix",
                "teacher_edges",
                "candidate_selected_edges",
                "effective_selected_edges",
                "residual_ranking",
                "anonymous_target_demand_slots",
                "pre_projection_reason_codes",
                "post_projection_reason_codes",
            },
            "adapter_evidence_fields_mismatch",
        )
        if payload["schema_version"] != A1_V3_ADAPTER_EVIDENCE_SCHEMA_V1:
            _fail("adapter_evidence_schema_mismatch")
        mask = _strict_mapping(
            payload["candidate_mask"],
            {"shape", "true_edges"},
            "adapter_candidate_mask_fields_mismatch",
        )
        shape_values = _sequence(mask["shape"], "candidate_mask.shape")
        if len(shape_values) != 2:
            _fail("adapter_candidate_mask_shape_invalid")
        ranking_items: list[A1V3EdgeResidualRank] = []
        for index, raw_item in enumerate(
            _sequence(payload["residual_ranking"], "residual_ranking")
        ):
            item = _strict_mapping(
                raw_item,
                {"edge", "residual", "rank"},
                "adapter_residual_rank_fields_mismatch",
            )
            ranking_items.append(
                A1V3EdgeResidualRank(
                    edge=_edge_pair(item["edge"], f"residual_ranking[{index}].edge"),
                    residual=_finite_float(
                        item["residual"], f"residual_ranking[{index}].residual"
                    ),
                    rank=_positive_int(
                        item["rank"], f"residual_ranking[{index}].rank"
                    ),
                )
            )
        return cls(
            frame_index=_nonnegative_int(payload["frame_index"], "frame_index"),
            measurement_timestamp_s=_finite_float(
                payload["measurement_timestamp_s"], "measurement_timestamp_s"
            ),
            arrival_timestamp_s=_finite_float(
                payload["arrival_timestamp_s"], "arrival_timestamp_s"
            ),
            observed_target_count=_nonnegative_int(
                payload["observed_target_count"], "observed_target_count"
            ),
            observed_resource_count=_nonnegative_int(
                payload["observed_resource_count"], "observed_resource_count"
            ),
            candidate_mask_shape=(
                _nonnegative_int(shape_values[0], "candidate_mask.shape[0]"),
                _nonnegative_int(shape_values[1], "candidate_mask.shape[1]"),
            ),
            candidate_mask_true_edges=_edge_pairs(
                mask["true_edges"], "candidate_mask.true_edges"
            ),
            rule_cost_matrix=tuple(
                tuple(
                    _finite_float(
                        cost, f"rule_cost_matrix[{row_index}][{column_index}]"
                    )
                    for column_index, cost in enumerate(
                        _sequence(row, f"rule_cost_matrix[{row_index}]")
                    )
                )
                for row_index, row in enumerate(
                    _sequence(payload["rule_cost_matrix"], "rule_cost_matrix")
                )
            ),
            teacher_edges=_edge_pairs(payload["teacher_edges"], "teacher_edges"),
            candidate_selected_edges=_edge_pairs(
                payload["candidate_selected_edges"], "candidate_selected_edges"
            ),
            effective_selected_edges=_edge_pairs(
                payload["effective_selected_edges"], "effective_selected_edges"
            ),
            residual_ranking=tuple(ranking_items),
            target_demand_slots=tuple(
                _nonnegative_int(item, f"anonymous_target_demand_slots[{index}]")
                for index, item in enumerate(
                    _sequence(
                        payload["anonymous_target_demand_slots"],
                        "anonymous_target_demand_slots",
                    )
                )
            ),
            pre_projection_reason_codes=_string_tuple(
                payload["pre_projection_reason_codes"],
                "pre_projection_reason_codes",
            ),
            post_projection_reason_codes=_string_tuple(
                payload["post_projection_reason_codes"],
                "post_projection_reason_codes",
            ),
        )


@dataclass(frozen=True)
class A1V3OfflineFrameSidecar:
    """Offline-only class and identity labels, independent of online input."""

    frame_index: int
    frame_class: str
    hard_negative: bool
    action_change_type: str
    hard_negative_type: str | None
    truth_target_labels: tuple[str, ...]
    actor_labels: tuple[str, ...]
    object_labels: tuple[str, ...]
    center_global_track_labels: tuple[str, ...]

    @property
    def classification_signature(self) -> tuple[int, str, bool, str, str | None]:
        return (
            self.frame_index,
            self.frame_class,
            self.hard_negative,
            self.action_change_type,
            self.hard_negative_type,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "A1V3OfflineFrameSidecar":
        payload = _strict_mapping(
            value,
            {
                "schema_version",
                "frame_index",
                "classification",
                "offline_identity_labels",
            },
            "offline_sidecar_fields_mismatch",
        )
        if payload["schema_version"] != A1_V3_OFFLINE_SIDECAR_SCHEMA_V1:
            _fail("offline_sidecar_schema_mismatch")
        classification = _strict_mapping(
            payload["classification"],
            {
                "frame_class",
                "hard_negative",
                "action_change_type",
                "hard_negative_type",
            },
            "offline_sidecar_classification_fields_mismatch",
        )
        identity = _strict_mapping(
            payload["offline_identity_labels"],
            {
                "truth_target_labels",
                "actor_labels",
                "object_labels",
                "center_global_track_labels",
            },
            "offline_sidecar_identity_fields_mismatch",
        )
        hard_negative = _bool(
            classification["hard_negative"], "classification.hard_negative"
        )
        hard_type = classification["hard_negative_type"]
        if hard_type is not None:
            hard_type = _nonempty_string(
                hard_type, "classification.hard_negative_type"
            )
        return cls(
            frame_index=_nonnegative_int(payload["frame_index"], "frame_index"),
            frame_class=_nonempty_string(
                classification["frame_class"], "classification.frame_class"
            ),
            hard_negative=hard_negative,
            action_change_type=_nonempty_string(
                classification["action_change_type"],
                "classification.action_change_type",
            ),
            hard_negative_type=hard_type,
            truth_target_labels=_string_tuple(
                identity["truth_target_labels"], "truth_target_labels"
            ),
            actor_labels=_string_tuple(identity["actor_labels"], "actor_labels"),
            object_labels=_string_tuple(
                identity["object_labels"], "object_labels"
            ),
            center_global_track_labels=_string_tuple(
                identity["center_global_track_labels"],
                "center_global_track_labels",
            ),
        )


@dataclass(frozen=True)
class A1V3BoundSourceFile:
    name: str
    path: Path
    sha256: str


@dataclass(frozen=True)
class A1V3NearTieBoundary:
    boundary_id: str
    file_sha256: str


@dataclass(frozen=True)
class A1V3WriterContract:
    request: A1V3FrozenRequest
    descriptor: A1V3ContractDescriptor
    generator_config: A1V3GeneratorConfig
    global_allocation: A1V3GlobalAllocation
    registry: A1V3SeedRegistry
    schedule: A1V3GenerationSchedule
    near_tie_boundary: A1V3NearTieBoundary
    sidecar_classification_policy: A1V3SidecarClassificationPolicy
    source_files: tuple[A1V3BoundSourceFile, ...]


@dataclass(frozen=True)
class A1V3StagedEpisodeSummary:
    episode_id: str
    seed: int
    split: str
    frame_count: int
    positive_frame_count: int
    negative_frame_count: int
    hard_negative_frame_count: int
    online_frames_sha256: str
    offline_labels_sha256: str
    offline_identity_audit_availability: str


@dataclass(frozen=True)
class A1V3DatasetFinalizationSummary:
    dataset_id: str
    dataset_dir: Path
    episode_count: int
    unique_seed_count: int
    frame_count: int
    positive_frame_count: int
    negative_frame_count: int
    hard_negative_frame_count: int
    online_frames_sha256: str
    offline_labels_sha256: str
    manifest_sha256: str
    offline_identity_audit_availability: str


@dataclass(frozen=True)
class _StagedEpisode:
    schedule_index: int
    scheduled: A1V3ScheduledEpisode
    online_frames: tuple[A1V3OnlineFrame, ...]
    offline_labels: tuple[A1V3OfflineLabel, ...]
    online_frames_sha256: str
    offline_labels_sha256: str


def build_a1_v3_online_frame(
    scheduled_episode: A1V3ScheduledEpisode,
    evidence: A1V3AdapterFrameEvidence,
) -> A1V3OnlineFrame:
    """Build and strictly parse one anonymous online record.

    Arrival time must be strictly later than measurement time.  This adapter
    therefore cannot accept one timestamp copied into both contract fields.
    """

    if not isinstance(scheduled_episode, A1V3ScheduledEpisode):
        _fail("scheduled_episode_type_required")
    if not isinstance(evidence, A1V3AdapterFrameEvidence):
        _fail("adapter_frame_evidence_type_required")
    if evidence.arrival_timestamp_s <= evidence.measurement_timestamp_s:
        _fail(
            "adapter_dual_timestamp_not_distinct",
            "arrival_timestamp_s must be later than measurement_timestamp_s",
        )
    candidate_edges = evidence.candidate_mask_true_edges
    if evidence.candidate_mask_shape != (
        evidence.observed_target_count,
        evidence.observed_resource_count,
    ):
        _fail("adapter_candidate_mask_observed_shape_mismatch")
    if len(evidence.rule_cost_matrix) != evidence.candidate_mask_shape[0] or any(
        len(row) != evidence.candidate_mask_shape[1]
        for row in evidence.rule_cost_matrix
    ):
        _fail("adapter_rule_cost_matrix_shape_mismatch")
    if any(not isfinite(float(cost)) for row in evidence.rule_cost_matrix for cost in row):
        _fail("adapter_rule_cost_matrix_nonfinite")
    if any(
        row >= evidence.candidate_mask_shape[0]
        or column >= evidence.candidate_mask_shape[1]
        for row, column in candidate_edges
    ):
        _fail("adapter_candidate_edge_out_of_bounds")
    candidate_edge_rule_costs = tuple(
        evidence.rule_cost_matrix[row][column]
        for row, column in candidate_edges
    )
    near_tie_margins = compute_a1_v3_near_tie_target_margins(
        candidate_edges,
        candidate_edge_rule_costs,
        target_count=evidence.observed_target_count,
    )
    near_tie_qualifying_count = sum(item.qualifies for item in near_tie_margins)
    near_tie_reason = (
        A1_V3_NEAR_TIE_REASON_MET
        if near_tie_qualifying_count > 0
        else A1_V3_NEAR_TIE_REASON_NOT_MET
    )
    candidate_edge_cost_payload = [
        {"edge": list(edge), "rule_cost": cost}
        for edge, cost in zip(
            candidate_edges, candidate_edge_rule_costs, strict=True
        )
    ]
    payload = {
        "schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
        "record_kind": "online_identity_free_diagnostic_frame",
        "source": {
            "split": scheduled_episode.split,
            "scenario_family": scheduled_episode.scenario_family,
            "cell_id": scheduled_episode.cell_id,
            "seed": scheduled_episode.seed,
            "episode_id": scheduled_episode.episode_id,
            "frame_index": evidence.frame_index,
            "measurement_timestamp_s": evidence.measurement_timestamp_s,
            "arrival_timestamp_s": evidence.arrival_timestamp_s,
            "configured_target_count": scheduled_episode.configured_target_count,
            "configured_resource_count": scheduled_episode.configured_resource_count,
        },
        "observed_scale": {
            "anonymous_target_count": evidence.observed_target_count,
            "anonymous_resource_count": evidence.observed_resource_count,
        },
        "candidate_edge_indices": [list(edge) for edge in candidate_edges],
        "candidate_edge_indices_sha256": canonical_json_sha256(
            [list(edge) for edge in candidate_edges]
        ),
        "teacher_mask_observability": {
            "teacher_edge_count": len(evidence.teacher_edges),
            "teacher_edges_in_candidate_mask_count": len(
                set(evidence.teacher_edges) & set(candidate_edges)
            ),
            "all_teacher_edges_in_candidate_mask": set(
                evidence.teacher_edges
            ).issubset(set(candidate_edges)),
        },
        "model_residual_ranking": {
            "rank_direction": "ascending_cost_residual_then_edge",
            "items": [item.to_dict() for item in evidence.residual_ranking],
        },
        "action_mask": {
            "shape": list(evidence.candidate_mask_shape),
            "true_count": len(candidate_edges),
            "content_sha256": action_mask_content_sha256(
                evidence.candidate_mask_shape, candidate_edges
            ),
        },
        "rule_cost_near_tie": {
            "boundary_id": A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
            "maximum_absolute_gap": A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
            "maximum_relative_gap": A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
            "relative_denominator_floor": (
                A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR
            ),
            "qualification_logic": "absolute_and_relative",
            "candidate_edge_costs": candidate_edge_cost_payload,
            "candidate_edge_costs_sha256": canonical_json_sha256(
                candidate_edge_cost_payload
            ),
            "evaluated_target_count": len(near_tie_margins),
            "qualifying_target_count": near_tie_qualifying_count,
            "target_margins": [item.to_dict() for item in near_tie_margins],
            "reason_code": near_tie_reason,
        },
        "anonymous_target_demand_slots": list(evidence.target_demand_slots),
        "target_demand_slots_sha256": canonical_json_sha256(
            list(evidence.target_demand_slots)
        ),
        "selected_edges": {
            "teacher": [list(edge) for edge in evidence.teacher_edges],
            "candidate_pre_projection": [
                list(edge) for edge in evidence.candidate_selected_edges
            ],
            "effective_post_projection": [
                list(edge) for edge in evidence.effective_selected_edges
            ],
        },
        "projection": {
            "pre_projection_reason_codes": list(
                evidence.pre_projection_reason_codes
            ),
            "post_projection_reason_codes": list(
                evidence.post_projection_reason_codes
            ),
        },
        "online_truth_use_count": 0,
        "center_identity_ownership": {
            "owner": "center",
            "learning_create_allowed": False,
            "learning_rewrite_allowed": False,
        },
        "permissions": _false_permissions(),
    }
    return A1V3OnlineFrame.from_dict(payload)


def build_a1_v3_offline_label(
    scheduled_episode: A1V3ScheduledEpisode,
    online_frame: A1V3OnlineFrame,
    sidecar: A1V3OfflineFrameSidecar,
    *,
    request: A1V3FrozenRequest,
) -> A1V3OfflineLabel:
    """Bind an offline-only sidecar to the exact canonical online payload."""

    if sidecar.frame_index != online_frame.source.frame_index:
        _fail("offline_sidecar_frame_index_mismatch")
    if online_frame.source.episode_key != scheduled_episode.episode_key:
        _fail("offline_sidecar_episode_mismatch")
    if (
        scheduled_episode.scenario_family == "near_tie_hard_negative"
        and sidecar.hard_negative
        and sidecar.hard_negative_type != "near_tie_but_teacher_keeps_r0"
    ):
        _fail("near_tie_cell_hard_negative_type_mismatch")
    if (
        sidecar.hard_negative
        and sidecar.hard_negative_type == "near_tie_but_teacher_keeps_r0"
        and (
            online_frame.near_tie_qualifying_target_count < 1
            or online_frame.near_tie_reason_code != A1_V3_NEAR_TIE_REASON_MET
        )
    ):
        _fail("near_tie_hard_negative_boundary_not_met")
    payload = {
        "schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
        "record_kind": "offline_d6_audit_label",
        "source_ref": {
            "split": scheduled_episode.split,
            "cell_id": scheduled_episode.cell_id,
            "seed": scheduled_episode.seed,
            "episode_id": scheduled_episode.episode_id,
            "frame_index": sidecar.frame_index,
            "online_payload_sha256": online_frame.content_sha256,
        },
        "classification": {
            "frame_class": sidecar.frame_class,
            "hard_negative": sidecar.hard_negative,
            "action_change_type": sidecar.action_change_type,
            "hard_negative_type": sidecar.hard_negative_type,
        },
        "offline_identity_labels": {
            "truth_target_labels": list(sidecar.truth_target_labels),
            "actor_labels": list(sidecar.actor_labels),
            "object_labels": list(sidecar.object_labels),
            "center_global_track_labels": list(
                sidecar.center_global_track_labels
            ),
        },
        "identity_provenance": {
            "global_track_id_owner": "center",
            "learning_path_created_global_track_id_count": 0,
            "learning_path_rewritten_global_track_id_count": 0,
        },
        "permissions": _false_permissions(),
    }
    return A1V3OfflineLabel.from_dict(
        payload,
        action_change_types=request.action_change_types,
        hard_negative_types=request.hard_negative_types,
    )


def derive_a1_v3_offline_sidecars(
    scheduled_episode: A1V3ScheduledEpisode,
    online_frames: Sequence[A1V3OnlineFrame],
    *,
    request: A1V3FrozenRequest,
    policy: A1V3SidecarClassificationPolicy,
) -> tuple[A1V3OfflineFrameSidecar, ...]:
    """Build classification-only sidecars; callers may add identity labels."""

    classifications = derive_a1_v3_frame_classifications(
        scheduled_episode,
        online_frames,
        request=request,
        policy=policy,
    )
    return tuple(
        A1V3OfflineFrameSidecar(
            frame_index=item.frame_index,
            frame_class=item.frame_class,
            hard_negative=item.hard_negative,
            action_change_type=item.action_change_type,
            hard_negative_type=item.hard_negative_type,
            truth_target_labels=(),
            actor_labels=(),
            object_labels=(),
            center_global_track_labels=(),
        )
        for item in classifications
    )


def load_a1_v3_writer_contract(
    *,
    request_path: str | Path = DEFAULT_A1_V3_REQUEST_PATH,
    exclusion_registry_path: str | Path = DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
    contract_path: str | Path = DEFAULT_A1_V3_DATA_CONTRACT_PATH,
    generator_config_path: str | Path = DEFAULT_A1_V3_GENERATOR_CONFIG_PATH,
    global_registry_path: str | Path = DEFAULT_A1_V3_GLOBAL_SEED_REGISTRY_PATH,
    registry_path: str | Path = DEFAULT_A1_V3_MAIN_SEED_REGISTRY_PATH,
    schedule_path: str | Path = DEFAULT_A1_V3_GENERATION_SCHEDULE_PATH,
    near_tie_boundary_path: str | Path = DEFAULT_A1_V3_NEAR_TIE_BOUNDARY_PATH,
    sidecar_classification_policy_path: str | Path = (
        DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH
    ),
) -> A1V3WriterContract:
    """Load the complete frozen plan used to bind a future producer writer."""

    request_path = Path(request_path)
    exclusion_registry_path = Path(exclusion_registry_path)
    contract_path = Path(contract_path)
    generator_config_path = Path(generator_config_path)
    global_registry_path = Path(global_registry_path)
    registry_path = Path(registry_path)
    schedule_path = Path(schedule_path)
    near_tie_boundary_path = Path(near_tie_boundary_path)
    sidecar_classification_policy_path = Path(sidecar_classification_policy_path)

    request = load_a1_v3_frozen_request(request_path)
    forbidden, exclusion_sha = load_a1_v3_exclusion_registry(
        exclusion_registry_path
    )
    descriptor = load_a1_v3_contract_descriptor(
        contract_path,
        request=request,
        exclusion_registry_file_sha256=exclusion_sha,
    )
    config = load_a1_v3_generator_config(
        generator_config_path,
        request=request,
        descriptor=descriptor,
        exclusion_registry_file_sha256=exclusion_sha,
    )
    global_allocation = load_a1_v3_global_seed_allocation(
        global_registry_path,
        config=config,
        request=request,
        descriptor=descriptor,
        exclusion_registry_file_sha256=exclusion_sha,
    )
    registry = load_a1_v3_main_seed_registry(
        registry_path,
        request=request,
        exclusion_registry_file_sha256=exclusion_sha,
        known_forbidden_seeds=forbidden,
        config=config,
        global_allocation=global_allocation,
    )
    schedule = load_a1_v3_generation_schedule(
        schedule_path,
        request=request,
        descriptor=descriptor,
        registry=registry,
    )
    near_tie_boundary = load_a1_v3_near_tie_boundary(near_tie_boundary_path)
    sidecar_policy = load_a1_v3_sidecar_classification_policy(
        sidecar_classification_policy_path,
        request=request,
        near_tie_boundary_file_sha256=near_tie_boundary.file_sha256,
    )
    classifier_source_path = Path(__file__).with_name(
        Path(A1_V3_SIDECAR_CLASSIFIER_LOGICAL_PATH).name
    )
    try:
        classifier_source_sha256 = sha256(classifier_source_path.read_bytes()).hexdigest()
    except OSError as exc:
        _fail("sidecar_classifier_source_read_failed", str(exc))
    return A1V3WriterContract(
        request=request,
        descriptor=descriptor,
        generator_config=config,
        global_allocation=global_allocation,
        registry=registry,
        schedule=schedule,
        near_tie_boundary=near_tie_boundary,
        sidecar_classification_policy=sidecar_policy,
        source_files=(
            A1V3BoundSourceFile("request", request_path, request.file_sha256),
            A1V3BoundSourceFile(
                "exclusion_registry", exclusion_registry_path, exclusion_sha
            ),
            A1V3BoundSourceFile("data_contract", contract_path, descriptor.file_sha256),
            A1V3BoundSourceFile(
                "generator_config", generator_config_path, config.file_sha256
            ),
            A1V3BoundSourceFile(
                "global_seed_registry",
                global_registry_path,
                global_allocation.file_sha256,
            ),
            A1V3BoundSourceFile("main_seed_registry", registry_path, registry.file_sha256),
            A1V3BoundSourceFile("generation_schedule", schedule_path, schedule.file_sha256),
            A1V3BoundSourceFile(
                "near_tie_boundary",
                near_tie_boundary_path,
                near_tie_boundary.file_sha256,
            ),
            A1V3BoundSourceFile(
                "sidecar_classification_policy",
                sidecar_classification_policy_path,
                sidecar_policy.file_sha256,
            ),
            A1V3BoundSourceFile(
                "sidecar_classifier_source",
                classifier_source_path,
                classifier_source_sha256,
            ),
        ),
    )


def load_a1_v3_near_tie_boundary(
    path: str | Path = DEFAULT_A1_V3_NEAR_TIE_BOUNDARY_PATH,
) -> A1V3NearTieBoundary:
    file_path = Path(path)
    try:
        content = file_path.read_bytes()
    except OSError as exc:
        _fail("near_tie_boundary_read_failed", str(exc))
    try:
        payload = json.loads(content.decode("ascii"), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("near_tie_boundary_json_invalid", str(exc))
    payload = _strict_mapping(
        payload,
        {
            "schema_version",
            "boundary_id",
            "status",
            "maximum_absolute_gap",
            "maximum_relative_gap",
            "relative_denominator_floor",
            "qualification_logic",
            "reason_codes",
            "permissions",
        },
        "near_tie_boundary_fields_mismatch",
    )
    if payload != {
        "schema_version": "d3_a1_v3_rule_cost_near_tie_boundary_v1",
        "boundary_id": A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
        "status": "frozen_for_a1_v3_generation",
        "maximum_absolute_gap": A1_V3_NEAR_TIE_MAXIMUM_ABSOLUTE_GAP,
        "maximum_relative_gap": A1_V3_NEAR_TIE_MAXIMUM_RELATIVE_GAP,
        "relative_denominator_floor": A1_V3_NEAR_TIE_RELATIVE_DENOMINATOR_FLOOR,
        "qualification_logic": "absolute_and_relative",
        "reason_codes": {
            "boundary_met": A1_V3_NEAR_TIE_REASON_MET,
            "boundary_not_met": A1_V3_NEAR_TIE_REASON_NOT_MET,
        },
        "permissions": _false_permissions(),
    }:
        _fail("near_tie_boundary_content_mismatch")
    return A1V3NearTieBoundary(
        boundary_id=A1_V3_NEAR_TIE_BOUNDARY_ID_V1,
        file_sha256=sha256(content).hexdigest(),
    )


class A1V3DatasetWriter:
    """Episode-atomic A1 v3 stager and all-inventory finalizer."""

    def __init__(
        self,
        dataset_dir: str | Path,
        *,
        dataset_id: str,
        contract: A1V3WriterContract,
    ) -> None:
        self.dataset_dir = Path(dataset_dir)
        self.dataset_id = _dataset_id(dataset_id)
        self.contract = contract
        self._stage_dir = self.dataset_dir / _STAGING_DIRECTORY
        self._session_path = self._stage_dir / _STAGING_SESSION_FILENAME
        self._episode_dir = self._stage_dir / _STAGING_EPISODE_DIRECTORY
        self._schedule_index = {
            episode.episode_key: index
            for index, episode in enumerate(self.contract.schedule.episodes)
        }
        self._episode_id_index = {
            episode.episode_id: index
            for index, episode in enumerate(self.contract.schedule.episodes)
        }
        self._verify_bound_sources()
        self._validate_contract_inventory()
        self._open_or_create_session()
        self._staged_episodes = self._load_all_staged_episodes()

    @classmethod
    def from_frozen_paths(
        cls,
        dataset_dir: str | Path,
        *,
        dataset_id: str,
        request_path: str | Path = DEFAULT_A1_V3_REQUEST_PATH,
        exclusion_registry_path: str | Path = DEFAULT_A1_V3_EXCLUSION_REGISTRY_PATH,
        contract_path: str | Path = DEFAULT_A1_V3_DATA_CONTRACT_PATH,
        generator_config_path: str | Path = DEFAULT_A1_V3_GENERATOR_CONFIG_PATH,
        global_registry_path: str | Path = DEFAULT_A1_V3_GLOBAL_SEED_REGISTRY_PATH,
        registry_path: str | Path = DEFAULT_A1_V3_MAIN_SEED_REGISTRY_PATH,
        schedule_path: str | Path = DEFAULT_A1_V3_GENERATION_SCHEDULE_PATH,
        near_tie_boundary_path: str | Path = DEFAULT_A1_V3_NEAR_TIE_BOUNDARY_PATH,
        sidecar_classification_policy_path: str | Path = (
            DEFAULT_A1_V3_SIDECAR_CLASSIFICATION_POLICY_PATH
        ),
    ) -> "A1V3DatasetWriter":
        contract = load_a1_v3_writer_contract(
            request_path=request_path,
            exclusion_registry_path=exclusion_registry_path,
            contract_path=contract_path,
            generator_config_path=generator_config_path,
            global_registry_path=global_registry_path,
            registry_path=registry_path,
            schedule_path=schedule_path,
            near_tie_boundary_path=near_tie_boundary_path,
            sidecar_classification_policy_path=sidecar_classification_policy_path,
        )
        return cls(dataset_dir, dataset_id=dataset_id, contract=contract)

    @property
    def staged_episode_count(self) -> int:
        return len(self.staged_episode_indices)

    @property
    def staged_episode_indices(self) -> tuple[int, ...]:
        """Return a disk-refreshed contiguous schedule prefix without payloads."""

        self._verify_bound_sources()
        staged = self._load_all_staged_episodes()
        indices = tuple(sorted(staged))
        if indices != tuple(range(len(indices))):
            _fail("writer_staged_episode_inventory_not_prefix")
        self._staged_episodes = staged
        return indices

    @property
    def staged_episode_ids(self) -> tuple[str, ...]:
        """Return schedule-bound ids for the validated staged prefix."""

        return tuple(
            self.contract.schedule.episodes[index].episode_id
            for index in self.staged_episode_indices
        )

    def stage_episode(
        self,
        scheduled_episode: A1V3ScheduledEpisode,
        online_evidence: Sequence[A1V3AdapterFrameEvidence],
        offline_sidecars: Sequence[A1V3OfflineFrameSidecar] | None = None,
    ) -> A1V3StagedEpisodeSummary:
        """Validate and atomically stage one complete scheduled episode."""

        self._verify_bound_sources()
        expected = self._expected_schedule_episode(scheduled_episode)
        index = self._schedule_index[expected.episode_key]
        output_path = self._episode_path(index)
        if output_path.exists() or index in self._staged_episodes:
            _fail("writer_duplicate_episode", expected.episode_id)

        evidence_by_index: dict[int, A1V3AdapterFrameEvidence] = {}
        for evidence in online_evidence:
            if not isinstance(evidence, A1V3AdapterFrameEvidence):
                _fail("adapter_frame_evidence_type_required")
            if evidence.frame_index in evidence_by_index:
                _fail("writer_duplicate_online_frame", str(evidence.frame_index))
            evidence_by_index[evidence.frame_index] = evidence
        expected_indices = set(range(len(evidence_by_index)))
        if set(evidence_by_index) != expected_indices:
            _fail("writer_episode_frame_index_gap")

        online_frames = [
            build_a1_v3_online_frame(expected, evidence_by_index[frame_index])
            for frame_index in sorted(evidence_by_index)
        ]
        derived_sidecars = derive_a1_v3_offline_sidecars(
            expected,
            online_frames,
            request=self.contract.request,
            policy=self.contract.sidecar_classification_policy,
        )
        if offline_sidecars is None:
            sidecar_by_index = {
                sidecar.frame_index: sidecar for sidecar in derived_sidecars
            }
        else:
            sidecar_by_index: dict[int, A1V3OfflineFrameSidecar] = {}
            for sidecar in offline_sidecars:
                if not isinstance(sidecar, A1V3OfflineFrameSidecar):
                    _fail("offline_frame_sidecar_type_required")
                if sidecar.frame_index in sidecar_by_index:
                    _fail("writer_duplicate_offline_frame", str(sidecar.frame_index))
                sidecar_by_index[sidecar.frame_index] = sidecar
            if set(evidence_by_index) != set(sidecar_by_index):
                _fail("writer_online_offline_frame_inventory_mismatch")
            for derived in derived_sidecars:
                if sidecar_by_index[derived.frame_index].classification_signature != (
                    derived.classification_signature
                ):
                    _fail(
                        "writer_offline_sidecar_classification_mismatch",
                        str(derived.frame_index),
                    )

        offline_labels: list[A1V3OfflineLabel] = []
        for frame in online_frames:
            frame_index = frame.source.frame_index
            label = build_a1_v3_offline_label(
                expected,
                frame,
                sidecar_by_index[frame_index],
                request=self.contract.request,
            )
            offline_labels.append(label)
        self._validate_episode_records(
            expected, tuple(online_frames), tuple(offline_labels)
        )
        payload = self._stage_payload(
            index, expected, tuple(online_frames), tuple(offline_labels)
        )
        _atomic_write_new(output_path, canonical_json_line(payload))
        staged = self._load_staged_episode(index, output_path)
        self._staged_episodes[index] = staged
        return self._stage_summary(staged)

    def finalize(self) -> A1V3DatasetFinalizationSummary:
        """Write the canonical three-file dataset after the full gate passes."""

        self._verify_bound_sources()
        staged = self._load_all_staged_episodes()
        self._staged_episodes = staged
        expected_indices = set(range(len(self.contract.schedule.episodes)))
        if set(staged) != expected_indices:
            missing = sorted(expected_indices - set(staged))
            _fail(
                "writer_schedule_episode_coverage_incomplete",
                f"missing_count={len(missing)}",
            )
        final_paths = (
            self.dataset_dir / A1_V3_ONLINE_FRAMES_FILENAME,
            self.dataset_dir / A1_V3_OFFLINE_LABELS_FILENAME,
            self.dataset_dir / A1_V3_MANIFEST_FILENAME,
        )
        if any(path.exists() or path.is_symlink() for path in final_paths):
            _fail("writer_final_artifact_already_exists")

        pairs: list[tuple[A1V3OnlineFrame, A1V3OfflineLabel]] = []
        for index in sorted(staged):
            episode = staged[index]
            pairs.extend(
                zip(episode.online_frames, episode.offline_labels, strict=True)
            )
        pairs.sort(
            key=lambda pair: (
                pair[0].source.cell_id,
                pair[0].source.seed,
                pair[0].source.episode_id,
                pair[0].source.frame_index,
            )
        )
        frame_keys = [frame.frame_key for frame, _ in pairs]
        if len(set(frame_keys)) != len(frame_keys):
            _fail("writer_duplicate_frame_across_episodes")
        online_bytes = b"".join(
            canonical_json_line(frame.to_dict()) for frame, _ in pairs
        )
        offline_bytes = b"".join(
            canonical_json_line(label.to_dict()) for _, label in pairs
        )
        online_sha = sha256(online_bytes).hexdigest()
        offline_sha = sha256(offline_bytes).hexdigest()
        manifest = self._manifest_payload(
            pairs,
            online_frames_sha256=online_sha,
            offline_labels_sha256=offline_sha,
        )
        manifest_bytes = canonical_json_line(manifest)

        _atomic_write_new(final_paths[0], online_bytes)
        _atomic_write_new(final_paths[1], offline_bytes)
        _atomic_write_new(final_paths[2], manifest_bytes)
        counts = manifest["counts"]
        identity = manifest["offline_identity_audit"]
        return A1V3DatasetFinalizationSummary(
            dataset_id=self.dataset_id,
            dataset_dir=self.dataset_dir,
            episode_count=counts["episode_count"],
            unique_seed_count=counts["unique_seed_count"],
            frame_count=counts["frame_count"],
            positive_frame_count=counts["positive_frame_count"],
            negative_frame_count=counts["negative_frame_count"],
            hard_negative_frame_count=counts["hard_negative_frame_count"],
            online_frames_sha256=online_sha,
            offline_labels_sha256=offline_sha,
            manifest_sha256=sha256(manifest_bytes).hexdigest(),
            offline_identity_audit_availability=identity["availability"],
        )

    def _verify_bound_sources(self) -> None:
        for source in self.contract.source_files:
            if source.path.is_symlink():
                _fail("writer_source_symlink_forbidden", source.name)
            try:
                content = source.path.read_bytes()
            except OSError as exc:
                _fail("writer_source_read_failed", f"{source.name}: {exc}")
            if sha256(content).hexdigest() != source.sha256:
                _fail("writer_source_hash_drift", source.name)

    def _validate_contract_inventory(self) -> None:
        request = self.contract.request
        schedule = self.contract.schedule
        registry = self.contract.registry
        if (
            request.requested_cell_count != 15
            or request.requested_episode_count != 300
            or request.requested_unique_seed_count != 300
            or request.minimum_total_observable_frame_count != 2700
            or request.minimum_positive_frame_count != 900
            or request.minimum_negative_frame_count != 900
            or request.minimum_hard_negative_frame_count != 450
        ):
            _fail("writer_fixed_request_inventory_mismatch")
        episodes = schedule.episodes
        if len(episodes) != 300:
            _fail("writer_schedule_episode_count_mismatch")
        if len({item.episode_id for item in episodes}) != 300:
            _fail("writer_schedule_episode_id_duplicate")
        if len({item.seed for item in episodes}) != 300:
            _fail("writer_schedule_seed_inventory_mismatch")
        if len({item.cell_id for item in episodes}) != 15:
            _fail("writer_schedule_cell_inventory_mismatch")
        if Counter(item.split for item in episodes) != Counter(
            A1_V3_SPLIT_SEED_COUNTS
        ):
            _fail("writer_schedule_split_inventory_mismatch")
        if {
            split: tuple(sorted(item.seed for item in episodes if item.split == split))
            for split in A1_V3_SPLITS
        } != dict(registry.split_seed_values):
            _fail("writer_schedule_registry_split_mismatch")
        if (
            schedule.minimum_observable_frames != 2700
            or schedule.minimum_positive_frames != 900
            or schedule.minimum_negative_frames != 900
            or schedule.minimum_hard_negative_frames != 450
        ):
            _fail("writer_schedule_quota_inventory_mismatch")
        cells = request.cells_by_id
        cell_split_counts: dict[str, Counter[str]] = {
            cell_id: Counter() for cell_id in cells
        }
        for episode in episodes:
            cell = cells.get(episode.cell_id)
            if cell is None or (
                episode.scenario_family != cell.scenario_family
                or episode.configured_target_count != cell.configured_target_count
                or episode.configured_resource_count != cell.configured_resource_count
            ):
                _fail("writer_schedule_cell_configuration_mismatch")
            cell_split_counts[episode.cell_id][episode.split] += 1
        expected_per_cell = Counter(A1_V3_CELL_SPLIT_SEED_COUNTS)
        if any(counts != expected_per_cell for counts in cell_split_counts.values()):
            _fail("writer_schedule_cell_split_inventory_mismatch")

    def _open_or_create_session(self) -> None:
        if self.dataset_dir.is_symlink():
            _fail("writer_dataset_directory_symlink_forbidden")
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        final_names = {
            A1_V3_ONLINE_FRAMES_FILENAME,
            A1_V3_OFFLINE_LABELS_FILENAME,
            A1_V3_MANIFEST_FILENAME,
        }
        if any((self.dataset_dir / name).exists() for name in final_names):
            _fail("writer_final_artifact_already_exists")
        if self._stage_dir.is_symlink() or self._episode_dir.is_symlink():
            _fail("writer_staging_symlink_forbidden")
        self._stage_dir.mkdir(exist_ok=True)
        self._episode_dir.mkdir(exist_ok=True)
        allowed_stage_names = {
            _STAGING_SESSION_FILENAME,
            _STAGING_EPISODE_DIRECTORY,
        }
        unexpected = sorted(
            path.name
            for path in self._stage_dir.iterdir()
            if path.name not in allowed_stage_names
        )
        if unexpected:
            _fail("writer_unexpected_staging_entry", repr(unexpected))
        expected_session = self._session_payload()
        if self._session_path.exists():
            if self._session_path.is_symlink():
                _fail("writer_session_symlink_forbidden")
            actual = _read_canonical_json(self._session_path, "writer_session")
            if actual != expected_session:
                _fail("writer_session_binding_mismatch")
        else:
            if any(self._episode_dir.iterdir()):
                _fail("writer_orphan_staged_episode")
            _atomic_write_new(
                self._session_path, canonical_json_line(expected_session)
            )

    def _session_payload(self) -> dict[str, Any]:
        return {
            "schema_version": A1_V3_WRITER_SESSION_SCHEMA_V1,
            "record_kind": "a1_v3_episode_staging_session",
            "dataset_id": self.dataset_id,
            "contract_bindings": {
                "request_id": self.contract.request.request_id,
                "request_file_sha256": self.contract.request.file_sha256,
                "contract_id": self.contract.descriptor.contract_id,
                "contract_file_sha256": self.contract.descriptor.file_sha256,
                "registry_id": self.contract.registry.registry_id,
                "registry_file_sha256": self.contract.registry.file_sha256,
                "schedule_id": self.contract.schedule.schedule_id,
                "schedule_file_sha256": self.contract.schedule.file_sha256,
                "schedule_inventory_sha256": _schedule_inventory_sha256(
                    self.contract.schedule.episodes
                ),
                "near_tie_boundary_id": (
                    self.contract.near_tie_boundary.boundary_id
                ),
                "near_tie_boundary_file_sha256": (
                    self.contract.near_tie_boundary.file_sha256
                ),
            },
            "source": {
                "git_commit": self.contract.schedule.source_git_commit,
                "repository_dirty": self.contract.schedule.repository_dirty,
                "generator_config_path": (
                    self.contract.schedule.generator_config_path
                ),
                "generator_config_sha256": (
                    self.contract.schedule.generator_config_sha256
                ),
                "bound_file_sha256": {
                    source.name: source.sha256
                    for source in self.contract.source_files
                },
            },
            "inventory": {
                "cell_count": 15,
                "episode_count": 300,
                "unique_seed_count": 300,
                "split_seed_counts": dict(A1_V3_SPLIT_SEED_COUNTS),
            },
            "permissions": _false_permissions(),
        }

    def _expected_schedule_episode(
        self, supplied: A1V3ScheduledEpisode
    ) -> A1V3ScheduledEpisode:
        if not isinstance(supplied, A1V3ScheduledEpisode):
            _fail("scheduled_episode_type_required")
        index = self._episode_id_index.get(supplied.episode_id)
        if index is None:
            _fail("writer_episode_not_scheduled", supplied.episode_id)
        expected = self.contract.schedule.episodes[index]
        if supplied != expected:
            _fail("writer_scheduled_episode_drift", supplied.episode_id)
        return expected

    def _episode_path(self, index: int) -> Path:
        return self._episode_dir / f"episode-{index:03d}.json"

    def _load_all_staged_episodes(self) -> dict[int, _StagedEpisode]:
        staged: dict[int, _StagedEpisode] = {}
        for path in sorted(self._episode_dir.iterdir()):
            match = re.fullmatch(r"episode-(\d{3})\.json", path.name)
            if match is None:
                _fail("writer_unexpected_staged_episode_entry", path.name)
            index = int(match.group(1))
            if index >= len(self.contract.schedule.episodes):
                _fail("writer_staged_episode_index_out_of_range", path.name)
            if index in staged:
                _fail("writer_duplicate_staged_episode_index", str(index))
            staged[index] = self._load_staged_episode(index, path)
        return staged

    def _load_staged_episode(self, index: int, path: Path) -> _StagedEpisode:
        if path.is_symlink():
            _fail("writer_staged_episode_symlink_forbidden", path.name)
        payload = _read_canonical_json(path, "staged_episode")
        payload = _strict_mapping(
            payload,
            {
                "schema_version",
                "record_kind",
                "schedule_index",
                "scheduled_episode",
                "online_frames",
                "offline_labels",
                "artifacts",
                "counts",
                "offline_identity_audit",
                "permissions",
            },
            "writer_staged_episode_fields_mismatch",
        )
        if payload["schema_version"] != A1_V3_STAGED_EPISODE_SCHEMA_V1:
            _fail("writer_staged_episode_schema_mismatch")
        if payload["record_kind"] != "a1_v3_complete_staged_episode":
            _fail("writer_staged_episode_kind_mismatch")
        if payload["schedule_index"] != index:
            _fail("writer_staged_episode_index_mismatch")
        expected = self.contract.schedule.episodes[index]
        if payload["scheduled_episode"] != _scheduled_episode_payload(expected):
            _fail("writer_staged_episode_schedule_mismatch")
        if payload["permissions"] != _false_permissions():
            _fail("writer_staged_episode_permission_violation")
        online_payloads = _sequence(payload["online_frames"], "online_frames")
        offline_payloads = _sequence(payload["offline_labels"], "offline_labels")
        online = tuple(A1V3OnlineFrame.from_dict(item) for item in online_payloads)
        offline = tuple(
            A1V3OfflineLabel.from_dict(
                item,
                action_change_types=self.contract.request.action_change_types,
                hard_negative_types=self.contract.request.hard_negative_types,
            )
            for item in offline_payloads
        )
        self._validate_episode_records(expected, online, offline)
        online_bytes = b"".join(canonical_json_line(item) for item in online_payloads)
        offline_bytes = b"".join(canonical_json_line(item) for item in offline_payloads)
        artifacts = _strict_mapping(
            payload["artifacts"],
            {"online_frames_sha256", "offline_labels_sha256"},
            "writer_staged_artifact_fields_mismatch",
        )
        online_sha = sha256(online_bytes).hexdigest()
        offline_sha = sha256(offline_bytes).hexdigest()
        if artifacts != {
            "online_frames_sha256": online_sha,
            "offline_labels_sha256": offline_sha,
        }:
            _fail("writer_staged_artifact_hash_mismatch")
        expected_counts = _episode_counts(offline)
        if payload["counts"] != expected_counts:
            _fail("writer_staged_episode_count_mismatch")
        if payload["offline_identity_audit"] != _identity_audit_payload(offline):
            _fail("writer_staged_identity_audit_mismatch")
        return _StagedEpisode(
            schedule_index=index,
            scheduled=expected,
            online_frames=online,
            offline_labels=offline,
            online_frames_sha256=online_sha,
            offline_labels_sha256=offline_sha,
        )

    def _validate_episode_records(
        self,
        scheduled: A1V3ScheduledEpisode,
        online: tuple[A1V3OnlineFrame, ...],
        offline: tuple[A1V3OfflineLabel, ...],
    ) -> None:
        if len(online) != len(offline):
            _fail("writer_online_offline_frame_count_mismatch")
        if not online:
            _fail("writer_empty_episode_forbidden")
        expected_indices = tuple(range(len(online)))
        if tuple(item.source.frame_index for item in online) != expected_indices:
            _fail("writer_episode_frame_index_not_contiguous")
        if tuple(item.frame_index for item in offline) != expected_indices:
            _fail("writer_offline_frame_index_not_contiguous")
        previous_measurement: float | None = None
        previous_arrival: float | None = None
        for frame, label in zip(online, offline, strict=True):
            source = frame.source
            if (
                source.episode_key != scheduled.episode_key
                or source.split != scheduled.split
                or source.cell_id != scheduled.cell_id
                or source.scenario_family != scheduled.scenario_family
                or source.configured_target_count
                != scheduled.configured_target_count
                or source.configured_resource_count
                != scheduled.configured_resource_count
            ):
                _fail("writer_online_frame_schedule_mismatch")
            if source.arrival_timestamp_s <= source.measurement_timestamp_s:
                _fail("adapter_dual_timestamp_not_distinct")
            if previous_measurement is not None and (
                source.measurement_timestamp_s < previous_measurement
                or source.arrival_timestamp_s < previous_arrival
            ):
                _fail("writer_episode_timestamp_not_monotonic")
            previous_measurement = source.measurement_timestamp_s
            previous_arrival = source.arrival_timestamp_s
            if (
                label.frame_key != frame.frame_key
                or label.split != source.split
                or label.cell_id != source.cell_id
                or label.online_payload_sha256 != frame.content_sha256
            ):
                _fail("writer_online_offline_binding_mismatch")
            if (
                label.hard_negative
                and scheduled.scenario_family == "near_tie_hard_negative"
                and label.hard_negative_type != "near_tie_but_teacher_keeps_r0"
            ):
                _fail("near_tie_cell_hard_negative_type_mismatch")
            if (
                label.hard_negative
                and label.hard_negative_type == "near_tie_but_teacher_keeps_r0"
                and (
                    frame.near_tie_qualifying_target_count < 1
                    or frame.near_tie_reason_code != A1_V3_NEAR_TIE_REASON_MET
                )
            ):
                _fail("near_tie_hard_negative_boundary_not_met")
        derived = derive_a1_v3_frame_classifications(
            scheduled,
            online,
            request=self.contract.request,
            policy=self.contract.sidecar_classification_policy,
        )
        for expected, label in zip(derived, offline, strict=True):
            actual = (
                label.frame_index,
                label.frame_class,
                label.hard_negative,
                label.action_change_type,
                label.hard_negative_type,
            )
            if actual != expected.signature:
                _fail(
                    "writer_offline_label_classification_mismatch",
                    str(label.frame_index),
                )
        counts = _episode_counts(offline)
        if (
            counts["frame_count"] < scheduled.minimum_observable_frames
            or counts["positive_frame_count"] < scheduled.minimum_positive_frames
            or counts["negative_frame_count"] < scheduled.minimum_negative_frames
            or counts["hard_negative_frame_count"]
            < scheduled.minimum_hard_negative_frames
        ):
            _fail("writer_episode_minimum_not_met", scheduled.episode_id)

    def _stage_payload(
        self,
        index: int,
        scheduled: A1V3ScheduledEpisode,
        online: tuple[A1V3OnlineFrame, ...],
        offline: tuple[A1V3OfflineLabel, ...],
    ) -> dict[str, Any]:
        online_payloads = [item.to_dict() for item in online]
        offline_payloads = [item.to_dict() for item in offline]
        online_bytes = b"".join(canonical_json_line(item) for item in online_payloads)
        offline_bytes = b"".join(canonical_json_line(item) for item in offline_payloads)
        return {
            "schema_version": A1_V3_STAGED_EPISODE_SCHEMA_V1,
            "record_kind": "a1_v3_complete_staged_episode",
            "schedule_index": index,
            "scheduled_episode": _scheduled_episode_payload(scheduled),
            "online_frames": online_payloads,
            "offline_labels": offline_payloads,
            "artifacts": {
                "online_frames_sha256": sha256(online_bytes).hexdigest(),
                "offline_labels_sha256": sha256(offline_bytes).hexdigest(),
            },
            "counts": _episode_counts(offline),
            "offline_identity_audit": _identity_audit_payload(offline),
            "permissions": _false_permissions(),
        }

    def _stage_summary(self, staged: _StagedEpisode) -> A1V3StagedEpisodeSummary:
        counts = _episode_counts(staged.offline_labels)
        identity = _identity_audit_payload(staged.offline_labels)
        return A1V3StagedEpisodeSummary(
            episode_id=staged.scheduled.episode_id,
            seed=staged.scheduled.seed,
            split=staged.scheduled.split,
            frame_count=counts["frame_count"],
            positive_frame_count=counts["positive_frame_count"],
            negative_frame_count=counts["negative_frame_count"],
            hard_negative_frame_count=counts["hard_negative_frame_count"],
            online_frames_sha256=staged.online_frames_sha256,
            offline_labels_sha256=staged.offline_labels_sha256,
            offline_identity_audit_availability=identity["availability"],
        )

    def _manifest_payload(
        self,
        pairs: Sequence[tuple[A1V3OnlineFrame, A1V3OfflineLabel]],
        *,
        online_frames_sha256: str,
        offline_labels_sha256: str,
    ) -> dict[str, Any]:
        frames = tuple(item[0] for item in pairs)
        labels = tuple(item[1] for item in pairs)
        episode_keys = {frame.source.episode_key for frame in frames}
        seeds = {frame.source.seed for frame in frames}
        cells = {frame.source.cell_id for frame in frames}
        counts = {
            "cell_count": len(cells),
            "episode_count": len(episode_keys),
            "unique_seed_count": len(seeds),
            "frame_count": len(frames),
            "positive_frame_count": sum(
                item.frame_class == "positive" for item in labels
            ),
            "negative_frame_count": sum(
                item.frame_class == "negative" for item in labels
            ),
            "hard_negative_frame_count": sum(item.hard_negative for item in labels),
            "online_truth_use_count": 0,
            "learning_created_global_track_id_count": 0,
            "learning_rewritten_global_track_id_count": 0,
            "duplicate_episode_count": 0,
            "duplicate_frame_count": 0,
        }
        request = self.contract.request
        if (
            counts["cell_count"] != 15
            or counts["episode_count"] != 300
            or counts["unique_seed_count"] != 300
            or counts["frame_count"] < request.minimum_total_observable_frame_count
            or counts["positive_frame_count"] < request.minimum_positive_frame_count
            or counts["negative_frame_count"] < request.minimum_negative_frame_count
            or counts["hard_negative_frame_count"]
            < request.minimum_hard_negative_frame_count
        ):
            _fail("writer_final_dataset_count_gate_failed")
        cell_counts: list[dict[str, Any]] = []
        for cell in request.cells:
            cell_frames = [
                frame for frame in frames if frame.source.cell_id == cell.cell_id
            ]
            cell_labels = [label for label in labels if label.cell_id == cell.cell_id]
            cell_counts.append(
                {
                    "cell_id": cell.cell_id,
                    "episode_count": len(
                        {frame.source.episode_key for frame in cell_frames}
                    ),
                    "frame_count": len(cell_frames),
                    "positive_frame_count": sum(
                        item.frame_class == "positive" for item in cell_labels
                    ),
                    "negative_frame_count": sum(
                        item.frame_class == "negative" for item in cell_labels
                    ),
                    "hard_negative_frame_count": sum(
                        item.hard_negative for item in cell_labels
                    ),
                }
            )
        return {
            "schema_version": A1_V3_DATASET_MANIFEST_SCHEMA_V1,
            "dataset_id": self.dataset_id,
            "status": "generated_untrained_not_admitted",
            "contract_bindings": {
                "request_id": request.request_id,
                "request_file_sha256": request.file_sha256,
                "contract_id": self.contract.descriptor.contract_id,
                "contract_file_sha256": self.contract.descriptor.file_sha256,
                "registry_id": self.contract.registry.registry_id,
                "registry_file_sha256": self.contract.registry.file_sha256,
                "schedule_id": self.contract.schedule.schedule_id,
                "schedule_file_sha256": self.contract.schedule.file_sha256,
                "online_frame_schema_version": A1_V3_ONLINE_FRAME_SCHEMA_V1,
                "offline_label_schema_version": A1_V3_OFFLINE_LABEL_SCHEMA_V1,
                "training_feature_schema_version": A1_V3_TRAINING_FEATURE_SCHEMA_V1,
                "training_target_schema_version": A1_V3_TRAINING_TARGET_SCHEMA_V1,
                "split_policy_version": A1_V3_SPLIT_POLICY_V1,
            },
            "source": {
                "git_commit": self.contract.schedule.source_git_commit,
                "repository_dirty": self.contract.schedule.repository_dirty,
                "generator_config_path": (
                    self.contract.schedule.generator_config_path
                ),
                "generator_config_sha256": (
                    self.contract.schedule.generator_config_sha256
                ),
            },
            "artifacts": {
                "online_frames_path": A1_V3_ONLINE_FRAMES_FILENAME,
                "online_frames_sha256": online_frames_sha256,
                "offline_labels_path": A1_V3_OFFLINE_LABELS_FILENAME,
                "offline_labels_sha256": offline_labels_sha256,
            },
            "counts": counts,
            "offline_identity_audit": _identity_audit_payload(labels),
            "split": {
                "policy_version": A1_V3_SPLIT_POLICY_V1,
                "unit": "whole_seed_one_episode_atomic",
                "ratios_percent": dict(A1_V3_SPLIT_PERCENT),
                "seed_counts": dict(A1_V3_SPLIT_SEED_COUNTS),
                "seed_values": {
                    split: list(self.contract.registry.split_seed_values[split])
                    for split in A1_V3_SPLITS
                },
                "cross_split_seed_overlap_allowed": False,
            },
            "cell_counts": cell_counts,
            "state": {
                "data_generated": True,
                "model_trained": False,
                "bundle_written": False,
                "v2_bundle_or_threshold_changed": False,
                "formal_holdout_read": False,
            },
            "permissions": _false_permissions(),
        }


def _scheduled_episode_payload(episode: A1V3ScheduledEpisode) -> dict[str, Any]:
    return {
        "episode_id": episode.episode_id,
        "cell_id": episode.cell_id,
        "scenario_family": episode.scenario_family,
        "seed": episode.seed,
        "split": episode.split,
        "configured_target_count": episode.configured_target_count,
        "configured_resource_count": episode.configured_resource_count,
        "minimum_observable_frames": episode.minimum_observable_frames,
        "minimum_positive_frames": episode.minimum_positive_frames,
        "minimum_negative_frames": episode.minimum_negative_frames,
        "minimum_hard_negative_frames": episode.minimum_hard_negative_frames,
    }


def _schedule_inventory_sha256(
    episodes: Sequence[A1V3ScheduledEpisode],
) -> str:
    return canonical_json_sha256(
        [_scheduled_episode_payload(episode) for episode in episodes]
    )


def _episode_counts(labels: Sequence[A1V3OfflineLabel]) -> dict[str, int]:
    return {
        "frame_count": len(labels),
        "positive_frame_count": sum(item.frame_class == "positive" for item in labels),
        "negative_frame_count": sum(item.frame_class == "negative" for item in labels),
        "hard_negative_frame_count": sum(item.hard_negative for item in labels),
    }


def _identity_audit_payload(
    labels: Sequence[A1V3OfflineLabel],
) -> dict[str, Any]:
    complete = 0
    partial = 0
    empty = 0
    for label in labels:
        present = (
            bool(label.truth_target_labels),
            bool(label.actor_labels),
            bool(label.object_labels),
            bool(label.center_global_track_labels),
        )
        if all(present):
            complete += 1
        elif any(present):
            partial += 1
        else:
            empty += 1
    availability = (
        "complete"
        if complete == len(labels)
        else "unavailable" if complete == 0 and partial == 0 else "partial"
    )
    return {
        "availability": availability,
        "complete_identity_audit_claimed": availability == "complete",
        "complete_identity_label_frame_count": complete,
        "partial_identity_label_frame_count": partial,
        "empty_identity_label_frame_count": empty,
    }


def _false_permissions() -> dict[str, bool]:
    return {name: False for name in A1_V3_PERMISSION_FIELDS}


def _dataset_id(value: Any) -> str:
    result = _nonempty_string(value, "dataset_id")
    if _DATASET_ID.fullmatch(result) is None:
        _fail("writer_dataset_id_invalid")
    return result


def _strict_mapping(
    value: Any, expected_keys: set[str], code: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", code)
    actual = set(value)
    if actual != expected_keys:
        _fail(
            code,
            f"missing={sorted(expected_keys - actual)!r}, "
            f"extra={sorted(actual - expected_keys)!r}",
        )
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        _fail("sequence_required", name)
    return value


def _edge_pair(value: Any, name: str) -> tuple[int, int]:
    raw = _sequence(value, name)
    if len(raw) != 2:
        _fail("edge_shape_invalid", name)
    return (
        _nonnegative_int(raw[0], f"{name}[0]"),
        _nonnegative_int(raw[1], f"{name}[1]"),
    )


def _edge_pairs(value: Any, name: str) -> tuple[tuple[int, int], ...]:
    return tuple(
        _edge_pair(item, f"{name}[{index}]")
        for index, item in enumerate(_sequence(value, name))
    )


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    return tuple(
        _nonempty_string(item, f"{name}[{index}]")
        for index, item in enumerate(_sequence(value, name))
    )


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail("nonempty_trimmed_string_required", name)
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("nonnegative_integer_required", name)
    return value


def _positive_int(value: Any, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result == 0:
        _fail("positive_integer_required", name)
    return result


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("finite_number_required", name)
    result = float(value)
    if not isfinite(result):
        _fail("finite_number_required", name)
    return result


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        _fail("boolean_required", name)
    return value


def _read_canonical_json(path: Path, name: str) -> Mapping[str, Any]:
    try:
        content = path.read_bytes()
    except OSError as exc:
        _fail("writer_staging_read_failed", f"{name}: {exc}")
    try:
        payload = json.loads(content.decode("ascii"), object_pairs_hook=_unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("writer_staging_json_invalid", f"{name}: {exc}")
    if not isinstance(payload, Mapping):
        _fail("writer_staging_json_object_required", name)
    if canonical_json_line(payload) != content:
        _fail("writer_staging_canonical_bytes_mismatch", name)
    return payload


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("writer_staging_duplicate_json_key", key)
        result[key] = value
    return result


def _atomic_write_new(path: Path, content: bytes) -> None:
    if path.exists() or path.is_symlink():
        _fail("writer_output_exists", str(path))
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.exists() or temporary.is_symlink():
        _fail("writer_temporary_output_exists", str(temporary))
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        _fail("writer_atomic_write_failed", f"{path}: {exc}")


def _fail(code: str, message: str = "") -> None:
    raise A1V3DataContractError(code, message)
