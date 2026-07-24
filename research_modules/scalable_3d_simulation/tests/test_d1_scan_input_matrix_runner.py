from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.scripts import (
    run_d1_scan_input_matrix as matrix_runner,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_scan_input_multiseed_v1.json"
)


def test_scan_input_matrix_freezes_same_commit_13_pair_contract() -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["same_clean_commit_required"] is True
    assert matrix["arm_implementations"] == {
        "reference": "reference_v1",
        "candidate": "candidate_v2",
    }
    assert [case["seed"] for case in short] == list(range(1101, 1111))
    assert [case["seed"] for case in long] == [1101, 1102, 1103]
    assert {case["duration_s"] for case in short} == {2.2}
    assert {case["duration_s"] for case in long} == {10.0}
    assert matrix["admission_gates"][
        "short_minimum_scan_input_improvement_pct"
    ] == 5.0
    assert matrix["admission_gates"][
        "long_minimum_scan_input_improvement_pct"
    ] == 5.0


def test_arm_commands_differ_only_by_explicit_implementation_and_output(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index("--d1-scan-input-implementation")
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "reference_v1"
    assert candidate[implementation_index + 1] == "candidate_v2"
    assert reference[output_index + 1] != candidate[output_index + 1]
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_manifest_binds_both_arms_to_one_commit_and_d6_contract(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    commit = "a" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["source_commit"] == commit
    assert manifest["source_repository_dirty"] is False
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_scan_input_multiseed_evaluation.v1"
    )
    assert len(manifest["cases"]) == 13
    for case in manifest["cases"]:
        assert {
            arm["expected_commit"] for arm in case["arms"].values()
        } == {commit}
        assert case["arms"]["reference"][
            "expected_implementation"
        ] == "reference_v1"
        assert case["arms"]["candidate"][
            "expected_implementation"
        ] == "candidate_v2"


def test_matrix_rejects_arm_override_in_common_flags(tmp_path: Path) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    invalid = copy.deepcopy(matrix)
    invalid["run_flags"].append("--d1-scan-input-implementation")
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ValueError, match="must not override"):
        matrix_runner.load_matrix(path)


def test_episode_resume_requires_actual_implementation_identity(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode"
    episode.mkdir()
    commit = "b" * 40
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "d1_scan_input_implementation": "candidate_v2",
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "d1_scan_input_implementation": "candidate_v2",
        "d1_scan_input_execution_config": {
            "implementation": "candidate_v2",
        },
        "d1_scan_input_performance_diagnostics": {
            "implementation": "candidate_v2",
        },
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    assert matrix_runner._episode_matches(
        episode,
        expected_commit=commit,
        expected_implementation="candidate_v2",
        seed=1101,
        duration_s=2.2,
        target_count=200,
        resource_count=200,
        recon_count=2,
    )
    summary["d1_scan_input_performance_diagnostics"][
        "implementation"
    ] = "reference_v1"
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(
        episode,
        expected_commit=commit,
        expected_implementation="candidate_v2",
        seed=1101,
        duration_s=2.2,
        target_count=200,
        resource_count=200,
        recon_count=2,
    )


def test_episode_cli_exposes_scan_input_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-scan-input-implementation",
            "reference_v1",
        ]
    )
    assert args.d1_scan_input_implementation == "reference_v1"
