from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d4_distributed_fallback.region_resource_v8_development_contract import (
    canonical_v8_sha256,
)
from d4_distributed_fallback.region_resource_v8_main_allocation_readiness import (
    RegionResourceV8MainAllocationError,
    V8_GENERATION_REQUEST_PERMISSION_NAMES,
    default_v8_main_allocation_binding_path,
    default_v8_source_generation_request_path,
    validate_v8_main_allocation_binding_payload,
    validate_v8_main_allocation_pre_generation_readiness,
    validate_v8_source_generation_request_payload,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_BINDING_PATH = default_v8_main_allocation_binding_path()
_SOURCE_GENERATION_REQUEST_PATH = default_v8_source_generation_request_path()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_self_hashed_json(path: Path, payload: dict[str, object]) -> None:
    content = deepcopy(payload)
    content.pop("content_sha256", None)
    payload["content_sha256"] = canonical_v8_sha256(content)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, ensure_ascii=True) + "\n",
        encoding="ascii",
    )


def _copy_contract_fixture(tmp_path: Path) -> dict[str, Path]:
    request = _read_json(_SOURCE_GENERATION_REQUEST_PATH)
    binding = _read_json(_BINDING_PATH)
    references = request["references"]
    paths = {
        "source_generation_request": (
            _SOURCE_GENERATION_REQUEST_PATH.relative_to(_REPOSITORY_ROOT)
        ),
        "binding": references["main_allocation_binding"]["path"],
        "global_registry": binding["global_registry"]["path"],
        "request": binding["d4_frozen_contract"]["request_path"],
        "module_registry": binding["d4_frozen_contract"][
            "module_seed_registry_path"
        ],
        "writer": references["writer_resume_implementation"]["path"],
        "v8_contract": references["v8_contract_implementation"]["path"],
        "runtime_evidence": references["runtime_evidence_implementation"]["path"],
        "source_viability": references["source_viability_implementation"]["path"],
        "region_resource_policy": references[
            "region_resource_policy_implementation"
        ]["path"],
        "main_runtime_adapter": references[
            "main_runtime_adapter_implementation"
        ]["path"],
        "main_treatment": references["main_treatment_implementation"]["path"],
        "main_recipe": references["main_recipe_implementation"]["path"],
    }
    copied: dict[str, Path] = {}
    for name, logical in paths.items():
        source = _REPOSITORY_ROOT / logical
        target = tmp_path / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[name] = target
    return copied


def _validate_fixture(tmp_path: Path):
    paths = _copy_contract_fixture(tmp_path)
    return paths, validate_v8_main_allocation_pre_generation_readiness(
        binding_path=paths["binding"],
        source_generation_request_path=paths["source_generation_request"],
        repository_root=tmp_path,
    )


def _validate_copied_fixture(tmp_path: Path, paths: dict[str, Path]):
    return validate_v8_main_allocation_pre_generation_readiness(
        binding_path=paths["binding"],
        source_generation_request_path=paths["source_generation_request"],
        repository_root=tmp_path,
    )


def test_exact_main_allocation_binding_is_generation_prerequisite_ready() -> None:
    report = validate_v8_main_allocation_pre_generation_readiness(
        binding_path=_BINDING_PATH,
        repository_root=_REPOSITORY_ROOT,
    )

    assert report.status == "generation_prerequisites_ready_no_data_generated"
    assert report.generation_prerequisites_ready is True
    assert report.global_registry_validated is True
    assert report.global_overlap_policy_validated is True
    assert report.source_bindings_validated is True
    assert report.exact_seed_inventory_validated is True
    assert report.source_generation_request_ready is True
    assert report.source_generation_request_path == (
        "research_modules/d4_distributed_fallback/configs/"
        "region_resource_v8_train_source_generation_request_readiness_v1.json"
    )
    assert report.source_generation_request_sha256 == (
        "e93e7a79a3bfae055721fc21d9ba1591228c3d46f662922de2c04713076fe808"
    )
    assert report.writer_resume_safety_validated is True
    assert report.source_viability_audit_validated is True
    assert report.source_viability_episode_count == 324
    assert report.source_viability_frame_count == 972
    assert report.source_viability_cell_evidence_sha256 == (
        "1cdb83e6ee4dd9a1f85ef166fc907446cd384218b8dfa563d7f0983e98471dc2"
    )
    assert report.allocation_seed_count == 324
    assert report.allocation_seed_range == (28100, 28423)
    assert report.validation_seed_allocation == ()
    assert report.test_seed_allocation == ()
    assert report.dataset_generation_executed is False
    assert report.main_execution_authorization is False
    assert report.generated_episode_count == 0
    assert report.generated_sample_count == 0
    assert report.training_ready is False
    assert report.model_ready is False
    assert report.runtime_admission_ready is False
    capability = report.to_dict()["producer_capability"]
    assert capability["source_generation_request_path"] == (
        report.source_generation_request_path
    )
    assert capability["source_generation_request_sha256"] == (
        report.source_generation_request_sha256
    )
    assert capability["source_generation_request_ready"] is True
    assert capability["all_frozen_cells_viable"] is True
    assert capability["source_viability_episode_count"] == 324
    assert capability["dataset_generation_execution_authorized"] is False
    assert report.generation_request_permissions.source_generation_request is True
    assert not any(
        getattr(report.generation_request_permissions, name)
        for name in V8_GENERATION_REQUEST_PERMISSION_NAMES
        if name != "source_generation_request"
    )
    assert not any(report.permissions.to_dict()[name] for name in (
        "assignment",
        "degradation",
        "coalition",
        "takeover",
        "control",
    ))


