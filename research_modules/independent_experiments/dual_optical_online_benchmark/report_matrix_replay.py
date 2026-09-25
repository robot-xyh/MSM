"""Rebuild the dual-optical report matrices from preserved anonymous evidence.

The campaign is diagnostic and deliberately keeps three evidence classes
separate:

* a 360-degree oracle-local-track replay built from offline labels;
* a 360-degree replay of the preserved camera-local tracks;
* an S180 replay whose medium/heavy observations are deterministically derived
  from the preserved anonymous detections with the recorded corruption policy.

Only confirmed cross-station relations are scored.  Offline quality is retained
when processing exceeds the one-second deadline; the same late result contributes
zero to the on-time coverage metric.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from dual_optical_40target.online_benchmark import (
    _WhitelistTemporalAssociator,
    _to_internal_snapshot,
)
from dual_optical_40target.core import ray_observation_from_detection

from .contracts import (
    CORRUPTION_LEVELS,
    RevolutionSnapshot,
    benchmark_protocol_from_mapping,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
)
from .dataset import (
    _load_raw_episode,
    build_shared_candidate_graph,
    materialize_episode,
    sha256_file,
    write_dataset_manifest,
)
from .offline_scale_replay import _load_route
from .s180_oracle_geometry_offline import (
    _camera_context,
    _opaque_track_id,
    _snapshot_track,
)
from .tracking import (
    SharedBearingTrack,
    SharedTrackerConfig,
    _innovation,
    _new_track,
    _scanlets_for_sweep,
    _update_track,
    load_tracker_freeze,
)


SCHEMA_VERSION = "dual-optical-report-matrix-replay-v1"
RUN_ID = "report_replay_20260819_v2"
TARGET_COUNTS = (20, 40, 60)
ROUTES = ("epipolar_mht", "gnn")
DEADLINE_MS = 1000.0
LOCAL_TRACK_PURITY_THRESHOLD = 0.85

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUTS_ROOT = PACKAGE_ROOT / "outputs"
CONTINUOUS_ROOT = OUTPUTS_ROOT / "scale_funnel_v3"
S180_ROOT = OUTPUTS_ROOT / "s180_1s_sector_v1"
TRANSFER_ROOT = OUTPUTS_ROOT / "offline_three_route_scale_v1"


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _percentile_nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(float(percentile) * len(ordered)) - 1)
    return ordered[index]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _dominant_truth(
    counts: Mapping[str, Any],
) -> tuple[str | None, int, int, float]:
    total = sum(max(0, int(value)) for value in counts.values())
    ranked = sorted(
        (
            (max(0, int(count)), str(identity))
            for identity, count in counts.items()
            if int(count) > 0 and not str(identity).startswith("FA-")
        ),
        reverse=True,
    )
    if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
        return None, 0, total, 0.0
    dominant_count, identity = ranked[0]
    purity = dominant_count / total if total else 0.0
    return identity, dominant_count, total, purity


def _single_station_diagnostics(
    snapshot: RevolutionSnapshot,
    labels: Mapping[str, Any],
) -> dict[str, Any]:
    counts_by_track = labels["track_truth_counts"]
    correct_truths_by_camera: dict[str, set[str]] = {}
    qualifying_count_by_camera_truth: dict[tuple[str, str], int] = defaultdict(int)
    truth_by_track: dict[str, str] = {}
    dominant_observation_count = 0
    labeled_observation_count = 0
    mixed_track_count = 0
    false_only_track_count = 0
    labeled_track_count = 0
    for camera_id in snapshot.camera_ids:
        correct_truths: set[str] = set()
        for track in snapshot.tracks[camera_id]:
            counts = counts_by_track.get(track.track_id, {})
            if not counts:
                continue
            labeled_track_count += 1
            identity, dominant_count, total, purity = _dominant_truth(counts)
            dominant_observation_count += dominant_count
            labeled_observation_count += total
            has_real = any(
                int(count) > 0 and not str(value).startswith("FA-")
                for value, count in counts.items()
            )
            if not has_real:
                false_only_track_count += 1
                continue
            if identity is None or purity < LOCAL_TRACK_PURITY_THRESHOLD:
                mixed_track_count += 1
                continue
            truth_by_track[track.track_id] = identity
            correct_truths.add(identity)
            qualifying_count_by_camera_truth[(camera_id, identity)] += 1
        correct_truths_by_camera[camera_id] = correct_truths
    duplicate_track_count = sum(
        max(0, count - 1) for count in qualifying_count_by_camera_truth.values()
    )
    correct_identity_count = sum(
        len(values) for values in correct_truths_by_camera.values()
    )
    opportunity_count = len(snapshot.camera_ids) * int(snapshot.target_count or 0)
    camera_a, camera_b = snapshot.camera_ids
    shared_correct_truths = (
        correct_truths_by_camera[camera_a] & correct_truths_by_camera[camera_b]
    )
    return {
        "single_station_correct_identity_count": correct_identity_count,
        "single_station_identity_opportunity_count": opportunity_count,
        "single_station_coverage": (
            correct_identity_count / opportunity_count if opportunity_count else 0.0
        ),
        "single_station_dominant_observation_count": dominant_observation_count,
        "single_station_labeled_observation_count": labeled_observation_count,
        "single_station_precision": (
            dominant_observation_count / labeled_observation_count
            if labeled_observation_count
            else 0.0
        ),
        "single_station_duplicate_track_count": duplicate_track_count,
        "single_station_mixed_track_count": mixed_track_count,
        "single_station_false_only_track_count": false_only_track_count,
        "single_station_labeled_track_count": labeled_track_count,
        "shared_correct_truth_count": len(shared_correct_truths),
        "truth_by_track": truth_by_track,
    }


def _score_matches(
    matches: Sequence[Any],
    truth_by_track: Mapping[str, str],
    target_count: int,
) -> dict[str, Any]:
    correct_count = 0
    correct_truths: set[str] = set()
    for match in matches:
        truth_a = truth_by_track.get(str(match.track_a_id))
        truth_b = truth_by_track.get(str(match.track_b_id))
        if truth_a is None or truth_b is None or truth_a != truth_b:
            continue
        correct_count += 1
        correct_truths.add(truth_a)
    output_count = len(matches)
    return {
        "output_match_count": output_count,
        "correct_match_count": correct_count,
        "false_match_count": output_count - correct_count,
        "association_precision": (
            correct_count / output_count if output_count else None
        ),
        "correct_unique_target_count": len(correct_truths),
        "fixed_target_coverage": len(correct_truths) / max(target_count, 1),
    }


def _continuous_target_root(target_count: int) -> Path:
    return CONTINUOUS_ROOT / f"targets_{target_count:03d}"


def _s180_target_root(target_count: int) -> Path:
    return S180_ROOT / f"targets_{target_count:03d}"


def _continuous_geometry_freeze(target_count: int) -> Path:
    if target_count == 20:
        return (
            _continuous_target_root(target_count)
            / "dataset/freezes/epipolar_mht/freeze_manifest.json"
        )
    return (
        TRANSFER_ROOT
        / f"targets_{target_count:03d}"
        / "freezes/epipolar_mht/transferred_freeze_manifest.json"
    )


def _route_freeze(profile: str, target_count: int, route_name: str) -> Path:
    if profile in {"continuous_360", "oracle_360"}:
        if route_name == "epipolar_mht":
            return _continuous_geometry_freeze(target_count)
        return (
            _continuous_target_root(target_count)
            / "dataset/freezes/gnn/freeze_manifest.json"
        )
    if profile == "s180":
        return (
            _s180_target_root(target_count)
            / f"dataset/freezes/{route_name}/freeze_manifest.json"
        )
    raise ValueError(f"unsupported profile: {profile}")


def _manifest_entries(
    manifest_path: Path, seed: int, condition: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _read_json(manifest_path)
    entries = sorted(
        (
            dict(entry)
            for entry in manifest["entries"]
            if int(entry["seed"]) == int(seed)
            and str(entry["corruption_level"]) == str(condition)
        ),
        key=lambda item: int(item["revolution_index"]),
    )
    if not entries:
        raise ValueError(
            f"no entries for seed={seed}, condition={condition}: {manifest_path}"
        )
    return manifest, entries


def _load_snapshot_and_labels(
    manifest_path: Path,
    entry: Mapping[str, Any],
) -> tuple[RevolutionSnapshot, dict[str, Any]]:
    root = manifest_path.parent
    snapshot_path = root / str(entry["snapshot_path"])
    label_path = root / str(entry["label_path"])
    if sha256_file(snapshot_path) != str(entry["snapshot_sha256"]):
        raise ValueError(f"snapshot hash changed: {snapshot_path}")
    if sha256_file(label_path) != str(entry["label_sha256"]):
        raise ValueError(f"label hash changed: {label_path}")
    snapshot = read_snapshot(snapshot_path)
    labels = _read_json(label_path)
    return snapshot, labels


def _base_result_row(
    *,
    profile: str,
    target_count: int,
    seed: int,
    condition: str,
    route_name: str,
    snapshot: RevolutionSnapshot,
    labels: Mapping[str, Any],
    matches: Sequence[Any],
    latency_ms: float,
    source_input_fingerprint: str,
    inference_input_fingerprint: str,
    route_freeze: Path,
    protocol_bridge_applied: bool,
    evidence_status: str,
) -> dict[str, Any]:
    local = _single_station_diagnostics(snapshot, labels)
    scored = _score_matches(
        matches,
        local["truth_by_track"],
        target_count,
    )
    deadline_met = latency_ms <= DEADLINE_MS
    residual_loss = max(
        0,
        int(local["shared_correct_truth_count"])
        - int(scored["correct_unique_target_count"]),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": profile,
        "target_count": target_count,
        "seed": seed,
        "condition": condition,
        "route_name": route_name,
        "round_index": int(snapshot.revolution_index),
        "source_input_fingerprint": source_input_fingerprint,
        "inference_input_fingerprint": inference_input_fingerprint,
        "route_freeze": str(route_freeze.resolve()),
        "route_freeze_sha256": sha256_file(route_freeze),
        "protocol_bridge_applied": protocol_bridge_applied,
        "evidence_status": evidence_status,
        **scored,
        "latency_ms": float(latency_ms),
        "deadline_ms": DEADLINE_MS,
        "deadline_met": deadline_met,
        "timed_out": not deadline_met,
        "on_time_correct_unique_target_count": (
            int(scored["correct_unique_target_count"]) if deadline_met else 0
        ),
        "on_time_fixed_target_coverage": (
            float(scored["fixed_target_coverage"]) if deadline_met else 0.0
        ),
        "dual_station_residual_loss_count": residual_loss,
        **{key: value for key, value in local.items() if key != "truth_by_track"},
    }


def _run_geometry_sequence(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    profile = str(task["profile"])
    target_count = int(task["target_count"])
    seed = int(task["seed"])
    condition = str(task["condition"])
    manifest_path = Path(str(task["manifest_path"])).resolve()
    freeze_path = Path(str(task["route_freeze"])).resolve()
    _, entries = _manifest_entries(manifest_path, seed, condition)
    route = _load_route(
        "epipolar_mht", freeze_path, diagnostic_lightweight=False
    )
    associator = _WhitelistTemporalAssociator(route.parameters)
    rows: list[dict[str, Any]] = []
    for entry in entries:
        snapshot, labels = _load_snapshot_and_labels(manifest_path, entry)
        started = time.perf_counter()
        result = associator.process_snapshot(
            _to_internal_snapshot(snapshot), snapshot.geometry_candidate_pairs
        )
        measured_ms = (time.perf_counter() - started) * 1000.0
        latency_ms = max(float(result.processing_elapsed_ms), measured_ms)
        fingerprint = snapshot_fingerprint(snapshot)
        rows.append(
            _base_result_row(
                profile=profile,
                target_count=target_count,
                seed=seed,
                condition=condition,
                route_name="epipolar_mht",
                snapshot=snapshot,
                labels=labels,
                matches=result.confirmed_matches,
                latency_ms=latency_ms,
                source_input_fingerprint=fingerprint,
                inference_input_fingerprint=fingerprint,
                route_freeze=freeze_path,
                protocol_bridge_applied=False,
                evidence_status=str(task["evidence_status"]),
            )
        )
    return rows


def _run_gnn_sequences(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    from dual_optical_100target_gnn.online import OnlineGNNAssociator

    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for task in tasks:
        key = (
            str(task["profile"]),
            int(task["target_count"]),
            str(task["route_freeze"]),
        )
        grouped[key].append(task)
    for (profile, target_count, freeze_text), group in sorted(grouped.items()):
        freeze_path = Path(freeze_text).resolve()
        freeze = _read_json(freeze_path)
        expected_protocol = str(freeze["protocol_fingerprint_sha256"])
        associator = OnlineGNNAssociator(str(freeze_path))
        for task in sorted(
            group, key=lambda value: (str(value["condition"]), int(value["seed"]))
        ):
            seed = int(task["seed"])
            condition = str(task["condition"])
            manifest_path = Path(str(task["manifest_path"])).resolve()
            _, entries = _manifest_entries(manifest_path, seed, condition)
            for entry in entries:
                snapshot, labels = _load_snapshot_and_labels(manifest_path, entry)
                source_fingerprint = snapshot_fingerprint(snapshot)
                protocol_bridge = snapshot.protocol_fingerprint != expected_protocol
                inference_snapshot = (
                    replace(snapshot, protocol_fingerprint=expected_protocol)
                    if protocol_bridge
                    else snapshot
                )
                started = time.perf_counter()
                result = associator.associate(inference_snapshot)
                measured_ms = (time.perf_counter() - started) * 1000.0
                latency_ms = max(
                    float(result.publication.end_to_end_ms), measured_ms
                )
                rows.append(
                    _base_result_row(
                        profile=profile,
                        target_count=target_count,
                        seed=seed,
                        condition=condition,
                        route_name="gnn",
                        snapshot=snapshot,
                        labels=labels,
                        matches=result.confirmed_matches,
                        latency_ms=latency_ms,
                        source_input_fingerprint=source_fingerprint,
                        inference_input_fingerprint=snapshot_fingerprint(
                            inference_snapshot
                        ),
                        route_freeze=freeze_path,
                        protocol_bridge_applied=protocol_bridge,
                        evidence_status=str(task["evidence_status"]),
                    )
                )
        print(
            f"GNN complete: profile={profile}, target_count={target_count}, "
            f"sequences={len(group)}",
            flush=True,
        )
    return rows


def _legacy_compatible_tracker_config(path: Path) -> tuple[dict[str, Any], SharedTrackerConfig]:
    payload = _read_json(path)
    values = dict(payload["tracker_config"])
    values["allowed_heading_offsets_deg"] = tuple(
        float(value) for value in values["allowed_heading_offsets_deg"]
    )
    values["corridor_x_bounds_m"] = tuple(
        float(value) for value in values["corridor_x_bounds_m"]
    )
    config = SharedTrackerConfig(**values)
    return payload, config


def _build_report_oracle_tracks(
    *,
    episode_dir: Path,
    tracker_config: SharedTrackerConfig,
) -> tuple[
    tuple[str, str],
    dict[str, tuple[float, float, float]],
    Any,
    dict[str, dict[str, SharedBearingTrack]],
    dict[str, str],
    dict[str, Any],
]:
    """Build one truth-grouped local track per observed target and camera.

    Preserved 360-degree records can contain two short scanlets for one target
    at a sweep boundary.  The original oracle helper rejects that legacy
    representation.  This report-local adapter retains the strongest observed
    scanlet and records every discarded secondary fragment; it never creates a
    detection or interpolates a bearing.
    """

    scenario, raw_detections, scan_rows, raw_truth = _load_raw_episode(episode_dir)
    camera, camera_ids, positions, states = _camera_context(scenario, scan_rows)
    seed = int(scenario["scenario"]["seed"])
    confidence_by_uid = {
        detection.detection_uid: float(detection.confidence)
        for detection in raw_detections
    }
    grouped: dict[tuple[str, str, int], list[Any]] = defaultdict(list)
    retained_real_detection_count = 0
    for detection in raw_detections:
        identity = str(raw_truth[detection.detection_uid])
        if identity.startswith("FA-"):
            continue
        state = states[(detection.camera_id, detection.frame_index)]
        observation = ray_observation_from_detection(
            detection,
            state,
            camera,
            scan_period_s=float(scenario["scenario"]["scan_period_s"]),
            scan_mode=str(scenario["scenario"].get("scan_mode", "continuous_360")),
        )
        grouped[(detection.camera_id, identity, observation.sweep_index)].append(
            observation
        )
        retained_real_detection_count += 1

    scanlets_by_track: dict[tuple[str, str], list[Any]] = defaultdict(list)
    secondary_fragment_count = 0
    secondary_detection_count = 0
    multi_fragment_group_count = 0
    for (camera_id, identity, sweep), observations in sorted(grouped.items()):
        scanlets = _scanlets_for_sweep(
            camera_id,
            sweep,
            observations,
            confidence_by_uid,
            tracker_config,
        )
        if not scanlets:
            raise RuntimeError(
                "truth-grouped observations produced no scanlet: "
                f"camera={camera_id}, identity={identity}, sweep={sweep}"
            )
        if len(scanlets) > 1:
            multi_fragment_group_count += 1
        group_median_timestamp = float(
            np.median([observation.timestamp for observation in observations])
        )
        ranked = sorted(
            scanlets,
            key=lambda item: (
                -len(item.detection_uids),
                abs(float(item.timestamp) - group_median_timestamp),
                float(item.timestamp),
            ),
        )
        primary = ranked[0]
        secondary_fragment_count += len(ranked) - 1
        secondary_detection_count += sum(
            len(item.detection_uids) for item in ranked[1:]
        )
        scanlets_by_track[(camera_id, identity)].append(primary)

    expected_truths = {
        str(value)
        for value in raw_truth.values()
        if not str(value).startswith("FA-")
    }
    missing_camera_truths = sorted(
        (camera_id, identity)
        for camera_id in camera_ids
        for identity in expected_truths
        if (camera_id, identity) not in scanlets_by_track
    )
    if missing_camera_truths:
        raise RuntimeError(
            "oracle source has targets with no recorded observation at one station: "
            f"{missing_camera_truths[:10]}"
        )

    tracks_by_camera: dict[str, dict[str, SharedBearingTrack]] = {
        camera_id: {} for camera_id in camera_ids
    }
    truth_by_opaque_track: dict[str, str] = {}
    for (camera_id, identity), scanlets in sorted(scanlets_by_track.items()):
        ordered = sorted(scanlets, key=lambda item: (item.sweep_index, item.timestamp))
        track = _new_track(camera_id, ordered[0], tracker_config)
        opaque_id = _opaque_track_id(seed, "clean", camera_id, identity)
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
        "retained_real_detection_count": retained_real_detection_count,
        "dropped_detection_count": 0,
        "false_detection_count": 0,
        "false_track_count": 0,
        "oracle_track_count_by_camera": {
            camera_id: len(tracks_by_camera[camera_id])
            for camera_id in camera_ids
        },
        "real_oracle_track_count_by_camera": {
            camera_id: len(tracks_by_camera[camera_id])
            for camera_id in camera_ids
        },
        "legacy_multi_fragment_group_count": multi_fragment_group_count,
        "discarded_secondary_fragment_count": secondary_fragment_count,
        "discarded_secondary_detection_count": secondary_detection_count,
        "oracle_fragment_policy": (
            "retain_most_detections_then_nearest_group_median_timestamp"
        ),
    }
    return (
        camera_ids,
        positions,
        camera,
        tracks_by_camera,
        truth_by_opaque_track,
        diagnostics,
    )


def _oracle_context(
    *, target_count: int, seed: int
) -> tuple[
    Any,
    Any,
    tuple[str, str],
    dict[str, tuple[float, float, float]],
    Any,
    dict[str, dict[str, Any]],
    dict[str, str],
    dict[str, Any],
    Path,
]:
    target_root = _continuous_target_root(target_count)
    manifest_path = target_root / "dataset/test_manifest.json"
    manifest = _read_json(manifest_path)
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    tracker_path = Path(str(manifest["tracker_freeze"])).resolve()
    tracker_payload, tracker_config = _legacy_compatible_tracker_config(tracker_path)
    episode_dir = (
        target_root
        / "raw/test"
        / f"airsim_seed_{seed}_online{target_count}"
    )
    (
        camera_ids,
        positions,
        camera,
        oracle_tracks,
        truth_by_track,
        diagnostics,
    ) = _build_report_oracle_tracks(
        episode_dir=episode_dir,
        tracker_config=tracker_config,
    )
    real_counts = diagnostics["real_oracle_track_count_by_camera"]
    if any(int(real_counts[camera_id]) != target_count for camera_id in camera_ids):
        raise RuntimeError(
            "oracle input is not one-target-one-track at both stations: "
            f"target_count={target_count}, seed={seed}, counts={real_counts}"
        )
    if diagnostics["false_track_count"] or diagnostics["false_detection_count"]:
        raise RuntimeError("clean oracle input unexpectedly contains false alarms")
    diagnostics = {
        **diagnostics,
        "source_tracker_fingerprint": str(tracker_payload["tracker_fingerprint"]),
        "oracle_builder_config_fingerprint": tracker_config.fingerprint,
        "legacy_tracker_defaults_added": (
            str(tracker_payload["tracker_fingerprint"]) != tracker_config.fingerprint
        ),
    }
    return (
        protocol,
        tracker_config,
        camera_ids,
        positions,
        camera,
        oracle_tracks,
        truth_by_track,
        diagnostics,
        episode_dir,
    )


def _oracle_snapshot(
    *,
    protocol: Any,
    tracker_config: SharedTrackerConfig,
    target_count: int,
    seed: int,
    revolution: int,
    camera_ids: tuple[str, str],
    positions: Mapping[str, tuple[float, float, float]],
    camera: Any,
    oracle_tracks: Mapping[str, Mapping[str, Any]],
    diagnostics: Mapping[str, Any],
    source_hashes: Mapping[str, str],
) -> RevolutionSnapshot:
    cutoff = float(revolution * protocol.association_round_period_s)
    current_sweep = revolution - 1
    snapshot_tracks: dict[str, tuple[Any, ...]] = {}
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
            sorted(converted, key=lambda value: value.track_id)
        )
    pairs, summary, fingerprint = build_shared_candidate_graph(
        tracks=snapshot_tracks,
        camera_ids=camera_ids,
        camera_positions_ned=positions,
        cutoff_timestamp=cutoff,
        target_count=target_count,
    )
    return RevolutionSnapshot(
        protocol_fingerprint=protocol.fingerprint,
        seed=seed,
        split="test",
        corruption_level="clean",
        revolution_index=revolution,
        cutoff_timestamp=cutoff,
        camera_ids=camera_ids,
        camera_positions_ned=positions,
        focal_length_px=camera.focal_length_px,
        tracks=snapshot_tracks,
        target_count=target_count,
        tracker_fingerprint=f"oracle-local-track-20260819-{target_count}",
        geometry_candidate_pairs=pairs,
        candidate_graph_fingerprint=fingerprint,
        candidate_graph_summary=summary,
        corruption_summary=dict(diagnostics),
        source_hashes=dict(source_hashes),
        association_round_period_s=protocol.association_round_period_s,
        association_round_count=protocol.association_round_count,
    )


def _oracle_labels(
    snapshot: RevolutionSnapshot,
    truth_by_track: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "offline_truth_only": True,
        "track_truth_counts": {
            track.track_id: {truth_by_track[track.track_id]: len(track.samples)}
            for camera_id in snapshot.camera_ids
            for track in snapshot.tracks[camera_id]
        },
    }


def _oracle_source_hashes(episode_dir: Path) -> dict[str, str]:
    return {
        "scenario_sha256": sha256_file(episode_dir / "scenario.json"),
        "anonymous_detections_sha256": sha256_file(
            episode_dir / "online/anonymous_detections.csv"
        ),
        "camera_scan_sha256": sha256_file(
            episode_dir / "online/camera_scan.csv"
        ),
        "offline_detection_truth_sha256": sha256_file(
            episode_dir / "truth/detection_truth.csv"
        ),
    }


def _run_oracle_geometry(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    target_count = int(task["target_count"])
    seed = int(task["seed"])
    freeze_path = Path(str(task["route_freeze"])).resolve()
    (
        protocol,
        tracker_config,
        camera_ids,
        positions,
        camera,
        oracle_tracks,
        truth_by_track,
        diagnostics,
        episode_dir,
    ) = _oracle_context(target_count=target_count, seed=seed)
    source_hashes = _oracle_source_hashes(episode_dir)
    route = _load_route(
        "epipolar_mht", freeze_path, diagnostic_lightweight=False
    )
    associator = _WhitelistTemporalAssociator(route.parameters)
    rows: list[dict[str, Any]] = []
    for revolution in range(1, protocol.association_round_count + 1):
        snapshot = _oracle_snapshot(
            protocol=protocol,
            tracker_config=tracker_config,
            target_count=target_count,
            seed=seed,
            revolution=revolution,
            camera_ids=camera_ids,
            positions=positions,
            camera=camera,
            oracle_tracks=oracle_tracks,
            diagnostics=diagnostics,
            source_hashes=source_hashes,
        )
        labels = _oracle_labels(snapshot, truth_by_track)
        started = time.perf_counter()
        result = associator.process_snapshot(
            _to_internal_snapshot(snapshot), snapshot.geometry_candidate_pairs
        )
        measured_ms = (time.perf_counter() - started) * 1000.0
        latency_ms = max(float(result.processing_elapsed_ms), measured_ms)
        fingerprint = snapshot_fingerprint(snapshot)
        rows.append(
            _base_result_row(
                profile="oracle_360",
                target_count=target_count,
                seed=seed,
                condition="clean",
                route_name="epipolar_mht",
                snapshot=snapshot,
                labels=labels,
                matches=result.confirmed_matches,
                latency_ms=latency_ms,
                source_input_fingerprint=fingerprint,
                inference_input_fingerprint=fingerprint,
                route_freeze=freeze_path,
                protocol_bridge_applied=False,
                evidence_status="offline_oracle_diagnostic",
            )
        )
    return rows


def _run_oracle_gnn(tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    from dual_optical_100target_gnn.online import OnlineGNNAssociator

    rows: list[dict[str, Any]] = []
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[int(task["target_count"])].append(task)
    for target_count, group in sorted(grouped.items()):
        freeze_path = Path(str(group[0]["route_freeze"])).resolve()
        freeze = _read_json(freeze_path)
        expected_protocol = str(freeze["protocol_fingerprint_sha256"])
        associator = OnlineGNNAssociator(str(freeze_path))
        for task in sorted(group, key=lambda value: int(value["seed"])):
            seed = int(task["seed"])
            (
                protocol,
                tracker_config,
                camera_ids,
                positions,
                camera,
                oracle_tracks,
                truth_by_track,
                diagnostics,
                episode_dir,
            ) = _oracle_context(target_count=target_count, seed=seed)
            source_hashes = _oracle_source_hashes(episode_dir)
            for revolution in range(1, protocol.association_round_count + 1):
                snapshot = _oracle_snapshot(
                    protocol=protocol,
                    tracker_config=tracker_config,
                    target_count=target_count,
                    seed=seed,
                    revolution=revolution,
                    camera_ids=camera_ids,
                    positions=positions,
                    camera=camera,
                    oracle_tracks=oracle_tracks,
                    diagnostics=diagnostics,
                    source_hashes=source_hashes,
                )
                labels = _oracle_labels(snapshot, truth_by_track)
                protocol_bridge = snapshot.protocol_fingerprint != expected_protocol
                inference_snapshot = (
                    replace(snapshot, protocol_fingerprint=expected_protocol)
                    if protocol_bridge
                    else snapshot
                )
                started = time.perf_counter()
                result = associator.associate(inference_snapshot)
                measured_ms = (time.perf_counter() - started) * 1000.0
                latency_ms = max(
                    float(result.publication.end_to_end_ms), measured_ms
                )
                fingerprint = snapshot_fingerprint(snapshot)
                rows.append(
                    _base_result_row(
                        profile="oracle_360",
                        target_count=target_count,
                        seed=seed,
                        condition="clean",
                        route_name="gnn",
                        snapshot=snapshot,
                        labels=labels,
                        matches=result.confirmed_matches,
                        latency_ms=latency_ms,
                        source_input_fingerprint=fingerprint,
                        inference_input_fingerprint=snapshot_fingerprint(
                            inference_snapshot
                        ),
                        route_freeze=freeze_path,
                        protocol_bridge_applied=protocol_bridge,
                        evidence_status="offline_oracle_diagnostic",
                    )
                )
        print(
            f"oracle GNN complete: target_count={target_count}, sequences={len(group)}",
            flush=True,
        )
    return rows


def _derived_s180_protocol(target_count: int) -> Any:
    source_manifest = _read_json(
        _s180_target_root(target_count) / "dataset/test_manifest.json"
    )
    source = benchmark_protocol_from_mapping(source_manifest["protocol"])
    return replace(source, corruption_levels=CORRUPTION_LEVELS)


def _materialize_s180_episode(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    target_count = int(task["target_count"])
    seed = int(task["seed"])
    source_root = _s180_target_root(target_count)
    tracker_path = source_root / "dataset/freezes/shared_tracker.json"
    _, tracker_config = load_tracker_freeze(tracker_path)
    protocol = _derived_s180_protocol(target_count)
    episode_dir = (
        source_root / "raw/test" / f"airsim_seed_{seed}_online{target_count}"
    )
    return materialize_episode(
        episode_dir,
        Path(str(task["dataset_root"])),
        protocol,
        tracker_config=tracker_config,
    )


def _materialize_s180_campaign(
    output_root: Path, workers: int
) -> dict[int, Path]:
    manifests: dict[int, Path] = {}
    for target_count in TARGET_COUNTS:
        source_manifest = _read_json(
            _s180_target_root(target_count) / "dataset/test_manifest.json"
        )
        protocol = _derived_s180_protocol(target_count)
        dataset_root = (
            output_root
            / "s180_derived"
            / f"targets_{target_count:03d}"
            / "dataset"
        )
        tasks = [
            {
                "target_count": target_count,
                "seed": int(seed),
                "dataset_root": str(dataset_root),
            }
            for seed in protocol.test_seeds
        ]
        entries: list[dict[str, Any]] = []
        with ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
            futures = {
                executor.submit(_materialize_s180_episode, task): task
                for task in tasks
            }
            for future in as_completed(futures):
                entries.extend(future.result())
        manifest_path = write_dataset_manifest(
            dataset_root,
            entries,
            protocol,
            phase="test",
            tracker_freeze=source_manifest["tracker_freeze"],
        )
        manifests[target_count] = manifest_path
        print(
            f"S180 derived dataset complete: target_count={target_count}, "
            f"entries={len(entries)}",
            flush=True,
        )
    return manifests


def _parallel_rows(
    function: Any,
    tasks: Sequence[Mapping[str, Any]],
    *,
    workers: int,
    label: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    completed = 0
    with ProcessPoolExecutor(max_workers=min(workers, len(tasks))) as executor:
        futures = {executor.submit(function, task): task for task in tasks}
        for future in as_completed(futures):
            rows.extend(future.result())
            completed += 1
            if completed % 5 == 0 or completed == len(tasks):
                print(
                    f"{label}: {completed}/{len(tasks)} sequences complete",
                    flush=True,
                )
    return rows


def _actual_tasks(
    *,
    profile: str,
    manifests: Mapping[int, Path] | None = None,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for target_count in TARGET_COUNTS:
        if profile == "continuous_360":
            manifest_path = (
                _continuous_target_root(target_count) / "dataset/test_manifest.json"
            )
            conditions = CORRUPTION_LEVELS
            status = (
                "offline_replay_diagnostic"
                if target_count > 20
                else "offline_replay"
            )
        elif profile == "s180":
            if manifests is None:
                raise ValueError("S180 tasks require derived manifests")
            manifest_path = manifests[target_count]
            conditions = CORRUPTION_LEVELS
            status = "offline_interference_replay_diagnostic"
        else:
            raise ValueError(f"unsupported actual profile: {profile}")
        manifest = _read_json(manifest_path)
        for seed in manifest["protocol"]["test_seeds"]:
            for condition in conditions:
                tasks.append(
                    {
                        "profile": profile,
                        "target_count": target_count,
                        "seed": int(seed),
                        "condition": condition,
                        "manifest_path": str(manifest_path),
                        "route_freeze": str(
                            _route_freeze(profile, target_count, "epipolar_mht")
                        ),
                        "evidence_status": status,
                    }
                )
    return tasks


def _gnn_tasks(geometry_tasks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **dict(task),
            "route_freeze": str(
                _route_freeze(
                    str(task["profile"]), int(task["target_count"]), "gnn"
                )
            ),
        }
        for task in geometry_tasks
    ]


def _oracle_tasks(route_name: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for target_count in TARGET_COUNTS:
        manifest = _read_json(
            _continuous_target_root(target_count) / "dataset/test_manifest.json"
        )
        for seed in manifest["protocol"]["test_seeds"]:
            tasks.append(
                {
                    "target_count": target_count,
                    "seed": int(seed),
                    "route_freeze": str(
                        _route_freeze("oracle_360", target_count, route_name)
                    ),
                }
            )
    return tasks


def _final_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    final_by_sequence: dict[tuple[str, int, int, str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (
            str(row["profile"]),
            int(row["target_count"]),
            int(row["seed"]),
            str(row["condition"]),
            str(row["route_name"]),
        )
        previous = final_by_sequence.get(key)
        if previous is None or int(row["round_index"]) > int(previous["round_index"]):
            final_by_sequence[key] = row
    return [dict(final_by_sequence[key]) for key in sorted(final_by_sequence)]


def _summarize(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    final = _final_rows(rows)
    groups: dict[tuple[str, int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in final:
        groups[
            (
                str(row["profile"]),
                int(row["target_count"]),
                str(row["condition"]),
                str(row["route_name"]),
            )
        ].append(row)
    summary: list[dict[str, Any]] = []
    for (profile, target_count, condition, route_name), group in sorted(groups.items()):
        output_count = sum(int(row["output_match_count"]) for row in group)
        correct_count = sum(int(row["correct_match_count"]) for row in group)
        correct_unique = sum(
            int(row["correct_unique_target_count"]) for row in group
        )
        on_time_correct = sum(
            int(row["on_time_correct_unique_target_count"]) for row in group
        )
        target_denominator = target_count * len(group)
        dominant = sum(
            int(row["single_station_dominant_observation_count"])
            for row in group
        )
        labeled = sum(
            int(row["single_station_labeled_observation_count"])
            for row in group
        )
        single_correct = sum(
            int(row["single_station_correct_identity_count"]) for row in group
        )
        single_opportunities = sum(
            int(row["single_station_identity_opportunity_count"])
            for row in group
        )
        summary.append(
            {
                "profile": profile,
                "target_count": target_count,
                "condition": condition,
                "route_name": route_name,
                "sample_count": len(group),
                "seeds": sorted(int(row["seed"]) for row in group),
                "offline_completed_precision": (
                    correct_count / output_count if output_count else None
                ),
                "offline_completed_coverage": correct_unique
                / max(target_denominator, 1),
                "on_time_coverage": on_time_correct / max(target_denominator, 1),
                "latency_p95_ms": _percentile_nearest_rank(
                    [float(row["latency_ms"]) for row in group], 0.95
                ),
                "timeout_count": sum(bool(row["timed_out"]) for row in group),
                "single_station_precision": dominant / max(labeled, 1),
                "single_station_coverage": single_correct
                / max(single_opportunities, 1),
                "single_station_duplicate_track_count": sum(
                    int(row["single_station_duplicate_track_count"])
                    for row in group
                ),
                "single_station_mixed_track_count": sum(
                    int(row["single_station_mixed_track_count"]) for row in group
                ),
                "single_station_missing_identity_count": sum(
                    int(row["single_station_identity_opportunity_count"])
                    - int(row["single_station_correct_identity_count"])
                    for row in group
                ),
                "dual_station_residual_loss_count": sum(
                    int(row["dual_station_residual_loss_count"]) for row in group
                ),
                "output_match_count": output_count,
                "correct_match_count": correct_count,
                "evidence_statuses": sorted(
                    {str(row["evidence_status"]) for row in group}
                ),
                "protocol_bridge_applied": any(
                    bool(row["protocol_bridge_applied"]) for row in group
                ),
            }
        )
    return summary


def _correlations(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    final = _final_rows(rows)
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in final:
        if str(row["profile"]) == "oracle_360":
            continue
        groups[(str(row["profile"]), str(row["route_name"]))].append(row)
    result: list[dict[str, Any]] = []
    for (profile, route_name), group in sorted(groups.items()):
        local_coverage = np.asarray(
            [float(row["single_station_coverage"]) for row in group], dtype=float
        )
        local_precision = np.asarray(
            [float(row["single_station_precision"]) for row in group], dtype=float
        )
        dual_coverage = np.asarray(
            [float(row["fixed_target_coverage"]) for row in group], dtype=float
        )

        def correlation(left: np.ndarray, right: np.ndarray) -> float | None:
            if len(left) < 2 or np.std(left) <= 1.0e-12 or np.std(right) <= 1.0e-12:
                return None
            return float(np.corrcoef(left, right)[0, 1])

        result.append(
            {
                "profile": profile,
                "route_name": route_name,
                "case_count": len(group),
                "single_station_coverage_vs_dual_coverage_pearson": correlation(
                    local_coverage, dual_coverage
                ),
                "single_station_precision_vs_dual_coverage_pearson": correlation(
                    local_precision, dual_coverage
                ),
            }
        )
    return result


def _validate_matrix(summary: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    keys = {
        (
            str(row["profile"]),
            int(row["target_count"]),
            str(row["condition"]),
            str(row["route_name"]),
        ): row
        for row in summary
    }
    expected: set[tuple[str, int, str, str]] = set()
    for target_count in TARGET_COUNTS:
        for route_name in ROUTES:
            expected.add(("oracle_360", target_count, "clean", route_name))
            for condition in CORRUPTION_LEVELS:
                expected.add(
                    ("continuous_360", target_count, condition, route_name)
                )
                expected.add(("s180", target_count, condition, route_name))
    missing = sorted(expected - set(keys))
    unexpected = sorted(set(keys) - expected)
    wrong_samples = sorted(
        (key, int(keys[key]["sample_count"]))
        for key in expected & set(keys)
        if int(keys[key]["sample_count"]) != 5
    )
    if missing or unexpected or wrong_samples:
        raise RuntimeError(
            "matrix incomplete: "
            f"missing={missing}, unexpected={unexpected}, wrong_samples={wrong_samples}"
        )
    return {
        "oracle_360_group_count": 6,
        "continuous_360_group_count": 24,
        "s180_group_count": 24,
        "total_group_count": len(expected),
        "seed_count_per_group": 5,
        "complete": True,
    }


def _source_inputs(output_root: Path) -> list[dict[str, str]]:
    inputs: list[dict[str, str]] = []
    seen: set[Path] = set()

    def append(role: str, path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        try:
            stored = resolved.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            stored = str(resolved)
        inputs.append({"role": role, "path": stored, "sha256": sha256_file(resolved)})

    for target_count in TARGET_COUNTS:
        for source_root in (
            _continuous_target_root(target_count),
            _s180_target_root(target_count),
        ):
            manifest = source_root / "dataset/test_manifest.json"
            append("source_test_manifest", manifest)
            values = _read_json(manifest)
            append("source_tracker_freeze", Path(str(values["tracker_freeze"])))
        for profile in ("continuous_360", "s180"):
            for route_name in ROUTES:
                append(
                    f"{profile}_{route_name}_freeze",
                    _route_freeze(profile, target_count, route_name),
                )
        continuous_manifest = _read_json(
            _continuous_target_root(target_count) / "dataset/test_manifest.json"
        )
        for seed in continuous_manifest["protocol"]["test_seeds"]:
            episode = (
                _continuous_target_root(target_count)
                / "raw/test"
                / f"airsim_seed_{seed}_online{target_count}"
            )
            append("oracle_source_scenario", episode / "scenario.json")
            append(
                "oracle_source_anonymous_detections",
                episode / "online/anonymous_detections.csv",
            )
            append("oracle_source_camera_scan", episode / "online/camera_scan.csv")
            append(
                "oracle_offline_detection_truth",
                episode / "truth/detection_truth.csv",
            )
        s180_manifest = _read_json(
            _s180_target_root(target_count) / "dataset/test_manifest.json"
        )
        for seed in s180_manifest["protocol"]["test_seeds"]:
            episode = (
                _s180_target_root(target_count)
                / "raw/test"
                / f"airsim_seed_{seed}_online{target_count}"
            )
            append("s180_source_scenario", episode / "scenario.json")
            append(
                "s180_source_anonymous_detections",
                episode / "online/anonymous_detections.csv",
            )
            append("s180_source_camera_scan", episode / "online/camera_scan.csv")
            append(
                "s180_offline_detection_truth",
                episode / "truth/detection_truth.csv",
            )
    for path in (
        Path(__file__),
        PACKAGE_ROOT / "contracts.py",
        PACKAGE_ROOT / "dataset.py",
        PACKAGE_ROOT / "tracking.py",
        PACKAGE_ROOT / "s180_oracle_geometry_offline.py",
    ):
        append("source_file", path)
    append("derived_s180_combined_summary", output_root / "combined_summary.json")
    return inputs


def _git_provenance() -> dict[str, Any]:
    def run(*arguments: str) -> str:
        completed = subprocess.run(
            ("git", *arguments),
            cwd=REPO_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()

    status = run("status", "--short")
    return {
        "git_commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(status),
        "git_status_short_sha256": hashlib.sha256(status.encode("utf-8")).hexdigest(),
    }


def _dependency_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in ("numpy", "scipy", "torch"):
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = "unavailable"
    return result


def _write_reproduction_manifest(
    output_root: Path,
    *,
    workers: int,
    matrix: Mapping[str, Any],
) -> None:
    command = [
        "python3",
        "-m",
        "dual_optical_online_benchmark.report_matrix_replay",
        "--output-dir",
        str(output_root),
        "--workers",
        str(workers),
    ]
    write_json(
        output_root / "reproduction_manifest.json",
        {
            "schema_version": "msm-experiment-reproduction-v1",
            "experiment_id": output_root.name,
            "status": "diagnostic_offline_replay",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "question": (
                "最后一圈条件下，单站航迹质量、双站配准质量和一秒时限之间的关系"
            ),
            "source": {
                **_git_provenance(),
                "entry_point": "dual_optical_online_benchmark.report_matrix_replay",
                "cwd": str(REPO_ROOT),
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
                "worker_count": workers,
            },
            "scenario": {
                "target_counts": list(TARGET_COUNTS),
                "corruption_levels": list(CORRUPTION_LEVELS),
                "routes": list(ROUTES),
                "deadline_ms": DEADLINE_MS,
                "matrix": dict(matrix),
                "final_window_only_in_summary": True,
            },
            "inputs": _source_inputs(output_root),
            "outputs": {
                "metrics": [
                    "oracle_360/round_metrics.csv",
                    "continuous_360/round_metrics.csv",
                    "s180_derived/round_metrics.csv",
                    "combined_final_case_metrics.csv",
                    "combined_summary.json",
                ],
                "configs": ["campaign_config.json", "matrix_completeness.json"],
                "reports": [],
            },
            "metrics_contract": {
                "precision": "correct confirmed relations / all confirmed relations",
                "coverage": "unique correctly confirmed targets / fixed target count",
                "single_station_precision": (
                    "dominant real observations / all labeled observations at both stations"
                ),
                "single_station_coverage": (
                    "unique identity-correct local tracks / (2 * fixed target count)"
                ),
                "timeout_policy": (
                    "quality retained after 1000 ms; late result contributes zero to on-time coverage"
                ),
                "local_track_purity_threshold": LOCAL_TRACK_PURITY_THRESHOLD,
            },
            "reproduction": {
                "offline_replay_command": " ".join(command),
                "full_airsim_rerun_command": None,
                "quality_metrics_deterministic": True,
                "latency_nondeterministic": True,
                "known_limits": [
                    "360-degree 40/60-target geometry uses a pre-existing cross-scale diagnostic freeze",
                    "S180 medium/heavy cases are deterministic offline corruption replays, not AirSim reruns",
                    "legacy 360-degree oracle construction adds current default fields to the preserved tracker config",
                ],
            },
        },
    )


def run_campaign(output_root: Path, *, workers: int) -> Path:
    if output_root.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {output_root}")
    output_root.mkdir(parents=True)
    config = {
        "schema_version": SCHEMA_VERSION,
        "run_id": output_root.name,
        "target_counts": list(TARGET_COUNTS),
        "routes": list(ROUTES),
        "corruption_levels": list(CORRUPTION_LEVELS),
        "deadline_ms": DEADLINE_MS,
        "local_track_purity_threshold": LOCAL_TRACK_PURITY_THRESHOLD,
        "summary_window": "last_revolution_or_last_round",
        "continuous_360_final_round": 6,
        "s180_final_round": 12,
        "oracle_360_condition": "clean",
        "s180_medium_heavy_generation": (
            "deterministic corruption of preserved anonymous observations using CORRUPTION_POLICY"
        ),
    }
    write_json(output_root / "campaign_config.json", config)

    s180_manifests = _materialize_s180_campaign(output_root, workers)

    oracle_geometry_tasks = _oracle_tasks("epipolar_mht")
    oracle_geometry = _parallel_rows(
        _run_oracle_geometry,
        oracle_geometry_tasks,
        workers=workers,
        label="oracle geometry",
    )
    oracle_gnn = _run_oracle_gnn(_oracle_tasks("gnn"))
    oracle_rows = oracle_geometry + oracle_gnn
    _write_csv(output_root / "oracle_360/round_metrics.csv", oracle_rows)

    continuous_geometry_tasks = _actual_tasks(profile="continuous_360")
    continuous_geometry = _parallel_rows(
        _run_geometry_sequence,
        continuous_geometry_tasks,
        workers=workers,
        label="continuous geometry",
    )
    continuous_gnn = _run_gnn_sequences(_gnn_tasks(continuous_geometry_tasks))
    continuous_rows = continuous_geometry + continuous_gnn
    _write_csv(
        output_root / "continuous_360/round_metrics.csv", continuous_rows
    )

    s180_geometry_tasks = _actual_tasks(
        profile="s180", manifests=s180_manifests
    )
    s180_geometry = _parallel_rows(
        _run_geometry_sequence,
        s180_geometry_tasks,
        workers=workers,
        label="S180 geometry",
    )
    s180_gnn = _run_gnn_sequences(_gnn_tasks(s180_geometry_tasks))
    s180_rows = s180_geometry + s180_gnn
    _write_csv(output_root / "s180_derived/round_metrics.csv", s180_rows)

    all_rows = oracle_rows + continuous_rows + s180_rows
    final_rows = _final_rows(all_rows)
    summary = _summarize(all_rows)
    correlations = _correlations(all_rows)
    matrix = _validate_matrix(summary)
    _write_csv(output_root / "combined_final_case_metrics.csv", final_rows)
    write_json(
        output_root / "combined_summary.json",
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": output_root.name,
            "summary_window": "last_revolution_or_last_round",
            "deadline_ms": DEADLINE_MS,
            "coverage_denominator": "fixed_target_count",
            "truth_used_online": False,
            "offline_truth_used_for_oracle_construction_and_scoring_only": True,
            "summary": summary,
            "correlations": correlations,
            "matrix": matrix,
        },
    )
    write_json(output_root / "matrix_completeness.json", matrix)
    _write_reproduction_manifest(output_root, workers=workers, matrix=matrix)
    print(f"campaign complete: {output_root}", flush=True)
    return output_root / "combined_summary.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUTS_ROOT / RUN_ID,
    )
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    result = run_campaign(args.output_dir.resolve(), workers=args.workers)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
