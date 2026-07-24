from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from d1_sensor_fusion import (
    FusionAdapter,
    GlobalTrack,
    SensorObservation,
    TrackLevel,
)
from d1_sensor_fusion.fusion import (
    COVARIANCE_CORRELATION_LIMIT,
    TRACK_COVARIANCE_CEILING_DIAG,
    TRACK_COVARIANCE_FLOOR_DIAG,
    _clip_covariance_off_diagonal_reference,
    _limit_covariance_diagonal,
)


_SEED_1103_PRE_LIMIT_COVARIANCE = np.array(
    [
        [
            288.63284402468094,
            1087.599461434918,
            -38.06515394136101,
            43.2357911377849,
            163.42951565715722,
            -5.553443238097041,
        ],
        [
            1087.599461434918,
            4099.476248134196,
            -143.47588053782465,
            160.82391476237328,
            616.4781092149342,
            -20.930619588465234,
        ],
        [
            -38.06515394136101,
            -143.47588053782465,
            5.107250581910017,
            -5.629056323480164,
            -21.559352531146924,
            1.2996419070631144,
        ],
        [
            43.2357911377849,
            160.82391476237328,
            -5.629056323480164,
            10.547493293383065,
            25.773151733015034,
            -0.8797257167927247,
        ],
        [
            163.42951565715722,
            616.4781092149342,
            -21.559352531146924,
            25.773151733015034,
            101.82201633624918,
            -3.355664022509692,
        ],
        [
            -5.553443238097041,
            -20.930619588465234,
            1.2996419070631144,
            -0.8797257167927247,
            -3.355664022509692,
            3.9184628729343274,
        ],
    ],
    dtype=float,
)


def _assert_governed_constraints(
    covariance: np.ndarray,
    floor: np.ndarray,
    ceiling: np.ndarray,
) -> None:
    assert np.isfinite(covariance).all()
    assert np.array_equal(covariance, covariance.T)
    diagonal = np.diag(covariance)
    assert np.all(diagonal >= floor)
    assert np.all(diagonal <= ceiling)
    assert float(np.linalg.eigvalsh(covariance)[0]) >= 0.0

    rows, columns = np.triu_indices(covariance.shape[0], k=1)
    if rows.size:
        limits = COVARIANCE_CORRELATION_LIMIT * np.sqrt(
            diagonal[rows] * diagonal[columns]
        )
        assert np.all(np.abs(covariance[rows, columns]) <= limits)


def test_seed_1103_pair_clip_regression_is_repaired_and_audited() -> None:
    assert (
        float(np.linalg.eigvalsh(_SEED_1103_PRE_LIMIT_COVARIANCE)[0])
        > 0.0
    )
    old_pairwise_only = _SEED_1103_PRE_LIMIT_COVARIANCE.copy()
    assert _clip_covariance_off_diagonal_reference(old_pairwise_only) == 1
    assert float(np.linalg.eigvalsh(old_pairwise_only)[0]) == pytest.approx(
        -9.247657799879168e-4
    )

    outputs = []
    audits = []
    for vectorized in (False, True):
        operation_counts: Counter[str] = Counter()
        output, reasons = _limit_covariance_diagonal(
            _SEED_1103_PRE_LIMIT_COVARIANCE,
            TRACK_COVARIANCE_FLOOR_DIAG,
            TRACK_COVARIANCE_CEILING_DIAG,
            floor_reason="track_covariance_floor",
            ceiling_reason="track_covariance_ceiling",
            vectorized_off_diagonal=vectorized,
            reason_prefix="track_covariance",
            operation_counts=operation_counts,
        )
        _assert_governed_constraints(
            output,
            TRACK_COVARIANCE_FLOOR_DIAG,
            TRACK_COVARIANCE_CEILING_DIAG,
        )
        assert "track_covariance_correlation_bound" in reasons
        assert "track_covariance_psd_projection" in reasons
        assert "track_covariance_psd_diagonal_fallback" not in reasons
        assert operation_counts[
            "track_covariance_correlation_clip_pair_count"
        ] == 1
        assert operation_counts[
            "track_covariance_psd_projection_iteration_count"
        ] >= 1
        assert operation_counts[
            "track_covariance_psd_eigenvalue_floor_count"
        ] >= 1
        outputs.append(output)
        audits.append(operation_counts)

    assert np.array_equal(outputs[0], outputs[1])
    assert audits[0] == audits[1]