def test_binding_sidecar_rejects_tamper_even_when_rehashed() -> None:
    payload = _read_json(_BINDING_PATH)
    payload["allocation"]["owner"] = "main"
    content = deepcopy(payload)
    content.pop("content_sha256")
    payload["content_sha256"] = canonical_v8_sha256(content)
    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_binding_payload(payload)
    assert error.value.code == "binding_allocation_drift"


def test_source_generation_request_artifact_is_machine_valid() -> None:
    payload = _read_json(_SOURCE_GENERATION_REQUEST_PATH)

    validated = validate_v8_source_generation_request_payload(payload)

    assert validated["request_scope"]["requested_split"] == "train"
    assert validated["request_scope"]["seed_count"] == 324
    assert validated["request_scope"]["topology_region_counts"] == [8, 9, 12, 16]
    assert validated["request_scope"]["validation_seed_allocation"] == []
    assert validated["request_scope"]["test_seed_allocation"] == []
    assert validated["request_scope"]["source_viability_audit"] == {
        "schema": "d4-region-resource-v8-source-viability-audit-v1",
        "required_episode_count": 324,
        "required_full_cell_combination_count": 324,
        "required_reduced_combination_count": 108,
        "required_online_truth_use_count": 0,
        "failure_policy": "fail_closed",
    }
    assert validated["permissions"]["source_generation_request"] is True
    assert validated["execution_claims"]["main_execution_authorization"] is False
    assert validated["references"]["main_recipe_implementation"][
        "file_sha256"
    ] == "34ced4f02c089b492b2ba58a94220fa319acd98ae65efa276c98fa7e4c8302d9"


