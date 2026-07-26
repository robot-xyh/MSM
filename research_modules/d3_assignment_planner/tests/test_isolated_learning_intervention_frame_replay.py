from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pytest

from commitment_test_support import committed_target_track
from d3_assignment_planner import (
    EDGE_FEATURE_NAMES,
    PAIRED_INTERVENTION_RESERVED_SEEDS_V1,
    AssignmentPlanner,
    CostMatrixResult,
    CostWeights,
    PairedInterventionContractError,
    PlannerConfig,
    ResourceState,
    SharedEdgeActorCriticPolicy,
    TargetDemand,
    canonical_isolated_learning_intervention_frame_replay_sha256,
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
            reject_reasons=(
                (None, None, None),
                (None, None, None),
            ),
            candidate_mask=np.ones((2, 3), dtype=bool),
        )


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _rule_frame(
    *,
    timestamp_s: float = 1.0,
    stale_after_s: float | None = None,
):
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
        stale_after_s=stale_after_s,
    )
    planner = AssignmentPlanner(
        cost_model=_FixedMToNCostModel(),
        config=config,
    )
    previous = planner.plan(tracks, resources, timestamp=0.0)
    planner.plan(
        tracks,
        resources,
        timestamp=timestamp_s,
        previous_plan=previous,
        expected_previous_version=previous.version,
        forced_replan=True,
        publish=False,
    )
    frame = planner.latest_planning_evidence
    assert frame.available
    assert frame.learning_state == "rule_only"
    assert frame.previous_plan is not None
    return frame, config


def _new_target_rule_frame():
    """Build the real replay shape where one target gains its first coalition."""

    previous_tracks = tuple(
        committed_target_track(
            f"global-track-{index}",
            0.8 - index * 0.05,
            100.0 + index * 10.0,
            0.0,
        )
        for index in range(4)
    )
    tracks = previous_tracks + (
        committed_target_track(
            "global-track-4",
            0.9,
            140.0,
            0.0,
        ),
    )
    resources = tuple(ResourceState(f"resource-{index}") for index in range(5))
    config = PlannerConfig(
        enable_hysteresis=False,
        solver_name="hungarian",
    )
    planner = AssignmentPlanner(config=config)
    previous = planner.plan(previous_tracks, resources, timestamp=0.0)
    planner.plan(
        tracks,
        resources,
        timestamp=1.0,
        previous_plan=previous,
        expected_previous_version=previous.version,
        publish=False,
    )
    frame = planner.latest_planning_evidence
    assert frame.available
    assert frame.plan is not None
    assert frame.previous_plan is not None
    assert len(frame.previous_plan.coalitions) == 4
    assert len(frame.plan.coalitions) == 5
    return frame, config


def _replace_plan_coalition_id(
    plan,
    *,
    target_id: str,
    coalition_id: str,
):
    return replace(
        plan,
        assignments=tuple(
            replace(item, coalition_id=coalition_id)
            if item.target_id == target_id
            else item
            for item in plan.assignments
        ),
        coalitions=tuple(
            replace(item, coalition_id=coalition_id)
            if item.target_id == target_id
            else item
            for item in plan.coalitions
        ),
        demand_summaries=tuple(
            replace(item, coalition_id=coalition_id)
            if item.target_id == target_id
            else item
            for item in plan.demand_summaries
        ),
    )


def _write_bundle(
    path: Path,
    *,
    binding_changing: bool = True,
    deadline_s: float = 1.0,
    normalization_scale: float = 1.0,
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
        normalization_scale=np.full(
            len(EDGE_FEATURE_NAMES),
            normalization_scale,
            dtype=float,
        ),
        training_results={"stage": "single_frame_replay_unit_fixture"},
        alpha=1.0,
        min_confidence=0.0,
        deadline_s=deadline_s,
        provenance={
            "repository_git_commit": "a" * 40,
            "repository_git_commit_role": "exact_training_source_commit",
            "training_worktree_state": "clean",
            "training_source_sha256": _digest("training-source"),
            "dataset_manifest_sha256": _digest("dataset-manifest"),
            "training_entrypoint": "single_frame_replay_unit_fixture",
            "training_date": "2026-07-26",
        },
        admission=development_shadow_admission(
            PAIRED_INTERVENTION_RESERVED_SEEDS_V1
        ),
        promotion_unavailable_reason="reserved_seed_evaluation_pending",
    )
    return manifest, _file_digest(path / "manifest.json")


