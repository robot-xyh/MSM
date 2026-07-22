"""Read-only D6 audit for reserved-seed D3/D4 intervention receipts.

The scalable-3D producer bundle is treated as a set of claims.  This module
authenticates the file inventory, recomputes the lineage and arm summaries,
and emits a detached outcome-availability sidecar.  It never imports producer
code and never writes below the input directory.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence


RESERVED_SEED_AUDIT_SCHEMA_VERSION_V1 = (
    "d6.reserved-seed-intervention-outcome-availability.v1"
)
RESERVED_SEED_AUDIT_SCHEMA_VERSION_V2 = (
    "d6.reserved-seed-intervention-outcome-availability.v2"
)
RESERVED_SEED_AUDIT_MANIFEST_SCHEMA_VERSION_V1 = (
    "d6.reserved-seed-intervention-provenance-manifest.v1"
)
RESERVED_SEED_AUDIT_MANIFEST_SCHEMA_VERSION_V2 = (
    "d6.reserved-seed-intervention-provenance-manifest.v2"
)
RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1 = (
    "scalable3d-reserved-seed-interventions-v1"
)
RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2 = (
    "scalable3d-reserved-seed-interventions-v2"
)
RESERVED_SEED_LINEAGE_SCHEMA_VERSION = (
    "scalable3d-reserved-seed-source-lineage-v1"
)

# Backward-compatible names remain bound to the historical v1 audit profile.
RESERVED_SEED_AUDIT_SCHEMA_VERSION = RESERVED_SEED_AUDIT_SCHEMA_VERSION_V1
RESERVED_SEED_AUDIT_MANIFEST_SCHEMA_VERSION = (
    RESERVED_SEED_AUDIT_MANIFEST_SCHEMA_VERSION_V1
)
RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION = (
    RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1
)

EXPECTED_RESERVED_SEEDS = tuple(range(1000, 1020))
EXPECTED_SOURCE_COMMIT = "6d5bfead31d53258b020a5f157b2ad5e7f25ee35"
EXPECTED_CHECKSUMS_SHA256 = (
    "931f68855df3e9f8c2a1f718249cf33c4ba6899d907ad0032af5b9588e90f08f"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "c393f26042f048a8614c81d9ffaef1a58d2b2df1dc32740eae8f10246833e691"
)
EXPECTED_SOURCE_COMMIT_V2 = "78912963b67fe86ee9a8d29186b18a9dd60c460c"
EXPECTED_CHECKSUMS_SHA256_V2 = (
    "821f15035e628d8db86f13c22d93f8e05142c5f00aae9118974a74bdc98b72bc"
)
EXPECTED_SOURCE_MANIFEST_SHA256_V2 = (
    "d6ef23b28add92e9a24a185ea72a7275e341bd796a2e11930c4d5f46b19a883c"
)
EXPECTED_D3_BUNDLE_MANIFEST_SHA256 = (
    "a9213d65606a9e2f921040e153488c0f4cdebb10882fa16013fce5b59f9314c0"
)
EXPECTED_D3_BUNDLE_STATE_SHA256 = (
    "e3da9fd5b54451da83358405b6051991e0c78bcf9f538b350d459b05faf8e0b2"
)
EXPECTED_D4_BUNDLE_MANIFEST_SHA256 = (
    "dad2adbe9c36dd9ff8ee8bb3c11b1e07e66743c6f80dd8e956799208a10c05c9"
)
EXPECTED_D4_BUNDLE_STATE_SHA256 = (
    "3da0360be8788f3ffeb8e9f9eba3e0d5369ec0bdf9e05729dfb1db07d71d5f62"
)
EXPECTED_D3_SAFETY_SHELL_VERSION_V2 = (
    "d3-offline-intervention-safety-shell-v2"
)
EXPECTED_D3_SAFETY_SHELL_CONFIG_SHA256_V2 = (
    "d95fff61d31d80dc799ca6a9fcbf1c6e7adbed5a3f3cdd08b2ab38f9365f75b8"
)
EXPECTED_D4_ARM_EVIDENCE_SCHEMA_VERSION_V2 = (
    "d4-region-resource-paired-arm-evidence-v2"
)

RESERVED_SEED_AUDIT_PROFILE_BINDINGS: dict[str, dict[str, str]] = {
    "v1": {
        "source_manifest_schema_version": (
            RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1
        ),
        "source_git_commit": EXPECTED_SOURCE_COMMIT,
        "checksums_sha256": EXPECTED_CHECKSUMS_SHA256,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
    },
    "v2": {
        "source_manifest_schema_version": (
            RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
        ),
        "source_git_commit": EXPECTED_SOURCE_COMMIT_V2,
        "checksums_sha256": EXPECTED_CHECKSUMS_SHA256_V2,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256_V2,
    },
}

_CHECKSUMS_FILE = "SHA256SUMS"
_SOURCE_MANIFEST_FILE = "manifest.json"
_D3_FILE = "d3_offline_paired_intervention.json"
_D4_FILE = "d4_offline_paired_intervention.json"
_LINEAGE_FILE = "source_lineage.jsonl"
_PRODUCER_REPORT_FILE = "RESERVED_SEED_INTERVENTION_REPORT_CN.md"
_INPUT_FILES = (
    _CHECKSUMS_FILE,
    _D3_FILE,
    _D4_FILE,
    _SOURCE_MANIFEST_FILE,
    _PRODUCER_REPORT_FILE,
    _LINEAGE_FILE,
)
_CHECKSUM_MEMBER_FILES = tuple(
    name for name in _INPUT_FILES if name != _CHECKSUMS_FILE
)
_MANIFEST_ARTIFACT_PATHS = {
    "d3_execution": _D3_FILE,
    "d4_execution": _D4_FILE,
    "report_cn": _PRODUCER_REPORT_FILE,
    "source_lineage": _LINEAGE_FILE,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256SUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$")

_D3_PAIR_DIFFERENCE_FIELDS = {
    "arm_id",
    "arm_kind",
    "isolation_id",
    "learning_cost_intervention_enabled",
    "planner_path",
}


class ReservedSeedInterventionAuditError(ValueError):
    """Raised when a reserved-seed artifact fails a fail-closed audit gate."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReservedSeedInterventionAuditInputs:
    """Explicit input, output, timestamp, and out-of-band digest bindings."""

    source_dir: Path
    output_dir: Path
    audited_at_utc: str
    expected_source_commit: str = EXPECTED_SOURCE_COMMIT
    expected_checksums_sha256: str = EXPECTED_CHECKSUMS_SHA256
    expected_source_manifest_sha256: str = EXPECTED_SOURCE_MANIFEST_SHA256
    expected_d3_bundle_manifest_sha256: str = (
        EXPECTED_D3_BUNDLE_MANIFEST_SHA256
    )
    expected_d3_bundle_state_sha256: str = EXPECTED_D3_BUNDLE_STATE_SHA256
    expected_d4_bundle_manifest_sha256: str = (
        EXPECTED_D4_BUNDLE_MANIFEST_SHA256
    )
    expected_d4_bundle_state_sha256: str = EXPECTED_D4_BUNDLE_STATE_SHA256
    expected_source_manifest_schema_version: str = (
        RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_dir", Path(self.source_dir).resolve())
        object.__setattr__(self, "output_dir", Path(self.output_dir).resolve())
        source_schema_version = str(
            self.expected_source_manifest_schema_version
        ).strip()
        if source_schema_version not in {
            RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1,
            RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2,
        }:
            _fail(
                "invalid_expected_source_manifest_schema_version",
                repr(source_schema_version),
            )
        object.__setattr__(
            self,
            "expected_source_manifest_schema_version",
            source_schema_version,
        )
        source_commit = str(self.expected_source_commit).strip().lower()
        if _GIT_COMMIT_RE.fullmatch(source_commit) is None:
            _fail(
                "invalid_source_git_commit",
                f"expected_source_commit={source_commit!r}",
            )
        object.__setattr__(self, "expected_source_commit", source_commit)
        for name in (
            "expected_checksums_sha256",
            "expected_source_manifest_sha256",
            "expected_d3_bundle_manifest_sha256",
            "expected_d3_bundle_state_sha256",
            "expected_d4_bundle_manifest_sha256",
            "expected_d4_bundle_state_sha256",
        ):
            value = str(getattr(self, name)).strip().lower()
            if _SHA256_RE.fullmatch(value) is None:
                _fail("invalid_out_of_band_sha256", f"{name}={value!r}")
            object.__setattr__(self, name, value)
        if not str(self.audited_at_utc).strip():
            _fail("audit_timestamp_missing", "audited_at_utc is required")

    def expected_bindings(self) -> dict[str, str]:
        return {
            "source_manifest_schema_version": (
                self.expected_source_manifest_schema_version
            ),
            "source_git_commit": self.expected_source_commit,
            "checksums_sha256": self.expected_checksums_sha256,
            "source_manifest_sha256": self.expected_source_manifest_sha256,
            "d3_bundle_manifest_sha256": (
                self.expected_d3_bundle_manifest_sha256
            ),
            "d3_bundle_state_sha256": self.expected_d3_bundle_state_sha256,
            "d4_bundle_manifest_sha256": (
                self.expected_d4_bundle_manifest_sha256
            ),
            "d4_bundle_state_sha256": self.expected_d4_bundle_state_sha256,
        }


def audit_reserved_seed_interventions(
    inputs: ReservedSeedInterventionAuditInputs,
) -> dict[str, Any]:
    """Authenticate and independently summarize one producer artifact set."""

    paths = _validate_input_locations(inputs)
    snapshot_before = _snapshot(paths)
    checksums = _validate_checksum_chain(inputs, paths, snapshot_before)

    source_manifest = _load_json_object(paths[_SOURCE_MANIFEST_FILE], "manifest")
    source_schema_version = _source_manifest_schema_version(source_manifest)
    _expect_equal(
        source_schema_version,
        inputs.expected_source_manifest_schema_version,
        "source_manifest_profile_schema_mismatch",
        (
            f"expected={inputs.expected_source_manifest_schema_version!r}, "
            f"actual={source_schema_version!r}"
        ),
    )
    lineage_records = _load_jsonl(paths[_LINEAGE_FILE])
    d3_payload = _load_json_object(paths[_D3_FILE], "D3 execution artifact")
    d4_payload = _load_json_object(paths[_D4_FILE], "D4 execution artifact")

    lineage_summary, lineage_by_seed = _audit_source_lineage(
        lineage_records,
        expected_source_commit=inputs.expected_source_commit,
    )
    d3_summary = _audit_d3(
        d3_payload,
        lineage_by_seed=lineage_by_seed,
        inputs=inputs,
        source_schema_version=source_schema_version,
    )
    d4_summary = _audit_d4(
        d4_payload,
        lineage_by_seed=lineage_by_seed,
        inputs=inputs,
        source_schema_version=source_schema_version,
    )
    _validate_source_manifest(
        source_manifest,
        lineage_summary=lineage_summary,
        d3_summary=d3_summary,
        d4_summary=d4_summary,
        inputs=inputs,
        input_sha256=snapshot_before,
        source_schema_version=source_schema_version,
    )

    snapshot_after = _snapshot(paths)
    _expect_equal(
        snapshot_after,
        snapshot_before,
        "input_artifact_mutation_detected",
        "one or more producer input files changed during the audit",
    )

    unavailable_runtime = _unavailable(
        "runtime_ack_references_not_present_in_the_authenticated_artifact_set"
    )
    unavailable_physical = _unavailable(
        "post_intervention_physical_state_windows_not_present"
    )
    unavailable_counterfactual = _unavailable(
        "counterfactual_outcome_evidence_not_present"
    )
    unavailable_causal = _unavailable(
        "paired_physical_outcomes_and_counterfactual_evidence_not_present"
    )
    unavailable_paired_outcome = _unavailable(
        "post_intervention_physical_outcome_windows_not_present"
    )
    unavailable_paired_effect = _unavailable(
        "paired_effect_is_not_defined_without_paired_physical_outcomes"
    )
    is_v2 = (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    evidence_availability = {
        "execution_receipts": True,
        "runtime_ack": False,
        "physical_outcome": False,
        "counterfactual": False,
        "causal": False,
    }
    availability_details: dict[str, Any] = {
        "execution_receipts": {
            "available": True,
            "status": "available",
            "value": True,
            "d3_receipt_count": d3_summary["execution_receipt_count"],
            "d4_receipt_count": d4_summary["execution_receipt_count"],
            "reason": None,
        },
        "runtime_ack": unavailable_runtime,
        "physical_outcome": unavailable_physical,
        "counterfactual": unavailable_counterfactual,
        "causal": unavailable_causal,
    }
    if is_v2:
        evidence_availability["offline_assignment_comparison"] = True
        availability_details["offline_assignment_comparison"] = dict(
            _mapping(d3_summary, "offline_assignment_comparison")
        )

    d3_fail_closed = d3_summary["treatment_rule_fallback_count"] == 20
    d4_fail_closed = (
        d4_summary["treatment_safe_adopted_count"] == 0
        and d4_summary["treatment_rule_fallback_count"] == 20
    )
    limitations = [
        "No runtime ACK or post-intervention physical outcome is included.",
        "Bundle digest identifiers are bound, but bundle files are not in the input directory and were not re-hashed by D6.",
        "Receipt latency is available; policy effectiveness and causal effect are not.",
    ]
    if is_v2:
        limitations.insert(
            0,
            "D3 isolated treatment application is observable only as a same-frame offline assignment comparison; D4 has zero safe adoptions.",
        )
        limitations.append(
            "The nominal 5v5 run is not evidence of degraded-operation strategy effectiveness."
        )
    else:
        limitations.insert(0, "D3 and D4 treatment adoption counts are both zero.")

    result: dict[str, Any] = {
        "schema_version": (
            RESERVED_SEED_AUDIT_SCHEMA_VERSION_V2
            if is_v2
            else RESERVED_SEED_AUDIT_SCHEMA_VERSION_V1
        ),
        "audited_at_utc": str(inputs.audited_at_utc),
        "audit_role": "independent_read_only_consumer",
        "status": (
            "pass_offline_assignment_comparison_only"
            if is_v2
            else "pass_fail_closed_only"
        ),
        "audit_passed": True,
        "source": {
            "directory": str(inputs.source_dir),
            "schema_version": source_manifest["schema_version"],
            "scenario": source_manifest["scenario"],
            "resource_count": source_manifest["resource_count"],
            "target_count": source_manifest["target_count"],
            "duration_s": source_manifest["duration_s"],
            "reserved_seeds": list(EXPECTED_RESERVED_SEEDS),
            "source_git_commit": inputs.expected_source_commit,
        },
        "integrity": {
            "sha256sums_verified": True,
            "manifest_artifact_sha256_verified": True,
            "internal_d3_hashes_verified": True,
            "internal_d4_specification_hashes_verified": True,
            "input_artifacts_unchanged": True,
            "expected_bindings": inputs.expected_bindings(),
            "checksums_members": dict(sorted(checksums.items())),
            "input_file_sha256_before": dict(sorted(snapshot_before.items())),
            "input_file_sha256_after": dict(sorted(snapshot_after.items())),
            "input_artifact_set_sha256": _artifact_set_sha256(snapshot_before),
        },
        "source_lineage": lineage_summary,
        "evidence_availability": evidence_availability,
        "availability_details": availability_details,
        "paired_results": {
            "outcome": unavailable_paired_outcome,
            "effect": unavailable_paired_effect,
            "non_degradation": _unavailable(
                "paired_non_degradation_requires_adopted_treatments_and_outcomes"
            ),
        },
        "d3": d3_summary,
        "d4": d4_summary,
        "claims": {
            "fail_closed_behavior_verified": d3_fail_closed and d4_fail_closed,
            "d3_isolated_treatment_application_verified": (
                d3_summary["treatment_applied_count"] == 20
            ),
            "d4_fail_closed_behavior_verified": d4_fail_closed,
            "same_frame_offline_assignment_comparison_available": is_v2,
            "evidence_integrity_verified": True,
            "candidate_policy_effectiveness_proven": False,
            "paired_non_degradation_proven": False,
            "counterfactual_effect_proven": False,
            "causal_effect_proven": False,
            "online_admission_changed": False,
            "runtime_authority_granted": False,
        },
        "limitations": limitations,
    }
    return _with_content_sha256(result)


def write_reserved_seed_intervention_audit(
    inputs: ReservedSeedInterventionAuditInputs,
) -> dict[str, Path]:
    """Write a detached sidecar/report/manifest package atomically."""

    if inputs.output_dir.exists():
        _fail("output_directory_exists", str(inputs.output_dir))
    report = audit_reserved_seed_interventions(inputs)
    markdown = render_reserved_seed_intervention_audit_markdown(report)

    parent = inputs.output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{inputs.output_dir.name}.", dir=parent))
    try:
        sidecar_path = temporary / "outcome_availability_sidecar.json"
        markdown_path = temporary / "RESERVED_SEED_INTERVENTION_AUDIT_CN.md"
        _write_json(sidecar_path, report)
        markdown_path.write_text(markdown, encoding="utf-8")

        output_artifacts = [
            _artifact_record(sidecar_path),
            _artifact_record(markdown_path),
        ]
        provenance = _with_content_sha256(
            {
                "schema_version": (
                    RESERVED_SEED_AUDIT_MANIFEST_SCHEMA_VERSION_V2
                    if report["source"]["schema_version"]
                    == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
                    else RESERVED_SEED_AUDIT_MANIFEST_SCHEMA_VERSION_V1
                ),
                "audited_at_utc": report["audited_at_utc"],
                "status": report["status"],
                "audit_sidecar_content_sha256": report["content_sha256"],
                "source_directory": str(inputs.source_dir),
                "expected_bindings": inputs.expected_bindings(),
                "input_artifact_set_sha256": report["integrity"][
                    "input_artifact_set_sha256"
                ],
                "input_artifacts": [
                    {
                        "path": name,
                        "sha256": digest,
                        "size_bytes": (inputs.source_dir / name).stat().st_size,
                    }
                    for name, digest in sorted(
                        report["integrity"]["input_file_sha256_before"].items()
                    )
                ],
                "artifacts": output_artifacts,
                "evidence_availability": dict(report["evidence_availability"]),
                "claims": dict(report["claims"]),
            }
        )
        provenance_path = temporary / "provenance_manifest.json"
        _write_json(provenance_path, provenance)
        checksum_records = output_artifacts + [_artifact_record(provenance_path)]
        checksums_path = temporary / "SHA256SUMS"
        checksums_path.write_text(
            "".join(
                f"{item['sha256']}  {item['path']}\n"
                for item in checksum_records
            ),
            encoding="ascii",
        )

        source_paths = {
            name: inputs.source_dir / name
            for name in _INPUT_FILES
        }
        current_snapshot = _snapshot(source_paths)
        _expect_equal(
            current_snapshot,
            report["integrity"]["input_file_sha256_before"],
            "input_artifact_mutation_detected",
            "producer inputs changed before output package publication",
        )
        temporary.rename(inputs.output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return {
        "sidecar": inputs.output_dir / sidecar_path.name,
        "markdown": inputs.output_dir / markdown_path.name,
        "provenance_manifest": inputs.output_dir / provenance_path.name,
        "checksums": inputs.output_dir / checksums_path.name,
    }


def render_reserved_seed_intervention_audit_markdown(
    report: Mapping[str, Any],
) -> str:
    """Render the compact Chinese audit report from the detached sidecar."""

    d3 = _mapping(report, "d3")
    d4 = _mapping(report, "d4")
    d3_latency = _mapping(d3, "treatment_inference_latency_ms")
    d4_latency = _mapping(d4, "treatment_candidate_latency_ms")
    source = _mapping(report, "source")
    integrity = _mapping(report, "integrity")
    details = _mapping(report, "availability_details")
    paired = _mapping(report, "paired_results")
    d3_status = _mapping(d3, "control_decision_counts")
    d3_fallback = _mapping(d3, "treatment_fallback_reason_counts")
    d4_rejection = _mapping(d4, "treatment_rejection_reason_counts")
    is_v2 = (
        source["schema_version"]
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )

    lines = [
        "# D6 保留 seed 隔离执行独立审计",
        "",
        "## 1. 审计范围",
        "",
        f"- 审计时间（UTC）：`{report['audited_at_utc']}`。",
        f"- 权威输入：`{source['directory']}`。",
        f"- 源 schema：`{source['schema_version']}`。",
        f"- 场景与规模：`{source['scenario']}`，资源 `{source['resource_count']}`，目标 `{source['target_count']}`，seed `1000-1019`。",
        f"- 源提交：`{source['source_git_commit']}`。",
        "- 方法：D6 只读重算校验和、lineage、arm/receipt、成对身份及版本对应汇总，不导入 D3/D4 producer 代码。",
        "",
        "## 2. 完整性结果",
        "",
        "| 检查项 | 结果 |",
        "| --- | --- |",
        "| `SHA256SUMS` | 通过 |",
        "| manifest 内全部 artifact SHA | 通过 |",
        "| 20 条 source lineage / seed 1000-1019 | 通过 |",
        "| dirty source episode | `0` |",
        "| online truth use | `0` |",
        "| 同源/随机流/通信/故障日程 | `20/20` 全部一致 |",
        "| 审计前后输入 artifact set SHA | 一致 |",
        f"| 输入 artifact set SHA256 | `{integrity['input_artifact_set_sha256']}` |",
        "",
        "## 3. Outcome availability",
        "",
        "| 证据 | available | value | 原因 |",
        "| --- | --- | --- | --- |",
        f"| execution receipts | `true` | `true` | D3 `{details['execution_receipts']['d3_receipt_count']}` + D4 `{details['execution_receipts']['d4_receipt_count']}` |",
    ]
    if is_v2:
        offline = _mapping(details, "offline_assignment_comparison")
        lines.append(
            f"| offline assignment comparison | `true` | `true` | `{offline['scope']}` |"
        )
    lines.extend(
        [
            f"| runtime ACK | `false` | `null` | `{details['runtime_ack']['reason']}` |",
            f"| physical outcome | `false` | `null` | `{details['physical_outcome']['reason']}` |",
            f"| counterfactual | `false` | `null` | `{details['counterfactual']['reason']}` |",
            f"| causal | `false` | `null` | `{details['causal']['reason']}` |",
            f"| paired outcome | `false` | `null` | `{paired['outcome']['reason']}` |",
            f"| paired effect | `false` | `null` | `{paired['effect']['reason']}` |",
            "",
            "`paired outcome/effect` 因缺少采用后的物理状态窗口而不可用，值必须为 `null`，不得解释为数值 `0`。",
            "",
            "## 4. D3 独立重算",
            "",
            f"- arm：`{d3['arm_count']}`，control/treatment=`{d3['control_arm_count']}/{d3['treatment_arm_count']}`；20 对输入与 bundle 身份全部一致。",
            f"- treatment 实际应用：`{d3['treatment_applied_count']}/20`；规则回退：`{d3['treatment_rule_fallback_count']}/20`；`out_of_distribution`：`{d3_fallback.get('out_of_distribution', 0)}`。",
            f"- control 状态：`unchanged={d3_status.get('unchanged', 0)}`，`held_by_hysteresis={d3_status.get('held_by_hysteresis', 0)}`，`replan_ack_no_change={d3_status.get('replan_ack_no_change', 0)}`。",
        ]
    )
    if is_v2:
        comparison = _mapping(d3, "offline_assignment_comparison")
        costs = _mapping(comparison, "assignment_cost")
        high_threat = _mapping(comparison, "high_threat_unmet")
        duplicate = _mapping(comparison, "duplicate_count")
        hard = _mapping(comparison, "hard_violation_count")
        churn = _mapping(comparison, "churn_mean")
        shell = _mapping(d3, "safety_shell")
        lines.extend(
            [
                f"- safety shell：`{shell['version']}` / `{shell['config_sha256']}`，40/40 arm 绑定通过。",
                f"- 同帧离线 assignment comparison 可用：规则/treatment 在规则 cost 基准上的均值为 `{costs['control_rule_mean']}` / `{costs['treatment_assignment_mean']}`；high-threat unmet=`{high_threat['control_total']}/{high_threat['treatment_total']}`，duplicate=`{duplicate['control_total']}/{duplicate['treatment_total']}`，hard=`{hard['control_total']}/{hard['treatment_total']}`，churn mean=`{churn['control']}/{churn['treatment']}`。",
                f"- treatment inference：n=`{d3_latency['sample_count']}`，mean=`{_format_ms(d3_latency['mean_ms'])}` ms，p95(linear)=`{_format_ms(d3_latency['p95_ms'])}` ms。该 comparison 不是物理 outcome/effect。",
            ]
        )
    else:
        lines.append(
            f"- treatment receipt 推理时延可用：n=`{d3_latency['sample_count']}`，mean=`{_format_ms(d3_latency['mean_ms'])}` ms，p95=`{_format_ms(d3_latency['p95_ms'])}` ms；这是失败关闭路径时延，不是效果值。"
        )
    lines.extend(
        [
            f"- bundle manifest/state 绑定：`{d3['bundle_binding']['manifest_sha256']}` / `{d3['bundle_binding']['state_sha256']}`。",
            "",
            "## 5. D4 独立重算",
            "",
            f"- arm：`{d4['arm_count']}`，control/treatment=`{d4['control_arm_count']}/{d4['treatment_arm_count']}`；20 对输入与 bundle 身份全部一致。",
            f"- treatment 安全采用：`{d4['treatment_safe_adopted_count']}/20`；规则回退：`{d4['treatment_rule_fallback_count']}/20`；`candidate_threshold_or_finite_gate_rejected`：`{d4_rejection.get('candidate_threshold_or_finite_gate_rejected', 0)}`。",
        ]
    )
    if is_v2:
        gates = _mapping(d4, "candidate_gate_summary")
        lines.extend(
            [
                f"- candidate considered=`{gates['candidate_considered_count']}/20`；confidence/OOD/latency/finite/failure pass=`{gates['confidence_gate_passed_count']}/{gates['ood_gate_passed_count']}/{gates['latency_gate_passed_count']}/{gates['finite_gate_passed_count']}/{gates['failure_gate_passed_count']}`；aggregate pass=`{gates['aggregate_gate_passed_count']}`。",
                f"- low-confidence=`{d4_rejection.get('candidate_low_confidence', 0)}/20`。`treatment_candidate_latency_ms` 的 p95(nearest-rank)=`{_format_ms(d4_latency['p95_ms'])}` ms；`candidate_gate_summary.candidate_latency_ms` 的 p95(linear interpolation)=`{_format_ms(gates['candidate_latency_ms']['p95'])}` ms。两者使用相同 20 个样本，但统计口径不同。",
                "- 本次是 nominal 5v5 门控审计，不是通信、节点或资源降级下的策略评估。",
            ]
        )
    else:
        lines.append(
            f"- treatment candidate 推理时延可用：n=`{d4_latency['sample_count']}`，mean=`{_format_ms(d4_latency['mean_ms'])}` ms，median=`{_format_ms(d4_latency['median_ms'])}` ms，p95(nearest-rank)=`{_format_ms(d4_latency['p95_ms'])}` ms，max=`{_format_ms(d4_latency['max_ms'])}` ms。"
        )
    lines.extend(
        [
            f"- bundle manifest/state 绑定：`{d4['bundle_binding']['manifest_sha256']}` / `{d4['bundle_binding']['state_sha256']}`。",
            "",
            "## 6. 结论与边界",
            "",
        ]
    )
    if is_v2:
        lines.append(
            "本审计证明 v2 输入完整、D3 隔离 treatment 已应用且同帧 assignment comparison 未出现 cost/safety/churn 退化，并证明 D4 在低置信度门失败时 20/20 回退。它不证明 D3 或 D4 候选策略有效，也不证明运行时采用、物理非退化、反事实收益或因果收益。"
        )
    else:
        lines.append(
            "本审计只证明两条候选路径在 20 个保留 seed 上失败关闭，以及输入、lineage、成对执行 receipt 和 digest 绑定完整。它不证明 D3 或 D4 候选策略有效，也不证明非退化、运行时采用、物理收益、反事实收益或因果收益。"
        )
    lines.extend(
        [
            "",
            "D3/D4 bundle 文件不在本输入目录内；D6 校验 artifact 中声明的 manifest/state digest 与任务给定 digest 的严格绑定，未重新哈希模型文件。只有取得严格绑定的 runtime ACK 和采用后的物理状态窗口，才能另行计算 paired outcome/effect。",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_input_locations(
    inputs: ReservedSeedInterventionAuditInputs,
) -> dict[str, Path]:
    _expect(inputs.source_dir.is_dir(), "source_directory_missing", str(inputs.source_dir))
    _expect(
        not _is_relative_to(inputs.output_dir, inputs.source_dir),
        "output_inside_input_directory",
        str(inputs.output_dir),
    )
    actual_names = {item.name for item in inputs.source_dir.iterdir()}
    _expect_equal(
        actual_names,
        set(_INPUT_FILES),
        "input_artifact_inventory_mismatch",
        f"expected={sorted(_INPUT_FILES)!r}, actual={sorted(actual_names)!r}",
    )
    paths = {name: inputs.source_dir / name for name in _INPUT_FILES}
    for name, path in paths.items():
        _expect(path.is_file(), "input_artifact_missing", name)
        _expect(not path.is_symlink(), "input_artifact_symlink_rejected", name)
    return paths


def _source_manifest_schema_version(manifest: Mapping[str, Any]) -> str:
    schema_version = str(manifest.get("schema_version", ""))
    _expect(
        schema_version
        in {
            RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1,
            RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2,
        },
        "source_manifest_schema_mismatch",
        schema_version,
    )
    return schema_version


def _validate_checksum_chain(
    inputs: ReservedSeedInterventionAuditInputs,
    paths: Mapping[str, Path],
    snapshot: Mapping[str, str],
) -> dict[str, str]:
    _expect_equal(
        snapshot[_CHECKSUMS_FILE],
        inputs.expected_checksums_sha256,
        "checksums_out_of_band_sha256_mismatch",
        _CHECKSUMS_FILE,
    )
    _expect_equal(
        snapshot[_SOURCE_MANIFEST_FILE],
        inputs.expected_source_manifest_sha256,
        "source_manifest_out_of_band_sha256_mismatch",
        _SOURCE_MANIFEST_FILE,
    )
    checksums = _parse_sha256sums(paths[_CHECKSUMS_FILE])
    _expect_equal(
        set(checksums),
        set(_CHECKSUM_MEMBER_FILES),
        "sha256sums_inventory_mismatch",
        "SHA256SUMS must bind exactly the five producer artifacts",
    )
    for name, expected in checksums.items():
        _expect_equal(
            snapshot[name],
            expected,
            "sha256sums_member_mismatch",
            name,
        )
    return checksums


def _audit_source_lineage(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_source_commit: str,
) -> tuple[dict[str, Any], dict[int, Mapping[str, Any]]]:
    _expect_equal(
        len(records),
        len(EXPECTED_RESERVED_SEEDS),
        "source_lineage_count_mismatch",
        "exactly 20 records are required",
    )
    seeds = [_integer(record.get("seed"), "lineage seed") for record in records]
    _expect_equal(
        seeds,
        list(EXPECTED_RESERVED_SEEDS),
        "source_lineage_seed_catalog_mismatch",
        repr(seeds),
    )
    seen_episode_ids: set[str] = set()
    for record in records:
        seed = _integer(record.get("seed"), "lineage seed")
        _expect_equal(
            record.get("schema_version"),
            RESERVED_SEED_LINEAGE_SCHEMA_VERSION,
            "source_lineage_schema_mismatch",
            str(seed),
        )
        _expect_equal(
            record.get("source_git_commit"),
            expected_source_commit,
            "source_lineage_commit_mismatch",
            str(seed),
        )
        _expect(
            record.get("source_repository_dirty") is False,
            "dirty_source_episode",
            str(seed),
        )
        _expect(record.get("finite_state") is True, "nonfinite_source_episode", str(seed))
        _expect_equal(
            _integer(record.get("online_truth_use_count"), "online truth use"),
            0,
            "online_truth_use_detected",
            str(seed),
        )
        for name in (
            "control_and_treatment_share_source_episode",
            "control_and_treatment_share_sensor_random_stream",
            "control_and_treatment_share_communication_schedule",
            "control_and_treatment_share_fault_schedule",
        ):
            _expect(record.get(name) is True, "source_pair_flag_false", f"{seed}:{name}")
        _expect_equal(record.get("scenario_id"), "nominal_5v5", "scenario_id_mismatch", str(seed))
        _expect_equal(
            record.get("scenario_version"),
            "nominal-5v5-v1",
            "scenario_version_mismatch",
            str(seed),
        )
        episode_id = str(record.get("source_episode_id", ""))
        _expect(episode_id != "", "source_episode_id_missing", str(seed))
        _expect(episode_id not in seen_episode_ids, "duplicate_source_episode_id", episode_id)
        seen_episode_ids.add(episode_id)
        for name in (
            "communication_schedule_sha256",
            "d3_input_snapshot_sha256",
            "d4_region_snapshot_lineage_sha256",
            "fault_schedule_sha256",
            "initial_state_sha256",
            "scenario_config_sha256",
            "source_episode_manifest_sha256",
            "source_summary_sha256",
        ):
            _require_sha256(record.get(name), f"lineage {seed}:{name}")

    summary = {
        "record_count": len(records),
        "unique_source_episode_count": len(seen_episode_ids),
        "reserved_seeds": seeds,
        "source_git_commits": [expected_source_commit],
        "dirty_source_episode_count": 0,
        "nonfinite_source_episode_count": 0,
        "online_truth_use_count": 0,
        "same_source_episode_count": len(records),
        "same_sensor_random_stream_count": len(records),
        "same_communication_schedule_count": len(records),
        "same_fault_schedule_count": len(records),
    }
    return summary, {int(record["seed"]): record for record in records}


def _audit_d3(
    payload: Mapping[str, Any],
    *,
    lineage_by_seed: Mapping[int, Mapping[str, Any]],
    inputs: ReservedSeedInterventionAuditInputs,
    source_schema_version: str = (
        RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1
    ),
) -> dict[str, Any]:
    _expect_equal(
        payload.get("schema_version"),
        "d3.offline-paired-intervention-execution.v1",
        "d3_schema_mismatch",
        "D3 execution artifact",
    )
    _expect_equal(
        payload.get("intervention_scope"),
        "offline_simulation_intervention_arm",
        "d3_intervention_scope_mismatch",
        "D3 execution artifact",
    )
    _expect_equal(
        _mapping(payload, "evidence_availability"),
        {"causal": False, "counterfactual": False, "outcome": False, "runtime_ack": False},
        "d3_top_level_availability_mismatch",
        "D3 must not claim outcomes",
    )
    admission = _mapping(payload, "admission")
    _expect_equal(
        admission,
        {
            "online_assist_enabled": False,
            "online_authority_enabled": False,
            "ppo_enabled": False,
            "rule_fallback_enabled": True,
            "runtime_publication_allowed": False,
        },
        "d3_admission_mismatch",
        "D3 authority must remain disabled",
    )
    bundle = _mapping(payload, "bundle")
    _expect(bundle.get("loaded") is True, "d3_bundle_not_loaded", "D3 bundle")
    _expect_equal(
        bundle.get("manifest_sha256"),
        inputs.expected_d3_bundle_manifest_sha256,
        "d3_bundle_manifest_binding_mismatch",
        "D3 bundle",
    )
    _expect_equal(
        bundle.get("state_dict_sha256"),
        inputs.expected_d3_bundle_state_sha256,
        "d3_bundle_state_binding_mismatch",
        "D3 bundle",
    )

    paired_report = _mapping(payload, "paired_evaluator_report")
    paired_report_sha256 = _require_sha256(
        payload.get("paired_evaluator_report_sha256"),
        "D3 paired evaluator report",
    )
    _expect_equal(
        _producer_json_sha256(paired_report),
        paired_report_sha256,
        "d3_paired_report_internal_sha256_mismatch",
        "paired_evaluator_report",
    )
    manifest = _mapping(payload, "manifest")
    specification = _mapping(manifest, "specification")
    specification_sha256 = _producer_json_sha256(specification)
    _expect_equal(
        payload.get("specification_sha256"),
        specification_sha256,
        "d3_specification_sha256_mismatch",
        "top-level specification",
    )
    _expect_equal(
        manifest.get("specification_sha256"),
        specification_sha256,
        "d3_manifest_specification_sha256_mismatch",
        "manifest specification",
    )
    unsigned_manifest = dict(manifest)
    claimed_manifest_sha = unsigned_manifest.pop("manifest_sha256", None)
    _expect_equal(
        claimed_manifest_sha,
        _producer_json_sha256(unsigned_manifest),
        "d3_internal_manifest_sha256_mismatch",
        "D3 manifest",
    )
    _validate_d3_manifest_availability(
        manifest,
        source_schema_version=source_schema_version,
    )

    pairs = _sequence(specification, "pairs")
    _expect_equal(len(pairs), 20, "d3_pair_count_mismatch", str(len(pairs)))
    _expect_equal(
        [_integer(pair.get("seed"), "D3 pair seed") for pair in pairs],
        list(EXPECTED_RESERVED_SEEDS),
        "d3_pair_seed_catalog_mismatch",
        "D3 specification pairs",
    )
    _expect_equal(
        list(_sequence(specification, "reserved_seeds")),
        list(EXPECTED_RESERVED_SEEDS),
        "d3_reserved_seed_catalog_mismatch",
        "D3 specification",
    )

    arms = _sequence(payload, "arms")
    _expect_equal(len(arms), 40, "d3_arm_count_mismatch", str(len(arms)))
    arm_by_key: dict[tuple[int, str], Mapping[str, Any]] = {}
    for raw_arm in arms:
        arm = _as_mapping(raw_arm, "D3 arm")
        arm_spec = _mapping(arm, "arm_specification")
        key = (
            _integer(arm_spec.get("seed"), "D3 arm seed"),
            str(arm_spec.get("arm_kind", "")),
        )
        _expect(key not in arm_by_key, "d3_duplicate_arm", repr(key))
        arm_by_key[key] = arm
    expected_keys = {
        (seed, kind)
        for seed in EXPECTED_RESERVED_SEEDS
        for kind in ("control", "treatment")
    }
    _expect_equal(set(arm_by_key), expected_keys, "d3_arm_catalog_mismatch", "D3 arms")
    _expect_equal(
        list(_sequence(manifest, "execution_receipts")),
        [_mapping(_as_mapping(arm, "D3 arm"), "receipt") for arm in arms],
        "d3_manifest_receipt_copy_mismatch",
        "manifest receipts must equal arm receipts",
    )

    control_statuses: Counter[str] = Counter()
    treatment_fallbacks: Counter[str] = Counter()
    treatment_latencies: list[float] = []
    applied_count = fallback_count = 0
    pair_identity_count = bundle_identity_count = 0
    receipt_hash_count = plan_hash_count = 0
    assignment_identity_count = 0
    for pair_raw in pairs:
        pair = _as_mapping(pair_raw, "D3 pair")
        seed = _integer(pair.get("seed"), "D3 pair seed")
        pair_id = str(pair.get("pair_id", ""))
        _expect(pair_id != "", "d3_pair_id_missing", str(seed))
        control_spec = _mapping(pair, "control")
        treatment_spec = _mapping(pair, "treatment")
        _expect_equal(control_spec.get("seed"), seed, "d3_control_seed_mismatch", str(seed))
        _expect_equal(treatment_spec.get("seed"), seed, "d3_treatment_seed_mismatch", str(seed))
        _expect_equal(control_spec.get("arm_kind"), "control", "d3_control_kind_mismatch", str(seed))
        _expect_equal(treatment_spec.get("arm_kind"), "treatment", "d3_treatment_kind_mismatch", str(seed))
        _expect_equal(
            _without_keys(control_spec, _D3_PAIR_DIFFERENCE_FIELDS),
            _without_keys(treatment_spec, _D3_PAIR_DIFFERENCE_FIELDS),
            "d3_pair_input_identity_mismatch",
            str(seed),
        )
        _expect(control_spec.get("learning_cost_intervention_enabled") is False, "d3_control_intervention_enabled", str(seed))
        _expect(treatment_spec.get("learning_cost_intervention_enabled") is True, "d3_treatment_intervention_disabled", str(seed))
        lineage = lineage_by_seed[seed]
        for spec in (control_spec, treatment_spec):
            _expect(spec.get("d3_bundle_frozen") is True, "d3_bundle_not_frozen", str(seed))
            _expect_equal(
                spec.get("d3_bundle_sha256"),
                inputs.expected_d3_bundle_manifest_sha256,
                "d3_arm_bundle_binding_mismatch",
                str(seed),
            )
            _expect_equal(spec.get("initial_world_state_sha256"), lineage["initial_state_sha256"], "d3_initial_state_binding_mismatch", str(seed))
            _expect_equal(spec.get("observation_input_snapshot_sha256"), lineage["d3_input_snapshot_sha256"], "d3_input_snapshot_binding_mismatch", str(seed))
            _expect_equal(spec.get("scenario_config_sha256"), lineage["scenario_config_sha256"], "d3_scenario_binding_mismatch", str(seed))
            _expect(spec.get("online_assist_enabled") is False, "d3_online_assist_enabled", str(seed))
            _expect(spec.get("online_authority_enabled") is False, "d3_online_authority_enabled", str(seed))
            _expect(spec.get("ppo_enabled") is False, "d3_ppo_enabled", str(seed))
            _expect(spec.get("rule_fallback_enabled") is True, "d3_rule_fallback_disabled", str(seed))
            if (
                source_schema_version
                == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
            ):
                _expect_equal(
                    spec.get("safety_shell_version"),
                    EXPECTED_D3_SAFETY_SHELL_VERSION_V2,
                    "d3_safety_shell_version_mismatch",
                    f"{seed}:{spec.get('arm_kind')}",
                )
                _expect_equal(
                    spec.get("safety_shell_config_sha256"),
                    EXPECTED_D3_SAFETY_SHELL_CONFIG_SHA256_V2,
                    "d3_safety_shell_config_sha256_mismatch",
                    f"{seed}:{spec.get('arm_kind')}",
                )
            bundle_identity_count += 1

        control_arm = arm_by_key[(seed, "control")]
        treatment_arm = arm_by_key[(seed, "treatment")]
        _expect_equal(_mapping(control_arm, "arm_specification"), control_spec, "d3_control_spec_copy_mismatch", str(seed))
        _expect_equal(_mapping(treatment_arm, "arm_specification"), treatment_spec, "d3_treatment_spec_copy_mismatch", str(seed))
        control_receipt = _validate_d3_arm(
            control_arm,
            expected_kind="control",
            expected_pair_id=pair_id,
            paired_report_sha256=paired_report_sha256,
            source_schema_version=source_schema_version,
        )
        treatment_receipt = _validate_d3_arm(
            treatment_arm,
            expected_kind="treatment",
            expected_pair_id=pair_id,
            paired_report_sha256=paired_report_sha256,
            source_schema_version=source_schema_version,
        )
        receipt_hash_count += 2
        plan_hash_count += 2
        for name in (
            "input_snapshot_sha256",
            "action_mask_sha256",
            "rule_cost_matrix_sha256",
            "paired_evaluator_report_sha256",
            "source_plan_version",
            "current_plan_version",
            "expected_previous_plan_version",
        ):
            _expect_equal(
                control_receipt.get(name),
                treatment_receipt.get(name),
                "d3_receipt_pair_identity_mismatch",
                f"{seed}:{name}",
            )
        _expect_equal(
            control_receipt.get("input_snapshot_sha256"),
            lineage["d3_input_snapshot_sha256"],
            "d3_receipt_lineage_binding_mismatch",
            str(seed),
        )
        pair_identity_count += 1
        if (
            source_schema_version
            == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
        ):
            _expect_equal(
                _d3_assignment_signature(_mapping(control_arm, "plan")),
                _d3_assignment_signature(_mapping(treatment_arm, "plan")),
                "d3_v2_selected_assignment_identity_mismatch",
                str(seed),
            )
            assignment_identity_count += 1

        control_statuses[str(control_receipt.get("hysteresis_decision", ""))] += 1
        fallback_reason = treatment_receipt.get("fallback_reason")
        if fallback_reason is not None:
            treatment_fallbacks[str(fallback_reason)] += 1
        applied_count += int(treatment_receipt.get("learning_cost_applied") is True)
        fallback_count += int(treatment_receipt.get("rule_fallback_applied") is True)
        treatment_latencies.append(
            _number(
                treatment_receipt.get("inference_elapsed_ms"),
                "D3 treatment inference latency",
            )
        )

    expected_statuses = {
        "held_by_hysteresis": 3,
        "replan_ack_no_change": 2,
        "unchanged": 15,
    }
    _expect_equal(dict(sorted(control_statuses.items())), expected_statuses, "d3_control_status_summary_mismatch", "D3 control decisions")
    is_v2 = (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    expected_fallbacks = {} if is_v2 else {"out_of_distribution": 20}
    expected_applied_count = 20 if is_v2 else 0
    expected_fallback_count = 0 if is_v2 else 20
    _expect_equal(
        dict(treatment_fallbacks),
        expected_fallbacks,
        "d3_fallback_summary_mismatch",
        "D3 treatment",
    )
    _expect_equal(
        applied_count,
        expected_applied_count,
        "d3_treatment_applied_count_mismatch",
        str(applied_count),
    )
    _expect_equal(
        fallback_count,
        expected_fallback_count,
        "d3_rule_fallback_count_mismatch",
        str(fallback_count),
    )

    d3_result: dict[str, Any] = {
        "execution_receipts_available": True,
        "execution_receipt_count": 40,
        "arm_count": 40,
        "control_arm_count": 20,
        "treatment_arm_count": 20,
        "pair_input_identity_verified_count": pair_identity_count,
        "bundle_identity_verified_arm_count": bundle_identity_count,
        "arm_spec_sha256_verified_count": receipt_hash_count,
        "output_plan_sha256_verified_count": plan_hash_count,
        "bundle_binding": {
            "manifest_sha256": inputs.expected_d3_bundle_manifest_sha256,
            "state_sha256": inputs.expected_d3_bundle_state_sha256,
            "bundle_files_rehashed": False,
            "binding_verified": True,
        },
        "control_decision_counts": expected_statuses,
        "treatment_applied_count": applied_count,
        "treatment_rule_fallback_count": fallback_count,
        "treatment_fallback_reason_counts": dict(sorted(treatment_fallbacks.items())),
        "treatment_inference_latency_ms": _latency_summary(
            treatment_latencies,
            p95_method="linear" if is_v2 else "nearest_rank",
        ),
        "paired_outcome": _unavailable("d3_physical_outcome_not_present"),
        "paired_effect": _unavailable("d3_paired_physical_effect_not_available"),
    }
    if is_v2:
        d3_result["safety_shell"] = {
            "version": EXPECTED_D3_SAFETY_SHELL_VERSION_V2,
            "config_sha256": EXPECTED_D3_SAFETY_SHELL_CONFIG_SHA256_V2,
            "verified_arm_count": 40,
        }
        d3_result["selected_assignment_identity_verified_pair_count"] = (
            assignment_identity_count
        )
        d3_result["offline_assignment_comparison"] = (
            _audit_d3_v2_offline_assignment_comparison(
                paired_report,
                arm_by_key=arm_by_key,
                inputs=inputs,
            )
        )
    return d3_result


def _d3_assignment_signature(plan: Mapping[str, Any]) -> dict[str, Any]:
    assignments = []
    for raw_assignment in _sequence(plan, "assignments"):
        assignment = _as_mapping(raw_assignment, "D3 plan assignment")
        assignments.append(
            (
                str(assignment.get("target_id", "")),
                str(assignment.get("resource_id", "")),
                str(assignment.get("member_role", "")),
                str(assignment.get("coalition_id", "")),
            )
        )
    return {
        "assignments": sorted(assignments),
        "unassigned_target_ids": sorted(
            str(item) for item in _sequence(plan, "unassigned_target_ids")
        ),
    }


def _audit_d3_v2_offline_assignment_comparison(
    report: Mapping[str, Any],
    *,
    arm_by_key: Mapping[tuple[int, str], Mapping[str, Any]],
    inputs: ReservedSeedInterventionAuditInputs,
) -> dict[str, Any]:
    _expect_equal(
        report.get("schema_version"),
        "d3_shadow_paired_evaluation_v2",
        "d3_v2_paired_report_schema_mismatch",
        "paired evaluator report",
    )
    _expect_equal(
        report.get("cost_basis"),
        "rule_cost_matrix_v1",
        "d3_v2_comparison_cost_basis_mismatch",
        "paired evaluator report",
    )
    _expect_equal(
        report.get("model_state_dict_sha256"),
        inputs.expected_d3_bundle_state_sha256,
        "d3_v2_paired_report_state_binding_mismatch",
        "paired evaluator report",
    )
    _require_sha256(
        report.get("dataset_frames_sha256"),
        "D3 v2 paired report dataset frames",
    )
    _require_sha256(report.get("split_hash"), "D3 v2 paired report split")
    frames = _sequence(report, "frames")
    _expect_equal(
        len(frames),
        len(EXPECTED_RESERVED_SEEDS),
        "d3_v2_comparison_frame_count_mismatch",
        "paired evaluator frames",
    )
    _expect_equal(
        report.get("frame_count"),
        len(frames),
        "d3_v2_reported_frame_count_mismatch",
        "paired evaluator report",
    )
    _expect_equal(
        [_integer(_as_mapping(item, "D3 v2 frame").get("seed"), "D3 v2 frame seed") for item in frames],
        list(EXPECTED_RESERVED_SEEDS),
        "d3_v2_comparison_seed_catalog_mismatch",
        "paired evaluator frames",
    )

    rule_costs: list[float] = []
    treatment_costs: list[float] = []
    latencies: list[float] = []
    rule_high_threat: list[int] = []
    treatment_high_threat: list[int] = []
    rule_duplicates: list[int] = []
    treatment_duplicates: list[int] = []
    rule_hard: list[int] = []
    treatment_hard: list[int] = []
    rule_churn: list[int] = []
    treatment_churn: list[int] = []
    fallback_reasons: Counter[str] = Counter()
    expected_per_seed: dict[str, Any] = {}
    for raw_frame in frames:
        frame = _as_mapping(raw_frame, "D3 v2 frame")
        seed = _integer(frame.get("seed"), "D3 v2 frame seed")
        _expect_equal(
            frame.get("episode"),
            f"d3-reserved-pair-{seed}",
            "d3_v2_comparison_episode_mismatch",
            str(seed),
        )
        _expect_equal(
            frame.get("frame_index"),
            0,
            "d3_v2_comparison_frame_index_mismatch",
            str(seed),
        )
        _expect_equal(
            frame.get("scenario_version"),
            "nominal-5v5-v1",
            "d3_v2_comparison_scenario_mismatch",
            str(seed),
        )
        control_plan = _mapping(arm_by_key[(seed, "control")], "plan")
        treatment_plan = _mapping(arm_by_key[(seed, "treatment")], "plan")
        treatment_receipt = _mapping(
            arm_by_key[(seed, "treatment")],
            "receipt",
        )
        rule_cost = _number(
            frame.get("rule_assignment_cost"),
            "D3 v2 rule assignment cost",
        )
        treatment_cost = _number(
            frame.get("shadow_assignment_cost"),
            "D3 v2 treatment assignment cost",
        )
        _expect_equal(
            rule_cost,
            _number(control_plan.get("total_cost"), "D3 control plan cost"),
            "d3_v2_rule_cost_plan_mismatch",
            str(seed),
        )
        _expect_equal(
            treatment_cost,
            rule_cost,
            "d3_v2_treatment_rule_basis_cost_mismatch",
            str(seed),
        )
        _expect_equal(
            _d3_assignment_signature(control_plan),
            _d3_assignment_signature(treatment_plan),
            "d3_v2_comparison_assignment_identity_mismatch",
            str(seed),
        )
        latency = _number(
            frame.get("inference_elapsed_ms"),
            "D3 v2 comparison inference latency",
        )
        _expect_equal(
            latency,
            _number(
                treatment_receipt.get("inference_elapsed_ms"),
                "D3 v2 treatment receipt latency",
            ),
            "d3_v2_comparison_latency_receipt_mismatch",
            str(seed),
        )
        fallback_reason = frame.get("fallback_reason")
        _expect_equal(
            fallback_reason,
            treatment_receipt.get("fallback_reason"),
            "d3_v2_comparison_fallback_receipt_mismatch",
            str(seed),
        )
        if fallback_reason is not None:
            fallback_reasons[str(fallback_reason)] += 1

        metrics = {
            "rule_high_threat_unmet": rule_high_threat,
            "shadow_high_threat_unmet": treatment_high_threat,
            "rule_duplicate_count": rule_duplicates,
            "shadow_duplicate_count": treatment_duplicates,
            "rule_hard_violation_count": rule_hard,
            "shadow_hard_violation_count": treatment_hard,
            "rule_churn": rule_churn,
            "shadow_churn": treatment_churn,
        }
        for name, destination in metrics.items():
            destination.append(_integer(frame.get(name), f"D3 v2 frame {name}"))
        rule_costs.append(rule_cost)
        treatment_costs.append(treatment_cost)
        latencies.append(latency)
        expected_per_seed[str(seed)] = {
            "fallback_frame_count": int(fallback_reason is not None),
            "frame_count": 1,
            "rule_assignment_cost_mean": rule_cost,
            "rule_churn_mean": rule_churn[-1],
            "rule_high_threat_unmet_total": rule_high_threat[-1],
            "shadow_assignment_cost_mean": treatment_cost,
            "shadow_churn_mean": treatment_churn[-1],
            "shadow_high_threat_unmet_total": treatment_high_threat[-1],
        }

    assignment_cost = {
        "rule_mean": math.fsum(rule_costs) / len(rule_costs),
        "shadow_mean": math.fsum(treatment_costs) / len(treatment_costs),
    }
    high_threat = {
        "rule_total": sum(rule_high_threat),
        "shadow_total": sum(treatment_high_threat),
    }
    duplicate_hard = {
        "rule_duplicate_count": sum(rule_duplicates),
        "rule_hard_violation_count": sum(rule_hard),
        "shadow_duplicate_count": sum(treatment_duplicates),
        "shadow_hard_violation_count": sum(treatment_hard),
    }
    churn = {
        "rule_mean": math.fsum(rule_churn) / len(rule_churn),
        "shadow_mean": math.fsum(treatment_churn) / len(treatment_churn),
    }
    inference_ms = {
        "p50": _percentile_linear(latencies, 0.50),
        "p95": _percentile_linear(latencies, 0.95),
    }
    _expect_numeric_mapping_close(
        _mapping(report, "assignment_cost"),
        assignment_cost,
        "d3_v2_assignment_cost_summary_mismatch",
        "paired evaluator report",
    )
    for field, expected in (
        ("high_threat_unmet", high_threat),
        ("duplicate_hard_violation", duplicate_hard),
        ("churn", churn),
        ("inference_ms", inference_ms),
        ("fallback_reasons", dict(sorted(fallback_reasons.items()))),
        ("per_seed_metrics", expected_per_seed),
    ):
        _expect_equal(
            report.get(field),
            expected,
            f"d3_v2_{field}_summary_mismatch",
            "paired evaluator report",
        )
    _expect(report.get("rule_matrix_unchanged") is True, "d3_v2_rule_matrix_changed", "paired evaluator report")
    _expect_equal(high_threat["rule_total"], 0, "d3_v2_rule_high_threat_unmet", "paired evaluator report")
    _expect_equal(high_threat["shadow_total"], 0, "d3_v2_treatment_high_threat_unmet", "paired evaluator report")
    _expect_equal(sum(duplicate_hard.values()), 0, "d3_v2_duplicate_or_hard_violation", "paired evaluator report")
    _expect_equal(churn, {"rule_mean": 0.0, "shadow_mean": 0.0}, "d3_v2_churn_nonzero", "paired evaluator report")
    promotion = _mapping(report, "promotion_manifest")
    _expect(promotion.get("promotion_recommended") is False, "d3_v2_promotion_claim", "paired evaluator report")
    _expect_equal(promotion.get("promotion_status"), "unavailable", "d3_v2_promotion_status_mismatch", "paired evaluator report")

    reported_assignment_cost = _mapping(report, "assignment_cost")
    return {
        "available": True,
        "status": "available",
        "value": True,
        "reason": None,
        "scope": "same_frame_offline_assignment_only",
        "frame_count": len(frames),
        "cost_basis": "rule_cost_matrix_v1",
        "assignment_cost": {
            "control_rule_mean": reported_assignment_cost["rule_mean"],
            "treatment_assignment_mean": reported_assignment_cost[
                "shadow_mean"
            ],
        },
        "high_threat_unmet": {
            "control_total": high_threat["rule_total"],
            "treatment_total": high_threat["shadow_total"],
        },
        "duplicate_count": {
            "control_total": duplicate_hard["rule_duplicate_count"],
            "treatment_total": duplicate_hard["shadow_duplicate_count"],
        },
        "hard_violation_count": {
            "control_total": duplicate_hard["rule_hard_violation_count"],
            "treatment_total": duplicate_hard["shadow_hard_violation_count"],
        },
        "churn_mean": {
            "control": churn["rule_mean"],
            "treatment": churn["shadow_mean"],
        },
        "inference_latency_ms": _latency_summary(
            latencies,
            p95_method="linear",
        ),
        "selected_assignment_identity_match_count": len(frames),
        "physical_outcome_available": False,
        "paired_physical_effect_available": False,
        "candidate_policy_effectiveness_proven": False,
    }


def _validate_d3_arm(
    arm: Mapping[str, Any],
    *,
    expected_kind: str,
    expected_pair_id: str,
    paired_report_sha256: str,
    source_schema_version: str,
) -> Mapping[str, Any]:
    spec = _mapping(arm, "arm_specification")
    receipt = _mapping(arm, "receipt")
    seed = _integer(spec.get("seed"), "D3 arm seed")
    _expect_equal(receipt.get("seed"), seed, "d3_receipt_seed_mismatch", str(seed))
    _expect_equal(receipt.get("arm_kind"), expected_kind, "d3_receipt_kind_mismatch", str(seed))
    _expect_equal(receipt.get("pair_id"), expected_pair_id, "d3_receipt_pair_id_mismatch", str(seed))
    _expect_equal(
        receipt.get("arm_spec_sha256"),
        _producer_json_sha256(spec),
        "d3_arm_spec_sha256_mismatch",
        f"{seed}:{expected_kind}",
    )
    _expect_equal(receipt.get("input_snapshot_sha256"), spec.get("observation_input_snapshot_sha256"), "d3_receipt_input_sha256_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(receipt.get("paired_evaluator_report_sha256"), paired_report_sha256, "d3_receipt_paired_report_sha256_mismatch", f"{seed}:{expected_kind}")
    plan = _mapping(arm, "plan")
    _expect_equal(receipt.get("output_plan_payload_sha256"), _producer_json_sha256(plan), "d3_output_plan_sha256_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(receipt.get("output_plan_id"), plan.get("plan_id"), "d3_output_plan_id_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(receipt.get("output_plan_version"), plan.get("version"), "d3_output_plan_version_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(arm.get("fallback_reason"), receipt.get("fallback_reason"), "d3_arm_fallback_copy_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(arm.get("learning_cost_applied"), receipt.get("learning_cost_applied"), "d3_arm_application_copy_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(arm.get("rule_fallback_applied"), receipt.get("rule_fallback_applied"), "d3_arm_fallback_flag_copy_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(_number(arm.get("inference_elapsed_ms"), "D3 arm latency"), _number(receipt.get("inference_elapsed_ms"), "D3 receipt latency"), "d3_arm_latency_copy_mismatch", f"{seed}:{expected_kind}")
    effective_matrix_sha256 = _require_sha256(
        arm.get("effective_matrix_sha256"),
        "D3 effective matrix",
    )
    if (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
        and expected_kind == "treatment"
    ):
        _expect(
            effective_matrix_sha256 != receipt.get("rule_cost_matrix_sha256"),
            "d3_v2_effective_matrix_not_intervened",
            str(seed),
        )
    else:
        _expect_equal(
            effective_matrix_sha256,
            receipt.get("rule_cost_matrix_sha256"),
            "d3_effective_matrix_binding_mismatch",
            f"{seed}:{expected_kind}",
        )
    _expect(receipt.get("isolated_simulation") is True, "d3_arm_not_isolated", f"{seed}:{expected_kind}")
    if (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    ):
        _expect_equal(
            receipt.get("schema_version"),
            "d3.paired-intervention-execution-receipt.v1",
            "d3_v2_receipt_schema_mismatch",
            f"{seed}:{expected_kind}",
        )
        _expect_equal(
            receipt.get("paired_evaluator_schema_version"),
            "d3_shadow_paired_evaluation_v2",
            "d3_v2_paired_evaluator_schema_mismatch",
            f"{seed}:{expected_kind}",
        )
    for name in (
        "capacity_gate_enforced",
        "deterministic_action_mask_enforced",
        "hysteresis_gate_enforced",
        "reachability_gate_enforced",
        "rule_fallback_available",
        "safety_gate_enforced",
        "version_gate_enforced",
    ):
        _expect(receipt.get(name) is True, "d3_safety_gate_not_enforced", f"{seed}:{expected_kind}:{name}")
    for name in (
        "global_track_id_rewrite_count",
        "nonfinite_value_count",
        "online_label_key_count",
    ):
        _expect_equal(_integer(receipt.get(name), f"D3 receipt {name}"), 0, "d3_receipt_safety_count_nonzero", f"{seed}:{expected_kind}:{name}")
    _require_sha256(receipt.get("action_mask_sha256"), "D3 action mask")
    _require_sha256(receipt.get("rule_cost_matrix_sha256"), "D3 rule matrix")
    if expected_kind == "control":
        _expect(receipt.get("fallback_reason") is None, "d3_control_fallback_reason_present", str(seed))
        _expect(receipt.get("learning_cost_applied") is False, "d3_control_learning_applied", str(seed))
        _expect(receipt.get("rule_fallback_applied") is False, "d3_control_rule_fallback", str(seed))
    elif (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1
    ):
        _expect_equal(receipt.get("fallback_reason"), "out_of_distribution", "d3_treatment_fallback_reason_mismatch", str(seed))
        _expect(receipt.get("learning_cost_applied") is False, "d3_treatment_learning_applied", str(seed))
        _expect(receipt.get("rule_fallback_applied") is True, "d3_treatment_rule_fallback_missing", str(seed))
    else:
        _expect(
            receipt.get("fallback_reason") is None,
            "d3_v2_treatment_fallback_reason_present",
            str(seed),
        )
        _expect(
            receipt.get("learning_cost_applied") is True,
            "d3_v2_treatment_learning_not_applied",
            str(seed),
        )
        _expect(
            receipt.get("rule_fallback_applied") is False,
            "d3_v2_treatment_rule_fallback_unexpected",
            str(seed),
        )
    return receipt


def _validate_d3_manifest_availability(
    manifest: Mapping[str, Any],
    *,
    source_schema_version: str,
) -> None:
    audit = _mapping(manifest, "audit")
    for name in (
        "d3_computed_causal_attribution",
        "d3_computed_counterfactual",
        "d3_computed_outcome",
    ):
        _expect(audit.get(name) is False, "d3_manifest_outcome_claim", name)
    _expect(audit.get("fail_closed") is True, "d3_manifest_fail_closed_false", "audit")
    _expect_equal(audit.get("paired_arm_count"), 40, "d3_manifest_arm_count_mismatch", "audit")
    _expect_equal(audit.get("reserved_seed_count"), 20, "d3_manifest_seed_count_mismatch", "audit")
    availability = _mapping(manifest, "availability")
    for name in ("causal", "counterfactual", "outcome", "runtime_ack"):
        item = _mapping(availability, name)
        _expect(item.get("available") is False, "d3_manifest_availability_claim", name)
        _expect_equal(item.get("status"), "unavailable", "d3_manifest_availability_status", name)
        _expect(item.get("value") is None, "d3_manifest_unavailable_value_nonnull", name)
    paired_input = _mapping(availability, "paired_input_equivalence")
    _expect(paired_input.get("available") is True and paired_input.get("value") is True, "d3_manifest_pair_input_unavailable", "paired_input_equivalence")
    applied = _mapping(availability, "treatment_safely_applied_in_isolated_simulation")
    is_v2 = (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    _expect(
        applied.get("available") is True
        and applied.get("value") is is_v2,
        "d3_manifest_treatment_application_claim",
        "treatment_safely_applied",
    )
    _expect_equal(
        applied.get("applied_seed_count"),
        20 if is_v2 else 0,
        "d3_manifest_applied_count_mismatch",
        "availability",
    )
    _expect_equal(
        applied.get("fallback_seed_count"),
        0 if is_v2 else 20,
        "d3_manifest_fallback_count_mismatch",
        "availability",
    )


def _audit_d4(
    payload: Mapping[str, Any],
    *,
    lineage_by_seed: Mapping[int, Mapping[str, Any]],
    inputs: ReservedSeedInterventionAuditInputs,
    source_schema_version: str = (
        RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V1
    ),
) -> dict[str, Any]:
    _expect_equal(payload.get("schema_version"), source_schema_version, "d4_schema_mismatch", "D4 execution artifact")
    _expect_equal(payload.get("execution_scope"), "offline_simulation_intervention_arm", "d4_execution_scope_mismatch", "D4 execution artifact")
    _expect_equal(
        _mapping(payload, "evidence_availability"),
        {"causal": False, "counterfactual": False, "physical_outcome": False, "runtime_ack": False},
        "d4_top_level_availability_mismatch",
        "D4 must not claim outcomes",
    )
    _expect_equal(
        _mapping(payload, "admission"),
        {"assist": False, "authority": False, "ppo": False, "rule_fallback": True, "runtime_publication_allowed": False},
        "d4_admission_mismatch",
        "D4 authority must remain disabled",
    )
    loader = _mapping(payload, "candidate_loader")
    _expect(loader.get("ready") is True, "d4_candidate_loader_not_ready", "candidate loader")
    _expect_equal(loader.get("load_rejection_reasons"), [], "d4_candidate_loader_rejected", "candidate loader")

    manifest = _mapping(payload, "manifest")
    is_v2 = (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    for name in (
        "causal_effect_available",
        "counterfactual_available",
        "d6_outcome_sidecar_attached",
        "formal_twenty_seed_performance_completed",
        "observed_outcome_available",
        "paired_non_degradation_available",
        "performance_claim_allowed",
    ):
        _expect(manifest.get(name) is False, "d4_manifest_outcome_claim", name)
    specification = _mapping(manifest, "specification")
    minimum_confidence: float | None = None
    latency_limit_ms: float | None = None
    if is_v2:
        _expect_equal(
            manifest.get("schema"),
            "d4-region-resource-paired-intervention-manifest-v1",
            "d4_v2_manifest_schema_mismatch",
            "D4 manifest",
        )
        _expect_equal(
            specification.get("schema"),
            "d4-region-resource-paired-intervention-spec-v1",
            "d4_v2_specification_schema_mismatch",
            "D4 specification",
        )
        thresholds = _mapping(specification, "thresholds")
        minimum_confidence = _number(
            thresholds.get("minimum_confidence"),
            "D4 minimum confidence",
        )
        latency_limit_ms = 1000.0 * _number(
            thresholds.get("inference_timeout_s"),
            "D4 inference timeout",
        )
        _expect_equal(
            minimum_confidence,
            0.6,
            "d4_v2_minimum_confidence_mismatch",
            "D4 specification",
        )
        _expect_equal(
            latency_limit_ms,
            50.0,
            "d4_v2_latency_limit_mismatch",
            "D4 specification",
        )
    unsigned_specification = dict(specification)
    specification_id = str(unsigned_specification.pop("specification_id", ""))
    _expect_equal(
        specification_id,
        f"d4-rr-paired-spec-{_producer_json_sha256(unsigned_specification)}",
        "d4_specification_id_mismatch",
        "D4 specification",
    )
    specification_sha256 = _producer_json_sha256(specification)
    candidate_bundle = _mapping(specification, "candidate_bundle")
    _expect_equal(candidate_bundle.get("bundle_manifest_sha256"), inputs.expected_d4_bundle_manifest_sha256, "d4_bundle_manifest_binding_mismatch", "D4 bundle")
    _expect_equal(candidate_bundle.get("model_state_sha256"), inputs.expected_d4_bundle_state_sha256, "d4_bundle_state_binding_mismatch", "D4 bundle")
    _expect_equal(list(_sequence(specification, "reserved_seeds")), list(EXPECTED_RESERVED_SEEDS), "d4_reserved_seed_catalog_mismatch", "D4 specification")
    for name in ("assist_enabled", "authority_enabled", "ppo_enabled"):
        _expect(specification.get(name) is False, "d4_specification_authority_enabled", name)
    _expect(specification.get("rule_fallback_enabled") is True, "d4_specification_rule_fallback_disabled", "D4 specification")

    arm_specs = _sequence(specification, "arms")
    evidence = _sequence(manifest, "arm_evidence")
    _expect_equal(len(arm_specs), 40, "d4_specification_arm_count_mismatch", str(len(arm_specs)))
    _expect_equal(len(evidence), 40, "d4_evidence_arm_count_mismatch", str(len(evidence)))
    specs_by_key: dict[tuple[int, str], Mapping[str, Any]] = {}
    evidence_by_key: dict[tuple[int, str], Mapping[str, Any]] = {}
    for raw_spec in arm_specs:
        spec = _as_mapping(raw_spec, "D4 arm specification")
        binding = _mapping(spec, "input_binding")
        key = (_integer(binding.get("seed"), "D4 specification seed"), str(spec.get("arm", "")))
        _expect(key not in specs_by_key, "d4_duplicate_arm_specification", repr(key))
        unsigned_arm = dict(spec)
        arm_id = str(unsigned_arm.pop("arm_id", ""))
        _expect_equal(arm_id, f"d4-rr-paired-arm-{_producer_json_sha256(unsigned_arm)}", "d4_arm_id_mismatch", repr(key))
        specs_by_key[key] = spec
    for raw_evidence in evidence:
        item = _as_mapping(raw_evidence, "D4 arm evidence")
        key = (_integer(item.get("seed"), "D4 evidence seed"), str(item.get("arm", "")))
        _expect(key not in evidence_by_key, "d4_duplicate_arm_evidence", repr(key))
        evidence_by_key[key] = item
    expected_keys = {
        (seed, kind)
        for seed in EXPECTED_RESERVED_SEEDS
        for kind in ("control_rule", "treatment_candidate")
    }
    _expect_equal(set(specs_by_key), expected_keys, "d4_arm_specification_catalog_mismatch", "D4 arms")
    _expect_equal(set(evidence_by_key), expected_keys, "d4_arm_evidence_catalog_mismatch", "D4 evidence")

    rejections: Counter[str] = Counter()
    treatment_latencies: list[float] = []
    treatment_confidences: list[float] = []
    gate_counts: Counter[str] = Counter()
    safe_adopted_count = fallback_count = 0
    pair_identity_count = bundle_identity_count = 0
    for seed in EXPECTED_RESERVED_SEEDS:
        control_spec = specs_by_key[(seed, "control_rule")]
        treatment_spec = specs_by_key[(seed, "treatment_candidate")]
        control_binding = _mapping(control_spec, "input_binding")
        treatment_binding = _mapping(treatment_spec, "input_binding")
        _expect_equal(control_binding, treatment_binding, "d4_pair_input_binding_mismatch", str(seed))
        lineage = lineage_by_seed[seed]
        expected_binding = {
            "communication_schedule_sha256": lineage["communication_schedule_sha256"],
            "fault_schedule_sha256": lineage["fault_schedule_sha256"],
            "initial_state_sha256": lineage["initial_state_sha256"],
            "region_snapshot_lineage_sha256": lineage["d4_region_snapshot_lineage_sha256"],
            "scenario_config_sha256": lineage["scenario_config_sha256"],
            "scenario_id": lineage["scenario_id"],
            "scenario_version": lineage["scenario_version"],
            "seed": seed,
        }
        _expect_equal(control_binding, expected_binding, "d4_lineage_binding_mismatch", str(seed))
        _expect(control_spec.get("candidate_influence_allowed") is False, "d4_control_candidate_influence", str(seed))
        _expect(treatment_spec.get("candidate_influence_allowed") is True, "d4_treatment_candidate_influence_disabled", str(seed))
        for spec in (control_spec, treatment_spec):
            _expect(spec.get("isolated_offline_only") is True, "d4_arm_not_isolated", str(seed))
            bundle_identity_count += 1

        control = evidence_by_key[(seed, "control_rule")]
        treatment = evidence_by_key[(seed, "treatment_candidate")]
        _validate_d4_evidence(
            control,
            spec=control_spec,
            specification_sha256=specification_sha256,
            expected_kind="control_rule",
            lineage=lineage,
            source_schema_version=source_schema_version,
            minimum_confidence=minimum_confidence,
            latency_limit_ms=latency_limit_ms,
        )
        _validate_d4_evidence(
            treatment,
            spec=treatment_spec,
            specification_sha256=specification_sha256,
            expected_kind="treatment_candidate",
            lineage=lineage,
            source_schema_version=source_schema_version,
            minimum_confidence=minimum_confidence,
            latency_limit_ms=latency_limit_ms,
        )
        for name in (
            "expected_input_sha256",
            "observed_input_sha256",
            "snapshot_payload_sha256",
            "specification_sha256",
        ):
            _expect_equal(control.get(name), treatment.get(name), "d4_evidence_pair_identity_mismatch", f"{seed}:{name}")
        pair_identity_count += 1
        safe_adopted_count += int(treatment.get("isolated_treatment_safe_adopted") is True)
        fallback_count += int(treatment.get("rule_fallback_used") is True)
        for reason in _sequence(treatment, "rejection_reasons"):
            rejections[str(reason)] += 1
        treatment_latencies.append(
            _number(treatment.get("candidate_latency_ms"), "D4 candidate latency")
        )
        if is_v2:
            treatment_confidences.append(
                _number(
                    treatment.get("candidate_confidence"),
                    "D4 candidate confidence",
                )
            )
            gate_counts["candidate_considered_count"] += int(
                treatment.get("candidate_considered") is True
            )
            gate_counts["diagnostics_available_count"] += int(
                treatment.get("candidate_gate_diagnostics_available") is True
            )
            for output_name, evidence_name in (
                ("confidence_gate_passed_count", "candidate_confidence_gate_passed"),
                ("ood_gate_passed_count", "candidate_ood_gate_passed"),
                ("latency_gate_passed_count", "candidate_latency_gate_passed"),
                ("finite_gate_passed_count", "candidate_finite_gate_passed"),
                ("failure_gate_passed_count", "candidate_failure_gate_passed"),
                ("aggregate_gate_passed_count", "candidate_thresholds_passed"),
            ):
                gate_counts[output_name] += int(
                    treatment.get(evidence_name) is True
                )

    _expect_equal(safe_adopted_count, 0, "d4_treatment_safe_adopted_unexpected", str(safe_adopted_count))
    _expect_equal(fallback_count, 20, "d4_rule_fallback_count_mismatch", str(fallback_count))
    expected_rejections = (
        {
            "candidate_low_confidence": 20,
            "candidate_threshold_or_finite_gate_rejected": 20,
        }
        if is_v2
        else {"candidate_threshold_or_finite_gate_rejected": 20}
    )
    _expect_equal(dict(rejections), expected_rejections, "d4_rejection_summary_mismatch", "D4 treatment")

    d4_result: dict[str, Any] = {
        "execution_receipts_available": True,
        "execution_receipt_count": 40,
        "arm_count": 40,
        "control_arm_count": 20,
        "treatment_arm_count": 20,
        "pair_input_identity_verified_count": pair_identity_count,
        "bundle_identity_verified_arm_count": bundle_identity_count,
        "specification_sha256_verified_arm_count": 40,
        "bundle_binding": {
            "manifest_sha256": inputs.expected_d4_bundle_manifest_sha256,
            "state_sha256": inputs.expected_d4_bundle_state_sha256,
            "bundle_files_rehashed": False,
            "binding_verified": True,
        },
        "treatment_safe_adopted_count": safe_adopted_count,
        "treatment_rule_fallback_count": fallback_count,
        "treatment_rejection_reason_counts": dict(sorted(rejections.items())),
        "treatment_candidate_latency_ms": _latency_summary(treatment_latencies),
        "paired_outcome": _unavailable("no_adopted_d4_treatment_and_no_physical_outcome"),
        "paired_effect": _unavailable("no_adopted_d4_treatment_and_no_physical_outcome"),
    }
    if is_v2:
        assert minimum_confidence is not None
        assert latency_limit_ms is not None
        d4_result["candidate_gate_summary"] = {
            **dict(gate_counts),
            "arm_evidence_schema_versions": [
                EXPECTED_D4_ARM_EVIDENCE_SCHEMA_VERSION_V2
            ],
            "candidate_confidence": _gate_distribution_summary(
                treatment_confidences
            ),
            "candidate_latency_ms": _gate_distribution_summary(
                treatment_latencies
            ),
            "minimum_confidence_values": [minimum_confidence],
            "candidate_latency_limit_ms_values": [latency_limit_ms],
        }
    return d4_result


def _validate_d4_evidence(
    item: Mapping[str, Any],
    *,
    spec: Mapping[str, Any],
    specification_sha256: str,
    expected_kind: str,
    lineage: Mapping[str, Any],
    source_schema_version: str,
    minimum_confidence: float | None,
    latency_limit_ms: float | None,
) -> None:
    seed = _integer(item.get("seed"), "D4 evidence seed")
    is_v2 = (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    if is_v2:
        _expect_equal(
            item.get("schema"),
            EXPECTED_D4_ARM_EVIDENCE_SCHEMA_VERSION_V2,
            "d4_v2_arm_evidence_schema_mismatch",
            f"{seed}:{expected_kind}",
        )
        _expect(
            item.get("candidate_gate_diagnostics_available") is True,
            "d4_v2_gate_diagnostics_unavailable",
            f"{seed}:{expected_kind}",
        )
        _expect(minimum_confidence is not None, "d4_v2_threshold_missing", "minimum confidence")
        _expect(latency_limit_ms is not None, "d4_v2_threshold_missing", "latency limit")
        _expect_equal(
            _number(item.get("minimum_confidence"), "D4 evidence minimum confidence"),
            minimum_confidence,
            "d4_v2_evidence_minimum_confidence_mismatch",
            f"{seed}:{expected_kind}",
        )
        _expect_equal(
            _number(item.get("candidate_latency_limit_ms"), "D4 evidence latency limit"),
            latency_limit_ms,
            "d4_v2_evidence_latency_limit_mismatch",
            f"{seed}:{expected_kind}",
        )
    _expect_equal(item.get("arm_id"), spec.get("arm_id"), "d4_evidence_arm_id_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(item.get("arm"), expected_kind, "d4_evidence_kind_mismatch", str(seed))
    _expect_equal(item.get("specification_sha256"), specification_sha256, "d4_evidence_specification_sha256_mismatch", f"{seed}:{expected_kind}")
    _expect(item.get("candidate_bundle_match") is True, "d4_candidate_bundle_mismatch", f"{seed}:{expected_kind}")
    _expect(item.get("pair_input_match") is True, "d4_pair_input_match_false", f"{seed}:{expected_kind}")
    _expect_equal(item.get("expected_input_sha256"), item.get("observed_input_sha256"), "d4_observed_input_mismatch", f"{seed}:{expected_kind}")
    _expect_equal(item.get("snapshot_payload_sha256"), lineage["d4_region_snapshot_lineage_sha256"], "d4_snapshot_lineage_mismatch", f"{seed}:{expected_kind}")
    _expect(item.get("assist_enabled") is False, "d4_assist_enabled", f"{seed}:{expected_kind}")
    _expect(item.get("online_authority") is False, "d4_online_authority_enabled", f"{seed}:{expected_kind}")
    _expect(item.get("ppo_enabled") is False, "d4_ppo_enabled", f"{seed}:{expected_kind}")
    _expect(item.get("rule_fallback_enabled") is True, "d4_rule_fallback_disabled", f"{seed}:{expected_kind}")
    _expect(item.get("runtime_advisory_applied_ack_available") is False, "d4_runtime_ack_claim", f"{seed}:{expected_kind}")
    _expect(item.get("post_projection_recommendation_is_applied_ack") is False, "d4_applied_ack_claim", f"{seed}:{expected_kind}")
    for name in (
        "causal_effect_available",
        "counterfactual_available",
        "observed_outcome_available",
        "paired_non_degradation_available",
    ):
        _expect(item.get(name) is False, "d4_evidence_outcome_claim", f"{seed}:{expected_kind}:{name}")
    _expect(item.get("deterministic_rule_executed") is True, "d4_rule_not_executed", f"{seed}:{expected_kind}")
    _expect(item.get("next_cycle_consumption_passed") is True, "d4_next_cycle_consumption_failed", f"{seed}:{expected_kind}")
    _expect(item.get("isolated_arm_safe_adopted") is True, "d4_isolated_arm_not_safe", f"{seed}:{expected_kind}")
    _require_sha256(item.get("advisory_payload_sha256"), "D4 advisory payload")
    _require_sha256(item.get("executed_recommendation_sha256"), "D4 executed recommendation")
    latency = _number(item.get("candidate_latency_ms"), "D4 candidate latency")
    _expect(latency >= 0.0, "d4_negative_candidate_latency", f"{seed}:{expected_kind}")
    if expected_kind == "control_rule":
        _expect(item.get("candidate_considered") is False, "d4_control_candidate_considered", str(seed))
        _expect(item.get("isolated_treatment_safe_adopted") is False, "d4_control_treatment_adopted", str(seed))
        _expect(item.get("rule_fallback_used") is False, "d4_control_rule_fallback", str(seed))
        _expect_equal(list(_sequence(item, "rejection_reasons")), [], "d4_control_rejection_reason", str(seed))
        if is_v2:
            for name in (
                "candidate_confidence",
                "candidate_confidence_gate_passed",
                "candidate_failure_gate_passed",
                "candidate_finite",
                "candidate_finite_gate_passed",
                "candidate_latency_gate_passed",
                "candidate_ood_gate_passed",
                "candidate_ood_passed",
            ):
                _expect(
                    item.get(name) is None,
                    "d4_v2_control_gate_value_nonnull",
                    f"{seed}:{name}",
                )
            _expect_equal(latency, 0.0, "d4_v2_control_latency_nonzero", str(seed))
            _expect(item.get("candidate_thresholds_passed") is True, "d4_v2_control_thresholds_failed", str(seed))
            _expect(item.get("candidate_safety_projection_passed") is True, "d4_v2_control_projection_failed", str(seed))
    else:
        _expect(item.get("candidate_considered") is True, "d4_treatment_candidate_not_considered", str(seed))
        _require_sha256(item.get("candidate_recommendation_sha256"), "D4 candidate recommendation")
        if is_v2:
            assert minimum_confidence is not None
            assert latency_limit_ms is not None
            confidence = _number(
                item.get("candidate_confidence"),
                "D4 candidate confidence",
            )
            _expect(
                0.0 <= confidence <= 1.0,
                "d4_v2_candidate_confidence_out_of_range",
                str(seed),
            )
            expected_confidence_gate = confidence >= minimum_confidence
            _expect_equal(
                item.get("candidate_confidence_gate_passed"),
                expected_confidence_gate,
                "d4_v2_candidate_confidence_gate_mismatch",
                str(seed),
            )
            _expect(item.get("candidate_ood_passed") is True, "d4_v2_candidate_ood_failed", str(seed))
            _expect_equal(item.get("candidate_ood_gate_passed"), item.get("candidate_ood_passed"), "d4_v2_candidate_ood_gate_mismatch", str(seed))
            _expect_equal(item.get("candidate_latency_gate_passed"), latency <= latency_limit_ms, "d4_v2_candidate_latency_gate_mismatch", str(seed))
            _expect(item.get("candidate_finite") is True, "d4_v2_candidate_nonfinite", str(seed))
            _expect_equal(item.get("candidate_finite_gate_passed"), item.get("candidate_finite"), "d4_v2_candidate_finite_gate_mismatch", str(seed))
            _expect(item.get("candidate_failure_gate_passed") is True, "d4_v2_candidate_failure_gate_failed", str(seed))
            aggregate_gate = all(
                item.get(name) is True
                for name in (
                    "candidate_confidence_gate_passed",
                    "candidate_ood_gate_passed",
                    "candidate_latency_gate_passed",
                    "candidate_finite_gate_passed",
                    "candidate_failure_gate_passed",
                )
            )
            _expect_equal(item.get("candidate_thresholds_passed"), aggregate_gate, "d4_v2_candidate_aggregate_gate_mismatch", str(seed))
            _expect_equal(item.get("candidate_safety_projection_passed"), aggregate_gate, "d4_v2_candidate_projection_gate_mismatch", str(seed))
            _expect_equal(item.get("isolated_treatment_safe_adopted"), aggregate_gate, "d4_v2_candidate_adoption_gate_mismatch", str(seed))
            _expect_equal(item.get("rule_fallback_used"), not aggregate_gate, "d4_v2_candidate_fallback_gate_mismatch", str(seed))
            expected_rejections = []
            if not expected_confidence_gate:
                expected_rejections.append("candidate_low_confidence")
            if not aggregate_gate:
                expected_rejections.append(
                    "candidate_threshold_or_finite_gate_rejected"
                )
            _expect_equal(list(_sequence(item, "rejection_reasons")), expected_rejections, "d4_v2_treatment_rejection_reason_mismatch", str(seed))
        else:
            _expect(item.get("candidate_thresholds_passed") is False, "d4_treatment_threshold_unexpectedly_passed", str(seed))
            _expect(item.get("candidate_safety_projection_passed") is False, "d4_treatment_projection_unexpectedly_passed", str(seed))
            _expect(item.get("isolated_treatment_safe_adopted") is False, "d4_treatment_safe_adopted", str(seed))
            _expect(item.get("rule_fallback_used") is True, "d4_treatment_rule_fallback_missing", str(seed))
            _expect_equal(list(_sequence(item, "rejection_reasons")), ["candidate_threshold_or_finite_gate_rejected"], "d4_treatment_rejection_reason_mismatch", str(seed))


def _validate_source_manifest(
    manifest: Mapping[str, Any],
    *,
    lineage_summary: Mapping[str, Any],
    d3_summary: Mapping[str, Any],
    d4_summary: Mapping[str, Any],
    inputs: ReservedSeedInterventionAuditInputs,
    input_sha256: Mapping[str, str],
    source_schema_version: str,
) -> None:
    _expect_equal(manifest.get("schema_version"), source_schema_version, "source_manifest_schema_mismatch", "manifest")
    _expect_equal(manifest.get("experiment_scope"), "reserved_seed_isolated_d3_d4_execution", "source_manifest_scope_mismatch", "manifest")
    _expect_equal(manifest.get("reserved_seeds"), list(EXPECTED_RESERVED_SEEDS), "source_manifest_seed_catalog_mismatch", "manifest")
    _expect_equal(manifest.get("source_episode_count"), 20, "source_manifest_episode_count_mismatch", "manifest")
    _expect_equal(manifest.get("source_git_commits"), [inputs.expected_source_commit], "source_manifest_commit_mismatch", "manifest")
    _expect_equal(manifest.get("dirty_source_episode_count"), lineage_summary["dirty_source_episode_count"], "source_manifest_dirty_count_mismatch", "manifest")
    _expect_equal(manifest.get("source_nonfinite_count"), lineage_summary["nonfinite_source_episode_count"], "source_manifest_nonfinite_count_mismatch", "manifest")
    _expect_equal(manifest.get("online_truth_use_count"), lineage_summary["online_truth_use_count"], "source_manifest_truth_count_mismatch", "manifest")
    _expect_equal(manifest.get("d3_arm_count"), d3_summary["arm_count"], "source_manifest_d3_arm_count_mismatch", "manifest")
    _expect_equal(manifest.get("d4_arm_count"), d4_summary["arm_count"], "source_manifest_d4_arm_count_mismatch", "manifest")
    _expect_equal(manifest.get("scenario"), "nominal", "source_manifest_scenario_mismatch", "manifest")
    for name in ("scale", "resource_count", "target_count"):
        _expect_equal(manifest.get(name), 5, "source_manifest_scale_mismatch", name)
    _expect_equal(
        _mapping(manifest, "evidence_availability"),
        {"causal": False, "counterfactual": False, "execution_receipts": True, "physical_outcome": False, "runtime_ack": False},
        "source_manifest_availability_mismatch",
        "manifest",
    )
    _expect_equal(
        _mapping(manifest, "admission"),
        {"assist": False, "authority": False, "ppo": False, "rule_fallback": True},
        "source_manifest_admission_mismatch",
        "manifest",
    )
    artifacts = _mapping(manifest, "artifacts_sha256")
    _expect_equal(set(artifacts), set(_MANIFEST_ARTIFACT_PATHS), "source_manifest_artifact_catalog_mismatch", "manifest")
    for key, filename in _MANIFEST_ARTIFACT_PATHS.items():
        _expect_equal(artifacts.get(key), input_sha256[filename], "source_manifest_artifact_sha256_mismatch", key)

    d3_bundle = _mapping(manifest, "d3_bundle")
    _expect(d3_bundle.get("loaded") is True, "source_manifest_d3_bundle_not_loaded", "manifest")
    _expect_equal(d3_bundle.get("expected_manifest_sha256"), inputs.expected_d3_bundle_manifest_sha256, "source_manifest_d3_expected_manifest_mismatch", "manifest")
    _expect_equal(d3_bundle.get("manifest_sha256"), inputs.expected_d3_bundle_manifest_sha256, "source_manifest_d3_manifest_mismatch", "manifest")
    _expect_equal(d3_bundle.get("state_dict_sha256"), inputs.expected_d3_bundle_state_sha256, "source_manifest_d3_state_mismatch", "manifest")
    d4_bundle = _mapping(manifest, "d4_bundle")
    _expect(d4_bundle.get("loaded") is True, "source_manifest_d4_bundle_not_loaded", "manifest")
    _expect_equal(d4_bundle.get("bundle_manifest_sha256"), inputs.expected_d4_bundle_manifest_sha256, "source_manifest_d4_manifest_mismatch", "manifest")
    _expect_equal(d4_bundle.get("model_state_sha256"), inputs.expected_d4_bundle_state_sha256, "source_manifest_d4_state_mismatch", "manifest")
    is_v2 = (
        source_schema_version
        == RESERVED_SEED_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    )
    expected_d3_summary: dict[str, Any] = {
        "applied_count": d3_summary["treatment_applied_count"],
        "fallback_reason_counts": d3_summary[
            "treatment_fallback_reason_counts"
        ],
        "rule_fallback_count": d3_summary[
            "treatment_rule_fallback_count"
        ],
    }
    if is_v2:
        expected_d3_summary.update(
            {
                "safety_shell_config_sha256": (
                    EXPECTED_D3_SAFETY_SHELL_CONFIG_SHA256_V2
                ),
                "safety_shell_version": EXPECTED_D3_SAFETY_SHELL_VERSION_V2,
            }
        )
    _expect_equal(
        _mapping(manifest, "d3_treatment_summary"),
        expected_d3_summary,
        "source_manifest_d3_summary_mismatch",
        "manifest",
    )
    expected_d4_summary: dict[str, Any] = {
        "rejection_reason_counts": d4_summary[
            "treatment_rejection_reason_counts"
        ],
        "rule_fallback_count": d4_summary[
            "treatment_rule_fallback_count"
        ],
        "safe_adopted_count": d4_summary["treatment_safe_adopted_count"],
    }
    if is_v2:
        expected_d4_summary["candidate_gate_summary"] = d4_summary[
            "candidate_gate_summary"
        ]
    _expect_equal(
        _mapping(manifest, "d4_treatment_summary"),
        expected_d4_summary,
        "source_manifest_d4_summary_mismatch",
        "manifest",
    )


def _latency_summary(
    values: Sequence[float],
    *,
    p95_method: str = "nearest_rank",
) -> dict[str, Any]:
    _expect(len(values) > 0, "latency_samples_missing", "latency summary")
    ordered = sorted(float(value) for value in values)
    for value in ordered:
        _expect(math.isfinite(value) and value >= 0.0, "invalid_latency_sample", repr(value))
    count = len(ordered)
    midpoint = count // 2
    median = (
        ordered[midpoint]
        if count % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
    )
    _expect(
        p95_method in {"nearest_rank", "linear"},
        "unsupported_percentile_method",
        p95_method,
    )
    if p95_method == "nearest_rank":
        p95_index = max(0, math.ceil(0.95 * count) - 1)
        p95 = ordered[p95_index]
        output_method = "nearest_rank"
    else:
        p95 = _percentile_linear(ordered, 0.95)
        output_method = "linear_interpolation"
    return {
        "availability": "available",
        "available": True,
        "unit": "ms",
        "sample_count": count,
        "min_ms": ordered[0],
        "mean_ms": math.fsum(ordered) / count,
        "median_ms": median,
        "p95_ms": p95,
        "p95_method": output_method,
        "max_ms": ordered[-1],
    }


def _gate_distribution_summary(values: Sequence[float]) -> dict[str, Any]:
    _expect(len(values) > 0, "gate_samples_missing", "gate summary")
    ordered = sorted(float(value) for value in values)
    for value in ordered:
        _expect(math.isfinite(value), "invalid_gate_sample", repr(value))
    return {
        "maximum": ordered[-1],
        "mean": math.fsum(ordered) / len(ordered),
        "minimum": ordered[0],
        "p95": _percentile_linear(ordered, 0.95),
        "sample_count": len(ordered),
    }


def _percentile_linear(values: Sequence[float], quantile: float) -> float:
    _expect(len(values) > 0, "percentile_samples_missing", "percentile")
    _expect(0.0 <= quantile <= 1.0, "percentile_out_of_range", str(quantile))
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "status": "unavailable",
        "value": None,
        "reason": reason,
    }


def _format_ms(value: Any) -> str:
    return f"{_number(value, 'latency'):0.6f}"


def _parse_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    lines = path.read_text(encoding="ascii").splitlines()
    _expect(len(lines) > 0, "sha256sums_empty", str(path))
    for line in lines:
        match = _SHA256SUM_LINE_RE.fullmatch(line)
        _expect(match is not None, "sha256sums_line_invalid", line)
        assert match is not None
        digest, filename = match.groups()
        _expect(filename not in result, "sha256sums_duplicate_file", filename)
        result[filename] = digest
    return result


def _snapshot(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: _sha256_file(path) for name, path in sorted(paths.items())}


def _artifact_set_sha256(snapshot: Mapping[str, str]) -> str:
    return _producer_json_sha256(dict(sorted(snapshot.items())))


def _artifact_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _load_json_object(path: Path, context: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _fail("json_load_failed", f"{context}: {exc}")
    if not isinstance(value, dict):
        _fail("json_object_required", context)
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        _fail("jsonl_load_failed", str(exc))
    for line_number, line in enumerate(lines, start=1):
        _expect(line.strip() != "", "jsonl_blank_line", str(line_number))
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail("jsonl_decode_failed", f"line {line_number}: {exc}")
        if not isinstance(value, dict):
            _fail("jsonl_object_required", f"line {line_number}")
        result.append(value)
    return result


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _with_content_sha256(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _producer_json_sha256(result)
    return result


def _producer_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    return _as_mapping(value.get(key), key)


def _as_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(value: Mapping[str, Any], key: str) -> Sequence[Any]:
    item = value.get(key)
    if not isinstance(item, list):
        _fail("list_required", key)
    return item


def _without_keys(value: Mapping[str, Any], keys: set[str]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in keys}


def _require_sha256(value: Any, context: str) -> str:
    digest = str(value)
    _expect(_SHA256_RE.fullmatch(digest) is not None, "sha256_invalid", context)
    return digest


def _integer(value: Any, context: str) -> int:
    if type(value) is not int:
        _fail("integer_required", context)
    return value


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("number_required", context)
    result = float(value)
    _expect(math.isfinite(result), "finite_number_required", context)
    return result


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _expect_equal(actual: Any, expected: Any, code: str, detail: str) -> None:
    if actual != expected:
        _fail(code, f"{detail}: actual={actual!r}, expected={expected!r}")


def _expect_numeric_mapping_close(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    code: str,
    detail: str,
) -> None:
    _expect_equal(set(actual), set(expected), code, detail)
    for key, expected_value in expected.items():
        actual_value = _number(actual.get(key), f"{detail}:{key}")
        _expect(
            math.isclose(
                actual_value,
                _number(expected_value, f"{detail}:{key}"),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ),
            code,
            f"{detail}:{key}: actual={actual_value!r}, expected={expected_value!r}",
        )


def _expect(condition: bool, code: str, detail: str) -> None:
    if not condition:
        _fail(code, detail)


def _fail(code: str, detail: str) -> None:
    raise ReservedSeedInterventionAuditError(code, detail)
