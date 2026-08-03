"""Authorized, resumable generation of D3/D4/D5 scalable learning sources.

The main runtime owns sequencing and provenance. Module-owned writers retain
their validation and storage contracts. This module never trains a model,
consumes a held-out set for evaluation, or grants runtime/control authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Mapping, Sequence

from .learning_source_generation_authorization import (
    LearningSourceGenerationAuthorization,
    load_learning_source_generation_authorization,
)
from .models import ScenarioConfig
from .module_stack import IntegratedScalableModuleStack, IntegratedStackConfig
from .orchestrator import run_episode


SOURCE_GENERATION_SESSION_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-session-v1"
)
SOURCE_GENERATION_CHECKPOINT_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-checkpoint-v1"
)
SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-progress-v1"
)
SOURCE_GENERATION_RESULT_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-result-v1"
)
SOURCE_GENERATION_FAILURE_SCHEMA_VERSION = (
    "scalable3d-learning-source-generation-failure-v1"
)
SOURCE_GENERATION_MODULES = ("D3", "D4", "D5")

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/nominal_200v200.json"
)
D3_SCHEDULE_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_generation_schedule_v1.json"
)
D4_REQUEST_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/reports/"
    "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)
D4_REQUEST_PATH = D4_REQUEST_ROOT / "v8_development_data_request.json"
D4_REGISTRY_PATH = D4_REQUEST_ROOT / "v8_development_seed_registry.json"
D5_SCHEDULE_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d5_terminal_association/configs/"
    "a3_v3_source_collection_schedule_20260801.json"
)


class LearningSourceGenerationError(RuntimeError):
    """A generation session is stale, unsafe, or inconsistent."""


@dataclass(frozen=True)
class ModuleGenerationResult:
    module: str
    planned_episode_count: int
    completed_episode_count: int
    newly_completed_episode_count: int
    finalized: bool
    finalization_summary: Mapping[str, Any] | None


def run_authorized_learning_source_generation(
    *,
    module: str,
    output_dir: str | Path,
    authorization_path: str | Path,
    authorization_sha256: str,
    repository_root: str | Path = REPOSITORY_ROOT,
    base_config_path: str | Path | None = None,
    max_episodes_per_run: int | None = None,
    resume: bool = False,
    minimum_free_gb: float = 5.0,
) -> dict[str, Any]:
    """Run one module's frozen source request from an exact clean commit."""

    selected = str(module).strip().upper()
    if selected not in SOURCE_GENERATION_MODULES:
        raise LearningSourceGenerationError("source_generation_module_invalid")
    if max_episodes_per_run is not None and (
        type(max_episodes_per_run) is not int or max_episodes_per_run <= 0
    ):
        raise LearningSourceGenerationError("max_episodes_per_run_invalid")
    free_gb = float(minimum_free_gb)
    if not math.isfinite(free_gb) or free_gb < 0.0:
        raise LearningSourceGenerationError("minimum_free_gb_invalid")

    root = _safe_existing_directory(repository_root, "repository_root")
    authorization = load_learning_source_generation_authorization(
        authorization_path,
        repository_root=root,
        expected_authorization_sha256=authorization_sha256,
    )
    authorization.assert_module(selected)
    default_config_path = _safe_source_file(
        root / DEFAULT_BASE_CONFIG_PATH.relative_to(REPOSITORY_ROOT),
        root,
        "base_config",
    )
    if base_config_path is not None:
        requested_config_path = _safe_source_file(
            base_config_path,
            root,
            "base_config",
        )
        if requested_config_path != default_config_path:
            raise LearningSourceGenerationError(
                "base_config_override_not_authorized"
            )
    config_path = default_config_path
    base_config = ScenarioConfig.from_dict(
        json.loads(config_path.read_text(encoding="utf-8"))
    )
    output = _safe_output_directory(output_dir)
    schedule_path = _module_schedule_path(selected, root)
    session = _session_payload(
        module=selected,
        authorization=authorization,
        authorization_sha256=authorization_sha256,
        base_config_path=config_path,
        schedule_path=schedule_path,
        repository_root=root,
    )
    _prepare_session(output, expected=session, resume=resume)
    failure_path = output / "generation_failure.json"
    if resume and failure_path.exists():
        if failure_path.is_symlink() or not failure_path.is_file():
            raise LearningSourceGenerationError(
                "source_generation_failure_record_unsafe"
            )
        raise LearningSourceGenerationError("source_generation_failed_closed")
    _require_free_space(output, free_gb)

    invocation_started = time.perf_counter()
    progress_path = output / "episode_progress.jsonl"
    rows = _load_progress(progress_path, expected_session=session)
    prior_checkpoint = _load_optional_checkpoint(output / "generation_checkpoint.json")
    if prior_checkpoint is not None:
        _validate_resume_checkpoint(
            prior_checkpoint,
            expected_session=session,
            result_path=output / "generation_result.json",
        )
    elif (output / "generation_result.json").exists():
        raise LearningSourceGenerationError(
            "generation_result_without_checkpoint"
        )
    invocation_count = (
        1 if prior_checkpoint is None else int(prior_checkpoint["invocation_count"]) + 1
    )
    runner = {
        "D3": _generate_d3,
        "D4": _generate_d4,
        "D5": _generate_d5,
    }[selected]
    try:
        result = runner(
            output=output,
            root=root,
            base_config=base_config,
            authorization=authorization,
            authorization_sha256=authorization_sha256,
            progress_rows=rows,
            progress_path=progress_path,
            max_episodes_per_run=max_episodes_per_run,
            minimum_free_gb=free_gb,
        )
    except Exception as exc:
        try:
            persisted_progress_count = len(
                _load_progress(progress_path, expected_session=session)
            )
        except Exception:
            persisted_progress_count = -1
        failure = {
            "schema_version": SOURCE_GENERATION_FAILURE_SCHEMA_VERSION,
            "state": "failed_closed",
            "module": selected,
            "source_git_commit": authorization.source_git_commit,
            "authorization_id": authorization.authorization_id,
            "authorization_sha256": authorization.authorization_file_sha256,
            "module_request_sha256": authorization.module_request_sha256[selected],
            "planned_episode_count": authorization.planned_episode_count[selected],
            "progress_record_count": persisted_progress_count,
            "exception_type": type(exc).__name__,
            "error_code": str(exc),
            "dataset_generation": True,
            "training_started": False,
            "runtime_authority_granted": False,
            "control_authority_granted": False,
            "formal_seed_payload_read_count": 0,
            "future_held_out_model_consumption_count": 0,
            "requires_new_source_commit": True,
            "requires_new_authorization": True,
            "requires_new_output_directory": True,
        }
        _atomic_json(failure_path, failure)
        raise
    elapsed = time.perf_counter() - invocation_started
    state = "finalized" if result.finalized else "paused"
    checkpoint = {
        "schema_version": SOURCE_GENERATION_CHECKPOINT_SCHEMA_VERSION,
        "state": state,
        "module": selected,
        "source_git_commit": authorization.source_git_commit,
        "authorization_id": authorization.authorization_id,
        "authorization_sha256": authorization.authorization_file_sha256,
        "module_request_sha256": authorization.module_request_sha256[selected],
        "planned_episode_count": result.planned_episode_count,
        "completed_episode_count": result.completed_episode_count,
        "remaining_episode_count": (
            result.planned_episode_count - result.completed_episode_count
        ),
        "next_sequence": result.completed_episode_count,
        "invocation_count": invocation_count,
        "last_invocation_wall_s": elapsed,
        "dataset_generation": True,
        "training_started": False,
        "runtime_authority_granted": False,
        "control_authority_granted": False,
        "formal_seed_payload_read_count": 0,
        "future_held_out_model_consumption_count": 0,
    }
    _atomic_json(output / "generation_checkpoint.json", checkpoint)
    response = {
        **checkpoint,
        "newly_completed_episode_count": result.newly_completed_episode_count,
        "finalization_summary": (
            None
            if result.finalization_summary is None
            else dict(result.finalization_summary)
        ),
    }
    if result.finalized:
        response["schema_version"] = SOURCE_GENERATION_RESULT_SCHEMA_VERSION
        response["artifact_inventory"] = _artifact_inventory(output)
        response = _jsonable(response)
        _atomic_json(output / "generation_result.json", response)
    return _jsonable(response)


