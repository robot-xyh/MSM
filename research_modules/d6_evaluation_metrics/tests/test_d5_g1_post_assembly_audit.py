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

from d6_evaluation_metrics.d5_g1_post_assembly_audit import (
    D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION,
    D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION,
    D5G1PostAssemblyAuditError,
    D5G1PostAssemblyAuditInputs,
    audit_d5_g1_post_assembly_bundle,
    load_d5_g1_post_assembly_audit_inputs,
    write_d5_g1_post_assembly_audit_report,
)


_RUNTIME_FILES = (
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
_MODEL_FILES = (
    "tracklet_gnn.py",
    "tracklet_model_bundle.py",
    "tracklet_training.py",
    "tracklet_training_audit.py",
)
_ARTIFACT_RELATIVE = {
    "bundle_manifest": "bundle/manifest.json",
    "bundle_weights": "bundle/weights.pt",
    "bundle_checksums": "bundle/SHA256SUMS",
    "heldout_evidence": "bundle/evidence/heldout_evaluation.json",
    "paired_shadow_evidence": (
        "bundle/evidence/paired_shadow_report.json"
    ),
    "d6_external_audit_evidence": (
        "bundle/evidence/d6_external_audit.json"
    ),
}
_CHECKSUM_RELATIVE = {
    "d6_external_audit_evidence": "evidence/d6_external_audit.json",
    "heldout_evidence": "evidence/heldout_evaluation.json",
    "paired_shadow_evidence": "evidence/paired_shadow_report.json",
    "bundle_manifest": "manifest.json",
    "bundle_weights": "weights.pt",
}


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


@dataclass
class _Fixture:
    root: Path
    bundle: Path
    spec: dict[str, Any]
    paths: dict[str, Path]

    def inputs(self) -> D5G1PostAssemblyAuditInputs:
        return D5G1PostAssemblyAuditInputs.from_mapping(
            deepcopy(self.spec),
            repository_root=self.root,
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
        self.spec["artifacts"][name]["sha256"] = _sha_file(
            self.paths[name]
        )

    def refresh_checksums(
        self,
        *,
        extra: tuple[str, str] | None = None,
    ) -> None:
        records = {
            relative: _sha_file(self.paths[name])
            for name, relative in _CHECKSUM_RELATIVE.items()
        }
        if extra is not None:
            records[extra[0]] = extra[1]
        self.paths["bundle_checksums"].write_text(
            "".join(
                f"{records[name]}  {name}\n"
                for name in sorted(records)
            ),
            encoding="ascii",
        )
        self.spec["artifacts"]["bundle_checksums"]["sha256"] = _sha_file(
            self.paths["bundle_checksums"]
        )

    def write_spec(self, path: Path) -> Path:
        _write_json(path, self.spec)
        return path

    def write_checksum_lines(self, lines: list[str]) -> None:
        self.paths["bundle_checksums"].write_text(
            "".join(f"{line}\n" for line in lines),
            encoding="ascii",
        )
        self.spec["artifacts"]["bundle_checksums"]["sha256"] = _sha_file(
            self.paths["bundle_checksums"]
        )

    def rebind_external(
        self,
        external: dict[str, Any],
    ) -> None:
        self.write_json(
            "d6_external_audit_evidence",
            external,
            content_hash=True,
        )
        rebound = self.read_json("d6_external_audit_evidence")
        file_sha = _sha_file(self.paths["d6_external_audit_evidence"])
        content_sha = rebound["content_sha256"]
        manifest = self.read_json("bundle_manifest")
        manifest["evidence"]["d6_external_audit"]["sha256"] = file_sha
        manifest["evidence"]["d6_external_audit"][
            "content_sha256"
        ] = content_sha
        manifest["admission"]["report"][
            "d6_external_audit_sha256"
        ] = file_sha
        manifest["admission"]["report"][
            "d6_external_audit_content_sha256"
        ] = content_sha
        self.write_json("bundle_manifest", manifest)
        self.spec["expected_external_audit_content_sha256"] = content_sha
        self.refresh_checksums()


def _make_fixture(root: Path) -> _Fixture:
    bundle = root / "bundle"
    evidence_dir = bundle / "evidence"
    evidence_dir.mkdir(parents=True)
    weights_path = bundle / "weights.pt"
    weights_path.write_bytes(b"fixture-v4-weights")
    weights_sha = _sha_file(weights_path)
    source_manifest_sha = "1" * 64
    source_checksums_sha = "2" * 64
    training = {
        "dataset_manifest_sha256": "3" * 64,
        "split_sha256": "4" * 64,
        "training_config_sha256": "5" * 64,
        "training_set_sha256": "6" * 64,
    }
    runtime_files = {
        name: hashlib.sha256(name.encode("ascii")).hexdigest()
        for name in _RUNTIME_FILES
    }
    model_files = {name: runtime_files[name] for name in _MODEL_FILES}
    runtime_sha = _sha_json(dict(sorted(runtime_files.items())))
    model_sha = _sha_json(dict(sorted(model_files.items())))
    model_fingerprint = f"sha256:{weights_sha}"

    heldout = _with_content(
        {
            "schema_version": "d5.tracklet-heldout-model-evaluation.v1",
            "evaluation_role": "held_out_evaluation",
            "development_model": {
                "admission_status": "development_only_fail_closed",
                "bundle_manifest_sha256": source_manifest_sha,
                "weights_sha256": weights_sha,
                "model_id": "fixture-development",
                "training_dataset": training,
            },
            "heldout_corpus": {
                "episode_count": 900,
                "scenario_scale_cell_count": 45,
                "seed_values": list(range(1000, 1020)),
            },
            "implementation_sha256": {
                name: runtime_files[name]
                for name in (
                    "sparse_tracklet_graph.py",
                    "tracklet_dataset.py",
                    "tracklet_gnn.py",
                    "tracklet_heldout_evaluation.py",
                    "tracklet_model_bundle.py",
                    "tracklet_training.py",
                    "tracklet_training_audit.py",
                )
            },
            "heldout_assessment": {
                "status": "pass",
                "passed": True,
                "authority_enabled": False,
                "g1_assist_eligible": False,
                "cell_catalog_gate": {
                    "actual": 45,
                    "expected": 45,
                    "passed": True,
                },
            },
            "overall": {
                "complete_truth": True,
                "episode_count": 900,
            },
            "identity_and_truth_safety": {
                "global_track_id_created_or_rebound": False,
                "online_truth_feature_count": 0,
                "same_camera_candidate_edge_count": 0,
            },
        }
    )
    heldout_path = evidence_dir / "heldout_evaluation.json"
    _write_json(heldout_path, heldout)
    heldout_file_sha = _sha_file(heldout_path)

    paired_expected = {
        "bundle_manifest_sha256": source_manifest_sha,
        "bundle_weights_sha256": weights_sha,
        "bundle_checksums_sha256": source_checksums_sha,
        "heldout_report_sha256": heldout_file_sha,
        "heldout_report_content_sha256": heldout["content_sha256"],
    }
    paired = _with_content(
        {
            "schema_version": "d5.tracklet-paired-shadow.v2",
            "execution_completed": True,
            "evaluation_role": "evaluator_only_paired_shadow",
            "status": "pass",
            "input_spec": {
                "schema_version": "d5.tracklet-paired-shadow-input.v1",
                "require_full_profile": True,
                "expected_hashes": paired_expected,
            },
            "input_hashes_before": paired_expected,
            "input_hashes_after": paired_expected,
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
            },
            "identity_and_truth_safety": {
                "online_truth_feature_count": 0,
                "global_track_id_rewrite_count": 0,
                "same_camera_mutual_exclusion_violation_count": 0,
            },
            "implementation_sha256": {
                name: runtime_files[name]
                for name in (
                    "scalable_3d_adapter.py",
                    "sparse_tracklet_graph.py",
                    "tracklet_dataset.py",
                    "tracklet_g1_evidence_assembler.py",
                    "tracklet_gnn.py",
                    "tracklet_heldout_evaluation.py",
                    "tracklet_model_bundle.py",
                    "tracklet_paired_shadow.py",
                )
            },
            "authority": {
                "status": "pending_d6_external_audit",
                "g1": False,
                "assist": False,
                "authority": False,
                "paired_shadow_passed": True,
                "rule_fallback": True,
                "runtime_default_changed": False,
            },
        }
    )
    paired_path = evidence_dir / "paired_shadow_report.json"
    _write_json(paired_path, paired)
    paired_file_sha = _sha_file(paired_path)

    consumer = {
        "schema_version": "d6.d5-g1-external-audit-consumer.v1",
        "model_fingerprint": model_fingerprint,
        "bundle_manifest_sha256": source_manifest_sha,
        "bundle_weights_sha256": weights_sha,
        "implementation_sha256": runtime_sha,
        "dataset_manifest_sha256": training[
            "dataset_manifest_sha256"
        ],
        "split_sha256": training["split_sha256"],
        "training_set_sha256": training["training_set_sha256"],
        "heldout_report_sha256": heldout_file_sha,
        "heldout_report_content_sha256": heldout["content_sha256"],
        "paired_shadow_report_sha256": paired_file_sha,
        "paired_shadow_report_content_sha256": paired["content_sha256"],
        "formal_evaluation": True,
        "heldout_passed": True,
        "paired_shadow_passed": True,
        "unseen_seed_count": 20,
        "heldout_episode_count": 900,
        "scenario_scale_cell_count": 45,
        "online_truth_feature_count": 0,
        "global_track_id_rewrite_count": 0,
        "same_camera_mutual_exclusion_violation_count": 0,
        "d6_external_audit_passed": True,
        "failure_reasons": [],
    }
    consumer["field_availability"] = {
        name: {"available": True, "reason": None}
        for name in consumer
        if name
        not in {
            "schema_version",
            "d6_external_audit_passed",
            "failure_reasons",
        }
    }
    external = _with_content(
        {
            "schema_version": "d6.d5-g1-external-audit.v1",
            "audit_id": "fixture-external",
            "evaluated_at_utc": "2026-07-26T00:00:00Z",
            "formal_profile_version": (
                "d6.d5-g1-formal-heldout-paired-shadow.v1"
            ),
            "status": "pass",
            "audit_passed": True,
            "fail_closed": False,
            "evidence_audit_only": True,
            "input_contract": {},
            "artifact_evidence": [
                {
                    "artifact_id": f"artifact-{index}",
                    "availability": "available",
                    "sha256_match": True,
                    "blocker_codes": [],
                }
                for index in range(9)
            ],
            "candidate": {
                "model": {
                    "available": True,
                    "manifest_sha256": source_manifest_sha,
                    "weights_sha256": weights_sha,
                    "checksums_sha256": source_checksums_sha,
                    "model_fingerprint": model_fingerprint,
                    "dataset_manifest_sha256": training[
                        "dataset_manifest_sha256"
                    ],
                    "split_sha256": training["split_sha256"],
                    "training_set_sha256": training[
                        "training_set_sha256"
                    ],
                    "manifest_implementation_sha256": model_sha,
                    "manifest_source_files": model_files,
                },
                "implementation": {
                    "current_implementation_sha256": runtime_sha,
                    "evidence_implementation_sha256": runtime_sha,
                    "current_source_files": runtime_files,
                    "evidence_source_files": runtime_files,
                },
                "heldout": {
                    "report_sha256": heldout_file_sha,
                    "report_content_sha256": heldout["content_sha256"],
                    "unseen_seed_count": 20,
                    "episode_count": 900,
                    "scenario_scale_cell_count": 45,
                    "online_truth_feature_count": 0,
                    "passed": True,
                    "training_dataset": {
                        "dataset_manifest_sha256": training[
                            "dataset_manifest_sha256"
                        ],
                        "split_sha256": training["split_sha256"],
                        "training_set_sha256": training[
                            "training_set_sha256"
                        ],
                    },
                },
                "paired_shadow": {
                    "report_sha256": paired_file_sha,
                    "report_content_sha256": paired["content_sha256"],
                    "seed_count": 20,
                    "episode_count": 900,
                    "scenario_scale_cell_count": 45,
                    "online_truth_feature_count": 0,
                    "global_track_id_rewrite_count": 0,
                    "same_camera_mutual_exclusion_violation_count": 0,
                    "passed": True,
                },
            },
            "limitations": {
                "robustness_generalization": {
                    "candidate_graph_limitation": (
                        "profiles hold the post-gate candidate graph fixed"
                    )
                }
            },
            "d5_consumer_contract": consumer,
            "blocker_codes": [],
            "blocker_details": {},
            "authority": {
                "model_promotion_granted": False,
                "g1_assist_granted": False,
                "control_authority_granted": False,
                "default_path_change_granted": False,
                "reason": "fixture",
            },
            "availability_policy": {},
        }
    )
    external_path = evidence_dir / "d6_external_audit.json"
    _write_json(external_path, external)
    external_file_sha = _sha_file(external_path)

    admission_report = {
        "schema_version": "d5.tracklet-g1-admission-report.v1",
        "model_fingerprint": model_fingerprint,
        "implementation_sha256": runtime_sha,
        "dataset_manifest_sha256": training[
            "dataset_manifest_sha256"
        ],
        "split_sha256": training["split_sha256"],
        "training_set_sha256": training["training_set_sha256"],
        "heldout_report_sha256": heldout_file_sha,
        "heldout_report_content_sha256": heldout["content_sha256"],
        "paired_shadow_report_sha256": paired_file_sha,
        "paired_shadow_report_content_sha256": paired["content_sha256"],
        "d6_external_audit_sha256": external_file_sha,
        "d6_external_audit_content_sha256": external["content_sha256"],
        "formal_evaluation": True,
        "heldout_passed": True,
        "paired_shadow_passed": True,
        "d6_external_audit_passed": True,
        "unseen_seed_count": 20,
        "heldout_episode_count": 900,
        "scenario_scale_cell_count": 45,
        "online_truth_feature_count": 0,
        "global_track_id_rewrite_count": 0,
        "same_camera_mutual_exclusion_violation_count": 0,
        "failure_reasons": [],
        "g1_assist_eligible": True,
    }
    manifest = {
        "schema_version": "d5.tracklet-model-bundle.v4",
        "source_development_bundle": {
            "schema_version": "d5.tracklet-model-bundle.v3",
            "admission_status": "development_only_fail_closed",
            "manifest_sha256": source_manifest_sha,
            "weights_sha256": weights_sha,
            "checksums_sha256": source_checksums_sha,
        },
        "weights": {
            "filename": "weights.pt",
            "format": "pytorch_state_dict_weights_only",
            "sha256": weights_sha,
            "size_bytes": weights_path.stat().st_size,
            "model_fingerprint": model_fingerprint,
        },
        "training_dataset": training,
        "code_provenance": {
            "implementation_sha256": model_sha,
            "runtime_implementation_sha256": runtime_sha,
            "source_files": model_files,
            "runtime_source_files": runtime_files,
        },
        "evidence": {
            "heldout": {
                "filename": "evidence/heldout_evaluation.json",
                "sha256": heldout_file_sha,
                "content_sha256": heldout["content_sha256"],
            },
            "paired_shadow": {
                "filename": "evidence/paired_shadow_report.json",
                "sha256": paired_file_sha,
                "content_sha256": paired["content_sha256"],
            },
            "d6_external_audit": {
                "filename": "evidence/d6_external_audit.json",
                "sha256": external_file_sha,
                "content_sha256": external["content_sha256"],
            },
        },
        "admission": {
            "status": "g1_assist_admitted",
            "default_model": False,
            "g1_assist_eligible": True,
            "global_track_id_authority": False,
            "assignment_authority": False,
            "control_authority": False,
            "report": admission_report,
        },
    }
    manifest_path = bundle / "manifest.json"
    _write_json(manifest_path, manifest)
    checksums_path = bundle / "SHA256SUMS"

    paths = {
        name: root / relative
        for name, relative in _ARTIFACT_RELATIVE.items()
    }
    paths["bundle_manifest"] = manifest_path
    paths["bundle_weights"] = weights_path
    paths["bundle_checksums"] = checksums_path
    paths["heldout_evidence"] = heldout_path
    paths["paired_shadow_evidence"] = paired_path
    paths["d6_external_audit_evidence"] = external_path
    spec = {
        "schema_version": D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION,
        "audit_id": "fixture-post-assembly",
        "evaluated_at_utc": "2026-07-26T00:00:00Z",
        "profile_version": D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION,
        "expected_external_audit_content_sha256": external[
            "content_sha256"
        ],
        "artifacts": {
            name: {
                "path": str(path.relative_to(root)),
                "sha256": (
                    _sha_file(path)
                    if path.is_file()
                    else "0" * 64
                ),
            }
            for name, path in paths.items()
        },
    }
    fixture = _Fixture(
        root=root,
        bundle=bundle,
        spec=spec,
        paths=paths,
    )
    fixture.refresh_checksums()
    return fixture


def test_positive_v4_bundle_passes_without_d6_authority(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert result["status"] == "pass"
    assert result["audit_passed"] is True
    assert result["blocker_codes"] == []
    assert result["d5_consumer_contract"][
        "bundle_declared_g1_assist_eligible"
    ] is True
    assert all(
        value is False
        for name, value in result["authority"].items()
        if name != "reason"
    )
    assert result["d5_consumer_contract"]["unseen_seed_count"] == 20
    assert result["d5_consumer_contract"]["heldout_episode_count"] == 900
    assert result["d5_consumer_contract"][
        "scenario_scale_cell_count"
    ] == 45
    assert result["d5_consumer_contract"][
        "online_truth_feature_count"
    ] == 0
    assert result["d5_consumer_contract"][
        "global_track_id_rewrite_count"
    ] == 0
    assert result["d5_consumer_contract"][
        "same_camera_mutual_exclusion_violation_count"
    ] == 0
    assert result["checksum_evidence"]["exact_coverage"] is True
    assert result["checksum_evidence"]["tree_evidence"]["exact"] is True
    assert result["cross_binding"]["runtime_implementation_sha256"] == (
        _sha_json(
            {
                name: hashlib.sha256(name.encode("ascii")).hexdigest()
                for name in sorted(_RUNTIME_FILES)
            }
        )
    )
    assert all(
        row["sha256_match"] is True
        for row in result["artifact_evidence"]
    )
    content_rows = {
        row["artifact_id"]: row
        for row in result["artifact_evidence"]
        if row["artifact_id"]
        in {
            "heldout_evidence",
            "paired_shadow_evidence",
            "d6_external_audit_evidence",
        }
    }
    assert all(
        row["content_sha256_verified"] is True
        for row in content_rows.values()
    )


@pytest.mark.parametrize("artifact_name", tuple(_ARTIFACT_RELATIVE))
def test_any_frozen_artifact_tamper_fails_closed(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    fixture = _make_fixture(tmp_path)
    with fixture.paths[artifact_name].open("ab") as stream:
        stream.write(b"\n")

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert result["audit_passed"] is False
    assert (
        f"artifact_sha256_mismatch.{artifact_name}"
        in result["blocker_codes"]
    )
    assert all(
        value is False
        for name, value in result["authority"].items()
        if name != "reason"
    )


def test_missing_packaged_evidence_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    fixture.paths["heldout_evidence"].unlink()

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "artifact_unavailable.heldout_evidence" in result[
        "blocker_codes"
    ]
    assert result["fail_closed"] is True


def test_extra_checksum_entry_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    fixture.refresh_checksums(extra=("unexpected.bin", "a" * 64))

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "bundle_checksums_entry_set_mismatch" in result["blocker_codes"]


def test_extra_unlisted_bundle_file_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    (fixture.bundle / "unlisted.bin").write_bytes(b"not in SHA256SUMS")

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert result["audit_passed"] is False
    assert "bundle_tree_extra_entry" in result["blocker_codes"]
    assert result["checksum_evidence"]["tree_evidence"]["exact"] is False


def test_missing_checksum_entry_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    lines = fixture.paths["bundle_checksums"].read_text(
        encoding="ascii"
    ).splitlines()
    fixture.write_checksum_lines(
        [line for line in lines if not line.endswith("  weights.pt")]
    )

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "bundle_checksums_entry_set_mismatch" in result["blocker_codes"]


def test_duplicate_checksum_entry_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    lines = fixture.paths["bundle_checksums"].read_text(
        encoding="ascii"
    ).splitlines()
    fixture.write_checksum_lines([*lines, lines[0]])

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "bundle_checksums_invalid" in result["blocker_codes"]


def test_checksum_path_escape_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    lines = fixture.paths["bundle_checksums"].read_text(
        encoding="ascii"
    ).splitlines()
    digest = lines[0].split("  ", 1)[0]
    fixture.write_checksum_lines(
        [f"{digest}  ../outside.bin", *lines[1:]]
    )

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "bundle_checksums_invalid" in result["blocker_codes"]


def test_required_artifact_symlink_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    real_weights = fixture.bundle / "weights.real"
    fixture.paths["bundle_weights"].rename(real_weights)
    fixture.paths["bundle_weights"].symlink_to(real_weights.name)

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "artifact_symlink.bundle_weights" in result["blocker_codes"]
    assert "bundle_tree_symlink" in result["blocker_codes"]
    assert result["audit_passed"] is False


def test_required_artifact_parent_symlink_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    evidence = fixture.bundle / "evidence"
    real_evidence = fixture.bundle / "evidence.real"
    evidence.rename(real_evidence)
    evidence.symlink_to(real_evidence.name, target_is_directory=True)

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "artifact_symlink.heldout_evidence" in result["blocker_codes"]
    assert "artifact_symlink.paired_shadow_evidence" in result[
        "blocker_codes"
    ]
    assert "artifact_symlink.d6_external_audit_evidence" in result[
        "blocker_codes"
    ]
    assert "bundle_tree_symlink" in result["blocker_codes"]
    assert result["audit_passed"] is False


@pytest.mark.parametrize(
    "field",
    (
        "default_model",
        "global_track_id_authority",
        "assignment_authority",
        "control_authority",
    ),
)
def test_forbidden_bundle_permission_fails_closed(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = _make_fixture(tmp_path)
    manifest = fixture.read_json("bundle_manifest")
    manifest["admission"][field] = True
    fixture.write_json("bundle_manifest", manifest)
    fixture.refresh_checksums()

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert (
        f"bundle_admission_permission_invalid.{field}"
        in result["blocker_codes"]
    )
    assert result["authority"]["g1_assist_granted"] is False


@pytest.mark.parametrize(
    "field",
    (
        "model_promotion_granted",
        "g1_assist_granted",
        "control_authority_granted",
        "default_path_change_granted",
    ),
)
def test_external_audit_permission_reopen_fails_closed(
    tmp_path: Path,
    field: str,
) -> None:
    fixture = _make_fixture(tmp_path)
    external = fixture.read_json("d6_external_audit_evidence")
    external["authority"][field] = True
    fixture.rebind_external(external)

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert (
        f"external_audit_authority_not_closed.{field}"
        in result["blocker_codes"]
    )
    assert result["audit_passed"] is False
    assert result["authority"]["control_authority_granted"] is False


def test_g1_assist_eligibility_must_be_true(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    manifest = fixture.read_json("bundle_manifest")
    manifest["admission"]["g1_assist_eligible"] = False
    fixture.write_json("bundle_manifest", manifest)
    fixture.refresh_checksums()

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert (
        "bundle_admission_permission_invalid.g1_assist_eligible"
        in result["blocker_codes"]
    )
    assert result["authority"]["g1_assist_granted"] is False


@pytest.mark.parametrize(
    "artifact_name",
    (
        "heldout_evidence",
        "paired_shadow_evidence",
        "d6_external_audit_evidence",
    ),
)
def test_evidence_content_hash_mismatch_fails_closed(
    tmp_path: Path,
    artifact_name: str,
) -> None:
    fixture = _make_fixture(tmp_path)
    evidence = fixture.read_json(artifact_name)
    evidence["content_sha256"] = "f" * 64
    fixture.write_json(artifact_name, evidence)
    fixture.refresh_checksums()

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert (
        f"artifact_content_sha256_mismatch.{artifact_name}"
        in result["blocker_codes"]
    )


def test_external_audit_failure_fails_closed(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    external = fixture.read_json("d6_external_audit_evidence")
    external["status"] = "fail_closed"
    external["audit_passed"] = False
    external["fail_closed"] = True
    external["blocker_codes"] = ["fixture_failure"]
    external["blocker_details"] = {"fixture_failure": ["fixture"]}
    external["d5_consumer_contract"]["d6_external_audit_passed"] = False
    external["d5_consumer_contract"]["failure_reasons"] = [
        "fixture_failure"
    ]
    fixture.write_json(
        "d6_external_audit_evidence",
        external,
        content_hash=True,
    )
    fixture.spec["expected_external_audit_content_sha256"] = (
        fixture.read_json("d6_external_audit_evidence")["content_sha256"]
    )
    fixture.refresh_checksums()

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert "external_audit_not_passed" in result["blocker_codes"]
    assert "external_audit_has_blockers" in result["blocker_codes"]
    assert result["authority"]["model_promotion_granted"] is False


def test_wrong_expected_external_content_hash_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    fixture.spec["expected_external_audit_content_sha256"] = "e" * 64

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert (
        "external_audit_expected_content_sha256_mismatch"
        in result["blocker_codes"]
    )


def test_manifest_external_binding_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path)
    manifest = fixture.read_json("bundle_manifest")
    manifest["evidence"]["d6_external_audit"][
        "content_sha256"
    ] = "f" * 64
    fixture.write_json("bundle_manifest", manifest)
    fixture.refresh_checksums()

    result = audit_d5_g1_post_assembly_bundle(fixture.inputs())

    assert (
        "cross_binding_mismatch.d6_external_audit_content_sha256"
        in result["blocker_codes"]
    )
    assert result["audit_passed"] is False


def test_outputs_are_atomic_deterministic_and_checksummed(
    tmp_path: Path,
) -> None:
    fixture = _make_fixture(tmp_path / "fixture")
    inputs = fixture.inputs()
    result = audit_d5_g1_post_assembly_bundle(inputs)

    first = write_d5_g1_post_assembly_audit_report(
        tmp_path / "out-a",
        result,
        inputs=inputs,
    )
    second = write_d5_g1_post_assembly_audit_report(
        tmp_path / "out-b",
        result,
        inputs=inputs,
    )

    for name in ("json", "csv", "markdown", "checksums"):
        assert first[name].read_bytes() == second[name].read_bytes()
    for line in first["checksums"].read_text(encoding="ascii").splitlines():
        digest, filename = line.split("  ")
        assert _sha_file(first["checksums"].parent / filename) == digest
    payload = json.loads(first["json"].read_text(encoding="utf-8"))
    content_sha = payload.pop("content_sha256")
    assert _sha_json(payload) == content_sha
    assert not list(tmp_path.glob(".out-a.*"))


def test_output_must_not_overlap_input_bundle(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    inputs = fixture.inputs()
    result = audit_d5_g1_post_assembly_bundle(inputs)

    with pytest.raises(
        D5G1PostAssemblyAuditError,
        match="output_input_overlap",
    ):
        write_d5_g1_post_assembly_audit_report(
            fixture.bundle / "audit-output",
            result,
            inputs=inputs,
        )


def test_input_rejects_caller_pass_boolean(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    payload = deepcopy(fixture.spec)
    payload["audit_passed"] = True

    with pytest.raises(
        D5G1PostAssemblyAuditError,
        match="input_fields_mismatch",
    ):
        D5G1PostAssemblyAuditInputs.from_mapping(
            payload,
            repository_root=fixture.root,
        )


def test_input_rejects_artifact_path_escape(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    payload = deepcopy(fixture.spec)
    payload["artifacts"]["bundle_weights"]["path"] = "../weights.pt"

    with pytest.raises(
        D5G1PostAssemblyAuditError,
        match="input_artifact_path_invalid",
    ):
        D5G1PostAssemblyAuditInputs.from_mapping(
            payload,
            repository_root=fixture.root,
        )


def test_cli_runs_same_contract(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path / "fixture")
    spec_path = fixture.write_spec(tmp_path / "input.json")
    loaded = load_d5_g1_post_assembly_audit_inputs(
        spec_path,
        repository_root=fixture.root,
    )
    assert loaded.audit_id == "fixture-post-assembly"

    repository_root = Path(__file__).resolve().parents[3]
    script = (
        repository_root
        / "research_modules/d6_evaluation_metrics/scripts"
        / "run_d5_g1_post_assembly_audit.py"
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
