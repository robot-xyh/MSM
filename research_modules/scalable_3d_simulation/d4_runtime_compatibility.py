"""Development preflight for D4 regional-policy runtime compatibility.

The preflight separates two questions that must not be conflated:

* whether a model bundle can be loaded and fingerprinted; and
* whether truth-free snapshots produced by the integrated runtime fall inside
  the feature support recorded by that bundle.

It never widens D4 out-of-distribution bounds, changes the deterministic
projector, or grants assist/adoption permissions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    EDGE_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN,
    RegionFeatureBounds,
    snapshot_to_region_graph,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_eight_region_candidate import (
    REGION_RESOURCE_EIGHT_REGION_CANDIDATE_FILENAME,
    load_region_resource_eight_region_candidate_manifest,
)

from .experiment_authorization import sha256_file
from .learning_runtime import LearningRuntimeOptions, resolve_learning_runtime
from .models import ScenarioConfig
from .module_stack import D4RegionLearningFrame, IntegratedStackConfig
from .orchestrator import run_episode


D4_RUNTIME_COMPATIBILITY_PREFLIGHT_SCHEMA_VERSION = (
    "scalable3d-d4-runtime-compatibility-preflight-v1"
)
DEFAULT_FORMAL_SEED_REGISTRY = (
    Path(__file__).with_name("configs")
    / "formal_evaluation_seed_registry_v1.json"
)


@dataclass(frozen=True)
class D4RuntimeCompatibilityThresholds:
    """Minimum evidence required before a paired A2 development rollout."""

    minimum_frame_count: int = 2
    minimum_in_distribution_fraction: float = 0.80
    minimum_model_evaluated_frame_count: int = 1
    ood_margin: float = REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN

    def __post_init__(self) -> None:
        if int(self.minimum_frame_count) <= 0:
            raise ValueError("minimum_frame_count must be positive")
        if not 0.0 <= float(self.minimum_in_distribution_fraction) <= 1.0:
            raise ValueError(
                "minimum_in_distribution_fraction must be in [0, 1]"
            )
        if int(self.minimum_model_evaluated_frame_count) <= 0:
            raise ValueError(
                "minimum_model_evaluated_frame_count must be positive"
            )
        if (
            not np.isfinite(float(self.ood_margin))
            or float(self.ood_margin)
            != REGION_RESOURCE_DEVELOPMENT_OOD_MARGIN
        ):
            raise ValueError("ood_margin must remain fixed at 0.05")


@dataclass(frozen=True)
class D4RuntimeCompatibilityOptions:
    """Bounded development-run configuration for the main-owned preflight."""

    config_path: Path
    bundle_dir: Path
    output_dir: Path
    seeds: tuple[int, ...] = (2_000,)
    duration_s: float = 2.2
    target_count: int | None = 5
    resource_count: int | None = 5
    recon_count: int | None = 2
    region_count: int | None = 2
    thresholds: D4RuntimeCompatibilityThresholds = (
        D4RuntimeCompatibilityThresholds()
    )
    formal_seed_registry_path: Path = DEFAULT_FORMAL_SEED_REGISTRY
    allow_reserved_evaluation_seeds: bool = False

    def __post_init__(self) -> None:
        for name in (
            "config_path",
            "bundle_dir",
            "output_dir",
            "formal_seed_registry_path",
        ):
            object.__setattr__(self, name, Path(getattr(self, name)))
        seeds = tuple(int(seed) for seed in self.seeds)
        if not seeds or len(set(seeds)) != len(seeds):
            raise ValueError("seeds must be non-empty and unique")
        object.__setattr__(self, "seeds", seeds)
        if not np.isfinite(float(self.duration_s)) or self.duration_s <= 0.0:
            raise ValueError("duration_s must be finite and positive")
        for name in (
            "target_count",
            "resource_count",
            "region_count",
        ):
            value = getattr(self, name)
            if value is not None and int(value) <= 0:
                raise ValueError(f"{name} must be positive when provided")
        if self.recon_count is not None and int(self.recon_count) < 0:
            raise ValueError("recon_count must be non-negative when provided")


def _resolve_d4_model_input(
    source: str | Path,
) -> tuple[Path, dict[str, Any] | None]:
    """Resolve either a raw bundle or an audited eight-region candidate."""

    root = Path(source).expanduser().resolve()
    raw_manifest = root / "manifest.json"
    if raw_manifest.is_file():
        return root, None

    candidate_manifest_path = (
        root / REGION_RESOURCE_EIGHT_REGION_CANDIDATE_FILENAME
    )
    if not candidate_manifest_path.is_file():
        raise ValueError(
            "D4 model input must be a bundle directory or an audited "
            f"candidate root: {root}"
        )
    manifest = load_region_resource_eight_region_candidate_manifest(root)
    bundle_dir = root / "bundle"
    if not (bundle_dir / "manifest.json").is_file():
        raise ValueError(f"D4 candidate bundle is unavailable: {bundle_dir}")
    return bundle_dir, {
        "candidate_root": str(root),
        "candidate_id": manifest.candidate_id,
        "model_version": manifest.model_version,
        "model_state_sha256": manifest.model_state_sha256,
        "manifest_file_sha256": sha256_file(candidate_manifest_path),
        "manifest_content_sha256": manifest.content_sha256,
        "source_identity_sha256": manifest.source_identity_sha256,
        "source_summary_file_sha256": (
            manifest.source_summary_file_sha256
        ),
        "applicable_region_count": manifest.applicable_region_count,
        "confidence_calibration_accepted": (
            manifest.confidence_calibration_accepted
        ),
        "validation_confidence_brier": (
            manifest.validation_confidence_brier
        ),
        "validation_action_inconsistent_threshold_pass_count": (
            manifest.validation_action_inconsistent_threshold_pass_count
        ),
        "read_only_shadow": manifest.read_only_shadow,
        "runtime_preflight_completed": manifest.runtime_preflight_completed,
        "formal_evaluation_authorized": (
            manifest.permissions.formal_evaluation_authorized
        ),
        "permissions": manifest.permissions.to_dict(),
    }


def assess_d4_runtime_compatibility(
    frames: Sequence[D4RegionLearningFrame] | Sequence[Any],
    *,
    feature_bounds: RegionFeatureBounds,
    model_version: str,
    model_sha256: str,
    thresholds: D4RuntimeCompatibilityThresholds | None = None,
    bundle_metadata: Mapping[str, Any] | None = None,
    online_truth_use_count: int = 0,
) -> dict[str, Any]:
    """Compare integrated D4 snapshots with immutable bundle feature bounds."""

    selected = thresholds or D4RuntimeCompatibilityThresholds()
    frame_values = tuple(frames)
    feature_rows = {
        "node": _empty_feature_rows(
            NODE_FEATURE_NAMES,
            feature_bounds.node_min,
            feature_bounds.node_max,
        ),
        "edge": _empty_feature_rows(
            EDGE_FEATURE_NAMES,
            feature_bounds.edge_min,
            feature_bounds.edge_max,
        ),
    }
    in_distribution_count = 0
    nonfinite_frame_count = 0
    model_evaluated_count = 0
    formal_decision_changed_count = 0
    gate_disagreement_count = 0
    fallback_reasons: Counter[str] = Counter()
    recommendation_sources: Counter[str] = Counter()
    per_frame: list[dict[str, Any]] = []

    for frame in frame_values:
        graph = snapshot_to_region_graph(frame.snapshot, device="cpu")
        node_values = graph.node_features.detach().cpu().numpy()
        edge_values = graph.edge_features.detach().cpu().numpy()
        finite = bool(
            np.isfinite(node_values).all()
            and (not edge_values.size or np.isfinite(edge_values).all())
        )
        if not finite:
            nonfinite_frame_count += 1
        node_inside = _accumulate_feature_diagnostics(
            feature_rows["node"],
            node_values,
            margin=selected.ood_margin,
        )
        edge_inside = _accumulate_feature_diagnostics(
            feature_rows["edge"],
            edge_values,
            margin=selected.ood_margin,
        )
        computed_inside = finite and node_inside and edge_inside
        if computed_inside:
            in_distribution_count += 1

        advice = frame.recommendation
        fallback_used = bool(getattr(advice, "fallback_used", False))
        fallback_reason_value = getattr(advice, "fallback_reason", None)
        fallback_reason = (
            None
            if fallback_reason_value is None
            else str(fallback_reason_value)
        )
        if fallback_reason:
            fallback_reasons[fallback_reason] += 1
        recommendation = getattr(advice, "recommendation", None)
        source_value = getattr(recommendation, "source", None)
        source = str(getattr(source_value, "value", source_value or "none"))
        recommendation_sources[source] += 1
        model_sha = getattr(recommendation, "model_sha256", None)
        model_evaluated = bool(
            not fallback_used
            and source == "learned"
            and str(model_sha) == str(model_sha256)
        )
        if model_evaluated:
            model_evaluated_count += 1
        unchanged = bool(
            getattr(advice, "formal_decision_unchanged", False)
        )
        if not unchanged:
            formal_decision_changed_count += 1
        advisor_feature_ood = fallback_reason == "feature_ood"
        if advisor_feature_ood != (not computed_inside):
            gate_disagreement_count += 1
        per_frame.append(
            {
                "frame_index": int(getattr(frame, "frame_index", len(per_frame))),
                "timestamp_s": float(getattr(frame, "timestamp_s", 0.0)),
                "snapshot_id": str(frame.snapshot.snapshot_id),
                "node_count": int(graph.node_count),
                "edge_count": int(graph.edge_count),
                "feature_in_distribution": computed_inside,
                "advisor_feature_ood": advisor_feature_ood,
                "fallback_used": fallback_used,
                "fallback_reason": fallback_reason,
                "recommendation_source": source,
                "model_evaluated": model_evaluated,
                "formal_decision_unchanged": unchanged,
            }
        )

    frame_count = len(frame_values)
    in_distribution_fraction = (
        in_distribution_count / frame_count if frame_count else 0.0
    )
    blockers: list[str] = []
    if frame_count < selected.minimum_frame_count:
        blockers.append("insufficient_runtime_frames")
    if nonfinite_frame_count:
        blockers.append("nonfinite_runtime_features")
    if (
        in_distribution_fraction
        < selected.minimum_in_distribution_fraction
    ):
        blockers.append("runtime_feature_distribution_mismatch")
    if (
        model_evaluated_count
        < selected.minimum_model_evaluated_frame_count
    ):
        blockers.append("no_nonfallback_model_evaluation")
    if formal_decision_changed_count:
        blockers.append("formal_d4_decision_changed")
    if gate_disagreement_count:
        blockers.append("advisor_preflight_ood_gate_disagreement")
    if int(online_truth_use_count) != 0:
        blockers.append("online_truth_use_nonzero")

    metadata = dict(bundle_metadata or {})
    feature_diagnostics = {
        group: _finalize_feature_rows(rows)
        for group, rows in feature_rows.items()
    }
    top_violations = sorted(
        (
            {
                "group": group,
                **row,
            }
            for group, rows in feature_diagnostics.items()
            for row in rows
            if int(row["out_of_bounds_value_count"]) > 0
        ),
        key=lambda row: (
            -int(row["out_of_bounds_value_count"]),
            str(row["group"]),
            str(row["feature_name"]),
        ),
    )
    return {
        "schema_version": D4_RUNTIME_COMPATIBILITY_PREFLIGHT_SCHEMA_VERSION,
        "model_version": str(model_version),
        "model_sha256": str(model_sha256),
        "bundle_lifecycle_stage": metadata.get("lifecycle_stage"),
        "bundle_maximum_advisor_mode": metadata.get(
            "maximum_advisor_mode"
        ),
        "bundle_action_diversity_sufficient": bool(
            metadata.get("action_diversity_sufficient", False)
        ),
        "bundle_strategy_capability_claim_allowed": bool(
            metadata.get("strategy_capability_claim_allowed", False)
        ),
        "thresholds": asdict(selected),
        "frame_count": frame_count,
        "in_distribution_frame_count": in_distribution_count,
        "in_distribution_fraction": in_distribution_fraction,
        "nonfinite_frame_count": nonfinite_frame_count,
        "model_evaluated_frame_count": model_evaluated_count,
        "formal_decision_changed_count": formal_decision_changed_count,
        "ood_gate_disagreement_count": gate_disagreement_count,
        "fallback_reason_counts": dict(sorted(fallback_reasons.items())),
        "recommendation_source_counts": dict(
            sorted(recommendation_sources.items())
        ),
        "online_truth_use_count": int(online_truth_use_count),
        "feature_diagnostics": feature_diagnostics,
        "top_feature_violations": top_violations,
        "frames": per_frame,
        "runtime_distribution_compatible": not blockers,
        "paired_development_rollout_allowed": not blockers,
        "assist_or_strategy_claim_granted": False,
        "blockers": blockers,
    }


def _apply_candidate_runtime_gate(
    compatibility: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None,
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Keep raw bundle compatibility separate from candidate permission."""

    result = dict(compatibility)
    raw_model_count = int(result["model_evaluated_frame_count"])
    result["raw_bundle_model_evaluated_frame_count"] = raw_model_count
    if candidate is None:
        result.update(
            candidate_gate_available=False,
            candidate_scope_compatible=None,
            candidate_confidence_calibration_accepted=None,
            candidate_permitted_model_evaluated_frame_count=None,
            candidate_blockers=[],
        )
        return result

    applicable_region_count = int(candidate["applicable_region_count"])
    observed_region_counts = sorted(
        {int(case["region_count"]) for case in cases}
    )
    scope_compatible = bool(
        observed_region_counts
        and observed_region_counts == [applicable_region_count]
    )
    calibration_accepted = bool(
        candidate["confidence_calibration_accepted"]
    )
    candidate_blockers: list[str] = []
    if not scope_compatible:
        candidate_blockers.append("candidate_region_count_out_of_scope")
    if not calibration_accepted:
        candidate_blockers.append(
            "candidate_confidence_calibration_not_accepted"
        )
    if candidate.get("read_only_shadow") is not True:
        candidate_blockers.append("candidate_not_read_only_shadow")
    permissions = candidate.get("permissions")
    permission_values = (
        {
            key: value
            for key, value in permissions.items()
            if key != "schema"
        }
        if isinstance(permissions, Mapping)
        else {}
    )
    if (
        not isinstance(permissions, Mapping)
        or not isinstance(permissions.get("schema"), str)
        or not permission_values
        or any(value is not False for value in permission_values.values())
    ):
        candidate_blockers.append("candidate_permission_boundary_crossed")

    candidate_permitted_count = (
        raw_model_count if not candidate_blockers else 0
    )
    result.update(
        candidate_gate_available=True,
        candidate_scope_compatible=scope_compatible,
        candidate_applicable_region_count=applicable_region_count,
        observed_region_counts=observed_region_counts,
        candidate_confidence_calibration_accepted=calibration_accepted,
        candidate_permitted_model_evaluated_frame_count=(
            candidate_permitted_count
        ),
        candidate_blockers=candidate_blockers,
        paired_development_rollout_allowed=bool(
            result["runtime_distribution_compatible"]
            and not candidate_blockers
            and candidate_permitted_count
            >= int(
                result["thresholds"][
                    "minimum_model_evaluated_frame_count"
                ]
            )
        ),
    )
    return result


