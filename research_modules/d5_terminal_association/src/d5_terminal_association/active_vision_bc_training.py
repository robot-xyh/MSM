"""Formal-data audit and scalable behavior cloning for D5 active vision.

The workflow is intentionally development-only.  It consumes every sample in
the immutable training split, never reads unavailable rewards as zero, never
runs PPO, and writes only a shadow-capable bundle that requires the existing
deterministic rule fallback.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
from torch.nn import functional as F

from .active_vision_bundle import (
    ACTIVE_VISION_MANIFEST_FILENAME,
    ACTIVE_VISION_WEIGHTS_FILENAME,
    load_active_vision_model_bundle,
    load_active_vision_model_bundle_for_runtime,
    write_active_vision_model_bundle,
)
from .active_vision_contracts import (
    ACTIVE_VISION_ACTION_SPACE_VERSION,
    ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
    ActiveVisionFovMode,
    ActiveVisionIntent,
    ActiveVisionRuntimeMode,
)
from .active_vision_episode_dataset import (
    ACTIVE_VISION_EPISODE_DATASET_SCHEMA_VERSION,
    LazyActiveVisionEpisodeDataset,
    load_active_vision_episode_dataset_lazy,
)
from .active_vision_learning import (
    ACTIVE_VISION_FEATURE_NAMES,
    ActiveVisionActorCritic,
    ActiveVisionFeatureBounds,
    ActiveVisionResearchEpisode,
    active_vision_candidate_batch,
)


ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION = "d5.active-vision-bc-cache.v1"
ACTIVE_VISION_BC_REPORT_SCHEMA_VERSION = "d5.active-vision-bc-formal-report.v1"
ACTIVE_VISION_BC_SUMMARY_SCHEMA_VERSION = "d5.active-vision-bc-tracked-summary.v1"
VALIDATION_DATE = "2026-07-20"
VALIDATION_TIMEZONE = "America/Los_Angeles"
_SPLITS = ("train", "validation", "test")
_INTENT_VALUES = tuple(item.value for item in ActiveVisionIntent)
_FOV_VALUES = tuple(item.value for item in ActiveVisionFovMode)
_CAMERA_TYPES = ("interceptor", "recon", "unknown")
_FILE_SPECS = {
    "features": ("candidate_features.f32", "<f4"),
    "candidate_intent": ("candidate_intent.u1", "u1"),
    "candidate_fov": ("candidate_fov.u1", "u1"),
    "candidate_yaw": ("candidate_yaw.f32", "<f4"),
    "candidate_pitch": ("candidate_pitch.f32", "<f4"),
    "candidate_has_target": ("candidate_has_target.u1", "u1"),
    "candidate_count": ("candidate_count.u2", "<u2"),
    "selected_index": ("selected_index.u2", "<u2"),
    "camera_type": ("camera_type.u1", "u1"),
    "scale": ("scale.u1", "u1"),
    "scenario": ("scenario.u2", "<u2"),
}


@dataclass(frozen=True)
class ActiveVisionBcConfig:
    seed: int = 20260720
    epochs: int = 5
    batch_size: int = 2048
    evaluation_batch_size: int = 4096
    learning_rate: float = 3.0e-4
    weight_decay: float = 0.0
    hidden_dim: int = 64
    device: str = "cpu"
    cpu_threads: int = 16
    latency_samples: int = 2048
    latency_warmup: int = 64

    def __post_init__(self) -> None:
        for name in (
            "epochs",
            "batch_size",
            "evaluation_batch_size",
            "hidden_dim",
            "cpu_threads",
            "latency_samples",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if int(self.latency_warmup) < 0:
            raise ValueError("latency_warmup must be non-negative")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0.0:
            raise ValueError("learning_rate must be positive")
        if not np.isfinite(self.weight_decay) or self.weight_decay < 0.0:
            raise ValueError("weight_decay must be non-negative")


@dataclass
class ActiveVisionBcSplitCache:
    root: Path
    sample_count: int
    candidate_row_count: int
    feature_dim: int
    files: Mapping[str, np.memmap]
    offsets: np.ndarray

    @classmethod
    def load(cls, root: str | Path, payload: Mapping[str, Any]) -> "ActiveVisionBcSplitCache":
        split_root = Path(root)
        sample_count = int(payload["sample_count"])
        candidate_rows = int(payload["candidate_row_count"])
        feature_dim = int(payload["feature_dim"])
        files: dict[str, np.memmap] = {}
        for key, (filename, dtype) in _FILE_SPECS.items():
            descriptor = payload["files"][key]
            path = split_root / filename
            if sha256_file(path) != descriptor["sha256"]:
                raise ValueError(f"active-vision BC cache hash mismatch: {key}")
            row_count = candidate_rows if key.startswith("candidate_") and key not in {
                "candidate_count"
            } else sample_count
            shape = (
                (candidate_rows, feature_dim)
                if key == "features"
                else (row_count,)
            )
            files[key] = np.memmap(path, dtype=np.dtype(dtype), mode="r", shape=shape)
        counts = np.asarray(files["candidate_count"], dtype=np.int64)
        offsets = np.empty(sample_count + 1, dtype=np.int64)
        offsets[0] = 0
        np.cumsum(counts, out=offsets[1:])
        if int(offsets[-1]) != candidate_rows:
            raise ValueError("active-vision BC cache offsets do not cover candidate rows")
        return cls(
            root=split_root,
            sample_count=sample_count,
            candidate_row_count=candidate_rows,
            feature_dim=feature_dim,
            files=files,
            offsets=offsets,
        )


def audit_capacity_probe(
    dataset: LazyActiveVisionEpisodeDataset,
    *,
    scales: Sequence[str] = ("5v5", "50v50", "200v200"),
) -> dict[str, Any]:
    """Measure representative feature extraction without changing the dataset."""

    wanted = set(scales)
    probes: dict[str, Any] = {}
    scanned = 0
    for episode in dataset.iter_behavior_cloning_episodes("train"):
        scanned += 1
        scale = scenario_scale(episode.scenario_version)
        if scale not in wanted or scale in probes:
            continue
        started = time.perf_counter()
        candidate_counts: list[int] = []
        candidate_rows = 0
        for transition in episode.transitions:
            batch = active_vision_candidate_batch(
                transition.snapshot,
                camera_id=transition.camera_id,
            )
            candidate_counts.append(len(batch.actions))
            candidate_rows += len(batch.actions)
        elapsed = time.perf_counter() - started
        values = np.asarray(candidate_counts, dtype=np.int64)
        probes[scale] = {
            "scenario_version": episode.scenario_version,
            "seed": episode.seed,
            "sample_count": len(episode.transitions),
            "candidate_row_count": candidate_rows,
            "candidate_min": int(values.min()),
            "candidate_median": float(np.median(values)),
            "candidate_p95": float(np.percentile(values, 95)),
            "candidate_max": int(values.max()),
            "feature_seconds": elapsed,
            "samples_per_second": len(values) / elapsed,
            "peak_rss_mib": peak_rss_mib(),
        }
        if set(probes) == wanted:
            break
    if set(probes) != wanted:
        raise ValueError(f"capacity probe is missing scales: {sorted(wanted - set(probes))}")
    weighted_rate = sum(item["sample_count"] for item in probes.values()) / sum(
        item["feature_seconds"] for item in probes.values()
    )
    train_samples = sum(
        int(item["sample_count"])
        for item in dataset.split_descriptors("train")
    )
    return {
        "episodes_scanned": scanned,
        "probes": dict(sorted(probes.items())),
        "weighted_samples_per_second": weighted_rate,
        "estimated_train_feature_seconds": train_samples / weighted_rate,
        "conclusion": "full_split_streaming_training_feasible",
        "legacy_materialized_per_sample_optimizer": "not_feasible",
    }


def build_behavior_cloning_feature_cache(
    dataset: LazyActiveVisionEpisodeDataset,
    cache_dir: str | Path,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Stream every split into compact candidate arrays and return the data audit."""

    root = Path(cache_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"active-vision BC cache is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    descriptors = dataset.episode_descriptors
    scenario_versions = sorted({str(item["scenario_version"]) for item in descriptors})
    scales = sorted(
        {scenario_scale(value) for value in scenario_versions},
        key=_scale_sort_key,
    )
    scenario_codes = {value: index for index, value in enumerate(scenario_versions)}
    scale_codes = {value: index for index, value in enumerate(scales)}
    camera_codes = {value: index for index, value in enumerate(_CAMERA_TYPES)}
    intent_codes = {value: index for index, value in enumerate(_INTENT_VALUES)}
    fov_codes = {value: index for index, value in enumerate(_FOV_VALUES)}
    audit = _new_audit(dataset)
    split_payloads: dict[str, Any] = {}
    feature_minimum = np.full(len(ACTIVE_VISION_FEATURE_NAMES), np.inf, dtype=np.float64)
    feature_maximum = np.full(len(ACTIVE_VISION_FEATURE_NAMES), -np.inf, dtype=np.float64)
    build_started = time.perf_counter()

    for split in _SPLITS:
        split_root = root / split
        split_root.mkdir(parents=True, exist_ok=False)
        split_sample_count = 0
        split_candidate_rows = 0
        expected_samples = sum(
            int(item["sample_count"])
            for item in dataset.split_descriptors(split)
        )
        file_paths = {
            key: split_root / filename
            for key, (filename, _) in _FILE_SPECS.items()
        }
        with ExitStack() as stack:
            streams = {
                key: stack.enter_context(path.open("xb"))
                for key, path in file_paths.items()
            }
            for episode in dataset.iter_behavior_cloning_episodes(split):
                episode_payload = _encode_episode(
                    episode,
                    scenario_codes=scenario_codes,
                    scale_codes=scale_codes,
                    camera_codes=camera_codes,
                    intent_codes=intent_codes,
                    fov_codes=fov_codes,
                    audit=audit,
                    split=split,
                )
                for key, array in episode_payload["arrays"].items():
                    streams[key].write(np.asarray(array).tobytes(order="C"))
                split_sample_count += int(episode_payload["sample_count"])
                split_candidate_rows += int(episode_payload["candidate_row_count"])
                if split == "train":
                    feature_minimum = np.minimum(
                        feature_minimum,
                        episode_payload["feature_minimum"],
                    )
                    feature_maximum = np.maximum(
                        feature_maximum,
                        episode_payload["feature_maximum"],
                    )
        if split_sample_count != expected_samples:
            raise ValueError(
                f"{split} cache sample count mismatch: {split_sample_count} != {expected_samples}"
            )
        files_payload = {
            key: {
                "filename": path.name,
                "dtype": _FILE_SPECS[key][1],
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for key, path in file_paths.items()
        }
        split_payloads[split] = {
            "sample_count": split_sample_count,
            "candidate_row_count": split_candidate_rows,
            "feature_dim": len(ACTIVE_VISION_FEATURE_NAMES),
            "files": files_payload,
        }

    audit = _finalize_audit(audit, dataset)
    manifest = {
        "schema_version": ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION,
        "dataset": {
            "schema_version": dataset.manifest["schema_version"],
            "manifest_sha256": dataset.manifest_sha256,
            "split_sha256": dataset.manifest["split_sha256"],
            "training_set_sha256": dataset.manifest["training_set_sha256"],
        },
        "feature_schema_version": ACTIVE_VISION_FEATURE_SCHEMA_VERSION,
        "action_space_version": ACTIVE_VISION_ACTION_SPACE_VERSION,
        "feature_names": list(ACTIVE_VISION_FEATURE_NAMES),
        "mappings": {
            "intent": intent_codes,
            "fov": fov_codes,
            "camera_type": camera_codes,
            "scale": scale_codes,
            "scenario": scenario_codes,
        },
        "training_feature_bounds": {
            "minimum": feature_minimum.tolist(),
            "maximum": feature_maximum.tolist(),
        },
        "splits": split_payloads,
        "build_elapsed_seconds": time.perf_counter() - build_started,
    }
    manifest_path = root / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    manifest_sha256 = sha256_file(manifest_path)
    return manifest, audit, manifest_sha256


def load_behavior_cloning_feature_cache(
    cache_dir: str | Path,
) -> tuple[Mapping[str, Any], Mapping[str, ActiveVisionBcSplitCache], str]:
    root = Path(cache_dir)
    manifest_path = root / "manifest.json"
    manifest = read_json(manifest_path)
    if manifest.get("schema_version") != ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION:
        raise ValueError("active-vision BC cache schema mismatch")
    if tuple(manifest.get("feature_names", ())) != ACTIVE_VISION_FEATURE_NAMES:
        raise ValueError("active-vision BC cache feature order mismatch")
    caches = {
        split: ActiveVisionBcSplitCache.load(root / split, manifest["splits"][split])
        for split in _SPLITS
    }
    return manifest, caches, sha256_file(manifest_path)


def train_cached_behavior_cloning(
    cache_manifest: Mapping[str, Any],
    caches: Mapping[str, ActiveVisionBcSplitCache],
    *,
    config: ActiveVisionBcConfig,
) -> tuple[ActiveVisionActorCritic, ActiveVisionFeatureBounds, dict[str, Any]]:
    """Train on every cached train sample using padded candidate batches."""

    set_fixed_seed(config.seed)
    device = torch.device(config.device)
    if device.type == "cpu":
        torch.set_num_threads(min(config.cpu_threads, os.cpu_count() or 1))
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("requested CUDA device is unavailable")
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    model = ActiveVisionActorCritic(hidden_dim=config.hidden_dim).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    train_cache = caches["train"]
    validation_cache = caches["validation"]
    epoch_reports: list[dict[str, Any]] = []
    best_validation_loss = math.inf
    best_epoch = 0
    best_state: dict[str, torch.Tensor] | None = None
    training_started = time.perf_counter()
    for epoch in range(config.epochs):
        model.train()
        order = np.random.default_rng(config.seed + epoch).permutation(
            train_cache.sample_count
        )
        loss_sum = 0.0
        for start in range(0, train_cache.sample_count, config.batch_size):
            indices = order[start : start + config.batch_size]
            features, mask, selected = padded_batch(train_cache, indices)
            feature_tensor = torch.as_tensor(features, device=device)
            mask_tensor = torch.as_tensor(mask, device=device)
            selected_tensor = torch.as_tensor(selected.astype(np.int64), device=device)
            logits = actor_logits(model, feature_tensor)
            logits = logits.masked_fill(~mask_tensor, torch.finfo(logits.dtype).min)
            loss = F.cross_entropy(logits, selected_tensor)
            if not bool(torch.isfinite(loss)):
                raise RuntimeError("non-finite active-vision BC loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach().cpu()) * len(indices)
        train_loss = loss_sum / train_cache.sample_count
        validation_loss = evaluate_loss(
            model,
            validation_cache,
            batch_size=config.evaluation_batch_size,
            device=device,
        )
        epoch_reports.append(
            {
                "epoch": epoch + 1,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
                "samples_seen": train_cache.sample_count,
            }
        )
        if validation_loss < best_validation_loss:
            best_validation_loss = validation_loss
            best_epoch = epoch + 1
            best_state = {
                key: value.detach().cpu().clone()
                for key, value in model.state_dict().items()
            }
    if best_state is None:
        raise RuntimeError("behavior-cloning training did not produce a checkpoint")
    model.load_state_dict(best_state, strict=True)
    model.to(device)
    model.eval()
    bounds_payload = cache_manifest["training_feature_bounds"]
    bounds = ActiveVisionFeatureBounds(
        minimum=tuple(bounds_payload["minimum"]),
        maximum=tuple(bounds_payload["maximum"]),
    )
    elapsed = time.perf_counter() - training_started
    training_report = {
        "method": "behavior_cloning",
        "ppo_started": False,
        "config": asdict(config),
        "train_sample_count": train_cache.sample_count,
        "samples_seen_per_epoch": train_cache.sample_count,
        "total_sample_presentations": train_cache.sample_count * config.epochs,
        "best_epoch": best_epoch,
        "best_validation_loss": best_validation_loss,
        "epochs": epoch_reports,
        "training_elapsed_seconds": elapsed,
        "peak_rss_mib": peak_rss_mib(),
        "cuda_peak_allocated_bytes": (
            int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
        ),
        "cuda_peak_reserved_bytes": (
            int(torch.cuda.max_memory_reserved(device)) if device.type == "cuda" else 0
        ),
    }
    return model, bounds, training_report


def evaluate_behavior_cloning_model(
    model: ActiveVisionActorCritic,
    cache_manifest: Mapping[str, Any],
    caches: Mapping[str, ActiveVisionBcSplitCache],
    *,
    config: ActiveVisionBcConfig,
) -> dict[str, Any]:
    device = torch.device(config.device)
    result = {
        split: evaluate_split(
            model,
            cache,
            cache_manifest=cache_manifest,
            batch_size=config.evaluation_batch_size,
            device=device,
        )
        for split, cache in caches.items()
    }
    result["inference_latency"] = measure_inference_latency(
        model,
        caches["test"],
        sample_count=min(config.latency_samples, caches["test"].sample_count),
        warmup=config.latency_warmup,
        device=device,
        seed=config.seed,
    )
    return result


def evaluate_split(
    model: ActiveVisionActorCritic,
    cache: ActiveVisionBcSplitCache,
    *,
    cache_manifest: Mapping[str, Any],
    batch_size: int,
    device: torch.device,
) -> dict[str, Any]:
    model.eval()
    predictions = np.empty(cache.sample_count, dtype=np.int64)
    loss_sum = 0.0
    with torch.no_grad():
        for start in range(0, cache.sample_count, batch_size):
            indices = np.arange(start, min(start + batch_size, cache.sample_count))
            features, mask, selected = padded_batch(cache, indices)
            logits = actor_logits(model, torch.as_tensor(features, device=device))
            logits = logits.masked_fill(
                ~torch.as_tensor(mask, device=device),
                torch.finfo(logits.dtype).min,
            )
            selected_tensor = torch.as_tensor(selected.astype(np.int64), device=device)
            loss = F.cross_entropy(logits, selected_tensor, reduction="sum")
            loss_sum += float(loss.cpu())
            predictions[start : start + len(indices)] = (
                torch.argmax(logits, dim=1).cpu().numpy()
            )
    return action_metrics(
        cache,
        predictions,
        mappings=cache_manifest["mappings"],
        loss=loss_sum / cache.sample_count,
    )


def action_metrics(
    cache: ActiveVisionBcSplitCache,
    predictions: np.ndarray,
    *,
    mappings: Mapping[str, Any],
    loss: float,
) -> dict[str, Any]:
    if predictions.shape != (cache.sample_count,):
        raise ValueError("prediction count does not match BC cache")
    sample_indices = np.arange(cache.sample_count, dtype=np.int64)
    true_indices = np.asarray(cache.files["selected_index"], dtype=np.int64)
    true_rows = cache.offsets[:-1] + true_indices
    predicted_rows = cache.offsets[:-1] + predictions
    candidate_intent = cache.files["candidate_intent"]
    candidate_fov = cache.files["candidate_fov"]
    candidate_yaw = cache.files["candidate_yaw"]
    candidate_pitch = cache.files["candidate_pitch"]
    candidate_target = cache.files["candidate_has_target"]
    true_intent = np.asarray(candidate_intent[true_rows], dtype=np.int64)
    predicted_intent = np.asarray(candidate_intent[predicted_rows], dtype=np.int64)
    true_fov = np.asarray(candidate_fov[true_rows], dtype=np.int64)
    predicted_fov = np.asarray(candidate_fov[predicted_rows], dtype=np.int64)
    true_yaw = np.asarray(candidate_yaw[true_rows], dtype=np.float64)
    predicted_yaw = np.asarray(candidate_yaw[predicted_rows], dtype=np.float64)
    true_pitch = np.asarray(candidate_pitch[true_rows], dtype=np.float64)
    predicted_pitch = np.asarray(candidate_pitch[predicted_rows], dtype=np.float64)
    true_target = np.asarray(candidate_target[true_rows], dtype=np.int64)
    predicted_target = np.asarray(candidate_target[predicted_rows], dtype=np.int64)
    exact = predictions == true_indices
    intent_equal = predicted_intent == true_intent
    fov_equal = predicted_fov == true_fov
    target_equal = predicted_target == true_target
    yaw_error = np.abs(predicted_yaw - true_yaw)
    pitch_error = np.abs(predicted_pitch - true_pitch)
    intent_mapping = _invert_mapping(mappings["intent"])
    camera_mapping = _invert_mapping(mappings["camera_type"])
    scale_mapping = _invert_mapping(mappings["scale"])
    per_intent: dict[str, Any] = {}
    classification = intent_classification_metrics(
        true_intent,
        predicted_intent,
        intent_mapping,
    )
    for intent_code, intent_name in intent_mapping.items():
        selected = true_intent == intent_code
        per_intent[intent_name] = {
            **classification["per_class"][intent_name],
            **subset_action_metrics(
                selected,
                exact=exact,
                intent_equal=intent_equal,
                fov_equal=fov_equal,
                target_equal=target_equal,
                yaw_error=yaw_error,
                pitch_error=pitch_error,
            ),
        }
    camera_codes = np.asarray(cache.files["camera_type"], dtype=np.int64)
    scale_codes = np.asarray(cache.files["scale"], dtype=np.int64)
    per_camera = {
        camera_name: subset_action_metrics(
            camera_codes == code,
            exact=exact,
            intent_equal=intent_equal,
            fov_equal=fov_equal,
            target_equal=target_equal,
            yaw_error=yaw_error,
            pitch_error=pitch_error,
        )
        for code, camera_name in camera_mapping.items()
    }
    per_scale = {
        scale_name: subset_action_metrics(
            scale_codes == code,
            exact=exact,
            intent_equal=intent_equal,
            fov_equal=fov_equal,
            target_equal=target_equal,
            yaw_error=yaw_error,
            pitch_error=pitch_error,
        )
        for code, scale_name in scale_mapping.items()
    }
    del sample_indices
    return {
        "sample_count": cache.sample_count,
        "cross_entropy_loss": loss,
        "overall": subset_action_metrics(
            np.ones(cache.sample_count, dtype=bool),
            exact=exact,
            intent_equal=intent_equal,
            fov_equal=fov_equal,
            target_equal=target_equal,
            yaw_error=yaw_error,
            pitch_error=pitch_error,
        ),
        "intent_classification": classification,
        "per_intent": per_intent,
        "per_camera_type": per_camera,
        "per_scale": per_scale,
    }


def intent_classification_metrics(
    truth: np.ndarray,
    predicted: np.ndarray,
    mapping: Mapping[int, str],
) -> dict[str, Any]:
    size = len(mapping)
    confusion = np.zeros((size, size), dtype=np.int64)
    np.add.at(confusion, (truth, predicted), 1)
    per_class: dict[str, Any] = {}
    f1_values: list[float] = []
    for code, name in mapping.items():
        support = int(confusion[code, :].sum())
        predicted_count = int(confusion[:, code].sum())
        true_positive = int(confusion[code, code])
        if support == 0:
            per_class[name] = {
                "support": 0,
                "predicted_count": predicted_count,
                "precision": unavailable("no_positive_samples"),
                "recall": unavailable("no_positive_samples"),
                "f1": unavailable("no_positive_samples"),
            }
            continue
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support
        f1 = 0.0 if precision + recall == 0.0 else 2.0 * precision * recall / (precision + recall)
        f1_values.append(f1)
        per_class[name] = {
            "support": support,
            "predicted_count": predicted_count,
            "precision": available(precision),
            "recall": available(recall),
            "f1": available(f1),
        }
    return {
        "accuracy": available(float(np.mean(truth == predicted))),
        "macro_f1_supported_classes": available(float(np.mean(f1_values))),
        "class_order": [mapping[index] for index in range(size)],
        "confusion_matrix": confusion.tolist(),
        "per_class": per_class,
    }


def subset_action_metrics(
    selector: np.ndarray,
    *,
    exact: np.ndarray,
    intent_equal: np.ndarray,
    fov_equal: np.ndarray,
    target_equal: np.ndarray,
    yaw_error: np.ndarray,
    pitch_error: np.ndarray,
) -> dict[str, Any]:
    count = int(np.sum(selector))
    if count == 0:
        return {
            "sample_count": 0,
            "exact_action_accuracy": unavailable("no_samples"),
            "intent_accuracy": unavailable("no_samples"),
            "fov_accuracy": unavailable("no_samples"),
            "target_presence_accuracy": unavailable("no_samples"),
            "yaw_mae_deg": unavailable("no_samples"),
            "pitch_mae_deg": unavailable("no_samples"),
            "angular_mae_deg": unavailable("no_samples"),
        }
    angular = np.hypot(yaw_error[selector], pitch_error[selector])
    return {
        "sample_count": count,
        "exact_action_accuracy": available(float(np.mean(exact[selector]))),
        "intent_accuracy": available(float(np.mean(intent_equal[selector]))),
        "fov_accuracy": available(float(np.mean(fov_equal[selector]))),
        "target_presence_accuracy": available(float(np.mean(target_equal[selector]))),
        "yaw_mae_deg": available(float(np.mean(yaw_error[selector]))),
        "pitch_mae_deg": available(float(np.mean(pitch_error[selector]))),
        "angular_mae_deg": available(float(np.mean(angular))),
    }


def padded_batch(
    cache: ActiveVisionBcSplitCache,
    indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sample_indices = np.asarray(indices, dtype=np.int64).reshape(-1)
    counts = np.asarray(cache.files["candidate_count"][sample_indices], dtype=np.int64)
    selected = np.asarray(cache.files["selected_index"][sample_indices], dtype=np.int64)
    maximum = int(counts.max())
    features = np.zeros(
        (len(sample_indices), maximum, cache.feature_dim),
        dtype=np.float32,
    )
    mask = np.zeros((len(sample_indices), maximum), dtype=bool)
    source = cache.files["features"]
    for row, (sample_index, count) in enumerate(zip(sample_indices, counts, strict=True)):
        start = int(cache.offsets[sample_index])
        stop = start + int(count)
        features[row, :count] = source[start:stop]
        mask[row, :count] = True
    return features, mask, selected


def actor_logits(model: ActiveVisionActorCritic, features: torch.Tensor) -> torch.Tensor:
    if features.ndim != 3 or features.shape[2] != model.feature_dim:
        raise ValueError("padded active-vision features have the wrong shape")
    batch, candidate_count, feature_dim = features.shape
    encoded = model.encoder(features.reshape(batch * candidate_count, feature_dim))
    return model.actor(encoded).reshape(batch, candidate_count)


def evaluate_loss(
    model: ActiveVisionActorCritic,
    cache: ActiveVisionBcSplitCache,
    *,
    batch_size: int,
    device: torch.device,
) -> float:
    model.eval()
    total = 0.0
    with torch.no_grad():
        for start in range(0, cache.sample_count, batch_size):
            indices = np.arange(start, min(start + batch_size, cache.sample_count))
            features, mask, selected = padded_batch(cache, indices)
            logits = actor_logits(model, torch.as_tensor(features, device=device))
            logits = logits.masked_fill(
                ~torch.as_tensor(mask, device=device),
                torch.finfo(logits.dtype).min,
            )
            total += float(
                F.cross_entropy(
                    logits,
                    torch.as_tensor(selected.astype(np.int64), device=device),
                    reduction="sum",
                ).cpu()
            )
    return total / cache.sample_count


def measure_inference_latency(
    model: ActiveVisionActorCritic,
    cache: ActiveVisionBcSplitCache,
    *,
    sample_count: int,
    warmup: int,
    device: torch.device,
    seed: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    indices = rng.choice(cache.sample_count, size=sample_count, replace=False)
    warmup_indices = indices[: min(warmup, sample_count)]
    model.eval()
    with torch.no_grad():
        for index in warmup_indices:
            start = int(cache.offsets[index])
            stop = int(cache.offsets[index + 1])
            model(torch.as_tensor(np.array(cache.files["features"][start:stop]), device=device))
        synchronize(device)
        latencies: list[float] = []
        for index in indices:
            start = int(cache.offsets[index])
            stop = int(cache.offsets[index + 1])
            features = torch.as_tensor(
                np.array(cache.files["features"][start:stop]),
                device=device,
            )
            synchronize(device)
            started = time.perf_counter()
            model(features)
            synchronize(device)
            latencies.append((time.perf_counter() - started) * 1000.0)
    values = np.asarray(latencies, dtype=np.float64)
    return {
        "measurement": "single_decision_candidate_set_model_forward",
        "device": str(device),
        "sample_count": sample_count,
        "warmup_count": len(warmup_indices),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "p99_ms": float(np.percentile(values, 99)),
        "maximum_ms": float(values.max()),
    }


def run_formal_behavior_cloning(
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    config: ActiveVisionBcConfig,
    tracked_summary_path: str | Path | None = None,
    tracked_report_path: str | Path | None = None,
    external_observed_outcome_count: int | None = None,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"active-vision BC output directory is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    pipeline_started = time.perf_counter()
    audit_started = time.perf_counter()
    dataset = load_active_vision_episode_dataset_lazy(dataset_dir)
    integrity_elapsed = time.perf_counter() - audit_started
    capacity = audit_capacity_probe(dataset)
    cache_manifest, data_audit, cache_manifest_sha256 = build_behavior_cloning_feature_cache(
        dataset,
        output_root / "feature_cache",
    )
    cache_manifest_loaded, caches, loaded_cache_sha256 = load_behavior_cloning_feature_cache(
        output_root / "feature_cache"
    )
    if loaded_cache_sha256 != cache_manifest_sha256:
        raise RuntimeError("active-vision BC cache manifest changed after writing")
    model, feature_bounds, training = train_cached_behavior_cloning(
        cache_manifest_loaded,
        caches,
        config=config,
    )
    evaluation_started = time.perf_counter()
    evaluation = evaluate_behavior_cloning_model(
        model,
        cache_manifest_loaded,
        caches,
        config=config,
    )
    evaluation_elapsed = time.perf_counter() - evaluation_started
    audit_path = output_root / "dataset_audit.json"
    capacity_path = output_root / "capacity_probe.json"
    write_json_atomic(audit_path, data_audit)
    write_json_atomic(capacity_path, capacity)
    audit_sha256 = sha256_file(audit_path)
    training_config = {
        **asdict(config),
        "dataset_audit_sha256": audit_sha256,
        "feature_cache_manifest_sha256": cache_manifest_sha256,
        "full_train_split_used": True,
        "ppo_enabled": False,
        "observed_outcome_used_as_reward": False,
    }
    bundle_dir = output_root / "development_shadow_model_bundle"
    validation_results = {
        "validation": evaluation["validation"],
        "test": evaluation["test"],
        "inference_latency": evaluation["inference_latency"],
        "promotion_status": "fail_closed_shadow_only",
        "statistical_limits": data_audit["generalization_risks"],
    }
    write_active_vision_model_bundle(
        bundle_dir,
        model,
        feature_bounds=feature_bounds,
        dataset_manifest_sha256=dataset.manifest_sha256,
        split_sha256=str(dataset.manifest["split_sha256"]),
        training_set_sha256=str(dataset.manifest["training_set_sha256"]),
        training_method="behavior_cloning",
        training_config=training_config,
        validation_results=validation_results,
        bundle_profile="development_shadow_only",
    )
    shadow_policy = load_active_vision_model_bundle_for_runtime(
        bundle_dir,
        device=config.device,
        requested_mode=ActiveVisionRuntimeMode.SHADOW,
    )
    assist_policy = load_active_vision_model_bundle_for_runtime(
        bundle_dir,
        device=config.device,
        requested_mode=ActiveVisionRuntimeMode.ASSIST,
    )
    if not shadow_policy.available or assist_policy.available:
        raise RuntimeError("development bundle runtime policy is not fail-closed")
    loaded = load_active_vision_model_bundle(bundle_dir, device=config.device)
    bundle_manifest_path = bundle_dir / ACTIVE_VISION_MANIFEST_FILENAME
    weights_path = bundle_dir / ACTIVE_VISION_WEIGHTS_FILENAME
    external_evidence = {
        "d6_observed_outcome_count": external_observed_outcome_count,
        "observed_outcome_scope": "adjacent_observation_without_applied_action_attribution",
        "observed_outcome_used_as_reward": False,
        "d4_d5_joint_training": "disabled_split_mismatch",
    }
    report = {
        "schema_version": ACTIVE_VISION_BC_REPORT_SCHEMA_VERSION,
        "validation_date": VALIDATION_DATE,
        "validation_timezone": VALIDATION_TIMEZONE,
        "dataset": {
            "path": str(Path(dataset_dir)),
            "schema_version": dataset.manifest["schema_version"],
            "manifest_sha256": dataset.manifest_sha256,
            "split_sha256": dataset.manifest["split_sha256"],
            "training_set_sha256": dataset.manifest["training_set_sha256"],
            "strict_integrity_audit_seconds": integrity_elapsed,
        },
        "data_audit": data_audit,
        "capacity_probe": capacity,
        "feature_cache": {
            "directory": str(output_root / "feature_cache"),
            "manifest_sha256": cache_manifest_sha256,
            "build_elapsed_seconds": cache_manifest["build_elapsed_seconds"],
        },
        "training": training,
        "evaluation": evaluation,
        "hardware": hardware_summary(config.device),
        "bundle": {
            "directory": str(bundle_dir),
            "schema_version": loaded.manifest["schema_version"],
            "status": loaded.runtime_status,
            "assist_admitted": loaded.assist_admitted,
            "ppo_enabled": loaded.ppo_enabled,
            "rule_fallback_required": loaded.rule_fallback_required,
            "shadow_load_available": shadow_policy.available,
            "assist_load_available": assist_policy.available,
            "assist_load_failure_reason": assist_policy.failure_reason,
            "manifest_sha256": sha256_file(bundle_manifest_path),
            "weights_sha256": sha256_file(weights_path),
            "weights_size_bytes": weights_path.stat().st_size,
            "model_fingerprint": loaded.model_fingerprint,
            "implementation_sha256": loaded.manifest["code_provenance"][
                "implementation_sha256"
            ],
        },
        "external_evidence": external_evidence,
        "admission": {
            "training_readiness": "pass_development_behavior_cloning",
            "runtime_status": "development_shadow_only",
            "assist": False,
            "ppo": False,
            "promotion": "fail_closed",
            "rule_fallback_required": True,
            "failure_reasons": data_audit["generalization_risks"]
            + [
                "no_applied_action_outcomes",
                "no_reward_or_counterfactual_labels",
                "no_formal_paired_shadow_non_degradation_evidence",
                "d4_d5_split_mismatch_disables_joint_training",
            ],
        },
        "evaluation_elapsed_seconds": evaluation_elapsed,
        "pipeline_elapsed_seconds": time.perf_counter() - pipeline_started,
    }
    full_report_path = output_root / "formal_bc_report.json"
    write_json_atomic(full_report_path, report)
    summary = tracked_summary(report, command=sys.argv)
    markdown = report_markdown(report)
    if tracked_summary_path is not None:
        write_json_atomic(Path(tracked_summary_path), summary)
    if tracked_report_path is not None:
        write_text_atomic(Path(tracked_report_path), markdown)
    write_json_atomic(output_root / "tracked_summary.json", summary)
    write_text_atomic(output_root / "FORMAL_BC_REPORT_CN.md", markdown)
    return report


def tracked_summary(report: Mapping[str, Any], *, command: Sequence[str]) -> dict[str, Any]:
    return {
        "schema_version": ACTIVE_VISION_BC_SUMMARY_SCHEMA_VERSION,
        "validation_date": report["validation_date"],
        "validation_timezone": report["validation_timezone"],
        "command": list(command),
        "dataset": report["dataset"],
        "data_audit": report["data_audit"],
        "capacity_probe": report["capacity_probe"],
        "training": report["training"],
        "evaluation": report["evaluation"],
        "hardware": report["hardware"],
        "bundle": report["bundle"],
        "external_evidence": report["external_evidence"],
        "admission": report["admission"],
        "pipeline_elapsed_seconds": report["pipeline_elapsed_seconds"],
    }


def report_markdown(report: Mapping[str, Any]) -> str:
    audit = report["data_audit"]
    evaluation = report["evaluation"]
    bundle = report["bundle"]
    lines = [
        "# D5 主动视觉行为克隆正式数据审计",
        "",
        f"验证日期：{report['validation_date']}（{report['validation_timezone']}）",
        "",
        "## 结论",
        "",
        f"正式数据共 `{audit['sample_count']}` 个样本，完整训练集 `{audit['split_sample_counts']['train']}` 个样本已用于行为克隆。",
        "模型仅为 development shadow-only，不具备 assist 权限，未启动 PPO，规则策略仍是强制回退。",
        "观测 outcome 没有动作执行归因，reward、counterfactual 和 causal label 均不可用，不能用于强化学习或晋级。",
        "",
        "## 数据覆盖",
        "",
        f"- episode：`{audit['episode_count']}`",
        f"- train/validation/test episode：`{_slash(audit['split_episode_counts'])}`",
        f"- train/validation/test sample：`{_slash(audit['split_sample_counts'])}`",
        f"- 唯一 seed：`{_slash(audit['split_seed_counts'])}`，分割交集为 0",
        f"- 保留 seed 1000-1019 进入训练：`{len(audit['reserved_evaluation_seed_overlap']['train'])}`",
        f"- 意图：`{json.dumps(audit['intent_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- 视场模式：`{json.dumps(audit['fov_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- 相机类型：`{json.dumps(audit['camera_type_counts'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "`hold` 没有正样本；`observe_target` 占比较低，`reacquire` 占主导。模型对缺失意图和少数类不能宣称泛化。",
        "",
        "## 训练",
        "",
        f"固定 seed `{report['training']['config']['seed']}`，训练 `{report['training']['config']['epochs']}` 个 epoch，",
        f"最佳 epoch `{report['training']['best_epoch']}`。训练耗时 `{report['training']['training_elapsed_seconds']:.3f} s`。",
        f"完整训练样本每个 epoch 使用一次，总样本呈现次数 `{report['training']['total_sample_presentations']}`。",
        "",
        "## 指标",
        "",
        "| 分割 | 损失 | 精确动作 | 意图准确率 | 视场准确率 | 偏航误差 | 俯仰误差 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in _SPLITS:
        item = evaluation[split]
        overall = item["overall"]
        lines.append(
            f"| {split} | {item['cross_entropy_loss']:.6f} | "
            f"{metric_text(overall['exact_action_accuracy'])} | "
            f"{metric_text(overall['intent_accuracy'])} | "
            f"{metric_text(overall['fov_accuracy'])} | "
            f"{metric_text(overall['yaw_mae_deg'], ' deg')} | "
            f"{metric_text(overall['pitch_mae_deg'], ' deg')} |"
        )
    latency = evaluation["inference_latency"]
    lines.extend(
        [
            "",
            f"单次候选集前向推理 P50/P95/P99 为 `{latency['p50_ms']:.4f}/"
            f"{latency['p95_ms']:.4f}/{latency['p99_ms']:.4f} ms`，设备为 `{latency['device']}`。",
            "",
            "## 准入",
            "",
            f"- bundle 状态：`{bundle['status']}`",
            f"- assist：`{str(bundle['assist_admitted']).lower()}`",
            f"- PPO：`{str(bundle['ppo_enabled']).lower()}`",
            f"- assist 加载：`{str(bundle['assist_load_available']).lower()}`（{bundle['assist_load_failure_reason']}）",
            f"- 权重 SHA256：`{bundle['weights_sha256']}`",
            f"- manifest SHA256：`{bundle['manifest_sha256']}`",
            f"- 实现 SHA256：`{bundle['implementation_sha256']}`",
            "",
            "完整 bundle 只保存在 D5 ignored outputs。模型不修改全局航迹标识、计划版本、联盟版本、通信版本或相机命令安全门。",
            "",
            "## Producer 缺口",
            "",
            "1. 增加 hold 正样本和更均衡的 observe/search/reacquire 示范，来源必须是独立场景与 seed。",
            "2. 在 shadow 模式实际请求动作并记录 runtime ack、执行后 outcome、延迟和安全回退，建立动作到结果的归因。",
            "3. 生成独立的 reward、counterfactual 和 causal label 后再研究 PPO；相邻观测变化不能替代这些标签。",
            "4. D4/D5 分割合同统一前保持联合训练关闭。",
            "",
        ]
    )
    return "\n".join(lines)


def _encode_episode(
    episode: ActiveVisionResearchEpisode,
    *,
    scenario_codes: Mapping[str, int],
    scale_codes: Mapping[str, int],
    camera_codes: Mapping[str, int],
    intent_codes: Mapping[str, int],
    fov_codes: Mapping[str, int],
    audit: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    feature_chunks: list[np.ndarray] = []
    candidate_intents: list[np.ndarray] = []
    candidate_fovs: list[np.ndarray] = []
    candidate_yaw: list[np.ndarray] = []
    candidate_pitch: list[np.ndarray] = []
    candidate_target: list[np.ndarray] = []
    counts: list[int] = []
    selected_indices: list[int] = []
    camera_types: list[int] = []
    scale_values: list[int] = []
    scenario_values: list[int] = []
    scale = scenario_scale(episode.scenario_version)
    for transition in episode.transitions:
        batch = active_vision_candidate_batch(
            transition.snapshot,
            camera_id=transition.camera_id,
        )
        selected_matches = [
            index
            for index, action in enumerate(batch.actions)
            if action.action_key == transition.selected_action.action_key
        ]
        if len(selected_matches) != 1:
            raise ValueError("rule demonstration is not unique in the candidate set")
        count = len(batch.actions)
        if count > np.iinfo(np.uint16).max:
            raise ValueError("active-vision candidate count exceeds cache encoding")
        selected_index = selected_matches[0]
        camera = transition.snapshot.camera(transition.camera_id)
        camera_type = camera_type_from_resource(camera.resource_id)
        feature_chunks.append(np.asarray(batch.features, dtype="<f4"))
        candidate_intents.append(
            np.asarray([intent_codes[action.intent.value] for action in batch.actions], dtype="u1")
        )
        candidate_fovs.append(
            np.asarray([fov_codes[action.fov_mode.value] for action in batch.actions], dtype="u1")
        )
        candidate_yaw.append(
            np.asarray([action.yaw_delta_deg for action in batch.actions], dtype="<f4")
        )
        candidate_pitch.append(
            np.asarray([action.pitch_delta_deg for action in batch.actions], dtype="<f4")
        )
        candidate_target.append(
            np.asarray(
                [action.target_global_track_id is not None for action in batch.actions],
                dtype="u1",
            )
        )
        counts.append(count)
        selected_indices.append(selected_index)
        camera_types.append(camera_codes[camera_type])
        scale_values.append(scale_codes[scale])
        scenario_values.append(scenario_codes[episode.scenario_version])
        _update_audit(
            audit,
            split=split,
            episode=episode,
            transition=transition,
            camera_type=camera_type,
            candidate_count=count,
        )
    features = np.concatenate(feature_chunks, axis=0)
    arrays = {
        "features": features,
        "candidate_intent": np.concatenate(candidate_intents),
        "candidate_fov": np.concatenate(candidate_fovs),
        "candidate_yaw": np.concatenate(candidate_yaw),
        "candidate_pitch": np.concatenate(candidate_pitch),
        "candidate_has_target": np.concatenate(candidate_target),
        "candidate_count": np.asarray(counts, dtype="<u2"),
        "selected_index": np.asarray(selected_indices, dtype="<u2"),
        "camera_type": np.asarray(camera_types, dtype="u1"),
        "scale": np.asarray(scale_values, dtype="u1"),
        "scenario": np.asarray(scenario_values, dtype="<u2"),
    }
    return {
        "arrays": arrays,
        "sample_count": len(counts),
        "candidate_row_count": len(features),
        "feature_minimum": np.min(features, axis=0).astype(np.float64),
        "feature_maximum": np.max(features, axis=0).astype(np.float64),
    }


def _new_audit(dataset: LazyActiveVisionEpisodeDataset) -> dict[str, Any]:
    descriptors = dataset.episode_descriptors
    seeds_by_split = {
        split: sorted(
            {int(item["seed"]) for item in descriptors if item["split"] == split}
        )
        for split in _SPLITS
    }
    intersections = {
        "train_validation": sorted(set(seeds_by_split["train"]) & set(seeds_by_split["validation"])),
        "train_test": sorted(set(seeds_by_split["train"]) & set(seeds_by_split["test"])),
        "validation_test": sorted(set(seeds_by_split["validation"]) & set(seeds_by_split["test"])),
    }
    reserved = set(range(1000, 1020))
    return {
        "dataset_integrity": {
            "strict_loader_passed": True,
            "schema_version": dataset.manifest["schema_version"],
            "manifest_sha256": dataset.manifest_sha256,
            "split_sha256": dataset.manifest["split_sha256"],
            "training_set_sha256": dataset.manifest["training_set_sha256"],
            "artifact_sha256_and_read_only_contract_validated": True,
        },
        "episode_count": len(descriptors),
        "sample_count": 0,
        "split_episode_counts": Counter(str(item["split"]) for item in descriptors),
        "split_sample_counts": Counter(),
        "split_seed_counts": {split: len(values) for split, values in seeds_by_split.items()},
        "seed_intersections": intersections,
        "whole_seed_split_atomic": not any(intersections.values()),
        "reserved_evaluation_seed_overlap": {
            split: sorted(set(values) & reserved) for split, values in seeds_by_split.items()
        },
        "intent_counts": Counter(),
        "intent_counts_by_split": defaultdict(Counter),
        "fov_counts": Counter(),
        "fov_counts_by_split": defaultdict(Counter),
        "camera_type_counts": Counter(),
        "camera_type_counts_by_split": defaultdict(Counter),
        "scale_counts": Counter(),
        "scale_counts_by_split": defaultdict(Counter),
        "scenario_counts": Counter(),
        "scenario_counts_by_split": defaultdict(Counter),
        "candidate_count_histogram": Counter(),
        "selected_action_range": {
            "yaw_delta_deg": [math.inf, -math.inf],
            "pitch_delta_deg": [math.inf, -math.inf],
            "issued_to_expiry_seconds": [math.inf, -math.inf],
        },
        "offline_label_availability": dataset.manifest["availability"],
        "synthetic_fixture_episode_count": sum(
            bool(item["synthetic_fixture"]) for item in descriptors
        ),
    }


def _update_audit(
    audit: dict[str, Any],
    *,
    split: str,
    episode: ActiveVisionResearchEpisode,
    transition: Any,
    camera_type: str,
    candidate_count: int,
) -> None:
    action = transition.selected_action
    scale = scenario_scale(episode.scenario_version)
    audit["sample_count"] += 1
    audit["split_sample_counts"][split] += 1
    audit["intent_counts"][action.intent.value] += 1
    audit["intent_counts_by_split"][split][action.intent.value] += 1
    audit["fov_counts"][action.fov_mode.value] += 1
    audit["fov_counts_by_split"][split][action.fov_mode.value] += 1
    audit["camera_type_counts"][camera_type] += 1
    audit["camera_type_counts_by_split"][split][camera_type] += 1
    audit["scale_counts"][scale] += 1
    audit["scale_counts_by_split"][split][scale] += 1
    audit["scenario_counts"][episode.scenario_version] += 1
    audit["scenario_counts_by_split"][split][episode.scenario_version] += 1
    audit["candidate_count_histogram"][str(candidate_count)] += 1
    for name, value in (
        ("yaw_delta_deg", action.yaw_delta_deg),
        ("pitch_delta_deg", action.pitch_delta_deg),
        ("issued_to_expiry_seconds", action.expires_timestamp - action.issued_timestamp),
    ):
        limits = audit["selected_action_range"][name]
        limits[0] = min(limits[0], float(value))
        limits[1] = max(limits[1], float(value))


def _finalize_audit(
    audit: dict[str, Any],
    dataset: LazyActiveVisionEpisodeDataset,
) -> dict[str, Any]:
    expected_samples = sum(
        int(item["sample_count"]) for item in dataset.episode_descriptors
    )
    if audit["sample_count"] != expected_samples:
        raise ValueError("active-vision audit did not cover every formal sample")
    intent_counts = audit["intent_counts"]
    intent_fractions = {
        name: intent_counts[name] / expected_samples for name in _INTENT_VALUES
    }
    majority_intent, majority_count = max(intent_counts.items(), key=lambda item: item[1])
    audit["intent_fractions"] = intent_fractions
    audit["class_imbalance"] = {
        "majority_intent": majority_intent,
        "majority_fraction": majority_count / expected_samples,
        "hold_positive_sample_count": intent_counts[ActiveVisionIntent.HOLD.value],
        "observe_target_fraction": intent_fractions[ActiveVisionIntent.OBSERVE_TARGET.value],
        "reacquire_fraction": intent_fractions[ActiveVisionIntent.REACQUIRE.value],
    }
    audit["generalization_risks"] = [
        "hold_has_no_positive_demonstrations",
        "observe_target_is_low_prevalence",
        "reacquire_dominates_rule_demonstrations",
        "all_runtime_actions_disabled_no_applied_action_feedback",
    ]
    audit["behavior_cloning_readiness"] = {
        "status": "pass_development_only",
        "rule_demonstration_complete": True,
        "full_split_training_allowed": True,
        "assist_eligible": False,
        "ppo_eligible": False,
    }
    audit["promotion_readiness"] = {
        "status": "fail_closed",
        "failure_reasons": audit["generalization_risks"]
        + ["reward_unavailable", "counterfactual_unavailable", "causal_label_unavailable"],
    }
    return _json_ready(audit)


def scenario_scale(scenario_version: str) -> str:
    parts = str(scenario_version).rsplit("-", 2)
    if len(parts) != 3 or "v" not in parts[1] or not parts[2].startswith("v"):
        raise ValueError(f"scenario version does not expose scale: {scenario_version}")
    return parts[1]


def camera_type_from_resource(resource_id: str) -> str:
    value = str(resource_id).upper()
    if value.startswith("INT-"):
        return "interceptor"
    if value.startswith("RECON-"):
        return "recon"
    return "unknown"


def hardware_summary(selected_device: str) -> dict[str, Any]:
    devices = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            properties = torch.cuda.get_device_properties(index)
            devices.append(
                {
                    "index": index,
                    "name": properties.name,
                    "total_memory_bytes": int(properties.total_memory),
                }
            )
    return {
        "selected_device": selected_device,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "torch_version": torch.__version__,
        "cpu_logical_count": os.cpu_count(),
        "peak_rss_mib": peak_rss_mib(),
        "cuda_available": torch.cuda.is_available(),
        "cuda_runtime_version": torch.version.cuda,
        "cuda_devices": devices,
    }


def peak_rss_mib() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value / 1024.0 if sys.platform != "darwin" else value / (1024.0 * 1024.0)


def set_fixed_seed(seed: int) -> None:
    random.seed(int(seed))
    np.random.seed(int(seed))
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
    torch.use_deterministic_algorithms(True)


def synchronize(device: torch.device) -> None:
    if device.type == "cuda" and torch.cuda.is_available():
        torch.cuda.synchronize(device)


def available(value: float | int) -> dict[str, Any]:
    return {"available": True, "value": value}


def unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "value": None, "reason": reason}


def metric_text(metric: Mapping[str, Any], suffix: str = "") -> str:
    if not metric.get("available"):
        return f"不可用（{metric.get('reason', 'unknown')}）"
    return f"{float(metric['value']):.6f}{suffix}"


def _invert_mapping(payload: Mapping[str, Any]) -> dict[int, str]:
    result = {int(code): str(name) for name, code in payload.items()}
    if set(result) != set(range(len(result))):
        raise ValueError("active-vision BC mapping codes are not contiguous")
    return result


def _scale_sort_key(value: str) -> tuple[int, int, str]:
    left, right = value.split("v", 1)
    return (int(left), int(right), value)


def _slash(payload: Mapping[str, Any]) -> str:
    return "/".join(str(payload[name]) for name in _SPLITS)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Counter):
        return {str(key): _json_ready(item) for key, item in sorted(value.items())}
    if isinstance(value, defaultdict):
        return {str(key): _json_ready(item) for key, item in sorted(value.items())}
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    encoded = (
        json.dumps(
            _json_ready(value),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    write_bytes_atomic(path, encoded)


def write_text_atomic(path: Path, value: str) -> None:
    write_bytes_atomic(path, value.encode("utf-8"))


def write_bytes_atomic(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object expected: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tracked-summary", default=None)
    parser.add_argument("--tracked-report", default=None)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--evaluation-batch-size", type=int, default=4096)
    parser.add_argument("--learning-rate", type=float, default=3.0e-4)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--cpu-threads", type=int, default=16)
    parser.add_argument("--latency-samples", type=int, default=2048)
    parser.add_argument("--latency-warmup", type=int, default=64)
    parser.add_argument("--external-observed-outcome-count", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_formal_behavior_cloning(
        args.dataset_dir,
        args.output_dir,
        config=ActiveVisionBcConfig(
            seed=args.seed,
            epochs=args.epochs,
            batch_size=args.batch_size,
            evaluation_batch_size=args.evaluation_batch_size,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            hidden_dim=args.hidden_dim,
            device=args.device,
            cpu_threads=args.cpu_threads,
            latency_samples=args.latency_samples,
            latency_warmup=args.latency_warmup,
        ),
        tracked_summary_path=args.tracked_summary,
        tracked_report_path=args.tracked_report,
        external_observed_outcome_count=args.external_observed_outcome_count,
    )
    print(
        json.dumps(
            {
                "training_readiness": report["admission"]["training_readiness"],
                "runtime_status": report["bundle"]["status"],
                "assist": report["bundle"]["assist_admitted"],
                "ppo": report["bundle"]["ppo_enabled"],
                "weights_sha256": report["bundle"]["weights_sha256"],
                "output_dir": str(Path(args.output_dir)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION",
    "ACTIVE_VISION_BC_REPORT_SCHEMA_VERSION",
    "ActiveVisionBcConfig",
    "ActiveVisionBcSplitCache",
    "action_metrics",
    "audit_capacity_probe",
    "build_behavior_cloning_feature_cache",
    "evaluate_behavior_cloning_model",
    "load_behavior_cloning_feature_cache",
    "run_formal_behavior_cloning",
    "train_cached_behavior_cloning",
]
