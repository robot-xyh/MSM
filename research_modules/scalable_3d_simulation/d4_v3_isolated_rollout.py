"""Isolated control/treatment episodes for the frozen D4 readiness-v3 model.

The D4 model remains a development-only shadow candidate.  This main-owned
adapter gives it one explicit intervention opportunity inside an isolated
treatment episode without pretending that the ordinary ``assist`` gate has
opened.  A deterministic control episode supplies the source snapshot and the
same exogenous configuration is then replayed in a separate treatment world.

Only a fully bound, gate-passed, projected and still-valid D4 advisory may be
translated into a D3 regional hint for the next planning cycle.  Production
ACK, failover authority, coalition authority and control authority remain
false throughout this module.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import shutil
from typing import Any, Mapping, Sequence
import uuid

import numpy as np

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    REGION_RESOURCE_V3_DEVELOPMENT_SEEDS,
    RegionResourceAdvisoryGate,
    RegionResourcePairedInputBinding,
    RegionResourceV3IsolatedPairedAdvisor,
    RegionResourceV3IsolatedPairedDecision,
    build_region_resource_v3_development_paired_specification,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    REGIONAL_PLANNING_HINT_SCHEMA_V1,
)

from .episode_bus import jsonable
from .experiment_matrix import paired_exogenous_config_sha256
from .module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from .orchestrator import EpisodeResult, Scalable3DEpisodeRunner
from .reporting import write_episode_outputs
from .runtime_ports import RuntimePublication, RuntimeStepOutput
from .scenarios import make_curriculum_scenario


D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION = (
    "scalable3d-d4-v3-isolated-rollout-v2"
)
D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION = (
    "scalable3d-d4-v3-isolated-runtime-record-v1"
)
D4_V3_ISOLATED_RUNTIME_TOPIC = "modules.d4.isolated_v3_treatment_evidence"
D4_V3_ISOLATED_SCOPE = "development_isolated_treatment_only"

_EPS = 1.0e-9
_PRODUCTION_PERMISSION_FIELDS = (
    "production_runtime_ack_emitted",
    "assist_authority_granted",
    "assignment_authority_granted",
    "degradation_authority_granted",
    "takeover_authority_granted",
    "coalition_commit_authority_granted",
    "control_authority_granted",
)


@dataclass(frozen=True, slots=True)
class D4V3IsolatedRolloutOptions:
    """Scenario controls for development-only D4 paired episodes."""

    scenario: str = "nominal"
    scale: int = 20
    target_count: int = 20
    resource_count: int = 20
    recon_count: int = 2
    region_count: int = 8
    duration_s: float = 3.2
    seeds: tuple[int, ...] = (2003,)
    intervention_frame_index: int = 0
    created_at_utc: str = "2026-07-29T00:00:00Z"

    def __post_init__(self) -> None:
        scenario = str(self.scenario).strip().lower()
        if not scenario:
            raise ValueError("scenario must be non-empty")
        object.__setattr__(self, "scenario", scenario)
        for name in (
            "scale",
            "target_count",
            "resource_count",
            "recon_count",
            "region_count",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if int(self.region_count) != 8:
            raise ValueError("readiness-v3 isolated rollout requires 8 regions")
        if not isfinite(float(self.duration_s)) or float(self.duration_s) <= 0.0:
            raise ValueError("duration_s must be positive and finite")
        seeds = tuple(int(seed) for seed in self.seeds)
        if not seeds or len(seeds) != len(set(seeds)):
            raise ValueError("seeds must be non-empty and unique")
        if not set(seeds).issubset(REGION_RESOURCE_V3_DEVELOPMENT_SEEDS):
            raise ValueError(
                "rollout seeds must be a subset of D4 development seeds 2003-2012"
            )
        object.__setattr__(self, "seeds", seeds)
        if int(self.intervention_frame_index) < 0:
            raise ValueError("intervention_frame_index must be non-negative")
        if not str(self.created_at_utc).strip():
            raise ValueError("created_at_utc must be non-empty")


@dataclass(frozen=True, slots=True)
class D4V3SourceEvidence:
    """Control-arm source frame used to freeze one intervention binding."""

    seed: int
    base_config: Any
    control_result: EpisodeResult | None
    binding: RegionResourcePairedInputBinding
    intervention_timestamp_s: float
    normalized_snapshot_lineage_sha256: str
    source_snapshot_payload_sha256: str

    def __post_init__(self) -> None:
        if int(self.seed) != int(self.binding.seed):
            raise ValueError("source evidence seed does not match binding")
        _require_sha256(self.normalized_snapshot_lineage_sha256)
        _require_sha256(self.source_snapshot_payload_sha256)
        if (
            self.binding.region_snapshot_lineage_sha256
            != self.normalized_snapshot_lineage_sha256
        ):
            raise ValueError("source binding has a different snapshot lineage")
        if (
            not isfinite(float(self.intervention_timestamp_s))
            or float(self.intervention_timestamp_s) < 0.0
        ):
            raise ValueError("intervention timestamp must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class D4V3IsolatedSeedPair:
    """One independently executed R0/treatment pair."""

    seed: int
    control: EpisodeResult
    treatment: EpisodeResult
    runtime_records: tuple[dict[str, Any], ...]
    same_initial_state: bool
    same_exogenous_config: bool
    worlds_isolated: bool
    buses_isolated: bool

    def __post_init__(self) -> None:
        if self.control.config.seed != self.seed or self.treatment.config.seed != self.seed:
            raise ValueError("pair result seed mismatch")
        if not all(
            (
                self.same_initial_state,
                self.same_exogenous_config,
                self.worlds_isolated,
                self.buses_isolated,
            )
        ):
            raise ValueError("isolated pair invariants are not satisfied")
        if int(self.control.summary.get("online_truth_use_count", -1)) != 0:
            raise ValueError("control episode used evaluator truth online")
        if int(self.treatment.summary.get("online_truth_use_count", -1)) != 0:
            raise ValueError("treatment episode used evaluator truth online")
        if not bool(self.control.summary.get("finite_state", False)):
            raise ValueError("control episode produced non-finite state")
        if not bool(self.treatment.summary.get("finite_state", False)):
            raise ValueError("treatment episode produced non-finite state")

    def summary_payload(self) -> dict[str, Any]:
        records = self.runtime_records
        decision_records = tuple(
            item for item in records if item.get("decision") is not None
        )
        successor_records = tuple(
            item
            for item in records
            if item.get("d3_successor", {}).get("available") is True
        )
        ack_records = tuple(
            item
            for item in records
            if item.get("runtime_ack", {}).get("accepted") is True
        )
        physical_records = tuple(
            item
            for item in records
            if item.get("physical_window", {}).get(
                "physical_execution_observed"
            )
            is True
        )
        return {
            "schema_version": D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION,
            "scope": D4_V3_ISOLATED_SCOPE,
            "seed": int(self.seed),
            "control_episode_id": self.control.manifest.episode_id,
            "treatment_episode_id": self.treatment.manifest.episode_id,
            "same_initial_state": self.same_initial_state,
            "same_exogenous_config": self.same_exogenous_config,
            "worlds_isolated": self.worlds_isolated,
            "buses_isolated": self.buses_isolated,
            "runtime_record_count": len(records),
            "candidate_decision_count": len(decision_records),
            "raw_inference_count": sum(
                bool(
                    item["decision"]["treatment"].get(
                        "raw_inference_completed",
                        False,
                    )
                )
                for item in decision_records
            ),
            "runtime_gate_pass_count": sum(
                bool(
                    item["decision"]["treatment"].get(
                        "runtime_gate_passed",
                        False,
                    )
                )
                for item in decision_records
            ),
            "projection_pass_count": sum(
                bool(
                    item["decision"]["treatment"].get(
                        "projection_passed",
                        False,
                    )
                )
                for item in decision_records
            ),
            "isolated_adoption_count": sum(
                bool(
                    item["decision"]["treatment"].get(
                        "isolated_treatment_influence_adopted",
                        False,
                    )
                )
                for item in decision_records
            ),
            "d3_successor_count": len(successor_records),
            "accepted_runtime_ack_count": len(ack_records),
            "physical_execution_window_count": len(physical_records),
            "control_intercept_count": int(
                self.control.summary.get("intercepted_target_count", 0)
            ),
            "treatment_intercept_count": int(
                self.treatment.summary.get("intercepted_target_count", 0)
            ),
            "control_minimum_distance_m": _minimum_distance(self.control),
            "treatment_minimum_distance_m": _minimum_distance(self.treatment),
            "production_runtime_ack_emitted": False,
            "runtime_authority_granted": False,
            "model_promotion_authority_granted": False,
            "paired_non_degradation_available": False,
            "positive_benefit_available": False,
            "availability_reason": "D6 paired outcome audit has not been attached",
        }


@dataclass(frozen=True, slots=True)
class D4V3IsolatedRolloutExecution:
    """In-memory development pair inventory."""

    options: D4V3IsolatedRolloutOptions
    specification_id: str
    specification_sha256: str
    candidate_identity_sha256: str
    pairs: tuple[D4V3IsolatedSeedPair, ...]

    def __post_init__(self) -> None:
        if tuple(pair.seed for pair in self.pairs) != self.options.seeds:
            raise ValueError("pair inventory differs from requested seed order")
        if not self.specification_id:
            raise ValueError("specification_id must be non-empty")
        _require_sha256(self.specification_sha256)
        _require_sha256(self.candidate_identity_sha256)


class _V3TreatmentProvider:
    """Trigger exactly one v3 decision on the frozen source-frame lineage."""

    def __init__(
        self,
        *,
        advisor: RegionResourceV3IsolatedPairedAdvisor,
        binding: RegionResourcePairedInputBinding,
        expected_timestamp_s: float,
        expected_snapshot_lineage_sha256: str,
    ) -> None:
        self.advisor = advisor
        self.binding = binding
        self.expected_timestamp_s = float(expected_timestamp_s)
        self.expected_snapshot_lineage_sha256 = (
            expected_snapshot_lineage_sha256
        )
        self.projector = advisor.executor.projector
        self.attempted = False
        self.events: list[dict[str, Any]] = []

    def evaluate_if_due(
        self,
        *,
        snapshot: Any,
        formal_decision: Any,
        evaluated_at_s: float,
    ) -> RegionResourceV3IsolatedPairedDecision | None:
        if self.attempted:
            return None
        now = float(evaluated_at_s)
        if now + _EPS < self.expected_timestamp_s:
            return None
        self.attempted = True
        actual_lineage = normalized_region_snapshot_lineage_sha256(snapshot)
        event: dict[str, Any] = {
            "schema_version": D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION,
            "scope": D4_V3_ISOLATED_SCOPE,
            "seed": int(self.binding.seed),
            "evaluation_timestamp_s": now,
            "expected_intervention_timestamp_s": self.expected_timestamp_s,
            "expected_snapshot_lineage_sha256": (
                self.expected_snapshot_lineage_sha256
            ),
            "observed_snapshot_lineage_sha256": actual_lineage,
            "trigger_passed": False,
            "trigger_rejection_reasons": [],
            "decision": None,
            "isolated_consumption": {
                "attempted": False,
                "consumable": False,
                "rejection_reasons": [],
            },
            "d3_successor": {
                "available": False,
                "hint_applied": False,
                "plan_id": None,
                "plan_version": None,
                "rejection_reason": None,
            },
            "runtime_ack": {
                "available": False,
                "accepted": False,
                "fully_bound_to_guidance": False,
            },
            "physical_window": {
                "available": False,
                "physical_execution_observed": False,
                "window_complete": False,
            },
            "production_runtime_ack_emitted": False,
            "assist_authority_granted": False,
            "assignment_authority_granted": False,
            "degradation_authority_granted": False,
            "takeover_authority_granted": False,
            "coalition_commit_authority_granted": False,
            "control_authority_granted": False,
            "revision": 1,
        }
        reasons: list[str] = []
        if not np.isclose(
            now,
            self.expected_timestamp_s,
            rtol=0.0,
            atol=_EPS,
        ):
            reasons.append("intervention_timestamp_mismatch")
        if actual_lineage != self.expected_snapshot_lineage_sha256:
            reasons.append("normalized_snapshot_lineage_mismatch")
        if int(snapshot.seed) != int(self.binding.seed):
            reasons.append("snapshot_seed_mismatch")
        if snapshot.scenario_id != self.binding.scenario_id:
            reasons.append("snapshot_scenario_id_mismatch")
        if snapshot.scenario_version != self.binding.scenario_version:
            reasons.append("snapshot_scenario_version_mismatch")
        if reasons:
            event["trigger_rejection_reasons"] = reasons
            self.events.append(event)
            return None

        event["trigger_passed"] = True
        decision = self.advisor.advise_pair(
            seed=self.binding.seed,
            observed_input_binding=self.binding,
            snapshot=snapshot,
            evaluated_at_s=now,
            formal_decision=formal_decision,
        )
        event["decision"] = decision.to_dict()
        self.events.append(event)
        return decision


class _V3IsolatedTreatmentStack(IntegratedScalableModuleStack):
    """Integrated D1-D7 stack with a separate isolated D4 treatment port."""

    def __init__(
        self,
        *,
        provider: _V3TreatmentProvider,
        config: IntegratedStackConfig,
    ) -> None:
        super().__init__(config=config)
        self._v3_provider = provider
        self._v3_pending_decision: (
            RegionResourceV3IsolatedPairedDecision | None
        ) = None
        self._v3_pending_event: dict[str, Any] | None = None
        self._v3_hint_event: dict[str, Any] | None = None
        self._v3_gate = RegionResourceAdvisoryGate(
            projector=provider.projector
        )
        self._v3_published_revisions: dict[int, int] = {}

    def _run_d4_region_resource_advisor(
        self,
        step_input: Any,
        *,
        formal_snapshot: Any,
        now: float,
    ) -> None:
        super()._run_d4_region_resource_advisor(
            step_input,
            formal_snapshot=formal_snapshot,
            now=now,
        )
        snapshot = self.latest_d4_region_snapshot
        if snapshot is None or self.latest_d4_decision is None:
            return
        decision = self._v3_provider.evaluate_if_due(
            snapshot=snapshot,
            formal_decision=self.latest_d4_decision,
            evaluated_at_s=now,
        )
        if decision is not None:
            self._v3_pending_decision = decision
            self._v3_pending_event = self._v3_provider.events[-1]

    def _d3_regional_hint_from_previous_d4(
        self,
        *,
        previous_plan: Any | None,
        advice_result: Any | None,
        source_snapshot: Any | None,
        source_decision: Any | None,
        now: float,
        fault_generation_changed: bool,
    ) -> Mapping[str, Any] | None:
        decision = self._v3_pending_decision
        event = self._v3_pending_event
        if decision is not None and event is not None:
            self._v3_pending_decision = None
            self._v3_pending_event = None
            hint = self._consume_v3_treatment_decision(
                decision=decision,
                event=event,
                previous_plan=previous_plan,
                source_snapshot=source_snapshot,
                source_decision=source_decision,
                now=now,
                fault_generation_changed=fault_generation_changed,
            )
            if hint is not None:
                self._v3_hint_event = event
                return hint
        return super()._d3_regional_hint_from_previous_d4(
            previous_plan=previous_plan,
            advice_result=advice_result,
            source_snapshot=source_snapshot,
            source_decision=source_decision,
            now=now,
            fault_generation_changed=fault_generation_changed,
        )

    def _consume_v3_treatment_decision(
        self,
        *,
        decision: RegionResourceV3IsolatedPairedDecision,
        event: dict[str, Any],
        previous_plan: Any | None,
        source_snapshot: Any | None,
        source_decision: Any | None,
        now: float,
        fault_generation_changed: bool,
    ) -> Mapping[str, Any] | None:
        consumption = event["isolated_consumption"]
        consumption["attempted"] = True
        reasons = _v3_decision_rejection_reasons(decision)
        if fault_generation_changed:
            reasons.append("fault_generation_changed_before_isolated_consumption")
        if previous_plan is None:
            reasons.append("previous_plan_missing")
        if source_snapshot is None or source_decision is None:
            reasons.append("source_authority_evidence_missing")

        advisory = decision.treatment.advisory_contract
        if previous_plan is not None:
            expected_source = (
                str(previous_plan.plan_id),
                int(previous_plan.version),
            )
            if tuple(advisory.source_plan_versions) != (expected_source,):
                reasons.append("source_plan_identity_mismatch")
        if source_snapshot is not None and (
            normalized_region_snapshot_lineage_sha256(source_snapshot)
            != self._v3_provider.expected_snapshot_lineage_sha256
        ):
            reasons.append("source_snapshot_lineage_changed")

        view = None
        if not reasons:
            try:
                view = self._v3_gate.consume(
                    advisory,
                    source_snapshot,
                    evaluated_at_s=now,
                    formal_decision=source_decision,
                )
            except Exception as exc:
                reasons.append(
                    "isolated_advisory_gate_error:"
                    f"{type(exc).__name__}:{str(exc).strip()}"
                )
            else:
                if not view.consumable:
                    reasons.extend(
                        f"isolated_advisory_rejected:{reason}"
                        for reason in view.rejection_reasons
                    )
        consumption["consumable"] = bool(view is not None and view.consumable)
        consumption["rejection_reasons"] = list(dict.fromkeys(reasons))
        consumption["evaluated_at_s"] = float(now)
        consumption["view"] = None if view is None else view.to_dict()
        event["revision"] = int(event["revision"]) + 1
        if reasons or view is None or not view.consumable:
            self._d4_region_hint_bridge_rejection_reason = (
                reasons[0] if reasons else "isolated_advisory_not_consumable"
            )
            return None

        hint = _regional_hint_from_advisory(
            advisory,
            previous_plan=previous_plan,
            advisory_version=self._next_d4_region_hint_version,
        )
        self._next_d4_region_hint_version += 1
        consumption["regional_hint_sha256"] = _canonical_sha256(hint)
        consumption["source_plan_id"] = str(previous_plan.plan_id)
        consumption["source_plan_version"] = int(previous_plan.version)
        self._d4_region_hint_bridge_rejection_reason = None
        return hint

    def _record_d3_regional_hint_outcome(
        self,
        plan: Any,
        regional_hint: Mapping[str, Any] | None,
    ) -> None:
        super()._record_d3_regional_hint_outcome(plan, regional_hint)
        event = self._v3_hint_event
        if event is None or regional_hint is None:
            return
        metadata = dict(getattr(plan, "metadata", {}))
        successor = event["d3_successor"]
        successor["hint_applied"] = bool(
            metadata.get("regional_hint_applied", False)
        )
        successor["available"] = bool(
            successor["hint_applied"]
            and metadata.get("regional_hint_successor_plan_available", False)
            and metadata.get("regional_hint_successor_plan_id")
            == getattr(plan, "plan_id", None)
            and metadata.get("regional_hint_successor_plan_version")
            == getattr(plan, "version", None)
        )
        successor["plan_id"] = (
            str(plan.plan_id) if successor["available"] else None
        )
        successor["plan_version"] = (
            int(plan.version) if successor["available"] else None
        )
        successor["rejection_reason"] = (
            None
            if successor["available"]
            else (
                metadata.get("regional_hint_successor_rejection_reason")
                or metadata.get("regional_hint_fallback_reason")
                or "d3_successor_not_available"
            )
        )
        successor["metadata"] = {
            key: value
            for key, value in metadata.items()
            if str(key).startswith("regional_hint_")
        }
        event["revision"] = int(event["revision"]) + 1
        self._v3_hint_event = None

    def step(self, step_input: Any) -> RuntimeStepOutput:
        output = super().step(step_input)
        publications = list(output.publications)
        for index, event in enumerate(self._v3_provider.events):
            revision = int(event["revision"])
            if revision <= self._v3_published_revisions.get(index, 0):
                continue
            publications.append(
                RuntimePublication(
                    topic=D4_V3_ISOLATED_RUNTIME_TOPIC,
                    source="main",
                    schema_version=(
                        D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION
                    ),
                    payload=jsonable(event),
                    copy_payload=True,
                )
            )
            self._v3_published_revisions[index] = revision
        return replace(output, publications=tuple(publications))

    def v3_runtime_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            json.loads(
                json.dumps(
                    jsonable(event),
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                )
            )
            for event in self._v3_provider.events
        )


def execute_d4_v3_isolated_rollouts(
    options: D4V3IsolatedRolloutOptions,
    *,
    candidate_root: str | Path,
) -> D4V3IsolatedRolloutExecution:
    """Run source controls, freeze the v3 spec, then run treatment episodes."""

    candidate_path = Path(candidate_root)
    selected = set(options.seeds)
    sources: dict[int, D4V3SourceEvidence] = {}
    bindings: list[RegionResourcePairedInputBinding] = []

    for seed in REGION_RESOURCE_V3_DEVELOPMENT_SEEDS:
        base = _base_config(options, seed=seed)
        control_config = _arm_config(base, arm="R0")
        stack = IntegratedScalableModuleStack(
            config=_stack_config()
        )
        result = Scalable3DEpisodeRunner(
            control_config,
            module_stack=stack,
        ).run()
        frames = stack.learning_artifacts().d4_region_frames
        if options.intervention_frame_index >= len(frames):
            raise RuntimeError(
                f"seed {seed} has no D4 frame index "
                f"{options.intervention_frame_index}"
            )
        frame = frames[options.intervention_frame_index]
        if (
            float(frame.timestamp_s) + float(base.assignment_period_s)
            >= float(base.duration_s) - _EPS
        ):
            raise RuntimeError(
                f"seed {seed} has no next D3 cycle after the intervention"
            )
        normalized_lineage = normalized_region_snapshot_lineage_sha256(
            frame.snapshot
        )
        binding = RegionResourcePairedInputBinding(
            seed=seed,
            scenario_id=frame.snapshot.scenario_id,
            scenario_version=frame.snapshot.scenario_version,
            scenario_config_sha256=_canonical_sha256(base.to_dict()),
            initial_state_sha256=_initial_state_sha256(result),
            communication_schedule_sha256=_communication_schedule_sha256(base),
            fault_schedule_sha256=_fault_schedule_sha256(base),
            region_snapshot_lineage_sha256=normalized_lineage,
        )
        bindings.append(binding)
        sources[seed] = D4V3SourceEvidence(
            seed=seed,
            base_config=base,
            control_result=result if seed in selected else None,
            binding=binding,
            intervention_timestamp_s=float(frame.timestamp_s),
            normalized_snapshot_lineage_sha256=normalized_lineage,
            source_snapshot_payload_sha256=_canonical_sha256(
                frame.snapshot.to_dict()
            ),
        )

    specification = build_region_resource_v3_development_paired_specification(
        experiment_id="scalable3d-d4-v3-isolated-rollout",
        experiment_version=D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION,
        input_bindings=tuple(bindings),
        candidate_root=candidate_path,
    )
    advisor = RegionResourceV3IsolatedPairedAdvisor(
        specification,
        candidate_path,
    )

    pairs: list[D4V3IsolatedSeedPair] = []
    for seed in options.seeds:
        source = sources[seed]
        if source.control_result is None:
            raise RuntimeError("selected control result was not retained")
        provider = _V3TreatmentProvider(
            advisor=advisor,
            binding=source.binding,
            expected_timestamp_s=source.intervention_timestamp_s,
            expected_snapshot_lineage_sha256=(
                source.normalized_snapshot_lineage_sha256
            ),
        )
        treatment_stack = _V3IsolatedTreatmentStack(
            provider=provider,
            config=_stack_config(),
        )
        treatment_config = _arm_config(
            source.base_config,
            arm="A2_V3_ISOLATED_TREATMENT",
        )
        treatment = Scalable3DEpisodeRunner(
            treatment_config,
            module_stack=treatment_stack,
        ).run()
        records = [
            dict(item) for item in treatment_stack.v3_runtime_records()
        ]
        _attach_runtime_and_physical_evidence(treatment, records)
        control = source.control_result
        pairs.append(
            D4V3IsolatedSeedPair(
                seed=seed,
                control=control,
                treatment=treatment,
                runtime_records=tuple(records),
                same_initial_state=(
                    _initial_state_sha256(control)
                    == _initial_state_sha256(treatment)
                ),
                same_exogenous_config=(
                    paired_exogenous_config_sha256(control.config)
                    == paired_exogenous_config_sha256(treatment.config)
                ),
                worlds_isolated=control is not treatment,
                buses_isolated=(
                    control.online_messages is not treatment.online_messages
                ),
            )
        )

    return D4V3IsolatedRolloutExecution(
        options=options,
        specification_id=specification.specification_id,
        specification_sha256=specification.sha256,
        candidate_identity_sha256=specification.candidate_registry.sha256,
        pairs=tuple(pairs),
    )


def write_d4_v3_isolated_rollout_execution(
    output_dir: str | Path,
    execution: D4V3IsolatedRolloutExecution,
    *,
    persist_episode_outputs: bool = True,
) -> dict[str, Path]:
    """Atomically write pair evidence and optional full episode artifacts."""

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"D4 v3 rollout output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    try:
        rows: list[dict[str, Any]] = []
        for pair in execution.pairs:
            pair_dir = temporary / f"seed_{pair.seed}"
            pair_dir.mkdir()
            if persist_episode_outputs:
                write_episode_outputs(pair.control, pair_dir / "control")
                write_episode_outputs(pair.treatment, pair_dir / "treatment")
            row = pair.summary_payload()
            row["runtime_records"] = list(pair.runtime_records)
            _write_json(pair_dir / "paired_evidence.json", row)
            rows.append(row)

        manifest = {
            "schema_version": D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION,
            "scope": D4_V3_ISOLATED_SCOPE,
            "created_at_utc": execution.options.created_at_utc,
            "scenario": execution.options.scenario,
            "target_count": execution.options.target_count,
            "resource_count": execution.options.resource_count,
            "recon_count": execution.options.recon_count,
            "region_count": execution.options.region_count,
            "duration_s": execution.options.duration_s,
            "seeds": list(execution.options.seeds),
            "specification_id": execution.specification_id,
            "specification_sha256": execution.specification_sha256,
            "candidate_identity_sha256": execution.candidate_identity_sha256,
            "source_provenance": _source_provenance(execution),
            "pair_count": len(rows),
            "raw_inference_seed_count": sum(
                row["raw_inference_count"] > 0 for row in rows
            ),
            "runtime_gate_pass_seed_count": sum(
                row["runtime_gate_pass_count"] > 0 for row in rows
            ),
            "isolated_adoption_seed_count": sum(
                row["isolated_adoption_count"] > 0 for row in rows
            ),
            "d3_successor_seed_count": sum(
                row["d3_successor_count"] > 0 for row in rows
            ),
            "accepted_runtime_ack_seed_count": sum(
                row["accepted_runtime_ack_count"] > 0 for row in rows
            ),
            "physical_execution_seed_count": sum(
                row["physical_execution_window_count"] > 0 for row in rows
            ),
            "d3_successor_rejection_reason_counts": dict(
                sorted(
                    Counter(
                        str(reason)
                        for row in rows
                        for record in row["runtime_records"]
                        for reason in (
                            record.get("d3_successor", {}).get(
                                "rejection_reason"
                            ),
                        )
                        if reason
                    ).items()
                )
            ),
            "isolated_consumption_rejection_reason_counts": dict(
                sorted(
                    Counter(
                        str(reason)
                        for row in rows
                        for record in row["runtime_records"]
                        for reason in record.get(
                            "isolated_consumption",
                            {},
                        ).get("rejection_reasons", ())
                    ).items()
                )
            ),
            "same_initial_state_count": sum(
                row["same_initial_state"] for row in rows
            ),
            "same_exogenous_config_count": sum(
                row["same_exogenous_config"] for row in rows
            ),
            "online_truth_use_count": sum(
                int(pair.control.summary.get("online_truth_use_count", 0))
                + int(pair.treatment.summary.get("online_truth_use_count", 0))
                for pair in execution.pairs
            ),
            "finite_pair_count": sum(
                bool(pair.control.summary.get("finite_state", False))
                and bool(pair.treatment.summary.get("finite_state", False))
                for pair in execution.pairs
            ),
            "production_permissions": {
                "runtime_ack": False,
                "assist": False,
                "assignment": False,
                "degradation": False,
                "takeover": False,
                "coalition_commit": False,
                "control": False,
                "model_promotion": False,
            },
            "d6_paired_non_degradation_available": False,
            "positive_benefit_available": False,
            "pair_summary_sha256": _canonical_sha256(rows),
        }
        _write_json(temporary / "manifest.json", manifest)
        _write_jsonl(temporary / "paired_evidence.jsonl", rows)
        (temporary / "D4_V3_ISOLATED_ROLLOUT_REPORT_CN.md").write_text(
            _render_report(manifest, rows),
            encoding="utf-8",
        )
        hashes = {
            str(path.relative_to(temporary)): _file_sha256(path)
            for path in sorted(temporary.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS"
        }
        (temporary / "SHA256SUMS").write_text(
            "".join(
                f"{digest}  {name}\n"
                for name, digest in sorted(hashes.items())
            ),
            encoding="utf-8",
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "manifest": output / "manifest.json",
        "paired_evidence": output / "paired_evidence.jsonl",
        "report_cn": output / "D4_V3_ISOLATED_ROLLOUT_REPORT_CN.md",
        "sha256sums": output / "SHA256SUMS",
    }


def normalized_region_snapshot_lineage_sha256(snapshot: Any) -> str:
    """Hash a cross-episode snapshot view without UUID-like D3 plan IDs."""

    payload = dict(snapshot.to_dict())
    payload["authority_digest"] = "normalized-per-arm-authority"
    regions: list[dict[str, Any]] = []
    for raw in payload.get("regions", ()):
        region = dict(raw)
        region["plan_id"] = (
            f"normalized-plan-version-{int(region.get('plan_version', 0))}"
        )
        regions.append(region)
    payload["regions"] = regions
    return _canonical_sha256(payload)


def _v3_decision_rejection_reasons(
    decision: RegionResourceV3IsolatedPairedDecision,
) -> list[str]:
    reasons: list[str] = []
    treatment = decision.treatment
    for name in _PRODUCTION_PERMISSION_FIELDS:
        if bool(getattr(decision, name, False)):
            reasons.append(f"paired_decision_permission_true:{name}")
        if bool(getattr(treatment, name, False)):
            reasons.append(f"treatment_permission_true:{name}")
    required = {
        "candidate_scope_compatible": treatment.candidate_scope_compatible,
        "raw_inference_completed": treatment.raw_inference_completed,
        "runtime_gate_applied": treatment.runtime_gate_applied,
        "runtime_gate_passed": treatment.runtime_gate_passed,
        "projection_passed": treatment.projection_passed,
        "next_cycle_isolated_adoption": (
            treatment.next_cycle_isolated_adoption
        ),
        "isolated_treatment_influence_allowed": (
            treatment.isolated_treatment_influence_allowed
        ),
        "isolated_treatment_influence_adopted": (
            treatment.isolated_treatment_influence_adopted
        ),
        "pair_input_match": treatment.arm_evidence.pair_input_match,
        "candidate_bundle_match": (
            treatment.arm_evidence.candidate_bundle_match
        ),
        "candidate_thresholds_passed": (
            treatment.arm_evidence.candidate_thresholds_passed
        ),
        "candidate_safety_projection_passed": (
            treatment.arm_evidence.candidate_safety_projection_passed
        ),
        "next_cycle_consumption_passed": (
            treatment.arm_evidence.next_cycle_consumption_passed
        ),
        "isolated_treatment_safe_adopted": (
            treatment.arm_evidence.isolated_treatment_safe_adopted
        ),
    }
    reasons.extend(
        f"required_evidence_false:{name}"
        for name, passed in required.items()
        if not bool(passed)
    )
    if treatment.deterministic_rule_selected:
        reasons.append("treatment_selected_rule_fallback")
    if decision.formal_evaluation_authorized:
        reasons.append("formal_evaluation_authority_unexpected")
    return reasons


def _regional_hint_from_advisory(
    advisory: Any,
    *,
    previous_plan: Any,
    advisory_version: int,
) -> dict[str, Any]:
    expected_source = (str(previous_plan.plan_id), int(previous_plan.version))
    constraints = tuple(
        {
            "region_id": region.region_id,
            "owner_id": region.source_version.owner_id,
            "owner_layer": region.source_version.owner_layer.value,
            "owner_epoch": int(region.source_version.epoch),
            "lease_expires_at_s": float(
                region.source_version.lease_expires_at_s
            ),
            "source_plan_id": expected_source[0],
            "source_plan_version": expected_source[1],
            "resource_quota_delta": int(region.resource_quota_delta),
            "reserve_ratio": float(region.reserve_ratio),
            "hold": bool(region.hold),
            "request_replan": bool(region.request_replan),
        }
        for region in advisory.regions
    )
    transfers = tuple(
        {
            "source_region_id": transfer.source_region_id,
            "target_region_id": transfer.target_region_id,
            "resource_count": int(transfer.resource_count),
            "edge_id": transfer.edge_id,
            "expected_transfer_time_s": float(
                transfer.expected_transfer_time_s
            ),
        }
        for transfer in advisory.transfers
    )
    return {
        "schema": REGIONAL_PLANNING_HINT_SCHEMA_V1,
        "advisory_id": advisory.advisory_id,
        "advisory_version": int(advisory_version),
        "created_at_s": float(advisory.created_at_s),
        "expires_at_s": float(advisory.valid_until_s),
        "source_plan_id": expected_source[0],
        "source_plan_version": expected_source[1],
        "projected": bool(advisory.projected),
        "constraints": constraints,
        "transfer_allowances": transfers,
    }


def _attach_runtime_and_physical_evidence(
    result: EpisodeResult,
    records: list[dict[str, Any]],
) -> None:
    acknowledgements = tuple(
        item
        for item in result.online_messages
        if item.topic == "runtime.assignment_plan_ack"
    )
    guidance = tuple(
        item
        for item in result.online_messages
        if item.topic == "modules.d7.guidance_commands"
    )
    for record in records:
        successor = record.get("d3_successor", {})
        plan_id = successor.get("plan_id")
        plan_version = successor.get("plan_version")
        if not successor.get("available") or not plan_id or plan_version is None:
            continue
        matching_ack = tuple(
            item
            for item in acknowledgements
            if item.payload.get("plan_id") == plan_id
            and int(item.payload.get("plan_version", -1)) == int(plan_version)
        )
        acknowledgement = (
            None
            if not matching_ack
            else max(matching_ack, key=lambda item: item.timestamp)
        )
        record["runtime_ack"] = {
            "available": acknowledgement is not None,
            "accepted": bool(
                acknowledgement is not None
                and acknowledgement.payload.get("accepted") is True
            ),
            "fully_bound_to_guidance": bool(
                acknowledgement is not None
                and acknowledgement.payload.get("fully_bound_to_guidance")
                is True
            ),
            "timestamp_s": (
                None if acknowledgement is None else acknowledgement.timestamp
            ),
            "payload_sha256": (
                None
                if acknowledgement is None
                else _canonical_sha256(acknowledgement.payload)
            ),
        }

        decision = record.get("decision")
        if not isinstance(decision, Mapping):
            continue
        advisory = decision["treatment"]["advisory_contract"]
        window_start = float(
            record["isolated_consumption"].get(
                "evaluated_at_s",
                record["evaluation_timestamp_s"],
            )
        )
        window_end = float(advisory["valid_until_s"])
        matching_guidance = tuple(
            item
            for item in guidance
            if window_start - _EPS <= item.timestamp <= window_end + _EPS
        )
        commands = tuple(
            command
            for message in matching_guidance
            for command in message.payload.get("commands", ())
            if command.get("plan_id") == plan_id
            and int(command.get("plan_version", -1)) == int(plan_version)
        )
        non_hold = tuple(
            command
            for command in commands
            if command.get("mode") != "hold"
            and float(command.get("command_norm_mps2", 0.0)) > 0.0
        )
        final_timestamp = (
            float(result.timestamps[-1]) if result.timestamps.size else 0.0
        )
        hard_violations = _guidance_hard_constraint_violations(
            commands,
            finite_state=bool(result.summary.get("finite_state", False)),
        )
        record["physical_window"] = {
            "available": bool(matching_guidance),
            "window_start_s": window_start,
            "window_end_s": window_end,
            "window_complete": final_timestamp + _EPS >= window_end,
            "guidance_publication_count": len(matching_guidance),
            "matching_command_count": len(commands),
            "non_hold_control_count": len(non_hold),
            "hard_constraint_violation_count": hard_violations,
            "physical_execution_observed": bool(
                record["runtime_ack"]["accepted"]
                and record["runtime_ack"]["fully_bound_to_guidance"]
                and non_hold
                and hard_violations == 0
            ),
        }
        record["revision"] = int(record.get("revision", 0)) + 1


def _guidance_hard_constraint_violations(
    commands: Sequence[Mapping[str, Any]],
    *,
    finite_state: bool,
) -> int:
    violations = 0 if finite_state else 1
    for command in commands:
        acceleration = tuple(
            float(value)
            for value in command.get("acceleration_ned_mps2", ())
        )
        norm = float(command.get("command_norm_mps2", float("nan")))
        if (
            len(acceleration) != 3
            or not all(isfinite(value) for value in acceleration)
            or not isfinite(norm)
            or norm > 12.0 + 1.0e-6
            or not np.isclose(
                np.linalg.norm(acceleration),
                norm,
                rtol=0.0,
                atol=1.0e-6,
            )
        ):
            violations += 1
    return violations


def _base_config(options: D4V3IsolatedRolloutOptions, *, seed: int) -> Any:
    config = make_curriculum_scenario(
        options.scenario,
        scale=options.scale,
        seed=seed,
        duration_s=options.duration_s,
        target_count=options.target_count,
        resource_count=options.resource_count,
    )
    metadata = {
        **dict(config.metadata),
        "d4_v3_isolated_pairing": {
            "schema_version": D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION,
            "scope": D4_V3_ISOLATED_SCOPE,
            "candidate_influence": "one_next_cycle_treatment_only",
            "production_runtime_ack": False,
            "assist_authority": False,
            "assignment_authority": False,
            "degradation_authority": False,
            "takeover_authority": False,
            "coalition_commit_authority": False,
            "control_authority": False,
        },
    }
    return replace(
        config,
        recon_count=options.recon_count,
        region_count=options.region_count,
        sensor_random_schedule_version="entity_fixed_v1",
        metadata=metadata,
    )


def _arm_config(config: Any, *, arm: str) -> Any:
    return replace(
        config,
        metadata={
            **dict(config.metadata),
            "algorithm_variant": arm,
        },
    )


def _stack_config() -> IntegratedStackConfig:
    return IntegratedStackConfig(
        capture_learning_artifacts=True,
        d5_active_vision_enabled=False,
    )


def _initial_state_sha256(result: EpisodeResult) -> str:
    payload = {
        "intruders": result.intruder_state_history[0].astype(float).tolist(),
        "interceptors": (
            result.interceptor_state_history[0].astype(float).tolist()
        ),
        "recon": result.recon_state_history[0].astype(float).tolist(),
        "intruder_active": (
            result.intruder_active_history[0].astype(bool).tolist()
        ),
    }
    return _canonical_sha256(payload)


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
            "sensor_random_schedule_version": (
                config.sensor_random_schedule_version
            ),
        }
    )


def _fault_schedule_sha256(config: Any) -> str:
    return _canonical_sha256(
        {
            "seed": int(config.seed),
            "fault_schedule": config.metadata.get("fault_schedule", ()),
            "center_failure": bool(
                config.metadata.get(
                    "fault_schedule_runtime_required",
                    False,
                )
            ),
        }
    )


def _minimum_distance(result: EpisodeResult) -> float | None:
    if (
        result.interceptor_state_history.size == 0
        or result.intruder_state_history.size == 0
    ):
        return None
    minimum = float("inf")
    for interceptors, intruders, active in zip(
        result.interceptor_state_history,
        result.intruder_state_history,
        result.intruder_active_history,
        strict=True,
    ):
        active_targets = intruders[np.asarray(active, dtype=bool), :3]
        if not active_targets.size:
            continue
        distance = np.linalg.norm(
            interceptors[:, None, :3] - active_targets[None, :, :],
            axis=2,
        )
        minimum = min(minimum, float(np.min(distance)))
    return None if not isfinite(minimum) else minimum


def _render_report(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# D4 readiness v3 隔离双臂运行报告",
        "",
        "## 结论",
        "",
        (
            f"本批运行 {manifest['pair_count']} 组 development control/treatment "
            f"episode。初态一致 {manifest['same_initial_state_count']}/"
            f"{manifest['pair_count']}，外生配置一致 "
            f"{manifest['same_exogenous_config_count']}/{manifest['pair_count']}。"
        ),
        (
            f"来源提交为 `{manifest['source_provenance']['git_commit']}`，"
            f"工作区 dirty={str(manifest['source_provenance']['repository_dirty']).lower()}。"
            "未提交实现由 manifest 中的逐文件 SHA-256 固定。"
        ),
        (
            f"原始推理、运行门通过、隔离采用、D3 后继计划、运行确认和物理执行窗口的"
            f" seed 数分别为 {manifest['raw_inference_seed_count']}、"
            f"{manifest['runtime_gate_pass_seed_count']}、"
            f"{manifest['isolated_adoption_seed_count']}、"
            f"{manifest['d3_successor_seed_count']}、"
            f"{manifest['accepted_runtime_ack_seed_count']} 和 "
            f"{manifest['physical_execution_seed_count']}。"
        ),
        "",
        "当前结果仍是 development 隔离试验。生产运行确认、普通 assist、分配、降级、"
        "接管、联盟提交、控制和模型晋级权限均未开放。D6 尚未附加同键非退化与收益"
        "审计，因此本报告不作收益判断。",
        "",
        "## 拒绝原因",
        "",
        (
            "D3 后继计划拒绝原因："
            + (
                "无。"
                if not manifest["d3_successor_rejection_reason_counts"]
                else "；".join(
                    f"`{reason}` {count} 次"
                    for reason, count in manifest[
                        "d3_successor_rejection_reason_counts"
                    ].items()
                )
                + "。"
            )
        ),
        (
            "隔离消费拒绝原因："
            + (
                "无。"
                if not manifest[
                    "isolated_consumption_rejection_reason_counts"
                ]
                else "；".join(
                    f"`{reason}` {count} 次"
                    for reason, count in manifest[
                        "isolated_consumption_rejection_reason_counts"
                    ].items()
                )
                + "。"
            )
        ),
        "",
        "## 逐 seed 结果",
        "",
        "| seed | raw | gate | adopt | D3 后继 | ACK | 物理窗口 | R0/处理拦截 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['seed']} | {row['raw_inference_count']} | "
            f"{row['runtime_gate_pass_count']} | "
            f"{row['isolated_adoption_count']} | "
            f"{row['d3_successor_count']} | "
            f"{row['accepted_runtime_ack_count']} | "
            f"{row['physical_execution_window_count']} | "
            f"{row['control_intercept_count']}/"
            f"{row['treatment_intercept_count']} |"
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- treatment 只在冻结干预帧执行一次候选评价，并只允许影响下一次 D3 规划。",
            "- 输入不一致、身份不一致、运行门失败、投影失败、建议过期或 D3 拒绝均回退规则。",
            "- 在线模块未读取仿真真值；真值仅保存在 episode 离线评估侧。",
            "- 正式保留 seeds 1000-1019 未使用，本批不能标记为正式 holdout。",
            "",
        ]
    )
    return "\n".join(lines)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        jsonable(value),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _source_provenance(
    execution: D4V3IsolatedRolloutExecution,
) -> dict[str, Any]:
    manifests = {
        str(pair.seed): {
            "control": pair.control.manifest.to_dict(),
            "treatment": pair.treatment.manifest.to_dict(),
        }
        for pair in execution.pairs
    }
    commits = sorted(
        {
            str(payload[arm]["git_commit"])
            for payload in manifests.values()
            for arm in ("control", "treatment")
        }
    )
    root = Path(__file__).resolve().parents[2]
    relative_sources = (
        "research_modules/scalable_3d_simulation/d4_v3_isolated_rollout.py",
        "research_modules/scalable_3d_simulation/module_stack.py",
        "research_modules/scalable_3d_simulation/orchestrator.py",
        (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/models.py"
        ),
        (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/planner.py"
        ),
        (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/regional_hint.py"
        ),
        (
            "research_modules/d4_distributed_fallback/"
            "d4_distributed_fallback/region_resource_paired_intervention.py"
        ),
        (
            "research_modules/d4_distributed_fallback/"
            "d4_distributed_fallback/region_resource_v3_paired_intervention.py"
        ),
        "research_modules/scalable_3d_simulation/d6_integration.py",
        (
            "research_modules/d6_evaluation_metrics/d6_evaluation_metrics/"
            "runtime_plan_outcome_join.py"
        ),
        (
            "research_modules/d7_proportional_guidance/"
            "d7_proportional_guidance/scalable_3d_guidance.py"
        ),
    )
    source_hashes: dict[str, str] = {}
    for relative in relative_sources:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(
                f"required D4 v3 rollout implementation is missing: {relative}"
            )
        source_hashes[relative] = _file_sha256(path)
    episode_manifest_hashes = {
        seed: {
            arm: _canonical_sha256(payload)
            for arm, payload in pair_manifests.items()
        }
        for seed, pair_manifests in manifests.items()
    }
    return {
        "git_commit": commits[0] if len(commits) == 1 else None,
        "git_commits": commits,
        "git_commit_uniform": len(commits) == 1,
        "repository_dirty": any(
            bool(payload[arm]["repository_dirty"])
            for payload in manifests.values()
            for arm in ("control", "treatment")
        ),
        "episode_manifest_sha256": episode_manifest_hashes,
        "implementation_file_sha256": source_hashes,
        "implementation_set_sha256": _canonical_sha256(source_hashes),
    }


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(
        json.dumps(
            jsonable(payload),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> Path:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(
                json.dumps(
                    jsonable(row),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                )
                + "\n"
            )
    return path


def _require_sha256(value: str) -> None:
    if (
        len(str(value)) != 64
        or str(value) != str(value).lower()
        or any(character not in "0123456789abcdef" for character in str(value))
    ):
        raise ValueError("expected lowercase SHA-256")


__all__ = [
    "D4_V3_ISOLATED_ROLLOUT_SCHEMA_VERSION",
    "D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION",
    "D4_V3_ISOLATED_RUNTIME_TOPIC",
    "D4V3IsolatedRolloutExecution",
    "D4V3IsolatedRolloutOptions",
    "D4V3IsolatedSeedPair",
    "D4V3SourceEvidence",
    "execute_d4_v3_isolated_rollouts",
    "normalized_region_snapshot_lineage_sha256",
    "write_d4_v3_isolated_rollout_execution",
]
