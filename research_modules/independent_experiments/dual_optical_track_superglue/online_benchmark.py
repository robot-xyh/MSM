"""Main-compatible freeze/load/publish entry points for the candidate route."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Mapping

import numpy as np
import torch

try:  # Main normally places independent_experiments on PYTHONPATH.
    from dual_optical_online_benchmark.contracts import (
        AssociationMatch,
        AssociationPublication,
        RevolutionSnapshot,
        read_snapshot,
        snapshot_fingerprint,
    )
except ImportError:  # Direct repository-root imports remain supported.
    from research_modules.independent_experiments.dual_optical_online_benchmark.contracts import (  # type: ignore[no-redef]
        AssociationMatch,
        AssociationPublication,
        RevolutionSnapshot,
        read_snapshot,
        snapshot_fingerprint,
    )

from .adapter import adapt_shared_feature_graph
from .artifacts import (
    canonical_sha256,
    load_weights,
    read_json,
    save_weights,
    sha256_file,
    write_json,
)
from .config import ModelConfig, TrainingConfig
from .matching import NamedMatch, TemporalMatchConfirmer, extract_mutual_matches
from .normalization import FeatureNormalizer
from .schema import AssociationLabels, TrackGraphInput, TrainingExample
from .tensors import graph_tensors
from .training import EnsembleTrainingResult, resolve_device, train_ensemble


ROUTE_NAME = "track_superglue"
ROUTE_VERSION = "dual-optical-track-superglue-online-v1"
FREEZE_SCHEMA_VERSION = "dual-optical-track-superglue-freeze-v1"


def _safe_path(root: Path, relative: object) -> Path:
    path = Path(str(relative))
    if not str(path) or path.is_absolute():
        raise ValueError("calibration artifact path must be nonempty and relative")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("calibration artifact escapes its manifest root") from exc
    return resolved


def _dominant_identity(raw_counts: Mapping[str, Any]) -> tuple[str | None, int]:
    counts = {
        str(identity): int(count)
        for identity, count in raw_counts.items()
        if int(count) > 0
    }
    if not counts:
        return None, 0
    maximum = max(counts.values())
    winners = sorted(identity for identity, count in counts.items() if count == maximum)
    if len(winners) != 1 or winners[0] == "FA" or winners[0].startswith("FA-"):
        return None, 0
    return winners[0], maximum


def _offline_labels(
    path: Path,
    graph: TrackGraphInput,
    *,
    seed: int,
    corruption_level: str,
    revolution_index: int,
) -> AssociationLabels:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("offline_truth_only") is not True:
        raise ValueError("calibration labels must be explicitly marked offline-only")
    expected_metadata = {
        "seed": seed,
        "corruption_level": corruption_level,
        "revolution_index": revolution_index,
    }
    if any(payload.get(name) != expected for name, expected in expected_metadata.items()):
        raise ValueError("offline label metadata does not match its snapshot")
    counts = payload.get("track_truth_counts")
    if not isinstance(counts, Mapping):
        raise ValueError("offline labels are missing track truth counts")
    identities_a = {
        track_id: _dominant_identity(counts.get(track_id, {}))
        for track_id in graph.track_ids_a
    }
    identities_b = {
        track_id: _dominant_identity(counts.get(track_id, {}))
        for track_id in graph.track_ids_b
    }
    candidates: dict[str, list[tuple[int, str, str, int, int]]] = {}
    for row, track_a in enumerate(graph.track_ids_a):
        identity_a, count_a = identities_a[track_a]
        if identity_a is None:
            continue
        for column, track_b in enumerate(graph.track_ids_b):
            if not graph.candidate_mask[row, column]:
                continue
            identity_b, count_b = identities_b[track_b]
            if identity_a == identity_b:
                candidates.setdefault(identity_a, []).append(
                    (-(count_a + count_b), track_a, track_b, row, column)
                )
    matched = []
    for identity in sorted(candidates):
        _, _, _, row, column = min(candidates[identity])
        matched.append((row, column))
    labels = AssociationLabels(tuple(sorted(matched)))
    labels.validate(graph)
    return labels


def _load_calibration_examples(
    calibration_manifest: Path,
) -> tuple[
    tuple[TrainingExample, ...],
    tuple[TrainingExample, ...],
    dict[str, Any],
]:
    manifest = read_json(calibration_manifest)
    if manifest.get("phase") != "calibration":
        raise ValueError("track SuperGlue freeze requires a calibration manifest")
    if manifest.get("test_access_allowed") is not False:
        raise ValueError("calibration manifest must prohibit test access")
    entries = tuple(manifest.get("entries", ()))
    if not entries:
        raise ValueError("calibration manifest contains no entries")
    if any(entry.get("split") not in {"train", "validation"} for entry in entries):
        raise ValueError("freeze input contains a test or unknown split")
    root = calibration_manifest.parent
    train: list[TrainingExample] = []
    validation: list[TrainingExample] = []
    seen = set()
    candidate_fingerprints = set()
    tracker_fingerprints = set()
    for entry in sorted(
        entries,
        key=lambda item: (
            0 if item["split"] == "train" else 1,
            int(item["seed"]),
            str(item["corruption_level"]),
            int(item["revolution_index"]),
        ),
    ):
        key = (
            str(entry["split"]),
            int(entry["seed"]),
            str(entry["corruption_level"]),
            int(entry["revolution_index"]),
        )
        if key in seen:
            raise ValueError("calibration manifest contains duplicate entries")
        seen.add(key)
        snapshot_path = _safe_path(root, entry["snapshot_path"])
        label_path = _safe_path(root, entry["label_path"])
        if sha256_file(snapshot_path) != entry.get("snapshot_sha256"):
            raise ValueError("calibration snapshot hash mismatch")
        if sha256_file(label_path) != entry.get("label_sha256"):
            raise ValueError("calibration label hash mismatch")
        snapshot = read_snapshot(snapshot_path)
        if snapshot_fingerprint(snapshot) != entry.get("input_fingerprint"):
            raise ValueError("calibration snapshot fingerprint mismatch")
        actual = (
            snapshot.split,
            snapshot.seed,
            snapshot.corruption_level,
            snapshot.revolution_index,
        )
        if actual != key:
            raise ValueError("calibration snapshot metadata mismatch")
        graph = adapt_shared_feature_graph(snapshot).replaced(
            input_fingerprint=str(entry["input_fingerprint"])
        )
        labels = _offline_labels(
            label_path,
            graph,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
            revolution_index=snapshot.revolution_index,
        )
        example = TrainingExample(graph, labels)
        example.validate()
        (train if snapshot.split == "train" else validation).append(example)
        candidate_fingerprints.add(graph.candidate_graph_fingerprint)
        tracker_fingerprints.add(str(snapshot.tracker_fingerprint))
    if not train or not validation:
        raise ValueError("calibration requires both train and validation splits")
    metadata = {
        "schema_version": manifest.get("schema_version", "unknown"),
        "protocol": manifest.get("protocol", {}),
        "protocol_fingerprint": manifest.get("protocol_fingerprint", ""),
        "tracker_fingerprint": manifest.get(
            "tracker_fingerprint",
            next(iter(tracker_fingerprints)) if len(tracker_fingerprints) == 1 else "mixed",
        ),
        "train_example_count": len(train),
        "validation_example_count": len(validation),
        "candidate_graph_fingerprint_count": len(candidate_fingerprints),
        "test_snapshot_access_count": 0,
        "test_label_access_count": 0,
    }
    return tuple(train), tuple(validation), metadata


def _save_training_result(
    result: EnsembleTrainingResult,
    output_root: Path,
    calibration_manifest: Path,
    calibration_metadata: Mapping[str, Any],
    training_config: TrainingConfig,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    weights_path = output_root / "track_superglue_weights.pt"
    normalizer_path = output_root / "normalizer.json"
    model_config_path = output_root / "model_config.json"
    training_summary_path = output_root / "training_summary.json"
    model = load_weights_from_state(result.model_config, result.selected_state_dict)
    save_weights(model, weights_path)
    result.normalizer.save(normalizer_path)
    write_json(model_config_path, result.model_config.to_dict())
    selection = result.validation_selection.to_dict()
    training_summary = {
        "schema_version": "track-superglue-training-summary-v1",
        "route_name": ROUTE_NAME,
        "training_config": training_config.to_dict(),
        "selected_validation": selection,
        "initializations": [
            summary.to_dict() for summary in result.initialization_summaries
        ],
        "training_example_count": result.training_example_count,
        "optimized_training_example_count": result.optimized_training_example_count,
        "skipped_empty_training_example_count": (
            result.skipped_empty_training_example_count
        ),
        "empty_training_example_policy": (
            "retain_for_causal_evaluation_but_skip_gradient_optimization"
        ),
        "test_snapshot_access_count": 0,
        "test_label_access_count": 0,
    }
    write_json(training_summary_path, training_summary)
    artifact_hashes = {
        "weights": sha256_file(weights_path),
        "normalizer": sha256_file(normalizer_path),
        "model_config": sha256_file(model_config_path),
        "training_summary": sha256_file(training_summary_path),
    }
    model_fingerprint = canonical_sha256(
        {
            "route_name": ROUTE_NAME,
            "route_version": ROUTE_VERSION,
            "artifacts": artifact_hashes,
            "validation_selection": selection,
        }
    )
    protocol = calibration_metadata.get("protocol", {})
    freeze = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "route_name": ROUTE_NAME,
        "route_version": ROUTE_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "weights": weights_path.name,
        "normalizer": normalizer_path.name,
        "model_config": model_config_path.name,
        "training_summary_path": training_summary_path.name,
        "artifact_sha256": artifact_hashes,
        "model_fingerprint_sha256": model_fingerprint,
        "calibration_manifest_sha256": sha256_file(calibration_manifest),
        "protocol_fingerprint_sha256": calibration_metadata.get(
            "protocol_fingerprint", ""
        ),
        "target_count": protocol.get("target_count"),
        "tracker_fingerprint": calibration_metadata.get("tracker_fingerprint", ""),
        "validation_selection": selection,
        "selected_validation": selection,
        "training_summary": {
            "selected_validation": selection,
            "initialization_count": len(result.initialization_summaries),
            "train_example_count": calibration_metadata["train_example_count"],
            "validation_example_count": calibration_metadata[
                "validation_example_count"
            ],
            "test_snapshot_access_count": 0,
            "test_label_access_count": 0,
        },
        "online_input_policy": {
            "anonymous_tracks_only": True,
            "uses_actor_or_truth_id": False,
            "candidate_edges_cannot_expand": True,
            "temporal_confirmation": "2_of_latest_3_revolutions",
        },
    }
    manifest_path = output_root / "freeze_manifest.json"
    write_json(manifest_path, freeze)
    return manifest_path


def load_weights_from_state(
    config: ModelConfig, state: Mapping[str, torch.Tensor]
) -> torch.nn.Module:
    from .model import TrackSuperGlue

    model = TrackSuperGlue(config)
    model.load_state_dict(state)
    model.eval()
    return model


def freeze_route(calibration_manifest: Path, output_root: Path) -> Path:
    """Train/freeze five initializations without opening any test artifact."""

    manifest_path = Path(calibration_manifest).resolve()
    output_path = Path(output_root).resolve()
    training_examples, validation_examples, metadata = _load_calibration_examples(
        manifest_path
    )
    training_config = TrainingConfig(device="auto")
    result = train_ensemble(
        training_examples,
        validation_examples,
        training_config=training_config,
        model_config=ModelConfig(dropout=training_config.dropout),
    )
    return _save_training_result(
        result, output_path, manifest_path, metadata, training_config
    )


def _validate_freeze_manifest(path: Path) -> tuple[dict[str, Any], Path]:
    freeze = read_json(path)
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION:
        raise ValueError("unsupported track SuperGlue freeze schema")
    if freeze.get("route_name") != ROUTE_NAME:
        raise ValueError("freeze manifest belongs to a different route")
    root = path.parent.resolve()
    artifact_hashes = freeze.get("artifact_sha256", {})
    for key in ("weights", "normalizer", "model_config", "training_summary_path"):
        relative = freeze.get(key)
        artifact = _safe_path(root, relative)
        hash_key = "training_summary" if key == "training_summary_path" else key
        if sha256_file(artifact) != artifact_hashes.get(hash_key):
            raise ValueError(f"frozen artifact hash mismatch: {key}")
    selection = freeze.get("validation_selection")
    required = {
        "macro_f1",
        "correct_assignment_count",
        "selected_assignment_count",
        "validation_failed_closed",
    }
    if not isinstance(selection, Mapping) or not required <= set(selection):
        raise ValueError("freeze manifest lacks a readable validation selection")
    return freeze, root


class FrozenTrackSuperGlueRoute:
    """Online route consuming only anonymous cumulative revolution snapshots."""

    route_name = ROUTE_NAME

    def __init__(self, freeze_manifest: Path, *, device: str = "cpu") -> None:
        self._freeze, root = _validate_freeze_manifest(Path(freeze_manifest).resolve())
        self._device = resolve_device(device)
        config = ModelConfig.from_mapping(read_json(root / self._freeze["model_config"]))
        self._model = load_weights(
            root / self._freeze["weights"], config, device=self._device
        )
        self._normalizer = FeatureNormalizer.load(root / self._freeze["normalizer"])
        self._threshold = float(self._freeze["validation_selection"]["threshold"])
        self._validation_failed_closed = bool(
            self._freeze["validation_selection"]["validation_failed_closed"]
        )
        self._confirmer = TemporalMatchConfirmer()

    @property
    def model_fingerprint(self) -> str:
        return str(self._freeze["model_fingerprint_sha256"])

    def publish(self, snapshot: RevolutionSnapshot) -> AssociationPublication:
        start = time.perf_counter()
        expected_protocol = str(
            self._freeze.get("protocol_fingerprint_sha256", "")
        )
        if expected_protocol and snapshot.protocol_fingerprint != expected_protocol:
            raise ValueError("snapshot protocol does not match the frozen route")
        input_fingerprint = snapshot_fingerprint(snapshot)
        adapter_start = time.perf_counter()
        graph = adapt_shared_feature_graph(snapshot).replaced(
            input_fingerprint=input_fingerprint
        )
        adapter_ms = (time.perf_counter() - adapter_start) * 1000.0
        tensor_start = time.perf_counter()
        tensors = graph_tensors(graph, self._normalizer, self._device)
        tensor_ms = (time.perf_counter() - tensor_start) * 1000.0
        scoring_start = time.perf_counter()
        if self._device.type == "cuda":
            torch.cuda.synchronize(self._device)
        with torch.no_grad():
            output = self._model(*tensors.model_arguments())
        if self._device.type == "cuda":
            torch.cuda.synchronize(self._device)
        scoring_ms = (time.perf_counter() - scoring_start) * 1000.0
        raw = ()
        if not self._validation_failed_closed:
            raw = extract_mutual_matches(
                output.transport.assignment,
                tensors.candidate_mask,
                self._threshold,
            )
        named = tuple(
            NamedMatch(
                graph.track_ids_a[match.index_a],
                graph.track_ids_b[match.index_b],
                match.score,
            )
            for match in raw
        )
        confirmation_start = time.perf_counter()
        confirmed = self._confirmer.update(
            (snapshot.seed, snapshot.corruption_level),
            snapshot.revolution_index,
            named,
        )
        confirmation_ms = (time.perf_counter() - confirmation_start) * 1000.0
        matches = tuple(
            AssociationMatch(
                track_a_id=match.track_a_id,
                track_b_id=match.track_b_id,
                score=match.score,
                decision_state="confirmed",
            )
            for match in confirmed
        )
        rejection_reasons: dict[str, int] = {}
        candidate_count = int(np.sum(graph.candidate_mask))
        if candidate_count == 0:
            rejection_reasons["empty_candidate_graph"] = 1
        elif self._validation_failed_closed:
            rejection_reasons["validation_failed_closed"] = candidate_count
        else:
            rejected = max(0, candidate_count - len(raw))
            if rejected:
                rejection_reasons["dustbin_mutual_best_or_threshold"] = rejected
            if raw and not confirmed:
                rejection_reasons["temporal_confirmation_pending"] = len(raw)
        backend = "gpu" if self._device.type == "cuda" else "cpu"
        if self._validation_failed_closed:
            availability = f"unavailable_validation_failed_closed_{backend}"
        elif candidate_count == 0:
            availability = f"empty_candidate_graph_{backend}"
        elif not matches:
            availability = f"tentative_{backend}"
        else:
            availability = f"available_{backend}"
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        stage_latencies = {
            "snapshot_adapter_ms": adapter_ms,
            "tensor_preparation_ms": tensor_ms,
            "attention_sinkhorn_ms": scoring_ms,
            "mutual_temporal_confirmation_ms": confirmation_ms,
        }
        measured_stages = sum(stage_latencies.values())
        return AssociationPublication(
            route_name=ROUTE_NAME,
            route_version=ROUTE_VERSION,
            model_fingerprint=self.model_fingerprint,
            seed=snapshot.seed,
            corruption_level=snapshot.corruption_level,
            revolution_index=snapshot.revolution_index,
            cutoff_timestamp=snapshot.cutoff_timestamp,
            input_fingerprint=input_fingerprint,
            availability=availability,
            matches=matches,
            rejection_reasons=rejection_reasons,
            candidate_graph_fingerprint=graph.candidate_graph_fingerprint,
            stage_latencies_ms=stage_latencies,
            scoring_ms=tensor_ms + scoring_ms,
            hungarian_ms=0.0,
            end_to_end_ms=max(elapsed_ms, measured_stages),
            deadline_ms=1000.0,
        )


def load_frozen_route(freeze_manifest: Path) -> FrozenTrackSuperGlueRoute:
    """Load a weights-only candidate route; CPU is the deterministic default."""

    return FrozenTrackSuperGlueRoute(Path(freeze_manifest))
