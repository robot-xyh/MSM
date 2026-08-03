from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from d3_assignment_planner.a1_v3_data_contract import (
    A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH,
    A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS,
    canonical_json_sha256,
    validate_a1_v3_pre_generation_readiness,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_GENERATION_REQUEST_PATH = (
    MODULE_ROOT
    / "configs/"
    "a1_source_independent_v3_source_generation_request_readiness_v1.json"
)
GENERATOR_CONFIG_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generator_config_v1.json"
)
MAIN_REGISTRY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_main_allocation_registry_v1.json"
)
SCHEDULE_PATH = (
    MODULE_ROOT / "configs/a1_source_independent_v3_generation_schedule_v1.json"
)
SIDECAR_POLICY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_sidecar_classification_policy_v1.json"
)
RUNTIME_QUOTA_INVENTORY_PATH = (
    MODULE_ROOT
    / "configs/a1_source_independent_v3_runtime_quota_probe_inventory_v1.json"
)
GLOBAL_REGISTRY_PATH = (
    MODULE_ROOT.parent
    / "scalable_3d_simulation/configs/"
    "scalable_learning_global_seed_registry_v1.json"
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="ascii"))


def _write_artifact(path: Path, payload: dict, *, rehash: bool = True) -> None:
    if rehash:
        payload.pop("content_sha256", None)
        payload["content_sha256"] = canonical_json_sha256(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="ascii",
    )


def _validate(
    *,
    source_generation_request_path: Path = SOURCE_GENERATION_REQUEST_PATH,
    sidecar_classification_policy_path: Path = SIDECAR_POLICY_PATH,
):
    return validate_a1_v3_pre_generation_readiness(
        generator_config_path=GENERATOR_CONFIG_PATH,
        global_registry_path=GLOBAL_REGISTRY_PATH,
        registry_path=MAIN_REGISTRY_PATH,
        schedule_path=SCHEDULE_PATH,
        source_generation_request_path=source_generation_request_path,
        sidecar_classification_policy_path=sidecar_classification_policy_path,
    )


