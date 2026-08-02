"""Fail-closed incremental writer for the frozen D4 A2 v8 TRAIN source.

The writer consumes already constructed online frames and independent offline
labels.  It does not build simulator treatments, infer labels, train a model,
or grant runtime authority.  A complete source is published only after the
existing strict v8 loader can round-trip all frozen registry entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
import tempfile
from typing import Sequence

from .region_resource_v8_development_contract import (
    LoadedV8FrozenRequest,
    LoadedV8TrainDataset,
    REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA,
    REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA,
    RegionResourceV8ContractError,
    RegionResourceV8ValidationError,
    V8_DATASET_STATUS,
    V8_MAIN_SCHEDULE_STATUS,
    V8EpisodeManifestEntry,
    V8MainGenerationSchedule,
    V8MainGenerationScheduleEntry,
    V8NoAuthorityPermissions,
    V8OfflineTransferLabel,
    V8OnlineRegionResourceFrame,
    V8TrainDatasetManifest,
    canonical_v8_json_line,
    canonical_v8_sha256,
    load_v8_development_train_dataset,
    load_v8_episode_pair,
    load_v8_frozen_request,
)


class RegionResourceV8DatasetWriterError(RegionResourceV8ContractError):
    """An incremental write operation violated the frozen v8 boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class V8CleanSourceMetadata:
    """Frozen clean-source identity repeated on every generation entry."""

    source_scenario_id: str
    source_scenario_version: str
    source_git_commit: str
    source_git_dirty: bool
    source_config_sha256: str

    def __post_init__(self) -> None:
        for name in ("source_scenario_id", "source_scenario_version"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise RegionResourceV8DatasetWriterError(
                    f"v8_writer_source_string_invalid:{name}"
                )
        commit = self.source_git_commit
        if (
            not isinstance(commit, str)
            or len(commit) not in {40, 64}
            or commit != commit.lower()
            or any(character not in "0123456789abcdef" for character in commit)
        ):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_source_git_commit_invalid"
            )
        if type(self.source_git_dirty) is not bool:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_source_git_dirty_not_boolean"
            )
        if self.source_git_dirty:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_dirty_source_forbidden"
            )
        config_sha = self.source_config_sha256
        if (
            not isinstance(config_sha, str)
            or len(config_sha) != 64
            or any(character not in "0123456789abcdef" for character in config_sha)
        ):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_source_config_sha256_invalid"
            )


@dataclass(frozen=True)
class V8StagedEpisode:
    """Content-addressed result of staging one registry-ordered episode."""

    schedule_index: int
    episode_id: str
    seed: int
    topology_id: str
    communication_condition: str
    requested_target_class: str
    requested_transfer_resource_count: int
    hard_negative_candidate_resource_count: int
    online_features_relative_path: str
    online_features_sha256: str
    offline_labels_relative_path: str
    offline_labels_sha256: str
    frame_count: int


@dataclass(frozen=True)
class V8DatasetWriteResult:
    """Proof returned only after final strict-loader round-trip succeeds."""

    dataset_root: Path
    main_schedule_path: Path
    main_schedule: V8MainGenerationSchedule
    manifest: V8TrainDatasetManifest
    loaded_dataset: LoadedV8TrainDataset


