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
from .active_vision_corpus_audit import (
    ActiveVisionCorpusCoveragePolicy,
    active_vision_camera_role,
    audit_active_vision_training_corpus,
    require_active_vision_training_corpus_ready,
    validate_active_vision_corpus_audit,
)
from .canonical_seed_view import (
    canonical_view_binding,
    load_active_vision_canonical_seed_view,
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


ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION = "d5.active-vision-bc-cache.v2"
_LEGACY_ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION = "d5.active-vision-bc-cache.v1"
ACTIVE_VISION_BC_REPORT_SCHEMA_VERSION = "d5.active-vision-bc-formal-report.v2"
ACTIVE_VISION_BC_SUMMARY_SCHEMA_VERSION = "d5.active-vision-bc-tracked-summary.v2"
ACTIVE_VISION_BC_MODEL_DIAGNOSTICS_SCHEMA_VERSION = (
    "d5.active-vision-bc-model-diagnostics.v1"
)
VALIDATION_DATE = "2026-07-27"
VALIDATION_TIMEZONE = "America/Los_Angeles"
_SPLITS = ("train", "validation", "test")
_INTENT_VALUES = tuple(item.value for item in ActiveVisionIntent)
_FOV_VALUES = tuple(item.value for item in ActiveVisionFovMode)
_CAMERA_TYPES = ("interceptor", "recon", "unknown")
_INTENT_WEIGHTING_STRATEGIES = ("none", "inverse_sqrt")
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
    intent_weighting: str = "inverse_sqrt"
    maximum_intent_weight: float = 8.0
    calibration_bin_count: int = 10
    ood_margin: float = 0.05

    def __post_init__(self) -> None:
        for name in (
            "epochs",
            "batch_size",
            "evaluation_batch_size",
            "hidden_dim",
            "cpu_threads",
            "latency_samples",
            "calibration_bin_count",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if int(self.latency_warmup) < 0:
            raise ValueError("latency_warmup must be non-negative")
        if not np.isfinite(self.learning_rate) or self.learning_rate <= 0.0:
            raise ValueError("learning_rate must be positive")
        if not np.isfinite(self.weight_decay) or self.weight_decay < 0.0:
            raise ValueError("weight_decay must be non-negative")
        if self.intent_weighting not in _INTENT_WEIGHTING_STRATEGIES:
            raise ValueError(
                "intent_weighting must be one of "
                f"{', '.join(_INTENT_WEIGHTING_STRATEGIES)}"
            )
        if (
            not np.isfinite(self.maximum_intent_weight)
            or self.maximum_intent_weight < 1.0
        ):
            raise ValueError("maximum_intent_weight must be finite and at least 1")
        if not np.isfinite(self.ood_margin) or not 0.0 <= self.ood_margin <= 1.0:
            raise ValueError("ood_margin must be finite and in [0, 1]")


@dataclass(frozen=True)
class ActiveVisionBcDevelopmentCriteria:
    """Model-only checks that cannot grant runtime or camera authority."""

    minimum_macro_intent_recall: float = 0.50
    minimum_per_intent_recall: float = 0.25
    minimum_camera_role_exact_action_accuracy: float = 0.50
    maximum_expected_calibration_error: float = 0.25
    maximum_out_of_distribution_fraction: float = 0.10

    def __post_init__(self) -> None:
        for name in (
            "minimum_macro_intent_recall",
            "minimum_per_intent_recall",
            "minimum_camera_role_exact_action_accuracy",
            "maximum_expected_calibration_error",
            "maximum_out_of_distribution_fraction",
        ):
            value = float(getattr(self, name))
            if not np.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")


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
    *,
    corpus_policy: ActiveVisionCorpusCoveragePolicy | None = None,
    reserved_evaluation_seeds: Sequence[int] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Stream every split into compact candidate arrays and return the data audit."""

    root = Path(cache_dir)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"active-vision BC cache is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    corpus_audit = audit_active_vision_training_corpus(
        dataset,
        policy=corpus_policy,
        reserved_evaluation_seeds=reserved_evaluation_seeds,
    )
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
    corpus_gate = corpus_audit["training_gate"]
    audit["training_corpus_audit"] = corpus_audit
    audit["behavior_cloning_readiness"] = {
        "status": corpus_gate["status"],
        "rule_demonstration_complete": bool(
            corpus_gate["development_training_allowed"]
        ),
        "full_split_training_allowed": bool(
            corpus_gate["development_training_allowed"]
        ),
        "assist_eligible": False,
        "ppo_eligible": False,
    }
    audit["generalization_risks"] = sorted(
        set(audit["generalization_risks"])
        | set(corpus_gate["failure_reasons"])
        | set(corpus_gate["warnings"])
    )
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
        "training_corpus_audit": corpus_audit,
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
    schema_version = manifest.get("schema_version")
    if schema_version not in {
        ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION,
        _LEGACY_ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION,
    }:
        raise ValueError("active-vision BC cache schema mismatch")
    if schema_version == ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION:
        validate_active_vision_corpus_audit(manifest.get("training_corpus_audit"))
    if tuple(manifest.get("feature_names", ())) != ACTIVE_VISION_FEATURE_NAMES:
        raise ValueError("active-vision BC cache feature order mismatch")
    caches = {
        split: ActiveVisionBcSplitCache.load(root / split, manifest["splits"][split])
        for split in _SPLITS
    }
    return manifest, caches, sha256_file(manifest_path)


def selected_intent_codes(
    cache: ActiveVisionBcSplitCache,
    indices: np.ndarray | None = None,
) -> np.ndarray:
    """Return the demonstrated intent code for each requested sample."""

    sample_indices = (
        np.arange(cache.sample_count, dtype=np.int64)
        if indices is None
        else np.asarray(indices, dtype=np.int64).reshape(-1)
    )
    if np.any(sample_indices < 0) or np.any(sample_indices >= cache.sample_count):
        raise ValueError("active-vision BC sample index is out of range")
    selected = np.asarray(
        cache.files["selected_index"][sample_indices],
        dtype=np.int64,
    )
    counts = np.asarray(
        cache.files["candidate_count"][sample_indices],
        dtype=np.int64,
    )
    if np.any(counts <= 0):
        raise ValueError("active-vision BC samples require at least one candidate")
    if np.any(selected < 0) or np.any(selected >= counts):
        raise ValueError("active-vision BC selected candidate index is out of range")
    selected_rows = cache.offsets[sample_indices] + selected
    if np.any(selected_rows < 0) or np.any(selected_rows >= cache.candidate_row_count):
        raise ValueError("active-vision BC selected candidate row is out of range")
    return np.asarray(
        cache.files["candidate_intent"][selected_rows],
        dtype=np.int64,
    )


def intent_weighting_profile(
    cache: ActiveVisionBcSplitCache,
    *,
    mappings: Mapping[str, Any],
    strategy: str,
    maximum_weight: float,
) -> dict[str, Any]:
    """Build bounded sample weights without fabricating absent actions."""

    if strategy not in _INTENT_WEIGHTING_STRATEGIES:
        raise ValueError("unsupported active-vision intent weighting strategy")
    if not np.isfinite(maximum_weight) or maximum_weight < 1.0:
        raise ValueError("maximum_weight must be finite and at least 1")
    if cache.sample_count <= 0:
        raise ValueError("active-vision BC weighting requires training samples")
    intent_mapping = _invert_mapping(mappings["intent"])
    codes = selected_intent_codes(cache)
    if np.any(codes < 0) or np.any(codes >= len(intent_mapping)):
        raise ValueError("active-vision BC selected intent code is out of range")
    counts = np.bincount(codes, minlength=len(intent_mapping)).astype(np.int64)
    weights = np.ones(len(intent_mapping), dtype=np.float64)
    supported = counts > 0
    if strategy == "inverse_sqrt":
        raw = np.ones(len(intent_mapping), dtype=np.float64)
        raw[supported] = np.sqrt(cache.sample_count / counts[supported])
        raw[supported] = np.minimum(raw[supported], maximum_weight)
        normalizer = float(np.sum(raw[supported] * counts[supported])) / float(
            cache.sample_count
        )
        weights[supported] = raw[supported] / normalizer
    # No training sample consumes these entries.  A held-out sample from an
    # unseen action receives the maximum validation penalty instead of being
    # silently ignored.
    weights[~supported] = maximum_weight
    training_sample_weight_mean = float(np.mean(weights[codes]))
    if (
        not np.all(np.isfinite(weights))
        or np.any(weights <= 0.0)
        or not math.isclose(training_sample_weight_mean, 1.0, abs_tol=1.0e-12)
    ):
        raise RuntimeError("active-vision intent weights are not normalized")
    count_by_intent = {
        intent_mapping[code]: int(counts[code])
        for code in range(len(intent_mapping))
    }
    weight_by_intent = {
        intent_mapping[code]: (
            available(float(weights[code]))
            if supported[code]
            else unavailable("no_positive_samples")
        )
        for code in range(len(intent_mapping))
    }
    return {
        "strategy": strategy,
        "normalization": "mean_training_sample_weight_equals_one",
        "training_sample_weight_mean": training_sample_weight_mean,
        "maximum_weight": float(maximum_weight),
        "sample_count": cache.sample_count,
        "count_by_intent": count_by_intent,
        "fraction_by_intent": {
            name: count / cache.sample_count
            for name, count in count_by_intent.items()
        },
        "weight_by_intent": weight_by_intent,
        "weight_by_code": weights.tolist(),
        "supported_by_code": supported.tolist(),
        "unseen_validation_intent_weight": float(maximum_weight),
        "unavailable_intents": [
            intent_mapping[code]
            for code in range(len(intent_mapping))
            if not supported[code]
        ],
        "zero_padding_or_synthetic_positive_used": False,
    }


def train_cached_behavior_cloning(
    cache_manifest: Mapping[str, Any],
    caches: Mapping[str, ActiveVisionBcSplitCache],
    *,
    config: ActiveVisionBcConfig,
) -> tuple[ActiveVisionActorCritic, ActiveVisionFeatureBounds, dict[str, Any]]:
    """Train on every cached train sample using padded candidate batches."""

    corpus_audit = require_active_vision_training_corpus_ready(cache_manifest)
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
    intent_weighting = intent_weighting_profile(
        train_cache,
        mappings=cache_manifest["mappings"],
        strategy=config.intent_weighting,
        maximum_weight=config.maximum_intent_weight,
    )
    intent_weight_lookup = np.asarray(
        intent_weighting["weight_by_code"],
        dtype=np.float32,
    )
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
        weighted_loss_sum = 0.0
        sample_weight_sum = 0.0
        for start in range(0, train_cache.sample_count, config.batch_size):
            indices = order[start : start + config.batch_size]
            features, mask, selected = padded_batch(train_cache, indices)
            feature_tensor = torch.as_tensor(features, device=device)
            mask_tensor = torch.as_tensor(mask, device=device)
            selected_tensor = torch.as_tensor(selected.astype(np.int64), device=device)
            logits = actor_logits(model, feature_tensor)
            logits = logits.masked_fill(~mask_tensor, torch.finfo(logits.dtype).min)
            sample_intent_codes = selected_intent_codes(train_cache, indices)
            sample_weights = torch.as_tensor(
                intent_weight_lookup[sample_intent_codes],
                device=device,
            )
            per_sample_loss = F.cross_entropy(
                logits,
                selected_tensor,
                reduction="none",
            )
            loss = torch.sum(per_sample_loss * sample_weights) / torch.sum(
                sample_weights
            )
            if not bool(torch.isfinite(loss)):
                raise RuntimeError("non-finite active-vision BC loss")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            weighted_loss_sum += float(
                torch.sum(per_sample_loss.detach() * sample_weights).cpu()
            )
            sample_weight_sum += float(torch.sum(sample_weights).cpu())
        train_loss = weighted_loss_sum / sample_weight_sum
        validation_loss = evaluate_loss(
            model,
            validation_cache,
            batch_size=config.evaluation_batch_size,
            device=device,
            intent_weight_lookup=intent_weight_lookup,
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
        "training_corpus_audit_sha256": corpus_audit["content_sha256"],
        "config": asdict(config),
        "intent_weighting": intent_weighting,
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
            calibration_bin_count=config.calibration_bin_count,
            ood_margin=config.ood_margin,
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
    calibration_bin_count: int = 10,
    ood_margin: float = 0.05,
) -> dict[str, Any]:
    if cache.sample_count <= 0:
        raise ValueError("active-vision BC evaluation split is empty")
    if batch_size <= 0:
        raise ValueError("active-vision BC evaluation batch size must be positive")
    if not np.isfinite(ood_margin) or not 0.0 <= ood_margin <= 1.0:
        raise ValueError("active-vision OOD margin must be finite and in [0, 1]")
    model.eval()
    predictions = np.empty(cache.sample_count, dtype=np.int64)
    confidences = np.empty(cache.sample_count, dtype=np.float64)
    out_of_distribution = np.empty(cache.sample_count, dtype=bool)
    bounds_payload = cache_manifest["training_feature_bounds"]
    lower = np.asarray(bounds_payload["minimum"], dtype=np.float64)
    upper = np.asarray(bounds_payload["maximum"], dtype=np.float64)
    expected_shape = (cache.feature_dim,)
    if (
        lower.shape != expected_shape
        or upper.shape != expected_shape
        or not np.all(np.isfinite(lower))
        or not np.all(np.isfinite(upper))
        or np.any(lower > upper)
    ):
        raise ValueError("active-vision training feature bounds are invalid")
    span = np.maximum(upper - lower, 1.0e-6)
    expanded_lower = lower - ood_margin * span
    expanded_upper = upper + ood_margin * span
    loss_sum = 0.0
    with torch.no_grad():
        for start in range(0, cache.sample_count, batch_size):
            indices = np.arange(start, min(start + batch_size, cache.sample_count))
            features, mask, selected = padded_batch(cache, indices)
            valid_features = features[mask]
            if not np.all(np.isfinite(valid_features)):
                raise ValueError("active-vision BC evaluation features are non-finite")
            logits = actor_logits(model, torch.as_tensor(features, device=device))
            logits = logits.masked_fill(
                ~torch.as_tensor(mask, device=device),
                torch.finfo(logits.dtype).min,
            )
            selected_tensor = torch.as_tensor(selected.astype(np.int64), device=device)
            loss = F.cross_entropy(logits, selected_tensor, reduction="sum")
            loss_sum += float(loss.cpu())
            probabilities = torch.softmax(logits, dim=1)
            confidence, prediction = torch.max(probabilities, dim=1)
            predictions[start : start + len(indices)] = prediction.cpu().numpy()
            confidences[start : start + len(indices)] = confidence.cpu().numpy()
            outside = np.logical_or(
                features < expanded_lower.reshape(1, 1, -1),
                features > expanded_upper.reshape(1, 1, -1),
            )
            outside &= mask[:, :, None]
            out_of_distribution[start : start + len(indices)] = np.any(
                outside,
                axis=(1, 2),
            )
    return action_metrics(
        cache,
        predictions,
        mappings=cache_manifest["mappings"],
        loss=loss_sum / cache.sample_count,
        confidences=confidences,
        out_of_distribution=out_of_distribution,
        calibration_bin_count=calibration_bin_count,
        ood_margin=ood_margin,
    )


def action_metrics(
    cache: ActiveVisionBcSplitCache,
    predictions: np.ndarray,
    *,
    mappings: Mapping[str, Any],
    loss: float,
    confidences: np.ndarray | None = None,
    out_of_distribution: np.ndarray | None = None,
    calibration_bin_count: int = 10,
    ood_margin: float = 0.05,
) -> dict[str, Any]:
    prediction_values = np.asarray(predictions)
    if prediction_values.shape != (cache.sample_count,):
        raise ValueError("prediction count does not match BC cache")
    if not np.issubdtype(prediction_values.dtype, np.integer):
        raise ValueError("active-vision candidate predictions must be integer indices")
    prediction_values = prediction_values.astype(np.int64, copy=False)
    if not np.isfinite(loss) or loss < 0.0:
        raise ValueError("active-vision cross-entropy loss must be finite and non-negative")
    if confidences is not None and np.asarray(confidences).shape != (
        cache.sample_count,
    ):
        raise ValueError("confidence count does not match BC cache")
    if out_of_distribution is not None and np.asarray(
        out_of_distribution
    ).shape != (cache.sample_count,):
        raise ValueError("OOD count does not match BC cache")
    true_indices = np.asarray(cache.files["selected_index"], dtype=np.int64)
    candidate_counts = np.asarray(cache.files["candidate_count"], dtype=np.int64)
    if np.any(candidate_counts <= 0):
        raise ValueError("active-vision BC samples require at least one candidate")
    if np.any(true_indices < 0) or np.any(true_indices >= candidate_counts):
        raise ValueError("active-vision BC selected candidate index is out of range")
    if np.any(prediction_values < 0) or np.any(
        prediction_values >= candidate_counts
    ):
        raise ValueError("active-vision predicted candidate index is out of range")
    true_rows = cache.offsets[:-1] + true_indices
    predicted_rows = cache.offsets[:-1] + prediction_values
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
    exact = prediction_values == true_indices
    intent_equal = predicted_intent == true_intent
    fov_equal = predicted_fov == true_fov
    target_equal = predicted_target == true_target
    yaw_error = np.abs(predicted_yaw - true_yaw)
    pitch_error = np.abs(predicted_pitch - true_pitch)
    intent_mapping = _invert_mapping(mappings["intent"])
    camera_mapping = _invert_mapping(mappings["camera_type"])
    scale_mapping = _invert_mapping(mappings["scale"])
    _validate_codes(true_intent, intent_mapping, "true intent")
    _validate_codes(predicted_intent, intent_mapping, "predicted intent")
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
    _validate_codes(camera_codes, camera_mapping, "camera type")
    _validate_codes(scale_codes, scale_mapping, "scenario scale")
    per_camera = {
        camera_name: {
            **subset_action_metrics(
                camera_codes == code,
                exact=exact,
                intent_equal=intent_equal,
                fov_equal=fov_equal,
                target_equal=target_equal,
                yaw_error=yaw_error,
                pitch_error=pitch_error,
            ),
            "intent_classification": intent_classification_metrics(
                true_intent[camera_codes == code],
                predicted_intent[camera_codes == code],
                intent_mapping,
            ),
            "calibration": exact_action_calibration(
                exact[camera_codes == code],
                (
                    None
                    if confidences is None
                    else np.asarray(confidences)[camera_codes == code]
                ),
                bin_count=calibration_bin_count,
            ),
            "out_of_distribution": out_of_distribution_metrics(
                exact[camera_codes == code],
                (
                    None
                    if out_of_distribution is None
                    else np.asarray(out_of_distribution)[camera_codes == code]
                ),
                margin=ood_margin,
            ),
        }
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
        "action_distribution": action_distribution_metrics(
            true_intent,
            predicted_intent,
            intent_mapping,
        ),
        "calibration": exact_action_calibration(
            exact,
            confidences,
            bin_count=calibration_bin_count,
        ),
        "out_of_distribution": out_of_distribution_metrics(
            exact,
            out_of_distribution,
            margin=ood_margin,
        ),
        "diagnostic_fallback_reason_counts": diagnostic_fallback_reason_counts(
            exact=exact,
            confidences=confidences,
            out_of_distribution=out_of_distribution,
        ),
        "per_intent": per_intent,
        "per_camera_type": per_camera,
        "per_scale": per_scale,
    }


def intent_classification_metrics(
    truth: np.ndarray,
    predicted: np.ndarray,
    mapping: Mapping[int, str],
) -> dict[str, Any]:
    truth_values = np.asarray(truth)
    predicted_values = np.asarray(predicted)
    if truth_values.ndim != 1 or predicted_values.shape != truth_values.shape:
        raise ValueError("intent truth and predictions must be aligned vectors")
    if not np.issubdtype(truth_values.dtype, np.integer) or not np.issubdtype(
        predicted_values.dtype,
        np.integer,
    ):
        raise ValueError("intent truth and predictions must use integer codes")
    truth_values = truth_values.astype(np.int64, copy=False)
    predicted_values = predicted_values.astype(np.int64, copy=False)
    size = len(mapping)
    if set(mapping) != set(range(size)):
        raise ValueError("intent metric mapping codes are not contiguous")
    _validate_codes(truth_values, mapping, "intent truth")
    _validate_codes(predicted_values, mapping, "intent prediction")
    confusion = np.zeros((size, size), dtype=np.int64)
    np.add.at(confusion, (truth_values, predicted_values), 1)
    per_class: dict[str, Any] = {}
    precision_values: list[float] = []
    recall_values: list[float] = []
    f1_values: list[float] = []
    precision_unavailable_classes: list[str] = []
    recall_unavailable_classes: list[str] = []
    f1_unavailable_classes: list[str] = []
    for code, name in mapping.items():
        support = int(confusion[code, :].sum())
        predicted_count = int(confusion[:, code].sum())
        true_positive = int(confusion[code, code])
        false_positive = predicted_count - true_positive
        false_negative = support - true_positive
        f1_denominator = 2 * true_positive + false_positive + false_negative
        if predicted_count:
            precision = true_positive / predicted_count
            precision_metric = available(precision)
            precision_values.append(precision)
        else:
            precision_unavailable_classes.append(name)
            precision_metric = unavailable("no_predicted_samples")
        if support:
            recall = true_positive / support
            recall_metric = available(recall)
            recall_values.append(recall)
        else:
            recall_unavailable_classes.append(name)
            recall_metric = unavailable("no_positive_samples")
        if f1_denominator:
            f1 = 2.0 * true_positive / f1_denominator
            f1_metric = available(f1)
            f1_values.append(f1)
        else:
            f1_unavailable_classes.append(name)
            f1_metric = unavailable("no_positive_or_predicted_samples")
        per_class[name] = {
            "support": support,
            "predicted_count": predicted_count,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision_denominator": predicted_count,
            "recall_denominator": support,
            "f1_denominator": f1_denominator,
            "precision": precision_metric,
            "recall": recall_metric,
            "f1": f1_metric,
        }
    return {
        "sample_count": int(len(truth_values)),
        "accuracy": (
            available(float(np.mean(truth_values == predicted_values)))
            if len(truth_values)
            else unavailable("no_samples")
        ),
        "supported_class_count": len(recall_values),
        "truth_supported_class_count": len(recall_values),
        "predicted_class_count": len(precision_values),
        "observed_class_count": len(f1_values),
        "unavailable_classes": recall_unavailable_classes,
        "precision_unavailable_classes": precision_unavailable_classes,
        "recall_unavailable_classes": recall_unavailable_classes,
        "f1_unavailable_classes": f1_unavailable_classes,
        "macro_precision_supported_classes": (
            available(float(np.mean(precision_values)))
            if precision_values
            else unavailable("no_predicted_samples")
        ),
        "macro_precision_denominator": "classes_with_predictions",
        "macro_recall_supported_classes": (
            available(float(np.mean(recall_values)))
            if recall_values
            else unavailable("no_positive_samples")
        ),
        "macro_recall_denominator": "classes_with_truth_support",
        "macro_f1_supported_classes": (
            available(float(np.mean(f1_values)))
            if f1_values
            else unavailable("no_positive_or_predicted_samples")
        ),
        "macro_f1_denominator": "classes_with_truth_or_predictions",
        "class_order": [mapping[index] for index in range(size)],
        "confusion_matrix": confusion.tolist(),
        "per_class": per_class,
    }


def action_distribution_metrics(
    truth: np.ndarray,
    predicted: np.ndarray,
    mapping: Mapping[int, str],
) -> dict[str, Any]:
    truth_values = np.asarray(truth)
    predicted_values = np.asarray(predicted)
    if truth_values.ndim != 1 or predicted_values.shape != truth_values.shape:
        raise ValueError("action distributions require aligned vectors")
    if not np.issubdtype(truth_values.dtype, np.integer) or not np.issubdtype(
        predicted_values.dtype,
        np.integer,
    ):
        raise ValueError("action distributions require integer codes")
    truth_values = truth_values.astype(np.int64, copy=False)
    predicted_values = predicted_values.astype(np.int64, copy=False)
    _validate_codes(truth_values, mapping, "action distribution truth")
    _validate_codes(predicted_values, mapping, "action distribution prediction")
    sample_count = int(len(truth_values))
    truth_counts = {
        mapping[code]: int(np.sum(truth_values == code))
        for code in range(len(mapping))
    }
    predicted_counts = {
        mapping[code]: int(np.sum(predicted_values == code))
        for code in range(len(mapping))
    }
    if sample_count:
        majority_count = max(truth_counts.values())
        majority_names = sorted(
            name for name, count in truth_counts.items() if count == majority_count
        )
        majority_baseline = available(majority_count / sample_count)
    else:
        majority_names = []
        majority_baseline = unavailable("no_samples")
    return {
        "sample_count": sample_count,
        "truth_counts": truth_counts,
        "predicted_counts": predicted_counts,
        "truth_fractions": {
            name: count / sample_count if sample_count else None
            for name, count in truth_counts.items()
        },
        "predicted_fractions": {
            name: count / sample_count if sample_count else None
            for name, count in predicted_counts.items()
        },
        "majority_truth_actions": majority_names,
        "majority_only_exact_accuracy": majority_baseline,
        "zero_positive_actions": sorted(
            name for name, count in truth_counts.items() if count == 0
        ),
    }


def exact_action_calibration(
    exact: np.ndarray,
    confidences: np.ndarray | None,
    *,
    bin_count: int,
) -> dict[str, Any]:
    if bin_count <= 0:
        raise ValueError("calibration bin_count must be positive")
    exact_values = np.asarray(exact)
    if exact_values.ndim != 1:
        raise ValueError("exact-action outcomes must be a vector")
    if exact_values.dtype != np.bool_:
        if not np.issubdtype(exact_values.dtype, np.integer) or np.any(
            (exact_values != 0) & (exact_values != 1)
        ):
            raise ValueError("exact-action outcomes must be boolean")
    exact_values = exact_values.astype(bool, copy=False)
    count = int(len(exact_values))
    if confidences is None:
        return {
            "sample_count": count,
            "status": "unavailable",
            "reason": "confidence_not_recorded",
            "expected_calibration_error": unavailable("confidence_not_recorded"),
            "maximum_calibration_error": unavailable("confidence_not_recorded"),
            "mean_confidence": unavailable("confidence_not_recorded"),
            "binary_brier_score": unavailable("confidence_not_recorded"),
            "bins": [],
        }
    values = np.asarray(confidences, dtype=np.float64)
    if values.shape != (count,) or not np.all(np.isfinite(values)):
        raise ValueError("exact-action confidences must be finite and aligned")
    if np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("exact-action confidences must be in [0, 1]")
    if not count:
        return {
            "sample_count": 0,
            "status": "unavailable",
            "reason": "no_samples",
            "expected_calibration_error": unavailable("no_samples"),
            "maximum_calibration_error": unavailable("no_samples"),
            "mean_confidence": unavailable("no_samples"),
            "binary_brier_score": unavailable("no_samples"),
            "bins": [],
        }
    correctness = exact_values.astype(np.float64)
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    bin_indices = np.minimum(
        np.searchsorted(edges, values, side="right") - 1,
        bin_count - 1,
    )
    bins: list[dict[str, Any]] = []
    weighted_gap = 0.0
    maximum_gap = 0.0
    for index in range(bin_count):
        selector = bin_indices == index
        selected_count = int(np.sum(selector))
        if not selected_count:
            continue
        accuracy = float(np.mean(correctness[selector]))
        confidence = float(np.mean(values[selector]))
        gap = abs(accuracy - confidence)
        weighted_gap += selected_count * gap
        maximum_gap = max(maximum_gap, gap)
        bins.append(
            {
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "sample_count": selected_count,
                "accuracy": accuracy,
                "mean_confidence": confidence,
                "absolute_gap": gap,
            }
        )
    return {
        "sample_count": count,
        "status": "available",
        "reason": None,
        "expected_calibration_error": available(weighted_gap / count),
        "maximum_calibration_error": available(maximum_gap),
        "mean_confidence": available(float(np.mean(values))),
        "binary_brier_score": available(
            float(np.mean(np.square(values - correctness)))
        ),
        "bins": bins,
    }


def out_of_distribution_metrics(
    exact: np.ndarray,
    out_of_distribution: np.ndarray | None,
    *,
    margin: float,
) -> dict[str, Any]:
    if not np.isfinite(margin) or not 0.0 <= margin <= 1.0:
        raise ValueError("OOD margin must be finite and in [0, 1]")
    exact_values = np.asarray(exact)
    if exact_values.ndim != 1:
        raise ValueError("exact-action outcomes must be a vector")
    if exact_values.dtype != np.bool_:
        if not np.issubdtype(exact_values.dtype, np.integer) or np.any(
            (exact_values != 0) & (exact_values != 1)
        ):
            raise ValueError("exact-action outcomes must be boolean")
    exact_values = exact_values.astype(bool, copy=False)
    count = int(len(exact_values))
    if out_of_distribution is None:
        return {
            "sample_count": count,
            "status": "unavailable",
            "reason": "feature_bounds_not_evaluated",
            "margin": float(margin),
            "out_of_distribution_count": None,
            "out_of_distribution_fraction": unavailable(
                "feature_bounds_not_evaluated"
            ),
            "in_distribution_exact_action_accuracy": unavailable(
                "feature_bounds_not_evaluated"
            ),
            "out_of_distribution_exact_action_accuracy": unavailable(
                "feature_bounds_not_evaluated"
            ),
        }
    flags = np.asarray(out_of_distribution, dtype=bool)
    if flags.shape != (count,):
        raise ValueError("OOD flags must align with exact-action outcomes")
    ood_count = int(np.sum(flags))
    in_distribution = ~flags
    return {
        "sample_count": count,
        "status": "available" if count else "unavailable",
        "reason": None if count else "no_samples",
        "margin": float(margin),
        "out_of_distribution_count": ood_count,
        "out_of_distribution_fraction": (
            available(ood_count / count) if count else unavailable("no_samples")
        ),
        "in_distribution_exact_action_accuracy": (
            available(float(np.mean(exact_values[in_distribution])))
            if np.any(in_distribution)
            else unavailable("no_in_distribution_samples")
        ),
        "out_of_distribution_exact_action_accuracy": (
            available(float(np.mean(exact_values[flags])))
            if np.any(flags)
            else unavailable("no_out_of_distribution_samples")
        ),
    }


def diagnostic_fallback_reason_counts(
    *,
    exact: np.ndarray,
    confidences: np.ndarray | None,
    out_of_distribution: np.ndarray | None,
    low_confidence_threshold: float = 0.50,
) -> dict[str, int]:
    reasons = {
        "model_action_mismatch": int(np.sum(~exact)),
        "low_confidence": 0,
        "feature_out_of_distribution": 0,
    }
    if confidences is not None:
        reasons["low_confidence"] = int(
            np.sum(np.asarray(confidences) < low_confidence_threshold)
        )
    if out_of_distribution is not None:
        reasons["feature_out_of_distribution"] = int(
            np.sum(np.asarray(out_of_distribution, dtype=bool))
        )
    return reasons


def assess_behavior_cloning_development_readiness(
    data_audit: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    *,
    criteria: ActiveVisionBcDevelopmentCriteria | None = None,
) -> dict[str, Any]:
    """Fail closed before paired-shadow evaluation or bundle promotion."""

    cfg = criteria or ActiveVisionBcDevelopmentCriteria()
    test = evaluation["test"]
    classification = test["intent_classification"]
    reasons: list[str] = []
    warnings: list[str] = []
    unavailable_actions: list[str] = []
    training_support: dict[str, dict[str, Any]] = {}
    corpus_audit = data_audit.get("training_corpus_audit")
    if not isinstance(corpus_audit, Mapping):
        reasons.append("training_corpus_audit_unavailable")
        corpus_gate: Mapping[str, Any] | None = None
    else:
        try:
            validate_active_vision_corpus_audit(corpus_audit)
        except ValueError:
            reasons.append("training_corpus_audit_invalid")
            corpus_gate = None
        else:
            corpus_gate = corpus_audit["training_gate"]
            if corpus_gate["development_training_allowed"] is not True:
                reasons.extend(
                    f"training_corpus:{item}"
                    for item in corpus_gate["failure_reasons"]
                )
    split_counts = data_audit.get("intent_counts_by_split")
    train_counts = (
        split_counts.get("train")
        if isinstance(split_counts, Mapping)
        else None
    )
    if not isinstance(train_counts, Mapping):
        reasons.append("training_intent_support_unavailable")
        training_support = {
            action: unavailable("training_split_counts_not_recorded")
            for action in _INTENT_VALUES
        }
    else:
        for action in _INTENT_VALUES:
            raw_count = train_counts.get(action, 0)
            if (
                isinstance(raw_count, bool)
                or not isinstance(raw_count, (int, np.integer))
                or int(raw_count) < 0
            ):
                reasons.append(f"training_action_support_invalid:{action}")
                training_support[action] = unavailable(
                    "invalid_training_positive_sample_count"
                )
                continue
            count = int(raw_count)
            training_support[action] = available(count)
            if count == 0:
                reasons.append(f"training_action_unavailable:{action}")
    for action in _INTENT_VALUES:
        recall = classification["per_class"][action]["recall"]
        if not recall["available"]:
            unavailable_actions.append(action)
            reasons.append(f"action_recall_unavailable:{action}")
        elif float(recall["value"]) < cfg.minimum_per_intent_recall:
            reasons.append(f"action_recall_below_threshold:{action}")
    macro_recall = classification["macro_recall_supported_classes"]
    if not macro_recall["available"]:
        reasons.append("macro_intent_recall_unavailable")
    elif float(macro_recall["value"]) < cfg.minimum_macro_intent_recall:
        reasons.append("macro_intent_recall_below_threshold")
    for camera_role in ("interceptor", "recon"):
        role_metrics = test["per_camera_type"].get(camera_role)
        if not role_metrics or int(role_metrics["sample_count"]) == 0:
            reasons.append(f"camera_role_metrics_unavailable:{camera_role}")
            continue
        accuracy = role_metrics["exact_action_accuracy"]
        if not accuracy["available"]:
            reasons.append(
                f"camera_role_exact_action_accuracy_unavailable:{camera_role}"
            )
        elif (
            float(accuracy["value"])
            < cfg.minimum_camera_role_exact_action_accuracy
        ):
            reasons.append(
                f"camera_role_exact_action_accuracy_below_threshold:{camera_role}"
            )
    calibration = test["calibration"]["expected_calibration_error"]
    if not calibration["available"]:
        reasons.append("exact_action_calibration_unavailable")
    elif float(calibration["value"]) > cfg.maximum_expected_calibration_error:
        reasons.append("expected_calibration_error_above_threshold")
    ood_fraction = test["out_of_distribution"]["out_of_distribution_fraction"]
    if not ood_fraction["available"]:
        reasons.append("out_of_distribution_diagnostic_unavailable")
    elif (
        float(ood_fraction["value"])
        > cfg.maximum_out_of_distribution_fraction
    ):
        reasons.append("out_of_distribution_fraction_above_threshold")
    majority_fraction_raw = data_audit.get("class_imbalance", {}).get(
        "majority_fraction"
    )
    if (
        isinstance(majority_fraction_raw, bool)
        or not isinstance(majority_fraction_raw, (int, float, np.number))
        or not np.isfinite(float(majority_fraction_raw))
        or not 0.0 <= float(majority_fraction_raw) <= 1.0
    ):
        majority_fraction: float | None = None
        reasons.append("majority_action_fraction_unavailable")
    else:
        majority_fraction = float(majority_fraction_raw)
    if majority_fraction is not None and majority_fraction >= 0.80:
        warnings.append("majority_action_fraction_at_least_0_80")
    if unavailable_actions:
        warnings.append("missing_positive_actions_must_not_be_zero_padded")
    unique_reasons = list(dict.fromkeys(reasons))
    precheck_passed = not unique_reasons
    return {
        "schema_version": ACTIVE_VISION_BC_MODEL_DIAGNOSTICS_SCHEMA_VERSION,
        "status": (
            "development_model_precheck_passed_shadow_only"
            if precheck_passed
            else "fail_closed_model_precheck"
        ),
        "development_model_precheck_passed": precheck_passed,
        "may_enter_formal_paired_shadow": precheck_passed,
        "assist_admitted": False,
        "active_vision_authority_granted": False,
        "assignment_authority_granted": False,
        "control_authority_granted": False,
        "rule_fallback_required": True,
        "criteria": asdict(cfg),
        "failure_reasons": unique_reasons,
        "warnings": warnings,
        "unavailable_actions": unavailable_actions,
        "training_intent_support": training_support,
        "training_corpus_gate": (
            unavailable("strict_training_corpus_audit_unavailable")
            if corpus_gate is None
            else {
                "available": True,
                "value": bool(corpus_gate["development_training_allowed"]),
                "reason": None,
                "status": corpus_gate["status"],
                "failure_reasons": list(corpus_gate["failure_reasons"]),
            }
        ),
        "majority_action_fraction": majority_fraction,
        "test_macro_intent_recall": macro_recall,
        "test_per_action_recall": {
            action: classification["per_class"][action]["recall"]
            for action in _INTENT_VALUES
        },
        "test_camera_role_exact_action_accuracy": {
            role: test["per_camera_type"][role]["exact_action_accuracy"]
            for role in ("interceptor", "recon")
            if role in test["per_camera_type"]
        },
        "test_calibration": test["calibration"],
        "test_out_of_distribution": test["out_of_distribution"],
        "diagnostic_fallback_reason_counts": test[
            "diagnostic_fallback_reason_counts"
        ],
        "hold_positive_fabrication_used": False,
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
    if not len(sample_indices):
        raise ValueError("active-vision BC batch cannot be empty")
    if np.any(sample_indices < 0) or np.any(sample_indices >= cache.sample_count):
        raise ValueError("active-vision BC sample index is out of range")
    counts = np.asarray(cache.files["candidate_count"][sample_indices], dtype=np.int64)
    selected = np.asarray(cache.files["selected_index"][sample_indices], dtype=np.int64)
    if np.any(counts <= 0):
        raise ValueError("active-vision BC samples require at least one candidate")
    if np.any(selected < 0) or np.any(selected >= counts):
        raise ValueError("active-vision BC selected candidate index is out of range")
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
    intent_weight_lookup: np.ndarray | None = None,
) -> float:
    if cache.sample_count <= 0:
        raise ValueError("active-vision validation split is empty")
    if batch_size <= 0:
        raise ValueError("active-vision validation batch size must be positive")
    weight_lookup: np.ndarray | None = None
    if intent_weight_lookup is not None:
        weight_lookup = np.asarray(intent_weight_lookup, dtype=np.float64)
        if (
            weight_lookup.ndim != 1
            or not len(weight_lookup)
            or not np.all(np.isfinite(weight_lookup))
            or np.any(weight_lookup <= 0.0)
        ):
            raise ValueError(
                "active-vision validation intent weights must be finite and positive"
            )
    model.eval()
    weighted_total = 0.0
    weight_total = 0.0
    with torch.no_grad():
        for start in range(0, cache.sample_count, batch_size):
            indices = np.arange(start, min(start + batch_size, cache.sample_count))
            features, mask, selected = padded_batch(cache, indices)
            logits = actor_logits(model, torch.as_tensor(features, device=device))
            logits = logits.masked_fill(
                ~torch.as_tensor(mask, device=device),
                torch.finfo(logits.dtype).min,
            )
            per_sample_loss = F.cross_entropy(
                logits,
                torch.as_tensor(selected.astype(np.int64), device=device),
                reduction="none",
            )
            if weight_lookup is None:
                sample_weights = torch.ones(
                    len(indices),
                    dtype=per_sample_loss.dtype,
                    device=device,
                )
            else:
                sample_intents = selected_intent_codes(cache, indices)
                if np.any(sample_intents < 0) or np.any(
                    sample_intents >= len(weight_lookup)
                ):
                    raise ValueError(
                        "active-vision validation intent code is out of range"
                    )
                sample_weights = torch.as_tensor(
                    weight_lookup[sample_intents],
                    dtype=per_sample_loss.dtype,
                    device=device,
                )
            weighted_total += float(
                torch.sum(per_sample_loss * sample_weights).cpu()
            )
            weight_total += float(torch.sum(sample_weights).cpu())
    if weight_total <= 0.0:
        raise RuntimeError("active-vision validation weights have zero mass")
    return weighted_total / weight_total


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
    canonical_view_manifest_path: str | Path | None = None,
    training_seed_registry_path: str | Path | None = None,
    shared_seed_registry_path: str | Path | None = None,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"active-vision BC output directory is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    pipeline_started = time.perf_counter()
    audit_started = time.perf_counter()
    dataset = _load_behavior_cloning_dataset(
        dataset_dir,
        canonical_view_manifest_path=canonical_view_manifest_path,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )
    integrity_elapsed = time.perf_counter() - audit_started
    capacity = audit_capacity_probe(dataset)
    cache_manifest, data_audit, cache_manifest_sha256 = build_behavior_cloning_feature_cache(
        dataset,
        output_root / "feature_cache",
    )
    corpus_audit_path = output_root / "training_corpus_audit.json"
    write_json_atomic(
        corpus_audit_path,
        cache_manifest["training_corpus_audit"],
    )
    corpus_audit_sha256 = sha256_file(corpus_audit_path)
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
    model_diagnostics = assess_behavior_cloning_development_readiness(
        data_audit,
        evaluation,
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
        "training_corpus_audit_sha256": corpus_audit_sha256,
        "feature_cache_manifest_sha256": cache_manifest_sha256,
        "full_train_split_used": True,
        "ppo_enabled": False,
        "observed_outcome_used_as_reward": False,
    }
    canonical_view = canonical_view_binding(dataset)
    if canonical_view is not None:
        training_config["canonical_seed_view"] = canonical_view
    bundle_dir = output_root / "development_shadow_model_bundle"
    validation_results = {
        "validation": evaluation["validation"],
        "test": evaluation["test"],
        "inference_latency": evaluation["inference_latency"],
        "model_diagnostics": model_diagnostics,
        "promotion_status": "fail_closed_shadow_only",
        "statistical_limits": (
            data_audit["generalization_risks"]
            + model_diagnostics["failure_reasons"]
        ),
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
    canonical_split_aligned = canonical_view is not None
    external_evidence = {
        "d6_observed_outcome_count": external_observed_outcome_count,
        "observed_outcome_scope": "adjacent_observation_without_applied_action_attribution",
        "observed_outcome_used_as_reward": False,
        "d4_d5_joint_training": (
            "split_aligned_data_view_only_no_joint_model_admission"
            if canonical_split_aligned
            else "disabled_split_mismatch"
        ),
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
            "canonical_seed_view": canonical_view,
            "training_corpus_audit_sha256": corpus_audit_sha256,
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
        "model_diagnostics": model_diagnostics,
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
            "active_vision_authority_granted": False,
            "assignment_authority_granted": False,
            "control_authority_granted": False,
            "ppo": False,
            "promotion": "fail_closed",
            "rule_fallback_required": True,
            "failure_reasons": data_audit["generalization_risks"]
            + model_diagnostics["failure_reasons"]
            + [
                "no_applied_action_outcomes",
                "no_reward_or_counterfactual_labels",
                "no_formal_paired_shadow_non_degradation_evidence",
                (
                    "joint_model_contract_not_admitted_after_split_alignment"
                    if canonical_split_aligned
                    else "d4_d5_split_mismatch_disables_joint_training"
                ),
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
        "model_diagnostics": report["model_diagnostics"],
        "hardware": report["hardware"],
        "bundle": report["bundle"],
        "external_evidence": report["external_evidence"],
        "admission": report["admission"],
        "pipeline_elapsed_seconds": report["pipeline_elapsed_seconds"],
    }


def report_markdown(report: Mapping[str, Any]) -> str:
    audit = report["data_audit"]
    corpus = audit["training_corpus_audit"]
    corpus_inventory = corpus["training_inventory"]
    corpus_gate = corpus["training_gate"]
    evaluation = report["evaluation"]
    diagnostics = report["model_diagnostics"]
    bundle = report["bundle"]
    lines = [
        "# D5 主动视觉行为克隆正式数据审计",
        "",
        f"验证日期：{report['validation_date']}（{report['validation_timezone']}）",
        "",
        "## 结论",
        "",
        f"正式数据共 `{audit['sample_count']}` 个样本，完整训练集 `{audit['split_sample_counts']['train']}` 个样本已用于行为克隆。",
        f"训练语料结构门为 `{corpus_gate['status']}`。该门只证明训练 split 的动作、相机角色、episode 和 seed 基础覆盖，不构成正式模型准入。",
        "模型仅为 development shadow-only，不具备 assist 权限，未启动 PPO，规则策略仍是强制回退。",
        "观测 outcome 没有动作执行归因，reward、counterfactual 和 causal label 均不可用，不能用于强化学习或晋级。",
        "",
        "## 数据覆盖",
        "",
        f"- episode：`{audit['episode_count']}`",
        f"- train/validation/test episode：`{_slash(audit['split_episode_counts'])}`",
        f"- train/validation/test sample：`{_slash(audit['split_sample_counts'])}`",
        f"- 唯一 seed：`{_slash(audit['split_seed_counts'])}`，分割交集为 0",
        f"- 训练与验证/测试 seed 重叠：`{len(corpus['split_integrity']['training_evaluation_seed_overlap'])}`",
        f"- 训练与显式保留 seed 重叠：`{len(corpus['split_integrity']['training_reserved_seed_overlap'])}`",
        f"- 训练结构有效样本：`{corpus_inventory['eligible_sample_count_by_split']['train']}`",
        f"- 训练 episode：合成 `{corpus_inventory['synthetic_training_episode_count']}`，非合成 `{corpus_inventory['non_synthetic_training_episode_count']}`",
        f"- 意图：`{json.dumps(audit['intent_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- 动作签名：`{json.dumps(audit['selected_action_signature_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- 视场模式：`{json.dumps(audit['fov_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- 相机类型：`{json.dumps(audit['camera_type_counts'], ensure_ascii=False, sort_keys=True)}`",
        "",
        f"- 补采请求：`{len(corpus['collection_plan']['requests'])}`",
        "",
        "逆平方根权重只调整已有样本的损失贡献。语料门按唯一 episode、seed、动作和相机角色计数，复制、过采样和重加权均不能补足覆盖。",
        "",
        "## 训练",
        "",
        f"固定 seed `{report['training']['config']['seed']}`，训练 `{report['training']['config']['epochs']}` 个 epoch，",
        f"最佳 epoch `{report['training']['best_epoch']}`。训练耗时 `{report['training']['training_elapsed_seconds']:.3f} s`。",
        f"完整训练样本每个 epoch 使用一次，总样本呈现次数 `{report['training']['total_sample_presentations']}`。",
        f"损失加权：`{report['training']['intent_weighting']['strategy']}`；缺失动作："
        f"`{json.dumps(report['training']['intent_weighting']['unavailable_intents'], ensure_ascii=False)}`。"
        "缺失动作权重保持不可用，没有补零或伪造正样本。",
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
    test_classification = evaluation["test"]["intent_classification"]
    test_calibration = evaluation["test"]["calibration"]
    test_ood = evaluation["test"]["out_of_distribution"]
    lines.extend(
        [
            "",
            "### 动作分层",
            "",
            f"- test 宏平均召回：`{metric_text(test_classification['macro_recall_supported_classes'])}`",
            f"- test 宏平均 F1：`{metric_text(test_classification['macro_f1_supported_classes'])}`",
            f"- test 每动作召回：`{json.dumps(diagnostics['test_per_action_recall'], ensure_ascii=False, sort_keys=True)}`",
            f"- test 相机角色精确动作：`{json.dumps(diagnostics['test_camera_role_exact_action_accuracy'], ensure_ascii=False, sort_keys=True)}`",
            f"- test 期望校准误差：`{metric_text(test_calibration['expected_calibration_error'])}`",
            f"- test 分布外比例：`{metric_text(test_ood['out_of_distribution_fraction'])}`",
            f"- 诊断回退原因计数：`{json.dumps(diagnostics['diagnostic_fallback_reason_counts'], ensure_ascii=False, sort_keys=True)}`",
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
            f"- 模型前置检查：`{diagnostics['status']}`",
            f"- 前置检查失败原因：`{json.dumps(diagnostics['failure_reasons'], ensure_ascii=False)}`",
            f"- 权重 SHA256：`{bundle['weights_sha256']}`",
            f"- manifest SHA256：`{bundle['manifest_sha256']}`",
            f"- 实现 SHA256：`{bundle['implementation_sha256']}`",
            "",
            "完整 bundle 只保存在 D5 ignored outputs。模型不修改全局航迹标识、计划版本、联盟版本、通信版本或相机命令安全门。",
            "",
            "## Producer 缺口",
            "",
            "1. 按语料审计生成的请求清单补充独立 episode 和新训练 seed；合成课程只作软件验证，不能替代非合成正式语料。",
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
        "selected_action_signature_counts": Counter(),
        "selected_action_signature_counts_by_split": defaultdict(Counter),
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
    action_signature = "|".join(
        (
            action.intent.value,
            action.fov_mode.value,
            (
                "target_reference"
                if action.target_global_track_id is not None
                else "no_target_reference"
            ),
        )
    )
    audit["selected_action_signature_counts"][action_signature] += 1
    audit["selected_action_signature_counts_by_split"][split][
        action_signature
    ] += 1
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
    majority_intent, majority_count = max(
        (
            (name, int(intent_counts[name]))
            for name in _INTENT_VALUES
        ),
        key=lambda item: item[1],
    )
    audit["intent_fractions"] = intent_fractions
    audit["class_imbalance"] = {
        "majority_intent": majority_intent,
        "majority_fraction": majority_count / expected_samples,
        "hold_positive_sample_count": intent_counts[ActiveVisionIntent.HOLD.value],
        "observe_target_fraction": intent_fractions[ActiveVisionIntent.OBSERVE_TARGET.value],
        "reacquire_fraction": intent_fractions[ActiveVisionIntent.REACQUIRE.value],
    }
    risks: list[str] = []
    if intent_counts[ActiveVisionIntent.HOLD.value] == 0:
        risks.append("hold_has_no_positive_demonstrations")
    if intent_fractions[ActiveVisionIntent.OBSERVE_TARGET.value] < 0.05:
        risks.append("observe_target_is_low_prevalence")
    if intent_fractions[ActiveVisionIntent.REACQUIRE.value] >= 0.80:
        risks.append("reacquire_dominates_rule_demonstrations")
    risks.append("all_runtime_actions_disabled_no_applied_action_feedback")
    audit["generalization_risks"] = risks
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
    return active_vision_camera_role(resource_id)


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


def _validate_codes(
    values: np.ndarray,
    mapping: Mapping[int, str],
    label: str,
) -> None:
    if values.ndim != 1:
        raise ValueError(f"{label} codes must be a vector")
    if len(values) and (
        np.any(values < 0) or np.any(values >= len(mapping))
    ):
        raise ValueError(f"{label} code is out of range")


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
    parser.add_argument(
        "--intent-weighting",
        choices=_INTENT_WEIGHTING_STRATEGIES,
        default="inverse_sqrt",
    )
    parser.add_argument("--maximum-intent-weight", type=float, default=8.0)
    parser.add_argument("--calibration-bin-count", type=int, default=10)
    parser.add_argument("--ood-margin", type=float, default=0.05)
    parser.add_argument("--external-observed-outcome-count", type=int, default=None)
    parser.add_argument("--canonical-view-manifest")
    parser.add_argument("--training-seed-registry")
    parser.add_argument("--shared-seed-registry")
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
            intent_weighting=args.intent_weighting,
            maximum_intent_weight=args.maximum_intent_weight,
            calibration_bin_count=args.calibration_bin_count,
            ood_margin=args.ood_margin,
        ),
        tracked_summary_path=args.tracked_summary,
        tracked_report_path=args.tracked_report,
        external_observed_outcome_count=args.external_observed_outcome_count,
        canonical_view_manifest_path=args.canonical_view_manifest,
        training_seed_registry_path=args.training_seed_registry,
        shared_seed_registry_path=args.shared_seed_registry,
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


def _load_behavior_cloning_dataset(
    dataset_dir: str | Path,
    *,
    canonical_view_manifest_path: str | Path | None,
    training_seed_registry_path: str | Path | None,
    shared_seed_registry_path: str | Path | None,
) -> LazyActiveVisionEpisodeDataset:
    canonical_values = (
        canonical_view_manifest_path,
        training_seed_registry_path,
        shared_seed_registry_path,
    )
    if not any(value is not None for value in canonical_values):
        return load_active_vision_episode_dataset_lazy(dataset_dir)
    if not all(value is not None for value in canonical_values):
        raise ValueError(
            "canonical active-vision view requires view manifest, training registry, and shared registry"
        )
    return load_active_vision_canonical_seed_view(
        dataset_dir,
        view_manifest_path=canonical_view_manifest_path,
        training_seed_registry_path=training_seed_registry_path,
        shared_seed_registry_path=shared_seed_registry_path,
    )


if __name__ == "__main__":  # pragma: no cover - exercised through the CLI.
    raise SystemExit(main())


__all__ = [
    "ACTIVE_VISION_BC_CACHE_SCHEMA_VERSION",
    "ACTIVE_VISION_BC_MODEL_DIAGNOSTICS_SCHEMA_VERSION",
    "ACTIVE_VISION_BC_REPORT_SCHEMA_VERSION",
    "ActiveVisionBcConfig",
    "ActiveVisionBcDevelopmentCriteria",
    "ActiveVisionBcSplitCache",
    "action_metrics",
    "assess_behavior_cloning_development_readiness",
    "audit_capacity_probe",
    "build_behavior_cloning_feature_cache",
    "exact_action_calibration",
    "evaluate_behavior_cloning_model",
    "intent_weighting_profile",
    "load_behavior_cloning_feature_cache",
    "out_of_distribution_metrics",
    "run_formal_behavior_cloning",
    "selected_intent_codes",
    "train_cached_behavior_cloning",
]
