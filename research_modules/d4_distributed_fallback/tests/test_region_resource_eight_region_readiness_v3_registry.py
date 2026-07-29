from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from d4_distributed_fallback.region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA,
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION,
    RegionResourceEightRegionCandidateError,
    load_region_resource_eight_region_candidate_manifest,
    review_region_resource_eight_region_candidate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
)
V3_ROOT = REGISTRY_ROOT / (
    REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
)
V2_ROOT = REGISTRY_ROOT / (
    "region_resource_a2_8region_runtime_action_readiness_shadow_v2"
)
V3_SOURCE_COMMIT = "4ba2c8a649dab157d55a2dd7817d5a8ded494114"
V3_MANIFEST_CONTENT_SHA256 = (
    "7978aec0bdf577571b9b85df10cf91f11a70f5d1b937f9dd5083bbf7e836ada2"
)
V3_MODEL_SHA256 = (
    "ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d"
)
V3_SOURCE_IDENTITY_SHA256 = (
    "e260ff2f69660142985569a73634920700325dbd6282b7e76e78a8a6562214ef"
)
V3_COMPOSITE_DATASET_SHA256 = (
    "5d174dd3526a0262990c5472556b024ac0306b33262fd805a38da16c999bee03"
)
V3_COMPOSITE_SPLIT_SHA256 = (
    "69ae1b0e40c6478ac62d65d89b1634f867d10b8167c523763741827a6f96d817"
)
V3_RUNTIME_GATE_SHA256 = (
    "7797283405cad532f2911ea5965102f3b916c4ce6ccf60c17f955ea87e0e6872"
)
V3_TREE_SHA256 = (
    "07c770b05ffc70f190cd8b45d762d579857747e0efb12b472a2354ee5aeaa93a"
)
V2_TREE_SHA256 = (
    "324a51181017ed6baae97893f32da5bf3f9364c1da6b6c046a0a9af4109e5010"
)
V3_REGISTERED_FILE_SHA256 = {
    "bundle/manifest.json": (
        "9f3bfb1d7b786ed88683ba1d04c0a274decd5e35a64cfd392117d6f284a6238d"
    ),
    "bundle/state_dict.pt": V3_MODEL_SHA256,
    "bundle/training_dataset_manifest.json": (
        "b779fb5f15d14dad99fe671dd80e73e9f9b11ebd5ea0ed1884cc56a6a6fdd4e2"
    ),
    "eight_region_shadow_candidate_manifest.json": (
        "5e575ec4c0cd40ddb33ae9f06ce3b5ca015825c5ad3364733234349f143459c3"
    ),
    "source_implementation_summary.json": (
        "aeae57179d2ef089482d1da75f404e5d6a745b2290f90cf8d084c15f88a30459"
    ),
    "training_config.json": (
        "18e7c24f5d3d9131f9aae75bcb64f4ed2cba7e0c1528a9f8478c75a0beb38499"
    ),
    "training_summary.json": (
        "a0db3d7fda8f8296e8e71c3687e49c5cc1f74d6e7683cf6d8d8c3f3f779d82b3"
    ),
    "training_view_manifest.json": (
        "5abbcaff658861c268d061a92bc44361260064aa936b47bffc010c012ecdc32c"
    ),
}


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _file_inventory(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _truth_use_counts(value: Any) -> list[int]:
    observed: list[int] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                "truth" in key.lower()
                and key.lower().endswith("use_count")
            ):
                assert type(item) is int
                observed.append(item)
            observed.extend(_truth_use_counts(item))
    elif isinstance(value, list):
        for item in value:
            observed.extend(_truth_use_counts(item))
    return observed


def test_readiness_v3_registry_has_exact_immutable_file_inventory() -> None:
    observed = _file_inventory(V3_ROOT)

    assert observed == V3_REGISTERED_FILE_SHA256
    assert _json_sha256(observed) == V3_TREE_SHA256