def _replay(
    frame,
    config: PlannerConfig,
    bundle_dir: Path,
    manifest_sha256: str,
    policy_version: str,
    *,
    sequence_index: int = 4,
):
    return replay_isolated_learning_intervention_frame(
        frame,
        sequence_index=sequence_index,
        bundle_dir=bundle_dir,
        expected_manifest_sha256=manifest_sha256,
        expected_policy_version=policy_version,
        planner_config=config,
        cost_weights=CostWeights(),
    )


def _assert_complete_m_to_n_plan(plan) -> None:
    assert len(plan.assignments) == 3
    assert plan.unassigned_target_ids == ()
    assert plan.incomplete_target_ids == ()
    assert sum(item.demand_required for item in plan.demand_summaries) == 3
    assert all(item.coalition_complete for item in plan.demand_summaries)
    assert all(item.complete for item in plan.coalitions)


def test_positive_m_to_n_replay_is_serialized_truth_free_and_non_authoritative(
    tmp_path: Path,
) -> None:
    frame, config = _rule_frame()
    bundle_dir = tmp_path / "bundle"
    manifest, manifest_sha256 = _write_bundle(bundle_dir)

    result = _replay(
        frame,
        config,
        bundle_dir,
        manifest_sha256,
        manifest.policy_version,
    )
    payload = result.to_dict()

    assert result.bundle_loaded is True
    assert result.bundle_fallback_reason is None
    assert result.rule_frame.learning_state == "rule_only"
    assert result.treatment_frame.learning_state == "assist_effective"
    assert result.eligibility.eligible is True
    assert result.eligibility.reason_codes == ("eligible",)
    assert result.eligibility.model_applied_edge_count == 6
    assert result.eligibility.binding_change_count == 3
    assert result.eligibility.m_to_n_target_count == 1
    assert result.content_sha256 == (
        canonical_isolated_learning_intervention_frame_replay_sha256(result)
    )
    assert result.isolated_simulation is True
    assert result.runtime_publication_allowed is False
    assert result.runtime_ack_available is False
    assert result.authority_available is False
    assert payload["execution_boundary"] == {
        "isolated_simulation": True,
        "publish_allowed": False,
        "runtime_ack_available": False,
        "authority_available": False,
        "global_track_id_rewrite_count": 0,
    }
    assert tuple(item.track_id for item in result.rule_frame.tracks) == tuple(
        item.track_id for item in result.treatment_frame.tracks
    )
    assert (
        result.treatment_frame.effective_matrix_result.metadata[
            "learning_applied"
        ]
        is True
    )
    _assert_complete_m_to_n_plan(result.rule_frame.plan)
    _assert_complete_m_to_n_plan(result.treatment_frame.plan)
    json.dumps(payload, allow_nan=False, sort_keys=True)
    rendered = json.dumps(payload, allow_nan=False, sort_keys=True).lower()
    for forbidden in (
        '"truth"',
        '"ground_truth"',
        '"physical_outcome"',
        '"intercept_success"',
        '"reward"',
    ):
        assert forbidden not in rendered


