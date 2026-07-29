"""Fail-closed audit for D4 readiness-v3 isolated paired evidence.

The source bundle is produced by the scalable 3D main runtime.  D6 treats it
as read-only evidence: every source file is bound through an externally pinned
``SHA256SUMS`` digest, and development ACKs never imply production authority.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
from typing import Any, Mapping, Sequence
import uuid


D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION_V1 = (
    "scalable3d-d4-v3-isolated-rollout-v1"
)
D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION = (
    "scalable3d-d4-v3-isolated-rollout-v2"
)
D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION = (
    "scalable3d-d4-v3-isolated-runtime-record-v1"
)
D4_V3_ISOLATED_SCOPE = "development_isolated_treatment_only"
D4_V3_ISOLATED_PAIRED_AUDIT_SCHEMA_VERSION = (
    "d6.d4-v3-isolated-paired-audit.v1"
)
D4_V3_ISOLATED_PAIRED_AUDIT_DATE = "2026-07-29"

_SHA256_RE_LENGTH = 64
_SOURCE_REPORT_NAME = "D4_V3_ISOLATED_ROLLOUT_REPORT_CN.md"
_MANIFEST_KEYS_V1 = frozenset(
    {
        "accepted_runtime_ack_seed_count",
        "candidate_identity_sha256",
        "created_at_utc",
        "d3_successor_rejection_reason_counts",
        "d3_successor_seed_count",
        "d6_paired_non_degradation_available",
        "duration_s",
        "finite_pair_count",
        "isolated_adoption_seed_count",
        "isolated_consumption_rejection_reason_counts",
        "online_truth_use_count",
        "pair_count",
        "pair_summary_sha256",
        "physical_execution_seed_count",
        "positive_benefit_available",
        "production_permissions",
        "raw_inference_seed_count",
        "recon_count",
        "region_count",
        "resource_count",
        "runtime_gate_pass_seed_count",
        "same_exogenous_config_count",
        "same_initial_state_count",
        "scenario",
        "schema_version",
        "scope",
        "seeds",
        "specification_id",
        "specification_sha256",
        "target_count",
    }
)
_MANIFEST_KEYS_V2 = _MANIFEST_KEYS_V1 | {"source_provenance"}
_SOURCE_PROVENANCE_KEYS = frozenset(
    {
        "git_commit",
        "git_commits",
        "git_commit_uniform",
        "repository_dirty",
        "episode_manifest_sha256",
        "implementation_file_sha256",
        "implementation_set_sha256",
    }
)
_IMPLEMENTATION_SOURCE_PATHS = frozenset(
    {
        (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/models.py"
        ),
        (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/planner.py"
        ),
        (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/regional_hint.py"
        ),
        (
            "research_modules/d4_distributed_fallback/"
            "d4_distributed_fallback/region_resource_paired_intervention.py"
        ),
        (
            "research_modules/d4_distributed_fallback/"
            "d4_distributed_fallback/region_resource_v3_paired_intervention.py"
        ),
        (
            "research_modules/d6_evaluation_metrics/"
            "d6_evaluation_metrics/runtime_plan_outcome_join.py"
        ),
        (
            "research_modules/d7_proportional_guidance/"
            "d7_proportional_guidance/scalable_3d_guidance.py"
        ),
        "research_modules/scalable_3d_simulation/d4_v3_isolated_rollout.py",
        "research_modules/scalable_3d_simulation/d6_integration.py",
        "research_modules/scalable_3d_simulation/module_stack.py",
        "research_modules/scalable_3d_simulation/orchestrator.py",
    }
)
D4_V3_ISOLATED_V2_MANIFEST_KEYS = _MANIFEST_KEYS_V2
D4_V3_ISOLATED_IMPLEMENTATION_SOURCE_PATHS = _IMPLEMENTATION_SOURCE_PATHS
_ROW_KEYS = frozenset(
    {
        "accepted_runtime_ack_count",
        "availability_reason",
        "buses_isolated",
        "candidate_decision_count",
        "control_episode_id",
        "control_intercept_count",
        "control_minimum_distance_m",
        "d3_successor_count",
        "isolated_adoption_count",
        "model_promotion_authority_granted",
        "paired_non_degradation_available",
        "physical_execution_window_count",
        "positive_benefit_available",
        "production_runtime_ack_emitted",
        "projection_pass_count",
        "raw_inference_count",
        "runtime_authority_granted",
        "runtime_gate_pass_count",
        "runtime_record_count",
        "runtime_records",
        "same_exogenous_config",
        "same_initial_state",
        "schema_version",
        "scope",
        "seed",
        "treatment_episode_id",
        "treatment_intercept_count",
        "treatment_minimum_distance_m",
        "worlds_isolated",
    }
)
_RUNTIME_RECORD_KEYS = frozenset(
    {
        "assignment_authority_granted",
        "assist_authority_granted",
        "coalition_commit_authority_granted",
        "control_authority_granted",
        "d3_successor",
        "decision",
        "degradation_authority_granted",
        "evaluation_timestamp_s",
        "expected_intervention_timestamp_s",
        "expected_snapshot_lineage_sha256",
        "isolated_consumption",
        "observed_snapshot_lineage_sha256",
        "physical_window",
        "production_runtime_ack_emitted",
        "revision",
        "runtime_ack",
        "schema_version",
        "scope",
        "seed",
        "takeover_authority_granted",
        "trigger_passed",
        "trigger_rejection_reasons",
    }
)
_PRODUCTION_BOOLEAN_KEYS = frozenset(
    {
        "assignment_authority_granted",
        "assist_authority_granted",
        "coalition_commit_authority_granted",
        "control_authority_granted",
        "degradation_authority_granted",
        "model_promotion_authority_granted",
        "online_authority",
        "production_runtime_ack",
        "production_runtime_ack_emitted",
        "runtime_authority_granted",
        "takeover_authority_granted",
    }
)
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "actor_id",
        "actor_name",
        "airsim_id",
        "ground_truth",
        "ground_truth_id",
        "object_id",
        "object_name",
        "offline_truth",
        "offline_truth_id",
        "truth",
        "truth_entity_id",
        "truth_entity_ids",
        "truth_id",
        "truth_ids",
        "truth_position",
        "truth_velocity",
    }
)
_EXECUTABLE_REGION_FIELDS = (
    "resource_quota_delta",
    "reserve_ratio",
    "hold",
    "request_replan",
)


class D4V3IsolatedPairedAuditError(ValueError):
    """Raised when a D4 v3 evidence bundle cannot be audited safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def validate_d4_v3_source_provenance(
    payload: Mapping[str, Any],
    *,
    seeds: Sequence[int],
) -> dict[str, Any]:
    """Validate the exact v2 source-provenance contract."""

    _require_exact_keys(
        payload,
        _SOURCE_PROVENANCE_KEYS,
        "manifest source_provenance",
    )
    commits = tuple(
        _git_commit(item, "source_provenance git_commits")
        for item in _sequence(
            payload.get("git_commits"),
            "source_provenance git_commits",
        )
    )
    _expect(
        commits and commits == tuple(sorted(set(commits))),
        "source_git_commits_invalid",
        "git_commits must be a non-empty sorted unique sequence",
    )
    uniform = _strict_bool(
        payload.get("git_commit_uniform"),
        "source_provenance git_commit_uniform",
    )
    declared_commit = payload.get("git_commit")
    if uniform:
        commit = _git_commit(
            declared_commit,
            "source_provenance git_commit",
        )
        _expect(
            commits == (commit,),
            "source_git_commit_uniformity_mismatch",
            "uniform provenance requires one matching commit",
        )
    else:
        _expect(
            declared_commit is None and len(commits) > 1,
            "source_git_commit_uniformity_mismatch",
            "non-uniform provenance requires null git_commit and multiple commits",
        )
        commit = None
    repository_dirty = _strict_bool(
        payload.get("repository_dirty"),
        "source_provenance repository_dirty",
    )

    expected_seed_keys = {str(seed) for seed in seeds}
    episode_hashes = _mapping(
        payload.get("episode_manifest_sha256"),
        "source_provenance episode_manifest_sha256",
    )
    _expect(
        set(episode_hashes) == expected_seed_keys,
        "source_episode_manifest_seed_mismatch",
        "episode manifest digest keys must exactly match manifest seeds",
    )
    normalized_episode_hashes: dict[str, dict[str, str]] = {}
    for seed_key in sorted(expected_seed_keys, key=int):
        arms = _mapping(
            episode_hashes[seed_key],
            f"source_provenance episode seed {seed_key}",
        )
        _require_exact_keys(
            arms,
            frozenset({"control", "treatment"}),
            f"source_provenance episode seed {seed_key}",
        )
        normalized_episode_hashes[seed_key] = {
            arm: f"sha256:{_normalise_sha256(arms[arm])}"
            for arm in ("control", "treatment")
        }

    implementation_hashes = _mapping(
        payload.get("implementation_file_sha256"),
        "source_provenance implementation_file_sha256",
    )
    _expect(
        set(implementation_hashes) == set(_IMPLEMENTATION_SOURCE_PATHS),
        "source_implementation_inventory_mismatch",
        "implementation digest inventory must exactly contain the fixed 11 files",
    )
    normalized_implementation_hashes = {
        path: _normalise_sha256(implementation_hashes[path])
        for path in sorted(_IMPLEMENTATION_SOURCE_PATHS)
    }
    expected_set_digest = _canonical_sha256(
        normalized_implementation_hashes
    )
    actual_set_digest = _normalise_sha256(
        payload.get("implementation_set_sha256")
    )
    _expect(
        actual_set_digest == expected_set_digest,
        "source_implementation_set_sha256_mismatch",
        "implementation_set_sha256 does not bind the 11 file digests",
    )
    return {
        "available": True,
        "validated": True,
        "git_commit": commit,
        "git_commits": list(commits),
        "git_commit_uniform": uniform,
        "repository_dirty": repository_dirty,
        "episode_manifest_sha256": normalized_episode_hashes,
        "implementation_file_count": len(normalized_implementation_hashes),
        "implementation_file_sha256": {
            path: f"sha256:{digest}"
            for path, digest in normalized_implementation_hashes.items()
        },
        "implementation_set_sha256": f"sha256:{actual_set_digest}",
    }


