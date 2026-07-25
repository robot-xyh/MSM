from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics import d1_online_batch_frame_multiseed as subject


ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = (
    ROOT
    / "research_modules"
    / "scalable_3d_simulation"
    / "configs"
    / "d1_online_batch_frame_multiseed_v1.json"
)


def test_frozen_matrix_contract_is_accepted() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

    subject._validate_matrix(matrix)

    assert subject._base._file_sha256(MATRIX_PATH) == (
        subject.D1_ONLINE_BATCH_FRAME_MATRIX_SHA256
    )
    assert len(matrix["cases"]) == 13


def test_matrix_threshold_tamper_fails_closed() -> None:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    matrix["admission_gates"][
        "minimum_candidate_closed_handoff_ratio_pct"
    ] = 98.0

    with pytest.raises(
        subject.D1OnlineBatchFrameEvidenceError,
        match="admission_gates",
    ):
        subject._validate_matrix(matrix)


def test_invalid_manifest_returns_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "evidence_manifest.json"
    path.write_text('{"schema_version":"wrong"}\n', encoding="utf-8")

    result = subject.evaluate_d1_online_batch_frame_multiseed(path)

    assert result["availability"]["available"] is False
    assert result["optimization_admitted"] is False
    assert result["system_realtime_gap_closed"] is False


@pytest.mark.parametrize("arm", ["reference", "candidate"])
def test_execution_config_binds_full_implementation_identity(arm: str) -> None:
    config = _execution_config(arm)

    subject._validate_execution_config(
        config,
        expected=subject._IMPLEMENTATIONS[arm],
        expected_id=subject._IMPLEMENTATION_IDS[arm],
        context=arm,
    )

    config["implementation_id"] = "d1.online_batch_frame.wrong.v1"
    with pytest.raises(
        subject.D1OnlineBatchFrameEvidenceError,
        match="execution config mismatch",
    ):
        subject._validate_execution_config(
            config,
            expected=subject._IMPLEMENTATIONS[arm],
            expected_id=subject._IMPLEMENTATION_IDS[arm],
            context=arm,
        )


@pytest.mark.parametrize("arm", ["reference", "candidate"])
def test_final_diagnostics_conservation_accepts_valid_arms(arm: str) -> None:
    diagnostics = _diagnostics(arm)

    normalized, audit = subject._validate_final_diagnostics(
        diagnostics, arm=arm, context=arm
    )

    assert audit["passed"] is True
    assert normalized["operation_counts"]["request_count"] == 4


def test_candidate_snapshot_partition_tamper_fails_closed() -> None:
    diagnostics = _diagnostics("candidate")
    diagnostics["operation_counts"]["closed_payload_snapshot_success_count"] = 3

    with pytest.raises(
        subject.D1OnlineBatchFrameEvidenceError,
        match="closed snapshot partition",
    ):
        subject._validate_final_diagnostics(
            diagnostics, arm="candidate", context="candidate"
        )


def test_reference_duplicate_check_tamper_fails_closed() -> None:
    diagnostics = _diagnostics("reference")
    diagnostics["operation_counts"]["raw_measurement_identity_check_count"] = 7

    with pytest.raises(
        subject.D1OnlineBatchFrameEvidenceError,
        match="duplicate measurement checks",
    ):
        subject._validate_final_diagnostics(
            diagnostics, arm="reference", context="reference"
        )


def test_pair_workload_recomputes_registered_audit_metrics() -> None:
    reference, _ = subject._validate_final_diagnostics(
        _diagnostics("reference"), arm="reference", context="reference"
    )
    candidate, _ = subject._validate_final_diagnostics(
        _diagnostics("candidate"), arm="candidate", context="candidate"
    )

    audit = subject._validate_pair_batch_frame_workload(
        reference, candidate, context="pair"
    )

    assert audit["candidate_duplicate_check_reduction_pct"] == 100.0
    assert audit["candidate_closed_handoff_ratio_pct"] == 100.0
    assert audit["candidate_reference_fallback_count"] == 0


def test_normalization_does_not_hide_assignment_business_difference() -> None:
    reference = _summary()
    candidate = copy.deepcopy(reference)
    candidate["module_final_diagnostics"]["d3_assignment_count"] = 199

    reference_hash = subject._base._canonical_sha256(
        subject._normalized_summary(reference)
    )
    candidate_hash = subject._base._canonical_sha256(
        subject._normalized_summary(candidate)
    )

    assert reference_hash != candidate_hash


