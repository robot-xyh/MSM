"""Read-only canonical seed split views for D4 regional learning.

This module consumes the public shared-registry schema without importing the
main simulation runtime.  It verifies the frozen source registry, reproduces
the D3-compatible numeric-seed assignment, and overlays that assignment in
memory.  Source dataset manifests and episode artifacts remain unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from .region_resource_dataset import (
    LoadedRegionLearningDataset,
    RegionLearningDatasetValidationError,
    RegionLearningEpisodeManifest,
    RegionLearningEpisodeSource,
    RegionLearningFrame,
    RegionLearningSplit,
    load_region_learning_dataset,
)


SHARED_SEED_SPLIT_SCHEMA_VERSION = "scalable3d-shared-seed-split-registry-v1"
SHARED_SEED_SPLIT_POLICY_VERSION = "scalable3d-numeric-seed-atomic-split-v1"
TRAINING_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-training-seed-registry-v1"
ORDERING_COMPATIBILITY_VERSION = "d3_numeric_seed_atomic_split_v2"
CANONICAL_REGION_SPLIT_VIEW_SCHEMA = "d4-canonical-region-seed-split-view-v1"
CANONICAL_REGION_SPLIT_AUDIT_SCHEMA = "d4-canonical-region-seed-split-audit-v1"

EXPECTED_SPLIT_SEED = 20260720
EXPECTED_VALIDATION_FRACTION = 0.20
EXPECTED_TEST_FRACTION = 0.20
EXPECTED_MINIMUM_TEST_SEED_COUNT = 20
EXPECTED_UNIT = "numeric_seed_atomic_across_modules_scenarios_and_scales"
EXPECTED_CONSUMER_CONTRACT = {
    "original_dataset_mutation_allowed": False,
    "module_local_split_override_allowed": False,
    "cross_module_training_requires_exact_registry": True,
    "reserved_evaluation_seeds_allowed": False,
}

_SPLIT_NAMES = ("train", "validation", "test")
_SOURCE_REGISTRY_KEYS = {
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
_SHARED_REGISTRY_KEYS = {
    "schema_version",
    "policy_version",
    "ordering_compatibility_version",
    "source",
    "unit",
    "split_seed",
    "validation_fraction",
    "test_fraction",
    "minimum_test_seed_count",
    "training_seed_count",
    "reserved_evaluation_seed_count",
    "reserved_evaluation_seeds",
    "training_reserved_overlap_count",
    "split_seed_values",
    "assignments",
    "assignment_sha256",
    "consumer_contract",
    "content_sha256",
}
_SHARED_SOURCE_KEYS = {
    "training_seed_registry_schema_version",
    "training_seed_registry_sha256",
    "git_commit",
    "repository_dirty",
    "schedule_sha256",
}


class CanonicalRegionSplitError(RegionLearningDatasetValidationError):
    """Stable fail-closed error raised at the shared split boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}:{message}")
        self.code = str(code)


@dataclass(frozen=True)
class CanonicalRegionLearningEpisode:
    """One source episode with a detached canonical split assignment."""

    source: RegionLearningEpisodeSource
    frames: tuple[RegionLearningFrame, ...]
    split: RegionLearningSplit
    original_split: RegionLearningSplit
    manifest: RegionLearningEpisodeManifest


