"""V5 protocol profile for the phase-180 target-track experiment."""

from __future__ import annotations

from .contracts import BenchmarkProtocol


V5_EXPERIMENT_PROFILE = "phase180_target_track_gnn_v1"
V5_OUTPUT_VERSION = "scale_funnel_v5_phase180_targettrack"
V5_TARGET_COUNTS = (40, 60, 100)
V5_CAMERA_B_PHASE_OFFSET_S = 1.0
V5_SEED_PREFIX = 20300000


def v5_protocol_for_target_count(target_count: int) -> BenchmarkProtocol:
    """Return one disjoint V5 protocol with a half-revolution B-station offset."""

    target_count = int(target_count)
    if target_count not in V5_TARGET_COUNTS:
        raise ValueError("V5 target count must be 40, 60, or 100")
    train_count, validation_count, test_count = (
        (24, 6, 20) if target_count == 100 else (8, 2, 5)
    )
    seed_base = V5_SEED_PREFIX + target_count * 100
    return BenchmarkProtocol(
        train_seeds=tuple(range(seed_base + 1, seed_base + train_count + 1)),
        validation_seeds=tuple(
            range(seed_base + 101, seed_base + 101 + validation_count)
        ),
        test_seeds=tuple(
            range(seed_base + 301, seed_base + 301 + test_count)
        ),
        target_count=target_count,
        zero_heading_count=target_count // 2,
        minus_thirty_heading_count=target_count - target_count // 2,
        camera_b_scan_phase_offset_s=V5_CAMERA_B_PHASE_OFFSET_S,
        corruption_levels=("clean", "light", "medium", "heavy"),
    )


def v5_protocols() -> tuple[BenchmarkProtocol, ...]:
    return tuple(v5_protocol_for_target_count(count) for count in V5_TARGET_COUNTS)


__all__ = [
    "V5_CAMERA_B_PHASE_OFFSET_S",
    "V5_EXPERIMENT_PROFILE",
    "V5_OUTPUT_VERSION",
    "V5_SEED_PREFIX",
    "V5_TARGET_COUNTS",
    "v5_protocol_for_target_count",
    "v5_protocols",
]
