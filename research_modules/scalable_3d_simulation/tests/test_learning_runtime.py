from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.episode_bus import build_episode_manifest
from research_modules.scalable_3d_simulation.experiment_authorization import (
    G1_SHADOW_APPROVAL_CONFIRMATION,
    approve_g1_shadow_authorization_request,
    build_g1_shadow_authorization_request,
    canonical_json_sha256,
    load_g1_shadow_experiment_authorization,
    sha256_file,
    write_g1_shadow_authorization_request,
    write_g1_shadow_revocation_registry,
)
from research_modules.scalable_3d_simulation.learning_runtime import (
    LearningRuntimeOptions,
    resolve_learning_runtime,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


READINESS_D4_BUNDLE = (
    Path(__file__).resolve().parents[2]
    / "d4_distributed_fallback/model_registry"
    / "region_resource_a2_8region_runtime_action_readiness_shadow_v2"
    / "bundle"
)


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
    assert (
        resolved.config.d5_active_vision_policy_version
        == config.d5_active_vision_policy_version
    )
    assert resolved.stack.d3_learning_assistant is None
    assert resolved.stack.d4_region_advisor is None
    assert resolved.stack.d5_edge_model is None
    assert resolved.stack.d5_active_vision_policy is None
    assert resolved.diagnostics["default_rule_path_preserved"] is True
    assert resolved.diagnostics["d3"]["effective_mode"] == "disabled"
    assert resolved.diagnostics["d4"]["effective_mode"] == "disabled"
    assert resolved.diagnostics["d5"]["effective_mode"] == "disabled"
    assert resolved.diagnostics["d5_active_vision"]["effective_mode"] == "disabled"

    manifest = build_episode_manifest(resolved.config)
    assert manifest.d4_policy_version == "d4-region-resource-rule-v1"
    assert manifest.d5_active_vision_policy_version == "d5-active-vision-rule-v1"
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
    config = _short_integrated_config()
    resolved = resolve_learning_runtime(config, options)

    assert resolved.diagnostics["d3"]["effective_mode"] == "rule_fallback"
    assert resolved.diagnostics["d3"]["fallback_reason"] == "model_bundle_missing"
    assert resolved.diagnostics["d4"]["bundle_loaded"] is False
    assert "model_bundle_missing" in resolved.diagnostics["d4"]["fallback_reason"]
    assert resolved.diagnostics["d4"]["formal_unseen_seed_count"] == 0
    assert (
        resolved.stack.d4_region_advisor.config.projection.advisory_ttl_s
        >= config.assignment_period_s + config.physics_dt_s
    )
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


def test_d4_runtime_gate_diagnostic_stays_out_of_online_bus() -> None:
    config = ScenarioConfig(
        scenario_name="d4_runtime_gate_bus_boundary",
        scenario_version="d4-runtime-gate-bus-boundary-v1",
        seed=2000,
        target_count=20,
        resource_count=20,
        recon_count=2,
        region_count=8,
        duration_s=1.2,
        acoustic_enabled=False,
    )
    resolved = resolve_learning_runtime(
        config,
        LearningRuntimeOptions(
            d4_mode="shadow",
            d4_bundle_dir=READINESS_D4_BUNDLE,
        ),
        stack_config=IntegratedStackConfig(
            capture_learning_artifacts=True
        ),
    )

    assert resolved.diagnostics["d4"]["bundle_loaded"] is True
    result = run_episode(resolved.config, module_stack=resolved.stack)
    advice_messages = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d4.region_resource_advice"
    )
    assert advice_messages
    assert all(
        "runtime_confidence_gate_diagnostic" not in message.payload
        for message in advice_messages
    )
    frames = resolved.stack.learning_artifacts().d4_region_frames
    assert frames
    assert all(
        frame.recommendation is not None
        and frame.recommendation.runtime_confidence_gate_diagnostic
        is not None
        for frame in frames
    )
    assert result.summary["online_truth_use_count"] == 0