@pytest.mark.parametrize("dimension", range(1, 7))
def test_random_and_extreme_covariances_preserve_all_constraints(
    dimension: int,
) -> None:
    generator = np.random.default_rng(20260724 + dimension)
    floor = np.geomspace(1.0e-6, 1.0e-2, dimension)
    ceiling = np.geomspace(1.0e2, 1.0e6, dimension)

    for _ in range(96):
        scale = np.power(10.0, generator.uniform(-8.0, 10.0))
        raw = generator.normal(size=(dimension, dimension)) * scale
        covariance = 0.5 * (raw + raw.T)
        diagonal = generator.normal(size=dimension) * scale
        np.fill_diagonal(covariance, diagonal)
        if dimension > 1:
            covariance[0, -1] = scale * 1.0e6
            covariance[-1, 0] = -scale * 2.0e5

        variants = []
        audits = []
        for vectorized in (False, True):
            operation_counts: Counter[str] = Counter()
            output = _limit_covariance_diagonal(
                covariance,
                floor,
                ceiling,
                floor_reason="property_floor",
                ceiling_reason="property_ceiling",
                vectorized_off_diagonal=vectorized,
                reason_prefix="property_covariance",
                operation_counts=operation_counts,
            )
            _assert_governed_constraints(output[0], floor, ceiling)
            variants.append(output)
            audits.append(operation_counts)

        assert variants[0][1] == variants[1][1]
        assert np.array_equal(variants[0][0], variants[1][0])
        assert audits[0] == audits[1]


def test_indefinite_matrix_inside_pairwise_bounds_is_projected() -> None:
    covariance = np.array(
        [
            [1.0, 0.9, 0.9],
            [0.9, 1.0, -0.9],
            [0.9, -0.9, 1.0],
        ],
        dtype=float,
    )
    assert float(np.linalg.eigvalsh(covariance)[0]) < 0.0
    operation_counts: Counter[str] = Counter()

    output, reasons = _limit_covariance_diagonal(
        covariance,
        np.full(3, 0.1),
        np.full(3, 10.0),
        floor_reason="floor",
        ceiling_reason="ceiling",
        reason_prefix="bounded",
        operation_counts=operation_counts,
    )

    _assert_governed_constraints(
        output,
        np.full(3, 0.1),
        np.full(3, 10.0),
    )
    assert "bounded_correlation_bound" not in reasons
    assert "bounded_psd_projection" in reasons
    assert operation_counts["bounded_psd_projection_iteration_count"] >= 1


def test_detached_track_exposes_projection_reason_and_operation_counts() -> None:
    adapter = FusionAdapter(vectorized_covariance_limit=True)
    track = GlobalTrack(
        global_track_id="global_track_031",
        state=np.zeros(6),
        covariance=_SEED_1103_PRE_LIMIT_COVARIANCE,
        timestamp=7.85180018473111,
        track_level=TrackLevel.COARSE,
        metadata={
            "measurement_timestamp": 7.7,
            "arrival_timestamp": 7.788263318059678,
        },
    )

    predicted = adapter.predict_track(track, track.timestamp)

    _assert_governed_constraints(
        predicted.covariance,
        TRACK_COVARIANCE_FLOOR_DIAG,
        TRACK_COVARIANCE_CEILING_DIAG,
    )
    assert "track_covariance_psd_projection" in predicted.metadata[
        "covariance_limit_reasons"
    ]
    counts = predicted.metadata["covariance_limit_operation_counts"]
    assert counts["track_covariance_correlation_clip_pair_count"] == 1
    assert counts["track_covariance_psd_projection_iteration_count"] >= 1
    assert predicted.metadata["covariance_limit_operation_count"] == sum(
        counts.values()
    )
    assert predicted.metadata["measurement_timestamp"] == 7.7
    assert predicted.metadata["arrival_timestamp"] == pytest.approx(
        7.788263318059678
    )


def test_internal_track_publishes_track_scoped_operation_counts() -> None:
    adapter = FusionAdapter(vectorized_covariance_limit=True)
    observation = SensorObservation(
        observation_id="psd-audit-radar-0001",
        sensor_id="RADAR-PSD-AUDIT",
        modality="radar",
        measurement_timestamp=1.0,
        arrival_timestamp=1.2,
        frame_id="ned",
        measurement=np.array([1000.0, 0.0, 0.0, 0.0]),
        covariance=np.diag([4.0, 1.0e-4, 1.0e-4, 1.0]),
        metadata={
            "sensor_position_ned": np.zeros(3),
            "scan_id": "psd-audit-scan-0001",
            "sequence_id": 1,
        },
    )
    adapter.process_scan_batch((observation,))
    record = next(iter(adapter.tracks.values()))
    record.current_state = record.current_state.__class__(
        record.current_state.state,
        _SEED_1103_PRE_LIMIT_COVARIANCE,
        record.current_state.timestamp,
    )
    record.current_state_covariance_limited = False

    track = adapter.materialize_global_tracks().tracks[0]

    track_counts = track.metadata[
        "track_covariance_limit_operation_counts"
    ]
    assert track_counts[
        "track_covariance_correlation_clip_pair_count"
    ] == 1
    assert track_counts[
        "track_covariance_psd_projection_iteration_count"
    ] >= 1
    assert track.metadata["track_covariance_limit_operation_count"] == sum(
        track_counts.values()
    )
    assert set(track_counts).issubset(
        track.metadata["covariance_limit_operation_counts"]
    )