def test_source_generation_request_physical_hash_drift_fails_closed(
    tmp_path: Path,
) -> None:
    paths = _copy_contract_fixture(tmp_path)
    artifact = paths["source_generation_request"]
    artifact.write_bytes(artifact.read_bytes() + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "source_generation_request_file_sha256_mismatch"


def test_writer_resume_implementation_hash_drift_fails_closed(
    tmp_path: Path,
) -> None:
    paths = _copy_contract_fixture(tmp_path)
    writer = paths["writer"]
    writer.write_bytes(writer.read_bytes() + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == (
        "writer_resume_implementation_file_sha256_mismatch"
    )


@pytest.mark.parametrize(
    ("fixture_key", "reference_name"),
    (
        ("v8_contract", "v8_contract_implementation"),
        ("runtime_evidence", "runtime_evidence_implementation"),
        ("source_viability", "source_viability_implementation"),
        ("region_resource_policy", "region_resource_policy_implementation"),
        ("main_runtime_adapter", "main_runtime_adapter_implementation"),
        ("main_treatment", "main_treatment_implementation"),
        ("main_recipe", "main_recipe_implementation"),
    ),
)
def test_bound_producer_hash_drift_fails_closed(
    tmp_path: Path,
    fixture_key: str,
    reference_name: str,
) -> None:
    paths = _copy_contract_fixture(tmp_path)
    producer = paths[fixture_key]
    producer.write_bytes(producer.read_bytes() + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == f"{reference_name}_file_sha256_mismatch"


def test_generation_request_reference_drift_fails_even_when_rehashed() -> None:
    payload = _read_json(_SOURCE_GENERATION_REQUEST_PATH)
    payload["references"]["global_seed_registry"]["file_sha256"] = "0" * 64
    content = deepcopy(payload)
    content.pop("content_sha256")
    payload["content_sha256"] = canonical_v8_sha256(content)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_source_generation_request_payload(payload)
    assert error.value.code == "source_generation_request_reference_drift"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed_count", 323),
        ("seed_range", [28101, 28423]),
        ("topology_region_counts", [8, 9, 12]),
        ("requested_split", "validation"),
        ("validation_seed_allocation", [29000]),
        ("test_seed_allocation", [29001]),
    ],
)
def test_generation_request_seed_region_or_split_drift_fails_closed(
    field: str,
    value: object,
) -> None:
    payload = _read_json(_SOURCE_GENERATION_REQUEST_PATH)
    payload["request_scope"][field] = value
    content = deepcopy(payload)
    content.pop("content_sha256")
    payload["content_sha256"] = canonical_v8_sha256(content)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_source_generation_request_payload(payload)
    assert error.value.code == "source_generation_request_scope_mismatch"


@pytest.mark.parametrize("permission", V8_GENERATION_REQUEST_PERMISSION_NAMES)
def test_generation_request_permission_escalation_or_removal_fails_closed(
    permission: str,
) -> None:
    payload = _read_json(_SOURCE_GENERATION_REQUEST_PATH)
    payload["permissions"][permission] = permission != "source_generation_request"
    content = deepcopy(payload)
    content.pop("content_sha256")
    payload["content_sha256"] = canonical_v8_sha256(content)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_source_generation_request_payload(payload)
    assert error.value.code == "source_generation_request_permissions_mismatch"


def test_generation_request_main_execution_permission_fails_closed() -> None:
    payload = _read_json(_SOURCE_GENERATION_REQUEST_PATH)
    payload["execution_claims"]["main_execution_authorization"] = True
    content = deepcopy(payload)
    content.pop("content_sha256")
    payload["content_sha256"] = canonical_v8_sha256(content)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_source_generation_request_payload(payload)
    assert error.value.code == (
        "source_generation_request_execution_claim_mismatch"
    )


def test_wrong_registry_id_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    global_path = paths["global_registry"]
    payload = _read_json(global_path)
    payload["registry_id"] = "obsolete-global-registry-v0"
    _write_self_hashed_json(global_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "global_registry_id_mismatch"


def test_global_registry_physical_file_hash_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    global_path = paths["global_registry"]
    global_path.write_bytes(global_path.read_bytes() + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "global_registry_file_sha256_mismatch"


def test_missing_d4_seed_fails_exact_inventory_check(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    global_path = paths["global_registry"]
    payload = _read_json(global_path)
    allocation = next(
        item
        for item in payload["allocations"]
        if item["allocation_id"] == "d4-a2-v8-train"
    )
    allocation["seeds"].pop()
    allocation["seed_count"] = len(allocation["seeds"])
    _write_self_hashed_json(global_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "global_allocation_seed_inventory_mismatch"


def test_global_allocation_overlap_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    global_path = paths["global_registry"]
    payload = _read_json(global_path)
    other = next(
        item
        for item in payload["allocations"]
        if item["allocation_id"] != "d4-a2-v8-train"
    )
    other["seeds"].append(28100)
    other["seeds"] = sorted(other["seeds"])
    other["seed_count"] = len(other["seeds"])
    _write_self_hashed_json(global_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "global_registry_allocation_seed_overlap"


def test_global_source_binding_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    global_path = paths["global_registry"]
    payload = _read_json(global_path)
    allocation = next(
        item
        for item in payload["allocations"]
        if item["allocation_id"] == "d4-a2-v8-train"
    )
    allocation["source_contract"]["request_id"] = "wrong-request"
    _write_self_hashed_json(global_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "global_allocation_source_binding_mismatch"


def test_d4_schedule_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    module_registry_path = paths["module_registry"]
    payload = _read_json(module_registry_path)
    payload["schedule"][0]["communication_condition"] = "bounded_delay_and_loss"
    payload["schedule_content_sha256"] = canonical_v8_sha256(payload["schedule"])
    _write_self_hashed_json(module_registry_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "d4_frozen_contract_invalid"
    assert "schedule_matrix_mismatch" in str(error.value)


@pytest.mark.parametrize("field", ["validation_seed_allocation", "test_seed_allocation"])
def test_validation_and_test_must_remain_unallocated(
    tmp_path: Path, field: str
) -> None:
    paths = _copy_contract_fixture(tmp_path)
    module_registry_path = paths["module_registry"]
    payload = _read_json(module_registry_path)
    payload[field] = [29000]
    _write_self_hashed_json(module_registry_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "d4_frozen_contract_invalid"
    assert "validation_test_must_remain_unallocated" in str(error.value)


def test_any_d4_authority_permission_true_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    request_path = paths["request"]
    payload = _read_json(request_path)
    payload["permissions"]["degradation"] = True
    _write_self_hashed_json(request_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "d4_frozen_contract_invalid"
    assert "permission_must_remain_false" in str(error.value)


def test_d4_request_physical_file_hash_drift_fails_closed(tmp_path: Path) -> None:
    paths = _copy_contract_fixture(tmp_path)
    request_path = paths["request"]
    original = request_path.read_bytes()
    assert sha256(original).hexdigest() != sha256(original + b"\n").hexdigest()
    request_path.write_bytes(original + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        _validate_copied_fixture(tmp_path, paths)
    assert error.value.code == "d4_request_file_sha256_mismatch"
