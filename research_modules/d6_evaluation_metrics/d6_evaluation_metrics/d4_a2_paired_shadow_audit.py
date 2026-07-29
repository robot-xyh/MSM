"""Strict read-only audit for current-lineage D4 A2/R0 shadow pairs.

The audit authenticates the frozen A2 source and recomputes runtime
distribution facts through the source adapters.  Per-seed treatment is then
accepted only when public D4 safe-adoption and same-key R0 contracts prove a
non-zero model intervention, a strict D3 successor, complete acknowledgements,
and a confirmed physical window.  Rule fallback is never treatment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from hashlib import sha256
import json
from math import isclose, isfinite
from pathlib import Path
from typing import Any

from .learning_run_source_adapters import (
    LearningRunSourceAdapterError,
    load_learning_run_source_evidence_bytes,
)
from .strict_learning_adoption_audit import (
    StrictLearningAdoptionAuditError,
    audit_learning_adoption_evidence,
    build_learning_adoption_audit_input,
)


D4_A2_PAIRED_SHADOW_INPUT_SCHEMA_VERSION = (
    "d6.d4-a2-paired-shadow-audit-input.v1"
)
D4_A2_PAIRED_SHADOW_AUDIT_SCHEMA_VERSION = (
    "d6.d4-a2-paired-shadow-audit.v1"
)
D4_A2_FROZEN_SEED_REGISTRY_SCHEMA_VERSION = (
    "d6.d4-a2-frozen-shadow-seed-registry.v1"
)
D4_A2_MODEL_STATE_SHA256 = (
    "fd1b9c4cf7580083fadc04a70b87aa6439930eba764a970279611ccc57f30047"
)
D4_A2_CANDIDATE_MANIFEST_SHA256 = (
    "7cc10ad770bd95fcb813dbf3d16b17040ec5f41f80fe0dc53e3e291a32f4de64"
)
D4_A2_MINIMUM_FORMAL_SEED_COUNT = 20

_INPUT_FIELDS = frozenset(
    {
        "schema_version",
        "audit_id",
        "model_source_reference",
        "runtime_distribution_reference",
        "seed_registry",
        "required_metrics",
        "pairs",
        "content_sha256",
    }
)
_ARTIFACT_FIELDS = frozenset({"path", "file_sha256"})
_SEED_REGISTRY_FIELDS = frozenset(
    {
        "schema_version",
        "registry_id",
        "registry_version",
        "frozen_at_utc",
        "frozen_before_execution",
        "candidate_manifest_file_sha256",
        "model_state_sha256",
        "evaluation_seeds",
        "registrations",
        "content_sha256",
    }
)
_PAIR_FIELDS = frozenset(
    {
        "seed",
        "started_at_utc",
        "candidate_episode_id",
        "r0_episode_id",
        "candidate_event_log_sha256",
        "r0_event_log_sha256",
        "candidate_external_config_sha256",
        "r0_external_config_sha256",
        "model_state_sha256",
        "adoption_records",
        "online_truth_use_count",
        "audited_finite_value_count",
        "nonfinite_value_count",
        "candidate_metrics",
        "r0_metrics",
    }
)
_METRIC_FIELDS = frozenset(
    {"numerator", "denominator", "value", "direction", "tolerance"}
)
_PERMISSION_FIELDS = (
    "admission",
    "assist",
    "authority",
    "assignment",
    "failover",
    "control",
)
_HEX64 = frozenset("0123456789abcdef")


class D4A2PairedShadowAuditError(ValueError):
    """Stable request-level failure for malformed audit inputs."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = str(code)
        self.detail = None if detail is None else str(detail)
        message = self.code if self.detail is None else f"{self.code}: {self.detail}"
        super().__init__(message)


