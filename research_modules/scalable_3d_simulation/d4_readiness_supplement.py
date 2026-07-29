"""Generate a truth-isolated D4 runtime-readiness supplement dataset."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping, Sequence

from .learning_export import BatchLearningArtifactWriter
from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .models import ScenarioConfig
from .module_stack import IntegratedLearningArtifacts, IntegratedStackConfig
from .orchestrator import run_episode
from .scenarios import make_curriculum_scenario


D4_READINESS_SUPPLEMENT_SCHEMA_VERSION = (
    "scalable3d-d4-readiness-supplement-v1"
)
DEFAULT_CONFIG = Path(__file__).with_name("configs") / "nominal_200v200.json"
DEFAULT_SEED_REGISTRY = (
    Path(__file__).with_name("configs")
    / "formal_evaluation_seed_registry_v1.json"
)
DEFAULT_SEEDS = tuple(range(100))


@dataclass(frozen=True)
class D4ReadinessSupplementOptions:
    """Bounded source and scenario definition for the D4 supplement."""

    output_dir: Path
    config_path: Path = DEFAULT_CONFIG
    seed_registry_path: Path = DEFAULT_SEED_REGISTRY
    seeds: tuple[int, ...] = DEFAULT_SEEDS
    target_count: int = 20
    resource_count: int = 20
    recon_count: int = 2
    region_count: int = 8
    duration_s: float = 1.2
    allow_dirty: bool = False

    def __post_init__(self) -> None:
        for name in ("output_dir", "config_path", "seed_registry_path"):
            object.__setattr__(self, name, Path(getattr(self, name)))
        seeds = tuple(int(seed) for seed in self.seeds)
        if len(seeds) < 3 or len(set(seeds)) != len(seeds):
            raise ValueError("seeds must contain at least three unique values")
        if any(seed < 0 for seed in seeds):
            raise ValueError("seeds must be non-negative")
        object.__setattr__(self, "seeds", seeds)
        for name in (
            "target_count",
            "resource_count",
            "recon_count",
            "region_count",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if not math.isfinite(float(self.duration_s)) or self.duration_s <= 0.0:
            raise ValueError("duration_s must be finite and positive")


def run_d4_readiness_supplement(
    options: D4ReadinessSupplementOptions,
) -> dict[str, Path]:
    """Run authentic episodes and finalize only their D4 learning records."""

    source_root = Path(__file__).resolve().parents[2]
    git_commit, repository_dirty = _repository_state(source_root)
    if repository_dirty and not options.allow_dirty:
        raise RuntimeError(
            "D4 readiness supplement generation requires a clean repository"
        )
    registry = _load_and_validate_seed_registry(
        options.seed_registry_path,
        seeds=options.seeds,
    )
    output = options.output_dir.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)

    base = ScenarioConfig.from_dict(
        json.loads(options.config_path.read_text(encoding="utf-8"))
    )
    plan = {
        "schema_version": D4_READINESS_SUPPLEMENT_SCHEMA_VERSION,
        "created_at_utc": _utc_now(),
        "purpose": "authentic_current_runtime_secondary_readiness_supplement",
        "source": {
            "git_commit": git_commit,
            "repository_dirty": repository_dirty,
            "config_path": str(options.config_path.resolve()),
            "config_sha256": _sha256_file(options.config_path),
            "seed_registry_path": str(options.seed_registry_path.resolve()),
            "seed_registry_sha256": _sha256_file(options.seed_registry_path),
        },
        "scenario": {
            "scenario_family": "nominal",
            "target_count": options.target_count,
            "resource_count": options.resource_count,
            "recon_count": options.recon_count,
            "region_count": options.region_count,
            "duration_s": options.duration_s,
            "d4_advisor_mode": "shadow_rule_fallback",
            "d5_active_vision_enabled": False,
        },
        "seeds": list(options.seeds),
        "reserved_evaluation_seeds": list(registry["evaluation_seeds"]),
        "online_truth_policy": "forbidden",
        "required_evidence": {
            "finite_state": True,
            "online_truth_use_count": 0,
            "rule_target_for_every_d4_frame": True,
            "secondary_readiness_zero_in_every_episode": True,
        },
    }
    plan_path = output / "generation_plan.json"
    _write_json(plan_path, plan)

    writer = BatchLearningArtifactWriter(output / "learning_dataset")
    progress_path = output / "episode_progress.jsonl"
    rows: list[dict[str, Any]] = []
    generation_started = time.perf_counter()
    for sequence, seed in enumerate(options.seeds):
        config = _build_supplement_config(base, options=options, seed=seed)
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
        frames = resolved.stack.learning_artifacts().d4_region_frames
        readiness = _audit_d4_frames(
            frames,
            expected_region_count=options.region_count,
        )
        if result.summary["finite_state"] is not True:
            raise RuntimeError(f"non-finite episode state for seed {seed}")
        if int(result.summary["online_truth_use_count"]) != 0:
            raise RuntimeError(f"online truth use detected for seed {seed}")
        if not options.allow_dirty and result.manifest.repository_dirty:
            raise RuntimeError(f"episode source became dirty for seed {seed}")
        if readiness["rule_target_frame_count"] != readiness["frame_count"]:
            raise RuntimeError(f"D4 rule target unavailable for seed {seed}")
        if readiness["zero_value_count"] <= 0:
            raise RuntimeError(
                f"secondary_readiness=0 was not observed for seed {seed}"
            )

        d4_only = IntegratedLearningArtifacts(
            d3_planning_frames=(),
            d4_region_frames=frames,
            d5_graph_frames=(),
            d5_active_vision_frames=(),
        )
        staged = writer.stage_episode(
            config=result.config,
            manifest=result.manifest,
            artifacts=d4_only,
            offline_truth_labels=(),
            online_messages=(),
        )
        row = {
            "sequence": sequence,
            "seed": seed,
            "episode_id": result.manifest.episode_id,
            "scenario_version": result.config.scenario_version,
            "config_sha256": result.manifest.config_sha256,
            "finite_state": True,
            "online_truth_use_count": 0,
            "repository_dirty": bool(result.manifest.repository_dirty),
            "episode_wall_s": episode_wall_s,
            **readiness,
            **{
                key: value
                for key, value in staged.items()
                if key not in {
                    "episode_id",
                    "scenario_version",
                    "seed",
                    "config_sha256",
                }
            },
        }
        _append_jsonl(progress_path, row)
        rows.append(row)

    finalized = writer.finalize()
    d4_manifest = finalized.get("d4_manifest")
    if d4_manifest is None or not d4_manifest.is_file():
        raise RuntimeError("D4 supplement dataset did not finalize")
    progress_csv = output / "episode_progress.csv"
    _write_progress_csv(progress_csv, rows)
    summary_path = output / "generation_summary.json"
    summary = _build_summary(
        plan=plan,
        rows=rows,
        generation_wall_s=time.perf_counter() - generation_started,
        d4_manifest=d4_manifest,
        batch_summary=finalized["summary"],
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


def _build_supplement_config(
    base: ScenarioConfig,
    *,
    options: D4ReadinessSupplementOptions,
    seed: int,
) -> ScenarioConfig:
    scale = max(options.target_count, options.resource_count)
    config = make_curriculum_scenario(
        "nominal",
        scale=scale,
        target_count=options.target_count,
        resource_count=options.resource_count,
        seed=seed,
        duration_s=options.duration_s,
        base=base,
    )
    metadata = dict(config.metadata)
    metadata.update(
        {
            "dataset_purpose": (
                "d4_authentic_current_runtime_readiness_supplement"
            ),
            "synthetic_feature_expansion": False,
            "online_truth_policy": "forbidden",
        }
    )
    return replace(
        config,
        scenario_name=(
            "d4_readiness_supplement_"
            f"M{options.target_count}N{options.resource_count}_"
            f"R{options.region_count}Q{options.recon_count}"
        ),
        scenario_version=(
            "d4-readiness-supplement-"
            f"M{options.target_count}N{options.resource_count}-"
            f"R{options.region_count}Q{options.recon_count}-v1"
        ),
        recon_count=options.recon_count,
        region_count=options.region_count,
        metadata=metadata,
    )


def _audit_d4_frames(
    frames: Sequence[Any],
    *,
    expected_region_count: int,
) -> dict[str, Any]:
    if not frames:
        raise RuntimeError("episode produced no D4 learning frames")
    zero_count = 0
    positive_count = 0
    rule_target_count = 0
    values: list[float] = []
    for frame in frames:
        regions = tuple(frame.snapshot.regions)
        if len(regions) != int(expected_region_count):
            raise RuntimeError(
                "D4 snapshot region count differs from supplement scope"
            )
        recommendation = getattr(frame.recommendation, "recommendation", None)
        source = getattr(recommendation, "source", None)
        source_value = str(getattr(source, "value", source or ""))
        rule_target_count += int(source_value == "rule")
        for region in regions:
            value = float(region.secondary_readiness)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise RuntimeError("secondary_readiness must be finite in [0, 1]")
            values.append(value)
            if abs(value) <= 1e-12:
                zero_count += 1
            else:
                positive_count += 1
    return {
        "frame_count": len(frames),
        "region_value_count": len(values),
        "zero_value_count": zero_count,
        "positive_value_count": positive_count,
        "zero_value_fraction": zero_count / len(values),
        "secondary_readiness_min": min(values),
        "secondary_readiness_max": max(values),
        "rule_target_frame_count": rule_target_count,
    }


def _load_and_validate_seed_registry(
    path: Path,
    *,
    seeds: Sequence[int],
) -> dict[str, tuple[int, ...]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("seed registry must be a JSON object")
    training = tuple(int(seed) for seed in payload.get("training_seeds", ()))
    evaluation = tuple(int(seed) for seed in payload.get("evaluation_seeds", ()))
    requested = set(int(seed) for seed in seeds)
    if not requested.issubset(training):
        raise ValueError(
            "supplement seeds must be declared training seeds: "
            f"{sorted(requested - set(training))}"
        )
    overlap = requested & set(evaluation)
    if overlap:
        raise ValueError(
            f"supplement seeds overlap evaluation seeds: {sorted(overlap)}"
        )
    return {
        "training_seeds": training,
        "evaluation_seeds": evaluation,
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
    value_count = sum(int(row["region_value_count"]) for row in rows)
    zero_count = sum(int(row["zero_value_count"]) for row in rows)
    rule_count = sum(int(row["rule_target_frame_count"]) for row in rows)
    return {
        "schema_version": D4_READINESS_SUPPLEMENT_SCHEMA_VERSION,
        "created_at_utc": _utc_now(),
        "source": dict(plan["source"]),
        "scenario": dict(plan["scenario"]),
        "episode_count": len(rows),
        "seed_count": len({int(row["seed"]) for row in rows}),
        "frame_count": frame_count,
        "region_value_count": value_count,
        "secondary_readiness_zero_value_count": zero_count,
        "secondary_readiness_zero_fraction": (
            zero_count / value_count if value_count else 0.0
        ),
        "secondary_readiness_min": min(
            float(row["secondary_readiness_min"]) for row in rows
        ),
        "secondary_readiness_max": max(
            float(row["secondary_readiness_max"]) for row in rows
        ),
        "rule_target_frame_count": rule_count,
        "all_frames_rule_labeled": rule_count == frame_count,
        "all_episodes_finite": all(bool(row["finite_state"]) for row in rows),
        "online_truth_use_count": sum(
            int(row["online_truth_use_count"]) for row in rows
        ),
        "repository_dirty_episode_count": sum(
            int(bool(row["repository_dirty"])) for row in rows
        ),
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


def _write_progress_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
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
    "D4_READINESS_SUPPLEMENT_SCHEMA_VERSION",
    "D4ReadinessSupplementOptions",
    "run_d4_readiness_supplement",
]
