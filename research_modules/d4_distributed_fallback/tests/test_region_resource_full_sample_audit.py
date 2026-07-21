from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from d4_distributed_fallback.region_resource_curriculum import (
    RegionActionCoverageCurriculumConfig,
    build_region_action_coverage_frames,
)
from d4_distributed_fallback.region_resource_dataset import (
    RegionLearningEpisodeSource,
)
from d4_distributed_fallback.region_resource_full_sample_audit import (
    REGION_RESOURCE_FULL_SAMPLE_AUDIT_SCHEMA,
    _SUPPLEMENTAL_REQUIREMENTS,
    _audit_dataset_inventory,
    _canonical_contract_violations,
    _forbidden_key_paths,
    _nonfinite_number_paths,
    _raw_recommendation_contract_violations,
    _version_monotonicity_violations,
)


def _frames():
    config = RegionActionCoverageCurriculumConfig(
        region_count=4,
        resource_count=17,
    )
    source = RegionLearningEpisodeSource(
        scenario_id=config.scenario_id,
        scenario_version=config.scenario_version,
        scenario_scale=config.scenario_scale,
        seed=7,
        episode_id="full-sample-audit-test-seed-7",
        git_commit="a" * 40,
        git_dirty=False,
        config_sha256=sha256(b"full-sample-audit-test").hexdigest(),
    )
    return build_region_action_coverage_frames(source, config)


def test_valid_projected_rule_teacher_frame_passes_raw_safety_contract() -> None:
    frame = _frames()[2]
    payload = frame.to_dict()

    assert _raw_recommendation_contract_violations(
        payload["snapshot"],
        payload["target"]["recommendation"],
        timestamp_s=frame.timestamp_s,
        path="valid",
    ) == []
    assert _nonfinite_number_paths(payload, path="valid") == []
    assert _forbidden_key_paths(payload, path="valid") == []


def test_nonfinite_numeric_feature_is_detected() -> None:
    payload = _frames()[0].to_dict()
    payload["snapshot"]["regions"][0]["d1_uncertainty"] = float("nan")

    assert _nonfinite_number_paths(payload, path="sample") == [
        "sample.snapshot.regions[0].d1_uncertainty"
    ]


def test_canonical_split_count_error_is_fail_closed() -> None:
    canonical = {
        "canonical_split": {
            "seed_counts": {"train": 60, "validation": 20, "test": 20},
            "episode_counts": {"train": 60, "validation": 20, "test": 20},
            "frame_counts": {"train": 180, "validation": 60, "test": 60},
            "numeric_seed_atomic": True,
            "reserved_seed_count": 20,
            "reserved_seed_present": False,
        }
    }
    assert _canonical_contract_violations(
        canonical, requirements=_SUPPLEMENTAL_REQUIREMENTS
    ) == []

    canonical["canonical_split"]["seed_counts"]["train"] = 59
    violations = _canonical_contract_violations(
        canonical, requirements=_SUPPLEMENTAL_REQUIREMENTS
    )
    assert any("canonical_seed_counts_mismatch" in item for item in violations)


def test_resource_quota_nonconservation_is_rejected() -> None:
    frame = _frames()[2]
    payload = frame.to_dict()
    recommendation = deepcopy(payload["target"]["recommendation"])
    recommendation["actions"][0]["resource_quota_delta"] += 1

    violations = _raw_recommendation_contract_violations(
        payload["snapshot"],
        recommendation,
        timestamp_s=frame.timestamp_s,
        path="quota",
    )
    assert any("resource_quota_not_conserved" in item for item in violations)


def test_illegal_cross_region_transfer_is_rejected() -> None:
    frame = _frames()[2]
    payload = frame.to_dict()
    recommendation = deepcopy(payload["target"]["recommendation"])
    recommendation["transfers"][0]["edge_id"] = "missing-edge"

    violations = _raw_recommendation_contract_violations(
        payload["snapshot"],
        recommendation,
        timestamp_s=frame.timestamp_s,
        path="transfer",
    )
    assert any("unknown_transfer_edge" in item for item in violations)


