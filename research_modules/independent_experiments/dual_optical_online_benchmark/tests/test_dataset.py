from __future__ import annotations

import csv
import json
import math

import pytest

from dual_optical_40target.core import CameraSpec, scan_yaw_deg, sweep_index
from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    SnapshotTrack,
    SnapshotTrackSample,
    benchmark_protocol_for_target_count,
    s180_protocol_for_target_count,
    read_snapshot,
)
from dual_optical_online_benchmark.dataset import (
    CORRUPTION_POLICY,
    build_shared_candidate_graph,
    materialize_episode,
    split_for_seed,
)
from dual_optical_online_benchmark.episode_worker import build_config
from dual_optical_online_benchmark.scoring import aggregate_rows
from dual_optical_online_benchmark.v5 import v5_protocol_for_target_count


def test_corruption_policy_is_frozen() -> None:
    assert CORRUPTION_POLICY["clean"] == {
        "miss_probability": 0.0,
        "transient_false_per_camera_second": 0.0,
        "persistent_false_per_camera": 0,
    }
    assert CORRUPTION_POLICY["light"] == {
        "miss_probability": 0.03,
        "transient_false_per_camera_second": 2.0,
        "persistent_false_per_camera": 0,
    }
    assert CORRUPTION_POLICY["heavy"]["persistent_false_per_camera"] == 2


def test_worker_config_matches_formal_protocol() -> None:
    protocol = BenchmarkProtocol()
    config = build_config(protocol.train_seeds[0], 41451)
    assert config.target_count == 100
    assert config.scan_mode == "continuous_360"
    assert config.scan_period_s == 2.0
    assert config.target_motion_profile == "split_0_minus30"
    assert config.gimbal_pose_error_enabled
    assert config.clock_speed == 0.1


def test_worker_config_accepts_each_target_tier() -> None:
    for target_count in (20, 40, 60, 100):
        protocol = benchmark_protocol_for_target_count(target_count)
        config = build_config(
            protocol.train_seeds[0], 41451, protocol=protocol
        )
        assert config.target_count == target_count


def test_shared_candidate_graph_is_symmetric_bounded_and_anonymous() -> None:
    def track(camera: str, index: int, azimuth: float) -> SnapshotTrack:
        import math

        direction = (
            math.cos(math.radians(azimuth)),
            math.sin(math.radians(azimuth)),
            0.0,
        )
        sample = SnapshotTrackSample(
            1,
            3.0,
            direction,
            1,
            1.0,
            1.0,
            measurement_covariance_deg2=(0.001, 0.0, 0.0, 0.001),
            state_vector=(azimuth, 0.0, 0.0, 0.0),
            state_covariance=tuple(
                0.001 if row == column else 0.0
                for row in range(4)
                for column in range(4)
            ),
        )
        return SnapshotTrack(
            f"{camera}-{index}", camera, (sample,), track_state="confirmed"
        )

    camera_ids = ("A", "B")
    tracks = {
        "A": tuple(track("A", index, 20.0 + index) for index in range(20)),
        "B": tuple(track("B", index, 20.0 + index) for index in range(20)),
    }
    pairs, summary, fingerprint = build_shared_candidate_graph(
        tracks=tracks,
        camera_ids=camera_ids,
        camera_positions_ned={"A": (0.0, -1000.0, 0.0), "B": (0.0, 1000.0, 0.0)},
        cutoff_timestamp=4.0,
        target_count=20,
    )
    assert len(pairs) <= 2 * 20 * int(summary["top_k_per_track"])
    assert summary["full_pair_count"] == 400
    assert summary["candidate_build_ms"] >= 0.0
    assert len(fingerprint) == 64
    assert all(left.startswith("A-") and right.startswith("B-") for left, right in pairs)