@dataclass(frozen=True)
class CanonicalRegionSplitBinding:
    """Content-addressed binding between a source dataset and shared registry."""

    source_dataset_sha256: str
    source_dataset_manifest_file_sha256: str
    source_dataset_split_sha256: str
    training_seed_registry_sha256: str
    shared_registry_file_sha256: str
    shared_registry_content_sha256: str
    assignment_sha256: str
    split_seed: int
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    test_seeds: tuple[int, ...]
    reserved_evaluation_seeds: tuple[int, ...]
    episode_count: int
    frame_count: int
    view_sha256: str
    schema: str = CANONICAL_REGION_SPLIT_VIEW_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != CANONICAL_REGION_SPLIT_VIEW_SCHEMA:
            raise ValueError("unsupported canonical region split view schema")
        for name in (
            "source_dataset_sha256",
            "source_dataset_manifest_file_sha256",
            "source_dataset_split_sha256",
            "training_seed_registry_sha256",
            "shared_registry_file_sha256",
            "shared_registry_content_sha256",
            "assignment_sha256",
            "view_sha256",
        ):
            _require_sha256(getattr(self, name), name)
        split_sets = (
            set(self.train_seeds),
            set(self.validation_seeds),
            set(self.test_seeds),
        )
        for values in (
            self.train_seeds,
            self.validation_seeds,
            self.test_seeds,
            self.reserved_evaluation_seeds,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("canonical seed catalogs must be unique and sorted")
        if any(not values for values in split_sets):
            raise ValueError("canonical split sets must be non-empty")
        if (
            split_sets[0] & split_sets[1]
            or split_sets[0] & split_sets[2]
            or split_sets[1] & split_sets[2]
        ):
            raise ValueError("canonical split sets must be disjoint")
        if set.union(*split_sets) & set(self.reserved_evaluation_seeds):
            raise ValueError("reserved evaluation seed entered canonical split")
        actual_counts = {
            "train": len(self.train_seeds),
            "validation": len(self.validation_seeds),
            "test": len(self.test_seeds),
        }
        if actual_counts != _expected_split_counts(sum(actual_counts.values())):
            raise ValueError("canonical split counts do not match shared policy")
        if int(self.split_seed) != EXPECTED_SPLIT_SEED:
            raise ValueError("canonical split seed does not match shared policy")
        if int(self.episode_count) <= 0 or int(self.frame_count) <= 0:
            raise ValueError("canonical split view requires episodes and frames")
        expected = _sha256_json(self.content_dict())
        if expected != self.view_sha256:
            raise ValueError("canonical split view hash mismatch")

    def content_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "source_dataset_sha256": self.source_dataset_sha256,
            "source_dataset_manifest_file_sha256": (
                self.source_dataset_manifest_file_sha256
            ),
            "source_dataset_split_sha256": self.source_dataset_split_sha256,
            "training_seed_registry_sha256": self.training_seed_registry_sha256,
            "shared_registry_file_sha256": self.shared_registry_file_sha256,
            "shared_registry_content_sha256": self.shared_registry_content_sha256,
            "assignment_sha256": self.assignment_sha256,
            "split_seed": int(self.split_seed),
            "train_seeds": list(self.train_seeds),
            "validation_seeds": list(self.validation_seeds),
            "test_seeds": list(self.test_seeds),
            "reserved_evaluation_seeds": list(self.reserved_evaluation_seeds),
            "episode_count": int(self.episode_count),
            "frame_count": int(self.frame_count),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.content_dict()
        payload["view_sha256"] = self.view_sha256
        return payload


@dataclass(frozen=True)
class CanonicalRegionLearningDatasetView:
    """Frozen in-memory overlay; source artifacts remain the authority."""

    source_dataset: LoadedRegionLearningDataset
    binding: CanonicalRegionSplitBinding
    episode_records: tuple[CanonicalRegionLearningEpisode, ...]

    def __post_init__(self) -> None:
        if self.binding.source_dataset_sha256 != self.source_dataset.manifest.dataset_sha256:
            raise ValueError("canonical view source dataset binding mismatch")
        if (
            self.binding.source_dataset_split_sha256
            != self.source_dataset.manifest.split.split_sha256
        ):
            raise ValueError("canonical view source split binding mismatch")
        if len(self.episode_records) != len(self.source_dataset.episode_records):
            raise ValueError("canonical view episode inventory mismatch")
        if self.binding.episode_count != len(self.episode_records):
            raise ValueError("canonical view binding episode count mismatch")
        if self.binding.frame_count != sum(
            len(item.frames) for item in self.episode_records
        ):
            raise ValueError("canonical view binding frame count mismatch")
        split_by_seed = {
            seed: RegionLearningSplit.TRAIN for seed in self.binding.train_seeds
        }
        split_by_seed.update(
            {
                seed: RegionLearningSplit.VALIDATION
                for seed in self.binding.validation_seeds
            }
        )
        split_by_seed.update(
            {seed: RegionLearningSplit.TEST for seed in self.binding.test_seeds}
        )
        for canonical, source in zip(
            self.episode_records,
            self.source_dataset.episode_records,
            strict=True,
        ):
            if (
                canonical.source != source.source
                or canonical.frames != source.frames
                or canonical.original_split != source.split
                or canonical.manifest != source.manifest
            ):
                raise ValueError("canonical view altered source episode content")
            if canonical.split != split_by_seed.get(int(canonical.source.seed)):
                raise ValueError("canonical view episode split mismatch")

    @property
    def root(self) -> Path:
        return self.source_dataset.root

    def assert_source(self, dataset: LoadedRegionLearningDataset) -> None:
        if dataset.manifest.dataset_sha256 != self.binding.source_dataset_sha256:
            raise CanonicalRegionSplitError(
                "source_dataset_mismatch",
                "canonical split view belongs to a different dataset",
            )
        if dataset.manifest.split.split_sha256 != self.binding.source_dataset_split_sha256:
            raise CanonicalRegionSplitError(
                "source_split_mismatch",
                "canonical split view belongs to a different source split",
            )
        if (
            _sha256_file(dataset.root / "manifest.json")
            != self.binding.source_dataset_manifest_file_sha256
        ):
            raise CanonicalRegionSplitError(
                "source_manifest_file_mismatch",
                "canonical split view belongs to a different manifest artifact",
            )

    def episodes(
        self, split: RegionLearningSplit | str | None = None
    ) -> tuple[CanonicalRegionLearningEpisode, ...]:
        if split is None:
            return self.episode_records
        resolved = (
            split
            if isinstance(split, RegionLearningSplit)
            else RegionLearningSplit(str(split))
        )
        return tuple(item for item in self.episode_records if item.split == resolved)

    def iter_frames(
        self, split: RegionLearningSplit | str | None = None
    ) -> Iterator[RegionLearningFrame]:
        for episode in self.episodes(split):
            yield from episode.frames


def load_canonical_region_learning_split_view(
    dataset: str | Path | LoadedRegionLearningDataset,
    *,
    shared_registry_path: str | Path,
    training_seed_registry_path: str | Path,
    expected_training_seed_registry_sha256: str | None = None,
) -> CanonicalRegionLearningDatasetView:
    """Validate and overlay the shared 60/20/20 split without source writes."""

    loaded = (
        dataset
        if isinstance(dataset, LoadedRegionLearningDataset)
        else load_region_learning_dataset(dataset)
    )
    source_path = Path(training_seed_registry_path)
    shared_path = Path(shared_registry_path)
    source_payload = _read_json_object(source_path, "training_seed_registry")
    source_sha256 = _sha256_file(source_path)
    if expected_training_seed_registry_sha256 is not None:
        _require_sha256(
            expected_training_seed_registry_sha256,
            "expected_training_seed_registry_sha256",
        )
        if source_sha256 != expected_training_seed_registry_sha256:
            raise CanonicalRegionSplitError(
                "source_registry_sha256_mismatch",
                "training seed registry does not match the caller binding",
            )
    source = _validate_training_seed_registry(source_payload)
    shared_payload = _read_json_object(shared_path, "shared_seed_split_registry")
    assignment = _validate_shared_registry(
        shared_payload,
        source=source,
        source_sha256=source_sha256,
    )

    dataset_seeds = tuple(
        sorted({int(item.source.seed) for item in loaded.episode_records})
    )
    expected_seeds = source["training_seeds"]
    reserved_in_dataset = sorted(set(dataset_seeds) & set(source["reserved_seeds"]))
    if reserved_in_dataset:
        raise CanonicalRegionSplitError(
            "reserved_seed_in_dataset",
            f"reserved evaluation seeds entered the dataset: {reserved_in_dataset}",
        )
    missing = sorted(set(expected_seeds) - set(dataset_seeds))
    extra = sorted(set(dataset_seeds) - set(expected_seeds))
    if missing or extra:
        raise CanonicalRegionSplitError(
            "dataset_seed_coverage_mismatch",
            f"missing={missing};extra={extra}",
        )

    records = tuple(
        CanonicalRegionLearningEpisode(
            source=item.source,
            frames=item.frames,
            split=RegionLearningSplit(assignment[int(item.source.seed)]),
            original_split=item.split,
            manifest=item.manifest,
        )
        for item in loaded.episode_records
    )
    split_seed_values = shared_payload["split_seed_values"]
    binding_content = {
        "schema": CANONICAL_REGION_SPLIT_VIEW_SCHEMA,
        "source_dataset_sha256": loaded.manifest.dataset_sha256,
        "source_dataset_manifest_file_sha256": _sha256_file(
            loaded.root / "manifest.json"
        ),
        "source_dataset_split_sha256": loaded.manifest.split.split_sha256,
        "training_seed_registry_sha256": source_sha256,
        "shared_registry_file_sha256": _sha256_file(shared_path),
        "shared_registry_content_sha256": shared_payload["content_sha256"],
        "assignment_sha256": shared_payload["assignment_sha256"],
        "split_seed": int(shared_payload["split_seed"]),
        "train_seeds": list(split_seed_values["train"]),
        "validation_seeds": list(split_seed_values["validation"]),
        "test_seeds": list(split_seed_values["test"]),
        "reserved_evaluation_seeds": list(source["reserved_seeds"]),
        "episode_count": len(records),
        "frame_count": sum(len(item.frames) for item in records),
    }
    binding = CanonicalRegionSplitBinding(
        **{
            **binding_content,
            "train_seeds": tuple(binding_content["train_seeds"]),
            "validation_seeds": tuple(binding_content["validation_seeds"]),
            "test_seeds": tuple(binding_content["test_seeds"]),
            "reserved_evaluation_seeds": tuple(
                binding_content["reserved_evaluation_seeds"]
            ),
            "view_sha256": _sha256_json(binding_content),
        }
    )
    return CanonicalRegionLearningDatasetView(
        source_dataset=loaded,
        binding=binding,
        episode_records=records,
    )


def audit_canonical_region_learning_split_view(
    view: CanonicalRegionLearningDatasetView,
) -> dict[str, Any]:
    """Return a truth-free data-governance audit for a canonical view."""

    canonical_episode_counts = {
        split.value: len(view.episodes(split)) for split in RegionLearningSplit
    }
    canonical_frame_counts = {
        split.value: sum(len(item.frames) for item in view.episodes(split))
        for split in RegionLearningSplit
    }
    source_episode_counts = {
        split.value: len(view.source_dataset.episodes(split))
        for split in RegionLearningSplit
    }
    return {
        "schema": CANONICAL_REGION_SPLIT_AUDIT_SCHEMA,
        "binding": view.binding.to_dict(),
        "source_split": {
            "episode_counts": source_episode_counts,
            "split_sha256": view.binding.source_dataset_split_sha256,
        },
        "canonical_split": {
            "seed_counts": {
                "train": len(view.binding.train_seeds),
                "validation": len(view.binding.validation_seeds),
                "test": len(view.binding.test_seeds),
            },
            "episode_counts": canonical_episode_counts,
            "frame_counts": canonical_frame_counts,
            "numeric_seed_atomic": all(
                len({item.split for item in view.episode_records if item.source.seed == seed})
                == 1
                for seed in (
                    *view.binding.train_seeds,
                    *view.binding.validation_seeds,
                    *view.binding.test_seeds,
                )
            ),
            "reserved_seed_count": len(view.binding.reserved_evaluation_seeds),
            "reserved_seed_present": False,
        },
        "readiness": {
            "behavior_cloning_view_available": bool(
                view.source_dataset.manifest.availability.behavior_cloning_available
            ),
            "ppo_available": bool(
                view.source_dataset.manifest.availability.ppo_available
            ),
            "assist_eligible": False,
            "development_data_governance_only": True,
            "model_performance_evidence": False,
        },
    }


def _validate_training_seed_registry(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != _SOURCE_REGISTRY_KEYS:
        raise CanonicalRegionSplitError(
            "source_registry_fields_mismatch",
            "training seed registry fields do not match schema v1",
        )
    if value.get("schema_version") != TRAINING_SEED_REGISTRY_SCHEMA_VERSION:
        raise CanonicalRegionSplitError(
            "source_registry_schema_mismatch",
            "unsupported training seed registry schema",
        )
    training = _canonical_seed_catalog(value.get("training_seeds"), "training_seeds")
    reserved = _canonical_seed_catalog(
        value.get("reserved_evaluation_seeds"),
        "reserved_evaluation_seeds",
        allow_empty=True,
    )
    if len(training) != _integer(value.get("training_seed_count"), "training_seed_count"):
        raise CanonicalRegionSplitError(
            "training_seed_count_mismatch", "training seed count does not match catalog"
        )
    if len(reserved) != _integer(
        value.get("reserved_evaluation_seed_count"),
        "reserved_evaluation_seed_count",
    ):
        raise CanonicalRegionSplitError(
            "reserved_seed_count_mismatch", "reserved seed count does not match catalog"
        )
    overlap = sorted(set(training) & set(reserved))
    if overlap or _integer(value.get("overlap_count"), "overlap_count") != 0:
        raise CanonicalRegionSplitError(
            "training_reserved_seed_overlap", f"overlap={overlap}"
        )
    commit = str(value.get("git_commit", ""))
    if len(commit) != 40 or not _is_lower_hex(commit):
        raise CanonicalRegionSplitError("source_git_commit_invalid", "invalid Git commit")
    if type(value.get("repository_dirty")) is not bool:
        raise CanonicalRegionSplitError(
            "source_repository_dirty_invalid", "repository_dirty must be boolean"
        )
    schedule_sha256 = value.get("schedule_sha256")
    if schedule_sha256 is not None:
        _require_sha256(schedule_sha256, "schedule_sha256")
    return {
        "training_seeds": training,
        "reserved_seeds": reserved,
        "git_commit": commit,
        "repository_dirty": value["repository_dirty"],
        "schedule_sha256": schedule_sha256,
    }


def _validate_shared_registry(
    value: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    source_sha256: str,
) -> dict[int, str]:
    if set(value) != _SHARED_REGISTRY_KEYS:
        raise CanonicalRegionSplitError(
            "shared_registry_fields_mismatch",
            "shared registry fields do not match schema v1",
        )
    if value.get("schema_version") != SHARED_SEED_SPLIT_SCHEMA_VERSION:
        raise CanonicalRegionSplitError(
            "shared_registry_schema_mismatch", "unsupported shared registry schema"
        )
    if value.get("policy_version") != SHARED_SEED_SPLIT_POLICY_VERSION:
        raise CanonicalRegionSplitError(
            "shared_registry_policy_mismatch", "unsupported shared split policy"
        )
    if value.get("ordering_compatibility_version") != ORDERING_COMPATIBILITY_VERSION:
        raise CanonicalRegionSplitError(
            "ordering_compatibility_mismatch", "registry is not D3 split compatible"
        )
    if value.get("unit") != EXPECTED_UNIT:
        raise CanonicalRegionSplitError("split_unit_mismatch", "unsupported split unit")
    if _integer(value.get("split_seed"), "split_seed") != EXPECTED_SPLIT_SEED:
        raise CanonicalRegionSplitError("split_seed_mismatch", "unexpected split seed")
    if (
        _number(value.get("validation_fraction"), "validation_fraction")
        != EXPECTED_VALIDATION_FRACTION
    ):
        raise CanonicalRegionSplitError(
            "validation_fraction_mismatch", "canonical validation fraction must be 0.20"
        )
    if _number(value.get("test_fraction"), "test_fraction") != EXPECTED_TEST_FRACTION:
        raise CanonicalRegionSplitError(
            "test_fraction_mismatch", "canonical test fraction must be 0.20"
        )
    if _integer(
        value.get("minimum_test_seed_count"), "minimum_test_seed_count"
    ) != EXPECTED_MINIMUM_TEST_SEED_COUNT:
        raise CanonicalRegionSplitError(
            "minimum_test_seed_count_mismatch", "canonical minimum test count must be 20"
        )
    if value.get("consumer_contract") != EXPECTED_CONSUMER_CONTRACT:
        raise CanonicalRegionSplitError(
            "consumer_contract_mismatch", "shared registry consumer contract changed"
        )

    content_sha256 = _require_sha256(value.get("content_sha256"), "content_sha256")
    unhashed = dict(value)
    unhashed.pop("content_sha256", None)
    if _sha256_json(unhashed) != content_sha256:
        raise CanonicalRegionSplitError(
            "content_sha256_mismatch", "shared registry content hash failed"
        )
    source_binding = value.get("source")
    if not isinstance(source_binding, dict) or set(source_binding) != _SHARED_SOURCE_KEYS:
        raise CanonicalRegionSplitError(
            "source_binding_fields_mismatch", "shared registry source binding is invalid"
        )
    if (
        source_binding.get("training_seed_registry_schema_version")
        != TRAINING_SEED_REGISTRY_SCHEMA_VERSION
    ):
        raise CanonicalRegionSplitError(
            "source_binding_schema_mismatch", "source registry schema binding changed"
        )
    if source_binding.get("training_seed_registry_sha256") != source_sha256:
        raise CanonicalRegionSplitError(
            "source_registry_sha256_mismatch", "shared registry source hash mismatch"
        )
    for key in ("git_commit", "repository_dirty", "schedule_sha256"):
        if source_binding.get(key) != source[key]:
            raise CanonicalRegionSplitError(
                "source_binding_metadata_mismatch", f"source metadata mismatch: {key}"
            )

    training = source["training_seeds"]
    reserved = source["reserved_seeds"]
    if _integer(value.get("training_seed_count"), "training_seed_count") != len(training):
        raise CanonicalRegionSplitError(
            "training_seed_count_mismatch", "shared registry training count mismatch"
        )
    if _integer(
        value.get("reserved_evaluation_seed_count"),
        "reserved_evaluation_seed_count",
    ) != len(reserved):
        raise CanonicalRegionSplitError(
            "reserved_seed_count_mismatch", "shared registry reserved count mismatch"
        )
    if value.get("reserved_evaluation_seeds") != list(reserved):
        raise CanonicalRegionSplitError(
            "reserved_seed_catalog_mismatch", "shared registry reserved catalog mismatch"
        )
    if _integer(
        value.get("training_reserved_overlap_count"),
        "training_reserved_overlap_count",
    ) != 0:
        raise CanonicalRegionSplitError(
            "training_reserved_seed_overlap", "shared registry reports seed overlap"
        )

    assignments = value.get("assignments")
    if not isinstance(assignments, list):
        raise CanonicalRegionSplitError(
            "assignments_invalid", "assignments must be a list"
        )
    assignment_sha256 = _require_sha256(
        value.get("assignment_sha256"), "assignment_sha256"
    )
    if _sha256_json(assignments) != assignment_sha256:
        raise CanonicalRegionSplitError(
            "assignment_sha256_mismatch", "assignment hash failed"
        )
    assignment: dict[int, str] = {}
    for item in assignments:
        if not isinstance(item, dict) or set(item) != {"seed", "split"}:
            raise CanonicalRegionSplitError(
                "assignment_record_invalid", "assignment record fields are invalid"
            )
        seed = _integer(item.get("seed"), "assignment.seed")
        split = str(item.get("split"))
        if split not in _SPLIT_NAMES:
            raise CanonicalRegionSplitError(
                "assignment_split_invalid", f"invalid split for seed {seed}"
            )
        if seed in assignment:
            raise CanonicalRegionSplitError(
                "duplicate_seed_assignment", f"seed {seed} is assigned more than once"
            )
        assignment[seed] = split
    if [item["seed"] for item in assignments] != sorted(assignment):
        raise CanonicalRegionSplitError(
            "assignment_order_invalid", "assignments must use canonical seed order"
        )
    reserved_assigned = sorted(set(assignment) & set(reserved))
    if reserved_assigned:
        raise CanonicalRegionSplitError(
            "reserved_seed_assigned", f"reserved seeds assigned: {reserved_assigned}"
        )
    missing = sorted(set(training) - set(assignment))
    extra = sorted(set(assignment) - set(training))
    if missing or extra:
        raise CanonicalRegionSplitError(
            "registry_seed_coverage_mismatch", f"missing={missing};extra={extra}"
        )

    expected = _d3_compatible_assignment(training)
    if assignment != expected:
        raise CanonicalRegionSplitError(
            "assignment_policy_reproduction_mismatch",
            "assignments do not reproduce the D3-compatible policy",
        )
    split_values = value.get("split_seed_values")
    if not isinstance(split_values, dict) or set(split_values) != set(_SPLIT_NAMES):
        raise CanonicalRegionSplitError(
            "split_seed_values_invalid", "split seed catalogs are invalid"
        )
    expected_values = {
        name: sorted(seed for seed, split in assignment.items() if split == name)
        for name in _SPLIT_NAMES
    }
    if split_values != expected_values:
        raise CanonicalRegionSplitError(
            "split_seed_values_mismatch", "split seed catalogs do not match assignments"
        )
    expected_counts = _expected_split_counts(len(training))
    actual_counts = {name: len(split_values[name]) for name in _SPLIT_NAMES}
    if actual_counts != expected_counts:
        raise CanonicalRegionSplitError(
            "split_count_mismatch",
            f"expected={expected_counts};actual={actual_counts}",
        )
    return assignment


def _d3_compatible_assignment(training_seeds: tuple[int, ...]) -> dict[int, str]:
    ordered = sorted(
        training_seeds,
        key=lambda seed: (
            sha256(
                f"{ORDERING_COMPATIBILITY_VERSION}|{EXPECTED_SPLIT_SEED}\0{seed}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            seed,
        ),
    )
    counts = _expected_split_counts(len(training_seeds))
    return {
        seed: (
            "test"
            if index < counts["test"]
            else "validation"
            if index < counts["test"] + counts["validation"]
            else "train"
        )
        for index, seed in enumerate(ordered)
    }


def _expected_split_counts(seed_count: int) -> dict[str, int]:
    if seed_count < 3:
        raise CanonicalRegionSplitError(
            "insufficient_training_seeds", "at least three training seeds are required"
        )
    test_count = max(1, min(seed_count - 2, round(seed_count * EXPECTED_TEST_FRACTION)))
    validation_count = max(
        1,
        min(
            seed_count - test_count - 1,
            round(seed_count * EXPECTED_VALIDATION_FRACTION),
        ),
    )
    if test_count < EXPECTED_MINIMUM_TEST_SEED_COUNT:
        raise CanonicalRegionSplitError(
            "insufficient_test_seeds", "canonical test split contains fewer than 20 seeds"
        )
    return {
        "train": seed_count - validation_count - test_count,
        "validation": validation_count,
        "test": test_count,
    }


def _canonical_seed_catalog(
    value: Any, name: str, *, allow_empty: bool = False
) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise CanonicalRegionSplitError("seed_catalog_invalid", f"{name} must be a list")
    seeds = tuple(_integer(seed, name) for seed in value)
    if any(seed < 0 for seed in seeds):
        raise CanonicalRegionSplitError("negative_seed", f"{name} contains a negative seed")
    if not seeds and not allow_empty:
        raise CanonicalRegionSplitError("seed_catalog_empty", f"{name} must not be empty")
    if seeds != tuple(sorted(set(seeds))):
        raise CanonicalRegionSplitError(
            "seed_catalog_not_canonical", f"{name} must be unique and sorted"
        )
    return seeds


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalRegionSplitError(
            "json_read_failed", f"cannot read {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalRegionSplitError(
            "json_object_required", f"{label} must be a JSON object"
        )
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise CanonicalRegionSplitError("integer_invalid", f"{name} must be an integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalRegionSplitError(
            "integer_invalid", f"{name} must be an integer"
        ) from exc
    if value != integer:
        raise CanonicalRegionSplitError("integer_invalid", f"{name} must be an integer")
    return integer


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise CanonicalRegionSplitError("number_invalid", f"{name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CanonicalRegionSplitError(
            "number_invalid", f"{name} must be numeric"
        ) from exc
    if not number == number or number in (float("inf"), float("-inf")):
        raise CanonicalRegionSplitError("number_invalid", f"{name} must be finite")
    return number


def _require_sha256(value: Any, name: str) -> str:
    text = str(value)
    if len(text) != 64 or not _is_lower_hex(text):
        raise CanonicalRegionSplitError(
            "sha256_invalid", f"{name} must be a lowercase SHA-256 digest"
        )
    return text


def _is_lower_hex(value: str) -> bool:
    return bool(value) and all(char in "0123456789abcdef" for char in value)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise CanonicalRegionSplitError(
            "file_hash_failed", f"cannot hash file: {path}"
        ) from exc
    return digest.hexdigest()
