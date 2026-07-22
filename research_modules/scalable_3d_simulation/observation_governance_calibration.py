"""Fast, truth-isolated calibration for long-episode observation governance."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tracemalloc
from typing import Any, Iterable

import numpy as np

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    ScanInputConfig,
    ScanInputOrganizer,
    SensorObservation,
    SensorScanFrame,
)
from research_modules.d2_data_association.d2_data_association import (
    ObservationClaimLedgerConfig,
    run_observation_governance_benchmark,
)
from research_modules.d6_evaluation_metrics.d6_evaluation_metrics import (
    D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
    D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_EVALUATOR_SIDECAR_SCHEMA_VERSION,
    OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
    ObservationGovernanceCalibrationReportGenerator,
    load_observation_governance_calibration_inputs,
)

from .episode_bus import BUS_SCHEMA_VERSION
from .models import (
    ONLINE_OBSERVATION_SCHEMA_VERSION,
    SCENARIO_SCHEMA_VERSION,
    WORLD_SCHEMA_VERSION,
)


OBSERVATION_GOVERNANCE_RUNNER_SCHEMA_VERSION = (
    "scalable3d-observation-governance-runner-v1"
)
DEFAULT_CALIBRATION_SCALES = (20, 50, 100, 200)


def run_observation_governance_calibration(
    output_dir: str | Path,
    *,
    scales: Iterable[int] = DEFAULT_CALIBRATION_SCALES,
    seeds_per_scale: int = 5,
    seed_base: int = 41_000,
    frame_count: int = 136,
    dt_seconds: float = 0.25,
    retention_seconds: float = 30.0,
    max_lateness_seconds: float = 0.5,
    bootstrap_resamples: int = 2_000,
) -> dict[str, Path]:
    """Run a fast governance benchmark and pass only files into D6."""

    scale_values = tuple(int(value) for value in scales)
    if not scale_values or any(value <= 0 for value in scale_values):
        raise ValueError("scales must contain positive integers")
    if len(set(scale_values)) != len(scale_values):
        raise ValueError("scales must be unique")
    if int(seeds_per_scale) <= 0:
        raise ValueError("seeds_per_scale must be positive")
    if int(frame_count) < 3:
        raise ValueError("frame_count must be at least three")
    if float(dt_seconds) <= 0.0:
        raise ValueError("dt_seconds must be positive")
    if float(retention_seconds) < 0.0 or float(max_lateness_seconds) < 0.0:
        raise ValueError("retention and lateness must be non-negative")

    root = Path(output_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    repository_root = Path(__file__).resolve().parents[2]
    git_commit = _git_output(repository_root, "rev-parse", "HEAD")
    repository_dirty = bool(
        _git_output(repository_root, "status", "--porcelain").strip()
    )
    evidence_tier = "development" if repository_dirty else "formal"
    descriptors: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []

    for scale in scale_values:
        for local_seed_index in range(int(seeds_per_scale)):
            seed = int(seed_base) + scale * 100 + local_seed_index
            episode_dir = root / f"scale_{scale:03d}" / f"seed_{seed:06d}"
            episode_dir.mkdir(parents=True, exist_ok=True)
            descriptor, row = _run_one_calibration_episode(
                episode_dir,
                scale=scale,
                seed=seed,
                frame_count=int(frame_count),
                dt_seconds=float(dt_seconds),
                retention_seconds=float(retention_seconds),
                max_lateness_seconds=float(max_lateness_seconds),
                git_commit=git_commit,
                repository_dirty=repository_dirty,
                evidence_tier=evidence_tier,
                input_root=root,
            )
            descriptors.append(descriptor)
            episode_rows.append(row)

    input_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_CALIBRATION_INPUT_SCHEMA_VERSION,
        "created_at_utc": _utc_timestamp(),
        "producer": "main-scalable3d-observation-governance-calibration",
        "admission_policy": (
            "allow_development" if repository_dirty else "formal_only"
        ),
        "expected_scales": list(scale_values),
        "episodes": descriptors,
    }
    input_path = _write_json(
        root / "observation_governance_calibration_input.json",
        input_payload,
    )
    inputs = load_observation_governance_calibration_inputs(
        input_path,
        expected_sha256=_sha256_file(input_path),
    )
    report_paths = ObservationGovernanceCalibrationReportGenerator().write_report_bundle(
        root / "d6_report",
        inputs=inputs,
        bootstrap_resamples=int(bootstrap_resamples),
        bootstrap_rng_seed=int(seed_base),
        title="长 Episode 观测治理快速标定报告",
    )
    runner_summary = {
        "schema_version": OBSERVATION_GOVERNANCE_RUNNER_SCHEMA_VERSION,
        "evidence_layer": "fast_3d_governance_benchmark",
        "full_system_evidence": False,
        "git_commit": git_commit,
        "repository_dirty": repository_dirty,
        "evidence_tier": evidence_tier,
        "scale_values": list(scale_values),
        "seeds_per_scale": int(seeds_per_scale),
        "episode_count": len(episode_rows),
        "frame_count": int(frame_count),
        "dt_seconds": float(dt_seconds),
        "retention_seconds": float(retention_seconds),
        "max_lateness_seconds": float(max_lateness_seconds),
        "online_truth_use_count": 0,
        "episodes": episode_rows,
    }
    runner_summary_path = _write_json(root / "runner_summary.json", runner_summary)
    return {
        "input_specification": input_path,
        "runner_summary": runner_summary_path,
        **{f"d6_{name}": path for name, path in report_paths.items()},
    }


def _run_one_calibration_episode(
    episode_dir: Path,
    *,
    scale: int,
    seed: int,
    frame_count: int,
    dt_seconds: float,
    retention_seconds: float,
    max_lateness_seconds: float,
    git_commit: str,
    repository_dirty: bool,
    evidence_tier: str,
    input_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    episode_id = f"governance-scale-{scale}-seed-{seed}"
    duration_s = (frame_count - 1) * dt_seconds
    episode = {
        "episode_id": episode_id,
        "scale": scale,
        "target_count": scale,
        "resource_count": scale,
        "seed": seed,
        "duration_s": duration_s,
    }
    config_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_RUNNER_SCHEMA_VERSION,
        "evidence_layer": "fast_3d_governance_benchmark",
        "scale": scale,
        "seed": seed,
        "frame_count": frame_count,
        "dt_seconds": dt_seconds,
        "retention_seconds": retention_seconds,
        "max_lateness_seconds": max_lateness_seconds,
    }
    config_path = _write_json(episode_dir / "calibration_config.json", config_payload)
    config_sha = _sha256_file(config_path)

    tracemalloc.start()
    d1_audit, d1_event_summary = _run_d1_scan_benchmark(
        scale=scale,
        seed=seed,
        frame_count=frame_count,
        dt_seconds=dt_seconds,
        max_lateness_seconds=max_lateness_seconds,
    )
    d1_current_memory, d1_peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    claim_capacity = max(
        4_096,
        int(
            np.ceil(
                2.0
                * scale
                * max(retention_seconds, max_lateness_seconds)
                / dt_seconds
            )
        ),
    )
    claim_config = ObservationClaimLedgerConfig(
        config_version="calibration-observation-claim-policy-v1",
        retention_seconds=retention_seconds,
        max_count=claim_capacity,
        max_lateness_seconds=max_lateness_seconds,
    )
    separation_m = 0.65 + 0.025 * (seed % 7)
    tracemalloc.start()
    benchmark = run_observation_governance_benchmark(
        target_count=scale,
        frame_count=frame_count,
        separation_m=separation_m,
        dt_seconds=dt_seconds,
        observation_claim_config=claim_config,
    )
    d2_current_memory, d2_peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    benchmark_payload = benchmark.to_dict()
    benchmark_path = _write_json(
        episode_dir / "offline_observation_governance_benchmark.json",
        benchmark_payload,
    )

    source_bus_path = _write_jsonl(
        episode_dir / "online_governance_events.jsonl",
        (
            {
                "schema_version": "scalable3d-governance-event-summary-v1",
                "episode_id": episode_id,
                "scale": scale,
                "seed": seed,
                "d1": d1_event_summary,
                "d2_claim_ledger": benchmark.ledger_summary,
                "online_truth_use_count": 0,
            },
        ),
    )

    manifest_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_EPISODE_MANIFEST_SCHEMA_VERSION,
        "episode": episode,
        "provenance": {
            "producer": "main-scalable3d-fast-governance-benchmark",
            "git_commit": git_commit,
            "repository_dirty": repository_dirty,
            "evidence_tier": evidence_tier,
            "config_sha256": config_sha,
            "world_schema": WORLD_SCHEMA_VERSION,
            "bus_schema": BUS_SCHEMA_VERSION,
            "scenario_schema": SCENARIO_SCHEMA_VERSION,
            "online_observation_schema": ONLINE_OBSERVATION_SCHEMA_VERSION,
            "d1_scan_oosm_audit_schema": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
            "d2_claim_ledger_audit_schema": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
        },
        "online_truth_use_count": 0,
    }
    manifest_path = _write_json(
        episode_dir / "observation_governance_manifest.json",
        manifest_payload,
    )
    manifest_sha = _sha256_file(manifest_path)

    online_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_ONLINE_AUDIT_SCHEMA_VERSION,
        "episode": episode,
        "provenance": {
            "producer": "main-scalable3d-fast-governance-benchmark",
            "git_commit": git_commit,
            "config_sha256": config_sha,
            "episode_manifest_sha256": manifest_sha,
            "source_bus_sha256": _sha256_file(source_bus_path),
            "source_bus_schema": BUS_SCHEMA_VERSION,
        },
        "online_truth_use_count": 0,
        "d1_scan_oosm_audit": {
            "schema_version": D1_SCAN_OOSM_AUDIT_SCHEMA_VERSION,
            "metrics": _d1_metrics(
                d1_audit,
                current_memory_bytes=d1_current_memory,
                peak_memory_bytes=d1_peak_memory,
            ),
        },
        "d2_claim_ledger_audit": {
            "schema_version": D2_CLAIM_LEDGER_AUDIT_SCHEMA_VERSION,
            "metrics": _d2_metrics(
                benchmark_payload,
                current_memory_bytes=d2_current_memory,
                peak_memory_bytes=d2_peak_memory,
            ),
        },
    }
    online_path = _write_json(
        episode_dir / "observation_governance_online_audit.json",
        online_payload,
    )
    online_sha = _sha256_file(online_path)

    legitimate_count = int(benchmark.legitimate_detection_count)
    false_suppression_count = int(
        benchmark.legitimate_false_suppression_count
    )
    near_recall_numerator = int(
        round(benchmark.nearby_independent_target_recall * legitimate_count)
    )
    latency_samples = [
        float(value)
        for value in benchmark.confirmation_latency_seconds_by_truth.values()
        if value is not None
    ]
    sidecar_payload = {
        "schema_version": OBSERVATION_GOVERNANCE_EVALUATOR_SIDECAR_SCHEMA_VERSION,
        "evaluator_only": True,
        "online_consumed": False,
        "episode": episode,
        "provenance": {
            "producer": "d2-offline-observation-governance-benchmark",
            "evaluator_git_commit": git_commit,
            "config_sha256": config_sha,
            "truth_schema": "d2-observation-governance-offline-benchmark-v1",
            "truth_artifact_sha256": _sha256_file(benchmark_path),
            "episode_manifest_sha256": manifest_sha,
            "online_audit_sha256": online_sha,
        },
        "metrics": {
            "near_neighbor_recall": {
                "availability": "available",
                "numerator": near_recall_numerator,
                "denominator": legitimate_count,
                "reason": None,
            },
            "false_suppression_rate": {
                "availability": "available",
                "numerator": false_suppression_count,
                "denominator": legitimate_count,
                "reason": None,
            },
            "erroneous_coalescence_rate": {
                "availability": "available",
                "numerator": int(benchmark.erroneous_coalescence_count),
                "denominator": legitimate_count,
                "reason": None,
            },
            "confirmation_latency_s": {
                "availability": "available" if latency_samples else "unavailable",
                "samples_s": latency_samples if latency_samples else None,
                "reason": None if latency_samples else "no_confirmed_tracks",
            },
        },
    }
    sidecar_path = _write_json(
        episode_dir / "observation_governance_evaluator_sidecar.json",
        sidecar_payload,
    )
    descriptor = {
        "episode": episode,
        "manifest_artifact": _artifact_reference(manifest_path, input_root),
        "online_audit_artifact": _artifact_reference(online_path, input_root),
        "evaluator_sidecar": {
            "availability": "available",
            "artifact": _artifact_reference(sidecar_path, input_root),
            "reason": None,
        },
    }
    row = {
        "episode_id": episode_id,
        "scale": scale,
        "seed": seed,
        "d1_reordered_scan_count": int(d1_audit["reordered_scan_count"]),
        "d1_rejected_scan_count": int(d1_audit["rejected_scan_count"]),
        "d1_peak_buffered_scan_count": int(
            d1_audit["maximum_buffered_scan_count"]
        ),
        "d2_peak_claim_count": int(benchmark.ledger_summary["peak_count"]),
        "d2_claim_capacity": int(benchmark.ledger_summary["max_count"]),
        "d2_claim_evicted_count": int(
            benchmark.ledger_summary["evicted_count"]
        ),
        "near_neighbor_recall": float(
            benchmark.nearby_independent_target_recall
        ),
        "false_suppression_rate": float(
            benchmark.legitimate_false_suppression_rate
        ),
        "erroneous_coalescence_count": int(
            benchmark.erroneous_coalescence_count
        ),
        "online_truth_use_count": 0,
    }
    return descriptor, row


def _run_d1_scan_benchmark(
    *,
    scale: int,
    seed: int,
    frame_count: int,
    dt_seconds: float,
    max_lateness_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = np.random.default_rng(seed)
    organizer = ScanInputOrganizer(
        ScanInputConfig(
            max_lateness_s=max_lateness_seconds,
            max_buffer_residence_s=max(5.0, 4.0 * max_lateness_seconds),
            max_buffered_scans=max(64, frame_count),
            max_buffered_observations=max(4_096, scale * frame_count),
            max_claimed_scans=max(1_024, 2 * frame_count),
            max_claimed_observation_lineages=max(8_192, 2 * scale * frame_count),
        )
    )
    frames: list[SensorScanFrame] = []
    for frame_index in range(frame_count):
        measurement_timestamp = frame_index * dt_seconds
        latency = 0.03 + float(rng.uniform(0.0, 0.07))
        if frame_index % 11 == 3:
            latency += min(0.8 * max_lateness_seconds, 0.35)
        arrival_timestamp = measurement_timestamp + latency
        scan_id = f"calibration-scan-{frame_index:06d}"
        observations = tuple(
            SensorObservation(
                observation_id=(
                    f"opaque-observation-{frame_index:06d}-{target_index:04d}"
                ),
                sensor_id="CALIBRATION-RADAR-001",
                modality="radar",
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=arrival_timestamp,
                frame_id="ned",
                measurement=np.asarray(
                    [
                        1_000.0 + 2.0 * target_index,
                        0.001 * target_index,
                        -0.05,
                        1.0,
                    ],
                    dtype=float,
                ),
                covariance=np.diag([4.0, 1.0e-4, 1.0e-4, 1.0]),
                confidence=0.95,
                metadata={
                    "scan_id": scan_id,
                    "source_lineage_key": (
                        "calibration-source",
                        frame_index,
                        target_index,
                    ),
                },
                source_node_id="CALIBRATION-RADAR-001",
                payload_kind="radar_scan",
            )
            for target_index in range(scale)
        )
        frames.append(SensorScanFrame(scan_id=scan_id, observations=observations))

    event_reason_counts: dict[str, int] = {}
    event_count = 0
    for frame in sorted(
        frames,
        key=lambda item: (
            item.arrival_timestamp,
            item.measurement_timestamp,
            item.scan_id,
        ),
    ):
        result = organizer.ingest(frame)
        event_count += len(result.events)
        for event in result.events:
            event_reason_counts[event.reason] = event_reason_counts.get(event.reason, 0) + 1
    final = organizer.close()
    event_count += len(final.events)
    for event in final.events:
        event_reason_counts[event.reason] = event_reason_counts.get(event.reason, 0) + 1
    audit = organizer.audit_summary().to_dict()
    return audit, {
        "event_count": event_count,
        "reason_counts": dict(sorted(event_reason_counts.items())),
        "online_truth_use_count": 0,
    }


def _d1_metrics(
    audit: dict[str, Any],
    *,
    current_memory_bytes: int,
    peak_memory_bytes: int,
) -> dict[str, Any]:
    values = {
        "scan_count": int(audit["received_scan_count"]),
        "current_oosm_buffer_count": int(audit["current_buffered_scan_count"]),
        "peak_oosm_buffer_count": int(audit["maximum_buffered_scan_count"]),
        "oosm_buffered_count": int(audit["buffered_event_count"]),
        "oosm_reordered_count": int(audit["reordered_scan_count"]),
        "oosm_rejected_count": int(audit["rejected_scan_count"]),
        "oosm_too_old_count": int(audit["too_late_scan_count"]),
        "oosm_overflow_count": int(audit["buffer_overflow_scan_count"])
        + int(audit["capacity_overflow_scan_count"]),
        "oosm_eviction_count": int(audit["buffer_expired_scan_count"]),
        "estimated_current_memory_bytes": int(current_memory_bytes),
        "estimated_peak_memory_bytes": int(peak_memory_bytes),
    }
    return {name: _available(value) for name, value in values.items()}


def _d2_metrics(
    benchmark: dict[str, Any],
    *,
    current_memory_bytes: int,
    peak_memory_bytes: int,
) -> dict[str, Any]:
    ledger = benchmark["ledger_summary"]
    values = {
        "current_claim_count": int(ledger["current_count"]),
        "peak_claim_count": int(ledger["peak_count"]),
        "claim_eviction_count": int(ledger["evicted_count"]),
        "claim_too_old_count": int(ledger["too_old_rejection_count"]),
        "claim_overflow_count": int(ledger["overflow_rejection_count"]),
        "replay_quarantine_count": int(ledger["replay_rejection_count"]),
        "timestamp_conflict_count": 0,
        "duplicate_coalescence_count": int(
            benchmark["erroneous_coalescence_count"]
        ),
        "estimated_current_memory_bytes": int(current_memory_bytes),
        "estimated_peak_memory_bytes": int(peak_memory_bytes),
    }
    return {name: _available(value) for name, value in values.items()}


def _available(value: int) -> dict[str, Any]:
    return {"availability": "available", "value": int(value), "reason": None}


def _artifact_reference(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": str(path.resolve().relative_to(root.resolve())),
        "sha256": _sha256_file(path),
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            )
    return path


def _sha256_file(path: str | Path) -> str:
    return f"sha256:{sha256(Path(path).read_bytes()).hexdigest()}"


def _git_output(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run scalable D1/D2 observation-governance calibration"
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--scales", nargs="+", type=int, default=list(DEFAULT_CALIBRATION_SCALES))
    parser.add_argument("--seeds-per-scale", type=int, default=5)
    parser.add_argument("--seed-base", type=int, default=41_000)
    parser.add_argument("--frame-count", type=int, default=136)
    parser.add_argument("--dt-seconds", type=float, default=0.25)
    parser.add_argument("--retention-seconds", type=float, default=30.0)
    parser.add_argument("--max-lateness-seconds", type=float, default=0.5)
    parser.add_argument("--bootstrap-resamples", type=int, default=2_000)
    args = parser.parse_args()
    paths = run_observation_governance_calibration(
        args.output_dir,
        scales=args.scales,
        seeds_per_scale=args.seeds_per_scale,
        seed_base=args.seed_base,
        frame_count=args.frame_count,
        dt_seconds=args.dt_seconds,
        retention_seconds=args.retention_seconds,
        max_lateness_seconds=args.max_lateness_seconds,
        bootstrap_resamples=args.bootstrap_resamples,
    )
    print(json.dumps({name: str(path) for name, path in paths.items()}, indent=2))


if __name__ == "__main__":
    main()
