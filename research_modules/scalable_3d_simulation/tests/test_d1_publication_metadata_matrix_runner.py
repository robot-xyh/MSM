from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from research_modules.d1_sensor_fusion.src.d1_sensor_fusion import (
    Scalable3DFusionAdapter,
)
from research_modules.scalable_3d_simulation.scripts import (
    run_d1_publication_metadata_matrix as matrix_runner,
)


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_publication_metadata_multiseed_v1.json"
)
V2_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_publication_metadata_v2_multiseed_v1.json"
)
CV_MOTION_MODEL_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_cv_motion_model_cache_multiseed_v1.json"
)
OPAQUE_SOURCE_IDENTITY_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_opaque_source_identity_cache_multiseed_v1.json"
)
ONLINE_BATCH_FRAME_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_online_batch_frame_multiseed_v1.json"
)
ONLINE_TRUTH_GUARD_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "online_truth_guard_multiseed_v1.json"
)
STRUCTURED_JACOBIAN_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_structured_numerical_jacobian_multiseed_v1.json"
)
ASSOCIATION_SPARSE_PREFILTER_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_association_sparse_prefilter_multiseed_v1.json"
)
REPLAY_PREFIX_SUMMARY_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_replay_prefix_summary_multiseed_v1.json"
)
PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_publication_evidence_snapshot_multiseed_v1.json"
)


def test_publication_metadata_matrix_freezes_same_commit_13_pair_contract() -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["same_clean_commit_required"] is True
    assert matrix["arm_implementations"] == {
        "reference": "per_track_copy_v1",
        "candidate": "immutable_shared_v1",
    }
    assert [case["seed"] for case in short] == list(range(1101, 1111))
    assert [case["seed"] for case in long] == [1101, 1102, 1103]
    assert {case["duration_s"] for case in short} == {2.2}
    assert {case["duration_s"] for case in long} == {10.0}
    assert matrix["admission_gates"][
        "short_minimum_d1_fusion_improvement_pct"
    ] == 10.0
    assert matrix["admission_gates"][
        "long_minimum_d1_fusion_improvement_pct"
    ] == 10.0


def test_publication_metadata_v2_matrix_freezes_audit_and_regression_gates() -> None:
    matrix = matrix_runner.load_matrix(V2_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "per_track_copy_v1",
        "candidate": "immutable_shared_v2",
    }
    assert len(short) == 10
    assert len(long) == 3
    assert matrix["admission_gates"][
        "all_pairs_d2_publication_metadata_audit_valid"
    ] is True
    assert matrix["admission_gates"][
        "maximum_short_d2_association_mean_increase_pct"
    ] == 5.0
    assert matrix["admission_gates"][
        "maximum_long_d2_association_mean_increase_pct"
    ] == 5.0
    boundary = matrix["evidence_boundary"]
    assert boundary["candidate_publication_audit_contract_version"] == (
        "d1.publication_audit_tree.v2"
    )
    assert boundary["d2_content_audit_required_before_identity_reuse"] is True


def test_cv_motion_model_matrix_freezes_exact_cache_and_admission_gates() -> None:
    matrix = matrix_runner.load_matrix(CV_MOTION_MODEL_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "per_prediction_build_v1",
        "candidate": "bounded_exact_lru_v1",
    }
    assert len(short) == 10
    assert len(long) == 3
    assert matrix["admission_gates"][
        "minimum_candidate_model_build_reduction_pct"
    ] == 95.0
    assert matrix["admission_gates"][
        "minimum_candidate_cache_hit_ratio_pct"
    ] == 95.0
    assert matrix["admission_gates"][
        "short_minimum_core_wall_improvement_pct"
    ] == 2.0
    assert matrix["evidence_boundary"]["cache_key_policy"] == (
        "exact_dt_process_noise"
    )
    assert matrix["evidence_boundary"]["cache_capacity"] == 128
    assert matrix["evidence_boundary"]["matrix_values_are_read_only"] is True


def test_opaque_source_identity_matrix_freezes_source_only_cache_contract() -> None:
    matrix = matrix_runner.load_matrix(OPAQUE_SOURCE_IDENTITY_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "per_publication_build_v1",
        "candidate": "bounded_generation_lru_v1",
    }
    assert len(short) == 10
    assert len(long) == 3
    assert matrix["run_flags"] == [
        "--integrated-stack",
        "--d1-publish-opaque-source-key",
    ]
    assert matrix["admission_gates"][
        "minimum_candidate_identity_build_reduction_pct"
    ] == 95.0
    assert matrix["admission_gates"][
        "minimum_candidate_cache_hit_ratio_pct"
    ] == 95.0
    boundary = matrix["evidence_boundary"]
    assert boundary["cache_key_policy"] == (
        "publisher_node_id_publisher_epoch_track_id"
    )
    assert boundary["cache_capacity"] == 1_024
    assert boundary["source_only_publication"] is True
    assert boundary["structural_ambiguity_hold_enabled"] is False


def test_online_batch_frame_matrix_freezes_default_r0_handoff_contract() -> None:
    matrix = matrix_runner.load_matrix(ONLINE_BATCH_FRAME_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "convert_then_frame_v1",
        "candidate": "closed_immutable_batch_to_frame_v1",
    }
    assert matrix["run_flags"] == ["--integrated-stack"]
    assert [case["seed"] for case in short] == list(range(1121, 1131))
    assert [case["seed"] for case in long] == [1121, 1122, 1123]
    assert matrix["admission_gates"][
        "short_minimum_scan_input_improvement_pct"
    ] == 20.0
    assert matrix["admission_gates"][
        "long_minimum_scan_input_improvement_pct"
    ] == 20.0
    assert matrix["admission_gates"][
        "minimum_candidate_closed_handoff_ratio_pct"
    ] == 99.0
    boundary = matrix["evidence_boundary"]
    assert boundary["candidate_default_off"] is True
    assert boundary["full_raw_batch_identity_check_preserved"] is True
    assert boundary["final_readonly_frame_check_preserved"] is True
    assert boundary["raw_source_absolute_immutability_claimed"] is False
    assert boundary["development_profile_seed_excluded"] == 1112


def test_truth_guard_matrix_freezes_same_commit_performance_contract() -> None:
    matrix = matrix_runner.load_matrix(ONLINE_TRUTH_GUARD_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "generic_recursive_v1",
        "candidate": "builtin_specialized_recursive_v2",
    }
    assert [case["seed"] for case in short] == list(range(1101, 1111))
    assert [case["seed"] for case in long] == [1101, 1102, 1103]
    assert matrix["admission_gates"][
        "short_minimum_publication_bus_improvement_pct"
    ] == 10.0
    assert matrix["admission_gates"][
        "long_minimum_publication_bus_improvement_pct"
    ] == 10.0
    assert matrix["admission_gates"][
        "short_minimum_core_wall_improvement_pct"
    ] == 0.5
    assert matrix["evidence_boundary"]["candidate_is_default"] is False


