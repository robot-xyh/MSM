from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from d1_sensor_fusion import (
    PUBLICATION_AUDIT_TREE_CONTRACT_VERSION,
    FusionAdapter,
    SensorObservation,
    validate_immutable_publication_audit_tree,
)
from d1_sensor_fusion.observations import (
    radar_covariance_from_range,
    radar_h,
)
from d1_sensor_fusion.publication_metadata_performance import (
    analyze_frozen_publication_metadata,
    write_publication_metadata_report,
)


def _radar_observation(
    observation_id: str,
    position: tuple[float, float, float],
    *,
    scan_id: str = "publication-scan-001",
) -> SensorObservation:
    state = np.asarray((*position, 0.0, 0.0, 0.0), dtype=float)
    measurement = radar_h(state, np.zeros(3))
    return SensorObservation(
        observation_id=observation_id,
        sensor_id="RADAR-PUBLICATION",
        modality="radar",
        measurement_timestamp=1.0,
        arrival_timestamp=1.1,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(float(measurement[0])),
        confidence=0.95,
        metadata={
            "sensor_position_ned": np.zeros(3),
            "scan_id": scan_id,
            "source_lineage_key": (
                "explicit",
                "RADAR-PUBLICATION",
                scan_id,
                observation_id,
            ),
        },
    )


def _materialize_two_tracks(
    *,
    immutable_shared_publication_metadata: bool,
) -> tuple[FusionAdapter, tuple]:
    adapter = FusionAdapter(
        immutable_shared_publication_metadata=(
            immutable_shared_publication_metadata
        )
    )
    result = adapter.process_scan_batch(
        (
            _radar_observation("publication-radar-001", (100.0, 0.0, -20.0)),
            _radar_observation("publication-radar-002", (900.0, 0.0, -20.0)),
        )
    )
    assert len(result.tracks) == 2
    return adapter, tuple(
        sorted(result.tracks, key=lambda item: item.global_track_id)
    )


def test_candidate_shares_only_recursively_immutable_publication_audits() -> None:
    adapter, tracks = _materialize_two_tracks(
        immutable_shared_publication_metadata=True,
    )
    first, second = tracks

    assert first.metadata is not second.metadata
    for key in ("association_audit", "latency_audit", "sensor_health"):
        assert first.metadata[key] is second.metadata[key]

    first.metadata["local_probe"] = "first-only"
    first.metadata["association_diagnostics"]["local_probe"] = 1
    assert "local_probe" not in second.metadata
    assert "local_probe" not in second.metadata["association_diagnostics"]

    with pytest.raises(TypeError, match="immutable"):
        first.metadata["association_audit"]["cross_track_pollution"] = True
    with pytest.raises(TypeError, match="immutable"):
        first.metadata["sensor_health"]["RADAR-PUBLICATION"]["reject_count"] = 99

    assert "cross_track_pollution" not in second.metadata["association_audit"]
    assert (
        second.metadata["sensor_health"]["RADAR-PUBLICATION"]["reject_count"]
        != 99
    )
    json.dumps(first.to_dict(), sort_keys=True)
    copied_metadata = copy.deepcopy(first.metadata)
    assert copied_metadata == first.metadata
    assert (
        copied_metadata["association_audit"]
        is first.metadata["association_audit"]
    )

    diagnostics = adapter.publication_materialization_diagnostics()
    counts = diagnostics["operation_counts"]
    assert diagnostics["implementation_id"].endswith(
        "immutable_shared_audit.v2"
    )
    assert (
        diagnostics["publication_audit_contract_version"]
        == PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
    )
    for key in ("association_audit", "latency_audit", "sensor_health"):
        assert (
            validate_immutable_publication_audit_tree(first.metadata[key])
            .contract_version
            == PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
        )
    assert counts["global_track_metadata_materialization_count"] == 2
    assert counts["shared_audit_value_reuse_count"] == 6
    assert counts["immutable_shared_mapping_build_count"] > 0
    assert counts.get("per_track_shared_audit_mapping_copy_count", 0) == 0


