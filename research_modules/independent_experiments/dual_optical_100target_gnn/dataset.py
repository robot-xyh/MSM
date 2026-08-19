"""Persist online graphs and offline labels with reproducible hashes."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from dual_optical_online_benchmark.contracts import (
    SUPPORTED_TARGET_COUNTS,
    BenchmarkProtocol,
    benchmark_protocol_for_target_count,
)

from .corruption import corrupt_episode, corrupt_episode_causal
from .graph import GeometryGate, build_graph
from .loader import load_offline_labels, load_online_episode, sha256_file
from .schema import (
    CORRUPTION_LEVELS,
    CAUSAL_FORMAL_SPLITS,
    CAUSAL_REVOLUTION_COUNT,
    DEFAULT_SPLITS,
    EDGE_FEATURE_NAMES,
    EXPANDED_FORMAL_TRAIN_SEEDS,
    EXPANDED_FORMAL_VALIDATION_SEEDS,
    LEGACY_FORMAL_TEST_SEEDS,
    MINIMUM_EXPANDED_TEST_SEEDS,
    NODE_FEATURE_NAMES,
    CausalProtocolConfig,
    CorruptionSummary,
    GraphLabels,
    OnlineGraph,
)


DATASET_SCHEMA_VERSION = "dual-optical-100target-gnn-dataset-v3"
CAUSAL_DATASET_SCHEMA_VERSION = "dual-optical-100target-gnn-dataset-v4"
LEGACY_DATASET_SCHEMA_VERSION = "dual-optical-100target-gnn-dataset-v2"
SUPPORTED_DATASET_SCHEMA_VERSIONS = frozenset(
    {
        LEGACY_DATASET_SCHEMA_VERSION,
        DATASET_SCHEMA_VERSION,
        CAUSAL_DATASET_SCHEMA_VERSION,
    }
)
PROTOCOL_LEGACY_FORMAL = "legacy_formal_2test_v1"
PROTOCOL_EXPANDED_FORMAL = "expanded_formal_20plus_test_v1"
PROTOCOL_CAUSAL_ONLINE = "causal_360_24train_6val_20test_v1"
PROTOCOL_NONFORMAL = "nonformal_fixture_or_custom"
ONLINE_GRAPH_FIELDS = frozenset(
    {
        "seed",
        "corruption_level",
        "camera_ids",
        "track_ids_a",
        "track_ids_b",
        "node_features_a",
        "node_features_b",
        "edge_index",
        "edge_features",
        "geometry_cost",
        "corruption_seed",
        "dropped_sample_count",
        "retained_sample_count",
        "transient_false_track_count",
        "persistent_false_track_count",
    }
)


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _fingerprint_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    sources = {
        str(seed): {
            key: value
            for key, value in source.items()
            if key != "path"
        }
        for seed, source in manifest["sources"].items()
    }
    payload = {
        "schema_version": manifest["schema_version"],
        "node_feature_names": manifest["node_feature_names"],
        "edge_feature_names": manifest["edge_feature_names"],
        "splits": manifest["splits"],
        "formal_protocol": manifest["formal_protocol"],
        "expected_target_count": manifest["expected_target_count"],
        "corruption_levels": manifest["corruption_levels"],
        "geometry_gate": manifest["geometry_gate"],
        "sources": sources,
        "samples": manifest["samples"],
        "truth_isolation": manifest["truth_isolation"],
    }
    if manifest["schema_version"] != LEGACY_DATASET_SCHEMA_VERSION:
        payload["protocol_profile"] = manifest["protocol_profile"]
        payload["expanded_formal_protocol"] = manifest[
            "expanded_formal_protocol"
        ]
    if manifest["schema_version"] == CAUSAL_DATASET_SCHEMA_VERSION:
        payload["causal_prefix_protocol"] = manifest["causal_prefix_protocol"]
        payload["revolutions_per_seed"] = manifest["revolutions_per_seed"]
        payload["causal_scenario_contract"] = manifest["causal_scenario_contract"]
        payload["protocol_fingerprint_sha256"] = manifest[
            "protocol_fingerprint_sha256"
        ]
    return payload


def dataset_fingerprint(manifest: Mapping[str, Any]) -> str:
    return canonical_json_sha256(_fingerprint_payload(manifest))


def _identity_array(values: Sequence[str | None]) -> np.ndarray:
    return np.asarray([value or "" for value in values], dtype="U128")


def _save_online_graph(path: Path, graph: OnlineGraph) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        seed=np.asarray([graph.seed], dtype=np.int64),
        corruption_level=np.asarray([graph.corruption_level], dtype="U16"),
        camera_ids=np.asarray(graph.camera_ids, dtype="U64"),
        track_ids_a=np.asarray(graph.track_ids_a, dtype="U128"),
        track_ids_b=np.asarray(graph.track_ids_b, dtype="U128"),
        node_features_a=graph.node_features_a.astype(np.float32),
        node_features_b=graph.node_features_b.astype(np.float32),
        edge_index=graph.edge_index.astype(np.int64),
        edge_features=graph.edge_features.astype(np.float32),
        geometry_cost=graph.geometry_cost.astype(np.float32),
        corruption_seed=np.asarray([graph.corruption_summary.corruption_seed], dtype=np.int64),
        dropped_sample_count=np.asarray([graph.corruption_summary.dropped_sample_count], dtype=np.int64),
        retained_sample_count=np.asarray([graph.corruption_summary.retained_sample_count], dtype=np.int64),
        transient_false_track_count=np.asarray([graph.corruption_summary.transient_false_track_count], dtype=np.int64),
        persistent_false_track_count=np.asarray([graph.corruption_summary.persistent_false_track_count], dtype=np.int64),
    )


def _save_offline_labels(path: Path, labels: GraphLabels) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        edge_labels=labels.edge_labels.astype(np.float32),
        identity_a=_identity_array(labels.identity_a),
        identity_b=_identity_array(labels.identity_b),
        expected_identities=np.asarray(labels.expected_identities, dtype="U128"),
    )


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key] for key in archive.files}


def load_online_graph(path: str | Path) -> OnlineGraph:
    values = _load_npz(Path(path))
    unexpected = set(values) - ONLINE_GRAPH_FIELDS
    missing = ONLINE_GRAPH_FIELDS - set(values)
    if unexpected or missing:
        raise ValueError(
            f"invalid online graph fields; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    summary = CorruptionSummary(
        level=str(values["corruption_level"][0]),
        corruption_seed=int(values["corruption_seed"][0]),
        dropped_sample_count=int(values["dropped_sample_count"][0]),
        retained_sample_count=int(values["retained_sample_count"][0]),
        transient_false_track_count=int(values["transient_false_track_count"][0]),
        persistent_false_track_count=int(values["persistent_false_track_count"][0]),
    )
    graph = OnlineGraph(
        seed=int(values["seed"][0]),
        corruption_level=str(values["corruption_level"][0]),
        camera_ids=tuple(str(value) for value in values["camera_ids"]),  # type: ignore[arg-type]
        track_ids_a=tuple(str(value) for value in values["track_ids_a"]),
        track_ids_b=tuple(str(value) for value in values["track_ids_b"]),
        node_features_a=values["node_features_a"].astype(np.float32),
        node_features_b=values["node_features_b"].astype(np.float32),
        edge_index=values["edge_index"].astype(np.int64),
        edge_features=values["edge_features"].astype(np.float32),
        geometry_cost=values["geometry_cost"].astype(np.float32),
        corruption_summary=summary,
    )
    graph.validate()
    return graph


def load_offline_graph_labels(path: str | Path, graph: OnlineGraph) -> GraphLabels:
    values = _load_npz(Path(path))
    labels = GraphLabels(
        edge_labels=values["edge_labels"].astype(np.float32),
        identity_a=tuple(str(value) or None for value in values["identity_a"]),
        identity_b=tuple(str(value) or None for value in values["identity_b"]),
        expected_identities=tuple(str(value) for value in values["expected_identities"]),
    )
    labels.validate(graph)
    return labels


def _validate_splits(splits: Mapping[str, Sequence[int]]) -> dict[str, tuple[int, ...]]:
    if set(splits) != {"train", "val", "test"}:
        raise ValueError("splits must contain exactly train, val, and test")
    normalized = {
        name: tuple(sorted(int(seed) for seed in splits[name]))
        for name in ("train", "val", "test")
    }
    for name, values in normalized.items():
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate seed in {name} split")
    sets = {name: set(values) for name, values in normalized.items()}
    if sets["train"] & sets["val"] or sets["train"] & sets["test"] or sets["val"] & sets["test"]:
        raise ValueError("train, validation, and test seeds must be disjoint")
    if any(not values for values in normalized.values()):
        raise ValueError("each split must contain at least one complete seed")
    return normalized


def protocol_profile(
    splits: Mapping[str, Sequence[int]], expected_target_count: int
) -> str:
    if expected_target_count in SUPPORTED_TARGET_COUNTS:
        tier = benchmark_protocol_for_target_count(expected_target_count)
        tier_splits = {
            "train": tier.train_seeds,
            "val": tier.validation_seeds,
            "test": tier.test_seeds,
        }
        if all(
            tuple(sorted(int(seed) for seed in splits[name]))
            == tuple(sorted(tier_splits[name]))
            for name in ("train", "val", "test")
        ):
            return PROTOCOL_CAUSAL_ONLINE
    # Preserve the sealed first-generation 100-target fixture profile. Its
    # protocol fingerprint and seed split remain distinct from the new tier.
    if expected_target_count != 100:
        return PROTOCOL_NONFORMAL
    legacy = all(
        set(int(seed) for seed in splits[name]) == set(DEFAULT_SPLITS[name])
        and len(splits[name]) == len(DEFAULT_SPLITS[name])
        for name in ("train", "val", "test")
    )
    if legacy:
        return PROTOCOL_LEGACY_FORMAL
    causal = all(
        tuple(sorted(int(seed) for seed in splits[name]))
        == tuple(sorted(CAUSAL_FORMAL_SPLITS[name]))
        for name in ("train", "val", "test")
    )
    if causal:
        return PROTOCOL_CAUSAL_ONLINE
    train = tuple(int(seed) for seed in splits["train"])
    validation = tuple(int(seed) for seed in splits["val"])
    test = tuple(int(seed) for seed in splits["test"])
    expanded = (
        set(train) == set(EXPANDED_FORMAL_TRAIN_SEEDS)
        and len(train) == len(EXPANDED_FORMAL_TRAIN_SEEDS)
        and set(validation) == set(EXPANDED_FORMAL_VALIDATION_SEEDS)
        and len(validation) == len(EXPANDED_FORMAL_VALIDATION_SEEDS)
        and len(test) >= MINIMUM_EXPANDED_TEST_SEEDS
        and not (set(test) & set(LEGACY_FORMAL_TEST_SEEDS))
    )
    return PROTOCOL_EXPANDED_FORMAL if expanded else PROTOCOL_NONFORMAL


def _is_formal_protocol(
    splits: Mapping[str, Sequence[int]], expected_target_count: int
) -> bool:
    return protocol_profile(splits, expected_target_count) != PROTOCOL_NONFORMAL


def candidate_graph_fingerprint(graph: OnlineGraph) -> str:
    """Hash every anonymous online input used by scoring and assignment."""

    digest = hashlib.sha256()
    metadata = {
        "seed": graph.seed,
        "corruption_level": graph.corruption_level,
        "camera_ids": list(graph.camera_ids),
        "track_ids_a": list(graph.track_ids_a),
        "track_ids_b": list(graph.track_ids_b),
    }
    digest.update(
        json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    for name, values, dtype in (
        ("node_features_a", graph.node_features_a, "<f4"),
        ("node_features_b", graph.node_features_b, "<f4"),
        ("edge_index", graph.edge_index, "<i8"),
        ("edge_features", graph.edge_features, "<f4"),
        ("geometry_cost", graph.geometry_cost, "<f4"),
    ):
        array = np.ascontiguousarray(np.asarray(values, dtype=dtype))
        digest.update(name.encode("ascii"))
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def causal_snapshot_fingerprint(
    graph: OnlineGraph,
    revolution_index: int,
    cutoff_timestamp_s: float,
) -> str:
    """Bind an anonymous graph to its causal prefix without adding identity fields."""

    return canonical_json_sha256(
        {
            "candidate_graph_fingerprint_sha256": candidate_graph_fingerprint(graph),
            "seed": int(graph.seed),
            "corruption_level": graph.corruption_level,
            "revolution_index": int(revolution_index),
            "cutoff_timestamp_s": float(cutoff_timestamp_s),
        }
    )


def _prefix_episode(episode: Any, cutoff_timestamp_s: float) -> Any:
    tracks = {}
    for camera_id in episode.camera_ids:
        prefix_tracks = []
        for track in episode.tracks[camera_id]:
            samples = tuple(
                sample
                for sample in track.samples
                if sample.timestamp <= cutoff_timestamp_s + 1.0e-9
            )
            if samples:
                prefix_tracks.append(replace(track, samples=samples))
        tracks[camera_id] = tuple(prefix_tracks)
    return replace(episode, tracks=tracks)


def prepare_causal_dataset(
    inputs: Mapping[int, str | Path],
    output_dir: str | Path,
    *,
    splits: Mapping[str, Sequence[int]] = CAUSAL_FORMAL_SPLITS,
    gate: GeometryGate | None = None,
    expected_target_count: int = 100,
    protocol: CausalProtocolConfig | None = None,
) -> Path:
    """Build six immutable prefixes per corruption without opening future samples."""

    split_values = _validate_splits(splits)
    required = set().union(*(set(values) for values in split_values.values()))
    missing = sorted(required - set(inputs))
    extra = sorted(set(inputs) - required)
    if missing:
        raise FileNotFoundError(f"missing complete episode seeds: {missing}")
    if extra:
        raise ValueError(f"input seeds are not assigned to a split: {extra}")

    protocol = protocol or CausalProtocolConfig()
    benchmark_protocol = (
        benchmark_protocol_for_target_count(expected_target_count)
        if expected_target_count in SUPPORTED_TARGET_COUNTS
        else BenchmarkProtocol()
    )
    gate = gate or GeometryGate()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, Any]] = []
    sources: dict[str, Any] = {}
    for seed in sorted(required):
        source_path = Path(inputs[seed]).resolve()
        episode = load_online_episode(source_path)
        if episode.seed != seed:
            raise ValueError(f"seed key {seed} does not match episode seed {episode.seed}")
        labels = load_offline_labels(source_path, episode)
        recorded_target_count = (
            episode.configured_target_count
            if episode.configured_target_count is not None
            else len(labels.expected_identities)
        )
        if recorded_target_count != expected_target_count:
            raise ValueError(
                f"episode seed {seed} configures {recorded_target_count} targets; "
                f"this dataset requires {expected_target_count}"
            )
        timestamps = [
            sample.timestamp
            for camera_id in episode.camera_ids
            for track in episode.tracks[camera_id]
            for sample in track.samples
        ]
        if not timestamps:
            raise ValueError(f"episode seed {seed} contains no online observations")
        start_timestamp_s = float(min(timestamps))
        sources[str(seed)] = {
            "path": str(source_path),
            "record_schema_version": episode.schema_version,
            "source_hashes": dict(episode.source_hashes),
            "offline_label_source_hashes": dict(labels.source_hashes),
            "observation_start_timestamp_s": start_timestamp_s,
        }
        split = next(name for name, values in split_values.items() if seed in values)
        for level_name, config in CORRUPTION_LEVELS.items():
            for revolution_index in range(1, protocol.revolution_count + 1):
                cutoff = revolution_index * protocol.scan_period_s
                source_prefix = _prefix_episode(episode, cutoff)
                prefix, corrupted_labels, summary = corrupt_episode_causal(
                    source_prefix,
                    labels,
                    config,
                    scan_period_s=protocol.scan_period_s,
                )
                graph, graph_labels, diagnostics = build_graph(
                    prefix,
                    corrupted_labels,
                    summary,
                    gate=gate,
                )
                stem = f"seed_{seed}_{level_name}_rev_{revolution_index:02d}"
                online_path = output_dir / "online" / f"{stem}.npz"
                label_path = output_dir / "offline_labels" / f"{stem}.npz"
                _save_online_graph(online_path, graph)
                _save_offline_labels(label_path, graph_labels)
                snapshot_fingerprint = causal_snapshot_fingerprint(
                    graph, revolution_index, cutoff
                )
                samples.append(
                    {
                        "seed": seed,
                        "split": split,
                        "corruption_level": level_name,
                        "revolution_index": revolution_index,
                        "cutoff_timestamp_s": cutoff,
                        "online_path": str(online_path.relative_to(output_dir)),
                        "online_sha256": sha256_file(online_path),
                        "input_fingerprint_sha256": snapshot_fingerprint,
                        "offline_label_path": str(label_path.relative_to(output_dir)),
                        "offline_label_sha256": sha256_file(label_path),
                        "corruption": asdict(summary),
                        "online_diagnostics": {
                            key: value
                            for key, value in diagnostics.items()
                            if key != "positive_candidate_edge_count"
                        },
                    }
                )

    profile = protocol_profile(split_values, expected_target_count)
    manifest = {
        "schema_version": CAUSAL_DATASET_SCHEMA_VERSION,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "splits": {name: list(values) for name, values in split_values.items()},
        "formal_protocol": profile == PROTOCOL_CAUSAL_ONLINE,
        "expanded_formal_protocol": False,
        "causal_prefix_protocol": True,
        "protocol_profile": profile,
        "protocol_fingerprint_sha256": benchmark_protocol.fingerprint,
        "revolutions_per_seed": protocol.revolution_count,
        "causal_scenario_contract": asdict(protocol),
        "expected_target_count": expected_target_count,
        "corruption_levels": {
            name: asdict(config) for name, config in CORRUPTION_LEVELS.items()
        },
        "geometry_gate": asdict(gate),
        "sources": sources,
        "samples": samples,
        "truth_isolation": {
            "online_files_contain_identity": False,
            "labels_are_offline_only": True,
            "actor_fields_are_features": False,
            "world_truth_fields_are_features": False,
        },
    }
    manifest["dataset_fingerprint_sha256"] = dataset_fingerprint(manifest)
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def prepare_dataset(
    inputs: Mapping[int, str | Path],
    output_dir: str | Path,
    *,
    splits: Mapping[str, Sequence[int]] = DEFAULT_SPLITS,
    gate: GeometryGate | None = None,
    expected_target_count: int = 100,
) -> Path:
    """Build all corruptions before training; split access remains separate later."""

    split_values = _validate_splits(splits)
    required = set().union(*[set(values) for values in split_values.values()])
    missing = sorted(required - set(inputs))
    extra = sorted(set(inputs) - required)
    if missing:
        raise FileNotFoundError(f"missing complete episode seeds: {missing}")
    if extra:
        raise ValueError(f"input seeds are not assigned to a split: {extra}")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    gate = gate or GeometryGate()

    samples: list[dict[str, Any]] = []
    sources: dict[str, Any] = {}
    for seed in sorted(required):
        source_path = Path(inputs[seed]).resolve()
        episode = load_online_episode(source_path)
        if episode.seed != seed:
            raise ValueError(f"seed key {seed} does not match episode seed {episode.seed}")
        labels = load_offline_labels(source_path, episode)
        recorded_target_count = (
            episode.configured_target_count
            if episode.configured_target_count is not None
            else len(labels.expected_identities)
        )
        if recorded_target_count != expected_target_count:
            raise ValueError(
                f"episode seed {seed} configures {recorded_target_count} targets; "
                f"this dataset requires {expected_target_count}"
            )
        sources[str(seed)] = {
            "path": str(source_path),
            "record_schema_version": episode.schema_version,
            "source_hashes": dict(episode.source_hashes),
            "offline_label_source_hashes": dict(labels.source_hashes),
        }
        split = next(name for name, values in split_values.items() if seed in values)
        for level_name, config in CORRUPTION_LEVELS.items():
            corrupted, corrupted_labels, summary = corrupt_episode(episode, labels, config)
            graph, graph_labels, diagnostics = build_graph(
                corrupted,
                corrupted_labels,
                summary,
                gate=gate,
            )
            stem = f"seed_{seed}_{level_name}"
            online_path = output_dir / "online" / f"{stem}.npz"
            label_path = output_dir / "offline_labels" / f"{stem}.npz"
            _save_online_graph(online_path, graph)
            _save_offline_labels(label_path, graph_labels)
            samples.append(
                {
                    "seed": seed,
                    "split": split,
                    "corruption_level": level_name,
                    "online_path": str(online_path.relative_to(output_dir)),
                    "online_sha256": sha256_file(online_path),
                    "offline_label_path": str(label_path.relative_to(output_dir)),
                    "offline_label_sha256": sha256_file(label_path),
                    "corruption": asdict(summary),
                    "online_diagnostics": {
                        key: value
                        for key, value in diagnostics.items()
                        if key != "positive_candidate_edge_count"
                    },
                }
            )

    profile = protocol_profile(split_values, expected_target_count)
    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "splits": {name: list(values) for name, values in split_values.items()},
        "formal_protocol": profile != PROTOCOL_NONFORMAL,
        "expanded_formal_protocol": profile == PROTOCOL_EXPANDED_FORMAL,
        "protocol_profile": profile,
        "expected_target_count": expected_target_count,
        "corruption_levels": {
            name: asdict(config) for name, config in CORRUPTION_LEVELS.items()
        },
        "geometry_gate": asdict(gate),
        "sources": sources,
        "samples": samples,
        "truth_isolation": {
            "online_files_contain_identity": False,
            "labels_are_offline_only": True,
            "actor_fields_are_features": False,
            "world_truth_fields_are_features": False,
        },
    }
    manifest["dataset_fingerprint_sha256"] = dataset_fingerprint(manifest)
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def load_dataset_manifest(path: str | Path) -> tuple[dict[str, Any], Path]:
    path = Path(path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    schema_version = manifest.get("schema_version")
    if schema_version not in SUPPORTED_DATASET_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported dataset schema: {manifest.get('schema_version')}")
    if manifest.get("node_feature_names") != list(NODE_FEATURE_NAMES):
        raise ValueError("dataset node feature contract does not match this implementation")
    if manifest.get("edge_feature_names") != list(EDGE_FEATURE_NAMES):
        raise ValueError("dataset edge feature contract does not match this implementation")
    expected_corruption = {
        name: asdict(config) for name, config in CORRUPTION_LEVELS.items()
    }
    if manifest.get("corruption_levels") != expected_corruption:
        raise ValueError("dataset corruption contract does not match this implementation")
    expected_truth_isolation = {
        "online_files_contain_identity": False,
        "labels_are_offline_only": True,
        "actor_fields_are_features": False,
        "world_truth_fields_are_features": False,
    }
    if manifest.get("truth_isolation") != expected_truth_isolation:
        raise ValueError("dataset truth-isolation contract is invalid")
    expected_fingerprint = dataset_fingerprint(manifest)
    if manifest.get("dataset_fingerprint_sha256") != expected_fingerprint:
        raise ValueError("dataset manifest fingerprint mismatch")
    splits = _validate_splits(manifest["splits"])
    expected_profile = protocol_profile(splits, int(manifest["expected_target_count"]))
    expected_formal = expected_profile != PROTOCOL_NONFORMAL
    if bool(manifest.get("formal_protocol")) != expected_formal:
        raise ValueError("dataset formal-protocol marker is inconsistent")
    if schema_version != LEGACY_DATASET_SCHEMA_VERSION:
        if manifest.get("protocol_profile") != expected_profile:
            raise ValueError("dataset protocol profile is inconsistent")
        expected_expanded = expected_profile == PROTOCOL_EXPANDED_FORMAL
        if bool(manifest.get("expanded_formal_protocol")) != expected_expanded:
            raise ValueError("dataset expanded-formal marker is inconsistent")
    if schema_version == CAUSAL_DATASET_SCHEMA_VERSION:
        expected_causal = expected_profile == PROTOCOL_CAUSAL_ONLINE
        if bool(manifest.get("causal_prefix_protocol")) is not True:
            raise ValueError("causal dataset must declare causal-prefix protocol")
        if expected_causal != bool(manifest.get("formal_protocol")):
            raise ValueError("causal formal-protocol marker is inconsistent")
        if int(manifest.get("revolutions_per_seed", 0)) != CAUSAL_REVOLUTION_COUNT:
            raise ValueError("causal dataset must contain six revolutions per seed")
        CausalProtocolConfig(**dict(manifest.get("causal_scenario_contract", {})))
        target_count = int(manifest["expected_target_count"])
        expected_fingerprints = {
            benchmark_protocol_for_target_count(target_count).fingerprint
            if target_count in SUPPORTED_TARGET_COUNTS
            else BenchmarkProtocol().fingerprint
        }
        if target_count == 100:
            expected_fingerprints.add(BenchmarkProtocol().fingerprint)
        if manifest.get("protocol_fingerprint_sha256") not in expected_fingerprints:
            raise ValueError("causal dataset protocol fingerprint is inconsistent")
    required_seeds = set().union(*(set(values) for values in splits.values()))
    if {int(seed) for seed in manifest["sources"]} != required_seeds:
        raise ValueError("dataset source list does not match the split contract")
    invalid_sample_splits = {
        str(item.get("split"))
        for item in manifest["samples"]
        if item.get("split") not in {"train", "val", "test"}
    }
    if invalid_sample_splits:
        raise ValueError(f"invalid sample split values: {sorted(invalid_sample_splits)}")
    for split in ("train", "val", "test"):
        sample_entries(manifest, split)
    return manifest, path.parent


def sample_entries(
    manifest: Mapping[str, Any],
    split: str,
) -> list[dict[str, Any]]:
    if split not in {"train", "val", "test"}:
        raise ValueError(f"invalid split: {split}")
    entries = [dict(item) for item in manifest["samples"] if item["split"] == split]
    expected_seeds = set(int(seed) for seed in manifest["splits"][split])
    actual_seeds = {int(item["seed"]) for item in entries}
    if actual_seeds != expected_seeds:
        raise ValueError(f"incomplete {split} split: expected {expected_seeds}, found {actual_seeds}")
    required_levels = set(CORRUPTION_LEVELS)
    causal = manifest.get("schema_version") == CAUSAL_DATASET_SCHEMA_VERSION
    for seed in sorted(expected_seeds):
        seed_entries = [item for item in entries if int(item["seed"]) == seed]
        if causal:
            expected_pairs = {
                (level, revolution)
                for level in required_levels
                for revolution in range(1, CAUSAL_REVOLUTION_COUNT + 1)
            }
            actual_pairs = [
                (str(item["corruption_level"]), int(item.get("revolution_index", 0)))
                for item in seed_entries
            ]
            if len(actual_pairs) != len(expected_pairs) or set(actual_pairs) != expected_pairs:
                raise ValueError(
                    f"incomplete causal snapshots for {split} seed {seed}"
                )
            for item in seed_entries:
                cutoff = float(item.get("cutoff_timestamp_s", float("nan")))
                if not np.isfinite(cutoff):
                    raise ValueError("causal snapshot cutoff timestamp is invalid")
                fingerprint = str(item.get("input_fingerprint_sha256", ""))
                if len(fingerprint) != 64:
                    raise ValueError("causal snapshot input fingerprint is invalid")
        else:
            levels = [str(item["corruption_level"]) for item in seed_entries]
            if len(levels) != len(required_levels) or set(levels) != required_levels:
                raise ValueError(
                    f"incomplete corruption set for {split} seed {seed}: {sorted(levels)}"
                )
    return sorted(
        entries,
        key=lambda item: (
            int(item["seed"]),
            item["corruption_level"],
            int(item.get("revolution_index", 0)),
        ),
    )


def load_entry(
    root: Path,
    entry: Mapping[str, Any],
    *,
    include_labels: bool,
) -> tuple[OnlineGraph, GraphLabels | None]:
    online_path = root / entry["online_path"]
    if sha256_file(online_path) != entry["online_sha256"]:
        raise ValueError(f"online graph hash mismatch: {online_path}")
    graph = load_online_graph(online_path)
    if graph.seed != int(entry["seed"]):
        raise ValueError(f"online graph seed does not match manifest entry: {online_path}")
    if graph.corruption_level != str(entry["corruption_level"]):
        raise ValueError(
            f"online graph corruption level does not match manifest entry: {online_path}"
        )
    if "input_fingerprint_sha256" in entry:
        expected = causal_snapshot_fingerprint(
            graph,
            int(entry["revolution_index"]),
            float(entry["cutoff_timestamp_s"]),
        )
        if expected != entry["input_fingerprint_sha256"]:
            raise ValueError(f"causal input fingerprint mismatch: {online_path}")
    if not include_labels:
        return graph, None
    label_path = root / entry["offline_label_path"]
    if sha256_file(label_path) != entry["offline_label_sha256"]:
        raise ValueError(f"offline label hash mismatch: {label_path}")
    return graph, load_offline_graph_labels(label_path, graph)