def test_new_target_replay_restores_hash_bound_recorded_coalition_identity(
    tmp_path: Path,
) -> None:
    frame, config = _new_target_rule_frame()
    result = _replay(
        frame,
        config,
        tmp_path / "missing-bundle",
        _digest("missing-manifest"),
        "missing-policy",
    )

    recorded_ids = {
        item.target_id: item.coalition_id for item in frame.plan.coalitions
    }
    previous_ids = {
        item.target_id: item.coalition_id
        for item in frame.previous_plan.coalitions
    }
    for replayed_frame in (result.rule_frame, result.treatment_frame):
        replayed_plan = replayed_frame.plan
        assert replayed_plan is not None
        replayed_ids = {
            item.target_id: item.coalition_id
            for item in replayed_plan.coalitions
        }
        assert replayed_ids == recorded_ids
        assert all(
            replayed_ids[target_id] == coalition_id
            for target_id, coalition_id in previous_ids.items()
        )
        assert replayed_plan.metadata[
            "offline_recorded_coalition_identity_applied"
        ] is True
        assert replayed_plan.metadata[
            "offline_recorded_coalition_identity_restored_target_ids"
        ] == ("target_0004",)
        assert replayed_plan.metadata[
            "offline_recorded_coalition_identity_publish_allowed"
        ] is False
        assert replayed_plan.metadata[
            "offline_recorded_coalition_identity_runtime_ack"
        ] is False
        assert replayed_plan.metadata[
            "offline_recorded_coalition_identity_authority"
        ] is False
        summary_ids = {
            item["target_id"]: item["coalition_id"]
            for item in replayed_plan.metadata["demand_summaries"]
        }
        membership_ids = {
            item["target_id"]: item["coalition_id"]
            for item in replayed_plan.metadata["coalition_membership"]
        }
        assert summary_ids["target_0004"] == "coalition_0004"
        assert membership_ids["target_0004"] == "coalition_0004"


