from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from commitment_test_support import committed_target_track
from d3_assignment_planner import (
    EDGE_FEATURE_NAMES,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    A1ActionMarginCalibrationConfig,
    AssignmentPlanner,
    CostMatrixResult,
    CostWeights,
    PairedInterventionContractError,
    PlannerConfig,
    ResourceState,
    SharedEdgeActorCriticPolicy,
    TargetDemand,
    calibrate_a1_action_margin,
    development_shadow_admission,
    replay_isolated_learning_intervention_frame,
    save_model_bundle,
)


class _FixedMToNCostModel:
    weights = CostWeights()

    def build_matrix(
        self,
        tracks,
        resources,
        timestamp,
        *,
        preserved_candidate_edges=None,
    ) -> CostMatrixResult:
        del timestamp, preserved_candidate_edges
        matrix = np.asarray(
            (
                (0.1, 0.2, 0.4),
                (0.4, 0.3, 0.1),
            ),
            dtype=float,
        )
        return CostMatrixResult(
            matrix=matrix,
            breakdowns=tuple(
                tuple(
                    {
                        "rule_total": float(matrix[row, column]),
                        "total": float(matrix[row, column]),
                    }
                    for column in range(matrix.shape[1])
                )
                for row in range(matrix.shape[0])
            ),
            target_ids=tuple(item.track_id for item in tracks),
            resource_ids=tuple(item.resource_id for item in resources),
            unassigned_costs=np.asarray((10.0, 10.0), dtype=float),
            target_threat_scores=(0.9, 0.5),
            reject_reasons=((None, None, None), (None, None, None)),
            candidate_mask=np.ones((2, 3), dtype=bool),
        )


class _NoFeasibleMToNCostModel(_FixedMToNCostModel):
    def build_matrix(self, *args, **kwargs) -> CostMatrixResult:
        result = super().build_matrix(*args, **kwargs)
        shape = np.asarray(result.matrix).shape
        return replace(
            result,
            reject_reasons=tuple(
                tuple("hard_safety_rejected" for _ in range(shape[1]))
                for _ in range(shape[0])
            ),
            candidate_mask=np.zeros(shape, dtype=bool),
        )


def _digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def _rule_frame(*, cost_model=None):
    tracks = (
        committed_target_track(
            "global-track-a",
            0.9,
            0.1,
            0.0,
            demand=TargetDemand(
                required_resource_count=2,
                primary_resource_count=2,
            ),
        ),
        committed_target_track("global-track-b", 0.5, 0.1, 0.0),
    )
    resources = tuple(ResourceState(f"resource-{index}") for index in range(3))
    config = PlannerConfig(
        enable_hysteresis=False,
        solver_name="hungarian_demand_slots",
    )
    planner = AssignmentPlanner(
        cost_model=cost_model or _FixedMToNCostModel(),
        config=config,
    )
    previous = planner.plan(tracks, resources, timestamp=0.0)
    planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        expected_previous_version=previous.version,
        forced_replan=True,
        publish=False,
    )
    return planner.latest_planning_evidence, config


def _write_bundle(
    path: Path,
    *,
    alpha: float,
    binding_changing: bool,
):
    torch = pytest.importorskip("torch")
    policy = SharedEdgeActorCriticPolicy(
        hidden_size=1,
        residual_bound=10.0,
    )
    with torch.no_grad():
        for parameter in policy.parameters():
            parameter.zero_()
        if binding_changing:
            previous_binding_index = EDGE_FEATURE_NAMES.index(
                "previous_binding"
            )
            first_layer = policy.edge_encoder[0]
            second_layer = policy.edge_encoder[2]
            first_layer.weight[0, previous_binding_index] = 2.0
            first_layer.bias[0] = -1.0
            second_layer.weight[0, 0] = 2.0
            policy.residual_mean_head.weight[0, 0] = 2.0
        policy.selection_head.bias[0] = 10.0

    manifest = save_model_bundle(
        path,
        policy,
        split_hash=_digest("split"),
        dataset_frames_sha256=_digest("dataset"),
        normalization_mean=np.zeros(len(EDGE_FEATURE_NAMES), dtype=float),
        normalization_scale=np.ones(len(EDGE_FEATURE_NAMES), dtype=float),
        training_results={"stage": "action_margin_unit_fixture"},
        alpha=alpha,
        min_confidence=0.0,
        deadline_s=1.0,
        provenance={
            "repository_git_commit": "a" * 40,
            "repository_git_commit_role": "exact_training_source_commit",
            "training_worktree_state": "clean",
            "training_source_sha256": _digest("training-source"),
            "dataset_manifest_sha256": _digest("dataset-manifest"),
            "training_entrypoint": "action_margin_unit_fixture",
            "training_date": "2026-07-27",
        },
        admission=development_shadow_admission(
            PAIRED_INTERVENTION_RESERVED_SEEDS_V1
        ),
        promotion_unavailable_reason="reserved_seed_evaluation_pending",
    )
    manifest_sha256 = sha256((path / "manifest.json").read_bytes()).hexdigest()
    return manifest, manifest_sha256


