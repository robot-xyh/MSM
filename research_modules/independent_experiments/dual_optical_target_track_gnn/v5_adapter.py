"""V5 adapter for causal target-hypothesis to local-track association."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

from dual_optical_online_benchmark.contracts import (
    BenchmarkProtocol,
    RevolutionSnapshot,
    benchmark_protocol_from_mapping,
    read_snapshot,
    snapshot_fingerprint,
)

from .assignment import publish_with_confirmation, solve_target_track_assignment
from .contracts import (
    PAIR_PUBLICATION_ROUTE,
    PAIR_PUBLICATION_SCHEMA_VERSION,
    ConfirmedTrackPair,
    TargetHypothesis,
    TargetTrackGraph,
    TargetTrackPublication,
    online_pair_publication_fingerprint,
    payload_fingerprint,
    validate_online_pair_publication,
)
from .geometry import (
    CausalityError,
    GeometryFitError,
    evaluate_asynchronous_track_pair,
    form_target_hypothesis,
)
from .graph import TargetTrackGate, build_camera_graphs
from .model import FeatureNormalizer, TargetTrackCostGNN, load_frozen_model
from .training import (
    DEFAULT_INITIALIZATION_SEEDS,
    FiveInitializationConfig,
    TargetTrackTrainingExample,
    train_and_freeze_five_initializations,
)


PUBLICATION_MANIFEST_SCHEMA = "dual-optical-v5-publications-v1"
SCENARIO_PUBLICATION_SCHEMA = "dual-optical-v5-target-track-scenario-v1"
NATIVE_FREEZE_SCHEMA = "dual-optical-v5-target-track-native-freeze-v1"
V5_MODEL_FREEZE_SCHEMA = "dual-optical-v5-target-track-model-freeze-v1"
V5_ONLINE_TEST_MANIFEST_SCHEMA = "dual-optical-v5-online-test-manifest-v1"
METRICS_SCHEMA = "dual-optical-v5-target-track-metrics-v1"
ROUTES = ("rule_baseline", "gnn_assisted")
ROUTE_TO_INTERNAL = {
    "rule_baseline": "deterministic",
    "gnn_assisted": "gnn_assisted",
}
SCALE_SAMPLING_POLICY = "uniform_over_40_60_100"
SUPPORTED_TARGET_COUNTS = (40, 60, 100)
PAIR_UNMATCHED_COST = 0.95
TRAIN_SEEDS_PER_SCALE = 4
VALIDATION_SEEDS_PER_SCALE = 2
TRAINING_MAX_EPOCHS = 40
TRAINING_PATIENCE = 8
_FORBIDDEN_ONLINE_FIELDS = {
    "label_path",
    "label_sha256",
    "track_truth_counts",
    "truth_heading_groups",
    "offline_truth_only",
    "truth_id",
    "actor_id",
    "global_track_id",
}


@dataclass(frozen=True)
class _GraphRecord:
    snapshot: RevolutionSnapshot
    hypotheses: tuple[TargetHypothesis, ...]
    graph: TargetTrackGraph


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(_canonical_json(payload) + b"\n")
    return destination


def _artifact_path(manifest_path: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def _find_forbidden_online_field(value: Any, prefix: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            name = str(key).lower()
            location = f"{prefix}.{name}" if prefix else name
            carries_label_artifact = "label" in name and any(
                marker in name for marker in ("path", "sha", "hash", "payload", "content")
            )
            carries_identity = (
                "truth" in name
                or "actor_id" in name
                or "global_track" in name
            )
            if (
                name in _FORBIDDEN_ONLINE_FIELDS
                or carries_label_artifact
                or carries_identity
            ):
                return location
            found = _find_forbidden_online_field(nested, location)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            found = _find_forbidden_online_field(nested, f"{prefix}[{index}]")
            if found is not None:
                return found
    return None


def _protocol_from_manifest(
    payload: Mapping[str, Any], *, expected_target_count: int | None = None
) -> BenchmarkProtocol:
    protocol_values = payload.get("protocol")
    if not isinstance(protocol_values, Mapping):
        raise ValueError("dataset manifest lacks its frozen protocol")
    protocol = benchmark_protocol_from_mapping(protocol_values)
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("dataset manifest protocol fingerprint mismatch")
    if expected_target_count is not None and protocol.target_count != expected_target_count:
        raise ValueError("dataset manifest target scale mismatch")
    return protocol


def _entry_matrix_fingerprint(entries: Sequence[Mapping[str, Any]]) -> str:
    rows = sorted(
        (
            {
                "split": str(entry["split"]),
                "seed": int(entry["seed"]),
                "corruption_level": str(entry["corruption_level"]),
                "revolution_index": int(entry["revolution_index"]),
                "snapshot_sha256": str(entry["snapshot_sha256"]),
                "input_fingerprint": str(entry["input_fingerprint"]),
            }
            for entry in entries
        ),
        key=lambda item: (
            item["split"],
            item["seed"],
            item["corruption_level"],
            item["revolution_index"],
        ),
    )
    return payload_fingerprint({"entries": rows})


def _load_snapshot_entry(
    manifest_path: Path, entry: Mapping[str, Any]
) -> RevolutionSnapshot:
    snapshot_path = _artifact_path(manifest_path, str(entry["snapshot_path"]))
    if _sha256_file(snapshot_path) != str(entry["snapshot_sha256"]):
        raise ValueError("snapshot hash mismatch")
    snapshot = read_snapshot(snapshot_path)
    if snapshot_fingerprint(snapshot) != str(entry["input_fingerprint"]):
        raise ValueError("snapshot input fingerprint mismatch")
    if (
        snapshot.seed != int(entry["seed"])
        or snapshot.corruption_level != str(entry["corruption_level"])
        or snapshot.revolution_index != int(entry["revolution_index"])
        or snapshot.split != str(entry["split"])
    ):
        raise ValueError("snapshot identity does not match its manifest entry")
    return snapshot


def _load_label_entry(manifest_path: Path, entry: Mapping[str, Any]) -> dict[str, Any]:
    label_path = _artifact_path(manifest_path, str(entry["label_path"]))
    if _sha256_file(label_path) != str(entry["label_sha256"]):
        raise ValueError("offline label hash mismatch")
    label = _read_object(label_path)
    if label.get("offline_truth_only") is not True:
        raise ValueError("scoring label is not marked offline-only")
    return label


def _group_entries(
    entries: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, int, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in entries:
        entry = dict(raw)
        key = (
            str(entry["split"]),
            int(entry["seed"]),
            str(entry["corruption_level"]),
        )
        groups[key].append(entry)
    for key, values in groups.items():
        values.sort(key=lambda item: int(item["revolution_index"]))
        revolutions = [int(item["revolution_index"]) for item in values]
        if revolutions != list(range(1, 7)):
            raise ValueError(f"scenario {key} does not contain six ordered revolutions")
    return dict(groups)


def _selected_calibration_groups(
    entries: Sequence[Mapping[str, Any]], split: str
) -> list[list[dict[str, Any]]]:
    groups = _group_entries(entries)
    seeds = sorted({seed for candidate_split, seed, _ in groups if candidate_split == split})
    requested = TRAIN_SEEDS_PER_SCALE if split == "train" else VALIDATION_SEEDS_PER_SCALE
    if len(seeds) < requested:
        raise ValueError(f"calibration manifest has too few {split} seeds")
    selected_seeds = set(seeds[:requested])
    selected = [
        values
        for (candidate_split, seed, _), values in sorted(groups.items())
        if candidate_split == split and seed in selected_seeds
    ]
    if not selected:
        raise ValueError(f"calibration manifest contains no {split} scenarios")
    return selected


def _active_track_ids(snapshot: RevolutionSnapshot, camera_id: str) -> tuple[str, ...]:
    return tuple(
        track.track_id
        for track in snapshot.tracks[camera_id]
        if track.track_state != "terminated" and track.samples
    )


def _pair_motion_cost(
    state_ned: Sequence[float] | None,
    geometry_cost: float,
    *,
    target_speed_mps: float,
) -> float:
    if state_ned is None:
        return 2.0
    state = np.asarray(state_ned, dtype=float)
    velocity = state[3:]
    speed = float(np.linalg.norm(velocity))
    speed_penalty = min(abs(speed - target_speed_mps) / max(target_speed_mps * 0.4, 1.0), 2.0)
    heading = math.degrees(math.atan2(float(velocity[1]), float(velocity[0])))

    def angle_error(reference: float) -> float:
        return abs((heading - reference + 180.0) % 360.0 - 180.0)

    heading_penalty = min(min(angle_error(180.0), angle_error(-150.0)) / 30.0, 2.0)
    vertical_penalty = min(abs(float(velocity[2])) / 10.0, 2.0)
    north, east, down = (float(value) for value in state[:3])
    corridor_penalty = float(
        north < 500.0
        or north > 3500.0
        or abs(east) > 900.0
        or not -250.0 <= down <= 50.0
    )
    return float(
        np.clip(
            0.45 * geometry_cost
            + 0.25 * speed_penalty
            + 0.20 * heading_penalty
            + 0.05 * vertical_penalty
            + 0.05 * corridor_penalty,
            0.0,
            2.0,
        )
    )


def _candidate_pairs(snapshot: RevolutionSnapshot) -> tuple[tuple[str, str], ...]:
    camera_a, camera_b = snapshot.camera_ids
    active_a = set(_active_track_ids(snapshot, camera_a))
    active_b = set(_active_track_ids(snapshot, camera_b))
    if snapshot.geometry_candidate_pairs:
        return tuple(
            (left, right)
            for left, right in snapshot.geometry_candidate_pairs
            if left in active_a and right in active_b
        )
    return tuple((left, right) for left in sorted(active_a) for right in sorted(active_b))


def _pair_history_count(
    prior_publications: Sequence[Mapping[str, Any]],
    revolution_index: int,
    pair: tuple[str, str],
) -> int:
    count = 1
    for publication in prior_publications:
        previous_revolution = int(publication["revolution_index"])
        if not revolution_index - 2 <= previous_revolution < revolution_index:
            continue
        previous_pairs = {
            (str(item["track_a_id"]), str(item["track_b_id"]))
            for item in publication["matches"]
        }
        count += pair in previous_pairs
    return count


def _build_pair_publication(
    snapshot: RevolutionSnapshot,
    prior_publications: Sequence[Mapping[str, Any]],
    *,
    target_speed_mps: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    camera_a, camera_b = snapshot.camera_ids
    track_a_ids = _active_track_ids(snapshot, camera_a)
    track_b_ids = _active_track_ids(snapshot, camera_b)
    index_a = {track_id: index for index, track_id in enumerate(track_a_ids)}
    index_b = {track_id: index for index, track_id in enumerate(track_b_ids)}
    qualities: dict[tuple[int, int], tuple[float, Any]] = {}
    rejection_counts: Counter[str] = Counter()
    for track_a_id, track_b_id in _candidate_pairs(snapshot):
        quality = evaluate_asynchronous_track_pair(snapshot, track_a_id, track_b_id)
        if not quality.gate_passed:
            rejection_counts[quality.rejection_reason or "geometry_gate"] += 1
            continue
        cost = _pair_motion_cost(
            quality.state_ned,
            quality.rule_cost,
            target_speed_mps=target_speed_mps,
        )
        qualities[(index_a[track_a_id], index_b[track_b_id])] = (cost, quality)

    target_count = len(track_a_ids)
    track_count = len(track_b_ids)
    size = target_count + track_count
    selected: list[dict[str, Any]] = []
    if size:
        matrix = np.full((size, size), 1.0e9, dtype=float)
        for key, (cost, _) in qualities.items():
            if cost < PAIR_UNMATCHED_COST:
                matrix[key] = cost
        for index in range(target_count):
            matrix[index, track_count + index] = PAIR_UNMATCHED_COST
        for index in range(track_count):
            matrix[target_count + index, index] = PAIR_UNMATCHED_COST
        matrix[target_count:, track_count:] = 0.0
        rows, columns = linear_sum_assignment(matrix)
        for row, column in zip(rows, columns):
            if row >= target_count or column >= track_count:
                continue
            if matrix[row, column] >= PAIR_UNMATCHED_COST:
                continue
            cost, quality = qualities[(int(row), int(column))]
            pair = (track_a_ids[int(row)], track_b_ids[int(column)])
            agreement_count = _pair_history_count(
                prior_publications, snapshot.revolution_index, pair
            )
            selected.append(
                {
                    "track_a_id": pair[0],
                    "track_b_id": pair[1],
                    "rule_cost": float(cost),
                    "decision_state": (
                        "confirmed" if agreement_count >= 2 else "tentative"
                    ),
                    "agreement_count": int(agreement_count),
                    "fit_rms_mrad": float(quality.fit_rms_mrad),
                    "intersection_angle_deg": float(quality.intersection_angle_deg),
                }
            )
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
        "matches": sorted(
            selected, key=lambda item: (item["track_a_id"], item["track_b_id"])
        ),
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "latency_ms": (time.perf_counter() - started) * 1000.0,
    }
    payload["publication_fingerprint"] = online_pair_publication_fingerprint(payload)
    validate_online_pair_publication(payload)
    return payload


def _hypothesis_id(
    snapshot: RevolutionSnapshot, track_a_id: str, track_b_id: str
) -> str:
    digest = hashlib.sha256(
        _canonical_json(
            {
                "seed": snapshot.seed,
                "corruption_level": snapshot.corruption_level,
                "track_a_id": track_a_id,
                "track_b_id": track_b_id,
            }
        )
    ).hexdigest()
    return f"H-{digest[:16]}"


def _create_prior_hypotheses(
    snapshot: RevolutionSnapshot,
    snapshots_by_revolution: Mapping[int, RevolutionSnapshot],
    pair_publications: Sequence[Mapping[str, Any]],
    publication_registry: Mapping[str, Mapping[str, Any]],
    hypotheses_by_pair: dict[tuple[str, str], TargetHypothesis],
    failure_counts: Counter[str],
) -> None:
    latest_confirmed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for publication in pair_publications:
        if int(publication["revolution_index"]) >= snapshot.revolution_index:
            continue
        for match in publication["matches"]:
            if str(match["decision_state"]) != "confirmed":
                continue
            key = (str(match["track_a_id"]), str(match["track_b_id"]))
            latest_confirmed[key] = publication
    for key, publication in sorted(latest_confirmed.items()):
        if key in hypotheses_by_pair:
            continue
        try:
            pair = ConfirmedTrackPair.from_online_publication(
                publication, key[0], key[1]
            )
            hypothesis = form_target_hypothesis(
                _hypothesis_id(snapshot, key[0], key[1]),
                snapshots_by_revolution,
                (pair,),
                creation_revolution_index=snapshot.revolution_index,
                online_publications=publication_registry,
            )
        except (CausalityError, GeometryFitError, ValueError, np.linalg.LinAlgError) as error:
            failure_counts[type(error).__name__] += 1
            continue
        hypotheses_by_pair[key] = hypothesis


def _process_online_scenario(
    snapshots: Sequence[RevolutionSnapshot],
    *,
    target_speed_mps: float,
    routes: Sequence[str] = (),
    model: TargetTrackCostGNN | None = None,
    normalizer: FeatureNormalizer | None = None,
) -> tuple[dict[str, Any], tuple[_GraphRecord, ...]]:
    ordered = tuple(sorted(snapshots, key=lambda item: item.revolution_index))
    if [item.revolution_index for item in ordered] != list(range(1, 7)):
        raise ValueError("online scenario requires six ordered revolution snapshots")
    identity = {
        (item.seed, item.split, item.corruption_level, item.protocol_fingerprint)
        for item in ordered
    }
    if len(identity) != 1:
        raise ValueError("online scenario snapshots do not share one identity")
    normalized_routes = tuple(str(route) for route in routes)
    if any(route not in ROUTES for route in normalized_routes) or len(
        set(normalized_routes)
    ) != len(normalized_routes):
        raise ValueError("V5 target-track routes are invalid")
    if "gnn_assisted" in normalized_routes and (model is None or normalizer is None):
        raise ValueError("GNN route requires a frozen model and normalizer")

    snapshots_by_revolution: dict[int, RevolutionSnapshot] = {}
    pair_publications: list[dict[str, Any]] = []
    publication_registry: dict[str, Mapping[str, Any]] = {}
    hypotheses_by_pair: dict[tuple[str, str], TargetHypothesis] = {}
    target_publication_history: dict[
        tuple[str, str], list[TargetTrackPublication]
    ] = defaultdict(list)
    graph_records: list[_GraphRecord] = []
    revolutions: list[dict[str, Any]] = []
    hypothesis_failure_counts: Counter[str] = Counter()
    gate = TargetTrackGate()

    for snapshot in ordered:
        snapshots_by_revolution[snapshot.revolution_index] = snapshot
        _create_prior_hypotheses(
            snapshot,
            snapshots_by_revolution,
            pair_publications,
            publication_registry,
            hypotheses_by_pair,
            hypothesis_failure_counts,
        )
        hypotheses = tuple(
            sorted(
                (
                    item
                    for item in hypotheses_by_pair.values()
                    if item.created_revolution_index < snapshot.revolution_index
                ),
                key=lambda item: item.hypothesis_id,
            )
        )
        graphs = build_camera_graphs(snapshot, hypotheses, gate=gate)
        camera_payloads: dict[str, Any] = {}
        for camera_id, graph in graphs.items():
            graph_records.append(_GraphRecord(snapshot, hypotheses, graph))
            route_payloads: dict[str, Any] = {}
            for route_name in normalized_routes:
                internal_route = ROUTE_TO_INTERNAL[route_name]
                started = time.perf_counter()
                assignment = solve_target_track_assignment(
                    graph,
                    internal_route,
                    model=model if internal_route == "gnn_assisted" else None,
                    normalizer=(
                        normalizer if internal_route == "gnn_assisted" else None
                    ),
                    unmatched_cost=gate.unmatched_cost,
                )
                publications = publish_with_confirmation(
                    graph,
                    assignment,
                    target_publication_history[(route_name, camera_id)],
                )
                target_publication_history[(route_name, camera_id)].extend(publications)
                latency_ms = (time.perf_counter() - started) * 1000.0
                route_payloads[route_name] = {
                    "internal_route": internal_route,
                    "latency_ms": latency_ms,
                    "duplicate_assignment_count": assignment.duplicate_assignment_count,
                    "publications": [item.to_dict() for item in publications],
                }
            camera_payloads[camera_id] = {
                "whitelist_fingerprint": graph.whitelist_fingerprint,
                "hypothesis_ids": list(graph.hypothesis_ids),
                "track_ids": list(graph.track_ids),
                "edge_count": int(graph.edge_index.shape[1]),
                "rejection_counts": dict(graph.rejection_counts),
                "routes": route_payloads,
            }
        pair_publication = _build_pair_publication(
            snapshot,
            pair_publications,
            target_speed_mps=target_speed_mps,
        )
        pair_publications.append(pair_publication)
        publication_registry[pair_publication["publication_fingerprint"]] = pair_publication
        revolutions.append(
            {
                "revolution_index": snapshot.revolution_index,
                "input_fingerprint": snapshot_fingerprint(snapshot),
                "active_hypothesis_ids": [item.hypothesis_id for item in hypotheses],
                "cameras": camera_payloads,
            }
        )

    first = ordered[0]
    payload = {
        "schema_version": SCENARIO_PUBLICATION_SCHEMA,
        "online_anonymous": True,
        "seed": first.seed,
        "split": first.split,
        "corruption_level": first.corruption_level,
        "protocol_fingerprint": first.protocol_fingerprint,
        "target_count": first.target_count,
        "routes": list(normalized_routes),
        "pair_publications": pair_publications,
        "hypotheses": [
            item.to_dict()
            for item in sorted(
                hypotheses_by_pair.values(), key=lambda value: value.hypothesis_id
            )
        ],
        "hypothesis_failure_counts": dict(sorted(hypothesis_failure_counts.items())),
        "revolutions": revolutions,
    }
    forbidden = _find_forbidden_online_field(payload)
    if forbidden is not None:
        raise RuntimeError(f"online scenario publication leaked {forbidden}")
    return payload, tuple(graph_records)


def _dominant_identity(counts: Mapping[str, Any]) -> str | None:
    ranked = sorted(
        ((int(count), str(identity)) for identity, count in counts.items()),
        reverse=True,
    )
    if not ranked or ranked[0][1].startswith("FA-"):
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _hypothesis_identity(
    hypothesis: TargetHypothesis,
    labels_by_revolution: Mapping[int, Mapping[str, Any]],
) -> str | None:
    votes: list[str] = []
    for pair in hypothesis.confirmed_pairs:
        labels = labels_by_revolution.get(pair.revolution_index)
        if labels is None:
            continue
        track_counts = labels.get("track_truth_counts", {})
        identity_a = _dominant_identity(track_counts.get(pair.track_a_id, {}))
        identity_b = _dominant_identity(track_counts.get(pair.track_b_id, {}))
        if identity_a is not None and identity_a == identity_b:
            votes.append(identity_a)
    if not votes:
        return None
    counts = Counter(votes)
    selected, selected_count = counts.most_common(1)[0]
    if sum(count == selected_count for count in counts.values()) > 1:
        return None
    return selected


def _training_examples_for_scenario(
    graph_records: Sequence[_GraphRecord],
    labels_by_revolution: Mapping[int, Mapping[str, Any]],
    *,
    target_count: int,
) -> list[TargetTrackTrainingExample]:
    examples: list[TargetTrackTrainingExample] = []
    for record in graph_records:
        graph = record.graph
        if graph.edge_index.shape[1] == 0:
            continue
        hypothesis_truth = {
            item.hypothesis_id: _hypothesis_identity(item, labels_by_revolution)
            for item in record.hypotheses
        }
        current_counts = labels_by_revolution[record.snapshot.revolution_index][
            "track_truth_counts"
        ]
        track_truth = {
            track_id: _dominant_identity(current_counts.get(track_id, {}))
            for track_id in graph.track_ids
        }
        labels = np.asarray(
            [
                float(
                    hypothesis_truth[graph.hypothesis_ids[int(target_index)]]
                    is not None
                    and hypothesis_truth[graph.hypothesis_ids[int(target_index)]]
                    == track_truth[graph.track_ids[int(track_index)]]
                )
                for target_index, track_index in graph.edge_index.T
            ],
            dtype=np.float32,
        )
        if not np.any(labels == 1.0):
            continue
        snapshot = record.snapshot
        examples.append(
            TargetTrackTrainingExample(
                example_id=(
                    f"{target_count}-{snapshot.split}-{snapshot.seed}-"
                    f"{snapshot.corruption_level}-r{snapshot.revolution_index}-"
                    f"{graph.camera_id}"
                ),
                split=snapshot.split,
                target_count=target_count,
                seed=snapshot.seed,
                graph=graph,
                edge_labels=labels,
            )
        )
    return examples


def _initialization_seeds(count: int) -> tuple[int, ...]:
    if count < 5:
        raise ValueError("V5 target-track training requires at least five initializations")
    values = list(DEFAULT_INITIALIZATION_SEEDS)
    candidate = 6607
    while len(values) < count:
        if candidate not in values:
            values.append(candidate)
        candidate += 1009
    return tuple(values[:count])


def train_and_freeze(
    *,
    calibration_manifests: Mapping[int, Path],
    output_dir: Path,
    scale_sampling_policy: str,
    initialization_count: int,
) -> str | Path:
    """Train one balanced 40/60/100 model using calibration labels only."""

    normalized = {int(count): Path(path).resolve() for count, path in calibration_manifests.items()}
    if set(normalized) != set(SUPPORTED_TARGET_COUNTS):
        raise ValueError("V5 training requires calibration manifests for 40/60/100")
    if scale_sampling_policy != SCALE_SAMPLING_POLICY:
        raise ValueError("V5 training scale sampling policy is invalid")
    initialization_count = int(initialization_count)
    examples: list[TargetTrackTrainingExample] = []
    manifest_hashes: dict[str, str] = {}
    for target_count in SUPPORTED_TARGET_COUNTS:
        manifest_path = normalized[target_count]
        payload = _read_object(manifest_path)
        protocol = _protocol_from_manifest(payload, expected_target_count=target_count)
        if payload.get("phase") != "calibration":
            raise ValueError("model training accepts calibration manifests only")
        entries = [dict(item) for item in payload.get("entries", ())]
        if not entries or any(str(item.get("split")) == "test" for item in entries):
            raise ValueError("test data cannot enter V5 model training")
        manifest_hashes[str(target_count)] = _sha256_file(manifest_path)
        for split in ("train", "validation"):
            for group in _selected_calibration_groups(entries, split):
                snapshots = [_load_snapshot_entry(manifest_path, entry) for entry in group]
                labels_by_revolution = {
                    int(entry["revolution_index"]): _load_label_entry(manifest_path, entry)
                    for entry in group
                }
                _, graph_records = _process_online_scenario(
                    snapshots,
                    target_speed_mps=protocol.target_speed_mps,
                )
                examples.extend(
                    _training_examples_for_scenario(
                        graph_records,
                        labels_by_revolution,
                        target_count=target_count,
                    )
                )
    available = {
        (split, count): sum(
            item.split == split and item.target_count == count for item in examples
        )
        for split in ("train", "validation")
        for count in SUPPORTED_TARGET_COUNTS
    }
    if any(count == 0 for count in available.values()):
        raise RuntimeError(f"calibration did not produce balanced positive graphs: {available}")

    output_dir = Path(output_dir).resolve()
    model_dir = output_dir / "model"
    outcome = train_and_freeze_five_initializations(
        examples,
        model_dir,
        config=FiveInitializationConfig(
            initialization_seeds=_initialization_seeds(initialization_count),
            max_epochs=TRAINING_MAX_EPOCHS,
            patience=TRAINING_PATIENCE,
        ),
    )
    freeze_manifest_path = model_dir / "freeze_manifest.json"
    freeze_manifest_hash = _sha256_file(freeze_manifest_path)
    model_fingerprint = payload_fingerprint(
        {
            "freeze_manifest_sha256": freeze_manifest_hash,
            "selected_initialization_seed": outcome.selected_initialization_seed,
            "scale_sampling_policy": scale_sampling_policy,
            "calibration_manifest_sha256": manifest_hashes,
        }
    )
    example_scale = {item.example_id: item.target_count for item in examples}
    selected_counts = {
        f"train_{count}": sum(
            example_scale[example_id] == count
            for example_id in outcome.train_example_ids
        )
        for count in SUPPORTED_TARGET_COUNTS
    }
    selected_counts.update(
        {
            f"validation_{count}": sum(
                example_scale[example_id] == count
                for example_id in outcome.validation_example_ids
            )
            for count in SUPPORTED_TARGET_COUNTS
        }
    )
    native = {
        "schema_version": NATIVE_FREEZE_SCHEMA,
        "model_fingerprint": model_fingerprint,
        "model_directory": str(model_dir),
        "freeze_manifest": str(freeze_manifest_path),
        "freeze_manifest_sha256": freeze_manifest_hash,
        "scale_sampling_policy": scale_sampling_policy,
        "initialization_count": len(outcome.initialization_results),
        "training_splits": ["train"],
        "selection_splits": ["validation"],
        "test_data_accessed": False,
        "test_labels_accessed": False,
        "acceptance_passed": False,
        "formal_use_allowed": False,
        "formal_route_markers": {},
        "evidence_status": "diagnostic_model_freeze_without_acceptance_threshold",
        "calibration_manifest_sha256": manifest_hashes,
        "available_example_count": {
            f"{split}_{count}": int(value)
            for (split, count), value in sorted(available.items())
        },
        "selected_balanced_example_count": selected_counts,
        "selected_initialization_seed": outcome.selected_initialization_seed,
        "selected_validation_loss": outcome.selected_validation_loss,
    }
    return _write_json(output_dir / "native_model_freeze.json", native)


def _load_v5_frozen_model(
    model_freeze: Path,
) -> tuple[TargetTrackCostGNN, FeatureNormalizer, dict[str, Any]]:
    wrapper_path = Path(model_freeze).resolve()
    wrapper = _read_object(wrapper_path)
    if wrapper.get("schema_version") == NATIVE_FREEZE_SCHEMA:
        native_path = wrapper_path
        native = wrapper
    else:
        if wrapper.get("schema_version") != V5_MODEL_FREEZE_SCHEMA:
            raise ValueError("unsupported V5 target-track model wrapper")
        unsigned_wrapper = dict(wrapper)
        stored_wrapper_fingerprint = str(
            unsigned_wrapper.pop("freeze_fingerprint", "")
        )
        if (
            not stored_wrapper_fingerprint
            or stored_wrapper_fingerprint != payload_fingerprint(unsigned_wrapper)
        ):
            raise ValueError("V5 model wrapper fingerprint mismatch")
        if (
            wrapper.get("test_data_accessed") is not False
            or wrapper.get("test_labels_accessed") is not False
            or wrapper.get("model_frozen_before_test") is not True
        ):
            raise ValueError("V5 wrapper model does not prove test isolation")
        native_path = Path(str(wrapper.get("native_model_freeze") or "")).resolve()
        if not native_path.is_file() or _sha256_file(native_path) != wrapper.get(
            "native_model_freeze_sha256"
        ):
            raise ValueError("V5 native model freeze changed")
        native = _read_object(native_path)
        if wrapper.get("model_fingerprint") != native.get("model_fingerprint"):
            raise ValueError("V5 wrapper and native model fingerprints disagree")
    if native.get("schema_version") != NATIVE_FREEZE_SCHEMA:
        raise ValueError("unsupported native target-track model freeze")
    if (
        native.get("test_data_accessed") is not False
        or native.get("test_labels_accessed") is not False
        or native.get("training_splits") != ["train"]
        or native.get("selection_splits") != ["validation"]
        or native.get("scale_sampling_policy") != SCALE_SAMPLING_POLICY
        or int(native.get("initialization_count", 0)) < 5
    ):
        raise ValueError("native target-track model violates split isolation")
    freeze_manifest = Path(str(native["freeze_manifest"])).resolve()
    if _sha256_file(freeze_manifest) != native.get("freeze_manifest_sha256"):
        raise ValueError("native target-track freeze manifest changed")
    model_dir = Path(str(native["model_directory"])).resolve()
    model, normalizer, _ = load_frozen_model(model_dir)
    return model, normalizer, native


def _validate_online_test_manifest_binding(
    test_manifest: Path,
    model_freeze: Path,
) -> dict[str, Any]:
    manifest = _read_object(test_manifest)
    forbidden = _find_forbidden_online_field(manifest)
    if forbidden is not None:
        raise ValueError(
            "publish_test requires an online-only manifest; "
            f"offline field found at {forbidden}"
        )
    if manifest.get("schema_version") != V5_ONLINE_TEST_MANIFEST_SCHEMA:
        raise ValueError("unsupported V5 online test manifest schema")
    if (
        manifest.get("phase") != "test"
        or manifest.get("online_only") is not True
        or manifest.get("test_access_allowed") is not True
    ):
        raise ValueError("V5 online manifest violates test-input isolation")

    unsigned = dict(manifest)
    online_fingerprint = str(unsigned.pop("online_manifest_fingerprint", ""))
    if (
        not online_fingerprint
        or online_fingerprint != payload_fingerprint(unsigned)
    ):
        raise ValueError("V5 online manifest fingerprint mismatch")

    model_hash = _sha256_file(model_freeze)
    if str(manifest.get("model_freeze_sha256") or "") != model_hash:
        raise ValueError("V5 online manifest is bound to another model freeze")
    return manifest


def publish_test(
    *,
    test_manifest: Path,
    model_freeze: Path,
    output_dir: Path,
    routes: Sequence[str],
) -> str | Path:
    """Publish both V5 routes from an online-only held-out manifest."""

    test_manifest = Path(test_manifest).resolve()
    model_freeze = Path(model_freeze).resolve()
    manifest = _validate_online_test_manifest_binding(test_manifest, model_freeze)
    normalized_routes = tuple(str(route) for route in routes)
    if normalized_routes != ROUTES:
        raise ValueError("V5 publication requires rule_baseline and gnn_assisted")
    protocol = _protocol_from_manifest(manifest)
    if protocol.target_count not in SUPPORTED_TARGET_COUNTS:
        raise ValueError("V5 publication target scale must be 40, 60, or 100")
    entries = [dict(item) for item in manifest.get("entries", ())]
    if not entries or any(str(item.get("split")) != "test" for item in entries):
        raise ValueError("online test manifest contains a non-test entry")
    model, normalizer, native = _load_v5_frozen_model(model_freeze)
    if manifest.get("model_fingerprint") != native.get("model_fingerprint"):
        raise ValueError("V5 online manifest and native model identities disagree")

    output_dir = Path(output_dir).resolve()
    scenario_entries: list[dict[str, Any]] = []
    for (_, seed, corruption_level), group in sorted(_group_entries(entries).items()):
        snapshots = [_load_snapshot_entry(test_manifest, entry) for entry in group]
        scenario, _ = _process_online_scenario(
            snapshots,
            target_speed_mps=protocol.target_speed_mps,
            routes=normalized_routes,
            model=model,
            normalizer=normalizer,
        )
        relative = Path("scenarios") / str(seed) / f"{corruption_level}.json"
        scenario_path = _write_json(output_dir / relative, scenario)
        scenario_entries.append(
            {
                "seed": seed,
                "corruption_level": corruption_level,
                "scenario_path": relative.as_posix(),
                "scenario_sha256": _sha256_file(scenario_path),
            }
        )
    payload = {
        "schema_version": PUBLICATION_MANIFEST_SCHEMA,
        "routes": list(ROUTES),
        "test_labels_accessed": False,
        "online_anonymous": True,
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "model_fingerprint": native["model_fingerprint"],
        "model_freeze": str(Path(model_freeze).resolve()),
        "model_freeze_sha256": _sha256_file(model_freeze),
        "online_test_manifest": str(test_manifest),
        "online_test_manifest_sha256": _sha256_file(test_manifest),
        "online_manifest_fingerprint": manifest["online_manifest_fingerprint"],
        "online_entry_matrix_fingerprint": _entry_matrix_fingerprint(entries),
        "entries": scenario_entries,
    }
    forbidden = _find_forbidden_online_field(payload)
    if forbidden is not None:
        raise RuntimeError(f"publication manifest leaked {forbidden}")
    return _write_json(output_dir / "publication_manifest.json", payload)


def _scenario_label_map(
    manifest_path: Path, group: Sequence[Mapping[str, Any]]
) -> dict[int, dict[str, Any]]:
    return {
        int(entry["revolution_index"]): _load_label_entry(manifest_path, entry)
        for entry in group
    }


def _validate_hypothesis_provenance(
    hypothesis: TargetHypothesis,
    pair_registry: Mapping[str, Mapping[str, Any]],
) -> None:
    for pair in hypothesis.confirmed_pairs:
        publication = pair_registry.get(pair.publication_fingerprint)
        if publication is None:
            raise ValueError("published hypothesis references a missing online pair publication")
        pair.validate_publication(publication)


def _route_row(
    scenario: Mapping[str, Any],
    labels_by_revolution: Mapping[int, Mapping[str, Any]],
    route_name: str,
) -> dict[str, Any]:
    hypotheses = {
        item.hypothesis_id: item
        for item in (
            TargetHypothesis.from_dict(payload)
            for payload in scenario.get("hypotheses", ())
        )
    }
    pair_registry = {
        str(payload["publication_fingerprint"]): payload
        for payload in scenario.get("pair_publications", ())
    }
    for publication in pair_registry.values():
        validate_online_pair_publication(publication)
    for hypothesis in hypotheses.values():
        _validate_hypothesis_provenance(hypothesis, pair_registry)
    hypothesis_truth = {
        hypothesis_id: _hypothesis_identity(hypothesis, labels_by_revolution)
        for hypothesis_id, hypothesis in hypotheses.items()
    }
    valid_hypotheses = {
        hypothesis_id: identity
        for hypothesis_id, identity in hypothesis_truth.items()
        if identity is not None
    }
    matched_count = 0
    correct_count = 0
    false_count = 0
    unmatched_count = 0
    confirmed_count = 0
    confirmed_correct_count = 0
    tentative_count = 0
    one_to_one_violations = 0
    latencies: list[float] = []
    coverage_values: list[float] = []
    target_count = int(scenario.get("target_count") or 0)

    for revolution in scenario.get("revolutions", ()):
        revolution_index = int(revolution["revolution_index"])
        labels = labels_by_revolution[revolution_index]
        track_counts = labels["track_truth_counts"]
        for camera in revolution["cameras"].values():
            route_payload = camera.get("routes", {}).get(route_name)
            if not isinstance(route_payload, Mapping):
                raise ValueError("scenario publication is missing one V5 route")
            latency = float(route_payload["latency_ms"])
            if latency < 0.0 or not math.isfinite(latency):
                raise ValueError("published target-track latency is invalid")
            latencies.append(latency)
            publications = [
                TargetTrackPublication.from_dict(value)
                for value in route_payload.get("publications", ())
            ]
            local_ids = [
                item.local_track_id
                for item in publications
                if item.local_track_id is not None
            ]
            hypothesis_ids = [item.hypothesis_id for item in publications]
            one_to_one_violations += len(local_ids) - len(set(local_ids))
            one_to_one_violations += len(hypothesis_ids) - len(set(hypothesis_ids))
            correctly_covered: set[str] = set()
            for publication in publications:
                expected = hypothesis_truth.get(publication.hypothesis_id)
                if publication.decision_state == "confirmed":
                    confirmed_count += 1
                elif publication.decision_state == "tentative":
                    tentative_count += 1
                if publication.local_track_id is None:
                    unmatched_count += 1
                    continue
                matched_count += 1
                actual = _dominant_identity(
                    track_counts.get(publication.local_track_id, {})
                )
                correct = expected is not None and expected == actual
                if correct:
                    correct_count += 1
                    correctly_covered.add(str(expected))
                    if publication.decision_state == "confirmed":
                        confirmed_correct_count += 1
                else:
                    false_count += 1
            coverage_values.append(len(correctly_covered) / max(target_count, 1))
    hypothesis_count = len(hypotheses)
    identity_rate = len(valid_hypotheses) / max(hypothesis_count, 1)
    current_identity_rate = correct_count / max(matched_count, 1)
    coverage = float(np.mean(coverage_values)) if coverage_values else 0.0
    return {
        "route_name": route_name,
        "target_count": target_count,
        "seed": int(scenario["seed"]),
        "corruption_level": str(scenario["corruption_level"]),
        "valid_hypothesis_identity_count": len(valid_hypotheses),
        "hypothesis_count": hypothesis_count,
        "valid_hypothesis_identity_rate": identity_rate,
        "current_track_identity_correct_count": correct_count,
        "current_track_identity_match_count": matched_count,
        "current_track_identity_rate": current_identity_rate,
        "coverage": coverage,
        "false_match_count": false_count,
        "unmatched_count": unmatched_count,
        "one_to_one_violation_count": one_to_one_violations,
        "confirmed_count": confirmed_count,
        "confirmed_correct_count": confirmed_correct_count,
        "tentative_count": tentative_count,
        "latency_mean_ms": float(np.mean(latencies)) if latencies else 0.0,
        "latency_p95_ms": float(np.percentile(latencies, 95)) if latencies else 0.0,
    }


def _aggregate_route_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    summed_names = (
        "valid_hypothesis_identity_count",
        "hypothesis_count",
        "current_track_identity_correct_count",
        "current_track_identity_match_count",
        "false_match_count",
        "unmatched_count",
        "one_to_one_violation_count",
        "confirmed_count",
        "confirmed_correct_count",
        "tentative_count",
    )
    result: dict[str, Any] = {
        "scenario_count": len(rows),
        **{
            name: int(sum(int(row[name]) for row in rows))
            for name in summed_names
        },
        "coverage": float(np.mean([float(row["coverage"]) for row in rows])),
        "latency_mean_ms": float(
            np.mean([float(row["latency_mean_ms"]) for row in rows])
        ),
        "latency_p95_ms": float(
            np.percentile([float(row["latency_p95_ms"]) for row in rows], 95)
        ),
    }
    result["valid_hypothesis_identity_rate"] = result[
        "valid_hypothesis_identity_count"
    ] / max(result["hypothesis_count"], 1)
    result["current_track_identity_rate"] = result[
        "current_track_identity_correct_count"
    ] / max(result["current_track_identity_match_count"], 1)
    result["confirmed_correct_rate"] = result["confirmed_correct_count"] / max(
        result["confirmed_count"], 1
    )
    return result


def score_publications(
    *,
    publication_manifest: Path,
    test_manifest: Path,
    output_dir: Path,
) -> str | Path:
    """Open held-out labels only after both route publications are immutable."""

    publication_manifest = Path(publication_manifest).resolve()
    publications = _read_object(publication_manifest)
    forbidden = _find_forbidden_online_field(publications)
    if forbidden is not None:
        raise ValueError(f"publication manifest contains offline field {forbidden}")
    if publications.get("schema_version") != PUBLICATION_MANIFEST_SCHEMA:
        raise ValueError("unsupported V5 target-track publication manifest")
    if publications.get("test_labels_accessed") is not False:
        raise ValueError("online publication reports test-label access")
    if tuple(publications.get("routes", ())) != ROUTES:
        raise ValueError("V5 publication manifest does not contain both routes")

    test_manifest = Path(test_manifest).resolve()
    full_manifest = _read_object(test_manifest)
    protocol = _protocol_from_manifest(full_manifest)
    if full_manifest.get("phase") != "test":
        raise ValueError("offline scoring accepts a test manifest only")
    entries = [dict(item) for item in full_manifest.get("entries", ())]
    if _entry_matrix_fingerprint(entries) != publications.get(
        "online_entry_matrix_fingerprint"
    ):
        raise ValueError("offline labels do not describe the published online inputs")
    if protocol.fingerprint != publications.get("protocol_fingerprint"):
        raise ValueError("publication and scoring protocol fingerprints disagree")
    groups = _group_entries(entries)
    published_keys = {
        ("test", int(item["seed"]), str(item["corruption_level"]))
        for item in publications.get("entries", ())
    }
    if published_keys != set(groups):
        raise ValueError("publication and scoring scenario sets disagree")
    rows: list[dict[str, Any]] = []
    for item in publications.get("entries", ()):
        seed = int(item["seed"])
        corruption_level = str(item["corruption_level"])
        key = ("test", seed, corruption_level)
        if key not in groups:
            raise ValueError("publication scenario has no matching held-out labels")
        scenario_path = _artifact_path(
            publication_manifest, str(item["scenario_path"])
        )
        if _sha256_file(scenario_path) != str(item["scenario_sha256"]):
            raise ValueError("scenario publication hash mismatch")
        scenario = _read_object(scenario_path)
        forbidden = _find_forbidden_online_field(scenario)
        if forbidden is not None:
            raise ValueError(f"scenario publication contains offline field {forbidden}")
        if scenario.get("schema_version") != SCENARIO_PUBLICATION_SCHEMA:
            raise ValueError("unsupported target-track scenario publication")
        expected_inputs = {
            int(entry["revolution_index"]): str(entry["input_fingerprint"])
            for entry in groups[key]
        }
        actual_inputs = {
            int(item["revolution_index"]): str(item["input_fingerprint"])
            for item in scenario.get("revolutions", ())
        }
        if actual_inputs != expected_inputs:
            raise ValueError("scenario publication input history does not match scoring data")
        labels_by_revolution = _scenario_label_map(test_manifest, groups[key])
        for route_name in ROUTES:
            rows.append(
                _route_row(scenario, labels_by_revolution, route_name)
            )
    routes = {
        route_name: _aggregate_route_rows(
            [row for row in rows if row["route_name"] == route_name]
        )
        for route_name in ROUTES
    }
    metrics = {
        "schema_version": METRICS_SCHEMA,
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "routes": routes,
        "rows": rows,
        "offline_labels_opened_during_scoring": True,
        "test_labels_used_for_model_selection": False,
        "formal_acceptance_claimed": False,
        "acceptance_status": "not_assessed",
        "evidence_status": "measured_held_out_metrics",
        "publication_manifest": str(publication_manifest),
        "publication_manifest_sha256": _sha256_file(publication_manifest),
    }
    return _write_json(Path(output_dir).resolve() / "metrics.json", metrics)


__all__ = ["publish_test", "score_publications", "train_and_freeze"]