def _generate_d3(
    *,
    output: Path,
    root: Path,
    base_config: ScenarioConfig,
    authorization: LearningSourceGenerationAuthorization,
    authorization_sha256: str,
    progress_rows: list[dict[str, Any]],
    progress_path: Path,
    max_episodes_per_run: int | None,
    minimum_free_gb: float,
) -> ModuleGenerationResult:
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
        A1V3DatasetWriter,
    )
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_source_only_projection import (
        A1V3CounterfactualMode,
        A1V3PostProjectionReferencePolicy,
    )

    from .learning_source_adapters import adapt_d3_a1_runtime_frame
    from .learning_source_recipes import load_d3_a1_v3_episode_recipes

    recipes = load_d3_a1_v3_episode_recipes(
        root / D3_SCHEDULE_PATH.relative_to(REPOSITORY_ROOT)
    )
    _assert_authorized_episode_count("D3", len(recipes), authorization)
    writer = A1V3DatasetWriter.from_frozen_paths(
        output / "dataset",
        dataset_id="d3-a1-v3-authorized-source-20260801",
    )
    scheduled = writer.contract.schedule.episodes
    _validate_recipe_binding(
        "D3",
        recipes,
        scheduled,
        recipe_id=lambda item: item.episode_id,
        scheduled_id=lambda item: item.episode_id,
        recipe_seed=lambda item: item.seed,
        scheduled_seed=lambda item: item.seed,
    )
    if writer.staged_episode_ids != tuple(
        item.episode_id for item in recipes[: writer.staged_episode_count]
    ):
        raise LearningSourceGenerationError("D3_staged_inventory_not_prefix")
    start = _reconcile_prefix(
        module="D3",
        rows=progress_rows,
        inventory_count=writer.staged_episode_count,
        expected_ids=[item.episode_id for item in recipes],
        expected_seeds=[item.seed for item in recipes],
        progress_path=progress_path,
        authorization=authorization,
    )
    stop = _stop_index(start, len(recipes), max_episodes_per_run)
    for index in range(start, stop):
        _require_free_space(output, minimum_free_gb)
        config = recipes[index].build_config(base_config)
        episode_started = time.perf_counter()
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(config, module_stack=stack)
        episode_wall_s = time.perf_counter() - episode_started
        _assert_safe_episode(result)
        adapted = tuple(
            adapt_d3_a1_runtime_frame(
                frame,
                source_only_counterfactual_mode=(
                    A1V3CounterfactualMode.COVERAGE_DEGRADING
                ),
                source_only_reference_policy=(
                    A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
                ),
                source_episode_key=(
                    recipes[index].seed,
                    recipes[index].episode_id,
                ),
            )
            for frame in stack.learning_artifacts().d3_a1_source_frames
        )
        staging_started = time.perf_counter()
        staged = writer.stage_episode(scheduled[index], adapted)
        staging_wall_s = time.perf_counter() - staging_started
        _append_progress(
            progress_path,
            _progress_row(
                module="D3",
                sequence=index,
                episode_id=recipes[index].episode_id,
                seed=recipes[index].seed,
                config=config,
                result=result,
                authorization=authorization,
                authorization_sha256=authorization_sha256,
                episode_wall_s=episode_wall_s,
                staging_wall_s=staging_wall_s,
                module_summary=asdict(staged),
            ),
        )
    completed = writer.staged_episode_count
    final_summary: Mapping[str, Any] | None = None
    finalized = completed == len(recipes)
    if finalized:
        final_summary = asdict(writer.finalize())
    return ModuleGenerationResult(
        module="D3",
        planned_episode_count=len(recipes),
        completed_episode_count=completed,
        newly_completed_episode_count=stop - start,
        finalized=finalized,
        finalization_summary=final_summary,
    )


