"""Public freeze and publish entry points for the main online benchmark."""

from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    AssociationPublication,
    BenchmarkProtocol,
    RevolutionSnapshot,
    read_snapshot,
    snapshot_fingerprint,
)
from dual_optical_online_benchmark.dataset import (
    DATASET_SCHEMA_VERSION as SHARED_DATASET_SCHEMA_VERSION,
    LEGACY_DATASET_SCHEMA_VERSION as SHARED_LEGACY_DATASET_SCHEMA_VERSION,
    load_dataset_manifest as load_shared_dataset_manifest,
)

from .dataset import (
    CAUSAL_DATASET_SCHEMA_VERSION,
    PROTOCOL_CAUSAL_ONLINE,
    canonical_json_sha256,
)
from .graph import GeometryGate
from .loader import sha256_file
from .online import (
    OnlineGNNAssociator,
    _snapshot_target_count,
    anonymous_graph_from_snapshot,
)
from .schema import GraphLabels, OnlineGraph
from .training import (
    CausalTrainingConfig,
    PreparedCausalCalibration,
    train_causal_ensemble_and_freeze,
)


ROUTE_NAME = "gnn"
OFFLINE_LABEL_SCHEMA = "track_truth_counts_v1"


def _safe_path(root: Path, relative: object) -> Path:
    path = Path(str(relative))
    if not str(path) or path.is_absolute():
        raise ValueError("dataset artifact path must be nonempty and relative")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("dataset artifact escapes its root") from exc
    return resolved


def _protocol_from_manifest(manifest: Mapping[str, Any]) -> BenchmarkProtocol:
    return BenchmarkProtocol(
        **{
            key: tuple(value)
            if key.endswith("_seeds") or key == "corruption_levels"
            else value
            for key, value in manifest["protocol"].items()
        }
    )