def _replay(
    tmp_path: Path,
    *,
    alpha: float,
    binding_changing: bool,
    cost_model=None,
):
    frame, config = _rule_frame(cost_model=cost_model)
    bundle_dir = tmp_path / "bundle"
    manifest, manifest_sha256 = _write_bundle(
        bundle_dir,
        alpha=alpha,
        binding_changing=binding_changing,
    )
    replay = replay_isolated_learning_intervention_frame(
        frame,
        sequence_index=0,
        bundle_dir=bundle_dir,
        expected_manifest_sha256=manifest_sha256,
        expected_policy_version=manifest.policy_version,
        planner_config=config,
        cost_weights=CostWeights(),
    )
    return replay, config


def test_zero_residual_is_reported_as_no_op(tmp_path: Path) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.25,
        binding_changing=False,
    )

    report = calibrate_a1_action_margin(
        replay,
        planner_config=planner_config,
        calibration_config=A1ActionMarginCalibrationConfig(
            candidate_alphas=(0.0, 0.25, 1.0),
            candidate_min_confidences=(0.0,),
            max_abs_cost_correction=1.0,
        ),
    )

    assert report.source_guard_passed is True
    assert report.source_binding_change_count == 0
    assert report.target_count == 2
    assert report.resource_count == 3
    assert report.hard_safe_action_count == 6
    assert report.lowest_identifiable_alpha is None
    assert all(item.classification == "no_op" for item in report.candidates)
    assert all(item.binding_change_count == 0 for item in report.candidates)


def test_alpha_grid_finds_identifiable_hungarian_intervention(
    tmp_path: Path,
) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.02,
        binding_changing=True,
    )
    assert replay.eligibility.binding_change_count == 0

    report = calibrate_a1_action_margin(
        replay,
        planner_config=planner_config,
        calibration_config=A1ActionMarginCalibrationConfig(
            candidate_alphas=(0.02, 0.1, 0.25, 0.5),
            candidate_min_confidences=(0.0,),
            max_abs_cost_correction=0.5,
        ),
    )

    by_alpha = {item.alpha: item for item in report.candidates}
    assert by_alpha[0.02].classification == "no_op"
    assert by_alpha[0.1].classification == "no_op"
    assert by_alpha[0.25].classification == (
        "identifiable_development_intervention"
    )
    assert by_alpha[0.25].binding_change_count == 3
    assert by_alpha[0.25].solver_name == "hungarian_demand_slots"
    assert by_alpha[0.25].rule_binding_sha256 != (
        by_alpha[0.25].candidate_binding_sha256
    )
    assert by_alpha[0.25].version_contract_passed is True
    assert report.lowest_identifiable_alpha == pytest.approx(0.25)
    assert any(
        item.required_alpha_to_cross == pytest.approx(0.15)
        for item in report.edge_margins
        if item.required_alpha_to_cross is not None
    )


def test_confidence_and_correction_safety_gates_fail_closed(
    tmp_path: Path,
) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.02,
        binding_changing=True,
    )

    report = calibrate_a1_action_margin(
        replay,
        planner_config=planner_config,
        calibration_config=A1ActionMarginCalibrationConfig(
            candidate_alphas=(0.25, 1.0),
            candidate_min_confidences=(0.0, 1.0),
            max_abs_cost_correction=0.3,
            max_binding_change_count=2,
        ),
    )

    by_key = {
        (item.alpha, item.min_confidence): item for item in report.candidates
    }
    confidence_blocked = by_key[(0.25, 1.0)]
    assert confidence_blocked.classification == "safety_gate_blocked"
    assert confidence_blocked.fallback_reason == "low_confidence"
    assert confidence_blocked.learning_applied is False
    binding_blocked = by_key[(0.25, 0.0)]
    assert binding_blocked.classification == "safety_gate_blocked"
    assert "binding_change_limit_exceeded" in binding_blocked.reason_codes
    correction_blocked = by_key[(1.0, 0.0)]
    assert correction_blocked.evaluated is False
    assert correction_blocked.reason_codes == (
        "cost_correction_bound_exceeded",
    )
    assert correction_blocked.binding_change_count == 0

    with pytest.raises(PairedInterventionContractError) as mismatch:
        calibrate_a1_action_margin(
            replay,
            planner_config=replace(
                planner_config,
                reassignment_switch_penalty=10.0,
            ),
            calibration_config=A1ActionMarginCalibrationConfig(
                candidate_alphas=(0.25,),
                candidate_min_confidences=(0.0,),
            ),
        )
    assert mismatch.value.code == "rule_matrix_replay_mismatch"


