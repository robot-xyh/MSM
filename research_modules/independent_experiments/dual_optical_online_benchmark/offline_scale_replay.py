"""Supplemental three-route replay on frozen anonymous snapshots.

This diagnostic does not alter scale-funnel promotion decisions. It exists to
compare routes that were previously stopped by validation or latency gates.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

from .contracts import (
    AssociationMatch,
    AssociationPublication,
    LEGACY_ROUTE_NAMES,
    ROUTE_NAMES,
    RevolutionSnapshot,
    benchmark_protocol_from_mapping,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
)
from .dataset import load_dataset_manifest, sha256_file
from .orchestrator import _deadline_publication
from .scoring import (
    aggregate_rows,
    load_offline_labels,
    score_publication,
    validate_and_score,
)


OFFLINE_REPLAY_SCHEMA = "dual-optical-offline-route-replay-v2"
TRANSFERRED_ENHANCED_SCHEMA = "dual-optical-offline-transferred-enhanced-v1"
TRANSFERRED_SUPERGLUE_SCHEMA = "dual-optical-offline-transferred-superglue-v1"


def _read_object(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _fingerprint(values: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        values,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_transferred_enhanced_route(
    source_freeze: str | Path,
    calibration_manifest: str | Path,
    output_path: str | Path,
) -> Path:
    """Bind a validated lower-scale parameter set to a higher-scale protocol."""

    source_freeze = Path(source_freeze).resolve()
    source = _read_object(source_freeze)
    if (
        source.get("route_name") != "epipolar_mht"
        or source.get("validation_acceptance_passed") is not True
        or not isinstance(source.get("selected_parameters"), Mapping)
    ):
        raise ValueError("source enhanced route lacks validated parameters")
    calibration_manifest = Path(calibration_manifest).resolve()
    manifest = load_dataset_manifest(
        calibration_manifest, validate_offline_labels=False
    )
    if manifest.get("phase") != "calibration" or manifest.get("test_access_allowed") is not False:
        raise ValueError("enhanced transfer requires a calibration-only manifest")
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    payload: dict[str, Any] = {
        "schema_version": TRANSFERRED_ENHANCED_SCHEMA,
        "route_name": "epipolar_mht",
        "route_version": str(source["route_version"]),
        "source_freeze": str(source_freeze),
        "source_freeze_sha256": sha256_file(source_freeze),
        "source_target_count": int(source.get("target_count") or 20),
        "source_model_fingerprint": str(source["model_fingerprint"]),
        "selected_parameters": dict(source["selected_parameters"]),
        "target_calibration_manifest": str(calibration_manifest),
        "target_calibration_manifest_sha256": sha256_file(calibration_manifest),
        "target_count": protocol.target_count,
        "protocol_fingerprint": protocol.fingerprint,
        "shared_tracker_fingerprint": str(manifest["tracker_fingerprint"]),
        "offline_diagnostic_selection": True,
        "formal_use_allowed": False,
        "test_data_accessed": False,
        "selection_policy": "validated_lower_scale_parameters_without_target_scale_retuning",
    }
    payload["model_fingerprint"] = _fingerprint(
        {
            "source_model_fingerprint": payload["source_model_fingerprint"],
            "protocol_fingerprint": payload["protocol_fingerprint"],
            "target_count": payload["target_count"],
            "selection_policy": payload["selection_policy"],
        }
    )
    payload["manifest_fingerprint_sha256"] = _fingerprint(payload)
    output_path = Path(output_path).resolve()
    write_json(output_path, payload)
    return output_path


def build_transferred_superglue_route(
    source_freeze: str | Path,
    target_manifest: str | Path,
    output_path: str | Path,
) -> Path:
    """Bind one frozen 20-target model to a higher-scale offline protocol.

    The model, normalizer, threshold, and weights remain unchanged.  The
    transferred manifest is diagnostic-only and must live beside the source
    manifest so its relative artifact paths retain their original meaning.
    """

    source_freeze = Path(source_freeze).resolve()
    source = _read_object(source_freeze)
    if (
        source.get("route_name") != "track_superglue"
        or source.get("validation_selection", {}).get(
            "validation_failed_closed"
        )
        is not False
    ):
        raise ValueError("source SuperGlue route lacks a usable frozen model")
    target_manifest = Path(target_manifest).resolve()
    manifest = _read_object(target_manifest)
    if manifest.get("phase") not in {"calibration", "test"}:
        raise ValueError("target manifest must describe calibration or test data")
    protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    if manifest.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("target manifest protocol fingerprint mismatch")
    output_path = Path(output_path).resolve()
    if output_path.parent != source_freeze.parent:
        raise ValueError(
            "transferred SuperGlue manifest must remain beside source artifacts"
        )
    payload = dict(source)
    payload.update(
        {
            "schema_version": source["schema_version"],
            "transfer_schema_version": TRANSFERRED_SUPERGLUE_SCHEMA,
            "source_freeze": str(source_freeze),
            "source_freeze_sha256": sha256_file(source_freeze),
            "source_target_count": int(source.get("target_count") or 20),
            "source_protocol_fingerprint_sha256": str(
                source.get("protocol_fingerprint_sha256", "")
            ),
            "protocol_fingerprint_sha256": protocol.fingerprint,
            "target_count": protocol.target_count,
            "target_manifest": str(target_manifest),
            "target_manifest_sha256": sha256_file(target_manifest),
            "offline_diagnostic_selection": True,
            "formal_use_allowed": False,
            "test_data_accessed": False,
            "selection_policy": (
                "validated_20_target_weights_without_target_scale_retuning"
            ),
        }
    )
    payload["transfer_manifest_fingerprint_sha256"] = _fingerprint(payload)
    write_json(output_path, payload)
    return output_path


def _load_route(
    route_name: str,
    freeze_manifest: Path,
    *,
    diagnostic_lightweight: bool,
) -> Any:
    if route_name == "epipolar_mht":
        from dual_optical_40target.online_benchmark import (
            FrozenEnhancedGeometryRoute,
            load_frozen_route,
        )

        payload = _read_object(freeze_manifest)
        if payload.get("schema_version") == TRANSFERRED_ENHANCED_SCHEMA:
            stored = str(payload.get("manifest_fingerprint_sha256") or "")
            unsigned = dict(payload)
            unsigned.pop("manifest_fingerprint_sha256", None)
            if stored != _fingerprint(unsigned):
                raise ValueError("transferred enhanced manifest fingerprint mismatch")
            if (
                payload.get("offline_diagnostic_selection") is not True
                or payload.get("formal_use_allowed") is not False
                or payload.get("test_data_accessed") is not False
            ):
                raise ValueError("transferred enhanced route is not diagnostic-only")
            return FrozenEnhancedGeometryRoute(
                {
                    "selected_parameters": payload["selected_parameters"],
                    "model_fingerprint": payload["model_fingerprint"],
                    "protocol_fingerprint": payload["protocol_fingerprint"],
                    "shared_tracker_fingerprint": payload[
                        "shared_tracker_fingerprint"
                    ],
                    "target_count": payload["target_count"],
                }
            )
        return load_frozen_route(freeze_manifest)
    if route_name == "lightweight":
        if diagnostic_lightweight:
            from dual_optical_100target_lightweight.online_benchmark import (
                load_offline_diagnostic_route,
            )

            return load_offline_diagnostic_route(freeze_manifest)
        from dual_optical_100target_lightweight.online_benchmark import (
            load_frozen_route,
        )

        return load_frozen_route(freeze_manifest)
    if route_name == "gnn":
        from dual_optical_100target_gnn.online_benchmark import load_frozen_route

        return load_frozen_route(freeze_manifest)
    if route_name == "track_superglue":
        from dual_optical_track_superglue.online_benchmark import load_frozen_route

        payload = _read_object(freeze_manifest)
        if payload.get("transfer_schema_version") == TRANSFERRED_SUPERGLUE_SCHEMA:
            stored = str(payload.get("transfer_manifest_fingerprint_sha256") or "")
            unsigned = dict(payload)
            unsigned.pop("transfer_manifest_fingerprint_sha256", None)
            if stored != _fingerprint(unsigned):
                raise ValueError("transferred SuperGlue manifest fingerprint mismatch")
            if (
                payload.get("offline_diagnostic_selection") is not True
                or payload.get("formal_use_allowed") is not False
                or payload.get("test_data_accessed") is not False
            ):
                raise ValueError("transferred SuperGlue route is not diagnostic-only")
        return load_frozen_route(freeze_manifest)
    raise ValueError(f"unsupported route: {route_name}")


def _publication_from_mapping(values: Mapping[str, Any]) -> AssociationPublication:
    return AssociationPublication(
        route_name=str(values["route_name"]),
        route_version=str(values["route_version"]),
        model_fingerprint=str(values["model_fingerprint"]),
        seed=int(values["seed"]),
        corruption_level=str(values["corruption_level"]),
        revolution_index=int(values["revolution_index"]),
        cutoff_timestamp=float(values["cutoff_timestamp"]),
        input_fingerprint=str(values["input_fingerprint"]),
        availability=str(values["availability"]),
        matches=tuple(
            AssociationMatch(
                track_a_id=str(item["track_a_id"]),
                track_b_id=str(item["track_b_id"]),
                score=float(item["score"]),
                decision_state=str(item["decision_state"]),
            )
            for item in values.get("matches", ())
        ),
        rejection_reasons={
            str(key): int(value)
            for key, value in values.get("rejection_reasons", {}).items()
        },
        candidate_graph_fingerprint=str(
            values.get("candidate_graph_fingerprint", "")
        ),
        stage_latencies_ms={
            str(key): float(value)
            for key, value in values.get("stage_latencies_ms", {}).items()
        },
        scoring_ms=float(values.get("scoring_ms", 0.0)),
        hungarian_ms=float(values.get("hungarian_ms", 0.0)),
        end_to_end_ms=float(values.get("end_to_end_ms", 0.0)),
        deadline_ms=float(values.get("deadline_ms", 1000.0)),
    )


def _metrics_payload(
    *,
    test_manifest: Path,
    route_manifests: Mapping[str, Path],
    rows: list[dict[str, Any]],
    source_mode: str,
    diagnostic_routes: tuple[str, ...],
    active_routes: tuple[str, ...] = LEGACY_ROUTE_NAMES,
    manifest_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if manifest_override is None:
        manifest = load_dataset_manifest(
            test_manifest, validate_offline_labels=False
        )
        protocol = benchmark_protocol_from_mapping(manifest["protocol"])
        protocol_values = asdict(protocol)
        protocol_fingerprint = protocol.fingerprint
        target_count = protocol.target_count
        compatibility_note = None
    else:
        manifest = dict(manifest_override)
        protocol_values = dict(manifest["protocol"])
        protocol_fingerprint = str(manifest["protocol_fingerprint"])
        target_count = int(protocol_values["target_count"])
        compatibility_note = (
            "sealed historical manifest replayed with its recorded file hashes; "
            "the current snapshot fingerprint is used only for new publications"
            if source_mode == "route_reexecution"
            else "sealed historical manifest rescored without rebuilding the "
            "evolved tracker/protocol dataclasses"
        )
    return {
        "schema_version": OFFLINE_REPLAY_SCHEMA,
        "source_mode": source_mode,
        "supplemental_offline_diagnostic": True,
        "changes_scale_funnel_decision": False,
        "protocol": protocol_values,
        "protocol_fingerprint": protocol_fingerprint,
        "target_count": target_count,
        "compatibility_note": compatibility_note,
        "test_manifest": str(test_manifest),
        "test_manifest_sha256": sha256_file(test_manifest),
        "route_manifests": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
                "diagnostic_failed_validation": name in diagnostic_routes,
            }
            for name, path in sorted(route_manifests.items())
        },
        "active_routes": list(active_routes),
        "truth_used_online": False,
        "offline_labels_opened_after_all_route_publications": True,
        "rows": rows,
        "aggregate": aggregate_rows(rows),
    }


def run_replay(
    test_manifest: str | Path,
    route_manifests: Mapping[str, str | Path],
    output_dir: str | Path,
    *,
    diagnostic_lightweight: bool = False,
    allow_legacy_snapshot_fingerprint: bool = False,
) -> Path:
    """Execute all routes on one reserved snapshot set and score afterward."""

    test_manifest = Path(test_manifest).resolve()
    if allow_legacy_snapshot_fingerprint:
        manifest = _read_object(test_manifest)
        protocol = benchmark_protocol_from_mapping(manifest["protocol"])
        if manifest.get("protocol_fingerprint") != protocol.fingerprint:
            raise ValueError("legacy test manifest protocol fingerprint mismatch")
        for entry in manifest.get("entries", ()):
            snapshot_path = test_manifest.parent / entry["snapshot_path"]
            label_path = test_manifest.parent / entry["label_path"]
            if sha256_file(snapshot_path) != entry["snapshot_sha256"]:
                raise ValueError("legacy test snapshot hash mismatch")
            if sha256_file(label_path) != entry["label_sha256"]:
                raise ValueError("legacy test label hash mismatch")
    else:
        manifest = load_dataset_manifest(
            test_manifest, validate_offline_labels=False
        )
        protocol = benchmark_protocol_from_mapping(manifest["protocol"])
    if manifest.get("phase") != "test" or manifest.get("test_access_allowed") is not True:
        raise ValueError("offline replay requires a reserved test manifest")
    normalized = {
        str(name): Path(path).resolve() for name, path in route_manifests.items()
    }
    active_routes = tuple(route for route in ROUTE_NAMES if route in normalized)
    if not active_routes or set(normalized) != set(active_routes):
        raise ValueError("offline replay received an invalid route set")
    routes = {
        name: _load_route(
            name,
            normalized[name],
            diagnostic_lightweight=(
                diagnostic_lightweight and name == "lightweight"
            ),
        )
        for name in active_routes
    }
    output_dir = Path(output_dir).resolve()
    publications_root = output_dir / "publications"
    rows: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        snapshot_path = test_manifest.parent / entry["snapshot_path"]
        label_path = test_manifest.parent / entry["label_path"]
        if allow_legacy_snapshot_fingerprint:
            snapshot_payload = _read_object(snapshot_path)
            if snapshot_payload.get("input_fingerprint") != entry["input_fingerprint"]:
                raise ValueError("legacy snapshot fingerprint record mismatch")
            snapshot = RevolutionSnapshot.from_online_payload(snapshot_payload)
        else:
            snapshot = read_snapshot(snapshot_path)
        expected_hash = snapshot_fingerprint(snapshot)
        if (
            not allow_legacy_snapshot_fingerprint
            and expected_hash != entry["input_fingerprint"]
        ):
            raise ValueError("test snapshot fingerprint changed")
        publications: list[AssociationPublication] = []
        for route_name in active_routes:
            started = time.perf_counter()
            raw = routes[route_name].publish(snapshot)
            measured_ms = (time.perf_counter() - started) * 1000.0
            publication = _deadline_publication(
                raw,
                measured_ms,
                expected_hash,
                protocol.online_deadline_ms,
            )
            publications.append(publication)
            publication_path = (
                publications_root
                / str(snapshot.seed)
                / snapshot.corruption_level
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
    payload = _metrics_payload(
        test_manifest=test_manifest,
        route_manifests=normalized,
        rows=rows,
        source_mode="route_reexecution",
        active_routes=active_routes,
        manifest_override=(manifest if allow_legacy_snapshot_fingerprint else None),
        diagnostic_routes=tuple(
            name
            for name, path in normalized.items()
            if (
                _read_object(path).get("offline_diagnostic_selection") is True
                or (name == "lightweight" and diagnostic_lightweight)
            )
        ),
    )
    metrics_path = output_dir / "offline_comparison_metrics.json"
    write_json(metrics_path, payload)
    return metrics_path


def rescore_publications(
    test_manifest: str | Path,
    route_manifests: Mapping[str, str | Path],
    publications_root: str | Path,
    output_dir: str | Path,
) -> Path:
    """Recompute scores from sealed publications without rerunning route code."""

    test_manifest = Path(test_manifest).resolve()
    manifest = _read_object(test_manifest)
    if manifest.get("phase") != "test" or manifest.get("test_access_allowed") is not True:
        raise ValueError("publication rescore requires a sealed test manifest")
    if not isinstance(manifest.get("protocol"), Mapping):
        raise ValueError("sealed test manifest has no protocol object")
    if int(manifest["protocol"].get("target_count", -1)) <= 0:
        raise ValueError("sealed test manifest has an invalid target count")
    if not manifest.get("protocol_fingerprint"):
        raise ValueError("sealed test manifest has no protocol fingerprint")
    normalized = {
        str(name): Path(path).resolve() for name, path in route_manifests.items()
    }
    if set(normalized) != set(LEGACY_ROUTE_NAMES):
        raise ValueError("publication rescore requires all three route manifests")
    publications_root = Path(publications_root).resolve()
    rows: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        snapshot_path = test_manifest.parent / entry["snapshot_path"]
        if sha256_file(snapshot_path) != entry["snapshot_sha256"]:
            raise ValueError("sealed snapshot hash mismatch")
        snapshot_payload = _read_object(snapshot_path)
        if snapshot_payload.get("input_fingerprint") != entry["input_fingerprint"]:
            raise ValueError("sealed snapshot fingerprint record mismatch")
        # The historical V2 fingerprint predates target-count and shared-candidate
        # fields in the current dataclass. Reconstruct its payload for scoring but
        # retain the sealed fingerprint as the cross-file identity check.
        snapshot = RevolutionSnapshot.from_online_payload(snapshot_payload)
        publications = []
        for route_name in LEGACY_ROUTE_NAMES:
            path = (
                publications_root
                / str(snapshot.seed)
                / snapshot.corruption_level
                / f"revolution_{snapshot.revolution_index:02d}_{route_name}.json"
            )
            publication = _publication_from_mapping(_read_object(path))
            if publication.input_fingerprint != entry["input_fingerprint"]:
                raise ValueError("sealed publication input fingerprint mismatch")
            if (
                publication.seed != int(entry["seed"])
                or publication.corruption_level != str(entry["corruption_level"])
                or publication.revolution_index != int(entry["revolution_index"])
            ):
                raise ValueError("sealed publication metadata mismatch")
            publications.append(publication)
        labels = load_offline_labels(
            test_manifest.parent / entry["label_path"], entry["label_sha256"]
        )
        if {publication.route_name for publication in publications} != set(LEGACY_ROUTE_NAMES):
            raise ValueError("sealed publications do not cover all three routes")
        for publication in publications:
            row = score_publication(publication, labels, snapshot)
            row["input_fingerprint"] = str(entry["input_fingerprint"])
            rows.append(row)
    payload = _metrics_payload(
        test_manifest=test_manifest,
        route_manifests=normalized,
        rows=rows,
        source_mode="sealed_publication_rescore",
        diagnostic_routes=(),
        active_routes=LEGACY_ROUTE_NAMES,
        manifest_override=manifest,
    )
    payload["source_publications_root"] = str(publications_root)
    output_dir = Path(output_dir).resolve()
    metrics_path = output_dir / "offline_comparison_metrics.json"
    write_json(metrics_path, payload)
    return metrics_path


def _route_arguments(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or name not in ROUTE_NAMES or not path:
            raise ValueError("route arguments must use ROUTE=/path/to/freeze.json")
        result[name] = Path(path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay = subparsers.add_parser("run")
    replay.add_argument("--test-manifest", type=Path, required=True)
    replay.add_argument("--route", action="append", required=True)
    replay.add_argument("--output-dir", type=Path, required=True)
    replay.add_argument("--diagnostic-lightweight", action="store_true")
    replay.add_argument(
        "--allow-legacy-snapshot-fingerprint", action="store_true"
    )
    rescore = subparsers.add_parser("rescore")
    rescore.add_argument("--test-manifest", type=Path, required=True)
    rescore.add_argument("--route", action="append", required=True)
    rescore.add_argument("--publications-root", type=Path, required=True)
    rescore.add_argument("--output-dir", type=Path, required=True)
    transfer = subparsers.add_parser("transfer-enhanced")
    transfer.add_argument("--source-freeze", type=Path, required=True)
    transfer.add_argument("--calibration-manifest", type=Path, required=True)
    transfer.add_argument("--output", type=Path, required=True)
    transfer_superglue = subparsers.add_parser("transfer-superglue")
    transfer_superglue.add_argument("--source-freeze", type=Path, required=True)
    transfer_superglue.add_argument("--target-manifest", type=Path, required=True)
    transfer_superglue.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "transfer-enhanced":
        result = build_transferred_enhanced_route(
            args.source_freeze,
            args.calibration_manifest,
            args.output,
        )
    elif args.command == "transfer-superglue":
        result = build_transferred_superglue_route(
            args.source_freeze,
            args.target_manifest,
            args.output,
        )
    elif args.command == "run":
        routes = _route_arguments(args.route)
        result = run_replay(
            args.test_manifest,
            routes,
            args.output_dir,
            diagnostic_lightweight=args.diagnostic_lightweight,
            allow_legacy_snapshot_fingerprint=(
                args.allow_legacy_snapshot_fingerprint
            ),
        )
    else:
        routes = _route_arguments(args.route)
        result = rescore_publications(
            args.test_manifest,
            routes,
            args.publications_root,
            args.output_dir,
        )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
