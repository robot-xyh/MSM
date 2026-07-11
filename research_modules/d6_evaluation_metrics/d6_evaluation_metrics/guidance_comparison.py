"""Same-seed offline comparison for D7 guidance-law experiments."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import statistics
from typing import Any, Iterable, Mapping

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .metrics import EpisodeMetrics


GUIDANCE_LAWS = ("pure_pursuit", "radar_pn", "png_vm", "png_ttc")
GUIDANCE_METRICS = (
    "intercept_success_rate",
    "intercept_abort_rate",
    "min_range_m",
    "time_to_intercept_s",
    "terminal_switch_allowed_rate",
    "terminal_takeover_rate",
    "gate_reject_per_target",
)
INTERCEPT_ABORT_STATUSES = {
    "abort",
    "aborted",
    "detection_timeout",
    "terminal_detection_timeout",
    "intercept_timeout",
    "timeout",
    "runtime_abort",
    "safety_abort",
}
INTERCEPT_SUCCESS_STATUSES = {"collision_intercept", "range_intercept"}


def compare_guidance_laws_same_seed(
    episodes: Iterable[EpisodeMetrics],
    *,
    reference_law: str = "radar_pn",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return paired per-seed rows and aggregate rows.

    Only episodes with an explicit experiment-level law are eligible. Runtime
    command-level mixed law counts are retained for audit but are not treated
    as an experiment selector.
    """

    if reference_law not in GUIDANCE_LAWS:
        raise ValueError(f"unsupported reference_law: {reference_law}")
    grouped: dict[tuple[Any, ...], dict[str, EpisodeMetrics]] = {}
    for episode in episodes:
        law = _episode_guidance_law(episode)
        if law not in GUIDANCE_LAWS or episode.seed is None:
            continue
        key = (
            episode.metric_scope,
            episode.scenario_group,
            _stable_scenario_version(episode.scenario_version),
            episode.seed,
            episode.drone_count,
            episode.resource_count,
            episode.target_count,
            episode.camera_count,
        )
        by_law = grouped.setdefault(key, {})
        if law in by_law:
            raise ValueError(
                "duplicate experiment guidance law for the same pairing key: "
                f"law={law}, episode={episode.episode_id}, "
                f"existing={by_law[law].episode_id}"
            )
        by_law[law] = episode

    paired_rows: list[dict[str, Any]] = []
    for key, by_law in sorted(grouped.items(), key=lambda item: str(item[0])):
        baseline = by_law.get(reference_law)
        if baseline is None:
            continue
        for candidate_law in GUIDANCE_LAWS:
            if candidate_law == reference_law:
                continue
            candidate = by_law.get(candidate_law)
            if candidate is None:
                continue
            for metric in GUIDANCE_METRICS:
                baseline_value = _guidance_metric_value(baseline, metric)
                candidate_value = _guidance_metric_value(candidate, metric)
                status = (
                    "available"
                    if baseline_value is not None and candidate_value is not None
                    else "unavailable"
                )
                paired_rows.append(
                    {
                        "metric_scope": key[0],
                        "scenario_group": key[1],
                        "scenario_version": key[2],
                        "seed": key[3],
                        "drone_count": key[4],
                        "resource_count": key[5],
                        "target_count": key[6],
                        "camera_count": key[7],
                        "reference_law": reference_law,
                        "candidate_law": candidate_law,
                        "metric": metric,
                        "status": status,
                        "reference_value": baseline_value,
                        "candidate_value": candidate_value,
                        "paired_delta": (
                            candidate_value - baseline_value
                            if status == "available"
                            else None
                        ),
                    }
                )

    aggregate_rows: list[dict[str, Any]] = []
    aggregate_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in paired_rows:
        key = (
            row["metric_scope"],
            row["scenario_group"],
            row["scenario_version"],
            row["drone_count"],
            row["resource_count"],
            row["target_count"],
            row["camera_count"],
            row["reference_law"],
            row["candidate_law"],
            row["metric"],
        )
        aggregate_groups.setdefault(key, []).append(row)
    for key, rows in sorted(aggregate_groups.items(), key=lambda item: str(item[0])):
        available = [row for row in rows if row["status"] == "available"]
        deltas = [float(row["paired_delta"]) for row in available]
        aggregate_rows.append(
            {
                "metric_scope": key[0],
                "scenario_group": key[1],
                "scenario_version": key[2],
                "drone_count": key[3],
                "resource_count": key[4],
                "target_count": key[5],
                "camera_count": key[6],
                "reference_law": key[7],
                "candidate_law": key[8],
                "metric": key[9],
                "pair_count": len(available),
                "paired_seeds": sorted(int(row["seed"]) for row in available),
                "status": "available" if available else "unavailable",
                "reference_mean": _mean_or_none(
                    [float(row["reference_value"]) for row in available]
                ),
                "candidate_mean": _mean_or_none(
                    [float(row["candidate_value"]) for row in available]
                ),
                "paired_delta_mean": _mean_or_none(deltas),
                "paired_delta_std": (
                    statistics.stdev(deltas) if len(deltas) > 1 else 0.0
                    if deltas
                    else None
                ),
            }
        )
    return paired_rows, aggregate_rows


