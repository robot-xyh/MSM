"""Public freeze and publish entry points for the main online benchmark."""

from __future__ import annotations

from dataclasses import asdict, replace
import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from dual_optical_100target_gnn.dataset import canonical_json_sha256
from dual_optical_100target_gnn.graph import GeometryGate
from dual_optical_100target_gnn.loader import sha256_file
from dual_optical_100target_gnn.schema import EDGE_FEATURE_NAMES, GraphLabels, OnlineGraph
from dual_optical_online_benchmark.contracts import (
    AssociationPublication,
    BenchmarkProtocol,
    RevolutionSnapshot,
    benchmark_protocol_from_mapping,
)
from dual_optical_online_benchmark.dataset import (
    DATASET_SCHEMA_VERSION,
    LEGACY_DATASET_SCHEMA_VERSION,
    load_dataset_manifest,
)

from .benchmark_adapter import (
    SharedSnapshotLightweightAdapter,
    _build_candidate_snapshot,
    read_shared_snapshot as read_snapshot,
    shared_snapshot_fingerprint as snapshot_fingerprint,
)
from .models import (
    GEOMETRY_COMPONENT_NAMES,
    LOGISTIC_C_GRID,
    MODEL_KINDS,
    PROBABILITY_THRESHOLD_GRID,
    UNMATCHED_COST_GRID,
    fit_all_models,
)
from .online import FrozenRoute, OnlineLightweightAdapter
from .pipeline import (
    MINIMUM_CONDITIONAL_PRECISION,
    ValidationSelectionError,
    _rank_validation_rows,
    _validation_rows,
)


FREEZE_SCHEMA_VERSION = "dual-optical-lightweight-online-benchmark-freeze-v2"
ROUTE_NAME = "lightweight"
ROUTE_VERSION = "dual-optical-lightweight-online-v2"
FREEZE_FILE_NAME = "lightweight_freeze_manifest.json"
FREEZE_FAILURE_FILE_NAME = "freeze_failure.json"
FREEZE_FAILURE_SCHEMA_VERSION = "dual-optical-lightweight-freeze-failure-v1"


