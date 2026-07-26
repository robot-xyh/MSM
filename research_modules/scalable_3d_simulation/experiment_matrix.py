"""Paired, fail-closed experiment orchestration for scalable 3D research.

The matrix runner is main-owned. It selects module-owned optional bundles,
uses identical scenario/scale/seed keys for comparable variants, and leaves
all control decisions inside the existing D1-D7 stack.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import csv
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence

from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .models import ScenarioConfig
from .module_stack import IntegratedStackConfig
from .orchestrator import run_episode
from .scenarios import AVAILABLE_SCENARIOS, make_curriculum_scenario


EXPERIMENT_MATRIX_SCHEMA_VERSION = "scalable3d-experiment-matrix-v1"
PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION = "entity_fixed_v1"
EXPERIMENT_VARIANTS = ("R0", "G1", "A1", "A2", "A3", "C1", "F1")
VARIANT_MODEL_COMPONENTS = {
    "R0": (),
    "G1": ("d5_graph",),
    "A1": ("d3",),
    "A2": ("d4",),
    "A3": ("d5_active_vision",),
    "C1": ("d3", "d4", "d5_graph", "d5_active_vision"),
    "F1": ("d3", "d4", "d5_graph", "d5_active_vision"),
}
FULL_SYSTEM_SCENARIOS = frozenset(
    {"center_failure", "secondary_failure", "high_threat_m_to_n"}
)


@dataclass(frozen=True)
class ModelBundlePaths:
    d3: Path | None = None
    d4: Path | None = None
    d5_graph: Path | None = None
    d5_active_vision: Path | None = None

    def __post_init__(self) -> None:
        for name in ("d3", "d4", "d5_graph", "d5_active_vision"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value))


@dataclass(frozen=True)
class ExperimentCell:
    variant: str
    scenario: str
    scale: int
    seed: int

    @property
    def comparison_key(self) -> str:
        return f"{self.scenario}|{self.scale}|{self.seed}"


@dataclass(frozen=True)
class ExperimentMatrixPlan:
    variants: tuple[str, ...]
    scenarios: tuple[str, ...]
    scales: tuple[int, ...]
    seeds: tuple[int, ...]
    duration_s: float
    formal: bool = False
    allow_rule_fallback: bool = False
    training_seeds: frozenset[int] | None = None

    def __post_init__(self) -> None:
        variants = tuple(dict.fromkeys(str(item).strip().upper() for item in self.variants))
        scenarios = tuple(dict.fromkeys(str(item).strip().lower() for item in self.scenarios))
        scales = tuple(dict.fromkeys(int(item) for item in self.scales))
        seeds = tuple(dict.fromkeys(int(item) for item in self.seeds))
        unknown_variants = sorted(set(variants) - set(EXPERIMENT_VARIANTS))
        unknown_scenarios = sorted(set(scenarios) - set(AVAILABLE_SCENARIOS))
        if unknown_variants:
            raise ValueError(f"unknown experiment variants: {unknown_variants}")
        if unknown_scenarios:
            raise ValueError(f"unknown scenarios: {unknown_scenarios}")
        if not variants or not scenarios or not scales or not seeds:
            raise ValueError("variants, scenarios, scales, and seeds must not be empty")
        if any(value <= 0 for value in scales):
            raise ValueError("all scales must be positive")
        if any(value < 0 for value in seeds):
            raise ValueError("all seeds must be non-negative")
        if float(self.duration_s) <= 0.0:
            raise ValueError("duration_s must be positive")
        if self.formal:
            if set(variants) != set(EXPERIMENT_VARIANTS):
                raise ValueError("formal matrix requires R0/G1/A1/A2/A3/C1/F1")
            if len(seeds) < 20:
                raise ValueError("formal matrix requires at least 20 unique unseen seeds")
            if self.training_seeds is None:
                raise ValueError("formal matrix requires an explicit training seed registry")
            required_scales = {5, 20, 50, 100, 200}
            missing_scales = sorted(required_scales - set(scales))
            if missing_scales:
                raise ValueError(f"formal matrix requires curriculum scales: {missing_scales}")
            missing_scenarios = sorted(set(AVAILABLE_SCENARIOS) - set(scenarios))
            if missing_scenarios:
                raise ValueError(
                    f"formal matrix requires the complete scenario catalog: {missing_scenarios}"
                )
            overlap = set(seeds) & set(self.training_seeds)
            if overlap:
                raise ValueError(f"formal evaluation seeds overlap training seeds: {sorted(overlap)}")
            if self.allow_rule_fallback:
                raise ValueError("formal matrix cannot allow rule fallback for learned variants")
            missing_full = sorted(FULL_SYSTEM_SCENARIOS - set(scenarios))
            if missing_full:
                raise ValueError(
                    f"formal matrix requires full-system scenarios: {missing_full}"
                )
        object.__setattr__(self, "variants", variants)
        object.__setattr__(self, "scenarios", scenarios)
        object.__setattr__(self, "scales", scales)
        object.__setattr__(self, "seeds", seeds)
        object.__setattr__(self, "duration_s", float(self.duration_s))

    def cells(self) -> tuple[ExperimentCell, ...]:
        cells: list[ExperimentCell] = []
        for variant in self.variants:
            variant_scenarios = self.scenarios
            if variant == "F1":
                variant_scenarios = tuple(
                    item for item in self.scenarios if item in FULL_SYSTEM_SCENARIOS
                )
                if not variant_scenarios:
                    raise ValueError("F1 requires at least one full-system fault/demand scenario")
            for scenario in variant_scenarios:
                for scale in self.scales:
                    for seed in self.seeds:
                        cells.append(ExperimentCell(variant, scenario, scale, seed))
        return tuple(cells)


def load_training_seeds(path: str | Path | None) -> frozenset[int] | None:
    """Load seed identities from a physically separate training registry."""

    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("training seed registry must be a JSON object")
    raw = payload.get("training_seeds", payload.get("seed_groups"))
    if not isinstance(raw, list):
        raise ValueError("training seed registry requires training_seeds or seed_groups")
    seeds: set[int] = set()
    for item in raw:
        value = item.get("seed") if isinstance(item, Mapping) else item
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("training seed values must be non-negative integers")
        seeds.add(int(value))
    return frozenset(seeds)


def runtime_options_for_variant(
    variant: str,
    bundles: ModelBundlePaths,
    *,
    device: str,
) -> LearningRuntimeOptions:
    """Map one named ablation to explicit optional-learning runtime inputs."""

    key = str(variant).strip().upper()
    if key not in EXPERIMENT_VARIANTS:
        raise ValueError(f"unknown experiment variant: {variant}")
    use_d3 = key in {"A1", "C1", "F1"}
    use_d4 = key in {"A2", "C1", "F1"}
    use_d5_graph = key in {"G1", "C1", "F1"}
    use_active_vision = key in {"A3", "C1", "F1"}
    return LearningRuntimeOptions(
        d3_mode="assist" if use_d3 else "disabled",
        d3_bundle_dir=bundles.d3 if use_d3 else None,
        d4_mode="assist" if use_d4 else "disabled",
        d4_bundle_dir=bundles.d4 if use_d4 else None,
        d5_bundle_dir=bundles.d5_graph if use_d5_graph else None,
        d5_active_vision_mode="assist" if use_active_vision else "disabled",
        d5_active_vision_bundle_dir=(
            bundles.d5_active_vision if use_active_vision else None
        ),
        device=device,
    )


def validate_required_bundles(
    variants: Iterable[str],
    bundles: ModelBundlePaths,
) -> None:
    labels = {
        "d3": "D3",
        "d4": "D4",
        "d5_graph": "D5 graph",
        "d5_active_vision": "D5 active vision",
    }
    required = required_model_components(variants)
    missing = [
        labels[name]
        for name in required
        if getattr(bundles, name) is None or not getattr(bundles, name).is_dir()
    ]
    if missing:
        raise ValueError(f"required model bundles are missing: {', '.join(missing)}")


def required_model_components(variants: Iterable[str]) -> tuple[str, ...]:
    """Return the stable union of model components required by variants."""

    selected = tuple(
        dict.fromkeys(str(item).strip().upper() for item in variants)
    )
    unknown = sorted(set(selected) - set(EXPERIMENT_VARIANTS))
    if unknown:
        raise ValueError(f"unknown experiment variants: {unknown}")
    required: list[str] = []
    for variant in selected:
        for component in VARIANT_MODEL_COMPONENTS[variant]:
            if component not in required:
                required.append(component)
    return tuple(required)


def repository_state(root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def run_experiment_matrix(
    *,
    root: Path,
    output_dir: Path,
    base_config: ScenarioConfig,
    plan: ExperimentMatrixPlan,
    bundles: ModelBundlePaths,
    device: str = "cpu",
    write_d6_report: bool = True,
) -> dict[str, Path]:
    """Run all matrix cells without retaining large episode histories in memory."""

    root = Path(root).resolve()
    output_dir = Path(output_dir)
    commit, dirty = repository_state(root)
    if plan.formal and dirty:
        raise RuntimeError("formal experiment matrix requires repository_dirty=false")
    validate_required_bundles(plan.variants, bundles)
    cells = plan.cells()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    episode_dirs: list[Path] = []
    pairing_hashes: dict[str, str] = {}
    for index, cell in enumerate(cells):
        config = make_curriculum_scenario(
            cell.scenario,
            scale=cell.scale,
            seed=cell.seed,
            duration_s=plan.duration_s,
            base=base_config,
        )
        config = replace(
            config,
            sensor_random_schedule_version=(
                PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION
            ),
        )
        pairing_config_sha256 = paired_exogenous_config_sha256(config)
        prior_pairing_hash = pairing_hashes.setdefault(
            cell.comparison_key,
            pairing_config_sha256,
        )
        if prior_pairing_hash != pairing_config_sha256:
            raise RuntimeError(
                "experiment variants do not share one exogenous configuration"
            )
        metadata = dict(config.metadata)
        metadata.update(
            {
                "experiment_matrix_schema": EXPERIMENT_MATRIX_SCHEMA_VERSION,
                "algorithm_variant": cell.variant,
                "comparison_key": cell.comparison_key,
                "paired_exogenous_config_sha256": pairing_config_sha256,
                "full_system_validation": cell.variant == "F1",
            }
        )
        config = replace(config, metadata=metadata)
        options = runtime_options_for_variant(cell.variant, bundles, device=device)
        resolved = resolve_learning_runtime(config, options, stack_config=IntegratedStackConfig())
        _validate_resolved_variant(
            cell.variant,
            resolved.diagnostics,
            allow_rule_fallback=plan.allow_rule_fallback,
        )
        episode_dir = (
            output_dir
            / cell.variant
            / cell.scenario
            / f"{cell.scale}v{cell.scale}"
            / f"seed_{cell.seed}"
        )
        result = run_episode(
            resolved.config,
            output_dir=episode_dir,
            module_stack=resolved.stack,
        )
        rows.append(
            {
                "cell_index": index,
                "variant": cell.variant,
                "scenario": cell.scenario,
                "scale": cell.scale,
                "seed": cell.seed,
                "comparison_key": cell.comparison_key,
                "paired_exogenous_config_sha256": pairing_config_sha256,
                "sensor_random_schedule_version": (
                    resolved.config.sensor_random_schedule_version
                ),
                "episode_id": result.manifest.episode_id,
                "finite_state": bool(result.summary["finite_state"]),
                "online_truth_use_count": int(result.summary["online_truth_use_count"]),
                "real_time_factor": result.summary["real_time_factor"],
                "intercepted_target_count": int(result.summary["intercepted_target_count"]),
            }
        )
        episode_dirs.append(episode_dir)

    matrix_manifest = {
        "schema_version": EXPERIMENT_MATRIX_SCHEMA_VERSION,
        "git_commit": commit,
        "repository_dirty": dirty,
        "formal": plan.formal,
        "variants": list(plan.variants),
        "scenarios": list(plan.scenarios),
        "scales": list(plan.scales),
        "seeds": list(plan.seeds),
        "training_seed_registry_present": plan.training_seeds is not None,
        "training_seeds_sha256": _seed_digest(plan.training_seeds or ()),
        "cell_count": len(cells),
        "completed_cell_count": len(rows),
        "paired_random_schedule_version": (
            PAIRED_SENSOR_RANDOM_SCHEDULE_VERSION
        ),
        "paired_exogenous_config_count": len(pairing_hashes),
        "paired_exogenous_configuration_consistent": True,
    }
    paths = {
        "manifest": _write_json(output_dir / "experiment_matrix_manifest.json", matrix_manifest),
        "cells": _write_rows(output_dir / "experiment_matrix_cells.csv", rows),
    }
    if write_d6_report:
        from research_modules.d6_evaluation_metrics.d6_evaluation_metrics.scalable_3d_offline import (
            Scalable3DOfflineEvaluationInputs,
            Scalable3DOfflineReportGenerator,
        )

        report_paths = Scalable3DOfflineReportGenerator().write_report_bundle(
            output_dir / "d6_evaluation",
            inputs=Scalable3DOfflineEvaluationInputs(episode_dirs=tuple(episode_dirs)),
        )
        paths.update({f"d6_{name}": path for name, path in report_paths.items()})
    return paths


def _validate_resolved_variant(
    variant: str,
    diagnostics: Mapping[str, Any],
    *,
    allow_rule_fallback: bool,
) -> None:
    if variant == "R0":
        return
    diagnostic_names = {"d5_graph": "d5"}
    required = tuple(
        diagnostic_names.get(component, component)
        for component in VARIANT_MODEL_COMPONENTS[variant]
    )
    failures: list[str] = []
    for component in required:
        record = diagnostics.get(component)
        if not isinstance(record, Mapping) or not bool(record.get("bundle_loaded")):
            failures.append(f"{component}:bundle_not_loaded")
            continue
        if component == "d5_active_vision" and not bool(record.get("assist_admitted")):
            failures.append(f"{component}:assist_not_admitted")
            continue
        if str(record.get("effective_mode")) != "assist":
            failures.append(f"{component}:effective_mode={record.get('effective_mode')}")
    if failures and not allow_rule_fallback:
        raise RuntimeError(
            f"variant {variant} did not resolve to its declared learning path: {failures}"
        )


def _seed_digest(seeds: Iterable[int]) -> str:
    payload = json.dumps(sorted(int(value) for value in seeds), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def paired_exogenous_config_sha256(config: ScenarioConfig) -> str:
    """Hash physical, sensor, communication, and fault inputs only.

    Learning variants and resolved model fingerprints are deliberately
    excluded. The hash is therefore identical for R0 and candidate variants
    only when they share the same exogenous episode conditions.
    """

    payload = config.to_dict()
    for name in (
        "d3_policy_version",
        "d4_policy_version",
        "d5_model_version",
        "d5_active_vision_policy_version",
    ):
        payload.pop(name, None)
    metadata = dict(payload.get("metadata", {}))
    for name in (
        "algorithm_variant",
        "comparison_key",
        "experiment_matrix_schema",
        "full_system_validation",
        "learning_runtime",
        "paired_exogenous_config_sha256",
        "matrix_execution_plan_sha256",
        "matrix_parent_plan_sha256",
        "matrix_scope_index",
        "matrix_global_index",
        "matrix_shard_index",
    ):
        metadata.pop(name, None)
    payload["metadata"] = metadata
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


__all__ = [
    "EXPERIMENT_MATRIX_SCHEMA_VERSION",
    "EXPERIMENT_VARIANTS",
    "VARIANT_MODEL_COMPONENTS",
    "ExperimentCell",
    "ExperimentMatrixPlan",
    "ModelBundlePaths",
    "load_training_seeds",
    "paired_exogenous_config_sha256",
    "repository_state",
    "required_model_components",
    "run_experiment_matrix",
    "runtime_options_for_variant",
    "validate_required_bundles",
]
