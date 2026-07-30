#!/usr/bin/env python3
"""Build the D3 assignment-aware A1 candidate twice and compare bytes."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = MODULE_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from d3_assignment_planner import (  # noqa: E402
    A1AssignmentAwareConfig,
    build_a1_assignment_aware_teachers,
    freeze_a1_assignment_aware_bundle,
    load_a1_assignment_aware_bundle,
    load_a1_development_records,
    summarize_a1_assignment_aware_teachers,
    train_a1_assignment_aware_candidate,
    write_a1_assignment_aware_development_output,
)


DEFAULT_DATASET = (
    MODULE_ROOT.parent
    / "scalable_3d_simulation"
    / "outputs"
    / "learning_generation_v1_multibatchfix"
    / "learning_dataset"
    / "d3_assignment"
)
DEFAULT_OUTPUT = (
    MODULE_ROOT
    / "outputs"
    / "a1_assignment_aware_development_v1_20260730"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260730)
    arguments = parser.parse_args()
    if arguments.output.exists() and any(arguments.output.iterdir()):
        raise SystemExit(f"output directory is not empty: {arguments.output}")
    arguments.output.mkdir(parents=True, exist_ok=True)

    config = A1AssignmentAwareConfig(
        epochs=arguments.epochs,
        hidden_size=arguments.hidden_size,
        seed=arguments.seed,
    )
    _, records, source_dataset = load_a1_development_records(
        arguments.dataset
    )
    teachers = build_a1_assignment_aware_teachers(records, config=config)
    teacher_summary = summarize_a1_assignment_aware_teachers(teachers)
    source_tree_sha256 = _source_tree_sha256()
    repository_git_commit = _repository_commit()

    first_policy, first_result = train_a1_assignment_aware_candidate(
        teachers,
        config=config,
    )
    second_policy, second_result = train_a1_assignment_aware_candidate(
        teachers,
        config=config,
    )
    if first_result.to_dict() != second_result.to_dict():
        raise RuntimeError("same-input training result is not reproducible")

    first_bundle = freeze_a1_assignment_aware_bundle(
        arguments.output / "build_a" / "bundle",
        first_policy,
        first_result,
        config=config,
        source_dataset=source_dataset,
        source_tree_sha256=source_tree_sha256,
        repository_git_commit=repository_git_commit,
    )
    second_bundle = freeze_a1_assignment_aware_bundle(
        arguments.output / "build_b" / "bundle",
        second_policy,
        second_result,
        config=config,
        source_dataset=source_dataset,
        source_tree_sha256=source_tree_sha256,
        repository_git_commit=repository_git_commit,
    )
    comparison = write_a1_assignment_aware_development_output(
        arguments.output,
        bundle_a=first_bundle,
        bundle_b=second_bundle,
        training_result=first_result,
        teacher_summary=teacher_summary,
        source_dataset=source_dataset,
        config=config,
    )
    if not comparison["byte_reproducible"]:
        raise RuntimeError("same-input bundle bytes are not reproducible")
    for label, bundle in (
        ("build_a", first_bundle),
        ("build_b", second_bundle),
    ):
        loaded = load_a1_assignment_aware_bundle(
            arguments.output / label / "bundle",
            mode="source_independent_evaluation",
            expected_manifest_sha256=bundle["manifest_sha256"],
            expected_tree_sha256=bundle["tree_sha256"],
        )
        if not loaded.loaded:
            raise RuntimeError(
                f"{label} strict loader failed: {loaded.fallback_reason}"
            )

    summary = {
        "output": str(arguments.output),
        "source_tree_sha256": source_tree_sha256,
        "repository_git_commit": repository_git_commit,
        "teacher_summary": teacher_summary,
        "selected_epoch": first_result.selected_epoch,
        "development_gate_passed": first_result.development_gate_passed,
        "selection_reason": first_result.selection_reason,
        "train_metrics": first_result.final_train_metrics,
        "validation_metrics": first_result.selected_validation_metrics,
        "reproducibility": comparison,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _source_tree_sha256() -> str:
    files = sorted((MODULE_ROOT / "src" / "d3_assignment_planner").glob("*.py"))
    files.append(Path(__file__).resolve())
    digest = sha256()
    for path in sorted(files):
        relative = path.relative_to(MODULE_ROOT)
        digest.update(str(relative).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _repository_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=MODULE_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if len(value) != 40:
        raise RuntimeError("git commit is not a full SHA-1")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
