from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any

import pytest
import torch

_D5_SOURCE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "d5_terminal_association"
    / "src"
)
if str(_D5_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_D5_SOURCE_ROOT))

from d5_terminal_association.tracklet_g1_evidence_assembler import (
    TrackletG1EvidenceInputs,
    assemble_tracklet_g1_bundle,
)
from d5_terminal_association.tracklet_gnn import (
    NativeTrackletEdgeClassifier,
)
from d5_terminal_association.tracklet_model_bundle import (
    write_tracklet_model_bundle,
)

from d6_evaluation_metrics.d5_g1_external_audit import (
    audit_d5_g1_external_evidence,
    load_d5_g1_external_audit_inputs,
)
from d6_evaluation_metrics.d5_g1_post_assembly_audit import (
    D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION,
    D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION,
    audit_d5_g1_post_assembly_bundle,
    load_d5_g1_post_assembly_audit_inputs,
)
from d6_evaluation_metrics.learning_run_readiness import (
    LEARNING_VARIANTS,
    READINESS_GATES,
    audit_learning_run_readiness,
    build_learning_run_readiness_input,
)
import d6_evaluation_metrics.learning_run_source_adapters as adapter_module
from d6_evaluation_metrics.learning_run_source_adapters import (
    D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION,
    LearningRunSourceAdapterError,
    load_learning_run_source_evidence_bytes,
)

from research_modules.d6_evaluation_metrics.tests.test_d5_g1_external_audit import (
    _HELDOUT_SOURCE_FILES,
    _PAIRED_SOURCE_FILES,
    _SOURCE_FILES,
    _make_fixture as _make_external_fixture,
)


_ARTIFACT_ROOT_NAME = "MSM-d5-g1-formal-evidence-8d5e02e-20260727"
_SOURCE_ROOT_RELATIVE = (
    "MSM-d5-g1-formal-8d5e02e/"
    "research_modules/d5_terminal_association/src/"
    "d5_terminal_association"
)
_BUNDLE_RELATIVE = "g1_assist_v5_7fb5db8b_d6_cbd6c72b"
_SIDECAR_ARTIFACT_PATHS = {
    "external_audit_input": "d6_external_audit_input.json",
    "external_audit_output": (
        "d6_external_audit/d5_g1_external_audit.json"
    ),
    "external_audit_checksums": "d6_external_audit/SHA256SUMS",
    "post_assembly_input": "d6_post_assembly_input.json",
    "post_assembly_output": (
        "d6_post_assembly_audit/d5_g1_post_assembly_audit.json"
    ),
    "post_assembly_checksums": "d6_post_assembly_audit/SHA256SUMS",
    "v5_bundle_manifest": f"{_BUNDLE_RELATIVE}/manifest.json",
    "v5_bundle_weights": f"{_BUNDLE_RELATIVE}/weights.pt",
    "v5_bundle_checksums": f"{_BUNDLE_RELATIVE}/SHA256SUMS",
    "v5_heldout_evidence": (
        f"{_BUNDLE_RELATIVE}/evidence/heldout_evaluation.json"
    ),
    "v5_paired_shadow_evidence": (
        f"{_BUNDLE_RELATIVE}/evidence/paired_shadow_report.json"
    ),
    "v5_paired_shadow_lineage": (
        f"{_BUNDLE_RELATIVE}/evidence/paired_episode_lineage.jsonl"
    ),
    "v5_external_audit_evidence": (
        f"{_BUNDLE_RELATIVE}/evidence/d6_external_audit.json"
    ),
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


def _sidecar_sha(value: Any) -> str:
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(payload))


def _write_report_checksums(
    directory: Path,
    *,
    markdown_name: str,
    json_name: str,
    csv_name: str,
) -> Path:
    markdown = directory / markdown_name
    csv_path = directory / csv_name
    markdown.write_text("fixture\n", encoding="utf-8")
    csv_path.write_text("fixture\n", encoding="utf-8")
    files = (markdown, directory / json_name, csv_path)
    checksum_path = directory / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{_sha_file(path)}  {path.name}\n" for path in files),
        encoding="ascii",
    )
    return checksum_path


def _rehash_sidecar(payload: dict[str, Any]) -> None:
    body = deepcopy(payload)
    body.pop("content_sha256", None)
    payload["content_sha256"] = _sidecar_sha(body)


