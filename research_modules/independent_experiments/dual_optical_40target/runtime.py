"""AirSim runtime for the independent dual-optical association experiment."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import uuid
from typing import Any, Iterable, Mapping, Sequence

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

from .core import (
    AssociationConfig,
    AnonymousDetection,
    BearingTrack,
    CameraSpec,
    CameraState,
    CrossAssociationResult,
    GeometrySensitivity,
    RayObservation,
    ScanRevisitTracker,
    ScenarioConfig,
    TargetSpec,
    TemporalAssociationResult,
    associate_tracks,
    associate_tracks_temporally,
    estimate_geometry_sensitivity,
    generate_target_specs,
    look_angles_deg,
    minimum_target_separation,
    online_truth_leakage_keys,
    project_world_point,
    ray_observation_from_detection,
    scan_yaw_deg,
    sweep_index,
)


SCENARIO_SCHEMA_V3 = "dual-optical-multitarget-scenario-v3"
METRICS_SCHEMA_V3 = "dual-optical-multitarget-metrics-v3"
TEMPORAL_ASSOCIATION_SCHEMA_V3 = "dual-optical-temporal-association-v3"
RECORD_MANIFEST_SCHEMA_V3 = "dual-optical-multitarget-record-manifest-v3"


def camera_scan_timestamp(
    config: ScenarioConfig, camera_id: str, logical_timestamp: float
) -> float:
    """Return the yaw-only scan clock, including camera B's phase offset.

    This clock must not be used for tracker sweep indices or snapshot cutoffs;
    those stay on the common scenario clock so both stations publish the same
    completed two-second revolution.
    """

    return float(logical_timestamp) + (
        config.camera_b_scan_phase_offset_s
        if camera_id == config.camera_b_name
        else 0.0
    )


def tracker_sweep_index(config: ScenarioConfig, logical_timestamp: float) -> int:
    """Map the common scenario clock to a tracker sweep/revolution index."""

    return sweep_index(
        logical_timestamp,
        period_s=config.scan_period_s,
        mode=config.scan_mode,
    )


def advance_scene_for_detection(client: Any, mode: str) -> None:
    """Refresh one scene step or fail explicitly when deterministic stepping is absent."""

    if mode == "legacy_wall_yield":
        time.sleep(0.002)
        return
    if mode != "paused_continue":
        raise ValueError(f"unsupported deterministic step mode: {mode}")
    continue_for_frames = getattr(client, "simContinueForFrames", None)
    if not callable(continue_for_frames):
        raise RuntimeError(
            "paused_continue unavailable: AirSim client has no simContinueForFrames"
        )
    try:
        continue_for_frames(1)
    except Exception as exc:
        raise RuntimeError(
            "paused_continue failed while advancing one AirSim frame: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def prepare_scene_stepping(client: Any, mode: str) -> None:
    """Enter paused stepping only when the configured AirSim API supports it."""

    if mode == "legacy_wall_yield":
        return
    if mode != "paused_continue":
        raise ValueError(f"unsupported deterministic step mode: {mode}")
    pause = getattr(client, "simPause", None)
    if not callable(pause):
        raise RuntimeError("paused_continue unavailable: AirSim client has no simPause")
    try:
        pause(True)
    except Exception as exc:
        raise RuntimeError(
            "paused_continue unavailable: AirSim simPause(True) failed: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


@dataclass(frozen=True)
class GimbalPoseErrorSample:
    camera_id: str
    frame_index: int
    timestamp: float
    nominal_yaw_deg: float
    nominal_pitch_deg: float
    actual_yaw_deg: float
    actual_pitch_deg: float
    fixed_yaw_axis_mrad: float
    fixed_pitch_axis_mrad: float
    jitter_yaw_axis_mrad: float
    jitter_pitch_axis_mrad: float

    @property
    def fixed_radial_mrad(self) -> float:
        return math.hypot(self.fixed_yaw_axis_mrad, self.fixed_pitch_axis_mrad)

    @property
    def jitter_radial_mrad(self) -> float:
        return math.hypot(self.jitter_yaw_axis_mrad, self.jitter_pitch_axis_mrad)

    @property
    def total_radial_mrad(self) -> float:
        return math.hypot(
            self.fixed_yaw_axis_mrad + self.jitter_yaw_axis_mrad,
            self.fixed_pitch_axis_mrad + self.jitter_pitch_axis_mrad,
        )

    def actual_state(self, nominal_state: CameraState) -> CameraState:
        if (
            nominal_state.camera_id != self.camera_id
            or nominal_state.frame_index != self.frame_index
        ):
            raise ValueError("nominal CameraState does not match pose-error sample")
        return CameraState(
            camera_id=nominal_state.camera_id,
            frame_index=nominal_state.frame_index,
            timestamp=nominal_state.timestamp,
            position_ned=nominal_state.position_ned,
            yaw_deg=self.actual_yaw_deg,
            pitch_deg=self.actual_pitch_deg,
        )


class GimbalPoseErrorModel:
    """Deterministic tangent-plane boresight bias and frame jitter."""

    def __init__(
        self,
        *,
        scenario_seed: int,
        camera_ids: Sequence[str],
        enabled: bool,
        fixed_bias_mrad: float,
        jitter_rms_mrad: float,
    ) -> None:
        if fixed_bias_mrad < 0.0 or jitter_rms_mrad < 0.0:
            raise ValueError("gimbal error magnitudes must be non-negative")
        self.scenario_seed = int(scenario_seed)
        self.enabled = bool(enabled)
        self.fixed_bias_mrad = float(fixed_bias_mrad)
        self.jitter_rms_mrad = float(jitter_rms_mrad)
        self._fixed_axis_mrad: dict[str, tuple[float, float]] = {}
        for camera_id in sorted(str(item) for item in camera_ids):
            rng = np.random.default_rng(
                _deterministic_seed(self.scenario_seed, camera_id, "fixed-gimbal")
            )
            angle = float(rng.uniform(0.0, 2.0 * math.pi))
            magnitude = self.fixed_bias_mrad if self.enabled else 0.0
            self._fixed_axis_mrad[camera_id] = (
                magnitude * math.cos(angle),
                magnitude * math.sin(angle),
            )

    def sample(
        self,
        nominal_state: CameraState,
    ) -> GimbalPoseErrorSample:
        camera_id = nominal_state.camera_id
        if camera_id not in self._fixed_axis_mrad:
            raise ValueError(f"unknown camera_id: {camera_id}")
        fixed_yaw, fixed_pitch = self._fixed_axis_mrad[camera_id]
        if self.enabled and self.jitter_rms_mrad > 0.0:
            rng = np.random.default_rng(
                _deterministic_seed(
                    self.scenario_seed,
                    camera_id,
                    nominal_state.frame_index,
                    "frame-gimbal",
                )
            )
            component_sigma = self.jitter_rms_mrad / math.sqrt(2.0)
            jitter_yaw, jitter_pitch = (
                float(value) for value in rng.normal(0.0, component_sigma, size=2)
            )
        else:
            jitter_yaw = jitter_pitch = 0.0
        yaw_axis_mrad = fixed_yaw + jitter_yaw
        pitch_axis_mrad = fixed_pitch + jitter_pitch
        pitch_cosine = max(
            abs(math.cos(math.radians(nominal_state.pitch_deg))), 1e-3
        )
        yaw_delta_deg = math.degrees((yaw_axis_mrad / pitch_cosine) / 1000.0)
        pitch_delta_deg = math.degrees(pitch_axis_mrad / 1000.0)
        return GimbalPoseErrorSample(
            camera_id=camera_id,
            frame_index=nominal_state.frame_index,
            timestamp=nominal_state.timestamp,
            nominal_yaw_deg=nominal_state.yaw_deg,
            nominal_pitch_deg=nominal_state.pitch_deg,
            actual_yaw_deg=nominal_state.yaw_deg + yaw_delta_deg,
            actual_pitch_deg=nominal_state.pitch_deg + pitch_delta_deg,
            fixed_yaw_axis_mrad=fixed_yaw,
            fixed_pitch_axis_mrad=fixed_pitch,
            jitter_yaw_axis_mrad=jitter_yaw,
            jitter_pitch_axis_mrad=jitter_pitch,
        )


def _deterministic_seed(*parts: object) -> int:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def pair_scaling_metrics(
    target_count: int,
    stable_track_count_a: int,
    stable_track_count_b: int,
) -> dict[str, int | float]:
    """Describe how local track fragmentation changes the cross-camera pair space."""

    if target_count <= 0:
        raise ValueError("target_count must be positive")
    if stable_track_count_a < 0 or stable_track_count_b < 0:
        raise ValueError("stable track counts must be non-negative")
    ideal_truth_pair_count = target_count * target_count
    actual_local_pair_count = stable_track_count_a * stable_track_count_b
    return {
        "ideal_truth_pair_count": ideal_truth_pair_count,
        "actual_local_pair_count": actual_local_pair_count,
        "fragment_excess_a": max(stable_track_count_a - target_count, 0),
        "fragment_excess_b": max(stable_track_count_b - target_count, 0),
        "pair_expansion_ratio": actual_local_pair_count / ideal_truth_pair_count,
    }


@dataclass(frozen=True)
class ExperimentResult:
    output_dir: Path
    settings_path: Path
    metrics_path: Path
    metrics: dict[str, Any]
    output_paths: dict[str, Path]
    tracks_a: tuple[BearingTrack, ...]
    tracks_b: tuple[BearingTrack, ...]
    association: CrossAssociationResult
    target_specs: tuple[TargetSpec, ...]
    enhanced_association: TemporalAssociationResult | None = None
    geometry_sensitivity: tuple[GeometrySensitivity, ...] = ()


def reprocess_enhanced_outputs(result: ExperimentResult) -> ExperimentResult:
    """Rebuild enhanced artifacts and upgrade saved metrics to schema v3."""

    enhanced = associate_tracks_temporally(
        result.tracks_a,
        result.tracks_b,
        config=AssociationConfig(
            expected_speed_mps=float(result.metrics.get("target_speed_mps", 50.0))
        ),
    )
    geometry = estimate_geometry_sensitivity(
        enhanced.selected_matches,
        result.tracks_a,
        result.tracks_b,
        angular_noise_mrad=0.15,
        sample_count=1000,
        seed=int(result.metrics.get("seed", 20260811)),
    )
    track_truth: dict[str, str] = {}
    with result.output_paths["track_scoring"].open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        for row in csv.DictReader(stream):
            if row.get("majority_truth_id"):
                track_truth[str(row["track_id"])] = str(row["majority_truth_id"])
    confirmed_pairs = {
        (item.track_a_id, item.track_b_id) for item in enhanced.confirmed_matches
    }
    epipolar_rows = [asdict(item) for item in enhanced.epipolar_evidence]
    candidate_rows = [asdict(item) for item in enhanced.fitted_candidates]
    match_rows = [
        asdict(item)
        | {
            "confirmation_state": (
                "confirmed"
                if (item.track_a_id, item.track_b_id) in confirmed_pairs
                else "pending"
            )
        }
        for item in enhanced.selected_matches
    ]
    decision_rows = [asdict(item) for item in enhanced.decisions]
    hypothesis_rows = [asdict(item) for item in enhanced.hypothesis_history]
    state_rows = [asdict(item) for item in enhanced.state_history]
    suppression_rows = [asdict(item) for item in enhanced.fragment_suppressions]
    geometry_rows = [asdict(item) for item in geometry]
    scored_rows: list[dict[str, Any]] = []
    correct_truth_ids: list[str] = []
    confirmed_truth_ids: list[str] = []
    for match in enhanced.selected_matches:
        truth_a = track_truth.get(match.track_a_id, "")
        truth_b = track_truth.get(match.track_b_id, "")
        correct = bool(truth_a and truth_a == truth_b)
        confirmed = (match.track_a_id, match.track_b_id) in confirmed_pairs
        if correct:
            correct_truth_ids.append(truth_a)
            if confirmed:
                confirmed_truth_ids.append(truth_a)
        scored_rows.append(
            {
                "match_id": match.match_id,
                "track_a_id": match.track_a_id,
                "track_b_id": match.track_b_id,
                "truth_a": truth_a,
                "truth_b": truth_b,
                "correct": correct,
                "confirmation_state": "confirmed" if confirmed else "pending",
                "offline_truth_only": True,
            }
        )
    online_rows = [
        *epipolar_rows,
        *candidate_rows,
        *match_rows,
        *decision_rows,
        *hypothesis_rows,
        *state_rows,
        *suppression_rows,
        *geometry_rows,
    ]
    new_leakage_keys = set(online_truth_leakage_keys(online_rows))
    old_leakage_keys = set(result.metrics.get("online_truth_leakage_keys") or [])
    leakage_keys = sorted(old_leakage_keys | new_leakage_keys)
    target_count = int(
        result.metrics.get("target_count") or len(result.target_specs)
    )
    correct_count = sum(bool(row["correct"]) for row in scored_rows)
    false_count = len(scored_rows) - correct_count
    unique_correct = set(correct_truth_ids)
    duplicate_count = sum(
        max(0, count - 1) for count in Counter(correct_truth_ids).values()
    )
    recall = len(unique_correct) / max(target_count, 1)
    confirmed_recall = len(set(confirmed_truth_ids)) / max(target_count, 1)
    precision = correct_count / len(scored_rows) if scored_rows else None
    coarse_truth_ids = {
        track_truth[item.track_a_id]
        for item in enhanced.epipolar_evidence
        if item.gate_passed
        and item.track_a_id in track_truth
        and item.track_b_id in track_truth
        and track_truth[item.track_a_id] == track_truth[item.track_b_id]
    }
    fit_reduction = 1.0 - enhanced.fit_evaluation_count / max(
        enhanced.full_pair_count, 1
    )
    metrics = json.loads(json.dumps(result.metrics))
    metrics["schema_version"] = METRICS_SCHEMA_V3
    metrics["target_count"] = target_count
    metrics.update(
        pair_scaling_metrics(target_count, len(result.tracks_a), len(result.tracks_b))
    )
    metrics["candidate_screening_elapsed_ms"] = (
        enhanced.candidate_screening_elapsed_ms
    )
    metrics["candidate_fitting_elapsed_ms"] = enhanced.candidate_fitting_elapsed_ms
    metrics["association_processing_elapsed_ms"] = enhanced.processing_elapsed_ms
    metrics["legacy_no_duplicate_match_passed"] = (
        int(metrics.get("duplicate_truth_match_count", 0)) == 0
    )
    metrics["online_truth_leakage_count"] = len(leakage_keys)
    metrics["online_truth_leakage_keys"] = leakage_keys
    metrics["enhanced_association"] = {
        "schema_version": TEMPORAL_ASSOCIATION_SCHEMA_V3,
        "coplanarity_gate_mrad": enhanced.config.coplanarity_median_gate_mrad,
        "full_pair_count": enhanced.full_pair_count,
        "coarse_gate_pass_count": enhanced.coarse_gate_pass_count,
        "fit_evaluation_count": enhanced.fit_evaluation_count,
        "candidate_screening_elapsed_ms": enhanced.candidate_screening_elapsed_ms,
        "candidate_fitting_elapsed_ms": enhanced.candidate_fitting_elapsed_ms,
        "processing_elapsed_ms": enhanced.processing_elapsed_ms,
        "fit_reduction_ratio": fit_reduction,
        "valid_fit_count": sum(item.valid for item in enhanced.fitted_candidates),
        "top_k_hypothesis_count": len(enhanced.hypotheses),
        "selected_match_count": len(enhanced.selected_matches),
        "confirmed_match_count": len(enhanced.confirmed_matches),
        "pending_selected_match_count": len(enhanced.selected_matches)
        - len(enhanced.confirmed_matches),
        "fragment_suppression_count": len(enhanced.fragment_suppressions),
        "fragment_merge_position_gate_m": enhanced.config.fragment_merge_position_gate_m,
        "fragment_merge_velocity_gate_mps": enhanced.config.fragment_merge_velocity_gate_mps,
        "correct_match_count": correct_count,
        "false_match_count": false_count,
        "association_precision": precision,
        "association_full_target_recall": recall,
        "confirmed_full_target_recall": confirmed_recall,
        "duplicate_truth_match_count": duplicate_count,
        "coarse_preserved_truth_count": len(coarse_truth_ids),
        "coarse_preserved_all_targets": len(coarse_truth_ids) == target_count,
        "geometry_sensitivity_evidence_label": "modeled_geometry_sensitivity",
        "geometry_sensitivity_record_count": len(geometry),
        "geometry_sensitivity_p50_median_m": _percentile(
            [item.position_sensitivity_p50_m for item in geometry], 50.0
        ),
        "geometry_sensitivity_p95_median_m": _percentile(
            [item.position_sensitivity_p95_m for item in geometry], 50.0
        ),
        "intersection_angle_median_deg": _percentile(
            [item.intersection_angle_deg for item in geometry], 50.0
        ),
    }
    acceptance = dict(metrics.get("acceptance") or {})
    acceptance.pop("overall_passed", None)
    acceptance["truth_isolation_passed"] = len(leakage_keys) == 0
    acceptance["no_duplicate_match_passed"] = duplicate_count == 0
    acceptance["enhanced_false_association_non_regression_passed"] = (
        false_count <= int(metrics.get("false_match_count", 0))
    )
    acceptance["enhanced_recall_target_passed"] = recall >= 0.900
    acceptance["enhanced_fit_reduction_passed"] = fit_reduction >= 0.80
    acceptance["enhanced_no_duplicate_match_passed"] = duplicate_count == 0
    acceptance["overall_passed"] = all(bool(value) for value in acceptance.values())
    metrics["acceptance"] = acceptance
    online_dir = result.output_dir / "online"
    truth_dir = result.output_dir / "truth"
    output_paths = dict(result.output_paths)
    output_paths.update(
        {
            "epipolar_evidence_v2": write_csv(
                online_dir / "epipolar_evidence_v2.csv", epipolar_rows
            ),
            "enhanced_candidates_v2": write_csv(
                online_dir / "enhanced_candidates_v2.csv", candidate_rows
            ),
            "enhanced_matches_v2": write_csv(
                online_dir / "enhanced_matches_v2.csv", match_rows
            ),
            "association_decisions_v2": write_csv(
                online_dir / "association_decisions_v2.csv", decision_rows
            ),
            "association_hypothesis_history_v2": write_csv(
                online_dir / "association_hypothesis_history_v2.csv", hypothesis_rows
            ),
            "association_state_timeline_v2": write_csv(
                online_dir / "association_state_timeline_v2.csv", state_rows
            ),
            "fragment_suppressions_v2": write_csv(
                online_dir / "fragment_suppressions_v2.csv", suppression_rows
            ),
            "global_hypotheses_v2": write_json(
                online_dir / "global_hypotheses_v2.json",
                [asdict(item) for item in enhanced.hypotheses],
            ),
            "geometry_sensitivity_v2": write_csv(
                online_dir / "geometry_sensitivity_v2.csv", geometry_rows
            ),
            "enhanced_match_scoring_v2": write_csv(
                truth_dir / "enhanced_match_scoring_v2.csv", scored_rows
            ),
        }
    )
    metrics_path = write_json(result.output_dir / "metrics.json", metrics)
    output_paths["metrics"] = metrics_path
    manifest_path = result.output_dir / "record_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = RECORD_MANIFEST_SCHEMA_V3
    manifest["artifacts"] = {
        key: str(path.relative_to(result.output_dir))
        for key, path in output_paths.items()
        if key != "manifest"
    }
    write_json(manifest_path, manifest)
    output_paths["manifest"] = manifest_path
    return ExperimentResult(
        output_dir=result.output_dir,
        settings_path=result.settings_path,
        metrics_path=metrics_path,
        metrics=metrics,
        output_paths=output_paths,
        tracks_a=result.tracks_a,
        tracks_b=result.tracks_b,
        association=result.association,
        target_specs=result.target_specs,
        enhanced_association=enhanced,
        geometry_sensitivity=geometry,
    )


class LocalBlocksProcess:
    """Launch one Blocks process with an experiment-local settings file."""

    def __init__(
        self,
        blocks_script: Path,
        settings_path: Path,
        output_dir: Path,
        *,
        api_port: int,
        prefer_nvidia_offload: bool = True,
    ) -> None:
        self.blocks_script = Path(blocks_script)
        self.settings_path = Path(settings_path)
        self.output_dir = Path(output_dir)
        self.api_port = int(api_port)
        self.prefer_nvidia_offload = bool(prefer_nvidia_offload)
        self.process: subprocess.Popen[str] | None = None
        self._log_stream: Any = None

    @property
    def log_path(self) -> Path:
        return self.output_dir / "blocks_stdout_stderr.log"

    def start(self) -> None:
        script = self.blocks_script.resolve()
        settings = self.settings_path.resolve()
        if not script.exists():
            raise FileNotFoundError(f"Blocks script not found: {script}")
        if not settings.exists():
            raise FileNotFoundError(f"settings file not found: {settings}")
        if _tcp_port_open("127.0.0.1", self.api_port):
            raise RuntimeError(f"AirSim RPC port {self.api_port} is already open")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.log_path.open("w", encoding="utf-8")
        environment = os.environ.copy()
        if self.prefer_nvidia_offload:
            environment.setdefault("__NV_PRIME_RENDER_OFFLOAD", "1")
            environment.setdefault("__GLX_VENDOR_LIBRARY_NAME", "nvidia")
            environment.setdefault("__VK_LAYER_NV_optimus", "NVIDIA_only")
        command = [
            str(script),
            f"-settings={settings}",
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            "-NoVSync",
            "-NoHMD",
            "-NoSound",
        ]
        if not os.access(script, os.X_OK):
            command.insert(0, "bash")
        self.process = subprocess.Popen(
            command,
            cwd=str(script.parent),
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=True,
        )

    def stop(self, timeout_s: float = 10.0) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                process.terminate()
            deadline = time.monotonic() + timeout_s
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.2)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    process.kill()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass
        if self._log_stream is not None:
            self._log_stream.close()
            self._log_stream = None
        deadline = time.monotonic() + timeout_s
        while _tcp_port_open("127.0.0.1", self.api_port) and time.monotonic() < deadline:
            time.sleep(0.2)

    def diagnostics(self) -> dict[str, Any]:
        log_text = (
            self.log_path.read_text(encoding="utf-8", errors="replace")
            if self.log_path.exists()
            else ""
        )
        settings_path = str(self.settings_path.resolve())
        return {
            "settings_path": settings_path,
            "settings_loaded": "Loaded settings from" in log_text
            and settings_path in log_text,
            "engine_initialized": "Engine is initialized" in log_text,
            "game_mode_seen": "Game class is 'AirSimGameMode'" in log_text,
            "rpc_port_open": _tcp_port_open("127.0.0.1", self.api_port),
            "process_returncode": None if self.process is None else self.process.poll(),
            "log_tail": "\n".join(log_text.splitlines()[-80:]),
        }


def write_airsim_settings(
    path: Path, config: ScenarioConfig, camera_spec: CameraSpec
) -> Path:
    capture = {
        "ImageType": 0,
        "Width": int(camera_spec.width),
        "Height": int(camera_spec.height),
        "FOV_Degrees": float(camera_spec.horizontal_fov_deg),
        "MotionBlurAmount": 0,
    }

    def vehicle(position: Sequence[float]) -> dict[str, Any]:
        return {
            "VehicleType": "ComputerVision",
            "AutoCreate": True,
            "AllowAPIAlways": True,
            "X": float(position[0]),
            "Y": float(position[1]),
            "Z": float(position[2]),
            "Pitch": 0,
            "Roll": 0,
            "Yaw": 0,
            "Cameras": {
                config.camera_name: {
                    "X": 0,
                    "Y": 0,
                    "Z": 0,
                    "Pitch": 0,
                    "Roll": 0,
                    "Yaw": 0,
                    "CaptureSettings": [dict(capture)],
                }
            },
        }

    payload = {
        "SeeDocsAt": "https://microsoft.github.io/AirSim/settings/",
        "SettingsVersion": 1.2,
        "SimMode": "ComputerVision",
        "EnableRpc": True,
        "RpcEnabled": True,
        "ApiServerPort": int(config.api_port),
        "LocalHostIp": "127.0.0.1",
        "ClockSpeed": float(config.clock_speed),
        "ViewMode": "NoDisplay",
        "CameraDefaults": {"CaptureSettings": [dict(capture)]},
        "SubWindows": [],
        "Vehicles": {
            config.camera_a_name: vehicle(config.camera_a_position_ned),
            config.camera_b_name: vehicle(config.camera_b_position_ned),
        },
    }
    return write_json(path, payload)


class DualOpticalAirSimRunner:
    def __init__(
        self,
        *,
        config: ScenarioConfig,
        camera_spec: CameraSpec,
        output_dir: Path,
        blocks_script: Path,
        launch_blocks: bool = True,
        connection_timeout_s: float = 90.0,
        client_timeout_s: float = 10.0,
        save_keyframes: bool = False,
        prefer_nvidia_offload: bool = True,
        client: Any | None = None,
        airsim_module: Any | None = None,
    ) -> None:
        self.config = config
        self.camera_spec = camera_spec
        self.output_dir = Path(output_dir)
        self.blocks_script = Path(blocks_script)
        self.launch_blocks = bool(launch_blocks)
        self.connection_timeout_s = float(connection_timeout_s)
        self.client_timeout_s = float(client_timeout_s)
        self.save_keyframes = bool(save_keyframes)
        self.prefer_nvidia_offload = bool(prefer_nvidia_offload)
        self._client = client
        self._airsim = airsim_module
        self._actor_run_nonce = f"P{os.getpid()}U{uuid.uuid4().hex}"
        self._spawned_actor_names: set[str] = set()

    def _actor_name_for_run(self, base_name: str) -> str:
        return f"{base_name}_R{self._actor_run_nonce}"

    def _remember_spawned_actor(self, spawned_name: Any) -> str:
        actual_name = str(spawned_name or "")
        if actual_name:
            self._spawned_actor_names.add(actual_name)
        return actual_name

    def _cleanup_spawned_actors(
        self, client: Any, requested_names: Sequence[str] = ()
    ) -> None:
        names = dict.fromkeys(
            [
                *sorted(self._spawned_actor_names),
                *(str(name) for name in requested_names if str(name)),
            ]
        )
        for name in names:
            try:
                client.simDestroyObject(name)
            except Exception:
                pass

    def run(self) -> ExperimentResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        settings_path = write_airsim_settings(
            self.output_dir / "settings.json", self.config, self.camera_spec
        )
        target_specs = tuple(
            replace(
                target,
                actor_name=self._actor_name_for_run(target.actor_name),
            )
            for target in generate_target_specs(self.config)
        )
        write_json(
            self.output_dir / "scenario.json",
            {
                "schema_version": SCENARIO_SCHEMA_V3,
                "independent_experiment": True,
                "connected_d_modules": [],
                "scenario": asdict(self.config),
                "camera": asdict(self.camera_spec)
                | {
                    "vertical_fov_deg": self.camera_spec.vertical_fov_deg,
                    "effective_ifov_mrad": self.camera_spec.effective_ifov_mrad,
                },
                "minimum_target_separation_m": minimum_target_separation(
                    target_specs, self.config.duration_s
                ),
                "target_specs_offline_truth_only": [
                    asdict(target) for target in target_specs
                ],
            },
        )
        process = LocalBlocksProcess(
            self.blocks_script,
            settings_path,
            self.output_dir,
            api_port=self.config.api_port,
            prefer_nvidia_offload=self.prefer_nvidia_offload,
        )
        if self.launch_blocks:
            process.start()
        try:
            airsim_module, client = self._connect()
            preflight = self._run_preflight(airsim_module, client)
            write_json(self.output_dir / "preflight.json", preflight)
            if not bool(preflight.get("passed")):
                raise RuntimeError(
                    f"preflight failed: {preflight.get('failure_reason', 'unknown')}"
                )
            client.reset()
            time.sleep(1.0)
            self._client = self._new_client()
            self._wait_for_client()
            client = self._client
            result = self._run_formal_episode(
                airsim_module,
                client,
                target_specs,
                float(preflight["final_scale_multiplier"]),
                settings_path,
            )
        except Exception as exc:
            write_json(
                self.output_dir / "failure.json",
                {
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "independent_experiment": True,
                },
            )
            raise
        finally:
            try:
                if self._client is not None:
                    self._client.simPause(False)
                    self._cleanup_spawned_actors(
                        self._client,
                        (
                            *(target.actor_name for target in target_specs),
                            self._actor_name_for_run(
                                "MSM_DualOptical_Calibration_Target"
                            ),
                        ),
                    )
            except Exception:
                pass
            if self.launch_blocks:
                process.stop()
            write_json(
                self.output_dir / "blocks_diagnostics.json", process.diagnostics()
            )
        return result

    def _connect(self) -> tuple[Any, Any]:
        if self._airsim is None:
            import airsim as airsim_module

            self._airsim = airsim_module
        if self._client is None:
            self._client = self._airsim.VehicleClient(
                ip="127.0.0.1",
                port=self.config.api_port,
                timeout_value=self.client_timeout_s,
            )
        self._wait_for_client()
        return self._airsim, self._client

    def _new_client(self) -> Any:
        return self._airsim.VehicleClient(
            ip="127.0.0.1",
            port=self.config.api_port,
            timeout_value=self.client_timeout_s,
        )

    def _wait_for_client(self) -> None:
        deadline = time.monotonic() + self.connection_timeout_s
        last_error = ""
        while time.monotonic() < deadline:
            try:
                if self._client.ping():
                    return
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            # AirSim 1.8.1 msgpack-rpc does not recover a transport that first
            # connected before Blocks opened the port.
            try:
                self._client = self._new_client()
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
        raise TimeoutError(f"AirSim connection timed out: {last_error}")

    def _run_preflight(self, airsim_module: Any, client: Any) -> dict[str, Any]:
        config = self.config
        camera = self.camera_spec
        base_yaw, fixed_pitch = look_angles_deg(
            config.camera_a_position_ned, config.corridor_center_ned
        )
        calibration_range = 120.0
        yaw_rad = math.radians(base_yaw)
        pitch_rad = math.radians(fixed_pitch)
        forward = np.asarray(
            (
                math.cos(pitch_rad) * math.cos(yaw_rad),
                math.cos(pitch_rad) * math.sin(yaw_rad),
                -math.sin(pitch_rad),
            ),
            dtype=float,
        )
        position = np.asarray(config.camera_a_position_ned, dtype=float) + forward * calibration_range
        calibration_name = self._actor_name_for_run(
            "MSM_DualOptical_Calibration_Target"
        )
        try:
            client.simDestroyObject(calibration_name)
        except Exception:
            pass
        client.simPause(False)
        for camera_id, camera_position in config.camera_positions.items():
            camera_yaw, camera_pitch = look_angles_deg(
                camera_position, config.corridor_center_ned
            )
            client.simSetCameraFov(
                config.camera_name,
                camera.horizontal_fov_deg,
                vehicle_name=camera_id,
            )
            client.simSetCameraPose(
                config.camera_name,
                _camera_pose(airsim_module, camera_yaw, camera_pitch),
                vehicle_name=camera_id,
            )
        spawned_name = client.simSpawnObject(
            calibration_name,
            config.target_asset_name,
            _world_pose(airsim_module, position, 0.0),
            airsim_module.Vector3r(1.0, 1.0, 1.0),
            False,
        )
        if not spawned_name:
            return {
                "passed": False,
                "failure_reason": "calibration_actor_spawn_failed",
                "requested_actor_name": calibration_name,
            }
        actual_name = self._remember_spawned_actor(spawned_name)
        self._configure_detection_filters(
            client,
            config.camera_a_name,
            (actual_name,),
        )
        initial = _wait_for_detection(
            client,
            airsim_module,
            config,
            config.camera_a_name,
            expected_name=actual_name,
            timeout_s=8.0,
        )
        initial_extent = _box3d_longest_extent(initial)
        if initial is None or initial_extent is None or initial_extent <= 0.0:
            client.simDestroyObject(actual_name)
            return {
                "passed": False,
                "failure_reason": "box3d_scale_measurement_unavailable",
                "spawned_actor_name": actual_name,
                "initial_detection_count": len(
                    client.simGetDetections(
                        config.camera_name,
                        airsim_module.ImageType.Scene,
                        vehicle_name=config.camera_a_name,
                    )
                ),
            }
        multiplier = config.target_longest_dimension_m / initial_extent
        client.simSetObjectScale(
            actual_name,
            airsim_module.Vector3r(multiplier, multiplier, multiplier),
        )
        final_detection, final_extent = _wait_for_detection_extent(
            client,
            airsim_module,
            config,
            config.camera_a_name,
            expected_name=actual_name,
            expected_extent_m=config.target_longest_dimension_m,
            tolerance_m=config.target_dimension_tolerance_m,
            timeout_s=4.0,
        )
        if final_extent is not None and final_extent > 0.0:
            correction = config.target_longest_dimension_m / final_extent
            if not math.isclose(correction, 1.0, abs_tol=0.01):
                multiplier *= correction
                client.simSetObjectScale(
                    actual_name,
                    airsim_module.Vector3r(multiplier, multiplier, multiplier),
                )
                final_detection, final_extent = _wait_for_detection_extent(
                    client,
                    airsim_module,
                    config,
                    config.camera_a_name,
                    expected_name=actual_name,
                    expected_extent_m=config.target_longest_dimension_m,
                    tolerance_m=config.target_dimension_tolerance_m,
                    timeout_s=4.0,
                )
        reported_scale = client.simGetObjectScale(actual_name)
        client.simDestroyObject(actual_name)
        camera_validation = self._validate_cameras(airsim_module, client)
        passed = bool(
            final_extent is not None
            and abs(final_extent - config.target_longest_dimension_m)
            <= config.target_dimension_tolerance_m
            and all(
                bool(item.get("passed"))
                for item in camera_validation.values()
            )
        )
        return {
            "passed": passed,
            "failure_reason": "" if passed else "camera_or_target_dimension_preflight_failed",
            "camera_validation": camera_validation,
            "spawned_actor_name": actual_name,
            "native_longest_extent_m": initial_extent,
            "final_longest_extent_m": final_extent,
            "requested_longest_extent_m": config.target_longest_dimension_m,
            "tolerance_m": config.target_dimension_tolerance_m,
            "final_scale_multiplier": multiplier,
            "reported_object_scale": _vector3_to_list(reported_scale),
            "fixed_pitch_deg": fixed_pitch,
            "base_yaw_deg": base_yaw,
        }

    def _validate_cameras(self, airsim_module: Any, client: Any) -> dict[str, Any]:
        validation: dict[str, Any] = {}
        for camera_id in self.config.camera_positions:
            info = client.simGetCameraInfo(
                self.config.camera_name, vehicle_name=camera_id
            )
            responses = client.simGetImages(
                [
                    airsim_module.ImageRequest(
                        self.config.camera_name,
                        airsim_module.ImageType.Scene,
                        False,
                        True,
                    )
                ],
                vehicle_name=camera_id,
            )
            response = responses[0] if responses else None
            actual_position = _vector3_to_list(info.pose.position)
            # ComputerVision API poses are relative to the initial positions
            # declared in settings.json.
            expected_position = [0.0, 0.0, 0.0]
            position_error = float(
                np.linalg.norm(
                    np.asarray(actual_position, dtype=float)
                    - np.asarray(expected_position, dtype=float)
                )
            )
            validation[camera_id] = {
                "horizontal_fov_deg": float(info.fov),
                "width": 0 if response is None else int(response.width),
                "height": 0 if response is None else int(response.height),
                "actual_position_ned": actual_position,
                "expected_position_ned": expected_position,
                "configured_initial_position_ned": list(
                    self.config.camera_positions[camera_id]
                ),
                "position_error_m": position_error,
                "passed": bool(
                    response is not None
                    and int(response.width) == self.camera_spec.width
                    and int(response.height) == self.camera_spec.height
                    and math.isclose(
                        float(info.fov),
                        self.camera_spec.horizontal_fov_deg,
                        abs_tol=1e-3,
                    )
                    and position_error <= 1e-3
                ),
            }
        return validation

    def _run_formal_episode(
        self,
        airsim_module: Any,
        client: Any,
        target_specs: tuple[TargetSpec, ...],
        target_scale: float,
        settings_path: Path,
    ) -> ExperimentResult:
        config = self.config
        camera_spec = self.camera_spec
        actor_name_by_truth: dict[str, str] = {}
        client.simPause(False)
        for target in target_specs:
            try:
                client.simDestroyObject(target.actor_name)
            except Exception:
                pass
            yaw = math.degrees(
                math.atan2(target.velocity_ned[1], target.velocity_ned[0])
            )
            spawned = client.simSpawnObject(
                target.actor_name,
                target.asset_name,
                _world_pose(airsim_module, target.start_ned, yaw),
                airsim_module.Vector3r(target_scale, target_scale, target_scale),
                False,
            )
            if not spawned:
                raise RuntimeError(f"failed to spawn actor {target.actor_name}")
            actor_name_by_truth[target.truth_id] = self._remember_spawned_actor(
                spawned
            )
            time.sleep(0.01)
        time.sleep(1.50)
        registered_targets = set(
            str(name)
            for name in client.simListSceneObjects(".*")
        )
        missing_targets = sorted(set(actor_name_by_truth.values()) - registered_targets)
        if missing_targets:
            raise RuntimeError(
                f"spawned actors not registered in scene: {missing_targets[:5]}"
            )
        # Use only names returned by this worker. AirSim 1.8.1 may defer
        # destruction across reset; a broad seed wildcard would admit stale
        # actors from a previous attempt into the online detection stream.
        filter_names = tuple(actor_name_by_truth.values())
        for camera_id in config.camera_positions:
            self._configure_detection_filters(client, camera_id, filter_names)
            client.simSetCameraFov(
                config.camera_name,
                camera_spec.horizontal_fov_deg,
                vehicle_name=camera_id,
            )
        prepare_scene_stepping(client, config.deterministic_step_mode)
        fixed_angles = {
            camera_id: look_angles_deg(position, config.corridor_center_ned)
            for camera_id, position in config.camera_positions.items()
        }
        trackers = {
            camera_id: ScanRevisitTracker(
                camera_id, max_coast_s=config.track_coast_s
            )
            for camera_id in config.camera_positions
        }
        gimbal_error_model = GimbalPoseErrorModel(
            scenario_seed=config.seed,
            camera_ids=tuple(config.camera_positions),
            enabled=config.gimbal_pose_error_enabled,
            fixed_bias_mrad=config.gimbal_fixed_bias_mrad,
            jitter_rms_mrad=config.gimbal_jitter_rms_mrad,
        )
        online_detection_rows: list[dict[str, Any]] = []
        offline_detection_rows: list[dict[str, Any]] = []
        gimbal_pose_truth_rows: list[dict[str, Any]] = []
        scan_rows: list[dict[str, Any]] = []
        target_truth_rows: list[dict[str, Any]] = []
        keyframe_rows: list[dict[str, Any]] = []
        uid_truth: dict[str, str] = {}
        rpc_latencies_ms: list[float] = []
        detection_truth_by_camera: dict[str, set[str]] = {
            camera_id: set() for camera_id in config.camera_positions
        }
        target_by_truth = {target.truth_id: target for target in target_specs}
        actor_to_truth = {
            actor_name: truth_id for truth_id, actor_name in actor_name_by_truth.items()
        }
        keyframe_indices = _keyframe_indices(config)
        wall_started = time.perf_counter()
        for frame_index in range(config.frame_count):
            timestamp = frame_index * config.dt_s
            current_positions: dict[str, tuple[float, float, float]] = {}
            for target in target_specs:
                position = target.position_at(timestamp)
                current_positions[target.truth_id] = position
                actor_name = actor_name_by_truth[target.truth_id]
                yaw = math.degrees(
                    math.atan2(target.velocity_ned[1], target.velocity_ned[0])
                )
                moved = frame_index == 0 or _set_object_pose_with_retry(
                    client,
                    actor_name,
                    _world_pose(airsim_module, position, yaw),
                    timeout_s=0.05,
                )
                if not moved:
                    raise RuntimeError(f"failed to move actor {actor_name}")
                target_truth_rows.append(
                    {
                        "frame_index": frame_index,
                        "simulation_timestamp": timestamp,
                        "truth_id": target.truth_id,
                        "actor_name": actor_name,
                        "px_ned_m": position[0],
                        "py_ned_m": position[1],
                        "pz_ned_m": position[2],
                        "vx_ned_mps": target.velocity_ned[0],
                        "vy_ned_mps": target.velocity_ned[1],
                        "vz_ned_mps": target.velocity_ned[2],
                        "offline_truth_only": True,
                    }
                )
            states: dict[str, CameraState] = {}
            actual_states: dict[str, CameraState] = {}
            command_wall_timestamps: dict[str, float] = {}
            for camera_id, position in config.camera_positions.items():
                base_yaw, fixed_pitch = fixed_angles[camera_id]
                scan_timestamp = camera_scan_timestamp(config, camera_id, timestamp)
                yaw = scan_yaw_deg(
                    scan_timestamp,
                    base_yaw,
                    half_span_deg=config.scan_half_span_deg,
                    period_s=config.scan_period_s,
                    mode=config.scan_mode,
                )
                nominal_state = CameraState(
                    camera_id=camera_id,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    position_ned=position,
                    yaw_deg=yaw,
                    pitch_deg=fixed_pitch,
                )
                pose_error = gimbal_error_model.sample(nominal_state)
                actual_state = pose_error.actual_state(nominal_state)
                command_wall_timestamps[camera_id] = time.time()
                client.simSetCameraPose(
                    config.camera_name,
                    _camera_pose(
                        airsim_module,
                        actual_state.yaw_deg,
                        actual_state.pitch_deg,
                    ),
                    vehicle_name=camera_id,
                )
                states[camera_id] = nominal_state
                actual_states[camera_id] = actual_state
                gimbal_pose_truth_rows.append(
                    asdict(pose_error)
                    | {
                        "fixed_radial_mrad": pose_error.fixed_radial_mrad,
                        "jitter_radial_mrad": pose_error.jitter_radial_mrad,
                        "total_radial_mrad": pose_error.total_radial_mrad,
                        "offline_truth_only": True,
                    }
                )
            advance_scene_for_detection(client, config.deterministic_step_mode)
            for camera_id, state in states.items():
                started = time.perf_counter()
                rpc_start_timestamp = time.time()
                raw_detections = _filter_detections_by_actor_name(
                    client.simGetDetections(
                        config.camera_name,
                        airsim_module.ImageType.Scene,
                        vehicle_name=camera_id,
                    ),
                    actor_to_truth,
                )
                latency_ms = (time.perf_counter() - started) * 1000.0
                rpc_end_timestamp = time.time()
                rpc_latencies_ms.append(latency_ms)
                anonymous, offline = self._anonymize_detections(
                    raw_detections,
                    camera_id=camera_id,
                    frame_index=frame_index,
                    timestamp=timestamp,
                    arrival_timestamp=rpc_end_timestamp,
                    gimbal_command_timestamp=command_wall_timestamps[camera_id],
                    detection_rpc_start_timestamp=rpc_start_timestamp,
                    detection_rpc_end_timestamp=rpc_end_timestamp,
                    camera_state=state,
                    offline_camera_state=actual_states[camera_id],
                    current_positions=current_positions,
                    actor_to_truth=actor_to_truth,
                )
                observations: list[RayObservation] = []
                for detection in anonymous:
                    online_detection_rows.append(asdict(detection))
                    observations.append(
                        ray_observation_from_detection(
                            detection,
                            state,
                            camera_spec,
                            scan_period_s=config.scan_period_s,
                            scan_mode=config.scan_mode,
                        )
                    )
                for row in offline:
                    offline_detection_rows.append(row)
                    truth_id = str(row.get("truth_id") or "")
                    if truth_id:
                        uid_truth[str(row["detection_uid"])] = truth_id
                        detection_truth_by_camera[camera_id].add(truth_id)
                current_sweep = tracker_sweep_index(config, timestamp)
                if any(
                    observation.sweep_index != current_sweep
                    for observation in observations
                ):
                    raise RuntimeError(
                        "observation and tracker use different global sweep clocks"
                    )
                trackers[camera_id].update(
                    sweep_index=current_sweep,
                    timestamp=timestamp,
                    observations=observations,
                )
                scan_rows.append(
                    {
                        "camera_id": camera_id,
                        "frame_index": frame_index,
                        "gimbal_command_timestamp": command_wall_timestamps[camera_id],
                        "measurement_timestamp": timestamp,
                        "arrival_timestamp": rpc_end_timestamp,
                        "detection_rpc_start_timestamp": rpc_start_timestamp,
                        "detection_rpc_end_timestamp": rpc_end_timestamp,
                        "measurement_timestamp_source": "scripted_scene_logical_time",
                        "gimbal_command_timestamp_source": "system_wall_clock_unix_s",
                        "arrival_timestamp_source": "system_wall_clock_unix_s",
                        "detection_rpc_timestamp_source": "system_wall_clock_unix_s",
                        "sweep_index": current_sweep,
                        "commanded_yaw_deg": state.yaw_deg,
                        "commanded_pitch_deg": state.pitch_deg,
                        "nominal_yaw_deg": state.yaw_deg,
                        "nominal_pitch_deg": state.pitch_deg,
                        "yaw_deg": state.yaw_deg,
                        "pitch_deg": state.pitch_deg,
                        "detection_count": len(anonymous),
                        "detection_rpc_latency_ms": latency_ms,
                    }
                )
                if self.save_keyframes and frame_index in keyframe_indices:
                    keyframe = self._capture_keyframe(
                        airsim_module,
                        client,
                        camera_id,
                        frame_index,
                        timestamp,
                    )
                    if keyframe is not None:
                        keyframe_rows.append(keyframe)
        wall_duration_s = time.perf_counter() - wall_started
        for tracker in trackers.values():
            tracker.flush()
        tracks_a = trackers[config.camera_a_name].stable_tracks(
            config.stable_sweep_count
        )
        tracks_b = trackers[config.camera_b_name].stable_tracks(
            config.stable_sweep_count
        )
        association_started = time.perf_counter()
        association = associate_tracks(
            tracks_a,
            tracks_b,
            expected_speed_mps=config.target_speed_mps,
            max_time_delta_s=config.max_cross_camera_time_delta_s,
        )
        association_wall_ms = (time.perf_counter() - association_started) * 1000.0
        enhanced_started = time.perf_counter()
        enhanced_association = associate_tracks_temporally(
            tracks_a,
            tracks_b,
            config=AssociationConfig(
                expected_speed_mps=config.target_speed_mps,
                max_time_delta_s=config.max_cross_camera_time_delta_s,
            ),
        )
        enhanced_association_wall_ms = (
            time.perf_counter() - enhanced_started
        ) * 1000.0
        geometry_sensitivity = estimate_geometry_sensitivity(
            enhanced_association.selected_matches,
            tracks_a,
            tracks_b,
            angular_noise_mrad=0.15,
            sample_count=1000,
            seed=config.seed,
        )
        return self._write_formal_outputs(
            settings_path=settings_path,
            target_specs=target_specs,
            target_scale=target_scale,
            actor_name_by_truth=actor_name_by_truth,
            trackers=trackers,
            tracks_a=tracks_a,
            tracks_b=tracks_b,
            association=association,
            enhanced_association=enhanced_association,
            geometry_sensitivity=geometry_sensitivity,
            online_detection_rows=online_detection_rows,
            offline_detection_rows=offline_detection_rows,
            gimbal_pose_truth_rows=gimbal_pose_truth_rows,
            scan_rows=scan_rows,
            target_truth_rows=target_truth_rows,
            keyframe_rows=keyframe_rows,
            uid_truth=uid_truth,
            detection_truth_by_camera=detection_truth_by_camera,
            target_by_truth=target_by_truth,
            rpc_latencies_ms=rpc_latencies_ms,
            wall_duration_s=wall_duration_s,
            association_wall_ms=association_wall_ms,
            enhanced_association_wall_ms=enhanced_association_wall_ms,
        )

    def _configure_detection_filters(
        self, client: Any, camera_id: str, names: Sequence[str]
    ) -> None:
        config = self.config
        import airsim

        client.simClearDetectionMeshNames(
            config.camera_name,
            airsim.ImageType.Scene,
            vehicle_name=camera_id,
        )
        client.simSetDetectionFilterRadius(
            config.camera_name,
            airsim.ImageType.Scene,
            350_000,
            vehicle_name=camera_id,
        )
        for name in dict.fromkeys(str(item) for item in names if str(item)):
            client.simAddDetectionFilterMeshName(
                config.camera_name,
                airsim.ImageType.Scene,
                name,
                vehicle_name=camera_id,
            )

    def _anonymize_detections(
        self,
        raw_detections: Sequence[Any],
        *,
        camera_id: str,
        frame_index: int,
        timestamp: float,
        arrival_timestamp: float,
        gimbal_command_timestamp: float | None = None,
        detection_rpc_start_timestamp: float | None = None,
        detection_rpc_end_timestamp: float | None = None,
        camera_state: CameraState,
        offline_camera_state: CameraState | None = None,
        current_positions: Mapping[str, tuple[float, float, float]],
        actor_to_truth: Mapping[str, str],
    ) -> tuple[list[AnonymousDetection], list[dict[str, Any]]]:
        anonymous: list[AnonymousDetection] = []
        offline: list[dict[str, Any]] = []
        boxes: list[tuple[float, float, float, float]] = []
        for raw in raw_detections:
            bbox = _bbox2d(raw)
            if bbox is None:
                continue
            boxes.append(bbox)
        truth_assignments = _offline_truth_assignments(
            boxes,
            current_positions,
            offline_camera_state or camera_state,
            self.camera_spec,
        )
        box_index = 0
        for raw_index, raw in enumerate(raw_detections):
            bbox = _bbox2d(raw)
            if bbox is None:
                continue
            detection_uid = f"{camera_id}-F{frame_index:05d}-D{box_index:03d}"
            center = ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5)
            anonymous.append(
                AnonymousDetection(
                    detection_uid=detection_uid,
                    camera_id=camera_id,
                    frame_index=frame_index,
                    measurement_timestamp=timestamp,
                    arrival_timestamp=arrival_timestamp,
                    bbox_xyxy=bbox,
                    center_px=center,
                    confidence=1.0,
                    gimbal_command_timestamp=timestamp
                    if gimbal_command_timestamp is None
                    else gimbal_command_timestamp,
                    detection_rpc_start_timestamp=timestamp
                    if detection_rpc_start_timestamp is None
                    else detection_rpc_start_timestamp,
                    detection_rpc_end_timestamp=arrival_timestamp
                    if detection_rpc_end_timestamp is None
                    else detection_rpc_end_timestamp,
                    measurement_timestamp_source="scripted_scene_logical_time",
                    gimbal_command_timestamp_source=(
                        "system_wall_clock_unix_s"
                        if gimbal_command_timestamp is not None
                        else "scripted_scene_logical_time_legacy_fallback"
                    ),
                    arrival_timestamp_source=(
                        "system_wall_clock_unix_s"
                        if detection_rpc_end_timestamp is not None
                        else "producer_clock_unspecified"
                    ),
                    detection_rpc_timestamp_source=(
                        "system_wall_clock_unix_s"
                        if detection_rpc_start_timestamp is not None
                        and detection_rpc_end_timestamp is not None
                        else "scripted_scene_logical_time_legacy_fallback"
                    ),
                )
            )
            raw_name = str(getattr(raw, "name", "") or "")
            truth_id = actor_to_truth.get(raw_name, "")
            assignment = truth_assignments.get(box_index)
            if not truth_id and assignment is not None:
                truth_id = assignment[0]
            offline.append(
                {
                    "detection_uid": detection_uid,
                    "camera_id": camera_id,
                    "frame_index": frame_index,
                    "measurement_timestamp": timestamp,
                    "truth_id": truth_id,
                    "raw_detection_name": raw_name,
                    "truth_assignment_pixel_error": None
                    if assignment is None
                    else assignment[1],
                    "relative_pose": _pose_to_dict(
                        getattr(raw, "relative_pose", None)
                    ),
                    "box3d": _box3d_to_dict(getattr(raw, "box3D", None)),
                    "offline_truth_only": True,
                }
            )
            box_index += 1
        return anonymous, offline

    def _capture_keyframe(
        self,
        airsim_module: Any,
        client: Any,
        camera_id: str,
        frame_index: int,
        timestamp: float,
    ) -> dict[str, Any] | None:
        responses = client.simGetImages(
            [
                airsim_module.ImageRequest(
                    self.config.camera_name,
                    airsim_module.ImageType.Scene,
                    False,
                    True,
                )
            ],
            vehicle_name=camera_id,
        )
        if not responses or not responses[0].image_data_uint8:
            return None
        response = responses[0]
        relative = Path("keyframes") / camera_id / f"frame_{frame_index:05d}.png"
        path = self.output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(response.image_data_uint8))
        return {
            "camera_id": camera_id,
            "frame_index": frame_index,
            "measurement_timestamp": timestamp,
            "airsim_image_timestamp": int(getattr(response, "time_stamp", 0)),
            "width": int(response.width),
            "height": int(response.height),
            "path": str(relative),
        }

    def _write_formal_outputs(
        self,
        *,
        settings_path: Path,
        target_specs: tuple[TargetSpec, ...],
        target_scale: float,
        actor_name_by_truth: Mapping[str, str],
        trackers: Mapping[str, ScanRevisitTracker],
        tracks_a: tuple[BearingTrack, ...],
        tracks_b: tuple[BearingTrack, ...],
        association: CrossAssociationResult,
        enhanced_association: TemporalAssociationResult,
        geometry_sensitivity: tuple[GeometrySensitivity, ...],
        online_detection_rows: list[dict[str, Any]],
        offline_detection_rows: list[dict[str, Any]],
        gimbal_pose_truth_rows: list[dict[str, Any]],
        scan_rows: list[dict[str, Any]],
        target_truth_rows: list[dict[str, Any]],
        keyframe_rows: list[dict[str, Any]],
        uid_truth: Mapping[str, str],
        detection_truth_by_camera: Mapping[str, set[str]],
        target_by_truth: Mapping[str, TargetSpec],
        rpc_latencies_ms: list[float],
        wall_duration_s: float,
        association_wall_ms: float,
        enhanced_association_wall_ms: float,
    ) -> ExperimentResult:
        online_dir = self.output_dir / "online"
        truth_dir = self.output_dir / "truth"
        track_rows: list[dict[str, Any]] = []
        sample_rows: list[dict[str, Any]] = []
        uid_to_track: dict[str, str] = {}
        track_truth_rows: list[dict[str, Any]] = []
        track_truth: dict[str, str] = {}
        for tracker in trackers.values():
            for track in tracker.tracks:
                stable = track.is_stable(self.config.stable_sweep_count)
                track_rows.append(
                    {
                        "track_id": track.track_id,
                        "camera_id": track.camera_id,
                        "stable": stable,
                        "sweep_count": track.stable_sweep_count,
                        "sample_count": len(track.samples),
                        "first_timestamp": track.samples[0].timestamp,
                        "last_timestamp": track.samples[-1].timestamp,
                    }
                )
                for sample_index, sample in enumerate(track.samples):
                    sample_rows.append(
                        {
                            "track_id": track.track_id,
                            "camera_id": track.camera_id,
                            "sample_index": sample_index,
                            "sweep_index": sample.sweep_index,
                            "measurement_timestamp": sample.timestamp,
                            "ray_x_ned": sample.direction_ned[0],
                            "ray_y_ned": sample.direction_ned[1],
                            "ray_z_ned": sample.direction_ned[2],
                            "azimuth_deg": sample.azimuth_deg,
                            "elevation_deg": sample.elevation_deg,
                            "detection_uids": list(sample.detection_uids),
                        }
                    )
                    for uid in sample.detection_uids:
                        uid_to_track[uid] = track.track_id
                truth_values = [
                    uid_truth[uid]
                    for uid in track.detection_uids
                    if uid in uid_truth and uid_truth[uid]
                ]
                counts = Counter(truth_values)
                majority_truth, majority_count = (
                    counts.most_common(1)[0] if counts else ("", 0)
                )
                purity = majority_count / len(truth_values) if truth_values else None
                if majority_truth:
                    track_truth[track.track_id] = majority_truth
                track_truth_rows.append(
                    {
                        "track_id": track.track_id,
                        "camera_id": track.camera_id,
                        "stable": stable,
                        "majority_truth_id": majority_truth,
                        "purity": purity,
                        "scored_detection_count": len(truth_values),
                        "offline_truth_only": True,
                    }
                )
        candidate_rows = [asdict(item) for item in association.candidates]
        match_rows = [asdict(item) for item in association.matches]
        epipolar_rows = [
            asdict(item) for item in enhanced_association.epipolar_evidence
        ]
        enhanced_candidate_rows = [
            asdict(item) for item in enhanced_association.fitted_candidates
        ]
        confirmed_pairs = {
            (item.track_a_id, item.track_b_id)
            for item in enhanced_association.confirmed_matches
        }
        enhanced_match_rows = [
            asdict(item)
            | {
                "confirmation_state": (
                    "confirmed"
                    if (item.track_a_id, item.track_b_id) in confirmed_pairs
                    else "pending"
                )
            }
            for item in enhanced_association.selected_matches
        ]
        decision_rows = [asdict(item) for item in enhanced_association.decisions]
        hypothesis_history_rows = [
            asdict(item) for item in enhanced_association.hypothesis_history
        ]
        state_rows = [asdict(item) for item in enhanced_association.state_history]
        fragment_suppression_rows = [
            asdict(item) for item in enhanced_association.fragment_suppressions
        ]
        geometry_rows = [asdict(item) for item in geometry_sensitivity]
        scored_match_rows: list[dict[str, Any]] = []
        correct_truth_ids: list[str] = []
        position_errors: list[float] = []
        velocity_errors: list[float] = []
        for match in association.matches:
            truth_a = track_truth.get(match.track_a_id, "")
            truth_b = track_truth.get(match.track_b_id, "")
            correct = bool(truth_a and truth_a == truth_b)
            position_error = None
            velocity_error = None
            if correct:
                correct_truth_ids.append(truth_a)
                target = target_by_truth[truth_a]
                position_error = float(
                    np.linalg.norm(
                        np.asarray(match.position_ned)
                        - np.asarray(target.position_at(match.reference_timestamp))
                    )
                )
                velocity_error = float(
                    np.linalg.norm(
                        np.asarray(match.velocity_ned)
                        - np.asarray(target.velocity_ned)
                    )
                )
                position_errors.append(position_error)
                velocity_errors.append(velocity_error)
            scored_match_rows.append(
                {
                    "match_id": match.match_id,
                    "track_a_id": match.track_a_id,
                    "track_b_id": match.track_b_id,
                    "truth_a": truth_a,
                    "truth_b": truth_b,
                    "correct": correct,
                    "position_error_m": position_error,
                    "velocity_error_mps": velocity_error,
                    "offline_truth_only": True,
                }
            )
        enhanced_scored_rows: list[dict[str, Any]] = []
        enhanced_correct_truth_ids: list[str] = []
        enhanced_confirmed_truth_ids: list[str] = []
        for match in enhanced_association.selected_matches:
            truth_a = track_truth.get(match.track_a_id, "")
            truth_b = track_truth.get(match.track_b_id, "")
            correct = bool(truth_a and truth_a == truth_b)
            confirmed = (match.track_a_id, match.track_b_id) in confirmed_pairs
            if correct:
                enhanced_correct_truth_ids.append(truth_a)
                if confirmed:
                    enhanced_confirmed_truth_ids.append(truth_a)
            enhanced_scored_rows.append(
                {
                    "match_id": match.match_id,
                    "track_a_id": match.track_a_id,
                    "track_b_id": match.track_b_id,
                    "truth_a": truth_a,
                    "truth_b": truth_b,
                    "correct": correct,
                    "confirmation_state": "confirmed" if confirmed else "pending",
                    "offline_truth_only": True,
                }
            )
        stable_truth_by_camera: dict[str, set[str]] = {}
        for camera_id in self.config.camera_positions:
            stable_truth_by_camera[camera_id] = {
                track_truth[track.track_id]
                for track in trackers[camera_id].stable_tracks(
                    self.config.stable_sweep_count
                )
                if track.track_id in track_truth
            }
        eligible_truth = set.intersection(*stable_truth_by_camera.values())
        correct_count = sum(bool(row["correct"]) for row in scored_match_rows)
        precision = (
            correct_count / len(scored_match_rows) if scored_match_rows else None
        )
        full_recall = correct_count / self.config.target_count
        eligible_recall = (
            correct_count / len(eligible_truth) if eligible_truth else None
        )
        duplicate_truth_match_count = sum(
            max(0, count - 1) for count in Counter(correct_truth_ids).values()
        )
        enhanced_correct_count = sum(
            bool(row["correct"]) for row in enhanced_scored_rows
        )
        enhanced_false_count = (
            len(enhanced_scored_rows) - enhanced_correct_count
        )
        enhanced_unique_correct_truth = set(enhanced_correct_truth_ids)
        enhanced_precision = (
            enhanced_correct_count / len(enhanced_scored_rows)
            if enhanced_scored_rows
            else None
        )
        enhanced_full_recall = (
            len(enhanced_unique_correct_truth) / self.config.target_count
        )
        enhanced_confirmed_recall = (
            len(set(enhanced_confirmed_truth_ids)) / self.config.target_count
        )
        enhanced_duplicate_truth_match_count = sum(
            max(0, count - 1)
            for count in Counter(enhanced_correct_truth_ids).values()
        )
        coarse_preserved_truth_ids = {
            track_truth[item.track_a_id]
            for item in enhanced_association.epipolar_evidence
            if item.gate_passed
            and item.track_a_id in track_truth
            and item.track_b_id in track_truth
            and track_truth[item.track_a_id] == track_truth[item.track_b_id]
        }
        fit_reduction_ratio = 1.0 - enhanced_association.fit_evaluation_count / max(
            enhanced_association.full_pair_count, 1
        )
        online_records = [
            *online_detection_rows,
            *scan_rows,
            *track_rows,
            *sample_rows,
            *candidate_rows,
            *match_rows,
            *epipolar_rows,
            *enhanced_candidate_rows,
            *enhanced_match_rows,
            *decision_rows,
            *hypothesis_history_rows,
            *state_rows,
            *fragment_suppression_rows,
            *geometry_rows,
        ]
        leakage_keys = online_truth_leakage_keys(online_records)
        pitch_by_camera = {
            camera_id: [
                float(row["pitch_deg"])
                for row in scan_rows
                if row["camera_id"] == camera_id
            ]
            for camera_id in self.config.camera_positions
        }
        scaling_metrics = pair_scaling_metrics(
            self.config.target_count, len(tracks_a), len(tracks_b)
        )
        metrics = {
            "schema_version": METRICS_SCHEMA_V3,
            "independent_experiment": True,
            "connected_d_modules": [],
            "seed": self.config.seed,
            "target_count": self.config.target_count,
            "spawned_target_count": len(actor_name_by_truth),
            "target_scale_multiplier": target_scale,
            "target_speed_mps": self.config.target_speed_mps,
            "minimum_target_separation_m": minimum_target_separation(
                target_specs, self.config.duration_s
            ),
            "camera_detection_coverage": {
                camera_id: len(values) / self.config.target_count
                for camera_id, values in detection_truth_by_camera.items()
            },
            "stable_track_count": {
                camera_id: len(
                    trackers[camera_id].stable_tracks(
                        self.config.stable_sweep_count
                    )
                )
                for camera_id in self.config.camera_positions
            },
            **scaling_metrics,
            "stable_track_truth_coverage": {
                camera_id: len(values) / self.config.target_count
                for camera_id, values in stable_truth_by_camera.items()
            },
            "eligible_cross_camera_truth_count": len(eligible_truth),
            "candidate_count": len(association.candidates),
            "valid_candidate_count": sum(
                candidate.valid for candidate in association.candidates
            ),
            "match_count": len(association.matches),
            "correct_match_count": correct_count,
            "false_match_count": len(association.matches) - correct_count,
            "association_precision": precision,
            "association_full_target_recall": full_recall,
            "association_eligible_recall": eligible_recall,
            "duplicate_truth_match_count": duplicate_truth_match_count,
            "legacy_no_duplicate_match_passed": duplicate_truth_match_count == 0,
            "unmatched_a_count": len(association.unmatched_a_track_ids),
            "unmatched_b_count": len(association.unmatched_b_track_ids),
            "position_error_mean_m": _mean(position_errors),
            "position_error_p95_m": _percentile(position_errors, 95.0),
            "velocity_error_mean_mps": _mean(velocity_errors),
            "velocity_error_p95_mps": _percentile(velocity_errors, 95.0),
            "online_truth_leakage_count": len(leakage_keys),
            "online_truth_leakage_keys": list(leakage_keys),
            "fixed_pitch_span_deg": {
                camera_id: max(values) - min(values) if values else None
                for camera_id, values in pitch_by_camera.items()
            },
            "configured_detection_request_rate_hz": self.config.sample_rate_hz,
            "detection_rpc_latency_mean_ms": _mean(rpc_latencies_ms),
            "detection_rpc_latency_p95_ms": _percentile(rpc_latencies_ms, 95.0),
            "formal_episode_wall_duration_s": wall_duration_s,
            "detection_rpc_wall_rate_hz": (
                len(rpc_latencies_ms) / wall_duration_s
                if wall_duration_s > 0.0
                else None
            ),
            "cross_camera_association_wall_ms": association_wall_ms,
            "enhanced_cross_camera_association_wall_ms": enhanced_association_wall_ms,
            "candidate_screening_elapsed_ms": (
                enhanced_association.candidate_screening_elapsed_ms
            ),
            "candidate_fitting_elapsed_ms": (
                enhanced_association.candidate_fitting_elapsed_ms
            ),
            "association_processing_elapsed_ms": (
                enhanced_association.processing_elapsed_ms
            ),
            "enhanced_association": {
                "schema_version": TEMPORAL_ASSOCIATION_SCHEMA_V3,
                "coplanarity_gate_mrad": enhanced_association.config.coplanarity_median_gate_mrad,
                "full_pair_count": enhanced_association.full_pair_count,
                "coarse_gate_pass_count": enhanced_association.coarse_gate_pass_count,
                "fit_evaluation_count": enhanced_association.fit_evaluation_count,
                "candidate_screening_elapsed_ms": (
                    enhanced_association.candidate_screening_elapsed_ms
                ),
                "candidate_fitting_elapsed_ms": (
                    enhanced_association.candidate_fitting_elapsed_ms
                ),
                "processing_elapsed_ms": enhanced_association.processing_elapsed_ms,
                "fit_reduction_ratio": fit_reduction_ratio,
                "valid_fit_count": sum(
                    item.valid for item in enhanced_association.fitted_candidates
                ),
                "top_k_hypothesis_count": len(enhanced_association.hypotheses),
                "selected_match_count": len(enhanced_association.selected_matches),
                "confirmed_match_count": len(enhanced_association.confirmed_matches),
                "pending_selected_match_count": len(enhanced_association.selected_matches)
                - len(enhanced_association.confirmed_matches),
                "fragment_suppression_count": len(
                    enhanced_association.fragment_suppressions
                ),
                "fragment_merge_position_gate_m": enhanced_association.config.fragment_merge_position_gate_m,
                "fragment_merge_velocity_gate_mps": enhanced_association.config.fragment_merge_velocity_gate_mps,
                "correct_match_count": enhanced_correct_count,
                "false_match_count": enhanced_false_count,
                "association_precision": enhanced_precision,
                "association_full_target_recall": enhanced_full_recall,
                "confirmed_full_target_recall": enhanced_confirmed_recall,
                "duplicate_truth_match_count": enhanced_duplicate_truth_match_count,
                "coarse_preserved_truth_count": len(coarse_preserved_truth_ids),
                "coarse_preserved_all_targets": len(coarse_preserved_truth_ids)
                == self.config.target_count,
                "geometry_sensitivity_evidence_label": "modeled_geometry_sensitivity",
                "geometry_sensitivity_record_count": len(geometry_sensitivity),
                "geometry_sensitivity_p50_median_m": _percentile(
                    [item.position_sensitivity_p50_m for item in geometry_sensitivity],
                    50.0,
                ),
                "geometry_sensitivity_p95_median_m": _percentile(
                    [item.position_sensitivity_p95_m for item in geometry_sensitivity],
                    50.0,
                ),
                "intersection_angle_median_deg": _percentile(
                    [item.intersection_angle_deg for item in geometry_sensitivity],
                    50.0,
                ),
            },
            "keyframe_count": len(keyframe_rows),
            "acceptance": {
                "truth_isolation_passed": len(leakage_keys) == 0,
                "spawn_passed": len(actor_name_by_truth) == self.config.target_count,
                "fixed_pitch_passed": all(
                    math.isclose(max(values) - min(values), 0.0, abs_tol=1e-9)
                    for values in pitch_by_camera.values()
                    if values
                ),
                "no_duplicate_match_passed": (
                    enhanced_duplicate_truth_match_count == 0
                ),
                "precision_target_passed": precision is not None and precision >= 0.95,
                "recall_target_passed": full_recall >= 0.80,
                "stable_coverage_target_passed": all(
                    len(values) / self.config.target_count >= 0.80
                    for values in stable_truth_by_camera.values()
                ),
                "enhanced_false_association_non_regression_passed": (
                    enhanced_false_count <= len(association.matches) - correct_count
                ),
                "enhanced_recall_target_passed": enhanced_full_recall >= 0.900,
                "enhanced_fit_reduction_passed": fit_reduction_ratio >= 0.80,
                "enhanced_no_duplicate_match_passed": (
                    enhanced_duplicate_truth_match_count == 0
                ),
            },
        }
        metrics["acceptance"]["overall_passed"] = all(
            bool(value) for value in metrics["acceptance"].values()
        )
        output_paths = {
            "anonymous_detections": write_csv(
                online_dir / "anonymous_detections.csv", online_detection_rows
            ),
            "camera_scan": write_csv(online_dir / "camera_scan.csv", scan_rows),
            "local_tracks": write_csv(online_dir / "local_tracks.csv", track_rows),
            "local_track_samples": write_csv(
                online_dir / "local_track_samples.csv", sample_rows
            ),
            "cross_camera_candidates": write_csv(
                online_dir / "cross_camera_candidates.csv", candidate_rows
            ),
            "cross_camera_matches": write_csv(
                online_dir / "cross_camera_matches.csv", match_rows
            ),
            "epipolar_evidence_v2": write_csv(
                online_dir / "epipolar_evidence_v2.csv", epipolar_rows
            ),
            "enhanced_candidates_v2": write_csv(
                online_dir / "enhanced_candidates_v2.csv", enhanced_candidate_rows
            ),
            "enhanced_matches_v2": write_csv(
                online_dir / "enhanced_matches_v2.csv", enhanced_match_rows
            ),
            "association_decisions_v2": write_csv(
                online_dir / "association_decisions_v2.csv", decision_rows
            ),
            "association_hypothesis_history_v2": write_csv(
                online_dir / "association_hypothesis_history_v2.csv",
                hypothesis_history_rows,
            ),
            "association_state_timeline_v2": write_csv(
                online_dir / "association_state_timeline_v2.csv", state_rows
            ),
            "fragment_suppressions_v2": write_csv(
                online_dir / "fragment_suppressions_v2.csv",
                fragment_suppression_rows,
            ),
            "global_hypotheses_v2": write_json(
                online_dir / "global_hypotheses_v2.json",
                [asdict(item) for item in enhanced_association.hypotheses],
            ),
            "geometry_sensitivity_v2": write_csv(
                online_dir / "geometry_sensitivity_v2.csv", geometry_rows
            ),
            "detection_truth": write_csv(
                truth_dir / "detection_truth.csv", offline_detection_rows
            ),
            "target_trajectories": write_csv(
                truth_dir / "target_trajectories.csv", target_truth_rows
            ),
            "gimbal_pose_truth": write_csv(
                truth_dir / "gimbal_pose_truth.csv", gimbal_pose_truth_rows
            ),
            "track_scoring": write_csv(
                truth_dir / "track_scoring.csv", track_truth_rows
            ),
            "match_scoring": write_csv(
                truth_dir / "match_scoring.csv", scored_match_rows
            ),
            "enhanced_match_scoring_v2": write_csv(
                truth_dir / "enhanced_match_scoring_v2.csv", enhanced_scored_rows
            ),
            "keyframe_manifest": write_csv(
                self.output_dir / "keyframes" / "manifest.csv", keyframe_rows
            ),
        }
        metrics_path = write_json(self.output_dir / "metrics.json", metrics)
        output_paths["metrics"] = metrics_path
        output_paths["manifest"] = write_json(
            self.output_dir / "record_manifest.json",
            {
                "schema_version": RECORD_MANIFEST_SCHEMA_V3,
                "independent_experiment": True,
                "settings": str(settings_path),
                "artifacts": {
                    key: str(path.relative_to(self.output_dir))
                    for key, path in output_paths.items()
                },
                "keyframes": keyframe_rows,
                "video_generated": False,
            },
        )
        return ExperimentResult(
            output_dir=self.output_dir,
            settings_path=settings_path,
            metrics_path=metrics_path,
            metrics=metrics,
            output_paths=output_paths,
            tracks_a=tracks_a,
            tracks_b=tracks_b,
            association=association,
            target_specs=target_specs,
            enhanced_association=enhanced_association,
            geometry_sensitivity=geometry_sensitivity,
        )



def _offline_truth_assignments(
    boxes: Sequence[tuple[float, float, float, float]],
    current_positions: Mapping[str, tuple[float, float, float]],
    camera_state: CameraState,
    camera_spec: CameraSpec,
) -> dict[int, tuple[str, float]]:
    projections: list[tuple[str, tuple[float, float]]] = []
    for truth_id, position in current_positions.items():
        pixel = project_world_point(position, camera_state, camera_spec)
        if pixel is None:
            continue
        if -100.0 <= pixel[0] <= camera_spec.width + 100.0 and -100.0 <= pixel[1] <= camera_spec.height + 100.0:
            projections.append((truth_id, pixel))
    if not boxes or not projections:
        return {}
    costs = np.full((len(boxes), len(projections)), 1e6, dtype=float)
    for row, bbox in enumerate(boxes):
        center = np.asarray(
            ((bbox[0] + bbox[2]) * 0.5, (bbox[1] + bbox[3]) * 0.5),
            dtype=float,
        )
        for column, (_truth_id, pixel) in enumerate(projections):
            error = float(np.linalg.norm(center - np.asarray(pixel, dtype=float)))
            if error <= 80.0:
                costs[row, column] = error
    rows, columns = linear_sum_assignment(costs)
    assignments: dict[int, tuple[str, float]] = {}
    for row, column in zip(rows, columns):
        if costs[row, column] >= 1e5:
            continue
        assignments[int(row)] = (projections[column][0], float(costs[row, column]))
    return assignments


def _keyframe_indices(config: ScenarioConfig) -> set[int]:
    indices: set[int] = set()
    for start in np.arange(0.0, config.duration_s + 1e-9, 2.0):
        for offset in (0.25, 0.75):
            timestamp = float(start + offset)
            if timestamp <= config.duration_s:
                indices.add(int(round(timestamp * config.sample_rate_hz)))
    return indices


def _camera_pose(airsim_module: Any, yaw_deg: float, pitch_deg: float) -> Any:
    return airsim_module.Pose(
        airsim_module.Vector3r(0.0, 0.0, 0.0),
        airsim_module.to_quaternion(
            math.radians(pitch_deg), 0.0, math.radians(yaw_deg)
        ),
    )


def _world_pose(
    airsim_module: Any, position: Sequence[float], yaw_deg: float
) -> Any:
    return airsim_module.Pose(
        airsim_module.Vector3r(
            float(position[0]), float(position[1]), float(position[2])
        ),
        airsim_module.to_quaternion(0.0, 0.0, math.radians(yaw_deg)),
    )


def _find_detection(
    client: Any,
    airsim_module: Any,
    config: ScenarioConfig,
    camera_id: str,
    *,
    expected_name: str | None = None,
) -> Any | None:
    detections = client.simGetDetections(
        config.camera_name,
        airsim_module.ImageType.Scene,
        vehicle_name=camera_id,
    )
    if expected_name is None:
        return detections[0] if detections else None
    return next(
        (
            detection
            for detection in detections
            if str(getattr(detection, "name", "")) == expected_name
        ),
        None,
    )


def _filter_detections_by_actor_name(
    detections: Sequence[Any], allowed_names: Iterable[str]
) -> list[Any]:
    allowed = frozenset(str(name) for name in allowed_names if str(name))
    return [
        detection
        for detection in detections
        if str(getattr(detection, "name", "") or "") in allowed
    ]


def _wait_for_detection_extent(
    client: Any,
    airsim_module: Any,
    config: ScenarioConfig,
    camera_id: str,
    *,
    expected_name: str | None = None,
    expected_extent_m: float,
    tolerance_m: float,
    timeout_s: float,
) -> tuple[Any | None, float | None]:
    """Wait until AirSim refreshes box3D after a runtime scale update."""

    deadline = time.monotonic() + float(timeout_s)
    last_detection: Any | None = None
    last_extent: float | None = None
    while time.monotonic() < deadline:
        last_detection = _find_detection(
            client,
            airsim_module,
            config,
            camera_id,
            expected_name=expected_name,
        )
        last_extent = _box3d_longest_extent(last_detection)
        if (
            last_extent is not None
            and abs(last_extent - expected_extent_m) <= tolerance_m
        ):
            return last_detection, last_extent
        time.sleep(0.05)
    return last_detection, last_extent


def _set_object_pose_with_retry(
    client: Any, object_name: str, pose: Any, *, timeout_s: float
) -> bool:
    deadline = time.monotonic() + float(timeout_s)
    while True:
        try:
            if bool(client.simSetObjectPose(object_name, pose, True)):
                return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)


def _wait_for_detection(
    client: Any,
    airsim_module: Any,
    config: ScenarioConfig,
    camera_id: str,
    *,
    expected_name: str | None = None,
    timeout_s: float,
) -> Any | None:
    deadline = time.monotonic() + float(timeout_s)
    while time.monotonic() < deadline:
        detection = _find_detection(
            client,
            airsim_module,
            config,
            camera_id,
            expected_name=expected_name,
        )
        if detection is not None:
            return detection
        try:
            client.simGetImages(
                [
                    airsim_module.ImageRequest(
                        config.camera_name,
                        airsim_module.ImageType.Scene,
                        False,
                        True,
                    )
                ],
                vehicle_name=camera_id,
            )
        except Exception:
            pass
        time.sleep(0.25)
    return None


def _box3d_longest_extent(detection: Any | None) -> float | None:
    if detection is None:
        return None
    box = getattr(detection, "box3D", None)
    if box is None:
        return None
    minimum = getattr(box, "min", None)
    maximum = getattr(box, "max", None)
    if minimum is None or maximum is None:
        return None
    extents = (
        abs(float(maximum.x_val) - float(minimum.x_val)),
        abs(float(maximum.y_val) - float(minimum.y_val)),
        abs(float(maximum.z_val) - float(minimum.z_val)),
    )
    longest = max(extents)
    return longest if math.isfinite(longest) and longest > 0.0 else None


def _bbox2d(detection: Any) -> tuple[float, float, float, float] | None:
    box = getattr(detection, "box2D", None)
    if box is None or getattr(box, "min", None) is None or getattr(box, "max", None) is None:
        return None
    bbox = (
        float(box.min.x_val),
        float(box.min.y_val),
        float(box.max.x_val),
        float(box.max.y_val),
    )
    if not all(math.isfinite(value) for value in bbox):
        return None
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return bbox


def _pose_to_dict(pose: Any | None) -> dict[str, Any] | None:
    if pose is None:
        return None
    position = getattr(pose, "position", None)
    orientation = getattr(pose, "orientation", None)
    return {
        "position": _vector3_to_list(position),
        "orientation_xyzw": None
        if orientation is None
        else [
            float(orientation.x_val),
            float(orientation.y_val),
            float(orientation.z_val),
            float(orientation.w_val),
        ],
    }


def _box3d_to_dict(box: Any | None) -> dict[str, Any] | None:
    if box is None:
        return None
    return {
        "min": _vector3_to_list(getattr(box, "min", None)),
        "max": _vector3_to_list(getattr(box, "max", None)),
    }


def _vector3_to_list(vector: Any | None) -> list[float] | None:
    if vector is None:
        return None
    return [float(vector.x_val), float(vector.y_val), float(vector.z_val)]


def _tcp_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=0.2):
            return True
    except OSError:
        return False


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    row_list = [dict(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(key for row in row_list for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        if fieldnames:
            writer = csv.DictWriter(
                stream, fieldnames=fieldnames, lineterminator="\n"
            )
            writer.writeheader()
            for row in row_list:
                writer.writerow(
                    {key: _csv_value(row.get(key)) for key in fieldnames}
                )
    return path


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _csv_value(value: Any) -> Any:
    if isinstance(value, (Mapping, list, tuple, np.ndarray)):
        return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=True)
    return value


def _mean(values: Sequence[float]) -> float | None:
    return None if not values else float(np.mean(np.asarray(values, dtype=float)))


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    return (
        None
        if not values
        else float(np.percentile(np.asarray(values, dtype=float), percentile))
    )
