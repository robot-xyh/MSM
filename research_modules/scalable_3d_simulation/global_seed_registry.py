"""Main-owned seed allocation registry for scalable learning experiments.

The registry reserves numeric episode seeds before any module creates data.
It is intentionally independent of module-local split manifests: D3, D4 and
D5 may define different sample schemas, but they must not silently reuse the
same source seed or a protected formal-evaluation seed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


GLOBAL_SEED_REGISTRY_SCHEMA_VERSION = "scalable3d-global-seed-registry-v1"
GLOBAL_SEED_REGISTRY_POLICY_VERSION = "scalable3d-seed-allocation-policy-v1"
PROTECTED_FORMAL_EVALUATION_SEEDS = frozenset(range(1000, 1020))

_ALLOCATION_LIFECYCLES = frozenset({"reserved", "active", "retired"})
_USAGE_CLASSES = frozenset(
    {
        "train_only",
        "train_validation_test",
        "validation_only",
        "test_only",
        "diagnostic_only",
    }
)
_OPERATIONS = frozenset(
    {
        "dataset_generation",
        "training",
        "validation",
        "test",
        "diagnostic_replay",
    }
)


class GlobalSeedRegistryError(ValueError):
    """Stable fail-closed error at the main seed-allocation boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


@dataclass(frozen=True)
class SeedAllocation:
    allocation_id: str
    owner: str
    candidate_version: str
    lifecycle: str
    usage_class: str
    split_policy: str
    permitted_operations: tuple[str, ...]
    seeds: tuple[int, ...]
    source_contract: Mapping[str, Any]


@dataclass(frozen=True)
class GlobalSeedRegistry:
    registry_id: str
    policy_version: str
    protected_seeds: frozenset[int]
    protected_set_ids: tuple[str, ...]
    allocations: Mapping[str, SeedAllocation]
    unallocated_requests: tuple[Mapping[str, Any], ...]
    content_sha256: str
    source_path: Path | None = None

    def allocation(self, allocation_id: str) -> SeedAllocation:
        key = str(allocation_id).strip()
        try:
            return self.allocations[key]
        except KeyError as exc:
            raise GlobalSeedRegistryError(
                "allocation_unknown",
                f"global seed allocation is not registered: {key}",
            ) from exc


