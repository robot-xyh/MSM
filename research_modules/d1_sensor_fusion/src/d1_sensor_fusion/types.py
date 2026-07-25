from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any

import numpy as np

from .publication_audit import publication_audit_to_builtin


STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION = (
    "d1.structural-ambiguity-evidence.v1"
)
STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION = (
    "prediction_only_maximum_matching_component_evidence_v3"
)
STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE = (
    "sha256(canonical_json([publisher_node_id,publisher_epoch,d1_local_track_id]))"
)
STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE = (
    "publisher_node_id::publisher_epoch::opaque_member_track_token"
)
STRUCTURAL_AMBIGUITY_UPDATE_MODE = "prediction_only"
STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION = "deferred_component_birth"
DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_NODE_ID = "D1_FUSION"
DEFAULT_STRUCTURAL_AMBIGUITY_PUBLISHER_EPOCH = "d1-default-epoch-v1"


CANONICAL_OBSERVATION_FRAMES = {
    "radar": {"ned"},
    "acoustic": {"ned"},
    "acoustic_3d": {"ned"},
    "eo": {"pixel"},
    "lidar": {"ned"},
}

COMMUNICATION_METADATA_KEYS = (
    "source_node_id",
    "target_node_id",
    "relay_node_id",
    "link_type",
    "sent_timestamp",
    "received_timestamp",
    "payload_kind",
    "stale_after_s",
    "source_support",
)

SOURCE_LINEAGE_METADATA_KEYS = (
    "source_lineage_key",
    "lineage_id",
    "sequence_id",
    "sequence",
    "source_sequence",
    "payload_id",
    "payload_hash",
    "payload_digest",
    "payload_sequence",
)


class TrackLevel(str, Enum):
    """Research quality level for a fused track."""

    COARSE = "coarse"
    STABLE = "stable"
    HANDOVER = "handover"
    LOST = "lost"


@dataclass(frozen=True)
class SensorTimingExpectation:
    """Configured timing budget used to interpret latency and OOSM health."""

    expected_latency_s: float
    latency_tolerance_s: float = 0.05
    oosm_expected: bool = False

    def __post_init__(self) -> None:
        raw_oosm_expected = self.oosm_expected
        if isinstance(raw_oosm_expected, str):
            normalized = raw_oosm_expected.strip().lower()
            if normalized not in {"true", "false", "1", "0", "yes", "no"}:
                raise ValueError("oosm_expected must be a boolean value")
            raw_oosm_expected = normalized in {"true", "1", "yes"}
        object.__setattr__(self, "expected_latency_s", float(self.expected_latency_s))
        object.__setattr__(self, "latency_tolerance_s", float(self.latency_tolerance_s))
        object.__setattr__(self, "oosm_expected", bool(raw_oosm_expected))
        if not np.isfinite(self.expected_latency_s) or self.expected_latency_s < 0.0:
            raise ValueError("expected_latency_s must be non-negative")
        if not np.isfinite(self.latency_tolerance_s) or self.latency_tolerance_s < 0.0:
            raise ValueError("latency_tolerance_s must be non-negative")


@dataclass
class SensorObservation:
    """Canonical heterogeneous observation.

    `measurement_timestamp` is the physical sensing time. `arrival_timestamp`
    is when the fusion node receives the observation and is only used for
    latency accounting, ordering, and fixed-lag replay.
    """

    observation_id: str
    sensor_id: str
    modality: str
    measurement_timestamp: float
    arrival_timestamp: float
    frame_id: str
    measurement: np.ndarray
    covariance: np.ndarray | None = None
    classification_hint: str | None = None
    confidence: float = 1.0
    quality_flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    source_node_id: str | None = None
    target_node_id: str | None = None
    relay_node_id: str | None = None
    link_type: str | None = None
    sent_timestamp: float | None = None
    received_timestamp: float | None = None
    payload_kind: str | None = None
    stale_after_s: float | None = None
    source_support: dict[str, int] | None = None
    timestamp_uncertainty_s: float | None = None

    def __post_init__(self) -> None:
        self.modality = str(self.modality).lower()
        self.frame_id = str(self.frame_id).lower()
        allowed_frames = CANONICAL_OBSERVATION_FRAMES.get(self.modality)
        if allowed_frames is None:
            raise ValueError(f"unsupported observation modality: {self.modality}")
        if self.frame_id not in allowed_frames:
            allowed = ", ".join(sorted(allowed_frames))
            raise ValueError(
                f"{self.modality} observations must use frame_id in {{{allowed}}}; "
                f"got {self.frame_id!r}. Convert external frames before fusion."
            )
        self.measurement_timestamp = float(self.measurement_timestamp)
        self.arrival_timestamp = float(self.arrival_timestamp)
        self.measurement = np.asarray(self.measurement, dtype=float)
        if self.covariance is not None:
            self.covariance = np.asarray(self.covariance, dtype=float)
        self.confidence = float(np.clip(self.confidence, 0.0, 1.0))
        self.metadata = dict(self.metadata or {})
        self._normalize_communication_metadata()
        self._normalize_timestamp_uncertainty()

    @property
    def latency(self) -> float:
        return self.arrival_timestamp - self.measurement_timestamp

    @property
    def communication_latency(self) -> float | None:
        if self.sent_timestamp is None or self.received_timestamp is None:
            return None
        return self.received_timestamp - self.sent_timestamp

    @property
    def communication_metadata(self) -> dict[str, Any]:
        return {
            key: getattr(self, key)
            for key in COMMUNICATION_METADATA_KEYS
            if getattr(self, key) is not None
        }

    @property
    def source_lineage_key(self) -> tuple[Any, ...]:
        """Stable key for suppressing repeated source/relay payloads."""

        explicit = self.metadata.get("source_lineage_key") or self.metadata.get("lineage_id")
        if explicit is not None:
            if isinstance(explicit, (list, tuple)):
                normalized = tuple(explicit)
                if normalized and normalized[0] in {"explicit", "source_payload"}:
                    return normalized
                return ("explicit", *normalized)
            return ("explicit", str(explicit))

        sequence = (
            self.metadata.get("sequence_id")
            or self.metadata.get("sequence")
            or self.metadata.get("source_sequence")
            or self.metadata.get("payload_sequence")
            or self.metadata.get("airsim_frame_index")
            or self.measurement_timestamp
        )
        payload = (
            self.metadata.get("payload_id")
            or self.metadata.get("payload_hash")
            or self.metadata.get("payload_digest")
            or self._payload_fingerprint()
        )
        source = self.source_node_id or self.metadata.get("source_node_id") or self.sensor_id
        return (
            "source_payload",
            str(source),
            self.sensor_id,
            self.modality,
            self.payload_kind or self.metadata.get("payload_kind") or "",
            _lineage_scalar(sequence),
            _lineage_scalar(payload),
        )

    def is_stale_at(self, timestamp: float) -> bool:
        if self.stale_after_s is None:
            return False
        reference = self.received_timestamp
        if reference is None:
            reference = self.arrival_timestamp
        return float(timestamp) - float(reference) > self.stale_after_s

    def with_measurement_timestamp(self, timestamp: float) -> "SensorObservation":
        """Return a shallow copy with a modified measurement timestamp."""

        return SensorObservation(
            observation_id=self.observation_id,
            sensor_id=self.sensor_id,
            modality=self.modality,
            measurement_timestamp=timestamp,
            arrival_timestamp=self.arrival_timestamp,
            frame_id=self.frame_id,
            measurement=self.measurement.copy(),
            covariance=None if self.covariance is None else self.covariance.copy(),
            classification_hint=self.classification_hint,
            confidence=self.confidence,
            quality_flags=tuple(self.quality_flags),
            metadata=dict(self.metadata),
            source_node_id=self.source_node_id,
            target_node_id=self.target_node_id,
            relay_node_id=self.relay_node_id,
            link_type=self.link_type,
            sent_timestamp=self.sent_timestamp,
            received_timestamp=self.received_timestamp,
            payload_kind=self.payload_kind,
            stale_after_s=self.stale_after_s,
            source_support=None if self.source_support is None else dict(self.source_support),
            timestamp_uncertainty_s=self.timestamp_uncertainty_s,
        )

    def _normalize_communication_metadata(self) -> None:
        for key in (
            "source_node_id",
            "target_node_id",
            "relay_node_id",
            "link_type",
            "payload_kind",
        ):
            value = getattr(self, key)
            if value is None:
                value = self.metadata.get(key)
            if value is not None:
                value = str(value)
                setattr(self, key, value)
                self.metadata[key] = value

        for key in ("sent_timestamp", "received_timestamp", "stale_after_s"):
            value = getattr(self, key)
            if value is None:
                value = self.metadata.get(key)
            if value is not None:
                value = float(value)
                setattr(self, key, value)
                self.metadata[key] = value

        support = self.source_support
        if support is None:
            support = self.metadata.get("source_support")
        if support is not None:
            normalized = {str(key): int(value) for key, value in dict(support).items()}
            self.source_support = normalized
            self.metadata["source_support"] = normalized

    def _normalize_timestamp_uncertainty(self) -> None:
        candidates: list[float] = []
        if self.timestamp_uncertainty_s is not None:
            candidates.append(abs(float(self.timestamp_uncertainty_s)))

        for key in (
            "timestamp_uncertainty_s",
            "timing_uncertainty_s",
            "clock_drift_s",
            "clock_offset_s",
            "timestamp_drift_s",
            "timestamp_jitter_s",
        ):
            value = self.metadata.get(key)
            if value is not None:
                candidates.append(abs(float(value)))

        for key in (
            "timestamp_uncertainty_ms",
            "timing_uncertainty_ms",
            "clock_drift_ms",
            "timestamp_jitter_ms",
        ):
            value = self.metadata.get(key)
            if value is not None:
                candidates.append(abs(float(value)) / 1000.0)

        if self.arrival_timestamp < self.measurement_timestamp:
            candidates.append(self.measurement_timestamp - self.arrival_timestamp)

        uncertainty = max(candidates) if candidates else 0.0
        self.timestamp_uncertainty_s = float(uncertainty)
        self.metadata["timestamp_uncertainty_s"] = self.timestamp_uncertainty_s
        self.metadata["timing_uncertainty_s"] = self.timestamp_uncertainty_s

    def _payload_fingerprint(self) -> tuple[Any, ...]:
        measurement = tuple(np.round(self.measurement.reshape(-1), decimals=9).tolist())
        covariance = None
        if self.covariance is not None:
            covariance = tuple(np.round(self.covariance.reshape(-1), decimals=9).tolist())
        truth_id = self.metadata.get("truth_id")
        return (
            truth_id,
            round(self.measurement_timestamp, 9),
            measurement,
            covariance,
        )


