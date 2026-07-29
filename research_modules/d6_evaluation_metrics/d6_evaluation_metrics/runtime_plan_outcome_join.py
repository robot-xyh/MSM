"""Strict offline join from runtime assignment ACKs to observed outcomes.

The evaluator keeps online execution evidence, evaluator-only identity mapping,
and truth-bearing physical state in separate inputs.  It verifies every source
by an externally supplied SHA-256 before joining them.  The resulting bounded
pair-progress value is a diagnostic only; it is never exposed as a D3 PPO
reward or as causal/counterfactual evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .observation_truth_sidecar import (
    D2_OBSERVATION_TRUTH_SCHEMA_V2,
    ObservationTruthSidecarError,
    TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
    TRUTH_DISPOSITION_TARGET,
    TRUTH_DISPOSITION_UNKNOWN,
    audit_observation_truth_sidecar,
)
from .truth_isolated_offline import (
    D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1,
    D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2,
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1,
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2,
    D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V1,
    D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V2,
    TruthIsolatedEvaluationError,
    adapt_d2_identity_recovery_config_provenance,
    validate_d2_identity_commitment_evaluation,
)


RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION = (
    "d6.runtime-plan-outcome-join-inputs.v1"
)
RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_VERSION = "d6.runtime-plan-outcome-join.v2"
RUNTIME_PLAN_OUTCOME_JOIN_DATE = "2026-07-23"
RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME = (
    "bounded_assigned_pair_best_distance_progress_v1"
)

ASSIGNMENT_PLAN_TOPIC = "modules.d3.assignment_plan"
GUIDANCE_COMMAND_TOPIC = "modules.d7.guidance_commands"
ASSIGNMENT_PLAN_ACK_TOPIC = "runtime.assignment_plan_ack"
ASSIGNMENT_PLAN_ACK_SCHEMA = "scalable3d-assignment-plan-runtime-ack-v1"
D3_PLAN_SCHEMA = "assignment_plan_v2"
D7_GUIDANCE_SCHEMA = "d7-scalable3d-guidance-v1"
D2_IDENTITY_MANIFEST_SCHEMA_V1 = (
    D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V1
)
D2_IDENTITY_MANIFEST_SCHEMA_V2 = (
    D2_OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2
)
D2_IDENTITY_MANIFEST_SCHEMAS = frozenset(
    {D2_IDENTITY_MANIFEST_SCHEMA_V1, D2_IDENTITY_MANIFEST_SCHEMA_V2}
)
D2_IDENTITY_EVALUATION_SCHEMA = (
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V1
)
D2_IDENTITY_EVALUATION_SCHEMA_V2 = (
    D2_SCALABLE_3D_IDENTITY_EVALUATION_SCHEMA_VERSION_V2
)
D2_IDENTITY_POLICY = D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V1
D2_IDENTITY_POLICY_V2 = D2_SCALABLE_3D_IDENTITY_POLICY_VERSION_V2
_D2_IDENTITY_POLICY_BY_SCHEMA = {
    D2_IDENTITY_EVALUATION_SCHEMA: D2_IDENTITY_POLICY,
    D2_IDENTITY_EVALUATION_SCHEMA_V2: D2_IDENTITY_POLICY_V2,
}
D2_EVALUATOR_ONLY_BOUNDED_COAST_BRIDGE_POLICY = (
    "offline_confirmed_unmatched_double_anchor_v1"
)
D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S = 0.9
EPISODE_BUS_SCHEMA = "scalable3d-episode-bus-v1"
SCENARIO_SCHEMA = "scalable3d-scenario-v1"
WORLD_SCHEMA = "scalable3d-world-v1"
FIVE_METER_THRESHOLD_M = 5.0

_SHA256_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_RESOURCE_ID_RE = re.compile(r"^INT-([0-9]{4})$")
_INPUT_NAMES = (
    "online_observations",
    "d2_identity_evaluation",
    "d2_identity_manifest",
    "d2_online_d1_records",
    "d2_online_d2_records",
    "d2_observation_truth_labels",
    "d2_identity_evidence",
    "offline_truth_state",
    "offline_proximity_intercepts",
    "episode_manifest",
    "scenario_config",
)
_ACK_KEYS = frozenset(
    {
        "decision_id",
        "ack_timestamp",
        "plan_id",
        "plan_version",
        "plan_created_at",
        "plan_schema_version",
        "source_plan_bus_sequence",
        "source_plan_payload_sha256",
        "source_guidance_bus_sequence",
        "source_guidance_payload_sha256",
        "accepted",
        "status_code",
        "assignment_count",
        "binding_ack_count",
        "fully_bound_to_guidance",
        "control_applied_binding_count",
        "held_binding_count",
        "active_plan_owner",
        "owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
        "d3_learning_evidence",
        "d4_regional_hint_evidence",
        "binding_acks",
        "physical_outcome_available",
        "reward_available",
    }
)
_BINDING_ACK_KEYS = frozenset(
    {
        "resource_id",
        "global_track_id",
        "coalition_id",
        "coalition_version",
        "member_role",
        "guidance_command_present",
        "guidance_mode",
        "guidance_gate_reason",
        "control_applied_to_world",
        "held",
    }
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_ids",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_position",
        "truth_velocity",
        "ground_truth",
        "ground_truth_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "airsim_id",
        "offline_truth_labels",
    }
)
_D2_FILTERED_SOURCE_TOPICS = frozenset(
    {
        "modules.d1.fused_tracks",
        "modules.d2.associated_tracks",
    }
)
_RETAINED_ONLINE_TOPICS = frozenset(
    {
        *_D2_FILTERED_SOURCE_TOPICS,
        ASSIGNMENT_PLAN_TOPIC,
        GUIDANCE_COMMAND_TOPIC,
        ASSIGNMENT_PLAN_ACK_TOPIC,
    }
)


class RuntimePlanOutcomeJoinError(RuntimeError):
    """Stable fail-closed error raised before any joined result is admitted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, slots=True)