def _validate_calibration_entries(
    manifest: Mapping[str, Any], protocol: BenchmarkProtocol
) -> list[dict[str, Any]]:
    if manifest.get("phase") != "calibration":
        raise ValueError("GNN freeze requires the calibration manifest")
    if manifest.get("test_access_allowed") is not False:
        raise ValueError("calibration manifest must prohibit test access")
    entries = [dict(item) for item in manifest.get("entries", [])]
    if any(item.get("split") not in {"train", "validation"} for item in entries):
        raise ValueError("GNN freeze cannot receive a test entry")
    expected = {
        (split, int(seed), level, revolution)
        for split, seeds in (
            ("train", protocol.train_seeds),
            ("validation", protocol.validation_seeds),
        )
        for seed in seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }
    actual = {
        (
            str(item["split"]),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in entries
    }
    if len(actual) != len(entries) or actual != expected:
        raise ValueError("calibration manifest is incomplete or contains duplicates")
    return sorted(
        entries,
        key=lambda item: (
            0 if item["split"] == "train" else 1,
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        ),
    )


def _is_false_alarm(identity: str) -> bool:
    return identity == "FA" or identity.startswith("FA-")


def dominant_truth(counts: Mapping[str, Any]) -> str | None:
    """Return a unique non-FA maximum; ties and FA maxima stay unknown."""

    normalized: dict[str, int] = {}
    for raw_identity, raw_count in counts.items():
        identity = str(raw_identity)
        if not identity:
            raise ValueError("offline truth identity cannot be empty")
        count = int(raw_count)
        if count < 0 or float(raw_count) != float(count):
            raise ValueError("offline truth observation counts must be non-negative integers")
        if count:
            normalized[identity] = count
    if not normalized:
        return None
    maximum = max(normalized.values())
    winners = sorted(
        identity for identity, count in normalized.items() if count == maximum
    )
    if len(winners) != 1 or _is_false_alarm(winners[0]):
        return None
    return winners[0]


def _read_offline_labels(
    path: Path,
    *,
    entry: Mapping[str, Any],
    graph: OnlineGraph,
) -> tuple[OnlineGraph, GraphLabels, dict[str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "offline_truth_only",
        "seed",
        "corruption_level",
        "revolution_index",
        "track_truth_counts",
        "truth_heading_groups",
    }
    if set(payload) != required or "track_truth_candidates" in payload:
        raise ValueError("offline label fields do not match the frozen main schema")
    if payload["schema_version"] != SHARED_DATASET_SCHEMA_VERSION:
        raise ValueError("unsupported main offline label schema")
    if payload["offline_truth_only"] is not True:
        raise ValueError("calibration labels must be marked offline-only")
    for name, expected in (
        ("seed", int(entry["seed"])),
        ("corruption_level", str(entry["corruption_level"])),
        ("revolution_index", int(entry["revolution_index"])),
    ):
        if payload[name] != expected:
            raise ValueError(f"offline label metadata mismatch: {name}")
    counts = payload["track_truth_counts"]
    heading_groups = payload["truth_heading_groups"]
    if not isinstance(counts, Mapping) or not isinstance(heading_groups, Mapping):
        raise ValueError("offline count and heading labels must be objects")

    status = {"known": 0, "unknown": 0, "fa_or_tied": 0}

    def identity(track_id: str) -> str | None:
        raw = counts.get(track_id, {})
        if not isinstance(raw, Mapping):
            raise ValueError("each track_truth_counts value must be an object")
        value = dominant_truth(raw)
        if value is None:
            status["unknown"] += 1
            if raw:
                status["fa_or_tied"] += 1
        else:
            status["known"] += 1
        return value

    identity_a = tuple(identity(track_id) for track_id in graph.track_ids_a)
    identity_b = tuple(identity(track_id) for track_id in graph.track_ids_b)
    known_edges = np.asarray(
        [
            identity_a[int(index_a)] is not None
            and identity_b[int(index_b)] is not None
            for index_a, index_b in graph.edge_index.T
        ],
        dtype=bool,
    )
    filtered = replace(
        graph,
        edge_index=graph.edge_index[:, known_edges],
        edge_features=graph.edge_features[known_edges],
        geometry_cost=graph.geometry_cost[known_edges],
    )
    filtered.validate()
    edge_labels = np.asarray(
        [
            float(identity_a[int(index_a)] == identity_b[int(index_b)])
            for index_a, index_b in filtered.edge_index.T
        ],
        dtype=np.float32,
    )
    expected_identities = tuple(
        sorted(
            ({value for value in identity_a if value is not None}
             & {value for value in identity_b if value is not None})
            & {str(value) for value in heading_groups}
        )
    )
    labels = GraphLabels(
        edge_labels=edge_labels,
        identity_a=identity_a,
        identity_b=identity_b,
        expected_identities=expected_identities,
    )
    labels.validate(filtered)
    return filtered, labels, {
        "known_track_count": status["known"],
        "unknown_track_count": status["unknown"],
        "fa_or_tied_track_count": status["fa_or_tied"],
        "excluded_unknown_edge_count": int(
            graph.edge_index.shape[1] - filtered.edge_index.shape[1]
        ),
    }


def _input_record(
    entry: Mapping[str, Any],
    *,
    snapshot_target_count: int,
    candidate_graph_fingerprint: str,
) -> dict[str, Any]:
    return {
        "seed": int(entry["seed"]),
        "corruption_level": str(entry["corruption_level"]),
        "revolution_index": int(entry["revolution_index"]),
        "target_count": int(snapshot_target_count),
        "candidate_graph_fingerprint_sha256": str(candidate_graph_fingerprint),
        "input_fingerprint_sha256": str(entry["input_fingerprint"]),
        "online_sha256": str(entry["snapshot_sha256"]),
        "offline_label_sha256": str(entry["label_sha256"]),
    }


def _prepare_shared_calibration(
    manifest_path: Path,
) -> PreparedCausalCalibration:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("phase") != "calibration" or raw.get("test_access_allowed") is not False:
        raise ValueError("GNN freeze accepts a calibration-only main manifest")
    if any(item.get("split") == "test" for item in raw.get("entries", [])):
        raise ValueError("test entries cannot be present during GNN freeze")
    manifest = load_shared_dataset_manifest(manifest_path)
    protocol = _protocol_from_manifest(manifest)
    if manifest.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("calibration protocol fingerprint mismatch")
    entries = _validate_calibration_entries(manifest, protocol)
    root = manifest_path.parent
    gate = GeometryGate()
    train_data: list[tuple[OnlineGraph, GraphLabels]] = []
    validation_data: list[tuple[OnlineGraph, GraphLabels]] = []
    train_entries: list[dict[str, Any]] = []
    validation_entries: list[dict[str, Any]] = []
    diagnostics = {
        "known_track_count": 0,
        "unknown_track_count": 0,
        "fa_or_tied_track_count": 0,
        "excluded_unknown_edge_count": 0,
    }
    snapshot_contract_versions: set[str] = set()
    tracker_fingerprints: set[str] = set()
    for entry in entries:
        snapshot_path = _safe_path(root, entry["snapshot_path"])
        label_path = _safe_path(root, entry["label_path"])
        if sha256_file(snapshot_path) != entry["snapshot_sha256"]:
            raise ValueError("calibration snapshot hash mismatch")
        if sha256_file(label_path) != entry["label_sha256"]:
            raise ValueError("calibration label hash mismatch")
        snapshot = read_snapshot(snapshot_path)
        if snapshot_fingerprint(snapshot) != entry["input_fingerprint"]:
            raise ValueError("calibration input fingerprint mismatch")
        expected = (
            int(entry["seed"]),
            str(entry["split"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        actual = (
            snapshot.seed,
            snapshot.split,
            snapshot.corruption_level,
            snapshot.revolution_index,
        )
        if actual != expected or snapshot.protocol_fingerprint != protocol.fingerprint:
            raise ValueError("calibration snapshot metadata mismatch")
        snapshot_target_count = _snapshot_target_count(snapshot)
        if snapshot_target_count is None:
            if protocol.fingerprint != BenchmarkProtocol().fingerprint:
                raise ValueError(
                    "scale-isolated calibration snapshot is missing target_count"
                )
            snapshot_target_count = int(protocol.target_count)
        if snapshot_target_count != int(protocol.target_count):
            raise ValueError("calibration snapshot target_count does not match protocol")
        graph, graph_diagnostics = anonymous_graph_from_snapshot(snapshot, gate)
        snapshot_contract_versions.add(
            str(graph_diagnostics["snapshot_contract_version"])
        )
        tracker_fingerprints.add(str(snapshot.tracker_fingerprint))
        graph, labels, label_diagnostics = _read_offline_labels(
            label_path, entry=entry, graph=graph
        )
        for name, value in label_diagnostics.items():
            diagnostics[name] += value
        record = _input_record(
            entry,
            snapshot_target_count=snapshot_target_count,
            candidate_graph_fingerprint=str(
                graph_diagnostics.get("candidate_graph_fingerprint", "")
            ),
        )
        if entry["split"] == "train":
            train_data.append((graph, labels))
            train_entries.append(record)
        else:
            validation_data.append((graph, labels))
            validation_entries.append(record)

    if len(snapshot_contract_versions) != 1:
        raise ValueError("calibration snapshots mix incompatible contract versions")
    if len(tracker_fingerprints) != 1:
        raise ValueError("calibration snapshots mix tracker fingerprints")

    dataset_fingerprint = canonical_json_sha256(
        {
            "protocol_fingerprint": protocol.fingerprint,
            "train_inputs": train_entries,
            "validation_inputs": validation_entries,
        }
    )
    prepared_manifest = {
        "dataset_manifest_kind": "main_shared_calibration_v1",
        "dataset_fingerprint_sha256": dataset_fingerprint,
        "protocol_profile": PROTOCOL_CAUSAL_ONLINE,
        "protocol_fingerprint_sha256": protocol.fingerprint,
        "target_count": int(protocol.target_count),
        "splits": {
            "train": list(protocol.train_seeds),
            "val": list(protocol.validation_seeds),
            "test": list(protocol.test_seeds),
        },
        "corruption_levels": list(protocol.corruption_levels),
        "geometry_gate": asdict(gate),
        "revolutions_per_seed": protocol.revolution_count,
        "train_label_fingerprint_sha256": canonical_json_sha256(
            [item["offline_label_sha256"] for item in train_entries]
        ),
        "validation_label_fingerprint_sha256": canonical_json_sha256(
            [item["offline_label_sha256"] for item in validation_entries]
        ),
        "offline_label_schema": OFFLINE_LABEL_SCHEMA,
        "offline_label_diagnostics": diagnostics,
        "route_name": ROUTE_NAME,
        "snapshot_contract_version": next(iter(snapshot_contract_versions)),
        "tracker_fingerprint": next(iter(tracker_fingerprints)),
        "candidate_graph_contract": "main_snapshot_geometry_candidate_pairs_v1",
    }
    return PreparedCausalCalibration(
        manifest=prepared_manifest,
        train_data=train_data,
        validation_data=validation_data,
        train_entries=train_entries,
        validation_entries=validation_entries,
    )


def freeze_route(
    dataset_manifest: Path,
    output_dir: Path,
    *,
    device: str = "auto",
) -> Path:
    """Train five initializations and freeze one without opening test data."""

    manifest_path = Path(dataset_manifest).resolve()
    config = CausalTrainingConfig(device=device)
    if not manifest_path.is_file():
        return train_causal_ensemble_and_freeze(
            manifest_path,
            output_dir,
            config=config,
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") == CAUSAL_DATASET_SCHEMA_VERSION:
        return train_causal_ensemble_and_freeze(
            manifest_path,
            output_dir,
            config=config,
        )
    if payload.get("schema_version") not in {
        SHARED_DATASET_SCHEMA_VERSION,
        SHARED_LEGACY_DATASET_SCHEMA_VERSION,
    }:
        raise ValueError("unsupported calibration dataset schema")
    prepared = _prepare_shared_calibration(manifest_path)
    return train_causal_ensemble_and_freeze(
        manifest_path,
        output_dir,
        config=config,
        prepared=prepared,
    )


class FrozenGNNRoute:
    """Frozen public route that consumes anonymous cumulative snapshots only."""

    route_name = ROUTE_NAME

    def __init__(self, freeze_manifest: Path) -> None:
        self._associator = OnlineGNNAssociator(str(freeze_manifest))

    @property
    def model_fingerprint(self) -> str:
        return self._associator.model_fingerprint

    def publish(self, snapshot: RevolutionSnapshot) -> AssociationPublication:
        return self._associator.associate(snapshot).publication


def load_frozen_route(freeze_manifest: Path) -> FrozenGNNRoute:
    """Load the selected checkpoint without opening a snapshot or label file."""

    return FrozenGNNRoute(freeze_manifest)