def audit_d4_v3_isolated_paired_evidence(
    input_root: str | Path,
    *,
    expected_sha256sums_sha256: str,
    allow_legacy_v1: bool = False,
) -> dict[str, Any]:
    """Audit one immutable D4 v3 isolated paired-evidence directory."""

    root = Path(input_root).resolve()
    _expect(root.is_dir(), "input_root_unavailable", f"missing directory: {root}")
    checksum_path = root / "SHA256SUMS"
    expected_checksum_digest = _normalise_sha256(expected_sha256sums_sha256)
    actual_checksum_digest = _sha256_file(checksum_path)
    _expect(
        actual_checksum_digest == expected_checksum_digest,
        "sha256sums_anchor_mismatch",
        "SHA256SUMS does not match the externally pinned digest",
    )
    checksums = _load_sha256sums(checksum_path, root=root)
    for relative, digest in checksums.items():
        _expect(
            _sha256_file(root / relative) == digest,
            "source_artifact_sha256_mismatch",
            relative,
        )

    manifest = _load_json(root / "manifest.json", "source manifest")
    source_schema = manifest.get("schema_version")
    if source_schema == D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION:
        _require_exact_keys(manifest, _MANIFEST_KEYS_V2, "source manifest")
        source_schema_status = "final_v2"
    elif (
        source_schema == D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION_V1
        and allow_legacy_v1
    ):
        _require_exact_keys(manifest, _MANIFEST_KEYS_V1, "source manifest")
        source_schema_status = "legacy_v1_compatibility_baseline_only"
    else:
        _fail("source_schema_unsupported", str(source_schema))
    _expect(
        manifest.get("scope") == D4_V3_ISOLATED_SCOPE,
        "source_scope_unsupported",
        str(manifest.get("scope")),
    )
    seeds = _integer_sequence(manifest.get("seeds"), "manifest seeds")
    _expect(seeds, "manifest_seed_set_empty", "at least one seed is required")
    _expect(
        len(seeds) == len(set(seeds)),
        "duplicate_manifest_seed",
        "manifest seeds must be unique",
    )
    _expect(
        _nonnegative_int(manifest.get("pair_count"), "manifest pair_count")
        == len(seeds),
        "manifest_pair_count_mismatch",
        "manifest pair_count does not match seeds",
    )
    if source_schema == D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION:
        source_provenance = validate_d4_v3_source_provenance(
            _mapping(
                manifest.get("source_provenance"),
                "manifest source_provenance",
            ),
            seeds=seeds,
        )
    else:
        source_provenance = {
            "available": False,
            "validated": False,
            "reason": "legacy_v1_has_no_source_provenance_contract",
        }
    expected_files = {
        "manifest.json",
        "paired_evidence.jsonl",
        _SOURCE_REPORT_NAME,
        *(f"seed_{seed}/paired_evidence.json" for seed in seeds),
    }
    _expect(
        set(checksums) == expected_files,
        "sha256sums_file_inventory_mismatch",
        "SHA256SUMS does not exactly bind the manifest, JSONL, report, and seed files",
    )

    rows = _load_jsonl(root / "paired_evidence.jsonl", "paired evidence JSONL")
    _expect(
        len(rows) == len(seeds),
        "paired_jsonl_seed_count_mismatch",
        "paired JSONL line count does not match manifest seeds",
    )
    row_seeds = tuple(
        _nonnegative_int(row.get("seed"), f"paired row {index} seed")
        for index, row in enumerate(rows, start=1)
    )
    _expect(
        len(row_seeds) == len(set(row_seeds)),
        "duplicate_paired_jsonl_seed",
        "paired JSONL contains duplicate seeds",
    )
    _expect(
        row_seeds == seeds,
        "paired_jsonl_seed_order_mismatch",
        "paired JSONL seeds must exactly follow the manifest order",
    )
    _expect(
        _canonical_sha256(rows)
        == _normalise_sha256(manifest.get("pair_summary_sha256")),
        "pair_summary_sha256_mismatch",
        "manifest pair_summary_sha256 does not bind the JSONL rows",
    )

    per_seed: list[dict[str, Any]] = []
    for seed, row in zip(seeds, rows, strict=True):
        seed_payload = _load_json(
            root / f"seed_{seed}" / "paired_evidence.json",
            f"seed {seed} paired evidence",
        )
        _expect(
            seed_payload == row,
            "per_seed_jsonl_payload_mismatch",
            f"seed {seed}",
        )
        per_seed.append(
            _audit_seed_row(
                row,
                seed=seed,
                manifest=manifest,
                source_schema_version=str(source_schema),
            )
        )

    _validate_manifest_aggregates(manifest, rows, per_seed)
    non_degradation = _paired_non_degradation(per_seed)
    rejection_counts = Counter(
        item["d3_successor"]["rejection_reason"]
        for item in per_seed
        if item["d3_successor"]["rejection_reason"] is not None
    )
    strict_chain_count = sum(
        item["chain_binding"]["strict_successor_ack_d7_chain_available"]
        for item in per_seed
    )
    accepted_development_ack_count = sum(
        item["development_runtime_ack"]["accepted"] for item in per_seed
    )
    positive_benefit = _positive_benefit_assessment(
        per_seed,
        duration_s=_positive_number(
            manifest["duration_s"],
            "manifest duration",
        ),
        strict_chain_count=strict_chain_count,
    )

    return {
        "schema_version": D4_V3_ISOLATED_PAIRED_AUDIT_SCHEMA_VERSION,
        "audit_date": D4_V3_ISOLATED_PAIRED_AUDIT_DATE,
        "input": {
            "root": str(root),
            "sha256sums_sha256": f"sha256:{actual_checksum_digest}",
            "verified_file_count": len(checksums),
            "source_schema_version": manifest["schema_version"],
            "source_schema_status": source_schema_status,
            "source_scope": manifest["scope"],
            "source_created_at_utc": manifest["created_at_utc"],
            "source_pair_summary_sha256": (
                f"sha256:{manifest['pair_summary_sha256']}"
            ),
            "source_provenance": source_provenance,
        },
        "scenario": {
            "scenario": manifest["scenario"],
            "target_count": _positive_int(
                manifest["target_count"], "manifest target_count"
            ),
            "resource_count": _positive_int(
                manifest["resource_count"], "manifest resource_count"
            ),
            "recon_count": _nonnegative_int(
                manifest["recon_count"], "manifest recon_count"
            ),
            "region_count": _positive_int(
                manifest["region_count"], "manifest region count"
            ),
            "duration_s": _positive_number(
                manifest["duration_s"], "manifest duration"
            ),
            "seeds": list(seeds),
        },
        "integrity": {
            "available": True,
            "passed": True,
            "manifest_bound": True,
            "jsonl_bound": True,
            "per_seed_files_bound": True,
            "sha256sums_externally_pinned": True,
            "duplicate_seed_count": 0,
            "missing_seed_count": 0,
            "nonfinite_value_count": 0,
            "online_truth_use_count": 0,
        },
        "aggregate": {
            "pair_count": len(per_seed),
            "pairing_claim_pass_count": sum(
                item["pairing_claims"]["passed"] for item in per_seed
            ),
            "raw_inference_seed_count": sum(
                item["candidate_pipeline"]["raw_inference"] for item in per_seed
            ),
            "runtime_gate_pass_seed_count": sum(
                item["candidate_pipeline"]["runtime_gate_passed"]
                for item in per_seed
            ),
            "projection_pass_seed_count": sum(
                item["candidate_pipeline"]["projection_passed"]
                for item in per_seed
            ),
            "isolated_adoption_seed_count": sum(
                item["candidate_pipeline"]["isolated_adoption"]
                for item in per_seed
            ),
            "d3_successor_seed_count": sum(
                item["d3_successor"]["available"] for item in per_seed
            ),
            "development_runtime_ack_accepted_seed_count": (
                accepted_development_ack_count
            ),
            "strict_successor_ack_d7_chain_seed_count": strict_chain_count,
            "physical_window_summary_seed_count": sum(
                item["physical_window"]["summary_available"] for item in per_seed
            ),
            "d3_successor_rejection_reason_counts": dict(
                sorted(rejection_counts.items())
            ),
            "paired_non_degradation": non_degradation,
            "positive_benefit": positive_benefit,
        },
        "authority_boundary": {
            "development_runtime_assignment_ack_observed": bool(
                accepted_development_ack_count
            ),
            "development_runtime_assignment_ack_count": (
                accepted_development_ack_count
            ),
            "production_runtime_authority": False,
            "production_assignment_authority": False,
            "production_degradation_authority": False,
            "production_takeover_authority": False,
            "production_coalition_commit_authority": False,
            "production_control_authority": False,
            "model_promotion_authority": False,
            "interpretation": (
                "accepted ACK is development runtime evidence only and does not "
                "grant production authority"
            ),
        },
        "evidence_boundary": {
            "pairing_flags_are_hash_bound_producer_claims": True,
            "initial_state_arrays_and_exogenous_schedules_embedded": False,
            "runtime_ack_payload_embedded": False,
            "runtime_ack_plan_identity_fields_embedded": False,
            "successor_source_and_successor_plan_payloads_embedded": False,
            "d7_guidance_payloads_embedded": False,
            "strict_successor_ack_d7_same_chain_replay_available": False,
            "production_claim_allowed": False,
            "causal_claim_allowed": False,
            "counterfactual_claim_allowed": False,
            "final_v2_source_admission": (
                source_schema_status == "final_v2"
            ),
        },
        "per_seed": per_seed,
    }


