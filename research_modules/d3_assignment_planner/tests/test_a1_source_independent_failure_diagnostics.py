from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d3_assignment_planner.a1_source_independent_failure_diagnostics import (
    A1FailureDiagnosticError,
    A1FailureDiagnosticInputs,
    _find_forbidden_identity_keys,
    _validate_csv,
    _validate_v3_seed_registry,
    _verify_result_inventory,
    diagnose_a1_source_independent_v2,
    write_a1_failure_diagnostics,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = REPOSITORY_ROOT / "research_modules/d3_assignment_planner"
RESULT_DIR = MODULE_ROOT / "results/a1_source_independent_evaluation_v2_20260731"
CONTRACT = MODULE_ROOT / "configs/a1_source_independent_evaluation_contract_v2.json"
BUNDLE = MODULE_ROOT / "results/a1_assignment_aware_development_v1_20260730/bundle"
D6_AUDIT = (
    REPOSITORY_ROOT
    / "research_modules/d6_evaluation_metrics/reports/"
    "D3_A1_SOURCE_INDEPENDENT_V2_EXTERNAL_AUDIT_20260731/audit.json"
)
MAIN_REPORT = REPOSITORY_ROOT / "subagent_reviews/MAIN_IMPLEMENTATION_GAP_AUDIT.md"
DATA_REQUEST = (
    MODULE_ROOT / "configs/a1_source_independent_v3_development_data_request_v1.json"
)
SEED_REGISTRY = (
    MODULE_ROOT / "configs/a1_source_independent_v3_seed_exclusion_registry_v1.json"
)


def _inputs() -> A1FailureDiagnosticInputs:
    return A1FailureDiagnosticInputs(
        repository_root=REPOSITORY_ROOT,
        result_dir=RESULT_DIR,
        contract_path=CONTRACT,
        bundle_dir=BUNDLE,
        d6_audit_path=D6_AUDIT,
        main_report_path=MAIN_REPORT,
        data_request_path=DATA_REQUEST,
        seed_registry_path=SEED_REGISTRY,
        analysis_id="unit-d3-a1-v2-failure-attribution",
        analyzed_at_utc="2026-08-01T00:00:00Z",
    )


@pytest.fixture(scope="module")
def official_result():
    return diagnose_a1_source_independent_v2(_inputs())


def test_official_v2_is_reloaded_without_authority(official_result) -> None:
    summary = official_result.summary
    frozen = summary["frozen_v2_confirmation"]
    assert frozen["episode_count"] == 100
    assert frozen["frame_count"] == 292
    assert frozen["unique_seed_count"] == 100
    assert (frozen["seed_minimum"], frozen["seed_maximum"]) == (20000, 20099)
    assert frozen["projection_rejection_count"] == 94
    assert frozen["fallback_exact_r0_count"] == 94
    assert frozen["formal_seed_read_count"] == 0
    assert frozen["forbidden_identity_key_count"] == 0
    assert frozen["model_authority_output_count"] == 0
    assert not any(summary["permissions"].values())
    assert summary["scope"]["training_count"] == 0
    assert summary["scope"]["model_invocation_count"] == 0
    assert summary["scope"]["new_bundle_write_count"] == 0


def test_test_positive_failure_attribution_is_bounded_by_observability(
    official_result,
) -> None:
    result = official_result.summary["test_positive_failure_attribution"]
    assert result["positive_denominator"] == 25
    assert result["effective_teacher_exact_match_numerator"] == 0
    assert result["candidate_teacher_exact_match_numerator"] == 0
    assert result["exclusive_observable_pathway_counts"] == {
        "candidate_selection_mismatch_non_ood": 16,
        "feature_ood_rule_fallback": 9,
    }
    assert result["projection_rejection_cooccurrence_count"] == 22
    assert result["projection_only_failure_count"] == 0
    assert result["strict_root_cause_denominator"] == 9
    assert result["teacher_candidate_reachability_unavailable_count"] == 25
    assert result["per_edge_model_ranking_unavailable_count"] == 25
    assert result["demand_structure_attribution_unavailable_count"] == 25


def test_stratification_covers_required_dimensions(official_result) -> None:
    dimensions = official_result.summary["stratification"]
    assert {
        "source_split",
        "scenario",
        "configured_scale",
        "class_label",
        "candidate_availability",
        "ood",
        "rejection_reason",
        "anonymous_target_count",
        "anonymous_resource_count",
        "teacher_binding_change_count",
        "candidate_teacher_difference_count",
    }.issubset(dimensions)
    assert sum(item["frame_count"] for item in dimensions["source_split"].values()) == 292
    assert dimensions["class_label"]["positive"]["frame_count"] == 110
    assert dimensions["class_label"]["negative"]["frame_count"] == 182


def test_v3_request_has_no_seed_allocation_or_generation_authority(
    official_result,
) -> None:
    request = official_result.summary["v3_development_data_request"]
    exclusion = request["seed_exclusion"]
    assert request["requested_episode_count"] == 300
    assert request["requested_unique_seed_count"] == 300
    assert request["requested_cell_count"] == 15
    assert request["minimum_positive_frame_count"] == 900
    assert request["minimum_negative_frame_count"] == 900
    assert request["minimum_hard_negative_frame_count"] == 450
    assert request["data_generated"] is False
    assert request["model_trained"] is False
    assert request["bundle_written"] is False
    assert request["generation_authorized"] is False
    assert exclusion["known_forbidden_seed_count"] == 220
    assert exclusion["assigned_seed_count"] == 0
    assert exclusion["training_seed_reuse_allowed"] is False
    assert exclusion["formal_seed_reuse_allowed"] is False
    assert exclusion["v2_evaluation_seed_reuse_allowed"] is False
    assert exclusion["other_registered_d3_seed_reuse_allowed"] is False


def test_result_checksum_rewrite_cannot_replace_official_frozen_result(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "result"
    shutil.copytree(RESULT_DIR, copied)
    aggregate = copied / "aggregate.json"
    payload = json.loads(aggregate.read_text(encoding="utf-8"))
    payload["tampered"] = True
    aggregate.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    hashes = {}
    for path in copied.iterdir():
        if path.name != "SHA256SUMS":
            hashes[path.name] = sha256(path.read_bytes()).hexdigest()
    (copied / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items())),
        encoding="ascii",
    )
    with pytest.raises(
        A1FailureDiagnosticError,
        match="result_sha256sums_file_mismatch|result_file_sha256_mismatch",
    ):
        _verify_result_inventory(copied)


