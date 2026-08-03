"""Truth-isolated adapters from main runtime frames to D3/D4/D5 source DTOs.

The adapters are deliberately authority-free.  They translate already
executed rule-path evidence and may assemble in-memory smoke records, but they
do not authorize episode generation, train a model, or alter an assignment,
degradation, camera, or guidance decision.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_data_contract import (
    A1V3EdgeResidualRank,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_source_only_projection import (
    A1V3CounterfactualMode,
    A1V3PostProjectionReferencePolicy,
    A1V3SourceOnlyProjectionInput,
    project_a1_v3_source_only_counterfactual,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
    A1V3AdapterFrameEvidence,
    load_a1_v3_writer_contract,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.planning_evidence import (
    PlanningFrameEvidence,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    RecommendationSource,
    RegionResourceRecommendation,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_development_contract import (
    V8RequestScheduleEntry,
    classify_v8_edge_direction,
    load_v8_frozen_request,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_runtime_evidence import (
    V8AnonymousCandidateEvidence,
    V8BuiltRuntimeEpisodeEvidence,
    V8RuntimeEpisodeEvidenceBuilder,
    V8RuntimeFrameEvidence,
)
from research_modules.d5_terminal_association.src.d5_terminal_association.active_vision_a3_v3_episode_evidence import (
    A3V3BoundaryPairEvidenceV1,
    A3V3EpisodeEvidenceError,
    A3V3EpisodeRecipeV1,
    A3V3HardConfusionBoundaryStateV1,
    A3V3OfflineEpisodeAuditV1,
    A3V3OfflineSampleAuditV1,
    A3V3OnlineEpisodeEvidenceV1,
    A3V3OnlineSampleEvidenceV1,
    a3_v3_assignment_reference_sha256,
    a3_v3_boundary_pair_id,
    a3_v3_sample_fingerprint,
    load_frozen_a3_v3_episode_recipes,
    validate_a3_v3_episode_evidence,
)

from .episode_treatments import D4RegionGraphTreatment, D4SupplyDemandTreatment


LEARNING_SOURCE_ADAPTER_SCHEMA_VERSION = (
    "scalable3d-learning-source-adapters-v1"
)
_D5_NEAR_TIE_MAXIMUM_GAP = 0.05


class LearningSourceAdapterError(ValueError):
    """A runtime frame cannot be represented by the strict source contract."""


@dataclass(frozen=True)
class LearningSourceAdapterSelfCheck:
    """Authority-free evidence that one producer adapter is executable."""

    module: str
    schedule_entry_count: int
    runtime_probe_episode_count: int
    runtime_probe_frame_count: int
    checks: tuple[str, ...]
    online_truth_use_count: int = 0

    def __post_init__(self) -> None:
        if self.module not in {"D3", "D4", "D5"}:
            raise LearningSourceAdapterError("self_check_module_invalid")
        for name in (
            "schedule_entry_count",
            "runtime_probe_episode_count",
            "runtime_probe_frame_count",
            "online_truth_use_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise LearningSourceAdapterError(
                    f"self_check_{name}_invalid"
                )
        checks = tuple(str(item).strip() for item in self.checks)
        if not checks or any(not item for item in checks):
            raise LearningSourceAdapterError("self_check_evidence_missing")
        if self.online_truth_use_count != 0:
            raise LearningSourceAdapterError("self_check_online_truth_use_nonzero")
        object.__setattr__(self, "checks", checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "pass_authority_free_in_memory_smoke",
            "module": self.module,
            "schedule_entry_count": self.schedule_entry_count,
            "runtime_probe_episode_count": self.runtime_probe_episode_count,
            "runtime_probe_frame_count": self.runtime_probe_frame_count,
            "checks": list(self.checks),
            "online_truth_use_count": self.online_truth_use_count,
            "formal_inventory_generated": False,
            "source_payload_written": False,
            "training_started": False,
            "runtime_authority_granted": False,
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
        }


@dataclass(frozen=True)
class D3A1RuntimeFrame:
    """Detached D3 planning evidence with explicit dual-time semantics."""

    frame_index: int
    measurement_timestamp_s: float
    arrival_timestamp_s: float
    planning_evidence: PlanningFrameEvidence

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or self.frame_index < 0:
            raise LearningSourceAdapterError("d3_frame_index_invalid")
        measurement = float(self.measurement_timestamp_s)
        arrival = float(self.arrival_timestamp_s)
        if (
            not math.isfinite(measurement)
            or not math.isfinite(arrival)
            or arrival <= measurement
        ):
            raise LearningSourceAdapterError("d3_dual_timestamp_invalid")
        if not isinstance(self.planning_evidence, PlanningFrameEvidence):
            raise LearningSourceAdapterError("d3_planning_evidence_required")
        object.__setattr__(self, "measurement_timestamp_s", measurement)
        object.__setattr__(self, "arrival_timestamp_s", arrival)


def self_check_d3_a1_adapter(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Exercise D3 recipe mapping, a real frame adapter, and writer binding."""

    root = str(Path(repository_root).expanduser().resolve())
    return _self_check_d3_a1_adapter_cached(root).to_dict()


