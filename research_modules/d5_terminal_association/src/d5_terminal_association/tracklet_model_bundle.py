"""Validated model bundles and calibrated online edge-probability scoring."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
import torch

from .sparse_tracklet_graph import EDGE_FEATURE_NAMES, NODE_FEATURE_NAMES, SparseTrackletGraph
from .tracklet_dataset import (
    DATASET_SCHEMA_VERSION,
    EDGE_FEATURE_VERSION,
    GRAPH_SCHEMA_VERSION,
    NODE_FEATURE_VERSION,
    sha256_file,
)
from .tracklet_gnn import NativeTrackletEdgeClassifier, graph_tensors


MODEL_BUNDLE_SCHEMA_VERSION = "d5.tracklet-model-bundle.v2"
MODEL_SEMANTIC_VERSION = "1.0.0"
WEIGHTS_FILENAME = "weights.pt"
MANIFEST_FILENAME = "manifest.json"
CHECKSUMS_FILENAME = "SHA256SUMS"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ModelBundleValidationError(ValueError):
    """Strict bundle-load failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class CalibratedTrackletEdgeScorer:
    """Online scorer that emits only calibrated same-target edge probability."""

    model: NativeTrackletEdgeClassifier
    temperature: float
    decision_threshold: float
    manifest: Mapping[str, Any]
    bundle_manifest_sha256: str
    bundle_weights_sha256: str
    device: torch.device
    available: bool = True

    def forward_graph(self, graph: SparseTrackletGraph) -> torch.Tensor:
        if not isinstance(graph, SparseTrackletGraph):
            raise TypeError("online scorer accepts only SparseTrackletGraph")
        node_features, edge_index, edge_features = graph_tensors(graph, device=self.device)
        self.model.eval()
        with torch.no_grad():
            logits = self.model.edge_logits(node_features, edge_index, edge_features)
            return torch.sigmoid(logits / self.temperature)


@dataclass(frozen=True)
class UnavailableTrackletEdgeScorer:
    """Non-throwing load result consumed by the adapter's rule fallback."""

    failure_reason: str
    available: bool = False

    def forward_graph(self, graph: SparseTrackletGraph) -> np.ndarray:
        raise RuntimeError(self.failure_reason)


