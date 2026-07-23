from __future__ import annotations

from collections import Counter
from dataclasses import replace
import csv
import json
from types import SimpleNamespace

import numpy as np
import pytest

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
    StructuralAmbiguityCandidateEdge,
    StructuralAmbiguityEvidence,
    StructuralAmbiguityMemberState,
    StructuralAmbiguityObservationEvidence,
    structural_ambiguity_member_track_token,
    structural_ambiguity_source_key,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner import (
    RegionalPlanAuthorityError,
)
from research_modules.d4_distributed_fallback.d4_distributed_fallback import (
    AdvisorMode,
    RecommendationSource,
    RegionResourceAdvisor,
    RegionResourceAdvisorConfig,
    RegionResourceProjectionConfig,
    RuleRegionResourcePolicy,
    RuleRegionResourcePolicyConfig,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.reporting import (
    STAGE_TIMING_SCHEMA_VERSION,
    write_batch_outputs,
)
from research_modules.scalable_3d_simulation.scenarios import make_curriculum_scenario


class _FiniteLearnedRegionPolicy:
    """Deterministic learned-policy stand-in for main bridge tests."""

    def __init__(self, projection: RegionResourceProjectionConfig) -> None:
        self._rule = RuleRegionResourcePolicy(
            RuleRegionResourcePolicyConfig(projection=projection)
        )

    def is_ood(self, snapshot, *, margin: float) -> bool:
        del snapshot, margin
        return False

    def recommend_raw(self, snapshot):
        rule = self._rule.recommend(snapshot)
        return replace(
            rule,
            policy_name="test-finite-region-policy",
            policy_version="v1",
            source=RecommendationSource.LEARNED,
            projected=False,
            model_sha256="a" * 64,
            fallback_reason=None,
        )


def _assist_region_advisor(*, ttl_s: float = 1.5) -> RegionResourceAdvisor:
    projection = RegionResourceProjectionConfig(advisory_ttl_s=ttl_s)
    return RegionResourceAdvisor(
        config=RegionResourceAdvisorConfig(
            mode=AdvisorMode.ASSIST,
            minimum_unseen_seeds=1,
            projection=projection,
        ),
        learned_policy=_FiniteLearnedRegionPolicy(projection),
    )


def test_recon_track_cues_are_fail_closed_by_default() -> None:
    assert IntegratedStackConfig().d5_recon_track_cues_enabled is False


def test_d1_radar_assignment_ambiguity_governance_v2_is_explicit_and_audited() -> None:
    default = IntegratedScalableModuleStack()
    default.reset(
        ScenarioConfig(
            scenario_name="d1_ambiguity_default",
            scenario_version="d1-ambiguity-default-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=13,
        )
    )
    default_audit = default.observation_governance_audit()
    assert (
        default_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_enabled"
        ]
        is False
    )
    assert (
        default_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_status"
        ]
        == "disabled"
    )
    assert (
        default_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_selected_policy_version"
        ]
        is None
    )

    experimental = IntegratedScalableModuleStack(
        config=IntegratedStackConfig(
            d1_radar_assignment_ambiguity_governance_v2=True
        )
    )
    experimental.reset(
        ScenarioConfig(
            scenario_name="d1_ambiguity_experimental",
            scenario_version="d1-ambiguity-experimental-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=0.2,
            seed=13,
        )
    )
    experimental_audit = experimental.observation_governance_audit()
    assert (
        experimental_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_enabled"
        ]
        is True
    )
    assert (
        experimental_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_governance_status"
        ]
        == "experimental_v2_enabled_rejected_candidate"
    )
    assert (
        experimental_audit["d1_fusion_association"][
            "radar_assignment_ambiguity_selected_policy_version"
        ]
        == "fail_closed_maximum_matching_allowed_edge_component_v2"
    )


@pytest.mark.parametrize("value", (None, 0, 1, "true"))
def test_d1_radar_assignment_ambiguity_governance_v2_requires_bool(
    value: object,
) -> None:
    with pytest.raises(
        TypeError,
        match="d1_radar_assignment_ambiguity_governance_v2 must be a bool",
    ):
        IntegratedStackConfig(
            d1_radar_assignment_ambiguity_governance_v2=value,  # type: ignore[arg-type]
        )


def _d1_track_stub(
    local_track_id: str,
    timestamp: float,
    position_ned: tuple[float, float, float],
) -> SimpleNamespace:
    observation_id = f"OBS-{local_track_id}-{timestamp:.3f}"
    state = np.array([*position_ned, 0.0, 0.0, 0.0], dtype=float)
    return SimpleNamespace(
        global_track_id=local_track_id,
        state=state,
        covariance=np.eye(6, dtype=float) * 4.0,
        timestamp=float(timestamp),
        metadata={
            "frame_id": "ned",
            "measurement_timestamp": float(timestamp),
            "arrival_timestamp": float(timestamp),
            "published_at": float(timestamp),
            "confidence": 1.0,
            "latest_observation_id": observation_id,
            "latest_measurement_timestamp": float(timestamp),
            "latest_sensor_id": "RADAR-TEST",
        },
    )


def _seed_d1_lineage_for_tracks(
    stack: IntegratedScalableModuleStack,
    tracks: tuple[SimpleNamespace, ...],
) -> None:
    for track in tracks:
        observation_id = str(track.metadata["latest_observation_id"])
        record = {
            "observation_id": observation_id,
            "measurement_timestamp": float(
                track.metadata["latest_measurement_timestamp"]
            ),
            "source_lineage": [
                "opaque_online_lineage",
                "sensor:RADAR-TEST",
                observation_id,
            ],
            "replay_generation": 0,
        }
        stack._d1_latest_lineage_by_observation[observation_id] = dict(
            record
        )
        stack._d1_pending_lineage_by_track.setdefault(
            str(track.global_track_id),
            {},
        )[observation_id] = dict(record)


