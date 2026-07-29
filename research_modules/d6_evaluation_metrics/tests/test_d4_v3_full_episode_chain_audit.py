from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from d6_evaluation_metrics.d4_v3_full_episode_chain_audit import (
    D4_V3_BOUNDED_COAST_BRIDGE_SOURCE_SCHEMA_VERSION,
    _load_bounded_coast_bridge_source,
    audit_d4_v3_full_episode_chain,
    evaluate_d4_v3_bounded_coast_bridge,
    write_d4_v3_full_episode_chain_audit,
)
from d6_evaluation_metrics.d4_v3_isolated_paired_audit import (
    D4V3IsolatedPairedAuditError,
)
from d6_evaluation_metrics.runtime_plan_outcome_join import (
    evaluate_runtime_plan_outcomes,
    load_runtime_plan_outcome_join_inputs,
)


ROOT = (
    Path(__file__).resolve().parents[3]
    / "research_modules/scalable_3d_simulation/outputs"
    / "d4_v3_isolated_final_v2b_seed_2007_full_20260729"
)
ANCHOR = "a061b2d69c98e07d506c28ce322761c5968417ac08ef607c1775a34f90c3d72c"


@pytest.fixture(scope="module")
def final_v2b_audit() -> dict:
    if not ROOT.is_dir():
        pytest.skip("final v2b full-chain evidence is not present")
    return audit_d4_v3_full_episode_chain(
        ROOT,
        expected_sha256sums_sha256=ANCHOR,
    )


@pytest.fixture(scope="module")
def bounded_coast_bridge_case() -> tuple[dict, dict]:
    if not ROOT.is_dir():
        pytest.skip("final v2b full-chain evidence is not present")
    report_root = ROOT / "seed_2007/treatment/d6_runtime_plan_outcomes"
    specification = report_root / "input_specification.json"
    expected_sha256 = hashlib.sha256(specification.read_bytes()).hexdigest()
    inputs = load_runtime_plan_outcome_join_inputs(
        specification,
        expected_sha256=expected_sha256,
    )
    join = evaluate_runtime_plan_outcomes(inputs)
    source = _load_bounded_coast_bridge_source(inputs, join=join)
    window = next(
        item
        for item in join["binding_windows"]
        if item["ack_bus_sequence"] == 271
        and item["global_track_id"] == "GT3D-000004"
    )
    assert window["state_window_available"] is False
    return window, source


def _evaluate_bridge_case(
    window: dict,
    source: dict,
    **overrides,
) -> dict:
    arguments = {
        "expected_plan_id": window["plan_id"],
        "expected_plan_version": window["plan_version"],
        "expected_ack_bus_sequence": window["ack_bus_sequence"],
    }
    arguments.update(overrides)
    return evaluate_d4_v3_bounded_coast_bridge(
        window,
        source=source,
        **arguments,
    )


def test_final_v2b_replays_successor_ack_guidance_and_refresh(
    final_v2b_audit: dict,
) -> None:
    result = final_v2b_audit
    chain = result["strict_chain"]
    applied = chain["applied_chain"]
    refresh = chain["same_identity_refresh"]

    assert result["integrity"]["passed"] is True
    assert result["source_provenance"]["implementation_file_count"] == 11
    assert chain["d4_regional_applied_chain_count"] == 1
    assert applied["d7_guidance_binding_count"] == 19
    assert applied["native_physical_state_window_count"] == 18
    assert applied["bounded_coast_bridged_window_count"] == 1
    assert applied["physical_state_window_count"] == 19
    assert applied["physical_state_window_coverage_complete"] is True
    assert applied["resource_target_action_identifiable"] is False
    bridge = applied["bounded_coast_bridge"]
    assert bridge["accepted_window_count"] == 1
    assert bridge["rejected_window_count"] == 0
    accepted = bridge["accepted"][0]
    assert accepted["global_track_id"] == "GT3D-000004"
    assert accepted["truth_target_id"] == "TGT-0004"
    assert accepted["bridged_frame_count"] == 1
    assert accepted["anchor_timestamps"] == [
        0.8334722201965242,
        1.2361487940887796,
    ]
    assert accepted["evaluation_only"] is True
    assert accepted["online_exposure_allowed"] is False
    assert accepted["global_track_id_rewrite_performed"] is False
    assert refresh["execution_signature_preserved"] is True
    assert refresh["authority_scope_preserved"] is True
    authority = result["authority_boundary"]
    for name in (
        "production_runtime_authority",
        "production_assignment_authority",
        "production_degradation_authority",
        "production_takeover_authority",
        "production_coalition_commit_authority",
        "production_control_authority",
        "model_promotion_authority",
    ):
        assert authority[name] is False
    assert authority["rule_fallback_required"] is True
    benefit = result["paired_outcome"]["positive_benefit"]
    assert benefit["availability"] == "unavailable"
    assert benefit["value"] is False


