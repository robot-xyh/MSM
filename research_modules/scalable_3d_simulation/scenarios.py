"""Versioned scenario catalog for scale-and-seed curriculum experiments."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

from .models import MotionProfile, ScenarioConfig


SCENARIO_CATALOG_VERSION = "scalable3d-catalog-v1"
AVAILABLE_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)


def make_curriculum_scenario(
    scenario: str,
    *,
    scale: int,
    seed: int,
    duration_s: float,
    base: ScenarioConfig | None = None,
    target_count: int | None = None,
    resource_count: int | None = None,
) -> ScenarioConfig:
    """Create one deterministic configuration without encoding scale in algorithms."""

    name = str(scenario).strip().lower()
    if name not in AVAILABLE_SCENARIOS:
        raise ValueError(
            f"unknown scenario {scenario!r}; choose from {', '.join(AVAILABLE_SCENARIOS)}"
        )
    if scale <= 0:
        raise ValueError("scale must be positive")
    targets = scale if target_count is None else int(target_count)
    resources = scale if resource_count is None else int(resource_count)
    config = base or ScenarioConfig()
    metadata: dict[str, Any] = dict(config.metadata)
    metadata.update(
        {
            "catalog_version": SCENARIO_CATALOG_VERSION,
            "scenario_family": name,
            "online_truth_policy": "forbidden",
        }
    )
    overrides: dict[str, Any] = {
        "scenario_name": f"{name}_{resources}v{targets}",
        "scenario_version": f"{name}-{resources}v{targets}-v1",
        "target_count": targets,
        "resource_count": resources,
        "recon_count": max(1, int(math.ceil(max(targets, resources) / 25.0))),
        "seed": int(seed),
        "duration_s": float(duration_s),
        "motion_profile": MotionProfile.CONSTANT_VELOCITY,
    }
    if name == "dense_crossing":
        overrides.update(
            motion_profile=MotionProfile.CROSSING,
            target_speed_min_mps=4.0,
            target_speed_max_mps=6.0,
            visual_false_alarm_rate=0.05,
        )
    elif name == "formation_split":
        overrides.update(motion_profile=MotionProfile.FORMATION_SPLIT)
    elif name == "evasive_multilevel":
        overrides.update(
            motion_profile=MotionProfile.EVASIVE,
            target_speed_min_mps=4.0,
            target_speed_max_mps=7.0,
        )
        metadata["altitude_challenge"] = "random_multilevel_with_vertical_manoeuvre"
    elif name == "delayed_noisy":
        overrides.update(
            radar_latency_s=0.8,
            visual_latency_s=0.25,
            radar_detection_probability=0.90,
            visual_detection_probability=0.80,
            visual_false_alarm_rate=0.12,
            radar_range_std_base_m=6.0,
            radar_range_std_per_km_m=3.0,
            radar_angle_std_deg=0.45,
        )
    elif name == "communication_degraded":
        overrides.update(
            communication_latency_s=0.18,
            communication_jitter_s=0.08,
            communication_drop_probability=0.20,
        )
        metadata["communication_fault_runtime_required"] = True
    elif name == "center_failure":
        metadata["fault_schedule"] = [
            {
                "time_s": float(duration_s) / 3.0,
                "component": "center",
                "action": "failed",
            }
        ]
        metadata["fault_schedule_runtime_required"] = True
    elif name == "secondary_failure":
        metadata["fault_schedule"] = [
            {
                "time_s": float(duration_s) / 3.0,
                "component": "center",
                "action": "failed",
            },
            {
                "time_s": 2.0 * float(duration_s) / 3.0,
                "component": "secondary",
                "action": "failed",
            },
        ]
        metadata["fault_schedule_runtime_required"] = True
    elif name == "high_threat_m_to_n":
        metadata.update(
            {
                "demand_pattern": "hybrid_2_primary_1_reserve",
                "high_threat_fraction": 0.10,
                "demand_runtime_required": True,
            }
        )
    overrides["metadata"] = metadata
    return replace(config, **overrides)
