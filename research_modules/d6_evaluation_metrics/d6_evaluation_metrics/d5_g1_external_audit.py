"""Deterministic, fail-closed external audit for D5 G1 evidence.

This module is a read-only D6 boundary. It authenticates one frozen D5 model,
its held-out report, paired-shadow report, registry records, and the current
runtime implementation. A passing result means only that the evidence bundle
is internally consistent and meets the frozen audit profile. D6 never grants
model promotion, G1 assist, control authority, or a default-path change.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION = "d6.d5-g1-external-audit.v1"
D5_G1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION = (
    "d6.d5-g1-external-audit-input.v1"
)
D5_G1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION = (
    "d6.d5-g1-external-audit-consumer.v1"
)
D5_G1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION = (
    "d6.d5-g1-formal-heldout-paired-shadow.v1"
)

_D5_MODEL_BUNDLE_SCHEMA = "d5.tracklet-model-bundle.v3"
_D5_HELDOUT_SCHEMA = "d5.tracklet-heldout-model-evaluation.v1"
_D5_PAIRED_SCHEMA = "d5.tracklet-paired-shadow.v2"
_D5_PAIRED_INPUT_SCHEMA = "d5.tracklet-paired-shadow-input.v1"
_D5_FROZEN_REFERENCE_SCHEMA = "d5.frozen-tracklet-audit-reference.v1"
_D5_FROZEN_EVIDENCE_SCHEMA = "d5.frozen-tracklet-audit-evidence.v1"

_REQUIRED_ARTIFACT_NAMES = (
    "registry_reference",
    "registry_audit_evidence",
    "registry_checksums",
    "bundle_manifest",
    "bundle_weights",
    "bundle_checksums",
    "heldout_report",
    "paired_shadow_report",
    "paired_shadow_lineage",
)
_JSON_ARTIFACT_NAMES = (
    "registry_reference",
    "registry_audit_evidence",
    "bundle_manifest",
    "heldout_report",
    "paired_shadow_report",
)
_CONTENT_HASHED_ARTIFACT_NAMES = (
    "heldout_report",
    "paired_shadow_report",
)
_RUNTIME_IMPLEMENTATION_FILES = (
    "scalable_3d_adapter.py",
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_g1_evidence_assembler.py",
    "tracklet_gnn.py",
    "tracklet_heldout_evaluation.py",
    "tracklet_model_bundle.py",
    "tracklet_paired_shadow.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_MODEL_IMPLEMENTATION_FILES = (
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_HELDOUT_METRIC_THRESHOLDS = {
    "f1": ("minimum_heldout_f1", ">="),
    "false_merge_rate": ("maximum_heldout_false_merge_rate", "<="),
    "candidate_recall": ("minimum_heldout_candidate_recall", ">="),
    "p95_inference_latency_ms": (
        "maximum_heldout_p95_inference_latency_ms",
        "<=",
    ),
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class D5G1ExternalAuditError(ValueError):
    """Stable error for an invalid audit request or output destination."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D5G1ExternalAuditArtifact:
    """One caller-frozen artifact path and file digest."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise D5G1ExternalAuditError(
                "input_artifact_path_invalid",
                repr(self.path),
            )
        path = Path(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise D5G1ExternalAuditError(
                "input_artifact_path_invalid",
                self.path,
            )
        if not isinstance(self.sha256, str) or not _SHA256_RE.fullmatch(
            self.sha256
        ):
            raise D5G1ExternalAuditError(
                "input_artifact_sha256_invalid",
                self.path,
            )


@dataclass(frozen=True, slots=True)
class D5G1ExternalAuditThresholds:
    """Frozen thresholds used by the v1 pre-admission audit."""

    minimum_unseen_seed_count: int
    minimum_heldout_episode_count: int
    minimum_scenario_scale_cell_count: int
    minimum_heldout_f1: float
    maximum_heldout_false_merge_rate: float
    minimum_heldout_candidate_recall: float
    maximum_heldout_p95_inference_latency_ms: float
    maximum_single_feature_auc: float
    minimum_robustness_profile_count: int
    minimum_robustness_edge_f1: float
    minimum_robustness_cluster_f1: float

    def __post_init__(self) -> None:
        for name in (
            "minimum_unseen_seed_count",
            "minimum_heldout_episode_count",
            "minimum_scenario_scale_cell_count",
            "minimum_robustness_profile_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise D5G1ExternalAuditError(
                    "input_threshold_type_invalid",
                    name,
                )
        for name in (
            "minimum_heldout_f1",
            "maximum_heldout_false_merge_rate",
            "minimum_heldout_candidate_recall",
            "maximum_heldout_p95_inference_latency_ms",
            "maximum_single_feature_auc",
            "minimum_robustness_edge_f1",
            "minimum_robustness_cluster_f1",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise D5G1ExternalAuditError(
                    "input_threshold_type_invalid",
                    name,
                )

    def to_dict(self) -> dict[str, int | float]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class D5G1ExternalAuditInputs:
    """Explicit repository root, source location, and frozen artifact set."""

    repository_root: Path
    audit_id: str
    evaluated_at_utc: str
    formal_profile_version: str
    d5_source_dir: str
    expected_current_implementation_sha256: str
    thresholds: D5G1ExternalAuditThresholds
    artifacts: Mapping[str, D5G1ExternalAuditArtifact]
    schema_version: str = D5_G1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        root = Path(self.repository_root).expanduser().resolve()
        if not root.is_dir():
            raise D5G1ExternalAuditError(
                "input_repository_root_invalid",
                str(root),
            )
        object.__setattr__(self, "repository_root", root)
        if self.schema_version != D5_G1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION:
            raise D5G1ExternalAuditError(
                "input_schema_mismatch",
                self.schema_version,
            )
        for name in ("audit_id", "evaluated_at_utc"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise D5G1ExternalAuditError(
                    "input_string_invalid",
                    name,
                )
        if (
            self.formal_profile_version
            != D5_G1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION
        ):
            raise D5G1ExternalAuditError(
                "input_formal_profile_mismatch",
                self.formal_profile_version,
            )
        if (
            not isinstance(self.d5_source_dir, str)
            or not self.d5_source_dir
        ):
            raise D5G1ExternalAuditError(
                "input_d5_source_dir_invalid",
                repr(self.d5_source_dir),
            )
        source = Path(self.d5_source_dir)
        if source.is_absolute() or ".." in source.parts:
            raise D5G1ExternalAuditError(
                "input_d5_source_dir_invalid",
                repr(self.d5_source_dir),
            )
        if (
            not isinstance(
                self.expected_current_implementation_sha256,
                str,
            )
            or not _SHA256_RE.fullmatch(
                self.expected_current_implementation_sha256
            )
        ):
            raise D5G1ExternalAuditError(
                "input_current_implementation_sha256_invalid",
                self.expected_current_implementation_sha256,
            )
        artifacts = dict(self.artifacts)
        if set(artifacts) != set(_REQUIRED_ARTIFACT_NAMES):
            raise D5G1ExternalAuditError(
                "input_artifact_set_mismatch",
                ",".join(sorted(set(artifacts) ^ set(_REQUIRED_ARTIFACT_NAMES))),
            )
        if any(
            not isinstance(value, D5G1ExternalAuditArtifact)
            for value in artifacts.values()
        ):
            raise D5G1ExternalAuditError(
                "input_artifact_type_invalid",
                "all artifacts must be D5G1ExternalAuditArtifact",
            )
        object.__setattr__(self, "artifacts", artifacts)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        repository_root: str | Path,
    ) -> "D5G1ExternalAuditInputs":
        expected_fields = {
            "schema_version",
            "audit_id",
            "evaluated_at_utc",
            "formal_profile_version",
            "d5_source_dir",
            "expected_current_implementation_sha256",
            "thresholds",
            "artifacts",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected_fields:
            raise D5G1ExternalAuditError(
                "input_fields_mismatch",
                "top-level input fields differ from v1 schema",
            )
        raw_thresholds = payload.get("thresholds")
        threshold_fields = set(D5G1ExternalAuditThresholds.__dataclass_fields__)
        if (
            not isinstance(raw_thresholds, Mapping)
            or set(raw_thresholds) != threshold_fields
        ):
            raise D5G1ExternalAuditError(
                "input_threshold_fields_mismatch",
                "threshold fields differ from v1 schema",
            )
        raw_artifacts = payload.get("artifacts")
        if not isinstance(raw_artifacts, Mapping):
            raise D5G1ExternalAuditError(
                "input_artifact_type_invalid",
                "artifacts must be an object",
            )
        artifacts: dict[str, D5G1ExternalAuditArtifact] = {}
        for name, raw in raw_artifacts.items():
            if (
                not isinstance(raw, Mapping)
                or set(raw) != {"path", "sha256"}
            ):
                raise D5G1ExternalAuditError(
                    "input_artifact_fields_mismatch",
                    str(name),
                )
            artifacts[str(name)] = D5G1ExternalAuditArtifact(
                path=raw["path"],
                sha256=raw["sha256"],
            )
        return cls(
            repository_root=Path(repository_root),
            audit_id=payload["audit_id"],
            evaluated_at_utc=payload["evaluated_at_utc"],
            formal_profile_version=payload["formal_profile_version"],
            d5_source_dir=payload["d5_source_dir"],
            expected_current_implementation_sha256=payload[
                "expected_current_implementation_sha256"
            ],
            thresholds=D5G1ExternalAuditThresholds(**dict(raw_thresholds)),
            artifacts=artifacts,
            schema_version=payload["schema_version"],
        )

    def resolve_artifact(self, name: str) -> Path:
        artifact = self.artifacts[name]
        return _safe_child(self.repository_root, artifact.path)

    @property
    def source_root(self) -> Path:
        return _safe_child(self.repository_root, self.d5_source_dir)


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


def load_d5_g1_external_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> D5G1ExternalAuditInputs:
    """Load one strict v1 audit request without discovering adjacent files."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D5G1ExternalAuditError(
            "input_json_invalid",
            str(source),
        ) from exc
    if not isinstance(payload, dict):
        raise D5G1ExternalAuditError(
            "input_json_object_required",
            str(source),
        )
    return D5G1ExternalAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
    )


