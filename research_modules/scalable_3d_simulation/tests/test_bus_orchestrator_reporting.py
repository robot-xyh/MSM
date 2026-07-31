from __future__ import annotations

import csv
from dataclasses import replace
from hashlib import sha256
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
    ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION,
    ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
    VersionedEnvelope,
    assert_online_payload_truth_free,
    build_episode_manifest,
)
from research_modules.scalable_3d_simulation.models import (
    CameraFrameEvent,
    OfflineTruthLabel,
    ScenarioConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import (
    _TimingAccumulator,
    _active_vision_pairing_context_sha256,
    run_episode,
)
from research_modules.scalable_3d_simulation.offline_evaluation import (
    OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2,
    PrewrittenIdentityRecordPaths,
    write_offline_identity_evaluation,
)
from research_modules.scalable_3d_simulation.runtime_ports import (
    CameraObservationCommand,
    RuntimeCommunicationIntent,
    RuntimePublication,
    RuntimeStepInput,
    RuntimeStepOutput,
)
from research_modules.scalable_3d_simulation.sensor_scene import SensorScene
from research_modules.scalable_3d_simulation.world import VectorizedPointMassWorld

_TEST_IDENTITY_RECOVERY_CONFIG = {
    "schema_version": "d2.identity-commitment-recovery-config.v2",
    "config_version": "test-identity-recovery-config-v1",
    "publication_freshness_gate_enabled": True,
    "max_recovery_evidence_age_seconds": 0.9,
    "publication_freshness_clock": (
        "d2_tracker_frame_timestamp_minus_source_measurement_timestamp"
    ),
    "publication_stale_behavior": (
        "remain_uncommitted_until_newer_original_evidence"
    ),
}


@pytest.mark.parametrize(
    "implementation",
    (
        ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
        ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION,
    ),
)
def test_recursive_truth_guard_rejects_nested_fields_and_truth_dataclasses(
    implementation: str,
) -> None:
    assert_online_payload_truth_free(
        {"track": {"global_track_id": "GT-0001"}},
        implementation=implementation,
    )
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(
            {"nested": [{"actor_id": "TargetActor_1"}]},
            implementation=implementation,
        )
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(
            OfflineTruthLabel("obs", "TGT-0001", 0.0),
            implementation=implementation,
        )


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


def test_active_vision_pairing_context_uses_frozen_exogenous_hash() -> None:
    unfrozen = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=1,
        seed=17,
        sensor_random_schedule_version="entity_fixed_v1",
        metadata={
            "comparison_key": "nominal|2|17",
            "algorithm_variant": "R0",
        },
    )
    frozen_hash = _active_vision_pairing_context_sha256(unfrozen)
    base = replace(
        unfrozen,
        metadata={
            **unfrozen.metadata,
            "paired_exogenous_config_sha256": frozen_hash,
        },
    )
    candidate = replace(
        base,
        d5_active_vision_policy_version="candidate-a3",
        metadata={
            **base.metadata,
            "algorithm_variant": "A3",
            "learning_runtime": {"d5_active_vision": {"effective_mode": "assist"}},
        },
    )

    assert _active_vision_pairing_context_sha256(base) == frozen_hash
    assert _active_vision_pairing_context_sha256(candidate) == frozen_hash
    with pytest.raises(ValueError, match="differs from episode configuration"):
        _active_vision_pairing_context_sha256(
            replace(
                base,
                metadata={
                    **base.metadata,
                    "paired_exogenous_config_sha256": "f" * 64,
                },
            )
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


@pytest.mark.parametrize(
    "implementation",
    (
        ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
        ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION,
    ),
)
def test_recursive_truth_guard_handles_cycles_without_weakening_nested_checks(
    implementation: str,
) -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    assert_online_payload_truth_free(cyclic, implementation=implementation)
    cyclic["nested"] = [{"object-id": "TargetActor_1"}]
    with pytest.raises(ValueError, match="truth fields"):
        assert_online_payload_truth_free(
            cyclic,
            implementation=implementation,
        )


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


def test_network_records_final_message_disposition_and_retry_generation() -> None:
    envelope = VersionedEnvelope(
        sequence=7,
        topic="d4.regional_plan_broadcast.v1",
        source="CENTER",
        timestamp=1.0,
        schema_version="d4-test-v1",
        payload={
            "message_id": "plan-message-7",
            "retry_generation": 1,
        },
    )
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
        source="CENTER",
        destination="INT-001",
        send_timestamp=1.0,
        envelope=envelope,
    )
    pending = network.disposition_records()
    assert len(pending) == 1
    assert pending[0].disposition == "pending"
    assert pending[0].retry_generation == 1
    assert pending[0].message_id == "plan-message-7"
    assert network.deliver_topics(
        1.2,
        topics=frozenset({"sensor.observations"}),
    ) == ()
    assert network.pending_topic_count(
        frozenset({"d4.regional_plan_broadcast.v1"})
    ) == 1

    delivered = network.deliver_topics(
        1.2,
        topics=frozenset({"d4.regional_plan_broadcast.v1"}),
    )

    assert len(delivered) == 1
    assert network.disposition_records()[0].disposition == "delivered"


