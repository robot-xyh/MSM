"""Canonical seed-atomic split registry for cross-module learning.

The registry is a detached, main-owned view over a frozen training-seed
registry.  It does not rewrite D3/D4/D5 datasets.  Consumers must verify the
source hash and use the same numeric-seed assignment before combining samples
from multiple modules.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Iterable, Mapping


SHARED_SEED_SPLIT_SCHEMA_VERSION = "scalable3d-shared-seed-split-registry-v1"
SHARED_SEED_SPLIT_POLICY_VERSION = "scalable3d-numeric-seed-atomic-split-v1"
TRAINING_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-training-seed-registry-v1"

# Preserve the already trained D3 development split.  D4 and D5 must consume
# this detached registry when a cross-module training view is constructed.
ORDERING_COMPATIBILITY_VERSION = "d3_numeric_seed_atomic_split_v2"
DEFAULT_SPLIT_SEED = 20260720
DEFAULT_VALIDATION_FRACTION = 0.20
DEFAULT_TEST_FRACTION = 0.20
DEFAULT_MINIMUM_TEST_SEED_COUNT = 20


class SharedSeedSplitError(ValueError):
    """Stable validation error for the shared split boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


def assign_shared_seed_splits(
    seed_values: Iterable[int],
    *,
    split_seed: int = DEFAULT_SPLIT_SEED,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    minimum_test_seed_count: int = DEFAULT_MINIMUM_TEST_SEED_COUNT,
) -> Mapping[int, str]:
    """Assign every numeric seed to exactly one deterministic split.

    The hash ordering intentionally matches D3's frozen v2 dataset policy so
    the existing D3 behavior-cloning result remains a valid development
    baseline.  The returned mapping is independent of input order and repeated
    seed values.
    """

    validation_fraction = _fraction(validation_fraction, "validation_fraction")
    test_fraction = _fraction(test_fraction, "test_fraction")
    if validation_fraction + test_fraction >= 1.0:
        raise SharedSeedSplitError(
            "split_fraction_invalid",
            "validation and test fractions must leave a non-empty train split",
        )
    minimum_test_seed_count = int(minimum_test_seed_count)
    if minimum_test_seed_count < 1:
        raise SharedSeedSplitError(
            "minimum_test_seed_count_invalid",
            "minimum test seed count must be positive",
        )
    seeds = tuple(sorted(set(int(seed) for seed in seed_values)))
    if any(seed < 0 for seed in seeds):
        raise SharedSeedSplitError(
            "negative_training_seed", "training seeds must be non-negative"
        )
    if len(seeds) < 3:
        raise SharedSeedSplitError(
            "insufficient_training_seeds",
            "at least three unique training seeds are required",
        )

    ordered = sorted(
        seeds,
        key=lambda seed: (
            hashlib.sha256(
                f"{ORDERING_COMPATIBILITY_VERSION}|{int(split_seed)}\0{seed}".encode(
                    "utf-8"
                )
            ).hexdigest(),
            seed,
        ),
    )
    test_count = max(1, min(len(seeds) - 2, round(len(seeds) * test_fraction)))
    validation_count = max(
        1,
        min(
            len(seeds) - test_count - 1,
            round(len(seeds) * validation_fraction),
        ),
    )
    if test_count < minimum_test_seed_count:
        raise SharedSeedSplitError(
            "insufficient_test_seeds",
            "canonical test split is smaller than the declared minimum",
        )
    split_by_seed = {
        seed: (
            "test"
            if index < test_count
            else "validation"
            if index < test_count + validation_count
            else "train"
        )
        for index, seed in enumerate(ordered)
    }
    return MappingProxyType(split_by_seed)


