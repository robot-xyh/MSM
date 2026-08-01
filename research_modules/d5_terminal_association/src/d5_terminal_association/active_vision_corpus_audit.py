"""Strict corpus coverage audit and collection planning for active vision.

The audit is deliberately separate from model weighting.  It counts only
truth-free, finite, uniquely identified samples from complete training
episodes.  Validation, test and reserved seeds never contribute to training
coverage.  Passing this structural development gate cannot grant model,
camera, assignment or control authority.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .active_vision_contracts import (
    ActiveVisionIntent,
    assert_truth_free_active_vision_payload,
)
from .active_vision_learning import active_vision_candidate_batch
from .active_vision_source import (
    ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION,
    ActiveVisionSourceDomain,
    ActiveVisionSourceValidationError,
    effective_source_domain,
    evidence_tier_for_source_domain,
    source_domain_from_optional_provenance,
)


ACTIVE_VISION_CORPUS_AUDIT_SCHEMA_VERSION = "d5.active-vision-corpus-audit.v1"
ACTIVE_VISION_CORPUS_POLICY_VERSION = "d5.active-vision-corpus-policy.v1"
ACTIVE_VISION_COLLECTION_PLAN_SCHEMA_VERSION = (
    "d5.active-vision-corpus-collection-plan.v1"
)
ACTIVE_VISION_RESEARCH_EVIDENCE_GATE_SCHEMA_VERSION = (
    "d5.active-vision-research-evidence-gate.v1"
)

_SPLITS = ("train", "validation", "test")
_SPLIT_ORDER = {name: index for index, name in enumerate(_SPLITS)}
_INTENTS = tuple(item.value for item in ActiveVisionIntent)
_CAMERA_ROLES = ("interceptor", "recon")
_FALLBACK_SCENARIO = "active-vision-coverage-supplement-v1"
_LEGACY_AUTHORITY_FALSE = {
    "formal_candidate_available": False,
    "assist_admitted": False,
    "active_vision_authority_granted": False,
    "camera_command_authority_granted": False,
    "assignment_authority_granted": False,
    "control_authority_granted": False,
    "global_track_id_write_authority_granted": False,
}
_AUTHORITY_FALSE = {
    **_LEGACY_AUTHORITY_FALSE,
    "degradation_authority_granted": False,
    "runtime_authority_granted": False,
    "production_authority_granted": False,
}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


@dataclass(frozen=True)
class ActiveVisionCorpusCoveragePolicy:
    """Structural minimums for development-only behavior-cloning training."""

    minimum_unique_samples_per_intent: int = 4
    minimum_unique_episodes_per_intent: int = 2
    minimum_unique_seeds_per_intent: int = 2
    minimum_unique_samples_per_camera_role: int = 8
    minimum_unique_episodes_per_camera_role: int = 2
    minimum_unique_seeds_per_camera_role: int = 2
    minimum_unique_samples_per_intent_camera_role: int = 2
    minimum_unique_episodes_per_intent_camera_role: int = 2
    minimum_unique_seeds_per_intent_camera_role: int = 2
    required_scenarios: tuple[str, ...] = ()
    require_reserved_seed_evidence: bool = True
    policy_version: str = ACTIVE_VISION_CORPUS_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.policy_version != ACTIVE_VISION_CORPUS_POLICY_VERSION:
            raise ValueError("active-vision corpus policy version mismatch")
        for name in (
            "minimum_unique_samples_per_intent",
            "minimum_unique_episodes_per_intent",
            "minimum_unique_seeds_per_intent",
            "minimum_unique_samples_per_camera_role",
            "minimum_unique_episodes_per_camera_role",
            "minimum_unique_seeds_per_camera_role",
            "minimum_unique_samples_per_intent_camera_role",
            "minimum_unique_episodes_per_intent_camera_role",
            "minimum_unique_seeds_per_intent_camera_role",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        scenarios = tuple(sorted({_key(item, "required_scenario") for item in self.required_scenarios}))
        object.__setattr__(self, "required_scenarios", scenarios)
        if type(self.require_reserved_seed_evidence) is not bool:
            raise ValueError("require_reserved_seed_evidence must be boolean")


class ActiveVisionCorpusCoverageError(ValueError):
    """Raised when a cache cannot enter development behavior cloning."""


@dataclass
class _CoverageAccumulator:
    sample_count: int = 0
    episode_keys: set[str] | None = None
    seeds: set[int] | None = None
    scenarios: set[str] | None = None

    def __post_init__(self) -> None:
        if self.episode_keys is None:
            self.episode_keys = set()
        if self.seeds is None:
            self.seeds = set()
        if self.scenarios is None:
            self.scenarios = set()

    def add(self, *, episode_key: str, seed: int, scenario: str) -> None:
        self.sample_count += 1
        self.episode_keys.add(episode_key)
        self.seeds.add(seed)
        self.scenarios.add(scenario)

    def payload(self) -> dict[str, int]:
        return {
            "unique_sample_count": int(self.sample_count),
            "unique_episode_count": len(self.episode_keys),
            "unique_seed_count": len(self.seeds),
            "unique_scenario_count": len(self.scenarios),
        }


def active_vision_camera_role(resource_id: str) -> str:
    """Resolve the two supported active-vision camera roles from resource IDs."""

    value = _key(resource_id, "resource_id").lower()
    tokens = tuple(
        token
        for token in value.replace("_", "-").replace(":", "-").replace(".", "-").split("-")
        if token
    )
    interceptor = any(token in {"int", "interceptor"} for token in tokens)
    recon = any(token in {"recon", "reconnaissance"} for token in tokens)
    if interceptor == recon:
        return "unknown"
    return "interceptor" if interceptor else "recon"


def audit_active_vision_training_corpus(
    dataset: Any,
    *,
    policy: ActiveVisionCorpusCoveragePolicy | None = None,
    reserved_evaluation_seeds: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Audit a complete split dataset and return a deterministic collection plan."""

    cfg = policy or ActiveVisionCorpusCoveragePolicy()
    if not isinstance(cfg, ActiveVisionCorpusCoveragePolicy):
        raise TypeError("policy must be ActiveVisionCorpusCoveragePolicy")
    reserved_seeds = _seed_catalog(
        reserved_evaluation_seeds,
        field_name="reserved_evaluation_seeds",
    )
    descriptors = tuple(getattr(dataset, "episode_descriptors", ()))
    manifest = getattr(dataset, "manifest", {})
    manifest = manifest if isinstance(manifest, Mapping) else {}

    integrity_reasons: set[str] = set()
    warnings: set[str] = set()
    descriptor_splits: dict[tuple[str, int, str], set[str]] = defaultdict(set)
    descriptor_keys_by_split: dict[str, set[tuple[str, int, str]]] = {
        split: set() for split in _SPLITS
    }
    descriptor_seeds_by_split: dict[str, set[int]] = {
        split: set() for split in _SPLITS
    }
    descriptor_scenarios_by_split: dict[str, set[str]] = {
        split: set() for split in _SPLITS
    }
    descriptor_duplicate_keys: list[str] = []
    seen_descriptor_identity: set[tuple[str, int, str]] = set()
    descriptor_source_domains: dict[
        tuple[str, int, str], ActiveVisionSourceDomain
    ] = {}
    descriptor_source_explicit: dict[tuple[str, int, str], bool] = {}
    source_domain_count_by_split: dict[str, Counter[str]] = {
        split: Counter() for split in _SPLITS
    }
    for descriptor in descriptors:
        try:
            if not isinstance(descriptor, Mapping):
                raise ValueError("descriptor is not a mapping")
            split = str(descriptor["split"])
            if split not in _SPLITS:
                raise ValueError("descriptor split is invalid")
            scenario = _key(descriptor["scenario_version"], "scenario_version")
            seed = _seed(descriptor["seed"], "descriptor.seed")
            episode_id = _key(descriptor["episode_id"], "episode_id")
            identity = (scenario, seed, episode_id)
            synthetic_fixture = descriptor.get("synthetic_fixture")
            if type(synthetic_fixture) is not bool:
                raise ValueError("descriptor synthetic_fixture is invalid")
            source_payload = descriptor.get("source_provenance")
            if source_payload is not None and not isinstance(source_payload, Mapping):
                raise ValueError("descriptor source provenance is invalid")
            source_domain, source_explicit = source_domain_from_optional_provenance(
                source_payload,
                synthetic_fixture=synthetic_fixture,
            )
        except (KeyError, TypeError, ValueError):
            integrity_reasons.add("episode_descriptor_invalid")
            continue
        if identity in seen_descriptor_identity:
            descriptor_duplicate_keys.append(_episode_key(*identity))
        seen_descriptor_identity.add(identity)
        descriptor_splits[identity].add(split)
        descriptor_keys_by_split[split].add(identity)
        descriptor_seeds_by_split[split].add(seed)
        descriptor_scenarios_by_split[split].add(scenario)
        descriptor_source_domains[identity] = source_domain
        descriptor_source_explicit[identity] = source_explicit
        source_domain_count_by_split[split][source_domain.value] += 1

    if descriptor_duplicate_keys:
        integrity_reasons.add("duplicate_episode_descriptor")
    split_seed_intersections = {
        "train_validation": sorted(
            descriptor_seeds_by_split["train"]
            & descriptor_seeds_by_split["validation"]
        ),
        "train_test": sorted(
            descriptor_seeds_by_split["train"]
            & descriptor_seeds_by_split["test"]
        ),
        "validation_test": sorted(
            descriptor_seeds_by_split["validation"]
            & descriptor_seeds_by_split["test"]
        ),
    }
    contaminated_seed_values = sorted(
        {
            seed
            for values in split_seed_intersections.values()
            for seed in values
        }
    )
    if contaminated_seed_values:
        integrity_reasons.add("seed_split_pollution")

    canonical_seed_evidence = _canonical_seed_evidence(
        manifest,
        descriptor_seeds_by_split=descriptor_seeds_by_split,
    )
    if reserved_evaluation_seeds is not None:
        reserved_evidence = {
            "available": True,
            "source": "explicit_development_argument",
            "formal_registry_binding": False,
            "reserved_seed_count": len(reserved_seeds),
            "reason": None,
        }
    else:
        reserved_evidence = canonical_seed_evidence
    if cfg.require_reserved_seed_evidence and not reserved_evidence["available"]:
        integrity_reasons.add("reserved_seed_evidence_unavailable")

    evaluation_seeds = (
        descriptor_seeds_by_split["validation"]
        | descriptor_seeds_by_split["test"]
    )
    prohibited_training_seeds = evaluation_seeds | set(reserved_seeds)
    train_evaluation_overlap = sorted(
        descriptor_seeds_by_split["train"] & evaluation_seeds
    )
    train_reserved_overlap = sorted(
        descriptor_seeds_by_split["train"] & set(reserved_seeds)
    )
    if train_evaluation_overlap:
        integrity_reasons.add("training_evaluation_seed_overlap")
    if train_reserved_overlap:
        integrity_reasons.add("training_reserved_seed_overlap")

    by_intent: dict[str, _CoverageAccumulator] = {
        intent: _CoverageAccumulator() for intent in _INTENTS
    }
    by_role: dict[str, _CoverageAccumulator] = {
        role: _CoverageAccumulator() for role in _CAMERA_ROLES
    }
    by_scenario: dict[str, _CoverageAccumulator] = {
        scenario: _CoverageAccumulator()
        for scenario in sorted(descriptor_scenarios_by_split["train"])
    }
    by_seed: dict[int, _CoverageAccumulator] = {
        seed: _CoverageAccumulator()
        for seed in sorted(descriptor_seeds_by_split["train"])
    }
    by_intent_role: dict[tuple[str, str], _CoverageAccumulator] = {
        (intent, role): _CoverageAccumulator()
        for intent in _INTENTS
        for role in _CAMERA_ROLES
    }
    by_scenario_intent_role: dict[
        tuple[str, str, str], _CoverageAccumulator
    ] = {
        (scenario, intent, role): _CoverageAccumulator()
        for scenario in sorted(
            descriptor_scenarios_by_split["train"] | set(cfg.required_scenarios)
        )
        for intent in _INTENTS
        for role in _CAMERA_ROLES
    }

    raw_episode_count_by_split = Counter()
    raw_sample_count_by_split = Counter()
    eligible_sample_count_by_split = Counter()
    duplicate_sample_count_by_split = Counter()
    excluded_sample_reasons = Counter()
    materialized_keys_by_split: dict[str, set[tuple[str, int, str]]] = {
        split: set() for split in _SPLITS
    }
    seen_materialized_episode_keys: set[tuple[str, int, str]] = set()
    duplicate_materialized_episode_keys: list[str] = []
    unique_training_episode_keys: set[str] = set()
    synthetic_training_episode_keys: set[str] = set()
    non_synthetic_training_episode_keys: set[str] = set()

    for split in _SPLITS:
        try:
            iterator = dataset.iter_behavior_cloning_episodes(split)
        except Exception:
            integrity_reasons.add(f"{split}_episode_iterator_unavailable")
            continue
        try:
            for episode in iterator:
                raw_episode_count_by_split[split] += 1
                transitions = tuple(getattr(episode, "transitions", ()))
                raw_sample_count_by_split[split] += len(transitions)
                try:
                    scenario = _key(
                        getattr(episode, "scenario_version"),
                        "scenario_version",
                    )
                    seed = _seed(getattr(episode, "seed"), "episode.seed")
                    episode_id = _key(
                        getattr(episode, "episode_id"),
                        "episode_id",
                    )
                    identity = (scenario, seed, episode_id)
                except (AttributeError, TypeError, ValueError):
                    integrity_reasons.add("materialized_episode_identity_invalid")
                    excluded_sample_reasons[
                        "materialized_episode_identity_invalid"
                    ] += len(transitions)
                    continue
                episode_key = _episode_key(*identity)
                materialized_keys_by_split[split].add(identity)
                if identity in seen_materialized_episode_keys:
                    duplicate_materialized_episode_keys.append(episode_key)
                    integrity_reasons.add("duplicate_materialized_episode")
                    excluded_sample_reasons["duplicate_materialized_episode"] += len(
                        transitions
                    )
                    continue
                seen_materialized_episode_keys.add(identity)
                declared_splits = descriptor_splits.get(identity, set())
                if declared_splits != {split}:
                    integrity_reasons.add("materialized_episode_split_mismatch")
                    excluded_sample_reasons[
                        "materialized_episode_split_mismatch"
                    ] += len(transitions)
                    continue
                if not transitions:
                    integrity_reasons.add("empty_materialized_episode")
                    continue
                synthetic = getattr(episode, "synthetic_fixture", None)
                if type(synthetic) is not bool:
                    integrity_reasons.add("synthetic_fixture_flag_invalid")
                    excluded_sample_reasons[
                        "synthetic_fixture_flag_invalid"
                    ] += len(transitions)
                    continue
                try:
                    materialized_source_domain = effective_source_domain(
                        getattr(episode, "source_domain", None),
                        synthetic_fixture=synthetic,
                    )
                except ActiveVisionSourceValidationError:
                    integrity_reasons.add("materialized_source_domain_invalid")
                    excluded_sample_reasons[
                        "materialized_source_domain_invalid"
                    ] += len(transitions)
                    continue
                if materialized_source_domain is not descriptor_source_domains.get(
                    identity
                ):
                    integrity_reasons.add("materialized_source_domain_mismatch")
                    excluded_sample_reasons[
                        "materialized_source_domain_mismatch"
                    ] += len(transitions)
                    continue
                if split == "train":
                    unique_training_episode_keys.add(episode_key)
                    if synthetic:
                        synthetic_training_episode_keys.add(episode_key)
                    else:
                        non_synthetic_training_episode_keys.add(episode_key)

                sample_index_by_fingerprint: dict[str, int] = {}
                for index, transition in enumerate(transitions):
                    sample_reason, sample_fingerprint = _validate_training_sample(
                        transition,
                        split=split,
                        seed=seed,
                        prohibited_training_seeds=prohibited_training_seeds,
                    )
                    if sample_reason is not None:
                        excluded_sample_reasons[sample_reason] += 1
                        if sample_reason == "truth_identity_field_detected":
                            integrity_reasons.add(
                                "training_corpus_truth_identity_forbidden"
                            )
                        elif sample_reason == "nonfinite_candidate_features":
                            integrity_reasons.add(
                                "training_corpus_nonfinite_features"
                            )
                        elif split == "train":
                            integrity_reasons.add(
                                f"training_sample_invalid:{sample_reason}"
                            )
                        continue
                    if sample_fingerprint in sample_index_by_fingerprint:
                        duplicate_sample_count_by_split[split] += 1
                        excluded_sample_reasons[
                            "duplicate_sample_within_episode"
                        ] += 1
                        integrity_reasons.add(
                            "duplicate_sample_within_episode"
                        )
                        continue
                    sample_index_by_fingerprint[sample_fingerprint] = index
                    if split != "train":
                        eligible_sample_count_by_split[split] += 1
                        continue

                    action = transition.selected_action
                    intent = action.intent.value
                    camera = transition.snapshot.camera(transition.camera_id)
                    role = active_vision_camera_role(camera.resource_id)
                    eligible_sample_count_by_split[split] += 1
                    by_intent[intent].add(
                        episode_key=episode_key,
                        seed=seed,
                        scenario=scenario,
                    )
                    by_role[role].add(
                        episode_key=episode_key,
                        seed=seed,
                        scenario=scenario,
                    )
                    by_scenario.setdefault(
                        scenario, _CoverageAccumulator()
                    ).add(
                        episode_key=episode_key,
                        seed=seed,
                        scenario=scenario,
                    )
                    by_seed.setdefault(seed, _CoverageAccumulator()).add(
                        episode_key=episode_key,
                        seed=seed,
                        scenario=scenario,
                    )
                    by_intent_role[(intent, role)].add(
                        episode_key=episode_key,
                        seed=seed,
                        scenario=scenario,
                    )
                    by_scenario_intent_role.setdefault(
                        (scenario, intent, role),
                        _CoverageAccumulator(),
                    ).add(
                        episode_key=episode_key,
                        seed=seed,
                        scenario=scenario,
                    )
        except Exception:
            integrity_reasons.add(f"{split}_episode_iteration_failed")

    for split in _SPLITS:
        missing = descriptor_keys_by_split[split] - materialized_keys_by_split[split]
        extra = materialized_keys_by_split[split] - descriptor_keys_by_split[split]
        if missing:
            integrity_reasons.add(f"{split}_materialized_episode_missing")
        if extra:
            integrity_reasons.add(f"{split}_materialized_episode_untracked")

    if not non_synthetic_training_episode_keys:
        warnings.add("non_synthetic_training_episode_evidence_unavailable")
    if synthetic_training_episode_keys:
        warnings.add("synthetic_training_episodes_cannot_grant_formal_candidate")

    inventory = _inventory_payload(
        by_intent=by_intent,
        by_role=by_role,
        by_scenario=by_scenario,
        by_seed=by_seed,
        by_intent_role=by_intent_role,
        by_scenario_intent_role=by_scenario_intent_role,
        raw_episode_count_by_split=raw_episode_count_by_split,
        raw_sample_count_by_split=raw_sample_count_by_split,
        eligible_sample_count_by_split=eligible_sample_count_by_split,
        duplicate_sample_count_by_split=duplicate_sample_count_by_split,
        excluded_sample_reasons=excluded_sample_reasons,
        unique_training_episode_keys=unique_training_episode_keys,
        synthetic_training_episode_keys=synthetic_training_episode_keys,
        non_synthetic_training_episode_keys=non_synthetic_training_episode_keys,
    )
    coverage_reasons = _coverage_failure_reasons(
        inventory,
        policy=cfg,
    )
    all_failure_reasons = sorted(integrity_reasons | set(coverage_reasons))
    plan = _collection_plan(
        inventory,
        policy=cfg,
        failure_reasons=all_failure_reasons,
    )
    development_ready = not all_failure_reasons
    research_evidence_gate = _research_evidence_gate(
        dataset,
        descriptors=descriptors,
        source_domain_count_by_split=source_domain_count_by_split,
        explicit_source_domain_count=sum(descriptor_source_explicit.values()),
        integrity_reasons=integrity_reasons,
        contaminated_seed_values=contaminated_seed_values,
        materialized_episode_count=len(seen_materialized_episode_keys),
    )
    report: dict[str, Any] = {
        "schema_version": ACTIVE_VISION_CORPUS_AUDIT_SCHEMA_VERSION,
        "policy": asdict(cfg),
        "scope": {
            "consumer": "active_vision_behavior_cloning",
            "coverage_split": "train_only",
            "validation_and_test_samples_used_for_training_coverage": False,
            "offline_labels_loaded": False,
            "online_truth_identifier_consumed": False,
            "global_track_id_created_or_rewritten": False,
            "sample_copy_used_for_coverage": False,
            "sample_reweighting_used_for_coverage": False,
            "synthetic_sample_fabrication_used_for_coverage": False,
            "independence_definition": (
                "unique scenario/seed/episode plus transition position; "
                "episode and seed counts are reported separately and no IID claim is made"
            ),
        },
        "source_binding": {
            "dataset_schema_version": manifest.get("schema_version"),
            "dataset_manifest_sha256": getattr(
                dataset, "manifest_sha256", None
            ),
            "canonical_seed_view_available": bool(
                isinstance(manifest.get("canonical_seed_view"), Mapping)
            ),
        },
        "split_integrity": {
            "descriptor_count": len(descriptors),
            "descriptor_duplicate_episode_keys": sorted(
                set(descriptor_duplicate_keys)
            ),
            "materialized_duplicate_episode_keys": sorted(
                set(duplicate_materialized_episode_keys)
            ),
            "seed_values_by_split": {
                split: sorted(descriptor_seeds_by_split[split])
                for split in _SPLITS
            },
            "seed_intersections": split_seed_intersections,
            "contaminated_seed_values": contaminated_seed_values,
            "evaluation_seed_values": sorted(evaluation_seeds),
            "explicit_reserved_evaluation_seed_values": list(reserved_seeds),
            "training_evaluation_seed_overlap": train_evaluation_overlap,
            "training_reserved_seed_overlap": train_reserved_overlap,
            "reserved_seed_evidence": reserved_evidence,
            "canonical_seed_evidence": canonical_seed_evidence,
        },
        "training_inventory": inventory,
        "training_gate": {
            "status": (
                "pass_development_corpus_only"
                if development_ready
                else "fail_closed_training_corpus"
            ),
            "development_training_allowed": development_ready,
            "failure_reasons": all_failure_reasons,
            "warnings": sorted(warnings),
            "structural_gate_is_not_statistical_admission": True,
        },
        "research_evidence_gate": research_evidence_gate,
        "collection_plan": plan,
        "evidence_availability": {
            "formal_candidate": {
                "available": False,
                "reason": "formal_model_and_paired_shadow_evidence_not_in_corpus_audit",
            },
            "non_synthetic_unseen_seed_evidence": {
                "available": False,
                "reason": "requires_independent_held_out_runtime_evaluation",
            },
            "runtime_applied_action_evidence": {
                "available": False,
                "reason": "requires_external_runtime_ack_and_outcome_lineage",
            },
        },
        "authority": dict(_AUTHORITY_FALSE),
    }
    report["content_sha256"] = _content_sha256(report)
    validate_active_vision_corpus_audit(report)
    return report


