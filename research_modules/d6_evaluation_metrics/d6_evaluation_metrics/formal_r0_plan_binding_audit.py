"""Strict D3-to-D4 current-plan binding audit for formal R0 episodes.

The audit consumes persisted episode artifacts only.  It never imports the
runtime stack and never treats a committed D4 decision for an older D3 plan as
evidence for the latest plan.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


FORMAL_R0_PLAN_BINDING_AUDIT_SCHEMA_VERSION = (
    "d6.formal-r0-d3-d4-plan-binding-audit.v1"
)
COMMUNICATION_DISPOSITION_ARTIFACT_NAME = "communication_dispositions.jsonl"
COMMUNICATION_DISPOSITION_SCHEMA_VERSION = (
    "scalable3d-communication-disposition-v1"
)

_D3_TOPIC = "modules.d3.assignment_plan"
_D4_TOPIC = "modules.d4.regional_failover"
_COMMITTED_STATES = frozenset({"committed", "executing"})
_FINAL_DISPOSITIONS = frozenset({"delivered", "dropped", "pending"})
_EPS = 1.0e-9


def audit_formal_r0_plan_binding_episode(
    episode_dir: str | Path,
) -> dict[str, Any]:
    """Audit the final D3/D4 generation and optional transport evidence."""

    directory = Path(episode_dir).resolve()
    online_path = directory / "online_observations.jsonl"
    communication_path = directory / COMMUNICATION_DISPOSITION_ARTIFACT_NAME
    online, online_reason = _load_jsonl(online_path)
    communication, communication_reason = _load_jsonl(communication_path)
    return audit_formal_r0_plan_binding_records(
        online or (),
        online_unavailable_reason=online_reason,
        communication_dispositions=communication,
        communication_unavailable_reason=communication_reason,
    )


def audit_formal_r0_plan_binding_records(
    online_records: Sequence[Mapping[str, Any]],
    *,
    online_unavailable_reason: str | None = None,
    communication_dispositions: Sequence[Mapping[str, Any]] | None = None,
    communication_unavailable_reason: str | None = None,
) -> dict[str, Any]:
    """Audit final-plan identity, authority, coalition closure, and transport."""

    records = _ordered_online_records(online_records)
    d3_record = _latest_topic(records, _D3_TOPIC)
    d4_record = _latest_topic(records, _D4_TOPIC)
    failures: list[str] = []

    if online_unavailable_reason is not None:
        failures.append(
            f"online_observations_unavailable:{online_unavailable_reason}"
        )
    if d3_record is None:
        failures.append("latest_d3_assignment_plan_missing")
    if d4_record is None:
        failures.append("latest_d4_regional_failover_missing")

    communication = _audit_communication_dispositions(
        communication_dispositions,
        unavailable_reason=communication_unavailable_reason,
    )
    failures.extend(communication["failure_reasons"])

    if d3_record is None or d4_record is None:
        failures = _dedupe(failures)
        return {
            "schema_version": FORMAL_R0_PLAN_BINDING_AUDIT_SCHEMA_VERSION,
            "status": "unavailable",
            "evidence_available": False,
            "verified": False,
            "latest_d3_plan": None,
            "latest_d4_decision": None,
            "plan_identity": _unavailable_check(
                "d3_or_d4_final_publication_missing"
            ),
            "authority_epoch": _unavailable_check(
                "d3_or_d4_final_publication_missing"
            ),
            "authority_lease": _unavailable_check(
                "d3_or_d4_final_publication_missing"
            ),
            "coalition_commit": _unavailable_coalition(
                "d3_or_d4_final_publication_missing"
            ),
            "communication_dispositions": communication,
            "failure_reasons": failures,
        }

    d3_payload = _payload(d3_record)
    d4_payload = _payload(d4_record)
    d3_plan_id = _nonempty_text(d3_payload.get("plan_id"))
    d3_plan_version = _nonnegative_int(d3_payload.get("plan_version"))
    if d3_plan_id is None:
        failures.append("latest_d3_plan_id_missing_or_invalid")
    if d3_plan_version is None:
        failures.append("latest_d3_plan_version_missing_or_invalid")

    raw_regions = d4_payload.get("regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        failures.append("latest_d4_regions_missing_or_empty")
        regions: list[Mapping[str, Any]] = []
    elif not all(isinstance(item, Mapping) for item in raw_regions):
        failures.append("latest_d4_regions_invalid")
        regions = [
            item for item in raw_regions if isinstance(item, Mapping)
        ]
    else:
        regions = list(raw_regions)

    d4_timestamp = _finite_float(
        d4_payload.get("timestamp_s", d4_record.get("timestamp"))
    )
    if d4_timestamp is None:
        failures.append("latest_d4_timestamp_missing_or_invalid")

    plan_identity = _audit_plan_identity(
        regions,
        d3_plan_id=d3_plan_id,
        d3_plan_version=d3_plan_version,
    )
    failures.extend(plan_identity["failure_reasons"])

    authority_epoch = _audit_authority_epoch(d3_payload, regions)
    failures.extend(authority_epoch["failure_reasons"])

    authority_lease = _audit_authority_lease(
        d3_payload,
        regions,
        d4_timestamp=d4_timestamp,
    )
    failures.extend(authority_lease["failure_reasons"])

    coalition = _audit_current_plan_coalitions(
        d3_payload,
        regions,
        d4_timestamp=d4_timestamp,
        plan_identity_verified=plan_identity["verified"] is True,
    )
    failures.extend(coalition["failure_reasons"])

    failures = _dedupe(failures)
    verified = (
        plan_identity["verified"] is True
        and coalition["verified"] is True
        and authority_epoch.get("match") is not False
        and authority_lease.get("match") is not False
        and not failures
    )
    return {
        "schema_version": FORMAL_R0_PLAN_BINDING_AUDIT_SCHEMA_VERSION,
        "status": "pass" if verified else "fail_closed",
        "evidence_available": True,
        "verified": verified,
        "latest_d3_plan": {
            "plan_id": d3_plan_id,
            "plan_version": d3_plan_version,
            "sequence": _nonnegative_int(d3_record.get("sequence")),
            "timestamp": _finite_float(d3_record.get("timestamp")),
        },
        "latest_d4_decision": {
            "sequence": _nonnegative_int(d4_record.get("sequence")),
            "timestamp": d4_timestamp,
            "region_count": len(regions),
        },
        "plan_identity": plan_identity,
        "authority_epoch": authority_epoch,
        "authority_lease": authority_lease,
        "coalition_commit": coalition,
        "communication_dispositions": communication,
        "failure_reasons": failures,
    }


def formal_r0_plan_binding_row_metrics(
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Flatten one binding audit into stable formal-R0 row metrics."""

    metrics: dict[str, Any] = {}
    evidence_available = audit.get("evidence_available") is True
    evidence_reason = (
        None
        if evidence_available
        else "d3_or_d4_final_publication_missing"
    )
    _put_metric(
        metrics,
        "d4_current_d3_plan_binding_verified",
        audit.get("verified") if evidence_available else None,
        available=evidence_available,
        unavailable_reason=evidence_reason,
    )

    identity = audit.get("plan_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    identity_available = identity.get("availability") == "available"
    identity_reason = identity.get("unavailable_reason")
    _put_metric(
        metrics,
        "d4_current_d3_plan_id_match",
        identity.get("plan_id_match") if identity_available else None,
        available=identity_available,
        unavailable_reason=identity_reason,
    )
    _put_metric(
        metrics,
        "d4_current_d3_plan_version_match",
        identity.get("plan_version_match") if identity_available else None,
        available=identity_available,
        unavailable_reason=identity_reason,
    )

    epoch = audit.get("authority_epoch")
    epoch = epoch if isinstance(epoch, Mapping) else {}
    epoch_available = epoch.get("availability") == "available"
    _put_metric(
        metrics,
        "d4_current_d3_authority_epoch_match",
        epoch.get("match") if epoch_available else None,
        available=epoch_available,
        unavailable_reason=epoch.get("unavailable_reason"),
    )

    lease = audit.get("authority_lease")
    lease = lease if isinstance(lease, Mapping) else {}
    lease_available = lease.get("availability") == "available"
    _put_metric(
        metrics,
        "d4_current_d3_authority_lease_match",
        lease.get("match") if lease_available else None,
        available=lease_available,
        unavailable_reason=lease.get("unavailable_reason"),
    )

    coalition = audit.get("coalition_commit")
    coalition = coalition if isinstance(coalition, Mapping) else {}
    coalition_available = coalition.get("availability") == "available"
    _put_metric(
        metrics,
        "d4_current_plan_coalition_commit_verified",
        coalition.get("verified") if coalition_available else None,
        available=coalition_available,
        unavailable_reason=coalition.get("unavailable_reason"),
    )
    _put_metric(
        metrics,
        "d4_current_plan_coalition_state_distribution_json",
        coalition.get("state_distribution") if coalition_available else None,
        available=coalition_available,
        unavailable_reason=coalition.get("unavailable_reason"),
    )
    _put_metric(
        metrics,
        "d4_current_plan_uncommitted_target_ids_json",
        coalition.get("uncommitted_target_ids")
        if coalition_available
        else None,
        available=coalition_available,
        unavailable_reason=coalition.get("unavailable_reason"),
    )

    communication = audit.get("communication_dispositions")
    communication = communication if isinstance(communication, Mapping) else {}
    communication_available = communication.get("availability") == "available"
    communication_reason = communication.get("unavailable_reason")
    _put_metric(
        metrics,
        "d4_communication_disposition_validation_verified",
        communication.get("verified") if communication_available else None,
        available=communication_available,
        unavailable_reason=communication_reason,
    )
    _put_metric(
        metrics,
        "d4_communication_disposition_record_count",
        communication.get("record_count") if communication_available else None,
        available=communication_available,
        unavailable_reason=communication_reason,
    )
    _put_metric(
        metrics,
        "d4_communication_disposition_distribution_json",
        communication.get("disposition_distribution")
        if communication_available
        else None,
        available=communication_available,
        unavailable_reason=communication_reason,
    )
    _put_metric(
        metrics,
        "d4_communication_topic_disposition_distribution_json",
        communication.get("d4_topic_disposition_distribution")
        if communication_available
        else None,
        available=communication_available,
        unavailable_reason=communication_reason,
    )
    _put_metric(
        metrics,
        "d4_current_d3_plan_binding_audit_json",
        dict(audit),
        available=True,
        unavailable_reason=None,
    )
    return metrics


def _audit_plan_identity(
    regions: Sequence[Mapping[str, Any]],
    *,
    d3_plan_id: str | None,
    d3_plan_version: int | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    observed: list[dict[str, Any]] = []
    id_matches: list[bool] = []
    version_matches: list[bool] = []
    if d3_plan_id is None or d3_plan_version is None or not regions:
        return {
            **_unavailable_check("current_plan_identity_evidence_incomplete"),
            "plan_id_match": None,
            "plan_version_match": None,
            "observed_regions": observed,
            "failure_reasons": [
                "current_plan_identity_evidence_incomplete"
            ],
        }
    for index, region in enumerate(regions):
        ownership = region.get("ownership")
        ownership = ownership if isinstance(ownership, Mapping) else {}
        region_id = _nonempty_text(region.get("region_id")) or f"index-{index}"
        observed_id = _nonempty_text(ownership.get("plan_id"))
        observed_version = _nonnegative_int(ownership.get("plan_version"))
        id_match = observed_id == d3_plan_id
        version_match = observed_version == d3_plan_version
        id_matches.append(id_match)
        version_matches.append(version_match)
        observed.append(
            {
                "region_id": region_id,
                "plan_id": observed_id,
                "plan_version": observed_version,
            }
        )
        if observed_id is None:
            reasons.append(
                f"latest_d4_plan_id_missing:region={region_id}"
            )
        elif not id_match:
            reasons.append(
                "latest_d4_plan_id_mismatch:"
                f"region={region_id}:d3={d3_plan_id}:d4={observed_id}"
            )
        if observed_version is None:
            reasons.append(
                f"latest_d4_plan_version_missing:region={region_id}"
            )
        elif not version_match:
            reasons.append(
                "latest_d4_plan_version_mismatch:"
                f"region={region_id}:d3={d3_plan_version}:"
                f"d4={observed_version}"
            )
    plan_id_match = bool(id_matches) and all(id_matches)
    plan_version_match = bool(version_matches) and all(version_matches)
    return {
        "availability": "available",
        "unavailable_reason": None,
        "verified": plan_id_match and plan_version_match,
        "plan_id_match": plan_id_match,
        "plan_version_match": plan_version_match,
        "expected_plan_id": d3_plan_id,
        "expected_plan_version": d3_plan_version,
        "observed_regions": observed,
        "failure_reasons": _dedupe(reasons),
    }


def _audit_authority_epoch(
    d3_payload: Mapping[str, Any],
    regions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    observed = _region_authority_values(regions, "epoch", _nonnegative_int)
    if observed is None:
        return {
            **_unavailable_check("d4_authority_epoch_missing"),
            "match": None,
            "failure_reasons": [],
        }

    assignments = d3_payload.get("assignments")
    expected_by_region: dict[str, set[int]] = defaultdict(set)
    complete = isinstance(assignments, list)
    if isinstance(assignments, list):
        for assignment in assignments:
            if not isinstance(assignment, Mapping):
                complete = False
                continue
            region_id = _nonempty_text(
                assignment.get("regional_region_id")
            )
            epoch = _nonnegative_int(assignment.get("regional_epoch"))
            if region_id is None or epoch is None:
                complete = False
                continue
            expected_by_region[region_id].add(epoch)
    reasons: list[str] = []
    if complete and expected_by_region:
        match = True
        for region_id, d4_epoch in observed.items():
            expected = expected_by_region.get(region_id)
            if expected is None or expected != {d4_epoch}:
                match = False
                reasons.append(
                    "latest_d4_authority_epoch_mismatch:"
                    f"region={region_id}:d3={sorted(expected or ())}:"
                    f"d4={d4_epoch}"
                )
        return {
            "availability": "available",
            "unavailable_reason": None,
            "match": match,
            "comparison_scope": "per_region_assignment_epoch",
            "expected_by_region": {
                key: sorted(values)
                for key, values in sorted(expected_by_region.items())
            },
            "observed_by_region": dict(sorted(observed.items())),
            "failure_reasons": reasons,
        }

    metadata = d3_payload.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    expected_max = _nonnegative_int(metadata.get("regional_max_epoch"))
    if expected_max is None:
        expected_max = _nonnegative_int(metadata.get("secondary_leader_epoch"))
    if expected_max is None:
        return {
            **_unavailable_check("d3_authority_epoch_not_published"),
            "match": None,
            "observed_by_region": dict(sorted(observed.items())),
            "failure_reasons": [],
        }
    observed_max = max(observed.values())
    match = observed_max == expected_max
    if not match:
        reasons.append(
            "latest_d4_authority_epoch_mismatch:"
            f"scope=max:d3={expected_max}:d4={observed_max}"
        )
    return {
        "availability": "available",
        "unavailable_reason": None,
        "match": match,
        "comparison_scope": "metadata_max_epoch",
        "expected_max_epoch": expected_max,
        "observed_max_epoch": observed_max,
        "observed_by_region": dict(sorted(observed.items())),
        "failure_reasons": reasons,
    }


def _audit_authority_lease(
    d3_payload: Mapping[str, Any],
    regions: Sequence[Mapping[str, Any]],
    *,
    d4_timestamp: float | None,
) -> dict[str, Any]:
    observed = _region_authority_values(
        regions,
        "lease_expires_at_s",
        _finite_float,
    )
    if observed is None:
        return {
            **_unavailable_check("d4_authority_lease_missing"),
            "match": None,
            "failure_reasons": ["latest_d4_authority_lease_missing"],
        }
    reasons: list[str] = []
    if d4_timestamp is None:
        reasons.append("latest_d4_timestamp_missing_for_lease_check")
    else:
        for region_id, lease in observed.items():
            if d4_timestamp >= lease:
                reasons.append(
                    "latest_d4_authority_lease_expired:"
                    f"region={region_id}:decision={d4_timestamp}:lease={lease}"
                )

    assignments = d3_payload.get("assignments")
    expected_by_region: dict[str, set[float]] = defaultdict(set)
    complete = isinstance(assignments, list)
    if isinstance(assignments, list):
        for assignment in assignments:
            if not isinstance(assignment, Mapping):
                complete = False
                continue
            region_id = _nonempty_text(
                assignment.get("regional_region_id")
            )
            lease = _finite_float(
                assignment.get("regional_lease_expires_at_s")
            )
            if region_id is None or lease is None:
                complete = False
                continue
            expected_by_region[region_id].add(lease)
    if complete and expected_by_region:
        match = True
        for region_id, d4_lease in observed.items():
            expected = expected_by_region.get(region_id)
            if (
                expected is None
                or len(expected) != 1
                or not _float_equal(next(iter(expected)), d4_lease)
            ):
                match = False
                reasons.append(
                    "latest_d4_authority_lease_mismatch:"
                    f"region={region_id}:d3={sorted(expected or ())}:"
                    f"d4={d4_lease}"
                )
        return {
            "availability": "available",
            "unavailable_reason": None,
            "match": match and not any(
                reason.startswith("latest_d4_authority_lease_expired")
                for reason in reasons
            ),
            "comparison_scope": "per_region_assignment_lease",
            "expected_by_region": {
                key: sorted(values)
                for key, values in sorted(expected_by_region.items())
            },
            "observed_by_region": dict(sorted(observed.items())),
            "failure_reasons": reasons,
        }

    metadata = d3_payload.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    expected_min = _finite_float(
        metadata.get("regional_min_lease_expires_at_s")
    )
    if expected_min is None:
        expected_min = _finite_float(
            metadata.get("secondary_lease_expires_at_s")
        )
    if expected_min is None:
        return {
            **_unavailable_check("d3_authority_lease_not_published"),
            "match": None,
            "observed_by_region": dict(sorted(observed.items())),
            "failure_reasons": reasons,
        }
    observed_min = min(observed.values())
    match = _float_equal(observed_min, expected_min)
    if not match:
        reasons.append(
            "latest_d4_authority_lease_mismatch:"
            f"scope=min:d3={expected_min}:d4={observed_min}"
        )
    if any(
        reason.startswith("latest_d4_authority_lease_expired")
        for reason in reasons
    ):
        match = False
    return {
        "availability": "available",
        "unavailable_reason": None,
        "match": match,
        "comparison_scope": "metadata_min_lease",
        "expected_min_lease_expires_at_s": expected_min,
        "observed_min_lease_expires_at_s": observed_min,
        "observed_by_region": dict(sorted(observed.items())),
        "failure_reasons": reasons,
    }


def _audit_current_plan_coalitions(
    d3_payload: Mapping[str, Any],
    regions: Sequence[Mapping[str, Any]],
    *,
    d4_timestamp: float | None,
    plan_identity_verified: bool,
) -> dict[str, Any]:
    assignments = d3_payload.get("assignments")
    if not isinstance(assignments, list):
        return {
            **_unavailable_coalition("d3_assignments_missing_or_invalid"),
            "failure_reasons": ["current_plan_d3_assignments_missing_or_invalid"],
        }

    resources_by_target: dict[str, set[str]] = defaultdict(set)
    reasons: list[str] = []
    for index, assignment in enumerate(assignments):
        if not isinstance(assignment, Mapping):
            reasons.append(f"current_plan_assignment_invalid:index={index}")
            continue
        target_id = _nonempty_text(assignment.get("global_track_id"))
        resource_id = _nonempty_text(assignment.get("resource_id"))
        if target_id is None or resource_id is None:
            reasons.append(
                f"current_plan_assignment_identity_missing:index={index}"
            )
            continue
        resources_by_target[target_id].add(resource_id)
    # A coalition identifier is provenance for single-member assignments too.
    # Atomic commit is required only by multiplicity or current D4 evidence.
    coalition_targets = {
        target_id
        for target_id, members in resources_by_target.items()
        if len(members) > 1
    }

    commits_by_target: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    state_counter: Counter[str] = Counter()
    for index, region in enumerate(regions):
        region_id = _nonempty_text(region.get("region_id")) or f"index-{index}"
        commits = region.get("coalition_commits")
        if not isinstance(commits, list):
            reasons.append(
                f"latest_d4_coalition_commits_missing:region={region_id}"
            )
            continue
        for commit_index, commit in enumerate(commits):
            if not isinstance(commit, Mapping):
                reasons.append(
                    "latest_d4_coalition_commit_invalid:"
                    f"region={region_id}:index={commit_index}"
                )
                continue
            target_id = _nonempty_text(commit.get("global_track_id"))
            if target_id is None:
                reasons.append(
                    "latest_d4_coalition_target_missing:"
                    f"region={region_id}:index={commit_index}"
                )
                continue
            commits_by_target[target_id].append(commit)
            if (
                plan_identity_verified
                and commit.get("commit_required") is True
            ):
                coalition_targets.add(target_id)
                if target_id not in resources_by_target:
                    reasons.append(
                        "current_plan_coalition_target_not_in_latest_d3_assignments:"
                        f"target={target_id}"
                    )

    uncommitted_targets: set[str] = set()
    if not plan_identity_verified:
        reasons.append(
            "current_plan_coalition_state_rejected_due_to_plan_generation_mismatch"
        )
        uncommitted_targets.update(coalition_targets)

    for target_id in sorted(coalition_targets):
        expected_members = resources_by_target.get(target_id, set())
        candidates = commits_by_target.get(target_id, ())
        if len(candidates) != 1:
            reasons.append(
                "current_plan_coalition_commit_count_mismatch:"
                f"target={target_id}:expected=1:actual={len(candidates)}"
            )
            uncommitted_targets.add(target_id)
            continue
        commit = candidates[0]
        state = _nonempty_text(commit.get("state")) or "unavailable"
        state_counter[state] += 1
        if state == "collecting_acks":
            reasons.append(
                f"current_plan_coalition_collecting_acks:target={target_id}"
            )
        elif state == "proposed":
            reasons.append(
                f"current_plan_coalition_proposed:target={target_id}"
            )
        elif state not in _COMMITTED_STATES:
            reasons.append(
                "current_plan_coalition_not_committed:"
                f"target={target_id}:state={state}"
            )

        required = _string_set(commit.get("required_member_ids"))
        acked = _string_set(commit.get("acked_member_ids"))
        missing = _string_set(commit.get("missing_member_ids"))
        if required is None or acked is None or missing is None:
            reasons.append(
                f"current_plan_coalition_ack_sets_invalid:target={target_id}"
            )
        else:
            if expected_members and required != expected_members:
                reasons.append(
                    "current_plan_coalition_required_members_mismatch:"
                    f"target={target_id}:d3={sorted(expected_members)}:"
                    f"d4={sorted(required)}"
                )
            if acked != required:
                reasons.append(
                    "current_plan_coalition_acked_members_incomplete:"
                    f"target={target_id}:required={sorted(required)}:"
                    f"acked={sorted(acked)}"
                )
            if missing:
                reasons.append(
                    "current_plan_coalition_missing_required_acks:"
                    f"target={target_id}:missing={sorted(missing)}"
                )
        if commit.get("commit_required") is not True:
            reasons.append(
                f"current_plan_coalition_commit_required_false:target={target_id}"
            )
        if commit.get("atomic_committed") is not True:
            reasons.append(
                f"current_plan_coalition_atomic_commit_false:target={target_id}"
            )
        if commit.get("execution_authorized") is not True:
            reasons.append(
                f"current_plan_coalition_execution_not_authorized:target={target_id}"
            )
        lease = _finite_float(commit.get("lease_expires_at_s"))
        if lease is None:
            reasons.append(
                f"current_plan_coalition_lease_missing:target={target_id}"
            )
        elif d4_timestamp is None or d4_timestamp >= lease:
            reasons.append(
                f"current_plan_coalition_lease_expired:target={target_id}"
            )

        target_prefix = (
            f"target={target_id}"
        )
        if any(target_prefix in reason for reason in reasons):
            uncommitted_targets.add(target_id)

    if reasons and not coalition_targets:
        # Malformed D3/D4 coalition evidence remains a failure even when no
        # valid target identifier could be recovered.
        verified = False
    else:
        verified = plan_identity_verified and not uncommitted_targets and not reasons
    return {
        "availability": "available",
        "unavailable_reason": None,
        "verified": verified,
        "expected_current_plan_coalition_target_count": len(coalition_targets),
        "audited_current_plan_coalition_target_count": sum(
            len(commits_by_target.get(target_id, ())) == 1
            for target_id in coalition_targets
        ),
        "state_distribution": dict(sorted(state_counter.items())),
        "uncommitted_target_ids": sorted(uncommitted_targets),
        "failure_reasons": _dedupe(reasons),
    }


def _audit_communication_dispositions(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    unavailable_reason: str | None,
) -> dict[str, Any]:
    if records is None:
        missing = (
            unavailable_reason is None
            or str(unavailable_reason).startswith("artifact_missing:")
        )
        return {
            "availability": "unavailable",
            "unavailable_reason": (
                unavailable_reason
                or f"artifact_missing:{COMMUNICATION_DISPOSITION_ARTIFACT_NAME}"
            ),
            "verified": None,
            "record_count": None,
            "disposition_distribution": None,
            "d4_topic_disposition_distribution": None,
            "retry_record_count": None,
            "failure_reasons": (
                []
                if missing
                else [
                    "communication_disposition_artifact_invalid:"
                    f"{unavailable_reason}"
                ]
            ),
        }

    reasons: list[str] = []
    transport_ids: set[int] = set()
    disposition_counter: Counter[str] = Counter()
    d4_counter: Counter[str] = Counter()
    retry_count = 0
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            reasons.append(
                f"communication_disposition_record_invalid:index={index}"
            )
            continue
        if record.get("schema_version") != (
            COMMUNICATION_DISPOSITION_SCHEMA_VERSION
        ):
            reasons.append(
                f"communication_disposition_schema_mismatch:index={index}"
            )
        transport_id = _nonnegative_int(record.get("transport_id"))
        if transport_id is None:
            reasons.append(
                f"communication_disposition_transport_id_invalid:index={index}"
            )
        elif transport_id in transport_ids:
            reasons.append(
                "communication_disposition_transport_id_duplicate:"
                f"transport_id={transport_id}"
            )
        else:
            transport_ids.add(transport_id)
        topic = _nonempty_text(record.get("topic"))
        source = _nonempty_text(record.get("source"))
        destination = _nonempty_text(record.get("destination"))
        disposition = _nonempty_text(record.get("disposition"))
        send_timestamp = _finite_float(record.get("send_timestamp"))
        arrival_timestamp = _finite_float(record.get("arrival_timestamp"))
        retry_generation = _nonnegative_int(record.get("retry_generation"))
        if topic is None or source is None or destination is None:
            reasons.append(
                f"communication_disposition_route_invalid:index={index}"
            )
        if disposition not in _FINAL_DISPOSITIONS:
            reasons.append(
                "communication_disposition_state_invalid:"
                f"index={index}:state={disposition}"
            )
        else:
            disposition_counter[disposition] += 1
            if topic is not None and topic.startswith("d4."):
                d4_counter[f"{topic}:{disposition}"] += 1
        if send_timestamp is None or send_timestamp < 0.0:
            reasons.append(
                f"communication_disposition_send_timestamp_invalid:index={index}"
            )
        if disposition in {"delivered", "pending"} and (
            arrival_timestamp is None or arrival_timestamp < 0.0
        ):
            reasons.append(
                f"communication_disposition_arrival_timestamp_invalid:index={index}"
            )
        if disposition == "dropped" and record.get("arrival_timestamp") is not None:
            reasons.append(
                f"communication_disposition_dropped_arrival_present:index={index}"
            )
        if retry_generation is None:
            reasons.append(
                f"communication_disposition_retry_generation_invalid:index={index}"
            )
        elif retry_generation > 0:
            retry_count += 1
    reasons = _dedupe(reasons)
    return {
        "availability": "available",
        "unavailable_reason": None,
        "verified": not reasons,
        "record_count": len(records),
        "disposition_distribution": dict(
            sorted(disposition_counter.items())
        ),
        "d4_topic_disposition_distribution": dict(sorted(d4_counter.items())),
        "retry_record_count": retry_count,
        "failure_reasons": reasons,
    }


def _region_authority_values(
    regions: Sequence[Mapping[str, Any]],
    field: str,
    converter: Any,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {}
    if not regions:
        return None
    for index, region in enumerate(regions):
        region_id = _nonempty_text(region.get("region_id")) or f"index-{index}"
        ownership = region.get("ownership")
        if not isinstance(ownership, Mapping):
            return None
        value = converter(ownership.get(field))
        if value is None:
            return None
        values[region_id] = value
    return values


def _ordered_online_records(
    records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized = [dict(record) for record in records if isinstance(record, Mapping)]
    return sorted(
        normalized,
        key=lambda record: (
            _finite_float(record.get("timestamp"))
            if _finite_float(record.get("timestamp")) is not None
            else math.inf,
            _nonnegative_int(record.get("sequence"))
            if _nonnegative_int(record.get("sequence")) is not None
            else 2**63 - 1,
        ),
    )


def _latest_topic(
    records: Sequence[Mapping[str, Any]],
    topic: str,
) -> Mapping[str, Any] | None:
    for record in reversed(records):
        if record.get("topic") == topic:
            return record
    return None


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _load_jsonl(
    path: Path,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if not path.is_file():
        return None, f"artifact_missing:{path.name}"
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return None, f"artifact_unreadable:{path.name}:{exc}"
    for line_number, text in enumerate(lines, start=1):
        if not text.strip():
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            return (
                None,
                f"artifact_invalid_jsonl:{path.name}:{line_number}:{exc.msg}",
            )
        if not isinstance(value, Mapping):
            return (
                None,
                f"artifact_record_not_object:{path.name}:{line_number}",
            )
        records.append(dict(value))
    return records, None


def _put_metric(
    metrics: dict[str, Any],
    field: str,
    value: Any,
    *,
    available: bool,
    unavailable_reason: Any,
) -> None:
    metrics[field] = value
    metrics[f"{field}_availability"] = (
        "available" if available else "unavailable"
    )
    metrics[f"{field}_unavailable_reason"] = (
        None if available else unavailable_reason
    )


def _unavailable_check(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "unavailable_reason": reason,
        "verified": False,
        "match": None,
        "failure_reasons": [],
    }


def _unavailable_coalition(reason: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "unavailable_reason": reason,
        "verified": False,
        "expected_current_plan_coalition_target_count": None,
        "audited_current_plan_coalition_target_count": None,
        "state_distribution": None,
        "uncommitted_target_ids": None,
        "failure_reasons": [],
    }


def _string_set(value: Any) -> set[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    normalized = [_nonempty_text(item) for item in value]
    if any(item is None for item in normalized):
        return None
    return {str(item) for item in normalized}


def _nonempty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value) if int(value) >= 0 else None


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _float_equal(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1.0e-12, abs_tol=_EPS)


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


__all__ = [
    "COMMUNICATION_DISPOSITION_ARTIFACT_NAME",
    "COMMUNICATION_DISPOSITION_SCHEMA_VERSION",
    "FORMAL_R0_PLAN_BINDING_AUDIT_SCHEMA_VERSION",
    "audit_formal_r0_plan_binding_episode",
    "audit_formal_r0_plan_binding_records",
    "formal_r0_plan_binding_row_metrics",
]