def test_csv_rewrite_is_detected_even_without_result_manifest_check(
    tmp_path: Path,
) -> None:
    rows = tuple(
        json.loads(line)
        for line in (RESULT_DIR / "per_frame_evaluation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    copied = tmp_path / "per_frame.csv"
    shutil.copy2(RESULT_DIR / "per_frame_evaluation.csv", copied)
    with copied.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = tuple(reader.fieldnames or ())
        csv_rows = list(reader)
    csv_rows[0]["negative_exact_r0"] = "0"
    with copied.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows)
    with pytest.raises(A1FailureDiagnosticError, match="csv_jsonl_mismatch"):
        _validate_csv(copied, rows)


def test_identity_keys_are_rejected_by_diagnostic_scan() -> None:
    payload = {
        "anonymous": {"target_truth_id": "truth-1"},
        "safe": {"observed_anonymous_target_count": 2},
    }
    assert _find_forbidden_identity_keys(payload) == (
        "anonymous.target_truth_id",
    )


def test_v3_registry_rejects_any_assigned_or_reused_seed() -> None:
    registry = json.loads(SEED_REGISTRY.read_text(encoding="utf-8"))
    registry["requested_allocation"]["assigned_seed_values"] = [1000]
    registry["requested_allocation"]["allocation_status"] = "allocated"
    with pytest.raises(
        A1FailureDiagnosticError,
        match="v3_seed_allocation_must_remain_unassigned",
    ):
        _validate_v3_seed_registry(registry)


def test_writer_creates_checksummed_diagnostics_only(
    tmp_path: Path,
    official_result,
) -> None:
    output = tmp_path / "diagnostics"
    paths = write_a1_failure_diagnostics(output, official_result)
    assert set(path.name for path in output.iterdir()) == {
        "diagnostics.json",
        "per_frame_attribution.jsonl",
        "per_frame_attribution.csv",
        "A1_V2_FAILURE_ATTRIBUTION_AND_V3_REQUEST_CN.md",
        "SHA256SUMS",
    }
    assert all(path.is_file() for path in paths.values())
    manifest = {}
    for line in paths["checksums"].read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        manifest[name] = digest
    assert len(manifest) == 4
    for name, digest in manifest.items():
        assert sha256((output / name).read_bytes()).hexdigest() == digest
    with pytest.raises(A1FailureDiagnosticError, match="diagnostic_output_already_exists"):
        write_a1_failure_diagnostics(output, official_result)
