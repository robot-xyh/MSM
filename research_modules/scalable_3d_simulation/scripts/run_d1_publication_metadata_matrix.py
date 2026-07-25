#!/usr/bin/env python3
"""Run the pre-registered same-commit D1 publication-metadata A/B matrix."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MATRIX_SCHEMA_VERSION = "scalable3d-d1-publication-metadata-multiseed-matrix-v1"
EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-multiseed-evidence-v1"
)
REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_multiseed_evaluation.v1"
)
V2_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-v2-multiseed-matrix-v1"
)
V2_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-publication-metadata-v2-multiseed-evidence-v1"
)
V2_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_publication_metadata_v2_multiseed_evaluation.v1"
)
CV_MOTION_MODEL_MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-cv-motion-model-cache-multiseed-matrix-v1"
)
CV_MOTION_MODEL_EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-cv-motion-model-cache-multiseed-evidence-v1"
)
CV_MOTION_MODEL_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION = (
    "d6.d1_cv_motion_model_cache_multiseed_evaluation.v1"
)
_ARMS = ("reference", "candidate")
_V1_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_track_copy_v1",
    "candidate": "immutable_shared_v1",
}
_V2_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_track_copy_v1",
    "candidate": "immutable_shared_v2",
}
_CV_MOTION_MODEL_EXPECTED_IMPLEMENTATIONS = {
    "reference": "per_prediction_build_v1",
    "candidate": "bounded_exact_lru_v1",
}
_D1_IMPLEMENTATION_IDS = {
    "per_track_copy_v1": (
        "d1.publication_metadata.per_track_audit_copy.v1"
    ),
    "immutable_shared_v1": (
        "d1.publication_metadata.immutable_shared_audit.v1"
    ),
    "immutable_shared_v2": (
        "d1.publication_metadata.immutable_shared_audit.v2"
    ),
    "per_prediction_build_v1": (
        "d1.fusion.cv_motion_model.per_prediction_build.v1"
    ),
    "bounded_exact_lru_v1": (
        "d1.fusion.cv_motion_model.bounded_exact_lru.v1"
    ),
}
_MATRIX_SPECS = {
    MATRIX_SCHEMA_VERSION: {
        "expected_implementations": _V1_EXPECTED_IMPLEMENTATIONS,
        "evidence_manifest_schema_version": (
            EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--d1-publication-metadata-implementation",
        "validation_kind": "publication_metadata_v1",
        "treatment_field": "d1_publication_metadata_implementation",
    },
    V2_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": _V2_EXPECTED_IMPLEMENTATIONS,
        "evidence_manifest_schema_version": (
            V2_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            V2_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": (
            "d1.publication_audit_tree.v2"
        ),
        "selector_flag": "--d1-publication-metadata-implementation",
        "validation_kind": "publication_metadata_v2",
        "treatment_field": "d1_publication_metadata_implementation",
    },
    CV_MOTION_MODEL_MATRIX_SCHEMA_VERSION: {
        "expected_implementations": (
            _CV_MOTION_MODEL_EXPECTED_IMPLEMENTATIONS
        ),
        "evidence_manifest_schema_version": (
            CV_MOTION_MODEL_EVIDENCE_MANIFEST_SCHEMA_VERSION
        ),
        "required_d6_evaluator_schema_version": (
            CV_MOTION_MODEL_REQUIRED_D6_EVALUATOR_SCHEMA_VERSION
        ),
        "publication_audit_contract_version": None,
        "selector_flag": "--d1-cv-motion-model-implementation",
        "validation_kind": "cv_motion_model_cache",
        "treatment_field": "d1_cv_motion_model_implementation",
    },
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_RUN_FLAGS = {
    "--config",
    "--drone-count",
    "--target-count",
    "--recon-count",
    "--duration",
    "--seed",
    "--output",
    "--d1-publication-metadata-implementation",
    "--d1-cv-motion-model-implementation",
    "--d1-cv-motion-model-cache-capacity",
}


def _matrix_spec(matrix: Mapping[str, Any]) -> Mapping[str, Any]:
    schema_version = matrix.get("schema_version")
    spec = _MATRIX_SPECS.get(schema_version)
    if spec is None:
        raise ValueError("unsupported matrix schema_version")
    return spec


def load_matrix(path: str | Path) -> dict[str, Any]:
    """Load and fail-closed validate the pre-registered evidence matrix."""

    matrix_path = Path(path).expanduser().resolve()
    value = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("matrix must be a JSON object")
    spec = _matrix_spec(value)
    _required_text(value.get("experiment_id"), "experiment_id")
    if value.get("same_clean_commit_required") is not True:
        raise ValueError("matrix must require one clean commit for both arms")
    for field in ("target_count", "resource_count", "recon_count"):
        _positive_int(value.get(field), field)
    cooldown_s = _finite_float(value.get("cooldown_s"), "cooldown_s")
    if cooldown_s < 0.0:
        raise ValueError("cooldown_s must be nonnegative")
    _positive_int(value.get("bootstrap_resamples"), "bootstrap_resamples")
    _nonnegative_int(value.get("bootstrap_seed"), "bootstrap_seed")

    implementations = value.get("arm_implementations")
    if implementations != spec["expected_implementations"]:
        expected = spec["expected_implementations"]
        raise ValueError(
            "arm_implementations must bind "
            f"{expected['reference']} and {expected['candidate']}"
        )

    flags = value.get("run_flags")
    if not isinstance(flags, list) or not all(
        isinstance(flag, str) and flag.strip() for flag in flags
    ):
        raise ValueError("run_flags must be a non-empty string list")
    if any(flag in _FORBIDDEN_RUN_FLAGS for flag in flags):
        raise ValueError("run_flags must not override matrix dimensions or arm")
    if "--integrated-stack" not in flags:
        raise ValueError("run_flags must enable --integrated-stack")

    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a non-empty list")
    case_ids: set[str] = set()
    group_seed_pairs: set[tuple[str, int]] = set()
    short_seeds: set[int] = set()
    long_seeds: set[int] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("each case must be an object")
        case_id = _required_text(item.get("case_id"), "case_id")
        if case_id in case_ids:
            raise ValueError(f"duplicate case_id: {case_id}")
        case_ids.add(case_id)
        group = _required_text(item.get("group"), "group")
        if group not in {"short", "long"}:
            raise ValueError(f"unsupported group: {group}")
        seed = _nonnegative_int(item.get("seed"), "seed")
        if (group, seed) in group_seed_pairs:
            raise ValueError(f"duplicate group/seed: {group}/{seed}")
        group_seed_pairs.add((group, seed))
        duration_s = _finite_float(item.get("duration_s"), "duration_s")
        if duration_s <= 0.0:
            raise ValueError("duration_s must be positive")
        arm_order = item.get("arm_order")
        if (
            not isinstance(arm_order, list)
            or len(arm_order) != 2
            or set(arm_order) != set(_ARMS)
        ):
            raise ValueError("arm_order must contain reference and candidate")
        (short_seeds if group == "short" else long_seeds).add(seed)
    if not long_seeds.issubset(short_seeds):
        raise ValueError("every long seed must have a matching short case")

    gates = value.get("admission_gates")
    if not isinstance(gates, dict) or not gates:
        raise ValueError("admission_gates must be a non-empty object")
    boundary = value.get("evidence_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("evidence_boundary must be an object")
    if boundary.get("same_source_commit_for_both_arms") is not True:
        raise ValueError("evidence boundary must require the same source commit")
    if (
        boundary.get("only_allowed_runtime_treatment_difference")
        != spec["treatment_field"]
    ):
        raise ValueError(
            "evidence boundary must isolate the registered runtime treatment"
        )
    if (
        boundary.get("reference_implementation")
        != implementations["reference"]
        or boundary.get("candidate_implementation")
        != implementations["candidate"]
    ):
        raise ValueError(
            "evidence boundary implementations must match arm_implementations"
        )
    contract_version = spec["publication_audit_contract_version"]
    if contract_version is not None:
        if (
            boundary.get("candidate_publication_audit_contract_version")
            != contract_version
        ):
            raise ValueError(
                "v2 evidence boundary must bind the publication audit contract"
            )
        if (
            boundary.get(
                "d2_content_audit_required_before_identity_reuse"
            )
            is not True
        ):
            raise ValueError(
                "v2 evidence boundary must require D2 content audit before "
                "identity reuse"
            )
        if (
            gates.get("all_pairs_d2_publication_metadata_audit_valid")
            is not True
        ):
            raise ValueError(
                "v2 admission gates must require valid D2 publication audit"
            )
        for field in (
            "maximum_short_d2_association_mean_increase_pct",
            "maximum_long_d2_association_mean_increase_pct",
        ):
            if _finite_float(gates.get(field), field) < 0.0:
                raise ValueError(f"{field} must be nonnegative")
    if spec["validation_kind"] == "cv_motion_model_cache":
        if boundary.get("cache_key_policy") != "exact_dt_process_noise":
            raise ValueError(
                "CV motion-model evidence must freeze the exact cache key"
            )
        if boundary.get("cache_capacity") != 128:
            raise ValueError(
                "CV motion-model evidence must freeze cache_capacity=128"
            )
        if boundary.get("matrix_values_are_read_only") is not True:
            raise ValueError(
                "CV motion-model evidence must require read-only matrices"
            )
        required_gates = {
            "all_pairs_cv_motion_model_cache_audit_valid": True,
            "minimum_candidate_model_build_reduction_pct": 95.0,
            "minimum_candidate_cache_hit_ratio_pct": 95.0,
        }
        for field, expected in required_gates.items():
            if gates.get(field) != expected:
                raise ValueError(
                    f"CV motion-model admission gate {field} must be "
                    f"{expected}"
                )
    return value


def build_episode_command(
    worktree: str | Path,
    matrix: Mapping[str, Any],
    case: Mapping[str, Any],
    arm: str,
    output_dir: str | Path,
) -> list[str]:
    """Build one arm command with an explicit registered implementation."""

    if arm not in _ARMS:
        raise ValueError(f"unsupported arm: {arm}")
    worktree_path = Path(worktree).expanduser().resolve()
    entrypoint = (
        worktree_path
        / "research_modules"
        / "scalable_3d_simulation"
        / "run_episode.py"
    )
    if not entrypoint.is_file():
        raise ValueError(f"run_episode.py unavailable: {entrypoint}")
    return [
        "python3",
        str(entrypoint),
        *[str(flag) for flag in matrix["run_flags"]],
        str(_matrix_spec(matrix)["selector_flag"]),
        str(matrix["arm_implementations"][arm]),
        "--duration",
        _format_float(float(case["duration_s"])),
        "--seed",
        str(int(case["seed"])),
        "--drone-count",
        str(int(matrix["resource_count"])),
        "--target-count",
        str(int(matrix["target_count"])),
        "--recon-count",
        str(int(matrix["recon_count"])),
        "--output",
        str(Path(output_dir).expanduser().resolve()),
    ]


def planned_evidence_manifest(
    matrix_path: str | Path,
    matrix: Mapping[str, Any],
    source_worktree: str | Path,
    source_commit: str,
    output_root: str | Path,
) -> dict[str, Any]:
    """Bind cases, arms, implementation identities and paths for D6."""

    if _COMMIT_RE.fullmatch(str(source_commit)) is None:
        raise ValueError("source_commit must be a full lowercase Git commit")
    root = Path(output_root).expanduser().resolve()
    worktree = Path(source_worktree).expanduser().resolve()
    spec = _matrix_spec(matrix)
    cases: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        case_root = root / str(case["case_id"])
        arms: dict[str, Any] = {}
        for arm in _ARMS:
            episode_dir = case_root / f"{arm}_episode"
            arms[arm] = {
                "arm": arm,
                "expected_implementation": matrix["arm_implementations"][arm],
                "expected_d1_implementation_id": (
                    _D1_IMPLEMENTATION_IDS[
                        matrix["arm_implementations"][arm]
                    ]
                ),
                "validation_kind": spec["validation_kind"],
                "expected_commit": source_commit,
                "episode_dir": str(episode_dir),
                "resource_path": str(case_root / f"{arm}_resource_usage.txt"),
                "stdout_path": str(case_root / f"{arm}_stdout.log"),
                "stderr_path": str(case_root / f"{arm}_stderr.log"),
                "command": build_episode_command(
                    worktree,
                    matrix,
                    case,
                    arm,
                    episode_dir,
                ),
                "status": "pending",
                "return_code": None,
            }
        cases.append(
            {
                "case_id": case["case_id"],
                "group": case["group"],
                "seed": case["seed"],
                "duration_s": case["duration_s"],
                "arm_order": list(case["arm_order"]),
                "arms": arms,
                "d6_evaluation_status": "pending",
            }
        )
    manifest = {
        "schema_version": spec["evidence_manifest_schema_version"],
        "experiment_id": matrix["experiment_id"],
        "matrix_path": str(Path(matrix_path).expanduser().resolve()),
        "matrix_sha256": _file_sha256(
            Path(matrix_path).expanduser().resolve()
        ),
        "matrix": matrix,
        "source_worktree": str(worktree),
        "source_commit": source_commit,
        "source_repository_dirty": False,
        "output_root": str(root),
        "required_d6_evaluator_schema_version": (
            spec["required_d6_evaluator_schema_version"]
        ),
        "status": "planned",
        "started_at_utc": None,
        "completed_at_utc": None,
        "cases": cases,
    }
    contract_version = spec["publication_audit_contract_version"]
    if contract_version is not None:
        manifest["publication_audit_contract_version"] = contract_version
    if spec["validation_kind"] == "cv_motion_model_cache":
        manifest["cv_motion_model_cache_capacity"] = int(
            matrix["evidence_boundary"]["cache_capacity"]
        )
        manifest["cv_motion_model_cache_diagnostics_schema_version"] = (
            "d1.cv_motion_model_cache_diagnostics.v1"
        )
    return manifest


def run_matrix(
    matrix_path: str | Path,
    source_worktree: str | Path,
    output_root: str | Path,
    *,
    resume: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Run all episode arms; semantic and admission decisions remain D6-owned."""

    matrix = load_matrix(matrix_path)
    spec = _matrix_spec(matrix)
    expected_cache_capacity = (
        int(matrix["evidence_boundary"]["cache_capacity"])
        if spec["validation_kind"] == "cv_motion_model_cache"
        else None
    )
    worktree = Path(source_worktree).expanduser().resolve()
    source_commit = _validate_source_worktree(worktree)
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "evidence_manifest.json"
    planned = planned_evidence_manifest(
        matrix_path,
        matrix,
        worktree,
        source_commit,
        root,
    )
    manifest = planned
    if resume and manifest_path.is_file():
        existing = _read_mapping(manifest_path)
        _validate_resume_manifest(existing, planned)
        manifest = existing
    manifest["status"] = "dry_run" if dry_run else "running"
    manifest["started_at_utc"] = (
        manifest.get("started_at_utc") or _utc_now()
    )
    _write_json_atomic(manifest_path, manifest)

    for case in manifest["cases"]:
        for arm in case["arm_order"]:
            record = case["arms"][arm]
            if resume and _episode_matches(
                Path(record["episode_dir"]),
                expected_commit=source_commit,
                expected_implementation=str(record["expected_implementation"]),
                seed=int(case["seed"]),
                duration_s=float(case["duration_s"]),
                target_count=int(matrix["target_count"]),
                resource_count=int(matrix["resource_count"]),
                recon_count=int(matrix["recon_count"]),
                require_v2_audit=(
                    matrix.get("schema_version") == V2_MATRIX_SCHEMA_VERSION
                ),
                validation_kind=str(spec["validation_kind"]),
                expected_cache_capacity=expected_cache_capacity,
            ):
                record["status"] = "reused"
                record["return_code"] = 0
                _write_json_atomic(manifest_path, manifest)
                continue
            if dry_run:
                record["status"] = "planned"
                continue
            record["status"] = "running"
            record["started_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            try:
                _run_arm(record, worktree)
                if not _episode_matches(
                    Path(record["episode_dir"]),
                    expected_commit=source_commit,
                    expected_implementation=str(
                        record["expected_implementation"]
                    ),
                    seed=int(case["seed"]),
                    duration_s=float(case["duration_s"]),
                    target_count=int(matrix["target_count"]),
                    resource_count=int(matrix["resource_count"]),
                    recon_count=int(matrix["recon_count"]),
                    require_v2_audit=(
                        matrix.get("schema_version")
                        == V2_MATRIX_SCHEMA_VERSION
                    ),
                    validation_kind=str(spec["validation_kind"]),
                    expected_cache_capacity=expected_cache_capacity,
                ):
                    raise RuntimeError(
                        "completed episode failed implementation or provenance "
                        "validation"
                    )
            except KeyboardInterrupt:
                record["status"] = "interrupted"
                manifest["status"] = "interrupted"
                manifest["failure"] = {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "error_type": "KeyboardInterrupt",
                    "error": "matrix execution interrupted by operator",
                }
                raise
            except Exception as exc:
                manifest["status"] = "failed"
                manifest["failure"] = {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                raise
            finally:
                _write_json_atomic(manifest_path, manifest)
            if float(matrix["cooldown_s"]) > 0.0:
                time.sleep(float(matrix["cooldown_s"]))
        if not dry_run:
            case["d6_evaluation_status"] = "episodes_complete_pending_d6"
            _write_json_atomic(manifest_path, manifest)

    manifest["status"] = (
        "dry_run" if dry_run else "episodes_complete_pending_d6"
    )
    manifest["completed_at_utc"] = _utc_now()
    _write_json_atomic(manifest_path, manifest)
    return manifest


def _run_arm(record: dict[str, Any], worktree: Path) -> None:
    episode_dir = Path(record["episode_dir"])
    if episode_dir.exists():
        raise FileExistsError(
            f"episode output already exists; use --resume: {episode_dir}"
        )
    episode_dir.parent.mkdir(parents=True, exist_ok=True)
    command = [str(item) for item in record["command"]]
    timed_command = [
        "/usr/bin/time",
        "--verbose",
        "--output",
        str(record["resource_path"]),
        *command,
    ]
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    with Path(record["stdout_path"]).open(
        "w", encoding="utf-8"
    ) as stdout, Path(record["stderr_path"]).open(
        "w", encoding="utf-8"
    ) as stderr:
        completed = subprocess.run(
            timed_command,
            cwd=worktree,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    record["return_code"] = int(completed.returncode)
    record["completed_at_utc"] = _utc_now()
    record["status"] = (
        "complete" if completed.returncode == 0 else "failed"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"episode command failed with {completed.returncode}: "
            f"{' '.join(command)}"
        )


def _validate_source_worktree(worktree: Path) -> str:
    if not worktree.is_dir():
        raise ValueError(f"source worktree unavailable: {worktree}")
    entrypoint = (
        worktree
        / "research_modules"
        / "scalable_3d_simulation"
        / "run_episode.py"
    )
    if not entrypoint.is_file():
        raise ValueError(f"run_episode.py unavailable: {entrypoint}")
    commit = _git_output(worktree, "rev-parse", "HEAD")
    if _COMMIT_RE.fullmatch(commit) is None:
        raise ValueError("source worktree HEAD is not a full Git commit")
    if _git_output(worktree, "status", "--porcelain"):
        raise ValueError("source worktree must be clean for formal evidence")
    return commit


def _validate_resume_manifest(
    existing: Mapping[str, Any],
    planned: Mapping[str, Any],
) -> None:
    for field in (
        "schema_version",
        "experiment_id",
        "matrix_sha256",
        "matrix",
        "source_commit",
        "source_worktree",
        "output_root",
        "required_d6_evaluator_schema_version",
    ):
        if existing.get(field) != planned.get(field):
            raise ValueError(f"resume manifest mismatch: {field}")
    existing_cases = [
        (
            item.get("case_id"),
            item.get("group"),
            item.get("seed"),
            item.get("duration_s"),
            item.get("arm_order"),
        )
        for item in existing.get("cases", [])
        if isinstance(item, Mapping)
    ]
    planned_cases = [
        (
            item.get("case_id"),
            item.get("group"),
            item.get("seed"),
            item.get("duration_s"),
            item.get("arm_order"),
        )
        for item in planned["cases"]
    ]
    if existing_cases != planned_cases:
        raise ValueError("resume manifest case matrix mismatch")


def _episode_matches(
    episode_dir: Path,
    *,
    expected_commit: str,
    expected_implementation: str,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
    require_v2_audit: bool = False,
    validation_kind: str = "publication_metadata_v1",
    expected_cache_capacity: int | None = None,
) -> bool:
    try:
        manifest = _read_mapping(episode_dir / "manifest.json")
        config = _read_mapping(episode_dir / "scenario_config.json")
        summary = _read_mapping(episode_dir / "summary.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if validation_kind == "cv_motion_model_cache":
        return _cv_motion_model_episode_matches(
            episode_dir,
            manifest=manifest,
            config=config,
            summary=summary,
            expected_commit=expected_commit,
            expected_implementation=expected_implementation,
            expected_cache_capacity=expected_cache_capacity,
            seed=seed,
            duration_s=duration_s,
            target_count=target_count,
            resource_count=resource_count,
            recon_count=recon_count,
        )
    if validation_kind not in {
        "publication_metadata_v1",
        "publication_metadata_v2",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    diagnostics = summary.get("d1_publication_metadata_diagnostics")
    expected_d1_implementation_id = _D1_IMPLEMENTATION_IDS.get(
        expected_implementation
    )
    if expected_d1_implementation_id is None:
        return False
    expected_candidate = expected_implementation in {
        "immutable_shared_v1",
        "immutable_shared_v2",
    }
    operation_counts = (
        diagnostics.get("operation_counts")
        if isinstance(diagnostics, Mapping)
        else None
    )
    implementation_operations_match = (
        isinstance(operation_counts, Mapping)
        and int(
            operation_counts.get(
                "global_track_metadata_materialization_count",
                0,
            )
        )
        > 0
    )
    if expected_candidate:
        implementation_operations_match = (
            implementation_operations_match
            and int(
                operation_counts.get(
                    "per_track_shared_audit_mapping_copy_count",
                    0,
                )
            )
            == 0
            and int(
                operation_counts.get("shared_audit_value_reuse_count", 0)
            )
            > 0
        )
    else:
        implementation_operations_match = (
            implementation_operations_match
            and int(
                operation_counts.get(
                    "per_track_shared_audit_mapping_copy_count",
                    0,
                )
            )
            > 0
            and int(
                operation_counts.get("shared_audit_value_reuse_count", 0)
            )
            == 0
        )
    contract_match = True
    if expected_implementation == "immutable_shared_v2":
        contract_match = (
            diagnostics.get("publication_audit_contract_version")
            == "d1.publication_audit_tree.v2"
            and _v2_d2_audit_matches(summary, candidate=True)
        )
    elif (
        expected_implementation == "per_track_copy_v1"
        and require_v2_audit
    ):
        contract_match = (
            diagnostics.get("publication_audit_contract_version") is None
            and _v2_d2_audit_matches(summary, candidate=False)
        )
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and isinstance(runtime_profile, Mapping)
        and runtime_profile.get("d1_publication_metadata_implementation")
        == expected_implementation
        and isinstance(diagnostics, Mapping)
        and diagnostics.get("implementation_id")
        == expected_d1_implementation_id
        and diagnostics.get("immutable_shared_publication_metadata")
        is expected_candidate
        and implementation_operations_match
        and contract_match
        and summary.get("d1_publication_metadata_implementation")
        == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _cv_motion_model_episode_matches(
    episode_dir: Path,
    *,
    manifest: Mapping[str, Any],
    config: Mapping[str, Any],
    summary: Mapping[str, Any],
    expected_commit: str,
    expected_implementation: str,
    expected_cache_capacity: int | None,
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
) -> bool:
    if expected_cache_capacity is None:
        return False
    expected_id = _D1_IMPLEMENTATION_IDS.get(expected_implementation)
    if expected_id is None:
        return False
    candidate = expected_implementation == "bounded_exact_lru_v1"
    if expected_implementation not in {
        "per_prediction_build_v1",
        "bounded_exact_lru_v1",
    }:
        return False
    runtime_profile = manifest.get("runtime_profile")
    runtime_configuration = (
        runtime_profile.get("configuration")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    initial_diagnostics = (
        runtime_profile.get("d1_cv_motion_model_cache_diagnostics")
        if isinstance(runtime_profile, Mapping)
        else None
    )
    diagnostics = summary.get("d1_cv_motion_model_cache_diagnostics")
    final = summary.get("module_final_diagnostics")
    final_diagnostics = (
        final.get("d1_cv_motion_model_cache_diagnostics")
        if isinstance(final, Mapping)
        else None
    )
    try:
        governance = _read_mapping(
            episode_dir / "observation_governance_audit.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    governance_diagnostics = governance.get(
        "d1_cv_motion_model_cache_diagnostics"
    )
    if not all(
        isinstance(value, Mapping)
        for value in (
            runtime_profile,
            runtime_configuration,
            initial_diagnostics,
            diagnostics,
            final,
            final_diagnostics,
            governance_diagnostics,
        )
    ):
        return False
    if (
        initial_diagnostics.get("schema_version")
        != "d1.cv_motion_model_cache_diagnostics.v1"
        or initial_diagnostics.get("implementation_id") != expected_id
        or initial_diagnostics.get("candidate_enabled") is not candidate
        or initial_diagnostics.get("cache_capacity")
        != expected_cache_capacity
        or initial_diagnostics.get("cache_entry_count") != 0
        or initial_diagnostics.get("operation_counts") != {}
    ):
        return False
    if (
        diagnostics != final_diagnostics
        or diagnostics != governance_diagnostics
        or diagnostics.get("schema_version")
        != "d1.cv_motion_model_cache_diagnostics.v1"
        or diagnostics.get("implementation_id") != expected_id
        or diagnostics.get("candidate_enabled") is not candidate
        or diagnostics.get("cache_capacity") != expected_cache_capacity
    ):
        return False
    if not _cv_motion_model_operation_counts_match(
        diagnostics,
        candidate=candidate,
        expected_cache_capacity=expected_cache_capacity,
    ):
        return False
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and runtime_profile.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and runtime_configuration.get(
            "d1_cv_motion_model_implementation"
        )
        == expected_implementation
        and runtime_configuration.get(
            "d1_cv_motion_model_cache_capacity"
        )
        == expected_cache_capacity
        and summary.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and final.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and governance.get("d1_cv_motion_model_implementation")
        == expected_implementation
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(summary.get("simulated_duration_s"), duration_s)
    )


def _cv_motion_model_operation_counts_match(
    diagnostics: Mapping[str, Any],
    *,
    candidate: bool,
    expected_cache_capacity: int,
) -> bool:
    operations = diagnostics.get("operation_counts")
    if not isinstance(operations, Mapping):
        return False
    names = (
        "prediction_request_count",
        "model_build_count",
        "nonpositive_dt_reference_bypass_count",
        "nonfinite_reference_bypass_count",
        "cache_hit_count",
        "cache_miss_count",
        "cache_eviction_count",
        "peak_entry_count",
    )
    counts: dict[str, int] = {}
    for name in names:
        value = operations.get(name, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return False
        counts[name] = int(value)
    entry_count = diagnostics.get("cache_entry_count")
    if (
        isinstance(entry_count, bool)
        or not isinstance(entry_count, int)
        or entry_count < 0
        or entry_count > expected_cache_capacity
        or counts["peak_entry_count"] > expected_cache_capacity
    ):
        return False
    requests = counts["prediction_request_count"]
    nonpositive = counts["nonpositive_dt_reference_bypass_count"]
    nonfinite = counts["nonfinite_reference_bypass_count"]
    if requests <= 0:
        return False
    if candidate:
        return (
            counts["cache_hit_count"] > 0
            and counts["cache_miss_count"] > 0
            and counts["model_build_count"]
            == counts["cache_miss_count"] + nonfinite
            and requests
            == (
                nonpositive
                + nonfinite
                + counts["cache_hit_count"]
                + counts["cache_miss_count"]
            )
        )
    return (
        entry_count == 0
        and counts["cache_hit_count"] == 0
        and counts["cache_miss_count"] == 0
        and counts["cache_eviction_count"] == 0
        and counts["peak_entry_count"] == 0
        and requests == nonpositive + counts["model_build_count"]
    )


def _v2_d2_audit_matches(
    summary: Mapping[str, Any],
    *,
    candidate: bool,
) -> bool:
    audit = summary.get("d2_publication_metadata_audit")
    if not isinstance(audit, Mapping):
        return False
    if (
        audit.get("schema_version")
        != "scalable3d-d2-publication-metadata-audit-v1"
    ):
        return False
    batch_count = audit.get("batch_count")
    latest = audit.get("latest")
    totals = audit.get("totals")
    if (
        isinstance(batch_count, bool)
        or not isinstance(batch_count, int)
        or batch_count <= 0
        or not isinstance(latest, Mapping)
        or not isinstance(totals, Mapping)
    ):
        return False
    required = (
        "metadata_count",
        "shared_subtree_full_audit_count",
        "shared_subtree_builtin_equivalent_reuse_count",
        "immutable_v2_contract_validation_count",
        "immutable_v2_full_content_audit_count",
        "immutable_v2_identity_reuse_count",
        "immutable_v2_contract_rejection_count",
    )
    for counts in (latest, totals):
        if any(
            isinstance(counts.get(key), bool)
            or not isinstance(counts.get(key), int)
            or int(counts[key]) < 0
            for key in required
        ):
            return False
    if any(int(totals[key]) < int(latest[key]) for key in required):
        return False
    if int(totals["metadata_count"]) <= 0:
        return False
    full_audit_count = int(totals["shared_subtree_full_audit_count"])
    builtin_reuse_count = int(
        totals["shared_subtree_builtin_equivalent_reuse_count"]
    )
    validation_count = int(
        totals["immutable_v2_contract_validation_count"]
    )
    v2_content_audit_count = int(
        totals["immutable_v2_full_content_audit_count"]
    )
    identity_reuse_count = int(
        totals["immutable_v2_identity_reuse_count"]
    )
    rejection_count = int(
        totals["immutable_v2_contract_rejection_count"]
    )
    if candidate:
        return (
            validation_count > 0
            and validation_count == v2_content_audit_count
            and full_audit_count == v2_content_audit_count
            and identity_reuse_count > 0
            and builtin_reuse_count == 0
            and rejection_count == 0
        )
    return (
        full_audit_count > 0
        and builtin_reuse_count > 0
        and validation_count == 0
        and v2_content_audit_count == 0
        and identity_reuse_count == 0
        and rejection_count == 0
    )


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"git {' '.join(args)} failed in {root}: "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _read_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_float(value: float) -> str:
    return format(value, ".15g")


def _required_text(value: Any, field: str) -> str:
    result = str(value).strip() if value is not None else ""
    if not result:
        raise ValueError(f"{field} must be non-empty")
    return result


def _positive_int(value: Any, field: str) -> int:
    result = _nonnegative_int(value, field)
    if result <= 0:
        raise ValueError(f"{field} must be positive")
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return int(value)


def _finite_float(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError(f"{field} must be finite numeric")
    return float(value)


def _float_equal(value: Any, expected: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and math.isclose(
            float(value),
            float(expected),
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        )
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=(
            ROOT
            / "research_modules"
            / "scalable_3d_simulation"
            / "configs"
            / "d1_publication_metadata_multiseed_v1.json"
        ),
    )
    parser.add_argument(
        "--source-worktree",
        type=Path,
        default=ROOT,
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_matrix(
        args.matrix,
        args.source_worktree,
        args.output_root,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    print(f"status={result['status']}")
    print(
        "evidence_manifest="
        f"{(args.output_root / 'evidence_manifest.json').resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