def _generate_d4(
    *,
    output: Path,
    root: Path,
    base_config: ScenarioConfig,
    authorization: LearningSourceGenerationAuthorization,
    authorization_sha256: str,
    progress_rows: list[dict[str, Any]],
    progress_path: Path,
    max_episodes_per_run: int | None,
    minimum_free_gb: float,
) -> ModuleGenerationResult:
    from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_dataset_writer import (
        V8CleanSourceMetadata,
        V8TrainDatasetWriter,
    )
    from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_development_contract import (
        load_v8_frozen_request,
    )

    from .learning_source_adapters import build_d4_v8_runtime_episode
    from .learning_source_recipes import load_d4_a2_v8_episode_recipes

    request_path = root / D4_REQUEST_PATH.relative_to(REPOSITORY_ROOT)
    registry_path = root / D4_REGISTRY_PATH.relative_to(REPOSITORY_ROOT)
    recipes = load_d4_a2_v8_episode_recipes(registry_path)
    _assert_authorized_episode_count("D4", len(recipes), authorization)
    frozen = load_v8_frozen_request(request_path, registry_path)
    metadata = V8CleanSourceMetadata(
        source_scenario_id="scalable-3d-a2-v8-controlled-source",
        source_scenario_version="scalable3d-a2-v8-source-v1",
        source_git_commit=authorization.source_git_commit,
        source_git_dirty=False,
        source_config_sha256=_canonical_sha256(
            {
                "base_config": base_config.to_dict(),
                "request_sha256": authorization.module_request_sha256["D4"],
                "registry_sha256": _file_sha256(registry_path),
            }
        ),
    )
    writer_state_path = output / "d4_writer_state.json"
    if writer_state_path.exists():
        writer_state = _read_json(writer_state_path, "d4_writer_state")
        writer = V8TrainDatasetWriter.resume_from_contract_files(
            staging_root=writer_state["staging_root"],
            dataset_root=output / "dataset",
            main_schedule_path=output / "main_schedule.json",
            request_path=request_path,
            registry_path=registry_path,
            expected_source_metadata=metadata,
            schedule_id="d4-a2-v8-authorized-main-schedule-20260801",
            dataset_id="d4-a2-v8-authorized-train-source-20260801",
        )
    else:
        writer = V8TrainDatasetWriter.from_contract_files(
            dataset_root=output / "dataset",
            main_schedule_path=output / "main_schedule.json",
            request_path=request_path,
            registry_path=registry_path,
            expected_source_metadata=metadata,
            schedule_id="d4-a2-v8-authorized-main-schedule-20260801",
            dataset_id="d4-a2-v8-authorized-train-source-20260801",
        )
        _atomic_json(
            writer_state_path,
            {
                "schema_version": "scalable3d-d4-v8-writer-pointer-v1",
                "staging_root": writer.staging_root.as_posix(),
            },
        )
    _validate_recipe_binding(
        "D4",
        recipes,
        frozen.schedule,
        recipe_id=lambda item: item.episode_id,
        scheduled_id=lambda item: f"d4-a2-v8-train-seed-{item.seed}",
        recipe_seed=lambda item: item.seed,
        scheduled_seed=lambda item: item.seed,
    )
    start = _reconcile_prefix(
        module="D4",
        rows=progress_rows,
        inventory_count=writer.staged_episode_count,
        expected_ids=[item.episode_id for item in recipes],
        expected_seeds=[item.seed for item in recipes],
        progress_path=progress_path,
        authorization=authorization,
    )
    stop = _stop_index(start, len(recipes), max_episodes_per_run)
    try:
        for index in range(start, stop):
            _require_free_space(output, minimum_free_gb)
            config = recipes[index].build_config(base_config)
            episode_started = time.perf_counter()
            stack = IntegratedScalableModuleStack(
                IntegratedStackConfig(capture_learning_artifacts=True)
            )
            result = run_episode(config, module_stack=stack)
            episode_wall_s = time.perf_counter() - episode_started
            _assert_safe_episode(result)
            built = build_d4_v8_runtime_episode(
                recipe=frozen.schedule[index],
                episode_id=recipes[index].episode_id,
                region_frames=stack.learning_artifacts().d4_region_frames,
            )
            staging_started = time.perf_counter()
            staged = writer.stage_episode(
                schedule_index=index,
                episode_id=recipes[index].episode_id,
                frames=built.frames,
                labels=built.labels,
                source_metadata=metadata,
            )
            staging_wall_s = time.perf_counter() - staging_started
            _append_progress(
                progress_path,
                _progress_row(
                    module="D4",
                    sequence=index,
                    episode_id=recipes[index].episode_id,
                    seed=recipes[index].seed,
                    config=config,
                    result=result,
                    authorization=authorization,
                    authorization_sha256=authorization_sha256,
                    episode_wall_s=episode_wall_s,
                    staging_wall_s=staging_wall_s,
                    module_summary=asdict(staged),
                ),
            )
        completed = writer.staged_episode_count
        finalized = completed == len(recipes)
        final_summary: Mapping[str, Any] | None = None
        if finalized:
            final = writer.finalize()
            writer_state_path.unlink(missing_ok=True)
            final_summary = {
                "dataset_root": final.dataset_root.as_posix(),
                "main_schedule_path": final.main_schedule_path.as_posix(),
                "episode_count": len(final.loaded_dataset.episodes),
                "manifest_sha256": _file_sha256(final.dataset_root / "manifest.json"),
                "main_schedule_sha256": _file_sha256(final.main_schedule_path),
            }
        else:
            staging_root = writer.suspend_for_resume()
            _atomic_json(
                writer_state_path,
                {
                    "schema_version": "scalable3d-d4-v8-writer-pointer-v1",
                    "staging_root": staging_root.as_posix(),
                },
            )
    except Exception:
        try:
            staging_root = writer.suspend_for_resume()
            _atomic_json(
                writer_state_path,
                {
                    "schema_version": "scalable3d-d4-v8-writer-pointer-v1",
                    "staging_root": staging_root.as_posix(),
                },
            )
        except Exception:
            pass
        raise
    return ModuleGenerationResult(
        module="D4",
        planned_episode_count=len(recipes),
        completed_episode_count=completed,
        newly_completed_episode_count=stop - start,
        finalized=finalized,
        finalization_summary=final_summary,
    )