def run_d4_runtime_compatibility_preflight(
    options: D4RuntimeCompatibilityOptions,
) -> dict[str, Path]:
    """Run bounded development episodes and write one compatibility decision."""

    reserved_seeds, registry_sha256 = _load_reserved_evaluation_seeds(
        options.formal_seed_registry_path
    )
    overlap = tuple(sorted(set(options.seeds) & reserved_seeds))
    if overlap and not options.allow_reserved_evaluation_seeds:
        raise ValueError(
            "development preflight refuses reserved evaluation seeds: "
            + ", ".join(str(seed) for seed in overlap)
        )
    base = ScenarioConfig.from_dict(
        json.loads(options.config_path.read_text(encoding="utf-8"))
    )
    model_input = options.bundle_dir.expanduser().resolve()
    if not model_input.is_dir():
        raise ValueError(f"D4 model input directory does not exist: {model_input}")
    bundle_dir, candidate_metadata = _resolve_d4_model_input(model_input)

    all_frames: list[D4RegionLearningFrame] = []
    cases: list[dict[str, Any]] = []
    runtime_diagnostics: dict[str, Any] | None = None
    learned_manifest: Any | None = None
    online_truth_use_count = 0
    for seed in options.seeds:
        config = replace(
            base,
            scenario_name="d4_runtime_compatibility_preflight",
            scenario_version="d4-runtime-compatibility-preflight-v1",
            seed=int(seed),
            duration_s=float(options.duration_s),
            target_count=(
                base.target_count
                if options.target_count is None
                else int(options.target_count)
            ),
            resource_count=(
                base.resource_count
                if options.resource_count is None
                else int(options.resource_count)
            ),
            recon_count=(
                base.recon_count
                if options.recon_count is None
                else int(options.recon_count)
            ),
            region_count=(
                base.region_count
                if options.region_count is None
                else int(options.region_count)
            ),
        )
        resolved = resolve_learning_runtime(
            config,
            LearningRuntimeOptions(
                d4_mode="shadow",
                d4_bundle_dir=bundle_dir,
                device="cpu",
            ),
            stack_config=IntegratedStackConfig(
                capture_learning_artifacts=True
            ),
        )
        d4_diagnostics = dict(resolved.diagnostics["d4"])
        if not d4_diagnostics.get("bundle_loaded", False):
            raise ValueError(
                "D4 bundle failed to load: "
                + str(d4_diagnostics.get("fallback_reason"))
            )
        policy = getattr(resolved.stack.d4_region_advisor, "learned_policy", None)
        manifest = getattr(policy, "manifest", None)
        if manifest is None:
            raise ValueError("loaded D4 advisor does not expose a model manifest")
        if learned_manifest is None:
            learned_manifest = manifest
            runtime_diagnostics = d4_diagnostics
        elif (
            manifest.state_dict_sha256
            != learned_manifest.state_dict_sha256
        ):
            raise RuntimeError("D4 model changed during compatibility preflight")

        result = run_episode(resolved.config, module_stack=resolved.stack)
        artifacts = resolved.stack.learning_artifacts()
        frame_values = tuple(artifacts.d4_region_frames)
        all_frames.extend(frame_values)
        case_fallbacks = Counter(
            str(frame.recommendation.fallback_reason)
            for frame in frame_values
            if frame.recommendation.fallback_reason is not None
        )
        case_model_count = sum(
            not frame.recommendation.fallback_used
            and frame.recommendation.recommendation is not None
            and frame.recommendation.recommendation.source.value == "learned"
            for frame in frame_values
        )
        truth_count = int(result.summary["online_truth_use_count"])
        online_truth_use_count += truth_count
        cases.append(
            {
                "seed": int(seed),
                "episode_id": result.manifest.episode_id,
                "config_sha256": result.manifest.config_sha256,
                "target_count": config.target_count,
                "resource_count": config.resource_count,
                "recon_count": config.recon_count,
                "region_count": config.region_count,
                "duration_s": config.duration_s,
                "d4_frame_count": len(frame_values),
                "model_evaluated_frame_count": case_model_count,
                "fallback_reason_counts": dict(sorted(case_fallbacks.items())),
                "online_truth_use_count": truth_count,
                "finite_state": bool(result.summary["finite_state"]),
            }
        )

    assert learned_manifest is not None
    if (
        candidate_metadata is not None
        and (
            learned_manifest.model_version
            != candidate_metadata["model_version"]
            or learned_manifest.state_dict_sha256
            != candidate_metadata["model_state_sha256"]
        )
    ):
        raise RuntimeError(
            "D4 candidate manifest does not match the loaded bundle"
        )
    compatibility = assess_d4_runtime_compatibility(
        all_frames,
        feature_bounds=learned_manifest.feature_bounds,
        model_version=learned_manifest.model_version,
        model_sha256=learned_manifest.state_dict_sha256,
        thresholds=options.thresholds,
        bundle_metadata=learned_manifest.to_dict(),
        online_truth_use_count=online_truth_use_count,
    )
    compatibility = _apply_candidate_runtime_gate(
        compatibility,
        candidate=candidate_metadata,
        cases=cases,
    )
    repository_root = Path(__file__).resolve().parents[2]
    payload = {
        "schema_version": D4_RUNTIME_COMPATIBILITY_PREFLIGHT_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "evidence_tier": "development_preflight",
        "git_commit": _git_output(repository_root, "rev-parse", "HEAD"),
        "repository_dirty": bool(
            _git_output(repository_root, "status", "--porcelain").strip()
        ),
        "model_input": str(model_input),
        "bundle_dir": str(bundle_dir),
        "bundle_manifest_sha256": sha256_file(
            bundle_dir / "manifest.json"
        ),
        "candidate": candidate_metadata,
        "learning_runtime_diagnostics": runtime_diagnostics,
        "formal_seed_registry": {
            "path": str(options.formal_seed_registry_path),
            "sha256": registry_sha256,
            "reserved_seed_overlap": list(overlap),
            "reserved_seed_override_used": bool(
                overlap and options.allow_reserved_evaluation_seeds
            ),
        },
        "cases": cases,
        "compatibility": compatibility,
        "evidence_boundary": {
            "simulation_mode": "three_dimensional_point_mass",
            "online_truth_is_control_input": False,
            "d4_mode": "shadow",
            "ood_margin_changed": False,
            "deterministic_projector_changed": False,
            "assist_permission_granted": False,
            "formal_evaluation_authorized": False,
        },
    }
    output_dir = options.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "d4_runtime_compatibility_preflight.json"
    report_path = output_dir / "D4_RUNTIME_COMPATIBILITY_PREFLIGHT_CN.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        _render_chinese_report(payload),
        encoding="utf-8",
    )
    return {
        "preflight_json": json_path,
        "report": report_path,
    }