def _best_route_rows(
    ranked_rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for row in ranked_rows:
        selected.setdefault(str(row["model_kind"]), dict(row))
    if set(selected) != set(MODEL_KINDS):
        raise ValueError("validation did not produce all four lightweight route families")
    return selected


def _rank_diagnostic_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rank failed validation rows for an explicitly offline-only replay.

    Formal freezing never calls this path. The diagnostic order first minimizes
    false correspondence risk, then uses recall and F1 to break ties.
    """

    nonzero = [dict(row) for row in rows if int(row.get("selected_count", 0)) > 0]
    if not nonzero:
        raise ValidationSelectionError(
            "diagnostic validation produced no nonzero assignment",
            reason_code="zero_validation_assignments",
            validation_rows=rows,
            best_validation_result=None,
        )
    ranked = sorted(
        nonzero,
        key=lambda row: (
            -float(row["conditional_precision"]),
            -float(row["macro_recall"]),
            -float(row["macro_f1"]),
            int(row["false_association_count"]),
            int(row["duplicate_identity_match_count"]),
            str(row["model_kind"]),
            str(row["model_id"]),
            float(row["probability_threshold"]),
            float(row["unmatched_cost"]),
        ),
    )
    return [
        {
            "rank": rank,
            **row,
            "selection_eligible": False,
            "diagnostic_selection_only": True,
        }
        for rank, row in enumerate(ranked, start=1)
    ]


def _candidate_evidence(
    data: Sequence[tuple[OnlineGraph, GraphLabels]],
) -> dict[str, int | float]:
    positive = sum(int(np.sum(labels.edge_labels > 0.5)) for _, labels in data)
    negative = sum(int(np.sum(labels.edge_labels <= 0.5)) for _, labels in data)
    expected = sum(len(labels.expected_identities) for _, labels in data)
    return {
        "snapshot_count": len(data),
        "candidate_positive_edge_count": positive,
        "candidate_negative_edge_count": negative,
        "expected_true_edge_opportunity_count": expected,
        "candidate_true_edge_retention_rate": (
            float(positive / expected) if expected else 0.0
        ),
    }


def _bundle_payload(
    routes: Sequence[FrozenRoute],
    *,
    selected_route_id: str,
    geometry_gate: Mapping[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "dual-optical-lightweight-online-model-bundle-v1",
        "selected_route_id": selected_route_id,
        "routes": [item.to_dict() for item in routes],
        "geometry_gate": dict(geometry_gate),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "geometry_component_names": list(GEOMETRY_COMPONENT_NAMES),
        "online_policy": {
            "truth_id": False,
            "actor_name": False,
            "offline_labels": False,
            "future_observations": False,
            "one_candidate_graph_for_all_routes": True,
            "candidate_graph_from_frozen_shared_tracker_only": True,
        },
    }
    payload["bundle_fingerprint_sha256"] = canonical_json_sha256(payload)
    return payload


def _load_model_bundle(
    path: Path,
) -> tuple[dict[str, Any], tuple[FrozenRoute, ...]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {
        "schema_version",
        "selected_route_id",
        "routes",
        "geometry_gate",
        "edge_feature_names",
        "geometry_component_names",
        "online_policy",
        "bundle_fingerprint_sha256",
    }
    if set(payload) != required:
        raise ValueError("online model bundle fields do not match the contract")
    if payload["schema_version"] != "dual-optical-lightweight-online-model-bundle-v1":
        raise ValueError("unsupported online model bundle schema")
    fingerprint_payload = {
        key: value
        for key, value in payload.items()
        if key != "bundle_fingerprint_sha256"
    }
    if payload["bundle_fingerprint_sha256"] != canonical_json_sha256(
        fingerprint_payload
    ):
        raise ValueError("online model bundle fingerprint mismatch")
    if payload["edge_feature_names"] != list(EDGE_FEATURE_NAMES):
        raise ValueError("online model bundle edge feature contract mismatch")
    if payload["geometry_component_names"] != list(GEOMETRY_COMPONENT_NAMES):
        raise ValueError("online model bundle geometry component contract mismatch")
    if payload["online_policy"] != {
        "truth_id": False,
        "actor_name": False,
        "offline_labels": False,
        "future_observations": False,
        "one_candidate_graph_for_all_routes": True,
        "candidate_graph_from_frozen_shared_tracker_only": True,
    }:
        raise ValueError("online model bundle policy is invalid")
    routes = tuple(FrozenRoute.from_dict(item) for item in payload["routes"])
    if {item.route_id for item in routes} != set(MODEL_KINDS):
        raise ValueError("online model bundle must contain all four route families")
    if payload["selected_route_id"] not in {item.route_id for item in routes}:
        raise ValueError("online model bundle selected route does not exist")
    return payload, routes


def _protocol_from_manifest(manifest: Mapping[str, Any]) -> BenchmarkProtocol:
    return benchmark_protocol_from_mapping(manifest["protocol"])


def _validate_calibration_entries(
    manifest: Mapping[str, Any], protocol: BenchmarkProtocol
) -> list[dict[str, Any]]:
    if manifest.get("phase") != "calibration":
        raise ValueError("lightweight freeze requires the calibration manifest")
    if manifest.get("test_access_allowed") is not False:
        raise ValueError("calibration manifest must prohibit test access")
    entries = [dict(item) for item in manifest["entries"]]
    if any(item.get("split") not in {"train", "validation"} for item in entries):
        raise ValueError("lightweight freeze cannot receive a test entry")
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
    if len(actual) != len(entries):
        raise ValueError("calibration manifest contains duplicate snapshot entries")
    if actual != expected:
        missing = sorted(expected - actual)[:5]
        extra = sorted(actual - expected)[:5]
        raise ValueError(
            f"calibration manifest is incomplete; missing={missing}, extra={extra}"
        )
    return sorted(
        entries,
        key=lambda item: (
            0 if item["split"] == "train" else 1,
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        ),
    )


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
    if set(payload) != required:
        raise ValueError("offline label fields do not match the main dataset contract")
    if payload["schema_version"] not in {
        DATASET_SCHEMA_VERSION,
        LEGACY_DATASET_SCHEMA_VERSION,
    }:
        raise ValueError("unsupported offline benchmark label schema")
    if payload["offline_truth_only"] is not True:
        raise ValueError("benchmark label file is not marked offline-only")
    for name, expected in (
        ("seed", int(entry["seed"])),
        ("corruption_level", str(entry["corruption_level"])),
        ("revolution_index", int(entry["revolution_index"])),
    ):
        if payload[name] != expected:
            raise ValueError(f"offline label metadata mismatch: {name}")
    track_truth_counts = payload["track_truth_counts"]
    if not isinstance(track_truth_counts, Mapping):
        raise ValueError("track_truth_counts must be an object")
    truth_heading_groups = payload["truth_heading_groups"]
    if not isinstance(truth_heading_groups, Mapping):
        raise ValueError("truth_heading_groups must be an object")
    for truth_id, heading_group in truth_heading_groups.items():
        if not isinstance(truth_id, str) or not truth_id:
            raise ValueError("truth_heading_groups keys must be non-empty strings")
        if not isinstance(heading_group, str) or not heading_group:
            raise ValueError("truth_heading_groups values must be non-empty strings")

    ambiguous_count = 0
    empty_count = 0
    false_alarm_dominant_count = 0
    missing_heading_group_count = 0

    def identity(track_id: str) -> str | None:
        nonlocal ambiguous_count, empty_count
        nonlocal false_alarm_dominant_count, missing_heading_group_count
        counts = track_truth_counts.get(track_id, {})
        if not isinstance(counts, Mapping):
            raise ValueError("each track_truth_counts value must be an object")
        positive_counts: list[tuple[str, int]] = []
        for truth_id, observation_count in counts.items():
            if not isinstance(truth_id, str) or not truth_id:
                raise ValueError("track truth IDs must be non-empty strings")
            if isinstance(observation_count, bool) or not isinstance(
                observation_count, int
            ):
                raise ValueError("track truth observation counts must be integers")
            if observation_count > 0:
                positive_counts.append((truth_id, observation_count))
        if not positive_counts:
            empty_count += 1
            return None
        highest_count = max(count for _, count in positive_counts)
        winners = sorted(
            truth_id
            for truth_id, count in positive_counts
            if count == highest_count
        )
        if len(winners) != 1:
            ambiguous_count += 1
            return None
        winner = winners[0]
        if winner.startswith("FA-"):
            false_alarm_dominant_count += 1
            return None
        if winner not in truth_heading_groups:
            missing_heading_group_count += 1
            return None
        return winner

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
    filtered_graph = replace(
        graph,
        edge_index=graph.edge_index[:, known_edges],
        edge_features=graph.edge_features[known_edges],
        geometry_cost=graph.geometry_cost[known_edges],
    )
    filtered_graph.validate()
    edge_labels = np.asarray(
        [
            float(
                identity_a[int(index_a)] is not None
                and identity_a[int(index_a)] == identity_b[int(index_b)]
            )
            for index_a, index_b in filtered_graph.edge_index.T
        ],
        dtype=np.float32,
    )
    expected_identities = tuple(
        sorted(
            {value for value in identity_a if value is not None}
            & {value for value in identity_b if value is not None}
        )
    )
    labels = GraphLabels(
        edge_labels=edge_labels,
        identity_a=identity_a,
        identity_b=identity_b,
        expected_identities=expected_identities,
    )
    labels.validate(filtered_graph)
    return filtered_graph, labels, {
        "single_identity_track_count": sum(value is not None for value in identity_a)
        + sum(value is not None for value in identity_b),
        "ambiguous_identity_track_count": ambiguous_count,
        "empty_identity_track_count": empty_count,
        "false_alarm_dominant_track_count": false_alarm_dominant_count,
        "missing_heading_group_track_count": missing_heading_group_count,
        "excluded_unknown_edge_count": int(len(graph.geometry_cost) - len(edge_labels)),
    }


def _input_record(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "seed": int(entry["seed"]),
        "corruption_level": str(entry["corruption_level"]),
        "revolution_index": int(entry["revolution_index"]),
        "snapshot_sha256": str(entry["snapshot_sha256"]),
        "input_fingerprint": str(entry["input_fingerprint"]),
        "offline_label_sha256": str(entry["label_sha256"]),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty validation leaderboard")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_freeze_failure(
    output_dir: Path,
    *,
    manifest_path: Path,
    protocol: BenchmarkProtocol,
    failure: ValidationSelectionError,
    train_snapshot_count: int,
    validation_snapshot_count: int,
) -> Path:
    """Persist an expected validation rejection without opening test data."""

    output_dir.mkdir(parents=True, exist_ok=True)
    best = failure.best_validation_result
    best_precision = (
        None if best is None else float(best["conditional_precision"])
    )
    payload: dict[str, Any] = {
        "schema_version": FREEZE_FAILURE_SCHEMA_VERSION,
        "status": "rejected",
        "route_name": ROUTE_NAME,
        "failure_stage": "validation_selection",
        "reason_code": failure.reason_code,
        "reason": str(failure),
        "target_count": protocol.target_count,
        "protocol_fingerprint": protocol.fingerprint,
        "calibration_manifest": str(manifest_path),
        "calibration_manifest_sha256": sha256_file(manifest_path),
        "train_snapshot_count": int(train_snapshot_count),
        "validation_snapshot_count": int(validation_snapshot_count),
        "candidate_configuration_count": len(failure.validation_rows),
        "nonzero_assignment_configuration_count": sum(
            int(row.get("selected_count", 0)) > 0
            for row in failure.validation_rows
        ),
        "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
        "best_validation_result": best,
        "precision_gate_evidence": {
            "best_conditional_precision": best_precision,
            "required_minimum": MINIMUM_CONDITIONAL_PRECISION,
            "shortfall": (
                None
                if best_precision is None
                else max(
                    0.0,
                    MINIMUM_CONDITIONAL_PRECISION - best_precision,
                )
            ),
            "gate_met": bool(
                best_precision is not None
                and best_precision >= MINIMUM_CONDITIONAL_PRECISION
            ),
            "best_result_order": (
                "conditional_precision_descending_then_recall_f1"
            ),
        },
        "test_accessed": False,
        "test_paths_opened": [],
        "reserved_test_threshold_selection": False,
        "freeze_manifest_written": False,
        "promotion_allowed": False,
        "stop_before_next_scale": True,
    }
    payload["failure_fingerprint_sha256"] = canonical_json_sha256(payload)
    failure_path = output_dir / FREEZE_FAILURE_FILE_NAME
    failure_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return failure_path


def freeze_route(
    dataset_manifest: Path,
    output_dir: Path,
    *,
    allow_offline_diagnostic_failure: bool = False,
) -> Path:
    """Fit on train, select on validation, and freeze without opening test data."""

    manifest_path = Path(dataset_manifest).resolve()
    output = Path(output_dir).resolve()
    manifest = load_dataset_manifest(manifest_path)
    protocol = _protocol_from_manifest(manifest)
    if manifest["protocol_fingerprint"] != protocol.fingerprint:
        raise ValueError("calibration protocol fingerprint mismatch")
    entries = _validate_calibration_entries(manifest, protocol)
    root = manifest_path.parent
    tracker_fingerprint = str(manifest.get("tracker_fingerprint", ""))
    snapshot_contract_version = str(manifest.get("schema_version", ""))
    geometry_gate = asdict(GeometryGate())
    train_data: list[tuple[OnlineGraph, GraphLabels]] = []
    validation_data: list[tuple[OnlineGraph, GraphLabels]] = []
    train_inputs: list[dict[str, Any]] = []
    validation_inputs: list[dict[str, Any]] = []
    label_diagnostics = {
        "single_identity_track_count": 0,
        "ambiguous_identity_track_count": 0,
        "empty_identity_track_count": 0,
        "false_alarm_dominant_track_count": 0,
        "missing_heading_group_track_count": 0,
        "excluded_unknown_edge_count": 0,
    }
    for entry in entries:
        snapshot_path = root / entry["snapshot_path"]
        label_path = root / entry["label_path"]
        snapshot = read_snapshot(snapshot_path)
        if snapshot_fingerprint(snapshot) != entry["input_fingerprint"]:
            raise ValueError("calibration snapshot fingerprint mismatch")
        expected_metadata = (
            int(entry["seed"]),
            str(entry["split"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        actual_metadata = (
            snapshot.seed,
            snapshot.split,
            snapshot.corruption_level,
            snapshot.revolution_index,
        )
        if actual_metadata != expected_metadata:
            raise ValueError("calibration snapshot metadata does not match its entry")
        if snapshot.protocol_fingerprint != protocol.fingerprint:
            raise ValueError("calibration snapshot uses a different protocol")
        if (
            snapshot.target_count is not None
            and snapshot.target_count != protocol.target_count
        ):
            raise ValueError(
                "calibration snapshot target_count differs from the protocol"
            )
        if snapshot_contract_version.endswith("v2"):
            if snapshot.tracker_fingerprint != tracker_fingerprint:
                raise ValueError("calibration snapshot uses a foreign shared tracker")
        candidate_snapshot, _ = _build_candidate_snapshot(snapshot, geometry_gate)
        training_graph, labels, diagnostics = _read_offline_labels(
            label_path, entry=entry, graph=candidate_snapshot.graph
        )
        for name, value in diagnostics.items():
            label_diagnostics[name] += value
        data = (training_graph, labels)
        record = _input_record(entry)
        if entry["split"] == "train":
            train_data.append(data)
            train_inputs.append(record)
        else:
            validation_data.append(data)
            validation_inputs.append(record)
    if not train_data or not validation_data:
        raise ValueError("calibration manifest must contain train and validation inputs")

    covariance_aware = snapshot_contract_version.endswith("v2")
    if covariance_aware and not tracker_fingerprint:
        raise ValueError("Snapshot V2 calibration must identify one frozen shared tracker")
    models = fit_all_models(
        train_data,
        geometry_gate,
        random_seed=protocol.train_seeds[0],
        covariance_aware=covariance_aware,
    )
    validation_rows = _validation_rows(models, validation_data, geometry_gate)
    diagnostic_selection = False
    validation_failure_path: Path | None = None
    try:
        ranked_rows = _rank_validation_rows(validation_rows, models)
    except ValidationSelectionError as exc:
        validation_failure_path = _write_freeze_failure(
            output,
            manifest_path=manifest_path,
            protocol=protocol,
            failure=exc,
            train_snapshot_count=len(train_data),
            validation_snapshot_count=len(validation_data),
        )
        if not allow_offline_diagnostic_failure:
            raise ValidationSelectionError(
                f"{exc}; structured failure written to {validation_failure_path}",
                reason_code=exc.reason_code,
                validation_rows=exc.validation_rows,
                best_validation_result=exc.best_validation_result,
            ) from exc
        ranked_rows = _rank_diagnostic_rows(exc.validation_rows)
        diagnostic_selection = True
    selected_by_kind = _best_route_rows(ranked_rows)
    model_by_id = {model.model_id: model for model in models}
    routes = tuple(
        FrozenRoute.create(
            model_by_id[selected_by_kind[kind]["model_id"]],
            float(selected_by_kind[kind]["probability_threshold"]),
            float(selected_by_kind[kind]["unmatched_cost"]),
        )
        for kind in MODEL_KINDS
    )
    selected_route_id = str(ranked_rows[0]["model_kind"])

    output.mkdir(parents=True, exist_ok=True)
    bundle_path = output / "lightweight_online_model_bundle.json"
    leaderboard_path = output / "lightweight_validation_leaderboard.csv"
    summary_path = output / "lightweight_training_summary.json"
    freeze_path = output / FREEZE_FILE_NAME
    bundle = _bundle_payload(
        routes,
        selected_route_id=selected_route_id,
        geometry_gate=geometry_gate,
    )
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(leaderboard_path, ranked_rows)
    summary = {
        "schema_version": "dual-optical-lightweight-online-benchmark-training-v1",
        "protocol_fingerprint": protocol.fingerprint,
        "target_count_from_protocol": protocol.target_count,
        "train_snapshot_count": len(train_data),
        "validation_snapshot_count": len(validation_data),
        "candidate_model_count": len(models),
        "candidate_configuration_count": len(ranked_rows),
        "logistic_c_grid": list(LOGISTIC_C_GRID),
        "probability_threshold_grid": list(PROBABILITY_THRESHOLD_GRID),
        "unmatched_cost_grid": list(UNMATCHED_COST_GRID),
        "selected_overall": dict(ranked_rows[0]),
        "selected_by_route": selected_by_kind,
        "offline_label_diagnostics": label_diagnostics,
        "candidate_evidence": {
            "train": _candidate_evidence(train_data),
            "validation": _candidate_evidence(validation_data),
        },
        "probability_distribution_fields": [
            "positive_probability_p05",
            "positive_probability_p50",
            "positive_probability_p95",
            "negative_probability_p05",
            "negative_probability_p50",
            "negative_probability_p95",
        ],
        "assignment_evidence_fields": [
            "pre_assignment_correct_edge_count",
            "pre_assignment_incorrect_edge_count",
            "post_assignment_correct_edge_count",
            "post_assignment_incorrect_edge_count",
        ],
        "test_accessed": False,
        "test_paths_opened": [],
        "selection_policy": {
            "primary_metric": "validation_macro_recall",
            "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
            "reserved_test_threshold_selection": False,
        },
        "validation_acceptance_passed": not diagnostic_selection,
        "offline_diagnostic_selection": diagnostic_selection,
        "formal_use_allowed": not diagnostic_selection,
        "validation_failure_evidence": (
            None
            if validation_failure_path is None
            else validation_failure_path.name
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    freeze: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "route_name": ROUTE_NAME,
        "route_version": ROUTE_VERSION,
        "protocol_fingerprint": protocol.fingerprint,
        "protocol_parameters": asdict(protocol),
        "expected_target_count": protocol.target_count,
        "calibration_manifest": str(manifest_path),
        "calibration_manifest_sha256": sha256_file(manifest_path),
        "train_seeds": list(protocol.train_seeds),
        "validation_seeds": list(protocol.validation_seeds),
        "reserved_test_seeds": list(protocol.test_seeds),
        "train_inputs": train_inputs,
        "validation_inputs": validation_inputs,
        "offline_label_diagnostics": label_diagnostics,
        "candidate_evidence": {
            "train": _candidate_evidence(train_data),
            "validation": _candidate_evidence(validation_data),
        },
        "train_input_fingerprint_sha256": canonical_json_sha256(train_inputs),
        "validation_input_fingerprint_sha256": canonical_json_sha256(
            validation_inputs
        ),
        "geometry_gate": geometry_gate,
        "snapshot_contract_version": (
            "v2" if covariance_aware else "v1"
        ),
        "shared_tracker_fingerprint": (
            tracker_fingerprint if covariance_aware else "legacy-unfrozen-tracker"
        ),
        "selected_route_id": selected_route_id,
        "frozen_routes": [route.to_dict() for route in routes],
        "model_bundle": bundle_path.name,
        "model_bundle_sha256": sha256_file(bundle_path),
        "model_bundle_fingerprint_sha256": bundle["bundle_fingerprint_sha256"],
        "validation_leaderboard": leaderboard_path.name,
        "validation_leaderboard_sha256": sha256_file(leaderboard_path),
        "training_summary": summary_path.name,
        "training_summary_sha256": sha256_file(summary_path),
        "test_accessed": False,
        "test_paths_opened": [],
        "selection_policy": {
            "primary_metric": "validation_macro_recall",
            "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
            "reserved_test_threshold_selection": False,
        },
        "validation_acceptance_passed": not diagnostic_selection,
        "offline_diagnostic_selection": diagnostic_selection,
        "formal_use_allowed": not diagnostic_selection,
        "validation_failure_evidence": (
            None
            if validation_failure_path is None
            else validation_failure_path.name
        ),
        "publish_policy": {
            "truth_id": False,
            "actor_name": False,
            "offline_labels": False,
            "future_observations": False,
            "reserved_test_seeds_only": True,
            "candidate_graph_from_frozen_shared_tracker_only": True,
            "confirmation_window_revolutions": 3,
            "confirmation_required_hits": 2,
            "tentative_start_revolution": 2,
            "confirmed_start_revolution": 3,
            "deadline_failure_mode": "fail_closed_without_matches",
            "shared_candidate_allowlist_is_hard_boundary": True,
        },
    }
    freeze["freeze_fingerprint_sha256"] = canonical_json_sha256(freeze)
    freeze_path.write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return freeze_path


def _verify_freeze(
    path: Path,
    *,
    allow_offline_diagnostic: bool = False,
) -> tuple[dict[str, Any], tuple[FrozenRoute, ...]]:
    freeze_path = Path(path).resolve()
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise ValueError("unsupported lightweight online benchmark freeze schema")
    if freeze.get("route_name") != ROUTE_NAME:
        raise ValueError("frozen route_name must be lightweight")
    if freeze.get("test_accessed") is not False or freeze.get("test_paths_opened") != []:
        raise ValueError("freeze manifest does not prove test isolation")
    diagnostic_selection = bool(freeze.get("offline_diagnostic_selection", False))
    if diagnostic_selection and not allow_offline_diagnostic:
        raise ValueError("offline diagnostic freeze cannot enter the formal route loader")
    if diagnostic_selection and freeze.get("formal_use_allowed") is not False:
        raise ValueError("offline diagnostic freeze does not prohibit formal use")
    if not diagnostic_selection and freeze.get("validation_acceptance_passed", True) is not True:
        raise ValueError("formal lightweight freeze lacks validation acceptance")
    fingerprint_payload = {
        key: value
        for key, value in freeze.items()
        if key != "freeze_fingerprint_sha256"
    }
    if freeze.get("freeze_fingerprint_sha256") != canonical_json_sha256(
        fingerprint_payload
    ):
        raise ValueError("lightweight online benchmark freeze fingerprint mismatch")
    if canonical_json_sha256(freeze["train_inputs"]) != freeze[
        "train_input_fingerprint_sha256"
    ]:
        raise ValueError("frozen training input fingerprint mismatch")
    if canonical_json_sha256(freeze["validation_inputs"]) != freeze[
        "validation_input_fingerprint_sha256"
    ]:
        raise ValueError("frozen validation input fingerprint mismatch")
    calibration_manifest = Path(freeze["calibration_manifest"]).resolve()
    if sha256_file(calibration_manifest) != freeze["calibration_manifest_sha256"]:
        raise ValueError("frozen calibration manifest hash mismatch")
    root = freeze_path.parent
    for path_key, hash_key in (
        ("model_bundle", "model_bundle_sha256"),
        ("validation_leaderboard", "validation_leaderboard_sha256"),
        ("training_summary", "training_summary_sha256"),
    ):
        artifact = root / freeze[path_key]
        if sha256_file(artifact) != freeze[hash_key]:
            raise ValueError(f"frozen lightweight artifact hash mismatch: {artifact}")
    bundle, routes = _load_model_bundle(root / freeze["model_bundle"])
    if bundle["bundle_fingerprint_sha256"] != freeze[
        "model_bundle_fingerprint_sha256"
    ]:
        raise ValueError("frozen model bundle fingerprint mismatch")
    if bundle["selected_route_id"] != freeze["selected_route_id"]:
        raise ValueError("frozen selected route mismatch")
    if bundle["geometry_gate"] != freeze["geometry_gate"]:
        raise ValueError("frozen geometry gate mismatch")
    if freeze.get("snapshot_contract_version") == "v2":
        if not freeze.get("shared_tracker_fingerprint"):
            raise ValueError("V2 freeze does not identify its shared tracker")
    publish_policy = freeze.get("publish_policy", {})
    if publish_policy.get("confirmation_window_revolutions") != 3:
        raise ValueError("frozen confirmation window must be three revolutions")
    if publish_policy.get("confirmation_required_hits") != 2:
        raise ValueError("frozen confirmation policy must require two hits")
    if publish_policy.get("tentative_start_revolution") != 2:
        raise ValueError("frozen tentative publication must start at revolution two")
    if publish_policy.get("confirmed_start_revolution") != 3:
        raise ValueError("frozen confirmed publication must start at revolution three")
    if publish_policy.get("deadline_failure_mode") != "fail_closed_without_matches":
        raise ValueError("frozen deadline policy must fail closed")
    if publish_policy.get("shared_candidate_allowlist_is_hard_boundary") is not True:
        raise ValueError("frozen candidate allowlist policy is invalid")
    if freeze.get("selection_policy") != {
        "primary_metric": "validation_macro_recall",
        "minimum_conditional_precision": MINIMUM_CONDITIONAL_PRECISION,
        "reserved_test_threshold_selection": False,
    }:
        raise ValueError("frozen lightweight selection policy is invalid")
    if [route.to_dict() for route in routes] != freeze["frozen_routes"]:
        raise ValueError("frozen route parameters differ from the model bundle")
    protocol = benchmark_protocol_from_mapping(freeze["protocol_parameters"])
    if protocol.fingerprint != freeze["protocol_fingerprint"]:
        raise ValueError("frozen protocol fingerprint mismatch")
    if int(freeze.get("expected_target_count", -1)) != protocol.target_count:
        raise ValueError("frozen target count differs from the protocol")
    expected_train = {
        (int(seed), level, revolution)
        for seed in protocol.train_seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }
    expected_validation = {
        (int(seed), level, revolution)
        for seed in protocol.validation_seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }
    actual_train = {
        (
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in freeze["train_inputs"]
    }
    actual_validation = {
        (
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in freeze["validation_inputs"]
    }
    if actual_train != expected_train or len(actual_train) != len(freeze["train_inputs"]):
        raise ValueError("frozen training inputs do not cover the formal protocol")
    if (
        actual_validation != expected_validation
        or len(actual_validation) != len(freeze["validation_inputs"])
    ):
        raise ValueError("frozen validation inputs do not cover the formal protocol")
    return freeze, routes


class FrozenLightweightRoute:
    """Frozen, stateful route loaded by main after calibration."""

    def __init__(
        self,
        freeze: Mapping[str, Any],
        routes: Sequence[FrozenRoute],
    ) -> None:
        self._freeze = dict(freeze)
        selected_routes = tuple(
            route
            for route in routes
            if route.route_id == self._freeze["selected_route_id"]
        )
        if len(selected_routes) != 1:
            raise ValueError("freeze must identify exactly one online lightweight route")
        online_adapter = OnlineLightweightAdapter(
            selected_routes,
            self._freeze["geometry_gate"],
            allowed_seeds=self._freeze["reserved_test_seeds"],
            confirmation_window_revolutions=3,
            confirmation_hits=2,
            latency_budget_ms=float(
                self._freeze["protocol_parameters"]["online_deadline_ms"]
            ),
        )
        self._adapter = SharedSnapshotLightweightAdapter(
            online_adapter,
            selected_route_id=str(self._freeze["selected_route_id"]),
        )

    @property
    def route_name(self) -> str:
        return ROUTE_NAME

    @property
    def model_fingerprint(self) -> str:
        selected = next(
            item
            for item in self._adapter.online_adapter.routes
            if item.route_id == self._freeze["selected_route_id"]
        )
        return selected.model_fingerprint_sha256

    def reset(self, seed: int | None = None, corruption_level: str | None = None) -> None:
        self._adapter.reset(seed, corruption_level)

    def publish(self, snapshot: RevolutionSnapshot) -> AssociationPublication:
        """Publish from anonymous prefix data without opening any label artifact."""

        if snapshot.protocol_fingerprint != self._freeze["protocol_fingerprint"]:
            raise ValueError("online snapshot protocol differs from the frozen route")
        if (
            snapshot.target_count is not None
            and int(snapshot.target_count) != int(self._freeze["expected_target_count"])
        ):
            raise ValueError("online snapshot target_count differs from the frozen route")
        if snapshot.split != "test":
            raise ValueError("frozen lightweight route publishes reserved test snapshots only")
        if snapshot.seed not in self._freeze["reserved_test_seeds"]:
            raise ValueError("online snapshot seed is outside the reserved test split")
        if self._freeze.get("snapshot_contract_version") == "v2":
            if snapshot.tracker_fingerprint != self._freeze.get(
                "shared_tracker_fingerprint"
            ):
                raise ValueError("online snapshot does not use the frozen shared tracker")
        publication = self._adapter.process(snapshot)
        if publication.route_name != ROUTE_NAME:
            raise AssertionError("lightweight publication route_name changed unexpectedly")
        return replace(
            publication,
            route_version=(
                f"{self._freeze['route_version']}:"
                f"{self._freeze['selected_route_id']}"
            ),
        )


def load_frozen_route(freeze_manifest: Path) -> FrozenLightweightRoute:
    """Verify local frozen artifacts and return the public online publisher."""

    freeze, routes = _verify_freeze(Path(freeze_manifest))
    return FrozenLightweightRoute(freeze, routes)


def load_offline_diagnostic_route(freeze_manifest: Path) -> FrozenLightweightRoute:
    """Load an explicitly marked failed-validation route for offline analysis only."""

    freeze, routes = _verify_freeze(
        Path(freeze_manifest), allow_offline_diagnostic=True
    )
    if freeze.get("offline_diagnostic_selection") is not True:
        raise ValueError("requested freeze is not an offline diagnostic artifact")
    return FrozenLightweightRoute(freeze, routes)


__all__ = [
    "FrozenLightweightRoute",
    "freeze_route",
    "load_frozen_route",
    "load_offline_diagnostic_route",
]
