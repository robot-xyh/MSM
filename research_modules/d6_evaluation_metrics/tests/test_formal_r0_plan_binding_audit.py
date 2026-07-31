from __future__ import annotations

import json
from pathlib import Path

from d6_evaluation_metrics.formal_r0_plan_binding_audit import (
    audit_formal_r0_plan_binding_episode,
    audit_formal_r0_plan_binding_records,
    formal_r0_plan_binding_row_metrics,
)


def _envelope(
    sequence: int,
    topic: str,
    timestamp: float,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": topic,
        "source": "D3" if ".d3." in topic else "D4",
        "timestamp": timestamp,
        "schema_version": "fixture-v1",
        "payload": payload,
    }


def _d3_payload(
    *,
    plan_version: int = 2,
    epoch: int = 4,
    lease: float = 8.0,
) -> dict[str, object]:
    return {
        "timestamp": 1.0,
        "plan_id": "PLAN-CURRENT",
        "plan_version": plan_version,
        "created_at": 1.0,
        "assignment_count": 3,
        "target_count": 1,
        "resource_count": 3,
        "assignments": [
            {
                "resource_id": resource_id,
                "global_track_id": "GT-HIGH",
                "coalition_id": "COALITION-GT-HIGH",
                "coalition_version": 2,
                "member_role": role,
                "regional_region_id": "region-000",
                "regional_epoch": epoch,
                "regional_lease_expires_at_s": lease,
            }
            for resource_id, role in (
                ("INT-0001", "primary"),
                ("INT-0002", "primary"),
                ("INT-0003", "reserve"),
            )
        ],
        "unassigned_global_track_ids": [],
        "metadata": {
            "regional_max_epoch": epoch,
            "regional_min_lease_expires_at_s": lease,
        },
    }


def _d4_payload(
    *,
    plan_version: int = 2,
    epoch: int = 4,
    lease: float = 8.0,
    state: str = "committed",
) -> dict[str, object]:
    required = ["INT-0001", "INT-0002", "INT-0003"]
    committed = state in {"committed", "executing"}
    acked = required if committed else required[:2]
    missing = [] if committed else ["INT-0003"]
    return {
        "schema": "d4-regional-failover-v1",
        "timestamp_s": 1.1,
        "regions": [
            {
                "region_id": "region-000",
                "selected_layer": "center",
                "ownership": {
                    "owner_id": "C2-CENTER",
                    "owner_layer": "center",
                    "plan_id": "PLAN-CURRENT",
                    "plan_version": plan_version,
                    "epoch": epoch,
                    "lease_expires_at_s": lease,
                    "active": committed,
                },
                "execution_allowed": committed,
                "fail_closed": not committed,
                "coalition_commits": [
                    {
                        "task_id": "task:GT-HIGH",
                        "global_track_id": "GT-HIGH",
                        "commit_required": True,
                        "state": state,
                        "coordinator_id": "C2-CENTER",
                        "required_member_ids": required,
                        "acked_member_ids": acked,
                        "missing_member_ids": missing,
                        "lease_expires_at_s": lease,
                        "atomic_committed": committed,
                        "execution_authorized": committed,
                        "reason": (
                            "all_required_acks_received"
                            if committed
                            else "collecting_member_acks"
                        ),
                    }
                ],
            }
        ],
    }


def _communication_records() -> list[dict[str, object]]:
    return [
        {
            "schema_version": "scalable3d-communication-disposition-v1",
            "transport_id": 1,
            "message_id": "d4:plan:PLAN-CURRENT:v2:r0",
            "envelope_sequence": 10,
            "topic": "d4.regional_plan_broadcast.v1",
            "source": "D4-AUTHORITY-GATE",
            "destination": "INT-0001",
            "send_timestamp": 1.0,
            "arrival_timestamp": 1.04,
            "disposition": "delivered",
            "payload_size_bytes": 512,
            "random_stream": "d4_strict_evidence_v1",
            "retry_generation": 0,
        },
        {
            "schema_version": "scalable3d-communication-disposition-v1",
            "transport_id": 2,
            "message_id": "d4:ack:PLAN-CURRENT:v2:INT-0001",
            "envelope_sequence": 11,
            "topic": "d4.coalition_member_ack.v1",
            "source": "INT-0001",
            "destination": "D4-AUTHORITY-GATE",
            "send_timestamp": 1.04,
            "arrival_timestamp": 1.08,
            "disposition": "delivered",
            "payload_size_bytes": 384,
            "random_stream": "d4_strict_evidence_v1",
            "retry_generation": 0,
        },
    ]


