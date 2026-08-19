"""Resumable main-owned AirSim episode generation for the frozen benchmark."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

from dual_optical_40target.core import CameraSpec
from dual_optical_40target.runtime import LocalBlocksProcess, write_airsim_settings

from .contracts import BenchmarkProtocol, write_json
from .dataset import (
    materialize_episode,
    sha256_file,
    split_for_seed,
    validate_raw_episode,
    write_dataset_manifest,
)
from .episode_worker import WORKER_PROTOCOL_SCHEMA, build_config
from .orchestrator import validate_freeze_marker
from .tracker_calibration import calibrate_and_freeze_tracker
from .tracker_calibration import (
    evaluate_prepared_tracker_episode,
    evaluate_tracker_episode,
    prepare_tracker_episode,
)
from .tracking import SharedTrackerConfig, load_tracker_freeze
from .tracker_calibration import tracker_config_for_protocol


BATCH_SCHEMA_VERSION = "dual-optical-online-batch-v2"
RAW_CALIBRATION_SCHEMA_VERSION = "dual-optical-raw-calibration-manifest-v1"
PREFLIGHT_SCHEMA_VERSION = "dual-optical-online-preflight-v1"
PREFLIGHT_SCENARIOS = (
    ("ideal", False, "none"),
    ("pose_error", True, "none"),
    ("full_interference", True, "heavy"),
)
PREFLIGHT_SEEDS = (20270001, 20270002, 20270003)
PREFLIGHT_ACCEPTANCE = {
    "median_track_purity": 0.85,
    "ideal_common_confirmed_rate": 0.70,
    "pose_error_common_confirmed_rate": 0.65,
    "full_interference_common_confirmed_rate": 0.50,
}
PREFLIGHT_TRACKER_CANDIDATES = (
    SharedTrackerConfig(),
    SharedTrackerConfig(
        motion_initialization_residual_gate_m=3.0,
        maximum_global_hypotheses=1,
    ),
    SharedTrackerConfig(
        motion_initialization_residual_gate_m=3.0,
        maximum_global_hypotheses=3,
    ),
    SharedTrackerConfig(
        motion_initialization_residual_gate_m=5.0,
        maximum_global_hypotheses=1,
    ),
)


def _preflight_tracker_candidates(
    protocol: BenchmarkProtocol,
) -> tuple[SharedTrackerConfig, ...]:
    if not protocol.is_legacy_continuous_profile:
        return (tracker_config_for_protocol(protocol),)
    return PREFLIGHT_TRACKER_CANDIDATES


def _rpc_ready(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_rpc(port: int, process: LocalBlocksProcess, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _rpc_ready(port):
            return
        if process.process is not None and process.process.poll() is not None:
            raise RuntimeError("Blocks exited before opening the AirSim RPC port")
        time.sleep(0.5)
    raise TimeoutError("AirSim RPC port did not become ready")


def _receipt_path(episode_dir: Path) -> Path:
    return episode_dir / "benchmark_episode_receipt.json"


def _load_reusable_receipt(
    episode_dir: Path, protocol: BenchmarkProtocol, seed: int
) -> dict[str, Any] | None:
    receipt_path = _receipt_path(episode_dir)
    if not receipt_path.is_file():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        validation = validate_raw_episode(episode_dir, protocol, expected_seed=seed)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None
    if receipt.get("schema_version") != BATCH_SCHEMA_VERSION:
        return None
    if receipt.get("protocol_fingerprint") != protocol.fingerprint:
        return None
    if receipt.get("raw_hashes") != validation["files"]:
        return None
    return receipt


def _run_worker(
    repo_root: Path,
    episode_dir: Path,
    seed: int,
    api_port: int,
    timeout_s: float,
    *,
    gimbal_pose_error_enabled: bool = True,
    protocol: BenchmarkProtocol | None = None,
) -> dict[str, Any]:
    protocol = protocol or BenchmarkProtocol()
    # A resumed episode must not retain a stale failure marker from the prior
    # attempt; the launch log remains archived by the main preflight runner.
    (episode_dir / "failure.json").unlink(missing_ok=True)
    protocol_path = episode_dir / "worker_protocol.json"
    write_json(
        protocol_path,
        {
            "schema_version": WORKER_PROTOCOL_SCHEMA,
            "protocol": asdict(protocol),
            "protocol_fingerprint": protocol.fingerprint,
        },
    )
    command = [
        sys.executable,
        "-m",
        "dual_optical_online_benchmark.episode_worker",
        "--seed",
        str(seed),
        "--output-dir",
        str(episode_dir),
        "--api-port",
        str(api_port),
        "--target-count",
        str(protocol.target_count),
        "--protocol-file",
        str(protocol_path),
    ]
    if not gimbal_pose_error_enabled:
        command.append("--disable-gimbal-pose-error")
    environment = os.environ.copy()
    package_root = repo_root / "research_modules" / "independent_experiments"
    environment["PYTHONPATH"] = str(package_root) + os.pathsep + environment.get("PYTHONPATH", "")
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_s,
            check=False,
        )
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        result = None
        timed_out = True
        output = (exc.stdout or "") + "\n[timeout]\n"
    else:
        output = result.stdout
    log_path = episode_dir / "main_episode_worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return {
        "returncode": None if result is None else result.returncode,
        "timed_out": timed_out,
        "wall_duration_s": time.perf_counter() - started,
        "log": log_path.name,
    }


def _reset_client(api_port: int) -> None:
    import airsim

    client = airsim.VehicleClient(port=api_port, timeout_value=10)
    client.simPause(False)
    client.reset()
    time.sleep(1.0)


def _preflight_config(
    seed: int,
    api_port: int,
    gimbal_enabled: bool,
    protocol: BenchmarkProtocol | None = None,
):
    return build_config(
        seed,
        api_port,
        gimbal_pose_error_enabled=gimbal_enabled,
        protocol=protocol,
    )


def _preflight_acceptance(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    by_scenario: dict[str, dict[str, float | int]] = {}
    for scenario, _, _ in PREFLIGHT_SCENARIOS:
        selected = [row for row in rows if row["diagnostic_scenario"] == scenario]
        by_scenario[scenario] = {
            "episode_count": len(selected),
            "median_track_purity": float(
                sorted(float(row["median_track_purity"]) for row in selected)[
                    len(selected) // 2
                ]
            ) if selected else 0.0,
            "mean_common_confirmed_rate": sum(
                float(row["common_confirmed_rate"]) for row in selected
            ) / max(len(selected), 1),
            "mean_common_confirmed_identity_count": sum(
                int(row["common_confirmed_identity_count"]) for row in selected
            ) / max(len(selected), 1),
        }
    checks = {
        "complete_nine_episode_matrix": all(
            int(by_scenario[name]["episode_count"]) == len(PREFLIGHT_SEEDS)
            for name, _, _ in PREFLIGHT_SCENARIOS
        ),
        "median_track_purity": min(
            float(values["median_track_purity"])
            for values in by_scenario.values()
        ) >= PREFLIGHT_ACCEPTANCE["median_track_purity"],
        "ideal_common_confirmed_rate": float(
            by_scenario["ideal"]["mean_common_confirmed_rate"]
        ) >= PREFLIGHT_ACCEPTANCE["ideal_common_confirmed_rate"],
        "pose_error_common_confirmed_rate": float(
            by_scenario["pose_error"]["mean_common_confirmed_rate"]
        ) >= PREFLIGHT_ACCEPTANCE["pose_error_common_confirmed_rate"],
        "full_interference_common_confirmed_rate": float(
            by_scenario["full_interference"]["mean_common_confirmed_rate"]
        ) >= PREFLIGHT_ACCEPTANCE["full_interference_common_confirmed_rate"],
    }
    return {
        "accepted": all(checks.values()),
        "thresholds": dict(PREFLIGHT_ACCEPTANCE),
        "checks": checks,
        "failure_reasons": [name for name, passed in checks.items() if not passed],
        "by_scenario": by_scenario,
    }


def _preflight_selection_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    """Prefer the simplest contamination-safe structure after acceptance."""

    acceptance = candidate["acceptance"]
    config = candidate["config"]
    scenarios = acceptance["by_scenario"].values()
    return (
        bool(acceptance["accepted"]),
        -int(config["maximum_global_hypotheses"]),
        -float(config["motion_initialization_residual_gate_m"]),
        min(float(values["median_track_purity"]) for values in scenarios),
        min(
            float(values["mean_common_confirmed_rate"])
            for values in acceptance["by_scenario"].values()
        ),
    )


def validate_preflight_summary(
    path: str | Path,
    protocol: BenchmarkProtocol | None = None,
) -> dict[str, Any]:
    """Validate the independent nine-episode diagnostic gate."""

    protocol = protocol or BenchmarkProtocol()
    path = Path(path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != PREFLIGHT_SCHEMA_VERSION:
        raise ValueError("unsupported preflight summary schema")
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("preflight protocol fingerprint mismatch")
    if payload.get("test_data_accessed") is not False:
        raise ValueError("preflight must not access reserved test data")
    if payload.get("acceptance", {}).get("accepted") is not True:
        raise ValueError("preflight tracker acceptance did not pass")
    selected_config = SharedTrackerConfig(
        **dict(payload.get("selected_tracker_config", {}))
    )
    if selected_config.fingerprint != payload.get("shared_tracker_fingerprint"):
        raise ValueError("preflight shared tracker fingerprint mismatch")
    if selected_config.fingerprint not in {
        config.fingerprint for config in _preflight_tracker_candidates(protocol)
    }:
        raise ValueError("preflight selected an unapproved tracker candidate")
    rows = payload.get("rows", [])
    expected = {
        (scenario, seed)
        for scenario, _, _ in PREFLIGHT_SCENARIOS
        for seed in PREFLIGHT_SEEDS
    }
    actual = {
        (str(row.get("diagnostic_scenario")), int(row.get("seed", -1)))
        for row in rows
    }
    if actual != expected or len(rows) != len(expected):
        raise ValueError("preflight summary does not contain the complete 3x3 matrix")
    return payload


def _archive_legacy_preflight_launch(output_root: Path) -> None:
    """Preserve first-generation root logs before a resumed preflight launch."""

    legacy_files = (
        "blocks_stdout_stderr.log",
        "blocks_diagnostics.json",
        "settings.json",
    )
    if not any((output_root / name).exists() for name in legacy_files):
        return
    launch_root = output_root / "launches" / "launch_01"
    launch_root.mkdir(parents=True, exist_ok=True)
    for name in legacy_files:
        source = output_root / name
        destination = launch_root / name
        if source.exists() and not destination.exists():
            source.replace(destination)


def _recover_preflight_rows(
    output_root: Path,
    protocol: BenchmarkProtocol,
    tracker_config: SharedTrackerConfig,
) -> list[dict[str, Any]]:
    """Rebuild diagnostic rows only from complete, validated raw episodes."""

    prior_rows: dict[tuple[str, int], dict[str, Any]] = {}
    progress = output_root / "preflight_progress.json"
    if progress.is_file():
        try:
            payload = json.loads(progress.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if (
            payload.get("schema_version") == PREFLIGHT_SCHEMA_VERSION
            and payload.get("protocol_fingerprint") == protocol.fingerprint
        ):
            prior_rows = {
                (str(row.get("diagnostic_scenario")), int(row.get("seed", -1))): row
                for row in payload.get("rows", [])
            }
    rows: list[dict[str, Any]] = []
    for scenario, gimbal_enabled, corruption_level in PREFLIGHT_SCENARIOS:
        for seed in PREFLIGHT_SEEDS:
            episode_dir = (
                output_root
                / scenario
                / f"airsim_seed_{seed}_online{protocol.target_count}"
            )
            try:
                validate_raw_episode(
                    episode_dir,
                    protocol,
                    expected_seed=seed,
                    expected_gimbal_pose_error=gimbal_enabled,
                    split_override="preflight",
                )
                metrics = evaluate_tracker_episode(
                    episode_dir,
                    protocol,
                    tracker_config,
                    corruption_level,
                    expected_gimbal_pose_error=gimbal_enabled,
                    split_override="preflight",
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue
            prior = prior_rows.get((scenario, seed), {})
            rows.append(
                {
                    **metrics,
                    "diagnostic_scenario": scenario,
                    "gimbal_pose_error_enabled": gimbal_enabled,
                    "attempts": list(prior.get("attempts", [])),
                    "reused_after_validation": True,
                    "offline_truth_used_for_diagnostics_only": True,
                }
            )
    return rows


def _select_preflight_tracker(
    output_root: Path,
    protocol: BenchmarkProtocol,
) -> tuple[SharedTrackerConfig, list[dict[str, Any]], list[dict[str, Any]]]:
    """Select one tracker only from the nine diagnostic episodes."""

    prepared = []
    for scenario, gimbal_enabled, corruption_level in PREFLIGHT_SCENARIOS:
        for seed in PREFLIGHT_SEEDS:
            episode_dir = (
                output_root
                / scenario
                / f"airsim_seed_{seed}_online{protocol.target_count}"
            )
            prepared.append(
                (
                    scenario,
                    gimbal_enabled,
                    prepare_tracker_episode(
                        episode_dir,
                        protocol,
                        corruption_level,
                        expected_gimbal_pose_error=gimbal_enabled,
                        split_override="preflight",
                    ),
                )
            )
    candidates: list[dict[str, Any]] = []
    selected_rows: dict[str, list[dict[str, Any]]] = {}
    for config in _preflight_tracker_candidates(protocol):
        rows = []
        for scenario, gimbal_enabled, item in prepared:
            row = evaluate_prepared_tracker_episode(item, protocol, config)
            row["diagnostic_scenario"] = scenario
            row["gimbal_pose_error_enabled"] = gimbal_enabled
            row["reused_after_validation"] = True
            row["offline_truth_used_for_diagnostics_only"] = True
            rows.append(row)
        acceptance = _preflight_acceptance(rows)
        candidates.append(
            {
                "tracker_fingerprint": config.fingerprint,
                "config": asdict(config),
                "acceptance": acceptance,
            }
        )
        selected_rows[config.fingerprint] = rows
    accepted = [item for item in candidates if item["acceptance"]["accepted"]]
    ranked = accepted or candidates
    selected = max(ranked, key=_preflight_selection_key)
    config = SharedTrackerConfig(**selected["config"])
    return config, selected_rows[config.fingerprint], candidates


def run_preflight(
    *,
    repo_root: str | Path,
    output_root: str | Path,
    blocks_script: str | Path,
    api_port: int = 41451,
    max_attempts: int = 2,
    episode_timeout_s: float = 900.0,
    protocol: BenchmarkProtocol | None = None,
) -> Path:
    """Run three diagnostic conditions with three seeds under one Blocks launch."""

    protocol = protocol or BenchmarkProtocol()
    repo_root = Path(repo_root).resolve()
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    rows = _recover_preflight_rows(
        output_root, protocol, tracker_config_for_protocol(protocol)
    )
    completed_keys = {
        (str(row["diagnostic_scenario"]), int(row["seed"])) for row in rows
    }
    pending = [
        (scenario, gimbal_enabled, corruption_level, seed)
        for scenario, gimbal_enabled, corruption_level in PREFLIGHT_SCENARIOS
        for seed in PREFLIGHT_SEEDS
        if (scenario, seed) not in completed_keys
    ]
    _archive_legacy_preflight_launch(output_root)
    launch_roots = sorted(
        path
        for path in (output_root / "launches").glob("launch_*")
        if path.is_dir()
    )
    if not pending:
        process = None
        launch_root = None
    else:
        launch_root = (
            output_root
            / "launches"
            / f"launch_{len(launch_roots) + 1:02d}"
        )
        launch_root.mkdir(parents=True, exist_ok=True)
    launch = _preflight_config(PREFLIGHT_SEEDS[0], api_port, True, protocol)
    settings_path = write_airsim_settings(
        (output_root if launch_root is None else launch_root) / "settings.json",
        launch,
        CameraSpec(),
    )
    process = (
        None
        if launch_root is None
        else LocalBlocksProcess(
            Path(blocks_script),
            settings_path,
            launch_root,
            api_port=api_port,
            prefer_nvidia_offload=True,
        )
    )
    if process is not None:
        process.start()
    try:
        if process is not None:
            _wait_for_rpc(api_port, process, 120.0)
            episode_index = 0
            for scenario, gimbal_enabled, corruption_level, seed in pending:
                episode_index += 1
                episode_dir = (
                    output_root
                    / scenario
                    / f"airsim_seed_{seed}_online{protocol.target_count}"
                )
                attempts: list[dict[str, Any]] = []
                completed = False
                for attempt in range(1, max_attempts + 1):
                    if episode_index > 1 or attempt > 1:
                        _reset_client(api_port)
                    result = _run_worker(
                        repo_root,
                        episode_dir,
                        seed,
                        api_port,
                        episode_timeout_s,
                        gimbal_pose_error_enabled=gimbal_enabled,
                        protocol=protocol,
                    )
                    result["attempt"] = attempt
                    attempts.append(result)
                    if result["returncode"] in {0, 2}:
                        try:
                            validate_raw_episode(
                                episode_dir,
                                protocol,
                                expected_seed=seed,
                                expected_gimbal_pose_error=gimbal_enabled,
                                split_override="preflight",
                            )
                        except ValueError:
                            pass
                        else:
                            completed = True
                            break
                if not completed:
                    raise RuntimeError(
                        f"preflight episode {scenario}/{seed} failed after "
                        f"{max_attempts} attempts"
                    )
                metrics = evaluate_tracker_episode(
                    episode_dir,
                    protocol,
                    tracker_config_for_protocol(protocol),
                    corruption_level,
                    expected_gimbal_pose_error=gimbal_enabled,
                    split_override="preflight",
                )
                rows.append(
                    {
                        **metrics,
                        "diagnostic_scenario": scenario,
                        "gimbal_pose_error_enabled": gimbal_enabled,
                        "attempts": attempts,
                        "reused_after_validation": False,
                        "offline_truth_used_for_diagnostics_only": True,
                    }
                )
                write_json(
                    output_root / "preflight_progress.json",
                    {
                        "schema_version": PREFLIGHT_SCHEMA_VERSION,
                        "protocol_fingerprint": protocol.fingerprint,
                        "completed_episode_count": len(rows),
                        "expected_episode_count": 9,
                        "rows": rows,
                    },
                )
    finally:
        if process is not None and launch_root is not None:
            process.stop()
            write_json(launch_root / "blocks_diagnostics.json", process.diagnostics())
    launch_roots = sorted(
        path
        for path in (output_root / "launches").glob("launch_*")
        if path.is_dir()
    )
    selected_tracker, selected_rows, tracker_candidates = _select_preflight_tracker(
        output_root, protocol
    )
    summary = output_root / "preflight_summary.json"
    write_json(
        summary,
        {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "protocol_fingerprint": protocol.fingerprint,
            "diagnostic_only": True,
            "test_data_accessed": False,
            "screenshots_saved": False,
            "blocks_launch_count": len(launch_roots),
            "resumed_after_runtime_failure": len(launch_roots) > 1,
            "reset_separated_episodes": True,
            "shared_tracker_fingerprint": selected_tracker.fingerprint,
            "selected_tracker_config": asdict(selected_tracker),
            "tracker_selection_basis": [
                "preflight_acceptance_desc",
                "global_hypothesis_count_asc",
                "motion_residual_gate_asc",
                "worst_scenario_median_purity_desc",
                "worst_scenario_common_confirmed_rate_desc",
            ],
            "tracker_candidates": tracker_candidates,
            "acceptance": _preflight_acceptance(selected_rows),
            "rows": selected_rows,
        },
    )
    return summary


def run_phase(
    *,
    repo_root: str | Path,
    output_root: str | Path,
    dataset_root: str | Path,
    seeds: Sequence[int],
    phase: str,
    blocks_script: str | Path,
    api_port: int = 41451,
    max_attempts: int = 2,
    episode_timeout_s: float = 900.0,
    preflight_summary: str | Path | None = None,
    protocol: BenchmarkProtocol | None = None,
) -> Path:
    """Launch Blocks once, reset between episodes, and materialize one phase."""

    protocol = protocol or BenchmarkProtocol()
    if phase not in {"calibration", "test"}:
        raise ValueError("phase must be calibration or test")
    expected = set(protocol.train_seeds + protocol.validation_seeds) if phase == "calibration" else set(protocol.test_seeds)
    if set(int(seed) for seed in seeds) != expected:
        raise ValueError(f"{phase} phase must use its complete frozen seed set")
    repo_root = Path(repo_root).resolve()
    output_root = Path(output_root).resolve()
    dataset_root = Path(dataset_root).resolve()
    if phase == "calibration":
        if preflight_summary is None:
            raise RuntimeError("formal calibration requires a passing preflight summary")
        preflight = validate_preflight_summary(preflight_summary, protocol)
    else:
        preflight = None
    phase_root = output_root / phase
    phase_root.mkdir(parents=True, exist_ok=True)
    prior_runtime_evidence = (phase_root / "blocks_diagnostics.json").is_file()
    tracker_freeze_path: Path | None = None
    tracker_config: SharedTrackerConfig | None = None
    if phase == "test":
        freezes = dataset_root / "freezes" / "all_routes_frozen.json"
        if not freezes.is_file():
            raise RuntimeError("test AirSim episodes cannot start before all routes freeze")
        try:
            freeze_marker = validate_freeze_marker(freezes)
        except (KeyError, OSError, ValueError) as exc:
            raise RuntimeError(
                "test AirSim episodes require a complete positively validated freeze marker"
            ) from exc
        tracker_freeze_path = Path(str(freeze_marker["tracker_freeze"])).resolve()
        _, tracker_config = load_tracker_freeze(tracker_freeze_path)
    launch_config = build_config(int(seeds[0]), api_port, protocol=protocol)
    settings_path = write_airsim_settings(
        phase_root / "settings.json", launch_config, CameraSpec()
    )
    reusable_receipts = {
        int(seed): _load_reusable_receipt(
            phase_root / f"airsim_seed_{int(seed)}_online{protocol.target_count}",
            protocol,
            int(seed),
        )
        for seed in seeds
    }
    needs_runtime = any(receipt is None for receipt in reusable_receipts.values())
    process = (
        LocalBlocksProcess(
            Path(blocks_script), settings_path, phase_root,
            api_port=api_port, prefer_nvidia_offload=True,
        )
        if needs_runtime
        else None
    )
    if process is not None:
        process.start()
    results: list[dict[str, Any]] = []
    episode_dirs: list[Path] = []
    try:
        if process is not None:
            _wait_for_rpc(api_port, process, 120.0)
        for index, seed_value in enumerate(seeds):
            seed = int(seed_value)
            print(
                f"phase={phase} seed={seed} index={index + 1}/{len(seeds)} started",
                flush=True,
            )
            episode_dir = phase_root / f"airsim_seed_{seed}_online{protocol.target_count}"
            reused = reusable_receipts[seed]
            attempts: list[dict[str, Any]] = []
            if reused is None:
                if process is None:
                    raise RuntimeError("missing episode receipt requires an AirSim runtime")
                completed = False
                for attempt in range(1, max_attempts + 1):
                    if index > 0 or attempt > 1:
                        _reset_client(api_port)
                    result = _run_worker(
                        repo_root,
                        episode_dir,
                        seed,
                        api_port,
                        episode_timeout_s,
                        protocol=protocol,
                    )
                    result["attempt"] = attempt
                    attempts.append(result)
                    if result["returncode"] in {0, 2}:
                        try:
                            validation = validate_raw_episode(
                                episode_dir, protocol, expected_seed=seed
                            )
                        except ValueError:
                            completed = False
                        else:
                            receipt = {
                                "schema_version": BATCH_SCHEMA_VERSION,
                                "protocol_fingerprint": protocol.fingerprint,
                                "seed": seed,
                                "split": split_for_seed(protocol, seed),
                                "raw_hashes": validation["files"],
                                "screenshots_saved": False,
                            }
                            write_json(_receipt_path(episode_dir), receipt)
                            reused = receipt
                            completed = True
                            break
                if not completed:
                    raise RuntimeError(f"AirSim episode {seed} failed after {max_attempts} attempts")
            episode_dirs.append(episode_dir)
            results.append({
                "seed": seed,
                "split": split_for_seed(protocol, seed),
                "reused": not attempts,
                "attempts": attempts,
                "receipt_sha256": sha256_file(_receipt_path(episode_dir)),
                "snapshot_count": 0,
            })
            write_json(phase_root / "batch_progress.json", {
                "schema_version": BATCH_SCHEMA_VERSION,
                "phase": phase,
                "protocol_fingerprint": protocol.fingerprint,
                "completed_seed_count": len(results),
                "expected_seed_count": len(seeds),
                "snapshot_count": 0,
                "last_completed_seed": seed,
                "results": results,
            })
            print(
                f"phase={phase} seed={seed} completed "
                f"reused={not attempts} raw_episode_validated=true",
                flush=True,
            )
    finally:
        if process is not None:
            process.stop()
            write_json(phase_root / "blocks_diagnostics.json", process.diagnostics())
    if phase == "calibration":
        raw_manifest = dataset_root / "raw_calibration_manifest.json"
        write_json(raw_manifest, {
            "schema_version": RAW_CALIBRATION_SCHEMA_VERSION,
            "protocol_fingerprint": protocol.fingerprint,
            "test_data_accessed": False,
            "episodes": [
                {
                    "seed": int(item["seed"]),
                    "split": str(item["split"]),
                    "episode_dir": str(path.resolve()),
                    "receipt_sha256": str(item["receipt_sha256"]),
                }
                for item, path in zip(results, episode_dirs)
            ],
        })
        tracker_freeze_path = dataset_root / "freezes" / "shared_tracker.json"
        calibrate_and_freeze_tracker(
            episode_dirs,
            raw_manifest,
            tracker_freeze_path,
            protocol,
        )
        _, tracker_config = load_tracker_freeze(tracker_freeze_path)
    if tracker_freeze_path is None or tracker_config is None:
        raise RuntimeError("shared tracker was not frozen before snapshot materialization")
    entries: list[dict[str, Any]] = []
    for index, episode_dir in enumerate(episode_dirs):
        episode_entries = materialize_episode(
            episode_dir,
            dataset_root,
            protocol,
            tracker_config=tracker_config,
        )
        entries.extend(episode_entries)
        results[index]["snapshot_count"] = len(episode_entries)
    manifest = write_dataset_manifest(
        dataset_root,
        entries,
        protocol,
        phase=phase,
        tracker_freeze=tracker_freeze_path,
    )
    current_blocks_launch_count = int(process is not None)
    write_json(phase_root / "batch_summary.json", {
        "schema_version": BATCH_SCHEMA_VERSION,
        "phase": phase,
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "blocks_launch_count": int(
            prior_runtime_evidence or current_blocks_launch_count > 0
        ),
        "blocks_launch_count_this_invocation": current_blocks_launch_count,
        "prior_blocks_runtime_evidence": prior_runtime_evidence,
        "all_raw_episodes_reused_this_invocation": all(
            bool(item["reused"]) for item in results
        ),
        "reset_separated_episodes": True,
        "screenshots_saved": False,
        "completed_seed_count": len(results),
        "snapshot_count": len(entries),
        "tracker_freeze": str(tracker_freeze_path),
        "tracker_fingerprint": tracker_config.fingerprint,
        "preflight_summary": (
            None if preflight_summary is None else str(Path(preflight_summary).resolve())
        ),
        "preflight_summary_sha256": (
            None
            if preflight_summary is None
            else sha256_file(Path(preflight_summary).resolve())
        ),
        "preflight_selected_tracker_fingerprint": (
            None if preflight is None else preflight["shared_tracker_fingerprint"]
        ),
        "dataset_manifest": str(manifest),
        "results": results,
    })
    return manifest
