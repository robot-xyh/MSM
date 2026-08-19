"""Offline diagnostic with truth-perfect camera-local tracks.

This diagnostic deliberately opens offline detection labels to remove local
track fragmentation and identity switches.  It keeps the recorded detections,
camera poses, deterministic misses, and generated false alarms unchanged, then
anonymizes the resulting local track identifiers before running the frozen
enhanced-geometry dual-station associator.

The output measures an upper-bound diagnostic.  It is not online capability
evidence and must never be used to claim that the camera-local tracker has
already reached the reported result.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
import platform
from pathlib import Path
import statistics
import subprocess
import sys
from typing import Any, Mapping, Sequence

from dual_optical_40target.core import (
    AnonymousDetection,
    CameraSpec,
    CameraState,
    ray_observation_from_detection,
)
from dual_optical_40target.online_benchmark import (
    _WhitelistTemporalAssociator,
    _to_internal_snapshot,
    load_frozen_route,
)

from .contracts import (
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    benchmark_protocol_from_mapping,
    write_json,
)
from .dataset import (
    CORRUPTION_POLICY,
    _camera_states,
    _false_detections,
    _false_track_specs,
    _load_raw_episode,
    _should_drop,
    build_shared_candidate_graph,
    sha256_file,
    validate_raw_episode,
)
from .tracking import (
    SharedBearingTrack,
    _innovation,
    _new_track,
    _scanlets_for_sweep,
    _update_track,
    load_tracker_freeze,
)


SCHEMA_VERSION = "s180-oracle-local-geometry-offline-v1"
DEFAULT_TARGET_COUNTS = (20, 40, 60)
DEFAULT_CONDITIONS = ("clean", "light")


def _opaque_track_id(
    seed: int, condition: str, camera_id: str, offline_identity: str
) -> str:
    payload = f"{seed}|{condition}|{camera_id}|{offline_identity}".encode("utf-8")
    suffix = hashlib.sha256(payload).hexdigest()[:16]
    return f"{camera_id}-ORACLE-{suffix}"


def _camera_context(
    scenario: Mapping[str, Any], scan_rows: Sequence[Mapping[str, str]]
) -> tuple[
    CameraSpec,
    tuple[str, str],
    dict[str, tuple[float, float, float]],
    dict[tuple[str, int], CameraState],
]:
    config = scenario["scenario"]
    values = scenario["camera"]
    camera = CameraSpec(
        width=int(values["width"]),
        height=int(values["height"]),
        horizontal_fov_deg=float(values["horizontal_fov_deg"]),
        equivalent_focal_length_mm=float(values["equivalent_focal_length_mm"]),
        stated_ifov_mrad=float(values["stated_ifov_mrad"]),
    )
    camera_ids = (str(config["camera_a_name"]), str(config["camera_b_name"]))
    positions = {
        camera_ids[0]: tuple(
            float(value) for value in config["camera_a_position_ned"]
        ),
        camera_ids[1]: tuple(
            float(value) for value in config["camera_b_position_ned"]
        ),
    }
    states = _camera_states(scan_rows)
    positioned_states = {
        key: CameraState(
            camera_id=state.camera_id,
            frame_index=state.frame_index,
            timestamp=state.timestamp,
            position_ned=positions[state.camera_id],
            yaw_deg=state.yaw_deg,
            pitch_deg=state.pitch_deg,
        )
        for key, state in states.items()
    }
    return camera, camera_ids, positions, positioned_states


def _build_oracle_tracks(
    *,
    episode_dir: Path,
    protocol: Any,
    tracker_config: Any,
    condition: str,
) -> tuple[
    tuple[str, str],
    dict[str, tuple[float, float, float]],
    CameraSpec,
    dict[str, dict[str, SharedBearingTrack]],
    dict[str, str],
    dict[str, Any],
]:
    scenario, raw_detections, scan_rows, raw_truth = _load_raw_episode(episode_dir)
    camera, camera_ids, positions, states = _camera_context(scenario, scan_rows)
    seed = int(scenario["scenario"]["seed"])
    policy = CORRUPTION_POLICY[condition]

    kept: list[AnonymousDetection] = []
    identity_by_detection: dict[str, str] = {}
    dropped_detection_count = 0
    for item in raw_detections:
        if _should_drop(
            seed,
            condition,
            item.detection_uid,
            float(policy["miss_probability"]),
        ):
            dropped_detection_count += 1
            continue
        detection = AnonymousDetection(**asdict(item))
        kept.append(detection)
        identity_by_detection[detection.detection_uid] = raw_truth[
            detection.detection_uid
        ]

    false_specs = _false_track_specs(
        protocol, seed, condition, camera_ids, states
    )
    false_detection_count = 0
    for detection, false_identity in _false_detections(
        false_specs,
        states,
        camera,
        sample_rate_hz=protocol.sample_rate_hz,
    ):
        kept.append(detection)
        identity_by_detection[detection.detection_uid] = false_identity
        false_detection_count += 1

    confidence_by_uid = {
        detection.detection_uid: detection.confidence for detection in kept
    }
    grouped: dict[tuple[str, str, int], list[Any]] = {}
    for detection in kept:
        state = states[(detection.camera_id, detection.frame_index)]
        observation = ray_observation_from_detection(
            detection,
            state,
            camera,
            scan_period_s=protocol.scan_period_s,
            scan_mode=protocol.scan_mode,
        )
        identity = identity_by_detection[detection.detection_uid]
        grouped.setdefault(
            (detection.camera_id, identity, observation.sweep_index), []
        ).append(observation)

    scanlets_by_track: dict[tuple[str, str], list[Any]] = {}
    for (camera_id, identity, sweep), observations in sorted(grouped.items()):
        scanlets = _scanlets_for_sweep(
            camera_id,
            sweep,
            observations,
            confidence_by_uid,
            tracker_config,
        )
        if len(scanlets) != 1:
            raise RuntimeError(
                "truth-grouped observations did not collapse to one scanlet: "
                f"camera={camera_id}, identity={identity}, sweep={sweep}, "
                f"count={len(scanlets)}"
            )
        scanlets_by_track.setdefault((camera_id, identity), []).append(scanlets[0])

    tracks_by_camera: dict[str, dict[str, SharedBearingTrack]] = {
        camera_id: {} for camera_id in camera_ids
    }
    truth_by_opaque_track: dict[str, str] = {}
    for (camera_id, identity), scanlets in sorted(scanlets_by_track.items()):
        ordered = sorted(scanlets, key=lambda item: (item.sweep_index, item.timestamp))
        track = _new_track(camera_id, ordered[0], tracker_config)
        opaque_id = _opaque_track_id(seed, condition, camera_id, identity)
        track.track_id = opaque_id
        for scanlet in ordered[1:]:
            mahalanobis2, _, _, _ = _innovation(track, scanlet, tracker_config)
            _update_track(
                track,
                scanlet,
                mahalanobis2=max(0.0, float(mahalanobis2)),
                config=tracker_config,
            )
        tracks_by_camera[camera_id][opaque_id] = track
        truth_by_opaque_track[opaque_id] = identity

    diagnostics = {
        "retained_real_detection_count": len(raw_detections)
        - dropped_detection_count,
        "dropped_detection_count": dropped_detection_count,
        "false_detection_count": false_detection_count,
        "false_track_count": len(false_specs),
        "oracle_track_count_by_camera": {
            camera_id: len(tracks_by_camera[camera_id])
            for camera_id in camera_ids
        },
        "real_oracle_track_count_by_camera": {
            camera_id: sum(
                not truth_by_opaque_track[track_id].startswith("FA-")
                for track_id in tracks_by_camera[camera_id]
            )
            for camera_id in camera_ids
        },
    }
    return (
        camera_ids,
        positions,
        camera,
        tracks_by_camera,
        truth_by_opaque_track,
        diagnostics,
    )


def _snapshot_track(
    track: SharedBearingTrack,
    *,
    current_sweep: int,
    cutoff_timestamp: float,
    maximum_missed_sweeps: int,
) -> SnapshotTrack | None:
    source_samples = [
        sample
        for sample in track.samples
        if sample.timestamp < cutoff_timestamp - 1.0e-9
    ]
    if not source_samples:
        return None
    hit_sweeps = {int(sample.sweep_index) for sample in source_samples}
    last_hit_sweep = max(hit_sweeps)
    missed_sweeps = max(0, int(current_sweep) - last_hit_sweep)
    if missed_sweeps > maximum_missed_sweeps:
        return None
    mature = len(hit_sweeps) >= 2
    if missed_sweeps:
        state = "coasting" if mature else "tentative"
    else:
        state = "confirmed" if mature else "tentative"
    samples = tuple(
        SnapshotTrackSample(
            sweep_index=int(sample.sweep_index),
            timestamp=float(sample.timestamp),
            direction_ned=tuple(float(value) for value in sample.direction_ned),
            detection_count=len(sample.detection_uids),
            bbox_area_px2=float(sample.bbox_area_px2),
            confidence=float(sample.confidence),
            measurement_covariance_deg2=tuple(
                float(value) for value in sample.measurement_covariance_deg2
            ),
            state_vector=tuple(float(value) for value in sample.state_vector),
            state_covariance=tuple(
                float(value) for value in sample.state_covariance
            ),
            innovation_mahalanobis2=float(sample.innovation_mahalanobis2),
        )
        for sample in source_samples
    )
    return SnapshotTrack(
        track_id=track.track_id,
        camera_id=track.camera_id,
        samples=samples,
        source_kind="anonymous",
        track_state=state,
        recent_sweep_hits=tuple(
            sweep in hit_sweeps
            for sweep in range(current_sweep - 2, current_sweep + 1)
        ),
        missed_sweep_count=missed_sweeps,
        ambiguity_count=0,
    )


def _score_matches(
    matches: Sequence[Any],
    truth_by_track: Mapping[str, str],
    target_count: int,
) -> dict[str, Any]:
    correct_truths: set[str] = set()
    correct_count = 0
    for match in matches:
        truth_a = truth_by_track.get(match.track_a_id)
        truth_b = truth_by_track.get(match.track_b_id)
        if truth_a is not None and not truth_a.startswith("FA-") and truth_a == truth_b:
            correct_count += 1
            correct_truths.add(truth_a)
    selected_count = len(matches)
    return {
        "match_count": selected_count,
        "correct_match_count": correct_count,
        "false_match_count": selected_count - correct_count,
        "precision": correct_count / selected_count if selected_count else 0.0,
        "coverage": len(correct_truths) / max(int(target_count), 1),
        "correct_unique_target_count": len(correct_truths),
    }


def _run_episode(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    target_root = Path(str(task["target_root"])).resolve()
    target_count = int(task["target_count"])
    seed = int(task["seed"])
    condition = str(task["condition"])
    manifest_path = target_root / "dataset" / "test_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    tracker_freeze = Path(str(manifest["tracker_freeze"]))
    _, tracker_config = load_tracker_freeze(tracker_freeze)
    route_freeze = target_root / "dataset" / "freezes" / "epipolar_mht" / "freeze_manifest.json"
    frozen_route = load_frozen_route(route_freeze)
    episode_dir = (
        target_root
        / "raw"
        / "test"
        / f"airsim_seed_{seed}_online{target_count}"
    )
    validation = validate_raw_episode(
        episode_dir,
        protocol,
        expected_seed=seed,
        split_override="test",
    )
    (
        camera_ids,
        positions,
        camera,
        oracle_tracks,
        truth_by_track,
        corruption_diagnostics,
    ) = _build_oracle_tracks(
        episode_dir=episode_dir,
        protocol=protocol,
        tracker_config=tracker_config,
        condition=condition,
    )
    associator = _WhitelistTemporalAssociator(frozen_route.parameters)
    rows: list[dict[str, Any]] = []
    for revolution in range(1, protocol.association_round_count + 1):
        cutoff = float(revolution * protocol.association_round_period_s)
        current_sweep = revolution - 1
        snapshot_tracks: dict[str, tuple[SnapshotTrack, ...]] = {}
        for camera_id in camera_ids:
            converted = [
                value
                for track in oracle_tracks[camera_id].values()
                if (
                    value := _snapshot_track(
                        track,
                        current_sweep=current_sweep,
                        cutoff_timestamp=cutoff,
                        maximum_missed_sweeps=tracker_config.maximum_missed_sweeps,
                    )
                )
                is not None
            ]
            snapshot_tracks[camera_id] = tuple(
                sorted(converted, key=lambda item: item.track_id)
            )
        candidate_pairs, candidate_summary, candidate_fingerprint = (
            build_shared_candidate_graph(
                tracks=snapshot_tracks,
                camera_ids=camera_ids,
                camera_positions_ned=positions,
                cutoff_timestamp=cutoff,
                target_count=target_count,
            )
        )
        snapshot = RevolutionSnapshot(
            protocol_fingerprint=protocol.fingerprint,
            seed=seed,
            split="test",
            corruption_level=condition,
            revolution_index=revolution,
            cutoff_timestamp=cutoff,
            camera_ids=camera_ids,
            camera_positions_ned=positions,
            focal_length_px=camera.focal_length_px,
            tracks=snapshot_tracks,
            target_count=target_count,
            tracker_fingerprint=f"oracle-local-track-v1-{target_count}",
            geometry_candidate_pairs=candidate_pairs,
            candidate_graph_fingerprint=candidate_fingerprint,
            candidate_graph_summary=candidate_summary,
            corruption_summary=corruption_diagnostics,
            source_hashes={
                "raw_scenario_sha256": validation["files"]["scenario"],
                "raw_detection_sha256": validation["files"]["detections"],
                "raw_scan_sha256": validation["files"]["scan"],
                "offline_detection_truth_sha256": validation["files"][
                    "detection_truth"
                ],
            },
            association_round_period_s=protocol.association_round_period_s,
            association_round_count=protocol.association_round_count,
        )
        result = associator.process_snapshot(
            _to_internal_snapshot(snapshot), candidate_pairs
        )
        selected = _score_matches(
            result.selected_matches, truth_by_track, target_count
        )
        confirmed = _score_matches(
            result.confirmed_matches, truth_by_track, target_count
        )
        common_truths = {
            truth_by_track[track.track_id]
            for track in snapshot_tracks[camera_ids[0]]
            if not truth_by_track[track.track_id].startswith("FA-")
        } & {
            truth_by_track[track.track_id]
            for track in snapshot_tracks[camera_ids[1]]
            if not truth_by_track[track.track_id].startswith("FA-")
        }
        retained_truths = {
            truth_by_track[left]
            for left, right in candidate_pairs
            if truth_by_track.get(left) == truth_by_track.get(right)
            and not truth_by_track.get(left, "FA-").startswith("FA-")
        }
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "target_count": target_count,
                "seed": seed,
                "condition": condition,
                "revolution_index": revolution,
                "cutoff_timestamp_s": cutoff,
                "selected_match_count": selected["match_count"],
                "selected_correct_match_count": selected["correct_match_count"],
                "selected_false_match_count": selected["false_match_count"],
                "selected_precision": selected["precision"],
                "selected_fixed_target_coverage": selected["coverage"],
                "selected_correct_unique_target_count": selected[
                    "correct_unique_target_count"
                ],
                "confirmed_match_count": confirmed["match_count"],
                "confirmed_correct_match_count": confirmed[
                    "correct_match_count"
                ],
                "confirmed_false_match_count": confirmed["false_match_count"],
                "confirmed_precision": confirmed["precision"],
                "confirmed_fixed_target_coverage": confirmed["coverage"],
                "confirmed_correct_unique_target_count": confirmed[
                    "correct_unique_target_count"
                ],
                "common_visible_target_count": len(common_truths),
                "true_candidate_retained_count": len(retained_truths),
                "true_candidate_retention_rate": len(retained_truths)
                / max(len(common_truths), 1),
                "candidate_pair_count": len(candidate_pairs),
                "left_track_count": int(candidate_summary["left_track_count"]),
                "right_track_count": int(candidate_summary["right_track_count"]),
                "fit_evaluation_count": result.fit_evaluation_count,
                "coarse_gate_pass_count": result.coarse_gate_pass_count,
                "screening_ms": result.screening_elapsed_ms,
                "fitting_ms": result.fitting_elapsed_ms,
                "assignment_ms": result.assignment_elapsed_ms,
                "state_update_ms": result.state_update_elapsed_ms,
                "processing_ms": result.processing_elapsed_ms,
                "deadline_applied": False,
                "truth_used_to_construct_local_tracks": True,
                "truth_exposed_to_dual_station_associator": False,
            }
        )
    return rows


def _mean(values: Sequence[float]) -> float:
    return float(statistics.fmean(values)) if values else 0.0


def _aggregate(final_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for row in final_rows:
        groups.setdefault(
            (int(row["target_count"]), str(row["condition"])), []
        ).append(row)
    result: list[dict[str, Any]] = []
    for (target_count, condition), rows in sorted(groups.items()):
        selected_total = sum(int(row["selected_match_count"]) for row in rows)
        selected_correct = sum(
            int(row["selected_correct_match_count"]) for row in rows
        )
        confirmed_total = sum(int(row["confirmed_match_count"]) for row in rows)
        confirmed_correct = sum(
            int(row["confirmed_correct_match_count"]) for row in rows
        )
        denominator = target_count * len(rows)
        result.append(
            {
                "target_count": target_count,
                "condition": condition,
                "seed_count": len(rows),
                "seeds": sorted(int(row["seed"]) for row in rows),
                "selected_match_count": selected_total,
                "selected_correct_match_count": selected_correct,
                "selected_false_match_count": selected_total - selected_correct,
                "selected_micro_precision": selected_correct
                / max(selected_total, 1),
                "selected_fixed_target_coverage": sum(
                    int(row["selected_correct_unique_target_count"])
                    for row in rows
                )
                / max(denominator, 1),
                "selected_seed_mean_precision": _mean(
                    [float(row["selected_precision"]) for row in rows]
                ),
                "selected_seed_min_precision": min(
                    float(row["selected_precision"]) for row in rows
                ),
                "selected_seed_max_precision": max(
                    float(row["selected_precision"]) for row in rows
                ),
                "selected_seed_mean_coverage": _mean(
                    [
                        float(row["selected_fixed_target_coverage"])
                        for row in rows
                    ]
                ),
                "selected_seed_min_coverage": min(
                    float(row["selected_fixed_target_coverage"])
                    for row in rows
                ),
                "selected_seed_max_coverage": max(
                    float(row["selected_fixed_target_coverage"])
                    for row in rows
                ),
                "confirmed_match_count": confirmed_total,
                "confirmed_correct_match_count": confirmed_correct,
                "confirmed_false_match_count": confirmed_total
                - confirmed_correct,
                "confirmed_micro_precision": confirmed_correct
                / max(confirmed_total, 1),
                "confirmed_fixed_target_coverage": sum(
                    int(row["confirmed_correct_unique_target_count"])
                    for row in rows
                )
                / max(denominator, 1),
                "mean_true_candidate_retention_rate": _mean(
                    [
                        float(row["true_candidate_retention_rate"])
                        for row in rows
                    ]
                ),
                "processing_p95_ms": float(
                    sorted(float(row["processing_ms"]) for row in rows)[
                        max(0, math.ceil(0.95 * len(rows)) - 1)
                    ]
                ),
            }
        )
    return result


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _pct(value: float) -> str:
    return f"{100.0 * float(value):.2f}%"


def _write_report(
    path: Path,
    aggregate: Sequence[Mapping[str, Any]],
    source_root: Path,
) -> None:
    lines = [
        "# 单站正确关联条件下双站配准离线诊断",
        "",
        "## 结论",
        "",
        "本试验把每台光电的真实检测按离线标签合成为完全正确的单站航迹，再将航迹编号匿名化，送入冻结的增强几何双站配准流程。结果只回答“单站关联不出错时，双站算法还能做到多少”，不代表在线单站跟踪已经达到该水平。",
        "",
        "## 口径",
        "",
        "- 保留原始 AirSim 检测、相机姿态、云台误差和时间戳。",
        "- 轻干扰仍保留确定性的 3% 漏检和每台每秒 2 个虚警；未补回漏检，也未删除虚警。",
        "- 离线真值只用于构造正确单站航迹和最终评分；双站候选生成、几何拟合和一一匹配看不到真实目标编号。",
        "- 使用 20、40、60 目标，每种规模无干扰和轻干扰各 5 个测试种子，共 30 个 episode。",
        "- 指标取第 12 圈。精度为正确配准数除以全部已给出的配准数；覆盖度为正确配准到的不同目标数除以固定目标总数。",
        "- 为隔离算法质量，本诊断不执行 1 秒在线超时清空；运行时间单独记录。",
        "",
        "## 结果",
        "",
        "| 目标数 | 条件 | 种子数 | 正确/给出 | 配准精度 | 配准覆盖度 | 确认后精度 | 确认后覆盖度 | 候选保留率 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    condition_names = {"clean": "无干扰", "light": "轻干扰"}
    for row in aggregate:
        lines.append(
            "| {target_count} | {condition} | {seed_count} | {correct}/{total} | "
            "{precision} | {coverage} | {confirmed_precision} | "
            "{confirmed_coverage} | {retention} |".format(
                target_count=row["target_count"],
                condition=condition_names.get(
                    str(row["condition"]), str(row["condition"])
                ),
                seed_count=row["seed_count"],
                correct=row["selected_correct_match_count"],
                total=row["selected_match_count"],
                precision=_pct(float(row["selected_micro_precision"])),
                coverage=_pct(float(row["selected_fixed_target_coverage"])),
                confirmed_precision=_pct(
                    float(row["confirmed_micro_precision"])
                ),
                confirmed_coverage=_pct(
                    float(row["confirmed_fixed_target_coverage"])
                ),
                retention=_pct(
                    float(row["mean_true_candidate_retention_rate"])
                ),
            )
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "该结果是离线真值辅助上限诊断。它消除了单站航迹断裂、错误重接和编号交换，但没有消除检测缺失、虚警、视角差异和云台姿态误差。若结果明显高于现有端到端结果，差值主要来自单站轨迹关联；若仍有缺口，则需要继续检查候选门控和双站几何关联。",
            "",
            "## 证据",
            "",
            f"- 输入根目录：`{source_root}`",
            "- 逐圈结果：`oracle_round_metrics.csv`",
            "- 最后一圈逐种子结果：`oracle_final_seed_metrics.csv`",
            "- 汇总和数据血缘：`oracle_aggregate.json`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _git_provenance(repo_root: Path) -> dict[str, Any]:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=repo_root,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()

    status = run("status", "--short")
    return {
        "git_commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(status),
        "git_status_short_sha256": hashlib.sha256(
            status.encode("utf-8")
        ).hexdigest(),
    }


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("numpy", "scipy"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return versions


def _replay_command(
    source_root: Path,
    output_dir: Path,
    target_counts: Sequence[int],
    conditions: Sequence[str],
    seeds: Sequence[int] | None,
    workers: int,
) -> list[str]:
    command = [
        "python3",
        "-m",
        "dual_optical_online_benchmark.s180_oracle_geometry_offline",
        "--source-root",
        str(source_root),
        "--output-dir",
        str(output_dir),
        "--workers",
        str(workers),
    ]
    if tuple(target_counts) != DEFAULT_TARGET_COUNTS:
        for target_count in target_counts:
            command.extend(("--target-count", str(target_count)))
    if tuple(conditions) != DEFAULT_CONDITIONS:
        for condition in conditions:
            command.extend(("--condition", str(condition)))
    if seeds is not None:
        for seed in seeds:
            command.extend(("--seed", str(seed)))
    return command


def _source_inputs(
    *,
    repo_root: Path,
    source_root: Path,
    source_manifests: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    inputs: list[dict[str, str]] = []
    seen: set[Path] = set()

    def append(role: str, path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        try:
            stored_path = resolved.relative_to(repo_root).as_posix()
        except ValueError:
            stored_path = str(resolved)
        inputs.append(
            {"role": role, "path": stored_path, "sha256": sha256_file(resolved)}
        )

    append("source_campaign_reproduction_manifest", source_root / "reproduction_manifest.json")
    for values in source_manifests.values():
        append("test_manifest", Path(str(values["test_manifest"])))
        append("shared_tracker_freeze", Path(str(values["tracker_freeze"])))
        append("enhanced_geometry_freeze", Path(str(values["route_freeze"])))
    episode_keys = {
        (int(task["target_count"]), int(task["seed"])) for task in tasks
    }
    for target_count, seed in sorted(episode_keys):
        episode = (
            source_root
            / f"targets_{target_count:03d}"
            / "raw"
            / "test"
            / f"airsim_seed_{seed}_online{target_count}"
        )
        append("raw_scenario", episode / "scenario.json")
        append("anonymous_observations", episode / "online" / "anonymous_detections.csv")
        append("camera_pose_timestamps", episode / "online" / "camera_scan.csv")
        append("offline_detection_truth", episode / "truth" / "detection_truth.csv")
    for relative in (
        "research_modules/independent_experiments/dual_optical_online_benchmark/s180_oracle_geometry_offline.py",
        "research_modules/independent_experiments/dual_optical_online_benchmark/contracts.py",
        "research_modules/independent_experiments/dual_optical_online_benchmark/dataset.py",
        "research_modules/independent_experiments/dual_optical_online_benchmark/tracking.py",
        "research_modules/independent_experiments/dual_optical_40target/core.py",
        "research_modules/independent_experiments/dual_optical_40target/online.py",
        "research_modules/independent_experiments/dual_optical_40target/online_benchmark.py",
    ):
        append("source_file", repo_root / relative)
    return inputs


def _write_reproduction_manifest(
    *,
    repo_root: Path,
    source_root: Path,
    output_dir: Path,
    target_counts: Sequence[int],
    conditions: Sequence[str],
    seeds: Sequence[int] | None,
    workers: int,
    source_manifests: Mapping[str, Any],
    tasks: Sequence[Mapping[str, Any]],
) -> Path:
    command = _replay_command(
        source_root,
        output_dir,
        target_counts,
        conditions,
        seeds,
        workers,
    )
    protocols = []
    for target_count in target_counts:
        manifest_path = Path(
            str(source_manifests[str(target_count)]["test_manifest"])
        )
        protocols.append(json.loads(manifest_path.read_text(encoding="utf-8"))["protocol"])
    source_inputs = _source_inputs(
        repo_root=repo_root,
        source_root=source_root,
        source_manifests=source_manifests,
        tasks=tasks,
    )
    write_json(
        output_dir / "protocol.json",
        {
            "schema_version": SCHEMA_VERSION,
            "protocols": protocols,
            "target_counts": list(target_counts),
            "conditions": list(conditions),
            "metric_round": 12,
        },
    )
    write_json(
        output_dir / "replay" / "input_index.json",
        {
            "schema_version": "s180-oracle-replay-input-index-v1",
            "inputs_are_immutable_by_sha256": True,
            "inputs": source_inputs,
        },
    )
    write_json(
        output_dir / "model_bundle.json",
        {
            "schema_version": "s180-oracle-frozen-route-bundle-v1",
            "learned_model_used": False,
            "bundles": [
                {
                    "target_count": int(target_count),
                    "shared_tracker_freeze": source_manifests[str(target_count)][
                        "tracker_freeze"
                    ],
                    "shared_tracker_freeze_sha256": source_manifests[
                        str(target_count)
                    ]["tracker_freeze_sha256"],
                    "enhanced_geometry_freeze": source_manifests[str(target_count)][
                        "route_freeze"
                    ],
                    "enhanced_geometry_freeze_sha256": source_manifests[
                        str(target_count)
                    ]["route_freeze_sha256"],
                }
                for target_count in target_counts
            ],
        },
    )
    aggregate_path = output_dir / "oracle_aggregate.json"
    manifest = {
        "schema_version": "msm-experiment-reproduction-v1",
        "experiment_id": output_dir.name,
        "status": "diagnostic_offline_replay",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": "单站航迹完全正确时，冻结的双站增强几何算法能达到多少配准精度和固定目标覆盖度",
        "source": {
            **_git_provenance(repo_root),
            "entry_point": "dual_optical_online_benchmark.s180_oracle_geometry_offline",
            "cwd": str(repo_root),
            "command": command,
            "environment": {
                "PYTHONPATH": "research_modules/independent_experiments",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
            },
        },
        "runtime": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "dependencies": _dependency_versions(),
            "simulator": "deterministic offline replay of preserved AirSim records",
            "simulator_version": "source records produced by AirSim 1.8.1",
            "hardware_summary": "CPU; worker count affects latency only",
        },
        "scenario": {
            "protocols": protocols,
            "target_counts": list(target_counts),
            "conditions": list(conditions),
            "episode_count": len(tasks),
            "association_round_count": 12,
            "metric_round": 12,
        },
        "inputs": source_inputs,
        "outputs": {
            "metrics": [
                "oracle_aggregate.json",
                "oracle_round_metrics.csv",
                "oracle_final_seed_metrics.csv",
            ],
            "reports": ["S180_ORACLE_LOCAL_TRACK_DUAL_STATION_REPORT_CN.md"],
            "configs": ["protocol.json", "model_bundle.json"],
            "input_indexes": ["replay/input_index.json"],
            "logs": [],
            "figures": [],
        },
        "metrics_contract": {
            "definitions_path": "S180_ORACLE_LOCAL_TRACK_DUAL_STATION_REPORT_CN.md",
            "denominators": {
                "precision": "correct selected target pairs / all selected pairs",
                "coverage": "unique correctly selected targets / fixed target_count",
                "confirmed_precision": "correct confirmed target pairs / all confirmed pairs",
                "confirmed_coverage": "unique correctly confirmed targets / fixed target_count",
            },
            "acceptance": {},
            "availability_policy": "one-second deadline bypassed; all final-round rows retained",
        },
        "reproduction": {
            "offline_replay_command": " ".join(command),
            "full_rerun_command": None,
            "expected_metrics_sha256": sha256_file(aggregate_path),
            "comparison_tolerance": "quality metrics exact; wall-clock latency excluded",
            "known_nondeterminism": [
                "wall-clock stage latency varies with worker scheduling",
                "source worktree is dirty and is therefore pinned by individual source-file hashes",
            ],
        },
    }
    path = output_dir / "reproduction_manifest.json"
    write_json(path, manifest)
    return path


def finalize_existing_output(
    source_root: str | Path,
    output_dir: str | Path,
    *,
    workers: int,
) -> Path:
    """Add a lineage manifest to an already completed diagnostic run."""

    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir).resolve()
    payload = json.loads(
        (output_dir / "oracle_aggregate.json").read_text(encoding="utf-8")
    )
    target_counts = tuple(int(value) for value in payload["target_counts"])
    conditions = tuple(str(value) for value in payload["conditions"])
    source_manifests = payload["source_manifests"]
    tasks = [
        {
            "target_count": target_count,
            "seed": seed,
            "condition": condition,
        }
        for target_count in target_counts
        for seed in source_manifests[str(target_count)]["seeds"]
        for condition in conditions
    ]
    completed = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=source_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return _write_reproduction_manifest(
        repo_root=Path(completed.stdout.strip()).resolve(),
        source_root=source_root,
        output_dir=output_dir,
        target_counts=target_counts,
        conditions=conditions,
        seeds=None,
        workers=workers,
        source_manifests=source_manifests,
        tasks=tasks,
    )


def run_campaign(
    *,
    source_root: Path,
    output_dir: Path,
    target_counts: Sequence[int],
    conditions: Sequence[str],
    seeds: Sequence[int] | None,
    workers: int,
) -> Path:
    source_root = source_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    tasks: list[dict[str, Any]] = []
    source_manifests: dict[str, Any] = {}
    for target_count in target_counts:
        target_root = source_root / f"targets_{target_count:03d}"
        manifest_path = target_root / "dataset" / "test_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        protocol = benchmark_protocol_from_mapping(manifest["protocol"])
        selected_seeds = tuple(protocol.test_seeds)
        if seeds is not None:
            selected_seeds = tuple(seed for seed in selected_seeds if seed in seeds)
        if not selected_seeds:
            raise ValueError(f"no requested seed belongs to target_count={target_count}")
        route_freeze = target_root / "dataset" / "freezes" / "epipolar_mht" / "freeze_manifest.json"
        source_manifests[str(target_count)] = {
            "test_manifest": str(manifest_path),
            "test_manifest_sha256": sha256_file(manifest_path),
            "tracker_freeze": str(manifest["tracker_freeze"]),
            "tracker_freeze_sha256": sha256_file(manifest["tracker_freeze"]),
            "route_freeze": str(route_freeze),
            "route_freeze_sha256": sha256_file(route_freeze),
            "protocol_fingerprint": protocol.fingerprint,
            "seeds": list(selected_seeds),
        }
        for seed in selected_seeds:
            for condition in conditions:
                tasks.append(
                    {
                        "target_root": str(target_root),
                        "target_count": target_count,
                        "seed": seed,
                        "condition": condition,
                    }
                )
    round_rows: list[dict[str, Any]] = []
    if workers == 1:
        for task in tasks:
            round_rows.extend(_run_episode(task))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run_episode, task): task for task in tasks}
            for future in as_completed(futures):
                round_rows.extend(future.result())
    round_rows.sort(
        key=lambda row: (
            int(row["target_count"]),
            str(row["condition"]),
            int(row["seed"]),
            int(row["revolution_index"]),
        )
    )
    final_rows = [row for row in round_rows if int(row["revolution_index"]) == 12]
    aggregate = _aggregate(final_rows)
    output_dir.mkdir(parents=True)
    _write_csv(output_dir / "oracle_round_metrics.csv", round_rows)
    _write_csv(output_dir / "oracle_final_seed_metrics.csv", final_rows)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_only": True,
        "online_capability_claim_allowed": False,
        "truth_used_to_construct_local_tracks": True,
        "truth_exposed_to_dual_station_associator": False,
        "deadline_applied": False,
        "metric_round": 12,
        "precision_definition": "correct_selected_pairs / selected_pairs",
        "coverage_definition": "unique_correct_target_pairs / fixed_target_count",
        "conditions": list(conditions),
        "target_counts": list(target_counts),
        "episode_count": len(tasks),
        "source_root": str(source_root),
        "source_manifests": source_manifests,
        "aggregate": aggregate,
        "final_rows": final_rows,
    }
    write_json(output_dir / "oracle_aggregate.json", payload)
    _write_report(
        output_dir / "S180_ORACLE_LOCAL_TRACK_DUAL_STATION_REPORT_CN.md",
        aggregate,
        source_root,
    )
    completed = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        cwd=source_root,
        check=True,
        text=True,
        capture_output=True,
    )
    _write_reproduction_manifest(
        repo_root=Path(completed.stdout.strip()).resolve(),
        source_root=source_root,
        output_dir=output_dir,
        target_counts=target_counts,
        conditions=conditions,
        seeds=seeds,
        workers=workers,
        source_manifests=source_manifests,
        tasks=tasks,
    )
    return output_dir


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure dual-station association after truth-perfect local tracking."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--target-count",
        action="append",
        type=int,
        choices=DEFAULT_TARGET_COUNTS,
        dest="target_counts",
    )
    parser.add_argument(
        "--condition",
        action="append",
        choices=DEFAULT_CONDITIONS,
        dest="conditions",
    )
    parser.add_argument("--seed", action="append", type=int, dest="seeds")
    parser.add_argument("--workers", type=int, default=1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.workers < 1:
        raise ValueError("workers must be positive")
    output = run_campaign(
        source_root=args.source_root,
        output_dir=args.output_dir,
        target_counts=tuple(args.target_counts or DEFAULT_TARGET_COUNTS),
        conditions=tuple(args.conditions or DEFAULT_CONDITIONS),
        seeds=None if args.seeds is None else tuple(args.seeds),
        workers=int(args.workers),
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
