from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from d6_evaluation_metrics.d5_a3_v2_bc_model_audit import (
    AUTHORITY_KEYS,
    AuditInputs,
    AuditFailure,
    audit_d5_a3_v2_bc_candidate,
    enforce_fail_closed_claims,
    independent_quality_gate,
    require_all_authority_false,
    sha256_file,
    validate_selection_contract,
    verify_file_descriptor,
    write_report_bundle,
)


def _selection() -> dict[str, object]:
    return {
        "selection_contract": {
            "configuration_count": 1,
            "hyperparameter_search": False,
            "validation_used_for_best_epoch": True,
            "test_used_for_training_or_selection": False,
            "repeat_on_gate_failure": False,
        }
    }


@pytest.mark.parametrize("true_key", AUTHORITY_KEYS)
def test_authority_true_fails_closed(true_key: str) -> None:
    authority = {
        "assist": False,
        "promotion": False,
        "ppo": False,
        "assignment": False,
        "degradation": False,
        "runtime": False,
        "production": False,
        "control": False,
        "camera_command": False,
        "global_track_id_write": False,
    }
    authority[true_key] = True
    with pytest.raises(AuditFailure, match=f"authority_not_false:{true_key}"):
        require_all_authority_false(authority)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("configuration_count", 2),
        ("hyperparameter_search", True),
        ("test_used_for_training_or_selection", True),
        ("repeat_on_gate_failure", True),
    ],
)
def test_multiple_configuration_or_test_tuning_fails_closed(
    key: str, value: object
) -> None:
    config = _selection()
    config["selection_contract"][key] = value  # type: ignore[index]
    with pytest.raises(AuditFailure, match="multiple_configurations_or_test_tuning"):
        validate_selection_contract(config)


def test_zero_minority_recall_cannot_be_hidden_by_accuracy() -> None:
    gate = independent_quality_gate(
        {
            "exact_action_accuracy": 0.999,
            "per_intent_recall": {
                "observe_target": 0.0,
                "search_sector": 0.0,
                "hold": 1.0,
                "reacquire": 1.0,
            },
            "macro_intent_recall": 0.5,
            "expected_calibration_error": 0.01,
            "feature_boundary_ood_fraction": 0.0,
            "per_camera_role_exact_action_accuracy": {
                "interceptor": 0.99,
                "recon": 0.99,
            },
        }
    )
    assert gate["passed"] is False
    assert gate["paired_shadow_allowed"] is False
    assert gate["failure_reasons"] == [
        "intent_recall_below_0.25:observe_target",
        "intent_recall_below_0.25:search_sector",
    ]


def test_zero_minority_recall_rejects_claimed_pass() -> None:
    gate = {"passed": False}
    with pytest.raises(AuditFailure, match="failed_quality_gate_claimed_as_passed"):
        enforce_fail_closed_claims(
            gate,
            {"development_model_precheck_passed": True, "paired_shadow_allowed": True},
        )


def test_cache_hash_tamper_fails_closed(tmp_path) -> None:
    path = tmp_path / "candidate_count.u2"
    path.write_bytes(b"\x01\x00")
    descriptor = {
        "size_bytes": 2,
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }
    verify_file_descriptor(path, descriptor)
    path.write_bytes(b"\x02\x00")
    with pytest.raises(AuditFailure, match="file_sha256_mismatch"):
        verify_file_descriptor(path, descriptor)


def test_real_development_candidate_recomputes_and_fails_quality_gate(
    tmp_path: Path,
) -> None:
    repo = Path(__file__).resolve().parents[3]
    corpus = (
        repo
        / "research_modules/scalable_3d_simulation/outputs/"
        "d5_a3_source_independent_point_mass_v2_20260801_d7bf890"
    )
    candidate = (
        repo
        / "research_modules/d5_terminal_association/outputs/"
        "a3_v2_active_vision_bc_development_20260801_d7bf890"
    )
    result = audit_d5_a3_v2_bc_candidate(
        AuditInputs(
            repo_root=repo,
            candidate_root=candidate,
            frozen_config=repo
            / "research_modules/d5_terminal_association/configs/"
            "a3_v2_active_vision_bc_development_20260801.json",
            candidate_evidence=repo
            / "research_modules/d5_terminal_association/results/"
            "a3_v2_active_vision_bc_development_candidate_evidence_20260801.json",
            generation_plan=corpus / "generation_plan.json",
            generation_summary=corpus / "generation_summary.json",
            training_seed_registry=corpus / "training_seed_registry.json",
        )
    )
    metrics = result["recomputation"]["metrics"]
    assert metrics["sample_count"] == 40133
    assert metrics["exact_action_accuracy"] == pytest.approx(0.9599581391872025)
    assert metrics["macro_intent_recall"] == pytest.approx(0.49550658912024403)
    assert metrics["expected_calibration_error"] == pytest.approx(0.3682385338)
    assert metrics["per_intent_recall"]["observe_target"] == 0.0
    assert metrics["per_intent_recall"]["search_sector"] == 0.0
    assert result["quality_gate"]["passed"] is False
    assert result["paired_shadow_allowed"] is False
    assert result["inputs"]["repo_root"] == "."
    assert all(not Path(value).is_absolute() for value in result["inputs"].values())
    implementation = result["auditor"]["implementation"]
    implementation_path = repo / implementation["path"]
    assert implementation_path.resolve() == Path(audit_d5_a3_v2_bc_candidate.__code__.co_filename).resolve()
    assert implementation["sha256"] == sha256_file(implementation_path)
    assert result["integrity"]["auditor_implementation_sha256"] == implementation[
        "sha256"
    ]

    output_dir = tmp_path / "report"
    write_report_bundle(result, output_dir)
    checksum_entries = {
        filename: digest
        for digest, filename in (
            line.split("  ")
            for line in (output_dir / "SHA256SUMS").read_text(
                encoding="ascii"
            ).splitlines()
        )
    }
    assert checksum_entries == {
        "audit.json": sha256_file(output_dir / "audit.json"),
        "REPORT_CN.md": sha256_file(output_dir / "REPORT_CN.md"),
    }