def test_structured_jacobian_matrix_freezes_same_commit_contract() -> None:
    matrix = matrix_runner.load_matrix(STRUCTURED_JACOBIAN_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "dense_output_probe_v1",
        "candidate": "known_dimension_structural_columns_v1",
    }
    assert [case["seed"] for case in short] == list(range(1101, 1111))
    assert [case["seed"] for case in long] == [1101, 1102, 1103]
    assert matrix["admission_gates"][
        "short_minimum_d1_fusion_improvement_pct"
    ] == 2.0
    assert matrix["admission_gates"][
        "long_minimum_d1_fusion_improvement_pct"
    ] == 2.0
    assert matrix["admission_gates"][
        "minimum_candidate_measurement_evaluation_reduction_pct"
    ] == 35.0
    boundary = matrix["evidence_boundary"]
    assert boundary["structured_jacobian_diagnostics_schema_version"] == (
        "d1.structured_numerical_jacobian_diagnostics.v1"
    )
    assert boundary["known_active_columns_by_modality"] is True
    assert (
        boundary["active_columns_preserve_reference_centered_difference"]
        is True
    )


def test_association_sparse_prefilter_matrix_freezes_safe_admission_contract() -> None:
    matrix = matrix_runner.load_matrix(
        ASSOCIATION_SPARSE_PREFILTER_MATRIX_PATH
    )
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "disabled_v1",
        "candidate": "modality_conservative_quadratic_bound_v1",
    }
    assert matrix["run_flags"] == ["--integrated-stack"]
    assert [case["seed"] for case in short] == list(range(1131, 1141))
    assert [case["seed"] for case in long] == [1131, 1132, 1133]
    gates = matrix["admission_gates"]
    assert gates[
        "all_pairs_association_sparse_prefilter_audit_valid"
    ] is True
    assert gates["all_pairs_exact_gate_pass_counts_equal"] is True
    assert gates[
        "minimum_candidate_non_radar_exact_solve_reduction_pct"
    ] == 20.0
    boundary = matrix["evidence_boundary"]
    assert boundary["candidate_default_off"] is True
    assert boundary["uncertified_pairs_fail_open"] is True
    assert boundary["exact_residual_semantics_preserved"] is True
    assert boundary["exact_association_gate_unchanged"] is True
    assert boundary["truth_dependent_inputs_forbidden"] is True


def test_association_sparse_prefilter_commands_isolate_only_the_selector(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(
        ASSOCIATION_SPARSE_PREFILTER_MATRIX_PATH
    )
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    selector_index = reference.index(
        "--d1-association-sparse-prefilter-implementation"
    )
    output_index = reference.index("--output")
    assert reference[selector_index + 1] == "disabled_v1"
    assert candidate[selector_index + 1] == (
        "modality_conservative_quadratic_bound_v1"
    )
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {selector_index + 1, output_index + 1}:
            assert left == right


@pytest.mark.parametrize(
    ("selector", "implementation_id", "candidate"),
    [
        (
            "disabled_v1",
            "d1.fusion.association_sparse_prefilter.disabled.v1",
            False,
        ),
        (
            "modality_conservative_quadratic_bound_v1",
            "d1.fusion.association_sparse_prefilter."
            "modality_conservative_quadratic_bound.v1",
            True,
        ),
    ],
)
def test_association_sparse_prefilter_resume_audit_accepts_sorted_json(
    selector: str,
    implementation_id: str,
    candidate: bool,
) -> None:
    diagnostics = Scalable3DFusionAdapter(
        association_sparse_prefilter=selector
    ).association_sparse_prefilter_diagnostics()
    persisted = json.loads(json.dumps(diagnostics, sort_keys=True))

    assert matrix_runner._association_sparse_prefilter_diagnostics_match(
        persisted,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=candidate,
        require_workload=False,
    )


def test_replay_prefix_summary_matrix_freezes_safe_admission_contract() -> None:
    matrix = matrix_runner.load_matrix(REPLAY_PREFIX_SUMMARY_MATRIX_PATH)
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "per_checkpoint_prefix_rebuild_v1",
        "candidate": "fixed_lag_checkpoint_prefix_cumulative_summary_v1",
    }
    assert matrix["run_flags"] == ["--integrated-stack"]
    assert [case["seed"] for case in short] == list(range(1151, 1161))
    assert [case["seed"] for case in long] == [1151, 1152, 1153]
    gates = matrix["admission_gates"]
    assert gates["all_pairs_replay_prefix_summary_audit_valid"] is True
    assert gates[
        "all_pairs_consistency_evidence_records_digest_equal"
    ] is True
    assert gates["all_pairs_existing_operation_counts_equal"] is True
    assert gates[
        "minimum_candidate_lazy_materialization_reduction_pct"
    ] == 20.0
    boundary = matrix["evidence_boundary"]
    assert boundary["candidate_default_off"] is True
    assert boundary["fixed_lag_window_changed"] is False
    assert boundary["checkpoint_audit_semantics_changed"] is False
    assert boundary["consistency_evidence_semantics_changed"] is False
    assert boundary["checkpoint_mutations_advance_revision"] is True
    assert boundary["development_profile_seed_excluded"] == 1141


