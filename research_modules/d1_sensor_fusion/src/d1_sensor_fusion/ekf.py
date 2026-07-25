from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Callable

import numpy as np

from .motion import predict_cv_state, predict_cv_state_with_model, wrap_residual


@dataclass
class EKFState:
    state: np.ndarray
    covariance: np.ndarray
    timestamp: float

    def __post_init__(self) -> None:
        self.state = np.asarray(self.state, dtype=float).reshape(6)
        self.covariance = np.asarray(self.covariance, dtype=float).reshape(6, 6)
        self.timestamp = float(self.timestamp)

    def copy(self) -> "EKFState":
        return EKFState(self.state.copy(), self.covariance.copy(), self.timestamp)


def numerical_jacobian(
    fn: Callable[[np.ndarray], np.ndarray],
    x: np.ndarray,
    eps: float = 1e-5,
) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    y0 = np.asarray(fn(x), dtype=float)
    jac = np.zeros((y0.size, x.size), dtype=float)
    for idx in range(x.size):
        step = eps * max(1.0, abs(x[idx]))
        xp = x.copy()
        xm = x.copy()
        xp[idx] += step
        xm[idx] -= step
        jac[:, idx] = (np.asarray(fn(xp)) - np.asarray(fn(xm))) / (2.0 * step)
    return jac


def structured_numerical_jacobian(
    fn: Callable[[np.ndarray], np.ndarray],
    x: np.ndarray,
    *,
    output_size: int,
    active_state_indices: tuple[int, ...],
    eps: float = 1e-5,
) -> np.ndarray:
    """Evaluate the reference finite differences only on structural columns.

    D1 measurement models declare output size and the state columns on which
    their observation equation depends. Active columns retain the exact
    reference arithmetic. Inactive columns are mathematical zeros and are
    materialized as such without evaluating the observation function.
    """

    if isinstance(output_size, bool) or not isinstance(output_size, Integral):
        raise TypeError("output_size must be an integer")
    output_size = int(output_size)
    if output_size < 1:
        raise ValueError("output_size must be positive")

    x = np.asarray(x, dtype=float)
    normalized_indices: list[int] = []
    seen: set[int] = set()
    for raw_index in active_state_indices:
        if isinstance(raw_index, bool) or not isinstance(raw_index, Integral):
            raise TypeError("active_state_indices must contain integers")
        index = int(raw_index)
        if index < 0 or index >= x.size:
            raise ValueError("active_state_indices contains an out-of-range index")
        if index in seen:
            raise ValueError("active_state_indices must not contain duplicates")
        seen.add(index)
        normalized_indices.append(index)

    jac = np.zeros((output_size, x.size), dtype=float)
    for idx in normalized_indices:
        step = eps * max(1.0, abs(x[idx]))
        xp = x.copy()
        xm = x.copy()
        xp[idx] += step
        xm[idx] -= step
        positive = np.asarray(fn(xp))
        negative = np.asarray(fn(xm))
        if positive.size != output_size or negative.size != output_size:
            raise ValueError("measurement function output size changed")
        jac[:, idx] = (positive - negative) / (2.0 * step)
    return jac


def predict_to(
    ekf_state: EKFState,
    timestamp: float,
    process_noise: float,
) -> EKFState:
    timestamp = float(timestamp)
    dt = timestamp - ekf_state.timestamp
    if dt <= 1e-12:
        out = ekf_state.copy()
        out.timestamp = timestamp
        return out
    state, covariance = predict_cv_state(
        ekf_state.state,
        ekf_state.covariance,
        dt,
        spectral_density=process_noise,
    )
    return EKFState(state, covariance, timestamp)


def predict_to_with_cv_model(
    ekf_state: EKFState,
    timestamp: float,
    transition: np.ndarray,
    process_covariance: np.ndarray,
) -> EKFState:
    """Predict with an immutable CV model supplied by the owning adapter."""

    timestamp = float(timestamp)
    dt = timestamp - ekf_state.timestamp
    if dt <= 1e-12:
        out = ekf_state.copy()
        out.timestamp = timestamp
        return out
    state, covariance = predict_cv_state_with_model(
        ekf_state.state,
        ekf_state.covariance,
        transition,
        process_covariance,
    )
    return EKFState(state, covariance, timestamp)


def ekf_update(
    ekf_state: EKFState,
    z: np.ndarray,
    h_fn: Callable[[np.ndarray], np.ndarray],
    h_jacobian_fn: Callable[[np.ndarray], np.ndarray],
    r: np.ndarray,
    angle_indices: tuple[int, ...] = (),
) -> tuple[EKFState, float]:
    z = np.asarray(z, dtype=float).reshape(-1)
    r = np.asarray(r, dtype=float)
    x = ekf_state.state
    p = ekf_state.covariance
    h = np.asarray(h_fn(x), dtype=float).reshape(-1)
    h_j = np.asarray(h_jacobian_fn(x), dtype=float)
    residual = wrap_residual(z - h, angle_indices)
    s = h_j @ p @ h_j.T + r
    s = 0.5 * (s + s.T) + 1e-9 * np.eye(s.shape[0])
    ph_t = p @ h_j.T
    try:
        k = np.linalg.solve(s, ph_t.T).T
        nis = float(residual.T @ np.linalg.solve(s, residual))
    except np.linalg.LinAlgError:
        s_inv = np.linalg.pinv(s)
        k = ph_t @ s_inv
        nis = float(residual.T @ s_inv @ residual)

    updated_x = x + k @ residual
    i = np.eye(p.shape[0])
    joseph_left = i - k @ h_j
    updated_p = joseph_left @ p @ joseph_left.T + k @ r @ k.T
    updated_p = 0.5 * (updated_p + updated_p.T)
    return EKFState(updated_x, updated_p, ekf_state.timestamp), nis
