from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.d4_v3_isolated_paired_audit import (
    D4V3IsolatedPairedAuditError,
    audit_d4_v3_isolated_paired_evidence,
    write_d4_v3_isolated_paired_audit,
)


SPEC_SHA = "1" * 64
CANDIDATE_SHA = "2" * 64
AUTHORITY_SHA = "3" * 64
LINEAGE_SHA = "4" * 64
IMPLEMENTATION_PATHS = (
    "research_modules/d3_assignment_planner/src/d3_assignment_planner/models.py",
    "research_modules/d3_assignment_planner/src/d3_assignment_planner/planner.py",
    "research_modules/d3_assignment_planner/src/d3_assignment_planner/regional_hint.py",
    (
        "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
        "region_resource_paired_intervention.py"
    ),
    (
        "research_modules/d4_distributed_fallback/d4_distributed_fallback/"
        "region_resource_v3_paired_intervention.py"
    ),
    (
        "research_modules/d6_evaluation_metrics/d6_evaluation_metrics/"
        "runtime_plan_outcome_join.py"
    ),
    (
        "research_modules/d7_proportional_guidance/d7_proportional_guidance/"
        "scalable_3d_guidance.py"
    ),
    "research_modules/scalable_3d_simulation/d4_v3_isolated_rollout.py",
    "research_modules/scalable_3d_simulation/d6_integration.py",
    "research_modules/scalable_3d_simulation/module_stack.py",
    "research_modules/scalable_3d_simulation/orchestrator.py",
)


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _advisory(
    *,
    seed: int,
    source_plan_id: str,
    reserve_ratio: float,
    reconnaissance_priority: float,
) -> dict[str, object]:
    return {
        "schema": "d4-region-resource-advisory-v1",
        "advisory_id": f"ADV-{seed}",
        "authority_digest": AUTHORITY_SHA,
        "seed": seed,
        "valid_from_s": 0.85,
        "valid_until_s": 2.35,
        "source_plan_versions": [[source_plan_id, 1]],
        "regions": [
            {
                "resource_quota_delta": 0,
                "reserve_ratio": reserve_ratio,
                "hold": False,
                "request_replan": False,
                "reconnaissance_priority": reconnaissance_priority,
                "source_version": {
                    "region_id": "region-000",
                },
            }
        ],
        "transfers": [],
    }


def _arm(
    *,
    seed: int,
    name: str,
    advisory: dict[str, object],
) -> dict[str, object]:
    treatment = name == "treatment"
    return {
        "schema": "d4-region-resource-v3-isolated-arm-decision-v1",
        "specification_id": "SPEC-V3",
        "specification_sha256": SPEC_SHA,
        "candidate_identity_sha256": CANDIDATE_SHA,
        "advisory_contract": advisory,
        "arm_evidence": {
            "advisory_payload_sha256": _canonical(advisory),
        },
        "raw_inference_completed": treatment,
        "runtime_gate_passed": treatment,
        "projection_passed": True,
        "isolated_treatment_influence_adopted": treatment,
        "assignment_authority_granted": False,
        "assist_authority_granted": False,
        "coalition_commit_authority_granted": False,
        "control_authority_granted": False,
        "degradation_authority_granted": False,
        "takeover_authority_granted": False,
        "production_runtime_ack_emitted": False,
    }


