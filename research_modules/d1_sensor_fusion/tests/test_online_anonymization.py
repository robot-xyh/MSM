from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

import numpy as np
import pytest

from d1_sensor_fusion import (
    ReplayProvenance,
    SensorObservation,
    anonymize_online_observations,
    assert_online_observations_identity_free,
    serialize_offline_governed_replay,
)


def test_scene_identity_rename_produces_field_identical_online_observations() -> None:
    alpha = _scene_observations(
        target_name="SceneTargetAlpha",
        actor_name="TargetActor-Alpha",
        truth_id="TRUTH-ALPHA",
    )
    bravo = _scene_observations(
        target_name="SceneTargetBravo",
        actor_name="TargetActor-Bravo",
        truth_id="TRUTH-BRAVO",
    )

    alpha_online = anonymize_online_observations(alpha)
    bravo_online = anonymize_online_observations(bravo)

    assert len(alpha_online) == len(bravo_online) == 2
    for left, right in zip(alpha_online, bravo_online):
        _assert_observations_field_identical(left, right)

    assert {item.observation_id for item in alpha_online} == {
        "online-frame-00000001-obs-0001",
        "online-frame-00000001-obs-0002",
    }
    assert len({item.source_lineage_key for item in alpha_online}) == 2
    assert alpha_online[0].classification_hint == "intruder"
    assert alpha_online[0].metadata["nested"]["detector"] == "simGetDetections"
    assert alpha_online[0].metadata["nested"]["detections"][0]["bbox"] == [10, 20, 30, 40]
    assert alpha_online[0].metadata["status"] == "tracked"
    assert alpha_online[0].metadata["source_lineage_key"][0] == "explicit"
    assert alpha_online[0].metadata["lineage_id"].startswith("online-frame-")

    for source, online in zip(alpha, alpha_online):
        assert online.measurement_timestamp == source.measurement_timestamp
        assert online.arrival_timestamp == source.arrival_timestamp
        np.testing.assert_array_equal(online.measurement, source.measurement)
        np.testing.assert_array_equal(online.covariance, source.covariance)
        np.testing.assert_array_equal(
            online.metadata["sensor_position_ned"], source.metadata["sensor_position_ned"]
        )
        np.testing.assert_array_equal(
            online.metadata["camera_model"]["rotation_world_to_camera"],
            source.metadata["camera_model"]["rotation_world_to_camera"],
        )
        assert online.metadata["camera_model"]["intrinsics"] == (
            source.metadata["camera_model"]["intrinsics"]
        )
        assert online.measurement is not source.measurement
        assert online.covariance is not source.covariance

    serialized = repr(alpha_online)
    for forbidden in (
        "SceneTargetAlpha",
        "TargetActor-Alpha",
        "TRUTH-ALPHA",
        "truth_id",
        "actor_name",
        "object_name",
        "segmentation_id",
        "local_track_id",
        "payload:SceneTargetAlpha",
    ):
        assert forbidden not in serialized
    assert_online_observations_identity_free(
        alpha_online,
        identity_tokens=("SceneTargetAlpha", "TargetActor-Alpha", "TRUTH-ALPHA"),
    )


def test_anonymizer_scrubs_explicit_token_outside_identity_keys_and_rejects_token_stream() -> None:
    observation = _scene_observations(
        target_name="SceneTargetAlpha",
        actor_name="TargetActor-Alpha",
        truth_id="TRUTH-ALPHA",
    )[0]
    observation.metadata.pop("target_name")
    observation.metadata.pop("actor_name")
    observation.metadata.pop("truth_id")
    observation.metadata["operator_note"] = "handover-to-CallsignRed"
    observation.classification_hint = "intruder CallsignRed priority"

    online = anonymize_online_observations(
        [observation], identity_tokens=("CallsignRed",)
    )[0]

    assert online.metadata["operator_note"] == "handover-to"
    assert online.classification_hint == "intruder priority"
    assert "CallsignRed" not in repr(online)
    with pytest.raises(ValueError, match="stream_id contains identity token"):
        anonymize_online_observations(
            [observation],
            identity_tokens=("CallsignRed",),
            stream_id="CallsignRed",
        )


def test_identity_validator_fails_closed_on_nested_keys_and_tokens() -> None:
    raw = _scene_observations(
        target_name="SceneTargetAlpha",
        actor_name="TargetActor-Alpha",
        truth_id="TRUTH-ALPHA",
    )[0]
    with pytest.raises(ValueError, match="identity key"):
        assert_online_observations_identity_free([raw])

    clean = anonymize_online_observations([raw])[0]
    clean.metadata["nested"]["note"] = "assigned to TargetActor-Alpha"
    with pytest.raises(ValueError, match="identity token.*TargetActor-Alpha"):
        assert_online_observations_identity_free(
            [clean], identity_tokens=("TargetActor-Alpha",)
        )

    clean.metadata["nested"].pop("note")
    clean.metadata["nested"]["actorName"] = "CamelCaseLeak"
    with pytest.raises(ValueError, match="identity key"):
        assert_online_observations_identity_free([clean])

    clean.metadata["nested"].pop("actorName")
    clean.metadata["nested"]["note"] = "assigned to CallsignRed"
    with pytest.raises(ValueError, match="CallsignRed"):
        assert_online_observations_identity_free([clean], identity_tokens="CallsignRed")


