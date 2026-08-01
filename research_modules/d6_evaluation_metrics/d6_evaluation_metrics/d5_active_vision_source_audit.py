"""Independent, read-only D6 audit of D5 active-vision source provenance.

This module deliberately does not import D5.  It parses the finalized dataset
artifacts directly and treats every D5 field as an untrusted claim.  The audit
can confirm bounded point-mass simulation integrity; it cannot attest AirSim
or real-camera provenance and never grants runtime or control authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import gzip
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping, Sequence


D5_ACTIVE_VISION_SOURCE_AUDIT_SCHEMA_VERSION = (
    "d6.d5-active-vision-source-audit.v1"
)

_DATASET_SCHEMA = "d5.active-vision-episode-dataset.v3"
_DESCRIPTOR_SCHEMA = "d5.active-vision-episode-descriptor.v2"
_RECORD_SCHEMA = "d5.active-vision-episode-record.v2"
_SAMPLE_SCHEMA = "d5.active-vision-sample.v2"
_OFFLINE_LABELS_SCHEMA = "d5.active-vision-offline-labels.v1"
_OFFLINE_LABEL_SCHEMA = "d5.active-vision-offline-label.v1"
_SOURCE_IDENTITY_SCHEMA = "d5.active-vision-source-identity.v1"
_SOURCE_PROVENANCE_SCHEMA = "d5.active-vision-source-provenance.v1"
_ONLINE_STORAGE_LAYOUT = "deduplicated-reference-stream-jsonl-gzip-v1"

_SOURCE_TIER_BY_DOMAIN = {
    "legacy_unspecified": "legacy_unclassified",
    "synthetic_fixture": "software_fixture_only",
    "scalable_3d_point_mass_runtime": "simulation_research",
    "airsim_runtime": "airsim_declaration_only",
    "real_camera_runtime": "real_camera_declaration_only",
}
_SOURCE_DOMAINS = tuple(_SOURCE_TIER_BY_DOMAIN)
_EVIDENCE_TIERS = tuple(sorted(set(_SOURCE_TIER_BY_DOMAIN.values())))
_SOURCE_PROVENANCE_CONTRACT = {
    "schema_version": _SOURCE_PROVENANCE_SCHEMA,
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
    "online_storage_layout": _ONLINE_STORAGE_LAYOUT,
    "shared_objects_referenced_by_sha256_key": True,
    "offline_join_uses_stream_audit": True,
    "detached": True,
    "immutable": True,
    "missing_numeric_labels_use_null": True,
}
_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "episode_descriptor_schema_version",
        "episode_record_schema_version",
        "sample_schema_version",
        "snapshot_schema_version",
        "action_schema_version",
        "camera_feedback_schema_version",
        "runtime_ack_schema_version",
        "offline_labels_schema_version",
        "offline_label_schema_version",
        "dataset_config_file",
        "dataset_config_sha256",
        "storage_contract",
        "reward_contract",
        "split_policy",
        "split_sha256",
        "training_set_sha256",
        "source_identity_summary",
        "source_provenance_contract",
        "source_domain_summary",
        "availability",
        "episodes",
    }
)
_DESCRIPTOR_FIELDS = frozenset(
    {
        "schema_version",
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "source_identity",
        "synthetic_fixture",
        "source_provenance",
        "dataset_config_sha256",
        "online_file",
        "online_sha256",
        "online_storage_layout",
        "unique_snapshot_count",
        "unique_camera_feedback_count",
        "offline_file",
        "offline_sha256",
        "sample_count",
        "availability",
        "split",
    }
)
_HEADER_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "sample_schema_version",
        "storage_layout",
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "source_identity",
        "synthetic_fixture",
        "source_provenance",
    }
)
_FOOTER_FIELDS = frozenset(
    {
        "record_type",
        "schema_version",
        "sample_count",
        "unique_snapshot_count",
        "unique_camera_feedback_count",
        "sample_index_sha256",
    }
)
_OFFLINE_FIELDS = frozenset(
    {
        "schema_version",
        "episode_uid",
        "scenario_version",
        "seed",
        "episode_id",
        "reward_bounds",
        "labels",
    }
)
_OFFLINE_LABEL_FIELDS = frozenset(
    {
        "schema_version",
        "sample_key",
        "observation_key",
        "reward",
        "counterfactual",
        "outcome",
        "causal_label",
    }
)
_SPLIT_POLICY_FIELDS = frozenset(
    {
        "unit",
        "sample_or_transition_level_random_split",
        "shared_seed_values_atomic_across_scenarios",
        "split_seed",
        "validation_fraction",
        "test_fraction",
        "minimum_unseen_seed_count",
        "unseen_test_seed_count",
    }
)
_SOURCE_IDENTITY_FIELDS = frozenset(
    {"schema_version", "git_commit", "git_dirty", "config_sha256"}
)
_SOURCE_PROVENANCE_FIELDS = frozenset(
    {"schema_version", "source_domain", "evidence_tier"}
)
_KNOWN_STREAM_RECORD_TYPES = frozenset(
    {"header", "camera_feedback", "snapshot", "sample", "footer"}
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "truth",
        "truth_id",
        "truth_entity_id",
        "ground_truth",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "entity_id",
        "entity_name",
        "target_truth_id",
        "airsim_id",
    }
)
_FORBIDDEN_ONLINE_SUFFIXES = (
    "_actor_id",
    "_actor_name",
    "_object_id",
    "_object_name",
    "_truth_id",
    "_entity_id",
    "_entity_name",
)
_TRUTH_LIKE_ONLINE_VALUE = re.compile(
    r"truth|actor|object|(?:^|[^a-z0-9])"
    r"(?:tgt|target(?:drone|uav)?|intruder)[_.\- ]*\d+",
    re.IGNORECASE,
)
_AUTHORITY_FALSE = {
    "airsim_external_proof": False,
    "real_camera_external_proof": False,
    "model_admission": False,
    "assist": False,
    "assignment": False,
    "degradation": False,
    "runtime": False,
    "production": False,
    "control": False,
    "global_track_id_write": False,
}
_CHECK_NAMES = (
    "checksum_inventory_complete",
    "artifact_hashes_complete",
    "immutable_artifacts_complete",
    "audit_input_unchanged_complete",
    "manifest_descriptor_binding_complete",
    "descriptor_header_binding_complete",
    "online_object_hash_binding_complete",
    "online_footer_index_binding_complete",
    "offline_label_binding_complete",
    "source_domain_mapping_complete",
    "fixture_consistency_complete",
    "source_domain_summary_complete",
    "source_identity_clean_complete",
    "seed_split_disjoint_complete",
    "split_hash_binding_complete",
    "truth_free_online_payload_complete",
)


class D5ActiveVisionSourceAuditError(ValueError):
    """Stable fail-closed validation error for an untrusted dataset."""

    def __init__(self, code: str, detail: str = "") -> None:
        message = str(code) if not detail else f"{code}: {detail}"
        super().__init__(message)
        self.code = str(code)
        self.detail = str(detail)


@dataclass(frozen=True, slots=True)
class _FileEvidence:
    path: Path
    sha256: str
    device: int
    inode: int
    size: int
    modified_ns: int
    mode: int


@dataclass(frozen=True, slots=True)
class _OnlineStreamEvidence:
    sample_count: int
    snapshot_count: int
    camera_feedback_count: int
    record_count: int
    sample_keys: tuple[str, ...]
    observation_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _EpisodeEvidence:
    episode_uid: str
    seed: int
    split: str
    source_domain: str
    evidence_tier: str
    source_identity: Mapping[str, Any]
    synthetic_fixture: bool
    sample_count: int
    snapshot_count: int
    camera_feedback_count: int
    online_record_count: int
    offline_label_count: int


def audit_d5_active_vision_source_dataset(
    dataset_root: str | Path,
) -> dict[str, Any]:
    """Independently audit one finalized D5 active-vision dataset root.

    Validation failures are returned as a stable ``fail_closed`` result so the
    fixed no-authority contract remains present even for malformed input.
    """

    result = _base_result(dataset_root)
    try:
        evidence = _audit_dataset_strict(Path(dataset_root))
    except (D5ActiveVisionSourceAuditError, OSError) as exc:
        if isinstance(exc, D5ActiveVisionSourceAuditError):
            code = exc.code
            detail = exc.detail
        else:  # pragma: no cover - platform-level I/O failures are rare.
            code = "dataset_io_error"
            detail = str(exc)
        result["blocker_codes"] = [code]
        result["failure_detail"] = detail
        return result

    source_domain = str(evidence["source_domain"])
    evidence_tier = str(evidence["evidence_tier"])
    if source_domain == "scalable_3d_point_mass_runtime":
        status = "simulation_research_integrity_confirmed"
        simulation_confirmed = True
        declaration_only = False
    elif source_domain in {"airsim_runtime", "real_camera_runtime"}:
        status = "declaration_only"
        simulation_confirmed = False
        declaration_only = True
    elif source_domain == "synthetic_fixture":
        status = "software_fixture_only"
        simulation_confirmed = False
        declaration_only = False
    else:  # pragma: no cover - legacy and mixed sources fail before this point.
        status = "fail_closed"
        simulation_confirmed = False
        declaration_only = False

    result.update(
        {
            "status": status,
            "simulation_research_integrity_confirmed": simulation_confirmed,
            "declaration_only": declaration_only,
            "declared_source_domain": source_domain,
            "evidence_tier": evidence_tier,
            "blocker_codes": [],
            "failure_detail": None,
            "checks": {name: True for name in _CHECK_NAMES},
            "evidence": evidence,
        }
    )
    return result


def _base_result(dataset_root: str | Path) -> dict[str, Any]:
    return {
        "schema_version": D5_ACTIVE_VISION_SOURCE_AUDIT_SCHEMA_VERSION,
        "dataset_root": str(Path(dataset_root).absolute()),
        "status": "fail_closed",
        "simulation_research_integrity_confirmed": False,
        "declaration_only": False,
        "declared_source_domain": None,
        "evidence_tier": None,
        "blocker_codes": [],
        "failure_detail": None,
        "checks": {name: False for name in _CHECK_NAMES},
        "evidence": None,
        "authority": dict(_AUTHORITY_FALSE),
        "d6_control_participation": False,
    }


def _audit_dataset_strict(root: Path) -> dict[str, Any]:
    resolved = _resolve_root(root)
    hashes, file_evidence = _verify_checksum_inventory(resolved)
    manifest_path = _required_artifact(resolved, "manifest.json", hashes)
    manifest = _load_json_object(manifest_path, "manifest")
    _require_fields(manifest, _MANIFEST_FIELDS, "manifest_fields_mismatch")
    _require_equal(manifest["schema_version"], _DATASET_SCHEMA, "dataset_schema_mismatch")
    _require_equal(
        manifest["episode_descriptor_schema_version"],
        _DESCRIPTOR_SCHEMA,
        "descriptor_schema_mismatch",
    )
    _require_equal(
        manifest["episode_record_schema_version"],
        _RECORD_SCHEMA,
        "online_record_schema_mismatch",
    )
    _require_equal(
        manifest["sample_schema_version"],
        _SAMPLE_SCHEMA,
        "sample_schema_mismatch",
    )
    _require_equal(
        manifest["storage_contract"],
        _STORAGE_CONTRACT,
        "storage_contract_mismatch",
    )
    _require_equal(
        manifest["source_provenance_contract"],
        _SOURCE_PROVENANCE_CONTRACT,
        "source_provenance_contract_mismatch",
    )

    config_relative = _safe_relative(manifest["dataset_config_file"])
    config_path = _required_artifact(resolved, config_relative, hashes)
    config_sha = _require_sha256(manifest["dataset_config_sha256"], "dataset_config_sha256")
    _require_equal(
        hashes[config_relative],
        config_sha,
        "dataset_config_sha256_mismatch",
    )
    _load_json_object(config_path, "dataset_config")

    raw_episodes = manifest["episodes"]
    if not isinstance(raw_episodes, list) or not raw_episodes:
        _fail("episodes_missing")
    if any(not isinstance(item, Mapping) for item in raw_episodes):
        _fail("descriptor_invalid")
    if raw_episodes != sorted(raw_episodes, key=lambda item: str(item.get("episode_uid", ""))):
        _fail("episode_descriptor_order_invalid")

    expected_artifacts = {"manifest.json", config_relative}
    episodes: list[_EpisodeEvidence] = []
    seen_uids: set[str] = set()
    seen_online: set[str] = set()
    seen_offline: set[str] = set()
    for raw_descriptor in raw_episodes:
        descriptor = _mapping(raw_descriptor, "descriptor_invalid")
        episode, referenced = _audit_episode(
            resolved,
            descriptor,
            hashes=hashes,
            file_evidence=file_evidence,
            dataset_config_relative=config_relative,
            dataset_config_sha256=config_sha,
        )
        if episode.episode_uid in seen_uids:
            _fail("episode_duplicate", episode.episode_uid)
        seen_uids.add(episode.episode_uid)
        if referenced[1] in seen_online:
            _fail("online_artifact_reused", referenced[1])
        if referenced[2] in seen_offline:
            _fail("offline_artifact_reused", referenced[2])
        seen_online.add(referenced[1])
        seen_offline.add(referenced[2])
        expected_artifacts.update(referenced)
        episodes.append(episode)

    if set(hashes) != expected_artifacts:
        _fail(
            "manifest_artifact_inventory_mismatch",
            _set_difference_detail(expected_artifacts, set(hashes)),
        )

    domains = {episode.source_domain for episode in episodes}
    if len(domains) != 1:
        _fail("source_domain_mixed", ",".join(sorted(domains)))
    source_domain = next(iter(domains))
    if source_domain == "legacy_unspecified":
        _fail("legacy_source_provenance_forbidden")

    _validate_source_summary(manifest["source_domain_summary"], episodes)
    _validate_source_identity_summary(manifest["source_identity_summary"], episodes)
    split_summary = _validate_splits(manifest, raw_episodes, episodes)

    for item in file_evidence.values():
        _verify_unchanged(item)
    seed_values = sorted({item.seed for item in episodes})
    return {
        "dataset_manifest_sha256": hashes["manifest.json"],
        "checksums_sha256": file_evidence[resolved / "SHA256SUMS"].sha256,
        "artifact_count": len(hashes),
        "audited_file_count": len(file_evidence),
        "descriptor_count": len(episodes),
        "online_stream_count": len(episodes),
        "offline_file_count": len(episodes),
        "episode_count": len(episodes),
        "sample_count": sum(item.sample_count for item in episodes),
        "online_record_count": sum(item.online_record_count for item in episodes),
        "offline_label_count": sum(item.offline_label_count for item in episodes),
        "online_snapshot_object_count": sum(item.snapshot_count for item in episodes),
        "online_camera_feedback_object_count": sum(
            item.camera_feedback_count for item in episodes
        ),
        "online_header_binding_count": len(episodes),
        "online_footer_index_binding_count": len(episodes),
        "offline_episode_binding_count": len(episodes),
        "seed_values": seed_values,
        "source_domain": source_domain,
        "evidence_tier": _SOURCE_TIER_BY_DOMAIN[source_domain],
        "source_domain_episode_counts": dict(
            sorted(Counter(item.source_domain for item in episodes).items())
        ),
        "source_identity": {
            "git_commits": sorted(
                {str(item.source_identity["git_commit"]) for item in episodes}
            ),
            "source_config_sha256_values": sorted(
                {str(item.source_identity["config_sha256"]) for item in episodes}
            ),
            "clean_episode_count": len(episodes),
            "dirty_episode_count": 0,
        },
        "split": split_summary,
        "online_truth_identifier_count": 0,
        "online_actor_identifier_count": 0,
        "online_object_identifier_count": 0,
        "external_runtime_attestation_validated": False,
    }


def _audit_episode(
    root: Path,
    descriptor: Mapping[str, Any],
    *,
    hashes: Mapping[str, str],
    file_evidence: Mapping[Path, _FileEvidence],
    dataset_config_relative: str,
    dataset_config_sha256: str,
) -> tuple[_EpisodeEvidence, tuple[str, str, str]]:
    _require_fields(descriptor, _DESCRIPTOR_FIELDS, "descriptor_fields_mismatch")
    _require_equal(descriptor["schema_version"], _DESCRIPTOR_SCHEMA, "descriptor_schema_mismatch")
    uid = _nonempty_string(descriptor["episode_uid"], "episode_uid_invalid")
    scenario = _nonempty_string(descriptor["scenario_version"], "scenario_version_invalid")
    episode_id = _nonempty_string(descriptor["episode_id"], "episode_id_invalid")
    seed = _strict_int(descriptor["seed"], "seed_invalid")
    split = str(descriptor["split"])
    if split not in {"train", "validation", "test"}:
        _fail("descriptor_not_finalized", uid)
    synthetic_fixture = _strict_bool(
        descriptor["synthetic_fixture"], "synthetic_fixture_flag_invalid"
    )
    source_domain, evidence_tier = _validate_source_provenance(
        descriptor["source_provenance"],
        synthetic_fixture=synthetic_fixture,
    )
    source_identity = _validate_source_identity(descriptor["source_identity"])
    if source_identity["git_dirty"] is True:
        _fail("source_identity_dirty", uid)

    descriptor_config_sha = _require_sha256(
        descriptor["dataset_config_sha256"], "dataset_config_sha256_invalid"
    )
    online_sha = _require_sha256(descriptor["online_sha256"], "online_sha256_invalid")
    offline_sha = _require_sha256(descriptor["offline_sha256"], "offline_sha256_invalid")
    _require_equal(
        descriptor["online_storage_layout"],
        _ONLINE_STORAGE_LAYOUT,
        "online_storage_layout_mismatch",
    )
    sample_count = _strict_positive_int(descriptor["sample_count"], "sample_count_invalid")
    snapshot_count = _strict_positive_int(
        descriptor["unique_snapshot_count"], "snapshot_count_invalid"
    )
    feedback_count = _strict_positive_int(
        descriptor["unique_camera_feedback_count"],
        "camera_feedback_count_invalid",
    )
    if snapshot_count > sample_count or feedback_count > sample_count:
        _fail("online_count_bounds_invalid", uid)

    descriptor_relative = f"episodes/{uid}.episode.json"
    online_relative = _safe_relative(descriptor["online_file"])
    offline_relative = _safe_relative(descriptor["offline_file"])
    if not online_relative.startswith("online/") or not online_relative.endswith(
        ".online.jsonl.gz"
    ):
        _fail("online_artifact_path_invalid", online_relative)
    if not offline_relative.startswith("offline/") or not offline_relative.endswith(
        ".offline.json"
    ):
        _fail("offline_artifact_path_invalid", offline_relative)

    descriptor_path = _required_artifact(root, descriptor_relative, hashes)
    online_path = _required_artifact(root, online_relative, hashes)
    offline_path = _required_artifact(root, offline_relative, hashes)
    stored_descriptor = _load_json_object(descriptor_path, "episode_descriptor")
    _require_equal(stored_descriptor, descriptor, "manifest_descriptor_binding_mismatch")
    _require_equal(hashes[online_relative], online_sha, "online_sha256_binding_mismatch")
    _require_equal(hashes[offline_relative], offline_sha, "offline_sha256_binding_mismatch")
    _require_equal(
        descriptor_config_sha,
        dataset_config_sha256,
        "episode_dataset_config_binding_mismatch",
    )
    if dataset_config_relative not in hashes:  # Defensive after root inventory audit.
        _fail("episode_dataset_config_artifact_missing", dataset_config_relative)

    stream_evidence = _audit_online_stream(
        online_path,
        descriptor=descriptor,
        source_domain=source_domain,
        evidence_tier=evidence_tier,
    )
    _require_equal(
        stream_evidence.sample_count,
        sample_count,
        "stream_sample_count_mismatch",
    )
    _require_equal(
        stream_evidence.snapshot_count,
        snapshot_count,
        "stream_snapshot_count_mismatch",
    )
    _require_equal(
        stream_evidence.camera_feedback_count,
        feedback_count,
        "stream_camera_feedback_count_mismatch",
    )
    offline_label_count = _audit_offline_file(
        offline_path,
        descriptor=descriptor,
        stream_evidence=stream_evidence,
    )
    for path in (descriptor_path, online_path, offline_path):
        _verify_unchanged(file_evidence[path])
    return (
        _EpisodeEvidence(
            episode_uid=uid,
            seed=seed,
            split=split,
            source_domain=source_domain,
            evidence_tier=evidence_tier,
            source_identity=source_identity,
            synthetic_fixture=synthetic_fixture,
            sample_count=sample_count,
            snapshot_count=snapshot_count,
            camera_feedback_count=feedback_count,
            online_record_count=stream_evidence.record_count,
            offline_label_count=offline_label_count,
        ),
        (descriptor_relative, online_relative, offline_relative),
    )


def _audit_online_stream(
    path: Path,
    *,
    descriptor: Mapping[str, Any],
    source_domain: str,
    evidence_tier: str,
) -> _OnlineStreamEvidence:
    header: Mapping[str, Any] | None = None
    footer: Mapping[str, Any] | None = None
    sample_count = 0
    snapshot_keys: set[str] = set()
    feedback_keys: set[str] = set()
    sample_keys: list[str] = []
    observation_keys: list[str] = []
    seen_sample_keys: set[str] = set()
    seen_observation_keys: set[str] = set()
    sample_index: list[dict[str, Any]] = []
    record_count = 0
    try:
        with gzip.open(path, mode="rt", encoding="utf-8", newline="") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.endswith("\n"):
                    _fail("online_stream_truncated", f"{path.name}:{line_number}")
                record_count += 1
                row = _load_json_line(line, path=path, line_number=line_number)
                violations = _find_forbidden_online_identity(row)
                if violations:
                    _fail(
                        "online_truth_actor_object_identity_forbidden",
                        f"{path.name}:{line_number}:{','.join(violations[:8])}",
                    )
                record_type = row.get("record_type")
                if record_type not in _KNOWN_STREAM_RECORD_TYPES:
                    _fail("online_stream_record_type_invalid", str(record_type))
                if footer is not None:
                    _fail("online_stream_trailing_record", path.name)
                if line_number == 1:
                    if record_type != "header":
                        _fail("online_stream_header_missing", path.name)
                    _require_fields(row, _HEADER_FIELDS, "online_stream_header_fields_mismatch")
                    _require_equal(row["schema_version"], _RECORD_SCHEMA, "online_record_schema_mismatch")
                    _require_equal(row["sample_schema_version"], _SAMPLE_SCHEMA, "sample_schema_mismatch")
                    _require_equal(row["storage_layout"], _ONLINE_STORAGE_LAYOUT, "online_storage_layout_mismatch")
                    _strict_int(row["seed"], "online_header_seed_invalid")
                    _nonempty_string(
                        row["episode_uid"], "online_header_episode_uid_invalid"
                    )
                    _nonempty_string(
                        row["scenario_version"],
                        "online_header_scenario_version_invalid",
                    )
                    _nonempty_string(
                        row["episode_id"], "online_header_episode_id_invalid"
                    )
                    header = row
                    continue
                if record_type == "header":
                    _fail("online_stream_header_duplicate", path.name)
                if record_type == "footer":
                    _require_fields(row, _FOOTER_FIELDS, "online_stream_footer_fields_mismatch")
                    _require_equal(row["schema_version"], _RECORD_SCHEMA, "online_record_schema_mismatch")
                    _require_sha256(row["sample_index_sha256"], "sample_index_sha256_invalid")
                    _strict_positive_int(
                        row["sample_count"], "footer_sample_count_invalid"
                    )
                    _strict_positive_int(
                        row["unique_snapshot_count"],
                        "footer_snapshot_count_invalid",
                    )
                    _strict_positive_int(
                        row["unique_camera_feedback_count"],
                        "footer_camera_feedback_count_invalid",
                    )
                    footer = row
                elif record_type == "sample":
                    _require_equal(
                        row.get("schema_version"),
                        _SAMPLE_SCHEMA,
                        "sample_schema_mismatch",
                    )
                    sequence_index = _strict_int(
                        row.get("sequence_index"),
                        "sample_sequence_index_invalid",
                    )
                    _require_equal(
                        sequence_index,
                        sample_count,
                        "sample_sequence_index_mismatch",
                    )
                    sample_key = _nonempty_string(
                        row.get("sample_key"), "sample_key_invalid"
                    )
                    observation_key = _nonempty_string(
                        row.get("observation_key"), "observation_key_invalid"
                    )
                    snapshot_key = _nonempty_string(
                        row.get("snapshot_key"), "sample_snapshot_key_invalid"
                    )
                    feedback_key = _nonempty_string(
                        row.get("camera_feedback_key"),
                        "sample_camera_feedback_key_invalid",
                    )
                    if (
                        sample_key in seen_sample_keys
                        or observation_key in seen_observation_keys
                    ):
                        _fail("online_sample_identity_duplicate", sample_key)
                    if snapshot_key not in snapshot_keys:
                        _fail("online_sample_snapshot_reference_missing", snapshot_key)
                    if feedback_key not in feedback_keys:
                        _fail("online_sample_feedback_reference_missing", feedback_key)
                    sample_keys.append(sample_key)
                    observation_keys.append(observation_key)
                    seen_sample_keys.add(sample_key)
                    seen_observation_keys.add(observation_key)
                    sample_index.append(
                        {
                            "sequence_index": sequence_index,
                            "sample_key": sample_key,
                            "observation_key": observation_key,
                            "snapshot_key": snapshot_key,
                            "camera_feedback_key": feedback_key,
                        }
                    )
                    sample_count += 1
                elif record_type in {"snapshot", "camera_feedback"}:
                    object_key = _nonempty_string(
                        row.get("object_key"), "online_object_key_invalid"
                    )
                    value = _mapping(
                        row.get("value"), "online_object_value_invalid"
                    )
                    prefix = (
                        "snapshot-sha256-"
                        if record_type == "snapshot"
                        else "camera-feedback-sha256-"
                    )
                    _require_equal(
                        object_key,
                        prefix + _sha256_json(value),
                        "online_object_key_hash_mismatch",
                    )
                    destination = snapshot_keys if record_type == "snapshot" else feedback_keys
                    if object_key in destination:
                        _fail("online_object_key_duplicate", object_key)
                    destination.add(object_key)
    except (gzip.BadGzipFile, EOFError, UnicodeError, json.JSONDecodeError) as exc:
        _fail("online_stream_invalid", f"{path.name}:{exc}")

    if header is None or footer is None:
        _fail("online_stream_incomplete", path.name)
    bindings = {
        "episode_uid": descriptor["episode_uid"],
        "scenario_version": descriptor["scenario_version"],
        "seed": descriptor["seed"],
        "episode_id": descriptor["episode_id"],
        "source_identity": descriptor["source_identity"],
        "synthetic_fixture": descriptor["synthetic_fixture"],
        "source_provenance": descriptor["source_provenance"],
    }
    for key, expected in bindings.items():
        _require_equal(header[key], expected, f"descriptor_header_binding_mismatch.{key}")
    header_domain, header_tier = _validate_source_provenance(
        header["source_provenance"],
        synthetic_fixture=_strict_bool(
            header["synthetic_fixture"], "synthetic_fixture_flag_invalid"
        ),
    )
    _require_equal(header_domain, source_domain, "source_domain_header_mismatch")
    _require_equal(header_tier, evidence_tier, "source_evidence_tier_header_mismatch")
    header_identity = _validate_source_identity(header["source_identity"])
    if header_identity["git_dirty"] is True:
        _fail("source_identity_dirty", str(descriptor["episode_uid"]))
    _require_equal(footer["sample_count"], sample_count, "stream_sample_count_mismatch")
    _require_equal(
        footer["unique_snapshot_count"],
        len(snapshot_keys),
        "stream_snapshot_count_mismatch",
    )
    _require_equal(
        footer["unique_camera_feedback_count"],
        len(feedback_keys),
        "stream_camera_feedback_count_mismatch",
    )
    _require_equal(
        footer["sample_index_sha256"],
        _sha256_json(sample_index),
        "sample_index_sha256_mismatch",
    )
    return _OnlineStreamEvidence(
        sample_count=sample_count,
        snapshot_count=len(snapshot_keys),
        camera_feedback_count=len(feedback_keys),
        record_count=record_count,
        sample_keys=tuple(sample_keys),
        observation_keys=tuple(observation_keys),
    )


def _audit_offline_file(
    path: Path,
    *,
    descriptor: Mapping[str, Any],
    stream_evidence: _OnlineStreamEvidence,
) -> int:
    payload = _load_json_object(path, "offline_labels")
    _require_fields(payload, _OFFLINE_FIELDS, "offline_fields_mismatch")
    _require_equal(
        payload["schema_version"],
        _OFFLINE_LABELS_SCHEMA,
        "offline_labels_schema_mismatch",
    )
    for key in ("episode_uid", "scenario_version", "seed", "episode_id"):
        _require_equal(
            payload[key],
            descriptor[key],
            f"descriptor_offline_binding_mismatch.{key}",
        )
    reward_bounds = _mapping(payload["reward_bounds"], "offline_reward_bounds_invalid")
    _require_fields(
        reward_bounds,
        frozenset({"minimum", "maximum"}),
        "offline_reward_bounds_fields_mismatch",
    )
    labels = payload["labels"]
    if not isinstance(labels, list):
        _fail("offline_labels_invalid")
    _require_equal(
        len(labels),
        stream_evidence.sample_count,
        "offline_label_count_mismatch",
    )
    sample_keys: list[str] = []
    observation_keys: list[str] = []
    for raw_label in labels:
        label = _mapping(raw_label, "offline_label_invalid")
        _require_fields(label, _OFFLINE_LABEL_FIELDS, "offline_label_fields_mismatch")
        _require_equal(
            label["schema_version"],
            _OFFLINE_LABEL_SCHEMA,
            "offline_label_schema_mismatch",
        )
        sample_keys.append(
            _nonempty_string(label["sample_key"], "offline_sample_key_invalid")
        )
        observation_keys.append(
            _nonempty_string(
                label["observation_key"], "offline_observation_key_invalid"
            )
        )
    _require_equal(
        tuple(sample_keys),
        stream_evidence.sample_keys,
        "offline_sample_key_binding_mismatch",
    )
    _require_equal(
        tuple(observation_keys),
        stream_evidence.observation_keys,
        "offline_observation_key_binding_mismatch",
    )
    return len(labels)


def _validate_source_provenance(
    raw: Any,
    *,
    synthetic_fixture: bool,
) -> tuple[str, str]:
    payload = _mapping(raw, "source_provenance_missing_or_invalid")
    _require_fields(payload, _SOURCE_PROVENANCE_FIELDS, "source_provenance_fields_mismatch")
    _require_equal(
        payload["schema_version"],
        _SOURCE_PROVENANCE_SCHEMA,
        "source_provenance_schema_mismatch",
    )
    domain = str(payload["source_domain"])
    if domain not in _SOURCE_TIER_BY_DOMAIN or domain == "legacy_unspecified":
        _fail("source_domain_invalid_or_legacy", domain)
    tier = str(payload["evidence_tier"])
    _require_equal(tier, _SOURCE_TIER_BY_DOMAIN[domain], "source_evidence_tier_mismatch")
    if synthetic_fixture != (domain == "synthetic_fixture"):
        _fail("source_fixture_flag_mismatch", domain)
    return domain, tier


def _validate_source_identity(raw: Any) -> dict[str, Any]:
    payload = _mapping(raw, "source_identity_invalid")
    _require_fields(payload, _SOURCE_IDENTITY_FIELDS, "source_identity_fields_mismatch")
    _require_equal(
        payload["schema_version"],
        _SOURCE_IDENTITY_SCHEMA,
        "source_identity_schema_mismatch",
    )
    commit = str(payload["git_commit"])
    if _GIT_COMMIT.fullmatch(commit) is None:
        _fail("source_identity_git_commit_invalid", commit)
    dirty = _strict_bool(payload["git_dirty"], "source_identity_git_dirty_invalid")
    config_sha = _require_sha256(
        payload["config_sha256"], "source_identity_config_sha256_invalid"
    )
    return {
        "schema_version": _SOURCE_IDENTITY_SCHEMA,
        "git_commit": commit,
        "git_dirty": dirty,
        "config_sha256": config_sha,
    }


def _validate_source_summary(raw: Any, episodes: Sequence[_EpisodeEvidence]) -> None:
    expected_domain_counts = {domain: 0 for domain in _SOURCE_DOMAINS}
    expected_tier_counts = {tier: 0 for tier in _EVIDENCE_TIERS}
    for episode in episodes:
        expected_domain_counts[episode.source_domain] += 1
        expected_tier_counts[episode.evidence_tier] += 1
    expected = {
        "episode_count": len(episodes),
        "episode_count_by_source_domain": expected_domain_counts,
        "episode_count_by_evidence_tier": expected_tier_counts,
        "explicit_source_domain_episode_count": len(episodes),
        "legacy_inferred_episode_count": 0,
        "external_runtime_attestation_validated": False,
    }
    _require_equal(raw, expected, "source_domain_summary_mismatch")


def _validate_source_identity_summary(
    raw: Any,
    episodes: Sequence[_EpisodeEvidence],
) -> None:
    expected = {
        "git_commits": sorted(
            {str(item.source_identity["git_commit"]) for item in episodes}
        ),
        "source_config_sha256_values": sorted(
            {str(item.source_identity["config_sha256"]) for item in episodes}
        ),
        "dirty_episode_count": 0,
        "clean_episode_count": len(episodes),
        "episode_count": len(episodes),
    }
    _require_equal(raw, expected, "source_identity_summary_mismatch")


def _validate_splits(
    manifest: Mapping[str, Any],
    descriptors: Sequence[Mapping[str, Any]],
    episodes: Sequence[_EpisodeEvidence],
) -> dict[str, Any]:
    policy = _mapping(manifest["split_policy"], "split_policy_invalid")
    _require_fields(policy, _SPLIT_POLICY_FIELDS, "split_policy_fields_mismatch")
    _require_equal(
        policy["unit"],
        "whole_episode_grouped_by_scenario_version_and_seed",
        "split_unit_mismatch",
    )
    _require_equal(
        policy["sample_or_transition_level_random_split"],
        False,
        "sample_random_split_forbidden",
    )
    _require_equal(
        policy["shared_seed_values_atomic_across_scenarios"],
        True,
        "shared_seed_split_policy_mismatch",
    )
    split_seed = _strict_int(policy["split_seed"], "split_seed_invalid")
    validation_fraction = _strict_fraction(
        policy["validation_fraction"], "validation_fraction_invalid"
    )
    test_fraction = _strict_fraction(policy["test_fraction"], "test_fraction_invalid")
    if validation_fraction + test_fraction >= 1.0:
        _fail("split_fraction_invalid")
    minimum_unseen = _strict_positive_int(
        policy["minimum_unseen_seed_count"], "minimum_unseen_seed_count_invalid"
    )
    declared_unseen = _strict_positive_int(
        policy["unseen_test_seed_count"], "unseen_test_seed_count_invalid"
    )

    split_seeds: dict[str, set[int]] = {
        "train": set(),
        "validation": set(),
        "test": set(),
    }
    split_by_seed: dict[int, str] = {}
    for episode in episodes:
        previous = split_by_seed.setdefault(episode.seed, episode.split)
        if previous != episode.split:
            _fail("split_seed_leakage", str(episode.seed))
        split_seeds[episode.split].add(episode.seed)
    if any(not values for values in split_seeds.values()):
        _fail("split_partition_empty")
    if (
        split_seeds["train"] & split_seeds["validation"]
        or split_seeds["train"] & split_seeds["test"]
        or split_seeds["validation"] & split_seeds["test"]
    ):
        _fail("split_seed_leakage")

    seed_values = sorted(split_by_seed)
    if len(seed_values) < 3:
        _fail("insufficient_split_seed_count")
    ordered = sorted(
        seed_values,
        key=lambda value: (
            sha256(f"{split_seed}\0{value}".encode("utf-8")).hexdigest(),
            value,
        ),
    )
    test_count = max(1, min(len(seed_values) - 2, round(len(seed_values) * test_fraction)))
    validation_count = max(
        1,
        min(
            len(seed_values) - test_count - 1,
            round(len(seed_values) * validation_fraction),
        ),
    )
    expected_by_seed = {
        value: (
            "test"
            if index < test_count
            else "validation"
            if index < test_count + validation_count
            else "train"
        )
        for index, value in enumerate(ordered)
    }
    _require_equal(split_by_seed, expected_by_seed, "split_assignment_mismatch")
    _require_equal(len(split_seeds["test"]), declared_unseen, "unseen_test_seed_count_mismatch")
    if declared_unseen < minimum_unseen:
        _fail("minimum_unseen_seed_requirement_not_met")

    split_payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "scenario_version": str(item["scenario_version"]),
            "seed": int(item["seed"]),
            "episode_id": str(item["episode_id"]),
            "split": str(item["split"]),
        }
        for item in sorted(descriptors, key=lambda value: str(value["episode_uid"]))
    ]
    expected_split_sha = _sha256_json(split_payload)
    _require_equal(
        _require_sha256(manifest["split_sha256"], "split_sha256_invalid"),
        expected_split_sha,
        "split_sha256_mismatch",
    )
    training_payload = [
        {
            "episode_uid": str(item["episode_uid"]),
            "online_sha256": str(item["online_sha256"]),
            "offline_sha256": str(item["offline_sha256"]),
            "source_identity": item["source_identity"],
        }
        for item in sorted(descriptors, key=lambda value: str(value["episode_uid"]))
        if item["split"] == "train"
    ]
    _require_equal(
        _require_sha256(
            manifest["training_set_sha256"], "training_set_sha256_invalid"
        ),
        _sha256_json(training_payload),
        "training_set_sha256_mismatch",
    )
    return {
        "seed_count_by_split": {
            name: len(split_seeds[name]) for name in ("train", "validation", "test")
        },
        "episode_count_by_split": dict(
            sorted(Counter(item.split for item in episodes).items())
        ),
        "seed_sets_mutually_exclusive": True,
        "split_sha256": expected_split_sha,
        "training_set_sha256": str(manifest["training_set_sha256"]),
    }


def _verify_checksum_inventory(
    root: Path,
) -> tuple[dict[str, str], dict[Path, _FileEvidence]]:
    checksum_path = root / "SHA256SUMS"
    if checksum_path.is_symlink() or not checksum_path.is_file():
        _fail("checksums_missing_or_invalid")
    checksum_evidence = _hash_regular_file(checksum_path)
    hashes = _read_checksums(checksum_path)
    actual_files: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            _fail("artifact_symlink_forbidden", path.relative_to(root).as_posix())
        if path.is_dir():
            continue
        if not path.is_file():
            _fail("artifact_type_invalid", path.relative_to(root).as_posix())
        if path != checksum_path:
            actual_files.add(path.relative_to(root).as_posix())
    if set(hashes) != actual_files:
        _fail(
            "checksum_artifact_set_mismatch",
            _set_difference_detail(set(hashes), actual_files),
        )
    evidence: dict[Path, _FileEvidence] = {checksum_path: checksum_evidence}
    for relative, expected in hashes.items():
        path = _safe_artifact_path(root, relative)
        item = _hash_regular_file(path)
        if item.sha256 != expected:
            _fail("artifact_sha256_mismatch", relative)
        if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) & 0o222:
            _fail("artifact_mutable", relative)
        evidence[path] = item
    if stat.S_IMODE(checksum_path.stat(follow_symlinks=False).st_mode) & 0o222:
        _fail("artifact_mutable", "SHA256SUMS")
    return hashes, evidence


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        _fail("checksums_invalid", str(exc))
    if not lines:
        _fail("checksums_invalid", "empty")
    result: dict[str, str] = {}
    previous = ""
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or _HEX_SHA256.fullmatch(parts[0]) is None:
            _fail("checksums_invalid", line)
        relative = _safe_relative(parts[1])
        if relative in result or relative <= previous:
            _fail("checksums_unsorted_or_duplicate", relative)
        result[relative] = parts[0]
        previous = relative
    return result


def _resolve_root(path: Path) -> Path:
    absolute = path.absolute()
    if absolute.is_symlink() or not absolute.is_dir():
        _fail("dataset_root_invalid", str(absolute))
    return absolute.resolve()


def _required_artifact(root: Path, relative: str, hashes: Mapping[str, str]) -> Path:
    safe = _safe_relative(relative)
    if safe not in hashes:
        _fail("artifact_not_registered", safe)
    return _safe_artifact_path(root, safe)


def _safe_artifact_path(root: Path, relative: str) -> Path:
    safe = _safe_relative(relative)
    path = root.joinpath(*PurePosixPath(safe).parts)
    current = path
    while current != root:
        if current.is_symlink():
            _fail("artifact_symlink_forbidden", safe)
        current = current.parent
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        _fail("artifact_missing", f"{safe}:{exc}")
    if not stat.S_ISREG(info.st_mode):
        _fail("regular_file_required", safe)
    return path


def _safe_relative(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw:
        _fail("artifact_path_invalid", str(raw))
    value = PurePosixPath(raw)
    if value.is_absolute() or not value.parts or any(part in {"", ".", ".."} for part in value.parts):
        _fail("artifact_path_invalid", raw)
    canonical = value.as_posix()
    if canonical != raw:
        _fail("artifact_path_not_canonical", raw)
    return canonical


def _hash_regular_file(path: Path) -> _FileEvidence:
    before = path.stat(follow_symlinks=False)
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat(follow_symlinks=False)
    before_fingerprint = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        stat.S_IMODE(before.st_mode),
    )
    after_fingerprint = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        stat.S_IMODE(after.st_mode),
    )
    if before_fingerprint != after_fingerprint:
        _fail("artifact_changed_during_audit", path.name)
    return _FileEvidence(
        path=path,
        sha256=digest.hexdigest(),
        device=int(after.st_dev),
        inode=int(after.st_ino),
        size=int(after.st_size),
        modified_ns=int(after.st_mtime_ns),
        mode=stat.S_IMODE(after.st_mode),
    )


def _verify_unchanged(evidence: _FileEvidence) -> None:
    info = evidence.path.stat(follow_symlinks=False)
    actual = (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_size),
        int(info.st_mtime_ns),
        stat.S_IMODE(info.st_mode),
    )
    expected = (
        evidence.device,
        evidence.inode,
        evidence.size,
        evidence.modified_ns,
        evidence.mode,
    )
    if actual != expected:
        _fail("artifact_changed_during_audit", evidence.path.name)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _fail("json_invalid", f"{label}:{exc}")
    return dict(_mapping(value, f"json_object_required.{label}"))


def _load_json_line(line: str, *, path: Path, line_number: int) -> dict[str, Any]:
    try:
        value = json.loads(
            line,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        _fail("online_json_invalid", f"{path.name}:{line_number}:{exc}")
    return dict(_mapping(value, "online_json_object_required"))


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _find_forbidden_online_identity(value: Any) -> list[str]:
    violations: list[str] = []

    def visit(item: Any, path: str, *, allow_center_id: bool = False) -> None:
        if isinstance(item, str):
            if not allow_center_id and _TRUTH_LIKE_ONLINE_VALUE.search(item):
                violations.append(path)
            return
        if item is None or isinstance(item, (bool, int, float)):
            return
        if isinstance(item, Mapping):
            for raw_key, child in item.items():
                key = _normalize_key(str(raw_key))
                child_path = f"{path}.{raw_key}"
                if (
                    key in _FORBIDDEN_ONLINE_KEYS
                    or key.startswith("truth_")
                    or key.endswith(_FORBIDDEN_ONLINE_SUFFIXES)
                ):
                    violations.append(child_path)
                else:
                    visit(
                        child,
                        child_path,
                        allow_center_id=key
                        in {"global_track_id", "target_global_track_id"},
                    )
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")
            return
        violations.append(path)

    visit(value, "online")
    return sorted(set(violations))


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code)
    return value


def _require_fields(value: Mapping[str, Any], expected: frozenset[str], code: str) -> None:
    if frozenset(value) != expected:
        _fail(code, _set_difference_detail(set(expected), set(value)))


def _require_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        _fail(code, f"expected={expected!r};actual={actual!r}")


def _require_sha256(value: Any, code: str) -> str:
    text = str(value)
    if _HEX_SHA256.fullmatch(text) is None:
        _fail(code, text)
    return text


def _strict_bool(value: Any, code: str) -> bool:
    if type(value) is not bool:
        _fail(code, repr(value))
    return value


def _strict_int(value: Any, code: str) -> int:
    if type(value) is not int:
        _fail(code, repr(value))
    return int(value)


def _strict_positive_int(value: Any, code: str) -> int:
    result = _strict_int(value, code)
    if result <= 0:
        _fail(code, repr(value))
    return result


def _strict_fraction(value: Any, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(code, repr(value))
    result = float(value)
    if not 0.0 < result < 1.0:
        _fail(code, repr(value))
    return result


def _nonempty_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code, repr(value))
    return value


def _sha256_json(value: Any) -> str:
    payload = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _set_difference_detail(expected: set[str], actual: set[str]) -> str:
    return (
        f"missing={sorted(expected - actual)!r};"
        f"extra={sorted(actual - expected)!r}"
    )


def _fail(code: str, detail: str = "") -> None:
    raise D5ActiveVisionSourceAuditError(code, detail)


__all__ = [
    "D5_ACTIVE_VISION_SOURCE_AUDIT_SCHEMA_VERSION",
    "D5ActiveVisionSourceAuditError",
    "audit_d5_active_vision_source_dataset",
]
