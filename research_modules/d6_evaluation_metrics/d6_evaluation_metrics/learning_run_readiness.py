"""Read-only readiness audit for formal scalable learning runs.

The audit aggregates already produced evidence summaries. It does not execute
an episode, load a policy into a controller, grant authority, or manufacture
missing runtime evidence. Model/evidence readiness is kept separate from
external permission and storage availability.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any

from .learning_run_source_adapters import (
    LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS,
    LearningRunSourceAdapterError,
    load_learning_run_source_evidence_bytes,
)

LEARNING_RUN_READINESS_INPUT_SCHEMA_VERSION = (
    "d6.learning-run-readiness-input.v2"
)
LEARNING_RUN_READINESS_SCHEMA_VERSION = "d6.learning-run-readiness-audit.v2"
LEARNING_RUN_READINESS_CONSUMER_SCHEMA_VERSION = (
    "d6.learning-run-readiness-consumer.v2"
)
LEARNING_RUN_READINESS_SCOPE = "read-only-evaluation-no-runtime-authority"
FORMAL_RUNTIME_MINIMUM_FREE_BYTES = 20 * 1024**3
FORMAL_RUNTIME_MINIMUM_FREE_GIB = 20.0
MINIMUM_FORMAL_UNSEEN_SEED_COUNT = 20

LEARNING_VARIANTS = ("G1", "A1", "A2", "A3", "C1", "F1")
READINESS_GATES = (
    "model_source",
    "frozen_unseen_seeds",
    "identifiable_adoption",
    "runtime_ack",
    "physical_window",
    "same_key_r0",
    "paired_non_degradation",
    "truth_use",
    "finite_state",
    "external_permission",
)
MODEL_GATES = ("model_source", "frozen_unseen_seeds")
RUNTIME_EVIDENCE_GATES = (
    "identifiable_adoption",
    "runtime_ack",
    "physical_window",
    "same_key_r0",
    "paired_non_degradation",
    "truth_use",
    "finite_state",
)

_REQUIRED_COMPONENTS = {
    "G1": frozenset({"d5_graph"}),
    "A1": frozenset({"d3"}),
    "A2": frozenset({"d4"}),
    "A3": frozenset({"d5_active_vision"}),
    "C1": frozenset({"d3", "d4", "d5_graph", "d5_active_vision"}),
    "F1": frozenset({"d3", "d4", "d5_graph", "d5_active_vision"}),
}
_EXPECTED_SOURCE_CLASS = {
    "model_source": frozenset(
        {
            "formal_external_audit",
            "formal_post_assembly_audit",
            "composite_formal_external_audits",
        }
    ),
    "frozen_unseen_seeds": frozenset({"frozen_seed_registry"}),
    "identifiable_adoption": frozenset(
        {"persisted_formal_runtime_adoption"}
    ),
    "runtime_ack": frozenset({"persisted_formal_runtime_ack"}),
    "physical_window": frozenset({"persisted_formal_physical_window"}),
    "same_key_r0": frozenset({"persisted_unique_same_key_r0"}),
    "paired_non_degradation": frozenset(
        {"formal_paired_runtime_non_degradation"}
    ),
    "truth_use": frozenset({"formal_truth_use_audit"}),
    "finite_state": frozenset({"formal_finite_state_audit"}),
    "external_permission": frozenset({"external_authority_decision"}),
}
_SOURCE_CLASS_REJECTION_CODES = {
    "development_20_seed_batch": (
        "development_20_seed_batch_not_formal_evidence"
    ),
    "development_external_audit": (
        "development_external_audit_not_formal_evidence"
    ),
    "developer_summary": "developer_summary_not_formal_evidence",
    "software_contract_fixture": (
        "software_contract_fixture_not_formal_evidence"
    ),
    "zero_drop_control": (
        "zero_drop_control_not_formal_non_degradation_evidence"
    ),
}
_GATE_FACT_FIELDS = {
    "model_source": frozenset(
        {"component_ids", "audit_passed", "model_identity"}
    ),
    "frozen_unseen_seeds": frozenset(
        {"evaluation_seed_count", "training_overlap_count", "frozen"}
    ),
    "identifiable_adoption": frozenset(
        {
            "actual_adoption_count",
            "identifiable_change_count",
            "binding_change_count",
            "no_op_count",
            "adopted_component_ids",
        }
    ),
    "runtime_ack": frozenset(
        {"required_ack_count", "matched_ack_count", "acked_component_ids"}
    ),
    "physical_window": frozenset(
        {"candidate_window_count", "confirmed_window_count"}
    ),
    "same_key_r0": frozenset(
        {
            "candidate_count",
            "pair_count",
            "unique_pair_count",
            "same_key_pair_count",
        }
    ),
    "paired_non_degradation": frozenset(
        {
            "pair_count",
            "evaluated_pair_count",
            "non_degraded_pair_count",
            "required_metric_count",
            "available_metric_count",
        }
    ),
    "truth_use": frozenset(
        {"audited_record_count", "online_truth_use_count"}
    ),
    "finite_state": frozenset(
        {"audited_value_count", "nonfinite_value_count"}
    ),
    "external_permission": frozenset({"granted", "authority", "scope"}),
}
_INPUT_FIELDS = frozenset(
    {"schema_version", "audit_id", "variants", "storage", "content_sha256"}
)
_VARIANT_FIELDS = frozenset({"variant", "gates"})
_GATE_FIELDS = frozenset(
    {"availability", "source_artifact", "reason_codes"}
)
_SOURCE_ARTIFACT_FIELDS = frozenset({"path", "file_sha256"})
_STORAGE_FIELDS = frozenset(
    {
        "availability",
        "source_class",
        "observed_at_utc",
        "mounts",
        "reason_codes",
    }
)
_MOUNT_FIELDS = frozenset(
    {"path", "available_bytes", "eligible_for_formal_output"}
)
_OUTPUT_FIELDS = frozenset(
    {
        "schema_version",
        "consumer_schema_version",
        "input_schema_version",
        "input_content_sha256",
        "audit_id",
        "scope",
        "variants",
        "storage",
        "aggregate",
        "permissions",
        "content_sha256",
    }
)
_OUTPUT_VARIANT_FIELDS = frozenset(
    {
        "variant",
        "required_components",
        "gates",
        "model_readiness",
        "runtime_evidence_readiness",
        "formal_evidence_readiness",
        "execution_startability",
        "blocker_codes",
        "d6_authority_generated",
    }
)
_OUTPUT_GATE_FIELDS = frozenset(
    {"availability", "passed", "source", "facts", "reason_codes"}
)
_OUTPUT_GATE_SOURCE_FIELDS = frozenset(
    {
        "artifact_path",
        "declared_file_sha256",
        "actual_file_sha256",
        "source_class",
        "source_schema_version",
        "source_content_sha256",
        "formal",
        "verified",
    }
)
_OUTPUT_SUMMARY_FIELDS = frozenset(
    {"availability", "ready", "fail_closed", "reason_codes"}
)
_OUTPUT_EXECUTION_FIELDS = frozenset(
    {"availability", "startable", "fail_closed", "reason_codes"}
)
_OUTPUT_STORAGE_FIELDS = frozenset(
    {
        "availability",
        "passed",
        "minimum_free_bytes",
        "minimum_free_gib",
        "source_class",
        "observed_at_utc",
        "mounts",
        "best_available_bytes",
        "best_available_gib",
        "reason_codes",
    }
)
_OUTPUT_AGGREGATE_FIELDS = frozenset(
    {
        "variant_count",
        "model_ready_variant_count",
        "runtime_evidence_ready_variant_count",
        "formal_evidence_ready_variant_count",
        "execution_startable_variant_count",
        "all_variants_execution_startable",
        "formal_large_run_started",
        "disk_changes_model_readiness",
    }
)
_OUTPUT_PERMISSION_FIELDS = frozenset(
    {
        "d6_generated_authority",
        "model_promotion_authority",
        "assignment_authority",
        "failover_authority",
        "camera_command_authority",
        "control_authority",
    }
)
_HEX64 = frozenset("0123456789abcdef")


class LearningRunReadinessError(ValueError):
    """Stable failure for malformed readiness manifests or audit output."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = str(code)
        self.detail = None if detail is None else str(detail)
        message = self.code if self.detail is None else f"{self.code}: {self.detail}"
        super().__init__(message)