def _positive_benefit_assessment(
    per_seed: Sequence[Mapping[str, Any]],
    *,
    duration_s: float,
    strict_chain_count: int,
) -> dict[str, Any]:
    pair_count = len(per_seed)
    zero_intercept_count = sum(
        int(item["outcomes"]["control_intercept_count"]) == 0
        and int(item["outcomes"]["treatment_intercept_count"]) == 0
        for item in per_seed
    )
    equal_distance_count = sum(
        math.isclose(
            float(item["outcomes"]["control_minimum_distance_m"]),
            float(item["outcomes"]["treatment_minimum_distance_m"]),
            abs_tol=1.0e-9,
        )
        for item in per_seed
    )
    improved_pair_count = sum(
        (
            int(item["outcomes"]["treatment_intercept_count"])
            > int(item["outcomes"]["control_intercept_count"])
        )
        or (
            float(item["outcomes"]["treatment_minimum_distance_m"])
            < float(item["outcomes"]["control_minimum_distance_m"]) - 1.0e-9
        )
        for item in per_seed
    )
    successor_count = sum(
        bool(item["d3_successor"]["available"]) for item in per_seed
    )
    identifiable_action_count = sum(
        bool(item["candidate_action"]["candidate_action_identifiable"])
        for item in per_seed
    )
    reasons: list[str] = []
    if zero_intercept_count == pair_count:
        reasons.append("no_intercept_observed_within_manifest_horizon")
    if equal_distance_count == pair_count:
        reasons.append("paired_minimum_distance_identical_for_all_seeds")
    if improved_pair_count == 0:
        reasons.append("no_strictly_improved_declared_outcome_metric")
    if strict_chain_count < successor_count:
        reasons.append("successor_ack_d7_same_chain_coverage_incomplete")
    if identifiable_action_count == 0:
        reasons.append("candidate_executable_action_not_identifiable")
    reasons.append("compact_bundle_does_not_embed_replayable_ack_d7_payloads")
    return {
        "availability": "unavailable",
        "value": False,
        "reasons": reasons,
        "observed_context": {
            "duration_s": duration_s,
            "pair_count": pair_count,
            "zero_intercept_pair_count": zero_intercept_count,
            "equal_minimum_distance_pair_count": equal_distance_count,
            "strictly_improved_pair_count": improved_pair_count,
            "d3_successor_pair_count": successor_count,
            "strict_successor_ack_d7_chain_pair_count": strict_chain_count,
            "identifiable_candidate_action_pair_count": (
                identifiable_action_count
            ),
        },
    }


def write_d4_v3_isolated_paired_audit(
    output_dir: str | Path,
    result: Mapping[str, Any],
) -> dict[str, Path]:
    """Atomically write the D6 JSON, Chinese report, and output checksums."""

    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"D6 D4 v3 audit output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp-{uuid.uuid4().hex}")
    temporary.mkdir()
    try:
        json_path = temporary / "d4_v3_isolated_paired_audit.json"
        markdown_path = temporary / "D4_V3_ISOLATED_PAIRED_AUDIT_CN.md"
        checksum_path = temporary / "SHA256SUMS"
        _write_json(json_path, result)
        markdown_path.write_text(
            render_d4_v3_isolated_paired_audit_markdown(result),
            encoding="utf-8",
        )
        checksum_path.write_text(
            "".join(
                f"{_sha256_file(path)}  {path.name}\n"
                for path in (markdown_path, json_path)
            ),
            encoding="utf-8",
        )
        temporary.rename(output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        "json": output / "d4_v3_isolated_paired_audit.json",
        "markdown": output / "D4_V3_ISOLATED_PAIRED_AUDIT_CN.md",
        "sha256sums": output / "SHA256SUMS",
    }


