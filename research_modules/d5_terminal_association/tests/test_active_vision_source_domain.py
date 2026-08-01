from __future__ import annotations

from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from d5_terminal_association import (
    ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION,
    ActiveVisionCorpusCoveragePolicy,
    ActiveVisionDatasetValidationError,
    ActiveVisionEvidenceTier,
    ActiveVisionSourceDomain,
    ActiveVisionSourceIdentityV1,
    ActiveVisionSourceProvenanceV1,
    ActiveVisionSourceValidationError,
    audit_active_vision_episode_record,
    audit_active_vision_training_corpus,
    evidence_tier_for_source_domain,
    finalize_active_vision_episode_dataset,
    load_active_vision_episode_dataset,
    load_active_vision_episode_dataset_lazy,
    load_active_vision_episode_record,
    require_active_vision_simulation_research_corpus_ready,
    source_domain_for_new_artifact,
    source_domain_from_optional_provenance,
    stage_active_vision_episode_record,
    stage_active_vision_offline_labels,
    unavailable_active_vision_offline_labels,
)
from d5_terminal_association.active_vision_curriculum import (
    ActiveVisionCurriculumConfig,
    build_active_vision_curriculum_episode,
)


_GENERATION_CONFIG = {
    "recording_mode": "whole_episode",
    "policy_source": "deterministic_rule_demonstration",
    "source_contract_test": True,
}
_RESEARCH_POLICY = ActiveVisionCorpusCoveragePolicy(
    require_reserved_seed_evidence=False,
)


def _fixture_record(seed: int):
    record, _ = build_active_vision_curriculum_episode(
        seed,
        source_identity=ActiveVisionSourceIdentityV1(
            git_commit="a" * 40,
            git_dirty=False,
            config_sha256="b" * 64,
        ),
        config=ActiveVisionCurriculumConfig(
            global_track_id=f"GT-SOURCE-{seed:03d}",
            scenario_version="active-vision-source-domain-v1",
            episode_id_prefix="source-domain",
        ),
    )
    return record


def _record_for_domain(seed: int, domain: ActiveVisionSourceDomain):
    record = _fixture_record(seed)
    if domain is ActiveVisionSourceDomain.SYNTHETIC_FIXTURE:
        return replace(record, source_domain=domain)
    return replace(
        record,
        synthetic_fixture=False,
        source_domain=domain,
    )


def _stage_finalized_dataset(
    root: Path,
    domain: ActiveVisionSourceDomain,
):
    for seed in (70, 71, 72, 73, 74):
        record = _record_for_domain(seed, domain)
        stage_active_vision_episode_record(
            root,
            record,
            generation_config=_GENERATION_CONFIG,
        )
        stage_active_vision_offline_labels(
            root,
            record.episode_uid,
            unavailable_active_vision_offline_labels(record),
        )
    finalize_active_vision_episode_dataset(
        root,
        split_seed=17,
        minimum_unseen_seed_count=1,
    )
    return load_active_vision_episode_dataset_lazy(root)


