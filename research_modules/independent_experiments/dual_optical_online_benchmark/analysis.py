"""Post-test diagnostics that never alter a frozen route or publication."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np

from .contracts import benchmark_protocol_from_mapping, read_snapshot, write_json


ROUTE_LABELS = {
    "epipolar_mht": "Enhanced geometry",
    "lightweight": "Lightweight",
    "gnn": "Graph network",
    "track_superglue": "Track SuperGlue",
}
ROUTE_COLORS = {
    "epipolar_mht": "#5f6b7a",
    "lightweight": "#2e7d32",
    "gnn": "#1565c0",
    "track_superglue": "#8e5a2b",
}
ROUTE_ORDER = tuple(ROUTE_LABELS)


def _read_mapping(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _resolve_active_routes(
    metrics: Mapping[str, Any],
    freeze_marker: Mapping[str, Any],
) -> tuple[str, ...]:
    """Resolve evaluated routes without reviving a validation elimination."""

    metrics_routes = metrics.get("active_routes")
    marker_routes = freeze_marker.get("active_routes")
    if metrics_routes is not None and marker_routes is not None:
        if tuple(metrics_routes) != tuple(marker_routes):
            raise ValueError("metrics and freeze marker active routes differ")
    raw_routes = metrics_routes if metrics_routes is not None else marker_routes
    aggregate = metrics.get("aggregate", {}).get("routes", {})
    if raw_routes is None:
        # Compatibility for sealed v1-v3 evidence written before active_routes.
        routes = tuple(route for route in ROUTE_ORDER if route in aggregate)
    else:
        routes = tuple(str(route) for route in raw_routes)
    if (
        not routes
        or len(routes) != len(set(routes))
        or any(route not in ROUTE_LABELS for route in routes)
    ):
        raise ValueError("comparison metrics contain an invalid active-route set")
    missing = [route for route in routes if route not in aggregate]
    if missing:
        raise ValueError(f"active routes missing aggregate metrics: {missing}")
    return routes


def _eliminated_route_facts(
    freeze_marker: Mapping[str, Any],
    active_routes: Sequence[str],
) -> dict[str, dict[str, str]]:
    """Copy only marker-level elimination facts, never route validation data."""

    raw = freeze_marker.get("eliminated_routes", {})
    if not isinstance(raw, Mapping):
        return {}
    facts: dict[str, dict[str, str]] = {}
    for route in ROUTE_ORDER:
        item = raw.get(route)
        if route in active_routes or not isinstance(item, Mapping):
            continue
        if item.get("status") not in {
            "eliminated_on_validation",
            "eliminated_on_main_validation_gate",
        }:
            continue
        facts[route] = {
            "status": "eliminated_on_validation",
            "reason_code": str(item.get("reason_code") or "validation_rejected"),
        }
    return facts


def _mean_route_level(
    rows: Sequence[Mapping[str, Any]],
    route: str,
    level: str,
) -> float:
    values = [
        float(row["f1"])
        for row in rows
        if row["route_name"] == route and row["corruption_level"] == level
    ]
    return float(np.mean(values)) if values else 0.0


def _write_route_comparison_figure(
    metrics: Mapping[str, Any],
    corruption_levels: Sequence[str],
    active_routes: Sequence[str],
    figure_dir: Path,
) -> Path:
    """Render a centered comparison for any nonempty subset of routes."""

    routes = tuple(active_routes)
    aggregate = metrics["aggregate"]["routes"]
    result_rows = metrics["rows"]
    comparison, axes = plt.subplots(1, 3, figsize=(15.2, 4.6))
    labels = [ROUTE_LABELS[route] for route in routes]
    colors = [ROUTE_COLORS[route] for route in routes]
    axes[0].bar(
        labels,
        [float(aggregate[route]["macro_f1"]) for route in routes],
        color=colors,
        width=min(0.72, 0.42 + 0.08 * len(routes)),
    )
    axes[0].set(title="Held-out macro F1", ylabel="F1")
    axes[0].tick_params(axis="x", rotation=18)

    levels = tuple(corruption_levels)
    x = np.arange(len(levels), dtype=float)
    width = min(0.56, 0.72 / len(routes))
    center = 0.5 * (len(routes) - 1)
    for index, route in enumerate(routes):
        axes[1].bar(
            x + (index - center) * width,
            [
                _mean_route_level(result_rows, route, level)
                for level in levels
            ],
            width=width,
            color=ROUTE_COLORS[route],
            label=ROUTE_LABELS[route],
        )
    axes[1].set(
        title="F1 by corruption level",
        ylabel="F1",
        xticks=x,
        xticklabels=[level.title() for level in levels],
    )
    axes[1].legend(fontsize=8)

    axes[2].bar(
        labels,
        [float(aggregate[route]["latency_p95_ms"]) for route in routes],
        color=colors,
        width=min(0.72, 0.42 + 0.08 * len(routes)),
    )
    axes[2].axhline(1000.0, color="#c62828", linestyle="--", linewidth=1.2)
    axes[2].set(title="Held-out P95 latency", ylabel="Milliseconds")
    axes[2].tick_params(axis="x", rotation=18)
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    comparison.tight_layout()
    output_path = figure_dir / "02_route_test_comparison.png"
    comparison.savefig(output_path, dpi=180)
    plt.close(comparison)
    return output_path


def _dominant(counts: dict[str, int]) -> str | None:
    ranked = sorted(((int(value), key) for key, value in counts.items()), reverse=True)
    if not ranked or ranked[0][1].startswith("FA-"):
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def generate_diagnostics(metrics_path: str | Path) -> tuple[Path, Path]:
    metrics_path = Path(metrics_path).resolve()
    metrics = _read_mapping(metrics_path)
    freeze_marker = _read_mapping(metrics["freeze_marker"])
    active_routes = _resolve_active_routes(metrics, freeze_marker)
    protocol = benchmark_protocol_from_mapping(metrics["protocol"])
    manifest_path = Path(metrics["test_manifest"])
    manifest = _read_mapping(manifest_path)
    root = manifest_path.parent
    rows: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        snapshot = read_snapshot(root / entry["snapshot_path"])
        labels = json.loads((root / entry["label_path"]).read_text(encoding="utf-8"))
        dominant = {
            track_id: _dominant(counts)
            for track_id, counts in labels["track_truth_counts"].items()
        }
        camera_a, camera_b = snapshot.camera_ids
        stable = {
            camera_id: [
                track for track in snapshot.tracks[camera_id]
                if len({sample.sweep_index for sample in track.samples}) >= 4
            ]
            for camera_id in snapshot.camera_ids
        }
        identities = {
            camera_id: {
                dominant[track.track_id]
                for track in stable[camera_id]
                if dominant.get(track.track_id) is not None
            }
            for camera_id in snapshot.camera_ids
        }
        rows.append({
            "seed": snapshot.seed,
            "corruption_level": snapshot.corruption_level,
            "revolution_index": snapshot.revolution_index,
            "track_count_a": len(snapshot.tracks[camera_a]),
            "track_count_b": len(snapshot.tracks[camera_b]),
            "stable_track_count_a": len(stable[camera_a]),
            "stable_track_count_b": len(stable[camera_b]),
            "stable_common_truth_count": len(identities[camera_a] & identities[camera_b]),
        })
    summary: dict[str, Any] = {"by_corruption_and_revolution": []}
    for level in protocol.corruption_levels:
        for revolution in range(1, 7):
            selected = [
                row for row in rows
                if row["corruption_level"] == level
                and row["revolution_index"] == revolution
            ]
            summary["by_corruption_and_revolution"].append({
                "corruption_level": level,
                "revolution_index": revolution,
                **{
                    name: float(np.mean([row[name] for row in selected]))
                    for name in (
                        "track_count_a", "track_count_b", "stable_track_count_a",
                        "stable_track_count_b", "stable_common_truth_count",
                    )
                },
            })
    active_rows = [
        row for row in metrics["rows"] if row["route_name"] in active_routes
    ]
    summary["active_routes"] = list(active_routes)
    summary["eliminated_routes"] = _eliminated_route_facts(
        freeze_marker, active_routes
    )
    summary["route_availability"] = {
        route: dict(Counter(
            row["availability"]
            for row in metrics["rows"] if row["route_name"] == route
        ))
        for route in active_routes
    }
    summary["all_routes_zero_match"] = all(
        row["match_count"] == 0 for row in active_rows
    )
    summary_path = metrics_path.parent / "failure_diagnostics.json"
    write_json(summary_path, summary)

    figure_dir = metrics_path.parent / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure_path = figure_dir / "01_failure_diagnostics.png"
    figure, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    colors = {
        "clean": "#1565c0",
        "light": "#2e7d32",
        "medium": "#ed6c02",
        "heavy": "#c62828",
    }
    colors = {level: colors[level] for level in protocol.corruption_levels}
    for level in colors:
        values = [
            item for item in summary["by_corruption_and_revolution"]
            if item["corruption_level"] == level
        ]
        axes[0].plot(
            [item["revolution_index"] for item in values],
            [0.5 * (item["track_count_a"] + item["track_count_b"]) for item in values],
            marker="o", color=colors[level], label=level,
        )
        axes[1].plot(
            [item["revolution_index"] for item in values],
            [item["stable_common_truth_count"] for item in values],
            marker="o", color=colors[level], label=level,
        )
    axes[0].axhline(
        protocol.target_count,
        color="#555555",
        linestyle="--",
        linewidth=1,
    )
    axes[0].set(title="Local track fragmentation", xlabel="Revolution", ylabel="Mean tracks per camera")
    axes[1].set(title="Stable common target identities", xlabel="Revolution", ylabel="Mean target count")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
        axis.set_xticks(range(1, 7))
    figure.tight_layout()
    figure.savefig(figure_path, dpi=180)
    plt.close(figure)

    _write_route_comparison_figure(
        metrics,
        protocol.corruption_levels,
        active_routes,
        figure_dir,
    )
    return summary_path, figure_path
