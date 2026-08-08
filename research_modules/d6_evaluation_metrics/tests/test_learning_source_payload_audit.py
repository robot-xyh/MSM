from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from d6_evaluation_metrics import learning_source_payload_audit as audit


def _write(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return sha256(path.read_bytes()).hexdigest()


def test_synthetic_strict_payload_positive(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    digest = _write(
        path,
        {
            "measurement_timestamp": 1.0,
            "arrival_timestamp": 1.2,
            "state_covariance": [[2.0, 0.1], [0.1, 1.0]],
        },
    )
    item = audit._InventoryItem("payload.json", path.stat().st_size, digest)
    context = audit._SourceContext(
        module="D3",
        root=tmp_path,
        binding=SimpleNamespace(),
        preflight={},
        authorization={},
        result_path=path,
        result_size_bytes=0,
        inventory=(item,),
        inventory_by_path={"payload.json": item},
        parsed_json={},
        jsonl_records={},
    )

    audit._verify_inventory_files(context)
    audit._parse_inventory_documents(context)
    assert context.document_record_count == 1
    assert context.covariance_matrix_count == 1
    assert audit._validate_timestamp_pair(1.0, 1.2, "fixture") == pytest.approx(0.2)


@pytest.mark.parametrize(
    "content",
    [b'{"a":1,"a":2}', b'{"value":NaN}', b'{"value":Infinity}'],
)
def test_duplicate_key_and_nonfinite_json_fail_closed(content: bytes) -> None:
    with pytest.raises(audit.LearningSourcePayloadAuditError):
        audit._decode_json_object(content, "fixture")


@pytest.mark.parametrize("relative", ["../payload.json", "/tmp/payload.json", "a/../b"])
def test_inventory_path_traversal_fails_closed(relative: str) -> None:
    with pytest.raises(audit.LearningSourcePayloadAuditError):
        audit._safe_relative(relative, "inventory")


def test_inventory_symlink_and_hash_tamper_fail_closed(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    digest = _write(real, {"ok": True})
    link = tmp_path / "link.json"
    link.symlink_to(real.name)
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="symlink_forbidden"):
        audit._resolve_inventory_file(tmp_path, "link.json", "inventory")

    item = audit._InventoryItem("real.json", real.stat().st_size, "0" * 64)
    context = audit._SourceContext(
        module="D3",
        root=tmp_path,
        binding=SimpleNamespace(),
        preflight={},
        authorization={},
        result_path=real,
        result_size_bytes=0,
        inventory=(item,),
        inventory_by_path={"real.json": item},
        parsed_json={},
        jsonl_records={},
    )
    assert digest != item.sha256
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="sha256_mismatch"):
        audit._verify_inventory_files(context)


def test_truth_and_split_leakage_fail_closed() -> None:
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="truth_leakage"):
        audit._reject_online_truth({"actor_id": "intruder-1"}, "D5")
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="identity_leakage"):
        audit._reject_online_truth({"global_track_id": "GT3D-1"}, "D3")
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="split_leakage"):
        audit._require_disjoint({"train": {1, 2}, "validation": {2, 3}}, "fixture")


def test_timestamp_and_covariance_fail_closed() -> None:
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="arrival_before"):
        audit._validate_timestamp_pair(2.0, 1.0, "fixture")
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="not_symmetric"):
        audit._validate_covariance_matrix([[1.0, 0.3], [0.1, 1.0]], "fixture")
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="not_psd"):
        audit._validate_covariance_matrix([[1.0, 2.0], [2.0, 1.0]], "fixture")


def test_exact_audit_authorization_accepts_d4_schema_field_and_rejects_escalation() -> None:
    sources = []
    preflight_sources = {}
    bindings = []
    for module, field, schema in (
        ("D3", "schema_version", "d3-schema"),
        ("D4", "schema", "d4-schema"),
        ("D5", "schema_version", "d5-schema"),
    ):
        binding = SimpleNamespace(
            module=module,
            source_root=Path(f"/tmp/{module}"),
            source_git_commit="a" * 40,
            generation_authorization_sha256="b" * 64,
            module_request_sha256="c" * 64,
        )
        bindings.append(binding)
        preflight_sources[module] = {
            "manifest_schema_field": field,
            "manifest_schema_version": schema,
            "artifact_inventory_tree_sha256": "d" * 64,
        }
        sources.append(
            {
                "module": module,
                "source_root": f"/tmp/{module}",
                "source_git_commit": "a" * 40,
                "generation_authorization_sha256": "b" * 64,
                "module_request_sha256": "c" * 64,
                "manifest_schema_field": field,
                "manifest_schema_version": schema,
                "artifact_inventory_tree_sha256": "d" * 64,
            }
        )
    authorization = {
        "schema_version": audit.SOURCE_AUDIT_AUTHORIZATION_SCHEMA_VERSION,
        "authorization_id": "fixture-audit",
        "approved_at_utc": "2026-08-04T00:00:00Z",
        "approver_id": "fixture-user",
        "approval_reason": "fixture",
        "confirmation": audit.SOURCE_AUDIT_CONFIRMATION,
        "status": "approved_for_source_integrity_audit_only",
        "preflight_input_contract_sha256": "1" * 64,
        "preflight_report_file_sha256": "2" * 64,
        "preflight_result_sha256": "2" * 64,
        "sources": sources,
        "permissions": dict(audit._AUTHORIZATION_PERMISSION_VALUES),
    }
    contract = SimpleNamespace(sources=tuple(bindings))
    preflight = {"sources": preflight_sources}
    audit._validate_authorization(
        authorization,
        contract=contract,
        preflight=preflight,
        contract_sha="1" * 64,
        preflight_sha="2" * 64,
    )

    authorization["permissions"]["training"] = True
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="not_exact_audit_only"):
        audit._validate_authorization(
            authorization,
            contract=contract,
            preflight=preflight,
            contract_sha="1" * 64,
            preflight_sha="2" * 64,
        )