def _generate_d5(
    *,
    output: Path,
    root: Path,
    base_config: ScenarioConfig,
    authorization: LearningSourceGenerationAuthorization,
    authorization_sha256: str,
    progress_rows: list[dict[str, Any]],
    progress_path: Path,
    max_episodes_per_run: int | None,
    minimum_free_gb: float,
) -> ModuleGenerationResult:
    from research_modules.d5_terminal_association.src.d5_terminal_association.active_vision_a3_v3_episode_evidence import (
        finalize_a3_v3_generation_partition,
        load_frozen_a3_v3_episode_recipes,
        recover_a3_v3_staged_episode_inventory,
        resume_a3_v3_episode_evidence,
        write_a3_v3_source_manifest,
    )

    from .learning_source_adapters import build_d5_a3_runtime_episode
    from .learning_source_recipes import load_d5_a3_v3_episode_recipes

    schedule_path = root / D5_SCHEDULE_PATH.relative_to(REPOSITORY_ROOT)
    recipes = load_d5_a3_v3_episode_recipes(schedule_path)
    _assert_authorized_episode_count("D5", len(recipes), authorization)
    frozen = load_frozen_a3_v3_episode_recipes(
        source_schedule_path=schedule_path
    )
    _validate_recipe_binding(
        "D5",
        recipes,
        frozen,
        recipe_id=lambda item: item.episode_id,
        scheduled_id=lambda item: item.episode_id,
        recipe_seed=lambda item: item.seed,
        scheduled_seed=lambda item: item.seed,
    )
    development = output / "development"
    future = output / "future_held_out"
    inventory = recover_a3_v3_staged_episode_inventory(
        development_dir=development,
        future_held_out_dir=future,
    )
    staged_ids = list(inventory["staged_episode_ids"])
    expected_ids = [item.episode_id for item in recipes]
    if staged_ids != expected_ids[: len(staged_ids)]:
        raise LearningSourceGenerationError("D5_staged_inventory_not_prefix")
    start = _reconcile_prefix(
        module="D5",
        rows=progress_rows,
        inventory_count=int(inventory["staged_episode_count"]),
        expected_ids=expected_ids,
        expected_seeds=[item.seed for item in recipes],
        progress_path=progress_path,
        authorization=authorization,
    )
    stop = _stop_index(start, len(recipes), max_episodes_per_run)
    for index in range(start, stop):
        _require_free_space(output, minimum_free_gb)
        config = recipes[index].build_config(base_config)
        episode_started = time.perf_counter()
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(
                capture_learning_artifacts=True,
                d5_recon_track_cues_enabled=True,
                d5_active_vision_collection_profile="balanced_action_role_v1",
            )
        )
        result = run_episode(config, module_stack=stack)
        episode_wall_s = time.perf_counter() - episode_started
        _assert_safe_episode(result)
        online, offline = build_d5_a3_runtime_episode(
            recipe=frozen[index],
            active_vision_frames=(
                stack.learning_artifacts().d5_active_vision_frames
            ),
        )
        staging_started = time.perf_counter()
        descriptor = resume_a3_v3_episode_evidence(
            development_dir=development,
            future_held_out_dir=future,
            online=online,
            offline=offline,
        )
        staging_wall_s = time.perf_counter() - staging_started
        _append_progress(
            progress_path,
            _progress_row(
                module="D5",
                sequence=index,
                episode_id=recipes[index].episode_id,
                seed=recipes[index].seed,
                config=config,
                result=result,
                authorization=authorization,
                authorization_sha256=authorization_sha256,
                episode_wall_s=episode_wall_s,
                staging_wall_s=staging_wall_s,
                module_summary={
                    "partition": descriptor["partition"],
                    "online_sha256": descriptor["online_sha256"],
                    "offline_sha256": descriptor["offline_sha256"],
                    "content_sha256": descriptor["content_sha256"],
                    "sample_count": descriptor["validation_summary"]["sample_count"],
                },
            ),
        )
    inventory = recover_a3_v3_staged_episode_inventory(
        development_dir=development,
        future_held_out_dir=future,
    )
    completed = int(inventory["staged_episode_count"])
    finalized = completed == len(recipes)
    final_summary: Mapping[str, Any] | None = None
    if finalized:
        development_recipes = tuple(
            item for item in frozen if item.partition == "development"
        )
        future_recipes = tuple(
            item for item in frozen if item.partition == "future_held_out"
        )
        development_manifest = finalize_a3_v3_generation_partition(
            development,
            partition="development",
            expected_recipes=development_recipes,
        )
        future_manifest = finalize_a3_v3_generation_partition(
            future,
            partition="future_held_out",
            expected_recipes=future_recipes,
        )
        source_manifest = write_a3_v3_source_manifest(
            output / "source_manifest.json",
            development_manifest_path=development / "manifest.json",
            future_held_out_manifest_path=future / "manifest.json",
        )
        final_summary = {
            "development_episode_count": development_manifest["episode_count"],
            "future_held_out_episode_count": future_manifest["episode_count"],
            "source_manifest_sha256": _file_sha256(
                output / "source_manifest.json"
            ),
            "future_held_out_model_consumption_count": 0,
            "status": source_manifest["status"],
        }
    return ModuleGenerationResult(
        module="D5",
        planned_episode_count=len(recipes),
        completed_episode_count=completed,
        newly_completed_episode_count=stop - start,
        finalized=finalized,
        finalization_summary=final_summary,
    )