def _runtime_record(seed: int, *, successor: bool) -> dict[str, object]:
    source_plan_id = f"SOURCE-{seed}"
    reserve_ratio = 1.0 / 3.0 if successor else 0.0
    control_advisory = _advisory(
        seed=seed,
        source_plan_id=source_plan_id,
        reserve_ratio=reserve_ratio,
        reconnaissance_priority=1.0,
    )
    treatment_advisory = _advisory(
        seed=seed,
        source_plan_id=source_plan_id,
        reserve_ratio=reserve_ratio,
        reconnaissance_priority=0.9999,
    )
    control = _arm(
        seed=seed,
        name="control",
        advisory=control_advisory,
    )
    treatment = _arm(
        seed=seed,
        name="treatment",
        advisory=treatment_advisory,
    )
    decision = {
        "schema": "d4-region-resource-v3-isolated-paired-decision-v1",
        "seed": seed,
        "development_only": True,
        "formal_evaluation_authorized": False,
        "specification_id": "SPEC-V3",
        "specification_sha256": SPEC_SHA,
        "candidate_identity_sha256": CANDIDATE_SHA,
        "control": control,
        "treatment": treatment,
        "assignment_authority_granted": False,
        "assist_authority_granted": False,
        "coalition_commit_authority_granted": False,
        "control_authority_granted": False,
        "degradation_authority_granted": False,
        "takeover_authority_granted": False,
        "production_runtime_ack_emitted": False,
    }
    successor_id = f"SUCCESSOR-{seed}" if successor else None
    rejection = None if successor else "regional_hint_no_executable_successor"
    successor_metadata = {
        "regional_hint_advisory_id": treatment_advisory["advisory_id"],
        "regional_hint_successor_advisory_id": treatment_advisory["advisory_id"],
        "regional_hint_source_plan_id": source_plan_id,
        "regional_hint_successor_source_plan_id": source_plan_id,
        "regional_hint_source_plan_version": 1,
        "regional_hint_successor_source_plan_version": 1,
        "regional_hint_successor_state": (
            "successor_published" if successor else "no_successor"
        ),
        "regional_hint_successor_plan_available": successor,
        "regional_hint_successor_plan_id": successor_id,
        "regional_hint_successor_plan_version": 2 if successor else None,
        "regional_hint_successor_rejection_reason": rejection,
    }
    if successor:
        ack = {
            "available": True,
            "accepted": True,
            "fully_bound_to_guidance": True,
            "timestamp_s": 2.0,
            "payload_sha256": "5" * 64,
        }
        physical = {
            "available": True,
            "physical_execution_observed": True,
            "window_complete": True,
            "window_start_s": 1.0,
            "window_end_s": 2.35,
            "guidance_publication_count": 5,
            "matching_command_count": 10,
            "non_hold_control_count": 8,
            "hard_constraint_violation_count": 0,
        }
    else:
        ack = {
            "available": False,
            "accepted": False,
            "fully_bound_to_guidance": False,
        }
        physical = {
            "available": False,
            "physical_execution_observed": False,
            "window_complete": False,
        }
    return {
        "schema_version": "scalable3d-d4-v3-isolated-runtime-record-v1",
        "scope": "development_isolated_treatment_only",
        "seed": seed,
        "revision": 4,
        "evaluation_timestamp_s": 0.85,
        "expected_intervention_timestamp_s": 0.85,
        "expected_snapshot_lineage_sha256": LINEAGE_SHA,
        "observed_snapshot_lineage_sha256": LINEAGE_SHA,
        "trigger_passed": True,
        "trigger_rejection_reasons": [],
        "decision": decision,
        "isolated_consumption": {
            "attempted": True,
            "consumable": True,
            "source_plan_id": source_plan_id,
            "source_plan_version": 1,
            "view": {
                "consumable": True,
                "current_authority_digest": AUTHORITY_SHA,
                "advisory": treatment_advisory,
            },
        },
        "d3_successor": {
            "available": successor,
            "hint_applied": successor,
            "plan_id": successor_id,
            "plan_version": 2 if successor else None,
            "rejection_reason": rejection,
            "metadata": successor_metadata,
        },
        "runtime_ack": ack,
        "physical_window": physical,
        "assignment_authority_granted": False,
        "assist_authority_granted": False,
        "coalition_commit_authority_granted": False,
        "control_authority_granted": False,
        "degradation_authority_granted": False,
        "takeover_authority_granted": False,
        "production_runtime_ack_emitted": False,
    }