@dataclass
class GlobalTrack:
    """Fused six-state track in NED coordinates."""

    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    timestamp: float
    track_level: TrackLevel
    source_support: dict[str, int] = field(default_factory=dict)
    identity_likelihood: dict[str, float] = field(default_factory=dict)
    last_nis: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.state = np.asarray(self.state, dtype=float).reshape(6)
        self.covariance = np.asarray(self.covariance, dtype=float).reshape(6, 6)
        self.timestamp = float(self.timestamp)
        if not isinstance(self.track_level, TrackLevel):
            self.track_level = TrackLevel(str(self.track_level))

    @property
    def position(self) -> np.ndarray:
        return self.state[:3]

    @property
    def velocity(self) -> np.ndarray:
        return self.state[3:]

    def copy(self) -> "GlobalTrack":
        return GlobalTrack(
            global_track_id=self.global_track_id,
            state=self.state.copy(),
            covariance=self.covariance.copy(),
            timestamp=self.timestamp,
            track_level=self.track_level,
            source_support=dict(self.source_support),
            identity_likelihood=dict(self.identity_likelihood),
            last_nis=self.last_nis,
            metadata=dict(self.metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
            "timestamp": self.timestamp,
            "track_level": self.track_level.value,
            "source_support": dict(self.source_support),
            "identity_likelihood": dict(self.identity_likelihood),
            "last_nis": self.last_nis,
            "metadata": publication_audit_to_builtin(self.metadata),
        }


@dataclass(frozen=True)
class StructuralAmbiguityCandidateEdge:
    """One truth-free allowed edge inside an ambiguous matching component."""

    opaque_member_track_token: str
    observation_evidence_key: str
    nis: float
    gate_threshold: float
    edge_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "opaque_member_track_token",
            _opaque_digest_token(
                self.opaque_member_track_token,
                "d1-track-sha256:",
                "opaque_member_track_token",
            ),
        )
        object.__setattr__(
            self,
            "observation_evidence_key",
            _opaque_digest_token(
                self.observation_evidence_key,
                "d1-observation-sha256:",
                "observation_evidence_key",
            ),
        )
        nis = _finite_nonnegative(self.nis, "candidate edge nis")
        gate = _finite_positive(self.gate_threshold, "candidate edge gate_threshold")
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
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "StructuralAmbiguityCandidateEdge":
        _require_exact_keys(
            payload,
            {
                "opaque_member_track_token",
                "observation_evidence_key",
                "nis",
                "gate_threshold",
                "edge_roles",
            },
            "structural ambiguity candidate edge",
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


@dataclass(frozen=True)
class StructuralAmbiguityMemberState:
    """Prediction-only state of one D1-local component member."""

    opaque_member_track_token: str
    source_key: str
    state: np.ndarray
    covariance: np.ndarray

    def __post_init__(self) -> None:
        token = _opaque_digest_token(
            self.opaque_member_track_token,
            "d1-track-sha256:",
            "opaque_member_track_token",
        )
        source_key = _identifier(self.source_key, "source_key")
        state = _finite_array(self.state, (6,), "member state")
        covariance = _strict_covariance(
            self.covariance,
            (6, 6),
            "member covariance",
        )
        object.__setattr__(self, "opaque_member_track_token", token)
        object.__setattr__(self, "source_key", source_key)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "covariance", covariance)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "StructuralAmbiguityMemberState":
        _require_exact_keys(
            payload,
            {
                "opaque_member_track_token",
                "source_key",
                "state",
                "covariance",
            },
            "structural ambiguity member state",
        )
        return cls(
            opaque_member_track_token=payload["opaque_member_track_token"],
            source_key=payload["source_key"],
            state=payload["state"],
            covariance=payload["covariance"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "opaque_member_track_token": self.opaque_member_track_token,
            "source_key": self.source_key,
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
        }


@dataclass(frozen=True)
class StructuralAmbiguityObservationEvidence:
    """Cartesian NED evidence retained without an identity assignment."""

    observation_evidence_key: str
    position_ned: np.ndarray
    covariance_ned: np.ndarray
    radial_velocity_observed: bool
    birth_deferred: bool
    velocity_evidence_used: bool = False

    def __post_init__(self) -> None:
        key = _opaque_digest_token(
            self.observation_evidence_key,
            "d1-observation-sha256:",
            "observation_evidence_key",
        )
        if not isinstance(self.radial_velocity_observed, bool):
            raise TypeError("radial_velocity_observed must be a bool")
        if not isinstance(self.birth_deferred, bool):
            raise TypeError("birth_deferred must be a bool")
        if not isinstance(self.velocity_evidence_used, bool):
            raise TypeError("velocity_evidence_used must be a bool")
        if self.velocity_evidence_used:
            raise ValueError(
                "prediction-only structural ambiguity evidence cannot use velocity"
            )
        object.__setattr__(self, "observation_evidence_key", key)
        object.__setattr__(
            self,
            "position_ned",
            _finite_array(self.position_ned, (3,), "observation position_ned"),
        )
        object.__setattr__(
            self,
            "covariance_ned",
            _strict_covariance(
                self.covariance_ned,
                (3, 3),
                "observation covariance_ned",
            ),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "StructuralAmbiguityObservationEvidence":
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
            "structural ambiguity observation evidence",
        )
        return cls(
            observation_evidence_key=payload["observation_evidence_key"],
            position_ned=payload["position_ned"],
            covariance_ned=payload["covariance_ned"],
            radial_velocity_observed=payload["radial_velocity_observed"],
            birth_deferred=payload["birth_deferred"],
            velocity_evidence_used=payload["velocity_evidence_used"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_evidence_key": self.observation_evidence_key,
            "position_ned": self.position_ned.tolist(),
            "covariance_ned": self.covariance_ned.tolist(),
            "radial_velocity_observed": self.radial_velocity_observed,
            "birth_deferred": self.birth_deferred,
            "velocity_evidence_used": self.velocity_evidence_used,
        }


@dataclass(frozen=True)
class StructuralAmbiguityEvidence:
    """Complete truth-free sidecar for one allowed-edge ambiguity component."""

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
    member_states: tuple[StructuralAmbiguityMemberState, ...]
    observations: tuple[StructuralAmbiguityObservationEvidence, ...]
    candidate_edges: tuple[StructuralAmbiguityCandidateEdge, ...]
    component_kinds: tuple[str, ...]
    member_count: int
    observation_count: int
    candidate_edge_count: int
    free_row_count: int
    free_column_count: int
    maximum_matching_cardinality: int
    policy_version: str = STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION
    frame_id: str = "NED"
    member_token_rule: str = STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE
    source_key_rule: str = STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE
    posterior_update_applied: bool = False
    update_mode: str = STRUCTURAL_AMBIGUITY_UPDATE_MODE
    birth_disposition: str = STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION
    component_complete: bool = True
    cross_covariance_available: bool = False
    schema_version: str = STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != STRUCTURAL_AMBIGUITY_EVIDENCE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported structural ambiguity schema: {self.schema_version!r}"
            )
        if self.policy_version != STRUCTURAL_AMBIGUITY_HOLD_POLICY_VERSION:
            raise ValueError(
                f"unsupported structural ambiguity policy: {self.policy_version!r}"
            )
        evidence_id = _opaque_digest_token(
            self.evidence_id,
            "d1-evidence-sha256:",
            "evidence_id",
        )
        component_id = _opaque_digest_token(
            self.component_id,
            "d1-component-sha256:",
            "component_id",
        )
        generation = _nonnegative_integer(
            self.component_generation,
            "component_generation",
        )
        if generation < 1:
            raise ValueError("component_generation must be at least one")
        publisher_node_id = _publisher_identifier(
            self.publisher_node_id,
            "publisher_node_id",
        )
        publisher_epoch = _publisher_identifier(
            self.publisher_epoch,
            "publisher_epoch",
        )
        measurement_timestamp = _finite_timestamp(
            self.measurement_timestamp,
            "measurement_timestamp",
        )
        arrival_timestamp = _finite_timestamp(
            self.arrival_timestamp,
            "arrival_timestamp",
        )
        state_valid_timestamp = _finite_timestamp(
            self.state_valid_timestamp,
            "state_valid_timestamp",
        )
        published_at = _finite_timestamp(self.published_at, "published_at")
        if arrival_timestamp + 1.0e-12 < measurement_timestamp:
            raise ValueError("arrival_timestamp cannot precede measurement_timestamp")
        if abs(state_valid_timestamp - measurement_timestamp) > 1.0e-9:
            raise ValueError(
                "prediction-only member state must be valid at measurement_timestamp"
            )
        if published_at + 1.0e-12 < arrival_timestamp:
            raise ValueError("published_at cannot precede arrival_timestamp")
        sensor_id = _identifier(self.sensor_id, "sensor_id")
        scan_id = _opaque_digest_token(
            self.scan_id,
            "d1-scan-sha256:",
            "scan_id",
        )
        frame_id = _identifier(self.frame_id, "frame_id").upper()
        if frame_id != "NED":
            raise ValueError("structural ambiguity evidence requires frame_id=NED")

        members = tuple(
            item
            if isinstance(item, StructuralAmbiguityMemberState)
            else StructuralAmbiguityMemberState.from_dict(
                _as_mapping(item, "member state")
            )
            for item in self.member_states
        )
        observations = tuple(
            item
            if isinstance(item, StructuralAmbiguityObservationEvidence)
            else StructuralAmbiguityObservationEvidence.from_dict(
                _as_mapping(item, "observation evidence")
            )
            for item in self.observations
        )
        edges = tuple(
            item
            if isinstance(item, StructuralAmbiguityCandidateEdge)
            else StructuralAmbiguityCandidateEdge.from_dict(
                _as_mapping(item, "candidate edge")
            )
            for item in self.candidate_edges
        )
        members = tuple(
            sorted(members, key=lambda item: item.opaque_member_track_token)
        )
        observations = tuple(
            sorted(observations, key=lambda item: item.observation_evidence_key)
        )
        edges = tuple(
            sorted(
                edges,
                key=lambda item: (
                    item.opaque_member_track_token,
                    item.observation_evidence_key,
                    item.edge_roles,
                ),
            )
        )
        kinds = tuple(
            sorted({_identifier(item, "component kind") for item in self.component_kinds})
        )
        if not kinds:
            raise ValueError("component_kinds must not be empty")
        if not members or not observations or not edges:
            raise ValueError(
                "structural ambiguity evidence requires members, observations, and edges"
            )

        member_tokens = [item.opaque_member_track_token for item in members]
        observation_keys = [
            item.observation_evidence_key for item in observations
        ]
        edge_pairs = [
            (item.opaque_member_track_token, item.observation_evidence_key)
            for item in edges
        ]
        if len(set(member_tokens)) != len(member_tokens):
            raise ValueError("member track tokens must be unique")
        if len(set(observation_keys)) != len(observation_keys):
            raise ValueError("observation evidence keys must be unique")
        if len(set(edge_pairs)) != len(edge_pairs):
            raise ValueError("candidate edge pairs must be unique")
        if any(
            token not in set(member_tokens) or key not in set(observation_keys)
            for token, key in edge_pairs
        ):
            raise ValueError("candidate edges must reference component members")
        if set(member_tokens) != {token for token, _ in edge_pairs}:
            raise ValueError("every component member must have a candidate edge")
        if set(observation_keys) != {key for _, key in edge_pairs}:
            raise ValueError("every component observation must have a candidate edge")
        for member in members:
            expected_source_key = structural_ambiguity_source_key(
                publisher_node_id,
                publisher_epoch,
                member.opaque_member_track_token,
            )
            if member.source_key != expected_source_key:
                raise ValueError(
                    "member source_key does not follow the declared source_key_rule"
                )

        member_count = _nonnegative_integer(self.member_count, "member_count")
        observation_count = _nonnegative_integer(
            self.observation_count,
            "observation_count",
        )
        edge_count = _nonnegative_integer(
            self.candidate_edge_count,
            "candidate_edge_count",
        )
        free_rows = _nonnegative_integer(self.free_row_count, "free_row_count")
        free_columns = _nonnegative_integer(
            self.free_column_count,
            "free_column_count",
        )
        matching_cardinality = _nonnegative_integer(
            self.maximum_matching_cardinality,
            "maximum_matching_cardinality",
        )
        if member_count != len(members):
            raise ValueError("member_count does not match member_states")
        if observation_count != len(observations):
            raise ValueError("observation_count does not match observations")
        if edge_count != len(edges):
            raise ValueError("candidate_edge_count does not match candidate_edges")
        if matching_cardinality != member_count - free_rows:
            raise ValueError("free_row_count is inconsistent with matching cardinality")
        if matching_cardinality != observation_count - free_columns:
            raise ValueError(
                "free_column_count is inconsistent with matching cardinality"
            )

        for name, value, expected in (
            ("posterior_update_applied", self.posterior_update_applied, False),
            ("component_complete", self.component_complete, True),
            ("cross_covariance_available", self.cross_covariance_available, False),
        ):
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a bool")
            if value is not expected:
                raise ValueError(f"{name} must be {expected}")
        if self.update_mode != STRUCTURAL_AMBIGUITY_UPDATE_MODE:
            raise ValueError("structural ambiguity update_mode must be prediction_only")
        if self.birth_disposition != STRUCTURAL_AMBIGUITY_BIRTH_DISPOSITION:
            raise ValueError(
                "structural ambiguity birth_disposition must defer component birth"
            )
        if self.member_token_rule != STRUCTURAL_AMBIGUITY_MEMBER_TOKEN_RULE:
            raise ValueError("unsupported member_token_rule")
        if self.source_key_rule != STRUCTURAL_AMBIGUITY_SOURCE_KEY_RULE:
            raise ValueError("unsupported source_key_rule")

        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "component_id", component_id)
        object.__setattr__(self, "component_generation", generation)
        object.__setattr__(self, "publisher_node_id", publisher_node_id)
        object.__setattr__(self, "publisher_epoch", publisher_epoch)
        object.__setattr__(self, "measurement_timestamp", measurement_timestamp)
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(self, "state_valid_timestamp", state_valid_timestamp)
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(self, "sensor_id", sensor_id)
        object.__setattr__(self, "scan_id", scan_id)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "member_states", members)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "candidate_edges", edges)
        object.__setattr__(self, "component_kinds", kinds)
        object.__setattr__(self, "member_count", member_count)
        object.__setattr__(self, "observation_count", observation_count)
        object.__setattr__(self, "candidate_edge_count", edge_count)
        object.__setattr__(self, "free_row_count", free_rows)
        object.__setattr__(self, "free_column_count", free_columns)
        object.__setattr__(
            self,
            "maximum_matching_cardinality",
            matching_cardinality,
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "StructuralAmbiguityEvidence":
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
        return cls(
            **{
                key: payload[key]
                for key in required
            }
        )

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
            "candidate_edges": [item.to_dict() for item in self.candidate_edges],
            "component_kinds": list(self.component_kinds),
            "member_count": self.member_count,
            "observation_count": self.observation_count,
            "candidate_edge_count": self.candidate_edge_count,
            "free_row_count": self.free_row_count,
            "free_column_count": self.free_column_count,
            "maximum_matching_cardinality": self.maximum_matching_cardinality,
            "posterior_update_applied": self.posterior_update_applied,
            "update_mode": self.update_mode,
            "birth_disposition": self.birth_disposition,
            "component_complete": self.component_complete,
            "cross_covariance_available": self.cross_covariance_available,
            "policy_version": self.policy_version,
        }