def validate_active_vision_corpus_audit(value: Mapping[str, Any]) -> None:
    """Validate the immutable parts of a corpus audit before model training."""

    if not isinstance(value, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus audit is unavailable"
        )
    if value.get("schema_version") != ACTIVE_VISION_CORPUS_AUDIT_SCHEMA_VERSION:
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus audit schema mismatch"
        )
    expected_sha = value.get("content_sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus audit hash is unavailable"
        )
    if _content_sha256(value) != expected_sha:
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus audit hash mismatch"
        )
    authority = value.get("authority")
    if authority not in (_LEGACY_AUTHORITY_FALSE, _AUTHORITY_FALSE):
        raise ActiveVisionCorpusCoverageError(
            "active-vision corpus audit attempted a permission escalation"
        )
    availability = value.get("evidence_availability")
    if not isinstance(availability, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision corpus evidence availability is missing"
        )
    for name in (
        "formal_candidate",
        "non_synthetic_unseen_seed_evidence",
        "runtime_applied_action_evidence",
    ):
        item = availability.get(name)
        if not isinstance(item, Mapping) or item.get("available") is not False:
            raise ActiveVisionCorpusCoverageError(
                f"active-vision corpus {name} must remain unavailable"
            )
    scope = value.get("scope")
    if not isinstance(scope, Mapping) or any(
        scope.get(name) is not False
        for name in (
            "validation_and_test_samples_used_for_training_coverage",
            "offline_labels_loaded",
            "online_truth_identifier_consumed",
            "global_track_id_created_or_rewritten",
            "sample_copy_used_for_coverage",
            "sample_reweighting_used_for_coverage",
            "synthetic_sample_fabrication_used_for_coverage",
        )
    ):
        raise ActiveVisionCorpusCoverageError(
            "active-vision corpus scope violates truth or sampling boundaries"
        )
    gate = value.get("training_gate")
    if not isinstance(gate, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus gate is unavailable"
        )
    allowed = gate.get("development_training_allowed")
    if type(allowed) is not bool:
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus gate flag is invalid"
        )
    reasons = gate.get("failure_reasons")
    if not isinstance(reasons, list) or reasons != sorted(set(reasons)):
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus reasons are not canonical"
        )
    expected_status = (
        "pass_development_corpus_only"
        if allowed and not reasons
        else "fail_closed_training_corpus"
    )
    if gate.get("status") != expected_status or (allowed == bool(reasons)):
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus gate is internally inconsistent"
        )
    plan = value.get("collection_plan")
    if not isinstance(plan, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision corpus collection plan is unavailable"
        )
    requests = plan.get("requests")
    if not isinstance(requests, list):
        raise ActiveVisionCorpusCoverageError(
            "active-vision corpus collection requests are invalid"
        )
    expected_ids = [
        f"AV-CORPUS-{index:03d}" for index in range(1, len(requests) + 1)
    ]
    if [item.get("request_id") for item in requests] != expected_ids:
        raise ActiveVisionCorpusCoverageError(
            "active-vision corpus collection request order is invalid"
        )
    if allowed and requests:
        raise ActiveVisionCorpusCoverageError(
            "a passing active-vision corpus audit cannot request more coverage"
        )

    research_gate = value.get("research_evidence_gate")
    if research_gate is None:
        if authority != _LEGACY_AUTHORITY_FALSE:
            raise ActiveVisionCorpusCoverageError(
                "legacy active-vision corpus audit authority fields mismatch"
            )
    else:
        if authority != _AUTHORITY_FALSE:
            raise ActiveVisionCorpusCoverageError(
                "active-vision corpus research gate authority fields mismatch"
            )
        _validate_research_evidence_gate(research_gate)


