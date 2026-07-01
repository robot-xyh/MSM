from __future__ import annotations

import numpy as np


def wrap_angle(angle: float | np.ndarray) -> float | np.ndarray:
    """Wrap radians to [-pi, pi)."""

    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def wrap_residual(residual: np.ndarray, angle_indices: tuple[int, ...]) -> np.ndarray:
    wrapped = residual.copy()
    for idx in angle_indices:
        wrapped[idx] = wrap_angle(wrapped[idx])
    return wrapped


def cv_transition(dt: float) -> np.ndarray:
    dt = max(float(dt), 0.0)
    f = np.eye(6)
    f[0, 3] = dt
    f[1, 4] = dt
    f[2, 5] = dt
    return f


def cv_process_noise(dt: float, spectral_density: float) -> np.ndarray:
    dt = max(float(dt), 0.0)
    q = float(spectral_density)
    q11 = 0.25 * dt**4 * q
    q12 = 0.5 * dt**3 * q
    q22 = dt**2 * q
    out = np.zeros((6, 6), dtype=float)
    out[:3, :3] = q11 * np.eye(3)
    out[:3, 3:] = q12 * np.eye(3)
    out[3:, :3] = q12 * np.eye(3)
    out[3:, 3:] = q22 * np.eye(3)
    return out


def predict_cv_state(
    state: np.ndarray,
    covariance: np.ndarray,
    dt: float,
    spectral_density: float,
) -> tuple[np.ndarray, np.ndarray]:
    f = cv_transition(dt)
    q = cv_process_noise(dt, spectral_density)
    x = f @ state
    p = f @ covariance @ f.T + q
    return x, 0.5 * (p + p.T)


def ca_truth_step(state: np.ndarray, acceleration: np.ndarray, dt: float) -> np.ndarray:
    """Six-state truth step driven by a known acceleration vector."""

    x = np.asarray(state, dtype=float).reshape(6).copy()
    a = np.asarray(acceleration, dtype=float).reshape(3)
    dt = float(dt)
    x[:3] = x[:3] + x[3:] * dt + 0.5 * a * dt**2
    x[3:] = x[3:] + a * dt
    return x


def coordinated_turn_truth_step(state: np.ndarray, turn_rate: float, dt: float) -> np.ndarray:
    """Horizontal coordinated-turn truth step in NED.

    The fallback filter still estimates a six-state CV model. This function is
    used to generate maneuvering truth trajectories for offline experiments.
    """

    x = np.asarray(state, dtype=float).reshape(6).copy()
    omega = float(turn_rate)
    dt = float(dt)
    px, py, pz, vx, vy, vz = x
    if abs(omega) < 1e-9:
        return ca_truth_step(x, np.zeros(3), dt)

    sin_wt = np.sin(omega * dt)
    cos_wt = np.cos(omega * dt)
    new_px = px + (vx * sin_wt + vy * (cos_wt - 1.0)) / omega
    new_py = py + (vx * (1.0 - cos_wt) + vy * sin_wt) / omega
    new_vx = vx * cos_wt - vy * sin_wt
    new_vy = vx * sin_wt + vy * cos_wt
    return np.array([new_px, new_py, pz + vz * dt, new_vx, new_vy, vz], dtype=float)
