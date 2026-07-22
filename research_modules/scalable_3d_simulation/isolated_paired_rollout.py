"""Isolated multi-cycle control/treatment rollouts for scalable 3D research.

The runner deliberately keeps both arms outside production authority.  It
starts each arm from the same deterministic scenario seed and exogenous
schedule, but gives each arm its own world, module stack, episode bus, and
output directory.  D3's development bundle may affect only the treatment arm.

This module records evidence; it does not promote a model, publish a plan to a
real runtime, or claim counterfactual/causal effects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping, Sequence
import uuid

import numpy as np

from .episode_bus import VersionedEnvelope, jsonable
from .module_stack import IntegratedScalableModuleStack, IntegratedStackConfig
from .orchestrator import EpisodeResult, Scalable3DEpisodeRunner
from .reporting import write_episode_outputs
from .reserved_seed_interventions import D3DevelopmentBundleBinding
from .scenarios import make_curriculum_scenario


ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION = "scalable3d-isolated-paired-rollout-v1"
ISOLATED_ARM_SCOPE = "isolated_simulation_only"
CONTROL_ARM = "control"
TREATMENT_ARM = "treatment"
_ARM_KINDS = frozenset({CONTROL_ARM, TREATMENT_ARM})


@dataclass(frozen=True, slots=True)
class IsolatedPairedRolloutOptions:
    """Shared scenario controls for an isolated paired experiment."""

    scenario: str = "nominal"
    scale: int = 5
    target_count: int | None = None
    resource_count: int | None = None
    duration_s: float = 6.0
    seeds: tuple[int, ...] = (1000,)
    created_at_utc: str = "2026-07-22T00:00:00Z"

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
        seeds = tuple(int(seed) for seed in self.seeds)
        if not seeds or len(set(seeds)) != len(seeds):
            raise ValueError("seeds must be non-empty and unique")
        object.__setattr__(self, "seeds", seeds)
        if not str(self.created_at_utc).strip():
            raise ValueError("created_at_utc must be non-empty")


@dataclass(frozen=True, slots=True)
class IsolatedArmEvidence:
    """Truth-free online lineage plus evaluator-only outcome availability."""

    seed: int
    arm_kind: str
    experiment_arm_id: str
    result: EpisodeResult
    initial_state_sha256: str
    exogenous_schedule_sha256: str
    plan_publication_sha256: tuple[str, ...]
    guidance_publication_sha256: tuple[str, ...]
    plan_ack_sha256: tuple[str, ...]
    plan_versions: tuple[int, ...]
    learning_applied_cycle_count: int
    learning_fallback_cycle_count: int

    def __post_init__(self) -> None:
        if self.arm_kind not in _ARM_KINDS:
            raise ValueError("unsupported arm kind")
        if not self.experiment_arm_id:
            raise ValueError("experiment_arm_id must be non-empty")
        for value in (
            self.initial_state_sha256,
            self.exogenous_schedule_sha256,
            *self.plan_publication_sha256,
            *self.guidance_publication_sha256,
            *self.plan_ack_sha256,
        ):
            _require_sha256(str(value), "evidence SHA256")
        if any(version <= 0 for version in self.plan_versions):
            raise ValueError("plan versions must be positive")
        if self.learning_applied_cycle_count < 0:
            raise ValueError("learning_applied_cycle_count must be nonnegative")
        if self.learning_fallback_cycle_count < 0:
            raise ValueError("learning_fallback_cycle_count must be nonnegative")

    def summary_payload(self) -> dict[str, Any]:
        return {
            "schema_version": ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION,
            "scope": ISOLATED_ARM_SCOPE,
            "seed": int(self.seed),
            "arm_kind": self.arm_kind,
            "experiment_arm_id": self.experiment_arm_id,
            "episode_id": self.result.manifest.episode_id,
            "initial_state_sha256": self.initial_state_sha256,
            "exogenous_schedule_sha256": self.exogenous_schedule_sha256,
            "plan_publication_sha256": list(self.plan_publication_sha256),
            "guidance_publication_sha256": list(
                self.guidance_publication_sha256
            ),
            "plan_ack_sha256": list(self.plan_ack_sha256),
            "plan_versions": list(self.plan_versions),
            "learning_applied_cycle_count": self.learning_applied_cycle_count,
            "learning_fallback_cycle_count": self.learning_fallback_cycle_count,
            "assignment_plan_ack_count": int(
                self.result.summary.get("assignment_plan_ack_count", 0)
            ),
            "control_applied_binding_count": int(
                self.result.summary.get(
                    "assignment_plan_control_applied_count",
                    0,
                )
            ),
            "physical_intercept_count": int(
                self.result.summary.get("intercepted_target_count", 0)
            ),
            "finite_state": bool(self.result.summary.get("finite_state", False)),
            "online_truth_use_count": int(
                self.result.summary.get("online_truth_use_count", 0)
            ),
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
            "ppo_allowed": False,
            "assist_allowed": False,
            "authority_allowed": False,
            "rule_fallback_required": True,
        }


@dataclass(frozen=True, slots=True)
class IsolatedSeedPairEvidence:
    """Two independently executed arms sharing one exogenous experiment seed."""

    pair_id: str
    seed: int
    control: IsolatedArmEvidence
    treatment: IsolatedArmEvidence
    same_initial_state: bool
    same_exogenous_schedule: bool
    worlds_isolated: bool
    buses_isolated: bool

    def __post_init__(self) -> None:
        if self.control.seed != self.seed or self.treatment.seed != self.seed:
            raise ValueError("pair seed does not match arm seed")
        if self.control.arm_kind != CONTROL_ARM:
            raise ValueError("control arm kind mismatch")
        if self.treatment.arm_kind != TREATMENT_ARM:
            raise ValueError("treatment arm kind mismatch")
        if not self.same_initial_state or not self.same_exogenous_schedule:
            raise ValueError("paired arms must share initial state and exogenous schedule")
        if not self.worlds_isolated or not self.buses_isolated:
            raise ValueError("paired arms must use isolated worlds and buses")

    @property
    def final_binding_changed(self) -> bool:
        return _final_binding_signature(self.control.result) != _final_binding_signature(
            self.treatment.result
        )

    @property
    def common_plan_cycle_count(self) -> int:
        control = _binding_signatures_by_timestamp(self.control.result)
        treatment = _binding_signatures_by_timestamp(self.treatment.result)
        return len(set(control) & set(treatment))

    @property
    def unpaired_plan_cycle_count(self) -> int:
        control = _binding_signatures_by_timestamp(self.control.result)
        treatment = _binding_signatures_by_timestamp(self.treatment.result)
        return len(set(control) ^ set(treatment))

    @property
    def binding_changed_cycle_count(self) -> int:
        control = _binding_signatures_by_timestamp(self.control.result)
        treatment = _binding_signatures_by_timestamp(self.treatment.result)
        return sum(
            control[timestamp] != treatment[timestamp]
            for timestamp in sorted(set(control) & set(treatment))
        )

    def summary_payload(self) -> dict[str, Any]:
        return {
            "schema_version": ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION,
            "pair_id": self.pair_id,
            "seed": int(self.seed),
            "same_initial_state": self.same_initial_state,
            "same_exogenous_schedule": self.same_exogenous_schedule,
            "worlds_isolated": self.worlds_isolated,
            "buses_isolated": self.buses_isolated,
            "common_plan_cycle_count": self.common_plan_cycle_count,
            "unpaired_plan_cycle_count": self.unpaired_plan_cycle_count,
            "binding_changed_cycle_count": self.binding_changed_cycle_count,
            "final_binding_changed": self.final_binding_changed,
            "control": self.control.summary_payload(),
            "treatment": self.treatment.summary_payload(),
            "paired_physical_effect_available": False,
            "paired_non_degradation_available": False,
            "counterfactual_available": False,
            "causal_available": False,
            "availability_reason": (
                "D6 paired physical-outcome audit has not been attached"
            ),
        }


@dataclass(frozen=True, slots=True)
class IsolatedPairedRolloutExecution:
    options: IsolatedPairedRolloutOptions
    pairs: tuple[IsolatedSeedPairEvidence, ...]
    d3_bundle_manifest_sha256: str
    d3_policy_version: str
    d3_bundle_loaded: bool
    d3_bundle_fallback_reason: str | None

    def __post_init__(self) -> None:
        if tuple(pair.seed for pair in self.pairs) != self.options.seeds:
            raise ValueError("pair inventory does not match requested seeds")
        _require_sha256(
            self.d3_bundle_manifest_sha256,
            "d3_bundle_manifest_sha256",
        )
        if not self.d3_policy_version:
            raise ValueError("d3_policy_version must be non-empty")


def execute_isolated_paired_rollouts(
    options: IsolatedPairedRolloutOptions,
    *,
    d3_bundle: D3DevelopmentBundleBinding,
) -> IsolatedPairedRolloutExecution:
    """Run each seed twice with independent state and no production authority."""

    # D3 owns the guarded development-bundle loader.  This private import is a
    # temporary compatibility bridge until the module exposes its public
    # isolated-experiment loader; no D3 algorithm is reimplemented here.
    from research_modules.d3_assignment_planner.src.d3_assignment_planner.offline_intervention_execution import (
        _load_offline_development_bundle,
    )

    loaded = _load_offline_development_bundle(
        d3_bundle.bundle_dir,
        expected_manifest_sha256=d3_bundle.manifest_sha256,
        expected_policy_version=d3_bundle.policy_version,
        reserved_seeds=options.seeds,
    )
    pairs: list[IsolatedSeedPairEvidence] = []
    for seed in options.seeds:
        base = make_curriculum_scenario(
            options.scenario,
            scale=options.scale,
            seed=seed,
            duration_s=options.duration_s,
            target_count=options.target_count,
            resource_count=options.resource_count,
        )
        base = replace(base, sensor_random_schedule_version="entity_fixed_v1")
        exogenous_sha = _exogenous_schedule_sha256(base)
        pair_id = f"paired-{options.scenario}-{seed}"
        control = _run_arm(
            base,
            pair_id=pair_id,
            arm_kind=CONTROL_ARM,
            d3_learning_assistant=None,
            exogenous_schedule_sha256=exogenous_sha,
        )
        treatment = _run_arm(
            base,
            pair_id=pair_id,
            arm_kind=TREATMENT_ARM,
            d3_learning_assistant=loaded.assistant,
            exogenous_schedule_sha256=exogenous_sha,
        )
        same_initial = control.initial_state_sha256 == treatment.initial_state_sha256
        same_exogenous = (
            control.exogenous_schedule_sha256
            == treatment.exogenous_schedule_sha256
            == exogenous_sha
        )
        pairs.append(
            IsolatedSeedPairEvidence(
                pair_id=pair_id,
                seed=seed,
                control=control,
                treatment=treatment,
                same_initial_state=same_initial,
                same_exogenous_schedule=same_exogenous,
                worlds_isolated=(control.result is not treatment.result),
                # Each _run_arm call constructs a new episode runner and bus.
                # Empty message tuples may share Python's singleton object, so
                # tuple identity is not a valid isolation check.
                buses_isolated=True,
            )
        )
    return IsolatedPairedRolloutExecution(
        options=options,
        pairs=tuple(pairs),
        d3_bundle_manifest_sha256=d3_bundle.manifest_sha256,
        d3_policy_version=d3_bundle.policy_version,
        d3_bundle_loaded=bool(loaded.loaded),
        d3_bundle_fallback_reason=loaded.fallback_reason,
    )


def write_isolated_paired_rollout_execution(
    output_dir: str | Path,
    execution: IsolatedPairedRolloutExecution,
) -> dict[str, Path]:
    """Atomically publish arm episodes, lineage, hashes, and a Chinese report."""

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"paired rollout output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir(parents=False)
    try:
        pair_rows: list[dict[str, Any]] = []
        for pair in execution.pairs:
            pair_dir = temporary / f"seed_{pair.seed}"
            for arm in (pair.control, pair.treatment):
                arm_dir = pair_dir / arm.arm_kind
                episode_paths = write_episode_outputs(arm.result, arm_dir)
                summary = arm.summary_payload()
                summary["artifact_sha256"] = {
                    name: _file_sha256(path)
                    for name, path in sorted(episode_paths.items())
                    if Path(path).is_file()
                }
                _write_json(arm_dir / "isolated_arm_evidence.json", summary)
            row = pair.summary_payload()
            _write_json(pair_dir / "paired_seed_evidence.json", row)
            pair_rows.append(row)

        manifest = _execution_manifest(execution, pair_rows)
        _write_json(temporary / "manifest.json", manifest)
        _write_jsonl(temporary / "paired_seed_evidence.jsonl", pair_rows)
        (temporary / "ISOLATED_PAIRED_ROLLOUT_REPORT_CN.md").write_text(
            _render_report(execution),
            encoding="utf-8",
        )
        hashes = {
            str(path.relative_to(temporary)): _file_sha256(path)
            for path in sorted(temporary.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS"
        }
        (temporary / "SHA256SUMS").write_text(
            "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
            encoding="utf-8",
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "manifest": output / "manifest.json",
        "paired_seed_evidence": output / "paired_seed_evidence.jsonl",
        "report_cn": output / "ISOLATED_PAIRED_ROLLOUT_REPORT_CN.md",
        "sha256sums": output / "SHA256SUMS",
    }


def _run_arm(
    base_config: Any,
    *,
    pair_id: str,
    arm_kind: str,
    d3_learning_assistant: Any | None,
    exogenous_schedule_sha256: str,
) -> IsolatedArmEvidence:
    metadata = {
        **dict(base_config.metadata),
        "isolated_paired_rollout": {
            "schema_version": ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION,
            "pair_id": pair_id,
            "arm_kind": arm_kind,
            "isolated_simulation_only": True,
            "production_runtime_ack": False,
            "online_assist_enabled": False,
            "online_authority_enabled": False,
        },
    }
    config = replace(
        base_config,
        scenario_name=f"{base_config.scenario_name}_{arm_kind}",
        scenario_version=(
            f"{base_config.scenario_version}-isolated-paired-v1-{arm_kind}"
        ),
        metadata=metadata,
    )
    stack = IntegratedScalableModuleStack(
        config=IntegratedStackConfig(capture_learning_artifacts=True),
        d3_learning_assistant=d3_learning_assistant,
    )
    runner = Scalable3DEpisodeRunner(config, module_stack=stack)
    result = runner.run()
    initial_sha = _initial_state_sha256(result)
    plans = _topic_messages(result.online_messages, "modules.d3.assignment_plan")
    guidance = _topic_messages(result.online_messages, "modules.d7.guidance_commands")
    acknowledgements = _topic_messages(
        result.online_messages,
        "runtime.assignment_plan_ack",
    )
    plan_versions = tuple(
        int(_mapping(message.payload, "D3 plan publication")["plan_version"])
        for message in plans
    )
    applied, fallback = _learning_cycle_counts(stack.learning_artifacts().d3_planning_frames)
    if int(result.summary.get("online_truth_use_count", -1)) != 0:
        raise ValueError("isolated arm used evaluator truth online")
    if not bool(result.summary.get("finite_state", False)):
        raise FloatingPointError("isolated arm produced a non-finite world state")
    return IsolatedArmEvidence(
        seed=int(config.seed),
        arm_kind=arm_kind,
        experiment_arm_id=f"{pair_id}-{arm_kind}",
        result=result,
        initial_state_sha256=initial_sha,
        exogenous_schedule_sha256=exogenous_schedule_sha256,
        plan_publication_sha256=tuple(_envelope_payload_sha256(item) for item in plans),
        guidance_publication_sha256=tuple(
            _envelope_payload_sha256(item) for item in guidance
        ),
        plan_ack_sha256=tuple(
            _envelope_payload_sha256(item) for item in acknowledgements
        ),
        plan_versions=plan_versions,
        learning_applied_cycle_count=applied,
        learning_fallback_cycle_count=fallback,
    )


def _execution_manifest(
    execution: IsolatedPairedRolloutExecution,
    pair_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION,
        "created_at_utc": execution.options.created_at_utc,
        "scenario": execution.options.scenario,
        "scale": execution.options.scale,
        "target_count": execution.pairs[0].control.result.config.target_count,
        "resource_count": execution.pairs[0].control.result.config.resource_count,
        "duration_s": execution.options.duration_s,
        "seeds": list(execution.options.seeds),
        "pair_count": len(execution.pairs),
        "d3_bundle": {
            "manifest_sha256": execution.d3_bundle_manifest_sha256,
            "policy_version": execution.d3_policy_version,
            "loaded": execution.d3_bundle_loaded,
            "fallback_reason": execution.d3_bundle_fallback_reason,
        },
        "pair_summary_sha256": _canonical_sha256(pair_rows),
        "same_initial_state_count": sum(
            pair.same_initial_state for pair in execution.pairs
        ),
        "same_exogenous_schedule_count": sum(
            pair.same_exogenous_schedule for pair in execution.pairs
        ),
        "treatment_learning_applied_seed_count": sum(
            pair.treatment.learning_applied_cycle_count > 0
            for pair in execution.pairs
        ),
        "final_binding_changed_seed_count": sum(
            pair.final_binding_changed for pair in execution.pairs
        ),
        "binding_changed_cycle_count": sum(
            pair.binding_changed_cycle_count for pair in execution.pairs
        ),
        "unpaired_plan_cycle_count": sum(
            pair.unpaired_plan_cycle_count for pair in execution.pairs
        ),
        "evidence_availability": {
            "isolated_episode_execution": True,
            "raw_plan_execution_ack": True,
            "d3_isolated_plan_consumption_validated": False,
            "guidance_lineage_raw": True,
            "d7_guidance_lineage_validated": False,
            "physical_state_window": True,
            "d6_paired_physical_effect": False,
            "paired_non_degradation": False,
            "production_runtime_ack": False,
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


def _render_report(execution: IsolatedPairedRolloutExecution) -> str:
    pair_count = len(execution.pairs)
    applied = sum(
        pair.treatment.learning_applied_cycle_count > 0 for pair in execution.pairs
    )
    binding_changed = sum(pair.final_binding_changed for pair in execution.pairs)
    changed_cycles = sum(
        pair.binding_changed_cycle_count for pair in execution.pairs
    )
    common_cycles = sum(pair.common_plan_cycle_count for pair in execution.pairs)
    control_intercepts = sum(
        int(pair.control.result.summary.get("intercepted_target_count", 0))
        for pair in execution.pairs
    )
    treatment_intercepts = sum(
        int(pair.treatment.result.summary.get("intercepted_target_count", 0))
        for pair in execution.pairs
    )
    return f"""# 隔离双臂多周期仿真记录

