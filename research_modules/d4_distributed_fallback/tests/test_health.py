from __future__ import annotations

from d4_distributed_fallback.coordinator import FailoverCoordinator
from d4_distributed_fallback.models import C2Health


def test_health_state_moves_from_normal_to_failed_on_stale_heartbeat() -> None:
    coordinator = FailoverCoordinator(
        node_id="node-1",
        peer_ids=["node-2", "node-3"],
        heartbeat_warning_s=1.0,
        heartbeat_stale_s=2.0,
        heartbeat_failure_s=4.0,
    )

    coordinator.observe_center(0.0, heartbeat_ok=True)

    assert coordinator.update_health(0.5) == C2Health.NORMAL
    assert coordinator.update_health(1.5) == C2Health.DEGRADED
    assert coordinator.update_health(2.5) == C2Health.SUSPECT
    assert coordinator.update_health(4.5) == C2Health.FAILED
    assert [item.to_state for item in coordinator.transition_log] == [
        C2Health.DEGRADED,
        C2Health.SUSPECT,
        C2Health.FAILED,
    ]


def test_digest_conflict_enters_suspect() -> None:
    coordinator = FailoverCoordinator(node_id="node-1", peer_ids=["node-2", "node-3"])

    state = coordinator.observe_center(0.0, heartbeat_ok=True, digest_ok=False)

    assert state == C2Health.SUSPECT
    assert coordinator.transition_log[-1].reason == "center_digest_conflict"


def test_recovered_heartbeat_requires_merge_before_normal() -> None:
    coordinator = FailoverCoordinator(node_id="node-1", peer_ids=["node-2", "node-3"])
    coordinator.update_health(5.0)

    state = coordinator.observe_center(5.5, heartbeat_ok=True, digest_ok=True)

    assert state == C2Health.SUSPECT
    assert coordinator.transition_log[-1].reason == "center_digest_recovered_pending_merge"
