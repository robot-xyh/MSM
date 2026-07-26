from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from d6_evaluation_metrics.d3_a1_external_audit import (
    D3_A1_EXTERNAL_AUDIT_SCHEMA_VERSION,
    audit_d3_a1_external_evidence,
    load_d3_a1_external_audit_inputs,
    write_d3_a1_external_audit_report,
)
from d6_evaluation_metrics.d4_a2_external_audit import (
    D4_A2_EXTERNAL_AUDIT_SCHEMA_VERSION,
    audit_d4_a2_external_evidence,
    load_d4_a2_external_audit_inputs,
    write_d4_a2_external_audit_report,
)
from d6_evaluation_metrics.learning_module_external_audit import (
    D3_A1_PROFILE,
    D4_A2_PROFILE,
    MODULE_IMPLEMENTATION_EVIDENCE_SCHEMA_VERSION,
    LearningModuleAuditProfile,
    LearningModuleExternalAuditError,
    LearningModuleExternalAuditInputs,
)
from d6_evaluation_metrics.learning_scope_formal_audit import (
    LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION,
)


_SOURCE_COMMIT = "a" * 40


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _with_content(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("content_sha256", None)
    result["content_sha256"] = _sha_json(result)
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_checksums(path: Path, files: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{_sha_file(item)}  {item.name}\n" for item in files),
        encoding="ascii",
    )


@dataclass
class _Fixture:
    root: Path
    profile: LearningModuleAuditProfile
    spec: dict[str, Any]
    paths: dict[str, Path]

    def inputs(self) -> LearningModuleExternalAuditInputs:
        return LearningModuleExternalAuditInputs.from_mapping(
            deepcopy(self.spec),
            repository_root=self.root,
            profile_key=self.profile.key,
        )

    def refresh_artifact(self, name: str) -> None:
        self.spec["artifacts"][name]["sha256"] = _sha_file(
            self.paths[name]
        )

    def read_json(self, name: str) -> dict[str, Any]:
        return json.loads(self.paths[name].read_text(encoding="utf-8"))

    def write_json(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        content_hash: bool = False,
    ) -> None:
        if content_hash:
            payload = _with_content(payload)
        _write_json(self.paths[name], payload)
        self.refresh_artifact(name)

    def refresh_formal(self, payload: dict[str, Any]) -> None:
        self.write_json("formal_scope_audit", payload)
        _write_checksums(
            self.paths["formal_scope_checksums"],
            [self.paths["formal_scope_audit"]],
        )
        self.refresh_artifact("formal_scope_checksums")

    def write_spec(self, path: Path) -> Path:
        _write_json(path, self.spec)
        return path


def _make_source(root: Path, profile: LearningModuleAuditProfile) -> tuple[Path, dict[str, str], str]:
    source = root / "module_source"
    source.mkdir(parents=True)
    hashes: dict[str, str] = {}
    for name in profile.source_files:
        path = source / name
        path.write_text(f"# fixture {profile.role} {name}\n", encoding="ascii")
        hashes[name] = _sha_file(path)
    return source, hashes, _sha_json(dict(sorted(hashes.items())))


def _seed_split() -> dict[str, list[int]]:
    return {
        "train": list(range(0, 60)),
        "validation": list(range(60, 80)),
        "test": list(range(80, 100)),
    }


def _d3_candidate(root: Path) -> tuple[dict[str, Path], dict[str, Any]]:
    paths: dict[str, Path] = {}
    payload_path = root / "candidate" / "frames.jsonl"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_text('{"fixture":"d3-data"}\n', encoding="ascii")
    payload_sha = _sha_file(payload_path)
    split = _seed_split()
    dataset = {
        "schema_version": "d3_learning_dataset_v2",
        "frames_sha256": payload_sha,
        "split_hash": "3" * 64,
        "split_seed_values": split,
        "unique_seed_count": 100,
    }
    dataset_path = root / "candidate" / "dataset_manifest.json"
    _write_json(dataset_path, dataset)
    dataset_file_sha = _sha_file(dataset_path)

    full = _with_content(
        {
            "schema_version": "d3.assignment-full-sample-audit.v1",
            "audit": {"passed": True, "violation_count": 0},
            "artifact_integrity": {
                "source_artifacts_unchanged": True,
                "formal_source_data_modified": False,
                "dataset_manifest_frames_binding_valid": True,
            },
            "actual_bindings": {
                "dataset_manifest_sha256": dataset_file_sha,
                "dataset_frames_sha256": payload_sha,
                "dataset_split_hash": dataset["split_hash"],
                "source_git_commit": _SOURCE_COMMIT,
            },
        }
    )
    full_path = root / "candidate" / "full_sample_audit.json"
    _write_json(full_path, full)

    weights_path = root / "candidate" / "state_dict.pt"
    weights_path.write_bytes(b"d3-fixture-weights")
    weights_sha = _sha_file(weights_path)
    bundle = {
        "bundle_schema_version": "d3_learning_model_bundle_v3",
        "dataset_frames_sha256": payload_sha,
        "split_hash": dataset["split_hash"],
        "state_dict": {
            "file": "state_dict.pt",
            "sha256": weights_sha,
        },
        "provenance": {
            "dataset_manifest_sha256": dataset_file_sha,
            "repository_git_commit": _SOURCE_COMMIT,
        },
        "admission": {
            "stage": "development",
            "allowed_modes": ["shadow"],
            "assist_authorized": False,
            "external_holdout_seed_values": list(range(1000, 1020)),
        },
        "promotion_manifest": {
            "promotion_status": "unavailable",
            "unseen_seed_count": 0,
        },
    }
    bundle_path = root / "candidate" / "manifest.json"
    _write_json(bundle_path, bundle)
    paths.update(
        dataset_manifest=dataset_path,
        dataset_payload=payload_path,
        full_sample_audit=full_path,
        bundle_manifest=bundle_path,
        bundle_weights=weights_path,
    )
    return paths, {
        "dataset_manifest_sha256": dataset_file_sha,
        "dataset_content_sha256": payload_sha,
        "dataset_split_sha256": dataset["split_hash"],
        "bundle_manifest_sha256": _sha_file(bundle_path),
        "bundle_weights_sha256": weights_sha,
    }


def _d4_candidate(root: Path) -> tuple[dict[str, Path], dict[str, Any]]:
    paths: dict[str, Path] = {}
    split_values = _seed_split()
    split = {
        "schema": "d4-region-learning-seed-split-v1",
        "split_sha256": "4" * 64,
        "train_seeds": split_values["train"],
        "validation_seeds": split_values["validation"],
        "test_seeds": split_values["test"],
        "unique_seed_count": 100,
    }
    dataset_content = {
        "schema": "d4-region-learning-dataset-v1",
        "created_at_utc": "2026-07-26T00:00:00Z",
        "feature_semantics": {},
        "target_semantics": {},
        "reward_semantics": {},
        "split": split,
        "availability": {},
        "episodes": [],
    }
    dataset_sha = _sha_json(dataset_content)
    dataset = {
        **dataset_content,
        "dataset_sha256": dataset_sha,
        "dataset_id": f"d4-region-learning-dataset-{dataset_sha}",
    }
    dataset_path = root / "candidate" / "training_dataset_manifest.json"
    _write_json(dataset_path, dataset)
    dataset_file_sha = _sha_file(dataset_path)

    full = _with_content(
        {
            "schema": "d4-region-resource-full-sample-admission-audit-v1",
            "audit": {"passed": True, "violation_count": 0},
            "artifact_integrity": {
                "formal": {
                    "artifact_inventory_exact": True,
                    "source_unchanged_during_audit": True,
                    "episode_sha256_mismatch_count": 0,
                },
                "formal_900_episode_dataset_modified": False,
            },
            "actual_bindings": {
                "formal_dataset_sha256": dataset_sha,
                "formal_manifest_sha256": dataset_file_sha,
                "formal_source_git_commit": _SOURCE_COMMIT,
            },
            "formal_corpus": {
                "canonical": {
                    "binding": {
                        "reserved_evaluation_seeds": list(
                            range(1000, 1020)
                        )
                    }
                }
            },
        }
    )
    full_path = root / "candidate" / "full_sample_audit.json"
    _write_json(full_path, full)

    weights_path = root / "candidate" / "state_dict.pt"
    weights_path.write_bytes(b"d4-fixture-weights")
    weights_sha = _sha_file(weights_path)
    bundle = {
        "schema": "d4-region-resource-model-bundle-v2",
        "model_version": "d4-fixture-v1",
        "state_dict_file": "state_dict.pt",
        "state_dict_sha256": weights_sha,
        "training_manifest_sha256": dataset_file_sha,
        "training_dataset_sha256": dataset_sha,
        "training_split_sha256": split["split_sha256"],
        "lifecycle_stage": "development",
        "maximum_advisor_mode": "shadow",
        "action_diversity_sufficient": False,
        "strategy_capability_claim_allowed": False,
    }
    bundle_path = root / "candidate" / "manifest.json"
    _write_json(bundle_path, bundle)
    readiness = {
        "schema": "d4-region-bc-model-readiness-v1",
        "model_version": bundle["model_version"],
        "state_dict_sha256": weights_sha,
        "training_dataset_sha256": dataset_sha,
        "training_split_sha256": split["split_sha256"],
        "final_holdout_evaluated_seed_count": 0,
        "assist_eligible": False,
    }
    readiness_path = root / "candidate" / "model_readiness.json"
    _write_json(readiness_path, readiness)
    paths.update(
        dataset_manifest=dataset_path,
        full_sample_audit=full_path,
        bundle_manifest=bundle_path,
        bundle_weights=weights_path,
        model_readiness=readiness_path,
    )
    return paths, {
        "dataset_manifest_sha256": dataset_file_sha,
        "dataset_content_sha256": dataset_sha,
        "dataset_split_sha256": split["split_sha256"],
        "bundle_manifest_sha256": _sha_file(bundle_path),
        "bundle_weights_sha256": weights_sha,
    }


def _formal_scope(
    profile: LearningModuleAuditProfile,
    *,
    bundle_manifest_sha256: str,
    source_commit: str,
    seed_values: list[int] | None = None,
) -> dict[str, Any]:
    seeds = list(range(1000, 1020)) if seed_values is None else seed_values
    cells: list[dict[str, Any]] = []
    r0_cells: list[dict[str, Any]] = []
    pairs: list[dict[str, Any]] = []
    for seed in seeds:
        key = f"nominal|5|{seed}"
        cell_id = f"{profile.variant}-{seed}"
        cells.append(
            {
                "variant": profile.variant,
                "scenario": "nominal",
                "scale": 5,
                "seed": seed,
                "comparison_key": key,
                "cell_id": cell_id,
                "evidence_status": "accepted",
                "assist_adoption_status": "actual_assist_adopted",
                "online_truth_status": "zero_verified",
                "physical_result_status": "available",
                "learning_evidence": {
                    "status": "preflight_and_episode_consistent",
                    "required_components": [profile.component],
                },
                "failure_reasons": [],
            }
        )
        r0_cells.append(
            {
                "variant": "R0",
                "scenario": "nominal",
                "scale": 5,
                "seed": seed,
                "comparison_key": key,
                "cell_id": f"R0-{seed}",
                "evidence_status": "accepted",
                "failure_reasons": [],
            }
        )
        pairs.append(
            {
                "comparison_key": key,
                "variant": profile.variant,
                "learned_cell_id": cell_id,
                "r0_cell_id": f"R0-{seed}",
                "availability": "available",
                "unavailable_reason": None,
                "non_degraded": True,
                "failure_reasons": [],
                "metric_comparisons": {
                    "intercepted_target_count": {
                        "availability": "available",
                        "non_degraded": True,
                        "required": True,
                    },
                    "offline_proximity_unique_target_count": {
                        "availability": "available",
                        "non_degraded": True,
                        "required": True,
                    },
                },
            }
        )
    count = len(cells)
    return {
        "schema_version": LEARNING_SCOPE_FORMAL_AUDIT_SCHEMA_VERSION,
        "verdict": "pass",
        "fail_closed": False,
        "formal_evidence_eligible": True,
        "evidence_admission_allowed": True,
        "model_promotion": {
            "availability": "unavailable",
            "allowed": False,
        },
        "default_control_path_modified": False,
        "learned_scope": {
            "source_git_commit": source_commit,
            "scope_variants": [profile.variant],
            "expected_cell_count": count,
            "accepted_cell_count": count,
            "formal_evidence_eligible": True,
            "bundle_binding_status": "available_and_valid",
            "scope_completeness_status": "complete",
            "bundle_binding": {
                "components": {
                    profile.component: {
                        "available": True,
                        "manifest_sha256_match": True,
                        "tree_sha256_match": True,
                        "file_count_match": True,
                        "total_size_bytes_match": True,
                        "actual": {
                            "manifest_sha256": bundle_manifest_sha256,
                        },
                    }
                }
            },
            "cells": cells,
            "blockers": [],
        },
        "r0_scopes": [
            {
                "label": "same-key-r0",
                "cells": r0_cells,
                "blockers": [],
            }
        ],
        "r0_pairing": {
            "availability": "available",
            "expected_pair_count": count,
            "available_pair_count": count,
            "non_degraded_pair_count": count,
            "all_required_pairs_available": True,
            "all_required_pairs_non_degraded": True,
            "pairs": pairs,
            "blockers": [],
        },
        "blockers": [],
    }


def _make_fixture(
    root: Path,
    profile: LearningModuleAuditProfile,
) -> _Fixture:
    root.mkdir(parents=True)
    source, source_hashes, implementation_sha = _make_source(root, profile)
    if profile.key == D3_A1_PROFILE.key:
        paths, candidate = _d3_candidate(root)
    else:
        paths, candidate = _d4_candidate(root)

    implementation = _with_content(
        {
            "schema_version": (
                MODULE_IMPLEMENTATION_EVIDENCE_SCHEMA_VERSION
            ),
            "role": profile.role,
            "source_git_commit": _SOURCE_COMMIT,
            "source_files": source_hashes,
            "implementation_sha256": implementation_sha,
            **candidate,
        }
    )
    implementation_path = (
        root / "evidence" / "implementation_evidence.json"
    )
    _write_json(implementation_path, implementation)
    paths["implementation_evidence"] = implementation_path

    formal = _formal_scope(
        profile,
        bundle_manifest_sha256=candidate["bundle_manifest_sha256"],
        source_commit=_SOURCE_COMMIT,
    )
    formal_path = root / "evidence" / "learning_scope_formal_audit.json"
    _write_json(formal_path, formal)
    checksums_path = root / "evidence" / "SHA256SUMS"
    _write_checksums(checksums_path, [formal_path])
    paths["formal_scope_audit"] = formal_path
    paths["formal_scope_checksums"] = checksums_path

    spec = {
        "schema_version": profile.input_schema_version,
        "audit_id": f"{profile.key}-positive-fixture",
        "evaluated_at_utc": "2026-07-26T00:00:00Z",
        "formal_profile_version": profile.formal_profile_version,
        "module_source_dir": source.relative_to(root).as_posix(),
        "expected_current_implementation_sha256": implementation_sha,
        "artifacts": {
            name: {
                "path": paths[name].relative_to(root).as_posix(),
                "sha256": _sha_file(paths[name]),
            }
            for name in profile.artifact_names
        },
    }
    return _Fixture(root=root, profile=profile, spec=spec, paths=paths)


def _audit(fixture: _Fixture) -> dict[str, Any]:
    if fixture.profile.key == D3_A1_PROFILE.key:
        return audit_d3_a1_external_evidence(fixture.inputs())
    return audit_d4_a2_external_evidence(fixture.inputs())


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_positive_contract_fixture_passes_without_granting_authority(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / profile.key, profile)

    result = _audit(fixture)

    expected_schema = (
        D3_A1_EXTERNAL_AUDIT_SCHEMA_VERSION
        if profile.key == D3_A1_PROFILE.key
        else D4_A2_EXTERNAL_AUDIT_SCHEMA_VERSION
    )
    assert result["schema_version"] == expected_schema
    assert result["status"] == "pass"
    assert result["audit_passed"] is True
    assert result["blocker_codes"] == []
    contract = result["consumer_contract"]
    assert contract["role"] == profile.role
    assert contract["variant"] == profile.variant
    assert (
        contract["adoption_evidence_kind"]
        == profile.adoption_evidence_kind
    )
    assert (
        contract["adoption_source_metric"]
        == profile.adoption_source_metric
    )
    assert contract["unseen_seed_count"] == 20
    assert contract["formal_episode_count"] == 20
    assert contract["actual_adoption_count"] == 20
    assert contract["physical_window_count"] == 20
    assert contract["unique_r0_pair_count"] == 20
    assert contract["paired_non_degraded_count"] == 20
    assert contract["safety_hard_constraint_passed"] is True
    assert contract["formal_scope_checksum_verified"] is True
    assert all(
        value is False
        for value in result["authority"].values()
        if isinstance(value, bool)
    )


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_missing_formal_scope_is_unavailable_without_zero_fill(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / profile.key, profile)
    fixture.paths["formal_scope_audit"].unlink()

    result = _audit(fixture)

    assert result["status"] == "fail_closed"
    assert "artifact_missing.formal_scope_audit" in result["blocker_codes"]
    contract = result["consumer_contract"]
    for field in (
        "unseen_seed_count",
        "formal_episode_count",
        "actual_adoption_count",
        "physical_window_count",
        "unique_r0_pair_count",
        "paired_non_degraded_count",
        "formal_scope_audit_passed",
        "formal_scope_checksum_verified",
    ):
        assert contract[field] is None
        assert (
            contract["field_availability"][field]["availability"]
            == "unavailable"
        )


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_weight_tamper_fails_out_of_band_sha256(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / profile.key, profile)
    with fixture.paths["bundle_weights"].open("ab") as stream:
        stream.write(b"tamper")

    result = _audit(fixture)

    assert (
        "artifact_sha256_mismatch.bundle_weights"
        in result["blocker_codes"]
    )


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_current_source_change_requires_new_implementation_evidence(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / profile.key, profile)
    changed = fixture.root / "module_source" / profile.source_files[0]
    changed.write_text("# changed implementation\n", encoding="ascii")
    current = {
        name: _sha_file(fixture.root / "module_source" / name)
        for name in profile.source_files
    }
    fixture.spec["expected_current_implementation_sha256"] = _sha_json(
        dict(sorted(current.items()))
    )

    result = _audit(fixture)

    assert "implementation_lineage_mismatch" in result["blocker_codes"]
    assert result["implementation"]["lineage_verified"] is False


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_formal_source_commit_must_match_implementation_evidence(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / profile.key, profile)
    formal = fixture.read_json("formal_scope_audit")
    formal["learned_scope"]["source_git_commit"] = "b" * 40
    fixture.refresh_formal(formal)

    result = _audit(fixture)

    assert "formal_scope_source_commit_mismatch" in result["blocker_codes"]


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_role_specific_adoption_evidence_cannot_be_substituted(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / profile.key, profile)
    formal = fixture.read_json("formal_scope_audit")
    wrong_component = (
        "d4" if profile.component == "d3" else "d3"
    )
    formal["learned_scope"]["cells"][0]["learning_evidence"][
        "required_components"
    ] = [wrong_component]
    fixture.refresh_formal(formal)

    result = _audit(fixture)

    assert (
        "runtime_ack_or_isolated_adoption_lineage_invalid"
        in result["blocker_codes"]
    )


def test_refrozen_file_with_stale_content_sha_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path / "d3", D3_A1_PROFILE)
    evidence = fixture.read_json("implementation_evidence")
    evidence["source_git_commit"] = "b" * 40
    fixture.write_json(
        "implementation_evidence",
        evidence,
        content_hash=False,
    )

    result = _audit(fixture)

    assert (
        "artifact_content_sha256_mismatch.implementation_evidence"
        in result["blocker_codes"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("nineteen_seeds", "minimum_unseen_seed_count_not_met"),
        ("zero_adoption", "actual_adoption_missing_or_not_applied"),
        ("shadow", "actual_adoption_missing_or_not_applied"),
        ("rule_fallback", "actual_adoption_missing_or_not_applied"),
        ("physical_unavailable", "physical_state_window_unavailable"),
        ("hard_constraint_failure", "formal_scope_cell_not_accepted"),
    ],
)
def test_formal_scope_adoption_availability_and_safety_fail_closed(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    fixture = _make_fixture(tmp_path / mutation, D3_A1_PROFILE)
    formal = fixture.read_json("formal_scope_audit")
    cells = formal["learned_scope"]["cells"]
    if mutation == "nineteen_seeds":
        cells.pop()
        formal["r0_pairing"]["pairs"].pop()
        for owner in (formal["learned_scope"], formal["r0_pairing"]):
            for key in (
                "expected_cell_count",
                "accepted_cell_count",
                "expected_pair_count",
                "available_pair_count",
                "non_degraded_pair_count",
            ):
                if key in owner:
                    owner[key] = 19
    elif mutation in {"zero_adoption", "shadow", "rule_fallback"}:
        cells[0]["assist_adoption_status"] = (
            "unavailable_or_not_adopted"
        )
        cells[0]["learning_evidence"]["status"] = mutation
    elif mutation == "physical_unavailable":
        cells[0]["physical_result_status"] = "unavailable"
    else:
        cells[0]["evidence_status"] = "fail_closed"
        cells[0]["failure_reasons"] = ["hard_constraint_violation"]
    fixture.refresh_formal(formal)

    result = _audit(fixture)

    assert expected_code in result["blocker_codes"]
    assert result["audit_passed"] is False


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("missing", "r0_pair_count_mismatch"),
        ("duplicate", "r0_comparison_key_duplicated"),
        ("degraded", "r0_pair_invalid_or_non_degraded_false"),
        ("metric_missing", "paired_required_metric_not_non_degraded"),
        ("r0_duplicate", "unique_same_key_r0_not_verified"),
    ],
)
def test_unique_same_key_r0_and_non_degradation_are_required(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    fixture = _make_fixture(tmp_path / mutation, D4_A2_PROFILE)
    formal = fixture.read_json("formal_scope_audit")
    pairs = formal["r0_pairing"]["pairs"]
    if mutation == "missing":
        pairs.pop()
    elif mutation == "duplicate":
        pairs[1]["comparison_key"] = pairs[0]["comparison_key"]
    elif mutation == "degraded":
        pairs[0]["non_degraded"] = False
        pairs[0]["metric_comparisons"]["intercepted_target_count"][
            "non_degraded"
        ] = False
    elif mutation == "metric_missing":
        pairs[0]["metric_comparisons"].pop(
            "offline_proximity_unique_target_count"
        )
    else:
        duplicate = deepcopy(formal["r0_scopes"][0]["cells"][0])
        duplicate["cell_id"] = "R0-duplicate"
        formal["r0_scopes"][0]["cells"].append(duplicate)
    fixture.refresh_formal(formal)

    result = _audit(fixture)

    assert expected_code in result["blocker_codes"]


def test_formal_scope_checksum_tamper_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path / "d4", D4_A2_PROFILE)
    fixture.paths["formal_scope_checksums"].write_text(
        f"{'f' * 64}  {fixture.paths['formal_scope_audit'].name}\n",
        encoding="ascii",
    )
    fixture.refresh_artifact("formal_scope_checksums")

    result = _audit(fixture)

    assert "formal_scope_checksum_mismatch" in result["blocker_codes"]