def structural_ambiguity_member_track_token(
    publisher_node_id: str,
    publisher_epoch: str,
    d1_local_track_id: str,
) -> str:
    """Build the stable opaque source token used by evidence and D2 snapshots."""

    node = _publisher_identifier(publisher_node_id, "publisher_node_id")
    epoch = _publisher_identifier(publisher_epoch, "publisher_epoch")
    local_track_id = _identifier(d1_local_track_id, "d1_local_track_id")
    payload = json.dumps(
        [node, epoch, local_track_id],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    return f"d1-track-sha256:{hashlib.sha256(payload).hexdigest()}"


def structural_ambiguity_source_track_id(
    publisher_epoch: str,
    opaque_member_track_token: str,
) -> str:
    """Return the D2-compatible source_track_id portion of the source key."""

    epoch = _publisher_identifier(publisher_epoch, "publisher_epoch")
    token = _opaque_digest_token(
        opaque_member_track_token,
        "d1-track-sha256:",
        "opaque_member_track_token",
    )
    return f"{epoch}::{token}"


def structural_ambiguity_source_key(
    publisher_node_id: str,
    publisher_epoch: str,
    opaque_member_track_token: str,
) -> str:
    """Return `source_node_id::source_track_id` consumed by the D2 adapter."""

    node = _publisher_identifier(publisher_node_id, "publisher_node_id")
    return (
        f"{node}::"
        f"{structural_ambiguity_source_track_id(publisher_epoch, opaque_member_track_token)}"
    )


@dataclass(frozen=True)
class ObserverLineage:
    """Immutable provenance for one cooperative observer payload."""

    observer_id: str
    sensor_id: str
    observation_id: str
    message_uuid: str
    source_lineage: tuple[str, ...]
    relay_node_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("observer_id", "sensor_id", "observation_id", "message_uuid"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must be non-empty")
            object.__setattr__(self, name, value)
        lineage = tuple(str(item).strip() for item in self.source_lineage if str(item).strip())
        if not lineage:
            raise ValueError("source_lineage must contain an immutable source payload identifier")
        object.__setattr__(self, "source_lineage", lineage)
        object.__setattr__(
            self,
            "relay_node_ids",
            tuple(str(item).strip() for item in self.relay_node_ids if str(item).strip()),
        )

    @property
    def deduplication_key(self) -> tuple[str, ...]:
        return ("message_uuid", self.message_uuid)

    @property
    def lineage_key(self) -> tuple[str, ...]:
        return ("source_lineage", *self.source_lineage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observer_id": self.observer_id,
            "sensor_id": self.sensor_id,
            "observation_id": self.observation_id,
            "message_uuid": self.message_uuid,
            "source_lineage": tuple(self.source_lineage),
            "relay_node_ids": tuple(self.relay_node_ids),
        }


@dataclass(frozen=True)
class CooperativeBearingObservation:
    """Calibrated bearing ray and observer uncertainty at measurement time.

    Rotations map sensor -> body -> NED. Pose and extrinsics covariance use
    ``[translation_ned, small_angle_ned]`` perturbation ordering.
    """

    global_track_id: str
    lineage: ObserverLineage
    measurement_timestamp: float
    arrival_timestamp: float
    platform_position_ned: np.ndarray
    platform_rotation_body_to_ned: np.ndarray
    sensor_translation_body: np.ndarray
    sensor_rotation_sensor_to_body: np.ndarray
    bearing_unit_sensor: np.ndarray
    bearing_covariance: np.ndarray | None
    platform_pose_covariance: np.ndarray | None
    sensor_extrinsics_covariance: np.ndarray | None
    timestamp_uncertainty_s: float = 0.0
    frame_id: str = "ned"

    def __post_init__(self) -> None:
        global_track_id = str(self.global_track_id).strip()
        if not global_track_id:
            raise ValueError("global_track_id must be supplied by the canonical track owner")
        object.__setattr__(self, "global_track_id", global_track_id)
        if str(self.frame_id).lower() != "ned":
            raise ValueError("cooperative bearing observations must use the NED working frame")
        object.__setattr__(self, "frame_id", "ned")
        object.__setattr__(self, "measurement_timestamp", float(self.measurement_timestamp))
        object.__setattr__(self, "arrival_timestamp", float(self.arrival_timestamp))
        object.__setattr__(
            self, "platform_position_ned", np.asarray(self.platform_position_ned, dtype=float).reshape(3)
        )
        object.__setattr__(
            self,
            "platform_rotation_body_to_ned",
            np.asarray(self.platform_rotation_body_to_ned, dtype=float).reshape(3, 3),
        )
        object.__setattr__(
            self, "sensor_translation_body", np.asarray(self.sensor_translation_body, dtype=float).reshape(3)
        )
        object.__setattr__(
            self,
            "sensor_rotation_sensor_to_body",
            np.asarray(self.sensor_rotation_sensor_to_body, dtype=float).reshape(3, 3),
        )
        if not np.isfinite(self.measurement_timestamp) or not np.isfinite(self.arrival_timestamp):
            raise ValueError("measurement_timestamp and arrival_timestamp must be finite")
        for name in (
            "platform_position_ned",
            "platform_rotation_body_to_ned",
            "sensor_translation_body",
            "sensor_rotation_sensor_to_body",
        ):
            if not np.all(np.isfinite(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        bearing = np.asarray(self.bearing_unit_sensor, dtype=float).reshape(3)
        norm = float(np.linalg.norm(bearing))
        if not np.isfinite(norm) or norm <= 1e-12:
            raise ValueError("bearing_unit_sensor must be finite and non-zero")
        object.__setattr__(self, "bearing_unit_sensor", bearing / norm)
        for name, shape in (
            ("bearing_covariance", (2, 2)),
            ("platform_pose_covariance", (6, 6)),
            ("sensor_extrinsics_covariance", (6, 6)),
        ):
            covariance = getattr(self, name)
            if covariance is not None:
                object.__setattr__(self, name, np.asarray(covariance, dtype=float).reshape(shape))
        timestamp_uncertainty_s = abs(float(self.timestamp_uncertainty_s))
        if not np.isfinite(timestamp_uncertainty_s):
            raise ValueError("timestamp_uncertainty_s must be finite")
        object.__setattr__(self, "timestamp_uncertainty_s", timestamp_uncertainty_s)

    @property
    def ray_origin_ned(self) -> np.ndarray:
        return self.platform_position_ned + (
            self.platform_rotation_body_to_ned @ self.sensor_translation_body
        )

    @property
    def ray_direction_ned(self) -> np.ndarray:
        direction = (
            self.platform_rotation_body_to_ned
            @ self.sensor_rotation_sensor_to_body
            @ self.bearing_unit_sensor
        )
        return direction / np.linalg.norm(direction)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "lineage": self.lineage.to_dict(),
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "estimate_frame_id": self.frame_id,
            "platform_position_ned": self.platform_position_ned.tolist(),
            "platform_rotation_body_to_ned": self.platform_rotation_body_to_ned.tolist(),
            "sensor_translation_body": self.sensor_translation_body.tolist(),
            "sensor_rotation_sensor_to_body": self.sensor_rotation_sensor_to_body.tolist(),
            "bearing_unit_sensor": self.bearing_unit_sensor.tolist(),
            "ray_origin_ned": self.ray_origin_ned.tolist(),
            "ray_direction_ned": self.ray_direction_ned.tolist(),
            "bearing_covariance": (
                None if self.bearing_covariance is None else self.bearing_covariance.tolist()
            ),
            "platform_pose_covariance": (
                None
                if self.platform_pose_covariance is None
                else self.platform_pose_covariance.tolist()
            ),
            "sensor_extrinsics_covariance": (
                None
                if self.sensor_extrinsics_covariance is None
                else self.sensor_extrinsics_covariance.tolist()
            ),
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
        }


@dataclass(frozen=True)
class CooperativeObservationGroup:
    """D2-confirmed observations for one canonical track at a common time."""

    global_track_id: str
    estimate_timestamp: float
    observations: tuple[CooperativeBearingObservation, ...]
    target_velocity_ned: np.ndarray | None = None

    def __post_init__(self) -> None:
        global_track_id = str(self.global_track_id).strip()
        if not global_track_id:
            raise ValueError("global_track_id must be non-empty")
        object.__setattr__(self, "global_track_id", global_track_id)
        object.__setattr__(self, "estimate_timestamp", float(self.estimate_timestamp))
        if not np.isfinite(self.estimate_timestamp):
            raise ValueError("estimate_timestamp must be finite")
        observations = tuple(self.observations)
        if any(item.global_track_id != global_track_id for item in observations):
            raise ValueError("all cooperative observations must already share one canonical global_track_id")
        object.__setattr__(self, "observations", observations)
        if self.target_velocity_ned is not None:
            object.__setattr__(
                self, "target_velocity_ned", np.asarray(self.target_velocity_ned, dtype=float).reshape(3)
            )
            if not np.all(np.isfinite(self.target_velocity_ned)):
                raise ValueError("target_velocity_ned must be finite")

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "frame_id": "ned",
            "target_velocity_ned": (
                None if self.target_velocity_ned is None else self.target_velocity_ned.tolist()
            ),
            "observations": tuple(item.to_dict() for item in self.observations),
        }


@dataclass(frozen=True)
class LosIntersectionAngle:
    first_observer_id: str
    second_observer_id: str
    angle_deg: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_observer_id": self.first_observer_id,
            "second_observer_id": self.second_observer_id,
            "angle_deg": self.angle_deg,
        }


@dataclass(frozen=True)
class CooperativeLocalizationSummary:
    """Geometry diagnostics and optional WLS position for one canonical track."""

    global_track_id: str
    estimate_timestamp: float
    accepted: bool
    geometry_reason: str
    quality_flags: tuple[str, ...]
    input_observer_count: int
    unique_observer_count: int
    duplicate_observer_count: int
    observer_lineages: tuple[ObserverLineage, ...]
    measurement_timestamps: tuple[float, ...]
    arrival_timestamps: tuple[float, ...]
    measurement_skew_s: float
    max_propagation_horizon_s: float
    los_intersection_angles: tuple[LosIntersectionAngle, ...]
    information_matrix: np.ndarray
    information_rank: int
    information_condition: float
    residuals_m: tuple[float, ...]
    angular_residuals_deg: tuple[float, ...]
    weighted_residual_rms: float | None
    position_ned: np.ndarray | None
    position_covariance_ned: np.ndarray | None
    covariance_inflation_trace: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "information_matrix", np.asarray(self.information_matrix, dtype=float).reshape(3, 3)
        )
        if self.position_ned is not None:
            object.__setattr__(self, "position_ned", np.asarray(self.position_ned, dtype=float).reshape(3))
        if self.position_covariance_ned is not None:
            object.__setattr__(
                self,
                "position_covariance_ned",
                np.asarray(self.position_covariance_ned, dtype=float).reshape(3, 3),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "frame_id": "ned",
            "accepted": self.accepted,
            "geometry_reason": self.geometry_reason,
            "quality_flags": tuple(self.quality_flags),
            "input_observer_count": self.input_observer_count,
            "unique_observer_count": self.unique_observer_count,
            "duplicate_observer_count": self.duplicate_observer_count,
            "observer_lineages": tuple(item.to_dict() for item in self.observer_lineages),
            "measurement_timestamps": tuple(self.measurement_timestamps),
            "arrival_timestamps": tuple(self.arrival_timestamps),
            "measurement_skew_s": self.measurement_skew_s,
            "max_propagation_horizon_s": self.max_propagation_horizon_s,
            "los_intersection_angles": tuple(
                item.to_dict() for item in self.los_intersection_angles
            ),
            "information_matrix": self.information_matrix.tolist(),
            "information_rank": self.information_rank,
            "information_condition": self.information_condition,
            "residuals_m": tuple(self.residuals_m),
            "angular_residuals_deg": tuple(self.angular_residuals_deg),
            "weighted_residual_rms": self.weighted_residual_rms,
            "position_ned": None if self.position_ned is None else self.position_ned.tolist(),
            "position_covariance_ned": (
                None
                if self.position_covariance_ned is None
                else self.position_covariance_ned.tolist()
            ),
            "covariance_inflation_trace": self.covariance_inflation_trace,
        }