def require_active_vision_training_corpus_ready(
    cache_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return a validated passing audit or fail before model initialization."""

    if not isinstance(cache_manifest, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision BC cache manifest is invalid"
        )
    report = cache_manifest.get("training_corpus_audit")
    if not isinstance(report, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus audit unavailable; legacy cache is fail-closed"
        )
    validate_active_vision_corpus_audit(report)
    gate = report["training_gate"]
    if gate["development_training_allowed"] is not True:
        reasons = ",".join(gate["failure_reasons"])
        raise ActiveVisionCorpusCoverageError(
            "active-vision training corpus failed closed: " + reasons
        )
    return report


def require_active_vision_simulation_research_corpus_ready(
    cache_manifest: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Require the stricter point-mass simulation research evidence gate."""

    report = require_active_vision_training_corpus_ready(cache_manifest)
    gate = report.get("research_evidence_gate")
    if not isinstance(gate, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision source evidence unavailable; legacy corpus is research-ineligible"
        )
    _validate_research_evidence_gate(gate)
    if gate["simulation_research_development_evaluation_eligible"] is not True:
        reasons = ",".join(gate["failure_reasons"])
        raise ActiveVisionCorpusCoverageError(
            "active-vision point-mass research evidence failed closed: " + reasons
        )
    return report


def _research_evidence_gate(
    dataset: Any,
    *,
    descriptors: Sequence[Mapping[str, Any]],
    source_domain_count_by_split: Mapping[str, Counter[str]],
    explicit_source_domain_count: int,
    integrity_reasons: set[str],
    contaminated_seed_values: Sequence[int],
    materialized_episode_count: int,
) -> dict[str, Any]:
    from .active_vision_episode_dataset import (
        LazyActiveVisionEpisodeDataset,
        LoadedActiveVisionEpisodeDataset,
    )

    manifest = getattr(dataset, "manifest", {})
    manifest = manifest if isinstance(manifest, Mapping) else {}
    strict_loader_used = isinstance(
        dataset,
        (LazyActiveVisionEpisodeDataset, LoadedActiveVisionEpisodeDataset),
    )
    domain_values = tuple(domain.value for domain in ActiveVisionSourceDomain)
    counts_by_split = {
        split: {
            domain: int(source_domain_count_by_split[split].get(domain, 0))
            for domain in domain_values
        }
        for split in _SPLITS
    }
    total_by_domain = {
        domain: sum(counts_by_split[split][domain] for split in _SPLITS)
        for domain in domain_values
    }
    episode_count = len(descriptors)
    exclusively_point_mass = (
        total_by_domain[
            ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME.value
        ]
        == episode_count
        and episode_count > 0
    )
    explicit_complete = explicit_source_domain_count == episode_count

    source_identity_complete = True
    dirty_episode_count = 0
    for descriptor in descriptors:
        identity = descriptor.get("source_identity")
        if not isinstance(identity, Mapping) or set(identity) != {
            "schema_version",
            "git_commit",
            "git_dirty",
            "config_sha256",
        }:
            source_identity_complete = False
            continue
        git_dirty = identity.get("git_dirty")
        if type(git_dirty) is not bool:
            source_identity_complete = False
        else:
            dirty_episode_count += int(git_dirty)
        if _GIT_COMMIT_PATTERN.fullmatch(str(identity.get("git_commit", ""))) is None:
            source_identity_complete = False
        if _SHA256_PATTERN.fullmatch(str(identity.get("config_sha256", ""))) is None:
            source_identity_complete = False

    source_contract = manifest.get("source_provenance_contract")
    source_summary = manifest.get("source_domain_summary")
    version_hash_complete = bool(
        strict_loader_used
        and _SHA256_PATTERN.fullmatch(str(getattr(dataset, "manifest_sha256", "")))
        and _SHA256_PATTERN.fullmatch(str(manifest.get("split_sha256", "")))
        and _SHA256_PATTERN.fullmatch(str(manifest.get("training_set_sha256", "")))
        and _SHA256_PATTERN.fullmatch(str(manifest.get("dataset_config_sha256", "")))
        and isinstance(source_contract, Mapping)
        and source_contract.get("schema_version")
        == ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION
        and source_contract.get("new_artifacts_require_explicit_provenance")
        is True
        and source_contract.get("legacy_evidence_upgrade_allowed") is False
        and source_contract.get("synthetic_fixture_true_domain")
        == ActiveVisionSourceDomain.SYNTHETIC_FIXTURE.value
        and source_contract.get("source_declaration_is_external_runtime_attestation")
        is False
        and isinstance(source_summary, Mapping)
    )
    split_complete = bool(
        not contaminated_seed_values
        and all(
            any(str(item.get("split")) == split for item in descriptors)
            for split in _SPLITS
        )
        and isinstance(manifest.get("split_policy"), Mapping)
        and manifest["split_policy"].get("sample_or_transition_level_random_split")
        is False
    )
    truth_free_complete = bool(
        strict_loader_used
        and manifest.get("storage_contract", {}).get("online_truth_free") is True
        and "training_corpus_truth_identity_forbidden" not in integrity_reasons
    )
    corpus_integrity_complete = bool(
        not integrity_reasons and materialized_episode_count == episode_count
    )

    reasons: list[str] = []
    if not strict_loader_used:
        reasons.append("strict_dataset_loader_evidence_unavailable")
    if not explicit_complete:
        reasons.append("source_domain_not_explicit_for_all_episodes")
    if not exclusively_point_mass:
        reasons.append("source_domain_not_exclusively_point_mass_runtime")
    if not source_identity_complete:
        reasons.append("source_identity_incomplete")
    if dirty_episode_count:
        reasons.append("source_worktree_dirty")
    if not version_hash_complete:
        reasons.append("dataset_version_hash_binding_incomplete")
    if not split_complete:
        reasons.append("seed_split_incomplete")
    if not truth_free_complete:
        reasons.append("truth_free_contract_incomplete")
    if not corpus_integrity_complete:
        reasons.append("corpus_integrity_incomplete")
    reasons = sorted(set(reasons))
    eligible = not reasons
    return {
        "schema_version": ACTIVE_VISION_RESEARCH_EVIDENCE_GATE_SCHEMA_VERSION,
        "status": (
            "point_mass_simulation_research_eligible"
            if eligible
            else "fail_closed_source_evidence"
        ),
        "simulation_research_development_evaluation_eligible": eligible,
        "failure_reasons": reasons,
        "source_inventory": {
            "episode_count": episode_count,
            "episode_count_by_split_and_source_domain": counts_by_split,
            "episode_count_by_source_domain": total_by_domain,
            "explicit_source_domain_episode_count": explicit_source_domain_count,
            "legacy_inferred_episode_count": episode_count
            - explicit_source_domain_count,
        },
        "contract_checks": {
            "strict_dataset_loader_used": strict_loader_used,
            "source_domain_explicit_complete": explicit_complete,
            "source_domain_exclusively_point_mass_runtime": exclusively_point_mass,
            "source_identity_complete": source_identity_complete,
            "source_worktree_clean": dirty_episode_count == 0,
            "version_hash_binding_complete": version_hash_complete,
            "seed_split_complete": split_complete,
            "truth_free_online_payload": truth_free_complete,
            "corpus_integrity_complete": corpus_integrity_complete,
        },
        "claim_limits": {
            "airsim_runtime_evidence_validated": False,
            "real_camera_runtime_evidence_validated": False,
            "real_camera_generalization_validated": False,
            "production_evidence_validated": False,
            "runtime_or_control_permission_granted": False,
        },
    }


def _validate_research_evidence_gate(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "status",
        "simulation_research_development_evaluation_eligible",
        "failure_reasons",
        "source_inventory",
        "contract_checks",
        "claim_limits",
    }:
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence gate fields mismatch"
        )
    if value.get("schema_version") != ACTIVE_VISION_RESEARCH_EVIDENCE_GATE_SCHEMA_VERSION:
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence gate schema mismatch"
        )
    inventory = value.get("source_inventory")
    if not isinstance(inventory, Mapping):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research source inventory is unavailable"
        )
    expected_domains = {domain.value for domain in ActiveVisionSourceDomain}
    totals = inventory.get("episode_count_by_source_domain")
    by_split = inventory.get("episode_count_by_split_and_source_domain")
    if (
        not isinstance(totals, Mapping)
        or set(totals) != expected_domains
        or not isinstance(by_split, Mapping)
        or set(by_split) != set(_SPLITS)
    ):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research source-domain inventory is invalid"
        )
    for split in _SPLITS:
        if not isinstance(by_split[split], Mapping) or set(by_split[split]) != expected_domains:
            raise ActiveVisionCorpusCoverageError(
                "active-vision research split source-domain inventory is invalid"
            )
    episode_count = inventory.get("episode_count")
    explicit_count = inventory.get("explicit_source_domain_episode_count")
    legacy_count = inventory.get("legacy_inferred_episode_count")
    numeric_values = [episode_count, explicit_count, legacy_count, *totals.values()]
    numeric_values.extend(
        value for split in _SPLITS for value in by_split[split].values()
    )
    if any(type(item) is not int or item < 0 for item in numeric_values):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research source-domain counts are invalid"
        )
    if (
        sum(totals.values()) != episode_count
        or explicit_count + legacy_count != episode_count
        or any(
            totals[domain]
            != sum(by_split[split][domain] for split in _SPLITS)
            for domain in expected_domains
        )
    ):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research source-domain counts are inconsistent"
        )
    checks = value.get("contract_checks")
    expected_check_fields = {
        "strict_dataset_loader_used",
        "source_domain_explicit_complete",
        "source_domain_exclusively_point_mass_runtime",
        "source_identity_complete",
        "source_worktree_clean",
        "version_hash_binding_complete",
        "seed_split_complete",
        "truth_free_online_payload",
        "corpus_integrity_complete",
    }
    if (
        not isinstance(checks, Mapping)
        or set(checks) != expected_check_fields
        or any(type(checks[name]) is not bool for name in expected_check_fields)
    ):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence checks are invalid"
        )
    claim_limits = value.get("claim_limits")
    expected_claim_fields = {
        "airsim_runtime_evidence_validated",
        "real_camera_runtime_evidence_validated",
        "real_camera_generalization_validated",
        "production_evidence_validated",
        "runtime_or_control_permission_granted",
    }
    if (
        not isinstance(claim_limits, Mapping)
        or set(claim_limits) != expected_claim_fields
        or any(claim_limits[name] is not False for name in expected_claim_fields)
    ):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence attempted an unsupported claim"
        )
    eligible = value.get("simulation_research_development_evaluation_eligible")
    reasons = value.get("failure_reasons")
    if type(eligible) is not bool or not isinstance(reasons, list):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence decision is invalid"
        )
    if reasons != sorted(set(reasons)) or any(
        not isinstance(reason, str) or not reason for reason in reasons
    ):
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence reasons are not canonical"
        )
    point_mass_count = totals[
        ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME.value
    ]
    expected_eligible = bool(
        episode_count > 0
        and point_mass_count == episode_count
        and explicit_count == episode_count
        and all(checks.values())
        and not reasons
    )
    expected_status = (
        "point_mass_simulation_research_eligible"
        if expected_eligible
        else "fail_closed_source_evidence"
    )
    if eligible != expected_eligible or value.get("status") != expected_status:
        raise ActiveVisionCorpusCoverageError(
            "active-vision research evidence gate is internally inconsistent"
        )


