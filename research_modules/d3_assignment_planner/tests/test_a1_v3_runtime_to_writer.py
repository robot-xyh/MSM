from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import pytest

from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
    A1V3DatasetWriter,
    build_a1_v3_online_frame,
    load_a1_v3_writer_contract,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_data_contract import (
    A1V3DataContractError,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_sidecar_classification import (
    derive_a1_v3_frame_classifications,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_source_only_projection import (
    A1V3CounterfactualMode,
    A1V3PostProjectionReferencePolicy,
)
from research_modules.scalable_3d_simulation.learning_source_adapters import (
    adapt_d3_a1_runtime_frame,
)
from research_modules.scalable_3d_simulation.learning_source_recipes import (
    load_d3_a1_v3_episode_recipes,
)
from research_modules.scalable_3d_simulation.models import ScenarioConfig
from research_modules.scalable_3d_simulation.module_stack import (
    IntegratedScalableModuleStack,
    IntegratedStackConfig,
)
from research_modules.scalable_3d_simulation.orchestrator import run_episode


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEDULE_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/configs/"
    "a1_source_independent_v3_generation_schedule_v1.json"
)
BASE_CONFIG_PATH = (
    REPOSITORY_ROOT
    / "research_modules/scalable_3d_simulation/configs/nominal_200v200.json"
)
D4_OWNED_CENTER_FAILURE_EPISODE = "a1-v3-cell-07-train-00"
D3_RUNTIME_EPISODE_IDS = tuple(
    f"a1-v3-cell-{cell_index:02d}-train-00"
    for cell_index in range(15)
    if cell_index != 7
)


@pytest.fixture(scope="module")
def frozen_runtime_stage_summaries(tmp_path_factory: pytest.TempPathFactory):
    base = ScenarioConfig.from_dict(
        json.loads(BASE_CONFIG_PATH.read_text(encoding="ascii"))
    )
    recipes = {
        item.episode_id: item
        for item in load_d3_a1_v3_episode_recipes(SCHEDULE_PATH)
        if item.episode_id in D3_RUNTIME_EPISODE_IDS
    }
    contract = load_a1_v3_writer_contract()
    scheduled = {item.episode_id: item for item in contract.schedule.episodes}
    output_root = tmp_path_factory.mktemp("d3-a1-v3-runtime-to-writer")
    summaries = {}

    for episode_id in D3_RUNTIME_EPISODE_IDS:
        stack = IntegratedScalableModuleStack(
            IntegratedStackConfig(capture_learning_artifacts=True)
        )
        result = run_episode(
            recipes[episode_id].build_config(base), module_stack=stack
        )
        adapted = tuple(
            adapt_d3_a1_runtime_frame(
                frame,
                source_only_counterfactual_mode=(
                    A1V3CounterfactualMode.COVERAGE_DEGRADING
                ),
                source_only_reference_policy=(
                    A1V3PostProjectionReferencePolicy.EXACT_SAFE_REFERENCE
                ),
                source_episode_key=(
                    recipes[episode_id].seed,
                    recipes[episode_id].episode_id,
                ),
            )
            for frame in stack.learning_artifacts().d3_a1_source_frames
        )
        online = tuple(
            build_a1_v3_online_frame(scheduled[episode_id], frame)
            for frame in adapted
        )
        classified = derive_a1_v3_frame_classifications(
            scheduled[episode_id],
            online,
            request=contract.request,
            policy=contract.sidecar_classification_policy,
        )
        class_counts = Counter(item.frame_class for item in classified)
        counts = (
            class_counts["positive"],
            class_counts["negative"],
            sum(item.hard_negative for item in classified),
        )
        assert result.summary["online_truth_use_count"] == 0
        assert all(
            frame.to_dict()["online_truth_use_count"] == 0
            and not any(frame.to_dict()["permissions"].values())
            for frame in online
        )
        writer = A1V3DatasetWriter(
            output_root / episode_id,
            dataset_id=f"d3-runtime-regression-{episode_id}",
            contract=contract,
        )
        expected = scheduled[episode_id]
        quota_met = (
            len(classified) >= expected.minimum_observable_frames
            and counts[0] >= expected.minimum_positive_frames
            and counts[1] >= expected.minimum_negative_frames
            and counts[2] >= expected.minimum_hard_negative_frames
        )
        if quota_met:
            summary = writer.stage_episode(scheduled[episode_id], adapted)
            assert counts == (
                summary.positive_frame_count,
                summary.negative_frame_count,
                summary.hard_negative_frame_count,
            )
            stage_status = "staged"
        else:
            with pytest.raises(
                A1V3DataContractError,
                match="writer_episode_minimum_not_met",
            ):
                writer.stage_episode(scheduled[episode_id], adapted)
            stage_status = "quota_failed_closed"
        stage_paths = tuple(
            (output_root / episode_id / ".a1_v3_staging/episodes").glob(
                "*.json"
            )
        )
        assert len(stage_paths) == int(quota_met)
        if stage_paths:
            staged = json.loads(stage_paths[0].read_text(encoding="ascii"))
            assert all(
                frame["online_truth_use_count"] == 0
                and not any(frame["permissions"].values())
                for frame in staged["online_frames"]
            )
        summaries[episode_id] = (len(classified), *counts, stage_status)
    return summaries


@pytest.mark.parametrize("episode_id", D3_RUNTIME_EPISODE_IDS)
def test_current_recipe_obeys_strict_natural_sidecar_quota_gate(
    frozen_runtime_stage_summaries,
    episode_id: str,
) -> None:
    frame_count, positive, negative, hard_negative, stage_status = (
        frozen_runtime_stage_summaries[episode_id]
    )
    assert positive + negative == frame_count
    assert hard_negative <= negative
    if stage_status == "staged":
        assert positive >= 3 and negative >= 3 and hard_negative >= 2
    else:
        assert stage_status == "quota_failed_closed"
        assert positive < 3 or negative < 3 or hard_negative < 2


def test_center_failure_recipe_is_explicitly_owned_by_d4_main() -> None:
    contract = load_a1_v3_writer_contract()
    assert any(
        episode.episode_id == D4_OWNED_CENTER_FAILURE_EPISODE
        and episode.cell_id == "center-failure-20t20r"
        for episode in contract.schedule.episodes
    )