def test_missing_or_tampered_authorization_fails_before_payload(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="missing"):
        audit._load_bound_json_file(missing, "0" * 64, "authorization")
    path = tmp_path / "authorization.json"
    _write(path, {"status": "tampered"})
    with pytest.raises(audit.LearningSourcePayloadAuditError, match="sha256_mismatch"):
        audit._load_bound_json_file(path, "0" * 64, "authorization")


def test_d5_identity_layers_accept_exact_producer_schemas() -> None:
    audit._validate_d5_source_identity(
        {
            "global_track_id_created_count": 0,
            "global_track_id_ownership": "center_read_only",
            "global_track_id_rewritten_count": 0,
        }
    )
    audit._validate_d5_source_provenance(
        {
            "formal_seed_1000_1019_episode_read_count": 0,
            "online_truth_id_use_count": 0,
            "source_domain": "scalable_3d_point_mass_runtime",
            "synthetic_fixture_episode_count": 0,
            "v2_episode_or_sample_reuse": False,
            "v2_test_episode_or_sample_read_count": 0,
        }
    )
    identity = {
        "global_track_id_created_count": 0,
        "global_track_id_ownership": "center_read_only",
        "global_track_id_rewritten_count": 0,
        "online_truth_identity_use_count": 0,
    }
    audit._validate_d5_partition_identity(identity)
    audit._validate_d5_online_identity(identity)


def test_d5_descriptor_self_hash_matches_producer_newline_contract() -> None:
    payload = {"schema_version": "fixture", "name": "来源"}
    producer_bytes = (
        json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    assert audit._d5_producer_canonical_line_sha256(payload) == sha256(
        producer_bytes
    ).hexdigest()
    assert (
        audit._d5_producer_canonical_line_sha256(payload)
        != audit._canonical_sha256(payload)
    )
    producer_without_newline = producer_bytes[:-1]
    assert audit._d5_producer_canonical_line_sha256(payload) != sha256(
        producer_without_newline
    ).hexdigest()


@pytest.mark.parametrize(
    ("validator", "payload", "expected_code"),
    [
        (
            audit._validate_d5_source_identity,
            {
                "global_track_id_created_count": 0,
                "global_track_id_ownership": "center_read_only",
            },
            "d5_source_identity_contract_mismatch",
        ),
        (
            audit._validate_d5_source_identity,
            {
                "global_track_id_created_count": 1,
                "global_track_id_ownership": "center_read_only",
                "global_track_id_rewritten_count": 0,
            },
            "d5_source_identity_contract_mismatch",
        ),
        (
            audit._validate_d5_source_identity,
            {
                "global_track_id_created_count": 0,
                "global_track_id_ownership": "local",
                "global_track_id_rewritten_count": 0,
            },
            "d5_source_identity_contract_mismatch",
        ),
        (
            audit._validate_d5_source_provenance,
            {
                "formal_seed_1000_1019_episode_read_count": 0,
                "online_truth_id_use_count": 1,
                "source_domain": "scalable_3d_point_mass_runtime",
                "synthetic_fixture_episode_count": 0,
                "v2_episode_or_sample_reuse": False,
                "v2_test_episode_or_sample_read_count": 0,
            },
            "d5_source_provenance_contract_mismatch",
        ),
        (
            audit._validate_d5_partition_identity,
            {
                "global_track_id_created_count": 0,
                "global_track_id_ownership": "center_read_only",
                "global_track_id_rewritten_count": 0,
            },
            "d5_partition_identity_contract_mismatch",
        ),
        (
            audit._validate_d5_online_identity,
            {
                "global_track_id_created_count": 0,
                "global_track_id_ownership": "center_read_only",
                "global_track_id_rewritten_count": 1,
                "online_truth_identity_use_count": 0,
            },
            "d5_online_identity_contract_mismatch",
        ),
    ],
)
def test_d5_identity_layers_fail_closed(
    validator, payload: dict[str, object], expected_code: str
) -> None:
    with pytest.raises(audit.LearningSourcePayloadAuditError) as exc:
        validator(payload)
    assert exc.value.code == expected_code