@dataclass(frozen=True)
class CooperativeTrackEstimate:
    """Canonical NED state estimate exchanged for conservative track fusion."""

    global_track_id: str
    state: np.ndarray
    covariance: np.ndarray
    estimate_timestamp: float
    measurement_timestamp: float
    arrival_timestamp: float
    message_uuid: str
    source_lineage: tuple[str, ...]
    timestamp_uncertainty_s: float = 0.0
    frame_id: str = "ned"

    def __post_init__(self) -> None:
        global_track_id = str(self.global_track_id).strip()
        if not global_track_id:
            raise ValueError("global_track_id must be supplied by the canonical track owner")
        object.__setattr__(self, "global_track_id", global_track_id)
        if str(self.frame_id).lower() != "ned":
            raise ValueError("cooperative track estimates must use the NED working frame")
        object.__setattr__(self, "frame_id", "ned")
        object.__setattr__(self, "state", np.asarray(self.state, dtype=float).reshape(6))
        object.__setattr__(self, "covariance", np.asarray(self.covariance, dtype=float).reshape(6, 6))
        if not np.all(np.isfinite(self.state)):
            raise ValueError("state must be finite")
        for name in ("estimate_timestamp", "measurement_timestamp", "arrival_timestamp"):
            object.__setattr__(self, name, float(getattr(self, name)))
            if not np.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        message_uuid = str(self.message_uuid).strip()
        if not message_uuid:
            raise ValueError("message_uuid must be non-empty")
        object.__setattr__(self, "message_uuid", message_uuid)
        source_lineage = tuple(str(item).strip() for item in self.source_lineage if str(item).strip())
        if not source_lineage:
            raise ValueError("source_lineage must be non-empty")
        object.__setattr__(self, "source_lineage", source_lineage)
        timestamp_uncertainty_s = abs(float(self.timestamp_uncertainty_s))
        if not np.isfinite(timestamp_uncertainty_s):
            raise ValueError("timestamp_uncertainty_s must be finite")
        object.__setattr__(self, "timestamp_uncertainty_s", timestamp_uncertainty_s)

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_track_id": self.global_track_id,
            "state": self.state.tolist(),
            "covariance": self.covariance.tolist(),
            "estimate_timestamp": self.estimate_timestamp,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "message_uuid": self.message_uuid,
            "source_lineage": tuple(self.source_lineage),
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
            "frame_id": self.frame_id,
        }