class HashedArtifact:
    """One explicit file path and its externally supplied SHA-256."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "sha256", _normalise_sha256(self.sha256))

    def resolved(self) -> "HashedArtifact":
        return HashedArtifact(self.path.expanduser().resolve(), self.sha256)

    def to_dict(self) -> dict[str, str]:
        return {"path": str(self.path), "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class RuntimePlanOutcomeJoinInputs:
    """All immutable sources required by the strict episode-level join."""

    online_observations: HashedArtifact
    d2_identity_evaluation: HashedArtifact
    d2_identity_manifest: HashedArtifact
    d2_online_d1_records: HashedArtifact
    d2_online_d2_records: HashedArtifact
    d2_observation_truth_labels: HashedArtifact
    d2_identity_evidence: HashedArtifact
    offline_truth_state: HashedArtifact
    offline_proximity_intercepts: HashedArtifact
    episode_manifest: HashedArtifact
    scenario_config: HashedArtifact
    schema_version: str = RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported runtime outcome input schema")
        for name in _INPUT_NAMES:
            if not isinstance(getattr(self, name), HashedArtifact):
                raise TypeError(f"{name} must be a HashedArtifact")

    def resolved(self) -> "RuntimePlanOutcomeJoinInputs":
        return RuntimePlanOutcomeJoinInputs(
            **{name: getattr(self, name).resolved() for name in _INPUT_NAMES}
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifacts": {
                name: getattr(self, name).to_dict() for name in _INPUT_NAMES
            },
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: str | Path | None = None,
    ) -> "RuntimePlanOutcomeJoinInputs":
        _require_exact_keys(
            payload,
            {"schema_version", "artifacts"},
            "runtime outcome input specification",
        )
        if payload.get("schema_version") != RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION:
            raise RuntimePlanOutcomeJoinError(
                "unsupported_input_schema",
                "runtime outcome input specification schema is unsupported",
            )
        artifacts = _mapping(payload.get("artifacts"), "input artifacts")
        _require_exact_keys(artifacts, set(_INPUT_NAMES), "input artifacts")
        root = None if base_dir is None else Path(base_dir).expanduser().resolve()
        values: dict[str, HashedArtifact] = {}
        for name in _INPUT_NAMES:
            item = _mapping(artifacts[name], f"input artifact {name}")
            _require_exact_keys(item, {"path", "sha256"}, f"input artifact {name}")
            path = Path(_required_string(item, "path"))
            if not path.is_absolute() and root is not None:
                path = root / path
            values[name] = HashedArtifact(path, str(item.get("sha256", "")))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class _Envelope:
    sequence: int
    topic: str
    source: str
    timestamp: float
    schema_version: str
    payload: Mapping[str, Any] | None
    canonical_record_sha256: str | None


@dataclass(frozen=True, slots=True)
class _ValidatedAck:
    envelope_sequence: int
    ack_timestamp: float
    decision_id: str
    occurrence_id: str
    occurrence_index: int
    adoption_kind: str
    plan_id: str
    plan_version: int
    execution_signature_sha256: str
    accepted: bool
    source_plan_sequence: int
    source_guidance_sequence: int | None
    d3_learning_evidence: Mapping[str, Any]
    d4_regional_hint_evidence: Mapping[str, Any]
    bindings: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _TruthState:
    timestamps: np.ndarray
    intruder_state: np.ndarray
    intruder_ids: tuple[str, ...]
    interceptor_state: np.ndarray
    intruder_active: np.ndarray
    resource_count: int
    target_count: int
    physics_dt_s: float

    @property
    def episode_end(self) -> float:
        return float(self.timestamps[-1])


@dataclass(frozen=True, slots=True)
class _IdentityIndex:
    lineage_time_window_s: float
    evaluation_schema_version: str
    by_global_track_id: Mapping[
        str,
        tuple[tuple[float, Mapping[str, Any]], ...],
    ]
    frame_mappings: tuple[
        tuple[float, tuple[Mapping[str, Any], ...]],
        ...,
    ]


def load_runtime_plan_outcome_join_inputs(
    path: str | Path,
    *,
    expected_sha256: str,
) -> RuntimePlanOutcomeJoinInputs:
    """Load a hash-verified input specification with relative-path support."""

    source = Path(path).expanduser().resolve()
    _verify_file(source, expected_sha256, "input_specification")
    payload = _load_json(source, "runtime outcome input specification")
    return RuntimePlanOutcomeJoinInputs.from_mapping(
        payload,
        base_dir=source.parent,
    )


def evaluate_runtime_plan_outcomes(
    inputs: RuntimePlanOutcomeJoinInputs,
    *,
    evaluation_date: str = RUNTIME_PLAN_OUTCOME_JOIN_DATE,
) -> dict[str, Any]:
    """Join verified runtime ACKs to evaluator-only identity and world state."""

    if evaluation_date != RUNTIME_PLAN_OUTCOME_JOIN_DATE:
        _fail(
            "evaluation_date_mismatch",
            f"evaluation_date must be {RUNTIME_PLAN_OUTCOME_JOIN_DATE}",
        )
    source = inputs.resolved()
    artifact_hashes = _verify_all_inputs(source)
    manifest = _load_json(source.episode_manifest.path, "episode manifest")
    config = _load_json(source.scenario_config.path, "scenario config")
    episode = _validate_episode_contract(manifest, config, artifact_hashes)

    envelopes = _load_online_envelopes(source.online_observations.path)
    envelopes_by_sequence = {item.sequence: item for item in envelopes}
    acks = _validate_runtime_acks(envelopes, envelopes_by_sequence)
    identity, identity_recovery_config_provenance = (
        _load_and_validate_d2_identity(
        source,
        artifact_hashes=artifact_hashes,
        manifest=manifest,
        online_envelopes=envelopes_by_sequence,
        )
    )
    observation_truth_disposition = (
        _load_and_validate_observation_truth_disposition(
            source,
            artifact_hashes=artifact_hashes,
            identity=identity,
        )
    )
    truth = _load_truth_state(
        source.offline_truth_state.path,
        config=config,
    )
    events = _load_and_validate_proximity_events(
        source.offline_proximity_intercepts.path,
        truth=truth,
    )
    _expect(
        math.isclose(
            truth.episode_end,
            float(config["duration_s"]),
            rel_tol=0.0,
            abs_tol=max(1.0e-9, truth.physics_dt_s * 1.0e-6),
        ),
        "episode_end_mismatch",
        "truth timeline endpoint does not match scenario duration",
    )

    windows = _build_binding_windows(
        acks,
        identity=identity,
        truth=truth,
        events=events,
    )
    diagnostic_available_count = sum(
        bool(item["bounded_pair_progress_diagnostic"]["available"])
        for item in windows
    )
    correct_event_count = sum(
        item["assigned_pair_proximity_event_observed"] is True for item in windows
    )
    wrong_target_event_count = sum(
        bool(item["other_target_proximity_event_observed"]) for item in windows
    )
    applied_learning_count = sum(
        ack.d3_learning_evidence.get("applied") is True for ack in acks
    )
    applied_regional_count = sum(
        ack.d4_regional_hint_evidence.get("applied") is True for ack in acks
    )
    evaluation_refresh_count = sum(
        ack.adoption_kind == "same_identity_evaluation_refresh" for ack in acks
    )
    plan_refresh_count = sum(
        ack.adoption_kind == "same_identity_plan_refresh" for ack in acks
    )
    refresh_count = evaluation_refresh_count + plan_refresh_count

    return {
        "schema_version": RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_VERSION,
        "evaluation_date": evaluation_date,
        "evaluation_mode": "offline_read_only_fail_closed",
        "episode": episode,
        "source_artifacts": {
            name: {
                "path": str(getattr(source, name).path),
                "sha256": artifact_hashes[name],
                "verified": True,
            }
            for name in _INPUT_NAMES
        },
        "runtime_ack_evidence": {
            "available": bool(acks),
            "reason": None if acks else "runtime_assignment_plan_ack_missing",
            "ack_count": len(acks),
            "unique_occurrence_count": len(acks),
            "new_plan_identity_occurrence_count": len(acks) - refresh_count,
            "same_identity_refresh_occurrence_count": refresh_count,
            "same_identity_evaluation_refresh_occurrence_count": (
                evaluation_refresh_count
            ),
            "same_identity_plan_refresh_occurrence_count": plan_refresh_count,
            "binding_count": len(windows),
            "source_sequence_and_payload_hash_verified": True,
            "online_truth_use_count": 0,
            "d3_learning_applied_ack_count": applied_learning_count,
            "d4_regional_applied_ack_count": applied_regional_count,
        },
        "d2_identity_recovery_config_provenance": (
            identity_recovery_config_provenance
        ),
        "offline_observation_truth_disposition": observation_truth_disposition,
        "binding_windows": windows,
        "observed_diagnostics": {
            "bounded_pair_progress_name": RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME,
            "bounded_pair_progress_available_count": diagnostic_available_count,
            "assigned_pair_five_meter_event_count": correct_event_count,
            "same_resource_other_target_event_count": wrong_target_event_count,
            "formal_reward_available": False,
            "formal_reward": None,
            "formal_reward_reason": (
                "bounded_pair_progress_is_not_a_formal_d3_ppo_reward"
            ),
            "counterfactual_available": False,
            "counterfactual": None,
            "counterfactual_reason": "same_seed_paired_formal_shadow_unavailable",
            "causal_attribution_available": False,
            "causal_attribution": None,
            "causal_attribution_reason": (
                "controlled_intervention_or_paired_causal_evidence_unavailable"
            ),
        },
        "admission": {
            "runtime_ack_join_available": bool(acks),
            "observed_pair_diagnostic_available": diagnostic_available_count > 0,
            "formal_same_seed_paired_shadow_available": False,
            "held_out_seed_performance_available": False,
            "formal_learning_adoption_outcome_available": False,
            "ppo_allowed": False,
            "assist_allowed": False,
            "authority_allowed": False,
            "rule_fallback_required": True,
            "identity_recovery_config_provenance_required": (
                identity_recovery_config_provenance[
                    "identity_manifest_schema_version"
                ]
                == D2_IDENTITY_MANIFEST_SCHEMA_V2
            ),
            "identity_recovery_config_provenance_verified": (
                identity_recovery_config_provenance["provenance_verified"]
            ),
            "identity_recovery_config_provenance_reason": (
                identity_recovery_config_provenance["unavailable_reason"]
            ),
            "status": "runtime_observed_diagnostic_only_admission_closed",
            "promotion_blockers": [
                "formal_same_seed_paired_shadow_unavailable",
                "held_out_seed_performance_unavailable",
                "counterfactual_and_causal_attribution_unavailable",
                "formal_ppo_reward_unavailable",
                "multi_seed_learning_adoption_outcome_evidence_unavailable",
            ],
        },
        "audit": {
            "passed": True,
            "fail_closed": True,
            "source_mutation_performed": False,
            "frozen_900_episode_data_modified": False,
            "violation_count": 0,
            "violations": [],
        },
    }


def write_runtime_plan_outcome_join_report(
    inputs: RuntimePlanOutcomeJoinInputs,
    output_dir: str | Path,
    *,
    evaluation_date: str = RUNTIME_PLAN_OUTCOME_JOIN_DATE,
) -> dict[str, Path]:
    """Write deterministic JSON and Chinese Markdown without source mutation."""

    payload = evaluate_runtime_plan_outcomes(
        inputs,
        evaluation_date=evaluation_date,
    )
    root = Path(output_dir).expanduser().resolve()
    input_paths = {
        getattr(inputs.resolved(), name).path for name in _INPUT_NAMES
    }
    _expect(
        all(path != root and root not in path.parents for path in input_paths),
        "output_overlaps_input_artifact",
        "output directory must not replace an input artifact",
    )
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "runtime_plan_outcome_join.json"
    markdown_path = root / "runtime_plan_outcome_join_cn.md"
    _write_json_atomic(json_path, payload)
    _write_text_atomic(
        markdown_path,
        render_runtime_plan_outcome_join_markdown(payload),
    )
    return {"json": json_path, "markdown": markdown_path}


def render_runtime_plan_outcome_join_markdown(
    payload: Mapping[str, Any],
) -> str:
    """Render the evidence boundary and per-binding result in Chinese."""

    runtime = _mapping(payload.get("runtime_ack_evidence"), "runtime evidence")
    diagnostics = _mapping(payload.get("observed_diagnostics"), "diagnostics")
    admission = _mapping(payload.get("admission"), "admission")
    disposition = _mapping(
        payload.get("offline_observation_truth_disposition"),
        "offline observation truth disposition",
    )
    recovery_config = _mapping(
        payload.get("d2_identity_recovery_config_provenance"),
        "D2 identity recovery config provenance",
    )
    windows = _sequence(payload.get("binding_windows"), "binding windows")
    lines = [
        "# 运行时计划确认与离线观测结果联接",
        "",
        "## 结论",
        "",
        (
            f"本 episode 校验 {int(runtime['ack_count'])} 条运行时计划确认和 "
            f"{int(runtime['binding_count'])} 个资源-航迹绑定。"
        ),
        (
            f"其中 {int(diagnostics['bounded_pair_progress_available_count'])} 个绑定具备"
            "有界配对进展诊断，5 米内正确目标接近事件为 "
            f"{int(diagnostics['assigned_pair_five_meter_event_count'])} 个。"
        ),
        "该诊断只描述已观测距离变化，不是 D3 正式强化学习奖励，也不构成因果或反事实证据。",
        "强化学习近端策略优化、辅助模式和控制权准入继续关闭，规则回退保持启用。",
        "",
        "## 身份恢复配置谱系",
        "",
        (
            "清单模式为 "
            f"`{recovery_config['identity_manifest_schema_version']}`，"
            "配置谱系"
            + (
                "已通过逐条在线记录校验。"
                if recovery_config["provenance_verified"]
                else "不可用，原因："
                f"`{recovery_config['unavailable_reason']}`。"
            )
        ),
        "该谱系只进入离线审计，不回填严格身份切换指标，也不进入在线控制。",
        "",
        "## 离线观测处置",
        "",
        (
            f"已验证 `{disposition['source_schema_version']}` sidecar 及来源哈希。"
            f"目标标签 {_disposition_count(disposition, 'target_label')} 条，"
            "已知虚警 "
            f"{_disposition_count(disposition, 'known_false_alarm')} 条，未知 "
            f"{_disposition_count(disposition, 'unknown')} 条，缺失处置 "
            f"{_disposition_count(disposition, 'missing_disposition')} 条。"
        ),
        "已知虚警不作为目标身份，D6 不从在线字段推断处置，也不回填 D2 严格 ID Switch。",
        "",
        "## 绑定结果",
        "",
        "| 决策 | 资源 | 全局航迹 | 离线目标映射 | 起始距离/m | 最小距离/m | 5米事件 | 其他目标事件 | 诊断分数 |",
        "| --- | --- | --- | --- | ---: | ---: | :---: | :---: | ---: |",
    ]
    for raw in windows:
        item = _mapping(raw, "binding window")
        identity = _mapping(item.get("identity_mapping"), "identity mapping")
        score = _mapping(
            item.get("bounded_pair_progress_diagnostic"),
            "pair progress diagnostic",
        )
        lines.append(
            "| {decision} | {resource} | {track} | {truth} | {start} | {minimum} | "
            "{correct} | {other} | {score} |".format(
                decision=item["decision_id"],
                resource=item["resource_id"],
                track=item["global_track_id"],
                truth=_format_identity_mapping(identity),
                start=_format_metric(item.get("start_3d_distance_m")),
                minimum=_format_metric(item.get("min_3d_distance_m")),
                correct=_format_bool(item.get("assigned_pair_proximity_event_observed")),
                other=_format_bool(item.get("other_target_proximity_event_observed")),
                score=(
                    _format_metric(score.get("value"))
                    if score.get("available")
                    else f"不可用（{score.get('reason')}）"
                ),
            )
        )
    lines.extend(
        [
            "",
            "## 准入边界",
            "",
            f"当前状态为 `{admission['status']}`。以下条件仍未满足：",
            "",
            *[f"- `{item}`" for item in admission["promotion_blockers"]],
            "",
        ]
    )
    return "\n".join(lines)


def _disposition_count(payload: Mapping[str, Any], name: str) -> str:
    item = payload.get(name)
    if not isinstance(item, Mapping) or item.get("availability") != "available":
        reason = item.get("reason") if isinstance(item, Mapping) else "unavailable"
        return f"不可用（{reason}）"
    return str(item.get("count"))


def _format_identity_mapping(payload: Mapping[str, Any]) -> str:
    if payload.get("available"):
        return str(payload.get("truth_target_id"))
    details = payload.get("details")
    detail_text = (
        ""
        if not isinstance(details, list) or not details
        else "；" + "；".join(str(value) for value in details)
    )
    return f"不可用（{payload.get('reason')}{detail_text}）"


def _verify_all_inputs(
    inputs: RuntimePlanOutcomeJoinInputs,
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    paths: set[Path] = set()
    for name in _INPUT_NAMES:
        artifact = getattr(inputs, name)
        _expect(
            artifact.path not in paths,
            "duplicate_input_path",
            f"multiple logical inputs reference the same file: {artifact.path}",
        )
        paths.add(artifact.path)
        hashes[name] = _verify_file(artifact.path, artifact.sha256, name)
    return hashes


def _validate_episode_contract(
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    for key in (
        "episode_id",
        "config_sha256",
        "scenario_name",
        "scenario_version",
        "seed",
        "world_schema",
        "bus_schema",
        "offline_truth_schema",
    ):
        _expect(key in manifest, "episode_manifest_incomplete", f"missing {key}")
    _expect(
        manifest.get("bus_schema") == EPISODE_BUS_SCHEMA,
        "unsupported_episode_bus_schema",
        "episode bus schema is unsupported",
    )
    _expect(
        manifest.get("world_schema") == WORLD_SCHEMA,
        "unsupported_world_schema",
        "world schema is unsupported",
    )
    _expect(
        config.get("schema_version") == SCENARIO_SCHEMA,
        "unsupported_scenario_schema",
        "scenario config schema is unsupported",
    )
    config_digest = _canonical_payload_sha256(config)
    expected_config = _normalise_sha256(manifest.get("config_sha256"))
    _expect(
        config_digest == expected_config,
        "scenario_config_manifest_hash_mismatch",
        "scenario config canonical SHA-256 does not match episode manifest",
    )
    for key in ("scenario_name", "scenario_version", "seed"):
        _expect(
            manifest.get(key) == config.get(key),
            "episode_manifest_config_mismatch",
            f"episode manifest and scenario config disagree on {key}",
        )
    target_count = _positive_int(config.get("target_count"), "target_count")
    resource_count = _positive_int(config.get("resource_count"), "resource_count")
    duration_s = _positive_float(config.get("duration_s"), "duration_s")
    physics_dt_s = _positive_float(config.get("physics_dt_s"), "physics_dt_s")
    intercept_radius = _positive_float(
        config.get("intercept_radius_m"), "intercept_radius_m"
    )
    _expect(
        math.isclose(intercept_radius, FIVE_METER_THRESHOLD_M, abs_tol=1.0e-12),
        "unsupported_intercept_radius",
        "offline proximity events must use the fixed 5 m threshold",
    )
    return {
        "episode_id": _required_string(manifest, "episode_id"),
        "scenario_name": _required_string(manifest, "scenario_name"),
        "scenario_version": _required_string(manifest, "scenario_version"),
        "seed": int(manifest["seed"]),
        "target_count": target_count,
        "resource_count": resource_count,
        "duration_s": duration_s,
        "physics_dt_s": physics_dt_s,
        "manifest_sha256": artifact_hashes["episode_manifest"],
        "scenario_config_sha256": artifact_hashes["scenario_config"],
        "config_canonical_sha256": config_digest,
    }


def _load_online_envelopes(path: Path) -> tuple[_Envelope, ...]:
    envelopes: list[_Envelope] = []
    seen: set[int] = set()
    previous = 0
    for index, record in enumerate(
        _iter_jsonl(
            path,
            "online observations",
            reject_online_truth=True,
        ),
        start=1,
    ):
        _require_exact_keys(
            record,
            {"sequence", "topic", "source", "timestamp", "schema_version", "payload"},
            f"online envelope line {index}",
        )
        sequence = _positive_int(record.get("sequence"), "bus sequence")
        _expect(
            sequence not in seen,
            "duplicate_bus_sequence",
            f"duplicate online bus sequence {sequence}",
        )
        _expect(
            sequence > previous,
            "non_monotonic_bus_sequence",
            "online bus sequences must be strictly increasing in file order",
        )
        seen.add(sequence)
        previous = sequence
        payload = _mapping(record.get("payload"), "online envelope payload")
        topic = _required_string(record, "topic")
        source = _required_string(record, "source")
        timestamp = _nonnegative_float(record.get("timestamp"), "timestamp")
        schema_version = _required_string(record, "schema_version")
        if topic not in _RETAINED_ONLINE_TOPICS:
            continue
        canonical_record_sha256 = None
        retained_payload: Mapping[str, Any] | None = payload
        if topic in _D2_FILTERED_SOURCE_TOPICS:
            canonical_record_sha256 = _canonical_payload_sha256(record)
            retained_payload = None
        envelopes.append(
            _Envelope(
                sequence=sequence,
                topic=topic,
                source=source,
                timestamp=timestamp,
                schema_version=schema_version,
                payload=retained_payload,
                canonical_record_sha256=canonical_record_sha256,
            )
        )
    return tuple(envelopes)


def _validate_runtime_acks(
    envelopes: Sequence[_Envelope],
    by_sequence: Mapping[int, _Envelope],
) -> tuple[_ValidatedAck, ...]:
    raw_acks = tuple(item for item in envelopes if item.topic == ASSIGNMENT_PLAN_ACK_TOPIC)
    validated: list[_ValidatedAck] = []
    plan_sources: set[int] = set()
    guidance_sources: set[int] = set()
    latest_version: dict[str, int] = {}
    identity_occurrences: dict[tuple[str, int], dict[str, Any]] = {}
    for envelope in raw_acks:
        _expect(
            envelope.source == "MAIN-RUNTIME"
            and envelope.schema_version == ASSIGNMENT_PLAN_ACK_SCHEMA,
            "unsupported_runtime_ack_contract",
            "runtime assignment ACK source or schema is unsupported",
        )
        assert envelope.payload is not None
        ack = envelope.payload
        _require_exact_keys(ack, set(_ACK_KEYS), "runtime assignment ACK")
        _expect(
            ack.get("physical_outcome_available") is False
            and ack.get("reward_available") is False,
            "ack_self_claims_offline_evidence",
            "runtime ACK may not claim physical outcome or reward availability",
        )
        ack_timestamp = _nonnegative_float(
            ack.get("ack_timestamp"), "ACK timestamp"
        )
        _expect(
            math.isclose(ack_timestamp, envelope.timestamp, abs_tol=1.0e-9),
            "ack_envelope_timestamp_mismatch",
            "ACK payload timestamp does not match its bus envelope",
        )
        plan_id = _required_string(ack, "plan_id")
        plan_version = _nonnegative_int(ack.get("plan_version"), "plan_version")
        decision_id = _required_string(ack, "decision_id")
        _expect(
            decision_id == f"{plan_id}:v{plan_version}",
            "decision_id_plan_mismatch",
            "ACK decision_id does not match plan id/version",
        )
        previous_version = latest_version.get(plan_id)
        _expect(
            previous_version is None or plan_version >= previous_version,
            "stale_plan_version",
            f"plan {plan_id} version {plan_version} is stale",
        )

        plan_sequence = _positive_int(
            ack.get("source_plan_bus_sequence"), "source plan bus sequence"
        )
        _expect(
            plan_sequence not in plan_sources,
            "source_plan_sequence_reused",
            "one D3 plan publication is referenced by multiple ACKs",
        )
        plan_sources.add(plan_sequence)
        plan_envelope = by_sequence.get(plan_sequence)
        _expect(
            plan_envelope is not None
            and plan_envelope.sequence < envelope.sequence
            and plan_envelope.topic == ASSIGNMENT_PLAN_TOPIC
            and plan_envelope.source == "D3"
            and plan_envelope.schema_version == D3_PLAN_SCHEMA,
            "source_plan_sequence_mismatch",
            "ACK source plan sequence does not identify a prior D3 plan",
        )
        assert plan_envelope is not None
        assert plan_envelope.payload is not None
        _expect(
            ack.get("plan_schema_version") == plan_envelope.schema_version,
            "source_plan_schema_mismatch",
            "ACK plan schema does not match the source plan envelope",
        )
        _expect_payload_hash(
            plan_envelope.payload,
            ack.get("source_plan_payload_sha256"),
            "source_plan_payload_hash_mismatch",
        )
        plan = plan_envelope.payload
        _expect(
            plan.get("plan_id") == plan_id
            and plan.get("plan_version") == plan_version,
            "ack_plan_version_mismatch",
            "ACK id/version does not match the referenced D3 plan",
        )
        plan_created = _nonnegative_float(
            plan.get("created_at"), "plan created_at"
        )
        _expect(
            math.isclose(
                plan_created,
                _nonnegative_float(ack.get("plan_created_at"), "ACK plan_created_at"),
                abs_tol=1.0e-9,
            ),
            "plan_created_at_mismatch",
            "ACK plan_created_at does not match the source plan",
        )
        _expect(
            plan_envelope.timestamp <= ack_timestamp + 1.0e-9,
            "source_plan_from_future",
            "ACK references a D3 plan from the future",
        )

        assignments = _assignment_bindings(plan)
        metadata = _mapping(plan.get("metadata"), "D3 plan metadata")
        authority = _validate_ack_authority(
            ack,
            metadata,
            ack_timestamp=ack_timestamp,
        )
        execution_signature = _plan_execution_signature(
            plan,
            assignments=assignments,
            authority=authority,
        )
        execution_signature_sha256 = _canonical_payload_sha256(
            execution_signature
        )
        identity_key = (plan_id, plan_version)
        prior_identity = identity_occurrences.get(identity_key)
        execution_changed = _strict_bool(
            metadata.get("execution_signature_changed"),
            "D3 execution_signature_changed",
        )
        evaluation_refresh_only = _strict_bool(
            metadata.get("evaluation_refresh_only"),
            "D3 evaluation_refresh_only",
        )
        plan_refresh_only = _strict_bool(
            metadata.get("plan_refresh_only"),
            "D3 plan_refresh_only",
        )
        if prior_identity is None:
            _expect(
                execution_changed
                and not evaluation_refresh_only
                and not plan_refresh_only,
                "new_plan_identity_refresh_flags_invalid",
                "a new plan identity must declare changed execution semantics",
            )
            occurrence_index = 1
            adoption_kind = "new_plan_identity"
            identity_occurrences[identity_key] = {
                "created_at": plan_created,
                "execution_signature": execution_signature,
                "last_ack_timestamp": ack_timestamp,
                "occurrence_count": 1,
            }
            latest_version[plan_id] = plan_version
        else:
            _expect(
                previous_version == plan_version,
                "superseded_plan_identity_refresh",
                "an older plan identity cannot refresh after a newer version",
            )
            _expect(
                math.isclose(
                    float(prior_identity["created_at"]),
                    plan_created,
                    abs_tol=1.0e-9,
                ),
                "same_plan_created_at_changed",
                "same plan identity refresh changed its creation timestamp",
            )
            _expect(
                ack_timestamp > float(prior_identity["last_ack_timestamp"]),
                "ack_occurrence_timestamp_not_increasing",
                "same plan identity ACK occurrences must advance in time",
            )
            _expect(
                execution_signature == prior_identity["execution_signature"],
                "same_plan_execution_signature_changed",
                "same plan identity refresh changed binding, coalition, or authority",
            )
            _expect(
                not execution_changed
                and (evaluation_refresh_only, plan_refresh_only)
                in {(True, False), (False, True)},
                "same_plan_refresh_flags_invalid",
                "same plan identity requires exactly one refresh-only flag",
            )
            occurrence_index = int(prior_identity["occurrence_count"]) + 1
            adoption_kind = (
                "same_identity_evaluation_refresh"
                if evaluation_refresh_only
                else "same_identity_plan_refresh"
            )
            prior_identity["last_ack_timestamp"] = ack_timestamp
            prior_identity["occurrence_count"] = occurrence_index
        guidance_sequence = ack.get("source_guidance_bus_sequence")
        guidance_hash = ack.get("source_guidance_payload_sha256")
        commands: dict[tuple[str, str], Mapping[str, Any]] = {}
        if guidance_sequence is None or guidance_hash is None:
            _expect(
                guidance_sequence is None and guidance_hash is None,
                "incomplete_source_guidance_reference",
                "guidance sequence and payload hash must both be null or present",
            )
            source_guidance_sequence = None
        else:
            source_guidance_sequence = _positive_int(
                guidance_sequence, "source guidance bus sequence"
            )
            _expect(
                source_guidance_sequence not in guidance_sources,
                "source_guidance_sequence_reused",
                "one D7 guidance batch is referenced by multiple ACKs",
            )
            guidance_sources.add(source_guidance_sequence)
            guidance_envelope = by_sequence.get(source_guidance_sequence)
            _expect(
                guidance_envelope is not None
                and guidance_envelope.sequence < envelope.sequence
                and guidance_envelope.topic == GUIDANCE_COMMAND_TOPIC
                and guidance_envelope.source == "D7"
                and guidance_envelope.schema_version == D7_GUIDANCE_SCHEMA,
                "source_guidance_sequence_mismatch",
                "ACK source guidance sequence does not identify a prior D7 batch",
            )
            assert guidance_envelope is not None
            assert guidance_envelope.payload is not None
            _expect_payload_hash(
                guidance_envelope.payload,
                guidance_hash,
                "source_guidance_payload_hash_mismatch",
            )
            commands = _guidance_bindings(
                guidance_envelope.payload,
                plan_id=plan_id,
                plan_version=plan_version,
            )
            extra = sorted(set(commands) - set(assignments))
            _expect(
                not extra,
                "extra_guidance_binding",
                f"D7 guidance contains bindings absent from D3 plan: {extra}",
            )

        binding_acks = _validate_binding_acks(
            ack,
            assignments=assignments,
            commands=commands,
        )
        validated.append(
            _ValidatedAck(
                envelope_sequence=envelope.sequence,
                ack_timestamp=ack_timestamp,
                decision_id=decision_id,
                occurrence_id=(
                    f"{decision_id}@ack-seq-{envelope.sequence}"
                    f"@t-{ack_timestamp:.9f}"
                ),
                occurrence_index=occurrence_index,
                adoption_kind=adoption_kind,
                plan_id=plan_id,
                plan_version=plan_version,
                execution_signature_sha256=execution_signature_sha256,
                accepted=_strict_bool(ack.get("accepted"), "accepted"),
                source_plan_sequence=plan_sequence,
                source_guidance_sequence=source_guidance_sequence,
                d3_learning_evidence=_mapping(
                    ack.get("d3_learning_evidence"), "D3 learning evidence"
                ),
                d4_regional_hint_evidence=_mapping(
                    ack.get("d4_regional_hint_evidence"),
                    "D4 regional hint evidence",
                ),
                bindings=binding_acks,
            )
        )
    return tuple(validated)


def _assignment_bindings(
    plan: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw = _sequence(plan.get("assignments"), "D3 assignments")
    declared = plan.get("assignment_count")
    if declared is not None:
        _expect(
            _nonnegative_int(declared, "D3 assignment_count") == len(raw),
            "d3_assignment_count_mismatch",
            "D3 assignment_count does not match assignments",
        )
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    resources: set[str] = set()
    for value in raw:
        item = _mapping(value, "D3 assignment")
        key = (
            _required_string(item, "resource_id"),
            _required_string(item, "global_track_id"),
        )
        _expect(
            key not in result and key[0] not in resources,
            "duplicate_d3_binding",
            "D3 plan contains a duplicate binding or resource",
        )
        resources.add(key[0])
        result[key] = item
    return result


def _validate_ack_authority(
    ack: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    ack_timestamp: float,
) -> dict[str, Any]:
    """Return the normalized authority jointly asserted by D3 and main."""

    ack_owner_layer = _required_string(ack, "active_plan_owner").lower()
    metadata_owner_layer = _required_string(metadata, "active_plan_owner").lower()
    ack_owner_id = _required_string(ack, "owner_node_id")
    metadata_owner_id = _required_string(metadata, "owner_node_id")
    _expect(
        ack_owner_layer == metadata_owner_layer and ack_owner_id == metadata_owner_id,
        "plan_ack_authority_owner_mismatch",
        "D3 plan metadata and runtime ACK disagree on active authority",
    )

    ack_epoch = _optional_nonnegative_int(
        ack.get("authority_epoch"), "ACK authority_epoch"
    )
    metadata_epoch = _optional_nonnegative_int(
        metadata.get("authority_epoch"), "D3 authority_epoch"
    )
    ack_lease = _optional_nonnegative_float(
        ack.get("lease_expires_at_s"), "ACK lease_expires_at_s"
    )
    metadata_lease = _optional_nonnegative_float(
        metadata.get("lease_expires_at_s"), "D3 lease_expires_at_s"
    )
    _expect(
        ack_epoch == metadata_epoch
        and (
            (ack_lease is None and metadata_lease is None)
            or (
                ack_lease is not None
                and metadata_lease is not None
                and math.isclose(ack_lease, metadata_lease, abs_tol=1.0e-9)
            )
        ),
        "plan_ack_authority_scope_mismatch",
        "D3 plan metadata and runtime ACK disagree on authority epoch or lease",
    )
    _expect(
        (ack_epoch is None) == (ack_lease is None),
        "partial_authority_epoch_lease",
        "authority epoch and lease must both be present or both be null",
    )
    if ack_lease is not None:
        _expect(
            ack_timestamp < ack_lease,
            "ack_authority_lease_expired",
            "runtime ACK was published after its authority lease expired",
        )
    return {
        "active_plan_owner": ack_owner_layer,
        "owner_node_id": ack_owner_id,
        "authority_epoch": ack_epoch,
        "lease_expires_at_s": ack_lease,
    }


def _plan_execution_signature(
    plan: Mapping[str, Any],
    *,
    assignments: Mapping[tuple[str, str], Mapping[str, Any]],
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Canonical executable signature used to admit same-identity refreshes."""

    records: list[dict[str, Any]] = []
    for key in sorted(assignments):
        item = assignments[key]
        records.append(
            {
                "resource_id": key[0],
                "global_track_id": key[1],
                "coalition_id": _optional_string(
                    item.get("coalition_id"), "D3 assignment coalition_id"
                ),
                "coalition_version": _optional_nonnegative_int(
                    item.get("coalition_version"),
                    "D3 assignment coalition_version",
                ),
                "member_role": _required_string(item, "member_role"),
                "owner_node_id": _optional_string(
                    item.get("owner_node_id"), "D3 assignment owner_node_id"
                ),
                "regional_owner_layer": _optional_string(
                    item.get("regional_owner_layer"),
                    "D3 assignment regional_owner_layer",
                ),
                "regional_region_id": _optional_string(
                    item.get("regional_region_id"),
                    "D3 assignment regional_region_id",
                ),
                "regional_epoch": _optional_nonnegative_int(
                    item.get("regional_epoch"), "D3 assignment regional_epoch"
                ),
                "regional_commit_mode": _optional_string(
                    item.get("regional_commit_mode"),
                    "D3 assignment regional_commit_mode",
                ),
            }
        )
    raw_unassigned = _sequence(
        plan.get("unassigned_global_track_ids"),
        "D3 unassigned_global_track_ids",
    )
    unassigned = tuple(
        _string_value(value, "D3 unassigned global_track_id")
        for value in raw_unassigned
    )
    _expect(
        len(unassigned) == len(set(unassigned)),
        "duplicate_unassigned_global_track_id",
        "D3 unassigned target inventory contains duplicates",
    )
    return {
        "plan_id": _required_string(plan, "plan_id"),
        "plan_version": _nonnegative_int(plan.get("plan_version"), "plan_version"),
        "assignments": records,
        "unassigned_global_track_ids": sorted(unassigned),
        "authority": dict(authority),
    }


