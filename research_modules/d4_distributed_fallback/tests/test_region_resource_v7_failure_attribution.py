from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d4_distributed_fallback.region_resource_v7_failure_attribution import (
    FAILURE_ATTRIBUTION_FILENAME,
    REGION_RESOURCE_V7_FAILURE_ATTRIBUTION_SCHEMA,
    REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA,
    REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA,
    RegionResourceV7FailureAttributionError,
    V8_DATA_REQUEST_FILENAME,
    V8_SEED_REGISTRY_FILENAME,
    _find_forbidden_identity_keys,
    _read_jsonl,
    _validate_paths,
    _validate_records,
    _verify_csv_transport,
    diagnose_v7_and_freeze_v8_development_request,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_ROOT = (
    MODULE_ROOT
    / "outputs/d4_v7_source_independent_external_evaluation_20260730"
)
CANDIDATE_ROOT = (
    MODULE_ROOT
    / "outputs/d4_v7_rule_node_residual_failclosed_final_20260730"
    / "region_resource_a2_rule_node_transfer_residual_shadow_v7"
)


@pytest.fixture(scope="module")
def frozen_result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    output = tmp_path_factory.mktemp("d4-v7-attribution") / "report"
    return diagnose_v7_and_freeze_v8_development_request(
        EVALUATION_ROOT,
        CANDIDATE_ROOT,
        output,
    )


def test_frozen_v7_failure_inventory_is_attributed_without_promotion(
    frozen_result: dict[str, object],
) -> None:
    attribution = frozen_result["failure_attribution"]
    assert isinstance(attribution, dict)
    assert attribution["schema"] == REGION_RESOURCE_V7_FAILURE_ATTRIBUTION_SCHEMA
    assert attribution["v7_history"]["evaluation_disposition"] == "failed_closed"
    assert attribution["by_split"]["validation"]["exact_positive_action_count"] == 0
    assert attribution["by_split"]["validation"]["exact_positive_action_denominator"] == 9
    assert attribution["by_split"]["test"]["exact_positive_action_count"] == 0
    assert attribution["by_split"]["test"]["exact_positive_action_denominator"] == 9
    assert attribution["by_split"]["train"]["projected_transfer_change_frame_count"] == 3
    assert attribution["wrong_edge_and_false_transfer"]["false_transfer_count"] == 3
    assert attribution["attribution_denominators"] == {
        "behavior_failure_frame_count": 45,
        "pipeline_stage_attribution_available_count": 45,
        "pipeline_stage_attribution_unavailable_count": 0,
        "feature_level_causal_attribution_available_count": 0,
        "feature_level_causal_attribution_unavailable_count": 45,
    }
    assert attribution["proximate_failure_attribution"] == {
        "positive_target_actor_activation_absent": 42,
        "negative_wrong_edge_survived_projection": 3,
        "unattributed_pipeline_stage_failure": 0,
    }
    assert attribution["supply_demand_gap"]["status"] == "unavailable"
    assert attribution["region_topology"]["full_adjacency_status"] == (
        "unavailable_not_exported"
    )
    assert not any(attribution["permissions"].values())


def test_reload_audit_binds_all_frozen_inputs_and_transports(
    frozen_result: dict[str, object],
) -> None:
    audit = frozen_result["reload_audit"]
    assert isinstance(audit, dict)
    assert audit["evaluation_tree_unchanged"] is True
    assert audit["candidate_tree_unchanged"] is True
    assert audit["artifact_file_match_count"] == 6
    assert audit["artifact_file_mismatch_count"] == 0
    assert audit["machine_json_content_hash_match_count"] == 8
    assert audit["machine_json_content_hash_mismatch_count"] == 0
    assert audit["jsonl_record_count"] == 128
    assert audit["csv_record_count"] == 128
    assert audit["csv_jsonl_exact_transport_match_count"] == 128
    assert audit["csv_jsonl_transport_mismatch_count"] == 0
    assert audit["formal_holdout_seed_read_count"] == 0
    assert audit["candidate_summary"]["external_evaluation_disposition"] == (
        "failed_closed"
    )
    assert not any(audit["permissions"].values())


def test_v8_registry_is_new_train_only_balanced_and_request_only(
    frozen_result: dict[str, object],
) -> None:
    registry = frozen_result["v8_seed_registry"]
    request = frozen_result["v8_data_request"]
    assert isinstance(registry, dict)
    assert isinstance(request, dict)
    assert registry["schema"] == REGION_RESOURCE_V8_SEED_REGISTRY_SCHEMA
    assert request["schema"] == REGION_RESOURCE_V8_DATA_REQUEST_SCHEMA
    assert registry["status"] == "request_only_no_data_generated"
    assert registry["requested_seed_range"] == [28100, 28423]
    assert registry["requested_seed_count"] == 324
    assert registry["requested_forbidden_overlap"] == []
    assert registry["validation_seed_allocation"] == []
    assert registry["test_seed_allocation"] == []
    assert registry["episode_generation_count"] == 0
    assert registry["sample_generation_count"] == 0
    assert registry["model_fit_count"] == 0
    schedule = registry["schedule"]
    assert len(schedule) == 324
    assert {item["split"] for item in schedule} == {"train"}
    class_counts = {
        name: sum(item["requested_target_class"] == name for item in schedule)
        for name in {
            "safe_forward_transfer",
            "safe_reverse_transfer",
            "hard_no_transfer_negative",
        }
    }
    assert class_counts == {
        "safe_forward_transfer": 108,
        "safe_reverse_transfer": 108,
        "hard_no_transfer_negative": 108,
    }
    assert {
        item["requested_transfer_resource_count"]
        for item in schedule
        if item["requested_target_class"] != "hard_no_transfer_negative"
    } == {1, 2, 3}
    assert {
        item["hard_negative_candidate_resource_count"]
        for item in schedule
        if item["requested_target_class"] == "hard_no_transfer_negative"
    } == {1, 2, 3}
    assert all(
        item["hard_negative_candidate_resource_count"] == 0
        for item in schedule
        if item["requested_target_class"] != "hard_no_transfer_negative"
    )
    assert all(
        item["requested_transfer_resource_count"] == 0
        for item in schedule
        if item["requested_target_class"] == "hard_no_transfer_negative"
    )
    assert registry["requested_positive_transfer_resource_counts"] == [1, 2, 3]
    assert registry["requested_hard_negative_candidate_resource_counts"] == [
        1,
        2,
        3,
    ]
    assert request["required_coverage"][
        "positive_transfer_resource_counts"
    ] == [1, 2, 3]
    assert request["required_coverage"][
        "hard_negative_candidate_resource_counts"
    ] == [1, 2, 3]
    assert request["status"] == "frozen_request_not_generated"
    assert request["data_generation_count"] == 0
    assert request["training_count"] == 0
    assert request["future_candidate_rules"][
        "current_v7_validation_test_tuning_allowed"
    ] is False
    assert request["future_candidate_rules"][
        "minimum_confidence_gate_may_be_lowered"
    ] is False
    assert not any(registry["permissions"].values())
    assert not any(request["permissions"].values())


def test_written_json_and_checksums_are_self_consistent(
    frozen_result: dict[str, object],
) -> None:
    output = Path(str(frozen_result["output_root"]))
    attribution = json.loads(
        (output / FAILURE_ATTRIBUTION_FILENAME).read_text(encoding="utf-8")
    )
    registry = json.loads(
        (output / V8_SEED_REGISTRY_FILENAME).read_text(encoding="utf-8")
    )
    request = json.loads(
        (output / V8_DATA_REQUEST_FILENAME).read_text(encoding="utf-8")
    )
    assert attribution == frozen_result["failure_attribution"]
    assert registry == frozen_result["v8_seed_registry"]
    assert request == frozen_result["v8_data_request"]
    checksum_lines = (output / "SHA256SUMS").read_text(
        encoding="ascii"
    ).splitlines()
    assert len(checksum_lines) == 6
    assert all(len(line.split("  ", maxsplit=1)[0]) == 64 for line in checksum_lines)


def test_csv_jsonl_transport_rejects_one_changed_cell(tmp_path: Path) -> None:
    records = (
        {
            "schema": "fixture",
            "flag": True,
            "value": 3,
            "payload": [{"a": 1}],
            "optional": None,
        },
    )
    path = tmp_path / "records.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["value", "schema", "payload", "optional", "flag"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "value": "4",
                "schema": "fixture",
                "payload": '[{"a": 1}]',
                "optional": "",
                "flag": "True",
            }
        )
    with pytest.raises(
        RegionResourceV7FailureAttributionError,
        match="csv_jsonl_transport_mismatch",
    ):
        _verify_csv_transport(path, records)


def test_truth_actor_or_object_identity_keys_are_rejected() -> None:
    assert _find_forbidden_identity_keys(
        {"nested": [{"truth_id": "T-1"}, {"actor_id": "A-1"}]}
    ) == {"truth_id", "actor_id"}


def test_formal_holdout_seed_is_rejected_before_attribution() -> None:
    records = list(_read_jsonl(EVALUATION_ROOT / "evaluation_records.jsonl"))
    records[0] = {**records[0], "seed": 1000}
    with pytest.raises(
        RegionResourceV7FailureAttributionError,
        match="formal_holdout_seed_read_forbidden",
    ):
        _validate_records(records)


def test_output_inside_frozen_input_is_rejected() -> None:
    with pytest.raises(
        RegionResourceV7FailureAttributionError,
        match="output_inside_frozen_input_forbidden",
    ):
        _validate_paths(
            EVALUATION_ROOT.resolve(),
            CANDIDATE_ROOT.resolve(),
            (EVALUATION_ROOT / "diagnostic").resolve(),
            replace_output=False,
        )