def audit_d5_g1_external_evidence(
    inputs: D5G1ExternalAuditInputs,
) -> dict[str, Any]:
    """Audit one frozen D5 G1 candidate and return a fail-closed result."""

    context = _AuditContext()
    artifact_rows, payloads = _audit_artifacts(inputs, context)
    registry = _audit_registry(inputs, payloads, context)
    bundle = _audit_bundle(inputs, payloads, context)
    heldout = _audit_heldout(inputs, payloads, context)
    paired = _audit_paired_shadow(inputs, payloads, context)
    lineage = _audit_lineage(inputs, artifact_rows, paired, context)
    implementation = _audit_implementation(
        inputs,
        bundle=bundle,
        heldout=heldout,
        paired=paired,
        context=context,
    )
    _audit_cross_bindings(
        inputs,
        registry=registry,
        bundle=bundle,
        heldout=heldout,
        paired=paired,
        lineage=lineage,
        context=context,
    )

    fields = _assemble_consumer_fields(
        inputs,
        bundle=bundle,
        heldout=heldout,
        paired=paired,
        implementation=implementation,
        context=context,
    )
    limitations = _audit_limitations(inputs, paired, context)
    blockers = context.blockers
    passed = not blockers
    fields["d6_external_audit_passed"] = passed
    fields["failure_reasons"] = blockers

    result: dict[str, Any] = {
        "schema_version": D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "formal_profile_version": inputs.formal_profile_version,
        "status": "pass" if passed else "fail_closed",
        "audit_passed": passed,
        "fail_closed": not passed,
        "evidence_audit_only": True,
        "input_contract": {
            "schema_version": inputs.schema_version,
            "expected_current_implementation_sha256": (
                inputs.expected_current_implementation_sha256
            ),
            "thresholds": inputs.thresholds.to_dict(),
        },
        "artifact_evidence": artifact_rows,
        "candidate": {
            "model": bundle,
            "registry": registry,
            "heldout": heldout,
            "paired_shadow": paired,
            "paired_lineage": lineage,
            "implementation": implementation,
        },
        "limitations": limitations,
        "d5_consumer_contract": {
            "schema_version": D5_G1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION,
            **fields,
        },
        "blocker_codes": blockers,
        "blocker_details": context.blocker_details(),
        "authority": {
            "model_promotion_granted": False,
            "g1_assist_granted": False,
            "control_authority_granted": False,
            "default_path_change_granted": False,
            "reason": (
                "D6 only issues an evidence audit pass/fail; promotion and "
                "runtime authority remain outside D6"
            ),
        },
        "availability_policy": {
            "missing_evidence": "unavailable_and_fail_closed",
            "type_error": "unavailable_and_fail_closed",
            "sha256_mismatch": "fail_closed",
            "lineage_mismatch": "fail_closed",
            "zero_fill_allowed": False,
            "unavailable_metric_is_zero": False,
        },
    }
    return _with_content_sha256(result)


