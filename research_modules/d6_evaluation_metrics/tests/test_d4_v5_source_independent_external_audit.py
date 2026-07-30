from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

import d6_evaluation_metrics.d4_v5_source_independent_external_audit as audit_module
from d6_evaluation_metrics.d4_v5_source_independent_external_audit import (
    D4V5ExternalAuditError,
    D4V5ExternalAuditInputs,
    _score_feature,
    write_d4_v5_external_audit_report,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INPUT_SPEC = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/configs/"
    "d4_v5_source_independent_external_audit_m16n20_20260729.json"
)


def test_frozen_input_spec_has_disjoint_external_and_formal_seed_paths() -> None:
    payload = json.loads(INPUT_SPEC.read_text(encoding="utf-8"))
    assert payload["source_git_commit"] == (
        "63987592c216fbdb7e03d77183afc6e9f15748a2"
    )
    assert payload["prior_main_external_test_payload_read_count"] == 10
    assert payload["expected_hashes"]["labeled_dataset"] == (
        "ed2fd4b1a4d50ec80e5abdaa35a1470cec03d419665ae0e08b7c4339e9b8887e"
    )


def test_calibrator_score_uses_exact_and_inverse_distance_rules() -> None:
    state = {
        "feature_dimension": 2,
        "train_feature_mean": [0.0, 0.0],
        "train_feature_scale": [1.0, 1.0],
        "normalized_train_features": [[0.0, 0.0], [2.0, 0.0]],
        "train_labels": [False, True],
        "neighbour_count": 2,
        "exact_match_epsilon": 1.0e-12,
    }
    assert _score_feature((0.0, 0.0), state) == 0.0
    assert _score_feature((2.0, 0.0), state) == 1.0
    assert _score_feature((1.0, 0.0), state) == pytest.approx(0.5)


def test_input_hash_inventory_fails_closed(tmp_path: Path) -> None:
    directories = {
        name: tmp_path / name
        for name in (
            "source",
            "export",
            "dataset",
            "v4",
            "v5",
        )
    }
    for path in directories.values():
        path.mkdir()
    expected_names = set(
        json.loads(INPUT_SPEC.read_text(encoding="utf-8"))["expected_hashes"]
    )
    hashes = {name: "a" * 64 for name in expected_names}
    inputs = D4V5ExternalAuditInputs(
        repository_root=tmp_path,
        source_root=directories["source"],
        labeled_export_root=directories["export"],
        labeled_dataset_root=directories["dataset"],
        base_v4_root=directories["v4"],
        candidate_v5_root=directories["v5"],
        audit_id="test",
        evaluated_at_utc="2026-07-29T00:00:00Z",
        source_git_commit="1" * 40,
        prior_main_external_test_payload_read_count=10,
        expected_hashes=hashes,
    )
    incomplete = dict(inputs.expected_hashes)
    incomplete.pop("label_audit_content")
    with pytest.raises(
        D4V5ExternalAuditError,
        match="expected_hash_inventory_mismatch",
    ):
        replace(inputs, expected_hashes=incomplete)


