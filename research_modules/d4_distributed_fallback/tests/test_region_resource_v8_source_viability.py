from __future__ import annotations

import json
from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource_v8_development_contract import (
    V8RequestScheduleEntry,
    load_v8_frozen_request,
)
from d4_distributed_fallback.region_resource_v8_source_viability import (
    RegionResourceV8SourceViabilityError,
    audit_v8_frozen_source_viability,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_REQUEST_ROOT = (
    _REPOSITORY_ROOT
    / "research_modules"
    / "d4_distributed_fallback"
    / "reports"
    / "D4_V7_FAILURE_ATTRIBUTION_V8_DATA_REQUEST_20260801"
)
_REQUEST_PATH = _REQUEST_ROOT / "v8_development_data_request.json"
_REGISTRY_PATH = _REQUEST_ROOT / "v8_development_seed_registry.json"


def test_all_324_frozen_cells_pass_in_memory_viability_audit() -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)

    report = audit_v8_frozen_source_viability(frozen.schedule)

    assert report.all_cells_viable is True
    assert report.schedule_episode_count == 324
    assert report.audited_frame_count == 972
    assert report.full_cell_combination_count == 324
    assert report.reduced_combination_count == 108
    assert report.online_truth_use_count == 0
    assert report.failure_count == 0
    assert dict(report.edge_count_by_topology) == {
        "directed_ring_8": 16,
        "directed_grid_3x3": 24,
        "directed_ring_12": 24,
        "directed_mesh_16": 240,
    }
    assert report.cell_evidence_sha256 == (
        "1cdb83e6ee4dd9a1f85ef166fc907446cd384218b8dfa563d7f0983e98471dc2"
    )
    assert not any(
        value
        for key, value in report.permissions.to_dict().items()
        if key != "schema"
    )


def test_viability_audit_fails_closed_on_schedule_order_drift() -> None:
    frozen = load_v8_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)
    schedule = list(frozen.schedule)
    first = schedule[0]
    second = schedule[1]
    schedule[0] = V8RequestScheduleEntry(
        seed=second.seed,
        split=first.split,
        topology_id=first.topology_id,
        region_count=first.region_count,
        supply_demand_condition=first.supply_demand_condition,
        communication_condition=first.communication_condition,
        requested_target_class=first.requested_target_class,
        requested_transfer_resource_count=first.requested_transfer_resource_count,
        hard_negative_candidate_resource_count=(
            first.hard_negative_candidate_resource_count
        ),
        replicate=first.replicate,
    )

    with pytest.raises(
        RegionResourceV8SourceViabilityError,
        match="seed_order_mismatch",
    ):
        audit_v8_frozen_source_viability(schedule)


def test_real_scalable_runtime_prefix_sequences_zero_and_one_are_buildable() -> None:
    from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource import (
        RuleRegionResourcePolicy,
    )
    from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_development_contract import (
        load_v8_frozen_request as load_runtime_frozen_request,
    )
    from research_modules.d4_distributed_fallback.d4_distributed_fallback.region_resource_v8_runtime_evidence import (
        V8RuntimeEpisodeEvidenceBuilder,
    )
    from research_modules.scalable_3d_simulation.learning_source_adapters import (
        _d4_runtime_frame_evidence,
        build_d4_v8_runtime_episode,
    )
    from research_modules.scalable_3d_simulation.learning_source_recipes import (
        load_d4_a2_v8_episode_recipes,
    )
    from research_modules.scalable_3d_simulation.models import ScenarioConfig
    from research_modules.scalable_3d_simulation.module_stack import (
        IntegratedScalableModuleStack,
        IntegratedStackConfig,
    )
    from research_modules.scalable_3d_simulation.orchestrator import run_episode

    base_config = ScenarioConfig.from_dict(
        json.loads(
            (
                _REPOSITORY_ROOT
                / "research_modules"
                / "scalable_3d_simulation"
                / "configs"
                / "nominal_200v200.json"
            ).read_text(encoding="utf-8")
        )
    )
    recipes = load_d4_a2_v8_episode_recipes(_REGISTRY_PATH)
    frozen = load_runtime_frozen_request(_REQUEST_PATH, _REGISTRY_PATH)

    for sequence in (0, 1):
        recipe = frozen.schedule[sequence]
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(recipes[sequence].build_config(base_config), module_stack=stack)
        region_frames = stack.learning_artifacts().d4_region_frames
        assert result.summary["online_truth_use_count"] == 0
        assert len(region_frames) == 3

        policy = RuleRegionResourcePolicy()
        builder = V8RuntimeEpisodeEvidenceBuilder(
            episode_id=recipes[sequence].episode_id,
            recipe=recipe,
            rule_policy=policy,
        )
        rejection_reasons: list[str] = []
        for frame_index, runtime_frame in enumerate(region_frames):
            try:
                evidence = _d4_runtime_frame_evidence(
                    runtime_frame.snapshot,
                    recipe=recipe,
                    policy=policy,
                )
                builder.stage_frame(frame_index=frame_index, evidence=evidence)
            except ValueError as exc:  # pragma: no cover - regression diagnostic
                rejection_reasons.append(str(exc))
        assert rejection_reasons == []
        direct = builder.finalize()
        adapted = build_d4_v8_runtime_episode(
            recipe=recipe,
            episode_id=recipes[sequence].episode_id,
            region_frames=region_frames,
        )
        assert len(direct.frames) == len(adapted.frames) == 3

    sequence_one = frozen.schedule[1]
    assert sequence_one.seed == 28101
    assert sequence_one.topology_id == "directed_ring_8"
    assert sequence_one.supply_demand_condition == (
        "source_surplus_target_deficit"
    )
    assert sequence_one.communication_condition == "nominal"
    assert sequence_one.requested_target_class.value == "safe_forward_transfer"
    assert sequence_one.requested_transfer_resource_count == 2