def _records(
    *,
    d3_version: int = 2,
    d4_version: int = 2,
    d3_epoch: int = 4,
    d4_epoch: int = 4,
    d3_lease: float = 8.0,
    d4_lease: float = 8.0,
    state: str = "committed",
) -> list[dict[str, object]]:
    return [
        _envelope(1, "modules.d3.assignment_plan", 1.0, _d3_payload(
            plan_version=d3_version,
            epoch=d3_epoch,
            lease=d3_lease,
        )),
        _envelope(2, "modules.d4.regional_failover", 1.1, _d4_payload(
            plan_version=d4_version,
            epoch=d4_epoch,
            lease=d4_lease,
            state=state,
        )),
    ]


def _mixed_single_and_multi_assignment_records() -> list[dict[str, object]]:
    d3 = _d3_payload()
    d3["assignment_count"] = 5
    d3["target_count"] = 4
    d3["resource_count"] = 5
    d3["assignments"] = [
        {
            "resource_id": resource_id,
            "global_track_id": target_id,
            "coalition_id": coalition_id,
            "coalition_version": 2,
            "member_role": role,
            "regional_region_id": "region-000",
            "regional_epoch": 4,
            "regional_lease_expires_at_s": 8.0,
        }
        for resource_id, target_id, coalition_id, role in (
            ("INT-0001", "GT-SOLO-1", "COALITION-GT-SOLO-1", "primary"),
            ("INT-0002", "GT-SOLO-2", "COALITION-GT-SOLO-2", "primary"),
            ("INT-0003", "GT-MULTI", "COALITION-GT-MULTI", "primary"),
            ("INT-0004", "GT-MULTI", "COALITION-GT-MULTI", "reserve"),
            ("INT-0005", "GT-SOLO-3", "COALITION-GT-SOLO-3", "primary"),
        )
    ]

    d4 = _d4_payload()
    d4["regions"][0]["coalition_commits"] = [
        {
            "task_id": "task:GT-MULTI",
            "global_track_id": "GT-MULTI",
            "commit_required": True,
            "state": "committed",
            "coordinator_id": "C2-CENTER",
            "required_member_ids": ["INT-0003", "INT-0004"],
            "acked_member_ids": ["INT-0003", "INT-0004"],
            "missing_member_ids": [],
            "lease_expires_at_s": 8.0,
            "atomic_committed": True,
            "execution_authorized": True,
            "reason": "all_required_acks_received",
        },
        {
            "task_id": "task:GT-SOLO-1",
            "global_track_id": "GT-SOLO-1",
            "commit_required": False,
            "state": "not_required",
        },
    ]
    return [
        _envelope(1, "modules.d3.assignment_plan", 1.0, d3),
        _envelope(2, "modules.d4.regional_failover", 1.1, d4),
    ]


def test_same_generation_current_plan_and_closed_acks_pass() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _records(),
        communication_dispositions=_communication_records(),
    )
    metrics = formal_r0_plan_binding_row_metrics(audit)

    assert audit["status"] == "pass"
    assert audit["verified"] is True
    assert audit["plan_identity"]["plan_id_match"] is True
    assert audit["plan_identity"]["plan_version_match"] is True
    assert audit["authority_epoch"]["match"] is True
    assert audit["authority_lease"]["match"] is True
    assert audit["coalition_commit"]["verified"] is True
    assert audit["communication_dispositions"]["verified"] is True
    assert metrics["d4_current_d3_plan_binding_verified"] is True
    assert (
        metrics["d4_current_plan_coalition_commit_verified"] is True
    )


def test_committed_d4_v1_is_rejected_for_latest_d3_v2() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _records(d3_version=2, d4_version=1),
        communication_dispositions=None,
        communication_unavailable_reason=(
            "artifact_missing:communication_dispositions.jsonl"
        ),
    )

    assert audit["status"] == "fail_closed"
    assert audit["verified"] is False
    assert audit["plan_identity"]["plan_version_match"] is False
    assert audit["coalition_commit"]["verified"] is False
    assert "GT-HIGH" in audit["coalition_commit"]["uncommitted_target_ids"]
    assert any(
        reason.startswith("latest_d4_plan_version_mismatch")
        for reason in audit["failure_reasons"]
    )
    assert (
        "current_plan_coalition_state_rejected_due_to_plan_generation_mismatch"
        in audit["failure_reasons"]
    )
    assert (
        audit["communication_dispositions"]["availability"]
        == "unavailable"
    )


def test_current_plan_collecting_acks_fails_closed_with_explicit_reason() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _records(state="collecting_acks"),
        communication_dispositions=_communication_records(),
    )

    assert audit["status"] == "fail_closed"
    assert audit["plan_identity"]["verified"] is True
    assert audit["coalition_commit"]["verified"] is False
    assert audit["coalition_commit"]["uncommitted_target_ids"] == [
        "GT-HIGH"
    ]
    assert (
        "current_plan_coalition_collecting_acks:target=GT-HIGH"
        in audit["failure_reasons"]
    )
    assert any(
        reason.startswith(
            "current_plan_coalition_missing_required_acks:target=GT-HIGH"
        )
        for reason in audit["failure_reasons"]
    )


