from __future__ import annotations

from collections import Counter, UserDict
import copy
import json
import pickle
from types import MappingProxyType

import numpy as np
import pytest

from d1_sensor_fusion import (
    PUBLICATION_AUDIT_TREE_CONTRACT_VERSION,
    PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID,
    ImmutablePublicationAuditMap,
    ImmutablePublicationAuditSequence,
    PublicationAuditContractError,
    freeze_publication_audit_tree,
    is_immutable_publication_audit_tree,
    publication_audit_to_builtin,
    validate_immutable_publication_audit_tree,
)


def _contract_tree() -> ImmutablePublicationAuditMap:
    return freeze_publication_audit_tree(
        {
            "schema_version": "d1.association_audit.v1",
            "nested": {
                "flags": [True, False, None],
                "thresholds": (1, 2.5),
            },
            "matrix": np.asarray([[1.0, 2.0], [3.0, 4.0]]),
        }
    )


def test_freeze_builds_exact_versioned_contract_and_builtin_payload() -> None:
    counts: Counter[str] = Counter()
    frozen = freeze_publication_audit_tree(
        {
            "schema_version": "d1.association_audit.v1",
            "nested": {"flags": [True, False, None]},
            "tuple_value": ("a", 2),
        },
        counts,
    )

    verification = validate_immutable_publication_audit_tree(frozen)
    assert type(frozen) is ImmutablePublicationAuditMap
    assert type(frozen["nested"]) is ImmutablePublicationAuditMap
    assert type(frozen["nested"]["flags"]) is ImmutablePublicationAuditSequence
    assert verification.contract_version == PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
    assert verification.mapping_count == 2
    assert verification.sequence_count == 2
    assert verification.scalar_count == 6
    assert verification.node_count == 10
    assert is_immutable_publication_audit_tree(frozen) is True

    builtin = publication_audit_to_builtin(frozen)
    assert type(builtin) is dict
    assert type(builtin["nested"]) is dict
    assert type(builtin["nested"]["flags"]) is list
    assert json.loads(json.dumps(builtin, allow_nan=False)) == builtin
    with pytest.raises(TypeError, match="not JSON serializable"):
        json.dumps(frozen)
    assert counts["immutable_shared_contract_validation_count"] == 1
    assert (
        counts["immutable_shared_contract_validated_node_count"]
        == verification.node_count
    )
    assert PUBLICATION_METADATA_CANDIDATE_IMPLEMENTATION_ID.endswith(
        "immutable_shared_audit.v2"
    )


def test_contract_copy_pickle_and_equality_preserve_safe_semantics() -> None:
    frozen = _contract_tree()
    assert copy.copy(frozen) is frozen
    assert copy.deepcopy(frozen) is frozen
    assert frozen == {
        "schema_version": "d1.association_audit.v1",
        "nested": {
            "flags": [True, False, None],
            "thresholds": (1, 2.5),
        },
        "matrix": [[1.0, 2.0], [3.0, 4.0]],
    }

    restored = pickle.loads(pickle.dumps(frozen))
    assert type(restored) is ImmutablePublicationAuditMap
    assert restored == frozen
    assert validate_immutable_publication_audit_tree(restored).node_count > 0
    json.dumps(publication_audit_to_builtin(restored), allow_nan=False)


@pytest.mark.parametrize(
    ("method_name", "arguments"),
    (
        ("clear", ()),
        ("pop", ("schema_version",)),
        ("popitem", ()),
        ("setdefault", ("new", 1)),
        ("update", ({"new": 1},)),
    ),
)
def test_mapping_public_mutators_fail_closed(
    method_name: str,
    arguments: tuple[object, ...],
) -> None:
    frozen = _contract_tree()
    with pytest.raises(TypeError, match="immutable"):
        getattr(frozen, method_name)(*arguments)
    assert validate_immutable_publication_audit_tree(frozen).node_count > 0


def test_mapping_item_mutators_and_base_class_bypass_fail_closed() -> None:
    frozen = _contract_tree()
    with pytest.raises(TypeError, match="immutable"):
        frozen["new"] = 1
    with pytest.raises(TypeError, match="immutable"):
        del frozen["schema_version"]
    with pytest.raises(TypeError, match="immutable"):
        frozen |= {"new": 1}
    with pytest.raises(TypeError):
        dict.__setitem__(frozen, "new", 1)
    with pytest.raises(TypeError):
        dict.update(frozen, {"new": 1})
    with pytest.raises(TypeError):
        set.add(frozen, ("new", 1))
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(frozen, "backing", {"mutable": True})
    assert "new" not in frozen


