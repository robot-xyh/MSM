"""Strict, read-only post-assembly audit for one D5 G1 v4 bundle.

The existing D5 G1 external audit authenticates a development v3 candidate
and its held-out evidence. This module starts at the separately assembled v4
bundle boundary. It verifies that the v4 manifest, weights, checksum catalog,
and three packaged evidence files are byte- and content-bound to the formal
D6 result. A passing result confirms assembly integrity only. D6 never grants
model promotion, G1 assist, default-path, identity, assignment, or control
authority.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence


D5_G1_POST_ASSEMBLY_AUDIT_SCHEMA_VERSION = (
    "d6.d5-g1-post-assembly-audit.v1"
)
D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION = (
    "d6.d5-g1-post-assembly-audit-input.v1"
)
D5_G1_POST_ASSEMBLY_AUDIT_CONSUMER_SCHEMA_VERSION = (
    "d6.d5-g1-post-assembly-audit-consumer.v1"
)
D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION = (
    "d6.d5-g1-post-assembly-integrity.v1"
)

_D5_V4_SCHEMA = "d5.tracklet-model-bundle.v4"
_D5_V3_SCHEMA = "d5.tracklet-model-bundle.v3"
_D5_ADMISSION_REPORT_SCHEMA = "d5.tracklet-g1-admission-report.v1"
_D5_HELDOUT_SCHEMA = "d5.tracklet-heldout-model-evaluation.v1"
_D5_PAIRED_SCHEMA = "d5.tracklet-paired-shadow.v2"
_D6_EXTERNAL_SCHEMA = "d6.d5-g1-external-audit.v1"
_D6_EXTERNAL_CONSUMER_SCHEMA = "d6.d5-g1-external-audit-consumer.v1"
_D6_EXTERNAL_PROFILE = "d6.d5-g1-formal-heldout-paired-shadow.v1"

_REQUIRED_ARTIFACT_NAMES = (
    "bundle_manifest",
    "bundle_weights",
    "bundle_checksums",
    "heldout_evidence",
    "paired_shadow_evidence",
    "d6_external_audit_evidence",
)
_JSON_ARTIFACT_NAMES = (
    "bundle_manifest",
    "heldout_evidence",
    "paired_shadow_evidence",
    "d6_external_audit_evidence",
)
_CONTENT_HASHED_ARTIFACT_NAMES = (
    "heldout_evidence",
    "paired_shadow_evidence",
    "d6_external_audit_evidence",
)
_EXPECTED_BUNDLE_LAYOUT = {
    "bundle_manifest": "manifest.json",
    "bundle_weights": "weights.pt",
    "bundle_checksums": "SHA256SUMS",
    "heldout_evidence": "evidence/heldout_evaluation.json",
    "paired_shadow_evidence": "evidence/paired_shadow_report.json",
    "d6_external_audit_evidence": "evidence/d6_external_audit.json",
}
_EXPECTED_BUNDLE_DIRECTORIES = ("evidence",)
_CHECKSUM_ARTIFACTS = (
    "d6_external_audit_evidence",
    "heldout_evidence",
    "paired_shadow_evidence",
    "bundle_manifest",
    "bundle_weights",
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
_FORMAL_SEEDS = tuple(range(1000, 1020))
_FORMAL_EPISODE_COUNT = 900
_FORMAL_CELL_COUNT = 45
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class D5G1PostAssemblyAuditError(ValueError):
    """Stable error for an invalid audit request or output destination."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class D5G1PostAssemblyAuditArtifact:
    """One caller-frozen artifact path and file digest."""

    path: str
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise D5G1PostAssemblyAuditError(
                "input_artifact_path_invalid",
                repr(self.path),
            )
        path = Path(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise D5G1PostAssemblyAuditError(
                "input_artifact_path_invalid",
                self.path,
            )
        if (
            not isinstance(self.sha256, str)
            or not _SHA256_RE.fullmatch(self.sha256)
        ):
            raise D5G1PostAssemblyAuditError(
                "input_artifact_sha256_invalid",
                self.path,
            )


@dataclass(frozen=True, slots=True)
class D5G1PostAssemblyAuditInputs:
    """Repository root and fully frozen v4 artifact set."""

    repository_root: Path
    audit_id: str
    evaluated_at_utc: str
    profile_version: str
    expected_external_audit_content_sha256: str
    artifacts: Mapping[str, D5G1PostAssemblyAuditArtifact]
    schema_version: str = D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        root = Path(self.repository_root).expanduser().resolve()
        if not root.is_dir():
            raise D5G1PostAssemblyAuditError(
                "input_repository_root_invalid",
                str(root),
            )
        object.__setattr__(self, "repository_root", root)
        if self.schema_version != D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION:
            raise D5G1PostAssemblyAuditError(
                "input_schema_mismatch",
                self.schema_version,
            )
        for name in ("audit_id", "evaluated_at_utc"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise D5G1PostAssemblyAuditError(
                    "input_string_invalid",
                    name,
                )
        if self.profile_version != D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION:
            raise D5G1PostAssemblyAuditError(
                "input_profile_mismatch",
                self.profile_version,
            )
        if (
            not isinstance(
                self.expected_external_audit_content_sha256,
                str,
            )
            or not _SHA256_RE.fullmatch(
                self.expected_external_audit_content_sha256
            )
        ):
            raise D5G1PostAssemblyAuditError(
                "input_external_content_sha256_invalid",
                str(self.expected_external_audit_content_sha256),
            )
        artifacts = dict(self.artifacts)
        if set(artifacts) != set(_REQUIRED_ARTIFACT_NAMES):
            raise D5G1PostAssemblyAuditError(
                "input_artifact_set_mismatch",
                ",".join(
                    sorted(
                        set(artifacts) ^ set(_REQUIRED_ARTIFACT_NAMES)
                    )
                ),
            )
        if any(
            not isinstance(value, D5G1PostAssemblyAuditArtifact)
            for value in artifacts.values()
        ):
            raise D5G1PostAssemblyAuditError(
                "input_artifact_type_invalid",
                "all artifacts must be frozen artifact records",
            )
        object.__setattr__(self, "artifacts", artifacts)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        repository_root: str | Path,
    ) -> "D5G1PostAssemblyAuditInputs":
        expected_fields = {
            "schema_version",
            "audit_id",
            "evaluated_at_utc",
            "profile_version",
            "expected_external_audit_content_sha256",
            "artifacts",
        }
        if not isinstance(payload, Mapping) or set(payload) != expected_fields:
            raise D5G1PostAssemblyAuditError(
                "input_fields_mismatch",
                "top-level fields differ from v1 schema",
            )
        raw_artifacts = payload.get("artifacts")
        if not isinstance(raw_artifacts, Mapping):
            raise D5G1PostAssemblyAuditError(
                "input_artifact_type_invalid",
                "artifacts must be an object",
            )
        artifacts: dict[str, D5G1PostAssemblyAuditArtifact] = {}
        for name, raw in raw_artifacts.items():
            if (
                not isinstance(raw, Mapping)
                or set(raw) != {"path", "sha256"}
            ):
                raise D5G1PostAssemblyAuditError(
                    "input_artifact_fields_mismatch",
                    str(name),
                )
            artifacts[str(name)] = D5G1PostAssemblyAuditArtifact(
                path=raw["path"],
                sha256=raw["sha256"],
            )
        return cls(
            repository_root=Path(repository_root),
            audit_id=payload["audit_id"],
            evaluated_at_utc=payload["evaluated_at_utc"],
            profile_version=payload["profile_version"],
            expected_external_audit_content_sha256=payload[
                "expected_external_audit_content_sha256"
            ],
            artifacts=artifacts,
            schema_version=payload["schema_version"],
        )

    def resolve_artifact(self, name: str) -> Path:
        return _safe_child(
            self.repository_root,
            self.artifacts[name].path,
        )

    @property
    def bundle_root(self) -> Path:
        return self.resolve_artifact("bundle_manifest").parent


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


def load_d5_g1_post_assembly_audit_inputs(
    path: str | Path,
    *,
    repository_root: str | Path,
) -> D5G1PostAssemblyAuditInputs:
    """Load one strict input specification without adjacent-file discovery."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D5G1PostAssemblyAuditError(
            "input_json_invalid",
            str(source),
        ) from exc
    if not isinstance(payload, dict):
        raise D5G1PostAssemblyAuditError(
            "input_json_object_required",
            str(source),
        )
    return D5G1PostAssemblyAuditInputs.from_mapping(
        payload,
        repository_root=repository_root,
    )


def audit_d5_g1_post_assembly_bundle(
    inputs: D5G1PostAssemblyAuditInputs,
) -> dict[str, Any]:
    """Audit one assembled v4 bundle and return a fail-closed result."""

    context = _AuditContext()
    artifact_rows, payloads, actual_hashes = _audit_artifacts(inputs, context)
    weights_path = inputs.resolve_artifact("bundle_weights")
    actual_weight_size = (
        weights_path.stat().st_size
        if _is_regular_file_without_symlink(
            weights_path,
            inputs.repository_root,
        )
        else None
    )
    checksum_evidence = _audit_layout_and_checksums(
        inputs,
        actual_hashes,
        context,
    )
    manifest = _audit_manifest(
        payloads.get("bundle_manifest"),
        actual_hashes,
        actual_weight_size,
        context,
    )
    heldout = _audit_heldout(
        payloads.get("heldout_evidence"),
        context,
    )
    paired = _audit_paired_shadow(
        payloads.get("paired_shadow_evidence"),
        context,
    )
    external = _audit_external_audit(
        payloads.get("d6_external_audit_evidence"),
        inputs,
        context,
    )
    cross = _audit_cross_bindings(
        manifest=manifest,
        heldout=heldout,
        paired=paired,
        external=external,
        actual_hashes=actual_hashes,
        context=context,
    )
    blockers = context.blockers
    passed = not blockers
    consumer = {
        "schema_version": (
            D5_G1_POST_ASSEMBLY_AUDIT_CONSUMER_SCHEMA_VERSION
        ),
        "post_assembly_integrity_passed": passed,
        "bundle_schema_version": manifest.get("schema_version"),
        "bundle_manifest_sha256": actual_hashes.get("bundle_manifest"),
        "bundle_weights_sha256": actual_hashes.get("bundle_weights"),
        "bundle_checksums_sha256": actual_hashes.get("bundle_checksums"),
        "source_development_manifest_sha256": cross.get(
            "source_development_manifest_sha256"
        ),
        "source_development_checksums_sha256": cross.get(
            "source_development_checksums_sha256"
        ),
        "d6_external_audit_sha256": actual_hashes.get(
            "d6_external_audit_evidence"
        ),
        "d6_external_audit_content_sha256": cross.get(
            "d6_external_audit_content_sha256"
        ),
        "runtime_implementation_sha256": cross.get(
            "runtime_implementation_sha256"
        ),
        "model_fingerprint": cross.get("model_fingerprint"),
        "unseen_seed_count": cross.get("unseen_seed_count"),
        "heldout_episode_count": cross.get("heldout_episode_count"),
        "scenario_scale_cell_count": cross.get(
            "scenario_scale_cell_count"
        ),
        "online_truth_feature_count": cross.get(
            "online_truth_feature_count"
        ),
        "global_track_id_rewrite_count": cross.get(
            "global_track_id_rewrite_count"
        ),
        "same_camera_mutual_exclusion_violation_count": cross.get(
            "same_camera_mutual_exclusion_violation_count"
        ),
        "bundle_declared_g1_assist_eligible": manifest.get(
            "g1_assist_eligible"
        ),
        "failure_reasons": blockers,
    }
    consumer["field_availability"] = {
        name: _availability(value)
        for name, value in consumer.items()
        if name
        not in {
            "schema_version",
            "post_assembly_integrity_passed",
            "failure_reasons",
        }
    }
    result: dict[str, Any] = {
        "schema_version": D5_G1_POST_ASSEMBLY_AUDIT_SCHEMA_VERSION,
        "audit_id": inputs.audit_id,
        "evaluated_at_utc": inputs.evaluated_at_utc,
        "profile_version": inputs.profile_version,
        "status": "pass" if passed else "fail_closed",
        "audit_passed": passed,
        "fail_closed": not passed,
        "post_assembly_integrity_only": True,
        "input_contract": {
            "schema_version": inputs.schema_version,
            "expected_external_audit_content_sha256": (
                inputs.expected_external_audit_content_sha256
            ),
            "required_seed_count": len(_FORMAL_SEEDS),
            "required_episode_count": _FORMAL_EPISODE_COUNT,
            "required_scenario_scale_cell_count": _FORMAL_CELL_COUNT,
        },
        "artifact_evidence": artifact_rows,
        "bundle": manifest,
        "checksum_evidence": checksum_evidence,
        "evidence": {
            "heldout": heldout,
            "paired_shadow": paired,
            "d6_external_audit": external,
        },
        "cross_binding": cross,
        "d5_consumer_contract": consumer,
        "blocker_codes": blockers,
        "blocker_details": context.blocker_details(),
        "authority": {
            "model_promotion_granted": False,
            "g1_assist_granted": False,
            "default_path_change_granted": False,
            "global_track_id_authority_granted": False,
            "assignment_authority_granted": False,
            "control_authority_granted": False,
            "reason": (
                "D6 confirms post-assembly evidence integrity only; all "
                "runtime and promotion authority remains outside D6"
            ),
        },
        "limitations": {
            "fixed_candidate_graph": external.get(
                "fixed_candidate_graph_limitation"
            ),
            "real_camera_evidence": False,
            "online_runtime_enabled_by_this_audit": False,
            "interpretation": (
                "A pass authenticates v4 assembly only. It does not prove "
                "real-camera generalization or enable an online path."
            ),
        },
        "availability_policy": {
            "missing_evidence": "unavailable_and_fail_closed",
            "type_error": "unavailable_and_fail_closed",
            "sha256_mismatch": "fail_closed",
            "content_sha256_mismatch": "fail_closed",
            "extra_checksum_entry": "fail_closed",
            "authority_true": "fail_closed",
            "zero_fill_allowed": False,
        },
    }
    return _with_content_sha256(result)


def write_d5_g1_post_assembly_audit_report(
    output_dir: str | Path,
    result: Mapping[str, Any],
    *,
    inputs: D5G1PostAssemblyAuditInputs,
) -> dict[str, Path]:
    """Atomically write deterministic JSON, CSV, Markdown, and checksums."""

    output = Path(output_dir).expanduser().resolve()
    bundle_root = inputs.bundle_root.resolve()
    if _paths_overlap(output, bundle_root):
        raise D5G1PostAssemblyAuditError(
            "output_input_overlap",
            f"{output} overlaps {bundle_root}",
        )
    for name in _REQUIRED_ARTIFACT_NAMES:
        artifact_path = inputs.resolve_artifact(name)
        if _paths_overlap(output, artifact_path):
            raise D5G1PostAssemblyAuditError(
                "output_input_overlap",
                f"{output} overlaps {artifact_path}",
            )
    if output.exists():
        raise D5G1PostAssemblyAuditError(
            "output_directory_exists",
            str(output),
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.",
            dir=output.parent,
        )
    )
    try:
        json_path = staging / "d5_g1_post_assembly_audit.json"
        csv_path = staging / "d5_g1_post_assembly_audit_evidence.csv"
        markdown_path = staging / "D5_G1_POST_ASSEMBLY_AUDIT_CN.md"
        checksums_path = staging / "SHA256SUMS"
        _write_json(json_path, result)
        _write_artifact_csv(csv_path, result)
        markdown_path.write_text(
            render_d5_g1_post_assembly_audit_markdown(result),
            encoding="utf-8",
        )
        content_files = (csv_path, json_path, markdown_path)
        checksums_path.write_text(
            "".join(
                f"{_sha256_file(path)}  {path.name}\n"
                for path in sorted(content_files, key=lambda item: item.name)
            ),
            encoding="ascii",
        )
        os.replace(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "json": output / "d5_g1_post_assembly_audit.json",
        "csv": output / "d5_g1_post_assembly_audit_evidence.csv",
        "markdown": output / "D5_G1_POST_ASSEMBLY_AUDIT_CN.md",
        "checksums": output / "SHA256SUMS",
    }


def render_d5_g1_post_assembly_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render a concise Chinese report without implying runtime authority."""

    consumer = _as_mapping(result.get("d5_consumer_contract"))
    authority = _as_mapping(result.get("authority"))
    limitations = _as_mapping(result.get("limitations"))
    lines = [
        "# D5 G1 v4 装配后外部审计",
        "",
        f"审计时间：`{result.get('evaluated_at_utc')}`",
        "",
        "## 结论",
        "",
        f"装配证据审计结果为 **{result.get('status')}**。",
        (
            "D6 只确认 v4 装配证据完整性，不授予模型晋级、G1 辅助、"
            "默认路径、身份、分配或控制权限。"
        ),
        "",
        "## 束缚关系",
        "",
        (
            "- v4 manifest SHA-256："
            f"`{consumer.get('bundle_manifest_sha256')}`。"
        ),
        (
            "- weights SHA-256："
            f"`{consumer.get('bundle_weights_sha256')}`。"
        ),
        (
            "- 原开发包 manifest SHA-256："
            f"`{consumer.get('source_development_manifest_sha256')}`。"
        ),
        (
            "- D6 预准入 JSON 文件/内容 SHA-256："
            f"`{consumer.get('d6_external_audit_sha256')}` / "
            f"`{consumer.get('d6_external_audit_content_sha256')}`。"
        ),
        (
            "- 运行实现摘要："
            f"`{consumer.get('runtime_implementation_sha256')}`。"
        ),
        "",
        "## 样本与安全",
        "",
        f"- 未见 seed：`{consumer.get('unseen_seed_count')}`。",
        f"- held-out episode：`{consumer.get('heldout_episode_count')}`。",
        (
            "- 场景规模单元："
            f"`{consumer.get('scenario_scale_cell_count')}`。"
        ),
        (
            "- 在线真值字段："
            f"`{consumer.get('online_truth_feature_count')}`。"
        ),
        (
            "- global_track_id 改写："
            f"`{consumer.get('global_track_id_rewrite_count')}`。"
        ),
        (
            "- 同相机互斥违规："
            f"{consumer.get('same_camera_mutual_exclusion_violation_count')}。"
        ),
        "",
        "## 权限边界",
        "",
        (
            "- v4 声明的 G1 辅助资格："
            f"`{consumer.get('bundle_declared_g1_assist_eligible')}`。"
        ),
        (
            "- D6 模型晋级授权："
            f"`{authority.get('model_promotion_granted')}`。"
        ),
        (
            "- D6 G1 辅助授权："
            f"`{authority.get('g1_assist_granted')}`。"
        ),
        (
            "- D6 控制授权："
            f"`{authority.get('control_authority_granted')}`。"
        ),
        "",
        "## 限制",
        "",
        (
            "- 固定候选图限制："
            f"`{limitations.get('fixed_candidate_graph')}`。"
        ),
        "- 真实相机证据：未覆盖。",
        "- 在线路径：本审计不启用。",
        "",
        "## 阻断项",
        "",
    ]
    blockers = list(result.get("blocker_codes", ()))
    if blockers:
        lines.extend(f"- `{code}`" for code in blockers)
    else:
        lines.append("- 无。")
    return "\n".join(lines) + "\n"


def _audit_artifacts(
    inputs: D5G1PostAssemblyAuditInputs,
    context: _AuditContext,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    actual_hashes: dict[str, str] = {}
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
        symlink = _first_symlink_component(
            path,
            inputs.repository_root,
        )
        if symlink is not None:
            code = f"artifact_symlink.{name}"
            context.block(
                code,
                str(symlink.relative_to(inputs.repository_root)),
            )
            row["blocker_codes"].append(code)
            rows.append(row)
            continue
        if not path.is_file():
            code = f"artifact_unavailable.{name}"
            context.block(code, binding.path)
            row["blocker_codes"].append(code)
            rows.append(row)
            continue
        actual = _sha256_file(path)
        actual_hashes[name] = actual
        row["availability"] = "available"
        row["actual_sha256"] = actual
        row["sha256_match"] = actual == binding.sha256
        if actual != binding.sha256:
            code = f"artifact_sha256_mismatch.{name}"
            context.block(code, f"{actual}!={binding.sha256}")
            row["blocker_codes"].append(code)
        if name in _JSON_ARTIFACT_NAMES:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                code = f"artifact_json_invalid.{name}"
                context.block(code, str(exc))
                row["blocker_codes"].append(code)
                rows.append(row)
                continue
            if not isinstance(payload, dict):
                code = f"artifact_json_invalid.{name}"
                context.block(code, "top level is not an object")
                row["blocker_codes"].append(code)
                rows.append(row)
                continue
            payloads[name] = payload
            if name in _CONTENT_HASHED_ARTIFACT_NAMES:
                declared = payload.get("content_sha256")
                actual_content = _sha256_json_without_content(payload)
                row["content_sha256"] = declared
                row["content_sha256_verified"] = (
                    isinstance(declared, str)
                    and declared == actual_content
                )
                if (
                    not isinstance(declared, str)
                    or not _SHA256_RE.fullmatch(declared)
                    or declared != actual_content
                ):
                    code = f"artifact_content_sha256_mismatch.{name}"
                    context.block(
                        code,
                        f"{declared}!={actual_content}",
                    )
                    row["blocker_codes"].append(code)
        rows.append(row)
    return rows, payloads, actual_hashes


def _audit_layout_and_checksums(
    inputs: D5G1PostAssemblyAuditInputs,
    actual_hashes: Mapping[str, str],
    context: _AuditContext,
) -> dict[str, Any]:
    bundle_root = inputs.bundle_root
    tree_evidence = _audit_bundle_tree(
        bundle_root,
        inputs.repository_root,
        context,
    )
    layout_matches: dict[str, bool] = {}
    for name, relative in _EXPECTED_BUNDLE_LAYOUT.items():
        expected = bundle_root / relative
        actual = inputs.resolve_artifact(name)
        matched = actual == expected
        layout_matches[name] = matched
        if not matched:
            context.block(
                f"bundle_layout_mismatch.{name}",
                f"{actual}!={expected}",
            )
    parsed: dict[str, str] | None = None
    ordered_names: list[str] | None = None
    checksum_path = inputs.resolve_artifact("bundle_checksums")
    if _is_regular_file_without_symlink(
        checksum_path,
        inputs.repository_root,
    ):
        try:
            parsed, ordered_names = _parse_sha256sums(checksum_path)
        except (OSError, UnicodeError, ValueError) as exc:
            context.block("bundle_checksums_invalid", str(exc))
    expected_checksums = {
        _EXPECTED_BUNDLE_LAYOUT[name]: actual_hashes.get(name)
        for name in _CHECKSUM_ARTIFACTS
    }
    if parsed is not None:
        if set(parsed) != set(expected_checksums):
            context.block(
                "bundle_checksums_entry_set_mismatch",
                ",".join(
                    sorted(set(parsed) ^ set(expected_checksums))
                ),
            )
        if ordered_names != sorted(expected_checksums):
            context.block(
                "bundle_checksums_order_invalid",
                ",".join(ordered_names or ()),
            )
        for filename, expected in expected_checksums.items():
            if parsed.get(filename) != expected:
                context.block(
                    f"bundle_checksums_digest_mismatch.{filename}",
                    f"{parsed.get(filename)}!={expected}",
                )
    return {
        "bundle_root": str(bundle_root.relative_to(inputs.repository_root)),
        "tree_evidence": tree_evidence,
        "layout_matches": layout_matches,
        "expected_entries": expected_checksums,
        "observed_entries": parsed,
        "exact_coverage": (
            parsed == expected_checksums
            and ordered_names == sorted(expected_checksums)
        ),
    }


def _audit_manifest(
    payload: Mapping[str, Any] | None,
    actual_hashes: Mapping[str, str],
    actual_weight_size: int | None,
    context: _AuditContext,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": payload is not None,
        "schema_version": None,
        "source_development_bundle": None,
        "weights": None,
        "training_dataset": None,
        "code_provenance": None,
        "evidence": None,
        "admission": None,
        "admission_report": None,
        "g1_assist_eligible": None,
    }
    if payload is None:
        context.block("bundle_manifest_unavailable", "manifest")
        return result
    result["schema_version"] = payload.get("schema_version")
    if payload.get("schema_version") != _D5_V4_SCHEMA:
        context.block(
            "bundle_schema_mismatch",
            str(payload.get("schema_version")),
        )

    source = _strict_mapping(
        payload.get("source_development_bundle"),
        context,
        "bundle_manifest_type_invalid",
        "source_development_bundle",
    )
    result["source_development_bundle"] = dict(source)
    if set(source) != {
        "schema_version",
        "admission_status",
        "manifest_sha256",
        "weights_sha256",
        "checksums_sha256",
    }:
        context.block(
            "source_development_bundle_fields_mismatch",
            "source_development_bundle",
        )
    if source.get("schema_version") != _D5_V3_SCHEMA:
        context.block(
            "source_development_bundle_schema_mismatch",
            str(source.get("schema_version")),
        )
    if source.get("admission_status") != "development_only_fail_closed":
        context.block(
            "source_development_bundle_admission_invalid",
            str(source.get("admission_status")),
        )
    for name in ("manifest_sha256", "weights_sha256", "checksums_sha256"):
        _require_sha(
            source.get(name),
            context,
            "bundle_manifest_type_invalid",
            f"source_development_bundle.{name}",
        )

    weights = _strict_mapping(
        payload.get("weights"),
        context,
        "bundle_manifest_type_invalid",
        "weights",
    )
    result["weights"] = dict(weights)
    if weights.get("filename") != "weights.pt":
        context.block(
            "bundle_weights_filename_mismatch",
            str(weights.get("filename")),
        )
    if weights.get("format") != "pytorch_state_dict_weights_only":
        context.block(
            "bundle_weights_format_mismatch",
            str(weights.get("format")),
        )
    weight_sha = _require_sha(
        weights.get("sha256"),
        context,
        "bundle_manifest_type_invalid",
        "weights.sha256",
    )
    if (
        weight_sha is not None
        and weight_sha != actual_hashes.get("bundle_weights")
    ):
        context.block(
            "bundle_weights_metadata_mismatch",
            f"{weight_sha}!={actual_hashes.get('bundle_weights')}",
        )
    size = _strict_int(
        weights.get("size_bytes"),
        context,
        "bundle_manifest_type_invalid",
        "weights.size_bytes",
    )
    model_fingerprint = weights.get("model_fingerprint")
    if model_fingerprint != f"sha256:{actual_hashes.get('bundle_weights')}":
        context.block(
            "bundle_model_fingerprint_mismatch",
            str(model_fingerprint),
        )
    if (
        size is not None
        and actual_weight_size is not None
        and size != actual_weight_size
    ):
        context.block(
            "bundle_weights_size_mismatch",
            f"{size}!={actual_weight_size}",
        )

    training = _strict_sha_mapping(
        payload.get("training_dataset"),
        context,
        "bundle_manifest_type_invalid",
        "training_dataset",
    )
    result["training_dataset"] = training
    required_training = {
        "dataset_manifest_sha256",
        "split_sha256",
        "training_config_sha256",
        "training_set_sha256",
    }
    if set(training) != required_training:
        context.block(
            "bundle_training_fields_mismatch",
            ",".join(sorted(set(training) ^ required_training)),
        )

    provenance = _strict_mapping(
        payload.get("code_provenance"),
        context,
        "bundle_manifest_type_invalid",
        "code_provenance",
    )
    source_files = _strict_sha_mapping(
        provenance.get("source_files"),
        context,
        "bundle_manifest_type_invalid",
        "code_provenance.source_files",
    )
    runtime_files = _strict_sha_mapping(
        provenance.get("runtime_source_files"),
        context,
        "bundle_manifest_type_invalid",
        "code_provenance.runtime_source_files",
    )
    implementation_sha = _require_sha(
        provenance.get("implementation_sha256"),
        context,
        "bundle_manifest_type_invalid",
        "code_provenance.implementation_sha256",
    )
    runtime_sha = _require_sha(
        provenance.get("runtime_implementation_sha256"),
        context,
        "bundle_manifest_type_invalid",
        "code_provenance.runtime_implementation_sha256",
    )
    if set(source_files) != set(_MODEL_IMPLEMENTATION_FILES):
        context.block(
            "bundle_model_source_set_mismatch",
            ",".join(
                sorted(
                    set(source_files) ^ set(_MODEL_IMPLEMENTATION_FILES)
                )
            ),
        )
    if set(runtime_files) != set(_RUNTIME_IMPLEMENTATION_FILES):
        context.block(
            "bundle_runtime_source_set_mismatch",
            ",".join(
                sorted(
                    set(runtime_files) ^ set(_RUNTIME_IMPLEMENTATION_FILES)
                )
            ),
        )
    if (
        implementation_sha is not None
        and implementation_sha != _sha256_json(dict(sorted(source_files.items())))
    ):
        context.block(
            "bundle_model_implementation_sha256_mismatch",
            str(implementation_sha),
        )
    if (
        runtime_sha is not None
        and runtime_sha != _sha256_json(dict(sorted(runtime_files.items())))
    ):
        context.block(
            "bundle_runtime_implementation_sha256_mismatch",
            str(runtime_sha),
        )
    for name in _MODEL_IMPLEMENTATION_FILES:
        if source_files.get(name) != runtime_files.get(name):
            context.block(
                f"bundle_model_runtime_source_mismatch.{name}",
                f"{source_files.get(name)}!={runtime_files.get(name)}",
            )
    result["code_provenance"] = {
        "implementation_sha256": implementation_sha,
        "runtime_implementation_sha256": runtime_sha,
        "source_files": source_files,
        "runtime_source_files": runtime_files,
    }

    evidence = _strict_mapping(
        payload.get("evidence"),
        context,
        "bundle_manifest_type_invalid",
        "evidence",
    )
    if set(evidence) != {"heldout", "paired_shadow", "d6_external_audit"}:
        context.block(
            "bundle_evidence_fields_mismatch",
            "manifest.evidence",
        )
    evidence_result: dict[str, dict[str, Any]] = {}
    for name, expected_filename in (
        ("heldout", _EXPECTED_BUNDLE_LAYOUT["heldout_evidence"]),
        (
            "paired_shadow",
            _EXPECTED_BUNDLE_LAYOUT["paired_shadow_evidence"],
        ),
        (
            "d6_external_audit",
            _EXPECTED_BUNDLE_LAYOUT["d6_external_audit_evidence"],
        ),
    ):
        record = _strict_mapping(
            evidence.get(name),
            context,
            "bundle_manifest_type_invalid",
            f"evidence.{name}",
        )
        if set(record) != {"filename", "sha256", "content_sha256"}:
            context.block(
                f"bundle_evidence_record_fields_mismatch.{name}",
                name,
            )
        if record.get("filename") != expected_filename:
            context.block(
                f"bundle_evidence_filename_mismatch.{name}",
                str(record.get("filename")),
            )
        for field in ("sha256", "content_sha256"):
            _require_sha(
                record.get(field),
                context,
                "bundle_manifest_type_invalid",
                f"evidence.{name}.{field}",
            )
        evidence_result[name] = dict(record)
    result["evidence"] = evidence_result

    admission = _strict_mapping(
        payload.get("admission"),
        context,
        "bundle_manifest_type_invalid",
        "admission",
    )
    expected_admission_fields = {
        "status",
        "default_model",
        "g1_assist_eligible",
        "global_track_id_authority",
        "assignment_authority",
        "control_authority",
        "report",
    }
    if set(admission) != expected_admission_fields:
        context.block(
            "bundle_admission_fields_mismatch",
            ",".join(
                sorted(set(admission) ^ expected_admission_fields)
            ),
        )
    if admission.get("status") != "g1_assist_admitted":
        context.block(
            "bundle_admission_status_invalid",
            str(admission.get("status")),
        )
    permission_expectations = {
        "default_model": False,
        "g1_assist_eligible": True,
        "global_track_id_authority": False,
        "assignment_authority": False,
        "control_authority": False,
    }
    for name, expected in permission_expectations.items():
        value = _strict_bool(
            admission.get(name),
            context,
            "bundle_manifest_type_invalid",
            f"admission.{name}",
        )
        if value is not None and value is not expected:
            context.block(
                f"bundle_admission_permission_invalid.{name}",
                f"{value}!={expected}",
            )
    report = _strict_mapping(
        admission.get("report"),
        context,
        "bundle_manifest_type_invalid",
        "admission.report",
    )
    if report.get("schema_version") != _D5_ADMISSION_REPORT_SCHEMA:
        context.block(
            "bundle_admission_report_schema_mismatch",
            str(report.get("schema_version")),
        )
    result["admission"] = {
        name: admission.get(name)
        for name in expected_admission_fields
        if name != "report"
    }
    result["admission_report"] = dict(report)
    result["g1_assist_eligible"] = admission.get("g1_assist_eligible")
    return result


def _audit_heldout(
    payload: Mapping[str, Any] | None,
    context: _AuditContext,
) -> dict[str, Any]:
    result: dict[str, Any] = {"available": payload is not None, "raw": payload}
    if payload is None:
        context.block("heldout_evidence_unavailable", "heldout")
        return result
    if payload.get("schema_version") != _D5_HELDOUT_SCHEMA:
        context.block(
            "heldout_schema_mismatch",
            str(payload.get("schema_version")),
        )
    if payload.get("evaluation_role") != "held_out_evaluation":
        context.block(
            "heldout_role_invalid",
            str(payload.get("evaluation_role")),
        )
    development = _strict_mapping(
        payload.get("development_model"),
        context,
        "heldout_type_invalid",
        "development_model",
    )
    corpus = _strict_mapping(
        payload.get("heldout_corpus"),
        context,
        "heldout_type_invalid",
        "heldout_corpus",
    )
    assessment = _strict_mapping(
        payload.get("heldout_assessment"),
        context,
        "heldout_type_invalid",
        "heldout_assessment",
    )
    overall = _strict_mapping(
        payload.get("overall"),
        context,
        "heldout_type_invalid",
        "overall",
    )
    safety = _strict_mapping(
        payload.get("identity_and_truth_safety"),
        context,
        "heldout_type_invalid",
        "identity_and_truth_safety",
    )
    if (
        assessment.get("status") != "pass"
        or _strict_bool(
            assessment.get("passed"),
            context,
            "heldout_type_invalid",
            "heldout_assessment.passed",
        )
        is not True
    ):
        context.block("heldout_not_passed", "heldout_assessment")
    for field in ("authority_enabled", "g1_assist_eligible"):
        value = _strict_bool(
            assessment.get(field),
            context,
            "heldout_type_invalid",
            f"heldout_assessment.{field}",
        )
        if value is not False:
            context.block(f"heldout_authority_not_closed.{field}", str(value))
    if overall.get("complete_truth") is not True:
        context.block("heldout_truth_incomplete", "overall.complete_truth")
    if safety.get("global_track_id_created_or_rebound") is not False:
        context.block(
            "heldout_global_track_id_rewrite",
            str(safety.get("global_track_id_created_or_rebound")),
        )
    result.update(
        {
            "development_model": dict(development),
            "heldout_corpus": dict(corpus),
            "heldout_assessment": dict(assessment),
            "overall": dict(overall),
            "identity_and_truth_safety": dict(safety),
            "implementation_source_files": _strict_sha_mapping(
                payload.get("implementation_sha256"),
                context,
                "heldout_type_invalid",
                "implementation_sha256",
            ),
            "content_sha256": payload.get("content_sha256"),
        }
    )
    return result


def _audit_paired_shadow(
    payload: Mapping[str, Any] | None,
    context: _AuditContext,
) -> dict[str, Any]:
    result: dict[str, Any] = {"available": payload is not None, "raw": payload}
    if payload is None:
        context.block("paired_shadow_evidence_unavailable", "paired")
        return result
    if payload.get("schema_version") != _D5_PAIRED_SCHEMA:
        context.block(
            "paired_shadow_schema_mismatch",
            str(payload.get("schema_version")),
        )
    if (
        payload.get("status") != "pass"
        or payload.get("execution_completed") is not True
        or payload.get("evaluation_role") != "evaluator_only_paired_shadow"
    ):
        context.block("paired_shadow_not_passed", "top-level status")
    spec = _strict_mapping(
        payload.get("input_spec"),
        context,
        "paired_shadow_type_invalid",
        "input_spec",
    )
    expected_hashes = _strict_sha_mapping(
        spec.get("expected_hashes"),
        context,
        "paired_shadow_type_invalid",
        "input_spec.expected_hashes",
    )
    before = _strict_sha_mapping(
        payload.get("input_hashes_before"),
        context,
        "paired_shadow_type_invalid",
        "input_hashes_before",
    )
    after = _strict_sha_mapping(
        payload.get("input_hashes_after"),
        context,
        "paired_shadow_type_invalid",
        "input_hashes_after",
    )
    if before != expected_hashes or after != expected_hashes:
        context.block(
            "paired_shadow_input_mutation",
            "spec/before/after differ",
        )
    if payload.get("input_artifacts_unchanged") is not True:
        context.block(
            "paired_shadow_input_mutation",
            "input_artifacts_unchanged",
        )
    if spec.get("require_full_profile") is not True:
        context.block(
            "paired_shadow_profile_incomplete",
            "require_full_profile",
        )
    status = _strict_mapping(
        payload.get("evidence_status"),
        context,
        "paired_shadow_type_invalid",
        "evidence_status",
    )
    if status.get("status") != "authoritative":
        context.block(
            "paired_shadow_evidence_status_invalid",
            str(status.get("status")),
        )
    catalog = _strict_mapping(
        payload.get("catalog_integrity"),
        context,
        "paired_shadow_type_invalid",
        "catalog_integrity",
    )
    if catalog.get("complete") is not True:
        context.block("paired_shadow_catalog_incomplete", "complete")
    assessment = _strict_mapping(
        payload.get("paired_shadow_assessment"),
        context,
        "paired_shadow_type_invalid",
        "paired_shadow_assessment",
    )
    if (
        assessment.get("status") != "pass"
        or assessment.get("passed") is not True
    ):
        context.block("paired_shadow_not_passed", "assessment")
    authority = _strict_mapping(
        payload.get("authority"),
        context,
        "paired_shadow_type_invalid",
        "authority",
    )
    for field in ("g1", "assist", "authority", "runtime_default_changed"):
        if authority.get(field) is not False:
            context.block(
                f"paired_shadow_authority_not_closed.{field}",
                str(authority.get(field)),
            )
    result.update(
        {
            "input_spec": dict(spec),
            "expected_hashes": expected_hashes,
            "totals": dict(
                _strict_mapping(
                    payload.get("totals"),
                    context,
                    "paired_shadow_type_invalid",
                    "totals",
                )
            ),
            "identity_and_truth_safety": dict(
                _strict_mapping(
                    payload.get("identity_and_truth_safety"),
                    context,
                    "paired_shadow_type_invalid",
                    "identity_and_truth_safety",
                )
            ),
            "implementation_source_files": _strict_sha_mapping(
                payload.get("implementation_sha256"),
                context,
                "paired_shadow_type_invalid",
                "implementation_sha256",
            ),
            "authority": dict(authority),
            "content_sha256": payload.get("content_sha256"),
        }
    )
    return result


def _audit_external_audit(
    payload: Mapping[str, Any] | None,
    inputs: D5G1PostAssemblyAuditInputs,
    context: _AuditContext,
) -> dict[str, Any]:
    result: dict[str, Any] = {"available": payload is not None, "raw": payload}
    if payload is None:
        context.block("external_audit_evidence_unavailable", "external audit")
        return result
    if payload.get("schema_version") != _D6_EXTERNAL_SCHEMA:
        context.block(
            "external_audit_schema_mismatch",
            str(payload.get("schema_version")),
        )
    if payload.get("formal_profile_version") != _D6_EXTERNAL_PROFILE:
        context.block(
            "external_audit_profile_mismatch",
            str(payload.get("formal_profile_version")),
        )
    if (
        payload.get("status") != "pass"
        or payload.get("audit_passed") is not True
        or payload.get("fail_closed") is not False
        or payload.get("evidence_audit_only") is not True
    ):
        context.block("external_audit_not_passed", "top-level result")
    blockers = payload.get("blocker_codes")
    details = payload.get("blocker_details")
    if blockers != [] or details != {}:
        context.block(
            "external_audit_has_blockers",
            f"{blockers!r}/{details!r}",
        )
    declared_content = payload.get("content_sha256")
    if declared_content != inputs.expected_external_audit_content_sha256:
        context.block(
            "external_audit_expected_content_sha256_mismatch",
            (
                f"{declared_content}!="
                f"{inputs.expected_external_audit_content_sha256}"
            ),
        )
    authority = _strict_mapping(
        payload.get("authority"),
        context,
        "external_audit_type_invalid",
        "authority",
    )
    expected_authority_fields = {
        "model_promotion_granted",
        "g1_assist_granted",
        "control_authority_granted",
        "default_path_change_granted",
    }
    if set(authority) != expected_authority_fields | {"reason"}:
        context.block(
            "external_audit_authority_fields_mismatch",
            ",".join(
                sorted(
                    set(authority)
                    ^ (expected_authority_fields | {"reason"})
                )
            ),
        )
    for field in expected_authority_fields:
        value = _strict_bool(
            authority.get(field),
            context,
            "external_audit_type_invalid",
            f"authority.{field}",
        )
        if value is not False:
            context.block(
                f"external_audit_authority_not_closed.{field}",
                str(value),
            )
    consumer = _strict_mapping(
        payload.get("d5_consumer_contract"),
        context,
        "external_audit_type_invalid",
        "d5_consumer_contract",
    )
    if consumer.get("schema_version") != _D6_EXTERNAL_CONSUMER_SCHEMA:
        context.block(
            "external_audit_consumer_schema_mismatch",
            str(consumer.get("schema_version")),
        )
    if (
        consumer.get("d6_external_audit_passed") is not True
        or consumer.get("failure_reasons") != []
    ):
        context.block(
            "external_audit_consumer_not_passed",
            str(consumer.get("failure_reasons")),
        )
    availability = _strict_mapping(
        consumer.get("field_availability"),
        context,
        "external_audit_type_invalid",
        "d5_consumer_contract.field_availability",
    )
    for name, raw in availability.items():
        record = _strict_mapping(
            raw,
            context,
            "external_audit_type_invalid",
            f"field_availability.{name}",
        )
        if record.get("available") is not True or record.get("reason") is not None:
            context.block(
                f"external_audit_consumer_field_unavailable.{name}",
                str(record),
            )
    artifact_rows = payload.get("artifact_evidence")
    if not isinstance(artifact_rows, list) or len(artifact_rows) != 9:
        context.block(
            "external_audit_artifact_evidence_invalid",
            "expected nine rows",
        )
    else:
        for index, raw in enumerate(artifact_rows):
            row = _strict_mapping(
                raw,
                context,
                "external_audit_type_invalid",
                f"artifact_evidence[{index}]",
            )
            if (
                row.get("availability") != "available"
                or row.get("sha256_match") is not True
                or row.get("blocker_codes") != []
            ):
                context.block(
                    "external_audit_artifact_evidence_invalid",
                    str(row.get("artifact_id", index)),
                )
    candidate = _strict_mapping(
        payload.get("candidate"),
        context,
        "external_audit_type_invalid",
        "candidate",
    )
    limitations = _strict_mapping(
        payload.get("limitations"),
        context,
        "external_audit_type_invalid",
        "limitations",
    )
    robustness = _strict_mapping(
        limitations.get("robustness_generalization"),
        context,
        "external_audit_type_invalid",
        "limitations.robustness_generalization",
    )
    result.update(
        {
            "content_sha256": declared_content,
            "consumer": dict(consumer),
            "authority": dict(authority),
            "candidate": dict(candidate),
            "fixed_candidate_graph_limitation": robustness.get(
                "candidate_graph_limitation"
            ),
        }
    )
    return result


def _audit_cross_bindings(
    *,
    manifest: Mapping[str, Any],
    heldout: Mapping[str, Any],
    paired: Mapping[str, Any],
    external: Mapping[str, Any],
    actual_hashes: Mapping[str, str],
    context: _AuditContext,
) -> dict[str, Any]:
    source = _as_mapping(manifest.get("source_development_bundle"))
    weights = _as_mapping(manifest.get("weights"))
    training = _as_mapping(manifest.get("training_dataset"))
    provenance = _as_mapping(manifest.get("code_provenance"))
    evidence = _as_mapping(manifest.get("evidence"))
    admission_report = _as_mapping(manifest.get("admission_report"))
    heldout_raw = _as_mapping(heldout.get("raw"))
    heldout_dev = _as_mapping(heldout_raw.get("development_model"))
    heldout_training = _as_mapping(heldout_dev.get("training_dataset"))
    heldout_corpus = _as_mapping(heldout_raw.get("heldout_corpus"))
    heldout_overall = _as_mapping(heldout_raw.get("overall"))
    heldout_assessment = _as_mapping(
        heldout_raw.get("heldout_assessment")
    )
    heldout_safety = _as_mapping(
        heldout_raw.get("identity_and_truth_safety")
    )
    paired_raw = _as_mapping(paired.get("raw"))
    paired_spec = _as_mapping(paired_raw.get("input_spec"))
    paired_expected = _as_mapping(paired_spec.get("expected_hashes"))
    paired_totals = _as_mapping(paired_raw.get("totals"))
    paired_safety = _as_mapping(
        paired_raw.get("identity_and_truth_safety")
    )
    paired_assessment = _as_mapping(
        paired_raw.get("paired_shadow_assessment")
    )
    external_raw = _as_mapping(external.get("raw"))
    external_consumer = _as_mapping(external.get("consumer"))
    external_candidate = _as_mapping(external_raw.get("candidate"))
    external_model = _as_mapping(external_candidate.get("model"))
    external_implementation = _as_mapping(
        external_candidate.get("implementation")
    )
    external_heldout = _as_mapping(external_candidate.get("heldout"))
    external_paired = _as_mapping(
        external_candidate.get("paired_shadow")
    )
    manifest_heldout = _as_mapping(evidence.get("heldout"))
    manifest_paired = _as_mapping(evidence.get("paired_shadow"))
    manifest_external = _as_mapping(evidence.get("d6_external_audit"))

    source_manifest = _equal_group(
        "source_development_manifest_sha256",
        (
            source.get("manifest_sha256"),
            external_consumer.get("bundle_manifest_sha256"),
            external_model.get("manifest_sha256"),
            heldout_dev.get("bundle_manifest_sha256"),
            paired_expected.get("bundle_manifest_sha256"),
        ),
        context,
    )
    source_weights = _equal_group(
        "source_development_weights_sha256",
        (
            source.get("weights_sha256"),
            actual_hashes.get("bundle_weights"),
            weights.get("sha256"),
            external_consumer.get("bundle_weights_sha256"),
            external_model.get("weights_sha256"),
            heldout_dev.get("weights_sha256"),
            paired_expected.get("bundle_weights_sha256"),
        ),
        context,
    )
    source_checksums = _equal_group(
        "source_development_checksums_sha256",
        (
            source.get("checksums_sha256"),
            external_model.get("checksums_sha256"),
            paired_expected.get("bundle_checksums_sha256"),
        ),
        context,
    )

    heldout_file = _equal_group(
        "heldout_file_sha256",
        (
            actual_hashes.get("heldout_evidence"),
            manifest_heldout.get("sha256"),
            admission_report.get("heldout_report_sha256"),
            external_consumer.get("heldout_report_sha256"),
            external_heldout.get("report_sha256"),
            paired_expected.get("heldout_report_sha256"),
        ),
        context,
    )
    heldout_content = _equal_group(
        "heldout_content_sha256",
        (
            heldout.get("content_sha256"),
            manifest_heldout.get("content_sha256"),
            admission_report.get("heldout_report_content_sha256"),
            external_consumer.get("heldout_report_content_sha256"),
            external_heldout.get("report_content_sha256"),
            paired_expected.get("heldout_report_content_sha256"),
        ),
        context,
    )
    paired_file = _equal_group(
        "paired_shadow_file_sha256",
        (
            actual_hashes.get("paired_shadow_evidence"),
            manifest_paired.get("sha256"),
            admission_report.get("paired_shadow_report_sha256"),
            external_consumer.get("paired_shadow_report_sha256"),
            external_paired.get("report_sha256"),
        ),
        context,
    )
    paired_content = _equal_group(
        "paired_shadow_content_sha256",
        (
            paired.get("content_sha256"),
            manifest_paired.get("content_sha256"),
            admission_report.get("paired_shadow_report_content_sha256"),
            external_consumer.get("paired_shadow_report_content_sha256"),
            external_paired.get("report_content_sha256"),
        ),
        context,
    )
    external_file = _equal_group(
        "d6_external_audit_file_sha256",
        (
            actual_hashes.get("d6_external_audit_evidence"),
            manifest_external.get("sha256"),
            admission_report.get("d6_external_audit_sha256"),
        ),
        context,
    )
    external_content = _equal_group(
        "d6_external_audit_content_sha256",
        (
            external.get("content_sha256"),
            manifest_external.get("content_sha256"),
            admission_report.get("d6_external_audit_content_sha256"),
        ),
        context,
    )

    dataset = _equal_group(
        "dataset_manifest_sha256",
        (
            training.get("dataset_manifest_sha256"),
            admission_report.get("dataset_manifest_sha256"),
            external_consumer.get("dataset_manifest_sha256"),
            heldout_training.get("dataset_manifest_sha256"),
            _as_mapping(external_heldout.get("training_dataset")).get(
                "dataset_manifest_sha256"
            ),
        ),
        context,
    )
    split = _equal_group(
        "split_sha256",
        (
            training.get("split_sha256"),
            admission_report.get("split_sha256"),
            external_consumer.get("split_sha256"),
            heldout_training.get("split_sha256"),
            _as_mapping(external_heldout.get("training_dataset")).get(
                "split_sha256"
            ),
        ),
        context,
    )
    training_set = _equal_group(
        "training_set_sha256",
        (
            training.get("training_set_sha256"),
            admission_report.get("training_set_sha256"),
            external_consumer.get("training_set_sha256"),
            heldout_training.get("training_set_sha256"),
            _as_mapping(external_heldout.get("training_dataset")).get(
                "training_set_sha256"
            ),
        ),
        context,
    )
    if (
        training.get("training_config_sha256")
        != heldout_training.get("training_config_sha256")
    ):
        context.block(
            "training_config_sha256_mismatch",
            (
                f"{training.get('training_config_sha256')}!="
                f"{heldout_training.get('training_config_sha256')}"
            ),
        )

    runtime_sha = _equal_group(
        "runtime_implementation_sha256",
        (
            provenance.get("runtime_implementation_sha256"),
            admission_report.get("implementation_sha256"),
            external_consumer.get("implementation_sha256"),
            external_implementation.get(
                "current_implementation_sha256"
            ),
            external_implementation.get(
                "evidence_implementation_sha256"
            ),
        ),
        context,
    )
    runtime_files = _as_mapping(provenance.get("runtime_source_files"))
    for external_name in ("current_source_files", "evidence_source_files"):
        if runtime_files != _as_mapping(
            external_implementation.get(external_name)
        ):
            context.block(
                f"runtime_source_files_mismatch.{external_name}",
                external_name,
            )
    for source_name, source_map in (
        (
            "heldout",
            _as_mapping(heldout.get("implementation_source_files")),
        ),
        (
            "paired_shadow",
            _as_mapping(paired.get("implementation_source_files")),
        ),
    ):
        for name, digest in source_map.items():
            if name in runtime_files and runtime_files.get(name) != digest:
                context.block(
                    f"runtime_source_files_mismatch.{source_name}.{name}",
                    f"{runtime_files.get(name)}!={digest}",
                )
    if _as_mapping(provenance.get("source_files")) != _as_mapping(
        external_model.get("manifest_source_files")
    ):
        context.block(
            "model_source_files_mismatch",
            "v4 manifest/external audit",
        )
    if provenance.get("implementation_sha256") != external_model.get(
        "manifest_implementation_sha256"
    ):
        context.block(
            "model_implementation_sha256_mismatch",
            "v4 manifest/external audit",
        )

    model_fingerprint = _equal_group(
        "model_fingerprint",
        (
            weights.get("model_fingerprint"),
            admission_report.get("model_fingerprint"),
            external_consumer.get("model_fingerprint"),
            external_model.get("model_fingerprint"),
        ),
        context,
    )

    seed_values = heldout_corpus.get("seed_values")
    seed_count = len(seed_values) if isinstance(seed_values, list) else None
    unseen = _equal_group(
        "unseen_seed_count",
        (
            seed_count,
            paired_totals.get("seed_count"),
            admission_report.get("unseen_seed_count"),
            external_consumer.get("unseen_seed_count"),
            external_heldout.get("unseen_seed_count"),
            external_paired.get("seed_count"),
        ),
        context,
    )
    if seed_values != list(_FORMAL_SEEDS):
        context.block(
            "formal_seed_catalog_mismatch",
            str(seed_values),
        )
    if unseen is not None and unseen != len(_FORMAL_SEEDS):
        context.block(
            "formal_seed_count_mismatch",
            str(unseen),
        )
    episodes = _equal_group(
        "heldout_episode_count",
        (
            heldout_corpus.get("episode_count"),
            heldout_overall.get("episode_count"),
            paired_totals.get("episode_count"),
            admission_report.get("heldout_episode_count"),
            external_consumer.get("heldout_episode_count"),
            external_heldout.get("episode_count"),
            external_paired.get("episode_count"),
        ),
        context,
    )
    if episodes is not None and episodes != _FORMAL_EPISODE_COUNT:
        context.block("formal_episode_count_mismatch", str(episodes))
    cell_gate = _as_mapping(
        heldout_assessment.get("cell_catalog_gate")
    )
    cells = _equal_group(
        "scenario_scale_cell_count",
        (
            heldout_corpus.get("scenario_scale_cell_count"),
            cell_gate.get("actual"),
            paired_totals.get("scenario_scale_cell_count"),
            admission_report.get("scenario_scale_cell_count"),
            external_consumer.get("scenario_scale_cell_count"),
            external_heldout.get("scenario_scale_cell_count"),
            external_paired.get("scenario_scale_cell_count"),
        ),
        context,
    )
    if cells is not None and cells != _FORMAL_CELL_COUNT:
        context.block("formal_cell_count_mismatch", str(cells))

    online_truth = _equal_group(
        "online_truth_feature_count",
        (
            heldout_safety.get("online_truth_feature_count"),
            paired_safety.get("online_truth_feature_count"),
            admission_report.get("online_truth_feature_count"),
            external_consumer.get("online_truth_feature_count"),
            external_heldout.get("online_truth_feature_count"),
            external_paired.get("online_truth_feature_count"),
        ),
        context,
    )
    if online_truth is not None and online_truth != 0:
        context.block("online_truth_feature_use", str(online_truth))
    global_rewrite = _equal_group(
        "global_track_id_rewrite_count",
        (
            paired_safety.get("global_track_id_rewrite_count"),
            admission_report.get("global_track_id_rewrite_count"),
            external_consumer.get("global_track_id_rewrite_count"),
            external_paired.get("global_track_id_rewrite_count"),
        ),
        context,
    )
    if (
        global_rewrite is not None
        and global_rewrite != 0
    ) or heldout_safety.get("global_track_id_created_or_rebound") is not False:
        context.block("global_track_id_rewrite", str(global_rewrite))
    same_camera = _equal_group(
        "same_camera_mutual_exclusion_violation_count",
        (
            paired_safety.get(
                "same_camera_mutual_exclusion_violation_count"
            ),
            admission_report.get(
                "same_camera_mutual_exclusion_violation_count"
            ),
            external_consumer.get(
                "same_camera_mutual_exclusion_violation_count"
            ),
            external_paired.get(
                "same_camera_mutual_exclusion_violation_count"
            ),
        ),
        context,
    )
    if same_camera is not None and same_camera != 0:
        context.block(
            "same_camera_mutual_exclusion_violation",
            str(same_camera),
        )

    formal = _equal_group(
        "formal_evaluation",
        (
            admission_report.get("formal_evaluation"),
            external_consumer.get("formal_evaluation"),
        ),
        context,
    )
    heldout_passed = _equal_group(
        "heldout_passed",
        (
            heldout_assessment.get("passed"),
            admission_report.get("heldout_passed"),
            external_consumer.get("heldout_passed"),
            external_heldout.get("passed"),
        ),
        context,
    )
    paired_passed = _equal_group(
        "paired_shadow_passed",
        (
            paired_assessment.get("passed"),
            admission_report.get("paired_shadow_passed"),
            external_consumer.get("paired_shadow_passed"),
            external_paired.get("passed"),
        ),
        context,
    )
    external_passed = _equal_group(
        "d6_external_audit_passed",
        (
            external_raw.get("audit_passed"),
            external_consumer.get("d6_external_audit_passed"),
            admission_report.get("d6_external_audit_passed"),
        ),
        context,
    )
    for name, value in (
        ("formal_evaluation", formal),
        ("heldout_passed", heldout_passed),
        ("paired_shadow_passed", paired_passed),
        ("d6_external_audit_passed", external_passed),
    ):
        if value is not True:
            context.block(f"admission_gate_not_passed.{name}", str(value))
    if (
        admission_report.get("failure_reasons") != []
        or external_consumer.get("failure_reasons") != []
        or external_raw.get("blocker_codes") != []
    ):
        context.block(
            "admission_failure_reasons_not_empty",
            str(admission_report.get("failure_reasons")),
        )
    if admission_report.get("g1_assist_eligible") is not True:
        context.block(
            "admission_report_not_eligible",
            str(admission_report.get("g1_assist_eligible")),
        )

    expected_report = {
        "schema_version": _D5_ADMISSION_REPORT_SCHEMA,
        "model_fingerprint": model_fingerprint,
        "implementation_sha256": runtime_sha,
        "dataset_manifest_sha256": dataset,
        "split_sha256": split,
        "training_set_sha256": training_set,
        "heldout_report_sha256": heldout_file,
        "heldout_report_content_sha256": heldout_content,
        "paired_shadow_report_sha256": paired_file,
        "paired_shadow_report_content_sha256": paired_content,
        "d6_external_audit_sha256": external_file,
        "d6_external_audit_content_sha256": external_content,
        "formal_evaluation": formal,
        "heldout_passed": heldout_passed,
        "paired_shadow_passed": paired_passed,
        "d6_external_audit_passed": external_passed,
        "unseen_seed_count": unseen,
        "heldout_episode_count": episodes,
        "scenario_scale_cell_count": cells,
        "online_truth_feature_count": online_truth,
        "global_track_id_rewrite_count": global_rewrite,
        "same_camera_mutual_exclusion_violation_count": same_camera,
        "failure_reasons": [],
        "g1_assist_eligible": True,
    }
    if dict(admission_report) != expected_report:
        context.block(
            "admission_report_cross_binding_mismatch",
            "manifest report differs from recomputed evidence",
        )
    return {
        "source_development_manifest_sha256": source_manifest,
        "source_development_weights_sha256": source_weights,
        "source_development_checksums_sha256": source_checksums,
        "heldout_file_sha256": heldout_file,
        "heldout_content_sha256": heldout_content,
        "paired_shadow_file_sha256": paired_file,
        "paired_shadow_content_sha256": paired_content,
        "d6_external_audit_file_sha256": external_file,
        "d6_external_audit_content_sha256": external_content,
        "dataset_manifest_sha256": dataset,
        "split_sha256": split,
        "training_set_sha256": training_set,
        "runtime_implementation_sha256": runtime_sha,
        "model_fingerprint": model_fingerprint,
        "unseen_seed_count": unseen,
        "heldout_episode_count": episodes,
        "scenario_scale_cell_count": cells,
        "online_truth_feature_count": online_truth,
        "global_track_id_rewrite_count": global_rewrite,
        "same_camera_mutual_exclusion_violation_count": same_camera,
        "formal_evaluation": formal,
        "heldout_passed": heldout_passed,
        "paired_shadow_passed": paired_passed,
        "d6_external_audit_passed": external_passed,
        "admission_report_exact_match": (
            dict(admission_report) == expected_report
        ),
    }


def _write_artifact_csv(
    path: Path,
    result: Mapping[str, Any],
) -> None:
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
    with path.open("w", newline="", encoding="utf-8") as stream:
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


def _parse_sha256sums(path: Path) -> tuple[dict[str, str], list[str]]:
    result: dict[str, str] = {}
    ordered: list[str] = []
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines:
        raise ValueError("SHA256SUMS is empty")
    for line_number, line in enumerate(lines, start=1):
        parts = line.split("  ")
        if len(parts) != 2 or not _SHA256_RE.fullmatch(parts[0]):
            raise ValueError(f"invalid SHA256SUMS line {line_number}")
        name = parts[1]
        relative = Path(name)
        if (
            not name
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or relative.as_posix() != name
            or name in result
        ):
            raise ValueError(f"invalid SHA256SUMS path {line_number}")
        result[name] = parts[0]
        ordered.append(name)
    return result, ordered


def _equal_group(
    name: str,
    values: Sequence[Any],
    context: _AuditContext,
) -> Any:
    if any(value is None for value in values):
        context.block(
            f"cross_binding_unavailable.{name}",
            repr(list(values)),
        )
        return None
    first = values[0]
    if any(value != first for value in values[1:]):
        context.block(
            f"cross_binding_mismatch.{name}",
            repr(list(values)),
        )
        return None
    return first


def _strict_mapping(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        context.block(blocker_code, field)
        return {}
    return value


def _strict_sha_mapping(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> dict[str, str]:
    mapping = _strict_mapping(value, context, blocker_code, field)
    result: dict[str, str] = {}
    for name, digest in mapping.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or not _SHA256_RE.fullmatch(digest)
        ):
            context.block(blocker_code, f"{field}.{name}")
            continue
        result[name] = digest
    return result


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


def _require_sha(
    value: Any,
    context: _AuditContext,
    blocker_code: str,
    field: str,
) -> str | None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        context.block(blocker_code, field)
        return None
    return value


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _availability(value: Any) -> dict[str, Any]:
    return {
        "available": value is not None,
        "reason": None if value is not None else "source_evidence_unavailable",
    }


def _paths_overlap(left: Path, right: Path) -> bool:
    return _is_relative_to(left, right) or _is_relative_to(right, left)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _safe_child(root: Path, relative: str) -> Path:
    path = root / relative
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise D5G1PostAssemblyAuditError(
            "input_path_outside_repository",
            relative,
        ) from exc
    return path


def _first_symlink_component(path: Path, root: Path) -> Path | None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise D5G1PostAssemblyAuditError(
            "input_path_outside_repository",
            str(path),
        ) from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return current
    return None


def _is_regular_file_without_symlink(path: Path, root: Path) -> bool:
    return _first_symlink_component(path, root) is None and path.is_file()


def _audit_bundle_tree(
    bundle_root: Path,
    repository_root: Path,
    context: _AuditContext,
) -> dict[str, Any]:
    expected_files = set(_EXPECTED_BUNDLE_LAYOUT.values())
    expected_directories = set(_EXPECTED_BUNDLE_DIRECTORIES)
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    observed_symlinks: set[str] = set()
    observed_special_entries: set[str] = set()

    root_symlink = _first_symlink_component(bundle_root, repository_root)
    if root_symlink is not None:
        relative = str(root_symlink.relative_to(repository_root))
        observed_symlinks.add(relative)
        context.block("bundle_tree_symlink", relative)
    elif not bundle_root.is_dir():
        context.block(
            "bundle_tree_unavailable",
            str(bundle_root.relative_to(repository_root)),
        )
    else:
        pending = [bundle_root]
        while pending:
            current = pending.pop()
            try:
                entries = sorted(
                    os.scandir(current),
                    key=lambda entry: entry.name,
                )
            except OSError as exc:
                context.block(
                    "bundle_tree_unavailable",
                    f"{current}:{exc}",
                )
                continue
            for entry in entries:
                entry_path = Path(entry.path)
                relative = entry_path.relative_to(bundle_root).as_posix()
                if entry.is_symlink():
                    observed_symlinks.add(relative)
                    context.block("bundle_tree_symlink", relative)
                elif entry.is_dir(follow_symlinks=False):
                    observed_directories.add(relative)
                    pending.append(entry_path)
                elif entry.is_file(follow_symlinks=False):
                    observed_files.add(relative)
                else:
                    observed_special_entries.add(relative)
                    context.block("bundle_tree_special_entry", relative)

    for relative in sorted(expected_files - observed_files):
        context.block("bundle_tree_missing_entry", relative)
    for relative in sorted(expected_directories - observed_directories):
        context.block("bundle_tree_missing_entry", relative)
    for relative in sorted(observed_files - expected_files):
        context.block("bundle_tree_extra_entry", relative)
    for relative in sorted(observed_directories - expected_directories):
        context.block("bundle_tree_extra_entry", relative)

    exact = (
        observed_files == expected_files
        and observed_directories == expected_directories
        and not observed_symlinks
        and not observed_special_entries
    )
    return {
        "expected_files": sorted(expected_files),
        "observed_files": sorted(observed_files),
        "expected_directories": sorted(expected_directories),
        "observed_directories": sorted(observed_directories),
        "observed_symlinks": sorted(observed_symlinks),
        "observed_special_entries": sorted(observed_special_entries),
        "exact": exact,
    }


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
    "D5_G1_POST_ASSEMBLY_AUDIT_CONSUMER_SCHEMA_VERSION",
    "D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION",
    "D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION",
    "D5_G1_POST_ASSEMBLY_AUDIT_SCHEMA_VERSION",
    "D5G1PostAssemblyAuditArtifact",
    "D5G1PostAssemblyAuditError",
    "D5G1PostAssemblyAuditInputs",
    "audit_d5_g1_post_assembly_bundle",
    "load_d5_g1_post_assembly_audit_inputs",
    "render_d5_g1_post_assembly_audit_markdown",
    "write_d5_g1_post_assembly_audit_report",
]
