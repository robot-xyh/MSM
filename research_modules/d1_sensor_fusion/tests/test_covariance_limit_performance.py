from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from d1_sensor_fusion import (
    FusionAdapter,
    Scalable3DFusionAdapter,
    SensorObservation,
    compare_covariance_limit_semantics_once,
    compare_covariance_limit_variants,
)
from d1_sensor_fusion.fusion import (
    _limit_covariance_diagonal,
)
from d1_sensor_fusion.long_duration_performance import (
    _coalesced_scan_semantic_digest,
)
from d1_sensor_fusion.observations import (
    radar_covariance_from_range,
    radar_h,
)


def _radar_observation(
    *,
    index: int,
    measurement_timestamp: float,
    arrival_timestamp: float,
) -> SensorObservation:
    state = np.array(
        [
            700.0 + 5.0 * measurement_timestamp,
            -120.0,
            -80.0,
            5.0,
            0.0,
            0.0,
        ],
        dtype=float,
    )
    measurement = radar_h(state, np.zeros(3))
    return SensorObservation(
        observation_id=f"covariance-limit-radar-{index}",
        sensor_id="RADAR-COVARIANCE-LIMIT",
        modality="radar",
        measurement_timestamp=measurement_timestamp,
        arrival_timestamp=arrival_timestamp,
        frame_id="ned",
        measurement=measurement,
        covariance=radar_covariance_from_range(float(measurement[0])),
        classification_hint="unknown_aircraft",
        confidence=0.95,
        metadata={
            "sensor_position_ned": np.zeros(3),
            "scan_id": f"covariance-limit-scan-{index}",
            "sequence_id": index,
            "source_node_id": "center-radar",
        },
    )