def test_runtime_normalization_is_narrow() -> None:
    reference = _runtime_profile("reference")
    candidate = _runtime_profile("candidate")

    assert subject._normalized_runtime_profile(
        reference
    ) == subject._normalized_runtime_profile(candidate)

    candidate["configuration"]["d3_human_authorization_state"] = "denied"
    assert subject._normalized_runtime_profile(
        reference
    ) != subject._normalized_runtime_profile(candidate)


def _execution_config(arm: str) -> dict[str, object]:
    return {
        "schema_version": subject.D1_ONLINE_BATCH_FRAME_DIAGNOSTICS_SCHEMA_VERSION,
        "implementation": subject._IMPLEMENTATIONS[arm],
        "implementation_id": subject._IMPLEMENTATION_IDS[arm],
        "candidate_default_enabled": False,
        "candidate_contract": (
            "full_raw_batch_identity_check_then_structural_eligibility_"
            "check_then_deep_snapshot_then_full_readonly_frame_check"
        ),
        "public_validation_bypass_available": False,
        "raw_source_absolute_immutability_claimed": False,
    }


def _diagnostics(arm: str) -> dict[str, object]:
    operations = {
        name: 0 for name in subject._BATCH_FRAME_OPERATION_FIELDS
    }
    operations.update(
        {
            "request_count": 4,
            "successful_build_count": 4,
            "raw_batch_identity_check_count": 4,
            "measurement_conversion_count": 8,
            "frame_final_identity_check_count": 4,
            "output_observation_count": 8,
        }
    )
    if arm == "reference":
        operations.update(
            {
                "reference_request_count": 4,
                "reference_path_execution_count": 4,
                "raw_measurement_identity_check_count": 8,
                "converted_observation_collection_check_count": 4,
            }
        )
    else:
        operations.update(
            {
                "candidate_request_count": 4,
                "candidate_closed_handoff_count": 4,
                "snapshot_structure_check_count": 4,
                "snapshot_structure_eligible_count": 4,
                "closed_payload_snapshot_attempt_count": 4,
                "closed_payload_snapshot_success_count": 4,
            }
        )
    return {
        **_execution_config(arm),
        "conservation": {
            "candidate_never_skips_final_frame_check": True,
            "candidate_path_partition": True,
            "closed_handoff_uses_successful_snapshot": True,
            "closed_payload_snapshot_partition": True,
            "raw_batch_check_accounting": True,
            "reference_path_partition": True,
            "request_partition": True,
            "result_partition": True,
            "snapshot_structure_check_partition": True,
        },
        "operation_counts": operations,
    }


def _runtime_profile(arm: str) -> dict[str, object]:
    return {
        "schema_version": "scalable3d-integrated-stack-runtime-profile-v1",
        "d1_online_batch_frame_implementation": subject._IMPLEMENTATIONS[arm],
        "d1_online_batch_frame_execution_config": _execution_config(arm),
        "configuration": {
            "d1_online_batch_frame_implementation": (
                subject._IMPLEMENTATIONS[arm]
            ),
            "d3_human_authorization_state": "approved",
        },
    }


def _summary() -> dict[str, object]:
    final = {
        "d1_online_batch_frame_implementation": (
            subject.REFERENCE_IMPLEMENTATION
        ),
        "d1_online_batch_frame_execution_config": _execution_config(
            "reference"
        ),
        "d1_online_batch_frame_diagnostics": _diagnostics("reference"),
        "d3_assignment_count": 200,
        "stage_timings": {"value": 1.0},
    }
    nested = {
        "d1_online_batch_frame_implementation": (
            subject.REFERENCE_IMPLEMENTATION
        ),
        "d1_online_batch_frame_execution_config": _execution_config(
            "reference"
        ),
        "d1_online_batch_frame_diagnostics": _diagnostics("reference"),
    }
    final["observation_governance"] = nested
    return {
        "episode_id": "episode-reference",
        "wall_time_s": 10.0,
        "real_time_factor": 0.2,
        "d1_online_batch_frame_implementation": (
            subject.REFERENCE_IMPLEMENTATION
        ),
        "d1_online_batch_frame_execution_config": _execution_config(
            "reference"
        ),
        "d1_online_batch_frame_diagnostics": _diagnostics("reference"),
        "module_final_diagnostics": final,
    }
