from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping as TypingMapping

import numpy as np
import pytest

from d2_data_association.scalable_3d_long_duration import (
    run_scalable_3d_long_duration_metadata_benchmark,
)
from d2_data_association.scalable_3d_models import (
    _forbidden_online_key,
    _normalized_key,
    assert_online_metadata_truth_free,
    assert_online_metadata_batch_truth_free,
    detections3d_from_d1_global_tracks,
)
from d2_data_association.scalable_3d_performance import (
    compare_scalable_3d_d2_performance,
)


def _legacy_forbidden_online_key(key: str) -> bool:
    collapsed = key.replace("_", "")
    if (
        key == "truth"
        or key.startswith("truth_")
        or key.endswith("_truth_id")
        or "ground_truth" in key
        or "offline_truth" in key
        or "sim_truth" in key
        or "truthid" in collapsed
        or "groundtruth" in collapsed
    ):
        return True
    if key in {
        "airsim_id",
        "actor_id",
        "actor_name",
        "object_id",
        "object_name",
        "entity_id",
        "entity_ids",
        "target_id",
        "target_ids",
        "global_track_id",
        "canonical_id",
    }:
        return True
    if "globaltrackid" in collapsed or "canonicaltrackid" in collapsed:
        return True
    identity_suffixes = ("id", "ids", "identity", "name", "uuid")
    return any(
        collapsed.startswith(domain) and collapsed.endswith(identity_suffixes)
        for domain in ("actor", "object", "entity", "target", "airsim")
    )


def _legacy_assert_online_metadata_truth_free(
    metadata: TypingMapping[str, Any],
) -> None:
    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, TypingMapping):
            for raw_key, item in value.items():
                key = str(raw_key).strip().lower().replace("-", "_").replace(" ", "_")
                child_path = f"{path}.{raw_key}"
                if _legacy_forbidden_online_key(key):
                    violations.append(child_path)
                else:
                    visit(item, child_path)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(metadata, "metadata")
    if violations:
        raise ValueError(
            "online Detection3D metadata contains evaluator or external identity: "
            + ", ".join(sorted(set(violations)))
        )


@pytest.mark.parametrize(
    "key",
    [
        "truth_id",
        "TruthId",
        "ground-truth-name",
        "actor_uuid",
        "object identity",
        "entityIds",
        "targetName",
        "airsimObjectId",
        "globalTrackId",
        "canonical_track_id",
        "latest_observation_id",
        "source_track_id",
        "sensor_health",
        "association_diagnostics",
        "measurement_timestamp",
        "arrival_timestamp",
    ],
)
def test_optimized_identity_key_classifier_matches_legacy(key: str) -> None:
    normalized = _normalized_key(key)
    assert _forbidden_online_key(normalized) is _legacy_forbidden_online_key(
        normalized
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {
            "sensor_health": {
                "radar": {
                    "latency": [0.1, 0.2],
                    "audit": {"measurement_timestamp": 1.0},
                }
            }
        },
        {"nested": [{"deeper": ({"actorName": "forbidden"},)}]},
        {"nested": {"truth-id": "forbidden", "truth_id": "duplicate"}},
    ],
)
def test_optimized_recursive_identity_audit_matches_legacy(
    metadata: dict[str, Any],
) -> None:
    def outcome(function: Any) -> tuple[type[Exception] | None, str | None]:
        try:
            function(metadata)
        except Exception as exc:  # noqa: BLE001 - comparing exact contracts
            return type(exc), str(exc)
        return None, None

    assert outcome(assert_online_metadata_truth_free) == outcome(
        _legacy_assert_online_metadata_truth_free
    )


def test_batch_audit_reuses_equal_diagnostics_and_rejects_changed_truth() -> None:
    shared_health = {
        "CAM-0001": {
            "measurement_count": 4,
            "quality_flags": ["nominal"],
        }
    }
    metadata = [
        {
            "latest_observation_id": f"obs-{index}",
            "sensor_health": json.loads(json.dumps(shared_health)),
        }
        for index in range(4)
    ]

    summary = assert_online_metadata_batch_truth_free(metadata)

    assert summary.metadata_count == 4
    assert summary.shared_subtree_full_audit_count == 1
    assert summary.shared_subtree_equivalent_reuse_count == 3

    metadata[-1]["sensor_health"]["CAM-0001"]["truth_id"] = "forbidden"
    with pytest.raises(ValueError, match="metadata.sensor_health.CAM-0001.truth_id"):
        assert_online_metadata_batch_truth_free(metadata)


def test_batch_audit_does_not_trust_custom_mapping_equality() -> None:
    class AlwaysEqualMapping(dict[str, Any]):
        def __eq__(self, other: object) -> bool:
            return True

    metadata = [
        {"sensor_health": AlwaysEqualMapping({"quality": "nominal"})},
        {"sensor_health": AlwaysEqualMapping({"truth_id": "forbidden"})},
    ]

    with pytest.raises(ValueError, match="metadata.sensor_health.truth_id"):
        assert_online_metadata_batch_truth_free(metadata)


def test_d1_adapter_projects_audited_diagnostics_to_d2_contract() -> None:
    metadata = {
        "frame_id": "NED",
        "latest_measurement_timestamp": 1.0,
        "latest_arrival_timestamp": 1.1,
        "latest_observation_id": "radar-observation-1",
        "latest_sensor_id": "RADAR-CENTER-001",
        "published_at": 1.2,
        "sensor_health": {
            "CAM-0001": {"measurement_count": 100, "quality": "nominal"}
        },
    }
    source = SimpleNamespace(
        global_track_id="UPSTREAM-MUST-BE-IGNORED",
        state=np.asarray([10.0, 20.0, -30.0, 2.0, 0.0, 0.0]),
        covariance=np.eye(6),
        timestamp=1.2,
        metadata=metadata,
    )

    timestamp, detections = detections3d_from_d1_global_tracks([source])

    assert timestamp == pytest.approx(1.2)
    assert detections[0].metadata["latest_observation_id"] == (
        "radar-observation-1"
    )
    assert detections[0].metadata["source_measurement_timestamp"] == pytest.approx(
        1.0
    )
    assert "sensor_health" not in detections[0].metadata
    assert "UPSTREAM-MUST-BE-IGNORED" not in str(detections[0].to_dict())


