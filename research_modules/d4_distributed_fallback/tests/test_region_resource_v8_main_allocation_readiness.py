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
    default_v8_main_allocation_binding_path,
    validate_v8_main_allocation_binding_payload,
    validate_v8_main_allocation_pre_generation_readiness,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_BINDING_PATH = default_v8_main_allocation_binding_path()


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


def _copy_contract_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    binding = _read_json(_BINDING_PATH)
    paths = (
        binding["global_registry"]["path"],
        binding["d4_frozen_contract"]["request_path"],
        binding["d4_frozen_contract"]["module_seed_registry_path"],
    )
    copied: list[Path] = []
    for logical in paths:
        source = _REPOSITORY_ROOT / logical
        target = tmp_path / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target)
    return copied[0], copied[1], copied[2]


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
    assert report.allocation_seed_count == 324
    assert report.allocation_seed_range == (28100, 28423)
    assert report.validation_seed_allocation == ()
    assert report.test_seed_allocation == ()
    assert report.dataset_generation_executed is False
    assert report.generated_episode_count == 0
    assert report.generated_sample_count == 0
    assert report.training_ready is False
    assert report.model_ready is False
    assert report.runtime_admission_ready is False
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


def test_wrong_registry_id_fails_closed(tmp_path: Path) -> None:
    global_path, _, _ = _copy_contract_fixture(tmp_path)
    payload = _read_json(global_path)
    payload["registry_id"] = "obsolete-global-registry-v0"
    _write_self_hashed_json(global_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "global_registry_id_mismatch"


def test_global_registry_physical_file_hash_drift_fails_closed(tmp_path: Path) -> None:
    global_path, _, _ = _copy_contract_fixture(tmp_path)
    global_path.write_bytes(global_path.read_bytes() + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "global_registry_file_sha256_mismatch"


def test_missing_d4_seed_fails_exact_inventory_check(tmp_path: Path) -> None:
    global_path, _, _ = _copy_contract_fixture(tmp_path)
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
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "global_allocation_seed_inventory_mismatch"


def test_global_allocation_overlap_fails_closed(tmp_path: Path) -> None:
    global_path, _, _ = _copy_contract_fixture(tmp_path)
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
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "global_registry_allocation_seed_overlap"


def test_global_source_binding_drift_fails_closed(tmp_path: Path) -> None:
    global_path, _, _ = _copy_contract_fixture(tmp_path)
    payload = _read_json(global_path)
    allocation = next(
        item
        for item in payload["allocations"]
        if item["allocation_id"] == "d4-a2-v8-train"
    )
    allocation["source_contract"]["request_id"] = "wrong-request"
    _write_self_hashed_json(global_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "global_allocation_source_binding_mismatch"


def test_d4_schedule_drift_fails_closed(tmp_path: Path) -> None:
    _, _, module_registry_path = _copy_contract_fixture(tmp_path)
    payload = _read_json(module_registry_path)
    payload["schedule"][0]["communication_condition"] = "bounded_delay_and_loss"
    payload["schedule_content_sha256"] = canonical_v8_sha256(payload["schedule"])
    _write_self_hashed_json(module_registry_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "d4_frozen_contract_invalid"
    assert "schedule_matrix_mismatch" in str(error.value)


@pytest.mark.parametrize("field", ["validation_seed_allocation", "test_seed_allocation"])
def test_validation_and_test_must_remain_unallocated(
    tmp_path: Path, field: str
) -> None:
    _, _, module_registry_path = _copy_contract_fixture(tmp_path)
    payload = _read_json(module_registry_path)
    payload[field] = [29000]
    _write_self_hashed_json(module_registry_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "d4_frozen_contract_invalid"
    assert "validation_test_must_remain_unallocated" in str(error.value)


def test_any_d4_authority_permission_true_fails_closed(tmp_path: Path) -> None:
    _, request_path, _ = _copy_contract_fixture(tmp_path)
    payload = _read_json(request_path)
    payload["permissions"]["degradation"] = True
    _write_self_hashed_json(request_path, payload)

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "d4_frozen_contract_invalid"
    assert "permission_must_remain_false" in str(error.value)


def test_d4_request_physical_file_hash_drift_fails_closed(tmp_path: Path) -> None:
    _, request_path, _ = _copy_contract_fixture(tmp_path)
    original = request_path.read_bytes()
    assert sha256(original).hexdigest() != sha256(original + b"\n").hexdigest()
    request_path.write_bytes(original + b"\n")

    with pytest.raises(RegionResourceV8MainAllocationError) as error:
        validate_v8_main_allocation_pre_generation_readiness(
            binding_path=_BINDING_PATH,
            repository_root=tmp_path,
        )
    assert error.value.code == "d4_request_file_sha256_mismatch"
