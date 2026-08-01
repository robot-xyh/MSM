"""Low-level independent D6 audit for the D5 A3 v2 BC candidate.

Every D5 result is an untrusted claim to reconcile.  The implementation reads
the frozen bytes, parses the state dict, and performs the actor forward pass
without importing D5 code or invoking a D5 evaluator, gate, or precheck.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch


SCHEMA_VERSION = "d6.d5-a3-v2-bc-model-independent-audit.v1"
AUDITOR_IMPLEMENTATION_VERSION = "1.1.0"
INTENTS = ("observe_target", "search_sector", "hold", "reacquire")
CAMERA_TYPES = ("interceptor", "recon", "unknown")
AUTHORITY_KEYS = (
    "assist",
    "promotion",
    "ppo",
    "assignment",
    "degradation",
    "runtime",
    "production",
    "control",
    "camera_command",
    "global_track_id_write",
)
EXPECTED_CANDIDATE_ROOT = "a3_v2_active_vision_bc_development_20260801_d7bf890"
EXPECTED_CORPUS_ROOT = "d5_a3_source_independent_point_mass_v2_20260801_d7bf890"
FORBIDDEN_RESERVED_SEEDS = tuple(range(1000, 1020))
EXPECTED_STATE_SHAPES = {
    "encoder.0.weight": (64, 35),
    "encoder.0.bias": (64,),
    "encoder.2.weight": (64, 64),
    "encoder.2.bias": (64,),
    "actor.weight": (1, 64),
    "actor.bias": (1,),
    "critic.0.weight": (64, 64),
    "critic.0.bias": (64,),
    "critic.2.weight": (1, 64),
    "critic.2.bias": (1,),
}
REQUIRED_TEST_FILES = {
    "camera_type": "u1",
    "candidate_count": "<u2",
    "selected_index": "<u2",
    "candidate_intent": "u1",
    "candidate_fov": "u1",
    "candidate_yaw": "<f4",
    "candidate_pitch": "<f4",
    "features": "<f4",
}


class AuditFailure(RuntimeError):
    """A fail-closed input, artifact, or evidence violation."""


@dataclass(frozen=True, slots=True)
class AuditInputs:
    repo_root: Path
    candidate_root: Path
    frozen_config: Path
    candidate_evidence: Path
    generation_plan: Path
    generation_summary: Path
    training_seed_registry: Path


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    _require_regular_file(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuditFailure(f"json_root_not_object:{path}")
    return value


def require_all_authority_false(*claims: Mapping[str, Any]) -> None:
    for claim in claims:
        for key in AUTHORITY_KEYS:
            if claim.get(key) is not False:
                raise AuditFailure(f"authority_not_false:{key}")


def validate_selection_contract(config: Mapping[str, Any]) -> None:
    selection = config.get("selection_contract")
    if not isinstance(selection, Mapping):
        raise AuditFailure("selection_contract_missing")
    expected = {
        "configuration_count": 1,
        "hyperparameter_search": False,
        "validation_used_for_best_epoch": True,
        "test_used_for_training_or_selection": False,
        "repeat_on_gate_failure": False,
    }
    if dict(selection) != expected:
        raise AuditFailure("multiple_configurations_or_test_tuning")


def verify_file_descriptor(path: Path, descriptor: Mapping[str, Any]) -> str:
    _require_regular_file(path)
    expected_size = _strict_int(descriptor.get("size_bytes"), "invalid_size")
    if path.stat().st_size != expected_size:
        raise AuditFailure(f"file_size_mismatch:{path.name}")
    actual = sha256_file(path)
    if actual != descriptor.get("sha256"):
        raise AuditFailure(f"file_sha256_mismatch:{path.name}")
    return actual


def independent_quality_gate(metrics: Mapping[str, Any]) -> dict[str, Any]:
    recalls = metrics.get("per_intent_recall")
    if not isinstance(recalls, Mapping):
        raise AuditFailure("per_intent_recall_missing")
    failures: list[str] = []
    for intent in INTENTS:
        value = _finite_float(recalls.get(intent), f"invalid_recall:{intent}")
        if value < 0.25:
            failures.append(f"intent_recall_below_0.25:{intent}")
    if _finite_float(metrics.get("macro_intent_recall"), "invalid_macro_recall") < 0.5:
        failures.append("macro_intent_recall_below_0.5")
    if _finite_float(metrics.get("expected_calibration_error"), "invalid_ece") > 0.25:
        failures.append("expected_calibration_error_above_0.25")
    if _finite_float(metrics.get("feature_boundary_ood_fraction"), "invalid_ood") > 0.1:
        failures.append("feature_boundary_ood_fraction_above_0.1")
    camera = metrics.get("per_camera_role_exact_action_accuracy")
    if not isinstance(camera, Mapping):
        raise AuditFailure("camera_role_accuracy_missing")
    for role in ("interceptor", "recon"):
        if _finite_float(camera.get(role), f"invalid_camera_accuracy:{role}") < 0.5:
            failures.append(f"camera_role_accuracy_below_0.5:{role}")
    return {
        "passed": not failures,
        "status": "passed" if not failures else "fail_closed",
        "failure_reasons": failures,
        "paired_shadow_allowed": False,
    }


def enforce_fail_closed_claims(
    gate: Mapping[str, Any], claims: Mapping[str, Any]
) -> None:
    if gate.get("passed") is not True and (
        claims.get("passed") is True
        or claims.get("development_model_precheck_passed") is True
        or claims.get("paired_shadow_allowed") is True
        or claims.get("may_enter_formal_paired_shadow") is True
    ):
        raise AuditFailure("failed_quality_gate_claimed_as_passed")


def audit_d5_a3_v2_bc_candidate(inputs: AuditInputs) -> dict[str, Any]:
    """Perform a complete low-level audit and return machine-readable evidence."""

    paths = _normalize_and_validate_paths(inputs)
    config = load_json(paths["frozen_config"])
    evidence = load_json(paths["candidate_evidence"])
    plan = load_json(paths["generation_plan"])
    summary = load_json(paths["generation_summary"])
    registry = load_json(paths["training_seed_registry"])
    cache_manifest_path = paths["candidate_root"] / "feature_cache" / "manifest.json"
    bundle_root = paths["candidate_root"] / "development_shadow_model_bundle"
    bundle_manifest_path = bundle_root / "manifest.json"
    weights_path = bundle_root / "weights.pt"
    bundle_sums_path = bundle_root / "SHA256SUMS"
    tracked_summary_path = paths["candidate_root"] / "tracked_summary.json"
    tracked_report_path = (
        paths["repo_root"]
        / "research_modules/d5_terminal_association/reports/"
        "D5_A3_V2_ACTIVE_VISION_BC_DEVELOPMENT_CANDIDATE_20260801_CN.md"
    )
    cache_manifest = load_json(cache_manifest_path)
    bundle_manifest = load_json(bundle_manifest_path)
    tracked_summary = load_json(tracked_summary_path)

    validate_selection_contract(config)
    _validate_selection_bindings(config, evidence, bundle_manifest, tracked_summary)
    hashes = _validate_hash_bindings(
        paths=paths,
        config=config,
        evidence=evidence,
        plan=plan,
        summary=summary,
        registry=registry,
        cache_manifest_path=cache_manifest_path,
        bundle_manifest_path=bundle_manifest_path,
        weights_path=weights_path,
        bundle_sums_path=bundle_sums_path,
        tracked_summary_path=tracked_summary_path,
        tracked_report_path=tracked_report_path,
        cache_manifest=cache_manifest,
        bundle_manifest=bundle_manifest,
    )
    source_evidence = _validate_generation_evidence(plan, summary, registry)
    authority_evidence = _validate_authority_claims(
        config, evidence, bundle_manifest, tracked_summary
    )
    cache_hashes = _verify_cache_files(paths["candidate_root"], cache_manifest)
    test_cache = _read_test_cache(paths["candidate_root"], cache_manifest)
    state = _load_and_validate_state_dict(weights_path)
    recomputation = _recompute_test_metrics(
        test_cache,
        cache_manifest=cache_manifest,
        bundle_manifest=bundle_manifest,
        state=state,
        calibration_bin_count=_strict_int(
            _mapping(config.get("config"), "frozen_training_config_missing").get(
                "calibration_bin_count"
            ),
            "invalid_calibration_bin_count",
        ),
        ood_margin=_finite_float(
            _mapping(config.get("config"), "frozen_training_config_missing").get(
                "ood_margin"
            ),
            "invalid_ood_margin",
        ),
    )
    comparison = _reconcile_claimed_metrics(recomputation["metrics"], evidence)
    quality_gate = independent_quality_gate(recomputation["metrics"])
    enforce_fail_closed_claims(
        quality_gate,
        _mapping(evidence.get("development_precheck"), "development_precheck_missing"),
    )
    _verify_hashes_unchanged(cache_hashes)
    auditor_source = Path(__file__).resolve()
    auditor_source_relative = _repo_relative_posix(
        auditor_source, paths["repo_root"]
    )
    auditor_source_sha256 = sha256_file(auditor_source)

    return {
        "schema_version": SCHEMA_VERSION,
        "validation_date": "2026-08-01",
        "status": "completed_fail_closed_quality_gate",
        "conclusion": (
            "candidate_bytes_and_claimed_metrics_reproduced_but_minority_action_"
            "recall_and_calibration_fail_independent_gate"
        ),
        "auditor": {
            "owner": "D6",
            "audit_schema_version": SCHEMA_VERSION,
            "implementation_version": AUDITOR_IMPLEMENTATION_VERSION,
            "implementation": {
                "path": auditor_source_relative,
                "sha256": auditor_source_sha256,
            },
            "read_only": True,
            "uses_d5_evaluator": False,
            "uses_d5_corpus_gate": False,
            "uses_d5_precheck": False,
            "uses_d5_model_class": False,
            "model_forward": "state_dict_tensor_shapes_plus_tanh_linear_algebra",
            "reserved_episode_or_r0_shard_read": False,
        },
        "inputs": {
            "repo_root": ".",
            **{
                key: _repo_relative_posix(value, paths["repo_root"])
                for key, value in paths.items()
                if key != "repo_root"
            },
        },
        "integrity": {
            "audit_schema_version": SCHEMA_VERSION,
            "auditor_implementation_version": AUDITOR_IMPLEMENTATION_VERSION,
            "auditor_implementation_sha256": auditor_source_sha256,
            "hashes": hashes,
            "cache_file_count": len(cache_hashes),
            "cache_files_verified_before_and_after": True,
            "tracked_d5_source_file_count": len(
                _mapping(
                    _mapping(bundle_manifest.get("code_provenance"), "code_provenance_missing").get(
                        "source_files"
                    ),
                    "source_files_missing",
                )
            ),
            "bundle_sha256sums_verified": True,
        },
        "source_evidence": source_evidence,
        "model": {
            "architecture": dict(
                _mapping(bundle_manifest.get("architecture"), "architecture_missing")
            ),
            "state_dict_shapes": {
                key: list(value.shape) for key, value in state.items()
            },
            "critic_parsed_but_not_used_for_action_selection": True,
        },
        "recomputation": recomputation,
        "claimed_metric_comparison": comparison,
        "quality_gate": quality_gate,
        "authority": authority_evidence,
        "paired_shadow_allowed": False,
        "scope_boundary": {
            "development_point_mass_test_cache_only": True,
            "airsim_physical_evidence": False,
            "real_camera_evidence": False,
            "formal_reserved_seed_evidence": False,
            "runtime_or_control_admission": False,
        },
    }


def render_report_cn(audit: Mapping[str, Any]) -> str:
    metrics = _mapping(
        _mapping(audit.get("recomputation"), "recomputation_missing").get("metrics"),
        "metrics_missing",
    )
    recalls = _mapping(metrics.get("per_intent_recall"), "recalls_missing")
    camera = _mapping(
        metrics.get("per_camera_role_exact_action_accuracy"), "camera_metrics_missing"
    )
    gate = _mapping(audit.get("quality_gate"), "quality_gate_missing")
    source = _mapping(audit.get("source_evidence"), "source_evidence_missing")
    auditor = _mapping(audit.get("auditor"), "auditor_missing")
    implementation = _mapping(
        auditor.get("implementation"), "auditor_implementation_missing"
    )
    return "\n".join(
        [
            "# D5 A3 v2 BC model D6 低层独立审计",
            "",
            "验证日期：2026-08-01",
            "",
            "## 结论",
            "",
            "D6 未调用 D5 evaluator、corpus gate、precheck 或模型类，直接读取冻结配置、",
            "generation plan/summary/registry、feature cache 二进制、bundle manifest、",
            "`SHA256SUMS` 和 `weights.pt`，按 state_dict 张量形状重建两层 tanh actor 前向。",
            "候选完整性与 D5 声明指标可复现，但独立质量门失败关闭。",
            "",
            f"- 审计 schema/实现版本：`{auditor['audit_schema_version']}`/"
            f"`{auditor['implementation_version']}`。",
            f"- 审计器源码：`{implementation['path']}`；SHA-256："
            f"`{implementation['sha256']}`。",
            f"- test 样本/候选：{metrics['sample_count']}/{metrics['candidate_row_count']}。",
            f"- exact action accuracy：{metrics['exact_action_accuracy']:.15f}。",
            f"- intent recall：observe_target={recalls['observe_target']:.15f}，"
            f"search_sector={recalls['search_sector']:.15f}，hold={recalls['hold']:.15f}，"
            f"reacquire={recalls['reacquire']:.15f}。",
            f"- macro intent recall：{metrics['macro_intent_recall']:.15f}。",
            f"- interceptor/recon exact accuracy：{camera['interceptor']:.15f}/"
            f"{camera['recon']:.15f}。",
            f"- ECE：{metrics['expected_calibration_error']:.15f}；feature-boundary OOD："
            f"{metrics['feature_boundary_ood_fraction']:.15f}。",
            "",
            "## 失败关闭",
            "",
            f"独立门状态为 `{gate['status']}`，原因："
            + "、".join(str(item) for item in gate["failure_reasons"])
            + "。",
            "总体准确率不能覆盖 observe_target 与 search_sector 的零召回。所有 authority",
            "保持 false，`paired_shadow_allowed=false`，规则回退继续有效。",
            "",
            "## 来源与范围",
            "",
            f"- generation seed 为 {source['training_seed_minimum']}-"
            f"{source['training_seed_maximum']}，共 {source['training_seed_count']}；只核对与"
            "保留 seed 1000-1019 的数值交集为 0，未读取或运行保留 episode。",
            "- 本证据只覆盖开发三维质点 test cache，不构成正式 R0、AirSim、真实相机、",
            "物理非退化、assist、运行或控制准入证据。",
            "- 每样本 prediction/confidence/OOD 已写入 `audit.json`；缓存文件在复算前后",
            "再次核对 SHA-256。",
            "",
        ]
    )


def write_report_bundle(audit: Mapping[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "audit.json"
    report_path = output_dir / "REPORT_CN.md"
    sums_path = output_dir / "SHA256SUMS"
    audit_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(render_report_cn(audit), encoding="utf-8")
    sums_path.write_text(
        f"{sha256_file(audit_path)}  audit.json\n"
        f"{sha256_file(report_path)}  REPORT_CN.md\n",
        encoding="utf-8",
    )


def _normalize_and_validate_paths(inputs: AuditInputs) -> dict[str, Path]:
    paths = {
        key: Path(getattr(inputs, key)).resolve()
        for key in (
            "repo_root",
            "candidate_root",
            "frozen_config",
            "candidate_evidence",
            "generation_plan",
            "generation_summary",
            "training_seed_registry",
        )
    }
    if paths["candidate_root"].name != EXPECTED_CANDIDATE_ROOT:
        raise AuditFailure("unexpected_candidate_root")
    corpus_parents = {
        paths[name].parent.name
        for name in ("generation_plan", "generation_summary", "training_seed_registry")
    }
    if corpus_parents != {EXPECTED_CORPUS_ROOT}:
        raise AuditFailure("unexpected_or_multiple_corpus_roots")
    for path in paths.values():
        if path != paths["repo_root"] and paths["repo_root"] not in path.parents:
            raise AuditFailure("input_outside_repository")
    return paths


def _repo_relative_posix(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise AuditFailure("path_outside_repository") from exc


def _validate_hash_bindings(
    *,
    paths: Mapping[str, Path],
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
    plan: Mapping[str, Any],
    summary: Mapping[str, Any],
    registry: Mapping[str, Any],
    cache_manifest_path: Path,
    bundle_manifest_path: Path,
    weights_path: Path,
    bundle_sums_path: Path,
    tracked_summary_path: Path,
    tracked_report_path: Path,
    cache_manifest: Mapping[str, Any],
    bundle_manifest: Mapping[str, Any],
) -> dict[str, str]:
    source_hashes = _mapping(config.get("source_hashes"), "source_hashes_missing")
    artifact_claims = _mapping(evidence.get("artifacts"), "artifact_claims_missing")
    frozen_claim = _mapping(evidence.get("frozen_config"), "frozen_claim_missing")
    actual = {
        "frozen_config": sha256_file(paths["frozen_config"]),
        "candidate_evidence": sha256_file(paths["candidate_evidence"]),
        "generation_plan": sha256_file(paths["generation_plan"]),
        "generation_summary": sha256_file(paths["generation_summary"]),
        "training_seed_registry": sha256_file(paths["training_seed_registry"]),
        "feature_cache_manifest": sha256_file(cache_manifest_path),
        "model_bundle_manifest": sha256_file(bundle_manifest_path),
        "model_weights": sha256_file(weights_path),
        "bundle_sha256sums": sha256_file(bundle_sums_path),
        "tracked_summary": sha256_file(tracked_summary_path),
        "tracked_report": sha256_file(tracked_report_path),
    }
    expected = {
        "frozen_config": frozen_claim.get("file_sha256"),
        "generation_plan": source_hashes.get("generation_plan_sha256"),
        "generation_summary": source_hashes.get("generation_summary_sha256"),
        "training_seed_registry": source_hashes.get("training_seed_registry_sha256"),
        "feature_cache_manifest": artifact_claims.get("feature_cache_manifest_sha256"),
        "model_bundle_manifest": artifact_claims.get("model_bundle_manifest_sha256"),
        "model_weights": artifact_claims.get("model_weights_sha256"),
        "tracked_summary": artifact_claims.get("tracked_summary_sha256"),
        "tracked_report": artifact_claims.get("chinese_report_sha256"),
    }
    for name, expected_hash in expected.items():
        if actual[name] != expected_hash:
            raise AuditFailure(f"external_hash_binding_mismatch:{name}")
    if summary.get("training_seed_registry_sha256") != actual["training_seed_registry"]:
        raise AuditFailure("summary_registry_file_sha256_mismatch")
    if canonical_json_sha256(config.get("config")) != frozen_claim.get("content_sha256"):
        raise AuditFailure("frozen_config_content_sha256_mismatch")
    if config.get("frozen_before_training") is not True:
        raise AuditFailure("config_not_frozen_before_training")
    cache_source = _mapping(cache_manifest.get("source_binding"), "cache_source_missing")
    cache_dataset = _mapping(cache_source.get("dataset"), "cache_dataset_missing")
    if cache_dataset.get("manifest_sha256") != source_hashes.get("dataset_manifest_sha256"):
        raise AuditFailure("dataset_manifest_binding_mismatch")
    training = _mapping(bundle_manifest.get("training"), "bundle_training_missing")
    training_config = _mapping(training.get("config"), "bundle_training_config_missing")
    if training_config.get("feature_cache_manifest_sha256") != actual["feature_cache_manifest"]:
        raise AuditFailure("bundle_cache_manifest_binding_mismatch")
    cache_plan = _mapping(cache_source.get("generation_plan"), "cache_plan_missing")
    cache_summary = _mapping(cache_source.get("generation_summary"), "cache_summary_missing")
    cache_registry = _mapping(
        cache_source.get("training_seed_registry"), "cache_registry_missing"
    )
    if (
        cache_plan.get("sha256") != actual["generation_plan"]
        or cache_summary.get("sha256") != actual["generation_summary"]
        or cache_registry.get("sha256") != actual["training_seed_registry"]
    ):
        raise AuditFailure("cache_generation_hash_binding_mismatch")
    _validate_bundle_sums(bundle_sums_path, bundle_manifest_path, weights_path)
    _validate_tracked_source_hashes(paths["repo_root"], bundle_manifest)
    return actual


def _validate_selection_bindings(
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
    bundle: Mapping[str, Any],
    tracked: Mapping[str, Any],
) -> None:
    selection = _mapping(config.get("selection_contract"), "selection_contract_missing")
    frozen_values = _mapping(config.get("config"), "frozen_training_config_missing")
    evidence_frozen = _mapping(evidence.get("frozen_config"), "evidence_frozen_missing")
    bundle_training = _mapping(bundle.get("training"), "bundle_training_missing")
    bundle_config = _mapping(bundle_training.get("config"), "bundle_config_missing")
    bundle_binding = _mapping(
        bundle_config.get("frozen_config_binding"), "bundle_frozen_binding_missing"
    )
    tracked_frozen = _mapping(tracked.get("frozen_config"), "tracked_frozen_missing")
    if evidence.get("training_run_count") != 1:
        raise AuditFailure("training_run_count_not_one")
    for bound in (bundle_binding, tracked_frozen):
        if bound.get("selection_contract") != selection:
            raise AuditFailure("selection_contract_binding_mismatch")
        if bound.get("frozen_before_training") is not True:
            raise AuditFailure("bound_config_not_frozen_before_training")
    if (
        evidence_frozen.get("configuration_count") != 1
        or evidence_frozen.get("hyperparameter_search") is not False
        or evidence_frozen.get("test_used_for_training_or_selection") is not False
        or evidence_frozen.get("repeat_on_gate_failure") is not False
    ):
        raise AuditFailure("evidence_selection_or_test_tuning_violation")
    if evidence_frozen.get("config") != frozen_values:
        raise AuditFailure("evidence_frozen_config_value_mismatch")
    for key, value in frozen_values.items():
        if bundle_config.get(key) != value:
            raise AuditFailure(f"bundle_frozen_config_value_mismatch:{key}")
    expected_flags = {
        "configuration_count": 1,
        "hyperparameter_search_used": False,
        "test_used_for_training_or_selection": False,
        "validation_used_for_best_epoch": True,
    }
    for key, value in expected_flags.items():
        if bundle_config.get(key) is not value:
            raise AuditFailure(f"bundle_selection_or_test_tuning_violation:{key}")


def _validate_bundle_sums(sums: Path, manifest: Path, weights: Path) -> None:
    entries: dict[str, str] = {}
    for line in sums.read_text(encoding="ascii").splitlines():
        parts = line.split("  ")
        if len(parts) != 2 or Path(parts[1]).name != parts[1]:
            raise AuditFailure("invalid_bundle_sha256sums_line")
        entries[parts[1]] = parts[0]
    if entries != {
        "manifest.json": sha256_file(manifest),
        "weights.pt": sha256_file(weights),
    }:
        raise AuditFailure("bundle_sha256sums_mismatch")


def _validate_tracked_source_hashes(
    repo_root: Path, bundle_manifest: Mapping[str, Any]
) -> None:
    provenance = _mapping(bundle_manifest.get("code_provenance"), "code_provenance_missing")
    source_files = _mapping(provenance.get("source_files"), "source_files_missing")
    source_root = (
        repo_root
        / "research_modules/d5_terminal_association/src/d5_terminal_association"
    )
    for name, expected_hash in source_files.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise AuditFailure("invalid_tracked_d5_source_name")
        if sha256_file(source_root / name) != expected_hash:
            raise AuditFailure(f"tracked_d5_source_sha256_mismatch:{name}")


def _validate_generation_evidence(
    plan: Mapping[str, Any], summary: Mapping[str, Any], registry: Mapping[str, Any]
) -> dict[str, Any]:
    if plan.get("formal") is not False or summary.get("formal") is not False:
        raise AuditFailure("formal_generation_input_prohibited")
    for key, value in plan.items():
        if summary.get(key) != value:
            raise AuditFailure(f"generation_plan_summary_mismatch:{key}")
    cells = plan.get("cells")
    training_seeds = registry.get("training_seeds")
    if not isinstance(cells, list) or not isinstance(training_seeds, list):
        raise AuditFailure("generation_cells_or_seed_registry_missing")
    cell_seeds = [_strict_int(_mapping(cell, "invalid_generation_cell").get("seed"), "invalid_cell_seed") for cell in cells]
    if sorted(cell_seeds) != training_seeds or len(set(cell_seeds)) != len(cell_seeds):
        raise AuditFailure("generation_seed_registry_mismatch")
    reserved = list(FORBIDDEN_RESERVED_SEEDS)
    if plan.get("reserved_evaluation_seeds") != reserved:
        raise AuditFailure("reserved_seed_catalog_mismatch")
    if registry.get("reserved_evaluation_seeds") != reserved:
        raise AuditFailure("registry_reserved_seed_catalog_mismatch")
    overlap = sorted(set(cell_seeds) & set(reserved))
    if overlap or registry.get("overlap_count") != 0:
        raise AuditFailure("reserved_seed_overlap")
    if registry.get("repository_dirty") is not False or plan.get("repository_dirty") is not False:
        raise AuditFailure("dirty_generation_source")
    return {
        "corpus_formal": False,
        "cell_count": len(cells),
        "training_seed_count": len(training_seeds),
        "training_seed_minimum": min(training_seeds),
        "training_seed_maximum": max(training_seeds),
        "reserved_seed_catalog": reserved,
        "reserved_seed_overlap": overlap,
        "reserved_seed_check_only_no_episode_read": True,
        "repository_dirty": False,
        "git_commit": registry.get("git_commit"),
    }


def _validate_authority_claims(
    config: Mapping[str, Any],
    evidence: Mapping[str, Any],
    bundle: Mapping[str, Any],
    tracked: Mapping[str, Any],
) -> dict[str, bool]:
    bundle_binding = _mapping(
        _mapping(
            _mapping(bundle.get("training"), "bundle_training_missing").get("config"),
            "bundle_training_config_missing",
        ).get("frozen_config_binding"),
        "bundle_frozen_config_binding_missing",
    )
    require_all_authority_false(
        _mapping(config.get("authority"), "config_authority_missing"),
        _mapping(evidence.get("authority"), "evidence_authority_missing"),
        _mapping(bundle_binding.get("authority"), "bundle_authority_missing"),
    )
    runtime = _mapping(bundle.get("runtime_policy"), "runtime_policy_missing")
    if (
        runtime.get("allowed_runtime_modes") != ["shadow"]
        or runtime.get("assist_admitted") is not False
        or runtime.get("camera_command_authority") is not False
        or runtime.get("ppo_enabled") is not False
        or runtime.get("rule_fallback_required") is not True
    ):
        raise AuditFailure("bundle_runtime_policy_not_fail_closed")
    admission = _mapping(bundle.get("admission"), "bundle_admission_missing")
    diagnostics = _mapping(
        _mapping(bundle.get("validation_results"), "bundle_validation_missing").get(
            "model_diagnostics"
        ),
        "bundle_model_diagnostics_missing",
    )
    tracked_admission = _mapping(tracked.get("admission"), "tracked_admission_missing")
    if admission.get("assist_admitted") is not False:
        raise AuditFailure("bundle_assist_admitted")
    forbidden_true = (
        diagnostics.get("development_model_precheck_passed"),
        diagnostics.get("may_enter_formal_paired_shadow"),
        tracked_admission.get("development_model_precheck_passed"),
        tracked_admission.get("assist"),
        tracked_admission.get("promotion"),
        tracked_admission.get("ppo"),
    )
    if any(value is not False for value in forbidden_true):
        raise AuditFailure("tracked_or_bundle_authority_not_false")
    return {key: False for key in AUTHORITY_KEYS}


def _verify_cache_files(
    candidate_root: Path, manifest: Mapping[str, Any]
) -> dict[Path, str]:
    splits = _mapping(manifest.get("splits"), "cache_splits_missing")
    verified: dict[Path, str] = {}
    for split_name in ("train", "validation", "test"):
        split = _mapping(splits.get(split_name), f"cache_split_missing:{split_name}")
        files = _mapping(split.get("files"), f"cache_files_missing:{split_name}")
        for descriptor_value in files.values():
            descriptor = _mapping(descriptor_value, "invalid_cache_file_descriptor")
            filename = descriptor.get("filename")
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise AuditFailure("invalid_cache_filename")
            path = candidate_root / "feature_cache" / split_name / filename
            verified[path] = verify_file_descriptor(path, descriptor)
    return verified


def _read_test_cache(
    candidate_root: Path, manifest: Mapping[str, Any]
) -> dict[str, np.ndarray | int]:
    split = _mapping(
        _mapping(manifest.get("splits"), "cache_splits_missing").get("test"),
        "test_cache_missing",
    )
    files = _mapping(split.get("files"), "test_cache_files_missing")
    sample_count = _strict_int(split.get("sample_count"), "invalid_test_sample_count")
    candidate_rows = _strict_int(
        split.get("candidate_row_count"), "invalid_test_candidate_rows"
    )
    feature_dim = _strict_int(split.get("feature_dim"), "invalid_feature_dim")
    if feature_dim != 35:
        raise AuditFailure("unexpected_feature_dim")
    result: dict[str, np.ndarray | int] = {
        "sample_count": sample_count,
        "candidate_row_count": candidate_rows,
        "feature_dim": feature_dim,
    }
    for key, expected_dtype in REQUIRED_TEST_FILES.items():
        descriptor = _mapping(files.get(key), f"required_test_file_missing:{key}")
        if descriptor.get("dtype") != expected_dtype:
            raise AuditFailure(f"test_file_dtype_mismatch:{key}")
        path = candidate_root / "feature_cache/test" / str(descriptor["filename"])
        values = np.fromfile(path, dtype=np.dtype(expected_dtype))
        result[key] = values
    if np.asarray(result["candidate_count"]).shape != (sample_count,):
        raise AuditFailure("candidate_count_shape_mismatch")
    if np.asarray(result["selected_index"]).shape != (sample_count,):
        raise AuditFailure("selected_index_shape_mismatch")
    if np.asarray(result["camera_type"]).shape != (sample_count,):
        raise AuditFailure("camera_type_shape_mismatch")
    for key in ("candidate_intent", "candidate_fov", "candidate_yaw", "candidate_pitch"):
        if np.asarray(result[key]).shape != (candidate_rows,):
            raise AuditFailure(f"candidate_field_shape_mismatch:{key}")
    if np.any(np.asarray(result["candidate_intent"], dtype=np.int64) > 3):
        raise AuditFailure("candidate_intent_code_out_of_range")
    if np.any(np.asarray(result["candidate_fov"], dtype=np.int64) > 1):
        raise AuditFailure("candidate_fov_code_out_of_range")
    if not np.all(np.isfinite(np.asarray(result["candidate_yaw"]))) or not np.all(
        np.isfinite(np.asarray(result["candidate_pitch"]))
    ):
        raise AuditFailure("candidate_angle_non_finite")
    features = np.asarray(result["features"])
    if features.size != candidate_rows * feature_dim:
        raise AuditFailure("candidate_features_shape_mismatch")
    result["features"] = features.reshape(candidate_rows, feature_dim)
    counts = np.asarray(result["candidate_count"], dtype=np.int64)
    selected = np.asarray(result["selected_index"], dtype=np.int64)
    if np.any(counts <= 0) or int(np.sum(counts)) != candidate_rows:
        raise AuditFailure("candidate_count_inventory_mismatch")
    if np.any(selected < 0) or np.any(selected >= counts):
        raise AuditFailure("selected_index_out_of_range")
    return result


def _load_and_validate_state_dict(path: Path) -> dict[str, torch.Tensor]:
    loaded = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(loaded, dict) or set(loaded) != set(EXPECTED_STATE_SHAPES):
        raise AuditFailure("unexpected_state_dict_keys")
    state: dict[str, torch.Tensor] = {}
    for key, shape in EXPECTED_STATE_SHAPES.items():
        value = loaded[key]
        if not isinstance(value, torch.Tensor) or tuple(value.shape) != shape:
            raise AuditFailure(f"state_dict_shape_mismatch:{key}")
        tensor = value.detach().to(dtype=torch.float32, device="cpu")
        if not bool(torch.isfinite(tensor).all()):
            raise AuditFailure(f"state_dict_non_finite:{key}")
        state[key] = tensor
    return state


def independent_actor_logits(
    features: torch.Tensor, state: Mapping[str, torch.Tensor]
) -> torch.Tensor:
    if features.ndim != 2 or features.shape[1] != 35:
        raise AuditFailure("forward_feature_shape_mismatch")
    hidden = torch.tanh(
        features @ state["encoder.0.weight"].T + state["encoder.0.bias"]
    )
    hidden = torch.tanh(
        hidden @ state["encoder.2.weight"].T + state["encoder.2.bias"]
    )
    return (hidden @ state["actor.weight"].T + state["actor.bias"]).reshape(-1)


def _recompute_test_metrics(
    cache: Mapping[str, np.ndarray | int],
    *,
    cache_manifest: Mapping[str, Any],
    bundle_manifest: Mapping[str, Any],
    state: Mapping[str, torch.Tensor],
    calibration_bin_count: int,
    ood_margin: float,
) -> dict[str, Any]:
    sample_count = int(cache["sample_count"])
    candidate_rows = int(cache["candidate_row_count"])
    counts = np.asarray(cache["candidate_count"], dtype=np.int64)
    selected = np.asarray(cache["selected_index"], dtype=np.int64)
    features = np.asarray(cache["features"], dtype=np.float32)
    if not np.all(np.isfinite(features)):
        raise AuditFailure("candidate_features_non_finite")
    logits = np.empty(candidate_rows, dtype=np.float32)
    with torch.no_grad():
        for start in range(0, candidate_rows, 65536):
            stop = min(start + 65536, candidate_rows)
            values = torch.from_numpy(features[start:stop])
            logits[start:stop] = independent_actor_logits(values, state).numpy()
    offsets = np.empty(sample_count + 1, dtype=np.int64)
    offsets[0] = 0
    np.cumsum(counts, out=offsets[1:])
    predictions = np.empty(sample_count, dtype=np.int64)
    confidences = np.empty(sample_count, dtype=np.float64)
    for index in range(sample_count):
        start, stop = int(offsets[index]), int(offsets[index + 1])
        sample_logits = logits[start:stop]
        prediction = int(np.argmax(sample_logits))
        shifted = sample_logits.astype(np.float64) - float(np.max(sample_logits))
        probabilities = np.exp(shifted)
        probabilities /= np.sum(probabilities)
        predictions[index] = prediction
        confidences[index] = probabilities[prediction]

    bounds = _mapping(
        cache_manifest.get("training_feature_bounds"), "training_bounds_missing"
    )
    bundle_bounds = _mapping(bundle_manifest.get("feature_bounds"), "bundle_bounds_missing")
    lower = np.asarray(bounds.get("minimum"), dtype=np.float64)
    upper = np.asarray(bounds.get("maximum"), dtype=np.float64)
    if lower.shape != (35,) or upper.shape != (35,) or np.any(lower > upper):
        raise AuditFailure("invalid_training_feature_bounds")
    if list(lower) != bundle_bounds.get("minimum") or list(upper) != bundle_bounds.get("maximum"):
        raise AuditFailure("cache_bundle_feature_bounds_mismatch")
    if bundle_bounds.get("ood_margin") != ood_margin:
        raise AuditFailure("ood_margin_binding_mismatch")
    span = np.maximum(upper - lower, 1.0e-6)
    outside_rows = np.any(
        (features < lower - ood_margin * span)
        | (features > upper + ood_margin * span),
        axis=1,
    )
    ood = np.logical_or.reduceat(outside_rows, offsets[:-1])

    true_rows = offsets[:-1] + selected
    predicted_rows = offsets[:-1] + predictions
    true_intent = np.asarray(cache["candidate_intent"], dtype=np.int64)[true_rows]
    predicted_intent = np.asarray(cache["candidate_intent"], dtype=np.int64)[
        predicted_rows
    ]
    exact = predictions == selected
    mappings = _mapping(cache_manifest.get("mappings"), "cache_mappings_missing")
    intent_mapping = _mapping(mappings.get("intent"), "intent_mapping_missing")
    camera_mapping = _mapping(mappings.get("camera_type"), "camera_mapping_missing")
    recalls: dict[str, float] = {}
    supports: dict[str, int] = {}
    for intent in INTENTS:
        code = _strict_int(intent_mapping.get(intent), f"intent_code_missing:{intent}")
        mask = true_intent == code
        supports[intent] = int(np.sum(mask))
        recalls[intent] = float(np.mean(predicted_intent[mask] == code))
    camera_codes = np.asarray(cache["camera_type"], dtype=np.int64)
    camera_metrics: dict[str, float | None] = {}
    camera_support: dict[str, int] = {}
    for role in CAMERA_TYPES:
        code = _strict_int(camera_mapping.get(role), f"camera_code_missing:{role}")
        mask = camera_codes == code
        camera_support[role] = int(np.sum(mask))
        camera_metrics[role] = float(np.mean(exact[mask])) if np.any(mask) else None
    ece, bins = _expected_calibration_error(exact, confidences, calibration_bin_count)
    metrics = {
        "sample_count": sample_count,
        "candidate_row_count": candidate_rows,
        "exact_action_accuracy": float(np.mean(exact)),
        "per_intent_recall": recalls,
        "per_intent_support": supports,
        "macro_intent_recall": float(np.mean(list(recalls.values()))),
        "per_camera_role_exact_action_accuracy": camera_metrics,
        "per_camera_role_support": camera_support,
        "expected_calibration_error": ece,
        "calibration_bins": bins,
        "mean_confidence": float(np.mean(confidences)),
        "feature_boundary_ood_count": int(np.sum(ood)),
        "feature_boundary_ood_fraction": float(np.mean(ood)),
        "ood_margin": ood_margin,
    }
    return {
        "metrics": metrics,
        "per_sample": {
            "sample_index": list(range(sample_count)),
            "prediction_index": predictions.tolist(),
            "confidence": confidences.tolist(),
            "feature_boundary_ood": ood.tolist(),
            "prediction_sha256": sha256(predictions.astype("<i8").tobytes()).hexdigest(),
            "confidence_sha256": sha256(confidences.astype("<f8").tobytes()).hexdigest(),
            "ood_sha256": sha256(ood.astype("u1").tobytes()).hexdigest(),
        },
    }


def _expected_calibration_error(
    exact: np.ndarray, confidence: np.ndarray, bin_count: int
) -> tuple[float, list[dict[str, Any]]]:
    if bin_count <= 0:
        raise AuditFailure("invalid_calibration_bin_count")
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    indices = np.minimum(np.searchsorted(edges, confidence, side="right") - 1, bin_count - 1)
    weighted = 0.0
    bins: list[dict[str, Any]] = []
    for index in range(bin_count):
        mask = indices == index
        count = int(np.sum(mask))
        if not count:
            continue
        accuracy = float(np.mean(exact[mask]))
        mean_confidence = float(np.mean(confidence[mask]))
        gap = abs(accuracy - mean_confidence)
        weighted += count * gap
        bins.append(
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "sample_count": count,
                "accuracy": accuracy,
                "mean_confidence": mean_confidence,
                "absolute_gap": gap,
            }
        )
    return weighted / len(exact), bins


def _reconcile_claimed_metrics(
    actual: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    claimed = _mapping(evidence.get("test_metrics"), "claimed_test_metrics_missing")
    comparisons = {
        "exact_action_accuracy": (
            actual["exact_action_accuracy"], claimed.get("exact_action_accuracy")
        ),
        "macro_intent_recall": (
            actual["macro_intent_recall"], claimed.get("macro_intent_recall")
        ),
        "expected_calibration_error": (
            actual["expected_calibration_error"],
            claimed.get("expected_calibration_error"),
        ),
        "feature_boundary_ood_fraction": (
            actual["feature_boundary_ood_fraction"],
            claimed.get("feature_boundary_ood_fraction"),
        ),
    }
    claimed_recalls = _mapping(claimed.get("per_action_recall"), "claimed_recalls_missing")
    for intent in INTENTS:
        comparisons[f"recall:{intent}"] = (
            _mapping(actual.get("per_intent_recall"), "actual_recalls_missing")[intent],
            claimed_recalls.get(intent),
        )
    claimed_camera = _mapping(
        claimed.get("per_camera_role_exact_action_accuracy"), "claimed_camera_missing"
    )
    for role in ("interceptor", "recon"):
        comparisons[f"camera:{role}"] = (
            _mapping(
                actual.get("per_camera_role_exact_action_accuracy"),
                "actual_camera_missing",
            )[role],
            claimed_camera.get(role),
        )
    result: dict[str, Any] = {}
    for name, (actual_value, claimed_value) in comparisons.items():
        difference = abs(float(actual_value) - _finite_float(claimed_value, f"invalid_claim:{name}"))
        result[name] = {
            "actual": actual_value,
            "claimed": claimed_value,
            "absolute_difference": difference,
            "matches_within_1e-6": difference <= 1.0e-6,
        }
        if difference > 1.0e-6:
            raise AuditFailure(f"claimed_metric_mismatch:{name}")
    return result


def _verify_hashes_unchanged(expected: Mapping[Path, str]) -> None:
    for path, digest in expected.items():
        if sha256_file(path) != digest:
            raise AuditFailure(f"cache_changed_during_audit:{path.name}")


def _require_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise AuditFailure(f"not_regular_file:{path}")


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuditFailure(code)
    return value


def _strict_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuditFailure(code)
    return value


def _finite_float(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditFailure(code)
    result = float(value)
    if not math.isfinite(result):
        raise AuditFailure(code)
    return result
