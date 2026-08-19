from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

import dual_optical_online_benchmark.gate_confirmation_scoring as scoring_bridge
from dual_optical_online_benchmark.contracts import (
    AssociationMatch,
    AssociationPublication,
    RevolutionSnapshot,
    SnapshotTrack,
    SnapshotTrackSample,
    candidate_graph_fingerprint,
    publication_fingerprint,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from dual_optical_online_benchmark.dataset import sha256_file
from dual_optical_online_benchmark.gate_confirmation_scoring import (
    build_offline_score_rows,
    main,
)


def _track(camera: str, index: int, timestamp: float) -> SnapshotTrack:
    sample = SnapshotTrackSample(
        sweep_index=int(timestamp // 2),
        timestamp=timestamp,
        direction_ned=(1.0, 0.0, 0.0),
        detection_count=1,
        bbox_area_px2=2.0,
        confidence=0.9,
    )
    return SnapshotTrack(f"{camera}-{index}", camera, (sample,))


def _snapshot(split: str, seed: int, level: str, revolution: int) -> RevolutionSnapshot:
    tracks = {
        "A": (_track("A", 1, revolution * 2.0), _track("A", 2, revolution * 2.0)),
        "B": (_track("B", 1, revolution * 2.0), _track("B", 2, revolution * 2.0)),
    }
    pairs = tuple((left.track_id, right.track_id) for left in tracks["A"] for right in tracks["B"])
    summary = {
        "builder_version": "fixture",
        "retained_pair_count": len(pairs),
        "candidate_build_ms": 1.25,
    }
    return RevolutionSnapshot(
        protocol_fingerprint="fixture-protocol",
        seed=seed,
        split=split,
        corruption_level=level,
        revolution_index=revolution,
        cutoff_timestamp=float(revolution * 2),
        camera_ids=("A", "B"),
        camera_positions_ned={"A": (0.0, -1.0, 0.0), "B": (0.0, 1.0, 0.0)},
        focal_length_px=1000.0,
        tracks=tracks,
        target_count=2,
        tracker_fingerprint="fixture-tracker",
        geometry_candidate_pairs=pairs,
        candidate_graph_fingerprint=candidate_graph_fingerprint(pairs, summary),
        candidate_graph_summary=summary,
    )


def _labels(seed: int, level: str, revolution: int) -> dict[str, object]:
    return {
        "offline_truth_only": True,
        "seed": seed,
        "corruption_level": level,
        "revolution_index": revolution,
        "track_truth_counts": {
            "A-1": {"T-1": 3},
            "A-2": {"T-2": 3},
            "B-1": {"T-1": 3},
            "B-2": {"T-2": 3},
        },
        "truth_heading_groups": {
            "T-1": "heading_0_deg",
            "T-2": "heading_minus_30_deg",
        },
    }


def _publication(
    snapshot: RevolutionSnapshot, pairs: list[tuple[str, str]]
) -> AssociationPublication:
    return AssociationPublication(
        route_name="gnn",
        route_version="fixture",
        model_fingerprint="fixture-model",
        seed=snapshot.seed,
        corruption_level=snapshot.corruption_level,
        revolution_index=snapshot.revolution_index,
        cutoff_timestamp=snapshot.cutoff_timestamp,
        input_fingerprint=snapshot_fingerprint(snapshot),
        availability="available_cuda",
        matches=tuple(
            AssociationMatch(left, right, 0.9, "confirmed") for left, right in pairs
        ),
        candidate_graph_fingerprint=snapshot.candidate_graph_fingerprint,
        stage_latencies_ms={
            "candidate_build_ms": 1.25,
            "tensor_preparation_ms": 2.0,
            "gpu_scoring_ms": 3.0,
            "hungarian_ms": 1.0,
            "confirmation_ms": 0.5,
        },
        scoring_ms=5.0,
        hungarian_ms=1.0,
        end_to_end_ms=8.0,
    )


def _build_variant(
    root: Path,
    *,
    variant_id: str,
    split: str,
    seed: int,
    pairs_by_revolution: list[list[tuple[str, str]]],
    invalid_one_to_one_revolution: int | None = None,
) -> tuple[Path, Path]:
    source_split = "validation" if split == "validation" else "test"
    source_root = root / variant_id / "dataset"
    confirmation_root = root / variant_id / "confirmation"
    entries = []
    publications = []
    for level in ("clean", "light"):
        for revolution, pairs in enumerate(pairs_by_revolution, start=1):
            snapshot = _snapshot(source_split, seed, level, revolution)
            snapshot_relative = Path(
                f"snapshots/{source_split}/{seed}/{level}/revolution_{revolution:02d}.json"
            )
            label_relative = Path(
                f"labels/{source_split}/{seed}/{level}/revolution_{revolution:02d}.json"
            )
            snapshot_path = source_root / snapshot_relative
            label_path = source_root / label_relative
            write_snapshot(snapshot_path, snapshot)
            write_json(label_path, _labels(seed, level, revolution))
            entries.append(
                {
                    "split": source_split,
                    "seed": seed,
                    "corruption_level": level,
                    "revolution_index": revolution,
                    "snapshot_path": snapshot_relative.as_posix(),
                    "snapshot_sha256": sha256_file(snapshot_path),
                    "input_fingerprint": snapshot_fingerprint(snapshot),
                    "label_path": label_relative.as_posix(),
                    "label_sha256": sha256_file(label_path),
                }
            )
            publication = _publication(snapshot, pairs)
            publication_payload = asdict(publication)
            if invalid_one_to_one_revolution == revolution:
                publication_payload["matches"] = [
                    {
                        "track_a_id": "A-1",
                        "track_b_id": "B-2",
                        "score": 0.9,
                        "decision_state": "confirmed",
                    },
                    {
                        "track_a_id": "A-2",
                        "track_b_id": "B-2",
                        "score": 0.8,
                        "decision_state": "confirmed",
                    },
                ]
            publication_relative = Path(
                f"publications/{seed}/{level}/revolution_{revolution:02d}.json"
            )
            publication_path = confirmation_root / publication_relative
            wrapper = {
                "publication": publication_payload,
                "diagnostics": {"runtime_device": "cuda:0"},
            }
            if invalid_one_to_one_revolution != revolution:
                wrapper["publication_fingerprint_sha256"] = publication_fingerprint(
                    publication
                )
            write_json(publication_path, wrapper)
            record = {
                "seed": seed,
                "corruption_level": level,
                "revolution_index": revolution,
                "input_fingerprint_sha256": snapshot_fingerprint(snapshot),
                "snapshot_sha256": sha256_file(snapshot_path),
                "publication_path": publication_relative.as_posix(),
                "publication_sha256": sha256_file(publication_path),
            }
            if invalid_one_to_one_revolution != revolution:
                record["publication_fingerprint_sha256"] = publication_fingerprint(
                    publication
                )
                record["gpu_peak_memory_mb"] = 128.0
            publications.append(record)
    source_manifest = source_root / (
        "calibration_manifest.json" if split == "validation" else "test_manifest.json"
    )
    write_json(
        source_manifest,
        {
            "phase": "calibration" if split == "validation" else "test",
            "protocol": {"target_count": 2},
            "entries": entries,
        },
    )
    confirmation_manifest = confirmation_root / "confirmation_manifest.json"
    write_json(
        confirmation_manifest,
        {
            "truth_scoring_performed": False,
            "truth_fields_accessed": False,
            "input_manifest_sha256": sha256_file(source_manifest),
            "counts": {"revolution_count": len(publications)},
            "publications": publications,
        },
    )
    return source_manifest, confirmation_manifest


def _variant_spec(
    root: Path, variants: list[tuple[str, str, Path, Path]]
) -> Path:
    path = root / "variant_spec.json"
    write_json(
        path,
        {
            "variants": [
                {
                    "variant_id": variant_id,
                    "target_count": 2,
                    "split": split,
                    "source_manifest": str(source.relative_to(root)),
                    "confirmation_manifest": str(confirmation.relative_to(root)),
                }
                for variant_id, split, source, confirmation in variants
            ]
        },
    )
    return path


def test_validation_and_test_are_scored_after_all_publications_are_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _build_variant(
        tmp_path,
        variant_id="validation_variant",
        split="validation",
        seed=101,
        pairs_by_revolution=[[], [("A-1", "B-1")]],
    )
    test = _build_variant(
        tmp_path,
        variant_id="test_variant",
        split="test",
        seed=201,
        pairs_by_revolution=[[("A-1", "B-1")], [("A-1", "B-1")]],
    )
    spec = _variant_spec(
        tmp_path,
        [
            ("validation_variant", "validation", *validation),
            ("test_variant", "test", *test),
        ],
    )
    expected_publication_reads = 8
    state = {"publication_reads": 0, "first_label_checked": False}
    original_publication_reader = scoring_bridge._read_publication_file
    original_label_reader = scoring_bridge.load_offline_labels

    def publication_reader(path: Path):
        state["publication_reads"] += 1
        return original_publication_reader(path)

    def label_reader(path: Path, expected_sha256: str):
        assert state["publication_reads"] == expected_publication_reads
        state["first_label_checked"] = True
        return original_label_reader(path, expected_sha256)

    monkeypatch.setattr(scoring_bridge, "_read_publication_file", publication_reader)
    monkeypatch.setattr(scoring_bridge, "load_offline_labels", label_reader)

    payload = build_offline_score_rows(spec)

    assert state["first_label_checked"] is True
    assert payload["truth_used_online"] is False
    assert payload["labels_read_after_all_online_publications_validated"] is True
    assert {row["split"] for row in payload["rows"]} == {"validation", "test"}
    validation_rows = [
        row for row in payload["rows"] if row["variant_id"] == "validation_variant"
    ]
    assert validation_rows[0]["match_count"] == 0
    assert validation_rows[0]["first_confirmation_s"] is None
    assert validation_rows[1]["first_confirmation_s"] == 4.0
    assert validation_rows[1]["gpu_peak_memory_available"] is True


@pytest.mark.parametrize("mismatch", ("source_manifest", "publication"))
def test_hash_mismatch_fails_closed(tmp_path: Path, mismatch: str) -> None:
    source, confirmation = _build_variant(
        tmp_path,
        variant_id="hash_variant",
        split="test",
        seed=301,
        pairs_by_revolution=[[('A-1', 'B-1')]],
    )
    confirmation_payload = json.loads(confirmation.read_text(encoding="utf-8"))
    if mismatch == "source_manifest":
        confirmation_payload["input_manifest_sha256"] = "0" * 64
    else:
        confirmation_payload["publications"][0]["publication_sha256"] = "0" * 64
    write_json(confirmation, confirmation_payload)
    spec = _variant_spec(
        tmp_path, [("hash_variant", "test", source, confirmation)]
    )

    with pytest.raises(ValueError, match="hash mismatch"):
        build_offline_score_rows(spec)


def test_missing_online_publication_fails_matrix_completeness(tmp_path: Path) -> None:
    source, confirmation = _build_variant(
        tmp_path,
        variant_id="incomplete_variant",
        split="test",
        seed=351,
        pairs_by_revolution=[[('A-1', 'B-1')], [('A-1', 'B-1')]],
    )
    payload = json.loads(confirmation.read_text(encoding="utf-8"))
    payload["publications"] = payload["publications"][:-1]
    payload["counts"]["revolution_count"] = len(payload["publications"])
    write_json(confirmation, payload)
    spec = _variant_spec(
        tmp_path,
        [("incomplete_variant", "test", source, confirmation)],
    )

    with pytest.raises(ValueError, match="publication matrix is incomplete"):
        build_offline_score_rows(spec)


def test_switch_empty_output_and_one_to_one_violation_are_explicit(
    tmp_path: Path,
) -> None:
    source, confirmation = _build_variant(
        tmp_path,
        variant_id="contract_variant",
        split="test",
        seed=401,
        pairs_by_revolution=[[], [("A-1", "B-1")], [("A-1", "B-2")]],
        invalid_one_to_one_revolution=3,
    )
    spec = _variant_spec(
        tmp_path, [("contract_variant", "test", source, confirmation)]
    )

    payload = build_offline_score_rows(spec)
    clean = [
        row
        for row in payload["rows"]
        if row["variant_id"] == "contract_variant" and row["level"] == "clean"
    ]

    assert clean[0]["match_count"] == 0
    assert clean[0]["first_confirmation_s"] is None
    assert clean[1]["first_confirmation_s"] == 4.0
    assert clean[2]["first_confirmation_s"] == 4.0
    assert clean[2]["relation_switch_count"] == 1
    assert clean[2]["one_to_one_violations"] == 1
    assert clean[2]["gpu_peak_memory_mb"] == 0.0
    assert clean[2]["gpu_peak_memory_available"] is False
    assert clean[2]["gpu_peak_memory_source"] == "not_recorded"
    audit = payload["variants"][0]
    assert audit["gpu_peak_memory_missing_count"] == 2
    assert all(item["label_sha256"] for item in audit["artifacts"])


def test_cli_writes_reporting_compatible_rows_json(tmp_path: Path) -> None:
    source, confirmation = _build_variant(
        tmp_path,
        variant_id="cli_variant",
        split="test",
        seed=501,
        pairs_by_revolution=[[('A-1', 'B-1')]],
    )
    spec = _variant_spec(
        tmp_path, [("cli_variant", "test", source, confirmation)]
    )
    output = tmp_path / "scored_rows.json"

    assert main(["--variant-spec", str(spec), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["truth_used_online"] is False
    assert payload["row_count"] == 2
    required = {
        "variant_id",
        "target_count",
        "seed",
        "split",
        "level",
        "revolution",
        "match_count",
        "correct_count",
        "false_count",
        "unique_correct_targets",
        "candidate_opportunities",
        "candidate_true_retained",
        "candidate_edge_count",
        "candidate_build_ms",
        "inference_ms",
        "assignment_ms",
        "end_to_end_ms",
        "first_confirmation_s",
        "relation_switch_count",
        "one_to_one_violations",
        "gpu_peak_memory_mb",
    }
    assert required <= set(payload["rows"][0])
