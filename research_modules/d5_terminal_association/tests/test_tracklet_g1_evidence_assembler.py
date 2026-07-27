from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest
import torch

import d5_terminal_association.tracklet_model_bundle as tracklet_model_bundle_module
from d5_terminal_association.tracklet_dataset import sha256_file, sha256_json
from d5_terminal_association.tracklet_g1_evidence_assembler import (
    D6_AUDIT_EVIDENCE_FILENAME,
    D6_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION,
    D6_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION,
    D6_EXTERNAL_AUDIT_SCHEMA_VERSION,
    D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION,
    G1_BUNDLE_CHECKSUM_FILES,
    HELDOUT_EVIDENCE_FILENAME,
    PAIRED_SHADOW_EVIDENCE_FILENAME,
    PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
    PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
    TrackletG1EvidenceAssemblyError,
    TrackletG1EvidenceInputs,
    assemble_tracklet_g1_bundle,
)
from d5_terminal_association.tracklet_gnn import NativeTrackletEdgeClassifier
from d5_terminal_association.tracklet_model_bundle import (
    G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON,
    G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION,
    LEGACY_G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION,
    LEGACY_TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION,
    TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION,
    TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION,
    TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS,
    ModelBundleValidationError,
    load_tracklet_model_bundle,
    load_tracklet_model_bundle_for_runtime,
    tracklet_runtime_implementation_sha256,
    write_tracklet_model_bundle,
)


def _canonical_json_bytes(value: Any) -> bytes:
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


def test_runtime_implementation_digest_binds_g1_evidence_assembler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = tracklet_runtime_implementation_sha256()
    original_sha256_file = tracklet_model_bundle_module.sha256_file
    assembler_was_hashed = False

    def changed_assembler_sha256(path: Path) -> str:
        nonlocal assembler_was_hashed
        digest = original_sha256_file(path)
        if Path(path).name == "tracklet_g1_evidence_assembler.py":
            assembler_was_hashed = True
            replacement = "0" if digest[0] != "0" else "1"
            return replacement + digest[1:]
        return digest

    monkeypatch.setattr(
        tracklet_model_bundle_module,
        "sha256_file",
        changed_assembler_sha256,
    )

    assert tracklet_runtime_implementation_sha256() != baseline
    assert assembler_was_hashed is True


def _write_content_json(path: Path, payload: dict[str, Any]) -> str:
    value = dict(payload)
    value.pop("content_sha256", None)
    value["content_sha256"] = sha256_json(value)
    path.write_bytes(_canonical_json_bytes(value))
    return sha256_file(path)


def _write_lineage(
    path: Path,
    *,
    record_count: int = 900,
    duplicate_last_uid: bool = False,
) -> str:
    records = []
    for index in range(record_count):
        uid_index = 0 if duplicate_last_uid and index == record_count - 1 else index
        records.append({"episode_uid": f"episode-{uid_index:04d}"})
    path.write_bytes(
        b"".join(_canonical_json_bytes(record) for record in records)
    )
    return sha256_file(path)


def _source_bundle(root: Path) -> dict[str, Any]:
    torch.manual_seed(31)
    model = NativeTrackletEdgeClassifier(
        hidden_dim=8,
        message_passing_steps=1,
    )
    write_tracklet_model_bundle(
        root,
        model,
        dataset_manifest_sha256="a" * 64,
        split_sha256="b" * 64,
        training_set_sha256="c" * 64,
        training_config_sha256="d" * 64,
        calibration_temperature=1.0,
        decision_threshold=0.6,
        validation_results={"f1": {"available": True, "value": 0.95}},
        admission_status="development_only_fail_closed",
        readiness_audit_sha256="e" * 64,
    )
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return {
        "manifest": manifest,
        "manifest_sha256": sha256_file(root / "manifest.json"),
        "weights_sha256": sha256_file(root / "weights.pt"),
        "checksums_sha256": sha256_file(root / "SHA256SUMS"),
    }


def _heldout_payload(source: dict[str, Any]) -> dict[str, Any]:
    training = source["manifest"]["training_dataset"]
    return {
        "schema_version": "d5.tracklet-heldout-model-evaluation.v1",
        "evaluation_role": "held_out_evaluation",
        "development_model": {
            "admission_status": "development_only_fail_closed",
            "bundle_manifest_sha256": source["manifest_sha256"],
            "weights_sha256": source["weights_sha256"],
            "training_dataset": dict(training),
        },
        "heldout_corpus": {
            "seed_values": list(range(1000, 1020)),
            "episode_count": 900,
            "scenario_scale_cell_count": 45,
        },
        "heldout_assessment": {
            "passed": True,
            "authority_enabled": False,
            "failure_reasons": [],
        },
        "identity_and_truth_safety": {
            "online_truth_feature_count": 0,
            "global_track_id_created_or_rebound": False,
        },
    }


