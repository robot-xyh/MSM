"""D4-adjudicated regional authority contracts owned by D3."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping


REGIONAL_AUTHORITY_INPUT_SCHEMA_V1 = "d3_regional_authority_input_v1"
REGIONAL_ASSIGNMENT_PLAN_SCHEMA_V1 = "d3_regional_assignment_plan_v1"
REGIONAL_OWNER_LAYERS = frozenset({"secondary", "distributed"})


class RegionalPlanAuthorityError(ValueError):
    """Fail-closed rejection of an invalid D4 regional authority input."""

    def __init__(self, reason: str, message: str | None = None) -> None:
        super().__init__(message or reason)
        self.reason = str(reason)


@dataclass(frozen=True)
class RegionalCoalitionCommitEvidence:
    """Minimal D4 commit evidence consumed by D3 without importing D4."""

    target_id: str
    coordinator_id: str
    epoch: int
    lease_expires_at_s: float
    required_member_ids: tuple[str, ...]
    acked_member_ids: tuple[str, ...]
    state: str = "committed"
    atomic_committed: bool = True
    execution_authorized: bool = True
    coalition_id: str | None = None
    coalition_version: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        target_id = str(self.target_id).strip()
        coordinator_id = str(self.coordinator_id).strip()
        if not target_id or not coordinator_id:
            raise ValueError("commit target_id and coordinator_id must not be empty")
        epoch = int(self.epoch)
        lease = float(self.lease_expires_at_s)
        if epoch < 0 or not isfinite(lease) or lease < 0.0:
            raise ValueError("commit epoch and lease must be finite and non-negative")
        required = _unique(self.required_member_ids)
        acked = _unique(self.acked_member_ids)
        if not required:
            raise ValueError("commit required_member_ids must not be empty")
        if not set(acked).issubset(set(required)):
            raise ValueError("commit ACK members must be required members")
        coalition_version = self.coalition_version
        if coalition_version is not None and int(coalition_version) <= 0:
            raise ValueError("coalition_version must be positive when provided")
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "coordinator_id", coordinator_id)
        object.__setattr__(self, "epoch", epoch)
        object.__setattr__(self, "lease_expires_at_s", lease)
        object.__setattr__(self, "required_member_ids", required)
        object.__setattr__(self, "acked_member_ids", acked)
        object.__setattr__(self, "state", str(self.state).strip().lower())
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def missing_member_ids(self) -> tuple[str, ...]:
        acked = set(self.acked_member_ids)
        return tuple(value for value in self.required_member_ids if value not in acked)

    def fail_closed_reason(self, *, now_s: float) -> str | None:
        if self.state != "committed" or not self.atomic_committed:
            return "regional_coalition_not_committed"
        if not self.execution_authorized:
            return "regional_coalition_execution_not_authorized"
        if self.missing_member_ids:
            return "regional_coalition_missing_ack"
        if float(now_s) >= self.lease_expires_at_s:
            return "regional_coalition_lease_expired"
        return None


@dataclass(frozen=True)
class RegionalAuthorityGrant:
    """One D4-adjudicated owner and executable membership for a region."""

    region_id: str
    owner_layer: str
    owner_node_id: str
    owner_role: str
    epoch: int
    source_plan_id: str
    source_plan_version: int
    lease_expires_at_s: float
    target_ids: tuple[str, ...]
    assigned_resource_ids_by_target: Mapping[str, tuple[str, ...]]
    execution_allowed: bool = True
    fail_closed: bool = False
    coalition_commits: tuple[RegionalCoalitionCommitEvidence, ...] = ()
    decision_reason: str = "d4_regional_authority_committed"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        region_id = str(self.region_id).strip()
        owner_layer = str(self.owner_layer).strip().lower()
        owner_node_id = str(self.owner_node_id).strip()
        owner_role = str(self.owner_role).strip()
        source_plan_id = str(self.source_plan_id).strip()
        if not all((region_id, owner_node_id, owner_role, source_plan_id)):
            raise ValueError("regional authority identity fields must not be empty")
        if owner_layer not in REGIONAL_OWNER_LAYERS:
            raise ValueError(f"unsupported regional owner layer: {owner_layer}")
        epoch = int(self.epoch)
        source_version = int(self.source_plan_version)
        lease = float(self.lease_expires_at_s)
        if epoch < 0 or source_version < 0:
            raise ValueError("regional epoch and source plan version must be non-negative")
        if not isfinite(lease) or lease < 0.0:
            raise ValueError("regional lease must be finite and non-negative")
        target_ids = _unique(self.target_ids)
        assignment_map = {
            str(target_id): _unique(resource_ids)
            for target_id, resource_ids in self.assigned_resource_ids_by_target.items()
        }
        if set(assignment_map) != set(target_ids):
            raise ValueError(
                "assigned_resource_ids_by_target keys must equal regional target_ids"
            )
        commits = tuple(self.coalition_commits)
        commit_targets = tuple(item.target_id for item in commits)
        if len(set(commit_targets)) != len(commit_targets):
            raise ValueError("a regional target may have at most one commit evidence item")
        if not set(commit_targets).issubset(set(target_ids)):
            raise ValueError("commit evidence must reference a regional target")
        object.__setattr__(self, "region_id", region_id)
        object.__setattr__(self, "owner_layer", owner_layer)
        object.__setattr__(self, "owner_node_id", owner_node_id)
        object.__setattr__(self, "owner_role", owner_role)
        object.__setattr__(self, "epoch", epoch)
        object.__setattr__(self, "source_plan_id", source_plan_id)
        object.__setattr__(self, "source_plan_version", source_version)
        object.__setattr__(self, "lease_expires_at_s", lease)
        object.__setattr__(self, "target_ids", target_ids)
        object.__setattr__(self, "assigned_resource_ids_by_target", assignment_map)
        object.__setattr__(self, "coalition_commits", commits)
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def commit_by_target(self) -> dict[str, RegionalCoalitionCommitEvidence]:
        return {item.target_id: item for item in self.coalition_commits}


@dataclass(frozen=True)
class RegionalAuthorityInput:
    """Complete D4 decision frame required to publish one regional D3 plan."""

    adjudicated_at_s: float
    grants: tuple[RegionalAuthorityGrant, ...]
    schema: str = REGIONAL_AUTHORITY_INPUT_SCHEMA_V1

    def __post_init__(self) -> None:
        timestamp = float(self.adjudicated_at_s)
        if not isfinite(timestamp) or timestamp < 0.0:
            raise ValueError("adjudicated_at_s must be finite and non-negative")
        if self.schema != REGIONAL_AUTHORITY_INPUT_SCHEMA_V1:
            raise ValueError(f"unsupported regional authority schema: {self.schema}")
        grants = tuple(self.grants)
        if not grants:
            raise ValueError("at least one regional authority grant is required")
        region_ids = tuple(item.region_id for item in grants)
        if len(set(region_ids)) != len(region_ids):
            raise ValueError("regional authority grants must have unique region ids")
        target_ids = tuple(target_id for item in grants for target_id in item.target_ids)
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("a target cannot be governed by multiple regional grants")
        object.__setattr__(self, "adjudicated_at_s", timestamp)
        object.__setattr__(self, "grants", grants)


def _unique(values: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            raise ValueError("regional identifiers must not be empty")
        if value in seen:
            raise ValueError(f"duplicate regional identifier: {value}")
        seen.add(value)
        output.append(value)
    return tuple(output)