@dataclass
class _ModelSourceFixture:
    artifact_root: Path
    sidecar_path: Path
    sidecar: dict[str, Any]
    anchor: dict[str, Any]
    external_originals: dict[str, Path]

    def install_anchor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            adapter_module,
            "_D5_G1_TRUSTED_MODEL_SOURCE",
            deepcopy(self.anchor),
        )

    def rewrite_sidecar(self) -> None:
        _rehash_sidecar(self.sidecar)
        _write_json(self.sidecar_path, self.sidecar)


def _build_complete_model_source_fixture(
    tmp_path: Path,
) -> _ModelSourceFixture:
    artifact_root = tmp_path / _ARTIFACT_ROOT_NAME
    external_fixture = _make_external_fixture(artifact_root)

    source_root = tmp_path / _SOURCE_ROOT_RELATIVE
    source_root.mkdir(parents=True)
    current_source = _D5_SOURCE_ROOT / "d5_terminal_association"
    for name in _SOURCE_FILES:
        shutil.copyfile(current_source / name, source_root / name)

    development_bundle = (
        artifact_root / "model_candidate" / "model_bundle"
    )
    torch.manual_seed(31)
    model = NativeTrackletEdgeClassifier(
        hidden_dim=8,
        message_passing_steps=1,
    )
    write_tracklet_model_bundle(
        development_bundle,
        model,
        dataset_manifest_sha256="1" * 64,
        split_sha256="2" * 64,
        training_set_sha256="4" * 64,
        training_config_sha256="3" * 64,
        calibration_temperature=1.0,
        decision_threshold=0.6,
        validation_results={"f1": {"available": True, "value": 0.95}},
        admission_status="development_only_fail_closed",
        readiness_audit_sha256="7" * 64,
    )
    external_fixture.paths.update(
        {
            "bundle_manifest": development_bundle / "manifest.json",
            "bundle_weights": development_bundle / "weights.pt",
            "bundle_checksums": development_bundle / "SHA256SUMS",
        }
    )

    formal_heldout = (
        artifact_root
        / "formal_audit"
        / "heldout_evaluation"
        / "heldout_evaluation.json"
    )
    formal_paired = (
        artifact_root
        / "formal_audit"
        / "paired_shadow"
        / "paired_shadow_report.json"
    )
    formal_lineage = (
        artifact_root
        / "formal_audit"
        / "paired_shadow"
        / "paired_episode_lineage.jsonl"
    )
    formal_heldout.parent.mkdir(parents=True)
    formal_paired.parent.mkdir(parents=True)
    shutil.move(external_fixture.paths["heldout_report"], formal_heldout)
    shutil.move(external_fixture.paths["paired_shadow_report"], formal_paired)
    shutil.move(external_fixture.paths["paired_shadow_lineage"], formal_lineage)
    external_fixture.paths.update(
        {
            "heldout_report": formal_heldout,
            "paired_shadow_report": formal_paired,
            "paired_shadow_lineage": formal_lineage,
        }
    )

    registry_root = artifact_root / "current_runtime_registry"
    registry_root.mkdir(parents=True)
    for name, filename in (
        ("registry_reference", "frozen_bundle_reference.json"),
        ("registry_audit_evidence", "audit_evidence.json"),
        ("registry_checksums", "SHA256SUMS"),
    ):
        destination = registry_root / filename
        shutil.move(external_fixture.paths[name], destination)
        external_fixture.paths[name] = destination

    development_manifest = json.loads(
        external_fixture.paths["bundle_manifest"].read_text(encoding="utf-8")
    )
    training = development_manifest["training_dataset"]
    runtime_files = development_manifest["code_provenance"][
        "runtime_source_files"
    ]
    runtime_sha = development_manifest["code_provenance"][
        "runtime_implementation_sha256"
    ]
    manifest_sha = _sha_file(external_fixture.paths["bundle_manifest"])
    weights_sha = _sha_file(external_fixture.paths["bundle_weights"])
    checksums_sha = _sha_file(external_fixture.paths["bundle_checksums"])

    heldout = json.loads(formal_heldout.read_text(encoding="utf-8"))
    heldout["development_model"].update(
        {
            "bundle_manifest_sha256": manifest_sha,
            "weights_sha256": weights_sha,
            "model_id": "fixture-formal-g1",
            "training_dataset": training,
        }
    )
    heldout["implementation_sha256"] = {
        name: runtime_files[name] for name in _HELDOUT_SOURCE_FILES
    }
    heldout["heldout_assessment"]["g1_assist_eligible"] = False
    heldout["heldout_assessment"]["cell_catalog_gate"] = {
        "actual": 45,
        "expected": 45,
        "passed": True,
    }
    heldout["overall"]["scenario_scale_cell_count"] = 45
    external_fixture.refresh_json(
        "heldout_report",
        heldout,
        content_hash=True,
    )
    heldout = json.loads(formal_heldout.read_text(encoding="utf-8"))

    lineage_sha = _sha_file(formal_lineage)
    paired = json.loads(formal_paired.read_text(encoding="utf-8"))
    paired_expected = {
        "bundle_manifest_sha256": manifest_sha,
        "bundle_weights_sha256": weights_sha,
        "bundle_checksums_sha256": checksums_sha,
        "heldout_report_sha256": _sha_file(formal_heldout),
        "heldout_report_content_sha256": heldout["content_sha256"],
    }
    paired["input_spec"]["expected_hashes"] = paired_expected
    paired["input_spec_sha256"] = sha256(
        _canonical(paired["input_spec"])
    ).hexdigest()
    paired["input_hashes_before"] = dict(paired_expected)
    paired["input_hashes_after"] = dict(paired_expected)
    paired["implementation_sha256"] = {
        name: runtime_files[name] for name in _PAIRED_SOURCE_FILES
    }
    paired["paired_lineage"] = {
        "schema_version": "d5.tracklet-paired-shadow-lineage.v1",
        "filename": "paired_episode_lineage.jsonl",
        "record_count": 900,
        "sha256": lineage_sha,
    }
    paired["authority"]["runtime_default_changed"] = False
    external_fixture.refresh_json(
        "paired_shadow_report",
        paired,
        content_hash=True,
    )

    registry_reference = json.loads(
        external_fixture.paths["registry_reference"].read_text(
            encoding="utf-8"
        )
    )
    registry_reference["bundle_relative_path"] = (
        "model_candidate/model_bundle"
    )
    registry_reference["model_id"] = "fixture-formal-g1"
    registry_reference["expected_hashes"] = {
        "manifest_sha256": manifest_sha,
        "weights_sha256": weights_sha,
        "checksums_sha256": checksums_sha,
    }
    external_fixture.refresh_json(
        "registry_reference",
        registry_reference,
    )
    registry_evidence = json.loads(
        external_fixture.paths["registry_audit_evidence"].read_text(
            encoding="utf-8"
        )
    )
    registry_evidence["frozen_model"] = {
        "manifest_sha256": manifest_sha,
        "weights_sha256": weights_sha,
    }
    external_fixture.refresh_json(
        "registry_audit_evidence",
        registry_evidence,
    )
    external_fixture.refresh_registry()

    external_fixture.spec["d5_source_dir"] = _SOURCE_ROOT_RELATIVE
    external_fixture.spec[
        "expected_current_implementation_sha256"
    ] = runtime_sha
    for name, path in external_fixture.paths.items():
        external_fixture.spec["artifacts"][name] = {
            "path": path.relative_to(tmp_path).as_posix(),
            "sha256": _sha_file(path),
        }
    external_input_path = artifact_root / "d6_external_audit_input.json"
    _write_json(external_input_path, external_fixture.spec)
    external_inputs = load_d5_g1_external_audit_inputs(
        external_input_path,
        repository_root=tmp_path,
    )
    external_result = audit_d5_g1_external_evidence(external_inputs)
    assert external_result["audit_passed"] is True

    external_output_dir = artifact_root / "d6_external_audit"
    external_output_dir.mkdir()
    external_output_path = (
        external_output_dir / "d5_g1_external_audit.json"
    )
    _write_json(external_output_path, external_result)
    external_checksums_path = _write_report_checksums(
        external_output_dir,
        markdown_name="D5_G1_EXTERNAL_AUDIT_CN.md",
        json_name="d5_g1_external_audit.json",
        csv_name="d5_g1_external_audit_evidence.csv",
    )

    v5_bundle = artifact_root / _BUNDLE_RELATIVE
    assemble_tracklet_g1_bundle(
        v5_bundle,
        TrackletG1EvidenceInputs(
            development_bundle_dir=development_bundle,
            expected_bundle_manifest_sha256=manifest_sha,
            expected_bundle_weights_sha256=weights_sha,
            expected_bundle_checksums_sha256=checksums_sha,
            heldout_report_path=formal_heldout,
            expected_heldout_report_sha256=_sha_file(formal_heldout),
            paired_shadow_report_path=formal_paired,
            expected_paired_shadow_report_sha256=_sha_file(formal_paired),
            paired_shadow_lineage_path=formal_lineage,
            expected_paired_shadow_lineage_sha256=lineage_sha,
            d6_audit_path=external_output_path,
            expected_d6_audit_sha256=_sha_file(external_output_path),
        ),
    )
    post_artifacts = {
        "bundle_manifest": v5_bundle / "manifest.json",
        "bundle_weights": v5_bundle / "weights.pt",
        "bundle_checksums": v5_bundle / "SHA256SUMS",
        "heldout_evidence": (
            v5_bundle / "evidence" / "heldout_evaluation.json"
        ),
        "paired_shadow_evidence": (
            v5_bundle / "evidence" / "paired_shadow_report.json"
        ),
        "paired_shadow_lineage": (
            v5_bundle / "evidence" / "paired_episode_lineage.jsonl"
        ),
        "d6_external_audit_evidence": (
            v5_bundle / "evidence" / "d6_external_audit.json"
        ),
    }
    post_spec = {
        "schema_version": D5_G1_POST_ASSEMBLY_AUDIT_INPUT_SCHEMA_VERSION,
        "audit_id": "fixture-post-assembly",
        "evaluated_at_utc": "2026-07-28T00:00:00Z",
        "profile_version": D5_G1_POST_ASSEMBLY_AUDIT_PROFILE_VERSION,
        "expected_external_audit_content_sha256": external_result[
            "content_sha256"
        ],
        "artifacts": {
            name: {
                "path": path.relative_to(artifact_root).as_posix(),
                "sha256": _sha_file(path),
            }
            for name, path in post_artifacts.items()
        },
    }
    post_input_path = artifact_root / "d6_post_assembly_input.json"
    _write_json(post_input_path, post_spec)
    post_inputs = load_d5_g1_post_assembly_audit_inputs(
        post_input_path,
        repository_root=artifact_root,
    )
    post_result = audit_d5_g1_post_assembly_bundle(post_inputs)
    assert post_result["audit_passed"] is True, post_result["blocker_details"]

    post_output_dir = artifact_root / "d6_post_assembly_audit"
    post_output_dir.mkdir()
    post_output_path = (
        post_output_dir / "d5_g1_post_assembly_audit.json"
    )
    _write_json(post_output_path, post_result)
    post_checksums_path = _write_report_checksums(
        post_output_dir,
        markdown_name="D5_G1_POST_ASSEMBLY_AUDIT_CN.md",
        json_name="d5_g1_post_assembly_audit.json",
        csv_name="d5_g1_post_assembly_audit_evidence.csv",
    )

    sidecar_paths = {
        "external_audit_input": external_input_path,
        "external_audit_output": external_output_path,
        "external_audit_checksums": external_checksums_path,
        "post_assembly_input": post_input_path,
        "post_assembly_output": post_output_path,
        "post_assembly_checksums": post_checksums_path,
        "v5_bundle_manifest": post_artifacts["bundle_manifest"],
        "v5_bundle_weights": post_artifacts["bundle_weights"],
        "v5_bundle_checksums": post_artifacts["bundle_checksums"],
        "v5_heldout_evidence": post_artifacts["heldout_evidence"],
        "v5_paired_shadow_evidence": post_artifacts[
            "paired_shadow_evidence"
        ],
        "v5_paired_shadow_lineage": post_artifacts[
            "paired_shadow_lineage"
        ],
        "v5_external_audit_evidence": post_artifacts[
            "d6_external_audit_evidence"
        ],
    }
    assert {
        name: path.relative_to(artifact_root).as_posix()
        for name, path in sidecar_paths.items()
    } == _SIDECAR_ARTIFACT_PATHS
    sidecar = {
        "schema_version": D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION,
        "variant": "G1",
        "component_references": {
            "d5_graph": {
                name: {
                    "path": path.relative_to(artifact_root).as_posix(),
                    "file_sha256": _sha_file(path),
                }
                for name, path in sorted(sidecar_paths.items())
            }
        },
    }
    _rehash_sidecar(sidecar)
    sidecar_path = artifact_root / "model_source_reference.json"
    _write_json(sidecar_path, sidecar)
    post_consumer = post_result["d5_consumer_contract"]
    anchor = {
        "variant": "G1",
        "component_id": "d5_graph",
        "source_root_relative_to_artifact_parent": _SOURCE_ROOT_RELATIVE,
        "artifact_layout": {
            name: reference["path"]
            for name, reference in sidecar["component_references"][
                "d5_graph"
            ].items()
        },
        "artifact_sha256": {
            name: reference["file_sha256"]
            for name, reference in sidecar["component_references"][
                "d5_graph"
            ].items()
        },
        "model_fingerprint": post_consumer["model_fingerprint"],
        "runtime_implementation_sha256": post_consumer[
            "runtime_implementation_sha256"
        ],
        "external_audit_content_sha256": external_result[
            "content_sha256"
        ],
        "post_assembly_content_sha256": post_result["content_sha256"],
    }
    return _ModelSourceFixture(
        artifact_root=artifact_root,
        sidecar_path=sidecar_path,
        sidecar=sidecar,
        anchor=anchor,
        external_originals=dict(external_fixture.paths),
    )