def _structural_ambiguity_fixture(
    *,
    publisher_epoch: str,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> StructuralAmbiguityEvidence:
    local_ids = ("D1-LOCAL-A", "D1-LOCAL-B")
    positions = (
        np.array([100.0, -20.0, -10.0]),
        np.array([100.0, 20.0, -10.0]),
    )
    tokens = tuple(
        structural_ambiguity_member_track_token(
            DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
            publisher_epoch,
            local_id,
        )
        for local_id in local_ids
    )
    members = tuple(
        StructuralAmbiguityMemberState(
            opaque_member_track_token=token,
            source_key=structural_ambiguity_source_key(
                DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
                publisher_epoch,
                token,
            ),
            state=np.concatenate((position, np.zeros(3, dtype=float))),
            covariance=np.eye(6, dtype=float) * 4.0,
        )
        for token, position in zip(tokens, positions, strict=True)
    )
    observation_keys = (
        f"d1-observation-sha256:{1:064x}",
        f"d1-observation-sha256:{2:064x}",
    )
    observations = tuple(
        StructuralAmbiguityObservationEvidence(
            observation_evidence_key=key,
            position_ned=position,
            covariance_ned=np.eye(3, dtype=float) * 4.0,
            radial_velocity_observed=False,
            birth_deferred=False,
        )
        for key, position in zip(observation_keys, positions, strict=True)
    )
    edges = tuple(
        StructuralAmbiguityCandidateEdge(
            opaque_member_track_token=token,
            observation_evidence_key=observation_key,
            nis=1.0 if member_index == observation_index else 2.0,
            gate_threshold=40.0,
            edge_roles=(
                ("matched_reference", "maximum_matching_allowed")
                if member_index == observation_index
                else ("alternating_cycle", "maximum_matching_allowed")
            ),
        )
        for member_index, token in enumerate(tokens)
        for observation_index, observation_key in enumerate(observation_keys)
    )
    return StructuralAmbiguityEvidence(
        evidence_id=f"d1-evidence-sha256:{3:064x}",
        component_id=f"d1-component-sha256:{4:064x}",
        component_generation=1,
        publisher_node_id=DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID,
        publisher_epoch=publisher_epoch,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        state_valid_timestamp=measurement_timestamp,
        published_at=arrival_timestamp,
        sensor_id="radar-main",
        scan_id=f"d1-scan-sha256:{5:064x}",
        member_states=members,
        observations=observations,
        candidate_edges=edges,
        component_kinds=("alternating_cycle",),
        member_count=2,
        observation_count=2,
        candidate_edge_count=4,
        free_row_count=0,
        free_column_count=0,
        maximum_matching_cardinality=2,
    )


def test_atomic_d1_d2_ambiguity_hold_consumes_delayed_sidecar_once() -> None:
    stack = IntegratedScalableModuleStack(
        config=IntegratedStackConfig(
            d1_d2_structural_ambiguity_hold_enabled=True,
        )
    )
    stack.reset(
        ScenarioConfig(
            scenario_name="main_ambiguity_hold_bridge_2v2",
            scenario_version="main-ambiguity-hold-bridge-v1",
            target_count=2,
            resource_count=2,
            recon_count=1,
            region_count=1,
            duration_s=1.0,
            radar_period_s=0.2,
            association_period_s=0.2,
            seed=31,
        )
    )
    assert (
        stack.d2.ambiguity_hold_config.max_component_age_seconds
        == pytest.approx(5.4)
    )
    assert (
        stack.d2.identity_commitment_recovery_config.config_version
        == "main-scalable3d-identity-recovery-publication-freshness-v1"
    )
    assert (
        stack.d2.identity_commitment_recovery_config
        .max_recovery_evidence_age_seconds
        == pytest.approx(
            stack.config.identity_lineage_freshness_budget_s
        )
    )
    publications = []
    positions = (
        (100.0, -20.0, -10.0),
        (100.0, 20.0, -10.0),
    )
    for generation, timestamp in enumerate((0.0, 0.2), start=1):
        tracks = tuple(
            _d1_track_stub(local_id, timestamp, position)
            for local_id, position in zip(
                ("D1-LOCAL-A", "D1-LOCAL-B"),
                positions,
                strict=True,
            )
        )
        stack.latest_d1_tracks = tracks
        _seed_d1_lineage_for_tracks(stack, tracks)
        if generation == 2:
            for track in tracks:
                stale_id = f"OBS-STALE-{track.global_track_id}"
                stack._d1_pending_lineage_by_track[
                    str(track.global_track_id)
                ][stale_id] = {
                    "observation_id": stale_id,
                    "measurement_timestamp": 0.1,
                    "source_lineage": [stale_id],
                    "replay_generation": 0,
                }
        stack._d1_posterior_generation = generation
        assert stack._associate_latest_d1_tracks(
            publications,
            publication_timestamp=timestamp,
            timing_stage="test_d2_seed",
            source_d1_posterior_generation=generation,
        )

    committed_lineage = publications[-1].payload["identity_lineage"]
    assert all(
        {
            item["measurement_timestamp"]
            for item in track_item["source_observations"]
        }
        == {0.1, 0.2}
        for track_item in committed_lineage
    )
    before = {
        track.global_track_id: (
            track.hits,
            track.misses,
            float(np.trace(track.covariance)),
        )
        for track in stack.d2.active_tracks()
    }
    evidence = _structural_ambiguity_fixture(
        publisher_epoch=stack._d1_publisher_epoch,
        measurement_timestamp=0.4,
        arrival_timestamp=0.65,
    )
    stack._latch_structural_ambiguity_evidence(
        SimpleNamespace(structural_ambiguity_evidence=(evidence,))
    )
    tracks = tuple(
        _d1_track_stub(local_id, 0.65, position)
        for local_id, position in zip(
            ("D1-LOCAL-A", "D1-LOCAL-B"),
            positions,
            strict=True,
        )
    )
    stack.latest_d1_tracks = tracks
    _seed_d1_lineage_for_tracks(stack, tracks)
    stack._d1_posterior_generation = 3

    assert stack._associate_latest_d1_tracks(
        publications,
        publication_timestamp=0.65,
        timing_stage="test_d2_hold",
        source_d1_posterior_generation=3,
    )

    hold = stack.latest_d2_result.metadata["ambiguity_hold"]
    assert hold["accepted_component_count"] == 1
    assert hold["active_component_count"] == 1
    assert len(hold["hold_track_ids"]) == 2
    assert stack._pending_structural_ambiguity_evidence == {}
    assert stack._structural_ambiguity_evidence_received_count == 1
    assert stack._structural_ambiguity_evidence_consumed_count == 1
    assert stack._structural_ambiguity_d2_consumption_count == 1
    lineage = stack._d2_identity_lineage_payload(
        stack.latest_d2_result
    )
    assert lineage
    assert {
        item["identity_commitment"]["identity_commitment_state"]
        for item in lineage
    } == {"identity_uncommitted_ambiguity_hold"}
    assert all(item["source_observations"] == [] for item in lineage)
    for track in stack.d2.active_tracks():
        previous_hits, previous_misses, previous_trace = before[
            track.global_track_id
        ]
        assert track.hits == previous_hits
        assert track.misses == previous_misses
        assert float(np.trace(track.covariance)) >= previous_trace


def test_atomic_ambiguity_treatment_rejects_partial_or_invalid_config() -> None:
    with pytest.raises(
        ValueError,
        match="cannot both be enabled",
    ):
        IntegratedStackConfig(
            d1_radar_assignment_ambiguity_governance_v2=True,
            d1_d2_structural_ambiguity_hold_enabled=True,
        )
    with pytest.raises(
        ValueError,
        match="hard hold cannot be shorter",
    ):
        IntegratedStackConfig(
            d2_ambiguity_hold_gap_scan_periods=5,
            d2_ambiguity_hold_hard_scan_periods=2,
        )


def test_d2_consumes_pending_d1_posterior_at_next_association_tick() -> None:
    config = ScenarioConfig(
        scenario_name="pending_d1_to_d2_schedule_3v3",
        scenario_version="pending-d1-to-d2-schedule-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )

    result = run_episode(config, module_stack=IntegratedScalableModuleStack())

    scheduled_d2 = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
        and abs(message.timestamp - 1.0) <= 1.0e-9
    )
    assert len(scheduled_d2) == 1
    d2_publications = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
    )
    consumed_generations = tuple(
        int(message.payload["source_d1_posterior_generation"])
        for message in d2_publications
    )
    assert consumed_generations == tuple(sorted(set(consumed_generations)))
    assert not any(
        abs(message.timestamp - 1.05) <= 1.0e-9
        for message in d2_publications
    )
    assert min(
        float(track["timestamp"])
        for track in scheduled_d2[0].payload["tracks"]
    ) > 0.4

    scheduled_guidance = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and abs(message.timestamp - 1.0) <= 1.0e-9
    )
    assert all(
        command["gate_reason"] != "global_track_stale"
        for command in scheduled_guidance.payload["commands"]
    )
    full_d1_publications = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d1.fused_tracks"
        and message.payload["tracks_materialized"]
    )
    d1_generations = tuple(
        int(message.payload["posterior_generation"])
        for message in full_d1_publications
    )
    assert d1_generations == tuple(range(1, len(d1_generations) + 1))
    assert set(consumed_generations).issubset(set(d1_generations))

    governance = result.observation_governance_audit
    assert governance["schema_version"] == (
        "scalable3d-observation-governance-runtime-v2"
    )
    assert governance["d1_posterior_generation"] == d1_generations[-1]
    assert governance["d2_consumed_d1_posterior_generation"] == (
        consumed_generations[-1]
    )
    assert governance["d2_posterior_consumption_count"] == len(
        d2_publications
    )
    assert governance["d2_pending_d1_posterior_generation"] is None
    assert governance["d2_pre_tick_posterior_merge_count"] >= 1