def test_anonymization_does_not_mutate_offline_truth_source_or_sidecar() -> None:
    source = _scene_observations(
        target_name="SceneTargetAlpha",
        actor_name="TargetActor-Alpha",
        truth_id="TRUTH-ALPHA",
    )[0]
    source_id = source.observation_id
    source_lineage = source.metadata["source_lineage_key"]

    anonymize_online_observations([source])

    assert source.observation_id == source_id
    assert source.metadata["truth_id"] == "TRUTH-ALPHA"
    assert source.metadata["actor_name"] == "TargetActor-Alpha"
    assert source.metadata["source_lineage_key"] == source_lineage

    offline = serialize_offline_governed_replay([source], _replay_provenance())
    sidecar = offline["records"][0]["offline_truth"]
    assert sidecar["truth_id"] == "TRUTH-ALPHA"
    assert sidecar["actor_name"] == "TargetActor-Alpha"
    assert sidecar["nested"]["object_name"] == "SceneTargetAlpha"
    assert sidecar["classification_hint"] == (
        "intruder SceneTargetAlpha TargetActor-Alpha TRUTH-ALPHA"
    )


def _scene_observations(
    *,
    target_name: str,
    actor_name: str,
    truth_id: str,
) -> list[SensorObservation]:
    observations: list[SensorObservation] = []
    for index in (1, 2):
        observations.append(
            SensorObservation(
                observation_id=f"scene/{actor_name}/{target_name}/{index}",
                sensor_id="EO-CAMERA-01",
                modality="eo",
                measurement_timestamp=12.5,
                arrival_timestamp=12.58,
                frame_id="pixel",
                measurement=np.array([620.0 + index, 355.0 - index]),
                covariance=np.array([[4.0, 0.25], [0.25, 5.0]]),
                classification_hint=f"intruder {target_name} {actor_name} {truth_id}",
                confidence=0.84,
                quality_flags=("small_bbox", f"candidate:{actor_name}"),
                metadata={
                    "coverage_cell": "cell-north",
                    "airsim_frame_index": 125,
                    "truth_id": truth_id,
                    "target_name": target_name,
                    "actor_name": actor_name,
                    "segmentation_id": f"seg-{truth_id}",
                    "source_lineage_key": ("scene_payload", target_name, index),
                    "sequence_id": f"payload:{target_name}:{index}",
                    "payload_hash": f"hash:{actor_name}:{index}",
                    "sensor_position_ned": np.array([3.0, -4.0, -10.0]),
                    "camera_model": {
                        "rotation_world_to_camera": np.array(
                            [
                                [0.0, 1.0, 0.0],
                                [0.0, 0.0, 1.0],
                                [1.0, 0.0, 0.0],
                            ]
                        ),
                        "intrinsics": {
                            "fx": 900.0,
                            "fy": 910.0,
                            "cx": 640.0,
                            "cy": 360.0,
                            "width": 1280,
                            "height": 720,
                        },
                    },
                    "nested": {
                        "detector": "simGetDetections",
                        "object_name": target_name,
                        "detections": [
                            {
                                "actor_name": actor_name,
                                "local_track_id": f"local:{truth_id}",
                                "bbox": [10, 20, 30, 40],
                            }
                        ],
                    },
                    "status": f"tracked:{target_name}",
                },
                source_node_id="MAIN-C2",
                target_node_id="D1-FUSION",
                link_type="runtime_bus",
                sent_timestamp=12.54,
                received_timestamp=12.57,
                payload_kind="camera_detection",
                stale_after_s=0.5,
                source_support={"eo": 1},
                timestamp_uncertainty_s=0.01,
            )
        )
    return observations


def _replay_provenance() -> ReplayProvenance:
    return ReplayProvenance(
        scenario_id="online-anonymization-regression",
        scenario_version="1",
        config_id="identity-boundary",
        config_digest="sha256:test-config",
        config_version="1",
        scenario_digest="sha256:test-scenario",
        seed=14,
    )


def _assert_observations_field_identical(
    left: SensorObservation,
    right: SensorObservation,
) -> None:
    for field in fields(SensorObservation):
        assert _normalized(getattr(left, field.name)) == _normalized(
            getattr(right, field.name)
        ), field.name


def _normalized(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return (value.dtype.str, value.shape, value.tolist())
    if isinstance(value, dict):
        return {str(key): _normalized(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_normalized(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalized(getattr(value, field.name))
            for field in fields(value)
        }
    return value
