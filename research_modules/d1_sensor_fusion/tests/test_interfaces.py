from __future__ import annotations

import numpy as np
import pytest

from d1_sensor_fusion.compat import FilterPyBackendPlaceholder, StoneSoupAdapterPlaceholder
from d1_sensor_fusion.fusion import FusionAdapter
from d1_sensor_fusion.observations import (
    RadarCovarianceConfig,
    acoustic_covariance,
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
