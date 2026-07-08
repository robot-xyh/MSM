from __future__ import annotations

import numpy as np
import pytest

from d1_sensor_fusion.compat import FilterPyBackendPlaceholder, StoneSoupAdapterPlaceholder
from d1_sensor_fusion.fusion import FusionAdapter
from d1_sensor_fusion.observations import (
    CameraModel,
    RadarCovarianceConfig,
    acoustic_covariance,
    eo_project,
    measurement_model_for,
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.types import SensorObservation


def test_sensor_observation_latency_and_bucket() -> None:
    obs = SensorObservation(
        observation_id="radar_001",
        sensor_id="radar",
        modality="radar",
        measurement_timestamp=1.2,
        arrival_timestamp=2.0,
        frame_id="ned",
        measurement=np.array([100.0, 0.1, 0.0, 4.0]),
    )
    adapter = FusionAdapter(bucket_size=0.1)
    assert obs.latency == 0.8
    assert adapter._bucket(1.23) == 12


def test_sensor_observation_normalizes_cross_node_metadata() -> None:
    obs = SensorObservation(
        observation_id="eo_peer_001",
        sensor_id="interceptor_cam_01",
        modality="eo",
        measurement_timestamp=1.0,
        arrival_timestamp=1.4,
        frame_id="pixel",
        measurement=np.array([640.0, 360.0]),
        covariance=np.eye(2),
        metadata={
            "source_node_id": "INT-01",
            "target_node_id": "C2",
            "relay_node_id": "TETHER-01",
            "link_type": "secondary_relay",
            "sent_timestamp": "1.1",
            "received_timestamp": 1.35,
            "payload_kind": "bbox",
            "stale_after_s": 0.4,
            "source_support": {"eo": 1},
        },
    )

    assert obs.source_node_id == "INT-01"
    assert obs.target_node_id == "C2"
    assert obs.relay_node_id == "TETHER-01"
    assert obs.link_type == "secondary_relay"
    assert obs.payload_kind == "bbox"
    assert obs.sent_timestamp == 1.1
    assert obs.received_timestamp == 1.35
    assert obs.communication_latency == pytest.approx(0.25)
    assert obs.source_support == {"eo": 1}
    assert obs.metadata["source_node_id"] == "INT-01"
    assert obs.is_stale_at(1.8)

    copied = obs.with_measurement_timestamp(1.2)
    assert copied.source_node_id == obs.source_node_id
    assert copied.metadata["payload_kind"] == "bbox"
    assert copied.source_support == {"eo": 1}


def test_radar_covariance_grows_with_range() -> None:
    near = radar_covariance_from_range(100.0)
    far = radar_covariance_from_range(800.0)
    assert far[0, 0] > near[0, 0]
    assert far[1, 1] > near[1, 1]
    assert far[3, 3] > near[3, 3]


def test_radar_covariance_config_preserves_default_and_can_be_tuned() -> None:
    default = radar_covariance_from_range(250.0)
    explicit_default = radar_covariance_from_range(250.0, RadarCovarianceConfig())
    tuned = radar_covariance_from_range(
        250.0,
        RadarCovarianceConfig(range_sigma_base_m=4.0, range_sigma_per_m=0.02),
    )

    assert np.allclose(default, explicit_default)
    assert tuned[0, 0] > default[0, 0]


def test_fusion_adapter_required_methods_create_and_update_track() -> None:
    adapter = FusionAdapter(latency_compensation=True)
    sensor_position = np.zeros(3)
    state = np.array([120.0, 20.0, -15.0, 4.0, 1.0, 0.0])
    radar_z = radar_h(state, sensor_position)
    radar_obs = SensorObservation(
        observation_id="radar_birth",
        sensor_id="radar",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=1.0,
        frame_id="ned",
        measurement=radar_z,
        covariance=radar_covariance_from_range(radar_z[0]),
        metadata={"sensor_position_ned": sensor_position},
    )
    tracks = adapter.process(radar_obs)
    assert len(tracks) == 1

    acoustic_obs = SensorObservation(
        observation_id="acoustic_update",
        sensor_id="acoustic",
        modality="acoustic",
        measurement_timestamp=0.8,
        arrival_timestamp=1.1,
        frame_id="ned",
        measurement=np.array([np.arctan2(20.8, 123.2)]),
        covariance=acoustic_covariance(0.8),
        confidence=0.8,
        metadata={"sensor_position_ned": sensor_position},
    )
    updated = adapter.update_at_measurement_time(acoustic_obs, current_time=1.1)
    assert updated is not None
    predicted = adapter.predict_track(updated, 1.5)
    assert predicted.timestamp == 1.5
    assert predicted.covariance.shape == (6, 6)


def test_track_uncertainty_summary_exports_required_fields() -> None:
    adapter = FusionAdapter(latency_compensation=True)
    sensor_position = np.zeros(3)
    state = np.array([120.0, 20.0, -15.0, 4.0, 1.0, 0.0])
    radar_z = radar_h(state, sensor_position)

    adapter.process(
        SensorObservation(
            observation_id="radar_summary_birth",
            sensor_id="radar",
            modality="radar",
            measurement_timestamp=1.0,
            arrival_timestamp=1.25,
            frame_id="ned",
            measurement=radar_z,
            covariance=radar_covariance_from_range(radar_z[0]),
            metadata={"sensor_position_ned": sensor_position, "coverage_cell": "cell-a"},
        )
    )

    summary = adapter.track_uncertainty_summaries()[0]
    payload = summary.to_dict()
    assert payload["track_id"] == payload["global_track_id"]
    assert payload["position_covariance_trace"] > 0.0
    assert payload["a95_m"] > 0.0
    assert payload["track_level"] == "coarse"
    assert payload["measurement_age_s"] == pytest.approx(0.25)
    assert payload["source_support"] == {"radar": 1}
    assert payload["coverage_cell"] == "cell-a"
    assert payload["measurement_timestamp"] == 1.0
    assert payload["arrival_timestamp"] == 1.25
    assert payload["valid_at"] == 1.25
    assert payload["published_at"] == 1.25

    regions = adapter.region_quality_summaries(required_modalities=("radar", "eo"), stale_age_s=0.1)
    assert len(regions) == 1
    region_payload = regions[0].to_dict()
    assert region_payload["coverage_cell"] == "cell-a"
    assert region_payload["track_count"] == 1
    assert region_payload["source_support"] == {"radar": 1}
    assert region_payload["source_gap_modalities"] == ("eo",)
    assert region_payload["stale_track_count"] == 1
    assert region_payload["max_measurement_age_s"] == pytest.approx(0.25)


def test_eo_measurement_model_uses_nested_replay_camera_model_metadata() -> None:
    camera_metadata = {
        "position_ned": [10.0, -5.0, -12.0],
        "rotation_world_to_camera": [
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
        ],
        "fx": 720.0,
        "fy": 710.0,
        "cx": 640.0,
        "cy": 360.0,
        "width": 1280,
        "height": 720,
    }
    state = np.array([130.0, 15.0, -18.0, 2.0, 0.0, 0.0])
    expected_camera = CameraModel(
        position_ned=np.asarray(camera_metadata["position_ned"], dtype=float),
        rotation_world_to_camera=np.asarray(
            camera_metadata["rotation_world_to_camera"], dtype=float
        ),
        fx=camera_metadata["fx"],
        fy=camera_metadata["fy"],
        cx=camera_metadata["cx"],
        cy=camera_metadata["cy"],
        width=camera_metadata["width"],
        height=camera_metadata["height"],
    )
    observation = SensorObservation(
        observation_id="eo_replay_camera_model",
        sensor_id="blocks_camera_01",
        modality="eo",
        measurement_timestamp=1.0,
        arrival_timestamp=1.05,
        frame_id="pixel",
        measurement=eo_project(state, expected_camera),
        covariance=np.eye(2),
        metadata={"camera_model": camera_metadata},
    )

    model = measurement_model_for(observation)

    assert np.allclose(model.h_fn(state), eo_project(state, expected_camera))
    assert model.r.shape == (2, 2)


def test_source_lineage_deduplicates_relay_repeated_payloads() -> None:
    adapter = FusionAdapter(latency_compensation=True)
    sensor_position = np.zeros(3)
    state = np.array([120.0, 20.0, -15.0, 4.0, 1.0, 0.0])
    radar_z = radar_h(state, sensor_position)
    base_metadata = {
        "sensor_position_ned": sensor_position,
        "sequence_id": 42,
        "payload_hash": "same-payload",
    }

    first = SensorObservation(
        observation_id="radar_lineage_direct",
        sensor_id="radar",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.2,
        frame_id="ned",
        measurement=radar_z,
        covariance=radar_covariance_from_range(radar_z[0]),
        metadata=base_metadata,
        source_node_id="NODE-A",
        payload_kind="radar_observation",
    )
    duplicate = SensorObservation(
        observation_id="radar_lineage_relay",
        sensor_id="radar",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.3,
        frame_id="ned",
        measurement=radar_z,
        covariance=radar_covariance_from_range(radar_z[0]),
        metadata=base_metadata,
        source_node_id="NODE-A",
        relay_node_id="RELAY-1",
        payload_kind="radar_observation",
    )

    adapter.process(first)
    tracks = adapter.process(duplicate)

    assert len(tracks) == 1
    assert tracks[0].metadata["hits"] == 1
    assert tracks[0].source_support == {"radar": 1}
    assert tracks[0].metadata["duplicate_observation_count"] == 1


def test_global_track_metadata_carries_cross_node_fields() -> None:
    adapter = FusionAdapter(latency_compensation=True)
    sensor_position = np.zeros(3)
    state = np.array([120.0, 20.0, -15.0, 4.0, 1.0, 0.0])
    radar_z = radar_h(state, sensor_position)
    tracks = adapter.process(
        SensorObservation(
            observation_id="radar_comm_birth",
            sensor_id="radar",
            modality="radar",
            measurement_timestamp=2.0,
            arrival_timestamp=2.5,
            frame_id="ned",
            measurement=radar_z,
            covariance=radar_covariance_from_range(radar_z[0]),
            metadata={"sensor_position_ned": sensor_position},
            source_node_id="C2",
            target_node_id="INT-01",
            relay_node_id="TETHER-01",
            link_type="secondary_relay",
            sent_timestamp=2.1,
            received_timestamp=2.45,
            payload_kind="track",
            stale_after_s=0.8,
        )
    )

    assert len(tracks) == 1
    metadata = tracks[0].metadata
    assert metadata["source_node_id"] == "C2"
    assert metadata["target_node_id"] == "INT-01"
    assert metadata["relay_node_id"] == "TETHER-01"
    assert metadata["link_type"] == "secondary_relay"
    assert metadata["payload_kind"] == "track"
    assert metadata["latest_measurement_timestamp"] == 2.0
    assert metadata["latest_arrival_timestamp"] == 2.5
    assert metadata["latest_communication_latency_s"] == pytest.approx(0.35)
    assert metadata["source_support"] == {"radar": 1}
    assert metadata["source_node_ids"] == ("C2",)


def test_delayed_non_radar_association_uses_measurement_time() -> None:
    adapter = FusionAdapter(latency_compensation=True, association_gate=25.0)
    sensor_position = np.zeros(3)
    state0 = np.array([100.0, 20.0, -5.0, 5.0, 0.0, 0.0])
    state10 = state0.copy()
    state10[:3] += state0[3:] * 10.0

    for observation_id, timestamp, state in (
        ("radar_0", 0.0, state0),
        ("radar_10", 10.0, state10),
    ):
        radar_z = radar_h(state, sensor_position)
        adapter.process(
            SensorObservation(
                observation_id=observation_id,
                sensor_id="radar",
                modality="radar",
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp,
                frame_id="ned",
                measurement=radar_z,
                covariance=radar_covariance_from_range(radar_z[0]),
                metadata={"sensor_position_ned": sensor_position},
            )
        )

    delayed_acoustic = SensorObservation(
        observation_id="acoustic_delayed_t0",
        sensor_id="acoustic",
        modality="acoustic",
        measurement_timestamp=0.0,
        arrival_timestamp=10.1,
        frame_id="ned",
        measurement=np.array([np.arctan2(state0[1], state0[0])]),
        covariance=acoustic_covariance(0.9),
        confidence=0.9,
        metadata={"sensor_position_ned": sensor_position},
    )

    tracks = adapter.process(delayed_acoustic)

    assert len(tracks) == 1
    assert tracks[0].source_support["acoustic"] == 1
    assert tracks[0].metadata["frame_id"] == "ned"


def test_latency_audit_summary_counts_delay_oosm_and_replay() -> None:
    adapter = FusionAdapter(latency_compensation=True, association_gate=25.0)
    sensor_position = np.zeros(3)
    state0 = np.array([100.0, 20.0, -5.0, 5.0, 0.0, 0.0])
    state2 = state0.copy()
    state2[:3] += state0[3:] * 2.0

    for observation_id, timestamp, state in (
        ("radar_audit_0", 0.0, state0),
        ("radar_audit_2", 2.0, state2),
    ):
        radar_z = radar_h(state, sensor_position)
        adapter.process(
            SensorObservation(
                observation_id=observation_id,
                sensor_id="radar",
                modality="radar",
                measurement_timestamp=timestamp,
                arrival_timestamp=timestamp,
                frame_id="ned",
                measurement=radar_z,
                covariance=radar_covariance_from_range(radar_z[0]),
                metadata={"sensor_position_ned": sensor_position},
            )
        )

    delayed_acoustic = SensorObservation(
        observation_id="acoustic_audit_delayed",
        sensor_id="acoustic",
        modality="acoustic",
        measurement_timestamp=1.0,
        arrival_timestamp=2.8,
        frame_id="ned",
        measurement=np.array([np.arctan2(state0[1], state0[0] + 5.0)]),
        covariance=acoustic_covariance(0.9),
        confidence=0.9,
        metadata={"sensor_position_ned": sensor_position},
        stale_after_s=0.5,
    )
    tracks = adapter.process(delayed_acoustic)

    audit = adapter.latency_audit_summary().to_dict()
    assert audit["observation_count"] == 3
    assert audit["replay_count"] == 2
    assert audit["oosm_observation_count"] == 1
    assert audit["stale_observation_count"] == 1
    assert audit["stale_or_oosm_observation_count"] == 1
    assert audit["max_delay_s"] == pytest.approx(1.8)
    assert audit["mean_delay_s"] == pytest.approx(0.6)
    assert audit["max_replay_observation_count"] >= 3
    assert tracks[0].metadata["latency_audit"]["max_delay_s"] == pytest.approx(1.8)


def test_observation_rejects_unconverted_external_frame() -> None:
    with pytest.raises(ValueError, match="Convert external frames"):
        SensorObservation(
            observation_id="radar_enu",
            sensor_id="radar",
            modality="radar",
            measurement_timestamp=0.0,
            arrival_timestamp=0.0,
            frame_id="enu",
            measurement=np.array([100.0, 0.0, 0.0, 0.0]),
        )


def test_optional_backend_placeholders_do_not_require_imports() -> None:
    stone_soup = StoneSoupAdapterPlaceholder()
    filterpy = FilterPyBackendPlaceholder()
    assert isinstance(stone_soup.available, bool)
    assert "fallback" in filterpy.describe().lower() or "optional" in filterpy.describe().lower()
