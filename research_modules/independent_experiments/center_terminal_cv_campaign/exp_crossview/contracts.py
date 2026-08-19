"""Online-safe products and offline evaluation records."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, Mapping, Sequence


CANDIDATE_SCHEMA = "terminal-crossview-candidate-v1"
MATCH_SCHEMA = "terminal-crossview-match-v1"
CLUSTER_SCHEMA = "terminal-crossview-cluster-v1"
RESULT_SCHEMA = "terminal-crossview-result-v1"
AUDIT_SCHEMA = "terminal-crossview-association-audit-v1"

FORBIDDEN_ONLINE_MARKERS = (
    "truth",
    "actor",
    "object_id",
    "object_name",
    "global_track_id",
    "label",
)


def track_key(camera_id: str, local_track_id: str) -> str:
    return f"{camera_id}::{local_track_id}"


def split_track_key(value: str) -> tuple[str, str]:
    camera_id, separator, local_track_id = value.partition("::")
    if not separator or not camera_id or not local_track_id:
        raise ValueError(f"invalid track key: {value}")
    return camera_id, local_track_id


def _contains_forbidden_online_value(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in FORBIDDEN_ONLINE_MARKERS):
                return True
            if _contains_forbidden_online_value(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_online_value(item) for item in value)
    return False


def assert_online_anonymous(value: Any) -> None:
    payload = asdict(value) if hasattr(value, "__dataclass_fields__") else value
    if _contains_forbidden_online_value(payload):
        raise ValueError("online payload contains identity-bearing evidence")
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).lower()
    # Identifier values are also checked. This catches a truth-bearing local ID
    # even when its key is otherwise allowed.
    if any(marker in encoded for marker in ("truth-", "actor-", "actor_", "global-track")):
        raise ValueError("online payload contains a forbidden identity marker")


@dataclass(frozen=True)
class CandidateEdge:
    camera_a_id: str
    track_a_id: str
    camera_b_id: str
    track_b_id: str
    reference_timestamp: float
    aligned_sample_count: int
    latest_time_offset_s: float
    median_ray_separation_m: float
    median_reprojection_error_px: float
    intersection_angle_deg: float
    motion_fit_error_m: float
    motion_turn_deg: float
    bbox_log_scale_difference: float
    camera_confidence: float
    geometry_cost: float
    gate_passed: bool
    reject_reasons: tuple[str, ...] = ()
    midpoint_ned_m: tuple[float, float, float] | None = None
    edge_features: tuple[float, ...] = ()
    learned_probability: float | None = None
    final_cost: float | None = None
    schema_version: str = CANDIDATE_SCHEMA

    @property
    def key_a(self) -> str:
        return track_key(self.camera_a_id, self.track_a_id)

    @property
    def key_b(self) -> str:
        return track_key(self.camera_b_id, self.track_b_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PairMatch:
    camera_a_id: str
    track_a_id: str
    camera_b_id: str
    track_b_id: str
    timestamp: float
    cost: float
    decision_state: str
    confirmation_count: int
    backend: str
    reject_reasons: tuple[str, ...] = ()
    schema_version: str = MATCH_SCHEMA

    @property
    def key_a(self) -> str:
        return track_key(self.camera_a_id, self.track_a_id)

    @property
    def key_b(self) -> str:
        return track_key(self.camera_b_id, self.track_b_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UnifiedTargetCluster:
    cluster_id: str
    member_track_keys: tuple[str, ...]
    camera_ids: tuple[str, ...]
    decision_state: str = "confirmed"
    schema_version: str = CLUSTER_SCHEMA

    def __post_init__(self) -> None:
        if len(self.camera_ids) != len(set(self.camera_ids)):
            raise ValueError("a unified target may contain at most one track per camera")
        if len(self.member_track_keys) != len(self.camera_ids):
            raise ValueError("cluster members and cameras disagree")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OfflineTruthLabels:
    """Fixture-only identities. Never pass this record into online association."""

    track_to_target: Mapping[str, str]
    target_trajectories_ned_m: Mapping[str, tuple[tuple[float, float, float, float], ...]]
    scenario_name: str
    seed: int
    offline_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossViewMetrics:
    recognized_track_count: int
    candidate_edge_count: int
    geometry_passed_edge_count: int
    confirmed_relation_count: int
    tentative_relation_count: int
    unresolved_track_count: int
    cluster_count: int
    camera_uniqueness_violation_count: int
    truth_leakage_count: int
    true_positive_relations: int | None = None
    false_positive_relations: int | None = None
    false_negative_relations: int | None = None
    association_precision: float | None = None
    association_recall: float | None = None
    id_switch_count: int | None = None
    availability: Mapping[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AssociationAudit:
    output_mode: str
    camera_pair_policy: str
    camera_pair_total_count: int
    camera_pair_retained_count: int
    camera_pair_pruned_count: int
    camera_pair_evaluation_count: int
    candidate_stage_counts: Mapping[str, int]
    candidate_reject_reason_counts: Mapping[str, int]
    camera_pair_reject_reason_counts: Mapping[str, int]
    candidate_sample_limit: int
    retained_candidate_sample_count: int
    omitted_candidate_count: int
    schema_version: str = AUDIT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CrossViewResult:
    backend: str
    candidates: tuple[CandidateEdge, ...]
    matches: tuple[PairMatch, ...]
    clusters: tuple[UnifiedTargetCluster, ...]
    pending_relations: tuple[PairMatch, ...]
    unresolved_track_keys: tuple[str, ...]
    metrics: CrossViewMetrics
    audit: AssociationAudit
    schema_version: str = RESULT_SCHEMA

    def to_online_dict(self) -> dict[str, Any]:
        payload = {
            "backend": self.backend,
            "candidates": [item.to_dict() for item in self.candidates],
            "matches": [item.to_dict() for item in self.matches],
            "clusters": [item.to_dict() for item in self.clusters],
            "pending_relations": [item.to_dict() for item in self.pending_relations],
            "unresolved_track_keys": self.unresolved_track_keys,
            "metrics": {
                key: value
                for key, value in self.metrics.to_dict().items()
                if key
                not in {
                    "truth_leakage_count",
                    "true_positive_relations",
                    "false_positive_relations",
                    "false_negative_relations",
                    "association_precision",
                    "association_recall",
                    "id_switch_count",
                }
            },
            "audit": self.audit.to_dict(),
            "schema_version": self.schema_version,
        }
        payload["metrics"]["availability"] = {
            key: value
            for key, value in self.metrics.availability.items()
            if "truth" not in key.lower()
        }
        assert_online_anonymous(payload)
        return payload


def finite_mean(values: Sequence[float], default: float = 0.0) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return sum(finite) / len(finite) if finite else float(default)