def _row(seed: int, *, successor: bool) -> dict[str, object]:
    record = _runtime_record(seed, successor=successor)
    return {
        "schema_version": "scalable3d-d4-v3-isolated-rollout-v2",
        "scope": "development_isolated_treatment_only",
        "seed": seed,
        "control_episode_id": f"CONTROL-{seed}",
        "treatment_episode_id": f"TREATMENT-{seed}",
        "same_initial_state": True,
        "same_exogenous_config": True,
        "worlds_isolated": True,
        "buses_isolated": True,
        "runtime_records": [record],
        "runtime_record_count": 1,
        "candidate_decision_count": 1,
        "raw_inference_count": 1,
        "runtime_gate_pass_count": 1,
        "projection_pass_count": 1,
        "isolated_adoption_count": 1,
        "d3_successor_count": int(successor),
        "accepted_runtime_ack_count": int(successor),
        "physical_execution_window_count": int(successor),
        "control_intercept_count": 0,
        "treatment_intercept_count": 0,
        "control_minimum_distance_m": 100.0 + seed,
        "treatment_minimum_distance_m": 100.0 + seed,
        "availability_reason": "D6 audit not attached",
        "paired_non_degradation_available": False,
        "positive_benefit_available": False,
        "production_runtime_ack_emitted": False,
        "runtime_authority_granted": False,
        "model_promotion_authority_granted": False,
    }


def _manifest(rows: list[dict[str, object]]) -> dict[str, object]:
    rejection_count = sum(
        not bool(row["d3_successor_count"]) for row in rows
    )
    rejection_counts = (
        {"regional_hint_no_executable_successor": rejection_count}
        if rejection_count
        else {}
    )
    implementation_hashes = {
        path: hashlib.sha256(path.encode("utf-8")).hexdigest()
        for path in IMPLEMENTATION_PATHS
    }
    return {
        "schema_version": "scalable3d-d4-v3-isolated-rollout-v2",
        "scope": "development_isolated_treatment_only",
        "created_at_utc": "2026-07-29T00:00:00Z",
        "scenario": "fixture",
        "target_count": 2,
        "resource_count": 2,
        "recon_count": 1,
        "region_count": 1,
        "duration_s": 3.2,
        "seeds": [row["seed"] for row in rows],
        "specification_id": "SPEC-V3",
        "specification_sha256": SPEC_SHA,
        "candidate_identity_sha256": CANDIDATE_SHA,
        "source_provenance": {
            "git_commit": "a" * 40,
            "git_commits": ["a" * 40],
            "git_commit_uniform": True,
            "repository_dirty": True,
            "episode_manifest_sha256": {
                str(row["seed"]): {
                    "control": hashlib.sha256(
                        f"control-{row['seed']}".encode("utf-8")
                    ).hexdigest(),
                    "treatment": hashlib.sha256(
                        f"treatment-{row['seed']}".encode("utf-8")
                    ).hexdigest(),
                }
                for row in rows
            },
            "implementation_file_sha256": implementation_hashes,
            "implementation_set_sha256": _canonical(
                implementation_hashes
            ),
        },
        "pair_count": len(rows),
        "raw_inference_seed_count": len(rows),
        "runtime_gate_pass_seed_count": len(rows),
        "isolated_adoption_seed_count": len(rows),
        "d3_successor_seed_count": sum(
            bool(row["d3_successor_count"]) for row in rows
        ),
        "accepted_runtime_ack_seed_count": sum(
            bool(row["accepted_runtime_ack_count"]) for row in rows
        ),
        "physical_execution_seed_count": sum(
            bool(row["physical_execution_window_count"]) for row in rows
        ),
        "d3_successor_rejection_reason_counts": rejection_counts,
        "isolated_consumption_rejection_reason_counts": {},
        "same_initial_state_count": len(rows),
        "same_exogenous_config_count": len(rows),
        "online_truth_use_count": 0,
        "finite_pair_count": len(rows),
        "production_permissions": {
            "runtime_ack": False,
            "assist": False,
            "assignment": False,
            "degradation": False,
            "takeover": False,
            "coalition_commit": False,
            "control": False,
            "model_promotion": False,
        },
        "d6_paired_non_degradation_available": False,
        "positive_benefit_available": False,
        "pair_summary_sha256": _canonical(rows),
    }