def _paired_payload(
    source: dict[str, Any],
    heldout_sha256: str,
    heldout_content_sha256: str,
    lineage_sha256: str,
    lineage_record_count: int = 900,
) -> dict[str, Any]:
    return {
        "schema_version": "d5.tracklet-paired-shadow.v2",
        "evaluation_role": "heldout_paired_shadow",
        "execution_completed": True,
        "input_artifacts_unchanged": True,
        "input_spec": {
            "schema_version": "d5.tracklet-paired-shadow-input.v1",
            "require_full_profile": True,
            "expected_hashes": {
                "bundle_manifest_sha256": source["manifest_sha256"],
                "bundle_weights_sha256": source["weights_sha256"],
                "heldout_report_sha256": heldout_sha256,
                "heldout_report_content_sha256": heldout_content_sha256,
            },
        },
        "totals": {
            "seed_count": 20,
            "episode_count": 900,
            "scenario_scale_cell_count": 45,
        },
        "paired_shadow_assessment": {
            "passed": True,
            "status": "pass",
            "failure_reasons": [],
        },
        "identity_and_truth_safety": {
            "online_truth_feature_count": 0,
            "global_track_id_rewrite_count": 0,
            "same_camera_mutual_exclusion_violation_count": 0,
        },
        "paired_lineage": {
            "schema_version": PAIRED_SHADOW_LINEAGE_SCHEMA_VERSION,
            "filename": Path(
                PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME
            ).name,
            "record_count": lineage_record_count,
            "sha256": lineage_sha256,
        },
        "authority": {
            "g1": False,
            "assist": False,
            "authority": False,
            "rule_fallback": True,
        },
    }


def _consumer_contract(
    source: dict[str, Any],
    heldout_sha256: str,
    heldout_content_sha256: str,
    paired_sha256: str,
    paired_content_sha256: str,
) -> dict[str, Any]:
    training = source["manifest"]["training_dataset"]
    implementation = source["manifest"]["code_provenance"][
        "runtime_implementation_sha256"
    ]
    values: dict[str, Any] = {
        "bundle_manifest_sha256": source["manifest_sha256"],
        "bundle_weights_sha256": source["weights_sha256"],
        "dataset_manifest_sha256": training["dataset_manifest_sha256"],
        "formal_evaluation": True,
        "global_track_id_rewrite_count": 0,
        "heldout_episode_count": 900,
        "heldout_passed": True,
        "heldout_report_content_sha256": heldout_content_sha256,
        "heldout_report_sha256": heldout_sha256,
        "implementation_sha256": implementation,
        "model_fingerprint": f"sha256:{source['weights_sha256']}",
        "online_truth_feature_count": 0,
        "paired_shadow_passed": True,
        "paired_shadow_report_content_sha256": paired_content_sha256,
        "paired_shadow_report_sha256": paired_sha256,
        "same_camera_mutual_exclusion_violation_count": 0,
        "scenario_scale_cell_count": 45,
        "split_sha256": training["split_sha256"],
        "training_set_sha256": training["training_set_sha256"],
        "unseen_seed_count": 20,
    }
    availability = {
        name: {"available": True, "reason": None}
        for name in values
    }
    return {
        "schema_version": D6_EXTERNAL_AUDIT_CONSUMER_SCHEMA_VERSION,
        **values,
        "d6_external_audit_passed": True,
        "failure_reasons": [],
        "field_availability": availability,
    }


def _audit_payload(
    source: dict[str, Any],
    heldout_sha256: str,
    heldout_content_sha256: str,
    paired_sha256: str,
    paired_content_sha256: str,
    lineage_sha256: str,
    lineage_record_count: int = 900,
    lineage_unique_episode_uid_count: int = 900,
) -> dict[str, Any]:
    contract = _consumer_contract(
        source,
        heldout_sha256,
        heldout_content_sha256,
        paired_sha256,
        paired_content_sha256,
    )
    implementation = contract["implementation_sha256"]
    return {
        "schema_version": D6_EXTERNAL_AUDIT_SCHEMA_VERSION,
        "audit_id": "positive-contract-fixture",
        "evaluated_at_utc": "2026-07-26T00:00:00Z",
        "formal_profile_version": (
            "d6.d5-g1-formal-heldout-paired-shadow.v1"
        ),
        "audit_passed": True,
        "status": "pass",
        "fail_closed": False,
        "evidence_audit_only": True,
        "blocker_codes": [],
        "blocker_details": {},
        "d5_consumer_contract": contract,
        "authority": {
            "model_promotion_granted": False,
            "g1_assist_granted": False,
            "default_path_change_granted": False,
            "assignment_authority_granted": False,
            "failover_authority_granted": False,
            "control_authority_granted": False,
            "reason": "fixture audit grants evidence status only",
        },
        "availability_policy": {
            "missing_evidence": "fail_closed",
        },
        "input_contract": {
            "schema_version": D6_EXTERNAL_AUDIT_INPUT_SCHEMA_VERSION,
            "expected_current_implementation_sha256": implementation,
            "thresholds": {},
        },
        "candidate": {
            "model": {
                "model_fingerprint": contract["model_fingerprint"],
                "manifest_sha256": contract["bundle_manifest_sha256"],
                "weights_sha256": contract["bundle_weights_sha256"],
            },
            "implementation": {
                "current_implementation_sha256": implementation,
            },
            "paired_lineage": {
                "available": True,
                "sha256": lineage_sha256,
                "record_count": lineage_record_count,
                "unique_episode_uid_count": (
                    lineage_unique_episode_uid_count
                ),
            },
        },
        "artifact_evidence": [],
        "limitations": {},
    }