def test_nested_formal_blockers_cannot_be_hidden_at_top_level(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path / "d3", D3_A1_PROFILE)
    formal = fixture.read_json("formal_scope_audit")
    formal["learned_scope"]["blockers"] = ["hidden_scope_failure"]
    formal["r0_pairing"]["blockers"] = ["hidden_pairing_failure"]
    fixture.refresh_formal(formal)

    result = _audit(fixture)

    assert (
        "formal_scope_learned_scope_contains_blockers"
        in result["blocker_codes"]
    )
    assert "r0_pairing_contains_blockers" in result["blocker_codes"]


def test_input_rejects_caller_self_declared_admission_fields(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path / "d3", D3_A1_PROFILE)
    payload = deepcopy(fixture.spec)
    payload["promotion_allowed"] = True

    with pytest.raises(
        LearningModuleExternalAuditError,
        match="input_fields_mismatch",
    ):
        LearningModuleExternalAuditInputs.from_mapping(
            payload,
            repository_root=fixture.root,
            profile_key=D3_A1_PROFILE.key,
        )


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_reports_are_reproducible_and_content_addressed(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / f"fixture-{profile.key}", profile)
    result = _audit(fixture)
    if profile.key == D3_A1_PROFILE.key:
        writer = write_d3_a1_external_audit_report
    else:
        writer = write_d4_a2_external_audit_report
    first = writer(tmp_path / f"out-a-{profile.key}", result)
    second = writer(tmp_path / f"out-b-{profile.key}", result)

    for name in ("json", "csv", "markdown", "checksums"):
        assert first[name].read_bytes() == second[name].read_bytes()
    loaded = json.loads(first["json"].read_text(encoding="utf-8"))
    content_sha = loaded.pop("content_sha256")
    assert _sha_json(loaded) == content_sha