def build_global_seed_registry(payload: Mapping[str, Any]) -> GlobalSeedRegistry:
    """Validate a decoded registry and return an immutable typed view."""

    if not isinstance(payload, Mapping):
        raise GlobalSeedRegistryError(
            "registry_not_object", "global seed registry must be a JSON object"
        )
    if payload.get("schema_version") != GLOBAL_SEED_REGISTRY_SCHEMA_VERSION:
        raise GlobalSeedRegistryError(
            "schema_version_unsupported",
            "unsupported global seed registry schema version",
        )
    policy_version = _nonempty_string(payload.get("policy_version"), "policy_version")
    if policy_version != GLOBAL_SEED_REGISTRY_POLICY_VERSION:
        raise GlobalSeedRegistryError(
            "policy_version_unsupported",
            "unsupported global seed registry policy version",
        )
    registry_id = _nonempty_string(payload.get("registry_id"), "registry_id")
    declared_hash = _sha256_string(payload.get("content_sha256"), "content_sha256")
    expected_hash = registry_content_sha256(payload)
    if declared_hash != expected_hash:
        raise GlobalSeedRegistryError(
            "content_hash_mismatch",
            "global seed registry content hash does not reproduce",
        )

    protected_sets = _object_list(payload.get("protected_seed_sets"), "protected_seed_sets")
    if not protected_sets:
        raise GlobalSeedRegistryError(
            "protected_seed_sets_empty", "at least one protected seed set is required"
        )
    protected_ids: list[str] = []
    protected_owner: dict[int, str] = {}
    for raw in protected_sets:
        set_id = _nonempty_string(raw.get("set_id"), "protected set_id")
        if set_id in protected_ids:
            raise GlobalSeedRegistryError(
                "protected_set_id_duplicate", f"duplicate protected set_id: {set_id}"
            )
        protected_ids.append(set_id)
        seeds = _seed_tuple(raw.get("seeds"), f"protected set {set_id} seeds")
        if raw.get("dataset_generation_allowed") is not False:
            raise GlobalSeedRegistryError(
                "protected_generation_policy_invalid",
                f"protected set {set_id} must forbid dataset generation",
            )
        for seed in seeds:
            previous = protected_owner.get(seed)
            if previous is not None:
                raise GlobalSeedRegistryError(
                    "protected_seed_overlap",
                    f"seed {seed} occurs in protected sets {previous} and {set_id}",
                )
            protected_owner[seed] = set_id

    missing_formal = sorted(PROTECTED_FORMAL_EVALUATION_SEEDS - set(protected_owner))
    if missing_formal:
        raise GlobalSeedRegistryError(
            "formal_evaluation_seed_unprotected",
            f"formal evaluation seeds are not protected: {missing_formal}",
        )

    raw_allocations = _object_list(payload.get("allocations"), "allocations")
    allocations: dict[str, SeedAllocation] = {}
    allocated_owner: dict[int, str] = {}
    for raw in raw_allocations:
        allocation_id = _nonempty_string(raw.get("allocation_id"), "allocation_id")
        if allocation_id in allocations:
            raise GlobalSeedRegistryError(
                "allocation_id_duplicate", f"duplicate allocation_id: {allocation_id}"
            )
        owner = _nonempty_string(raw.get("owner"), "allocation owner")
        candidate_version = _nonempty_string(
            raw.get("candidate_version"), "candidate_version"
        )
        lifecycle = _nonempty_string(raw.get("lifecycle"), "allocation lifecycle")
        if lifecycle not in _ALLOCATION_LIFECYCLES:
            raise GlobalSeedRegistryError(
                "allocation_lifecycle_invalid",
                f"unsupported lifecycle for {allocation_id}: {lifecycle}",
            )
        usage_class = _nonempty_string(raw.get("usage_class"), "usage_class")
        if usage_class not in _USAGE_CLASSES:
            raise GlobalSeedRegistryError(
                "allocation_usage_invalid",
                f"unsupported usage class for {allocation_id}: {usage_class}",
            )
        split_policy = _nonempty_string(raw.get("split_policy"), "split_policy")
        operations = _string_tuple(
            raw.get("permitted_operations"),
            f"allocation {allocation_id} permitted_operations",
        )
        invalid_operations = sorted(set(operations) - _OPERATIONS)
        if invalid_operations:
            raise GlobalSeedRegistryError(
                "allocation_operation_invalid",
                f"unsupported operations for {allocation_id}: {invalid_operations}",
            )
        seeds = _seed_tuple(raw.get("seeds"), f"allocation {allocation_id} seeds")
        declared_count = _integer(raw.get("seed_count"), "seed_count")
        if declared_count != len(seeds):
            raise GlobalSeedRegistryError(
                "allocation_seed_count_mismatch",
                f"allocation {allocation_id} declares {declared_count} seeds but contains {len(seeds)}",
            )
        overlap = sorted(set(seeds) & set(protected_owner))
        if overlap:
            raise GlobalSeedRegistryError(
                "allocation_uses_protected_seed",
                f"allocation {allocation_id} uses protected seeds: {overlap}",
            )
        for seed in seeds:
            previous = allocated_owner.get(seed)
            if previous is not None:
                raise GlobalSeedRegistryError(
                    "allocation_seed_overlap",
                    f"seed {seed} occurs in allocations {previous} and {allocation_id}",
                )
            allocated_owner[seed] = allocation_id
        source_contract = raw.get("source_contract", {})
        if not isinstance(source_contract, Mapping):
            raise GlobalSeedRegistryError(
                "source_contract_not_object",
                f"allocation {allocation_id} source_contract must be an object",
            )
        allocations[allocation_id] = SeedAllocation(
            allocation_id=allocation_id,
            owner=owner,
            candidate_version=candidate_version,
            lifecycle=lifecycle,
            usage_class=usage_class,
            split_policy=split_policy,
            permitted_operations=operations,
            seeds=seeds,
            source_contract=MappingProxyType(dict(source_contract)),
        )

    raw_requests = _object_list(
        payload.get("unallocated_requests", []), "unallocated_requests"
    )
    requests: list[Mapping[str, Any]] = []
    request_ids: set[str] = set()
    for raw in raw_requests:
        request_id = _nonempty_string(raw.get("request_id"), "request_id")
        if request_id in request_ids:
            raise GlobalSeedRegistryError(
                "request_id_duplicate", f"duplicate unallocated request_id: {request_id}"
            )
        request_ids.add(request_id)
        if "seeds" in raw or "seed_range" in raw:
            raise GlobalSeedRegistryError(
                "unallocated_request_contains_seeds",
                f"unallocated request {request_id} must not reserve seeds implicitly",
            )
        requested_count = _integer(raw.get("requested_seed_count"), "requested_seed_count")
        if requested_count < 1:
            raise GlobalSeedRegistryError(
                "requested_seed_count_invalid",
                f"unallocated request {request_id} must request a positive count",
            )
        requests.append(MappingProxyType(dict(raw)))

    return GlobalSeedRegistry(
        registry_id=registry_id,
        policy_version=policy_version,
        protected_seeds=frozenset(protected_owner),
        protected_set_ids=tuple(protected_ids),
        allocations=MappingProxyType(dict(allocations)),
        unallocated_requests=tuple(requests),
        content_sha256=declared_hash,
    )


