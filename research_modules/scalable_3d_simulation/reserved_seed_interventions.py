"""Main-owned reserved-seed orchestration for isolated D3/D4 interventions.

The runner executes one deterministic rule episode for each reserved seed and
reuses the exact same planning/region snapshot for the control and treatment
arms.  The module intentionally stops at execution receipts.  It does not
publish either arm, issue runtime acknowledgements, or infer physical,
counterfactual, or causal outcomes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, is_dataclass, replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Sequence
import uuid

import numpy as np

from .episode_bus import jsonable
from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .module_stack import IntegratedStackConfig
from .orchestrator import EpisodeResult, Scalable3DEpisodeRunner
from .scenarios import make_curriculum_scenario


RESERVED_SEED_INTERVENTION_SCHEMA_VERSION = (
    "scalable3d-reserved-seed-interventions-v2"
)
RESERVED_SEED_SOURCE_LINEAGE_SCHEMA_VERSION = (
    "scalable3d-reserved-seed-source-lineage-v1"
)
RESERVED_EVALUATION_SEEDS = tuple(range(1000, 1020))
INTERVENTION_SELECTION_POLICY = "first-common-frame-after-prior-plan-v1"
D1_D2_LINEAGE_CONTRACT_VERSION = "scalable3d-d1-d2-planning-evidence-v1"
D3_SAFETY_SHELL_VERSION = "d3-offline-intervention-safety-shell-v2"


@dataclass(frozen=True, slots=True)
class D3DevelopmentBundleBinding:
    """Out-of-band identity for the frozen D3 development bundle."""

    bundle_dir: Path
    manifest_sha256: str
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_dir", Path(self.bundle_dir))
        _require_sha256(self.manifest_sha256, "manifest_sha256")
        if not str(self.policy_version).strip():
            raise ValueError("policy_version must be non-empty")


@dataclass(frozen=True, slots=True)
class ReservedSeedInterventionOptions:
    """Scenario controls shared by all twenty reserved source episodes."""

    scenario: str = "nominal"
    scale: int = 5
    target_count: int | None = None
    resource_count: int | None = None
    duration_s: float = 2.2
    created_at_utc: str = "2026-07-21T00:00:00Z"
    reserved_seeds: tuple[int, ...] = RESERVED_EVALUATION_SEEDS

    def __post_init__(self) -> None:
        scenario = str(self.scenario).strip().lower()
        if not scenario:
            raise ValueError("scenario must be non-empty")
        object.__setattr__(self, "scenario", scenario)
        if int(self.scale) <= 0:
            raise ValueError("scale must be positive")
        for name in ("target_count", "resource_count"):
            value = getattr(self, name)
            if value is not None and int(value) <= 0:
                raise ValueError(f"{name} must be positive when provided")
        if not isfinite(float(self.duration_s)) or float(self.duration_s) <= 0.0:
            raise ValueError("duration_s must be positive and finite")
        if not str(self.created_at_utc).strip():
            raise ValueError("created_at_utc must be non-empty")
        seeds = tuple(int(seed) for seed in self.reserved_seeds)
        if seeds != RESERVED_EVALUATION_SEEDS:
            raise ValueError("reserved seeds must be exactly 1000-1019")
        object.__setattr__(self, "reserved_seeds", seeds)


@dataclass(frozen=True, slots=True)
class ReservedSeedSourceEvidence:
    """Truth-free hashes and module inputs selected from one source episode."""

    seed: int
    scenario_config: Any
    source_episode_id: str
    source_git_commit: str
    source_repository_dirty: bool
    source_episode_manifest_sha256: str
    source_summary_sha256: str
    scenario_config_sha256: str
    initial_state_sha256: str
    communication_schedule_sha256: str
    fault_schedule_sha256: str
    d3_planning_frame: Any
    d4_region_snapshot: Any
    d3_input_snapshot_sha256: str
    d4_region_snapshot_lineage_sha256: str
    intervention_timestamp_s: float
    finite_state: bool
    online_truth_use_count: int

    def lineage_payload(self) -> dict[str, Any]:
        return {
            "schema_version": RESERVED_SEED_SOURCE_LINEAGE_SCHEMA_VERSION,
            "seed": int(self.seed),
            "scenario_id": self.scenario_config.scenario_name,
            "scenario_version": self.scenario_config.scenario_version,
            "source_episode_id": self.source_episode_id,
            "source_git_commit": self.source_git_commit,
            "source_repository_dirty": bool(self.source_repository_dirty),
            "source_episode_manifest_sha256": self.source_episode_manifest_sha256,
            "source_summary_sha256": self.source_summary_sha256,
            "scenario_config_sha256": self.scenario_config_sha256,
            "initial_state_sha256": self.initial_state_sha256,
            "communication_schedule_sha256": self.communication_schedule_sha256,
            "fault_schedule_sha256": self.fault_schedule_sha256,
            "d3_input_snapshot_sha256": self.d3_input_snapshot_sha256,
            "d4_region_snapshot_lineage_sha256": (
                self.d4_region_snapshot_lineage_sha256
            ),
            "intervention_timestamp_s": float(self.intervention_timestamp_s),
            "frame_selection_policy": INTERVENTION_SELECTION_POLICY,
            "finite_state": bool(self.finite_state),
            "online_truth_use_count": int(self.online_truth_use_count),
            "control_and_treatment_share_source_episode": True,
            "control_and_treatment_share_sensor_random_stream": True,
            "control_and_treatment_share_communication_schedule": True,
            "control_and_treatment_share_fault_schedule": True,
        }


@dataclass(frozen=True, slots=True)
class ReservedSeedSourceBatch:
    sources: tuple[ReservedSeedSourceEvidence, ...]
    planner_config: Any
    cost_weights: Any

    def __post_init__(self) -> None:
        if tuple(item.seed for item in self.sources) != RESERVED_EVALUATION_SEEDS:
            raise ValueError("source batch must contain ordered seeds 1000-1019")


@dataclass(frozen=True, slots=True)
class ReservedSeedInterventionExecution:
    """In-memory D3/D4 receipt set with all online authority disabled."""

    options: ReservedSeedInterventionOptions
    sources: tuple[ReservedSeedSourceEvidence, ...]
    d3_execution: Any
    d4_manifest: Any
    d4_candidate_loader_ready: bool
    d4_candidate_load_rejection_reasons: tuple[str, ...]

    @property
    def source_truth_violation_count(self) -> int:
        return sum(int(item.online_truth_use_count) for item in self.sources)

    @property
    def source_nonfinite_count(self) -> int:
        return sum(not item.finite_state for item in self.sources)


def resolve_d3_development_bundle_binding(
    bundle_dir: str | Path,
    *,
    expected_manifest_sha256: str | None = None,
    expected_policy_version: str | None = None,
) -> D3DevelopmentBundleBinding:
    """Resolve the D3 identity without relaxing its module-owned admission gate."""

    source = Path(bundle_dir)
    manifest_path = source / "manifest.json"
    actual_sha: str | None = None
    actual_version: str | None = None
    if manifest_path.is_file():
        actual_sha = _file_sha256(manifest_path)
        payload = _read_json(manifest_path)
        actual_version = str(payload.get("policy_version", "")).strip() or None
    manifest_sha = expected_manifest_sha256 or actual_sha
    policy_version = expected_policy_version or actual_version
    if manifest_sha is None:
        raise FileNotFoundError(
            "D3 bundle manifest is missing and no expected SHA-256 was supplied"
        )
    if policy_version is None:
        raise ValueError(
            "D3 bundle policy version is unavailable and no expected version was supplied"
        )
    if expected_manifest_sha256 is not None and actual_sha is not None:
        if expected_manifest_sha256 != actual_sha:
            raise ValueError("D3 bundle manifest SHA-256 does not match expectation")
    if expected_policy_version is not None and actual_version is not None:
        if expected_policy_version != actual_version:
            raise ValueError("D3 bundle policy version does not match expectation")
    return D3DevelopmentBundleBinding(
        bundle_dir=source,
        manifest_sha256=manifest_sha,
        policy_version=policy_version,
    )


def collect_reserved_seed_sources(
    options: ReservedSeedInterventionOptions,
) -> ReservedSeedSourceBatch:
    """Run one rule-only episode per seed and select a common D3/D4 frame."""

    sources: list[ReservedSeedSourceEvidence] = []
    planner_config: Any | None = None
    cost_weights: Any | None = None
    planner_config_sha: str | None = None
    cost_weights_sha: str | None = None

    for seed in options.reserved_seeds:
        config = make_curriculum_scenario(
            options.scenario,
            scale=options.scale,
            seed=seed,
            duration_s=options.duration_s,
            target_count=options.target_count,
            resource_count=options.resource_count,
        )
        config = replace(config, sensor_random_schedule_version="entity_fixed_v1")
        resolved = resolve_learning_runtime(
            config,
            LearningRuntimeOptions(),
            stack_config=IntegratedStackConfig(capture_learning_artifacts=True),
        )
        result = Scalable3DEpisodeRunner(
            resolved.config,
            module_stack=resolved.stack,
        ).run()
        artifacts = resolved.stack.learning_artifacts()
        d3_frame, d4_frame = _select_common_intervention_frames(
            artifacts.d3_planning_frames,
            artifacts.d4_region_frames,
        )
        _validate_source_episode(result, seed=seed)
        if int(d4_frame.snapshot.seed) != seed:
            raise ValueError("D4 region snapshot seed does not match source episode")
        if d4_frame.snapshot.scenario_version != resolved.config.scenario_version:
            raise ValueError("D4 region snapshot scenario version mismatch")

        current_planner_config = resolved.stack.d3.config
        current_cost_weights = resolved.stack.d3.cost_model.weights
        current_planner_sha = _canonical_sha256(_dataclass_payload(current_planner_config))
        current_weights_sha = _canonical_sha256(_dataclass_payload(current_cost_weights))
        if planner_config is None:
            planner_config = current_planner_config
            cost_weights = current_cost_weights
            planner_config_sha = current_planner_sha
            cost_weights_sha = current_weights_sha
        elif (
            current_planner_sha != planner_config_sha
            or current_weights_sha != cost_weights_sha
        ):
            raise ValueError("D3 planner configuration changed across reserved seeds")

        scenario_payload = resolved.config.to_dict()
        sources.append(
            ReservedSeedSourceEvidence(
                seed=seed,
                scenario_config=resolved.config,
                source_episode_id=result.manifest.episode_id,
                source_git_commit=result.manifest.git_commit,
                source_repository_dirty=bool(result.manifest.repository_dirty),
                source_episode_manifest_sha256=_canonical_sha256(
                    jsonable(result.manifest)
                ),
                source_summary_sha256=_canonical_sha256(result.summary),
                scenario_config_sha256=_canonical_sha256(scenario_payload),
                initial_state_sha256=_initial_state_sha256(result),
                communication_schedule_sha256=_communication_schedule_sha256(
                    resolved.config
                ),
                fault_schedule_sha256=_fault_schedule_sha256(resolved.config),
                d3_planning_frame=d3_frame,
                d4_region_snapshot=d4_frame.snapshot,
                d3_input_snapshot_sha256=_d3_input_snapshot_sha256(d3_frame),
                d4_region_snapshot_lineage_sha256=_canonical_sha256(
                    d4_frame.snapshot.to_dict()
                ),
                intervention_timestamp_s=float(d3_frame.timestamp_s),
                finite_state=bool(result.summary["finite_state"]),
                online_truth_use_count=int(
                    result.summary["online_truth_use_count"]
                ),
            )
        )

    assert planner_config is not None
    assert cost_weights is not None
    return ReservedSeedSourceBatch(
        sources=tuple(sources),
        planner_config=planner_config,
        cost_weights=cost_weights,
    )


def execute_reserved_seed_interventions(
    options: ReservedSeedInterventionOptions,
    *,
    d3_bundle: D3DevelopmentBundleBinding,
    d4_bundle_dir: str | Path,
) -> ReservedSeedInterventionExecution:
    """Execute D3 and D4 control/treatment arms on shared source snapshots."""

    source_batch = collect_reserved_seed_sources(options)
    d3_specification = _build_d3_specification(source_batch.sources, d3_bundle)
    from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
        execute_offline_paired_intervention,
    )

    d3_execution = execute_offline_paired_intervention(
        d3_specification,
        {item.seed: item.d3_planning_frame for item in source_batch.sources},
        bundle_dir=d3_bundle.bundle_dir,
        planner_config=source_batch.planner_config,
        cost_weights=source_batch.cost_weights,
    )

    d4_specification = _build_d4_specification(source_batch.sources)
    from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
        RegionResourceIsolatedPairedEvaluator,
        RegionResourcePairedArm,
        RegionResourcePairedInterventionManifest,
    )

    d4_evaluator = RegionResourceIsolatedPairedEvaluator(
        d4_specification,
        Path(d4_bundle_dir),
    )
    d4_records = []
    for source in source_batch.sources:
        binding = d4_specification.arm_for(
            source.seed,
            RegionResourcePairedArm.CONTROL,
        ).input_binding
        control, treatment = d4_evaluator.execute_pair(
            seed=source.seed,
            observed_input_binding=binding,
            snapshot=source.d4_region_snapshot,
            evaluated_at_s=source.intervention_timestamp_s,
        )
        d4_records.extend((control, treatment))
    d4_manifest = RegionResourcePairedInterventionManifest(
        specification=d4_specification,
        arm_evidence=tuple(d4_records),
        created_at_utc=options.created_at_utc,
    )
    execution = ReservedSeedInterventionExecution(
        options=options,
        sources=source_batch.sources,
        d3_execution=d3_execution,
        d4_manifest=d4_manifest,
        d4_candidate_loader_ready=d4_evaluator.candidate_loader_ready,
        d4_candidate_load_rejection_reasons=tuple(
            d4_evaluator.load_rejection_reasons
        ),
    )
    _validate_execution_boundaries(execution)
    return execution


def write_reserved_seed_intervention_execution(
    destination: str | Path,
    execution: ReservedSeedInterventionExecution,
) -> dict[str, Path]:
    """Atomically publish receipts, lineage, hashes, and a Chinese report."""

    output = Path(destination)
    if output.exists():
        raise FileExistsError(f"reserved-seed output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir(parents=True)
    try:
        lineage_path = temporary / "source_lineage.jsonl"
        with lineage_path.open("w", encoding="utf-8") as stream:
            for source in execution.sources:
                stream.write(_canonical_json(source.lineage_payload()))
                stream.write("\n")

        d3_path = temporary / "d3_offline_paired_intervention.json"
        from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
            write_offline_paired_intervention_execution,
        )

        write_offline_paired_intervention_execution(d3_path, execution.d3_execution)

        d4_path = temporary / "d4_offline_paired_intervention.json"
        _write_json(d4_path, _d4_execution_payload(execution))

        report_path = temporary / "RESERVED_SEED_INTERVENTION_REPORT_CN.md"
        report_path.write_text(_render_report(execution), encoding="utf-8")

        artifact_paths = {
            "source_lineage": lineage_path,
            "d3_execution": d3_path,
            "d4_execution": d4_path,
            "report_cn": report_path,
        }
        artifact_hashes = {
            name: _file_sha256(path) for name, path in artifact_paths.items()
        }
        manifest_path = temporary / "manifest.json"
        _write_json(
            manifest_path,
            _top_level_manifest(execution, artifact_hashes),
        )
        artifact_paths["manifest"] = manifest_path
        artifact_hashes["manifest"] = _file_sha256(manifest_path)

        checksums_path = temporary / "SHA256SUMS"
        checksum_lines = [
            f"{artifact_hashes[name]}  {artifact_paths[name].name}"
            for name in sorted(artifact_paths)
        ]
        checksums_path.write_text("\n".join(checksum_lines) + "\n", encoding="ascii")
        temporary.replace(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "source_lineage": output / "source_lineage.jsonl",
        "d3_execution": output / "d3_offline_paired_intervention.json",
        "d4_execution": output / "d4_offline_paired_intervention.json",
        "manifest": output / "manifest.json",
        "report_cn": output / "RESERVED_SEED_INTERVENTION_REPORT_CN.md",
        "checksums": output / "SHA256SUMS",
    }


def _build_d3_specification(
    sources: Sequence[ReservedSeedSourceEvidence],
    bundle: D3DevelopmentBundleBinding,
) -> Any:
    from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
        BINARY_EDGE_FEATURE_NAMES,
        BINARY_FEATURE_ENDPOINT_TOLERANCE,
        CONTROL_ARM,
        CONTROL_PLANNER_PATH,
        D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
        D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1,
        D6_SIDECAR_OWNER,
        FEATURE_DISTRIBUTION_ASSESSMENT_SCHEMA_V1,
        OFFLINE_INTERVENTION_SCOPE,
        PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
        PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
        SHADOW_EVALUATION_SCHEMA_V2,
        TREATMENT_ARM,
        TREATMENT_PLANNER_PATH,
        PairedInterventionArmSpecification,
        PairedInterventionSeedPair,
        PairedInterventionSpecification,
    )

    pairs = []
    for source in sources:
        frame = source.d3_planning_frame
        previous_plan = frame.previous_plan
        if previous_plan is None:
            raise ValueError("D3 intervention frame must have a previous plan")
        lineage_sha = _canonical_sha256(
            {
                "contract_version": D1_D2_LINEAGE_CONTRACT_VERSION,
                "planning_frame_schema": frame.schema_version,
                "online_truth_policy": "forbidden",
                "global_track_id_owner": "d2_center",
            }
        )
        rule_config_sha = _canonical_sha256(
            {
                "profile_version": source.scenario_config.d3_policy_version,
                "planning_path": frame.planning_path,
                "selection_source": frame.selection_source,
            }
        )
        threshold_sha = _canonical_sha256(
            {
                "threshold_version": source.scenario_config.threshold_version,
                "assignment_period_s": source.scenario_config.assignment_period_s,
                "physics_dt_s": source.scenario_config.physics_dt_s,
            }
        )
        safety_sha = _canonical_sha256(
            {
                "safety_shell_version": D3_SAFETY_SHELL_VERSION,
                "offline_only": True,
                "version_gate": True,
                "reachability_gate": True,
                "capacity_gate": True,
                "hysteresis_gate": True,
                "rule_fallback": True,
                "feature_distribution_diagnostic_schema": (
                    FEATURE_DISTRIBUTION_ASSESSMENT_SCHEMA_V1
                ),
                "binary_feature_names": list(BINARY_EDGE_FEATURE_NAMES),
                "binary_feature_endpoint_tolerance": (
                    BINARY_FEATURE_ENDPOINT_TOLERANCE
                ),
                "continuous_feature_z_gate_unchanged": True,
            }
        )
        valid_until = source.intervention_timestamp_s + max(
            source.scenario_config.assignment_period_s,
            source.scenario_config.physics_dt_s,
        )
        common = {
            "seed": source.seed,
            "intervention_scope": OFFLINE_INTERVENTION_SCOPE,
            "scenario_version": source.scenario_config.scenario_version,
            "scenario_config_sha256": source.scenario_config_sha256,
            "initial_world_state_sha256": source.initial_state_sha256,
            "observation_input_snapshot_sha256": source.d3_input_snapshot_sha256,
            "input_snapshot_schema_version": frame.schema_version,
            "d1_d2_lineage_contract_version": D1_D2_LINEAGE_CONTRACT_VERSION,
            "d1_d2_lineage_contract_sha256": lineage_sha,
            "rule_cost_profile_version": source.scenario_config.d3_policy_version,
            "rule_cost_config_sha256": rule_config_sha,
            "d3_bundle_version": bundle.policy_version,
            "d3_bundle_sha256": bundle.manifest_sha256,
            "d3_bundle_frozen": True,
            "threshold_version": source.scenario_config.threshold_version,
            "threshold_config_sha256": threshold_sha,
            "threshold_frozen": True,
            "safety_shell_version": D3_SAFETY_SHELL_VERSION,
            "safety_shell_config_sha256": safety_sha,
            "source_plan_id": previous_plan.plan_id,
            "source_plan_version": previous_plan.version,
            "expected_previous_plan_version": previous_plan.version,
            "current_plan_version": previous_plan.version,
            "source_plan_created_at_s": previous_plan.created_at,
            "intervention_timestamp_s": source.intervention_timestamp_s,
            "plan_valid_until_s": valid_until,
            "ppo_enabled": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "rule_fallback_enabled": True,
        }
        control = PairedInterventionArmSpecification(
            arm_id=f"d3-{source.seed}-control",
            arm_kind=CONTROL_ARM,
            isolation_id=f"{source.source_episode_id}-control",
            planner_path=CONTROL_PLANNER_PATH,
            learning_cost_intervention_enabled=False,
            **common,
        )
        treatment = PairedInterventionArmSpecification(
            arm_id=f"d3-{source.seed}-treatment",
            arm_kind=TREATMENT_ARM,
            isolation_id=f"{source.source_episode_id}-treatment",
            planner_path=TREATMENT_PLANNER_PATH,
            learning_cost_intervention_enabled=True,
            **common,
        )
        pairs.append(
            PairedInterventionSeedPair(
                pair_id=f"d3-reserved-pair-{source.seed}",
                seed=source.seed,
                control=control,
                treatment=treatment,
            )
        )
    return PairedInterventionSpecification(
        experiment_id="scalable3d-d3-reserved-intervention",
        experiment_version=RESERVED_SEED_INTERVENTION_SCHEMA_VERSION,
        reserved_seed_policy_version=PAIRED_INTERVENTION_RESERVED_SEED_POLICY_V1,
        reserved_seeds=PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
        paired_evaluator_schema_version=SHADOW_EVALUATION_SCHEMA_V2,
        runtime_ack_evidence_schema_version=D3_RUNTIME_PLAN_ACK_EVIDENCE_SCHEMA_V1,
        runtime_reward_evidence_schema_version=(
            D3_RUNTIME_PLAN_WINDOW_REWARD_EVIDENCE_SCHEMA_V1
        ),
        d6_sidecar_owner=D6_SIDECAR_OWNER,
        ppo_enabled=False,
        online_assist_enabled=False,
        online_authority_enabled=False,
        rule_fallback_enabled=True,
        pairs=tuple(pairs),
    )


def _build_d4_specification(
    sources: Sequence[ReservedSeedSourceEvidence],
) -> Any:
    from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
        REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
        RegionResourcePairedInputBinding,
        build_region_resource_paired_intervention_specification,
    )

    bindings = tuple(
        RegionResourcePairedInputBinding(
            seed=source.seed,
            scenario_id=source.d4_region_snapshot.scenario_id,
            scenario_version=source.d4_region_snapshot.scenario_version,
            scenario_config_sha256=source.scenario_config_sha256,
            initial_state_sha256=source.initial_state_sha256,
            communication_schedule_sha256=source.communication_schedule_sha256,
            fault_schedule_sha256=source.fault_schedule_sha256,
            region_snapshot_lineage_sha256=(
                source.d4_region_snapshot_lineage_sha256
            ),
        )
        for source in sources
    )
    return build_region_resource_paired_intervention_specification(
        experiment_id="scalable3d-d4-reserved-intervention",
        experiment_version=RESERVED_SEED_INTERVENTION_SCHEMA_VERSION,
        input_bindings=bindings,
        candidate_bundle=REGION_RESOURCE_FROZEN_DEVELOPMENT_BUNDLE_BINDING,
    )


def _select_common_intervention_frames(
    d3_frames: Sequence[Any],
    d4_frames: Sequence[Any],
) -> tuple[Any, Any]:
    d3_candidates = [
        frame
        for frame in d3_frames
        if bool(getattr(frame, "available", False))
        and getattr(frame, "timestamp_s", None) is not None
        and getattr(frame, "previous_plan", None) is not None
        and getattr(frame, "plan", None) is not None
    ]
    d4_candidates = [
        frame
        for frame in d4_frames
        if getattr(frame, "snapshot", None) is not None
        and isfinite(float(getattr(frame, "timestamp_s", float("nan"))))
    ]
    matches = [
        (float(d3.timestamp_s), d3, d4)
        for d3 in d3_candidates
        for d4 in d4_candidates
        if abs(float(d3.timestamp_s) - float(d4.timestamp_s)) <= 1.0e-9
    ]
    if not matches:
        raise ValueError("source episode has no common D3/D4 intervention frame")
    # The first frame after a prior plan is available is the clean intervention
    # boundary. Later unchanged frames may contain accumulated execution-control
    # state that is intentionally absent from the frozen offline replay.
    _, d3_frame, d4_frame = min(matches, key=lambda item: item[0])
    return d3_frame, d4_frame


def _validate_source_episode(result: EpisodeResult, *, seed: int) -> None:
    if int(result.config.seed) != int(seed):
        raise ValueError("source episode seed mismatch")
    if result.summary.get("finite_state") is not True:
        raise ValueError("source episode contains non-finite state")
    if int(result.summary.get("online_truth_use_count", -1)) != 0:
        raise ValueError("source episode violated online truth isolation")
    if result.summary.get("module_stack_enabled") is not True:
        raise ValueError("source episode did not run the integrated module stack")
    if result.config.sensor_random_schedule_version != "entity_fixed_v1":
        raise ValueError("source episode did not use the fixed sensor random stream")


def _validate_execution_boundaries(
    execution: ReservedSeedInterventionExecution,
) -> None:
    from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
        REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA,
    )

    if execution.source_nonfinite_count != 0:
        raise ValueError("reserved source set contains non-finite episodes")
    if execution.source_truth_violation_count != 0:
        raise ValueError("reserved source set contains online truth use")
    if len(execution.d3_execution.arms) != 40:
        raise ValueError("D3 execution must contain forty arms")
    if len(execution.d4_manifest.arm_evidence) != 40:
        raise ValueError("D4 execution must contain forty arms")
    if any(
        item.arm_specification.safety_shell_version != D3_SAFETY_SHELL_VERSION
        for item in execution.d3_execution.arms
    ):
        raise ValueError("D3 execution used an incompatible safety shell")
    if any(
        item.schema != REGION_RESOURCE_PAIRED_ARM_EVIDENCE_SCHEMA
        or not item.candidate_gate_diagnostics_available
        for item in execution.d4_manifest.arm_evidence
    ):
        raise ValueError("D4 execution did not emit v2 candidate gate diagnostics")
    d3_payload = execution.d3_execution.to_dict()
    admission = d3_payload["admission"]
    if any(
        (
            admission["ppo_enabled"],
            admission["online_assist_enabled"],
            admission["online_authority_enabled"],
            admission["runtime_publication_allowed"],
        )
    ):
        raise ValueError("D3 isolated execution opened online authority")
    if admission["rule_fallback_enabled"] is not True:
        raise ValueError("D3 isolated execution disabled rule fallback")
    d4_spec = execution.d4_manifest.specification
    if any((d4_spec.ppo_enabled, d4_spec.assist_enabled, d4_spec.authority_enabled)):
        raise ValueError("D4 isolated execution opened online authority")
    if d4_spec.rule_fallback_enabled is not True:
        raise ValueError("D4 isolated execution disabled rule fallback")


def _d4_execution_payload(
    execution: ReservedSeedInterventionExecution,
) -> dict[str, Any]:
    return {
        "schema_version": RESERVED_SEED_INTERVENTION_SCHEMA_VERSION,
        "execution_scope": "offline_simulation_intervention_arm",
        "manifest": execution.d4_manifest.to_dict(),
        "candidate_loader": {
            "ready": execution.d4_candidate_loader_ready,
            "load_rejection_reasons": list(
                execution.d4_candidate_load_rejection_reasons
            ),
        },
        "evidence_availability": {
            "runtime_ack": False,
            "physical_outcome": False,
            "counterfactual": False,
            "causal": False,
        },
        "admission": {
            "ppo": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
            "runtime_publication_allowed": False,
        },
    }


def _top_level_manifest(
    execution: ReservedSeedInterventionExecution,
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    d3_expected_bundle = (
        execution.d3_execution.specification.pairs[0].treatment
    )
    d3_treatment = _d3_treatment_arms(execution)
    d4_treatment = _d4_treatment_arms(execution)
    d4_gate_summary = _d4_candidate_gate_summary(d4_treatment)
    return {
        "schema_version": RESERVED_SEED_INTERVENTION_SCHEMA_VERSION,
        "experiment_scope": "reserved_seed_isolated_d3_d4_execution",
        "scenario": execution.options.scenario,
        "scale": execution.options.scale,
        "target_count": execution.sources[0].scenario_config.target_count,
        "resource_count": execution.sources[0].scenario_config.resource_count,
        "duration_s": execution.options.duration_s,
        "reserved_seeds": list(execution.options.reserved_seeds),
        "source_episode_count": len(execution.sources),
        "source_git_commits": sorted(
            {item.source_git_commit for item in execution.sources}
        ),
        "dirty_source_episode_count": sum(
            item.source_repository_dirty for item in execution.sources
        ),
        "d3_arm_count": len(execution.d3_execution.arms),
        "d4_arm_count": len(execution.d4_manifest.arm_evidence),
        "source_nonfinite_count": execution.source_nonfinite_count,
        "online_truth_use_count": execution.source_truth_violation_count,
        "artifacts_sha256": dict(sorted(artifact_hashes.items())),
        "d3_bundle": {
            "loaded": bool(execution.d3_execution.bundle_loaded),
            "expected_policy_version": d3_expected_bundle.d3_bundle_version,
            "expected_manifest_sha256": d3_expected_bundle.d3_bundle_sha256,
            "manifest_sha256": execution.d3_execution.bundle_manifest_sha256,
            "state_dict_sha256": execution.d3_execution.bundle_state_dict_sha256,
        },
        "d3_treatment_summary": {
            "safety_shell_version": d3_expected_bundle.safety_shell_version,
            "safety_shell_config_sha256": (
                d3_expected_bundle.safety_shell_config_sha256
            ),
            "applied_count": sum(item.learning_cost_applied for item in d3_treatment),
            "rule_fallback_count": sum(
                item.rule_fallback_applied for item in d3_treatment
            ),
            "fallback_reason_counts": _reason_counts(
                item.fallback_reason for item in d3_treatment
            ),
        },
        "d4_bundle": {
            **execution.d4_manifest.specification.candidate_bundle.to_dict(),
            "loaded": bool(execution.d4_candidate_loader_ready),
            "load_rejection_reasons": list(
                execution.d4_candidate_load_rejection_reasons
            ),
        },
        "d4_treatment_summary": {
            "safe_adopted_count": sum(
                item.isolated_treatment_safe_adopted for item in d4_treatment
            ),
            "rule_fallback_count": sum(item.rule_fallback_used for item in d4_treatment),
            "rejection_reason_counts": _reason_counts(
                reason
                for item in d4_treatment
                for reason in item.rejection_reasons
            ),
            "candidate_gate_summary": d4_gate_summary,
        },
        "evidence_availability": {
            "execution_receipts": True,
            "runtime_ack": False,
            "physical_outcome": False,
            "counterfactual": False,
            "causal": False,
        },
        "admission": {
            "ppo": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
        },
    }


def _render_report(execution: ReservedSeedInterventionExecution) -> str:
    d3_treatment = _d3_treatment_arms(execution)
    d4_treatment = _d4_treatment_arms(execution)
    d3_applied = sum(item.learning_cost_applied for item in d3_treatment)
    d3_fallback = sum(item.rule_fallback_applied for item in d3_treatment)
    d4_applied = sum(item.isolated_treatment_safe_adopted for item in d4_treatment)
    d4_fallback = sum(item.rule_fallback_used for item in d4_treatment)
    d3_fallback_reasons = _reason_counts(
        item.fallback_reason for item in d3_treatment
    )
    d4_rejection_reasons = _reason_counts(
        reason
        for item in d4_treatment
        for reason in item.rejection_reasons
    )
    d4_gate_summary = _d4_candidate_gate_summary(d4_treatment)
    confidence_summary = d4_gate_summary["candidate_confidence"]
    latency_summary = d4_gate_summary["candidate_latency_ms"]
    report = execution.d3_execution.paired_evaluator_report
    lines = [
        "# 保留种子隔离干预报告",
        "",
        "## 结论",
        "",
        (
            f"本次运行完成 `{len(execution.sources)}` 个保留种子源 episode，"
            f"D3 和 D4 各形成 `40` 个隔离执行臂。源 episode 有限状态异常为 "
            f"`{execution.source_nonfinite_count}`，在线真值使用为 "
            f"`{execution.source_truth_violation_count}`。"
        ),
        "",
        (
            "当前证据只确认控制臂和处理臂在同一量测、计划、区域快照、通信与故障"
            "日程上执行。运行时确认、后续物理结果、反事实和因果收益均未生成。"
        ),
        "",
        "## 输入",
        "",
        f"- 场景：`{execution.options.scenario}`。",
        (
            f"- 规模：资源 `{execution.sources[0].scenario_config.resource_count}`，"
            f"目标 `{execution.sources[0].scenario_config.target_count}`。"
        ),
        f"- 时长：每个源 episode `{execution.options.duration_s:.3f}` 秒。",
        "- 随机种子：`1000-1019`。",
        f"- 帧选择：`{INTERVENTION_SELECTION_POLICY}`。",
        "",
        "## D3 分配干预",
        "",
        f"- 安全外壳：`{D3_SAFETY_SHELL_VERSION}`。",
        f"- 处理臂实际应用学习代价修正：`{d3_applied}/20`。",
        f"- 处理臂规则回退：`{d3_fallback}/20`。",
        f"- 回退原因：{_format_reason_counts(d3_fallback_reasons)}。",
        (
            f"- 规则平均分配代价：`{report.rule_assignment_cost_mean:.6f}`；"
            f"处理臂平均分配代价：`{report.shadow_assignment_cost_mean:.6f}`。"
        ),
        (
            f"- 规则/处理臂高威胁未满足总数："
            f"`{report.rule_high_threat_unmet_total}/"
            f"{report.shadow_high_threat_unmet_total}`。"
        ),
        "",
        "## D4 区域干预",
        "",
        (
            f"- 冻结候选加载状态："
            f"`{'ready' if execution.d4_candidate_loader_ready else 'rule_fallback'}`。"
        ),
        f"- 处理臂通过隔离安全投影：`{d4_applied}/20`。",
        f"- 处理臂规则回退：`{d4_fallback}/20`。",
        f"- 拒绝原因：{_format_reason_counts(d4_rejection_reasons)}。",
        (
            "- 候选门诊断：已考虑 "
            f"`{d4_gate_summary['candidate_considered_count']}/20`，"
            f"置信度通过 `{d4_gate_summary['confidence_gate_passed_count']}`，"
            f"分布外门通过 `{d4_gate_summary['ood_gate_passed_count']}`，"
            f"时延门通过 `{d4_gate_summary['latency_gate_passed_count']}`，"
            f"有限值门通过 `{d4_gate_summary['finite_gate_passed_count']}`。"
        ),
        (
            "- 候选置信度 min/mean/max："
            f"`{_format_optional_triplet(confidence_summary)}`；"
            "候选时延 mean/P95/max："
            f"`{_format_optional_latency(latency_summary)}` ms。"
        ),
        "",
        "## 权限边界",
        "",
        "`PPO=false`，`assist=false`，`authority=false`，`rule_fallback=true`。",
        "",
        (
            "任何隔离计划和区域建议均不可发布到在线总线，也不能授权 D7。D6 只有在"
            "取得后续状态窗口和严格绑定的实际采用证据后，才能另行生成结果 sidecar。"
        ),
        "",
    ]
    return "\n".join(lines)


def _d3_treatment_arms(
    execution: ReservedSeedInterventionExecution,
) -> tuple[Any, ...]:
    return tuple(
        item
        for item in execution.d3_execution.arms
        if item.arm_specification.arm_kind == "treatment"
    )


def _d4_treatment_arms(
    execution: ReservedSeedInterventionExecution,
) -> tuple[Any, ...]:
    return tuple(
        item
        for item in execution.d4_manifest.arm_evidence
        if item.arm.value == "treatment_candidate"
    )


def _d4_candidate_gate_summary(
    treatment_arms: Sequence[Any],
) -> dict[str, Any]:
    diagnostics = tuple(
        item
        for item in treatment_arms
        if item.candidate_gate_diagnostics_available
    )
    considered = tuple(item for item in diagnostics if item.candidate_considered)
    confidences = tuple(
        float(item.candidate_confidence)
        for item in considered
        if item.candidate_confidence is not None
    )
    latencies = tuple(float(item.candidate_latency_ms) for item in considered)
    minimum_confidences = sorted(
        {
            float(item.minimum_confidence)
            for item in diagnostics
            if item.minimum_confidence is not None
        }
    )
    latency_limits = sorted(
        {
            float(item.candidate_latency_limit_ms)
            for item in diagnostics
            if item.candidate_latency_limit_ms is not None
        }
    )
    return {
        "arm_evidence_schema_versions": sorted(
            {str(item.schema) for item in treatment_arms}
        ),
        "diagnostics_available_count": len(diagnostics),
        "candidate_considered_count": len(considered),
        "minimum_confidence_values": minimum_confidences,
        "candidate_latency_limit_ms_values": latency_limits,
        "aggregate_gate_passed_count": sum(
            item.candidate_thresholds_passed is True for item in considered
        ),
        "confidence_gate_passed_count": sum(
            item.candidate_confidence_gate_passed is True for item in considered
        ),
        "ood_gate_passed_count": sum(
            item.candidate_ood_gate_passed is True for item in considered
        ),
        "latency_gate_passed_count": sum(
            item.candidate_latency_gate_passed is True for item in considered
        ),
        "finite_gate_passed_count": sum(
            item.candidate_finite_gate_passed is True for item in considered
        ),
        "failure_gate_passed_count": sum(
            item.candidate_failure_gate_passed is True for item in considered
        ),
        "candidate_confidence": _numeric_summary(confidences),
        "candidate_latency_ms": _numeric_summary(latencies),
    }


def _numeric_summary(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "sample_count": 0,
            "minimum": None,
            "mean": None,
            "p95": None,
            "maximum": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "sample_count": int(array.size),
        "minimum": float(np.min(array)),
        "mean": float(np.mean(array)),
        "p95": float(np.percentile(array, 95.0)),
        "maximum": float(np.max(array)),
    }


def _format_optional_triplet(summary: Mapping[str, Any]) -> str:
    if int(summary["sample_count"]) == 0:
        return "unavailable"
    return "/".join(
        f"{float(summary[name]):.6f}"
        for name in ("minimum", "mean", "maximum")
    )


def _format_optional_latency(summary: Mapping[str, Any]) -> str:
    if int(summary["sample_count"]) == 0:
        return "unavailable"
    return "/".join(
        f"{float(summary[name]):.3f}"
        for name in ("mean", "p95", "maximum")
    )


def _reason_counts(values: Iterable[str | None]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(value).strip()
                for value in values
                if value is not None and str(value).strip()
            ).items()
        )
    )


def _format_reason_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "无"
    return "、".join(f"`{reason}` {count} 次" for reason, count in counts.items())


def _d3_input_snapshot_sha256(frame: Any) -> str:
    from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
        canonical_planning_frame_snapshot_sha256,
    )

    return canonical_planning_frame_snapshot_sha256(frame)


def _initial_state_sha256(result: EpisodeResult) -> str:
    digest = sha256()
    digest.update(b"scalable3d-initial-world-state-v1\0")
    for name, array in (
        ("intruders", result.intruder_state_history[0]),
        ("interceptors", result.interceptor_state_history[0]),
        ("recon", result.recon_state_history[0]),
        ("intruder_active", result.intruder_active_history[0]),
    ):
        contiguous = np.ascontiguousarray(array)
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(contiguous.dtype.str.encode("ascii"))
        digest.update(b"\0")
        digest.update(_canonical_json(list(contiguous.shape)).encode("ascii"))
        digest.update(b"\0")
        digest.update(contiguous.tobytes(order="C"))
    return digest.hexdigest()


def _communication_schedule_sha256(config: Any) -> str:
    return _canonical_sha256(
        {
            "seed": int(config.seed),
            "enabled": bool(config.communication_enabled),
            "latency_s": float(config.communication_latency_s),
            "jitter_s": float(config.communication_jitter_s),
            "drop_probability": float(config.communication_drop_probability),
            "bandwidth_bytes_per_s": float(
                config.communication_bandwidth_bytes_per_s
            ),
            "sensor_random_schedule_version": config.sensor_random_schedule_version,
        }
    )


def _fault_schedule_sha256(config: Any) -> str:
    return _canonical_sha256(
        {
            "seed": int(config.seed),
            "fault_schedule": config.metadata.get("fault_schedule", ()),
            "center_failure": bool(
                config.metadata.get("fault_schedule_runtime_required", False)
            ),
        }
    )


def _dataclass_payload(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return jsonable(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        jsonable(value),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_sha256(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            jsonable(payload),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: str, name: str) -> None:
    if len(str(value)) != 64:
        raise ValueError(f"{name} must be a SHA-256 hex digest")
    try:
        int(str(value), 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a SHA-256 hex digest") from exc