def _guidance_bindings(
    payload: Mapping[str, Any],
    *,
    plan_id: str,
    plan_version: int,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    raw = _sequence(payload.get("commands"), "D7 commands")
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for value in raw:
        item = _mapping(value, "D7 guidance command")
        _expect(
            item.get("plan_id") == plan_id
            and item.get("plan_version") == plan_version,
            "d7_wrong_plan_version",
            "D7 guidance command references a different D3 plan version",
        )
        key = (
            _required_string(item, "resource_id"),
            _required_string(item, "global_track_id"),
        )
        _expect(
            key not in result,
            "duplicate_d7_binding",
            "D7 guidance batch contains a duplicate binding",
        )
        result[key] = item
    return result


def _validate_binding_acks(
    ack: Mapping[str, Any],
    *,
    assignments: Mapping[tuple[str, str], Mapping[str, Any]],
    commands: Mapping[tuple[str, str], Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    raw = _sequence(ack.get("binding_acks"), "ACK binding_acks")
    _expect(
        _nonnegative_int(ack.get("assignment_count"), "ACK assignment_count")
        == len(assignments)
        == len(raw),
        "ack_assignment_count_mismatch",
        "ACK binding list does not exactly cover D3 assignments",
    )
    result: list[Mapping[str, Any]] = []
    keys: set[tuple[str, str]] = set()
    for value in raw:
        item = _mapping(value, "ACK binding")
        _require_exact_keys(item, set(_BINDING_ACK_KEYS), "ACK binding")
        key = (
            _required_string(item, "resource_id"),
            _required_string(item, "global_track_id"),
        )
        _expect(
            key in assignments and key not in keys,
            "extra_or_duplicate_ack_binding",
            "ACK binding is extra, missing from D3, or duplicated",
        )
        keys.add(key)
        assignment = assignments[key]
        for field in ("coalition_id", "coalition_version", "member_role"):
            _expect(
                item.get(field) == assignment.get(field),
                "ack_assignment_metadata_mismatch",
                f"ACK binding disagrees with D3 assignment field {field}",
            )
        command = commands.get(key)
        expected_present = command is not None
        expected_mode = None if command is None else command.get("mode")
        expected_reason = None if command is None else command.get("gate_reason")
        expected_held = command is None or expected_mode == "hold"
        _expect(
            item.get("guidance_command_present") is expected_present
            and item.get("control_applied_to_world") is expected_present
            and item.get("guidance_mode") == expected_mode
            and item.get("guidance_gate_reason") == expected_reason
            and item.get("held") is expected_held,
            "ack_binding_guidance_mismatch",
            "ACK binding does not match the referenced D7 command",
        )
        result.append(dict(item))
    _expect(
        keys == set(assignments),
        "missing_ack_binding",
        "ACK does not cover every D3 assignment binding",
    )
    command_count = len(commands)
    held_count = sum(bool(item["held"]) for item in result)
    _expect(
        _nonnegative_int(ack.get("binding_ack_count"), "binding_ack_count")
        == command_count
        and _strict_bool(ack.get("fully_bound_to_guidance"), "fully_bound")
        is (command_count == len(assignments))
        and _nonnegative_int(
            ack.get("control_applied_binding_count"), "control applied count"
        )
        == command_count
        and _nonnegative_int(ack.get("held_binding_count"), "held count")
        == held_count,
        "ack_summary_count_mismatch",
        "ACK summary counters contradict its binding evidence",
    )
    return tuple(result)


def _load_and_validate_d2_identity(
    inputs: RuntimePlanOutcomeJoinInputs,
    *,
    artifact_hashes: Mapping[str, str],
    manifest: Mapping[str, Any],
    online_envelopes: Mapping[int, _Envelope],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    d2_manifest = _load_json(inputs.d2_identity_manifest.path, "D2 identity manifest")
    evaluation = _load_json(
        inputs.d2_identity_evaluation.path, "D2 identity evaluation"
    )
    _expect(
        d2_manifest.get("schema_version") in D2_IDENTITY_MANIFEST_SCHEMAS,
        "unsupported_d2_identity_manifest_schema",
        "D2 identity manifest schema is unsupported",
    )
    evaluation_schema = str(evaluation.get("schema_version", ""))
    _expect(
        evaluation_schema in _D2_IDENTITY_POLICY_BY_SCHEMA
        and evaluation.get("policy_version")
        == _D2_IDENTITY_POLICY_BY_SCHEMA.get(evaluation_schema)
        and evaluation.get("hash_algorithm") == "sha256",
        "unsupported_d2_identity_evaluation_contract",
        "D2 identity evaluation schema, policy, or hash algorithm is unsupported",
    )
    episode_id = _required_string(manifest, "episode_id")
    _expect(
        d2_manifest.get("episode_id") == episode_id
        and evaluation.get("episode_id") == episode_id,
        "d2_episode_id_mismatch",
        "D2 identity artifacts belong to a different episode",
    )
    _expect(
        d2_manifest.get("available") is True
        and d2_manifest.get("online_truth_isolation_verified") is True,
        "d2_identity_manifest_unavailable",
        "D2 identity manifest did not verify online truth isolation",
    )
    manifest_hashes = _mapping(
        d2_manifest.get("source_hashes"), "D2 manifest source_hashes"
    )
    expected_manifest_hashes = {
        "identity_evaluation": artifact_hashes["d2_identity_evaluation"],
        "identity_evidence": artifact_hashes["d2_identity_evidence"],
        "observation_truth_labels": artifact_hashes[
            "d2_observation_truth_labels"
        ],
        "online_d1_records": artifact_hashes["d2_online_d1_records"],
        "online_d2_records": artifact_hashes["d2_online_d2_records"],
    }
    for name, expected in expected_manifest_hashes.items():
        _expect(
            _normalise_sha256(manifest_hashes.get(name)) == expected,
            "d2_manifest_source_hash_mismatch",
            f"D2 manifest source hash mismatch for {name}",
        )
    evaluation_hashes = _mapping(
        evaluation.get("source_hashes"), "D2 evaluation source_hashes"
    )
    expected_evaluation_hashes = {
        "identity_evidence_bundle": artifact_hashes["d2_identity_evidence"],
        "observation_truth_labels": artifact_hashes[
            "d2_observation_truth_labels"
        ],
        "online_d1_records": artifact_hashes["d2_online_d1_records"],
        "online_d2_records": artifact_hashes["d2_online_d2_records"],
    }
    for name, expected in expected_evaluation_hashes.items():
        _expect(
            _normalise_sha256(evaluation_hashes.get(name)) == expected,
            "d2_evaluation_source_hash_mismatch",
            f"D2 evaluation source hash mismatch for {name}",
        )
    recovery_config_provenance = (
        adapt_d2_identity_recovery_config_provenance(
            producer_evaluation_schema_version=evaluation_schema,
            identity_source=inputs.d2_identity_evaluation.path,
            identity_manifest=inputs.d2_identity_manifest.path,
            expected_identity_manifest_sha256=artifact_hashes[
                "d2_identity_manifest"
            ],
            d2_online_d2_records=inputs.d2_online_d2_records.path,
            d2_expected_online_d2_records_sha256=artifact_hashes[
                "d2_online_d2_records"
            ],
            identity_source_hashes={
                str(name): _normalise_sha256(value)
                for name, value in evaluation_hashes.items()
            },
        )
    )
    if (
        d2_manifest.get("schema_version") == D2_IDENTITY_MANIFEST_SCHEMA_V2
        and not recovery_config_provenance.available
    ):
        _fail(
            recovery_config_provenance.unavailable_reason
            or "identity_recovery_config_provenance_unavailable",
            "D2 identity recovery configuration provenance is invalid",
        )
    try:
        validate_d2_identity_commitment_evaluation(
            evaluation,
            source_hashes={
                str(name): _normalise_sha256(value)
                for name, value in evaluation_hashes.items()
            },
        )
    except TruthIsolatedEvaluationError as exc:
        _fail(
            "d2_identity_commitment_contract_invalid",
            str(exc),
        )
    audit = _mapping(evaluation.get("audit"), "D2 identity audit")
    _expect(
        audit.get("online_truth_isolation_verified") is True
        and audit.get("source_record_semantics_verified") is True
        and audit.get("source_verification")
        == "raw_source_hashes_and_record_sequences_verified"
        and audit.get("identity_heuristics_used") is False
        and audit.get("identity_sources_allowed") == ["source_observation_lineage"],
        "d2_identity_lineage_audit_incomplete",
        "D2 identity evaluation lacks strict source-observation lineage evidence",
    )
    _validate_filtered_online_source(
        inputs.d2_online_d1_records.path,
        expected_topic="modules.d1.fused_tracks",
        online_envelopes=online_envelopes,
    )
    _validate_filtered_online_source(
        inputs.d2_online_d2_records.path,
        expected_topic="modules.d2.associated_tracks",
        online_envelopes=online_envelopes,
    )
    frames = _sequence(evaluation.get("frames"), "D2 identity frames")
    previous_index = -1
    previous_time = -1.0
    for raw_frame in frames:
        frame = _mapping(raw_frame, "D2 identity frame")
        frame_index = _nonnegative_int(frame.get("frame_index"), "frame_index")
        frame_time = _nonnegative_float(
            frame.get("frame_timestamp"), "frame_timestamp"
        )
        _expect(
            frame_index > previous_index and frame_time >= previous_time,
            "d2_identity_frames_not_ordered",
            "D2 identity frames must be ordered and unique",
        )
        previous_index = frame_index
        previous_time = frame_time
        frame_track_ids: set[str] = set()
        for raw_mapping in _sequence(frame.get("mappings"), "D2 frame mappings"):
            mapping = _mapping(raw_mapping, "D2 frame mapping")
            track_id = _required_string(mapping, "global_track_id")
            _expect(
                track_id not in frame_track_ids,
                "d2_duplicate_track_mapping_in_frame",
                "D2 identity frame contains duplicate global_track_id mappings",
            )
            frame_track_ids.add(track_id)
    return evaluation, recovery_config_provenance.to_dict()


def _load_and_validate_observation_truth_disposition(
    inputs: RuntimePlanOutcomeJoinInputs,
    *,
    artifact_hashes: Mapping[str, str],
    identity: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate D2's normalized sidecar and cross-check its identity audit."""

    rows = tuple(
        _iter_jsonl(
            inputs.d2_observation_truth_labels.path,
            "D2 normalized observation truth labels",
            empty_code="d2_observation_truth_labels_empty",
        )
    )
    try:
        disposition = audit_observation_truth_sidecar(
            rows,
            accepted_contract="d2_normalized",
        )
    except ObservationTruthSidecarError as exc:
        _fail(exc.code, str(exc))

    identity_audit = _mapping(identity.get("audit"), "D2 identity audit")
    audit_cross_check = "legacy_v1_not_reported_by_d2"
    known_false_alarm_mapping_count = 0
    if disposition.source_schema_version == D2_OBSERVATION_TRUTH_SCHEMA_V2:
        _expect(
            identity_audit.get("observation_truth_schema_version")
            == D2_OBSERVATION_TRUTH_SCHEMA_V2,
            "d2_observation_truth_audit_schema_mismatch",
            "D2 identity audit does not identify its normalized v2 sidecar",
        )
        raw_counts = _mapping(
            identity_audit.get("observation_truth_disposition_counts"),
            "D2 observation truth disposition counts",
        )
        unsupported = set(raw_counts) - {
            TRUTH_DISPOSITION_TARGET,
            TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
            TRUTH_DISPOSITION_UNKNOWN,
        }
        _expect(
            not unsupported,
            "d2_observation_truth_audit_disposition_unknown",
            f"D2 identity audit reports unsupported dispositions: {sorted(unsupported)}",
        )
        reported_counts = {
            name: _nonnegative_int(
                raw_counts.get(name, 0),
                f"D2 disposition count {name}",
            )
            for name in (
                TRUTH_DISPOSITION_TARGET,
                TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
                TRUTH_DISPOSITION_UNKNOWN,
            )
        }
        expected_counts = {
            TRUTH_DISPOSITION_TARGET: disposition.target_label_count,
            TRUTH_DISPOSITION_KNOWN_FALSE_ALARM: (
                disposition.known_false_alarm_count
            ),
            TRUTH_DISPOSITION_UNKNOWN: disposition.unknown_count,
        }
        _expect(
            reported_counts == expected_counts,
            "d2_observation_truth_audit_count_mismatch",
            "D2 identity audit disposition counts contradict the hashed sidecar",
        )
        _expect(
            sum(reported_counts.values()) == disposition.record_count,
            "d2_observation_truth_audit_total_mismatch",
            "D2 disposition counts do not cover the normalized sidecar",
        )
        audit_cross_check = "schema_and_disposition_counts_match_hashed_sidecar"

        for raw_frame in _sequence(identity.get("frames"), "D2 identity frames"):
            frame = _mapping(raw_frame, "D2 identity frame")
            for raw_mapping in _sequence(
                frame.get("mappings"),
                "D2 identity frame mappings",
            ):
                mapping = _mapping(raw_mapping, "D2 identity mapping")
                if mapping.get("reason") != "known_false_alarm_only":
                    continue
                known_false_alarm_mapping_count += 1
                _expect(
                    mapping.get("status") == "excluded"
                    and mapping.get("truth_target_id") is None
                    and not mapping.get("candidate_truth_target_ids"),
                    "d2_known_false_alarm_promoted_to_target",
                    "D2 mapped known false alarm evidence into a target identity",
                )
        _expect(
            _nonnegative_int(
                identity_audit.get("known_false_alarm_only_mapping_count", 0),
                "D2 known-false-alarm-only mapping count",
            )
            == known_false_alarm_mapping_count,
            "d2_known_false_alarm_mapping_audit_mismatch",
            "D2 known-false-alarm exclusion count contradicts its mappings",
        )

        if disposition.unknown_count:
            metrics = _mapping(identity.get("metrics"), "D2 identity metrics")
            blockers = identity_audit.get("identity_metrics_blocking_reasons")
            _expect(
                metrics.get("truth_metrics_available") is False
                and metrics.get("id_switch_count_available") is False
                and metrics.get("id_switch_count") is None
                and isinstance(blockers, list)
                and "truth_label_unknown" in blockers,
                "d2_unknown_disposition_did_not_fail_closed",
                "D2 strict identity metrics remained available with unknown labels",
            )

    payload = disposition.to_dict()
    payload.update(
        {
            "availability": "available",
            "source_artifact": "d2_observation_truth_labels",
            "source_sha256": artifact_hashes["d2_observation_truth_labels"],
            "source_hash_verified": True,
            "d2_identity_audit_cross_check": audit_cross_check,
            "known_false_alarm_only_mapping_count": (
                known_false_alarm_mapping_count
            ),
            "known_false_alarm_exclusion_verified": (
                disposition.source_schema_version
                == D2_OBSERVATION_TRUTH_SCHEMA_V2
            ),
            "strict_id_switch_source": "d2_identity_evaluation_only",
            "strict_id_switch_backfilled": False,
            "online_bus_contains_disposition_or_truth": False,
        }
    )
    return payload


def _validate_filtered_online_source(
    path: Path,
    *,
    expected_topic: str,
    online_envelopes: Mapping[int, _Envelope],
) -> None:
    seen: set[int] = set()
    for row in _iter_jsonl(
        path,
        f"D2 filtered source {expected_topic}",
        empty_code="d2_filtered_source_empty",
    ):
        sequence = _positive_int(row.get("sequence"), "D2 source sequence")
        _expect(
            sequence not in seen,
            "d2_source_duplicate_sequence",
            "D2 filtered source contains duplicate sequences",
        )
        seen.add(sequence)
        online = online_envelopes.get(sequence)
        _expect(
            online is not None and online.topic == expected_topic,
            "d2_source_sequence_not_in_online_log",
            "D2 filtered source sequence is absent from online observations",
        )
        _expect(
            online.canonical_record_sha256 is not None
            and _canonical_payload_sha256(row)
            == online.canonical_record_sha256,
            "d2_source_payload_not_in_online_log",
            "D2 filtered source payload differs from online observations",
        )


def _load_truth_state(
    path: Path,
    *,
    config: Mapping[str, Any],
) -> _TruthState:
    try:
        with np.load(path, allow_pickle=False) as payload:
            required = {
                "timestamps",
                "intruder_state",
                "intruder_ids",
                "interceptor_state",
                "intruder_active",
            }
            _expect(
                required.issubset(payload.files),
                "truth_state_fields_missing",
                "offline truth state NPZ lacks required arrays",
            )
            timestamps = np.asarray(payload["timestamps"], dtype=float)
            intruder_state = np.asarray(payload["intruder_state"], dtype=float)
            intruder_ids = tuple(str(value) for value in payload["intruder_ids"].tolist())
            interceptor_state = np.asarray(payload["interceptor_state"], dtype=float)
            intruder_active = np.asarray(payload["intruder_active"], dtype=bool)
    except RuntimePlanOutcomeJoinError:
        raise
    except Exception as exc:
        _fail("truth_state_load_failed", f"cannot load offline truth state: {exc}")
    target_count = _positive_int(config.get("target_count"), "target_count")
    resource_count = _positive_int(config.get("resource_count"), "resource_count")
    _expect(
        timestamps.ndim == 1
        and timestamps.size >= 2
        and np.all(np.isfinite(timestamps))
        and np.all(np.diff(timestamps) > 0.0),
        "truth_timeline_invalid",
        "truth timestamps must be finite, ordered, unique, and contain two samples",
    )
    expected_intruder_shape = (timestamps.size, target_count, 6)
    expected_interceptor_shape = (timestamps.size, resource_count, 6)
    _expect(
        intruder_state.shape == expected_intruder_shape
        and interceptor_state.shape == expected_interceptor_shape
        and intruder_active.shape == (timestamps.size, target_count),
        "truth_state_shape_mismatch",
        "truth state arrays do not match scenario counts and timeline",
    )
    _expect(
        np.all(np.isfinite(intruder_state))
        and np.all(np.isfinite(interceptor_state)),
        "truth_state_nonfinite",
        "truth state contains non-finite values",
    )
    _expect(
        len(intruder_ids) == target_count
        and len(set(intruder_ids)) == target_count
        and all(value for value in intruder_ids),
        "truth_target_ids_invalid",
        "truth target IDs must be present and unique",
    )
    return _TruthState(
        timestamps=timestamps,
        intruder_state=intruder_state,
        intruder_ids=intruder_ids,
        interceptor_state=interceptor_state,
        intruder_active=intruder_active,
        resource_count=resource_count,
        target_count=target_count,
        physics_dt_s=_positive_float(config.get("physics_dt_s"), "physics_dt_s"),
    )


def _load_and_validate_proximity_events(
    path: Path,
    *,
    truth: _TruthState,
) -> tuple[Mapping[str, Any], ...]:
    seen: set[tuple[float, str, str]] = set()
    result: list[Mapping[str, Any]] = []
    for row in _iter_jsonl(
        path,
        "offline proximity intercepts",
        allow_empty=True,
    ):
        timestamp = _nonnegative_float(row.get("timestamp"), "event timestamp")
        resource_id = _required_string(row, "resource_id")
        truth_target_id = _required_string(row, "truth_target_id")
        distance = _nonnegative_float(row.get("distance_m"), "event distance")
        resource_index = _resource_index(resource_id, truth.resource_count)
        _expect(
            truth_target_id in truth.intruder_ids,
            "proximity_event_target_unknown",
            "proximity event references an unknown truth target",
        )
        target_index = truth.intruder_ids.index(truth_target_id)
        _expect(
            row.get("resource_index") == resource_index
            and row.get("target_index") == target_index,
            "proximity_event_index_mismatch",
            "proximity event indices disagree with stable world IDs",
        )
        _expect(
            distance <= FIVE_METER_THRESHOLD_M + 1.0e-9,
            "proximity_event_above_threshold",
            "offline proximity event exceeds the fixed 5 m threshold",
        )
        state_distance = _distance_at_timestamp(
            truth,
            timestamp=timestamp,
            resource_index=resource_index,
            target_index=target_index,
        )
        _expect(
            math.isclose(distance, state_distance, rel_tol=0.0, abs_tol=1.0e-6),
            "proximity_event_state_mismatch",
            "offline proximity event distance disagrees with truth state",
        )
        key = (timestamp, resource_id, truth_target_id)
        _expect(
            key not in seen,
            "duplicate_proximity_event",
            "offline proximity event is duplicated",
        )
        seen.add(key)
        result.append(dict(row))
    return tuple(result)


def _build_binding_windows(
    acks: Sequence[_ValidatedAck],
    *,
    identity: Mapping[str, Any],
    truth: _TruthState,
    events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_resource: dict[str, list[tuple[_ValidatedAck, Mapping[str, Any]]]] = defaultdict(list)
    for ack in acks:
        for binding in ack.bindings:
            by_resource[str(binding["resource_id"])].append((ack, binding))
    for resource_id, values in by_resource.items():
        values.sort(key=lambda value: (value[0].ack_timestamp, value[0].envelope_sequence))
        for current, following in zip(values, values[1:]):
            _expect(
                following[0].ack_timestamp > current[0].ack_timestamp,
                "nonpositive_binding_window",
                f"resource {resource_id} has simultaneous or reversed ACK windows",
            )

    identity_index = _build_identity_index(identity) if by_resource else None
    windows: list[dict[str, Any]] = []
    for resource_id in sorted(by_resource):
        values = by_resource[resource_id]
        for index, (ack, binding) in enumerate(values):
            final_window = index + 1 == len(values)
            end = (
                truth.episode_end
                if final_window
                else values[index + 1][0].ack_timestamp
            )
            windows.append(
                _evaluate_binding_window(
                    ack,
                    binding,
                    start=ack.ack_timestamp,
                    end=end,
                    end_inclusive=final_window,
                    identity=identity_index,
                    truth=truth,
                    events=events,
                )
            )
    windows.sort(key=lambda item: (item["ack_bus_sequence"], item["resource_id"]))
    return windows


def _evaluate_binding_window(
    ack: _ValidatedAck,
    binding: Mapping[str, Any],
    *,
    start: float,
    end: float,
    end_inclusive: bool,
    identity: _IdentityIndex | None,
    truth: _TruthState,
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    resource_id = str(binding["resource_id"])
    track_id = str(binding["global_track_id"])
    assert identity is not None
    mapping = _identity_mapping_for_window(
        identity,
        global_track_id=track_id,
        start=start,
        end=end,
        end_inclusive=end_inclusive,
    )
    state = _state_window(
        truth,
        resource_id=resource_id,
        truth_target_id=mapping.get("truth_target_id"),
        start=start,
        end=end,
        end_inclusive=end_inclusive,
    )
    window_events = [
        event
        for event in events
        if event.get("resource_id") == resource_id
        and _timestamp_in_window(
            float(event["timestamp"]),
            start=start,
            end=end,
            end_inclusive=end_inclusive,
        )
    ]
    truth_target_id = mapping.get("truth_target_id") if mapping.get("available") else None
    correct_events = (
        []
        if truth_target_id is None
        else [
            event
            for event in window_events
            if event.get("truth_target_id") == truth_target_id
            and float(event["distance_m"]) <= FIVE_METER_THRESHOLD_M
        ]
    )
    other_events = (
        []
        if truth_target_id is None
        else [
            event
            for event in window_events
            if event.get("truth_target_id") != truth_target_id
            and float(event["distance_m"]) <= FIVE_METER_THRESHOLD_M
        ]
    )
    score = _pair_progress_diagnostic(
        ack=ack,
        binding=binding,
        mapping=mapping,
        state=state,
    )
    return {
        "ack_bus_sequence": ack.envelope_sequence,
        "decision_id": ack.decision_id,
        "occurrence_id": ack.occurrence_id,
        "occurrence_index": ack.occurrence_index,
        "adoption_kind": ack.adoption_kind,
        "plan_id": ack.plan_id,
        "plan_version": ack.plan_version,
        "execution_signature_sha256": ack.execution_signature_sha256,
        "resource_id": resource_id,
        "global_track_id": track_id,
        "coalition_id": binding.get("coalition_id"),
        "coalition_version": binding.get("coalition_version"),
        "member_role": binding.get("member_role"),
        "window_start_timestamp": start,
        "window_end_timestamp": end,
        "window_interval": "closed" if end_inclusive else "left_closed_right_open",
        "identity_mapping": mapping,
        "state_window_available": state["available"],
        "state_window_reason": state["reason"],
        "state_sample_count": state["sample_count"],
        "first_state_timestamp": state["first_timestamp"],
        "last_state_timestamp": state["last_timestamp"],
        "start_3d_distance_m": state["start_distance_m"],
        "end_3d_distance_m": state["end_distance_m"],
        "min_3d_distance_m": state["min_distance_m"],
        "distance_progress_m": state["distance_progress_m"],
        "best_distance_progress_m": state["best_distance_progress_m"],
        "assigned_pair_proximity_event_observed": (
            None if truth_target_id is None else bool(correct_events)
        ),
        "assigned_pair_proximity_events": [dict(item) for item in correct_events],
        "other_target_proximity_event_observed": (
            None if truth_target_id is None else bool(other_events)
        ),
        "other_target_proximity_events": [dict(item) for item in other_events],
        "guidance_command_present": binding["guidance_command_present"],
        "guidance_mode": binding["guidance_mode"],
        "guidance_gate_reason": binding["guidance_gate_reason"],
        "control_applied_to_world": binding["control_applied_to_world"],
        "held": binding["held"],
        "d3_learning_evidence": dict(ack.d3_learning_evidence),
        "d4_regional_hint_evidence": dict(ack.d4_regional_hint_evidence),
        "bounded_pair_progress_diagnostic": score,
        "formal_d3_ppo_reward_available": False,
        "formal_d3_ppo_reward": None,
        "formal_d3_ppo_reward_reason": (
            "bounded_pair_progress_is_not_a_formal_d3_ppo_reward"
        ),
        "counterfactual_available": False,
        "counterfactual": None,
        "counterfactual_reason": "same_seed_paired_formal_shadow_unavailable",
        "causal_attribution_available": False,
        "causal_attribution": None,
        "causal_attribution_reason": (
            "controlled_intervention_or_paired_causal_evidence_unavailable"
        ),
    }


def _build_identity_index(
    evaluation: Mapping[str, Any],
) -> _IdentityIndex:
    configuration = _mapping(
        evaluation.get("configuration"), "D2 identity configuration"
    )
    lineage_window = _positive_float(
        configuration.get("lineage_time_window_s"), "lineage_time_window_s"
    )
    by_global_track_id: dict[
        str,
        list[tuple[float, Mapping[str, Any]]],
    ] = defaultdict(list)
    frame_mappings: list[
        tuple[float, tuple[Mapping[str, Any], ...]]
    ] = []
    for raw_frame in _sequence(evaluation.get("frames"), "D2 identity frames"):
        frame = _mapping(raw_frame, "D2 identity frame")
        frame_time = float(frame["frame_timestamp"])
        mappings = tuple(
            _mapping(raw_mapping, "D2 track mapping")
            for raw_mapping in _sequence(
                frame.get("mappings"), "D2 frame mappings"
            )
        )
        frame_mappings.append((frame_time, mappings))
        for item in mappings:
            by_global_track_id[str(item["global_track_id"])].append(
                (frame_time, item)
            )
    return _IdentityIndex(
        lineage_time_window_s=lineage_window,
        evaluation_schema_version=str(evaluation.get("schema_version", "")),
        by_global_track_id={
            track_id: tuple(values)
            for track_id, values in by_global_track_id.items()
        },
        frame_mappings=tuple(frame_mappings),
    )


def _identity_mapping_for_window(
    identity: _IdentityIndex,
    *,
    global_track_id: str,
    start: float,
    end: float,
    end_inclusive: bool,
    allow_evaluator_only_bounded_coast_bridge: bool = False,
) -> dict[str, Any]:
    lineage_window = identity.lineage_time_window_s
    candidates = identity.by_global_track_id.get(global_track_id, ())
    before = [item for item in candidates if item[0] <= start + 1.0e-9]
    if not before:
        return _unavailable_identity("d2_mapping_missing_at_window_start")
    selected_time, selected = max(before, key=lambda item: item[0])
    if start - selected_time > lineage_window + 1.0e-9:
        return _unavailable_identity("d2_mapping_stale_at_window_start")
    relevant = [
        item
        for item in candidates
        if (
            item[0] >= selected_time - 1.0e-9
            and _timestamp_in_window(
                item[0], start=start, end=end, end_inclusive=end_inclusive
            )
        )
        or math.isclose(item[0], selected_time, abs_tol=1.0e-9)
    ]
    uncommitted = [
        (timestamp, item)
        for timestamp, item in relevant
        if item.get("status") == "uncommitted"
    ]
    if uncommitted:
        details = [
            (
                f"frame_timestamp={timestamp:.12g};status=uncommitted;"
                f"reason={item.get('reason') or 'identity_uncommitted'};"
                f"global_track_id={global_track_id}"
            )
            for timestamp, item in uncommitted
        ]
        return _unavailable_identity(
            "d2_identity_uncommitted_in_assignment_window",
            details=details,
            global_track_id=global_track_id,
            source_frame_timestamp=selected_time,
            evidence_frame_count=len(relevant),
            policy=(
                "d2_identity_commitment_window_v2"
                if identity.evaluation_schema_version
                == D2_IDENTITY_EVALUATION_SCHEMA_V2
                else "d2_source_observation_lineage_unique_window_v1"
            ),
        )
    unavailable = [
        (timestamp, item)
        for timestamp, item in relevant
        if item.get("status") != "available"
        or item.get("truth_target_id") is None
        or not item.get("source_observation_ids")
        or not item.get("source_lineage_hashes")
    ]
    if unavailable:
        if allow_evaluator_only_bounded_coast_bridge:
            bridge = _bounded_coast_identity_mapping(
                identity,
                global_track_id=global_track_id,
                start=start,
                end=end,
                end_inclusive=end_inclusive,
                selected_time=selected_time,
            )
            if bridge is not None:
                return bridge
        reasons = sorted(
            {
                str(item.get("reason") or "d2_mapping_unavailable_in_window")
                for _, item in unavailable
            }
        )
        return _unavailable_identity(
            "d2_mapping_unavailable_in_window", details=reasons
        )
    truth_ids = {str(item["truth_target_id"]) for _, item in relevant}
    if len(truth_ids) != 1:
        return _unavailable_identity(
            "d2_mapping_ambiguous_across_window",
            details=sorted(truth_ids),
        )
    truth_target_id = next(iter(truth_ids))
    source_observations = sorted(
        {
            str(value)
            for _, item in relevant
            for value in item.get("source_observation_ids", ())
        }
    )
    lineage_hashes = sorted(
        {
            _normalise_sha256(value)
            for _, item in relevant
            for value in item.get("source_lineage_hashes", ())
        }
    )
    return {
        "available": True,
        "reason": None,
        "global_track_id": global_track_id,
        "truth_target_id": truth_target_id,
        "policy": "d2_source_observation_lineage_unique_window_v1",
        "source_frame_timestamp": selected_time,
        "evidence_frame_count": len(relevant),
        "source_observation_ids": source_observations,
        "source_lineage_hashes": lineage_hashes,
        "online_exposure_allowed": False,
    }


def _bounded_coast_identity_mapping(
    identity: _IdentityIndex,
    *,
    global_track_id: str,
    start: float,
    end: float,
    end_inclusive: bool,
    selected_time: float,
) -> dict[str, Any] | None:
    if (
        identity.evaluation_schema_version
        != D2_IDENTITY_EVALUATION_SCHEMA_V2
    ):
        return None

    scope_frames = [
        (timestamp, mappings)
        for timestamp, mappings in identity.frame_mappings
        if math.isclose(timestamp, selected_time, abs_tol=1.0e-9)
        or (
            timestamp >= selected_time - 1.0e-9
            and _timestamp_in_window(
                timestamp,
                start=start,
                end=end,
                end_inclusive=end_inclusive,
            )
        )
    ]
    if not scope_frames:
        return None

    scoped_track_entries: list[tuple[float, Mapping[str, Any]]] = []
    for timestamp, mappings in scope_frames:
        track_mappings = [
            item
            for item in mappings
            if item.get("global_track_id") == global_track_id
        ]
        if len(track_mappings) != 1:
            return None
        if any(
            item.get("status") in {"uncommitted", "ambiguous"}
            for item in mappings
        ):
            return None
        scoped_track_entries.append((timestamp, track_mappings[0]))

    scoped_track_entries.sort(key=lambda item: item[0])
    if any(
        math.isclose(left[0], right[0], abs_tol=1.0e-9)
        for left, right in zip(
            scoped_track_entries,
            scoped_track_entries[1:],
        )
    ):
        return None

    unavailable_indices = [
        index
        for index, (timestamp, item) in enumerate(scoped_track_entries)
        if item.get("status") == "unavailable"
        and _timestamp_in_window(
            timestamp,
            start=start,
            end=end,
            end_inclusive=end_inclusive,
        )
    ]
    if not unavailable_indices:
        return None
    if any(
        not _bounded_coast_entry_is_valid(
            item,
            global_track_id=global_track_id,
        )
        for _, item in scoped_track_entries
    ):
        return None

    available_truth_ids = {
        str(item["truth_target_id"])
        for _, item in scoped_track_entries
        if item.get("status") == "available"
    }
    if len(available_truth_ids) != 1:
        return None
    truth_target_id = next(iter(available_truth_ids))

    anchor_pairs: list[tuple[float, float]] = []
    max_anchor_gap_s = min(
        identity.lineage_time_window_s,
        D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S,
    )
    for index in unavailable_indices:
        before_index = next(
            (
                candidate
                for candidate in range(index - 1, -1, -1)
                if scoped_track_entries[candidate][1].get("status")
                == "available"
            ),
            None,
        )
        after_index = next(
            (
                candidate
                for candidate in range(
                    index + 1,
                    len(scoped_track_entries),
                )
                if scoped_track_entries[candidate][1].get("status")
                == "available"
            ),
            None,
        )
        if before_index is None or after_index is None:
            return None
        before_time = scoped_track_entries[before_index][0]
        after_time = scoped_track_entries[after_index][0]
        if (
            after_time - before_time
            > max_anchor_gap_s + 1.0e-9
        ):
            return None
        pair = (before_time, after_time)
        if pair not in anchor_pairs:
            anchor_pairs.append(pair)

    for _, mappings in scope_frames:
        for item in mappings:
            if item.get("global_track_id") == global_track_id:
                continue
            candidates = _bounded_coast_string_sequence(
                item.get("candidate_truth_target_ids")
            )
            if candidates is None:
                return None
            if (
                item.get("truth_target_id") == truth_target_id
                or truth_target_id in candidates
            ):
                return None

    available_entries = [
        item
        for _, item in scoped_track_entries
        if item.get("status") == "available"
    ]
    source_observations = sorted(
        {
            value
            for item in available_entries
            for value in (
                _bounded_coast_string_sequence(
                    item.get("source_observation_ids")
                )
                or ()
            )
        }
    )
    lineage_hashes = sorted(
        {
            _normalise_sha256(value)
            for item in available_entries
            for value in (
                _bounded_coast_string_sequence(
                    item.get("source_lineage_hashes")
                )
                or ()
            )
        }
    )
    anchor_timestamps = sorted(
        {timestamp for pair in anchor_pairs for timestamp in pair}
    )
    return {
        "available": True,
        "reason": None,
        "global_track_id": global_track_id,
        "truth_target_id": truth_target_id,
        "policy": D2_EVALUATOR_ONLY_BOUNDED_COAST_BRIDGE_POLICY,
        "source_frame_timestamp": selected_time,
        "evidence_frame_count": len(scoped_track_entries),
        "source_observation_ids": source_observations,
        "source_lineage_hashes": lineage_hashes,
        "bridged_frame_count": len(unavailable_indices),
        "bridge_anchor_timestamps": anchor_timestamps,
        "bridge_anchor_pairs": [
            {
                "before_frame_timestamp": before,
                "after_frame_timestamp": after,
                "anchor_gap_s": after - before,
            }
            for before, after in anchor_pairs
        ],
        "lineage_time_window_s": identity.lineage_time_window_s,
        "max_anchor_gap_s": max_anchor_gap_s,
        "evaluator_only": True,
        "online_exposure_allowed": False,
    }


def _bounded_coast_entry_is_valid(
    item: Mapping[str, Any],
    *,
    global_track_id: str,
) -> bool:
    if (
        item.get("global_track_id") != global_track_id
        or item.get("lifecycle_state") != "confirmed"
    ):
        return False
    status = item.get("status")
    if status == "available":
        truth_target_id = item.get("truth_target_id")
        candidates = _bounded_coast_string_sequence(
            item.get("candidate_truth_target_ids")
        )
        observations = _bounded_coast_string_sequence(
            item.get("source_observation_ids")
        )
        lineage = _bounded_coast_string_sequence(
            item.get("source_lineage_hashes")
        )
        return bool(
            item.get("association_state") == "matched"
            and isinstance(truth_target_id, str)
            and truth_target_id
            and candidates == (truth_target_id,)
            and observations
            and lineage
            and all(_SHA256_RE.fullmatch(value.lower()) for value in lineage)
        )
    if status != "unavailable":
        return False
    reason = "track_not_assigned_in_frame"
    return bool(
        item.get("association_state") == "unmatched"
        and item.get("reason") == reason
        and _bounded_coast_string_sequence(item.get("unavailable_reasons"))
        == (reason,)
        and item.get("truth_target_id") is None
        and _bounded_coast_string_sequence(
            item.get("candidate_truth_target_ids")
        )
        == ()
        and _bounded_coast_string_sequence(item.get("source_observation_ids"))
        == ()
        and _bounded_coast_string_sequence(item.get("source_lineage_hashes"))
        == ()
        and all(
            isinstance(item.get(name), int)
            and not isinstance(item.get(name), bool)
            and item.get(name) == 0
            for name in (
                "evidence_count",
                "unique_lineage_count",
                "labeled_evidence_count",
                "replayed_lineage_count",
            )
        )
    )


def _bounded_coast_string_sequence(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return None
    if any(not isinstance(item, str) or not item for item in value):
        return None
    return tuple(value)


def _unavailable_identity(
    reason: str,
    *,
    details: Sequence[str] = (),
    global_track_id: str | None = None,
    source_frame_timestamp: float | None = None,
    evidence_frame_count: int = 0,
    policy: str = "d2_source_observation_lineage_unique_window_v1",
) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "details": list(details),
        "global_track_id": global_track_id,
        "truth_target_id": None,
        "policy": policy,
        "source_frame_timestamp": source_frame_timestamp,
        "evidence_frame_count": evidence_frame_count,
        "source_observation_ids": [],
        "source_lineage_hashes": [],
        "online_exposure_allowed": False,
    }


def _state_window(
    truth: _TruthState,
    *,
    resource_id: str,
    truth_target_id: Any,
    start: float,
    end: float,
    end_inclusive: bool,
) -> dict[str, Any]:
    if truth_target_id is None:
        return _unavailable_state("identity_mapping_unavailable")
    try:
        resource_index = _resource_index(resource_id, truth.resource_count)
    except RuntimePlanOutcomeJoinError as exc:
        return _unavailable_state(exc.code)
    if str(truth_target_id) not in truth.intruder_ids:
        return _unavailable_state("mapped_truth_target_absent_from_state")
    target_index = truth.intruder_ids.index(str(truth_target_id))
    tolerance = max(1.0e-9, truth.physics_dt_s * 1.0e-6)
    if start < truth.timestamps[0] - tolerance or end > truth.timestamps[-1] + tolerance:
        return _unavailable_state("state_timeline_does_not_cover_window")
    if end_inclusive:
        mask = (truth.timestamps >= start - tolerance) & (
            truth.timestamps <= end + tolerance
        )
    else:
        mask = (truth.timestamps >= start - tolerance) & (
            truth.timestamps < end - tolerance
        )
    indices = np.flatnonzero(mask)
    if indices.size < 2:
        return _unavailable_state("state_window_has_fewer_than_two_samples")
    sample_times = truth.timestamps[indices]
    if sample_times[0] - start > truth.physics_dt_s + tolerance:
        return _unavailable_state("state_window_start_sample_missing")
    expected_last_gap = end - sample_times[-1]
    if expected_last_gap > truth.physics_dt_s + tolerance:
        return _unavailable_state("state_window_end_sample_missing")
    delta = (
        truth.interceptor_state[indices, resource_index, :3]
        - truth.intruder_state[indices, target_index, :3]
    )
    distances = np.linalg.norm(delta, axis=1)
    if not np.all(np.isfinite(distances)):
        return _unavailable_state("state_window_distance_nonfinite")
    start_distance = float(distances[0])
    end_distance = float(distances[-1])
    minimum = float(np.min(distances))
    return {
        "available": True,
        "reason": None,
        "sample_count": int(indices.size),
        "first_timestamp": float(sample_times[0]),
        "last_timestamp": float(sample_times[-1]),
        "start_distance_m": start_distance,
        "end_distance_m": end_distance,
        "min_distance_m": minimum,
        "distance_progress_m": start_distance - end_distance,
        "best_distance_progress_m": start_distance - minimum,
    }


def _unavailable_state(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "reason": reason,
        "sample_count": 0,
        "first_timestamp": None,
        "last_timestamp": None,
        "start_distance_m": None,
        "end_distance_m": None,
        "min_distance_m": None,
        "distance_progress_m": None,
        "best_distance_progress_m": None,
    }


def _pair_progress_diagnostic(
    *,
    ack: _ValidatedAck,
    binding: Mapping[str, Any],
    mapping: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    reason = None
    if not ack.accepted:
        reason = "runtime_ack_not_accepted"
    elif not binding.get("guidance_command_present"):
        reason = "d7_binding_not_present"
    elif not binding.get("control_applied_to_world"):
        reason = "d7_binding_not_applied_to_world"
    elif binding.get("held") or binding.get("guidance_mode") == "hold":
        reason = "d7_binding_held"
    elif not mapping.get("available"):
        reason = str(mapping.get("reason") or "d2_mapping_unavailable")
    elif not state.get("available"):
        reason = str(state.get("reason") or "state_window_unavailable")
    if reason is not None:
        return {
            "name": RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME,
            "available": False,
            "value": None,
            "reason": reason,
            "range": [-1.0, 1.0],
            "formal_reward": False,
            "causal": False,
            "counterfactual": False,
        }
    start = float(state["start_distance_m"])
    minimum = float(state["min_distance_m"])
    if start <= FIVE_METER_THRESHOLD_M:
        value = 1.0 if minimum <= FIVE_METER_THRESHOLD_M else 0.0
    else:
        denominator = max(start - FIVE_METER_THRESHOLD_M, 1.0e-9)
        value = float(np.clip((start - minimum) / denominator, -1.0, 1.0))
    return {
        "name": RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME,
        "available": True,
        "value": value,
        "reason": None,
        "range": [-1.0, 1.0],
        "formula": "clip((d_start-d_min)/max(d_start-5m,epsilon),-1,1)",
        "formal_reward": False,
        "causal": False,
        "counterfactual": False,
    }


def _distance_at_timestamp(
    truth: _TruthState,
    *,
    timestamp: float,
    resource_index: int,
    target_index: int,
) -> float:
    tolerance = max(1.0e-9, truth.physics_dt_s * 1.0e-6)
    matches = np.flatnonzero(np.abs(truth.timestamps - timestamp) <= tolerance)
    _expect(
        matches.size == 1,
        "proximity_event_timestamp_missing",
        "proximity event timestamp is not an exact truth-state sample",
    )
    index = int(matches[0])
    return float(
        np.linalg.norm(
            truth.interceptor_state[index, resource_index, :3]
            - truth.intruder_state[index, target_index, :3]
        )
    )


def _resource_index(resource_id: str, resource_count: int) -> int:
    match = _RESOURCE_ID_RE.fullmatch(str(resource_id))
    _expect(
        match is not None,
        "unsupported_resource_id",
        f"resource ID does not match the world contract: {resource_id}",
    )
    assert match is not None
    index = int(match.group(1)) - 1
    _expect(
        0 <= index < resource_count,
        "resource_id_out_of_range",
        f"resource ID is outside the truth-state resource array: {resource_id}",
    )
    return index


def _timestamp_in_window(
    timestamp: float,
    *,
    start: float,
    end: float,
    end_inclusive: bool,
) -> bool:
    if timestamp < start - 1.0e-9:
        return False
    if end_inclusive:
        return timestamp <= end + 1.0e-9
    return timestamp < end - 1.0e-9


def _expect_payload_hash(
    payload: Any,
    expected: Any,
    code: str,
) -> None:
    actual = _canonical_payload_sha256(payload)
    _expect(
        actual == _normalise_sha256(expected),
        code,
        f"canonical payload SHA-256 mismatch: expected {expected}, got {actual}",
    )


def _canonical_payload_sha256(payload: Any) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("canonical_payload_encoding_failed", str(exc))
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _verify_file(path: str | Path, expected: Any, name: str) -> str:
    source = Path(path)
    _expect(source.is_file(), "input_file_missing", f"{name} file is missing: {source}")
    expected_digest = _normalise_sha256(expected)
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = f"sha256:{digest.hexdigest()}"
    _expect(
        actual == expected_digest,
        f"{name}_sha256_mismatch",
        f"{name} SHA-256 mismatch: expected {expected_digest}, got {actual}",
    )
    return actual


def _normalise_sha256(value: Any) -> str:
    text = str(value).strip().lower()
    match = _SHA256_RE.fullmatch(text)
    if match is None:
        raise RuntimePlanOutcomeJoinError(
            "invalid_sha256",
            f"expected a SHA-256 hexadecimal digest, got {value!r}",
        )
    return f"sha256:{match.group(1)}"


def _load_json(path: Path, name: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except RuntimePlanOutcomeJoinError:
        raise
    except Exception as exc:
        _fail("json_load_failed", f"cannot load {name}: {exc}")
    return _mapping(payload, name)


def _iter_jsonl(
    path: Path,
    name: str,
    *,
    allow_empty: bool = False,
    empty_code: str = "jsonl_empty",
    reject_online_truth: bool = False,
) -> Iterable[Mapping[str, Any]]:
    record_count = 0
    with path.open("r", encoding="utf-8") as stream:
        lines = enumerate(stream, start=1)
        for line_number, raw in lines:
            record_count += 1
            _expect(
                bool(raw.strip()),
                "jsonl_blank_line",
                f"{name} contains a blank line at {line_number}",
            )
            forbidden_fields: list[str] = []
            object_hook = (
                partial(
                    _unique_truth_free_online_object,
                    forbidden_fields=forbidden_fields,
                )
                if reject_online_truth
                else _unique_object
            )
            try:
                payload = json.loads(
                    raw,
                    object_pairs_hook=object_hook,
                    parse_constant=_reject_json_constant,
                )
            except RuntimePlanOutcomeJoinError:
                raise
            except Exception as exc:
                _fail(
                    "jsonl_load_failed",
                    f"cannot load {name} line {line_number}: {exc}",
                )
            if forbidden_fields:
                _fail(
                    "online_truth_field_present",
                    "online observations contain evaluator-only field "
                    f"{forbidden_fields[0]}",
                )
            yield _mapping(payload, f"{name} line {line_number}")
    _expect(
        allow_empty or record_count > 0,
        empty_code,
        f"{name} contains no records",
    )


def _unique_truth_free_online_object(
    pairs: Iterable[tuple[str, Any]],
    *,
    forbidden_fields: list[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimePlanOutcomeJoinError(
                "duplicate_json_key", f"duplicate JSON object key: {key}"
            )
        result[key] = value
        normalised = str(key).strip().lower().replace("-", "_")
        if normalised in _FORBIDDEN_ONLINE_KEYS:
            forbidden_fields.append(key)
    return result


def _unique_object(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimePlanOutcomeJoinError(
                "duplicate_json_key", f"duplicate JSON object key: {key}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise RuntimePlanOutcomeJoinError(
        "nonfinite_json_number", f"non-finite JSON number is forbidden: {value}"
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", f"{name} must be a JSON object")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail("list_required", f"{name} must be a JSON list")
    return value


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    actual = set(payload)
    _expect(
        actual == expected,
        "object_keys_mismatch",
        f"{name} keys mismatch; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}",
    )


def _required_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    _expect(isinstance(value, str) and bool(value.strip()), "string_required", f"{name} must be a non-empty string")
    return str(value).strip()


def _string_value(value: Any, name: str) -> str:
    _expect(
        isinstance(value, str) and bool(value.strip()),
        "string_required",
        f"{name} must be a non-empty string",
    )
    return str(value).strip()


def _optional_string(value: Any, name: str) -> str | None:
    return None if value is None else _string_value(value, name)


def _strict_bool(value: Any, name: str) -> bool:
    _expect(isinstance(value, bool), "boolean_required", f"{name} must be boolean")
    return bool(value)


def _nonnegative_int(value: Any, name: str) -> int:
    _expect(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0,
        "nonnegative_integer_required",
        f"{name} must be a non-negative integer",
    )
    return int(value)


def _optional_nonnegative_int(value: Any, name: str) -> int | None:
    return None if value is None else _nonnegative_int(value, name)


def _positive_int(value: Any, name: str) -> int:
    result = _nonnegative_int(value, name)
    _expect(result > 0, "positive_integer_required", f"{name} must be positive")
    return result


def _nonnegative_float(value: Any, name: str) -> float:
    _expect(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0,
        "nonnegative_number_required",
        f"{name} must be finite and non-negative",
    )
    return float(value)


def _optional_nonnegative_float(value: Any, name: str) -> float | None:
    return None if value is None else _nonnegative_float(value, name)


def _positive_float(value: Any, name: str) -> float:
    result = _nonnegative_float(value, name)
    _expect(result > 0.0, "positive_number_required", f"{name} must be positive")
    return result


def _format_metric(value: Any) -> str:
    return "-" if value is None else f"{float(value):.4f}"


def _format_bool(value: Any) -> str:
    if value is None:
        return "-"
    return "是" if value else "否"


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _write_text_atomic(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _expect(condition: bool, code: str, message: str) -> None:
    if not condition:
        _fail(code, message)


def _fail(code: str, message: str) -> None:
    raise RuntimePlanOutcomeJoinError(code, message)


__all__ = [
    "ASSIGNMENT_PLAN_ACK_SCHEMA",
    "ASSIGNMENT_PLAN_ACK_TOPIC",
    "D6_EVALUATOR_ONLY_BOUNDED_COAST_MAX_ANCHOR_GAP_S",
    "FIVE_METER_THRESHOLD_M",
    "GUIDANCE_COMMAND_TOPIC",
    "HashedArtifact",
    "RUNTIME_PLAN_OUTCOME_DIAGNOSTIC_NAME",
    "RUNTIME_PLAN_OUTCOME_INPUT_SCHEMA_VERSION",
    "RUNTIME_PLAN_OUTCOME_JOIN_DATE",
    "RUNTIME_PLAN_OUTCOME_JOIN_SCHEMA_VERSION",
    "RuntimePlanOutcomeJoinError",
    "RuntimePlanOutcomeJoinInputs",
    "evaluate_runtime_plan_outcomes",
    "load_runtime_plan_outcome_join_inputs",
    "render_runtime_plan_outcome_join_markdown",
    "write_runtime_plan_outcome_join_report",
]
