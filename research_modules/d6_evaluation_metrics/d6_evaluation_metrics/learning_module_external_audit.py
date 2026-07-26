"""Strict external pre-admission audits for learned D3 and D4 modules.

This module is a read-only D6 boundary.  It authenticates one frozen candidate
bundle, its training corpus audit, its current implementation lineage, and one
formal scope audit with same-key R0 evidence.  Passing means only that the
evidence chain is complete and internally consistent.  D6 never grants model
promotion, assist, default-path, assignment, failover, or control authority.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .learning_scope_formal_audit import (
    LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION,
)


MODULE_IMPLEMENTATION_EVIDENCE_SCHEMA_VERSION = (
    "d6.learning-module-implementation-evidence.v1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

_COMMON_ARTIFACT_NAMES = (
    "dataset_manifest",
    "full_sample_audit",
    "bundle_manifest",
    "bundle_weights",
    "implementation_evidence",
    "formal_scope_audit",
    "formal_scope_checksums",
)

_D3_SOURCE_FILES = (
    "isolated_plan_consumption.py",
    "learning.py",
    "learning_bundle.py",
    "learning_data.py",
    "learning_training.py",
    "multi_cycle_shadow.py",
    "offline_intervention_execution.py",
    "paired_intervention.py",
    "planner.py",
    "runtime_reward_evidence.py",
    "solver.py",
)

_D4_SOURCE_FILES = (
    "canonical_seed_split.py",
    "coalition_safety.py",
    "communication_causal_evidence.py",
    "region_resource.py",
    "region_resource_dataset.py",
    "region_resource_isolated_rollout.py",
    "region_resource_learning.py",
    "region_resource_paired_intervention.py",
    "region_resource_reward_evidence.py",
    "region_resource_runtime_ack.py",
    "region_resource_training.py",
    "regional_failover.py",
)


@dataclass(frozen=True, slots=True)
class LearningModuleAuditProfile:
    """Frozen role-specific semantics for one external audit contract."""

    key: str
    role: str
    variant: str
    component: str
    input_schema_version: str
    output_schema_version: str
    consumer_schema_version: str
    formal_profile_version: str
    artifact_names: tuple[str, ...]
    source_files: tuple[str, ...]
    report_prefix: str
    report_title_cn: str
    adoption_evidence_kind: str
    adoption_source_metric: str
    minimum_unseen_seed_count: int = 20


D3_A1_PROFILE = LearningModuleAuditProfile(
    key="d3_a1",
    role="D3_A1",
    variant="A1",
    component="d3",
    input_schema_version="d6.d3-a1-external-audit-input.v1",
    output_schema_version="d6.d3-a1-external-audit.v1",
    consumer_schema_version="d6.d3-a1-external-audit-consumer.v1",
    formal_profile_version="d6.d3-a1-formal-pre-admission.v1",
    artifact_names=(
        *_COMMON_ARTIFACT_NAMES[:1],
        "dataset_payload",
        *_COMMON_ARTIFACT_NAMES[1:],
    ),
    source_files=_D3_SOURCE_FILES,
    report_prefix="d3_a1",
    report_title_cn="D3 A1 预准入外部审计",
    adoption_evidence_kind="isolated_application",
    adoption_source_metric="d3_learning_applied_count",
)

D4_A2_PROFILE = LearningModuleAuditProfile(
    key="d4_a2",
    role="D4_A2",
    variant="A2",
    component="d4",
    input_schema_version="d6.d4-a2-external-audit-input.v1",
    output_schema_version="d6.d4-a2-external-audit.v1",
    consumer_schema_version="d6.d4-a2-external-audit-consumer.v1",
    formal_profile_version="d6.d4-a2-formal-pre-admission.v1",
    artifact_names=(
        *_COMMON_ARTIFACT_NAMES[:4],
        "model_readiness",
        *_COMMON_ARTIFACT_NAMES[4:],
    ),
    source_files=_D4_SOURCE_FILES,
    report_prefix="d4_a2",
    report_title_cn="D4 A2 预准入外部审计",
    adoption_evidence_kind="runtime_ack",
    adoption_source_metric="d4_advice_control_adoption_count",
)

_PROFILES = {
    D3_A1_PROFILE.key: D3_A1_PROFILE,
    D4_A2_PROFILE.key: D4_A2_PROFILE,
}


class LearningModuleExternalAuditError(ValueError):
    """Stable validation error for an invalid request or output directory."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class LearningModuleExternalAuditArtifact:
    """One caller-frozen relative artifact path and out-of-band digest."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise LearningModuleExternalAuditError(
                "input_artifact_path_invalid",
                repr(self.path),
            )
        path = Path(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise LearningModuleExternalAuditError(
                "input_artifact_path_invalid",
                self.path,
            )
        if (
            not isinstance(self.sha256, str)
            or _SHA256_RE.fullmatch(self.sha256) is None
        ):
            raise LearningModuleExternalAuditError(
                "input_artifact_sha256_invalid",
                self.path,
            )


@dataclass(frozen=True, slots=True)
class LearningModuleExternalAuditInputs:
    """Strict profile-bound request for one D3/A1 or D4/A2 audit."""

    repository_root: Path
    profile_key: str
    audit_id: str
    evaluated_at_utc: str
    formal_profile_version: str
    module_source_dir: str
    expected_current_implementation_sha256: str
    artifacts: Mapping[str, LearningModuleExternalAuditArtifact]
    schema_version: str

    def __post_init__(self) -> None:
        profile = get_learning_module_audit_profile(self.profile_key)
        root = Path(self.repository_root).expanduser().resolve()
        if not root.is_dir():
            raise LearningModuleExternalAuditError(
                "input_repository_root_invalid",
                str(root),
            )
        object.__setattr__(self, "repository_root", root)
        if self.schema_version != profile.input_schema_version:
            raise LearningModuleExternalAuditError(
                "input_schema_mismatch",
                self.schema_version,
            )
        if self.formal_profile_version != profile.formal_profile_version:
            raise LearningModuleExternalAuditError(
                "input_formal_profile_mismatch",
                self.formal_profile_version,
            )
        for name in ("audit_id", "evaluated_at_utc"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise LearningModuleExternalAuditError(
                    "input_string_invalid",
                    name,
                )
        if (
            not isinstance(self.module_source_dir, str)
            or not self.module_source_dir.strip()
        ):
            raise LearningModuleExternalAuditError(
                "input_module_source_dir_invalid",
                repr(self.module_source_dir),
            )
        source = Path(self.module_source_dir)
        if source.is_absolute() or ".." in source.parts:
            raise LearningModuleExternalAuditError(
                "input_module_source_dir_invalid",
                self.module_source_dir,
            )
        if (
            not isinstance(
                self.expected_current_implementation_sha256,
                str,
            )
            or _SHA256_RE.fullmatch(
                self.expected_current_implementation_sha256
            )
            is None
        ):
            raise LearningModuleExternalAuditError(
                "input_current_implementation_sha256_invalid",
                self.expected_current_implementation_sha256,
            )
        artifacts = dict(self.artifacts)
        if set(artifacts) != set(profile.artifact_names):
            mismatch = sorted(
                set(artifacts) ^ set(profile.artifact_names)
            )
            raise LearningModuleExternalAuditError(
                "input_artifact_set_mismatch",
                ",".join(mismatch),
            )
        if any(
            not isinstance(value, LearningModuleExternalAuditArtifact)
            for value in artifacts.values()
        ):
            raise LearningModuleExternalAuditError(
                "input_artifact_type_invalid",
                "all artifacts must be LearningModuleExternalAuditArtifact",
            )
        object.__setattr__(self, "artifacts", artifacts)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        repository_root: str | Path,
        profile_key: str,
    ) -> "LearningModuleExternalAuditInputs":
        profile = get_learning_module_audit_profile(profile_key)
        expected_fields = {
            "schema_version",
            "audit_id",
            "evaluated_at_utc",
            "formal_profile_version",
            "module_source_dir",
            "expected_current_implementation_sha256",
            "artifacts",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected_fields:
            raise LearningModuleExternalAuditError(
                "input_fields_mismatch",
                "top-level fields differ from the frozen schema",
            )
        raw_artifacts = payload.get("artifacts")
        if not isinstance(raw_artifacts, Mapping):
            raise LearningModuleExternalAuditError(
                "input_artifact_type_invalid",
                "artifacts must be an object",
            )
        artifacts: dict[str, LearningModuleExternalAuditArtifact] = {}
        for name, raw in raw_artifacts.items():
            if (
                not isinstance(raw, Mapping)
                or set(raw) != {"path", "sha256"}
            ):
                raise LearningModuleExternalAuditError(
                    "input_artifact_fields_mismatch",
                    str(name),
                )
            artifacts[str(name)] = LearningModuleExternalAuditArtifact(
                path=raw["path"],
                sha256=raw["sha256"],
            )
        return cls(
            repository_root=Path(repository_root),
            profile_key=profile.key,
            audit_id=payload["audit_id"],
            evaluated_at_utc=payload["evaluated_at_utc"],
            formal_profile_version=payload["formal_profile_version"],
            module_source_dir=payload["module_source_dir"],
            expected_current_implementation_sha256=payload[
                "expected_current_implementation_sha256"
            ],
            artifacts=artifacts,
            schema_version=payload["schema_version"],
        )

    @property
    def profile(self) -> LearningModuleAuditProfile:
        return get_learning_module_audit_profile(self.profile_key)

    @property
    def source_root(self) -> Path:
        return _safe_child(self.repository_root, self.module_source_dir)

    def resolve_artifact(self, name: str) -> Path:
        return _safe_child(
            self.repository_root,
            self.artifacts[name].path,
        )


class _AuditContext:
    def __init__(self) -> None:
        self.details: dict[str, list[str]] = {}

    def block(self, code: str, detail: str) -> None:
        values = self.details.setdefault(str(code), [])
        text = str(detail)
        if text not in values:
            values.append(text)

    @property
    def blockers(self) -> list[str]:
        return sorted(self.details)

    def blocker_details(self) -> dict[str, list[str]]:
        return {
            key: sorted(values)
            for key, values in sorted(self.details.items())
        }


def get_learning_module_audit_profile(
    profile_key: str,
) -> LearningModuleAuditProfile:
    """Return one immutable role profile."""

    try:
        return _PROFILES[str(profile_key)]
    except KeyError as exc:
        raise LearningModuleExternalAuditError(
            "input_profile_unknown",
            str(profile_key),
        ) from exc


def load_learning_module_external_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
    profile_key: str,
) -> LearningModuleExternalAuditInputs:
    """Load one strict profile request without adjacent-file discovery."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LearningModuleExternalAuditError(
            "input_json_invalid",
            str(source),
        ) from exc
    if not isinstance(payload, dict):
        raise LearningModuleExternalAuditError(
            "input_json_object_required",
            str(source),
        )
    return LearningModuleExternalAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
        profile_key=profile_key,
    )


