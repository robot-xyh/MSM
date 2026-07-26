"""Independent hard cross-view curriculum for D5 sparse tracklet graphs.

The producer uses physical 3-D points, pinhole projection, anonymous camera-local
tracklets, and the unchanged :class:`SparseTrackletGraphConfig` candidate gates.
Evaluator identity is joined only after graph construction and is stored in a
separate compressed lineage artifact.  The frozen formal corpus is read only
for provenance and duplicate checks.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence
import uuid

import numpy as np

from .canonical_seed_view import _load_registry_binding
from .models import CameraModel
from .sparse_tracklet_graph import (
    CameraLocalTracklet,
    SparseTrackletGraph,
    SparseTrackletGraphConfig,
    TrackletCameraGeometry,
    build_sparse_tracklet_graph,
)
from .tracklet_dataset import (
    LoadedTrackletDataset,
    TrackletDatasetValidationError,
    finalize_tracklet_dataset,
    join_offline_observation_labels,
    load_tracklet_dataset,
    sha256_file,
    stage_tracklet_dataset_episode,
)


SUPPLEMENTAL_CURRICULUM_SCHEMA_VERSION = "d5.tracklet-supplemental-curriculum.v1"
SUPPLEMENTAL_MANIFEST_SCHEMA_VERSION = "d5.tracklet-supplemental-manifest.v1"
SUPPLEMENTAL_LINEAGE_SCHEMA_VERSION = "d5.tracklet-supplemental-lineage.v1"
SUPPLEMENTAL_PROFILE_VERSION = "d5-tracklet-hard-crossview-full-v1"
SUPPLEMENTAL_SMOKE_PROFILE_VERSION = "d5-tracklet-hard-crossview-smoke-v1"
SUPPLEMENTAL_RNG_NAMESPACE = "d5-tracklet-hard-crossview-independent-rng-v1"
SUPPLEMENTAL_FRAME_COUNT_PER_CELL_SEED = 1
CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION = (
    "d5-camera-local-kinematic-measurement-noise-v1"
)
CAMERA_LOCAL_BBOX_LOG_SIDE_SIGMA = 0.04
CAMERA_LOCAL_SCALE_RATE_SIGMA_S = 0.0015
CAMERA_LOCAL_ANGULAR_RATE_SIGMA_RAD_S = 0.0015

FORMAL_SCENARIOS = (
    "nominal",
    "dense_crossing",
    "formation_split",
    "evasive_multilevel",
    "delayed_noisy",
    "communication_degraded",
    "center_failure",
    "secondary_failure",
    "high_threat_m_to_n",
)
FORMAL_SCALES = (5, 20, 50, 100, 200)
FORMAL_SCENARIO_CELLS = tuple(
    (scenario, scale) for scenario in FORMAL_SCENARIOS for scale in FORMAL_SCALES
)

_WORLD_TO_CAMERA_BASE = np.array(
    [[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]],
    dtype=float,
)
_IMAGE_SIZE = (1280, 720)
_INTRINSICS = np.array(
    [[800.0, 0.0, 640.0], [0.0, 800.0, 360.0], [0.0, 0.0, 1.0]],
    dtype=float,
)


class TrackletSupplementalCurriculumError(ValueError):
    """Stable fail-closed producer or loader error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class SupplementalGenerationConfig:
    """Frozen producer profile.  Geometry gates are intentionally not exposed."""

    profile_version: str = SUPPLEMENTAL_PROFILE_VERSION
    rng_namespace: str = SUPPLEMENTAL_RNG_NAMESPACE
    camera_count: int = 4
    physical_target_count: int = 4
    image_width: int = _IMAGE_SIZE[0]
    image_height: int = _IMAGE_SIZE[1]
    frames_per_cell_seed: int = SUPPLEMENTAL_FRAME_COUNT_PER_CELL_SEED
    scenario_cells: tuple[tuple[str, int], ...] = FORMAL_SCENARIO_CELLS

    def __post_init__(self) -> None:
        if self.profile_version not in {
            SUPPLEMENTAL_PROFILE_VERSION,
            SUPPLEMENTAL_SMOKE_PROFILE_VERSION,
        }:
            _fail("profile_version_mismatch", "supplemental profile version changed")
        if self.rng_namespace != SUPPLEMENTAL_RNG_NAMESPACE:
            _fail("rng_namespace_mismatch", "supplemental RNG namespace changed")
        if self.camera_count != 4 or self.physical_target_count != 4:
            _fail("local_geometry_profile_changed", "full curriculum requires 4 cameras and 4 targets")
        if (self.image_width, self.image_height) != _IMAGE_SIZE:
            _fail("image_geometry_profile_changed", "full curriculum image size changed")
        if self.frames_per_cell_seed != SUPPLEMENTAL_FRAME_COUNT_PER_CELL_SEED:
            _fail("frame_profile_changed", "full curriculum frame count changed")
        cells = tuple(self.scenario_cells)
        if self.profile_version == SUPPLEMENTAL_PROFILE_VERSION:
            if cells != FORMAL_SCENARIO_CELLS:
                _fail("scenario_cell_profile_changed", "full curriculum scenario cells changed")
        elif not cells or any(cell not in FORMAL_SCENARIO_CELLS for cell in cells):
            _fail("smoke_scenario_cell_invalid", "smoke cells must be a non-empty formal subset")

    def to_payload(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "scenario_cells": [
                {"scenario": scenario, "scale": scale}
                for scenario, scale in self.scenario_cells
            ],
        }


@dataclass(frozen=True)
class _OfflineObservation:
    observation_id: str
    truth_entity_id: str
    measurement_timestamp: float


@dataclass(frozen=True)
class SupplementalCurriculumResult:
    output_dir: Path
    dataset: LoadedTrackletDataset
    manifest: Mapping[str, Any]
    manifest_sha256: str
    summary: Mapping[str, Any]


