from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .fusion import FusionAdapter
from .metrics import (
    EstimateRecord,
    grading_accuracy,
    position_rmse,
    track_continuity,
)
from .motion import ca_truth_step, coordinated_turn_truth_step, wrap_angle
from .observations import (
    CameraModel,
    acoustic_covariance,
    acoustic_h,
    eo_covariance_from_bbox,
    eo_project,
    radar_covariance_from_range,
    radar_h,
)
from .types import SensorObservation


@dataclass
class SimulationResult:
    metrics: dict[str, float]
    truth: dict[str, dict[str, np.ndarray]]
    observations: list[SensorObservation]
    compensated_estimates: list[EstimateRecord]
    uncompensated_estimates: list[EstimateRecord]
    report_path: Path | None = None
    figure_paths: list[Path] | None = None


def generate_truth(
    target_count: int = 3,
    duration_s: float = 60.0,
    dt: float = 0.1,
    extension_s: float = 2.5,
) -> dict[str, dict[str, np.ndarray]]:
    target_count = int(np.clip(target_count, 1, 3))
    times = np.arange(0.0, duration_s + extension_s + 0.5 * dt, dt)
    initial_states = [
        np.array([160.0, -70.0, -25.0, 5.8, 1.8, -0.02], dtype=float),
        np.array([230.0, 90.0, -32.0, 3.0, -6.5, 0.03], dtype=float),
        np.array([130.0, 60.0, -22.0, 4.5, 3.0, 0.0], dtype=float),
    ]
    truth: dict[str, dict[str, np.ndarray]] = {}
    for target_idx in range(target_count):
        states = np.zeros((times.size, 6), dtype=float)
        states[0] = initial_states[target_idx]
        for idx in range(1, times.size):
            t = times[idx - 1]
            if target_idx == 0:
                states[idx] = ca_truth_step(states[idx - 1], np.zeros(3), dt)
            elif target_idx == 1:
                states[idx] = coordinated_turn_truth_step(states[idx - 1], turn_rate=0.025, dt=dt)
            else:
                acceleration = np.array(
                    [0.20 * np.sin(0.16 * t), -0.12 * np.cos(0.10 * t), 0.0],
                    dtype=float,
                )
                states[idx] = ca_truth_step(states[idx - 1], acceleration, dt)
        truth[f"target_{target_idx + 1:02d}"] = {"times": times, "states": states}
    return truth


def _state_at_grid(truth_item: dict[str, np.ndarray], index: int) -> np.ndarray:
    return truth_item["states"][index]


