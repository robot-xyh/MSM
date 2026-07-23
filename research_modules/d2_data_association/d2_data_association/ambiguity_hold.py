"""Truth-free contracts for bounded D2 structural-ambiguity holds."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from numbers import Integral
from typing import Any, Mapping

import numpy as np

from .models import govern_covariance


D1_STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION = (
    "d1.structural-ambiguity-evidence.v1"
)
D1_STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION = (
    "prediction_only_maximum_matching_component_evidence_v3"
)
D1_STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE = (
    "sha256(canonical_json([publisher_node_id,publisher_epoch,"
    "d1_local_track_id]))"
)
D1_STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE = (
    "publisher_node_id::publisher_epoch::opaque_member_track_token"
)
D1_STRUCTURAL_AMBIGUITY_UPDATE_MODE = "prediction_only"
D1_STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION = "deferred_component_birth"
D1_DEFAULT_PUBLISHER_NODE_ID = "D1_FUSION"
D1_DEFAULT_PUBLISHER_EPOCH = "d1-default-epoch-v1"
D1_OPAQUE_SOURCE_TOKEN_POLICY_VERSION = (
    "d1-structural-ambiguity-opaque-source-token-v1"
)
D2_AMBIGUITY_HOLD_LEASE_POLICY_SCHEMA_VERSION = (
    "d2.ambiguity-hold-lease-policy.v1"
)
D2_AMBIGUITY_HOLD_LEASE_POLICY_VERSION = "d2-ambiguity-hold-lease-v1"


class AmbiguityComponentValidationError(ValueError):
    """Raised when structural-ambiguity evidence is not admissible."""


def opaque_d1_member_track_token(
    publisher_node_id: object,
    publisher_epoch: object,
    d1_local_track_id: object,
) -> str:
    """Mirror the frozen D1 opaque-member-token contract byte for byte."""

    node = _publisher_identifier(publisher_node_id, "publisher_node_id")
    epoch = _publisher_identifier(publisher_epoch, "publisher_epoch")
    local_track_id = _identifier(d1_local_track_id, "d1_local_track_id")
    payload = json.dumps(
        [node, epoch, local_track_id],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return f"d1-track-sha256:{sha256(payload).hexdigest()}"


def opaque_d1_source_track_id(
    publisher_node_id: object,
    publisher_epoch: object,
    d1_local_track_id: object,
) -> str:
    """Return the D2 ``source_track_id`` portion for one D1-local track."""

    epoch = _publisher_identifier(publisher_epoch, "publisher_epoch")
    token = opaque_d1_member_track_token(
        publisher_node_id,
        epoch,
        d1_local_track_id,
    )
    return f"{epoch}::{token}"


def opaque_d1_source_key(
    publisher_node_id: object,
    publisher_epoch: object,
    d1_local_track_id: object,
) -> str:
    """Return the D2 binding key without exposing the D1-local identifier."""

    node = _publisher_identifier(publisher_node_id, "publisher_node_id")
    return (
        f"{node}::"
        f"{opaque_d1_source_track_id(node, publisher_epoch, d1_local_track_id)}"
    )


def source_key_from_opaque_d1_member_token(
    publisher_node_id: object,
    publisher_epoch: object,
    opaque_member_track_token: object,
) -> str:
    """Build the frozen D1 source key from an already opaque member token."""

    node = _publisher_identifier(publisher_node_id, "publisher_node_id")
    epoch = _publisher_identifier(publisher_epoch, "publisher_epoch")
    token = _opaque_digest(
        opaque_member_track_token,
        "d1-track-sha256:",
        "opaque_member_track_token",
    )
    return f"{node}::{epoch}::{token}"


@dataclass(frozen=True, slots=True)
class AmbiguityHoldLeaseConfig:
    """Versioned, bounded lease policy for D1 structural ambiguity."""

    enabled: bool = False
    equivalent_scan_period_seconds: float = 0.1
    gap_scan_periods: int = 2
    hard_scan_periods: int = 5
    gap_seconds: float | None = None
    hard_seconds: float | None = None
    max_component_age_seconds: float = 1.0
    max_active_components: int = 256
    max_members_per_component: int = 32
    max_observations_per_component: int = 64
    max_candidate_edges_per_component: int = 2048
    max_reserved_evidence: int = 100_000
    max_component_history: int = 4096
    schema_version: str = D2_AMBIGUITY_HOLD_LEASE_POLICY_SCHEMA_VERSION
    policy_version: str = D2_AMBIGUITY_HOLD_LEASE_POLICY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("ambiguity hold enabled must be a bool")
        object.__setattr__(
            self,
            "equivalent_scan_period_seconds",
            _positive_finite(
                self.equivalent_scan_period_seconds,
                "equivalent_scan_period_seconds",
            ),
        )
        for name in ("gap_scan_periods", "hard_scan_periods"):
            object.__setattr__(
                self,
                name,
                _positive_integer(getattr(self, name), name),
            )
        for name in ("gap_seconds", "hard_seconds"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive_finite(value, name))
        object.__setattr__(
            self,
            "max_component_age_seconds",
            _nonnegative_finite(
                self.max_component_age_seconds,
                "max_component_age_seconds",
            ),
        )
        for name in (
            "max_active_components",
            "max_members_per_component",
            "max_observations_per_component",
            "max_candidate_edges_per_component",
            "max_reserved_evidence",
            "max_component_history",
        ):
            object.__setattr__(
                self,
                name,
                _positive_integer(getattr(self, name), name),
            )
        schema = _identifier(self.schema_version, "schema_version")
        if schema != D2_AMBIGUITY_HOLD_LEASE_POLICY_SCHEMA_VERSION:
            raise ValueError(
                "unsupported ambiguity hold lease policy schema_version"
            )
        object.__setattr__(self, "schema_version", schema)
        object.__setattr__(
            self,
            "policy_version",
            _identifier(self.policy_version, "policy_version"),
        )
        if self.effective_hard_seconds < self.effective_gap_seconds:
            raise ValueError("hard ambiguity lease cannot be shorter than gap lease")
        if self.max_component_history < self.max_active_components:
            raise ValueError(
                "max_component_history cannot be below max_active_components"
            )

    @property
    def effective_gap_seconds(self) -> float:
        if self.gap_seconds is not None:
            return self.gap_seconds
        return self.gap_scan_periods * self.equivalent_scan_period_seconds

    @property
    def effective_hard_seconds(self) -> float:
        if self.hard_seconds is not None:
            return self.hard_seconds
        return self.hard_scan_periods * self.equivalent_scan_period_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "enabled": self.enabled,
            "equivalent_scan_period_seconds": (
                self.equivalent_scan_period_seconds
            ),
            "gap_scan_periods": self.gap_scan_periods,
            "hard_scan_periods": self.hard_scan_periods,
            "gap_seconds": self.gap_seconds,
            "hard_seconds": self.hard_seconds,
            "effective_gap_seconds": self.effective_gap_seconds,
            "effective_hard_seconds": self.effective_hard_seconds,
            "max_component_age_seconds": self.max_component_age_seconds,
            "max_active_components": self.max_active_components,
            "max_members_per_component": self.max_members_per_component,
            "max_observations_per_component": (
                self.max_observations_per_component
            ),
            "max_candidate_edges_per_component": (
                self.max_candidate_edges_per_component
            ),
            "max_reserved_evidence": self.max_reserved_evidence,
            "max_component_history": self.max_component_history,
            "lease_clock": "d2_consumption_tracker_epoch",
            "component_age_clock": (
                "d2_consumption_tracker_epoch_minus_d1_state_valid_timestamp"
            ),
            "soft_extension_source": "new_original_observation_evidence_only",
            "replay_refresh_allowed": False,
        }


@dataclass(frozen=True, slots=True)
class AmbiguityMember3D:
    """One D1 prediction-only member referenced by an opaque source key."""

    opaque_member_track_token: str
    source_key: str
    state_ned: np.ndarray
    covariance: np.ndarray
    covariance_consistency: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        token = _opaque_digest(
            self.opaque_member_track_token,
            "d1-track-sha256:",
            "opaque_member_track_token",
        )
        object.__setattr__(self, "opaque_member_track_token", token)
        source_key = _identifier(self.source_key, "source_key")
        source_parts = source_key.split("::")
        if len(source_parts) != 3 or source_parts[2] != token:
            raise ValueError(
                "source_key must be node::epoch::opaque_member_track_token"
            )
        _publisher_identifier(source_parts[0], "member publisher_node_id")
        _publisher_identifier(source_parts[1], "member publisher_epoch")
        object.__setattr__(self, "source_key", source_key)
        object.__setattr__(
            self,
            "state_ned",
            _finite_vector(self.state_ned, 6, "member state"),
        )
        covariance, consistency = govern_covariance(
            self.covariance,
            (6, 6),
            "ambiguity member covariance",
        )
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "covariance_consistency", dict(consistency))

    @property
    def source_node_id(self) -> str:
        return self.source_key.split("::", maxsplit=1)[0]

    @property
    def source_track_id(self) -> str:
        return self.source_key.split("::", maxsplit=1)[1]

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
        *,
        publisher_node_id: str,
        publisher_epoch: str,
    ) -> "AmbiguityMember3D":
        _require_exact_keys(
            payload,
            {
                "opaque_member_track_token",
                "source_key",
                "state",
                "covariance",
            },
            "member state",
        )
        member = cls(
            opaque_member_track_token=payload["opaque_member_track_token"],
            source_key=payload["source_key"],
            state_ned=payload["state"],
            covariance=payload["covariance"],
        )
        expected = source_key_from_opaque_d1_member_token(
            publisher_node_id,
            publisher_epoch,
            member.opaque_member_track_token,
        )
        if member.source_key != expected:
            raise ValueError("member source_key violates the frozen D1 rule")
        return member

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_member_track_token": self.opaque_member_track_token,
            "source_key": self.source_key,
            "state": self.state_ned.tolist(),
            "covariance": self.covariance.tolist(),
        }


@dataclass(frozen=True, slots=True)
class AmbiguityObservation3D:
    """Anonymous original observation reserved only by its opaque D1 key."""

    observation_evidence_key: str
    position_ned: np.ndarray
    covariance_ned: np.ndarray
    radial_velocity_observed: bool
    birth_deferred: bool
    velocity_evidence_used: bool = False
    covariance_consistency: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_evidence_key",
            _opaque_digest(
                self.observation_evidence_key,
                "d1-observation-sha256:",
                "observation_evidence_key",
            ),
        )
        for name in (
            "radial_velocity_observed",
            "birth_deferred",
            "velocity_evidence_used",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")
        if self.velocity_evidence_used:
            raise ValueError(
                "prediction-only ambiguity evidence cannot use velocity"
            )
        object.__setattr__(
            self,
            "position_ned",
            _finite_vector(self.position_ned, 3, "observation position_ned"),
        )
        covariance, consistency = govern_covariance(
            self.covariance_ned,
            (3, 3),
            "ambiguity observation covariance_ned",
        )
        object.__setattr__(self, "covariance_ned", covariance)
        object.__setattr__(self, "covariance_consistency", dict(consistency))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AmbiguityObservation3D":
        _require_exact_keys(
            payload,
            {
                "observation_evidence_key",
                "position_ned",
                "covariance_ned",
                "radial_velocity_observed",
                "birth_deferred",
                "velocity_evidence_used",
            },
            "observation evidence",
        )
        return cls(**{key: payload[key] for key in payload})

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_evidence_key": self.observation_evidence_key,
            "position_ned": self.position_ned.tolist(),
            "covariance_ned": self.covariance_ned.tolist(),
            "radial_velocity_observed": self.radial_velocity_observed,
            "birth_deferred": self.birth_deferred,
            "velocity_evidence_used": self.velocity_evidence_used,
        }


@dataclass(frozen=True, slots=True)
class AmbiguityCandidateEdge3D:
    """One truth-free allowed edge in a D1 ambiguity component."""

    opaque_member_track_token: str
    observation_evidence_key: str
    nis: float
    gate_threshold: float
    edge_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "opaque_member_track_token",
            _opaque_digest(
                self.opaque_member_track_token,
                "d1-track-sha256:",
                "opaque_member_track_token",
            ),
        )
        object.__setattr__(
            self,
            "observation_evidence_key",
            _opaque_digest(
                self.observation_evidence_key,
                "d1-observation-sha256:",
                "observation_evidence_key",
            ),
        )
        nis = _nonnegative_finite(self.nis, "nis")
        gate = _positive_finite(self.gate_threshold, "gate_threshold")
        if nis > gate + 1.0e-9:
            raise ValueError("candidate edge nis must be within gate_threshold")
        roles = tuple(sorted({_identifier(item, "edge role") for item in self.edge_roles}))
        if "maximum_matching_allowed" not in roles:
            raise ValueError(
                "candidate edge roles must include maximum_matching_allowed"
            )
        object.__setattr__(self, "nis", nis)
        object.__setattr__(self, "gate_threshold", gate)
        object.__setattr__(self, "edge_roles", roles)

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "AmbiguityCandidateEdge3D":
        _require_exact_keys(
            payload,
            {
                "opaque_member_track_token",
                "observation_evidence_key",
                "nis",
                "gate_threshold",
                "edge_roles",
            },
            "candidate edge",
        )
        return cls(
            opaque_member_track_token=payload["opaque_member_track_token"],
            observation_evidence_key=payload["observation_evidence_key"],
            nis=payload["nis"],
            gate_threshold=payload["gate_threshold"],
            edge_roles=tuple(payload["edge_roles"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_member_track_token": self.opaque_member_track_token,
            "observation_evidence_key": self.observation_evidence_key,
            "nis": self.nis,
            "gate_threshold": self.gate_threshold,
            "edge_roles": list(self.edge_roles),
        }


@dataclass(frozen=True, slots=True)
class AmbiguityComponent3D:
    """Strict D2 view of one frozen D1 v1 ambiguity-evidence payload."""

    evidence_id: str
    component_id: str
    component_generation: int
    publisher_node_id: str
    publisher_epoch: str
    measurement_timestamp: float
    arrival_timestamp: float
    state_valid_timestamp: float
    published_at: float
    sensor_id: str
    scan_id: str
    member_states: tuple[AmbiguityMember3D, ...]
    observations: tuple[AmbiguityObservation3D, ...]
    candidate_edges: tuple[AmbiguityCandidateEdge3D, ...]
    component_kinds: tuple[str, ...]
    member_count: int
    observation_count: int
    candidate_edge_count: int
    free_row_count: int
    free_column_count: int
    maximum_matching_cardinality: int
    policy_version: str
    frame_id: str
    member_token_rule: str
    source_key_rule: str
    posterior_update_applied: bool
    update_mode: str
    birth_disposition: str
    component_complete: bool
    cross_covariance_available: bool
    schema_version: str

    def __post_init__(self) -> None:
        if self.schema_version != D1_STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported structural ambiguity schema_version")
        if self.policy_version != D1_STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION:
            raise ValueError("unsupported structural ambiguity policy_version")
        if self.member_token_rule != D1_STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE:
            raise ValueError("unsupported member_token_rule")
        if self.source_key_rule != D1_STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE:
            raise ValueError("unsupported source_key_rule")
        object.__setattr__(
            self,
            "evidence_id",
            _opaque_digest(
                self.evidence_id,
                "d1-evidence-sha256:",
                "evidence_id",
            ),
        )
        object.__setattr__(
            self,
            "component_id",
            _opaque_digest(
                self.component_id,
                "d1-component-sha256:",
                "component_id",
            ),
        )
        object.__setattr__(
            self,
            "scan_id",
            _opaque_digest(self.scan_id, "d1-scan-sha256:", "scan_id"),
        )
        object.__setattr__(
            self,
            "component_generation",
            _positive_integer(
                self.component_generation,
                "component_generation",
            ),
        )
        node = _publisher_identifier(
            self.publisher_node_id,
            "publisher_node_id",
        )
        epoch = _publisher_identifier(self.publisher_epoch, "publisher_epoch")
        object.__setattr__(self, "publisher_node_id", node)
        object.__setattr__(self, "publisher_epoch", epoch)
        measurement = _timestamp(
            self.measurement_timestamp,
            "measurement_timestamp",
        )
        arrival = _timestamp(self.arrival_timestamp, "arrival_timestamp")
        state_valid = _timestamp(
            self.state_valid_timestamp,
            "state_valid_timestamp",
        )
        published = _timestamp(self.published_at, "published_at")
        if arrival + 1.0e-12 < measurement:
            raise ValueError(
                "arrival_timestamp cannot precede measurement_timestamp"
            )
        if abs(state_valid - measurement) > 1.0e-9:
            raise ValueError(
                "state_valid_timestamp must equal measurement_timestamp"
            )
        if published + 1.0e-12 < arrival:
            raise ValueError("published_at cannot precede arrival_timestamp")
        object.__setattr__(self, "measurement_timestamp", measurement)
        object.__setattr__(self, "arrival_timestamp", arrival)
        object.__setattr__(self, "state_valid_timestamp", state_valid)
        object.__setattr__(self, "published_at", published)
        object.__setattr__(self, "sensor_id", _identifier(self.sensor_id, "sensor_id"))
        frame = _identifier(self.frame_id, "frame_id").upper()
        if frame != "NED":
            raise ValueError("structural ambiguity evidence requires frame_id=NED")
        object.__setattr__(self, "frame_id", frame)
        kinds = tuple(
            sorted({_identifier(item, "component kind") for item in self.component_kinds})
        )
        if not kinds:
            raise ValueError("component_kinds must not be empty")
        object.__setattr__(self, "component_kinds", kinds)

        for name, expected in (
            ("posterior_update_applied", False),
            ("component_complete", True),
            ("cross_covariance_available", False),
        ):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a bool")
            if value is not expected:
                raise ValueError(f"{name} must be {expected}")
        if self.update_mode != D1_STRUCTURAL_AMBIGUITY_UPDATE_MODE:
            raise ValueError("update_mode must be prediction_only")
        if self.birth_disposition != D1_STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION:
            raise ValueError("birth_disposition must defer component birth")
        if not self.member_states or not self.observations or not self.candidate_edges:
            raise ValueError(
                "ambiguity evidence requires members, observations, and edges"
            )

        member_tokens = [
            item.opaque_member_track_token for item in self.member_states
        ]
        member_keys = [item.source_key for item in self.member_states]
        observation_keys = [
            item.observation_evidence_key for item in self.observations
        ]
        edge_pairs = [
            (
                item.opaque_member_track_token,
                item.observation_evidence_key,
            )
            for item in self.candidate_edges
        ]
        if len(set(member_tokens)) != len(member_tokens):
            raise ValueError("member tokens must be unique")
        if len(set(member_keys)) != len(member_keys):
            raise ValueError("member source keys must be unique")
        if len(set(observation_keys)) != len(observation_keys):
            raise ValueError("observation evidence keys must be unique")
        if len(set(edge_pairs)) != len(edge_pairs):
            raise ValueError("candidate edge pairs must be unique")
        if {item[0] for item in edge_pairs} != set(member_tokens):
            raise ValueError("every member must have a candidate edge")
        if {item[1] for item in edge_pairs} != set(observation_keys):
            raise ValueError("every observation must have a candidate edge")
        if any(
            token not in set(member_tokens) or key not in set(observation_keys)
            for token, key in edge_pairs
        ):
            raise ValueError("candidate edge references outside the component")
        for member in self.member_states:
            expected = source_key_from_opaque_d1_member_token(
                node,
                epoch,
                member.opaque_member_track_token,
            )
            if member.source_key != expected:
                raise ValueError("member source_key violates the frozen D1 rule")

        integer_fields = (
            "member_count",
            "observation_count",
            "candidate_edge_count",
            "free_row_count",
            "free_column_count",
            "maximum_matching_cardinality",
        )
        for name in integer_fields:
            object.__setattr__(
                self,
                name,
                _nonnegative_integer(getattr(self, name), name),
            )
        if self.member_count != len(self.member_states):
            raise ValueError("member_count does not match member_states")
        if self.observation_count != len(self.observations):
            raise ValueError("observation_count does not match observations")
        if self.candidate_edge_count != len(self.candidate_edges):
            raise ValueError("candidate_edge_count does not match candidate_edges")
        if (
            self.maximum_matching_cardinality
            != self.member_count - self.free_row_count
        ):
            raise ValueError("free_row_count is inconsistent")
        if (
            self.maximum_matching_cardinality
            != self.observation_count - self.free_column_count
        ):
            raise ValueError("free_column_count is inconsistent")

    @property
    def generation(self) -> int:
        return self.component_generation

    @property
    def members(self) -> tuple[AmbiguityMember3D, ...]:
        return self.member_states

    @property
    def member_source_keys(self) -> tuple[str, ...]:
        return tuple(item.source_key for item in self.member_states)

    @property
    def observation_evidence_keys(self) -> tuple[str, ...]:
        return tuple(
            item.observation_evidence_key for item in self.observations
        )

    @property
    def lease_key(self) -> str:
        return (
            f"{self.publisher_node_id}::{self.publisher_epoch}::"
            f"{self.component_id}"
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AmbiguityComponent3D":
        """Parse the exact D1 v1 public payload without importing D1 code."""

        try:
            if not isinstance(payload, Mapping):
                raise TypeError("structural ambiguity payload must be a mapping")
            from .scalable_3d_models import assert_online_metadata_truth_free

            assert_online_metadata_truth_free(payload)
            required = {
                "schema_version",
                "evidence_id",
                "component_id",
                "component_generation",
                "publisher_node_id",
                "publisher_epoch",
                "member_token_rule",
                "source_key_rule",
                "measurement_timestamp",
                "arrival_timestamp",
                "state_valid_timestamp",
                "published_at",
                "sensor_id",
                "scan_id",
                "frame_id",
                "member_states",
                "observations",
                "candidate_edges",
                "component_kinds",
                "member_count",
                "observation_count",
                "candidate_edge_count",
                "free_row_count",
                "free_column_count",
                "maximum_matching_cardinality",
                "posterior_update_applied",
                "update_mode",
                "birth_disposition",
                "component_complete",
                "cross_covariance_available",
                "policy_version",
            }
            _require_exact_keys(payload, required, "structural ambiguity evidence")
            node = _publisher_identifier(
                payload["publisher_node_id"],
                "publisher_node_id",
            )
            epoch = _publisher_identifier(
                payload["publisher_epoch"],
                "publisher_epoch",
            )
            members = tuple(
                AmbiguityMember3D.from_mapping(
                    item,
                    publisher_node_id=node,
                    publisher_epoch=epoch,
                )
                for item in _mapping_sequence(
                    payload["member_states"],
                    "member_states",
                )
            )
            observations = tuple(
                AmbiguityObservation3D.from_mapping(item)
                for item in _mapping_sequence(
                    payload["observations"],
                    "observations",
                )
            )
            edges = tuple(
                AmbiguityCandidateEdge3D.from_mapping(item)
                for item in _mapping_sequence(
                    payload["candidate_edges"],
                    "candidate_edges",
                )
            )
            values = {key: payload[key] for key in required}
            values["publisher_node_id"] = node
            values["publisher_epoch"] = epoch
            values["member_states"] = members
            values["observations"] = observations
            values["candidate_edges"] = edges
            values["component_kinds"] = tuple(payload["component_kinds"])
            return cls(**values)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, AmbiguityComponentValidationError):
                raise
            raise AmbiguityComponentValidationError(str(exc)) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "component_id": self.component_id,
            "component_generation": self.component_generation,
            "publisher_node_id": self.publisher_node_id,
            "publisher_epoch": self.publisher_epoch,
            "member_token_rule": self.member_token_rule,
            "source_key_rule": self.source_key_rule,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "state_valid_timestamp": self.state_valid_timestamp,
            "published_at": self.published_at,
            "sensor_id": self.sensor_id,
            "scan_id": self.scan_id,
            "frame_id": self.frame_id,
            "member_states": [item.to_dict() for item in self.member_states],
            "observations": [item.to_dict() for item in self.observations],
            "candidate_edges": [
                item.to_dict() for item in self.candidate_edges
            ],
            "component_kinds": list(self.component_kinds),
            "member_count": self.member_count,
            "observation_count": self.observation_count,
            "candidate_edge_count": self.candidate_edge_count,
            "free_row_count": self.free_row_count,
            "free_column_count": self.free_column_count,
            "maximum_matching_cardinality": (
                self.maximum_matching_cardinality
            ),
            "posterior_update_applied": self.posterior_update_applied,
            "update_mode": self.update_mode,
            "birth_disposition": self.birth_disposition,
            "component_complete": self.component_complete,
            "cross_covariance_available": self.cross_covariance_available,
            "policy_version": self.policy_version,
        }


def _mapping_sequence(
    value: Any,
    name: str,
) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{name} must be a sequence of mappings")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(f"{name}[{index}] must be a mapping")
        result.append(item)
    return tuple(result)


def _require_exact_keys(
    payload: Mapping[str, Any],
    required: set[str],
    name: str,
) -> None:
    actual = {str(key) for key in payload}
    if actual != required:
        missing = sorted(required - actual)
        extra = sorted(actual - required)
        details: list[str] = []
        if missing:
            details.append(f"missing={missing}")
        if extra:
            details.append(f"extra={extra}")
        raise ValueError(f"{name} fields invalid: " + ", ".join(details))


def _identifier(value: object, name: str) -> str:
    if value is None:
        raise ValueError(f"{name} must be non-empty")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{name} must not contain control characters")
    return normalized


def _publisher_identifier(value: object, name: str) -> str:
    normalized = _identifier(value, name)
    if "::" in normalized:
        raise ValueError(f"{name} cannot contain the source-key separator")
    lowered = normalized.lower()
    if any(marker in lowered for marker in ("truth", "actor", "target_id")):
        raise ValueError(
            f"{name} must not encode truth, actor, or target identity"
        )
    return normalized


def _opaque_digest(value: object, prefix: str, name: str) -> str:
    normalized = _identifier(value, name)
    if not normalized.startswith(prefix):
        raise ValueError(f"{name} must start with {prefix}")
    digest = normalized[len(prefix) :]
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"{name} must contain a lowercase SHA-256 digest")
    return normalized


def _timestamp(value: object, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _finite_vector(value: object, size: int, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=float).reshape(-1)
    if result.shape != (size,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite vector of length {size}")
    return result


def _positive_finite(value: object, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return result


def _nonnegative_finite(value: object, name: str) -> float:
    result = float(value)
    if not np.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return result


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be a non-negative integer")
    result = int(value)
    if result < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return result
