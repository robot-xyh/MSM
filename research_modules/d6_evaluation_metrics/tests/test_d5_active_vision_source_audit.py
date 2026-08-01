from __future__ import annotations

from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import (
    D5_ACTIVE_VISION_SOURCE_AUDIT_SCHEMA_VERSION,
    audit_d5_active_vision_source_dataset,
)


_DOMAIN_TIER = {
    "legacy_unspecified": "legacy_unclassified",
    "synthetic_fixture": "software_fixture_only",
    "scalable_3d_point_mass_runtime": "simulation_research",
    "airsim_runtime": "airsim_declaration_only",
    "real_camera_runtime": "real_camera_declaration_only",
}
_SOURCE_CONTRACT = {
    "schema_version": "d5.active-vision-source-provenance.v1",
    "new_artifacts_require_explicit_provenance": True,
    "legacy_missing_policy": (
        "fixture_flag_true_maps_to_synthetic_fixture_else_legacy_unspecified"
    ),
    "legacy_evidence_upgrade_allowed": False,
    "synthetic_fixture_true_domain": "synthetic_fixture",
    "source_declaration_is_external_runtime_attestation": False,
}
_STORAGE_CONTRACT = {
    "online_truth_free": True,
    "offline_labels_physically_separate": True,
    "online_storage_layout": "deduplicated-reference-stream-jsonl-gzip-v1",
    "shared_objects_referenced_by_sha256_key": True,
    "offline_join_uses_stream_audit": True,
    "detached": True,
    "immutable": True,
    "missing_numeric_labels_use_null": True,
}
_SEEDS = (200, 201, 202, 203, 204)


def _canonical_bytes(value: object) -> bytes:
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


def _sha_json(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value))


def _source_provenance(domain: str, *, tier_override: str | None) -> dict[str, object]:
    return {
        "schema_version": "d5.active-vision-source-provenance.v1",
        "source_domain": domain,
        "evidence_tier": tier_override or _DOMAIN_TIER[domain],
    }


def _split_by_seed() -> dict[int, str]:
    ordered = sorted(
        _SEEDS,
        key=lambda seed: (
            sha256(f"17\0{seed}".encode("utf-8")).hexdigest(),
            seed,
        ),
    )
    return {
        seed: "test" if index == 0 else "validation" if index == 1 else "train"
        for index, seed in enumerate(ordered)
    }


