from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import errno
import json
import math

import pytest

from dual_optical_online_benchmark.candidate_gate_ablation import (
    derive_candidate_manifest,
)
from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    candidate_gate_policy,
    candidate_graph_fingerprint,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from dual_optical_online_benchmark.dataset import (
    build_shared_candidate_graph,
    sha256_file,
)


CAMERA_POSITIONS = {"A": (0.0, -1000.0, 0.0), "B": (0.0, 1000.0, 0.0)}


def _track(camera_id: str, index: int, elevation_deg: float) -> SnapshotTrack:
    elevation = math.radians(elevation_deg)
    sample = SnapshotTrackSample(
        sweep_index=1,
        timestamp=1.0,
        direction_ned=(math.cos(elevation), 0.0, -math.sin(elevation)),
        detection_count=1,
        bbox_area_px2=1.0,
        confidence=1.0,
        measurement_covariance_deg2=(0.001, 0.0, 0.0, 0.001),
        state_vector=(0.0, elevation_deg, 0.0, 0.0),
        state_covariance=tuple(
            0.001 if row == column else 0.0
            for row in range(4)
            for column in range(4)
        ),
    )
    return SnapshotTrack(
        track_id=f"{camera_id}-{index:02d}",
        camera_id=camera_id,
        samples=(sample,),
        track_state="confirmed",
        recent_sweep_hits=(True, True, True),
    )


def _build(
    tracks: dict[str, tuple[SnapshotTrack, ...]], strategy_name: str | None
) -> tuple[tuple[tuple[str, str], ...], dict[str, int | float | str], str]:
    return build_shared_candidate_graph(
        tracks=tracks,
        camera_ids=("A", "B"),
        camera_positions_ned=CAMERA_POSITIONS,
        cutoff_timestamp=2.0,
        target_count=20,
        candidate_gate_policy=(
            None if strategy_name is None else candidate_gate_policy(strategy_name)
        ),
    )


def test_default_candidate_graph_remains_legacy_compatible() -> None:
    tracks = {
        "A": (_track("A", 0, 0.0), _track("A", 1, 0.1)),
        "B": (_track("B", 0, 0.0), _track("B", 1, 0.1)),
    }
    pairs, summary, fingerprint = _build(tracks, None)
    assert pairs == (
        ("A-00", "B-00"),
        ("A-00", "B-01"),
        ("A-01", "B-00"),
        ("A-01", "B-01"),
    )
    assert summary["normalized_gate_sigma"] == 8.0
    assert summary["top_k_per_track"] == 8
    assert "candidate_gate_strategy" not in summary
    assert fingerprint == "3661bb831eebb83b2113df114ed9f06fdb3696980a0eb048159577e0e4d818c6"


def test_wider_gate_and_top_k_monotonically_include_candidates() -> None:
    tracks = {
        "A": tuple(_track("A", index, 0.0) for index in range(20)),
        "B": tuple(_track("B", index, index * 0.075) for index in range(20)),
    }
    baseline_pairs, baseline_summary, baseline_fingerprint = _build(
        tracks, "baseline"
    )
    moderate_pairs, moderate_summary, moderate_fingerprint = _build(
        tracks, "moderate"
    )
    wide_pairs, wide_summary, wide_fingerprint = _build(tracks, "wide")

    assert set(baseline_pairs) < set(moderate_pairs) < set(wide_pairs)
    assert baseline_summary["top_k_per_track"] == 8
    assert moderate_summary["top_k_per_track"] == 12
    assert wide_summary["top_k_per_track"] == 16
    assert baseline_summary["normalized_gate_sigma"] == 8.0
    assert moderate_summary["normalized_gate_sigma"] == 10.0
    assert wide_summary["normalized_gate_sigma"] == 12.0
    assert len({baseline_fingerprint, moderate_fingerprint, wide_fingerprint}) == 3
    assert baseline_summary["candidate_gate_strategy"] == "baseline"
    assert "truth" not in json.dumps(baseline_summary).lower()


def test_policy_fingerprint_distinguishes_same_candidate_pairs() -> None:
    tracks = {"A": (_track("A", 0, 0.0),), "B": (_track("B", 0, 0.0),)}
    outputs = [_build(tracks, name) for name in ("baseline", "moderate", "wide")]
    assert len({pairs for pairs, _, _ in outputs}) == 1
    assert len({fingerprint for _, _, fingerprint in outputs}) == 3
    assert len(
        {
            str(summary["candidate_gate_config_fingerprint"])
            for _, summary, _ in outputs
        }
    ) == 3


