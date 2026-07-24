from __future__ import annotations

import json
from pathlib import Path

from d1_sensor_fusion.scan_input_performance import (
    benchmark_scan_input_implementations,
    write_scan_input_performance_report,
)


def _write_frozen_input(path: Path) -> None:
    records = []
    for index in range(6):
        measurement_timestamp = 0.5 * float(index)
        arrival_timestamp = measurement_timestamp + 0.1
        batch_id = f"benchmark-scan-{index:03d}"
        records.append(
            {
                "sequence": index + 1,
                "topic": "sensor.observations",
                "source": "RADAR-BENCHMARK",
                "timestamp": arrival_timestamp,
                "schema_version": "scalable3d-observation-v1",
                "payload": {
                    "batch_id": batch_id,
                    "sensor_id": "RADAR-BENCHMARK",
                    "measurement_timestamp": measurement_timestamp,
                    "arrival_timestamp": arrival_timestamp,
                    "measurements": [
                        {
                            "observation_id": f"{batch_id}-obs-{target_index}",
                            "sensor_id": "RADAR-BENCHMARK",
                            "modality": "radar",
                            "measurement_timestamp": measurement_timestamp,
                            "arrival_timestamp": arrival_timestamp,
                            "frame_id": "ned",
                            "measurement": [
                                1_000.0 + 10.0 * target_index,
                                0.1,
                                -0.05,
                                3.0,
                            ],
                            "covariance": [
                                [16.0, 0.0, 0.0, 0.0],
                                [0.0, 0.01, 0.0, 0.0],
                                [0.0, 0.0, 0.01, 0.0],
                                [0.0, 0.0, 0.0, 4.0],
                            ],
                            "confidence": 0.95,
                            "metadata": {
                                "scan_id": batch_id,
                                "source_lineage_key": [
                                    "explicit",
                                    "RADAR-BENCHMARK",
                                    batch_id,
                                    target_index,
                                ],
                                "sensor_position_ned": [0.0, 0.0, 0.0],
                            },
                        }
                        for target_index in range(4)
                    ],
                },
            }
        )
    path.write_text(
        "".join(
            json.dumps(record, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def test_scan_input_performance_benchmark_is_strict_and_reproducible(
    tmp_path: Path,
) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_input(source)

    report = benchmark_scan_input_implementations(
        source,
        repeat_count=2,
    )

    assert report["schema_version"] == "d1.scan_input.performance_benchmark.v1"
    assert report["passed"] is True
    assert all(report["acceptance"].values())
    assert report["input"]["benchmark_frame_count"] == 6
    assert report["input"]["benchmark_observation_count"] == 24
    assert report["reference"]["claim_registry_sha256"] == (
        report["candidate"]["claim_registry_sha256"]
    )
    assert report["reference"]["result_stream_sha256"] == (
        report["candidate"]["result_stream_sha256"]
    )
    reference_operations = report["reference"]["performance_diagnostics"]
    candidate_operations = report["candidate"]["performance_diagnostics"]
    assert reference_operations["source_lineage_reconstruction_count"] == 24
    assert candidate_operations["source_lineage_reconstruction_count"] == 0
    assert candidate_operations["cached_source_lineage_reuse_count"] == 24
    assert (
        reference_operations["lineage_sort_key_construction_count"]
        == 2 * candidate_operations["lineage_sort_key_construction_count"]
    )
    assert (
        report["interleaved_wall_time"]["wall_time_used_for_acceptance"]
        is False
    )
    assert report["evidence_boundary"]["system_realtime_gap_closed"] is False

    json_path = tmp_path / "scan_input.json"
    markdown_path = tmp_path / "scan_input.md"
    write_scan_input_performance_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    serialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert serialized["passed"] is True
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "main 正式 13-pair 矩阵尚未运行" in markdown