def test_report_writer_preserves_unavailable_denominator_and_lf_csv(
    tmp_path: Path,
) -> None:
    result = {
        "status": "test",
        "seed_governance": {
            "formal_holdout_payload_read_count": 0,
            "semantic_payload_reads": {
                "d6_external_train": 1,
                "d6_external_validation": 1,
                "d6_external_test_nonformal": 1,
                "prior_main_external_test_nonformal": 1,
            },
        },
        "input_immutability": {
            "passed": True,
            "summary_method": "test",
            "before_sha256": {
                "base_v4_tree_sha256": "1" * 64,
                "candidate_v5_tree_sha256": "2" * 64,
            },
            "after_sha256": {
                "base_v4_tree_sha256": "1" * 64,
                "candidate_v5_tree_sha256": "2" * 64,
            },
            "input_mutation_count": 0,
            "mutated_inputs": [],
        },
        "anchors": {
            "actual_sha256": {
                "source_manifest_file": "a" * 64,
                "labeled_dataset": "b" * 64,
                "labeled_split": "c" * 64,
                "source_artifact_file": "d" * 64,
                "external_evidence_content": "e" * 64,
                "label_audit_content": "f" * 64,
                "base_v4_tree": "1" * 64,
                "base_v4_model_state": "2" * 64,
                "candidate_v5_tree": "3" * 64,
                "candidate_v5_state_file": "4" * 64,
            }
        },
        "observable_independence": {
            "base_v4_train_validation_frame_count": 1,
            "base_v4_train_validation_unique_key_count": 1,
            "external_frame_count": 3,
            "external_unique_key_count": 3,
            "exact_observable_key_overlap_count": 0,
        },
        "candidate_evaluation": {
            "fixed_gate": 0.6,
            "split_metrics": [
                {
                    "split": name,
                    "sample_count": 1,
                    "seed_count": 1,
                    "unique_observable_key_count": 1,
                    "rule_safe_positive_action_count": int(name == "train"),
                    "actor_derived_positive_count": 0,
                    "actor_derived_negative_count": 1,
                    "actor_executable_action_count": 0,
                    "actor_action_valid_count": 1,
                    "score_finite_count": 1,
                    "score_minimum": 0.0,
                    "score_mean": 0.0,
                    "score_maximum": 0.0,
                    "gate_pass_count": 0,
                    "positive_gate_pass_count": 0,
                    "negative_gate_pass_count": 0,
                    "negative_rejection_count": 1,
                    "positive_recall": {
                        "availability": "unavailable",
                        "value": None,
                        "denominator": 0,
                    },
                    "negative_specificity": {
                        "availability": "available",
                        "value": 1.0,
                        "denominator": 1,
                    },
                    "rule_fallback_count": 1,
                    "rule_fallback_rate": 1.0,
                    "nonformal_external_test_split": name == "test",
                }
                for name in ("train", "validation", "test")
            ],
            "aggregate": {
                "negative_specificity": {
                    "availability": "available",
                    "value": 1.0,
                    "denominator": 3,
                },
                "positive_recall": {
                    "availability": "unavailable",
                    "value": None,
                    "denominator": 0,
                },
            },
        },
    }
    output = tmp_path / "audit"
    files = write_d4_v5_external_audit_report(output, result)
    csv_bytes = files["csv"].read_bytes()
    csv_text = files["csv"].read_text(encoding="utf-8")
    report = files["markdown"].read_text(encoding="utf-8")
    assert b"\r" not in csv_bytes
    assert csv_bytes.endswith(b"\n")
    assert all(
        not line.rstrip(b"\n").endswith((b" ", b"\t"))
        for line in csv_bytes.splitlines(keepends=True)
    )
    assert "unavailable" in csv_text
    assert "正类召回不可评价" in report
    assert len(files["sha256sums"].read_text().splitlines()) == 3
    with pytest.raises(FileExistsError):
        write_d4_v5_external_audit_report(output, result)


def test_audit_fails_closed_when_input_changes_during_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directories = {
        name: tmp_path / name
        for name in ("source", "export", "dataset", "v4", "v5")
    }
    for path in directories.values():
        path.mkdir()
        (path / "frozen.txt").write_text("before", encoding="utf-8")
    expected_names = set(
        json.loads(INPUT_SPEC.read_text(encoding="utf-8"))["expected_hashes"]
    )
    inputs = D4V5ExternalAuditInputs(
        repository_root=tmp_path,
        source_root=directories["source"],
        labeled_export_root=directories["export"],
        labeled_dataset_root=directories["dataset"],
        base_v4_root=directories["v4"],
        candidate_v5_root=directories["v5"],
        audit_id="mutation-test",
        evaluated_at_utc="2026-07-29T00:00:00Z",
        source_git_commit="1" * 40,
        prior_main_external_test_payload_read_count=10,
        expected_hashes={name: "a" * 64 for name in expected_names},
    )

    monkeypatch.setattr(audit_module, "_load_d4_api", lambda _root: {})
    monkeypatch.setattr(
        audit_module,
        "_audit_hashes_and_bindings",
        lambda _inputs, _api: {
            "candidate_v5_payloads": {},
            "base_v4_manifest": {},
        },
    )
    monkeypatch.setattr(
        audit_module,
        "_audit_seed_governance",
        lambda _inputs, _anchors, _api: {},
    )
    monkeypatch.setattr(
        audit_module,
        "_load_frozen_candidate",
        lambda _inputs, _api: {},
    )

    def mutate_candidate(*_args: object, **_kwargs: object) -> dict[str, object]:
        (directories["v5"] / "frozen.txt").write_text(
            "changed",
            encoding="utf-8",
        )
        return {"_observable_keys": {}}

    monkeypatch.setattr(
        audit_module,
        "_evaluate_external_dataset",
        mutate_candidate,
    )
    monkeypatch.setattr(
        audit_module,
        "_audit_observable_key_independence",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        audit_module,
        "_audit_closed_permissions",
        lambda *_args, **_kwargs: {},
    )

    with pytest.raises(D4V5ExternalAuditError) as exc_info:
        audit_module.audit_d4_v5_source_independent_external(inputs)
    assert exc_info.value.code == "audit_input_mutated_during_execution"
    assert "candidate_v5_tree_sha256" in exc_info.value.detail