def _session_payload(
    *,
    module: str,
    authorization: LearningSourceGenerationAuthorization,
    authorization_sha256: str,
    base_config_path: Path,
    schedule_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_GENERATION_SESSION_SCHEMA_VERSION,
        "module": module,
        "source_git_commit": authorization.source_git_commit,
        "authorization_id": authorization.authorization_id,
        "authorization_sha256": _sha256_string(authorization_sha256),
        "preflight_sha256": authorization.preflight_sha256,
        "registry_file_sha256": authorization.registry_file_sha256,
        "module_request_sha256": authorization.module_request_sha256[module],
        "planned_episode_count": authorization.planned_episode_count[module],
        "base_config_path": base_config_path.relative_to(repository_root).as_posix(),
        "base_config_sha256": _file_sha256(base_config_path),
        "schedule_path": schedule_path.relative_to(repository_root).as_posix(),
        "schedule_sha256": _file_sha256(schedule_path),
        "dataset_generation": True,
        "training": False,
        "future_held_out_model_consumption": False,
        "runtime": False,
        "control": False,
        "global_track_id_create": False,
        "global_track_id_write": False,
    }


def _prepare_session(
    output: Path,
    *,
    expected: Mapping[str, Any],
    resume: bool,
) -> None:
    session_path = output / "generation_session.json"
    if resume:
        if not session_path.is_file():
            raise LearningSourceGenerationError("resume_session_missing")
        actual = _read_json(session_path, "generation_session")
        if actual != dict(expected):
            raise LearningSourceGenerationError("resume_session_binding_mismatch")
        return
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"source generation output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    _atomic_json(session_path, expected)


