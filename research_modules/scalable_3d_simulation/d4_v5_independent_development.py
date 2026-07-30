"""Generate source-independent D4 development frames from the 3D runtime.

This main-owned path uses seeds and scenario versions that are disjoint from
the D4 v4 training corpus and the formal holdout. It only exports truth-free
D4 regional snapshots and rule targets. Model fitting, candidate registration,
and runtime authority are outside this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Mapping, Sequence

from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .models import ScenarioConfig
from .module_stack import IntegratedStackConfig
from .orchestrator import run_episode
from .scenarios import AVAILABLE_SCENARIOS, make_curriculum_scenario
from .world import REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION


D4_V5_INDEPENDENT_DEVELOPMENT_SCHEMA = (
    "scalable3d-d4-v5-independent-development-source-v1"
)
DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"
DEFAULT_SEED_REGISTRY = (
    Path(__file__).with_name("configs")
    / "d4_v5_independent_development_seed_registry_v1.json"
)
DEFAULT_SEEDS = tuple(range(3000, 3040))
DEFAULT_SCENARIO_FAMILIES = (
    "nominal",
    "dense_crossing",
    "evasive_multilevel",
    "delayed_noisy",
)

_BASE_REGION_PATTERNS = (
    (
        (2, 4, 2, 3, 2, 3, 2, 2),
        (4, 1, 2, 3, 2, 3, 2, 3),
    ),
    (
        (3, 2, 4, 2, 3, 2, 2, 2),
        (2, 4, 1, 3, 2, 3, 3, 2),
    ),
    (
        (4, 2, 2, 3, 2, 2, 3, 2),
        (1, 3, 4, 2, 3, 2, 2, 3),
    ),
    (
        (2, 3, 2, 4, 2, 3, 2, 2),
        (3, 2, 3, 1, 4, 2, 2, 3),
    ),
)


class D4V5IndependentDevelopmentError(RuntimeError):
    """Stable failure for invalid or contaminated development generation."""


@dataclass(frozen=True)
class D4V5IndependentDevelopmentOptions:
    """Frozen source-generation contract for one development batch."""

    output_dir: Path
    config_path: Path = DEFAULT_CONFIG
    seed_registry_path: Path = DEFAULT_SEED_REGISTRY
    seeds: tuple[int, ...] = DEFAULT_SEEDS
    scenario_families: tuple[str, ...] = DEFAULT_SCENARIO_FAMILIES
    target_count: int = 20
    resource_count: int = 20
    recon_count: int = 2
    region_count: int = 8
    duration_s: float = 1.6
    allow_dirty: bool = False

    def __post_init__(self) -> None:
        for name in ("output_dir", "config_path", "seed_registry_path"):
            object.__setattr__(self, name, Path(getattr(self, name)))
        seeds = tuple(int(seed) for seed in self.seeds)
        if len(seeds) < 8 or len(set(seeds)) != len(seeds):
            raise ValueError(
                "independent development requires at least eight unique seeds"
            )
        if any(seed < 0 for seed in seeds):
            raise ValueError("seeds must be non-negative")
        object.__setattr__(self, "seeds", seeds)
        families = tuple(
            str(value).strip().lower() for value in self.scenario_families
        )
        if not families or len(set(families)) != len(families):
            raise ValueError("scenario families must be non-empty and unique")
        unsupported = set(families) - set(AVAILABLE_SCENARIOS)
        if unsupported:
            raise ValueError(
                f"unsupported scenario families: {sorted(unsupported)}"
            )
        object.__setattr__(self, "scenario_families", families)
        for name in (
            "target_count",
            "resource_count",
            "recon_count",
            "region_count",
        ):
            value = int(getattr(self, name))
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.target_count != 20 or self.resource_count != 20:
            raise ValueError(
                "v1 regional perturbation patterns require 20 targets and "
                "20 resources"
            )
        if self.region_count != 8:
            raise ValueError(
                "v1 regional perturbation patterns require eight regions"
            )
        if not math.isfinite(float(self.duration_s)) or self.duration_s <= 0.0:
            raise ValueError("duration_s must be finite and positive")


def run_d4_v5_independent_development(
    options: D4V5IndependentDevelopmentOptions,
) -> dict[str, Path]:
    """Run authentic episodes and freeze only their D4 learning records."""

    repository_root = Path(__file__).resolve().parents[2]
    git_commit, repository_dirty = _repository_state(repository_root)
    if repository_dirty and not options.allow_dirty:
        raise D4V5IndependentDevelopmentError(
            "independent development generation requires a clean repository"
        )
    registry = _load_and_validate_seed_registry(
        options.seed_registry_path,
        seeds=options.seeds,
    )
    output = options.output_dir.expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)

    base = ScenarioConfig.from_dict(
        json.loads(options.config_path.read_text(encoding="utf-8"))
    )
    plan = {
        "schema_version": D4_V5_INDEPENDENT_DEVELOPMENT_SCHEMA,
        "created_at_utc": _utc_now(),
        "purpose": "d4_v5_source_independent_development_evaluation",
        "source": {
            "git_commit": git_commit,
            "repository_dirty": repository_dirty,
            "config_path": str(options.config_path.resolve()),
            "config_sha256": _sha256_file(options.config_path),
            "seed_registry_path": str(options.seed_registry_path.resolve()),
            "seed_registry_sha256": _sha256_file(
                options.seed_registry_path
            ),
        },
        "options": {
            **asdict(options),
            "output_dir": str(options.output_dir),
            "config_path": str(options.config_path),
            "seed_registry_path": str(options.seed_registry_path),
            "seeds": list(options.seeds),
            "scenario_families": list(options.scenario_families),
        },
        "seed_classes": registry,
        "online_truth_policy": "forbidden",
        "learning_target_policy": (
            "same_snapshot_deterministic_rule_recomputed_offline"
        ),
        "runtime_recommendation_policy": (
            "preserved_as_non_target_audit_evidence"
        ),
        "model_fit_allowed": False,
        "candidate_registration_allowed": False,
        "production_permission_available": False,
    }
    plan_path = output / "generation_plan.json"
    _write_json(plan_path, plan)

    learning_root = output / "learning_dataset"
    staging_root = learning_root / "_staging" / "d4_region_episodes"
    progress_path = output / "episode_progress.jsonl"
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for sequence, seed in enumerate(options.seeds):
        family = options.scenario_families[
            sequence % len(options.scenario_families)
        ]
        config = _build_development_config(
            base,
            options=options,
            seed=seed,
            scenario_family=family,
        )
        resolved = resolve_learning_runtime(
            config,
            LearningRuntimeOptions(d4_mode="shadow"),
            stack_config=IntegratedStackConfig(
                capture_learning_artifacts=True,
                d5_active_vision_enabled=False,
            ),
        )
        episode_started = time.perf_counter()
        result = run_episode(resolved.config, module_stack=resolved.stack)
        episode_wall_s = time.perf_counter() - episode_started
        runtime_frames = resolved.stack.learning_artifacts().d4_region_frames
        source, learning_frames = _build_offline_rule_frames(
            config=result.config,
            manifest=result.manifest,
            runtime_frames=runtime_frames,
        )
        frame_audit = _audit_frames(
            runtime_frames,
            learning_frames=learning_frames,
            expected_region_count=options.region_count,
        )
        if result.summary["finite_state"] is not True:
            raise D4V5IndependentDevelopmentError(
                f"non-finite episode state for seed {seed}"
            )
        if int(result.summary["online_truth_use_count"]) != 0:
            raise D4V5IndependentDevelopmentError(
                f"online truth use detected for seed {seed}"
            )
        if not options.allow_dirty and result.manifest.repository_dirty:
            raise D4V5IndependentDevelopmentError(
                f"episode source became dirty for seed {seed}"
            )
        if frame_audit["safe_rule_target_frame_count"] != frame_audit["frame_count"]:
            raise D4V5IndependentDevelopmentError(
                f"D4 rule target unavailable for seed {seed}"
            )
        from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
            stage_region_learning_episode,
        )

        staged = stage_region_learning_episode(
            staging_root,
            source,
            learning_frames,
        )
        target_counts, resource_counts = _regional_pattern(seed)
        row = {
            "sequence": sequence,
            "seed": seed,
            "scenario_family": family,
            "episode_id": result.manifest.episode_id,
            "scenario_version": result.config.scenario_version,
            "config_sha256": result.manifest.config_sha256,
            "target_counts_by_region": list(target_counts),
            "resource_counts_by_region": list(resource_counts),
            "finite_state": True,
            "online_truth_use_count": 0,
            "repository_dirty": bool(result.manifest.repository_dirty),
            "episode_wall_s": episode_wall_s,
            "staged_episode_sha256": staged.episode_sha256,
            "staged_frame_count": staged.frame_count,
            **frame_audit,
        }
        _append_jsonl(progress_path, row)
        rows.append(row)

    from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
        finalize_region_learning_dataset,
    )

    dataset_root = learning_root / "d4_region"
    d4_dataset_manifest = finalize_region_learning_dataset(
        staging_root,
        dataset_root,
        created_at_utc=str(plan["created_at_utc"]),
        split_seed=20260729,
        minimum_unseen_seeds=8 if len(options.seeds) >= 40 else 2,
    )
    shutil.rmtree(staging_root.parent)
    d4_manifest = dataset_root / "manifest.json"
    if not d4_manifest.is_file():
        raise D4V5IndependentDevelopmentError(
            "independent development D4 dataset did not finalize"
        )
    batch_summary = learning_root / "batch_learning_export_summary.json"
    _write_json(
        batch_summary,
        {
            "schema_version": D4_V5_INDEPENDENT_DEVELOPMENT_SCHEMA,
            "episode_count": len(rows),
            "frame_count": sum(int(row["frame_count"]) for row in rows),
            "d4_dataset_finalized": True,
            "d4_dataset_availability": (
                d4_dataset_manifest.availability.to_dict()
            ),
            "online_truth_policy": "forbidden",
            "learning_target_policy": (
                "same_snapshot_deterministic_rule_recomputed_offline"
            ),
            "runtime_recommendation_preserved": True,
            "model_fit_count": 0,
            "formal_holdout_payload_read_count": 0,
        },
    )
    progress_csv = output / "episode_progress.csv"
    _write_progress_csv(progress_csv, rows)
    summary_path = output / "generation_summary.json"
    summary = _build_summary(
        plan=plan,
        rows=rows,
        generation_wall_s=time.perf_counter() - started,
        d4_manifest=d4_manifest,
        batch_summary=batch_summary,
    )
    _write_json(summary_path, summary)
    return {
        "plan": plan_path,
        "progress_jsonl": progress_path,
        "progress_csv": progress_csv,
        "summary": summary_path,
        "d4_manifest": d4_manifest,
        "d4_dataset": d4_manifest.parent,
    }


def _build_development_config(
    base: ScenarioConfig,
    *,
    options: D4V5IndependentDevelopmentOptions,
    seed: int,
    scenario_family: str,
) -> ScenarioConfig:
    """Build one runtime configuration with a rotated regional imbalance."""

    config = make_curriculum_scenario(
        scenario_family,
        scale=max(options.target_count, options.resource_count),
        target_count=options.target_count,
        resource_count=options.resource_count,
        seed=seed,
        duration_s=options.duration_s,
        base=base,
    )
    target_counts, resource_counts = _regional_pattern(seed)
    metadata = dict(config.metadata)
    metadata.update(
        {
            "dataset_purpose": (
                "d4_v5_source_independent_development_evaluation"
            ),
            "development_data_class": (
                "independent_nonformal_no_fit"
            ),
            # Keep the imbalanced physical layout while allowing D3 to produce
            # one globally feasible plan. Planning-only D4 actions are not
            # executable teacher labels under the public learning contract.
            "regional_resource_locality_enforced": False,
            "regional_probe_layout_only": True,
            "regional_resource_probe": {
                "schema": REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION,
                "target_counts_by_region": target_counts,
                "resource_counts_by_region": resource_counts,
            },
            "synthetic_feature_expansion": False,
            "online_truth_policy": "forbidden",
            "model_fit_allowed": False,
            "formal_holdout": False,
        }
    )
    return replace(
        config,
        scenario_name=(
            "d4_v5_independent_development_"
            f"{scenario_family}_M{options.target_count}N"
            f"{options.resource_count}_R{options.region_count}"
        ),
        scenario_version=(
            "d4-v5-independent-development-"
            f"{scenario_family}-M{options.target_count}N"
            f"{options.resource_count}-R{options.region_count}-v1"
        ),
        recon_count=options.recon_count,
        region_count=options.region_count,
        metadata=metadata,
    )


def _regional_pattern(seed: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return a deterministic imbalance with seed-dependent region rotation."""

    base_targets, base_resources = _BASE_REGION_PATTERNS[
        int(seed) % len(_BASE_REGION_PATTERNS)
    ]
    offset = (int(seed) // len(_BASE_REGION_PATTERNS)) % len(base_targets)
    targets = _rotate(base_targets, offset)
    resources = _rotate(base_resources, offset)
    if (
        sum(targets) != 20
        or sum(resources) != 20
        or targets == resources
        or not any(t > r for t, r in zip(targets, resources, strict=True))
        or not any(t < r for t, r in zip(targets, resources, strict=True))
    ):
        raise D4V5IndependentDevelopmentError(
            "invalid independent regional perturbation pattern"
        )
    return targets, resources


def _rotate(values: Sequence[int], offset: int) -> tuple[int, ...]:
    resolved = int(offset) % len(values)
    return tuple(values[resolved:]) + tuple(values[:resolved])


def _audit_frames(
    runtime_frames: Sequence[Any],
    *,
    learning_frames: Sequence[Any],
    expected_region_count: int,
) -> dict[str, Any]:
    if not runtime_frames:
        raise D4V5IndependentDevelopmentError(
            "episode produced no D4 learning frames"
        )
    if len(runtime_frames) != len(learning_frames):
        raise D4V5IndependentDevelopmentError(
            "runtime and staged D4 frame counts differ"
        )
    safe_rule_target_count = 0
    runtime_recommendation_count = 0
    runtime_rule_recommendation_count = 0
    blocked_region_count = 0
    edge_count = 0
    region_count = 0
    target_transfer_count = 0
    for runtime_frame, learning_frame in zip(
        runtime_frames,
        learning_frames,
        strict=True,
    ):
        if runtime_frame.snapshot != learning_frame.snapshot:
            raise D4V5IndependentDevelopmentError(
                "offline target frame changed the authentic D4 snapshot"
            )
        regions = tuple(runtime_frame.snapshot.regions)
        if len(regions) != int(expected_region_count):
            raise D4V5IndependentDevelopmentError(
                "D4 snapshot region count differs from development scope"
            )
        region_count += len(regions)
        edge_count += len(tuple(runtime_frame.snapshot.edges))
        blocked_region_count += sum(
            bool(
                not bool(getattr(region, "owner_active", True))
                or bool(getattr(region, "fault_fenced", False))
                or str(
                    getattr(
                        getattr(region, "current_owner_layer", None),
                        "value",
                        "",
                    )
                )
                == "hold"
            )
            for region in regions
        )
        runtime_result = runtime_frame.recommendation
        runtime_recommendation = (
            None
            if runtime_result is None
            else getattr(runtime_result, "recommendation", None)
        )
        runtime_recommendation_count += int(runtime_recommendation is not None)
        runtime_source = getattr(runtime_recommendation, "source", None)
        runtime_source_value = str(
            getattr(runtime_source, "value", runtime_source or "")
        )
        runtime_rule_recommendation_count += int(
            runtime_source_value == "rule"
        )
        target = learning_frame.target
        recommendation = getattr(target, "recommendation", None)
        source = getattr(recommendation, "source", None)
        source_value = str(getattr(source, "value", source or ""))
        availability = getattr(target, "availability", None)
        availability_value = str(
            getattr(availability, "value", availability or "")
        )
        safe_rule_target_count += int(
            availability_value == "available"
            and source_value == "rule"
            and bool(getattr(recommendation, "projected", False))
        )
        target_transfer_count += len(
            tuple(getattr(recommendation, "transfers", ()))
        )
    return {
        "frame_count": len(runtime_frames),
        "region_record_count": region_count,
        "edge_record_count": edge_count,
        "safe_rule_target_frame_count": safe_rule_target_count,
        "runtime_recommendation_frame_count": runtime_recommendation_count,
        "runtime_rule_recommendation_frame_count": (
            runtime_rule_recommendation_count
        ),
        "blocked_runtime_region_record_count": blocked_region_count,
        "rule_target_transfer_count": target_transfer_count,
    }


def _build_offline_rule_frames(
    *,
    config: ScenarioConfig,
    manifest: Any,
    runtime_frames: Sequence[Any],
) -> tuple[Any, tuple[Any, ...]]:
    """Recompute same-snapshot R0 labels without changing online D4 evidence."""

    from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
        RegionLearningEpisodeSource,
        RegionLearningFrame,
        RegionLearningReward,
        RegionLearningTarget,
        RegionLearningTargetKind,
        RuleRegionResourcePolicy,
    )

    source = RegionLearningEpisodeSource(
        scenario_id=config.scenario_name,
        scenario_version=config.scenario_version,
        scenario_scale=f"M{config.target_count}N{config.resource_count}",
        seed=config.seed,
        episode_id=manifest.episode_id,
        git_commit=manifest.git_commit,
        git_dirty=manifest.repository_dirty,
        config_sha256=manifest.config_sha256,
    )
    rule_policy = RuleRegionResourcePolicy()
    records = []
    for frame in sorted(
        runtime_frames,
        key=lambda item: int(item.frame_index),
    ):
        rule_target = rule_policy.recommend(frame.snapshot)
        runtime_result = frame.recommendation
        runtime_recommendation = (
            None
            if runtime_result is None
            else getattr(runtime_result, "recommendation", None)
        )
        try:
            records.append(
                RegionLearningFrame(
                    frame_index=int(frame.frame_index),
                    timestamp_s=float(frame.timestamp_s),
                    snapshot=frame.snapshot,
                    target=RegionLearningTarget.available(
                        RegionLearningTargetKind.RULE,
                        rule_target,
                    ),
                    reward=RegionLearningReward.unavailable(
                        "d6_episode_outcome_not_joined"
                    ),
                    recommendation=runtime_recommendation,
                )
            )
        except ValueError as exc:
            raise D4V5IndependentDevelopmentError(
                "same-snapshot deterministic rule target is not safe: "
                f"seed={config.seed}, frame={frame.frame_index}, error={exc}"
            ) from exc
    return source, tuple(records)


