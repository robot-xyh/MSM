from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from research_modules.scalable_3d_simulation.global_seed_registry import (
    GLOBAL_SEED_REGISTRY_POLICY_VERSION,
    GLOBAL_SEED_REGISTRY_SCHEMA_VERSION,
    GlobalSeedRegistryError,
    build_global_seed_registry,
    load_global_seed_registry,
    registry_content_sha256,
    validate_registry_source_contracts,
    validate_seed_request,
)


def _payload() -> dict:
    payload = {
        "schema_version": GLOBAL_SEED_REGISTRY_SCHEMA_VERSION,
        "policy_version": GLOBAL_SEED_REGISTRY_POLICY_VERSION,
        "registry_id": "scalable3d-development-seed-registry-test-v1",
        "protected_seed_sets": [
            {
                "set_id": "formal-evaluation-v1",
                "purpose": "formal_evaluation_payload",
                "seeds": list(range(1000, 1020)),
                "dataset_generation_allowed": False,
                "payload_read_allowed": False,
            }
        ],
        "allocations": [
            {
                "allocation_id": "d3-a1-v3",
                "owner": "D3",
                "candidate_version": "a1-v3",
                "lifecycle": "reserved",
                "usage_class": "train_validation_test",
                "split_policy": "whole_seed_60_20_20_v1",
                "permitted_operations": ["dataset_generation", "training"],
                "seed_count": 3,
                "seeds": [23000, 23001, 23002],
                "source_contract": {
                    "path": "research_modules/d3_assignment_planner/configs/contract.json"
                },
            },
            {
                "allocation_id": "d4-a2-v8-train",
                "owner": "D4",
                "candidate_version": "a2-v8",
                "lifecycle": "reserved",
                "usage_class": "train_only",
                "split_policy": "train_only_independent_source_v1",
                "permitted_operations": ["dataset_generation", "training"],
                "seed_count": 2,
                "seeds": [28100, 28101],
                "source_contract": {},
            },
        ],
        "unallocated_requests": [
            {
                "request_id": "d5-a3-next-source",
                "owner": "D5",
                "candidate_version": "a3-v3",
                "requested_seed_count": 100,
                "reason": "protocol must be frozen before allocation",
            }
        ],
    }
    payload["content_sha256"] = registry_content_sha256(payload)
    return payload


def test_registry_loads_typed_allocations_and_authorizes_exact_request(
    tmp_path: Path,
) -> None:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    registry = load_global_seed_registry(path)

    assert registry.source_path == path.resolve()
    assert registry.protected_seeds == frozenset(range(1000, 1020))
    assert registry.allocation("d3-a1-v3").owner == "D3"
    provenance = validate_seed_request(
        registry,
        allocation_id="d3-a1-v3",
        seeds=(23002, 23000, 23001),
        operation="dataset_generation",
    )
    assert provenance["exact_allocation_match"] is True
    assert provenance["protected_seed_overlap_count"] == 0
    assert provenance["registry_content_sha256"] == registry.content_sha256


def test_registry_rejects_tamper_overlap_and_unprotected_formal_seed() -> None:
    tampered = _payload()
    tampered["allocations"][0]["owner"] = "D4"
    with pytest.raises(GlobalSeedRegistryError) as error:
        build_global_seed_registry(tampered)
    assert error.value.code == "content_hash_mismatch"

    overlap = _payload()
    overlap["allocations"][1]["seeds"] = [23002, 28101]
    overlap["content_sha256"] = registry_content_sha256(overlap)
    with pytest.raises(GlobalSeedRegistryError) as error:
        build_global_seed_registry(overlap)
    assert error.value.code == "allocation_seed_overlap"

    unprotected = _payload()
    unprotected["protected_seed_sets"][0]["seeds"] = list(range(1000, 1019))
    unprotected["content_sha256"] = registry_content_sha256(unprotected)
    with pytest.raises(GlobalSeedRegistryError) as error:
        build_global_seed_registry(unprotected)
    assert error.value.code == "formal_evaluation_seed_unprotected"


