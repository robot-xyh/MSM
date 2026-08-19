"""Freeze isolated routes, execute common test snapshots, and score offline."""

from __future__ import annotations

from dataclasses import asdict, replace
import importlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

from .contracts import (
    AssociationPublication,
    BenchmarkProtocol,
    ROUTE_NAMES,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
    benchmark_protocol_from_mapping,
)
from .dataset import load_dataset_manifest, sha256_file
from .scoring import aggregate_rows, load_offline_labels, validate_and_score
from .tracking import load_tracker_freeze


ROUTE_MODULES = {
    "epipolar_mht": "dual_optical_40target.online_benchmark",
    "lightweight": "dual_optical_100target_lightweight.online_benchmark",
    "gnn": "dual_optical_100target_gnn.online_benchmark",
    "track_superglue": "dual_optical_track_superglue.online_benchmark",
}

FREEZE_ACCEPTANCE_SCHEMA = "dual-optical-freeze-acceptance-v1"
ALL_ROUTES_FREEZE_SCHEMA = "dual-optical-all-routes-freeze-v5"
READABLE_ALL_ROUTES_FREEZE_SCHEMAS = {
    ALL_ROUTES_FREEZE_SCHEMA,
    "dual-optical-all-routes-freeze-v4",
}


def _validated_route_failure(
    route_name: str,
    failure_path: Path,
    *,
    protocol: BenchmarkProtocol,
) -> dict[str, Any] | None:
    """Accept only an explicit validation rejection, never a program failure."""

    if not failure_path.is_file():
        return None
    try:
        payload = _read_json(failure_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if (
        payload.get("route_name") != route_name
        or int(payload.get("target_count", -1)) != protocol.target_count
        or payload.get("protocol_fingerprint") != protocol.fingerprint
        or payload.get("test_accessed") is not False
        or payload.get("promotion_allowed") is not False
        or payload.get("stop_before_next_scale") is not True
    ):
        return None
    return {
        "route_name": route_name,
        "status": "eliminated_on_validation",
        "reason_code": str(payload.get("reason_code") or "validation_rejected"),
        "failure_evidence": str(failure_path.resolve()),
        "failure_evidence_sha256": sha256_file(failure_path),
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _positive_validation_metrics(
    route_name: str,
    freeze_manifest: Path,
) -> dict[str, Any]:
    """Return route validation evidence and reject a zero-skill freeze.

    Each route owns its model-selection format. Main reads only the frozen
    validation summary and requires both a positive task score and at least
    one correct association before it publishes the all-routes marker.
    """

    freeze = _read_json(freeze_manifest)
    validation_failed_closed = False
    if route_name == "epipolar_mht":
        metrics = freeze.get("selected_validation_metrics", {})
        evidence_path = freeze_manifest
        f1 = float(metrics.get("f1", 0.0))
        correct_count = int(metrics.get("correct_association_count", 0))
        selected_count = correct_count + int(metrics.get("false_association_count", 0))
    elif route_name == "lightweight":
        summary_path = freeze_manifest.parent / str(freeze["training_summary"])
        summary = _read_json(summary_path)
        metrics = summary.get("selected_overall", {})
        evidence_path = summary_path
        f1 = float(metrics.get("macro_f1", 0.0))
        correct_count = int(metrics.get("correct_count", 0))
        selected_count = int(metrics.get("selected_count", 0))
    elif route_name == "gnn":
        selection_path = freeze_manifest.parent / str(freeze["validation_selection"])
        selection = _read_json(selection_path)
        selected_route = str(selection.get("selected_route", freeze.get("selected_route", "")))
        metrics = selection.get("best_by_route", {}).get(selected_route, {})
        evidence_path = selection_path
        f1 = float(metrics.get("macro_f1", 0.0))
        correct_count = int(
            metrics.get(
                "correct_assignment_count",
                metrics.get("correct_association_count", 0),
            )
        )
        selected_count = int(
            metrics.get(
                "selected_assignment_count",
                metrics.get("selected_count", 0),
            )
        )
        validation_failed_closed = bool(
            selection.get("validation_failed_closed", False)
        )
    elif route_name == "track_superglue":
        evidence_record = freeze.get("validation_selection") or freeze.get(
            "training_summary"
        )
        if not evidence_record:
            raise ValueError("track_superglue freeze omits validation evidence")
        if isinstance(evidence_record, Mapping):
            selection = dict(evidence_record)
            evidence_path = freeze_manifest
        else:
            evidence_path = freeze_manifest.parent / str(evidence_record)
            selection = _read_json(evidence_path)
        metrics = selection.get(
            "selected_validation_metrics",
            selection.get("selected_overall", selection),
        )
        f1 = float(metrics.get("macro_f1", metrics.get("f1", 0.0)))
        correct_count = int(
            metrics.get(
                "correct_assignment_count",
                metrics.get("correct_association_count", 0),
            )
        )
        selected_count = int(
            metrics.get(
                "selected_assignment_count",
                metrics.get("selected_count", 0),
            )
        )
        validation_failed_closed = bool(
            selection.get("validation_failed_closed", False)
        )
    else:
        raise ValueError(f"unsupported route validation contract: {route_name}")

    positive_correct = correct_count > 0 or (
        route_name == "gnn" and f1 > 0.0
    )
    positive_selected = selected_count > 0 or (
        route_name == "gnn" and f1 > 0.0
    )
    tiny_lightweight_output = route_name == "lightweight" and (
        f1 < 0.05 or correct_count < 2 or selected_count < 2
    )
    accepted = (
        f1 > 0.0
        and positive_correct
        and positive_selected
        and not tiny_lightweight_output
        and not validation_failed_closed
    )
    return {
        "schema_version": FREEZE_ACCEPTANCE_SCHEMA,
        "route_name": route_name,
        "accepted": accepted,
        "validation_f1": f1,
        "validation_correct_association_count": correct_count,
        "validation_selected_count": selected_count,
        "evidence_path": str(evidence_path),
        "evidence_sha256": sha256_file(evidence_path),
        "failure_reason": (
            None
            if accepted
            else (
                "route_validation_failed_closed"
                if validation_failed_closed
                else (
                    "tiny_validation_association_output"
                    if tiny_lightweight_output
                    else "zero_validation_association_skill"
                )
            )
        ),
    }


def _main_gate_elimination(
    route_name: str, acceptance: Mapping[str, Any]
) -> dict[str, Any]:
    """Convert a readable negative validation result into route elimination."""

    if acceptance.get("accepted") is not False:
        raise ValueError("main-gate elimination requires rejected validation evidence")
    return {
        "route_name": route_name,
        "status": "eliminated_on_main_validation_gate",
        "reason_code": str(
            acceptance.get("failure_reason") or "main_validation_rejected"
        ),
        "failure_evidence": str(acceptance["evidence_path"]),
        "failure_evidence_sha256": str(acceptance["evidence_sha256"]),
        "validation_acceptance": dict(acceptance),
    }


def freeze_all_routes(
    calibration_manifest: str | Path,
    output_root: str | Path,
    *,
    active_routes: tuple[str, ...] | None = None,
) -> Path:
    calibration_manifest = Path(calibration_manifest).resolve()
    manifest = load_dataset_manifest(calibration_manifest)
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    if manifest["phase"] != "calibration" or manifest["test_access_allowed"]:
        raise ValueError("route freezing accepts calibration data only")
    output_root = Path(output_root).resolve()
    tracker_freeze = Path(str(manifest.get("tracker_freeze") or "")).resolve()
    if not tracker_freeze.is_file():
        raise ValueError("route freezing requires the shared tracker freeze")
    tracker_payload, tracker_config = load_tracker_freeze(tracker_freeze)
    if tracker_config.fingerprint != manifest.get("tracker_fingerprint"):
        raise ValueError("calibration manifest was built by a foreign tracker")
    diagnostic_only = manifest.get("diagnostic_only") is True
    tracker_acceptance = tracker_payload.get("validation_metrics", {}).get(
        "acceptance", {}
    )
    if diagnostic_only:
        if (
            manifest.get("formal_use_allowed") is not False
            or manifest.get("promotion_allowed") is not False
            or manifest.get("tracker_acceptance_passed") is not False
            or tracker_payload.get("diagnostic_only") is not True
            or tracker_payload.get("formal_use_allowed") is not False
            or tracker_payload.get("promotion_allowed") is not False
            or tracker_acceptance.get("accepted") is not False
        ):
            raise ValueError("diagnostic route freeze contract is invalid")
    elif tracker_acceptance.get("accepted") is not True:
        raise ValueError("formal route freezing requires an accepted tracker")
    freeze_root = output_root / "freezes"
    freeze_root.mkdir(parents=True, exist_ok=True)
    marker = freeze_root / "all_routes_frozen.json"
    failure = freeze_root / "freeze_acceptance_failure.json"
    marker.unlink(missing_ok=True)
    failure.unlink(missing_ok=True)
    active_routes = tuple(active_routes or ROUTE_NAMES)
    if (
        not active_routes
        or len(active_routes) != len(set(active_routes))
        or any(route not in ROUTE_NAMES for route in active_routes)
    ):
        raise ValueError("freeze requires a nonempty unique active-route set")
    routes: dict[str, Any] = {}
    eliminated: dict[str, dict[str, Any]] = {}
    for route_name in active_routes:
        module = importlib.import_module(ROUTE_MODULES[route_name])
        route_root = freeze_root / route_name
        try:
            freeze_manifest = Path(
                module.freeze_route(calibration_manifest, route_root)
            ).resolve()
        except Exception:
            route_failure = _validated_route_failure(
                route_name,
                route_root / "freeze_failure.json",
                protocol=protocol,
            )
            if route_failure is None:
                raise
            eliminated[route_name] = route_failure
            continue
        acceptance = _positive_validation_metrics(route_name, freeze_manifest)
        if acceptance["accepted"]:
            routes[route_name] = {
                "freeze_manifest": str(freeze_manifest),
                "freeze_manifest_sha256": sha256_file(freeze_manifest),
                "validation_acceptance": acceptance,
            }
        else:
            eliminated[route_name] = _main_gate_elimination(
                route_name, acceptance
            )
    surviving_routes = tuple(route for route in active_routes if route in routes)
    if not surviving_routes:
        write_json(failure, {
            "schema_version": FREEZE_ACCEPTANCE_SCHEMA,
            "protocol_fingerprint": protocol.fingerprint,
            "protocol": asdict(protocol),
            "calibration_manifest": str(calibration_manifest),
            "calibration_manifest_sha256": sha256_file(calibration_manifest),
            "tracker_freeze": str(tracker_freeze),
            "tracker_freeze_sha256": sha256_file(tracker_freeze),
            "tracker_fingerprint": tracker_config.fingerprint,
            "test_data_accessed": False,
            "all_routes_accepted": False,
            "requested_routes": list(active_routes),
            "active_routes": list(surviving_routes),
            "routes": routes,
            "rejected_routes": {
                route: evidence
                for route, evidence in eliminated.items()
                if evidence.get("status") == "eliminated_on_main_validation_gate"
            },
            "eliminated_routes": eliminated,
        })
        raise RuntimeError(
            "route freeze rejected by validation acceptance gate; "
            f"see {failure}"
        )
    write_json(marker, {
        "schema_version": ALL_ROUTES_FREEZE_SCHEMA,
        "protocol_fingerprint": protocol.fingerprint,
        "protocol": asdict(protocol),
        "calibration_manifest": str(calibration_manifest),
        "calibration_manifest_sha256": sha256_file(calibration_manifest),
        "tracker_freeze": str(tracker_freeze),
        "tracker_freeze_sha256": sha256_file(tracker_freeze),
        "tracker_fingerprint": tracker_config.fingerprint,
        "test_data_accessed": False,
        "all_routes_accepted": True,
        "diagnostic_only": diagnostic_only,
        "formal_use_allowed": not diagnostic_only,
        "promotion_allowed": not diagnostic_only,
        "tracker_acceptance_passed": not diagnostic_only,
        "requested_routes": list(active_routes),
        "active_routes": list(surviving_routes),
        "eliminated_routes": eliminated,
        "routes": routes,
    })
    return marker


def _protocol_from_freeze_marker(marker: Mapping[str, Any]) -> BenchmarkProtocol:
    protocol_values = marker.get("protocol")
    if not isinstance(protocol_values, Mapping):
        # Compatibility is limited to the sealed legacy 100-target marker.
        return BenchmarkProtocol()
    return benchmark_protocol_from_mapping(protocol_values)


def _load_routes(freeze_marker: Path) -> dict[str, Any]:
    marker = json.loads(freeze_marker.read_text(encoding="utf-8"))
    protocol = _protocol_from_freeze_marker(marker)
    if marker.get("schema_version") not in READABLE_ALL_ROUTES_FREEZE_SCHEMAS:
        raise ValueError("unsupported all-routes freeze marker schema")
    if marker.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("freeze marker protocol mismatch")
    if marker.get("all_routes_accepted") is not True:
        raise ValueError("freeze marker does not prove positive validation acceptance")
    active_routes = tuple(marker.get("active_routes", ()))
    if (
        not active_routes
        or len(active_routes) != len(set(active_routes))
        or any(route not in ROUTE_NAMES for route in active_routes)
        or set(marker.get("routes", {})) != set(active_routes)
    ):
        raise ValueError("freeze marker does not contain every active route")
    tracker_freeze = Path(str(marker.get("tracker_freeze") or ""))
    if not tracker_freeze.is_file():
        raise ValueError("freeze marker does not contain a shared tracker freeze")
    if sha256_file(tracker_freeze) != marker.get("tracker_freeze_sha256"):
        raise ValueError("shared tracker freeze hash mismatch")
    _, tracker_config = load_tracker_freeze(tracker_freeze)
    if tracker_config.fingerprint != marker.get("tracker_fingerprint"):
        raise ValueError("shared tracker fingerprint mismatch")
    routes: dict[str, Any] = {}
    for route_name in active_routes:
        item = marker["routes"][route_name]
        acceptance = item.get("validation_acceptance", {})
        if acceptance.get("accepted") is not True:
            raise ValueError(f"{route_name} did not pass validation acceptance")
        path = Path(item["freeze_manifest"])
        if sha256_file(path) != item["freeze_manifest_sha256"]:
            raise ValueError(f"{route_name} freeze manifest hash mismatch")
        module = importlib.import_module(ROUTE_MODULES[route_name])
        routes[route_name] = module.load_frozen_route(path)
    return routes


def validate_freeze_marker(freeze_marker: str | Path) -> dict[str, Any]:
    """Validate the current main marker without loading route implementations."""

    freeze_marker = Path(freeze_marker).resolve()
    marker = _read_json(freeze_marker)
    protocol = _protocol_from_freeze_marker(marker)
    if marker.get("schema_version") not in READABLE_ALL_ROUTES_FREEZE_SCHEMAS:
        raise ValueError("unsupported all-routes freeze marker schema")
    if marker.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("freeze marker protocol mismatch")
    if marker.get("all_routes_accepted") is not True:
        raise ValueError("freeze marker does not prove positive validation acceptance")
    active_routes = tuple(marker.get("active_routes", ()))
    if (
        not active_routes
        or len(active_routes) != len(set(active_routes))
        or any(route not in ROUTE_NAMES for route in active_routes)
        or set(marker.get("routes", {})) != set(active_routes)
    ):
        raise ValueError("freeze marker does not contain every active route")
    tracker_freeze = Path(str(marker.get("tracker_freeze") or ""))
    if not tracker_freeze.is_file():
        raise ValueError("freeze marker does not contain a shared tracker freeze")
    if sha256_file(tracker_freeze) != marker.get("tracker_freeze_sha256"):
        raise ValueError("shared tracker freeze hash mismatch")
    tracker_payload, tracker_config = load_tracker_freeze(tracker_freeze)
    if tracker_config.fingerprint != marker.get("tracker_fingerprint"):
        raise ValueError("shared tracker fingerprint mismatch")
    acceptance = tracker_payload.get("validation_metrics", {}).get("acceptance", {})
    diagnostic_only = marker.get("diagnostic_only") is True
    if diagnostic_only:
        if (
            marker.get("formal_use_allowed") is not False
            or marker.get("promotion_allowed") is not False
            or marker.get("tracker_acceptance_passed") is not False
            or tracker_payload.get("diagnostic_only") is not True
            or tracker_payload.get("formal_use_allowed") is not False
            or tracker_payload.get("promotion_allowed") is not False
            or acceptance.get("accepted") is not False
        ):
            raise ValueError("diagnostic freeze marker capability contract is invalid")
    elif acceptance.get("accepted") is not True:
        raise ValueError("shared tracker did not pass validation acceptance")
    for route_name in active_routes:
        item = marker["routes"][route_name]
        acceptance = item.get("validation_acceptance", {})
        if acceptance.get("accepted") is not True:
            raise ValueError(f"{route_name} did not pass validation acceptance")
        manifest = Path(item["freeze_manifest"])
        if sha256_file(manifest) != item["freeze_manifest_sha256"]:
            raise ValueError(f"{route_name} freeze manifest hash mismatch")
        evidence = Path(acceptance["evidence_path"])
        if sha256_file(evidence) != acceptance["evidence_sha256"]:
            raise ValueError(f"{route_name} validation evidence hash mismatch")
    return marker


def _deadline_publication(
    publication: AssociationPublication,
    measured_ms: float,
    snapshot_hash: str,
    deadline_ms: float,
) -> AssociationPublication:
    if publication.input_fingerprint != snapshot_hash:
        raise ValueError(f"{publication.route_name} returned a foreign input fingerprint")
    end_to_end = max(float(publication.end_to_end_ms), measured_ms)
    if end_to_end <= deadline_ms:
        if end_to_end == publication.end_to_end_ms:
            return publication
        return replace(publication, end_to_end_ms=end_to_end)
    return AssociationPublication(
        route_name=publication.route_name,
        route_version=publication.route_version,
        model_fingerprint=publication.model_fingerprint,
        seed=publication.seed,
        corruption_level=publication.corruption_level,
        revolution_index=publication.revolution_index,
        cutoff_timestamp=publication.cutoff_timestamp,
        input_fingerprint=publication.input_fingerprint,
        availability="timeout",
        matches=(),
        rejection_reasons={"deadline_exceeded": 1},
        candidate_graph_fingerprint=publication.candidate_graph_fingerprint,
        stage_latencies_ms=dict(publication.stage_latencies_ms),
        scoring_ms=0.0,
        hungarian_ms=0.0,
        end_to_end_ms=end_to_end,
        deadline_ms=deadline_ms,
    )


def run_frozen_test(
    test_manifest: str | Path,
    freeze_marker: str | Path,
    output_dir: str | Path,
) -> Path:
    test_manifest = Path(test_manifest).resolve()
    # Do not open or hash an offline label until all three routes have
    # published for its snapshot.
    manifest = load_dataset_manifest(test_manifest, validate_offline_labels=False)
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    if manifest["phase"] != "test" or not manifest["test_access_allowed"]:
        raise ValueError("frozen evaluation requires the reserved test manifest")
    freeze_marker = Path(freeze_marker).resolve()
    marker = validate_freeze_marker(freeze_marker)
    if marker.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("test manifest and freeze marker protocols differ")
    if manifest.get("tracker_fingerprint") != marker.get("tracker_fingerprint"):
        raise ValueError("test snapshots were built by a different shared tracker")
    routes = _load_routes(freeze_marker)
    active_routes = tuple(marker["active_routes"])
    output_dir = Path(output_dir).resolve()
    publications_root = output_dir / "publications"
    rows: list[dict[str, Any]] = []
    fingerprint_checks: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        snapshot_path = test_manifest.parent / entry["snapshot_path"]
        label_path = test_manifest.parent / entry["label_path"]
        snapshot = read_snapshot(snapshot_path)
        expected_hash = snapshot_fingerprint(snapshot)
        if expected_hash != entry["input_fingerprint"]:
            raise ValueError("test snapshot fingerprint changed after manifest creation")
        publications: list[AssociationPublication] = []
        for route_name in active_routes:
            started = time.perf_counter()
            raw_publication = routes[route_name].publish(snapshot)
            measured_ms = (time.perf_counter() - started) * 1000.0
            publication = _deadline_publication(
                raw_publication,
                measured_ms,
                expected_hash,
                protocol.online_deadline_ms,
            )
            if publication.route_name != route_name:
                raise ValueError("loaded route published under the wrong route name")
            publications.append(publication)
            publication_path = (
                publications_root / str(snapshot.seed) / snapshot.corruption_level
                / f"revolution_{snapshot.revolution_index:02d}_{route_name}.json"
            )
            write_json(publication_path, asdict(publication))
        labels = load_offline_labels(label_path, entry["label_sha256"])
        rows.extend(
            validate_and_score(
                snapshot,
                publications,
                labels,
                expected_routes=active_routes,
            )
        )
        fingerprint_checks.append({
            "seed": snapshot.seed,
            "corruption_level": snapshot.corruption_level,
            "revolution_index": snapshot.revolution_index,
            "input_fingerprint": expected_hash,
            "route_fingerprints": {
                publication.route_name: publication.input_fingerprint
                for publication in publications
            },
            "all_equal": all(
                publication.input_fingerprint == expected_hash
                for publication in publications
            ),
        })
    metrics = {
        "schema_version": "dual-optical-online-comparison-metrics-v1",
        "protocol_fingerprint": protocol.fingerprint,
        "protocol": asdict(protocol),
        "test_manifest": str(test_manifest),
        "test_manifest_sha256": sha256_file(test_manifest),
        "freeze_marker": str(freeze_marker),
        "freeze_marker_sha256": sha256_file(freeze_marker),
        "truth_used_online": False,
        "diagnostic_only": marker.get("diagnostic_only") is True,
        "formal_use_allowed": marker.get("formal_use_allowed", True),
        "promotion_allowed": marker.get("promotion_allowed", True),
        "tracker_acceptance_passed": marker.get(
            "tracker_acceptance_passed", True
        ),
        "active_routes": list(active_routes),
        "rows": rows,
        "aggregate": aggregate_rows(rows),
        "shared_input_checks": fingerprint_checks,
    }
    metrics_path = output_dir / "comparison_metrics.json"
    write_json(metrics_path, metrics)
    from .reporting import generate_report
    from .analysis import generate_diagnostics

    generate_diagnostics(metrics_path)
    generate_report(metrics_path)
    return metrics_path