def test_recorded_new_target_coalition_duplicate_is_rejected(
    tmp_path: Path,
) -> None:
    frame, config = _new_target_rule_frame()
    duplicate_id = frame.plan.coalitions[0].coalition_id
    tampered = replace(
        frame,
        plan=_replace_plan_coalition_id(
            frame.plan,
            target_id="target_0004",
            coalition_id=duplicate_id,
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "missing-bundle",
            _digest("missing-manifest"),
            "missing-policy",
        )

    assert captured.value.code == (
        "offline_recorded_coalition_identity_duplicate"
    )


def test_recorded_previous_target_coalition_rewrite_is_rejected(
    tmp_path: Path,
) -> None:
    frame, config = _new_target_rule_frame()
    tampered = replace(
        frame,
        plan=_replace_plan_coalition_id(
            frame.plan,
            target_id="target_0000",
            coalition_id="coalition_rewritten",
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "missing-bundle",
            _digest("missing-manifest"),
            "missing-policy",
        )

    assert captured.value.code == (
        "offline_recorded_coalition_identity_previous_rewrite"
    )


@pytest.mark.parametrize("tamper_kind", ("assignment", "summary", "metadata"))
def test_recorded_coalition_reference_tampering_is_rejected(
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    frame, config = _new_target_rule_frame()
    plan = frame.plan
    if tamper_kind == "assignment":
        plan = replace(
            plan,
            assignments=tuple(
                replace(item, coalition_id="coalition_wrong")
                if item.target_id == "target_0004"
                else item
                for item in plan.assignments
            ),
        )
        expected_code = (
            "offline_recorded_coalition_identity_assignment_mismatch"
        )
    elif tamper_kind == "summary":
        plan = replace(
            plan,
            demand_summaries=tuple(
                replace(item, coalition_id="coalition_wrong")
                if item.target_id == "target_0004"
                else item
                for item in plan.demand_summaries
            ),
        )
        expected_code = "offline_recorded_coalition_identity_summary_mismatch"
    else:
        membership = tuple(
            {
                "target_id": item.target_id,
                "coalition_id": (
                    "coalition_wrong"
                    if item.target_id == "target_0004"
                    else item.coalition_id
                ),
                "coalition_version": item.version,
                "coalition_epoch": item.epoch,
            }
            for item in plan.coalitions
        )
        plan = replace(
            plan,
            metadata={
                **dict(plan.metadata),
                "coalition_membership": membership,
            },
        )
        expected_code = "offline_recorded_coalition_identity_metadata_mismatch"
    tampered = replace(frame, plan=plan)

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "missing-bundle",
            _digest("missing-manifest"),
            "missing-policy",
        )

    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    ("identity_kind", "expected_reason"),
    (
        ("manifest", "bundle_manifest_sha256_mismatch"),
        ("policy", "bundle_policy_version_mismatch"),
    ),
)
def test_bundle_identity_mismatch_falls_back_and_cannot_be_eligible(
    tmp_path: Path,
    identity_kind: str,
    expected_reason: str,
) -> None:
    frame, config = _rule_frame()
    bundle_dir = tmp_path / "bundle"
    manifest, manifest_sha256 = _write_bundle(bundle_dir)
    expected_manifest = (
        _digest("wrong-manifest")
        if identity_kind == "manifest"
        else manifest_sha256
    )
    expected_policy = (
        "wrong-policy"
        if identity_kind == "policy"
        else manifest.policy_version
    )

    result = _replay(
        frame,
        config,
        bundle_dir,
        expected_manifest,
        expected_policy,
    )

    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == expected_reason
    assert result.eligibility.eligible is False
    assert result.treatment_frame.learning_state == "rule_fallback"
    assert (
        result.treatment_frame.effective_matrix_result.metadata[
            "learning_applied"
        ]
        is False
    )


def test_non_shadow_development_manifest_cannot_apply_treatment(
    tmp_path: Path,
) -> None:
    frame, config = _rule_frame()
    bundle_dir = tmp_path / "bundle"
    manifest, _ = _write_bundle(bundle_dir)
    manifest_path = bundle_dir / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["admission"]["allowed_modes"] = ["shadow", "assist"]
    manifest_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = _replay(
        frame,
        config,
        bundle_dir,
        _file_digest(manifest_path),
        manifest.policy_version,
    )

    assert result.bundle_loaded is False
    assert result.bundle_fallback_reason == "model_manifest_invalid"
    assert result.eligibility.eligible is False
    assert result.treatment_frame.learning_state == "rule_fallback"
    assert (
        result.treatment_frame.effective_matrix_result.metadata[
            "learning_applied"
        ]
        is False
    )


def test_valid_zero_residual_bundle_is_applied_but_binding_is_ineligible(
    tmp_path: Path,
) -> None:
    frame, config = _rule_frame()
    bundle_dir = tmp_path / "bundle"
    manifest, manifest_sha256 = _write_bundle(
        bundle_dir,
        binding_changing=False,
    )

    result = _replay(
        frame,
        config,
        bundle_dir,
        manifest_sha256,
        manifest.policy_version,
    )

    assert result.bundle_loaded is True
    assert result.treatment_frame.learning_state == "assist_effective"
    assert result.eligibility.eligible is False
    assert result.eligibility.binding_change_count == 0
    assert "binding_unchanged" in result.eligibility.reason_codes


@pytest.mark.parametrize("forbidden_key", ("truth", "reward", "physical_outcome"))
def test_truth_reward_and_outcome_fields_are_rejected(
    tmp_path: Path,
    forbidden_key: str,
) -> None:
    frame, config = _rule_frame()
    resource = replace(
        frame.resources[0],
        metadata={
            **dict(frame.resources[0].metadata),
            forbidden_key: "forbidden",
        },
    )
    tampered = replace(frame, resources=(resource, *frame.resources[1:]))

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "unused",
            _digest("manifest"),
            "policy",
        )

    assert captured.value.code == "offline_execution_online_label_key_present"


def test_previous_plan_version_mismatch_is_rejected(tmp_path: Path) -> None:
    frame, config = _rule_frame()
    tampered = replace(
        frame,
        previous_plan_version=frame.previous_plan.version + 1,
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "unused",
            _digest("manifest"),
            "policy",
        )

    assert captured.value.code == (
        "single_frame_replay_previous_plan_version_mismatch"
    )


