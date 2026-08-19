from __future__ import annotations

from types import SimpleNamespace

from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.airsim_adapter import (
    AirSimDetectionAdapter,
)
from research_modules.independent_experiments.center_terminal_cv_campaign.exp_center_handover.geometry import (
    CameraIntrinsics,
    CameraModel,
)


class FakeDetection:
    def __init__(self, name: str, width: float) -> None:
        self.name = name
        self.box2D = SimpleNamespace(
            min=SimpleNamespace(x_val=960.0 - width / 2.0, y_val=538.0),
            max=SimpleNamespace(x_val=960.0 + width / 2.0, y_val=542.0),
        )


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def simGetCameraInfo(self, camera_name, *, vehicle_name):
        self.calls.append("simGetCameraInfo")
        return SimpleNamespace(
            fov=19.0,
            pose=SimpleNamespace(
                position=SimpleNamespace(x_val=0.0, y_val=0.0, z_val=0.0),
                orientation=SimpleNamespace(x_val=0.0, y_val=0.0, z_val=0.0, w_val=1.0),
            ),
        )

    def simGetDetections(self, camera_name, image_type, *, vehicle_name):
        self.calls.append("simGetDetections")
        return (FakeDetection("Actor_A", 9.99), FakeDetection("Actor_B", 10.0))


def camera() -> CameraModel:
    return CameraModel(
        camera_id="Terminal_CV_01",
        intrinsics=CameraIntrinsics(),
        body_position_ned_m=(0.0, 0.0, 0.0),
        body_yaw_pitch_roll_deg=(0.0, 0.0, 0.0),
        camera_offset_body_m=(0.0, 0.0, 0.0),
    )


def test_adapter_only_reads_detection_and_camera_info_and_keeps_names_offline() -> None:
    client = FakeClient()
    adapter = AirSimDetectionAdapter({camera().camera_id: camera()})
    batch = adapter.collect_frame(
        client,
        measurement_timestamp=0.2,
        arrival_timestamp=0.22,
    )
    assert client.calls == ["simGetCameraInfo", "simGetDetections"]
    assert [record.recognized for record in batch.local_tracks] == [False, True]
    assert all("Actor" not in record.local_track_id for record in batch.local_tracks)
    assert all("raw_detection_name" not in record.metadata for record in batch.local_tracks)
    assert [label.raw_detection_name for label in batch.offline_labels] == ["Actor_A", "Actor_B"]


def test_adapter_keeps_anonymous_local_track_ids_across_frames() -> None:
    client = FakeClient()
    model = camera()
    adapter = AirSimDetectionAdapter({model.camera_id: model})
    first = adapter.collect_frame(client, measurement_timestamp=0.2, arrival_timestamp=0.22)
    second = adapter.collect_frame(client, measurement_timestamp=0.3, arrival_timestamp=0.32)
    assert [item.local_track_id for item in first.local_tracks] == [
        item.local_track_id for item in second.local_tracks
    ]
