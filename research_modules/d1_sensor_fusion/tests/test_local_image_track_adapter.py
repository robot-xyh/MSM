from __future__ import annotations

import numpy as np
import pytest

from research_modules.integration_contracts import LocalImageTrackObservation

from d1_sensor_fusion import sensor_observation_from_local_image_track
from d1_sensor_fusion.fusion import FusionAdapter
from d1_sensor_fusion.observations import radar_covariance_from_range, radar_h
from d1_sensor_fusion.types import SensorObservation


def _local_track(
    *,
    spectral_band: str = "visible",
    sensor_id: str = "camera-north",
    stream_id: str = "primary",
    local_track_id: str = "track-007",
    local_epoch: int = 3,
    measurement_timestamp: float = 12.25,
    arrival_timestamp: float = 12.40,
    track_state: str = "measured",
    metadata: dict | None = None,
) -> LocalImageTrackObservation:
    measured = track_state == "measured"
    return LocalImageTrackObservation(
        sensor_id=sensor_id,
        stream_id=stream_id,
        local_track_id=local_track_id,
        local_epoch=local_epoch,
        spectral_band=spectral_band,
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        center_px=np.array([640.25, 359.75]) if measured else None,
        bbox_xyxy=(620.0, 340.0, 660.0, 380.0) if measured else None,
        pixel_covariance=(
            np.array([[2.5, 0.25], [0.25, 3.5]]) if measured else None
        ),
        confidence=0.82,
        track_state=track_state,
        quality_flags=("detected", "batch-verified"),
        metadata=metadata,
    )


@pytest.mark.parametrize("spectral_band", ("visible", "infrared"))
def test_measured_visible_and_infrared_tracks_become_eo_pixel_observations(
    spectral_band: str,
) -> None:
    track = _local_track(
        spectral_band=spectral_band,
        metadata={
            "backend": "bytetrack",
            "batch_id": "batch-0042",
            "batch_index": 5,
            "batch_audit": {"frame_count": 16, "online_truth_use_count": 0},
        },
    )

    observation = sensor_observation_from_local_image_track(track)

    assert observation is not None
    assert observation.modality == "eo"
    assert observation.frame_id == "pixel"
    assert observation.measurement_timestamp == 12.25
    assert observation.arrival_timestamp == 12.40
    assert observation.confidence == 0.82
    assert observation.quality_flags == ("detected", "batch-verified")
    np.testing.assert_array_equal(observation.measurement, track.center_px)
    np.testing.assert_array_equal(observation.covariance, track.pixel_covariance)
    assert observation.metadata["spectral_band"] == spectral_band
    assert observation.metadata["sensor_id"] == "camera-north"
    assert observation.metadata["stream_id"] == "primary"
    assert observation.metadata["local_track_id"] == "track-007"
    assert observation.metadata["local_epoch"] == 3
    assert observation.metadata["source_track_key"] == track.source_track_key
    assert observation.metadata["bbox_xyxy"] == (620.0, 340.0, 660.0, 380.0)
    np.testing.assert_array_equal(observation.metadata["center_px"], track.center_px)
    assert observation.metadata["backend"] == "bytetrack"
    assert observation.metadata["batch_id"] == "batch-0042"
    assert observation.metadata["batch_audit"] == {
        "frame_count": 16,
        "online_truth_use_count": 0,
    }


def test_adapter_copies_arrays_and_generates_deterministic_local_lineage() -> None:
    first = _local_track()
    equivalent = _local_track()

    observation = sensor_observation_from_local_image_track(first)
    repeated = sensor_observation_from_local_image_track(equivalent)

    assert observation is not None and repeated is not None
    assert observation.observation_id == repeated.observation_id
    assert observation.source_lineage_key == repeated.source_lineage_key
    assert "camera-north" in observation.observation_id
    assert "primary" in observation.observation_id
    assert "epoch-3" in observation.observation_id
    assert "track-007" in observation.observation_id

    first.center_px[0] = -1.0
    first.pixel_covariance[0, 0] = 999.0
    assert observation.measurement[0] == 640.25
    assert observation.metadata["center_px"][0] == 640.25
    assert observation.covariance[0, 0] == 2.5