def _validate_training_sample(
    transition: Any,
    *,
    split: str,
    seed: int,
    prohibited_training_seeds: set[int],
) -> tuple[str | None, str | None]:
    try:
        assert_truth_free_active_vision_payload(transition)
    except Exception:
        return "truth_identity_field_detected", None
    try:
        action = transition.selected_action
        intent = ActiveVisionIntent(action.intent)
        camera = transition.snapshot.camera(transition.camera_id)
        role = active_vision_camera_role(camera.resource_id)
    except Exception:
        return "sample_contract_invalid", None
    if intent.value not in _INTENTS:
        return "action_intent_invalid", None
    if role not in _CAMERA_ROLES:
        return "camera_role_unknown", None
    try:
        batch = active_vision_candidate_batch(
            transition.snapshot,
            camera_id=transition.camera_id,
        )
    except Exception as exc:
        message = str(exc).lower()
        if "finite" in message or "nan" in message or "inf" in message:
            return "nonfinite_candidate_features", None
        return "candidate_feature_extraction_failed", None
    features = np.asarray(getattr(batch, "features", ()), dtype=float)
    actions = tuple(getattr(batch, "actions", ()))
    if (
        features.ndim != 2
        or features.shape[0] != len(actions)
        or len(actions) == 0
    ):
        return "candidate_feature_shape_invalid", None
    if not np.all(np.isfinite(features)):
        return "nonfinite_candidate_features", None
    matches = sum(
        candidate.action_key == action.action_key for candidate in actions
    )
    if matches != 1:
        return "selected_action_not_unique_in_candidates", None
    if split == "train" and seed in prohibited_training_seeds:
        return "prohibited_seed_in_training", None
    return None, _sample_input_fingerprint(
        transition,
        features=features,
        actions=actions,
    )


