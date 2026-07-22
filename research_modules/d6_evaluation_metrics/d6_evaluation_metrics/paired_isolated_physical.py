"""Strict read-only evaluation of paired isolated physical rollouts.

This consumer is deliberately separate from production runtime-ACK auditing.
It verifies two independently executed point-mass worlds that share only a
frozen initial state and exogenous schedules.  The result is a descriptive
paired isolated simulation comparison.  It is not causal or counterfactual
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence


PAIRED_ISOLATED_PHYSICAL_INPUT_SCHEMA_VERSION = (
    "d6.paired-isolated-physical-inputs.v1"
)
PAIRED_ISOLATED_PHYSICAL_SIDECAR_SCHEMA_VERSION = (
    "d6.paired-isolated-physical-evaluation.v1"
)
PAIRED_ISOLATED_PHYSICAL_OUTPUT_MANIFEST_SCHEMA_VERSION = (
    "d6.paired-isolated-physical-output-manifest.v1"
)
PAIRED_ISOLATED_PHYSICAL_EVALUATION_DATE = "2026-07-22"
PAIRED_ISOLATED_COMPARISON_SCOPE = "paired_isolated_simulation_comparison"

ARM_EPISODE_MANIFEST_SCHEMA = "scalable3d-isolated-arm-episode-manifest-v1"
INITIAL_STATE_SCHEMA = "scalable3d-paired-initial-state-v1"
SENSOR_SCHEDULE_SCHEMA = "scalable3d-exogenous-sensor-schedule-v1"
COMMUNICATION_SCHEDULE_SCHEMA = (
    "scalable3d-exogenous-communication-schedule-v1"
)
FAULT_SCHEDULE_SCHEMA = "scalable3d-exogenous-fault-schedule-v1"
D3_PLAN_RECORD_SCHEMA = "d3.isolated-plan-publication.v1"
D3_PLAN_PAYLOAD_SCHEMA = "assignment_plan_v2"
ISOLATED_PLAN_CONSUMPTION_SCHEMA = (
    "d3.isolated-plan-consumption-confirmation.v1"
)
ISOLATED_PLAN_CONSUMPTION_SCOPE = "paired_isolated_simulation_only"
D7_COMMAND_LINEAGE_SCHEMA = "d7.isolated-command-lineage.v1"
WORLD_APPLICATION_SCHEMA = "scalable3d-isolated-world-application.v1"
OFFLINE_IDENTITY_SCHEMA = "d6.paired-isolated-offline-identity.v1"
OFFLINE_TRUTH_STATE_SCHEMA = "scalable3d-offline-truth-state-sample.v1"
D4_ISOLATED_PHYSICAL_ADOPTION_SCHEMA = (
    "scalable3d-d4-isolated-physical-adoption-v1"
)
D4_DEGRADED_SCENARIO_LINEAGE_SCHEMA = (
    "d4-region-resource-degraded-scenario-lineage-v1"
)
D4_ISOLATED_CANDIDATE_GATE_SCHEMA = (
    "d4-region-resource-isolated-candidate-gate-v1"
)
D4_ISOLATED_PLAN_ACK_SCHEMA = (
    "d4-region-resource-isolated-plan-consumption-ack-v1"
)
D4_ISOLATED_ADOPTION_EVIDENCE_SCHEMA = (
    "d4-region-resource-isolated-adoption-evidence-v1"
)

FIVE_METER_THRESHOLD_M = 5.0
MINIMUM_CONTROL_CYCLE_COUNT = 2

_SHA256_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
_SHARED_ARTIFACT_NAMES = (
    "initial_state",
    "sensor_schedule",
    "communication_schedule",
    "fault_schedule",
)
_REQUIRED_ARM_ARTIFACT_NAMES = (
    "episode_manifest",
    "assignment_plans",
    "isolated_plan_consumption",
    "d7_command_lineage",
    "world_applications",
    "offline_truth_identity",
    "offline_truth_state",
)
_OPTIONAL_ARM_ARTIFACT_NAMES = ("d4_adoption_evidence",)
_D4_DEGRADED_INTERVENTION_KINDS = frozenset(
    {"center_failed", "center_and_secondary_failed", "active_risk"}
)
_D4_ADOPTION_RECORD_KEYS = frozenset(
    {
        "arm_kind",
        "region_id",
        "intervention_kind",
        "available",
        "reason",
        "source_plan",
        "applied_plan",
        "scenario_lineage",
        "candidate_gate",
        "plan_consumption_ack",
        "adoption_evidence",
        "schema_version",
    }
)
_D4_PLAN_KEYS = frozenset(
    {
        "timestamp",
        "plan_id",
        "plan_version",
        "created_at",
        "assignment_count",
        "assignments",
        "unassigned_global_track_ids",
        "metadata",
    }
)
_D4_PLAN_METADATA_BASE_KEYS = frozenset(
    {
        "active_plan_owner",
        "owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
        "current_plan_id",
        "current_plan_version",
        "identity_created_at_s",
        "last_evaluated_at_s",
        "execution_signature_changed",
        "plan_refresh_only",
        "evaluation_refresh_only",
        "plan_published",
    }
)
_D4_APPLIED_PLAN_METADATA_KEYS = _D4_PLAN_METADATA_BASE_KEYS | frozenset(
    {
        "d4_isolated_execution_source",
        "d4_candidate_payload_sha256",
        "d4_source_lineage_sha256",
    }
)
_D4_ASSIGNMENT_KEYS = frozenset(
    {
        "resource_id",
        "global_track_id",
        "coalition_id",
        "coalition_version",
        "member_role",
        "owner_node_id",
        "regional_owner_layer",
        "regional_region_id",
        "regional_epoch",
        "regional_commit_mode",
    }
)
_D4_SCENARIO_LINEAGE_KEYS = frozenset(
    {
        "scenario_kind",
        "scenario_id",
        "scenario_version",
        "seed",
        "arm_id",
        "cycle_index",
        "region_id",
        "source_timestamp_s",
        "scenario_config_sha256",
        "initial_state_sha256",
        "communication_schedule_sha256",
        "fault_schedule_sha256",
        "source_snapshot_payload_sha256",
        "formal_decision_payload_sha256",
        "source_plan_payload_sha256",
        "candidate_gate_payload_sha256",
        "isolated_simulation_only",
        "nominal_evidence",
        "schema",
    }
)
_D4_CANDIDATE_GATE_KEYS = frozenset(
    {
        "candidate_considered",
        "candidate_id",
        "candidate_payload_sha256",
        "candidate_confidence",
        "minimum_confidence",
        "candidate_ood_passed",
        "candidate_latency_ms",
        "candidate_latency_limit_ms",
        "candidate_finite",
        "candidate_failure_gate_passed",
        "candidate_safety_projection_passed",
        "gate_pass",
        "rule_fallback",
        "rejection_reasons",
        "isolated_simulation_only",
        "production_authority",
        "schema",
    }
)
_D4_PLAN_ACK_KEYS = frozenset(
    {
        "ack_id",
        "source_lineage_sha256",
        "arm_id",
        "cycle_index",
        "acknowledged_at_s",
        "accepted",
        "status_code",
        "source_plan_id",
        "source_plan_version",
        "applied_plan_id",
        "applied_plan_version",
        "applied_plan_payload_sha256",
        "execution_binding_sha256",
        "execution_source",
        "owner_layer",
        "owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
        "assignment_count",
        "control_applied_binding_count",
        "fully_consumed_by_isolated_world",
        "network_partition_observed",
        "isolated_simulation_only",
        "production_runtime_ack",
        "schema",
    }
)
_D4_ADOPTION_EVIDENCE_KEYS = frozenset(
    {
        "code",
        "reason",
        "scenario_kind",
        "scenario_lineage_sha256",
        "scenario_validated",
        "candidate_considered",
        "gate_pass",
        "new_execution_plan_applied",
        "evaluation_refresh_applied",
        "rule_fallback",
        "isolated_plan_consumption_ack_available",
        "isolated_candidate_adoption_available",
        "adoption_kind",
        "source_plan_id",
        "source_plan_version",
        "applied_plan_id",
        "applied_plan_version",
        "owner_layer",
        "owner_node_id",
        "authority_epoch",
        "lease_expires_at_s",
        "ack_id",
        "ack_timestamp_s",
        "candidate_gate_rejection_reasons",
        "rejection_reasons",
        "isolated_simulation_only",
        "production_runtime_ack",
        "physical_outcome_available",
        "paired_non_degradation_available",
        "counterfactual_available",
        "causal_effect_available",
        "degradation_effectiveness_claim_allowed",
        "ppo_enabled",
        "assist_enabled",
        "authority_enabled",
        "rule_fallback_enabled",
        "schema",
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


class PairedIsolatedPhysicalEvaluationError(RuntimeError):
    """Stable fail-closed validation error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True, slots=True)
