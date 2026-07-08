from __future__ import annotations

from d4_distributed_fallback.cbba import CBBANegotiator, build_cbba_cost_gap_benchmark
from d4_distributed_fallback.models import (
    Assignment,
    AvailabilityBand,
    CBBAResult,
    CommBand,
    ConfidenceBand,
    CBBACostGapBenchmark,
    DistributedVisualEvidenceSummary,
    ResourceSummary,
    TrackSummary,
)
from d4_distributed_fallback.network import SimulatedNetwork


def _resources(node_ids: list[str]) -> list[ResourceSummary]:
    return [
        ResourceSummary(
            node_id=node_id,
            capability_class="observe",
            availability_band=AvailabilityBand.HIGH,
            comm_band=CommBand.GOOD,
            epoch=1,
        )
        for node_id in node_ids
    ]


def _tasks(count: int) -> list[TrackSummary]:
    return [
        TrackSummary(
            track_id=f"task-{idx + 1}",
            coarse_cell=f"cell-{idx + 1}",
            age_s=1.0,
            confidence_band=ConfidenceBand.HIGH,
            source_count=2,
            epoch=1,
        )
        for idx in range(count)
    ]


def _visual_task(
    task_id: str,
    *,
    support: tuple[str, ...] = (),
    hold: tuple[str, ...] = (),
    ambiguous: tuple[str, ...] = (),
    duplicate: tuple[str, ...] = (),
    confidence: float = 0.8,
    ambiguity: float = 0.1,
    hypothesis_only: bool = False,
    missing_global_id: bool = False,
    stale_global_id: bool = False,
    friend_conflict: bool = False,
    local_id_conflict: bool = False,
) -> TrackSummary:
    return TrackSummary(
        track_id=task_id,
        coarse_cell=f"cell-{task_id}",
        age_s=1.0,
        confidence_band=ConfidenceBand.HIGH,
        source_count=2,
        epoch=1,
        visual_evidence=DistributedVisualEvidenceSummary(
            visual_support_resource_ids=support,
            hold_resource_ids=hold,
            ambiguous_resource_ids=ambiguous,
            duplicate_lock_resource_ids=duplicate,
            assigned_global_track_id=None if missing_global_id else task_id,
            terminal_confidence=confidence,
            terminal_ambiguity=ambiguity,
            hypothesis_count=1,
            support_count=len(support),
            hypothesis_only=hypothesis_only,
            stale_global_track_id=stale_global_id,
            missing_global_track_id=missing_global_id,
            duplicate_terminal_lock_risk=bool(duplicate),
            friend_conflict=friend_conflict,
            local_id_conflict=local_id_conflict,
        ),
    )


def test_cbba_converges_without_duplicate_task_owners() -> None:
    node_ids = ["node-1", "node-2", "node-3", "node-4"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=10).run(
        tasks=_tasks(3),
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.completion_rate == 1.0
    assert len(result.assignments) == 3
    assert len(set(result.assignments)) == 3
    assert result.messages_sent > 0


def test_cbba_tie_break_prefers_lower_node_id() -> None:
    node_ids = ["node-2", "node-1"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=10).run(
        tasks=_tasks(1),
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.assignments["task-1"].owner == "node-1"


def test_cbba_prefers_d5_distributed_visual_support() -> None:
    node_ids = ["node-1", "node-2"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=10).run(
        tasks=[_visual_task("task-1", support=("node-2",), confidence=0.95)],
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.assignments["task-1"].owner == "node-2"
    assert result.assignment_audit["task-1"]["visual_support_resource_ids"] == ("node-2",)


def test_no_center_cbba_uses_d5_visual_evidence_as_risk_weighting() -> None:
    node_ids = ["node-1", "node-2", "node-3"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=12).run(
        tasks=[_visual_task("task-1", support=("node-3",), confidence=0.96)],
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.assignments["task-1"].owner == "node-3"
    assert result.assignment_audit["task-1"]["owner"] == "node-3"
    assert result.final_views


def test_cbba_records_duplicate_terminal_lock_without_multiple_owners() -> None:
    node_ids = ["node-1", "node-2", "node-3"]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=12).run(
        tasks=[
            _visual_task(
                "task-1",
                support=("node-1", "node-2"),
                duplicate=("node-1", "node-2"),
                confidence=0.9,
            )
        ],
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert len(result.assignments) == 1
    assert len({assignment.owner for assignment in result.assignments.values()}) == 1
    assert result.assignment_audit["task-1"]["duplicate_terminal_lock_risk"] is True


def test_cbba_blocks_stale_missing_or_friend_conflicted_visual_evidence() -> None:
    node_ids = ["node-1", "node-2"]
    risky_tasks = [
        _visual_task("missing", support=("node-1",), missing_global_id=True),
        _visual_task("stale", support=("node-1",), stale_global_id=True),
        _visual_task("friend", support=("node-1",), friend_conflict=True),
    ]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=10).run(
        tasks=risky_tasks,
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.assignments == {}
    assert result.completion_rate == 0.0
    assert result.assignment_audit["missing"]["missing_global_track_id"] is True
    assert result.assignment_audit["stale"]["stale_global_track_id"] is True
    assert result.assignment_audit["friend"]["friend_conflict"] is True


def test_cbba_scales_n_peer_n_target_with_visual_support() -> None:
    count = 7
    node_ids = [f"node-{idx + 1}" for idx in range(count)]
    tasks = [
        _visual_task(f"task-{idx + 1}", support=(f"node-{idx + 1}",), confidence=0.9)
        for idx in range(count)
    ]
    network = SimulatedNetwork(node_ids=node_ids, packet_loss=0.0, min_delay_s=0.1, max_delay_s=0.1)
    result = CBBANegotiator(node_ids=node_ids, max_rounds=30).run(
        tasks=tasks,
        resources=_resources(node_ids),
        network=network,
    )

    assert result.converged
    assert result.completion_rate == 1.0
    for idx in range(count):
        assert result.assignments[f"task-{idx + 1}"].owner == f"node-{idx + 1}"


def test_cbba_cost_gap_benchmark_compares_against_d3_center_plan_without_hungarian() -> None:
    result = CBBAResult(
        assignments={
            "task-1": Assignment("task-1", "node-2", 8.0, epoch=1),
            "task-2": Assignment("task-2", "node-1", 7.0, epoch=1),
        },
        consensus_rounds=4,
        converged=True,
        conflict_count=1,
        completion_rate=1.0,
        messages_sent=12,
        messages_delivered=12,
        messages_dropped=0,
        estimated_bytes=1200,
        duration_s=2.0,
    )

    benchmark = build_cbba_cost_gap_benchmark(
        result,
        center_assignments={"task-1": "node-1", "task-2": "node-2"},
        cost_by_task_resource={
            "task-1": {"node-1": 1.0, "node-2": 3.0},
            "task-2": {"node-1": 4.0, "node-2": 2.0},
        },
        attach_to_result=True,
    )

    assert isinstance(benchmark, CBBACostGapBenchmark)
    assert result.cost_gap_benchmark is benchmark
    assert benchmark.benchmark_source == "d3_hungarian_cost_matrix"
    assert benchmark.cbba_total_cost == 7.0
    assert benchmark.center_total_cost == 3.0
    assert benchmark.absolute_cost_gap == 4.0
    assert benchmark.relative_cost_gap == 4.0 / 3.0
    assert benchmark.completion_rate_gap == 0.0
    assert benchmark.cbba_conflict_count == 1
    assert benchmark.per_task_cost_gap == {"task-1": 2.0, "task-2": 2.0}