@dataclass(frozen=True)
class CISourceWeight:
    message_uuid: str
    source_lineage: tuple[str, ...]
    weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_uuid": self.message_uuid,
            "source_lineage": tuple(self.source_lineage),
            "weight": self.weight,
        }


@dataclass(frozen=True)
class CovarianceIntersectionSummary:
    """Result and audit evidence for unknown-correlation state fusion."""

    global_track_id: str | None
    estimate_timestamp: float | None
    accepted: bool
    reason: str
    input_count: int
    unique_source_count: int
    duplicate_source_count: int
    duplicate_message_uuids: tuple[str, ...]
    source_weights: tuple[CISourceWeight, ...]
    source_measurement_timestamps: tuple[float, ...]
    source_arrival_timestamps: tuple[float, ...]
    fused_estimate: CooperativeTrackEstimate | None

    def to_dict(self) -> dict[str, Any]:
        estimate = self.fused_estimate
        return {
            "global_track_id": self.global_track_id,
            "estimate_timestamp": self.estimate_timestamp,
            "frame_id": "ned",
            "accepted": self.accepted,
            "reason": self.reason,
            "input_count": self.input_count,
            "unique_source_count": self.unique_source_count,
            "duplicate_source_count": self.duplicate_source_count,
            "duplicate_message_uuids": tuple(self.duplicate_message_uuids),
            "source_weights": tuple(item.to_dict() for item in self.source_weights),
            "source_measurement_timestamps": tuple(self.source_measurement_timestamps),
            "source_arrival_timestamps": tuple(self.source_arrival_timestamps),
            "state": None if estimate is None else estimate.state.tolist(),
            "covariance": None if estimate is None else estimate.covariance.tolist(),
            "measurement_timestamp": None if estimate is None else estimate.measurement_timestamp,
            "arrival_timestamp": None if estimate is None else estimate.arrival_timestamp,
            "message_uuid": None if estimate is None else estimate.message_uuid,
            "source_lineage": () if estimate is None else tuple(estimate.source_lineage),
        }