def audit_learning_module_external_evidence(
    inputs: LearningModuleExternalAuditInputs,
) -> dict[str, Any]:
    """Audit one frozen D3/A1 or D4/A2 pre-admission evidence chain."""

    profile = inputs.profile
    context = _AuditContext()
    artifact_rows, payloads = _audit_artifacts(inputs, context)
    if profile.key == D3_A1_PROFILE.key:
        candidate = _audit_d3_candidate(
            inputs,
            artifact_rows=artifact_rows,
            payloads=payloads,
            context=context,
        )
    else:
        candidate = _audit_d4_candidate(
            inputs,
            artifact_rows=artifact_rows,
            payloads=payloads,
            context=context,
        )
    implementation = _audit_implementation(
        inputs,
        candidate=candidate,
        payloads=payloads,
        context=context,
    )
    formal = _audit_formal_scope(
        inputs,
        candidate=candidate,
        implementation=implementation,
        artifact_rows=artifact_rows,
        payloads=payloads,
        context=context,
    )

    fields = _assemble_consumer_fields(
        inputs,
        candidate=candidate,
        implementation=implementation,
        formal=formal,
        artifact_rows=artifact_rows,
        context=context,
    )
    blockers = context.blockers
    passed = not blockers
    fields["d6_external_audit_passed"] = passed
    fields["failure_reasons"] = blockers
    result: dict[str, Any] = {
        "schema_version": profile.output_schema_version,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "role": profile.role,
        "variant": profile.variant,
        "formal_profile_version": inputs.formal_profile_version,
        "status": "pass" if passed else "fail_closed",
        "audit_passed": passed,
        "fail_closed": not passed,
        "evidence_audit_only": True,
        "frozen_thresholds": {
            "minimum_unseen_seed_count": (
                profile.minimum_unseen_seed_count
            ),
            "maximum_online_truth_use_count": 0,
            "maximum_hard_constraint_failure_count": 0,
            "maximum_rule_fallback_count": 0,
            "maximum_shadow_adoption_count": 0,
            "required_physical_window_availability": "available",
            "required_r0_cardinality_per_comparison_key": 1,
            "required_pair_non_degradation": True,
            "required_adoption_evidence_kind": (
                profile.adoption_evidence_kind
            ),
            "required_adoption_source_metric": (
                profile.adoption_source_metric
            ),
        },
        "artifact_evidence": artifact_rows,
        "candidate": candidate,
        "implementation": implementation,
        "formal_scope": formal,
        "consumer_contract": {
            "schema_version": profile.consumer_schema_version,
            **fields,
        },
        "blocker_codes": blockers,
        "blocker_details": context.blocker_details(),
        "authority": {
            "model_promotion_granted": False,
            "assist_granted": False,
            "assignment_authority_granted": False,
            "failover_authority_granted": False,
            "control_authority_granted": False,
            "default_path_change_granted": False,
            "reason": (
                "D6 issues evidence audit results only; module promotion and "
                "runtime authority remain outside D6"
            ),
        },
        "availability_policy": {
            "missing_evidence": "unavailable_and_fail_closed",
            "type_error": "unavailable_and_fail_closed",
            "source_mismatch": "fail_closed",
            "sha256_mismatch": "fail_closed",
            "shadow_is_adoption": False,
            "rule_fallback_is_adoption": False,
            "caller_declaration_is_evidence": False,
            "missing_physical_window_is_success": False,
            "missing_r0_is_non_degraded": False,
            "zero_fill_allowed": False,
            "unavailable_metric_is_zero": False,
        },
    }
    return _with_content_sha256(result)


def write_learning_module_external_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
    *,
    profile_key: str,
) -> dict[str, Path]:
    """Write deterministic JSON, artifact CSV, Chinese Markdown, and hashes."""

    profile = get_learning_module_audit_profile(profile_key)
    if result.get("schema_version") != profile.output_schema_version:
        raise LearningModuleExternalAuditError(
            "output_result_schema_mismatch",
            str(result.get("schema_version")),
        )
    output = Path(output_dir)
    if output.exists() and (
        not output.is_dir() or any(output.iterdir())
    ):
        raise LearningModuleExternalAuditError(
            "output_directory_not_empty",
            str(output),
        )
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / f"{profile.report_prefix}_external_audit.json"
    csv_path = output / (
        f"{profile.report_prefix}_external_audit_evidence.csv"
    )
    markdown_path = output / (
        f"{profile.report_prefix.upper()}_EXTERNAL_AUDIT_CN.md"
    )
    checksums_path = output / "SHA256SUMS"

    _write_json(json_path, result)
    fieldnames = (
        "artifact_id",
        "path",
        "availability",
        "expected_sha256",
        "actual_sha256",
        "sha256_match",
        "content_sha256",
        "content_sha256_verified",
        "blocker_codes",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            lineterminator="\n",
        )
        writer.writeheader()
        for raw in sorted(
            result.get("artifact_evidence", ()),
            key=lambda item: str(item.get("artifact_id", "")),
        ):
            row = dict(raw)
            row["blocker_codes"] = ";".join(
                str(value) for value in row.get("blocker_codes", ())
            )
            writer.writerow({name: row.get(name) for name in fieldnames})
    markdown_path.write_text(
        render_learning_module_external_audit_markdown(
            result,
            profile_key=profile.key,
        ),
        encoding="utf-8",
    )
    artifacts = (csv_path, json_path, markdown_path)
    checksums_path.write_text(
        "".join(
            f"{_sha256_file(path)}  {path.name}\n"
            for path in sorted(artifacts, key=lambda item: item.name)
        ),
        encoding="ascii",
    )
    return {
        "json": json_path,
        "csv": csv_path,
        "markdown": markdown_path,
        "checksums": checksums_path,
    }