def _progress_row(
    *,
    module: str,
    sequence: int,
    episode_id: str,
    seed: int,
    config: ScenarioConfig,
    result: Any,
    authorization: LearningSourceGenerationAuthorization,
    authorization_sha256: str,
    episode_wall_s: float,
    staging_wall_s: float,
    module_summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION,
        "module": module,
        "sequence": sequence,
        "episode_id": episode_id,
        "seed": seed,
        "source_git_commit": authorization.source_git_commit,
        "authorization_sha256": _sha256_string(authorization_sha256),
        "module_request_sha256": authorization.module_request_sha256[module],
        "config_sha256": _canonical_sha256(config.to_dict()),
        "finite_state": bool(result.summary.get("finite_state")),
        "online_truth_use_count": int(
            result.summary.get("online_truth_use_count", -1)
        ),
        "global_track_id_created_count": int(
            result.summary.get("global_track_id_created_count", 0)
        ),
        "global_track_id_rewritten_count": int(
            result.summary.get("global_track_id_rewritten_count", 0)
        ),
        "episode_run_wall_s": float(episode_wall_s),
        "artifact_stage_wall_s": float(staging_wall_s),
        "module_summary": _jsonable(module_summary),
        "training_started": False,
        "runtime_authority_granted": False,
        "control_authority_granted": False,
    }


def _reconcile_prefix(
    *,
    module: str,
    rows: list[dict[str, Any]],
    inventory_count: int,
    expected_ids: Sequence[str],
    expected_seeds: Sequence[int],
    progress_path: Path,
    authorization: LearningSourceGenerationAuthorization,
) -> int:
    if inventory_count < len(rows) or inventory_count > len(expected_ids):
        raise LearningSourceGenerationError(f"{module}_inventory_progress_mismatch")
    for index, row in enumerate(rows):
        if (
            row.get("module") != module
            or row.get("sequence") != index
            or row.get("episode_id") != expected_ids[index]
            or row.get("seed") != expected_seeds[index]
            or row.get("source_git_commit") != authorization.source_git_commit
            or row.get("module_request_sha256")
            != authorization.module_request_sha256[module]
        ):
            raise LearningSourceGenerationError(f"{module}_progress_prefix_invalid")
    for index in range(len(rows), inventory_count):
        recovered = {
            "schema_version": SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION,
            "module": module,
            "sequence": index,
            "episode_id": expected_ids[index],
            "seed": expected_seeds[index],
            "source_git_commit": authorization.source_git_commit,
            "authorization_sha256": authorization.authorization_file_sha256,
            "module_request_sha256": authorization.module_request_sha256[module],
            "status": "staged_episode_recovered_after_progress_gap",
            "finite_state": True,
            "online_truth_use_count": 0,
            "global_track_id_created_count": 0,
            "global_track_id_rewritten_count": 0,
            "timing_available": False,
            "training_started": False,
            "runtime_authority_granted": False,
            "control_authority_granted": False,
        }
        _append_progress(progress_path, recovered)
        rows.append(recovered)
    return inventory_count


