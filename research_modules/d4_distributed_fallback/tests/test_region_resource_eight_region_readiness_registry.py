from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from d4_distributed_fallback.region_resource_eight_region_candidate import (
    RegionResourceEightRegionCandidateError,
    load_region_resource_eight_region_candidate_manifest,
    review_region_resource_eight_region_candidate,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CANDIDATE_ID = (
    "region_resource_a2_8region_runtime_action_readiness_shadow_v2"
)
CANDIDATE_ROOT = (
    REPOSITORY_ROOT
    / "research_modules/d4_distributed_fallback/model_registry"
    / CANDIDATE_ID
)
SOURCE_COMMIT = "891b542337ef065eee8c794d38dfa6ba382fea9e"
MANIFEST_FILE_SHA256 = (
    "c3194c900058e85aad57bd52853fea99846a35c1f8d4fd8a81a53832d4daf72b"
)
MANIFEST_CONTENT_SHA256 = (
    "481480346f6c7355d3124f7ff3fdc4e9f8208a0209d4319514be25a91793852f"
)
MODEL_SHA256 = (
    "ace5df6dae62f8a9a80a4cd141d50a93427e609e4caa605b9962494ebfe7f52d"
)
SOURCE_IDENTITY_SHA256 = (
    "331b4f296a1c9fa46b61c9dcb7b59c499280817389b3b1b843181e38d4392ce0"
)
COMPOSITE_DATASET_SHA256 = (
    "996dbd667deec08451a52c9878b2ad02cf699c69ec0920fe26807fec0f62493e"
)
COMPOSITE_SPLIT_SHA256 = (
    "69ae1b0e40c6478ac62d65d89b1634f867d10b8167c523763741827a6f96d817"
)
RUNTIME_GATE_CONFIG_SHA256 = (
    "acdcb781e9c884ced85544f0f4b7c329d8be23b39fd977dc380bd294b9f44cde"
)
SOURCE_DATASET_SHA256 = {
    "runtime": (
        "b06d741bd22a0cd84ef1e47a48a0b8cd81ceb7e4ea294eeeb38b892e69d36158"
    ),
    "action_curriculum": (
        "7e17aba7911602c1b9e9f5b917aea97f1eeec478f03963b119fbcfc8de299e72"
    ),
    "readiness_supplement": (
        "34244f1fe4f15cf82ff144e6c6cb5cabedccf5ba7f7880adcd2b820b681c9c56"
    ),
}
REGISTERED_FILE_SHA256 = {
    "bundle/manifest.json": (
        "efca7be5dd74888cbccaaf2e4f45a0bd54b6bdcace5a4309daad33c525e1637c"
    ),
    "bundle/state_dict.pt": MODEL_SHA256,
    "bundle/training_dataset_manifest.json": (
        "2c924a1148730d19a12ee8ef5e03aa3cdb6ddf3aba467ad7cda386375a419871"
    ),
    "eight_region_shadow_candidate_manifest.json": MANIFEST_FILE_SHA256,
    "source_implementation_summary.json": (
        "c710b9b7983460242fb3bebbf3a96f3720646220a182345fc498551386b12b9e"
    ),
    "training_config.json": (
        "626261c1d261bc26e971d643ced64ee04395abebde1b76907ce4d0fa967205ad"
    ),
    "training_summary.json": (
        "c1cde24aba004c5969be012ac73fcd347da5c98abc060f8ab18cce030c429e17"
    ),
    "training_view_manifest.json": (
        "bb8a95a3b6e33a3f1b45c2dc68e1f12ac5fbf1a350b6899fd3b95c24bd37d45b"
    ),
}


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def test_readiness_v2_registry_has_exact_immutable_file_inventory() -> None:
    observed = {
        str(path.relative_to(CANDIDATE_ROOT)): _file_sha256(path)
        for path in CANDIDATE_ROOT.rglob("*")
        if path.is_file()
    }
    assert observed == REGISTERED_FILE_SHA256


def test_readiness_v2_registry_load_and_review_are_self_contained(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isolated = tmp_path / CANDIDATE_ID
    shutil.copytree(CANDIDATE_ROOT, isolated)

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

    manifest = load_region_resource_eight_region_candidate_manifest(isolated)
    review = review_region_resource_eight_region_candidate(isolated)
    source = json.loads(
        (isolated / "source_implementation_summary.json").read_text(
            encoding="utf-8"
        )
    )
    view = json.loads(
        (isolated / "training_view_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    training = json.loads(
        (isolated / "training_summary.json").read_text(encoding="utf-8")
    )

    assert manifest.candidate_id == CANDIDATE_ID
    assert manifest.content_sha256 == MANIFEST_CONTENT_SHA256
    assert manifest.model_state_sha256 == MODEL_SHA256
    assert manifest.source_identity_sha256 == SOURCE_IDENTITY_SHA256
    assert manifest.composite_dataset_sha256 == COMPOSITE_DATASET_SHA256
    assert manifest.composite_split_sha256 == COMPOSITE_SPLIT_SHA256
    assert manifest.applicable_region_count == 8
    assert source["git_commit"] == SOURCE_COMMIT
    assert source["repository_tracked_dirty"] is False
    assert source["training_core_matches_commit"] is True
    assert source["view_builder_content_addressed"] is True
    assert {
        name: payload["dataset_sha256"]
        for name, payload in view["sources"].items()
    } == SOURCE_DATASET_SHA256

    split = view["global_split"]
    split_sets = {
        name: set(split[f"{name}_seeds"])
        for name in ("train", "validation", "test")
    }
    assert split["split_sha256"] == COMPOSITE_SPLIT_SHA256
    assert not split_sets["train"] & split_sets["validation"]
    assert not split_sets["train"] & split_sets["test"]
    assert not split_sets["validation"] & split_sets["test"]
    assert set.union(*split_sets.values()) == set(range(100))
    assert not set.union(*split_sets.values()) & set(range(1000, 1020))
    assert manifest.split_usage.test_payload_read_count == 0
    assert manifest.split_usage.calibration_seed_use_count == 0
    assert manifest.split_usage.reserved_seed_use_count == 0

    gate = view["confidence_supervision"]["runtime_gate"]
    assert gate["content_sha256"] == RUNTIME_GATE_CONFIG_SHA256
    assert gate["fixed_ood_margin"] == 0.05
    assert gate["fixed_minimum_confidence"] == 0.60
    assert gate["inconsistent_confidence_cap"] == 0.59
    assert gate["continuous_tolerance"] == 0.10

    validation = training["confidence_supervision"]["validation"]
    assert validation["sample_count"] == 344
    assert validation["raw"]["threshold_pass_count"] == 344
    assert (
        validation["raw"]["action_inconsistent_threshold_pass_count"] == 51
    )
    assert validation["effective"]["threshold_pass_count"] == 293
    assert (
        validation["effective"]["action_inconsistent_threshold_pass_count"]
        == 0
    )
    assert (
        validation["effective"][
            "action_consistency_rate_among_threshold_pass"
        ]
        == 1.0
    )
    assert validation["effective"]["brier_score"] == pytest.approx(
        0.056837453793788656
    )
    assert validation["runtime_reference_target_mismatch_count"] == 0
    assert manifest.confidence_calibration_accepted is True

    assert review["read_only_shadow_verified"] is True
    assert review["source_datasets_required_for_runtime_load"] is False
    assert review["runtime_preflight_completed"] is False
    assert review["formal_evaluation_authorized"] is False
    assert not any(
        value
        for name, value in review["permissions"].items()
        if name != "schema"
    )


def test_readiness_v2_registry_tamper_is_rejected(tmp_path: Path) -> None:
    copied = tmp_path / CANDIDATE_ID
    shutil.copytree(CANDIDATE_ROOT, copied)
    gate_manifest = copied / "bundle/manifest.json"
    gate_manifest.write_bytes(gate_manifest.read_bytes() + b"\n")

    with pytest.raises(
        RegionResourceEightRegionCandidateError,
        match="candidate_artifact_sha256_mismatch:bundle/manifest.json",
    ):
        review_region_resource_eight_region_candidate(copied)