def generate_tracklet_supplemental_curriculum(
    output_dir: str | Path,
    *,
    formal_dataset_dir: str | Path,
    training_seed_registry_path: str | Path,
    shared_seed_registry_path: str | Path,
    created_at_utc: str,
    source_git_commit: str,
    source_repository_dirty: bool,
    config: SupplementalGenerationConfig | None = None,
) -> SupplementalCurriculumResult:
    """Generate and atomically publish the full 100-seed supplemental corpus."""

    cfg = config or SupplementalGenerationConfig()
    destination = Path(output_dir).resolve()
    formal_root = Path(formal_dataset_dir).resolve()
    training_registry = Path(training_seed_registry_path).resolve()
    shared_registry = Path(shared_seed_registry_path).resolve()
    _validate_destination(destination, (formal_root, training_registry.parent, shared_registry.parent))
    if destination.exists():
        _fail("destination_exists", f"destination already exists: {destination}")
    commit = _git_commit(source_git_commit)
    if type(source_repository_dirty) is not bool:
        _fail("dirty_flag_invalid", "source_repository_dirty must be boolean")
    timestamp = str(created_at_utc).strip()
    if not timestamp:
        _fail("created_at_missing", "created_at_utc must be non-empty")

    formal = load_tracklet_dataset(formal_root)
    assignment, registry = _load_registry_binding(training_registry, shared_registry)
    seeds = tuple(registry["training"]["training_seeds"])
    if len(seeds) != 100 or set(seeds) != set(range(100)):
        _fail("training_seed_catalog_mismatch", "full curriculum requires seeds 0-99")
    if set(seeds) & set(registry["training"]["reserved_seeds"]):
        _fail("reserved_seed_leak", "reserved evaluation seeds entered curriculum generation")

    temporary = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        dataset_root = temporary / "dataset"
        evaluator_root = temporary / "evaluator"
        evaluator_root.mkdir()
        gate_config = SparseTrackletGraphConfig()
        gate_payload = asdict(gate_config)
        gate_sha256 = _sha256_json(gate_payload)
        implementation_hashes = _implementation_hashes()
        generation_config = {
            "schema_version": SUPPLEMENTAL_CURRICULUM_SCHEMA_VERSION,
            "profile": cfg.to_payload(),
            "created_at_utc": timestamp,
            "source_git_commit": commit,
            "source_repository_dirty": source_repository_dirty,
            "formal_manifest_sha256": formal.manifest_sha256,
            "training_seed_registry_sha256": registry["training_file_sha256"],
            "shared_seed_registry_sha256": registry["shared_file_sha256"],
            "candidate_gate_config": gate_payload,
            "candidate_gate_config_sha256": gate_sha256,
            "camera_local_measurement_model": {
                "version": CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION,
                "bbox_log_side_sigma": CAMERA_LOCAL_BBOX_LOG_SIDE_SIGMA,
                "bbox_scale_rate_sigma_s": CAMERA_LOCAL_SCALE_RATE_SIGMA_S,
                "angular_rate_sigma_rad_s": (
                    CAMERA_LOCAL_ANGULAR_RATE_SIGMA_RAD_S
                ),
                "truth_or_edge_label_accessed": False,
            },
            "online_truth_policy": "forbidden",
            "evaluator_truth_policy": "physically_separate_exact_observation_lineage",
            "implementation_sha256": implementation_hashes,
        }
        lineage_records: list[dict[str, Any]] = []
        factor_counts: Counter[str] = Counter()
        gate_counts: Counter[str] = Counter()
        class_counts: Counter[str] = Counter()
        frame_count = 0

        for seed in seeds:
            for scenario, scale in cfg.scenario_cells:
                graph, offline, lineage, factors = _build_curriculum_frame(
                    seed,
                    scenario=scenario,
                    scale=scale,
                    frame_index=0,
                    gate_config=gate_config,
                )
                joined = join_offline_observation_labels(graph, offline)
                if not joined.labels_complete:
                    _fail("producer_label_join_incomplete", "producer failed exact observation join")
                positive, negative, unlabeled = _edge_balance(graph, joined.tracklet_labels)
                if positive <= 0 or negative <= 0 or unlabeled != 0:
                    _fail(
                        "producer_dual_class_requirement_failed",
                        f"{scenario}-{scale}: positive={positive};negative={negative};unlabeled={unlabeled}",
                    )
                scenario_version = f"{scenario}-{scale}v{scale}-v1"
                episode_id = (
                    f"d5-supplemental-{scenario}-{scale}v{scale}-s{seed:03d}-frame-000000"
                )
                descriptor = stage_tracklet_dataset_episode(
                    dataset_root,
                    graph,
                    joined.tracklet_labels,
                    scenario_version=scenario_version,
                    seed=seed,
                    episode_id=episode_id,
                    generation_config=generation_config,
                    labels_complete=True,
                    candidate_recall_available=True,
                    hard_negative_provenance={
                        "source": "supplemental_physical_projection_after_default_geometry_gates",
                        "truth_use": "offline_exact_observation_lineage_only",
                        "candidate_gate_config_sha256": gate_sha256,
                        "rng_namespace": SUPPLEMENTAL_RNG_NAMESPACE,
                        "scenario": scenario,
                        "scale": scale,
                        "frame_index": 0,
                    },
                )
                for record in lineage:
                    enriched = dict(record)
                    enriched["episode_uid"] = descriptor["episode_uid"]
                    enriched["scenario_version"] = scenario_version
                    enriched["seed"] = seed
                    lineage_records.append(enriched)
                frame_count += 1
                class_counts.update(
                    {
                        "positive_candidate_edges": positive,
                        "negative_candidate_edges": negative,
                        "unlabeled_candidate_edges": unlabeled,
                    }
                )
                gate_counts.update(graph.candidate_counts)
                factor_counts.update(factors)

        finalize_tracklet_dataset(dataset_root, split_seed=20260720)
        lineage_path = evaluator_root / "observation_lineage.json.gz"
        _write_lineage(
            lineage_path,
            records=lineage_records,
            formal_manifest_sha256=formal.manifest_sha256,
            gate_config_sha256=gate_sha256,
        )
        supplemental = load_tracklet_dataset(dataset_root)
        duplicate_audit = _duplicate_audit(formal, supplemental)
        if duplicate_audit["violation_count"]:
            _fail("formal_supplemental_duplicate", json.dumps(duplicate_audit, sort_keys=True))
        split_seed_counts = Counter(assignment[episode.graph.seed] for episode in supplemental.episodes)
        manifest = _build_supplemental_manifest(
            root=temporary,
            dataset=supplemental,
            formal=formal,
            registries=registry,
            created_at_utc=timestamp,
            source_git_commit=commit,
            source_repository_dirty=source_repository_dirty,
            config=cfg,
            generation_config=generation_config,
            implementation_hashes=implementation_hashes,
            lineage_path=lineage_path,
            lineage_record_count=len(lineage_records),
            frame_count=frame_count,
            class_counts=class_counts,
            factor_counts=factor_counts,
            gate_counts=gate_counts,
            split_seed_counts=split_seed_counts,
            duplicate_audit=duplicate_audit,
        )
        _write_json_atomic(temporary / "supplemental_manifest.json", manifest)
        summary = _curriculum_summary(manifest, supplemental)
        _write_json_atomic(temporary / "curriculum_summary.json", summary)
        _write_text_atomic(
            temporary / "curriculum_report.md",
            render_supplemental_curriculum_markdown(summary),
        )
        os.replace(temporary, destination)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise

    return load_tracklet_supplemental_curriculum(
        destination,
        require_full_profile=(cfg.profile_version == SUPPLEMENTAL_PROFILE_VERSION),
    )