def write_tracklet_model_bundle(
    bundle_dir: str | Path,
    model: NativeTrackletEdgeClassifier,
    *,
    dataset_manifest_sha256: str,
    split_sha256: str,
    training_set_sha256: str,
    training_config_sha256: str,
    calibration_temperature: float,
    decision_threshold: float,
    validation_results: Mapping[str, Any],
    model_semantic_version: str = MODEL_SEMANTIC_VERSION,
) -> Mapping[str, Any]:
    """Write a research-candidate bundle without granting default admission."""

    if not isinstance(model, NativeTrackletEdgeClassifier):
        raise TypeError("model must be NativeTrackletEdgeClassifier")
    hashes = {
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "split_sha256": split_sha256,
        "training_set_sha256": training_set_sha256,
        "training_config_sha256": training_config_sha256,
    }
    for name, value in hashes.items():
        _validate_sha256(value, name)
    temperature = float(calibration_temperature)
    threshold = float(decision_threshold)
    if not np.isfinite(temperature) or temperature <= 0.0:
        raise ValueError("calibration_temperature must be finite and positive")
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("decision_threshold must be finite and in [0, 1]")
    semantic_version = str(model_semantic_version).strip()
    if not semantic_version:
        raise ValueError("model_semantic_version must be non-empty")
    validation_payload = _json_object(validation_results, "validation_results")

    root = Path(bundle_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = {
        "weights": root / WEIGHTS_FILENAME,
        "manifest": root / MANIFEST_FILENAME,
        "checksums": root / CHECKSUMS_FILENAME,
    }
    existing = [path.name for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(f"bundle artifacts already exist: {existing}")

    state_dict: dict[str, torch.Tensor] = {}
    for key, value in model.state_dict().items():
        tensor = value.detach().cpu().clone()
        if not bool(torch.all(torch.isfinite(tensor))):
            raise ValueError(f"model state contains non-finite tensor: {key}")
        state_dict[str(key)] = tensor
    _torch_save_atomic(paths["weights"], state_dict)
    weights_sha256 = sha256_file(paths["weights"])
    weights_size = paths["weights"].stat().st_size
    manifest = {
        "schema_version": MODEL_BUNDLE_SCHEMA_VERSION,
        "model_semantic_version": semantic_version,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "node_feature_version": NODE_FEATURE_VERSION,
        "edge_feature_version": EDGE_FEATURE_VERSION,
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "architecture": {
            "class_name": "NativeTrackletEdgeClassifier",
            "node_feature_dim": model.node_feature_dim,
            "edge_feature_dim": model.edge_feature_dim,
            "hidden_dim": model.hidden_dim,
            "message_passing_steps": model.message_passing_steps,
            "dropout": model.dropout,
        },
        "training_dataset": {
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "split_sha256": split_sha256,
            "training_set_sha256": training_set_sha256,
            "training_config_sha256": training_config_sha256,
        },
        "calibration": {
            "method": "validation_only_scalar_temperature",
            "source_split": "validation",
            "temperature": temperature,
            "decision_threshold": threshold,
            "threshold_objective": "validation_f1",
        },
        "validation_results": validation_payload,
        "weights": {
            "filename": WEIGHTS_FILENAME,
            "format": "pytorch_state_dict_weights_only",
            "sha256": weights_sha256,
            "size_bytes": weights_size,
        },
        "admission": {
            "status": "research_candidate_not_default",
            "default_model": False,
        },
    }
    _write_json_atomic(paths["manifest"], manifest)
    manifest_sha256 = sha256_file(paths["manifest"])
    checksum_text = (
        f"{manifest_sha256}  {MANIFEST_FILENAME}\n"
        f"{weights_sha256}  {WEIGHTS_FILENAME}\n"
    )
    _write_bytes_atomic(paths["checksums"], checksum_text.encode("ascii"))
    load_tracklet_model_bundle(root)
    return MappingProxyType(manifest)


def load_tracklet_model_bundle(
    bundle_dir: str | Path,
    *,
    device: torch.device | str = "cpu",
    expected_model_semantic_version: str = MODEL_SEMANTIC_VERSION,
    expected_dataset_manifest_sha256: str | None = None,
    expected_split_sha256: str | None = None,
    expected_training_set_sha256: str | None = None,
) -> CalibratedTrackletEdgeScorer:
    """Strictly validate checksums/schema/order and load weights safely."""

    root = Path(bundle_dir)
    if not root.is_dir():
        raise ModelBundleValidationError("bundle_missing", "model bundle directory is missing")
    manifest_path = root / MANIFEST_FILENAME
    weights_path = root / WEIGHTS_FILENAME
    checksums_path = root / CHECKSUMS_FILENAME
    for path, code in (
        (manifest_path, "manifest_missing"),
        (weights_path, "weights_missing"),
        (checksums_path, "checksums_missing"),
    ):
        if not path.is_file():
            raise ModelBundleValidationError(code, f"required bundle file is missing: {path.name}")

    checksums = _read_checksums(checksums_path)
    expected_files = {MANIFEST_FILENAME, WEIGHTS_FILENAME}
    if set(checksums) != expected_files:
        raise ModelBundleValidationError("checksums_fields_mismatch", "SHA256SUMS must cover manifest and weights")
    manifest_sha256 = sha256_file(manifest_path)
    weights_sha256 = sha256_file(weights_path)
    _expect_equal(manifest_sha256, checksums[MANIFEST_FILENAME], "manifest_sha_mismatch")
    _expect_equal(weights_sha256, checksums[WEIGHTS_FILENAME], "weights_sha_mismatch")
    manifest = _read_json(manifest_path)

    _expect_equal(manifest.get("schema_version"), MODEL_BUNDLE_SCHEMA_VERSION, "bundle_schema_mismatch")
    _expect_equal(
        manifest.get("model_semantic_version"),
        expected_model_semantic_version,
        "model_semantic_version_mismatch",
    )
    _expect_equal(
        manifest.get("dataset_schema_version"),
        DATASET_SCHEMA_VERSION,
        "dataset_schema_mismatch",
    )
    _expect_equal(manifest.get("graph_schema_version"), GRAPH_SCHEMA_VERSION, "graph_schema_mismatch")
    _expect_equal(manifest.get("node_feature_version"), NODE_FEATURE_VERSION, "node_feature_version_mismatch")
    _expect_equal(manifest.get("edge_feature_version"), EDGE_FEATURE_VERSION, "edge_feature_version_mismatch")
    _expect_equal(tuple(manifest.get("node_feature_names", ())), NODE_FEATURE_NAMES, "node_feature_order_mismatch")
    _expect_equal(tuple(manifest.get("edge_feature_names", ())), EDGE_FEATURE_NAMES, "edge_feature_order_mismatch")

    architecture = manifest.get("architecture")
    if not isinstance(architecture, Mapping):
        raise ModelBundleValidationError("architecture_missing", "bundle architecture is missing")
    required_architecture = {
        "class_name",
        "node_feature_dim",
        "edge_feature_dim",
        "hidden_dim",
        "message_passing_steps",
        "dropout",
    }
    if set(architecture) != required_architecture:
        raise ModelBundleValidationError("architecture_fields_mismatch", "bundle architecture fields mismatch")
    _expect_equal(architecture["class_name"], "NativeTrackletEdgeClassifier", "model_class_mismatch")
    try:
        node_feature_dim = int(architecture["node_feature_dim"])
        edge_feature_dim = int(architecture["edge_feature_dim"])
        hidden_dim = int(architecture["hidden_dim"])
        message_passing_steps = int(architecture["message_passing_steps"])
        dropout = float(architecture["dropout"])
    except (TypeError, ValueError) as exc:
        raise ModelBundleValidationError("architecture_invalid", "bundle architecture is invalid") from exc
    _expect_equal(node_feature_dim, len(NODE_FEATURE_NAMES), "node_feature_dim_mismatch")
    _expect_equal(edge_feature_dim, len(EDGE_FEATURE_NAMES), "edge_feature_dim_mismatch")
    try:
        model = NativeTrackletEdgeClassifier(
            node_feature_dim=node_feature_dim,
            edge_feature_dim=edge_feature_dim,
            hidden_dim=hidden_dim,
            message_passing_steps=message_passing_steps,
            dropout=dropout,
        )
    except (TypeError, ValueError) as exc:
        raise ModelBundleValidationError("architecture_invalid", "bundle architecture is invalid") from exc

    training_dataset = manifest.get("training_dataset")
    if not isinstance(training_dataset, Mapping):
        raise ModelBundleValidationError("training_dataset_missing", "training dataset metadata is missing")
    required_training_hashes = {
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
        "training_config_sha256",
    }
    if set(training_dataset) != required_training_hashes:
        raise ModelBundleValidationError("training_dataset_fields_mismatch", "training dataset fields mismatch")
    for name in required_training_hashes:
        _validate_sha256(training_dataset[name], name, error_type=ModelBundleValidationError)
    if expected_dataset_manifest_sha256 is not None:
        _expect_equal(
            training_dataset["dataset_manifest_sha256"],
            expected_dataset_manifest_sha256,
            "dataset_manifest_sha_mismatch",
        )
    if expected_split_sha256 is not None:
        _expect_equal(training_dataset["split_sha256"], expected_split_sha256, "split_sha_mismatch")
    if expected_training_set_sha256 is not None:
        _expect_equal(
            training_dataset["training_set_sha256"],
            expected_training_set_sha256,
            "training_set_sha_mismatch",
        )

    calibration = manifest.get("calibration")
    if not isinstance(calibration, Mapping):
        raise ModelBundleValidationError("calibration_missing", "bundle calibration is missing")
    if calibration.get("method") != "validation_only_scalar_temperature":
        raise ModelBundleValidationError("calibration_method_invalid", "unsupported calibration method")
    if calibration.get("source_split") != "validation":
        raise ModelBundleValidationError("calibration_split_invalid", "calibration must use validation only")
    if calibration.get("threshold_objective") != "validation_f1":
        raise ModelBundleValidationError("threshold_objective_invalid", "threshold must be selected on validation F1")
    try:
        temperature = float(calibration["temperature"])
        threshold = float(calibration["decision_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelBundleValidationError("calibration_invalid", "calibration values are invalid") from exc
    if not np.isfinite(temperature) or temperature <= 0.0:
        raise ModelBundleValidationError("temperature_invalid", "temperature must be finite and positive")
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ModelBundleValidationError("threshold_invalid", "decision threshold must be in [0, 1]")
    if not isinstance(manifest.get("validation_results"), Mapping):
        raise ModelBundleValidationError("validation_results_missing", "validation results are missing")
    admission = manifest.get("admission")
    if (
        not isinstance(admission, Mapping)
        or admission.get("default_model") is not False
        or admission.get("status") != "research_candidate_not_default"
    ):
        raise ModelBundleValidationError("admission_invalid", "bundle must not self-admit as a default model")

    weights = manifest.get("weights")
    if not isinstance(weights, Mapping):
        raise ModelBundleValidationError("weights_metadata_missing", "weights metadata is missing")
    _expect_equal(weights.get("filename"), WEIGHTS_FILENAME, "weights_filename_mismatch")
    _expect_equal(weights.get("format"), "pytorch_state_dict_weights_only", "weights_format_mismatch")
    _expect_equal(weights.get("sha256"), weights_sha256, "weights_manifest_sha_mismatch")
    try:
        manifest_weights_size = int(weights.get("size_bytes", -1))
    except (TypeError, ValueError) as exc:
        raise ModelBundleValidationError("weights_size_invalid", "weights size metadata is invalid") from exc
    _expect_equal(manifest_weights_size, weights_path.stat().st_size, "weights_size_mismatch")

    try:
        state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise ModelBundleValidationError(
            "weights_only_unavailable",
            "this PyTorch runtime does not support safe weights-only loading",
        ) from exc
    except Exception as exc:
        raise ModelBundleValidationError("weights_load_failed", "weights-only load failed") from exc
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ModelBundleValidationError("state_dict_invalid", "weights file is not a state_dict mapping")
    for key, value in state_dict.items():
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ModelBundleValidationError("state_dict_invalid", "state_dict contains an unsafe value")
        if not bool(torch.all(torch.isfinite(value))):
            raise ModelBundleValidationError("state_dict_non_finite", f"non-finite tensor: {key}")
    try:
        model.load_state_dict(state_dict, strict=True)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ModelBundleValidationError("state_dict_mismatch", "state_dict does not match architecture") from exc
    target_device = torch.device(device)
    model.to(target_device)
    model.eval()
    return CalibratedTrackletEdgeScorer(
        model=model,
        temperature=temperature,
        decision_threshold=threshold,
        manifest=MappingProxyType(dict(manifest)),
        bundle_manifest_sha256=manifest_sha256,
        bundle_weights_sha256=weights_sha256,
        device=target_device,
    )


def load_tracklet_model_bundle_for_runtime(
    bundle_dir: str | Path,
    *,
    device: torch.device | str = "cpu",
) -> CalibratedTrackletEdgeScorer | UnavailableTrackletEdgeScorer:
    """Convert every strict load failure into an explicit online fallback token."""

    try:
        return load_tracklet_model_bundle(bundle_dir, device=device)
    except ModelBundleValidationError as exc:
        reason = exc.code if exc.code.startswith("bundle_") else f"bundle_{exc.code}"
        return UnavailableTrackletEdgeScorer(failure_reason=reason)
    except Exception as exc:  # Defensive boundary: no load error may escape into identity logic.
        return UnavailableTrackletEdgeScorer(
            failure_reason=f"bundle_unexpected_{type(exc).__name__}"
        )


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ModelBundleValidationError("checksums_invalid", "cannot read SHA256SUMS") from exc
    result: dict[str, str] = {}
    for line in lines:
        parts = line.split("  ")
        if len(parts) != 2 or not _SHA256_PATTERN.fullmatch(parts[0]):
            raise ModelBundleValidationError("checksums_invalid", "invalid SHA256SUMS line")
        filename = parts[1]
        if filename in result or Path(filename).name != filename:
            raise ModelBundleValidationError("checksums_invalid", "invalid checksum filename")
        result[filename] = parts[0]
    return result


def _validate_sha256(
    value: Any,
    name: str,
    *,
    error_type: type[Exception] = ValueError,
) -> None:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        message = f"{name} must be a lowercase SHA256 hex digest"
        if error_type is ModelBundleValidationError:
            raise ModelBundleValidationError("hash_invalid", message)
        raise error_type(message)


def _expect_equal(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise ModelBundleValidationError(code, f"expected {expected!r}, received {actual!r}")


def _json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    try:
        result = json.loads(_canonical_json_bytes(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite JSON data") from exc
    if not isinstance(result, dict):
        raise TypeError(f"{name} must encode an object")
    return result


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: _reject_json_constant(token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ModelBundleValidationError("manifest_invalid", "cannot parse manifest.json") from exc
    if not isinstance(value, dict):
        raise ModelBundleValidationError("manifest_invalid", "manifest must contain an object")
    return value


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"non-finite JSON constant: {token}")


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value))


def _write_bytes_atomic(path: Path, value: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _torch_save_atomic(path: Path, state_dict: Mapping[str, torch.Tensor]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        torch.save(state_dict, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "CHECKSUMS_FILENAME",
    "CalibratedTrackletEdgeScorer",
    "MANIFEST_FILENAME",
    "MODEL_BUNDLE_SCHEMA_VERSION",
    "MODEL_SEMANTIC_VERSION",
    "ModelBundleValidationError",
    "UnavailableTrackletEdgeScorer",
    "WEIGHTS_FILENAME",
    "load_tracklet_model_bundle",
    "load_tracklet_model_bundle_for_runtime",
    "write_tracklet_model_bundle",
]