def _empty_feature_rows(
    names: Sequence[str],
    minima: Sequence[float],
    maxima: Sequence[float],
) -> list[dict[str, Any]]:
    return [
        {
            "feature_name": str(name),
            "training_min": float(low),
            "training_max": float(high),
            "observed_min": None,
            "observed_max": None,
            "value_count": 0,
            "below_count": 0,
            "above_count": 0,
        }
        for name, low, high in zip(names, minima, maxima)
    ]


def _accumulate_feature_diagnostics(
    rows: list[dict[str, Any]],
    values: np.ndarray,
    *,
    margin: float,
) -> bool:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return True
    array = array.reshape((-1, len(rows)))
    all_inside = True
    for index, row in enumerate(rows):
        column = array[:, index]
        low = float(row["training_min"])
        high = float(row["training_max"])
        tolerance = float(margin) * max(abs(low), abs(high), 1.0)
        below = int(np.count_nonzero(column < low - tolerance))
        above = int(np.count_nonzero(column > high + tolerance))
        all_inside = all_inside and below == 0 and above == 0
        observed_min = float(np.min(column))
        observed_max = float(np.max(column))
        row["observed_min"] = (
            observed_min
            if row["observed_min"] is None
            else min(float(row["observed_min"]), observed_min)
        )
        row["observed_max"] = (
            observed_max
            if row["observed_max"] is None
            else max(float(row["observed_max"]), observed_max)
        )
        row["value_count"] = int(row["value_count"]) + int(column.size)
        row["below_count"] = int(row["below_count"]) + below
        row["above_count"] = int(row["above_count"]) + above
    return all_inside