def build_shared_seed_split_registry(
    training_seed_registry: Mapping[str, Any],
    *,
    training_seed_registry_sha256: str,
    split_seed: int = DEFAULT_SPLIT_SEED,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    minimum_test_seed_count: int = DEFAULT_MINIMUM_TEST_SEED_COUNT,
) -> dict[str, Any]:
    """Build a self-hashed registry bound to a frozen seed registry."""

    source = _validate_training_seed_registry(
        training_seed_registry,
        training_seed_registry_sha256=training_seed_registry_sha256,
    )
    split_by_seed = assign_shared_seed_splits(
        source["training_seeds"],
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_test_seed_count=minimum_test_seed_count,
    )
    split_seed_values = {
        name: sorted(seed for seed, split in split_by_seed.items() if split == name)
        for name in ("train", "validation", "test")
    }
    assignments = [
        {"seed": int(seed), "split": split_by_seed[seed]}
        for seed in sorted(split_by_seed)
    ]
    assignment_sha256 = _sha256_json(assignments)
    payload: dict[str, Any] = {
        "schema_version": SHARED_SEED_SPLIT_SCHEMA_VERSION,
        "policy_version": SHARED_SEED_SPLIT_POLICY_VERSION,
        "ordering_compatibility_version": ORDERING_COMPATIBILITY_VERSION,
        "source": {
            "training_seed_registry_schema_version": source["schema_version"],
            "training_seed_registry_sha256": training_seed_registry_sha256,
            "git_commit": source["git_commit"],
            "repository_dirty": source["repository_dirty"],
            "schedule_sha256": source.get("schedule_sha256"),
        },
        "unit": "numeric_seed_atomic_across_modules_scenarios_and_scales",
        "split_seed": int(split_seed),
        "validation_fraction": float(validation_fraction),
        "test_fraction": float(test_fraction),
        "minimum_test_seed_count": int(minimum_test_seed_count),
        "training_seed_count": len(source["training_seeds"]),
        "reserved_evaluation_seed_count": len(source["reserved_evaluation_seeds"]),
        "reserved_evaluation_seeds": list(source["reserved_evaluation_seeds"]),
        "training_reserved_overlap_count": 0,
        "split_seed_values": split_seed_values,
        "assignments": assignments,
        "assignment_sha256": assignment_sha256,
        "consumer_contract": {
            "original_dataset_mutation_allowed": False,
            "module_local_split_override_allowed": False,
            "cross_module_training_requires_exact_registry": True,
            "reserved_evaluation_seeds_allowed": False,
        },
    }
    payload["content_sha256"] = _sha256_json(payload)
    return payload


def load_shared_seed_split_registry(
    registry_path: str | Path,
    *,
    training_seed_registry_path: str | Path,
) -> dict[str, Any]:
    """Load and fully reproduce a detached registry from its source."""

    registry_file = Path(registry_path)
    source_file = Path(training_seed_registry_path)
    registry = _read_json_object(registry_file)
    source = _read_json_object(source_file)
    expected = build_shared_seed_split_registry(
        source,
        training_seed_registry_sha256=_sha256_file(source_file),
        split_seed=_integer(registry.get("split_seed"), "split_seed"),
        validation_fraction=_number(
            registry.get("validation_fraction"), "validation_fraction"
        ),
        test_fraction=_number(registry.get("test_fraction"), "test_fraction"),
        minimum_test_seed_count=_integer(
            registry.get("minimum_test_seed_count"), "minimum_test_seed_count"
        ),
    )
    if registry != expected:
        raise SharedSeedSplitError(
            "registry_reproduction_mismatch",
            "shared seed split registry does not reproduce from its frozen source",
        )
    return registry


def write_shared_seed_split_registry(
    training_seed_registry_path: str | Path,
    output_path: str | Path,
    *,
    split_seed: int = DEFAULT_SPLIT_SEED,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
    minimum_test_seed_count: int = DEFAULT_MINIMUM_TEST_SEED_COUNT,
) -> dict[str, Any]:
    """Atomically write a detached registry and verify its round trip."""

    source_file = Path(training_seed_registry_path).resolve()
    output_file = Path(output_path).resolve()
    if output_file == source_file:
        raise SharedSeedSplitError(
            "source_mutation_forbidden", "output must not replace the source registry"
        )
    source = _read_json_object(source_file)
    payload = build_shared_seed_split_registry(
        source,
        training_seed_registry_sha256=_sha256_file(source_file),
        split_seed=split_seed,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
        minimum_test_seed_count=minimum_test_seed_count,
    )
    if output_file.exists():
        current = load_shared_seed_split_registry(
            output_file, training_seed_registry_path=source_file
        )
        if current != payload:
            raise SharedSeedSplitError(
                "existing_registry_conflict",
                "existing shared split registry uses a different policy",
            )
        return current
    output_file.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json_bytes(payload) + b"\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output_file.name}.", suffix=".tmp", dir=str(output_file.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_file)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return load_shared_seed_split_registry(
        output_file, training_seed_registry_path=source_file
    )