def render_learning_module_external_audit_markdown(
    result: Mapping[str, Any],
    *,
    profile_key: str,
) -> str:
    """Render one role-explicit audit report without authority claims."""

    profile = get_learning_module_audit_profile(profile_key)
    contract = result.get("consumer_contract", {})
    candidate = result.get("candidate", {})
    implementation = result.get("implementation", {})
    formal = result.get("formal_scope", {})
    lines = [
        f"# {profile.report_title_cn}",
        "",
        f"审计时间：`{result.get('evaluated_at_utc')}`",
        "",
        "## 结论",
        "",
        f"证据审计结果为 **{result.get('status')}**。",
        (
            "D6 只校验证据链，不授予模型晋级、辅助运行、分配、"
            "降级或控制权限。"
        ),
        "",
        "## 候选绑定",
        "",
        f"- 候选指纹：`{contract.get('candidate_fingerprint')}`。",
        f"- 数据 manifest：`{contract.get('dataset_manifest_sha256')}`。",
        f"- 数据内容：`{contract.get('dataset_content_sha256')}`。",
        f"- 切分：`{contract.get('dataset_split_sha256')}`。",
        f"- bundle manifest：`{contract.get('bundle_manifest_sha256')}`。",
        f"- 权重：`{contract.get('bundle_weights_sha256')}`。",
        (
            "- 当前实现："
            f"`{implementation.get('current_implementation_sha256')}`；"
            "证据实现："
            f"`{implementation.get('evidence_implementation_sha256')}`。"
        ),
        "",
        "## 正式运行证据",
        "",
        (
            "- 未见 seed："
            f"`{contract.get('unseen_seed_count')}`，"
            f"最低要求 `{profile.minimum_unseen_seed_count}`。"
        ),
        f"- 正式学习 episode：`{contract.get('formal_episode_count')}`。",
        f"- 实际采用：`{contract.get('actual_adoption_count')}`。",
        f"- 后续物理状态窗口：`{contract.get('physical_window_count')}`。",
        f"- 唯一同键 R0：`{contract.get('unique_r0_pair_count')}`。",
        (
            "- paired non-degradation："
            f"`{contract.get('paired_non_degraded_count')}`。"
        ),
        (
            "- 安全与硬约束："
            f"`{contract.get('safety_hard_constraint_passed')}`。"
        ),
        (
            "- formal scope 文件 SHA-256："
            f"`{formal.get('audit_file_sha256')}`。"
        ),
        (
            "- 实际采用证据："
            f"`{contract.get('adoption_evidence_kind')}` / "
            f"`{contract.get('adoption_source_metric')}`。"
        ),
        "",
        "## 阻断项",
        "",
    ]
    blockers = list(result.get("blocker_codes", ()))
    if blockers:
        lines.extend(f"- `{code}`" for code in blockers)
    else:
        lines.append("- 无。")
    candidate_limitations = list(candidate.get("limitations", ()))
    lines.extend(["", "## 候选限制", ""])
    if candidate_limitations:
        lines.extend(f"- `{value}`" for value in candidate_limitations)
    else:
        lines.append("- 无附加静态限制。")
    lines.extend(
        [
            "",
            "## 装配器消费边界",
            "",
            (
                "后续模块装配器必须同时校验本 JSON 的文件 SHA-256、"
                "`content_sha256`、consumer schema、角色、变体、候选指纹、"
                "全部来源摘要及 `d6_external_audit_passed=true`。"
            ),
            (
                "任一字段缺失、类型变化、来源不一致、摘要不匹配或审计失败，"
                "均继续失败关闭。正向测试 fixture 只验证软件合同，不代表实际"
                "模型通过。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def current_implementation_inventory(
    inputs: LearningModuleExternalAuditInputs,
) -> dict[str, Any]:
    """Return the role-frozen current source inventory and digest."""

    hashes: dict[str, str | None] = {}
    for name in inputs.profile.source_files:
        path = inputs.source_root / name
        hashes[name] = _sha256_file(path) if path.is_file() else None
    available = all(value is not None for value in hashes.values())
    digest = (
        _sha256_json(dict(sorted(hashes.items())))
        if available
        else None
    )
    return {
        "source_files": hashes,
        "available": available,
        "implementation_sha256": digest,
    }


def _audit_artifacts(
    inputs: LearningModuleExternalAuditInputs,
    context: _AuditContext,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    json_artifacts = set(inputs.profile.artifact_names) - {
        "bundle_weights",
        "dataset_payload",
        "formal_scope_checksums",
    }
    content_hashed = {
        "full_sample_audit",
        "implementation_evidence",
    }
    for name in inputs.profile.artifact_names:
        binding = inputs.artifacts[name]
        path = inputs.resolve_artifact(name)
        row: dict[str, Any] = {
            "artifact_id": name,
            "path": binding.path,
            "availability": "unavailable",
            "expected_sha256": binding.sha256,
            "actual_sha256": None,
            "sha256_match": None,
            "content_sha256": None,
            "content_sha256_verified": None,
            "blocker_codes": [],
        }
        if not path.is_file():
            code = f"artifact_missing.{name}"
            context.block(code, binding.path)
            row["blocker_codes"].append(code)
            rows.append(row)
            continue
        actual = _sha256_file(path)
        row["availability"] = "available"
        row["actual_sha256"] = actual
        row["sha256_match"] = actual == binding.sha256
        if actual != binding.sha256:
            code = f"artifact_sha256_mismatch.{name}"
            context.block(code, f"{binding.sha256}!={actual}")
            row["blocker_codes"].append(code)
        if name in json_artifacts:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                code = f"artifact_json_invalid.{name}"
                context.block(code, str(exc))
                row["blocker_codes"].append(code)
            else:
                if not isinstance(payload, dict):
                    code = f"artifact_json_invalid.{name}"
                    context.block(code, "JSON root must be an object")
                    row["blocker_codes"].append(code)
                else:
                    payloads[name] = payload
                    if name in content_hashed:
                        claimed = payload.get("content_sha256")
                        row["content_sha256"] = (
                            claimed if isinstance(claimed, str) else None
                        )
                        if (
                            not isinstance(claimed, str)
                            or _SHA256_RE.fullmatch(claimed) is None
                        ):
                            code = (
                                f"artifact_content_sha256_invalid.{name}"
                            )
                            context.block(
                                code,
                                "content_sha256 is missing or invalid",
                            )
                            row["blocker_codes"].append(code)
                            row["content_sha256_verified"] = False
                        else:
                            actual_content = (
                                _sha256_json_without_content(payload)
                            )
                            matched = actual_content == claimed
                            row["content_sha256_verified"] = matched
                            if not matched:
                                code = (
                                    "artifact_content_sha256_mismatch."
                                    f"{name}"
                                )
                                context.block(
                                    code,
                                    f"{claimed}!={actual_content}",
                                )
                                row["blocker_codes"].append(code)
        rows.append(row)
    return rows, payloads


def _audit_d3_candidate(
    inputs: LearningModuleExternalAuditInputs,
    *,
    artifact_rows: Sequence[Mapping[str, Any]],
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    dataset = payloads.get("dataset_manifest")
    full = payloads.get("full_sample_audit")
    bundle = payloads.get("bundle_manifest")
    result: dict[str, Any] = {
        "role": inputs.profile.role,
        "dataset_manifest_sha256": _artifact_actual(
            artifact_rows,
            "dataset_manifest",
        ),
        "dataset_content_sha256": _artifact_actual(
            artifact_rows,
            "dataset_payload",
        ),
        "dataset_split_sha256": None,
        "bundle_manifest_sha256": _artifact_actual(
            artifact_rows,
            "bundle_manifest",
        ),
        "bundle_weights_sha256": _artifact_actual(
            artifact_rows,
            "bundle_weights",
        ),
        "training_seed_values": [],
        "declared_external_holdout_seed_values": [],
        "declared_external_holdout_evaluated_seed_count": None,
        "source_git_commit": None,
        "candidate_lifecycle": None,
        "candidate_maximum_mode": None,
        "limitations": [],
    }
    if dataset is None or full is None or bundle is None:
        context.block(
            "candidate_static_evidence_unavailable",
            "D3 dataset, full-sample audit, or bundle manifest is unavailable",
        )
        return result

    if dataset.get("schema_version") != "d3_learning_dataset_v2":
        context.block(
            "dataset_schema_mismatch",
            str(dataset.get("schema_version")),
        )
    split_hash = _strict_sha(
        dataset.get("split_hash"),
        "dataset_split_sha256_invalid",
        context,
    )
    frames_sha = _strict_sha(
        dataset.get("frames_sha256"),
        "dataset_content_sha256_invalid",
        context,
    )
    result["dataset_split_sha256"] = split_hash
    payload_sha = result["dataset_content_sha256"]
    if frames_sha is not None and frames_sha != payload_sha:
        context.block(
            "dataset_payload_lineage_mismatch",
            f"{frames_sha}!={payload_sha}",
        )
    seed_values = _d3_dataset_seed_values(dataset, context)
    result["training_seed_values"] = seed_values

    if full.get("schema_version") != (
        "d3.assignment-full-sample-audit.v1"
    ):
        context.block(
            "full_sample_audit_schema_mismatch",
            str(full.get("schema_version")),
        )
    audit = _mapping(full.get("audit"))
    if (
        audit.get("passed") is not True
        or _strict_int_value(audit.get("violation_count")) != 0
    ):
        context.block(
            "full_sample_audit_not_clean",
            json.dumps(audit, sort_keys=True),
        )
    integrity = _mapping(full.get("artifact_integrity"))
    if (
        integrity.get("source_artifacts_unchanged") is not True
        or integrity.get("formal_source_data_modified") is not False
        or integrity.get("dataset_manifest_frames_binding_valid") is not True
    ):
        context.block(
            "dataset_artifact_integrity_not_verified",
            "D3 full-sample artifact integrity is incomplete",
        )
    bindings = _mapping(full.get("actual_bindings"))
    full_dataset_manifest = bindings.get("dataset_manifest_sha256")
    full_frames = bindings.get("dataset_frames_sha256")
    full_split = bindings.get("dataset_split_hash")
    expected_bindings = {
        "dataset_manifest_sha256": result["dataset_manifest_sha256"],
        "dataset_frames_sha256": result["dataset_content_sha256"],
        "dataset_split_hash": split_hash,
    }
    actual_bindings = {
        "dataset_manifest_sha256": full_dataset_manifest,
        "dataset_frames_sha256": full_frames,
        "dataset_split_hash": full_split,
    }
    if actual_bindings != expected_bindings:
        context.block(
            "dataset_full_sample_lineage_mismatch",
            json.dumps(
                {
                    "expected": expected_bindings,
                    "observed": actual_bindings,
                },
                sort_keys=True,
            ),
        )
    result["source_git_commit"] = bindings.get("source_git_commit")

    if bundle.get("bundle_schema_version") != (
        "d3_learning_model_bundle_v3"
    ):
        context.block(
            "bundle_schema_mismatch",
            str(bundle.get("bundle_schema_version")),
        )
    state = _mapping(bundle.get("state_dict"))
    if (
        state.get("file") != "state_dict.pt"
        or state.get("sha256") != result["bundle_weights_sha256"]
    ):
        context.block(
            "bundle_weights_lineage_mismatch",
            json.dumps(state, sort_keys=True),
        )
    provenance = _mapping(bundle.get("provenance"))
    if (
        provenance.get("dataset_manifest_sha256")
        != result["dataset_manifest_sha256"]
        or bundle.get("dataset_frames_sha256")
        != result["dataset_content_sha256"]
        or bundle.get("split_hash") != split_hash
    ):
        context.block(
            "bundle_dataset_lineage_mismatch",
            "D3 bundle does not bind the audited dataset and split",
        )
    if result["source_git_commit"] != provenance.get(
        "repository_git_commit"
    ):
        context.block(
            "bundle_source_commit_mismatch",
            f"{result['source_git_commit']}!="
            f"{provenance.get('repository_git_commit')}",
        )
    admission = _mapping(bundle.get("admission"))
    result["candidate_lifecycle"] = admission.get("stage")
    modes = admission.get("allowed_modes")
    result["candidate_maximum_mode"] = (
        modes[0]
        if isinstance(modes, list) and len(modes) == 1
        else modes
    )
    external = _strict_int_sequence(
        admission.get("external_holdout_seed_values"),
        context=context,
        code="bundle_external_holdout_seed_values_invalid",
    )
    result["declared_external_holdout_seed_values"] = external or []
    promotion = _mapping(bundle.get("promotion_manifest"))
    evaluated = _strict_int_value(promotion.get("unseen_seed_count"))
    result["declared_external_holdout_evaluated_seed_count"] = evaluated
    if (
        admission.get("stage") == "development"
        or admission.get("assist_authorized") is not True
        or promotion.get("promotion_status") != "qualified"
    ):
        result["limitations"].append(
            "candidate_bundle_development_shadow_only"
        )
    if evaluated == 0:
        result["limitations"].append(
            "candidate_manifest_formal_holdout_evaluated_zero"
        )
    return result


def _audit_d4_candidate(
    inputs: LearningModuleExternalAuditInputs,
    *,
    artifact_rows: Sequence[Mapping[str, Any]],
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    dataset = payloads.get("dataset_manifest")
    full = payloads.get("full_sample_audit")
    bundle = payloads.get("bundle_manifest")
    readiness = payloads.get("model_readiness")
    result: dict[str, Any] = {
        "role": inputs.profile.role,
        "dataset_manifest_sha256": _artifact_actual(
            artifact_rows,
            "dataset_manifest",
        ),
        "dataset_content_sha256": None,
        "dataset_split_sha256": None,
        "bundle_manifest_sha256": _artifact_actual(
            artifact_rows,
            "bundle_manifest",
        ),
        "bundle_weights_sha256": _artifact_actual(
            artifact_rows,
            "bundle_weights",
        ),
        "training_seed_values": [],
        "declared_external_holdout_seed_values": [],
        "declared_external_holdout_evaluated_seed_count": None,
        "source_git_commit": None,
        "candidate_lifecycle": None,
        "candidate_maximum_mode": None,
        "limitations": [],
    }
    if (
        dataset is None
        or full is None
        or bundle is None
        or readiness is None
    ):
        context.block(
            "candidate_static_evidence_unavailable",
            "D4 dataset, full-sample audit, bundle, or readiness is unavailable",
        )
        return result

    if dataset.get("schema") != "d4-region-learning-dataset-v1":
        context.block(
            "dataset_schema_mismatch",
            str(dataset.get("schema")),
        )
    dataset_digest = _strict_sha(
        dataset.get("dataset_sha256"),
        "dataset_content_sha256_invalid",
        context,
    )
    result["dataset_content_sha256"] = dataset_digest
    if dataset_digest is not None:
        content = dict(dataset)
        content.pop("dataset_sha256", None)
        content.pop("dataset_id", None)
        recomputed = _sha256_json(content)
        if recomputed != dataset_digest:
            context.block(
                "dataset_content_sha256_mismatch",
                f"{dataset_digest}!={recomputed}",
            )
    split = _mapping(dataset.get("split"))
    split_hash = _strict_sha(
        split.get("split_sha256"),
        "dataset_split_sha256_invalid",
        context,
    )
    result["dataset_split_sha256"] = split_hash
    seed_values = _d4_dataset_seed_values(split, context)
    result["training_seed_values"] = seed_values

    if full.get("schema") != (
        "d4-region-resource-full-sample-admission-audit-v1"
    ):
        context.block(
            "full_sample_audit_schema_mismatch",
            str(full.get("schema")),
        )
    audit = _mapping(full.get("audit"))
    if (
        audit.get("passed") is not True
        or _strict_int_value(audit.get("violation_count")) != 0
    ):
        context.block(
            "full_sample_audit_not_clean",
            json.dumps(audit, sort_keys=True),
        )
    integrity = _mapping(full.get("artifact_integrity"))
    formal_integrity = _mapping(integrity.get("formal"))
    if (
        formal_integrity.get("artifact_inventory_exact") is not True
        or formal_integrity.get("source_unchanged_during_audit") is not True
        or _strict_int_value(
            formal_integrity.get("episode_sha256_mismatch_count")
        )
        != 0
        or integrity.get("formal_900_episode_dataset_modified") is not False
    ):
        context.block(
            "dataset_artifact_integrity_not_verified",
            "D4 formal corpus integrity is incomplete",
        )
    bindings = _mapping(full.get("actual_bindings"))
    if (
        bindings.get("formal_dataset_sha256") != dataset_digest
        or bindings.get("formal_manifest_sha256")
        != result["dataset_manifest_sha256"]
    ):
        context.block(
            "dataset_full_sample_lineage_mismatch",
            "D4 full-sample audit does not bind the selected dataset",
        )
    source_commit = bindings.get("formal_source_git_commit")
    result["source_git_commit"] = source_commit

    if bundle.get("schema") != "d4-region-resource-model-bundle-v2":
        context.block(
            "bundle_schema_mismatch",
            str(bundle.get("schema")),
        )
    if (
        bundle.get("state_dict_file") != "state_dict.pt"
        or bundle.get("state_dict_sha256")
        != result["bundle_weights_sha256"]
    ):
        context.block(
            "bundle_weights_lineage_mismatch",
            "D4 bundle state digest differs from the selected weights",
        )
    if (
        bundle.get("training_manifest_sha256")
        != result["dataset_manifest_sha256"]
        or bundle.get("training_dataset_sha256") != dataset_digest
        or bundle.get("training_split_sha256") != split_hash
    ):
        context.block(
            "bundle_dataset_lineage_mismatch",
            "D4 bundle does not bind the audited dataset and split",
        )
    if readiness.get("schema") != "d4-region-bc-model-readiness-v1":
        context.block(
            "model_readiness_schema_mismatch",
            str(readiness.get("schema")),
        )
    if (
        readiness.get("model_version") != bundle.get("model_version")
        or readiness.get("state_dict_sha256")
        != result["bundle_weights_sha256"]
        or readiness.get("training_dataset_sha256") != dataset_digest
        or readiness.get("training_split_sha256") != split_hash
    ):
        context.block(
            "model_readiness_lineage_mismatch",
            "D4 readiness does not bind the selected bundle and dataset",
        )
    evaluated = _strict_int_value(
        readiness.get("final_holdout_evaluated_seed_count")
    )
    result["declared_external_holdout_evaluated_seed_count"] = evaluated
    reserved = _strict_int_sequence(
        _mapping(
            _mapping(full.get("formal_corpus")).get("canonical")
        )
        .get("binding", {})
        .get("reserved_evaluation_seeds"),
        context=context,
        code="full_sample_reserved_seed_values_invalid",
    )
    result["declared_external_holdout_seed_values"] = reserved or []
    result["candidate_lifecycle"] = bundle.get("lifecycle_stage")
    result["candidate_maximum_mode"] = bundle.get("maximum_advisor_mode")
    if (
        bundle.get("lifecycle_stage") == "development"
        or bundle.get("maximum_advisor_mode") == "shadow"
        or readiness.get("assist_eligible") is not True
    ):
        result["limitations"].append(
            "candidate_bundle_development_shadow_only"
        )
    if evaluated == 0:
        result["limitations"].append(
            "candidate_manifest_formal_holdout_evaluated_zero"
        )
    if bundle.get("action_diversity_sufficient") is not True:
        result["limitations"].append(
            "candidate_action_diversity_insufficient"
        )
    if bundle.get("strategy_capability_claim_allowed") is not True:
        result["limitations"].append(
            "candidate_strategy_capability_not_demonstrated"
        )
    return result


def _audit_implementation(
    inputs: LearningModuleExternalAuditInputs,
    *,
    candidate: Mapping[str, Any],
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    inventory = current_implementation_inventory(inputs)
    current_sha = inventory["implementation_sha256"]
    result: dict[str, Any] = {
        "available": inventory["available"],
        "current_source_files": inventory["source_files"],
        "current_implementation_sha256": current_sha,
        "expected_current_implementation_sha256": (
            inputs.expected_current_implementation_sha256
        ),
        "evidence_source_files": {},
        "evidence_implementation_sha256": None,
        "source_git_commit": None,
        "lineage_verified": False,
    }
    if not inventory["available"]:
        missing = sorted(
            name
            for name, digest in inventory["source_files"].items()
            if digest is None
        )
        context.block(
            "current_implementation_source_unavailable",
            ",".join(missing),
        )
    if current_sha != inputs.expected_current_implementation_sha256:
        context.block(
            "current_implementation_sha256_mismatch",
            f"{inputs.expected_current_implementation_sha256}!={current_sha}",
        )
    evidence = payloads.get("implementation_evidence")
    if evidence is None:
        context.block(
            "implementation_evidence_unavailable",
            "versioned implementation evidence is missing",
        )
        return result
    expected_fields = {
        "schema_version",
        "role",
        "source_git_commit",
        "source_files",
        "implementation_sha256",
        "dataset_manifest_sha256",
        "dataset_content_sha256",
        "dataset_split_sha256",
        "bundle_manifest_sha256",
        "bundle_weights_sha256",
        "content_sha256",
    }
    if set(evidence) != expected_fields:
        context.block(
            "implementation_evidence_fields_mismatch",
            ",".join(sorted(set(evidence) ^ expected_fields)),
        )
    if evidence.get("schema_version") != (
        MODULE_IMPLEMENTATION_EVIDENCE_SCHEMA_VERSION
    ):
        context.block(
            "implementation_evidence_schema_mismatch",
            str(evidence.get("schema_version")),
        )
    if evidence.get("role") != inputs.profile.role:
        context.block(
            "implementation_evidence_role_mismatch",
            str(evidence.get("role")),
        )
    evidence_files = evidence.get("source_files")
    if not isinstance(evidence_files, Mapping):
        context.block(
            "implementation_evidence_source_files_invalid",
            "source_files must be an object",
        )
        evidence_files = {}
    evidence_files = dict(evidence_files)
    result["evidence_source_files"] = evidence_files
    if set(evidence_files) != set(inputs.profile.source_files):
        context.block(
            "implementation_evidence_source_inventory_mismatch",
            ",".join(
                sorted(
                    set(evidence_files) ^ set(inputs.profile.source_files)
                )
            ),
        )
    if any(
        not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None
        for value in evidence_files.values()
    ):
        context.block(
            "implementation_evidence_source_sha256_invalid",
            "one or more source digests are invalid",
        )
    evidence_sha = evidence.get("implementation_sha256")
    result["evidence_implementation_sha256"] = evidence_sha
    computed_evidence_sha = _sha256_json(dict(sorted(evidence_files.items())))
    if (
        not isinstance(evidence_sha, str)
        or _SHA256_RE.fullmatch(evidence_sha) is None
        or evidence_sha != computed_evidence_sha
    ):
        context.block(
            "implementation_evidence_digest_invalid",
            f"{evidence_sha}!={computed_evidence_sha}",
        )
    source_commit = evidence.get("source_git_commit")
    result["source_git_commit"] = source_commit
    if (
        not isinstance(source_commit, str)
        or _GIT_COMMIT_RE.fullmatch(source_commit) is None
    ):
        context.block(
            "implementation_evidence_source_commit_invalid",
            str(source_commit),
        )
    expected_candidate = {
        "dataset_manifest_sha256": candidate.get(
            "dataset_manifest_sha256"
        ),
        "dataset_content_sha256": candidate.get(
            "dataset_content_sha256"
        ),
        "dataset_split_sha256": candidate.get("dataset_split_sha256"),
        "bundle_manifest_sha256": candidate.get(
            "bundle_manifest_sha256"
        ),
        "bundle_weights_sha256": candidate.get(
            "bundle_weights_sha256"
        ),
    }
    observed_candidate = {
        name: evidence.get(name) for name in expected_candidate
    }
    if observed_candidate != expected_candidate:
        context.block(
            "implementation_candidate_lineage_mismatch",
            json.dumps(
                {
                    "expected": expected_candidate,
                    "observed": observed_candidate,
                },
                sort_keys=True,
            ),
        )
    if (
        current_sha is None
        or evidence_sha != current_sha
        or evidence_files != inventory["source_files"]
    ):
        context.block(
            "implementation_lineage_mismatch",
            f"evidence={evidence_sha};current={current_sha}",
        )
    if candidate.get("source_git_commit") != source_commit:
        context.block(
            "implementation_dataset_source_commit_mismatch",
            f"{source_commit}!={candidate.get('source_git_commit')}",
        )
    result["lineage_verified"] = not any(
        code.startswith("implementation_")
        or code.startswith("current_implementation_")
        for code in context.blockers
    )
    return result


def _audit_formal_scope(
    inputs: LearningModuleExternalAuditInputs,
    *,
    candidate: Mapping[str, Any],
    implementation: Mapping[str, Any],
    artifact_rows: Sequence[Mapping[str, Any]],
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    report = payloads.get("formal_scope_audit")
    report_sha = _artifact_actual(artifact_rows, "formal_scope_audit")
    checksums_sha = _artifact_actual(
        artifact_rows,
        "formal_scope_checksums",
    )
    result: dict[str, Any] = {
        "available": report is not None,
        "audit_file_sha256": report_sha,
        "checksums_file_sha256": checksums_sha,
        "checksums_verified": None,
        "source_git_commit": None,
        "formal_episode_count": None,
        "unseen_seed_values": None,
        "unseen_seed_count": None,
        "actual_adoption_count": None,
        "physical_window_count": None,
        "unique_r0_pair_count": None,
        "paired_non_degraded_count": None,
        "safety_hard_constraint_passed": None,
        "audit_passed": None,
    }
    checksums_path = inputs.resolve_artifact("formal_scope_checksums")
    if checksums_path.is_file() and report_sha is not None:
        checksums = _parse_sha256sums(checksums_path)
        report_name = inputs.resolve_artifact("formal_scope_audit").name
        result["checksums_verified"] = (
            checksums.get(report_name) == report_sha
        )
        if not result["checksums_verified"]:
            context.block(
                "formal_scope_checksum_mismatch",
                f"{report_name}:{checksums.get(report_name)}!={report_sha}",
            )
    else:
        context.block(
            "formal_scope_checksum_unavailable",
            "formal scope report or checksum file is unavailable",
        )
    if report is None:
        context.block(
            "formal_scope_evidence_unavailable",
            "formal scope audit JSON is unavailable",
        )
        _block_unavailable_formal_fields(context)
        return result
    if report.get("schema_version") != (
        LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION
    ):
        context.block(
            "formal_scope_schema_mismatch",
            str(report.get("schema_version")),
        )
    if (
        report.get("verdict") != "pass"
        or report.get("fail_closed") is not False
        or report.get("formal_evidence_eligible") is not True
        or report.get("evidence_admission_allowed") is not True
    ):
        context.block(
            "formal_scope_audit_not_passed",
            str(report.get("verdict")),
        )
    if report.get("default_control_path_modified") is not False:
        context.block(
            "formal_scope_default_path_modified",
            str(report.get("default_control_path_modified")),
        )
    promotion = _mapping(report.get("model_promotion"))
    if (
        promotion.get("availability") != "unavailable"
        or promotion.get("allowed") is not False
    ):
        context.block(
            "formal_scope_contains_promotion_authority",
            json.dumps(promotion, sort_keys=True),
        )
    if report.get("blockers") not in ([], ()):
        context.block(
            "formal_scope_contains_blockers",
            json.dumps(report.get("blockers"), sort_keys=True),
        )

    learned = _mapping(report.get("learned_scope"))
    learned_blockers = learned.get("blockers")
    if learned_blockers not in ([], ()):
        context.block(
            "formal_scope_learned_scope_contains_blockers",
            json.dumps(learned_blockers, sort_keys=True),
        )
    result["source_git_commit"] = learned.get("source_git_commit")
    if learned.get("scope_variants") != [inputs.profile.variant]:
        context.block(
            "formal_scope_variant_mismatch",
            json.dumps(learned.get("scope_variants")),
        )
    if (
        learned.get("formal_evidence_eligible") is not True
        or learned.get("bundle_binding_status")
        != "available_and_valid"
        or learned.get("scope_completeness_status") != "complete"
    ):
        context.block(
            "formal_scope_learned_scope_not_complete",
            "learned scope is not complete and eligible",
        )
    if result["source_git_commit"] != implementation.get(
        "source_git_commit"
    ):
        context.block(
            "formal_scope_source_commit_mismatch",
            f"{result['source_git_commit']}!="
            f"{implementation.get('source_git_commit')}",
        )
    _audit_formal_bundle_binding(
        inputs,
        candidate=candidate,
        learned=learned,
        context=context,
    )

    cells_raw = learned.get("cells")
    cells = cells_raw if isinstance(cells_raw, list) else []
    if not isinstance(cells_raw, list):
        context.block(
            "formal_scope_cells_invalid",
            "learned_scope.cells must be an array",
        )
    expected_count = _strict_int_value(
        learned.get("expected_cell_count")
    )
    accepted_count = _strict_int_value(
        learned.get("accepted_cell_count")
    )
    if (
        expected_count is None
        or expected_count <= 0
        or accepted_count != expected_count
        or len(cells) != expected_count
    ):
        context.block(
            "formal_scope_cell_count_mismatch",
            f"expected={expected_count};accepted={accepted_count};"
            f"cells={len(cells)}",
        )
    result["formal_episode_count"] = (
        len(cells) if isinstance(cells_raw, list) else None
    )

    seed_values: list[int] = []
    comparison_keys: list[str] = []
    adoption_count = 0
    physical_count = 0
    safety_passed = True
    for index, cell in enumerate(cells):
        if not isinstance(cell, Mapping):
            context.block(
                "formal_scope_cell_type_invalid",
                str(index),
            )
            safety_passed = False
            continue
        seed = _strict_int_value(cell.get("seed"))
        if seed is None:
            context.block(
                "formal_scope_seed_invalid",
                str(cell.get("seed")),
            )
        else:
            seed_values.append(seed)
        key = cell.get("comparison_key")
        if not isinstance(key, str) or not key:
            context.block(
                "formal_scope_comparison_key_invalid",
                str(key),
            )
        else:
            comparison_keys.append(key)
        if cell.get("variant") != inputs.profile.variant:
            context.block(
                "formal_scope_cell_variant_mismatch",
                str(cell.get("variant")),
            )
        failure_reasons = cell.get("failure_reasons")
        if (
            cell.get("evidence_status") != "accepted"
            or failure_reasons not in ([], ())
        ):
            context.block(
                "formal_scope_cell_not_accepted",
                str(cell.get("cell_id")),
            )
            safety_passed = False
        adoption_status = cell.get("assist_adoption_status")
        if adoption_status == "actual_assist_adopted":
            adoption_count += 1
        else:
            context.block(
                "actual_adoption_missing_or_not_applied",
                f"{cell.get('cell_id')}:{adoption_status}",
            )
            safety_passed = False
        if cell.get("physical_result_status") == "available":
            physical_count += 1
        else:
            context.block(
                "physical_state_window_unavailable",
                str(cell.get("cell_id")),
            )
        if cell.get("online_truth_status") != "zero_verified":
            context.block(
                "online_truth_safety_not_verified",
                str(cell.get("cell_id")),
            )
            safety_passed = False
        learning_evidence = _mapping(cell.get("learning_evidence"))
        if (
            learning_evidence.get("status")
            != "preflight_and_episode_consistent"
            or learning_evidence.get("required_components")
            != [inputs.profile.component]
        ):
            context.block(
                "runtime_ack_or_isolated_adoption_lineage_invalid",
                str(cell.get("cell_id")),
            )
            safety_passed = False
    unique_seed_values = sorted(set(seed_values))
    result["unseen_seed_values"] = unique_seed_values
    result["unseen_seed_count"] = len(unique_seed_values)
    result["actual_adoption_count"] = adoption_count
    result["physical_window_count"] = physical_count
    if len(comparison_keys) != len(set(comparison_keys)):
        context.block(
            "learned_comparison_key_duplicated",
            "learned cells do not have unique comparison keys",
        )
        safety_passed = False
    training_seeds = set(candidate.get("training_seed_values", ()))
    overlap = sorted(training_seeds & set(unique_seed_values))
    if overlap:
        context.block(
            "formal_seed_training_overlap",
            ",".join(str(value) for value in overlap),
        )
    if len(unique_seed_values) < inputs.profile.minimum_unseen_seed_count:
        context.block(
            "minimum_unseen_seed_count_not_met",
            f"{len(unique_seed_values)}<"
            f"{inputs.profile.minimum_unseen_seed_count}",
        )
    if adoption_count != len(cells):
        context.block(
            "actual_adoption_count_incomplete",
            f"{adoption_count}/{len(cells)}",
        )
    if physical_count != len(cells):
        context.block(
            "physical_state_window_count_incomplete",
            f"{physical_count}/{len(cells)}",
        )

    pairing = _mapping(report.get("r0_pairing"))
    pairing_blockers = pairing.get("blockers")
    if pairing_blockers not in ([], ()):
        context.block(
            "r0_pairing_contains_blockers",
            json.dumps(pairing_blockers, sort_keys=True),
        )
    pairs_raw = pairing.get("pairs")
    pairs = pairs_raw if isinstance(pairs_raw, list) else []
    r0_cells = _collect_r0_cells(report, context)
    unique_pairs, non_degraded_pairs = _audit_r0_pairs(
        inputs,
        cells=cells,
        r0_cells=r0_cells,
        pairs=pairs,
        pairing=pairing,
        context=context,
    )
    result["unique_r0_pair_count"] = unique_pairs
    result["paired_non_degraded_count"] = non_degraded_pairs
    result["safety_hard_constraint_passed"] = (
        safety_passed
        and adoption_count == len(cells)
        and physical_count == len(cells)
        and report.get("blockers") in ([], ())
    )
    if result["safety_hard_constraint_passed"] is not True:
        context.block(
            "safety_hard_constraint_not_verified",
            "one or more accepted-cell safety gates are unavailable or failed",
        )
    result["audit_passed"] = not any(
        code.startswith(
            (
                "formal_scope_",
                "actual_adoption_",
                "physical_state_",
                "online_truth_",
                "runtime_ack_",
                "learned_comparison_",
                "formal_seed_",
                "minimum_unseen_",
                "r0_",
                "paired_",
                "safety_",
            )
        )
        for code in context.blockers
    )
    return result


def _audit_formal_bundle_binding(
    inputs: LearningModuleExternalAuditInputs,
    *,
    candidate: Mapping[str, Any],
    learned: Mapping[str, Any],
    context: _AuditContext,
) -> None:
    binding = _mapping(learned.get("bundle_binding"))
    components = _mapping(binding.get("components"))
    component = _mapping(components.get(inputs.profile.component))
    actual = _mapping(component.get("actual"))
    if (
        component.get("available") is not True
        or component.get("manifest_sha256_match") is not True
        or component.get("tree_sha256_match") is not True
        or component.get("file_count_match") is not True
        or component.get("total_size_bytes_match") is not True
    ):
        context.block(
            "formal_scope_bundle_binding_invalid",
            inputs.profile.component,
        )
    if (
        actual.get("manifest_sha256")
        != candidate.get("bundle_manifest_sha256")
    ):
        context.block(
            "formal_scope_candidate_bundle_mismatch",
            f"{actual.get('manifest_sha256')}!="
            f"{candidate.get('bundle_manifest_sha256')}",
        )


def _audit_r0_pairs(
    inputs: LearningModuleExternalAuditInputs,
    *,
    cells: Sequence[Mapping[str, Any]],
    r0_cells: Sequence[Mapping[str, Any]],
    pairs: Sequence[Any],
    pairing: Mapping[str, Any],
    context: _AuditContext,
) -> tuple[int, int]:
    if (
        pairing.get("availability") != "available"
        or pairing.get("all_required_pairs_available") is not True
        or pairing.get("all_required_pairs_non_degraded") is not True
    ):
        context.block(
            "r0_pairing_not_complete",
            str(pairing.get("availability")),
        )
    if (
        _strict_int_value(pairing.get("expected_pair_count"))
        != len(cells)
        or _strict_int_value(pairing.get("available_pair_count"))
        != len(cells)
        or _strict_int_value(pairing.get("non_degraded_pair_count"))
        != len(cells)
        or len(pairs) != len(cells)
    ):
        context.block(
            "r0_pair_count_mismatch",
            f"cells={len(cells)};pairs={len(pairs)}",
        )
    learned_keys = {
        str(cell.get("comparison_key"))
        for cell in cells
        if isinstance(cell, Mapping)
        and isinstance(cell.get("comparison_key"), str)
    }
    learned_cell_ids = {
        str(cell.get("comparison_key")): str(cell.get("cell_id"))
        for cell in cells
        if isinstance(cell, Mapping)
        and isinstance(cell.get("comparison_key"), str)
        and isinstance(cell.get("cell_id"), str)
    }
    r0_by_key: dict[str, list[Mapping[str, Any]]] = {}
    for cell in r0_cells:
        key = cell.get("comparison_key")
        if isinstance(key, str):
            r0_by_key.setdefault(key, []).append(cell)
    pair_keys: list[str] = []
    r0_cell_ids: list[str] = []
    unique_count = 0
    non_degraded_count = 0
    for index, pair in enumerate(pairs):
        if not isinstance(pair, Mapping):
            context.block("r0_pair_type_invalid", str(index))
            continue
        key = pair.get("comparison_key")
        if isinstance(key, str):
            pair_keys.append(key)
        expected_r0 = r0_by_key.get(str(key), [])
        if len(expected_r0) != 1:
            context.block(
                "unique_same_key_r0_not_verified",
                f"{key}:{len(expected_r0)}",
            )
            continue
        expected_r0_cell_id = expected_r0[0].get("cell_id")
        r0_cell_id = pair.get("r0_cell_id")
        if isinstance(r0_cell_id, str):
            r0_cell_ids.append(r0_cell_id)
        if (
            pair.get("variant") != inputs.profile.variant
            or pair.get("availability") != "available"
            or pair.get("non_degraded") is not True
            or pair.get("learned_cell_id")
            != learned_cell_ids.get(str(key))
            or not isinstance(pair.get("r0_cell_id"), str)
            or not pair.get("r0_cell_id")
            or pair.get("r0_cell_id") != expected_r0_cell_id
            or expected_r0[0].get("variant") != "R0"
            or expected_r0[0].get("evidence_status") != "accepted"
            or pair.get("failure_reasons") not in ([], ())
        ):
            context.block(
                "r0_pair_invalid_or_non_degraded_false",
                str(key),
            )
            continue
        comparisons = pair.get("metric_comparisons")
        if not isinstance(comparisons, Mapping):
            context.block(
                "paired_metric_comparisons_unavailable",
                str(key),
            )
            continue
        required_names = (
            "intercepted_target_count",
            "offline_proximity_unique_target_count",
        )
        required = [comparisons.get(name) for name in required_names]
        if any(
            not isinstance(value, Mapping)
            or value.get("required") is not True
            or value.get("availability") != "available"
            or value.get("non_degraded") is not True
            for value in required
        ):
            context.block(
                "paired_required_metric_not_non_degraded",
                str(key),
            )
            continue
        unique_count += 1
        non_degraded_count += 1
    if len(pair_keys) != len(set(pair_keys)):
        context.block(
            "r0_comparison_key_duplicated",
            "R0 pair comparison keys are duplicated",
        )
    if len(r0_cell_ids) != len(set(r0_cell_ids)):
        context.block(
            "r0_cell_id_duplicated",
            "one R0 cell is reused by multiple comparison keys",
        )
    if set(pair_keys) != learned_keys:
        context.block(
            "r0_comparison_key_inventory_mismatch",
            json.dumps(
                {
                    "learned": sorted(learned_keys),
                    "paired": sorted(set(pair_keys)),
                },
                sort_keys=True,
            ),
        )
    return unique_count, non_degraded_count


def _assemble_consumer_fields(
    inputs: LearningModuleExternalAuditInputs,
    *,
    candidate: Mapping[str, Any],
    implementation: Mapping[str, Any],
    formal: Mapping[str, Any],
    artifact_rows: Sequence[Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    fingerprint_payload = {
        "role": inputs.profile.role,
        "variant": inputs.profile.variant,
        "dataset_manifest_sha256": candidate.get(
            "dataset_manifest_sha256"
        ),
        "dataset_content_sha256": candidate.get(
            "dataset_content_sha256"
        ),
        "dataset_split_sha256": candidate.get("dataset_split_sha256"),
        "bundle_manifest_sha256": candidate.get(
            "bundle_manifest_sha256"
        ),
        "bundle_weights_sha256": candidate.get(
            "bundle_weights_sha256"
        ),
        "implementation_sha256": implementation.get(
            "evidence_implementation_sha256"
        ),
    }
    fingerprint_available = all(
        isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None
        for name, value in fingerprint_payload.items()
        if name not in {"role", "variant"}
    )
    fingerprint = (
        f"sha256:{_sha256_json(fingerprint_payload)}"
        if fingerprint_available
        else None
    )
    fields = {
        "role": inputs.profile.role,
        "variant": inputs.profile.variant,
        "formal_profile_version": inputs.formal_profile_version,
        "adoption_evidence_kind": (
            inputs.profile.adoption_evidence_kind
        ),
        "adoption_source_metric": inputs.profile.adoption_source_metric,
        "candidate_fingerprint": fingerprint,
        "dataset_manifest_sha256": candidate.get(
            "dataset_manifest_sha256"
        ),
        "dataset_content_sha256": candidate.get(
            "dataset_content_sha256"
        ),
        "dataset_split_sha256": candidate.get("dataset_split_sha256"),
        "bundle_manifest_sha256": candidate.get(
            "bundle_manifest_sha256"
        ),
        "bundle_weights_sha256": candidate.get(
            "bundle_weights_sha256"
        ),
        "implementation_sha256": implementation.get(
            "evidence_implementation_sha256"
        ),
        "source_git_commit": implementation.get("source_git_commit"),
        "formal_scope_audit_sha256": formal.get("audit_file_sha256"),
        "formal_scope_checksums_sha256": formal.get(
            "checksums_file_sha256"
        ),
        "formal_scope_checksum_verified": formal.get(
            "checksums_verified"
        ),
        "unseen_seed_count": formal.get("unseen_seed_count"),
        "formal_episode_count": formal.get("formal_episode_count"),
        "actual_adoption_count": formal.get("actual_adoption_count"),
        "physical_window_count": formal.get("physical_window_count"),
        "unique_r0_pair_count": formal.get("unique_r0_pair_count"),
        "paired_non_degraded_count": formal.get(
            "paired_non_degraded_count"
        ),
        "safety_hard_constraint_passed": formal.get(
            "safety_hard_constraint_passed"
        ),
        "formal_scope_audit_passed": formal.get("audit_passed"),
        "field_availability": {},
    }
    fields["field_availability"] = {
        name: _availability(value)
        for name, value in fields.items()
        if name
        not in {
            "role",
            "variant",
            "formal_profile_version",
            "field_availability",
        }
    }
    if fingerprint is None:
        context.block(
            "candidate_fingerprint_unavailable",
            "one or more source digests are unavailable",
        )
    return fields


def _collect_r0_cells(
    report: Mapping[str, Any],
    context: _AuditContext,
) -> list[Mapping[str, Any]]:
    raw_scopes = report.get("r0_scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes:
        context.block(
            "r0_scope_evidence_unavailable",
            "formal report does not contain an R0 scope",
        )
        return []
    cells: list[Mapping[str, Any]] = []
    for index, raw_scope in enumerate(raw_scopes):
        if not isinstance(raw_scope, Mapping):
            context.block("r0_scope_type_invalid", str(index))
            continue
        if raw_scope.get("blockers") not in ([], ()):
            context.block(
                "r0_scope_contains_blockers",
                f"{index}:{raw_scope.get('blockers')}",
            )
        raw_cells = raw_scope.get("cells")
        if not isinstance(raw_cells, list):
            context.block("r0_scope_cells_invalid", str(index))
            continue
        for cell_index, cell in enumerate(raw_cells):
            if not isinstance(cell, Mapping):
                context.block(
                    "r0_scope_cell_type_invalid",
                    f"{index}:{cell_index}",
                )
                continue
            cells.append(cell)
    return cells


def _block_unavailable_formal_fields(context: _AuditContext) -> None:
    for code in (
        "formal_unseen_seed_count_unavailable",
        "formal_episode_count_unavailable",
        "actual_adoption_unavailable",
        "physical_state_window_unavailable",
        "unique_same_key_r0_unavailable",
        "paired_non_degradation_unavailable",
        "safety_hard_constraint_unavailable",
    ):
        context.block(code, "formal scope evidence is unavailable")


def _d3_dataset_seed_values(
    dataset: Mapping[str, Any],
    context: _AuditContext,
) -> list[int]:
    split_values = dataset.get("split_seed_values")
    if not isinstance(split_values, Mapping):
        context.block(
            "dataset_seed_split_invalid",
            "split_seed_values is missing",
        )
        return []
    values: list[int] = []
    seen: set[int] = set()
    for split in ("train", "validation", "test"):
        seeds = _strict_int_sequence(
            split_values.get(split),
            context=context,
            code=f"dataset_seed_split_invalid.{split}",
        )
        if seeds is None:
            continue
        overlap = seen & set(seeds)
        if overlap:
            context.block(
                "dataset_seed_split_overlap",
                ",".join(str(value) for value in sorted(overlap)),
            )
        seen.update(seeds)
        values.extend(seeds)
    if _strict_int_value(dataset.get("unique_seed_count")) != len(seen):
        context.block(
            "dataset_unique_seed_count_mismatch",
            f"{dataset.get('unique_seed_count')}!={len(seen)}",
        )
    return sorted(seen)


def _d4_dataset_seed_values(
    split: Mapping[str, Any],
    context: _AuditContext,
) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    for field in ("train_seeds", "validation_seeds", "test_seeds"):
        seeds = _strict_int_sequence(
            split.get(field),
            context=context,
            code=f"dataset_seed_split_invalid.{field}",
        )
        if seeds is None:
            continue
        overlap = seen & set(seeds)
        if overlap:
            context.block(
                "dataset_seed_split_overlap",
                ",".join(str(value) for value in sorted(overlap)),
            )
        seen.update(seeds)
        values.extend(seeds)
    if _strict_int_value(split.get("unique_seed_count")) != len(seen):
        context.block(
            "dataset_unique_seed_count_mismatch",
            f"{split.get('unique_seed_count')}!={len(seen)}",
        )
    return sorted(seen)


def _strict_sha(
    value: Any,
    code: str,
    context: _AuditContext,
) -> str | None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        context.block(code, str(value))
        return None
    return value


def _strict_int_value(value: Any) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return int(value)


def _strict_int_sequence(
    value: Any,
    *,
    context: _AuditContext,
    code: str,
) -> list[int] | None:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or any(type(item) is not int or item < 0 for item in value)
    ):
        context.block(code, repr(value))
        return None
    result = [int(item) for item in value]
    if len(result) != len(set(result)):
        context.block(code, "duplicate values")
        return None
    return result


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _artifact_actual(
    rows: Sequence[Mapping[str, Any]],
    name: str,
) -> str | None:
    for row in rows:
        if row.get("artifact_id") == name:
            value = row.get("actual_sha256")
            return value if isinstance(value, str) else None
    return None


def _availability(value: Any) -> dict[str, Any]:
    return {
        "availability": (
            "available" if value is not None else "unavailable"
        ),
        "unavailable_reason": (
            None if value is not None else "evidence_unavailable"
        ),
        "value": value,
    }


def _safe_child(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise LearningModuleExternalAuditError(
            "input_path_escapes_repository",
            relative,
        ) from exc
    return candidate


def _parse_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        return result
    for line in lines:
        if "  " not in line:
            continue
        digest, name = line.split("  ", 1)
        if _SHA256_RE.fullmatch(digest) and name and name not in result:
            result[name] = digest
    return result


def _with_content_sha256(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha256_json(result)
    return result


def _sha256_json_without_content(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    return _sha256_json(unsigned)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise LearningModuleExternalAuditError(
            "canonical_json_invalid",
            str(exc),
        ) from exc
    return text.encode("utf-8")


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "D3_A1_PROFILE",
    "D4_A2_PROFILE",
    "MODULE_IMPLEMENTATION_EVIDENCE_SCHEMA_VERSION",
    "LearningModuleAuditProfile",
    "LearningModuleExternalAuditArtifact",
    "LearningModuleExternalAuditError",
    "LearningModuleExternalAuditInputs",
    "audit_learning_module_external_evidence",
    "current_implementation_inventory",
    "get_learning_module_audit_profile",
    "load_learning_module_external_audit_inputs",
    "render_learning_module_external_audit_markdown",
    "write_learning_module_external_audit_report",
]
