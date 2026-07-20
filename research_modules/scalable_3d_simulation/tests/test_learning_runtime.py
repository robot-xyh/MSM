from __future__ import annotations

from pathlib import Path

from research_modules.scalable_3d_simulation.episode_bus import build_episode_manifest
from research_modules.scalable_3d_simulation.learning_runtime import (
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.orchestrator import run_episode


def _short_integrated_config() -> ScenarioConfig:
    return ScenarioConfig(
        scenario_name="learning_runtime_smoke",
        scenario_version="learning-runtime-smoke-v1",
        seed=31,
        target_count=5,
        resource_count=5,
        recon_count=2,
        region_count=2,
        duration_s=1.2,
        acoustic_enabled=False,
    )


def test_default_resolution_preserves_rule_versions_and_disabled_models() -> None:
    config = _short_integrated_config()
    resolved = resolve_learning_runtime(config)

    assert resolved.config.d3_policy_version == config.d3_policy_version
    assert resolved.config.d4_policy_version == config.d4_policy_version
    assert resolved.config.d5_model_version == config.d5_model_version
    assert resolved.stack.d3_learning_assistant is None
    assert resolved.stack.d4_region_advisor is None
    assert resolved.stack.d5_edge_model is None
    assert resolved.diagnostics["default_rule_path_preserved"] is True
    assert resolved.diagnostics["d3"]["effective_mode"] == "disabled"
    assert resolved.diagnostics["d4"]["effective_mode"] == "disabled"
    assert resolved.diagnostics["d5"]["effective_mode"] == "disabled"

    manifest = build_episode_manifest(resolved.config)
    assert manifest.d4_policy_version == "d4-region-resource-rule-v1"
    assert resolved.config.metadata["learning_runtime"] == resolved.diagnostics


def test_missing_bundles_fall_back_and_d4_assist_cannot_self_promote(
    tmp_path: Path,
) -> None:
    options = LearningRuntimeOptions(
        d3_mode="shadow",
        d3_bundle_dir=tmp_path / "missing-d3",
        d4_mode="assist",
        d4_bundle_dir=tmp_path / "missing-d4",
        d5_bundle_dir=tmp_path / "missing-d5",
    )
    resolved = resolve_learning_runtime(_short_integrated_config(), options)

    assert resolved.diagnostics["d3"]["effective_mode"] == "rule_fallback"
    assert resolved.diagnostics["d3"]["fallback_reason"] == "model_bundle_missing"
    assert resolved.diagnostics["d4"]["bundle_loaded"] is False
    assert "model_bundle_missing" in resolved.diagnostics["d4"]["fallback_reason"]
    assert resolved.diagnostics["d4"]["formal_unseen_seed_count"] == 0
    assert resolved.diagnostics["d5"]["effective_mode"] == "rule_fallback"
    assert resolved.config.d3_policy_version.endswith("rule-cost-v1")
    assert resolved.config.d4_policy_version.endswith("rule-v1")
    assert resolved.config.d5_model_version.endswith("geometry-rule-v1")

    result = run_episode(resolved.config, module_stack=resolved.stack)
    d3_messages = tuple(
        item for item in result.online_messages if item.topic == "modules.d3.assignment_plan"
    )
    d4_advice_messages = tuple(
        item
        for item in result.online_messages
        if item.topic == "modules.d4.region_resource_advice"
    )
    d5_messages = tuple(
        item
        for item in result.online_messages
        if item.topic == "modules.d5.terminal_association"
    )

    assert d3_messages
    assert d3_messages[-1].payload["metadata"]["learning_applied"] is False
    assert (
        d3_messages[-1].payload["metadata"]["learning_fallback_reason"]
        == "model_bundle_missing"
    )
    assert d4_advice_messages
    advice = d4_advice_messages[-1].payload
    assert advice["requested_mode"] == "assist"
    assert advice["effective_mode"] == "shadow"
    assert advice["assist_eligible"] is False
    assert advice["unseen_seed_count"] == 0
    assert advice["formal_decision_unchanged"] is True
    assert advice["fallback_used"] is True
    assert d5_messages
    assert d5_messages[-1].payload["probability_source"] == "deterministic_geometry_rule"
    assert d5_messages[-1].payload["fallback_reason"].startswith("bundle_")
    assert result.summary["online_truth_use_count"] == 0


def test_learning_runtime_rejects_invalid_modes() -> None:
    try:
        LearningRuntimeOptions(d3_mode="online")
    except ValueError as exc:
        assert "d3_mode" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid mode was accepted")