@pytest.mark.parametrize(
    ("method_name", "arguments"),
    (
        ("append", (3,)),
        ("clear", ()),
        ("extend", ([3],)),
        ("insert", (0, 3)),
        ("pop", ()),
        ("remove", (1,)),
        ("reverse", ()),
        ("sort", ()),
    ),
)
def test_sequence_public_mutators_fail_closed(
    method_name: str,
    arguments: tuple[object, ...],
) -> None:
    sequence = freeze_publication_audit_tree({"items": [1, 2]})["items"]
    with pytest.raises(TypeError, match="immutable"):
        getattr(sequence, method_name)(*arguments)
    assert sequence == [1, 2]


def test_sequence_item_and_base_class_bypass_fail_closed() -> None:
    sequence = freeze_publication_audit_tree({"items": [1, 2]})["items"]
    with pytest.raises(TypeError, match="immutable"):
        sequence[0] = 9
    with pytest.raises(TypeError, match="immutable"):
        del sequence[0]
    with pytest.raises(TypeError, match="immutable"):
        sequence += (3,)
    with pytest.raises(TypeError, match="immutable"):
        sequence *= 2
    with pytest.raises(TypeError):
        list.append(sequence, 3)
    with pytest.raises(TypeError):
        list.__setitem__(sequence, 0, 9)
    assert sequence == [1, 2]


@pytest.mark.parametrize(
    "forged",
    (
        {"contract_version": PUBLICATION_AUDIT_TREE_CONTRACT_VERSION},
        UserDict({"safe": 1}),
        MappingProxyType({"safe": 1}),
    ),
)
def test_markers_and_arbitrary_mappings_are_not_certified(forged: object) -> None:
    assert is_immutable_publication_audit_tree(forged) is False
    with pytest.raises(PublicationAuditContractError):
        validate_immutable_publication_audit_tree(forged)
    if type(forged) is dict:
        frozen = freeze_publication_audit_tree(forged)
        assert is_immutable_publication_audit_tree(frozen) is True
        assert frozen is not forged
    else:
        with pytest.raises(PublicationAuditContractError):
            freeze_publication_audit_tree(forged)


def test_mutable_backing_store_cannot_be_certified() -> None:
    backing = {"safe": 1}
    proxy = MappingProxyType(backing)
    assert is_immutable_publication_audit_tree(proxy) is False
    backing["late_mutation"] = True
    assert "late_mutation" in proxy
    assert is_immutable_publication_audit_tree(proxy) is False


def test_cycle_non_string_key_nonfinite_and_unsupported_leaf_are_rejected() -> None:
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    with pytest.raises(PublicationAuditContractError, match="cyclic"):
        freeze_publication_audit_tree(cyclic)

    for invalid in (
        {1: "non-string-key"},
        {"nan": float("nan")},
        {"infinity": float("inf")},
        {"bytes": b"unsupported"},
        {"numpy_scalar": np.float64(1.0)},
        {"object": object()},
    ):
        with pytest.raises(PublicationAuditContractError):
            freeze_publication_audit_tree(invalid)


def test_base_immutable_construction_cannot_forge_a_valid_contract() -> None:
    malformed_pair = frozenset.__new__(
        ImmutablePublicationAuditMap,
        (("key",),),
    )
    unsupported_leaf = frozenset.__new__(
        ImmutablePublicationAuditMap,
        (("key", b"unsupported"),),
    )
    duplicate_key = frozenset.__new__(
        ImmutablePublicationAuditMap,
        (("key", 1), ("key", 2)),
    )
    malformed_sequence = tuple.__new__(
        ImmutablePublicationAuditSequence,
        (b"unsupported",),
    )
    nested_malformed_sequence = frozenset.__new__(
        ImmutablePublicationAuditMap,
        (("items", malformed_sequence),),
    )

    for forged in (
        malformed_pair,
        unsupported_leaf,
        duplicate_key,
        nested_malformed_sequence,
    ):
        assert type(forged) is ImmutablePublicationAuditMap
        assert is_immutable_publication_audit_tree(forged) is False
        with pytest.raises(PublicationAuditContractError):
            validate_immutable_publication_audit_tree(forged)


def test_contract_subclasses_are_not_certified() -> None:
    class ForgedMap(ImmutablePublicationAuditMap):
        pass

    forged = frozenset.__new__(ForgedMap, (("safe", 1),))
    assert is_immutable_publication_audit_tree(forged) is False
    with pytest.raises(PublicationAuditContractError, match="exact"):
        validate_immutable_publication_audit_tree(forged)
