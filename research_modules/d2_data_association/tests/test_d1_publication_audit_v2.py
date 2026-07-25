from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

import d2_data_association as d2_package
from research_modules.d1_sensor_fusion.src.d1_sensor_fusion.publication_audit import (
    PUBLICATION_AUDIT_TREE_CONTRACT_VERSION,
    ImmutablePublicationAuditMap,
    PublicationAuditContractError,
    freeze_publication_audit_tree,
)

from d2_data_association import (
    D1GlobalTrackDetectionBatch,
    detections3d_from_d1_global_tracks,
    detections3d_from_d1_global_tracks_with_audit,
)
from d2_data_association.scalable_3d_models import (
    assert_online_metadata_batch_truth_free,
)


def _safe_shared_roots() -> tuple[
    ImmutablePublicationAuditMap,
    ImmutablePublicationAuditMap,
    ImmutablePublicationAuditMap,
]:
    return (
        freeze_publication_audit_tree(
            {
                "schema_version": "d1.association_audit.v1",
                "candidate_count": 40000,
            }
        ),
        freeze_publication_audit_tree(
            {
                "schema_version": "d1.latency_audit.v1",
                "samples": [0.1, 0.2],
            }
        ),
        freeze_publication_audit_tree(
            {
                "RADAR-001": {
                    "measurement_count": 200,
                    "quality_flags": ["nominal"],
                }
            }
        ),
    )


def _source_track(
    index: int,
    roots: tuple[
        ImmutablePublicationAuditMap,
        ImmutablePublicationAuditMap,
        ImmutablePublicationAuditMap,
    ],
) -> SimpleNamespace:
    association_audit, latency_audit, sensor_health = roots
    return SimpleNamespace(
        global_track_id=f"UPSTREAM-PRIVATE-{index:04d}",
        state=np.asarray(
            [float(index), 20.0, -30.0, 2.0, 0.0, 0.0],
            dtype=float,
        ),
        covariance=np.eye(6, dtype=float),
        timestamp=1.2,
        metadata={
            "frame_id": "NED",
            "latest_measurement_timestamp": 1.0,
            "latest_arrival_timestamp": 1.1,
            "latest_observation_id": f"radar-observation-{index:04d}",
            "published_at": 1.2,
            "association_audit": association_audit,
            "latency_audit": latency_audit,
            "sensor_health": sensor_health,
        },
    )


def test_v2_adapter_symbols_are_exported_by_package_api_and_all() -> None:
    assert (
        d2_package.D1GlobalTrackDetectionBatch
        is D1GlobalTrackDetectionBatch
    )
    assert (
        d2_package.detections3d_from_d1_global_tracks_with_audit
        is detections3d_from_d1_global_tracks_with_audit
    )
    assert "D1GlobalTrackDetectionBatch" in d2_package.__all__
    assert (
        "detections3d_from_d1_global_tracks_with_audit"
        in d2_package.__all__
    )

    exported: dict[str, object] = {}
    exec("from d2_data_association import *", {}, exported)
    assert (
        exported["D1GlobalTrackDetectionBatch"]
        is D1GlobalTrackDetectionBatch
    )
    assert (
        exported["detections3d_from_d1_global_tracks_with_audit"]
        is detections3d_from_d1_global_tracks_with_audit
    )


def test_200_tracks_validate_and_audit_three_shared_v2_roots_once() -> None:
    roots = _safe_shared_roots()
    metadata = [
        _source_track(index, roots).metadata
        for index in range(200)
    ]

    summary = assert_online_metadata_batch_truth_free(metadata)

    assert summary.metadata_count == 200
    assert summary.shared_subtree_full_audit_count == 3
    assert summary.shared_subtree_equivalent_reuse_count == 0
    assert summary.immutable_v2_contract_validation_count == 3
    assert summary.immutable_v2_full_content_audit_count == 3
    assert summary.immutable_v2_identity_reuse_count == 3 * (200 - 1)
    assert summary.immutable_v2_contract_rejection_count == 0
    assert summary.to_dict()["shared_subtree_builtin_equivalent_reuse_count"] == 0


@pytest.mark.parametrize(
    "forbidden_key",
    (
        "truth",
        "actor_id",
        "object_id",
        "target_id",
        "global_track_id",
    ),
)
def test_v2_root_still_receives_truth_free_content_audit(
    forbidden_key: str,
) -> None:
    root = freeze_publication_audit_tree({forbidden_key: "forbidden"})

    with pytest.raises(ValueError, match=forbidden_key):
        assert_online_metadata_batch_truth_free(
            [{"sensor_health": root}]
        )