def test_stale_previous_plan_time_window_is_rejected(tmp_path: Path) -> None:
    frame, config = _rule_frame()
    tampered = replace(
        frame,
        previous_plan=replace(frame.previous_plan, stale_after_s=0.1),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "unused",
            _digest("manifest"),
            "policy",
        )

    assert captured.value.code == "single_frame_replay_stale_previous_plan"


def test_rule_and_effective_input_mismatch_is_rejected(tmp_path: Path) -> None:
    frame, config = _rule_frame()
    matrix = np.asarray(frame.effective_matrix, dtype=float).copy()
    matrix[0, 0] += 0.01
    tampered = replace(
        frame,
        effective_matrix_result=replace(
            frame.effective_matrix_result,
            matrix=matrix,
        ),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "unused",
            _digest("manifest"),
            "policy",
        )

    assert captured.value.code == (
        "single_frame_replay_rule_effective_matrix_mismatch"
    )


def test_nonfinite_rule_input_is_rejected(tmp_path: Path) -> None:
    frame, config = _rule_frame()
    matrix = np.asarray(frame.rule_matrix, dtype=float).copy()
    matrix[0, 0] = np.nan
    tampered = replace(
        frame,
        rule_matrix_result=replace(frame.rule_matrix_result, matrix=matrix),
    )

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "unused",
            _digest("manifest"),
            "policy",
        )

    assert captured.value.code == "offline_execution_rule_input_nonfinite"


@pytest.mark.parametrize("tamper_kind", ("order", "set"))
def test_global_track_id_order_or_set_change_is_rejected(
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    frame, config = _rule_frame()
    if tamper_kind == "order":
        tracks = tuple(reversed(frame.tracks))
    else:
        tracks = (
            replace(frame.tracks[0], track_id="target_modified"),
            *frame.tracks[1:],
        )
    tampered = replace(frame, tracks=tracks)

    with pytest.raises(PairedInterventionContractError) as captured:
        _replay(
            tampered,
            config,
            tmp_path / "unused",
            _digest("manifest"),
            "policy",
        )

    assert captured.value.code == (
        "single_frame_replay_global_track_id_snapshot_mismatch"
    )


def test_content_hash_and_input_lineage_tampering_are_rejected(
    tmp_path: Path,
) -> None:
    frame, config = _rule_frame()
    bundle_dir = tmp_path / "bundle"
    manifest, manifest_sha256 = _write_bundle(bundle_dir)
    result = _replay(
        frame,
        config,
        bundle_dir,
        manifest_sha256,
        manifest.policy_version,
    )

    with pytest.raises(PairedInterventionContractError) as hash_error:
        replace(result, content_sha256=_digest("tampered-content"))
    assert hash_error.value.code == "single_frame_replay_content_sha256_mismatch"

    treatment = replace(
        result.treatment_frame,
        timestamp_s=result.treatment_frame.timestamp_s + 0.25,
    )
    with pytest.raises(PairedInterventionContractError) as lineage_error:
        replace(result, treatment_frame=treatment)
    assert lineage_error.value.code == (
        "single_frame_replay_input_lineage_mismatch"
    )


@pytest.mark.parametrize(
    ("bundle_option", "expected_fallback"),
    (
        ({"normalization_scale": 1.0e-12}, "out_of_distribution"),
        ({"deadline_s": 1.0e-12}, "model_timeout"),
    ),
)
def test_ood_and_timeout_fallbacks_remain_ineligible(
    tmp_path: Path,
    bundle_option: dict[str, float],
    expected_fallback: str,
) -> None:
    frame, config = _rule_frame()
    bundle_dir = tmp_path / "bundle"
    manifest, manifest_sha256 = _write_bundle(bundle_dir, **bundle_option)

    result = _replay(
        frame,
        config,
        bundle_dir,
        manifest_sha256,
        manifest.policy_version,
    )

    assert result.bundle_loaded is True
    assert result.treatment_frame.learning_state == "rule_fallback"
    assert result.treatment_frame.fallback_reason == expected_fallback
    assert result.eligibility.eligible is False
    assert result.eligibility.fallback_reason == expected_fallback
