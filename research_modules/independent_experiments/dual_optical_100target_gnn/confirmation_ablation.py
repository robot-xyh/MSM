"""Replay anonymous test snapshots under explicit confirmation diagnostics."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    RevolutionSnapshot,
    publication_fingerprint,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
)

from .loader import sha256_file
from .online import (
    CONFIRMATION_STRATEGIES,
    ConfirmationStrategy,
    OnlineGNNAssociator,
)


MANIFEST_SCHEMA_VERSION = "dual-optical-confirmation-ablation-v1"
_FORBIDDEN_ONLINE_KEY_PARTS = ("truth", "actor", "identity", "label")
ReplaySplit = Literal["test", "validation"]


@dataclass(frozen=True)
class ReplayEntry:
    snapshot: RevolutionSnapshot
    snapshot_path: Path
    snapshot_sha256: str
    input_fingerprint: str


def _safe_path(root: Path, relative: object) -> Path:
    path = Path(str(relative))
    if not str(path) or path.is_absolute():
        raise ValueError("snapshot_path must be nonempty and relative")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("snapshot_path escapes the input manifest root") from exc
    return resolved


def _forbidden_online_keys(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            location = f"{prefix}.{key}" if prefix else key
            lowered = key.lower()
            if any(part in lowered for part in _FORBIDDEN_ONLINE_KEY_PARTS):
                found.append(location)
            found.extend(_forbidden_online_keys(nested, location))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found.extend(_forbidden_online_keys(nested, f"{prefix}[{index}]"))
    return found


def _load_replay_entries(
    test_manifest: Path,
    *,
    input_split: ReplaySplit = "test",
) -> tuple[dict[str, Any], tuple[ReplayEntry, ...], int]:
    if input_split not in {"test", "validation"}:
        raise ValueError("confirmation replay supports only test or validation")
    manifest_path = Path(test_manifest).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_phase = "test" if input_split == "test" else "calibration"
    if payload.get("phase") != expected_phase:
        raise ValueError(
            f"{input_split} replay requires phase={expected_phase}"
        )
    if input_split == "test" and payload.get("test_access_allowed") is not True:
        raise ValueError("test replay requires test_access_allowed=true")
    all_entries = [dict(item) for item in payload.get("entries", ())]
    if not all_entries:
        raise ValueError("input manifest entries must be nonempty")
    valid_splits = {"train", "validation", "test"}
    if any(item.get("split") not in valid_splits for item in all_entries):
        raise ValueError("input manifest contains an unsupported split")
    if input_split == "test" and any(
        item.get("split") != "test" for item in all_entries
    ):
        raise ValueError("phase=test manifest must contain only test entries")
    if input_split == "validation" and any(
        item.get("split") == "test" for item in all_entries
    ):
        raise ValueError("phase=calibration manifest cannot contain test entries")
    entries = [item for item in all_entries if item.get("split") == input_split]
    if not entries:
        raise ValueError(f"input manifest contains no {input_split} entries")

    root = manifest_path.parent
    loaded: list[ReplayEntry] = []
    keys: set[tuple[int, str, int]] = set()
    ignored_label_references = sum(
        "label_path" in entry or "label_sha256" in entry
        for entry in all_entries
    )
    for entry in entries:
        snapshot_path = _safe_path(root, entry["snapshot_path"])
        expected_sha256 = str(entry["snapshot_sha256"])
        if sha256_file(snapshot_path) != expected_sha256:
            raise ValueError("input snapshot hash mismatch")
        raw_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        forbidden = _forbidden_online_keys(raw_snapshot)
        if forbidden:
            raise ValueError(
                "online snapshot contains forbidden truth-bearing fields: "
                + ", ".join(forbidden[:5])
            )
        snapshot = read_snapshot(snapshot_path)
        expected_fingerprint = str(
            entry.get("input_fingerprint", entry.get("input_fingerprint_sha256", ""))
        )
        if not expected_fingerprint or snapshot_fingerprint(snapshot) != expected_fingerprint:
            raise ValueError("input snapshot fingerprint mismatch")
        expected_metadata = (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        actual_metadata = (
            snapshot.seed,
            snapshot.corruption_level,
            snapshot.revolution_index,
        )
        if snapshot.split != input_split or actual_metadata != expected_metadata:
            raise ValueError("input snapshot metadata mismatch")
        if actual_metadata in keys:
            raise ValueError("input manifest contains a duplicate revolution")
        keys.add(actual_metadata)
        loaded.append(
            ReplayEntry(
                snapshot=snapshot,
                snapshot_path=snapshot_path,
                snapshot_sha256=expected_sha256,
                input_fingerprint=expected_fingerprint,
            )
        )
    loaded.sort(
        key=lambda item: (
            item.snapshot.seed,
            item.snapshot.corruption_level,
            item.snapshot.revolution_index,
        )
    )
    return payload, tuple(loaded), ignored_label_references


def _latency_summary(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return {"count": 0, "total_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": int(array.size),
        "total_ms": float(np.sum(array)),
        "p50_ms": float(np.percentile(array, 50)),
        "p95_ms": float(np.percentile(array, 95)),
        "max_ms": float(np.max(array)),
    }


def run_confirmation_ablation(
    test_manifest: str | Path,
    freeze_manifest: str | Path,
    output_dir: str | Path,
    *,
    confirmation_strategy: ConfirmationStrategy,
    device: str = "auto",
    graded_probability_threshold: float | None = None,
    graded_margin: float | None = None,
    diagnostic_mode: bool = False,
    input_split: ReplaySplit = "test",
) -> Path:
    """Replay anonymous snapshots and write diagnostics without opening labels."""

    test_manifest_path = Path(test_manifest).resolve()
    freeze_manifest_path = Path(freeze_manifest).resolve()
    test_payload, entries, ignored_label_references = _load_replay_entries(
        test_manifest_path,
        input_split=input_split,
    )
    associator = OnlineGNNAssociator(
        str(freeze_manifest_path),
        device=device,
        confirmation_strategy=confirmation_strategy,
        graded_probability_threshold=graded_probability_threshold,
        graded_margin=graded_margin,
        diagnostic_mode=diagnostic_mode,
    )

    destination = Path(output_dir).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("confirmation ablation output directory must be empty")
    destination.mkdir(parents=True, exist_ok=True)
    counts = {
        "revolution_count": 0,
        "raw_match_count": 0,
        "tentative_match_count": 0,
        "fast_confirmed_match_count": 0,
        "confirmed_match_count": 0,
        "published_match_count": 0,
    }
    latencies: dict[str, list[float]] = {}
    publication_records: list[dict[str, Any]] = []
    backends: set[str] = set()
    route_versions: set[str] = set()
    for entry in entries:
        result = associator.associate(entry.snapshot)
        publication = result.publication
        relative_path = Path("publications") / str(publication.seed) / publication.corruption_level / f"revolution_{publication.revolution_index:02d}.json"
        output_path = destination / relative_path
        record = {
            "publication": asdict(publication),
            "publication_fingerprint_sha256": publication_fingerprint(publication),
            "diagnostics": {
                "raw_matches": [asdict(item) for item in result.raw_matches],
                "tentative_matches": [asdict(item) for item in result.tentative_matches],
                "fast_confirmed_matches": [
                    asdict(item) for item in result.fast_confirmed_matches
                ],
                "confirmed_matches": [asdict(item) for item in result.confirmed_matches],
                "inference_backend": result.inference_backend,
                "runtime_device": associator.runtime_device,
                "confirmation_strategy": result.confirmation_strategy,
                "diagnostic_mode": result.diagnostic_mode,
                "stage_latency_ms": dict(result.stage_latency_ms),
            },
        }
        write_json(output_path, record)
        revolution_counts = {
            "raw_match_count": len(result.raw_matches),
            "tentative_match_count": len(result.tentative_matches),
            "fast_confirmed_match_count": len(result.fast_confirmed_matches),
            "confirmed_match_count": len(result.confirmed_matches),
            "published_match_count": len(publication.matches),
        }
        counts["revolution_count"] += 1
        for name, value in revolution_counts.items():
            counts[name] += value
        for name, value in result.stage_latency_ms.items():
            latencies.setdefault(name, []).append(float(value))
        backends.add(result.inference_backend)
        route_versions.add(publication.route_version)
        publication_records.append(
            {
                "seed": publication.seed,
                "corruption_level": publication.corruption_level,
                "revolution_index": publication.revolution_index,
                "input_fingerprint_sha256": result.input_fingerprint_sha256,
                "snapshot_sha256": entry.snapshot_sha256,
                "publication_path": relative_path.as_posix(),
                "publication_fingerprint_sha256": record[
                    "publication_fingerprint_sha256"
                ],
                **revolution_counts,
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "diagnostic_only": True,
        "formal_route_replacement_allowed": False,
        "truth_scoring_performed": False,
        "truth_fields_accessed": False,
        "offline_label_references_ignored": ignored_label_references,
        "input_split": input_split,
        "confirmation_strategy": confirmation_strategy,
        "strategy_parameters": {
            "graded_probability_threshold": graded_probability_threshold,
            "graded_margin": graded_margin,
            "diagnostic_mode": diagnostic_mode,
        },
        "route_versions": sorted(route_versions),
        "test_manifest_sha256": sha256_file(test_manifest_path),
        "freeze_manifest_sha256": sha256_file(freeze_manifest_path),
        "protocol_fingerprint": test_payload.get("protocol_fingerprint", ""),
        "model_fingerprint_sha256": associator.model_fingerprint,
        "device": {
            "requested": device,
            "runtime": associator.runtime_device,
            "inference_backends": sorted(backends),
        },
        "counts": counts,
        "stage_latency_summary": {
            name: _latency_summary(values) for name, values in sorted(latencies.items())
        },
        "publications": publication_records,
    }
    manifest_path = destination / "confirmation_ablation_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-manifest", required=True)
    parser.add_argument("--freeze-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--strategy",
        choices=CONFIRMATION_STRATEGIES,
        required=True,
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--split",
        choices=("test", "validation"),
        default="test",
    )
    parser.add_argument("--probability-threshold", type=float)
    parser.add_argument("--margin", type=float)
    parser.add_argument("--diagnostic-mode", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        run_confirmation_ablation(
            args.test_manifest,
            args.freeze_manifest,
            args.output_dir,
            confirmation_strategy=args.strategy,
            device=args.device,
            graded_probability_threshold=args.probability_threshold,
            graded_margin=args.margin,
            diagnostic_mode=args.diagnostic_mode,
            input_split=args.split,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