def _rewrite_stream_header(path: Path, *, synthetic_fixture: bool) -> None:
    with gzip.open(path, mode="rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    rows[0].pop("source_provenance", None)
    rows[0]["synthetic_fixture"] = synthetic_fixture
    path.chmod(0o644)
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=6,
            fileobj=raw_handle,
            mtime=0,
        ) as stream:
            for row in rows:
                stream.write(
                    (
                        json.dumps(
                            row,
                            ensure_ascii=True,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("ascii")
                )


def _tamper_manifest_summary(root: Path) -> None:
    manifest_path = root / "manifest.json"
    checksums_path = root / "SHA256SUMS"
    manifest_path.chmod(0o644)
    checksums_path.chmod(0o644)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = manifest["source_domain_summary"]["episode_count_by_source_domain"]
    counts[ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME.value] += 1
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="ascii",
    )
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    lines = checksums_path.read_text(encoding="ascii").splitlines()
    rewritten = [
        f"{manifest_sha}  manifest.json"
        if line.endswith("  manifest.json")
        else line
        for line in lines
    ]
    checksums_path.write_text("\n".join(rewritten) + "\n", encoding="ascii")
    manifest_path.chmod(0o444)
    checksums_path.chmod(0o444)


@pytest.mark.parametrize(
    ("domain", "tier", "synthetic_fixture"),
    (
        (
            ActiveVisionSourceDomain.LEGACY_UNSPECIFIED,
            ActiveVisionEvidenceTier.LEGACY_UNCLASSIFIED,
            False,
        ),
        (
            ActiveVisionSourceDomain.SYNTHETIC_FIXTURE,
            ActiveVisionEvidenceTier.SOFTWARE_FIXTURE_ONLY,
            True,
        ),
        (
            ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME,
            ActiveVisionEvidenceTier.SIMULATION_RESEARCH,
            False,
        ),
        (
            ActiveVisionSourceDomain.AIRSIM_RUNTIME,
            ActiveVisionEvidenceTier.AIRSIM_DECLARATION_ONLY,
            False,
        ),
        (
            ActiveVisionSourceDomain.REAL_CAMERA_RUNTIME,
            ActiveVisionEvidenceTier.REAL_CAMERA_DECLARATION_ONLY,
            False,
        ),
    ),
)
def test_five_source_domains_have_bounded_evidence_tiers(
    domain: ActiveVisionSourceDomain,
    tier: ActiveVisionEvidenceTier,
    synthetic_fixture: bool,
) -> None:
    payload = None
    if domain is not ActiveVisionSourceDomain.LEGACY_UNSPECIFIED:
        payload = ActiveVisionSourceProvenanceV1(domain).to_payload()

    resolved, explicit = source_domain_from_optional_provenance(
        payload,
        synthetic_fixture=synthetic_fixture,
    )

    assert resolved is domain
    assert explicit is (payload is not None)
    assert evidence_tier_for_source_domain(resolved) is tier


def test_new_fixture_write_is_explicit_but_legacy_missing_records_stay_conservative(
    tmp_path: Path,
) -> None:
    current_root = tmp_path / "current"
    record = _fixture_record(80)
    descriptor = stage_active_vision_episode_record(
        current_root,
        record,
        generation_config=_GENERATION_CONFIG,
    )
    assert descriptor["source_provenance"]["source_domain"] == "synthetic_fixture"
    online_path = current_root / descriptor["online_file"]
    with gzip.open(online_path, mode="rt", encoding="utf-8") as stream:
        current_header = json.loads(next(stream))
    assert current_header["source_provenance"]["source_domain"] == "synthetic_fixture"

    _rewrite_stream_header(online_path, synthetic_fixture=True)
    legacy_fixture = load_active_vision_episode_record(online_path)
    fixture_audit = audit_active_vision_episode_record(online_path)
    assert legacy_fixture.source_domain is None
    assert legacy_fixture.effective_source_domain is ActiveVisionSourceDomain.SYNTHETIC_FIXTURE
    assert fixture_audit["source_domain_explicit"] is False
    assert fixture_audit["evidence_tier"] == "software_fixture_only"

    legacy_root = tmp_path / "legacy"
    legacy_descriptor = stage_active_vision_episode_record(
        legacy_root,
        _fixture_record(81),
        generation_config=_GENERATION_CONFIG,
    )
    legacy_path = legacy_root / legacy_descriptor["online_file"]
    _rewrite_stream_header(legacy_path, synthetic_fixture=False)
    legacy_unspecified = load_active_vision_episode_record(legacy_path)
    unspecified_audit = audit_active_vision_episode_record(legacy_path)
    assert legacy_unspecified.source_domain is None
    assert (
        legacy_unspecified.effective_source_domain
        is ActiveVisionSourceDomain.LEGACY_UNSPECIFIED
    )
    assert unspecified_audit["source_domain_explicit"] is False
    assert unspecified_audit["evidence_tier"] == "legacy_unclassified"


def test_point_mass_fixture_conflict_and_new_nonfixture_missing_source_are_rejected(
    tmp_path: Path,
) -> None:
    with pytest.raises(ActiveVisionSourceValidationError) as conflict:
        source_domain_for_new_artifact(
            ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME,
            synthetic_fixture=True,
        )
    assert conflict.value.code == "source_fixture_flag_mismatch"

    missing_source = replace(
        _fixture_record(82),
        synthetic_fixture=False,
        source_domain=None,
    )
    with pytest.raises(ActiveVisionDatasetValidationError) as missing:
        stage_active_vision_episode_record(
            tmp_path / "missing-source",
            missing_source,
            generation_config=_GENERATION_CONFIG,
        )
    assert missing.value.code == "source_provenance_required_for_new_artifact"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            lambda payload: payload.__setitem__("source_domain", "unknown-runtime"),
            "source_domain_invalid",
        ),
        (
            lambda payload: payload.__setitem__(
                "evidence_tier", "real_camera_declaration_only"
            ),
            "source_evidence_tier_mismatch",
        ),
        (
            lambda payload: payload.__setitem__("unexpected", False),
            "source_provenance_fields_mismatch",
        ),
    ),
)
def test_source_domain_tier_and_field_tampering_are_rejected(
    mutation,
    expected_code: str,
) -> None:
    payload = {
        "schema_version": ACTIVE_VISION_SOURCE_PROVENANCE_SCHEMA_VERSION,
        "source_domain": "scalable_3d_point_mass_runtime",
        "evidence_tier": "simulation_research",
    }
    mutation(payload)

    with pytest.raises(ActiveVisionSourceValidationError) as rejected:
        ActiveVisionSourceProvenanceV1.from_payload(
            payload,
            synthetic_fixture=False,
        )
    assert rejected.value.code == expected_code


