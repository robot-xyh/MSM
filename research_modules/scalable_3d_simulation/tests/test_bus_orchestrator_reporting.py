from __future__ import annotations

import csv
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
    VersionedEnvelope,
    assert_online_payload_truth_free,
    build_episode_manifest,
)
from research_modules.scalable_3d_simulation.models import (
    OfflineTruthLabel,
    ScenarioConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import (
    _TimingAccumulator,
    run_episode,
)
from research_modules.scalable_3d_simulation.offline_evaluation import (
    PrewrittenIdentityRecordPaths,
    write_offline_identity_evaluation,
)
from research_modules.scalable_3d_simulation.runtime_ports import (
    CameraObservationCommand,
    RuntimePublication,
    RuntimeStepInput,
    RuntimeStepOutput,
)


def test_recursive_truth_guard_rejects_nested_fields_and_truth_dataclasses() -> None:
    assert_online_payload_truth_free({"track": {"global_track_id": "GT-0001"}})
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free({"nested": [{"actor_id": "TargetActor_1"}]})
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(OfflineTruthLabel("obs", "TGT-0001", 0.0))


def test_timing_accumulator_does_not_backfill_missing_child_distribution() -> None:
    timings = _TimingAccumulator()
    timings.add("direct", 0.002)
    timings.add("direct", 0.004)
    timings.merge_total("module.legacy", wall_time_s=0.006, call_count=2)

    records = {item.stage: item for item in timings.records()}

    assert records["direct"].distribution_available is True
    assert records["direct"].p50_wall_time_ms == pytest.approx(3.0)
    assert records["module.legacy"].distribution_available is False
    assert records["module.legacy"].p50_wall_time_ms is None
    assert records["module.legacy"].p95_wall_time_ms is None
    assert records["module.legacy"].max_wall_time_ms is None
    assert records["module.legacy"].distribution_unavailable_reason == (
        "child_timing_distribution_unavailable"
    )


def test_timing_accumulator_rejects_partial_child_distribution() -> None:
    timings = _TimingAccumulator()

    with pytest.raises(
        ValueError,
        match="timing distribution fields must be all present or all absent",
    ):
        timings.merge_total(
            "module.partial",
            wall_time_s=0.006,
            call_count=2,
            p50_wall_time_ms=2.0,
        )


def test_recursive_truth_guard_handles_cycles_without_weakening_nested_checks() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    assert_online_payload_truth_free(cyclic)
    cyclic["nested"] = [{"object-id": "TargetActor_1"}]
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(cyclic)


def test_truth_guard_layout_cache_still_checks_new_nested_values_and_keys() -> None:
    assert_online_payload_truth_free({"nested": [{"status": "safe"}]})

    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(
            {"nested": [{"actor_id": "TargetActor_1"}]}
        )

    mutable = {"status": "safe"}
    assert_online_payload_truth_free(mutable)
    mutable["actor-id"] = "TargetActor_1"
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(mutable)


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
    assert first.d5_active_vision_policy_version == "d5-active-vision-rule-v1"


def test_manifest_hashes_runtime_treatment_separately_from_scenario() -> None:
    config = ScenarioConfig(
        target_count=5,
        resource_count=5,
        recon_count=1,
        seed=7,
    )
    baseline = build_episode_manifest(
        config,
        runtime_profile={
            "schema_version": "test-runtime-profile-v1",
            "d1_radar_assignment_ambiguity_governance_v2": False,
        },
    )
    candidate = build_episode_manifest(
        config,
        runtime_profile={
            "schema_version": "test-runtime-profile-v1",
            "d1_radar_assignment_ambiguity_governance_v2": True,
        },
    )

    assert baseline.config_sha256 == candidate.config_sha256
    assert baseline.runtime_profile_sha256 != candidate.runtime_profile_sha256
    assert baseline.episode_id != candidate.episode_id
    assert baseline.runtime_profile_schema == "test-runtime-profile-v1"
    assert candidate.runtime_profile == {
        "schema_version": "test-runtime-profile-v1",
        "d1_radar_assignment_ambiguity_governance_v2": True,
    }


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
        assert payload["intruder_ids"].tolist() == [
            f"TGT-{index:04d}" for index in range(1, 6)
        ]
    consistency_manifest = json.loads(
        (tmp_path / "offline_consistency" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert consistency_manifest["available"] is False
    assert consistency_manifest["reason"] == "d1_consistency_evidence_unavailable"
    d6_record = json.loads(
        (tmp_path / "d6_truth_isolated" / "episode_record.json").read_text(
            encoding="utf-8"
        )
    )
    assert d6_record["d2_identity"]["id_switch_count"] is None
    assert d6_record["d2_identity"]["id_switch_count_availability"] == (
        "unavailable"
    )
    report = (tmp_path / "SCALABLE_3D_EPISODE_REPORT_CN.md").read_text(
        encoding="utf-8"
    )
    assert "本次未启用 D1-D7 集成栈" in report


def test_offline_identity_marks_incomplete_lineage_unavailable(tmp_path: Path) -> None:
    messages = (
        VersionedEnvelope(
            sequence=1,
            topic="modules.d1.fused_tracks",
            source="D1",
            timestamp=0.1,
            schema_version="d1-scalable3d-fusion-v1",
            payload={
                "timestamp": 0.1,
                "track_count": 1,
                "tracks": [
                    {
                        "global_track_id": "D1-TRACK-0001",
                        "state_ned": [0.0] * 6,
                        "covariance": np.eye(6).tolist(),
                        "timestamp": 0.0,
                        "track_state": "tentative",
                    }
                ],
                "observation_lineage": [
                    {
                        "observation_id": "OBS-0001",
                        "measurement_timestamp": 0.0,
                        "source_lineage": ["OBS-0001"],
                        "replay_generation": 0,
                    }
                ]
            },
        ),
        VersionedEnvelope(
            sequence=2,
            topic="modules.d2.associated_tracks",
            source="D2",
            timestamp=0.1,
            schema_version="d2-scalable3d-association-v1",
            payload={
                "timestamp": 0.1,
                "track_count": 1,
                "tracks": [
                    {
                        "global_track_id": "GT-0001",
                        "state_ned": [0.0] * 6,
                        "covariance": np.eye(6).tolist(),
                        "timestamp": 0.0,
                        "track_state": "tentative",
                    }
                ],
                "association": {"timestamp": 0.0},
                "id_switch_count": None,
                "id_switch_count_available": False,
                "identity_lineage_policy": (
                    "d2_center_track_to_d1_source_observation_v1"
                ),
                "identity_lineage": [
                    {
                        "global_track_id": "GT-0001",
                        "lifecycle_state": "tentative",
                        "association_state": "matched",
                        "source_observations": [],
                    }
                ],
            },
        ),
    )

    paths = write_offline_identity_evaluation(
        tmp_path,
        episode_id="episode-incomplete-lineage",
        messages=messages,
        offline_truth_labels=(
            OfflineTruthLabel("OBS-0001", "TGT-0001", 0.0),
        ),
    )

    manifest = json.loads(
        paths["offline_identity_manifest"].read_text(encoding="utf-8")
    )
    evaluation = json.loads(
        paths["offline_identity_evaluation"].read_text(encoding="utf-8")
    )
    assert manifest["available"] is True
    assert manifest["identity_metrics_available"] is False
    assert manifest["evidence_record_count"] == 1
    assert manifest["lineage_incomplete_record_count"] == 1
    assert evaluation["metrics"]["truth_metrics_available"] is False
    assert "source_lineage_missing" in evaluation["audit"][
        "identity_metrics_blocking_reasons"
    ]


def test_offline_identity_rejects_mismatched_prewritten_record_counts(
    tmp_path: Path,
) -> None:
    messages = (
        VersionedEnvelope(
            sequence=1,
            topic="modules.d1.fused_tracks",
            source="D1",
            timestamp=0.1,
            schema_version="d1-scalable3d-fusion-v1",
            payload={"tracks": [], "observation_lineage": []},
        ),
        VersionedEnvelope(
            sequence=2,
            topic="modules.d2.associated_tracks",
            source="D2",
            timestamp=0.1,
            schema_version="d2-scalable3d-association-v1",
            payload={"tracks": [], "identity_lineage": []},
        ),
    )
    d1_path = tmp_path / "online_d1_records.jsonl"
    d2_path = tmp_path / "online_d2_records.jsonl"
    d1_path.write_text("{}\n", encoding="utf-8")
    d2_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="prewritten D1 record count"):
        write_offline_identity_evaluation(
            tmp_path / "evaluation",
            episode_id="prewritten-count-mismatch",
            messages=messages,
            offline_truth_labels=(),
            prewritten_records=PrewrittenIdentityRecordPaths(
                d1_path=d1_path,
                d2_path=d2_path,
                d1_record_count=2,
                d2_record_count=1,
            ),
        )


def test_episode_routes_sensor_batches_through_configured_network() -> None:
    config = ScenarioConfig(
        scenario_name="networked_sensor_delivery",
        scenario_version="networked-sensor-delivery-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.25,
        radar_period_s=1.0,
        radar_latency_s=0.05,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_latency_s=0.10,
        communication_jitter_s=0.0,
        communication_drop_probability=0.0,
        communication_bandwidth_bytes_per_s=1_000_000_000.0,
    )

    result = run_episode(config)

    batches = [
        message.payload
        for message in result.online_messages
        if message.topic == "sensor.observations"
    ]
    assert len(batches) == 1
    assert batches[0].measurement_timestamp == pytest.approx(0.0)
    assert 0.15 <= batches[0].arrival_timestamp <= 0.20
    assert all(
        measurement.arrival_timestamp == batches[0].arrival_timestamp
        for measurement in batches[0].measurements
    )
    assert result.summary["communication_sent_count"] == 1
    assert result.summary["communication_delivered_count"] == 1
    assert result.summary["communication_dropped_count"] == 0
    assert result.summary["communication_pending_count"] == 0


def test_episode_network_drop_removes_batch_from_online_consumer() -> None:
    config = ScenarioConfig(
        scenario_name="network_drop",
        scenario_version="network-drop-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.20,
        radar_period_s=1.0,
        radar_latency_s=0.05,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_latency_s=0.0,
        communication_jitter_s=0.0,
        communication_drop_probability=1.0,
    )

    result = run_episode(config)

    assert result.summary["radar_observation_count"] == 0
    assert result.summary["communication_sent_count"] == 1
    assert result.summary["communication_delivered_count"] == 0
    assert result.summary["communication_dropped_count"] == 1


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
        communication_enabled=False,
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


class _StaleCameraCommandStack:
    def __init__(self) -> None:
        self.config: ScenarioConfig | None = None
        self.calls = 0

    def reset(self, config: ScenarioConfig) -> None:
        self.config = config
        self.calls = 0

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        assert self.config is not None
        self.calls += 1
        camera = step_input.cameras[0]
        position = step_input.interceptors.state_ned[0, :3]
        plan_version = 2 if self.calls == 1 else 1
        return RuntimeStepOutput(
            interceptor_acceleration_ned=np.zeros((self.config.resource_count, 3)),
            recon_acceleration_ned=np.zeros((self.config.recon_count, 3)),
            camera_commands=(
                CameraObservationCommand(
                    camera_id=camera.camera_id,
                    resource_id=camera.resource_id,
                    issued_timestamp=step_input.timestamp,
                    expires_timestamp=step_input.timestamp + 0.2,
                    plan_version=plan_version,
                    coalition_version=0,
                    communication_version=self.calls,
                    intent="search_sector",
                    aim_point_ned=position + np.array([1_000.0, 0.0, 0.0]),
                    horizontal_fov_deg=30.0,
                    fov_mode="zoom",
                ),
            ),
        )


class _AssignmentPlanAckStack:
    def __init__(self, *, stale_guidance: bool = False) -> None:
        self.config: ScenarioConfig | None = None
        self.stale_guidance = stale_guidance

    def reset(self, config: ScenarioConfig) -> None:
        self.config = config

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        assert self.config is not None
        plan_version = 3
        guidance_version = plan_version - int(self.stale_guidance)
        return RuntimeStepOutput(
            interceptor_acceleration_ned=np.zeros((self.config.resource_count, 3)),
            recon_acceleration_ned=np.zeros((self.config.recon_count, 3)),
            publications=(
                RuntimePublication(
                    topic="modules.d3.assignment_plan",
                    source="D3",
                    schema_version="assignment-plan-v1",
                    payload={
                        "timestamp": step_input.timestamp,
                        "plan_id": "PLAN-ACK-TEST",
                        "plan_version": plan_version,
                        "created_at": step_input.timestamp,
                        "assignments": [
                            {
                                "resource_id": "INT-000",
                                "global_track_id": "GT-000001",
                                "coalition_id": None,
                                "coalition_version": None,
                                "member_role": "primary",
                            }
                        ],
                        "metadata": {
                            "active_plan_owner": "center",
                            "owner_node_id": "C2",
                            "authority_epoch": 4,
                            "lease_expires_at_s": step_input.timestamp + 1.0,
                            "learning_mode": "shadow",
                            "learning_applied": False,
                            "learning_shadow_only": True,
                            "learning_bundle_loaded": True,
                            "learning_fallback_reason": None,
                            "learning_model_fingerprint": "sha256:model",
                            "regional_hint_considered": True,
                            "regional_hint_applied": True,
                            "regional_hint_rejected": False,
                            "regional_hint_fallback_reason": None,
                            "regional_hint_advisory_id": "ADV-1",
                            "regional_hint_advisory_version": 8,
                            "regional_hint_source_plan_id": "PLAN-OLD",
                            "regional_hint_source_plan_version": 2,
                        },
                    },
                ),
                RuntimePublication(
                    topic="modules.d7.guidance_commands",
                    source="D7",
                    schema_version="d7-guidance-v1",
                    payload={
                        "timestamp": step_input.timestamp,
                        "commands": [
                            {
                                "resource_id": "INT-000",
                                "global_track_id": "GT-000001",
                                "plan_id": "PLAN-ACK-TEST",
                                "plan_version": guidance_version,
                                "mode": "midcourse_pn",
                                "gate_reason": "midcourse_position_guidance",
                            }
                        ],
                    },
                ),
            ),
        )


def test_runtime_publication_keeps_safe_copy_as_the_default() -> None:
    publication = RuntimePublication(
        topic="modules.test",
        source="TEST-STACK",
        schema_version="test-stack-v1",
        payload={"status": "coast"},
    )
    assert publication.copy_payload is True


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


def test_runtime_applies_current_camera_command_and_rejects_stale_plan() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.15,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )

    result = run_episode(config, module_stack=_StaleCameraCommandStack())

    assert result.summary["camera_command_issued_count"] == 3
    assert result.summary["camera_command_applied_count"] == 1
    assert result.summary["camera_command_rejected_count"] == 2
    assert result.summary["camera_command_rejection_reason_counts"] == {
        "stale_plan_version": 2
    }
    acknowledgements = [
        message.payload
        for message in result.online_messages
        if message.topic == "runtime.camera_command_ack"
    ]
    assert [item["status"] for item in acknowledgements] == [
        "applied",
        "rejected",
        "rejected",
    ]


def test_runtime_acknowledges_d3_plan_binding_consumed_by_d7() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )

    result = run_episode(config, module_stack=_AssignmentPlanAckStack())

    assert result.summary["assignment_plan_ack_count"] == 1
    assert result.summary["assignment_plan_binding_ack_count"] == 1
    assert result.summary["assignment_plan_control_applied_count"] == 1
    assert result.summary["assignment_plan_hold_count"] == 0
    acknowledgements = [
        message.payload
        for message in result.online_messages
        if message.topic == "runtime.assignment_plan_ack"
    ]
    assert len(acknowledgements) == 1
    acknowledgement = acknowledgements[0]
    assert acknowledgement["plan_id"] == "PLAN-ACK-TEST"
    assert acknowledgement["plan_version"] == 3
    assert acknowledgement["accepted"] is True
    assert acknowledgement["fully_bound_to_guidance"] is True
    assert acknowledgement["decision_id"] == "PLAN-ACK-TEST:v3"
    assert acknowledgement["source_plan_bus_sequence"] == 1
    assert acknowledgement["source_guidance_bus_sequence"] == 2
    assert len(acknowledgement["source_plan_payload_sha256"]) == 64
    assert len(acknowledgement["source_guidance_payload_sha256"]) == 64
    assert acknowledgement["d3_learning_evidence"] == {
        "mode": "shadow",
        "applied": False,
        "shadow_only": True,
        "bundle_loaded": True,
        "fallback_reason": None,
        "model_fingerprint": "sha256:model",
    }
    assert acknowledgement["d4_regional_hint_evidence"] == {
        "considered": True,
        "applied": True,
        "rejected": False,
        "fallback_reason": None,
        "advisory_id": "ADV-1",
        "advisory_version": 8,
        "source_plan_id": "PLAN-OLD",
        "source_plan_version": 2,
    }
    assert acknowledgement["physical_outcome_available"] is False
    assert acknowledgement["reward_available"] is False
    assert acknowledgement["binding_acks"] == [
        {
            "resource_id": "INT-000",
            "global_track_id": "GT-000001",
            "coalition_id": None,
            "coalition_version": None,
            "member_role": "primary",
            "guidance_command_present": True,
            "guidance_mode": "midcourse_pn",
            "guidance_gate_reason": "midcourse_position_guidance",
            "control_applied_to_world": True,
            "held": False,
        }
    ]


def test_runtime_rejects_guidance_ack_for_stale_d3_plan_version() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )

    with pytest.raises(ValueError, match="current D3 plan"):
        run_episode(
            config,
            module_stack=_AssignmentPlanAckStack(stale_guidance=True),
        )