def test_exact_source_generation_request_is_ready_after_full_dirty_probe() -> None:
    report = _validate()
    assert report.status == "ready"
    assert report.ready is True
    assert report.reason_codes == ()
    assert report.source_generation_request_ready is True
    assert report.source_generation_request_path == (
        A1_V3_SOURCE_GENERATION_REQUEST_LOGICAL_PATH
    )
    assert report.source_generation_request_sha256 == sha256(
        SOURCE_GENERATION_REQUEST_PATH.read_bytes()
    ).hexdigest()
    assert report.source_generation_request_sha256 == (
        "b5685b61acff9f0f1bde504ecc27d17621e0161c8adad95d1789e4d46b74c42f"
    )

    payload = report.to_dict()
    stable_fields = (
        "source_generation_request_path",
        "source_generation_request_sha256",
        "source_generation_request_ready",
    )
    for field in stable_fields:
        assert payload["producer_capability"][field] == payload[field]
    assert payload["request_permissions"] == {
        name: name == "source_generation_request"
        for name in A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS
    }
    assert not any(payload["permissions"].values())
    assert payload["generation_authorized"] is False
    assert payload["validation_payload_read"] is False
    assert payload["formal_seed_payload_read"] is False
    assert payload["producer_capability"]["generation_authorized"] is False

    artifact = _json(SOURCE_GENERATION_REQUEST_PATH)
    assert artifact["status"] == "request_ready_frozen_runtime_quota_probe_passed"
    assert artifact["permissions"] == payload["request_permissions"]
    probe = artifact["producer_capability"]["frozen_runtime_quota_probe"]
    schedule = _json(SCHEDULE_PATH)["episodes"]
    expected_schedule = {item["episode_id"]: item for item in schedule}
    passing_ids = probe["passing_runtime_to_writer_recipe_ids"]
    runtime_results = probe["runtime_results"]
    assert probe["status"] == "exploratory_dirty_pass"
    assert probe["audited_cell_count"] == 15
    assert probe["audited_recipe_count"] == 300
    assert probe["episode_count"] == 300
    assert probe["pass_count"] == 300
    assert probe["failure_count"] == 0
    assert probe["probe_error_count"] == 0
    assert probe["repository_dirty"] is True
    assert probe["exploratory_only"] is True
    assert probe["readiness_eligible"] is False
    assert probe["formal_source_generation"] is False
    assert probe["dataset_finalized"] is False
    assert probe["training_started"] is False
    assert probe["runtime_authority_granted"] is False
    assert probe["control_authority_granted"] is False
    assert probe["required_per_episode"] == {
        "observable_frame_count": 9,
        "positive_frame_count": 3,
        "negative_frame_count": 3,
        "hard_negative_frame_count": 2,
    }
    assert probe["minimum_observed_per_episode"] == {
        "observable_frame_count": 9,
        "positive_frame_count": 3,
        "negative_frame_count": 3,
        "hard_negative_frame_count": 3,
    }
    assert probe["all_frozen_cells_quota_ready"] is True
    assert probe["online_truth_use_count"] == 0
    assert probe["global_track_id_created_count"] == 0
    assert probe["global_track_id_rewritten_count"] == 0
    assert probe["duplicate_frame_count"] == 0
    assert probe["forbidden_formal_seed_read_count"] == 0
    assert probe["r0_shard_10_19_read_count"] == 0
    assert probe["observed_frame_totals"] == {
        "observable_frame_count": 3086,
        "positive_frame_count": 1313,
        "negative_frame_count": 1773,
        "hard_negative_frame_count": 1771,
    }
    assert len(passing_ids) == len(set(passing_ids)) == 300
    assert set(passing_ids) == set(expected_schedule)
    assert len(runtime_results) == 300
    assert {item["episode_id"] for item in runtime_results} == set(
        expected_schedule
    )
    for result in runtime_results:
        expected = expected_schedule[result["episode_id"]]
        assert result["cell_id"] == expected["cell_id"]
        assert result["seed"] == expected["seed"]
        assert result["frame_count"] >= expected["minimum_observable_frames"]
        assert (
            result["positive_frame_count"]
            >= expected["minimum_positive_frames"]
        )
        assert (
            result["negative_frame_count"]
            >= expected["minimum_negative_frames"]
        )
        assert (
            result["hard_negative_frame_count"]
            >= expected["minimum_hard_negative_frames"]
        )
        assert result["quota_met"] is True
        assert result["writer_staged"] is True
        assert result["reason_codes"] == []
    assert probe["caller_classification_override_used"] is False
    assert probe["classifier_error_count"] == 0
    assert probe["blocker_codes"] == []
    assert probe["inventory_binding"]["file_sha256"] == (
        "fb89bfe57431647d1c7f82a6b7ae53ca995bec31e9d885bd0c2a8a6bfb111f55"
    )
    assert sha256(RUNTIME_QUOTA_INVENTORY_PATH.read_bytes()).hexdigest() == (
        probe["inventory_binding"]["file_sha256"]
    )
    assert probe["inventory_binding"]["evidence_content_sha256"] == (
        probe["evidence_artifacts"]["content_sha256"]
    )
    assert probe["evidence_artifacts"]["summary"]["sha256"] == (
        "53c2e8a417a926b018d0b491149c2c7f2bf7fd4f17f5fe8035e4b4450508e415"
    )
    assert probe["evidence_artifacts"]["episodes_jsonl"]["sha256"] == (
        "78da424c51a1b91d7ffcf288af9eeb4c887a8353cae8b125efcb7dbce7a66ad3"
    )
    assert probe["evidence_artifacts"]["checkpoint"]["sha256"] == (
        "ad2641e2b1258dbbd8869b46d9954fbe596434f624793dc5dbc6ae8d020975ee"
    )
    main_bindings = probe["source_bindings"]
    assert main_bindings["learning_source_recipes"]["sha256"] == (
        "34ced4f02c089b492b2ba58a94220fa319acd98ae65efa276c98fa7e4c8302d9"
    )
    assert main_bindings["episode_treatments"]["sha256"] == (
        "135a526ad9591c2fa3a0041d50335db1fcb75e1129e97df60c5739df66b4cf9c"
    )
    emitted = artifact["producer_capability"][
        "deterministically_emitted_action_change_types"
    ]
    assert "assignment_coverage_contraction" in emitted
    assert "assignment_coverage_recovery" in emitted
    policy = _json(SIDECAR_POLICY_PATH)
    assert policy["boundaries"][
        "assignment_coverage_change_requires_candidate_feasibility_delta"
    ] is True
    assert policy["boundaries"][
        "assignment_coverage_change_requires_candidate_teacher_direction_match"
    ] is True
    assert policy["boundaries"][
        "single_slot_coverage_transfer_requires_candidate_capacity_collapse"
    ] is True
    assert policy["boundaries"][
        "single_slot_coverage_transfer_requires_equal_teacher_coverage"
    ] is True
    assert policy["boundaries"][
        "single_slot_coverage_transfer_requires_one_resource_exchange"
    ] is True