def test_source_domain_summary_tampering_is_rejected_after_checksum_rebinding(
    tmp_path: Path,
) -> None:
    root = tmp_path / "point-mass-summary"
    _stage_finalized_dataset(
        root,
        ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME,
    )
    _tamper_manifest_summary(root)

    with pytest.raises(ActiveVisionDatasetValidationError) as rejected:
        load_active_vision_episode_dataset(root)
    assert rejected.value.code == "source_domain_summary_mismatch"


def test_clean_point_mass_corpus_stops_at_simulation_research_gate(
    tmp_path: Path,
) -> None:
    dataset = _stage_finalized_dataset(
        tmp_path / "point-mass",
        ActiveVisionSourceDomain.SCALABLE_3D_POINT_MASS_RUNTIME,
    )
    report = audit_active_vision_training_corpus(
        dataset,
        policy=_RESEARCH_POLICY,
    )

    assert report["training_gate"]["development_training_allowed"] is True
    gate = report["research_evidence_gate"]
    assert gate["status"] == "point_mass_simulation_research_eligible"
    assert gate["simulation_research_development_evaluation_eligible"] is True
    assert all(value is False for value in report["authority"].values())
    assert all(value is False for value in gate["claim_limits"].values())
    assert report["evidence_availability"]["formal_candidate"]["available"] is False
    require_active_vision_simulation_research_corpus_ready(
        {"training_corpus_audit": report}
    )


@pytest.mark.parametrize(
    ("domain", "tier"),
    (
        (
            ActiveVisionSourceDomain.AIRSIM_RUNTIME,
            ActiveVisionEvidenceTier.AIRSIM_DECLARATION_ONLY,
        ),
        (
            ActiveVisionSourceDomain.REAL_CAMERA_RUNTIME,
            ActiveVisionEvidenceTier.REAL_CAMERA_DECLARATION_ONLY,
        ),
    ),
)
def test_external_runtime_source_is_declaration_only_without_authority(
    tmp_path: Path,
    domain: ActiveVisionSourceDomain,
    tier: ActiveVisionEvidenceTier,
) -> None:
    dataset = _stage_finalized_dataset(tmp_path / domain.value, domain)
    report = audit_active_vision_training_corpus(
        dataset,
        policy=_RESEARCH_POLICY,
    )

    source_summary = dataset.manifest["source_domain_summary"]
    assert source_summary["episode_count_by_evidence_tier"][tier.value] == 5
    assert source_summary["external_runtime_attestation_validated"] is False
    gate = report["research_evidence_gate"]
    assert gate["simulation_research_development_evaluation_eligible"] is False
    assert "source_domain_not_exclusively_point_mass_runtime" in gate["failure_reasons"]
    assert all(value is False for value in gate["claim_limits"].values())
    assert all(value is False for value in report["authority"].values())