def generate_observations(
    truth: dict[str, dict[str, np.ndarray]],
    duration_s: float = 60.0,
    dt: float = 0.1,
    seed: int = 7,
) -> list[SensorObservation]:
    rng = np.random.default_rng(seed)
    radar_position = np.array([0.0, 0.0, 0.0], dtype=float)
    acoustic_position = np.array([0.0, -45.0, 0.0], dtype=float)
    camera = CameraModel()
    observations: list[SensorObservation] = []
    radar_stride = max(int(round(0.1 / dt)), 1)
    acoustic_stride = max(int(round(0.5 / dt)), 1)
    eo_stride = max(int(round(0.2 / dt)), 1)

    for truth_id, truth_item in truth.items():
        times = truth_item["times"]
        max_index = int(np.searchsorted(times, duration_s, side="right"))
        for idx in range(max_index):
            t = float(times[idx])
            state = _state_at_grid(truth_item, idx)

            if idx % radar_stride == 0:
                z = radar_h(state, radar_position)
                r = radar_covariance_from_range(z[0])
                noisy_z = z + rng.multivariate_normal(np.zeros(4), r)
                noisy_z[1] = wrap_angle(noisy_z[1])
                noisy_z[2] = wrap_angle(noisy_z[2])
                delay = float(rng.uniform(0.5, 2.0))
                observations.append(
                    SensorObservation(
                        observation_id=f"radar_{truth_id}_{idx:04d}",
                        sensor_id="radar_ground_01",
                        modality="radar",
                        measurement_timestamp=t,
                        arrival_timestamp=t + delay,
                        frame_id="ned",
                        measurement=noisy_z,
                        covariance=r,
                        confidence=0.9,
                        metadata={
                            "truth_id": truth_id,
                            "sensor_position_ned": radar_position,
                        },
                    )
                )

            if idx % acoustic_stride == 0:
                confidence = float(rng.uniform(0.65, 0.9))
                r = acoustic_covariance(confidence)
                z = acoustic_h(state, acoustic_position)
                noisy_z = np.array([wrap_angle(z[0] + rng.normal(0.0, np.sqrt(r[0, 0])))])
                delay = float(rng.uniform(0.08, 0.35))
                observations.append(
                    SensorObservation(
                        observation_id=f"acoustic_{truth_id}_{idx:04d}",
                        sensor_id="acoustic_array_01",
                        modality="acoustic",
                        measurement_timestamp=t,
                        arrival_timestamp=t + delay,
                        frame_id="ned",
                        measurement=noisy_z,
                        covariance=r,
                        classification_hint=f"voiceprint_{truth_id}",
                        confidence=confidence,
                        metadata={
                            "truth_id": truth_id,
                            "sensor_position_ned": acoustic_position,
                        },
                    )
                )

            if idx % eo_stride == 0:
                pixel = eo_project(state, camera)
                rel = state[:3] - camera.position_ned
                point_camera = camera.rotation_world_to_camera @ rel
                if point_camera[2] <= 1.0:
                    continue
                if not (-80.0 <= pixel[0] <= camera.width + 80.0 and -80.0 <= pixel[1] <= camera.height + 80.0):
                    continue
                distance = max(float(np.linalg.norm(rel)), 1.0)
                box_size = float(np.clip(5200.0 / distance, 8.0, 80.0))
                bbox = np.array(
                    [
                        pixel[0] - 0.5 * box_size,
                        pixel[1] - 0.35 * box_size,
                        pixel[0] + 0.5 * box_size,
                        pixel[1] + 0.35 * box_size,
                    ],
                    dtype=float,
                )
                flags: tuple[str, ...] = ()
                if box_size < 14.0:
                    flags = ("small_bbox",)
                confidence = float(np.clip(0.95 - 0.0015 * distance + rng.normal(0.0, 0.03), 0.45, 0.95))
                r = eo_covariance_from_bbox(bbox, confidence, flags)
                noisy_pixel = pixel + rng.multivariate_normal(np.zeros(2), r)
                delay = float(rng.uniform(0.04, 0.18))
                observations.append(
                    SensorObservation(
                        observation_id=f"eo_{truth_id}_{idx:04d}",
                        sensor_id="eo_camera_01",
                        modality="eo",
                        measurement_timestamp=t,
                        arrival_timestamp=t + delay,
                        frame_id="pixel",
                        measurement=noisy_pixel,
                        covariance=r,
                        confidence=confidence,
                        quality_flags=flags,
                        metadata={
                            "truth_id": truth_id,
                            "bbox": bbox,
                            "camera_model": camera,
                        },
                    )
                )

    return sorted(observations, key=lambda obs: (obs.arrival_timestamp, obs.observation_id))


def _run_adapter(
    observations: list[SensorObservation],
    latency_compensation: bool,
    use_truth_hints_for_association: bool,
) -> list[EstimateRecord]:
    adapter = FusionAdapter(
        process_noise=8.0,
        stable_threshold_m=30.0,
        handover_threshold_m=12.0,
        association_gate=45.0,
        latency_compensation=latency_compensation,
        use_truth_hints_for_association=use_truth_hints_for_association,
    )
    estimates: list[EstimateRecord] = []
    for observation in observations:
        tracks = adapter.process(observation)
        estimates.extend(EstimateRecord.from_track(track) for track in tracks)
    return estimates


def run_simulation(
    target_count: int = 3,
    duration_s: float = 60.0,
    dt: float = 0.1,
    seed: int = 7,
    output_dir: str | Path | None = None,
    make_plots: bool = True,
    write_report: bool = True,
    use_truth_hints_for_association: bool = False,
) -> SimulationResult:
    truth = generate_truth(target_count=target_count, duration_s=duration_s, dt=dt)
    observations = generate_observations(truth, duration_s=duration_s, dt=dt, seed=seed)
    compensated = _run_adapter(
        observations,
        latency_compensation=True,
        use_truth_hints_for_association=use_truth_hints_for_association,
    )
    uncompensated = _run_adapter(
        observations,
        latency_compensation=False,
        use_truth_hints_for_association=use_truth_hints_for_association,
    )

    metrics = {
        "compensated_rmse_m": position_rmse(compensated, truth, end_time=duration_s),
        "uncompensated_rmse_m": position_rmse(uncompensated, truth, end_time=duration_s),
        "compensated_track_continuity": track_continuity(compensated, truth, duration_s),
        "uncompensated_track_continuity": track_continuity(uncompensated, truth, duration_s),
        "compensated_grading_accuracy": grading_accuracy(
            compensated, truth, stable_threshold_m=30.0, handover_threshold_m=12.0, end_time=duration_s
        ),
        "uncompensated_grading_accuracy": grading_accuracy(
            uncompensated, truth, stable_threshold_m=30.0, handover_threshold_m=12.0, end_time=duration_s
        ),
        "observation_count": float(len(observations)),
        "mean_radar_latency_s": float(
            np.mean([obs.latency for obs in observations if obs.modality == "radar"])
        ),
    }

    report_path: Path | None = None
    figure_paths: list[Path] = []
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if make_plots:
            figure_paths = _make_plots(out_dir, truth, compensated, uncompensated, metrics, duration_s)
        if write_report:
            report_path = _write_report(out_dir, metrics, figure_paths, target_count, duration_s, dt, seed)

    return SimulationResult(
        metrics=metrics,
        truth=truth,
        observations=observations,
        compensated_estimates=compensated,
        uncompensated_estimates=uncompensated,
        report_path=report_path,
        figure_paths=figure_paths,
    )