def _load_fixture(fixture: _ModelSourceFixture) -> dict[str, Any]:
    return load_learning_run_source_evidence_bytes(
        fixture.sidecar_path.read_bytes(),
        artifact_root=fixture.artifact_root,
        expected_variant="G1",
        expected_gate="model_source",
    )


def _unavailable(reason: str) -> dict[str, object]:
    return {
        "availability": False,
        "source_artifact": None,
        "reason_codes": [reason],
    }


def test_complete_original_chain_passes_only_with_trusted_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.install_anchor(monkeypatch)

    result = _load_fixture(fixture)

    assert result == {
        "source_class": "formal_post_assembly_audit",
        "source_schema_version": (
            D5_G1_MODEL_SOURCE_REFERENCE_SCHEMA_VERSION
        ),
        "source_content_sha256": fixture.sidecar["content_sha256"],
        "formal": True,
        "facts": {
            "component_ids": ["d5_graph"],
            "audit_passed": True,
            "model_identity": fixture.anchor["model_fingerprint"],
        },
    }

    variants: dict[str, object] = {}
    for variant in LEARNING_VARIANTS:
        gates = {
            gate: _unavailable(f"{variant.lower()}_{gate}_not_supplied")
            for gate in READINESS_GATES
        }
        if variant == "G1":
            gates["model_source"] = {
                "availability": True,
                "source_artifact": {
                    "path": fixture.sidecar_path.relative_to(
                        fixture.artifact_root
                    ).as_posix(),
                    "file_sha256": _sha_file(fixture.sidecar_path),
                },
                "reason_codes": [],
            }
        variants[variant] = {"variant": variant, "gates": gates}
    manifest = build_learning_run_readiness_input(
        audit_id="trusted-model-source-fixture",
        variants=variants,
        storage={
            "availability": True,
            "source_class": "filesystem_disk_usage_snapshot",
            "observed_at_utc": "2026-07-28T00:00:00Z",
            "mounts": [
                {
                    "path": "/fixture",
                    "available_bytes": 25 * 1024**3,
                    "eligible_for_formal_output": True,
                }
            ],
            "reason_codes": [],
        },
    )
    readiness = audit_learning_run_readiness(
        manifest,
        artifact_root=fixture.artifact_root,
    )
    gate = readiness["variants"]["G1"]["gates"]["model_source"]
    assert gate["availability"] is True
    assert gate["passed"] is True
    assert readiness["variants"]["G1"]["model_readiness"]["ready"] is None
    assert all(value is False for value in readiness["permissions"].values())


