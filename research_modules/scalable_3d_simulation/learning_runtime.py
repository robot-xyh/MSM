"""Explicit, fail-closed loading of optional scalable-3D learning bundles.

The deterministic D1-D7 path remains the default.  This module is main-owned
glue: it loads module-owned research bundles, records immutable fingerprints,
and injects only the narrow interfaces already defined by D3, D4, and D5.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .models import ScenarioConfig
from .module_stack import IntegratedScalableModuleStack, IntegratedStackConfig


_LEARNING_MODES = frozenset({"disabled", "shadow", "assist"})


@dataclass(frozen=True)
class LearningRuntimeOptions:
    """Optional model locations and requested runtime modes.

    Paths are intentionally excluded from the episode manifest.  The resolved
    model version and SHA256 fingerprint are recorded instead, so a relocated
    but identical bundle produces the same scientific configuration.
    """

    d3_mode: str = "disabled"
    d3_bundle_dir: Path | None = None
    d4_mode: str = "disabled"
    d4_bundle_dir: Path | None = None
    d5_bundle_dir: Path | None = None
    d5_active_vision_mode: str = "disabled"
    d5_active_vision_bundle_dir: Path | None = None
    device: str = "cpu"

    def __post_init__(self) -> None:
        for name in ("d3_mode", "d4_mode", "d5_active_vision_mode"):
            value = str(getattr(self, name)).strip().lower()
            if value not in _LEARNING_MODES:
                raise ValueError(f"{name} must be disabled, shadow, or assist")
            object.__setattr__(self, name, value)
        for name in (
            "d3_bundle_dir",
            "d4_bundle_dir",
            "d5_bundle_dir",
            "d5_active_vision_bundle_dir",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value))
        device = str(self.device).strip()
        if not device:
            raise ValueError("learning device must be non-empty")
        object.__setattr__(self, "device", device)

    @property
    def requested(self) -> bool:
        return bool(
            self.d3_mode != "disabled"
            or self.d4_mode != "disabled"
            or self.d5_bundle_dir is not None
            or self.d5_active_vision_mode != "disabled"
            or self.d5_active_vision_bundle_dir is not None
        )


@dataclass(frozen=True)
class ResolvedLearningRuntime:
    """Scenario and stack after deterministic bundle resolution."""

    config: ScenarioConfig
    stack: IntegratedScalableModuleStack
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class _UnavailableEdgeModel:
    failure_reason: str
    available: bool = False

    def forward_graph(self, graph: Any) -> Any:
        del graph
        raise RuntimeError(self.failure_reason)


def resolve_learning_runtime(
    config: ScenarioConfig,
    options: LearningRuntimeOptions | None = None,
    *,
    stack_config: IntegratedStackConfig | None = None,
) -> ResolvedLearningRuntime:
    """Load optional bundles and preserve exact-rule fallback on every failure."""

    selected = options or LearningRuntimeOptions()
    d3_assistant: Any | None = None
    d4_advisor: Any | None = None
    d5_edge_model: Any | None = None
    d5_active_vision_policy: Any | None = None
    d3_version = config.d3_policy_version
    d4_version = config.d4_policy_version
    d5_version = config.d5_model_version
    d5_active_vision_version = config.d5_active_vision_policy_version

    d3_diagnostics: dict[str, Any] = {
        "requested_mode": selected.d3_mode,
        "effective_mode": "disabled",
        "bundle_requested": selected.d3_bundle_dir is not None,
        "bundle_loaded": False,
        "fallback_reason": None,
        "model_fingerprint": None,
    }
    if selected.d3_mode != "disabled":
        from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
            RuleFallbackLearningAssistant,
            load_model_bundle,
        )

        if selected.d3_bundle_dir is None:
            d3_assistant = RuleFallbackLearningAssistant(
                "model_bundle_missing",
                mode=selected.d3_mode,
            )
            d3_diagnostics.update(
                effective_mode="rule_fallback",
                fallback_reason="model_bundle_missing",
            )
        else:
            result = load_model_bundle(
                selected.d3_bundle_dir,
                mode=selected.d3_mode,
                require_promotion_for_assist=True,
            )
            d3_assistant = result.assistant
            d3_diagnostics.update(
                effective_mode=(selected.d3_mode if result.loaded else "rule_fallback"),
                bundle_loaded=bool(result.loaded),
                fallback_reason=result.fallback_reason,
            )
            if result.manifest is not None:
                fingerprint = result.manifest.state_dict_sha256
                d3_diagnostics["model_fingerprint"] = fingerprint
                d3_version = (
                    f"{result.manifest.policy_version}+{fingerprint[:12]}"
                )

    d4_diagnostics: dict[str, Any] = {
        "requested_mode": selected.d4_mode,
        "effective_mode": "disabled",
        "bundle_requested": selected.d4_bundle_dir is not None,
        "bundle_loaded": False,
        "fallback_reason": None,
        "model_fingerprint": None,
        "formal_unseen_seed_count": 0,
    }
    if selected.d4_mode != "disabled":
        from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
            RegionResourceAdvisor,
            RegionResourceAdvisorConfig,
        )

        advisor_config = RegionResourceAdvisorConfig(mode=selected.d4_mode)
        if (
            selected.d4_bundle_dir is None
            or not selected.d4_bundle_dir.is_dir()
        ):
            d4_advisor = RegionResourceAdvisor(
                config=advisor_config,
                bundle_error="model_bundle_missing",
            )
        else:
            d4_advisor = RegionResourceAdvisor.from_bundle(
                selected.d4_bundle_dir,
                config=advisor_config,
            )
        learned_policy = getattr(d4_advisor, "learned_policy", None)
        manifest = getattr(learned_policy, "manifest", None)
        bundle_error = getattr(d4_advisor, "bundle_error", None)
        d4_diagnostics.update(
            effective_mode="pending_runtime_shadow_gate",
            bundle_loaded=manifest is not None,
            fallback_reason=(
                None if manifest is not None else str(bundle_error or "model_unavailable")
            ),
        )
        if manifest is not None:
            fingerprint = str(manifest.state_dict_sha256)
            d4_diagnostics["model_fingerprint"] = fingerprint
            d4_version = f"{manifest.model_version}+{fingerprint[:12]}"

    d5_diagnostics: dict[str, Any] = {
        "requested_mode": "assist" if selected.d5_bundle_dir is not None else "disabled",
        "effective_mode": "disabled",
        "bundle_requested": selected.d5_bundle_dir is not None,
        "bundle_loaded": False,
        "fallback_reason": None,
        "model_fingerprint": None,
    }
    if selected.d5_bundle_dir is not None:
        try:
            from research_modules.d5_terminal_association.src.d5_terminal_association.tracklet_model_bundle import (
                load_tracklet_model_bundle_for_runtime,
            )

            d5_edge_model = load_tracklet_model_bundle_for_runtime(
                selected.d5_bundle_dir,
                device=selected.device,
            )
        except Exception as exc:
            d5_edge_model = _UnavailableEdgeModel(
                failure_reason=f"bundle_import_{type(exc).__name__}"
            )
        available = getattr(d5_edge_model, "available", False) is True
        reason = None if available else str(
            getattr(d5_edge_model, "failure_reason", "model_unavailable")
        )
        d5_diagnostics.update(
            effective_mode="assist" if available else "rule_fallback",
            bundle_loaded=available,
            fallback_reason=reason,
        )
        if available:
            fingerprint = str(d5_edge_model.bundle_weights_sha256)
            d5_diagnostics["model_fingerprint"] = fingerprint
            semantic_version = str(
                d5_edge_model.manifest.get("model_semantic_version", "unknown")
            )
            d5_version = f"d5-crossview-gnn-v{semantic_version}+{fingerprint[:12]}"

    d5_active_vision_diagnostics: dict[str, Any] = {
        "requested_mode": selected.d5_active_vision_mode,
        "effective_mode": "disabled",
        "bundle_requested": selected.d5_active_vision_bundle_dir is not None,
        "bundle_loaded": False,
        "assist_admitted": False,
        "fallback_reason": None,
        "model_semantic_version": None,
        "model_fingerprint": None,
        "bundle_manifest_sha256": None,
        "bundle_weights_sha256": None,
    }
    if (
        selected.d5_active_vision_mode != "disabled"
        or selected.d5_active_vision_bundle_dir is not None
    ):
        from research_modules.d5_terminal_association.src.d5_terminal_association import (
            UnavailableActiveVisionPolicy,
            load_active_vision_model_bundle_for_runtime,
        )

        if selected.d5_active_vision_bundle_dir is None:
            d5_active_vision_policy = UnavailableActiveVisionPolicy(
                failure_reason="model_bundle_missing"
            )
        else:
            d5_active_vision_policy = load_active_vision_model_bundle_for_runtime(
                selected.d5_active_vision_bundle_dir,
                device=selected.device,
            )
        available = bool(getattr(d5_active_vision_policy, "available", False))
        admitted = bool(
            getattr(d5_active_vision_policy, "assist_admitted", False)
        )
        fallback_reason = None
        if not available:
            fallback_reason = str(
                getattr(
                    d5_active_vision_policy,
                    "failure_reason",
                    "model_unavailable",
                )
            )
        elif selected.d5_active_vision_mode == "assist" and not admitted:
            fallback_reason = "assist_not_admitted"
        effective_mode = selected.d5_active_vision_mode
        if fallback_reason is not None:
            effective_mode = "rule_fallback"
        elif selected.d5_active_vision_mode == "disabled":
            effective_mode = "disabled"
        d5_active_vision_diagnostics.update(
            effective_mode=effective_mode,
            bundle_loaded=available,
            assist_admitted=admitted,
            fallback_reason=fallback_reason,
        )
        if available:
            manifest = getattr(d5_active_vision_policy, "manifest", {})
            semantic_version = str(
                manifest.get("model_semantic_version", "unknown")
            )
            fingerprint = str(d5_active_vision_policy.model_fingerprint)
            d5_active_vision_diagnostics.update(
                model_semantic_version=semantic_version,
                model_fingerprint=fingerprint,
                bundle_manifest_sha256=str(
                    d5_active_vision_policy.bundle_manifest_sha256
                ),
                bundle_weights_sha256=str(
                    d5_active_vision_policy.bundle_weights_sha256
                ),
            )
            d5_active_vision_version = (
                f"d5-active-vision-v{semantic_version}+"
                f"{fingerprint.removeprefix('sha256:')[:12]}"
            )

    diagnostics = {
        "schema_version": "scalable3d-learning-runtime-v1",
        "device": selected.device,
        "d3": d3_diagnostics,
        "d4": d4_diagnostics,
        "d5": d5_diagnostics,
        "d5_active_vision": d5_active_vision_diagnostics,
        "default_rule_path_preserved": True,
    }
    metadata = dict(config.metadata)
    metadata["learning_runtime"] = diagnostics
    resolved_config = replace(
        config,
        d3_policy_version=d3_version,
        d4_policy_version=d4_version,
        d5_model_version=d5_version,
        d5_active_vision_policy_version=d5_active_vision_version,
        metadata=metadata,
    )
    resolved_stack_config = replace(
        stack_config or IntegratedStackConfig(),
        d5_active_vision_mode=selected.d5_active_vision_mode,
    )
    stack = IntegratedScalableModuleStack(
        config=resolved_stack_config,
        d3_learning_assistant=d3_assistant,
        d4_region_advisor=d4_advisor,
        d4_unseen_seed_count=0,
        d5_edge_model=d5_edge_model,
        d5_active_vision_policy=d5_active_vision_policy,
        learning_runtime_diagnostics=diagnostics,
    )
    return ResolvedLearningRuntime(
        config=resolved_config,
        stack=stack,
        diagnostics=diagnostics,
    )


def add_learning_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    """Add identical optional-learning arguments to episode and batch CLIs."""

    parser.add_argument(
        "--d3-learning-mode",
        choices=tuple(sorted(_LEARNING_MODES)),
        default="disabled",
    )
    parser.add_argument("--d3-model-bundle", type=Path)
    parser.add_argument(
        "--d4-learning-mode",
        choices=tuple(sorted(_LEARNING_MODES)),
        default="disabled",
    )
    parser.add_argument("--d4-model-bundle", type=Path)
    parser.add_argument("--d5-model-bundle", type=Path)
    parser.add_argument(
        "--d5-active-vision-mode",
        choices=tuple(sorted(_LEARNING_MODES)),
        default="disabled",
    )
    parser.add_argument("--d5-active-vision-bundle", type=Path)
    parser.add_argument("--learning-device", default="cpu")


def learning_runtime_options_from_args(args: argparse.Namespace) -> LearningRuntimeOptions:
    return LearningRuntimeOptions(
        d3_mode=args.d3_learning_mode,
        d3_bundle_dir=args.d3_model_bundle,
        d4_mode=args.d4_learning_mode,
        d4_bundle_dir=args.d4_model_bundle,
        d5_bundle_dir=args.d5_model_bundle,
        d5_active_vision_mode=args.d5_active_vision_mode,
        d5_active_vision_bundle_dir=args.d5_active_vision_bundle,
        device=args.learning_device,
    )


__all__ = [
    "LearningRuntimeOptions",
    "ResolvedLearningRuntime",
    "add_learning_runtime_arguments",
    "learning_runtime_options_from_args",
    "resolve_learning_runtime",
]
