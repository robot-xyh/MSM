"""Shared models for the integrated offline simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ScenarioConfig:
    """Configuration for one deterministic offline integration episode."""

    name: str = "nominal_5v5"
    seed: int = 7
    duration_s: float = 8.0
    dt_s: float = 0.5
    target_count: int = 5
    resource_count: int = 5
    assignment_period_s: float = 1.0
    terminal_start_s: float = 3.0
    radar_latency_s: float = 0.6
    radar_noise_scale: float = 0.7
    visual_noise_px: float = 0.4
    acoustic_enabled: bool = True
    eo_enabled: bool = True
    c2_failure_time_s: float | None = None
    secondary_failure_time_s: float | None = None
    active_mismatch_start_s: float | None = None
    friend_overlap_start_s: float | None = None
    crossing: bool = False
    cooperative_demand_enabled: bool = False
    cooperative_high_threat_target_count: int = 1
    high_threat_required_resource_count: int = 3
    cooperative_coordination_mode: str = "hybrid"
    cooperative_primary_count: int = 2
    cooperative_wave_gap_s: float = 2.0
    cooperative_minimum_separation_s: float = 0.5
    output_root: Path | None = None

    def timestamps(self) -> list[float]:
        values = np.arange(0.0, self.duration_s + 1e-9, self.dt_s)
        return [round(float(value), 6) for value in values]


@dataclass(frozen=True)
class TruthState:
    """Synthetic point-mass truth state in the local NED-like workspace."""

    truth_id: str
    timestamp: float
    position: np.ndarray
    velocity: np.ndarray
    threat_score: float
    coverage_cell: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", np.asarray(self.position, dtype=float).reshape(3))
        object.__setattr__(self, "velocity", np.asarray(self.velocity, dtype=float).reshape(3))


@dataclass(frozen=True)
class ResourcePlatform:
    """Abstract resource platform used by D3/D4/D5 adapters."""

    resource_id: str
    position: np.ndarray
    coverage_cell: str
    health_score: float = 1.0
    status: str = "available"

    def __post_init__(self) -> None:
        object.__setattr__(self, "position", np.asarray(self.position, dtype=float).reshape(3))


@dataclass(frozen=True)
class IntegratedDecisionRecord:
    """Recorded D4 arbitration decision for one terminal association window."""

    timestamp: float
    resource_id: str
    global_track_id: str
    mode: str
    action: str
    reason: str
    target_node_id: str | None = None
    terminal_consistent: bool = False
    risk_factors: tuple[str, ...] = ()


@dataclass
class EpisodeResult:
    """Outputs from one integrated offline episode."""

    scenario: ScenarioConfig
    metrics: Any
    truth_summary: dict[str, Any]
    decisions: list[IntegratedDecisionRecord]
    guidance_records: list[Any] = field(default_factory=list)
    guidance_summaries: list[dict[str, Any]] = field(default_factory=list)
    output_paths: dict[str, Path] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