def test_learning_runtime_rejects_invalid_modes() -> None:
    try:
        LearningRuntimeOptions(d3_mode="online")
    except ValueError as exc:
        assert "d3_mode" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid mode was accepted")

    try:
        LearningRuntimeOptions(d5_active_vision_mode="online")
    except ValueError as exc:
        assert "d5_active_vision_mode" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("invalid active-vision mode was accepted")


def test_missing_active_vision_bundle_falls_back_to_rule_camera_actions(
    tmp_path: Path,
) -> None:
    options = LearningRuntimeOptions(
        d5_active_vision_mode="assist",
        d5_active_vision_bundle_dir=tmp_path / "missing-active-vision",
    )
    resolved = resolve_learning_runtime(_short_integrated_config(), options)

    diagnostics = resolved.diagnostics["d5_active_vision"]
    assert diagnostics["bundle_loaded"] is False
    assert diagnostics["effective_mode"] == "rule_fallback"
    assert diagnostics["fallback_reason"].startswith("bundle_")
    assert diagnostics["assist_admitted"] is False

    result = run_episode(resolved.config, module_stack=resolved.stack)
    messages = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.active_vision"
    ]
    assert messages
    assert result.summary["camera_command_applied_count"] > 0
    assert result.summary["camera_command_rejected_count"] == 0
    assert {
        command["effective_mode"]
        for payload in messages
        for command in payload["commands"]
    } == {"disabled"}
    assert all(
        "bundle_" in command["reason"]
        for payload in messages
        for command in payload["commands"]
    )


def test_integrated_d5_bundle_requires_g1_assist_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_modules.d5_terminal_association.src.d5_terminal_association import (
        tracklet_model_bundle,
    )

    bundle = tmp_path / "d5-development-bundle"
    bundle.mkdir()
    captured: dict[str, object] = {}

    class _Unavailable:
        available = False
        failure_reason = "bundle_g1_assist_not_eligible"

    def _load(
        bundle_dir: Path,
        *,
        device: str,
        require_g1_assist_eligible: bool = False,
    ) -> _Unavailable:
        captured.update(
            bundle_dir=Path(bundle_dir),
            device=device,
            require_g1_assist_eligible=require_g1_assist_eligible,
        )
        return _Unavailable()

    monkeypatch.setattr(
        tracklet_model_bundle,
        "load_tracklet_model_bundle_for_runtime",
        _load,
    )

    resolved = resolve_learning_runtime(
        _short_integrated_config(),
        LearningRuntimeOptions(d5_bundle_dir=bundle),
    )

    assert captured == {
        "bundle_dir": bundle,
        "device": "cpu",
        "require_g1_assist_eligible": True,
    }
    assert resolved.diagnostics["d5"]["bundle_loaded"] is False
    assert resolved.diagnostics["d5"]["effective_mode"] == "rule_fallback"
    assert (
        resolved.diagnostics["d5"]["fallback_reason"]
        == "bundle_g1_assist_not_eligible"
    )