@dataclass(frozen=True)
class TrackUncertaintySummary:
    """Compact D1 track quality export for downstream offline modules."""

    track_id: str
    global_track_id: str
    valid_at: float
    published_at: float
    track_bucket: int
    track_level: str
    position_covariance_trace: float
    velocity_covariance_trace: float
    a95_m: float
    measurement_age_s: float
    source_support: dict[str, int]
    coverage_cell: str | None = None
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    timestamp_uncertainty_s: float = 0.0
    covariance_limit_reasons: tuple[str, ...] = ()
    covariance_growth_rate: float | None = None
    source_diversity_count: int = 0
    last_nis: float | None = None
    handover_readiness: float = 0.0
    quality_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "global_track_id": self.global_track_id,
            "valid_at": self.valid_at,
            "published_at": self.published_at,
            "track_bucket": self.track_bucket,
            "track_level": self.track_level,
            "position_covariance_trace": self.position_covariance_trace,
            "position_cov_trace": self.position_covariance_trace,
            "velocity_covariance_trace": self.velocity_covariance_trace,
            "velocity_cov_trace": self.velocity_covariance_trace,
            "a95_m": self.a95_m,
            "a95_xy_m": self.a95_m,
            "measurement_age_s": self.measurement_age_s,
            "source_support": dict(self.source_support),
            "coverage_cell": self.coverage_cell,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
            "timing_uncertainty_s": self.timestamp_uncertainty_s,
            "covariance_limit_reasons": tuple(self.covariance_limit_reasons),
            "covariance_growth_rate": self.covariance_growth_rate,
            "source_diversity_count": self.source_diversity_count,
            "last_nis": self.last_nis,
            "handover_readiness": self.handover_readiness,
            "quality_flags": tuple(self.quality_flags),
        }


@dataclass(frozen=True)
class SensorHealthSummary:
    """Per-sensor FDIR-light status derived inside the D1 fusion adapter."""

    sensor_id: str
    status: str
    fault_reason: str | None
    reject_count: int
    isolation_hint: str | None
    recovery_state: str
    observation_count: int = 0
    duplicate_count: int = 0
    oosm_count: int = 0
    stale_count: int = 0
    low_quality_count: int = 0
    anomalous_covariance_count: int = 0
    timestamp_uncertainty_s: float = 0.0
    latest_observation_timestamp: float | None = None
    fault_reasons: tuple[str, ...] = ()
    expected_latency_s: float | None = None
    latency_tolerance_s: float | None = None
    mean_latency_s: float = 0.0
    max_latency_s: float = 0.0
    latency_budget_exceedance_count: int = 0
    latency_budget_exceedance_rate: float = 0.0
    oosm_expected: bool = False
    unexpected_oosm_count: int = 0
    oosm_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id,
            "status": self.status,
            "fault_reason": self.fault_reason,
            "reject_count": self.reject_count,
            "isolation_hint": self.isolation_hint,
            "recovery_state": self.recovery_state,
            "observation_count": self.observation_count,
            "duplicate_count": self.duplicate_count,
            "oosm_count": self.oosm_count,
            "stale_count": self.stale_count,
            "low_quality_count": self.low_quality_count,
            "anomalous_covariance_count": self.anomalous_covariance_count,
            "timestamp_uncertainty_s": self.timestamp_uncertainty_s,
            "timing_uncertainty_s": self.timestamp_uncertainty_s,
            "latest_observation_timestamp": self.latest_observation_timestamp,
            "fault_reasons": tuple(self.fault_reasons),
            "expected_latency_s": self.expected_latency_s,
            "latency_tolerance_s": self.latency_tolerance_s,
            "mean_latency_s": self.mean_latency_s,
            "max_latency_s": self.max_latency_s,
            "latency_budget_exceedance_count": self.latency_budget_exceedance_count,
            "latency_budget_exceedance_rate": self.latency_budget_exceedance_rate,
            "oosm_expected": self.oosm_expected,
            "unexpected_oosm_count": self.unexpected_oosm_count,
            "oosm_rate": self.oosm_rate,
        }


@dataclass(frozen=True)
class LatencyAuditSummary:
    """Fusion replay/latency counters exported for downstream audit."""

    observation_count: int
    replay_count: int
    oosm_observation_count: int
    stale_observation_count: int
    stale_or_oosm_observation_count: int
    max_delay_s: float
    mean_delay_s: float
    duplicate_observation_count: int
    max_replay_observation_count: int
    latency_compensation: bool
    published_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "replay_count": self.replay_count,
            "oosm_observation_count": self.oosm_observation_count,
            "stale_observation_count": self.stale_observation_count,
            "stale_or_oosm_observation_count": self.stale_or_oosm_observation_count,
            "max_delay_s": self.max_delay_s,
            "mean_delay_s": self.mean_delay_s,
            "duplicate_observation_count": self.duplicate_observation_count,
            "max_replay_observation_count": self.max_replay_observation_count,
            "latency_compensation": self.latency_compensation,
            "published_at": self.published_at,
        }