def _fixture(tmp_path: Path) -> dict[str, Any]:
    source_root = tmp_path / "development"
    source = _source_bundle(source_root)

    heldout_path = tmp_path / "heldout.json"
    heldout_sha = _write_content_json(
        heldout_path, _heldout_payload(source)
    )
    heldout = json.loads(heldout_path.read_text(encoding="utf-8"))

    lineage_path = tmp_path / "paired_episode_lineage.jsonl"
    lineage_sha = _write_lineage(lineage_path)

    paired_path = tmp_path / "paired.json"
    paired_sha = _write_content_json(
        paired_path,
        _paired_payload(
            source,
            heldout_sha,
            heldout["content_sha256"],
            lineage_sha,
        ),
    )
    paired = json.loads(paired_path.read_text(encoding="utf-8"))

    audit_path = tmp_path / "audit.json"
    audit_sha = _write_content_json(
        audit_path,
        _audit_payload(
            source,
            heldout_sha,
            heldout["content_sha256"],
            paired_sha,
            paired["content_sha256"],
            lineage_sha,
        ),
    )
    return {
        "source": source,
        "source_root": source_root,
        "heldout_path": heldout_path,
        "heldout_sha256": heldout_sha,
        "paired_path": paired_path,
        "paired_sha256": paired_sha,
        "lineage_path": lineage_path,
        "lineage_sha256": lineage_sha,
        "audit_path": audit_path,
        "audit_sha256": audit_sha,
    }


def _inputs(fixture: dict[str, Any]) -> TrackletG1EvidenceInputs:
    source = fixture["source"]
    return TrackletG1EvidenceInputs(
        development_bundle_dir=fixture["source_root"],
        expected_bundle_manifest_sha256=source["manifest_sha256"],
        expected_bundle_weights_sha256=source["weights_sha256"],
        expected_bundle_checksums_sha256=source["checksums_sha256"],
        heldout_report_path=fixture["heldout_path"],
        expected_heldout_report_sha256=fixture["heldout_sha256"],
        paired_shadow_report_path=fixture["paired_path"],
        expected_paired_shadow_report_sha256=fixture["paired_sha256"],
        paired_shadow_lineage_path=fixture["lineage_path"],
        expected_paired_shadow_lineage_sha256=(
            fixture["lineage_sha256"]
        ),
        d6_audit_path=fixture["audit_path"],
        expected_d6_audit_sha256=fixture["audit_sha256"],
    )


def _rewrite_audit(
    fixture: dict[str, Any],
    update: Callable[[dict[str, Any]], None],
) -> None:
    payload = json.loads(
        fixture["audit_path"].read_text(encoding="utf-8")
    )
    payload.pop("content_sha256")
    update(payload)
    fixture["audit_sha256"] = _write_content_json(
        fixture["audit_path"], payload
    )


def _rewrite_paired(
    fixture: dict[str, Any],
    update: Callable[[dict[str, Any]], None],
) -> None:
    payload = json.loads(
        fixture["paired_path"].read_text(encoding="utf-8")
    )
    payload.pop("content_sha256")
    update(payload)
    fixture["paired_sha256"] = _write_content_json(
        fixture["paired_path"], payload
    )


def _rewrite_bundle_manifest_and_checksums(
    bundle: Path,
    update: Callable[[dict[str, Any]], None],
) -> None:
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    update(manifest)
    manifest_path.write_bytes(_canonical_json_bytes(manifest))
    checksum_text = "".join(
        f"{sha256_file(bundle / filename)}  {filename}\n"
        for filename in sorted(G1_BUNDLE_CHECKSUM_FILES)
    )
    (bundle / "SHA256SUMS").write_text(
        checksum_text,
        encoding="ascii",
    )