def load_global_seed_registry(path: str | Path) -> GlobalSeedRegistry:
    """Load and validate one versioned global registry from disk."""

    source = Path(path).resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GlobalSeedRegistryError(
            "registry_read_failed", f"unable to read global seed registry: {source}"
        ) from exc
    registry = build_global_seed_registry(payload)
    return GlobalSeedRegistry(
        registry_id=registry.registry_id,
        policy_version=registry.policy_version,
        protected_seeds=registry.protected_seeds,
        protected_set_ids=registry.protected_set_ids,
        allocations=registry.allocations,
        unallocated_requests=registry.unallocated_requests,
        content_sha256=registry.content_sha256,
        source_path=source,
    )


def validate_seed_request(
    registry: GlobalSeedRegistry,
    *,
    allocation_id: str,
    seeds: Iterable[int],
    operation: str,
    require_exact_allocation: bool = True,
) -> dict[str, Any]:
    """Authorize one explicit seed use and return frozen provenance."""

    allocation = registry.allocation(allocation_id)
    requested = _normalized_seed_tuple(seeds, "requested seeds")
    operation = _nonempty_string(operation, "operation")
    if operation not in allocation.permitted_operations:
        raise GlobalSeedRegistryError(
            "operation_not_permitted",
            f"operation {operation} is not permitted by allocation {allocation_id}",
        )
    if allocation.lifecycle == "retired":
        raise GlobalSeedRegistryError(
            "allocation_retired", f"allocation {allocation_id} is retired"
        )
    protected_overlap = sorted(set(requested) & registry.protected_seeds)
    if protected_overlap:
        raise GlobalSeedRegistryError(
            "request_uses_protected_seed",
            f"requested seeds include protected values: {protected_overlap}",
        )
    undeclared = sorted(set(requested) - set(allocation.seeds))
    if undeclared:
        raise GlobalSeedRegistryError(
            "request_uses_unallocated_seed",
            f"requested seeds are outside allocation {allocation_id}: {undeclared}",
        )
    exact_match = requested == allocation.seeds
    if require_exact_allocation and not exact_match:
        missing = sorted(set(allocation.seeds) - set(requested))
        raise GlobalSeedRegistryError(
            "request_not_exact_allocation",
            f"requested seed set does not exactly match {allocation_id}; missing={missing}",
        )
    return {
        "schema_version": GLOBAL_SEED_REGISTRY_SCHEMA_VERSION,
        "registry_id": registry.registry_id,
        "registry_content_sha256": registry.content_sha256,
        "allocation_id": allocation.allocation_id,
        "owner": allocation.owner,
        "candidate_version": allocation.candidate_version,
        "lifecycle": allocation.lifecycle,
        "usage_class": allocation.usage_class,
        "split_policy": allocation.split_policy,
        "operation": operation,
        "requested_seed_count": len(requested),
        "exact_allocation_match": exact_match,
        "protected_seed_overlap_count": 0,
        "source_contract": dict(allocation.source_contract),
    }


def registry_content_sha256(payload: Mapping[str, Any]) -> str:
    """Hash canonical registry content while excluding its self-hash field."""

    content = dict(payload)
    content.pop("content_sha256", None)
    encoded = json.dumps(
        content,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _object_list(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list):
        raise GlobalSeedRegistryError(f"{name}_not_list", f"{name} must be a list")
    if any(not isinstance(item, Mapping) for item in value):
        raise GlobalSeedRegistryError(
            f"{name}_item_not_object", f"every {name} item must be an object"
        )
    return tuple(value)


def _seed_tuple(value: Any, name: str) -> tuple[int, ...]:
    seeds = _normalized_seed_tuple(value, name)
    if not seeds:
        raise GlobalSeedRegistryError(f"{name}_empty", f"{name} must not be empty")
    if list(value) != list(seeds):
        raise GlobalSeedRegistryError(
            f"{name}_not_canonical",
            f"{name} must be strictly increasing with no duplicates",
        )
    return seeds


def _normalized_seed_tuple(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise GlobalSeedRegistryError(f"{name}_not_sequence", f"{name} must be a sequence")
    seeds: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise GlobalSeedRegistryError(
                f"{name}_invalid", f"{name} must contain non-negative integers"
            )
        seeds.add(int(item))
    return tuple(sorted(seeds))


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GlobalSeedRegistryError(f"{name}_invalid", f"{name} must be a non-empty list")
    items = tuple(_nonempty_string(item, name) for item in value)
    if len(items) != len(set(items)):
        raise GlobalSeedRegistryError(f"{name}_duplicate", f"{name} contains duplicates")
    return items


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GlobalSeedRegistryError(f"{name}_invalid", f"{name} must be a non-empty string")
    return value.strip()


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GlobalSeedRegistryError(f"{name}_invalid", f"{name} must be an integer")
    return int(value)


def _sha256_string(value: Any, name: str) -> str:
    text = _nonempty_string(value, name).lower()
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise GlobalSeedRegistryError(f"{name}_invalid", f"{name} must be a SHA-256 hex digest")
    return text