def test_complete_self_signed_alternate_model_cannot_pass(
    tmp_path: Path,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="d5_g1_model_source_trust_anchor_mismatch",
    ):
        _load_fixture(fixture)


@pytest.mark.parametrize("assertion_name", ["facts", "permissions"])
def test_self_signed_sidecar_assertions_are_rejected(
    tmp_path: Path,
    assertion_name: str,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.sidecar[assertion_name] = {
        "audit_passed": True,
        "control_authority": True,
    }
    fixture.rewrite_sidecar()

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="gate_source_fields_mismatch",
    ):
        _load_fixture(fixture)


def test_nested_original_producer_tamper_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.install_anchor(monkeypatch)
    original = fixture.external_originals["registry_reference"]
    original.write_bytes(original.read_bytes() + b"\n")

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="gate_source_original_file_sha256_mismatch",
    ):
        _load_fixture(fixture)


def test_sidecar_original_path_escape_is_rejected(tmp_path: Path) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.sidecar["component_references"]["d5_graph"][
        "v5_bundle_weights"
    ]["path"] = "../outside.pt"
    fixture.rewrite_sidecar()

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="gate_source_original_path_escape_rejected",
    ):
        _load_fixture(fixture)


def test_sidecar_original_symlink_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.install_anchor(monkeypatch)
    relative = fixture.sidecar["component_references"]["d5_graph"][
        "v5_bundle_weights"
    ]["path"]
    path = fixture.artifact_root / relative
    target = fixture.artifact_root / "same-weights.pt"
    target.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(target)

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="gate_source_original_symlink_rejected",
    ):
        _load_fixture(fixture)