def _write_online_stream(
    path: Path,
    *,
    uid: str,
    seed: int,
    source_identity: dict[str, object],
    source_provenance: dict[str, object] | None,
    synthetic_fixture: bool,
    online_identity_key: str | None,
) -> None:
    header = {
        "record_type": "header",
        "schema_version": "d5.active-vision-episode-record.v2",
        "sample_schema_version": "d5.active-vision-sample.v2",
        "storage_layout": "deduplicated-reference-stream-jsonl-gzip-v1",
        "episode_uid": uid,
        "scenario_version": "d6-source-audit-fixture-v1",
        "seed": seed,
        "episode_id": f"episode-{seed}",
        "source_identity": source_identity,
        "synthetic_fixture": synthetic_fixture,
    }
    if source_provenance is not None:
        header["source_provenance"] = source_provenance
    feedback = {
        "record_type": "camera_feedback",
        "object_key": f"camera-feedback-sha256-{'c' * 64}",
        "value": {"camera_id": "camera-local", "accepted": True},
    }
    snapshot = {
        "record_type": "snapshot",
        "object_key": f"snapshot-sha256-{'d' * 64}",
        "value": {
            "global_track_id": f"GT-{seed}",
            "measurement_timestamp": 1.0,
            "arrival_timestamp": 1.1,
        },
    }
    sample = {
        "record_type": "sample",
        "schema_version": "d5.active-vision-sample.v2",
        "sequence_index": 0,
        "sample_key": f"sample-{seed}",
        "observation_key": f"observation-{seed}",
    }
    if online_identity_key is not None:
        sample[online_identity_key] = "Intruder_001"
    footer = {
        "record_type": "footer",
        "schema_version": "d5.active-vision-episode-record.v2",
        "sample_count": 1,
        "unique_snapshot_count": 1,
        "unique_camera_feedback_count": 1,
        "sample_index_sha256": "e" * 64,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in (header, feedback, snapshot, sample, footer):
                stream.write(_canonical_bytes(row))


def _build_dataset(
    root: Path,
    *,
    domain: str = "scalable_3d_point_mass_runtime",
    mixed_domain: bool = False,
    dirty: bool = False,
    tier_override: str | None = None,
    online_identity_key: str | None = None,
    omit_source_provenance: bool = False,
    fixture_override: bool | None = None,
    tamper_source_summary: bool = False,
    tamper_split_sha: bool = False,
) -> Path:
    root.mkdir(parents=True)
    config = {
        "schema_version": "d5.active-vision-dataset-config.v1",
        "fixture": "d6-independent-source-audit",
    }
    config_path = root / "dataset_config.json"
    _write_json(config_path, config)
    config_sha = _sha_file(config_path)
    split_by_seed = _split_by_seed()
    descriptors: list[dict[str, object]] = []

    for index, seed in enumerate(_SEEDS):
        episode_domain = "airsim_runtime" if mixed_domain and index == 0 else domain
        synthetic_fixture = (
            episode_domain == "synthetic_fixture"
            if fixture_override is None
            else fixture_override
        )
        identity = {
            "schema_version": "d5.active-vision-source-identity.v1",
            "git_commit": "a" * 40,
            "git_dirty": dirty,
            "config_sha256": "b" * 64,
        }
        provenance = None
        if not omit_source_provenance:
            provenance = _source_provenance(
                episode_domain,
                tier_override=tier_override,
            )
        uid = sha256(f"fixture:{seed}".encode("ascii")).hexdigest()[:24]
        online_relative = f"online/{uid}.online.jsonl.gz"
        offline_relative = f"offline/{uid}.offline.json"
        _write_online_stream(
            root / online_relative,
            uid=uid,
            seed=seed,
            source_identity=identity,
            source_provenance=provenance,
            synthetic_fixture=synthetic_fixture,
            online_identity_key=online_identity_key,
        )
        _write_json(
            root / offline_relative,
            {
                "schema_version": "d5.active-vision-offline-labels.v1",
                "episode_uid": uid,
                "labels": [],
            },
        )
        descriptor: dict[str, object] = {
            "schema_version": "d5.active-vision-episode-descriptor.v2",
            "episode_uid": uid,
            "scenario_version": "d6-source-audit-fixture-v1",
            "seed": seed,
            "episode_id": f"episode-{seed}",
            "source_identity": identity,
            "synthetic_fixture": synthetic_fixture,
            "dataset_config_sha256": config_sha,
            "online_file": online_relative,
            "online_sha256": _sha_file(root / online_relative),
            "online_storage_layout": "deduplicated-reference-stream-jsonl-gzip-v1",
            "unique_snapshot_count": 1,
            "unique_camera_feedback_count": 1,
            "offline_file": offline_relative,
            "offline_sha256": _sha_file(root / offline_relative),
            "sample_count": 1,
            "availability": {},
            "split": split_by_seed[seed],
        }
        if provenance is not None:
            descriptor["source_provenance"] = provenance
        descriptors.append(descriptor)

    descriptors.sort(key=lambda item: str(item["episode_uid"]))
    for descriptor in descriptors:
        _write_json(
            root / "episodes" / f"{descriptor['episode_uid']}.episode.json",
            descriptor,
        )

    domains = Counter(
        str(item.get("source_provenance", {}).get("source_domain", "legacy_unspecified"))
        for item in descriptors
    )
    tiers = Counter(
        str(item.get("source_provenance", {}).get("evidence_tier", "legacy_unclassified"))
        for item in descriptors
    )
    domain_counts = {name: int(domains.get(name, 0)) for name in _DOMAIN_TIER}
    tier_counts = {
        name: int(tiers.get(name, 0)) for name in sorted(set(_DOMAIN_TIER.values()))
    }
    source_summary = {
        "episode_count": len(descriptors),
        "episode_count_by_source_domain": domain_counts,
        "episode_count_by_evidence_tier": tier_counts,
        "explicit_source_domain_episode_count": (
            0 if omit_source_provenance else len(descriptors)
        ),
        "legacy_inferred_episode_count": (
            len(descriptors) if omit_source_provenance else 0
        ),
        "external_runtime_attestation_validated": False,
    }
    if tamper_source_summary:
        source_summary["episode_count_by_source_domain"][domain] += 1

    split_payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "scenario_version": str(item["scenario_version"]),
            "seed": int(item["seed"]),
            "episode_id": str(item["episode_id"]),
            "split": str(item["split"]),
        }
        for item in descriptors
    ]
    training_payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "online_sha256": str(item["online_sha256"]),
            "offline_sha256": str(item["offline_sha256"]),
            "source_identity": item["source_identity"],
        }
        for item in descriptors
        if item["split"] == "train"
    ]
    manifest = {
        "schema_version": "d5.active-vision-episode-dataset.v3",
        "episode_descriptor_schema_version": "d5.active-vision-episode-descriptor.v2",
        "episode_record_schema_version": "d5.active-vision-episode-record.v2",
        "sample_schema_version": "d5.active-vision-sample.v2",
        "snapshot_schema_version": "d5.active-vision-snapshot.v1",
        "action_schema_version": "d5.active-vision-action.v1",
        "camera_feedback_schema_version": "d5.active-vision-camera-feedback.v1",
        "runtime_ack_schema_version": "d5.active-vision-runtime-ack.v1",
        "offline_labels_schema_version": "d5.active-vision-offline-labels.v1",
        "offline_label_schema_version": "d5.active-vision-offline-label.v1",
        "dataset_config_file": "dataset_config.json",
        "dataset_config_sha256": config_sha,
        "storage_contract": _STORAGE_CONTRACT,
        "reward_contract": {},
        "split_policy": {
            "unit": "whole_episode_grouped_by_scenario_version_and_seed",
            "sample_or_transition_level_random_split": False,
            "shared_seed_values_atomic_across_scenarios": True,
            "split_seed": 17,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
            "minimum_unseen_seed_count": 1,
            "unseen_test_seed_count": 1,
        },
        "split_sha256": "f" * 64 if tamper_split_sha else _sha_json(split_payload),
        "training_set_sha256": _sha_json(training_payload),
        "source_identity_summary": {
            "git_commits": ["a" * 40],
            "source_config_sha256_values": ["b" * 64],
            "dirty_episode_count": len(descriptors) if dirty else 0,
            "clean_episode_count": 0 if dirty else len(descriptors),
            "episode_count": len(descriptors),
        },
        "source_provenance_contract": _SOURCE_CONTRACT,
        "source_domain_summary": source_summary,
        "availability": {},
        "episodes": descriptors,
    }
    _write_json(root / "manifest.json", manifest)
    artifacts = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS"
    )
    (root / "SHA256SUMS").write_text(
        "".join(
            f"{_sha_file(path)}  {path.relative_to(root).as_posix()}\n"
            for path in artifacts
        ),
        encoding="ascii",
    )
    for path in (*artifacts, root / "SHA256SUMS"):
        path.chmod(0o444)
    return root