def _load_and_validate_seed_registry(
    path: Path,
    *,
    seeds: Sequence[int],
) -> dict[str, list[int] | str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("seed registry must be a JSON object")
    if payload.get("schema_version") != (
        "scalable3d-d4-v5-independent-development-seed-registry-v1"
    ):
        raise ValueError("unsupported independent development seed registry")
    training = tuple(int(seed) for seed in payload.get("training_seeds", ()))
    formal = tuple(
        int(seed) for seed in payload.get("formal_holdout_seeds", ())
    )
    development = tuple(
        int(seed)
        for seed in payload.get("independent_development_seeds", ())
    )
    if (
        not training
        or not formal
        or not development
        or len(set(training)) != len(training)
        or len(set(formal)) != len(formal)
        or len(set(development)) != len(development)
    ):
        raise ValueError("seed registry classes must be non-empty and unique")
    if set(training) & set(formal) or set(training) & set(development) or (
        set(formal) & set(development)
    ):
        raise ValueError("seed registry classes must be disjoint")
    requested = set(int(seed) for seed in seeds)
    if not requested.issubset(development):
        raise ValueError(
            "requested seeds must belong to independent development: "
            f"{sorted(requested - set(development))}"
        )
    policy = payload.get("policy")
    if not isinstance(policy, Mapping) or (
        policy.get("all_seed_classes_disjoint") is not True
        or policy.get("independent_development_fit_allowed") is not False
        or policy.get("formal_holdout_payload_read_allowed") is not False
        or policy.get("online_truth_use_allowed") is not False
    ):
        raise ValueError("seed registry policy is not fail-closed")
    return {
        "registry_id": str(payload.get("registry_id", "")),
        "training_seeds": list(training),
        "formal_holdout_seeds": list(formal),
        "independent_development_seeds": list(development),
        "requested_seeds": sorted(requested),
    }


def _build_summary(
    *,
    plan: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    generation_wall_s: float,
    d4_manifest: Path,
    batch_summary: Path,
) -> dict[str, Any]:
    frame_count = sum(int(row["frame_count"]) for row in rows)
    rule_count = sum(
        int(row["safe_rule_target_frame_count"]) for row in rows
    )
    return {
        "schema_version": D4_V5_INDEPENDENT_DEVELOPMENT_SCHEMA,
        "created_at_utc": _utc_now(),
        "source": dict(plan["source"]),
        "seed_registry_id": plan["seed_classes"]["registry_id"],
        "episode_count": len(rows),
        "seed_count": len({int(row["seed"]) for row in rows}),
        "scenario_family_counts": {
            family: sum(row["scenario_family"] == family for row in rows)
            for family in sorted(
                {str(row["scenario_family"]) for row in rows}
            )
        },
        "frame_count": frame_count,
        "rule_target_frame_count": rule_count,
        "all_frames_rule_labeled": rule_count == frame_count,
        "all_episodes_finite": all(bool(row["finite_state"]) for row in rows),
        "online_truth_use_count": sum(
            int(row["online_truth_use_count"]) for row in rows
        ),
        "repository_dirty_episode_count": sum(
            int(bool(row["repository_dirty"])) for row in rows
        ),
        "model_fit_count": 0,
        "formal_holdout_payload_read_count": 0,
        "production_permission_available": False,
        "generation_wall_s": float(generation_wall_s),
        "d4_manifest": str(d4_manifest),
        "d4_manifest_sha256": _sha256_file(d4_manifest),
        "batch_summary": str(batch_summary),
        "batch_summary_sha256": _sha256_file(batch_summary),
    }


def _repository_state(root: Path) -> tuple[str, bool]:
    commit = _git_output(root, "rev-parse", "HEAD")
    dirty = bool(_git_output(root, "status", "--porcelain").strip())
    return commit, dirty


def _git_output(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_jsonl(path: Path, row: Mapping[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True))
        stream.write("\n")


def _write_progress_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if not rows:
        raise ValueError("progress rows must not be empty")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "D4_V5_INDEPENDENT_DEVELOPMENT_SCHEMA",
    "D4V5IndependentDevelopmentError",
    "D4V5IndependentDevelopmentOptions",
    "run_d4_v5_independent_development",
]