def load_tracklet_supplemental_curriculum(
    output_dir: str | Path,
    *,
    require_full_profile: bool = True,
) -> SupplementalCurriculumResult:
    """Strictly validate every source artifact and evaluator lineage record."""

    root = Path(output_dir).resolve()
    manifest_path = root / "supplemental_manifest.json"
    manifest = _read_json(manifest_path)
    _validate_supplemental_manifest_shape(manifest, require_full_profile=require_full_profile)
    inventory = manifest["artifact_inventory"]
    expected_paths = set()
    for item in inventory:
        relative = _safe_relative_path(item["path"])
        path = root / relative
        expected_paths.add(relative.as_posix())
        if not path.is_file():
            _fail("supplemental_artifact_missing", relative.as_posix())
        if path.stat().st_size != int(item["size_bytes"]):
            _fail("supplemental_artifact_size_mismatch", relative.as_posix())
        if sha256_file(path) != item["sha256"]:
            _fail("supplemental_artifact_hash_mismatch", relative.as_posix())
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.name not in {"supplemental_manifest.json", "curriculum_summary.json", "curriculum_report.md"}
    }
    if actual_paths != expected_paths:
        _fail(
            "supplemental_artifact_inventory_mismatch",
            f"missing={sorted(expected_paths-actual_paths)};extra={sorted(actual_paths-expected_paths)}",
        )
    unhashed = dict(manifest)
    content_hash = unhashed.pop("content_sha256")
    if _sha256_json(unhashed) != content_hash:
        _fail("supplemental_manifest_content_hash_mismatch", "manifest content changed")
    gate_payload = asdict(SparseTrackletGraphConfig())
    if manifest["candidate_gate"]["config"] != gate_payload:
        _fail("candidate_gate_lowered_or_changed", "candidate gate config differs from default")
    if manifest["candidate_gate"]["config_sha256"] != _sha256_json(gate_payload):
        _fail("candidate_gate_hash_mismatch", "candidate gate hash changed")

    try:
        dataset = load_tracklet_dataset(root / "dataset")
    except TrackletDatasetValidationError as error:
        _fail(
            f"supplemental_dataset_{error.code}",
            f"strict supplemental dataset validation failed: {error}",
        )
    if dataset.manifest_sha256 != manifest["dataset"]["manifest_sha256"]:
        _fail("supplemental_dataset_manifest_mismatch", "dataset manifest changed")
    lineage = _load_lineage(root / manifest["evaluator_lineage"]["file"])
    _validate_lineage_against_dataset(dataset, lineage)
    if any(not episode.evaluator_labels.labels_complete for episode in dataset.episodes):
        _fail("supplemental_labels_incomplete", "supplemental labels must be complete")
    if any(not episode.evaluator_labels.candidate_recall_available for episode in dataset.episodes):
        _fail("supplemental_candidate_recall_unavailable", "supplemental recall must be evaluable")
    if sum(episode.class_balance["unlabeled_candidate_edges"] for episode in dataset.episodes):
        _fail("supplemental_unlabeled_edge", "supplemental corpus contains unlabeled edges")
    summary_path = root / "curriculum_summary.json"
    summary = _read_json(summary_path)
    expected_summary = _curriculum_summary(manifest, dataset)
    if summary != expected_summary:
        _fail("supplemental_summary_mismatch", "curriculum summary changed")
    return SupplementalCurriculumResult(
        output_dir=root,
        dataset=dataset,
        manifest=MappingProxyType(manifest),
        manifest_sha256=sha256_file(manifest_path),
        summary=MappingProxyType(summary),
    )


def render_supplemental_curriculum_markdown(summary: Mapping[str, Any]) -> str:
    """Render the generated data evidence in Chinese."""

    classes = summary["class_balance"]
    lines = [
        "# D5 跨视角困难样本补充课程",
        "",
        "## 结论",
        "",
        f"独立补充课程生成 `{summary['episode_count']}` 个图帧、`{summary['node_count']}` 个匿名"
        f"局部航迹节点和 `{summary['candidate_edge_count']}` 条默认几何门候选边。标签完整率为 "
        f"`{summary['label_availability_ratio']:.2%}`。",
        "",
        f"正边 `{classes['positive_candidate_edges']}` 条，困难负边 "
        f"`{classes['negative_candidate_edges']}` 条，未标注边 "
        f"`{classes['unlabeled_candidate_edges']}` 条。producer 未修改正式语料，未训练模型，"
        "未开放 G1 或在线辅助权限。",
        "",
        "## 数据来源",
        "",
        f"- supplemental manifest SHA-256：`{summary['manifest_sha256']}`",
        f"- dataset manifest SHA-256：`{summary['dataset_manifest_sha256']}`",
        f"- evaluator lineage SHA-256：`{summary['evaluator_lineage_sha256']}`",
        f"- 正式源 manifest SHA-256：`{summary['formal_manifest_sha256']}`",
        f"- 源 Git 提交：`{summary['source_git_commit']}`",
        f"- 源工作区 dirty：`{str(summary['source_repository_dirty']).lower()}`",
        "",
        "## 覆盖",
        "",
        f"- numeric seed：`{summary['unique_seed_count']}` 个，canonical 分桶 "
        f"`{summary['canonical_seed_counts']}`。",
        f"- 场景规模 cell：`{summary['scenario_scale_cell_count']}` 个。",
        f"- 遮挡进入/退出、时间偏差、外参扰动、漏检和虚警均有生成记录。",
        f"- 与正式源重复图、重复边和重复 episode：`{summary['duplicate_violation_count']}`。",
        "",
        "## 安全边界",
        "",
        "在线图只含匿名局部航迹、时间戳、像素量测、协方差和几何特征。真值位于独立 "
        "evaluator lineage 与 label 文件。候选边仍经过默认时间、视场、极线、射线、重投影"
        "和协方差门，D5 不创建或改写 `global_track_id`。",
        "",
    ]
    return "\n".join(lines)


