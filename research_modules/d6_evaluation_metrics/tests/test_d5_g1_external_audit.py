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

from d6_evaluation_metrics.d5_g1_external_audit import (
    D5_G1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION,
    D5_G1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION,
    D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION,
    D5G1ExternalAuditInputs,
    audit_d5_g1_external_evidence,
    load_d5_g1_external_audit_inputs,
    write_d5_g1_external_audit_report,
)


_SOURCE_FILES = (
    "scalable_3d_adapter.py",
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_g1_evidence_assembler.py",
    "tracklet_gnn.py",
    "tracklet_heldout_evaluation.py",
    "tracklet_model_bundle.py",
    "tracklet_paired_shadow.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_MODEL_SOURCE_FILES = (
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_HELDOUT_SOURCE_FILES = (
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_g1_evidence_assembler.py",
    "tracklet_gnn.py",
    "tracklet_heldout_evaluation.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_PAIRED_SOURCE_FILES = (
    "scalable_3d_adapter.py",
    "sparse_tracklet_graph.py",
    "tracklet_dataset.py",
    "tracklet_g1_evidence_assembler.py",
    "tracklet_gnn.py",
    "tracklet_heldout_evaluation.py",
    "tracklet_model_bundle.py",
    "tracklet_paired_shadow.py",
)


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
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
    path.write_bytes(_canonical(payload))


def _write_checksums(path: Path, files: list[Path]) -> None:
    path.write_text(
        "".join(f"{_sha_file(item)}  {item.name}\n" for item in files),
        encoding="ascii",
    )


@dataclass
class _Fixture:
    root: Path
    spec: dict[str, Any]
    paths: dict[str, Path]
    source_hashes: dict[str, str]

    def inputs(self) -> D5G1ExternalAuditInputs:
        return D5G1ExternalAuditInputs.from_mapping(
            deepcopy(self.spec),
            repository_root=self.root,
        )

    def refresh_json(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        content_hash: bool = False,
    ) -> None:
        if content_hash:
            payload = _with_content(payload)
        _write_json(self.paths[name], payload)
        self.spec["artifacts"][name]["sha256"] = _sha_file(self.paths[name])

    def refresh_registry(self) -> None:
        evidence = json.loads(
            self.paths["registry_audit_evidence"].read_text(encoding="utf-8")
        )
        heldout = json.loads(
            self.paths["heldout_report"].read_text(encoding="utf-8")
        )
        paired = json.loads(
            self.paths["paired_shadow_report"].read_text(encoding="utf-8")
        )
        evidence["output_hashes"].update(
            {
                "heldout_evaluation_file_sha256": _sha_file(
                    self.paths["heldout_report"]
                ),
                "heldout_evaluation_content_sha256": heldout[
                    "content_sha256"
                ],
                "paired_report_file_sha256": _sha_file(
                    self.paths["paired_shadow_report"]
                ),
                "paired_report_content_sha256": paired["content_sha256"],
                "paired_lineage_sha256": _sha_file(
                    self.paths["paired_shadow_lineage"]
                ),
            }
        )
        self.refresh_json("registry_audit_evidence", evidence)
        _write_checksums(
            self.paths["registry_checksums"],
            [
                self.paths["registry_audit_evidence"],
                self.paths["registry_reference"],
            ],
        )
        self.spec["artifacts"]["registry_checksums"]["sha256"] = _sha_file(
            self.paths["registry_checksums"]
        )

    def write_input_spec(self, path: Path) -> Path:
        _write_json(path, self.spec)
        return path


def _make_fixture(root: Path) -> _Fixture:
    source_root = root / "d5_source"
    source_root.mkdir(parents=True)
    source_hashes: dict[str, str] = {}
    for name in _SOURCE_FILES:
        path = source_root / name
        path.write_text(f"# fixture {name}\n", encoding="ascii")
        source_hashes[name] = _sha_file(path)
    implementation_sha = _sha_json(dict(sorted(source_hashes.items())))

    bundle_dir = root / "bundle"
    bundle_dir.mkdir()
    weights_path = bundle_dir / "weights.pt"
    weights_path.write_bytes(b"fixture-weights")
    weights_sha = _sha_file(weights_path)
    training = {
        "dataset_manifest_sha256": "1" * 64,
        "split_sha256": "2" * 64,
        "training_config_sha256": "3" * 64,
        "training_set_sha256": "4" * 64,
    }
    model_sources = {
        name: source_hashes[name] for name in _MODEL_SOURCE_FILES
    }
    manifest = {
        "schema_version": "d5.tracklet-model-bundle.v3",
        "model_semantic_version": "1.0.0",
        "training_dataset": training,
        "code_provenance": {
            "implementation_sha256": _sha_json(
                dict(sorted(model_sources.items()))
            ),
            "source_files": model_sources,
        },
        "weights": {
            "filename": "weights.pt",
            "format": "pytorch_state_dict_weights_only",
            "sha256": weights_sha,
            "size_bytes": weights_path.stat().st_size,
        },
        "admission": {
            "status": "development_only_fail_closed",
            "default_model": False,
            "g1_assist_eligible": False,
        },
    }
    manifest_path = bundle_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    bundle_checksums = bundle_dir / "SHA256SUMS"
    _write_checksums(bundle_checksums, [manifest_path, weights_path])

    heldout_metrics = {
        "f1": {"available": True, "value": 0.92},
        "false_merge_rate": {"available": True, "value": 0.01},
        "candidate_recall": {"available": True, "value": 0.95},
        "p95_inference_latency_ms": {
            "available": True,
            "value": 100.0,
        },
    }
    heldout = _with_content(
        {
            "schema_version": "d5.tracklet-heldout-model-evaluation.v1",
            "evaluation_role": "held_out_evaluation",
            "development_model": {
                "admission_status": "development_only_fail_closed",
                "bundle_manifest_sha256": _sha_file(manifest_path),
                "weights_sha256": weights_sha,
                "model_id": f"fixture-{weights_sha[:16]}",
                "training_dataset": training,
            },
            "heldout_corpus": {
                "episode_count": 900,
                "scenario_scale_cell_count": 45,
                "seed_values": list(range(1000, 1020)),
            },
            "implementation_sha256": {
                name: source_hashes[name]
                for name in _HELDOUT_SOURCE_FILES
            },
            "heldout_assessment": {
                "status": "pass",
                "passed": True,
                "authority_enabled": False,
            },
            "overall": {
                "complete_truth": True,
                "episode_count": 900,
                "metrics": heldout_metrics,
            },
            "identity_and_truth_safety": {
                "online_truth_feature_count": 0,
                "global_track_id_created_or_rebound": False,
            },
        }
    )
    heldout_path = root / "heldout" / "heldout_evaluation.json"
    _write_json(heldout_path, heldout)

    lineage_path = root / "paired" / "paired_episode_lineage.jsonl"
    lineage_path.parent.mkdir(parents=True)
    lineage_path.write_text(
        "".join(
            json.dumps({"episode_uid": f"episode-{index:04d}"}) + "\n"
            for index in range(900)
        ),
        encoding="utf-8",
    )
    expected_hashes = {
        "bundle_manifest_sha256": _sha_file(manifest_path),
        "bundle_weights_sha256": weights_sha,
        "heldout_report_sha256": _sha_file(heldout_path),
        "heldout_report_content_sha256": heldout["content_sha256"],
    }
    input_spec = {
        "schema_version": "d5.tracklet-paired-shadow-input.v1",
        "require_full_profile": True,
        "expected_hashes": expected_hashes,
    }
    paired = _with_content(
        {
            "schema_version": "d5.tracklet-paired-shadow.v2",
            "execution_completed": True,
            "evaluation_role": "evaluator_only_paired_shadow",
            "status": "pass",
            "input_spec": input_spec,
            "input_spec_sha256": _sha_json(input_spec),
            "input_hashes_before": expected_hashes,
            "input_hashes_after": expected_hashes,
            "input_artifacts_unchanged": True,
            "evidence_status": {"status": "authoritative"},
            "totals": {
                "seed_count": 20,
                "episode_count": 900,
                "scenario_scale_cell_count": 45,
            },
            "catalog_integrity": {"complete": True},
            "paired_shadow_assessment": {
                "status": "pass",
                "passed": True,
                "gates": [
                    {
                        "name": "boundary_gate",
                        "available": True,
                        "passed": True,
                    }
                ],
            },
            "identity_and_truth_safety": {
                "online_truth_feature_count": 0,
                "global_track_id_rewrite_count": 0,
                "same_camera_mutual_exclusion_violation_count": 0,
            },
            "implementation_sha256": {
                name: source_hashes[name]
                for name in _PAIRED_SOURCE_FILES
            },
            "feature_label_diagnostics": {
                "maximum_single_feature_auc": {
                    "available": True,
                    "best_direction_auc": 0.98,
                    "feature": "fixture_feature",
                }
            },
            "robustness_profiles": [
                {
                    "profile": {
                        "profile_id": f"profile-{index}",
                        "truth_dependent": False,
                        "candidate_graph_rebuilt": True,
                    },
                    "model": {
                        "edge": {"f1": 0.9},
                        "cluster_pairwise": {"f1": 0.9},
                    },
                }
                for index in range(5)
            ],
            "authority": {
                "status": "pending_d6_external_audit",
                "g1": False,
                "assist": False,
                "authority": False,
                "rule_fallback": True,
            },
        }
    )
    paired_path = root / "paired" / "paired_shadow_report.json"
    _write_json(paired_path, paired)

    registry_dir = root / "registry"
    registry_dir.mkdir()
    reference = {
        "schema_version": "d5.frozen-tracklet-audit-reference.v1",
        "bundle_relative_path": "bundle",
        "model_id": f"fixture-{weights_sha[:16]}",
        "expected_hashes": {
            "manifest_sha256": _sha_file(manifest_path),
            "weights_sha256": weights_sha,
            "checksums_sha256": _sha_file(bundle_checksums),
        },
        "admission_policy": {
            "g1": False,
            "assist": False,
            "authority": False,
            "default_model": False,
        },
    }
    reference_path = registry_dir / "frozen_bundle_reference.json"
    _write_json(reference_path, reference)
    evidence = {
        "schema_version": "d5.frozen-tracklet-audit-evidence.v1",
        "status": "evidence_chain_closed_shadow_only",
        "frozen_model": {
            "manifest_sha256": _sha_file(manifest_path),
            "weights_sha256": weights_sha,
        },
        "output_hashes": {
            "heldout_evaluation_file_sha256": _sha_file(heldout_path),
            "heldout_evaluation_content_sha256": heldout["content_sha256"],
            "paired_report_file_sha256": _sha_file(paired_path),
            "paired_report_content_sha256": paired["content_sha256"],
            "paired_lineage_sha256": _sha_file(lineage_path),
        },
        "catalog": {
            "seed_count": 20,
            "episode_count": 900,
            "scenario_scale_cell_count": 45,
        },
        "authority": {
            "g1": False,
            "assist": False,
            "authority": False,
            "default_model_changed": False,
        },
        "limitations": [
            "d6_external_audit_required",
            "no_online_authority",
        ],
    }
    evidence_path = registry_dir / "audit_evidence.json"
    _write_json(evidence_path, evidence)
    registry_checksums = registry_dir / "SHA256SUMS"
    _write_checksums(registry_checksums, [evidence_path, reference_path])

    paths = {
        "registry_reference": reference_path,
        "registry_audit_evidence": evidence_path,
        "registry_checksums": registry_checksums,
        "bundle_manifest": manifest_path,
        "bundle_weights": weights_path,
        "bundle_checksums": bundle_checksums,
        "heldout_report": heldout_path,
        "paired_shadow_report": paired_path,
        "paired_shadow_lineage": lineage_path,
    }
    spec = {
        "schema_version": D5_G1_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION,
        "audit_id": "fixture-positive",
        "evaluated_at_utc": "2026-07-26T00:00:00Z",
        "formal_profile_version": (
            D5_G1_EXTERNAL_AUDIT_FORMAL_PROFILE_VERSION
        ),
        "d5_source_dir": "d5_source",
        "expected_current_implementation_sha256": implementation_sha,
        "thresholds": {
            "minimum_unseen_seed_count": 20,
            "minimum_heldout_episode_count": 900,
            "minimum_scenario_scale_cell_count": 45,
            "minimum_heldout_f1": 0.92,
            "maximum_heldout_false_merge_rate": 0.01,
            "minimum_heldout_candidate_recall": 0.95,
            "maximum_heldout_p95_inference_latency_ms": 100.0,
            "maximum_single_feature_auc": 0.98,
            "minimum_robustness_profile_count": 5,
            "minimum_robustness_edge_f1": 0.9,
            "minimum_robustness_cluster_f1": 0.9,
        },
        "artifacts": {
            name: {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha_file(path),
            }
            for name, path in paths.items()
        },
    }
    return _Fixture(
        root=root,
        spec=spec,
        paths=paths,
        source_hashes=source_hashes,
    )


def test_positive_fixture_passes_at_all_threshold_boundaries(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert result["schema_version"] == D5_G1_EXTERNAL_AUDIT_SCHEMA_VERSION
    assert result["status"] == "pass"
    assert result["audit_passed"] is True
    assert result["blocker_codes"] == []
    contract = result["d5_consumer_contract"]
    assert contract["model_fingerprint"].startswith("sha256:")
    assert contract["formal_evaluation"] is True
    assert contract["unseen_seed_count"] == 20
    assert contract["heldout_episode_count"] == 900
    assert contract["scenario_scale_cell_count"] == 45
    assert contract["d6_external_audit_passed"] is True
    assert all(value is False for value in result["authority"].values() if isinstance(value, bool))


def test_missing_file_is_unavailable_and_not_zero(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    fixture.paths["paired_shadow_report"].unlink()

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert result["status"] == "fail_closed"
    assert "artifact_missing.paired_shadow_report" in result["blocker_codes"]
    contract = result["d5_consumer_contract"]
    assert contract["unseen_seed_count"] is None
    assert contract["field_availability"]["unseen_seed_count"]["available"] is False


def test_file_sha_tamper_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    with fixture.paths["bundle_weights"].open("ab") as stream:
        stream.write(b"tamper")

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "artifact_sha256_mismatch.bundle_weights" in result["blocker_codes"]
    assert result["audit_passed"] is False


def test_content_sha_tamper_fails_closed_even_when_file_sha_is_refrozen(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    heldout = json.loads(
        fixture.paths["heldout_report"].read_text(encoding="utf-8")
    )
    heldout["overall"]["episode_count"] = 899
    fixture.refresh_json("heldout_report", heldout, content_hash=False)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert (
        "artifact_content_sha256_mismatch.heldout_report"
        in result["blocker_codes"]
    )


def test_cross_model_paired_report_is_rejected(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    paired = json.loads(
        fixture.paths["paired_shadow_report"].read_text(encoding="utf-8")
    )
    paired["input_spec"]["expected_hashes"][
        "bundle_weights_sha256"
    ] = "a" * 64
    paired["input_hashes_before"] = deepcopy(
        paired["input_spec"]["expected_hashes"]
    )
    paired["input_hashes_after"] = deepcopy(
        paired["input_spec"]["expected_hashes"]
    )
    paired["input_spec_sha256"] = _sha_json(paired["input_spec"])
    fixture.refresh_json("paired_shadow_report", paired, content_hash=True)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "model_lineage_mismatch" in result["blocker_codes"]


def test_cross_dataset_heldout_report_is_rejected(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    heldout = json.loads(
        fixture.paths["heldout_report"].read_text(encoding="utf-8")
    )
    heldout["development_model"]["training_dataset"][
        "dataset_manifest_sha256"
    ] = "b" * 64
    fixture.refresh_json("heldout_report", heldout, content_hash=True)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "dataset_lineage_mismatch" in result["blocker_codes"]


def test_current_implementation_change_without_evidence_bridge_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    changed = fixture.root / "d5_source" / "tracklet_model_bundle.py"
    changed.write_text("# changed runtime implementation\n", encoding="ascii")
    current = {
        name: _sha_file(fixture.root / "d5_source" / name)
        for name in _SOURCE_FILES
    }
    fixture.spec["expected_current_implementation_sha256"] = _sha_json(
        dict(sorted(current.items()))
    )

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "implementation_lineage_mismatch" in result["blocker_codes"]
    assert (
        result["candidate"]["implementation"]["equivalence_bridge"]["verified"]
        is False
    )


def test_pre_assembler_evidence_exposes_both_source_mismatches(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    assembler = "tracklet_g1_evidence_assembler.py"

    heldout = json.loads(
        fixture.paths["heldout_report"].read_text(encoding="utf-8")
    )
    heldout["implementation_sha256"].pop(assembler)
    fixture.refresh_json("heldout_report", heldout, content_hash=True)

    paired = json.loads(
        fixture.paths["paired_shadow_report"].read_text(encoding="utf-8")
    )
    paired["implementation_sha256"].pop(assembler)
    paired["input_spec"]["expected_hashes"].update(
        {
            "heldout_report_sha256": _sha_file(
                fixture.paths["heldout_report"]
            ),
            "heldout_report_content_sha256": heldout["content_sha256"],
        }
    )
    paired["input_spec_sha256"] = _sha_json(paired["input_spec"])
    paired["input_hashes_before"] = deepcopy(
        paired["input_spec"]["expected_hashes"]
    )
    paired["input_hashes_after"] = deepcopy(
        paired["input_spec"]["expected_hashes"]
    )
    fixture.refresh_json("paired_shadow_report", paired, content_hash=True)
    fixture.refresh_registry()

    model_bundle = fixture.root / "d5_source" / "tracklet_model_bundle.py"
    model_bundle.write_text(
        "# post-assembler runtime implementation\n",
        encoding="ascii",
    )
    current = {
        name: _sha_file(fixture.root / "d5_source" / name)
        for name in _SOURCE_FILES
    }
    fixture.spec["expected_current_implementation_sha256"] = _sha_json(
        dict(sorted(current.items()))
    )

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "implementation_evidence_unavailable" in result["blocker_codes"]
    assert "implementation_lineage_mismatch" in result["blocker_codes"]
    mismatches = result["candidate"]["implementation"]["source_mismatches"]
    assert mismatches[assembler] == {
        "evidence_sha256": None,
        "current_sha256": current[assembler],
    }
    assert mismatches["tracklet_model_bundle.py"] == {
        "evidence_sha256": fixture.source_hashes[
            "tracklet_model_bundle.py"
        ],
        "current_sha256": current["tracklet_model_bundle.py"],
    }


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("execution_completed",), 1),
        (("totals", "seed_count"), True),
    ],
)
def test_boolean_and_integer_fields_use_strict_types(
    tmp_path: Path,
    field_path: tuple[str, ...],
    value: Any,
) -> None:
    fixture = _make_fixture(tmp_path)
    paired = json.loads(
        fixture.paths["paired_shadow_report"].read_text(encoding="utf-8")
    )
    target = paired
    for part in field_path[:-1]:
        target = target[part]
    target[field_path[-1]] = value
    fixture.refresh_json("paired_shadow_report", paired, content_hash=True)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "paired_shadow_type_invalid" in result["blocker_codes"]
    assert result["audit_passed"] is False


def test_threshold_exceedance_fails_but_exact_boundary_passes(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    paired = json.loads(
        fixture.paths["paired_shadow_report"].read_text(encoding="utf-8")
    )
    paired["feature_label_diagnostics"]["maximum_single_feature_auc"][
        "best_direction_auc"
    ] = 0.980001
    fixture.refresh_json("paired_shadow_report", paired, content_hash=True)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "synthetic_single_feature_shortcut" in result["blocker_codes"]


def test_unavailable_metric_fails_closed_without_zero_fill(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    heldout = json.loads(
        fixture.paths["heldout_report"].read_text(encoding="utf-8")
    )
    heldout["overall"]["metrics"]["f1"] = {
        "available": False,
        "value": None,
    }
    fixture.refresh_json("heldout_report", heldout, content_hash=True)

    result = audit_d5_g1_external_evidence(fixture.inputs())

    assert "heldout_metric_unavailable" in result["blocker_codes"]
    assert result["candidate"]["heldout"]["metrics"]["f1"] is None


def test_outputs_are_reproducible_and_checksums_verify(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path / "fixture")
    result = audit_d5_g1_external_evidence(fixture.inputs())
    first = write_d5_g1_external_audit_report(tmp_path / "out-a", result)
    second = write_d5_g1_external_audit_report(tmp_path / "out-b", result)

    for name in ("json", "csv", "markdown", "checksums"):
        assert first[name].read_bytes() == second[name].read_bytes()
    for line in first["checksums"].read_text(encoding="ascii").splitlines():
        digest, filename = line.split("  ")
        assert _sha_file(first["checksums"].parent / filename) == digest
    loaded = json.loads(first["json"].read_text(encoding="utf-8"))
    unsigned = dict(loaded)
    content_sha = unsigned.pop("content_sha256")
    assert _sha_json(unsigned) == content_sha


def test_cli_runs_the_same_fixture_contract(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path / "fixture")
    spec_path = fixture.write_input_spec(tmp_path / "input.json")
    loaded = load_d5_g1_external_audit_inputs(
        spec_path,
        repository_root=fixture.root,
    )
    assert loaded.audit_id == "fixture-positive"

    repository_root = Path(__file__).resolve().parents[3]
    script = (
        repository_root
        / "research_modules/d6_evaluation_metrics/scripts"
        / "run_d5_g1_external_audit.py"
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
            str(tmp_path / "cli-output"),
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
    assert (tmp_path / "cli-output" / "SHA256SUMS").is_file()
