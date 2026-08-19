from dataclasses import asdict
import json
import math
from pathlib import Path

from dual_optical_40target.core import scan_yaw_deg
from dual_optical_online_benchmark.contracts import (
    benchmark_protocol_for_target_count,
)
from dual_optical_online_benchmark.episode_worker import (
    WORKER_PROTOCOL_SCHEMA,
    build_config,
    load_worker_protocol,
)
from dual_optical_online_benchmark.v5 import (
    V5_TARGET_COUNTS,
    v5_protocol_for_target_count,
)


def test_v5_protocols_use_disjoint_seeds_and_half_revolution_offset() -> None:
    all_seeds: set[int] = set()
    for target_count in V5_TARGET_COUNTS:
        protocol = v5_protocol_for_target_count(target_count)
        current = set(
            protocol.train_seeds
            + protocol.validation_seeds
            + protocol.test_seeds
        )
        assert all_seeds.isdisjoint(current)
        all_seeds.update(current)
        assert protocol.camera_b_scan_phase_offset_s == 1.0
        assert protocol.scan_period_s == 2.0
        yaw_a = scan_yaw_deg(
            0.25, 0.0, period_s=protocol.scan_period_s, mode="continuous_360"
        )
        yaw_b = scan_yaw_deg(
            0.25 + protocol.camera_b_scan_phase_offset_s,
            0.0,
            period_s=protocol.scan_period_s,
            mode="continuous_360",
        )
        delta = (yaw_b - yaw_a + 180.0) % 360.0 - 180.0
        assert math.isclose(abs(delta), 180.0, abs_tol=1.0e-9)


def test_v4_protocol_default_remains_zero_phase() -> None:
    assert benchmark_protocol_for_target_count(40).camera_b_scan_phase_offset_s == 0.0


def test_worker_loads_exact_v5_protocol(tmp_path: Path) -> None:
    protocol = v5_protocol_for_target_count(40)
    path = tmp_path / "worker_protocol.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": WORKER_PROTOCOL_SCHEMA,
                "protocol": asdict(protocol),
                "protocol_fingerprint": protocol.fingerprint,
            }
        ),
        encoding="utf-8",
    )
    restored = load_worker_protocol(path, target_count=40)
    config = build_config(restored.train_seeds[0], 41451, protocol=restored)
    assert restored == protocol
    assert config.camera_b_scan_phase_offset_s == 1.0
