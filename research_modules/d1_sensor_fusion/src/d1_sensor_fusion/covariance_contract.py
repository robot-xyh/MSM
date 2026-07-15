from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np


OBSERVATION_MEASUREMENT_DIMENSIONS = {
    "radar": 4,
    "acoustic": 1,
    "eo": 2,
    "lidar": 3,
}
COVARIANCE_IMPUTATION_METADATA_KEY = "covariance_imputation_provenance"
OFFLINE_LEGACY_COVARIANCE_MIGRATION_MODE = "explicit_offline_legacy_migration"
OFFLINE_LEGACY_COVARIANCE_IMPUTATION_SCHEMA_VERSION = (
    "d1.offline_legacy_covariance_imputation.v1"
)


def validate_sensor_observation_covariance(
    observation: Any,
    *,
    context: str = "D1 SensorObservation",
) -> np.ndarray:
    """Return a validated covariance matrix without repairing invalid input."""

    modality = str(observation.modality).lower()
    expected_dimension = OBSERVATION_MEASUREMENT_DIMENSIONS.get(modality)
    if expected_dimension is None:
        raise ValueError(f"{context} has unsupported modality {modality!r}")

    measurement_size = int(np.asarray(observation.measurement).size)
    if measurement_size != expected_dimension:
        raise ValueError(
            f"{context} {modality} measurement dimension must be "
            f"{expected_dimension}; got {measurement_size}"
        )

    if observation.covariance is None:
        raise ValueError(f"{context} requires covariance on every observation")
    try:
        covariance = np.asarray(observation.covariance, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} covariance must be a numeric matrix") from exc

    expected_shape = (expected_dimension, expected_dimension)
    if covariance.shape != expected_shape:
        raise ValueError(
            f"{context} {modality} covariance shape must be {expected_shape}; "
            f"got {covariance.shape}"
        )
    if not np.isfinite(covariance).all():
        raise ValueError(f"{context} covariance must be finite")
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-9):
        raise ValueError(f"{context} covariance must be symmetric")
    if float(np.linalg.eigvalsh(covariance).min()) < -1.0e-9:
        raise ValueError(f"{context} covariance must be positive semidefinite")
    return covariance


def validate_online_sensor_observation(
    observation: Any,
    *,
    context: str = "D1 online SensorObservation",
) -> np.ndarray:
    """Validate the online covariance contract and reject offline migrations."""

    covariance = validate_sensor_observation_covariance(observation, context=context)
    metadata = observation.metadata if isinstance(observation.metadata, Mapping) else {}
    if COVARIANCE_IMPUTATION_METADATA_KEY in metadata:
        raise ValueError(
            f"{context} rejects offline legacy covariance migration; "
            "migrated observations are evaluator-only"
        )
    return covariance