def _finalize_feature_rows(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        row["out_of_bounds_value_count"] = int(row["below_count"]) + int(
            row["above_count"]
        )
        finalized.append(row)
    return finalized


def _load_reserved_evaluation_seeds(
    registry_path: Path,
) -> tuple[set[int], str]:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    seeds = {int(seed) for seed in payload["evaluation_seeds"]}
    return seeds, sha256_file(registry_path)


def _git_output(repository_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _render_chinese_report(payload: Mapping[str, Any]) -> str:
    compatibility = payload["compatibility"]
    distribution_ready = bool(
        compatibility["runtime_distribution_compatible"]
    )
    rollout_allowed = bool(
        compatibility["paired_development_rollout_allowed"]
    )
    candidate_gate_available = bool(
        compatibility["candidate_gate_available"]
    )
    if rollout_allowed:
        conclusion = "当前候选可进入受控的成对开发试验。"
    elif distribution_ready and candidate_gate_available:
        conclusion = (
            "原始模型包通过运行分布检查，但候选级门控未通过，"
            "不得启动正式多随机种子成对试验。"
        )
    else:
        conclusion = (
            "当前模型未通过运行分布预检，不应启动正式多随机种子"
            "成对试验。"
        )
    lines = [
        "# D4 区域策略运行分布兼容性预检",
        "",
        "## 结论",
        "",
        conclusion,
        (
            f"共检查 {compatibility['frame_count']} 个 D4 区域快照，"
            f"分布内快照 {compatibility['in_distribution_frame_count']} 个，"
            "原始模型前向有效执行 "
            f"{compatibility['raw_bundle_model_evaluated_frame_count']} 次，"
            "候选门控许可执行 "
            f"{compatibility['candidate_permitted_model_evaluated_frame_count']} 次。"
        ),
        "本预检不授予在线辅助、策略能力声明或正式评估权限。",
        "",
        "## 运行分布阻断项",
        "",
    ]
    blockers = list(compatibility["blockers"])
    lines.extend(
        ["- 无。" if not blockers else ""]
        if not blockers
        else [f"- `{item}`" for item in blockers]
    )
    lines.extend(["", "## 候选门控阻断项", ""])
    candidate_blockers = list(compatibility["candidate_blockers"])
    if not candidate_gate_available:
        lines.append("- 未提供候选级审计清单，仅完成裸模型包检查。")
    elif candidate_blockers:
        lines.extend(f"- `{item}`" for item in candidate_blockers)
    else:
        lines.append("- 无。")
    lines.extend(
        [
            "",
            "## 运行结果",
            "",
            "| 项目 | 结果 |",
            "| --- | ---: |",
            f"| 运行快照数 | {compatibility['frame_count']} |",
            (
                "| 分布内比例 | "
                f"{100.0 * compatibility['in_distribution_fraction']:.1f}% |"
            ),
            (
                "| 原始模型前向有效执行数 | "
                f"{compatibility['raw_bundle_model_evaluated_frame_count']} |"
            ),
            (
                "| 候选门控许可执行数 | "
                f"{compatibility['candidate_permitted_model_evaluated_frame_count']} |"
            ),
            (
                "| 非有限特征帧数 | "
                f"{compatibility['nonfinite_frame_count']} |"
            ),
            (
                "| 在线真值使用数 | "
                f"{compatibility['online_truth_use_count']} |"
            ),
            "",
            "## 主要越界特征",
            "",
            "| 特征组 | 特征 | 训练范围 | 运行范围 | 越界值数 |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    violations = list(compatibility["top_feature_violations"])
    if violations:
        for row in violations[:12]:
            lines.append(
                "| {group} | `{feature_name}` | {training_min:.6g} 至 "
                "{training_max:.6g} | {observed_min:.6g} 至 "
                "{observed_max:.6g} | {out_of_bounds_value_count} |".format(
                    **row
                )
            )
    else:
        lines.append("| - | 无 | - | - | 0 |")
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            "- 数据来自三维质点主运行时的匿名在线状态，真值不进入 D4 控制输入。",
            "- 预检沿用模型清单中的特征边界和 D4 默认越界余量。",
            "- 确定性资源投影、版本门控和规则回退保持不变。",
            "- 裸模型前向结果与候选级执行许可分开记录。",
            "- 结果不回答策略收益和部署适用性。",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "D4_RUNTIME_COMPATIBILITY_PREFLIGHT_SCHEMA_VERSION",
    "D4RuntimeCompatibilityOptions",
    "D4RuntimeCompatibilityThresholds",
    "assess_d4_runtime_compatibility",
    "run_d4_runtime_compatibility_preflight",
]