def test_separate_communication_random_stream_does_not_perturb_shared_transport() -> None:
    profile = LinkProfile(
        latency_s=0.1,
        jitter_s=0.02,
        drop_probability=0.0,
        bandwidth_bytes_per_s=1_000_000.0,
    )

    def shared_arrivals(*, include_strict_evidence: bool) -> tuple[float, ...]:
        bus = InMemoryEpisodeBus()
        network = DeterministicCommunicationNetwork(
            seed=17,
            default_profile=profile,
        )
        first = bus.publish(
            topic="sensor.observations",
            source="RADAR",
            timestamp=1.0,
            payload={"batch": 1},
        )
        second = bus.publish(
            topic="sensor.observations",
            source="RADAR",
            timestamp=1.1,
            payload={"batch": 2},
        )
        assert network.send(
            source="RADAR",
            destination="FUSION",
            send_timestamp=1.0,
            envelope=first,
        )
        if include_strict_evidence:
            evidence = bus.publish(
                topic="d4.regional_plan_owner_ack.v1",
                source="D4",
                timestamp=1.05,
                payload={"ack": 1},
            )
            assert network.send(
                source="D4",
                destination="MAIN",
                send_timestamp=1.05,
                envelope=evidence,
                random_stream="d4_strict_evidence_v1",
            )
        assert network.send(
            source="RADAR",
            destination="FUSION",
            send_timestamp=1.1,
            envelope=second,
        )
        return tuple(
            item.arrival_timestamp
            for item in network.deliver(2.0)
            if item.envelope.topic == "sensor.observations"
        )

    assert shared_arrivals(include_strict_evidence=False) == shared_arrivals(
        include_strict_evidence=True
    )