## 结论

本批完成 {pair_count} 组同随机种子双臂仿真。两个臂使用相同初始状态和外生随机日程，世界、模块栈和总线彼此隔离。开发模型在 {applied}/{pair_count} 组处理臂中至少通过一次 D3 安全门。共有 {changed_cycles}/{common_cycles} 个共同规划周期的分配绑定不同，最终分配绑定在 {binding_changed}/{pair_count} 组发生变化。

规则臂累计产生 {control_intercepts} 次五米内物理接近事件，处理臂累计产生 {treatment_intercepts} 次。本文件只记录原始执行事实。D6 尚未完成带哈希的成对物理结果复核，因此成对效果、非退化、反事实和因果结论均不可用。

## 证据边界

- 每个臂都保留计划发布、D7 导引发布、仿真运行确认和离线物理状态。
- 仿真确认的作用域是 `{ISOLATED_ARM_SCOPE}`，`production_runtime_ack=false`。
- 在线真值使用次数要求为零；真值轨迹只写入离线评估文件。
- 近端策略优化、在线辅助和生产控制权限均未开放，规则回退继续有效。
"""


def _topic_messages(
    messages: Iterable[VersionedEnvelope],
    topic: str,
) -> tuple[VersionedEnvelope, ...]:
    return tuple(message for message in messages if message.topic == topic)


def _learning_cycle_counts(frames: Iterable[Any]) -> tuple[int, int]:
    applied = 0
    fallback = 0
    for frame in frames:
        effective = getattr(frame, "effective_matrix_result", None)
        if effective is None:
            continue
        metadata = dict(getattr(effective, "metadata", {}) or {})
        if bool(metadata.get("learning_applied", False)):
            applied += 1
        elif str(metadata.get("learning_mode", "")) == "assist":
            fallback += 1
    return applied, fallback


def _final_binding_signature(result: EpisodeResult) -> tuple[tuple[str, str], ...]:
    messages = _topic_messages(result.online_messages, "modules.d3.assignment_plan")
    if not messages:
        return ()
    payload = _mapping(messages[-1].payload, "D3 plan publication")
    assignments = payload.get("assignments", ())
    if not isinstance(assignments, (tuple, list)):
        raise TypeError("D3 assignments must be a sequence")
    return tuple(
        sorted(
            (
                str(_mapping(item, "D3 assignment").get("resource_id", "")),
                str(_mapping(item, "D3 assignment").get("global_track_id", "")),
            )
            for item in assignments
        )
    )


def _binding_signatures_by_timestamp(
    result: EpisodeResult,
) -> dict[float, tuple[tuple[str, str], ...]]:
    signatures: dict[float, tuple[tuple[str, str], ...]] = {}
    for message in _topic_messages(
        result.online_messages,
        "modules.d3.assignment_plan",
    ):
        payload = _mapping(message.payload, "D3 plan publication")
        assignments = payload.get("assignments", ())
        if not isinstance(assignments, (tuple, list)):
            raise TypeError("D3 assignments must be a sequence")
        timestamp = round(float(message.timestamp), 12)
        if timestamp in signatures:
            raise ValueError("one arm published multiple D3 plans at one timestamp")
        signatures[timestamp] = tuple(
            sorted(
                (
                    str(
                        _mapping(item, "D3 assignment").get(
                            "resource_id",
                            "",
                        )
                    ),
                    str(
                        _mapping(item, "D3 assignment").get(
                            "global_track_id",
                            "",
                        )
                    ),
                )
                for item in assignments
            )
        )
    return signatures


def _initial_state_sha256(result: EpisodeResult) -> str:
    payload = {
        "intruders": result.intruder_state_history[0].astype(float).tolist(),
        "interceptors": result.interceptor_state_history[0].astype(float).tolist(),
        "recon": result.recon_state_history[0].astype(float).tolist(),
        "intruder_active": result.intruder_active_history[0].astype(bool).tolist(),
    }
    return _canonical_sha256(payload)


def _exogenous_schedule_sha256(config: Any) -> str:
    payload = {
        "seed": int(config.seed),
        "physics_dt_s": float(config.physics_dt_s),
        "motion_profile": str(config.motion_profile.value),
        "sensor_random_schedule_version": config.sensor_random_schedule_version,
        "sensor_periods": {
            "radar": float(config.radar_period_s),
            "acoustic": float(config.acoustic_period_s),
            "visual": float(config.visual_period_s),
        },
        "sensor_probabilities": {
            "radar_detection": float(config.radar_detection_probability),
            "acoustic_detection": float(config.acoustic_detection_probability),
            "visual_detection": float(config.visual_detection_probability),
            "visual_false_alarm": float(config.visual_false_alarm_rate),
        },
        "sensor_noise": {
            "radar_range_std_base_m": float(config.radar_range_std_base_m),
            "radar_range_std_per_km_m": float(
                config.radar_range_std_per_km_m
            ),
            "radar_angle_std_deg": float(config.radar_angle_std_deg),
            "acoustic_angle_std_deg": float(config.acoustic_angle_std_deg),
        },
        "communication": {
            "enabled": bool(config.communication_enabled),
            "latency_s": float(config.communication_latency_s),
            "jitter_s": float(config.communication_jitter_s),
            "drop_probability": float(config.communication_drop_probability),
            "bandwidth_bytes_per_s": float(
                config.communication_bandwidth_bytes_per_s
            ),
        },
        "fault_schedule": config.metadata.get("fault_schedule", ()),
    }
    return _canonical_sha256(payload)


def _envelope_payload_sha256(message: VersionedEnvelope) -> str:
    return _canonical_sha256(
        {
            "sequence": int(message.sequence),
            "topic": message.topic,
            "source": message.source,
            "timestamp": float(message.timestamp),
            "schema_version": message.schema_version,
            "payload": jsonable(message.payload),
        }
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            jsonable(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(
                json.dumps(
                    jsonable(row),
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
            )
            stream.write("\n")
    return path


def _require_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA256")


__all__ = [
    "CONTROL_ARM",
    "ISOLATED_ARM_SCOPE",
    "ISOLATED_PAIRED_ROLLOUT_SCHEMA_VERSION",
    "TREATMENT_ARM",
    "IsolatedArmEvidence",
    "IsolatedPairedRolloutExecution",
    "IsolatedPairedRolloutOptions",
    "IsolatedSeedPairEvidence",
    "execute_isolated_paired_rollouts",
    "write_isolated_paired_rollout_execution",
]
