#!/usr/bin/env python3
"""Run the pre-registered D1 covariance-limit clean A/B matrix."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
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

from research_modules.scalable_3d_simulation.cross_build_equivalence import (
    compare_cross_build_episodes,
    write_cross_build_equivalence_bundle,
)


MATRIX_SCHEMA_VERSION = (
    "scalable3d-d1-covariance-limit-multiseed-matrix-v1"
)
EVIDENCE_MANIFEST_SCHEMA_VERSION = (
    "scalable3d-d1-covariance-limit-multiseed-evidence-v1"
)
_ARMS = ("reference", "candidate")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_RUN_FLAGS = {
    "--config",
    "--drone-count",
    "--target-count",
    "--recon-count",
    "--duration",
    "--seed",
    "--output",
}


def load_matrix(path: str | Path) -> dict[str, Any]:
    """Load and fail-closed validate a pre-registered matrix."""

    matrix_path = Path(path).expanduser().resolve()
    value = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("matrix must be a JSON object")
    if value.get("schema_version") != MATRIX_SCHEMA_VERSION:
        raise ValueError("unsupported matrix schema_version")
    for field in ("experiment_id", "runtime_profile_sha256"):
        _required_text(value.get(field), field)
    for field in ("reference_commit", "candidate_commit"):
        commit = _required_text(value.get(field), field)
        if _COMMIT_RE.fullmatch(commit) is None:
            raise ValueError(f"{field} must be a full lowercase Git commit")
    for field in ("target_count", "resource_count", "recon_count"):
        _positive_int(value.get(field), field)
    cooldown_s = _finite_float(value.get("cooldown_s"), "cooldown_s")
    if cooldown_s < 0.0:
        raise ValueError("cooldown_s must be nonnegative")
    _positive_int(value.get("bootstrap_resamples"), "bootstrap_resamples")
    _nonnegative_int(value.get("bootstrap_seed"), "bootstrap_seed")

    flags = value.get("run_flags")
    if not isinstance(flags, list) or not all(
        isinstance(flag, str) and flag.strip() for flag in flags
    ):
        raise ValueError("run_flags must be a non-empty string list")
    if any(flag in _FORBIDDEN_RUN_FLAGS for flag in flags):
        raise ValueError("run_flags must not override matrix dimensions")
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
    return value


def build_episode_command(
    worktree: str | Path,
    matrix: Mapping[str, Any],
    case: Mapping[str, Any],
    output_dir: str | Path,
) -> list[str]:
    """Build the exact run command for one arm without shell interpolation."""

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
    reference_worktree: str | Path,
    candidate_worktree: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Create explicit arm/path bindings consumed later by D6."""

    root = Path(output_root).expanduser().resolve()
    worktrees = {
        "reference": Path(reference_worktree).expanduser().resolve(),
        "candidate": Path(candidate_worktree).expanduser().resolve(),
    }
    cases: list[dict[str, Any]] = []
    for case in matrix["cases"]:
        case_root = root / str(case["case_id"])
        arms: dict[str, Any] = {}
        for arm in _ARMS:
            episode_dir = case_root / f"{arm}_episode"
            arms[arm] = {
                "arm": arm,
                "expected_commit": matrix[f"{arm}_commit"],
                "worktree": str(worktrees[arm]),
                "episode_dir": str(episode_dir),
                "resource_path": str(case_root / f"{arm}_resource_usage.txt"),
                "stdout_path": str(case_root / f"{arm}_stdout.log"),
                "stderr_path": str(case_root / f"{arm}_stderr.log"),
                "command": build_episode_command(
                    worktrees[arm], matrix, case, episode_dir
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
                "cross_build_dir": str(case_root / "cross_build"),
                "cross_build_json": str(
                    case_root
                    / "cross_build"
                    / "cross_build_semantic_equivalence.json"
                ),
                "cross_build_status": "pending",
            }
        )
    return {
        "schema_version": EVIDENCE_MANIFEST_SCHEMA_VERSION,
        "experiment_id": matrix["experiment_id"],
        "matrix_path": str(Path(matrix_path).expanduser().resolve()),
        "matrix": matrix,
        "output_root": str(root),
        "status": "planned",
        "started_at_utc": None,
        "completed_at_utc": None,
        "cases": cases,
    }


