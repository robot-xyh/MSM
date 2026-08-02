from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d3_assignment_planner.a1_v3_data_contract import (
    A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH,
    A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS,
    canonical_json_sha256,
    validate_a1_v3_pre_generation_readiness,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_GENERATION_REQUEST_PATH = (
    MODULE_ROOT
    / "configs/"
    "a1_source_independent_v3_source_generation_request_readiness_v1.json"
)
GENERATOR_CONFIG_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generator_config_v1.json"
)
MAIN_REGISTRY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_main_allocation_registry_v1.json"
)
SCHEDULE_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generation_schedule_v1.json"
)
SIDECAR_POLICY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_sidecar_classification_policy_v1.json"
)
GLOBAL_REGISTRY_PATH = (
    MODULE_ROOT.parent
    / "scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="ascii"))


def _write_artifact(path: Path, payload: dict, *, rehash: bool = True) -> None:
    if rehash:
        payload.pop("content_sha256", None)
        payload["content_sha256"] = canonical_json_sha256(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="ascii",
    )


def _validate(
    *,
    source_generation_request_path: Path = SOURCE_GENERATION_REQUEST_PATH,
    sidecar_classification_policy_path: Path = SIDECAR_POLICY_PATH,
):
    return validate_a1_v3_pre_generation_readiness(
        generator_config_path=GENERATOR_CONFIG_PATH,
        global_registry_path=GLOBAL_REGISTRY_PATH,
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
        source_generation_request_path=source_generation_request_path,
        sidecar_classification_policy_path=sidecar_classification_policy_path,
    )


def test_exact_source_generation_request_is_ready_without_generation_authority() -> None:
    report = _validate()
    assert report.status == "ready"
    assert report.ready is True
    assert report.reason_codes == ()
    assert report.source_generation_request_ready is True
    assert report.source_generation_request_path == (
        A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH
    )
    assert report.source_generation_request_sha256 == sha256(
        SOURCE_GENERATION_REQUEST_PATH.read_bytes()
    ).hexdigest()

    payload = report.to_dict()
    stable_fields = (
        "source_generation_request_path",
        "source_generation_request_sha256",
        "source_generation_request_ready",
    )
    for field in stable_fields:
        assert payload["producer_capability"][field] == payload[field]
    assert payload["request_permissions"]["source_generation_request"] is True
    assert not any(
        value
        for name, value in payload["request_permissions"].items()
        if name != "source_generation_request"
    )
    assert not any(payload["permissions"].values())
    assert payload["generation_authorized"] is False
    assert payload["validation_payload_read"] is False
    assert payload["formal_seed_payload_read"] is False
    assert payload["producer_capability"]["generation_authorized"] is False

    artifact = _json(SOURCE_GENERATION_REQUEST_PATH)
    assert artifact["status"] == (
        "request_ready_frozen_runtime_quota_probe_passed"
    )
    assert [
        name for name, value in artifact["permissions"].items() if value
    ] == ["source_generation_request"]
    probe = artifact["producer_capability"]["frozen_runtime_quota_probe"]
    assert probe["audited_cell_count"] == 15
    assert probe["audited_recipe_count"] == 15
    assert len(probe["runtime_results"]) == 15
    assert len(probe["passing_runtime_to_writer_recipe_ids"]) == 15
    assert probe["blocking_cell_ids"] == []
    assert probe["writer_staged_cell_count"] == 15
    assert probe["all_frozen_cells_quota_ready"] is True
    assert probe["online_truth_use_count"] == 0
    assert probe["blocker_codes"] == []
    assert all(
        row["quota_met"] is True
        and row["writer_staged"] is True
        and row["positive_frame_count"] >= 3
        and row["negative_frame_count"] >= 3
        and row["hard_negative_frame_count"] >= 2
        and row["reason_codes"] == []
        for row in probe["runtime_results"]
    )


def test_missing_request_or_classification_policy_fails_closed(
    tmp_path: Path,
) -> None:
    missing_request = _validate(
        source_generation_request_path=tmp_path / "missing-request.json"
    )
    assert missing_request.status == "fail_closed"
    assert missing_request.source_generation_request_ready is False
    assert missing_request.reason_codes == (
        "source_generation_request_read_failed",
    )
    assert not any(missing_request.to_dict()["request_permissions"].values())

    missing_policy = _validate(
        sidecar_classification_policy_path=tmp_path / "missing-policy.json"
    )
    assert missing_policy.status == "fail_closed"
    assert missing_policy.source_generation_request_ready is False
    assert missing_policy.reason_codes == (
        "sidecar_classification_policy_read_failed",
    )


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("content_hash", "source_generation_request_content_sha256_mismatch"),
        ("binding_hash", "source_generation_request_binding_mismatch"),
        ("schema", "source_generation_request_schema_contract_mismatch"),
        ("seed", "source_generation_request_seed_contract_mismatch"),
        ("allocation", "source_generation_request_seed_contract_mismatch"),
    ),
)
def test_request_hash_schema_seed_or_allocation_drift_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    payload = deepcopy(_json(SOURCE_GENERATION_REQUEST_PATH))
    rehash = True
    if mutation == "content_hash":
        payload["content_sha256"] = "0" * 64
        rehash = False
    elif mutation == "binding_hash":
        payload["bindings"]["frozen_request"]["file_sha256"] = "0" * 64
    elif mutation == "schema":
        payload["schema_contract"]["online_frame_schema_version"] = "wrong"
    elif mutation == "seed":
        payload["seed_contract"]["assigned_seed_minimum"] = 23001
    elif mutation == "allocation":
        payload["seed_contract"]["allocation_id"] = "wrong-allocation"
    path = tmp_path / f"{mutation}.json"
    _write_artifact(path, payload, rehash=rehash)

    report = _validate(source_generation_request_path=path)
    assert report.status == "fail_closed"
    assert report.ready is False
    assert report.source_generation_request_ready is False
    assert report.reason_codes == (expected_reason,)
    assert not any(report.to_dict()["request_permissions"].values())


def test_ready_request_cannot_disable_request_permission(tmp_path: Path) -> None:
    payload = deepcopy(_json(SOURCE_GENERATION_REQUEST_PATH))
    payload["permissions"]["source_generation_request"] = False
    path = tmp_path / "request-disabled.json"
    _write_artifact(path, payload)

    report = _validate(source_generation_request_path=path)
    assert report.status == "fail_closed"
    assert report.source_generation_request_ready is False
    assert report.reason_codes == (
        "source_generation_request_permission_mismatch",
    )


@pytest.mark.parametrize(
    "permission_name",
    tuple(
        name
        for name in A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS
        if name != "source_generation_request"
    ),
)
def test_any_generation_or_runtime_permission_escalation_fails_closed(
    tmp_path: Path,
    permission_name: str,
) -> None:
    payload = deepcopy(_json(SOURCE_GENERATION_REQUEST_PATH))
    payload["permissions"][permission_name] = True
    path = tmp_path / f"permission-{permission_name}.json"
    _write_artifact(path, payload)

    report = _validate(source_generation_request_path=path)
    assert report.status == "fail_closed"
    assert report.source_generation_request_ready is False
    assert report.reason_codes == (
        "source_generation_request_permission_mismatch",
    )
    assert not any(report.to_dict()["request_permissions"].values())
