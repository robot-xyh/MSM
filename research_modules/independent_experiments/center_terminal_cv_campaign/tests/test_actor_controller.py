from __future__ import annotations

from dataclasses import dataclass

from center_terminal_cv_campaign.actor_controller import CampaignActorClientProxy
from center_terminal_cv_campaign.common.scenario import CampaignScenario, generate_targets


@dataclass
class Vector:
    x: float
    y: float
    z: float


@dataclass
class Pose:
    position: Vector
    orientation: tuple[float, float, float]


class FakeAirSim:
    Vector3r = Vector
    Pose = Pose

    @staticmethod
    def to_quaternion(pitch: float, roll: float, yaw: float):
        return (pitch, roll, yaw)


class FakeClient:
    def __init__(self) -> None:
        self.spawned: dict[str, Pose] = {}
        self.moved: list[tuple[str, Pose]] = []

    def simSpawnObject(self, name, asset, pose, scale, physics):
        assert asset == "Quadrotor1"
        assert not physics
        assert scale.x > 2.0
        self.spawned[name] = pose
        return name

    def simSetObjectPose(self, name, pose, teleport):
        assert teleport
        self.moved.append((name, pose))
        return True

    def simDestroyObject(self, name):
        self.spawned.pop(name, None)
        return True


def test_main_proxy_spawns_and_moves_all_targets() -> None:
    targets = generate_targets(CampaignScenario(target_count=5))
    raw = FakeClient()
    proxy = CampaignActorClientProxy(raw, FakeAirSim, targets)
    proxy.setup_targets()
    proxy.set_search_frame(1, 0.5)

    assert len(raw.spawned) == 5
    assert len(raw.moved) == 5
    assert proxy.logical_timestamp == 0.5
    assert proxy.actor_audit()["target_count"] == 5
