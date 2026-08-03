from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_dataset_writer import (
    build_a1_v3_online_frame,
    load_a1_v3_writer_contract,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_quota_probe import (
    A1V3QuotaCounts,
    A1V3QuotaProbeError,
    A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT,
    build_a1_v3_quota_probe_report,
    canonical_frame_key,
    missing_a1_v3_quota,
    validate_probe_episode_record,
)
from research_modules.d3_assignment_planner.src.d3_assignment_planner.a1_v3_sidecar_classification import (
    derive_a1_v3_frame_classifications,
)
from research_modules.d3_assignment_planner.simulations import (
    run_a1_v3_cross_seed_quota_probe as quota_probe_runner,
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
EXISTING_PROBE_ROWS_PATH = (
    REPOSITORY_ROOT
    / "research_modules/d3_assignment_planner/results/"
    "a1_v3_cross_seed_quota_probe_20260802/"
    "a1_v3_300_recipe_quota_probe_before_fix.json.episodes.jsonl"
)


def _record(index: int, *, passed: bool) -> dict:
    counts = A1V3QuotaCounts(10, 3 if passed else 1, 7 if passed else 9, 3)
    required = A1V3QuotaCounts(9, 3, 3, 2)
    missing = missing_a1_v3_quota(counts, required)
    return {
        "entry_index": index,
        "episode_id": f"episode-{index}",
        "cell_id": "cell-0",
        "scenario_family": "nominal_balanced",
        "seed": 23000 + index,
        "split": "train",
        "source_only_counterfactual_mode": "coverage_degrading",
        "source_only_contract": dict(A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT),
        "status": "pass" if passed else "quota_failed",
        "required": required.to_dict(),
        "counts": counts.to_dict(),
        "missing": missing.to_dict(),
        "online_truth_use_count": 0,
        "global_track_id_created_count": 0,
        "global_track_id_rewritten_count": 0,
        "finite_state": True,
        "frames": [
            {
                "frame_index": frame_index,
                "frame_key": [23000 + index, f"episode-{index}", frame_index],
                "measurement_timestamp_s": float(frame_index),
                "arrival_timestamp_s": float(frame_index) + 0.01,
                "source_only_counterfactual_mode": "coverage_degrading",
                "post_projection_reference_policy": "exact_safe_reference",
                "action_change_type": "keep_exact_r0",
                "transition_axes": [],
                "candidate_edge_count_before": 2,
                "candidate_edge_count_after": 2,
                "candidate_edge_count_delta": 0,
                "candidate_edge_added_count": 0,
                "candidate_edge_removed_count": 0,
                "teacher_edge_count_delta": 0,
                "coverage_deficit_delta": 0,
                "candidate_differs_from_teacher": True,
                "effective_matches_teacher": True,
                "online_truth_use_count": 0,
                "global_track_id_created_count": 0,
                "global_track_id_rewritten_count": 0,
                "pre_projection_reason_codes": [
                    "candidate_coverage_degradation_generated_v1"
                ],
                "post_projection_reason_codes": [
                    "effective_reference_plan_stability_fallback_v1"
                ],
            }
            for frame_index in range(counts.observable)
        ],
        "probe_error_code": None,
    }


def test_quota_report_is_explicitly_non_formal_and_preserves_deficit() -> None:
    report = build_a1_v3_quota_probe_report(
        (_record(0, passed=True), _record(1, passed=False)),
        schedule_path="schedule.json",
        schedule_sha256="a" * 64,
        base_config_path="base.json",
        base_config_sha256="b" * 64,
        source_git_commit="c" * 40,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_s=1.0,
        expected_episode_count=2,
    )

    assert report["status"] == "exploratory_incomplete_quota_gap"
    assert report["formal_source_generation"] is False
    assert report["dataset_finalized"] is False
    assert report["training_started"] is False
    assert report["failure_count"] == 1
    assert report["failures"][0]["missing"]["positive"] == 2
    assert report["duplicate_frame_count"] == 0
    assert report["readiness_eligible"] is False


def test_frame_key_accepts_json_list_and_python_tuple_but_canonicalizes() -> None:
    assert canonical_frame_key([23000, "episode-0", 2]) == (
        23000,
        "episode-0",
        2,
    )
    assert canonical_frame_key((23000, "episode-0", 2)) == (
        23000,
        "episode-0",
        2,
    )
    with pytest.raises(A1V3QuotaProbeError, match="probe_frame_key_invalid"):
        canonical_frame_key("23000:episode-0:2")


def test_duplicate_frame_count_uses_canonical_list_tuple_identity() -> None:
    first = _record(0, passed=True)
    second = _record(1, passed=True)
    second["frames"][1]["frame_index"] = 0
    second["frames"][1]["frame_key"] = (23001, "episode-1", 0)
    report = build_a1_v3_quota_probe_report(
        (first, second),
        schedule_path="schedule.json",
        schedule_sha256="a" * 64,
        base_config_path="base.json",
        base_config_sha256="b" * 64,
        source_git_commit="c" * 40,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_s=1.0,
        expected_episode_count=2,
    )
    assert report["duplicate_frame_count"] == 1


def test_new_checkpoint_rejects_frame_that_bypasses_source_only_contract() -> None:
    record = _record(0, passed=True)
    record["frames"][0].pop("source_only_counterfactual_mode")
    with pytest.raises(
        A1V3QuotaProbeError,
        match="probe_frame_counterfactual_mode_binding_mismatch",
    ):
        validate_probe_episode_record(record)

    record = _record(0, passed=True)
    record["frames"][0]["post_projection_reference_policy"] = "coverage_floor"
    with pytest.raises(
        A1V3QuotaProbeError,
        match="probe_frame_reference_policy_binding_mismatch",
    ):
        validate_probe_episode_record(record)

    record = _record(0, passed=True)
    record["frames"][0]["online_truth_use_count"] = 1
    with pytest.raises(
        A1V3QuotaProbeError,
        match="probe_frame_online_truth_use_count_nonzero",
    ):
        validate_probe_episode_record(record)


def test_probe_rejects_inconsistent_candidate_feasibility_inventory() -> None:
    record = _record(0, passed=True)
    record["frames"][0]["candidate_edge_count_after"] = 1
    with pytest.raises(
        A1V3QuotaProbeError,
        match="probe_frame_candidate_feasibility_inventory_inconsistent",
    ):
        validate_probe_episode_record(record)


def test_existing_seed_23001_row_preserves_cross_seed_positive_quota_gap() -> None:
    rows = [
        json.loads(line)
        for line in EXISTING_PROBE_ROWS_PATH.read_text(encoding="ascii").splitlines()
    ]
    row = next(item for item in rows if item["seed"] == 23001)
    assert row["counts"] == {
        "observable": 10,
        "positive": 1,
        "negative": 9,
        "hard_negative": 4,
    }
    assert row["missing"]["positive"] == 2
    assert row["online_truth_use_count"] == 0


def test_probe_source_bindings_cover_adapter_and_d3_projection_dependencies() -> None:
    bindings = quota_probe_runner._source_bindings()
    expected = {
        "probe_runner": (
            "research_modules/d3_assignment_planner/simulations/"
            "run_a1_v3_cross_seed_quota_probe.py"
        ),
        "source_only_projection": (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/a1_v3_source_only_projection.py"
        ),
        "assignment_safety_projection": (
            "research_modules/d3_assignment_planner/src/"
            "d3_assignment_planner/a1_assignment_aware_development.py"
        ),
        "learning_source_adapter": (
            "research_modules/scalable_3d_simulation/"
            "learning_source_adapters.py"
        ),
        "sidecar_classification_policy": (
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_sidecar_classification_policy_v1.json"
        ),
        "frozen_request": (
            "research_modules/d3_assignment_planner/configs/"
            "a1_source_independent_v3_development_data_request_v1.json"
        ),
    }

    for name, path in expected.items():
        assert bindings[name]["path"] == path
        assert len(bindings[name]["sha256"]) == 64
    assert bindings["source_only_projection"][
        "selected_counterfactual_mode"
    ] == "coverage_degrading"
    assert bindings["source_only_projection"][
        "selected_post_projection_reference_policy"
    ] == "exact_safe_reference"


def test_checkpoint_v4_binds_exact_source_only_contract() -> None:
    binding = quota_probe_runner._checkpoint_binding(
        schedule_sha256="a" * 64,
        base_config_sha256="b" * 64,
        source_git_commit="c" * 40,
        repository_dirty=True,
        source_bindings={},
    )
    assert binding["schema_version"].endswith("checkpoint-v4")
    assert binding["source_only_contract"] == (
        A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT
    )


def test_probe_enforces_three_three_two_floor_for_every_frozen_recipe() -> None:
    recipes = load_d3_a1_v3_episode_recipes(SCHEDULE_PATH)
    assert len(recipes) == 300
    required = tuple(
        quota_probe_runner._required_probe_quota(item) for item in recipes
    )
    assert min(item.positive for item in required) == 3
    assert min(item.negative for item in required) == 3
    assert min(item.hard_negative for item in required) == 2


@pytest.fixture(scope="module")
def source_only_probe_record() -> dict:
    quota_probe_runner._WORKER_CONTEXT.clear()
    quota_probe_runner._initialize_worker(
        str(REPOSITORY_ROOT),
        str(SCHEDULE_PATH),
        str(BASE_CONFIG_PATH),
    )
    return quota_probe_runner._probe_recipe(0)


@pytest.fixture(scope="module")
def seed_23006_probe_record(source_only_probe_record: dict) -> dict:
    del source_only_probe_record
    return quota_probe_runner._probe_recipe(6)


@pytest.fixture(scope="module")
def seed_23191_probe_record(source_only_probe_record: dict) -> dict:
    del source_only_probe_record
    entry_index = next(
        index
        for index, recipe in enumerate(quota_probe_runner._WORKER_CONTEXT["recipes"])
        if recipe.seed == 23191
    )
    return quota_probe_runner._probe_recipe(entry_index)


@pytest.fixture(scope="module")
def seed_23032_probe_record(source_only_probe_record: dict) -> dict:
    del source_only_probe_record
    entry_index = next(
        index
        for index, recipe in enumerate(quota_probe_runner._WORKER_CONTEXT["recipes"])
        if recipe.seed == 23032
    )
    return quota_probe_runner._probe_recipe(entry_index)


def test_probe_adapts_every_runtime_frame_before_classification(
    source_only_probe_record: dict,
) -> None:
    record = source_only_probe_record
    assert record["status"] != "probe_error"
    assert record["source_only_counterfactual_mode"] == "coverage_degrading"
    assert record["source_only_contract"] == (
        A1_V3_QUOTA_PROBE_SOURCE_ONLY_CONTRACT
    )
    assert len(record["frames"]) == record["counts"]["observable"]
    assert {frame["frame_class"] for frame in record["frames"]} == {
        "positive",
        "negative",
    }
    assert all(
        frame["source_only_counterfactual_mode"] == "coverage_degrading"
        and frame["post_projection_reference_policy"] == "exact_safe_reference"
        and any(
            reason
            in {
                "candidate_coverage_degradation_generated_v1",
                "candidate_coverage_degradation_unavailable_v1",
            }
            for reason in frame["pre_projection_reason_codes"]
        )
        for frame in record["frames"]
    )
    assert any(
        frame["candidate_differs_from_teacher"] for frame in record["frames"]
    )


def test_probe_online_contract_preserves_effective_safety_time_key_and_identity(
    source_only_probe_record: dict,
) -> None:
    record = source_only_probe_record
    assert record["online_truth_use_count"] == 0
    assert record["global_track_id_created_count"] == 0
    assert record["global_track_id_rewritten_count"] == 0
    for frame in record["frames"]:
        assert frame["frame_key"] == (
            record["seed"],
            record["episode_id"],
            frame["frame_index"],
        )
        assert frame["arrival_timestamp_s"] > frame["measurement_timestamp_s"]
        assert frame["effective_matches_teacher"] is True
        assert frame["online_truth_use_count"] == 0
        assert frame["global_track_id_created_count"] == 0
        assert frame["global_track_id_rewritten_count"] == 0
        assert any(
            reason
            in {
                "effective_reference_plan_stability_fallback_v1",
                "effective_reference_plan_stability_match_v1",
            }
            for reason in frame["post_projection_reason_codes"]
        )


def test_seed_23006_same_coverage_rebinding_uses_exact_reference_stability(
    seed_23006_probe_record: dict,
) -> None:
    record = seed_23006_probe_record
    assert record["seed"] == 23006
    assert record["status"] != "probe_error"
    frame = record["frames"][2]
    assert frame["post_projection_reference_policy"] == "exact_safe_reference"
    assert frame["candidate_differs_from_teacher"] is True
    assert frame["effective_matches_teacher"] is True
    assert "effective_reference_plan_stability_fallback_v1" in (
        frame["post_projection_reason_codes"]
    )
    assert record["online_truth_use_count"] == 0
    assert record["global_track_id_created_count"] == 0
    assert record["global_track_id_rewritten_count"] == 0


def test_seed_23191_assignment_coverage_changes_are_anonymously_classified(
    seed_23191_probe_record: dict,
) -> None:
    record = seed_23191_probe_record
    assert record["seed"] == 23191
    assert record["episode_id"] == "a1-v3-cell-02-validation-03"
    assert record["status"] != "probe_error"
    frames = {frame["frame_index"]: frame for frame in record["frames"]}
    actions = {
        frame_index: frame["action_change_type"]
        for frame_index, frame in frames.items()
    }
    assert actions[3] == "assignment_coverage_contraction"
    assert actions[8] == "assignment_coverage_recovery"
    assert (
        frames[3]["candidate_edge_count_before"],
        frames[3]["candidate_edge_count_after"],
        frames[3]["candidate_edge_added_count"],
        frames[3]["candidate_edge_removed_count"],
        frames[3]["teacher_edge_count_delta"],
    ) == (1600, 1521, 174, 253, -2)
    assert (
        frames[8]["candidate_edge_count_before"],
        frames[8]["candidate_edge_count_after"],
        frames[8]["candidate_edge_added_count"],
        frames[8]["candidate_edge_removed_count"],
        frames[8]["teacher_edge_count_delta"],
    ) == (1590, 1600, 72, 62, 1)
    assert "candidate_feasibility" in frames[3]["transition_axes"]
    assert "candidate_feasibility" in frames[8]["transition_axes"]
    assert actions[3] not in {
        "resource_failure_reassignment",
        "resource_recovery_reassignment",
        "multi_target_cycle",
    }
    assert actions[8] not in {
        "resource_failure_reassignment",
        "resource_recovery_reassignment",
        "multi_target_cycle",
    }


def test_seed_23032_candidate_collapse_transfers_one_coverage_slot(
    seed_23032_probe_record: dict,
) -> None:
    record = seed_23032_probe_record
    assert record["entry_index"] == 48
    assert record["seed"] == 23032
    assert record["episode_id"] == "a1-v3-cell-02-train-08"
    assert record["status"] == "pass"
    assert record["missing"] == {
        "observable": 0,
        "positive": 0,
        "negative": 0,
        "hard_negative": 0,
    }
    frame = record["frames"][3]
    assert frame["transition_axes"] == [
        "candidate_feasibility",
        "teacher_edges",
    ]
    assert (
        frame["candidate_edge_count_before"],
        frame["candidate_edge_count_after"],
        frame["candidate_edge_added_count"],
        frame["candidate_edge_removed_count"],
    ) == (1600, 1568, 213, 245)
    assert frame["teacher_edge_count_delta"] == 0
    assert frame["coverage_deficit_delta"] == 0
    assert frame["action_change_type"] == (
        "single_target_rebind_with_resource_release"
    )
    assert record["online_truth_use_count"] == 0
    assert record["global_track_id_created_count"] == 0
    assert record["global_track_id_rewritten_count"] == 0