def test_finalize_consumes_pending_d1_posterior_without_emitting_control() -> None:
    config = ScenarioConfig(
        scenario_name="pending_d1_finalize_3v3",
        scenario_version="pending-d1-finalize-v1",
        target_count=3,
        resource_count=3,
        recon_count=1,
        region_count=2,
        duration_s=0.95,
        seed=7,
        radar_detection_probability=1.0,
    )

    result = run_episode(config, module_stack=IntegratedScalableModuleStack())

    final_d2 = tuple(
        message
        for message in result.online_messages
        if message.topic == "modules.d2.associated_tracks"
        and abs(message.timestamp - config.duration_s) <= 1.0e-9
    )
    assert len(final_d2) == 1
    final_generation = int(
        final_d2[0].payload["source_d1_posterior_generation"]
    )
    full_d1_generations = tuple(
        int(message.payload["posterior_generation"])
        for message in result.online_messages
        if message.topic == "modules.d1.fused_tracks"
        and message.payload["tracks_materialized"]
    )
    assert final_generation == full_d1_generations[-1]
    assert not any(
        message.topic in {
            "modules.d5.active_vision",
            "modules.d7.guidance_commands",
        }
        and abs(message.timestamp - config.duration_s) <= 1.0e-9
        for message in result.online_messages
    )
    governance = result.observation_governance_audit
    assert governance["d2_pending_d1_posterior_generation"] is None
    assert governance["d2_consumed_d1_posterior_generation"] == (
        governance["d1_posterior_generation"]
    )