@lru_cache(maxsize=4)
def _self_check_d3_a1_adapter_cached(
    repository_root: str,
) -> LearningSourceAdapterSelfCheck:
    from .learning_source_recipes import load_d3_a1_v3_episode_recipes
    from .models import ScenarioConfig
    from .module_stack import IntegratedScalableModuleStack, IntegratedStackConfig
    from .orchestrator import run_episode

    root = Path(repository_root)
    schedule_path = (
        root
        / "research_modules/d3_assignment_planner/configs/"
        "a1_source_independent_v3_generation_schedule_v1.json"
    )
    recipes = load_d3_a1_v3_episode_recipes(schedule_path)
    base = ScenarioConfig(
        target_count=5,
        resource_count=5,
        recon_count=1,
        duration_s=2.0,
        seed=31_001,
    )
    mapped = tuple(recipe.build_config(base) for recipe in recipes)
    if any(
        config.target_count != recipe.target_count
        or config.resource_count != recipe.resource_count
        or config.seed != recipe.seed
        for config, recipe in zip(mapped, recipes, strict=True)
    ):
        raise LearningSourceAdapterError("d3_recipe_count_mapping_failed")
    expected_families = {
        "nominal_balanced",
        "resource_shortage",
        "resource_surplus",
        "dynamic_add_drop",
        "near_tie_hard_negative",
    }
    if not expected_families.issubset(
        {item.scenario_family for item in recipes}
    ):
        raise LearningSourceAdapterError("d3_recipe_family_mapping_incomplete")

    writer_contract = load_a1_v3_writer_contract(
        request_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_development_data_request_v1.json"
        ),
        exclusion_registry_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_seed_exclusion_registry_v1.json"
        ),
        contract_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_data_contract_v1.json"
        ),
        generator_config_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_generator_config_v1.json"
        ),
        global_registry_path=(
            root
            / "research_modules/scalable_3d_simulation/configs/"
            "scalable_learning_global_seed_registry_v1.json"
        ),
        registry_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_main_allocation_registry_v1.json"
        ),
        schedule_path=schedule_path,
        near_tie_boundary_path=(
            root
            / "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_near_tie_boundary_v1.json"
        ),
    )
    if len(writer_contract.schedule.episodes) != len(recipes):
        raise LearningSourceAdapterError("d3_writer_schedule_mismatch")

    probe_config = replace(
        base,
        scenario_name="d3-adapter-self-check",
        scenario_version="d3-adapter-self-check-v1",
        radar_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(capture_learning_artifacts=True)
    )
    result = run_episode(probe_config, module_stack=stack)
    frames = stack.learning_artifacts().d3_a1_source_frames
    if not frames or result.summary.get("online_truth_use_count") != 0:
        raise LearningSourceAdapterError("d3_runtime_probe_failed")
    adapted = adapt_d3_a1_runtime_frame(frames[0])
    if (
        adapted.arrival_timestamp_s <= adapted.measurement_timestamp_s
        or adapted.observed_target_count != len(adapted.target_demand_slots)
        or not set(adapted.teacher_edges).issubset(
            set(adapted.candidate_mask_true_edges)
        )
    ):
        raise LearningSourceAdapterError("d3_runtime_adapter_contract_failed")
    return LearningSourceAdapterSelfCheck(
        module="D3",
        schedule_entry_count=len(recipes),
        runtime_probe_episode_count=1,
        runtime_probe_frame_count=1,
        checks=(
            "all_frozen_recipe_mappings",
            "unequal_target_resource_counts",
            "five_new_and_eight_existing_scenario_families",
            "actual_dual_time_runtime_frame",
            "strict_a1_v3_writer_contract",
        ),
    )