def build_learning_run_readiness_input(
    *,
    audit_id: str,
    variants: Mapping[str, Mapping[str, Any]],
    storage: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one content-addressed readiness request."""

    payload: dict[str, Any] = {
        "schema_version": LEARNING_RUN_READINESS_INPUT_SCHEMA_VERSION,
        "audit_id": _text(audit_id, "audit_id"),
        "variants": _json_mapping(variants, "variants"),
        "storage": _json_mapping(storage, "storage"),
    }
    _assert_finite(payload)
    payload["content_sha256"] = _canonical_sha256(payload)
    return validate_learning_run_readiness_input(payload)


def validate_learning_run_readiness_input(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact input fields and normalize JSON-compatible values."""

    payload = _json_mapping(value, "readiness_input")
    _expect_exact_fields(payload, _INPUT_FIELDS, "readiness_input")
    if (
        payload["schema_version"]
        != LEARNING_RUN_READINESS_INPUT_SCHEMA_VERSION
    ):
        _fail("readiness_input_schema_unsupported")

    variants = _mapping(payload["variants"], "variants")
    if set(variants) != set(LEARNING_VARIANTS):
        _fail(
            "readiness_input_variants_mismatch",
            ",".join(sorted(set(variants) ^ set(LEARNING_VARIANTS))),
        )
    normalized_variants = {
        variant: _validate_variant_input(variant, variants[variant])
        for variant in LEARNING_VARIANTS
    }
    normalized_storage = _validate_storage_input(payload["storage"])
    normalized: dict[str, Any] = {
        "schema_version": payload["schema_version"],
        "audit_id": _text(payload["audit_id"], "audit_id"),
        "variants": normalized_variants,
        "storage": normalized_storage,
    }
    claimed = _sha256_text(payload["content_sha256"], "content_sha256")
    if _canonical_sha256(normalized) != claimed:
        _fail("readiness_input_content_sha256_mismatch")
    normalized["content_sha256"] = claimed
    _assert_finite(normalized)
    return normalized


def load_learning_run_readiness_input(path: str | Path) -> dict[str, Any]:
    """Load one explicit readiness manifest without directory discovery."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("readiness_input_file_invalid", type(exc).__name__)
    if not isinstance(payload, Mapping):
        _fail("readiness_input_type_invalid")
    return validate_learning_run_readiness_input(payload)


def audit_learning_run_readiness(
    value: Mapping[str, Any],
    *,
    artifact_root: str | Path | None,
) -> dict[str, Any]:
    """Aggregate file-bound evidence without producing authorization.

    ``artifact_root`` is an explicit read-only boundary. Every available gate
    must reference a regular file below this directory.
    """

    payload = validate_learning_run_readiness_input(value)
    resolved_root, root_reason = _resolve_artifact_root(artifact_root)
    storage = _audit_storage(payload["storage"])
    variants = {
        variant: _audit_variant(
            variant,
            payload["variants"][variant],
            storage=storage,
            artifact_root=resolved_root,
            artifact_root_reason=root_reason,
        )
        for variant in LEARNING_VARIANTS
    }
    result: dict[str, Any] = {
        "schema_version": LEARNING_RUN_READINESS_SCHEMA_VERSION,
        "consumer_schema_version": (
            LEARNING_RUN_READINESS_CONSUMER_SCHEMA_VERSION
        ),
        "input_schema_version": payload["schema_version"],
        "input_content_sha256": payload["content_sha256"],
        "audit_id": payload["audit_id"],
        "scope": LEARNING_RUN_READINESS_SCOPE,
        "variants": variants,
        "storage": storage,
        "aggregate": _build_aggregate(variants),
        "permissions": {
            "d6_generated_authority": False,
            "model_promotion_authority": False,
            "assignment_authority": False,
            "failover_authority": False,
            "camera_command_authority": False,
            "control_authority": False,
        },
    }
    result["content_sha256"] = _canonical_sha256(result)
    return validate_learning_run_readiness_output(result)


def validate_learning_run_readiness_output(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Strictly reload one current readiness audit result."""

    payload = _json_mapping(value, "readiness_output")
    _expect_exact_fields(payload, _OUTPUT_FIELDS, "readiness_output")
    if payload["schema_version"] != LEARNING_RUN_READINESS_SCHEMA_VERSION:
        _fail("readiness_output_schema_unsupported")
    if (
        payload["consumer_schema_version"]
        != LEARNING_RUN_READINESS_CONSUMER_SCHEMA_VERSION
    ):
        _fail("readiness_output_consumer_schema_unsupported")
    if (
        payload["input_schema_version"]
        != LEARNING_RUN_READINESS_INPUT_SCHEMA_VERSION
    ):
        _fail("readiness_output_input_schema_unsupported")
    _sha256_text(payload["input_content_sha256"], "input_content_sha256")
    if payload["scope"] != LEARNING_RUN_READINESS_SCOPE:
        _fail("readiness_output_scope_invalid")
    variants = _mapping(payload["variants"], "readiness_output.variants")
    if set(variants) != set(LEARNING_VARIANTS):
        _fail("readiness_output_variants_mismatch")
    for variant in LEARNING_VARIANTS:
        row = _mapping(variants[variant], f"readiness_output.{variant}")
        _expect_exact_fields(
            row,
            _OUTPUT_VARIANT_FIELDS,
            f"readiness_output.{variant}",
        )
        if row.get("variant") != variant:
            _fail("readiness_output_variant_identity_mismatch", variant)
        required_components = _text_sequence(
            row.get("required_components"),
            f"readiness_output.{variant}.required_components",
        )
        if set(required_components) != set(_REQUIRED_COMPONENTS[variant]):
            _fail(
                "readiness_output_required_components_mismatch",
                variant,
            )
        gates = _mapping(row.get("gates"), f"readiness_output.{variant}.gates")
        if set(gates) != set(READINESS_GATES):
            _fail("readiness_output_gate_set_mismatch", variant)
        for gate_name, gate_value in gates.items():
            gate = _mapping(
                gate_value,
                f"readiness_output.{variant}.{gate_name}",
            )
            _expect_exact_fields(
                gate,
                _OUTPUT_GATE_FIELDS,
                f"readiness_output.{variant}.{gate_name}",
            )
            if not isinstance(gate.get("availability"), bool):
                _fail("readiness_output_gate_availability_invalid")
            passed = gate.get("passed")
            if passed is not None and not isinstance(passed, bool):
                _fail("readiness_output_gate_passed_invalid")
            if gate["availability"] is False and passed is not None:
                _fail("readiness_output_unavailable_gate_has_result")
            reasons = _text_sequence(
                gate.get("reason_codes"),
                f"readiness_output.{variant}.{gate_name}.reason_codes",
            )
            if list(reasons) != gate.get("reason_codes"):
                _fail("readiness_output_gate_reason_order_invalid")
            source = _mapping(
                gate.get("source"),
                f"readiness_output.{variant}.{gate_name}.source",
            )
            _expect_exact_fields(
                source,
                _OUTPUT_GATE_SOURCE_FIELDS,
                f"readiness_output.{variant}.{gate_name}.source",
            )
            facts = _mapping(
                gate.get("facts"),
                f"readiness_output.{variant}.{gate_name}.facts",
            )
            if gate["availability"]:
                _expect_exact_fields(
                    facts,
                    _GATE_FACT_FIELDS[gate_name],
                    f"readiness_output.{variant}.{gate_name}.facts",
                )
            elif facts:
                _fail("readiness_output_unavailable_gate_has_facts")
            _validate_output_gate_semantics(
                variant,
                gate_name,
                gate,
                context=f"readiness_output.{variant}.{gate_name}",
            )

        for summary_name in (
            "model_readiness",
            "runtime_evidence_readiness",
            "formal_evidence_readiness",
        ):
            summary = _mapping(
                row[summary_name],
                f"readiness_output.{variant}.{summary_name}",
            )
            _expect_exact_fields(
                summary,
                _OUTPUT_SUMMARY_FIELDS,
                f"readiness_output.{variant}.{summary_name}",
            )
            _validate_output_summary(
                summary,
                result_field="ready",
                context=f"readiness_output.{variant}.{summary_name}",
            )
        execution = _mapping(
            row["execution_startability"],
            f"readiness_output.{variant}.execution_startability",
        )
        _expect_exact_fields(
            execution,
            _OUTPUT_EXECUTION_FIELDS,
            f"readiness_output.{variant}.execution_startability",
        )
        _validate_output_summary(
            execution,
            result_field="startable",
            context=f"readiness_output.{variant}.execution_startability",
        )
        blocker_codes = _text_sequence(
            row["blocker_codes"],
            f"readiness_output.{variant}.blocker_codes",
        )
        if list(blocker_codes) != row["blocker_codes"]:
            _fail("readiness_output_blocker_order_invalid")
        if row["d6_authority_generated"] is not False:
            _fail("readiness_output_authority_escalation_attempt")

    storage = _mapping(payload["storage"], "readiness_output.storage")
    _expect_exact_fields(
        storage,
        _OUTPUT_STORAGE_FIELDS,
        "readiness_output.storage",
    )
    if storage.get("minimum_free_bytes") != FORMAL_RUNTIME_MINIMUM_FREE_BYTES:
        _fail("readiness_output_storage_threshold_changed")
    if storage.get("minimum_free_gib") != FORMAL_RUNTIME_MINIMUM_FREE_GIB:
        _fail("readiness_output_storage_threshold_changed")
    if not isinstance(storage.get("availability"), bool):
        _fail("readiness_output_storage_availability_invalid")
    storage_passed = storage.get("passed")
    if storage_passed is not None and not isinstance(storage_passed, bool):
        _fail("readiness_output_storage_passed_invalid")
    if not storage["availability"] and storage_passed is not None:
        _fail("readiness_output_unavailable_storage_has_result")
    storage_reasons = _text_sequence(
        storage.get("reason_codes"),
        "readiness_output.storage.reason_codes",
    )
    if list(storage_reasons) != storage.get("reason_codes"):
        _fail("readiness_output_storage_reason_order_invalid")
    mounts = storage.get("mounts")
    if (
        isinstance(mounts, (str, bytes, bytearray))
        or not isinstance(mounts, Sequence)
    ):
        _fail("readiness_output_storage_mounts_invalid")
    for index, raw_mount in enumerate(mounts):
        mount = _mapping(
            raw_mount,
            f"readiness_output.storage.mounts.{index}",
        )
        _expect_exact_fields(
            mount,
            _MOUNT_FIELDS,
            f"readiness_output.storage.mounts.{index}",
        )
    _validate_output_storage_semantics(storage)
    for variant in LEARNING_VARIANTS:
        _validate_output_variant_semantics(
            variant,
            _mapping(
                variants[variant],
                f"readiness_output.{variant}",
            ),
            storage,
        )
    aggregate = _mapping(
        payload["aggregate"], "readiness_output.aggregate"
    )
    _expect_exact_fields(
        aggregate,
        _OUTPUT_AGGREGATE_FIELDS,
        "readiness_output.aggregate",
    )
    if aggregate["variant_count"] != len(LEARNING_VARIANTS):
        _fail("readiness_output_variant_count_mismatch")
    for name in (
        "model_ready_variant_count",
        "runtime_evidence_ready_variant_count",
        "formal_evidence_ready_variant_count",
        "execution_startable_variant_count",
    ):
        count = _nonnegative_int(
            aggregate[name],
            f"readiness_output.aggregate.{name}",
        )
        if count > len(LEARNING_VARIANTS):
            _fail("readiness_output_aggregate_count_invalid", name)
    for name in (
        "all_variants_execution_startable",
        "formal_large_run_started",
        "disk_changes_model_readiness",
    ):
        _strict_bool(
            aggregate[name],
            f"readiness_output.aggregate.{name}",
        )
    if aggregate["formal_large_run_started"] is not False:
        _fail("readiness_output_claims_run_started")
    if aggregate["disk_changes_model_readiness"] is not False:
        _fail("readiness_output_disk_model_conclusion_coupled")
    if dict(aggregate) != _build_aggregate(variants):
        _fail("readiness_output_aggregate_semantics_mismatch")
    permissions = _mapping(
        payload["permissions"], "readiness_output.permissions"
    )
    _expect_exact_fields(
        permissions,
        _OUTPUT_PERMISSION_FIELDS,
        "readiness_output.permissions",
    )
    if any(item is not False for item in permissions.values()):
        _fail("readiness_output_authority_escalation_attempt")
    claimed = _sha256_text(payload["content_sha256"], "content_sha256")
    body = dict(payload)
    body.pop("content_sha256")
    if _canonical_sha256(body) != claimed:
        _fail("readiness_output_content_sha256_mismatch")
    _assert_finite(payload)
    return payload


def load_learning_run_readiness_output(path: str | Path) -> dict[str, Any]:
    """Load one current readiness result without adjacent-file discovery."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("readiness_output_file_invalid", type(exc).__name__)
    if not isinstance(payload, Mapping):
        _fail("readiness_output_type_invalid")
    return validate_learning_run_readiness_output(payload)


def write_learning_run_readiness_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write a small JSON/Markdown/checksum readiness bundle."""

    payload = validate_learning_run_readiness_output(result)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "learning_run_readiness.json"
    markdown_path = output / "LEARNING_RUN_READINESS_CN.md"
    checksum_path = output / "SHA256SUMS"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_learning_run_readiness_markdown(payload),
        encoding="utf-8",
    )
    checksum_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in sorted((json_path, markdown_path), key=lambda item: item.name)
        ),
        encoding="utf-8",
    )
    return {
        "json": json_path,
        "markdown": markdown_path,
        "checksums": checksum_path,
    }