def build_d4_a2_paired_shadow_audit_input(
    *,
    audit_id: str,
    model_source_reference: Mapping[str, Any],
    runtime_distribution_reference: Mapping[str, Any],
    seed_registry: Mapping[str, Any],
    required_metrics: Sequence[str],
    pairs: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one content-addressed audit request without deriving evidence."""

    body = {
        "schema_version": D4_A2_PAIRED_SHADOW_INPUT_SCHEMA_VERSION,
        "audit_id": _text(audit_id, "audit_id"),
        "model_source_reference": _json_mapping(
            model_source_reference,
            "model_source_reference",
        ),
        "runtime_distribution_reference": _json_mapping(
            runtime_distribution_reference,
            "runtime_distribution_reference",
        ),
        "seed_registry": _json_mapping(seed_registry, "seed_registry"),
        "required_metrics": list(required_metrics),
        "pairs": [_json_mapping(item, "pairs") for item in pairs],
    }
    body["content_sha256"] = _canonical_sha256(body)
    return validate_d4_a2_paired_shadow_audit_input(body)


def validate_d4_a2_paired_shadow_audit_input(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact fields, hashes, finite values, and denominator schemas."""

    payload = _json_mapping(value, "input")
    _exact(payload, _INPUT_FIELDS, "input")
    if payload["schema_version"] != D4_A2_PAIRED_SHADOW_INPUT_SCHEMA_VERSION:
        _fail("a2_paired_input_schema_unsupported")
    source_reference = _artifact_reference(
        payload["model_source_reference"],
        "model_source_reference",
    )
    distribution_reference = _artifact_reference(
        payload["runtime_distribution_reference"],
        "runtime_distribution_reference",
    )
    registry = _validate_seed_registry(payload["seed_registry"])
    required_metrics = list(
        _text_sequence(payload["required_metrics"], "required_metrics")
    )
    if not required_metrics:
        _fail("a2_paired_required_metrics_empty")
    pairs = [
        _validate_pair(item, required_metrics=required_metrics, index=index)
        for index, item in enumerate(
            _sequence(payload["pairs"], "pairs")
        )
    ]
    pair_seeds = [item["seed"] for item in pairs]
    if len(pair_seeds) != len(set(pair_seeds)):
        _fail("a2_paired_duplicate_seed")
    normalized: dict[str, Any] = {
        "schema_version": payload["schema_version"],
        "audit_id": _text(payload["audit_id"], "audit_id"),
        "model_source_reference": source_reference,
        "runtime_distribution_reference": distribution_reference,
        "seed_registry": registry,
        "required_metrics": required_metrics,
        "pairs": pairs,
    }
    claimed = _sha256_text(payload["content_sha256"], "content_sha256")
    if _canonical_sha256(normalized) != claimed:
        _fail("a2_paired_input_content_sha256_mismatch")
    normalized["content_sha256"] = claimed
    return normalized


def audit_d4_a2_paired_shadow(
    value: Mapping[str, Any],
    *,
    artifact_root: str | Path,
) -> dict[str, Any]:
    """Audit every pair and aggregate only complete non-fallback treatment."""

    payload = validate_d4_a2_paired_shadow_audit_input(value)
    root = _artifact_root(artifact_root)
    model_source, model_reasons = _load_source(
        payload["model_source_reference"],
        root=root,
        gate="model_source",
    )
    distribution, distribution_reasons = _load_source(
        payload["runtime_distribution_reference"],
        root=root,
        gate="runtime_distribution_compatible",
    )
    model_verified = bool(
        model_source is not None
        and model_source["source_class"]
        == "formal_current_lineage_source_audit"
        and model_source["formal"] is True
        and model_source["facts"]["audit_passed"] is True
        and model_source["facts"]["model_identity"]
        == f"sha256:{D4_A2_MODEL_STATE_SHA256}"
    )
    distribution_facts = (
        {} if distribution is None else distribution["facts"]
    )
    distribution_blockers = _runtime_distribution_blockers(
        distribution_facts
    )
    distribution_compatible = bool(
        distribution is not None and not distribution_blockers
    )

    registry_reasons = _seed_registry_blockers(
        payload["seed_registry"],
        payload["pairs"],
        distribution_facts,
    )
    pair_results = [
        _audit_pair(
            pair,
            required_metrics=payload["required_metrics"],
            registration_by_seed={
                int(item["seed"]): item
                for item in payload["seed_registry"]["registrations"]
            },
            runtime_seed_diagnostics=distribution_facts.get(
                "seed_diagnostics",
                {},
            ),
            global_reasons=(
                *model_reasons,
                *distribution_reasons,
                *registry_reasons,
                *(() if model_verified else ("a2_model_source_unverified",)),
            ),
        )
        for pair in payload["pairs"]
    ]
    aggregate_reasons = _dedupe(
        [
            *model_reasons,
            *distribution_reasons,
            *distribution_blockers,
            *registry_reasons,
            *(
                ()
                if model_verified
                else ("a2_model_source_unverified",)
            ),
            *(
                reason
                for row in pair_results
                for reason in row["reason_codes"]
            ),
        ]
    )
    seed_count = len({row["seed"] for row in pair_results})
    available_count = sum(
        row["availability"] == "available" for row in pair_results
    )
    treatment_count = sum(
        row["treatment_observed"] for row in pair_results
    )
    rollout_precondition_count = sum(
        row["rollout_precondition_satisfied"] for row in pair_results
    )
    non_degraded_count = sum(
        row["all_metrics_non_degraded"] is True for row in pair_results
    )
    complete_denominator_count = sum(
        row["complete_denominators"] for row in pair_results
    )
    formal_pairing_available = bool(
        model_verified
        and distribution_compatible
        and not registry_reasons
        and seed_count >= D4_A2_MINIMUM_FORMAL_SEED_COUNT
        and available_count == len(pair_results)
        and len(pair_results) == seed_count
    )
    if seed_count < D4_A2_MINIMUM_FORMAL_SEED_COUNT:
        aggregate_reasons = _dedupe(
            [
                *aggregate_reasons,
                "a2_preregistered_unseen_seed_count_below_20",
            ]
        )
    result: dict[str, Any] = {
        "schema_version": D4_A2_PAIRED_SHADOW_AUDIT_SCHEMA_VERSION,
        "input_schema_version": payload["schema_version"],
        "input_content_sha256": payload["content_sha256"],
        "audit_id": payload["audit_id"],
        "scope": "read-only-shadow-evaluation-no-runtime-authority",
        "model_source_verified": model_verified,
        "runtime_distribution_compatible": distribution_compatible,
        "seed_results": pair_results,
        "aggregate": {
            "registered_seed_count": len(
                payload["seed_registry"]["evaluation_seeds"]
            ),
            "pair_seed_count": seed_count,
            "available_pair_count": available_count,
            "rollout_precondition_pair_count": rollout_precondition_count,
            "treatment_pair_count": treatment_count,
            "complete_denominator_pair_count": complete_denominator_count,
            "non_degraded_pair_count": non_degraded_count,
            "paired_non_degradation_available": formal_pairing_available,
            "all_pairs_non_degraded": (
                all(
                    row["all_metrics_non_degraded"] is True
                    for row in pair_results
                )
                if formal_pairing_available
                else None
            ),
            "reason_codes": [] if formal_pairing_available else aggregate_reasons,
        },
        "permissions": {name: False for name in _PERMISSION_FIELDS},
    }
    result["content_sha256"] = _canonical_sha256(result)
    return result


def write_d4_a2_paired_shadow_audit(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write JSON and a compact Chinese audit report."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "d4_a2_paired_shadow_audit.json"
    markdown_path = output / "D4_A2_PAIRED_SHADOW_AUDIT_CN.md"
    checksum_path = output / "SHA256SUMS"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    aggregate = result["aggregate"]
    markdown_path.write_text(
        "\n".join(
            (
                "# D4 A2 成对影子审计",
                "",
                "## 结论",
                "",
                f"- 模型来源验证：{result['model_source_verified']}。",
                (
                    "- 运行分布兼容："
                    f"{result['runtime_distribution_compatible']}。"
                ),
                (
                    "- 影子动作前置条件："
                    f"{aggregate['rollout_precondition_pair_count']}/"
                    f"{aggregate['pair_seed_count']}。"
                ),
                (
                    "- 可审计 treatment："
                    f"{aggregate['treatment_pair_count']}/"
                    f"{aggregate['pair_seed_count']}。"
                ),
                (
                    "- 成对非退化可用："
                    f"{aggregate['paired_non_degradation_available']}。"
                ),
                (
                    "- 阻断：`"
                    + ";".join(aggregate["reason_codes"])
                    + "`。"
                ),
                "",
                "D6 未授予准入、辅助、分配、降级或控制权限。",
                "",
            )
        ),
        encoding="utf-8",
    )
    checksum_path.write_text(
        "".join(
            f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in (json_path, markdown_path)
        ),
        encoding="ascii",
    )
    return {
        "json": json_path,
        "markdown": markdown_path,
        "checksums": checksum_path,
    }


def _audit_pair(
    pair: Mapping[str, Any],
    *,
    required_metrics: Sequence[str],
    registration_by_seed: Mapping[int, Mapping[str, Any]],
    runtime_seed_diagnostics: Mapping[str, Any],
    global_reasons: Sequence[str],
) -> dict[str, Any]:
    reasons = list(global_reasons)
    seed = pair["seed"]
    registration = registration_by_seed.get(seed)
    if registration is None:
        reasons.append("a2_seed_registration_missing")
    else:
        if registration["episode_id"] != pair["candidate_episode_id"]:
            reasons.append("a2_seed_registration_episode_mismatch")
        if _utc(registration["registered_at_utc"], "registered_at_utc") >= _utc(
            pair["started_at_utc"],
            "started_at_utc",
        ):
            reasons.append("a2_seed_not_registered_before_execution")

    seed_diagnostic = runtime_seed_diagnostics.get(str(seed))
    rollout_precondition_satisfied = False
    if not isinstance(seed_diagnostic, Mapping):
        reasons.append("a2_runtime_seed_diagnostic_missing")
    else:
        reasons.extend(_runtime_distribution_blockers(seed_diagnostic))
        rollout_reasons = _rollout_precondition_blockers(seed_diagnostic)
        reasons.extend(rollout_reasons)
        rollout_precondition_satisfied = not rollout_reasons

    adoption = _audit_adoption_records(pair["adoption_records"])
    reasons.extend(adoption["reason_codes"])
    treatment_observed = adoption["treatment_observed"]
    if treatment_observed:
        reasons.extend(_validate_pair_lineage(pair, adoption))

    metric_results: dict[str, Any] = {}
    complete_denominators = True
    all_non_degraded = True
    for name in required_metrics:
        candidate = pair["candidate_metrics"].get(name)
        r0 = pair["r0_metrics"].get(name)
        if candidate is None or r0 is None:
            reasons.append(f"a2_metric_unavailable.{name}")
            complete_denominators = False
            all_non_degraded = False
            continue
        denominator_complete = bool(
            candidate["denominator"] > 0
            and r0["denominator"] > 0
            and candidate["denominator"] == r0["denominator"]
        )
        if not denominator_complete:
            reasons.append(f"a2_metric_denominator_incomplete.{name}")
        non_degraded = (
            _metric_non_degraded(candidate, r0)
            if denominator_complete and treatment_observed
            else None
        )
        metric_results[name] = {
            "candidate_value": candidate["value"],
            "r0_value": r0["value"],
            "denominator": (
                candidate["denominator"]
                if denominator_complete
                else None
            ),
            "non_degraded": non_degraded,
        }
        complete_denominators &= denominator_complete
        all_non_degraded &= non_degraded is True

    if pair["online_truth_use_count"] != 0:
        reasons.append("a2_online_truth_use_nonzero")
    if (
        pair["audited_finite_value_count"] <= 0
        or pair["nonfinite_value_count"] != 0
    ):
        reasons.append("a2_finite_state_incomplete")
    normalized = _dedupe(reasons)
    available = bool(
        not normalized
        and treatment_observed
        and complete_denominators
    )
    return {
        "seed": seed,
        "availability": "available" if available else "unavailable",
        "rollout_precondition_satisfied": (
            rollout_precondition_satisfied
        ),
        "treatment_observed": treatment_observed,
        "complete_denominators": complete_denominators,
        "all_metrics_non_degraded": all_non_degraded if available else None,
        "metric_results": metric_results,
        "reason_codes": [] if available else normalized,
    }


def _audit_adoption_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    try:
        request = build_learning_adoption_audit_input(a2=records)
        audit = audit_learning_adoption_evidence(request)
    except (StrictLearningAdoptionAuditError, TypeError, ValueError) as exc:
        return {
            "treatment_observed": False,
            "reason_codes": [
                f"a2_strict_adoption_audit_rejected.{type(exc).__name__}"
            ],
            "pair_record": None,
        }
    row = audit["variants"]["A2"]
    metrics = (
        "actual_adoption_count",
        "physical_window_count",
        "same_key_r0_pair_count",
        "benefit_auditable_count",
    )
    complete = bool(
        row["availability"] == "available"
        and all(
            row[name]["availability"] == "available"
            and row[name]["value"] == 1
            for name in metrics
        )
    )
    reasons = [] if complete else [
        *row["blocker_codes"],
        "a2_strict_successor_ack_physical_pair_incomplete",
    ]
    pair_records = [
        item
        for item in records
        if item.get("schema")
        == "d4-region-resource-a2-benefit-audit-input-v1"
    ]
    model_reasons = _model_intervention_blockers(records)
    reasons.extend(model_reasons)
    return {
        "treatment_observed": complete and not model_reasons,
        "reason_codes": _dedupe(reasons),
        "pair_record": pair_records[0] if len(pair_records) == 1 else None,
    }


def _model_intervention_blockers(
    records: Sequence[Mapping[str, Any]],
) -> list[str]:
    safe_records = [
        item
        for item in records
        if item.get("schema")
        == "d4-region-resource-safe-adoption-evidence-v1"
    ]
    if len(safe_records) != 1:
        return ["a2_safe_adoption_record_count_invalid"]
    preparation = safe_records[0].get("preparation")
    if not isinstance(preparation, Mapping):
        return ["a2_safe_adoption_preparation_missing"]
    applied = preparation.get("applied_recommendation")
    if not isinstance(applied, Mapping):
        return ["a2_applied_model_recommendation_missing"]
    advisory = applied.get("advisory")
    intervention = applied.get("intervention_evidence")
    reasons: list[str] = []
    if not isinstance(advisory, Mapping):
        reasons.append("a2_model_advisory_missing")
    else:
        if advisory.get("model_sha256") != D4_A2_MODEL_STATE_SHA256:
            reasons.append("a2_model_state_binding_mismatch")
        if advisory.get("policy_version") != (
            "d4-region-a2-current-lineage-development-v1"
        ):
            reasons.append("a2_model_version_binding_mismatch")
        if advisory.get("source") != "learned":
            reasons.append("a2_rule_adapter_not_treatment")
        if advisory.get("fallback_reason") is not None:
            reasons.append("a2_rule_fallback_not_treatment")
    if not isinstance(intervention, Mapping):
        reasons.append("a2_intervention_evidence_missing")
    elif (
        intervention.get("identifiable_intervention_available") is not True
        or not intervention.get("intervention_fields")
    ):
        reasons.append("a2_identifiable_nonzero_intervention_missing")
    return reasons


def _validate_pair_lineage(
    pair: Mapping[str, Any],
    adoption: Mapping[str, Any],
) -> list[str]:
    record = adoption.get("pair_record")
    if not isinstance(record, Mapping):
        return ["a2_pair_contract_missing"]
    candidate = record.get("candidate_window")
    r0 = record.get("same_key_r0_window")
    context = record.get("context")
    if not all(isinstance(item, Mapping) for item in (candidate, r0, context)):
        return ["a2_pair_window_or_context_missing"]
    reasons: list[str] = []
    expected = (
        (
            candidate.get("execution_arm_id"),
            pair["candidate_episode_id"],
            "a2_candidate_episode_mismatch",
        ),
        (
            r0.get("execution_arm_id"),
            pair["r0_episode_id"],
            "a2_r0_episode_mismatch",
        ),
        (
            candidate.get("source_event_log_sha256"),
            pair["candidate_event_log_sha256"],
            "a2_candidate_event_log_mismatch",
        ),
        (
            r0.get("source_event_log_sha256"),
            pair["r0_event_log_sha256"],
            "a2_r0_event_log_mismatch",
        ),
        (
            context.get("paired_exogenous_config_sha256"),
            pair["candidate_external_config_sha256"],
            "a2_candidate_external_config_mismatch",
        ),
        (
            context.get("paired_exogenous_config_sha256"),
            pair["r0_external_config_sha256"],
            "a2_r0_external_config_mismatch",
        ),
    )
    reasons.extend(code for observed, target, code in expected if observed != target)
    if pair["candidate_episode_id"] == pair["r0_episode_id"]:
        reasons.append("a2_candidate_r0_episode_reuse")
    if pair["candidate_event_log_sha256"] == pair["r0_event_log_sha256"]:
        reasons.append("a2_candidate_r0_event_log_reuse")
    if (
        pair["candidate_external_config_sha256"]
        != pair["r0_external_config_sha256"]
    ):
        reasons.append("a2_external_configuration_mismatch")
    if pair["model_state_sha256"] != D4_A2_MODEL_STATE_SHA256:
        reasons.append("a2_pair_model_state_mismatch")
    return reasons


def _runtime_distribution_blockers(
    facts: Mapping[str, Any],
) -> list[str]:
    if not facts:
        return ["a2_runtime_distribution_evidence_unavailable"]
    audited = facts.get("audited_snapshot_count")
    finite_records = facts.get("finite_record_count")
    nonfinite_records = facts.get("nonfinite_record_count")
    compatible = facts.get("compatible_snapshot_count")
    ood = facts.get("feature_ood_snapshot_count")
    reasons: list[str] = []
    if not isinstance(audited, int) or audited <= 0:
        reasons.append("a2_runtime_distribution_audit_empty")
        return reasons
    if (
        not isinstance(finite_records, int)
        or not isinstance(nonfinite_records, int)
        or finite_records + nonfinite_records != audited
    ):
        reasons.append("a2_runtime_finite_record_denominator_mismatch")
    elif nonfinite_records > 0:
        reasons.append("a2_runtime_nonfinite_record")
    if (
        not isinstance(compatible, int)
        or not isinstance(ood, int)
        or compatible + ood != audited
    ):
        reasons.append("a2_runtime_distribution_snapshot_denominator_mismatch")
    if ood:
        reasons.append("a2_runtime_feature_ood")
        counts = facts.get("feature_ood_counts", {})
        if isinstance(counts, Mapping):
            reasons.extend(
                f"a2_runtime_feature_ood.{name}"
                for name in sorted(counts)
            )
    return _dedupe(reasons)


def _rollout_precondition_blockers(
    facts: Mapping[str, Any],
) -> list[str]:
    """Diagnose shadow action availability without redefining distribution."""

    audited = facts.get("audited_snapshot_count")
    actions = facts.get("model_action_count")
    missing = facts.get("missing_model_action_count")
    fallbacks = facts.get("rule_fallback_count")
    if not isinstance(audited, int) or audited <= 0:
        return ["a2_rollout_diagnostic_unavailable"]
    reasons: list[str] = []
    if (
        not isinstance(actions, int)
        or not isinstance(missing, int)
        or actions + missing != audited
    ):
        reasons.append("a2_rollout_action_denominator_mismatch")
    elif actions <= 0:
        reasons.append("a2_model_action_missing")
    if (
        isinstance(actions, int)
        and isinstance(fallbacks, int)
        and actions == 0
        and fallbacks == audited
    ):
        reasons.append("a2_rule_fallback_only_not_treatment")
    return _dedupe(reasons)


def _seed_registry_blockers(
    registry: Mapping[str, Any],
    pairs: Sequence[Mapping[str, Any]],
    distribution_facts: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    seeds = set(registry["evaluation_seeds"])
    pair_seeds = {item["seed"] for item in pairs}
    diagnostic_seeds = {
        int(seed)
        for seed in distribution_facts.get("seed_diagnostics", {})
        if str(seed).isdigit()
    }
    if registry["frozen_before_execution"] is not True:
        reasons.append("a2_unseen_seed_registry_not_frozen_before_execution")
    if len(seeds) < D4_A2_MINIMUM_FORMAL_SEED_COUNT:
        reasons.append("a2_preregistered_unseen_seed_count_below_20")
    if pair_seeds != seeds:
        reasons.append("a2_registered_pair_seed_coverage_mismatch")
    if diagnostic_seeds != seeds:
        reasons.append("a2_registered_runtime_seed_coverage_mismatch")
    if registry["candidate_manifest_file_sha256"] != (
        D4_A2_CANDIDATE_MANIFEST_SHA256
    ):
        reasons.append("a2_seed_registry_candidate_manifest_mismatch")
    if registry["model_state_sha256"] != D4_A2_MODEL_STATE_SHA256:
        reasons.append("a2_seed_registry_model_state_mismatch")
    runtime_binding = distribution_facts.get("candidate_binding_sha256")
    if not isinstance(runtime_binding, str):
        reasons.append("a2_runtime_candidate_binding_unavailable")
    elif any(
        item["candidate_binding_sha256"] != runtime_binding
        for item in registry["registrations"]
    ):
        reasons.append("a2_seed_registration_candidate_binding_mismatch")
    return reasons


def _validate_seed_registry(value: Any) -> dict[str, Any]:
    registry = _json_mapping(value, "seed_registry")
    _exact(registry, _SEED_REGISTRY_FIELDS, "seed_registry")
    if (
        registry["schema_version"]
        != D4_A2_FROZEN_SEED_REGISTRY_SCHEMA_VERSION
    ):
        _fail("a2_seed_registry_schema_unsupported")
    seeds = list(_integer_sequence(registry["evaluation_seeds"], "evaluation_seeds"))
    if len(seeds) != len(set(seeds)):
        _fail("a2_seed_registry_duplicate_seed")
    registrations = [
        _validate_seed_registration(item, index=index)
        for index, item in enumerate(
            _sequence(registry["registrations"], "registrations")
        )
    ]
    if {item["seed"] for item in registrations} != set(seeds):
        _fail("a2_seed_registry_registration_coverage_mismatch")
    normalized: dict[str, Any] = {
        "schema_version": registry["schema_version"],
        "registry_id": _text(registry["registry_id"], "registry_id"),
        "registry_version": _positive_int(
            registry["registry_version"],
            "registry_version",
        ),
        "frozen_at_utc": _utc_text(
            registry["frozen_at_utc"],
            "frozen_at_utc",
        ),
        "frozen_before_execution": _boolean(
            registry["frozen_before_execution"],
            "frozen_before_execution",
        ),
        "candidate_manifest_file_sha256": _sha256_text(
            registry["candidate_manifest_file_sha256"],
            "candidate_manifest_file_sha256",
        ),
        "model_state_sha256": _sha256_text(
            registry["model_state_sha256"],
            "model_state_sha256",
        ),
        "evaluation_seeds": seeds,
        "registrations": registrations,
    }
    claimed = _sha256_text(
        registry["content_sha256"],
        "seed_registry.content_sha256",
    )
    if _canonical_sha256(normalized) != claimed:
        _fail("a2_seed_registry_content_sha256_mismatch")
    normalized["content_sha256"] = claimed
    return normalized


def _validate_seed_registration(value: Any, *, index: int) -> dict[str, Any]:
    context = f"seed_registry.registrations.{index}"
    item = _json_mapping(value, context)
    required = frozenset(
        {
            "seed",
            "episode_id",
            "registered_at_utc",
            "candidate_binding_sha256",
            "registration",
        }
    )
    _exact(item, required, context)
    registration = _json_mapping(
        item["registration"],
        f"{context}.registration",
    )
    try:
        module = __import__(
            "research_modules.d4_distributed_fallback."
            "d4_distributed_fallback.region_resource_current_lineage_shadow",
            fromlist=["RegionResourceCurrentLineageShadowSeedRegistration"],
        )
        parsed = (
            module.RegionResourceCurrentLineageShadowSeedRegistration
            .from_mapping(registration)
        )
    except (ImportError, TypeError, ValueError) as exc:
        _fail(
            "a2_seed_registration_public_contract_rejected",
            f"{index}:{type(exc).__name__}",
        )
    seed = _nonnegative_int(item["seed"], f"{context}.seed")
    episode_id = _text(item["episode_id"], f"{context}.episode_id")
    binding = _sha256_text(
        item["candidate_binding_sha256"],
        f"{context}.candidate_binding_sha256",
    )
    if parsed.to_dict() != registration:
        _fail("a2_seed_registration_roundtrip_mismatch", str(index))
    if (
        parsed.seed != seed
        or parsed.episode_id != episode_id
        or parsed.candidate_binding_sha256 != binding
        or parsed.shadow_only is not True
        or parsed.purpose != "strict_unseen_shadow"
    ):
        _fail("a2_seed_registration_binding_mismatch", str(index))
    return {
        "seed": seed,
        "episode_id": episode_id,
        "registered_at_utc": _utc_text(
            item["registered_at_utc"],
            f"{context}.registered_at_utc",
        ),
        "candidate_binding_sha256": binding,
        "registration": registration,
    }


def _validate_pair(
    value: Any,
    *,
    required_metrics: Sequence[str],
    index: int,
) -> dict[str, Any]:
    context = f"pairs.{index}"
    pair = _json_mapping(value, context)
    _exact(pair, _PAIR_FIELDS, context)
    candidate_metrics = _validate_metrics(
        pair["candidate_metrics"],
        required_metrics=required_metrics,
        context=f"{context}.candidate_metrics",
    )
    r0_metrics = _validate_metrics(
        pair["r0_metrics"],
        required_metrics=required_metrics,
        context=f"{context}.r0_metrics",
    )
    return {
        "seed": _nonnegative_int(pair["seed"], f"{context}.seed"),
        "started_at_utc": _utc_text(
            pair["started_at_utc"],
            f"{context}.started_at_utc",
        ),
        "candidate_episode_id": _text(
            pair["candidate_episode_id"],
            f"{context}.candidate_episode_id",
        ),
        "r0_episode_id": _text(
            pair["r0_episode_id"],
            f"{context}.r0_episode_id",
        ),
        "candidate_event_log_sha256": _sha256_text(
            pair["candidate_event_log_sha256"],
            f"{context}.candidate_event_log_sha256",
        ),
        "r0_event_log_sha256": _sha256_text(
            pair["r0_event_log_sha256"],
            f"{context}.r0_event_log_sha256",
        ),
        "candidate_external_config_sha256": _sha256_text(
            pair["candidate_external_config_sha256"],
            f"{context}.candidate_external_config_sha256",
        ),
        "r0_external_config_sha256": _sha256_text(
            pair["r0_external_config_sha256"],
            f"{context}.r0_external_config_sha256",
        ),
        "model_state_sha256": _sha256_text(
            pair["model_state_sha256"],
            f"{context}.model_state_sha256",
        ),
        "adoption_records": list(
            _mapping_sequence(
                pair["adoption_records"],
                f"{context}.adoption_records",
            )
        ),
        "online_truth_use_count": _nonnegative_int(
            pair["online_truth_use_count"],
            f"{context}.online_truth_use_count",
        ),
        "audited_finite_value_count": _nonnegative_int(
            pair["audited_finite_value_count"],
            f"{context}.audited_finite_value_count",
        ),
        "nonfinite_value_count": _nonnegative_int(
            pair["nonfinite_value_count"],
            f"{context}.nonfinite_value_count",
        ),
        "candidate_metrics": candidate_metrics,
        "r0_metrics": r0_metrics,
    }


def _validate_metrics(
    value: Any,
    *,
    required_metrics: Sequence[str],
    context: str,
) -> dict[str, Any]:
    metrics = _json_mapping(value, context)
    unexpected = set(metrics) - set(required_metrics)
    if unexpected:
        _fail("a2_metric_unexpected", ",".join(sorted(unexpected)))
    result: dict[str, Any] = {}
    for name, raw in sorted(metrics.items()):
        row = _json_mapping(raw, f"{context}.{name}")
        _exact(row, _METRIC_FIELDS, f"{context}.{name}")
        numerator = _finite_float(
            row["numerator"],
            f"{context}.{name}.numerator",
        )
        denominator = _positive_int(
            row["denominator"],
            f"{context}.{name}.denominator",
        )
        value_float = _finite_float(
            row["value"],
            f"{context}.{name}.value",
        )
        if not isclose(
            value_float,
            numerator / denominator,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            _fail("a2_metric_ratio_mismatch", name)
        direction = _text(
            row["direction"],
            f"{context}.{name}.direction",
        )
        if direction not in {"higher", "lower"}:
            _fail("a2_metric_direction_invalid", name)
        tolerance = _finite_float(
            row["tolerance"],
            f"{context}.{name}.tolerance",
        )
        if tolerance < 0.0:
            _fail("a2_metric_tolerance_negative", name)
        result[name] = {
            "numerator": numerator,
            "denominator": denominator,
            "value": value_float,
            "direction": direction,
            "tolerance": tolerance,
        }
    return result


def _metric_non_degraded(
    candidate: Mapping[str, Any],
    r0: Mapping[str, Any],
) -> bool:
    if (
        candidate["direction"] != r0["direction"]
        or candidate["tolerance"] != r0["tolerance"]
    ):
        return False
    if candidate["direction"] == "lower":
        return candidate["value"] <= r0["value"] + candidate["tolerance"]
    return candidate["value"] + candidate["tolerance"] >= r0["value"]


def _load_source(
    reference: Mapping[str, Any],
    *,
    root: Path,
    gate: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        path = _resolve_artifact(reference, root=root)
        evidence = load_learning_run_source_evidence_bytes(
            path.read_bytes(),
            artifact_root=root,
            expected_variant="A2",
            expected_gate=gate,
        )
    except (D4A2PairedShadowAuditError, LearningRunSourceAdapterError) as exc:
        code = exc.code if hasattr(exc, "code") else type(exc).__name__
        return None, [str(code)]
    return evidence, []


def _resolve_artifact(reference: Mapping[str, Any], *, root: Path) -> Path:
    relative = Path(reference["path"])
    if relative.is_absolute() or ".." in relative.parts:
        _fail("a2_paired_artifact_path_escape")
    try:
        path = (root / relative).resolve(strict=True)
        path.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail("a2_paired_artifact_unavailable", str(relative))
    if not path.is_file() or path.is_symlink():
        _fail("a2_paired_artifact_not_regular", str(relative))
    if sha256(path.read_bytes()).hexdigest() != reference["file_sha256"]:
        _fail("a2_paired_artifact_sha256_mismatch", str(relative))
    return path


def _artifact_reference(value: Any, context: str) -> dict[str, str]:
    reference = _json_mapping(value, context)
    _exact(reference, _ARTIFACT_FIELDS, context)
    return {
        "path": _text(reference["path"], f"{context}.path"),
        "file_sha256": _sha256_text(
            reference["file_sha256"],
            f"{context}.file_sha256",
        ),
    }


def _artifact_root(value: str | Path) -> Path:
    try:
        root = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("a2_paired_artifact_root_invalid")
    if not root.is_dir():
        _fail("a2_paired_artifact_root_not_directory")
    return root


def _utc_text(value: Any, context: str) -> str:
    text = _text(value, context)
    _utc(text, context)
    return text


def _utc(value: str, context: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("a2_paired_timestamp_invalid", context)
    if parsed.tzinfo is None:
        _fail("a2_paired_timestamp_timezone_missing", context)
    return parsed


def _json_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("a2_paired_mapping_required", context)
    try:
        normalized = json.loads(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    except (TypeError, ValueError) as exc:
        _fail("a2_paired_json_invalid", f"{context}:{type(exc).__name__}")
    if not isinstance(normalized, dict):
        _fail("a2_paired_mapping_required", context)
    return normalized


def _mapping_sequence(
    value: Any,
    context: str,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        _json_mapping(item, f"{context}.{index}")
        for index, item in enumerate(_sequence(value, context))
    )


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if (
        isinstance(value, (str, bytes, bytearray))
        or not isinstance(value, Sequence)
    ):
        _fail("a2_paired_sequence_required", context)
    return value


def _text_sequence(value: Any, context: str) -> tuple[str, ...]:
    result = tuple(_text(item, context) for item in _sequence(value, context))
    if len(result) != len(set(result)):
        _fail("a2_paired_duplicate_text", context)
    return result


def _integer_sequence(value: Any, context: str) -> tuple[int, ...]:
    return tuple(
        _nonnegative_int(item, context) for item in _sequence(value, context)
    )


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("a2_paired_text_required", context)
    return value.strip()


def _boolean(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        _fail("a2_paired_boolean_required", context)
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("a2_paired_nonnegative_integer_required", context)
    return value


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    if result <= 0:
        _fail("a2_paired_positive_integer_required", context)
    return result


def _finite_float(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("a2_paired_number_required", context)
    result = float(value)
    if not isfinite(result):
        _fail("a2_paired_finite_number_required", context)
    return result


def _sha256_text(value: Any, context: str) -> str:
    text = _text(value, context)
    if len(text) != 64 or any(character not in _HEX64 for character in text):
        _fail("a2_paired_sha256_required", context)
    return text


def _exact(value: Mapping[str, Any], expected: frozenset[str], context: str) -> None:
    if set(value) != set(expected):
        _fail(
            "a2_paired_fields_mismatch",
            f"{context}:{','.join(sorted(set(value) ^ set(expected)))}",
        )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _dedupe(values: Sequence[str] | Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw)
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _fail(code: str, detail: str | None = None) -> None:
    raise D4A2PairedShadowAuditError(code, detail)


__all__ = [
    "D4_A2_CANDIDATE_MANIFEST_SHA256",
    "D4_A2_FROZEN_SEED_REGISTRY_SCHEMA_VERSION",
    "D4_A2_MINIMUM_FORMAL_SEED_COUNT",
    "D4_A2_MODEL_STATE_SHA256",
    "D4_A2_PAIRED_SHADOW_AUDIT_SCHEMA_VERSION",
    "D4_A2_PAIRED_SHADOW_INPUT_SCHEMA_VERSION",
    "D4A2PairedShadowAuditError",
    "audit_d4_a2_paired_shadow",
    "build_d4_a2_paired_shadow_audit_input",
    "validate_d4_a2_paired_shadow_audit_input",
    "write_d4_a2_paired_shadow_audit",
]