def _assemble(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    fixture = _fixture(tmp_path)
    output = tmp_path / "admitted-v5"
    assemble_tracklet_g1_bundle(output, _inputs(fixture))
    return fixture, output


def test_positive_fixture_atomically_assembles_and_public_runtime_loads(
    tmp_path: Path,
) -> None:
    fixture, output = _assemble(tmp_path)

    assert output.is_dir()
    expected_files = {
        "manifest.json",
        "weights.pt",
        "SHA256SUMS",
        HELDOUT_EVIDENCE_FILENAME,
        PAIRED_SHADOW_EVIDENCE_FILENAME,
        PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
        D6_AUDIT_EVIDENCE_FILENAME,
    }
    actual_files = {
        str(path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files

    scorer = load_tracklet_model_bundle(output)
    shadow_runtime = load_tracklet_model_bundle_for_runtime(output)
    assist_runtime = load_tracklet_model_bundle_for_runtime(
        output, require_g1_assist_eligible=True
    )
    admission = scorer.manifest["admission"]
    assert scorer.available is True
    assert shadow_runtime.available is True
    assert assist_runtime.available is False
    assert (
        assist_runtime.failure_reason
        == G1_ASSIST_AUTHORITY_NOT_GRANTED_REASON
    )
    assert (
        scorer.manifest["schema_version"]
        == G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION
    )
    assert admission["g1_assist_eligible"] is True
    assert admission["default_model"] is False
    assert admission["global_track_id_authority"] is False
    assert (
        admission["status"]
        == "g1_evidence_eligible_not_authorized"
    )
    authority_contract = admission["authority_contract"]
    assert (
        authority_contract["schema_version"]
        == TRACKLET_G1_AUTHORITY_CONTRACT_SCHEMA_VERSION
    )
    assert authority_contract["evidence_audit_passed"] is True
    assert authority_contract["evidence_eligible"] is True
    assert set(authority_contract["runtime_authority"]) == set(
        TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS
    )
    assert not any(authority_contract["runtime_authority"].values())
    assert (
        authority_contract["d6_external_audit_sha256"]
        == fixture["audit_sha256"]
    )
    assert (
        admission["report"]["authority_contract"]
        == authority_contract
    )
    assert (
        admission["report"]["schema_version"]
        == TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION
    )
    assert (
        admission["report"]["d6_external_audit_sha256"]
        == fixture["audit_sha256"]
    )
    lineage_record = scorer.manifest["evidence"][
        "paired_shadow_lineage"
    ]
    assert lineage_record == {
        "filename": PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME,
        "sha256": fixture["lineage_sha256"],
        "record_count": 900,
        "unique_episode_uid_count": 900,
    }
    assert (
        admission["report"]["paired_shadow_lineage_sha256"]
        == fixture["lineage_sha256"]
    )
    assert (
        admission["report"]["paired_shadow_lineage_record_count"]
        == 900
    )
    assert (
        admission["report"][
            "paired_shadow_lineage_unique_episode_uid_count"
        ]
        == 900
    )
    assert (
        output / PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME
    ).read_bytes() == fixture["lineage_path"].read_bytes()
    checksums = {
        line.split("  ")[1]
        for line in (output / "SHA256SUMS").read_text(
            encoding="ascii"
        ).splitlines()
    }
    assert checksums == set(G1_BUNDLE_CHECKSUM_FILES)
    assert not tuple(output.parent.glob(f".{output.name}.staging-*"))


def test_missing_paired_lineage_input_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["lineage_path"].unlink()

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "missing-lineage",
            _inputs(fixture),
        )

    assert exc_info.value.code == "input_missing.paired_shadow_lineage"


def test_paired_lineage_input_hash_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    with fixture["lineage_path"].open("ab") as stream:
        stream.write(_canonical_json_bytes({"episode_uid": "extra"}))

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "tampered-lineage",
            _inputs(fixture),
        )

    assert (
        exc_info.value.code
        == "input_sha256_mismatch.paired_shadow_lineage"
    )


@pytest.mark.parametrize(
    ("record", "error_code"),
    [
        ({"episode_uid": ""}, "paired_lineage_episode_uid_invalid"),
        ({"episode_uid": "   "}, "paired_lineage_episode_uid_invalid"),
        (["episode-0000"], "paired_lineage_record_type_invalid"),
    ],
)
def test_paired_lineage_record_validation_fails_closed(
    tmp_path: Path,
    record: Any,
    error_code: str,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["lineage_path"].write_bytes(_canonical_json_bytes(record))
    fixture["lineage_sha256"] = sha256_file(fixture["lineage_path"])

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"invalid-record-{error_code}",
            _inputs(fixture),
        )

    assert exc_info.value.code == error_code


def test_duplicate_paired_lineage_episode_uid_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["lineage_sha256"] = _write_lineage(
        fixture["lineage_path"],
        duplicate_last_uid=True,
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "duplicate-lineage-uid",
            _inputs(fixture),
        )

    assert (
        exc_info.value.code
        == "paired_lineage_duplicate_episode_uid"
    )


def test_paired_lineage_requires_formal_900_records(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["lineage_sha256"] = _write_lineage(
        fixture["lineage_path"],
        record_count=899,
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "short-lineage",
            _inputs(fixture),
        )

    assert (
        exc_info.value.code
        == "paired_lineage_formal_record_count_mismatch"
    )


def test_legacy_paired_report_lineage_file_field_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    def use_legacy_field(payload: dict[str, Any]) -> None:
        lineage = payload["paired_lineage"]
        lineage["file"] = lineage.pop("filename")

    _rewrite_paired(fixture, use_legacy_field)

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "legacy-paired-lineage-field",
            _inputs(fixture),
        )

    assert exc_info.value.code == "paired_lineage_fields_mismatch"


def test_paired_report_lineage_count_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_paired(
        fixture,
        lambda payload: payload["paired_lineage"].__setitem__(
            "record_count", 899
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "paired-lineage-count-mismatch",
            _inputs(fixture),
        )

    assert exc_info.value.code == "paired_lineage_record_count_mismatch"


@pytest.mark.parametrize(
    ("field_name", "value", "error_code"),
    [
        (
            "sha256",
            "9" * 64,
            "d6_paired_lineage_sha256_mismatch",
        ),
        (
            "record_count",
            899,
            "d6_paired_lineage_record_count_mismatch",
        ),
        (
            "unique_episode_uid_count",
            899,
            "d6_paired_lineage_unique_episode_uid_count_mismatch",
        ),
    ],
)
def test_d6_paired_lineage_cross_binding_fails_closed(
    tmp_path: Path,
    field_name: str,
    value: Any,
    error_code: str,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: payload["candidate"]["paired_lineage"].__setitem__(
            field_name, value
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"d6-lineage-{field_name}",
            _inputs(fixture),
        )

    assert exc_info.value.code == error_code


def test_d6_fail_closed_rejects_without_output_or_staging(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    def fail(payload: dict[str, Any]) -> None:
        payload["audit_passed"] = False
        payload["status"] = "fail_closed"
        payload["fail_closed"] = True
        payload["blocker_codes"] = ["synthetic_single_feature_shortcut"]
        contract = payload["d5_consumer_contract"]
        contract["d6_external_audit_passed"] = False
        contract["failure_reasons"] = [
            "synthetic_single_feature_shortcut"
        ]

    _rewrite_audit(fixture, fail)
    output = tmp_path / "rejected-v5"

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(output, _inputs(fixture))

    assert exc_info.value.code == "d6_external_audit_fail_closed"
    assert not output.exists()
    assert not tuple(output.parent.glob(f".{output.name}.staging-*"))


@pytest.mark.parametrize(
    ("case_name", "update"),
    [
        (
            "missing",
            lambda authority: authority.pop("assignment_authority_granted"),
        ),
        (
            "extra",
            lambda authority: authority.__setitem__(
                "camera_authority_granted", False
            ),
        ),
        (
            "misspelled",
            lambda authority: (
                authority.pop("failover_authority_granted"),
                authority.__setitem__(
                    "failover_authority_grant", False
                ),
            ),
        ),
        (
            "reason_only",
            lambda authority: [
                authority.pop(name)
                for name in TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS
            ],
        ),
        (
            "legacy_v1_four_fields",
            lambda authority: (
                authority.pop("assignment_authority_granted"),
                authority.pop("failover_authority_granted"),
            ),
        ),
    ],
)
def test_d6_authority_v2_exact_field_set_is_required(
    tmp_path: Path,
    case_name: str,
    update: Callable[[dict[str, Any]], Any],
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: update(payload["authority"]),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"authority-{case_name}",
            _inputs(fixture),
        )

    assert exc_info.value.code == "d6_authority_fields_mismatch"


@pytest.mark.parametrize(
    "field_name",
    TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS,
)
def test_each_d6_runtime_authority_true_is_rejected(
    tmp_path: Path,
    field_name: str,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: payload["authority"].__setitem__(
            field_name, True
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"authority-true-{field_name}",
            _inputs(fixture),
        )

    assert (
        exc_info.value.code
        == f"d6_authority_not_closed.{field_name}"
    )


@pytest.mark.parametrize(
    "field_name",
    TRACKLET_G1_RUNTIME_AUTHORITY_FIELDS,
)
def test_each_d6_runtime_authority_requires_strict_bool(
    tmp_path: Path,
    field_name: str,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: payload["authority"].__setitem__(
            field_name, 0
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"authority-type-{field_name}",
            _inputs(fixture),
        )

    assert (
        exc_info.value.code
        == f"d6_type_invalid.authority.{field_name}"
    )


def test_unknown_d6_audit_schema_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: payload.__setitem__(
            "schema_version",
            "d6.d5-g1-external-audit.v2-unknown",
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "unknown-d6-schema",
            _inputs(fixture),
        )

    assert exc_info.value.code == "d6_schema_mismatch"


def test_legacy_d6_external_audit_v1_is_rejected(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: payload.__setitem__(
            "schema_version",
            D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION,
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "legacy-d6-v1",
            _inputs(fixture),
        )

    assert (
        exc_info.value.code
        == "legacy_d6_external_audit_schema_unsupported"
    )


@pytest.mark.parametrize(
    ("contract_name", "update", "error_code"),
    [
        (
            "input",
            lambda payload: payload["input_contract"].__setitem__(
                "schema_version",
                "d6.d5-g1-external-audit-input.v2",
            ),
            "d6_input_contract_schema_mismatch",
        ),
        (
            "consumer",
            lambda payload: payload["d5_consumer_contract"].__setitem__(
                "schema_version",
                "d6.d5-g1-external-audit-consumer.v2",
            ),
            "d6_consumer_schema_mismatch",
        ),
    ],
)
def test_d6_input_and_consumer_v1_schemas_are_independent(
    tmp_path: Path,
    contract_name: str,
    update: Callable[[dict[str, Any]], Any],
    error_code: str,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(fixture, update)

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"{contract_name}-schema-mismatch",
            _inputs(fixture),
        )

    assert exc_info.value.code == error_code


def test_d6_authority_reason_cannot_replace_permission_fields(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)

    def replace_with_reason(payload: dict[str, Any]) -> None:
        payload["authority"] = {
            "reason": "all permissions are described as false"
        }

    _rewrite_audit(fixture, replace_with_reason)

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "reason-only",
            _inputs(fixture),
        )

    assert exc_info.value.code == "d6_authority_fields_mismatch"


@pytest.mark.parametrize("reason", ["", "   ", None, False])
def test_d6_authority_reason_requires_nonempty_text(
    tmp_path: Path,
    reason: Any,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(
        fixture,
        lambda payload: payload["authority"].__setitem__(
            "reason", reason
        ),
    )

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / "invalid-reason",
            _inputs(fixture),
        )

    assert exc_info.value.code == "d6_authority_reason_invalid"


def test_missing_input_rejects_without_half_product(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["heldout_path"].unlink()
    output = tmp_path / "missing"

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(output, _inputs(fixture))

    assert exc_info.value.code == "input_missing.heldout_report"
    assert not output.exists()


def test_input_file_and_content_tampering_fail_closed(
    tmp_path: Path,
) -> None:
    file_fixture = _fixture(tmp_path / "file")
    file_fixture["paired_path"].write_bytes(
        file_fixture["paired_path"].read_bytes() + b" "
    )
    with pytest.raises(TrackletG1EvidenceAssemblyError) as file_exc:
        assemble_tracklet_g1_bundle(
            tmp_path / "file-output", _inputs(file_fixture)
        )
    assert (
        file_exc.value.code
        == "input_sha256_mismatch.paired_shadow_report"
    )

    content_fixture = _fixture(tmp_path / "content")
    payload = json.loads(
        content_fixture["heldout_path"].read_text(encoding="utf-8")
    )
    payload["heldout_corpus"]["episode_count"] = 901
    content_fixture["heldout_path"].write_bytes(
        _canonical_json_bytes(payload)
    )
    content_fixture["heldout_sha256"] = sha256_file(
        content_fixture["heldout_path"]
    )
    with pytest.raises(TrackletG1EvidenceAssemblyError) as content_exc:
        assemble_tracklet_g1_bundle(
            tmp_path / "content-output", _inputs(content_fixture)
        )
    assert (
        content_exc.value.code
        == "input_content_sha256_mismatch.heldout_report"
    )


@pytest.mark.parametrize(
    ("name", "update", "expected_code"),
    [
        (
            "model",
            lambda payload: payload["d5_consumer_contract"].__setitem__(
                "model_fingerprint", "sha256:" + "9" * 64
            ),
            "evidence_cross_binding_mismatch.model_fingerprint",
        ),
        (
            "dataset",
            lambda payload: payload["d5_consumer_contract"].__setitem__(
                "dataset_manifest_sha256", "9" * 64
            ),
            "evidence_cross_binding_mismatch.dataset_manifest_sha256",
        ),
        (
            "implementation",
            lambda payload: (
                payload["d5_consumer_contract"].__setitem__(
                    "implementation_sha256", "9" * 64
                ),
                payload["input_contract"].__setitem__(
                    "expected_current_implementation_sha256", "9" * 64
                ),
            ),
            "evidence_cross_binding_mismatch.implementation_sha256",
        ),
    ],
)
def test_cross_model_dataset_and_implementation_are_rejected(
    tmp_path: Path,
    name: str,
    update: Callable[[dict[str, Any]], None],
    expected_code: str,
) -> None:
    fixture = _fixture(tmp_path)
    _rewrite_audit(fixture, update)

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(
            tmp_path / f"cross-{name}", _inputs(fixture)
        )
    assert exc_info.value.code == expected_code


def test_unavailable_field_and_strict_bool_int_types_are_rejected(
    tmp_path: Path,
) -> None:
    unavailable = _fixture(tmp_path / "unavailable")

    def mark_unavailable(payload: dict[str, Any]) -> None:
        payload["d5_consumer_contract"]["field_availability"][
            "implementation_sha256"
        ] = {"available": False, "reason": "not measured"}

    _rewrite_audit(unavailable, mark_unavailable)
    with pytest.raises(TrackletG1EvidenceAssemblyError) as unavailable_exc:
        assemble_tracklet_g1_bundle(
            tmp_path / "unavailable-output", _inputs(unavailable)
        )
    assert (
        unavailable_exc.value.code
        == "d6_field_unavailable.implementation_sha256"
    )

    boolean = _fixture(tmp_path / "boolean")
    _rewrite_audit(
        boolean,
        lambda payload: payload["d5_consumer_contract"].__setitem__(
            "formal_evaluation", 1
        ),
    )
    with pytest.raises(TrackletG1EvidenceAssemblyError) as boolean_exc:
        assemble_tracklet_g1_bundle(
            tmp_path / "boolean-output", _inputs(boolean)
        )
    assert boolean_exc.value.code == "d6_type_invalid.formal_evaluation"

    integer = _fixture(tmp_path / "integer")
    _rewrite_audit(
        integer,
        lambda payload: payload["d5_consumer_contract"].__setitem__(
            "unseen_seed_count", True
        ),
    )
    with pytest.raises(TrackletG1EvidenceAssemblyError) as integer_exc:
        assemble_tracklet_g1_bundle(
            tmp_path / "integer-output", _inputs(integer)
        )
    assert integer_exc.value.code == "d6_type_invalid.unseen_seed_count"


def test_packaged_evidence_tamper_and_missing_file_fail_public_load(
    tmp_path: Path,
) -> None:
    _, tampered = _assemble(tmp_path / "tampered")
    evidence = tampered / HELDOUT_EVIDENCE_FILENAME
    evidence.write_bytes(evidence.read_bytes() + b" ")
    with pytest.raises(ModelBundleValidationError) as tamper_exc:
        load_tracklet_model_bundle(tampered)
    assert tamper_exc.value.code == "evidence_sha_mismatch"
    runtime = load_tracklet_model_bundle_for_runtime(
        tampered, require_g1_assist_eligible=True
    )
    assert runtime.available is False
    assert runtime.failure_reason == "bundle_evidence_sha_mismatch"

    _, missing = _assemble(tmp_path / "missing")
    (missing / PAIRED_SHADOW_EVIDENCE_FILENAME).unlink()
    with pytest.raises(ModelBundleValidationError) as missing_exc:
        load_tracklet_model_bundle(missing)
    assert missing_exc.value.code == "evidence_missing"


def test_packaged_lineage_tamper_and_missing_file_fail_public_load(
    tmp_path: Path,
) -> None:
    _, tampered = _assemble(tmp_path / "lineage-tampered")
    lineage = tampered / PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME
    lineage.write_bytes(lineage.read_bytes() + b" ")
    with pytest.raises(ModelBundleValidationError) as tamper_exc:
        load_tracklet_model_bundle(tampered)
    assert tamper_exc.value.code == "evidence_sha_mismatch"

    _, missing = _assemble(tmp_path / "lineage-missing")
    (
        missing / PAIRED_SHADOW_LINEAGE_EVIDENCE_FILENAME
    ).unlink()
    with pytest.raises(ModelBundleValidationError) as missing_exc:
        load_tracklet_model_bundle(missing)
    assert missing_exc.value.code == "evidence_missing"


@pytest.mark.parametrize(
    ("field_name", "value", "error_code"),
    [
        (
            "paired_shadow_lineage_sha256",
            "9" * 64,
            "evidence_admission_report_cross_binding_mismatch",
        ),
        ("paired_shadow_lineage_record_count", 899, "admission_invalid"),
        (
            "paired_shadow_lineage_unique_episode_uid_count",
            899,
            "admission_invalid",
        ),
    ],
)
def test_admission_report_lineage_tamper_fails_public_load(
    tmp_path: Path,
    field_name: str,
    value: Any,
    error_code: str,
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: manifest["admission"]["report"].__setitem__(
            field_name, value
        ),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert exc_info.value.code == error_code


def test_admission_report_missing_lineage_field_fails_public_load(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: manifest["admission"]["report"].pop(
            "paired_shadow_lineage_sha256"
        ),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert exc_info.value.code == "admission_invalid"


def test_manifest_lineage_record_tamper_fails_strict_revalidation(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: manifest["evidence"][
            "paired_shadow_lineage"
        ].__setitem__("record_count", 899),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert (
        exc_info.value.code
        == "evidence_evidence_record_count_mismatch."
        "paired_shadow_lineage"
    )


def test_manifest_missing_lineage_record_fails_strict_revalidation(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: manifest["evidence"].pop(
            "paired_shadow_lineage"
        ),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert exc_info.value.code == "evidence_evidence_fields_mismatch"


def test_manifest_evidence_content_cross_binding_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["evidence"]["heldout"]["content_sha256"] = "9" * 64
    manifest_path.write_bytes(_canonical_json_bytes(manifest))
    checksum_lines = []
    for filename in sorted(G1_BUNDLE_CHECKSUM_FILES):
        checksum_lines.append(
            f"{sha256_file(output / filename)}  {filename}\n"
        )
    (output / "SHA256SUMS").write_text(
        "".join(checksum_lines), encoding="ascii"
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)
    assert (
        exc_info.value.code
        == "evidence_evidence_content_cross_binding_mismatch.heldout_report"
    )


@pytest.mark.parametrize(
    ("case_name", "update"),
    [
        (
            "legacy_contract_schema",
            lambda contract: contract.__setitem__(
                "schema_version",
                "d5.tracklet-g1-authority-contract.v1",
            ),
        ),
        (
            "missing_permission",
            lambda contract: contract["runtime_authority"].pop(
                "assignment_authority_granted"
            ),
        ),
        (
            "extra_permission",
            lambda contract: contract["runtime_authority"].__setitem__(
                "camera_authority_granted", False
            ),
        ),
        (
            "permission_true",
            lambda contract: contract["runtime_authority"].__setitem__(
                "control_authority_granted", True
            ),
        ),
        (
            "permission_typo",
            lambda contract: (
                contract["runtime_authority"].pop(
                    "failover_authority_granted"
                ),
                contract["runtime_authority"].__setitem__(
                    "failover_authority_grant", False
                ),
            ),
        ),
    ],
)
def test_v5_manifest_authority_contract_v2_is_exact_and_closed(
    tmp_path: Path,
    case_name: str,
    update: Callable[[dict[str, Any]], Any],
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: update(
            manifest["admission"]["authority_contract"]
        ),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert exc_info.value.code == "admission_invalid"
    runtime = load_tracklet_model_bundle_for_runtime(
        output,
        require_g1_assist_eligible=True,
    )
    assert runtime.available is False
    assert runtime.failure_reason == "bundle_admission_invalid"


def test_legacy_v4_bundle_is_not_reinterpreted_as_v5(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: manifest.__setitem__(
            "schema_version",
            LEGACY_G1_ADMITTED_MODEL_BUNDLE_SCHEMA_VERSION,
        ),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert (
        exc_info.value.code
        == "legacy_g1_bundle_schema_unsupported"
    )
    runtime = load_tracklet_model_bundle_for_runtime(output)
    assert runtime.available is False
    assert (
        runtime.failure_reason
        == "bundle_legacy_g1_bundle_schema_unsupported"
    )


@pytest.mark.parametrize(
    ("schema_version", "error_code"),
    [
        (
            LEGACY_TRACKLET_G1_ADMISSION_REPORT_SCHEMA_VERSION,
            "legacy_g1_admission_report_schema_unsupported",
        ),
        (
            "d5.tracklet-g1-admission-report.v3-unknown",
            "g1_admission_report_schema_mismatch",
        ),
    ],
)
def test_v5_rejects_legacy_or_unknown_admission_report_schema(
    tmp_path: Path,
    schema_version: str,
    error_code: str,
) -> None:
    _, output = _assemble(tmp_path)
    _rewrite_bundle_manifest_and_checksums(
        output,
        lambda manifest: manifest["admission"]["report"].__setitem__(
            "schema_version",
            schema_version,
        ),
    )

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert exc_info.value.code == error_code
    runtime = load_tracklet_model_bundle_for_runtime(output)
    assert runtime.available is False
    assert runtime.failure_reason == f"bundle_{error_code}"


def test_post_assembly_verifier_rechecks_packaged_d6_authority_v2(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    audit_path = output / D6_AUDIT_EVIDENCE_FILENAME
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.pop("content_sha256")
    audit["authority"]["g1_assist_granted"] = True
    audit_sha256 = _write_content_json(audit_path, audit)
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_content_sha256 = audit_payload["content_sha256"]

    def bind_tampered_audit(manifest: dict[str, Any]) -> None:
        evidence = manifest["evidence"]["d6_external_audit"]
        evidence["sha256"] = audit_sha256
        evidence["content_sha256"] = audit_content_sha256
        admission = manifest["admission"]
        for contract in (
            admission["authority_contract"],
            admission["report"]["authority_contract"],
        ):
            contract["d6_external_audit_sha256"] = audit_sha256
            contract[
                "d6_external_audit_content_sha256"
            ] = audit_content_sha256
        admission["report"]["d6_external_audit_sha256"] = audit_sha256
        admission["report"][
            "d6_external_audit_content_sha256"
        ] = audit_content_sha256

    _rewrite_bundle_manifest_and_checksums(output, bind_tampered_audit)

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert (
        exc_info.value.code
        == "evidence_d6_authority_not_closed.g1_assist_granted"
    )


def test_post_assembly_verifier_rejects_packaged_legacy_d6_v1(
    tmp_path: Path,
) -> None:
    _, output = _assemble(tmp_path)
    audit_path = output / D6_AUDIT_EVIDENCE_FILENAME
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit.pop("content_sha256")
    audit["schema_version"] = D6_LEGACY_EXTERNAL_AUDIT_SCHEMA_VERSION
    audit_sha256 = _write_content_json(audit_path, audit)
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_content_sha256 = audit_payload["content_sha256"]

    def bind_legacy_audit(manifest: dict[str, Any]) -> None:
        evidence = manifest["evidence"]["d6_external_audit"]
        evidence["sha256"] = audit_sha256
        evidence["content_sha256"] = audit_content_sha256
        admission = manifest["admission"]
        for contract in (
            admission["authority_contract"],
            admission["report"]["authority_contract"],
        ):
            contract["d6_external_audit_sha256"] = audit_sha256
            contract[
                "d6_external_audit_content_sha256"
            ] = audit_content_sha256
        admission["report"]["d6_external_audit_sha256"] = audit_sha256
        admission["report"][
            "d6_external_audit_content_sha256"
        ] = audit_content_sha256

    _rewrite_bundle_manifest_and_checksums(output, bind_legacy_audit)

    with pytest.raises(ModelBundleValidationError) as exc_info:
        load_tracklet_model_bundle(output)

    assert (
        exc_info.value.code
        == "evidence_legacy_d6_external_audit_schema_unsupported"
    )
    runtime = load_tracklet_model_bundle_for_runtime(output)
    assert runtime.available is False
    assert (
        runtime.failure_reason
        == (
            "bundle_evidence_"
            "legacy_d6_external_audit_schema_unsupported"
        )
    )


def test_nonempty_output_is_rejected_without_modifying_existing_files(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    output = tmp_path / "occupied"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("unchanged", encoding="utf-8")
    marker_sha = sha256_file(marker)

    with pytest.raises(TrackletG1EvidenceAssemblyError) as exc_info:
        assemble_tracklet_g1_bundle(output, _inputs(fixture))

    assert exc_info.value.code == "output_not_empty"
    assert sha256_file(marker) == marker_sha
    assert set(output.iterdir()) == {marker}


def test_failure_never_rewrites_source_or_evidence(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    before = {
        path: sha256_file(path)
        for path in (
            fixture["source_root"] / "manifest.json",
            fixture["source_root"] / "weights.pt",
            fixture["source_root"] / "SHA256SUMS",
            fixture["heldout_path"],
            fixture["paired_path"],
            fixture["audit_path"],
        )
    }

    def fail(payload: dict[str, Any]) -> None:
        payload["audit_passed"] = False
        payload["status"] = "fail_closed"
        payload["fail_closed"] = True
        payload["blocker_codes"] = ["implementation_lineage_mismatch"]
        payload["d5_consumer_contract"][
            "d6_external_audit_passed"
        ] = False
        payload["d5_consumer_contract"]["failure_reasons"] = [
            "implementation_lineage_mismatch"
        ]

    _rewrite_audit(fixture, fail)
    before[fixture["audit_path"]] = sha256_file(fixture["audit_path"])
    output = tmp_path / "no-product"
    with pytest.raises(TrackletG1EvidenceAssemblyError):
        assemble_tracklet_g1_bundle(output, _inputs(fixture))

    assert not output.exists()
    assert {
        path: sha256_file(path) for path in before
    } == before


def test_empty_output_directory_can_be_atomically_replaced(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    output = tmp_path / "empty-output"
    output.mkdir()

    result = assemble_tracklet_g1_bundle(output, _inputs(fixture))

    assert result.bundle_dir == output
    assert (output / "manifest.json").is_file()
