from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d6_evaluation_metrics.d4_v5_confidence_candidate_audit import (
    D4V5CandidateAuditError,
    audit_d4_v5_confidence_candidate,
    load_d4_v5_candidate_audit_inputs,
    write_d4_v5_candidate_audit_report,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INPUT_SPEC = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/configs/"
    "d4_v5_confidence_candidate_independent_audit_20260729.json"
)


def _inputs():
    return load_d4_v5_candidate_audit_inputs(
        INPUT_SPEC,
        repository_root=REPOSITORY_ROOT,
    )


def _canonical_sha256(value: object) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def test_real_v5_candidate_recalculates_memory_bias_without_test_payload_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _inputs()
    dataset_manifest = json.loads(
        (
            inputs.base_v4_root / "development_dataset/manifest.json"
        ).read_text(encoding="utf-8")
    )
    forbidden_test_paths = {
        (
            inputs.base_v4_root
            / "development_dataset"
            / episode["relative_path"]
        ).resolve()
        for episode in dataset_manifest["episodes"]
        if episode["split"] == "test"
    }
    original_read_text = Path.read_text

    def guarded_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path.resolve() in forbidden_test_paths:
            raise AssertionError(f"TEST payload semantic read: {path}")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    result = audit_d4_v5_confidence_candidate(inputs)

    assert result["audit_execution_passed"] is True
    assert result["strict_profile_passed"] is False
    assert result["status"] == (
        "completed_development_memorization_baseline_"
        "candidate_unregistered_admission_closed"
    )
    assert "documented_latent_dimension_mismatch" in result[
        "strict_profile_blocker_codes"
    ]
    assert result["anchors"][
        "candidate_manifest_file_sha256"
    ] == (
        "caa774143db4a9c797e2a4ddff42d8f4cbc437471fe95926270f9bdec93b9459"
    )
    assert result["anchors"][
        "candidate_manifest_content_sha256"
    ] == (
        "83192d4f96d7dd2c64ffd8f9b5c7c11a70c8c24a90934a0dfea12fe397c12c52"
    )
    assert result["anchors"]["calibration_state_file_sha256"] == (
        "d8bd543759f6e52eb62585c1bd8aa67e59e718e7b548d38cc9dd5c690a5612a3"
    )
    assert result["anchors"]["calibration_summary_file_sha256"] == (
        "7f0047f72ebeea0358c127af5fe3dabe0c7f886bee48ff94b7d92b12b3259c60"
    )
    assert result["anchors"]["development_gate_file_sha256"] == (
        "e88c9480765369e34a03dd417e4b483143188da40c3403ff35918f9cfd605b3c"
    )
    assert result["anchors"]["builder_source_sha256"] == (
        "77e91e06712013e6c1195c40f72b9a941d8396aa4594b52bd7d839276b57e1e0"
    )

    assert result["candidate_tree"]["file_count"] == 4
    assert result["candidate_tree"]["external_anchors_match"] is True
    base = result["base_v4_and_v3_binding"]
    assert base["base_v4_file_count"] == 180
    assert base["base_v4_tree_sha256"] == (
        "2afd692874b91a23a5525448a0c5af98f3c2d96f0b12cebbf81a570d58d500d0"
    )
    assert base["v3_registry_tree_sha256"] == (
        "07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a"
    )
    assert base["test_payload_semantic_read_count"] == 0
    assert base["formal_holdout_payload_read_count"] == 0

    latent = result["latent_reconstruction"]
    assert latent["actual_frozen_actor_hidden_dimension"] == 24
    assert latent["candidate_state_feature_dimension"] == 24
    assert latent["documented_or_requested_feature_dimension"] == 64
    assert latent["documented_dimension_contract_passed"] is False
    state = latent["state_recalculation"]
    assert state["train_sample_count"] == 350
    assert state["validation_sample_count"] == 75
    assert state["train_positive_count"] == 58
    assert state["validation_positive_count"] == 13
    assert state["latent_key_count"] == 229
    assert state["maximum_mean_absolute_difference"] <= 1.0e-12
    assert state["maximum_scale_absolute_difference"] <= 1.0e-12
    assert state[
        "maximum_normalized_feature_absolute_difference"
    ] <= 1.0e-12

    fixed = result["fixed_development_gate"]
    assert fixed["recalculated_gate_passed"] is True
    assert fixed["train"]["positive_recall"] == 1.0
    assert fixed["train"]["negative_specificity"] == 1.0
    assert fixed["train"]["minimum_positive_passing_margin"] == 0.4
    assert fixed["validation"]["positive_recall"] == 1.0
    assert fixed["validation"]["negative_specificity"] == 1.0
    assert fixed["validation"][
        "minimum_positive_passing_margin"
    ] == pytest.approx(0.2093188036155168)

    memory = result["memory_bias_and_overlap"]
    self_match = memory["train_self_match"]
    assert self_match["self_in_k_neighbour_inventory_count"] == 350
    assert self_match["self_exact_match_count"] == 350
    assert self_match["self_match_rate"] == 1.0
    loso = memory["leave_one_sample_out"]["metrics"]
    assert loso["positive_recall"] == 1.0
    assert loso["negative_specificity"] == pytest.approx(290 / 292)
    assert loso["minimum_positive_passing_margin"] == pytest.approx(
        0.06628310634382983
    )
    assert loso["brier_score"] == pytest.approx(0.006652708026781329)
    raw_logo = memory["leave_one_observable_group_out"][
        "raw_observable_key"
    ]
    latent_logo = memory["leave_one_observable_group_out"][
        "latent_exact_key"
    ]
    for logo in (raw_logo, latent_logo):
        assert logo["group_count"] == 229
        assert logo["duplicate_group_count"] == 115
        assert logo["maximum_group_size"] == 3
        assert logo["metrics"]["positive_recall"] == pytest.approx(56 / 58)
        assert logo["metrics"]["negative_specificity"] == pytest.approx(
            280 / 292
        )
        assert logo["metrics"]["brier_score"] == pytest.approx(
            0.03761043972744485
        )

    overlap = memory["validation_overlap"]
    assert overlap["validation_record_count"] == 75
    assert overlap["exact_raw_graph_key_overlap_count"] == 42
    assert overlap["exact_latent_overlap_count"] == 42
    assert overlap["nonexact_lt_1e_3_count"] == 20
    assert overlap["ge_1e_3_lt_1e_1_count"] == 10
    assert overlap["ge_1e_1_count"] == 3
    assert overlap["nearest_train_label_match_count"] == 75
    assert overlap["positive_exact_raw_graph_key_overlap_count"] == 12
    assert overlap["positive_exact_latent_overlap_count"] == 12
    assert overlap["expected_crosscheck_passed"] is True

    subsets = memory["validation_subsets"]
    assert subsets["without_exact_overlap"]["sample_count"] == 33
    assert subsets["without_exact_overlap"]["target_positive_count"] == 1
    assert subsets["without_exact_overlap"]["positive_recall"][
        "availability"
    ] == "unavailable"
    assert subsets["nearest_distance_ge_1e_3"]["sample_count"] == 13
    assert subsets["nearest_distance_ge_1e_3"]["positive_recall"][
        "value"
    ] is None
    assert subsets["nearest_distance_ge_1e_1"]["sample_count"] == 3
    assert subsets["nearest_distance_ge_1e_1"]["target_positive_count"] == 0
    assert subsets["nearest_distance_ge_1e_1"]["brier_score"][
        "availability"
    ] == "unavailable"

    boundary = result["data_usage_and_permissions"]
    assert boundary["all_permissions_false"] is True
    assert boundary["candidate_unregistered"] is True
    assert boundary["d3_permission_available"] is False
    assert boundary["d7_permission_available"] is False
    assert boundary["d6_semantic_payload_usage"][
        "test_payload_read_count"
    ] == 0
    assert boundary["d6_semantic_payload_usage"][
        "formal_holdout_payload_read_count"
    ] == 0
    conclusion = result["four_level_conclusion"]
    assert conclusion["fixed_development_gate"]["passed"] is True
    assert conclusion["independent_validation_and_generalization"][
        "passed"
    ] is False
    assert conclusion["admission"]["allowed"] is False
    assert conclusion["admission"]["rule_fallback_required"] is True

    outputs = write_d4_v5_candidate_audit_report(
        tmp_path / "v5-audit-output",
        result,
    )
    written = json.loads(outputs["json"].read_text(encoding="utf-8"))
    assert written["content_sha256"] == result["content_sha256"]
    report = outputs["markdown"].read_text(encoding="utf-8")
    assert "self-match 350/350" in report
    assert "实际 latent 维数均为 24" in report
    assert "记忆化开发对照" in report
    assert "不授予 D3/D7 权限" in report
    checksum_lines = outputs["sha256sums"].read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(checksum_lines) == 2