def test_stale_epoch_plan_version_and_expired_lease_are_rejected() -> None:
    frame = _frames()[0]
    payload = frame.to_dict()
    snapshot = deepcopy(payload["snapshot"])
    recommendation = deepcopy(payload["target"]["recommendation"])
    action = recommendation["actions"][0]
    action["expected_epoch"] -= 1
    action["expected_plan_version"] -= 1
    action["expected_lease_expires_at_s"] -= 1.0
    snapshot["regions"][1]["lease_expires_at_s"] = frame.timestamp_s

    violations = _raw_recommendation_contract_violations(
        snapshot,
        recommendation,
        timestamp_s=frame.timestamp_s,
        path="stale",
    )
    assert any("expected_epoch_stale_or_mismatch" in item for item in violations)
    assert any(
        "expected_plan_version_stale_or_mismatch" in item for item in violations
    )
    assert any(
        "expected_lease_expires_at_s_stale_or_mismatch" in item
        for item in violations
    )
    assert any("owner_lease_expired" in item for item in violations)


def test_owner_epoch_version_and_lease_regression_are_detected() -> None:
    first = _frames()[0].to_dict()["snapshot"]
    second = deepcopy(_frames()[1].to_dict()["snapshot"])
    previous: dict[str, dict] = {}
    assert _version_monotonicity_violations(
        first, previous_regions=previous, path="first"
    ) == []
    second_region = second["regions"][0]
    second_region["plan_version"] = first["regions"][0]["plan_version"] - 1
    second_region["epoch"] = first["regions"][0]["epoch"] - 1
    second_region["lease_expires_at_s"] = (
        first["regions"][0]["lease_expires_at_s"] - 1.0
    )

    violations = _version_monotonicity_violations(
        second, previous_regions=previous, path="second"
    )
    assert any("plan_version_regressed" in item for item in violations)
    assert any("epoch_regressed" in item for item in violations)
    assert any("lease_expiry_regressed" in item for item in violations)


def test_truth_identifier_key_is_rejected_without_rejecting_target_container() -> None:
    payload = _frames()[0].to_dict()
    assert _forbidden_key_paths(payload, path="sample") == []

    payload["target"]["truth_id"] = "must-not-enter-online-data"
    paths = _forbidden_key_paths(payload, path="sample")
    assert paths == ["sample.target.truth_id"]


def test_episode_file_tampering_changes_hash_and_fails_inventory(tmp_path: Path) -> None:
    episode_dir = tmp_path / "episodes"
    episode_dir.mkdir()
    episode = episode_dir / "episode-a.jsonl"
    episode.write_text("original\n", encoding="utf-8")
    expected_sha = sha256(episode.read_bytes()).hexdigest()
    manifest = {
        "episodes": [
            {
                "relative_path": "episodes/episode-a.jsonl",
                "episode_sha256": expected_sha,
            }
        ]
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    violations: list[str] = []
    inventory = _audit_dataset_inventory(
        tmp_path, manifest, violations, "fixture"
    )
    assert inventory["episode_sha256_verified_count"] == 1
    assert not violations

    episode.write_text("tampered\n", encoding="utf-8")
    violations = []
    inventory = _audit_dataset_inventory(
        tmp_path, manifest, violations, "fixture"
    )
    assert inventory["episode_sha256_mismatch_count"] == 1
    assert any("episode_sha256_mismatch" in item for item in violations)


def test_tracked_full_sample_evidence_preserves_fail_closed_authority() -> None:
    path = Path(
        "research_modules/d4_distributed_fallback/reports/"
        "D4_REGION_RESOURCE_FULL_SAMPLE_ADMISSION_20260721.json"
    )
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["schema"] == REGION_RESOURCE_FULL_SAMPLE_AUDIT_SCHEMA
    assert report["status"] == {
        "formal_full_sample": "complete",
        "supplemental_full_sample": "complete",
        "combined_full_sample": "complete",
    }
    assert report["admission"]["ppo_allowed"] is False
    assert report["admission"]["assist_allowed"] is False
    assert report["admission"]["online_authority_allowed"] is False
    assert report["admission"]["rule_fallback_required"] is True
    assert (
        report["supplemental_curriculum"]["synthetic_evidence_boundary"][
            "real_runtime_coalition_member_ack_evidence"
        ]
        is False
    )
