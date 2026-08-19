"""Offline scoring bridge for gate and confirmation ablation publications.

The bridge deliberately runs in two phases.  It first validates every source
manifest, anonymous snapshot, confirmation manifest, and online publication.
Only after all variants have passed those checks does it open offline labels
and call :func:`score_publication`.

Variant-spec example::

    {
      "variants": [
        {
          "variant_id": "baseline",
          "target_count": 20,
          "split": "test",
          "source_manifest": "dataset/test_manifest.json",
          "confirmation_manifest": "publications/confirmation_manifest.json"
        }
      ]
    }
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .contracts import (
    AssociationMatch,
    RevolutionSnapshot,
    publication_fingerprint,
    read_snapshot,
    snapshot_fingerprint,
)
from .scoring import load_offline_labels, score_publication


SCHEMA_VERSION = "dual-optical-gate-confirmation-offline-scores-v1"
REPORT_LEVELS = {"clean", "light"}
ALLOWED_SPLITS = {"validation", "test", "offline"}


@dataclass(frozen=True)
class ScorablePublication:
    """AssociationPublication-compatible view that preserves invalid outputs.

    Normal online code rejects duplicate A/B assignments at construction time.
    The offline bridge must still report such a violation if a foreign or
    corrupted publisher emitted one, so this view intentionally does not apply
    that constructor check.
    """

    route_name: str
    route_version: str
    model_fingerprint: str
    seed: int
    corruption_level: str
    revolution_index: int
    cutoff_timestamp: float
    input_fingerprint: str
    availability: str
    matches: tuple[AssociationMatch, ...]
    rejection_reasons: Mapping[str, int] = field(default_factory=dict)
    candidate_graph_fingerprint: str = ""
    stage_latencies_ms: Mapping[str, float] = field(default_factory=dict)
    scoring_ms: float = 0.0
    hungarian_ms: float = 0.0
    end_to_end_ms: float = 0.0
    deadline_ms: float = 1000.0

    @property
    def deadline_met(self) -> bool:
        return self.end_to_end_ms <= self.deadline_ms


@dataclass(frozen=True)
class PreparedPublication:
    variant_id: str
    target_count: int
    output_split: str
    source_manifest_path: Path
    source_manifest_sha256: str
    source_entry: Mapping[str, Any]
    snapshot_path: Path
    snapshot_sha256: str
    snapshot: RevolutionSnapshot
    confirmation_manifest_path: Path
    confirmation_manifest_sha256: str
    confirmation_record: Mapping[str, Any]
    publication_path: Path
    publication_file_sha256: str
    publication_fingerprint_sha256: str
    publication: ScorablePublication
    gpu_peak_memory_mb: float
    gpu_peak_memory_available: bool
    gpu_peak_memory_source: str

    @property
    def identity(self) -> tuple[str, int, str, int]:
        return (
            self.variant_id,
            self.publication.seed,
            self.publication.corruption_level,
            self.publication.revolution_index,
        )


@dataclass(frozen=True)
class PreparedVariant:
    variant_id: str
    target_count: int
    output_split: str
    source_manifest_path: Path
    source_manifest_sha256: str
    source_declared_hashes: Mapping[str, str]
    confirmation_manifest_path: Path
    confirmation_manifest_sha256: str
    confirmation_declared_hashes: Mapping[str, str]
    publications: tuple[PreparedPublication, ...]
    skipped_reporting_levels: tuple[str, ...]


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_artifact(root: Path, value: object, field_name: str) -> Path:
    relative = Path(str(value))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{field_name} must be a relative path inside its manifest root")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"{field_name} escapes its manifest root") from exc
    return path


def _spec_path(root: Path, value: object, field_name: str) -> Path:
    if not value:
        raise ValueError(f"variant has no {field_name}")
    path = Path(str(value))
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _as_nonnegative_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be finite and nonnegative")
    return number


def _publication_from_mapping(values: Mapping[str, Any]) -> ScorablePublication:
    matches = tuple(
        AssociationMatch(
            track_a_id=str(item["track_a_id"]),
            track_b_id=str(item["track_b_id"]),
            score=float(item.get("score", 0.0)),
            decision_state=str(item.get("decision_state", "published")),
        )
        for item in values.get("matches", ())
    )
    publication = ScorablePublication(
        route_name=str(values["route_name"]),
        route_version=str(values["route_version"]),
        model_fingerprint=str(values["model_fingerprint"]),
        seed=int(values["seed"]),
        corruption_level=str(values["corruption_level"]),
        revolution_index=int(values["revolution_index"]),
        cutoff_timestamp=float(values["cutoff_timestamp"]),
        input_fingerprint=str(values["input_fingerprint"]),
        availability=str(values.get("availability", "available")),
        matches=matches,
        rejection_reasons={
            str(key): int(value)
            for key, value in values.get("rejection_reasons", {}).items()
        },
        candidate_graph_fingerprint=str(
            values.get("candidate_graph_fingerprint", "")
        ),
        stage_latencies_ms={
            str(key): _as_nonnegative_float(value, f"stage_latencies_ms.{key}")
            for key, value in values.get("stage_latencies_ms", {}).items()
        },
        scoring_ms=_as_nonnegative_float(values.get("scoring_ms", 0.0), "scoring_ms"),
        hungarian_ms=_as_nonnegative_float(
            values.get("hungarian_ms", 0.0), "hungarian_ms"
        ),
        end_to_end_ms=_as_nonnegative_float(
            values.get("end_to_end_ms", 0.0), "end_to_end_ms"
        ),
        deadline_ms=_as_nonnegative_float(
            values.get("deadline_ms", 1000.0), "deadline_ms"
        ),
    )
    if publication.end_to_end_ms + 1e-9 < (
        publication.scoring_ms + publication.hungarian_ms
    ):
        raise ValueError("publication end_to_end_ms is below measured stages")
    return publication


def _read_publication_file(
    path: Path,
) -> tuple[dict[str, Any], Mapping[str, Any], ScorablePublication]:
    wrapper = _read_json_object(path)
    raw_publication = wrapper.get("publication", wrapper)
    if not isinstance(raw_publication, Mapping):
        raise ValueError(f"publication payload is not an object: {path}")
    return wrapper, raw_publication, _publication_from_mapping(raw_publication)


def _declared_manifest_hash(confirmation: Mapping[str, Any]) -> str:
    candidates = []
    for key in (
        "source_manifest_sha256",
        "input_manifest_sha256",
        "online_manifest_sha256",
        "test_manifest_sha256",
        "validation_manifest_sha256",
    ):
        value = confirmation.get(key)
        if value:
            candidates.append(str(value))
    nested = confirmation.get("input_manifest")
    if isinstance(nested, Mapping) and nested.get("sha256"):
        candidates.append(str(nested["sha256"]))
    unique = set(candidates)
    if not unique:
        raise ValueError("confirmation manifest has no input-manifest hash binding")
    if len(unique) != 1:
        raise ValueError("confirmation manifest contains conflicting input-manifest hashes")
    return unique.pop()


def _collect_declared_hashes(value: Any, prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(value, Mapping):
        for key, nested in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            if (
                isinstance(nested, str)
                and ("sha256" in str(key).lower() or "fingerprint" in str(key).lower())
            ):
                result[location] = nested
            result.update(_collect_declared_hashes(nested, location))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            result.update(_collect_declared_hashes(nested, f"{prefix}[{index}]"))
    return result


def _publication_record_hashes(record: Mapping[str, Any]) -> tuple[str | None, str | None]:
    file_hash = record.get("publication_sha256") or record.get(
        "publication_file_sha256"
    )
    fingerprint = record.get("publication_fingerprint_sha256")
    if not file_hash and not fingerprint:
        raise ValueError("confirmation publication record has no publication hash")
    return (
        None if not file_hash else str(file_hash),
        None if not fingerprint else str(fingerprint),
    )


def _record_input_fingerprint(record: Mapping[str, Any]) -> str:
    value = record.get("input_fingerprint") or record.get(
        "input_fingerprint_sha256"
    )
    if not value:
        raise ValueError("confirmation publication record has no input fingerprint")
    return str(value)


def _gpu_peak(
    record: Mapping[str, Any],
    wrapper: Mapping[str, Any],
    confirmation: Mapping[str, Any],
) -> tuple[float, bool, str]:
    diagnostics = (
        wrapper.get("diagnostics", {})
        if isinstance(wrapper.get("diagnostics"), Mapping)
        else {}
    )
    device = (
        confirmation.get("device", {})
        if isinstance(confirmation.get("device"), Mapping)
        else {}
    )
    device_peak = device.get("gpu_peak_memory_mb")
    if device_peak is None:
        device_peak = device.get("peak_memory_mb")
    candidates: tuple[tuple[str, Any], ...] = (
        (
            "publication_record",
            None
            if record.get("gpu_peak_memory_available") is False
            else record.get("gpu_peak_memory_mb"),
        ),
        (
            "publication_record_cuda",
            None
            if record.get("gpu_peak_memory_available") is False
            else record.get("cuda_peak_memory_mb"),
        ),
        (
            "publication_diagnostics",
            None
            if diagnostics.get("gpu_peak_memory_available") is False
            else diagnostics.get("gpu_peak_memory_mb"),
        ),
        (
            "publication_diagnostics_cuda",
            None
            if diagnostics.get("gpu_peak_memory_available") is False
            else diagnostics.get("cuda_peak_memory_mb"),
        ),
        (
            "confirmation_manifest",
            None
            if confirmation.get("gpu_peak_memory_available") is False
            else confirmation.get("gpu_peak_memory_mb"),
        ),
        (
            "confirmation_manifest_cuda",
            None
            if confirmation.get("gpu_peak_memory_available") is False
            else confirmation.get("cuda_peak_memory_mb"),
        ),
        (
            "confirmation_device",
            None if device.get("gpu_peak_memory_available") is False else device_peak,
        ),
    )
    for source, value in candidates:
        if value is not None:
            return _as_nonnegative_float(value, "gpu_peak_memory_mb"), True, source
    return 0.0, False, "not_recorded"


def _source_candidates(
    source_entries: Sequence[Mapping[str, Any]],
    record: Mapping[str, Any],
    output_split: str,
    source_split: str | None,
) -> list[Mapping[str, Any]]:
    seed = int(record["seed"])
    level = str(record["corruption_level"])
    revolution = int(record["revolution_index"])
    expected_split = source_split or (output_split if output_split != "offline" else None)
    return [
        entry
        for entry in source_entries
        if int(entry.get("seed", -1)) == seed
        and str(entry.get("corruption_level")) == level
        and int(entry.get("revolution_index", -1)) == revolution
        and (expected_split is None or str(entry.get("split")) == expected_split)
    ]


def _stage_value(stages: Mapping[str, float], *names: str) -> float | None:
    for name in names:
        if name in stages:
            return float(stages[name])
    return None


def _latencies(
    publication: ScorablePublication, snapshot: RevolutionSnapshot
) -> tuple[float, float, float, float]:
    stages = publication.stage_latencies_ms
    candidate_build = _stage_value(stages, "candidate_build_ms")
    if candidate_build is None:
        candidate_build = float(snapshot.candidate_graph_summary.get("candidate_build_ms", 0.0))
    inference = _stage_value(stages, "inference_ms", "model_inference_ms")
    if inference is None:
        inference_parts = (
            "tensor_preparation_ms",
            "gpu_scoring_ms",
            "cpu_scoring_ms",
            "edge_scoring_ms",
        )
        inference = sum(float(stages.get(name, 0.0)) for name in inference_parts)
        if inference <= 0.0:
            inference = publication.scoring_ms
    assignment = _stage_value(stages, "assignment_ms", "hungarian_ms")
    if assignment is None:
        assignment = publication.hungarian_ms
    return candidate_build, inference, assignment, publication.end_to_end_ms


def _one_to_one_violations(publication: ScorablePublication) -> int:
    left = Counter(match.track_a_id for match in publication.matches)
    right = Counter(match.track_b_id for match in publication.matches)
    return sum(max(0, count - 1) for count in left.values()) + sum(
        max(0, count - 1) for count in right.values()
    )


def _unique_bindings(publication: ScorablePublication) -> dict[str, str]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for match in publication.matches:
        candidates[match.track_a_id].add(match.track_b_id)
    return {
        track_a: next(iter(track_b_values))
        for track_a, track_b_values in candidates.items()
        if len(track_b_values) == 1
    }


def _prepare_variant(
    spec_root: Path, raw_variant: Mapping[str, Any]
) -> PreparedVariant:
    variant_id = str(raw_variant.get("variant_id") or "").strip()
    if not variant_id:
        raise ValueError("variant_id must not be empty")
    target_count = int(raw_variant.get("target_count", 0))
    if target_count <= 0:
        raise ValueError(f"{variant_id}: target_count must be positive")
    output_split = str(raw_variant.get("split") or "").lower()
    if output_split not in ALLOWED_SPLITS:
        raise ValueError(f"{variant_id}: split must be validation, test, or offline")
    source_split_value = raw_variant.get("source_split")
    source_split = None if source_split_value is None else str(source_split_value)
    if source_split is not None and source_split not in {"train", "validation", "test"}:
        raise ValueError(f"{variant_id}: invalid source_split")

    source_path = _spec_path(
        spec_root, raw_variant.get("source_manifest"), "source_manifest"
    )
    confirmation_path = _spec_path(
        spec_root,
        raw_variant.get("confirmation_manifest"),
        "confirmation_manifest",
    )
    source_sha = _sha256(source_path)
    confirmation_sha = _sha256(confirmation_path)
    source = _read_json_object(source_path)
    confirmation = _read_json_object(confirmation_path)
    if confirmation.get("truth_scoring_performed") is not False:
        raise ValueError(f"{variant_id}: online confirmation did not prove truth isolation")
    if confirmation.get("truth_fields_accessed") is True:
        raise ValueError(f"{variant_id}: online confirmation accessed truth fields")
    if _declared_manifest_hash(confirmation) != source_sha:
        raise ValueError(f"{variant_id}: confirmation input-manifest hash mismatch")
    protocol = source.get("protocol")
    if not isinstance(protocol, Mapping) or int(protocol.get("target_count", 0)) != target_count:
        raise ValueError(f"{variant_id}: source manifest target_count mismatch")
    source_entries = source.get("entries")
    publication_records = confirmation.get("publications")
    if (
        not isinstance(source_entries, list)
        or not source_entries
        or not isinstance(publication_records, list)
        or not publication_records
    ):
        raise ValueError(f"{variant_id}: source or confirmation manifest is empty")
    if isinstance(confirmation.get("counts"), Mapping):
        expected = confirmation["counts"].get("revolution_count")
        if expected is not None and int(expected) != len(publication_records):
            raise ValueError(f"{variant_id}: confirmation publication count mismatch")

    prepared: list[PreparedPublication] = []
    seen: set[tuple[int, str, int]] = set()
    for record_value in publication_records:
        if not isinstance(record_value, Mapping):
            raise ValueError(f"{variant_id}: publication record is not an object")
        record = dict(record_value)
        record_key = (
            int(record["seed"]),
            str(record["corruption_level"]),
            int(record["revolution_index"]),
        )
        if record_key in seen:
            raise ValueError(f"{variant_id}: duplicate publication record")
        seen.add(record_key)
        candidates = _source_candidates(
            source_entries, record, output_split, source_split
        )
        if len(candidates) != 1:
            raise ValueError(
                f"{variant_id}: publication does not resolve to one source entry"
            )
        entry = dict(candidates[0])
        snapshot_path = _safe_artifact(
            source_path.parent, entry["snapshot_path"], "snapshot_path"
        )
        snapshot_sha = _sha256(snapshot_path)
        if snapshot_sha != str(entry["snapshot_sha256"]):
            raise ValueError(f"{variant_id}: source snapshot hash mismatch")
        if record.get("snapshot_sha256") and snapshot_sha != str(
            record["snapshot_sha256"]
        ):
            raise ValueError(f"{variant_id}: confirmation snapshot hash mismatch")
        snapshot = read_snapshot(snapshot_path)
        input_fingerprint = snapshot_fingerprint(snapshot)
        expected_input = str(entry["input_fingerprint"])
        if input_fingerprint != expected_input:
            raise ValueError(f"{variant_id}: source snapshot input fingerprint mismatch")
        if _record_input_fingerprint(record) != expected_input:
            raise ValueError(f"{variant_id}: confirmation input fingerprint mismatch")
        if snapshot.target_count != target_count:
            raise ValueError(f"{variant_id}: snapshot target_count mismatch")

        publication_path = _safe_artifact(
            confirmation_path.parent,
            record["publication_path"],
            "publication_path",
        )
        actual_file_sha = _sha256(publication_path)
        expected_file_sha, expected_fingerprint = _publication_record_hashes(record)
        if expected_file_sha is not None and actual_file_sha != expected_file_sha:
            raise ValueError(f"{variant_id}: publication file hash mismatch")
        wrapper, raw_publication, publication = _read_publication_file(
            publication_path
        )
        actual_fingerprint = publication_fingerprint(publication)  # type: ignore[arg-type]
        embedded_fingerprint = wrapper.get("publication_fingerprint_sha256")
        if embedded_fingerprint and str(embedded_fingerprint) != actual_fingerprint:
            raise ValueError(f"{variant_id}: embedded publication fingerprint mismatch")
        if expected_fingerprint is not None and expected_fingerprint != actual_fingerprint:
            raise ValueError(f"{variant_id}: publication fingerprint mismatch")
        if publication.input_fingerprint != expected_input:
            raise ValueError(f"{variant_id}: publication consumed another snapshot")
        if (
            publication.seed != record_key[0]
            or publication.corruption_level != record_key[1]
            or publication.revolution_index != record_key[2]
            or snapshot.seed != record_key[0]
            or snapshot.corruption_level != record_key[1]
            or snapshot.revolution_index != record_key[2]
        ):
            raise ValueError(f"{variant_id}: publication scenario identity mismatch")
        if not math.isclose(
            publication.cutoff_timestamp,
            snapshot.cutoff_timestamp,
            abs_tol=1e-9,
        ):
            raise ValueError(f"{variant_id}: publication cutoff mismatch")
        if (
            publication.candidate_graph_fingerprint
            and snapshot.candidate_graph_fingerprint
            and publication.candidate_graph_fingerprint
            != snapshot.candidate_graph_fingerprint
        ):
            raise ValueError(f"{variant_id}: publication candidate graph mismatch")
        gpu_peak, gpu_available, gpu_source = _gpu_peak(
            record, wrapper, confirmation
        )
        prepared.append(
            PreparedPublication(
                variant_id=variant_id,
                target_count=target_count,
                output_split=output_split,
                source_manifest_path=source_path,
                source_manifest_sha256=source_sha,
                source_entry=entry,
                snapshot_path=snapshot_path,
                snapshot_sha256=snapshot_sha,
                snapshot=snapshot,
                confirmation_manifest_path=confirmation_path,
                confirmation_manifest_sha256=confirmation_sha,
                confirmation_record=record,
                publication_path=publication_path,
                publication_file_sha256=actual_file_sha,
                publication_fingerprint_sha256=actual_fingerprint,
                publication=publication,
                gpu_peak_memory_mb=gpu_peak,
                gpu_peak_memory_available=gpu_available,
                gpu_peak_memory_source=gpu_source,
            )
        )
    published_levels = {
        str(record["corruption_level"]) for record in publication_records
    }
    expected_source_split = source_split or (
        output_split if output_split != "offline" else None
    )
    expected_keys = {
        (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        for entry in source_entries
        if str(entry.get("corruption_level")) in published_levels
        and (
            expected_source_split is None
            or str(entry.get("split")) == expected_source_split
        )
    }
    if seen != expected_keys:
        raise ValueError(
            f"{variant_id}: online publication matrix is incomplete or foreign"
        )
    levels = sorted(
        {item.publication.corruption_level for item in prepared} - REPORT_LEVELS
    )
    prepared.sort(
        key=lambda item: (
            item.publication.seed,
            item.publication.corruption_level,
            item.publication.revolution_index,
        )
    )
    return PreparedVariant(
        variant_id=variant_id,
        target_count=target_count,
        output_split=output_split,
        source_manifest_path=source_path,
        source_manifest_sha256=source_sha,
        source_declared_hashes=_collect_declared_hashes(source),
        confirmation_manifest_path=confirmation_path,
        confirmation_manifest_sha256=confirmation_sha,
        confirmation_declared_hashes=_collect_declared_hashes(confirmation),
        publications=tuple(prepared),
        skipped_reporting_levels=tuple(levels),
    )


def _timing_and_switches(
    publications: Sequence[PreparedPublication],
) -> tuple[dict[tuple[str, int, str, int], float | None], dict[tuple[str, int, str, int], int]]:
    groups: dict[tuple[str, int, str], list[PreparedPublication]] = defaultdict(list)
    for item in publications:
        groups[(item.variant_id, item.publication.seed, item.publication.corruption_level)].append(item)
    first_confirmation: dict[tuple[str, int, str, int], float | None] = {}
    switches: dict[tuple[str, int, str, int], int] = {}
    for group in groups.values():
        group.sort(key=lambda item: item.publication.revolution_index)
        first_time: float | None = None
        previous: dict[str, str] = {}
        for item in group:
            publication = item.publication
            if first_time is None and publication.matches:
                explicit = next(
                    (
                        item.confirmation_record[name]
                        for name in (
                            "publication_time_s",
                            "first_confirmation_s",
                            "elapsed_s",
                        )
                        if item.confirmation_record.get(name) is not None
                    ),
                    None,
                )
                first_time = (
                    publication.cutoff_timestamp
                    if explicit is None
                    else _as_nonnegative_float(explicit, "publication_time_s")
                )
            first_confirmation[item.identity] = first_time
            current = _unique_bindings(publication)
            switches[item.identity] = sum(
                previous[track_a] != track_b
                for track_a, track_b in current.items()
                if track_a in previous
            )
            previous = current
    return first_confirmation, switches


def _score_prepared(
    variants: Sequence[PreparedVariant],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    publications = [item for variant in variants for item in variant.publications]
    first_confirmation, switches = _timing_and_switches(publications)
    rows: list[dict[str, Any]] = []
    variant_audits: list[dict[str, Any]] = []
    for variant in variants:
        publication_audits: list[dict[str, Any]] = []
        available_gpu_records = 0
        for item in variant.publications:
            entry = item.source_entry
            label_path = _safe_artifact(
                item.source_manifest_path.parent,
                entry["label_path"],
                "label_path",
            )
            labels = load_offline_labels(label_path, str(entry["label_sha256"]))
            actual_label_sha = _sha256(label_path)
            publication_audits.append(
                {
                    "seed": item.publication.seed,
                    "level": item.publication.corruption_level,
                    "revolution": item.publication.revolution_index,
                    "snapshot_path": str(item.snapshot_path),
                    "snapshot_sha256": item.snapshot_sha256,
                    "input_fingerprint": item.publication.input_fingerprint,
                    "publication_path": str(item.publication_path),
                    "publication_file_sha256": item.publication_file_sha256,
                    "publication_fingerprint_sha256": item.publication_fingerprint_sha256,
                    "label_path": str(label_path),
                    "label_sha256": actual_label_sha,
                }
            )
            if item.gpu_peak_memory_available:
                available_gpu_records += 1
            if item.publication.corruption_level not in REPORT_LEVELS:
                continue
            scored = score_publication(  # type: ignore[arg-type]
                item.publication, labels, item.snapshot
            )
            candidate_build, inference, assignment, end_to_end = _latencies(
                item.publication, item.snapshot
            )
            unique_correct = sum(
                int(group["correct_unique_match_count"])
                for group in scored.get("heading_groups", {}).values()
            )
            rows.append(
                {
                    "variant_id": item.variant_id,
                    "target_count": item.target_count,
                    "seed": item.publication.seed,
                    "split": item.output_split,
                    "level": item.publication.corruption_level,
                    "revolution": item.publication.revolution_index,
                    "match_count": int(scored["match_count"]),
                    "correct_count": int(scored["correct_match_count"]),
                    "false_count": int(scored["false_association_count"]),
                    "unique_correct_targets": unique_correct,
                    "candidate_opportunities": int(
                        scored["candidate_true_opportunity_count"]
                    ),
                    "candidate_true_retained": int(
                        scored["candidate_true_retained_count"]
                    ),
                    "candidate_edge_count": len(
                        item.snapshot.geometry_candidate_pairs
                    ),
                    "candidate_build_ms": candidate_build,
                    "inference_ms": inference,
                    "assignment_ms": assignment,
                    "end_to_end_ms": end_to_end,
                    "first_confirmation_s": first_confirmation[item.identity],
                    "relation_switch_count": switches[item.identity],
                    "one_to_one_violations": _one_to_one_violations(
                        item.publication
                    ),
                    "gpu_peak_memory_mb": item.gpu_peak_memory_mb,
                    "gpu_peak_memory_available": item.gpu_peak_memory_available,
                    "gpu_peak_memory_source": item.gpu_peak_memory_source,
                }
            )
        variant_audits.append(
            {
                "variant_id": variant.variant_id,
                "target_count": variant.target_count,
                "split": variant.output_split,
                "source_manifest": str(variant.source_manifest_path),
                "source_manifest_sha256": variant.source_manifest_sha256,
                "source_declared_hashes": dict(variant.source_declared_hashes),
                "confirmation_manifest": str(variant.confirmation_manifest_path),
                "confirmation_manifest_sha256": variant.confirmation_manifest_sha256,
                "confirmation_declared_hashes": dict(
                    variant.confirmation_declared_hashes
                ),
                "publication_count": len(variant.publications),
                "gpu_peak_memory_available_count": available_gpu_records,
                "gpu_peak_memory_missing_count": len(variant.publications)
                - available_gpu_records,
                "skipped_reporting_levels": list(
                    variant.skipped_reporting_levels
                ),
                "artifacts": publication_audits,
            }
        )
    rows.sort(
        key=lambda row: (
            row["variant_id"],
            row["target_count"],
            row["split"],
            row["seed"],
            row["level"],
            row["revolution"],
        )
    )
    return rows, variant_audits


def build_offline_score_rows(
    variant_spec: str | Path,
) -> dict[str, Any]:
    """Validate all online artifacts, then read labels and build report rows."""

    spec_path = Path(variant_spec).resolve()
    spec = _read_json_object(spec_path)
    raw_variants = spec.get("variants")
    if (
        not isinstance(raw_variants, list)
        or not raw_variants
        or any(not isinstance(item, Mapping) for item in raw_variants)
    ):
        raise ValueError("variant spec must contain a nonempty variants array")
    identifiers = [str(item.get("variant_id") or "") for item in raw_variants]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("variant spec contains duplicate variant_id values")

    # Phase 1: no label path is opened in this loop.
    prepared = tuple(
        _prepare_variant(spec_path.parent, item) for item in raw_variants
    )

    # Phase 2 starts only after every variant and publication passed phase 1.
    rows, variant_audits = _score_prepared(prepared)
    return {
        "schema_version": SCHEMA_VERSION,
        "variant_spec": str(spec_path),
        "variant_spec_sha256": _sha256(spec_path),
        "truth_used_online": False,
        "truth_scoring_performed": True,
        "labels_read_after_all_online_publications_validated": True,
        "online_publication_validation_complete": True,
        "row_count": len(rows),
        "variants": variant_audits,
        "rows": rows,
    }


def write_offline_score_rows(
    variant_spec: str | Path, output_path: str | Path
) -> Path:
    payload = build_offline_score_rows(variant_spec)
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(write_offline_score_rows(args.variant_spec, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