def test_replay_prefix_summary_commands_isolate_only_the_selector(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(REPLAY_PREFIX_SUMMARY_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    selector_index = reference.index(
        "--d1-replay-prefix-summary-implementation"
    )
    output_index = reference.index("--output")
    assert (
        reference[selector_index + 1]
        == "per_checkpoint_prefix_rebuild_v1"
    )
    assert candidate[selector_index + 1] == (
        "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
    )
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {selector_index + 1, output_index + 1}:
            assert left == right


@pytest.mark.parametrize(
    ("selector", "implementation_id", "candidate"),
    [
        (
            "per_checkpoint_prefix_rebuild_v1",
            "d1.fusion.replay_prefix.per_checkpoint_rebuild.v1",
            False,
        ),
        (
            "fixed_lag_checkpoint_prefix_cumulative_summary_v1",
            "d1.fusion.replay_prefix."
            "frozen_cumulative_summary_lazy_evidence_ranges.v1",
            True,
        ),
    ],
)
def test_replay_prefix_summary_resume_audit_accepts_sorted_json(
    selector: str,
    implementation_id: str,
    candidate: bool,
) -> None:
    diagnostics = Scalable3DFusionAdapter(
        replay_prefix_summary=selector
    ).replay_prefix_summary_diagnostics()
    persisted = json.loads(json.dumps(diagnostics, sort_keys=True))

    assert matrix_runner._replay_prefix_summary_diagnostics_match(
        persisted,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=candidate,
        require_workload=False,
        require_materialized=True,
    )


def test_replay_prefix_summary_audit_distinguishes_pre_export_and_exported_state(
) -> None:
    selector = "fixed_lag_checkpoint_prefix_cumulative_summary_v1"
    implementation_id = (
        "d1.fusion.replay_prefix."
        "frozen_cumulative_summary_lazy_evidence_ranges.v1"
    )
    adapter = Scalable3DFusionAdapter(replay_prefix_summary=selector)
    pre_export = adapter.replay_prefix_summary_diagnostics()
    pre_export["operation_counts"] = {
        "summary_attempt_count": 3,
        "summary_hit_count": 2,
        "summary_fallback_count": 1,
        "summary_reused_checkpoint_count": 4,
        "lazy_consistency_refresh_logical_record_count": 5,
        "append_only_revision_advance_count": 3,
        "append_only_pending_preservation_count": 2,
        "public_snapshot_projection_count": 1,
        "public_snapshot_projected_record_count": 4,
    }
    pre_export["fallback_reasons"] = {"no_checkpoint_prefix": 1}
    pre_export["materialization_reasons"] = {}
    pre_export["pending_consistency_ledger_count"] = 2

    assert matrix_runner._replay_prefix_summary_diagnostics_match(
        pre_export,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=True,
        require_workload=True,
        require_materialized=False,
    )
    assert not matrix_runner._replay_prefix_summary_diagnostics_match(
        pre_export,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=True,
        require_workload=True,
        require_materialized=True,
    )

    exported = copy.deepcopy(pre_export)
    exported["operation_counts"][
        "lazy_consistency_materialized_record_count"
    ] = 2
    exported["pending_consistency_ledger_count"] = 0
    exported["materialization_reasons"] = {
        "public_evidence_snapshot": 2,
    }
    assert matrix_runner._replay_prefix_summary_diagnostics_match(
        exported,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=True,
        require_workload=True,
        require_materialized=True,
    )

    invalid_append = copy.deepcopy(exported)
    invalid_append["materialization_reasons"][
        "checkpoint_suffix_appended"
    ] = 1
    assert not matrix_runner._replay_prefix_summary_diagnostics_match(
        invalid_append,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=True,
        require_workload=True,
        require_materialized=True,
    )


def test_replay_prefix_summary_manifest_binds_contract_and_d6_evaluator(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(REPLAY_PREFIX_SUMMARY_MATRIX_PATH)
    commit = "b" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        REPLAY_PREFIX_SUMMARY_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-d1-replay-prefix-summary-multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_replay_prefix_summary_multiseed_evaluation.v1"
    )
    assert manifest[
        "replay_prefix_summary_execution_config_schema_version"
    ] == "d1.fixed_lag_replay_prefix_summary_execution_config.v1"
    assert manifest[
        "replay_prefix_summary_diagnostics_schema_version"
    ] == "d1.fixed_lag_replay_prefix_summary_diagnostics.v1"
    for case in manifest["cases"]:
        assert case["arms"]["reference"]["validation_kind"] == (
            "replay_prefix_summary"
        )
        assert case["arms"]["candidate"][
            "expected_d1_implementation_id"
        ].endswith("frozen_cumulative_summary_lazy_evidence_ranges.v1")


def test_publication_evidence_snapshot_matrix_freezes_safe_admission_contract(
) -> None:
    matrix = matrix_runner.load_matrix(
        PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_PATH
    )
    short = [case for case in matrix["cases"] if case["group"] == "short"]
    long = [case for case in matrix["cases"] if case["group"] == "long"]

    assert matrix["arm_implementations"] == {
        "reference": "full_consistency_snapshot_v1",
        "candidate": "required_observation_subset_v1",
    }
    assert matrix["run_flags"] == ["--integrated-stack"]
    assert [case["seed"] for case in short] == list(range(1151, 1161))
    assert [case["seed"] for case in long] == [1151, 1152, 1153]
    gates = matrix["admission_gates"]
    assert gates[
        "all_pairs_publication_evidence_snapshot_audit_valid"
    ] is True
    assert gates[
        "all_pairs_consistency_evidence_records_digest_equal"
    ] is True
    assert gates["all_pairs_existing_operation_counts_equal"] is True
    assert gates[
        "minimum_candidate_returned_record_reduction_pct"
    ] == 50.0
    boundary = matrix["evidence_boundary"]
    assert boundary["candidate_default_off"] is True
    assert boundary["same_release_cycle_required_ids"] is True
    assert boundary["published_payload_semantics_changed"] is False
    assert boundary["consistency_evidence_semantics_changed"] is False
    assert boundary["replay_prefix_implementation"] == (
        "per_checkpoint_prefix_rebuild_v1"
    )


def test_publication_evidence_snapshot_commands_isolate_only_selector(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(
        PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_PATH
    )
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    selector_index = reference.index(
        "--d1-publication-evidence-snapshot-implementation"
    )
    output_index = reference.index("--output")
    assert reference[selector_index + 1] == (
        "full_consistency_snapshot_v1"
    )
    assert candidate[selector_index + 1] == (
        "required_observation_subset_v1"
    )
    assert "--d1-replay-prefix-summary-implementation" not in reference
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {selector_index + 1, output_index + 1}:
            assert left == right


def test_publication_evidence_snapshot_manifest_binds_d6_contract(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(
        PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_PATH
    )
    commit = "c" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        PUBLICATION_EVIDENCE_SNAPSHOT_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-d1-publication-evidence-snapshot-"
        "multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_publication_evidence_snapshot_multiseed_evaluation.v1"
    )
    assert manifest[
        "publication_evidence_snapshot_execution_config_schema_version"
    ] == (
        "scalable3d-d1-publication-evidence-snapshot-execution-config-v1"
    )
    assert manifest[
        "publication_evidence_snapshot_diagnostics_schema_version"
    ] == (
        "scalable3d-d1-publication-evidence-snapshot-diagnostics-v1"
    )
    for case in manifest["cases"]:
        assert case["arms"]["reference"]["validation_kind"] == (
            "publication_evidence_snapshot"
        )
        assert case["arms"]["reference"][
            "expected_d1_implementation_id"
        ].endswith("full_consistency_snapshot.v1")
        assert case["arms"]["candidate"][
            "expected_d1_implementation_id"
        ].endswith("required_observation_subset.v1")


@pytest.mark.parametrize(
    ("selector", "implementation_id", "candidate"),
    [
        (
            "full_consistency_snapshot_v1",
            "main.d1_publication_evidence.full_consistency_snapshot.v1",
            False,
        ),
        (
            "required_observation_subset_v1",
            "main.d1_publication_evidence.required_observation_subset.v1",
            True,
        ),
    ],
)
def test_publication_evidence_snapshot_diagnostics_accept_valid_workload(
    selector: str,
    implementation_id: str,
    candidate: bool,
) -> None:
    execution_config = {
        "schema_version": (
            "scalable3d-d1-publication-evidence-snapshot-"
            "execution-config-v1"
        ),
        "selector": selector,
        "implementation_id": implementation_id,
        "candidate_enabled": candidate,
        "required_id_sources": [
            "source_observations",
            "materialized_track_latest_observation",
        ],
        "required_id_order": "deduplicated_lexicographic",
        "invalid_or_unknown_id_policy": "fallback_to_full_snapshot",
        "episode_final_export_scope": "full_exact_materialized_records",
        "truth_dependent_inputs_allowed": False,
    }
    counts = {
        "selection_count": 2,
        "reference_selection_count": 0 if candidate else 2,
        "candidate_selection_count": 2 if candidate else 0,
        "candidate_subset_success_count": 2 if candidate else 0,
        "candidate_fallback_count": 0,
        "adapter_snapshot_call_count": 2,
        "full_snapshot_call_count": 0 if candidate else 2,
        "subset_snapshot_call_count": 2 if candidate else 0,
        "publication_count": 4,
        "source_observation_reference_count": 5 if candidate else 0,
        "track_latest_observation_reference_count": 7 if candidate else 0,
        "required_observation_id_count": 8 if candidate else 0,
        "duplicate_reference_count": 4 if candidate else 0,
        "invalid_required_id_count": 0,
        "empty_required_id_selection_count": 0,
        "returned_record_count": 8 if candidate else 20,
        "lookup_miss_count": 0,
    }
    diagnostics = {
        "schema_version": (
            "scalable3d-d1-publication-evidence-snapshot-diagnostics-v1"
        ),
        "execution_config": execution_config,
        "operation_counts": counts,
        "fallback_reason_counts": {},
        "conservation": {
            "selection_partition": True,
            "candidate_selection_partition": True,
            "adapter_call_partition": True,
            "reference_deduplication_partition": True,
            "fallback_not_above_candidate_selection": True,
            "all_required_records_available": True,
        },
    }

    assert matrix_runner._publication_evidence_snapshot_diagnostics_match(
        diagnostics,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=candidate,
        require_workload=True,
    )

    invalid = copy.deepcopy(diagnostics)
    invalid["operation_counts"]["lookup_miss_count"] = 1
    assert not matrix_runner._publication_evidence_snapshot_diagnostics_match(
        invalid,
        expected_implementation=selector,
        expected_implementation_id=implementation_id,
        candidate=candidate,
        require_workload=True,
    )


def test_arm_commands_differ_only_by_explicit_implementation_and_output(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--d1-publication-metadata-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "per_track_copy_v1"
    assert candidate[implementation_index + 1] == "immutable_shared_v1"
    assert reference[output_index + 1] != candidate[output_index + 1]
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_v2_arm_commands_bind_only_the_v2_candidate_treatment(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(V2_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--d1-publication-metadata-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "per_track_copy_v1"
    assert candidate[implementation_index + 1] == "immutable_shared_v2"
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_cv_motion_model_commands_bind_only_the_cache_treatment(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(CV_MOTION_MODEL_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--d1-cv-motion-model-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "per_prediction_build_v1"
    assert candidate[implementation_index + 1] == "bounded_exact_lru_v1"
    capacity_index = reference.index(
        "--d1-cv-motion-model-cache-capacity"
    )
    assert reference[capacity_index + 1] == "128"
    assert candidate[capacity_index + 1] == "128"
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_opaque_source_identity_commands_bind_only_cache_treatment(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(OPAQUE_SOURCE_IDENTITY_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--d1-opaque-source-identity-implementation"
    )
    capacity_index = reference.index(
        "--d1-opaque-source-identity-cache-capacity"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == (
        "per_publication_build_v1"
    )
    assert candidate[implementation_index + 1] == (
        "bounded_generation_lru_v1"
    )
    assert reference[capacity_index + 1] == "1024"
    assert candidate[capacity_index + 1] == "1024"
    assert "--d1-publish-opaque-source-key" in reference
    assert "--d1-d2-structural-ambiguity-hold" not in reference
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_online_batch_frame_commands_bind_only_registered_treatment(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(ONLINE_BATCH_FRAME_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--d1-online-batch-frame-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "convert_then_frame_v1"
    assert candidate[implementation_index + 1] == (
        "closed_immutable_batch_to_frame_v1"
    )
    assert "--d1-d2-structural-ambiguity-hold" not in reference
    assert "--d1-publish-opaque-source-key" not in reference
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_truth_guard_commands_bind_only_registered_treatment(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(ONLINE_TRUTH_GUARD_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--online-truth-guard-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "generic_recursive_v1"
    assert (
        candidate[implementation_index + 1]
        == "builtin_specialized_recursive_v2"
    )
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_structured_jacobian_commands_bind_only_registered_treatment(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(STRUCTURED_JACOBIAN_MATRIX_PATH)
    case = matrix["cases"][0]
    reference = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "reference",
        tmp_path / "reference",
    )
    candidate = matrix_runner.build_episode_command(
        ROOT,
        matrix,
        case,
        "candidate",
        tmp_path / "candidate",
    )

    implementation_index = reference.index(
        "--d1-structured-numerical-jacobian-implementation"
    )
    output_index = reference.index("--output")
    assert reference[implementation_index + 1] == "dense_output_probe_v1"
    assert (
        candidate[implementation_index + 1]
        == "known_dimension_structural_columns_v1"
    )
    for index, (left, right) in enumerate(
        zip(reference, candidate, strict=True)
    ):
        if index not in {implementation_index + 1, output_index + 1}:
            assert left == right


def test_manifest_binds_both_arms_to_one_commit_and_d6_contract(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    commit = "a" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["source_commit"] == commit
    assert manifest["source_repository_dirty"] is False
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_publication_metadata_multiseed_evaluation.v1"
    )
    assert len(manifest["cases"]) == 13
    for case in manifest["cases"]:
        assert {
            arm["expected_commit"] for arm in case["arms"].values()
        } == {commit}
        assert case["arms"]["reference"][
            "expected_implementation"
        ] == "per_track_copy_v1"
        assert case["arms"]["candidate"][
            "expected_implementation"
        ] == "immutable_shared_v1"
        assert case["arms"]["reference"][
            "expected_d1_implementation_id"
        ].endswith("per_track_audit_copy.v1")
        assert case["arms"]["candidate"][
            "expected_d1_implementation_id"
        ].endswith("immutable_shared_audit.v1")


def test_v2_manifest_binds_audit_contract_and_v2_d6_evaluator(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(V2_MATRIX_PATH)
    commit = "d" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        V2_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-d1-publication-metadata-v2-multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_publication_metadata_v2_multiseed_evaluation.v1"
    )
    assert manifest["publication_audit_contract_version"] == (
        "d1.publication_audit_tree.v2"
    )
    for case in manifest["cases"]:
        assert {
            arm["expected_commit"] for arm in case["arms"].values()
        } == {commit}
        assert case["arms"]["candidate"][
            "expected_d1_implementation_id"
        ].endswith("immutable_shared_audit.v2")


def test_cv_motion_model_manifest_binds_cache_contract_and_d6_evaluator(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(CV_MOTION_MODEL_MATRIX_PATH)
    commit = "f" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        CV_MOTION_MODEL_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-d1-cv-motion-model-cache-multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_cv_motion_model_cache_multiseed_evaluation.v1"
    )
    assert manifest["cv_motion_model_cache_capacity"] == 128
    assert manifest[
        "cv_motion_model_cache_diagnostics_schema_version"
    ] == "d1.cv_motion_model_cache_diagnostics.v1"
    for case in manifest["cases"]:
        assert case["arms"]["reference"]["validation_kind"] == (
            "cv_motion_model_cache"
        )
        assert case["arms"]["reference"][
            "expected_d1_implementation_id"
        ].endswith("per_prediction_build.v1")
        assert case["arms"]["candidate"][
            "expected_d1_implementation_id"
        ].endswith("bounded_exact_lru.v1")


def test_opaque_source_identity_manifest_binds_cache_and_d6_contract(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(OPAQUE_SOURCE_IDENTITY_MATRIX_PATH)
    commit = "1" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        OPAQUE_SOURCE_IDENTITY_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-d1-opaque-source-identity-cache-multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_opaque_source_identity_cache_multiseed_evaluation.v1"
    )
    assert manifest["opaque_source_identity_cache_capacity"] == 1_024
    assert manifest[
        "opaque_source_identity_cache_diagnostics_schema_version"
    ] == "d1.opaque_source_identity_cache_diagnostics.v1"
    for case in manifest["cases"]:
        reference = case["arms"]["reference"]
        candidate = case["arms"]["candidate"]
        assert reference["validation_kind"] == (
            "opaque_source_identity_cache"
        )
        assert reference["expected_d1_implementation_id"].endswith(
            "per_publication_build.v1"
        )
        assert candidate["expected_d1_implementation_id"].endswith(
            "bounded_generation_lru.v1"
        )


def test_truth_guard_manifest_binds_diagnostics_and_d6_evaluator(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(ONLINE_TRUTH_GUARD_MATRIX_PATH)
    commit = "2" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        ONLINE_TRUTH_GUARD_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-online-truth-guard-multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.online_truth_guard_multiseed_evaluation.v1"
    )
    assert manifest["truth_guard_diagnostics_schema_version"] == (
        "scalable3d-online-truth-guard-diagnostics-v1"
    )
    for case in manifest["cases"]:
        reference = case["arms"]["reference"]
        candidate = case["arms"]["candidate"]
        assert reference["validation_kind"] == "online_truth_guard"
        assert reference["expected_truth_guard_implementation"] == (
            "generic_recursive_v1"
        )
        assert candidate["expected_truth_guard_implementation"] == (
            "builtin_specialized_recursive_v2"
        )
        assert "expected_d1_implementation_id" not in reference


def test_structured_jacobian_manifest_binds_diagnostics_and_d6_evaluator(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(STRUCTURED_JACOBIAN_MATRIX_PATH)
    commit = "4" * 40
    manifest = matrix_runner.planned_evidence_manifest(
        STRUCTURED_JACOBIAN_MATRIX_PATH,
        matrix,
        ROOT,
        commit,
        tmp_path / "evidence",
    )

    assert manifest["schema_version"] == (
        "scalable3d-d1-structured-jacobian-multiseed-evidence-v1"
    )
    assert manifest["required_d6_evaluator_schema_version"] == (
        "d6.d1_structured_jacobian_multiseed_evaluation.v1"
    )
    assert manifest["structured_jacobian_diagnostics_schema_version"] == (
        "d1.structured_numerical_jacobian_diagnostics.v1"
    )
    for case in manifest["cases"]:
        reference = case["arms"]["reference"]
        candidate = case["arms"]["candidate"]
        assert reference["validation_kind"] == (
            "structured_numerical_jacobian"
        )
        assert reference["expected_d1_implementation_id"].endswith(
            "dense_output_probe.v1"
        )
        assert candidate["expected_d1_implementation_id"].endswith(
            "known_dimension_structural_columns.v1"
        )


def test_matrix_rejects_arm_override_in_common_flags(tmp_path: Path) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    invalid = copy.deepcopy(matrix)
    invalid["run_flags"].append("--d1-publication-metadata-implementation")
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")

    with pytest.raises(ValueError, match="must not override"):
        matrix_runner.load_matrix(path)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("cache_key_policy", "rounded_dt", "exact cache key"),
        ("cache_capacity", 256, "cache_capacity=128"),
        ("matrix_values_are_read_only", False, "read-only matrices"),
    ],
)
def test_cv_motion_model_matrix_rejects_weakened_cache_boundary(
    tmp_path: Path,
    field: str,
    value: object,
    match: str,
) -> None:
    matrix = matrix_runner.load_matrix(CV_MOTION_MODEL_MATRIX_PATH)
    matrix["evidence_boundary"][field] = value
    path = tmp_path / "invalid_cv_cache.json"
    path.write_text(json.dumps(matrix), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        matrix_runner.load_matrix(path)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("cache_key_policy", "track_id", "freeze the cache key"),
        ("cache_capacity", 128, "cache_capacity=1024"),
        ("source_only_publication", False, "source-only publication"),
        ("structural_ambiguity_hold_enabled", True, "hold disabled"),
    ],
)
def test_opaque_source_identity_matrix_rejects_weakened_boundary(
    tmp_path: Path,
    field: str,
    value: object,
    match: str,
) -> None:
    matrix = matrix_runner.load_matrix(OPAQUE_SOURCE_IDENTITY_MATRIX_PATH)
    matrix["evidence_boundary"][field] = value
    path = tmp_path / "invalid_opaque_source_cache.json"
    path.write_text(json.dumps(matrix), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        matrix_runner.load_matrix(path)


def test_structured_jacobian_matrix_rejects_weakened_diagnostics_boundary(
    tmp_path: Path,
) -> None:
    matrix = matrix_runner.load_matrix(STRUCTURED_JACOBIAN_MATRIX_PATH)
    matrix["evidence_boundary"][
        "structured_jacobian_diagnostics_schema_version"
    ] = "d1.structured_numerical_jacobian_diagnostics.v0"
    path = tmp_path / "invalid_structured_jacobian.json"
    path.write_text(json.dumps(matrix), encoding="utf-8")

    with pytest.raises(ValueError, match="bind diagnostics schema v1"):
        matrix_runner.load_matrix(path)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (
            "candidate_publication_audit_contract_version",
            "d1.publication_audit_tree.v1",
            "bind the publication audit contract",
        ),
        (
            "d2_content_audit_required_before_identity_reuse",
            False,
            "content audit before identity reuse",
        ),
    ],
)
def test_v2_matrix_rejects_weakened_audit_boundary(
    tmp_path: Path,
    field: str,
    value: object,
    match: str,
) -> None:
    matrix = matrix_runner.load_matrix(V2_MATRIX_PATH)
    matrix["evidence_boundary"][field] = value
    path = tmp_path / "invalid_v2.json"
    path.write_text(json.dumps(matrix), encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        matrix_runner.load_matrix(path)


def test_episode_resume_requires_actual_implementation_identity(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode"
    episode.mkdir()
    commit = "b" * 40
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "d1_publication_metadata_implementation": "immutable_shared_v1",
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "d1_publication_metadata_implementation": "immutable_shared_v1",
        "d1_publication_metadata_diagnostics": {
            "implementation_id": (
                "d1.publication_metadata.immutable_shared_audit.v1"
            ),
            "immutable_shared_publication_metadata": True,
            "operation_counts": {
                "global_track_metadata_materialization_count": 400,
                "shared_audit_value_reuse_count": 1200,
            },
        },
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    assert matrix_runner._episode_matches(
        episode,
        expected_commit=commit,
        expected_implementation="immutable_shared_v1",
        seed=1101,
        duration_s=2.2,
        target_count=200,
        resource_count=200,
        recon_count=2,
    )
    summary["d1_publication_metadata_diagnostics"][
        "implementation_id"
    ] = "d1.publication_metadata.per_track_audit_copy.v1"
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(
        episode,
        expected_commit=commit,
        expected_implementation="immutable_shared_v1",
        seed=1101,
        duration_s=2.2,
        target_count=200,
        resource_count=200,
        recon_count=2,
    )


def _valid_v2_d2_audit(*, candidate: bool) -> dict[str, object]:
    latest = {
        "metadata_count": 200,
        "shared_subtree_full_audit_count": 3,
        "shared_subtree_builtin_equivalent_reuse_count": (
            0 if candidate else 597
        ),
        "immutable_v2_contract_validation_count": 3 if candidate else 0,
        "immutable_v2_full_content_audit_count": 3 if candidate else 0,
        "immutable_v2_identity_reuse_count": 597 if candidate else 0,
        "immutable_v2_contract_rejection_count": 0,
    }
    return {
        "schema_version": "scalable3d-d2-publication-metadata-audit-v1",
        "batch_count": 2,
        "latest": latest,
        "totals": {
            key: value * 2 for key, value in latest.items()
        },
    }


def test_v2_d2_audit_accepts_reference_and_candidate_modes() -> None:
    assert matrix_runner._v2_d2_audit_matches(
        {"d2_publication_metadata_audit": _valid_v2_d2_audit(candidate=False)},
        candidate=False,
    )
    assert matrix_runner._v2_d2_audit_matches(
        {"d2_publication_metadata_audit": _valid_v2_d2_audit(candidate=True)},
        candidate=True,
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("batch_count",), 0),
        (("latest", "metadata_count"), True),
        (("totals", "immutable_v2_contract_rejection_count"), 1),
        (("totals", "immutable_v2_identity_reuse_count"), 0),
        (("totals", "immutable_v2_full_content_audit_count"), 2),
    ],
)
def test_v2_d2_candidate_audit_rejects_tampering(
    path: tuple[str, ...],
    value: object,
) -> None:
    audit = _valid_v2_d2_audit(candidate=True)
    target: dict[str, object] = audit
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value

    assert not matrix_runner._v2_d2_audit_matches(
        {"d2_publication_metadata_audit": audit},
        candidate=True,
    )


def test_v2_episode_resume_requires_contract_and_d2_audit(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode_v2"
    episode.mkdir()
    commit = "e" * 40
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "d1_publication_metadata_implementation": "immutable_shared_v2",
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "d1_publication_metadata_implementation": "immutable_shared_v2",
        "d1_publication_metadata_diagnostics": {
            "implementation_id": (
                "d1.publication_metadata.immutable_shared_audit.v2"
            ),
            "publication_audit_contract_version": (
                "d1.publication_audit_tree.v2"
            ),
            "immutable_shared_publication_metadata": True,
            "operation_counts": {
                "global_track_metadata_materialization_count": 400,
                "per_track_shared_audit_mapping_copy_count": 0,
                "shared_audit_value_reuse_count": 1200,
            },
        },
        "d2_publication_metadata_audit": _valid_v2_d2_audit(candidate=True),
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    match_args = {
        "expected_commit": commit,
        "expected_implementation": "immutable_shared_v2",
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "require_v2_audit": True,
    }
    assert matrix_runner._episode_matches(episode, **match_args)

    summary["d2_publication_metadata_audit"]["totals"][
        "immutable_v2_contract_rejection_count"
    ] = 1
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(episode, **match_args)


def test_cv_motion_model_episode_resume_requires_four_surface_audit(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode_cv_cache"
    episode.mkdir()
    commit = "1" * 40
    implementation = "bounded_exact_lru_v1"
    implementation_id = "d1.fusion.cv_motion_model.bounded_exact_lru.v1"
    diagnostics = {
        "schema_version": "d1.cv_motion_model_cache_diagnostics.v1",
        "implementation_id": implementation_id,
        "candidate_enabled": True,
        "cache_capacity": 128,
        "cache_entry_count": 8,
        "operation_counts": {
            "prediction_request_count": 110,
            "nonpositive_dt_reference_bypass_count": 10,
            "cache_hit_count": 92,
            "cache_miss_count": 8,
            "model_build_count": 8,
            "peak_entry_count": 8,
        },
    }
    initial_diagnostics = {
        **diagnostics,
        "cache_entry_count": 0,
        "operation_counts": {},
    }
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "d1_cv_motion_model_implementation": implementation,
            "d1_cv_motion_model_cache_diagnostics": initial_diagnostics,
            "configuration": {
                "d1_cv_motion_model_implementation": implementation,
                "d1_cv_motion_model_cache_capacity": 128,
            },
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "d1_cv_motion_model_implementation": implementation,
        "d1_cv_motion_model_cache_diagnostics": diagnostics,
        "module_final_diagnostics": {
            "d1_cv_motion_model_implementation": implementation,
            "d1_cv_motion_model_cache_diagnostics": diagnostics,
        },
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    governance = {
        "d1_cv_motion_model_implementation": implementation,
        "d1_cv_motion_model_cache_diagnostics": diagnostics,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    match_args = {
        "expected_commit": commit,
        "expected_implementation": implementation,
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "validation_kind": "cv_motion_model_cache",
        "expected_cache_capacity": 128,
    }
    assert matrix_runner._episode_matches(episode, **match_args)

    summary["d1_cv_motion_model_cache_diagnostics"]["operation_counts"][
        "cache_hit_count"
    ] = 91
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(episode, **match_args)


def test_opaque_source_identity_episode_resume_requires_four_surface_audit(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode_opaque_source_identity_cache"
    episode.mkdir()
    commit = "6" * 40
    implementation = "bounded_generation_lru_v1"
    implementation_id = (
        "d1.publication.opaque_source_identity.bounded_generation_lru.v1"
    )
    conservation = {
        "request_equals_hit_plus_miss_plus_bypass": True,
        "build_equals_miss_plus_bypass": True,
        "eviction_not_above_miss": True,
        "entry_count_within_capacity": True,
        "peak_entry_count_within_capacity": True,
    }
    diagnostics = {
        "schema_version": (
            "d1.opaque_source_identity_cache_diagnostics.v1"
        ),
        "implementation_id": implementation_id,
        "candidate_enabled": True,
        "cache_capacity": 1_024,
        "cache_entry_count": 200,
        "cache_generation": ["D1_FUSION", "main-stack-reset-00000001-v1"],
        "operation_counts": {
            "request_count": 11_200,
            "cache_hit_count": 11_000,
            "cache_miss_count": 200,
            "identity_build_count": 200,
            "cache_eviction_count": 0,
            "reference_bypass_count": 0,
            "peak_entry_count": 200,
            "generation_invalidation_count": 0,
            "generation_invalidated_entry_count": 0,
            "explicit_reset_count": 0,
            "explicit_reset_entry_count": 0,
        },
        "conservation": conservation,
    }
    initial_diagnostics = {
        **diagnostics,
        "cache_entry_count": 0,
        "cache_generation": None,
        "operation_counts": {},
    }
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "d1_opaque_source_identity_implementation": implementation,
            "d1_opaque_source_identity_cache_diagnostics": (
                initial_diagnostics
            ),
            "configuration": {
                "d1_opaque_source_identity_implementation": implementation,
                "d1_opaque_source_identity_cache_capacity": 1_024,
                "d1_publish_opaque_source_key": True,
                "d1_d2_structural_ambiguity_hold_enabled": False,
            },
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "d1_opaque_source_identity_implementation": implementation,
        "d1_opaque_source_identity_cache_diagnostics": diagnostics,
        "module_final_diagnostics": {
            "d1_opaque_source_identity_implementation": implementation,
            "d1_opaque_source_identity_cache_diagnostics": diagnostics,
        },
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    governance = {
        "d1_opaque_source_identity_implementation": implementation,
        "d1_opaque_source_identity_cache_diagnostics": diagnostics,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    match_args = {
        "expected_commit": commit,
        "expected_implementation": implementation,
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "validation_kind": "opaque_source_identity_cache",
        "expected_cache_capacity": 1_024,
    }
    assert matrix_runner._episode_matches(episode, **match_args)

    summary[
        "d1_opaque_source_identity_cache_diagnostics"
    ]["operation_counts"]["cache_hit_count"] = 10_999
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(episode, **match_args)


@pytest.mark.parametrize(
    ("implementation", "implementation_id", "candidate"),
    (
        (
            "convert_then_frame_v1",
            "d1.online_batch_frame.convert_then_frame.v1",
            False,
        ),
        (
            "closed_immutable_batch_to_frame_v1",
            "d1.online_batch_frame."
            "closed_immutable_batch_final_frame_validation.v1",
            True,
        ),
    ),
)
def test_online_batch_frame_episode_resume_requires_four_surface_audit(
    tmp_path: Path,
    implementation: str,
    implementation_id: str,
    candidate: bool,
) -> None:
    episode = tmp_path / f"episode_online_batch_frame_{candidate}"
    episode.mkdir()
    commit = "7" * 40
    request_count = 10
    output_count = 20
    execution_config = {
        "schema_version": "d1.online_batch_frame_handoff_diagnostics.v1",
        "implementation": implementation,
        "implementation_id": implementation_id,
        "candidate_default_enabled": False,
        "public_validation_bypass_available": False,
        "raw_source_absolute_immutability_claimed": False,
        "candidate_contract": (
            "full_raw_batch_identity_check_then_structural_eligibility_"
            "check_then_deep_snapshot_then_full_readonly_frame_check"
        ),
    }
    counts = {
        "request_count": request_count,
        "successful_build_count": request_count,
        "rejected_build_count": 0,
        "reference_request_count": 0 if candidate else request_count,
        "candidate_request_count": request_count if candidate else 0,
        "reference_path_execution_count": 0 if candidate else request_count,
        "candidate_closed_handoff_count": request_count if candidate else 0,
        "candidate_reference_fallback_count": 0,
        "candidate_raw_rejection_count": 0,
        "candidate_resource_rejection_count": 0,
        "snapshot_structure_check_count": request_count if candidate else 0,
        "snapshot_structure_eligible_count": request_count if candidate else 0,
        "snapshot_structure_ineligible_count": 0,
        "snapshot_structure_error_count": 0,
        "closed_payload_snapshot_attempt_count": (
            request_count if candidate else 0
        ),
        "closed_payload_snapshot_success_count": (
            request_count if candidate else 0
        ),
        "closed_payload_snapshot_failure_count": 0,
        "raw_batch_identity_check_count": request_count,
        "raw_measurement_identity_check_count": (
            0 if candidate else output_count
        ),
        "converted_observation_collection_check_count": (
            0 if candidate else request_count
        ),
        "frame_final_identity_check_count": request_count,
        "measurement_conversion_count": output_count,
        "output_observation_count": output_count,
    }
    diagnostics = {
        **execution_config,
        "operation_counts": counts,
        "conservation": {
            "request_partition": True,
            "result_partition": True,
            "reference_path_partition": True,
            "candidate_path_partition": True,
            "snapshot_structure_check_partition": True,
            "closed_payload_snapshot_partition": True,
            "closed_handoff_uses_successful_snapshot": True,
            "raw_batch_check_accounting": True,
            "candidate_never_skips_final_frame_check": True,
        },
    }
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1121,
        "runtime_profile": {
            "d1_online_batch_frame_implementation": implementation,
            "d1_online_batch_frame_execution_config": execution_config,
            "configuration": {
                "d1_online_batch_frame_implementation": implementation,
            },
        },
    }
    config = {
        "seed": 1121,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    final = {
        "d1_online_batch_frame_implementation": implementation,
        "d1_online_batch_frame_execution_config": execution_config,
        "d1_online_batch_frame_diagnostics": diagnostics,
    }
    summary = {
        **final,
        "module_final_diagnostics": final,
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    governance = dict(final)
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    match_args = {
        "expected_commit": commit,
        "expected_implementation": implementation,
        "seed": 1121,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "validation_kind": "online_batch_frame_handoff",
    }
    assert matrix_runner._episode_matches(episode, **match_args)

    summary["d1_online_batch_frame_diagnostics"]["operation_counts"][
        "candidate_reference_fallback_count"
    ] = 1
    (episode / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    assert not matrix_runner._episode_matches(episode, **match_args)


def test_structured_jacobian_episode_resume_requires_four_surface_audit(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode_structured_jacobian"
    episode.mkdir()
    commit = "5" * 40
    selector = "known_dimension_structural_columns_v1"
    implementation_id = (
        "d1.ekf.numerical_jacobian."
        "known_dimension_structural_columns.v1"
    )
    diagnostics = {
        "schema_version": (
            "d1.structured_numerical_jacobian_diagnostics.v1"
        ),
        "implementation_id": implementation_id,
        "candidate_enabled": True,
        "operation_counts": {
            "jacobian_attempt_count": 100,
            "jacobian_success_count": 100,
            "structured_candidate_call_count": 100,
            "output_probe_elision_count": 100,
            "inactive_state_column_elision_count": 240,
            "measurement_function_evaluation_count": 720,
        },
        "conservation": {
            "attempt_equals_success_plus_failure": True,
            "attempt_equals_reference_plus_candidate": True,
        },
    }
    initial_diagnostics = {
        **diagnostics,
        "operation_counts": {},
    }
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "d1_structured_numerical_jacobian_implementation": selector,
            "d1_structured_numerical_jacobian_diagnostics": (
                initial_diagnostics
            ),
            "configuration": {
                "d1_structured_numerical_jacobian_implementation": selector,
            },
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "d1_structured_numerical_jacobian_implementation": selector,
        "d1_structured_numerical_jacobian_diagnostics": diagnostics,
        "module_final_diagnostics": {
            "d1_structured_numerical_jacobian_implementation": selector,
            "d1_structured_numerical_jacobian_diagnostics": diagnostics,
        },
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    governance = {
        "d1_structured_numerical_jacobian_implementation": selector,
        "d1_structured_numerical_jacobian_diagnostics": diagnostics,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
        ("observation_governance_audit.json", governance),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")

    match_args = {
        "expected_commit": commit,
        "expected_implementation": selector,
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "validation_kind": "structured_numerical_jacobian",
    }
    assert matrix_runner._episode_matches(episode, **match_args)

    summary[
        "d1_structured_numerical_jacobian_diagnostics"
    ]["operation_counts"]["measurement_function_evaluation_count"] = 1300
    (episode / "summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    assert not matrix_runner._episode_matches(episode, **match_args)


def test_truth_guard_episode_resume_requires_exact_message_audit(
    tmp_path: Path,
) -> None:
    episode = tmp_path / "episode_truth_guard"
    episode.mkdir()
    commit = "3" * 40
    implementation = "builtin_specialized_recursive_v2"
    manifest = {
        "git_commit": commit,
        "repository_dirty": False,
        "seed": 1101,
        "runtime_profile": {
            "online_truth_guard_implementation": implementation,
        },
    }
    config = {
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
    }
    summary = {
        "online_truth_guard_implementation": implementation,
        "online_truth_guard_diagnostics": {
            "schema_version": (
                "scalable3d-online-truth-guard-diagnostics-v1"
            ),
            "implementation": implementation,
            "candidate_enabled": True,
            "validation_count": 2,
        },
        "finite_state": True,
        "online_truth_use_count": 0,
        "simulated_duration_s": 2.2,
    }
    for name, payload in (
        ("manifest.json", manifest),
        ("scenario_config.json", config),
        ("summary.json", summary),
    ):
        (episode / name).write_text(json.dumps(payload), encoding="utf-8")
    (episode / "online_observations.jsonl").write_text(
        '{"sequence":1}\n{"sequence":2}\n',
        encoding="utf-8",
    )
    match_args = {
        "expected_commit": commit,
        "expected_implementation": implementation,
        "seed": 1101,
        "duration_s": 2.2,
        "target_count": 200,
        "resource_count": 200,
        "recon_count": 2,
        "validation_kind": "online_truth_guard",
    }

    assert matrix_runner._episode_matches(episode, **match_args)
    summary["online_truth_guard_diagnostics"]["validation_count"] = 1
    (episode / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )
    assert not matrix_runner._episode_matches(episode, **match_args)


def test_episode_cli_exposes_publication_metadata_selector() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.d1_publication_metadata_implementation
        == "immutable_shared_v2"
    )
    args = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--d1-publication-metadata-implementation",
            "per_track_copy_v1",
        ]
    )
    assert args.d1_publication_metadata_implementation == "per_track_copy_v1"


def test_episode_cli_exposes_default_off_truth_guard_candidate() -> None:
    episode_cli = importlib.import_module(
        "research_modules.scalable_3d_simulation.run_episode"
    )
    default_args = episode_cli.parse_args(["--integrated-stack"])
    assert (
        default_args.online_truth_guard_implementation
        == "generic_recursive_v1"
    )
    candidate = episode_cli.parse_args(
        [
            "--integrated-stack",
            "--online-truth-guard-implementation",
            "builtin_specialized_recursive_v2",
        ]
    )
    assert candidate.online_truth_guard_implementation == (
        "builtin_specialized_recursive_v2"
    )


def test_operator_interrupt_is_persisted_as_interrupted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = matrix_runner.load_matrix(MATRIX_PATH)
    matrix["cases"] = [matrix["cases"][0]]
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    monkeypatch.setattr(
        matrix_runner,
        "_validate_source_worktree",
        lambda worktree: "c" * 40,
    )

    def interrupt_arm(record: dict[str, object], worktree: Path) -> None:
        del record, worktree
        raise KeyboardInterrupt

    monkeypatch.setattr(matrix_runner, "_run_arm", interrupt_arm)
    output_root = tmp_path / "output"

    with pytest.raises(KeyboardInterrupt):
        matrix_runner.run_matrix(
            matrix_path,
            ROOT,
            output_root,
            resume=False,
            dry_run=False,
        )

    evidence = json.loads(
        (output_root / "evidence_manifest.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "interrupted"
    assert evidence["failure"] == {
        "case_id": "short_seed_1101",
        "arm": "reference",
        "error_type": "KeyboardInterrupt",
        "error": "matrix execution interrupted by operator",
    }
    assert evidence["cases"][0]["arms"]["reference"][
        "status"
    ] == "interrupted"