def _build_curriculum_frame(
    seed: int,
    *,
    scenario: str,
    scale: int,
    frame_index: int,
    gate_config: SparseTrackletGraphConfig,
) -> tuple[SparseTrackletGraph, tuple[_OfflineObservation, ...], list[dict[str, Any]], Counter[str]]:
    if (scenario, int(scale)) not in FORMAL_SCENARIO_CELLS:
        _fail("unknown_scenario_cell", f"{scenario}:{scale}")
    if gate_config != SparseTrackletGraphConfig():
        _fail("candidate_gate_override_forbidden", "supplemental producer requires default gates")
    rng_seed = _derived_seed(seed, scenario, scale, frame_index)
    rng = np.random.default_rng(rng_seed)
    scenario_index = FORMAL_SCENARIOS.index(scenario)
    phase = (seed + scenario_index + FORMAL_SCALES.index(scale)) % 3
    phase_name = ("occlusion_enter", "occluded", "occlusion_exit")[phase]
    base_time = 20.0 + 0.05 * scenario_index + 0.001 * (scale + seed)
    target_range = 420.0 + 0.35 * scale + rng.uniform(-15.0, 15.0)
    baseline_step = 7.0 + 0.025 * scale + rng.uniform(0.0, 4.0)
    camera_east = baseline_step * np.array([-1.5, -0.5, 0.5, 1.5])
    target_offsets = np.array([-3.0, -1.0, 1.0, 3.0])
    if scenario == "dense_crossing":
        target_offsets *= 0.55
    elif scenario == "formation_split":
        target_offsets *= 0.8
    vertical_offsets = (
        np.array([-0.45, -0.15, 0.15, 0.45])
        if scenario == "evasive_multilevel"
        else np.zeros(4)
    )
    lateral_velocity = np.array([1.8, 0.8, -0.8, -1.8])
    if scenario in {"nominal", "center_failure", "secondary_failure"}:
        lateral_velocity *= 0.35
    motion_time = 0.18 * ((seed + scenario_index) % 9)
    target_points = [
        np.array(
            [
                target_range + 0.4 * math.sin(0.3 * seed + target_index),
                target_offsets[target_index] + lateral_velocity[target_index] * motion_time,
                -100.0 + vertical_offsets[target_index],
            ],
            dtype=float,
        )
        for target_index in range(4)
    ]

    tracklets: list[CameraLocalTracklet] = []
    cameras: list[TrackletCameraGeometry] = []
    offline: list[_OfflineObservation] = []
    lineage: list[dict[str, Any]] = []
    factors: Counter[str] = Counter({phase_name: 1, "external_perturbation": 1})
    time_spread = 0.025 + (0.025 if scenario == "delayed_noisy" else 0.0)
    miss_camera = (seed + scenario_index) % 4
    miss_target = (seed + scale + scenario_index) % 4
    false_alarm_enabled = scenario in {"delayed_noisy", "communication_degraded"} or seed % 7 == 0

    for camera_index, east in enumerate(camera_east):
        measurement_timestamp = base_time + (camera_index - 1.5) * time_spread
        arrival_delay = 0.035 + 0.015 * camera_index
        if scenario in {"delayed_noisy", "communication_degraded"}:
            arrival_delay += 0.04 + 0.01 * ((seed + camera_index) % 4)
            factors["time_bias"] += 1
        true_center = np.array([0.0, east, -100.0], dtype=float)
        true_camera = CameraModel(
            K=_INTRINSICS,
            R=_WORLD_TO_CAMERA_BASE,
            t=-_WORLD_TO_CAMERA_BASE @ true_center,
            image_size=_IMAGE_SIZE,
            measurement_cov=np.diag([1.5, 1.5]),
        )
        position_sigma = 0.05 + (0.12 if scenario == "delayed_noisy" else 0.04)
        attitude_sigma = 2.0e-4 + (6.0e-4 if scenario == "delayed_noisy" else 2.0e-4)
        estimated_center = true_center + rng.normal(0.0, position_sigma, size=3)
        delta_rotation = _small_rotation(rng.normal(0.0, attitude_sigma, size=3))
        estimated_rotation = delta_rotation @ _WORLD_TO_CAMERA_BASE
        estimated_camera = CameraModel(
            K=_INTRINSICS,
            R=estimated_rotation,
            t=-estimated_rotation @ estimated_center,
            image_size=_IMAGE_SIZE,
            measurement_cov=np.diag([1.5, 1.5]),
        )
        resource_id = f"CUR-CAM-{camera_index:02d}"
        camera_id = "OPTICAL"
        cameras.append(
            TrackletCameraGeometry(
                resource_id=resource_id,
                camera_id=camera_id,
                camera=estimated_camera,
                measurement_timestamp=measurement_timestamp,
                position_covariance_ned=np.eye(3) * position_sigma**2,
                attitude_covariance_rad2=np.eye(3) * attitude_sigma**2,
            )
        )
        permutation = np.random.default_rng(
            _derived_seed(seed, scenario, scale, 100 + camera_index)
        ).permutation(4)
        visible_targets = list(range(4))
        if phase == 0 and camera_index == 3:
            visible_targets.remove(3)
            factors["occlusion_target_omitted"] += 1
        elif phase == 1 and camera_index in {2, 3}:
            hidden = 2 if camera_index == 2 else 3
            visible_targets.remove(hidden)
            factors["occlusion_target_omitted"] += 1
        if camera_index == miss_camera and miss_target in visible_targets:
            visible_targets.remove(miss_target)
            factors["missed_detection"] += 1

        for target_index in visible_targets:
            point = target_points[target_index].copy()
            point[1] += lateral_velocity[target_index] * (
                measurement_timestamp - base_time
            )
            center = _project(point, true_camera)
            noise_sigma = 0.35 + (0.35 if scenario == "delayed_noisy" else 0.0)
            center += rng.normal(0.0, noise_sigma, size=2)
            depth = float((_WORLD_TO_CAMERA_BASE @ point + true_camera.t)[2])
            side = float(np.clip(800.0 * 2.0 / max(depth, 1.0), 3.0, 16.0))
            local_sequence = int(permutation[target_index]) + 1
            if phase == 2 and camera_index == 3 and target_index == 3:
                local_sequence += 20
                factors["reentry_tracklet_fragment"] += 1
            local_track_id = f"trk-{local_sequence:06d}"
            observation_id = _anonymous_observation_id(
                seed, scenario, scale, camera_index, target_index, "target"
            )
            (
                measured_side,
                measured_angular_velocity,
                measured_scale_rate,
            ) = _camera_local_kinematic_measurement(
                observation_id=observation_id,
                bbox_side=side,
                angular_velocity_rad_s=np.array(
                    [lateral_velocity[target_index] / max(depth, 1.0), 0.0],
                    dtype=float,
                ),
                bbox_scale_rate_s=0.002 * math.sin(seed + target_index),
            )
            covariance = np.eye(2) * (noise_sigma**2 + 1.0)
            tracklet = CameraLocalTracklet(
                resource_id=resource_id,
                camera_id=camera_id,
                local_track_id=local_track_id,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=measurement_timestamp + arrival_delay,
                center_px=center,
                covariance_px=covariance,
                bbox_xyxy=(
                    center[0] - measured_side,
                    center[1] - 0.75 * measured_side,
                    center[0] + measured_side,
                    center[1] + 0.75 * measured_side,
                ),
                angular_velocity_rad_s=measured_angular_velocity,
                bbox_scale_rate_s=measured_scale_rate,
                confidence=0.82 + 0.03 * ((seed + target_index) % 4),
                tracklet_start_timestamp=measurement_timestamp - 0.2 - 0.05 * target_index,
                source_observation_id=observation_id,
                metadata={
                    "source": "d5_supplemental_physical_projection",
                    "tracker_backend": "anonymous_curriculum_tracklet",
                    "measurement_model": CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION,
                },
            )
            truth_entity_id = _truth_entity_id(seed, target_index)
            tracklets.append(tracklet)
            offline.append(_OfflineObservation(observation_id, truth_entity_id, measurement_timestamp))
            lineage.append(
                _lineage_record(
                    tracklet,
                    observation_id=observation_id,
                    truth_entity_id=truth_entity_id,
                    observation_kind="physical_target",
                    entity_slot=target_index,
                    world_point_ned=point,
                )
            )
            factors["camera_local_measurement_noise"] += 1

        if false_alarm_enabled and camera_index in {0, 2}:
            clutter_slot = 100 + camera_index
            point = np.array(
                [target_range + 2.0, 0.3 * (camera_index - 1), -100.0], dtype=float
            )
            center = _project(point, true_camera) + rng.normal(0.0, 0.5, size=2)
            observation_id = _anonymous_observation_id(
                seed, scenario, scale, camera_index, clutter_slot, "clutter"
            )
            local_track_id = f"trk-{100 + camera_index:06d}"
            (
                measured_side,
                measured_angular_velocity,
                measured_scale_rate,
            ) = _camera_local_kinematic_measurement(
                observation_id=observation_id,
                bbox_side=3.0,
                angular_velocity_rad_s=np.zeros(2, dtype=float),
                bbox_scale_rate_s=0.0,
            )
            tracklet = CameraLocalTracklet(
                resource_id=resource_id,
                camera_id=camera_id,
                local_track_id=local_track_id,
                measurement_timestamp=measurement_timestamp,
                arrival_timestamp=measurement_timestamp + arrival_delay,
                center_px=center,
                covariance_px=np.eye(2) * 1.5,
                bbox_xyxy=(
                    center[0] - measured_side,
                    center[1] - (2.0 / 3.0) * measured_side,
                    center[0] + measured_side,
                    center[1] + (2.0 / 3.0) * measured_side,
                ),
                angular_velocity_rad_s=measured_angular_velocity,
                bbox_scale_rate_s=measured_scale_rate,
                confidence=0.45,
                tracklet_start_timestamp=measurement_timestamp,
                source_observation_id=observation_id,
                metadata={
                    "source": "d5_supplemental_false_alarm",
                    "tracker_backend": "anonymous_curriculum_tracklet",
                    "measurement_model": CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION,
                },
            )
            truth_entity_id = _clutter_truth_id(seed, scenario, scale, camera_index)
            tracklets.append(tracklet)
            offline.append(_OfflineObservation(observation_id, truth_entity_id, measurement_timestamp))
            lineage.append(
                _lineage_record(
                    tracklet,
                    observation_id=observation_id,
                    truth_entity_id=truth_entity_id,
                    observation_kind="camera_local_false_alarm",
                    entity_slot=clutter_slot,
                    world_point_ned=point,
                )
            )
            factors["false_alarm"] += 1
            factors["camera_local_measurement_noise"] += 1

    graph = build_sparse_tracklet_graph(tracklets, cameras, center_tracks=(), config=gate_config)
    return graph, tuple(offline), lineage, factors