class V8TrainDatasetWriter:
    """Incrementally stage and atomically publish one complete v8 TRAIN source."""

    def __init__(
        self,
        *,
        dataset_root: str | Path,
        main_schedule_path: str | Path,
        frozen_request: LoadedV8FrozenRequest,
        expected_source_metadata: V8CleanSourceMetadata,
        schedule_id: str,
        dataset_id: str,
    ) -> None:
        if not isinstance(frozen_request, LoadedV8FrozenRequest):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_loaded_frozen_request_required"
            )
        if not isinstance(expected_source_metadata, V8CleanSourceMetadata):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_clean_source_metadata_required"
            )
        self._validate_identifier(schedule_id, "schedule_id")
        self._validate_identifier(dataset_id, "dataset_id")

        root = Path(dataset_root).expanduser().resolve()
        schedule_path = Path(main_schedule_path).expanduser().resolve()
        if root == schedule_path or _is_relative_to(schedule_path, root):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_main_schedule_must_be_outside_dataset_root"
            )
        if root.exists():
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_dataset_root_already_exists"
            )
        if schedule_path.exists():
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_main_schedule_already_exists"
            )

        reloaded = load_v8_frozen_request(
            frozen_request.request_path,
            frozen_request.registry_path,
        )
        if reloaded != frozen_request:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_frozen_request_obsolete_or_mismatched"
            )

        root.parent.mkdir(parents=True, exist_ok=True)
        schedule_path.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{root.name}.v8-staging-",
                dir=root.parent,
            )
        ).resolve()
        (staging / "online").mkdir()
        (staging / "labels").mkdir()

        self._dataset_root = root
        self._main_schedule_path = schedule_path
        self._frozen_request = reloaded
        self._expected_source_metadata = expected_source_metadata
        self._schedule_id = schedule_id
        self._dataset_id = dataset_id
        self._staging_root: Path | None = staging
        self._schedule_entries: list[V8MainGenerationScheduleEntry] = []
        self._manifest_entries: list[V8EpisodeManifestEntry] = []
        self._staged_results: list[V8StagedEpisode] = []
        self._seen_episode_ids: set[str] = set()
        self._seen_seeds: set[int] = set()
        self._seen_frame_ids: set[str] = set()
        self._finalized = False
        self._aborted = False

    @classmethod
    def from_contract_files(
        cls,
        *,
        dataset_root: str | Path,
        main_schedule_path: str | Path,
        request_path: str | Path,
        registry_path: str | Path,
        expected_source_metadata: V8CleanSourceMetadata,
        schedule_id: str,
        dataset_id: str,
    ) -> "V8TrainDatasetWriter":
        """Load the frozen request strictly, then create an incremental writer."""

        frozen = load_v8_frozen_request(request_path, registry_path)
        return cls(
            dataset_root=dataset_root,
            main_schedule_path=main_schedule_path,
            frozen_request=frozen,
            expected_source_metadata=expected_source_metadata,
            schedule_id=schedule_id,
            dataset_id=dataset_id,
        )

    @property
    def staged_episode_count(self) -> int:
        return len(self._staged_results)

    @property
    def expected_episode_count(self) -> int:
        return len(self._frozen_request.schedule)

    @property
    def next_schedule_index(self) -> int:
        return len(self._staged_results)

    @property
    def staged_episodes(self) -> tuple[V8StagedEpisode, ...]:
        return tuple(self._staged_results)

    def stage_episode(
        self,
        *,
        schedule_index: int,
        episode_id: str,
        frames: Sequence[V8OnlineRegionResourceFrame],
        labels: Sequence[V8OfflineTransferLabel],
        source_metadata: V8CleanSourceMetadata,
    ) -> V8StagedEpisode:
        """Validate and stage exactly the next frozen registry episode."""

        staging = self._require_active()
        if type(schedule_index) is not int or schedule_index < 0:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_schedule_index_invalid"
            )
        expected_index = len(self._staged_results)
        if schedule_index != expected_index:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_schedule_index_out_of_order"
            )
        if schedule_index >= len(self._frozen_request.schedule):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_schedule_index_outside_frozen_registry"
            )
        if not isinstance(source_metadata, V8CleanSourceMetadata):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_clean_source_metadata_required"
            )
        if source_metadata != self._expected_source_metadata:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_source_metadata_obsolete_or_mismatched"
            )
        if not isinstance(episode_id, str) or not episode_id.strip():
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_episode_id_required"
            )
        if episode_id in self._seen_episode_ids:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_duplicate_episode_id"
            )

        canonical_frames = self._canonicalize_frames(frames)
        canonical_labels = self._canonicalize_labels(labels)
        if not canonical_frames or len(canonical_frames) != len(canonical_labels):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_frame_label_count_mismatch"
            )
        frame_ids = tuple(item.frame_id for item in canonical_frames)
        if len(set(frame_ids)) != len(frame_ids):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_duplicate_frame_id_within_episode"
            )
        if any(frame_id in self._seen_frame_ids for frame_id in frame_ids):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_duplicate_frame_id_across_episodes"
            )
        episode_seeds = {
            *(item.seed for item in canonical_frames),
            *(item.seed for item in canonical_labels),
        }
        if len(episode_seeds) == 1 and next(iter(episode_seeds)) in self._seen_seeds:
            raise RegionResourceV8DatasetWriterError("v8_writer_duplicate_seed")
        if any(item.episode_id != episode_id for item in canonical_frames) or any(
            item.episode_id != episode_id for item in canonical_labels
        ):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_explicit_episode_id_mismatch"
            )

        request_entry = self._frozen_request.schedule[schedule_index]
        online_relative = f"online/{schedule_index:03d}_{request_entry.seed}.jsonl"
        offline_relative = f"labels/{schedule_index:03d}_{request_entry.seed}.jsonl"
        online_path = staging / online_relative
        offline_path = staging / offline_relative
        if online_path.exists() or offline_path.exists():
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_episode_path_duplicate"
            )

        online_bytes = b"".join(
            canonical_v8_json_line(item.to_dict()) for item in canonical_frames
        )
        offline_bytes = b"".join(
            canonical_v8_json_line(item.to_dict()) for item in canonical_labels
        )
        online_temporary = _write_temporary_bytes(online_path.parent, online_bytes)
        offline_temporary = _write_temporary_bytes(offline_path.parent, offline_bytes)
        try:
            loaded = load_v8_episode_pair(
                online_temporary,
                offline_temporary,
                expected_online_sha256=sha256(online_bytes).hexdigest(),
                expected_offline_sha256=sha256(offline_bytes).hexdigest(),
                expected_frame_count=len(canonical_frames),
                schedule_entry=request_entry,
            )
            if loaded.episode_id != episode_id or loaded.seed != request_entry.seed:
                raise RegionResourceV8DatasetWriterError(
                    "v8_writer_episode_registry_identity_mismatch"
                )
            metadata = self._expected_source_metadata
            schedule_entry = V8MainGenerationScheduleEntry(
                schedule_index=schedule_index,
                episode_id=episode_id,
                **request_entry.to_registry_dict(),
                source_scenario_id=metadata.source_scenario_id,
                source_scenario_version=metadata.source_scenario_version,
                source_git_commit=metadata.source_git_commit,
                source_git_dirty=metadata.source_git_dirty,
                source_config_sha256=metadata.source_config_sha256,
                online_features_relative_path=online_relative,
                offline_labels_relative_path=offline_relative,
            )
            manifest_entry = V8EpisodeManifestEntry(
                schedule_index=schedule_index,
                episode_id=episode_id,
                seed=request_entry.seed,
                online_features_relative_path=online_relative,
                online_features_sha256=sha256(online_bytes).hexdigest(),
                offline_labels_relative_path=offline_relative,
                offline_labels_sha256=sha256(offline_bytes).hexdigest(),
                frame_count=len(canonical_frames),
                first_measurement_timestamp=(
                    canonical_frames[0].measurement_timestamp
                ),
                last_arrival_timestamp=canonical_frames[-1].arrival_timestamp,
            )
            os.replace(online_temporary, online_path)
            os.replace(offline_temporary, offline_path)
        except Exception:
            online_temporary.unlink(missing_ok=True)
            offline_temporary.unlink(missing_ok=True)
            online_path.unlink(missing_ok=True)
            offline_path.unlink(missing_ok=True)
            raise

        staged = V8StagedEpisode(
            schedule_index=schedule_index,
            episode_id=episode_id,
            seed=request_entry.seed,
            topology_id=request_entry.topology_id,
            communication_condition=request_entry.communication_condition,
            requested_target_class=request_entry.requested_target_class.value,
            requested_transfer_resource_count=(
                request_entry.requested_transfer_resource_count
            ),
            hard_negative_candidate_resource_count=(
                request_entry.hard_negative_candidate_resource_count
            ),
            online_features_relative_path=online_relative,
            online_features_sha256=manifest_entry.online_features_sha256,
            offline_labels_relative_path=offline_relative,
            offline_labels_sha256=manifest_entry.offline_labels_sha256,
            frame_count=len(canonical_frames),
        )
        self._schedule_entries.append(schedule_entry)
        self._manifest_entries.append(manifest_entry)
        self._staged_results.append(staged)
        self._seen_episode_ids.add(episode_id)
        self._seen_seeds.add(request_entry.seed)
        self._seen_frame_ids.update(frame_ids)
        return staged

    def finalize(self) -> V8DatasetWriteResult:
        """Publish only a complete source that passes strict full-dataset loading."""

        staging = self._require_active()
        expected_count = len(self._frozen_request.schedule)
        if len(self._staged_results) != expected_count:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_missing_frozen_registry_episodes:"
                f"staged={len(self._staged_results)}:expected={expected_count}"
            )
        if tuple(item.schedule_index for item in self._staged_results) != tuple(
            range(expected_count)
        ):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_staged_schedule_not_contiguous"
            )
        if tuple(item.seed for item in self._staged_results) != tuple(
            item.seed for item in self._frozen_request.schedule
        ):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_staged_seed_inventory_mismatch"
            )
        if self._dataset_root.exists() or self._main_schedule_path.exists():
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_publish_destination_became_occupied"
            )

        schedule = self._build_main_schedule()
        manifest = self._build_manifest(schedule)
        manifest_path = staging / "manifest.json"
        _write_atomic_bytes(
            manifest_path,
            canonical_v8_json_line(manifest.to_dict()),
        )
        schedule_temporary = _write_temporary_bytes(
            self._main_schedule_path.parent,
            canonical_v8_json_line(schedule.to_dict()),
        )
        published_dataset = False
        published_schedule = False
        try:
            preflight = load_v8_development_train_dataset(
                staging,
                self._frozen_request.request_path,
                self._frozen_request.registry_path,
                schedule_temporary,
            )
            if preflight.main_schedule != schedule or preflight.manifest != manifest:
                raise RegionResourceV8DatasetWriterError(
                    "v8_writer_prepublication_round_trip_mismatch"
                )
            if self._dataset_root.exists() or self._main_schedule_path.exists():
                raise RegionResourceV8DatasetWriterError(
                    "v8_writer_publish_destination_became_occupied"
                )
            os.replace(staging, self._dataset_root)
            self._staging_root = None
            published_dataset = True
            try:
                os.replace(schedule_temporary, self._main_schedule_path)
                published_schedule = True
            except Exception:
                shutil.rmtree(self._dataset_root, ignore_errors=True)
                published_dataset = False
                raise
            loaded = load_v8_development_train_dataset(
                self._dataset_root,
                self._frozen_request.request_path,
                self._frozen_request.registry_path,
                self._main_schedule_path,
            )
        except Exception:
            schedule_temporary.unlink(missing_ok=True)
            if published_schedule:
                self._main_schedule_path.unlink(missing_ok=True)
            if published_dataset:
                shutil.rmtree(self._dataset_root, ignore_errors=True)
            if self._staging_root is None:
                self._aborted = True
            raise

        self._finalized = True
        return V8DatasetWriteResult(
            dataset_root=self._dataset_root,
            main_schedule_path=self._main_schedule_path,
            main_schedule=schedule,
            manifest=manifest,
            loaded_dataset=loaded,
        )

    def abort(self) -> None:
        """Remove only this writer's unpublished hidden staging directory."""

        if self._finalized or self._aborted:
            return
        if self._staging_root is not None:
            shutil.rmtree(self._staging_root, ignore_errors=True)
            self._staging_root = None
        self._aborted = True

    def __enter__(self) -> "V8TrainDatasetWriter":
        self._require_active()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self._finalized:
            self.abort()

    def _build_main_schedule(self) -> V8MainGenerationSchedule:
        permissions = V8NoAuthorityPermissions()
        content = {
            "schema": REGION_RESOURCE_V8_MAIN_SCHEDULE_SCHEMA,
            "schedule_id": self._schedule_id,
            "request_id": self._frozen_request.request_id,
            "request_content_sha256": self._frozen_request.request_content_sha256,
            "registry_id": self._frozen_request.registry_id,
            "registry_content_sha256": self._frozen_request.registry_content_sha256,
            "registry_schedule_content_sha256": (
                self._frozen_request.registry_schedule_content_sha256
            ),
            "status": V8_MAIN_SCHEDULE_STATUS,
            "split": "train",
            "entry_count": len(self._schedule_entries),
            "entries": [item.to_dict() for item in self._schedule_entries],
            "permissions": permissions.to_dict(),
        }
        return V8MainGenerationSchedule(
            schedule_id=self._schedule_id,
            request_id=self._frozen_request.request_id,
            request_content_sha256=self._frozen_request.request_content_sha256,
            registry_id=self._frozen_request.registry_id,
            registry_content_sha256=self._frozen_request.registry_content_sha256,
            registry_schedule_content_sha256=(
                self._frozen_request.registry_schedule_content_sha256
            ),
            status=V8_MAIN_SCHEDULE_STATUS,
            split="train",
            entry_count=len(self._schedule_entries),
            entries=tuple(self._schedule_entries),
            permissions=permissions,
            content_sha256=canonical_v8_sha256(content),
        )

    def _build_manifest(
        self,
        schedule: V8MainGenerationSchedule,
    ) -> V8TrainDatasetManifest:
        permissions = V8NoAuthorityPermissions()
        episode_inventory = [item.to_dict() for item in self._manifest_entries]
        inventory_sha = canonical_v8_sha256(episode_inventory)
        content = {
            "schema": REGION_RESOURCE_V8_DATASET_MANIFEST_SCHEMA,
            "dataset_id": self._dataset_id,
            "request_id": self._frozen_request.request_id,
            "request_content_sha256": self._frozen_request.request_content_sha256,
            "registry_id": self._frozen_request.registry_id,
            "registry_content_sha256": self._frozen_request.registry_content_sha256,
            "registry_schedule_content_sha256": (
                self._frozen_request.registry_schedule_content_sha256
            ),
            "main_schedule_id": schedule.schedule_id,
            "main_schedule_content_sha256": schedule.content_sha256,
            "status": V8_DATASET_STATUS,
            "split": "train",
            "train_only": True,
            "online_labels_separate": True,
            "episode_count": len(self._manifest_entries),
            "frame_count": sum(item.frame_count for item in self._manifest_entries),
            "online_feature_file_count": len(self._manifest_entries),
            "offline_label_file_count": len(self._manifest_entries),
            "validation_seed_allocation": [],
            "test_seed_allocation": [],
            "training_count": 0,
            "checkpoint_count": 0,
            "model_registration_count": 0,
            "runtime_connection_count": 0,
            "episodes": episode_inventory,
            "episode_inventory_sha256": inventory_sha,
            "permissions": permissions.to_dict(),
        }
        return V8TrainDatasetManifest(
            dataset_id=self._dataset_id,
            request_id=self._frozen_request.request_id,
            request_content_sha256=self._frozen_request.request_content_sha256,
            registry_id=self._frozen_request.registry_id,
            registry_content_sha256=self._frozen_request.registry_content_sha256,
            registry_schedule_content_sha256=(
                self._frozen_request.registry_schedule_content_sha256
            ),
            main_schedule_id=schedule.schedule_id,
            main_schedule_content_sha256=schedule.content_sha256,
            status=V8_DATASET_STATUS,
            split="train",
            train_only=True,
            online_labels_separate=True,
            episode_count=len(self._manifest_entries),
            frame_count=sum(item.frame_count for item in self._manifest_entries),
            online_feature_file_count=len(self._manifest_entries),
            offline_label_file_count=len(self._manifest_entries),
            validation_seed_allocation=(),
            test_seed_allocation=(),
            training_count=0,
            checkpoint_count=0,
            model_registration_count=0,
            runtime_connection_count=0,
            episodes=tuple(self._manifest_entries),
            episode_inventory_sha256=inventory_sha,
            permissions=permissions,
            content_sha256=canonical_v8_sha256(content),
        )

    @staticmethod
    def _canonicalize_frames(
        frames: Sequence[V8OnlineRegionResourceFrame],
    ) -> tuple[V8OnlineRegionResourceFrame, ...]:
        if not isinstance(frames, (list, tuple)):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_frame_sequence_required"
            )
        result: list[V8OnlineRegionResourceFrame] = []
        for item in frames:
            if not isinstance(item, V8OnlineRegionResourceFrame):
                raise RegionResourceV8DatasetWriterError(
                    "v8_writer_online_frame_dto_required"
                )
            try:
                result.append(
                    V8OnlineRegionResourceFrame.from_dict(item.to_dict())
                )
            except RegionResourceV8ValidationError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise RegionResourceV8ValidationError(
                    f"v8_writer_online_frame_invalid:{type(exc).__name__}:{exc}"
                ) from exc
        return tuple(result)

    @staticmethod
    def _canonicalize_labels(
        labels: Sequence[V8OfflineTransferLabel],
    ) -> tuple[V8OfflineTransferLabel, ...]:
        if not isinstance(labels, (list, tuple)):
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_label_sequence_required"
            )
        result: list[V8OfflineTransferLabel] = []
        for item in labels:
            if not isinstance(item, V8OfflineTransferLabel):
                raise RegionResourceV8DatasetWriterError(
                    "v8_writer_offline_label_dto_required"
                )
            try:
                result.append(V8OfflineTransferLabel.from_dict(item.to_dict()))
            except RegionResourceV8ValidationError:
                raise
            except (KeyError, TypeError, ValueError) as exc:
                raise RegionResourceV8ValidationError(
                    f"v8_writer_offline_label_invalid:{type(exc).__name__}:{exc}"
                ) from exc
        return tuple(result)

    def _require_active(self) -> Path:
        if self._finalized:
            raise RegionResourceV8DatasetWriterError(
                "v8_writer_already_finalized"
            )
        if self._aborted or self._staging_root is None:
            raise RegionResourceV8DatasetWriterError("v8_writer_aborted")
        return self._staging_root

    @staticmethod
    def _validate_identifier(value: str, name: str) -> None:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
        ):
            raise RegionResourceV8DatasetWriterError(
                f"v8_writer_identifier_invalid:{name}"
            )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_temporary_bytes(parent: Path, value: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".v8-write-", dir=parent)
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _write_atomic_bytes(path: Path, value: bytes) -> None:
    if path.exists():
        raise RegionResourceV8DatasetWriterError(
            "v8_writer_atomic_destination_already_exists"
        )
    temporary = _write_temporary_bytes(path.parent, value)
    try:
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


__all__ = [
    "RegionResourceV8DatasetWriterError",
    "V8CleanSourceMetadata",
    "V8DatasetWriteResult",
    "V8StagedEpisode",
    "V8TrainDatasetWriter",
]