def test_5v5_online_stack_connects_d1_to_d7_without_truth_identity(tmp_path) -> None:
    config = ScenarioConfig(
        scenario_name="integrated_5v5",
        scenario_version="integrated-5v5-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d5_recon_track_cues_enabled=True)
    )

    result = run_episode(config, module_stack=stack, output_dir=tmp_path)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert result.d1_consistency_evidence_records
    d1_publications = tuple(
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d1.fused_tracks"
    )
    assert d1_publications
    state_only = tuple(
        payload
        for payload in d1_publications
        if not payload["tracks_materialized"]
    )
    full_snapshots = tuple(
        payload for payload in d1_publications if payload["tracks_materialized"]
    )
    assert state_only
    assert len(full_snapshots) == len(
        {payload["summary"]["published_at"] for payload in d1_publications}
    )
    assert all(
        payload["snapshot_kind"] == "state_update"
        and payload["tracks"] == []
        and payload["track_count"] == 0
        and payload["current_track_count"] > 0
        for payload in state_only
    )
    assert all(
        payload["snapshot_kind"] == "full_posterior"
        and payload["track_count"] == payload["current_track_count"]
        and payload["track_count"] == len(payload["tracks"])
        for payload in full_snapshots
    )
    published_observation_ids = {
        item["observation_id"]
        for payload in d1_publications
        for item in payload["observation_lineage"]
    }
    assert published_observation_ids == {
        item.observation_id for item in result.d1_consistency_evidence_records
    }
    assert result.observation_governance_audit["d1_state_only_scan_count"] == len(
        state_only
    )
    assert result.observation_governance_audit[
        "d1_materialized_snapshot_count"
    ] == len(full_snapshots)
    final_diagnostics = result.summary["module_final_diagnostics"]
    assert final_diagnostics["d1_fusion_performance"]["current_track_count"] == 5
    assert final_diagnostics["d5_terminal_performance"]["process_frame_count"] > 0
    assert final_diagnostics["d5_terminal_performance"]["graph_build_count"] > 0
    assert len(stack.latest_d1_tracks) == 5
    assert len(stack.latest_d2_tracks) == 5
    assert len(stack.latest_plan.assignments) == 5
    assert stack.latest_plan.unassigned_target_ids == ()
    assert len(stack.latest_guidance_batch.pair_commands) == 5
    assert all(
        command.mode.value == "midcourse_pn_3d"
        for command in stack.latest_guidance_batch.pair_commands
    )
    topics = {message.topic for message in result.online_messages}
    assert {
        "modules.d1.fused_tracks",
        "modules.d2.associated_tracks",
        "modules.d3.assignment_plan",
        "modules.d4.regional_failover",
        "modules.d5.terminal_association",
        "modules.d5.active_vision",
        "modules.d7.guidance_commands",
    }.issubset(topics)
    d5_payload = next(
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.terminal_association"
    )
    assert "all_possible_camera_pairs" in d5_payload["diagnostics"]
    assert "candidate_tracklet_edges" in d5_payload["diagnostics"]
    assert stack.latest_d5_result is not None
    assert all(
        tracklet.local_track_id.startswith("trk-")
        for tracklet in stack.latest_d5_result.tracklets
    )
    center_ids = {track.global_track_id for track in stack.latest_d2_tracks}
    assert {
        binding.global_track_id
        for binding in stack.latest_d5_result.association.bindings
        if binding.global_track_id is not None
    }.issubset(center_ids)
    active_vision_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d5.active_vision"
    ]
    assert active_vision_payloads
    assert result.summary["camera_command_issued_count"] > 0
    assert result.summary["camera_command_applied_count"] == result.summary[
        "camera_command_issued_count"
    ]
    assert result.summary["camera_command_rejected_count"] == 0
    assert all(
        command["target_global_track_id"] is None
        or command["target_global_track_id"] in center_ids
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    assert all(
        not str(command["target_global_track_id"]).startswith("TGT-")
        for payload in active_vision_payloads
        for command in payload["commands"]
    )
    assert stack.latest_active_vision_snapshot is not None
    recon_targets = stack.latest_active_vision_snapshot.assigned_target_ids(
        "CAM-RECON-001"
    )
    assert len(recon_targets) == 1
    assert set(recon_targets).issubset(center_ids)
    assert stack.latest_active_vision_recon_cue_count == 1
    assert all(not target_id.startswith("TGT-") for target_id in recon_targets)
    camera_acks = [
        message.payload
        for message in result.online_messages
        if message.topic == "runtime.camera_command_ack"
    ]
    assert len(camera_acks) == result.summary["camera_command_ack_count"]
    assert {ack["status"] for ack in camera_acks} == {"applied"}
    timings = {item.stage: item for item in result.stage_timings}
    assert timings["module.d1_fusion"].call_count > 0
    assert timings["module.d3_assignment"].wall_time_s > 0.0
    assert timings["module.main_d4_adapter"].mean_wall_time_ms > 0.0
    fusion_timing = timings["module.d1_fusion"]
    assert fusion_timing.distribution_available is True
    assert fusion_timing.distribution_unavailable_reason is None
    assert (
        0.0
        < fusion_timing.p50_wall_time_ms
        <= fusion_timing.p95_wall_time_ms
        <= fusion_timing.max_wall_time_ms
    )
    with (tmp_path / "stage_timings.csv").open(
        newline="",
        encoding="utf-8",
    ) as stream:
        timing_rows = list(csv.DictReader(stream))
    fusion_row = next(
        row for row in timing_rows if row["stage"] == "module.d1_fusion"
    )
    assert fusion_row["schema_version"] == STAGE_TIMING_SCHEMA_VERSION
    assert fusion_row["distribution_available"] == "True"
    assert fusion_row["distribution_unavailable_reason"] == ""
    assert float(fusion_row["p50_wall_time_ms"]) > 0.0
    assert float(fusion_row["p95_wall_time_ms"]) >= float(
        fusion_row["p50_wall_time_ms"]
    )
    assert float(fusion_row["max_wall_time_ms"]) >= float(
        fusion_row["p95_wall_time_ms"]
    )
    report = (tmp_path / "SCALABLE_3D_EPISODE_REPORT_CN.md").read_text(
        encoding="utf-8"
    )
    assert "本次启用 D1-D7 规则集成栈" in report
    assert "D1/D2 航迹数分别为 5/5" in report
    online_lines = (tmp_path / "online_observations.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    d1_lines = (tmp_path / "offline_identity" / "online_d1_records.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    d2_lines = (tmp_path / "offline_identity" / "online_d2_records.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert d1_lines == [
        line
        for line in online_lines
        if json.loads(line)["topic"] == "modules.d1.fused_tracks"
    ]
    assert d2_lines == [
        line
        for line in online_lines
        if json.loads(line)["topic"] == "modules.d2.associated_tracks"
    ]
    with (tmp_path / "post_run_timings.csv").open(
        newline="", encoding="utf-8"
    ) as stream:
        post_run_rows = list(csv.DictReader(stream))
    assert {row["stage"] for row in post_run_rows}.issuperset(
        {
            "online_bus_and_identity_views",
            "offline_identity",
            "offline_consistency",
            "d6_runtime_plan_outcomes",
            "total_before_timing_artifact",
        }
    )
    assert {
        row["schema_version"] for row in post_run_rows
    } == {"scalable3d-post-run-timings-v1"}
    assert all(float(row["wall_time_s"]) >= 0.0 for row in post_run_rows)
    consistency_manifest = json.loads(
        (tmp_path / "offline_consistency" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    consistency_result = json.loads(
        (tmp_path / "offline_consistency" / "offline_result.json").read_text(
            encoding="utf-8"
        )
    )
    d2_lineage_mapping = json.loads(
        (tmp_path / "offline_consistency" / "d2_lineage_mapping.json").read_text(
            encoding="utf-8"
        )
    )
    assert consistency_manifest["status"] == "available"
    assert consistency_manifest["truth_metrics_available"] is True
    assert consistency_manifest["mapping_audit"]["available"] is True
    assert consistency_manifest["mapping_audit"]["policy"] == (
        "d2_source_observation_exact_join_v1"
    )
    assert all(
        value.startswith("sha256:")
        for value in consistency_manifest["source_hashes"].values()
    )
    assert consistency_result["metrics"]["position_rmse_m"]["available"] is True
    assert consistency_result["metrics"]["mean_nees"]["available"] is True
    assert d2_lineage_mapping["producer_role"] == "d2_evaluator_only"
    assert d2_lineage_mapping["mapping_count"] >= 5
    d6_record = json.loads(
        (tmp_path / "d6_truth_isolated" / "episode_record.json").read_text(
            encoding="utf-8"
        )
    )
    assert d6_record["d1_consistency"]["status"] == "available"
    assert d6_record["d2_identity"]["id_switch_count"] == 0
    assert d6_record["d2_identity"]["id_switch_count_availability"] == (
        "available"
    )
    assert d6_record["d2_identity"]["truth_isolation_verified"] is True
    runtime_root = tmp_path / "d6_runtime_plan_outcomes"
    runtime_inputs = json.loads(
        (runtime_root / "input_specification.json").read_text(encoding="utf-8")
    )
    runtime_result = json.loads(
        (runtime_root / "runtime_plan_outcome_join.json").read_text(
            encoding="utf-8"
        )
    )
    runtime_manifest = json.loads(
        (runtime_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert len(runtime_inputs["artifacts"]) == 11
    assert all(
        not item["path"].startswith("/")
        and item["sha256"].startswith("sha256:")
        for item in runtime_inputs["artifacts"].values()
    )
    assert runtime_result["runtime_ack_evidence"]["ack_count"] >= 1
    assert runtime_result["runtime_ack_evidence"]["binding_count"] >= 5
    assert runtime_result["runtime_ack_evidence"]["online_truth_use_count"] == 0
    assert runtime_result["admission"]["ppo_allowed"] is False
    assert runtime_result["admission"]["assist_allowed"] is False
    assert runtime_result["admission"]["authority_allowed"] is False
    assert runtime_result["admission"]["rule_fallback_required"] is True
    assert runtime_manifest["runtime_assignment_plan_ack_count"] == (
        result.summary["assignment_plan_ack_count"]
    )
    assert runtime_manifest["admission"] == {
        "assist_allowed": False,
        "authority_allowed": False,
        "ppo_allowed": False,
        "rule_fallback_required": True,
        "status": "runtime_observed_diagnostic_only_admission_closed",
    }
    governance = result.observation_governance_audit
    assert governance is not None
    assert governance["online_truth_use_count"] == 0
    assert governance["d1_scan_input"]["closed"] is True
    assert governance["d1_scan_input"]["current_buffered_scan_count"] == 0
    ledger = governance["d2_claim_ledger"]
    assert ledger["current_count"] <= ledger["max_count"]
    assert ledger["peak_count"] <= ledger["max_count"]
    governance_manifest = json.loads(
        (
            tmp_path
            / "observation_governance"
            / "observation_governance_manifest.json"
        ).read_text(encoding="utf-8")
    )
    governance_online = json.loads(
        (
            tmp_path
            / "observation_governance"
            / "observation_governance_online_audit.json"
        ).read_text(encoding="utf-8")
    )
    governance_aggregate = json.loads(
        (
            tmp_path
            / "observation_governance"
            / "d6_report"
            / "observation_governance_aggregate.json"
        ).read_text(encoding="utf-8")
    )
    assert governance_manifest["online_truth_use_count"] == 0
    assert governance_online["online_truth_use_count"] == 0
    assert governance_online["d1_scan_oosm_audit"]["metrics"][
        "current_oosm_buffer_count"
    ]["value"] == 0
    assert governance_aggregate["episode_count"] == 1
    assert governance_aggregate["truth_isolation"]["online_truth_use_count"] == 0


def test_d1_same_time_snapshot_coalescing_preserves_final_module_state() -> None:
    config = ScenarioConfig(
        scenario_name="d1_snapshot_coalescing_equivalence",
        scenario_version="d1-snapshot-coalescing-equivalence-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=7,
        radar_detection_probability=1.0,
    )
    baseline = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_coalesce_same_fusion_time=False)
    )
    candidate = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_coalesce_same_fusion_time=True)
    )

    baseline_result = run_episode(config, module_stack=baseline)
    candidate_result = run_episode(config, module_stack=candidate)

    assert candidate_result.observation_governance_audit[
        "d1_state_only_scan_count"
    ] > 0
    assert baseline_result.observation_governance_audit[
        "d1_state_only_scan_count"
    ] == 0
    assert candidate_result.observation_governance_audit[
        "d1_materialized_snapshot_count"
    ] < baseline_result.observation_governance_audit[
        "d1_materialized_snapshot_count"
    ]
    assert tuple(track.global_track_id for track in candidate.latest_d1_tracks) == tuple(
        track.global_track_id for track in baseline.latest_d1_tracks
    )
    for candidate_track, baseline_track in zip(
        candidate.latest_d1_tracks,
        baseline.latest_d1_tracks,
        strict=True,
    ):
        assert candidate_track.timestamp == baseline_track.timestamp
        np.testing.assert_array_equal(candidate_track.state, baseline_track.state)
        np.testing.assert_array_equal(
            candidate_track.covariance,
            baseline_track.covariance,
        )
        assert candidate_track.track_level == baseline_track.track_level
    assert tuple(track.global_track_id for track in candidate.latest_d2_tracks) == tuple(
        track.global_track_id for track in baseline.latest_d2_tracks
    )
    for candidate_track, baseline_track in zip(
        candidate.latest_d2_tracks,
        baseline.latest_d2_tracks,
        strict=True,
    ):
        np.testing.assert_array_equal(candidate_track.state, baseline_track.state)
        np.testing.assert_array_equal(
            candidate_track.covariance,
            baseline_track.covariance,
        )
        assert candidate_track.lifecycle_state == baseline_track.lifecycle_state
    assert candidate.latest_plan.execution_signature() == (
        baseline.latest_plan.execution_signature()
    )
    np.testing.assert_array_equal(
        candidate.latest_guidance_batch.acceleration_ned_mps2,
        baseline.latest_guidance_batch.acceleration_ned_mps2,
    )
    assert tuple(
        replace(command, plan_id="")
        for command in candidate.latest_guidance_batch.pair_commands
    ) == tuple(
        replace(command, plan_id="")
        for command in baseline.latest_guidance_batch.pair_commands
    )
    assert [
        item.to_dict() for item in candidate_result.d1_consistency_evidence_records
    ] == [
        item.to_dict() for item in baseline_result.d1_consistency_evidence_records
    ]


def test_d6_batch_aggregates_distinct_seed_episode_artifacts(tmp_path) -> None:
    results = []
    for seed in (31, 32):
        config = ScenarioConfig(
            scenario_name="d6_batch_3v3",
            scenario_version="d6-batch-3v3-v1",
            target_count=3,
            resource_count=3,
            recon_count=1,
            duration_s=0.8,
            seed=seed,
            radar_detection_probability=1.0,
            visual_detection_probability=1.0,
            visual_false_alarm_rate=0.0,
            communication_enabled=False,
        )
        results.append(
            run_episode(
                config,
                module_stack=IntegratedScalableModuleStack(),
                output_dir=tmp_path / f"seed_{seed}",
            )
        )

    paths = write_batch_outputs(results, tmp_path / "batch")

    aggregate = json.loads(
        paths["d6_truth_isolated_batch_aggregate_json"].read_text(
            encoding="utf-8"
        )
    )
    assert aggregate["episode_count"] == 2
    assert aggregate["scale_values"] == [3]
    assert len(aggregate["groups"]) == 1
    group = aggregate["groups"][0]
    assert group["episode_count"] == 2
    assert group["seed_count"] == 2
    assert group["metrics"]["d2.id_switch_count"]["episode_value_count"] == 2


def test_200v200_stack_uses_sparse_candidates_and_commands_every_assignment() -> None:
    config = ScenarioConfig(
        scenario_name="integrated_200v200_smoke",
        scenario_version="integrated-200v200-smoke-v1",
        target_count=200,
        resource_count=200,
        recon_count=8,
        region_count=8,
        duration_s=0.45,
        seed=17,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        communication_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    assert result.summary["finite_state"] is True
    assert result.summary["online_truth_use_count"] == 0
    assert len(stack.latest_d1_tracks) == 200
    assert len(stack.latest_d2_tracks) == 200
    assert len(stack.latest_plan.assignments) == 200
    assert stack.latest_plan.unassigned_target_ids == ()
    assert stack.latest_plan.metadata["candidate_full_edge_count"] == 40_000
    assert stack.latest_plan.metadata["candidate_edge_count"] == 6_400
    assert len(stack.latest_guidance_batch.pair_commands) == 200
    assert stack.latest_guidance_batch.acceleration_ned_mps2.shape == (200, 3)


def test_center_failure_reissues_a_secondary_owned_plan_before_guidance_continues() -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    config = replace(
        config,
        metadata={
            **config.metadata,
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ],
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[0]["summary"]["selected_layer_counts"]["center"] == 8
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["secondary"] == 8
    assert d4_payloads[-1]["summary"]["execution_allowed_region_count"] == 8
    assert stack.latest_plan.version == 2
    assert stack.latest_plan.metadata["active_plan_owner"] == "secondary"
    assert stack.latest_plan.metadata["owner_node_id"] == "RECON-001"
    assert all(
        command.mode.value == "midcourse_pn_3d"
        for command in stack.latest_guidance_batch.pair_commands
    )


def test_secondary_failure_reissues_a_distributed_regional_plan() -> None:
    config = make_curriculum_scenario(
        "secondary_failure",
        scale=5,
        seed=4,
        duration_s=4.4,
    )
    # Radar arrives later than the faster vision stream in this scenario. Keep
    # the production lateness window so valid radar scans survive reordering
    # while the distributed handover is exercised.
    stack = IntegratedScalableModuleStack()

    result = run_episode(config, module_stack=stack)

    d4_payloads = [
        message.payload
        for message in result.online_messages
        if message.topic == "modules.d4.regional_failover"
    ]
    assert d4_payloads[-1]["summary"]["selected_layer_counts"]["distributed"] == 8
    active_regions = [
        item for item in d4_payloads[-1]["regions"] if item["task_ids"]
    ]
    assert len(active_regions) == 5
    assert all(item["execution_allowed"] for item in active_regions)
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["regional_owner_layers"] == ("distributed",)
    assert stack.latest_plan.metadata["regional_single_member_authority_count"] == 5
    assert stack.latest_plan.metadata["regional_atomic_coalition_commit_count"] == 0
    assert all(
        assignment.metadata["regional_owner_layer"] == "distributed"
        for assignment in stack.latest_plan.assignments
    )
    distributed_plan = next(
        message
        for message in reversed(result.online_messages)
        if message.topic == "modules.d3.assignment_plan"
        and tuple(
            message.payload["metadata"].get("regional_owner_layers", ())
        ) == ("distributed",)
    )
    distributed_guidance = next(
        message
        for message in result.online_messages
        if message.topic == "modules.d7.guidance_commands"
        and abs(message.timestamp - distributed_plan.timestamp) <= 1.0e-9
    )
    assert Counter(
        command["mode"] for command in distributed_guidance.payload["commands"]
    ) == {"midcourse_pn_3d": 5}
    distributed_ack = next(
        message
        for message in result.online_messages
        if message.topic == "runtime.assignment_plan_ack"
        and abs(message.timestamp - distributed_plan.timestamp) <= 1.0e-9
    )
    assert distributed_ack.payload["held_binding_count"] == 0
    assert Counter(
        (command.mode.value, command.gate_reason)
        for command in stack.latest_guidance_batch.pair_commands
    ) == {("hold", "global_track_stale"): 5}
    assert stack._regional_plan_rejection_reason is None
    target_id = stack.latest_plan.assignments[0].target_id
    permission = stack._d4_permission(target_id)
    assert permission.action == "continue"
    assert permission.mode == "distributed"
    assert permission.atomic_coalition_formed is None
    assert permission.coalition_commit_state == "single_member_authorized"
    assert permission.metadata["commit_required"] is False


def test_two_secondary_nodes_publish_one_multi_owner_regional_plan() -> None:
    config = ScenarioConfig(
        scenario_name="multi_secondary_50v50",
        scenario_version="multi-secondary-50v50-v1",
        target_count=50,
        resource_count=50,
        recon_count=2,
        region_count=8,
        duration_s=2.4,
        seed=13,
        interceptor_speed_mps=30.0,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
        metadata={
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ]
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )

    result = run_episode(config, module_stack=stack)

    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_plan.metadata["active_plan_owner"] == "regional"
    assert stack.latest_plan.metadata["regional_owner_layers"] == ("secondary",)
    assert stack.latest_plan.metadata["regional_owner_node_ids"] == (
        "RECON-001",
        "RECON-002",
    )
    assert stack.latest_plan.metadata["regional_single_member_authority_count"] == 50
    assert stack.latest_plan.metadata["regional_atomic_coalition_commit_count"] == 0
    assert {
        assignment.target_id for assignment in stack.latest_plan.assignments
    } == {track.global_track_id for track in stack.latest_d2_tracks}
    assert Counter(
        command.mode.value for command in stack.latest_guidance_batch.pair_commands
    ) == {"midcourse_pn_3d": 50}
    assert stack._regional_plan_rejection_reason is None


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("expired", "regional_d4_authority_lease_expired"),
        ("missing_commit", "regional_d4_commit_evidence_missing"),
        ("stale_source", "regional_d4_stale_source_plan"),
    ),
)
def test_regional_authority_adapter_rejects_incomplete_d4_evidence(
    mutation: str,
    expected_reason: str,
) -> None:
    config = make_curriculum_scenario(
        "center_failure",
        scale=5,
        seed=3,
        duration_s=1.2,
    )
    config = replace(
        config,
        metadata={
            **config.metadata,
            "fault_schedule": [
                {"time_s": 0.6, "component": "center", "action": "failed"}
            ],
        },
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0)
    )
    run_episode(config, module_stack=stack)

    target_ids = {track.global_track_id for track in stack.latest_d2_tracks}
    now = 1.1
    if mutation == "expired":
        now = 10.0
    else:
        decisions = list(stack.latest_d4_decision.region_decisions)
        index = next(
            index for index, item in enumerate(decisions) if item.task_ids
        )
        selected = decisions[index]
        if mutation == "missing_commit":
            selected = replace(selected, coalition_commits=())
        else:
            selected = replace(
                selected,
                ownership=replace(
                    selected.ownership,
                    plan_version=selected.ownership.plan_version - 1,
                ),
            )
        decisions[index] = selected
        stack.latest_d4_decision = replace(
            stack.latest_d4_decision,
            region_decisions=tuple(decisions),
        )

    with pytest.raises(RegionalPlanAuthorityError) as error:
        stack._regional_authority_from_d4(
            stack.latest_plan,
            target_ids=target_ids,
            now=now,
        )
    assert error.value.reason == expected_reason


def test_d4_assist_advisory_is_consumed_once_by_next_center_plan() -> None:
    config = ScenarioConfig(
        scenario_name="d4_d3_next_cycle_bridge",
        scenario_version="d4-d3-next-cycle-bridge-v1",
        target_count=5,
        resource_count=5,
        recon_count=1,
        region_count=2,
        duration_s=1.2,
        seed=41,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )

    result = run_episode(config, module_stack=stack)

    assert result.summary["online_truth_use_count"] == 0
    assert stack.latest_d4_region_consumption is not None
    assert stack.latest_d4_region_consumption.consumable is True
    assert stack.latest_plan.metadata["regional_hint_applied"] is True
    assert stack.latest_plan.metadata["regional_hint_advisory_version"] == 1
    consumption_payloads = [
        item.payload
        for item in result.online_messages
        if item.topic == "modules.d4.region_resource_consumption"
    ]
    assert len(consumption_payloads) == 1
    assert consumption_payloads[0]["consumable"] is True
    assert consumption_payloads[0]["d3_hint_applied"] is True
    assert consumption_payloads[0]["bridge_rejection_reason"] is None


def test_d4_advisory_bridge_rejects_replay_and_strict_expiry() -> None:
    config = ScenarioConfig(
        scenario_name="d4_advisory_replay",
        scenario_version="d4-advisory-replay-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.8,
        seed=42,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0),
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )
    run_episode(config, module_stack=stack)
    advice = stack.latest_d4_region_advice
    snapshot = stack.latest_d4_region_snapshot
    decision = stack.latest_d4_decision
    plan = stack.latest_plan
    advisory = advice.advisory_contract

    hint = stack._d3_regional_hint_from_previous_d4(
        previous_plan=plan,
        advice_result=advice,
        source_snapshot=snapshot,
        source_decision=decision,
        now=advisory.created_at_s + 0.1,
        fault_generation_changed=False,
    )
    assert hint is not None
    replay = stack._d3_regional_hint_from_previous_d4(
        previous_plan=plan,
        advice_result=advice,
        source_snapshot=snapshot,
        source_decision=decision,
        now=advisory.created_at_s + 0.2,
        fault_generation_changed=False,
    )
    assert replay is None
    assert "advisory_already_consumed" in (
        stack._d4_region_hint_bridge_rejection_reason or ""
    )

    expiry_stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0),
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )
    run_episode(config, module_stack=expiry_stack)
    expiry_advice = expiry_stack.latest_d4_region_advice
    expired = expiry_stack._d3_regional_hint_from_previous_d4(
        previous_plan=expiry_stack.latest_plan,
        advice_result=expiry_advice,
        source_snapshot=expiry_stack.latest_d4_region_snapshot,
        source_decision=expiry_stack.latest_d4_decision,
        now=expiry_advice.advisory_contract.valid_until_s,
        fault_generation_changed=False,
    )
    assert expired is None
    assert "advisory_expired" in (
        expiry_stack._d4_region_hint_bridge_rejection_reason or ""
    )