@dataclass(frozen=True)
class FusionBatchSummary:
    """Audit summary for one ordered batch of arrived observations.

    A batch preserves the caller-provided arrival order.  Each observation is
    still validated, audited, associated, and retained individually; only
    repeated fixed-lag history evaluations and end-of-update publication are
    coalesced.
    """

    observation_count: int
    accepted_observation_count: int
    unaccepted_observation_count: int
    duplicate_observation_count: int
    created_track_count: int
    updated_observation_count: int
    updated_track_count: int
    affected_track_ids: tuple[str, ...]
    history_replay_count: int
    origin_replay_count: int
    state_cache_hit_count: int
    state_cache_miss_count: int
    finalization_replay_count: int
    replay_filter_update_count: int
    replay_checkpoint_reuse_count: int
    global_track_materialization_count: int
    sensor_health_snapshot_build_count: int
    association_candidate_pair_count: int
    association_measurement_model_build_count: int
    association_projection_build_count: int
    association_innovation_solve_count: int
    association_radar_track_state_build_count: int
    association_radar_observation_state_build_count: int
    deferred_update_replay_avoidance_count: int
    published_at: float
    ordering: str = "input_arrival_order"

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "accepted_observation_count": self.accepted_observation_count,
            "unaccepted_observation_count": self.unaccepted_observation_count,
            "duplicate_observation_count": self.duplicate_observation_count,
            "created_track_count": self.created_track_count,
            "updated_observation_count": self.updated_observation_count,
            "updated_track_count": self.updated_track_count,
            "affected_track_ids": tuple(self.affected_track_ids),
            "history_replay_count": self.history_replay_count,
            "origin_replay_count": self.origin_replay_count,
            "state_cache_hit_count": self.state_cache_hit_count,
            "state_cache_miss_count": self.state_cache_miss_count,
            "finalization_replay_count": self.finalization_replay_count,
            "replay_filter_update_count": self.replay_filter_update_count,
            "replay_checkpoint_reuse_count": self.replay_checkpoint_reuse_count,
            "global_track_materialization_count": (
                self.global_track_materialization_count
            ),
            "sensor_health_snapshot_build_count": (
                self.sensor_health_snapshot_build_count
            ),
            "association_candidate_pair_count": (
                self.association_candidate_pair_count
            ),
            "association_measurement_model_build_count": (
                self.association_measurement_model_build_count
            ),
            "association_projection_build_count": (
                self.association_projection_build_count
            ),
            "association_innovation_solve_count": (
                self.association_innovation_solve_count
            ),
            "association_radar_track_state_build_count": (
                self.association_radar_track_state_build_count
            ),
            "association_radar_observation_state_build_count": (
                self.association_radar_observation_state_build_count
            ),
            "deferred_update_replay_avoidance_count": (
                self.deferred_update_replay_avoidance_count
            ),
            "published_at": self.published_at,
            "ordering": self.ordering,
        }


@dataclass(frozen=True)
class FusionPerformanceDiagnostics:
    """Bounded cumulative operation counters for batch/scan fusion.

    The snapshot intentionally contains scalar counters only.  It can be
    sampled by an episode profiler without retaining per-scan track snapshots
    or observation histories.
    """

    batch_count: int
    scan_batch_count: int
    observation_count: int
    history_replay_count: int
    origin_replay_count: int
    finalization_replay_count: int
    replay_filter_update_count: int
    replay_checkpoint_reuse_count: int
    checkpoint_state_query_count: int
    fixed_lag_rebase_count: int
    fixed_lag_checkpoint_suffix_reuse_count: int
    replay_checkpoint_prefix_fast_path_count: int
    cached_consistency_refresh_count: int
    global_track_materialization_count: int
    sensor_health_snapshot_build_count: int
    association_candidate_pair_count: int
    association_innovation_solve_count: int
    current_track_count: int
    current_time: float
    schema_version: str = "d1.fusion_performance_diagnostics.v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_count": self.batch_count,
            "scan_batch_count": self.scan_batch_count,
            "observation_count": self.observation_count,
            "history_replay_count": self.history_replay_count,
            "origin_replay_count": self.origin_replay_count,
            "finalization_replay_count": self.finalization_replay_count,
            "replay_filter_update_count": self.replay_filter_update_count,
            "replay_checkpoint_reuse_count": self.replay_checkpoint_reuse_count,
            "checkpoint_state_query_count": self.checkpoint_state_query_count,
            "fixed_lag_rebase_count": self.fixed_lag_rebase_count,
            "fixed_lag_checkpoint_suffix_reuse_count": (
                self.fixed_lag_checkpoint_suffix_reuse_count
            ),
            "replay_checkpoint_prefix_fast_path_count": (
                self.replay_checkpoint_prefix_fast_path_count
            ),
            "cached_consistency_refresh_count": (
                self.cached_consistency_refresh_count
            ),
            "global_track_materialization_count": (
                self.global_track_materialization_count
            ),
            "sensor_health_snapshot_build_count": (
                self.sensor_health_snapshot_build_count
            ),
            "association_candidate_pair_count": (
                self.association_candidate_pair_count
            ),
            "association_innovation_solve_count": (
                self.association_innovation_solve_count
            ),
            "current_track_count": self.current_track_count,
            "current_time": self.current_time,
        }


@dataclass(frozen=True)
class FusionBatchResult:
    """Final publication and audit evidence produced by ``process_batch``."""

    tracks: tuple[GlobalTrack, ...]
    summary: FusionBatchSummary
    structural_ambiguity_evidence: tuple[StructuralAmbiguityEvidence, ...] = ()

    def __post_init__(self) -> None:
        evidence = tuple(
            item
            if isinstance(item, StructuralAmbiguityEvidence)
            else StructuralAmbiguityEvidence.from_dict(
                _as_mapping(item, "structural ambiguity evidence")
            )
            for item in self.structural_ambiguity_evidence
        )
        object.__setattr__(self, "structural_ambiguity_evidence", evidence)

    @property
    def tracks_materialized(self) -> bool:
        """Return whether this result contains a concrete track snapshot."""

        return True

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def current_track_count(self) -> int:
        return self.track_count

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "tracks": tuple(track.to_dict() for track in self.tracks),
            "summary": self.summary.to_dict(),
        }
        if self.structural_ambiguity_evidence:
            payload["structural_ambiguity_evidence"] = [
                item.to_dict() for item in self.structural_ambiguity_evidence
            ]
        return payload


class TracksNotMaterializedError(RuntimeError):
    """Raised when a state-only fusion result is consumed as a track snapshot."""


@dataclass(frozen=True)
class FusionStateUpdateResult:
    """Audit result for a scan whose internal state was updated without publication.

    ``tracks`` deliberately raises instead of returning an empty tuple. A caller
    must invoke ``FusionAdapter.materialize_global_tracks()`` after processing the
    final released scan for its runtime tick.
    """

    summary: FusionBatchSummary
    current_track_count: int
    structural_ambiguity_evidence: tuple[StructuralAmbiguityEvidence, ...] = ()
    tracks_materialized: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if int(self.current_track_count) < 0:
            raise ValueError("current_track_count must be non-negative")
        object.__setattr__(self, "current_track_count", int(self.current_track_count))
        evidence = tuple(
            item
            if isinstance(item, StructuralAmbiguityEvidence)
            else StructuralAmbiguityEvidence.from_dict(
                _as_mapping(item, "structural ambiguity evidence")
            )
            for item in self.structural_ambiguity_evidence
        )
        object.__setattr__(self, "structural_ambiguity_evidence", evidence)

    @property
    def state_updated_at(self) -> float:
        return float(self.summary.published_at)

    @property
    def track_count(self) -> int:
        """Serialized track-array length; always zero without materialization."""

        return 0

    @property
    def tracks(self) -> tuple[GlobalTrack, ...]:
        raise TracksNotMaterializedError(
            "tracks were not materialized; call materialize_global_tracks() "
            "after the final state-only scan"
        )

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "tracks_materialized": False,
            "tracks": [],
            "track_count": self.track_count,
            "state_updated_at": self.state_updated_at,
            "current_track_count": self.current_track_count,
            "summary": self.summary.to_dict(),
        }
        if self.structural_ambiguity_evidence:
            payload["structural_ambiguity_evidence"] = [
                item.to_dict() for item in self.structural_ambiguity_evidence
            ]
        return payload


@dataclass(frozen=True)
class FusionTrackSnapshot:
    """Explicitly materialized current ``GlobalTrack`` publication."""

    tracks: tuple[GlobalTrack, ...]
    published_at: float
    global_track_materialization_count: int
    sensor_health_snapshot_build_count: int
    tracks_materialized: bool = field(default=True, init=False)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def current_track_count(self) -> int:
        return self.track_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "tracks_materialized": True,
            "tracks": [track.to_dict() for track in self.tracks],
            "track_count": self.track_count,
            "current_track_count": self.current_track_count,
            "published_at": self.published_at,
            "global_track_materialization_count": (
                self.global_track_materialization_count
            ),
            "sensor_health_snapshot_build_count": (
                self.sensor_health_snapshot_build_count
            ),
        }