def _camera_local_kinematic_measurement(
    *,
    observation_id: str,
    bbox_side: float,
    angular_velocity_rad_s: np.ndarray,
    bbox_scale_rate_s: float,
) -> tuple[float, np.ndarray, float]:
    """Apply one deterministic, identity-free camera-local measurement error."""

    material = (
        f"{CAMERA_LOCAL_MEASUREMENT_MODEL_VERSION}|{str(observation_id)}"
    ).encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    side = float(bbox_side) * math.exp(
        float(rng.normal(0.0, CAMERA_LOCAL_BBOX_LOG_SIDE_SIGMA))
    )
    angular_velocity = np.asarray(angular_velocity_rad_s, dtype=float).reshape(2)
    angular_velocity = angular_velocity + rng.normal(
        0.0,
        CAMERA_LOCAL_ANGULAR_RATE_SIGMA_RAD_S,
        size=2,
    )
    scale_rate = float(bbox_scale_rate_s) + float(
        rng.normal(0.0, CAMERA_LOCAL_SCALE_RATE_SIGMA_S)
    )
    return max(side, 1.0e-6), angular_velocity, scale_rate


def _lineage_record(
    tracklet: CameraLocalTracklet,
    *,
    observation_id: str,
    truth_entity_id: str,
    observation_kind: str,
    entity_slot: int,
    world_point_ned: np.ndarray,
) -> dict[str, Any]:
    return {
        "tracklet_key": tracklet.tracklet_key,
        "camera_key": tracklet.camera_key,
        "measurement_timestamp": tracklet.measurement_timestamp,
        "source_observation_id": observation_id,
        "truth_entity_id": truth_entity_id,
        "observation_kind": observation_kind,
        "entity_slot": int(entity_slot),
        "world_point_ned": [float(value) for value in world_point_ned],
        "evidence_kind": "offline_observation_truth_lineage",
    }


def _edge_balance(graph: SparseTrackletGraph, labels: Iterable[Any]) -> tuple[int, int, int]:
    by_key = {label.tracklet_key: label.truth_entity_id for label in labels}
    positive = negative = unlabeled = 0
    for edge in graph.edges:
        source = by_key.get(edge.source_tracklet_key)
        target = by_key.get(edge.target_tracklet_key)
        if source is None or target is None:
            unlabeled += 1
        elif source == target:
            positive += 1
        else:
            negative += 1
    return positive, negative, unlabeled


