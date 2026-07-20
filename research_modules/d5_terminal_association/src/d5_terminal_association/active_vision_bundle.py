"""Strict active-vision model bundles and fail-closed runtime policy loading."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import time
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
import torch

from .active_vision_contracts import (
    ACTIVE_VISION_ACTION_SPACE_VERSION,
    ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
    ActiveVisionPolicyProposal,
    ActiveVisionSafetyConfigV1,
    ActiveVisionSnapshotV1,
)
from .active_vision_evaluation import (
    ActiveVisionAdmissionReport,
    admission_report_from_manifest,
)
from .active_vision_episode_dataset import ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION
from .active_vision_learning import (
    ACTIVE_VISION_FEATURE_NAMES,
    ACTIVE_VISION_MODEL_SEMANTIC_VERSION,
    ActiveVisionActorCritic,
    ActiveVisionFeatureBounds,
    active_vision_candidate_batch,
)


ACTIVE_VISION_BUNDLE_SCHEMA_VERSION = "d5.active-vision-model-bundle.v3"
ACTIVE_VISION_WEIGHTS_FILENAME = "weights.pt"
ACTIVE_VISION_MANIFEST_FILENAME = "manifest.json"
ACTIVE_VISION_CHECKSUMS_FILENAME = "SHA256SUMS"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ActiveVisionBundleValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class LoadedActiveVisionPolicy:
    model: ActiveVisionActorCritic
    feature_bounds: ActiveVisionFeatureBounds
    manifest: Mapping[str, Any]
    model_fingerprint: str
    bundle_manifest_sha256: str
    bundle_weights_sha256: str
    device: torch.device
    assist_admitted: bool
    safety_config: ActiveVisionSafetyConfigV1
    ood_margin: float = 0.05
    available: bool = True
    failure_reason: str | None = None

    def propose(
        self,
        snapshot: ActiveVisionSnapshotV1,
        *,
        camera_id: str,
        current_timestamp: float,
    ) -> ActiveVisionPolicyProposal:
        batch = active_vision_candidate_batch(
            snapshot,
            camera_id=camera_id,
            current_timestamp=current_timestamp,
            safety_config=self.safety_config,
        )
        if not self.feature_bounds.contains(batch.features, margin=self.ood_margin):
            return ActiveVisionPolicyProposal(
                action=None,
                confidence=0.0,
                inference_latency_ms=0.0,
                model_fingerprint=self.model_fingerprint,
                ood=True,
                failure_reason="model_input_ood",
            )
        features = torch.as_tensor(
            np.array(batch.features, copy=True), dtype=torch.float32, device=self.device
        )
        self.model.eval()
        _synchronize(self.device)
        started = time.perf_counter()
        with torch.no_grad():
            logits, value = self.model(features)
            probabilities = torch.softmax(logits, dim=0)
        _synchronize(self.device)
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not bool(torch.all(torch.isfinite(logits))) or not bool(
            torch.all(torch.isfinite(probabilities))
        ) or not bool(torch.isfinite(value)):
            return ActiveVisionPolicyProposal(
                action=None,
                confidence=0.0,
                inference_latency_ms=latency_ms,
                model_fingerprint=self.model_fingerprint,
                failure_reason="model_non_finite_output",
            )
        selected_index = int(torch.argmax(probabilities).item())
        confidence = float(probabilities[selected_index].detach().cpu())
        return ActiveVisionPolicyProposal(
            action=batch.actions[selected_index],
            confidence=confidence,
            inference_latency_ms=latency_ms,
            model_fingerprint=self.model_fingerprint,
        )


@dataclass(frozen=True)
class UnavailableActiveVisionPolicy:
    failure_reason: str
    model_fingerprint: str | None = None
    available: bool = False
    assist_admitted: bool = False

    def propose(self, *_: Any, **__: Any) -> ActiveVisionPolicyProposal:
        raise RuntimeError(self.failure_reason)


def active_vision_model_fingerprint(
    model_or_state: ActiveVisionActorCritic | Mapping[str, torch.Tensor],
) -> str:
    """Stable fingerprint of tensor names, dtypes, shapes, and bytes."""

    state = (
        model_or_state.state_dict()
        if isinstance(model_or_state, ActiveVisionActorCritic)
        else model_or_state
    )
    if not isinstance(state, Mapping) or not state:
        raise ValueError("model fingerprint requires a non-empty state_dict")
    digest = hashlib.sha256()
    for key in sorted(state):
        value = state[key]
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ValueError("model fingerprint state_dict is invalid")
        tensor = value.detach().cpu().contiguous()
        if not bool(torch.all(torch.isfinite(tensor))):
            raise ValueError("model fingerprint cannot include non-finite tensors")
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(b"\0")
        digest.update(json.dumps(list(tensor.shape), separators=(",", ":")).encode("ascii"))
        digest.update(b"\0")
        digest.update(tensor.numpy().tobytes(order="C"))
    return f"sha256:{digest.hexdigest()}"


def write_active_vision_model_bundle(
    bundle_dir: str | Path,
    model: ActiveVisionActorCritic,
    *,
    feature_bounds: ActiveVisionFeatureBounds,
    dataset_manifest_sha256: str,
    split_sha256: str,
    training_set_sha256: str,
    training_method: str,
    training_config: Mapping[str, Any],
    validation_results: Mapping[str, Any],
    admission_report: ActiveVisionAdmissionReport | None = None,
    model_semantic_version: str = ACTIVE_VISION_MODEL_SEMANTIC_VERSION,
) -> Mapping[str, Any]:
    """Write a research bundle.  No report means assist remains unadmitted."""

    if not isinstance(model, ActiveVisionActorCritic):
        raise TypeError("model must be ActiveVisionActorCritic")
    for name, value in {
        "dataset_manifest_sha256": dataset_manifest_sha256,
        "split_sha256": split_sha256,
        "training_set_sha256": training_set_sha256,
    }.items():
        _validate_sha(value, name)
    method = str(training_method).strip().lower()
    if method not in {"behavior_cloning", "clipped_ppo", "behavior_cloning_then_clipped_ppo"}:
        raise ValueError("unsupported active-vision training method")
    semantic_version = str(model_semantic_version).strip()
    if not semantic_version:
        raise ValueError("model_semantic_version must be non-empty")
    training_payload = _json_object(training_config, "training_config")
    validation_payload = _json_object(validation_results, "validation_results")
    root = Path(bundle_dir)
    root.mkdir(parents=True, exist_ok=True)
    weights_path = root / ACTIVE_VISION_WEIGHTS_FILENAME
    manifest_path = root / ACTIVE_VISION_MANIFEST_FILENAME
    checksums_path = root / ACTIVE_VISION_CHECKSUMS_FILENAME
    existing = [path.name for path in (weights_path, manifest_path, checksums_path) if path.exists()]
    if existing:
        raise FileExistsError(f"active-vision bundle artifacts already exist: {existing}")
    state_dict: dict[str, torch.Tensor] = {}
    for key, value in model.state_dict().items():
        tensor = value.detach().cpu().clone()
        if not bool(torch.all(torch.isfinite(tensor))):
            raise ValueError(f"active-vision model state is non-finite: {key}")
        state_dict[str(key)] = tensor
    _torch_save_atomic(weights_path, state_dict)
    weights_sha = _sha256_file(weights_path)
    fingerprint = active_vision_model_fingerprint(state_dict)
    if admission_report is not None and admission_report.model_fingerprint != fingerprint:
        raise ValueError("admission report fingerprint does not match bundle weights")
    if admission_report is not None and (
        admission_report.dataset_manifest_sha256 != dataset_manifest_sha256
        or admission_report.split_sha256 != split_sha256
        or admission_report.training_set_sha256 != training_set_sha256
    ):
        raise ValueError("admission report dataset hashes do not match bundle training data")
    admission_payload: Mapping[str, Any]
    if admission_report is None:
        admission_payload = {
            "status": "research_candidate_not_admitted",
            "assist_admitted": False,
            "report": None,
        }
    else:
        admission_payload = {
            "status": "assist_admitted" if admission_report.assist_admitted else "research_candidate_not_admitted",
            "assist_admitted": admission_report.assist_admitted,
            "report": dict(admission_report.to_manifest()),
        }
    manifest = {
        "schema_version": ACTIVE_VISION_BUNDLE_SCHEMA_VERSION,
        "model_semantic_version": semantic_version,
        "dataset_schema_version": ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
        "feature_schema_version": ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
        "action_space_version": ACTIVE_VISION_ACTION_SPACE_VERSION,
        "feature_names": list(ACTIVE_VISION_FEATURE_NAMES),
        "architecture": {
            "class_name": "ActiveVisionActorCritic",
            "feature_dim": model.feature_dim,
            "hidden_dim": model.hidden_dim,
        },
        "feature_bounds": {
            "minimum": list(feature_bounds.minimum),
            "maximum": list(feature_bounds.maximum),
            "ood_margin": 0.05,
        },
        "training": {
            "method": method,
            "dataset_manifest_sha256": dataset_manifest_sha256,
            "split_sha256": split_sha256,
            "training_set_sha256": training_set_sha256,
            "config": training_payload,
        },
        "validation_results": validation_payload,
        "weights": {
            "filename": ACTIVE_VISION_WEIGHTS_FILENAME,
            "format": "pytorch_state_dict_weights_only",
            "sha256": weights_sha,
            "size_bytes": weights_path.stat().st_size,
            "model_fingerprint": fingerprint,
        },
        "admission": dict(admission_payload),
    }
    _write_json_atomic(manifest_path, manifest)
    manifest_sha = _sha256_file(manifest_path)
    _write_bytes_atomic(
        checksums_path,
        (
            f"{manifest_sha}  {ACTIVE_VISION_MANIFEST_FILENAME}\n"
            f"{weights_sha}  {ACTIVE_VISION_WEIGHTS_FILENAME}\n"
        ).encode("ascii"),
    )
    load_active_vision_model_bundle(root)
    return MappingProxyType(manifest)


def load_active_vision_model_bundle(
    bundle_dir: str | Path,
    *,
    device: str | torch.device = "cpu",
    safety_config: ActiveVisionSafetyConfigV1 | None = None,
    expected_model_semantic_version: str = ACTIVE_VISION_MODEL_SEMANTIC_VERSION,
) -> LoadedActiveVisionPolicy:
    root = Path(bundle_dir)
    if not root.is_dir():
        raise ActiveVisionBundleValidationError("bundle_missing", "bundle directory is missing")
    manifest_path = root / ACTIVE_VISION_MANIFEST_FILENAME
    weights_path = root / ACTIVE_VISION_WEIGHTS_FILENAME
    checksums_path = root / ACTIVE_VISION_CHECKSUMS_FILENAME
    for path, code in (
        (manifest_path, "manifest_missing"),
        (weights_path, "weights_missing"),
        (checksums_path, "checksums_missing"),
    ):
        if not path.is_file():
            raise ActiveVisionBundleValidationError(code, f"required bundle file is missing: {path.name}")
    checksums = _read_checksums(checksums_path)
    if set(checksums) != {ACTIVE_VISION_MANIFEST_FILENAME, ACTIVE_VISION_WEIGHTS_FILENAME}:
        raise ActiveVisionBundleValidationError(
            "checksums_fields_mismatch", "SHA256SUMS must cover manifest and weights"
        )
    manifest_sha = _sha256_file(manifest_path)
    weights_sha = _sha256_file(weights_path)
    _expect(manifest_sha, checksums[ACTIVE_VISION_MANIFEST_FILENAME], "manifest_sha_mismatch")
    _expect(weights_sha, checksums[ACTIVE_VISION_WEIGHTS_FILENAME], "weights_sha_mismatch")
    manifest = _read_json(manifest_path)
    required_manifest_fields = {
        "schema_version",
        "model_semantic_version",
        "dataset_schema_version",
        "feature_schema_version",
        "action_space_version",
        "feature_names",
        "architecture",
        "feature_bounds",
        "training",
        "validation_results",
        "weights",
        "admission",
    }
    if set(manifest) != required_manifest_fields:
        raise ActiveVisionBundleValidationError(
            "manifest_fields_mismatch", "bundle manifest fields mismatch"
        )
    _expect(manifest.get("schema_version"), ACTIVE_VISION_BUNDLE_SCHEMA_VERSION, "bundle_schema_mismatch")
    _expect(
        manifest.get("model_semantic_version"),
        expected_model_semantic_version,
        "model_semantic_version_mismatch",
    )
    _expect(
        manifest.get("dataset_schema_version"),
        ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
        "dataset_schema_mismatch",
    )
    _expect(manifest.get("feature_schema_version"), ACTIVE_VISION_FEATURE_SCHEMA_VERSION, "feature_schema_mismatch")
    _expect(manifest.get("action_space_version"), ACTIVE_VISION_ACTION_SPACE_VERSION, "action_space_mismatch")
    _expect(tuple(manifest.get("feature_names", ())), ACTIVE_VISION_FEATURE_NAMES, "feature_order_mismatch")
    architecture = _required_mapping(manifest, "architecture")
    if set(architecture) != {"class_name", "feature_dim", "hidden_dim"}:
        raise ActiveVisionBundleValidationError("architecture_fields_mismatch", "architecture fields mismatch")
    _expect(architecture["class_name"], "ActiveVisionActorCritic", "model_class_mismatch")
    try:
        feature_dim = int(architecture["feature_dim"])
        hidden_dim = int(architecture["hidden_dim"])
    except (TypeError, ValueError) as exc:
        raise ActiveVisionBundleValidationError("architecture_invalid", "architecture is invalid") from exc
    _expect(feature_dim, len(ACTIVE_VISION_FEATURE_NAMES), "feature_dim_mismatch")
    try:
        model = ActiveVisionActorCritic(hidden_dim=hidden_dim)
    except (TypeError, ValueError) as exc:
        raise ActiveVisionBundleValidationError("architecture_invalid", "architecture is invalid") from exc
    bounds_payload = _required_mapping(manifest, "feature_bounds")
    if set(bounds_payload) != {"minimum", "maximum", "ood_margin"}:
        raise ActiveVisionBundleValidationError("feature_bounds_fields_mismatch", "feature bounds fields mismatch")
    try:
        bounds = ActiveVisionFeatureBounds(
            minimum=tuple(bounds_payload["minimum"]),
            maximum=tuple(bounds_payload["maximum"]),
        )
        ood_margin = float(bounds_payload["ood_margin"])
    except (TypeError, ValueError) as exc:
        raise ActiveVisionBundleValidationError("feature_bounds_invalid", "feature bounds are invalid") from exc
    if not np.isfinite(ood_margin) or not 0.0 <= ood_margin <= 1.0:
        raise ActiveVisionBundleValidationError("ood_margin_invalid", "OOD margin is invalid")
    training = _required_mapping(manifest, "training")
    if set(training) != {
        "method",
        "dataset_manifest_sha256",
        "split_sha256",
        "training_set_sha256",
        "config",
    }:
        raise ActiveVisionBundleValidationError("training_fields_mismatch", "training fields mismatch")
    if training["method"] not in {
        "behavior_cloning",
        "clipped_ppo",
        "behavior_cloning_then_clipped_ppo",
    }:
        raise ActiveVisionBundleValidationError("training_method_invalid", "training method is invalid")
    for name in ("dataset_manifest_sha256", "split_sha256", "training_set_sha256"):
        _validate_sha(training[name], name, error_type=ActiveVisionBundleValidationError)
    if not isinstance(training["config"], Mapping) or not isinstance(
        manifest.get("validation_results"), Mapping
    ):
        raise ActiveVisionBundleValidationError("training_metadata_invalid", "training metadata is invalid")
    weights = _required_mapping(manifest, "weights")
    if set(weights) != {"filename", "format", "sha256", "size_bytes", "model_fingerprint"}:
        raise ActiveVisionBundleValidationError("weights_fields_mismatch", "weights fields mismatch")
    _expect(weights["filename"], ACTIVE_VISION_WEIGHTS_FILENAME, "weights_filename_mismatch")
    _expect(weights["format"], "pytorch_state_dict_weights_only", "weights_format_mismatch")
    _expect(weights["sha256"], weights_sha, "weights_manifest_sha_mismatch")
    _expect(int(weights["size_bytes"]), weights_path.stat().st_size, "weights_size_mismatch")
    manifest_fingerprint = str(weights["model_fingerprint"])
    if not manifest_fingerprint.startswith("sha256:") or _SHA_PATTERN.fullmatch(
        manifest_fingerprint.removeprefix("sha256:")
    ) is None:
        raise ActiveVisionBundleValidationError(
            "model_fingerprint_invalid", "model fingerprint is invalid"
        )
    admission = _required_mapping(manifest, "admission")
    if set(admission) != {"status", "assist_admitted", "report"}:
        raise ActiveVisionBundleValidationError("admission_fields_mismatch", "admission fields mismatch")
    assist_admitted = bool(admission["assist_admitted"])
    report_payload = admission["report"]
    if report_payload is None:
        if assist_admitted or admission["status"] != "research_candidate_not_admitted":
            raise ActiveVisionBundleValidationError("admission_invalid", "bundle cannot self-admit")
    else:
        if not isinstance(report_payload, Mapping):
            raise ActiveVisionBundleValidationError("admission_invalid", "admission report is invalid")
        try:
            report = admission_report_from_manifest(report_payload)
        except (TypeError, ValueError) as exc:
            raise ActiveVisionBundleValidationError("admission_invalid", "admission report failed validation") from exc
        _expect(
            report.model_fingerprint,
            manifest_fingerprint,
            "admission_fingerprint_mismatch",
        )
        _expect(
            report.dataset_manifest_sha256,
            training["dataset_manifest_sha256"],
            "admission_dataset_manifest_sha_mismatch",
        )
        _expect(
            report.split_sha256,
            training["split_sha256"],
            "admission_split_sha_mismatch",
        )
        _expect(
            report.training_set_sha256,
            training["training_set_sha256"],
            "admission_training_set_sha_mismatch",
        )
        _expect(report.assist_admitted, assist_admitted, "admission_status_mismatch")
        expected_status = "assist_admitted" if assist_admitted else "research_candidate_not_admitted"
        _expect(admission["status"], expected_status, "admission_status_mismatch")
    try:
        state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    except TypeError as exc:
        raise ActiveVisionBundleValidationError(
            "weights_only_unavailable", "PyTorch weights_only loading is unavailable"
        ) from exc
    except Exception as exc:
        raise ActiveVisionBundleValidationError("weights_load_failed", "weights-only load failed") from exc
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise ActiveVisionBundleValidationError("state_dict_invalid", "weights are not a state_dict")
    for key, value in state_dict.items():
        if not isinstance(key, str) or not isinstance(value, torch.Tensor):
            raise ActiveVisionBundleValidationError("state_dict_invalid", "state_dict contains unsafe values")
        if not bool(torch.all(torch.isfinite(value))):
            raise ActiveVisionBundleValidationError("state_dict_non_finite", f"non-finite tensor: {key}")
    fingerprint = active_vision_model_fingerprint(state_dict)
    _expect(manifest_fingerprint, fingerprint, "model_fingerprint_mismatch")
    try:
        model.load_state_dict(state_dict, strict=True)
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ActiveVisionBundleValidationError("state_dict_mismatch", "state_dict shape mismatch") from exc
    target_device = torch.device(device)
    model.to(target_device)
    model.eval()
    return LoadedActiveVisionPolicy(
        model=model,
        feature_bounds=bounds,
        manifest=MappingProxyType(dict(manifest)),
        model_fingerprint=fingerprint,
        bundle_manifest_sha256=manifest_sha,
        bundle_weights_sha256=weights_sha,
        device=target_device,
        assist_admitted=assist_admitted,
        safety_config=safety_config or ActiveVisionSafetyConfigV1(),
        ood_margin=ood_margin,
    )


def load_active_vision_model_bundle_for_runtime(
    bundle_dir: str | Path,
    *,
    device: str | torch.device = "cpu",
    safety_config: ActiveVisionSafetyConfigV1 | None = None,
) -> LoadedActiveVisionPolicy | UnavailableActiveVisionPolicy:
    try:
        return load_active_vision_model_bundle(
            bundle_dir,
            device=device,
            safety_config=safety_config,
        )
    except ActiveVisionBundleValidationError as exc:
        code = exc.code if exc.code.startswith("bundle_") else f"bundle_{exc.code}"
        return UnavailableActiveVisionPolicy(failure_reason=code)
    except Exception as exc:
        return UnavailableActiveVisionPolicy(
            failure_reason=f"bundle_unexpected_{type(exc).__name__}"
        )


def _required_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ActiveVisionBundleValidationError(f"{name}_missing", f"{name} is missing")
    return value


def _expect(actual: Any, expected: Any, code: str) -> None:
    if actual != expected:
        raise ActiveVisionBundleValidationError(code, f"bundle mismatch: {code}")


def _validate_sha(
    value: Any,
    name: str,
    *,
    error_type: type[ValueError] = ValueError,
) -> None:
    if not isinstance(value, str) or _SHA_PATTERN.fullmatch(value) is None:
        if error_type is ActiveVisionBundleValidationError:
            raise ActiveVisionBundleValidationError(f"{name}_invalid", f"{name} is not SHA256")
        raise error_type(f"{name} must be a lowercase SHA256")


def _json_object(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    try:
        encoded = json.dumps(dict(value), sort_keys=True, allow_nan=False, ensure_ascii=True)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{name} must be a JSON object")
    return decoded


def _read_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ActiveVisionBundleValidationError("checksums_read_failed", "cannot read SHA256SUMS") from exc
    for line in lines:
        parts = line.split()
        if len(parts) != 2 or _SHA_PATTERN.fullmatch(parts[0]) is None or parts[1] in result:
            raise ActiveVisionBundleValidationError("checksums_invalid", "SHA256SUMS is invalid")
        result[parts[1]] = parts[0]
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActiveVisionBundleValidationError("manifest_invalid", "manifest is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ActiveVisionBundleValidationError("manifest_invalid", "manifest must be an object")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _torch_save_atomic(path: Path, payload: Mapping[str, torch.Tensor]) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        torch.save(dict(payload), temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    data = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    _write_bytes_atomic(path, data)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _synchronize(device: torch.device) -> None:
    if device.type == "cuda" and torch.cuda.is_available():
        torch.cuda.synchronize(device)


__all__ = [
    "ACTIVE_VISION_BUNDLE_SCHEMA_VERSION",
    "ActiveVisionBundleValidationError",
    "LoadedActiveVisionPolicy",
    "UnavailableActiveVisionPolicy",
    "active_vision_model_fingerprint",
    "load_active_vision_model_bundle",
    "load_active_vision_model_bundle_for_runtime",
    "write_active_vision_model_bundle",
]