def render_learning_run_readiness_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render a compact Chinese readiness report."""

    payload = validate_learning_run_readiness_output(result)
    storage = payload["storage"]
    lines = [
        "# 学习变体正式运行准备度审计",
        "",
        "## 结论",
        "",
        (
            f"本次审计覆盖 {len(LEARNING_VARIANTS)} 个学习变体。模型证据就绪 "
            f"{payload['aggregate']['model_ready_variant_count']} 个，完整正式证据就绪 "
            f"{payload['aggregate']['formal_evidence_ready_variant_count']} 个，执行前提满足 "
            f"{payload['aggregate']['execution_startable_variant_count']} 个。"
        ),
        (
            "D6 只汇总证据，不授予模型、分配、降级、相机或控制权限，也没有启动正式实验。"
        ),
        "",
        "## 变体",
        "",
        "| 变体 | 模型 | 运行证据 | 正式证据 | 外部权限 | 可启动 | 主要阻断 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for variant in LEARNING_VARIANTS:
        row = payload["variants"][variant]
        blockers = row["blocker_codes"]
        lines.append(
            "| {variant} | {model} | {runtime} | {formal} | {permission} | "
            "{startable} | `{blockers}` |".format(
                variant=variant,
                model=_summary_text(row["model_readiness"], "ready"),
                runtime=_summary_text(
                    row["runtime_evidence_readiness"], "ready"
                ),
                formal=_summary_text(row["formal_evidence_readiness"], "ready"),
                permission=_gate_text(row["gates"]["external_permission"]),
                startable=_summary_text(
                    row["execution_startability"], "startable"
                ),
                blockers=";".join(blockers) if blockers else "none",
            )
        )
    best_gib = storage.get("best_available_gib")
    lines.extend(
        [
            "",
            "## 存储",
            "",
            f"- 固定保护线：{FORMAL_RUNTIME_MINIMUM_FREE_GIB:.0f} GiB。",
            (
                "- 当前最佳可用容量："
                f"{best_gib:.3f} GiB。"
                if isinstance(best_gib, (int, float))
                else "- 当前最佳可用容量：不可用。"
            ),
            f"- 执行资源门：{_gate_text(storage)}。",
            (
                "- 原因：`"
                + ";".join(storage.get("reason_codes", ()))
                + "`。"
            ),
            "",
            "## 判定边界",
            "",
            "- 20 个开发 seed 只有数量，不构成冻结未见 seed 证据。",
            "- 软件合同夹具只能验证接口，不能替代实际采用、运行确认或物理窗口。",
            "- 零丢包对照只能定位通信损失，不能替代正式成对非退化证据。",
            "- 磁盘不足只阻断执行，不改变模型和算法证据结论。",
            "- 所有缺项均保持 availability=false，并保留稳定原因码。",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_variant_input(
    variant: str,
    value: Any,
) -> dict[str, Any]:
    row = _mapping(value, f"variants.{variant}")
    _expect_exact_fields(row, _VARIANT_FIELDS, f"variants.{variant}")
    if row["variant"] != variant:
        _fail("readiness_input_variant_identity_mismatch", variant)
    gates = _mapping(row["gates"], f"variants.{variant}.gates")
    if set(gates) != set(READINESS_GATES):
        _fail(
            "readiness_input_gate_set_mismatch",
            f"{variant}:{','.join(sorted(set(gates) ^ set(READINESS_GATES)))}",
        )
    return {
        "variant": variant,
        "gates": {
            gate: _validate_gate_input(
                gate,
                gates[gate],
                context=f"variants.{variant}.gates.{gate}",
            )
            for gate in READINESS_GATES
        },
    }


def _validate_gate_input(
    gate_name: str,
    value: Any,
    *,
    context: str,
) -> dict[str, Any]:
    gate = _mapping(value, context)
    _expect_exact_fields(gate, _GATE_FIELDS, context)
    availability = _strict_bool(gate["availability"], f"{context}.availability")
    reason_codes = list(
        _text_sequence(gate["reason_codes"], f"{context}.reason_codes")
    )
    if len(reason_codes) != len(set(reason_codes)):
        _fail("readiness_input_duplicate_reason_code", context)
    if not availability:
        if gate["source_artifact"] is not None:
            _fail(
                "readiness_input_unavailable_gate_has_source_artifact",
                context,
            )
        if not reason_codes:
            _fail("readiness_input_unavailable_gate_reason_missing", context)
        return {
            "availability": False,
            "source_artifact": None,
            "reason_codes": reason_codes,
        }

    artifact = _mapping(
        gate["source_artifact"],
        f"{context}.source_artifact",
    )
    _expect_exact_fields(
        artifact,
        _SOURCE_ARTIFACT_FIELDS,
        f"{context}.source_artifact",
    )
    return {
        "availability": True,
        "source_artifact": {
            "path": _text(
                artifact["path"],
                f"{context}.source_artifact.path",
            ),
            "file_sha256": _sha256_text(
                artifact["file_sha256"],
                f"{context}.source_artifact.file_sha256",
            ),
        },
        "reason_codes": reason_codes,
    }


def _validate_gate_facts(
    gate_name: str,
    facts: Mapping[str, Any],
    *,
    context: str,
) -> dict[str, Any]:
    if gate_name == "model_source":
        return {
            "component_ids": list(
                _text_sequence(
                    facts["component_ids"], f"{context}.component_ids"
                )
            ),
            "audit_passed": _strict_bool(
                facts["audit_passed"], f"{context}.audit_passed"
            ),
            "model_identity": _text(
                facts["model_identity"], f"{context}.model_identity"
            ),
        }
    if gate_name == "frozen_unseen_seeds":
        return {
            "evaluation_seed_count": _nonnegative_int(
                facts["evaluation_seed_count"],
                f"{context}.evaluation_seed_count",
            ),
            "training_overlap_count": _nonnegative_int(
                facts["training_overlap_count"],
                f"{context}.training_overlap_count",
            ),
            "frozen": _strict_bool(facts["frozen"], f"{context}.frozen"),
        }
    if gate_name == "identifiable_adoption":
        return {
            name: _nonnegative_int(facts[name], f"{context}.{name}")
            for name in (
                "actual_adoption_count",
                "identifiable_change_count",
                "binding_change_count",
                "no_op_count",
            )
        } | {
            "adopted_component_ids": list(
                _text_sequence(
                    facts["adopted_component_ids"],
                    f"{context}.adopted_component_ids",
                )
            )
        }
    if gate_name == "runtime_ack":
        return {
            "required_ack_count": _nonnegative_int(
                facts["required_ack_count"],
                f"{context}.required_ack_count",
            ),
            "matched_ack_count": _nonnegative_int(
                facts["matched_ack_count"],
                f"{context}.matched_ack_count",
            ),
            "acked_component_ids": list(
                _text_sequence(
                    facts["acked_component_ids"],
                    f"{context}.acked_component_ids",
                )
            ),
        }
    if gate_name == "physical_window":
        return {
            name: _nonnegative_int(facts[name], f"{context}.{name}")
            for name in ("candidate_window_count", "confirmed_window_count")
        }
    if gate_name == "same_key_r0":
        return {
            name: _nonnegative_int(facts[name], f"{context}.{name}")
            for name in (
                "candidate_count",
                "pair_count",
                "unique_pair_count",
                "same_key_pair_count",
            )
        }
    if gate_name == "paired_non_degradation":
        return {
            name: _nonnegative_int(facts[name], f"{context}.{name}")
            for name in (
                "pair_count",
                "evaluated_pair_count",
                "non_degraded_pair_count",
                "required_metric_count",
                "available_metric_count",
            )
        }
    if gate_name == "truth_use":
        return {
            name: _nonnegative_int(facts[name], f"{context}.{name}")
            for name in ("audited_record_count", "online_truth_use_count")
        }
    if gate_name == "finite_state":
        return {
            name: _nonnegative_int(facts[name], f"{context}.{name}")
            for name in ("audited_value_count", "nonfinite_value_count")
        }
    if gate_name == "external_permission":
        return {
            "granted": _strict_bool(
                facts["granted"], f"{context}.granted"
            ),
            "authority": _text(
                facts["authority"], f"{context}.authority"
            ),
            "scope": _text(facts["scope"], f"{context}.scope"),
        }
    _fail("readiness_input_gate_unknown", gate_name)


def _validate_storage_input(value: Any) -> dict[str, Any]:
    storage = _mapping(value, "storage")
    _expect_exact_fields(storage, _STORAGE_FIELDS, "storage")
    availability = _strict_bool(
        storage["availability"], "storage.availability"
    )
    reasons = list(
        _text_sequence(storage["reason_codes"], "storage.reason_codes")
    )
    if len(reasons) != len(set(reasons)):
        _fail("readiness_input_duplicate_reason_code", "storage")
    raw_mounts = storage["mounts"]
    if (
        isinstance(raw_mounts, (str, bytes, bytearray))
        or not isinstance(raw_mounts, Sequence)
    ):
        _fail("readiness_input_storage_mounts_invalid")
    mounts: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_mounts):
        mount = _mapping(raw, f"storage.mounts.{index}")
        _expect_exact_fields(
            mount,
            _MOUNT_FIELDS,
            f"storage.mounts.{index}",
        )
        mounts.append(
            {
                "path": _text(
                    mount["path"], f"storage.mounts.{index}.path"
                ),
                "available_bytes": _nonnegative_int(
                    mount["available_bytes"],
                    f"storage.mounts.{index}.available_bytes",
                ),
                "eligible_for_formal_output": _strict_bool(
                    mount["eligible_for_formal_output"],
                    (
                        "storage.mounts."
                        f"{index}.eligible_for_formal_output"
                    ),
                ),
            }
        )
    if not availability:
        if storage["source_class"] is not None:
            _fail("readiness_input_unavailable_storage_has_source")
        if storage["observed_at_utc"] is not None:
            _fail("readiness_input_unavailable_storage_has_timestamp")
        if mounts:
            _fail("readiness_input_unavailable_storage_has_mounts")
        if not reasons:
            _fail("readiness_input_unavailable_storage_reason_missing")
        return {
            "availability": False,
            "source_class": None,
            "observed_at_utc": None,
            "mounts": [],
            "reason_codes": reasons,
        }
    return {
        "availability": True,
        "source_class": _text(
            storage["source_class"], "storage.source_class"
        ),
        "observed_at_utc": _text(
            storage["observed_at_utc"], "storage.observed_at_utc"
        ),
        "mounts": mounts,
        "reason_codes": reasons,
    }


def _audit_variant(
    variant: str,
    row: Mapping[str, Any],
    *,
    storage: Mapping[str, Any],
    artifact_root: Path | None,
    artifact_root_reason: str | None,
) -> dict[str, Any]:
    gates = {
        gate_name: _audit_gate(
            variant,
            gate_name,
            row["gates"][gate_name],
            artifact_root=artifact_root,
            artifact_root_reason=artifact_root_reason,
        )
        for gate_name in READINESS_GATES
    }
    model = _summarize_gates(gates, MODEL_GATES)
    runtime = _summarize_gates(gates, RUNTIME_EVIDENCE_GATES)
    formal = _summarize_gates(
        gates,
        (*MODEL_GATES, *RUNTIME_EVIDENCE_GATES),
    )
    execution_gate_names = (
        *MODEL_GATES,
        *RUNTIME_EVIDENCE_GATES,
        "external_permission",
    )
    execution = _summarize_execution(
        gates,
        storage,
        gate_names=execution_gate_names,
    )
    blocker_codes = _variant_blocker_codes(gates, storage)
    return {
        "variant": variant,
        "required_components": sorted(_REQUIRED_COMPONENTS[variant]),
        "gates": gates,
        "model_readiness": model,
        "runtime_evidence_readiness": runtime,
        "formal_evidence_readiness": formal,
        "execution_startability": execution,
        "blocker_codes": blocker_codes,
        "d6_authority_generated": False,
    }


def _audit_gate(
    variant: str,
    gate_name: str,
    evidence: Mapping[str, Any],
    *,
    artifact_root: Path | None,
    artifact_root_reason: str | None,
) -> dict[str, Any]:
    if not evidence["availability"]:
        reasons = _dedupe(
            [
                *evidence["reason_codes"],
                _unavailable_reason(variant, gate_name),
            ]
        )
        return {
            "availability": False,
            "passed": None,
            "source": {
                "artifact_path": None,
                "declared_file_sha256": None,
                "actual_file_sha256": None,
                "source_class": None,
                "source_schema_version": None,
                "source_content_sha256": None,
                "formal": None,
                "verified": None,
            },
            "facts": {},
            "reason_codes": reasons,
        }

    loaded = _load_bound_gate_source(
        variant,
        gate_name,
        evidence["source_artifact"],
        artifact_root=artifact_root,
        artifact_root_reason=artifact_root_reason,
    )
    if loaded["evidence"] is None:
        reasons = _dedupe(
            [
                *evidence["reason_codes"],
                *loaded["reason_codes"],
                _unavailable_reason(variant, gate_name),
            ]
        )
        return {
            "availability": False,
            "passed": None,
            "source": loaded["source"],
            "facts": {},
            "reason_codes": reasons,
        }

    verified_evidence = loaded["evidence"]
    reasons = list(evidence["reason_codes"])
    source_class = verified_evidence["source_class"]
    if source_class not in _EXPECTED_SOURCE_CLASS[gate_name]:
        reasons.append(
            _SOURCE_CLASS_REJECTION_CODES.get(
                source_class,
                f"{variant.lower()}_{gate_name}_source_class_not_accepted",
            )
        )
    if verified_evidence["formal"] is not True:
        reasons.append(f"{variant.lower()}_{gate_name}_not_formal")
    reasons.extend(
        _fact_blockers(
            variant,
            gate_name,
            verified_evidence["facts"],
        )
    )
    normalized = _dedupe(reasons)
    return {
        "availability": True,
        "passed": not normalized,
        "source": loaded["source"],
        "facts": dict(verified_evidence["facts"]),
        "reason_codes": normalized,
    }


def _resolve_artifact_root(
    value: str | Path | None,
) -> tuple[Path | None, str | None]:
    if value is None:
        return None, "learning_run_artifact_root_unavailable"
    try:
        root = Path(value).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "learning_run_artifact_root_invalid"
    if not root.is_dir():
        return None, "learning_run_artifact_root_not_directory"
    return root, None


def _load_bound_gate_source(
    variant: str,
    gate_name: str,
    reference: Mapping[str, Any],
    *,
    artifact_root: Path | None,
    artifact_root_reason: str | None,
) -> dict[str, Any]:
    raw_path = reference["path"]
    declared_sha = reference["file_sha256"]
    source = {
        "artifact_path": raw_path,
        "declared_file_sha256": declared_sha,
        "actual_file_sha256": None,
        "source_class": None,
        "source_schema_version": None,
        "source_content_sha256": None,
        "formal": None,
        "verified": False,
    }
    if artifact_root is None:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": [
                artifact_root_reason
                or "learning_run_artifact_root_unavailable"
            ],
        }

    relative = Path(raw_path)
    if relative.is_absolute() or ".." in relative.parts:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_path_escape_rejected"],
        }
    unresolved = artifact_root / relative
    if unresolved.is_symlink():
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_symlink_rejected"],
        }
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_file_missing"],
        }
    except (OSError, RuntimeError):
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_path_invalid"],
        }
    try:
        resolved.relative_to(artifact_root)
    except ValueError:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_path_escape_rejected"],
        }
    if resolved.is_dir():
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_directory_rejected"],
        }
    if not resolved.is_file():
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_not_regular_file"],
        }
    try:
        data = resolved.read_bytes()
    except OSError:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_file_read_failed"],
        }
    actual_sha = sha256(data).hexdigest()
    source["actual_file_sha256"] = actual_sha
    if actual_sha != declared_sha:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": ["gate_source_file_sha256_mismatch"],
        }
    try:
        evidence = load_learning_run_source_evidence_bytes(
            data,
            artifact_root=artifact_root,
            expected_variant=variant,
            expected_gate=gate_name,
        )
    except LearningRunSourceAdapterError as exc:
        return {
            "evidence": None,
            "source": source,
            "reason_codes": [exc.code],
        }
    source.update(
        {
            "source_class": evidence["source_class"],
            "source_schema_version": evidence["source_schema_version"],
            "source_content_sha256": evidence["source_content_sha256"],
            "formal": evidence["formal"],
            "verified": True,
        }
    )
    return {
        "evidence": evidence,
        "source": source,
        "reason_codes": [],
    }


def _fact_blockers(
    variant: str,
    gate_name: str,
    facts: Mapping[str, Any],
) -> list[str]:
    prefix = variant.lower()
    required_components = _REQUIRED_COMPONENTS[variant]
    reasons: list[str] = []
    if gate_name == "model_source":
        components = set(facts["component_ids"])
        for component in sorted(required_components - components):
            reasons.append(f"{prefix}_required_model_component_missing.{component}")
        for component in sorted(components - required_components):
            reasons.append(f"{prefix}_unexpected_model_component.{component}")
        if facts["audit_passed"] is not True:
            reasons.append(f"{prefix}_model_external_audit_not_passed")
    elif gate_name == "frozen_unseen_seeds":
        if facts["frozen"] is not True:
            reasons.append(f"{prefix}_evaluation_seed_registry_not_frozen")
        if (
            facts["evaluation_seed_count"]
            < MINIMUM_FORMAL_UNSEEN_SEED_COUNT
        ):
            reasons.append(f"{prefix}_frozen_unseen_seed_count_below_20")
        if facts["training_overlap_count"] != 0:
            reasons.append(f"{prefix}_training_evaluation_seed_overlap")
    elif gate_name == "identifiable_adoption":
        components = set(facts["adopted_component_ids"])
        if facts["actual_adoption_count"] <= 0:
            reasons.append(f"{prefix}_actual_adoption_not_observed")
        if facts["identifiable_change_count"] <= 0:
            reasons.append(_identifiable_change_reason(variant))
        for component in sorted(required_components - components):
            reasons.append(f"{prefix}_adopted_component_missing.{component}")
        for component in sorted(components - required_components):
            reasons.append(f"{prefix}_unexpected_adopted_component.{component}")
        if variant == "A1" and facts["binding_change_count"] <= 0:
            reasons.append("a1_binding_change_not_observed")
        if variant == "A2" and (
            facts["no_op_count"] >= facts["actual_adoption_count"]
        ):
            reasons.append("a2_non_noop_adoption_not_observed")
    elif gate_name == "runtime_ack":
        components = set(facts["acked_component_ids"])
        if (
            facts["required_ack_count"] <= 0
            or facts["matched_ack_count"] != facts["required_ack_count"]
        ):
            reasons.append(f"{prefix}_runtime_ack_incomplete")
        for component in sorted(required_components - components):
            reasons.append(f"{prefix}_runtime_ack_component_missing.{component}")
        for component in sorted(components - required_components):
            reasons.append(f"{prefix}_unexpected_runtime_ack_component.{component}")
    elif gate_name == "physical_window":
        if (
            facts["candidate_window_count"] <= 0
            or facts["confirmed_window_count"]
            != facts["candidate_window_count"]
        ):
            reasons.append(f"{prefix}_physical_window_incomplete")
    elif gate_name == "same_key_r0":
        candidate_count = facts["candidate_count"]
        if (
            candidate_count <= 0
            or facts["pair_count"] != candidate_count
            or facts["unique_pair_count"] != candidate_count
            or facts["same_key_pair_count"] != candidate_count
        ):
            reasons.append(f"{prefix}_same_key_r0_pairing_incomplete")
    elif gate_name == "paired_non_degradation":
        pair_count = facts["pair_count"]
        if (
            pair_count <= 0
            or facts["evaluated_pair_count"] != pair_count
            or facts["required_metric_count"] <= 0
            or facts["available_metric_count"] != facts["required_metric_count"]
        ):
            reasons.append(f"{prefix}_paired_non_degradation_incomplete")
        if facts["non_degraded_pair_count"] != pair_count:
            reasons.append(f"{prefix}_paired_degradation_observed")
    elif gate_name == "truth_use":
        if facts["audited_record_count"] <= 0:
            reasons.append(f"{prefix}_truth_use_audit_empty")
        if facts["online_truth_use_count"] != 0:
            reasons.append(f"{prefix}_online_truth_use_nonzero")
    elif gate_name == "finite_state":
        if facts["audited_value_count"] <= 0:
            reasons.append(f"{prefix}_finite_state_audit_empty")
        if facts["nonfinite_value_count"] != 0:
            reasons.append(f"{prefix}_nonfinite_state_observed")
    elif gate_name == "external_permission":
        if facts["granted"] is not True:
            reasons.append(f"{prefix}_external_permission_not_granted")
        if facts["authority"].strip().lower() == "d6":
            reasons.append(f"{prefix}_d6_cannot_be_permission_authority")
    return reasons


def _audit_storage(storage: Mapping[str, Any]) -> dict[str, Any]:
    if not storage["availability"]:
        reasons = _dedupe(
            [
                *storage["reason_codes"],
                "formal_runtime_storage_observation_unavailable",
            ]
        )
        return {
            "availability": False,
            "passed": None,
            "minimum_free_bytes": FORMAL_RUNTIME_MINIMUM_FREE_BYTES,
            "minimum_free_gib": FORMAL_RUNTIME_MINIMUM_FREE_GIB,
            "source_class": None,
            "observed_at_utc": None,
            "mounts": [],
            "best_available_bytes": None,
            "best_available_gib": None,
            "reason_codes": reasons,
        }
    reasons = list(storage["reason_codes"])
    if storage["source_class"] != "filesystem_disk_usage_snapshot":
        reasons.append("formal_runtime_storage_source_class_not_accepted")
    eligible = [
        mount
        for mount in storage["mounts"]
        if mount["eligible_for_formal_output"]
    ]
    if not eligible:
        best_bytes = None
        reasons.append("formal_output_mount_unavailable")
    else:
        best_bytes = max(mount["available_bytes"] for mount in eligible)
        if best_bytes < FORMAL_RUNTIME_MINIMUM_FREE_BYTES:
            reasons.append("formal_runtime_disk_below_20_gib_threshold")
            reasons.append("alternate_large_capacity_mount_unavailable")
    normalized = _dedupe(reasons)
    return {
        "availability": True,
        "passed": not normalized,
        "minimum_free_bytes": FORMAL_RUNTIME_MINIMUM_FREE_BYTES,
        "minimum_free_gib": FORMAL_RUNTIME_MINIMUM_FREE_GIB,
        "source_class": storage["source_class"],
        "observed_at_utc": storage["observed_at_utc"],
        "mounts": list(storage["mounts"]),
        "best_available_bytes": best_bytes,
        "best_available_gib": (
            None if best_bytes is None else best_bytes / 1024**3
        ),
        "reason_codes": normalized,
    }


def _summarize_gates(
    gates: Mapping[str, Mapping[str, Any]],
    names: Sequence[str],
) -> dict[str, Any]:
    availability = all(gates[name]["availability"] for name in names)
    ready = all(gates[name]["passed"] is True for name in names)
    reasons = _dedupe(
        reason
        for name in names
        for reason in gates[name]["reason_codes"]
    )
    return {
        "availability": availability,
        "ready": ready if availability else None,
        "fail_closed": not ready,
        "reason_codes": [] if ready else reasons,
    }


def _summarize_execution(
    gates: Mapping[str, Mapping[str, Any]],
    storage: Mapping[str, Any],
    *,
    gate_names: Sequence[str],
) -> dict[str, Any]:
    reasons = _dedupe(
        [
            *(
                reason
                for gate_name in gate_names
                for reason in gates[gate_name]["reason_codes"]
            ),
            *storage["reason_codes"],
        ]
    )
    availability = (
        all(gates[name]["availability"] for name in gate_names)
        and storage["availability"]
    )
    startable = (
        all(gates[name]["passed"] is True for name in gate_names)
        and storage["passed"] is True
    )
    return {
        "availability": availability,
        "startable": startable if availability else None,
        "fail_closed": not startable,
        "reason_codes": [] if startable else reasons,
    }


def _variant_blocker_codes(
    gates: Mapping[str, Mapping[str, Any]],
    storage: Mapping[str, Any],
) -> list[str]:
    return _dedupe(
        [
            *(
                reason
                for gate_name in READINESS_GATES
                for reason in gates[gate_name]["reason_codes"]
            ),
            *storage["reason_codes"],
        ]
    )


def _build_aggregate(
    variants: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "variant_count": len(LEARNING_VARIANTS),
        "model_ready_variant_count": sum(
            row["model_readiness"]["ready"] is True
            for row in variants.values()
        ),
        "runtime_evidence_ready_variant_count": sum(
            row["runtime_evidence_readiness"]["ready"] is True
            for row in variants.values()
        ),
        "formal_evidence_ready_variant_count": sum(
            row["formal_evidence_readiness"]["ready"] is True
            for row in variants.values()
        ),
        "execution_startable_variant_count": sum(
            row["execution_startability"]["startable"] is True
            for row in variants.values()
        ),
        "all_variants_execution_startable": all(
            row["execution_startability"]["startable"] is True
            for row in variants.values()
        ),
        "formal_large_run_started": False,
        "disk_changes_model_readiness": False,
    }


def _unavailable_reason(variant: str, gate_name: str) -> str:
    prefix = variant.lower()
    if gate_name == "external_permission":
        return f"{prefix}_external_permission_decision_unavailable"
    return f"{prefix}_{gate_name}_evidence_unavailable"


def _identifiable_change_reason(variant: str) -> str:
    return {
        "G1": "g1_identifiable_graph_adoption_not_observed",
        "A1": "a1_identifiable_assignment_intervention_not_observed",
        "A2": "a2_identifiable_regional_intervention_not_observed",
        "A3": "a3_identifiable_camera_command_adoption_not_observed",
        "C1": "c1_identifiable_composite_adoption_not_observed",
        "F1": "f1_identifiable_composite_adoption_not_observed",
    }[variant]


def _summary_text(summary: Mapping[str, Any], field: str) -> str:
    if not summary.get("availability"):
        return "不可用"
    return "通过" if summary.get(field) is True else "拒绝"


def _gate_text(gate: Mapping[str, Any]) -> str:
    if not gate.get("availability"):
        return "不可用"
    return "通过" if gate.get("passed") is True else "拒绝"


def _validate_output_gate_semantics(
    variant: str,
    gate_name: str,
    gate: Mapping[str, Any],
    *,
    context: str,
) -> None:
    reasons = list(
        _text_sequence(gate["reason_codes"], f"{context}.reason_codes")
    )
    source = _mapping(gate["source"], f"{context}.source")
    artifact_path = source["artifact_path"]
    declared_file_sha = source["declared_file_sha256"]
    actual_file_sha = source["actual_file_sha256"]
    verified = source["verified"]
    if gate["availability"] is False:
        expected = _unavailable_reason(variant, gate_name)
        if not reasons or expected not in reasons:
            _fail(
                "readiness_output_unavailable_gate_reason_missing",
                context,
            )
        if artifact_path is None:
            if any(
                source[name] is not None
                for name in (
                    "declared_file_sha256",
                    "actual_file_sha256",
                    "source_class",
                    "source_schema_version",
                    "source_content_sha256",
                    "formal",
                    "verified",
                )
            ):
                _fail(
                    "readiness_output_unavailable_gate_source_invalid",
                    context,
                )
            return
        _text(artifact_path, f"{context}.source.artifact_path")
        _sha256_text(
            declared_file_sha,
            f"{context}.source.declared_file_sha256",
        )
        if actual_file_sha is not None:
            _sha256_text(
                actual_file_sha,
                f"{context}.source.actual_file_sha256",
            )
        if verified is not False:
            _fail(
                "readiness_output_unavailable_gate_verified",
                context,
            )
        if any(
            source[name] is not None
            for name in (
                "source_class",
                "source_schema_version",
                "source_content_sha256",
                "formal",
            )
        ):
            _fail(
                "readiness_output_unavailable_gate_has_accepted_source",
                context,
            )
        return

    _text(artifact_path, f"{context}.source.artifact_path")
    declared_file_sha = _sha256_text(
        declared_file_sha,
        f"{context}.source.declared_file_sha256",
    )
    actual_file_sha = _sha256_text(
        actual_file_sha,
        f"{context}.source.actual_file_sha256",
    )
    if declared_file_sha != actual_file_sha:
        _fail("readiness_output_gate_file_sha256_mismatch", context)
    if verified is not True:
        _fail("readiness_output_gate_source_not_verified", context)
    source_class = _text(
        source["source_class"],
        f"{context}.source.source_class",
    )
    source_schema = _text(
        source["source_schema_version"],
        f"{context}.source.source_schema_version",
    )
    if source_schema not in LEARNING_RUN_SUPPORTED_SOURCE_SCHEMAS[gate_name]:
        _fail("readiness_output_gate_source_schema_unsupported", context)
    _sha256_text(
        source["source_content_sha256"],
        f"{context}.source.source_content_sha256",
    )
    formal = _strict_bool(
        source["formal"],
        f"{context}.source.formal",
    )
    facts = _mapping(gate["facts"], f"{context}.facts")
    normalized_facts = _validate_gate_facts(
        gate_name,
        facts,
        context=f"{context}.facts",
    )
    if dict(facts) != normalized_facts:
        _fail("readiness_output_gate_facts_not_normalized", context)

    mandatory: list[str] = []
    if source_class not in _EXPECTED_SOURCE_CLASS[gate_name]:
        mandatory.append(
            _SOURCE_CLASS_REJECTION_CODES.get(
                source_class,
                f"{variant.lower()}_{gate_name}_source_class_not_accepted",
            )
        )
    if formal is not True:
        mandatory.append(f"{variant.lower()}_{gate_name}_not_formal")
    mandatory.extend(_fact_blockers(variant, gate_name, normalized_facts))
    missing = [reason for reason in _dedupe(mandatory) if reason not in reasons]
    if missing:
        _fail(
            "readiness_output_gate_required_reason_missing",
            f"{context}:{','.join(missing)}",
        )
    if gate["passed"] is not (not reasons):
        _fail("readiness_output_gate_result_mismatch", context)


def _validate_output_storage_semantics(
    storage: Mapping[str, Any],
) -> None:
    reasons = list(
        _text_sequence(
            storage["reason_codes"],
            "readiness_output.storage.reason_codes",
        )
    )
    if storage["availability"] is False:
        if (
            storage["source_class"] is not None
            or storage["observed_at_utc"] is not None
            or storage["mounts"]
            or storage["best_available_bytes"] is not None
            or storage["best_available_gib"] is not None
        ):
            _fail("readiness_output_unavailable_storage_has_evidence")
        if "formal_runtime_storage_observation_unavailable" not in reasons:
            _fail("readiness_output_unavailable_storage_reason_missing")
        return

    source_class = _text(
        storage["source_class"],
        "readiness_output.storage.source_class",
    )
    _text(
        storage["observed_at_utc"],
        "readiness_output.storage.observed_at_utc",
    )
    normalized_mounts: list[dict[str, Any]] = []
    for index, raw_mount in enumerate(storage["mounts"]):
        mount = _mapping(
            raw_mount,
            f"readiness_output.storage.mounts.{index}",
        )
        normalized_mounts.append(
            {
                "path": _text(
                    mount["path"],
                    f"readiness_output.storage.mounts.{index}.path",
                ),
                "available_bytes": _nonnegative_int(
                    mount["available_bytes"],
                    (
                        "readiness_output.storage.mounts."
                        f"{index}.available_bytes"
                    ),
                ),
                "eligible_for_formal_output": _strict_bool(
                    mount["eligible_for_formal_output"],
                    (
                        "readiness_output.storage.mounts."
                        f"{index}.eligible_for_formal_output"
                    ),
                ),
            }
        )
    if list(storage["mounts"]) != normalized_mounts:
        _fail("readiness_output_storage_mounts_not_normalized")

    eligible = [
        mount
        for mount in normalized_mounts
        if mount["eligible_for_formal_output"]
    ]
    expected_best = (
        max(mount["available_bytes"] for mount in eligible)
        if eligible
        else None
    )
    if storage["best_available_bytes"] != expected_best:
        _fail("readiness_output_storage_best_bytes_mismatch")
    expected_gib = (
        None if expected_best is None else expected_best / 1024**3
    )
    best_gib = storage["best_available_gib"]
    if (
        best_gib is not None
        and (
            isinstance(best_gib, bool)
            or not isinstance(best_gib, (int, float))
            or not isfinite(best_gib)
        )
    ):
        _fail("readiness_output_storage_best_gib_invalid")
    if best_gib != expected_gib:
        _fail("readiness_output_storage_best_gib_mismatch")

    mandatory: list[str] = []
    if source_class != "filesystem_disk_usage_snapshot":
        mandatory.append("formal_runtime_storage_source_class_not_accepted")
    if expected_best is None:
        mandatory.append("formal_output_mount_unavailable")
    elif expected_best < FORMAL_RUNTIME_MINIMUM_FREE_BYTES:
        mandatory.extend(
            (
                "formal_runtime_disk_below_20_gib_threshold",
                "alternate_large_capacity_mount_unavailable",
            )
        )
    missing = [reason for reason in mandatory if reason not in reasons]
    if missing:
        _fail(
            "readiness_output_storage_required_reason_missing",
            ",".join(missing),
        )
    if storage["passed"] is not (not reasons):
        _fail("readiness_output_storage_result_mismatch")


def _validate_output_variant_semantics(
    variant: str,
    row: Mapping[str, Any],
    storage: Mapping[str, Any],
) -> None:
    gates = _mapping(
        row["gates"],
        f"readiness_output.{variant}.gates",
    )
    expected_summaries = {
        "model_readiness": _summarize_gates(gates, MODEL_GATES),
        "runtime_evidence_readiness": _summarize_gates(
            gates,
            RUNTIME_EVIDENCE_GATES,
        ),
        "formal_evidence_readiness": _summarize_gates(
            gates,
            (*MODEL_GATES, *RUNTIME_EVIDENCE_GATES),
        ),
    }
    for name, expected in expected_summaries.items():
        if dict(_mapping(row[name], name)) != expected:
            _fail(
                "readiness_output_summary_semantics_mismatch",
                f"{variant}:{name}",
            )
    execution = _summarize_execution(
        gates,
        storage,
        gate_names=(
            *MODEL_GATES,
            *RUNTIME_EVIDENCE_GATES,
            "external_permission",
        ),
    )
    if dict(_mapping(row["execution_startability"], "execution")) != execution:
        _fail(
            "readiness_output_execution_semantics_mismatch",
            variant,
        )
    if row["blocker_codes"] != _variant_blocker_codes(gates, storage):
        _fail("readiness_output_blocker_semantics_mismatch", variant)


def _validate_output_summary(
    summary: Mapping[str, Any],
    *,
    result_field: str,
    context: str,
) -> None:
    availability = _strict_bool(
        summary["availability"],
        f"{context}.availability",
    )
    result = summary[result_field]
    if result is not None and not isinstance(result, bool):
        _fail("readiness_output_summary_result_invalid", context)
    if not availability and result is not None:
        _fail("readiness_output_unavailable_summary_has_result", context)
    _strict_bool(summary["fail_closed"], f"{context}.fail_closed")
    reasons = _text_sequence(
        summary["reason_codes"],
        f"{context}.reason_codes",
    )
    if list(reasons) != summary["reason_codes"]:
        _fail("readiness_output_summary_reason_order_invalid", context)


def _expect_exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = set(value)
    if actual != set(expected):
        _fail(
            "readiness_fields_mismatch",
            f"{context}:{','.join(sorted(actual ^ set(expected)))}",
        )


def _json_mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("readiness_mapping_required", context)
    try:
        normalized = json.loads(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            )
        )
    except (TypeError, ValueError) as exc:
        _fail("readiness_json_value_invalid", f"{context}:{type(exc).__name__}")
    if not isinstance(normalized, dict):
        _fail("readiness_mapping_required", context)
    return normalized


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("readiness_mapping_required", context)
    return value


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("readiness_text_required", context)
    return value.strip()


def _text_sequence(value: Any, context: str) -> tuple[str, ...]:
    if (
        isinstance(value, (str, bytes, bytearray))
        or not isinstance(value, Sequence)
    ):
        _fail("readiness_text_sequence_required", context)
    normalized = tuple(_text(item, context) for item in value)
    if len(normalized) != len(set(normalized)):
        _fail("readiness_text_sequence_duplicate", context)
    return normalized


def _strict_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        _fail("readiness_boolean_required", context)
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("readiness_nonnegative_integer_required", context)
    return value


def _sha256_text(value: Any, context: str) -> str:
    text = _text(value, context)
    if len(text) != 64 or any(character not in _HEX64 for character in text):
        _fail("readiness_sha256_required", context)
    return text


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_finite(value: Any) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, float):
        if not isfinite(value):
            _fail("readiness_nonfinite_value")
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_finite(item)
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for item in value:
            _assert_finite(item)


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
    raise LearningRunReadinessError(code, detail)
