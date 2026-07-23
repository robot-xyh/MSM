"""Versioned truth-free identity commitment contract for D2 tracks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Any, Mapping


D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION = (
    "d2.identity-evidence-commitment.v2"
)
D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION = (
    "d2-structural-ambiguity-commitment-v2"
)
D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION = (
    "d2.identity-commitment-recovery-config.v1"
)


class IdentityCommitmentState(str, Enum):
    """Whether a D2-owned track may publish a committed identity mapping."""

    COMMITTED = "committed"
    UNCOMMITTED_AMBIGUITY_HOLD = (
        "identity_uncommitted_ambiguity_hold"
    )
    UNCOMMITTED_AFTER_HOLD = "identity_uncommitted_after_hold"


_ASSOCIATION_STATES = frozenset(
    {"created", "matched", "unmatched", "lost", "dropped"}
)
_SOURCE_OBSERVATION_DISPOSITIONS = frozenset(
    {"target_candidate", "known_false_alarm", "unknown"}
)


@dataclass(frozen=True, slots=True)
class IdentityCommitmentRecoveryConfig:
    """Bound unresolved ambiguity evidence while keeping recovery fail-closed."""

    config_version: str = "d2-identity-recovery-barrier-v1"
    max_blocked_keys_per_track: int = 2_048
    max_total_blocked_keys: int = 250_000
    schema_version: str = (
        D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != D2_IDENTITY_COMMITMENT_RECOVERY_CONFIG_SCHEMA_VERSION
        ):
            raise ValueError(
                "unsupported identity commitment recovery config schema_version"
            )
        version = _identifier(
            self.config_version,
            "identity commitment recovery config_version",
        )
        per_track = _positive_int(
            self.max_blocked_keys_per_track,
            "max_blocked_keys_per_track",
        )
        total = _positive_int(
            self.max_total_blocked_keys,
            "max_total_blocked_keys",
        )
        object.__setattr__(self, "config_version", version)
        object.__setattr__(self, "max_blocked_keys_per_track", per_track)
        object.__setattr__(self, "max_total_blocked_keys", total)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "max_blocked_keys_per_track": self.max_blocked_keys_per_track,
            "max_total_blocked_keys": self.max_total_blocked_keys,
            "overflow_behavior": "fail_closed_until_track_retirement",
        }


@dataclass(frozen=True, slots=True)
class IdentityEvidenceCommitment:
    """Portable D2 decision for one global track at one tracker epoch.

    The contract is truth-free. ``target_candidate`` means only that an
    upstream sensor admitted an original observation as a target candidate;
    it is not simulator truth or a positive identity label.
    """

    global_track_id: str
    association_state: str
    identity_commitment_state: IdentityCommitmentState | str
    reason: str
    state_timestamp: float
    commitment_generation: int = 0
    measurement_timestamp: float | None = None
    arrival_timestamp: float | None = None
    source_observation_evidence_key: str | None = None
    source_observation_evidence_generation: int | None = None
    source_observation_disposition: str | None = None
    ambiguity_component_key: str | None = None
    ambiguity_evidence_id: str | None = None
    ambiguity_component_generation: int | None = None
    publisher_node_id: str | None = None
    publisher_epoch: str | None = None
    active_lease_count: int = 0
    active_lease_keys: tuple[str, ...] = ()
    lease_first_seen_timestamp: float | None = None
    lease_soft_deadline: float | None = None
    lease_hard_deadline: float | None = None
    lease_expired_timestamp: float | None = None
    lease_expiration_reason: str | None = None
    recovery_blocker_count: int = 0
    recovery_not_before_measurement_timestamp: float | None = None
    recovery_blocker_overflow: bool = False
    online_truth_used: bool = False
    schema_version: str = D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION
    policy_version: str = D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != D2_IDENTITY_EVIDENCE_COMMITMENT_SCHEMA_VERSION:
            raise ValueError("unsupported identity commitment schema_version")
        if self.policy_version != D2_IDENTITY_EVIDENCE_COMMITMENT_POLICY_VERSION:
            raise ValueError("unsupported identity commitment policy_version")
        if self.online_truth_used is not False:
            raise ValueError("identity commitment must remain truth-free")

        track_id = _identifier(self.global_track_id, "global_track_id")
        association_state = str(self.association_state).strip().lower()
        if association_state not in _ASSOCIATION_STATES:
            raise ValueError(
                f"unsupported association_state: {self.association_state!r}"
            )
        try:
            commitment_state = IdentityCommitmentState(
                self.identity_commitment_state
            )
        except ValueError as exc:
            raise ValueError(
                "unsupported identity_commitment_state: "
                f"{self.identity_commitment_state!r}"
            ) from exc
        reason = _identifier(self.reason, "identity commitment reason")
        state_timestamp = _timestamp(self.state_timestamp, "state_timestamp")
        commitment_generation = _nonnegative_int(
            self.commitment_generation,
            "commitment_generation",
        )

        measurement_timestamp = _optional_timestamp(
            self.measurement_timestamp,
            "measurement_timestamp",
        )
        arrival_timestamp = _optional_timestamp(
            self.arrival_timestamp,
            "arrival_timestamp",
        )
        if (measurement_timestamp is None) != (arrival_timestamp is None):
            raise ValueError(
                "measurement_timestamp and arrival_timestamp must be paired"
            )
        if (
            measurement_timestamp is not None
            and arrival_timestamp is not None
            and arrival_timestamp + 1.0e-12 < measurement_timestamp
        ):
            raise ValueError(
                "arrival_timestamp cannot precede measurement_timestamp"
            )

        evidence_key = _optional_identifier(
            self.source_observation_evidence_key,
            "source_observation_evidence_key",
        )
        evidence_generation = _optional_nonnegative_int(
            self.source_observation_evidence_generation,
            "source_observation_evidence_generation",
        )
        disposition = _optional_identifier(
            self.source_observation_disposition,
            "source_observation_disposition",
        )
        if disposition is not None and disposition not in (
            _SOURCE_OBSERVATION_DISPOSITIONS
        ):
            raise ValueError("unsupported source observation disposition")
        if (
            evidence_generation is not None
            or disposition is not None
        ) and evidence_key is None:
            raise ValueError(
                "source observation details require an evidence key"
            )

        component_key = _optional_identifier(
            self.ambiguity_component_key,
            "ambiguity_component_key",
        )
        ambiguity_evidence_id = _optional_identifier(
            self.ambiguity_evidence_id,
            "ambiguity_evidence_id",
        )
        ambiguity_generation = _optional_nonnegative_int(
            self.ambiguity_component_generation,
            "ambiguity_component_generation",
        )
        publisher_node_id = _optional_identifier(
            self.publisher_node_id,
            "publisher_node_id",
        )
        publisher_epoch = _optional_identifier(
            self.publisher_epoch,
            "publisher_epoch",
        )
        active_lease_count = _nonnegative_int(
            self.active_lease_count,
            "active_lease_count",
        )
        active_lease_keys = tuple(
            _identifier(item, "active_lease_key")
            for item in self.active_lease_keys
        )
        if len(set(active_lease_keys)) != len(active_lease_keys):
            raise ValueError("active_lease_keys must not contain duplicates")
        if len(active_lease_keys) != active_lease_count:
            raise ValueError(
                "active_lease_count must equal active_lease_keys length"
            )
        lease_first_seen = _optional_timestamp(
            self.lease_first_seen_timestamp,
            "lease_first_seen_timestamp",
        )
        lease_soft_deadline = _optional_timestamp(
            self.lease_soft_deadline,
            "lease_soft_deadline",
        )
        lease_hard_deadline = _optional_timestamp(
            self.lease_hard_deadline,
            "lease_hard_deadline",
        )
        lease_expired_timestamp = _optional_timestamp(
            self.lease_expired_timestamp,
            "lease_expired_timestamp",
        )
        lease_expiration_reason = _optional_identifier(
            self.lease_expiration_reason,
            "lease_expiration_reason",
        )
        recovery_blocker_count = _nonnegative_int(
            self.recovery_blocker_count,
            "recovery_blocker_count",
        )
        recovery_not_before = _optional_timestamp(
            self.recovery_not_before_measurement_timestamp,
            "recovery_not_before_measurement_timestamp",
        )
        if not isinstance(self.recovery_blocker_overflow, bool):
            raise TypeError("recovery_blocker_overflow must be a bool")
        recovery_blocker_overflow = self.recovery_blocker_overflow
        if (
            recovery_blocker_count > 0 or recovery_blocker_overflow
        ) and recovery_not_before is None:
            raise ValueError(
                "identity recovery blockers require a measurement-time watermark"
            )

        if commitment_state == IdentityCommitmentState.COMMITTED:
            if active_lease_count:
                raise ValueError("committed identity cannot carry active leases")
            if disposition in {"known_false_alarm", "unknown"}:
                raise ValueError(
                    "known false alarm or unknown evidence cannot commit identity"
                )
            if (
                recovery_blocker_count
                or recovery_not_before is not None
                or recovery_blocker_overflow
            ):
                raise ValueError(
                    "committed identity cannot retain ambiguity recovery blockers"
                )
        elif (
            commitment_state
            == IdentityCommitmentState.UNCOMMITTED_AMBIGUITY_HOLD
        ):
            if active_lease_count <= 0:
                raise ValueError(
                    "ambiguity-hold identity requires at least one active lease"
                )
            if any(
                value is None
                for value in (
                    component_key,
                    ambiguity_evidence_id,
                    ambiguity_generation,
                    publisher_node_id,
                    publisher_epoch,
                    lease_first_seen,
                    lease_soft_deadline,
                    lease_hard_deadline,
                )
            ):
                raise ValueError(
                    "ambiguity-hold identity lacks lease generation metadata"
                )
            if evidence_key is not None:
                raise ValueError(
                    "uncommitted hold must not expose candidate observation binding"
                )
            if lease_expired_timestamp is not None:
                raise ValueError("active hold cannot already be expired")
            if recovery_not_before is None:
                raise ValueError(
                    "ambiguity-hold identity requires a recovery watermark"
                )
        else:
            if active_lease_count:
                raise ValueError(
                    "after-hold identity cannot carry active leases"
                )
            if lease_expired_timestamp is None or lease_expiration_reason is None:
                raise ValueError(
                    "after-hold identity requires expiry time and reason"
                )
            if evidence_key is not None:
                raise ValueError(
                    "uncommitted after hold must not expose observation binding"
                )
            if recovery_not_before is None:
                raise ValueError(
                    "after-hold identity requires a recovery watermark"
                )

        object.__setattr__(self, "global_track_id", track_id)
        object.__setattr__(self, "association_state", association_state)
        object.__setattr__(
            self,
            "identity_commitment_state",
            commitment_state,
        )
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "state_timestamp", state_timestamp)
        object.__setattr__(
            self,
            "commitment_generation",
            commitment_generation,
        )
        object.__setattr__(
            self,
            "measurement_timestamp",
            measurement_timestamp,
        )
        object.__setattr__(self, "arrival_timestamp", arrival_timestamp)
        object.__setattr__(
            self,
            "source_observation_evidence_key",
            evidence_key,
        )
        object.__setattr__(
            self,
            "source_observation_evidence_generation",
            evidence_generation,
        )
        object.__setattr__(
            self,
            "source_observation_disposition",
            disposition,
        )
        object.__setattr__(self, "ambiguity_component_key", component_key)
        object.__setattr__(self, "ambiguity_evidence_id", ambiguity_evidence_id)
        object.__setattr__(
            self,
            "ambiguity_component_generation",
            ambiguity_generation,
        )
        object.__setattr__(self, "publisher_node_id", publisher_node_id)
        object.__setattr__(self, "publisher_epoch", publisher_epoch)
        object.__setattr__(self, "active_lease_count", active_lease_count)
        object.__setattr__(
            self,
            "active_lease_keys",
            tuple(sorted(active_lease_keys)),
        )
        object.__setattr__(
            self,
            "lease_first_seen_timestamp",
            lease_first_seen,
        )
        object.__setattr__(
            self,
            "lease_soft_deadline",
            lease_soft_deadline,
        )
        object.__setattr__(
            self,
            "lease_hard_deadline",
            lease_hard_deadline,
        )
        object.__setattr__(
            self,
            "lease_expired_timestamp",
            lease_expired_timestamp,
        )
        object.__setattr__(
            self,
            "lease_expiration_reason",
            lease_expiration_reason,
        )
        object.__setattr__(
            self,
            "recovery_blocker_count",
            recovery_blocker_count,
        )
        object.__setattr__(
            self,
            "recovery_not_before_measurement_timestamp",
            recovery_not_before,
        )
        object.__setattr__(
            self,
            "recovery_blocker_overflow",
            recovery_blocker_overflow,
        )

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> "IdentityEvidenceCommitment":
        allowed = {
            "schema_version",
            "policy_version",
            "global_track_id",
            "association_state",
            "identity_commitment_state",
            "reason",
            "state_timestamp",
            "commitment_generation",
            "measurement_timestamp",
            "arrival_timestamp",
            "source_observation_evidence_key",
            "source_observation_evidence_generation",
            "source_observation_disposition",
            "ambiguity_component_key",
            "ambiguity_evidence_id",
            "ambiguity_component_generation",
            "publisher_node_id",
            "publisher_epoch",
            "active_lease_count",
            "active_lease_keys",
            "lease_first_seen_timestamp",
            "lease_soft_deadline",
            "lease_hard_deadline",
            "lease_expired_timestamp",
            "lease_expiration_reason",
            "recovery_blocker_count",
            "recovery_not_before_measurement_timestamp",
            "recovery_blocker_overflow",
            "online_truth_used",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(
                "identity commitment contains unsupported fields: "
                f"{sorted(unknown)}"
            )
        required = {
            "schema_version",
            "policy_version",
            "global_track_id",
            "association_state",
            "identity_commitment_state",
            "reason",
            "state_timestamp",
            "commitment_generation",
            "active_lease_count",
            "active_lease_keys",
            "recovery_blocker_count",
            "recovery_not_before_measurement_timestamp",
            "recovery_blocker_overflow",
            "online_truth_used",
        }
        missing = required - set(payload)
        if missing:
            raise ValueError(
                "identity commitment is missing required fields: "
                f"{sorted(missing)}"
            )
        return cls(**{key: payload[key] for key in payload})

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "global_track_id": self.global_track_id,
            "association_state": self.association_state,
            "identity_commitment_state": (
                self.identity_commitment_state.value
            ),
            "reason": self.reason,
            "state_timestamp": self.state_timestamp,
            "commitment_generation": self.commitment_generation,
            "measurement_timestamp": self.measurement_timestamp,
            "arrival_timestamp": self.arrival_timestamp,
            "source_observation_evidence_key": (
                self.source_observation_evidence_key
            ),
            "source_observation_evidence_generation": (
                self.source_observation_evidence_generation
            ),
            "source_observation_disposition": (
                self.source_observation_disposition
            ),
            "ambiguity_component_key": self.ambiguity_component_key,
            "ambiguity_evidence_id": self.ambiguity_evidence_id,
            "ambiguity_component_generation": (
                self.ambiguity_component_generation
            ),
            "publisher_node_id": self.publisher_node_id,
            "publisher_epoch": self.publisher_epoch,
            "active_lease_count": self.active_lease_count,
            "active_lease_keys": list(self.active_lease_keys),
            "lease_first_seen_timestamp": self.lease_first_seen_timestamp,
            "lease_soft_deadline": self.lease_soft_deadline,
            "lease_hard_deadline": self.lease_hard_deadline,
            "lease_expired_timestamp": self.lease_expired_timestamp,
            "lease_expiration_reason": self.lease_expiration_reason,
            "recovery_blocker_count": self.recovery_blocker_count,
            "recovery_not_before_measurement_timestamp": (
                self.recovery_not_before_measurement_timestamp
            ),
            "recovery_blocker_overflow": self.recovery_blocker_overflow,
            "online_truth_used": False,
        }


def _identifier(value: object, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must be non-empty")
    return result


def _optional_identifier(value: object | None, name: str) -> str | None:
    return None if value is None else _identifier(value, name)


def _timestamp(value: object, name: str) -> float:
    result = float(value)
    if not isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def _optional_timestamp(value: object | None, name: str) -> float | None:
    return None if value is None else _timestamp(value, name)


def _nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < 0 or result != value:
        raise ValueError(f"{name} must be a non-negative integer")
    return result


def _optional_nonnegative_int(value: object | None, name: str) -> int | None:
    return None if value is None else _nonnegative_int(value, name)


def _positive_int(value: object, name: str) -> int:
    result = _nonnegative_int(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result
