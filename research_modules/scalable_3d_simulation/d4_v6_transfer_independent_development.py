"""Generate source-independent D4 v6 transfer-development frames.

This main-owned generator is intentionally model-free. It exports authentic
truth-free D4 snapshots and same-snapshot deterministic rule labels from seed
classes that are disjoint from training, prior development, and the formal
holdout. Candidate fitting and admission remain outside this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
import shutil
import time
from typing import Any, Mapping, Sequence

from .d4_v5_independent_development import (
    _append_jsonl,
    _audit_frames,
    _build_offline_rule_frames,
    _repository_state,
    _sha256_file,
    _utc_now,
    _write_json,
    _write_progress_csv,
)
from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .models import ScenarioConfig
from .module_stack import IntegratedStackConfig
from .orchestrator import run_episode
from .scenarios import AVAILABLE_SCENARIOS, make_curriculum_scenario
from .world import REGIONAL_RESOURCE_PROBE_SCHEMA_VERSION


D4_V6_TRANSFER_INDEPENDENT_SOURCE_SCHEMA = (
    "scalable3d-d4-v6-transfer-independent-source-v1"
)
DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"
DEFAULT_SEED_REGISTRY = (
    Path(__file__).with_name("configs")
    / "d4_v6_transfer_independent_seed_registry_v1.json"
)
DEFAULT_SEEDS = tuple(range(4016, 4080))
DEFAULT_SCENARIO_FAMILIES = (
    "nominal",
    "dense_crossing",
    "evasive_multilevel",
    "delayed_noisy",
)

_BASE_REGION_PATTERNS = (
    (
        (4, 3, 2, 2, 2, 1, 1, 1),
        (1, 2, 2, 3, 4, 5, 4, 3),
    ),
    (
        (1, 4, 3, 2, 1, 2, 2, 1),
        (5, 1, 2, 3, 4, 2, 4, 3),
    ),
    (
        (2, 1, 4, 1, 3, 2, 1, 2),
        (3, 5, 1, 4, 1, 3, 4, 3),
    ),
    (
        (3, 2, 1, 4, 2, 1, 2, 1),
        (1, 4, 5, 1, 3, 4, 3, 3),
    ),
)


class D4V6TransferIndependentDevelopmentError(RuntimeError):
    """Stable failure for invalid or contaminated source generation."""


@dataclass(frozen=True)
class D4V6TransferIndependentDevelopmentOptions:
    """Frozen source-generation contract for one independent batch."""

    output_dir: Path
    config_path: Path = DEFAULT_CONFIG
    seed_registry_path: Path = DEFAULT_SEED_REGISTRY
    seeds: tuple[int, ...] = DEFAULT_SEEDS
    scenario_families: tuple[str, ...] = DEFAULT_SCENARIO_FAMILIES
    target_count: int = 16
    resource_count: int = 24
    recon_count: int = 2
    region_count: int = 8
    duration_s: float = 2.0
    allow_dirty: bool = False

    def __post_init__(self) -> None:
        for name in ("output_dir", "config_path", "seed_registry_path"):
            object.__setattr__(self, name, Path(getattr(self, name)))
        seeds = tuple(int(seed) for seed in self.seeds)
        if len(seeds) < 8 or len(set(seeds)) != len(seeds):
            raise ValueError(
                "v6 independent generation requires eight unique seeds"
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
        if (
            int(self.target_count) != 16
            or int(self.resource_count) != 24
            or int(self.region_count) != 8
            or int(self.recon_count) <= 0
        ):
            raise ValueError(
                "v6 transfer source contract requires M16N24, eight "
                "regions, and a positive reconnaissance count"
            )
        if not math.isfinite(float(self.duration_s)) or self.duration_s <= 0.0:
            raise ValueError("duration_s must be finite and positive")


def run_d4_v6_transfer_independent_development(
    options: D4V6TransferIndependentDevelopmentOptions,
) -> dict[str, Path]:
    """Run authentic episodes and freeze their model-free D4 records."""

    repository_root = Path(__file__).resolve().parents[2]
    git_commit, repository_dirty = _repository_state(repository_root)
    if repository_dirty and not options.allow_dirty:
        raise D4V6TransferIndependentDevelopmentError(
            "v6 independent generation requires a clean repository"
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
        "schema_version": D4_V6_TRANSFER_INDEPENDENT_SOURCE_SCHEMA,
        "created_at_utc": _utc_now(),
        "purpose": "d4_v6_transfer_source_independent_development",
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
            raise D4V6TransferIndependentDevelopmentError(
                f"non-finite episode state for seed {seed}"
            )
        if int(result.summary["online_truth_use_count"]) != 0:
            raise D4V6TransferIndependentDevelopmentError(
                f"online truth use detected for seed {seed}"
            )
        if not options.allow_dirty and result.manifest.repository_dirty:
            raise D4V6TransferIndependentDevelopmentError(
                f"episode source became dirty for seed {seed}"
            )
        if (
            frame_audit["safe_rule_target_frame_count"]
            != frame_audit["frame_count"]
        ):
            raise D4V6TransferIndependentDevelopmentError(
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
        split_seed=20260730,
        minimum_unseen_seeds=16 if len(options.seeds) >= 48 else 2,
    )
    shutil.rmtree(staging_root.parent)
    d4_manifest = dataset_root / "manifest.json"
    if not d4_manifest.is_file():
        raise D4V6TransferIndependentDevelopmentError(
            "v6 independent D4 dataset did not finalize"
        )
    batch_summary = learning_root / "batch_learning_export_summary.json"
    _write_json(
        batch_summary,
        {
            "schema_version": D4_V6_TRANSFER_INDEPENDENT_SOURCE_SCHEMA,
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
            "prior_evaluation_payload_read_count": 0,
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
    options: D4V6TransferIndependentDevelopmentOptions,
    seed: int,
    scenario_family: str,
) -> ScenarioConfig:
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
                "d4_v6_transfer_source_independent_development"
            ),
            "development_data_class": (
                "independent_nonformal_no_fit"
            ),
            "regional_resource_locality_enforced": False,
            "regional_probe_layout_only": True,
            "resource_surplus_design": {
                "target_count": options.target_count,
                "resource_count": options.resource_count,
                "spare_resource_count": (
                    options.resource_count - options.target_count
                ),
                "design_pilot_seeds": list(range(4000, 4016)),
                "design_pilot_excluded_from_evaluation": True,
                "prior_evaluation_seeds": list(range(3000, 3040)),
                "prior_evaluation_reuse_allowed": False,
            },
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
            "d4_v6_transfer_independent_"
            f"{scenario_family}_M{options.target_count}N"
            f"{options.resource_count}_R{options.region_count}"
        ),
        scenario_version=(
            "d4-v6-transfer-independent-"
            f"{scenario_family}-M{options.target_count}N"
            f"{options.resource_count}-R{options.region_count}-v1"
        ),
        recon_count=options.recon_count,
        region_count=options.region_count,
        metadata=metadata,
    )


def _regional_pattern(seed: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return 64 deterministic donor/receiver layouts before repetition."""

    base_targets, base_resources = _BASE_REGION_PATTERNS[
        int(seed) % len(_BASE_REGION_PATTERNS)
    ]
    block = int(seed) // len(_BASE_REGION_PATTERNS)
    offset = block % len(base_targets)
    targets = _rotate(base_targets, offset)
    resources = _rotate(base_resources, offset)
    if (block // len(base_targets)) % 2:
        targets = tuple(reversed(targets))
        resources = tuple(reversed(resources))
    if (
        sum(targets) != 16
        or sum(resources) != 24
        or not any(t > r for t, r in zip(targets, resources, strict=True))
        or not any(t < r for t, r in zip(targets, resources, strict=True))
        or min(targets) <= 0
        or min(resources) <= 0
    ):
        raise D4V6TransferIndependentDevelopmentError(
            "invalid v6 independent regional pattern"
        )
    return targets, resources


def _rotate(values: Sequence[int], offset: int) -> tuple[int, ...]:
    resolved = int(offset) % len(values)
    return tuple(values[resolved:]) + tuple(values[:resolved])


def _load_and_validate_seed_registry(
    path: Path,
    *,
    seeds: Sequence[int],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != (
        "scalable3d-d4-v6-transfer-independent-seed-registry-v1"
    ):
        raise ValueError("unsupported v6 transfer seed registry")
    names = (
        "training_seeds",
        "formal_holdout_seeds",
        "prior_design_and_evaluation_seeds",
        "design_pilot_seeds",
        "independent_development_seeds",
    )
    classes = {
        name: tuple(int(seed) for seed in payload.get(name, ()))
        for name in names
    }
    if any(
        not values or len(values) != len(set(values))
        for values in classes.values()
    ):
        raise ValueError("v6 seed classes must be non-empty and unique")
    sets = tuple(set(classes[name]) for name in names)
    if any(
        left & right
        for index, left in enumerate(sets)
        for right in sets[index + 1 :]
    ):
        raise ValueError("v6 seed classes must be disjoint")
    requested = {int(seed) for seed in seeds}
    independent = set(classes["independent_development_seeds"])
    if not requested.issubset(independent):
        raise ValueError(
            "requested seeds must belong to v6 independent development: "
            f"{sorted(requested - independent)}"
        )
    policy = payload.get("policy")
    if not isinstance(policy, Mapping) or any(
        policy.get(name) is not expected
        for name, expected in {
            "all_seed_classes_disjoint": True,
            "design_pilot_fit_allowed": False,
            "independent_development_fit_allowed": False,
            "prior_evaluation_reuse_allowed": False,
            "formal_holdout_payload_read_allowed": False,
            "online_truth_use_allowed": False,
        }.items()
    ):
        raise ValueError("v6 seed registry policy is not fail-closed")
    return {
        "registry_id": str(payload.get("registry_id", "")),
        **{name: list(classes[name]) for name in names},
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
        "schema_version": D4_V6_TRANSFER_INDEPENDENT_SOURCE_SCHEMA,
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
        "regional_pattern_count": len(
            {
                (
                    tuple(row["target_counts_by_region"]),
                    tuple(row["resource_counts_by_region"]),
                )
                for row in rows
            }
        ),
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
        "prior_evaluation_payload_read_count": 0,
        "formal_holdout_payload_read_count": 0,
        "production_permission_available": False,
        "generation_wall_s": float(generation_wall_s),
        "d4_manifest": str(d4_manifest),
        "d4_manifest_sha256": _sha256_file(d4_manifest),
        "batch_summary": str(batch_summary),
        "batch_summary_sha256": _sha256_file(batch_summary),
    }


__all__ = [
    "D4_V6_TRANSFER_INDEPENDENT_SOURCE_SCHEMA",
    "D4V6TransferIndependentDevelopmentError",
    "D4V6TransferIndependentDevelopmentOptions",
    "run_d4_v6_transfer_independent_development",
]
