import numpy as np

from dual_optical_online_benchmark.generate_track_registration_figures import (
    fit_joint_constant_velocity,
)


def _track(camera_id: str, camera: np.ndarray, p0: np.ndarray, velocity: np.ndarray):
    samples = []
    for timestamp in (0.0, 2.0, 4.0, 6.0):
        position = p0 + velocity * timestamp
        direction = position - camera
        direction = direction / np.linalg.norm(direction)
        samples.append(
            {
                "timestamp": timestamp,
                "direction_ned": direction.tolist(),
            }
        )
    return {"camera_id": camera_id, "samples": samples}


def test_joint_fit_recovers_constant_velocity_from_two_stations() -> None:
    camera_a = np.array([0.0, -1000.0, -100.0])
    camera_b = np.array([0.0, 1000.0, -100.0])
    position = np.array([1800.0, -200.0, -100.0])
    velocity = np.array([50.0, 5.0, 0.0])
    fit = fit_joint_constant_velocity(
        _track("Optical_A", camera_a, position, velocity),
        _track("Optical_B", camera_b, position, velocity),
        {"Optical_A": camera_a, "Optical_B": camera_b},
    )

    assert np.linalg.norm(fit.velocity - velocity) < 1e-6
    expected_at_reference = position + velocity * fit.reference_time
    assert np.linalg.norm(fit.position_at_reference - expected_at_reference) < 1e-6
    assert fit.rms_angular_residual_mrad < 1e-5