def test_human_authorized_g1_is_shadow_only_and_cannot_change_d5_bindings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research_modules.d5_terminal_association.src.d5_terminal_association import (
        tracklet_model_bundle,
    )

    bundle = tmp_path / "d5-v5"
    bundle.mkdir()
    (bundle / "manifest.json").write_text(
        '{"schema_version":"test-v5"}\n',
        encoding="utf-8",
    )
    (bundle / "weights.pt").write_bytes(b"test-shadow-weights")
    manifest_sha256 = sha256_file(bundle / "manifest.json")
    weights_sha256 = sha256_file(bundle / "weights.pt")
    tree_sha256 = canonical_json_sha256(
        [
            {
                "path": path.relative_to(bundle).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in sorted(bundle.iterdir())
            if path.is_file()
        ]
    )
    request = build_g1_shadow_authorization_request(
        authorization_id="g1-shadow-runtime-test",
        purpose="bounded runtime test",
        source_git_commit="e" * 40,
        scenarios=("learning_runtime_smoke",),
        scales=(5,),
        seeds=(31,),
        duration_s=1.2,
        d5_bundle_manifest_sha256=manifest_sha256,
        d5_bundle_tree_sha256=tree_sha256,
        d5_weights_sha256=weights_sha256,
        device="cpu",
        not_before_utc="2020-01-01T00:00:00+00:00",
        expires_at_utc="2099-01-01T00:00:00+00:00",
        revocation_registry_id="g1-shadow-registry-test",
    )
    request_path = write_g1_shadow_authorization_request(
        tmp_path / "request.json",
        request,
    )
    registry_path = write_g1_shadow_revocation_registry(
        tmp_path / "revocations.json",
        registry_id="g1-shadow-registry-test",
        updated_at_utc="2026-07-27T00:00:00+00:00",
    )
    authorization_path, authorization_sha256 = (
        approve_g1_shadow_authorization_request(
            request_path,
            tmp_path / "authorization.json",
            expected_request_sha256=str(request["request_sha256"]),
            approver_id="test-operator",
            approval_reason="bounded test",
            confirmation=G1_SHADOW_APPROVAL_CONFIRMATION,
            approved_at_utc="2026-07-27T00:00:00+00:00",
        )
    )
    authorization = load_g1_shadow_experiment_authorization(
        authorization_path,
        expected_authorization_sha256=authorization_sha256,
        revocation_registry_path=registry_path,
        now_utc="2026-07-27T00:00:00+00:00",
    )
    captured: dict[str, object] = {}

    class _ShadowScorer:
        available = True
        bundle_manifest_sha256 = manifest_sha256
        bundle_weights_sha256 = weights_sha256
        decision_threshold = 0.5
        manifest = {"model_semantic_version": "1.0.0"}

        def forward_graph(self, graph: object) -> np.ndarray:
            return np.full(graph.edge_count, 0.9, dtype=float)

    def _load(
        bundle_dir: Path,
        *,
        device: str,
        require_g1_assist_eligible: bool = False,
    ) -> _ShadowScorer:
        captured.update(
            bundle_dir=Path(bundle_dir),
            device=device,
            require_g1_assist_eligible=require_g1_assist_eligible,
        )
        return _ShadowScorer()

    monkeypatch.setattr(
        tracklet_model_bundle,
        "load_tracklet_model_bundle_for_runtime",
        _load,
    )
    resolved = resolve_learning_runtime(
        _short_integrated_config(),
        LearningRuntimeOptions(
            d5_bundle_dir=bundle,
            d5_g1_shadow_authorization=authorization,
        ),
    )

    assert captured["require_g1_assist_eligible"] is False
    assert resolved.stack.d5_edge_model is None
    assert resolved.stack.d5_shadow_edge_model is not None
    assert resolved.diagnostics["d5"]["effective_mode"] == "authorized_shadow"
    assert resolved.diagnostics["d5"]["model_output_applied"] is False
    assert (
        resolved.diagnostics["d5"]["experiment_authorization_valid"] is True
    )

    result = run_episode(resolved.config, module_stack=resolved.stack)
    online_d5 = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.terminal_association"
    ]
    shadow = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.g1_shadow_scoring"
    ]
    assert online_d5
    assert shadow
    assert {
        payload["probability_source"] for payload in online_d5
    } == {"deterministic_geometry_rule"}
    assert all(payload["model_output_applied"] is False for payload in shadow)
    assert all(payload["global_track_id_authority"] is False for payload in shadow)
    assert all(payload["control_authority"] is False for payload in shadow)
    module_summary = result.summary["module_final_diagnostics"]
    assert module_summary["d5_g1_shadow_scoring_frame_count"] == len(shadow)
    assert module_summary["d5_g1_shadow_model_output_applied"] is False

    (bundle / "unexpected.txt").write_text("tampered\n", encoding="utf-8")
    rejected = resolve_learning_runtime(
        _short_integrated_config(),
        LearningRuntimeOptions(
            d5_bundle_dir=bundle,
            d5_g1_shadow_authorization=authorization,
        ),
    )
    assert rejected.stack.d5_shadow_edge_model is None
    assert rejected.diagnostics["d5"]["effective_mode"] == "rule_fallback"
    assert (
        rejected.diagnostics["d5"]["fallback_reason"]
        == "experiment_authorization_ValueError"
    )
