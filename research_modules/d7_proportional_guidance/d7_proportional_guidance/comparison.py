"""Offline report rows for PN/Pure-Pursuit/visual-PNG comparisons."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from statistics import mean
from typing import Any, Iterable, Literal, Mapping

from .calibration import DEFAULT_CALIBRATION_THRESHOLD_VERSION
from .models import GuidanceConfig
from .replay import BBOX_LOS_REPLAY_BOUNDARY, evaluate_bbox_los_replay
from .simulator import simulate_guidance_episode
from .terminal_gate import AssignmentGuidanceBinding, D4GuidancePermission
from .vision_png import PngGuidanceConfig


GuidanceComparisonStrategy = Literal["pn", "pure_pursuit", "png_vm", "png_ttc"]
DEFAULT_COMPARISON_STRATEGIES: tuple[GuidanceComparisonStrategy, ...] = (
    "pn",
    "pure_pursuit",
    "png_vm",
    "png_ttc",
)


@dataclass(frozen=True)
class GuidanceStrategyComparisonRow:
    """One strategy/seed row with D6-friendly report fields."""

    seed: int
    strategy: str
    guidance_law: str
    boundary: str
    sample_count: int
    min_range_m: float | None
    final_range_m: float | None
    time_to_intercept_s: float | None
    terminal_mode_entered: bool
    visual_png_switch_count: int
    terminal_switch_allowed_rate: float
    terminal_range_m: float | None = None
    closing_speed_mps: float | None = None
    bbox_gate_pass_rate: float | None = None
    los_gate_pass_rate: float | None = None
    maneuver_gate_pass_rate: float | None = None
    d5_lock_consistent_rate: float | None = None
    d3_owner_version_consistent_rate: float | None = None
    threshold_advisory_version: str = DEFAULT_CALIBRATION_THRESHOLD_VERSION
    d4_action_block_reasons: dict[str, int] = field(default_factory=dict)
    secondary_capability_class_counts: dict[str, int] = field(default_factory=dict)
    secondary_readiness_class_counts: dict[str, int] = field(default_factory=dict)
    detect_registration_outcome_counts: dict[str, int] = field(default_factory=dict)
    terminal_contract_reject_reasons: dict[str, int] = field(default_factory=dict)
    terminal_switch_reject_reasons: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_guidance_strategy_comparison(
    *,
    seeds: Iterable[int],
    strategies: Iterable[GuidanceComparisonStrategy] = DEFAULT_COMPARISON_STRATEGIES,
    base_config: GuidanceConfig | None = None,
    png_config: PngGuidanceConfig | None = None,
) -> list[GuidanceStrategyComparisonRow]:
    """Return offline comparison rows for PN, pure pursuit, png_vm, and png_ttc."""

    rows: list[GuidanceStrategyComparisonRow] = []
    for seed in seeds:
        for strategy in strategies:
            if strategy in {"pn", "pure_pursuit"}:
                rows.append(_run_point_mass_strategy(seed, strategy, base_config))
            elif strategy in {"png_vm", "png_ttc"}:
                rows.append(_run_visual_png_strategy(seed, strategy, png_config))
            else:
                raise ValueError(f"unknown guidance comparison strategy: {strategy}")
    return rows


def summarize_guidance_strategy_comparison(
    rows: Iterable[GuidanceStrategyComparisonRow],
) -> dict[str, Any]:
    """Aggregate comparison rows without recomputing guidance."""

    grouped: dict[str, list[GuidanceStrategyComparisonRow]] = {}
    for row in rows:
        grouped.setdefault(row.strategy, []).append(row)

    by_strategy: dict[str, Any] = {}
    for strategy, strategy_rows in grouped.items():
        min_ranges = [row.min_range_m for row in strategy_rows if row.min_range_m is not None]
        final_ranges = [row.final_range_m for row in strategy_rows if row.final_range_m is not None]
        contract_reasons: Counter[str] = Counter()
        switch_reasons: Counter[str] = Counter()
        d4_block_reasons: Counter[str] = Counter()
        secondary_capability_classes: Counter[str] = Counter()
        secondary_readiness_classes: Counter[str] = Counter()
        detect_registration_outcomes: Counter[str] = Counter()
        for row in strategy_rows:
            contract_reasons.update(row.terminal_contract_reject_reasons)
            switch_reasons.update(row.terminal_switch_reject_reasons)
            d4_block_reasons.update(row.d4_action_block_reasons)
            secondary_capability_classes.update(row.secondary_capability_class_counts)
            secondary_readiness_classes.update(row.secondary_readiness_class_counts)
            detect_registration_outcomes.update(row.detect_registration_outcome_counts)
        terminal_ranges = [
            row.terminal_range_m for row in strategy_rows if row.terminal_range_m is not None
        ]
        closing_speeds = [
            row.closing_speed_mps for row in strategy_rows if row.closing_speed_mps is not None
        ]
        by_strategy[strategy] = {
            "seed_count": len(strategy_rows),
            "mean_min_range_m": mean(min_ranges) if min_ranges else None,
            "mean_final_range_m": mean(final_ranges) if final_ranges else None,
            "mean_terminal_range_m": mean(terminal_ranges) if terminal_ranges else None,
            "mean_closing_speed_mps": mean(closing_speeds) if closing_speeds else None,
            "visual_png_switch_count": sum(row.visual_png_switch_count for row in strategy_rows),
            "mean_terminal_switch_allowed_rate": mean(
                row.terminal_switch_allowed_rate for row in strategy_rows
            )
            if strategy_rows
            else 0.0,
            "mean_bbox_gate_pass_rate": _mean_optional(
                row.bbox_gate_pass_rate for row in strategy_rows
            ),
            "mean_los_gate_pass_rate": _mean_optional(
                row.los_gate_pass_rate for row in strategy_rows
            ),
            "mean_maneuver_gate_pass_rate": _mean_optional(
                row.maneuver_gate_pass_rate for row in strategy_rows
            ),
            "mean_d5_lock_consistent_rate": _mean_optional(
                row.d5_lock_consistent_rate for row in strategy_rows
            ),
            "mean_d3_owner_version_consistent_rate": _mean_optional(
                row.d3_owner_version_consistent_rate for row in strategy_rows
            ),
            "threshold_advisory_versions": sorted(
                {row.threshold_advisory_version for row in strategy_rows if row.threshold_advisory_version}
            ),
            "d4_action_block_reasons": dict(d4_block_reasons),
            "secondary_capability_class_counts": dict(secondary_capability_classes),
            "secondary_readiness_class_counts": dict(secondary_readiness_classes),
            "detect_registration_outcome_counts": dict(detect_registration_outcomes),
            "terminal_contract_reject_reasons": dict(contract_reasons),
            "terminal_switch_reject_reasons": dict(switch_reasons),
        }
    return {
        "row_count": sum(len(strategy_rows) for strategy_rows in grouped.values()),
        "strategy_count": len(grouped),
        "strategies": by_strategy,
    }


def _run_point_mass_strategy(
    seed: int,
    strategy: GuidanceComparisonStrategy,
    base_config: GuidanceConfig | None,
) -> GuidanceStrategyComparisonRow:
    cfg = replace(
        base_config or GuidanceConfig(stop_at_intercept_radius=False),
        guidance_law=strategy,
        random_seed=int(seed),
    )
    records, summary = simulate_guidance_episode(config=cfg)
    stopped = bool(summary.get("stopped_on_intercept_radius", False))
    closest_record = min(records, key=lambda record: record.range_m) if records else None
    return GuidanceStrategyComparisonRow(
        seed=int(seed),
        strategy=strategy,
        guidance_law=strategy,
        boundary=str(summary["boundary"]),
        sample_count=int(summary["steps"]),
        min_range_m=float(summary["min_range_m"]),
        final_range_m=float(summary["final_range_m"]),
        time_to_intercept_s=float(summary["closest_time_s"]) if stopped else None,
        terminal_mode_entered=bool(summary["terminal_mode_entered"]),
        visual_png_switch_count=0,
        terminal_switch_allowed_rate=0.0,
        terminal_range_m=float(summary["min_range_m"]),
        closing_speed_mps=(
            float(closest_record.closing_speed_mps) if closest_record is not None else None
        ),
        bbox_gate_pass_rate=None,
        los_gate_pass_rate=None,
        maneuver_gate_pass_rate=None,
        d5_lock_consistent_rate=None,
        d3_owner_version_consistent_rate=None,
        metadata={
            "mode_sequence": tuple(summary["mode_sequence"]),
            "stopped_on_intercept_radius": stopped,
        },
    )


def _run_visual_png_strategy(
    seed: int,
    strategy: GuidanceComparisonStrategy,
    png_config: PngGuidanceConfig | None,
) -> GuidanceStrategyComparisonRow:
    cfg = replace(_default_png_config(png_config), law=strategy)
    binding = AssignmentGuidanceBinding(
        plan_id=f"comparison-plan-{seed}",
        plan_version=1,
        owner_node_id="center",
        assignment_id=f"comparison-R1-G1-{seed}",
        resource_id="R1",
        vehicle_name="Interceptor_R1",
        assigned_global_track_id="G1",
        track_version=100 + int(seed),
        authorization_state="approved",
    )
    terminal_association = {
        "assigned_global_track_id": "G1",
        "local_track_id": f"R1:replay:{seed}",
        "decision_state": "locked",
        "friend_conflict_state": "none",
        "assignment_version": 100 + int(seed),
    }
    outputs, summary = evaluate_bbox_los_replay(
        _comparison_bbox_sequence(seed, cfg),
        binding=binding,
        d4_permission=D4GuidancePermission(
            action="continue_center",
            target_node_id="center",
            new_plan_id=binding.plan_id,
            new_plan_version=binding.plan_version,
        ),
        terminal_association=terminal_association,
        config=cfg,
        source=f"{strategy}_comparison_replay",
        assigned_global_track_id="G1",
        camera_id="front_center",
        current_heading_rad=0.0,
        current_speed_mps=8.0,
        intercept_speed_mps=8.0,
        relative_position_ned=(30.0, 1.0, 0.0),
        relative_velocity_ned=(-5.0, 0.0, 0.0),
    )
    return GuidanceStrategyComparisonRow(
        seed=int(seed),
        strategy=strategy,
        guidance_law=strategy,
        boundary=BBOX_LOS_REPLAY_BOUNDARY,
        sample_count=int(summary["sample_count"]),
        min_range_m=None,
        final_range_m=None,
        time_to_intercept_s=None,
        terminal_mode_entered=any(output.visual_png_enabled for output in outputs),
        visual_png_switch_count=int(summary["visual_png_switch_count"]),
        terminal_switch_allowed_rate=float(summary["terminal_switch_allowed_rate"]),
        terminal_range_m=_optional_summary_float(summary, "terminal_range_m_mean"),
        closing_speed_mps=_optional_summary_float(summary, "closing_speed_mps_mean"),
        bbox_gate_pass_rate=float(summary["camera_quality_gate_pass_rate"]),
        los_gate_pass_rate=float(summary["los_quality_gate_pass_rate"]),
        maneuver_gate_pass_rate=float(summary["maneuver_margin_gate_pass_rate"]),
        d5_lock_consistent_rate=float(summary["d5_lock_consistent_rate"]),
        d3_owner_version_consistent_rate=float(summary["d3_owner_version_consistent_rate"]),
        d4_action_block_reasons=dict(summary["d4_action_block_reasons"]),
        secondary_capability_class_counts=dict(summary["secondary_capability_class_counts"]),
        secondary_readiness_class_counts=dict(summary["secondary_readiness_class_counts"]),
        detect_registration_outcome_counts=dict(summary["detect_registration_outcome_counts"]),
        terminal_contract_reject_reasons=dict(summary["terminal_contract_reject_reasons"]),
        terminal_switch_reject_reasons=dict(summary["terminal_switch_reject_reasons"]),
        metadata={
            "replay_source": summary["replay_source"],
            "vehicle_control": False,
        },
    )


def _default_png_config(config: PngGuidanceConfig | None) -> PngGuidanceConfig:
    if config is not None:
        return config
    return PngGuidanceConfig(
        dt_s=0.1,
        image_width_px=640,
        image_height_px=480,
        focal_length_px=320.0,
        min_bbox_area_ratio=0.001,
        min_detection_confidence=0.55,
        min_stable_frames=2,
        edge_margin_ratio=0.03,
        max_los_rate_variance_radps2=2.0,
        los_rate_window=5,
        max_visual_latency_s=0.35,
        navigation_constant=3.0,
    )


def _comparison_bbox_sequence(seed: int, cfg: PngGuidanceConfig) -> list[dict[str, Any]]:
    offset_px = float((int(seed) % 5) - 2)
    return [
        {
            "timestamp_s": index * cfg.dt_s,
            "bbox_xyxy": (
                320.0 + offset_px - half_size,
                240.0 - half_size,
                320.0 + offset_px + half_size,
                240.0 + half_size,
            ),
            "confidence": 0.9,
            "track_id": f"R1:replay:{seed}",
            "measurement_age_s": 0.02,
            "detect_registration_outcome": "registered",
            "projection_valid": True,
            "gate_pass": True,
        }
        for index, half_size in enumerate((28.0, 31.0, 34.0, 37.0, 40.0, 43.0))
    ]


def _mean_optional(values: Iterable[float | None]) -> float | None:
    items = [float(value) for value in values if value is not None]
    return mean(items) if items else None


def _optional_summary_float(summary: Mapping[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if value is None:
        return None
    return float(value)
