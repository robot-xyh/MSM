from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.scripts import (
    run_d1_covariance_limit_matrix as matrix_runner,
)
from research_modules.scalable_3d_simulation.scripts.run_d1_covariance_limit_matrix import (
    build_episode_command,
    load_matrix,
    planned_evidence_manifest,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_covariance_limit_multiseed_v1.json"
)
MATRIX_V2_PATH = MATRIX_PATH.with_name(
    "d1_covariance_limit_multiseed_v2.json"
)
MATRIX_V3_PATH = MATRIX_PATH.with_name(
    "d1_covariance_limit_multiseed_v3.json"
)


def test_pre_registered_matrix_has_expected_independent_and_long_cases() -> None:
    matrix = load_matrix(MATRIX_PATH)

    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert [case["seed"] for case in short] == list(range(1101, 1111))
    assert [case["seed"] for case in long] == [1101, 1102, 1103]
    assert {case["duration_s"] for case in short} == {2.2}
    assert {case["duration_s"] for case in long} == {10.0}
    assert all(set(case["arm_order"]) == {"reference", "candidate"} for case in matrix["cases"])


def test_v2_preserves_matrix_and_applies_common_d2_fix() -> None:
    v1 = load_matrix(MATRIX_PATH)
    v2 = load_matrix(MATRIX_V2_PATH)

    assert v2["experiment_id"].endswith("-v2")
    assert v2["reference_base_commit"] == v1["reference_commit"]
    assert v2["candidate_base_commit"] == v1["candidate_commit"]
    assert v2["common_d2_fix_source_commit"] == "e4147b8"
    assert v2["cases"] == v1["cases"]
    assert v2["admission_gates"] == v1["admission_gates"]
    assert v2["bootstrap_resamples"] == 10000
    assert v2["evidence_boundary"]["v1_outputs_reused"] is False


def test_v3_uses_common_psd_fix_and_commit_scoped_scalar_reference() -> None:
    v2 = load_matrix(MATRIX_V2_PATH)
    v3 = load_matrix(MATRIX_V3_PATH)

    assert v3["experiment_id"].endswith("-v3")
    assert v3["reference_base_commit"] == v3["candidate_commit"]
    assert v3["candidate_base_commit"] == v3["candidate_commit"]
    assert v3["common_d2_fix_source_commit"] == (
        v2["common_d2_fix_source_commit"]
    )
    assert v3["common_d1_psd_fix_source_commit"] == (
        v3["candidate_commit"]
    )
    assert v3["reference_treatment_commit"] == v3["reference_commit"]
    assert v3["cases"] == v2["cases"]
    assert v3["admission_gates"] == v2["admission_gates"]
    assert v3["bootstrap_resamples"] == 10000
    assert v3["evidence_boundary"]["v1_outputs_reused"] is False
    assert v3["evidence_boundary"]["v2_outputs_reused"] is False
    assert (
        v3["evidence_boundary"]["reference_vectorized_covariance_limit"]
        is False
    )
    assert (
        v3["evidence_boundary"]["candidate_vectorized_covariance_limit"]
        is True
    )


def test_command_carries_scale_seed_duration_flags_and_explicit_output(
    tmp_path: Path,
) -> None:
    matrix = load_matrix(MATRIX_PATH)
    command = build_episode_command(
        ROOT,
        matrix,
        matrix["cases"][0],
        tmp_path / "episode",
    )

    assert "--integrated-stack" in command
    assert "--d1-d2-structural-ambiguity-hold" in command
    assert command[command.index("--drone-count") + 1] == "200"
    assert command[command.index("--target-count") + 1] == "200"
    assert command[command.index("--recon-count") + 1] == "2"
    assert command[command.index("--seed") + 1] == "1101"
    assert command[command.index("--duration") + 1] == "2.2"
    assert Path(command[command.index("--output") + 1]).is_absolute()


def test_evidence_manifest_binds_arms_without_path_name_inference(
    tmp_path: Path,
) -> None:
    matrix = load_matrix(MATRIX_PATH)
    result = planned_evidence_manifest(
        MATRIX_PATH,
        matrix,
        ROOT,
        ROOT,
        tmp_path / "evidence",
    )

    assert result["status"] == "planned"
    assert len(result["cases"]) == 13
    first = result["cases"][0]
    assert first["arms"]["reference"]["arm"] == "reference"
    assert (
        first["arms"]["reference"]["expected_commit"]
        == matrix["reference_commit"]
    )
    assert first["arms"]["candidate"]["arm"] == "candidate"
    assert (
        first["arms"]["candidate"]["expected_commit"]
        == matrix["candidate_commit"]
    )
    assert first["cross_build_json"].endswith(
        "cross_build/cross_build_semantic_equivalence.json"
    )


def test_matrix_rejects_long_seed_without_matching_short(
    tmp_path: Path,
) -> None:
    matrix = load_matrix(MATRIX_PATH)
    invalid = copy.deepcopy(matrix)
    invalid["cases"][-1]["seed"] = 1200
    path = tmp_path / "invalid.json"

    path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(
        ValueError, match="long seed must have a matching short"
    ):
        load_matrix(path)


def test_run_failure_is_persisted_with_case_and_arm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = load_matrix(MATRIX_PATH)
    matrix["cases"] = [matrix["cases"][0]]
    matrix["cases"][0]["arm_order"] = ["reference", "candidate"]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    for root in (reference, candidate):
        entrypoint = (
            root
            / "research_modules"
            / "scalable_3d_simulation"
            / "run_episode.py"
        )
        entrypoint.parent.mkdir(parents=True)
        entrypoint.write_text("", encoding="utf-8")

    monkeypatch.setattr(
        matrix_runner,
        "_validate_worktrees",
        lambda matrix, worktrees: None,
    )

    def fail_arm(record: dict[str, object], worktree: Path) -> None:
        record["status"] = "failed"
        record["return_code"] = 7
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(matrix_runner, "_run_arm", fail_arm)
    output_root = tmp_path / "output"

    with pytest.raises(RuntimeError, match="fixture failure"):
        matrix_runner.run_matrix(
            matrix_path,
            reference,
            candidate,
            output_root,
            resume=False,
            dry_run=False,
        )

    evidence = json.loads(
        (output_root / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "failed"
    assert evidence["failure"] == {
        "case_id": "short_seed_1101",
        "arm": "reference",
        "error_type": "RuntimeError",
        "error": "fixture failure",
    }
    assert evidence["cases"][0]["arms"]["reference"]["status"] == "failed"