class PairedPhysicalArtifact:
    """One explicit artifact and its caller-supplied SHA-256."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "sha256", _normalise_sha256(self.sha256))

    def resolved(self) -> "PairedPhysicalArtifact":
        return PairedPhysicalArtifact(self.path.expanduser().resolve(), self.sha256)

    def to_dict(self) -> dict[str, str]:
        return {"path": str(self.path), "sha256": self.sha256}

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: Path | None,
        context: str,
    ) -> "PairedPhysicalArtifact":
        _require_exact_keys(payload, {"path", "sha256"}, context)
        path = Path(_required_string(payload, "path", context))
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        return cls(path=path, sha256=str(payload.get("sha256", "")))


@dataclass(frozen=True, slots=True)
class IsolatedArmArtifacts:
    """All immutable inputs for one isolated world."""

    episode_manifest: PairedPhysicalArtifact
    assignment_plans: PairedPhysicalArtifact
    isolated_plan_consumption: PairedPhysicalArtifact
    d7_command_lineage: PairedPhysicalArtifact
    world_applications: PairedPhysicalArtifact
    offline_truth_identity: PairedPhysicalArtifact
    offline_truth_state: PairedPhysicalArtifact
    d4_adoption_evidence: PairedPhysicalArtifact | None = None

    def __post_init__(self) -> None:
        for name in _REQUIRED_ARM_ARTIFACT_NAMES:
            if not isinstance(getattr(self, name), PairedPhysicalArtifact):
                raise TypeError(f"{name} must be a PairedPhysicalArtifact")
        if self.d4_adoption_evidence is not None and not isinstance(
            self.d4_adoption_evidence, PairedPhysicalArtifact
        ):
            raise TypeError(
                "d4_adoption_evidence must be a PairedPhysicalArtifact or None"
            )

    @property
    def declared_artifact_names(self) -> tuple[str, ...]:
        """Return only artifacts explicitly bound by the caller."""

        optional = (
            _OPTIONAL_ARM_ARTIFACT_NAMES
            if self.d4_adoption_evidence is not None
            else ()
        )
        return _REQUIRED_ARM_ARTIFACT_NAMES + optional

    def resolved(self) -> "IsolatedArmArtifacts":
        return IsolatedArmArtifacts(
            **{
                name: getattr(self, name).resolved()
                for name in self.declared_artifact_names
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name).to_dict()
            for name in self.declared_artifact_names
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: Path | None,
        context: str,
    ) -> "IsolatedArmArtifacts":
        keys = set(payload)
        required = set(_REQUIRED_ARM_ARTIFACT_NAMES)
        allowed = required | set(_OPTIONAL_ARM_ARTIFACT_NAMES)
        _expect(
            required.issubset(keys) and keys.issubset(allowed),
            "arm_artifact_declaration_invalid",
            (
                f"{context} must contain all required artifacts and only the "
                "supported optional D4 artifact"
            ),
        )
        return cls(
            **{
                name: PairedPhysicalArtifact.from_mapping(
                    _mapping(payload.get(name), f"{context}.{name}"),
                    base_dir=base_dir,
                    context=f"{context}.{name}",
                )
                for name in _REQUIRED_ARM_ARTIFACT_NAMES
            },
            **{
                name: PairedPhysicalArtifact.from_mapping(
                    _mapping(payload.get(name), f"{context}.{name}"),
                    base_dir=base_dir,
                    context=f"{context}.{name}",
                )
                for name in _OPTIONAL_ARM_ARTIFACT_NAMES
                if name in payload
            }
        )


@dataclass(frozen=True, slots=True)
class PairedIsolatedEpisodeInputs:
    """One seed with shared exogenous inputs and two isolated arms."""

    pair_id: str
    seed: int
    initial_state: PairedPhysicalArtifact
    sensor_schedule: PairedPhysicalArtifact
    communication_schedule: PairedPhysicalArtifact
    fault_schedule: PairedPhysicalArtifact
    control: IsolatedArmArtifacts
    treatment: IsolatedArmArtifacts

    def __post_init__(self) -> None:
        if not self.pair_id:
            raise ValueError("pair_id must be non-empty")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise TypeError("seed must be an integer")
        for name in _SHARED_ARTIFACT_NAMES:
            if not isinstance(getattr(self, name), PairedPhysicalArtifact):
                raise TypeError(f"{name} must be a PairedPhysicalArtifact")
        if not isinstance(self.control, IsolatedArmArtifacts):
            raise TypeError("control must be IsolatedArmArtifacts")
        if not isinstance(self.treatment, IsolatedArmArtifacts):
            raise TypeError("treatment must be IsolatedArmArtifacts")

    def resolved(self) -> "PairedIsolatedEpisodeInputs":
        return PairedIsolatedEpisodeInputs(
            pair_id=self.pair_id,
            seed=self.seed,
            **{
                name: getattr(self, name).resolved()
                for name in _SHARED_ARTIFACT_NAMES
            },
            control=self.control.resolved(),
            treatment=self.treatment.resolved(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "seed": self.seed,
            "shared_artifacts": {
                name: getattr(self, name).to_dict()
                for name in _SHARED_ARTIFACT_NAMES
            },
            "arms": {
                "control": self.control.to_dict(),
                "treatment": self.treatment.to_dict(),
            },
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: Path | None,
    ) -> "PairedIsolatedEpisodeInputs":
        _require_exact_keys(
            payload,
            {"pair_id", "seed", "shared_artifacts", "arms"},
            "paired episode input",
        )
        shared = _mapping(payload.get("shared_artifacts"), "shared_artifacts")
        _require_exact_keys(
            shared,
            set(_SHARED_ARTIFACT_NAMES),
            "shared_artifacts",
        )
        arms = _mapping(payload.get("arms"), "arms")
        _require_exact_keys(arms, {"control", "treatment"}, "arms")
        return cls(
            pair_id=_required_string(payload, "pair_id", "paired episode input"),
            seed=_integer(payload.get("seed"), "paired episode seed"),
            **{
                name: PairedPhysicalArtifact.from_mapping(
                    _mapping(shared.get(name), f"shared_artifacts.{name}"),
                    base_dir=base_dir,
                    context=f"shared_artifacts.{name}",
                )
                for name in _SHARED_ARTIFACT_NAMES
            },
            control=IsolatedArmArtifacts.from_mapping(
                _mapping(arms.get("control"), "arms.control"),
                base_dir=base_dir,
                context="arms.control",
            ),
            treatment=IsolatedArmArtifacts.from_mapping(
                _mapping(arms.get("treatment"), "arms.treatment"),
                base_dir=base_dir,
                context="arms.treatment",
            ),
        )


@dataclass(frozen=True, slots=True)
class PairedIsolatedPhysicalInputs:
    """Versioned top-level input specification."""

    evaluation_id: str
    pairs: tuple[PairedIsolatedEpisodeInputs, ...]
    schema_version: str = PAIRED_ISOLATED_PHYSICAL_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_ISOLATED_PHYSICAL_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported paired isolated physical input schema")
        if not self.evaluation_id:
            raise ValueError("evaluation_id must be non-empty")
        object.__setattr__(self, "pairs", tuple(self.pairs))
        if not self.pairs:
            raise ValueError("at least one paired episode is required")
        if any(not isinstance(item, PairedIsolatedEpisodeInputs) for item in self.pairs):
            raise TypeError("pairs must contain PairedIsolatedEpisodeInputs")
        pair_ids = [item.pair_id for item in self.pairs]
        seeds = [item.seed for item in self.pairs]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("pair_id values must be unique")
        if len(seeds) != len(set(seeds)):
            raise ValueError("seed values must be unique")

    def resolved(self) -> "PairedIsolatedPhysicalInputs":
        return PairedIsolatedPhysicalInputs(
            evaluation_id=self.evaluation_id,
            pairs=tuple(item.resolved() for item in self.pairs),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_id": self.evaluation_id,
            "pairs": [item.to_dict() for item in self.pairs],
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        base_dir: Path | None = None,
    ) -> "PairedIsolatedPhysicalInputs":
        _require_exact_keys(
            payload,
            {"schema_version", "evaluation_id", "pairs"},
            "paired isolated physical input specification",
        )
        _expect(
            payload.get("schema_version")
            == PAIRED_ISOLATED_PHYSICAL_INPUT_SCHEMA_VERSION,
            "unsupported_input_schema",
            "paired isolated physical input schema is unsupported",
        )
        pairs = _sequence(payload.get("pairs"), "input pairs")
        return cls(
            evaluation_id=_required_string(
                payload,
                "evaluation_id",
                "paired isolated physical input specification",
            ),
            pairs=tuple(
                PairedIsolatedEpisodeInputs.from_mapping(
                    _mapping(item, f"input pair {index}"),
                    base_dir=base_dir,
                )
                for index, item in enumerate(pairs)
            ),
        )


@dataclass(frozen=True, slots=True)
class _Plan:
    plan_id: str
    plan_version: int
    payload_sha256: str
    published_at_s: float
    assignments: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _Consumption:
    consumption_id: str
    cycle_index: int
    consumed_at_s: float
    accepted: bool
    plan: _Plan


@dataclass(frozen=True, slots=True)
class _Command:
    command_id: str
    cycle_index: int
    issued_at_s: float
    consumption_id: str
    plan_id: str
    plan_version: int
    plan_payload_sha256: str
    resource_id: str
    global_track_id: str
    command_payload_sha256: str
    control_applied_to_world: bool
    world_application_id: str | None


@dataclass(frozen=True, slots=True)
class _WorldApplication:
    world_application_id: str
    cycle_index: int
    applied_at_s: float
    command_id: str
    command_payload_sha256: str
    resource_id: str
    global_track_id: str
    hard_constraint_violation_count: int


@dataclass(frozen=True, slots=True)
class _TruthSample:
    timestamp_s: float
    interceptor_positions: Mapping[str, tuple[float, float, float]]
    target_positions: Mapping[str, tuple[float, float, float]]


def load_paired_isolated_physical_inputs(
    path: str | Path,
    *,
    expected_sha256: str,
) -> PairedIsolatedPhysicalInputs:
    """Load an externally hash-bound specification with relative paths."""

    source = Path(path).expanduser().resolve()
    _verify_file(source, expected_sha256, "input_specification")
    payload = _load_json(source, "paired isolated physical input specification")
    return PairedIsolatedPhysicalInputs.from_mapping(
        payload,
        base_dir=source.parent,
    )


def evaluate_paired_isolated_physical(
    inputs: PairedIsolatedPhysicalInputs,
    *,
    evaluation_date: str = PAIRED_ISOLATED_PHYSICAL_EVALUATION_DATE,
) -> dict[str, Any]:
    """Evaluate all pairs without mutating any producer artifact."""

    _expect(
        evaluation_date == PAIRED_ISOLATED_PHYSICAL_EVALUATION_DATE,
        "evaluation_date_mismatch",
        f"evaluation_date must be {PAIRED_ISOLATED_PHYSICAL_EVALUATION_DATE}",
    )
    resolved = inputs.resolved()
    before = _verify_and_snapshot_inputs(resolved)
    pair_results = [
        _evaluate_pair(item, source_hashes=before[item.pair_id])
        for item in resolved.pairs
    ]
    after = _snapshot_inputs(resolved)
    _expect(
        before == after,
        "input_mutated_during_evaluation",
        "one or more input artifacts changed during read-only evaluation",
    )
    aggregate = _aggregate_pair_results(pair_results)
    payload: dict[str, Any] = {
        "schema_version": PAIRED_ISOLATED_PHYSICAL_SIDECAR_SCHEMA_VERSION,
        "evaluation_date": evaluation_date,
        "evaluation_id": resolved.evaluation_id,
        "evaluation_mode": "offline_read_only_fail_closed",
        "comparison_scope": PAIRED_ISOLATED_COMPARISON_SCOPE,
        "five_meter_threshold_m": FIVE_METER_THRESHOLD_M,
        "pair_results": pair_results,
        "aggregate": aggregate,
        "claim_boundary": {
            "production_runtime_ack_evaluated": False,
            "isolated_plan_consumption_confirmation_only": True,
            "paired_isolated_simulation_comparison": True,
            "degraded_paired_physical_comparison_is_descriptive_only": True,
            "degradation_effectiveness_claim_allowed": False,
            "counterfactual_claim_allowed": False,
            "causal_claim_allowed": False,
            "reason": (
                "shared_exogenous_schedules_do_not_by_themselves_establish_"
                "counterfactual_or_causal_identification"
            ),
        },
        "audit": {
            "passed": True,
            "fail_closed": True,
            "source_mutation_performed": False,
            "all_artifact_hashes_verified": True,
            "truth_used_offline_only": True,
            "online_truth_use_count": 0,
            "global_track_id_rewrite_count": 0,
            "violation_count": 0,
            "violations": [],
        },
    }
    payload["content_sha256"] = _canonical_payload_sha256(payload)
    return payload


def write_paired_isolated_physical_report(
    inputs: PairedIsolatedPhysicalInputs,
    output_dir: str | Path,
    *,
    evaluation_date: str = PAIRED_ISOLATED_PHYSICAL_EVALUATION_DATE,
) -> dict[str, Path]:
    """Write a deterministic sidecar, Chinese report and checksum manifest."""

    resolved = inputs.resolved()
    root = Path(output_dir).expanduser().resolve()
    input_paths = _all_input_paths(resolved)
    _expect(
        root not in input_paths
        and all(root not in path.parents for path in input_paths),
        "output_overlaps_input_artifact",
        "output directory must not contain or replace an input artifact",
    )
    payload = evaluate_paired_isolated_physical(
        resolved,
        evaluation_date=evaluation_date,
    )
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.", dir=str(root.parent))
    )
    try:
        sidecar = temporary / "paired_isolated_physical_sidecar.json"
        markdown = temporary / "paired_isolated_physical_report_cn.md"
        manifest = temporary / "provenance_manifest.json"
        checksums = temporary / "SHA256SUMS"
        _write_json(sidecar, payload)
        _write_text(markdown, render_paired_isolated_physical_markdown(payload))
        manifest_payload = {
            "schema_version": (
                PAIRED_ISOLATED_PHYSICAL_OUTPUT_MANIFEST_SCHEMA_VERSION
            ),
            "evaluation_id": payload["evaluation_id"],
            "evaluation_date": payload["evaluation_date"],
            "comparison_scope": payload["comparison_scope"],
            "sidecar_content_sha256": payload["content_sha256"],
            "artifacts": {
                sidecar.name: _sha256_file(sidecar),
                markdown.name: _sha256_file(markdown),
            },
            "source_artifact_set_sha256": _canonical_payload_sha256(
                _snapshot_inputs(resolved)
            ),
        }
        _write_json(manifest, manifest_payload)
        checksum_lines = [
            f"{_sha256_file(path)}  {path.name}"
            for path in (sidecar, markdown, manifest)
        ]
        _write_text(checksums, "\n".join(checksum_lines) + "\n")
        if root.exists():
            shutil.rmtree(root)
        temporary.replace(root)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "sidecar": root / sidecar.name,
        "markdown": root / markdown.name,
        "manifest": root / manifest.name,
        "checksums": root / checksums.name,
    }


def render_paired_isolated_physical_markdown(
    payload: Mapping[str, Any],
) -> str:
    """Render the evidence layers and descriptive deltas in Chinese."""

    aggregate = _mapping(payload.get("aggregate"), "aggregate")
    coverage = _mapping(aggregate.get("availability_coverage"), "coverage")
    lines = [
        "# 隔离双臂多周期物理结果评估",
        "",
        "## 结论",
        "",
        (
            f"本次只读核验 {int(aggregate['pair_count'])} 个随机种子。"
            "control 与 treatment 使用同一初始状态和外生传感器、通信、故障日程，"
            "但 episode、world 和状态文件相互隔离。"
        ),
        (
            "结果口径为 paired isolated simulation comparison。隔离计划消费确认"
            "不称为 production runtime ACK，共享外生日程也不自动构成反事实或因果证据。"
        ),
        "",
        "## 可用性",
        "",
        "| 证据层 | 可用 seed | 总 seed |",
        "| --- | ---: | ---: |",
    ]
    for name in (
        "plan_consumption",
        "guidance_lineage",
        "physical_window",
        "d4_degraded_adoption",
        "paired_physical_effect",
        "paired_non_degradation",
        "degraded_paired_physical_comparison",
        "counterfactual",
        "causal",
    ):
        item = _mapping(coverage.get(name), f"coverage.{name}")
        lines.append(
            f"| `{name}` | {int(item['available_pair_count'])} | "
            f"{int(item['total_pair_count'])} |"
        )
    lines.extend(
        [
            "",
            "## 逐 seed 结果",
            "",
            "| seed | 计划消费 | 导引血缘 | 物理窗 | D4降级采用 | 降级配对比较 | control成功 | treatment成功 | 成功差值 | 最近距离差值/m | 硬约束差值 | 错误绑定差值 | 非退化 |",
            "| ---: | :---: | :---: | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
        ]
    )
    for raw_pair in _sequence(payload.get("pair_results"), "pair_results"):
        pair = _mapping(raw_pair, "pair result")
        availability = _mapping(pair.get("availability"), "pair availability")
        arms = _mapping(pair.get("arms"), "pair arms")
        control = _mapping(arms.get("control"), "control arm")
        treatment = _mapping(arms.get("treatment"), "treatment arm")
        control_metrics = _mapping(control.get("metrics"), "control metrics")
        treatment_metrics = _mapping(treatment.get("metrics"), "treatment metrics")
        effect = _mapping(
            availability.get("paired_physical_effect"),
            "paired physical effect",
        )
        delta = effect.get("value") if effect.get("available") else None
        delta_map = delta if isinstance(delta, Mapping) else {}
        non_degradation = _mapping(
            availability.get("paired_non_degradation"),
            "paired non-degradation",
        )
        lines.append(
            "| {seed} | {plan} | {guidance} | {physical} | {d4} | {degraded} | {control_success} | "
            "{treatment_success} | {success_delta} | {distance_delta} | "
            "{hard_delta} | {binding_delta} | {non_degradation} |".format(
                seed=int(pair["seed"]),
                plan=_cn_available(availability["plan_consumption"]),
                guidance=_cn_available(availability["guidance_lineage"]),
                physical=_cn_available(availability["physical_window"]),
                d4=_cn_available(availability["d4_degraded_adoption"]),
                degraded=_cn_available(
                    availability["degraded_paired_physical_comparison"]
                ),
                control_success=_metric(control_metrics.get("success_count")),
                treatment_success=_metric(treatment_metrics.get("success_count")),
                success_delta=_metric(delta_map.get("success_count_delta")),
                distance_delta=_metric(
                    delta_map.get("mean_closest_distance_delta_m")
                ),
                hard_delta=_metric(
                    delta_map.get("hard_constraint_violation_count_delta")
                ),
                binding_delta=_metric(
                    delta_map.get("incorrect_binding_count_delta")
                ),
                non_degradation=(
                    "通过"
                    if non_degradation.get("available")
                    and _mapping(
                        non_degradation.get("value"),
                        "non-degradation value",
                    ).get("overall")
                    else "未通过"
                    if non_degradation.get("available")
                    else "不可用"
                ),
            )
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 计划消费证据仅表示隔离仿真中的计划被读取和接受。它不是生产运行时确认。",
            "- D4 采用证据只证明隔离世界消费了降级计划；空文件表示名义场景不适用。",
            "- 物理成功按北东地坐标三维欧氏距离不大于 5 米判定。",
            "- treatment-control 差值只描述已执行的两套隔离轨迹。",
            "- 降级配对比较仍是描述性隔离仿真比较，不表示降级因果收益。",
            "- 本合同不输出反事实值或因果效应；对应 value 始终为 null，并给出原因。",
            "",
        ]
    )
    return "\n".join(lines)


def _evaluate_pair(
    pair: PairedIsolatedEpisodeInputs,
    *,
    source_hashes: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    shared_payloads = _validate_shared_artifacts(pair)
    _validate_pair_path_isolation(pair)
    arm_results: dict[str, Any] = {}
    arm_internal: dict[str, Mapping[str, Any]] = {}
    for arm_kind, artifacts in (
        ("control", pair.control),
        ("treatment", pair.treatment),
    ):
        result, internal = _evaluate_arm(
            pair,
            arm_kind=arm_kind,
            artifacts=artifacts,
            shared_payloads=shared_payloads,
            source_hashes=source_hashes[arm_kind],
        )
        arm_results[arm_kind] = result
        arm_internal[arm_kind] = internal

    control_manifest = _mapping(
        arm_internal["control"]["manifest"], "control manifest"
    )
    treatment_manifest = _mapping(
        arm_internal["treatment"]["manifest"], "treatment manifest"
    )
    _validate_arm_pair_equivalence(control_manifest, treatment_manifest)
    control_times = arm_internal["control"].get("truth_timestamps")
    treatment_times = arm_internal["treatment"].get("truth_timestamps")
    if control_times is not None and treatment_times is not None:
        _expect(
            control_times == treatment_times,
            "paired_truth_timeline_mismatch",
            f"pair {pair.pair_id} control/treatment truth timelines differ",
        )

    availability = _pair_availability(arm_results)
    return {
        "pair_id": pair.pair_id,
        "seed": pair.seed,
        "scenario_name": control_manifest["scenario_name"],
        "scenario_version": control_manifest["scenario_version"],
        "comparison_scope": PAIRED_ISOLATED_COMPARISON_SCOPE,
        "input_equivalence": {
            "same_seed": True,
            "same_initial_state": True,
            "same_sensor_schedule": True,
            "same_communication_schedule": True,
            "same_fault_schedule": True,
            "isolated_episode_ids": True,
            "isolated_world_ids": True,
            "isolated_arm_artifact_paths": True,
        },
        "source_artifacts": source_hashes,
        "arms": arm_results,
        "availability": availability,
    }


def _evaluate_arm(
    pair: PairedIsolatedEpisodeInputs,
    *,
    arm_kind: str,
    artifacts: IsolatedArmArtifacts,
    shared_payloads: Mapping[str, Mapping[str, Any]],
    source_hashes: Mapping[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(artifacts.episode_manifest.path, f"{arm_kind} manifest")
    _validate_arm_manifest(
        manifest,
        pair=pair,
        arm_kind=arm_kind,
        source_hashes=source_hashes,
        shared_payloads=shared_payloads,
    )
    plans = _load_plans(artifacts.assignment_plans.path)
    consumptions = _load_consumptions(
        artifacts.isolated_plan_consumption.path,
        plans=plans,
    )
    commands = _load_commands(
        artifacts.d7_command_lineage.path,
        consumptions=consumptions,
    )
    applications = _load_world_applications(
        artifacts.world_applications.path,
        manifest=manifest,
        commands=commands,
    )
    plan_layer = _plan_consumption_availability(consumptions)
    guidance_layer = _guidance_availability(
        consumptions,
        commands=commands,
        applications=applications,
        plan_available=bool(plan_layer["available"]),
    )
    d4_layer = _d4_adoption_availability(
        artifacts.d4_adoption_evidence,
        pair=pair,
        arm_kind=arm_kind,
    )

    identity, identity_reason = _load_offline_identity(
        artifacts.offline_truth_identity.path,
        manifest=manifest,
    )
    truth, truth_reason = _load_truth_state(
        artifacts.offline_truth_state.path,
        manifest=manifest,
        initial_state=shared_payloads["initial_state"],
    )
    windows: list[dict[str, Any]] = []
    physical_reason: str | None = None
    if not guidance_layer["available"]:
        physical_reason = "guidance_lineage_unavailable"
    elif identity is None:
        physical_reason = identity_reason
    elif truth is None:
        physical_reason = truth_reason
    else:
        windows, physical_reason = _build_physical_windows(
            consumptions,
            commands=commands,
            applications=applications,
            identity=identity,
            truth=truth,
            episode_end_s=float(manifest["duration_s"]),
        )
    physical_available = physical_reason is None and bool(windows)
    physical_layer = _availability(
        physical_available,
        {
            "binding_window_count": len(windows),
            "all_windows_complete": True,
        }
        if physical_available
        else None,
        None if physical_available else physical_reason or "physical_window_missing",
    )
    metrics = _arm_metrics(
        windows if physical_available else (),
        applications=applications,
        physical_available=physical_available,
        unavailable_reason=physical_layer["reason"],
    )
    result = {
        "arm_kind": arm_kind,
        "episode_id": manifest["episode_id"],
        "world_id": manifest["world_id"],
        "seed": manifest["seed"],
        "isolated_simulation": True,
        "production_runtime_ack_available": False,
        "availability": {
            "plan_consumption": plan_layer,
            "guidance_lineage": guidance_layer,
            "physical_window": physical_layer,
            "d4_degraded_adoption": d4_layer,
        },
        "evidence_counts": {
            "plan_publication_count": len(plans),
            "plan_consumption_confirmation_count": len(consumptions),
            "accepted_plan_consumption_count": sum(
                item.accepted for item in consumptions.values()
            ),
            "d7_command_count": len(commands),
            "control_applied_to_world_count": sum(
                item.control_applied_to_world for item in commands.values()
            ),
            "world_application_count": len(applications),
            "distinct_control_cycle_count": len(
                {item.cycle_index for item in commands.values()}
            ),
            "d4_adoption_region_count": (
                int(_mapping(d4_layer.get("value"), "D4 adoption value").get(
                    "region_count", 0
                ))
                if isinstance(d4_layer.get("value"), Mapping)
                else 0
            ),
            "d4_adoption_available_count": (
                int(_mapping(d4_layer.get("value"), "D4 adoption value").get(
                    "available_count", 0
                ))
                if isinstance(d4_layer.get("value"), Mapping)
                else 0
            ),
        },
        "metrics": metrics,
        "binding_windows": windows,
        "truth_isolation": {
            "verified": True,
            "online_truth_use_count": 0,
            "offline_identity_mapping_used": identity is not None,
            "offline_truth_state_used": truth is not None,
        },
    }
    internal: dict[str, Any] = {
        "manifest": manifest,
        "truth_timestamps": (
            tuple(item.timestamp_s for item in truth) if truth is not None else None
        ),
    }
    return result, internal


def _validate_shared_artifacts(
    pair: PairedIsolatedEpisodeInputs,
) -> dict[str, Mapping[str, Any]]:
    expected_schemas = {
        "initial_state": INITIAL_STATE_SCHEMA,
        "sensor_schedule": SENSOR_SCHEDULE_SCHEMA,
        "communication_schedule": COMMUNICATION_SCHEDULE_SCHEMA,
        "fault_schedule": FAULT_SCHEDULE_SCHEMA,
    }
    payloads: dict[str, Mapping[str, Any]] = {}
    scenario_identity: tuple[str, str] | None = None
    for name in _SHARED_ARTIFACT_NAMES:
        payload = _load_json(getattr(pair, name).path, f"shared {name}")
        _expect(
            payload.get("schema_version") == expected_schemas[name],
            "shared_artifact_schema_mismatch",
            f"pair {pair.pair_id} {name} schema is unsupported",
        )
        _expect(
            _integer(payload.get("seed"), f"shared {name} seed") == pair.seed,
            "shared_artifact_seed_mismatch",
            f"pair {pair.pair_id} {name} seed differs from input spec",
        )
        identity = (
            _required_string(payload, "scenario_name", f"shared {name}"),
            _required_string(payload, "scenario_version", f"shared {name}"),
        )
        if scenario_identity is None:
            scenario_identity = identity
        _expect(
            identity == scenario_identity,
            "shared_artifact_scenario_mismatch",
            f"pair {pair.pair_id} shared scenario identity differs",
        )
        payloads[name] = payload
    _validate_initial_state(payloads["initial_state"])
    return payloads


def _validate_initial_state(payload: Mapping[str, Any]) -> None:
    interceptors = _mapping(payload.get("interceptor_positions_ned_m"), "initial interceptors")
    targets = _mapping(payload.get("target_positions_ned_m"), "initial targets")
    _expect(bool(interceptors), "initial_state_empty", "initial interceptor state is empty")
    _expect(bool(targets), "initial_state_empty", "initial target state is empty")
    for entity_id, position in tuple(interceptors.items()) + tuple(targets.items()):
        _position(position, f"initial state {entity_id}")


def _validate_pair_path_isolation(pair: PairedIsolatedEpisodeInputs) -> None:
    shared_paths = {getattr(pair, name).path for name in _SHARED_ARTIFACT_NAMES}
    control_paths = {
        getattr(pair.control, name).path
        for name in pair.control.declared_artifact_names
    }
    treatment_paths = {
        getattr(pair.treatment, name).path
        for name in pair.treatment.declared_artifact_names
    }
    _expect(
        len(shared_paths) == len(_SHARED_ARTIFACT_NAMES),
        "duplicate_shared_artifact_path",
        f"pair {pair.pair_id} shared artifacts must use distinct files",
    )
    _expect(
        len(control_paths) == len(pair.control.declared_artifact_names)
        and len(treatment_paths) == len(pair.treatment.declared_artifact_names),
        "duplicate_arm_artifact_path",
        f"pair {pair.pair_id} logical arm artifacts must use distinct files",
    )
    _expect(
        control_paths.isdisjoint(treatment_paths),
        "arm_artifact_path_not_isolated",
        f"pair {pair.pair_id} control and treatment files overlap",
    )
    _expect(
        shared_paths.isdisjoint(control_paths | treatment_paths),
        "shared_and_arm_artifact_path_overlap",
        f"pair {pair.pair_id} shared and arm files overlap",
    )


def _validate_arm_manifest(
    manifest: Mapping[str, Any],
    *,
    pair: PairedIsolatedEpisodeInputs,
    arm_kind: str,
    source_hashes: Mapping[str, str],
    shared_payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    required = {
        "schema_version",
        "pair_id",
        "arm_kind",
        "episode_id",
        "world_id",
        "seed",
        "scenario_name",
        "scenario_version",
        "world_schema",
        "bus_schema",
        "duration_s",
        "physics_dt_s",
        "intercept_radius_m",
        "isolated_simulation",
        "truth_isolation_verified",
        "online_truth_use_count",
        "production_runtime_ack_available",
        "shared_artifact_sha256",
        "arm_artifact_sha256",
    }
    _require_exact_keys(manifest, required, f"{arm_kind} episode manifest")
    _expect(
        manifest.get("schema_version") == ARM_EPISODE_MANIFEST_SCHEMA,
        "arm_manifest_schema_mismatch",
        f"{arm_kind} arm manifest schema is unsupported",
    )
    _expect(
        manifest.get("pair_id") == pair.pair_id
        and _integer(manifest.get("seed"), f"{arm_kind} seed") == pair.seed
        and manifest.get("arm_kind") == arm_kind,
        "arm_manifest_pair_identity_mismatch",
        f"{arm_kind} manifest pair/seed/arm identity differs from input spec",
    )
    shared_identity = shared_payloads["initial_state"]
    _expect(
        manifest.get("scenario_name") == shared_identity.get("scenario_name")
        and manifest.get("scenario_version")
        == shared_identity.get("scenario_version"),
        "arm_shared_scenario_identity_mismatch",
        f"{arm_kind} manifest scenario differs from shared artifacts",
    )
    _expect(
        manifest.get("isolated_simulation") is True,
        "arm_not_isolated_simulation",
        f"{arm_kind} manifest does not declare isolated simulation",
    )
    _expect(
        manifest.get("truth_isolation_verified") is True
        and _integer(
            manifest.get("online_truth_use_count"),
            f"{arm_kind} online truth use count",
        )
        == 0,
        "online_truth_isolation_failed",
        f"{arm_kind} manifest does not prove zero online truth use",
    )
    _expect(
        manifest.get("production_runtime_ack_available") is False,
        "production_runtime_ack_impersonation",
        "isolated rollout may not claim production runtime ACK availability",
    )
    _expect(
        manifest.get("world_schema") == "scalable3d-world-v1"
        and manifest.get("bus_schema") == "scalable3d-episode-bus-v1",
        "arm_runtime_schema_mismatch",
        f"{arm_kind} world or bus schema is unsupported",
    )
    _positive_float(manifest.get("duration_s"), f"{arm_kind} duration")
    _positive_float(manifest.get("physics_dt_s"), f"{arm_kind} physics dt")
    _expect(
        math.isclose(
            _positive_float(
                manifest.get("intercept_radius_m"),
                f"{arm_kind} intercept radius",
            ),
            FIVE_METER_THRESHOLD_M,
            abs_tol=1.0e-12,
        ),
        "unsupported_intercept_radius",
        "physical success must use the fixed 5 m threshold",
    )
    shared_hashes = _mapping(
        manifest.get("shared_artifact_sha256"),
        f"{arm_kind} shared artifact hashes",
    )
    arm_hashes = _mapping(
        manifest.get("arm_artifact_sha256"),
        f"{arm_kind} arm artifact hashes",
    )
    _require_exact_keys(
        shared_hashes,
        set(_SHARED_ARTIFACT_NAMES),
        f"{arm_kind} shared artifact hashes",
    )
    expected_arm_hash_names = set(source_hashes) - {"episode_manifest"}
    _expect(
        set(arm_hashes) == expected_arm_hash_names,
        "arm_optional_artifact_declaration_mismatch",
        (
            f"{arm_kind} manifest and input specification declare different "
            "arm artifacts"
        ),
    )
    for name in _SHARED_ARTIFACT_NAMES:
        _expect(
            _normalise_sha256(shared_hashes[name])
            == getattr(pair, name).sha256,
            "arm_shared_artifact_hash_mismatch",
            f"{arm_kind} manifest does not bind shared artifact {name}",
        )
    for name in sorted(expected_arm_hash_names):
        _expect(
            _normalise_sha256(arm_hashes[name]) == source_hashes[name],
            "arm_artifact_hash_mismatch",
            f"{arm_kind} manifest does not bind arm artifact {name}",
        )


def _validate_arm_pair_equivalence(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
) -> None:
    for key in (
        "pair_id",
        "seed",
        "scenario_name",
        "scenario_version",
        "world_schema",
        "bus_schema",
        "duration_s",
        "physics_dt_s",
        "intercept_radius_m",
        "shared_artifact_sha256",
    ):
        _expect(
            control.get(key) == treatment.get(key),
            "paired_arm_contract_mismatch",
            f"control/treatment manifests differ on {key}",
        )
    _expect(
        control.get("episode_id") != treatment.get("episode_id"),
        "paired_episode_not_isolated",
        "control and treatment must have different episode_id values",
    )
    _expect(
        control.get("world_id") != treatment.get("world_id"),
        "paired_world_not_isolated",
        "control and treatment must have different world_id values",
    )


def _load_plans(path: Path) -> dict[tuple[str, int], _Plan]:
    records = _load_jsonl(path, "D3 assignment plans")
    result: dict[tuple[str, int], _Plan] = {}
    latest_version: dict[str, int] = {}
    for index, record in enumerate(records):
        context = f"D3 assignment plan line {index + 1}"
        _require_exact_keys(
            record,
            {"schema_version", "published_at_s", "plan_payload_sha256", "plan"},
            context,
        )
        _expect(
            record.get("schema_version") == D3_PLAN_RECORD_SCHEMA,
            "d3_plan_record_schema_mismatch",
            context,
        )
        _assert_truth_free(record, context)
        plan_payload = _mapping(record.get("plan"), f"{context}.plan")
        _expect(
            plan_payload.get("schema_version") == D3_PLAN_PAYLOAD_SCHEMA,
            "d3_plan_payload_schema_mismatch",
            context,
        )
        plan_id = _required_string(plan_payload, "plan_id", context)
        plan_version = _nonnegative_int(
            plan_payload.get("plan_version"), f"{context} plan_version"
        )
        _nonnegative_float(plan_payload.get("created_at"), f"{context} created_at")
        digest = _canonical_payload_sha256(plan_payload)
        _expect(
            digest == _normalise_sha256(record.get("plan_payload_sha256")),
            "d3_plan_payload_hash_mismatch",
            context,
        )
        assignments = _normalise_assignments(
            plan_payload.get("assignments"),
            context=context,
        )
        key = (plan_id, plan_version)
        _expect(key not in result, "duplicate_d3_plan_identity", context)
        previous = latest_version.get(plan_id)
        _expect(
            previous is None or plan_version > previous,
            "stale_or_repeated_d3_plan_version",
            context,
        )
        latest_version[plan_id] = plan_version
        result[key] = _Plan(
            plan_id=plan_id,
            plan_version=plan_version,
            payload_sha256=digest,
            published_at_s=_nonnegative_float(
                record.get("published_at_s"), f"{context} published_at_s"
            ),
            assignments=assignments,
        )
    return result


def _load_consumptions(
    path: Path,
    *,
    plans: Mapping[tuple[str, int], _Plan],
) -> dict[str, _Consumption]:
    records = _load_jsonl(path, "isolated plan consumption confirmations")
    result: dict[str, _Consumption] = {}
    previous_cycle = -1
    previous_time = -math.inf
    for index, record in enumerate(records):
        context = f"isolated plan consumption line {index + 1}"
        _require_exact_keys(
            record,
            {
                "schema_version",
                "consumption_id",
                "cycle_index",
                "consumed_at_s",
                "evidence_scope",
                "production_runtime_ack",
                "accepted",
                "status_code",
                "plan_id",
                "plan_version",
                "plan_payload_sha256",
                "consumed_assignments_sha256",
            },
            context,
        )
        _expect(
            record.get("schema_version") == ISOLATED_PLAN_CONSUMPTION_SCHEMA,
            "isolated_plan_consumption_schema_mismatch",
            context,
        )
        _expect(
            record.get("evidence_scope") == ISOLATED_PLAN_CONSUMPTION_SCOPE
            and record.get("production_runtime_ack") is False,
            "production_runtime_ack_impersonation",
            "isolated confirmation may not be represented as production runtime ACK",
        )
        _assert_truth_free(record, context)
        consumption_id = _required_string(record, "consumption_id", context)
        _expect(
            consumption_id not in result,
            "duplicate_plan_consumption_id",
            context,
        )
        cycle = _nonnegative_int(record.get("cycle_index"), f"{context} cycle")
        consumed_at = _nonnegative_float(
            record.get("consumed_at_s"), f"{context} consumed_at_s"
        )
        _expect(
            cycle >= previous_cycle and consumed_at >= previous_time,
            "non_monotonic_plan_consumption",
            context,
        )
        previous_cycle = cycle
        previous_time = consumed_at
        plan_id = _required_string(record, "plan_id", context)
        plan_version = _nonnegative_int(
            record.get("plan_version"), f"{context} plan_version"
        )
        plan = plans.get((plan_id, plan_version))
        _expect(plan is not None, "plan_consumption_source_missing", context)
        assert plan is not None
        _expect(
            consumed_at + 1.0e-9 >= plan.published_at_s,
            "plan_consumed_before_publication",
            context,
        )
        _expect(
            _normalise_sha256(record.get("plan_payload_sha256"))
            == plan.payload_sha256,
            "plan_consumption_identity_hash_mismatch",
            context,
        )
        assignments_digest = _canonical_payload_sha256(
            [
                {"resource_id": resource_id, "global_track_id": track_id}
                for resource_id, track_id in plan.assignments
            ]
        )
        _expect(
            _normalise_sha256(record.get("consumed_assignments_sha256"))
            == assignments_digest,
            "consumed_assignments_hash_mismatch",
            context,
        )
        accepted = _strict_bool(record.get("accepted"), f"{context} accepted")
        status = _required_string(record, "status_code", context)
        _expect(
            (accepted and status == "isolated_plan_consumed")
            or (not accepted and status != "isolated_plan_consumed"),
            "plan_consumption_status_mismatch",
            context,
        )
        result[consumption_id] = _Consumption(
            consumption_id=consumption_id,
            cycle_index=cycle,
            consumed_at_s=consumed_at,
            accepted=accepted,
            plan=plan,
        )
    return result


def _load_commands(
    path: Path,
    *,
    consumptions: Mapping[str, _Consumption],
) -> dict[str, _Command]:
    records = _load_jsonl(path, "D7 command lineage")
    result: dict[str, _Command] = {}
    for index, record in enumerate(records):
        context = f"D7 command lineage line {index + 1}"
        _require_exact_keys(
            record,
            {
                "schema_version",
                "command_id",
                "cycle_index",
                "issued_at_s",
                "consumption_id",
                "plan_id",
                "plan_version",
                "plan_payload_sha256",
                "resource_id",
                "global_track_id",
                "command_payload_sha256",
                "command_payload",
                "control_applied_to_world",
                "world_application_id",
            },
            context,
        )
        _expect(
            record.get("schema_version") == D7_COMMAND_LINEAGE_SCHEMA,
            "d7_command_lineage_schema_mismatch",
            context,
        )
        _assert_truth_free(record, context)
        command_id = _required_string(record, "command_id", context)
        _expect(command_id not in result, "duplicate_d7_command_id", context)
        consumption_id = _required_string(record, "consumption_id", context)
        consumption = consumptions.get(consumption_id)
        _expect(
            consumption is not None and consumption.accepted,
            "d7_command_consumption_lineage_mismatch",
            context,
        )
        assert consumption is not None
        plan = consumption.plan
        resource_id = _required_string(record, "resource_id", context)
        global_track_id = _required_string(record, "global_track_id", context)
        _expect(
            (resource_id, global_track_id) in plan.assignments,
            "d7_command_binding_not_in_consumed_plan",
            context,
        )
        _expect(
            record.get("plan_id") == plan.plan_id
            and _nonnegative_int(
                record.get("plan_version"), f"{context} plan_version"
            )
            == plan.plan_version
            and _normalise_sha256(record.get("plan_payload_sha256"))
            == plan.payload_sha256,
            "d7_command_plan_lineage_mismatch",
            context,
        )
        command_payload = _mapping(
            record.get("command_payload"), f"{context} command payload"
        )
        command_hash = _canonical_payload_sha256(command_payload)
        _expect(
            command_hash
            == _normalise_sha256(record.get("command_payload_sha256")),
            "d7_command_payload_hash_mismatch",
            context,
        )
        issued_at = _nonnegative_float(
            record.get("issued_at_s"), f"{context} issued_at_s"
        )
        _expect(
            issued_at + 1.0e-9 >= consumption.consumed_at_s,
            "d7_command_precedes_plan_consumption",
            context,
        )
        applied = _strict_bool(
            record.get("control_applied_to_world"),
            f"{context} control_applied_to_world",
        )
        raw_application_id = record.get("world_application_id")
        _expect(
            (applied and isinstance(raw_application_id, str) and raw_application_id)
            or (not applied and raw_application_id is None),
            "d7_world_application_claim_mismatch",
            context,
        )
        result[command_id] = _Command(
            command_id=command_id,
            cycle_index=_nonnegative_int(
                record.get("cycle_index"), f"{context} cycle"
            ),
            issued_at_s=issued_at,
            consumption_id=consumption_id,
            plan_id=plan.plan_id,
            plan_version=plan.plan_version,
            plan_payload_sha256=plan.payload_sha256,
            resource_id=resource_id,
            global_track_id=global_track_id,
            command_payload_sha256=command_hash,
            control_applied_to_world=applied,
            world_application_id=(str(raw_application_id) if applied else None),
        )
    return result


def _load_world_applications(
    path: Path,
    *,
    manifest: Mapping[str, Any],
    commands: Mapping[str, _Command],
) -> dict[str, _WorldApplication]:
    records = _load_jsonl(path, "world applications")
    result: dict[str, _WorldApplication] = {}
    command_ids: set[str] = set()
    for index, record in enumerate(records):
        context = f"world application line {index + 1}"
        _require_exact_keys(
            record,
            {
                "schema_version",
                "world_application_id",
                "world_id",
                "cycle_index",
                "applied_at_s",
                "command_id",
                "command_payload_sha256",
                "resource_id",
                "global_track_id",
                "control_applied_to_world",
                "hard_constraint_violation_count",
            },
            context,
        )
        _expect(
            record.get("schema_version") == WORLD_APPLICATION_SCHEMA,
            "world_application_schema_mismatch",
            context,
        )
        _assert_truth_free(record, context)
        application_id = _required_string(
            record, "world_application_id", context
        )
        _expect(
            application_id not in result,
            "duplicate_world_application_id",
            context,
        )
        _expect(
            record.get("world_id") == manifest.get("world_id"),
            "world_application_world_mismatch",
            context,
        )
        command_id = _required_string(record, "command_id", context)
        _expect(
            command_id not in command_ids,
            "duplicate_world_application_for_command",
            context,
        )
        command_ids.add(command_id)
        command = commands.get(command_id)
        _expect(
            command is not None,
            "world_application_unknown_command",
            context,
        )
        assert command is not None
        _expect(
            command.control_applied_to_world
            and command.world_application_id == application_id
            and record.get("control_applied_to_world") is True,
            "world_application_claim_mismatch",
            context,
        )
        _expect(
            record.get("resource_id") == command.resource_id
            and record.get("global_track_id") == command.global_track_id
            and _normalise_sha256(record.get("command_payload_sha256"))
            == command.command_payload_sha256
            and _nonnegative_int(record.get("cycle_index"), f"{context} cycle")
            == command.cycle_index,
            "world_application_command_lineage_mismatch",
            context,
        )
        applied_at = _nonnegative_float(
            record.get("applied_at_s"), f"{context} applied_at_s"
        )
        _expect(
            applied_at + 1.0e-9 >= command.issued_at_s,
            "world_application_precedes_command",
            context,
        )
        result[application_id] = _WorldApplication(
            world_application_id=application_id,
            cycle_index=command.cycle_index,
            applied_at_s=applied_at,
            command_id=command_id,
            command_payload_sha256=command.command_payload_sha256,
            resource_id=command.resource_id,
            global_track_id=command.global_track_id,
            hard_constraint_violation_count=_nonnegative_int(
                record.get("hard_constraint_violation_count"),
                f"{context} hard constraint count",
            ),
        )
    return result


def _d4_adoption_availability(
    artifact: PairedPhysicalArtifact | None,
    *,
    pair: PairedIsolatedEpisodeInputs,
    arm_kind: str,
) -> dict[str, Any]:
    """Validate optional D4 evidence without inferring undeclared files."""

    if artifact is None:
        return {
            "available": False,
            "status": "not_declared",
            "value": None,
            "reason": "d4_adoption_artifact_not_declared_by_input_spec",
        }
    records = _load_jsonl(artifact.path, f"{arm_kind} D4 adoption evidence")
    if not records:
        return {
            "available": False,
            "status": "not_applicable",
            "value": {
                "artifact_declared": True,
                "region_count": 0,
                "available_count": 0,
                "reason_counts": {},
                "intervention_kind": "nominal",
                "region_ids": [],
                "all_regions_available": True,
            },
            "reason": None,
        }

    region_ids: set[str] = set()
    intervention_kinds: set[str] = set()
    reason_counts: dict[str, int] = {}
    available_count = 0
    for index, record in enumerate(records):
        context = f"{arm_kind} D4 adoption line {index + 1}"
        region_id, intervention_kind, available, reason = (
            _validate_d4_adoption_record(
                record,
                context=context,
                pair=pair,
                arm_kind=arm_kind,
            )
        )
        _expect(
            region_id not in region_ids,
            "duplicate_d4_adoption_region",
            f"{context} duplicates region {region_id}",
        )
        region_ids.add(region_id)
        intervention_kinds.add(intervention_kind)
        if available:
            available_count += 1
        else:
            assert reason is not None
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    _expect(
        len(intervention_kinds) == 1,
        "d4_adoption_intervention_mismatch",
        f"{arm_kind} D4 evidence mixes intervention kinds",
    )
    summary = {
        "artifact_declared": True,
        "region_count": len(records),
        "available_count": available_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "intervention_kind": next(iter(intervention_kinds)),
        "region_ids": sorted(region_ids),
        "all_regions_available": available_count == len(records),
    }
    if available_count == len(records):
        return _availability(True, summary, None)
    return {
        "available": False,
        "status": "unavailable",
        "value": summary,
        "reason": "one_or_more_d4_adoption_regions_unavailable",
    }


def _validate_d4_adoption_record(
    record: Mapping[str, Any],
    *,
    context: str,
    pair: PairedIsolatedEpisodeInputs,
    arm_kind: str,
) -> tuple[str, str, bool, str | None]:
    _require_exact_keys(record, set(_D4_ADOPTION_RECORD_KEYS), context)
    _expect(
        record.get("schema_version") == D4_ISOLATED_PHYSICAL_ADOPTION_SCHEMA,
        "d4_adoption_schema_mismatch",
        f"{context} schema is unsupported",
    )
    _expect(
        record.get("arm_kind") == arm_kind,
        "d4_adoption_arm_mismatch",
        f"{context} belongs to another arm",
    )
    region_id = _required_string(record, "region_id", context)
    intervention_kind = _required_string(record, "intervention_kind", context)
    _expect(
        intervention_kind in _D4_DEGRADED_INTERVENTION_KINDS,
        "d4_adoption_intervention_invalid",
        f"{context} intervention kind is unsupported",
    )
    available = _strict_bool(record.get("available"), f"{context} available")
    raw_reason = record.get("reason")
    if available:
        _expect(
            raw_reason is None,
            "d4_adoption_state_contradiction",
            f"{context} available record carries a reason",
        )
        reason: str | None = None
    else:
        reason = _required_string(record, "reason", context)

    nested_names = (
        "source_plan",
        "applied_plan",
        "scenario_lineage",
        "candidate_gate",
        "plan_consumption_ack",
        "adoption_evidence",
    )
    if available:
        _expect(
            all(isinstance(record.get(name), Mapping) for name in nested_names),
            "d4_adoption_available_evidence_incomplete",
            f"{context} available record lacks nested evidence",
        )
    for name in nested_names:
        value = record.get(name)
        _expect(
            value is None or isinstance(value, Mapping),
            "d4_adoption_nested_contract_invalid",
            f"{context}.{name} must be an object or null",
        )
    _assert_truth_free(record, context)
    _assert_d4_nonproduction(record, context)

    source_plan = (
        _validate_d4_plan(
            _mapping(record["source_plan"], f"{context}.source_plan"),
            context=f"{context}.source_plan",
            region_id=region_id,
            applied=False,
        )
        if record.get("source_plan") is not None
        else None
    )
    applied_plan = (
        _validate_d4_plan(
            _mapping(record["applied_plan"], f"{context}.applied_plan"),
            context=f"{context}.applied_plan",
            region_id=region_id,
            applied=True,
        )
        if record.get("applied_plan") is not None
        else None
    )
    lineage = (
        _validate_d4_scenario_lineage(
            _mapping(record["scenario_lineage"], f"{context}.scenario_lineage"),
            context=f"{context}.scenario_lineage",
            pair=pair,
            arm_kind=arm_kind,
            region_id=region_id,
            intervention_kind=intervention_kind,
        )
        if record.get("scenario_lineage") is not None
        else None
    )
    gate = (
        _validate_d4_candidate_gate(
            _mapping(record["candidate_gate"], f"{context}.candidate_gate"),
            context=f"{context}.candidate_gate",
        )
        if record.get("candidate_gate") is not None
        else None
    )

    if lineage is not None and source_plan is not None:
        _expect(
            lineage["source_plan_payload_sha256"]
            == source_plan["payload_sha256"],
            "d4_adoption_source_plan_hash_mismatch",
            f"{context} source plan is not bound by scenario lineage",
        )
    if lineage is not None and gate is not None:
        _expect(
            lineage["candidate_gate_payload_sha256"] == gate["payload_sha256"],
            "d4_adoption_candidate_gate_hash_mismatch",
            f"{context} candidate gate is not bound by scenario lineage",
        )
    if lineage is not None and applied_plan is not None:
        _expect(
            applied_plan["source_lineage_sha256"] == lineage["payload_sha256"],
            "d4_adoption_applied_plan_lineage_mismatch",
            f"{context} applied plan is not bound to scenario lineage",
        )
    if gate is not None and applied_plan is not None:
        _expect(
            (
                gate["rule_fallback"] is True
                and applied_plan["candidate_payload_sha256"] is None
            )
            or (
                gate["rule_fallback"] is False
                and applied_plan["candidate_payload_sha256"]
                == gate["candidate_payload_sha256"]
            ),
            "d4_adoption_applied_plan_candidate_mismatch",
            f"{context} applied plan contradicts candidate gate",
        )

    ack = None
    if record.get("plan_consumption_ack") is not None:
        _expect(
            source_plan is not None and applied_plan is not None and lineage is not None,
            "d4_adoption_ack_dependencies_missing",
            f"{context} ACK lacks plan or lineage dependencies",
        )
        ack = _validate_d4_plan_ack(
            _mapping(
                record["plan_consumption_ack"],
                f"{context}.plan_consumption_ack",
            ),
            context=f"{context}.plan_consumption_ack",
            arm_id=str(lineage["arm_id"]),
            lineage_sha256=str(lineage["payload_sha256"]),
            source_plan=source_plan,
            applied_plan=applied_plan,
        )

    if record.get("adoption_evidence") is not None:
        _expect(
            all(item is not None for item in (source_plan, applied_plan, lineage, gate)),
            "d4_adoption_verdict_dependencies_missing",
            f"{context} verdict lacks plan, lineage, or gate dependencies",
        )
        _validate_d4_adoption_verdict(
            _mapping(record["adoption_evidence"], f"{context}.adoption_evidence"),
            context=f"{context}.adoption_evidence",
            intervention_kind=intervention_kind,
            source_plan=source_plan,
            applied_plan=applied_plan,
            lineage=lineage,
            gate=gate,
            ack=ack,
            top_level_available=available,
        )
    elif available:
        _fail(
            "d4_adoption_available_evidence_incomplete",
            f"{context} available record has no D4 verdict",
        )
    return region_id, intervention_kind, available, reason


def _validate_d4_plan(
    payload: Mapping[str, Any],
    *,
    context: str,
    region_id: str,
    applied: bool,
) -> dict[str, Any]:
    _require_exact_keys(payload, set(_D4_PLAN_KEYS), context)
    plan_id = _required_string(payload, "plan_id", context)
    plan_version = _nonnegative_int(
        payload.get("plan_version"), f"{context}.plan_version"
    )
    _nonnegative_float(payload.get("timestamp"), f"{context}.timestamp")
    _nonnegative_float(payload.get("created_at"), f"{context}.created_at")
    assignments = _sequence(payload.get("assignments"), f"{context}.assignments")
    assignment_count = _nonnegative_int(
        payload.get("assignment_count"), f"{context}.assignment_count"
    )
    _expect(
        assignment_count == len(assignments),
        "d4_adoption_plan_binding_count_mismatch",
        f"{context} assignment_count differs from assignments",
    )
    metadata = _mapping(payload.get("metadata"), f"{context}.metadata")
    _require_exact_keys(
        metadata,
        set(
            _D4_APPLIED_PLAN_METADATA_KEYS
            if applied
            else _D4_PLAN_METADATA_BASE_KEYS
        ),
        f"{context}.metadata",
    )
    _expect(
        metadata.get("current_plan_id") == plan_id
        and _nonnegative_int(
            metadata.get("current_plan_version"),
            f"{context}.metadata.current_plan_version",
        )
        == plan_version,
        "d4_adoption_plan_identity_mismatch",
        f"{context} metadata does not bind plan identity",
    )
    owner_layer = _required_string(metadata, "active_plan_owner", context)
    _expect(
        owner_layer in {"center", "secondary", "distributed"},
        "d4_adoption_owner_layer_invalid",
        f"{context} owner layer is invalid",
    )
    owner_node_id = _required_string(metadata, "owner_node_id", context)
    authority_epoch = _nonnegative_int(
        metadata.get("authority_epoch"), f"{context}.authority_epoch"
    )
    _nonnegative_float(
        metadata.get("lease_expires_at_s"), f"{context}.lease_expires_at_s"
    )
    for name in (
        "identity_created_at_s",
        "last_evaluated_at_s",
    ):
        _nonnegative_float(metadata.get(name), f"{context}.metadata.{name}")
    for name in (
        "execution_signature_changed",
        "plan_refresh_only",
        "evaluation_refresh_only",
        "plan_published",
    ):
        _strict_bool(metadata.get(name), f"{context}.metadata.{name}")
    _expect(
        metadata.get("plan_published") is True,
        "d4_adoption_plan_not_published",
        f"{context} plan is not published",
    )

    signature: list[tuple[Any, ...]] = []
    seen_bindings: set[tuple[str, str]] = set()
    for index, raw in enumerate(assignments):
        item_context = f"{context}.assignments[{index}]"
        item = _mapping(raw, item_context)
        _require_exact_keys(item, set(_D4_ASSIGNMENT_KEYS), item_context)
        resource_id = _required_string(item, "resource_id", item_context)
        track_id = _required_string(item, "global_track_id", item_context)
        binding = (resource_id, track_id)
        _expect(
            binding not in seen_bindings,
            "duplicate_d4_adoption_plan_binding",
            item_context,
        )
        seen_bindings.add(binding)
        _expect(
            item.get("regional_region_id") == region_id
            and item.get("owner_node_id") == owner_node_id
            and item.get("regional_owner_layer") == owner_layer
            and _nonnegative_int(
                item.get("regional_epoch"), f"{item_context}.regional_epoch"
            )
            == authority_epoch,
            "d4_adoption_plan_region_authority_mismatch",
            item_context,
        )
        member_role = _required_string(item, "member_role", item_context)
        coalition_id = item.get("coalition_id")
        coalition_version = item.get("coalition_version")
        if coalition_id is not None:
            _expect(
                isinstance(coalition_id, str) and bool(coalition_id),
                "d4_adoption_plan_binding_invalid",
                f"{item_context}.coalition_id is invalid",
            )
        if coalition_version is not None:
            coalition_version = _nonnegative_int(
                coalition_version, f"{item_context}.coalition_version"
            )
        regional_commit_mode = item.get("regional_commit_mode")
        if regional_commit_mode is not None:
            _expect(
                isinstance(regional_commit_mode, str) and bool(regional_commit_mode),
                "d4_adoption_plan_binding_invalid",
                f"{item_context}.regional_commit_mode is invalid",
            )
        signature.append(
            (
                resource_id,
                track_id,
                coalition_id,
                coalition_version,
                member_role,
                owner_node_id,
                owner_layer,
                region_id,
                authority_epoch,
                regional_commit_mode,
            )
        )
    unassigned = _sequence(
        payload.get("unassigned_global_track_ids"),
        f"{context}.unassigned_global_track_ids",
    )
    unassigned_ids = [
        _required_text_value(item, f"{context}.unassigned_global_track_ids")
        for item in unassigned
    ]
    _expect(
        len(unassigned_ids) == len(set(unassigned_ids)),
        "duplicate_d4_unassigned_track",
        context,
    )
    source_lineage_sha256 = None
    candidate_payload_sha256 = None
    if applied:
        execution_source = _required_string(
            metadata, "d4_isolated_execution_source", f"{context}.metadata"
        )
        _expect(
            execution_source
            in {"candidate", "deterministic_rule_fallback", "evaluation_refresh"},
            "d4_adoption_execution_source_invalid",
            context,
        )
        candidate_sha = metadata.get("d4_candidate_payload_sha256")
        if candidate_sha is not None:
            candidate_payload_sha256 = _normalise_sha256(candidate_sha)
        source_lineage_sha256 = _normalise_sha256(
            metadata.get("d4_source_lineage_sha256")
        )
    _assert_truth_free(payload, context)
    return {
        "plan_id": plan_id,
        "plan_version": plan_version,
        "assignment_count": assignment_count,
        "payload_sha256": _canonical_payload_sha256(payload),
        "binding_sha256": _canonical_payload_sha256(
            tuple(sorted(signature, key=lambda item: (item[0], item[1])))
        ),
        "source_lineage_sha256": source_lineage_sha256,
        "candidate_payload_sha256": candidate_payload_sha256,
        "owner_layer": owner_layer,
        "owner_node_id": owner_node_id,
        "authority_epoch": authority_epoch,
        "lease_expires_at_s": float(metadata["lease_expires_at_s"]),
        "execution_source": metadata.get("d4_isolated_execution_source"),
    }


def _validate_d4_scenario_lineage(
    payload: Mapping[str, Any],
    *,
    context: str,
    pair: PairedIsolatedEpisodeInputs,
    arm_kind: str,
    region_id: str,
    intervention_kind: str,
) -> dict[str, Any]:
    _require_exact_keys(payload, set(_D4_SCENARIO_LINEAGE_KEYS), context)
    _expect(
        payload.get("schema") == D4_DEGRADED_SCENARIO_LINEAGE_SCHEMA,
        "d4_scenario_lineage_schema_mismatch",
        context,
    )
    _expect(
        payload.get("scenario_kind") == intervention_kind
        and payload.get("region_id") == region_id
        and _integer(payload.get("seed"), f"{context}.seed") == pair.seed
        and payload.get("arm_id") == f"{pair.seed}-{arm_kind}",
        "d4_scenario_lineage_identity_mismatch",
        context,
    )
    _required_string(payload, "scenario_id", context)
    _required_string(payload, "scenario_version", context)
    _nonnegative_int(payload.get("cycle_index"), f"{context}.cycle_index")
    _nonnegative_float(
        payload.get("source_timestamp_s"), f"{context}.source_timestamp_s"
    )
    _expect(
        payload.get("isolated_simulation_only") is True
        and payload.get("nominal_evidence") is False,
        "d4_scenario_lineage_not_isolated_degraded",
        context,
    )
    for name in (
        "scenario_config_sha256",
        "initial_state_sha256",
        "communication_schedule_sha256",
        "fault_schedule_sha256",
        "source_snapshot_payload_sha256",
        "formal_decision_payload_sha256",
        "source_plan_payload_sha256",
        "candidate_gate_payload_sha256",
    ):
        _normalise_sha256(payload.get(name))
    return {
        "arm_id": str(payload["arm_id"]),
        "source_plan_payload_sha256": _normalise_sha256(
            payload["source_plan_payload_sha256"]
        ),
        "candidate_gate_payload_sha256": _normalise_sha256(
            payload["candidate_gate_payload_sha256"]
        ),
        "payload_sha256": _canonical_payload_sha256(payload),
    }


def _validate_d4_candidate_gate(
    payload: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    _require_exact_keys(payload, set(_D4_CANDIDATE_GATE_KEYS), context)
    _expect(
        payload.get("schema") == D4_ISOLATED_CANDIDATE_GATE_SCHEMA,
        "d4_candidate_gate_schema_mismatch",
        context,
    )
    considered = _strict_bool(
        payload.get("candidate_considered"), f"{context}.candidate_considered"
    )
    gate_pass = _strict_bool(payload.get("gate_pass"), f"{context}.gate_pass")
    rule_fallback = _strict_bool(
        payload.get("rule_fallback"), f"{context}.rule_fallback"
    )
    _expect(
        payload.get("isolated_simulation_only") is True
        and payload.get("production_authority") is False,
        "production_runtime_ack_impersonation",
        f"{context} claims production authority",
    )
    _expect(
        math.isclose(
            _number(payload.get("minimum_confidence"), f"{context}.minimum_confidence"),
            0.60,
            abs_tol=1.0e-12,
        )
        and math.isclose(
            _number(
                payload.get("candidate_latency_limit_ms"),
                f"{context}.candidate_latency_limit_ms",
            ),
            50.0,
            abs_tol=1.0e-12,
        ),
        "d4_candidate_gate_threshold_mismatch",
        context,
    )
    rejection_reasons = _sequence(
        payload.get("rejection_reasons"), f"{context}.rejection_reasons"
    )
    for item in rejection_reasons:
        _required_text_value(item, f"{context}.rejection_reasons")
    if considered:
        _required_string(payload, "candidate_id", context)
        candidate_payload_sha256 = _normalise_sha256(
            payload.get("candidate_payload_sha256")
        )
        confidence = _number(
            payload.get("candidate_confidence"), f"{context}.candidate_confidence"
        )
        _expect(
            0.0 <= confidence <= 1.0,
            "d4_candidate_gate_state_contradiction",
            f"{context}.candidate_confidence is outside [0, 1]",
        )
        latency = _nonnegative_float(
            payload.get("candidate_latency_ms"), f"{context}.candidate_latency_ms"
        )
        diagnostics: dict[str, bool] = {}
        for name in (
            "candidate_ood_passed",
            "candidate_finite",
            "candidate_failure_gate_passed",
            "candidate_safety_projection_passed",
        ):
            diagnostics[name] = _strict_bool(
                payload.get(name), f"{context}.{name}"
            )
        expected_gate = bool(
            confidence >= 0.60
            and diagnostics["candidate_ood_passed"]
            and latency <= 50.0
            and diagnostics["candidate_finite"]
            and diagnostics["candidate_failure_gate_passed"]
            and diagnostics["candidate_safety_projection_passed"]
        )
        _expect(
            gate_pass == expected_gate
            and (gate_pass or rule_fallback)
            and (not rule_fallback or bool(rejection_reasons))
            and (not gate_pass or rule_fallback or not rejection_reasons),
            "d4_candidate_gate_state_contradiction",
            context,
        )
    else:
        candidate_payload_sha256 = None
        _expect(
            all(
                payload.get(name) is None
                for name in (
                    "candidate_id",
                    "candidate_payload_sha256",
                    "candidate_confidence",
                    "candidate_ood_passed",
                    "candidate_latency_ms",
                    "candidate_finite",
                    "candidate_failure_gate_passed",
                    "candidate_safety_projection_passed",
                )
            )
            and not gate_pass
            and rule_fallback,
            "d4_candidate_gate_state_contradiction",
            context,
        )
    return {
        "candidate_considered": considered,
        "gate_pass": gate_pass,
        "rule_fallback": rule_fallback,
        "candidate_payload_sha256": candidate_payload_sha256,
        "payload_sha256": _canonical_payload_sha256(payload),
    }


def _validate_d4_plan_ack(
    payload: Mapping[str, Any],
    *,
    context: str,
    arm_id: str,
    lineage_sha256: str,
    source_plan: Mapping[str, Any],
    applied_plan: Mapping[str, Any],
) -> dict[str, Any]:
    _require_exact_keys(payload, set(_D4_PLAN_ACK_KEYS), context)
    _expect(
        payload.get("schema") == D4_ISOLATED_PLAN_ACK_SCHEMA,
        "d4_plan_ack_schema_mismatch",
        context,
    )
    _assert_d4_nonproduction(payload, context)
    _expect(
        payload.get("isolated_simulation_only") is True
        and payload.get("production_runtime_ack") is False,
        "production_runtime_ack_impersonation",
        context,
    )
    _expect(
        payload.get("arm_id") == arm_id
        and _normalise_sha256(payload.get("source_lineage_sha256"))
        == lineage_sha256,
        "d4_plan_ack_lineage_mismatch",
        context,
    )
    _required_string(payload, "ack_id", context)
    _nonnegative_int(payload.get("cycle_index"), f"{context}.cycle_index")
    _nonnegative_float(
        payload.get("acknowledged_at_s"), f"{context}.acknowledged_at_s"
    )
    accepted = _strict_bool(payload.get("accepted"), f"{context}.accepted")
    fully_consumed = _strict_bool(
        payload.get("fully_consumed_by_isolated_world"),
        f"{context}.fully_consumed_by_isolated_world",
    )
    _strict_bool(
        payload.get("network_partition_observed"),
        f"{context}.network_partition_observed",
    )
    assignment_count = _nonnegative_int(
        payload.get("assignment_count"), f"{context}.assignment_count"
    )
    consumed_count = _nonnegative_int(
        payload.get("control_applied_binding_count"),
        f"{context}.control_applied_binding_count",
    )
    _expect(
        payload.get("status_code")
        == (
            "accepted_by_isolated_simulation"
            if accepted
            else "rejected_by_isolated_simulation"
        )
        and consumed_count <= assignment_count
        and (not fully_consumed or consumed_count == assignment_count),
        "d4_plan_ack_state_contradiction",
        context,
    )
    _expect(
        payload.get("source_plan_id") == source_plan["plan_id"]
        and _nonnegative_int(
            payload.get("source_plan_version"), f"{context}.source_plan_version"
        )
        == source_plan["plan_version"]
        and payload.get("applied_plan_id") == applied_plan["plan_id"]
        and _nonnegative_int(
            payload.get("applied_plan_version"), f"{context}.applied_plan_version"
        )
        == applied_plan["plan_version"]
        and _normalise_sha256(payload.get("applied_plan_payload_sha256"))
        == applied_plan["payload_sha256"]
        and _normalise_sha256(payload.get("execution_binding_sha256"))
        == applied_plan["binding_sha256"]
        and assignment_count == applied_plan["assignment_count"],
        "d4_plan_ack_plan_lineage_mismatch",
        context,
    )
    _expect(
        payload.get("execution_source") == applied_plan["execution_source"]
        and payload.get("owner_layer") == applied_plan["owner_layer"]
        and payload.get("owner_node_id") == applied_plan["owner_node_id"]
        and _nonnegative_int(
            payload.get("authority_epoch"), f"{context}.authority_epoch"
        )
        == applied_plan["authority_epoch"]
        and math.isclose(
            _nonnegative_float(
                payload.get("lease_expires_at_s"), f"{context}.lease_expires_at_s"
            ),
            float(applied_plan["lease_expires_at_s"]),
            abs_tol=1.0e-9,
        ),
        "d4_plan_ack_authority_mismatch",
        context,
    )
    return {
        "ack_id": str(payload["ack_id"]),
        "accepted": accepted,
        "fully_consumed": fully_consumed,
        "assignment_count": assignment_count,
        "consumed_count": consumed_count,
    }


def _validate_d4_adoption_verdict(
    payload: Mapping[str, Any],
    *,
    context: str,
    intervention_kind: str,
    source_plan: Mapping[str, Any],
    applied_plan: Mapping[str, Any],
    lineage: Mapping[str, Any],
    gate: Mapping[str, Any],
    ack: Mapping[str, Any] | None,
    top_level_available: bool,
) -> None:
    _require_exact_keys(payload, set(_D4_ADOPTION_EVIDENCE_KEYS), context)
    _expect(
        payload.get("schema") == D4_ISOLATED_ADOPTION_EVIDENCE_SCHEMA,
        "d4_adoption_verdict_schema_mismatch",
        context,
    )
    _assert_d4_nonproduction(payload, context)
    _required_string(payload, "code", context)
    _required_string(payload, "reason", context)
    _expect(
        payload.get("scenario_kind") == intervention_kind
        and _normalise_sha256(payload.get("scenario_lineage_sha256"))
        == lineage["payload_sha256"],
        "d4_adoption_verdict_lineage_mismatch",
        context,
    )
    boolean_names = (
        "scenario_validated",
        "candidate_considered",
        "gate_pass",
        "new_execution_plan_applied",
        "evaluation_refresh_applied",
        "rule_fallback",
        "isolated_plan_consumption_ack_available",
        "isolated_candidate_adoption_available",
        "isolated_simulation_only",
        "production_runtime_ack",
        "physical_outcome_available",
        "paired_non_degradation_available",
        "counterfactual_available",
        "causal_effect_available",
        "degradation_effectiveness_claim_allowed",
        "ppo_enabled",
        "assist_enabled",
        "authority_enabled",
        "rule_fallback_enabled",
    )
    for name in boolean_names:
        _strict_bool(payload.get(name), f"{context}.{name}")
    new_plan = payload.get("new_execution_plan_applied") is True
    refresh = payload.get("evaluation_refresh_applied") is True
    ack_available = payload.get("isolated_plan_consumption_ack_available") is True
    _expect(
        (
            (new_plan != refresh)
            if ack_available
            else not (new_plan or refresh)
        )
        and payload.get("rule_fallback_enabled") is True,
        "d4_adoption_verdict_state_contradiction",
        context,
    )
    expected_kind = (
        "new_execution_plan_applied"
        if new_plan
        else "evaluation_refresh_applied"
        if refresh
        else None
    )
    expected_candidate_adoption = bool(
        payload.get("scenario_validated") is True
        and gate["candidate_considered"] is True
        and gate["gate_pass"] is True
        and new_plan
        and gate["rule_fallback"] is False
    )
    _expect(
        payload.get("adoption_kind") == expected_kind
        and payload.get("isolated_candidate_adoption_available")
        is expected_candidate_adoption,
        "d4_adoption_kind_mismatch",
        context,
    )
    _expect(
        payload.get("candidate_considered") == gate["candidate_considered"]
        and payload.get("gate_pass") == gate["gate_pass"]
        and payload.get("rule_fallback") == gate["rule_fallback"],
        "d4_adoption_verdict_gate_mismatch",
        context,
    )
    _expect(
        payload.get("source_plan_id") == source_plan["plan_id"]
        and payload.get("source_plan_version") == source_plan["plan_version"]
        and payload.get("applied_plan_id") == applied_plan["plan_id"]
        and payload.get("applied_plan_version") == applied_plan["plan_version"],
        "d4_adoption_verdict_plan_mismatch",
        context,
    )
    # A producer may retain an independently auditable ACK even when the D4
    # verdict did not admit it as adoption evidence. Bind the verdict ACK only
    # when that verdict explicitly declares the ACK available.
    if ack_available:
        _expect(
            ack is not None and payload.get("ack_id") == ack["ack_id"],
            "d4_adoption_verdict_ack_mismatch",
            context,
        )
    if top_level_available:
        _expect(
            payload.get("scenario_validated") is True
            and payload.get("isolated_plan_consumption_ack_available") is True
            and ack is not None
            and ack["accepted"] is True
            and ack["fully_consumed"] is True
            and ack["consumed_count"] == ack["assignment_count"]
            and new_plan != refresh,
            "d4_adoption_available_state_invalid",
            context,
        )


def _assert_d4_nonproduction(value: Any, context: str) -> None:
    forbidden_false = {
        "production_runtime_ack",
        "production_runtime_ack_available",
        "production_authority",
        "control_applied_to_production_world",
        "physical_outcome_available",
        "paired_non_degradation_available",
        "counterfactual_available",
        "causal_effect_available",
        "degradation_effectiveness_claim_allowed",
        "ppo_enabled",
        "assist_enabled",
        "authority_enabled",
        "online_assist_enabled",
        "online_authority_enabled",
    }
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in forbidden_false and nested is not False:
                _fail(
                    "production_runtime_ack_impersonation",
                    f"{context}.{key} must be false for isolated evidence",
                )
            if key == "isolated_simulation_only" and nested is not True:
                _fail(
                    "d4_adoption_isolation_claim_invalid",
                    f"{context}.{key} must be true",
                )
            _assert_d4_nonproduction(nested, f"{context}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, nested in enumerate(value):
            _assert_d4_nonproduction(nested, f"{context}[{index}]")


def _required_text_value(value: Any, context: str) -> str:
    _expect(
        isinstance(value, str) and bool(value),
        "required_string_missing",
        f"{context} must contain non-empty strings",
    )
    return str(value)


def _load_offline_identity(
    path: Path,
    *,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, str] | None, str | None]:
    payload = _load_json(path, "offline identity mapping")
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "episode_id",
            "world_id",
            "seed",
            "online_truth_isolation_verified",
            "online_truth_use_count",
            "mappings",
        },
        "offline identity mapping",
    )
    _expect(
        payload.get("schema_version") == OFFLINE_IDENTITY_SCHEMA,
        "offline_identity_schema_mismatch",
        "offline identity schema is unsupported",
    )
    _expect(
        payload.get("episode_id") == manifest.get("episode_id")
        and payload.get("world_id") == manifest.get("world_id")
        and payload.get("seed") == manifest.get("seed"),
        "offline_identity_episode_mismatch",
        "offline identity does not bind the isolated arm",
    )
    _expect(
        payload.get("online_truth_isolation_verified") is True
        and _nonnegative_int(
            payload.get("online_truth_use_count"), "offline identity truth count"
        )
        == 0,
        "online_truth_isolation_failed",
        "offline identity does not prove zero online truth use",
    )
    mappings = _sequence(payload.get("mappings"), "offline identity mappings")
    if not mappings:
        return None, "offline_identity_mapping_empty"
    result: dict[str, str] = {}
    used_targets: set[str] = set()
    for index, raw in enumerate(mappings):
        item = _mapping(raw, f"offline identity mapping {index}")
        _require_exact_keys(
            item,
            {"global_track_id", "truth_target_id", "mapping_status"},
            f"offline identity mapping {index}",
        )
        track_id = _required_string(
            item, "global_track_id", f"offline identity mapping {index}"
        )
        target_id = _required_string(
            item, "truth_target_id", f"offline identity mapping {index}"
        )
        _expect(
            item.get("mapping_status") == "unique_lineage_verified",
            "offline_identity_mapping_not_unique",
            f"offline identity mapping {index}",
        )
        _expect(
            track_id not in result and target_id not in used_targets,
            "offline_identity_mapping_not_one_to_one",
            f"offline identity mapping {index}",
        )
        result[track_id] = target_id
        used_targets.add(target_id)
    return result, None


def _load_truth_state(
    path: Path,
    *,
    manifest: Mapping[str, Any],
    initial_state: Mapping[str, Any],
) -> tuple[tuple[_TruthSample, ...] | None, str | None]:
    records = _load_jsonl(path, "offline truth state")
    if not records:
        return None, "offline_truth_state_empty"
    samples: list[_TruthSample] = []
    previous_time = -math.inf
    interceptor_ids: set[str] | None = None
    target_ids: set[str] | None = None
    for index, record in enumerate(records):
        context = f"offline truth state line {index + 1}"
        _require_exact_keys(
            record,
            {
                "schema_version",
                "episode_id",
                "world_id",
                "seed",
                "timestamp_s",
                "interceptor_positions_ned_m",
                "target_positions_ned_m",
            },
            context,
        )
        _expect(
            record.get("schema_version") == OFFLINE_TRUTH_STATE_SCHEMA,
            "offline_truth_state_schema_mismatch",
            context,
        )
        _expect(
            record.get("episode_id") == manifest.get("episode_id")
            and record.get("world_id") == manifest.get("world_id")
            and record.get("seed") == manifest.get("seed"),
            "offline_truth_state_episode_mismatch",
            context,
        )
        timestamp = _nonnegative_float(
            record.get("timestamp_s"), f"{context} timestamp"
        )
        _expect(
            timestamp > previous_time,
            "offline_truth_timeline_not_strict",
            context,
        )
        previous_time = timestamp
        interceptors = _position_mapping(
            record.get("interceptor_positions_ned_m"),
            f"{context} interceptors",
        )
        targets = _position_mapping(
            record.get("target_positions_ned_m"),
            f"{context} targets",
        )
        if interceptor_ids is None:
            interceptor_ids = set(interceptors)
            target_ids = set(targets)
        _expect(
            set(interceptors) == interceptor_ids and set(targets) == target_ids,
            "offline_truth_entity_catalog_changed",
            context,
        )
        samples.append(
            _TruthSample(
                timestamp_s=timestamp,
                interceptor_positions=interceptors,
                target_positions=targets,
            )
        )
    _expect(
        math.isclose(samples[0].timestamp_s, 0.0, abs_tol=1.0e-9),
        "offline_truth_initial_timestamp_mismatch",
        "offline truth must start at t=0",
    )
    _expect(
        math.isclose(
            samples[-1].timestamp_s,
            _positive_float(manifest.get("duration_s"), "episode duration"),
            abs_tol=1.0e-9,
        ),
        "offline_truth_episode_end_mismatch",
        "offline truth must close at episode duration",
    )
    expected_interceptors = _position_mapping(
        initial_state.get("interceptor_positions_ned_m"),
        "shared initial interceptors",
    )
    expected_targets = _position_mapping(
        initial_state.get("target_positions_ned_m"),
        "shared initial targets",
    )
    _expect(
        _positions_close(samples[0].interceptor_positions, expected_interceptors)
        and _positions_close(samples[0].target_positions, expected_targets),
        "paired_initial_state_mismatch",
        "isolated arm truth does not start from the shared initial state",
    )
    return tuple(samples), None


def _plan_consumption_availability(
    consumptions: Mapping[str, _Consumption],
) -> dict[str, Any]:
    accepted = [item for item in consumptions.values() if item.accepted]
    if not accepted:
        return _availability(
            False,
            None,
            "no_accepted_isolated_plan_consumption_confirmation",
        )
    return _availability(
        True,
        {
            "confirmation_count": len(consumptions),
            "accepted_confirmation_count": len(accepted),
            "consumed_binding_count": sum(len(item.plan.assignments) for item in accepted),
            "evidence_scope": ISOLATED_PLAN_CONSUMPTION_SCOPE,
            "production_runtime_ack": False,
        },
        None,
    )


def _guidance_availability(
    consumptions: Mapping[str, _Consumption],
    *,
    commands: Mapping[str, _Command],
    applications: Mapping[str, _WorldApplication],
    plan_available: bool,
) -> dict[str, Any]:
    if not plan_available:
        return _availability(False, None, "plan_consumption_unavailable")
    if not commands:
        return _availability(False, None, "d7_command_lineage_missing")
    cycles = {item.cycle_index for item in commands.values()}
    if len(cycles) < MINIMUM_CONTROL_CYCLE_COUNT:
        return _availability(
            False,
            None,
            "insufficient_distinct_control_cycles",
        )
    expected_bindings = {
        (item.consumption_id, resource_id, track_id)
        for item in consumptions.values()
        if item.accepted
        for resource_id, track_id in item.plan.assignments
    }
    applied_bindings = {
        (item.consumption_id, item.resource_id, item.global_track_id)
        for item in commands.values()
        if item.control_applied_to_world
        and item.world_application_id in applications
    }
    if not expected_bindings.issubset(applied_bindings):
        return _availability(
            False,
            None,
            "accepted_plan_binding_without_applied_d7_control",
        )
    missing_applications = [
        item.command_id
        for item in commands.values()
        if item.control_applied_to_world
        and item.world_application_id not in applications
    ]
    if missing_applications:
        return _availability(
            False,
            None,
            "control_applied_claim_without_world_application_evidence",
        )
    return _availability(
        True,
        {
            "d7_command_count": len(commands),
            "world_application_count": len(applications),
            "distinct_control_cycle_count": len(cycles),
            "all_consumed_bindings_have_applied_control": True,
        },
        None,
    )


def _build_physical_windows(
    consumptions: Mapping[str, _Consumption],
    *,
    commands: Mapping[str, _Command],
    applications: Mapping[str, _WorldApplication],
    identity: Mapping[str, str],
    truth: Sequence[_TruthSample],
    episode_end_s: float,
) -> tuple[list[dict[str, Any]], str | None]:
    accepted = sorted(
        (item for item in consumptions.values() if item.accepted),
        key=lambda item: (item.consumed_at_s, item.cycle_index, item.consumption_id),
    )
    next_by_resource: dict[tuple[str, str], float] = {}
    for index, current in enumerate(accepted):
        for resource_id, _ in current.plan.assignments:
            for later in accepted[index + 1 :]:
                if any(resource_id == item[0] for item in later.plan.assignments):
                    next_by_resource[(current.consumption_id, resource_id)] = (
                        later.consumed_at_s
                    )
                    break
    commands_by_binding: dict[tuple[str, str, str], list[_Command]] = {}
    for command in commands.values():
        if command.control_applied_to_world:
            commands_by_binding.setdefault(
                (
                    command.consumption_id,
                    command.resource_id,
                    command.global_track_id,
                ),
                [],
            ).append(command)
    windows: list[dict[str, Any]] = []
    for consumption in accepted:
        for resource_id, track_id in consumption.plan.assignments:
            truth_target_id = identity.get(track_id)
            if truth_target_id is None:
                return [], "assigned_global_track_missing_offline_identity_mapping"
            binding_commands = commands_by_binding.get(
                (consumption.consumption_id, resource_id, track_id), []
            )
            if not binding_commands:
                return [], "accepted_binding_without_applied_control_command"
            binding_applications = [
                applications[item.world_application_id]
                for item in binding_commands
                if item.world_application_id in applications
            ]
            if len(binding_applications) != len(binding_commands):
                return [], "applied_control_without_complete_world_application"
            start = min(item.applied_at_s for item in binding_applications)
            end = next_by_resource.get(
                (consumption.consumption_id, resource_id), episode_end_s
            )
            samples = [
                item
                for item in truth
                if (
                    item.timestamp_s + 1.0e-9 >= start
                    and item.timestamp_s < end - 1.0e-9
                )
                or (
                    math.isclose(item.timestamp_s, end, abs_tol=1.0e-9)
                    and math.isclose(end, episode_end_s, abs_tol=1.0e-9)
                )
            ]
            if not samples:
                return [], "physical_window_has_no_truth_samples"
            if any(resource_id not in item.interceptor_positions for item in samples):
                return [], "assigned_resource_missing_from_truth_state"
            if any(truth_target_id not in item.target_positions for item in samples):
                return [], "assigned_target_missing_from_truth_state"
            distances = [
                _distance(
                    item.interceptor_positions[resource_id],
                    item.target_positions[truth_target_id],
                )
                for item in samples
            ]
            closest = min(distances)
            successful_indices = [
                index
                for index, distance in enumerate(distances)
                if distance <= FIVE_METER_THRESHOLD_M + 1.0e-12
            ]
            success = bool(successful_indices)
            time_to_five = (
                samples[successful_indices[0]].timestamp_s - start
                if success
                else None
            )
            wrong_targets: set[str] = set()
            for sample in samples:
                resource_position = sample.interceptor_positions[resource_id]
                for candidate_id, target_position in sample.target_positions.items():
                    if candidate_id == truth_target_id:
                        continue
                    if (
                        _distance(resource_position, target_position)
                        <= FIVE_METER_THRESHOLD_M + 1.0e-12
                    ):
                        wrong_targets.add(candidate_id)
            windows.append(
                {
                    "consumption_id": consumption.consumption_id,
                    "plan_id": consumption.plan.plan_id,
                    "plan_version": consumption.plan.plan_version,
                    "plan_payload_sha256": consumption.plan.payload_sha256,
                    "resource_id": resource_id,
                    "global_track_id": track_id,
                    "offline_truth_target_id": truth_target_id,
                    "window_start_s": start,
                    "window_end_s": end,
                    "truth_sample_count": len(samples),
                    "command_count": len(binding_commands),
                    "control_applied_to_world": True,
                    "closest_distance_m": closest,
                    "five_meter_success": success,
                    "time_to_five_meter_s": time_to_five,
                    "incorrect_binding_observed": bool(wrong_targets),
                    "wrong_target_five_meter_ids": sorted(wrong_targets),
                    "hard_constraint_violation_count": sum(
                        item.hard_constraint_violation_count
                        for item in binding_applications
                    ),
                }
            )
    if not windows:
        return [], "no_consumed_assignment_binding_windows"
    return windows, None


def _arm_metrics(
    windows: Sequence[Mapping[str, Any]],
    *,
    applications: Mapping[str, _WorldApplication],
    physical_available: bool,
    unavailable_reason: Any,
) -> dict[str, Any]:
    hard_constraint_count = sum(
        item.hard_constraint_violation_count for item in applications.values()
    )
    if not physical_available:
        return {
            "available": False,
            "reason": unavailable_reason,
            "success_count": None,
            "successful_binding_count": None,
            "binding_window_count": None,
            "closest_distance_m": None,
            "mean_closest_distance_m": None,
            "time_to_five_meter_mean_s": None,
            "time_to_five_meter_sample_count": None,
            "hard_constraint_violation_count": hard_constraint_count,
            "incorrect_binding_count": None,
        }
    successful = [item for item in windows if item["five_meter_success"]]
    success_targets = {
        str(item["offline_truth_target_id"]) for item in successful
    }
    times = [
        float(item["time_to_five_meter_s"])
        for item in successful
        if item.get("time_to_five_meter_s") is not None
    ]
    closest = [float(item["closest_distance_m"]) for item in windows]
    return {
        "available": True,
        "reason": None,
        "success_count": len(success_targets),
        "successful_binding_count": len(successful),
        "binding_window_count": len(windows),
        "closest_distance_m": min(closest),
        "mean_closest_distance_m": sum(closest) / len(closest),
        "time_to_five_meter_mean_s": (
            sum(times) / len(times) if times else None
        ),
        "time_to_five_meter_sample_count": len(times),
        "time_to_five_meter_unavailable_reason": (
            None if times else "no_five_meter_success"
        ),
        "hard_constraint_violation_count": hard_constraint_count,
        "incorrect_binding_count": sum(
            bool(item["incorrect_binding_observed"]) for item in windows
        ),
    }


def _pair_availability(arms: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in ("plan_consumption", "guidance_lineage", "physical_window"):
        unavailable = [
            arm_kind
            for arm_kind in ("control", "treatment")
            if not _mapping(
                _mapping(arms[arm_kind].get("availability"), f"{arm_kind} availability").get(layer),
                f"{arm_kind} {layer}",
            ).get("available")
        ]
        result[layer] = _availability(
            not unavailable,
            {"control": True, "treatment": True} if not unavailable else None,
            None
            if not unavailable
            else f"arm_evidence_unavailable:{','.join(unavailable)}",
        )
    d4_layers = {
        arm_kind: _mapping(
            _mapping(
                arms[arm_kind].get("availability"),
                f"{arm_kind} availability",
            ).get("d4_degraded_adoption"),
            f"{arm_kind} D4 degraded adoption",
        )
        for arm_kind in ("control", "treatment")
    }
    d4_statuses = {
        arm_kind: str(layer.get("status"))
        for arm_kind, layer in d4_layers.items()
    }
    d4_values = {
        arm_kind: layer.get("value")
        for arm_kind, layer in d4_layers.items()
    }
    if set(d4_statuses.values()) == {"not_applicable"}:
        result["d4_degraded_adoption"] = {
            "available": False,
            "status": "not_applicable",
            "value": {
                "control": d4_values["control"],
                "treatment": d4_values["treatment"],
                "paired_region_inventory_match": True,
                "intervention_kind": "nominal",
            },
            "reason": None,
        }
    elif all(layer.get("available") is True for layer in d4_layers.values()):
        control_d4 = _mapping(d4_values["control"], "control D4 summary")
        treatment_d4 = _mapping(d4_values["treatment"], "treatment D4 summary")
        inventory_matches = bool(
            control_d4.get("region_ids") == treatment_d4.get("region_ids")
            and control_d4.get("intervention_kind")
            == treatment_d4.get("intervention_kind")
        )
        result["d4_degraded_adoption"] = (
            _availability(
                True,
                {
                    "control": control_d4,
                    "treatment": treatment_d4,
                    "paired_region_inventory_match": True,
                    "intervention_kind": control_d4["intervention_kind"],
                },
                None,
            )
            if inventory_matches
            else {
                "available": False,
                "status": "unavailable",
                "value": {
                    "control": control_d4,
                    "treatment": treatment_d4,
                    "paired_region_inventory_match": False,
                    "intervention_kind": None,
                },
                "reason": "d4_control_treatment_region_or_intervention_mismatch",
            }
        )
    else:
        result["d4_degraded_adoption"] = {
            "available": False,
            "status": "unavailable",
            "value": {
                "control": d4_values["control"],
                "treatment": d4_values["treatment"],
                "arm_status": d4_statuses,
                "paired_region_inventory_match": None,
                "intervention_kind": None,
            },
            "reason": "complete_control_and_treatment_d4_adoption_required",
        }
    control_metrics = _mapping(arms["control"].get("metrics"), "control metrics")
    treatment_metrics = _mapping(
        arms["treatment"].get("metrics"), "treatment metrics"
    )
    if result["physical_window"]["available"]:
        deltas = {
            "success_count_delta": int(treatment_metrics["success_count"])
            - int(control_metrics["success_count"]),
            "successful_binding_count_delta": int(
                treatment_metrics["successful_binding_count"]
            )
            - int(control_metrics["successful_binding_count"]),
            "mean_closest_distance_delta_m": float(
                treatment_metrics["mean_closest_distance_m"]
            )
            - float(control_metrics["mean_closest_distance_m"]),
            "closest_distance_delta_m": float(
                treatment_metrics["closest_distance_m"]
            )
            - float(control_metrics["closest_distance_m"]),
            "hard_constraint_violation_count_delta": int(
                treatment_metrics["hard_constraint_violation_count"]
            )
            - int(control_metrics["hard_constraint_violation_count"]),
            "incorrect_binding_count_delta": int(
                treatment_metrics["incorrect_binding_count"]
            )
            - int(control_metrics["incorrect_binding_count"]),
        }
        control_time = control_metrics.get("time_to_five_meter_mean_s")
        treatment_time = treatment_metrics.get("time_to_five_meter_mean_s")
        deltas["time_to_five_meter_delta_s"] = (
            float(treatment_time) - float(control_time)
            if control_time is not None and treatment_time is not None
            else None
        )
        deltas["time_to_five_meter_delta_reason"] = (
            None
            if deltas["time_to_five_meter_delta_s"] is not None
            else "one_or_both_arms_have_no_five_meter_success"
        )
        result["paired_physical_effect"] = _availability(True, deltas, None)
        criteria = {
            "success_count_not_lower": deltas["success_count_delta"] >= 0,
            "mean_closest_distance_not_greater": (
                deltas["mean_closest_distance_delta_m"] <= 1.0e-9
            ),
            "hard_constraint_count_not_greater": (
                deltas["hard_constraint_violation_count_delta"] <= 0
            ),
            "incorrect_binding_count_not_greater": (
                deltas["incorrect_binding_count_delta"] <= 0
            ),
        }
        result["paired_non_degradation"] = _availability(
            True,
            {
                "criteria_version": "d6.paired-physical-non-degradation.v1",
                "overall": all(criteria.values()),
                "criteria": criteria,
                "time_to_five_meter_is_reported_but_not_required_when_unavailable": True,
            },
            None,
        )
    else:
        result["paired_physical_effect"] = _availability(
            False,
            None,
            "complete_control_and_treatment_physical_windows_required",
        )
        result["paired_non_degradation"] = _availability(
            False,
            None,
            "paired_physical_effect_unavailable",
        )
    required_degraded_layers = (
        "d4_degraded_adoption",
        "plan_consumption",
        "guidance_lineage",
        "physical_window",
    )
    if all(result[name].get("available") is True for name in required_degraded_layers):
        d4_value = _mapping(
            result["d4_degraded_adoption"].get("value"),
            "paired D4 adoption value",
        )
        physical_deltas = _mapping(
            result["paired_physical_effect"].get("value"),
            "paired physical deltas",
        )
        result["degraded_paired_physical_comparison"] = _availability(
            True,
            {
                "comparison_scope": PAIRED_ISOLATED_COMPARISON_SCOPE,
                "intervention_kind": d4_value["intervention_kind"],
                "region_count": int(
                    _mapping(d4_value["control"], "control D4 summary")[
                        "region_count"
                    ]
                ),
                "control_d4_adoption": d4_value["control"],
                "treatment_d4_adoption": d4_value["treatment"],
                "physical_deltas": physical_deltas,
                "production_runtime_ack": False,
                "counterfactual_claim_allowed": False,
                "causal_claim_allowed": False,
                "degradation_effectiveness_claim_allowed": False,
            },
            None,
        )
    elif result["d4_degraded_adoption"].get("status") == "not_applicable":
        result["degraded_paired_physical_comparison"] = {
            "available": False,
            "status": "not_applicable",
            "value": None,
            "reason": None,
        }
    else:
        missing = [
            name
            for name in required_degraded_layers
            if result[name].get("available") is not True
        ]
        result["degraded_paired_physical_comparison"] = _availability(
            False,
            None,
            f"required_evidence_unavailable:{','.join(missing)}",
        )
    result["counterfactual"] = _availability(
        False,
        None,
        "paired_isolated_trajectories_are_observed_comparisons_not_counterfactual_proof",
    )
    result["causal"] = _availability(
        False,
        None,
        "shared_exogenous_schedules_do_not_establish_causal_identification",
    )
    return result


def _aggregate_pair_results(
    pair_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    layers = (
        "plan_consumption",
        "guidance_lineage",
        "physical_window",
        "d4_degraded_adoption",
        "paired_physical_effect",
        "paired_non_degradation",
        "degraded_paired_physical_comparison",
        "counterfactual",
        "causal",
    )
    coverage: dict[str, Any] = {}
    for layer in layers:
        layer_values = [
            _mapping(
                _mapping(item.get("availability"), "pair availability").get(layer),
                f"pair availability {layer}",
            )
            for item in pair_results
        ]
        count = sum(item.get("available") is True for item in layer_values)
        not_applicable_count = sum(
            item.get("status") == "not_applicable" for item in layer_values
        )
        coverage[layer] = {
            "available_pair_count": count,
            "not_applicable_pair_count": not_applicable_count,
            "unavailable_pair_count": (
                len(pair_results) - count - not_applicable_count
            ),
            "total_pair_count": len(pair_results),
            "complete": count == len(pair_results),
        }
    physical_complete = coverage["physical_window"]["complete"]
    arm_aggregate: dict[str, Any] = {}
    for arm_kind in ("control", "treatment"):
        metrics = [
            _mapping(
                _mapping(item.get("arms"), "pair arms")[arm_kind]["metrics"],
                f"{arm_kind} metrics",
            )
            for item in pair_results
        ]
        if physical_complete:
            time_values = [
                float(item["time_to_five_meter_mean_s"])
                for item in metrics
                if item.get("time_to_five_meter_mean_s") is not None
            ]
            arm_aggregate[arm_kind] = _availability(
                True,
                {
                    "success_count_total": sum(
                        int(item["success_count"]) for item in metrics
                    ),
                    "successful_binding_count_total": sum(
                        int(item["successful_binding_count"]) for item in metrics
                    ),
                    "mean_closest_distance_m": _mean(
                        [float(item["mean_closest_distance_m"]) for item in metrics]
                    ),
                    "time_to_five_meter_mean_s": (
                        _mean(time_values) if time_values else None
                    ),
                    "time_to_five_meter_seed_count": len(time_values),
                    "hard_constraint_violation_count_total": sum(
                        int(item["hard_constraint_violation_count"])
                        for item in metrics
                    ),
                    "incorrect_binding_count_total": sum(
                        int(item["incorrect_binding_count"]) for item in metrics
                    ),
                },
                None,
            )
        else:
            arm_aggregate[arm_kind] = _availability(
                False,
                None,
                "aggregate_requires_complete_physical_window_coverage",
            )
    effect_values = [
        _mapping(
            _mapping(item.get("availability"), "pair availability")[
                "paired_physical_effect"
            ]["value"],
            "paired effect value",
        )
        for item in pair_results
        if _mapping(item.get("availability"), "pair availability")[
            "paired_physical_effect"
        ]["available"]
    ]
    if len(effect_values) == len(pair_results):
        delta_fields = (
            "success_count_delta",
            "successful_binding_count_delta",
            "mean_closest_distance_delta_m",
            "closest_distance_delta_m",
            "hard_constraint_violation_count_delta",
            "incorrect_binding_count_delta",
        )
        paired_delta_value = {
            f"{field}_mean": _mean([float(item[field]) for item in effect_values])
            for field in delta_fields
        }
        time_deltas = [
            float(item["time_to_five_meter_delta_s"])
            for item in effect_values
            if item.get("time_to_five_meter_delta_s") is not None
        ]
        paired_delta_value["time_to_five_meter_delta_s_mean"] = (
            _mean(time_deltas) if time_deltas else None
        )
        paired_delta_value["time_to_five_meter_delta_seed_count"] = len(time_deltas)
        paired_effect = _availability(True, paired_delta_value, None)
    else:
        paired_effect = _availability(
            False,
            None,
            "aggregate_requires_complete_paired_physical_effect_coverage",
        )
    non_degradation_values = [
        _mapping(
            _mapping(item.get("availability"), "pair availability")[
                "paired_non_degradation"
            ]["value"],
            "paired non-degradation value",
        )
        for item in pair_results
        if _mapping(item.get("availability"), "pair availability")[
            "paired_non_degradation"
        ]["available"]
    ]
    non_degradation = (
        _availability(
            True,
            {
                "pass_count": sum(bool(item["overall"]) for item in non_degradation_values),
                "pair_count": len(non_degradation_values),
                "pass_rate": sum(bool(item["overall"]) for item in non_degradation_values)
                / len(non_degradation_values),
            },
            None,
        )
        if len(non_degradation_values) == len(pair_results)
        else _availability(
            False,
            None,
            "aggregate_requires_complete_paired_non_degradation_coverage",
        )
    )
    d4_arm_aggregate: dict[str, Any] = {}
    for arm_kind in ("control", "treatment"):
        arm_layers = [
            _mapping(
                _mapping(
                    _mapping(item.get("arms"), "pair arms")[arm_kind].get(
                        "availability"
                    ),
                    f"{arm_kind} availability",
                ).get("d4_degraded_adoption"),
                f"{arm_kind} D4 adoption",
            )
            for item in pair_results
        ]
        summaries = [
            _mapping(item.get("value"), f"{arm_kind} D4 summary")
            for item in arm_layers
            if isinstance(item.get("value"), Mapping)
        ]
        reason_counts: dict[str, int] = {}
        intervention_counts: dict[str, int] = {}
        for summary in summaries:
            for reason, count in _mapping(
                summary.get("reason_counts"), f"{arm_kind} D4 reasons"
            ).items():
                reason_counts[str(reason)] = reason_counts.get(str(reason), 0) + int(
                    count
                )
            intervention = str(summary.get("intervention_kind"))
            intervention_counts[intervention] = (
                intervention_counts.get(intervention, 0) + 1
            )
        d4_arm_aggregate[arm_kind] = {
            "declared_pair_count": len(summaries),
            "not_declared_pair_count": sum(
                item.get("status") == "not_declared" for item in arm_layers
            ),
            "not_applicable_pair_count": sum(
                item.get("status") == "not_applicable" for item in arm_layers
            ),
            "region_count": sum(int(item["region_count"]) for item in summaries),
            "available_count": sum(
                int(item["available_count"]) for item in summaries
            ),
            "reason_counts": dict(sorted(reason_counts.items())),
            "intervention_kind_counts": dict(sorted(intervention_counts.items())),
        }
    d4_pair_layers = [
        _mapping(
            _mapping(item.get("availability"), "pair availability").get(
                "d4_degraded_adoption"
            ),
            "pair D4 degraded adoption",
        )
        for item in pair_results
    ]
    d4_pair_statuses = [str(item.get("status")) for item in d4_pair_layers]
    d4_aggregate_value = {
        "applicable_pair_count": sum(
            item.get("available") is True for item in d4_pair_layers
        ),
        "not_applicable_pair_count": sum(
            status == "not_applicable" for status in d4_pair_statuses
        ),
        "control": d4_arm_aggregate["control"],
        "treatment": d4_arm_aggregate["treatment"],
    }
    if all(
        status in {"available", "not_applicable"} for status in d4_pair_statuses
    ) and any(status == "available" for status in d4_pair_statuses):
        d4_aggregate = _availability(True, d4_aggregate_value, None)
    elif all(status == "not_applicable" for status in d4_pair_statuses):
        d4_aggregate = {
            "available": False,
            "status": "not_applicable",
            "value": d4_aggregate_value,
            "reason": None,
        }
    else:
        d4_aggregate = {
            "available": False,
            "status": "unavailable",
            "value": d4_aggregate_value,
            "reason": "aggregate_contains_incomplete_d4_adoption_evidence",
        }

    degraded_layers = [
        _mapping(
            _mapping(item.get("availability"), "pair availability").get(
                "degraded_paired_physical_comparison"
            ),
            "degraded paired physical comparison",
        )
        for item in pair_results
    ]
    degraded_statuses = [str(item.get("status")) for item in degraded_layers]
    degraded_values = [
        _mapping(item.get("value"), "degraded paired value")
        for item in degraded_layers
        if item.get("available") is True
    ]
    if degraded_values and all(
        status in {"available", "not_applicable"} for status in degraded_statuses
    ):
        physical_values = [
            _mapping(item.get("physical_deltas"), "degraded physical deltas")
            for item in degraded_values
        ]
        fields = (
            "success_count_delta",
            "successful_binding_count_delta",
            "mean_closest_distance_delta_m",
            "closest_distance_delta_m",
            "hard_constraint_violation_count_delta",
            "incorrect_binding_count_delta",
        )
        value = {
            "comparison_scope": PAIRED_ISOLATED_COMPARISON_SCOPE,
            "applicable_pair_count": len(degraded_values),
            "not_applicable_pair_count": sum(
                status == "not_applicable" for status in degraded_statuses
            ),
            "physical_delta_means": {
                field: _mean([float(item[field]) for item in physical_values])
                for field in fields
            },
            "production_runtime_ack": False,
            "counterfactual_claim_allowed": False,
            "causal_claim_allowed": False,
            "degradation_effectiveness_claim_allowed": False,
        }
        degraded_aggregate = _availability(True, value, None)
    elif all(status == "not_applicable" for status in degraded_statuses):
        degraded_aggregate = {
            "available": False,
            "status": "not_applicable",
            "value": None,
            "reason": None,
        }
    else:
        degraded_aggregate = _availability(
            False,
            None,
            "aggregate_requires_complete_applicable_d4_and_physical_evidence",
        )
    return {
        "pair_count": len(pair_results),
        "seed_count": len({int(item["seed"]) for item in pair_results}),
        "availability_coverage": coverage,
        "arm_metrics": arm_aggregate,
        "paired_physical_effect": paired_effect,
        "paired_non_degradation": non_degradation,
        "d4_degraded_adoption": d4_aggregate,
        "degraded_paired_physical_comparison": degraded_aggregate,
        "counterfactual": _availability(
            False,
            None,
            "paired_isolated_simulation_comparison_is_not_counterfactual_proof",
        ),
        "causal": _availability(
            False,
            None,
            "paired_isolated_simulation_comparison_has_no_causal_identification_claim",
        ),
    }


def _verify_and_snapshot_inputs(
    inputs: PairedIsolatedPhysicalInputs,
) -> dict[str, dict[str, dict[str, str]]]:
    seen_paths: set[Path] = set()
    result: dict[str, dict[str, dict[str, str]]] = {}
    for pair in inputs.pairs:
        pair_hashes: dict[str, dict[str, str]] = {
            "shared": {},
            "control": {},
            "treatment": {},
        }
        for name in _SHARED_ARTIFACT_NAMES:
            artifact = getattr(pair, name)
            _expect(
                artifact.path not in seen_paths,
                "duplicate_input_path",
                f"input path reused: {artifact.path}",
            )
            seen_paths.add(artifact.path)
            pair_hashes["shared"][name] = _verify_file(
                artifact.path, artifact.sha256, f"{pair.pair_id}.shared.{name}"
            )
        for arm_kind, arm in (("control", pair.control), ("treatment", pair.treatment)):
            for name in arm.declared_artifact_names:
                artifact = getattr(arm, name)
                _expect(
                    artifact.path not in seen_paths,
                    "duplicate_input_path",
                    f"input path reused: {artifact.path}",
                )
                seen_paths.add(artifact.path)
                pair_hashes[arm_kind][name] = _verify_file(
                    artifact.path,
                    artifact.sha256,
                    f"{pair.pair_id}.{arm_kind}.{name}",
                )
        result[pair.pair_id] = pair_hashes
    return result


def _snapshot_inputs(
    inputs: PairedIsolatedPhysicalInputs,
) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for pair in inputs.pairs:
        result[pair.pair_id] = {
            "shared": {
                name: _sha256_file(getattr(pair, name).path)
                for name in _SHARED_ARTIFACT_NAMES
            },
            "control": {
                name: _sha256_file(getattr(pair.control, name).path)
                for name in pair.control.declared_artifact_names
            },
            "treatment": {
                name: _sha256_file(getattr(pair.treatment, name).path)
                for name in pair.treatment.declared_artifact_names
            },
        }
    return result


def _all_input_paths(inputs: PairedIsolatedPhysicalInputs) -> set[Path]:
    paths: set[Path] = set()
    for pair in inputs.pairs:
        paths.update(getattr(pair, name).path for name in _SHARED_ARTIFACT_NAMES)
        for arm in (pair.control, pair.treatment):
            paths.update(
                getattr(arm, name).path for name in arm.declared_artifact_names
            )
    return paths


def _normalise_assignments(
    value: Any,
    *,
    context: str,
) -> tuple[tuple[str, str], ...]:
    assignments = _sequence(value, f"{context} assignments")
    result: list[tuple[str, str]] = []
    resources: set[str] = set()
    for index, raw in enumerate(assignments):
        item = _mapping(raw, f"{context} assignment {index}")
        resource_id = _required_string(
            item, "resource_id", f"{context} assignment {index}"
        )
        track_id = _required_string(
            item, "global_track_id", f"{context} assignment {index}"
        )
        _expect(
            resource_id not in resources,
            "duplicate_resource_in_d3_plan",
            f"{context} assignment {index}",
        )
        resources.add(resource_id)
        result.append((resource_id, track_id))
    return tuple(result)


def _position_mapping(value: Any, context: str) -> dict[str, tuple[float, float, float]]:
    mapping = _mapping(value, context)
    return {
        str(entity_id): _position(position, f"{context}.{entity_id}")
        for entity_id, position in mapping.items()
    }


def _position(value: Any, context: str) -> tuple[float, float, float]:
    sequence = _sequence(value, context)
    _expect(len(sequence) == 3, "invalid_ned_position", context)
    return (
        _number(sequence[0], context),
        _number(sequence[1], context),
        _number(sequence[2], context),
    )


def _positions_close(
    actual: Mapping[str, tuple[float, float, float]],
    expected: Mapping[str, tuple[float, float, float]],
) -> bool:
    return set(actual) == set(expected) and all(
        all(math.isclose(a, b, rel_tol=0.0, abs_tol=1.0e-9) for a, b in zip(actual[key], expected[key]))
        for key in actual
    )


def _distance(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _availability(
    available: bool,
    value: Any,
    reason: str | None,
) -> dict[str, Any]:
    _expect(
        (available and value is not None and reason is None)
        or (not available and value is None and isinstance(reason, str) and reason),
        "invalid_availability_record",
        "available requires a value; unavailable requires null value and reason",
    )
    return {
        "available": available,
        "status": "available" if available else "unavailable",
        "value": value,
        "reason": reason,
    }


def _assert_truth_free(value: Any, context: str) -> None:
    violations: list[str] = []

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                key_text = str(key)
                if key_text.lower() in _FORBIDDEN_ONLINE_KEYS:
                    violations.append(f"{path}.{key_text}")
                visit(nested, f"{path}.{key_text}")
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for index, nested in enumerate(item):
                visit(nested, f"{path}[{index}]")

    visit(value, context)
    _expect(
        not violations,
        "online_truth_field_detected",
        f"{context} contains forbidden online truth fields: {violations[:3]}",
    )


def _verify_file(path: Path, expected_sha256: Any, context: str) -> str:
    _expect(path.is_file(), "input_artifact_missing", f"{context}: {path}")
    expected = _normalise_sha256(expected_sha256)
    actual = _sha256_file(path)
    _expect(
        actual == expected,
        "input_artifact_hash_mismatch",
        f"{context}: expected {expected}, actual {actual}",
    )
    return actual


def _load_json(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("invalid_json_artifact", f"{context}: {exc}")
    return dict(_mapping(value, context))


def _load_jsonl(path: Path, context: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        _fail("invalid_jsonl_artifact", f"{context}: {exc}")
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail("invalid_jsonl_artifact", f"{context} line {index}: {exc}")
        records.append(dict(_mapping(value, f"{context} line {index}")))
    return records


def _canonical_payload_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        _fail("non_canonical_json_payload", str(exc))
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_sha256(value: Any) -> str:
    match = _SHA256_RE.fullmatch(str(value))
    if match is None:
        _fail("invalid_sha256", f"invalid SHA-256 value: {value!r}")
    return match.group(1)


def _write_json(path: Path, value: Any) -> None:
    _write_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
    )


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("expected_mapping", f"{context} must be a mapping")
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail("expected_sequence", f"{context} must be a sequence")
    return value


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: set[str],
    context: str,
) -> None:
    actual = set(payload)
    _expect(
        actual == expected,
        "unexpected_contract_keys",
        f"{context}: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}",
    )


def _required_string(
    payload: Mapping[str, Any],
    key: str,
    context: str,
) -> str:
    value = payload.get(key)
    _expect(
        isinstance(value, str) and bool(value),
        "invalid_required_string",
        f"{context}.{key} must be a non-empty string",
    )
    return str(value)


def _integer(value: Any, context: str) -> int:
    _expect(
        isinstance(value, int) and not isinstance(value, bool),
        "invalid_integer",
        context,
    )
    return int(value)


def _nonnegative_int(value: Any, context: str) -> int:
    result = _integer(value, context)
    _expect(result >= 0, "negative_integer", context)
    return result


def _number(value: Any, context: str) -> float:
    _expect(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        "invalid_finite_number",
        context,
    )
    return float(value)


def _nonnegative_float(value: Any, context: str) -> float:
    result = _number(value, context)
    _expect(result >= 0.0, "negative_number", context)
    return result


def _positive_float(value: Any, context: str) -> float:
    result = _number(value, context)
    _expect(result > 0.0, "nonpositive_number", context)
    return result


def _strict_bool(value: Any, context: str) -> bool:
    _expect(isinstance(value, bool), "invalid_boolean", context)
    return bool(value)


def _mean(values: Sequence[float]) -> float:
    _expect(bool(values), "empty_mean", "cannot compute mean of empty values")
    return sum(values) / len(values)


def _metric(value: Any) -> str:
    if value is None:
        return "不可用"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _cn_available(value: Any) -> str:
    item = _mapping(value, "availability display")
    if item.get("available"):
        return "可用"
    if item.get("status") == "not_applicable":
        return "不适用"
    if item.get("status") == "not_declared":
        return "未声明"
    return "不可用"


def _expect(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise PairedIsolatedPhysicalEvaluationError(code, message)


def _fail(code: str, message: str) -> None:
    raise PairedIsolatedPhysicalEvaluationError(code, message)
