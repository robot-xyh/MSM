from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from research_modules.scalable_3d_simulation.communication import (
    DeterministicCommunicationNetwork,
    LinkProfile,
)
from research_modules.scalable_3d_simulation.animation import write_trajectory_animation
from research_modules.scalable_3d_simulation.episode_bus import (
    InMemoryEpisodeBus,
    assert_online_payload_truth_free,
    build_episode_manifest,
)
from research_modules.scalable_3d_simulation.models import (
    OfflineTruthLabel,
    ScenarioConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.runtime_ports import (
    RuntimePublication,
    RuntimeStepOutput,
)


def test_recursive_truth_guard_rejects_nested_fields_and_truth_dataclasses() -> None:
    assert_online_payload_truth_free({"track": {"global_track_id": "GT-0001"}})
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free({"nested": [{"actor_id": "TargetActor_1"}]})
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(OfflineTruthLabel("obs", "TGT-0001", 0.0))


def test_manifest_hash_and_episode_id_change_with_configuration() -> None:
    first = build_episode_manifest(
        ScenarioConfig(target_count=5, resource_count=5, recon_count=1, seed=7)
    )
    second = build_episode_manifest(
        ScenarioConfig(target_count=5, resource_count=5, recon_count=1, seed=8)
    )
    assert first.config_sha256 != second.config_sha256
    assert first.episode_id != second.episode_id
    assert first.world_schema == "scalable3d-world-v1"


def test_bus_sequences_messages_and_network_applies_transport_delay() -> None:
    bus = InMemoryEpisodeBus()
    envelope = bus.publish(
        topic="tracks",
        source="D2",
        timestamp=1.0,
        payload={"global_track_id": "GT-0001", "covariance": np.eye(6)},
    )
    assert envelope.sequence == 1
    network = DeterministicCommunicationNetwork(
        seed=3,
        default_profile=LinkProfile(
            latency_s=0.1,
            jitter_s=0.0,
            drop_probability=0.0,
            bandwidth_bytes_per_s=1_000_000.0,
        ),
    )
    assert network.send(
        source="D2", destination="D3", send_timestamp=1.0, envelope=envelope
    )
    assert network.deliver(1.05) == ()
    delivered = network.deliver(1.2)
    assert len(delivered) == 1
    assert delivered[0].arrival_timestamp > 1.1


def test_small_episode_writes_separate_online_and_truth_artifacts(tmp_path: Path) -> None:
    config = ScenarioConfig(
        scenario_name="test_5v5",
        scenario_version="test-5v5-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        duration_s=0.2,
        radar_detection_probability=1.0,
        visual_detection_probability=1.0,
        visual_false_alarm_rate=0.0,
    )
    result = run_episode(config, output_dir=tmp_path)
    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert result.output_paths is not None
    online_text = (tmp_path / "online_observations.jsonl").read_text(encoding="utf-8")
    truth_text = (tmp_path / "offline_truth_labels.jsonl").read_text(encoding="utf-8")
    assert "truth_entity_id" not in online_text
    assert "actor_id" not in online_text
    assert "truth_entity_id" in truth_text
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_sha256"] == result.manifest.config_sha256
    with np.load(tmp_path / "offline_truth_state.npz") as payload:
        assert payload["intruder_state"].shape[1:] == (5, 6)


def test_200v200_episode_has_finite_states_without_array_limits() -> None:
    config = ScenarioConfig(
        scenario_name="smoke_200v200",
        scenario_version="smoke-200v200-v1",
        target_count=200,
        resource_count=200,
        recon_count=8,
        duration_s=0.2,
        radar_enabled=True,
        visual_enabled=False,
    )
    result = run_episode(config)
    assert result.intruder_state_history.shape == (5, 200, 6)
    assert result.interceptor_state_history.shape == (5, 200, 6)
    assert result.summary["finite_state"] is True
    assert result.summary["radar_observation_count"] > 0


def test_offline_truth_history_can_render_three_dimensional_gif(tmp_path: Path) -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=1,
        duration_s=0.1,
        radar_enabled=False,
        visual_enabled=False,
    )
    result = run_episode(config)
    path = write_trajectory_animation(result, tmp_path / "trajectory.gif", fps=5)
    assert path.read_bytes()[:6] in {b"GIF87a", b"GIF89a"}


class _ConstantCommandStack:
    def __init__(self, *, publish_truth: bool = False) -> None:
        self.publish_truth = publish_truth
        self.config: ScenarioConfig | None = None

    def reset(self, config: ScenarioConfig) -> None:
        self.config = config

    def step(self, step_input: object) -> RuntimeStepOutput:
        assert self.config is not None
        payload = {"plan_version": 1, "status": "coast"}
        if self.publish_truth:
            payload["actor_id"] = "TargetActor_1"
        return RuntimeStepOutput(
            interceptor_acceleration_ned=np.tile(
                np.array([0.0, 0.5, 0.0]),
                (self.config.resource_count, 1),
            ),
            recon_acceleration_ned=np.zeros((self.config.recon_count, 3)),
            publications=(
                RuntimePublication(
                    topic="modules.test",
                    source="TEST-STACK",
                    schema_version="test-stack-v1",
                    payload=payload,
                ),
            ),
        )


def test_truth_free_module_stack_can_write_commands_back_to_world() -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=1,
        duration_s=0.1,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    result = run_episode(config, module_stack=_ConstantCommandStack())
    assert result.summary["module_stack_enabled"] is True
    assert result.summary["control_command_tick_count"] == 2
    assert result.summary["module_publication_count"] == 2
    assert len(result.online_messages) == 2
    assert not np.array_equal(
        result.interceptor_state_history[0], result.interceptor_state_history[-1]
    )


def test_module_stack_publication_cannot_leak_actor_identity() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    with pytest.raises(ValueError, match="truth fields"):
        run_episode(config, module_stack=_ConstantCommandStack(publish_truth=True))