def test_current_plan_proposed_fails_closed() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _records(state="proposed"),
        communication_dispositions=_communication_records(),
    )

    assert audit["verified"] is False
    assert (
        "current_plan_coalition_proposed:target=GT-HIGH"
        in audit["failure_reasons"]
    )


def test_current_plan_authority_epoch_mismatch_fails_closed() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _records(d3_epoch=5, d4_epoch=4),
        communication_dispositions=_communication_records(),
    )

    assert audit["verified"] is False
    assert audit["authority_epoch"]["availability"] == "available"
    assert audit["authority_epoch"]["match"] is False
    assert any(
        reason.startswith("latest_d4_authority_epoch_mismatch")
        for reason in audit["failure_reasons"]
    )


def test_current_plan_authority_lease_mismatch_fails_closed() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _records(d3_lease=9.0, d4_lease=8.0),
        communication_dispositions=_communication_records(),
    )

    assert audit["verified"] is False
    assert audit["authority_lease"]["availability"] == "available"
    assert audit["authority_lease"]["match"] is False
    assert any(
        reason.startswith("latest_d4_authority_lease_mismatch")
        for reason in audit["failure_reasons"]
    )


def test_missing_communication_artifact_is_reported_as_unavailable(
    tmp_path: Path,
) -> None:
    records = _records()
    (tmp_path / "online_observations.jsonl").write_text(
        "".join(
            f"{json.dumps(record, sort_keys=True)}\n"
            for record in records
        ),
        encoding="utf-8",
    )

    audit = audit_formal_r0_plan_binding_episode(tmp_path)
    metrics = formal_r0_plan_binding_row_metrics(audit)

    assert audit["verified"] is True
    assert (
        audit["communication_dispositions"]["availability"]
        == "unavailable"
    )
    assert audit["communication_dispositions"]["verified"] is None
    assert (
        metrics[
            "d4_communication_disposition_validation_verified_availability"
        ]
        == "unavailable"
    )
    assert (
        metrics["d4_communication_disposition_validation_verified"] is None
    )


def test_single_member_coalition_ids_do_not_require_atomic_commits() -> None:
    audit = audit_formal_r0_plan_binding_records(
        _mixed_single_and_multi_assignment_records(),
        communication_dispositions=_communication_records(),
    )

    assert audit["status"] == "pass"
    assert audit["coalition_commit"]["verified"] is True
    assert (
        audit["coalition_commit"][
            "expected_current_plan_coalition_target_count"
        ]
        == 1
    )
    assert (
        audit["coalition_commit"][
            "audited_current_plan_coalition_target_count"
        ]
        == 1
    )
    assert audit["coalition_commit"]["uncommitted_target_ids"] == []
    assert audit["coalition_commit"]["state_distribution"] == {
        "committed": 1
    }


def test_commit_for_target_absent_from_latest_d3_plan_fails_closed() -> None:
    records = _records()
    stale_commit = dict(
        records[-1]["payload"]["regions"][0]["coalition_commits"][0]
    )
    stale_commit["task_id"] = "task:GT-OLD"
    stale_commit["global_track_id"] = "GT-OLD"
    records[-1]["payload"]["regions"][0]["coalition_commits"].append(
        stale_commit
    )

    audit = audit_formal_r0_plan_binding_records(
        records,
        communication_dispositions=_communication_records(),
    )

    assert audit["verified"] is False
    assert audit["coalition_commit"]["verified"] is False
    assert "GT-OLD" in audit["coalition_commit"]["uncommitted_target_ids"]
    assert (
        "current_plan_coalition_target_not_in_latest_d3_assignments:"
        "target=GT-OLD"
        in audit["failure_reasons"]
    )


def test_duplicate_current_plan_commit_authorization_fails_closed() -> None:
    records = _records()
    duplicate = dict(
        records[-1]["payload"]["regions"][0]["coalition_commits"][0]
    )
    records[-1]["payload"]["regions"][0]["coalition_commits"].append(
        duplicate
    )

    audit = audit_formal_r0_plan_binding_records(
        records,
        communication_dispositions=_communication_records(),
    )

    assert audit["verified"] is False
    assert audit["coalition_commit"]["verified"] is False
    assert "GT-HIGH" in audit["coalition_commit"]["uncommitted_target_ids"]
    assert (
        "current_plan_coalition_commit_count_mismatch:"
        "target=GT-HIGH:expected=1:actual=2"
        in audit["failure_reasons"]
    )