def test_final_v2b_runtime_replay_is_semantically_exact(
    final_v2b_audit: dict,
) -> None:
    for arm in ("control", "treatment"):
        replay = final_v2b_audit["runtime_replay"][arm]
        assert replay["independent_replay_passed"] is True
        assert replay["persisted_result_semantically_exact"] is True
        assert replay["source_sequence_and_payload_hash_verified"] is True
        assert replay["online_truth_use_count"] == 0
        assert replay["production_authority"] is False
        assert replay["admission_status"] == (
            "runtime_observed_diagnostic_only_admission_closed"
        )
        assert replay["rule_fallback_required"] is True


def test_bounded_coast_bridge_accepts_only_explicit_real_gap(
    bounded_coast_bridge_case: tuple[dict, dict],
) -> None:
    window, source = bounded_coast_bridge_case

    result = _evaluate_bridge_case(window, source)

    assert result["available"] is True
    assert result["bridged_frame_count"] == 1
    assert result["online_exposure_allowed"] is False
    assert result["production_runtime_authority"] is False


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("expected_plan_id", "tampered-plan"),
        ("expected_plan_version", 999),
        ("expected_ack_bus_sequence", 999),
    ],
)
def test_bounded_coast_bridge_rejects_runtime_chain_mismatch(
    bounded_coast_bridge_case: tuple[dict, dict],
    argument: str,
    value,
) -> None:
    window, source = bounded_coast_bridge_case

    result = _evaluate_bridge_case(
        window,
        source,
        **{argument: value},
    )

    assert result["available"] is False
    assert result["reason"] == "bounded_coast_runtime_chain_mismatch"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "window_interval",
            "open",
            "bounded_coast_window_interval_invalid",
        ),
        (
            "window_start_timestamp",
            "not-a-timestamp",
            "bounded_coast_window_timestamp_invalid",
        ),
    ],
)
def test_bounded_coast_bridge_rejects_invalid_window(
    bounded_coast_bridge_case: tuple[dict, dict],
    field: str,
    value,
    reason: str,
) -> None:
    window, source = bounded_coast_bridge_case
    tampered = copy.deepcopy(window)
    tampered[field] = value

    result = _evaluate_bridge_case(tampered, source)

    assert result["available"] is False
    assert result["reason"] == reason


def test_bounded_coast_bridge_rejects_non_gap_identity_reason(
    bounded_coast_bridge_case: tuple[dict, dict],
) -> None:
    window, source = bounded_coast_bridge_case
    tampered = copy.deepcopy(window)
    tampered["identity_mapping"]["reason"] = "d2_mapping_stale_at_window_start"

    result = _evaluate_bridge_case(tampered, source)

    assert result["available"] is False
    assert result["reason"] == "bounded_coast_not_an_identity_gap"


def test_bounded_coast_bridge_rejects_source_schema_mismatch(
    bounded_coast_bridge_case: tuple[dict, dict],
) -> None:
    window, source = bounded_coast_bridge_case
    tampered_source = dict(source)
    tampered_source["schema_version"] = (
        D4_V3_BOUNDED_COAST_BRIDGE_SOURCE_SCHEMA_VERSION + ".tampered"
    )

    result = _evaluate_bridge_case(window, tampered_source)

    assert result["available"] is False
    assert result["reason"] == "bounded_coast_source_schema_unsupported"


def test_wrong_external_anchor_is_rejected() -> None:
    if not ROOT.is_dir():
        pytest.skip("final v2b full-chain evidence is not present")
    with pytest.raises(D4V3IsolatedPairedAuditError) as captured:
        audit_d4_v3_full_episode_chain(
            ROOT,
            expected_sha256sums_sha256="0" * 64,
        )
    assert captured.value.code == "sha256sums_anchor_mismatch"


def test_full_chain_writer_is_atomic(
    final_v2b_audit: dict,
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit"
    paths = write_d4_v3_full_episode_chain_audit(
        output,
        final_v2b_audit,
    )
    assert all(path.is_file() for path in paths.values())
    with pytest.raises(FileExistsError):
        write_d4_v3_full_episode_chain_audit(
            output,
            final_v2b_audit,
        )
