"""Post-hoc V4.1 deterministic target-handover replay.

The replay consumes sealed V4 zero-phase snapshots and Track SuperGlue
publications.  It never changes those artifacts, never loads a learned
target-track model, and opens offline identity records only after all anonymous
handover publications have been written and validated.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import numpy as np

from dual_optical_target_track_gnn.contracts import (
    ConfirmedTrackPair,
    PAIR_PUBLICATION_ROUTE,
    PAIR_PUBLICATION_SCHEMA_VERSION,
    TargetHypothesis,
    TargetTrackPublication,
    online_pair_publication_fingerprint,
    validate_online_pair_publication,
)
from dual_optical_target_track_gnn.deterministic import (
    publish_with_confirmation,
    solve_deterministic_assignment,
)
from dual_optical_target_track_gnn.geometry import (
    CausalityError,
    GeometryFitError,
    WeightedFitConfig,
    form_target_hypothesis,
)
from dual_optical_target_track_gnn.graph import TargetTrackGate, build_camera_graphs

from .contracts import (
    BenchmarkProtocol,
    RevolutionSnapshot,
    benchmark_protocol_from_mapping,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
)
from .dataset import load_dataset_manifest, sha256_file


V41_OUTPUT_VERSION = "scale_funnel_v4_1_deterministic_handover"
V41_ONLINE_MANIFEST_SCHEMA = "dual-optical-v4.1-online-manifest-v1"
V41_PUBLICATION_SCHEMA = "dual-optical-v4.1-publication-v1"
V41_SCENARIO_SCHEMA = "dual-optical-v4.1-scenario-publication-v1"
V41_SUMMARY_SCHEMA = "dual-optical-v4.1-summary-v1"
V41_TRACKER_DIAGNOSTIC_SCHEMA = "dual-optical-v4.1-tracker-diagnostic-v1"
V41_ROUTE_NAME = "v41_deterministic_handover"
V4_BASELINE_ROUTE_NAME = "v4_track_superglue_baseline"
V4_SOURCE_ROUTE = "track_superglue"
V4_SOURCE_ROUTE_VERSION = "dual-optical-track-superglue-online-v1"
V41_COMPARISON_REVOLUTIONS = (5, 6)

_FORBIDDEN_ONLINE_MARKERS = (
    "truth",
    "actor",
    "label",
    "global_track_id",
)
_ONLINE_ENTRY_FIELDS = {
    "split",
    "seed",
    "corruption_level",
    "revolution_index",
    "snapshot_path",
    "snapshot_sha256",
    "input_fingerprint",
    "tracker_fingerprint",
    "source_publication_path",
    "source_publication_sha256",
    "candidate_graph_fingerprint",
    "source_model_fingerprint",
    "source_route_version",
}


def _read_object(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _signed_payload(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    signed = dict(payload)
    signed[field] = _canonical_sha256(payload)
    return signed


def _validate_signature(payload: Mapping[str, Any], field: str) -> None:
    unsigned = dict(payload)
    stored = str(unsigned.pop(field, ""))
    if not stored or stored != _canonical_sha256(unsigned):
        raise ValueError(f"{field} mismatch")


def _safe_artifact(root: Path, relative: object) -> Path:
    value = Path(str(relative))
    if value.is_absolute():
        raise ValueError("artifact path must be relative")
    root = root.resolve()
    resolved = (root / value).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("artifact path escapes its declared root") from error
    return resolved


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError as error:
        raise ValueError("artifact is outside its declared source root") from error


def _forbidden_online_location(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            name = str(key)
            location = f"{prefix}.{name}" if prefix else name
            lowered = name.lower()
            if any(marker in lowered for marker in _FORBIDDEN_ONLINE_MARKERS):
                return location
            found = _forbidden_online_location(nested, location)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            found = _forbidden_online_location(nested, f"{prefix}[{index}]")
            if found is not None:
                return found
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _FORBIDDEN_ONLINE_MARKERS):
            return prefix
    return None


def assert_online_anonymous(value: Any) -> None:
    location = _forbidden_online_location(value)
    if location is not None:
        raise ValueError(f"online payload contains identity-bearing content at {location}")


def _source_paths(source_root: Path) -> dict[str, Path]:
    return {
        "test_manifest": source_root / "dataset" / "test_manifest.json",
        "all_routes_freeze": (
            source_root / "dataset" / "freezes" / "all_routes_frozen.json"
        ),
        "route_freeze": (
            source_root
            / "dataset"
            / "freezes"
            / V4_SOURCE_ROUTE
            / "freeze_manifest.json"
        ),
        "publications": source_root / "results" / "publications",
        "tracker_calibration": (
            source_root
            / "dataset"
            / "freezes"
            / "shared_tracker_calibration.json"
        ),
    }


def _validate_route_freeze(
    route_freeze_path: Path,
    *,
    protocol: BenchmarkProtocol,
    all_routes_freeze_path: Path,
) -> dict[str, Any]:
    route_freeze = _read_object(route_freeze_path)
    if route_freeze.get("route_name") != V4_SOURCE_ROUTE:
        raise ValueError("V4.1 requires the frozen Track SuperGlue route")
    if route_freeze.get("route_version") != V4_SOURCE_ROUTE_VERSION:
        raise ValueError("source Track SuperGlue route version mismatch")
    if route_freeze.get("protocol_fingerprint_sha256") != protocol.fingerprint:
        raise ValueError("source route protocol mismatch")
    if int(route_freeze.get("target_count", -1)) != protocol.target_count:
        raise ValueError("source route target count mismatch")
    model_fingerprint = str(route_freeze.get("model_fingerprint_sha256") or "")
    if len(model_fingerprint) != 64:
        raise ValueError("source route model fingerprint is invalid")
    for name, expected_hash in route_freeze.get("artifact_sha256", {}).items():
        key = "weights" if name == "weights" else name
        value = route_freeze.get(key)
        if name == "training_summary" and isinstance(value, Mapping):
            value = route_freeze.get("training_summary_path")
        if not value:
            raise ValueError(f"source route freeze omits artifact {name}")
        artifact = _safe_artifact(route_freeze_path.parent, value)
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            raise ValueError(f"source route artifact changed: {name}")

    all_routes = _read_object(all_routes_freeze_path)
    if all_routes.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("all-route freeze protocol mismatch")
    if V4_SOURCE_ROUTE not in all_routes.get("active_routes", ()):
        raise ValueError("Track SuperGlue is absent from the V4 active routes")
    route_entry = all_routes.get("routes", {}).get(V4_SOURCE_ROUTE, {})
    if route_entry.get("freeze_manifest_sha256") != sha256_file(route_freeze_path):
        raise ValueError("all-route freeze references another Track SuperGlue model")
    return route_freeze


def _validate_source_publication(
    payload: Mapping[str, Any],
    snapshot: RevolutionSnapshot,
    *,
    model_fingerprint: str,
) -> None:
    assert_online_anonymous(payload)
    checks = {
        "route": payload.get("route_name") == V4_SOURCE_ROUTE,
        "route_version": payload.get("route_version") == V4_SOURCE_ROUTE_VERSION,
        "model": payload.get("model_fingerprint") == model_fingerprint,
        "seed": int(payload.get("seed", -1)) == snapshot.seed,
        "corruption": payload.get("corruption_level") == snapshot.corruption_level,
        "revolution": int(payload.get("revolution_index", -1))
        == snapshot.revolution_index,
        "input": payload.get("input_fingerprint") == snapshot_fingerprint(snapshot),
        "candidate_graph": payload.get("candidate_graph_fingerprint")
        == snapshot.candidate_graph_fingerprint,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise ValueError("source publication mismatch: " + ",".join(failed))
    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("source publication matches must be a list")
    camera_a, camera_b = snapshot.camera_ids
    tracks_a = {track.track_id for track in snapshot.tracks[camera_a]}
    tracks_b = {track.track_id for track in snapshot.tracks[camera_b]}
    left_ids: list[str] = []
    right_ids: list[str] = []
    for match in matches:
        if not isinstance(match, Mapping):
            raise ValueError("source publication match is malformed")
        left = str(match.get("track_a_id") or "")
        right = str(match.get("track_b_id") or "")
        if left not in tracks_a or right not in tracks_b:
            raise ValueError("source publication references a foreign local track")
        if str(match.get("decision_state")) not in {"tentative", "confirmed"}:
            raise ValueError("source publication decision state is invalid")
        score = float(match.get("score", float("nan")))
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("source publication score is invalid")
        left_ids.append(left)
        right_ids.append(right)
    if len(left_ids) != len(set(left_ids)) or len(right_ids) != len(set(right_ids)):
        raise ValueError("source publication violates one-to-one assignment")


def _wrap_source_publication(
    source: Mapping[str, Any],
    snapshot: RevolutionSnapshot,
    *,
    source_sha256: str,
) -> dict[str, Any]:
    """Bind a sealed SuperGlue publication to the neutral geometry contract."""

    payload: dict[str, Any] = {
        "schema_version": PAIR_PUBLICATION_SCHEMA_VERSION,
        "online_anonymous": True,
        "seed": snapshot.seed,
        "protocol_fingerprint": snapshot.protocol_fingerprint,
        "corruption_level": snapshot.corruption_level,
        "revolution_index": snapshot.revolution_index,
        "input_fingerprint": snapshot_fingerprint(snapshot),
        "candidate_graph_fingerprint": snapshot.candidate_graph_fingerprint,
        "route_name": PAIR_PUBLICATION_ROUTE,
        "source_route_name": V4_SOURCE_ROUTE,
        "source_route_version": str(source["route_version"]),
        "source_model_fingerprint": str(source["model_fingerprint"]),
        "source_publication_sha256": source_sha256,
        "matches": [
            {
                "track_a_id": str(match["track_a_id"]),
                "track_b_id": str(match["track_b_id"]),
                "rule_cost": float(np.clip(1.0 - float(match["score"]), 0.0, 2.0)),
                "decision_state": str(match["decision_state"]),
            }
            for match in source["matches"]
        ],
        "latency_ms": float(source.get("end_to_end_ms", 0.0)),
    }
    payload["publication_fingerprint"] = online_pair_publication_fingerprint(payload)
    validate_online_pair_publication(payload)
    return payload


def write_v41_online_manifest(
    source_root: str | Path,
    output_dir: str | Path,
) -> Path:
    """Create a physically identity-free, hash-bound V4.1 replay input."""

    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir).resolve()
    paths = _source_paths(source_root)
    full_manifest = load_dataset_manifest(
        paths["test_manifest"], validate_offline_labels=False
    )
    if full_manifest.get("phase") != "test":
        raise ValueError("V4.1 accepts a sealed V4 test manifest only")
    protocol = benchmark_protocol_from_mapping(full_manifest["protocol"])
    if not math.isclose(protocol.camera_b_scan_phase_offset_s, 0.0, abs_tol=1e-12):
        raise ValueError("V4.1 requires the V4 zero-phase scan protocol")
    route_freeze = _validate_route_freeze(
        paths["route_freeze"],
        protocol=protocol,
        all_routes_freeze_path=paths["all_routes_freeze"],
    )
    model_fingerprint = str(route_freeze["model_fingerprint_sha256"])
    entries: list[dict[str, Any]] = []
    for source_entry in sorted(
        full_manifest["entries"],
        key=lambda item: (
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        ),
    ):
        snapshot_path = _safe_artifact(
            paths["test_manifest"].parent, source_entry["snapshot_path"]
        )
        snapshot = read_snapshot(snapshot_path)
        publication_path = (
            paths["publications"]
            / str(snapshot.seed)
            / snapshot.corruption_level
            / f"revolution_{snapshot.revolution_index:02d}_{V4_SOURCE_ROUTE}.json"
        )
        if not publication_path.is_file():
            raise ValueError(f"missing V4 source publication: {publication_path}")
        publication = _read_object(publication_path)
        _validate_source_publication(
            publication, snapshot, model_fingerprint=model_fingerprint
        )
        entries.append(
            {
                "split": snapshot.split,
                "seed": snapshot.seed,
                "corruption_level": snapshot.corruption_level,
                "revolution_index": snapshot.revolution_index,
                "snapshot_path": _relative(snapshot_path, source_root),
                "snapshot_sha256": sha256_file(snapshot_path),
                "input_fingerprint": snapshot_fingerprint(snapshot),
                "tracker_fingerprint": snapshot.tracker_fingerprint,
                "source_publication_path": _relative(
                    publication_path, source_root
                ),
                "source_publication_sha256": sha256_file(publication_path),
                "candidate_graph_fingerprint": snapshot.candidate_graph_fingerprint,
                "source_model_fingerprint": model_fingerprint,
                "source_route_version": V4_SOURCE_ROUTE_VERSION,
            }
        )
    payload = {
        "schema_version": V41_ONLINE_MANIFEST_SCHEMA,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "online_only": True,
        "post_hoc_replay": True,
        "identity_fields_absent": True,
        "source_root": str(source_root),
        "source_manifest_path": _relative(paths["test_manifest"], source_root),
        "source_manifest_sha256": sha256_file(paths["test_manifest"]),
        "source_route_freeze_path": _relative(paths["route_freeze"], source_root),
        "source_route_freeze_sha256": sha256_file(paths["route_freeze"]),
        "source_all_routes_freeze_path": _relative(
            paths["all_routes_freeze"], source_root
        ),
        "source_all_routes_freeze_sha256": sha256_file(
            paths["all_routes_freeze"]
        ),
        "source_route_name": V4_SOURCE_ROUTE,
        "source_route_version": V4_SOURCE_ROUTE_VERSION,
        "source_model_fingerprint": model_fingerprint,
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "entry_count": len(entries),
        "entries": entries,
    }
    assert_online_anonymous(payload)
    path = output_dir / "online_manifest.json"
    write_json(path, _signed_payload(payload, "manifest_fingerprint"))
    validate_v41_online_manifest(path, validate_artifacts=True)
    return path


def validate_v41_online_manifest(
    path: str | Path,
    *,
    validate_artifacts: bool = True,
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = _read_object(path)
    assert_online_anonymous(payload)
    if payload.get("schema_version") != V41_ONLINE_MANIFEST_SCHEMA:
        raise ValueError("unsupported V4.1 online manifest schema")
    if (
        payload.get("diagnostic_only") is not True
        or payload.get("formal_use_allowed") is not False
        or payload.get("online_only") is not True
        or payload.get("post_hoc_replay") is not True
    ):
        raise ValueError("V4.1 online manifest grants an invalid evidence status")
    _validate_signature(payload, "manifest_fingerprint")
    protocol = benchmark_protocol_from_mapping(payload["protocol"])
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("V4.1 manifest protocol fingerprint mismatch")
    if not math.isclose(protocol.camera_b_scan_phase_offset_s, 0.0, abs_tol=1e-12):
        raise ValueError("V4.1 manifest is not a zero-phase V4 protocol")
    if int(payload.get("target_count", -1)) != protocol.target_count:
        raise ValueError("V4.1 manifest target count mismatch")
    source_root = Path(str(payload.get("source_root") or "")).resolve()
    source_manifest_path = _safe_artifact(
        source_root, payload.get("source_manifest_path")
    )
    route_freeze_path = _safe_artifact(
        source_root, payload.get("source_route_freeze_path")
    )
    all_routes_path = _safe_artifact(
        source_root, payload.get("source_all_routes_freeze_path")
    )
    entries = payload.get("entries")
    if not isinstance(entries, list) or int(payload.get("entry_count", -1)) != len(entries):
        raise ValueError("V4.1 manifest entry count is invalid")
    if any(set(entry) != _ONLINE_ENTRY_FIELDS for entry in entries):
        raise ValueError("V4.1 online entry exposes an unexpected field")
    keys = [
        (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        for entry in entries
    ]
    expected = {
        (seed, level, revolution)
        for seed in protocol.test_seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError("V4.1 online manifest does not cover the frozen test matrix")
    if not validate_artifacts:
        for entry in entries:
            _safe_artifact(source_root, entry["snapshot_path"])
            _safe_artifact(source_root, entry["source_publication_path"])
        return payload

    expected_hashes = {
        source_manifest_path: str(payload.get("source_manifest_sha256") or ""),
        route_freeze_path: str(payload.get("source_route_freeze_sha256") or ""),
        all_routes_path: str(payload.get("source_all_routes_freeze_sha256") or ""),
    }
    for artifact, expected_hash in expected_hashes.items():
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            raise ValueError("V4.1 source manifest or freeze hash mismatch")
    source_manifest = load_dataset_manifest(
        source_manifest_path, validate_offline_labels=False
    )
    if source_manifest.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("V4.1 source dataset protocol mismatch")
    route_freeze = _validate_route_freeze(
        route_freeze_path,
        protocol=protocol,
        all_routes_freeze_path=all_routes_path,
    )
    model_fingerprint = str(route_freeze["model_fingerprint_sha256"])
    for entry in entries:
        snapshot_path = _safe_artifact(source_root, entry["snapshot_path"])
        publication_path = _safe_artifact(
            source_root, entry["source_publication_path"]
        )
        if sha256_file(snapshot_path) != entry["snapshot_sha256"]:
            raise ValueError("V4.1 snapshot hash mismatch")
        if sha256_file(publication_path) != entry["source_publication_sha256"]:
            raise ValueError("V4.1 source publication hash mismatch")
        snapshot = read_snapshot(snapshot_path)
        if (
            snapshot.seed != int(entry["seed"])
            or snapshot.corruption_level != entry["corruption_level"]
            or snapshot.revolution_index != int(entry["revolution_index"])
            or snapshot.protocol_fingerprint != protocol.fingerprint
            or snapshot_fingerprint(snapshot) != entry["input_fingerprint"]
            or snapshot.tracker_fingerprint != entry["tracker_fingerprint"]
            or snapshot.candidate_graph_fingerprint
            != entry["candidate_graph_fingerprint"]
        ):
            raise ValueError("V4.1 online entry does not match its snapshot")
        if (
            entry["source_model_fingerprint"] != model_fingerprint
            or entry["source_route_version"] != V4_SOURCE_ROUTE_VERSION
        ):
            raise ValueError("V4.1 online entry source model mismatch")
        _validate_source_publication(
            _read_object(publication_path),
            snapshot,
            model_fingerprint=model_fingerprint,
        )
    return payload


def _hypothesis_id(
    *,
    seed: int,
    corruption_level: str,
    track_a_id: str,
    track_b_id: str,
) -> str:
    digest = _canonical_sha256(
        {
            "seed": seed,
            "corruption_level": corruption_level,
            "track_a_id": track_a_id,
            "track_b_id": track_b_id,
        }
    )
    return f"V41-H-{digest[:16]}"


def _hypotheses_for_revolution(
    *,
    current_revolution: int,
    snapshots: Mapping[int, RevolutionSnapshot],
    wrapped_publications: Mapping[int, Mapping[str, Any]],
    weighted_fit_config: WeightedFitConfig,
) -> tuple[tuple[TargetHypothesis, ...], dict[str, dict[str, Any]], Counter[str]]:
    """Create hypotheses one boundary earlier and use them for one revolution."""

    source_revolution = current_revolution - 2
    if source_revolution < 1:
        return (), {}, Counter()
    source_publication = wrapped_publications.get(source_revolution)
    if source_publication is None:
        return (), {}, Counter({"missing_source_publication": 1})
    registry = {
        str(source_publication["publication_fingerprint"]): source_publication
    }
    hypotheses: list[TargetHypothesis] = []
    sources: dict[str, dict[str, Any]] = {}
    failures: Counter[str] = Counter()
    for match in source_publication["matches"]:
        if str(match["decision_state"]) != "confirmed":
            continue
        track_a_id = str(match["track_a_id"])
        track_b_id = str(match["track_b_id"])
        hypothesis_id = _hypothesis_id(
            seed=int(source_publication["seed"]),
            corruption_level=str(source_publication["corruption_level"]),
            track_a_id=track_a_id,
            track_b_id=track_b_id,
        )
        try:
            pair = ConfirmedTrackPair.from_online_publication(
                source_publication, track_a_id, track_b_id
            )
            hypothesis = form_target_hypothesis(
                hypothesis_id,
                snapshots,
                (pair,),
                creation_revolution_index=current_revolution - 1,
                online_publications=registry,
                config=weighted_fit_config,
            )
        except (
            CausalityError,
            GeometryFitError,
            ValueError,
            np.linalg.LinAlgError,
        ) as error:
            failures[f"{type(error).__name__}:{error}"] += 1
            continue
        hypotheses.append(hypothesis)
        sources[hypothesis_id] = {
            "source_revolution_index": source_revolution,
            "track_a_id": track_a_id,
            "track_b_id": track_b_id,
            "source_publication_fingerprint": source_publication[
                "publication_fingerprint"
            ],
        }
    return (
        tuple(sorted(hypotheses, key=lambda item: item.hypothesis_id)),
        dict(sorted(sources.items())),
        failures,
    )


def _entry_groups(
    entries: Sequence[Mapping[str, Any]],
) -> dict[tuple[int, str], list[dict[str, Any]]]:
    groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        groups[(int(entry["seed"]), str(entry["corruption_level"]))].append(
            dict(entry)
        )
    for values in groups.values():
        values.sort(key=lambda item: int(item["revolution_index"]))
    return dict(groups)


def _process_scenario(
    entries: Sequence[Mapping[str, Any]],
    *,
    source_root: Path,
    protocol: BenchmarkProtocol,
) -> dict[str, Any]:
    if [int(entry["revolution_index"]) for entry in entries] != list(
        range(1, protocol.revolution_count + 1)
    ):
        raise ValueError("V4.1 scenario requires six ordered revolutions")
    snapshots: dict[int, RevolutionSnapshot] = {}
    wrapped_publications: dict[int, dict[str, Any]] = {}
    for entry in entries:
        snapshot = read_snapshot(_safe_artifact(source_root, entry["snapshot_path"]))
        source_path = _safe_artifact(source_root, entry["source_publication_path"])
        source = _read_object(source_path)
        _validate_source_publication(
            source,
            snapshot,
            model_fingerprint=str(entry["source_model_fingerprint"]),
        )
        snapshots[snapshot.revolution_index] = snapshot
        wrapped_publications[snapshot.revolution_index] = _wrap_source_publication(
            source,
            snapshot,
            source_sha256=str(entry["source_publication_sha256"]),
        )

    fit_config = WeightedFitConfig()
    gate = TargetTrackGate()
    publication_history: dict[str, list[TargetTrackPublication]] = defaultdict(list)
    revolutions: list[dict[str, Any]] = []
    total_failures: Counter[str] = Counter()
    duplicate_assignment_count = 0
    for revolution_index in range(1, protocol.revolution_count + 1):
        snapshot = snapshots[revolution_index]
        started = time.perf_counter()
        fit_started = time.perf_counter()
        hypotheses, hypothesis_sources, failures = _hypotheses_for_revolution(
            current_revolution=revolution_index,
            snapshots=snapshots,
            wrapped_publications=wrapped_publications,
            weighted_fit_config=fit_config,
        )
        fit_ms = (time.perf_counter() - fit_started) * 1000.0
        total_failures.update(failures)
        graph_started = time.perf_counter()
        graphs = build_camera_graphs(snapshot, hypotheses, gate=gate)
        graph_ms = (time.perf_counter() - graph_started) * 1000.0
        camera_payloads: dict[str, Any] = {}
        assignment_ms = 0.0
        for camera_id, graph in graphs.items():
            route_started = time.perf_counter()
            assignment = solve_deterministic_assignment(
                graph, unmatched_cost=gate.unmatched_cost
            )
            publications = publish_with_confirmation(
                graph,
                assignment,
                publication_history[camera_id],
            )
            publication_history[camera_id].extend(publications)
            route_ms = (time.perf_counter() - route_started) * 1000.0
            assignment_ms += route_ms
            duplicate_assignment_count += assignment.duplicate_assignment_count
            camera_payloads[camera_id] = {
                "whitelist_fingerprint": graph.whitelist_fingerprint,
                "hypothesis_ids": list(graph.hypothesis_ids),
                "track_ids": list(graph.track_ids),
                "edge_count": int(graph.edge_index.shape[1]),
                "rejection_counts": dict(graph.rejection_counts),
                "assignment_latency_ms": route_ms,
                "duplicate_assignment_count": assignment.duplicate_assignment_count,
                "unmatched_hypothesis_count": len(
                    assignment.unmatched_hypothesis_indices
                ),
                "unmatched_track_count": len(assignment.unmatched_track_indices),
                "publications": [item.to_dict() for item in publications],
            }
        total_ms = (time.perf_counter() - started) * 1000.0
        revolutions.append(
            {
                "revolution_index": revolution_index,
                "input_fingerprint": snapshot_fingerprint(snapshot),
                "source_revolution_index": (
                    revolution_index - 2 if revolution_index >= 3 else None
                ),
                "hypotheses": [item.to_dict() for item in hypotheses],
                "hypothesis_sources": hypothesis_sources,
                "hypothesis_failure_counts": dict(failures),
                "cameras": camera_payloads,
                "latency_ms": {
                    "weighted_los_fit": fit_ms,
                    "graph_build": graph_ms,
                    "hungarian_and_confirmation": assignment_ms,
                    "incremental_total": total_ms,
                },
            }
        )
    first = snapshots[1]
    payload = {
        "schema_version": V41_SCENARIO_SCHEMA,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "online_anonymous": True,
        "post_hoc_replay": True,
        "route_name": V41_ROUTE_NAME,
        "source_route_name": V4_SOURCE_ROUTE,
        "seed": first.seed,
        "split": first.split,
        "corruption_level": first.corruption_level,
        "target_count": first.target_count,
        "protocol_fingerprint": first.protocol_fingerprint,
        "weighted_fit_config": asdict(fit_config),
        "target_track_gate": asdict(gate),
        "hypothesis_lifetime": "one_next_revolution",
        "confirmation_policy": "two_of_latest_three_revolutions",
        "duplicate_assignment_count": duplicate_assignment_count,
        "hypothesis_failure_counts": dict(sorted(total_failures.items())),
        "revolutions": revolutions,
    }
    assert_online_anonymous(payload)
    return _signed_payload(payload, "scenario_fingerprint")


def _validate_scenario_publication(payload: Mapping[str, Any]) -> None:
    assert_online_anonymous(payload)
    if payload.get("schema_version") != V41_SCENARIO_SCHEMA:
        raise ValueError("unsupported V4.1 scenario publication schema")
    if (
        payload.get("diagnostic_only") is not True
        or payload.get("formal_use_allowed") is not False
        or payload.get("online_anonymous") is not True
        or payload.get("post_hoc_replay") is not True
        or payload.get("route_name") != V41_ROUTE_NAME
    ):
        raise ValueError("V4.1 scenario publication grants an invalid status")
    _validate_signature(payload, "scenario_fingerprint")
    for revolution in payload.get("revolutions", ()):
        current = int(revolution["revolution_index"])
        for hypothesis in revolution.get("hypotheses", ()):
            created = int(hypothesis["created_revolution_index"])
            if created >= current:
                raise ValueError("V4.1 publication contains future hypothesis evidence")
            last_observation = float(hypothesis["last_observation_timestamp"])
            for camera in revolution.get("cameras", {}).values():
                for publication in camera.get("publications", ()):
                    if publication["hypothesis_id"] == hypothesis["hypothesis_id"]:
                        if int(publication["revolution_index"]) != current:
                            raise ValueError("V4.1 publication revolution mismatch")
            for pair in hypothesis.get("confirmed_pairs", ()):
                if int(pair["revolution_index"]) >= created:
                    raise ValueError("V4.1 publication reuses current or future evidence")
            if not math.isfinite(last_observation):
                raise ValueError("V4.1 hypothesis observation time is invalid")


def write_v41_publications(
    online_manifest_path: str | Path,
    output_dir: str | Path,
) -> Path:
    online_manifest_path = Path(online_manifest_path).resolve()
    online = validate_v41_online_manifest(
        online_manifest_path, validate_artifacts=True
    )
    output_dir = Path(output_dir).resolve()
    source_root = Path(str(online["source_root"])).resolve()
    scenario_entries: list[dict[str, Any]] = []
    for (seed, corruption_level), entries in sorted(
        _entry_groups(online["entries"]).items()
    ):
        payload = _process_scenario(
            entries,
            source_root=source_root,
            protocol=benchmark_protocol_from_mapping(online["protocol"]),
        )
        _validate_scenario_publication(payload)
        scenario_path = (
            output_dir
            / "publications"
            / str(seed)
            / corruption_level
            / "v41_deterministic_handover.json"
        )
        write_json(scenario_path, payload)
        scenario_entries.append(
            {
                "seed": seed,
                "corruption_level": corruption_level,
                "publication_path": _relative(scenario_path, output_dir),
                "publication_sha256": sha256_file(scenario_path),
                "scenario_fingerprint": payload["scenario_fingerprint"],
            }
        )
    payload = {
        "schema_version": V41_PUBLICATION_SCHEMA,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "online_anonymous": True,
        "post_hoc_replay": True,
        "route_name": V41_ROUTE_NAME,
        "source_route_name": V4_SOURCE_ROUTE,
        "online_manifest_path": _relative(online_manifest_path, output_dir),
        "online_manifest_sha256": sha256_file(online_manifest_path),
        "online_manifest_fingerprint": online["manifest_fingerprint"],
        "protocol_fingerprint": online["protocol_fingerprint"],
        "target_count": online["target_count"],
        "scenario_count": len(scenario_entries),
        "scenarios": scenario_entries,
    }
    assert_online_anonymous(payload)
    path = output_dir / "publication_manifest.json"
    write_json(path, _signed_payload(payload, "publication_manifest_fingerprint"))
    validate_v41_publication_manifest(
        path, expected_online_manifest=online_manifest_path
    )
    return path


def validate_v41_publication_manifest(
    path: str | Path,
    *,
    expected_online_manifest: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = _read_object(path)
    assert_online_anonymous(payload)
    if payload.get("schema_version") != V41_PUBLICATION_SCHEMA:
        raise ValueError("unsupported V4.1 publication manifest schema")
    if (
        payload.get("diagnostic_only") is not True
        or payload.get("formal_use_allowed") is not False
        or payload.get("online_anonymous") is not True
        or payload.get("post_hoc_replay") is not True
    ):
        raise ValueError("V4.1 publication manifest grants an invalid evidence status")
    _validate_signature(payload, "publication_manifest_fingerprint")
    root = path.parent
    online_path = _safe_artifact(root, payload["online_manifest_path"])
    if expected_online_manifest is not None and online_path != Path(
        expected_online_manifest
    ).resolve():
        raise ValueError("V4.1 publication manifest references another online input")
    online = validate_v41_online_manifest(online_path, validate_artifacts=True)
    if (
        sha256_file(online_path) != payload.get("online_manifest_sha256")
        or online.get("manifest_fingerprint")
        != payload.get("online_manifest_fingerprint")
        or online.get("protocol_fingerprint") != payload.get("protocol_fingerprint")
    ):
        raise ValueError("V4.1 publication manifest online input hash mismatch")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != int(
        payload.get("scenario_count", -1)
    ):
        raise ValueError("V4.1 publication scenario count mismatch")
    for entry in scenarios:
        scenario_path = _safe_artifact(root, entry["publication_path"])
        if sha256_file(scenario_path) != entry["publication_sha256"]:
            raise ValueError("V4.1 scenario publication hash mismatch")
        scenario = _read_object(scenario_path)
        _validate_scenario_publication(scenario)
        if (
            scenario["scenario_fingerprint"] != entry["scenario_fingerprint"]
            or int(scenario["seed"]) != int(entry["seed"])
            or scenario["corruption_level"] != entry["corruption_level"]
            or scenario["protocol_fingerprint"] != online["protocol_fingerprint"]
        ):
            raise ValueError("V4.1 scenario publication provenance mismatch")
    return payload


def _dominant_identity(raw_counts: Mapping[str, Any]) -> str | None:
    ranked = sorted(
        ((int(count), str(identity)) for identity, count in raw_counts.items()),
        reverse=True,
    )
    if not ranked or ranked[0][1].startswith("FA-"):
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _load_scoring_inputs(
    online: Mapping[str, Any],
) -> tuple[dict[tuple[int, str, int], dict[str, Any]], dict[tuple[int, str, int], dict[str, Any]]]:
    source_root = Path(str(online["source_root"])).resolve()
    manifest_path = _safe_artifact(source_root, online["source_manifest_path"])
    full = load_dataset_manifest(manifest_path, validate_offline_labels=True)
    labels: dict[tuple[int, str, int], dict[str, Any]] = {}
    source_publications: dict[tuple[int, str, int], dict[str, Any]] = {}
    for entry in full["entries"]:
        key = (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        label_path = _safe_artifact(manifest_path.parent, entry["label_path"])
        if sha256_file(label_path) != entry["label_sha256"]:
            raise ValueError("offline scoring identity file hash mismatch")
        label = _read_object(label_path)
        if label.get("offline_truth_only") is not True:
            raise ValueError("scoring identity file is not offline-only")
        labels[key] = label
    for entry in online["entries"]:
        key = (
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        source_publications[key] = _read_object(
            _safe_artifact(source_root, entry["source_publication_path"])
        )
    return labels, source_publications


def _score_baseline(
    publication: Mapping[str, Any],
    label: Mapping[str, Any],
    *,
    target_count: int,
) -> dict[str, Any]:
    track_counts = label["track_truth_counts"]
    selected = []
    correct_identities = []
    for match in publication.get("matches", ()):
        if str(match.get("decision_state")) != "confirmed":
            continue
        identity_a = _dominant_identity(
            track_counts.get(str(match["track_a_id"]), {})
        )
        identity_b = _dominant_identity(
            track_counts.get(str(match["track_b_id"]), {})
        )
        selected.append((identity_a, identity_b))
        if identity_a is not None and identity_a == identity_b:
            correct_identities.append(identity_a)
    unique_correct = set(correct_identities)
    false_count = len(selected) - len(correct_identities)
    duplicate_count = len(correct_identities) - len(unique_correct)
    return {
        "selected_count": len(selected),
        "correct_count": len(correct_identities),
        "correct_unique_count": len(unique_correct),
        "false_count": false_count,
        "duplicate_identity_count": duplicate_count,
        "coverage": len(unique_correct) / max(target_count, 1),
        "false_opportunity_rate": false_count / max(target_count, 1),
        "precision": len(correct_identities) / max(len(selected), 1),
        "latency_ms": float(publication.get("end_to_end_ms", 0.0)),
    }


def _hypothesis_identity(
    source: Mapping[str, Any],
    source_label: Mapping[str, Any],
) -> str | None:
    track_counts = source_label["track_truth_counts"]
    identity_a = _dominant_identity(
        track_counts.get(str(source["track_a_id"]), {})
    )
    identity_b = _dominant_identity(
        track_counts.get(str(source["track_b_id"]), {})
    )
    return identity_a if identity_a is not None and identity_a == identity_b else None


def _score_handover(
    revolution: Mapping[str, Any],
    *,
    labels: Mapping[tuple[int, str, int], Mapping[str, Any]],
    seed: int,
    corruption_level: str,
    target_count: int,
) -> dict[str, Any]:
    current_revolution = int(revolution["revolution_index"])
    current_label = labels[(seed, corruption_level, current_revolution)]
    track_counts = current_label["track_truth_counts"]
    camera_ids = sorted(revolution.get("cameras", {}))
    if len(camera_ids) != 2:
        raise ValueError("V4.1 scoring requires two camera publications")
    confirmed_by_camera: dict[str, dict[str, str]] = {}
    tentative_count = 0
    for camera_id in camera_ids:
        confirmed: dict[str, str] = {}
        for publication in revolution["cameras"][camera_id].get("publications", ()):
            if publication["decision_state"] == "tentative":
                tentative_count += 1
            if publication["decision_state"] != "confirmed":
                continue
            local_track_id = publication.get("local_track_id")
            if local_track_id is not None:
                confirmed[str(publication["hypothesis_id"])] = str(local_track_id)
        confirmed_by_camera[camera_id] = confirmed
    common_hypotheses = set(confirmed_by_camera[camera_ids[0]]) & set(
        confirmed_by_camera[camera_ids[1]]
    )
    correct_identities: list[str] = []
    false_count = 0
    unresolved_source_count = 0
    for hypothesis_id in sorted(common_hypotheses):
        source = revolution.get("hypothesis_sources", {}).get(hypothesis_id)
        if not isinstance(source, Mapping):
            false_count += 1
            continue
        source_revolution = int(source["source_revolution_index"])
        source_label = labels[(seed, corruption_level, source_revolution)]
        expected_identity = _hypothesis_identity(source, source_label)
        identity_a = _dominant_identity(
            track_counts.get(
                confirmed_by_camera[camera_ids[0]][hypothesis_id], {}
            )
        )
        identity_b = _dominant_identity(
            track_counts.get(
                confirmed_by_camera[camera_ids[1]][hypothesis_id], {}
            )
        )
        if expected_identity is None:
            unresolved_source_count += 1
        if (
            expected_identity is not None
            and identity_a == expected_identity
            and identity_b == expected_identity
        ):
            correct_identities.append(expected_identity)
        else:
            false_count += 1
    unique_correct = set(correct_identities)
    latency = float(revolution.get("latency_ms", {}).get("incremental_total", 0.0))
    duplicate_assignments = sum(
        int(camera.get("duplicate_assignment_count", 0))
        for camera in revolution.get("cameras", {}).values()
    )
    return {
        "hypothesis_count": len(revolution.get("hypotheses", ())),
        "fit_failure_count": sum(
            int(value)
            for value in revolution.get("hypothesis_failure_counts", {}).values()
        ),
        "candidate_edge_count": sum(
            int(camera.get("edge_count", 0))
            for camera in revolution.get("cameras", {}).values()
        ),
        "tentative_publication_count": tentative_count,
        "both_camera_confirmed_count": len(common_hypotheses),
        "correct_count": len(correct_identities),
        "correct_unique_count": len(unique_correct),
        "false_count": false_count,
        "unresolved_source_count": unresolved_source_count,
        "duplicate_identity_count": len(correct_identities) - len(unique_correct),
        "duplicate_assignment_count": duplicate_assignments,
        "coverage": len(unique_correct) / max(target_count, 1),
        "false_opportunity_rate": false_count / max(target_count, 1),
        "precision": len(correct_identities) / max(len(common_hypotheses), 1),
        "latency_ms": latency,
        "latency_breakdown_ms": dict(revolution.get("latency_ms", {})),
        "rejection_counts": {
            camera_id: dict(
                revolution["cameras"][camera_id].get("rejection_counts", {})
            )
            for camera_id in camera_ids
        },
    }


def _paired_bootstrap_ci(
    paired_deltas: Sequence[float],
    *,
    iterations: int = 4000,
    seed: int = 20260815,
) -> tuple[float, float]:
    values = np.asarray(paired_deltas, dtype=float)
    if len(values) == 0:
        return 0.0, 0.0
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(iterations, len(values)), replace=True)
    means = np.mean(samples, axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def classify_v41_diagnostic(
    *,
    coverage_delta: float,
    coverage_delta_ci95: Sequence[float],
    false_opportunity_rate_delta: float,
    latency_p95_ms: float,
    safety_violation_count: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if safety_violation_count:
        reasons.append("safety_or_causality_violation")
    if latency_p95_ms > 1000.0:
        reasons.append("incremental_latency_p95_exceeded_1000ms")
    if false_opportunity_rate_delta > 0.005:
        reasons.append("false_opportunity_rate_increased_over_0.5pp")
    if coverage_delta < -0.005 or float(coverage_delta_ci95[0]) < -0.02:
        reasons.append("coverage_regression")
    if reasons:
        return "diagnostic_rejected", reasons
    if coverage_delta >= 0.02 and float(coverage_delta_ci95[0]) >= 0.0:
        return "diagnostic_improved", []
    return "diagnostic_neutral", ["coverage_gain_below_2pp"]


def score_v41_publications(
    publication_manifest_path: str | Path,
    output_dir: str | Path,
) -> Path:
    publication_manifest_path = Path(publication_manifest_path).resolve()
    publication_manifest = validate_v41_publication_manifest(
        publication_manifest_path
    )
    output_dir = Path(output_dir).resolve()
    online_path = _safe_artifact(
        publication_manifest_path.parent,
        publication_manifest["online_manifest_path"],
    )
    online = validate_v41_online_manifest(online_path, validate_artifacts=True)
    labels, source_publications = _load_scoring_inputs(online)
    rows: list[dict[str, Any]] = []
    scenario_deltas: dict[tuple[int, str], list[float]] = defaultdict(list)
    for scenario_entry in publication_manifest["scenarios"]:
        scenario = _read_object(
            _safe_artifact(
                publication_manifest_path.parent,
                scenario_entry["publication_path"],
            )
        )
        seed = int(scenario["seed"])
        corruption_level = str(scenario["corruption_level"])
        target_count = int(scenario["target_count"])
        for revolution in scenario["revolutions"]:
            revolution_index = int(revolution["revolution_index"])
            key = (seed, corruption_level, revolution_index)
            baseline = _score_baseline(
                source_publications[key],
                labels[key],
                target_count=target_count,
            )
            handover = _score_handover(
                revolution,
                labels=labels,
                seed=seed,
                corruption_level=corruption_level,
                target_count=target_count,
            )
            eligible = revolution_index in V41_COMPARISON_REVOLUTIONS
            if eligible:
                scenario_deltas[(seed, corruption_level)].append(
                    handover["coverage"] - baseline["coverage"]
                )
            rows.append(
                {
                    "seed": seed,
                    "corruption_level": corruption_level,
                    "revolution_index": revolution_index,
                    "comparison_eligible": eligible,
                    V4_BASELINE_ROUTE_NAME: baseline,
                    V41_ROUTE_NAME: handover,
                    "coverage_delta": handover["coverage"] - baseline["coverage"],
                    "false_opportunity_rate_delta": (
                        handover["false_opportunity_rate"]
                        - baseline["false_opportunity_rate"]
                    ),
                }
            )
    eligible_rows = [row for row in rows if row["comparison_eligible"]]
    baseline_coverage = float(
        np.mean(
            [row[V4_BASELINE_ROUTE_NAME]["coverage"] for row in eligible_rows]
        )
    )
    handover_coverage = float(
        np.mean([row[V41_ROUTE_NAME]["coverage"] for row in eligible_rows])
    )
    baseline_false_rate = float(
        np.mean(
            [
                row[V4_BASELINE_ROUTE_NAME]["false_opportunity_rate"]
                for row in eligible_rows
            ]
        )
    )
    handover_false_rate = float(
        np.mean(
            [
                row[V41_ROUTE_NAME]["false_opportunity_rate"]
                for row in eligible_rows
            ]
        )
    )
    scenario_mean_deltas = [
        float(np.mean(values)) for values in scenario_deltas.values()
    ]
    coverage_ci = _paired_bootstrap_ci(scenario_mean_deltas)
    latency_values = [row[V41_ROUTE_NAME]["latency_ms"] for row in eligible_rows]
    safety_violations = sum(
        row[V41_ROUTE_NAME]["duplicate_assignment_count"]
        + row[V41_ROUTE_NAME]["duplicate_identity_count"]
        for row in eligible_rows
    )
    status, reasons = classify_v41_diagnostic(
        coverage_delta=handover_coverage - baseline_coverage,
        coverage_delta_ci95=coverage_ci,
        false_opportunity_rate_delta=handover_false_rate - baseline_false_rate,
        latency_p95_ms=float(np.percentile(latency_values, 95)),
        safety_violation_count=safety_violations,
    )
    by_corruption: dict[str, Any] = {}
    for level in benchmark_protocol_from_mapping(online["protocol"]).corruption_levels:
        selected = [row for row in eligible_rows if row["corruption_level"] == level]
        by_corruption[level] = {
            "sample_count": len(selected),
            "baseline_coverage": float(
                np.mean([row[V4_BASELINE_ROUTE_NAME]["coverage"] for row in selected])
            ),
            "handover_coverage": float(
                np.mean([row[V41_ROUTE_NAME]["coverage"] for row in selected])
            ),
            "handover_precision": float(
                np.mean([row[V41_ROUTE_NAME]["precision"] for row in selected])
            ),
        }
    payload = {
        "schema_version": V41_SUMMARY_SCHEMA,
        "evidence_status": status,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "post_hoc_replay": True,
        "test_set_previously_observed": True,
        "source_publication_manifest": str(publication_manifest_path),
        "source_publication_manifest_sha256": sha256_file(
            publication_manifest_path
        ),
        "target_count": int(online["target_count"]),
        "protocol_fingerprint": online["protocol_fingerprint"],
        "comparison_revolutions": list(V41_COMPARISON_REVOLUTIONS),
        "comparison_sample_count": len(eligible_rows),
        "scenario_pair_count": len(scenario_mean_deltas),
        "routes": {
            V4_BASELINE_ROUTE_NAME: {
                "coverage": baseline_coverage,
                "false_opportunity_rate": baseline_false_rate,
                "latency_p95_ms": float(
                    np.percentile(
                        [
                            row[V4_BASELINE_ROUTE_NAME]["latency_ms"]
                            for row in eligible_rows
                        ],
                        95,
                    )
                ),
            },
            V41_ROUTE_NAME: {
                "coverage": handover_coverage,
                "false_opportunity_rate": handover_false_rate,
                "latency_p50_ms": float(np.percentile(latency_values, 50)),
                "latency_p95_ms": float(np.percentile(latency_values, 95)),
                "fit_hypothesis_count": int(
                    sum(
                        row[V41_ROUTE_NAME]["hypothesis_count"]
                        for row in eligible_rows
                    )
                ),
                "fit_failure_count": int(
                    sum(
                        row[V41_ROUTE_NAME]["fit_failure_count"]
                        for row in eligible_rows
                    )
                ),
                "candidate_edge_count": int(
                    sum(
                        row[V41_ROUTE_NAME]["candidate_edge_count"]
                        for row in eligible_rows
                    )
                ),
                "both_camera_confirmed_count": int(
                    sum(
                        row[V41_ROUTE_NAME]["both_camera_confirmed_count"]
                        for row in eligible_rows
                    )
                ),
            },
        },
        "paired_comparison": {
            "coverage_delta": handover_coverage - baseline_coverage,
            "coverage_delta_ci95": list(coverage_ci),
            "false_opportunity_rate_delta": handover_false_rate
            - baseline_false_rate,
            "safety_violation_count": safety_violations,
            "decision_reasons": reasons,
        },
        "acceptance": {
            "improvement_minimum_coverage_delta": 0.02,
            "improvement_ci_lower_minimum": 0.0,
            "maximum_false_opportunity_rate_delta": 0.005,
            "maximum_incremental_latency_p95_ms": 1000.0,
            "formal_promotion_allowed": False,
        },
        "by_corruption": by_corruption,
        "rows": rows,
    }
    path = output_dir / "summary.json"
    write_json(path, payload)
    return path


def write_v41_tracker_diagnostic(
    source_root: str | Path,
    output_dir: str | Path,
) -> Path:
    """Record the 40-target V4 stop without opening or inventing a test set."""

    source_root = Path(source_root).resolve()
    output_dir = Path(output_dir).resolve()
    paths = _source_paths(source_root)
    evidence_path = paths["tracker_calibration"]
    evidence_hash = sha256_file(evidence_path)
    evidence = _read_object(evidence_path)
    acceptance = evidence.get("acceptance")
    if not isinstance(acceptance, Mapping) or acceptance.get("accepted") is not False:
        raise ValueError("tracker diagnostic requires failed V4 calibration evidence")
    if evidence.get("test_data_accessed") is not False:
        raise ValueError("40-target V4 tracker evidence opened reserved test data")
    if paths["test_manifest"].exists():
        raise ValueError("40-target V4 diagnostic unexpectedly has a test manifest")
    selected = evidence.get("selected_validation_metrics", {})
    payload = {
        "schema_version": V41_TRACKER_DIAGNOSTIC_SCHEMA,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "handover_executed": False,
        "test_data_accessed": False,
        "status": "blocked_at_v4_tracker_freeze",
        "target_count": 40,
        "protocol_fingerprint": evidence.get("protocol_fingerprint"),
        "source_evidence": str(evidence_path),
        "source_evidence_sha256": evidence_hash,
        "candidate_count": int(evidence.get("candidate_count", 0)),
        "accepted_candidate_count": int(evidence.get("accepted_candidate_count", 0)),
        "failure_reasons": list(acceptance.get("failure_reasons", ())),
        "acceptance_checks": dict(acceptance.get("checks", {})),
        "acceptance_thresholds": dict(acceptance.get("thresholds", {})),
        "selected_tracker_fingerprint": evidence.get(
            "selected_tracker_fingerprint"
        ),
        "selected_validation_metrics": dict(selected),
    }
    path = output_dir / "tracker_diagnostic.json"
    write_json(path, payload)
    if sha256_file(evidence_path) != evidence_hash:
        path.unlink(missing_ok=True)
        raise RuntimeError("40-target calibration evidence changed during audit")
    return path


def _write_v41_figures(summary: Mapping[str, Any], figure_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure_dir.mkdir(parents=True, exist_ok=True)
    levels = list(summary["by_corruption"])
    baseline = [summary["by_corruption"][level]["baseline_coverage"] for level in levels]
    handover = [summary["by_corruption"][level]["handover_coverage"] for level in levels]
    x = np.arange(len(levels))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    ax.bar(x - width / 2, baseline, width, label="V4 SuperGlue baseline", color="#4472c4")
    ax.bar(x + width / 2, handover, width, label="V4.1 deterministic handover", color="#70ad47")
    ax.set_xticks(x, levels)
    ax.set_ylim(0.0, max(0.1, max(baseline + handover, default=0.0) * 1.2))
    ax.set_ylabel("Target coverage")
    ax.set_title("Eligible revolutions 5-6: coverage by corruption")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    coverage_path = figure_dir / "01_coverage_comparison.png"
    fig.savefig(coverage_path, dpi=180)
    plt.close(fig)

    route = summary["routes"][V41_ROUTE_NAME]
    funnel_names = ["Fitted hypotheses", "Candidate edges", "Both-camera confirmed"]
    funnel_values = [
        route["fit_hypothesis_count"],
        route["candidate_edge_count"],
        route["both_camera_confirmed_count"],
    ]
    fig, ax = plt.subplots(figsize=(8.6, 4.8))
    bars = ax.barh(funnel_names, funnel_values, color=["#5b9bd5", "#ed7d31", "#70ad47"])
    ax.bar_label(bars, padding=4)
    ax.set_xlabel("Count across eligible replay rows")
    ax.set_title("V4.1 deterministic handover funnel")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    funnel_path = figure_dir / "02_handover_funnel.png"
    fig.savefig(funnel_path, dpi=180)
    plt.close(fig)
    return [coverage_path, funnel_path]


def write_v41_report(output_root: str | Path) -> Path:
    output_root = Path(output_root).resolve()
    summary_path = output_root / "targets_020" / "summary.json"
    tracker_path = output_root / "targets_040" / "tracker_diagnostic.json"
    if not summary_path.is_file():
        raise ValueError("20-target V4.1 summary is required before report generation")
    summary = _read_object(summary_path)
    figures = _write_v41_figures(summary, output_root / "figures")
    tracker = _read_object(tracker_path) if tracker_path.is_file() else None
    baseline = summary["routes"][V4_BASELINE_ROUTE_NAME]
    handover = summary["routes"][V41_ROUTE_NAME]
    comparison = summary["paired_comparison"]
    status_cn = {
        "diagnostic_improved": "诊断性改善",
        "diagnostic_neutral": "诊断性持平",
        "diagnostic_rejected": "诊断性未通过",
    }.get(summary["evidence_status"], summary["evidence_status"])
    reason_names = {
        "coverage_regression": "目标覆盖明显下降",
        "safety_or_causality_violation": "存在安全或因果约束违规",
        "incremental_latency_p95_exceeded_1000ms": "增量处理时延超过1000毫秒",
        "false_opportunity_rate_increased_over_0.5pp": "虚假机会率增加超过0.5个百分点",
        "coverage_gain_below_2pp": "目标覆盖增益不足2个百分点",
    }
    decision_reason_text = "、".join(
        reason_names.get(reason, reason)
        for reason in comparison["decision_reasons"]
    ) or "全部改善门槛满足"
    lines = [
        "# V4.1确定性目标交接离线回放报告",
        "",
        "## 1. 结论",
        "",
        f"本轮判定为**{status_cn}**。该结果来自已经查看过的V4二十目标保留集，属于事后诊断，不能转为新的正式验收证据。V4原始匿名快照、航迹级SuperGlue发布和冻结模型均保持只读。",
        "",
        f"在可比较的第5至第6圈，V4航迹级SuperGlue基线目标覆盖为{baseline['coverage']:.4f}，V4.1确定性交接覆盖为{handover['coverage']:.4f}，差值为{comparison['coverage_delta']:+.4f}。配对自助法95%区间为[{comparison['coverage_delta_ci95'][0]:+.4f}, {comparison['coverage_delta_ci95'][1]:+.4f}]。确定性交接增量处理时延P95为{handover['latency_p95_ms']:.2f}毫秒。",
        "",
        "## 2. 试验边界",
        "",
        "本轮不重新启动AirSim，不改变两站零相位连续周扫设置，不训练新模型，也不使用V5的一百八十度扫描相位差。输入为V4封存的二十目标匿名快照和航迹级SuperGlue发布。测试包含5个种子、4档漏检与虚警条件、每个场景6圈。确定性交接只在第5至第6圈具备完整的因果证据，因此统计比较限定在40个逐圈样本。",
        "",
        "在线回放清单和交接发布中没有目标真实身份、AirSim实体名称、离线评分路径或中心全局编号。每个输入快照、源发布、模型冻结和输出发布均校验文件哈希、协议指纹、种子、圈次和候选图指纹。离线身份文件在全部匿名结果写入并复验后才打开。",
        "",
        "## 3. 算法流程",
        "",
        "```text",
        "V4航迹级SuperGlue确认的双站航迹对",
        "        ↓  来源文件、协议、输入和模型哈希复验",
        "两站异步视线加权拟合",
        "        ↓  位置、速度和六维协方差",
        "仅向下一圈外推并重投影到A、B两站",
        "        ↓  方位残差、协方差归一化残差、角速度和时效硬门控",
        "规则代价与带未匹配项的匈牙利一一分配",
        "        ↓",
        "最近三圈中两次一致后确认",
        "        ↓",
        "全部匿名发布封存后离线评分",
        "```",
        "",
        "目标假设使用源确认圈以前的观测建立，在下一处理边界生成，只允许服务一个后续圈。用于拟合的样本不能再次作为新证据。病态交会、预测过期、残差或协方差超限、来源不一致时均保持未匹配。V4.1只调用规则代价和匈牙利求解，不导入冻结图网络权重，也不允许扩大几何白名单。",
        "",
        "## 4. 二十目标结果",
        "",
        "| 指标 | V4基线 | V4.1确定性交接 |",
        "| --- | ---: | ---: |",
        f"| 第5至第6圈平均覆盖 | {baseline['coverage']:.4f} | {handover['coverage']:.4f} |",
        f"| 虚假机会率 | {baseline['false_opportunity_rate']:.4f} | {handover['false_opportunity_rate']:.4f} |",
        f"| P95处理时延 | {baseline['latency_p95_ms']:.2f} ms | {handover['latency_p95_ms']:.2f} ms |",
        f"| 成功拟合目标假设 | - | {handover['fit_hypothesis_count']} |",
        f"| 拟合失败 | - | {handover['fit_failure_count']} |",
        f"| 几何白名单候选边 | - | {handover['candidate_edge_count']} |",
        f"| 双相机均确认 | - | {handover['both_camera_confirmed_count']} |",
        "",
        f"![覆盖比较]({figures[0].relative_to(output_root).as_posix()})",
        "",
        f"![交接漏斗]({figures[1].relative_to(output_root).as_posix()})",
        "",
        "覆盖指标要求同一匿名目标假设在A、B两站都达到两圈一致确认，并在离线评分时证明两条当前局部航迹与源确认对属于同一目标。暂定关系不计入覆盖。这个口径比单圈双站配准更严格，结果不能与V4全六圈宏平均召回直接混用。",
        "",
        "## 5. 四十目标状态",
        "",
    ]
    if tracker is None:
        lines.extend(
            [
                "四十目标诊断尚未写入。本轮报告不得推断四十目标交接性能。",
                "",
            ]
        )
    else:
        reasons = "、".join(tracker["failure_reasons"])
        lines.extend(
            [
                f"四十目标仍停在V4共享单站跟踪器冻结阶段。25组候选中通过数量为{tracker['accepted_candidate_count']}，失败项为{reasons}。因此未生成四十目标保留测试清单，也未运行SuperGlue或V4.1确定性交接。",
                "",
                "该停止点保持原有失败关闭规则。四十目标不能引用二十目标交接结果，也不能使用标定数据代替保留测试。",
                "",
            ]
        )
    lines.extend(
        [
            "## 6. 判定与后续",
            "",
            "诊断改善门槛为覆盖增加至少2个百分点、配对区间下界不低于0、虚假机会率增量不高于0.5个百分点、增量处理时延P95不超过1000毫秒，并保持身份泄漏、重复占用和因果违规为0。当前判定原因："
            + decision_reason_text
            + "。",
            "",
            "下一步先根据逐圈漏斗判断损失集中在视线拟合、几何白名单还是两圈确认。若覆盖没有改善，保留V4.1作为可解释诊断工具，不进入在线主线。四十目标仍优先修复共享单站跟踪器的时延和碎片问题，使用新协议和未查看种子重新冻结后，才能复测确定性交接。",
            "",
            "## 7. 文件索引",
            "",
            f"- 二十目标机器汇总：`{summary_path}`",
            f"- 四十目标停止证据：`{tracker_path}`",
            f"- 匿名在线清单：`{output_root / 'targets_020' / 'online_manifest.json'}`",
            f"- 匿名发布清单：`{output_root / 'targets_020' / 'publication_manifest.json'}`",
            "- 本轮没有AirSim截图，也没有重新运行AirSim。",
            "",
        ]
    )
    content = "\n".join(lines)
    path = output_root / "V4_1_DETERMINISTIC_HANDOVER_OFFLINE_REPORT_CN.md"
    path.write_text(content, encoding="utf-8")
    module_root = Path(__file__).resolve().parent
    stable_figures = _write_v41_figures(
        summary, module_root / "figures" / "v41_deterministic_handover"
    )
    stable_content = content.replace(
        figures[0].relative_to(output_root).as_posix(),
        stable_figures[0].relative_to(module_root).as_posix(),
    ).replace(
        figures[1].relative_to(output_root).as_posix(),
        stable_figures[1].relative_to(module_root).as_posix(),
    )
    stable_path = module_root / "V4_1_DETERMINISTIC_HANDOVER_OFFLINE_REPORT_CN.md"
    stable_path.write_text(stable_content, encoding="utf-8")
    return stable_path


def _resolve_output_root(output_root: str | Path) -> Path:
    value = Path(output_root).resolve()
    return value if value.name == V41_OUTPUT_VERSION else value / V41_OUTPUT_VERSION


def run_v41_replay(
    source_root: str | Path,
    output_root: str | Path,
) -> Path:
    """Run a 20-target replay or record a 40-target upstream stop."""

    source_root = Path(source_root).resolve()
    root = _resolve_output_root(output_root)
    paths = _source_paths(source_root)
    if paths["test_manifest"].is_file():
        full = load_dataset_manifest(
            paths["test_manifest"], validate_offline_labels=False
        )
        target_count = int(full["protocol"]["target_count"])
        output_dir = root / f"targets_{target_count:03d}"
        online = write_v41_online_manifest(source_root, output_dir)
        publication_manifest = write_v41_publications(online, output_dir)
        summary = score_v41_publications(publication_manifest, output_dir)
        if target_count == 20:
            write_v41_report(root)
        return summary
    if paths["tracker_calibration"].is_file():
        evidence = _read_object(paths["tracker_calibration"])
        protocol_fingerprint = str(evidence.get("protocol_fingerprint") or "")
        if not protocol_fingerprint:
            raise ValueError("tracker calibration evidence lacks a protocol")
        output_dir = root / "targets_040"
        diagnostic = write_v41_tracker_diagnostic(source_root, output_dir)
        if (root / "targets_020" / "summary.json").is_file():
            write_v41_report(root)
        return diagnostic
    raise ValueError("source root has neither a sealed test set nor tracker evidence")


__all__ = [
    "V41_ONLINE_MANIFEST_SCHEMA",
    "V41_OUTPUT_VERSION",
    "V41_PUBLICATION_SCHEMA",
    "V41_ROUTE_NAME",
    "V41_SUMMARY_SCHEMA",
    "assert_online_anonymous",
    "classify_v41_diagnostic",
    "run_v41_replay",
    "score_v41_publications",
    "validate_v41_online_manifest",
    "validate_v41_publication_manifest",
    "write_v41_online_manifest",
    "write_v41_publications",
    "write_v41_report",
    "write_v41_tracker_diagnostic",
]
