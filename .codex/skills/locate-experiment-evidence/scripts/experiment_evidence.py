#!/usr/bin/env python3
"""Read-only locator and reproducibility triage for MSM experiment artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable


TEXT_SUFFIXES = {".md", ".json", ".jsonl", ".csv", ".txt", ".log", ".yaml", ".yml"}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
}
SEARCH_ROOTS = (
    "research_modules",
    "subagent_reviews",
    "deliverables",
)
MAX_CONTENT_BYTES = 256 * 1024
MAX_JSON_BYTES = 10 * 1024 * 1024


def classify(path: Path) -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".svg", ".gif"}:
        return "figure"
    if "manifest" in name or "fingerprint" in name or "freeze" in name:
        return "manifest"
    if "report" in name and suffix in {".md", ".docx", ".pdf"}:
        return "report"
    if suffix in {".json", ".csv"} and any(
        token in name for token in ("metric", "summary", "score", "result", "leaderboard")
    ):
        return "metrics"
    if name in {"settings.json", "scenario.json", "protocol.json"} or any(
        token in name for token in ("config", "settings", "scenario", "protocol", "camera_profile")
    ):
        return "config"
    if suffix in {".pt", ".pth", ".onnx", ".ckpt", ".pkl", ".joblib"} or any(
        token in name for token in ("model_bundle", "checkpoint", "weights")
    ):
        return "model"
    if suffix == ".log" or any(token in name for token in ("stdout", "stderr", "diagnostic")):
        return "log"
    if parts & {"raw", "snapshots", "fixtures", "online", "truth", "labels", "replay"}:
        return "input"
    if name in {"readme.md", "plan.md"}:
        return "documentation"
    return "other"


def walk_files(root: Path, *, max_files: int | None = None) -> Iterable[Path]:
    count = 0
    for directory, names, files in os.walk(root):
        names[:] = sorted(name for name in names if name not in SKIP_DIRS)
        for name in sorted(files):
            path = Path(directory) / name
            if not path.is_file():
                continue
            yield path
            count += 1
            if max_files is not None and count >= max_files:
                return


def search_files(roots: list[Path]) -> Iterable[Path]:
    """List ignored and tracked experiment files quickly, with an os.walk fallback."""
    command = ["rg", "--files", "--hidden", "--no-ignore"]
    for directory in sorted(SKIP_DIRS):
        command.extend(("-g", f"!**/{directory}/**"))
    command.append("--")
    command.extend(str(root) for root in roots)
    try:
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError:
        completed = None
    if completed is not None and completed.returncode in (0, 1):
        for line in completed.stdout.splitlines():
            if line.strip():
                yield Path(line)
        return
    for root in roots:
        yield from walk_files(root)


def repository_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    if root.is_file():
        root = root.parent
    return root


def candidate_roots(repo: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for relative in SEARCH_ROOTS:
        path = (repo / relative).resolve()
        if path.is_dir() and path not in seen:
            found.append(path)
            seen.add(path)
    return found or [repo]


def read_prefix(path: Path) -> str:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return ""
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_CONTENT_BYTES)
        return data.decode("utf-8", errors="ignore").lower()
    except OSError:
        return ""


def search_score(
    path: Path,
    phrase: str,
    tokens: list[str],
    *,
    inspect_content: bool,
) -> int:
    relative = str(path).lower()
    name = path.name.lower()
    score = 0
    if phrase and phrase in relative:
        score += 30
    for token in tokens:
        if token in name:
            score += 8
        elif token in relative:
            score += 5
    if inspect_content:
        content = read_prefix(path)
        if phrase and phrase in content:
            score += 12
        score += sum(2 for token in tokens if token in content)
    return score


def rg_content_candidates(roots: list[Path], phrase: str, tokens: list[str]) -> set[Path] | None:
    """Return files containing the query, or None when ripgrep is unavailable."""

    def run(patterns: list[str]) -> set[Path] | None:
        command = [
            "rg",
            "--files-with-matches",
            "--ignore-case",
            "--fixed-strings",
            "--no-messages",
        ]
        for pattern in patterns:
            command.extend(("-e", pattern))
        command.append("--")
        command.extend(str(root) for root in roots)
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False)
        except OSError:
            return None
        if completed.returncode not in (0, 1):
            return None
        return {Path(line).resolve() for line in completed.stdout.splitlines() if line.strip()}

    exact = run([phrase])
    if exact is None or exact or len(tokens) == 1:
        return exact
    return run(tokens)


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def find_artifacts(args: argparse.Namespace) -> int:
    repo = repository_root(args.root)
    phrase = args.query.strip().lower()
    tokens = [item for item in re.split(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", phrase) if item]
    if not tokens:
        raise SystemExit("query must contain at least one searchable token")
    roots = candidate_roots(repo)
    content_candidates = rg_content_candidates(roots, phrase, tokens)
    matches: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in search_files(roots):
        resolved = path if path.is_absolute() else (repo / path).absolute()
        if resolved in seen:
            continue
        seen.add(resolved)
        kind = classify(path)
        if args.kind and kind != args.kind:
            continue
        if kind == "other" and not args.include_other:
            continue
        inspect_content = content_candidates is None or resolved in content_candidates
        score = search_score(path, phrase, tokens, inspect_content=inspect_content)
        if score <= 0:
            continue
        stat = path.stat()
        matches.append(
            {
                "score": score,
                "kind": kind,
                "path": rel(path, repo),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    matches.sort(key=lambda item: (-item["score"], item["kind"], item["path"]))
    matches = matches[: args.limit]
    if args.json:
        print(json.dumps({"query": args.query, "root": str(repo), "matches": matches}, ensure_ascii=False, indent=2))
        return 0
    if not matches:
        print("No matching experiment artifacts found.")
        return 1
    print(f"Query: {args.query}")
    print(f"Repository: {repo}")
    print(f"Matches: {len(matches)}")
    print("SCORE  KIND           MODIFIED             PATH")
    for item in matches:
        print(f"{item['score']:>5}  {item['kind']:<13}  {item['modified']:<19}  {item['path']}")
    return 0


def scalar_values(value: Any) -> Iterable[Any]:
    if isinstance(value, (str, int, float, bool)) or value is None:
        yield value
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (str, int, float, bool)) or item is None:
                yield item


def collect_json_metadata(path: Path, metadata: dict[str, Any]) -> None:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            return
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).lower()
                values = list(scalar_values(item))
                if re.search(r"(?:^|_)seeds?(?:_|$)", lowered):
                    metadata["seeds"].update(str(v) for v in values if v is not None)
                if lowered in {"command", "argv", "rerun_command", "full_rerun_command", "offline_replay_command"}:
                    if isinstance(item, list):
                        command = " ".join(str(part) for part in item)
                    else:
                        command = str(item)
                    if command and command not in metadata["commands"]:
                        metadata["commands"].append(command)
                if lowered in {"git_commit", "source_commit", "commit_sha", "commit"}:
                    metadata["recorded_commits"].update(str(v) for v in values if v)
                if lowered in {"worktree_dirty", "git_dirty", "source_dirty"}:
                    metadata["recorded_dirty_states"].update(str(v).lower() for v in values)
                if "sha256" in lowered or "fingerprint" in lowered:
                    metadata["hash_field_count"] += 1
                if lowered in {
                    "experiment_id",
                    "campaign_id",
                    "target_count",
                    "resource_count",
                    "drone_count",
                    "clock_speed",
                    "duration_s",
                    "mode",
                    "simmode",
                    "status",
                    "schema_version",
                }:
                    for scalar in values:
                        if scalar is not None and len(metadata["parameters"][lowered]) < 12:
                            metadata["parameters"][lowered].add(str(scalar))
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)


def git_state(repo: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"head": None, "dirty": None}
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--short"], cwd=repo, check=True, text=True, capture_output=True
        ).stdout
        result = {"head": head, "dirty": bool(status.strip())}
    except (OSError, subprocess.CalledProcessError):
        pass
    return result


def environment_evidence(paths: list[Path]) -> bool:
    names = {path.name.lower() for path in paths}
    return any(
        name in names
        for name in (
            "requirements.txt",
            "requirements.lock",
            "poetry.lock",
            "uv.lock",
            "environment.yml",
            "pip_freeze.txt",
            "blocks_diagnostics.json",
        )
    )


def executable_command(command: str) -> bool:
    lowered = command.strip().lower()
    if not lowered or lowered.startswith("in_process "):
        return False
    return bool(
        re.search(r"(?:^|\s)(?:python3?|pytest|bash|sh)(?:\s|$)", lowered)
        or " -m " in lowered
        or ".py" in lowered
    )


def assess(counts: Counter[str], metadata: dict[str, Any], paths: list[Path]) -> dict[str, Any]:
    has_results = counts["metrics"] > 0 or counts["report"] > 0
    has_config = counts["config"] > 0
    has_manifest = counts["manifest"] > 0
    has_inputs = counts["input"] > 0
    has_models = counts["model"] > 0 or any("model" in path.name.lower() for path in paths)
    has_seed = bool(metadata["seeds"])
    has_command = any(executable_command(command) for command in metadata["commands"])
    has_commit = bool(metadata["recorded_commits"])
    has_dirty_state = bool(metadata["recorded_dirty_states"])
    has_hashes = metadata["hash_field_count"] > 0
    has_environment = environment_evidence(paths)

    exact_rerun = all(
        (has_results, has_config, has_seed, has_command, has_commit, has_dirty_state, has_environment)
    )
    offline_replay = all((has_results, has_manifest, has_inputs, has_seed, has_hashes))
    rescoring = all((counts["metrics"] > 0, has_inputs, has_manifest))
    if exact_rerun:
        grade = "A"
        verdict = "candidate exact-rerun package; manually verify every recorded version and hash"
    elif offline_replay:
        grade = "B"
        verdict = "candidate deterministic offline replay; full simulator equality is not established"
    elif has_results and has_config and has_seed:
        grade = "C"
        verdict = "partial rerun evidence; one or more provenance conditions must be reconstructed"
    else:
        grade = "D"
        verdict = "evidence inspection only; preserved artifacts are insufficient for a defensible rerun"

    missing: list[str] = []
    checks = (
        (has_results, "machine-readable metrics or report"),
        (has_config, "executed scenario/settings/protocol"),
        (has_seed, "complete seed list"),
        (has_command, "exact command and working directory"),
        (has_commit, "recorded source commit"),
        (has_dirty_state, "recorded dirty-worktree state"),
        (has_environment, "dependency and simulator/runtime versions"),
        (has_manifest, "lineage manifest"),
        (has_hashes, "input/config/model hashes"),
        (has_inputs, "raw observations or frozen replay inputs"),
    )
    for present, description in checks:
        if not present:
            missing.append(description)
    if not has_models:
        missing.append("frozen model/tracker evidence if the route uses learned or calibrated state")
    return {
        "grade": grade,
        "verdict": verdict,
        "exact_rerun_candidate": exact_rerun,
        "offline_replay_candidate": offline_replay,
        "metrics_rescoring_candidate": rescoring,
        "missing": missing,
    }


def audit_artifacts(args: argparse.Namespace) -> int:
    repo = repository_root(args.root)
    target = Path(args.path)
    if not target.is_absolute():
        target = (repo / target).resolve()
    if not target.exists():
        raise SystemExit(f"audit path does not exist: {target}")
    scan_root = target.parent if target.is_file() else target
    paths = list(walk_files(scan_root, max_files=args.max_files))
    if target.is_file() and target not in paths:
        paths.append(target)
    counts: Counter[str] = Counter(classify(path) for path in paths)
    by_kind: dict[str, list[str]] = {}
    for path in paths:
        kind = classify(path)
        if kind == "other":
            continue
        by_kind.setdefault(kind, [])
        if len(by_kind[kind]) < args.samples_per_kind:
            by_kind[kind].append(rel(path, repo))

    metadata: dict[str, Any] = {
        "seeds": set(),
        "commands": [],
        "recorded_commits": set(),
        "recorded_dirty_states": set(),
        "hash_field_count": 0,
        "parameters": {
            key: set()
            for key in (
                "experiment_id",
                "campaign_id",
                "target_count",
                "resource_count",
                "drone_count",
                "clock_speed",
                "duration_s",
                "mode",
                "simmode",
                "status",
                "schema_version",
            )
        },
    }
    for path in paths:
        if path.suffix.lower() == ".json":
            collect_json_metadata(path, metadata)
    assessment = assess(counts, metadata, paths)
    git = git_state(repo)
    serial_metadata = {
        "seeds": sorted(metadata["seeds"]),
        "commands": metadata["commands"][:20],
        "recorded_commits": sorted(metadata["recorded_commits"]),
        "recorded_dirty_states": sorted(metadata["recorded_dirty_states"]),
        "hash_field_count": metadata["hash_field_count"],
        "parameters": {
            key: sorted(values) for key, values in metadata["parameters"].items() if values
        },
    }
    payload = {
        "audit_path": str(target),
        "scan_root": str(scan_root),
        "repository": str(repo),
        "scanned_file_count": len(paths),
        "artifact_counts": dict(sorted(counts.items())),
        "artifact_samples": dict(sorted(by_kind.items())),
        "metadata": serial_metadata,
        "recorded_source_provenance": {
            "commits": sorted(metadata["recorded_commits"]),
            "dirty_states": sorted(metadata["recorded_dirty_states"]),
        },
        "current_workspace_state_not_original_provenance": git,
        "assessment": assessment,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"Audit path: {target}")
    print(f"Scanned root: {scan_root}")
    print(f"Files scanned: {len(paths)}")
    print(f"Reproducibility grade: {assessment['grade']}")
    print(f"Verdict: {assessment['verdict']}")
    print(
        "Capabilities: "
        f"exact-rerun={assessment['exact_rerun_candidate']}  "
        f"offline-replay={assessment['offline_replay_candidate']}  "
        f"rescoring={assessment['metrics_rescoring_candidate']}"
    )
    print("Artifact counts:")
    for kind, count in sorted(counts.items()):
        if kind != "other":
            print(f"  {kind:<14} {count}")
    if serial_metadata["parameters"]:
        print("Parameters found:")
        for key, values in serial_metadata["parameters"].items():
            print(f"  {key}: {', '.join(values[:12])}")
    print(f"Seeds found: {', '.join(serial_metadata['seeds'][:30]) or 'none'}")
    print(f"Recorded source commits: {', '.join(serial_metadata['recorded_commits']) or 'none'}")
    print(
        "Recorded dirty-worktree states: "
        f"{', '.join(serial_metadata['recorded_dirty_states']) or 'none'}"
    )
    print(
        "Current workspace (not original provenance): "
        f"HEAD={git['head'] or 'unknown'} dirty={git['dirty']}"
    )
    if serial_metadata["commands"]:
        print("Recorded commands:")
        for command in serial_metadata["commands"]:
            print(f"  {command}")
    print("Representative evidence:")
    for kind, samples in sorted(by_kind.items()):
        print(f"  {kind}:")
        for sample in samples:
            print(f"    {sample}")
    if assessment["missing"]:
        print("Missing or unverified conditions:")
        for item in assessment["missing"]:
            print(f"  - {item}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.set_defaults(func=None)
    subparsers = parser.add_subparsers(dest="command")

    find_parser = subparsers.add_parser("find", help="find experiment artifacts by name, path, or content")
    find_parser.add_argument("query")
    find_parser.add_argument("--root", default=".", help="repository root; defaults to current directory")
    find_parser.add_argument("--kind", choices=("report", "metrics", "config", "manifest", "log", "input", "model", "documentation"))
    find_parser.add_argument("--limit", type=int, default=30)
    find_parser.add_argument("--include-other", action="store_true")
    find_parser.add_argument("--json", action="store_true")
    find_parser.set_defaults(func=find_artifacts)

    audit_parser = subparsers.add_parser("audit", help="audit one experiment directory or report parent")
    audit_parser.add_argument("path")
    audit_parser.add_argument("--root", default=".", help="repository root; defaults to current directory")
    audit_parser.add_argument("--max-files", type=int, default=50000)
    audit_parser.add_argument("--samples-per-kind", type=int, default=8)
    audit_parser.add_argument("--json", action="store_true")
    audit_parser.set_defaults(func=audit_artifacts)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.func is None:
        parser.print_help()
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