def _write_lineage(
    path: Path,
    *,
    records: Sequence[Mapping[str, Any]],
    formal_manifest_sha256: str,
    gate_config_sha256: str,
) -> None:
    payload = {
        "schema_version": SUPPLEMENTAL_LINEAGE_SCHEMA_VERSION,
        "formal_manifest_sha256": formal_manifest_sha256,
        "candidate_gate_config_sha256": gate_config_sha256,
        "record_count": len(records),
        "records": sorted(
            (dict(item) for item in records),
            key=lambda item: (
                item["episode_uid"],
                item["tracklet_key"],
                item["measurement_timestamp"],
            ),
        ),
    }
    raw = (
        json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as stream:
        stream.write(raw)
    path.write_bytes(buffer.getvalue())


def _load_lineage(path: Path) -> Mapping[str, Any]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        _fail("evaluator_lineage_invalid", str(exc))
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SUPPLEMENTAL_LINEAGE_SCHEMA_VERSION:
        _fail("evaluator_lineage_schema_mismatch", "lineage schema changed")
    records = payload.get("records")
    if not isinstance(records, list) or payload.get("record_count") != len(records):
        _fail("evaluator_lineage_count_mismatch", "lineage record count changed")
    return payload


def _validate_lineage_against_dataset(
    dataset: LoadedTrackletDataset,
    lineage: Mapping[str, Any],
) -> None:
    index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for item in lineage["records"]:
        if not isinstance(item, Mapping):
            _fail("lineage_record_invalid", "lineage record is not an object")
        required = {
            "episode_uid",
            "scenario_version",
            "seed",
            "tracklet_key",
            "camera_key",
            "measurement_timestamp",
            "source_observation_id",
            "truth_entity_id",
            "observation_kind",
            "entity_slot",
            "world_point_ned",
            "evidence_kind",
        }
        if set(item) != required:
            _fail("lineage_record_fields_mismatch", "lineage record fields changed")
        if item["evidence_kind"] != "offline_observation_truth_lineage":
            _fail("lineage_evidence_kind_invalid", "lineage is not direct evaluator evidence")
        if item["observation_kind"] not in {"physical_target", "camera_local_false_alarm"}:
            _fail("lineage_observation_kind_invalid", str(item["observation_kind"]))
        point = np.asarray(item["world_point_ned"], dtype=float)
        if point.shape != (3,) or not np.all(np.isfinite(point)):
            _fail("lineage_world_point_invalid", "lineage world point must be finite NED")
        seed = int(item["seed"])
        slot = int(item["entity_slot"])
        expected_truth = (
            _truth_entity_id(seed, slot)
            if item["observation_kind"] == "physical_target"
            else _clutter_truth_id_from_record(item)
        )
        if item["truth_entity_id"] != expected_truth:
            _fail("negative_edge_label_forgery", "lineage truth ID does not match producer identity rule")
        key = (
            str(item["episode_uid"]),
            str(item["tracklet_key"]),
            _time_key(float(item["measurement_timestamp"])),
        )
        if key in index:
            _fail("lineage_duplicate", str(key))
        index[key] = item

    expected_count = 0
    for episode in dataset.episodes:
        labels = episode.evaluator_labels.by_tracklet_key
        for node_index, tracklet_key in enumerate(episode.graph.tracklet_keys):
            timestamp = float(episode.graph.measurement_timestamps[node_index])
            key = (episode.graph.episode_uid, tracklet_key, _time_key(timestamp))
            item = index.get(key)
            if item is None:
                _fail("lineage_missing_for_tracklet", str(key))
            label = labels.get(tracklet_key)
            if label is None:
                _fail("lineage_label_missing", str(key))
            if label.truth_entity_id != item["truth_entity_id"]:
                _fail("negative_edge_label_forgery", str(key))
            if item["camera_key"] != episode.graph.camera_keys[node_index]:
                _fail("lineage_camera_mismatch", str(key))
            expected_count += 1
    if len(index) != expected_count:
        _fail("lineage_orphan_record", f"lineage={len(index)};nodes={expected_count}")


def _build_supplemental_manifest(
    *,
    root: Path,
    dataset: LoadedTrackletDataset,
    formal: LoadedTrackletDataset,
    registries: Mapping[str, Any],
    created_at_utc: str,
    source_git_commit: str,
    source_repository_dirty: bool,
    config: SupplementalGenerationConfig,
    generation_config: Mapping[str, Any],
    implementation_hashes: Mapping[str, str],
    lineage_path: Path,
    lineage_record_count: int,
    frame_count: int,
    class_counts: Mapping[str, int],
    factor_counts: Mapping[str, int],
    gate_counts: Mapping[str, int],
    split_seed_counts: Mapping[str, int],
    duplicate_audit: Mapping[str, Any],
) -> dict[str, Any]:
    artifacts = _artifact_inventory(root)
    scenario_cells = {
        episode.graph.scenario_version for episode in dataset.episodes
    }
    seeds = {episode.graph.seed for episode in dataset.episodes}
    manifest: dict[str, Any] = {
        "schema_version": SUPPLEMENTAL_MANIFEST_SCHEMA_VERSION,
        "created_at_utc": created_at_utc,
        "profile": config.to_payload(),
        "source": {
            "git_commit": source_git_commit,
            "repository_dirty": source_repository_dirty,
            "implementation_sha256": dict(implementation_hashes),
            "generation_config_sha256": _sha256_json(generation_config),
        },
        "formal_source": {
            "manifest_sha256": formal.manifest_sha256,
            "episode_count": len(formal.episodes),
            "modified": False,
        },
        "seed_registries": {
            "training_file_sha256": registries["training_file_sha256"],
            "shared_file_sha256": registries["shared_file_sha256"],
            "shared_assignment_sha256": registries["shared"]["assignment_sha256"],
            "reserved_evaluation_seeds": list(registries["training"]["reserved_seeds"]),
            "reserved_seed_overlap": [],
            "canonical_seed_counts": {
                split: len(registries["shared"]["split_seed_values"][split])
                for split in ("train", "validation", "test")
            },
            "canonical_episode_counts": {
                split: int(split_seed_counts[split])
                for split in ("train", "validation", "test")
            },
        },
        "candidate_gate": {
            "policy": "unchanged_sparse_tracklet_default",
            "config": asdict(SparseTrackletGraphConfig()),
            "config_sha256": generation_config["candidate_gate_config_sha256"],
            "center_track_projection_gate": "not_applicable_distributed_cross_view_curriculum",
            "time_epipolar_ray_reprojection_covariance_gates_required": True,
            "aggregate_counts": {key: int(value) for key, value in sorted(gate_counts.items())},
        },
        "dataset": {
            "directory": "dataset",
            "manifest_sha256": dataset.manifest_sha256,
            "schema_version": dataset.manifest["schema_version"],
            "episode_count": frame_count,
            "node_count": sum(episode.graph.node_count for episode in dataset.episodes),
            "candidate_edge_count": sum(episode.graph.edge_count for episode in dataset.episodes),
            "unique_seed_count": len(seeds),
            "scenario_scale_cell_count": len(scenario_cells),
            "class_balance": {key: int(value) for key, value in sorted(class_counts.items())},
            "labels_complete_episode_count": sum(
                episode.evaluator_labels.labels_complete for episode in dataset.episodes
            ),
            "candidate_recall_available_episode_count": sum(
                episode.evaluator_labels.candidate_recall_available for episode in dataset.episodes
            ),
        },
        "factor_coverage": {key: int(value) for key, value in sorted(factor_counts.items())},
        "evaluator_lineage": {
            "file": lineage_path.relative_to(root).as_posix(),
            "sha256": sha256_file(lineage_path),
            "record_count": lineage_record_count,
            "online_graph_truth_identifier_count": 0,
        },
        "duplicate_audit": dict(duplicate_audit),
        "artifact_inventory": artifacts,
        "artifact_inventory_sha256": _sha256_json({"artifacts": artifacts}),
        "admission": {
            "producer_complete": True,
            "full_sample_audit_required": True,
            "model_training_performed": False,
            "pt_generated": False,
            "g1_assist_allowed": False,
            "global_track_id_created_or_rebound": False,
        },
    }
    manifest["content_sha256"] = _sha256_json(manifest)
    return manifest


def _curriculum_summary(
    manifest: Mapping[str, Any],
    dataset: LoadedTrackletDataset,
) -> dict[str, Any]:
    data = manifest["dataset"]
    summary = {
        "schema_version": "d5.tracklet-supplemental-summary.v1",
        "manifest_sha256": sha256_file(dataset.root.parent / "supplemental_manifest.json"),
        "dataset_manifest_sha256": data["manifest_sha256"],
        "evaluator_lineage_sha256": manifest["evaluator_lineage"]["sha256"],
        "formal_manifest_sha256": manifest["formal_source"]["manifest_sha256"],
        "source_git_commit": manifest["source"]["git_commit"],
        "source_repository_dirty": manifest["source"]["repository_dirty"],
        "episode_count": data["episode_count"],
        "node_count": data["node_count"],
        "candidate_edge_count": data["candidate_edge_count"],
        "class_balance": data["class_balance"],
        "label_availability_ratio": (
            data["labels_complete_episode_count"] / max(1, data["episode_count"])
        ),
        "unique_seed_count": data["unique_seed_count"],
        "canonical_seed_counts": manifest["seed_registries"]["canonical_seed_counts"],
        "scenario_scale_cell_count": data["scenario_scale_cell_count"],
        "factor_coverage": manifest["factor_coverage"],
        "duplicate_violation_count": manifest["duplicate_audit"]["violation_count"],
        "admission": manifest["admission"],
    }
    summary["content_sha256"] = _sha256_json(summary)
    return summary


def _duplicate_audit(
    formal: LoadedTrackletDataset,
    supplemental: LoadedTrackletDataset,
) -> dict[str, Any]:
    formal_uids = {episode.graph.episode_uid for episode in formal.episodes}
    supplemental_uids = {episode.graph.episode_uid for episode in supplemental.episodes}
    formal_graph_hashes = {episode.graph_sha256 for episode in formal.episodes}
    supplemental_graph_hashes = {episode.graph_sha256 for episode in supplemental.episodes}
    formal_graph_fingerprints = {_graph_fingerprint(episode.graph) for episode in formal.episodes}
    supplemental_graph_fingerprint_rows = [
        _graph_fingerprint(episode.graph) for episode in supplemental.episodes
    ]
    supplemental_graph_fingerprints = set(supplemental_graph_fingerprint_rows)
    formal_edge_fingerprints = {
        fingerprint
        for episode in formal.episodes
        for fingerprint in _edge_fingerprints(episode.graph)
    }
    supplemental_edge_fingerprint_rows = [
        fingerprint
        for episode in supplemental.episodes
        for fingerprint in _edge_fingerprints(episode.graph)
    ]
    supplemental_edge_fingerprints = set(supplemental_edge_fingerprint_rows)
    uid_overlap = sorted(formal_uids & supplemental_uids)
    graph_hash_overlap = sorted(formal_graph_hashes & supplemental_graph_hashes)
    graph_content_overlap = sorted(formal_graph_fingerprints & supplemental_graph_fingerprints)
    edge_content_overlap = sorted(formal_edge_fingerprints & supplemental_edge_fingerprints)
    supplemental_graph_duplicate_count = len(supplemental_graph_fingerprint_rows) - len(
        supplemental_graph_fingerprints
    )
    supplemental_edge_duplicate_count = len(supplemental_edge_fingerprint_rows) - len(
        supplemental_edge_fingerprints
    )
    violation_count = sum(
        len(values)
        for values in (uid_overlap, graph_hash_overlap, graph_content_overlap, edge_content_overlap)
    ) + supplemental_graph_duplicate_count + supplemental_edge_duplicate_count
    return {
        "formal_episode_uid_overlap": uid_overlap,
        "formal_graph_sha256_overlap": graph_hash_overlap,
        "formal_graph_content_fingerprint_overlap": graph_content_overlap,
        "formal_edge_content_fingerprint_overlap": edge_content_overlap,
        "supplemental_episode_uid_unique": len(supplemental_uids) == len(supplemental.episodes),
        "supplemental_graph_content_unique_count": len(supplemental_graph_fingerprints),
        "supplemental_edge_content_unique_count": len(supplemental_edge_fingerprints),
        "supplemental_graph_duplicate_count": supplemental_graph_duplicate_count,
        "supplemental_edge_duplicate_count": supplemental_edge_duplicate_count,
        "violation_count": violation_count,
    }


def _graph_fingerprint(graph: Any) -> str:
    digest = hashlib.sha256()
    for array in (
        graph.node_features,
        graph.edge_index,
        graph.edge_features,
        graph.measurement_timestamps,
        graph.arrival_timestamps,
    ):
        value = np.ascontiguousarray(array)
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(str(value.shape).encode("ascii"))
        digest.update(value.tobytes())
    digest.update("\0".join(graph.camera_keys).encode("utf-8"))
    return digest.hexdigest()


def _edge_fingerprints(graph: Any) -> tuple[str, ...]:
    values: list[str] = []
    for edge_index in range(graph.edge_count):
        source = int(graph.edge_index[0, edge_index])
        target = int(graph.edge_index[1, edge_index])
        digest = hashlib.sha256()
        digest.update(np.ascontiguousarray(graph.node_features[source]).tobytes())
        digest.update(np.ascontiguousarray(graph.node_features[target]).tobytes())
        digest.update(np.ascontiguousarray(graph.edge_features[edge_index]).tobytes())
        digest.update(graph.camera_keys[source].encode("utf-8"))
        digest.update(b"\0")
        digest.update(graph.camera_keys[target].encode("utf-8"))
        values.append(digest.hexdigest())
    return tuple(values)


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _validate_supplemental_manifest_shape(
    manifest: Mapping[str, Any],
    *,
    require_full_profile: bool,
) -> None:
    required = {
        "schema_version",
        "created_at_utc",
        "profile",
        "source",
        "formal_source",
        "seed_registries",
        "candidate_gate",
        "dataset",
        "factor_coverage",
        "evaluator_lineage",
        "duplicate_audit",
        "artifact_inventory",
        "artifact_inventory_sha256",
        "admission",
        "content_sha256",
    }
    if set(manifest) != required:
        _fail("supplemental_manifest_fields_mismatch", "supplemental manifest fields changed")
    if manifest["schema_version"] != SUPPLEMENTAL_MANIFEST_SCHEMA_VERSION:
        _fail("supplemental_manifest_schema_mismatch", "supplemental manifest schema changed")
    if require_full_profile:
        profile = manifest["profile"]
        if profile != SupplementalGenerationConfig().to_payload():
            _fail("supplemental_profile_not_full", "source is not the full admission profile")
        data = manifest["dataset"]
        if data["episode_count"] != 100 * len(FORMAL_SCENARIO_CELLS):
            _fail("supplemental_episode_count_mismatch", "full profile episode count changed")
        if data["unique_seed_count"] != 100 or data["scenario_scale_cell_count"] != 45:
            _fail("supplemental_coverage_mismatch", "full profile seed/cell coverage changed")
        if manifest["seed_registries"]["canonical_seed_counts"] != {
            "train": 60,
            "validation": 20,
            "test": 20,
        }:
            _fail("supplemental_canonical_seed_count_mismatch", "canonical seed counts changed")
    if manifest["seed_registries"]["reserved_seed_overlap"]:
        _fail("reserved_seed_leak", "reserved evaluation seed appears in supplemental source")
    if manifest["duplicate_audit"]["violation_count"] != 0:
        _fail("formal_supplemental_duplicate", "duplicate source material detected")
    if manifest["admission"] != {
        "producer_complete": True,
        "full_sample_audit_required": True,
        "model_training_performed": False,
        "pt_generated": False,
        "g1_assist_allowed": False,
        "global_track_id_created_or_rebound": False,
    }:
        _fail("supplemental_admission_contract_changed", "admission contract changed")
    inventory = manifest["artifact_inventory"]
    if not isinstance(inventory, list) or not inventory:
        _fail("supplemental_artifact_inventory_invalid", "artifact inventory is empty")
    if _sha256_json({"artifacts": inventory}) != manifest["artifact_inventory_sha256"]:
        _fail("supplemental_artifact_inventory_hash_mismatch", "artifact inventory changed")


def _implementation_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    files = (
        root / "tracklet_supplemental_curriculum.py",
        root / "sparse_tracklet_graph.py",
        root / "tracklet_dataset.py",
    )
    return {path.name: sha256_file(path) for path in files}


def _derived_seed(seed: int, scenario: str, scale: int, frame_index: int) -> int:
    payload = f"{SUPPLEMENTAL_RNG_NAMESPACE}|{int(seed)}|{scenario}|{int(scale)}|{int(frame_index)}"
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def _anonymous_observation_id(
    seed: int,
    scenario: str,
    scale: int,
    camera_index: int,
    slot: int,
    kind: str,
) -> str:
    digest = hashlib.sha256(
        f"obs|{SUPPLEMENTAL_RNG_NAMESPACE}|{seed}|{scenario}|{scale}|{camera_index}|{slot}|{kind}".encode(
            "utf-8"
        )
    ).hexdigest()[:24]
    return f"obs-{digest}"


def _truth_entity_id(seed: int, slot: int) -> str:
    digest = hashlib.sha256(
        f"evaluator-physical-target|{SUPPLEMENTAL_RNG_NAMESPACE}|{int(seed)}|{int(slot)}".encode(
            "utf-8"
        )
    ).hexdigest()[:24]
    return f"eval-{digest}"


def _clutter_truth_id(seed: int, scenario: str, scale: int, camera_index: int) -> str:
    digest = hashlib.sha256(
        f"evaluator-camera-local-clutter|{SUPPLEMENTAL_RNG_NAMESPACE}|{seed}|{scenario}|{scale}|{camera_index}".encode(
            "utf-8"
        )
    ).hexdigest()[:24]
    return f"eval-clutter-{digest}"


def _clutter_truth_id_from_record(item: Mapping[str, Any]) -> str:
    scenario_version = str(item["scenario_version"])
    scenario_scale = scenario_version.removesuffix("-v1")
    scenario, scale_pair = scenario_scale.rsplit("-", 1)
    scale = int(scale_pair.split("v", 1)[0])
    camera_index = int(str(item["camera_key"]).split("/")[0].rsplit("-", 1)[1])
    return _clutter_truth_id(int(item["seed"]), scenario, scale, camera_index)


def _small_rotation(rotation_vector: np.ndarray) -> np.ndarray:
    x, y, z = (float(value) for value in rotation_vector)
    skew = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)
    angle = float(np.linalg.norm(rotation_vector))
    if angle <= 1.0e-12:
        return np.eye(3) + skew
    return np.eye(3) + (math.sin(angle) / angle) * skew + (
        (1.0 - math.cos(angle)) / (angle * angle)
    ) * (skew @ skew)