def _write_bundle(
    root: Path,
    rows: list[dict[str, object]],
    *,
    manifest: dict[str, object] | None = None,
) -> str:
    root.mkdir(parents=True, exist_ok=True)
    source_manifest = _manifest(rows) if manifest is None else manifest
    (root / "manifest.json").write_text(
        json.dumps(source_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "paired_evidence.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    (root / "D4_V3_ISOLATED_ROLLOUT_REPORT_CN.md").write_text(
        "# fixture\n",
        encoding="utf-8",
    )
    for row in rows:
        path = root / f"seed_{row['seed']}" / "paired_evidence.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(row, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    _rewrite_sha256sums(root)
    return _file_sha(root / "SHA256SUMS")


def _rewrite_sha256sums(root: Path) -> None:
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{_file_sha(path)}  {path.relative_to(root).as_posix()}\n"
            for path in files
        ),
        encoding="utf-8",
    )


def _fixture(root: Path) -> tuple[list[dict[str, object]], str]:
    rows = [_row(2007, successor=True), _row(2008, successor=False)]
    return rows, _write_bundle(root, rows)


def test_valid_bundle_keeps_development_ack_separate_from_production(
    tmp_path: Path,
) -> None:
    rows, digest = _fixture(tmp_path / "source")

    result = audit_d4_v3_isolated_paired_evidence(
        tmp_path / "source",
        expected_sha256sums_sha256=digest,
    )

    assert result["integrity"]["passed"] is True
    assert result["aggregate"]["d3_successor_seed_count"] == 1
    assert result["aggregate"]["development_runtime_ack_accepted_seed_count"] == 1
    assert result["aggregate"]["strict_successor_ack_d7_chain_seed_count"] == 0
    assert result["authority_boundary"]["production_runtime_authority"] is False
    assert result["aggregate"]["paired_non_degradation"]["availability"] == "available"
    assert result["aggregate"]["paired_non_degradation"]["value"]["overall"] is True
    assert result["aggregate"]["positive_benefit"]["availability"] == "unavailable"
    assert result["aggregate"]["positive_benefit"]["value"] is False
    seed_2007 = result["per_seed"][0]
    assert seed_2007["candidate_action"]["candidate_action_identifiable"] is False
    assert seed_2007["candidate_action"]["candidate_vs_rule_interpretation"] == (
        "candidate_executable_fields_equal_rule_control"
    )
    assert rows[0]["seed"] == 2007


def test_tampered_seed_file_is_rejected(tmp_path: Path) -> None:
    _, digest = _fixture(tmp_path / "source")
    path = tmp_path / "source" / "seed_2007" / "paired_evidence.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=digest,
        )

    assert captured.value.code == "source_artifact_sha256_mismatch"


def test_changed_sha256sums_requires_external_anchor_update(tmp_path: Path) -> None:
    _, digest = _fixture(tmp_path / "source")
    checksum = tmp_path / "source" / "SHA256SUMS"
    checksum.write_text(
        checksum.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=digest,
        )

    assert captured.value.code == "sha256sums_anchor_mismatch"


def test_missing_seed_file_is_rejected(tmp_path: Path) -> None:
    _, digest = _fixture(tmp_path / "source")
    (tmp_path / "source" / "seed_2008" / "paired_evidence.json").unlink()

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=digest,
        )

    assert captured.value.code == "sha256sums_artifact_unavailable"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (
            lambda rows, manifest: rows[0].__setitem__(
                "same_initial_state", False
            ),
            "paired_isolation_claim_failed",
        ),
        (
            lambda rows, manifest: rows[0].__setitem__(
                "runtime_authority_granted", True
            ),
            "source_claim_exceeds_evidence",
        ),
        (
            lambda rows, manifest: manifest.__setitem__(
                "online_truth_use_count", 1
            ),
            "online_truth_use_nonzero",
        ),
    ],
)
def test_semantic_tampering_fails_even_with_recomputed_checksums(
    tmp_path: Path,
    mutation,
    code: str,
) -> None:
    rows = [_row(2007, successor=True), _row(2008, successor=False)]
    manifest = _manifest(rows)
    mutation(rows, manifest)
    manifest["pair_summary_sha256"] = _canonical(rows)
    digest = _write_bundle(tmp_path / "source", rows, manifest=manifest)

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=digest,
        )

    assert captured.value.code == code