def _make_plots(
    output_dir: Path,
    truth: dict[str, dict[str, np.ndarray]],
    compensated: list[EstimateRecord],
    uncompensated: list[EstimateRecord],
    metrics: dict[str, float],
    duration_s: float,
) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths: list[Path] = []

    fig, ax = plt.subplots(figsize=(8, 6))
    for truth_id, truth_item in truth.items():
        mask = truth_item["times"] <= duration_s
        states = truth_item["states"][mask]
        ax.plot(states[:, 1], states[:, 0], linewidth=2, label=f"{truth_id} truth")
    for label, estimates, alpha in [
        ("compensated", compensated, 0.75),
        ("uncompensated", uncompensated, 0.35),
    ]:
        if not estimates:
            continue
        xy = np.array([record.state[:2] for record in estimates if record.timestamp <= duration_s])
        if xy.size:
            ax.scatter(xy[:, 1], xy[:, 0], s=5, alpha=alpha, label=label)
    ax.set_xlabel("East y (m)")
    ax.set_ylabel("North x (m)")
    ax.set_title("NED horizontal truth and estimates")
    ax.grid(True, linewidth=0.4, alpha=0.4)
    ax.legend(loc="best", fontsize=8)
    path = output_dir / "tracks_xy.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(6, 4))
    labels = ["compensated", "uncompensated"]
    values = [metrics["compensated_rmse_m"], metrics["uncompensated_rmse_m"]]
    ax.bar(labels, values, color=["#2f6f8f", "#b36b43"])
    ax.set_ylabel("Position RMSE (m)")
    ax.set_title("Latency compensation ablation")
    ax.grid(axis="y", linewidth=0.4, alpha=0.4)
    path = output_dir / "rmse_latency_ablation.png"
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)
    return paths


def _write_report(
    output_dir: Path,
    metrics: dict[str, float],
    figure_paths: list[Path],
    target_count: int,
    duration_s: float,
    dt: float,
    seed: int,
) -> Path:
    report_path = output_dir / "EXPERIMENT_REPORT.md"
    figure_lines = "\n".join(f"- `{path.name}`" for path in figure_paths) or "- No plots generated."
    text = f"""# D1 Sensor Fusion Offline Experiment Report

## Scope

This report covers offline research simulation only. It does not include real fire-control parameters, damage logic, vehicle control, hardware drivers, automatic action, or bypass of human authorization.

## Scenario

- Targets: {target_count}
- Duration: {duration_s:.1f} s
- Base step: {dt:.2f} s
- Seed: {seed}
- Sensors: delayed range-dependent radar, acoustic bearing with voiceprint hints, EO pixel-box projection.
- Filter: NumPy EKF fallback with fixed-lag measurement-time replay.

## Metrics

| Metric | Value |
|---|---:|
| Compensated RMSE (m) | {metrics['compensated_rmse_m']:.3f} |
| Uncompensated RMSE (m) | {metrics['uncompensated_rmse_m']:.3f} |
| Compensated track continuity | {metrics['compensated_track_continuity']:.3f} |
| Uncompensated track continuity | {metrics['uncompensated_track_continuity']:.3f} |
| Compensated grading accuracy | {metrics['compensated_grading_accuracy']:.3f} |
| Uncompensated grading accuracy | {metrics['uncompensated_grading_accuracy']:.3f} |
| Observation count | {metrics['observation_count']:.0f} |
| Mean radar latency (s) | {metrics['mean_radar_latency_s']:.3f} |

## Figures

{figure_lines}

## Interpretation

The compensated run updates each track at `measurement_timestamp` and replays to the current arrival time. The uncompensated run intentionally updates stale measurements at `arrival_timestamp`, which provides the latency-ablation baseline.
"""
    report_path.write_text(text, encoding="utf-8")
    return report_path
