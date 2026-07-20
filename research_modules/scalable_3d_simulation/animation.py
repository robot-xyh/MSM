"""Three-dimensional GIF/MP4 rendering from evaluator-only state histories."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .orchestrator import EpisodeResult


def write_trajectory_animation(
    result: EpisodeResult,
    path: Path,
    *,
    max_frames: int = 120,
    trail_frames: int = 20,
    fps: int = 10,
) -> Path:
    """Render a bounded-size 3D animation without entering the online bus."""

    import matplotlib

    matplotlib.use("Agg")
    ensure_mplot3d(matplotlib)
    import matplotlib.animation as animation
    import matplotlib.pyplot as plt

    if path.suffix.lower() not in {".gif", ".mp4"}:
        raise ValueError("animation path must end in .gif or .mp4")
    if max_frames <= 1 or trail_frames < 0 or fps <= 0:
        raise ValueError("invalid animation frame or fps configuration")
    path.parent.mkdir(parents=True, exist_ok=True)
    total_steps = result.timestamps.size
    stride = max(1, int(np.ceil(total_steps / max_frames)))
    frame_indices = np.arange(0, total_steps, stride, dtype=int)
    if frame_indices[-1] != total_steps - 1:
        frame_indices = np.append(frame_indices, total_steps - 1)

    intruders = _ned_to_plot(result.intruder_state_history[:, :, :3])
    interceptors = _ned_to_plot(result.interceptor_state_history[:, :, :3])
    recon = _ned_to_plot(result.recon_state_history[:, :, :3])
    all_positions = np.concatenate(
        [values.reshape(-1, 3) for values in (intruders, interceptors, recon) if values.size],
        axis=0,
    )
    lower = np.min(all_positions, axis=0)
    upper = np.max(all_positions, axis=0)
    margin = np.maximum((upper - lower) * 0.05, np.array([50.0, 50.0, 20.0]))

    figure = plt.figure(figsize=(10, 7))
    axis = figure.add_subplot(111, projection="3d")
    target_scatter = axis.scatter([], [], [], color="#b33a3a", s=12, label="Intruders")
    resource_scatter = axis.scatter([], [], [], color="#286090", s=12, label="Interceptors")
    recon_scatter = axis.scatter([], [], [], color="#2f7d32", marker="^", s=28, label="Recon")
    trail_limit = min(20, result.config.target_count, result.config.resource_count)
    target_trails = [axis.plot([], [], [], color="#b33a3a", alpha=0.35, lw=0.8)[0] for _ in range(trail_limit)]
    resource_trails = [axis.plot([], [], [], color="#286090", alpha=0.35, lw=0.8)[0] for _ in range(trail_limit)]
    axis.set_xlim(lower[0] - margin[0], upper[0] + margin[0])
    axis.set_ylim(lower[1] - margin[1], upper[1] + margin[1])
    axis.set_zlim(max(0.0, lower[2] - margin[2]), upper[2] + margin[2])
    axis.set_xlabel("North / m")
    axis.set_ylabel("East / m")
    axis.set_zlabel("Altitude / m")
    axis.legend(loc="upper right")

    def update(frame_number: int) -> tuple[object, ...]:
        index = int(frame_indices[frame_number])
        active = result.intruder_active_history[index]
        _set_scatter(target_scatter, intruders[index, active])
        _set_scatter(resource_scatter, interceptors[index])
        _set_scatter(recon_scatter, recon[index])
        start = max(0, index - trail_frames * stride)
        for entity_index in range(trail_limit):
            _set_line(target_trails[entity_index], intruders[start : index + 1, entity_index])
            _set_line(
                resource_trails[entity_index],
                interceptors[start : index + 1, entity_index],
            )
        axis.set_title(
            f"3D point-mass episode | t={result.timestamps[index]:.2f}s | "
            f"active targets={int(np.count_nonzero(active))}"
        )
        return (
            target_scatter,
            resource_scatter,
            recon_scatter,
            *target_trails,
            *resource_trails,
        )

    movie = animation.FuncAnimation(
        figure,
        update,
        frames=len(frame_indices),
        interval=1_000.0 / fps,
        blit=False,
    )
    if path.suffix.lower() == ".gif":
        writer = animation.PillowWriter(fps=fps)
    else:
        if not animation.writers.is_available("ffmpeg"):
            plt.close(figure)
            raise RuntimeError("ffmpeg writer is unavailable; request GIF or install ffmpeg")
        writer = animation.FFMpegWriter(fps=fps, bitrate=1_800)
    movie.save(path, writer=writer, dpi=110)
    plt.close(figure)
    return path


def ensure_mplot3d(matplotlib_module: object) -> None:
    """Prefer the mpl_toolkits bundled with the active Matplotlib installation."""

    import importlib
    import mpl_toolkits

    package_root = Path(matplotlib_module.__file__).resolve().parent.parent
    bundled_toolkits = package_root / "mpl_toolkits"
    if bundled_toolkits.is_dir() and str(bundled_toolkits) not in mpl_toolkits.__path__:
        mpl_toolkits.__path__.insert(0, str(bundled_toolkits))
    try:
        importlib.import_module("mpl_toolkits.mplot3d")
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "the active Matplotlib installation does not provide a compatible mplot3d toolkit"
        ) from exc


def _ned_to_plot(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=float).copy()
    result[..., 2] *= -1.0
    return result


def _set_scatter(scatter: object, values: np.ndarray) -> None:
    points = np.asarray(values, dtype=float).reshape(-1, 3)
    scatter._offsets3d = (points[:, 0], points[:, 1], points[:, 2])


def _set_line(line: object, values: np.ndarray) -> None:
    points = np.asarray(values, dtype=float).reshape(-1, 3)
    line.set_data(points[:, 0], points[:, 1])
    line.set_3d_properties(points[:, 2])
