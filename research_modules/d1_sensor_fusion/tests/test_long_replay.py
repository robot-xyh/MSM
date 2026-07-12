from __future__ import annotations

import json

import numpy as np

from d1_sensor_fusion import (
    LONG_REPLAY_CONFIG_VERSION,
    LONG_REPLAY_OFFLINE_TRUTH_SCHEMA_VERSION,
    LONG_REPLAY_SCENARIO_VERSION,
    LONG_REPLAY_SUMMARY_SCHEMA_VERSION,
    LONG_REPLAY_THRESHOLD_PROFILE_VERSION,
    LongReplayConfig,
    build_long_replay_scenario,
    serialize_governed_replay,
    summarize_long_replay,
)


def test_long_replay_freezes_governance_and_isolates_online_truth() -> None:
    scenario = build_long_replay_scenario(
        LongReplayConfig(
            target_count=3,
            duration_s=8.0,
            sample_period_s=0.5,
            radar_period_s=0.5,
            acoustic_period_s=1.0,
            eo_period_s=0.5,
            radar_oosm_interval_frames=4,
            relay_duplicate_interval_frames=7,
            seed=19,
        )
    )

    assert scenario.provenance.scenario_version == LONG_REPLAY_SCENARIO_VERSION
    assert scenario.provenance.config_version == LONG_REPLAY_CONFIG_VERSION
    assert scenario.provenance.metadata["threshold_profile_version"] == (
        LONG_REPLAY_THRESHOLD_PROFILE_VERSION
    )
    assert scenario.offline_truth["schema_version"] == LONG_REPLAY_OFFLINE_TRUTH_SCHEMA_VERSION
    assert len(scenario.offline_truth["tracks"]) == 3
    assert scenario.event_counts["eo_occlusion_drop_count"] > 0
    assert scenario.event_counts["radar_oosm_injected_count"] > 0
    assert scenario.event_counts["relay_duplicate_injected_count"] > 0

    for observation in scenario.observations:
        assert observation.arrival_timestamp >= observation.measurement_timestamp
        assert observation.covariance is not None
        assert np.isfinite(observation.covariance).all()
        assert observation.metadata["working_frame"] == "ned"
        assert observation.metadata["source_lineage_key"]
        assert not any(
            "slot-" in str(item) for item in observation.metadata["source_lineage_key"]
        )
        assert not _contains_identity_key(observation.metadata)

    online = serialize_governed_replay(scenario.observations, scenario.provenance)
    json.dumps(online, allow_nan=False)
    assert online["manifest"]["provenance"]["scenario_version"] == (
        LONG_REPLAY_SCENARIO_VERSION
    )
    assert online["manifest"]["provenance"]["config_version"] == LONG_REPLAY_CONFIG_VERSION
    assert not any(_contains_identity_key(record) for record in online["records"])
    assert "offline_truth" not in online


def test_long_replay_summary_exposes_latency_regions_and_metric_availability() -> None:
    scenario = build_long_replay_scenario(
        LongReplayConfig(
            target_count=2,
            duration_s=10.0,
            sample_period_s=0.5,
            radar_period_s=0.5,
            acoustic_period_s=1.0,
            eo_period_s=0.5,
            radar_oosm_interval_frames=4,
            relay_duplicate_interval_frames=8,
            seed=23,
        )
    )

    summary = summarize_long_replay(scenario)
    payload = summary.to_dict()

    assert payload["schema_version"] == LONG_REPLAY_SUMMARY_SCHEMA_VERSION
    assert payload["scenario_version"] == LONG_REPLAY_SCENARIO_VERSION
    assert payload["threshold_profile_version"] == LONG_REPLAY_THRESHOLD_PROFILE_VERSION
    assert payload["observation_count"] == len(scenario.observations)
    assert set(payload["modality_counts"]) == {"acoustic", "eo", "radar"}
    assert payload["raw_latency_audit"]["oosm_observation_count"] > 0
    assert payload["fusion_latency_audit"]["duplicate_observation_count"] > 0
    assert payload["sensor_health"]
    assert payload["final_track_count"] > 0
    assert payload["region_quality_windows"]
    assert payload["online_truth_leak_count"] == 0
    assert payload["metric_availability"]["rmse"]["available"] is False
    assert "canonical-ID" in payload["metric_availability"]["rmse"]["reason"]
    assert payload["manifest_digest"].startswith("sha256:")
    json.dumps(payload, allow_nan=False)


def test_long_replay_is_deterministic_for_same_seed_and_config() -> None:
    config = LongReplayConfig(
        target_count=2,
        duration_s=4.0,
        sample_period_s=0.5,
        radar_period_s=0.5,
        acoustic_period_s=1.0,
        eo_period_s=0.5,
        seed=31,
    )
    first = build_long_replay_scenario(config)
    second = build_long_replay_scenario(config)

    assert first.provenance.config_digest == second.provenance.config_digest
    assert first.provenance.scenario_digest == second.provenance.scenario_digest
    assert [obs.observation_id for obs in first.observations] == [
        obs.observation_id for obs in second.observations
    ]
    for left, right in zip(first.observations, second.observations):
        np.testing.assert_allclose(left.measurement, right.measurement)
        np.testing.assert_allclose(left.covariance, right.covariance)


def _contains_identity_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in {
                "truth_id",
                "truth_object_id",
                "actor_id",
                "actor_name",
                "object_id",
                "object_name",
            } or normalized.endswith(("_truth_id", "_actor_id", "_object_id")):
                return True
            if _contains_identity_key(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_identity_key(item) for item in value)
    return False
