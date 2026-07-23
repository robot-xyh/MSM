from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from d1_sensor_fusion import SensorObservation
from d1_sensor_fusion.observations import radar_covariance_from_range, radar_h
from d1_sensor_fusion.tail_latency_performance import (
    analyze_frozen_tail_latency,
    write_tail_latency_report,
)


def _write_frozen_input(path: Path) -> None:
    records = []
    for index in range(6):
        measurement_timestamp = float(index // 2)
        arrival_timestamp = measurement_timestamp + 0.1
        state = np.array(
            [800.0 + 4.0 * measurement_timestamp, -200.0, -100.0, 4.0, 0.0, 0.0],
            dtype=float,
        )
        measurement = radar_h(state, np.zeros(3))
        observation = SensorObservation(
            observation_id=f"tail-radar-{index}",
            sensor_id=f"RADAR-{index % 2}",
            modality="radar",
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
            frame_id="ned",
            measurement=measurement,
            covariance=radar_covariance_from_range(float(measurement[0])),
            confidence=0.95,
            metadata={
                "sensor_position_ned": np.zeros(3),
                "scan_id": f"tail-scan-{index}",
                "source_lineage_key": (
                    "explicit",
                    f"RADAR-{index % 2}",
                    f"tail-scan-{index}",
                    0,
                ),
            },
        )
        records.append(
            {
                "sequence": index + 1,
                "topic": "sensor.observations",
                "source": observation.sensor_id,
                "timestamp": arrival_timestamp,
                "schema_version": "scalable3d-observation-v1",
                "payload": {
                    "batch_id": f"tail-scan-{index}",
                    "sensor_id": observation.sensor_id,
                    "measurement_timestamp": measurement_timestamp,
                    "arrival_timestamp": arrival_timestamp,
                    "measurements": [
                        {
                            "observation_id": observation.observation_id,
                            "sensor_id": observation.sensor_id,
                            "modality": observation.modality,
                            "measurement_timestamp": measurement_timestamp,
                            "arrival_timestamp": arrival_timestamp,
                            "frame_id": observation.frame_id,
                            "measurement": observation.measurement.tolist(),
                            "covariance": observation.covariance.tolist(),
                            "confidence": observation.confidence,
                            "metadata": {
                                "sensor_position_ned": [0.0, 0.0, 0.0],
                                "scan_id": f"tail-scan-{index}",
                                "source_lineage_key": [
                                    "explicit",
                                    observation.sensor_id,
                                    f"tail-scan-{index}",
                                    0,
                                ],
                            },
                        }
                    ],
                },
            }
        )
    path.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
        encoding="utf-8",
    )


def test_tail_latency_replay_preserves_strict_per_scan_semantics(
    tmp_path: Path,
) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_input(source)

    report = analyze_frozen_tail_latency(
        source,
        scan_input_repeat_count=2,
        scan_input_benchmark_scan_count=4,
        profile_directory=tmp_path / "profiles",
    )

    comparison = report["scan_input_comparison"]
    assert comparison["passed"] is True
    assert all(comparison["acceptance"].values())
    assert comparison["acceptance"][
        "per_fusion_state_covariance_timestamp_lineage_level_equivalence"
    ]
    assert comparison["acceptance"]["per_fusion_operation_counts_equivalence"]
    assert comparison["acceptance"][
        "per_fusion_cumulative_diagnostics_equivalence"
    ]
    assert comparison["reference"]["fusion_operation_snapshots_sha256"] == (
        comparison["optimized"]["fusion_operation_snapshots_sha256"]
    )
    assert comparison["reference"]["fusion_diagnostic_snapshots_sha256"] == (
        comparison["optimized"]["fusion_diagnostic_snapshots_sha256"]
    )
    assert comparison["reference"]["scan_input_performance_diagnostics"][
        "organizer_observation_snapshot_count"
    ] == 6
    assert comparison["optimized"]["scan_input_performance_diagnostics"][
        "organizer_observation_snapshot_count"
    ] == 0
    assert comparison["interleaved_distribution"]["wall_time_used_for_acceptance"] is False
    claim_comparison = report["claim_serialization_comparison"]
    assert claim_comparison["passed"] is True
    assert all(claim_comparison["acceptance"].values())
    assert claim_comparison["acceptance"]["claim_registry_digest_equivalence"]
    assert claim_comparison["acceptance"][
        "per_fusion_state_covariance_timestamp_lineage_level_equivalence"
    ]
    assert claim_comparison["acceptance"][
        "per_fusion_operation_counts_equivalence"
    ]
    assert claim_comparison["acceptance"][
        "per_fusion_cumulative_diagnostics_equivalence"
    ]
    assert (
        claim_comparison["reference"]["scan_claims_sha256"]
        == claim_comparison["optimized"]["scan_claims_sha256"]
    )
    assert (
        claim_comparison["interleaved_distribution"][
            "wall_time_used_for_acceptance"
        ]
        is False
    )
    assert report["constraints"]["online_truth_use_count"] == 0
    assert report["constraints"]["claim_digest_format_changed"] is False
    assert (
        report["constraints"]["claim_registry_or_rejection_policy_changed"]
        is False
    )
    assert report["fusion_tail_attribution"]["profile_selected_functions"][
        "process_scan_batch"
    ]["primitive_call_count"] == 6

    json_path = tmp_path / "tail.json"
    markdown_path = tmp_path / "tail.md"
    write_tail_latency_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    serialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert serialized["schema_version"] == "d1.tail_latency_performance.v1"
    assert "不是 AirSim" in markdown_path.read_text(encoding="utf-8")