def test_fault_generation_blocks_d4_advisory_before_gate_consumption() -> None:
    config = ScenarioConfig(
        scenario_name="d4_advisory_fault_fence",
        scenario_version="d4-advisory-fault-fence-v1",
        target_count=2,
        resource_count=2,
        recon_count=1,
        region_count=1,
        duration_s=0.8,
        seed=43,
        radar_detection_probability=1.0,
        acoustic_enabled=False,
        visual_enabled=False,
    )
    stack = IntegratedScalableModuleStack(
        IntegratedStackConfig(d1_scan_max_lateness_s=0.0),
        d4_region_advisor=_assist_region_advisor(),
        d4_unseen_seed_count=1,
    )
    run_episode(config, module_stack=stack)
    advice = stack.latest_d4_region_advice

    hint = stack._d3_regional_hint_from_previous_d4(
        previous_plan=stack.latest_plan,
        advice_result=advice,
        source_snapshot=stack.latest_d4_region_snapshot,
        source_decision=stack.latest_d4_decision,
        now=advice.advisory_contract.created_at_s + 0.1,
        fault_generation_changed=True,
    )

    assert hint is None
    assert stack.latest_d4_region_consumption is None
    assert stack._d4_region_advisory_gate.consumed_advisory_ids == frozenset()
    assert stack._d4_region_hint_bridge_rejection_reason == (
        "fault_generation_changed_before_advisory_consumption"
    )