def write_d5_g1_external_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Write deterministic JSON, evidence CSV, Chinese Markdown, and hashes."""

    output = Path(output_dir)
    if output.exists() and (
        not output.is_dir() or any(output.iterdir())
    ):
        raise D5G1ExternalAuditError(
            "output_directory_not_empty",
            str(output),
        )
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "d5_g1_external_audit.json"
    csv_path = output / "d5_g1_external_audit_evidence.csv"
    markdown_path = output / "D5_G1_EXTERNAL_AUDIT_CN.md"
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
        render_d5_g1_external_audit_markdown(result),
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


def render_d5_g1_external_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render the audit result in Chinese without implying model authority."""

    contract = result.get("d5_consumer_contract", {})
    implementation = result.get("candidate", {}).get("implementation", {})
    shortcut = result.get("limitations", {}).get(
        "synthetic_single_feature_shortcut",
        {},
    )
    robustness = result.get("limitations", {}).get(
        "robustness_generalization",
        {},
    )
    lines = [
        "# D5 G1 预准入外部审计",
        "",
        f"审计时间：`{result.get('evaluated_at_utc')}`",
        "",
        "## 结论",
        "",
        f"证据审计结果为 **{result.get('status')}**。",
        (
            "D6 只确认证据链是否通过，不授予模型晋级、G1 辅助权限、"
            "控制权或默认路径变更。"
        ),
        "",
        "## 候选绑定",
        "",
        f"- 模型指纹：`{contract.get('model_fingerprint')}`。",
        f"- manifest SHA-256：`{contract.get('bundle_manifest_sha256')}`。",
        f"- weights SHA-256：`{contract.get('bundle_weights_sha256')}`。",
        (
            "- 当前实现摘要："
            f"`{implementation.get('current_implementation_sha256')}`；"
            "证据实现摘要："
            f"`{implementation.get('evidence_implementation_sha256')}`。"
        ),
        f"- 未见 seed：`{contract.get('unseen_seed_count')}`。",
        f"- held-out episode：`{contract.get('heldout_episode_count')}`。",
        (
            "- 场景规模单元："
            f"`{contract.get('scenario_scale_cell_count')}`。"
        ),
        "",
        "## 安全计数",
        "",
        (
            "- 在线真值字段："
            f"`{contract.get('online_truth_feature_count')}`。"
        ),
        (
            "- global_track_id 改写："
            f"`{contract.get('global_track_id_rewrite_count')}`。"
        ),
        (
            "- 同相机互斥违规："
            f"`{contract.get('same_camera_mutual_exclusion_violation_count')}`。"
        ),
        "",
        "## 泛化限制",
        "",
        (
            "- 单特征最高 AUC："
            f"`{shortcut.get('observed_best_direction_auc')}`，特征为 "
            f"`{shortcut.get('feature')}`，门限为 "
            f"`{shortcut.get('maximum_allowed_auc')}`。"
        ),
        (
            "- 扰动最低边/簇 F1："
            f"`{robustness.get('minimum_observed_edge_f1')}` / "
            f"`{robustness.get('minimum_observed_cluster_f1')}`。"
        ),
        (
            "- 扰动过程重新构建候选图："
            f"`{robustness.get('all_profiles_rebuilt_candidate_graph')}`。"
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
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            (
                "D5 后续证据装配器只能消费本 JSON 及其文件 SHA-256、"
                "内容 SHA-256。任何字段缺失、类型变化、哈希不一致或 "
                "`audit_passed=false` 都必须继续失败关闭。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _audit_artifacts(
    inputs: D5G1ExternalAuditInputs,
    context: _AuditContext,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for name in _REQUIRED_ARTIFACT_NAMES:
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
            by_name[name] = row
            continue
        actual = _sha256_file(path)
        row["availability"] = "available"
        row["actual_sha256"] = actual
        row["sha256_match"] = actual == binding.sha256
        if actual != binding.sha256:
            code = f"artifact_sha256_mismatch.{name}"
            context.block(code, binding.path)
            row["blocker_codes"].append(code)
        rows.append(row)
        by_name[name] = row

    for name in _JSON_ARTIFACT_NAMES:
        row = by_name[name]
        if row["availability"] != "available":
            continue
        path = inputs.resolve_artifact(name)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            code = f"artifact_json_invalid.{name}"
            context.block(code, str(exc))
            row["blocker_codes"].append(code)
            continue
        if not isinstance(payload, dict):
            code = f"artifact_json_invalid.{name}"
            context.block(code, "JSON root must be an object")
            row["blocker_codes"].append(code)
            continue
        payloads[name] = payload
        if name in _CONTENT_HASHED_ARTIFACT_NAMES:
            claimed = payload.get("content_sha256")
            row["content_sha256"] = claimed if isinstance(claimed, str) else None
            if not isinstance(claimed, str) or not _SHA256_RE.fullmatch(claimed):
                code = f"artifact_content_sha256_invalid.{name}"
                context.block(code, "content_sha256 is missing or invalid")
                row["blocker_codes"].append(code)
                row["content_sha256_verified"] = False
            else:
                actual_content = _sha256_json_without_content(payload)
                matched = actual_content == claimed
                row["content_sha256_verified"] = matched
                if not matched:
                    code = f"artifact_content_sha256_mismatch.{name}"
                    context.block(code, f"{claimed}!={actual_content}")
                    row["blocker_codes"].append(code)
    return rows, payloads


def _audit_registry(
    inputs: D5G1ExternalAuditInputs,
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    reference = payloads.get("registry_reference")
    evidence = payloads.get("registry_audit_evidence")
    result: dict[str, Any] = {
        "available": reference is not None and evidence is not None,
        "reference_sha256": _artifact_actual_sha(inputs, "registry_reference"),
        "audit_evidence_sha256": _artifact_actual_sha(
            inputs,
            "registry_audit_evidence",
        ),
        "checksums_sha256": _artifact_actual_sha(inputs, "registry_checksums"),
        "status": None,
        "limitations": None,
    }
    if reference is None or evidence is None:
        context.block(
            "registry_evidence_unavailable",
            "frozen reference or audit evidence is unavailable",
        )
        return result
    if reference.get("schema_version") != _D5_FROZEN_REFERENCE_SCHEMA:
        context.block("registry_contract_invalid", "reference schema")
    if evidence.get("schema_version") != _D5_FROZEN_EVIDENCE_SCHEMA:
        context.block("registry_contract_invalid", "audit evidence schema")

    expected_hashes = _strict_mapping(
        reference.get("expected_hashes"),
        context,
        "registry_type_invalid",
        "reference.expected_hashes",
    )
    frozen_model = _strict_mapping(
        evidence.get("frozen_model"),
        context,
        "registry_type_invalid",
        "evidence.frozen_model",
    )
    output_hashes = _strict_mapping(
        evidence.get("output_hashes"),
        context,
        "registry_type_invalid",
        "evidence.output_hashes",
    )
    catalog = _strict_mapping(
        evidence.get("catalog"),
        context,
        "registry_type_invalid",
        "evidence.catalog",
    )
    for key in ("manifest_sha256", "weights_sha256", "checksums_sha256"):
        _strict_sha(
            expected_hashes.get(key),
            context,
            "registry_type_invalid",
            f"reference.expected_hashes.{key}",
        )
    for key in ("manifest_sha256", "weights_sha256"):
        _strict_sha(
            frozen_model.get(key),
            context,
            "registry_type_invalid",
            f"evidence.frozen_model.{key}",
        )
    for key in (
        "heldout_evaluation_file_sha256",
        "heldout_evaluation_content_sha256",
        "paired_report_file_sha256",
        "paired_report_content_sha256",
        "paired_lineage_sha256",
    ):
        _strict_sha(
            output_hashes.get(key),
            context,
            "registry_type_invalid",
            f"evidence.output_hashes.{key}",
        )
    for key in (
        "seed_count",
        "episode_count",
        "scenario_scale_cell_count",
    ):
        _strict_int(
            catalog.get(key),
            context,
            "registry_type_invalid",
            f"evidence.catalog.{key}",
        )
    authority = _strict_mapping(
        evidence.get("authority"),
        context,
        "registry_type_invalid",
        "evidence.authority",
    )
    for key in ("g1", "assist", "authority", "default_model_changed"):
        value = _strict_bool(
            authority.get(key),
            context,
            "registry_type_invalid",
            f"evidence.authority.{key}",
        )
        if value is not None and value is not False:
            context.block("registry_authority_not_closed", key)

    limitations = evidence.get("limitations")
    if (
        not isinstance(limitations, list)
        or any(not isinstance(item, str) or not item for item in limitations)
    ):
        context.block("registry_type_invalid", "evidence.limitations")
        limitations = None
    result["status"] = evidence.get("status")
    result["limitations"] = limitations

    _audit_checksum_file(
        inputs.resolve_artifact("registry_checksums"),
        {
            Path(inputs.artifacts["registry_reference"].path).name: inputs.artifacts[
                "registry_reference"
            ].sha256,
            Path(inputs.artifacts["registry_audit_evidence"].path).name: inputs.artifacts[
                "registry_audit_evidence"
            ].sha256,
        },
        context,
        "registry_checksums_invalid",
    )
    return result


def _audit_bundle(
    inputs: D5G1ExternalAuditInputs,
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    manifest = payloads.get("bundle_manifest")
    result: dict[str, Any] = {
        "available": manifest is not None,
        "model_fingerprint": None,
        "manifest_sha256": _artifact_actual_sha(inputs, "bundle_manifest"),
        "weights_sha256": _artifact_actual_sha(inputs, "bundle_weights"),
        "checksums_sha256": _artifact_actual_sha(inputs, "bundle_checksums"),
        "dataset_manifest_sha256": None,
        "split_sha256": None,
        "training_set_sha256": None,
        "manifest_implementation_sha256": None,
        "manifest_source_files": None,
    }
    if manifest is None:
        context.block("bundle_evidence_unavailable", "bundle manifest")
        return result
    if manifest.get("schema_version") != _D5_MODEL_BUNDLE_SCHEMA:
        context.block("bundle_contract_invalid", "manifest schema")

    weights = _strict_mapping(
        manifest.get("weights"),
        context,
        "bundle_type_invalid",
        "weights",
    )
    manifest_weights_sha = _strict_sha(
        weights.get("sha256"),
        context,
        "bundle_type_invalid",
        "weights.sha256",
    )
    actual_weights_sha = result["weights_sha256"]
    if (
        manifest_weights_sha is not None
        and actual_weights_sha is not None
        and manifest_weights_sha != actual_weights_sha
    ):
        context.block("model_lineage_mismatch", "manifest weights SHA")
    if actual_weights_sha is not None:
        result["model_fingerprint"] = f"sha256:{actual_weights_sha}"

    training = _strict_mapping(
        manifest.get("training_dataset"),
        context,
        "bundle_type_invalid",
        "training_dataset",
    )
    for field in (
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
    ):
        result[field] = _strict_sha(
            training.get(field),
            context,
            "bundle_type_invalid",
            f"training_dataset.{field}",
        )
    provenance = _strict_mapping(
        manifest.get("code_provenance"),
        context,
        "bundle_type_invalid",
        "code_provenance",
    )
    source_files = _strict_sha_mapping(
        provenance.get("source_files"),
        context,
        "bundle_type_invalid",
        "code_provenance.source_files",
    )
    manifest_implementation = _strict_sha(
        provenance.get("implementation_sha256"),
        context,
        "bundle_type_invalid",
        "code_provenance.implementation_sha256",
    )
    if source_files is not None:
        if set(source_files) != set(_MODEL_IMPLEMENTATION_FILES):
            context.block(
                "bundle_contract_invalid",
                "model implementation source file set",
            )
        calculated = _sha256_json(dict(sorted(source_files.items())))
        if (
            manifest_implementation is not None
            and calculated != manifest_implementation
        ):
            context.block(
                "bundle_contract_invalid",
                "manifest implementation digest",
            )
    result["manifest_implementation_sha256"] = manifest_implementation
    result["manifest_source_files"] = source_files

    admission = _strict_mapping(
        manifest.get("admission"),
        context,
        "bundle_type_invalid",
        "admission",
    )
    for field in ("default_model", "g1_assist_eligible"):
        value = _strict_bool(
            admission.get(field),
            context,
            "bundle_type_invalid",
            f"admission.{field}",
        )
        if value is not None and value is not False:
            context.block("bundle_authority_not_closed", field)

    _audit_checksum_file(
        inputs.resolve_artifact("bundle_checksums"),
        {
            Path(inputs.artifacts["bundle_manifest"].path).name: inputs.artifacts[
                "bundle_manifest"
            ].sha256,
            Path(inputs.artifacts["bundle_weights"].path).name: inputs.artifacts[
                "bundle_weights"
            ].sha256,
        },
        context,
        "bundle_checksums_invalid",
    )
    return result


def _audit_heldout(
    inputs: D5G1ExternalAuditInputs,
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    report = payloads.get("heldout_report")
    result: dict[str, Any] = {
        "available": report is not None,
        "report_sha256": _artifact_actual_sha(inputs, "heldout_report"),
        "report_content_sha256": None,
        "passed": None,
        "seed_values": None,
        "unseen_seed_count": None,
        "episode_count": None,
        "scenario_scale_cell_count": None,
        "bundle_manifest_sha256": None,
        "bundle_weights_sha256": None,
        "training_dataset": None,
        "implementation_source_files": None,
        "formal_inputs": None,
        "online_truth_feature_count": None,
    }
    if report is None:
        context.block("heldout_evidence_unavailable", "heldout report")
        return result
    if report.get("schema_version") != _D5_HELDOUT_SCHEMA:
        context.block("heldout_contract_invalid", "report schema")
    result["report_content_sha256"] = _strict_sha(
        report.get("content_sha256"),
        context,
        "heldout_type_invalid",
        "content_sha256",
    )
    if report.get("evaluation_role") != "held_out_evaluation":
        context.block("heldout_contract_invalid", "evaluation role")

    development_model = _strict_mapping(
        report.get("development_model"),
        context,
        "heldout_type_invalid",
        "development_model",
    )
    result["bundle_manifest_sha256"] = _strict_sha(
        development_model.get("bundle_manifest_sha256"),
        context,
        "heldout_type_invalid",
        "development_model.bundle_manifest_sha256",
    )
    result["bundle_weights_sha256"] = _strict_sha(
        development_model.get("weights_sha256"),
        context,
        "heldout_type_invalid",
        "development_model.weights_sha256",
    )
    training = _strict_mapping(
        development_model.get("training_dataset"),
        context,
        "heldout_type_invalid",
        "development_model.training_dataset",
    )
    training_values: dict[str, str | None] = {}
    for field in (
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
    ):
        training_values[field] = _strict_sha(
            training.get(field),
            context,
            "heldout_type_invalid",
            f"development_model.training_dataset.{field}",
        )
    result["training_dataset"] = training_values

    corpus = _strict_mapping(
        report.get("heldout_corpus"),
        context,
        "heldout_type_invalid",
        "heldout_corpus",
    )
    seed_values = _strict_int_sequence(
        corpus.get("seed_values"),
        context,
        "heldout_type_invalid",
        "heldout_corpus.seed_values",
    )
    episode_count = _strict_int(
        corpus.get("episode_count"),
        context,
        "heldout_type_invalid",
        "heldout_corpus.episode_count",
    )
    cell_count = _strict_int(
        corpus.get("scenario_scale_cell_count"),
        context,
        "heldout_type_invalid",
        "heldout_corpus.scenario_scale_cell_count",
    )
    if seed_values is not None and len(set(seed_values)) != len(seed_values):
        context.block("heldout_contract_invalid", "duplicate held-out seed")
    result["seed_values"] = seed_values
    result["unseen_seed_count"] = (
        None if seed_values is None else len(seed_values)
    )
    result["episode_count"] = episode_count
    result["scenario_scale_cell_count"] = cell_count

    implementation = _strict_sha_mapping(
        report.get("implementation_sha256"),
        context,
        "heldout_type_invalid",
        "implementation_sha256",
    )
    result["implementation_source_files"] = implementation

    assessment = _strict_mapping(
        report.get("heldout_assessment"),
        context,
        "heldout_type_invalid",
        "heldout_assessment",
    )
    result["passed"] = _strict_bool(
        assessment.get("passed"),
        context,
        "heldout_type_invalid",
        "heldout_assessment.passed",
    )
    if assessment.get("status") != "pass":
        context.block("heldout_not_passed", "assessment status")
    if result["passed"] is False:
        context.block("heldout_not_passed", "assessment passed=false")

    overall = _strict_mapping(
        report.get("overall"),
        context,
        "heldout_type_invalid",
        "overall",
    )
    overall_episode_count = _strict_int(
        overall.get("episode_count"),
        context,
        "heldout_type_invalid",
        "overall.episode_count",
    )
    complete_truth = _strict_bool(
        overall.get("complete_truth"),
        context,
        "heldout_type_invalid",
        "overall.complete_truth",
    )
    if (
        episode_count is not None
        and overall_episode_count is not None
        and episode_count != overall_episode_count
    ):
        context.block("heldout_contract_invalid", "episode count mismatch")
    metrics = _strict_mapping(
        overall.get("metrics"),
        context,
        "heldout_type_invalid",
        "overall.metrics",
    )
    metric_values: dict[str, float | None] = {}
    for metric_name, (threshold_name, operator) in _HELDOUT_METRIC_THRESHOLDS.items():
        metric = _strict_mapping(
            metrics.get(metric_name),
            context,
            "heldout_type_invalid",
            f"overall.metrics.{metric_name}",
        )
        available = _strict_bool(
            metric.get("available"),
            context,
            "heldout_type_invalid",
            f"overall.metrics.{metric_name}.available",
        )
        if available is not True:
            context.block("heldout_metric_unavailable", metric_name)
            metric_values[metric_name] = None
            continue
        value = _strict_number(
            metric.get("value"),
            context,
            "heldout_type_invalid",
            f"overall.metrics.{metric_name}.value",
        )
        metric_values[metric_name] = value
        threshold = float(getattr(inputs.thresholds, threshold_name))
        if value is not None and not _comparison_passed(value, threshold, operator):
            context.block(
                f"heldout_threshold_not_met.{metric_name}",
                f"{value}{operator}{threshold}",
            )

    safety = _strict_mapping(
        report.get("identity_and_truth_safety"),
        context,
        "heldout_type_invalid",
        "identity_and_truth_safety",
    )
    online_truth = _strict_int(
        safety.get("online_truth_feature_count"),
        context,
        "heldout_type_invalid",
        "identity_and_truth_safety.online_truth_feature_count",
    )
    rebound = _strict_bool(
        safety.get("global_track_id_created_or_rebound"),
        context,
        "heldout_type_invalid",
        "identity_and_truth_safety.global_track_id_created_or_rebound",
    )
    if online_truth is not None and online_truth != 0:
        context.block("online_truth_feature_use", f"heldout:{online_truth}")
    if rebound is True:
        context.block("global_track_id_rewrite", "heldout rebound=true")
    result["online_truth_feature_count"] = online_truth
    result["metrics"] = metric_values
    result["formal_inputs"] = {
        "evaluation_role": report.get("evaluation_role"),
        "complete_truth": complete_truth,
        "exact_seed_catalog": (
            seed_values == list(range(1000, 1020))
            if seed_values is not None
            else None
        ),
    }
    return result


def _audit_paired_shadow(
    inputs: D5G1ExternalAuditInputs,
    payloads: Mapping[str, Mapping[str, Any]],
    context: _AuditContext,
) -> dict[str, Any]:
    report = payloads.get("paired_shadow_report")
    result: dict[str, Any] = {
        "available": report is not None,
        "report_sha256": _artifact_actual_sha(inputs, "paired_shadow_report"),
        "report_content_sha256": None,
        "passed": None,
        "seed_count": None,
        "episode_count": None,
        "scenario_scale_cell_count": None,
        "bundle_manifest_sha256": None,
        "bundle_weights_sha256": None,
        "heldout_report_sha256": None,
        "heldout_report_content_sha256": None,
        "implementation_source_files": None,
        "formal_inputs": None,
        "online_truth_feature_count": None,
        "global_track_id_rewrite_count": None,
        "same_camera_mutual_exclusion_violation_count": None,
        "maximum_single_feature_auc": None,
        "robustness_profiles": None,
    }
    if report is None:
        context.block("paired_shadow_evidence_unavailable", "paired report")
        return result
    if report.get("schema_version") != _D5_PAIRED_SCHEMA:
        context.block("paired_shadow_contract_invalid", "report schema")
    result["report_content_sha256"] = _strict_sha(
        report.get("content_sha256"),
        context,
        "paired_shadow_type_invalid",
        "content_sha256",
    )
    execution_completed = _strict_bool(
        report.get("execution_completed"),
        context,
        "paired_shadow_type_invalid",
        "execution_completed",
    )
    if execution_completed is False:
        context.block("paired_shadow_not_passed", "execution incomplete")
    if report.get("evaluation_role") != "evaluator_only_paired_shadow":
        context.block("paired_shadow_contract_invalid", "evaluation role")
    if report.get("status") != "pass":
        context.block("paired_shadow_not_passed", "report status")

    spec = _strict_mapping(
        report.get("input_spec"),
        context,
        "paired_shadow_type_invalid",
        "input_spec",
    )
    if spec.get("schema_version") != _D5_PAIRED_INPUT_SCHEMA:
        context.block("paired_shadow_contract_invalid", "input spec schema")
    require_full_profile = _strict_bool(
        spec.get("require_full_profile"),
        context,
        "paired_shadow_type_invalid",
        "input_spec.require_full_profile",
    )
    input_spec_sha = _strict_sha(
        report.get("input_spec_sha256"),
        context,
        "paired_shadow_type_invalid",
        "input_spec_sha256",
    )
    if input_spec_sha is not None and input_spec_sha != _sha256_json(spec):
        context.block("paired_shadow_contract_invalid", "input spec SHA")
    expected_hashes = _strict_mapping(
        spec.get("expected_hashes"),
        context,
        "paired_shadow_type_invalid",
        "input_spec.expected_hashes",
    )
    for output_name, source_name in (
        ("bundle_manifest_sha256", "bundle_manifest_sha256"),
        ("bundle_weights_sha256", "bundle_weights_sha256"),
        ("heldout_report_sha256", "heldout_report_sha256"),
        ("heldout_report_content_sha256", "heldout_report_content_sha256"),
    ):
        result[output_name] = _strict_sha(
            expected_hashes.get(source_name),
            context,
            "paired_shadow_type_invalid",
            f"input_spec.expected_hashes.{source_name}",
        )

    before = _strict_mapping(
        report.get("input_hashes_before"),
        context,
        "paired_shadow_type_invalid",
        "input_hashes_before",
    )
    after = _strict_mapping(
        report.get("input_hashes_after"),
        context,
        "paired_shadow_type_invalid",
        "input_hashes_after",
    )
    if before != after or before != expected_hashes:
        context.block("paired_shadow_input_mutation", "before/after/spec mismatch")
    immutable = _strict_bool(
        report.get("input_artifacts_unchanged"),
        context,
        "paired_shadow_type_invalid",
        "input_artifacts_unchanged",
    )
    if immutable is False:
        context.block("paired_shadow_input_mutation", "unchanged=false")
    evidence_status = _strict_mapping(
        report.get("evidence_status"),
        context,
        "paired_shadow_type_invalid",
        "evidence_status",
    )
    if evidence_status.get("status") != "authoritative":
        context.block("paired_shadow_contract_invalid", "evidence status")

    totals = _strict_mapping(
        report.get("totals"),
        context,
        "paired_shadow_type_invalid",
        "totals",
    )
    for field in ("seed_count", "episode_count", "scenario_scale_cell_count"):
        result[field] = _strict_int(
            totals.get(field),
            context,
            "paired_shadow_type_invalid",
            f"totals.{field}",
        )
    catalog = _strict_mapping(
        report.get("catalog_integrity"),
        context,
        "paired_shadow_type_invalid",
        "catalog_integrity",
    )
    catalog_complete = _strict_bool(
        catalog.get("complete"),
        context,
        "paired_shadow_type_invalid",
        "catalog_integrity.complete",
    )
    if catalog_complete is False:
        context.block("paired_shadow_catalog_incomplete", "complete=false")

    assessment = _strict_mapping(
        report.get("paired_shadow_assessment"),
        context,
        "paired_shadow_type_invalid",
        "paired_shadow_assessment",
    )
    result["passed"] = _strict_bool(
        assessment.get("passed"),
        context,
        "paired_shadow_type_invalid",
        "paired_shadow_assessment.passed",
    )
    if assessment.get("status") != "pass" or result["passed"] is False:
        context.block("paired_shadow_not_passed", "assessment")
    gates = assessment.get("gates")
    if not isinstance(gates, list) or not gates:
        context.block("paired_metric_unavailable", "assessment gates")
    else:
        for index, raw_gate in enumerate(gates):
            gate = _strict_mapping(
                raw_gate,
                context,
                "paired_shadow_type_invalid",
                f"paired_shadow_assessment.gates[{index}]",
            )
            name = gate.get("name")
            if not isinstance(name, str) or not name:
                context.block(
                    "paired_shadow_type_invalid",
                    f"gate[{index}].name",
                )
                name = f"gate_{index}"
            available = _strict_bool(
                gate.get("available"),
                context,
                "paired_shadow_type_invalid",
                f"gate[{index}].available",
            )
            passed = _strict_bool(
                gate.get("passed"),
                context,
                "paired_shadow_type_invalid",
                f"gate[{index}].passed",
            )
            if available is not True:
                context.block("paired_metric_unavailable", name)
            elif passed is not True:
                context.block(f"paired_threshold_not_met.{name}", name)

    safety = _strict_mapping(
        report.get("identity_and_truth_safety"),
        context,
        "paired_shadow_type_invalid",
        "identity_and_truth_safety",
    )
    for field, blocker in (
        ("online_truth_feature_count", "online_truth_feature_use"),
        ("global_track_id_rewrite_count", "global_track_id_rewrite"),
        (
            "same_camera_mutual_exclusion_violation_count",
            "same_camera_mutual_exclusion_violation",
        ),
    ):
        value = _strict_int(
            safety.get(field),
            context,
            "paired_shadow_type_invalid",
            f"identity_and_truth_safety.{field}",
        )
        result[field] = value
        if value is not None and value != 0:
            context.block(blocker, f"paired:{value}")

    implementation = _strict_sha_mapping(
        report.get("implementation_sha256"),
        context,
        "paired_shadow_type_invalid",
        "implementation_sha256",
    )
    result["implementation_source_files"] = implementation
    diagnostics = _strict_mapping(
        report.get("feature_label_diagnostics"),
        context,
        "paired_shadow_type_invalid",
        "feature_label_diagnostics",
    )
    maximum_auc = _strict_mapping(
        diagnostics.get("maximum_single_feature_auc"),
        context,
        "paired_shadow_type_invalid",
        "feature_label_diagnostics.maximum_single_feature_auc",
    )
    auc_available = _strict_bool(
        maximum_auc.get("available"),
        context,
        "paired_shadow_type_invalid",
        "maximum_single_feature_auc.available",
    )
    auc_value = (
        _strict_number(
            maximum_auc.get("best_direction_auc"),
            context,
            "paired_shadow_type_invalid",
            "maximum_single_feature_auc.best_direction_auc",
        )
        if auc_available is True
        else None
    )
    if auc_available is not True:
        context.block("synthetic_single_feature_metric_unavailable", "AUC")
    result["maximum_single_feature_auc"] = {
        "available": auc_available,
        "best_direction_auc": auc_value,
        "feature": (
            maximum_auc.get("feature")
            if isinstance(maximum_auc.get("feature"), str)
            else None
        ),
    }

    profiles = report.get("robustness_profiles")
    parsed_profiles: list[dict[str, Any]] | None = []
    if not isinstance(profiles, list):
        context.block("robustness_evidence_unavailable", "profiles")
        parsed_profiles = None
    else:
        for index, raw in enumerate(profiles):
            profile = _strict_mapping(
                raw,
                context,
                "paired_shadow_type_invalid",
                f"robustness_profiles[{index}]",
            )
            profile_meta = _strict_mapping(
                profile.get("profile"),
                context,
                "paired_shadow_type_invalid",
                f"robustness_profiles[{index}].profile",
            )
            model = _strict_mapping(
                profile.get("model"),
                context,
                "paired_shadow_type_invalid",
                f"robustness_profiles[{index}].model",
            )
            edge = _strict_mapping(
                model.get("edge"),
                context,
                "paired_shadow_type_invalid",
                f"robustness_profiles[{index}].model.edge",
            )
            cluster = _strict_mapping(
                model.get("cluster_pairwise"),
                context,
                "paired_shadow_type_invalid",
                f"robustness_profiles[{index}].model.cluster_pairwise",
            )
            parsed_profiles.append(
                {
                    "profile_id": (
                        profile_meta.get("profile_id")
                        if isinstance(profile_meta.get("profile_id"), str)
                        else None
                    ),
                    "truth_dependent": _strict_bool(
                        profile_meta.get("truth_dependent"),
                        context,
                        "paired_shadow_type_invalid",
                        f"robustness_profiles[{index}].truth_dependent",
                    ),
                    "candidate_graph_rebuilt": _strict_bool(
                        profile_meta.get("candidate_graph_rebuilt"),
                        context,
                        "paired_shadow_type_invalid",
                        f"robustness_profiles[{index}].candidate_graph_rebuilt",
                    ),
                    "edge_f1": _strict_number(
                        edge.get("f1"),
                        context,
                        "paired_shadow_type_invalid",
                        f"robustness_profiles[{index}].model.edge.f1",
                    ),
                    "cluster_f1": _strict_number(
                        cluster.get("f1"),
                        context,
                        "paired_shadow_type_invalid",
                        f"robustness_profiles[{index}].model.cluster_pairwise.f1",
                    ),
                }
            )
    result["robustness_profiles"] = parsed_profiles
    result["formal_inputs"] = {
        "execution_completed": execution_completed,
        "require_full_profile": require_full_profile,
        "input_artifacts_unchanged": immutable,
        "catalog_complete": catalog_complete,
        "evidence_status": evidence_status.get("status"),
    }
    return result


def _audit_lineage(
    inputs: D5G1ExternalAuditInputs,
    artifact_rows: Sequence[Mapping[str, Any]],
    paired: Mapping[str, Any],
    context: _AuditContext,
) -> dict[str, Any]:
    row = next(
        item
        for item in artifact_rows
        if item["artifact_id"] == "paired_shadow_lineage"
    )
    result = {
        "available": row["availability"] == "available",
        "sha256": row["actual_sha256"],
        "record_count": None,
        "unique_episode_uid_count": None,
    }
    if row["availability"] != "available":
        context.block("paired_lineage_unavailable", "lineage file")
        return result
    path = inputs.resolve_artifact("paired_shadow_lineage")
    episode_uids: set[str] = set()
    count = 0
    try:
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    raise ValueError(f"blank line {line_number}")
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"non-object line {line_number}")
                uid = value.get("episode_uid")
                if not isinstance(uid, str) or not uid:
                    raise ValueError(f"episode_uid line {line_number}")
                if uid in episode_uids:
                    raise ValueError(f"duplicate episode_uid {uid}")
                episode_uids.add(uid)
                count += 1
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        context.block("paired_lineage_invalid", str(exc))
        return result
    result["record_count"] = count
    result["unique_episode_uid_count"] = len(episode_uids)
    expected = paired.get("episode_count")
    if expected is None:
        context.block("paired_lineage_count_unavailable", "paired episode count")
    elif count != expected:
        context.block(
            "paired_lineage_count_mismatch",
            f"{count}!={expected}",
        )
    return result


def _audit_implementation(
    inputs: D5G1ExternalAuditInputs,
    *,
    bundle: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    context: _AuditContext,
) -> dict[str, Any]:
    current: dict[str, str] = {}
    for filename in _RUNTIME_IMPLEMENTATION_FILES:
        path = inputs.source_root / filename
        if not path.is_file():
            context.block("current_implementation_source_missing", filename)
            continue
        current[filename] = _sha256_file(path)
    current_digest = (
        _sha256_json(dict(sorted(current.items())))
        if len(current) == len(_RUNTIME_IMPLEMENTATION_FILES)
        else None
    )
    if (
        current_digest is not None
        and current_digest != inputs.expected_current_implementation_sha256
    ):
        context.block(
            "current_implementation_sha256_mismatch",
            (
                f"{current_digest}!="
                f"{inputs.expected_current_implementation_sha256}"
            ),
        )

    held_sources = heldout.get("implementation_source_files")
    paired_sources = paired.get("implementation_source_files")
    evidence: dict[str, str] = {}
    conflicts: dict[str, dict[str, str]] = {}
    for source in (held_sources, paired_sources):
        if not isinstance(source, Mapping):
            continue
        for name, digest in source.items():
            if name in evidence and evidence[name] != digest:
                conflicts[str(name)] = {
                    "first": evidence[name],
                    "second": str(digest),
                }
            else:
                evidence[str(name)] = str(digest)
    if conflicts:
        context.block(
            "implementation_evidence_conflict",
            ",".join(sorted(conflicts)),
        )
    missing = sorted(set(_RUNTIME_IMPLEMENTATION_FILES) - set(evidence))
    if missing:
        context.block(
            "implementation_evidence_unavailable",
            ",".join(missing),
        )
    evidence_runtime = {
        name: evidence[name]
        for name in _RUNTIME_IMPLEMENTATION_FILES
        if name in evidence
    }
    evidence_digest = (
        _sha256_json(dict(sorted(evidence_runtime.items())))
        if len(evidence_runtime) == len(_RUNTIME_IMPLEMENTATION_FILES)
        else None
    )
    mismatches = {
        name: {
            "evidence_sha256": evidence_runtime.get(name),
            "current_sha256": current.get(name),
        }
        for name in _RUNTIME_IMPLEMENTATION_FILES
        if evidence_runtime.get(name) != current.get(name)
    }
    manifest_sources = bundle.get("manifest_source_files")
    if isinstance(manifest_sources, Mapping):
        for name, digest in manifest_sources.items():
            if name in evidence and digest != evidence[name]:
                mismatches.setdefault(
                    str(name),
                    {
                        "evidence_sha256": evidence.get(str(name)),
                        "current_sha256": current.get(str(name)),
                    },
                )
    if mismatches or (
        evidence_digest is not None
        and current_digest is not None
        and evidence_digest != current_digest
    ):
        context.block(
            "implementation_lineage_mismatch",
            ",".join(sorted(mismatches)) or "aggregate digest mismatch",
        )
    return {
        "availability": (
            "available"
            if current_digest is not None and evidence_digest is not None
            else "unavailable"
        ),
        "current_implementation_sha256": current_digest,
        "expected_current_implementation_sha256": (
            inputs.expected_current_implementation_sha256
        ),
        "evidence_implementation_sha256": evidence_digest,
        "current_source_files": dict(sorted(current.items())),
        "evidence_source_files": dict(sorted(evidence_runtime.items())),
        "source_mismatches": mismatches,
        "equivalence_bridge": {
            "available": False,
            "verified": False,
            "reason": "v1 accepts no implementation equivalence bridge",
        },
    }


def _audit_cross_bindings(
    inputs: D5G1ExternalAuditInputs,
    *,
    registry: Mapping[str, Any],
    bundle: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    lineage: Mapping[str, Any],
    context: _AuditContext,
) -> None:
    manifest_values = {
        bundle.get("manifest_sha256"),
        heldout.get("bundle_manifest_sha256"),
        paired.get("bundle_manifest_sha256"),
    }
    weights_values = {
        bundle.get("weights_sha256"),
        heldout.get("bundle_weights_sha256"),
        paired.get("bundle_weights_sha256"),
    }
    if None in manifest_values or len(manifest_values) != 1:
        context.block("model_lineage_mismatch", "bundle manifest")
    if None in weights_values or len(weights_values) != 1:
        context.block("model_lineage_mismatch", "bundle weights")

    held_training = heldout.get("training_dataset")
    if not isinstance(held_training, Mapping):
        context.block("dataset_lineage_mismatch", "heldout training dataset")
    else:
        for field in (
            "dataset_manifest_sha256",
            "split_sha256",
            "training_set_sha256",
        ):
            if (
                bundle.get(field) is None
                or held_training.get(field) is None
                or bundle.get(field) != held_training.get(field)
            ):
                context.block("dataset_lineage_mismatch", field)

    if (
        paired.get("heldout_report_sha256")
        != heldout.get("report_sha256")
        or paired.get("heldout_report_content_sha256")
        != heldout.get("report_content_sha256")
    ):
        context.block("heldout_paired_lineage_mismatch", "heldout report")

    evidence_payload = _read_json_if_possible(
        inputs.resolve_artifact("registry_audit_evidence")
    )
    reference_payload = _read_json_if_possible(
        inputs.resolve_artifact("registry_reference")
    )
    if evidence_payload is not None:
        output_hashes = evidence_payload.get("output_hashes")
        frozen_model = evidence_payload.get("frozen_model")
        if not isinstance(output_hashes, Mapping) or not isinstance(
            frozen_model,
            Mapping,
        ):
            context.block("registry_contract_invalid", "binding objects")
        else:
            expected_pairs = {
                "heldout_evaluation_file_sha256": heldout.get(
                    "report_sha256"
                ),
                "heldout_evaluation_content_sha256": heldout.get(
                    "report_content_sha256"
                ),
                "paired_report_file_sha256": paired.get("report_sha256"),
                "paired_report_content_sha256": paired.get(
                    "report_content_sha256"
                ),
                "paired_lineage_sha256": lineage.get("sha256"),
            }
            for key, expected in expected_pairs.items():
                if expected is None or output_hashes.get(key) != expected:
                    context.block("registry_lineage_mismatch", key)
            if (
                frozen_model.get("manifest_sha256")
                != bundle.get("manifest_sha256")
                or frozen_model.get("weights_sha256")
                != bundle.get("weights_sha256")
            ):
                context.block("registry_lineage_mismatch", "frozen model")
    if reference_payload is not None:
        expected = reference_payload.get("expected_hashes")
        if not isinstance(expected, Mapping):
            context.block("registry_contract_invalid", "reference hashes")
        else:
            for key, observed in (
                ("manifest_sha256", bundle.get("manifest_sha256")),
                ("weights_sha256", bundle.get("weights_sha256")),
                ("checksums_sha256", bundle.get("checksums_sha256")),
            ):
                if observed is None or expected.get(key) != observed:
                    context.block("registry_lineage_mismatch", key)

    held_count = heldout.get("episode_count")
    paired_count = paired.get("episode_count")
    if held_count is None or paired_count is None or held_count != paired_count:
        context.block("episode_count_lineage_mismatch", "heldout vs paired")
    held_cells = heldout.get("scenario_scale_cell_count")
    paired_cells = paired.get("scenario_scale_cell_count")
    if held_cells is None or paired_cells is None or held_cells != paired_cells:
        context.block(
            "scenario_scale_cell_count_lineage_mismatch",
            "heldout vs paired",
        )
    held_seeds = heldout.get("unseen_seed_count")
    paired_seeds = paired.get("seed_count")
    if held_seeds is None or paired_seeds is None or held_seeds != paired_seeds:
        context.block("unseen_seed_count_lineage_mismatch", "heldout vs paired")


def _assemble_consumer_fields(
    inputs: D5G1ExternalAuditInputs,
    *,
    bundle: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    implementation: Mapping[str, Any],
    context: _AuditContext,
) -> dict[str, Any]:
    thresholds = inputs.thresholds
    unseen = _same_value(
        heldout.get("unseen_seed_count"),
        paired.get("seed_count"),
    )
    episodes = _same_value(
        heldout.get("episode_count"),
        paired.get("episode_count"),
    )
    cells = _same_value(
        heldout.get("scenario_scale_cell_count"),
        paired.get("scenario_scale_cell_count"),
    )
    if unseen is not None and unseen < thresholds.minimum_unseen_seed_count:
        context.block(
            "insufficient_unseen_seeds",
            f"{unseen}<{thresholds.minimum_unseen_seed_count}",
        )
    if (
        episodes is not None
        and episodes < thresholds.minimum_heldout_episode_count
    ):
        context.block(
            "insufficient_heldout_episodes",
            f"{episodes}<{thresholds.minimum_heldout_episode_count}",
        )
    if (
        cells is not None
        and cells < thresholds.minimum_scenario_scale_cell_count
    ):
        context.block(
            "insufficient_scenario_scale_cells",
            f"{cells}<{thresholds.minimum_scenario_scale_cell_count}",
        )

    held_formal = heldout.get("formal_inputs")
    paired_formal = paired.get("formal_inputs")
    formal: bool | None = None
    if isinstance(held_formal, Mapping) and isinstance(paired_formal, Mapping):
        formal = (
            held_formal.get("evaluation_role") == "held_out_evaluation"
            and held_formal.get("complete_truth") is True
            and held_formal.get("exact_seed_catalog") is True
            and paired_formal.get("execution_completed") is True
            and paired_formal.get("require_full_profile") is True
            and paired_formal.get("input_artifacts_unchanged") is True
            and paired_formal.get("catalog_complete") is True
            and paired_formal.get("evidence_status") == "authoritative"
        )
        if not formal:
            context.block("formal_evaluation_not_met", "formal profile gates")
    else:
        context.block(
            "formal_evaluation_unavailable",
            "heldout or paired formal fields",
        )

    safety_values = {
        "online_truth_feature_count": paired.get(
            "online_truth_feature_count"
        ),
        "global_track_id_rewrite_count": paired.get(
            "global_track_id_rewrite_count"
        ),
        "same_camera_mutual_exclusion_violation_count": paired.get(
            "same_camera_mutual_exclusion_violation_count"
        ),
    }
    consumer_values = {
        "model_fingerprint": bundle.get("model_fingerprint"),
        "bundle_manifest_sha256": bundle.get("manifest_sha256"),
        "bundle_weights_sha256": bundle.get("weights_sha256"),
        "implementation_sha256": implementation.get(
            "current_implementation_sha256"
        ),
        "dataset_manifest_sha256": bundle.get("dataset_manifest_sha256"),
        "split_sha256": bundle.get("split_sha256"),
        "training_set_sha256": bundle.get("training_set_sha256"),
        "heldout_report_sha256": heldout.get("report_sha256"),
        "heldout_report_content_sha256": heldout.get(
            "report_content_sha256"
        ),
        "paired_shadow_report_sha256": paired.get("report_sha256"),
        "paired_shadow_report_content_sha256": paired.get(
            "report_content_sha256"
        ),
        "formal_evaluation": formal,
        "heldout_passed": heldout.get("passed"),
        "paired_shadow_passed": paired.get("passed"),
        "unseen_seed_count": unseen,
        "heldout_episode_count": episodes,
        "scenario_scale_cell_count": cells,
        **safety_values,
    }
    availability = {
        name: _availability(value)
        for name, value in consumer_values.items()
    }
    for name, record in availability.items():
        if record["available"] is False:
            context.block(f"consumer_field_unavailable.{name}", name)
    return {
        **consumer_values,
        "d6_external_audit_passed": False,
        "failure_reasons": [],
        "field_availability": availability,
    }


def _audit_limitations(
    inputs: D5G1ExternalAuditInputs,
    paired: Mapping[str, Any],
    context: _AuditContext,
) -> dict[str, Any]:
    maximum = paired.get("maximum_single_feature_auc")
    auc = None
    feature = None
    available = False
    if isinstance(maximum, Mapping):
        available = maximum.get("available") is True
        auc = maximum.get("best_direction_auc")
        feature = maximum.get("feature")
    shortcut_passed: bool | None = None
    if available and isinstance(auc, (int, float)) and not isinstance(auc, bool):
        shortcut_passed = (
            float(auc) <= inputs.thresholds.maximum_single_feature_auc
        )
        if not shortcut_passed:
            context.block(
                "synthetic_single_feature_shortcut",
                (
                    f"{auc}>"
                    f"{inputs.thresholds.maximum_single_feature_auc}"
                ),
            )
    else:
        context.block(
            "synthetic_single_feature_metric_unavailable",
            "maximum AUC",
        )

    profiles = paired.get("robustness_profiles")
    minimum_edge: float | None = None
    minimum_cluster: float | None = None
    all_truth_independent: bool | None = None
    all_rebuilt: bool | None = None
    profile_count: int | None = None
    if isinstance(profiles, list) and profiles:
        edge_values = [
            item.get("edge_f1")
            for item in profiles
            if isinstance(item, Mapping)
        ]
        cluster_values = [
            item.get("cluster_f1")
            for item in profiles
            if isinstance(item, Mapping)
        ]
        if (
            len(edge_values) == len(profiles)
            and len(cluster_values) == len(profiles)
            and all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in (*edge_values, *cluster_values)
            )
        ):
            minimum_edge = min(float(value) for value in edge_values)
            minimum_cluster = min(float(value) for value in cluster_values)
        profile_count = len(profiles)
        all_truth_independent = all(
            item.get("truth_dependent") is False for item in profiles
        )
        all_rebuilt = all(
            item.get("candidate_graph_rebuilt") is True for item in profiles
        )
    else:
        context.block("robustness_evidence_unavailable", "profiles")
    if minimum_edge is None:
        context.block("robustness_evidence_unavailable", "edge F1")
    if minimum_cluster is None:
        context.block("robustness_evidence_unavailable", "cluster F1")
    if (
        profile_count is not None
        and profile_count < inputs.thresholds.minimum_robustness_profile_count
    ):
        context.block(
            "insufficient_robustness_profiles",
            (
                f"{profile_count}<"
                f"{inputs.thresholds.minimum_robustness_profile_count}"
            ),
        )
    if (
        minimum_edge is not None
        and minimum_edge < inputs.thresholds.minimum_robustness_edge_f1
    ):
        context.block(
            "robustness_threshold_not_met.edge_f1",
            (
                f"{minimum_edge}<"
                f"{inputs.thresholds.minimum_robustness_edge_f1}"
            ),
        )
    if (
        minimum_cluster is not None
        and minimum_cluster < inputs.thresholds.minimum_robustness_cluster_f1
    ):
        context.block(
            "robustness_threshold_not_met.cluster_f1",
            (
                f"{minimum_cluster}<"
                f"{inputs.thresholds.minimum_robustness_cluster_f1}"
            ),
        )
    if all_truth_independent is False:
        context.block("robustness_truth_dependent", "one or more profiles")
    return {
        "synthetic_single_feature_shortcut": {
            "available": available,
            "feature": feature,
            "observed_best_direction_auc": auc,
            "maximum_allowed_auc": (
                inputs.thresholds.maximum_single_feature_auc
            ),
            "threshold_passed": shortcut_passed,
            "shortcut_detected": (
                None if shortcut_passed is None else not shortcut_passed
            ),
        },
        "robustness_generalization": {
            "available": bool(profiles),
            "profile_count": profile_count,
            "minimum_required_profile_count": (
                inputs.thresholds.minimum_robustness_profile_count
            ),
            "minimum_observed_edge_f1": minimum_edge,
            "minimum_required_edge_f1": (
                inputs.thresholds.minimum_robustness_edge_f1
            ),
            "minimum_observed_cluster_f1": minimum_cluster,
            "minimum_required_cluster_f1": (
                inputs.thresholds.minimum_robustness_cluster_f1
            ),
            "all_profiles_truth_independent": all_truth_independent,
            "all_profiles_rebuilt_candidate_graph": all_rebuilt,
            "candidate_graph_limitation": (
                "profiles hold the post-gate candidate graph fixed"
                if all_rebuilt is False
                else None
            ),
            "profiles": profiles,
        },
        "interpretation": (
            "Synthetic shortcut and fixed-candidate robustness evidence are "
            "reported separately from nominal held-out and paired-shadow gates."
        ),
    }


def _audit_checksum_file(
    path: Path,
    expected: Mapping[str, str],
    context: _AuditContext,
    blocker_code: str,
) -> None:
    if not path.is_file():
        context.block(blocker_code, "file missing")
        return
    try:
        values = _parse_sha256sums(path)
    except (OSError, UnicodeError, ValueError) as exc:
        context.block(blocker_code, str(exc))
        return
    for name, digest in expected.items():
        if values.get(name) != digest:
            context.block(blocker_code, name)


def _strict_mapping(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        context.block(blocker_code, field)
        return {}
    return dict(value)


def _strict_sha_mapping(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> dict[str, str] | None:
    if not isinstance(value, Mapping) or not value:
        context.block(blocker_code, field)
        return None
    result: dict[str, str] = {}
    for name, digest in value.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            context.block(blocker_code, f"{field}.{name}")
            return None
        result[name] = digest
    return result


def _strict_sha(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> str | None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        context.block(blocker_code, field)
        return None
    return value


def _strict_bool(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> bool | None:
    if type(value) is not bool:
        context.block(blocker_code, field)
        return None
    return value


def _strict_int(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> int | None:
    if type(value) is not int or value < 0:
        context.block(blocker_code, field)
        return None
    return value


def _strict_number(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        context.block(blocker_code, field)
        return None
    return float(value)


def _strict_int_sequence(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> list[int] | None:
    if not isinstance(value, list) or any(
        type(item) is not int or item < 0 for item in value
    ):
        context.block(blocker_code, field)
        return None
    return list(value)


def _comparison_passed(actual: float, threshold: float, operator: str) -> bool:
    if operator == ">=":
        return actual >= threshold
    if operator == "<=":
        return actual <= threshold
    raise AssertionError(operator)


def _same_value(left: Any, right: Any) -> Any:
    if left is None or right is None or left != right:
        return None
    return left


def _availability(value: Any) -> dict[str, Any]:
    return {
        "available": value is not None,
        "reason": None if value is not None else "source_evidence_unavailable",
    }


def _artifact_actual_sha(
    inputs: D5G1ExternalAuditInputs,
    name: str,
) -> str | None:
    path = inputs.resolve_artifact(name)
    return _sha256_file(path) if path.is_file() else None


def _safe_child(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise D5G1ExternalAuditError(
            "input_path_outside_repository",
            relative,
        ) from exc
    return path


def _read_json_if_possible(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _parse_sha256sums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="ascii").splitlines(),
        start=1,
    ):
        parts = line.split("  ")
        if len(parts) != 2 or not _SHA256_RE.fullmatch(parts[0]):
            raise ValueError(f"invalid SHA256SUMS line {line_number}")
        name = parts[1]
        if (
            not name
            or Path(name).name != name
            or name in result
        ):
            raise ValueError(f"invalid SHA256SUMS filename {line_number}")
        result[name] = parts[0]
    return result


def _with_content_sha256(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha256_json(result)
    return result


def _sha256_json_without_content(payload: Mapping[str, Any]) -> str:
    value = dict(payload)
    value.pop("content_sha256", None)
    return _sha256_json(value)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_canonical_json_bytes(value))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "D5_G1_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION",
    "D5_G1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION",
    "D5_G1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION",
    "D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION",
    "D5G1ExternalAuditArtifact",
    "D5G1ExternalAuditError",
    "D5G1ExternalAuditInputs",
    "D5G1ExternalAuditThresholds",
    "audit_d5_g1_external_evidence",
    "load_d5_g1_external_audit_inputs",
    "render_d5_g1_external_audit_markdown",
    "write_d5_g1_external_audit_report",
]
