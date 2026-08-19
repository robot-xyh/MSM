"""V5 orchestration for the phase-180 target-track experiment.

The formal V4 batch gates remain authoritative.  This module adds a separate
diagnostic path for the case where shared tracker calibration leaves complete
evidence but correctly refuses to write a formal tracker freeze.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import importlib
import json
from pathlib import Path
import shlex
from typing import Any, Callable, Mapping, Protocol, Sequence

from dual_optical_40target.core import CameraSpec
from dual_optical_40target.runtime import LocalBlocksProcess, write_airsim_settings

from .batch import (
    BATCH_SCHEMA_VERSION,
    PREFLIGHT_SCENARIOS,
    PREFLIGHT_SEEDS,
    _load_reusable_receipt,
    _receipt_path,
    _reset_client,
    _run_worker,
    _wait_for_rpc,
    run_phase,
    run_preflight,
)
from .contracts import (
    BenchmarkProtocol,
    benchmark_protocol_from_mapping,
    read_snapshot,
    snapshot_fingerprint,
    write_json,
)
from .dataset import (
    materialize_episode,
    sha256_file,
    split_for_seed,
    validate_raw_episode,
)
from .orchestrator import validate_freeze_marker
from .tracking import SharedTrackerConfig, load_tracker_freeze
from .v5 import (
    V5_CAMERA_B_PHASE_OFFSET_S,
    V5_EXPERIMENT_PROFILE,
    V5_OUTPUT_VERSION,
    V5_TARGET_COUNTS,
    v5_protocol_for_target_count,
)


V5_PLAN_SCHEMA = "dual-optical-v5-plan-v1"
V5_RUN_SCHEMA = "dual-optical-v5-run-v1"
V5_DIAGNOSTIC_TRACKER_SCHEMA = "dual-optical-v5-diagnostic-tracker-v1"
V5_DIAGNOSTIC_RAW_SCHEMA = "dual-optical-v5-diagnostic-raw-v1"
V5_DIAGNOSTIC_DATASET_SCHEMA = "dual-optical-v5-diagnostic-dataset-v1"
V5_MODEL_FREEZE_SCHEMA = "dual-optical-v5-target-track-model-freeze-v1"
V5_ONLINE_TEST_MANIFEST_SCHEMA = "dual-optical-v5-online-test-manifest-v1"
V5_PUBLICATION_MANIFEST_SCHEMA = "dual-optical-v5-publications-v1"
V5_TEST_OPENING_SCHEMA = "dual-optical-v5-test-opening-v1"
V5_ROUTE_NAMES = ("rule_baseline", "gnn_assisted")
V5_SCALE_SAMPLING_POLICY = "uniform_over_40_60_100"
DEFAULT_TARGET_ADAPTER_MODULE = "dual_optical_target_track_gnn.v5_adapter"

_V5_ONLINE_ENTRY_FIELDS = (
    "split",
    "seed",
    "corruption_level",
    "revolution_index",
    "snapshot_path",
    "snapshot_sha256",
    "input_fingerprint",
    "tracker_fingerprint",
)


def _read_json_object(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tracker_config_from_mapping(values: Mapping[str, Any]) -> SharedTrackerConfig:
    normalized = dict(values)
    normalized["allowed_heading_offsets_deg"] = tuple(
        float(value) for value in normalized["allowed_heading_offsets_deg"]
    )
    normalized["corridor_x_bounds_m"] = tuple(
        float(value) for value in normalized["corridor_x_bounds_m"]
    )
    return SharedTrackerConfig(**normalized)


def resolve_v5_output_root(output_parent: str | Path) -> Path:
    """Return exactly one versioned V5 output root."""

    parent = Path(output_parent).resolve()
    return parent if parent.name == V5_OUTPUT_VERSION else parent / V5_OUTPUT_VERSION


def _scale_name(target_count: int) -> str:
    return f"target_{int(target_count):03d}"


def _scale_paths(output_root: Path, target_count: int) -> dict[str, str]:
    scale_root = output_root / _scale_name(target_count)
    return {
        "scale_root": str(scale_root),
        "preflight_root": str(scale_root / "preflight"),
        "runtime_root": str(scale_root / "runtime"),
        "dataset_root": str(scale_root / "dataset"),
        "diagnostic_root": str(scale_root / "diagnostic"),
        "results_root": str(scale_root / "results"),
    }


def build_v5_plan(
    *,
    repo_root: str | Path,
    output_parent: str | Path,
    blocks_script: str | Path,
    api_port: int = 41451,
) -> dict[str, Any]:
    """Build a complete, side-effect-free V5 execution plan."""

    repo_root = Path(repo_root).resolve()
    output_root = resolve_v5_output_root(output_parent)
    blocks_script = Path(blocks_script).resolve()
    base_command = [
        "python3",
        "-m",
        "dual_optical_online_benchmark.v5_runner",
        "run",
        "--repo-root",
        str(repo_root),
        "--output-parent",
        str(output_root),
        "--blocks-script",
        str(blocks_script),
        "--api-port",
        str(int(api_port)),
    ]
    scales: list[dict[str, Any]] = []
    for target_count in V5_TARGET_COUNTS:
        protocol = v5_protocol_for_target_count(target_count)
        paths = _scale_paths(output_root, target_count)
        stages = []
        for stage in ("preflight", "calibration", "test"):
            command = [
                *base_command,
                "--stage",
                stage,
                "--target-count",
                str(target_count),
            ]
            stages.append(
                {
                    "stage": stage,
                    "command": shlex.join(command),
                    "output_dir": (
                        paths["preflight_root"]
                        if stage == "preflight"
                        else str(Path(paths["runtime_root"]) / stage)
                    ),
                }
            )
        scales.append(
            {
                "target_count": target_count,
                "protocol": asdict(protocol),
                "protocol_fingerprint": protocol.fingerprint,
                "camera_b_scan_phase_offset_s": (
                    protocol.camera_b_scan_phase_offset_s
                ),
                "preflight": {
                    "seeds": list(PREFLIGHT_SEEDS),
                    "scenarios": [name for name, _, _ in PREFLIGHT_SCENARIOS],
                    "episode_count": len(PREFLIGHT_SEEDS)
                    * len(PREFLIGHT_SCENARIOS),
                },
                "seeds": {
                    "train": list(protocol.train_seeds),
                    "validation": list(protocol.validation_seeds),
                    "test": list(protocol.test_seeds),
                },
                "paths": paths,
                "stages": stages,
            }
        )
    model_command = shlex.join([*base_command, "--stage", "model-freeze"])
    report_command = shlex.join([*base_command, "--stage", "report"])
    all_command = shlex.join([*base_command, "--stage", "all"])
    return {
        "schema_version": V5_PLAN_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "output_version": V5_OUTPUT_VERSION,
        "output_root": str(output_root),
        "repo_root": str(repo_root),
        "blocks_script": str(blocks_script),
        "api_port": int(api_port),
        "target_counts": list(V5_TARGET_COUNTS),
        "camera_b_scan_phase_offset_s": V5_CAMERA_B_PHASE_OFFSET_S,
        "phase_zero_control_included": False,
        "phase_contribution_isolatable": False,
        "screenshots_saved": False,
        "stage_order": [
            "preflight_40_60_100",
            "calibration_40_60_100",
            "shared_model_freeze",
            "test_40_60_100",
            "report",
        ],
        "shared_model": {
            "target_counts": list(V5_TARGET_COUNTS),
            "scale_sampling_policy": V5_SCALE_SAMPLING_POLICY,
            "initialization_count": 5,
            "training_splits": ["train"],
            "selection_splits": ["validation"],
            "test_labels_available_during_selection": False,
            "command": model_command,
            "output_dir": str(output_root / "shared_target_track_model"),
        },
        "scales": scales,
        "commands": {
            "all": all_command,
            "model_freeze": model_command,
            "report": report_command,
        },
    }


def write_v5_plan(
    *,
    repo_root: str | Path,
    output_parent: str | Path,
    blocks_script: str | Path,
    api_port: int = 41451,
) -> Path:
    plan = build_v5_plan(
        repo_root=repo_root,
        output_parent=output_parent,
        blocks_script=blocks_script,
        api_port=api_port,
    )
    output_root = Path(plan["output_root"])
    path = output_root / "v5_plan.json"
    write_json(path, plan)
    return path


def create_diagnostic_tracker_freeze(
    calibration_evidence: str | Path,
    output_path: str | Path,
    protocol: BenchmarkProtocol,
) -> Path:
    """Freeze the recorded best-effort candidate without granting formal use."""

    evidence_path = Path(calibration_evidence).resolve()
    evidence_hash_before = sha256_file(evidence_path)
    evidence = _read_json_object(evidence_path)
    if evidence.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("tracker calibration evidence protocol mismatch")
    if evidence.get("test_data_accessed") is not False:
        raise ValueError("diagnostic tracker evidence accessed reserved test data")
    acceptance = evidence.get("acceptance")
    if not isinstance(acceptance, Mapping) or acceptance.get("accepted") is not False:
        raise ValueError("diagnostic continuation requires failed formal acceptance")
    selected_config_values = evidence.get("selected_config")
    selected_fingerprint = str(evidence.get("selected_tracker_fingerprint") or "")
    if not isinstance(selected_config_values, Mapping) or not selected_fingerprint:
        raise ValueError("tracker evidence does not identify a best-effort candidate")
    config = _tracker_config_from_mapping(selected_config_values)
    if config.fingerprint != selected_fingerprint:
        raise ValueError("selected tracker evidence fingerprint mismatch")
    candidates = evidence.get("candidates")
    if not isinstance(candidates, list) or not any(
        isinstance(candidate, Mapping)
        and candidate.get("tracker_fingerprint") == selected_fingerprint
        and candidate.get("config") == selected_config_values
        for candidate in candidates
    ):
        raise ValueError("selected best-effort tracker is absent from candidate evidence")
    failure_reasons = [str(value) for value in acceptance.get("failure_reasons", ())]
    if not failure_reasons:
        failure_reasons = [
            str(name)
            for name, passed in dict(acceptance.get("checks", {})).items()
            if passed is not True
        ]
    if not failure_reasons:
        raise ValueError("failed tracker acceptance has no recorded reason")
    payload: dict[str, Any] = {
        "schema_version": V5_DIAGNOSTIC_TRACKER_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "acceptance_passed": False,
        "failure_reasons": failure_reasons,
        "source_calibration_evidence": str(evidence_path),
        "source_calibration_evidence_sha256": evidence_hash_before,
        "source_acceptance": dict(acceptance),
        "selected_candidate_basis": "best_effort_candidate_recorded_by_calibration",
        "tracker_config": asdict(config),
        "tracker_fingerprint": config.fingerprint,
        "test_data_accessed": False,
    }
    payload["diagnostic_freeze_fingerprint"] = _canonical_sha256(payload)
    output_path = Path(output_path).resolve()
    formal_freeze_path = evidence_path.with_name("shared_tracker.json")
    if output_path == formal_freeze_path:
        raise ValueError("diagnostic tracker cannot overwrite the formal freeze")
    write_json(output_path, payload)
    if sha256_file(evidence_path) != evidence_hash_before:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("source calibration evidence changed while freezing")
    return output_path


def load_diagnostic_tracker_freeze(
    path: str | Path,
    protocol: BenchmarkProtocol | None = None,
) -> tuple[dict[str, Any], SharedTrackerConfig]:
    freeze_path = Path(path).resolve()
    payload = _read_json_object(freeze_path)
    if payload.get("schema_version") != V5_DIAGNOSTIC_TRACKER_SCHEMA:
        raise ValueError("unsupported V5 diagnostic tracker schema")
    if (
        payload.get("diagnostic_only") is not True
        or payload.get("formal_use_allowed") is not False
        or payload.get("acceptance_passed") is not False
        or payload.get("test_data_accessed") is not False
    ):
        raise ValueError("diagnostic tracker freeze grants an invalid capability")
    unsigned = dict(payload)
    stored_fingerprint = str(unsigned.pop("diagnostic_freeze_fingerprint", ""))
    if stored_fingerprint != _canonical_sha256(unsigned):
        raise ValueError("diagnostic tracker freeze fingerprint mismatch")
    evidence_path = Path(str(payload.get("source_calibration_evidence") or ""))
    if not evidence_path.is_file():
        raise ValueError("diagnostic tracker source evidence is unavailable")
    if sha256_file(evidence_path) != payload.get("source_calibration_evidence_sha256"):
        raise ValueError("diagnostic tracker source evidence changed")
    evidence = _read_json_object(evidence_path)
    if evidence.get("acceptance", {}).get("accepted") is not False:
        raise ValueError("diagnostic tracker no longer points to failed acceptance")
    config = _tracker_config_from_mapping(payload["tracker_config"])
    if config.fingerprint != payload.get("tracker_fingerprint"):
        raise ValueError("diagnostic tracker config fingerprint mismatch")
    if protocol is not None:
        if payload.get("protocol_fingerprint") != protocol.fingerprint:
            raise ValueError("diagnostic tracker protocol mismatch")
        if int(payload.get("target_count", -1)) != protocol.target_count:
            raise ValueError("diagnostic tracker target count mismatch")
    return payload, config


def _load_any_tracker_freeze(
    path: str | Path,
    protocol: BenchmarkProtocol,
) -> tuple[str, dict[str, Any], SharedTrackerConfig]:
    payload = _read_json_object(path)
    if payload.get("schema_version") == V5_DIAGNOSTIC_TRACKER_SCHEMA:
        diagnostic, config = load_diagnostic_tracker_freeze(path, protocol)
        return "diagnostic", diagnostic, config
    formal, config = load_tracker_freeze(path)
    if formal.get("validation_metrics", {}).get("acceptance", {}).get("accepted") is not True:
        raise ValueError("formal tracker freeze lacks positive acceptance")
    if config.fingerprint != payload.get("tracker_fingerprint"):
        raise ValueError("formal tracker fingerprint mismatch")
    return "formal", formal, config


def _expected_dataset_keys(
    protocol: BenchmarkProtocol, phase: str
) -> set[tuple[str, int, str, int]]:
    seeds = (
        protocol.train_seeds + protocol.validation_seeds
        if phase == "calibration"
        else protocol.test_seeds
    )
    return {
        (
            split_for_seed(protocol, seed),
            int(seed),
            level,
            revolution,
        )
        for seed in seeds
        for level in protocol.corruption_levels
        for revolution in range(1, protocol.revolution_count + 1)
    }


def write_diagnostic_dataset_manifest(
    dataset_root: str | Path,
    entries: Sequence[Mapping[str, Any]],
    protocol: BenchmarkProtocol,
    *,
    phase: str,
    tracker_freeze: str | Path,
    model_freeze: str | Path | None = None,
) -> Path:
    """Write an explicitly non-formal manifest without formal marker aliases."""

    if phase not in {"calibration", "test"}:
        raise ValueError("diagnostic dataset phase must be calibration or test")
    tracker_freeze = Path(tracker_freeze).resolve()
    tracker_kind, tracker_payload, tracker_config = _load_any_tracker_freeze(
        tracker_freeze, protocol
    )
    model_payload: dict[str, Any] | None = None
    model_path: Path | None = None
    if phase == "test":
        if model_freeze is None:
            raise RuntimeError("diagnostic test snapshots require a frozen V5 model")
        model_path = Path(model_freeze).resolve()
        model_payload = validate_v5_model_freeze(model_path)
        if protocol.target_count not in model_payload["target_counts"]:
            raise ValueError("V5 model freeze does not cover this target scale")
    elif model_freeze is not None:
        raise ValueError("calibration manifest must not depend on a model freeze")

    normalized = sorted(
        (dict(entry) for entry in entries),
        key=lambda item: (
            ("train", "validation", "test").index(str(item["split"])),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        ),
    )
    keys = {
        (
            str(item["split"]),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in normalized
    }
    expected = _expected_dataset_keys(protocol, phase)
    if len(keys) != len(normalized) or keys != expected:
        raise ValueError(
            "diagnostic dataset is incomplete or duplicated: "
            f"missing={len(expected - keys)}, unexpected={len(keys - expected)}"
        )
    fingerprints = {
        str(entry.get("tracker_fingerprint") or "") for entry in normalized
    }
    if fingerprints != {tracker_config.fingerprint}:
        raise ValueError("diagnostic snapshots do not use the selected tracker")
    dataset_root = Path(dataset_root).resolve()
    payload: dict[str, Any] = {
        "schema_version": V5_DIAGNOSTIC_DATASET_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "phase": phase,
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "camera_b_scan_phase_offset_s": protocol.camera_b_scan_phase_offset_s,
        "tracker_status": tracker_kind,
        "tracker_freeze": str(tracker_freeze),
        "tracker_freeze_sha256": sha256_file(tracker_freeze),
        "tracker_fingerprint": tracker_config.fingerprint,
        "tracker_acceptance_passed": tracker_kind == "formal",
        "tracker_failure_reasons": (
            []
            if tracker_kind == "formal"
            else list(tracker_payload["failure_reasons"])
        ),
        "model_freeze": None if model_path is None else str(model_path),
        "model_freeze_sha256": (
            None if model_path is None else sha256_file(model_path)
        ),
        "model_frozen_before_test": phase != "test" or model_payload is not None,
        "test_access_allowed": phase == "test",
        "test_labels_accessed_for_model_selection": False,
        "offline_labels_sealed_until_publication": phase == "test",
        "entries": normalized,
    }
    manifest_path = dataset_root / f"diagnostic_{phase}_manifest.json"
    write_json(manifest_path, payload)
    return manifest_path


def validate_diagnostic_dataset_manifest(
    path: str | Path,
    *,
    expected_phase: str | None = None,
    validate_artifacts: bool = True,
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = _read_json_object(path)
    if payload.get("schema_version") != V5_DIAGNOSTIC_DATASET_SCHEMA:
        raise ValueError("unsupported V5 diagnostic dataset schema")
    if (
        payload.get("diagnostic_only") is not True
        or payload.get("formal_use_allowed") is not False
        or payload.get("test_labels_accessed_for_model_selection") is not False
    ):
        raise ValueError("diagnostic dataset violates isolation policy")
    phase = str(payload.get("phase"))
    if phase not in {"calibration", "test"}:
        raise ValueError("invalid diagnostic dataset phase")
    if expected_phase is not None and phase != expected_phase:
        raise ValueError("diagnostic dataset phase mismatch")
    from .contracts import benchmark_protocol_from_mapping

    protocol = benchmark_protocol_from_mapping(payload["protocol"])
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("diagnostic dataset protocol fingerprint mismatch")
    if payload.get("camera_b_scan_phase_offset_s") != V5_CAMERA_B_PHASE_OFFSET_S:
        raise ValueError("diagnostic dataset is not the V5 phase-180 protocol")
    tracker_path = Path(str(payload.get("tracker_freeze") or ""))
    if not tracker_path.is_file() or sha256_file(tracker_path) != payload.get(
        "tracker_freeze_sha256"
    ):
        raise ValueError("diagnostic dataset tracker freeze changed")
    _, _, tracker = _load_any_tracker_freeze(tracker_path, protocol)
    if tracker.fingerprint != payload.get("tracker_fingerprint"):
        raise ValueError("diagnostic dataset tracker fingerprint mismatch")
    if phase == "test":
        model_path = Path(str(payload.get("model_freeze") or ""))
        if not model_path.is_file() or sha256_file(model_path) != payload.get(
            "model_freeze_sha256"
        ):
            raise ValueError("diagnostic test model freeze changed")
        validate_v5_model_freeze(model_path)
        if payload.get("model_frozen_before_test") is not True:
            raise ValueError("diagnostic test opened before model freeze")
    entries = list(payload.get("entries", ()))
    keys = {
        (
            str(item["split"]),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in entries
    }
    if len(keys) != len(entries) or keys != _expected_dataset_keys(protocol, phase):
        raise ValueError("diagnostic dataset entry matrix is incomplete")
    if validate_artifacts:
        for entry in entries:
            snapshot = path.parent / str(entry["snapshot_path"])
            label = path.parent / str(entry["label_path"])
            if sha256_file(snapshot) != entry["snapshot_sha256"]:
                raise ValueError("diagnostic snapshot hash mismatch")
            if sha256_file(label) != entry["label_sha256"]:
                raise ValueError("diagnostic offline label hash mismatch")
    return payload


def materialize_diagnostic_snapshots(
    raw_manifest: str | Path,
    dataset_root: str | Path,
    protocol: BenchmarkProtocol,
    *,
    phase: str,
    tracker_freeze: str | Path,
    model_freeze: str | Path | None = None,
) -> Path:
    """Materialize diagnostic snapshots from a complete raw episode manifest."""

    raw_manifest = Path(raw_manifest).resolve()
    raw = _read_json_object(raw_manifest)
    if raw.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("raw diagnostic manifest protocol mismatch")
    if phase == "calibration":
        if raw.get("test_data_accessed") is not False:
            raise ValueError("calibration raw manifest accessed test data")
    elif phase == "test":
        if raw.get("schema_version") != V5_DIAGNOSTIC_RAW_SCHEMA:
            raise ValueError("test snapshots require a V5 diagnostic raw manifest")
        if raw.get("model_frozen_before_test") is not True:
            raise ValueError("test raw collection predates model freeze")
        if model_freeze is None:
            raise RuntimeError("test snapshot materialization requires model freeze")
        if raw.get("model_freeze_sha256") != sha256_file(model_freeze):
            raise ValueError("raw test and model freeze hashes disagree")
    else:
        raise ValueError("diagnostic phase must be calibration or test")
    _, _, tracker_config = _load_any_tracker_freeze(tracker_freeze, protocol)
    expected_seeds = set(
        protocol.train_seeds + protocol.validation_seeds
        if phase == "calibration"
        else protocol.test_seeds
    )
    episode_records = list(raw.get("episodes", ()))
    actual_seeds = {int(item["seed"]) for item in episode_records}
    if actual_seeds != expected_seeds or len(actual_seeds) != len(episode_records):
        raise ValueError("raw diagnostic episode set is incomplete")
    entries: list[dict[str, Any]] = []
    for record in sorted(episode_records, key=lambda item: int(item["seed"])):
        episode_dir = Path(str(record["episode_dir"])).resolve()
        seed = int(record["seed"])
        validate_raw_episode(episode_dir, protocol, expected_seed=seed)
        entries.extend(
            materialize_episode(
                episode_dir,
                dataset_root,
                protocol,
                tracker_config=tracker_config,
            )
        )
    return write_diagnostic_dataset_manifest(
        dataset_root,
        entries,
        protocol,
        phase=phase,
        tracker_freeze=tracker_freeze,
        model_freeze=model_freeze,
    )


def _validate_calibration_manifest_reference(
    path: str | Path,
    protocol: BenchmarkProtocol,
) -> tuple[str, dict[str, Any]]:
    path = Path(path).resolve()
    payload = _read_json_object(path)
    if payload.get("schema_version") == V5_DIAGNOSTIC_DATASET_SCHEMA:
        payload = validate_diagnostic_dataset_manifest(
            path, expected_phase="calibration", validate_artifacts=False
        )
        status = "diagnostic"
    else:
        from .dataset import load_dataset_manifest

        payload = load_dataset_manifest(path, validate_offline_labels=False)
        if payload.get("phase") != "calibration" or payload.get(
            "test_access_allowed"
        ) is not False:
            raise ValueError("model training accepts calibration manifests only")
        status = "formal"
    if payload.get("protocol_fingerprint") != protocol.fingerprint:
        raise ValueError("model calibration manifest protocol mismatch")
    return status, payload


def register_v5_model_freeze(
    native_model_freeze: str | Path,
    calibration_manifests: Mapping[int, str | Path],
    output_path: str | Path,
) -> Path:
    """Bind one native model to all three calibration scales before test."""

    if set(int(value) for value in calibration_manifests) != set(V5_TARGET_COUNTS):
        raise ValueError("V5 shared model requires 40/60/100 calibration manifests")
    native_path = Path(native_model_freeze).resolve()
    native = _read_json_object(native_path)
    if native.get("test_data_accessed") is not False:
        raise ValueError("native model freeze does not prove test isolation")
    if native.get("test_labels_accessed") is not False:
        raise ValueError("native model freeze does not seal test labels")
    if list(native.get("training_splits", ())) != ["train"]:
        raise ValueError("native model must train on the train split only")
    if list(native.get("selection_splits", ())) != ["validation"]:
        raise ValueError("native model must select on validation only")
    if native.get("scale_sampling_policy") != V5_SCALE_SAMPLING_POLICY:
        raise ValueError("native model did not balance the three target scales")
    if int(native.get("initialization_count", 0)) < 5:
        raise ValueError("native model freeze requires at least five initializations")
    model_fingerprint = str(native.get("model_fingerprint") or "")
    if not model_fingerprint:
        raise ValueError("native model freeze lacks a model fingerprint")
    calibration: dict[str, Any] = {}
    statuses: list[str] = []
    for target_count in V5_TARGET_COUNTS:
        protocol = v5_protocol_for_target_count(target_count)
        manifest_path = Path(calibration_manifests[target_count]).resolve()
        status, _ = _validate_calibration_manifest_reference(manifest_path, protocol)
        statuses.append(status)
        calibration[str(target_count)] = {
            "status": status,
            "manifest": str(manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
            "protocol_fingerprint": protocol.fingerprint,
            "train_seeds": list(protocol.train_seeds),
            "validation_seeds": list(protocol.validation_seeds),
        }
    payload: dict[str, Any] = {
        "schema_version": V5_MODEL_FREEZE_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "output_version": V5_OUTPUT_VERSION,
        "target_counts": list(V5_TARGET_COUNTS),
        "routes": list(V5_ROUTE_NAMES),
        "shared_across_target_scales": True,
        "scale_sampling_policy": V5_SCALE_SAMPLING_POLICY,
        "initialization_count": int(native["initialization_count"]),
        "training_splits": ["train"],
        "selection_splits": ["validation"],
        "test_data_accessed": False,
        "test_labels_accessed": False,
        "model_frozen_before_test": True,
        "native_model_freeze": str(native_path),
        "native_model_freeze_sha256": sha256_file(native_path),
        "model_fingerprint": model_fingerprint,
        "calibration_manifests": calibration,
        "formal_use_allowed": (
            all(status == "formal" for status in statuses)
            and native.get("formal_use_allowed") is True
            and native.get("acceptance_passed") is True
        ),
        "acceptance_passed": native.get("acceptance_passed") is True,
        "formal_route_markers": dict(native.get("formal_route_markers", {})),
    }
    payload["freeze_fingerprint"] = _canonical_sha256(payload)
    output_path = Path(output_path).resolve()
    write_json(output_path, payload)
    return output_path


def validate_v5_model_freeze(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = _read_json_object(path)
    if payload.get("schema_version") != V5_MODEL_FREEZE_SCHEMA:
        raise ValueError("unsupported V5 target-track model freeze schema")
    unsigned = dict(payload)
    stored = str(unsigned.pop("freeze_fingerprint", ""))
    if stored != _canonical_sha256(unsigned):
        raise ValueError("V5 model freeze fingerprint mismatch")
    if (
        payload.get("test_data_accessed") is not False
        or payload.get("test_labels_accessed") is not False
        or payload.get("model_frozen_before_test") is not True
        or payload.get("training_splits") != ["train"]
        or payload.get("selection_splits") != ["validation"]
        or payload.get("scale_sampling_policy") != V5_SCALE_SAMPLING_POLICY
        or payload.get("target_counts") != list(V5_TARGET_COUNTS)
    ):
        raise ValueError("V5 model freeze violates split or scale isolation")
    native = Path(str(payload.get("native_model_freeze") or ""))
    if not native.is_file() or sha256_file(native) != payload.get(
        "native_model_freeze_sha256"
    ):
        raise ValueError("native V5 model freeze changed")
    for target_count in V5_TARGET_COUNTS:
        item = payload.get("calibration_manifests", {}).get(str(target_count), {})
        manifest = Path(str(item.get("manifest") or ""))
        if not manifest.is_file() or sha256_file(manifest) != item.get(
            "manifest_sha256"
        ):
            raise ValueError("V5 calibration manifest changed after model freeze")
        if item.get("protocol_fingerprint") != v5_protocol_for_target_count(
            target_count
        ).fingerprint:
            raise ValueError("V5 model freeze calibration protocol mismatch")
    return payload


class TargetTrackAdapter(Protocol):
    """Delayed interface implemented by ``dual_optical_target_track_gnn``."""

    def train_and_freeze(
        self,
        *,
        calibration_manifests: Mapping[int, Path],
        output_dir: Path,
        scale_sampling_policy: str,
        initialization_count: int,
    ) -> str | Path:
        ...

    def publish_test(
        self,
        *,
        test_manifest: Path,
        model_freeze: Path,
        output_dir: Path,
        routes: Sequence[str],
    ) -> str | Path:
        ...

    def score_publications(
        self,
        *,
        publication_manifest: Path,
        test_manifest: Path,
        output_dir: Path,
    ) -> str | Path:
        ...


class _ModuleTargetTrackAdapter:
    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._module: Any | None = None

    @property
    def module(self) -> Any:
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module

    def train_and_freeze(self, **kwargs: Any) -> str | Path:
        function = getattr(self.module, "train_and_freeze", None)
        if function is None:
            raise RuntimeError(
                f"{self._module_name} must expose train_and_freeze"
            )
        return function(**kwargs)

    def publish_test(self, **kwargs: Any) -> str | Path:
        function = getattr(self.module, "publish_test", None)
        if function is None:
            raise RuntimeError(f"{self._module_name} must expose publish_test")
        return function(**kwargs)

    def score_publications(self, **kwargs: Any) -> str | Path:
        function = getattr(self.module, "score_publications", None)
        if function is None:
            raise RuntimeError(
                f"{self._module_name} must expose score_publications"
            )
        return function(**kwargs)


def load_target_track_adapter(
    module_name: str = DEFAULT_TARGET_ADAPTER_MODULE,
) -> TargetTrackAdapter:
    """Create a lazy adapter; importing this runner never requires the GNN package."""

    return _ModuleTargetTrackAdapter(module_name)


def freeze_shared_target_track_model(
    calibration_manifests: Mapping[int, str | Path],
    output_root: str | Path,
    *,
    adapter: TargetTrackAdapter | None = None,
) -> Path:
    adapter = adapter or load_target_track_adapter()
    normalized = {
        int(count): Path(path).resolve()
        for count, path in calibration_manifests.items()
    }
    if set(normalized) != set(V5_TARGET_COUNTS):
        raise ValueError("shared target-track training requires all V5 scales")
    output_root = Path(output_root).resolve()
    native_path = Path(
        adapter.train_and_freeze(
            calibration_manifests=normalized,
            output_dir=output_root / "native",
            scale_sampling_policy=V5_SCALE_SAMPLING_POLICY,
            initialization_count=5,
        )
    ).resolve()
    return register_v5_model_freeze(
        native_path,
        normalized,
        output_root / "v5_model_freeze.json",
    )


def _reject_offline_label_references(value: Any) -> None:
    """Reject label fields and label-directory paths from an online payload."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in {
                "label_path",
                "label_sha256",
                "label_root",
                "labels_root",
            }:
                raise ValueError("online test manifest contains an offline label field")
            _reject_offline_label_references(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_offline_label_references(item)
        return
    if isinstance(value, str):
        parts = {
            part.lower()
            for part in value.replace("\\", "/").split("/")
            if part
        }
        if "labels" in parts:
            raise ValueError("online test manifest contains an offline label path")


def _load_full_test_manifest_without_labels(path: Path) -> dict[str, Any]:
    payload = _read_json_object(path)
    if payload.get("schema_version") == V5_DIAGNOSTIC_DATASET_SCHEMA:
        payload = validate_diagnostic_dataset_manifest(
            path,
            expected_phase="test",
            validate_artifacts=False,
        )
    else:
        from .dataset import load_dataset_manifest

        payload = load_dataset_manifest(path, validate_offline_labels=False)
    if payload.get("phase") != "test" or payload.get("test_access_allowed") is not True:
        raise ValueError("online publication requires a held-out test manifest")
    return payload


def _validated_online_entry(
    *,
    manifest_path: Path,
    entry: Mapping[str, Any],
    protocol: BenchmarkProtocol,
    tracker_fingerprint: str,
) -> dict[str, Any]:
    missing = [field for field in _V5_ONLINE_ENTRY_FIELDS if field not in entry]
    if missing:
        raise ValueError(f"online test entry is missing fields: {missing}")
    normalized = {field: entry[field] for field in _V5_ONLINE_ENTRY_FIELDS}
    snapshot_relative = Path(str(normalized["snapshot_path"]))
    if snapshot_relative.is_absolute() or ".." in snapshot_relative.parts:
        raise ValueError("online snapshot path must stay below the manifest root")
    snapshot_path = (manifest_path.parent / snapshot_relative).resolve()
    try:
        snapshot_path.relative_to(manifest_path.parent.resolve())
    except ValueError as exc:
        raise ValueError("online snapshot path escaped the manifest root") from exc
    if not snapshot_path.is_file() or sha256_file(snapshot_path) != str(
        normalized["snapshot_sha256"]
    ):
        raise ValueError("online snapshot hash mismatch")
    snapshot = read_snapshot(snapshot_path)
    if snapshot_fingerprint(snapshot) != str(normalized["input_fingerprint"]):
        raise ValueError("online snapshot input fingerprint mismatch")
    expected_identity = (
        str(normalized["split"]),
        int(normalized["seed"]),
        str(normalized["corruption_level"]),
        int(normalized["revolution_index"]),
    )
    actual_identity = (
        snapshot.split,
        snapshot.seed,
        snapshot.corruption_level,
        snapshot.revolution_index,
    )
    if actual_identity != expected_identity:
        raise ValueError("online snapshot identity differs from its manifest entry")
    if (
        snapshot.protocol_fingerprint != protocol.fingerprint
        or snapshot.tracker_fingerprint != tracker_fingerprint
        or normalized["tracker_fingerprint"] != tracker_fingerprint
        or snapshot.target_count != protocol.target_count
    ):
        raise ValueError("online snapshot protocol, scale, or tracker mismatch")
    return normalized


def write_online_test_manifest(
    full_test_manifest: str | Path,
    model_freeze: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Create the label-free V5 input passed to online publication routes."""

    full_path = Path(full_test_manifest).resolve()
    full = _load_full_test_manifest_without_labels(full_path)
    protocol = benchmark_protocol_from_mapping(full["protocol"])
    if (
        protocol.camera_b_scan_phase_offset_s != V5_CAMERA_B_PHASE_OFFSET_S
        or full.get("protocol_fingerprint") != protocol.fingerprint
    ):
        raise ValueError("full test manifest is not the V5 phase-180 protocol")

    model_path = Path(model_freeze).resolve()
    model = validate_v5_model_freeze(model_path)
    model_hash = sha256_file(model_path)
    if protocol.target_count not in model["target_counts"]:
        raise ValueError("V5 model freeze does not cover the test target scale")
    recorded_model_hash = full.get("model_freeze_sha256")
    if recorded_model_hash is not None and recorded_model_hash != model_hash:
        raise ValueError("full test manifest was materialized under another model")

    tracker_path = Path(str(full.get("tracker_freeze") or "")).resolve()
    tracker_hash = str(full.get("tracker_freeze_sha256") or "")
    if not tracker_path.is_file() or sha256_file(tracker_path) != tracker_hash:
        raise ValueError("full test manifest tracker freeze changed")
    _, _, tracker = _load_any_tracker_freeze(tracker_path, protocol)
    tracker_fingerprint = str(full.get("tracker_fingerprint") or "")
    if tracker.fingerprint != tracker_fingerprint:
        raise ValueError("full test manifest tracker fingerprint mismatch")

    destination = (
        full_path.parent / "online_test_manifest.json"
        if output_path is None
        else Path(output_path).resolve()
    )
    if destination.parent != full_path.parent:
        raise ValueError("online test manifest must share the snapshot root")
    entries = [
        _validated_online_entry(
            manifest_path=destination,
            entry=entry,
            protocol=protocol,
            tracker_fingerprint=tracker_fingerprint,
        )
        for entry in full.get("entries", ())
    ]
    keys = {
        (
            str(item["split"]),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in entries
    }
    if len(keys) != len(entries) or keys != _expected_dataset_keys(protocol, "test"):
        raise ValueError("online test manifest entry matrix is incomplete")

    payload: dict[str, Any] = {
        "schema_version": V5_ONLINE_TEST_MANIFEST_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "phase": "test",
        "online_only": True,
        "test_access_allowed": True,
        "source_manifest_schema": str(full.get("schema_version") or ""),
        "dataset_status": (
            "diagnostic"
            if full.get("diagnostic_only") is True
            else "formal"
        ),
        "formal_use_allowed": full.get("formal_use_allowed") is not False,
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "camera_b_scan_phase_offset_s": protocol.camera_b_scan_phase_offset_s,
        "tracker_freeze": str(tracker_path),
        "tracker_freeze_sha256": tracker_hash,
        "tracker_fingerprint": tracker_fingerprint,
        "model_freeze": str(model_path),
        "model_freeze_sha256": model_hash,
        "model_fingerprint": str(model["model_fingerprint"]),
        "entries": entries,
    }
    _reject_offline_label_references(payload)
    payload["online_manifest_fingerprint"] = _canonical_sha256(payload)
    write_json(destination, payload)
    validate_online_test_manifest(
        destination,
        expected_model_freeze=model_path,
        validate_artifacts=True,
    )
    return destination


def validate_online_test_manifest(
    path: str | Path,
    *,
    expected_model_freeze: str | Path | None = None,
    validate_artifacts: bool = True,
) -> dict[str, Any]:
    manifest_path = Path(path).resolve()
    payload = _read_json_object(manifest_path)
    _reject_offline_label_references(payload)
    if payload.get("schema_version") != V5_ONLINE_TEST_MANIFEST_SCHEMA:
        raise ValueError("unsupported V5 online test manifest schema")
    if (
        payload.get("phase") != "test"
        or payload.get("online_only") is not True
        or payload.get("test_access_allowed") is not True
    ):
        raise ValueError("V5 online manifest violates test-input isolation")
    unsigned = dict(payload)
    stored_fingerprint = str(unsigned.pop("online_manifest_fingerprint", ""))
    if stored_fingerprint != _canonical_sha256(unsigned):
        raise ValueError("V5 online manifest fingerprint mismatch")

    protocol = benchmark_protocol_from_mapping(payload["protocol"])
    if (
        payload.get("protocol_fingerprint") != protocol.fingerprint
        or payload.get("target_count") != protocol.target_count
        or payload.get("camera_b_scan_phase_offset_s")
        != V5_CAMERA_B_PHASE_OFFSET_S
    ):
        raise ValueError("V5 online manifest protocol mismatch")

    model_path = Path(str(payload.get("model_freeze") or "")).resolve()
    model_hash = str(payload.get("model_freeze_sha256") or "")
    if not model_path.is_file() or sha256_file(model_path) != model_hash:
        raise ValueError("V5 online manifest model freeze changed")
    if expected_model_freeze is not None:
        expected_model_path = Path(expected_model_freeze).resolve()
        if sha256_file(expected_model_path) != model_hash:
            raise ValueError("V5 online manifest is bound to another model freeze")
    model = validate_v5_model_freeze(model_path)
    if (
        protocol.target_count not in model["target_counts"]
        or payload.get("model_fingerprint") != model.get("model_fingerprint")
    ):
        raise ValueError("V5 online manifest model identity mismatch")

    tracker_path = Path(str(payload.get("tracker_freeze") or "")).resolve()
    if not tracker_path.is_file() or sha256_file(tracker_path) != payload.get(
        "tracker_freeze_sha256"
    ):
        raise ValueError("V5 online manifest tracker freeze changed")
    _, _, tracker = _load_any_tracker_freeze(tracker_path, protocol)
    tracker_fingerprint = str(payload.get("tracker_fingerprint") or "")
    if tracker.fingerprint != tracker_fingerprint:
        raise ValueError("V5 online manifest tracker identity mismatch")

    entries = list(payload.get("entries", ()))
    if any(set(entry) != set(_V5_ONLINE_ENTRY_FIELDS) for entry in entries):
        raise ValueError("V5 online entries contain non-online fields")
    keys = {
        (
            str(item["split"]),
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        )
        for item in entries
    }
    if len(keys) != len(entries) or keys != _expected_dataset_keys(protocol, "test"):
        raise ValueError("V5 online test entry matrix is incomplete")
    if validate_artifacts:
        for entry in entries:
            _validated_online_entry(
                manifest_path=manifest_path,
                entry=entry,
                protocol=protocol,
                tracker_fingerprint=tracker_fingerprint,
            )
    return payload


def validate_publication_manifest(
    path: str | Path,
    *,
    online_test_manifest: str | Path | None = None,
    model_freeze: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload = _read_json_object(path)
    if payload.get("schema_version") != V5_PUBLICATION_MANIFEST_SCHEMA:
        raise ValueError("unsupported V5 publication manifest schema")
    if payload.get("test_labels_accessed") is not False:
        raise ValueError("route publication accessed test labels")
    if tuple(payload.get("routes", ())) != V5_ROUTE_NAMES:
        raise ValueError("publication manifest does not contain both V5 routes")
    online_hash = str(payload.get("online_test_manifest_sha256") or "")
    model_hash = str(payload.get("model_freeze_sha256") or "")
    online_fingerprint = str(payload.get("online_manifest_fingerprint") or "")
    if not online_hash or not model_hash or not online_fingerprint:
        raise ValueError("publication manifest lacks input/model hash binding")
    if online_test_manifest is not None:
        online_path = Path(online_test_manifest).resolve()
        online = validate_online_test_manifest(
            online_path,
            expected_model_freeze=model_freeze,
            validate_artifacts=True,
        )
        if online_hash != sha256_file(online_path):
            raise ValueError("publication manifest was built from another online input")
        if online_fingerprint != online.get("online_manifest_fingerprint"):
            raise ValueError("publication manifest online fingerprint mismatch")
    if model_freeze is not None:
        model_path = Path(model_freeze).resolve()
        validate_v5_model_freeze(model_path)
        if model_hash != sha256_file(model_path):
            raise ValueError("publication manifest was built from another model")
    return payload


def collect_diagnostic_test_raw(
    *,
    repo_root: str | Path,
    output_root: str | Path,
    protocol: BenchmarkProtocol,
    blocks_script: str | Path,
    model_freeze: str | Path,
    api_port: int = 41451,
    max_attempts: int = 2,
    episode_timeout_s: float = 900.0,
) -> Path:
    """Collect held-out raw episodes after model freeze, without formal aliases."""

    model_freeze = Path(model_freeze).resolve()
    model = validate_v5_model_freeze(model_freeze)
    if protocol.target_count not in model["target_counts"]:
        raise ValueError("model freeze does not cover diagnostic test scale")
    repo_root = Path(repo_root).resolve()
    output_root = Path(output_root).resolve()
    phase_root = output_root / "diagnostic_test"
    opening_path = phase_root / "test_opening.json"
    if phase_root.exists() and not opening_path.is_file() and any(phase_root.iterdir()):
        raise RuntimeError(
            "existing diagnostic test data lacks a pre-test model opening marker"
        )
    phase_root.mkdir(parents=True, exist_ok=True)
    if opening_path.is_file():
        opening = _read_json_object(opening_path)
        if (
            opening.get("schema_version") != V5_TEST_OPENING_SCHEMA
            or opening.get("protocol_fingerprint") != protocol.fingerprint
            or opening.get("model_freeze_sha256") != sha256_file(model_freeze)
            or opening.get("model_frozen_before_test") is not True
        ):
            raise RuntimeError(
                "diagnostic test set was opened under a different model freeze"
            )
    else:
        write_json(
            opening_path,
            {
                "schema_version": V5_TEST_OPENING_SCHEMA,
                "experiment_profile": V5_EXPERIMENT_PROFILE,
                "protocol_fingerprint": protocol.fingerprint,
                "target_count": protocol.target_count,
                "test_seeds": list(protocol.test_seeds),
                "model_freeze": str(model_freeze),
                "model_freeze_sha256": sha256_file(model_freeze),
                "model_frozen_before_test": True,
                "test_labels_accessed_for_model_selection": False,
            },
        )
    seeds = protocol.test_seeds
    launch_config = __import__(
        "dual_optical_online_benchmark.episode_worker",
        fromlist=["build_config"],
    ).build_config(int(seeds[0]), api_port, protocol=protocol)
    settings_path = write_airsim_settings(
        phase_root / "settings.json", launch_config, CameraSpec()
    )
    reusable = {
        int(seed): _load_reusable_receipt(
            phase_root / f"airsim_seed_{int(seed)}_online{protocol.target_count}",
            protocol,
            int(seed),
        )
        for seed in seeds
    }
    process = (
        LocalBlocksProcess(
            Path(blocks_script),
            settings_path,
            phase_root,
            api_port=api_port,
            prefer_nvidia_offload=True,
        )
        if any(receipt is None for receipt in reusable.values())
        else None
    )
    if process is not None:
        process.start()
    records: list[dict[str, Any]] = []
    try:
        if process is not None:
            _wait_for_rpc(api_port, process, 120.0)
        for index, seed_value in enumerate(seeds):
            seed = int(seed_value)
            episode_dir = (
                phase_root / f"airsim_seed_{seed}_online{protocol.target_count}"
            )
            receipt = reusable[seed]
            attempts: list[dict[str, Any]] = []
            if receipt is None:
                if process is None:
                    raise RuntimeError("missing diagnostic episode requires AirSim")
                for attempt in range(1, max_attempts + 1):
                    if index > 0 or attempt > 1:
                        _reset_client(api_port)
                    result = _run_worker(
                        repo_root,
                        episode_dir,
                        seed,
                        api_port,
                        episode_timeout_s,
                        protocol=protocol,
                    )
                    result["attempt"] = attempt
                    attempts.append(result)
                    if result["returncode"] not in {0, 2}:
                        continue
                    try:
                        validation = validate_raw_episode(
                            episode_dir, protocol, expected_seed=seed
                        )
                    except ValueError:
                        continue
                    receipt = {
                        "schema_version": BATCH_SCHEMA_VERSION,
                        "protocol_fingerprint": protocol.fingerprint,
                        "seed": seed,
                        "split": "test",
                        "raw_hashes": validation["files"],
                        "screenshots_saved": False,
                    }
                    write_json(_receipt_path(episode_dir), receipt)
                    break
                if receipt is None:
                    raise RuntimeError(
                        f"diagnostic AirSim episode {seed} failed after "
                        f"{max_attempts} attempts"
                    )
            records.append(
                {
                    "seed": seed,
                    "split": "test",
                    "episode_dir": str(episode_dir.resolve()),
                    "receipt_sha256": sha256_file(_receipt_path(episode_dir)),
                    "reused": not attempts,
                    "attempts": attempts,
                }
            )
    finally:
        if process is not None:
            process.stop()
            write_json(phase_root / "blocks_diagnostics.json", process.diagnostics())
    payload = {
        "schema_version": V5_DIAGNOSTIC_RAW_SCHEMA,
        "experiment_profile": V5_EXPERIMENT_PROFILE,
        "phase": "test",
        "diagnostic_only": True,
        "formal_use_allowed": False,
        "protocol": asdict(protocol),
        "protocol_fingerprint": protocol.fingerprint,
        "target_count": protocol.target_count,
        "camera_b_scan_phase_offset_s": protocol.camera_b_scan_phase_offset_s,
        "model_freeze": str(model_freeze),
        "model_freeze_sha256": sha256_file(model_freeze),
        "model_frozen_before_test": True,
        "test_data_accessed": True,
        "test_labels_accessed_for_model_selection": False,
        "screenshots_saved": False,
        "reset_separated_episodes": True,
        "episodes": records,
    }
    path = phase_root / "diagnostic_raw_test_manifest.json"
    write_json(path, payload)
    return path


@dataclass
class V5Runner:
    repo_root: Path
    output_root: Path
    blocks_script: Path
    api_port: int = 41451
    max_attempts: int = 2
    episode_timeout_s: float = 900.0
    adapter: TargetTrackAdapter | None = None
    preflight_fn: Callable[..., Path] = run_preflight
    run_phase_fn: Callable[..., Path] = run_phase

    @classmethod
    def create(
        cls,
        *,
        repo_root: str | Path,
        output_parent: str | Path,
        blocks_script: str | Path,
        api_port: int = 41451,
        max_attempts: int = 2,
        episode_timeout_s: float = 900.0,
        adapter: TargetTrackAdapter | None = None,
    ) -> "V5Runner":
        return cls(
            repo_root=Path(repo_root).resolve(),
            output_root=resolve_v5_output_root(output_parent),
            blocks_script=Path(blocks_script).resolve(),
            api_port=int(api_port),
            max_attempts=int(max_attempts),
            episode_timeout_s=float(episode_timeout_s),
            adapter=adapter,
        )

    @property
    def run_manifest_path(self) -> Path:
        return self.output_root / "v5_run_manifest.json"

    def plan(self, *, write: bool = False) -> dict[str, Any]:
        plan = build_v5_plan(
            repo_root=self.repo_root,
            output_parent=self.output_root,
            blocks_script=self.blocks_script,
            api_port=self.api_port,
        )
        if write:
            write_json(self.output_root / "v5_plan.json", plan)
        return plan

    def _new_state(self) -> dict[str, Any]:
        return {
            "schema_version": V5_RUN_SCHEMA,
            "experiment_profile": V5_EXPERIMENT_PROFILE,
            "output_version": V5_OUTPUT_VERSION,
            "output_root": str(self.output_root),
            "target_counts": list(V5_TARGET_COUNTS),
            "camera_b_scan_phase_offset_s": V5_CAMERA_B_PHASE_OFFSET_S,
            "phase_zero_control_included": False,
            "phase_contribution_isolatable": False,
            "screenshots_saved": False,
            "test_data_used_for_model_selection": False,
            "shared_model_freeze": None,
            "scales": {},
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.run_manifest_path.is_file():
            return self._new_state()
        state = _read_json_object(self.run_manifest_path)
        if state.get("schema_version") != V5_RUN_SCHEMA:
            raise ValueError("unsupported V5 run state")
        if state.get("output_version") != V5_OUTPUT_VERSION:
            raise ValueError("V5 run state output version mismatch")
        return state

    def _save_state(self, state: Mapping[str, Any]) -> Path:
        write_json(self.run_manifest_path, dict(state))
        return self.run_manifest_path

    def run_preflight_scale(self, target_count: int) -> Path:
        protocol = v5_protocol_for_target_count(target_count)
        paths = _scale_paths(self.output_root, target_count)
        summary = Path(
            self.preflight_fn(
                repo_root=self.repo_root,
                output_root=paths["preflight_root"],
                blocks_script=self.blocks_script,
                api_port=self.api_port,
                max_attempts=self.max_attempts,
                episode_timeout_s=self.episode_timeout_s,
                protocol=protocol,
            )
        ).resolve()
        state = self._load_state()
        scale = dict(state["scales"].get(str(target_count), {}))
        scale.update(
            {
                "target_count": target_count,
                "protocol_fingerprint": protocol.fingerprint,
                "preflight_summary": str(summary),
                "preflight_summary_sha256": sha256_file(summary),
            }
        )
        state["scales"][str(target_count)] = scale
        self._save_state(state)
        return summary

    def run_calibration_scale(self, target_count: int) -> Path:
        protocol = v5_protocol_for_target_count(target_count)
        paths = _scale_paths(self.output_root, target_count)
        state = self._load_state()
        scale = dict(state["scales"].get(str(target_count), {}))
        preflight = Path(str(scale.get("preflight_summary") or ""))
        if not preflight.is_file():
            preflight = self.run_preflight_scale(target_count)
            state = self._load_state()
            scale = dict(state["scales"][str(target_count)])
        try:
            manifest = Path(
                self.run_phase_fn(
                    repo_root=self.repo_root,
                    output_root=paths["runtime_root"],
                    dataset_root=paths["dataset_root"],
                    seeds=protocol.train_seeds + protocol.validation_seeds,
                    phase="calibration",
                    blocks_script=self.blocks_script,
                    api_port=self.api_port,
                    max_attempts=self.max_attempts,
                    episode_timeout_s=self.episode_timeout_s,
                    preflight_summary=preflight,
                    protocol=protocol,
                )
            ).resolve()
        except RuntimeError:
            dataset_root = Path(paths["dataset_root"])
            evidence = dataset_root / "freezes" / "shared_tracker_calibration.json"
            raw_manifest = dataset_root / "raw_calibration_manifest.json"
            if not evidence.is_file() or not raw_manifest.is_file():
                raise
            evidence_payload = _read_json_object(evidence)
            if evidence_payload.get("acceptance", {}).get("accepted") is not False:
                raise
            diagnostic_freeze = create_diagnostic_tracker_freeze(
                evidence,
                dataset_root / "diagnostic_freezes" / "shared_tracker.json",
                protocol,
            )
            manifest = materialize_diagnostic_snapshots(
                raw_manifest,
                dataset_root,
                protocol,
                phase="calibration",
                tracker_freeze=diagnostic_freeze,
            )
            tracker_status = "diagnostic"
            tracker_freeze = diagnostic_freeze
            failure_reasons = list(
                load_diagnostic_tracker_freeze(diagnostic_freeze, protocol)[0][
                    "failure_reasons"
                ]
            )
        else:
            tracker_status = "formal"
            tracker_freeze = Path(paths["dataset_root"]) / "freezes" / "shared_tracker.json"
            failure_reasons = []
        state = self._load_state()
        scale = dict(state["scales"].get(str(target_count), {}))
        scale.update(
            {
                "target_count": target_count,
                "protocol_fingerprint": protocol.fingerprint,
                "camera_b_scan_phase_offset_s": protocol.camera_b_scan_phase_offset_s,
                "calibration_manifest": str(manifest),
                "calibration_manifest_sha256": sha256_file(manifest),
                "tracker_status": tracker_status,
                "tracker_formal_use_allowed": tracker_status == "formal",
                "tracker_acceptance_passed": tracker_status == "formal",
                "tracker_failure_reasons": failure_reasons,
                "tracker_freeze": str(Path(tracker_freeze).resolve()),
                "tracker_freeze_sha256": sha256_file(tracker_freeze),
            }
        )
        state["scales"][str(target_count)] = scale
        self._save_state(state)
        return manifest

    def freeze_model(self) -> Path:
        state = self._load_state()
        manifests: dict[int, Path] = {}
        for target_count in V5_TARGET_COUNTS:
            scale = state["scales"].get(str(target_count), {})
            path = Path(str(scale.get("calibration_manifest") or ""))
            if not path.is_file():
                raise RuntimeError(
                    "all 40/60/100 calibration manifests are required before model freeze"
                )
            manifests[target_count] = path
        freeze = freeze_shared_target_track_model(
            manifests,
            self.output_root / "shared_target_track_model",
            adapter=self.adapter,
        )
        state["shared_model_freeze"] = str(freeze)
        state["shared_model_freeze_sha256"] = sha256_file(freeze)
        self._save_state(state)
        return freeze

    def _formal_marker_for_scale(
        self, target_count: int, model: Mapping[str, Any]
    ) -> Path | None:
        value = model.get("formal_route_markers", {}).get(str(target_count))
        if not value:
            return None
        marker = Path(str(value)).resolve()
        validate_freeze_marker(marker)
        return marker

    def run_test_scale(self, target_count: int) -> Path:
        protocol = v5_protocol_for_target_count(target_count)
        paths = _scale_paths(self.output_root, target_count)
        state = self._load_state()
        scale = dict(state["scales"].get(str(target_count), {}))
        model_path = Path(str(state.get("shared_model_freeze") or ""))
        model = validate_v5_model_freeze(model_path)
        if state.get("shared_model_freeze_sha256") != sha256_file(model_path):
            raise ValueError("V5 run state model freeze hash mismatch")
        tracker_path = Path(str(scale.get("tracker_freeze") or ""))
        if not tracker_path.is_file():
            raise RuntimeError("calibration tracker must be frozen before V5 test")
        formal_candidate = (
            scale.get("tracker_status") == "formal"
            and model.get("formal_use_allowed") is True
        )
        # A diagnostic run never asks the formal validator to bless a marker.
        formal_marker = (
            self._formal_marker_for_scale(target_count, model)
            if formal_candidate
            else None
        )
        if formal_candidate and formal_marker is not None:
            expected_marker = Path(paths["dataset_root"]) / "freezes" / "all_routes_frozen.json"
            if formal_marker != expected_marker.resolve():
                raise ValueError("formal marker must be installed by the route owner")
            scoring_manifest = Path(
                self.run_phase_fn(
                    repo_root=self.repo_root,
                    output_root=paths["runtime_root"],
                    dataset_root=paths["dataset_root"],
                    seeds=protocol.test_seeds,
                    phase="test",
                    blocks_script=self.blocks_script,
                    api_port=self.api_port,
                    max_attempts=self.max_attempts,
                    episode_timeout_s=self.episode_timeout_s,
                    protocol=protocol,
                )
            ).resolve()
            test_status = "formal"
        else:
            raw = collect_diagnostic_test_raw(
                repo_root=self.repo_root,
                output_root=paths["runtime_root"],
                protocol=protocol,
                blocks_script=self.blocks_script,
                model_freeze=model_path,
                api_port=self.api_port,
                max_attempts=self.max_attempts,
                episode_timeout_s=self.episode_timeout_s,
            )
            scoring_manifest = materialize_diagnostic_snapshots(
                raw,
                paths["dataset_root"],
                protocol,
                phase="test",
                tracker_freeze=tracker_path,
                model_freeze=model_path,
            )
            test_status = "diagnostic"
        scoring_manifest = Path(scoring_manifest).resolve()
        scoring_manifest_hash = sha256_file(scoring_manifest)
        online_manifest = write_online_test_manifest(
            scoring_manifest,
            model_path,
            Path(paths["dataset_root"]) / "online_test_manifest.json",
        )
        adapter = self.adapter or load_target_track_adapter()
        publication_path = Path(
            adapter.publish_test(
                test_manifest=online_manifest,
                model_freeze=model_path,
                output_dir=Path(paths["results_root"]) / "publications",
                routes=V5_ROUTE_NAMES,
            )
        ).resolve()
        validate_publication_manifest(
            publication_path,
            online_test_manifest=online_manifest,
            model_freeze=model_path,
        )
        if sha256_file(scoring_manifest) != scoring_manifest_hash:
            raise ValueError("full scoring manifest changed during online publication")
        metrics_path = Path(
            adapter.score_publications(
                publication_manifest=publication_path,
                test_manifest=scoring_manifest,
                output_dir=Path(paths["results_root"]),
            )
        ).resolve()
        state = self._load_state()
        scale = dict(state["scales"].get(str(target_count), {}))
        scale.update(
            {
                "test_status": test_status,
                "test_formal_use_allowed": test_status == "formal",
                "online_test_manifest": str(online_manifest),
                "online_test_manifest_sha256": sha256_file(online_manifest),
                "scoring_test_manifest": str(scoring_manifest),
                "scoring_test_manifest_sha256": scoring_manifest_hash,
                "test_manifest": str(scoring_manifest),
                "test_manifest_sha256": scoring_manifest_hash,
                "publication_manifest": str(publication_path),
                "publication_manifest_sha256": sha256_file(publication_path),
                "metrics": str(metrics_path),
                "metrics_sha256": sha256_file(metrics_path),
            }
        )
        state["scales"][str(target_count)] = scale
        self._save_state(state)
        return metrics_path

    def run_all(self) -> Path:
        self.plan(write=True)
        for target_count in V5_TARGET_COUNTS:
            self.run_calibration_scale(target_count)
        self.freeze_model()
        for target_count in V5_TARGET_COUNTS:
            self.run_test_scale(target_count)
        from .v5_reporting import generate_v5_report

        generate_v5_report(self.run_manifest_path)
        return self.run_manifest_path


def _runner_from_args(args: argparse.Namespace) -> V5Runner:
    adapter = load_target_track_adapter(args.adapter_module)
    return V5Runner.create(
        repo_root=args.repo_root,
        output_parent=args.output_parent,
        blocks_script=args.blocks_script,
        api_port=args.api_port,
        max_attempts=args.max_attempts,
        episode_timeout_s=args.episode_timeout_s,
        adapter=adapter,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("--repo-root", type=Path, required=True)
        command.add_argument("--output-parent", type=Path, required=True)
        command.add_argument("--blocks-script", type=Path, required=True)
        command.add_argument("--api-port", type=int, default=41451)
        command.add_argument("--max-attempts", type=int, default=2)
        command.add_argument("--episode-timeout-s", type=float, default=900.0)
        command.add_argument(
            "--adapter-module", default=DEFAULT_TARGET_ADAPTER_MODULE
        )
    run = subparsers.choices["run"]
    run.add_argument(
        "--stage",
        choices=(
            "all",
            "preflight",
            "calibration",
            "model-freeze",
            "test",
            "report",
        ),
        default="all",
    )
    run.add_argument("--target-count", type=int, choices=V5_TARGET_COUNTS)
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="write and print the complete plan without importing the algorithm adapter",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    runner = _runner_from_args(args)
    if args.command == "plan":
        print(json.dumps(runner.plan(write=True), ensure_ascii=False, indent=2))
        return 0
    if args.dry_run:
        print(json.dumps(runner.plan(write=True), ensure_ascii=False, indent=2))
        return 0
    if args.stage in {"preflight", "calibration", "test"}:
        if args.target_count is None:
            raise SystemExit(f"--target-count is required for stage {args.stage}")
        result = getattr(runner, f"run_{args.stage}_scale")(args.target_count)
    elif args.stage == "model-freeze":
        result = runner.freeze_model()
    elif args.stage == "report":
        from .v5_reporting import generate_v5_report

        result = generate_v5_report(runner.run_manifest_path)[1]
    else:
        result = runner.run_all()
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_TARGET_ADAPTER_MODULE",
    "TargetTrackAdapter",
    "V5_DIAGNOSTIC_DATASET_SCHEMA",
    "V5_DIAGNOSTIC_RAW_SCHEMA",
    "V5_DIAGNOSTIC_TRACKER_SCHEMA",
    "V5_MODEL_FREEZE_SCHEMA",
    "V5_ONLINE_TEST_MANIFEST_SCHEMA",
    "V5_PLAN_SCHEMA",
    "V5_PUBLICATION_MANIFEST_SCHEMA",
    "V5_ROUTE_NAMES",
    "V5_RUN_SCHEMA",
    "V5_TEST_OPENING_SCHEMA",
    "V5Runner",
    "build_v5_plan",
    "collect_diagnostic_test_raw",
    "create_diagnostic_tracker_freeze",
    "freeze_shared_target_track_model",
    "load_diagnostic_tracker_freeze",
    "load_target_track_adapter",
    "materialize_diagnostic_snapshots",
    "register_v5_model_freeze",
    "resolve_v5_output_root",
    "validate_diagnostic_dataset_manifest",
    "validate_online_test_manifest",
    "validate_publication_manifest",
    "validate_v5_model_freeze",
    "write_diagnostic_dataset_manifest",
    "write_online_test_manifest",
    "write_v5_plan",
]