def _write_frozen_input(
    path: Path,
    *,
    timestamps: tuple[tuple[float, float], ...] = (
        (0.0, 0.10),
        (0.2, 0.30),
        (0.1, 0.40),
        (0.4, 0.50),
        (0.6, 0.70),
        (0.8, 0.90),
    ),
) -> None:
    records = []
    for index, (measurement_timestamp, arrival_timestamp) in enumerate(
        timestamps,
        start=1,
    ):
        observation = _radar_observation(
            index=index,
            measurement_timestamp=measurement_timestamp,
            arrival_timestamp=arrival_timestamp,
        )
        records.append(
            {
                "sequence": index,
                "topic": "sensor.observations",
                "source": observation.sensor_id,
                "timestamp": observation.arrival_timestamp,
                "schema_version": "scalable3d-observation-v1",
                "payload": {
                    "batch_id": observation.metadata["scan_id"],
                    "sensor_id": observation.sensor_id,
                    "measurement_timestamp": observation.measurement_timestamp,
                    "arrival_timestamp": observation.arrival_timestamp,
                    "measurements": [
                        {
                            "observation_id": observation.observation_id,
                            "sensor_id": observation.sensor_id,
                            "modality": observation.modality,
                            "measurement_timestamp": (
                                observation.measurement_timestamp
                            ),
                            "arrival_timestamp": observation.arrival_timestamp,
                            "frame_id": observation.frame_id,
                            "measurement": observation.measurement.tolist(),
                            "covariance": observation.covariance.tolist(),
                            "classification_hint": (
                                observation.classification_hint
                            ),
                            "confidence": observation.confidence,
                            "metadata": {
                                "sensor_position_ned": [0.0, 0.0, 0.0],
                                "scan_id": observation.metadata["scan_id"],
                                "sequence_id": index,
                                "source_node_id": "center-radar",
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


def test_vectorized_pairwise_limit_is_bitwise_equivalent() -> None:
    generator = np.random.default_rng(20260724)
    for dimension in (1, 2, 3, 4, 6):
        for _ in range(64):
            covariance = generator.normal(size=(dimension, dimension))
            floor = np.linspace(0.1, 0.2, dimension)
            ceiling = np.linspace(5.0, 8.0, dimension)
            covariance[0, 0] = floor[0] * generator.uniform(-2.0, 0.5)
            covariance[-1, -1] = ceiling[-1] * generator.uniform(1.5, 5.0)
            if dimension > 1:
                covariance[0, -1] = generator.choice((-1.0, 1.0)) * 1.0e12
                covariance[-1, 0] = generator.choice((-1.0, 1.0)) * 2.0e11

            reference = _limit_covariance_diagonal(
                covariance,
                floor,
                ceiling,
                floor_reason="floor",
                ceiling_reason="ceiling",
                vectorized_off_diagonal=False,
            )
            optimized = _limit_covariance_diagonal(
                covariance,
                floor,
                ceiling,
                floor_reason="floor",
                ceiling_reason="ceiling",
                vectorized_off_diagonal=True,
            )

            assert reference[1] == optimized[1]
            assert "ceiling" in optimized[1]
            if dimension > 1:
                assert "floor" in optimized[1]
            assert np.array_equal(reference[0], optimized[0])
            assert np.array_equal(reference[0], reference[0].T)
            assert np.all(np.diag(reference[0]) >= floor)
            assert np.all(np.diag(reference[0]) <= ceiling)


@pytest.mark.parametrize(
    "covariance",
    [
        np.diag([-5.0, 0.0, 1.0, 2.0, 3.0, 4.0]),
        np.array(
            [
                [1.0, 1.0e15, 0.0, 0.0, 0.0, 0.0],
                [-1.0e14, 2.0, 3.0, 0.0, 0.0, 0.0],
                [0.0, -4.0, 3.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 4.0, -1.0e12, 0.0],
                [0.0, 0.0, 0.0, 2.0e12, 5.0, 1.0],
                [0.0, 0.0, 0.0, 0.0, -2.0, 6.0],
            ],
            dtype=float,
        ),
        np.diag([1.0e-30, 1.0e30, 0.0, -1.0, 2.0, 3.0]),
    ],
)
def test_vectorized_pairwise_limit_preserves_boundary_reason_semantics(
    covariance: np.ndarray,
) -> None:
    floor = np.full(6, 0.25, dtype=float)
    ceiling = np.full(6, 100.0, dtype=float)

    reference = _limit_covariance_diagonal(
        covariance,
        floor,
        ceiling,
        floor_reason="floor",
        ceiling_reason="ceiling",
        vectorized_off_diagonal=False,
    )
    optimized = _limit_covariance_diagonal(
        covariance,
        floor,
        ceiling,
        floor_reason="floor",
        ceiling_reason="ceiling",
        vectorized_off_diagonal=True,
    )

    assert optimized[1] == reference[1]
    assert np.array_equal(optimized[0], reference[0])


@pytest.mark.parametrize(
    "covariance",
    [
        np.diag([np.nan, 1.0, 1.0, 1.0, 1.0, 1.0]),
        np.diag([np.inf, 1.0, 1.0, 1.0, 1.0, 1.0]),
        np.diag([-1.0, 0.0, 1.0, 1.0, 1.0, 1.0]),
        np.array(
            [
                [4.0, 2.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 3.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 2.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        np.array(
            [
                [1.0, 2.0, 0.0, 0.0, 0.0, 0.0],
                [2.0, 1.0, 0.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        np.diag([0.25, 1.0e6, 0.25, 0.04, 1.0e4, 0.04]),
    ],
)
def test_state_covariance_negative_and_boundary_paths_are_equivalent(
    covariance: np.ndarray,
) -> None:
    reference = FusionAdapter(vectorized_covariance_limit=False)
    optimized = FusionAdapter(vectorized_covariance_limit=True)

    reference_covariance, reference_reasons = reference._limit_state_covariance(
        covariance
    )
    optimized_covariance, optimized_reasons = optimized._limit_state_covariance(
        covariance
    )

    assert reference_reasons == optimized_reasons
    assert np.array_equal(reference_covariance, optimized_covariance)
    assert np.isfinite(optimized_covariance).all()
    assert np.array_equal(optimized_covariance, optimized_covariance.T)
    assert np.all(np.diag(optimized_covariance) >= optimized.covariance_floor_diag)
    assert np.all(
        np.diag(optimized_covariance) <= optimized.covariance_ceiling_diag
    )
    assert float(np.linalg.eigvalsh(optimized_covariance)[0]) >= -1.0e-12


@pytest.mark.parametrize(
    ("covariance", "message"),
    [
        (np.diag([1.0, 1.0, 1.0, np.inf]), "finite"),
        (
            np.array(
                [
                    [1.0, 0.5, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            ),
            "symmetric",
        ),
        (np.diag([1.0, 1.0, 1.0, -1.0]), "positive semidefinite"),
    ],
)
def test_online_covariance_contract_rejects_invalid_inputs_in_both_modes(
    covariance: np.ndarray,
    message: str,
) -> None:
    for vectorized in (False, True):
        observation = SensorObservation(
            observation_id=f"invalid-{message}-{vectorized}",
            sensor_id="RADAR-COVARIANCE-LIMIT",
            modality="radar",
            measurement_timestamp=1.0,
            arrival_timestamp=1.1,
            frame_id="ned",
            measurement=np.array([100.0, 0.0, 0.0, 0.0]),
            covariance=covariance,
        )
        with pytest.raises(ValueError, match=message):
            FusionAdapter(
                vectorized_covariance_limit=vectorized
            ).process_scan_batch((observation,))


def test_covariance_limit_mode_requires_boolean() -> None:
    with pytest.raises(TypeError, match="vectorized_covariance_limit"):
        FusionAdapter(vectorized_covariance_limit="true")  # type: ignore[arg-type]


def test_scalable_adapter_exposes_reference_and_optimized_switch() -> None:
    reference = Scalable3DFusionAdapter(vectorized_covariance_limit=False)
    optimized = Scalable3DFusionAdapter(vectorized_covariance_limit=True)

    assert reference.vectorized_covariance_limit is False
    assert optimized.vectorized_covariance_limit is True


def test_reference_and_optimized_replays_preserve_every_scan_contract() -> None:
    reference = FusionAdapter(vectorized_covariance_limit=False)
    optimized = FusionAdapter(vectorized_covariance_limit=True)
    assert reference.buffer_horizon == optimized.buffer_horizon == 6.0
    observations = (
        _radar_observation(
            index=1,
            measurement_timestamp=0.0,
            arrival_timestamp=0.1,
        ),
        _radar_observation(
            index=2,
            measurement_timestamp=0.2,
            arrival_timestamp=0.3,
        ),
        _radar_observation(
            index=3,
            measurement_timestamp=0.1,
            arrival_timestamp=0.4,
        ),
        _radar_observation(
            index=4,
            measurement_timestamp=0.6,
            arrival_timestamp=0.7,
        ),
    )

    for index, observation in enumerate(observations):
        materialize = index != 1
        reference_result = reference.process_scan_batch(
            (observation,),
            materialize_tracks=materialize,
        )
        optimized_result = optimized.process_scan_batch(
            (observation,),
            materialize_tracks=materialize,
        )

        assert reference_result.summary.to_dict() == optimized_result.summary.to_dict()
        assert _coalesced_scan_semantic_digest(
            reference,
            reference_result,
        ) == _coalesced_scan_semantic_digest(
            optimized,
            optimized_result,
        )
        assert (
            reference.fusion_performance_diagnostics().to_dict()
            == optimized.fusion_performance_diagnostics().to_dict()
        )

    reference_tracks = reference.materialize_global_tracks()
    optimized_tracks = optimized.materialize_global_tracks()
    assert [item.to_dict() for item in reference_tracks.tracks] == [
        item.to_dict() for item in optimized_tracks.tracks
    ]
    reference_evidence = reference.consistency_evidence_records()
    optimized_evidence = optimized.consistency_evidence_records()
    assert [item.to_dict() for item in reference_evidence] == [
        item.to_dict() for item in optimized_evidence
    ]
    observations_by_id = {
        item.observation_id: item for item in observations
    }
    for evidence in optimized_evidence:
        source = observations_by_id[evidence.observation_id]
        assert evidence.measurement_timestamp == source.measurement_timestamp
        assert evidence.arrival_timestamp == source.arrival_timestamp
        assert evidence.source_lineage[0] == "opaque_online_lineage"
        assert evidence.source_lineage[1] == f"sensor:{source.sensor_id}"
        assert len(evidence.source_lineage) == 3
    final_track = optimized_tracks.tracks[0]
    assert final_track.metadata["measurement_timestamp"] == pytest.approx(0.6)
    assert final_track.metadata["arrival_timestamp"] == pytest.approx(0.7)
    assert final_track.metadata["source_support"]["radar"] == 4
    assert final_track.identity_likelihood["unknown_aircraft"] == pytest.approx(1.0)


def test_interleaved_frozen_benchmark_reports_semantics_and_profiles(
    tmp_path: Path,
) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_input(source)

    report = compare_covariance_limit_variants(
        source,
        repeat_count=5,
        profile_directory=tmp_path / "profiles",
    )

    assert report["comparison"]["semantic_passed"] is True
    assert all(report["comparison"]["semantic_acceptance"].values())
    assert report["benchmark"]["reference"]["sample_count"] == 5
    assert report["benchmark"]["optimized"]["sample_count"] == 5
    assert report["input"]["online_truth_use_count"] == 0
    reference_profile = report["reference"]["profile"]["selected_functions"]
    optimized_profile = report["optimized"]["profile"]["selected_functions"]
    assert (
        reference_profile[
            "_clip_covariance_off_diagonal_reference"
        ]["primitive_call_count"]
        > 0
    )
    assert (
        optimized_profile[
            "_clip_covariance_off_diagonal_vectorized"
        ]["primitive_call_count"]
        > 0
    )


def test_long_fixture_runs_one_semantic_pair_and_exercises_rebase(
    tmp_path: Path,
) -> None:
    source = tmp_path / "online_observations.jsonl"
    _write_frozen_input(
        source,
        timestamps=tuple(
            (
                0.3 if index == 3 else 0.2 * index,
                0.2 * index + 0.1,
            )
            for index in range(33)
        ),
    )

    with pytest.raises(ValueError, match="no longer than 6 seconds"):
        compare_covariance_limit_variants(source, repeat_count=5)

    report = compare_covariance_limit_semantics_once(source)

    assert report["comparison"]["passed"] is True
    assert all(report["comparison"]["semantic_acceptance"].values())
    assert all(report["comparison"]["scenario_acceptance"].values())
    assert report["execution_policy"] == {
        "warmup_count": 0,
        "repeat_count": 1,
        "profiled": False,
        "timing_acceptance": False,
    }
    assert report["reference"]["cumulative_diagnostics"][
        "fixed_lag_rebase_count"
    ] > 0
    assert report["reference"]["latency_audit"]["oosm_observation_count"] > 0
