"""Stateful PN-to-pure-pursuit midcourse reacquisition selection."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import GuidanceCommand, GuidanceMode, GuidanceState
from .pn import compute_proportional_navigation_command, compute_pure_pursuit_command


@dataclass(frozen=True)
class MidcourseReacquisitionConfig:
    """Hysteresis and command bounds for PN overshoot recovery."""

    enter_closing_speed_mps: float = 0.0
    exit_closing_speed_mps: float = 1.0
    enter_consecutive_frames: int = 2
    exit_consecutive_frames: int = 3
    overshoot_range_increase_m: float = 2.0
    range_increase_epsilon_m: float = 0.05
    max_reacquisition_turn_rate_radps: float = 0.9

    def __post_init__(self) -> None:
        if self.exit_closing_speed_mps <= self.enter_closing_speed_mps:
            raise ValueError("exit_closing_speed_mps must exceed enter_closing_speed_mps")
        if self.enter_consecutive_frames < 1 or self.exit_consecutive_frames < 1:
            raise ValueError("consecutive frame thresholds must be at least one")
        if self.overshoot_range_increase_m < 0.0:
            raise ValueError("overshoot_range_increase_m must be nonnegative")
        if self.range_increase_epsilon_m < 0.0:
            raise ValueError("range_increase_epsilon_m must be nonnegative")
        if self.max_reacquisition_turn_rate_radps < 0.0:
            raise ValueError("max_reacquisition_turn_rate_radps must be nonnegative")


class MidcourseReacquisitionSelector:
    """Select radar PN or bounded pure pursuit for one assignment pair.

    Callers must keep one selector per assignment pair and reset it when the
    assignment identity/version changes. The helper does not allocate targets
    or alter either guidance-law implementation.
    """

    def __init__(self, config: MidcourseReacquisitionConfig | None = None) -> None:
        self.config = config or MidcourseReacquisitionConfig()
        self.reset()

    @property
    def reacquisition_active(self) -> bool:
        return self._reacquisition_active

    def reset(self) -> None:
        self._reacquisition_active = False
        self._entry_streak = 0
        self._recovery_streak = 0
        self._previous_range_m: float | None = None
        self._minimum_range_m: float | None = None
        self._active_entry_reason = ""
        self._selection_count = 0

    def compute_command(
        self,
        *,
        pursuer: GuidanceState,
        target: GuidanceState,
        dt_s: float,
        navigation_constant: float,
        mode: GuidanceMode | str = GuidanceMode.RADAR_MIDCOURSE,
        max_lateral_accel_mps2: float | None = None,
        max_turn_rate_radps: float | None = None,
        min_speed_mps: float = 1.0e-9,
    ) -> GuidanceCommand:
        """Return a selected midcourse command with auditable metadata."""

        pn_command = compute_proportional_navigation_command(
            pursuer=pursuer,
            target=target,
            dt_s=dt_s,
            navigation_constant=navigation_constant,
            mode=mode,
            max_lateral_accel_mps2=max_lateral_accel_mps2,
            max_turn_rate_radps=max_turn_rate_radps,
            min_speed_mps=min_speed_mps,
        )
        selection, reason, overshoot_detected = self._select(
            range_m=pn_command.range_m,
            closing_speed_mps=pn_command.closing_speed_mps,
        )
        if selection == "pure_pursuit_reacquisition":
            pursuit_turn_limit = self.config.max_reacquisition_turn_rate_radps
            if max_turn_rate_radps is not None:
                pursuit_turn_limit = min(pursuit_turn_limit, max_turn_rate_radps)
            command = compute_pure_pursuit_command(
                pursuer=pursuer,
                target=target,
                dt_s=dt_s,
                mode=mode,
                max_turn_rate_radps=pursuit_turn_limit,
                min_speed_mps=min_speed_mps,
            )
        else:
            command = pn_command

        self._selection_count += 1
        metadata = {
            **command.metadata,
            "guidance_law": (
                "pure_pursuit" if selection == "pure_pursuit_reacquisition" else "radar_pn"
            ),
            "midcourse_guidance_selection": selection,
            "midcourse_selection_reason": reason,
            "midcourse_reacquisition_active": self._reacquisition_active,
            "midcourse_reacquisition_entry_streak": self._entry_streak,
            "midcourse_reacquisition_recovery_streak": self._recovery_streak,
            "midcourse_reacquisition_entry_reason": self._active_entry_reason,
            "midcourse_overshoot_detected": overshoot_detected,
            "midcourse_minimum_range_m": self._minimum_range_m,
            "midcourse_enter_closing_speed_mps": self.config.enter_closing_speed_mps,
            "midcourse_exit_closing_speed_mps": self.config.exit_closing_speed_mps,
            "midcourse_selection_count": self._selection_count,
        }
        return replace(command, metadata=metadata)

    def _select(
        self,
        *,
        range_m: float,
        closing_speed_mps: float,
    ) -> tuple[str, str, bool]:
        cfg = self.config
        previous_range = self._previous_range_m
        minimum_before_sample = self._minimum_range_m
        overshoot_detected = bool(
            previous_range is not None
            and minimum_before_sample is not None
            and range_m >= minimum_before_sample + cfg.overshoot_range_increase_m
            and range_m > previous_range + cfg.range_increase_epsilon_m
        )
        self._previous_range_m = range_m
        self._minimum_range_m = (
            range_m if minimum_before_sample is None else min(minimum_before_sample, range_m)
        )

        not_closing = closing_speed_mps <= cfg.enter_closing_speed_mps
        entry_candidate = overshoot_detected or not_closing
        entry_reason = "range_increasing_after_closest_approach" if overshoot_detected else "not_closing"

        if not self._reacquisition_active:
            self._recovery_streak = 0
            if entry_candidate:
                self._entry_streak += 1
                if self._entry_streak >= cfg.enter_consecutive_frames:
                    self._reacquisition_active = True
                    self._active_entry_reason = entry_reason
                    return "pure_pursuit_reacquisition", entry_reason, overshoot_detected
                return "radar_pn", f"reacquisition_entry_hysteresis:{entry_reason}", overshoot_detected
            self._entry_streak = 0
            self._active_entry_reason = ""
            return "radar_pn", "pn_nominal_positive_closing", overshoot_detected

        self._entry_streak = 0
        if closing_speed_mps >= cfg.exit_closing_speed_mps:
            self._recovery_streak += 1
            if self._recovery_streak >= cfg.exit_consecutive_frames:
                self._reacquisition_active = False
                self._recovery_streak = 0
                self._active_entry_reason = ""
                return "radar_pn", "positive_closing_recovered", overshoot_detected
            return "pure_pursuit_reacquisition", "positive_closing_recovery_hysteresis", overshoot_detected

        self._recovery_streak = 0
        reason = self._active_entry_reason or entry_reason
        return "pure_pursuit_reacquisition", f"reacquisition_active:{reason}", overshoot_detected


def compute_midcourse_reacquisition_command(
    selector: MidcourseReacquisitionSelector,
    *,
    pursuer: GuidanceState,
    target: GuidanceState,
    dt_s: float,
    navigation_constant: float,
    mode: GuidanceMode | str = GuidanceMode.RADAR_MIDCOURSE,
    max_lateral_accel_mps2: float | None = None,
    max_turn_rate_radps: float | None = None,
    min_speed_mps: float = 1.0e-9,
) -> GuidanceCommand:
    """Functional entry point for callers that store selector state per pair."""

    return selector.compute_command(
        pursuer=pursuer,
        target=target,
        dt_s=dt_s,
        navigation_constant=navigation_constant,
        mode=mode,
        max_lateral_accel_mps2=max_lateral_accel_mps2,
        max_turn_rate_radps=max_turn_rate_radps,
        min_speed_mps=min_speed_mps,
    )
