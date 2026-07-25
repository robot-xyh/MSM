from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from d1_sensor_fusion import FusionAdapter
from d1_sensor_fusion.fusion import (
    COVARIANCE_CHOLESKY_RELATIVE_DETERMINANT_FLOOR,
    COVARIANCE_PSD_CHECK_CANDIDATE_IMPLEMENTATION_ID,
    COVARIANCE_PSD_CHECK_REFERENCE_IMPLEMENTATION_ID,
    _limit_covariance_diagonal,
    _project_bounded_covariance_to_psd,
)
from d1_sensor_fusion.scalable_3d import Scalable3DFusionAdapter


_FLOOR = np.full(6, 1.0e-16, dtype=float)
_CEILING = np.full(6, 1.0e6, dtype=float)


def _indefinite_covariance() -> np.ndarray:
    covariance = np.eye(6, dtype=float)
    covariance[:3, :3] = np.array(
        [
            [1.0, 0.9, 0.9],
            [0.9, 1.0, -0.9],
            [0.9, -0.9, 1.0],
        ],
        dtype=float,
    )
    return covariance


def _limit(
    covariance: np.ndarray,
    *,
    candidate_enabled: bool,
    diagnostics: Counter[str] | None = None,
    business_operations: Counter[str] | None = None,
) -> tuple[np.ndarray, tuple[str, ...]]:
    return _limit_covariance_diagonal(
        covariance,
        _FLOOR,
        _CEILING,
        floor_reason="floor",
        ceiling_reason="ceiling",
        vectorized_off_diagonal=True,
        reason_prefix="test_covariance",
        operation_counts=business_operations,
        cholesky_psd_fast_path=candidate_enabled,
        psd_check_operation_counts=diagnostics,
    )


def test_candidate_is_explicit_and_standalone_default_remains_reference() -> None:
    reference = FusionAdapter()
    candidate = FusionAdapter(cholesky_covariance_psd_fast_path=True)
    scalable_reference = Scalable3DFusionAdapter()
    scalable_candidate = Scalable3DFusionAdapter(
        cholesky_covariance_psd_fast_path=True
    )

    assert reference.cholesky_covariance_psd_fast_path is False
    assert scalable_reference.cholesky_covariance_psd_fast_path is False
    assert candidate.cholesky_covariance_psd_fast_path is True
    assert scalable_candidate.cholesky_covariance_psd_fast_path is True
    assert (
        reference.covariance_psd_check_diagnostics()["implementation_id"]
        == COVARIANCE_PSD_CHECK_REFERENCE_IMPLEMENTATION_ID
    )
    assert (
        candidate.covariance_psd_check_diagnostics()["implementation_id"]
        == COVARIANCE_PSD_CHECK_CANDIDATE_IMPLEMENTATION_ID
    )
    assert (
        candidate.covariance_psd_check_diagnostics()[
            "relative_determinant_floor"
        ]
        == COVARIANCE_CHOLESKY_RELATIVE_DETERMINANT_FLOOR
    )
    with pytest.raises(
        TypeError,
        match="cholesky_covariance_psd_fast_path",
    ):
        FusionAdapter(
            cholesky_covariance_psd_fast_path=1  # type: ignore[arg-type]
        )


def test_spd_candidate_is_bitwise_equivalent_and_non_aliasing() -> None:
    generator = np.random.default_rng(20260724)
    diagnostics: Counter[str] = Counter()

    for _ in range(128):
        diagonal = generator.uniform(1.0, 100.0, size=6)
        correlation = generator.normal(scale=1.0e-3, size=(6, 6))
        correlation = 0.5 * (correlation + correlation.T)
        np.fill_diagonal(correlation, 0.0)
        covariance = np.diag(diagonal) + (
            np.sqrt(np.outer(diagonal, diagonal)) * correlation
        )
        original = covariance.copy()

        reference = _limit(covariance, candidate_enabled=False)
        candidate = _limit(
            covariance,
            candidate_enabled=True,
            diagnostics=diagnostics,
        )

        assert reference[1] == candidate[1] == ()
        assert np.array_equal(reference[0], candidate[0])
        assert np.array_equal(covariance, original)
        assert not np.shares_memory(reference[0], covariance)
        assert not np.shares_memory(candidate[0], covariance)

    assert diagnostics == {
        "cholesky_attempt_count": 128,
        "cholesky_success_count": 128,
    }


def test_near_singular_positive_definite_matrix_uses_fast_path_exactly() -> None:
    covariance = np.diag(
        [1.0e-14, 1.0e-10, 1.0e-6, 1.0e-2, 1.0, 10.0]
    )
    diagnostics: Counter[str] = Counter()

    reference = _limit(covariance, candidate_enabled=False)
    candidate = _limit(
        covariance,
        candidate_enabled=True,
        diagnostics=diagnostics,
    )

    assert np.array_equal(reference[0], candidate[0])
    assert reference[1] == candidate[1] == ()
    assert diagnostics == {
        "cholesky_attempt_count": 1,
        "cholesky_success_count": 1,
    }