def render_d4_v3_isolated_paired_audit_markdown(
    result: Mapping[str, Any],
) -> str:
    """Render a concise Chinese audit report."""

    scenario = _mapping(result["scenario"], "audit scenario")
    aggregate = _mapping(result["aggregate"], "audit aggregate")
    non_degradation = _mapping(
        aggregate["paired_non_degradation"],
        "paired non-degradation",
    )
    positive = _mapping(aggregate["positive_benefit"], "positive benefit")
    lines = [
        "# D4 readiness-v3 隔离双臂审计",
        "",
        "## 结论",
        "",
        (
            f"输入完整性审计通过。共核验 {aggregate['pair_count']} 个 seed，"
            f"原始推理、运行门、投影和隔离采用均覆盖 "
            f"{aggregate['isolated_adoption_seed_count']} 个 seed。"
        ),
        (
            f"D3 后继计划仅覆盖 {aggregate['d3_successor_seed_count']} 个 seed；"
            f"其余拒绝原因为 "
            f"`{aggregate['d3_successor_rejection_reason_counts']}`。"
        ),
        (
            "配对非退化仅针对已声明的拦截数和最小距离，"
            f"可用性为 `{non_degradation['availability']}`，"
            f"判定为 `{non_degradation['value']['overall']}`。"
        ),
        (
            "正收益不可用，结果固定为 false。"
            f"原因：{', '.join(positive['reasons'])}；"
            f"manifest 时长为 {positive['observed_context']['duration_s']} 秒。"
        ),
        "",
        "## 场景",
        "",
        f"- 场景：`{scenario['scenario']}`",
        (
            f"- 规模：目标 {scenario['target_count']}、资源 "
            f"{scenario['resource_count']}、侦察节点 {scenario['recon_count']}、"
            f"区域 {scenario['region_count']}"
        ),
        f"- 时长：{scenario['duration_s']} 秒",
        f"- seeds：{scenario['seeds']}",
        "",
        "## 权限边界",
        "",
        (
            f"- 接受的开发运行 ACK："
            f"{aggregate['development_runtime_ack_accepted_seed_count']} 个 seed。"
        ),
        "- 生产分配、降级、接管、联盟提交、控制和模型晋级权限均为 false。",
        (
            "- 开发 ACK 只说明隔离 treatment 中记录到一次运行消费，"
            "不能转换为生产运行 authority。"
        ),
        "",
        "## 逐 seed 结果",
        "",
        (
            "| seed | 后继计划 | 开发 ACK | 物理窗口摘要 | "
            "严格 ACK/D7 同链 | 可执行候选动作 | 拦截数 R0/A2 | 最小距离 R0/A2（米） |"
        ),
        "| ---: | :---: | :---: | :---: | :---: | ---: | --- | --- |",
    ]
    for item in _sequence(result["per_seed"], "per-seed audit"):
        row = _mapping(item, "per-seed row")
        lines.append(
            "| "
            f"{row['seed']} | "
            f"{_cn_bool(row['d3_successor']['available'])} | "
            f"{_cn_bool(row['development_runtime_ack']['accepted'])} | "
            f"{_cn_bool(row['physical_window']['summary_available'])} | "
            f"{_cn_bool(row['chain_binding']['strict_successor_ack_d7_chain_available'])} | "
            f"{row['candidate_action']['executable_change_count']} | "
            f"{row['outcomes']['control_intercept_count']}/"
            f"{row['outcomes']['treatment_intercept_count']} | "
            f"{row['outcomes']['control_minimum_distance_m']:.6f}/"
            f"{row['outcomes']['treatment_minimum_distance_m']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            (
                "- `SHA256SUMS`、manifest、JSONL 和逐 seed 文件已形成外部摘要绑定，"
                "可检测缺失、重复和内容篡改。"
            ),
            (
                "- 当前 paired evidence 未嵌入完整 ACK payload、ACK 的 plan "
                "id/version/source sequence，也未嵌入 D7 guidance payload。"
            ),
            (
                "- seed 2007 的 D4 advisory 到 D3 successor 谱系可核对。"
                "开发 ACK 和物理窗口摘要存在，但不能由该目录独立重放为完整同链证据。"
            ),
            (
                "- 初态和外生配置一致性在当前 schema 中是受摘要保护的 producer "
                "claim；目录未包含初态数组及通信、故障调度明细。"
            ),
            (
                "- 正收益理由由 manifest 时长和逐 seed 结果计算。"
                f"双臂均无拦截 {positive['observed_context']['zero_intercept_pair_count']}/"
                f"{positive['observed_context']['pair_count']} 个 seed，"
                f"最小距离相同 {positive['observed_context']['equal_minimum_distance_pair_count']}/"
                f"{positive['observed_context']['pair_count']} 个 seed。"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _audit_seed_row(
    row: Mapping[str, Any],
    *,
    seed: int,
    manifest: Mapping[str, Any],
    source_schema_version: str,
) -> dict[str, Any]:
    _require_exact_keys(row, _ROW_KEYS, f"seed {seed} paired row")
    _assert_finite_tree(row, f"seed {seed} paired row")
    _assert_truth_free(row, f"seed {seed} paired row")
    _expect(
        row.get("schema_version") == source_schema_version,
        "paired_row_schema_mismatch",
        f"seed {seed}",
    )
    _expect(
        row.get("scope") == D4_V3_ISOLATED_SCOPE,
        "paired_row_scope_mismatch",
        f"seed {seed}",
    )
    _expect(
        _nonnegative_int(row.get("seed"), f"seed {seed}") == seed,
        "paired_row_seed_mismatch",
        f"seed {seed}",
    )
    for key in (
        "same_initial_state",
        "same_exogenous_config",
        "worlds_isolated",
        "buses_isolated",
    ):
        _expect(
            _strict_bool(row.get(key), f"seed {seed} {key}"),
            "paired_isolation_claim_failed",
            f"seed {seed} {key}",
        )
    for key in (
        "production_runtime_ack_emitted",
        "runtime_authority_granted",
        "model_promotion_authority_granted",
        "paired_non_degradation_available",
        "positive_benefit_available",
    ):
        _expect(
            not _strict_bool(row.get(key), f"seed {seed} {key}"),
            "source_claim_exceeds_evidence",
            f"seed {seed} {key}",
        )
    _assert_no_production_permission(row, f"seed {seed} paired row")

    control_episode_id = _required_string(
        row, "control_episode_id", f"seed {seed} paired row"
    )
    treatment_episode_id = _required_string(
        row, "treatment_episode_id", f"seed {seed} paired row"
    )
    _expect(
        control_episode_id != treatment_episode_id,
        "paired_episode_identity_reused",
        f"seed {seed}",
    )
    runtime_records = _mapping_sequence(
        row.get("runtime_records"),
        f"seed {seed} runtime records",
    )
    _expect(
        _nonnegative_int(
            row.get("runtime_record_count"),
            f"seed {seed} runtime_record_count",
        )
        == len(runtime_records),
        "runtime_record_count_mismatch",
        f"seed {seed}",
    )
    _expect(
        _nonnegative_int(
            row.get("candidate_decision_count"),
            f"seed {seed} candidate_decision_count",
        )
        == len(runtime_records),
        "candidate_decision_count_mismatch",
        f"seed {seed}",
    )
    records = [
        _audit_runtime_record(
            record,
            seed=seed,
            manifest=manifest,
        )
        for record in runtime_records
    ]
    count_expectations = {
        "raw_inference_count": sum(
            item["candidate_pipeline"]["raw_inference"] for item in records
        ),
        "runtime_gate_pass_count": sum(
            item["candidate_pipeline"]["runtime_gate_passed"] for item in records
        ),
        "projection_pass_count": sum(
            item["candidate_pipeline"]["projection_passed"] for item in records
        ),
        "isolated_adoption_count": sum(
            item["candidate_pipeline"]["isolated_adoption"] for item in records
        ),
        "d3_successor_count": sum(
            item["d3_successor"]["available"] for item in records
        ),
        "accepted_runtime_ack_count": sum(
            item["development_runtime_ack"]["accepted"] for item in records
        ),
        "physical_execution_window_count": sum(
            item["physical_window"]["summary_available"] for item in records
        ),
    }
    for key, expected in count_expectations.items():
        _expect(
            _nonnegative_int(row.get(key), f"seed {seed} {key}") == expected,
            "paired_row_aggregate_count_mismatch",
            f"seed {seed} {key}",
        )

    control_intercepts = _nonnegative_int(
        row.get("control_intercept_count"),
        f"seed {seed} control intercept count",
    )
    treatment_intercepts = _nonnegative_int(
        row.get("treatment_intercept_count"),
        f"seed {seed} treatment intercept count",
    )
    control_distance = _nonnegative_number(
        row.get("control_minimum_distance_m"),
        f"seed {seed} control minimum distance",
    )
    treatment_distance = _nonnegative_number(
        row.get("treatment_minimum_distance_m"),
        f"seed {seed} treatment minimum distance",
    )
    record = records[0] if len(records) == 1 else None
    _expect(
        record is not None,
        "runtime_record_cardinality_unsupported",
        f"seed {seed} requires exactly one frozen intervention record",
    )
    return {
        "seed": seed,
        "pairing_claims": {
            "passed": True,
            "same_initial_state": True,
            "same_exogenous_config": True,
            "worlds_isolated": True,
            "buses_isolated": True,
            "source_state_and_schedule_replay_available": False,
        },
        "candidate_pipeline": record["candidate_pipeline"],
        "candidate_action": record["candidate_action"],
        "d3_successor": record["d3_successor"],
        "development_runtime_ack": record["development_runtime_ack"],
        "physical_window": record["physical_window"],
        "chain_binding": record["chain_binding"],
        "outcomes": {
            "control_intercept_count": control_intercepts,
            "treatment_intercept_count": treatment_intercepts,
            "control_minimum_distance_m": control_distance,
            "treatment_minimum_distance_m": treatment_distance,
            "intercept_delta": treatment_intercepts - control_intercepts,
            "minimum_distance_delta_m": treatment_distance - control_distance,
        },
    }


def _audit_runtime_record(
    record: Mapping[str, Any],
    *,
    seed: int,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    _require_exact_keys(
        record,
        _RUNTIME_RECORD_KEYS,
        f"seed {seed} runtime record",
    )
    _expect(
        record.get("schema_version")
        == D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION,
        "runtime_record_schema_mismatch",
        f"seed {seed}",
    )
    _expect(
        record.get("scope") == D4_V3_ISOLATED_SCOPE,
        "runtime_record_scope_mismatch",
        f"seed {seed}",
    )
    _expect(
        _nonnegative_int(record.get("seed"), f"seed {seed} runtime record seed")
        == seed,
        "runtime_record_seed_mismatch",
        f"seed {seed}",
    )
    _assert_no_production_permission(record, f"seed {seed} runtime record")
    _expect(
        _strict_bool(record.get("trigger_passed"), f"seed {seed} trigger"),
        "runtime_trigger_not_passed",
        f"seed {seed}",
    )
    _expect(
        not _text_sequence(
            record.get("trigger_rejection_reasons"),
            f"seed {seed} trigger reasons",
        ),
        "runtime_trigger_rejection_present",
        f"seed {seed}",
    )
    expected_lineage = _normalise_sha256(
        record.get("expected_snapshot_lineage_sha256")
    )
    observed_lineage = _normalise_sha256(
        record.get("observed_snapshot_lineage_sha256")
    )
    _expect(
        expected_lineage == observed_lineage,
        "snapshot_lineage_mismatch",
        f"seed {seed}",
    )
    _expect(
        math.isclose(
            _nonnegative_number(
                record.get("evaluation_timestamp_s"),
                f"seed {seed} evaluation timestamp",
            ),
            _nonnegative_number(
                record.get("expected_intervention_timestamp_s"),
                f"seed {seed} expected intervention timestamp",
            ),
            abs_tol=1.0e-9,
        ),
        "intervention_timestamp_mismatch",
        f"seed {seed}",
    )

    decision = _mapping(record.get("decision"), f"seed {seed} decision")
    _assert_no_production_permission(decision, f"seed {seed} decision")
    _expect(
        decision.get("schema") == "d4-region-resource-v3-isolated-paired-decision-v1",
        "decision_schema_mismatch",
        f"seed {seed}",
    )
    _expect(
        decision.get("development_only") is True
        and decision.get("formal_evaluation_authorized") is False,
        "development_scope_boundary_mismatch",
        f"seed {seed}",
    )
    _expect(
        decision.get("specification_id") == manifest.get("specification_id")
        and decision.get("specification_sha256")
        == manifest.get("specification_sha256")
        and decision.get("candidate_identity_sha256")
        == manifest.get("candidate_identity_sha256"),
        "decision_specification_binding_mismatch",
        f"seed {seed}",
    )

    control = _mapping(decision.get("control"), f"seed {seed} control arm")
    treatment = _mapping(
        decision.get("treatment"),
        f"seed {seed} treatment arm",
    )
    for name, arm in (("control", control), ("treatment", treatment)):
        _assert_no_production_permission(arm, f"seed {seed} {name} arm")
        _expect(
            arm.get("schema") == "d4-region-resource-v3-isolated-arm-decision-v1",
            "arm_schema_mismatch",
            f"seed {seed} {name}",
        )
        _expect(
            arm.get("specification_id") == manifest.get("specification_id")
            and arm.get("specification_sha256")
            == manifest.get("specification_sha256")
            and arm.get("candidate_identity_sha256")
            == manifest.get("candidate_identity_sha256"),
            "arm_specification_binding_mismatch",
            f"seed {seed} {name}",
        )
        advisory = _mapping(
            arm.get("advisory_contract"),
            f"seed {seed} {name} advisory",
        )
        arm_evidence = _mapping(
            arm.get("arm_evidence"),
            f"seed {seed} {name} arm evidence",
        )
        _expect(
            _canonical_sha256(advisory)
            == _normalise_sha256(arm_evidence.get("advisory_payload_sha256")),
            "advisory_payload_sha256_mismatch",
            f"seed {seed} {name}",
        )

    candidate_pipeline = {
        "raw_inference": _strict_bool(
            treatment.get("raw_inference_completed"),
            f"seed {seed} treatment raw inference",
        ),
        "runtime_gate_passed": _strict_bool(
            treatment.get("runtime_gate_passed"),
            f"seed {seed} treatment runtime gate",
        ),
        "projection_passed": _strict_bool(
            treatment.get("projection_passed"),
            f"seed {seed} treatment projection",
        ),
        "isolated_adoption": _strict_bool(
            treatment.get("isolated_treatment_influence_adopted"),
            f"seed {seed} isolated adoption",
        ),
    }
    _expect(
        all(candidate_pipeline.values()),
        "candidate_pipeline_incomplete",
        f"seed {seed}",
    )
    action = _candidate_action_delta(control, treatment, seed=seed)

    consumption = _mapping(
        record.get("isolated_consumption"),
        f"seed {seed} isolated consumption",
    )
    consumption_view = _mapping(
        consumption.get("view"),
        f"seed {seed} isolated consumption view",
    )
    treatment_advisory = _mapping(
        treatment.get("advisory_contract"),
        f"seed {seed} treatment advisory",
    )
    _expect(
        _mapping(
            consumption_view.get("advisory"),
            f"seed {seed} consumed advisory",
        )
        == treatment_advisory,
        "consumed_advisory_payload_mismatch",
        f"seed {seed}",
    )
    _expect(
        consumption.get("attempted") is True
        and consumption.get("consumable") is True
        and consumption_view.get("consumable") is True,
        "isolated_consumption_not_accepted",
        f"seed {seed}",
    )
    source_plan_id = _required_string(
        consumption,
        "source_plan_id",
        f"seed {seed} consumption",
    )
    source_plan_version = _nonnegative_int(
        consumption.get("source_plan_version"),
        f"seed {seed} source plan version",
    )
    source_versions = _sequence(
        treatment_advisory.get("source_plan_versions"),
        f"seed {seed} advisory source plan versions",
    )
    _expect(
        source_versions == [[source_plan_id, source_plan_version]],
        "advisory_source_plan_binding_mismatch",
        f"seed {seed}",
    )
    _expect(
        _normalise_sha256(treatment_advisory.get("authority_digest"))
        == _normalise_sha256(consumption_view.get("current_authority_digest")),
        "consumption_authority_digest_mismatch",
        f"seed {seed}",
    )

    successor = _audit_successor(
        _mapping(record.get("d3_successor"), f"seed {seed} D3 successor"),
        source_plan_id=source_plan_id,
        source_plan_version=source_plan_version,
        advisory=treatment_advisory,
        seed=seed,
    )
    runtime_ack = _audit_runtime_ack(
        _mapping(record.get("runtime_ack"), f"seed {seed} runtime ACK"),
        successor_available=successor["available"],
        seed=seed,
    )
    physical = _audit_physical_window(
        _mapping(record.get("physical_window"), f"seed {seed} physical window"),
        runtime_ack=runtime_ack,
        successor_available=successor["available"],
        seed=seed,
    )
    return {
        "candidate_pipeline": candidate_pipeline,
        "candidate_action": action,
        "d3_successor": successor,
        "development_runtime_ack": runtime_ack,
        "physical_window": physical,
        "chain_binding": {
            "d4_advisory_to_d3_successor_lineage_verified": (
                successor["lineage_verified"]
            ),
            "runtime_ack_summary_present": runtime_ack["available"],
            "physical_window_summary_present": physical["summary_available"],
            "runtime_ack_successor_identity_binding_available": False,
            "d7_window_successor_identity_binding_available": False,
            "strict_successor_ack_d7_chain_available": False,
            "unavailable_reasons": (
                [
                    "runtime_ack_payload_and_plan_identity_not_embedded",
                    "d7_guidance_payload_and_source_hash_not_embedded",
                ]
                if successor["available"]
                else ["d3_successor_unavailable"]
            ),
        },
    }


def _candidate_action_delta(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    *,
    seed: int,
) -> dict[str, Any]:
    control_advisory = _mapping(
        control.get("advisory_contract"),
        f"seed {seed} control advisory",
    )
    treatment_advisory = _mapping(
        treatment.get("advisory_contract"),
        f"seed {seed} treatment advisory",
    )
    control_regions = {
        _required_string(
            _mapping(
                item.get("source_version"),
                f"seed {seed} control source version",
            ),
            "region_id",
            f"seed {seed} control source version",
        ): item
        for item in _mapping_sequence(
            control_advisory.get("regions"),
            f"seed {seed} control regions",
        )
    }
    treatment_regions = {
        _required_string(
            _mapping(
                item.get("source_version"),
                f"seed {seed} treatment source version",
            ),
            "region_id",
            f"seed {seed} treatment source version",
        ): item
        for item in _mapping_sequence(
            treatment_advisory.get("regions"),
            f"seed {seed} treatment regions",
        )
    }
    _expect(
        set(control_regions) == set(treatment_regions),
        "paired_region_inventory_mismatch",
        f"seed {seed}",
    )
    executable: list[dict[str, Any]] = []
    reconnaissance: list[dict[str, Any]] = []
    for region_id in sorted(control_regions):
        control_region = control_regions[region_id]
        treatment_region = treatment_regions[region_id]
        for field in _EXECUTABLE_REGION_FIELDS:
            before = control_region.get(field)
            after = treatment_region.get(field)
            if before != after:
                executable.append(
                    {
                        "region_id": region_id,
                        "field": field,
                        "control": before,
                        "treatment": after,
                    }
                )
        before_priority = _number(
            control_region.get("reconnaissance_priority"),
            f"seed {seed} control reconnaissance priority",
        )
        after_priority = _number(
            treatment_region.get("reconnaissance_priority"),
            f"seed {seed} treatment reconnaissance priority",
        )
        if not math.isclose(before_priority, after_priority, abs_tol=1.0e-12):
            reconnaissance.append(
                {
                    "region_id": region_id,
                    "control": before_priority,
                    "treatment": after_priority,
                    "delta": after_priority - before_priority,
                }
            )
    if control_advisory.get("transfers") != treatment_advisory.get("transfers"):
        executable.append(
            {
                "field": "transfers",
                "control": control_advisory.get("transfers"),
                "treatment": treatment_advisory.get("transfers"),
            }
        )
    return {
        "candidate_action_identifiable": bool(executable),
        "executable_change_count": len(executable),
        "executable_changes": executable,
        "candidate_vs_rule_interpretation": (
            "candidate_executable_fields_differ_from_rule_control"
            if executable
            else "candidate_executable_fields_equal_rule_control"
        ),
        "reconnaissance_priority_change_count": len(reconnaissance),
        "reconnaissance_priority_changes": reconnaissance,
        "d3_successor_execution_delta_available": False,
        "d3_successor_execution_delta_reason": (
            "source_and_successor_assignment_payloads_not_embedded"
        ),
    }


def _audit_successor(
    successor: Mapping[str, Any],
    *,
    source_plan_id: str,
    source_plan_version: int,
    advisory: Mapping[str, Any],
    seed: int,
) -> dict[str, Any]:
    metadata = _mapping(
        successor.get("metadata"),
        f"seed {seed} successor metadata",
    )
    available = _strict_bool(
        successor.get("available"),
        f"seed {seed} successor available",
    )
    advisory_id = _required_string(
        advisory,
        "advisory_id",
        f"seed {seed} advisory",
    )
    _expect(
        metadata.get("regional_hint_advisory_id") == advisory_id
        and metadata.get("regional_hint_successor_advisory_id") == advisory_id
        and metadata.get("regional_hint_source_plan_id") == source_plan_id
        and metadata.get("regional_hint_successor_source_plan_id")
        == source_plan_id
        and metadata.get("regional_hint_source_plan_version")
        == source_plan_version
        and metadata.get("regional_hint_successor_source_plan_version")
        == source_plan_version,
        "d3_successor_source_lineage_mismatch",
        f"seed {seed}",
    )
    if available:
        plan_id = _required_string(
            successor, "plan_id", f"seed {seed} successor"
        )
        plan_version = _nonnegative_int(
            successor.get("plan_version"),
            f"seed {seed} successor plan version",
        )
        _expect(
            successor.get("hint_applied") is True
            and successor.get("rejection_reason") is None
            and metadata.get("regional_hint_successor_state")
            == "successor_published"
            and metadata.get("regional_hint_successor_plan_available") is True
            and metadata.get("regional_hint_successor_plan_id") == plan_id
            and metadata.get("regional_hint_successor_plan_version")
            == plan_version,
            "d3_successor_publication_binding_mismatch",
            f"seed {seed}",
        )
        _expect(
            plan_version > source_plan_version,
            "d3_successor_version_not_strictly_new",
            f"seed {seed}",
        )
        rejection_reason = None
    else:
        _expect(
            successor.get("hint_applied") is False
            and successor.get("plan_id") is None
            and successor.get("plan_version") is None
            and metadata.get("regional_hint_successor_plan_available") is False
            and metadata.get("regional_hint_successor_state") == "no_successor",
            "d3_no_successor_contract_mismatch",
            f"seed {seed}",
        )
        rejection_reason = _required_string(
            successor,
            "rejection_reason",
            f"seed {seed} successor",
        )
        _expect(
            metadata.get("regional_hint_successor_rejection_reason")
            == rejection_reason,
            "d3_successor_rejection_reason_mismatch",
            f"seed {seed}",
        )
        plan_id = None
        plan_version = None
    return {
        "available": available,
        "plan_id": plan_id,
        "plan_version": plan_version,
        "source_plan_id": source_plan_id,
        "source_plan_version": source_plan_version,
        "lineage_verified": True,
        "rejection_reason": rejection_reason,
    }


def _audit_runtime_ack(
    ack: Mapping[str, Any],
    *,
    successor_available: bool,
    seed: int,
) -> dict[str, Any]:
    available = _strict_bool(ack.get("available"), f"seed {seed} ACK available")
    accepted = _strict_bool(ack.get("accepted"), f"seed {seed} ACK accepted")
    bound = _strict_bool(
        ack.get("fully_bound_to_guidance"),
        f"seed {seed} ACK guidance binding",
    )
    if successor_available:
        _expect(
            available and accepted and bound,
            "development_runtime_ack_incomplete",
            f"seed {seed}",
        )
        _normalise_sha256(ack.get("payload_sha256"))
        timestamp = _nonnegative_number(
            ack.get("timestamp_s"),
            f"seed {seed} ACK timestamp",
        )
    else:
        _expect(
            not available and not accepted and not bound,
            "runtime_ack_without_successor",
            f"seed {seed}",
        )
        timestamp = None
    return {
        "available": available,
        "accepted": accepted,
        "fully_bound_to_guidance_claimed": bound,
        "timestamp_s": timestamp,
        "scope": D4_V3_ISOLATED_SCOPE,
        "production_runtime_authority": False,
        "successor_identity_binding_available": False,
    }


def _audit_physical_window(
    window: Mapping[str, Any],
    *,
    runtime_ack: Mapping[str, Any],
    successor_available: bool,
    seed: int,
) -> dict[str, Any]:
    available = _strict_bool(
        window.get("available"),
        f"seed {seed} physical window available",
    )
    observed = _strict_bool(
        window.get("physical_execution_observed"),
        f"seed {seed} physical execution observed",
    )
    complete = _strict_bool(
        window.get("window_complete"),
        f"seed {seed} physical window complete",
    )
    if successor_available:
        _expect(
            available and observed and complete and runtime_ack["accepted"],
            "physical_window_incomplete",
            f"seed {seed}",
        )
        start = _nonnegative_number(
            window.get("window_start_s"),
            f"seed {seed} physical window start",
        )
        end = _nonnegative_number(
            window.get("window_end_s"),
            f"seed {seed} physical window end",
        )
        _expect(end > start, "physical_window_interval_invalid", f"seed {seed}")
        guidance_count = _positive_int(
            window.get("guidance_publication_count"),
            f"seed {seed} guidance publication count",
        )
        command_count = _positive_int(
            window.get("matching_command_count"),
            f"seed {seed} matching command count",
        )
        non_hold_count = _positive_int(
            window.get("non_hold_control_count"),
            f"seed {seed} non-hold count",
        )
        _expect(
            non_hold_count <= command_count,
            "physical_window_count_mismatch",
            f"seed {seed}",
        )
        _expect(
            _nonnegative_int(
                window.get("hard_constraint_violation_count"),
                f"seed {seed} hard constraint count",
            )
            == 0,
            "physical_window_hard_constraint_violation",
            f"seed {seed}",
        )
    else:
        _expect(
            not available and not observed and not complete,
            "physical_window_without_successor",
            f"seed {seed}",
        )
        start = None
        end = None
        guidance_count = 0
        command_count = 0
        non_hold_count = 0
    return {
        "summary_available": available,
        "physical_execution_observed_claimed": observed,
        "window_complete": complete,
        "window_start_s": start,
        "window_end_s": end,
        "guidance_publication_count": guidance_count,
        "matching_command_count": command_count,
        "non_hold_control_count": non_hold_count,
        "successor_identity_binding_available": False,
    }


def _validate_manifest_aggregates(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    per_seed: Sequence[Mapping[str, Any]],
) -> None:
    counts = {
        "raw_inference_seed_count": sum(
            int(row["raw_inference_count"]) > 0 for row in rows
        ),
        "runtime_gate_pass_seed_count": sum(
            int(row["runtime_gate_pass_count"]) > 0 for row in rows
        ),
        "isolated_adoption_seed_count": sum(
            int(row["isolated_adoption_count"]) > 0 for row in rows
        ),
        "d3_successor_seed_count": sum(
            int(row["d3_successor_count"]) > 0 for row in rows
        ),
        "accepted_runtime_ack_seed_count": sum(
            int(row["accepted_runtime_ack_count"]) > 0 for row in rows
        ),
        "physical_execution_seed_count": sum(
            int(row["physical_execution_window_count"]) > 0 for row in rows
        ),
        "same_initial_state_count": sum(
            bool(row["same_initial_state"]) for row in rows
        ),
        "same_exogenous_config_count": sum(
            bool(row["same_exogenous_config"]) for row in rows
        ),
    }
    for key, expected in counts.items():
        _expect(
            _nonnegative_int(manifest.get(key), f"manifest {key}") == expected,
            "manifest_aggregate_count_mismatch",
            key,
        )
    _expect(
        _nonnegative_int(
            manifest.get("online_truth_use_count"),
            "manifest online truth use count",
        )
        == 0,
        "online_truth_use_nonzero",
        "manifest reports online truth use",
    )
    _expect(
        _nonnegative_int(
            manifest.get("finite_pair_count"),
            "manifest finite pair count",
        )
        == len(rows),
        "finite_pair_coverage_incomplete",
        "all paired rows must be finite",
    )
    permissions = _mapping(
        manifest.get("production_permissions"),
        "manifest production permissions",
    )
    expected_permission_keys = {
        "runtime_ack",
        "assist",
        "assignment",
        "degradation",
        "takeover",
        "coalition_commit",
        "control",
        "model_promotion",
    }
    _expect(
        set(permissions) == expected_permission_keys
        and all(value is False for value in permissions.values()),
        "production_permission_impersonation",
        "all production permissions must be explicitly false",
    )
    _expect(
        manifest.get("d6_paired_non_degradation_available") is False
        and manifest.get("positive_benefit_available") is False,
        "source_claim_exceeds_evidence",
        "source producer may not self-certify D6 non-degradation or benefit",
    )
    rejections = Counter(
        item["d3_successor"]["rejection_reason"]
        for item in per_seed
        if item["d3_successor"]["rejection_reason"] is not None
    )
    _expect(
        dict(sorted(rejections.items()))
        == manifest.get("d3_successor_rejection_reason_counts"),
        "manifest_rejection_count_mismatch",
        "D3 successor rejection counts do not match seed evidence",
    )


def _paired_non_degradation(
    per_seed: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    intercept_non_degraded = all(
        int(item["outcomes"]["treatment_intercept_count"])
        >= int(item["outcomes"]["control_intercept_count"])
        for item in per_seed
    )
    distance_non_degraded = all(
        float(item["outcomes"]["treatment_minimum_distance_m"])
        <= float(item["outcomes"]["control_minimum_distance_m"]) + 1.0e-9
        for item in per_seed
    )
    return {
        "availability": "available",
        "value": {
            "overall": intercept_non_degraded and distance_non_degraded,
            "intercept_count_non_degraded": intercept_non_degraded,
            "minimum_distance_non_degraded": distance_non_degraded,
            "pair_count": len(per_seed),
            "metric_coverage_count": len(per_seed),
            "intercept_delta_sum": sum(
                int(item["outcomes"]["intercept_delta"]) for item in per_seed
            ),
            "minimum_distance_delta_m_max_abs": max(
                (
                    abs(float(item["outcomes"]["minimum_distance_delta_m"]))
                    for item in per_seed
                ),
                default=0.0,
            ),
        },
        "scope": (
            "hash_bound_declared_intercept_count_and_minimum_distance_only"
        ),
        "does_not_imply_positive_benefit": True,
    }


def _load_sha256sums(path: Path, *, root: Path) -> dict[str, str]:
    _expect(path.is_file(), "sha256sums_unavailable", str(path))
    result: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    _expect(lines, "sha256sums_empty", str(path))
    for index, line in enumerate(lines, start=1):
        parts = line.split("  ", 1)
        _expect(
            len(parts) == 2,
            "sha256sums_line_invalid",
            f"line {index}",
        )
        digest = _normalise_sha256(parts[0])
        relative = parts[1]
        pure = PurePosixPath(relative)
        _expect(
            relative == pure.as_posix()
            and not pure.is_absolute()
            and ".." not in pure.parts
            and relative not in {"", ".", "SHA256SUMS"},
            "sha256sums_path_invalid",
            relative,
        )
        _expect(
            relative not in result,
            "sha256sums_duplicate_path",
            relative,
        )
        candidate = (root / relative).resolve()
        _expect(
            candidate.is_relative_to(root) and candidate.is_file(),
            "sha256sums_artifact_unavailable",
            relative,
        )
        result[relative] = digest
    return result


def _load_json(path: Path, context: str) -> dict[str, Any]:
    _expect(path.is_file(), "json_artifact_unavailable", context)
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except D4V3IsolatedPairedAuditError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("json_decode_failed", f"{context}: {type(exc).__name__}")
    return dict(_mapping(value, context))


def _load_jsonl(path: Path, context: str) -> list[dict[str, Any]]:
    _expect(path.is_file(), "jsonl_artifact_unavailable", context)
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        _expect(line.strip() == line and line, "jsonl_line_invalid", f"line {index}")
        try:
            value = json.loads(
                line,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except D4V3IsolatedPairedAuditError:
            raise
        except json.JSONDecodeError as exc:
            _fail("jsonl_decode_failed", f"line {index}: {exc.msg}")
        rows.append(dict(_mapping(value, f"{context} line {index}")))
    return rows


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key", key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    _fail("nonfinite_json_value", value)


def _assert_finite_tree(value: Any, context: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        _expect(
            math.isfinite(float(value)),
            "nonfinite_value_detected",
            context,
        )
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _assert_finite_tree(child, f"{context}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, child in enumerate(value):
            _assert_finite_tree(child, f"{context}[{index}]")
        return
    _fail("unsupported_json_value_type", context)


def _assert_truth_free(value: Any, context: str) -> None:
    violations: list[str] = []

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                normalized = str(key).strip().lower().replace("-", "_")
                if normalized in _FORBIDDEN_ONLINE_KEYS:
                    violations.append(f"{path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, context)
    _expect(
        not violations,
        "online_truth_field_detected",
        ", ".join(violations[:3]),
    )


def _assert_no_production_permission(value: Any, context: str) -> None:
    violations: list[str] = []

    def visit(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if key in _PRODUCTION_BOOLEAN_KEYS and child is not False:
                    violations.append(f"{path}.{key}={child!r}")
                visit(child, f"{path}.{key}")
        elif isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray)
        ):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, context)
    _expect(
        not violations,
        "production_permission_impersonation",
        ", ".join(violations[:3]),
    )


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    actual = set(value)
    _expect(
        actual == set(expected),
        "schema_key_mismatch",
        f"{context}: missing={sorted(set(expected) - actual)}, "
        f"extra={sorted(actual - set(expected))}",
    )


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("mapping_required", context)
    return value


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        _fail("sequence_required", context)
    return value


def _mapping_sequence(value: Any, context: str) -> list[Mapping[str, Any]]:
    return [
        _mapping(item, f"{context}[{index}]")
        for index, item in enumerate(_sequence(value, context))
    ]


def _text_sequence(value: Any, context: str) -> tuple[str, ...]:
    items = tuple(_string_value(item, context) for item in _sequence(value, context))
    _expect(
        len(items) == len(set(items)),
        "duplicate_text_value",
        context,
    )
    return items


def _integer_sequence(value: Any, context: str) -> tuple[int, ...]:
    return tuple(
        _nonnegative_int(item, context) for item in _sequence(value, context)
    )


def _required_string(
    value: Mapping[str, Any],
    key: str,
    context: str,
) -> str:
    return _string_value(value.get(key), f"{context}.{key}")


def _string_value(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("nonempty_string_required", context)
    return value


def _git_commit(value: Any, context: str) -> str:
    commit = _string_value(value, context)
    _expect(
        len(commit) == 40
        and all(character in "0123456789abcdef" for character in commit),
        "source_git_commit_invalid",
        context,
    )
    return commit


def _strict_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        _fail("boolean_required", context)
    return value


def _nonnegative_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("nonnegative_integer_required", context)
    return value


def _positive_int(value: Any, context: str) -> int:
    result = _nonnegative_int(value, context)
    if result <= 0:
        _fail("positive_integer_required", context)
    return result


def _number(value: Any, context: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        _fail("finite_number_required", context)
    return float(value)


def _nonnegative_number(value: Any, context: str) -> float:
    result = _number(value, context)
    if result < 0.0:
        _fail("nonnegative_number_required", context)
    return result


def _positive_number(value: Any, context: str) -> float:
    result = _number(value, context)
    if result <= 0.0:
        _fail("positive_number_required", context)
    return result


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalise_sha256(value: Any) -> str:
    text = str(value)
    if text.startswith("sha256:"):
        text = text[7:]
    _expect(
        len(text) == _SHA256_RE_LENGTH
        and all(character in "0123456789abcdef" for character in text),
        "sha256_invalid",
        str(value),
    )
    return text


def _sha256_file(path: Path) -> str:
    _expect(path.is_file(), "artifact_unavailable", str(path))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
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


def _cn_bool(value: Any) -> str:
    return "是" if bool(value) else "否"


def _expect(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise D4V3IsolatedPairedAuditError(code, message)


def _fail(code: str, message: str) -> None:
    raise D4V3IsolatedPairedAuditError(code, message)


__all__ = [
    "D4_V3_ISOLATED_PAIRED_AUDIT_DATE",
    "D4_V3_ISOLATED_PAIRED_AUDIT_SCHEMA_VERSION",
    "D4_V3_ISOLATED_IMPLEMENTATION_SOURCE_PATHS",
    "D4_V3_ISOLATED_RUNTIME_RECORD_SCHEMA_VERSION",
    "D4_V3_ISOLATED_SCOPE",
    "D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION",
    "D4_V3_ISOLATED_SOURCE_SCHEMA_VERSION_V1",
    "D4_V3_ISOLATED_V2_MANIFEST_KEYS",
    "D4V3IsolatedPairedAuditError",
    "audit_d4_v3_isolated_paired_evidence",
    "render_d4_v3_isolated_paired_audit_markdown",
    "validate_d4_v3_source_provenance",
    "write_d4_v3_isolated_paired_audit",
]