def _source_manifest(
    root: Path, *, phase: str = "test"
) -> tuple[Path, Path, Path]:
    split = "test" if phase == "test" else "train"
    tracks = {"A": (_track("A", 0, 0.0),), "B": (_track("B", 0, 0.0),)}
    pairs, summary, fingerprint = _build(tracks, None)
    snapshot = RevolutionSnapshot(
        protocol_fingerprint="protocol-test",
        seed=101,
        split=split,
        corruption_level="light",
        revolution_index=1,
        cutoff_timestamp=2.0,
        camera_ids=("A", "B"),
        camera_positions_ned=CAMERA_POSITIONS,
        focal_length_px=1000.0,
        tracks=tracks,
        target_count=20,
        tracker_fingerprint="tracker-test",
        geometry_candidate_pairs=pairs,
        candidate_graph_fingerprint=fingerprint,
        candidate_graph_summary=summary,
    )
    snapshot_relative = Path(
        f"snapshots/{split}/101/light/revolution_01.json"
    )
    label_relative = Path(f"labels/{split}/101/light/revolution_01.json")
    snapshot_path = root / snapshot_relative
    label_path = root / label_relative
    write_snapshot(snapshot_path, snapshot)
    write_json(label_path, {"offline_truth_only": True, "track_truth_counts": {}})
    manifest = {
        "schema_version": "dual-optical-online-dataset-v2",
        "phase": phase,
        "protocol": {"target_count": 20},
        "protocol_fingerprint": "protocol-test",
        "test_access_allowed": phase == "test",
        "tracker_fingerprint": "tracker-test",
        "tracker_freeze": None,
        "tracker_freeze_sha256": None,
        "entries": [
            {
                "split": split,
                "seed": 101,
                "corruption_level": "light",
                "revolution_index": 1,
                "snapshot_path": snapshot_relative.as_posix(),
                "snapshot_sha256": sha256_file(snapshot_path),
                "input_fingerprint": snapshot_fingerprint(snapshot),
                "label_path": label_relative.as_posix(),
                "label_sha256": sha256_file(label_path),
                "tracker_fingerprint": "tracker-test",
            }
        ],
    }
    manifest_path = root / f"{phase}_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path, snapshot_path, label_path


@pytest.mark.parametrize("phase", ("calibration", "test"))
def test_derived_manifest_hard_links_labels_inside_root_without_reading(
    tmp_path: Path,
    phase: str,
) -> None:
    source_root = tmp_path / f"source-{phase}"
    manifest_path, snapshot_path, label_path = _source_manifest(
        source_root, phase=phase
    )
    source_hashes = {
        path: sha256_file(path) for path in (manifest_path, snapshot_path, label_path)
    }
    original_open = Path.open

    def guarded_open(path: Path, *args: object, **kwargs: object):
        if path == label_path:
            raise AssertionError("test label content was opened during derivation")
        return original_open(path, *args, **kwargs)

    output_root = tmp_path / f"derived-wide-{phase}"
    with patch.object(Path, "open", guarded_open):
        derived_manifest_path = derive_candidate_manifest(
            manifest_path, output_root, "wide"
        )

    assert {path: sha256_file(path) for path in source_hashes} == source_hashes
    payload = json.loads(derived_manifest_path.read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    derived_snapshot = read_snapshot(output_root / entry["snapshot_path"])
    derived_label = output_root / entry["label_path"]
    from dual_optical_100target_gnn.online_benchmark import _safe_path

    safe_label = _safe_path(output_root, entry["label_path"])
    assert payload["candidate_gate_ablation"]["strategy"] == "wide"
    assert payload["candidate_gate_ablation"][
        "truth_labels_read_during_derivation"
    ] is False
    assert payload["candidate_gate_ablation"][
        "calibration_labels_read_during_derivation"
    ] is False
    assert payload["candidate_gate_ablation"][
        "test_labels_read_during_derivation"
    ] is False
    assert payload["candidate_gate_ablation"]["label_materialization"] == (
        "same_filesystem_hard_link_no_read"
    )
    assert entry["label_path"] == (
        f"labels/{'test' if phase == 'test' else 'train'}/101/light/"
        "revolution_01.json"
    )
    assert entry["label_sha256"] == source_hashes[label_path]
    assert safe_label == derived_label.resolve()
    safe_label.relative_to(output_root.resolve())
    assert not derived_label.is_symlink()
    assert derived_label.stat().st_dev == label_path.stat().st_dev
    assert derived_label.stat().st_ino == label_path.stat().st_ino
    assert sha256_file(derived_label) == source_hashes[label_path]
    assert derived_snapshot.candidate_graph_summary["candidate_gate_strategy"] == "wide"
    assert derived_snapshot.candidate_graph_fingerprint == candidate_graph_fingerprint(
        derived_snapshot.geometry_candidate_pairs,
        derived_snapshot.candidate_graph_summary,
    )
    assert entry["source_snapshot_sha256"] == source_hashes[snapshot_path]


def test_hard_link_failure_is_explicit_and_never_copies_label(tmp_path: Path) -> None:
    source_root = tmp_path / "source-test"
    manifest_path, snapshot_path, label_path = _source_manifest(source_root)
    source_hashes = {
        path: sha256_file(path) for path in (manifest_path, snapshot_path, label_path)
    }
    output_root = tmp_path / "derived-cross-device"
    with patch(
        "dual_optical_online_benchmark.candidate_gate_ablation.os.link",
        side_effect=OSError(errno.EXDEV, "cross-device link"),
    ):
        with pytest.raises(RuntimeError, match="same-filesystem hard link"):
            derive_candidate_manifest(manifest_path, output_root, "moderate")

    assert not output_root.exists()
    assert {path: sha256_file(path) for path in source_hashes} == source_hashes