def test_sidecar_declared_digest_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.sidecar["component_references"]["d5_graph"][
        "v5_bundle_manifest"
    ]["file_sha256"] = "0" * 64
    fixture.rewrite_sidecar()

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="gate_source_original_file_sha256_mismatch",
    ):
        _load_fixture(fixture)


def test_external_input_schema_mismatch_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    external_input = (
        fixture.artifact_root
        / fixture.sidecar["component_references"]["d5_graph"][
            "external_audit_input"
        ]["path"]
    )
    payload = json.loads(external_input.read_text(encoding="utf-8"))
    payload["schema_version"] = "d6.d5-g1-external-audit-input.v99"
    _write_json(external_input, payload)
    digest = _sha_file(external_input)
    fixture.sidecar["component_references"]["d5_graph"][
        "external_audit_input"
    ]["file_sha256"] = digest
    fixture.anchor["artifact_sha256"]["external_audit_input"] = digest
    fixture.rewrite_sidecar()
    fixture.install_anchor(monkeypatch)

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="d5_g1_external_input.input_schema_mismatch",
    ):
        _load_fixture(fixture)


def test_trusted_model_identity_mismatch_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.anchor["model_fingerprint"] = f"sha256:{'0' * 64}"
    fixture.install_anchor(monkeypatch)

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="d5_g1_model_identity_mismatch",
    ):
        _load_fixture(fixture)


