from __future__ import annotations

import numpy as np
import pytest

from d1_sensor_fusion.compat import FilterPyBackendPlaceholder, StoneSoupAdapterPlaceholder
from d1_sensor_fusion.fusion import FusionAdapter
from d1_sensor_fusion.observations import acoustic_covariance, radar_covariance_from_range, radar_h
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


def test_radar_covariance_grows_with_range() -> None:
    near = radar_covariance_from_range(100.0)
    far = radar_covariance_from_range(800.0)
    assert far[0, 0] > near[0, 0]
    assert far[1, 1] > near[1, 1]
    assert far[3, 3] > near[3, 3]


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