def test_shared_candidate_budget_prioritizes_mature_tracks_over_tentative_clutter() -> None:
    import math

    def track(
        camera: str, index: int, elevation: float, state: str
    ) -> SnapshotTrack:
        direction = (
            math.cos(math.radians(elevation)),
            0.0,
            -math.sin(math.radians(elevation)),
        )
        sample = SnapshotTrackSample(
            1,
            3.0,
            direction,
            1,
            1.0,
            1.0,
            measurement_covariance_deg2=(0.001, 0.0, 0.0, 0.001),
            state_vector=(0.0, elevation, 0.0, 0.0),
            state_covariance=tuple(
                0.001 if row == column else 0.0
                for row in range(4)
                for column in range(4)
            ),
        )
        return SnapshotTrack(
            f"{camera}-{index}", camera, (sample,), track_state=state
        )

    tracks_a = (track("A", 0, 0.0, "confirmed"),)
    # Eight tentative tracks have a lower residual than the mature track.  A
    # residual-only K=8 ranking would remove the mature candidate.
    tracks_b = tuple(
        track("B", index, 0.001 * index, "tentative")
        for index in range(8)
    ) + (track("B", 8, 0.02, "confirmed"),)
    pairs, summary, _ = build_shared_candidate_graph(
        tracks={"A": tracks_a, "B": tracks_b},
        camera_ids=("A", "B"),
        camera_positions_ned={
            "A": (0.0, -1000.0, 0.0),
            "B": (0.0, 1000.0, 0.0),
        },
        cutoff_timestamp=4.0,
        target_count=20,
    )
    assert ("A-0", "B-8") in pairs
    assert summary["top_k_per_track"] == 8
    assert summary["ranking_policy"] == (
        "mature_track_then_normalized_epipolar_residual"
    )


def test_dormant_tracks_do_not_enter_cross_station_candidate_graph() -> None:
    sample = SnapshotTrackSample(
        1,
        3.0,
        (1.0, 0.0, 0.0),
        1,
        1.0,
        1.0,
        state_covariance=tuple(
            0.001 if row == column else 0.0
            for row in range(4)
            for column in range(4)
        ),
    )
    tracks = {
        "A": (SnapshotTrack("A-dormant", "A", (sample,), track_state="dormant"),),
        "B": (SnapshotTrack("B-live", "B", (sample,), track_state="confirmed"),),
    }
    pairs, summary, _ = build_shared_candidate_graph(
        tracks=tracks,
        camera_ids=("A", "B"),
        camera_positions_ned={"A": (0.0, -1000.0, 0.0), "B": (0.0, 1000.0, 0.0)},
        cutoff_timestamp=4.0,
        target_count=20,
    )
    assert pairs == ()
    assert summary["left_track_count"] == 0


def test_split_for_seed_rejects_unreserved_seed() -> None:
    protocol = BenchmarkProtocol()
    assert split_for_seed(protocol, 20270101) == "train"
    assert split_for_seed(protocol, 20270125) == "validation"
    assert split_for_seed(protocol, 20270201) == "test"
    with pytest.raises(ValueError):
        split_for_seed(protocol, 1)


