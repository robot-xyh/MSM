"""Independent R0/candidate episode pairing for A2 and A3 audits.

The main runtime owns execution isolation and evidence routing.  D4 and D5 own
the fail-closed DTOs used here, while D6 remains a read-only consumer.  This
module never promotes a model or grants assignment, failover, camera, or
guidance authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    RegionResourceA2AuditArm,
    RegionResourceA2AuditContext,
    RegionResourceA2AuditWindowReference,
    RegionResourceA2SafeAdoptionAuditSource,
    RuleRegionResourcePolicy,
    assemble_region_resource_a2_benefit_audit_batch,
    assemble_region_resource_a2_benefit_audit_input,
)
from research_modules.d5_terminal_association.src.d5_terminal_association import (
    ActiveVisionA3PairingDisposition,
    ActiveVisionA3PhysicalObservationWindow,
    attempt_active_vision_a3_pairing,
    validate_active_vision_a3_evidence,
)
from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.strict_learning_adoption_audit import (
    audit_learning_adoption_evidence,
    build_learning_adoption_audit_input,
)

from .episode_bus import jsonable
from .experiment_matrix import paired_exogenous_config_sha256
from .models import ScenarioConfig
from .orchestrator import EpisodeResult, run_episode
from .runtime_ports import ScalableModuleStack


PAIRED_LEARNING_ADOPTION_SCHEMA_VERSION = (
    "scalable3d-paired-learning-adoption-v2"
)
PAIRED_LEARNING_ADOPTION_ARTIFACT_SCHEMA_VERSION = (
    "scalable3d-paired-learning-adoption-artifact-v2"
)
PAIRED_LEARNING_ADOPTION_BATCH_SCHEMA_VERSION = (
    "scalable3d-paired-learning-adoption-batch-v2"
)
_D4_RELEVANT_TOPICS = frozenset(
    {
        "modules.d3.assignment_plan",
        "modules.d4.regional_failover",
        "modules.d7.guidance_commands",
        "runtime.assignment_plan_ack",
    }
)
_EPS = 1.0e-9


@dataclass(frozen=True, slots=True)
class PairedLearningAdoptionResult:
    """Truth-free pair records and the resulting read-only D6 audit."""

    pairing_context_sha256: str
    scenario_id: str
    scenario_version: str
    scale: int
    seed: int
    r0_episode_id: str
    candidate_episode_id: str
    r0_event_log_sha256: str
    candidate_event_log_sha256: str
    candidate_a2_record_count: int
    candidate_a2_safe_adoption_count: int
    candidate_a3_adoption_record_count: int
    candidate_a3_pairable_record_count: int
    a1_records: tuple[dict[str, Any], ...]
    a2_records: tuple[dict[str, Any], ...]
    a3_records: tuple[dict[str, Any], ...]
    a3_pairing_dispositions: tuple[dict[str, Any], ...]
    d6_audit: dict[str, Any]
    schema_version: str = PAIRED_LEARNING_ADOPTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_LEARNING_ADOPTION_SCHEMA_VERSION:
            raise ValueError("unsupported paired learning-adoption schema")
        for value in (
            self.pairing_context_sha256,
            self.r0_event_log_sha256,
            self.candidate_event_log_sha256,
        ):
            _require_sha256(value)
        if not self.scenario_id or not self.scenario_version:
            raise ValueError("paired scenario identity must be non-empty")
        if self.scale < 1 or self.seed < 0:
            raise ValueError("paired scale must be positive and seed non-negative")
        if not self.r0_episode_id or not self.candidate_episode_id:
            raise ValueError("paired episode IDs must be non-empty")
        if self.r0_episode_id == self.candidate_episode_id:
            raise ValueError("R0 and candidate must use independent episodes")
        if self.r0_event_log_sha256 == self.candidate_event_log_sha256:
            raise ValueError("R0 and candidate event logs must be independent")
        for name in (
            "candidate_a2_safe_adoption_count",
            "candidate_a2_record_count",
            "candidate_a3_adoption_record_count",
            "candidate_a3_pairable_record_count",
        ):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} must be non-negative")
        if (
            self.candidate_a2_safe_adoption_count
            > self.candidate_a2_record_count
        ):
            raise ValueError("safe A2 inventory exceeds candidate inventory")
        if (
            self.candidate_a3_pairable_record_count
            > self.candidate_a3_adoption_record_count
        ):
            raise ValueError("pairable A3 inventory exceeds candidate inventory")
        if len(self.a3_pairing_dispositions) != (
            self.candidate_a3_adoption_record_count
        ):
            raise ValueError("A3 candidate inventory is not complete")
        disposition_pairable_count = sum(
            item.get("pairable") is True
            for item in self.a3_pairing_dispositions
        )
        if disposition_pairable_count != self.candidate_a3_pairable_record_count:
            raise ValueError("A3 pairable inventory disagrees with dispositions")
        if len(self.a3_records) != self.candidate_a3_pairable_record_count:
            raise ValueError("A3 D6 input inventory includes an unpairable record")
        if any(bool(value) for value in self.d6_audit["permissions"].values()):
            raise ValueError("D6 paired audit granted runtime authority")

    def to_dict(self) -> dict[str, Any]:
        a3_pairing_reason_counts = Counter(
            str(item["reason_code"])
            for item in self.a3_pairing_dispositions
        )
        a3_stage_reason_counts = Counter(
            str(reason)
            for item in self.a3_pairing_dispositions
            for reason in item.get("candidate_stage_reason_codes", ())
        )
        a3_stage_evidence_count = sum(
            isinstance(item.get("candidate_stage_evidence"), Mapping)
            for item in self.a3_pairing_dispositions
        )
        payload = {
            "schema_version": self.schema_version,
            "pairing_context_sha256": self.pairing_context_sha256,
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "scale": self.scale,
            "seed": self.seed,
            "r0_episode_id": self.r0_episode_id,
            "candidate_episode_id": self.candidate_episode_id,
            "r0_event_log_sha256": self.r0_event_log_sha256,
            "candidate_event_log_sha256": self.candidate_event_log_sha256,
            "candidate_a2_safe_adoption_count": (
                self.candidate_a2_safe_adoption_count
            ),
            "candidate_a2_record_count": self.candidate_a2_record_count,
            "candidate_a3_adoption_record_count": (
                self.candidate_a3_adoption_record_count
            ),
            "candidate_a3_pairable_record_count": (
                self.candidate_a3_pairable_record_count
            ),
            "candidate_a3_unpairable_record_count": (
                self.candidate_a3_adoption_record_count
                - self.candidate_a3_pairable_record_count
            ),
            "candidate_a3_pairing_coverage_ratio": (
                None
                if self.candidate_a3_adoption_record_count == 0
                else (
                    self.candidate_a3_pairable_record_count
                    / self.candidate_a3_adoption_record_count
                )
            ),
            "candidate_a3_pairing_reason_counts": dict(
                sorted(a3_pairing_reason_counts.items())
            ),
            "candidate_a3_stage_evidence_count": (
                a3_stage_evidence_count
            ),
            "candidate_a3_stage_evidence_missing_count": (
                self.candidate_a3_adoption_record_count
                - a3_stage_evidence_count
            ),
            "candidate_a3_stage_inventory_complete": (
                a3_stage_evidence_count
                == self.candidate_a3_adoption_record_count
            ),
            "candidate_a3_stage_reason_counts": dict(
                sorted(a3_stage_reason_counts.items())
            ),
            "records": {
                "a1": list(self.a1_records),
                "a2": list(self.a2_records),
                "a3": list(self.a3_records),
                "a3_pairing_dispositions": list(
                    self.a3_pairing_dispositions
                ),
            },
            "d6_audit": self.d6_audit,
            "runtime_authority_granted": False,
            "model_promotion_authority_granted": False,
        }
        payload["content_sha256"] = _canonical_sha256(payload)
        return payload


@dataclass(frozen=True, slots=True)
class PairedLearningAdoptionBatchResult:
    """Multi-seed pairing inventory without benefit or authority claims."""

    pairs: tuple[PairedLearningAdoptionResult, ...]
    minimum_unseen_seed_target: int = 20
    seeds_verified_unseen: bool = False
    evidence_scope: str = "development_pairing_only"
    schema_version: str = PAIRED_LEARNING_ADOPTION_BATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PAIRED_LEARNING_ADOPTION_BATCH_SCHEMA_VERSION:
            raise ValueError("unsupported paired batch schema")
        if self.evidence_scope != "development_pairing_only":
            raise ValueError("paired batch scope cannot grant runtime authority")
        if self.minimum_unseen_seed_target < 1:
            raise ValueError("minimum unseen-seed target must be positive")
        if not isinstance(self.seeds_verified_unseen, bool):
            raise TypeError("seeds_verified_unseen must be bool")
        if self.seeds_verified_unseen:
            raise ValueError(
                "development pairing cannot self-assert unseen-seed verification"
            )
        identities = tuple(
            (item.scenario_id, item.scale, item.seed) for item in self.pairs
        )
        if not identities or len(identities) != len(set(identities)):
            raise ValueError("paired batch inventory must be non-empty and unique")
        r0_episodes = tuple(item.r0_episode_id for item in self.pairs)
        candidate_episodes = tuple(
            item.candidate_episode_id for item in self.pairs
        )
        event_logs = tuple(
            digest
            for item in self.pairs
            for digest in (
                item.r0_event_log_sha256,
                item.candidate_event_log_sha256,
            )
        )
        if (
            len(r0_episodes) != len(set(r0_episodes))
            or len(candidate_episodes) != len(set(candidate_episodes))
            or len(event_logs) != len(set(event_logs))
        ):
            raise ValueError("paired batch reuses an episode or event log")

    @property
    def seed_count(self) -> int:
        return len({item.seed for item in self.pairs})

    def to_dict(self) -> dict[str, Any]:
        a2_candidate_pairs = tuple(
            item
            for item in self.pairs
            if item.candidate_a2_safe_adoption_count > 0
        )
        a2_evaluated_pairs = tuple(
            item
            for item in self.pairs
            if item.candidate_a2_record_count > 0
        )
        a3_candidate_pairs = tuple(
            item
            for item in self.pairs
            if item.candidate_a3_adoption_record_count > 0
        )
        a3_pairing_reason_counts = Counter(
            str(disposition["reason_code"])
            for item in self.pairs
            for disposition in item.a3_pairing_dispositions
        )
        a3_stage_reason_counts = Counter(
            str(reason)
            for item in self.pairs
            for disposition in item.a3_pairing_dispositions
            for reason in disposition.get(
                "candidate_stage_reason_codes",
                (),
            )
        )
        a3_stage_evidence_count = sum(
            isinstance(
                disposition.get("candidate_stage_evidence"),
                Mapping,
            )
            for item in self.pairs
            for disposition in item.a3_pairing_dispositions
        )
        a3_candidate_record_count = sum(
            item.candidate_a3_adoption_record_count
            for item in self.pairs
        )
        payload = {
            "schema_version": self.schema_version,
            "evidence_scope": self.evidence_scope,
            "minimum_unseen_seed_target": self.minimum_unseen_seed_target,
            "seed_count": self.seed_count,
            "seeds_verified_unseen": self.seeds_verified_unseen,
            "minimum_seed_count_met": (
                self.seed_count >= self.minimum_unseen_seed_target
            ),
            "minimum_unseen_seed_target_met": (
                self.seeds_verified_unseen
                and self.seed_count >= self.minimum_unseen_seed_target
            ),
            "pair_count": len(self.pairs),
            "a2_candidate_pair_count": len(a2_candidate_pairs),
            "a2_evaluated_pair_count": len(a2_evaluated_pairs),
            "a2_auditable_pair_count": sum(
                item.d6_audit["variants"]["A2"]["availability"]
                == "available"
                for item in a2_candidate_pairs
            ),
            "a3_candidate_pair_count": len(a3_candidate_pairs),
            "a3_auditable_pair_count": sum(
                item.d6_audit["variants"]["A3"]["availability"]
                == "available"
                for item in a3_candidate_pairs
            ),
            "a3_seed_with_pairable_record_count": sum(
                item.candidate_a3_pairable_record_count > 0
                for item in a3_candidate_pairs
            ),
            "a3_candidate_record_count": a3_candidate_record_count,
            "a3_pairable_record_count": sum(
                item.candidate_a3_pairable_record_count
                for item in self.pairs
            ),
            "a3_unpairable_record_count": sum(
                (
                    item.candidate_a3_adoption_record_count
                    - item.candidate_a3_pairable_record_count
                )
                for item in self.pairs
            ),
            "a3_pairing_reason_counts": dict(
                sorted(a3_pairing_reason_counts.items())
            ),
            "a3_stage_evidence_count": a3_stage_evidence_count,
            "a3_stage_evidence_missing_count": (
                a3_candidate_record_count - a3_stage_evidence_count
            ),
            "a3_stage_inventory_complete": (
                a3_stage_evidence_count == a3_candidate_record_count
            ),
            "a3_stage_reason_counts": dict(
                sorted(a3_stage_reason_counts.items())
            ),
            "pairs": [item.to_dict() for item in self.pairs],
            "d6_non_degradation_available": False,
            "positive_benefit_claimed": False,
            "model_authorization_allowed": False,
            "runtime_authority_granted": False,
        }
        payload["content_sha256"] = _canonical_sha256(payload)
        return payload


def run_paired_learning_adoption_episodes(
    config: ScenarioConfig,
    *,
    r0_stack: ScalableModuleStack,
    candidate_stack: ScalableModuleStack,
    output_dir: str | Path | None = None,
) -> tuple[EpisodeResult, EpisodeResult, PairedLearningAdoptionResult]:
    """Run two isolated arms from one exogenous configuration and pair them."""

    if r0_stack is candidate_stack:
        raise ValueError("paired arms must not share one module-stack instance")
    pairing_hash = paired_exogenous_config_sha256(config)
    base_metadata = dict(config.metadata)
    common_metadata = {
        **base_metadata,
        "comparison_key": (
            f"{config.scenario_name}|scale="
            f"{max(config.target_count, config.resource_count)}|"
            f"seed={config.seed}"
        ),
        "paired_exogenous_config_sha256": pairing_hash,
    }
    r0_config = replace(
        config,
        metadata={
            **common_metadata,
            "algorithm_variant": "R0",
        },
    )
    candidate_config = replace(
        config,
        metadata={
            **common_metadata,
            "algorithm_variant": "LEARNING_CANDIDATE",
        },
    )
    root = None if output_dir is None else Path(output_dir)
    r0_result = run_episode(
        r0_config,
        module_stack=r0_stack,
        output_dir=None if root is None else root / "R0",
    )
    candidate_result = run_episode(
        candidate_config,
        module_stack=candidate_stack,
        output_dir=None if root is None else root / "candidate",
    )
    paired = assemble_paired_learning_adoption_evidence(
        r0_result=r0_result,
        candidate_result=candidate_result,
    )
    if root is not None:
        write_paired_learning_adoption_output(
            paired,
            root / "paired_learning_adoption.json",
        )
    return r0_result, candidate_result, paired


def run_paired_learning_adoption_batch(
    configs: Iterable[ScenarioConfig],
    *,
    r0_stack_factory: Callable[[ScenarioConfig], ScalableModuleStack],
    candidate_stack_factory: Callable[[ScenarioConfig], ScalableModuleStack],
    output_dir: str | Path | None = None,
    persist_episode_outputs: bool = False,
    seeds_verified_unseen: bool = False,
) -> PairedLearningAdoptionBatchResult:
    """Run isolated episode pairs sequentially and freeze their inventory."""

    if not isinstance(seeds_verified_unseen, bool):
        raise TypeError("seeds_verified_unseen must be bool")
    if seeds_verified_unseen:
        raise ValueError(
            "development pairing cannot self-assert unseen-seed verification"
        )
    selected = tuple(configs)
    if not selected:
        raise ValueError("paired batch requires at least one scenario")
    keys = tuple(
        (
            item.scenario_name,
            max(item.target_count, item.resource_count),
            item.seed,
        )
        for item in selected
    )
    if len(keys) != len(set(keys)):
        raise ValueError("paired batch scenario/scale/seed keys must be unique")
    root = None if output_dir is None else Path(output_dir)
    pairs: list[PairedLearningAdoptionResult] = []
    for config in selected:
        pair_dir = (
            None
            if root is None
            else root
            / (
                f"{config.scenario_name}_"
                f"{config.resource_count}r_{config.target_count}t_"
                f"seed_{config.seed}"
            )
        )
        _, _, paired = run_paired_learning_adoption_episodes(
            config,
            r0_stack=r0_stack_factory(config),
            candidate_stack=candidate_stack_factory(config),
            output_dir=(
                pair_dir if persist_episode_outputs else None
            ),
        )
        pairs.append(paired)
    batch = PairedLearningAdoptionBatchResult(
        pairs=tuple(pairs),
        seeds_verified_unseen=seeds_verified_unseen,
    )
    if root is not None:
        write_paired_learning_adoption_batch_output(
            batch,
            root / "paired_learning_adoption_batch.json",
        )
    return batch


def assemble_paired_learning_adoption_evidence(
    *,
    r0_result: EpisodeResult,
    candidate_result: EpisodeResult,
) -> PairedLearningAdoptionResult:
    """Build D4/D5 paired records and rerun the strict D6 audit."""

    pairing_hash = _validate_episode_pair(r0_result, candidate_result)
    r0_log_sha = _episode_event_log_sha256(r0_result)
    candidate_log_sha = _episode_event_log_sha256(candidate_result)
    candidate_records = candidate_result.learning_adoption_evidence_records or {}

    a1_records = tuple(
        dict(item) for item in candidate_records.get("a1", ())
    )
    a2_source_records = tuple(
        dict(item) for item in candidate_records.get("a2", ())
    )
    a2_safe_adoption_count = sum(
        item.get("safe_adoption_available") is True
        for item in a2_source_records
    )
    a3_source_records = tuple(candidate_records.get("a3", ()))
    a2_objects = _assemble_a2_records(
        r0_result=r0_result,
        candidate_result=candidate_result,
        pairing_hash=pairing_hash,
        r0_event_log_sha256=r0_log_sha,
        candidate_event_log_sha256=candidate_log_sha,
    )
    a3_objects, a3_dispositions = _assemble_a3_records(
        r0_result=r0_result,
        candidate_result=candidate_result,
    )
    a2_records = a2_source_records + tuple(
        item.to_dict() for item in a2_objects
    )
    a3_records = tuple(item.to_dict() for item in a3_objects)
    a3_pairing_dispositions = tuple(
        item.to_dict() for item in a3_dispositions
    )
    audit_input = build_learning_adoption_audit_input(
        a1=a1_records,
        a2=a2_records,
        a3=a3_records,
        a3_pairing_dispositions=a3_pairing_dispositions,
    )
    audit = audit_learning_adoption_evidence(audit_input)
    for variant in ("A1", "A2", "A3"):
        if any(
            bool(value)
            for value in audit["variants"][variant]["permissions"].values()
        ):
            raise ValueError(f"D6 {variant} paired audit granted authority")
    return PairedLearningAdoptionResult(
        pairing_context_sha256=pairing_hash,
        scenario_id=candidate_result.config.scenario_name,
        scenario_version=candidate_result.config.scenario_version,
        scale=max(
            candidate_result.config.target_count,
            candidate_result.config.resource_count,
        ),
        seed=candidate_result.config.seed,
        r0_episode_id=r0_result.manifest.episode_id,
        candidate_episode_id=candidate_result.manifest.episode_id,
        r0_event_log_sha256=r0_log_sha,
        candidate_event_log_sha256=candidate_log_sha,
        candidate_a2_record_count=len(a2_source_records),
        candidate_a2_safe_adoption_count=a2_safe_adoption_count,
        candidate_a3_adoption_record_count=len(a3_source_records),
        candidate_a3_pairable_record_count=sum(
            item.pairable for item in a3_dispositions
        ),
        a1_records=a1_records,
        a2_records=a2_records,
        a3_records=a3_records,
        a3_pairing_dispositions=a3_pairing_dispositions,
        d6_audit=audit,
    )


def write_paired_learning_adoption_output(
    result: PairedLearningAdoptionResult,
    path: str | Path,
) -> Path:
    """Persist one immutable paired-evidence bundle."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_schema_version": (
            PAIRED_LEARNING_ADOPTION_ARTIFACT_SCHEMA_VERSION
        ),
        "paired_result": result.to_dict(),
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def write_paired_learning_adoption_batch_output(
    result: PairedLearningAdoptionBatchResult,
    path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    output_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_path


def _assemble_a2_records(
    *,
    r0_result: EpisodeResult,
    candidate_result: EpisodeResult,
    pairing_hash: str,
    r0_event_log_sha256: str,
    candidate_event_log_sha256: str,
) -> tuple[Any, ...]:
    records = (
        candidate_result.learning_adoption_evidence_records or {}
    ).get("a2", ())
    paired: list[Any] = []
    for index, record in enumerate(records):
        if (
            record.get("safe_adoption_available") is not True
            or not isinstance(record.get("physical_window"), Mapping)
            or not isinstance(record.get("d3_successor_plan"), Mapping)
        ):
            continue
        source = RegionResourceA2SafeAdoptionAuditSource.from_mapping(record)
        duration = (
            source.physical_window_end_s
            - source.physical_window_start_s
        )
        paired_window_id = (
            f"a2-window-{index:06d}-"
            f"{source.physical_window_start_s:.9f}-"
            f"{source.physical_window_end_s:.9f}"
        )
        comparison_key = (
            f"{candidate_result.config.scenario_name}|"
            f"{candidate_result.config.scenario_version}|"
            f"scale={max(candidate_result.config.target_count, candidate_result.config.resource_count)}|"
            f"seed={candidate_result.config.seed}|{paired_window_id}"
        )
        context = RegionResourceA2AuditContext(
            comparison_key=comparison_key,
            scenario_id=candidate_result.config.scenario_name,
            scenario_version=candidate_result.config.scenario_version,
            scale=max(
                candidate_result.config.target_count,
                candidate_result.config.resource_count,
            ),
            seed=candidate_result.config.seed,
            paired_window_id=paired_window_id,
            paired_exogenous_config_sha256=pairing_hash,
            required_window_duration_s=duration,
        )
        candidate_window = RegionResourceA2AuditWindowReference(
            arm=RegionResourceA2AuditArm.A2,
            comparison_key=comparison_key,
            scenario_id=context.scenario_id,
            scenario_version=context.scenario_version,
            scale=context.scale,
            seed=context.seed,
            paired_window_id=paired_window_id,
            paired_exogenous_config_sha256=pairing_hash,
            execution_arm_id=candidate_result.manifest.episode_id,
            window_id=source.physical_window_id,
            source_event_log_id=(
                f"{candidate_result.manifest.episode_id}/online-events"
            ),
            source_event_log_sha256=candidate_event_log_sha256,
            window_start_s=source.physical_window_start_s,
            window_end_s=source.physical_window_end_s,
            plan_id=source.applied_plan_id,
            plan_version=source.applied_plan_version,
            plan_valid_until_s=source.plan_valid_until_s,
            authority_lease_expires_at_s=(
                source.authority_lease_expires_at_s
            ),
            physical_window_payload_sha256=(
                source.physical_window_payload_sha256
            ),
            policy_name=source.policy_name,
            policy_version=source.policy_version,
            source_safe_adoption_evidence_sha256=(
                source.evidence_content_sha256
            ),
            source_advisory_id=source.advisory_id,
            source_advisory_version=source.advisory_version,
            physical_execution_observed=(
                source.physical_execution_observed
            ),
            window_complete=True,
            hard_constraint_violation_count=(
                source.hard_constraint_violation_count
            ),
        )
        r0_window = _r0_a2_window_reference(
            result=r0_result,
            context=context,
            event_log_sha256=r0_event_log_sha256,
        )
        paired.append(
            assemble_region_resource_a2_benefit_audit_input(
                safe_adoption_evidence=record,
                context=context,
                candidate_window=candidate_window,
                same_key_r0_window=r0_window,
            )
        )
    if not paired:
        return ()
    batch = assemble_region_resource_a2_benefit_audit_batch(paired)
    return batch.records


def _assemble_a3_records(
    *,
    r0_result: EpisodeResult,
    candidate_result: EpisodeResult,
) -> tuple[
    tuple[Any, ...],
    tuple[ActiveVisionA3PairingDisposition, ...],
]:
    r0_by_key: dict[
        str,
        list[ActiveVisionA3PhysicalObservationWindow],
    ] = {}
    for record in r0_result.active_vision_r0_window_records or ():
        window = ActiveVisionA3PhysicalObservationWindow.from_mapping(record)
        r0_by_key.setdefault(window.comparison_key, []).append(window)

    candidate_stage_by_key: dict[str, Mapping[str, Any]] = {}
    for record in (
        candidate_result.active_vision_a3_candidate_stage_records or ()
    ):
        comparison_key = str(record.get("comparison_key", "")).strip()
        if not comparison_key or comparison_key in candidate_stage_by_key:
            raise ValueError(
                "A3 candidate-stage inventory has a missing or duplicate key"
            )
        candidate_stage_by_key[comparison_key] = record

    output: list[Any] = []
    dispositions: list[ActiveVisionA3PairingDisposition] = []
    candidate_keys: set[str] = set()
    candidate_records = (
        candidate_result.learning_adoption_evidence_records or {}
    ).get("a3", ())
    for record in candidate_records:
        validated = validate_active_vision_a3_evidence(record)
        comparison_key = validated.adoption_trace.comparison_key
        candidate_keys.add(comparison_key)
        disposition = attempt_active_vision_a3_pairing(
            validated.adoption_trace,
            candidate_window=validated.candidate_window,
            same_key_r0_windows=r0_by_key.get(
                comparison_key,
                (),
            ),
            candidate_stage_evidence=candidate_stage_by_key.get(
                comparison_key
            ),
        )
        dispositions.append(disposition)
        if disposition.paired_evidence is not None:
            output.append(disposition.paired_evidence)
    extra_stage_keys = set(candidate_stage_by_key) - candidate_keys
    if extra_stage_keys:
        raise ValueError(
            "A3 candidate-stage inventory references an unknown candidate"
        )
    return tuple(output), tuple(dispositions)


def _r0_a2_window_reference(
    *,
    result: EpisodeResult,
    context: RegionResourceA2AuditContext,
    event_log_sha256: str,
) -> RegionResourceA2AuditWindowReference | None:
    window_start = _paired_window_start(context)
    window_end = window_start + context.required_window_duration_s
    plan_messages = tuple(
        item
        for item in result.online_messages
        if item.topic == "modules.d3.assignment_plan"
        and item.timestamp <= window_start + _EPS
    )
    if not plan_messages:
        return None
    plan_message = max(plan_messages, key=lambda item: item.timestamp)
    plan = dict(plan_message.payload)
    plan_id = str(plan.get("plan_id", "")).strip()
    plan_version = int(plan.get("plan_version", -1))
    if not plan_id or plan_version < 0:
        return None

    failover_messages = tuple(
        item
        for item in result.online_messages
        if item.topic == "modules.d4.regional_failover"
        and item.timestamp <= window_start + _EPS
    )
    if not failover_messages:
        return None
    failover_message = max(failover_messages, key=lambda item: item.timestamp)
    ownership = tuple(
        dict(region.get("ownership", {}))
        for region in failover_message.payload.get("regions", ())
        if region.get("execution_allowed") is True
        and isinstance(region.get("ownership"), Mapping)
        and region["ownership"].get("active") is True
        and region["ownership"].get("owner_layer") == "center"
    )
    if not ownership:
        return None
    lease_expires = min(
        float(item["lease_expires_at_s"]) for item in ownership
    )

    acknowledgements = tuple(
        item
        for item in result.online_messages
        if item.topic == "runtime.assignment_plan_ack"
        and item.timestamp <= window_start + _EPS
        and item.payload.get("plan_id") == plan_id
        and int(item.payload.get("plan_version", -1)) == plan_version
    )
    acknowledgement = (
        None
        if not acknowledgements
        else max(acknowledgements, key=lambda item: item.timestamp)
    )
    guidance_messages = tuple(
        item
        for item in result.online_messages
        if item.topic == "modules.d7.guidance_commands"
        and window_start - _EPS <= item.timestamp <= window_end + _EPS
    )
    matching_commands = tuple(
        command
        for message in guidance_messages
        for command in message.payload.get("commands", ())
        if command.get("plan_id") == plan_id
        and int(command.get("plan_version", -1)) == plan_version
    )
    physical_execution_observed = bool(
        acknowledgement is not None
        and acknowledgement.payload.get("accepted") is True
        and acknowledgement.payload.get("fully_bound_to_guidance") is True
        and any(
            command.get("mode") != "hold"
            and float(command.get("command_norm_mps2", 0.0)) > 0.0
            for command in matching_commands
        )
    )
    superseded = any(
        item.topic == "modules.d3.assignment_plan"
        and window_start < item.timestamp <= window_end + _EPS
        and int(item.payload.get("plan_version", -1)) != plan_version
        for item in result.online_messages
    )
    window_complete = bool(
        result.timestamps.size
        and float(result.timestamps[-1]) + _EPS >= window_end
        and not superseded
        and guidance_messages
    )
    hard_violations = _guidance_hard_constraint_violations(
        matching_commands,
        finite_state=bool(result.summary.get("finite_state", False)),
    )
    physical_payload = {
        "episode_id": result.manifest.episode_id,
        "paired_window_id": context.paired_window_id,
        "window_start_s": window_start,
        "window_end_s": window_end,
        "plan_publication": plan_message.to_dict(),
        "failover_publication": failover_message.to_dict(),
        "assignment_ack": (
            None if acknowledgement is None else acknowledgement.to_dict()
        ),
        "guidance_publications": [
            item.to_dict() for item in guidance_messages
        ],
    }
    return RegionResourceA2AuditWindowReference(
        arm=RegionResourceA2AuditArm.R0,
        comparison_key=context.comparison_key,
        scenario_id=context.scenario_id,
        scenario_version=context.scenario_version,
        scale=context.scale,
        seed=context.seed,
        paired_window_id=context.paired_window_id,
        paired_exogenous_config_sha256=(
            context.paired_exogenous_config_sha256
        ),
        execution_arm_id=result.manifest.episode_id,
        window_id=(
            f"{result.manifest.episode_id}:{context.paired_window_id}:r0"
        ),
        source_event_log_id=f"{result.manifest.episode_id}/online-events",
        source_event_log_sha256=event_log_sha256,
        window_start_s=window_start,
        window_end_s=window_end,
        plan_id=plan_id,
        plan_version=plan_version,
        plan_valid_until_s=lease_expires,
        authority_lease_expires_at_s=lease_expires,
        physical_window_payload_sha256=_canonical_sha256(
            physical_payload
        ),
        policy_name=RuleRegionResourcePolicy.policy_name,
        policy_version=RuleRegionResourcePolicy.policy_version,
        source_safe_adoption_evidence_sha256=None,
        source_advisory_id=None,
        source_advisory_version=None,
        physical_execution_observed=physical_execution_observed,
        window_complete=window_complete,
        hard_constraint_violation_count=hard_violations,
    )


def _paired_window_start(context: RegionResourceA2AuditContext) -> float:
    parts = context.paired_window_id.rsplit("-", 2)
    if len(parts) != 3:
        raise ValueError("paired window ID does not encode its time interval")
    try:
        start = float(parts[-2])
        end = float(parts[-1])
    except ValueError as exc:
        raise ValueError(
            "paired window ID has an invalid time interval"
        ) from exc
    if not math.isclose(
        end - start,
        context.required_window_duration_s,
        rel_tol=0.0,
        abs_tol=_EPS,
    ):
        raise ValueError("paired window ID duration differs from context")
    return start


def _guidance_hard_constraint_violations(
    commands: tuple[Mapping[str, Any], ...],
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
            or not all(math.isfinite(value) for value in acceleration)
            or not math.isfinite(norm)
            or norm > 12.0 + 1.0e-6
            or not math.isclose(
                math.sqrt(sum(value * value for value in acceleration)),
                norm,
                rel_tol=0.0,
                abs_tol=1.0e-6,
            )
        ):
            violations += 1
    return violations


def _validate_episode_pair(
    r0_result: EpisodeResult,
    candidate_result: EpisodeResult,
) -> str:
    if r0_result.manifest.episode_id == candidate_result.manifest.episode_id:
        raise ValueError("R0 and candidate episode identities are not isolated")
    r0_hash = paired_exogenous_config_sha256(r0_result.config)
    candidate_hash = paired_exogenous_config_sha256(candidate_result.config)
    if r0_hash != candidate_hash:
        raise ValueError("paired episodes do not share one exogenous configuration")
    identity_fields = (
        "scenario_name",
        "scenario_version",
        "seed",
        "target_count",
        "resource_count",
        "recon_count",
        "region_count",
    )
    for field_name in identity_fields:
        if getattr(r0_result.config, field_name) != getattr(
            candidate_result.config,
            field_name,
        ):
            raise ValueError(
                f"paired episode field mismatch: {field_name}"
            )
    r0_records = r0_result.learning_adoption_evidence_records or {}
    if tuple(r0_records.get("a2", ())) or tuple(r0_records.get("a3", ())):
        raise ValueError("R0 episode contains learned A2/A3 adoption records")
    return r0_hash


def _episode_event_log_sha256(result: EpisodeResult) -> str:
    return _canonical_sha256(
        {
            "episode_id": result.manifest.episode_id,
            "messages": [
                item.to_dict()
                for item in result.online_messages
                if item.topic in _D4_RELEVANT_TOPICS
            ],
        }
    )


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(
            jsonable(value),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_sha256(value: str) -> None:
    if (
        len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("expected lowercase SHA-256")


__all__ = [
    "PAIRED_LEARNING_ADOPTION_ARTIFACT_SCHEMA_VERSION",
    "PAIRED_LEARNING_ADOPTION_BATCH_SCHEMA_VERSION",
    "PAIRED_LEARNING_ADOPTION_SCHEMA_VERSION",
    "PairedLearningAdoptionBatchResult",
    "PairedLearningAdoptionResult",
    "assemble_paired_learning_adoption_evidence",
    "run_paired_learning_adoption_batch",
    "run_paired_learning_adoption_episodes",
    "write_paired_learning_adoption_batch_output",
    "write_paired_learning_adoption_output",
]
