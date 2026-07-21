"""Truth-isolated offline label audit and sidecar construction.

The module consumes the frozen scalable-3D learning export without importing
or mutating any online D1-D7 runtime.  It separates an observed state
transition from action attribution: an adjacent D4/D5 observation may be a
valid outcome, while a PPO reward still requires explicit application
evidence.  Missing counterfactual or causal evidence is never encoded as zero.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence


READINESS_SCHEMA_VERSION = "d6.learning-label-readiness.v1"
BUNDLE_SCHEMA_VERSION = "d6.learning-label-sidecar-bundle.v1"
LAYER_SCHEMA_VERSION = "d6.learning-label-layer.v1"
D4_LABEL_SCHEMA_VERSION = "d6.d4-region-offline-label.v1"
D5_LABEL_SCHEMA_VERSION = "d6.d5-active-vision-offline-label.v1"
D4_OUTCOME_SCHEMA_VERSION = "d6.d4-region-observed-transition.v1"
D5_OUTCOME_SCHEMA_VERSION = "d6.d5-active-vision-observed-transition.v1"

_LEARNING_EXPORT_SCHEMA = "scalable3d-learning-export-v2"
_GENERATION_PLAN_SCHEMA = "scalable3d-learning-generation-plan-v1"
_GENERATION_CHECKPOINT_SCHEMA = "scalable3d-learning-generation-checkpoint-v2"
_TRAINING_SEED_REGISTRY_SCHEMA = "scalable3d-training-seed-registry-v1"
_D4_DATASET_SCHEMA = "d4-region-learning-dataset-v1"
_D4_EPISODE_SCHEMA = "d4-region-learning-episode-v1"
_D4_FRAME_SCHEMA = "d4-region-learning-frame-v1"
_D4_SOURCE_SCHEMA = "d4-region-learning-source-v1"
_D5_DATASET_SCHEMA = "d5.active-vision-episode-dataset.v3"
_D5_DESCRIPTOR_SCHEMA = "d5.active-vision-episode-descriptor.v2"
_D5_RECORD_SCHEMA = "d5.active-vision-episode-record.v2"
_D5_SOURCE_IDENTITY_SCHEMA = "d5.active-vision-source-identity.v1"
_D5_SAMPLE_SCHEMA = "d5.active-vision-sample.v2"
_D5_ACTION_SCHEMA = "d5.active-vision-action.v1"
_D5_SNAPSHOT_SCHEMA = "d5.active-vision-snapshot.v1"
_D5_FEEDBACK_SCHEMA = "d5.active-vision-camera-feedback.v1"
_D5_ACK_SCHEMA = "d5.active-vision-runtime-ack.v1"
_D5_OFFLINE_LABELS_SCHEMA = "d5.active-vision-offline-labels.v1"
_D5_OFFLINE_LABEL_SCHEMA = "d5.active-vision-offline-label.v1"

_HEX64 = frozenset("0123456789abcdef")
_D5_MODES = frozenset({"disabled", "shadow", "assist"})
_D5_TARGET_INTENTS = frozenset({"observe_target", "reacquire"})
_D5_INTENTS = frozenset({"observe_target", "search_sector", "hold", "reacquire"})
_FROZEN_RESERVED_EVALUATION_SEEDS = tuple(range(1000, 1020))
_D5_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "actor_id",
        "ground_truth",
        "object_id",
        "offline_truth_global_id",
        "offline_truth_id",
        "simulator_id",
        "target_actor_id",
        "truth_global_track_id",
        "truth_id",
        "truth_position",
        "truth_state",
        "truth_target_id",
        "truth_track_id",
    }
)


class LearningLabelBackfillError(RuntimeError):
    """Stable fail-closed error raised by the D6 backfill boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class LearningLabelBackfillConfig:
    """Frozen labeling policy for one deterministic D6 run."""

    audit_date: str = "2026-07-20"
    d4_transition_window_s: float = 2.0
    d5_transition_window_s: float = 0.5
    reserved_evaluation_seeds: tuple[int, ...] = _FROZEN_RESERVED_EVALUATION_SEEDS
    verify_all_source_hashes: bool = True

    def __post_init__(self) -> None:
        if not str(self.audit_date).strip():
            raise ValueError("audit_date must not be empty")
        for name in ("d4_transition_window_s", "d5_transition_window_s"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        seeds = tuple(int(item) for item in self.reserved_evaluation_seeds)
        if len(seeds) != len(set(seeds)) or any(seed < 0 for seed in seeds):
            raise ValueError("reserved evaluation seeds must be unique and non-negative")
        if seeds != _FROZEN_RESERVED_EVALUATION_SEEDS:
            raise ValueError("reserved evaluation seeds are frozen to 1000-1019")
        object.__setattr__(self, "reserved_evaluation_seeds", seeds)


@dataclass(frozen=True)
class _SourceContext:
    dataset_root: Path
    generation_root: Path
    episode_index: Mapping[str, Mapping[str, Any]]
    training_seeds: frozenset[int]
    reserved_seeds: frozenset[int]
    git_commit: str
    source_hashes: Mapping[str, str]


@dataclass
class _D4Stats:
    episode_count: int = 0
    frame_count: int = 0
    outcome_available_count: int = 0
    reward_available_count: int = 0
    counterfactual_available_count: int = 0
    causal_label_available_count: int = 0
    target_available_count: int = 0
    recommendation_available_count: int = 0
    dirty_episode_count: int = 0
    action_count: int = 0
    nonzero_quota_action_count: int = 0
    hold_action_count: int = 0
    replan_action_count: int = 0
    transfer_count: int = 0
    outcome_unavailable_reasons: Counter[str] | None = None
    reward_unavailable_reasons: Counter[str] | None = None
    episode_splits: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.outcome_unavailable_reasons = Counter()
        self.reward_unavailable_reasons = Counter()
        self.episode_splits = {}


@dataclass
class _D5Stats:
    episode_count: int = 0
    sample_count: int = 0
    outcome_available_count: int = 0
    reward_available_count: int = 0
    reward_positive_count: int = 0
    reward_negative_count: int = 0
    counterfactual_available_count: int = 0
    causal_label_available_count: int = 0
    runtime_ack_count: int = 0
    accepted_ack_count: int = 0
    requested_action_count: int = 0
    rule_demonstration_count: int = 0
    dirty_episode_count: int = 0
    synthetic_episode_count: int = 0
    modes: Counter[str] | None = None
    intents: Counter[str] | None = None
    outcome_unavailable_reasons: Counter[str] | None = None
    reward_unavailable_reasons: Counter[str] | None = None
    split_alignment_count: int = 0
    split_mismatch_count: int = 0
    split_mismatch_seeds: set[int] | None = None
    split_mismatch_pairs: Counter[str] | None = None

    def __post_init__(self) -> None:
        self.modes = Counter()
        self.intents = Counter()
        self.outcome_unavailable_reasons = Counter()
        self.reward_unavailable_reasons = Counter()
        self.split_mismatch_seeds = set()
        self.split_mismatch_pairs = Counter()


def audit_learning_label_readiness(
    learning_dataset_dir: str | Path,
    *,
    config: LearningLabelBackfillConfig | None = None,
) -> dict[str, Any]:
    """Audit a frozen learning export and report label/training readiness.

    This function is read-only.  It validates every source artifact hash when
    ``verify_all_source_hashes`` is enabled, but never modifies source labels.
    """

    resolved = config or LearningLabelBackfillConfig()
    context = _audit_source_context(Path(learning_dataset_dir), resolved)
    d4 = _audit_d4(context, resolved, sink_root=None)
    d5 = _audit_d5(
        context,
        resolved,
        sink_root=None,
        expected_episode_splits=d4.episode_splits or {},
    )
    return _readiness_payload(context, resolved, d4, d5)


def write_learning_label_sidecars(
    learning_dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    config: LearningLabelBackfillConfig | None = None,
) -> dict[str, Any]:
    """Atomically write detached D4/D5 label sidecars and their manifest.

    An existing valid bundle for the same source is returned unchanged.  A
    conflicting or invalid destination fails closed; source artifacts are
    never edited or copied into the output bundle.
    """

    resolved = config or LearningLabelBackfillConfig()
    if not resolved.verify_all_source_hashes:
        raise LearningLabelBackfillError(
            "source_hash_verification_required",
            "detached sidecars require verification of every registered source hash",
        )
    source = Path(learning_dataset_dir).resolve()
    output = Path(output_dir).resolve()
    if output == source or _is_relative_to(output, source):
        raise LearningLabelBackfillError(
            "output_inside_source",
            "sidecar output must be outside the immutable learning dataset",
        )
    if output.exists():
        manifest = audit_learning_label_sidecar_bundle(output)
        current_readiness = audit_learning_label_readiness(source, config=resolved)
        if manifest.get("source") != current_readiness["source"]:
            raise LearningLabelBackfillError(
                "existing_bundle_source_mismatch",
                "existing sidecar bundle belongs to a different learning export",
            )
        if manifest.get("labeling_policy") != _labeling_policy(resolved):
            raise LearningLabelBackfillError(
                "existing_bundle_policy_mismatch",
                "existing sidecar bundle uses a different labeling policy",
            )
        return manifest

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        context = _audit_source_context(source, resolved)
        d4 = _audit_d4(context, resolved, sink_root=staging)
        d5 = _audit_d5(
            context,
            resolved,
            sink_root=staging,
            expected_episode_splits=d4.episode_splits or {},
        )
        readiness = _readiness_payload(context, resolved, d4, d5)
        _write_json_atomic(staging / "readiness.json", readiness)

        artifact_entries = _artifact_entries(staging, exclude={"manifest.json", "SHA256SUMS"})
        manifest_content = {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "audit_date": resolved.audit_date,
            "source": readiness["source"],
            "truth_isolation": readiness["truth_isolation"],
            "labeling_policy": readiness["labeling_policy"],
            "readiness_sha256": _sha256_file(staging / "readiness.json"),
            "artifacts": artifact_entries,
            "determinism": {
                "canonical_json": True,
                "gzip_mtime": 0,
                "atomic_directory_publish": True,
                "source_mutation_allowed": False,
            },
        }
        manifest = {
            **manifest_content,
            "content_sha256": _sha256_bytes(_canonical_json_bytes(manifest_content)),
        }
        _write_json_atomic(staging / "manifest.json", manifest)
        checksum_entries = _artifact_entries(staging, exclude={"SHA256SUMS"})
        checksum_text = "".join(
            f"{item['sha256']}  {item['relative_path']}\n" for item in checksum_entries
        )
        _write_bytes_atomic(staging / "SHA256SUMS", checksum_text.encode("ascii"))
        os.replace(staging, output)
        return audit_learning_label_sidecar_bundle(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def write_learning_label_readiness(
    learning_dataset_dir: str | Path,
    output_json: str | Path,
    *,
    config: LearningLabelBackfillConfig | None = None,
) -> dict[str, Any]:
    """Write a compact deterministic audit without materializing sidecars."""

    payload = audit_learning_label_readiness(learning_dataset_dir, config=config)
    _write_json_atomic(Path(output_json), payload)
    return payload


def audit_learning_label_sidecar_bundle(output_dir: str | Path) -> dict[str, Any]:
    """Validate a previously written bundle and return its manifest."""

    root = Path(output_dir).resolve()
    manifest_path = root / "manifest.json"
    checksums_path = root / "SHA256SUMS"
    if not manifest_path.is_file() or not checksums_path.is_file():
        raise LearningLabelBackfillError(
            "bundle_incomplete", "sidecar bundle requires manifest.json and SHA256SUMS"
        )
    manifest = _read_json_object(manifest_path)
    if manifest.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise LearningLabelBackfillError("bundle_schema_mismatch", "unsupported sidecar bundle")
    unsigned = dict(manifest)
    claimed = _require_sha256(unsigned.pop("content_sha256", None), "content_sha256")
    if _sha256_bytes(_canonical_json_bytes(unsigned)) != claimed:
        raise LearningLabelBackfillError(
            "bundle_manifest_hash_mismatch", "sidecar manifest content hash mismatch"
        )
    checksums = _read_checksum_file(checksums_path)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != checksums_path
    }
    if set(checksums) != actual:
        raise LearningLabelBackfillError(
            "bundle_artifact_set_mismatch", "SHA256SUMS does not cover the exact bundle"
        )
    for relative, expected in checksums.items():
        path = _safe_relative_path(root, relative)
        if _sha256_file(path) != expected:
            raise LearningLabelBackfillError(
                "bundle_artifact_hash_mismatch", f"sidecar artifact changed: {relative}"
            )
    readiness_path = root / "readiness.json"
    if manifest.get("readiness_sha256") != _sha256_file(readiness_path):
        raise LearningLabelBackfillError(
            "bundle_readiness_hash_mismatch", "manifest readiness hash mismatch"
        )
    expected_artifacts = _artifact_entries(
        root, exclude={"manifest.json", "SHA256SUMS"}
    )
    if manifest.get("artifacts") != expected_artifacts:
        raise LearningLabelBackfillError(
            "bundle_manifest_artifacts_mismatch",
            "manifest artifact inventory does not match the bundle",
        )
    return manifest


def _audit_source_context(
    dataset_root: Path,
    config: LearningLabelBackfillConfig,
) -> _SourceContext:
    root = dataset_root.resolve()
    generation_root = root.parent
    required = {
        "batch_learning_export_summary": root / "batch_learning_export_summary.json",
        "episode_index": root / "episodes.jsonl",
        "generation_plan": generation_root / "generation_plan.json",
        "generation_summary": generation_root / "generation_summary.json",
        "generation_checkpoint": generation_root / "generation_checkpoint.json",
        "training_seed_registry": generation_root / "training_seed_registry.json",
    }
    for name, path in required.items():
        if not path.is_file():
            raise LearningLabelBackfillError(
                "source_artifact_missing", f"required source artifact is missing: {name}"
            )
    source_hashes = {name: _sha256_file(path) for name, path in required.items()}
    summary = _read_json_object(required["batch_learning_export_summary"])
    plan = _read_json_object(required["generation_plan"])
    generation_summary = _read_json_object(required["generation_summary"])
    checkpoint = _read_json_object(required["generation_checkpoint"])
    registry = _read_json_object(required["training_seed_registry"])

    _expect_equal(summary.get("schema_version"), _LEARNING_EXPORT_SCHEMA, "export schema")
    _expect_equal(plan.get("schema_version"), _GENERATION_PLAN_SCHEMA, "generation plan schema")
    _expect_equal(
        generation_summary.get("schema_version"),
        _GENERATION_PLAN_SCHEMA,
        "generation summary schema",
    )
    _expect_equal(
        checkpoint.get("schema_version"),
        _GENERATION_CHECKPOINT_SCHEMA,
        "generation checkpoint schema",
    )
    _expect_equal(
        registry.get("schema_version"),
        _TRAINING_SEED_REGISTRY_SCHEMA,
        "training seed registry schema",
    )
    if checkpoint.get("state") != "finalized":
        raise LearningLabelBackfillError(
            "generation_not_finalized", "only a finalized learning generation may be labeled"
        )
    plan_hash = _sha256_file(required["generation_plan"])
    if checkpoint.get("plan_sha256") != plan_hash:
        raise LearningLabelBackfillError("generation_plan_hash_mismatch", "checkpoint plan hash mismatch")
    if checkpoint.get("generation_summary_sha256") != source_hashes["generation_summary"]:
        raise LearningLabelBackfillError(
            "generation_summary_hash_mismatch", "checkpoint generation summary hash mismatch"
        )
    if generation_summary.get("training_seed_registry_sha256") != source_hashes[
        "training_seed_registry"
    ]:
        raise LearningLabelBackfillError(
            "training_registry_hash_mismatch", "generation summary registry hash mismatch"
        )
    if plan.get("formal") is not True or plan.get("repository_dirty") is not False:
        raise LearningLabelBackfillError(
            "generation_not_formal", "formal labeling requires a clean formal generation plan"
        )
    if generation_summary.get("formal") is not True or generation_summary.get(
        "repository_dirty"
    ) is not False:
        raise LearningLabelBackfillError(
            "generation_summary_not_formal", "generation summary is not clean formal evidence"
        )
    if checkpoint.get("repository_dirty") is not False:
        raise LearningLabelBackfillError(
            "generation_checkpoint_not_clean", "generation checkpoint is not clean evidence"
        )
    git_commit = str(plan.get("git_commit", ""))
    if not git_commit or generation_summary.get("git_commit") != git_commit:
        raise LearningLabelBackfillError(
            "source_git_commit_mismatch", "generation plan and summary Git identities differ"
        )
    if checkpoint.get("git_commit") != git_commit:
        raise LearningLabelBackfillError(
            "source_git_commit_mismatch", "generation checkpoint Git identity differs"
        )
    if generation_summary.get("learning_export_summary") != summary:
        raise LearningLabelBackfillError(
            "generation_export_summary_mismatch",
            "generation summary does not embed the frozen learning export summary",
        )

    training_seeds = _integer_set(registry.get("training_seeds"), "training_seeds")
    reserved_seeds = _integer_set(
        registry.get("reserved_evaluation_seeds"), "reserved_evaluation_seeds"
    )
    expected_reserved = frozenset(config.reserved_evaluation_seeds)
    if reserved_seeds != expected_reserved:
        raise LearningLabelBackfillError(
            "reserved_seed_registry_mismatch",
            "training registry does not match the frozen reserved evaluation seeds",
        )
    if training_seeds & reserved_seeds or int(registry.get("overlap_count", -1)) != 0:
        raise LearningLabelBackfillError(
            "reserved_seed_leakage", "training and reserved evaluation seeds overlap"
        )
    if frozenset(_integer_sequence(plan.get("reserved_evaluation_seeds"), "plan reserved seeds")) != reserved_seeds:
        raise LearningLabelBackfillError(
            "plan_reserved_seed_mismatch", "generation plan reserved seed list differs"
        )

    episode_rows = tuple(_read_jsonl(required["episode_index"]))
    expected_count = int(summary.get("episode_count", -1))
    if expected_count <= 0 or len(episode_rows) != expected_count:
        raise LearningLabelBackfillError(
            "episode_index_count_mismatch", "episode index count does not match export summary"
        )
    episode_index: dict[str, Mapping[str, Any]] = {}
    for row in episode_rows:
        episode_id = _required_text(row, "episode_id")
        if episode_id in episode_index:
            raise LearningLabelBackfillError("duplicate_episode_id", f"duplicate episode: {episode_id}")
        seed = _required_nonnegative_int(row, "seed")
        if seed not in training_seeds:
            reason = "reserved_seed_leakage" if seed in reserved_seeds else "unregistered_training_seed"
            raise LearningLabelBackfillError(reason, f"episode uses a non-training seed: {seed}")
        _require_sha256(row.get("config_sha256"), "episode config_sha256")
        episode_index[episode_id] = dict(row)
    if int(checkpoint.get("completed_episode_count", -1)) != expected_count:
        raise LearningLabelBackfillError(
            "checkpoint_episode_count_mismatch", "checkpoint episode count differs from dataset"
        )
    if int(generation_summary.get("completed_episode_count", -1)) != expected_count:
        raise LearningLabelBackfillError(
            "generation_episode_count_mismatch",
            "generation summary episode count differs from dataset",
        )
    return _SourceContext(
        dataset_root=root,
        generation_root=generation_root,
        episode_index=episode_index,
        training_seeds=training_seeds,
        reserved_seeds=reserved_seeds,
        git_commit=git_commit,
        source_hashes=source_hashes,
    )


def _audit_d4(
    context: _SourceContext,
    config: LearningLabelBackfillConfig,
    *,
    sink_root: Path | None,
) -> _D4Stats:
    root = context.dataset_root / "d4_region"
    manifest_path = root / "manifest.json"
    manifest = _read_json_object(manifest_path)
    if manifest.get("schema") != _D4_DATASET_SCHEMA:
        raise LearningLabelBackfillError("d4_dataset_schema_mismatch", "unsupported D4 dataset")
    dataset_hash = _require_sha256(manifest.get("dataset_sha256"), "D4 dataset_sha256")
    unsigned = {key: value for key, value in manifest.items() if key not in {"dataset_sha256", "dataset_id"}}
    if _sha256_bytes(_canonical_json_bytes(unsigned)) != dataset_hash:
        raise LearningLabelBackfillError("d4_manifest_hash_mismatch", "D4 manifest content changed")
    if manifest.get("dataset_id") != f"d4-region-learning-dataset-{dataset_hash}":
        raise LearningLabelBackfillError("d4_dataset_id_mismatch", "D4 dataset ID is inconsistent")
    entries = manifest.get("episodes")
    if not isinstance(entries, list) or len(entries) != len(context.episode_index):
        raise LearningLabelBackfillError("d4_episode_inventory_mismatch", "D4 episode inventory differs")
    split = _mapping(manifest.get("split"), "D4 split")
    split_by_seed: dict[int, str] = {}
    for name in ("train", "validation", "test"):
        for seed in _integer_sequence(split.get(f"{name}_seeds"), f"D4 {name} seeds"):
            if seed in split_by_seed:
                raise LearningLabelBackfillError("d4_split_overlap", "D4 seed occurs in two splits")
            split_by_seed[seed] = name
    stats = _D4Stats()
    seen: set[str] = set()
    for entry in entries:
        entry = _mapping(entry, "D4 episode entry")
        relative = _required_text(entry, "relative_path")
        path = _safe_relative_path(root, relative)
        expected_hash = _require_sha256(entry.get("episode_sha256"), "D4 episode_sha256")
        raw = path.read_bytes()
        if config.verify_all_source_hashes and _sha256_bytes(raw) != expected_hash:
            raise LearningLabelBackfillError("d4_episode_hash_mismatch", f"D4 episode changed: {relative}")
        source, frames = _parse_d4_episode(raw, relative)
        episode_id = _required_text(source, "episode_id")
        if episode_id in seen:
            raise LearningLabelBackfillError("d4_duplicate_episode", f"duplicate D4 episode: {episode_id}")
        seen.add(episode_id)
        index_row = context.episode_index.get(episode_id)
        if index_row is None:
            raise LearningLabelBackfillError("d4_episode_identity_unknown", f"unknown D4 episode: {episode_id}")
        _validate_episode_identity(source, index_row, context.git_commit, module="d4")
        if _mapping(entry.get("source"), "D4 manifest source") != source:
            raise LearningLabelBackfillError(
                "d4_manifest_source_mismatch", f"D4 manifest source differs: {episode_id}"
            )
        seed = _required_nonnegative_int(source, "seed")
        declared_split = _required_text(entry, "split")
        if split_by_seed.get(seed) != declared_split:
            raise LearningLabelBackfillError("d4_split_mismatch", f"D4 split mismatch: {episode_id}")
        assert stats.episode_splits is not None
        stats.episode_splits[episode_id] = declared_split
        if seed in context.reserved_seeds:
            raise LearningLabelBackfillError("reserved_seed_leakage", f"D4 contains reserved seed {seed}")
        if int(entry.get("frame_count", -1)) != len(frames):
            raise LearningLabelBackfillError("d4_frame_count_mismatch", f"D4 frame count mismatch: {episode_id}")

        labels = _d4_labels(
            frames,
            episode_id=episode_id,
            split=declared_split,
            source_relative=relative,
            source_sha256=expected_hash,
            transition_window_s=config.d4_transition_window_s,
            stats=stats,
        )
        if sink_root is not None:
            output = sink_root / "d4_region" / f"{path.stem}.labels.jsonl.gz"
            _write_gzip_jsonl_atomic(output, labels)
        stats.episode_count += 1
        stats.frame_count += len(frames)
        stats.dirty_episode_count += bool(source.get("git_dirty"))
    if seen != set(context.episode_index):
        raise LearningLabelBackfillError("d4_episode_set_mismatch", "D4 episodes do not cover the index")
    availability = _mapping(manifest.get("availability"), "D4 availability")
    if int(availability.get("frame_count", -1)) != stats.frame_count:
        raise LearningLabelBackfillError("d4_availability_count_mismatch", "D4 availability count differs")
    return stats


def _parse_d4_episode(raw: bytes, relative: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LearningLabelBackfillError("d4_episode_encoding_invalid", relative) from exc
    lines = text.splitlines()
    if len(lines) < 3 or not raw.endswith(b"\n"):
        raise LearningLabelBackfillError("d4_episode_incomplete", relative)
    records = [_parse_json_object(line, f"{relative}:{index}") for index, line in enumerate(lines, 1)]
    header, footer = records[0], records[-1]
    if header.get("record_type") != "episode_header" or header.get("schema") != _D4_EPISODE_SCHEMA:
        raise LearningLabelBackfillError("d4_episode_header_invalid", relative)
    if footer.get("record_type") != "episode_footer" or footer.get("schema") != _D4_EPISODE_SCHEMA:
        raise LearningLabelBackfillError("d4_episode_footer_invalid", relative)
    if footer.get("complete") is not True:
        raise LearningLabelBackfillError("d4_episode_not_complete", relative)
    frames: list[dict[str, Any]] = []
    for record in records[1:-1]:
        if record.get("record_type") != "frame":
            raise LearningLabelBackfillError("d4_record_type_invalid", relative)
        frame = dict(_mapping(record.get("frame"), "D4 frame"))
        if frame.get("schema") != _D4_FRAME_SCHEMA:
            raise LearningLabelBackfillError("d4_frame_schema_mismatch", relative)
        frames.append(frame)
    if not frames or [int(item.get("frame_index", -1)) for item in frames] != list(range(len(frames))):
        raise LearningLabelBackfillError("d4_frame_sequence_invalid", relative)
    timestamps = [_finite_nonnegative(item.get("timestamp_s"), "D4 timestamp") for item in frames]
    if any(right < left for left, right in zip(timestamps, timestamps[1:])):
        raise LearningLabelBackfillError("d4_timestamp_regressed", relative)
    frame_bytes = b"\n".join(
        _canonical_json_bytes({"record_type": "frame", "frame": item})
        for item in frames
    ) + b"\n"
    if footer.get("frames_sha256") != _sha256_bytes(frame_bytes):
        raise LearningLabelBackfillError("d4_frame_hash_mismatch", relative)
    if int(footer.get("frame_count", -1)) != len(frames):
        raise LearningLabelBackfillError("d4_footer_count_mismatch", relative)
    source = dict(_mapping(header.get("source"), "D4 source"))
    if source.get("schema") != _D4_SOURCE_SCHEMA:
        raise LearningLabelBackfillError("d4_source_schema_mismatch", relative)
    return source, frames


def _d4_labels(
    frames: Sequence[Mapping[str, Any]],
    *,
    episode_id: str,
    split: str,
    source_relative: str,
    source_sha256: str,
    transition_window_s: float,
    stats: _D4Stats,
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        target = _mapping(frame.get("target"), "D4 target")
        recommendation = frame.get("recommendation")
        target_available = target.get("availability") == "available" and target.get("recommendation") is not None
        stats.target_available_count += target_available
        stats.recommendation_available_count += isinstance(recommendation, Mapping)
        if isinstance(recommendation, Mapping):
            actions = recommendation.get("actions")
            transfers = recommendation.get("transfers")
            if not isinstance(actions, list) or not isinstance(transfers, list):
                raise LearningLabelBackfillError("d4_recommendation_invalid", episode_id)
            stats.transfer_count += len(transfers)
            for action in actions:
                action = _mapping(action, "D4 action")
                stats.action_count += 1
                stats.nonzero_quota_action_count += int(action.get("resource_quota_delta", 0)) != 0
                stats.hold_action_count += action.get("hold") is True
                stats.replan_action_count += action.get("request_replan") is True

        provenance = {
            "evidence_class": "truth_free_observed_region_transition",
            "source_component": "d4_region_learning_export",
            "source_relative_path": f"d4_region/{source_relative}",
            "source_sha256": source_sha256,
            "episode_id": episode_id,
            "frame_index": int(frame["frame_index"]),
        }
        next_frame = frames[index + 1] if index + 1 < len(frames) else None
        outcome = _d4_observed_outcome(frame, next_frame, transition_window_s, provenance)
        if outcome["available"]:
            stats.outcome_available_count += 1
        else:
            stats.outcome_unavailable_reasons[str(outcome["reason"])] += 1
        reward_reason = (
            "d4_recommendation_application_evidence_missing"
            if target_available and isinstance(recommendation, Mapping)
            else "d4_policy_action_missing"
        )
        reward = _unavailable_layer(reward_reason, provenance)
        counterfactual = _unavailable_layer("paired_intervention_evidence_missing", provenance)
        causal = _unavailable_layer("counterfactual_and_action_attribution_unavailable", provenance)
        stats.reward_unavailable_reasons[reward_reason] += 1
        labels.append(
            {
                "schema_version": D4_LABEL_SCHEMA_VERSION,
                "episode_id": episode_id,
                "frame_index": int(frame["frame_index"]),
                "timestamp_s": float(frame["timestamp_s"]),
                "split": split,
                "outcome": outcome,
                "reward": reward,
                "counterfactual": counterfactual,
                "causal_label": causal,
            }
        )
    return labels


def _d4_observed_outcome(
    frame: Mapping[str, Any],
    next_frame: Mapping[str, Any] | None,
    transition_window_s: float,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    if next_frame is None:
        return _unavailable_layer("successor_frame_missing", provenance)
    start = _finite_nonnegative(frame.get("timestamp_s"), "D4 timestamp")
    end = _finite_nonnegative(next_frame.get("timestamp_s"), "D4 next timestamp")
    delta_t = end - start
    if delta_t <= 0.0 or delta_t > transition_window_s + 1.0e-9:
        return _unavailable_layer("successor_frame_outside_transition_window", provenance)
    current = _d4_region_summary(_mapping(frame.get("snapshot"), "D4 snapshot"))
    following = _d4_region_summary(_mapping(next_frame.get("snapshot"), "D4 next snapshot"))
    delta = {
        key: float(following[key]) - float(current[key])
        for key in current
        if key != "region_count"
    }
    return _available_layer(
        {
            "schema_version": D4_OUTCOME_SCHEMA_VERSION,
            "semantics": "observed_state_transition_without_action_attribution",
            "window_start_s": start,
            "window_end_s": end,
            "window_duration_s": delta_t,
            "current": current,
            "next": following,
            "delta": delta,
            "action_attribution_available": False,
        },
        provenance,
    )


def _d4_region_summary(snapshot: Mapping[str, Any]) -> dict[str, float | int]:
    regions = snapshot.get("regions")
    if not isinstance(regions, list) or not regions:
        raise LearningLabelBackfillError("d4_region_snapshot_empty", "D4 snapshot has no regions")
    sums = {
        "target_demand": 0.0,
        "high_threat_backlog": 0.0,
        "d1_uncertainty": 0.0,
        "d2_uncertainty": 0.0,
        "d5_visibility": 0.0,
        "d5_consistency": 0.0,
        "reserve_resources": 0.0,
        "committed_resources": 0.0,
        "communication_latency_s": 0.0,
        "packet_loss_rate": 0.0,
        "assignment_conflict_count": 0.0,
        "degradation_failure_count": 0.0,
    }
    for raw in regions:
        region = _mapping(raw, "D4 region")
        for key in (
            "target_demand",
            "high_threat_backlog",
            "d1_uncertainty",
            "d2_uncertainty",
            "d5_visibility",
            "d5_consistency",
            "reserve_resources",
            "committed_resources",
            "communication_latency_s",
            "packet_loss_rate",
            "assignment_conflict_count",
        ):
            sums[key] += _finite_nonnegative(region.get(key), f"D4 {key}")
        sums["degradation_failure_count"] += region.get("degradation_failed") is True
    count = len(regions)
    for key in (
        "d1_uncertainty",
        "d2_uncertainty",
        "d5_visibility",
        "d5_consistency",
        "communication_latency_s",
        "packet_loss_rate",
    ):
        sums[key] /= count
    return {"region_count": count, **sums}


def _audit_d5(
    context: _SourceContext,
    config: LearningLabelBackfillConfig,
    *,
    sink_root: Path | None,
    expected_episode_splits: Mapping[str, str],
) -> _D5Stats:
    root = context.dataset_root / "d5_active_vision"
    manifest = _read_json_object(root / "manifest.json")
    if manifest.get("schema_version") != _D5_DATASET_SCHEMA:
        raise LearningLabelBackfillError("d5_dataset_schema_mismatch", "unsupported D5 dataset")
    storage = _mapping(manifest.get("storage_contract"), "D5 storage contract")
    if storage.get("online_truth_free") is not True or storage.get(
        "offline_labels_physically_separate"
    ) is not True:
        raise LearningLabelBackfillError("d5_truth_isolation_contract_invalid", "D5 storage is not isolated")
    checksums = _read_checksum_file(root / "SHA256SUMS")
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }
    if set(checksums) != actual_files:
        raise LearningLabelBackfillError("d5_artifact_set_mismatch", "D5 checksums do not cover all files")
    if config.verify_all_source_hashes:
        for relative, expected in checksums.items():
            if _sha256_file(_safe_relative_path(root, relative)) != expected:
                raise LearningLabelBackfillError("d5_artifact_hash_mismatch", f"D5 artifact changed: {relative}")

    entries = manifest.get("episodes")
    if not isinstance(entries, list) or len(entries) != len(context.episode_index):
        raise LearningLabelBackfillError("d5_episode_inventory_mismatch", "D5 episode inventory differs")
    stats = _D5Stats()
    seen: set[str] = set()
    split_by_seed: dict[int, str] = {}
    for raw_entry in entries:
        entry = dict(_mapping(raw_entry, "D5 episode entry"))
        if entry.get("schema_version") != _D5_DESCRIPTOR_SCHEMA:
            raise LearningLabelBackfillError("d5_descriptor_schema_mismatch", "D5 descriptor schema changed")
        uid = _required_text(entry, "episode_uid")
        descriptor_relative = f"episodes/{uid}.episode.json"
        descriptor = _read_json_object(_safe_relative_path(root, descriptor_relative))
        if descriptor != entry:
            raise LearningLabelBackfillError("d5_descriptor_manifest_mismatch", f"D5 descriptor differs: {uid}")
        episode_id = _required_text(entry, "episode_id")
        if episode_id in seen:
            raise LearningLabelBackfillError("d5_duplicate_episode", f"duplicate D5 episode: {episode_id}")
        seen.add(episode_id)
        index_row = context.episode_index.get(episode_id)
        if index_row is None:
            raise LearningLabelBackfillError("d5_episode_identity_unknown", f"unknown D5 episode: {episode_id}")
        seed = _required_nonnegative_int(entry, "seed")
        source_identity = _mapping(entry.get("source_identity"), "D5 source identity")
        if source_identity.get("schema_version") != _D5_SOURCE_IDENTITY_SCHEMA:
            raise LearningLabelBackfillError(
                "d5_source_identity_schema_mismatch", episode_id
            )
        _validate_episode_identity(
            {
                **source_identity,
                "episode_id": episode_id,
                "scenario_version": entry.get("scenario_version"),
                "seed": seed,
            },
            index_row,
            context.git_commit,
            module="d5",
        )
        split_name = _required_text(entry, "split")
        if split_name not in {"train", "validation", "test"}:
            raise LearningLabelBackfillError("d5_split_invalid", f"invalid D5 split: {split_name}")
        expected_split = expected_episode_splits.get(episode_id)
        if expected_split is None:
            raise LearningLabelBackfillError(
                "d4_split_identity_missing", f"D4 split missing for D5 episode: {episode_id}"
            )
        if expected_split == split_name:
            stats.split_alignment_count += 1
        else:
            stats.split_mismatch_count += 1
            assert stats.split_mismatch_seeds is not None
            assert stats.split_mismatch_pairs is not None
            stats.split_mismatch_seeds.add(seed)
            stats.split_mismatch_pairs[f"{expected_split}_to_{split_name}"] += 1
        previous_split = split_by_seed.setdefault(seed, split_name)
        if previous_split != split_name:
            raise LearningLabelBackfillError("d5_seed_split_leakage", f"D5 seed spans splits: {seed}")
        if seed in context.reserved_seeds:
            raise LearningLabelBackfillError("reserved_seed_leakage", f"D5 contains reserved seed {seed}")
        online_relative = _required_text(entry, "online_file")
        offline_relative = _required_text(entry, "offline_file")
        if checksums.get(online_relative) != _require_sha256(entry.get("online_sha256"), "D5 online hash"):
            raise LearningLabelBackfillError("d5_online_descriptor_hash_mismatch", uid)
        if checksums.get(offline_relative) != _require_sha256(entry.get("offline_sha256"), "D5 offline hash"):
            raise LearningLabelBackfillError("d5_offline_descriptor_hash_mismatch", uid)

        samples = _parse_d5_online_episode(
            _safe_relative_path(root, online_relative),
            entry,
        )
        _validate_d5_offline_labels(
            _safe_relative_path(root, offline_relative),
            entry,
            samples,
        )
        labels = _d5_labels(
            samples,
            episode_id=episode_id,
            split=split_name,
            source_relative=online_relative,
            source_sha256=str(entry["online_sha256"]),
            transition_window_s=config.d5_transition_window_s,
            stats=stats,
        )
        if sink_root is not None:
            output = sink_root / "d5_active_vision" / f"{uid}.labels.jsonl.gz"
            _write_gzip_jsonl_atomic(output, labels)
        stats.episode_count += 1
        stats.sample_count += len(samples)
        stats.dirty_episode_count += source_identity.get("git_dirty") is True
        stats.synthetic_episode_count += entry.get("synthetic_fixture") is True
    if seen != set(context.episode_index):
        raise LearningLabelBackfillError("d5_episode_set_mismatch", "D5 episodes do not cover the index")
    availability = _mapping(manifest.get("availability"), "D5 availability")
    source_total = int(_mapping(availability.get("reward"), "D5 reward availability").get("sample_count", -1))
    if source_total != stats.sample_count:
        raise LearningLabelBackfillError("d5_availability_count_mismatch", "D5 sample count differs")
    return stats


def _parse_d5_online_episode(
    path: Path,
    descriptor: Mapping[str, Any],
) -> list[dict[str, Any]]:
    snapshots: dict[str, Mapping[str, Any]] = {}
    feedback: dict[str, Mapping[str, Any]] = {}
    samples: list[dict[str, Any]] = []
    header: Mapping[str, Any] | None = None
    footer: Mapping[str, Any] | None = None
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.endswith("\n"):
                raise LearningLabelBackfillError("d5_stream_truncated", f"{path}:{line_number}")
            row = _parse_json_object(line[:-1], f"{path}:{line_number}")
            _assert_truth_free_online(row)
            record_type = row.get("record_type")
            if record_type == "header":
                if header is not None or line_number != 1:
                    raise LearningLabelBackfillError("d5_header_order_invalid", str(path))
                header = row
            elif record_type == "snapshot":
                key = _required_text(row, "object_key")
                value = _mapping(row.get("value"), "D5 snapshot")
                if value.get("schema_version") != _D5_SNAPSHOT_SCHEMA or key in snapshots:
                    raise LearningLabelBackfillError("d5_snapshot_invalid", str(path))
                expected_key = "snapshot-sha256-" + _sha256_bytes(
                    _canonical_json_bytes(value) + b"\n"
                )
                if key != expected_key:
                    raise LearningLabelBackfillError("d5_snapshot_key_mismatch", str(path))
                snapshots[key] = value
            elif record_type == "camera_feedback":
                key = _required_text(row, "object_key")
                value = _mapping(row.get("value"), "D5 camera feedback")
                if value.get("schema_version") != _D5_FEEDBACK_SCHEMA or key in feedback:
                    raise LearningLabelBackfillError("d5_feedback_invalid", str(path))
                expected_key = "camera-feedback-sha256-" + _sha256_bytes(
                    _canonical_json_bytes(value) + b"\n"
                )
                if key != expected_key:
                    raise LearningLabelBackfillError("d5_feedback_key_mismatch", str(path))
                feedback[key] = value
            elif record_type == "sample":
                if row.get("schema_version") != _D5_SAMPLE_SCHEMA:
                    raise LearningLabelBackfillError("d5_sample_schema_mismatch", str(path))
                sequence = _required_nonnegative_int(row, "sequence_index")
                if sequence != len(samples):
                    raise LearningLabelBackfillError("d5_sample_sequence_invalid", str(path))
                snapshot_key = _required_text(row, "snapshot_key")
                feedback_key = _required_text(row, "camera_feedback_key")
                if snapshot_key not in snapshots or feedback_key not in feedback:
                    raise LearningLabelBackfillError("d5_sample_reference_missing", str(path))
                sample = dict(row)
                sample["_snapshot"] = snapshots[snapshot_key]
                sample["_feedback"] = feedback[feedback_key]
                _validate_d5_sample(sample)
                samples.append(sample)
            elif record_type == "footer":
                footer = row
            else:
                raise LearningLabelBackfillError("d5_record_type_invalid", str(path))
    if header is None or footer is None or not samples:
        raise LearningLabelBackfillError("d5_episode_incomplete", str(path))
    if header.get("schema_version") != _D5_RECORD_SCHEMA or footer.get("schema_version") != _D5_RECORD_SCHEMA:
        raise LearningLabelBackfillError("d5_record_schema_mismatch", str(path))
    for key in ("episode_uid", "episode_id", "scenario_version", "seed"):
        if header.get(key) != descriptor.get(key):
            raise LearningLabelBackfillError("d5_header_identity_mismatch", f"{path}:{key}")
    if header.get("source_identity") != descriptor.get("source_identity"):
        raise LearningLabelBackfillError("d5_header_source_mismatch", str(path))
    if int(footer.get("sample_count", -1)) != len(samples) or int(descriptor.get("sample_count", -1)) != len(samples):
        raise LearningLabelBackfillError("d5_sample_count_mismatch", str(path))
    if int(footer.get("unique_snapshot_count", -1)) != len(snapshots):
        raise LearningLabelBackfillError("d5_snapshot_count_mismatch", str(path))
    if int(footer.get("unique_camera_feedback_count", -1)) != len(feedback):
        raise LearningLabelBackfillError("d5_feedback_count_mismatch", str(path))
    sample_keys = [str(item["sample_key"]) for item in samples]
    observation_keys = [str(item["observation_key"]) for item in samples]
    if len(sample_keys) != len(set(sample_keys)) or len(observation_keys) != len(
        set(observation_keys)
    ):
        raise LearningLabelBackfillError("d5_sample_identity_duplicate", str(path))
    timestamps = [
        _finite_nonnegative(item["_snapshot"].get("snapshot_timestamp"), "D5 timestamp")
        for item in samples
    ]
    if any(right + 1.0e-9 < left for left, right in zip(timestamps, timestamps[1:])):
        raise LearningLabelBackfillError("d5_sample_timestamp_regressed", str(path))
    sample_index = [
        {
            "sequence_index": sample["sequence_index"],
            "sample_key": sample["sample_key"],
            "observation_key": sample["observation_key"],
            "snapshot_key": sample["snapshot_key"],
            "camera_feedback_key": sample["camera_feedback_key"],
        }
        for sample in samples
    ]
    if footer.get("sample_index_sha256") != _sha256_bytes(
        _canonical_json_bytes(sample_index) + b"\n"
    ):
        raise LearningLabelBackfillError("d5_sample_index_hash_mismatch", str(path))
    return samples


def _validate_d5_sample(sample: Mapping[str, Any]) -> None:
    camera_id = _required_text(sample, "camera_id")
    mode = _required_text(sample, "effective_mode")
    if mode not in _D5_MODES:
        raise LearningLabelBackfillError("d5_mode_invalid", camera_id)
    snapshot = _mapping(sample.get("_snapshot"), "D5 snapshot")
    plan = _mapping(snapshot.get("plan"), "D5 plan")
    communication = _mapping(snapshot.get("communication"), "D5 communication")
    expected_versions = (
        _required_nonnegative_int(plan, "plan_version"),
        _required_nonnegative_int(plan, "coalition_version"),
        _required_nonnegative_int(communication, "communication_version"),
    )
    actual_versions = (
        _required_nonnegative_int(sample, "plan_version"),
        _required_nonnegative_int(sample, "coalition_version"),
        _required_nonnegative_int(sample, "communication_version"),
    )
    if actual_versions != expected_versions:
        raise LearningLabelBackfillError("d5_sample_version_mismatch", camera_id)
    action = _mapping(sample.get("effective_action"), "D5 effective action")
    rule = _mapping(sample.get("rule_demonstration_action"), "D5 rule action")
    for value in (action, rule):
        if value.get("schema_version") != _D5_ACTION_SCHEMA:
            raise LearningLabelBackfillError("d5_action_schema_mismatch", camera_id)
        if _required_text(value, "camera_id") != camera_id:
            raise LearningLabelBackfillError("d5_action_camera_mismatch", camera_id)
        intent = _required_text(value, "intent")
        if intent not in _D5_INTENTS:
            raise LearningLabelBackfillError("d5_action_intent_invalid", intent)
        target = value.get("target_global_track_id")
        if (intent in _D5_TARGET_INTENTS) != (isinstance(target, str) and bool(target)):
            raise LearningLabelBackfillError("d5_action_target_semantics_invalid", camera_id)
    if mode != "assist" and action != rule:
        raise LearningLabelBackfillError("d5_rule_fallback_changed", camera_id)
    cameras = snapshot.get("cameras")
    tracks = snapshot.get("tracks")
    if not isinstance(cameras, list) or not any(item.get("camera_id") == camera_id for item in cameras):
        raise LearningLabelBackfillError("d5_camera_reference_unknown", camera_id)
    if not isinstance(tracks, list):
        raise LearningLabelBackfillError("d5_tracks_invalid", camera_id)
    center_ids = {str(item.get("global_track_id")) for item in tracks}
    target_id = action.get("target_global_track_id")
    if target_id is not None and target_id not in center_ids:
        raise LearningLabelBackfillError("d5_center_reference_unknown", str(target_id))
    ack = sample.get("runtime_ack")
    if ack is not None:
        ack = _mapping(ack, "D5 runtime ACK")
        if ack.get("schema_version") != _D5_ACK_SCHEMA:
            raise LearningLabelBackfillError("d5_ack_schema_mismatch", camera_id)
        if ack.get("sample_key") != sample.get("sample_key") or ack.get("camera_id") != camera_id:
            raise LearningLabelBackfillError("d5_ack_identity_mismatch", camera_id)
        ack_versions = tuple(_required_nonnegative_int(ack, key) for key in (
            "plan_version", "coalition_version", "communication_version"
        ))
        if ack_versions != expected_versions:
            raise LearningLabelBackfillError("d5_ack_version_mismatch", camera_id)
        if not isinstance(ack.get("accepted"), bool):
            raise LearningLabelBackfillError("d5_ack_status_invalid", camera_id)
        _required_nonnegative_int(ack, "command_version")
        ack_timestamp = _finite_nonnegative(ack.get("ack_timestamp"), "D5 ACK timestamp")
        issued_timestamp = _finite_nonnegative(action.get("issued_timestamp"), "D5 issue timestamp")
        if ack_timestamp + 1.0e-9 < issued_timestamp:
            raise LearningLabelBackfillError("d5_ack_precedes_command", camera_id)
        _required_text(ack, "status_code")
    feedback = _mapping(sample.get("_feedback"), "D5 camera feedback")
    feedback_state = _mapping(feedback.get("camera_state"), "D5 feedback camera state")
    if feedback_state.get("camera_id") != camera_id:
        raise LearningLabelBackfillError("d5_feedback_camera_mismatch", camera_id)


def _validate_d5_offline_labels(
    path: Path,
    descriptor: Mapping[str, Any],
    samples: Sequence[Mapping[str, Any]],
) -> None:
    payload = _read_json_object(path)
    expected_payload_fields = {
        "schema_version",
        "episode_uid",
        "episode_id",
        "scenario_version",
        "seed",
        "reward_bounds",
        "labels",
    }
    if set(payload) != expected_payload_fields:
        raise LearningLabelBackfillError("d5_offline_fields_mismatch", str(path))
    if payload.get("schema_version") != _D5_OFFLINE_LABELS_SCHEMA:
        raise LearningLabelBackfillError("d5_offline_schema_mismatch", str(path))
    for key in ("episode_uid", "episode_id", "scenario_version", "seed"):
        if payload.get(key) != descriptor.get(key):
            raise LearningLabelBackfillError("d5_offline_identity_mismatch", f"{path}:{key}")
    labels = payload.get("labels")
    if not isinstance(labels, list) or len(labels) != len(samples):
        raise LearningLabelBackfillError("d5_offline_count_mismatch", str(path))
    if payload.get("reward_bounds") != {"minimum": -1.0, "maximum": 1.0}:
        raise LearningLabelBackfillError("d5_offline_reward_bounds_mismatch", str(path))
    sample_by_key = {str(item["sample_key"]): item for item in samples}
    availability = Counter()
    seen_labels: set[str] = set()
    for label in labels:
        label = _mapping(label, "D5 offline label")
        if label.get("schema_version") != _D5_OFFLINE_LABEL_SCHEMA:
            raise LearningLabelBackfillError("d5_offline_label_schema_mismatch", str(path))
        sample_key = _required_text(label, "sample_key")
        if sample_key in seen_labels:
            raise LearningLabelBackfillError("d5_offline_label_duplicate", sample_key)
        seen_labels.add(sample_key)
        source = sample_by_key.get(sample_key)
        if source is None or label.get("observation_key") != source.get("observation_key"):
            raise LearningLabelBackfillError("d5_offline_join_mismatch", sample_key)
        layer_availability: dict[str, bool] = {}
        for name in ("outcome", "reward", "counterfactual", "causal_label"):
            layer = _mapping(label.get(name), f"D5 source {name}")
            available = layer.get("available")
            if not isinstance(available, bool):
                raise LearningLabelBackfillError("d5_source_availability_invalid", name)
            _validate_source_offline_layer(name, layer, available)
            availability[name] += available
            layer_availability[name] = available
        if layer_availability["reward"] and not layer_availability["outcome"]:
            raise LearningLabelBackfillError(
                "d5_source_reward_without_outcome", sample_key
            )
        if layer_availability["causal_label"] and not (
            layer_availability["outcome"]
            and layer_availability["counterfactual"]
        ):
            raise LearningLabelBackfillError(
                "d5_source_causal_dependencies_missing", sample_key
            )
    if seen_labels != set(sample_by_key):
        raise LearningLabelBackfillError("d5_offline_label_set_mismatch", str(path))
    declared = _mapping(descriptor.get("availability"), "D5 descriptor availability")
    for name in ("outcome", "reward", "counterfactual", "causal_label"):
        item = _mapping(declared.get(name), f"D5 descriptor {name}")
        if int(item.get("sample_count", -1)) != len(samples) or int(
            item.get("available_sample_count", -1)
        ) != availability[name]:
            raise LearningLabelBackfillError("d5_descriptor_availability_mismatch", name)


def _validate_source_offline_layer(
    name: str,
    layer: Mapping[str, Any],
    available: bool,
) -> None:
    """Validate the frozen D5 producer's four physically detached layers."""

    expected_fields = {
        "outcome": {"available", "value"},
        "reward": {"available", "value", "minimum", "maximum", "provenance"},
        "counterfactual": {
            "available",
            "reward",
            "minimum",
            "maximum",
            "provenance",
        },
        "causal_label": {"available", "value"},
    }
    fields = expected_fields.get(name)
    if fields is None or set(layer) != fields:
        raise LearningLabelBackfillError("d5_source_layer_fields_mismatch", name)

    if name in {"reward", "counterfactual"}:
        if layer.get("minimum") != -1.0 or layer.get("maximum") != 1.0:
            raise LearningLabelBackfillError("d5_source_reward_bounds_mismatch", name)
        value_key = "value" if name == "reward" else "reward"
        value = layer.get(value_key)
        provenance = layer.get("provenance")
        if available:
            bounded = _finite(value, f"D5 source {name}")
            if not -1.0 <= bounded <= 1.0:
                raise LearningLabelBackfillError(
                    "d5_source_reward_out_of_bounds", name
                )
            if not isinstance(provenance, str) or not provenance.strip():
                raise LearningLabelBackfillError(
                    "d5_source_provenance_missing", name
                )
        elif value is not None or provenance is not None:
            raise LearningLabelBackfillError(
                "d5_source_unavailable_layer_not_null", name
            )
        return

    value = layer.get("value")
    if available:
        if not isinstance(value, Mapping):
            raise LearningLabelBackfillError(
                "d5_source_available_object_missing", name
            )
    elif value is not None:
        raise LearningLabelBackfillError(
            "d5_source_unavailable_layer_not_null", name
        )


def _d5_labels(
    samples: Sequence[Mapping[str, Any]],
    *,
    episode_id: str,
    split: str,
    source_relative: str,
    source_sha256: str,
    transition_window_s: float,
    stats: _D5Stats,
) -> list[dict[str, Any]]:
    by_camera: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for sample in samples:
        by_camera[str(sample["camera_id"])].append(sample)
        stats.rule_demonstration_count += 1
        stats.runtime_ack_count += sample.get("runtime_ack") is not None
        stats.requested_action_count += sample.get("requested_action") is not None
        stats.modes[str(sample["effective_mode"])] += 1
        stats.intents[str(_mapping(sample["effective_action"], "D5 action")["intent"])] += 1
    next_by_sequence: dict[int, Mapping[str, Any]] = {}
    for camera_samples in by_camera.values():
        for current, following in zip(camera_samples, camera_samples[1:]):
            next_by_sequence[int(current["sequence_index"])] = following

    labels: list[dict[str, Any]] = []
    for sample in samples:
        sequence = int(sample["sequence_index"])
        provenance = {
            "evidence_class": "truth_free_observed_camera_transition",
            "source_component": "d5_active_vision_online_export",
            "source_relative_path": f"d5_active_vision/{source_relative}",
            "source_sha256": source_sha256,
            "episode_id": episode_id,
            "sample_key": sample["sample_key"],
            "observation_key": sample["observation_key"],
        }
        following = next_by_sequence.get(sequence)
        outcome = _d5_observed_outcome(sample, following, transition_window_s, provenance)
        if outcome["available"]:
            stats.outcome_available_count += 1
        else:
            stats.outcome_unavailable_reasons[str(outcome["reason"])] += 1
        reward = _d5_reward(sample, following, outcome, provenance)
        if reward["available"]:
            stats.reward_available_count += 1
            value = float(reward["value"])
            stats.reward_positive_count += value > 0.0
            stats.reward_negative_count += value < 0.0
        else:
            stats.reward_unavailable_reasons[str(reward["reason"])] += 1
        ack = sample.get("runtime_ack")
        stats.accepted_ack_count += isinstance(ack, Mapping) and ack.get("accepted") is True
        counterfactual = _unavailable_layer("paired_intervention_evidence_missing", provenance)
        causal = _unavailable_layer("counterfactual_unavailable", provenance)
        labels.append(
            {
                "schema_version": D5_LABEL_SCHEMA_VERSION,
                "episode_id": episode_id,
                "sample_key": sample["sample_key"],
                "observation_key": sample["observation_key"],
                "sequence_index": sequence,
                "camera_id": sample["camera_id"],
                "split": split,
                "outcome": outcome,
                "reward": reward,
                "counterfactual": counterfactual,
                "causal_label": causal,
            }
        )
    return labels


def _d5_observed_outcome(
    sample: Mapping[str, Any],
    following: Mapping[str, Any] | None,
    transition_window_s: float,
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    if following is None:
        return _unavailable_layer("successor_camera_sample_missing", provenance)
    current_snapshot = _mapping(sample.get("_snapshot"), "D5 snapshot")
    next_snapshot = _mapping(following.get("_snapshot"), "D5 next snapshot")
    start = _finite_nonnegative(current_snapshot.get("snapshot_timestamp"), "D5 timestamp")
    end = _finite_nonnegative(next_snapshot.get("snapshot_timestamp"), "D5 next timestamp")
    delta_t = end - start
    if delta_t <= 0.0 or delta_t > transition_window_s + 1.0e-9:
        return _unavailable_layer("successor_camera_sample_outside_transition_window", provenance)
    action = _mapping(sample.get("effective_action"), "D5 action")
    target_id = action.get("target_global_track_id")
    camera_id = str(sample["camera_id"])
    if target_id is not None:
        current = _projection_summary(current_snapshot, camera_id, str(target_id))
        following_summary = _projection_summary(next_snapshot, camera_id, str(target_id))
        if current is None or following_summary is None:
            return _unavailable_layer("target_projection_missing_in_transition", provenance)
        semantics = "target_projection_transition_without_action_attribution"
    else:
        current = _camera_coverage_summary(current_snapshot, camera_id)
        following_summary = _camera_coverage_summary(next_snapshot, camera_id)
        semantics = "camera_coverage_transition_without_action_attribution"
    delta = {
        key: float(following_summary[key]) - float(current[key])
        for key in current
        if isinstance(current[key], (int, float)) and not isinstance(current[key], bool)
    }
    return _available_layer(
        {
            "schema_version": D5_OUTCOME_SCHEMA_VERSION,
            "semantics": semantics,
            "window_start_s": start,
            "window_end_s": end,
            "window_duration_s": delta_t,
            "camera_id": camera_id,
            "intent": action["intent"],
            "target_global_track_id": target_id,
            "current": current,
            "next": following_summary,
            "delta": delta,
            "action_attribution_available": False,
        },
        provenance,
    )


def _d5_reward(
    sample: Mapping[str, Any],
    following: Mapping[str, Any] | None,
    outcome: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    if not outcome.get("available"):
        return _unavailable_layer("observed_outcome_unavailable", provenance)
    ack = sample.get("runtime_ack")
    if not isinstance(ack, Mapping):
        return _unavailable_layer("runtime_ack_missing", provenance)
    if ack.get("accepted") is not True:
        return _available_layer(-1.0, {**provenance, "reward_semantics": "rejected_command_penalty"})
    if following is None:
        return _unavailable_layer("successor_camera_feedback_missing", provenance)
    next_feedback = _mapping(following.get("_feedback"), "D5 next feedback")
    next_feedback_state = _mapping(
        next_feedback.get("camera_state"), "D5 next feedback camera state"
    )
    feedback_timestamp = _finite_nonnegative(
        next_feedback_state.get("state_timestamp"), "D5 next feedback timestamp"
    )
    ack_timestamp = _finite_nonnegative(ack.get("ack_timestamp"), "D5 ACK timestamp")
    if feedback_timestamp + 1.0e-9 < ack_timestamp:
        return _unavailable_layer("post_ack_camera_feedback_missing", provenance)
    accepted_version = next_feedback.get("last_accepted_command_version")
    command_version = ack.get("command_version")
    if accepted_version is None:
        return _unavailable_layer("accepted_command_version_feedback_missing", provenance)
    if int(accepted_version) != int(command_version):
        return _unavailable_layer("accepted_command_version_feedback_mismatch", provenance)
    value = _mapping(outcome.get("value"), "D5 outcome value")
    current = _mapping(value.get("current"), "D5 current outcome")
    next_value = _mapping(value.get("next"), "D5 next outcome")
    if value.get("target_global_track_id") is not None:
        error_gain = _clip(
            (float(current["angular_error_deg"]) - float(next_value["angular_error_deg"])) / 30.0,
            -1.0,
            1.0,
        )
        visibility_gain = float(next_value["visibility_probability"]) - float(
            current["visibility_probability"]
        )
        association_gain = float(next_value["association_confidence"]) - float(
            current["association_confidence"]
        )
        fov_gain = float(next_value["in_fov"]) - float(current["in_fov"])
        occlusion_gain = float(current["occlusion_fraction"]) - float(
            next_value["occlusion_fraction"]
        )
        reward = (
            0.30 * error_gain
            + 0.25 * visibility_gain
            + 0.20 * association_gain
            + 0.15 * fov_gain
            + 0.10 * occlusion_gain
        )
    else:
        coverage_gain = float(next_value["in_fov_ratio"]) - float(current["in_fov_ratio"])
        visibility_gain = float(next_value["mean_visibility_probability"]) - float(
            current["mean_visibility_probability"]
        )
        association_gain = float(next_value["mean_association_confidence"]) - float(
            current["mean_association_confidence"]
        )
        reward = 0.5 * coverage_gain + 0.3 * visibility_gain + 0.2 * association_gain
    return _available_layer(
        _clip(reward, -1.0, 1.0),
        {**provenance, "reward_semantics": "bounded_observed_transition_after_versioned_ack"},
    )


def _projection_summary(
    snapshot: Mapping[str, Any], camera_id: str, target_id: str
) -> dict[str, Any] | None:
    projections = snapshot.get("projections")
    if not isinstance(projections, list):
        raise LearningLabelBackfillError("d5_projections_invalid", camera_id)
    matches = [
        item
        for item in projections
        if item.get("camera_id") == camera_id and item.get("global_track_id") == target_id
    ]
    if len(matches) != 1:
        return None
    item = _mapping(matches[0], "D5 projection")
    yaw = _finite(item.get("yaw_error_deg"), "D5 yaw error")
    pitch = _finite(item.get("pitch_error_deg"), "D5 pitch error")
    measurement = _finite_nonnegative(item.get("measurement_timestamp"), "D5 measurement timestamp")
    arrival = _finite_nonnegative(item.get("arrival_timestamp"), "D5 arrival timestamp")
    if arrival + 1.0e-9 < measurement:
        raise LearningLabelBackfillError("d5_projection_timestamp_invalid", target_id)
    return {
        "angular_error_deg": math.hypot(yaw, pitch),
        "yaw_error_deg": yaw,
        "pitch_error_deg": pitch,
        "visibility_probability": _bounded(item.get("visibility_probability"), "visibility"),
        "association_confidence": _bounded(item.get("association_confidence"), "association"),
        "occlusion_fraction": _bounded(item.get("occlusion_fraction"), "occlusion"),
        "in_fov": bool(item.get("in_fov")),
        "measurement_timestamp": measurement,
        "arrival_timestamp": arrival,
        "measurement_age_s": max(0.0, arrival - measurement),
    }


def _camera_coverage_summary(snapshot: Mapping[str, Any], camera_id: str) -> dict[str, Any]:
    projections = snapshot.get("projections")
    if not isinstance(projections, list):
        raise LearningLabelBackfillError("d5_projections_invalid", camera_id)
    values = [item for item in projections if item.get("camera_id") == camera_id]
    count = len(values)
    if not count:
        return {
            "projection_count": 0,
            "in_fov_count": 0,
            "in_fov_ratio": 0.0,
            "mean_visibility_probability": 0.0,
            "mean_association_confidence": 0.0,
        }
    in_fov_count = sum(item.get("in_fov") is True for item in values)
    return {
        "projection_count": count,
        "in_fov_count": in_fov_count,
        "in_fov_ratio": in_fov_count / count,
        "mean_visibility_probability": sum(
            _bounded(item.get("visibility_probability"), "visibility") for item in values
        )
        / count,
        "mean_association_confidence": sum(
            _bounded(item.get("association_confidence"), "association") for item in values
        )
        / count,
    }


def _readiness_payload(
    context: _SourceContext,
    config: LearningLabelBackfillConfig,
    d4: _D4Stats,
    d5: _D5Stats,
) -> dict[str, Any]:
    d4_behavior_cloning_available = bool(
        config.verify_all_source_hashes
        and d4.dirty_episode_count == 0
        and d4.target_available_count == d4.frame_count
        and d4.recommendation_available_count == d4.frame_count
    )
    d5_behavior_cloning_available = bool(
        config.verify_all_source_hashes
        and d5.dirty_episode_count == 0
        and d5.rule_demonstration_count == d5.sample_count
    )
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "audit_date": config.audit_date,
        "source": {
            "dataset_name": context.dataset_root.name,
            "git_commit": context.git_commit,
            "episode_count": len(context.episode_index),
            "batch_learning_export_summary_sha256": context.source_hashes[
                "batch_learning_export_summary"
            ],
            "generation_plan_sha256": context.source_hashes["generation_plan"],
            "generation_summary_sha256": context.source_hashes["generation_summary"],
            "generation_checkpoint_sha256": context.source_hashes[
                "generation_checkpoint"
            ],
            "episode_index_sha256": context.source_hashes["episode_index"],
            "training_seed_registry_sha256": context.source_hashes[
                "training_seed_registry"
            ],
        },
        "labeling_policy": _labeling_policy(config),
        "truth_isolation": {
            "online_source_mutated": False,
            "training_seed_count": len(context.training_seeds),
            "reserved_evaluation_seed_count": len(context.reserved_seeds),
            "reserved_evaluation_seeds": sorted(context.reserved_seeds),
            "training_reserved_overlap_count": len(context.training_seeds & context.reserved_seeds),
            "reserved_seed_used_for_labels": False,
            "online_truth_policy": "forbidden",
            "labels_detached": True,
            "all_registered_source_hashes_verified": config.verify_all_source_hashes,
            "cross_module_split_alignment": {
                "status": (
                    "consistent" if d5.split_mismatch_count == 0 else "inconsistent"
                ),
                "aligned_episode_count": d5.split_alignment_count,
                "mismatched_episode_count": d5.split_mismatch_count,
                "mismatched_seed_count": len(d5.split_mismatch_seeds or ()),
                "mismatch_pair_counts": dict(
                    sorted((d5.split_mismatch_pairs or {}).items())
                ),
                "training_scope": (
                    "joint_training_allowed"
                    if d5.split_mismatch_count == 0
                    else "module_local_training_only"
                ),
                "reason": (
                    None
                    if d5.split_mismatch_count == 0
                    else "d4_d5_seed_split_registries_differ"
                ),
            },
        },
        "d4_region": {
            "episode_count": d4.episode_count,
            "frame_count": d4.frame_count,
            "observed_outcome": _availability_summary(
                d4.outcome_available_count,
                d4.frame_count,
                reasons=d4.outcome_unavailable_reasons,
                semantics="truth-free state transition; no policy-effect attribution",
            ),
            "reward": _availability_summary(
                d4.reward_available_count,
                d4.frame_count,
                reasons=d4.reward_unavailable_reasons,
                semantics="bounded reward requires a versioned applied recommendation and post-action evidence",
            ),
            "counterfactual": _availability_summary(
                d4.counterfactual_available_count,
                d4.frame_count,
                reasons={"paired_intervention_evidence_missing": d4.frame_count},
                semantics="single factual trajectory cannot identify an alternative action",
            ),
            "causal_label": _availability_summary(
                d4.causal_label_available_count,
                d4.frame_count,
                reasons={"counterfactual_and_action_attribution_unavailable": d4.frame_count},
                semantics="requires factual action attribution plus counterfactual evidence",
            ),
            "behavior_cloning": {
                "available": d4_behavior_cloning_available,
                "reason": (
                    "all_clean_frames_have_rule_demonstrations"
                    if d4_behavior_cloning_available
                    else "source_hash_verification_or_rule_demonstration_incomplete"
                ),
                "qualification": "pipeline_ready_but_action_diversity_insufficient_for_policy_promotion",
            },
            "ppo": {
                "available": False,
                "reason": "reward_and_applied_action_evidence_unavailable",
            },
            "action_audit": {
                "action_count": d4.action_count,
                "nonzero_quota_action_count": d4.nonzero_quota_action_count,
                "hold_action_count": d4.hold_action_count,
                "request_replan_action_count": d4.replan_action_count,
                "transfer_count": d4.transfer_count,
            },
            "missing_producer_conditions": [
                "versioned D4 recommendation consumption/adoption evidence per frame",
                "applied action digest bound to plan_id/plan_version/epoch/lease",
                "post-action regional state and terminal episode outcome",
                "non-trivial quota/hold/replan/transfer action coverage",
                "on-policy rollout log probability/value for PPO",
            ],
        },
        "d5_active_vision": {
            "episode_count": d5.episode_count,
            "sample_count": d5.sample_count,
            "synthetic_episode_count": d5.synthetic_episode_count,
            "observed_outcome": _availability_summary(
                d5.outcome_available_count,
                d5.sample_count,
                reasons=d5.outcome_unavailable_reasons,
                semantics="adjacent camera observation only; no command-effect attribution",
            ),
            "reward": _availability_summary(
                d5.reward_available_count,
                d5.sample_count,
                reasons=d5.reward_unavailable_reasons,
                semantics="bounded visual reward requires matching runtime ACK and accepted command feedback",
            ),
            "counterfactual": _availability_summary(
                d5.counterfactual_available_count,
                d5.sample_count,
                reasons={"paired_intervention_evidence_missing": d5.sample_count},
                semantics="same-initial-state paired replay or intervention is required",
            ),
            "causal_label": _availability_summary(
                d5.causal_label_available_count,
                d5.sample_count,
                reasons={"counterfactual_unavailable": d5.sample_count},
                semantics="observational camera transitions are not causal labels",
            ),
            "behavior_cloning": {
                "available": d5_behavior_cloning_available,
                "reason": (
                    "all_clean_samples_have_bounded_rule_demonstrations"
                    if d5_behavior_cloning_available
                    else "source_hash_verification_or_rule_demonstration_incomplete"
                ),
            },
            "ppo": {
                "available": bool(d5.sample_count and d5.reward_available_count == d5.sample_count),
                "reason": (
                    "all_effective_actions_have_bounded_rewards"
                    if d5.sample_count and d5.reward_available_count == d5.sample_count
                    else "runtime_application_and_reward_evidence_incomplete"
                ),
            },
            "runtime_evidence": {
                "runtime_ack_count": d5.runtime_ack_count,
                "accepted_ack_count": d5.accepted_ack_count,
                "requested_action_count": d5.requested_action_count,
                "effective_mode_counts": dict(sorted(d5.modes.items())),
                "intent_counts": dict(sorted(d5.intents.items())),
                "reward_positive_count": d5.reward_positive_count,
                "reward_negative_count": d5.reward_negative_count,
            },
            "missing_producer_conditions": [
                "runtime ACK joined to each sample before learning export finalization",
                "camera feedback last_accepted_command_version mapped from runtime state",
                "version-consistent applied command and post-command observation window",
                "terminal task outcome if reward includes mission completion",
                "same-initial-state paired replay/intervention for counterfactual or causal labels",
                "on-policy rollout log probability/value for PPO",
            ],
        },
        "overall": {
            "d4_behavior_cloning_available": d4_behavior_cloning_available,
            "d4_ppo_available": False,
            "d5_active_vision_behavior_cloning_available": d5_behavior_cloning_available,
            "d5_active_vision_ppo_available": bool(
                d5.sample_count and d5.reward_available_count == d5.sample_count
            ),
            "counterfactual_training_available": False,
            "causal_training_available": False,
            "formal_dataset_relabel_required": False,
            "sidecar_backfill_supported": True,
            "cross_module_joint_training_available": d5.split_mismatch_count == 0,
        },
    }


def _labeling_policy(config: LearningLabelBackfillConfig) -> dict[str, Any]:
    return {
        "audit_date": config.audit_date,
        "d4_transition_window_s": config.d4_transition_window_s,
        "d5_transition_window_s": config.d5_transition_window_s,
        "reserved_evaluation_seeds": list(config.reserved_evaluation_seeds),
        "verify_all_source_hashes": config.verify_all_source_hashes,
    }


def _availability_summary(
    available: int,
    total: int,
    *,
    reasons: Mapping[str, int],
    semantics: str,
) -> dict[str, Any]:
    status = "available" if available == total else "unavailable" if available == 0 else "partial"
    return {
        "status": status,
        "available_count": int(available),
        "unavailable_count": int(total - available),
        "total_count": int(total),
        "reasons": {key: int(value) for key, value in sorted(reasons.items()) if value},
        "semantics": semantics,
    }


def _available_layer(value: Any, provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": LAYER_SCHEMA_VERSION,
        "available": True,
        "value": value,
        "reason": None,
        "provenance": dict(provenance),
    }


def _unavailable_layer(reason: str, provenance: Mapping[str, Any]) -> dict[str, Any]:
    if not str(reason).strip():
        raise ValueError("unavailable layer requires a reason")
    return {
        "schema_version": LAYER_SCHEMA_VERSION,
        "available": False,
        "value": None,
        "reason": str(reason),
        "provenance": dict(provenance),
    }


def _validate_episode_identity(
    source: Mapping[str, Any],
    index_row: Mapping[str, Any],
    git_commit: str,
    *,
    module: str,
) -> None:
    expected = (
        index_row.get("episode_id"),
        index_row.get("scenario_version"),
        int(index_row.get("seed", -1)),
        index_row.get("config_sha256"),
        git_commit,
        False,
    )
    actual = (
        source.get("episode_id"),
        source.get("scenario_version"),
        int(source.get("seed", -1)),
        source.get("config_sha256"),
        source.get("git_commit"),
        source.get("git_dirty"),
    )
    if actual != expected:
        raise LearningLabelBackfillError(
            f"{module}_episode_identity_mismatch",
            f"{module.upper()} episode identity does not match the frozen index",
        )


def _assert_truth_free_online(value: Any, *, path: str = "online") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if (
                normalized in _D5_FORBIDDEN_ONLINE_KEYS
                or normalized.startswith("offline_truth")
                or normalized.startswith("truth_")
                or normalized.endswith("_truth_id")
            ):
                raise LearningLabelBackfillError(
                    "d5_online_truth_field_forbidden", f"forbidden online field: {path}.{key}"
                )
            _assert_truth_free_online(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_truth_free_online(child, path=f"{path}[{index}]")


def _artifact_entries(root: Path, *, exclude: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": _sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
        if path.name not in exclude
    ]


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(value) + b"\n")


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _write_gzip_jsonl_atomic(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as stream:
                for row in rows:
                    stream.write(_canonical_json_bytes(row) + b"\n")
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _read_checksum_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise LearningLabelBackfillError("checksums_missing", f"checksum file missing: {path}")
    checksums: dict[str, str] = {}
    previous = ""
    for line_number, raw in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        parts = raw.split("  ", 1)
        if len(parts) != 2:
            raise LearningLabelBackfillError("checksums_invalid", f"invalid checksum line {line_number}")
        digest = _require_sha256(parts[0], "checksum")
        relative = parts[1]
        if not relative or relative <= previous or relative in checksums:
            raise LearningLabelBackfillError("checksums_invalid", "checksum paths must be sorted and unique")
        _safe_relative_path(path.parent, relative)
        checksums[relative] = digest
        previous = relative
    if not checksums:
        raise LearningLabelBackfillError("checksums_invalid", "checksum file is empty")
    return checksums


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise LearningLabelBackfillError("json_invalid", f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise LearningLabelBackfillError("json_not_object", f"JSON root is not an object: {path}")
    return value


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise LearningLabelBackfillError("jsonl_blank_line", f"blank row: {path}:{line_number}")
            yield _parse_json_object(line, f"{path}:{line_number}")


def _parse_json_object(text: str, source: str) -> dict[str, Any]:
    try:
        value = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise LearningLabelBackfillError("json_invalid", f"invalid JSON object: {source}") from exc
    if not isinstance(value, dict):
        raise LearningLabelBackfillError("json_not_object", f"JSON row is not an object: {source}")
    return value


def _safe_relative_path(root: Path, relative: str) -> Path:
    candidate = Path(str(relative))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LearningLabelBackfillError("unsafe_relative_path", f"unsafe path: {relative}")
    resolved = (root / candidate).resolve()
    if not _is_relative_to(resolved, root.resolve()) or not resolved.is_file():
        raise LearningLabelBackfillError("source_artifact_missing", f"missing artifact: {relative}")
    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha256(value: Any, name: str) -> str:
    text = str(value or "").lower()
    if len(text) != 64 or any(character not in _HEX64 for character in text):
        raise LearningLabelBackfillError("sha256_invalid", f"{name} is not a SHA256 digest")
    return text


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LearningLabelBackfillError("mapping_required", f"{name} must be an object")
    return value


def _required_text(value: Mapping[str, Any], key: str) -> str:
    text = str(value.get(key, "")).strip()
    if not text:
        raise LearningLabelBackfillError("text_required", f"{key} must not be empty")
    return text


def _required_nonnegative_int(value: Mapping[str, Any], key: str) -> int:
    raw = value.get(key)
    if isinstance(raw, bool):
        raise LearningLabelBackfillError("integer_required", f"{key} must be an integer")
    try:
        integer = int(raw)
    except (TypeError, ValueError) as exc:
        raise LearningLabelBackfillError("integer_required", f"{key} must be an integer") from exc
    if integer < 0 or isinstance(raw, float) and not raw.is_integer():
        raise LearningLabelBackfillError("integer_required", f"{key} must be non-negative")
    return integer


def _integer_sequence(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise LearningLabelBackfillError("integer_list_required", f"{name} must be a list")
    result = tuple(_required_nonnegative_int({"value": item}, "value") for item in value)
    if len(result) != len(set(result)):
        raise LearningLabelBackfillError("integer_list_duplicate", f"{name} contains duplicates")
    return result


def _integer_set(value: Any, name: str) -> frozenset[int]:
    return frozenset(_integer_sequence(value, name))


def _finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LearningLabelBackfillError("finite_number_required", f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise LearningLabelBackfillError("finite_number_required", f"{name} must be finite")
    return number


def _finite_nonnegative(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number < 0.0:
        raise LearningLabelBackfillError("nonnegative_number_required", f"{name} must be non-negative")
    return number


def _bounded(value: Any, name: str) -> float:
    number = _finite(value, name)
    if not 0.0 <= number <= 1.0:
        raise LearningLabelBackfillError("bounded_number_required", f"{name} must be in [0, 1]")
    return number


def _clip(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, float(value)))


def _expect_equal(actual: Any, expected: Any, name: str) -> None:
    if actual != expected:
        raise LearningLabelBackfillError("source_contract_mismatch", f"{name} mismatch")


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "D4_LABEL_SCHEMA_VERSION",
    "D5_LABEL_SCHEMA_VERSION",
    "LearningLabelBackfillConfig",
    "LearningLabelBackfillError",
    "READINESS_SCHEMA_VERSION",
    "audit_learning_label_readiness",
    "audit_learning_label_sidecar_bundle",
    "write_learning_label_readiness",
    "write_learning_label_sidecars",
]
