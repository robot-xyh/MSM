from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.scripts import (
    run_d1_publication_metadata_matrix as matrix_runner,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_publication_metadata_multiseed_v1.json"
)


def test_publication_metadata_matrix_freezes_same_commit_13_pair_contract() -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["same_clean_commit_required"] is True
    assert matrix["arm_implementations"] == {
        "reference": "per_track_copy_v1",
        "candidate": "immutable_shared_v1",
    }
    assert [case["seed"] for case in short] == list(range(1101, 1111))
    assert [case["seed"] for case in long] == [1101, 1102, 1103]
    assert {case["duration_s"] for case in short} == {2.2}
    assert {case["duration_s"] for case in long} == {10.0}
    assert matrix["admission_gates"][
        "short_minimum_d1_fusion_improvement_pct"
    ] == 10.0
    assert matrix["admission_gates"][
        "long_minimum_d1_fusion_improvement_pct"
    ] == 10.0


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

    implementation_index = reference.index(
        "--d1-publication-metadata-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "per_track_copy_v1"
    assert candidate[implementation_index + 1] == "immutable_shared_v1"
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
        "d6.d1_publication_metadata_multiseed_evaluation.v1"
    )
    assert len(manifest["cases"]) == 13
    for case in manifest["cases"]:
        assert {
            arm["expected_commit"] for arm in case["arms"].values()
        } == {commit}
        assert case["arms"]["reference"][
            "expected_implementation"
        ] == "per_track_copy_v1"
        assert case["arms"]["candidate"][
            "expected_implementation"
        ] == "immutable_shared_v1"
        assert case["arms"]["reference"][
            "expected_d1_implementation_id"
        ].endswith("per_track_audit_copy.v1")
        assert case["arms"]["candidate"][
            "expected_d1_implementation_id"
        ].endswith("immutable_shared_audit.v1")


def test_matrix_rejects_arm_override_in_common_flags(tmp_path: Path) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    invalid = copy.deepcopy(matrix)
    invalid["run_flags"].append("--d1-publication-metadata-implementation")
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
            "d1_publication_metadata_implementation": "immutable_shared_v1",
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
        "d1_publication_metadata_implementation": "immutable_shared_v1",
        "d1_publication_metadata_diagnostics": {
            "implementation_id": (
                "d1.publication_metadata.immutable_shared_audit.v1"
            ),
            "immutable_shared_publication_metadata": True,
            "operation_counts": {
                "global_track_metadata_materialization_count": 400,
                "shared_audit_value_reuse_count": 1200,
            },
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
        expected_implementation="immutable_shared_v1",
        seed=1101,
        duration_s=2.2,
        target_count=200,
        resource_count=200,
        recon_count=2,
    )
    summary["d1_publication_metadata_diagnostics"][
        "implementation_id"
    ] = "d1.publication_metadata.per_track_audit_copy.v1"
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(
        episode,
        expected_commit=commit,
        expected_implementation="immutable_shared_v1",
        seed=1101,
        duration_s=2.2,
        target_count=200,
        resource_count=200,
        recon_count=2,
    )


def test_episode_cli_exposes_publication_metadata_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-publication-metadata-implementation",
            "per_track_copy_v1",
        ]
    )
    assert args.d1_publication_metadata_implementation == "per_track_copy_v1"


def test_operator_interrupt_is_persisted_as_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    matrix["cases"] = [matrix["cases"][0]]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    monkeypatch.setattr(
        matrix_runner,
        "_validate_source_worktree",
        lambda worktree: "c" * 40,
    )

    def interrupt_arm(record: dict[str, object], worktree: Path) -> None:
        del record, worktree
        raise KeyboardInterrupt

    monkeypatch.setattr(matrix_runner, "_run_arm", interrupt_arm)
    output_root = tmp_path / "output"

    with pytest.raises(KeyboardInterrupt):
        matrix_runner.run_matrix(
            matrix_path,
            ROOT,
            output_root,
            resume=False,
            dry_run=False,
        )

    evidence = json.loads(
        (output_root / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "interrupted"
    assert evidence["failure"] == {
        "case_id": "short_seed_1101",
        "arm": "reference",
        "error_type": "KeyboardInterrupt",
        "error": "matrix execution interrupted by operator",
    }
    assert evidence["cases"][0]["arms"]["reference"][
        "status"
    ] == "interrupted"
