"""Tick-driven D4 communication and failover contract for AirSim main.

The adapter consumes communication evidence on the caller's clock.  It does
not launch AirSim and does not construct a system AssignmentPlan.  Main owns
those concerns and may use the emitted owner/generation transitions to publish
the corresponding versioned plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .coalition_safety import (
    CoalitionCommitCoordinator,
    CoalitionCommitState,
    CoalitionMemberAck,
)
from .models import C2Health, to_jsonable


EPISODE_COMMUNICATION_SCHEMA = "d4_airsim_episode_communication_v1"
P1_EPISODE_VALIDATION_VERSION = "d4-p1-episode-fault-validation-v2"
EPISODE_FAULT_SCENARIOS = (
    "normal",
    "center_failure",
    "center_secondary_failure",
    "missing_ack",
    "stale_epoch",
    "expired_lease",
    "partition",
)
_EPISODE_FAULT_SCENARIO_ALIASES = {"partition_missing_ack": "partition"}


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value)))


@dataclass(frozen=True)
class EpisodeCommunicationConfig:
    """Static identities and timing bounds for one reset-separated episode."""

    member_ids: tuple[str, ...]
    secondary_node_ids: tuple[str, ...]
    center_node_id: str = "CENTER"
    global_track_id: str = "G-EPISODE-1"
    coalition_id: str = "coalition-episode-1"
    plan_id: str = "plan-episode-1"
    initial_plan_version: int = 1
    initial_epoch: int = 1
    heartbeat_warning_s: float = 0.5
    center_failure_timeout_s: float = 1.0
    secondary_stale_after_s: float = 0.75
    ack_deadline_s: float = 0.75
    ack_validity_s: float = 1.0
    lease_duration_s: float = 10.0
    recovery_validation_ticks: int = 2

    def __post_init__(self) -> None:
        members = _unique(self.member_ids)
        secondaries = _unique(self.secondary_node_ids)
        if not members:
            raise ValueError("member_ids must not be empty")
        if not secondaries:
            raise ValueError("secondary_node_ids must not be empty")
        all_ids = (*members, *secondaries, self.center_node_id)
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("center, secondary, and member identities must be distinct")
        for name in (
            "heartbeat_warning_s",
            "center_failure_timeout_s",
            "secondary_stale_after_s",
            "ack_deadline_s",
            "ack_validity_s",
            "lease_duration_s",
        ):
            if float(getattr(self, name)) <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.center_failure_timeout_s < self.heartbeat_warning_s:
            raise ValueError("center failure timeout must not precede heartbeat warning")
        if int(self.recovery_validation_ticks) < 1:
            raise ValueError("recovery_validation_ticks must be positive")
        object.__setattr__(self, "member_ids", members)
        object.__setattr__(self, "secondary_node_ids", secondaries)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class EpisodeCommunicationTickInput:
    """Communication observations sampled at one AirSim episode timestamp."""

    timestamp_s: float
    center_heartbeat_received: bool
    secondary_heartbeat_ids: tuple[str, ...] = ()
    message_delay_s: float = 0.0
    dropped_ack_member_ids: tuple[str, ...] = ()
    partitioned: bool = False
    center_digest_matches: bool | None = None
    recovery_authorized: bool = False
    member_can_execute: Mapping[str, bool] = field(default_factory=dict)
    ack_epoch_overrides: Mapping[str, int] = field(default_factory=dict)
    ack_plan_version_overrides: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if float(self.timestamp_s) < 0.0:
            raise ValueError("timestamp_s must be non-negative")
        if float(self.message_delay_s) < 0.0:
            raise ValueError("message_delay_s must be non-negative")
        object.__setattr__(
            self, "secondary_heartbeat_ids", _unique(self.secondary_heartbeat_ids)
        )
        object.__setattr__(
            self, "dropped_ack_member_ids", _unique(self.dropped_ack_member_ids)
        )
        object.__setattr__(self, "member_can_execute", dict(self.member_can_execute))
        object.__setattr__(self, "ack_epoch_overrides", dict(self.ack_epoch_overrides))
        object.__setattr__(
            self, "ack_plan_version_overrides", dict(self.ack_plan_version_overrides)
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class EpisodeCommunicationTick:
    """Flat, D6-friendly state emitted after processing one episode tick."""

    timestamp_s: float
    center_health: str
    center_heartbeat_received: bool
    center_heartbeat_age_s: float
    secondary_heartbeat_ids: tuple[str, ...]
    healthy_secondary_ids: tuple[str, ...]
    heartbeat_events: tuple[dict[str, Any], ...]
    message_events: tuple[dict[str, Any], ...]
    acked_member_ids: tuple[str, ...]
    missing_member_ids: tuple[str, ...]
    rejected_ack_reasons: tuple[str, ...]
    lease_expires_at: float | None
    lease_remaining_s: float | None
    lease_valid: bool
    epoch: int
    owner_id: str | None
    executable_owner_ids: tuple[str, ...]
    selected_layer: str
    plan_id: str
    coalition_id: str
    plan_version: int
    coalition_version: int
    plan_transition: str
    commit_state: str
    commit_reason: str
    execution_allowed: bool
    fail_closed: bool
    partitioned: bool
    recovery_state: str
    recovery_validation_count: int
    single_executable_owner: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = EPISODE_COMMUNICATION_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class EpisodeCommunicationReplayReport:
    """Episode-clock fault-injection output ready for main/D6 ingestion."""

    scenario_id: str
    ticks: tuple[EpisodeCommunicationTick, ...]
    passed: bool
    transition_count: int
    executable_owner_ids: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    fault_events: tuple[dict[str, Any], ...] = ()
    timing_metrics_s: dict[str, float | None] = field(default_factory=dict)
    acceptance_limits_s: dict[str, float] = field(default_factory=dict)
    false_degradation_count: int = 0
    audit_fields_complete: bool = False
    validation_scope: str = "episode_time_fault_injection"
    real_rf_network_validated: bool = False
    real_hardware_validated: bool = False
    validation_version: str = P1_EPISODE_VALIDATION_VERSION
    schema: str = "d4_airsim_episode_communication_replay_v2"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class EpisodeFaultValidationMatrixReport:
    """Canonical P1 episode-time cases and their bounded safety outcomes."""

    scenario_ids: tuple[str, ...]
    cases: tuple[EpisodeCommunicationReplayReport, ...]
    summary: dict[str, Any]
    validation_scope: str = "episode_time_fault_injection"
    real_rf_network_validated: bool = False
    real_hardware_validated: bool = False
    validation_version: str = P1_EPISODE_VALIDATION_VERSION
    schema: str = "d4_p1_episode_fault_validation_matrix_v1"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class _PendingAck:
    ack: CoalitionMemberAck
    sent_at: float
    delivery_at: float


class AirSimEpisodeCommunicationAdapter:
    """Advance D4 failover safety using the real episode clock supplied by main."""

    def __init__(self, config: EpisodeCommunicationConfig) -> None:
        self.config = config
        self._coordinator = CoalitionCommitCoordinator()
        self._last_timestamp: float | None = None
        self._last_center_heartbeat = 0.0
        self._secondary_heartbeats: dict[str, float] = {}
        self._center_health = C2Health.NORMAL
        self._layer = "center"
        self._owner_id: str | None = config.center_node_id
        self._epoch = config.initial_epoch
        self._plan_version = config.initial_plan_version
        self._coalition_version = 1
        self._commit_state: CoalitionCommitState | None = None
        self._pending_acks: list[_PendingAck] = []
        self._ack_deadline_at: float | None = None
        self._last_drop_signature: tuple[str, ...] = ()
        self._recovery_validation_count = 0
        self._fallback_started = False

    def tick(self, evidence: EpisodeCommunicationTickInput) -> EpisodeCommunicationTick:
        now = float(evidence.timestamp_s)
        if self._last_timestamp is not None and now <= self._last_timestamp:
            raise ValueError("episode timestamps must be strictly increasing")
        self._last_timestamp = now
        messages: list[dict[str, Any]] = []
        heartbeats = self._record_heartbeats(evidence)
        previous_owner = self._owner_id
        previous_layer = self._layer
        previous_plan = self._plan_version
        previous_epoch = self._epoch
        transition = "none"

        center_age = now - self._last_center_heartbeat
        self._center_health = self._classify_center_health(
            center_age=center_age,
            heartbeat_received=evidence.center_heartbeat_received,
        )
        healthy_secondaries = self._healthy_secondaries(now)

        messages.extend(self._deliver_pending_acks(evidence))
        if self._commit_state is not None:
            before = self._commit_state
            self._commit_state = self._coordinator.evaluate(
                self._commit_state,
                timestamp=now,
                partitioned=evidence.partitioned,
            )
            if self._commit_state.state in {"aborted", "reconfiguring"}:
                self._owner_id = None
                if before.state != self._commit_state.state:
                    transition = self._commit_state.reason

        if evidence.partitioned:
            # Force a fresh generation when the partition clears even if the
            # configured ACK-drop set itself did not change.
            self._last_drop_signature = ("__network_partition__",)
            if self._layer == "center" and self._center_health != C2Health.FAILED:
                # A center-local plan remains valid until center health actually fails.
                pass
            else:
                self._owner_id = None
                self._layer = "partition_hold"
                transition = "partition_fail_closed"
        else:
            desired_layer, desired_owner = self._desired_owner(healthy_secondaries)
            if desired_layer == "center":
                recovery_transition = self._handle_center_recovery(evidence)
                if recovery_transition != "none":
                    transition = recovery_transition
            elif self._takeover_required(desired_layer, desired_owner, evidence):
                transition = self._start_takeover(
                    desired_layer=desired_layer,
                    desired_owner=desired_owner,
                    evidence=evidence,
                    message_events=messages,
                )

        messages.extend(self._deliver_pending_acks(evidence))
        commit_transition = self._finalize_commit(now)
        if commit_transition != "none":
            transition = commit_transition

        if (
            self._commit_state is not None
            and self._ack_deadline_at is not None
            and now >= self._ack_deadline_at
            and self._commit_state.state in {"proposed", "collecting_acks"}
        ):
            self._commit_state = self._coordinator.evaluate(
                self._commit_state, timestamp=now, finalize=True
            )
            self._owner_id = None
            transition = self._commit_state.reason

        if self._commit_state is not None and self._commit_state.state in {
            "aborted",
            "reconfiguring",
        }:
            self._owner_id = None

        plan_changed = (
            previous_owner != self._owner_id
            or previous_layer != self._layer
            or previous_plan != self._plan_version
            or previous_epoch != self._epoch
        )
        if transition == "none" and plan_changed:
            transition = "owner_or_generation_changed"

        state = self._commit_state
        acked = () if state is None else state.acked_member_ids
        missing = () if state is None else state.missing_member_ids
        lease_expires = None if state is None else state.lease_expires_at
        lease_remaining = None if lease_expires is None else lease_expires - now
        lease_valid = bool(lease_expires is None or now < lease_expires)
        execution_allowed = bool(
            self._owner_id is not None
            and (
                self._layer == "center"
                or (
                    state is not None
                    and state.state == "executing"
                    and not state.missing_member_ids
                    and lease_valid
                )
            )
        )
        executable_owners = (self._owner_id,) if execution_allowed else ()
        rejected = tuple(
            str(item.get("reject_reason"))
            for item in messages
            if item.get("status") == "rejected"
        )
        return EpisodeCommunicationTick(
            timestamp_s=now,
            center_health=self._center_health.value,
            center_heartbeat_received=evidence.center_heartbeat_received,
            center_heartbeat_age_s=center_age,
            secondary_heartbeat_ids=evidence.secondary_heartbeat_ids,
            healthy_secondary_ids=healthy_secondaries,
            heartbeat_events=heartbeats,
            message_events=tuple(messages),
            acked_member_ids=acked,
            missing_member_ids=missing,
            rejected_ack_reasons=rejected,
            lease_expires_at=lease_expires,
            lease_remaining_s=lease_remaining,
            lease_valid=lease_valid,
            epoch=self._epoch,
            owner_id=self._owner_id,
            executable_owner_ids=executable_owners,
            selected_layer=self._layer,
            plan_id=self.config.plan_id,
            coalition_id=self.config.coalition_id,
            plan_version=self._plan_version,
            coalition_version=self._coalition_version,
            plan_transition=transition,
            commit_state="center_active" if state is None else state.state,
            commit_reason="center_authority_current" if state is None else state.reason,
            execution_allowed=execution_allowed,
            fail_closed=bool(not execution_allowed and self._layer != "center"),
            partitioned=evidence.partitioned,
            recovery_state=self._recovery_state(evidence),
            recovery_validation_count=self._recovery_validation_count,
            single_executable_owner=len(executable_owners) <= 1,
            metadata={
                **dict(evidence.metadata),
                "arrival_coordination_required": False,
                "multi_member_atomic_authorization_required": len(self.config.member_ids) > 1,
                "validation_scope": "episode_time_fault_injection",
                "real_rf_network_validated": False,
                "previous_owner_id": previous_owner,
                "previous_layer": previous_layer,
                "previous_plan_version": previous_plan,
                "previous_epoch": previous_epoch,
            },
        )

    def _record_heartbeats(
        self, evidence: EpisodeCommunicationTickInput
    ) -> tuple[dict[str, Any], ...]:
        now = float(evidence.timestamp_s)
        events: list[dict[str, Any]] = []
        if evidence.center_heartbeat_received:
            self._last_center_heartbeat = now
        events.append(
            {
                "node_id": self.config.center_node_id,
                "role": "center",
                "received": evidence.center_heartbeat_received,
                "timestamp_s": now,
            }
        )
        unknown = set(evidence.secondary_heartbeat_ids) - set(self.config.secondary_node_ids)
        if unknown:
            raise ValueError(f"unknown secondary heartbeat ids: {sorted(unknown)}")
        for node_id in self.config.secondary_node_ids:
            received = node_id in set(evidence.secondary_heartbeat_ids)
            if received:
                self._secondary_heartbeats[node_id] = now
            events.append(
                {
                    "node_id": node_id,
                    "role": "secondary",
                    "received": received,
                    "timestamp_s": now,
                }
            )
        return tuple(events)

    def _classify_center_health(
        self, *, center_age: float, heartbeat_received: bool
    ) -> C2Health:
        if heartbeat_received and not self._fallback_started:
            return C2Health.NORMAL
        if heartbeat_received and self._fallback_started:
            return C2Health.SUSPECT
        if center_age > self.config.center_failure_timeout_s:
            return C2Health.FAILED
        if center_age > self.config.heartbeat_warning_s:
            return C2Health.SUSPECT
        return C2Health.DEGRADED

    def _healthy_secondaries(self, now: float) -> tuple[str, ...]:
        return tuple(
            node_id
            for node_id in self.config.secondary_node_ids
            if node_id in self._secondary_heartbeats
            and now - self._secondary_heartbeats[node_id]
            <= self.config.secondary_stale_after_s
        )

    def _desired_owner(self, healthy_secondaries: tuple[str, ...]) -> tuple[str, str]:
        if self._center_health != C2Health.FAILED:
            return "center", self.config.center_node_id
        if healthy_secondaries:
            return "secondary", healthy_secondaries[0]
        return "distributed", self.config.member_ids[0]

    def _takeover_required(
        self,
        desired_layer: str,
        desired_owner: str,
        evidence: EpisodeCommunicationTickInput,
    ) -> bool:
        if self._owner_id == desired_owner and self._layer == desired_layer:
            return False
        if self._commit_state is None:
            return True
        if self._commit_state.state in {"aborted", "reconfiguring"}:
            signature = tuple(sorted(evidence.dropped_ack_member_ids))
            return signature != self._last_drop_signature
        if self._commit_state.coordinator_id != desired_owner:
            return True
        return False

    def _start_takeover(
        self,
        *,
        desired_layer: str,
        desired_owner: str,
        evidence: EpisodeCommunicationTickInput,
        message_events: list[dict[str, Any]],
    ) -> str:
        now = float(evidence.timestamp_s)
        self._fallback_started = True
        self._owner_id = None
        self._layer = desired_layer
        self._epoch += 1
        self._plan_version += 1
        self._coalition_version += 1
        self._pending_acks = []
        self._ack_deadline_at = now + self.config.ack_deadline_s
        self._last_drop_signature = tuple(sorted(evidence.dropped_ack_member_ids))
        role = "mobile_high_recon" if desired_layer == "secondary" else "cluster_representative"
        self._commit_state = self._coordinator.propose(
            global_track_id=self.config.global_track_id,
            coalition_id=self.config.coalition_id,
            coalition_version=self._coalition_version,
            plan_id=self.config.plan_id,
            plan_version=self._plan_version,
            epoch=self._epoch,
            coordinator_id=desired_owner,
            coordinator_role=role,
            required_member_ids=self.config.member_ids,
            lease_expires_at=now + self.config.lease_duration_s,
            timestamp=now,
            metadata={
                "takeover_ready": desired_layer == "secondary",
                "arrival_coordination_required": False,
                "atomic_member_authorization": True,
            },
        )
        for member_id in self.config.member_ids:
            sent_at = now
            delay = 0.0 if member_id == desired_owner else evidence.message_delay_s
            dropped = bool(
                evidence.partitioned or member_id in set(evidence.dropped_ack_member_ids)
            )
            event = {
                "kind": "coalition_member_ack",
                "sender_id": member_id,
                "receiver_id": desired_owner,
                "sent_at": sent_at,
                "delivery_at": sent_at + delay,
                "delay_s": delay,
                "dropped": dropped,
                "status": "dropped" if dropped else "queued",
                "drop_reason": (
                    "network_partition"
                    if evidence.partitioned
                    else "configured_missing_ack"
                    if dropped
                    else None
                ),
                "epoch": self._epoch,
                "plan_version": self._plan_version,
                "coalition_version": self._coalition_version,
            }
            message_events.append(event)
            if dropped:
                continue
            ack = CoalitionMemberAck(
                resource_id=member_id,
                global_track_id=self.config.global_track_id,
                coalition_id=self.config.coalition_id,
                coalition_version=self._coalition_version,
                plan_id=self.config.plan_id,
                plan_version=int(
                    evidence.ack_plan_version_overrides.get(
                        member_id, self._plan_version
                    )
                ),
                epoch=int(evidence.ack_epoch_overrides.get(member_id, self._epoch)),
                can_execute=bool(evidence.member_can_execute.get(member_id, True)),
                evidence_timestamp=sent_at,
                valid_until=sent_at + self.config.ack_validity_s,
            )
            self._pending_acks.append(
                _PendingAck(ack=ack, sent_at=sent_at, delivery_at=sent_at + delay)
            )
        return f"{desired_layer}_takeover_proposed"

    def _deliver_pending_acks(
        self, evidence: EpisodeCommunicationTickInput
    ) -> list[dict[str, Any]]:
        now = float(evidence.timestamp_s)
        if self._commit_state is None or evidence.partitioned:
            return []
        delivered: list[dict[str, Any]] = []
        remaining: list[_PendingAck] = []
        for pending in self._pending_acks:
            if pending.delivery_at > now:
                remaining.append(pending)
                continue
            before_acked = self._commit_state.acked_member_ids
            self._commit_state = self._coordinator.record_ack(
                self._commit_state, pending.ack, timestamp=now
            )
            accepted = pending.ack.resource_id in set(self._commit_state.acked_member_ids)
            newly_accepted = accepted and pending.ack.resource_id not in set(before_acked)
            rejection = None
            if not newly_accepted and self._commit_state.reason.startswith("ack_"):
                rejection = self._commit_state.reason
            delivered.append(
                {
                    "kind": "coalition_member_ack",
                    "sender_id": pending.ack.resource_id,
                    "receiver_id": self._commit_state.coordinator_id,
                    "sent_at": pending.sent_at,
                    "delivery_at": now,
                    "delay_s": now - pending.sent_at,
                    "dropped": False,
                    "status": "accepted" if newly_accepted else "rejected",
                    "reject_reason": rejection,
                    "epoch": pending.ack.epoch,
                    "plan_version": pending.ack.plan_version,
                    "coalition_version": pending.ack.coalition_version,
                }
            )
        self._pending_acks = remaining
        return delivered

    def _finalize_commit(self, now: float) -> str:
        if self._commit_state is None:
            return "none"
        if self._commit_state.state == "committed":
            self._commit_state = self._coordinator.mark_executing(
                self._commit_state, timestamp=now
            )
            self._owner_id = self._commit_state.coordinator_id
            return f"{self._layer}_execution_started"
        return "none"

    def _handle_center_recovery(
        self, evidence: EpisodeCommunicationTickInput
    ) -> str:
        if self._layer == "center" and self._owner_id == self.config.center_node_id:
            self._recovery_validation_count = 0
            return "none"
        if not evidence.center_heartbeat_received:
            self._recovery_validation_count = 0
            return "none"
        if evidence.center_digest_matches is True:
            self._recovery_validation_count += 1
        else:
            self._recovery_validation_count = 0
        if (
            self._recovery_validation_count < self.config.recovery_validation_ticks
            or not evidence.recovery_authorized
        ):
            return "center_recovery_dual_track_validation"
        self._epoch += 1
        self._plan_version += 1
        self._coalition_version += 1
        self._layer = "center"
        self._owner_id = self.config.center_node_id
        self._commit_state = None
        self._pending_acks = []
        self._ack_deadline_at = None
        self._fallback_started = False
        self._center_health = C2Health.NORMAL
        self._recovery_validation_count = 0
        return "center_recovery_accepted_after_dual_track_validation"

    def _recovery_state(self, evidence: EpisodeCommunicationTickInput) -> str:
        if self._layer == "center" and self._owner_id == self.config.center_node_id:
            return "center_current"
        if not evidence.center_heartbeat_received:
            return "not_observed"
        if evidence.center_digest_matches is not True:
            return "dual_track_conflict_or_unavailable"
        if self._recovery_validation_count < self.config.recovery_validation_ticks:
            return "dual_track_validating"
        if not evidence.recovery_authorized:
            return "dual_track_validated_waiting_authorization"
        return "recovery_accepted"


def run_episode_communication_replay(
    scenario_id: str,
    *,
    config: EpisodeCommunicationConfig | None = None,
) -> EpisodeCommunicationReplayReport:
    """Run one deterministic fault scenario on an AirSim-compatible episode clock.

    This helper does not launch AirSim or emulate an RF link.  It supplies the
    same monotonic episode timestamps and fault evidence that main can pass to
    :class:`AirSimEpisodeCommunicationAdapter` during a reset-separated run.
    """

    normalized_scenario = _EPISODE_FAULT_SCENARIO_ALIASES.get(scenario_id, scenario_id)
    if normalized_scenario not in EPISODE_FAULT_SCENARIOS:
        raise ValueError(f"unknown episode communication scenario: {scenario_id}")
    cfg = config or EpisodeCommunicationConfig(
        member_ids=("INT-1", "INT-2", "INT-3"),
        secondary_node_ids=("RECON-1",),
    )
    adapter = AirSimEpisodeCommunicationAdapter(cfg)
    ticks: list[EpisodeCommunicationTick] = []
    dt = 0.25
    center_failure_at_s = dt
    secondary_failure_at_s = 2.0
    partition_at_s = 2.0
    duration_s = 6.0
    if normalized_scenario == "expired_lease":
        duration_s = max(
            duration_s,
            center_failure_at_s
            + cfg.center_failure_timeout_s
            + cfg.lease_duration_s
            + 1.5,
        )
    tick_count = int(round(duration_s / dt)) + 1
    for index in range(tick_count):
        now = index * dt
        center_ok = True
        secondary_ids: tuple[str, ...] = cfg.secondary_node_ids
        partitioned = False
        dropped: tuple[str, ...] = ()
        epoch_overrides: dict[str, int] = {}
        if normalized_scenario != "normal" and now >= center_failure_at_s:
            center_ok = False
        if normalized_scenario in {
            "missing_ack",
            "stale_epoch",
            "expired_lease",
            "partition",
        }:
            secondary_ids = ()
        if (
            normalized_scenario == "center_secondary_failure"
            and now >= secondary_failure_at_s
        ):
            secondary_ids = ()
        if normalized_scenario == "missing_ack" and now >= center_failure_at_s:
            dropped = (cfg.member_ids[-1],)
        if normalized_scenario == "stale_epoch" and now >= center_failure_at_s:
            epoch_overrides = {cfg.member_ids[-1]: cfg.initial_epoch}
        if normalized_scenario == "partition" and now >= partition_at_s:
            partitioned = True
        ticks.append(
            adapter.tick(
                EpisodeCommunicationTickInput(
                    timestamp_s=now,
                    center_heartbeat_received=center_ok,
                    secondary_heartbeat_ids=secondary_ids,
                    message_delay_s=0.1,
                    dropped_ack_member_ids=dropped,
                    partitioned=partitioned,
                    ack_epoch_overrides=epoch_overrides,
                    metadata={
                        "scenario_id": normalized_scenario,
                        "requested_scenario_id": scenario_id,
                    },
                )
            )
        )
    owners = _unique(
        tuple(
            owner
            for tick in ticks
            for owner in tick.executable_owner_ids
        )
    )
    failures: list[str] = []
    false_degradation_count = sum(
        tick.selected_layer != "center" for tick in ticks
    ) if normalized_scenario == "normal" else 0
    audit_fields_complete = _episode_audit_fields_complete(ticks)
    if any(not tick.single_executable_owner for tick in ticks):
        failures.append("multiple_executable_owners")
    if false_degradation_count:
        failures.append("false_degradation")
    if not audit_fields_complete:
        failures.append("incomplete_owner_version_epoch_lease_audit")
    if normalized_scenario != "normal" and not any(tick.fail_closed for tick in ticks):
        failures.append("missing_transition_hold")
    secondary_executable_at_s = _first_tick_time(
        ticks, layer="secondary", execution_allowed=True
    )
    distributed_executable_at_s = _first_tick_time(
        ticks, layer="distributed", execution_allowed=True
    )
    center_to_secondary_s = _elapsed(secondary_executable_at_s, center_failure_at_s)
    secondary_to_distributed_s = _elapsed(
        distributed_executable_at_s, secondary_failure_at_s
    )
    acceptance_limits: dict[str, float] = {}
    if normalized_scenario == "center_failure":
        acceptance_limits["center_to_secondary_executable_s"] = 1.5
        if secondary_executable_at_s is None:
            failures.append("secondary_takeover_not_completed")
        elif center_to_secondary_s is None or center_to_secondary_s > 1.5:
            failures.append("secondary_takeover_exceeded_1_5s")
    elif normalized_scenario == "center_secondary_failure":
        acceptance_limits["center_to_secondary_executable_s"] = 1.5
        acceptance_limits["secondary_to_distributed_commit_s"] = 2.5
        if secondary_executable_at_s is None:
            failures.append("secondary_takeover_not_completed_before_secondary_failure")
        elif center_to_secondary_s is None or center_to_secondary_s > 1.5:
            failures.append("secondary_takeover_exceeded_1_5s")
        if distributed_executable_at_s is None:
            failures.append("distributed_takeover_not_completed")
        elif secondary_to_distributed_s is None or secondary_to_distributed_s > 2.5:
            failures.append("distributed_commit_exceeded_2_5s")
        if not _secondary_preceded_distributed(ticks):
            failures.append("secondary_layer_not_active_before_distributed")
    elif normalized_scenario == "missing_ack":
        if not _fail_closed_reason_observed(ticks, "missing_required_acks"):
            failures.append("missing_ack_not_fail_closed")
        if _fallback_execution_observed(ticks):
            failures.append("missing_ack_allowed_fallback_execution")
    elif normalized_scenario == "stale_epoch":
        if not any("ack_epoch_stale" in tick.rejected_ack_reasons for tick in ticks):
            failures.append("stale_epoch_not_rejected")
        if not _fail_closed_reason_observed(ticks, "missing_required_acks"):
            failures.append("stale_epoch_not_fail_closed")
        if _fallback_execution_observed(ticks):
            failures.append("stale_epoch_allowed_fallback_execution")
    elif normalized_scenario == "expired_lease":
        if distributed_executable_at_s is None:
            failures.append("pre_expiry_fallback_not_executable")
        if not _fail_closed_reason_observed(ticks, "coalition_lease_expired"):
            failures.append("expired_lease_not_fail_closed")
    elif normalized_scenario == "partition":
        if distributed_executable_at_s is None:
            failures.append("pre_partition_fallback_not_executable")
        partition_ticks = [tick for tick in ticks if tick.timestamp_s >= partition_at_s]
        if not partition_ticks or any(tick.execution_allowed for tick in partition_ticks):
            failures.append("partition_not_fail_closed")
        if not any(tick.commit_reason == "network_partition" for tick in partition_ticks):
            failures.append("partition_reason_not_audited")

    fault_events = _episode_fault_events(
        normalized_scenario,
        ticks=ticks,
        center_failure_at_s=center_failure_at_s,
        secondary_failure_at_s=secondary_failure_at_s,
        partition_at_s=partition_at_s,
    )
    transitions = sum(tick.plan_transition != "none" for tick in ticks)
    return EpisodeCommunicationReplayReport(
        scenario_id=normalized_scenario,
        ticks=tuple(ticks),
        passed=not failures,
        transition_count=transitions,
        executable_owner_ids=owners,
        failure_reasons=tuple(failures),
        fault_events=fault_events,
        timing_metrics_s={
            "center_failure_injected_at_s": (
                None if normalized_scenario == "normal" else center_failure_at_s
            ),
            "secondary_executable_at_s": secondary_executable_at_s,
            "center_to_secondary_executable_s": center_to_secondary_s,
            "secondary_failure_injected_at_s": (
                secondary_failure_at_s
                if normalized_scenario == "center_secondary_failure"
                else None
            ),
            "distributed_executable_at_s": distributed_executable_at_s,
            "secondary_to_distributed_commit_s": (
                secondary_to_distributed_s
                if normalized_scenario == "center_secondary_failure"
                else None
            ),
        },
        acceptance_limits_s=acceptance_limits,
        false_degradation_count=false_degradation_count,
        audit_fields_complete=audit_fields_complete,
    )


def run_p1_episode_fault_validation_matrix(
    *,
    config: EpisodeCommunicationConfig | None = None,
) -> EpisodeFaultValidationMatrixReport:
    """Run all canonical P1 episode-time fault cases without launching AirSim."""

    cases = tuple(
        run_episode_communication_replay(scenario_id, config=config)
        for scenario_id in EPISODE_FAULT_SCENARIOS
    )
    summary = {
        "scenario_count": len(cases),
        "passed_count": sum(case.passed for case in cases),
        "failed_count": sum(not case.passed for case in cases),
        "all_acceptance_outcomes_met": all(case.passed for case in cases),
        "normal_false_degradation_count": sum(
            case.false_degradation_count for case in cases if case.scenario_id == "normal"
        ),
        "all_audit_fields_complete": all(case.audit_fields_complete for case in cases),
        "real_rf_network_validated": False,
        "real_hardware_validated": False,
    }
    return EpisodeFaultValidationMatrixReport(
        scenario_ids=EPISODE_FAULT_SCENARIOS,
        cases=cases,
        summary=summary,
    )


def _first_tick_time(
    ticks: Sequence[EpisodeCommunicationTick],
    *,
    layer: str,
    execution_allowed: bool,
) -> float | None:
    return next(
        (
            tick.timestamp_s
            for tick in ticks
            if tick.selected_layer == layer
            and tick.execution_allowed is execution_allowed
        ),
        None,
    )


def _elapsed(end_s: float | None, start_s: float) -> float | None:
    return None if end_s is None else max(0.0, float(end_s) - float(start_s))


def _fallback_execution_observed(ticks: Sequence[EpisodeCommunicationTick]) -> bool:
    return any(
        tick.selected_layer in {"secondary", "distributed"} and tick.execution_allowed
        for tick in ticks
    )


def _fail_closed_reason_observed(
    ticks: Sequence[EpisodeCommunicationTick], reason: str
) -> bool:
    return any(
        tick.commit_reason == reason and tick.fail_closed and not tick.execution_allowed
        for tick in ticks
    )


def _secondary_preceded_distributed(
    ticks: Sequence[EpisodeCommunicationTick],
) -> bool:
    secondary_time = _first_tick_time(ticks, layer="secondary", execution_allowed=True)
    distributed_time = _first_tick_time(
        ticks, layer="distributed", execution_allowed=True
    )
    return bool(
        secondary_time is not None
        and distributed_time is not None
        and secondary_time < distributed_time
    )


def _episode_audit_fields_complete(
    ticks: Sequence[EpisodeCommunicationTick],
) -> bool:
    for tick in ticks:
        if not tick.plan_id or not tick.coalition_id:
            return False
        if tick.plan_version < 1 or tick.coalition_version < 1 or tick.epoch < 1:
            return False
        if tick.selected_layer != "center" and tick.lease_expires_at is None:
            return False
        if tick.execution_allowed and tick.selected_layer != "center":
            if not tick.owner_id or not tick.lease_valid or tick.lease_remaining_s is None:
                return False
    return True


def _episode_fault_events(
    scenario_id: str,
    *,
    ticks: Sequence[EpisodeCommunicationTick],
    center_failure_at_s: float,
    secondary_failure_at_s: float,
    partition_at_s: float,
) -> tuple[dict[str, Any], ...]:
    if scenario_id == "normal":
        return ()
    events: list[dict[str, Any]] = [
        {"kind": "center_heartbeat_loss", "injected_at_s": center_failure_at_s}
    ]
    if scenario_id == "center_secondary_failure":
        events.append(
            {
                "kind": "secondary_heartbeat_loss",
                "injected_at_s": secondary_failure_at_s,
            }
        )
    elif scenario_id == "missing_ack":
        events.append(
            {
                "kind": "required_member_ack_drop",
                "injected_at_s": _first_transition_time(ticks, "distributed_takeover_proposed"),
            }
        )
    elif scenario_id == "stale_epoch":
        events.append(
            {
                "kind": "stale_epoch_ack",
                "injected_at_s": _first_transition_time(ticks, "distributed_takeover_proposed"),
            }
        )
    elif scenario_id == "expired_lease":
        lease_expiry = next(
            (tick.lease_expires_at for tick in ticks if tick.lease_expires_at is not None),
            None,
        )
        events.append({"kind": "lease_expiry", "injected_at_s": lease_expiry})
    elif scenario_id == "partition":
        events.append({"kind": "peer_partition", "injected_at_s": partition_at_s})
    return tuple(events)


def _first_transition_time(
    ticks: Sequence[EpisodeCommunicationTick], transition: str
) -> float | None:
    return next(
        (tick.timestamp_s for tick in ticks if tick.plan_transition == transition),
        None,
    )