def test_long_duration_metadata_benchmark_preserves_semantics() -> None:
    report = run_scalable_3d_long_duration_metadata_benchmark(
        track_count=8,
        cycle_count=6,
        sensor_count_start=2,
        sensor_count_end=7,
    )

    assert report.cycle_semantic_hashes_equal is True
    assert report.final_track_hash_equal is True
    assert report.final_claim_hash_equal is True
    assert report.all_online_truth_free is True
    assert len(report.cycle_records) == 6
    assert report.cycle_records[-1]["track_count"] == 8
    assert report.cycle_records[-1]["claim_count"] == 48


def test_episode_comparison_hashes_d2_semantics_and_separates_timing(
    tmp_path: Path,
) -> None:
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    baseline_episode = baseline_root / "nominal" / "200v200" / "seed_42"
    candidate_episode = candidate_root / "nominal" / "200v200" / "seed_42"
    record = _d2_record()
    _write_episode(baseline_episode, record, association_seconds=8.0, finalize_seconds=2.0)
    _write_episode(candidate_episode, record, association_seconds=2.0, finalize_seconds=0.5)

    report = compare_scalable_3d_d2_performance(baseline_root, candidate_root)

    assert report["seed_count"] == 1
    assert report["all_semantics_equal"] is True
    assert report["all_online_truth_free"] is True
    assert report["aggregate_timing"]["association_speedup"] == pytest.approx(4.0)
    assert report["aggregate_timing"]["finalize_speedup"] == pytest.approx(4.0)
    episode = report["episodes"][0]
    assert episode["cycle_hashes_equal"] is True
    assert all(episode["domain_equality"].values())


def test_episode_comparison_detects_claim_semantic_change(tmp_path: Path) -> None:
    baseline_root = tmp_path / "baseline"
    candidate_root = tmp_path / "candidate"
    baseline_episode = baseline_root / "nominal" / "200v200" / "seed_42"
    candidate_episode = candidate_root / "nominal" / "200v200" / "seed_42"
    baseline_record = _d2_record()
    candidate_record = json.loads(json.dumps(baseline_record))
    candidate_record["payload"]["association"]["observation_evidence_governance"][
        "claim_ledger"
    ]["current_count"] = 2
    _write_episode(baseline_episode, baseline_record, association_seconds=8.0, finalize_seconds=2.0)
    _write_episode(candidate_episode, candidate_record, association_seconds=2.0, finalize_seconds=0.5)

    report = compare_scalable_3d_d2_performance(baseline_root, candidate_root)

    assert report["all_semantics_equal"] is False
    episode = report["episodes"][0]
    assert episode["domain_equality"]["claim_and_audit_sha256"] is False
    assert episode["domain_equality"]["identity_lifecycle_sha256"] is True


def _d2_record() -> dict[str, Any]:
    return {
        "sequence": 10,
        "topic": "modules.d2.associated_tracks",
        "source": "D2",
        "timestamp": 1.0,
        "schema_version": "d2-scalable3d-association-v1",
        "payload": {
            "timestamp": 1.0,
            "track_count": 1,
            "tracks": [
                {
                    "global_track_id": "GT3D-000001",
                    "timestamp": 1.0,
                    "state_ned": [0.0] * 6,
                    "covariance": [[1.0 if i == j else 0.0 for j in range(6)] for i in range(6)],
                    "track_state": "confirmed",
                }
            ],
            "association": {
                "timestamp": 1.0,
                "matched_pairs": [],
                "unmatched_track_ids": [],
                "unmatched_detection_ids": [],
                "observation_evidence_governance": {
                    "claim_ledger": {"current_count": 1},
                    "online_truth_used": False,
                },
            },
            "id_switch_count": None,
            "id_switch_count_available": False,
            "identity_lineage_policy": "d2_center_track_to_d1_source_observation_v1",
            "identity_lineage": [],
        },
    }


def _write_episode(
    episode: Path,
    record: dict[str, Any],
    *,
    association_seconds: float,
    finalize_seconds: float,
) -> None:
    episode.mkdir(parents=True, exist_ok=True)
    (episode / "online_observations.jsonl").write_text(
        json.dumps(record, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (episode / "offline_truth_labels.jsonl").write_text(
        json.dumps({"truth": "offline-only"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (episode / "scenario_config.json").write_text(
        json.dumps({"seed": 42, "resource_count": 200, "target_count": 200}, sort_keys=True),
        encoding="utf-8",
    )
    (episode / "summary.json").write_text(
        json.dumps({"seed": 42, "online_truth_use_count": 0}, sort_keys=True),
        encoding="utf-8",
    )
    with (episode / "stage_timings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("stage", "call_count", "wall_time_s", "mean_wall_time_ms"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "stage": "module.d2_association",
                "call_count": 8,
                "wall_time_s": association_seconds,
                "mean_wall_time_ms": association_seconds * 1000.0 / 8.0,
            }
        )
        writer.writerow(
            {
                "stage": "module.d2_association_finalize",
                "call_count": 1,
                "wall_time_s": finalize_seconds,
                "mean_wall_time_ms": finalize_seconds * 1000.0,
            }
        )