def test_clean_point_mass_dataset_confirms_only_simulation_research_integrity(
    tmp_path: Path,
) -> None:
    root = _build_dataset(tmp_path / "point-mass")

    result = audit_d5_active_vision_source_dataset(root)

    assert result["schema_version"] == D5_ACTIVE_VISION_SOURCE_AUDIT_SCHEMA_VERSION
    assert result["status"] == "simulation_research_integrity_confirmed"
    assert result["simulation_research_integrity_confirmed"] is True
    assert result["declaration_only"] is False
    assert result["evidence"]["episode_count"] == 5
    assert result["evidence"]["split"]["seed_sets_mutually_exclusive"] is True
    assert all(result["checks"].values())
    assert all(value is False for value in result["authority"].values())
    assert result["d6_control_participation"] is False


@pytest.mark.parametrize(
    ("domain", "tier"),
    (
        ("airsim_runtime", "airsim_declaration_only"),
        ("real_camera_runtime", "real_camera_declaration_only"),
    ),
)
def test_external_source_domains_remain_declaration_only(
    tmp_path: Path,
    domain: str,
    tier: str,
) -> None:
    root = _build_dataset(tmp_path / domain, domain=domain)

    result = audit_d5_active_vision_source_dataset(root)

    assert result["status"] == "declaration_only"
    assert result["declared_source_domain"] == domain
    assert result["evidence_tier"] == tier
    assert result["simulation_research_integrity_confirmed"] is False
    assert result["authority"]["airsim_external_proof"] is False
    assert result["authority"]["real_camera_external_proof"] is False
    assert all(value is False for value in result["authority"].values())


def test_unrebound_artifact_tampering_fails_closed(tmp_path: Path) -> None:
    root = _build_dataset(tmp_path / "tampered")
    online = next((root / "online").glob("*.online.jsonl.gz"))
    online.chmod(0o644)
    online.write_bytes(online.read_bytes() + b"tamper")
    online.chmod(0o444)

    result = audit_d5_active_vision_source_dataset(root)

    assert result["status"] == "fail_closed"
    assert result["blocker_codes"] == ["artifact_sha256_mismatch"]
    assert all(value is False for value in result["authority"].values())


def test_truth_identity_with_fully_rebound_hashes_fails_closed(tmp_path: Path) -> None:
    root = _build_dataset(
        tmp_path / "truth-rebound",
        online_identity_key="actor_id",
    )

    result = audit_d5_active_vision_source_dataset(root)

    assert result["status"] == "fail_closed"
    assert result["blocker_codes"] == [
        "online_truth_actor_object_identity_forbidden"
    ]
    assert all(value is False for value in result["authority"].values())


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    (
        ({"tier_override": "real_camera_declaration_only"}, "source_evidence_tier_mismatch"),
        ({"mixed_domain": True}, "source_domain_mixed"),
        ({"dirty": True}, "source_identity_dirty"),
        ({"tamper_source_summary": True}, "source_domain_summary_mismatch"),
        ({"tamper_split_sha": True}, "split_sha256_mismatch"),
        ({"omit_source_provenance": True}, "descriptor_fields_mismatch"),
        ({"fixture_override": True}, "source_fixture_flag_mismatch"),
    ),
)
def test_rebound_contract_tampering_and_legacy_source_fail_closed(
    tmp_path: Path,
    kwargs: dict[str, object],
    expected_code: str,
) -> None:
    root = _build_dataset(tmp_path / expected_code, **kwargs)

    result = audit_d5_active_vision_source_dataset(root)

    assert result["status"] == "fail_closed"
    assert result["blocker_codes"] == [expected_code]
    assert result["simulation_research_integrity_confirmed"] is False
    assert all(value is False for value in result["authority"].values())
