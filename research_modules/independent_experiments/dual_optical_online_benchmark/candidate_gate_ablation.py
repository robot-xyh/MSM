"""Derive anonymous candidate-graph ablation datasets without reading labels."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from .contracts import (
    CANDIDATE_GATE_STRATEGY_NAMES,
    CandidateGatePolicy,
    candidate_gate_policy,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
    write_snapshot,
)
from .dataset import build_shared_candidate_graph, sha256_file


DERIVATION_SCHEMA_VERSION = "candidate-gate-derived-manifest-v1"


def _payload_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relative_artifact_path(value: object, field_name: str) -> Path:
    path = Path(str(value))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must remain inside its dataset root")
    if not path.parts:
        raise ValueError(f"{field_name} cannot be empty")
    return path


def _assert_disjoint_roots(source_root: Path, output_root: Path) -> None:
    if (
        source_root == output_root
        or source_root in output_root.parents
        or output_root in source_root.parents
    ):
        raise ValueError("derived output must use a directory disjoint from the source dataset")


def _hard_link_label_without_reading(
    source_root: Path,
    staging_root: Path,
    relative_label_path: Path,
) -> None:
    source_label = source_root / relative_label_path
    derived_label = staging_root / relative_label_path
    derived_label.parent.mkdir(parents=True, exist_ok=True)
    if derived_label.exists() or derived_label.is_symlink():
        raise FileExistsError(f"derived label path already exists: {derived_label}")
    try:
        resolved_source = source_label.resolve(strict=True)
        resolved_source.relative_to(source_root.resolve())
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("source label must resolve inside its dataset root") from exc
    try:
        os.link(resolved_source, derived_label)
    except OSError as exc:
        raise RuntimeError(
            "candidate derivation requires a same-filesystem hard link for labels; "
            "copying label content is forbidden"
        ) from exc
    try:
        derived_label.resolve(strict=True).relative_to(staging_root.resolve())
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError("derived hard-linked label escaped its dataset root") from exc


def _validate_source_manifest(payload: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    phase = str(payload.get("phase", ""))
    if phase not in {"calibration", "test"}:
        raise ValueError("source manifest phase must be calibration or test")
    entries = [dict(entry) for entry in payload.get("entries", ())]
    if not entries:
        raise ValueError("source manifest contains no snapshot entries")
    allowed_splits = {"train", "validation"} if phase == "calibration" else {"test"}
    if any(str(entry.get("split")) not in allowed_splits for entry in entries):
        raise ValueError("source manifest contains a split outside its phase")
    required = {
        "split",
        "seed",
        "corruption_level",
        "revolution_index",
        "snapshot_path",
        "snapshot_sha256",
        "input_fingerprint",
        "label_path",
        "label_sha256",
    }
    if any(required - set(entry) for entry in entries):
        raise ValueError("source manifest entry is missing a snapshot or label contract")
    return phase, entries


def _candidate_totals() -> dict[str, int]:
    return {
        "snapshot_count": 0,
        "left_track_count": 0,
        "right_track_count": 0,
        "full_pair_count": 0,
        "evaluated_pair_count": 0,
        "eligible_pair_count": 0,
        "retained_pair_count": 0,
        "left_tracks_with_candidate_count": 0,
        "right_tracks_with_candidate_count": 0,
        "isolated_left_track_count": 0,
        "isolated_right_track_count": 0,
    }


def _accumulate_candidate_totals(
    totals: dict[str, int], summary: Mapping[str, int | float | str]
) -> None:
    totals["snapshot_count"] += 1
    for key in tuple(totals):
        if key == "snapshot_count":
            continue
        totals[key] += int(summary[key])


def derive_candidate_manifest(
    source_manifest: str | Path,
    output_dir: str | Path,
    strategy_name: str,
) -> Path:
    """Rebuild candidate pairs from anonymous snapshots into a new dataset root."""

    source_manifest_path = Path(source_manifest).resolve()
    source_root = source_manifest_path.parent
    output_root = Path(output_dir).resolve()
    _assert_disjoint_roots(source_root, output_root)
    if output_root.exists():
        raise FileExistsError(f"derived output already exists: {output_root}")
    if not source_manifest_path.is_file():
        raise FileNotFoundError(source_manifest_path)

    source_manifest_hash = sha256_file(source_manifest_path)
    source_payload = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    phase, entries = _validate_source_manifest(source_payload)
    policy = candidate_gate_policy(strategy_name)
    target_count = int(source_payload["protocol"]["target_count"])
    policy.top_k(target_count)

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}.tmp-",
            dir=output_root.parent,
        )
    )
    source_snapshot_hashes: dict[Path, str] = {}
    totals = _candidate_totals()
    derived_entries: list[dict[str, Any]] = []
    try:
        for entry in entries:
            snapshot_relative = _relative_artifact_path(
                entry["snapshot_path"], "snapshot_path"
            )
            label_relative = _relative_artifact_path(entry["label_path"], "label_path")
            source_snapshot_path = source_root / snapshot_relative
            source_snapshot_hash = sha256_file(source_snapshot_path)
            if source_snapshot_hash != str(entry["snapshot_sha256"]):
                raise ValueError(f"source snapshot hash mismatch: {snapshot_relative}")
            source_snapshot_hashes[source_snapshot_path] = source_snapshot_hash
            snapshot = read_snapshot(source_snapshot_path)
            if (
                snapshot.split != str(entry["split"])
                or snapshot.seed != int(entry["seed"])
                or snapshot.corruption_level != str(entry["corruption_level"])
                or snapshot.revolution_index != int(entry["revolution_index"])
            ):
                raise ValueError("source snapshot identity disagrees with its manifest entry")

            pairs, summary, graph_fingerprint = build_shared_candidate_graph(
                tracks=snapshot.tracks,
                camera_ids=snapshot.camera_ids,
                camera_positions_ned=snapshot.camera_positions_ned,
                cutoff_timestamp=snapshot.cutoff_timestamp,
                target_count=target_count,
                candidate_gate_policy=policy,
            )
            derived_snapshot = replace(
                snapshot,
                geometry_candidate_pairs=pairs,
                candidate_graph_fingerprint=graph_fingerprint,
                candidate_graph_summary=summary,
            )
            derived_snapshot_path = staging_root / snapshot_relative
            write_snapshot(derived_snapshot_path, derived_snapshot)
            _hard_link_label_without_reading(
                source_root, staging_root, label_relative
            )

            derived_entry = dict(entry)
            derived_entry.update(
                {
                    "snapshot_sha256": sha256_file(derived_snapshot_path),
                    "input_fingerprint": snapshot_fingerprint(derived_snapshot),
                    "source_snapshot_sha256": source_snapshot_hash,
                    "source_input_fingerprint": str(entry["input_fingerprint"]),
                    "candidate_graph_fingerprint": graph_fingerprint,
                    "candidate_gate_strategy": policy.strategy_name,
                    "candidate_gate_config_fingerprint": policy.fingerprint,
                }
            )
            derived_entries.append(derived_entry)
            _accumulate_candidate_totals(totals, summary)

        for path, expected_hash in source_snapshot_hashes.items():
            if sha256_file(path) != expected_hash:
                raise RuntimeError(f"source snapshot changed during derivation: {path}")
        if sha256_file(source_manifest_path) != source_manifest_hash:
            raise RuntimeError("source manifest changed during derivation")

        derived_payload = dict(source_payload)
        derived_payload["entries"] = derived_entries
        derived_payload["candidate_gate_ablation"] = {
            "schema_version": DERIVATION_SCHEMA_VERSION,
            "strategy": policy.strategy_name,
            "config": asdict(policy),
            "config_fingerprint": policy.fingerprint,
            "source_manifest": str(source_manifest_path),
            "source_manifest_sha256": source_manifest_hash,
            "phase": phase,
            "truth_labels_read_during_derivation": False,
            "calibration_labels_read_during_derivation": False,
            "test_labels_read_during_derivation": False,
            "label_materialization": "same_filesystem_hard_link_no_read",
            "contains_online_truth_statistics": False,
            "candidate_totals": totals,
        }
        derived_payload["derived_manifest_fingerprint"] = _payload_sha256(
            derived_payload
        )
        derived_manifest = staging_root / source_manifest_path.name
        write_json(derived_manifest, derived_payload)
        staging_root.replace(output_root)
    except BaseException:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    return output_root / source_manifest_path.name


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Derive candidate-gate ablation snapshots without reading labels."
    )
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--strategy",
        required=True,
        choices=CANDIDATE_GATE_STRATEGY_NAMES,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = derive_candidate_manifest(
        args.source_manifest,
        args.output_dir,
        args.strategy,
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = {
        "manifest": str(manifest_path),
        "strategy": args.strategy,
        "candidate_totals": payload["candidate_gate_ablation"]["candidate_totals"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