def test_identifiable_candidate_remains_unseen_and_unauthorized(
    tmp_path: Path,
) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.02,
        binding_changing=True,
    )

    report = calibrate_a1_action_margin(
        replay,
        planner_config=planner_config,
        calibration_config=A1ActionMarginCalibrationConfig(
            candidate_alphas=(0.25,),
            candidate_min_confidences=(0.0,),
            max_abs_cost_correction=0.25,
        ),
    )
    candidate = report.candidates[0]

    assert candidate.identifiable is True
    assert candidate.authorization_state == "not_authorized"
    assert candidate.runtime_publication_allowed is False
    assert candidate.assignment_authority_allowed is False
    assert candidate.control_authority_allowed is False
    assert report.development_only is True
    assert report.formal_evidence is False
    assert report.unseen_seed_evidence is False
    assert report.runtime_publication_allowed is False
    assert report.assignment_authority_allowed is False
    assert report.control_authority_allowed is False
    assert "seed" not in report.to_dict()


def test_source_with_existing_binding_change_is_not_recalibrated(
    tmp_path: Path,
) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.25,
        binding_changing=True,
    )
    assert replay.eligibility.binding_change_count > 0

    report = calibrate_a1_action_margin(
        replay,
        planner_config=planner_config,
        calibration_config=A1ActionMarginCalibrationConfig(
            candidate_alphas=(0.25,),
            candidate_min_confidences=(0.0,),
        ),
    )

    assert report.source_guard_passed is False
    assert "source_binding_already_changed" in report.source_guard_reasons
    assert report.candidates[0].evaluated is False
    assert report.candidates[0].assignment_authority_allowed is False


def test_no_feasible_action_inventory_fails_closed(tmp_path: Path) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.25,
        binding_changing=False,
        cost_model=_NoFeasibleMToNCostModel(),
    )

    report = calibrate_a1_action_margin(
        replay,
        planner_config=planner_config,
        calibration_config=A1ActionMarginCalibrationConfig(
            candidate_alphas=(0.25,),
            candidate_min_confidences=(0.0,),
        ),
    )

    assert report.hard_safe_action_count == 0
    assert "source_no_feasible_actions" in report.source_guard_reasons
    assert report.edge_margins == ()
    assert report.candidates[0].classification == "safety_gate_blocked"
    assert report.candidates[0].solver_name is None


@pytest.mark.parametrize(
    "replacement, expected",
    (
        (np.empty((0, 3), dtype=float), "matrix shape mismatch"),
        (
            np.asarray(((np.nan, 0.2, 0.4), (0.4, 0.3, 0.1))),
            "non-finite",
        ),
    ),
)
def test_post_construction_matrix_tampering_fails_closed(
    tmp_path: Path,
    replacement: np.ndarray,
    expected: str,
) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.25,
        binding_changing=False,
    )
    object.__setattr__(
        replay.rule_frame.rule_matrix_result,
        "matrix",
        replacement,
    )

    with pytest.raises(ValueError, match=expected):
        calibrate_a1_action_margin(
            replay,
            planner_config=planner_config,
        )


def test_invalid_calibration_configuration_is_rejected(
    tmp_path: Path,
) -> None:
    replay, planner_config = _replay(
        tmp_path,
        alpha=0.25,
        binding_changing=False,
    )

    with pytest.raises(ValueError, match="candidate_alphas"):
        A1ActionMarginCalibrationConfig(candidate_alphas=(float("nan"),))
    with pytest.raises(TypeError, match="calibration_config"):
        calibrate_a1_action_margin(
            replay,
            planner_config=planner_config,
            calibration_config={},  # type: ignore[arg-type]
        )
