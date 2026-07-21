"""Atomic 100-seed supplemental curriculum generation for D5 active vision.

This module only orchestrates existing D5 contracts. It creates no center
identity, online truth, reward, outcome, counterfactual, or causal label. The
result is a detached synthetic development dataset with a read-only canonical
seed view; it never rewrites the formal 900-episode dataset.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .active_vision_contracts import (
    ActiveVisionRuntimeMode,
    assert_truth_free_active_vision_payload,
)
from .active_vision_curriculum import (
    ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT,
    ACTIVE_VISION_CURRICULUM_SCHEMA_VERSION,
    ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT,
    ActiveVisionCurriculumConfig,
    build_active_vision_curriculum_episode,
)
from .active_vision_episode_dataset import (
    ActiveVisionSourceIdentityV1,
    LazyActiveVisionEpisodeDataset,
    finalize_active_vision_episode_dataset,
    load_active_vision_episode_dataset_lazy,
    stage_active_vision_episode_record,
    stage_active_vision_offline_labels,
    unavailable_active_vision_offline_labels,
)
from .canonical_seed_view import (
    SHARED_SEED_SPLIT_SCHEMA_VERSION,
    TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
    active_vision_canonical_readiness,
    load_active_vision_canonical_seed_view,
    write_active_vision_canonical_seed_view,
    write_canonical_readiness,
)


ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SCHEMA_VERSION = (
    "d5.active-vision-supplemental-curriculum.v1"
)
ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SUMMARY_SCHEMA_VERSION = (
    "d5.active-vision-supplemental-curriculum-summary.v1"
)
ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_AUDIT_SCHEMA_VERSION = (
    "d5.active-vision-supplemental-curriculum-audit.v1"
)
ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_CONFIG_SCHEMA_VERSION = (
    "d5.active-vision-supplemental-curriculum-config.v1"
)
ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT = 100
RESERVED_ACTIVE_VISION_EVALUATION_SEEDS = tuple(range(1000, 1020))

_SPLITS = ("train", "validation", "test")
_EXPECTED_CANONICAL_SEED_COUNTS = {
    "train": 60,
    "validation": 20,
    "test": 20,
}
_EXPECTED_INTENT_COUNTS = {
    "hold": 2,
    "observe_target": 6,
    "reacquire": 2,
    "search_sector": 2,
}
_EXPECTED_FOV_COUNTS = {"wide": 10, "zoom": 2}
_EXPECTED_ROLE_COUNTS = {"interceptor": 6, "recon": 6}
_EXPECTED_ACK_COUNTS = {"applied": 4, "rejected": 4, "missing": 4}
_UNAVAILABLE_LABEL_NAMES = ("reward", "outcome", "counterfactual", "causal_label")
_TRAINING_REGISTRY_KEYS = {
    "schema_version",
    "git_commit",
    "repository_dirty",
    "schedule_sha256",
    "training_seed_count",
    "training_seeds",
    "reserved_evaluation_seed_count",
    "reserved_evaluation_seeds",
    "overlap_count",
}


class ActiveVisionSupplementalCurriculumError(RuntimeError):
    """Fail-closed generation or audit error."""


@dataclass(frozen=True)
class GeneratedActiveVisionSupplementalCurriculum:
    """Strictly reloaded handles for one atomically published curriculum."""

    output_dir: Path
    dataset: LazyActiveVisionEpisodeDataset
    canonical_dataset: LazyActiveVisionEpisodeDataset
    canonical_readiness: Mapping[str, Any]
    summary: Mapping[str, Any]


def generate_active_vision_supplemental_curriculum(
    output_dir: str | Path,
    *,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    created_at_utc: str,
    global_track_id: str,
    source_git_commit: str,
    source_repository_dirty: bool,
    config: ActiveVisionCurriculumConfig | None = None,
    tracked_summary_path: str | Path | None = None,
    tracked_markdown_path: str | Path | None = None,
) -> GeneratedActiveVisionSupplementalCurriculum:
    """Generate, audit, and atomically publish the separate 100-seed corpus."""

    destination = Path(output_dir).resolve()
    training_path = Path(training_seed_registry_path).resolve()
    shared_path = Path(shared_seed_registry_path).resolve()
    resolved_tracked_summary_path = (
        Path(tracked_summary_path).resolve()
        if tracked_summary_path is not None
        else None
    )
    resolved_tracked_markdown_path = (
        Path(tracked_markdown_path).resolve()
        if tracked_markdown_path is not None
        else None
    )
    artifact_paths = [("output_dir", destination)]
    if resolved_tracked_summary_path is not None:
        artifact_paths.append(
            ("tracked_summary_path", resolved_tracked_summary_path)
        )
    if resolved_tracked_markdown_path is not None:
        artifact_paths.append(
            ("tracked_markdown_path", resolved_tracked_markdown_path)
        )
    _assert_artifacts_outside_registry_source_roots(
        artifact_paths,
        protected_roots=(training_path.parent, shared_path.parent),
    )
    if destination.exists():
        raise ActiveVisionSupplementalCurriculumError(
            f"curriculum destination already exists: {destination}"
        )
    created_at = str(created_at_utc).strip()
    if not created_at:
        raise ValueError("created_at_utc must not be empty")
    if type(source_repository_dirty) is not bool:
        raise ValueError("source_repository_dirty must be a boolean")

    explicit_track_id = str(global_track_id).strip()
    resolved_config = config or ActiveVisionCurriculumConfig(
        global_track_id=explicit_track_id
    )
    if not isinstance(resolved_config, ActiveVisionCurriculumConfig):
        raise TypeError("config must be ActiveVisionCurriculumConfig")
    if resolved_config.global_track_id != explicit_track_id:
        raise ValueError(
            "config.global_track_id must match the explicitly supplied global_track_id"
        )

    tracked_paths = tuple(path for _, path in artifact_paths[1:])
    if any(path == destination or destination in path.parents for path in tracked_paths):
        raise ValueError("tracked outputs must be outside the curriculum destination")

    seed_catalog = _load_training_seed_catalog(training_path)
    training_seeds = seed_catalog["training_seeds"]
    reserved_seeds = seed_catalog["reserved_evaluation_seeds"]
    training_registry_sha256 = _sha256_file(training_path)
    shared_registry_sha256 = _sha256_file(shared_path)
    _preflight_shared_registry_binding(
        shared_path,
        training_registry_sha256=training_registry_sha256,
        training_seeds=training_seeds,
        reserved_seeds=reserved_seeds,
    )
    generation_config = _generation_config_payload(
        resolved_config,
        training_registry_sha256=training_registry_sha256,
        shared_registry_sha256=shared_registry_sha256,
    )
    generation_config_sha256 = _sha256_json(generation_config)
    source_identity = ActiveVisionSourceIdentityV1(
        git_commit=source_git_commit,
        git_dirty=source_repository_dirty,
        config_sha256=generation_config_sha256,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    try:
        dataset_dir = temporary_root / "dataset"
        for seed in training_seeds:
            record, episode_summary = build_active_vision_curriculum_episode(
                seed,
                source_identity=source_identity,
                config=resolved_config,
            )
            _assert_builder_summary(episode_summary.to_payload(), seed=seed)
            stage_active_vision_episode_record(
                dataset_dir,
                record,
                generation_config=generation_config,
            )
            stage_active_vision_offline_labels(
                dataset_dir,
                record.episode_uid,
                unavailable_active_vision_offline_labels(record),
            )

        manifest = finalize_active_vision_episode_dataset(
            dataset_dir,
            split_seed=20260720,
            validation_fraction=0.20,
            test_fraction=0.20,
            minimum_unseen_seed_count=20,
        )
        dataset = load_active_vision_episode_dataset_lazy(
            dataset_dir,
            expected_generation_config_sha256=manifest["dataset_config_sha256"],
        )
        _assert_registry_files_unchanged(
            training_path,
            training_registry_sha256,
            shared_path,
            shared_registry_sha256,
        )
        source_manifest_sha256 = dataset.manifest_sha256
        view_path = temporary_root / "canonical_seed_view.json"
        canonical_dataset, view_manifest, view_manifest_sha256 = (
            write_active_vision_canonical_seed_view(
                dataset_dir,
                training_seed_registry_path=training_path,
                shared_seed_registry_path=shared_path,
                view_manifest_path=view_path,
            )
        )
        source_after_view = load_active_vision_episode_dataset_lazy(dataset_dir)
        if source_after_view.manifest_sha256 != source_manifest_sha256:
            raise ActiveVisionSupplementalCurriculumError(
                "canonical view modified the source manifest"
            )
        readiness = active_vision_canonical_readiness(
            canonical_dataset,
            view_manifest=view_manifest,
            view_manifest_sha256=view_manifest_sha256,
        )
        readiness_json_path = temporary_root / "canonical_readiness.json"
        readiness_markdown_path = temporary_root / "canonical_readiness.md"
        readiness_json_sha256, readiness_markdown_sha256 = write_canonical_readiness(
            readiness,
            json_path=readiness_json_path,
            markdown_path=readiness_markdown_path,
        )
        summary = audit_active_vision_supplemental_curriculum(
            dataset,
            canonical_dataset=canonical_dataset,
            view_manifest=view_manifest,
            view_manifest_sha256=view_manifest_sha256,
            canonical_readiness=readiness,
            canonical_readiness_json_sha256=readiness_json_sha256,
            canonical_readiness_markdown_sha256=readiness_markdown_sha256,
            config=resolved_config,
            created_at_utc=created_at,
            training_seeds=training_seeds,
            reserved_seeds=reserved_seeds,
            source_identity=source_identity,
            generation_config_sha256=generation_config_sha256,
            training_registry_sha256=training_registry_sha256,
            shared_registry_sha256=shared_registry_sha256,
        )
        _write_json_atomic(temporary_root / "curriculum_summary.json", summary)
        _write_text_atomic(
            temporary_root / "curriculum_report.md",
            _curriculum_markdown(summary),
        )

        verified_dataset = load_active_vision_episode_dataset_lazy(dataset_dir)
        verified_canonical = load_active_vision_canonical_seed_view(
            dataset_dir,
            training_seed_registry_path=training_path,
            shared_seed_registry_path=shared_path,
            view_manifest_path=view_path,
        )
        verified_readiness = active_vision_canonical_readiness(
            verified_canonical,
            view_manifest=view_manifest,
            view_manifest_sha256=view_manifest_sha256,
        )
        if _plain_json(verified_readiness) != _plain_json(readiness):
            raise ActiveVisionSupplementalCurriculumError(
                "canonical readiness changed during pre-publication reload"
            )
        verified_summary = audit_active_vision_supplemental_curriculum(
            verified_dataset,
            canonical_dataset=verified_canonical,
            view_manifest=view_manifest,
            view_manifest_sha256=view_manifest_sha256,
            canonical_readiness=verified_readiness,
            canonical_readiness_json_sha256=_sha256_file(readiness_json_path),
            canonical_readiness_markdown_sha256=_sha256_file(
                readiness_markdown_path
            ),
            config=resolved_config,
            created_at_utc=created_at,
            training_seeds=training_seeds,
            reserved_seeds=reserved_seeds,
            source_identity=source_identity,
            generation_config_sha256=generation_config_sha256,
            training_registry_sha256=training_registry_sha256,
            shared_registry_sha256=shared_registry_sha256,
        )
        if verified_summary != summary:
            raise ActiveVisionSupplementalCurriculumError(
                "curriculum summary changed during pre-publication reload"
            )
        _assert_registry_files_unchanged(
            training_path,
            training_registry_sha256,
            shared_path,
            shared_registry_sha256,
        )
        if destination.exists():
            raise ActiveVisionSupplementalCurriculumError(
                f"curriculum destination appeared before publication: {destination}"
            )
        os.replace(temporary_root, destination)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    published = _load_published_curriculum(
        destination,
        training_path=training_path,
        shared_path=shared_path,
        training_seeds=training_seeds,
        reserved_seeds=reserved_seeds,
        source_identity=source_identity,
        config=resolved_config,
        created_at_utc=created_at,
        generation_config_sha256=generation_config_sha256,
        training_registry_sha256=training_registry_sha256,
        shared_registry_sha256=shared_registry_sha256,
    )
    if resolved_tracked_summary_path is not None:
        _write_json_atomic(resolved_tracked_summary_path, published.summary)
    if resolved_tracked_markdown_path is not None:
        _write_text_atomic(
            resolved_tracked_markdown_path,
            _curriculum_markdown(published.summary),
        )
    return published


def audit_active_vision_supplemental_curriculum(
    dataset: LazyActiveVisionEpisodeDataset,
    *,
    canonical_dataset: LazyActiveVisionEpisodeDataset,
    view_manifest: Mapping[str, Any],
    view_manifest_sha256: str,
    canonical_readiness: Mapping[str, Any],
    canonical_readiness_json_sha256: str,
    canonical_readiness_markdown_sha256: str,
    config: ActiveVisionCurriculumConfig,
    created_at_utc: str,
    training_seeds: Sequence[int],
    reserved_seeds: Sequence[int],
    source_identity: ActiveVisionSourceIdentityV1,
    generation_config_sha256: str,
    training_registry_sha256: str,
    shared_registry_sha256: str,
) -> dict[str, Any]:
    """Audit every episode, sample, label, split, identity, and hash binding."""

    expected_seeds = tuple(training_seeds)
    expected_reserved = tuple(reserved_seeds)
    violations: list[str] = []
    descriptors = tuple(dataset.episode_descriptors)
    descriptor_seeds = tuple(int(item["seed"]) for item in descriptors)
    descriptor_seed_counts = Counter(descriptor_seeds)
    if len(descriptors) != ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT:
        violations.append("episode_count_mismatch")
    if tuple(sorted(descriptor_seed_counts)) != expected_seeds:
        violations.append("dataset_seed_catalog_mismatch")
    if any(count != 1 for count in descriptor_seed_counts.values()):
        violations.append("episode_per_seed_mismatch")
    reserved_overlap = sorted(set(descriptor_seeds) & set(expected_reserved))
    if reserved_overlap:
        violations.append("reserved_seed_leakage")

    intent_counts: Counter[str] = Counter()
    fov_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    ack_counts: Counter[str] = Counter()
    sample_count = 0
    segment_count = 0
    dirty_episode_count = 0
    synthetic_episode_count = 0
    truth_guard_episode_count = 0
    unavailable_label_count = Counter()
    observed_center_ids: set[str] = set()
    runtime_mode_counts: Counter[str] = Counter()

    for loaded in dataset.iter_episodes():
        record = loaded.record
        try:
            assert_truth_free_active_vision_payload(record)
        except ValueError:
            violations.append(f"{record.episode_uid}:online_truth_guard_failed")
        else:
            truth_guard_episode_count += 1
        if record.seed not in descriptor_seed_counts:
            violations.append(f"{record.episode_uid}:unknown_seed")
        if record.scenario_version != config.scenario_version:
            violations.append(f"{record.episode_uid}:scenario_version_mismatch")
        if record.episode_id != f"{config.episode_id_prefix}-{record.seed}":
            violations.append(f"{record.episode_uid}:episode_id_mismatch")
        if record.source_identity != source_identity:
            violations.append(f"{record.episode_uid}:source_identity_mismatch")
        dirty_episode_count += int(record.source_identity.git_dirty)
        synthetic_episode_count += int(record.synthetic_fixture)
        samples = tuple(record.samples)
        sample_count += len(samples)
        if len(samples) != ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT:
            violations.append(f"{record.episode_uid}:sample_count_mismatch")
            continue

        sequence = [item.sequence_index for item in samples]
        timestamps = [item.snapshot.snapshot_timestamp for item in samples]
        plan_versions = [item.plan_version for item in samples]
        coalition_versions = [item.coalition_version for item in samples]
        communication_versions = [item.communication_version for item in samples]
        expected_plan_versions = [
            config.initial_plan_version + offset
            for offset in (0, 1, 2, 2, 2, 3, 3, 3, 4, 5, 6, 7)
        ]
        expected_coalition_versions = [
            config.initial_coalition_version + offset
            for offset in (0, 1, 2, 2, 2, 3, 3, 3, 4, 5, 6, 7)
        ]
        expected_communication_versions = list(
            range(
                config.initial_communication_version,
                config.initial_communication_version + len(samples),
            )
        )
        if sequence != list(range(len(samples))):
            violations.append(f"{record.episode_uid}:sequence_not_contiguous")
        if not all(right > left for left, right in zip(timestamps, timestamps[1:])):
            violations.append(f"{record.episode_uid}:timestamp_not_strict")
        if plan_versions != expected_plan_versions:
            violations.append(f"{record.episode_uid}:plan_version_contract_changed")
        if coalition_versions != expected_coalition_versions:
            violations.append(
                f"{record.episode_uid}:coalition_version_contract_changed"
            )
        if communication_versions != expected_communication_versions:
            violations.append(
                f"{record.episode_uid}:communication_version_contract_changed"
            )
        segment_count += len(set(zip(plan_versions, coalition_versions)))

        episode_intents: Counter[str] = Counter()
        episode_fovs: Counter[str] = Counter()
        episode_roles: Counter[str] = Counter()
        episode_acks: Counter[str] = Counter()
        for index, sample in enumerate(samples):
            action = sample.effective_action
            episode_intents[action.intent.value] += 1
            episode_fovs[action.fov_mode.value] += 1
            role = _camera_role(sample.camera_id, config)
            if role is None:
                violations.append(f"{record.episode_uid}:{index}:unknown_camera_role")
            else:
                episode_roles[role] += 1
            outcome = _ack_outcome(sample.runtime_ack)
            episode_acks[outcome] += 1
            if sample.requested_mode is not ActiveVisionRuntimeMode.DISABLED:
                violations.append(f"{record.episode_uid}:{index}:requested_mode_enabled")
            if sample.effective_mode is not ActiveVisionRuntimeMode.DISABLED:
                violations.append(f"{record.episode_uid}:{index}:effective_mode_enabled")
            runtime_mode_counts[sample.effective_mode.value] += 1
            if sample.runtime_ack is not None:
                expected_status = "applied" if sample.runtime_ack.accepted else "rejected_"
                if sample.runtime_ack.accepted:
                    if sample.runtime_ack.status_code != expected_status:
                        violations.append(
                            f"{record.episode_uid}:{index}:applied_ack_status_mismatch"
                        )
                elif not sample.runtime_ack.status_code.startswith(expected_status):
                    violations.append(
                        f"{record.episode_uid}:{index}:rejected_ack_status_mismatch"
                    )
                if (
                    sample.runtime_ack.command_version
                    != sample.effective_action.communication_version
                ):
                    violations.append(
                        f"{record.episode_uid}:{index}:ack_command_version_mismatch"
                    )
            observed_center_ids.update(
                track.global_track_id for track in sample.snapshot.tracks
            )
            observed_center_ids.update(
                item.global_track_id for item in sample.snapshot.plan.assignments
            )
            observed_center_ids.update(
                item.global_track_id for item in sample.snapshot.projections
            )
            for candidate in (
                sample.rule_demonstration_action,
                sample.requested_action,
                sample.effective_action,
            ):
                if candidate is not None and candidate.target_global_track_id is not None:
                    observed_center_ids.add(candidate.target_global_track_id)
            track_ids = {
                track.global_track_id for track in sample.snapshot.tracks
            }
            assignment_ids = {
                item.global_track_id for item in sample.snapshot.plan.assignments
            }
            projection_ids = {
                item.global_track_id for item in sample.snapshot.projections
            }
            if track_ids != {config.global_track_id}:
                violations.append(
                    f"{record.episode_uid}:{index}:center_track_reference_mismatch"
                )
            if assignment_ids != {config.global_track_id}:
                violations.append(
                    f"{record.episode_uid}:{index}:assignment_reference_mismatch"
                )
            if not projection_ids.issubset({config.global_track_id}):
                violations.append(
                    f"{record.episode_uid}:{index}:projection_reference_mismatch"
                )
            expected_track_version = config.initial_track_version + index
            if any(
                track.track_version != expected_track_version
                for track in sample.snapshot.tracks
            ):
                violations.append(
                    f"{record.episode_uid}:{index}:track_version_contract_changed"
                )

        if dict(episode_intents) != _EXPECTED_INTENT_COUNTS:
            violations.append(f"{record.episode_uid}:intent_coverage_mismatch")
        if dict(episode_fovs) != _EXPECTED_FOV_COUNTS:
            violations.append(f"{record.episode_uid}:fov_coverage_mismatch")
        if dict(episode_roles) != _EXPECTED_ROLE_COUNTS:
            violations.append(f"{record.episode_uid}:camera_role_coverage_mismatch")
        if dict(episode_acks) != _EXPECTED_ACK_COUNTS:
            violations.append(f"{record.episode_uid}:ack_fault_coverage_mismatch")
        intent_counts.update(episode_intents)
        fov_counts.update(episode_fovs)
        role_counts.update(episode_roles)
        ack_counts.update(episode_acks)

        if len(loaded.offline_labels) != len(samples):
            violations.append(f"{record.episode_uid}:offline_label_count_mismatch")
        for label in loaded.offline_labels:
            availability = {
                "reward": label.reward_available,
                "outcome": label.outcome_available,
                "counterfactual": label.counterfactual_available,
                "causal_label": label.causal_label_available,
            }
            for name, available in availability.items():
                if available:
                    violations.append(
                        f"{record.episode_uid}:{label.sample_key}:{name}_fabricated"
                    )
                else:
                    unavailable_label_count[name] += 1
            if any(
                value is not None
                for value in (
                    label.reward,
                    label.reward_provenance,
                    label.outcome,
                    label.counterfactual_reward,
                    label.counterfactual_provenance,
                    label.causal_label,
                )
            ):
                violations.append(
                    f"{record.episode_uid}:{label.sample_key}:unavailable_value_not_null"
                )

    if observed_center_ids != {config.global_track_id}:
        violations.append("global_track_id_created_or_rebound")
    if synthetic_episode_count != len(descriptors):
        violations.append("non_synthetic_episode_present")
    if dirty_episode_count != (
        len(descriptors) if source_identity.git_dirty else 0
    ):
        violations.append("dirty_source_summary_mismatch")

    manifest_availability = _plain_json(dataset.manifest["availability"])
    for name in _UNAVAILABLE_LABEL_NAMES:
        item = manifest_availability.get(name, {})
        if (
            item.get("status") != "unavailable"
            or int(item.get("available_sample_count", -1)) != 0
            or int(item.get("sample_count", -1)) != sample_count
            or unavailable_label_count[name] != sample_count
        ):
            violations.append(f"{name}_availability_mismatch")

    canonical_split = _plain_json(view_manifest["canonical_split"])
    if canonical_split.get("seed_counts") != _EXPECTED_CANONICAL_SEED_COUNTS:
        violations.append("canonical_seed_count_mismatch")
    if canonical_split.get("episode_counts") != _EXPECTED_CANONICAL_SEED_COUNTS:
        violations.append("canonical_episode_count_mismatch")
    expected_sample_counts = {
        split: count * ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT
        for split, count in _EXPECTED_CANONICAL_SEED_COUNTS.items()
    }
    if canonical_split.get("sample_counts") != expected_sample_counts:
        violations.append("canonical_sample_count_mismatch")
    if canonical_split.get("reserved_evaluation_seed_overlap") != []:
        violations.append("canonical_reserved_seed_leakage")
    if view_manifest["source"]["manifest_sha256"] != dataset.manifest_sha256:
        violations.append("canonical_source_manifest_sha_mismatch")
    if canonical_dataset.root != dataset.root:
        violations.append("canonical_source_root_changed")
    if canonical_dataset.manifest_sha256 != view_manifest_sha256:
        violations.append("canonical_view_file_sha_mismatch")
    if view_manifest["training_seed_registry"]["file_sha256"] != (
        training_registry_sha256
    ):
        violations.append("training_registry_sha_mismatch")
    if view_manifest["shared_seed_registry"]["file_sha256"] != (
        shared_registry_sha256
    ):
        violations.append("shared_registry_sha_mismatch")
    if canonical_readiness["view_manifest_sha256"] != view_manifest_sha256:
        violations.append("readiness_view_sha_mismatch")
    if canonical_readiness["source_manifest_sha256"] != dataset.manifest_sha256:
        violations.append("readiness_source_sha_mismatch")
    if _plain_json(canonical_readiness["offline_label_availability"]) != (
        manifest_availability
    ):
        violations.append("readiness_availability_mismatch")
    readiness_admission = canonical_readiness["admission"]
    if readiness_admission.get("assist") is not False:
        violations.append("canonical_readiness_assist_enabled")
    if readiness_admission.get("ppo") is not False:
        violations.append("canonical_readiness_ppo_enabled")
    source_summary = _plain_json(dataset.manifest["source_identity_summary"])
    if source_summary.get("source_config_sha256_values") != [
        generation_config_sha256
    ]:
        violations.append("source_config_sha_mismatch")
    if int(source_summary.get("dirty_episode_count", -1)) != dirty_episode_count:
        violations.append("manifest_dirty_episode_count_mismatch")

    if violations:
        raise ActiveVisionSupplementalCurriculumError(
            "supplemental curriculum audit failed: " + ",".join(sorted(set(violations)))
        )

    episode_count = len(descriptors)
    clean_source = dirty_episode_count == 0
    coverage = {
        "episode_count": episode_count,
        "segment_count": segment_count,
        "sample_count": sample_count,
        "intent_counts": _ordered_counts(
            intent_counts,
            tuple(_EXPECTED_INTENT_COUNTS),
        ),
        "fov_mode_counts": _ordered_counts(
            fov_counts,
            tuple(_EXPECTED_FOV_COUNTS),
        ),
        "camera_role_counts": _ordered_counts(
            role_counts,
            tuple(_EXPECTED_ROLE_COUNTS),
        ),
    }
    content: dict[str, Any] = {
        "schema_version": (
            ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SUMMARY_SCHEMA_VERSION
        ),
        "curriculum_schema_version": (
            ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SCHEMA_VERSION
        ),
        "episode_curriculum_schema_version": ACTIVE_VISION_CURRICULUM_SCHEMA_VERSION,
        "created_at_utc": created_at_utc,
        "purpose": "synthetic_behavior_cloning_development_and_offline_shadow_only",
        "config": config.to_payload(),
        "source_binding": {
            "git_commit": source_identity.git_commit,
            "repository_dirty": source_identity.git_dirty,
            "curriculum_generation_config_schema_version": (
                ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_CONFIG_SCHEMA_VERSION
            ),
            "curriculum_generation_config_sha256": generation_config_sha256,
            "dataset_config_sha256": dataset.manifest["dataset_config_sha256"],
            "training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
            "training_seed_registry_sha256": training_registry_sha256,
            "shared_seed_registry_schema_version": (
                SHARED_SEED_SPLIT_SCHEMA_VERSION
            ),
            "shared_seed_registry_sha256": shared_registry_sha256,
            "shared_seed_registry_content_sha256": view_manifest[
                "shared_seed_registry"
            ]["content_sha256"],
            "shared_seed_registry_assignment_sha256": view_manifest[
                "shared_seed_registry"
            ]["assignment_sha256"],
        },
        "dataset": {
            "schema_version": dataset.manifest["schema_version"],
            "manifest_sha256": dataset.manifest_sha256,
            "content_sha256": view_manifest["source"]["content_sha256"],
            "native_split_sha256": dataset.manifest["split_sha256"],
            "native_training_set_sha256": dataset.manifest["training_set_sha256"],
            "native_split_episode_counts": _descriptor_split_counts(descriptors),
            "episode_count": episode_count,
            "unique_seed_count": len(descriptor_seed_counts),
            "sample_count": sample_count,
        },
        "canonical": {
            "view_schema_version": view_manifest["schema_version"],
            "view_manifest_sha256": view_manifest_sha256,
            "view_content_sha256": view_manifest["content_sha256"],
            "split": canonical_split,
            "source_manifest_modified": False,
            "source_episode_or_sample_rewritten": False,
            "readiness_json_sha256": canonical_readiness_json_sha256,
            "readiness_markdown_sha256": canonical_readiness_markdown_sha256,
            "readiness": _plain_json(canonical_readiness),
        },
        "coverage": coverage,
        "ack_fault_coverage": {
            "counts": _ordered_counts(ack_counts, tuple(_EXPECTED_ACK_COUNTS)),
            "per_episode_counts": dict(_EXPECTED_ACK_COUNTS),
            "interpretation": "deterministic_fault_injection_coverage_only",
            "runtime_distribution_evidence": False,
            "reward_or_outcome_evidence": False,
        },
        "version_and_identity_audit": {
            "sequence_contiguous": True,
            "timestamps_strictly_increasing": True,
            "plan_and_coalition_versions_monotonic": True,
            "communication_and_track_versions_strictly_increasing": True,
            "global_track_id_source": "caller_owned_center_reference",
            "global_track_id_values": [config.global_track_id],
            "global_track_id_created_or_rebound": False,
            "runtime_mode_counts": _ordered_counts(
                runtime_mode_counts,
                (ActiveVisionRuntimeMode.DISABLED.value,),
            ),
        },
        "truth_seed_and_formal_isolation": {
            "truth_guard_passed_episode_count": truth_guard_episode_count,
            "online_truth_identifier_count": 0,
            "training_seed_count": len(expected_seeds),
            "reserved_evaluation_seeds": list(expected_reserved),
            "reserved_seed_overlap": reserved_overlap,
            "synthetic_episode_count": synthetic_episode_count,
            "non_synthetic_episode_count": episode_count - synthetic_episode_count,
            "formal_900_episode_dataset_modified": False,
        },
        "offline_label_availability": {
            **manifest_availability,
            "all_values_explicitly_unavailable": True,
            "zero_padding_used": False,
        },
        "admission": {
            "clean_source": clean_source,
            "dirty_episode_count": dirty_episode_count,
            "behavior_cloning_view_available": True,
            "behavior_cloning_development_eligible": clean_source,
            "status": (
                "development_shadow_only"
                if clean_source
                else "fail_closed_dirty_source"
            ),
            "synthetic_curriculum_only": True,
            "ppo_available": False,
            "online_assist_available": False,
            "online_authority_available": False,
            "camera_command_authority_available": False,
            "rule_fallback_required": True,
        },
        "audit": {
            "schema_version": (
                ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_AUDIT_SCHEMA_VERSION
            ),
            "passed": True,
            "strict_lazy_loader_passed": True,
            "canonical_loader_passed": True,
            "violation_count": 0,
            "violations": [],
        },
    }
    return {**content, "content_sha256": _sha256_json(content)}


def _load_published_curriculum(
    destination: Path,
    *,
    training_path: Path,
    shared_path: Path,
    training_seeds: Sequence[int],
    reserved_seeds: Sequence[int],
    source_identity: ActiveVisionSourceIdentityV1,
    config: ActiveVisionCurriculumConfig,
    created_at_utc: str,
    generation_config_sha256: str,
    training_registry_sha256: str,
    shared_registry_sha256: str,
) -> GeneratedActiveVisionSupplementalCurriculum:
    dataset_dir = destination / "dataset"
    view_path = destination / "canonical_seed_view.json"
    readiness_json_path = destination / "canonical_readiness.json"
    readiness_markdown_path = destination / "canonical_readiness.md"
    summary_path = destination / "curriculum_summary.json"
    report_path = destination / "curriculum_report.md"
    dataset = load_active_vision_episode_dataset_lazy(dataset_dir)
    canonical_dataset = load_active_vision_canonical_seed_view(
        dataset_dir,
        training_seed_registry_path=training_path,
        shared_seed_registry_path=shared_path,
        view_manifest_path=view_path,
    )
    view_manifest = _read_json(view_path)
    view_manifest_sha256 = _sha256_file(view_path)
    readiness = active_vision_canonical_readiness(
        canonical_dataset,
        view_manifest=view_manifest,
        view_manifest_sha256=view_manifest_sha256,
    )
    stored_readiness = _read_json(readiness_json_path)
    if _plain_json(readiness) != stored_readiness:
        raise ActiveVisionSupplementalCurriculumError(
            "published canonical readiness does not reproduce"
        )
    expected_summary = audit_active_vision_supplemental_curriculum(
        dataset,
        canonical_dataset=canonical_dataset,
        view_manifest=view_manifest,
        view_manifest_sha256=view_manifest_sha256,
        canonical_readiness=readiness,
        canonical_readiness_json_sha256=_sha256_file(readiness_json_path),
        canonical_readiness_markdown_sha256=_sha256_file(readiness_markdown_path),
        config=config,
        created_at_utc=created_at_utc,
        training_seeds=training_seeds,
        reserved_seeds=reserved_seeds,
        source_identity=source_identity,
        generation_config_sha256=generation_config_sha256,
        training_registry_sha256=training_registry_sha256,
        shared_registry_sha256=shared_registry_sha256,
    )
    stored_summary = _read_json(summary_path)
    if expected_summary != stored_summary:
        raise ActiveVisionSupplementalCurriculumError(
            "published curriculum summary does not reproduce"
        )
    if report_path.read_text(encoding="utf-8") != _curriculum_markdown(stored_summary):
        raise ActiveVisionSupplementalCurriculumError(
            "published curriculum Markdown does not reproduce"
        )
    _assert_registry_files_unchanged(
        training_path,
        training_registry_sha256,
        shared_path,
        shared_registry_sha256,
    )
    return GeneratedActiveVisionSupplementalCurriculum(
        output_dir=destination,
        dataset=dataset,
        canonical_dataset=canonical_dataset,
        canonical_readiness=readiness,
        summary=stored_summary,
    )


def _generation_config_payload(
    config: ActiveVisionCurriculumConfig,
    *,
    training_registry_sha256: str,
    shared_registry_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_CONFIG_SCHEMA_VERSION,
        "episode_curriculum": config.to_payload(),
        "training_seed_contract": {
            "expected_seed_count": ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT,
            "reserved_evaluation_seeds": list(
                RESERVED_ACTIVE_VISION_EVALUATION_SEEDS
            ),
            "one_episode_per_seed": True,
        },
        "coverage_contract": {
            "segment_count_per_episode": ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT,
            "sample_count_per_episode": ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT,
            "intent_counts_per_episode": dict(_EXPECTED_INTENT_COUNTS),
            "fov_mode_counts_per_episode": dict(_EXPECTED_FOV_COUNTS),
            "camera_role_counts_per_episode": dict(_EXPECTED_ROLE_COUNTS),
            "ack_fault_counts_per_episode": dict(_EXPECTED_ACK_COUNTS),
        },
        "registry_binding": {
            "training_seed_registry_schema_version": (
                TRAINING_SEED_REGISTRY_SCHEMA_VERSION
            ),
            "training_seed_registry_sha256": training_registry_sha256,
            "shared_seed_registry_schema_version": (
                SHARED_SEED_SPLIT_SCHEMA_VERSION
            ),
            "shared_seed_registry_sha256": shared_registry_sha256,
        },
        "offline_labels": {
            name: "unavailable" for name in _UNAVAILABLE_LABEL_NAMES
        },
        "admission": {
            "ppo": False,
            "assist": False,
            "authority": False,
        },
    }


def _load_training_seed_catalog(path: Path) -> dict[str, tuple[int, ...]]:
    payload = _read_json(path)
    if set(payload) != _TRAINING_REGISTRY_KEYS:
        raise ActiveVisionSupplementalCurriculumError(
            "training seed registry fields changed"
        )
    if payload.get("schema_version") != TRAINING_SEED_REGISTRY_SCHEMA_VERSION:
        raise ActiveVisionSupplementalCurriculumError(
            "unsupported training seed registry schema"
        )
    training = _canonical_seed_tuple(payload.get("training_seeds"), "training_seeds")
    reserved = _canonical_seed_tuple(
        payload.get("reserved_evaluation_seeds"),
        "reserved_evaluation_seeds",
    )
    if len(training) != ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT:
        raise ActiveVisionSupplementalCurriculumError(
            "training seed registry must contain exactly 100 seeds"
        )
    if int(payload.get("training_seed_count", -1)) != len(training):
        raise ActiveVisionSupplementalCurriculumError("training seed count mismatch")
    if reserved != RESERVED_ACTIVE_VISION_EVALUATION_SEEDS:
        raise ActiveVisionSupplementalCurriculumError(
            "reserved evaluation seed catalog must be 1000-1019"
        )
    if int(payload.get("reserved_evaluation_seed_count", -1)) != len(reserved):
        raise ActiveVisionSupplementalCurriculumError("reserved seed count mismatch")
    overlap = sorted(set(training) & set(reserved))
    if overlap or int(payload.get("overlap_count", -1)) != 0:
        raise ActiveVisionSupplementalCurriculumError(
            "training and reserved evaluation seeds overlap"
        )
    commit = str(payload.get("git_commit", ""))
    if len(commit) != 40 or not _is_lower_hex(commit):
        raise ActiveVisionSupplementalCurriculumError(
            "training registry Git commit binding is invalid"
        )
    if type(payload.get("repository_dirty")) is not bool:
        raise ActiveVisionSupplementalCurriculumError(
            "training registry repository_dirty must be a boolean"
        )
    schedule = payload.get("schedule_sha256")
    if schedule is not None and (
        len(str(schedule)) != 64 or not _is_lower_hex(str(schedule))
    ):
        raise ActiveVisionSupplementalCurriculumError(
            "training registry schedule_sha256 is invalid"
        )
    return {
        "training_seeds": training,
        "reserved_evaluation_seeds": reserved,
    }


def _canonical_seed_tuple(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ActiveVisionSupplementalCurriculumError(f"{name} must be a list")
    if any(type(seed) is not int or seed < 0 for seed in value):
        raise ActiveVisionSupplementalCurriculumError(
            f"{name} must contain non-negative integers"
        )
    result = tuple(value)
    if result != tuple(sorted(set(result))):
        raise ActiveVisionSupplementalCurriculumError(
            f"{name} must be sorted and unique"
        )
    return result


def _preflight_shared_registry_binding(
    path: Path,
    *,
    training_registry_sha256: str,
    training_seeds: Sequence[int],
    reserved_seeds: Sequence[int],
) -> None:
    payload = _read_json(path)
    if payload.get("schema_version") != SHARED_SEED_SPLIT_SCHEMA_VERSION:
        raise ActiveVisionSupplementalCurriculumError(
            "unsupported shared seed registry schema"
        )
    declared_content_sha256 = str(payload.get("content_sha256", ""))
    unhashed = dict(payload)
    unhashed.pop("content_sha256", None)
    if (
        len(declared_content_sha256) != 64
        or not _is_lower_hex(declared_content_sha256)
        or _sha256_json(unhashed) != declared_content_sha256
    ):
        raise ActiveVisionSupplementalCurriculumError(
            "shared seed registry content SHA256 mismatch"
        )
    source = payload.get("source")
    if not isinstance(source, Mapping):
        raise ActiveVisionSupplementalCurriculumError(
            "shared seed registry source binding is missing"
        )
    if source.get("training_seed_registry_schema_version") != (
        TRAINING_SEED_REGISTRY_SCHEMA_VERSION
    ):
        raise ActiveVisionSupplementalCurriculumError(
            "shared registry training schema binding mismatch"
        )
    if source.get("training_seed_registry_sha256") != training_registry_sha256:
        raise ActiveVisionSupplementalCurriculumError(
            "shared registry training file SHA256 binding mismatch"
        )
    if int(payload.get("training_seed_count", -1)) != len(training_seeds):
        raise ActiveVisionSupplementalCurriculumError(
            "shared registry training seed count mismatch"
        )
    if payload.get("reserved_evaluation_seeds") != list(reserved_seeds):
        raise ActiveVisionSupplementalCurriculumError(
            "shared registry reserved seed catalog mismatch"
        )


def _assert_builder_summary(payload: Mapping[str, Any], *, seed: int) -> None:
    expected = {
        "seed": seed,
        "episode_count": 1,
        "segment_count": ACTIVE_VISION_CURRICULUM_SEGMENT_COUNT,
        "sample_count": ACTIVE_VISION_CURRICULUM_SAMPLE_COUNT,
        "camera_count": 2,
        "intent_counts": _EXPECTED_INTENT_COUNTS,
        "fov_mode_counts": _EXPECTED_FOV_COUNTS,
        "camera_role_counts": _EXPECTED_ROLE_COUNTS,
        "ack_outcome_counts": _EXPECTED_ACK_COUNTS,
    }
    for name, value in expected.items():
        if payload.get(name) != value:
            raise ActiveVisionSupplementalCurriculumError(
                f"single-seed curriculum summary changed for seed {seed}: {name}"
            )


def _camera_role(
    camera_id: str,
    config: ActiveVisionCurriculumConfig,
) -> str | None:
    if camera_id == config.interceptor_camera_id:
        return "interceptor"
    if camera_id == config.recon_camera_id:
        return "recon"
    return None


def _ack_outcome(runtime_ack: Any) -> str:
    if runtime_ack is None:
        return "missing"
    return "applied" if runtime_ack.accepted else "rejected"


def _ordered_counts(counts: Mapping[str, int], order: Sequence[str]) -> dict[str, int]:
    return {name: int(counts.get(name, 0)) for name in order}


def _descriptor_split_counts(
    descriptors: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    counts = Counter(str(item["split"]) for item in descriptors)
    return {split: counts[split] for split in _SPLITS}


def _assert_registry_files_unchanged(
    training_path: Path,
    training_sha256: str,
    shared_path: Path,
    shared_sha256: str,
) -> None:
    if _sha256_file(training_path) != training_sha256:
        raise ActiveVisionSupplementalCurriculumError(
            "training seed registry changed during generation"
        )
    if _sha256_file(shared_path) != shared_sha256:
        raise ActiveVisionSupplementalCurriculumError(
            "shared seed registry changed during generation"
        )


def _assert_artifacts_outside_registry_source_roots(
    artifacts: Sequence[tuple[str, Path]],
    *,
    protected_roots: Sequence[Path],
) -> None:
    for artifact_name, artifact_path in artifacts:
        for source_root in protected_roots:
            if artifact_path == source_root or source_root in artifact_path.parents:
                raise ActiveVisionSupplementalCurriculumError(
                    f"{artifact_name} must be outside registry source root "
                    f"{source_root}: {artifact_path}"
                )


def _curriculum_markdown(summary: Mapping[str, Any]) -> str:
    coverage = summary["coverage"]
    canonical = summary["canonical"]["split"]
    admission = summary["admission"]
    binding = summary["source_binding"]
    return "\n".join(
        [
            "# D5 主动视觉补充课程报告",
            "",
            f"- 创建时间：`{summary['created_at_utc']}`",
            f"- 准入状态：`{admission['status']}`",
            f"- episode / segment / sample 数量：`{coverage['episode_count']} / {coverage['segment_count']} / {coverage['sample_count']}`",
            f"- canonical seed 分配：`{_inline_json(canonical['seed_counts'])}`",
            f"- intent 覆盖：`{_inline_json(coverage['intent_counts'])}`",
            f"- FOV 模式覆盖：`{_inline_json(coverage['fov_mode_counts'])}`",
            f"- 相机角色覆盖：`{_inline_json(coverage['camera_role_counts'])}`",
            f"- ACK 故障注入覆盖：`{_inline_json(summary['ack_fault_coverage']['counts'])}`",
            "",
            "上述 ACK 计数仅表示每个 seed 的 `4/4/4` 确定性故障注入覆盖，不是实际运行分布，"
            "也不是 reward、outcome、counterfactual 或 causal 证据。",
            "",
            f"- 数据集 manifest SHA256：`{summary['dataset']['manifest_sha256']}`",
            f"- canonical view SHA256：`{summary['canonical']['view_manifest_sha256']}`",
            f"- 数据集配置 SHA256：`{binding['dataset_config_sha256']}`",
            f"- training registry SHA256：`{binding['training_seed_registry_sha256']}`",
            f"- shared registry SHA256：`{binding['shared_seed_registry_sha256']}`",
            "",
            "所有离线 reward、outcome、counterfactual 和 causal 字段均显式标记为 unavailable。"
            "PPO、assist、在线 authority 和相机命令 authority 均保持 false。该 synthetic 补充制品"
            "不修改，也不替代正式 900-episode 数据集。",
            "",
        ]
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ActiveVisionSupplementalCurriculumError(
            f"invalid JSON artifact: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ActiveVisionSupplementalCurriculumError(
            f"JSON artifact must be an object: {path}"
        )
    return payload


def _plain_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _plain_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _inline_json(value: Any) -> str:
    return _canonical_json_bytes(value).decode("utf-8")


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: str | Path) -> str:
    digest = sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ActiveVisionSupplementalCurriculumError(
            f"cannot hash artifact: {path}"
        ) from exc
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical_json_bytes(value) + b"\n"
    _write_bytes_atomic(path, payload)


def _write_text_atomic(path: Path, value: str) -> None:
    _write_bytes_atomic(path, value.encode("utf-8"))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _is_lower_hex(value: str) -> bool:
    return bool(value) and all(character in "0123456789abcdef" for character in value)


__all__ = [
    "ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_AUDIT_SCHEMA_VERSION",
    "ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_CONFIG_SCHEMA_VERSION",
    "ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SCHEMA_VERSION",
    "ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SEED_COUNT",
    "ACTIVE_VISION_SUPPLEMENTAL_CURRICULUM_SUMMARY_SCHEMA_VERSION",
    "RESERVED_ACTIVE_VISION_EVALUATION_SEEDS",
    "ActiveVisionSupplementalCurriculumError",
    "GeneratedActiveVisionSupplementalCurriculum",
    "audit_active_vision_supplemental_curriculum",
    "generate_active_vision_supplemental_curriculum",
]