def _validate_training_seed_registry(
    value: Mapping[str, Any],
    *,
    training_seed_registry_sha256: str,
) -> dict[str, Any]:
    if value.get("schema_version") != TRAINING_SEED_REGISTRY_SCHEMA_VERSION:
        raise SharedSeedSplitError(
            "source_schema_mismatch", "unsupported training seed registry schema"
        )
    _sha256(training_seed_registry_sha256, "training_seed_registry_sha256")
    training = tuple(sorted(set(_integer(seed, "training_seed") for seed in value.get("training_seeds", ()))))
    reserved = tuple(
        sorted(
            set(
                _integer(seed, "reserved_evaluation_seed")
                for seed in value.get("reserved_evaluation_seeds", ())
            )
        )
    )
    if not training:
        raise SharedSeedSplitError(
            "training_seed_catalog_empty", "training seed registry is empty"
        )
    if any(seed < 0 for seed in (*training, *reserved)):
        raise SharedSeedSplitError(
            "negative_seed", "training and reserved seeds must be non-negative"
        )
    if len(training) != _integer(value.get("training_seed_count"), "training_seed_count"):
        raise SharedSeedSplitError(
            "training_seed_count_mismatch", "training seed count does not match catalog"
        )
    if len(reserved) != _integer(
        value.get("reserved_evaluation_seed_count"),
        "reserved_evaluation_seed_count",
    ):
        raise SharedSeedSplitError(
            "reserved_seed_count_mismatch", "reserved seed count does not match catalog"
        )
    overlap = sorted(set(training) & set(reserved))
    if overlap or _integer(value.get("overlap_count"), "overlap_count") != 0:
        raise SharedSeedSplitError(
            "training_reserved_seed_overlap",
            f"training and reserved evaluation seeds overlap: {overlap}",
        )
    commit = str(value.get("git_commit", ""))
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise SharedSeedSplitError("git_commit_invalid", "source Git commit is invalid")
    dirty = value.get("repository_dirty")
    if not isinstance(dirty, bool):
        raise SharedSeedSplitError(
            "repository_dirty_invalid", "repository_dirty must be boolean"
        )
    schedule_sha256 = value.get("schedule_sha256")
    if schedule_sha256 is not None:
        _sha256(schedule_sha256, "schedule_sha256")
    return {
        "schema_version": TRAINING_SEED_REGISTRY_SCHEMA_VERSION,
        "git_commit": commit,
        "repository_dirty": dirty,
        "schedule_sha256": schedule_sha256,
        "training_seeds": training,
        "reserved_evaluation_seeds": reserved,
    }


def _fraction(value: Any, name: str) -> float:
    number = _number(value, name)
    if not 0.0 < number < 1.0:
        raise SharedSeedSplitError(
            "split_fraction_invalid", f"{name} must be in (0, 1)"
        )
    return number


def _number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SharedSeedSplitError("number_invalid", f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise SharedSeedSplitError("number_invalid", f"{name} must be finite")
    return number


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise SharedSeedSplitError("integer_invalid", f"{name} must be an integer")
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise SharedSeedSplitError("integer_invalid", f"{name} must be an integer") from exc
    if value != integer:
        raise SharedSeedSplitError("integer_invalid", f"{name} must be an integer")
    return integer


def _sha256(value: Any, name: str) -> str:
    text = str(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise SharedSeedSplitError("sha256_invalid", f"{name} must be lowercase SHA-256")
    return text


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SharedSeedSplitError(
            "json_read_failed", f"cannot read JSON object: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise SharedSeedSplitError("json_object_required", f"JSON object required: {path}")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
