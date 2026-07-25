"""Versioned immutable contract for shared publication audit metadata.

The contract deliberately uses immutable built-in bases instead of ``dict`` or
``list`` subclasses: mappings hold key/value pairs in a ``frozenset`` and
sequences use a ``tuple``.  A consumer can therefore validate one shared tree
and reuse that result by object identity without accepting arbitrary
``Mapping`` implementations or mutable backing stores.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
import math
from typing import Any, Iterator

import numpy as np


PUBLICATION_AUDIT_TREE_CONTRACT_VERSION = "d1.publication_audit_tree.v2"
PUBLICATION_METADATA_REFERENCE_IMPLEMENTATION_ID = (
    "d1.publication_metadata.per_track_audit_copy.v1"
)
PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID = (
    "d1.publication_metadata.immutable_shared_audit.v2"
)

_IMMUTABLE_SCALAR_TYPES = (type(None), bool, int, float, str)


class PublicationAuditContractError(TypeError):
    """Raised when a value is outside the immutable publication contract."""


class ImmutablePublicationAuditMap(frozenset, Mapping[str, Any]):
    """Frozenset-backed mapping used by the v2 publication audit contract.

    The raw frozenset contains ``(str, value)`` pairs.  The type has no instance
    dictionary or writable slots, and no mutable base-class storage exists.
    Exact recursive validation remains mandatory because callers can invoke
    ``frozenset.__new__`` directly to construct malformed instances.
    """

    __slots__ = ()
    __hash__ = frozenset.__hash__

    def __new__(
        cls,
        entries: object = (),
    ) -> "ImmutablePublicationAuditMap":
        return frozenset.__new__(cls, entries)  # type: ignore[arg-type]

    def __iter__(self) -> Iterator[str]:
        return (
            pair[0]
            for pair in frozenset.__iter__(self)
        )

    def __getitem__(self, key: str) -> Any:
        for candidate_key, value in frozenset.__iter__(self):
            if candidate_key == key:
                return value
        raise KeyError(key)

    def keys(self) -> Iterator[str]:
        return iter(self)

    def items(self) -> Iterator[tuple[str, Any]]:
        return frozenset.__iter__(self)

    def values(self) -> Iterator[Any]:
        return (
            pair[1]
            for pair in frozenset.__iter__(self)
        )

    def __copy__(self) -> "ImmutablePublicationAuditMap":
        return self

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "ImmutablePublicationAuditMap":
        memo[id(self)] = self
        return self

    def __reduce_ex__(self, protocol: int) -> tuple[object, tuple[object, ...]]:
        del protocol
        entries = tuple(frozenset.__iter__(self))
        return (ImmutablePublicationAuditMap, (entries,))

    @staticmethod
    def _reject_mutation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("shared publication audit metadata is immutable")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    clear = _reject_mutation
    pop = _reject_mutation
    popitem = _reject_mutation
    setdefault = _reject_mutation
    update = _reject_mutation
    __ior__ = _reject_mutation

    def __eq__(self, other: object) -> bool:
        if type(other) is ImmutablePublicationAuditMap:
            return frozenset.__eq__(self, other)
        if not isinstance(other, Mapping) or len(self) != len(other):
            return False
        try:
            return all(
                key in other and value == other[key]
                for key, value in frozenset.__iter__(self)
            )
        except (KeyError, TypeError, ValueError):
            return False

    def __repr__(self) -> str:
        return (
            "ImmutablePublicationAuditMap("
            f"{publication_audit_to_builtin(self)!r})"
        )


class ImmutablePublicationAuditSequence(tuple):
    """Tuple-backed JSON-array value used by the v2 audit contract."""

    __slots__ = ()
    __hash__ = tuple.__hash__

    def __new__(
        cls,
        values: object = (),
    ) -> "ImmutablePublicationAuditSequence":
        return tuple.__new__(cls, tuple(values))  # type: ignore[arg-type]

    def __copy__(self) -> "ImmutablePublicationAuditSequence":
        return self

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "ImmutablePublicationAuditSequence":
        memo[id(self)] = self
        return self

    def __reduce_ex__(self, protocol: int) -> tuple[object, tuple[object, ...]]:
        del protocol
        values = tuple(tuple.__iter__(self))
        return (ImmutablePublicationAuditSequence, (values,))

    @staticmethod
    def _reject_mutation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("shared publication audit metadata is immutable")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    __iadd__ = _reject_mutation
    __imul__ = _reject_mutation
    append = _reject_mutation
    clear = _reject_mutation
    extend = _reject_mutation
    insert = _reject_mutation
    pop = _reject_mutation
    remove = _reject_mutation
    reverse = _reject_mutation
    sort = _reject_mutation

    def __eq__(self, other: object) -> bool:
        if type(other) is ImmutablePublicationAuditSequence:
            return tuple.__eq__(self, other)
        if type(other) not in (list, tuple):
            return False
        return len(self) == len(other) and all(
            left == right
            for left, right in zip(tuple.__iter__(self), other, strict=True)
        )

    def __repr__(self) -> str:
        return (
            "ImmutablePublicationAuditSequence("
            f"{publication_audit_to_builtin(self)!r})"
        )


@dataclass(frozen=True, slots=True)
class PublicationAuditContractVerification:
    """Result of an exact recursive v2 contract verification."""

    contract_version: str
    mapping_count: int
    sequence_count: int
    scalar_count: int

    @property
    def node_count(self) -> int:
        return self.mapping_count + self.sequence_count + self.scalar_count


def freeze_publication_audit_tree(
    value: object,
    operation_counts: MutableMapping[str, int] | None = None,
) -> ImmutablePublicationAuditMap:
    """Freeze one built-in JSON-like mapping into the v2 exact contract.

    Only exact built-in ``dict``, ``list`` and ``tuple`` containers are
    accepted as input.  NumPy arrays are copied through ``tolist()`` and become
    immutable sequences.  Custom mappings, container subclasses, cycles,
    non-string mapping keys, non-finite floats and unsupported leaves fail
    closed.
    """

    if type(value) is not dict:
        raise PublicationAuditContractError(
            "publication audit root must be an exact built-in dict"
        )

    active_source_ids: set[int] = set()
    frozen_by_source_id: dict[int, object] = {}

    def increment(name: str, amount: int = 1) -> None:
        if operation_counts is not None:
            operation_counts[name] = (
                int(operation_counts.get(name, 0)) + amount
            )

    def freeze_nested(nested: object, path: str) -> object:
        nested_type = type(nested)
        if nested_type in _IMMUTABLE_SCALAR_TYPES:
            if nested_type is float and not math.isfinite(nested):
                raise PublicationAuditContractError(
                    f"{path} contains a non-finite float"
                )
            increment("immutable_shared_scalar_reuse_count")
            return nested

        if nested_type is np.ndarray:
            source_id = id(nested)
            if source_id in active_source_ids:
                raise PublicationAuditContractError(
                    f"{path} contains a cyclic NumPy array"
                )
            if source_id in frozen_by_source_id:
                increment("immutable_shared_source_identity_reuse_count")
                return frozen_by_source_id[source_id]
            active_source_ids.add(source_id)
            increment("immutable_shared_array_build_count")
            try:
                frozen = freeze_nested(nested.tolist(), path)
            finally:
                active_source_ids.remove(source_id)
            frozen_by_source_id[source_id] = frozen
            return frozen

        if nested_type is dict:
            source_id = id(nested)
            if source_id in active_source_ids:
                raise PublicationAuditContractError(
                    f"{path} contains a cyclic mapping"
                )
            if source_id in frozen_by_source_id:
                increment("immutable_shared_source_identity_reuse_count")
                return frozen_by_source_id[source_id]
            active_source_ids.add(source_id)
            increment("immutable_shared_mapping_build_count")
            entries: list[tuple[str, object]] = []
            try:
                for key, child in nested.items():
                    if type(key) is not str:
                        raise PublicationAuditContractError(
                            f"{path} contains a non-string mapping key"
                        )
                    entries.append(
                        (
                            key,
                            freeze_nested(child, f"{path}.{key}"),
                        )
                    )
            finally:
                active_source_ids.remove(source_id)
            frozen = ImmutablePublicationAuditMap(entries)
            frozen_by_source_id[source_id] = frozen
            return frozen

        if nested_type in (list, tuple):
            source_id = id(nested)
            if source_id in active_source_ids:
                raise PublicationAuditContractError(
                    f"{path} contains a cyclic sequence"
                )
            if source_id in frozen_by_source_id:
                increment("immutable_shared_source_identity_reuse_count")
                return frozen_by_source_id[source_id]
            active_source_ids.add(source_id)
            if nested_type is list:
                increment("immutable_shared_list_build_count")
            else:
                increment("immutable_shared_tuple_build_count")
            try:
                frozen = ImmutablePublicationAuditSequence(
                    freeze_nested(child, f"{path}[{index}]")
                    for index, child in enumerate(nested)
                )
            finally:
                active_source_ids.remove(source_id)
            frozen_by_source_id[source_id] = frozen
            return frozen

        raise PublicationAuditContractError(
            f"{path} contains unsupported leaf/container type "
            f"{nested_type.__module__}.{nested_type.__qualname__}"
        )

    frozen_root = freeze_nested(value, "$")
    if type(frozen_root) is not ImmutablePublicationAuditMap:
        raise PublicationAuditContractError(
            "publication audit freeze did not produce an immutable mapping"
        )
    verification = validate_immutable_publication_audit_tree(frozen_root)
    increment("immutable_shared_contract_validation_count")
    increment(
        "immutable_shared_contract_validated_node_count",
        verification.node_count,
    )
    return frozen_root


def validate_immutable_publication_audit_tree(
    value: object,
) -> PublicationAuditContractVerification:
    """Validate an exact recursively immutable v2 audit mapping.

    This function does not certify that the content is truth-free.  A downstream
    consumer must still run its content policy once, then it may reuse that
    result only for the same validated object identity.
    """

    if type(value) is not ImmutablePublicationAuditMap:
        raise PublicationAuditContractError(
            "publication audit root is not the exact v2 immutable mapping type"
        )

    active_ids: set[int] = set()
    mapping_count = 0
    sequence_count = 0
    scalar_count = 0

    def validate_nested(nested: object, path: str) -> None:
        nonlocal mapping_count, sequence_count, scalar_count
        nested_type = type(nested)
        if nested_type in _IMMUTABLE_SCALAR_TYPES:
            if nested_type is float and not math.isfinite(nested):
                raise PublicationAuditContractError(
                    f"{path} contains a non-finite float"
                )
            scalar_count += 1
            return

        if nested_type is ImmutablePublicationAuditMap:
            nested_id = id(nested)
            if nested_id in active_ids:
                raise PublicationAuditContractError(
                    f"{path} contains a cyclic immutable mapping"
                )
            active_ids.add(nested_id)
            mapping_count += 1
            keys: set[str] = set()
            try:
                for index, pair in enumerate(frozenset.__iter__(nested)):
                    if type(pair) is not tuple or len(pair) != 2:
                        raise PublicationAuditContractError(
                            f"{path}[{index}] is not an exact key/value tuple"
                        )
                    key = tuple.__getitem__(pair, 0)
                    child = tuple.__getitem__(pair, 1)
                    if type(key) is not str:
                        raise PublicationAuditContractError(
                            f"{path}[{index}] has a non-string key"
                        )
                    if key in keys:
                        raise PublicationAuditContractError(
                            f"{path} contains duplicate key {key!r}"
                        )
                    keys.add(key)
                    validate_nested(child, f"{path}.{key}")
            finally:
                active_ids.remove(nested_id)
            return

        if nested_type is ImmutablePublicationAuditSequence:
            nested_id = id(nested)
            if nested_id in active_ids:
                raise PublicationAuditContractError(
                    f"{path} contains a cyclic immutable sequence"
                )
            active_ids.add(nested_id)
            sequence_count += 1
            try:
                for index, child in enumerate(tuple.__iter__(nested)):
                    validate_nested(child, f"{path}[{index}]")
            finally:
                active_ids.remove(nested_id)
            return

        raise PublicationAuditContractError(
            f"{path} contains non-contract type "
            f"{nested_type.__module__}.{nested_type.__qualname__}"
        )

    validate_nested(value, "$")
    return PublicationAuditContractVerification(
        contract_version=PUBLICATION_AUDIT_TREE_CONTRACT_VERSION,
        mapping_count=mapping_count,
        sequence_count=sequence_count,
        scalar_count=scalar_count,
    )


def is_immutable_publication_audit_tree(value: object) -> bool:
    """Return whether ``value`` satisfies the exact recursive v2 contract."""

    try:
        validate_immutable_publication_audit_tree(value)
    except PublicationAuditContractError:
        return False
    return True


def publication_audit_to_builtin(value: object) -> object:
    """Convert contract containers to JSON-compatible built-in containers."""

    value_type = type(value)
    if value_type is ImmutablePublicationAuditMap:
        return {
            key: publication_audit_to_builtin(nested)
            for key, nested in frozenset.__iter__(value)
        }
    if value_type is ImmutablePublicationAuditSequence:
        return [
            publication_audit_to_builtin(nested)
            for nested in tuple.__iter__(value)
        ]
    if value_type is dict:
        return {
            key: publication_audit_to_builtin(nested)
            for key, nested in value.items()
        }
    if value_type is list:
        return [
            publication_audit_to_builtin(nested)
            for nested in value
        ]
    if value_type is tuple:
        return tuple(
            publication_audit_to_builtin(nested)
            for nested in value
        )
    return value