def test_missing_request_or_classification_policy_fails_closed(
    tmp_path: Path,
) -> None:
    missing_request = _validate(
        source_generation_request_path=tmp_path / "missing-request.json"
    )
    assert missing_request.status == "fail_closed"
    assert missing_request.source_generation_request_ready is False
    assert missing_request.reason_codes == (
        "source_generation_request_read_failed",
    )
    assert not any(missing_request.to_dict()["request_permissions"].values())

    missing_policy = _validate(
        sidecar_classification_policy_path=tmp_path / "missing-policy.json"
    )
    assert missing_policy.status == "fail_closed"
    assert missing_policy.source_generation_request_ready is False
    assert missing_policy.reason_codes == (
        "sidecar_classification_policy_read_failed",
    )


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("content_hash", "source_generation_request_content_sha256_mismatch"),
        ("binding_hash", "source_generation_request_binding_mismatch"),
        ("schema", "source_generation_request_schema_contract_mismatch"),
        ("seed", "source_generation_request_seed_contract_mismatch"),
        ("allocation", "source_generation_request_seed_contract_mismatch"),
        ("taxonomy", "source_generation_request_producer_capability_mismatch"),
    ),
)
def test_request_hash_schema_seed_or_allocation_drift_fails_closed(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    payload = deepcopy(_json(SOURCE_GENERATION_REQUEST_PATH))
    rehash = True
    if mutation == "content_hash":
        payload["content_sha256"] = "0" * 64
        rehash = False
    elif mutation == "binding_hash":
        payload["bindings"]["frozen_request"]["file_sha256"] = "0" * 64
    elif mutation == "schema":
        payload["schema_contract"]["online_frame_schema_version"] = "wrong"
    elif mutation == "seed":
        payload["seed_contract"]["assigned_seed_minimum"] = 23001
    elif mutation == "allocation":
        payload["seed_contract"]["allocation_id"] = "wrong-allocation"
    elif mutation == "taxonomy":
        payload["producer_capability"][
            "deterministically_emitted_action_change_types"
        ].remove("assignment_coverage_recovery")
    path = tmp_path / f"{mutation}.json"
    _write_artifact(path, payload, rehash=rehash)

    report = _validate(source_generation_request_path=path)
    assert report.status == "fail_closed"
    assert report.ready is False
    assert report.source_generation_request_ready is False
    assert report.reason_codes == (expected_reason,)
    assert not any(report.to_dict()["request_permissions"].values())


def test_ready_request_cannot_disable_request_permission(tmp_path: Path) -> None:
    payload = deepcopy(_json(SOURCE_GENERATION_REQUEST_PATH))
    payload["permissions"]["source_generation_request"] = False
    path = tmp_path / "request-disabled.json"
    _write_artifact(path, payload)

    report = _validate(source_generation_request_path=path)
    assert report.status == "fail_closed"
    assert report.source_generation_request_ready is False
    assert report.reason_codes == (
        "source_generation_request_permission_mismatch",
    )


@pytest.mark.parametrize(
    "permission_name",
    tuple(
        name
        for name in A1_V3_SOURCE_GENERATION_REQUEST_PERMISSION_FIELDS
        if name != "source_generation_request"
    ),
)
def test_any_generation_or_runtime_permission_escalation_fails_closed(
    tmp_path: Path,
    permission_name: str,
) -> None:
    payload = deepcopy(_json(SOURCE_GENERATION_REQUEST_PATH))
    payload["permissions"][permission_name] = True
    path = tmp_path / f"permission-{permission_name}.json"
    _write_artifact(path, payload)

    report = _validate(source_generation_request_path=path)
    assert report.status == "fail_closed"
    assert report.source_generation_request_ready is False
    assert report.reason_codes == (
        "source_generation_request_permission_mismatch",
    )
    assert not any(report.to_dict()["request_permissions"].values())
