"""Export truth-free runtime frames for the unregistered D4 v4 shadow path.

The exporter is owned by the integrated simulation layer. It does not train a
model or grant D4 authority. It rebuilds same-key deterministic R0 labels and
adds only bounded one-resource transfer examples that pass the existing D4
projection and v4 intervention invariants.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
    DeterministicResourceProjector,
    RecommendationSource,
    RegionResourceProjectionConfig,
    RegionResourceRecommendation,
    RegionTransferSuggestion,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
    split_scenario_seed_groups,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_dataset import (
    RegionLearningFrame,
    RegionLearningSplit,
    RegionLearningTarget,
    RegionLearningTargetKind,
    finalize_region_learning_dataset,
    load_region_learning_dataset,
    load_region_learning_dataset_splits,
    stage_region_learning_episode,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v4_shadow_candidate import (
    REGION_RESOURCE_V4_INTERVENTION_GATE,
    RegionResourceV4BuildConfig,
    RegionResourceV4ExternalDatasetEvidence,
    _audit_external_dataset_governance,
    evaluate_v4_intervention_invariants,
)


D4_V4_EXTERNAL_EXPORT_SCHEMA = "scalable3d-d4-v4-external-dataset-export-v1"
D4_V4_EXTERNAL_DERIVATION_FILENAME = "source_derivation_manifest.json"
D4_V4_EXTERNAL_EVIDENCE_FILENAME = "external_dataset_evidence.json"
D4_V4_EXTERNAL_SUMMARY_FILENAME = "export_summary.json"

_PROJECTION = RegionResourceProjectionConfig(
    minimum_reserve_ratio=0.10,
    minimum_reserve_resources=1,
    advisory_ttl_s=1.5,
)
_RULE_CONFIG = RuleRegionResourcePolicyConfig(
    projection=_PROJECTION,
    high_threat_weight=2.0,
    uncertainty_weight=0.5,
    transfer_pressure_margin=0.05,
)


class D4V4ExternalDatasetExportError(RuntimeError):
    """Stable export failure for an inadmissible external dataset."""


@dataclass(frozen=True)
class D4V4ExternalDatasetExportConfig:
    """Reproducible split and positive/negative curriculum contract."""

    split_seed: int = 9
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    minimum_unique_seeds: int = 16
    minimum_unseen_seeds: int = 8
    minimum_train_seeds: int = 8
    minimum_validation_seeds: int = 4
    minimum_test_seeds: int = 4
    train_positive_frame_count: int = 1
    validation_positive_frame_count: int = 1
    source_kind: str = "main_runtime_frames"
    created_at_utc: str = "2026-07-29T00:00:00Z"
    schema: str = D4_V4_EXTERNAL_EXPORT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != D4_V4_EXTERNAL_EXPORT_SCHEMA:
            raise ValueError("unsupported D4 v4 external export schema")
        for name in (
            "split_seed",
            "minimum_unique_seeds",
            "minimum_unseen_seeds",
            "minimum_train_seeds",
            "minimum_validation_seeds",
            "minimum_test_seeds",
            "train_positive_frame_count",
            "validation_positive_frame_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not 0.0 < self.train_fraction < 1.0:
            raise ValueError("train_fraction must be in (0, 1)")
        if not 0.0 < self.validation_fraction < 1.0:
            raise ValueError("validation_fraction must be in (0, 1)")
        if self.train_fraction + self.validation_fraction >= 1.0:
            raise ValueError("train and validation fractions must leave a test split")
        if not self.created_at_utc:
            raise ValueError("created_at_utc must not be empty")
        if self.source_kind not in {
            "main_runtime_frames",
            "external_region_learning_dataset",
        }:
            raise ValueError("unsupported D4 v4 external source kind")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def export_d4_v4_external_runtime_dataset(
    source_dataset_dir: str | Path | Sequence[str | Path],
    output_dir: str | Path,
    *,
    repository_root: str | Path,
    config: D4V4ExternalDatasetExportConfig | None = None,
) -> dict[str, Any]:
    """Create a content-addressed external dataset and provenance evidence.

    The source dataset may contain any number of regions, targets, or
    resources. Positive examples are selected from train and validation only
    after the requested seed split is determined. Test episodes are copied and
    sealed in the output dataset, but the D4 v4 loader remains responsible for
    not reading their payloads during model construction.
    """

    resolved = config or D4V4ExternalDatasetExportConfig()
    source_roots = _resolve_source_roots(source_dataset_dir)
    destination = Path(output_dir).resolve()
    repository = Path(repository_root).resolve()
    if any(path.is_symlink() for path in source_roots) or destination.is_symlink():
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_dataset_symlink_forbidden"
        )
    if destination.exists():
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_output_already_exists"
        )

    sources = tuple(
        load_region_learning_dataset(source_root)
        for source_root in source_roots
    )
    if any(
        source.manifest.availability.dirty_episode_count
        for source in sources
    ):
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_source_contains_dirty_episode"
        )
    repository_identity = _clean_repository_identity(repository)
    episodes = tuple(
        episode
        for source in sources
        for episode in source.episode_records
    )
    split = split_scenario_seed_groups(
        [episode.source for episode in episodes],
        train_fraction=resolved.train_fraction,
        validation_fraction=resolved.validation_fraction,
        split_seed=resolved.split_seed,
        minimum_unique_seeds=resolved.minimum_unique_seeds,
        minimum_unseen_seeds=resolved.minimum_unseen_seeds,
    )
    seed_split = {
        **{int(seed): RegionLearningSplit.TRAIN for seed in split.train_seeds},
        **{
            int(seed): RegionLearningSplit.VALIDATION
            for seed in split.validation_seeds
        },
        **{int(seed): RegionLearningSplit.TEST for seed in split.test_seeds},
    }
    _require_split_inventory(split, resolved)

    projector = DeterministicResourceProjector(_PROJECTION)
    rule_policy = RuleRegionResourcePolicy(
        _RULE_CONFIG,
        projector=projector,
    )
    selected = _select_positive_frames(
        episodes,
        seed_split=seed_split,
        positive_counts={
            RegionLearningSplit.TRAIN: resolved.train_positive_frame_count,
            RegionLearningSplit.VALIDATION: (
                resolved.validation_positive_frame_count
            ),
        },
        projector=projector,
        rule_policy=rule_policy,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    try:
        staging = temporary_root / "staging"
        dataset_root = temporary_root / "dataset"
        positive_records: list[dict[str, Any]] = []
        for episode in episodes:
            frames: list[RegionLearningFrame] = []
            for frame in episode.frames:
                key = (episode.source.identity_sha256, int(frame.frame_index))
                r0 = rule_policy.recommend(frame.snapshot)
                target = r0
                if key in selected:
                    target = selected[key]
                    positive_records.append(
                        {
                            "source_identity_sha256": (
                                episode.source.identity_sha256
                            ),
                            "scenario_id": episode.source.scenario_id,
                            "scenario_version": episode.source.scenario_version,
                            "seed": int(episode.source.seed),
                            "frame_index": int(frame.frame_index),
                            "snapshot_id": frame.snapshot.snapshot_id,
                            "split": seed_split[int(episode.source.seed)].value,
                            "transfer_count": len(target.transfers),
                        }
                    )
                frames.append(
                    replace(
                        frame,
                        target=RegionLearningTarget.available(
                            RegionLearningTargetKind.RULE,
                            target,
                        ),
                        recommendation=target,
                    )
                )
            stage_region_learning_episode(staging, episode.source, frames)

        manifest = finalize_region_learning_dataset(
            staging,
            dataset_root,
            created_at_utc=resolved.created_at_utc,
            split_seed=resolved.split_seed,
            minimum_unique_seeds=resolved.minimum_unique_seeds,
            minimum_unseen_seeds=resolved.minimum_unseen_seeds,
            train_fraction=resolved.train_fraction,
            validation_fraction=resolved.validation_fraction,
        )
        shutil.rmtree(staging)

        loaded = load_region_learning_dataset_splits(
            dataset_root,
            splits=(
                RegionLearningSplit.TRAIN,
                RegionLearningSplit.VALIDATION,
            ),
        )
        governance = _audit_external_dataset_governance(
            loaded,
            config=RegionResourceV4BuildConfig(
                minimum_train_seeds=resolved.minimum_train_seeds,
                minimum_validation_seeds=resolved.minimum_validation_seeds,
                minimum_test_seeds=resolved.minimum_test_seeds,
            ),
        )
        derivation_content = {
            "schema": D4_V4_EXTERNAL_EXPORT_SCHEMA,
            "created_at_utc": resolved.created_at_utc,
            "purpose": "d4_v4_unregistered_shadow_candidate_external_input",
            "source": {
                "dataset_count": len(sources),
                "datasets": [
                    {
                        "dataset_id": item.manifest.dataset_id,
                        "dataset_sha256": item.manifest.dataset_sha256,
                        "split_sha256": item.manifest.split.split_sha256,
                        "episode_count": (
                            item.manifest.availability.episode_count
                        ),
                        "frame_count": item.manifest.availability.frame_count,
                        "dirty_episode_count": (
                            item.manifest.availability.dirty_episode_count
                        ),
                    }
                    for item in sources
                ],
                "episode_count": sum(
                    item.manifest.availability.episode_count
                    for item in sources
                ),
                "frame_count": sum(
                    item.manifest.availability.frame_count
                    for item in sources
                ),
                "dirty_episode_count": 0,
            },
            "output": {
                "dataset_id": manifest.dataset_id,
                "dataset_sha256": manifest.dataset_sha256,
                "split_sha256": manifest.split.split_sha256,
                "episode_count": manifest.availability.episode_count,
                "frame_count": manifest.availability.frame_count,
            },
            "repository": repository_identity,
            "config": resolved.to_dict(),
            "positive_records": sorted(
                positive_records,
                key=lambda item: (
                    item["split"],
                    item["seed"],
                    item["frame_index"],
                ),
            ),
            "governance": governance,
            "generation": {
                "same_key_r0_negative_labels": True,
                "bounded_one_resource_transfer_positive_labels": True,
                "deterministic_projection_required": True,
                "v4_intervention_invariants_required": True,
                "generated_by_v4_builder": False,
                "truth_identifier_use_count": 0,
                "future_outcome_use_count": 0,
                "production_permission_available": False,
            },
        }
        derivation = {
            **derivation_content,
            "content_sha256": _canonical_sha256(derivation_content),
        }
        derivation_path = (
            temporary_root / D4_V4_EXTERNAL_DERIVATION_FILENAME
        )
        _write_json(derivation_path, derivation)
        evidence = RegionResourceV4ExternalDatasetEvidence(
            dataset_sha256=manifest.dataset_sha256,
            dataset_split_sha256=manifest.split.split_sha256,
            source_artifact_sha256=_sha256_file(derivation_path),
            source_kind=resolved.source_kind,
            truth_free_online_features=True,
            generated_by_v4_builder=False,
            source_worktree_dirty=False,
        )
        evidence_path = temporary_root / D4_V4_EXTERNAL_EVIDENCE_FILENAME
        _write_json(evidence_path, evidence.to_dict())
        summary = {
            "schema": D4_V4_EXTERNAL_EXPORT_SCHEMA,
            "dataset_dir": "dataset",
            "derivation_manifest": D4_V4_EXTERNAL_DERIVATION_FILENAME,
            "external_dataset_evidence": D4_V4_EXTERNAL_EVIDENCE_FILENAME,
            "dataset_sha256": manifest.dataset_sha256,
            "dataset_split_sha256": manifest.split.split_sha256,
            "source_artifact_sha256": evidence.source_artifact_sha256,
            "external_dataset_evidence_sha256": evidence.content_sha256,
            "positive_record_count": len(positive_records),
            "positive_record_count_by_split": {
                split_name: sum(
                    record["split"] == split_name
                    for record in positive_records
                )
                for split_name in ("train", "validation")
            },
            "test_payload_read_by_v4_builder": False,
            "truth_identifier_use_count": 0,
            "production_permission_available": False,
        }
        summary["content_sha256"] = _canonical_sha256(summary)
        _write_json(
            temporary_root / D4_V4_EXTERNAL_SUMMARY_FILENAME,
            summary,
        )
        temporary_root.replace(destination)
        return summary
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


def _select_positive_frames(
    episodes: Sequence[Any],
    *,
    seed_split: Mapping[int, RegionLearningSplit],
    positive_counts: Mapping[RegionLearningSplit, int],
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> dict[tuple[str, int], RegionResourceRecommendation]:
    selected: dict[tuple[str, int], RegionResourceRecommendation] = {}
    count_by_split = {
        RegionLearningSplit.TRAIN: 0,
        RegionLearningSplit.VALIDATION: 0,
    }
    for episode in sorted(
        episodes,
        key=lambda item: (
            int(item.source.seed),
            item.source.scenario_id,
            item.source.episode_id,
        ),
    ):
        split = seed_split[int(episode.source.seed)]
        if (
            split not in count_by_split
            or count_by_split[split] >= positive_counts[split]
        ):
            continue
        for frame in episode.frames:
            candidate = _safe_transfer_alternative(
                frame.snapshot,
                projector=projector,
                rule_policy=rule_policy,
            )
            if candidate is None:
                continue
            selected[
                (episode.source.identity_sha256, int(frame.frame_index))
            ] = candidate
            count_by_split[split] += 1
            break
    missing = [
        split.value
        for split, count in count_by_split.items()
        if count < positive_counts[split]
    ]
    if missing:
        raise D4V4ExternalDatasetExportError(
            "d4_v4_safe_positive_unavailable:" + ",".join(missing)
        )
    return selected


def _resolve_source_roots(
    source_dataset_dir: str | Path | Sequence[str | Path],
) -> tuple[Path, ...]:
    if isinstance(source_dataset_dir, (str, Path)):
        values = (source_dataset_dir,)
    else:
        values = tuple(source_dataset_dir)
    if not values:
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_source_dataset_missing"
        )
    roots = tuple(Path(value).resolve() for value in values)
    if len(set(roots)) != len(roots):
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_source_dataset_duplicate"
        )
    return roots


def _safe_transfer_alternative(
    snapshot: Any,
    *,
    projector: DeterministicResourceProjector,
    rule_policy: RuleRegionResourcePolicy,
) -> RegionResourceRecommendation | None:
    r0 = rule_policy.recommend(snapshot)
    raw_actions = tuple(
        replace(
            action,
            resource_quota_delta=0,
            reasons=("external_safe_transfer_curriculum",),
        )
        for action in r0.actions
    )
    for edge in sorted(snapshot.edges, key=lambda item: item.edge_id):
        directions = [(edge.source_region_id, edge.target_region_id)]
        if edge.bidirectional:
            directions.append(
                (edge.target_region_id, edge.source_region_id)
            )
        for source_region_id, target_region_id in directions:
            transfer = RegionTransferSuggestion(
                source_region_id=source_region_id,
                target_region_id=target_region_id,
                resource_count=1,
                edge_id=edge.edge_id,
                expected_transfer_time_s=edge.transfer_time_s,
                reasons=("external_safe_transfer_curriculum",),
            )
            proposal = RegionResourceRecommendation(
                snapshot_id=snapshot.snapshot_id,
                scenario_id=snapshot.scenario_id,
                scenario_version=snapshot.scenario_version,
                seed=snapshot.seed,
                authority_digest=snapshot.authority_digest,
                created_at_s=snapshot.timestamp_s,
                policy_name="scalable3d-external-safe-transfer-curriculum",
                policy_version="v1",
                source=RecommendationSource.RULE,
                confidence=1.0,
                actions=raw_actions,
                transfers=(transfer,),
                projected=False,
                planning_authority_digest=snapshot.planning_authority_digest,
            )
            candidate = projector.project(snapshot, proposal)
            valid, _ = evaluate_v4_intervention_invariants(
                snapshot,
                candidate,
                r0,
                gate=REGION_RESOURCE_V4_INTERVENTION_GATE,
                projector=projector,
                formal_decision=None,
            )
            if valid:
                return candidate
    return None


def _require_split_inventory(
    split: Any,
    config: D4V4ExternalDatasetExportConfig,
) -> None:
    counts = {
        "train": len(split.train_seeds),
        "validation": len(split.validation_seeds),
        "test": len(split.test_seeds),
    }
    required = {
        "train": config.minimum_train_seeds,
        "validation": config.minimum_validation_seeds,
        "test": config.minimum_test_seeds,
    }
    missing = [
        name for name in required if counts[name] < required[name]
    ]
    if missing:
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_split_inventory_insufficient:"
            + ",".join(missing)
        )


def _clean_repository_identity(repository_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ("git", "-C", str(repository_root), "rev-parse", "HEAD"),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            (
                "git",
                "-C",
                str(repository_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise D4V4ExternalDatasetExportError(
            f"d4_v4_external_source_git_unavailable:{type(exc).__name__}"
        ) from exc
    if status:
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_source_worktree_dirty"
        )
    implementation = (
        repository_root
        / "research_modules/scalable_3d_simulation/d4_v4_external_dataset.py"
    )
    if not implementation.is_file():
        raise D4V4ExternalDatasetExportError(
            "d4_v4_external_exporter_source_missing"
        )
    return {
        "git_commit": commit,
        "source_worktree_dirty": False,
        "exporter_sha256": _sha256_file(implementation),
    }


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


__all__ = [
    "D4V4ExternalDatasetExportConfig",
    "D4V4ExternalDatasetExportError",
    "export_d4_v4_external_runtime_dataset",
]