class GuidanceLawComparisonReportGenerator:
    """Write CSV/JSON/Chinese Markdown and one paired-delta curve."""

    def write_bundle(
        self,
        episodes: Iterable[EpisodeMetrics],
        output_dir: str | Path,
        *,
        reference_law: str = "radar_pn",
    ) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        paired_rows, aggregate_rows = compare_guidance_laws_same_seed(
            episodes,
            reference_law=reference_law,
        )
        paired_csv = output_dir / "guidance_same_seed_pairs.csv"
        aggregate_csv = output_dir / "guidance_same_seed_summary.csv"
        json_path = output_dir / "guidance_same_seed_summary.json"
        markdown_path = output_dir / "guidance_same_seed_report.md"
        plot_path = output_dir / "guidance_same_seed_deltas.png"
        _write_csv(paired_csv, paired_rows)
        _write_csv(aggregate_csv, aggregate_rows)
        json_path.write_text(
            json.dumps(
                {
                    "schema_version": "d6-guidance-paired-v1",
                    "reference_law": reference_law,
                    "supported_laws": list(GUIDANCE_LAWS),
                    "paired_rows": paired_rows,
                    "aggregate_rows": aggregate_rows,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _write_markdown(markdown_path, aggregate_rows, reference_law)
        _write_plot(plot_path, paired_rows)
        return {
            "paired_csv": paired_csv,
            "aggregate_csv": aggregate_csv,
            "json": json_path,
            "markdown": markdown_path,
            "plot": plot_path,
        }


def _episode_guidance_law(episode: EpisodeMetrics) -> str | None:
    for key in ("experiment_guidance_law", "selected_guidance_law"):
        value = episode.metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip().lower()
    return None


def _guidance_metric_value(episode: EpisodeMetrics, metric: str) -> float | None:
    target_count = int(episode.target_count or 0)
    if metric == "intercept_success_rate":
        return episode.intercept_success_count / target_count if target_count else None
    if metric == "intercept_abort_rate":
        status_counts = episode.metadata.get("intercept_status_counts")
        if not isinstance(status_counts, Mapping) or target_count == 0:
            return None
        abort_count = sum(
            int(count)
            for status, count in status_counts.items()
            if str(status).lower() in INTERCEPT_ABORT_STATUSES
        )
        classified_count = abort_count + sum(
            int(count)
            for status, count in status_counts.items()
            if str(status).lower() in INTERCEPT_SUCCESS_STATUSES
        )
        return abort_count / target_count if classified_count == target_count else None
    if metric == "gate_reject_per_target":
        return episode.gate_reject_count / target_count if target_count else None
    value = getattr(episode, metric, None)
    return float(value) if value is not None else None


def _stable_scenario_version(value: str) -> str:
    parts = [
        part
        for part in str(value or "unversioned").split(":")
        if not re.fullmatch(r"seed\d+", part, flags=re.IGNORECASE)
        and not re.fullmatch(
            r"(?:law|guidance)(?:pure_pursuit|radar_pn|png_vm|png_ttc)",
            part,
            flags=re.IGNORECASE,
        )
    ]
    return ":".join(parts) or "unversioned"


def _mean_or_none(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0]) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(
    path: Path,
    rows: list[dict[str, Any]],
    reference_law: str,
) -> None:
    lines = [
        "# D7 四导引律同 Seed 配对报告",
        "",
        f"参考导引律为 `{reference_law}`。仅显式写出 experiment-level guidance law 且 seed/场景/规模一致的 episode 参与配对。",
        "",
        "| 候选导引律 | 指标 | 配对数 | 参考均值 | 候选均值 | 配对差值均值 | 状态 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {candidate_law} | {metric} | {pair_count} | {reference_mean} | {candidate_mean} | {paired_delta_mean} | {status} |".format(
                **{key: ("unavailable" if value is None else value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "![同 Seed 配对差值曲线](guidance_same_seed_deltas.png)",
            "",
            "D6 只消费执行日志；该报告不选择或切换导引律。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_plot(path: Path, rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.8))
    available = [row for row in rows if row["status"] == "available"]
    if not available:
        ax.text(0.5, 0.5, "unavailable", ha="center", va="center")
        ax.set_axis_off()
    else:
        grouped: dict[tuple[str, str], list[tuple[int, float]]] = {}
        for row in available:
            grouped.setdefault((row["candidate_law"], row["metric"]), []).append(
                (int(row["seed"]), float(row["paired_delta"]))
            )
        for (law, metric), points in sorted(grouped.items()):
            ordered = sorted(points)
            ax.plot(
                [point[0] for point in ordered],
                [point[1] for point in ordered],
                marker="o",
                label=f"{law}:{metric}",
            )
        ax.axhline(0.0, color="#333333", linewidth=1.0)
        ax.set_xlabel("Seed")
        ax.set_ylabel("Candidate - reference")
        ax.set_title("Guidance same-seed paired deltas")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
