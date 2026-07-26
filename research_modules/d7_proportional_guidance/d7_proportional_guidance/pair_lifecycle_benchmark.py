"""Frozen-input benchmark for scalable D7 assignment-pair state lifecycle."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import tracemalloc
from typing import Any, Mapping

import numpy as np

from .scalable_3d_guidance import (
    AssignmentPairGuidanceInput3D,
    ScalableGuidanceController3D,
    TerminalVisualObservation3D,
)
from .terminal_gate import AssignmentGuidanceBinding, D4GuidancePermission


PAIR_LIFECYCLE_BENCHMARK_SCHEMA = "d7_pair_lifecycle_frozen_3d_v1"
_PLAN_ID = "plan-d7-pair-lifecycle-frozen"
_CAMERA_TO_NED = np.array(
    [
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=float,
)
_CAMERA_INTRINSICS = np.array(
    [
        [320.0, 0.0, 320.0],
        [0.0, 320.0, 240.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=float,
)


@dataclass(frozen=True)
class PairLifecycleBenchmarkResult3D:
    """Measured result of the deterministic 200-pair lifecycle fixture."""

    schema: str
    pair_count: int
    batch_count: int
    final_valid_pair_count: int
    final_active_state_count: int
    peak_active_state_count: int
    state_bound_violation_count: int
    transient_state_preserved: bool
    old_state_reclaim_verified: bool
    stale_plan_reject_count: int
    stale_plan_accept_count: int
    global_track_id_rewrite_count: int
    nonfinite_command_block_count: int
    command_saturation_count: int
    created_count: int
    reused_count: int
    reset_count: int
    reclaimed_count: int
    reset_reasons: Mapping[str, int] = field(default_factory=dict)
    reclaim_reasons: Mapping[str, int] = field(default_factory=dict)
    mode_counts: Mapping[str, int] = field(default_factory=dict)
    terminal_reject_reasons: Mapping[str, int] = field(default_factory=dict)
    pair_latency_p50_ms: float = 0.0
    pair_latency_p95_ms: float = 0.0
    batch_latency_p50_ms: float = 0.0
    batch_latency_p95_ms: float = 0.0
    peak_traced_memory_bytes: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "reset_reasons", dict(self.reset_reasons))
        object.__setattr__(self, "reclaim_reasons", dict(self.reclaim_reasons))
        object.__setattr__(self, "mode_counts", dict(self.mode_counts))
        object.__setattr__(
            self,
            "terminal_reject_reasons",
            dict(self.terminal_reject_reasons),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "pair_count": self.pair_count,
            "batch_count": self.batch_count,
            "final_valid_pair_count": self.final_valid_pair_count,
            "final_active_state_count": self.final_active_state_count,
            "peak_active_state_count": self.peak_active_state_count,
            "state_bound_violation_count": self.state_bound_violation_count,
            "transient_state_preserved": self.transient_state_preserved,
            "old_state_reclaim_verified": self.old_state_reclaim_verified,
            "stale_plan_reject_count": self.stale_plan_reject_count,
            "stale_plan_accept_count": self.stale_plan_accept_count,
            "global_track_id_rewrite_count": self.global_track_id_rewrite_count,
            "nonfinite_command_block_count": self.nonfinite_command_block_count,
            "command_saturation_count": self.command_saturation_count,
            "created_count": self.created_count,
            "reused_count": self.reused_count,
            "reset_count": self.reset_count,
            "reclaimed_count": self.reclaimed_count,
            "reset_reasons": dict(self.reset_reasons),
            "reclaim_reasons": dict(self.reclaim_reasons),
            "mode_counts": dict(self.mode_counts),
            "terminal_reject_reasons": dict(self.terminal_reject_reasons),
            "pair_latency_p50_ms": self.pair_latency_p50_ms,
            "pair_latency_p95_ms": self.pair_latency_p95_ms,
            "batch_latency_p50_ms": self.batch_latency_p50_ms,
            "batch_latency_p95_ms": self.batch_latency_p95_ms,
            "peak_traced_memory_bytes": self.peak_traced_memory_bytes,
        }


def run_pair_lifecycle_frozen_benchmark(
    *,
    pair_count: int = 200,
) -> PairLifecycleBenchmarkResult3D:
    """Run a deterministic mixed-mode lifecycle benchmark.

    The formal fixture uses 200 pairs. Smaller values are accepted for local
    diagnostics, but the reassignment/lost/withdrawn partitions scale down.
    """

    if pair_count < 20:
        raise ValueError("pair_count must be at least 20")
    controller = ScalableGuidanceController3D()
    batches = []
    mode_counts: Counter[str] = Counter()
    reset_reasons: Counter[str] = Counter()
    reclaim_reasons: Counter[str] = Counter()
    terminal_reject_reasons: Counter[str] = Counter()
    pair_latencies: list[float] = []
    batch_latencies: list[float] = []
    state_bound_violation_count = 0
    transient_state_preserved = False

    visual_end = min(pair_count, max(8, int(round(0.60 * pair_count))))
    pending_end = min(visual_end, max(2, int(round(0.10 * pair_count))))
    reacquire_no_observation_end = min(
        visual_end,
        pending_end + max(2, int(round(0.10 * pair_count))),
    )
    reacquire_with_observation_end = min(
        visual_end,
        reacquire_no_observation_end + max(2, int(round(0.10 * pair_count))),
    )
    locked_dropout_end = min(
        visual_end,
        reacquire_with_observation_end + max(2, int(round(0.10 * pair_count))),
    )

    def execute(inputs: list[AssignmentPairGuidanceInput3D]) -> None:
        nonlocal state_bound_violation_count
        batch = controller.command_batch(inputs, resource_count=pair_count)
        diagnostics = batch.lifecycle_diagnostics
        assert diagnostics is not None
        batches.append(batch)
        mode_counts.update(command.mode.value for command in batch.pair_commands)
        reset_reasons.update(diagnostics.reset_reasons)
        reclaim_reasons.update(diagnostics.reclaim_reasons)
        terminal_reject_reasons.update(diagnostics.terminal_reject_reasons)
        pair_latencies.extend(diagnostics.pair_latency_ms)
        batch_latencies.append(diagnostics.batch_latency_ms)
        if diagnostics.active_state_count > diagnostics.active_pair_count:
            state_bound_violation_count += 1

    tracemalloc.start()
    try:
        for frame_index, half_size_px in enumerate((10.0, 13.0, 17.0)):
            timestamp_s = 0.1 * frame_index
            execute(
                [
                    _pair_input(
                        index=index,
                        target_id=_target_id(index),
                        timestamp_s=timestamp_s,
                        plan_version=1,
                        decision_state=("locked" if index < visual_end else None),
                        visual_half_size_px=(
                            half_size_px if index < visual_end else None
                        ),
                    )
                    for index in range(pair_count)
                ]
            )

        representative_indices = (
            0,
            pending_end,
            reacquire_no_observation_end,
            reacquire_with_observation_end,
        )
        before_transient = {
            index: controller.pair_state(_resource_id(index), _target_id(index))
            for index in representative_indices
            if index < visual_end
        }
        transient_inputs = []
        for index in range(pair_count):
            permission = D4GuidancePermission(action="continue_center")
            decision_state: str | None = None
            visual_half_size_px: float | None = None
            if index < pending_end:
                permission = D4GuidancePermission(action="request_center_replan")
                decision_state = "locked"
                visual_half_size_px = 18.0
            elif index < reacquire_no_observation_end:
                decision_state = "reacquire"
            elif index < reacquire_with_observation_end:
                decision_state = "reacquire"
                visual_half_size_px = 18.0
            elif index < locked_dropout_end:
                decision_state = "locked"
            elif index < visual_end:
                decision_state = "locked"
                visual_half_size_px = 18.0
            transient_inputs.append(
                _pair_input(
                    index=index,
                    target_id=_target_id(index),
                    timestamp_s=0.3,
                    plan_version=1,
                    decision_state=decision_state,
                    visual_half_size_px=visual_half_size_px,
                    permission=permission,
                )
            )
        execute(transient_inputs)
        after_transient = {
            index: controller.pair_state(_resource_id(index), _target_id(index))
            for index in before_transient
        }
        transient_state_preserved = all(
            before is not None
            and after_transient[index] is not None
            and before.los_filter_initialized
            and after_transient[index].los_filter_initialized
            and after_transient[index].ttc_sample_count == before.ttc_sample_count
            and after_transient[index].last_visual_command_timestamp_s
            == before.last_visual_command_timestamp_s
            for index, before in before_transient.items()
        )

        execute(
            [
                _pair_input(
                    index=index,
                    target_id=_target_id(index),
                    timestamp_s=0.4,
                    plan_version=1,
                    decision_state=("locked" if index < visual_end else None),
                    visual_half_size_px=(20.0 if index < visual_end else None),
                )
                for index in range(pair_count)
            ]
        )
        execute(
            [
                _pair_input(
                    index=index,
                    target_id=_target_id(index),
                    timestamp_s=0.5,
                    plan_version=2,
                )
                for index in range(pair_count)
            ]
        )

        rebind_count = max(1, int(round(0.20 * pair_count)))
        lost_count = max(1, int(round(0.05 * pair_count)))
        withdrawn_count = max(1, int(round(0.10 * pair_count)))
        active_limit = pair_count - lost_count - withdrawn_count
        input_limit = pair_count - withdrawn_count
        partial_inputs = []
        for index in range(input_limit):
            target_id = (
                _replacement_target_id(index)
                if index < rebind_count
                else _target_id(index)
            )
            lifecycle_state = "lost" if index >= active_limit else "confirmed"
            partial_inputs.append(
                _pair_input(
                    index=index,
                    target_id=target_id,
                    timestamp_s=0.6,
                    plan_version=3,
                    lifecycle_state=lifecycle_state,
                )
            )
        execute(partial_inputs)

        stale_start = min(rebind_count, active_limit)
        stale_count = min(max(1, int(round(0.05 * pair_count))), active_limit - stale_start)
        stale_indices = set(range(stale_start, stale_start + stale_count))
        stale_inputs = []
        for index in range(active_limit):
            target_id = (
                _replacement_target_id(index)
                if index < rebind_count
                else _target_id(index)
            )
            stale_inputs.append(
                _pair_input(
                    index=index,
                    target_id=target_id,
                    timestamp_s=0.7,
                    plan_version=(2 if index in stale_indices else 3),
                    active_plan_version=3,
                )
            )
        execute(stale_inputs)

        execute(
            [
                _pair_input(
                    index=index,
                    target_id=(
                        _replacement_target_id(index)
                        if index < rebind_count
                        else _target_id(index)
                    ),
                    timestamp_s=0.8,
                    plan_version=3,
                )
                for index in range(active_limit)
            ]
        )
        _, peak_traced_memory_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    diagnostics = [batch.lifecycle_diagnostics for batch in batches]
    assert all(item is not None for item in diagnostics)
    typed_diagnostics = [item for item in diagnostics if item is not None]
    old_state_reclaim_verified = all(
        controller.pair_state(_resource_id(index), _target_id(index)) is None
        for index in range(rebind_count)
    ) and all(
        controller.pair_state(_resource_id(index), _target_id(index)) is None
        for index in range(active_limit, pair_count)
    )
    pair_latency_values = np.asarray(pair_latencies, dtype=float)
    batch_latency_values = np.asarray(batch_latencies, dtype=float)
    final_active_state_count = controller.active_pair_state_count
    return PairLifecycleBenchmarkResult3D(
        schema=PAIR_LIFECYCLE_BENCHMARK_SCHEMA,
        pair_count=pair_count,
        batch_count=len(batches),
        final_valid_pair_count=active_limit,
        final_active_state_count=final_active_state_count,
        peak_active_state_count=max(
            item.peak_active_state_count for item in typed_diagnostics
        ),
        state_bound_violation_count=state_bound_violation_count,
        transient_state_preserved=transient_state_preserved,
        old_state_reclaim_verified=old_state_reclaim_verified,
        stale_plan_reject_count=sum(
            item.stale_plan_reject_count for item in typed_diagnostics
        ),
        stale_plan_accept_count=sum(
            item.stale_plan_accept_count for item in typed_diagnostics
        ),
        global_track_id_rewrite_count=sum(
            item.global_track_id_rewrite_count for item in typed_diagnostics
        ),
        nonfinite_command_block_count=sum(
            item.nonfinite_command_block_count for item in typed_diagnostics
        ),
        command_saturation_count=sum(
            item.command_saturation_count for item in typed_diagnostics
        ),
        created_count=typed_diagnostics[-1].cumulative_created_count,
        reused_count=typed_diagnostics[-1].cumulative_reused_count,
        reset_count=typed_diagnostics[-1].cumulative_reset_count,
        reclaimed_count=typed_diagnostics[-1].cumulative_reclaimed_count,
        reset_reasons=reset_reasons,
        reclaim_reasons=reclaim_reasons,
        mode_counts=mode_counts,
        terminal_reject_reasons=terminal_reject_reasons,
        pair_latency_p50_ms=float(np.percentile(pair_latency_values, 50.0)),
        pair_latency_p95_ms=float(np.percentile(pair_latency_values, 95.0)),
        batch_latency_p50_ms=float(np.percentile(batch_latency_values, 50.0)),
        batch_latency_p95_ms=float(np.percentile(batch_latency_values, 95.0)),
        peak_traced_memory_bytes=int(peak_traced_memory_bytes),
    )


def _pair_input(
    *,
    index: int,
    target_id: str,
    timestamp_s: float,
    plan_version: int,
    active_plan_version: int | None = None,
    lifecycle_state: str = "confirmed",
    decision_state: str | None = None,
    visual_half_size_px: float | None = None,
    permission: D4GuidancePermission | None = None,
) -> AssignmentPairGuidanceInput3D:
    resource_id = _resource_id(index)
    near_terminal = decision_state is not None or visual_half_size_px is not None
    range_m = 50.0 if near_terminal else 500.0
    east_m = 0.5 * index
    resource_state = np.array([0.0, east_m, -40.0, 4.0, 0.0, 0.0], dtype=float)
    target_state = np.array([range_m, east_m, -40.0, 0.0, 0.0, 0.0], dtype=float)
    association = (
        _association(
            resource_id=resource_id,
            target_id=target_id,
            plan_version=plan_version,
            decision_state=decision_state,
        )
        if decision_state is not None
        else None
    )
    visual = (
        _visual_observation(
            resource_id=resource_id,
            target_id=target_id,
            timestamp_s=timestamp_s,
            half_size_px=visual_half_size_px,
        )
        if visual_half_size_px is not None
        else None
    )
    return AssignmentPairGuidanceInput3D(
        resource_index=index,
        resource_state=resource_state,
        global_track={
            "global_track_id": target_id,
            "state": target_state,
            "covariance": np.eye(6, dtype=float),
            "timestamp": timestamp_s,
            "lifecycle_state": lifecycle_state,
        },
        binding=AssignmentGuidanceBinding(
            plan_id=_PLAN_ID,
            plan_version=plan_version,
            resource_id=resource_id,
            vehicle_name=resource_id,
            assigned_global_track_id=target_id,
            track_version=plan_version,
            authorization_state="recorded",
            owner_node_id="center",
            assignment_id=f"{_PLAN_ID}:{resource_id}:{target_id}",
        ),
        d4_permission=permission or D4GuidancePermission(action="continue_center"),
        terminal_association=association,
        active_plan_id=_PLAN_ID,
        active_plan_version=(
            plan_version if active_plan_version is None else active_plan_version
        ),
        timestamp_s=timestamp_s,
        visual_observation=visual,
        camera_recognition_ready=True,
    )


def _association(
    *,
    resource_id: str,
    target_id: str,
    plan_version: int,
    decision_state: str,
) -> dict[str, Any]:
    return {
        "assigned_global_track_id": target_id,
        "local_track_id": f"{resource_id}:camera-track",
        "association_confidence": 0.95,
        "friend_conflict_state": "none",
        "decision_state": decision_state,
        "assignment_version": plan_version,
        "plan_id": _PLAN_ID,
        "plan_version": plan_version,
        "resource_id": resource_id,
        "metadata": {"camera_recognition_ready": True, "maneuver_capable": True},
    }


def _visual_observation(
    *,
    resource_id: str,
    target_id: str,
    timestamp_s: float,
    half_size_px: float,
) -> TerminalVisualObservation3D:
    return TerminalVisualObservation3D(
        timestamp_s=timestamp_s,
        bbox_xyxy=(
            320.0 - half_size_px,
            240.0 - half_size_px,
            320.0 + half_size_px,
            240.0 + half_size_px,
        ),
        image_width_px=640,
        image_height_px=480,
        camera_intrinsics=_CAMERA_INTRINSICS,
        camera_to_ned_rotation=_CAMERA_TO_NED,
        detection_confidence=0.95,
        local_track_id=f"{resource_id}:camera-track",
        assigned_global_track_id=target_id,
        camera_id=f"{resource_id}:front_center",
    )


def _resource_id(index: int) -> str:
    return f"INT-{index + 1:04d}"


def _target_id(index: int) -> str:
    return f"GT-{index + 1:04d}"


def _replacement_target_id(index: int) -> str:
    return f"GT-R-{index + 1:04d}"


def main() -> int:
    result = run_pair_lifecycle_frozen_benchmark()
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