def test_reference_and_candidate_publish_identical_complete_track_payloads() -> None:
    reference, reference_tracks = _materialize_two_tracks(
        immutable_shared_publication_metadata=False,
    )
    candidate, candidate_tracks = _materialize_two_tracks(
        immutable_shared_publication_metadata=True,
    )

    reference_payload = json.dumps(
        [item.to_dict() for item in reference_tracks],
        sort_keys=True,
    )
    candidate_payload = json.dumps(
        [item.to_dict() for item in candidate_tracks],
        sort_keys=True,
    )
    assert candidate_payload == reference_payload
    assert (
        reference_tracks[0].metadata["association_audit"]
        is not reference_tracks[1].metadata["association_audit"]
    )

    reference_counts = reference.publication_materialization_diagnostics()[
        "operation_counts"
    ]
    assert (
        reference.publication_materialization_diagnostics()[
            "publication_audit_contract_version"
        ]
        is None
    )
    candidate_counts = candidate.publication_materialization_diagnostics()[
        "operation_counts"
    ]
    assert reference_counts[
        "per_track_shared_audit_mapping_copy_count"
    ] > 0
    assert candidate_counts.get(
        "per_track_shared_audit_mapping_copy_count",
        0,
    ) == 0


def test_candidate_configuration_rejects_unsafe_or_implicit_modes() -> None:
    with pytest.raises(TypeError, match="must be a bool"):
        FusionAdapter(immutable_shared_publication_metadata=1)
    with pytest.raises(ValueError, match="requires"):
        FusionAdapter(
            shared_publication_audit_snapshot=False,
            immutable_shared_publication_metadata=True,
        )


def _write_frozen_input(path: Path) -> None:
    records = []
    for index in range(4):
        measurement_timestamp = float(index)
        arrival_timestamp = measurement_timestamp + 0.1
        state = np.asarray(
            [100.0 + 5.0 * index, 10.0, -20.0, 5.0, 0.0, 0.0],
            dtype=float,
        )
        measurement = radar_h(state, np.zeros(3))
        covariance = radar_covariance_from_range(float(measurement[0]))
        observation_id = f"publication-replay-{index:03d}"
        scan_id = f"publication-replay-scan-{index:03d}"
        records.append(
            {
                "sequence": index + 1,
                "topic": "sensor.observations",
                "source": "RADAR-PUBLICATION",
                "timestamp": arrival_timestamp,
                "schema_version": "scalable3d-observation-v1",
                "payload": {
                    "batch_id": scan_id,
                    "sensor_id": "RADAR-PUBLICATION",
                    "measurement_timestamp": measurement_timestamp,
                    "arrival_timestamp": arrival_timestamp,
                    "measurements": [
                        {
                            "observation_id": observation_id,
                            "sensor_id": "RADAR-PUBLICATION",
                            "modality": "radar",
                            "measurement_timestamp": measurement_timestamp,
                            "arrival_timestamp": arrival_timestamp,
                            "frame_id": "ned",
                            "measurement": measurement.tolist(),
                            "covariance": covariance.tolist(),
                            "confidence": 0.95,
                            "metadata": {
                                "sensor_position_ned": [0.0, 0.0, 0.0],
                                "scan_id": scan_id,
                                "source_lineage_key": [
                                    "explicit",
                                    "RADAR-PUBLICATION",
                                    scan_id,
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


def test_frozen_replay_benchmark_records_strict_equivalence_and_counts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_input(source)
    report = analyze_frozen_publication_metadata(
        source,
        repeat_count=2,
        profile_directory=tmp_path / "profiles",
    )

    comparison = report["comparison"]
    assert comparison["passed"] is True
    assert all(comparison["acceptance"].values())
    assert comparison["acceptance"][
        "per_publication_complete_global_track_equivalence"
    ]
    assert comparison["acceptance"][
        "candidate_per_track_copy_eliminated"
    ]
    assert comparison["timing"]["wall_time_used_for_acceptance"] is False
    assert report["constraints"]["candidate_promoted_to_default"] is False
    assert report["constraints"]["online_truth_use_count"] == 0
    assert (
        comparison["reference"]["publication_materialization_diagnostics"][
            "implementation_id"
        ]
        != comparison["candidate"]["publication_materialization_diagnostics"][
            "implementation_id"
        ]
    )

    json_path = tmp_path / "publication.json"
    markdown_path = tmp_path / "publication.md"
    write_publication_metadata_report(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    serialized = json.loads(json_path.read_text(encoding="utf-8"))
    assert (
        serialized["schema_version"]
        == "d1.publication_metadata_performance.v1"
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "candidate 默认关闭" in markdown
    assert "不是正式多 seed 放行" in markdown