def test_v5_candidate_ordinary_artifact_tamper_fails_external_anchor(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    tampered = tmp_path / inputs.candidate_root.name
    shutil.copytree(inputs.candidate_root, tampered)
    with (tampered / "calibration_state.json").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(" ")

    with pytest.raises(
        D4V5CandidateAuditError,
        match="candidate_artifact_external_anchor_mismatch",
    ):
        audit_d4_v5_confidence_candidate(
            replace(inputs, candidate_root=tampered)
        )


def test_synchronously_self_resigned_candidate_still_fails_caller_anchor(
    tmp_path: Path,
) -> None:
    inputs = _inputs()
    tampered = tmp_path / inputs.candidate_root.name
    shutil.copytree(inputs.candidate_root, tampered)

    summary_path = tampered / "calibration_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["permissions"]["assist_enabled"] = True
    summary_content = dict(summary)
    summary_content.pop("content_sha256")
    summary["content_sha256"] = _canonical_sha256(summary_content)
    _write_json(summary_path, summary)

    manifest_path = tampered / "v5_confidence_candidate_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["permissions"]["assist_enabled"] = True
    manifest["calibration_summary_content_sha256"] = summary[
        "content_sha256"
    ]
    manifest["artifact_files"]["calibration_summary.json"] = sha256(
        summary_path.read_bytes()
    ).hexdigest()
    manifest_content = dict(manifest)
    manifest_content.pop("content_sha256")
    manifest["content_sha256"] = _canonical_sha256(manifest_content)
    _write_json(manifest_path, manifest)

    with pytest.raises(
        D4V5CandidateAuditError,
        match="candidate_manifest_file_external_anchor_mismatch",
    ):
        audit_d4_v5_confidence_candidate(
            replace(inputs, candidate_root=tampered)
        )


def test_known_overlap_diagnostic_disagreement_fails_closed() -> None:
    inputs = _inputs()
    expected = dict(inputs.expected_validation_diagnostics)
    expected["exact_latent_overlap_count"] = 41

    with pytest.raises(
        D4V5CandidateAuditError,
        match="validation_overlap_expected_crosscheck_mismatch",
    ):
        audit_d4_v5_confidence_candidate(
            replace(inputs, expected_validation_diagnostics=expected)
        )


def test_output_writer_refuses_existing_directory(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        write_d4_v5_candidate_audit_report(output, {"result": "unused"})