def test_roundoff_scale_indefinite_matrix_falls_back_exactly() -> None:
    covariance = np.array(
        [
            [
                0.4510446857978497,
                -0.5883177966255164,
                -1.0882610597771931,
                1.0165367403468077,
                -0.4334983355541179,
                -0.5619998810340328,
            ],
            [
                -0.5883177966255164,
                1.8109916907785608,
                2.2067165255609478,
                -1.9455038479144955,
                1.6100814250648934,
                0.710983560129121,
            ],
            [
                -1.0882610597771931,
                2.2067165255609478,
                3.5994590518111282,
                -3.2216237735123454,
                1.924688365662182,
                1.582194529463176,
            ],
            [
                1.0165367403468077,
                -1.9455038479144955,
                -3.2216237735123454,
                2.898858747654143,
                -1.6695051271559138,
                -1.445741573875167,
            ],
            [
                -0.4334983355541179,
                1.6100814250648934,
                1.924688365662182,
                -1.6695051271559138,
                1.484121808909296,
                0.5757944359899945,
            ],
            [
                -0.5619998810340328,
                0.710983560129121,
                1.582194529463176,
                -1.445741573875167,
                0.5757944359899945,
                0.8565250150490198,
            ],
        ],
        dtype=float,
    )
    diagnostics: Counter[str] = Counter()

    reference = _project_bounded_covariance_to_psd(
        covariance,
        np.diag(covariance),
        reason_prefix="test_covariance",
        operation_counts=Counter(),
    )
    candidate = _project_bounded_covariance_to_psd(
        covariance,
        np.diag(covariance),
        reason_prefix="test_covariance",
        operation_counts=Counter(),
        cholesky_psd_fast_path=True,
        psd_check_operation_counts=diagnostics,
    )

    assert reference[1] == candidate[1] == (
        "test_covariance_psd_projection",
    )
    assert np.array_equal(reference[0], candidate[0])
    assert diagnostics == {
        "cholesky_attempt_count": 1,
        "cholesky_fallback_count": 1,
    }


def test_semidefinite_and_indefinite_matrices_fall_back_to_reference() -> None:
    semidefinite = np.full((6, 6), -0.2, dtype=float)
    np.fill_diagonal(semidefinite, 1.0)
    indefinite = _indefinite_covariance()

    for covariance in (semidefinite, indefinite):
        reference = _project_bounded_covariance_to_psd(
            covariance,
            np.diag(covariance),
            reason_prefix="test_covariance",
            operation_counts=Counter(),
        )
        diagnostics: Counter[str] = Counter()
        candidate = _project_bounded_covariance_to_psd(
            covariance,
            np.diag(covariance),
            reason_prefix="test_covariance",
            operation_counts=Counter(),
            cholesky_psd_fast_path=True,
            psd_check_operation_counts=diagnostics,
        )

        assert reference[1] == candidate[1]
        assert np.array_equal(reference[0], candidate[0])
        assert diagnostics == {
            "cholesky_attempt_count": 1,
            "cholesky_fallback_count": 1,
        }


def test_nonfinite_input_preserves_rejection_before_candidate_attempt() -> None:
    covariance = np.eye(6, dtype=float)
    covariance[0, 0] = np.nan
    diagnostics: Counter[str] = Counter()

    with pytest.raises(ValueError, match="finite"):
        _limit(covariance, candidate_enabled=False)
    with pytest.raises(ValueError, match="finite"):
        _limit(
            covariance,
            candidate_enabled=True,
            diagnostics=diagnostics,
        )

    assert diagnostics == {}


def test_diagnostics_conserve_attempts_without_changing_business_counts() -> None:
    adapter = FusionAdapter(cholesky_covariance_psd_fast_path=True)
    business_counts: Counter[str] = Counter()

    adapter._limit_state_covariance(
        np.diag([4.0, 5.0, 6.0, 1.0, 2.0, 3.0]),
        operation_counts=business_counts,
    )
    adapter._limit_state_covariance(
        _indefinite_covariance(),
        operation_counts=business_counts,
    )

    diagnostics = adapter.covariance_psd_check_diagnostics()
    assert diagnostics["operation_counts"] == {
        "cholesky_attempt_count": 2,
        "cholesky_success_count": 1,
        "cholesky_fallback_count": 1,
    }
    assert diagnostics["conservation"][
        "attempt_equals_success_plus_fallback"
    ] is True
    assert not any("cholesky" in key for key in business_counts)


def test_non_six_dimensional_covariance_keeps_reference_check() -> None:
    diagnostics: Counter[str] = Counter()
    covariance = np.diag([1.0, 2.0, 3.0, 4.0])

    reference = _limit_covariance_diagonal(
        covariance,
        np.full(4, 0.1),
        np.full(4, 10.0),
        floor_reason="floor",
        ceiling_reason="ceiling",
    )
    candidate = _limit_covariance_diagonal(
        covariance,
        np.full(4, 0.1),
        np.full(4, 10.0),
        floor_reason="floor",
        ceiling_reason="ceiling",
        cholesky_psd_fast_path=True,
        psd_check_operation_counts=diagnostics,
    )

    assert reference[1] == candidate[1]
    assert np.array_equal(reference[0], candidate[0])
    assert diagnostics == {}
