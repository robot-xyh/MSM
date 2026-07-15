"""Shared fail-closed readiness contract for secondary takeover owners."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

from .models import (
    AvailabilityBand,
    CommunicationSummary,
    LinkType,
    PayloadKind,
    ResourceSummary,
    to_jsonable,
)


MIN_SECONDARY_COVERAGE_RATIO = 0.65
MIN_SECONDARY_NETWORK_FULL_VIEW_RATE = 0.80
MIN_SUSTAINED_READINESS_OBSERVATIONS = 3
MIN_SUSTAINED_READINESS_DURATION_S = 0.20

_USABLE_LINK_TYPES = frozenset(
    {LinkType.C2_DIRECT, LinkType.SECONDARY_RELAY, LinkType.VIDEO_CUE}
)
_USABLE_PAYLOAD_KINDS = frozenset(
    {
        PayloadKind.TRACK,
        PayloadKind.BBOX,
        PayloadKind.VIDEO_METADATA,
        PayloadKind.ASSIGNMENT,
        PayloadKind.TERMINAL_ASSOCIATION,
        PayloadKind.RESOURCE_SUMMARY,
        PayloadKind.HEALTH,
    }
)


@dataclass(frozen=True)
class SecondaryReadinessEvidence:
    """Time-bound evidence required before a secondary may own a plan."""

    node_id: str
    current_time_s: float | None = None
    readiness_timestamp_s: float | None = None
    readiness_stale_after_s: float | None = None
    availability_confirmed: bool | None = None
    lease_epoch: int | None = None
    lease_expires_at_s: float | None = None
    heartbeat_timestamp_s: float | None = None
    heartbeat_stale_after_s: float | None = None
    cue_freshness_s: float | None = None
    cue_stale_after_s: float | None = None
    gimbal_pointing_ok: bool | None = None
    communication_received_timestamp_s: float | None = None
    communication_stale_after_s: float | None = None
    coverage_matches_requested_cell: bool | None = None
    coverage_ratio: float | None = None
    network_full_view_rate: float | None = None
    takeover_ready_sustained: bool | None = None
    takeover_ready_since_s: float | None = None
    takeover_ready_observation_count: int | None = None

    @classmethod
    def from_value(cls, value: Any) -> "SecondaryReadinessEvidence":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("secondary readiness evidence must be a mapping or DTO")
        return cls(
            node_id=str(value.get("node_id", "")),
            current_time_s=_optional_float(value.get("current_time_s")),
            readiness_timestamp_s=_optional_float(value.get("readiness_timestamp_s")),
            readiness_stale_after_s=_optional_float(value.get("readiness_stale_after_s")),
            availability_confirmed=_optional_bool(value.get("availability_confirmed")),
            lease_epoch=_optional_int(value.get("lease_epoch")),
            lease_expires_at_s=_optional_float(value.get("lease_expires_at_s")),
            heartbeat_timestamp_s=_optional_float(value.get("heartbeat_timestamp_s")),
            heartbeat_stale_after_s=_optional_float(value.get("heartbeat_stale_after_s")),
            cue_freshness_s=_optional_float(value.get("cue_freshness_s")),
            cue_stale_after_s=_optional_float(value.get("cue_stale_after_s")),
            gimbal_pointing_ok=_optional_bool(value.get("gimbal_pointing_ok")),
            communication_received_timestamp_s=_optional_float(
                value.get("communication_received_timestamp_s")
            ),
            communication_stale_after_s=_optional_float(
                value.get("communication_stale_after_s")
            ),
            coverage_matches_requested_cell=_optional_bool(
                value.get("coverage_matches_requested_cell")
            ),
            coverage_ratio=_optional_float(value.get("coverage_ratio")),
            network_full_view_rate=_optional_float(value.get("network_full_view_rate")),
            takeover_ready_sustained=_optional_bool(
                value.get("takeover_ready_sustained")
            ),
            takeover_ready_since_s=_optional_float(value.get("takeover_ready_since_s")),
            takeover_ready_observation_count=_optional_int(
                value.get("takeover_ready_observation_count")
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class SecondaryReadinessAssessment:
    node_id: str
    ready: bool
    reject_reasons: tuple[str, ...]
    current_time_s: float | None
    lease_valid: bool
    heartbeat_fresh: bool
    cue_fresh: bool
    communication_fresh: bool
    coverage_ready: bool
    network_full_view_ready: bool
    sustained_ready: bool

    @property
    def primary_reject_reason(self) -> str | None:
        return self.reject_reasons[0] if self.reject_reasons else None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def assess_secondary_readiness(
    evidence: SecondaryReadinessEvidence | Mapping[str, Any],
    *,
    expected_current_time_s: float | None = None,
    require_sustained: bool = True,
) -> SecondaryReadinessAssessment:
    """Evaluate every takeover prerequisite; absent evidence always rejects."""

    item = SecondaryReadinessEvidence.from_value(evidence)
    reasons: list[str] = []
    current_time = item.current_time_s
    if current_time is None or not _finite(current_time):
        reasons.append("current_time_missing")
        current_time = None
    elif expected_current_time_s is not None and (
        not _finite(expected_current_time_s)
        or abs(float(current_time) - float(expected_current_time_s)) > 1e-9
    ):
        reasons.append("current_time_mismatch")

    if not item.node_id:
        reasons.append("node_id_missing")
    if item.availability_confirmed is not True:
        reasons.append(
            "availability_unknown"
            if item.availability_confirmed is None
            else "secondary_unavailable"
        )

    lease_valid = True
    if item.lease_epoch is None or int(item.lease_epoch) <= 0:
        reasons.append("lease_epoch_missing")
        lease_valid = False
    if item.lease_expires_at_s is None or not _finite(item.lease_expires_at_s):
        reasons.append("lease_expiry_missing")
        lease_valid = False
    elif current_time is None or float(item.lease_expires_at_s) <= float(current_time):
        reasons.append("lease_expired")
        lease_valid = False

    heartbeat_fresh = _timestamp_is_fresh(
        timestamp=item.heartbeat_timestamp_s,
        stale_after_s=item.heartbeat_stale_after_s,
        current_time_s=current_time,
        missing_timestamp_reason="heartbeat_timestamp_missing",
        missing_window_reason="heartbeat_stale_after_missing",
        stale_reason="heartbeat_stale",
        future_reason="heartbeat_from_future",
        reasons=reasons,
    )

    cue_fresh = True
    if item.cue_freshness_s is None or not _finite(item.cue_freshness_s):
        reasons.append("cue_freshness_missing")
        cue_fresh = False
    elif item.cue_stale_after_s is None or not _positive(item.cue_stale_after_s):
        reasons.append("cue_stale_after_missing")
        cue_fresh = False
    elif not 0.0 <= float(item.cue_freshness_s) <= float(item.cue_stale_after_s):
        reasons.append("cue_stale")
        cue_fresh = False

    if item.gimbal_pointing_ok is not True:
        reasons.append(
            "gimbal_pointing_unknown"
            if item.gimbal_pointing_ok is None
            else "gimbal_not_pointing"
        )

    communication_fresh = _timestamp_is_fresh(
        timestamp=item.communication_received_timestamp_s,
        stale_after_s=item.communication_stale_after_s,
        current_time_s=current_time,
        missing_timestamp_reason="communication_evidence_missing",
        missing_window_reason="communication_stale_after_missing",
        stale_reason="communication_stale",
        future_reason="communication_from_future",
        reasons=reasons,
    )

    coverage_ready = True
    if item.coverage_matches_requested_cell is not True:
        reasons.append(
            "coverage_match_unknown"
            if item.coverage_matches_requested_cell is None
            else "coverage_cell_mismatch"
        )
        coverage_ready = False
    if item.coverage_ratio is None or not _finite(item.coverage_ratio):
        reasons.append("coverage_ratio_missing")
        coverage_ready = False
    elif float(item.coverage_ratio) < MIN_SECONDARY_COVERAGE_RATIO:
        reasons.append("coverage_ratio_low")
        coverage_ready = False

    network_ready = True
    if item.network_full_view_rate is None or not _finite(item.network_full_view_rate):
        reasons.append("network_full_view_rate_missing")
        network_ready = False
    elif float(item.network_full_view_rate) < MIN_SECONDARY_NETWORK_FULL_VIEW_RATE:
        reasons.append("network_full_view_rate_low")
        network_ready = False

    sustained_ready = True
    if require_sustained:
        if item.takeover_ready_sustained is not True:
            reasons.append(
                "sustained_readiness_missing"
                if item.takeover_ready_sustained is None
                else "sustained_readiness_not_met"
            )
            sustained_ready = False
        if item.takeover_ready_observation_count is None:
            reasons.append("sustained_observation_count_missing")
            sustained_ready = False
        elif int(item.takeover_ready_observation_count) < MIN_SUSTAINED_READINESS_OBSERVATIONS:
            reasons.append("sustained_observation_count_low")
            sustained_ready = False
        if item.takeover_ready_since_s is None or not _finite(item.takeover_ready_since_s):
            reasons.append("sustained_ready_since_missing")
            sustained_ready = False
        elif current_time is None or (
            float(item.takeover_ready_since_s) > float(current_time)
            or float(current_time) - float(item.takeover_ready_since_s)
            < MIN_SUSTAINED_READINESS_DURATION_S
        ):
            reasons.append("sustained_readiness_duration_low")
            sustained_ready = False
        _timestamp_is_fresh(
            timestamp=item.readiness_timestamp_s,
            stale_after_s=item.readiness_stale_after_s,
            current_time_s=current_time,
            missing_timestamp_reason="readiness_timestamp_missing",
            missing_window_reason="readiness_stale_after_missing",
            stale_reason="readiness_evidence_stale",
            future_reason="readiness_evidence_from_future",
            reasons=reasons,
        )

    unique_reasons = tuple(dict.fromkeys(reasons))
    return SecondaryReadinessAssessment(
        node_id=item.node_id,
        ready=not unique_reasons,
        reject_reasons=unique_reasons,
        current_time_s=current_time,
        lease_valid=lease_valid,
        heartbeat_fresh=heartbeat_fresh,
        cue_fresh=cue_fresh,
        communication_fresh=communication_fresh,
        coverage_ready=coverage_ready,
        network_full_view_ready=network_ready,
        sustained_ready=sustained_ready,
    )


def readiness_evidence_from_resource(
    resource: ResourceSummary,
    *,
    current_time_s: float | None,
    requested_coverage_cells: Sequence[str],
    communication_summaries: Sequence[CommunicationSummary] | None,
) -> SecondaryReadinessEvidence:
    """Normalize coordinator inputs into the shared strict readiness DTO."""

    task_cells = {str(cell) for cell in requested_coverage_cells if str(cell)}
    coverage_matches = bool(
        not task_cells
        or (
            resource.coverage_cell not in {None, ""}
            and task_cells == {str(resource.coverage_cell)}
        )
    )
    communications = [
        summary
        for summary in communication_summaries or ()
        if summary.involves_node(resource.node_id)
        and summary.link_type in _USABLE_LINK_TYPES
        and summary.payload_kind in _USABLE_PAYLOAD_KINDS
    ]
    freshest = max(communications, key=lambda item: item.received_timestamp, default=None)
    stale_after = float(resource.heartbeat_stale_after_s)
    return SecondaryReadinessEvidence(
        node_id=resource.node_id,
        current_time_s=current_time_s,
        readiness_timestamp_s=resource.readiness_timestamp_s,
        readiness_stale_after_s=resource.readiness_stale_after_s,
        availability_confirmed=bool(
            not resource.operator_hold
            and resource.availability_band != AvailabilityBand.NONE
        ),
        lease_epoch=int(resource.lease_epoch),
        lease_expires_at_s=resource.lease_expires_at_s,
        heartbeat_timestamp_s=resource.heartbeat_timestamp_s,
        heartbeat_stale_after_s=stale_after,
        cue_freshness_s=resource.cue_freshness_s,
        cue_stale_after_s=stale_after,
        gimbal_pointing_ok=resource.gimbal_pointing_ok,
        communication_received_timestamp_s=(
            None if freshest is None else float(freshest.received_timestamp)
        ),
        communication_stale_after_s=(
            None if freshest is None else float(freshest.stale_after_s)
        ),
        coverage_matches_requested_cell=coverage_matches,
        coverage_ratio=resource.secondary_coverage_ratio,
        network_full_view_rate=resource.secondary_network_full_view_rate,
        takeover_ready_sustained=resource.takeover_ready_sustained,
        takeover_ready_since_s=resource.takeover_ready_since_s,
        takeover_ready_observation_count=resource.takeover_ready_observation_count,
    )


def _timestamp_is_fresh(
    *,
    timestamp: float | None,
    stale_after_s: float | None,
    current_time_s: float | None,
    missing_timestamp_reason: str,
    missing_window_reason: str,
    stale_reason: str,
    future_reason: str,
    reasons: list[str],
) -> bool:
    if timestamp is None or not _finite(timestamp):
        reasons.append(missing_timestamp_reason)
        return False
    if stale_after_s is None or not _positive(stale_after_s):
        reasons.append(missing_window_reason)
        return False
    if current_time_s is None:
        return False
    age = float(current_time_s) - float(timestamp)
    if age < 0.0:
        reasons.append(future_reason)
        return False
    if age > float(stale_after_s):
        reasons.append(stale_reason)
        return False
    return True


def _finite(value: Any) -> bool:
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _positive(value: Any) -> bool:
    return _finite(value) and float(value) > 0.0


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