def _project(point_ned: np.ndarray, camera: CameraModel) -> np.ndarray:
    point_camera = camera.R @ point_ned + camera.t
    if point_camera[2] <= 0.0:
        _fail("projection_behind_camera", "curriculum point is behind camera")
    homogeneous = camera.K @ point_camera
    pixel = homogeneous[:2] / homogeneous[2]
    if not np.all(np.isfinite(pixel)):
        _fail("projection_nonfinite", "curriculum projection is non-finite")
    return pixel


def _validate_destination(destination: Path, protected: Sequence[Path]) -> None:
    for source in protected:
        resolved = source.resolve()
        if destination == resolved or resolved in destination.parents:
            _fail("output_inside_source", f"output must be outside source root: {resolved}")


def _safe_relative_path(value: Any) -> Path:
    path = Path(str(value))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        _fail("artifact_path_invalid", str(value))
    return path


def _git_commit(value: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        _fail("source_git_commit_invalid", "source Git commit must be 40 lowercase hex characters")
    return text


def _time_key(value: float) -> str:
    return format(float(value), ".17g")


def _sha256_json(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail("json_artifact_invalid", f"{path}: {exc}")
    if not isinstance(value, dict):
        _fail("json_artifact_not_object", str(path))
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    _write_bytes_atomic(
        path,
        (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )


def _write_text_atomic(path: Path, value: str) -> None:
    _write_bytes_atomic(path, value.encode("utf-8"))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _fail(code: str, message: str) -> None:
    raise TrackletSupplementalCurriculumError(code, message)


__all__ = [
    "FORMAL_SCALES",
    "FORMAL_SCENARIOS",
    "FORMAL_SCENARIO_CELLS",
    "SUPPLEMENTAL_CURRICULUM_SCHEMA_VERSION",
    "SUPPLEMENTAL_LINEAGE_SCHEMA_VERSION",
    "SUPPLEMENTAL_MANIFEST_SCHEMA_VERSION",
    "SUPPLEMENTAL_PROFILE_VERSION",
    "SUPPLEMENTAL_SMOKE_PROFILE_VERSION",
    "SupplementalCurriculumResult",
    "SupplementalGenerationConfig",
    "TrackletSupplementalCurriculumError",
    "generate_tracklet_supplemental_curriculum",
    "load_tracklet_supplemental_curriculum",
    "render_supplemental_curriculum_markdown",
]