def _sample_input_fingerprint(
    transition: Any,
    *,
    features: np.ndarray,
    actions: Sequence[Any],
) -> str:
    """Hash one policy input without using the selected label or truth fields."""

    snapshot = transition.snapshot
    metadata = {
        "snapshot_schema_version": snapshot.schema_version,
        "snapshot_timestamp_hex": float(snapshot.snapshot_timestamp).hex(),
        "camera_id": str(transition.camera_id),
        "candidate_action_keys": [
            list(candidate.action_key) for candidate in actions
        ],
        "feature_shape": list(features.shape),
    }
    digest = hashlib.sha256(
        json.dumps(
            metadata,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("ascii")
    )
    canonical_features = np.ascontiguousarray(features, dtype="<f8")
    digest.update(canonical_features.tobytes(order="C"))
    return digest.hexdigest()


def _inventory_payload(
    *,
    by_intent: Mapping[str, _CoverageAccumulator],
    by_role: Mapping[str, _CoverageAccumulator],
    by_scenario: Mapping[str, _CoverageAccumulator],
    by_seed: Mapping[int, _CoverageAccumulator],
    by_intent_role: Mapping[tuple[str, str], _CoverageAccumulator],
    by_scenario_intent_role: Mapping[
        tuple[str, str, str], _CoverageAccumulator
    ],
    raw_episode_count_by_split: Counter[str],
    raw_sample_count_by_split: Counter[str],
    eligible_sample_count_by_split: Counter[str],
    duplicate_sample_count_by_split: Counter[str],
    excluded_sample_reasons: Counter[str],
    unique_training_episode_keys: set[str],
    synthetic_training_episode_keys: set[str],
    non_synthetic_training_episode_keys: set[str],
) -> dict[str, Any]:
    return {
        "raw_episode_count_by_split": {
            split: int(raw_episode_count_by_split[split]) for split in _SPLITS
        },
        "raw_sample_count_by_split": {
            split: int(raw_sample_count_by_split[split]) for split in _SPLITS
        },
        "eligible_sample_count_by_split": {
            split: int(eligible_sample_count_by_split[split]) for split in _SPLITS
        },
        "duplicate_sample_count_by_split": {
            split: int(duplicate_sample_count_by_split[split]) for split in _SPLITS
        },
        "excluded_sample_reason_counts": {
            key: int(value)
            for key, value in sorted(excluded_sample_reasons.items())
        },
        "unique_training_episode_count": len(unique_training_episode_keys),
        "synthetic_training_episode_count": len(
            synthetic_training_episode_keys
        ),
        "non_synthetic_training_episode_count": len(
            non_synthetic_training_episode_keys
        ),
        "by_action_intent": {
            intent: by_intent[intent].payload() for intent in _INTENTS
        },
        "by_camera_role": {
            role: by_role[role].payload() for role in _CAMERA_ROLES
        },
        "by_scenario": {
            scenario: by_scenario[scenario].payload()
            for scenario in sorted(by_scenario)
        },
        "by_seed": {
            str(seed): by_seed[seed].payload() for seed in sorted(by_seed)
        },
        "by_action_intent_and_camera_role": {
            intent: {
                role: by_intent_role[(intent, role)].payload()
                for role in _CAMERA_ROLES
            }
            for intent in _INTENTS
        },
        "by_scenario_action_intent_camera_role": {
            scenario: {
                intent: {
                    role: by_scenario_intent_role[
                        (scenario, intent, role)
                    ].payload()
                    for role in _CAMERA_ROLES
                }
                for intent in _INTENTS
            }
            for scenario in sorted(
                {key[0] for key in by_scenario_intent_role}
            )
        },
    }


def _coverage_failure_reasons(
    inventory: Mapping[str, Any],
    *,
    policy: ActiveVisionCorpusCoveragePolicy,
) -> list[str]:
    reasons: list[str] = []
    by_intent = inventory["by_action_intent"]
    by_role = inventory["by_camera_role"]
    by_pair = inventory["by_action_intent_and_camera_role"]
    for intent in _INTENTS:
        cell = by_intent[intent]
        if cell["unique_sample_count"] < policy.minimum_unique_samples_per_intent:
            reasons.append(f"intent_sample_coverage_below_minimum:{intent}")
        if cell["unique_episode_count"] < policy.minimum_unique_episodes_per_intent:
            reasons.append(f"intent_episode_coverage_below_minimum:{intent}")
        if cell["unique_seed_count"] < policy.minimum_unique_seeds_per_intent:
            reasons.append(f"intent_seed_coverage_below_minimum:{intent}")
    if by_intent[ActiveVisionIntent.HOLD.value]["unique_sample_count"] == 0:
        reasons.append("hold_demonstration_missing")
    for role in _CAMERA_ROLES:
        cell = by_role[role]
        if cell["unique_sample_count"] < policy.minimum_unique_samples_per_camera_role:
            reasons.append(f"camera_role_sample_coverage_below_minimum:{role}")
        if cell["unique_episode_count"] < policy.minimum_unique_episodes_per_camera_role:
            reasons.append(f"camera_role_episode_coverage_below_minimum:{role}")
        if cell["unique_seed_count"] < policy.minimum_unique_seeds_per_camera_role:
            reasons.append(f"camera_role_seed_coverage_below_minimum:{role}")
    if by_role["recon"]["unique_sample_count"] == 0:
        reasons.append("recon_camera_training_data_missing")
    for intent in _INTENTS:
        for role in _CAMERA_ROLES:
            cell = by_pair[intent][role]
            prefix = f"intent_camera_role:{intent}:{role}"
            if (
                cell["unique_sample_count"]
                < policy.minimum_unique_samples_per_intent_camera_role
            ):
                reasons.append(f"{prefix}:sample_coverage_below_minimum")
            if (
                cell["unique_episode_count"]
                < policy.minimum_unique_episodes_per_intent_camera_role
            ):
                reasons.append(f"{prefix}:episode_coverage_below_minimum")
            if (
                cell["unique_seed_count"]
                < policy.minimum_unique_seeds_per_intent_camera_role
            ):
                reasons.append(f"{prefix}:seed_coverage_below_minimum")
    scenario_cells = inventory["by_scenario_action_intent_camera_role"]
    for scenario in policy.required_scenarios:
        if scenario not in scenario_cells:
            reasons.append(f"required_scenario_missing:{scenario}")
            continue
        for intent in _INTENTS:
            for role in _CAMERA_ROLES:
                cell = scenario_cells[scenario][intent][role]
                prefix = f"required_scenario_cell:{scenario}:{intent}:{role}"
                if (
                    cell["unique_sample_count"]
                    < policy.minimum_unique_samples_per_intent_camera_role
                ):
                    reasons.append(f"{prefix}:sample_coverage_below_minimum")
                if (
                    cell["unique_episode_count"]
                    < policy.minimum_unique_episodes_per_intent_camera_role
                ):
                    reasons.append(f"{prefix}:episode_coverage_below_minimum")
                if (
                    cell["unique_seed_count"]
                    < policy.minimum_unique_seeds_per_intent_camera_role
                ):
                    reasons.append(f"{prefix}:seed_coverage_below_minimum")
    return sorted(set(reasons))


def _collection_plan(
    inventory: Mapping[str, Any],
    *,
    policy: ActiveVisionCorpusCoveragePolicy,
    failure_reasons: Sequence[str],
) -> dict[str, Any]:
    observed_scenarios = tuple(sorted(inventory["by_scenario"]))
    scenario_cells = inventory["by_scenario_action_intent_camera_role"]
    pair_cells = inventory["by_action_intent_and_camera_role"]
    requests: dict[tuple[str, str, str], dict[str, Any]] = {}

    def scenario_for(intent: str, role: str) -> str:
        if not observed_scenarios:
            return _FALLBACK_SCENARIO
        return min(
            observed_scenarios,
            key=lambda scenario: (
                scenario_cells[scenario][intent][role][
                    "unique_sample_count"
                ],
                scenario,
            ),
        )

    def add(
        *,
        scenario: str,
        intent: str,
        role: str,
        samples: int,
        episodes: int,
        seeds: int,
        reason: str,
    ) -> None:
        key = (scenario, intent, role)
        item = requests.setdefault(
            key,
            {
                "scenario_version": scenario,
                "action_intent": intent,
                "camera_role": role,
                "minimum_additional_unique_samples": 0,
                "minimum_additional_unique_episodes": 0,
                "minimum_additional_new_training_seeds": 0,
                "coverage_reasons": set(),
            },
        )
        item["minimum_additional_unique_samples"] = max(
            item["minimum_additional_unique_samples"], max(0, samples)
        )
        item["minimum_additional_unique_episodes"] = max(
            item["minimum_additional_unique_episodes"], max(0, episodes)
        )
        item["minimum_additional_new_training_seeds"] = max(
            item["minimum_additional_new_training_seeds"], max(0, seeds)
        )
        item["coverage_reasons"].add(reason)

    for intent in _INTENTS:
        for role in _CAMERA_ROLES:
            cell = pair_cells[intent][role]
            sample_gap = (
                policy.minimum_unique_samples_per_intent_camera_role
                - cell["unique_sample_count"]
            )
            episode_gap = (
                policy.minimum_unique_episodes_per_intent_camera_role
                - cell["unique_episode_count"]
            )
            seed_gap = (
                policy.minimum_unique_seeds_per_intent_camera_role
                - cell["unique_seed_count"]
            )
            if max(sample_gap, episode_gap, seed_gap) > 0:
                add(
                    scenario=scenario_for(intent, role),
                    intent=intent,
                    role=role,
                    samples=sample_gap,
                    episodes=episode_gap,
                    seeds=seed_gap,
                    reason="intent_camera_role_structural_deficit",
                )

    for scenario in policy.required_scenarios:
        for intent in _INTENTS:
            for role in _CAMERA_ROLES:
                cell = (
                    scenario_cells[scenario][intent][role]
                    if scenario in scenario_cells
                    else {
                        "unique_sample_count": 0,
                        "unique_episode_count": 0,
                        "unique_seed_count": 0,
                    }
                )
                sample_gap = (
                    policy.minimum_unique_samples_per_intent_camera_role
                    - cell["unique_sample_count"]
                )
                episode_gap = (
                    policy.minimum_unique_episodes_per_intent_camera_role
                    - cell["unique_episode_count"]
                )
                seed_gap = (
                    policy.minimum_unique_seeds_per_intent_camera_role
                    - cell["unique_seed_count"]
                )
                if max(sample_gap, episode_gap, seed_gap) > 0:
                    add(
                        scenario=scenario,
                        intent=intent,
                        role=role,
                        samples=sample_gap,
                        episodes=episode_gap,
                        seeds=seed_gap,
                        reason="required_scenario_cell_deficit",
                    )

    ordered: list[dict[str, Any]] = []
    for index, key in enumerate(sorted(requests), start=1):
        item = requests[key]
        ordered.append(
            {
                "request_id": f"AV-CORPUS-{index:03d}",
                "scenario_version": item["scenario_version"],
                "action_intent": item["action_intent"],
                "camera_role": item["camera_role"],
                "minimum_additional_unique_samples": item[
                    "minimum_additional_unique_samples"
                ],
                "minimum_additional_unique_episodes": item[
                    "minimum_additional_unique_episodes"
                ],
                "minimum_additional_new_training_seeds": item[
                    "minimum_additional_new_training_seeds"
                ],
                "coverage_reasons": sorted(item["coverage_reasons"]),
                "seed_selection": (
                    "allocate_new_training_seeds_from_the_bound_registry; "
                    "exclude validation, test and reserved evaluation seeds"
                ),
            }
        )
    noncoverage_reasons = sorted(
        reason
        for reason in failure_reasons
        if "coverage_below_minimum" not in reason
        and not reason.endswith("_missing")
        and not reason.startswith("required_scenario_cell:")
    )
    return {
        "schema_version": ACTIVE_VISION_COLLECTION_PLAN_SCHEMA_VERSION,
        "status": (
            "development_coverage_satisfied"
            if not failure_reasons
            else "collection_or_remediation_required"
        ),
        "requests": ordered,
        "blocking_remediation_reasons": noncoverage_reasons,
        "collection_constraints": [
            "collect complete new episodes; do not copy or duplicate samples",
            "do not use reweighting or oversampling to claim corpus coverage",
            "do not use validation, test or reserved evaluation seeds",
            "do not place simulator, actor or evaluator truth identity in online records",
            "synthetic fixtures may verify software but cannot establish a formal candidate",
            "global_track_id remains a read-only center-owned reference",
        ],
    }


def _canonical_seed_evidence(
    manifest: Mapping[str, Any],
    *,
    descriptor_seeds_by_split: Mapping[str, set[int]],
) -> dict[str, Any]:
    view = manifest.get("canonical_seed_view")
    if not isinstance(view, Mapping):
        return {
            "available": False,
            "source": None,
            "formal_registry_binding": False,
            "reserved_seed_count": None,
            "reason": "canonical_seed_view_unavailable",
        }
    split = view.get("canonical_split")
    contract = view.get("view_contract")
    if not isinstance(split, Mapping) or not isinstance(contract, Mapping):
        return {
            "available": False,
            "source": "canonical_seed_view",
            "formal_registry_binding": False,
            "reserved_seed_count": None,
            "reason": "canonical_seed_view_contract_invalid",
        }
    try:
        declared = split["seed_values"]
        if not isinstance(declared, Mapping):
            raise ValueError("seed values missing")
        declared_sets = {
            name: set(_seed_catalog(declared[name], field_name=f"{name}_seeds"))
            for name in _SPLITS
        }
        if declared_sets != {
            name: set(descriptor_seeds_by_split[name]) for name in _SPLITS
        }:
            raise ValueError("canonical split differs from descriptors")
        if split.get("reserved_evaluation_seed_overlap") != []:
            raise ValueError("reserved overlap is not empty")
        if contract.get("sample_copy_allowed") is not False:
            raise ValueError("sample copy contract is not false")
        if not isinstance(view.get("training_seed_registry"), Mapping):
            raise ValueError("training registry binding missing")
        if not isinstance(view.get("shared_seed_registry"), Mapping):
            raise ValueError("shared registry binding missing")
    except (KeyError, TypeError, ValueError):
        return {
            "available": False,
            "source": "canonical_seed_view",
            "formal_registry_binding": False,
            "reserved_seed_count": None,
            "reason": "canonical_seed_view_contract_invalid",
        }
    return {
        "available": True,
        "source": "canonical_seed_view",
        "formal_registry_binding": True,
        "reserved_seed_count": None,
        "reason": None,
    }


def _seed_catalog(
    values: Sequence[int] | None,
    *,
    field_name: str,
) -> tuple[int, ...]:
    if values is None:
        return ()
    result = tuple(_seed(value, field_name) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} contains duplicate values")
    return tuple(sorted(result))


def _seed(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{field_name} must contain integers")
    result = int(value)
    if result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _episode_key(scenario: str, seed: int, episode_id: str) -> str:
    return f"{scenario}|{seed}|{episode_id}"


def _key(value: Any, field_name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{field_name} must be non-empty")
    return result


def _content_sha256(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ACTIVE_VISION_COLLECTION_PLAN_SCHEMA_VERSION",
    "ACTIVE_VISION_CORPUS_AUDIT_SCHEMA_VERSION",
    "ACTIVE_VISION_CORPUS_POLICY_VERSION",
    "ACTIVE_VISION_RESEARCH_EVIDENCE_GATE_SCHEMA_VERSION",
    "ActiveVisionCorpusCoverageError",
    "ActiveVisionCorpusCoveragePolicy",
    "active_vision_camera_role",
    "audit_active_vision_training_corpus",
    "require_active_vision_training_corpus_ready",
    "require_active_vision_simulation_research_corpus_ready",
    "validate_active_vision_corpus_audit",
]