def test_explicit_observation_id_is_preserved() -> None:
    observation = sensor_observation_from_local_image_track(
        _local_track(),
        observation_id="camera-local-observation-009",
    )

    assert observation is not None
    assert observation.observation_id == "camera-local-observation-009"


def test_lost_track_never_emits_stale_pixels() -> None:
    track = _local_track(track_state="lost")
    object.__setattr__(track, "center_px", np.array([10.0, 20.0]))
    object.__setattr__(track, "pixel_covariance", np.eye(2))

    assert sensor_observation_from_local_image_track(track) is None


@pytest.mark.parametrize(
    "invalid_covariance, message",
    (
        (None, "require pixel_covariance"),
        (np.array([[1.0, 2.0], [2.0, 1.0]]), "positive semidefinite"),
        (np.array([[1.0, np.nan], [np.nan, 1.0]]), "finite"),
    ),
)
def test_adapter_fails_closed_on_missing_or_invalid_covariance(
    invalid_covariance: np.ndarray | None,
    message: str,
) -> None:
    track = _local_track()
    object.__setattr__(track, "pixel_covariance", invalid_covariance)

    with pytest.raises(ValueError, match=message):
        sensor_observation_from_local_image_track(track)


@pytest.mark.parametrize(
    "identity_metadata",
    (
        {"global_track_id": "global_track_999"},
        {"truth_id": "actor-secret"},
        {"audit": {"ground_truth_id": "actor-secret"}},
    ),
)
def test_adapter_rejects_global_and_truth_identity_metadata(
    identity_metadata: dict,
) -> None:
    track = _local_track()
    track.metadata.update(identity_metadata)

    with pytest.raises(ValueError, match="global/truth identity"):
        sensor_observation_from_local_image_track(track)


def test_accepted_visual_sources_accumulate_without_rebinding_global_track_id() -> None:
    state = np.array([100.0, 0.0, -10.0, 0.0, 0.0, 0.0])
    radar_measurement = radar_h(state, np.zeros(3))
    radar = SensorObservation(
        observation_id="radar-seed",
        sensor_id="radar-main",
        modality="radar",
        measurement_timestamp=0.0,
        arrival_timestamp=0.0,
        frame_id="ned",
        measurement=radar_measurement,
        covariance=radar_covariance_from_range(radar_measurement[0]),
        metadata={"sensor_position_ned": np.zeros(3), "scan_id": 0},
    )
    visible = _local_track(
        sensor_id="camera-visible",
        stream_id="front-rgb",
        local_track_id="local-1",
        local_epoch=1,
        measurement_timestamp=0.1,
        arrival_timestamp=0.1,
    )
    infrared = _local_track(
        spectral_band="infrared",
        sensor_id="camera-infrared",
        stream_id="front-ir",
        local_track_id="local-4",
        local_epoch=2,
        measurement_timestamp=0.2,
        arrival_timestamp=0.2,
    )
    adapter = FusionAdapter()

    tracks = adapter.process(radar)
    global_track_id = tracks[0].global_track_id
    tracks = adapter.process(sensor_observation_from_local_image_track(visible))
    tracks = adapter.process(sensor_observation_from_local_image_track(infrared))

    assert len(tracks) == 1
    track = tracks[0]
    assert track.global_track_id == global_track_id
    assert track.global_track_id not in {visible.source_track_key, infrared.source_track_key}
    assert set(track.metadata["source_track_ids"]) == {
        visible.source_track_key,
        infrared.source_track_key,
    }


def test_repeated_local_image_sample_has_deduplicable_source_lineage() -> None:
    first = sensor_observation_from_local_image_track(_local_track())
    repeated = sensor_observation_from_local_image_track(_local_track())

    assert first is not None and repeated is not None
    assert first.source_lineage_key == repeated.source_lineage_key