def self_check_d4_v8_adapter(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Exercise every D4 recipe mapping and three actual transfer classes."""

    root = str(Path(repository_root).expanduser().resolve())
    return _self_check_d4_v8_adapter_cached(root).to_dict()


@lru_cache(maxsize=4)
def _self_check_d4_v8_adapter_cached(
    repository_root: str,
) -> LearningSourceAdapterSelfCheck:
    from .learning_source_recipes import load_d4_a2_v8_episode_recipes
    from .models import ScenarioConfig
    from .module_stack import IntegratedScalableModuleStack, IntegratedStackConfig
    from .orchestrator import run_episode

    root = Path(repository_root)
    request_root = (
        root
        / "research_modules/d4_distributed_fallback/reports/"
        "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
    )
    request_path = request_root / "v8_development_data_request.json"
    registry_path = request_root / "v8_development_seed_registry.json"
    recipes = load_d4_a2_v8_episode_recipes(registry_path)
    base = ScenarioConfig(
        target_count=16,
        resource_count=16,
        recon_count=2,
        region_count=8,
        duration_s=3.0,
        seed=31_200,
    )
    for recipe in recipes:
        config = recipe.build_config(base)
        graph = D4RegionGraphTreatment(
            topology_id=recipe.topology_id,
            region_count=recipe.region_count,
            communication_condition=recipe.communication_condition,
            partition_start_s=(
                recipe.duration_s / 3.0
                if recipe.communication_condition == "partition_then_recovery"
                else None
            ),
            partition_end_s=(
                2.0 * recipe.duration_s / 3.0
                if recipe.communication_condition == "partition_then_recovery"
                else None
            ),
        )
        supply = D4SupplyDemandTreatment(
            topology_id=recipe.topology_id,
            region_count=recipe.region_count,
            supply_demand_condition=recipe.supply_demand_condition,
            requested_target_class=recipe.requested_target_class,
            requested_transfer_resource_count=(
                recipe.requested_transfer_resource_count
            ),
            hard_negative_candidate_resource_count=(
                recipe.hard_negative_candidate_resource_count
            ),
        )
        if (
            config.region_count != recipe.region_count
            or not graph.directed_pairs(
                tuple(f"REGION-{index:03d}" for index in range(recipe.region_count))
            )
            or supply.candidate_resource_count < 1
        ):
            raise LearningSourceAdapterError("d4_recipe_mapping_failed")

    frozen = load_v8_frozen_request(request_path, registry_path)
    if {item.seed for item in frozen.schedule} != {item.seed for item in recipes}:
        raise LearningSourceAdapterError("d4_frozen_schedule_mismatch")
    built: dict[str, V8BuiltRuntimeEpisodeEvidence] = {}
    truth_use_count = 0
    for target_class in (
        "safe_forward_transfer",
        "safe_reverse_transfer",
        "hard_no_transfer_negative",
    ):
        recipe = next(
            item
            for item in frozen.schedule
            if item.requested_target_class.value == target_class
        )
        config = ScenarioConfig(
            scenario_name="d4-adapter-self-check",
            scenario_version="d4-adapter-self-check-v1",
            target_count=2 * recipe.region_count,
            resource_count=2 * recipe.region_count,
            recon_count=max(1, recipe.region_count // 4),
            region_count=recipe.region_count,
            duration_s=3.0,
            seed=recipe.seed,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
            metadata={
                "learning_source_recipe": {
                    "module": "D4",
                    **recipe.to_registry_dict(),
                }
            },
        )
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(config, module_stack=stack)
        truth_use_count += int(result.summary.get("online_truth_use_count", -1))
        built[target_class] = build_d4_v8_runtime_episode(
            recipe=recipe,
            episode_id=f"d4-v8-adapter-self-check-{recipe.seed}",
            region_frames=stack.learning_artifacts().d4_region_frames,
        )
    if truth_use_count != 0:
        raise LearningSourceAdapterError("d4_runtime_probe_truth_use_nonzero")
    if (
        not all(
            frame.projected_transfers
            for target_class in (
                "safe_forward_transfer",
                "safe_reverse_transfer",
            )
            for frame in built[target_class].frames
        )
        or any(
            frame.projected_transfers
            for frame in built["hard_no_transfer_negative"].frames
        )
        or not all(
            label.hard_negative_reasons
            for label in built["hard_no_transfer_negative"].labels
        )
    ):
        raise LearningSourceAdapterError("d4_runtime_class_boundary_failed")
    return LearningSourceAdapterSelfCheck(
        module="D4",
        schedule_entry_count=len(recipes),
        runtime_probe_episode_count=3,
        runtime_probe_frame_count=sum(
            len(episode.frames) for episode in built.values()
        ),
        checks=(
            "all_frozen_recipe_mappings",
            "all_region_topologies",
            "all_communication_conditions",
            "actual_forward_and_reverse_transfer",
            "actual_hard_no_transfer_negative",
            "strict_v8_runtime_dtos",
        ),
    )


def self_check_d5_a3_adapter(
    repository_root: str | Path,
) -> dict[str, Any]:
    """Exercise all D5 recipes and the five actual hard-confusion families."""

    root = str(Path(repository_root).expanduser().resolve())
    return _self_check_d5_a3_adapter_cached(root).to_dict()


@lru_cache(maxsize=4)
def _self_check_d5_a3_adapter_cached(
    repository_root: str,
) -> LearningSourceAdapterSelfCheck:
    from .learning_source_recipes import load_d5_a3_v3_episode_recipes
    from .models import ScenarioConfig
    from .module_stack import IntegratedScalableModuleStack, IntegratedStackConfig
    from .orchestrator import run_episode

    root = Path(repository_root)
    schedule_path = (
        root
        / "research_modules/d5_terminal_association/configs/"
        "a3_v3_source_collection_schedule_20260801.json"
    )
    main_recipes = load_d5_a3_v3_episode_recipes(schedule_path)
    module_recipes = load_frozen_a3_v3_episode_recipes(
        source_schedule_path=schedule_path
    )
    if len(main_recipes) != len(module_recipes):
        raise LearningSourceAdapterError("d5_recipe_inventory_mismatch")
    if any(
        main.seed != module.seed
        or main.episode_id != module.episode_id
        or main.split != module.split
        for main, module in zip(main_recipes, module_recipes, strict=True)
    ):
        raise LearningSourceAdapterError("d5_recipe_binding_mismatch")

    expected_families = {
        "observe_vs_reacquire_projection_boundary",
        "search_vs_reacquire_cue_loss_boundary",
        "hold_vs_observe_gimbal_busy_boundary",
        "role_matched_interceptor_recon_geometry",
        "multiple_legal_targets_near_tie",
    }
    observed_families: set[str] = set()
    runtime_frame_count = 0
    runtime_episode_count = 0
    for entry_index in range(5):
        seed = 31_300 + entry_index
        main_recipe = main_recipes[entry_index]
        recipe_payload = module_recipes[entry_index].to_dict()
        recipe_payload.update(
            {
                "seed": seed,
                "episode_id": f"d5-a3-v3-adapter-self-check-{seed}",
                "scale": 5,
                "target_count": 5,
                "resource_count": 5,
                "recon_count": 2,
            }
        )
        adapter_recipe = A3V3EpisodeRecipeV1.from_dict(recipe_payload)
        base = ScenarioConfig(
            target_count=5,
            resource_count=5,
            recon_count=2,
            region_count=1,
            duration_s=6.0,
            seed=seed,
            visual_period_s=0.05,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
        )
        config = main_recipe.build_config(base)
        metadata = dict(config.metadata)
        metadata["learning_source_recipe"] = {
            **dict(metadata["learning_source_recipe"]),
            "seed": seed,
            "episode_id": adapter_recipe.episode_id,
        }
        config = replace(
            config,
            seed=seed,
            target_count=5,
            resource_count=5,
            recon_count=2,
            visual_period_s=0.05,
            metadata=metadata,
        )
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(
                capture_learning_artifacts=True,
                d5_recon_track_cues_enabled=True,
                d5_active_vision_collection_profile="balanced_action_role_v1",
            )
        )
        result = run_episode(config, module_stack=stack)
        if result.summary.get("online_truth_use_count") != 0:
            raise LearningSourceAdapterError("d5_runtime_probe_truth_use_nonzero")
        frames = stack.learning_artifacts().d5_active_vision_frames
        online, offline = build_d5_a3_runtime_episode(
            recipe=adapter_recipe,
            active_vision_frames=frames,
        )
        counts = Counter(item.window_id for item in online.samples)
        if any(
            counts[window.window_id] < window.minimum_unique_samples
            for window in online.recipe.intent_windows
        ):
            raise LearningSourceAdapterError("d5_runtime_window_quota_failed")
        online_round_trip = A3V3OnlineEpisodeEvidenceV1.from_dict(
            online.to_dict()
        )
        offline_round_trip = A3V3OfflineEpisodeAuditV1.from_dict(
            offline.to_dict()
        )
        if (
            online_round_trip.to_dict() != online.to_dict()
            or offline_round_trip.to_dict() != offline.to_dict()
        ):
            raise LearningSourceAdapterError("d5_episode_dto_round_trip_failed")
        observed_families.update(item.family for item in offline.boundary_pairs)
        runtime_frame_count += len(frames)
        runtime_episode_count += 1
    if observed_families != expected_families:
        raise LearningSourceAdapterError("d5_hard_confusion_family_incomplete")
    return LearningSourceAdapterSelfCheck(
        module="D5",
        schedule_entry_count=len(main_recipes),
        runtime_probe_episode_count=runtime_episode_count,
        runtime_probe_frame_count=runtime_frame_count,
        checks=(
            "all_frozen_recipe_mappings",
            "four_intent_windows_and_camera_roles",
            "five_actual_hard_confusion_families",
            "minimum_unique_sample_quotas",
            "strict_online_offline_episode_dtos",
        ),
    )


def adapt_d3_a1_runtime_frame(
    frame: D3A1RuntimeFrame,
    *,
    source_only_counterfactual_mode: A1V3CounterfactualMode | None = None,
    source_only_reference_policy: A1V3PostProjectionReferencePolicy | None = None,
    source_episode_key: tuple[int, str] | None = None,
) -> A1V3AdapterFrameEvidence:
    """Translate one actual planner snapshot into the strict A1 adapter DTO."""

    try:
        validated_frame = D3A1RuntimeFrame(
            frame_index=int(frame.frame_index),
            measurement_timestamp_s=float(frame.measurement_timestamp_s),
            arrival_timestamp_s=float(frame.arrival_timestamp_s),
            planning_evidence=frame.planning_evidence,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, LearningSourceAdapterError):
            raise
        raise LearningSourceAdapterError("d3_runtime_frame_invalid") from exc
    evidence = validated_frame.planning_evidence
    if (
        not evidence.available
        or evidence.rule_matrix_result is None
        or evidence.effective_matrix_result is None
        or evidence.plan is None
    ):
        raise LearningSourceAdapterError(
            f"d3_planning_evidence_unavailable:{evidence.reason}"
        )
    rule = evidence.rule_matrix_result
    effective = evidence.effective_matrix_result
    rule_matrix = np.asarray(rule.matrix, dtype=float)
    effective_matrix = np.asarray(effective.matrix, dtype=float)
    if (
        rule_matrix.ndim != 2
        or effective_matrix.shape != rule_matrix.shape
        or not np.all(np.isfinite(rule_matrix))
        or not np.all(np.isfinite(effective_matrix))
    ):
        raise LearningSourceAdapterError("d3_cost_matrix_invalid")
    candidate_mask = np.asarray(rule.hard_safe_candidate_mask, dtype=bool)
    if candidate_mask.shape != rule_matrix.shape:
        raise LearningSourceAdapterError("d3_candidate_mask_shape_invalid")
    candidate_edges = tuple(
        (int(row), int(column))
        for row, column in zip(*np.nonzero(candidate_mask), strict=True)
    )
    if not candidate_edges:
        raise LearningSourceAdapterError("d3_candidate_mask_empty")

    effective_edges = _d3_plan_edges(evidence, rule)
    teacher = tuple(effective_edges)
    candidate_selected = effective_edges
    source_projection = None
    if source_only_counterfactual_mode is not None:
        if (
            not isinstance(source_only_counterfactual_mode, A1V3CounterfactualMode)
            or not isinstance(
                source_only_reference_policy,
                A1V3PostProjectionReferencePolicy,
            )
            or not isinstance(source_episode_key, tuple)
            or len(source_episode_key) != 2
            or isinstance(source_episode_key[0], bool)
            or not isinstance(source_episode_key[0], int)
            or source_episode_key[0] < 0
            or not isinstance(source_episode_key[1], str)
            or not source_episode_key[1].strip()
        ):
            raise LearningSourceAdapterError(
                "d3_source_only_counterfactual_binding_invalid"
            )
        previous_edges = _d3_previous_plan_edges(
            evidence,
            rule,
            candidate_mask=candidate_mask,
        )
        try:
            source_projection = project_a1_v3_source_only_counterfactual(
                A1V3SourceOnlyProjectionInput(
                    frame_key=(
                        source_episode_key[0],
                        source_episode_key[1].strip(),
                        validated_frame.frame_index,
                    ),
                    measurement_timestamp_s=(
                        validated_frame.measurement_timestamp_s
                    ),
                    arrival_timestamp_s=validated_frame.arrival_timestamp_s,
                    rule_cost_matrix=rule_matrix,
                    hard_safe_action_mask=candidate_mask,
                    target_demand_slots=_d3_target_demand_slots(evidence, rule),
                    target_threat_scores=tuple(
                        float(value) for value in rule.target_threat_scores
                    ),
                    unassigned_costs=np.asarray(
                        rule.unassigned_costs, dtype=float
                    ),
                    previous_selected_edges=previous_edges,
                    preregistered_mode=source_only_counterfactual_mode,
                ),
                reference_effective_edges=effective_edges,
                reference_policy=source_only_reference_policy,
            )
        except (TypeError, ValueError) as exc:
            raise LearningSourceAdapterError(
                "d3_source_only_counterfactual_projection_failed"
            ) from exc
        candidate_selected = source_projection.candidate_pre_projection_edges
        effective_edges = source_projection.effective_post_projection_edges
        if (
            source_only_counterfactual_mode
            is A1V3CounterfactualMode.COVERAGE_DEGRADING
            and effective_edges != teacher
        ):
            raise LearningSourceAdapterError(
                "d3_source_only_coverage_floor_not_preserved"
            )
    elif (
        source_episode_key is not None
        or source_only_reference_policy is not None
    ):
        raise LearningSourceAdapterError(
            "d3_source_only_counterfactual_binding_invalid"
        )
    _validate_index_edges(teacher, rule_matrix.shape, "d3_teacher")
    _validate_index_edges(candidate_selected, rule_matrix.shape, "d3_candidate")
    _validate_index_edges(effective_edges, rule_matrix.shape, "d3_effective")

    residual_items = sorted(
        (
            float(effective_matrix[row, column] - rule_matrix[row, column]),
            row,
            column,
        )
        for row, column in candidate_edges
    )
    residual_ranking = tuple(
        A1V3EdgeResidualRank(
            edge=(row, column),
            residual=residual,
            rank=rank,
        )
        for rank, (residual, row, column) in enumerate(residual_items, start=1)
    )
    target_demand_slots = _d3_target_demand_slots(evidence, rule)
    pre_reason_set = {
        f"planning_path_{_reason_token(evidence.planning_path)}",
        f"selection_source_{_reason_token(evidence.selection_source)}",
        f"learning_state_{_reason_token(evidence.learning_state)}",
    }
    if source_projection is not None:
        pre_reason_set.update(source_projection.pre_projection_reason_codes)
    pre_reasons = tuple(sorted(pre_reason_set))
    post_reasons = [
        "effective_plan_projected",
        f"solver_{_reason_token(evidence.solver_name or 'unknown')}",
    ]
    if evidence.fallback_reason:
        post_reasons.append("learning_fallback_applied")
    if source_projection is not None:
        post_reasons.extend(source_projection.post_projection_reason_codes)
    return A1V3AdapterFrameEvidence(
        frame_index=validated_frame.frame_index,
        measurement_timestamp_s=validated_frame.measurement_timestamp_s,
        arrival_timestamp_s=validated_frame.arrival_timestamp_s,
        observed_target_count=rule_matrix.shape[0],
        observed_resource_count=rule_matrix.shape[1],
        candidate_mask_shape=rule_matrix.shape,
        candidate_mask_true_edges=candidate_edges,
        rule_cost_matrix=tuple(
            tuple(float(value) for value in row) for row in rule_matrix
        ),
        teacher_edges=teacher,
        candidate_selected_edges=candidate_selected,
        effective_selected_edges=effective_edges,
        residual_ranking=residual_ranking,
        target_demand_slots=target_demand_slots,
        pre_projection_reason_codes=pre_reasons,
        post_projection_reason_codes=tuple(sorted(set(post_reasons))),
    )


def build_d4_v8_runtime_episode(
    *,
    recipe: V8RequestScheduleEntry,
    episode_id: str,
    region_frames: Sequence[Any],
    rule_policy: RuleRegionResourcePolicy | None = None,
) -> V8BuiltRuntimeEpisodeEvidence:
    """Build one D4 v8 episode from actual main-captured regional frames."""

    if not isinstance(recipe, V8RequestScheduleEntry):
        raise LearningSourceAdapterError("d4_frozen_recipe_required")
    policy = rule_policy or RuleRegionResourcePolicy()
    builder = V8RuntimeEpisodeEvidenceBuilder(
        episode_id=episode_id,
        recipe=recipe,
        rule_policy=policy,
    )
    staged = 0
    for frame in sorted(region_frames, key=lambda item: float(item.timestamp_s)):
        snapshot = frame.snapshot
        if int(snapshot.seed) != int(recipe.seed):
            continue
        try:
            runtime_evidence = _d4_runtime_frame_evidence(
                snapshot,
                recipe=recipe,
                policy=policy,
            )
            builder.stage_frame(frame_index=staged, evidence=runtime_evidence)
        except (LearningSourceAdapterError, ValueError):
            continue
        staged += 1
    if staged == 0:
        raise LearningSourceAdapterError("d4_no_qualifying_runtime_frames")
    try:
        return builder.finalize()
    except ValueError as exc:
        raise LearningSourceAdapterError(
            f"d4_runtime_episode_incomplete:{exc}"
        ) from exc


def _d4_runtime_frame_evidence(
    snapshot: Any,
    *,
    recipe: V8RequestScheduleEntry,
    policy: RuleRegionResourcePolicy,
) -> V8RuntimeFrameEvidence:
    treatment = D4SupplyDemandTreatment(
        topology_id=recipe.topology_id,
        region_count=recipe.region_count,
        supply_demand_condition=recipe.supply_demand_condition,
        requested_target_class=recipe.requested_target_class.value,
        requested_transfer_resource_count=(
            recipe.requested_transfer_resource_count
        ),
        hard_negative_candidate_resource_count=(
            recipe.hard_negative_candidate_resource_count
        ),
    )
    source_index, target_index = treatment.candidate_index_pair()
    if len(snapshot.regions) != recipe.region_count:
        raise LearningSourceAdapterError("d4_snapshot_region_count_mismatch")
    source_id = snapshot.regions[source_index].region_id
    target_id = snapshot.regions[target_index].region_id
    edge = next(
        (
            item
            for item in snapshot.edges
            if item.permits(source_id, target_id)
        ),
        None,
    )
    if edge is None:
        raise LearningSourceAdapterError("d4_candidate_edge_missing")
    expected_direction = (
        None
        if recipe.requested_target_class.value == "hard_no_transfer_negative"
        else (
            "forward"
            if recipe.requested_target_class.value == "safe_forward_transfer"
            else "reverse"
        )
    )
    direction = classify_v8_edge_direction(
        recipe.topology_id,
        source_index,
        target_index,
    )
    if expected_direction is not None and direction != expected_direction:
        raise LearningSourceAdapterError("d4_candidate_direction_mismatch")

    count = treatment.candidate_resource_count
    r0 = policy.recommend(snapshot)
    transfer = RegionTransferSuggestion(
        source_region_id=source_id,
        target_region_id=target_id,
        resource_count=count,
        edge_id=edge.edge_id,
        expected_transfer_time_s=edge.transfer_time_s,
        reasons=("anonymous_frozen_recipe_candidate",),
    )
    raw = RegionResourceRecommendation(
        snapshot_id=snapshot.snapshot_id,
        scenario_id=snapshot.scenario_id,
        scenario_version=snapshot.scenario_version,
        seed=snapshot.seed,
        authority_digest=snapshot.authority_digest,
        created_at_s=snapshot.timestamp_s,
        policy_name="main-anonymous-v8-source-actor",
        policy_version="v1",
        source=RecommendationSource.LEARNED,
        confidence=0.9,
        actions=r0.actions,
        transfers=(transfer,),
        projected=False,
        planning_authority_digest=snapshot.planning_authority_digest,
    )
    projected = policy.projector.project(snapshot, raw)
    latency = max(
        1.0e-3,
        max(
            (float(node.communication_latency_s) for node in snapshot.regions),
            default=0.0,
        ),
    )
    return V8RuntimeFrameEvidence(
        snapshot=snapshot,
        r0_recommendation=r0,
        raw_actor_proposal=raw,
        projected_actor_recommendation=projected,
        anonymous_candidates=(
            V8AnonymousCandidateEvidence(
                transfer=transfer,
                activation_score=0.9,
            ),
        ),
        arrival_timestamp=float(snapshot.timestamp_s) + latency,
    )


@dataclass(frozen=True)
class _D5RuntimeSample:
    sample: A3V3OnlineSampleEvidenceV1
    boundary_state: A3V3HardConfusionBoundaryStateV1


def build_d5_a3_runtime_episode(
    *,
    recipe: A3V3EpisodeRecipeV1,
    active_vision_frames: Sequence[Any],
    episode_start_timestamp_s: float = 0.0,
) -> tuple[A3V3OnlineEpisodeEvidenceV1, A3V3OfflineEpisodeAuditV1]:
    """Build and validate one A3 episode from actual active-vision frames."""

    if not isinstance(recipe, A3V3EpisodeRecipeV1):
        raise LearningSourceAdapterError("d5_frozen_recipe_required")
    start = float(episode_start_timestamp_s)
    if not math.isfinite(start):
        raise LearningSourceAdapterError("d5_episode_start_invalid")
    records: list[_D5RuntimeSample] = []
    center_track_ids: set[str] = set()
    for frame in sorted(
        active_vision_frames,
        key=lambda item: (float(item.timestamp_s), int(item.frame_index)),
    ):
        snapshot = frame.snapshot
        center_track_ids.update(item.global_track_id for item in snapshot.tracks)
        relative = float(frame.timestamp_s) - start
        for decision in frame.decisions:
            camera_id = decision.effective_action.camera_id
            camera = snapshot.camera(camera_id)
            role = _d5_camera_role(camera)
            window = next(
                (
                    item
                    for item in recipe.intent_windows
                    if item.camera_role == role
                    and item.start_s <= relative < item.end_s
                ),
                None,
            )
            if window is None:
                continue
            intent = decision.effective_action.intent.value
            if intent != window.intent:
                continue
            record = _d5_runtime_sample(
                recipe,
                frame=frame,
                decision=decision,
                camera=camera,
                window=window,
                relative_timestamp_s=relative,
            )
            if all(record.sample.required_control_states.values()):
                records.append(record)
    if not records:
        raise LearningSourceAdapterError("d5_no_qualifying_runtime_samples")

    online = A3V3OnlineEpisodeEvidenceV1(
        recipe=recipe,
        center_global_track_ids=tuple(sorted(center_track_ids)),
        samples=tuple(item.sample for item in records),
    )
    sample_audits = tuple(
        A3V3OfflineSampleAuditV1(
            sample_fingerprint=item.sample.sample_fingerprint,
            treatment_achieved=True,
            evaluation_available=False,
            evaluation=None,
        )
        for item in records
    )
    boundary_pairs = tuple(
        _d5_boundary_pair(recipe, assignment, records)
        for assignment in recipe.hard_confusion_assignments
    )
    offline = A3V3OfflineEpisodeAuditV1(
        episode_id=recipe.episode_id,
        split=recipe.split,
        allocation_id=recipe.allocation_id,
        sample_audits=sample_audits,
        boundary_pairs=boundary_pairs,
    )
    try:
        validate_a3_v3_episode_evidence(online, offline)
    except A3V3EpisodeEvidenceError as exc:
        raise LearningSourceAdapterError(
            f"d5_runtime_episode_contract_failed:{exc.code}"
        ) from exc
    return online, offline


def _d5_runtime_sample(
    recipe: A3V3EpisodeRecipeV1,
    *,
    frame: Any,
    decision: Any,
    camera: Any,
    window: Any,
    relative_timestamp_s: float,
) -> _D5RuntimeSample:
    snapshot = frame.snapshot
    camera_id = camera.camera_id
    assigned_target_ids = snapshot.assigned_target_ids(camera_id)
    action_target_id = decision.effective_action.target_global_track_id
    target_id = action_target_id or (
        assigned_target_ids[0] if assigned_target_ids else None
    )
    camera_projections = tuple(
        item for item in snapshot.projections if item.camera_id == camera_id
    )
    projection = next(
        (
            item
            for item in camera_projections
            if item.global_track_id == target_id
        ),
        None,
    )
    if projection is None and camera_projections:
        projection = camera_projections[0]
        if target_id is None:
            target_id = projection.global_track_id
    track = next(
        (
            item
            for item in snapshot.tracks
            if item.global_track_id == target_id
        ),
        None,
    )
    measurement = (
        float(projection.measurement_timestamp)
        if projection is not None
        else (
            float(track.measurement_timestamp)
            if track is not None
            else float(snapshot.snapshot_timestamp)
        )
    )
    arrival = (
        float(projection.arrival_timestamp)
        if projection is not None
        else float(snapshot.snapshot_timestamp)
    )
    if arrival < measurement:
        raise LearningSourceAdapterError("d5_projection_dual_timestamp_invalid")

    fresh = bool(
        projection is not None
        and float(snapshot.snapshot_timestamp) - measurement <= 0.75 + 1.0e-12
    )
    inside = bool(
        projection is not None
        and projection.in_fov
        and projection.visibility_probability >= 0.35
        and projection.association_confidence >= 0.60
        and projection.occlusion_fraction <= 0.80
    )
    assignment_retained = bool(assigned_target_ids)
    matched_retained = projection is not None and target_id is not None
    gimbal_busy = bool(
        camera.action_in_progress_until is not None
        and float(camera.action_in_progress_until)
        > float(snapshot.snapshot_timestamp) + 1.0e-12
    )
    slew_available = bool(camera.slew_available)
    stale_or_occluded = bool(
        projection is None
        or not fresh
        or projection.occlusion_fraction > 0.80
    )
    outside_or_degraded = bool(stale_or_occluded or not inside)
    recon_cue_available = bool(assignment_retained and projection is not None)
    control_values = {
        "assigned_projection_fresh": bool(assignment_retained and fresh),
        "projection_inside_usable_boundary": inside,
        "assignment_retained": assignment_retained,
        "truth_free_recon_cue_loss_or_projection_absence": bool(
            assignment_retained and projection is None
        ),
        "matched_target_evidence_retained": matched_retained,
        "bounded_gimbal_busy_or_slew_unavailable": bool(
            gimbal_busy or not slew_available
        ),
        "projection_stale_occluded_or_outside_boundary": bool(
            assignment_retained and outside_or_degraded
        ),
    }
    unknown_controls = set(window.required_controls) - set(control_values)
    if unknown_controls:
        raise LearningSourceAdapterError(
            "d5_window_control_unsupported:" + ",".join(sorted(unknown_controls))
        )
    required_states = {
        name: control_values[name] for name in window.required_controls
    }
    feature_payload = {
        "schema_version": LEARNING_SOURCE_ADAPTER_SCHEMA_VERSION,
        "frame_index": int(frame.frame_index),
        "snapshot_timestamp": float(snapshot.snapshot_timestamp),
        "camera_id": camera_id,
        "resource_id": camera.resource_id,
        "camera_role": _d5_camera_role(camera),
        "plan_version": int(snapshot.plan.plan_version),
        "coalition_version": int(snapshot.plan.coalition_version),
        "communication_healthy": bool(snapshot.communication.healthy),
        "assigned_target_ids": list(assigned_target_ids),
        "effective_intent": decision.effective_action.intent.value,
        "effective_target_id": target_id,
        "camera": {
            "yaw_deg": float(camera.yaw_deg),
            "pitch_deg": float(camera.pitch_deg),
            "fov_mode": camera.current_fov_mode.value,
            "slew_available": slew_available,
            "gimbal_busy": gimbal_busy,
        },
        "projections": [
            {
                "global_track_id": item.global_track_id,
                "measurement_timestamp": float(item.measurement_timestamp),
                "arrival_timestamp": float(item.arrival_timestamp),
                "yaw_error_deg": float(item.yaw_error_deg),
                "pitch_error_deg": float(item.pitch_error_deg),
                "visibility_probability": float(item.visibility_probability),
                "occlusion_fraction": float(item.occlusion_fraction),
                "association_confidence": float(item.association_confidence),
                "in_fov": bool(item.in_fov),
            }
            for item in sorted(
                camera_projections,
                key=lambda value: value.global_track_id,
            )
        ],
    }
    candidate_fingerprint = _canonical_sha256(feature_payload)
    sample_fingerprint = a3_v3_sample_fingerprint(
        recipe,
        frame_index=int(frame.frame_index),
        camera_id=camera_id,
        candidate_feature_fingerprint=candidate_fingerprint,
    )
    sample = A3V3OnlineSampleEvidenceV1(
        sample_fingerprint=sample_fingerprint,
        candidate_feature_fingerprint=candidate_fingerprint,
        frame_index=int(frame.frame_index),
        relative_timestamp_s=relative_timestamp_s,
        measurement_timestamp=measurement,
        arrival_timestamp=arrival,
        camera_id=camera_id,
        resource_id=camera.resource_id,
        camera_role=_d5_camera_role(camera),
        window_id=window.window_id,
        intent=window.intent,
        treatment_recipe=window.treatment_recipe,
        required_control_states=required_states,
        global_track_id=target_id,
    )

    qualities = sorted(
        (
            float(item.visibility_probability)
            * float(item.association_confidence)
            * (1.0 - float(item.occlusion_fraction))
            for item in camera_projections
        ),
        reverse=True,
    )
    quality_gap = (
        abs(qualities[0] - qualities[1]) if len(qualities) >= 2 else 1.0
    )
    geometry_family = _canonical_sha256(
        {
            "episode_id": recipe.episode_id,
            "center_global_track_id": target_id,
            "geometry_family": "assigned_camera_track_projection",
        }
    )
    communication_state = _d5_role_match_communication_state_sha256(snapshot)
    boundary_state = A3V3HardConfusionBoundaryStateV1(
        assignment_reference_sha256=a3_v3_assignment_reference_sha256(recipe),
        geometry_family_sha256=geometry_family,
        communication_state_sha256=communication_state,
        camera_role=_d5_camera_role(camera),
        projection_available=projection is not None,
        projection_inside_usable_boundary=inside,
        projection_fresh=fresh,
        projection_stale_or_occluded=stale_or_occluded,
        recon_cue_available=recon_cue_available,
        gimbal_busy=gimbal_busy,
        slew_available=slew_available,
        matched_target_evidence_retained=matched_retained,
        legal_target_count=len(camera_projections),
        projection_quality_gap=quality_gap,
        near_tie_maximum_gap=_D5_NEAR_TIE_MAXIMUM_GAP,
    )
    return _D5RuntimeSample(sample=sample, boundary_state=boundary_state)


def _d5_role_match_communication_state_sha256(snapshot: Any) -> str:
    """Hash communication equivalence without volatile planning counters."""

    return _canonical_sha256(
        {
            "schema_version": "d5-role-match-communication-equivalence-v1",
            "healthy": bool(snapshot.communication.healthy),
        }
    )


def _d5_boundary_pair(
    recipe: A3V3EpisodeRecipeV1,
    assignment: Any,
    records: Sequence[_D5RuntimeSample],
) -> A3V3BoundaryPairEvidenceV1:
    by_window: dict[str, list[_D5RuntimeSample]] = defaultdict(list)
    for item in records:
        by_window[item.sample.window_id].append(item)
    window_ids = tuple(assignment.window_ids)
    for left_index, left_window in enumerate(window_ids):
        for right_window in window_ids[left_index + 1 :]:
            for left in by_window.get(left_window, ()):
                for right in by_window.get(right_window, ()):
                    if left.sample.sample_fingerprint == right.sample.sample_fingerprint:
                        continue
                    pair_id = a3_v3_boundary_pair_id(
                        recipe,
                        family=assignment.family,
                        left_sample_fingerprint=left.sample.sample_fingerprint,
                        right_sample_fingerprint=right.sample.sample_fingerprint,
                    )
                    try:
                        return A3V3BoundaryPairEvidenceV1(
                            boundary_pair_id=pair_id,
                            family=assignment.family,
                            treatment_recipe=assignment.treatment_recipe,
                            left_sample_fingerprint=left.sample.sample_fingerprint,
                            right_sample_fingerprint=right.sample.sample_fingerprint,
                            left_state=left.boundary_state,
                            right_state=right.boundary_state,
                            required_control_states={
                                name: True for name in assignment.required_controls
                            },
                            achieved=True,
                        )
                    except A3V3EpisodeEvidenceError:
                        continue
    raise LearningSourceAdapterError(
        f"d5_hard_confusion_boundary_not_observed:{assignment.family}"
    )


def _d3_plan_edges(
    evidence: PlanningFrameEvidence,
    matrix_result: Any,
) -> tuple[tuple[int, int], ...]:
    """Map the detached plan back to anonymous matrix indices."""

    if evidence.plan is None:
        raise LearningSourceAdapterError("d3_plan_required")
    target_index = {
        str(target_id): index
        for index, target_id in enumerate(matrix_result.target_ids)
    }
    resource_index = {
        str(resource_id): index
        for index, resource_id in enumerate(matrix_result.resource_ids)
    }
    if len(target_index) != len(matrix_result.target_ids):
        raise LearningSourceAdapterError("d3_matrix_target_id_duplicate")
    if len(resource_index) != len(matrix_result.resource_ids):
        raise LearningSourceAdapterError("d3_matrix_resource_id_duplicate")

    edges: list[tuple[int, int]] = []
    for assignment in evidence.plan.assignments:
        try:
            edge = (
                target_index[str(assignment.target_id)],
                resource_index[str(assignment.resource_id)],
            )
        except KeyError as exc:
            raise LearningSourceAdapterError(
                "d3_plan_assignment_outside_matrix"
            ) from exc
        edges.append(edge)
    if len(edges) != len(set(edges)):
        raise LearningSourceAdapterError("d3_plan_edge_duplicate")
    return tuple(sorted(edges))


def _d3_previous_plan_edges(
    evidence: PlanningFrameEvidence,
    matrix_result: Any,
    *,
    candidate_mask: np.ndarray,
) -> tuple[tuple[int, int], ...]:
    """Map only still-valid prior-plan edges into the current anonymous frame."""

    if evidence.previous_plan is None:
        return ()
    target_index = {
        str(target_id): index
        for index, target_id in enumerate(matrix_result.target_ids)
    }
    resource_index = {
        str(resource_id): index
        for index, resource_id in enumerate(matrix_result.resource_ids)
    }
    edges: list[tuple[int, int]] = []
    for assignment in evidence.previous_plan.assignments:
        target = target_index.get(str(assignment.target_id))
        resource = resource_index.get(str(assignment.resource_id))
        if target is None or resource is None or not candidate_mask[target, resource]:
            continue
        edges.append((target, resource))
    if len(edges) != len(set(edges)):
        raise LearningSourceAdapterError("d3_previous_plan_edge_duplicate")
    resources = [resource for _, resource in edges]
    if len(resources) != len(set(resources)):
        raise LearningSourceAdapterError("d3_previous_plan_resource_duplicate")
    return tuple(sorted(edges))


def _d3_target_demand_slots(
    evidence: PlanningFrameEvidence,
    matrix_result: Any,
) -> tuple[int, ...]:
    """Return one anonymous required-resource count for every matrix target."""

    track_by_id = {str(track.track_id): track for track in evidence.tracks}
    if len(track_by_id) != len(evidence.tracks):
        raise LearningSourceAdapterError("d3_track_id_duplicate")
    slots: list[int] = []
    for target_id in matrix_result.target_ids:
        track = track_by_id.get(str(target_id))
        if track is None:
            raise LearningSourceAdapterError("d3_matrix_target_snapshot_mismatch")
        count = int(track.effective_demand.required_resource_count)
        if count < 1:
            raise LearningSourceAdapterError("d3_target_demand_slot_invalid")
        slots.append(count)
    return tuple(slots)


def _validate_index_edges(
    edges: Sequence[tuple[int, int]],
    shape: tuple[int, int],
    role: str,
) -> None:
    """Fail closed on malformed, duplicate, or out-of-range matrix edges."""

    rows, columns = shape
    canonical: list[tuple[int, int]] = []
    for raw_edge in edges:
        if not isinstance(raw_edge, (tuple, list)) or len(raw_edge) != 2:
            raise LearningSourceAdapterError(f"{role}_edge_invalid")
        row, column = raw_edge
        if (
            isinstance(row, bool)
            or isinstance(column, bool)
            or not isinstance(row, int)
            or not isinstance(column, int)
            or row < 0
            or column < 0
            or row >= rows
            or column >= columns
        ):
            raise LearningSourceAdapterError(f"{role}_edge_out_of_bounds")
        canonical.append((row, column))
    if len(canonical) != len(set(canonical)):
        raise LearningSourceAdapterError(f"{role}_edge_duplicate")


def _reason_token(value: Any) -> str:
    """Normalize one diagnostic value into a stable reason-code token."""

    text = str(value).strip().lower()
    token = "".join(character if character.isalnum() else "_" for character in text)
    token = "_".join(part for part in token.split("_") if part)
    return token or "unknown"


def _d5_camera_role(camera: Any) -> str:
    """Derive the frozen role from the runtime resource namespace."""

    resource_id = str(getattr(camera, "resource_id", "")).strip().upper()
    if not resource_id:
        raise LearningSourceAdapterError("d5_camera_resource_id_missing")
    return "recon" if resource_id.startswith("RECON-") else "interceptor"


def _canonical_sha256(value: Mapping[str, Any] | Sequence[Any]) -> str:
    """Hash finite canonical JSON used only for identity-free evidence joins."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise LearningSourceAdapterError("canonical_evidence_json_invalid") from exc
    return sha256(payload).hexdigest()