@dataclass(frozen=True)
class FusionQualityRegionSummary:
    """Coverage-cell quality aggregate derived from track summaries."""

    coverage_cell: str
    published_at: float
    track_count: int
    coarse_track_count: int
    stable_track_count: int
    handover_track_count: int
    stale_track_count: int
    mean_a95_m: float
    max_a95_m: float
    max_measurement_age_s: float
    mean_handover_readiness: float
    source_support: dict[str, int]
    source_gap_modalities: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    mean_covariance_growth_rate: float | None = None
    max_covariance_growth_rate: float | None = None
    window_start: float | None = None
    window_end: float | None = None
    sample_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_cell": self.coverage_cell,
            "published_at": self.published_at,
            "track_count": self.track_count,
            "coarse_track_count": self.coarse_track_count,
            "stable_track_count": self.stable_track_count,
            "handover_track_count": self.handover_track_count,
            "stale_track_count": self.stale_track_count,
            "mean_a95_m": self.mean_a95_m,
            "max_a95_m": self.max_a95_m,
            "max_measurement_age_s": self.max_measurement_age_s,
            "mean_handover_readiness": self.mean_handover_readiness,
            "source_support": dict(self.source_support),
            "source_gap_modalities": tuple(self.source_gap_modalities),
            "quality_flags": tuple(self.quality_flags),
            "mean_covariance_growth_rate": self.mean_covariance_growth_rate,
            "max_covariance_growth_rate": self.max_covariance_growth_rate,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True)
class FusionQualityRegionWindowSummary:
    """Windowed coverage-cell quality trend for D4/D6 audit."""

    coverage_cell: str
    window_start: float
    window_end: float
    sample_count: int
    latest_published_at: float
    latest_track_count: int
    mean_a95_m: float
    max_a95_m: float
    mean_measurement_age_s: float
    mean_handover_readiness: float
    source_support: dict[str, int]
    source_gap_modalities: tuple[str, ...] = ()
    source_gap_sample_count: int = 0
    stale_track_sample_count: int = 0
    mean_covariance_growth_rate: float | None = None
    max_covariance_growth_rate: float | None = None
    mean_a95_growth_rate_mps: float | None = None
    measurement_age_growth_rate: float | None = None
    handover_readiness_delta: float | None = None
    latency_observation_count: int = 0
    oosm_observation_count: int = 0
    stale_observation_count: int = 0
    max_delay_s: float = 0.0
    mean_delay_s: float = 0.0
    quality_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage_cell": self.coverage_cell,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "window_duration_s": max(0.0, self.window_end - self.window_start),
            "sample_count": self.sample_count,
            "latest_published_at": self.latest_published_at,
            "latest_track_count": self.latest_track_count,
            "mean_a95_m": self.mean_a95_m,
            "max_a95_m": self.max_a95_m,
            "mean_measurement_age_s": self.mean_measurement_age_s,
            "mean_handover_readiness": self.mean_handover_readiness,
            "source_support": dict(self.source_support),
            "source_gap_modalities": tuple(self.source_gap_modalities),
            "source_gap_sample_count": self.source_gap_sample_count,
            "stale_track_sample_count": self.stale_track_sample_count,
            "mean_covariance_growth_rate": self.mean_covariance_growth_rate,
            "max_covariance_growth_rate": self.max_covariance_growth_rate,
            "mean_a95_growth_rate_mps": self.mean_a95_growth_rate_mps,
            "measurement_age_growth_rate": self.measurement_age_growth_rate,
            "handover_readiness_delta": self.handover_readiness_delta,
            "latency_observation_count": self.latency_observation_count,
            "oosm_observation_count": self.oosm_observation_count,
            "stale_observation_count": self.stale_observation_count,
            "max_delay_s": self.max_delay_s,
            "mean_delay_s": self.mean_delay_s,
            "quality_flags": tuple(self.quality_flags),
        }


@dataclass(frozen=True)
class ReconCueSummary:
    """Compact D1 cue for coarse recon camera pointing over fused tracks."""

    cue_position_ned: np.ndarray
    cue_covariance: np.ndarray
    covariance_trace: float
    active_target_ids: tuple[str, ...]
    track_count: int
    stale_count: int
    total_input_count: int
    excluded_count: int
    default_covariance_count: int
    coverage_cell: str | None = None
    coverage_cells: tuple[str, ...] = ()
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    quality_flags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cue_position_ned",
            np.asarray(self.cue_position_ned, dtype=float).reshape(3),
        )
        object.__setattr__(
            self,
            "cue_covariance",
            np.asarray(self.cue_covariance, dtype=float).reshape(3, 3),
        )
        object.__setattr__(self, "covariance_trace", float(self.covariance_trace))

    @property
    def centroid_ned(self) -> np.ndarray:
        return self.cue_position_ned

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue_position_ned": self.cue_position_ned.tolist(),
            "centroid_ned": self.centroid_ned.tolist(),
            "cue_covariance": self.cue_covariance.tolist(),
            "covariance_trace": self.covariance_trace,
            "active_target_ids": tuple(self.active_target_ids),
            "coverage_cell": self.coverage_cell,
            "coverage_cells": tuple(self.coverage_cells),
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "track_count": self.track_count,
            "stale_count": self.stale_count,
            "total_input_count": self.total_input_count,
            "excluded_count": self.excluded_count,
            "default_covariance_count": self.default_covariance_count,
            "quality_flags": tuple(self.quality_flags),
            "metadata": dict(self.metadata),
        }


def _lineage_scalar(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return tuple(np.asarray(value).reshape(-1).tolist())
    if isinstance(value, (list, tuple)):
        return tuple(_lineage_scalar(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((str(key), _lineage_scalar(val)) for key, val in value.items()))
    if isinstance(value, float):
        return round(value, 9)
    return value


def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _require_exact_keys(
    payload: Mapping[str, Any],
    expected: set[str],
    name: str,
) -> None:
    actual = {str(key) for key in payload}
    missing = expected - actual
    unknown = actual - expected
    if missing or unknown:
        raise ValueError(
            f"{name} keys mismatch: missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )


def _identifier(value: Any, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{name} must not contain control characters")
    return normalized


def _publisher_identifier(value: Any, name: str) -> str:
    normalized = _identifier(value, name)
    if "::" in normalized:
        raise ValueError(f"{name} must not contain the source-key delimiter")
    lowered = normalized.lower()
    if any(marker in lowered for marker in ("truth", "actor", "target_id")):
        raise ValueError(f"{name} must not encode truth, actor, or target identity")
    return normalized


def _opaque_digest_token(value: Any, prefix: str, name: str) -> str:
    token = _identifier(value, name)
    if not token.startswith(prefix):
        raise ValueError(f"{name} must start with {prefix!r}")
    digest = token[len(prefix) :]
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{name} must contain a lowercase SHA-256 digest")
    return token


def _finite_timestamp(value: Any, name: str) -> float:
    timestamp = float(value)
    if not np.isfinite(timestamp):
        raise ValueError(f"{name} must be finite")
    return timestamp


def _finite_nonnegative(value: Any, name: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _finite_positive(value: Any, name: str) -> float:
    number = float(value)
    if not np.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    integer = int(value)
    if integer != value or integer < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return integer


def _finite_array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}; got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")
    return array.copy()


def _strict_covariance(
    value: Any,
    shape: tuple[int, int],
    name: str,
) -> np.ndarray:
    covariance = _finite_array(value, shape, name)
    if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1.0e-10):
        raise ValueError(f"{name} must be symmetric")
    minimum_eigenvalue = float(np.linalg.eigvalsh(covariance).min())
    if minimum_eigenvalue < -1.0e-9:
        raise ValueError(f"{name} must be positive semidefinite")
    return 0.5 * (covariance + covariance.T)
