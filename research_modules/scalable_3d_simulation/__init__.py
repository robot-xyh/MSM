"""Main-owned scalable three-dimensional point-mass simulation."""

from .camera_projection import (
    CameraIntrinsics,
    CameraPose,
    ProjectionBatch,
    look_at_rotation_ned_to_camera,
    project_points,
)
from .episode_bus import (
    EpisodeManifest,
    InMemoryEpisodeBus,
    VersionedEnvelope,
    assert_online_payload_truth_free,
    build_episode_manifest,
)
from .communication import (
    CommunicationStats,
    DeliveredMessage,
    DeterministicCommunicationNetwork,
    LinkProfile,
)
from .models import (
    BUS_SCHEMA_VERSION,
    OFFLINE_TRUTH_SCHEMA_VERSION,
    ONLINE_OBSERVATION_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
    WORLD_SCHEMA_VERSION,
    EntityKind,
    EntitySnapshot,
    KinematicLimits,
    ObservationBatch,
    OnlineSensorBatch,
    OfflineTruthLabel,
    ScenarioConfig,
    SensorMeasurement,
    WorldSnapshot,
)
from .orchestrator import EpisodeResult, Scalable3DEpisodeRunner, run_episode
from .sensor_scene import CameraView, SensorScene
from .scenarios import AVAILABLE_SCENARIOS, SCENARIO_CATALOG_VERSION, make_curriculum_scenario
from .runtime_ports import (
    PlatformNavigationBatch,
    RuntimePublication,
    RuntimeStepInput,
    RuntimeStepOutput,
    ScalableModuleStack,
)
from .module_stack import (
    INTEGRATED_STACK_SCHEMA_VERSION,
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from .world import ProximityInterceptEvent, VectorizedPointMassWorld
from .animation import write_trajectory_animation

__all__ = [
    "BUS_SCHEMA_VERSION",
    "AVAILABLE_SCENARIOS",
    "CameraIntrinsics",
    "CameraPose",
    "CameraView",
    "CommunicationStats",
    "DeliveredMessage",
    "DeterministicCommunicationNetwork",
    "EntityKind",
    "EntitySnapshot",
    "EpisodeManifest",
    "EpisodeResult",
    "InMemoryEpisodeBus",
    "INTEGRATED_STACK_SCHEMA_VERSION",
    "IntegratedScalableModuleStack",
    "IntegratedStackConfig",
    "KinematicLimits",
    "LinkProfile",
    "ObservationBatch",
    "OnlineSensorBatch",
    "OFFLINE_TRUTH_SCHEMA_VERSION",
    "OfflineTruthLabel",
    "ONLINE_OBSERVATION_SCHEMA_VERSION",
    "ProjectionBatch",
    "ProximityInterceptEvent",
    "PlatformNavigationBatch",
    "RuntimePublication",
    "RuntimeStepInput",
    "RuntimeStepOutput",
    "SCENARIO_SCHEMA_VERSION",
    "SCENARIO_CATALOG_VERSION",
    "Scalable3DEpisodeRunner",
    "ScalableModuleStack",
    "ScenarioConfig",
    "SensorMeasurement",
    "SensorScene",
    "VectorizedPointMassWorld",
    "VersionedEnvelope",
    "WORLD_SCHEMA_VERSION",
    "WorldSnapshot",
    "assert_online_payload_truth_free",
    "build_episode_manifest",
    "look_at_rotation_ned_to_camera",
    "make_curriculum_scenario",
    "project_points",
    "run_episode",
    "write_trajectory_animation",
]
