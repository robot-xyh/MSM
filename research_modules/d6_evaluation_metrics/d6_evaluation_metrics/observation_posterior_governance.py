"""Passive audit of scalable-3D D1 posterior generations consumed by D2.

The evaluator reads persisted summary and online-bus records only.  It does
not import runtime modules, consult evaluator truth, or write to the control
path.  Runtime v1 remains explicitly unavailable because it did not publish
the generation evidence needed for this audit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


OBSERVATION_GOVERNANCE_RUNTIME_V1 = (
    "scalable3d-observation-governance-runtime-v1"
)
OBSERVATION_GOVERNANCE_RUNTIME_V2 = (
    "scalable3d-observation-governance-runtime-v2"
)
POSTERIOR_GOVERNANCE_AUDIT_SCHEMA_VERSION = (
    "d6-scalable3d-posterior-governance-audit-v1"
)
MODULE_PERFORMANCE_EVIDENCE_REGISTRY_SCHEMA_VERSION = (
    "d6-module-performance-descriptive-evidence-registry-v1"
)

_D1_TOPIC = "modules.d1.fused_tracks"
_D2_TOPIC = "modules.d2.associated_tracks"
_SUMMARY_COUNT_FIELDS = (
    "d1_posterior_generation",
    "d2_consumed_d1_posterior_generation",
    "d2_posterior_consumption_count",
    "d2_pre_tick_posterior_merge_count",
)


@dataclass(frozen=True)
class PosteriorGovernanceEvidence:
    """Availability-aware row extension and formal failure reasons."""

    metrics: dict[str, Any]
    failure_reasons: tuple[str, ...] = ()


def evaluate_posterior_governance(
    online_records: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any] | None,
    *,
    online_unavailable_reason: str | None = None,
) -> PosteriorGovernanceEvidence:
    """Audit D1 generation publication and D2 single-consumption semantics."""

    metrics: dict[str, Any] = {
        "observation_governance_audit_schema_version": (
            POSTERIOR_GOVERNANCE_AUDIT_SCHEMA_VERSION
        )
    }
    governance = _summary_governance(summary)
    if governance is None:
        reason = "summary_observation_governance_missing"
        _put_unavailable_contract(metrics, reason)
        return PosteriorGovernanceEvidence(metrics=metrics)

    runtime_schema = governance.get("schema_version")
    if runtime_schema is None or not str(runtime_schema).strip():
        _put_unavailable_contract(
            metrics,
            "observation_governance_runtime_schema_missing",
        )
        return PosteriorGovernanceEvidence(metrics=metrics)
    _put_available(metrics, "observation_governance_runtime_schema", str(runtime_schema))

    if runtime_schema == OBSERVATION_GOVERNANCE_RUNTIME_V1:
        _put_unavailable_contract(metrics, "runtime_v1_generation_fields_unavailable")
        return PosteriorGovernanceEvidence(metrics=metrics)
    if runtime_schema != OBSERVATION_GOVERNANCE_RUNTIME_V2:
        reason = f"unsupported_observation_governance_runtime_schema:{runtime_schema}"
        _put_unavailable_contract(metrics, reason)
        return PosteriorGovernanceEvidence(
            metrics=metrics,
            failure_reasons=(f"observation_governance_generation_integrity:{reason}",),
        )

    reasons: list[str] = []
    summary_counts: dict[str, int] = {}
    for field in _SUMMARY_COUNT_FIELDS:
        value = governance.get(field)
        if not _is_nonnegative_int(value):
            reasons.append(f"invalid_summary_count:{field}")
            _put_unavailable(metrics, field, f"invalid_nonnegative_integer:{field}")
            continue
        summary_counts[field] = int(value)
        _put_available(metrics, field, int(value))

    pending_is_empty: bool | None = None
    if "d2_pending_d1_posterior_generation" not in governance:
        reasons.append("pending_generation_field_missing")
        _put_unavailable(
            metrics,
            "d2_pending_generation_empty",
            "d2_pending_d1_posterior_generation_missing",
        )
    else:
        pending = governance.get("d2_pending_d1_posterior_generation")
        pending_is_empty = pending is None
        _put_available(metrics, "d2_pending_generation_empty", pending_is_empty)
        if pending is not None:
            reasons.append("pending_generation_not_drained")

    if online_unavailable_reason is not None:
        reasons.append(f"online_bus_unavailable:{online_unavailable_reason}")
        _put_unavailable(
            metrics,
            "d1_full_posterior_publication_count",
            str(online_unavailable_reason),
        )
        _put_unavailable(
            metrics,
            "d2_association_publication_count",
            str(online_unavailable_reason),
        )
        _put_unavailable(
            metrics,
            "d1_posterior_generation_sequence_json",
            str(online_unavailable_reason),
        )
        _put_unavailable(
            metrics,
            "d2_source_d1_posterior_generation_sequence_json",
            str(online_unavailable_reason),
        )
    else:
        d1_generations, d2_generations, bus_reasons = _audit_bus_generations(
            online_records
        )
        reasons.extend(bus_reasons)
        _put_available(
            metrics,
            "d1_full_posterior_publication_count",
            len(d1_generations),
        )
        _put_available(
            metrics,
            "d2_association_publication_count",
            len(d2_generations),
        )
        _put_available(
            metrics,
            "d1_posterior_generation_sequence_json",
            d1_generations,
        )
        _put_available(
            metrics,
            "d2_source_d1_posterior_generation_sequence_json",
            d2_generations,
        )
        _cross_check_summary_and_bus(
            summary_counts,
            d1_generations,
            d2_generations,
            pending_is_empty=pending_is_empty,
            reasons=reasons,
        )

    reasons = list(dict.fromkeys(reasons))
    _put_available(metrics, "observation_governance_generation_integrity", not reasons)
    _put_available(
        metrics,
        "observation_governance_generation_integrity_reasons_json",
        reasons,
    )
    _put_available(
        metrics,
        "observation_governance_generation_contract_status",
        "verified" if not reasons else "failed_closed",
    )
    failures = tuple(
        f"observation_governance_generation_integrity:{reason}" for reason in reasons
    )
    return PosteriorGovernanceEvidence(metrics=metrics, failure_reasons=failures)


def register_module_performance_evidence(
    paths: Sequence[str | Path],
) -> dict[str, Any]:
    """Register D1/D5 module-only performance JSON as descriptive evidence."""

    records: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path).resolve()
        try:
            payload_bytes = path.read_bytes()
            payload = json.loads(payload_bytes)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot load module performance evidence {path}: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"module performance evidence must be a JSON object: {path}")
        schema_version = payload.get("schema_version")
        if schema_version is None or not str(schema_version).strip():
            raise ValueError(f"module performance evidence schema_version missing: {path}")
        normalized_schema = str(schema_version).strip().lower()
        if normalized_schema.startswith("d1"):
            module = "D1"
        elif normalized_schema.startswith("d5"):
            module = "D5"
        else:
            raise ValueError(
                "only D1/D5 module performance evidence is accepted by this registry: "
                f"{path}"
            )
        records.append(
            {
                "module": module,
                "path": str(path),
                "sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "source_schema_version": str(schema_version),
                "evidence_class": "descriptive_standalone_module_performance",
                "full_stack_realtime_claim": False,
                "control_effect_claim": False,
            }
        )
    return {
        "schema_version": MODULE_PERFORMANCE_EVIDENCE_REGISTRY_SCHEMA_VERSION,
        "evidence_count": len(records),
        "records": records,
        "interpretation": (
            "standalone A/B or replay timing; not full-stack real-time capability"
        ),
    }


def _audit_bus_generations(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[int], list[int], list[str]]:
    d1_generations: list[int] = []
    d2_generations: list[int] = []
    published: set[int] = set()
    reasons: list[str] = []

    for record_index, record in enumerate(records):
        topic = record.get("topic")
        payload = record.get("payload")
        if not isinstance(payload, Mapping):
            if topic in {_D1_TOPIC, _D2_TOPIC}:
                reasons.append(f"invalid_bus_payload:{topic}:{record_index}")
            continue
        if topic == _D1_TOPIC:
            if payload.get("snapshot_kind") != "full_posterior":
                continue
            generation = payload.get("posterior_generation")
            if not _is_positive_int(generation):
                reasons.append(f"invalid_d1_full_posterior_generation:{record_index}")
                continue
            parsed = int(generation)
            expected = len(d1_generations) + 1
            if parsed != expected:
                reasons.append(
                    f"d1_generation_not_contiguous:expected={expected}:actual={parsed}"
                )
            d1_generations.append(parsed)
            published.add(parsed)
        elif topic == _D2_TOPIC:
            generation = payload.get("source_d1_posterior_generation")
            if not _is_positive_int(generation):
                reasons.append(f"invalid_d2_source_generation:{record_index}")
                continue
            parsed = int(generation)
            if d2_generations and parsed <= d2_generations[-1]:
                reasons.append(
                    "d2_source_generation_not_strictly_increasing:"
                    f"previous={d2_generations[-1]}:actual={parsed}"
                )
            if parsed not in published:
                reasons.append(f"d2_source_generation_not_previously_published:{parsed}")
            d2_generations.append(parsed)
    return d1_generations, d2_generations, reasons


def _cross_check_summary_and_bus(
    summary_counts: Mapping[str, int],
    d1_generations: Sequence[int],
    d2_generations: Sequence[int],
    *,
    pending_is_empty: bool | None,
    reasons: list[str],
) -> None:
    d1_final = summary_counts.get("d1_posterior_generation")
    d2_final = summary_counts.get("d2_consumed_d1_posterior_generation")
    consumption_count = summary_counts.get("d2_posterior_consumption_count")
    if d1_final is not None and d1_final != len(d1_generations):
        reasons.append(
            "d1_final_generation_publication_count_mismatch:"
            f"summary={d1_final}:bus={len(d1_generations)}"
        )
    if d2_final is not None and d1_final is not None and d2_final > d1_final:
        reasons.append(
            f"d2_consumed_generation_exceeds_d1:consumed={d2_final}:d1={d1_final}"
        )
    if (
        pending_is_empty is True
        and d2_final is not None
        and d1_final is not None
        and d2_final != d1_final
    ):
        reasons.append(
            "d2_final_consumed_generation_not_equal_d1_when_pending_empty:"
            f"consumed={d2_final}:d1={d1_final}"
        )
    merge_count = summary_counts.get("d2_pre_tick_posterior_merge_count")
    if (
        consumption_count is not None
        and merge_count is not None
        and d1_final is not None
        and consumption_count + merge_count != d1_final
    ):
        reasons.append(
            "d2_consumption_plus_pre_tick_merge_not_equal_d1:"
            f"consumption={consumption_count}:merge={merge_count}:d1={d1_final}"
        )
    expected_final = d2_generations[-1] if d2_generations else 0
    if d2_final is not None and d2_final != expected_final:
        reasons.append(
            "d2_final_consumed_generation_mismatch:"
            f"summary={d2_final}:bus={expected_final}"
        )
    if consumption_count is not None and consumption_count != len(d2_generations):
        reasons.append(
            "d2_consumption_count_publication_count_mismatch:"
            f"summary={consumption_count}:bus={len(d2_generations)}"
        )


def _summary_governance(summary: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(summary, Mapping):
        return None
    diagnostics = summary.get("module_final_diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None
    governance = diagnostics.get("observation_governance")
    return governance if isinstance(governance, Mapping) else None


def _put_unavailable_contract(metrics: dict[str, Any], reason: str) -> None:
    for field in (
        "observation_governance_generation_integrity",
        "observation_governance_generation_contract_status",
        "observation_governance_generation_integrity_reasons_json",
        "d1_posterior_generation",
        "d1_full_posterior_publication_count",
        "d2_consumed_d1_posterior_generation",
        "d2_posterior_consumption_count",
        "d2_association_publication_count",
        "d2_pre_tick_posterior_merge_count",
        "d2_pending_generation_empty",
        "d1_posterior_generation_sequence_json",
        "d2_source_d1_posterior_generation_sequence_json",
    ):
        _put_unavailable(metrics, field, reason)


def _put_available(metrics: dict[str, Any], field: str, value: Any) -> None:
    metrics[field] = value
    metrics[f"{field}_availability"] = "available"
    metrics[f"{field}_unavailable_reason"] = None


def _put_unavailable(metrics: dict[str, Any], field: str, reason: str) -> None:
    metrics[field] = None
    metrics[f"{field}_availability"] = "unavailable"
    metrics[f"{field}_unavailable_reason"] = str(reason)


def _is_positive_int(value: Any) -> bool:
    return _is_nonnegative_int(value) and int(value) > 0


def _is_nonnegative_int(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return value.is_integer() and value >= 0.0
    return False


__all__ = [
    "MODULE_PERFORMANCE_EVIDENCE_REGISTRY_SCHEMA_VERSION",
    "OBSERVATION_GOVERNANCE_RUNTIME_V1",
    "OBSERVATION_GOVERNANCE_RUNTIME_V2",
    "POSTERIOR_GOVERNANCE_AUDIT_SCHEMA_VERSION",
    "PosteriorGovernanceEvidence",
    "evaluate_posterior_governance",
    "register_module_performance_evidence",
]