def run_matrix(
    matrix_path: str | Path,
    reference_worktree: str | Path,
    candidate_worktree: str | Path,
    output_root: str | Path,
    *,
    resume: bool,
    dry_run: bool,
) -> dict[str, Any]:
    """Run all cases sequentially and persist an explicit evidence manifest."""

    matrix = load_matrix(matrix_path)
    worktrees = {
        "reference": Path(reference_worktree).expanduser().resolve(),
        "candidate": Path(candidate_worktree).expanduser().resolve(),
    }
    _validate_worktrees(matrix, worktrees)
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "evidence_manifest.json"
    manifest = planned_evidence_manifest(
        matrix_path,
        matrix,
        worktrees["reference"],
        worktrees["candidate"],
        root,
    )
    if resume and manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        _validate_resume_manifest(existing, manifest)
        manifest = existing
    manifest["status"] = "dry_run" if dry_run else "running"
    manifest["started_at_utc"] = (
        manifest.get("started_at_utc") or _utc_now()
    )
    _write_json_atomic(manifest_path, manifest)

    for case in manifest["cases"]:
        for arm in case["arm_order"]:
            arm_record = case["arms"][arm]
            episode_dir = Path(arm_record["episode_dir"])
            if resume and _episode_matches(
                episode_dir,
                expected_commit=str(arm_record["expected_commit"]),
                seed=int(case["seed"]),
                duration_s=float(case["duration_s"]),
                target_count=int(matrix["target_count"]),
                resource_count=int(matrix["resource_count"]),
                recon_count=int(matrix["recon_count"]),
                runtime_profile_sha256=str(
                    matrix["runtime_profile_sha256"]
                ),
            ):
                arm_record["status"] = "reused"
                arm_record["return_code"] = 0
                _write_json_atomic(manifest_path, manifest)
                continue
            if dry_run:
                arm_record["status"] = "planned"
                continue
            arm_record["status"] = "running"
            arm_record["started_at_utc"] = _utc_now()
            _write_json_atomic(manifest_path, manifest)
            try:
                _run_arm(arm_record, worktrees[arm])
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

        if dry_run:
            continue
        report = compare_cross_build_episodes(
            case["arms"]["reference"]["episode_dir"],
            case["arms"]["candidate"]["episode_dir"],
        )
        write_cross_build_equivalence_bundle(
            case["cross_build_dir"], report
        )
        case["cross_build_status"] = (
            "passed" if report["passed"] else "failed"
        )
        _write_json_atomic(manifest_path, manifest)
        if not report["passed"]:
            manifest["status"] = "failed"
            _write_json_atomic(manifest_path, manifest)
            raise RuntimeError(
                f"cross-build audit failed: {case['case_id']}"
            )

    manifest["status"] = "dry_run" if dry_run else "complete"
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
    resource_path = Path(record["resource_path"])
    stdout_path = Path(record["stdout_path"])
    stderr_path = Path(record["stderr_path"])
    command = [str(item) for item in record["command"]]
    timed_command = [
        "/usr/bin/time",
        "--verbose",
        "--output",
        str(resource_path),
        *command,
    ]
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
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


def _validate_worktrees(
    matrix: Mapping[str, Any],
    worktrees: Mapping[str, Path],
) -> None:
    for arm in _ARMS:
        root = worktrees[arm]
        if not root.is_dir():
            raise ValueError(f"{arm} worktree unavailable: {root}")
        head = _git_output(root, "rev-parse", "HEAD")
        if head != matrix[f"{arm}_commit"]:
            raise ValueError(
                f"{arm} worktree commit mismatch: {head}"
            )
        if _git_output(root, "status", "--porcelain"):
            raise ValueError(f"{arm} worktree is dirty")


def _validate_resume_manifest(
    existing: Any,
    planned: Mapping[str, Any],
) -> None:
    if not isinstance(existing, dict):
        raise ValueError("resume manifest must be an object")
    for field in ("schema_version", "experiment_id", "matrix", "output_root"):
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
    seed: int,
    duration_s: float,
    target_count: int,
    resource_count: int,
    recon_count: int,
    runtime_profile_sha256: str,
) -> bool:
    try:
        manifest = _read_mapping(episode_dir / "manifest.json")
        config = _read_mapping(episode_dir / "scenario_config.json")
        summary = _read_mapping(episode_dir / "summary.json")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        manifest.get("git_commit") == expected_commit
        and manifest.get("repository_dirty") is False
        and manifest.get("seed") == seed
        and manifest.get("runtime_profile_sha256")
        == runtime_profile_sha256
        and config.get("seed") == seed
        and _float_equal(config.get("duration_s"), duration_s)
        and config.get("target_count") == target_count
        and config.get("resource_count") == resource_count
        and config.get("recon_count") == recon_count
        and summary.get("finite_state") is True
        and summary.get("online_truth_use_count") == 0
        and _float_equal(
            summary.get("simulated_duration_s"), duration_s
        )
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
            float(value), float(expected), rel_tol=1e-12, abs_tol=1e-12
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
            / "d1_covariance_limit_multiseed_v1.json"
        ),
    )
    parser.add_argument("--reference-worktree", type=Path, required=True)
    parser.add_argument("--candidate-worktree", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_matrix(
        args.matrix,
        args.reference_worktree,
        args.candidate_worktree,
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