def test_equal_but_distinct_v2_roots_are_validated_and_audited_separately() -> None:
    left = freeze_publication_audit_tree(
        {"sensor": {"quality": "nominal"}}
    )
    right = freeze_publication_audit_tree(
        {"sensor": {"quality": "nominal"}}
    )
    assert left == right
    assert left is not right

    summary = assert_online_metadata_batch_truth_free(
        [
            {"sensor_health": left},
            {"sensor_health": right},
        ]
    )

    assert summary.shared_subtree_full_audit_count == 2
    assert summary.immutable_v2_contract_validation_count == 2
    assert summary.immutable_v2_full_content_audit_count == 2
    assert summary.immutable_v2_identity_reuse_count == 0


def test_malformed_exact_v2_root_is_rejected_before_content_policy() -> None:
    malformed = frozenset.__new__(
        ImmutablePublicationAuditMap,
        (("truth", object()),),
    )

    with pytest.raises(PublicationAuditContractError, match="non-contract"):
        assert_online_metadata_batch_truth_free(
            [{"sensor_health": malformed}]
        )


def test_v2_subclass_is_never_trusted() -> None:
    class ForgedMap(ImmutablePublicationAuditMap):
        pass

    forged = frozenset.__new__(ForgedMap, (("safe", 1),))

    with pytest.raises(PublicationAuditContractError, match="subclasses"):
        assert_online_metadata_batch_truth_free(
            [{"sensor_health": forged}]
        )


def test_marker_custom_equality_and_mutable_backing_do_not_gain_v2_trust() -> None:
    class AlwaysEqualMapping(dict[str, Any]):
        def __eq__(self, other: object) -> bool:
            del other
            return True

    marker_summary = assert_online_metadata_batch_truth_free(
        [
            {
                "sensor_health": {
                    "contract_version": (
                        PUBLICATION_AUDIT_TREE_CONTRACT_VERSION
                    ),
                    "quality": "nominal",
                }
            }
        ]
    )
    assert marker_summary.immutable_v2_contract_validation_count == 0
    assert marker_summary.shared_subtree_full_audit_count == 1

    with pytest.raises(ValueError, match="truth_id"):
        assert_online_metadata_batch_truth_free(
            [
                {
                    "sensor_health": AlwaysEqualMapping(
                        {"quality": "nominal"}
                    )
                },
                {
                    "sensor_health": AlwaysEqualMapping(
                        {"truth_id": "forbidden"}
                    )
                },
            ]
        )

    backing = {"quality": "nominal"}
    proxy = MappingProxyType(backing)
    proxy_summary = assert_online_metadata_batch_truth_free(
        [
            {"sensor_health": proxy},
            {"sensor_health": proxy},
        ]
    )
    assert proxy_summary.shared_subtree_full_audit_count == 2
    assert proxy_summary.immutable_v2_identity_reuse_count == 0
    backing["global_track_id"] = "forbidden"
    with pytest.raises(ValueError, match="global_track_id"):
        assert_online_metadata_batch_truth_free(
            [{"sensor_health": proxy}]
        )


def test_adapter_returns_audit_summary_without_copying_upstream_global_id() -> None:
    roots = _safe_shared_roots()
    sources = [_source_track(index, roots) for index in range(2)]

    result = detections3d_from_d1_global_tracks_with_audit(sources)
    legacy_timestamp, legacy_detections = (
        detections3d_from_d1_global_tracks(sources)
    )

    assert result.frame_timestamp == pytest.approx(1.2)
    assert result.metadata_audit.metadata_count == 2
    assert result.metadata_audit.immutable_v2_contract_validation_count == 3
    assert result.metadata_audit.immutable_v2_identity_reuse_count == 3
    assert legacy_timestamp == result.frame_timestamp
    assert [item.to_dict() for item in legacy_detections] == [
        item.to_dict() for item in result.detections
    ]
    serialized = str([item.to_dict() for item in result.detections])
    assert "UPSTREAM-PRIVATE" not in serialized
    assert all(
        "global_track_id" not in item.metadata
        for item in result.detections
    )


def test_exact_builtin_equivalent_reuse_regression_is_preserved() -> None:
    metadata = [
        {
            "sensor_health": {
                "RADAR-001": {
                    "measurement_count": 200,
                    "quality_flags": ["nominal"],
                }
            }
        }
        for _ in range(4)
    ]

    summary = assert_online_metadata_batch_truth_free(metadata)

    assert summary.shared_subtree_full_audit_count == 1
    assert summary.shared_subtree_equivalent_reuse_count == 3
    assert summary.immutable_v2_contract_validation_count == 0
    assert summary.immutable_v2_identity_reuse_count == 0