def test_readiness_v3_registry_load_review_and_contract_are_self_contained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated = tmp_path / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    shutil.copytree(V3_ROOT, isolated)

    def source_access_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("registry review attempted source dataset access")

    monkeypatch.setattr(
        "d4_distributed_fallback.region_resource_eight_region_candidate."
        "_load_verified_source",
        source_access_forbidden,
    )
    monkeypatch.setattr(
        "d4_distributed_fallback.region_resource_eight_region_candidate."
        "load_verified_eight_region_readiness_source",
        source_access_forbidden,
    )

    manifest = load_region_resource_eight_region_candidate_manifest(
        isolated
    )
    review = review_region_resource_eight_region_candidate(isolated)
    source = _read_json(
        isolated / "source_implementation_summary.json"
    )
    config = _read_json(isolated / "training_config.json")
    bundle = _read_json(isolated / "bundle/manifest.json")
    view = _read_json(isolated / "training_view_manifest.json")
    training = _read_json(isolated / "training_summary.json")
    gate = bundle["runtime_confidence_gate"]

    assert manifest.schema == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_SCHEMA
    )
    assert manifest.candidate_id == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    )
    assert manifest.model_version == (
        REGION_RESOURCE_EIGHT_REGION_READINESS_V3_MODEL_VERSION
    )
    assert manifest.content_sha256 == V3_MANIFEST_CONTENT_SHA256
    assert manifest.model_state_sha256 == V3_MODEL_SHA256
    assert manifest.source_identity_sha256 == V3_SOURCE_IDENTITY_SHA256
    assert (
        manifest.composite_dataset_sha256
        == V3_COMPOSITE_DATASET_SHA256
    )
    assert manifest.composite_split_sha256 == V3_COMPOSITE_SPLIT_SHA256
    assert source["git_commit"] == V3_SOURCE_COMMIT
    assert source["repository_tracked_dirty"] is False

    assert config["runtime_projection_minimum_reserve_ratio"] == 0.1
    assert config["runtime_projection_minimum_reserve_resources"] == 1
    assert config["runtime_projection_advisory_ttl_s"] == 1.5
    assert config["runtime_rule_high_threat_weight"] == 2.0
    assert config["runtime_rule_uncertainty_weight"] == 0.5
    assert config["runtime_rule_transfer_pressure_margin"] == 0.05
    assert config["runtime_fixed_ood_margin"] == 0.05
    assert config["fixed_minimum_confidence"] == 0.60
    assert config["confidence_inconsistent_target_ceiling"] == 0.59
    assert config["confidence_continuous_tolerance"] == 0.10

    assert gate["content_sha256"] == V3_RUNTIME_GATE_SHA256
    assert gate["projection_config"] == {
        "minimum_reserve_ratio": 0.1,
        "minimum_reserve_resources": 1,
        "advisory_ttl_s": 1.5,
    }
    assert gate["rule_policy_config"] == {
        "projection": gate["projection_config"],
        "high_threat_weight": 2.0,
        "uncertainty_weight": 0.5,
        "transfer_pressure_margin": 0.05,
    }
    assert gate["fixed_ood_margin"] == 0.05
    assert gate["fixed_minimum_confidence"] == 0.60
    assert gate["inconsistent_confidence_cap"] == 0.59
    assert gate["continuous_tolerance"] == 0.10

    truth_counts = (
        _truth_use_counts(view)
        + _truth_use_counts(training)
        + _truth_use_counts(bundle)
    )
    assert truth_counts
    assert not any(truth_counts)
    assert manifest.confidence_calibration_accepted is True
    assert manifest.runtime_preflight_completed is False
    assert manifest.formal_holdout_evaluated is False
    assert review["formal_evaluation_authorized"] is False
    assert review["read_only_shadow_verified"] is True
    assert review["source_datasets_required_for_runtime_load"] is False
    assert not any(
        value
        for name, value in review["permissions"].items()
        if name != "schema"
    )


def test_readiness_v3_registry_tamper_is_rejected(
    tmp_path: Path,
) -> None:
    copied = tmp_path / REGION_RESOURCE_EIGHT_REGION_READINESS_V3_CANDIDATE_ID
    shutil.copytree(V3_ROOT, copied)
    gate_manifest = copied / "bundle/manifest.json"
    gate_manifest.write_bytes(gate_manifest.read_bytes() + b"\n")

    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="candidate_artifact_sha256_mismatch:bundle/manifest.json",
    ):
        review_region_resource_eight_region_candidate(copied)


def test_readiness_v2_registry_tree_remains_immutable() -> None:
    observed = _file_inventory(V2_ROOT)

    assert _json_sha256(observed) == V2_TREE_SHA256
    review = review_region_resource_eight_region_candidate(V2_ROOT)
    assert review["candidate_id"] == (
        "region_resource_a2_8region_runtime_action_readiness_shadow_v2"
    )
