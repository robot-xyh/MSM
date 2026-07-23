from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest

from research_modules.d2_data_association.d2_data_association import (
    IdentityCommitmentState,
    IdentityEvidenceCommitment,
)
from research_modules.scalable_3d_simulation.episode_bus import (
    VersionedEnvelope,
    jsonable,
)
from research_modules.scalable_3d_simulation.models import (
    OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
    OFFLINE_TRUTH_DISPOSITION_TARGET,
    OFFLINE_TRUTH_DISPOSITION_UNKNOWN,
    OFFLINE_TRUTH_SCHEMA_VERSION,
    OFFLINE_TRUTH_SCHEMA_VERSION_V1,
    OfflineTruthLabel,
    ScenarioConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode
from research_modules.scalable_3d_simulation.offline_evaluation import (
    write_offline_identity_evaluation,
)
from research_modules.scalable_3d_simulation.reserved_seed_interventions import (
    _offline_identity_mapping_at_timestamp,
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


def test_offline_truth_v1_target_and_v2_dispositions_validate() -> None:
    legacy = OfflineTruthLabel(
        observation_id="OBS-LEGACY",
        truth_entity_id="TGT-0001",
        measurement_timestamp=0.0,
        schema_version=OFFLINE_TRUTH_SCHEMA_VERSION_V1,
    )
    target = OfflineTruthLabel(
        observation_id="OBS-TARGET",
        truth_entity_id="TGT-0002",
        measurement_timestamp=0.1,
    )
    false_alarm = OfflineTruthLabel.known_false_alarm(
        observation_id="OBS-FALSE",
        measurement_timestamp=0.2,
    )
    unknown = OfflineTruthLabel.unknown(
        observation_id="OBS-UNKNOWN",
        measurement_timestamp=0.3,
    )

    assert legacy.disposition == OFFLINE_TRUTH_DISPOSITION_TARGET
    assert legacy.schema_version == OFFLINE_TRUTH_SCHEMA_VERSION_V1
    assert target.schema_version == OFFLINE_TRUTH_SCHEMA_VERSION
    assert target.disposition == OFFLINE_TRUTH_DISPOSITION_TARGET
    assert false_alarm.disposition == OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM
    assert false_alarm.truth_entity_id is None
    assert unknown.disposition == OFFLINE_TRUTH_DISPOSITION_UNKNOWN
    assert unknown.truth_entity_id is None

    with pytest.raises(ValueError, match="v1 supports target"):
        OfflineTruthLabel(
            observation_id="OBS-INVALID-V1",
            truth_entity_id=None,
            measurement_timestamp=0.0,
            schema_version=OFFLINE_TRUTH_SCHEMA_VERSION_V1,
            disposition=OFFLINE_TRUTH_DISPOSITION_UNKNOWN,
        )
    with pytest.raises(ValueError, match="require truth_entity_id"):
        OfflineTruthLabel(
            observation_id="OBS-MISSING-TARGET",
            truth_entity_id=None,
            measurement_timestamp=0.0,
        )
    with pytest.raises(ValueError, match="must not carry truth_entity_id"):
        OfflineTruthLabel(
            observation_id="OBS-FALSE-WITH-TARGET",
            truth_entity_id="TGT-0001",
            measurement_timestamp=0.0,
            disposition=OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
        )


def test_visual_false_alarms_have_explicit_offline_labels_only() -> None:
    config = ScenarioConfig(
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.1,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=50.0,
    )
    snapshot = VectorizedPointMassWorld(config).snapshot()
    batch = SensorScene(config).visual_scan(snapshot)

    assert batch.measurements
    assert len(batch.measurements) == len(batch.offline_truth_labels)
    assert {
        label.disposition for label in batch.offline_truth_labels
    } == {OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM}
    assert all(
        label.truth_entity_id is None for label in batch.offline_truth_labels
    )
    measurement_ids = {item.observation_id for item in batch.measurements}
    label_ids = {item.observation_id for item in batch.offline_truth_labels}
    assert measurement_ids == label_ids
    online_payload = json.dumps(
        jsonable(batch.measurements),
        sort_keys=True,
    )
    assert "truth_entity_id" not in online_payload
    assert "disposition" not in online_payload


def test_root_artifacts_keep_dispositions_out_of_online_payload(tmp_path) -> None:
    config = ScenarioConfig(
        scenario_name="truth-disposition-artifact",
        scenario_version="truth-disposition-artifact-v1",
        target_count=1,
        resource_count=1,
        recon_count=0,
        duration_s=0.1,
        radar_enabled=False,
        acoustic_enabled=False,
        visual_detection_probability=0.0,
        visual_false_alarm_rate=50.0,
    )
    result = run_episode(config, output_dir=tmp_path)

    online_text = (tmp_path / "online_observations.jsonl").read_text(
        encoding="utf-8"
    )
    offline_rows = [
        json.loads(line)
        for line in (
            tmp_path / "offline_truth_labels.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert result.offline_truth_labels
    assert "truth_entity_id" not in online_text
    assert "disposition" not in online_text
    assert offline_rows
    assert all(
        row["schema_version"] == OFFLINE_TRUTH_SCHEMA_VERSION
        for row in offline_rows
    )
    assert {
        row["disposition"] for row in offline_rows
    } == {OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM}


def test_reserved_seed_identity_mapping_ignores_non_target_labels() -> None:
    target = OfflineTruthLabel(
        observation_id="OBS-TARGET",
        truth_entity_id="TGT-0001",
        measurement_timestamp=0.0,
    )
    false_alarm = OfflineTruthLabel.known_false_alarm(
        observation_id="OBS-FALSE",
        measurement_timestamp=0.0,
    )
    unknown = OfflineTruthLabel.unknown(
        observation_id="OBS-UNKNOWN",
        measurement_timestamp=0.0,
    )
    message = SimpleNamespace(
        topic="modules.d2.associated_tracks",
        timestamp=0.1,
        payload={
            "identity_lineage": [
                {
                    "global_track_id": "GT-0001",
                    "source_observations": [
                        {"observation_id": target.observation_id},
                        {"observation_id": false_alarm.observation_id},
                        {"observation_id": unknown.observation_id},
                    ],
                }
            ]
        },
    )
    result = SimpleNamespace(
        online_messages=(message,),
        offline_truth_labels=(target, false_alarm, unknown),
    )

    assert _offline_identity_mapping_at_timestamp(
        result,
        timestamp_s=0.1,
        global_track_ids=("GT-0001",),
    ) == (("GT-0001", "TGT-0001"),)


def test_d2_adapter_excludes_false_alarms_and_blocks_unknown(tmp_path) -> None:
    covariance = np.eye(6, dtype=float).tolist()

    def track(global_track_id: str) -> dict[str, object]:
        return {
            "global_track_id": global_track_id,
            "state_ned": [0.0] * 6,
            "covariance": covariance,
            "timestamp": 0.0,
            "track_state": "tentative",
        }

    def lineage(observation_id: str) -> dict[str, object]:
        return {
            "observation_id": observation_id,
            "measurement_timestamp": 0.0,
            "source_lineage": [observation_id],
            "replay_generation": 0,
        }

    messages = (
        VersionedEnvelope(
            sequence=1,
            topic="modules.d1.fused_tracks",
            source="D1",
            timestamp=0.1,
            schema_version="d1-scalable3d-fusion-v1",
            payload={
                "timestamp": 0.1,
                "track_count": 2,
                "tracks": [track("D1-1"), track("D1-2")],
                "observation_lineage": [
                    lineage("OBS-TARGET"),
                    lineage("OBS-FALSE"),
                    lineage("OBS-UNKNOWN"),
                ],
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
                "track_count": 2,
                "tracks": [track("GT-1"), track("GT-2")],
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
                        "global_track_id": "GT-1",
                        "lifecycle_state": "tentative",
                        "association_state": "matched",
                        "source_observations": [
                            lineage("OBS-TARGET"),
                            lineage("OBS-FALSE"),
                        ],
                    },
                    {
                        "global_track_id": "GT-2",
                        "lifecycle_state": "tentative",
                        "association_state": "matched",
                        "source_observations": [lineage("OBS-UNKNOWN")],
                    },
                ],
            },
        ),
    )
    labels = (
        OfflineTruthLabel("OBS-TARGET", "TGT-0001", 0.0),
        OfflineTruthLabel.known_false_alarm(
            observation_id="OBS-FALSE",
            measurement_timestamp=0.0,
        ),
        OfflineTruthLabel.unknown(
            observation_id="OBS-UNKNOWN",
            measurement_timestamp=0.0,
        ),
    )

    paths = write_offline_identity_evaluation(
        tmp_path,
        episode_id="disposition-adapter",
        messages=messages,
        offline_truth_labels=labels,
    )
    truth_rows = [
        json.loads(line)
        for line in paths["offline_identity_truth_labels"]
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    evaluation = json.loads(
        paths["offline_identity_evaluation"].read_text(encoding="utf-8")
    )
    mappings = {
        item["global_track_id"]: item
        for frame in evaluation["frames"]
        for item in frame["mappings"]
    }

    assert {row["disposition"] for row in truth_rows} == {
        OFFLINE_TRUTH_DISPOSITION_TARGET,
        OFFLINE_TRUTH_DISPOSITION_KNOWN_FALSE_ALARM,
        OFFLINE_TRUTH_DISPOSITION_UNKNOWN,
    }
    assert all(
        "truth_target_id" not in row
        for row in truth_rows
        if row["disposition"] != OFFLINE_TRUTH_DISPOSITION_TARGET
    )
    assert mappings["GT-1"]["status"] == "available"
    assert mappings["GT-1"]["truth_target_id"] == "TGT-0001"
    assert mappings["GT-2"]["status"] == "unavailable"
    assert mappings["GT-2"]["reason"] == "truth_label_unknown"
    assert evaluation["metrics"]["truth_metrics_available"] is False
    assert evaluation["metrics"]["truth_metrics_reason"] == "truth_label_unknown"


def test_offline_identity_v2_keeps_uncommitted_gap_explicit(
    tmp_path,
) -> None:
    covariance = np.eye(6, dtype=float).tolist()

    def track(timestamp: float) -> dict[str, object]:
        return {
            "global_track_id": "GT3D-000001",
            "state_ned": [0.0] * 6,
            "covariance": covariance,
            "timestamp": timestamp,
            "track_state": "confirmed",
        }

    def lineage(
        observation_id: str,
        timestamp: float,
    ) -> dict[str, object]:
        return {
            "observation_id": observation_id,
            "measurement_timestamp": timestamp,
            "source_lineage": [
                "opaque_online_lineage",
                observation_id,
            ],
            "replay_generation": 0,
        }

    committed = IdentityEvidenceCommitment(
        global_track_id="GT3D-000001",
        association_state="created",
        identity_commitment_state=IdentityCommitmentState.COMMITTED,
        reason="track_created_from_fresh_original_observation",
        state_timestamp=0.0,
        measurement_timestamp=0.0,
        arrival_timestamp=0.01,
        source_observation_evidence_key="d1-observation-sha256:"
        + "1" * 64,
        source_observation_evidence_generation=0,
        source_observation_disposition="target_candidate",
    )
    uncommitted = IdentityEvidenceCommitment(
        global_track_id="GT3D-000001",
        association_state="unmatched",
        identity_commitment_state=(
            IdentityCommitmentState.UNCOMMITTED_AFTER_HOLD
        ),
        reason=(
            "ambiguity_hold_released_without_fresh_original_observation"
        ),
        state_timestamp=1.0,
        commitment_generation=1,
        measurement_timestamp=0.6,
        arrival_timestamp=0.7,
        ambiguity_component_key="component-1",
        ambiguity_evidence_id="evidence-1",
        ambiguity_component_generation=1,
        publisher_node_id="D1_FUSION",
        publisher_epoch="epoch-1",
        lease_first_seen_timestamp=0.7,
        lease_soft_deadline=0.9,
        lease_hard_deadline=1.2,
        lease_expired_timestamp=0.9,
        lease_expiration_reason="soft_deadline_reached",
        recovery_blocker_count=2,
        recovery_not_before_measurement_timestamp=0.6,
    )
    messages = (
        VersionedEnvelope(
            sequence=1,
            topic="modules.d1.fused_tracks",
            source="D1",
            timestamp=0.0,
            schema_version="d1-scalable3d-fusion-v1",
            payload={
                "timestamp": 0.0,
                "track_count": 1,
                "tracks": [track(0.0)],
                "observation_lineage": [lineage("OBS-0", 0.0)],
            },
        ),
        VersionedEnvelope(
            sequence=2,
            topic="modules.d2.associated_tracks",
            source="D2",
            timestamp=0.0,
            schema_version="d2-scalable3d-association-v1",
            payload={
                "timestamp": 0.0,
                "track_count": 1,
                "tracks": [track(0.0)],
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
                    "d2_center_track_to_d1_source_observation_commitment_v2"
                ),
                "identity_lineage": [
                    {
                        "global_track_id": "GT3D-000001",
                        "lifecycle_state": "confirmed",
                        "association_state": "created",
                        "identity_commitment": committed.to_dict(),
                        "source_observations": [lineage("OBS-0", 0.0)],
                    }
                ],
            },
        ),
        VersionedEnvelope(
            sequence=3,
            topic="modules.d1.fused_tracks",
            source="D1",
            timestamp=1.0,
            schema_version="d1-scalable3d-fusion-v1",
            payload={
                "timestamp": 1.0,
                "track_count": 1,
                "tracks": [track(1.0)],
                "observation_lineage": [lineage("OBS-PRESENCE", 1.0)],
            },
        ),
        VersionedEnvelope(
            sequence=4,
            topic="modules.d2.associated_tracks",
            source="D2",
            timestamp=1.0,
            schema_version="d2-scalable3d-association-v1",
            payload={
                "timestamp": 1.0,
                "track_count": 1,
                "tracks": [track(1.0)],
                "association": {
                    "timestamp": 1.0,
                    "identity_commitment": {
                        "recovery_config": dict(
                            _TEST_IDENTITY_RECOVERY_CONFIG
                        )
                    },
                },
                "id_switch_count": None,
                "id_switch_count_available": False,
                "identity_lineage_policy": (
                    "d2_center_track_to_d1_source_observation_commitment_v2"
                ),
                "identity_lineage": [
                    {
                        "global_track_id": "GT3D-000001",
                        "lifecycle_state": "confirmed",
                        "association_state": "unmatched",
                        "identity_commitment": uncommitted.to_dict(),
                        "source_observations": [],
                    }
                ],
            },
        ),
    )
    labels = (
        OfflineTruthLabel("OBS-0", "TGT-0001", 0.0),
        OfflineTruthLabel("OBS-PRESENCE", "TGT-0001", 1.0),
    )

    paths = write_offline_identity_evaluation(
        tmp_path,
        episode_id="identity-commitment-v2",
        messages=messages,
        offline_truth_labels=labels,
        lineage_time_window_s=0.5,
        truth_presence_window_s=0.1,
    )
    manifest = json.loads(
        paths["offline_identity_manifest"].read_text(encoding="utf-8")
    )
    evaluation = json.loads(
        paths["offline_identity_evaluation"].read_text(encoding="utf-8")
    )

    assert manifest["identity_evidence_schema_version"].endswith(".v2")
    assert manifest["identity_evaluation_schema_version"].endswith(".v2")
    assert evaluation["metrics"]["truth_metrics_available"] is True
    assert evaluation["metrics"]["coverage_continuity"] == pytest.approx(0.5)
    assert evaluation["frames"][1]["mappings"][0]["status"] == "uncommitted"
    assert evaluation["frames"][1]["mappings"][0][
        "source_observation_ids"
    ] == []
    assert evaluation["audit"]["identity_commitment_all_records"][
        "uncommitted_count"
    ] == 1
    assert evaluation["audit"][
        "uncommitted_source_binding_violation_count"
    ] == 0