def test_registry_rejects_protected_seed_and_implicit_request_reservation() -> None:
    protected = _payload()
    protected["allocations"][0]["seeds"] = [1000, 23001, 23002]
    protected["content_sha256"] = registry_content_sha256(protected)
    with pytest.raises(GlobalSeedRegistryError) as error:
        build_global_seed_registry(protected)
    assert error.value.code == "allocation_uses_protected_seed"

    implicit = _payload()
    implicit["unallocated_requests"][0]["seeds"] = [29000]
    implicit["content_sha256"] = registry_content_sha256(implicit)
    with pytest.raises(GlobalSeedRegistryError) as error:
        build_global_seed_registry(implicit)
    assert error.value.code == "unallocated_request_contains_seeds"


def test_seed_request_fails_closed_for_partial_wrong_operation_or_retired() -> None:
    registry = build_global_seed_registry(_payload())
    with pytest.raises(GlobalSeedRegistryError) as error:
        validate_seed_request(
            registry,
            allocation_id="d3-a1-v3",
            seeds=(23000, 23001),
            operation="dataset_generation",
        )
    assert error.value.code == "request_not_exact_allocation"

    with pytest.raises(GlobalSeedRegistryError) as error:
        validate_seed_request(
            registry,
            allocation_id="d3-a1-v3",
            seeds=(23000, 23001, 23002),
            operation="validation",
        )
    assert error.value.code == "operation_not_permitted"

    retired = copy.deepcopy(_payload())
    retired["allocations"][0]["lifecycle"] = "retired"
    retired["content_sha256"] = registry_content_sha256(retired)
    retired_registry = build_global_seed_registry(retired)
    with pytest.raises(GlobalSeedRegistryError) as error:
        validate_seed_request(
            retired_registry,
            allocation_id="d3-a1-v3",
            seeds=(23000, 23001, 23002),
            operation="dataset_generation",
        )
    assert error.value.code == "allocation_retired"


def test_source_contract_verification_rejects_hash_drift_and_unsafe_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "contract.json"
    source.write_text('{"version":1}\n', encoding="ascii")
    payload = _payload()
    payload["allocations"] = [payload["allocations"][0]]
    payload["allocations"][0]["source_contract"] = {
        "bindings": [
            {
                "role": "contract",
                "path": "contract.json",
                "sha256": sha256(source.read_bytes()).hexdigest(),
            }
        ]
    }
    payload["content_sha256"] = registry_content_sha256(payload)
    registry = build_global_seed_registry(payload)
    audit = validate_registry_source_contracts(
        registry,
        repository_root=tmp_path,
    )
    assert audit["all_source_contracts_verified"] is True

    source.write_text('{"version":2}\n', encoding="ascii")
    with pytest.raises(GlobalSeedRegistryError) as error:
        validate_registry_source_contracts(registry, repository_root=tmp_path)
    assert error.value.code == "source_binding_hash_mismatch"

    payload["allocations"][0]["source_contract"]["bindings"][0]["path"] = (
        "../contract.json"
    )
    payload["content_sha256"] = registry_content_sha256(payload)
    unsafe = build_global_seed_registry(payload)
    with pytest.raises(GlobalSeedRegistryError) as error:
        validate_registry_source_contracts(unsafe, repository_root=tmp_path)
    assert error.value.code == "source_binding_path_unsafe"


def test_project_registry_is_reproducible_disjoint_and_source_bound() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "research_modules/scalable_3d_simulation/configs/"
        "scalable_learning_global_seed_registry_v1.json"
    )
    registry = load_global_seed_registry(path)
    audit = validate_registry_source_contracts(registry, repository_root=root)

    assert audit["allocation_count"] == 5
    assert not registry.unallocated_requests
    assert registry.allocation("d3-a1-v3-all-splits").seeds == tuple(
        range(23000, 23300)
    )
    assert registry.allocation("d4-a2-v8-train").seeds == tuple(
        range(28100, 28424)
    )
    assert registry.allocation("d5-a3-v3-train").seeds == tuple(
        range(24000, 24048)
    )
    assert registry.allocation("d5-a3-v3-validation").seeds == tuple(
        range(24048, 24072)
    )
    future = registry.allocation("d5-a3-v3-future-held-out")
    assert future.seeds == tuple(range(24072, 24104))
    assert future.permitted_operations == ("dataset_generation", "test")
    assert "training" not in future.permitted_operations