def test_duplicate_manifest_seed_is_rejected(tmp_path: Path) -> None:
    rows, _ = _fixture(tmp_path / "source")
    manifest_path = tmp_path / "source" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["seeds"] = [2007, 2007]
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    _rewrite_sha256sums(tmp_path / "source")

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=_file_sha(
                tmp_path / "source" / "SHA256SUMS"
            ),
        )

    assert captured.value.code == "duplicate_manifest_seed"
    assert len(rows) == 2


def test_nonfinite_json_value_is_rejected(tmp_path: Path) -> None:
    _, _ = _fixture(tmp_path / "source")
    jsonl = tmp_path / "source" / "paired_evidence.jsonl"
    text = jsonl.read_text(encoding="utf-8")
    jsonl.write_text(
        text.replace('"control_minimum_distance_m": 2107.0', '"control_minimum_distance_m": NaN', 1),
        encoding="utf-8",
    )
    _rewrite_sha256sums(tmp_path / "source")

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=_file_sha(
                tmp_path / "source" / "SHA256SUMS"
            ),
        )

    assert captured.value.code == "nonfinite_json_value"


def test_atomic_writer_refuses_to_overwrite(tmp_path: Path) -> None:
    _, digest = _fixture(tmp_path / "source")
    result = audit_d4_v3_isolated_paired_evidence(
        tmp_path / "source",
        expected_sha256sums_sha256=digest,
    )

    paths = write_d4_v3_isolated_paired_audit(tmp_path / "report", result)

    assert paths["json"].is_file()
    assert paths["markdown"].is_file()
    assert paths["sha256sums"].is_file()
    with pytest.raises(FileExistsError):
        write_d4_v3_isolated_paired_audit(tmp_path / "report", result)


def test_v2_manifest_requires_exact_source_provenance(tmp_path: Path) -> None:
    rows = [_row(2007, successor=True)]
    manifest = _manifest(rows)
    del manifest["source_provenance"]["implementation_file_sha256"][
        IMPLEMENTATION_PATHS[0]
    ]
    manifest["source_provenance"]["implementation_set_sha256"] = _canonical(
        manifest["source_provenance"]["implementation_file_sha256"]
    )
    digest = _write_bundle(tmp_path / "source", rows, manifest=manifest)

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=digest,
        )

    assert captured.value.code == "source_implementation_inventory_mismatch"


def test_legacy_v1_is_rejected_without_explicit_compatibility(
    tmp_path: Path,
) -> None:
    rows = [_row(2007, successor=True)]
    rows[0]["schema_version"] = "scalable3d-d4-v3-isolated-rollout-v1"
    manifest = _manifest(rows)
    manifest["schema_version"] = "scalable3d-d4-v3-isolated-rollout-v1"
    del manifest["source_provenance"]
    manifest["pair_summary_sha256"] = _canonical(rows)
    digest = _write_bundle(tmp_path / "source", rows, manifest=manifest)

    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_isolated_paired_evidence(
            tmp_path / "source",
            expected_sha256sums_sha256=digest,
        )

    assert captured.value.code == "source_schema_unsupported"


def test_positive_benefit_context_uses_manifest_and_seed_values(
    tmp_path: Path,
) -> None:
    rows = [_row(2007, successor=True)]
    manifest = _manifest(rows)
    manifest["duration_s"] = 7.75
    digest = _write_bundle(tmp_path / "source", rows, manifest=manifest)

    result = audit_d4_v3_isolated_paired_evidence(
        tmp_path / "source",
        expected_sha256sums_sha256=digest,
    )

    context = result["aggregate"]["positive_benefit"]["observed_context"]
    assert context["duration_s"] == 7.75
    assert context["zero_intercept_pair_count"] == 1
    assert context["equal_minimum_distance_pair_count"] == 1