@pytest.mark.parametrize("profile", [D3_A1_PROFILE, D4_A2_PROFILE])
def test_role_specific_cli_uses_the_same_contract(
    tmp_path: Path,
    profile: LearningModuleAuditProfile,
) -> None:
    fixture = _make_fixture(tmp_path / f"fixture-{profile.key}", profile)
    spec_path = fixture.write_spec(tmp_path / f"{profile.key}.json")
    if profile.key == D3_A1_PROFILE.key:
        loaded = load_d3_a1_external_audit_inputs(
            spec_path,
            repository_root=fixture.root,
        )
        script_name = "run_d3_a1_external_audit.py"
    else:
        loaded = load_d4_a2_external_audit_inputs(
            spec_path,
            repository_root=fixture.root,
        )
        script_name = "run_d4_a2_external_audit.py"
    assert loaded.profile_key == profile.key

    repository_root = Path(__file__).resolve().parents[3]
    script = (
        repository_root
        / "research_modules/d6_evaluation_metrics/scripts"
        / script_name
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--input-spec",
            str(spec_path),
            "--repository-root",
            str(fixture.root),
            "--output-dir",
            str(tmp_path / f"cli-{profile.key}"),
        ],
        cwd=repository_root,
        env={
            **os.environ,
            "PYTHONPATH": str(
                repository_root / "research_modules/d6_evaluation_metrics"
            ),
        },
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["status"] == "pass"
    assert summary["audit_passed"] is True
    assert (tmp_path / f"cli-{profile.key}" / "SHA256SUMS").is_file()