def test_bus_truth_guard_candidate_is_explicit_auditable_and_default_off() -> None:
    reference = InMemoryEpisodeBus()
    candidate = InMemoryEpisodeBus(
        truth_guard_implementation=(
            ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION
        )
    )

    reference.publish(
        topic="tracks",
        source="D2",
        timestamp=0.1,
        payload={"global_track_id": "GT-0001"},
        copy_payload=False,
    )
    candidate.publish(
        topic="tracks",
        source="D2",
        timestamp=0.1,
        payload={"global_track_id": "GT-0001"},
        copy_payload=False,
    )

    assert reference.truth_guard_diagnostics() == {
        "schema_version": (
            "scalable3d-online-truth-guard-diagnostics-v1"
        ),
        "implementation": ONLINE_TRUTH_GUARD_REFERENCE_IMPLEMENTATION,
        "candidate_enabled": False,
        "validation_count": 1,
    }
    assert candidate.truth_guard_diagnostics() == {
        "schema_version": (
            "scalable3d-online-truth-guard-diagnostics-v1"
        ),
        "implementation": ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION,
        "candidate_enabled": True,
        "validation_count": 1,
    }
    with pytest.raises(ValueError, match="truth fields"):
        candidate.publish(
            topic="tracks",
            source="D2",
            timestamp=0.2,
            payload={"nested": {"truth_entity_id": "TGT-0001"}},
        )
    assert candidate.truth_guard_diagnostics()["validation_count"] == 1
    with pytest.raises(ValueError, match="truth_guard_implementation"):
        InMemoryEpisodeBus(truth_guard_implementation="unknown")


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
    dispositions = [
        json.loads(line)
        for line in (tmp_path / "communication_dispositions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(dispositions) == result.summary[
        "communication_disposition_record_count"
    ]
    assert all(
        item["schema_version"]
        == "scalable3d-communication-disposition-v1"
        for item in dispositions
    )
    online_text = (tmp_path / "online_observations.jsonl").read_text(encoding="utf-8")
    truth_text = (tmp_path / "offline_truth_labels.jsonl").read_text(encoding="utf-8")
    assert "truth_entity_id" not in online_text
    assert "actor_id" not in online_text
    assert "truth_entity_id" in truth_text
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_sha256"] == result.manifest.config_sha256
    learning_evidence = json.loads(
        (tmp_path / "learning_adoption_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert learning_evidence["schema_version"] == (
        "scalable3d-learning-adoption-evidence-records-v1"
    )
    assert learning_evidence["episode_id"] == result.manifest.episode_id
    assert learning_evidence["records"] == {"a1": [], "a2": [], "a3": []}
    assert len(learning_evidence["content_sha256"]) == 64
    r0_windows = json.loads(
        (tmp_path / "active_vision_r0_windows.json").read_text(
            encoding="utf-8"
        )
    )
    assert r0_windows["schema_version"] == (
        "scalable3d-active-vision-r0-window-records-v1"
    )
    assert r0_windows["episode_id"] == result.manifest.episode_id
    assert r0_windows["records"] == []
    assert len(r0_windows["content_sha256"]) == 64
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
                "association": {
                    "timestamp": 0.0,
                    "identity_commitment": {
                        "recovery_config": dict(
                            _TEST_IDENTITY_RECOVERY_CONFIG
                        )
                    },
                },
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
    assert (
        manifest["schema_version"]
        == OFFLINE_IDENTITY_MANIFEST_SCHEMA_VERSION_V2
    )
    assert manifest["identity_commitment_recovery_config"] == (
        _TEST_IDENTITY_RECOVERY_CONFIG
    )
    canonical_config = json.dumps(
        _TEST_IDENTITY_RECOVERY_CONFIG,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert manifest["identity_commitment_recovery_config_sha256"] == (
        f"sha256:{sha256(canonical_config).hexdigest()}"
    )
    assert (
        manifest[
            "identity_commitment_recovery_config_consistency_verified"
        ]
        is True
    )
    assert manifest["identity_commitment_recovery_config_record_count"] == 1
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
            payload={
                "tracks": [],
                "identity_lineage": [],
                "association": {
                    "identity_commitment": {
                        "recovery_config": dict(
                            _TEST_IDENTITY_RECOVERY_CONFIG
                        )
                    }
                },
            },
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


def test_offline_identity_rejects_recovery_config_change_within_episode(
    tmp_path: Path,
) -> None:
    d1 = VersionedEnvelope(
        sequence=1,
        topic="modules.d1.fused_tracks",
        source="D1",
        timestamp=0.1,
        schema_version="d1-scalable3d-fusion-v1",
        payload={"tracks": [], "observation_lineage": []},
    )

    def d2(sequence: int, max_age_s: float) -> VersionedEnvelope:
        config = {
            **_TEST_IDENTITY_RECOVERY_CONFIG,
            "max_recovery_evidence_age_seconds": max_age_s,
        }
        return VersionedEnvelope(
            sequence=sequence,
            topic="modules.d2.associated_tracks",
            source="D2",
            timestamp=float(sequence) / 10.0,
            schema_version="d2-scalable3d-association-v1",
            payload={
                "tracks": [],
                "identity_lineage": [],
                "association": {
                    "identity_commitment": {
                        "recovery_config": config,
                    }
                },
            },
        )

    with pytest.raises(
        ValueError,
        match="recovery config changed within the episode",
    ):
        write_offline_identity_evaluation(
            tmp_path,
            episode_id="recovery-config-change",
            messages=(d1, d2(2, 0.9), d2(3, 1.0)),
            offline_truth_labels=(),
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


def test_episode_records_explicit_truth_guard_treatment() -> None:
    config = ScenarioConfig(
        scenario_name="truth_guard_treatment",
        scenario_version="truth-guard-treatment-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.1,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )

    result = run_episode(
        config,
        online_truth_guard_implementation=(
            ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION
        ),
    )

    assert result.manifest.runtime_profile is not None
    assert result.manifest.runtime_profile[
        "online_truth_guard_implementation"
    ] == ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION
    assert result.summary["online_truth_guard_implementation"] == (
        ONLINE_TRUTH_GUARD_CANDIDATE_IMPLEMENTATION
    )
    diagnostics = result.summary["online_truth_guard_diagnostics"]
    assert diagnostics["candidate_enabled"] is True
    assert diagnostics["validation_count"] == len(result.online_messages)
    assert result.summary["online_truth_use_count"] == 0


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


def test_visual_scan_emits_one_truth_free_frame_event_per_active_camera() -> None:
    config = ScenarioConfig(
        target_count=2,
        resource_count=2,
        recon_count=1,
        duration_s=0.2,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=0.0,
        communication_enabled=False,
    )
    world = VectorizedPointMassWorld(config)
    scene = SensorScene(config)
    world.reset()
    scene.reset()

    batch = scene.visual_scan(world.snapshot())

    assert batch.measurements == ()
    assert len(batch.camera_frame_events) == 3
    assert all(event.empty for event in batch.camera_frame_events)
    assert {event.camera_id for event in batch.camera_frame_events} == {
        "CAM-INT-0001",
        "CAM-INT-0002",
        "CAM-RECON-001",
    }
    for event in batch.camera_frame_events:
        assert event.measurement_timestamp == 0.0
        assert event.arrival_timestamp == config.visual_latency_s
        assert event.detection_count == 0
        assert_online_payload_truth_free(event)


class _CameraFrameCaptureStack:
    def __init__(self) -> None:
        self.config: ScenarioConfig | None = None
        self.frame_events: list[CameraFrameEvent] = []

    def reset(self, config: ScenarioConfig) -> None:
        self.config = config
        self.frame_events.clear()

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        assert self.config is not None
        self.frame_events.extend(step_input.arrived_camera_frame_events)
        return RuntimeStepOutput(
            interceptor_acceleration_ned=np.zeros(
                (self.config.resource_count, 3)
            ),
            recon_acceleration_ned=np.zeros((self.config.recon_count, 3)),
        )


def test_zero_detection_camera_frame_survives_transport_without_truth() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=1,
        duration_s=0.35,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=0.0,
        communication_enabled=True,
        communication_drop_probability=0.0,
        communication_jitter_s=0.0,
    )
    stack = _CameraFrameCaptureStack()

    result = run_episode(config, module_stack=stack)

    assert stack.frame_events
    assert all(event.empty for event in stack.frame_events)
    assert all(
        event.arrival_timestamp
        >= event.measurement_timestamp
        + config.visual_latency_s
        + config.communication_latency_s
        for event in stack.frame_events
    )
    messages = [
        message
        for message in result.online_messages
        if message.topic == "sensor.camera_empty_frame"
    ]
    assert len(messages) >= len(stack.frame_events)
    assert {
        event.event_id for event in stack.frame_events
    }.issubset({message.payload.event_id for message in messages})
    assert result.summary["camera_empty_frame_generated_count"] > 0
    assert result.summary["camera_empty_frame_delivered_count"] == len(messages)
    assert result.summary["camera_empty_frame_dropped_count"] == 0
    assert result.summary["online_truth_use_count"] == 0


def test_dropped_zero_detection_frame_is_not_delivered_to_module_stack() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.25,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=0.0,
        communication_enabled=True,
        communication_drop_probability=1.0,
        communication_jitter_s=0.0,
    )
    stack = _CameraFrameCaptureStack()

    result = run_episode(config, module_stack=stack)

    assert stack.frame_events == []
    assert result.summary["camera_empty_frame_generated_count"] > 0
    assert result.summary["camera_empty_frame_queued_count"] == 0
    assert result.summary["camera_empty_frame_dropped_count"] > 0
    assert not any(
        message.topic == "sensor.camera_empty_frame"
        for message in result.online_messages
    )


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


class _CameraAckEvidenceStack(_StaleCameraCommandStack):
    def __init__(self) -> None:
        super().__init__()
        self.feedback_calls: list[dict[str, object]] = []

    def step(self, step_input: RuntimeStepInput) -> RuntimeStepOutput:
        output = super().step(step_input)
        return RuntimeStepOutput(
            interceptor_acceleration_ned=output.interceptor_acceleration_ned,
            recon_acceleration_ned=output.recon_acceleration_ned,
            camera_commands=output.camera_commands,
            publications=(
                RuntimePublication(
                    topic="modules.d5.active_vision",
                    source="D5",
                    schema_version="d5.active-vision-runtime.v1",
                    payload={
                        "timestamp": step_input.timestamp,
                        "command_count": len(output.camera_commands),
                        "commands": [
                            {
                                "camera_id": command.camera_id,
                                "communication_version": (
                                    command.communication_version
                                ),
                            }
                            for command in output.camera_commands
                        ],
                    },
                    copy_payload=False,
                ),
            ),
        )

    def record_active_vision_runtime_feedback(
        self,
        **kwargs: object,
    ) -> None:
        self.feedback_calls.append(dict(kwargs))


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


class _AssignmentPlanAckIntentStack(_AssignmentPlanAckStack):
    def __init__(self) -> None:
        super().__init__()
        self.recorded_acknowledgements: list[dict[str, object]] = []

    def record_assignment_plan_runtime_ack(
        self,
        *,
        acknowledgement: dict[str, object],
        acknowledgement_envelope: VersionedEnvelope,
        source_publication_envelopes: tuple[VersionedEnvelope, ...],
        timestamp_s: float,
        partition_generation: int,
    ) -> tuple[RuntimeCommunicationIntent, ...]:
        assert acknowledgement_envelope.topic == "runtime.assignment_plan_ack"
        assert acknowledgement_envelope.payload is acknowledgement
        assert {
            item.topic for item in source_publication_envelopes
        } == {
            "modules.d3.assignment_plan",
            "modules.d7.guidance_commands",
        }
        self.recorded_acknowledgements.append(dict(acknowledgement))
        return (
            RuntimeCommunicationIntent(
                source="C2",
                destination="D4-GATE",
                topic="test.assignment_owner_ack",
                schema_version="test-assignment-owner-ack-v1",
                payload={
                    "plan_id": acknowledgement["plan_id"],
                    "plan_version": acknowledgement["plan_version"],
                    "ack_bus_sequence": acknowledgement_envelope.sequence,
                    "ack_timestamp": timestamp_s,
                    "partition_generation": partition_generation,
                },
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


def test_camera_ack_is_published_before_runtime_feedback_is_recorded() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = _CameraAckEvidenceStack()

    result = run_episode(config, module_stack=stack)

    assert len(stack.feedback_calls) == 1
    callback = stack.feedback_calls[0]
    ack_envelope = callback["acknowledgement_envelopes"][0]
    source_envelope = callback["source_publication_envelopes"][0]
    assert source_envelope.topic == "modules.d5.active_vision"
    assert ack_envelope.topic == "runtime.camera_command_ack"
    assert source_envelope.sequence < ack_envelope.sequence
    assert ack_envelope in result.online_messages
    assert callback["source_git_commit"] == result.manifest.git_commit
    assert len(callback["pairing_context_sha256"]) == 64
    assert result.summary["learning_adoption_status"] == {
        "A1": "evidence_unavailable",
        "A2": "evidence_unavailable",
        "A3": "evidence_unavailable",
    }
    assert not any(
        result.summary["learning_adoption_audit"]["permissions"].values()
    )


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


def test_runtime_routes_post_assignment_ack_intents_through_network() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.05,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = _AssignmentPlanAckIntentStack()

    result = run_episode(config, module_stack=stack)

    assert len(stack.recorded_acknowledgements) == 1
    assert result.summary["assignment_plan_post_ack_intent_count"] == 1
    assert result.summary["communication_intent_issued_count"] == 1
    assert result.summary["communication_intent_topic_counts"] == {
        "test.assignment_owner_ack": 1
    }


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