def _write_csv(path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _raw_fixture(
    root, seed: int, protocol: BenchmarkProtocol | None = None
) -> None:
    protocol = protocol or BenchmarkProtocol()
    config = build_config(seed, 41451, protocol=protocol)
    camera = CameraSpec()
    scenario = {
        "scenario": {
            **config.__dict__,
            "camera_a_position_ned": list(config.camera_a_position_ned),
            "camera_b_position_ned": list(config.camera_b_position_ned),
            "corridor_center_ned": list(config.corridor_center_ned),
        },
        "camera": {
            **camera.__dict__,
            "vertical_fov_deg": camera.vertical_fov_deg,
            "effective_ifov_mrad": camera.effective_ifov_mrad,
        },
        "target_specs_offline_truth_only": [
            {
                "truth_id": f"TRUTH-{index:03d}",
                "heading_offset_deg": (
                    0.0 if index <= protocol.zero_heading_count else -30.0
                ),
            }
            for index in range(1, protocol.target_count + 1)
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    (root / "metrics.json").write_text(
        json.dumps({
            "target_count": protocol.target_count,
            "spawned_target_count": protocol.target_count,
            "online_truth_leakage_count": 0,
        }) + "\n",
        encoding="utf-8",
    )
    scan_rows = []
    frame_count = int(round(protocol.duration_s * protocol.sample_rate_hz))
    frames_per_revolution = int(
        round(protocol.association_round_period_s * protocol.sample_rate_hz)
    )
    for frame_index in range(frame_count):
        timestamp = frame_index / protocol.sample_rate_hz
        for camera_id in (config.camera_a_name, config.camera_b_name):
            scan_timestamp = timestamp + (
                protocol.camera_b_scan_phase_offset_s
                if camera_id == config.camera_b_name
                else 0.0
            )
            scan_rows.append({
                "camera_id": camera_id,
                "frame_index": frame_index,
                "measurement_timestamp": timestamp,
                "sweep_index": sweep_index(
                    timestamp,
                    period_s=protocol.scan_period_s,
                    mode=protocol.scan_mode,
                ),
                "yaw_deg": scan_yaw_deg(
                    scan_timestamp,
                    0.0,
                    half_span_deg=protocol.scan_half_span_deg,
                    period_s=protocol.scan_period_s,
                    mode=protocol.scan_mode,
                ),
                "pitch_deg": 0.0,
                "detection_count": 0,
                "detection_rpc_latency_ms": 1.0,
            })
    _write_csv(root / "online/camera_scan.csv", list(scan_rows[0]), scan_rows)
    detections = []
    truth_rows = []
    for revolution in range(protocol.revolution_count):
        for camera_index, camera_id in enumerate((config.camera_a_name, config.camera_b_name)):
            frame_index = revolution * frames_per_revolution + 20 + camera_index
            uid = f"{camera_id}-F{frame_index:05d}-D000"
            detections.append({
                "detection_uid": uid,
                "camera_id": camera_id,
                "frame_index": frame_index,
                "measurement_timestamp": frame_index / protocol.sample_rate_hz,
                "arrival_timestamp": frame_index / protocol.sample_rate_hz + 0.001,
                "bbox_xyxy": "[630.0, 502.0, 650.0, 522.0]",
                "center_px": "[640.0, 512.0]",
                "confidence": 1.0,
            })
            truth_rows.append({
                "detection_uid": uid,
                "camera_id": camera_id,
                "frame_index": frame_index,
                "measurement_timestamp": frame_index / protocol.sample_rate_hz,
                "truth_id": "TRUTH-001",
                "raw_detection_name": "fixture_actor_name",
                "truth_assignment_pixel_error": 0.0,
                "relative_pose": "{}",
                "box3d": "{}",
                "offline_truth_only": True,
            })
    _write_csv(root / "online/anonymous_detections.csv", list(detections[0]), detections)
    _write_csv(root / "truth/detection_truth.csv", list(truth_rows[0]), truth_rows)
    manifest = {
        "artifacts": {
            "anonymous_detections": "online/anonymous_detections.csv",
            "camera_scan": "online/camera_scan.csv",
            "detection_truth": "truth/detection_truth.csv",
            "metrics": "metrics.json",
        }
    }
    (root / "record_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_materialization_produces_anonymous_six_revolution_snapshots(tmp_path) -> None:
    episode = tmp_path / "raw"
    dataset = tmp_path / "dataset"
    _raw_fixture(episode, 20270101)
    entries = materialize_episode(episode, dataset)
    assert len(entries) == 18
    assert {(item["corruption_level"], item["revolution_index"]) for item in entries} == {
        (level, revolution)
        for level in ("light", "medium", "heavy")
        for revolution in range(1, 7)
    }
    snapshot_path = dataset / entries[-1]["snapshot_path"]
    snapshot = read_snapshot(snapshot_path)
    assert all(
        track.source_kind == "anonymous"
        for camera_tracks in snapshot.tracks.values()
        for track in camera_tracks
    )
    online_text = snapshot_path.read_text(encoding="utf-8")
    assert "TRUTH-" not in online_text
    assert "fixture_actor_name" not in online_text
    assert "synthetic_false" not in online_text
    labels = json.loads((dataset / entries[-1]["label_path"]).read_text(encoding="utf-8"))
    assert labels["offline_truth_only"] is True
    assert labels["truth_heading_groups"]["TRUTH-001"] == "heading_0_deg"


def test_s180_materialization_produces_twelve_one_way_rounds(tmp_path) -> None:
    protocol = s180_protocol_for_target_count(20)
    episode = tmp_path / "raw_s180"
    dataset = tmp_path / "dataset_s180"
    _raw_fixture(episode, protocol.train_seeds[0], protocol)

    entries = materialize_episode(episode, dataset, protocol)

    assert len(entries) == 2 * 12
    assert {(item["corruption_level"], item["revolution_index"]) for item in entries} == {
        (level, round_index)
        for level in ("clean", "light")
        for round_index in range(1, 13)
    }
    final_snapshot = read_snapshot(dataset / entries[-1]["snapshot_path"])
    assert final_snapshot.association_round_period_s == 1.0
    assert final_snapshot.association_round_count == 12
    assert final_snapshot.cutoff_timestamp == 12.0


def test_s180_worker_uses_triangle_scan_and_one_second_tracker_period() -> None:
    protocol = s180_protocol_for_target_count(40)
    config = build_config(protocol.train_seeds[0], 41451, protocol=protocol)
    assert config.scan_mode == "triangle"
    assert config.scan_half_span_deg == 90.0
    assert config.scan_period_s == 2.0


def test_phase_180_materialization_keeps_both_cameras_on_global_revolutions(
    tmp_path,
) -> None:
    protocol = v5_protocol_for_target_count(100)
    episode = tmp_path / "raw_phase180"
    dataset = tmp_path / "dataset_phase180"
    _raw_fixture(episode, protocol.train_seeds[0], protocol)

    entries = materialize_episode(episode, dataset, protocol)

    assert len(entries) == (
        len(protocol.corruption_levels) * protocol.revolution_count
    )
    for entry in entries:
        snapshot = read_snapshot(dataset / entry["snapshot_path"])
        for camera_id in snapshot.camera_ids:
            for track in snapshot.tracks[camera_id]:
                for sample in track.samples:
                    assert sample.sweep_index == min(
                        int(sample.timestamp // protocol.scan_period_s),
                        protocol.revolution_count - 1,
                    )

    with (episode / "online/camera_scan.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    by_key = {
        (row["camera_id"], int(row["frame_index"])): row for row in rows
    }
    for timestamp, frame_index, expected_sweep in (
        (0.0, 0, 0),
        (1.0, 100, 0),
        (2.0, 200, 1),
    ):
        row_a = by_key[("Optical_A", frame_index)]
        row_b = by_key[("Optical_B", frame_index)]
        assert int(row_a["sweep_index"]) == expected_sweep
        assert int(row_b["sweep_index"]) == expected_sweep
        yaw_difference = (
            float(row_b["yaw_deg"]) - float(row_a["yaw_deg"])
        ) % 360.0
        assert math.isclose(yaw_difference, 180.0, abs_tol=1e-9)
        assert math.isclose(
            float(row_a["measurement_timestamp"]), timestamp, abs_tol=1e-9
        )


def test_gpu_available_status_counts_as_available() -> None:
    row = {
        "route_name": "gnn",
        "availability": "available_gpu",
        "deadline_met": True,
        "precision": 0.5,
        "recall": 0.25,
        "f1": 1.0 / 3.0,
        "false_association_count": 1,
        "duplicate_identity_match_count": 0,
        "end_to_end_ms": 4.0,
    }
    assert aggregate_rows([row])["routes"]["gnn"]["availability_rate"] == 1.0