def test_composite_variant_missing_components_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    fixture.sidecar["variant"] = "C1"
    fixture.rewrite_sidecar()

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="model_source_component_coverage_mismatch",
    ):
        load_learning_run_source_evidence_bytes(
            fixture.sidecar_path.read_bytes(),
            artifact_root=fixture.artifact_root,
            expected_variant="C1",
            expected_gate="model_source",
        )


def test_rehashed_permission_escalation_output_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_complete_model_source_fixture(tmp_path)
    output = (
        fixture.artifact_root
        / fixture.sidecar["component_references"]["d5_graph"][
            "post_assembly_output"
        ]["path"]
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["authority"]["control_authority_granted"] = True
    body = deepcopy(payload)
    body.pop("content_sha256", None)
    payload["content_sha256"] = sha256(_canonical(body)).hexdigest()
    _write_json(output, payload)
    digest = _sha_file(output)
    fixture.sidecar["component_references"]["d5_graph"][
        "post_assembly_output"
    ]["file_sha256"] = digest
    fixture.anchor["artifact_sha256"]["post_assembly_output"] = digest
    fixture.rewrite_sidecar()
    fixture.install_anchor(monkeypatch)

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="d5_g1_persisted_post_assembly_audit_mismatch",
    ):
        _load_fixture(fixture)


def test_current_external_formal_chain_passes_read_only_when_present() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sidecar = (
        repository_root
        / "research_modules"
        / "d6_evaluation_metrics"
        / "configs"
        / "d5_g1_model_source_reference_7fb5db8b_20260728.json"
    )
    artifact_root = Path(
        "/tmp/MSM-d5-g1-formal-evidence-8d5e02e-20260727"
    )
    if not artifact_root.is_dir():
        pytest.skip("external formal D5 G1 artifact root is unavailable")

    result = load_learning_run_source_evidence_bytes(
        sidecar.read_bytes(),
        artifact_root=artifact_root,
        expected_variant="G1",
        expected_gate="model_source",
    )

    assert result["formal"] is True
    assert result["facts"]["component_ids"] == ["d5_graph"]
    assert result["facts"]["audit_passed"] is True


def test_repository_root_does_not_discover_external_formal_chain() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    sidecar = (
        repository_root
        / "research_modules"
        / "d6_evaluation_metrics"
        / "configs"
        / "d5_g1_model_source_reference_7fb5db8b_20260728.json"
    )

    with pytest.raises(
        LearningRunSourceAdapterError,
        match="gate_source_original_file_missing",
    ):
        load_learning_run_source_evidence_bytes(
            sidecar.read_bytes(),
            artifact_root=repository_root,
            expected_variant="G1",
            expected_gate="model_source",
        )