def _load_progress(
    path: Path,
    *,
    expected_session: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise LearningSourceGenerationError("progress_symlink_forbidden")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            raise LearningSourceGenerationError("progress_blank_line")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LearningSourceGenerationError(
                f"progress_json_invalid:{line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise LearningSourceGenerationError("progress_record_not_object")
        if (
            row.get("schema_version") != SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION
            or row.get("module") != expected_session["module"]
            or row.get("source_git_commit") != expected_session["source_git_commit"]
            or row.get("module_request_sha256")
            != expected_session["module_request_sha256"]
        ):
            raise LearningSourceGenerationError("progress_binding_mismatch")
        rows.append(row)
    return rows


def _append_progress(path: Path, row: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = _canonical_json_bytes(row)
    with path.open("ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _assert_safe_episode(result: Any) -> None:
    summary = result.summary
    if (
        summary.get("finite_state") is not True
        or int(summary.get("online_truth_use_count", -1)) != 0
        or int(summary.get("global_track_id_created_count", 0)) != 0
        or int(summary.get("global_track_id_rewritten_count", 0)) != 0
    ):
        raise LearningSourceGenerationError("source_episode_safety_gate_failed")


def _validate_recipe_binding(
    module: str,
    recipes: Sequence[Any],
    scheduled: Sequence[Any],
    *,
    recipe_id: Callable[[Any], str],
    scheduled_id: Callable[[Any], str],
    recipe_seed: Callable[[Any], int],
    scheduled_seed: Callable[[Any], int],
) -> None:
    if len(recipes) != len(scheduled):
        raise LearningSourceGenerationError(f"{module}_schedule_count_mismatch")
    for recipe, item in zip(recipes, scheduled, strict=True):
        if (
            recipe_id(recipe) != scheduled_id(item)
            or recipe_seed(recipe) != scheduled_seed(item)
        ):
            raise LearningSourceGenerationError(f"{module}_schedule_binding_mismatch")


def _module_schedule_path(module: str, root: Path) -> Path:
    relative = {
        "D3": D3_SCHEDULE_PATH.relative_to(REPOSITORY_ROOT),
        "D4": D4_REGISTRY_PATH.relative_to(REPOSITORY_ROOT),
        "D5": D5_SCHEDULE_PATH.relative_to(REPOSITORY_ROOT),
    }[module]
    return _safe_source_file(root / relative, root, f"{module}_schedule")


def _safe_existing_directory(path: str | Path, name: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    if _has_existing_symlink_component(candidate):
        raise LearningSourceGenerationError(f"{name}_symlink_forbidden")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise LearningSourceGenerationError(f"{name}_invalid")
    return resolved


def _safe_source_file(path: str | Path, root: Path, name: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    if _has_existing_symlink_component(candidate):
        raise LearningSourceGenerationError(f"{name}_symlink_forbidden")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LearningSourceGenerationError(f"{name}_outside_repository") from exc
    if not resolved.is_file():
        raise LearningSourceGenerationError(f"{name}_missing")
    return resolved


def _safe_output_directory(path: str | Path) -> Path:
    candidate = Path(path).expanduser().absolute()
    if _has_existing_symlink_component(candidate):
        raise LearningSourceGenerationError("output_symlink_forbidden")
    resolved = candidate.resolve()
    if resolved.exists() and not resolved.is_dir():
        raise LearningSourceGenerationError("output_not_directory")
    parent = resolved if resolved.exists() else resolved.parent
    parent.mkdir(parents=True, exist_ok=True)
    if _has_existing_symlink_component(candidate):
        raise LearningSourceGenerationError("output_parent_symlink_forbidden")
    return resolved


def _has_existing_symlink_component(path: Path) -> bool:
    """Inspect the unresolved path so parent symlinks survive validation."""

    absolute = path.expanduser().absolute()
    return any(
        component.is_symlink()
        for component in (absolute, *absolute.parents)
    )


def _require_free_space(path: Path, minimum_free_gb: float) -> None:
    probe = path if path.exists() else path.parent
    free = shutil.disk_usage(probe).free
    if free < minimum_free_gb * 1024**3:
        raise LearningSourceGenerationError(
            f"source_generation_free_space_below_limit:{free}"
        )


def _stop_index(start: int, total: int, maximum: int | None) -> int:
    return total if maximum is None else min(total, start + maximum)


def _load_optional_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = _read_json(path, "generation_checkpoint")
    if payload.get("schema_version") != SOURCE_GENERATION_CHECKPOINT_SCHEMA_VERSION:
        raise LearningSourceGenerationError("generation_checkpoint_schema_mismatch")
    return payload


def _validate_resume_checkpoint(
    payload: Mapping[str, Any],
    *,
    expected_session: Mapping[str, Any],
    result_path: Path,
) -> None:
    """Reject stale, escalated, or already-finalized resumptions."""

    binding_fields = (
        "module",
        "source_git_commit",
        "authorization_id",
        "authorization_sha256",
        "module_request_sha256",
        "planned_episode_count",
    )
    if any(
        payload.get(name) != expected_session.get(name)
        for name in binding_fields
    ):
        raise LearningSourceGenerationError(
            "generation_checkpoint_binding_mismatch"
        )
    state = payload.get("state")
    if state == "finalized":
        if not result_path.is_file() or result_path.is_symlink():
            raise LearningSourceGenerationError(
                "finalized_checkpoint_result_missing_or_unsafe"
            )
        raise LearningSourceGenerationError(
            "source_generation_already_finalized"
        )
    if state != "paused":
        raise LearningSourceGenerationError(
            "generation_checkpoint_state_invalid"
        )
    if result_path.exists() or result_path.is_symlink():
        raise LearningSourceGenerationError(
            "paused_checkpoint_has_generation_result"
        )
    planned = payload.get("planned_episode_count")
    completed = payload.get("completed_episode_count")
    remaining = payload.get("remaining_episode_count")
    next_sequence = payload.get("next_sequence")
    invocation_count = payload.get("invocation_count")
    if (
        type(planned) is not int
        or type(completed) is not int
        or type(remaining) is not int
        or type(next_sequence) is not int
        or type(invocation_count) is not int
        or planned <= 0
        or completed < 0
        or completed >= planned
        or remaining != planned - completed
        or next_sequence != completed
        or invocation_count <= 0
    ):
        raise LearningSourceGenerationError(
            "generation_checkpoint_progress_invalid"
        )
    elapsed = payload.get("last_invocation_wall_s")
    if (
        type(elapsed) not in (int, float)
        or isinstance(elapsed, bool)
        or not math.isfinite(float(elapsed))
        or float(elapsed) < 0.0
    ):
        raise LearningSourceGenerationError(
            "generation_checkpoint_timing_invalid"
        )
    expected_false = (
        "training_started",
        "runtime_authority_granted",
        "control_authority_granted",
    )
    if (
        payload.get("dataset_generation") is not True
        or any(payload.get(name) is not False for name in expected_false)
        or payload.get("formal_seed_payload_read_count") != 0
        or payload.get("future_held_out_model_consumption_count") != 0
    ):
        raise LearningSourceGenerationError(
            "generation_checkpoint_authority_boundary_invalid"
        )


def _assert_authorized_episode_count(
    module: str,
    actual_count: int,
    authorization: LearningSourceGenerationAuthorization,
) -> None:
    expected = authorization.planned_episode_count[module]
    if type(actual_count) is not int or actual_count != expected:
        raise LearningSourceGenerationError(
            f"{module}_authorized_episode_count_mismatch"
        )


def _read_json(path: Path, name: str) -> dict[str, Any]:
    if path.is_symlink():
        raise LearningSourceGenerationError(f"{name}_symlink_forbidden")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearningSourceGenerationError(f"{name}_json_invalid") from exc
    if not isinstance(payload, dict):
        raise LearningSourceGenerationError(f"{name}_not_object")
    return payload


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    content = _canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    if temporary.is_symlink():
        raise LearningSourceGenerationError("atomic_temporary_symlink_forbidden")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_string(value: str) -> str:
    text = str(value)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise LearningSourceGenerationError("sha256_invalid")
    return text


def _artifact_inventory(root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    total_size = 0
    excluded = {"generation_result.json"}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded:
            continue
        if path.is_symlink():
            raise LearningSourceGenerationError("artifact_symlink_forbidden")
        size = path.stat().st_size
        total_size += size
        records.append(
            {"path": relative, "size_bytes": size, "sha256": _file_sha256(path)}
        )
    return {
        "file_count": len(records),
        "total_size_bytes": total_size,
        "files": records,
        "tree_sha256": _canonical_sha256({"files": records}),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        return _jsonable(value.value)
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")


__all__ = [
    "LearningSourceGenerationError",
    "ModuleGenerationResult",
    "SOURCE_GENERATION_CHECKPOINT_SCHEMA_VERSION",
    "SOURCE_GENERATION_MODULES",
    "SOURCE_GENERATION_PROGRESS_SCHEMA_VERSION",
    "SOURCE_GENERATION_RESULT_SCHEMA_VERSION",
    "SOURCE_GENERATION_SESSION_SCHEMA_VERSION",
    "run_authorized_learning_source_generation",
]
