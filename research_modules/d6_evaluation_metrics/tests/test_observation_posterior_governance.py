from __future__ import annotations

import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.observation_posterior_governance import (
    OBSERVATION_GOVERNANCE_RUNTIME_V1,
    OBSERVATION_GOVERNANCE_RUNTIME_V2,
    evaluate_posterior_governance,
    register_module_performance_evidence,
)
from d6_evaluation_metrics.scalable_3d_offline import (
    SCALABLE_3D_OFFLINE_EVALUATION_DATE,
    aggregate_scalable_3d_episodes,
    render_scalable_3d_offline_markdown,
)


def _summary(
    *,
    schema: str = OBSERVATION_GOVERNANCE_RUNTIME_V2,
    d1_generation: int = 3,
    d2_generation: int = 3,
    consumption_count: int = 2,
    merge_count: int = 1,
    finalize_skip_count: int = 0,
    pending: int | None = None,
) -> dict[str, object]:
    return {
        "module_final_diagnostics": {
            "observation_governance": {
                "schema_version": schema,
                "d1_posterior_generation": d1_generation,
                "d2_pending_d1_posterior_generation": pending,
                "d2_consumed_d1_posterior_generation": d2_generation,
                "d2_posterior_consumption_count": consumption_count,
                "d2_pre_tick_posterior_merge_count": merge_count,
                "d2_finalize_unchanged_posterior_skip_count": (
                    finalize_skip_count
                ),
            }
        }
    }


def _d1(generation: int, sequence: int) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": "modules.d1.fused_tracks",
        "payload": {
            "snapshot_kind": "full_posterior",
            "posterior_generation": generation,
        },
    }


def _d2(generation: int, sequence: int) -> dict[str, object]:
    return {
        "sequence": sequence,
        "topic": "modules.d2.associated_tracks",
        "payload": {"source_d1_posterior_generation": generation},
    }


def _d1_noop_tail(
    generation: int,
    sequence: int,
    *,
    accepted_observation_count: int = 0,
    position_north_m: float = 100.0,
    covariance_scale: float = 1.0,
    timestamp: float = 1.0,
    track_ids: tuple[str, ...] = ("global_track_001",),
) -> dict[str, object]:
    record = _d1(generation, sequence)
    record["payload"].update(
        tracks=[
            {
                "global_track_id": global_track_id,
                "state_ned": [
                    position_north_m,
                    0.0,
                    -10.0,
                    1.0,
                    0.0,
                    0.0,
                ],
                "covariance": [
                    [
                        covariance_scale if row == column else 0.0
                        for column in range(6)
                    ]
                    for row in range(6)
                ],
                "timestamp": timestamp,
                "track_state": "stable",
            }
            for global_track_id in track_ids
        ],
        summary={
            "accepted_observation_count": accepted_observation_count,
            "updated_observation_count": accepted_observation_count,
            "created_track_count": 0,
        },
        structural_ambiguity_evidence_count=0,
    )
    return record


def _normal_records() -> list[dict[str, object]]:
    return [_d1(1, 1), _d2(1, 2), _d1(2, 3), _d1(3, 4), _d2(3, 5)]


def _reasons(evidence: object) -> list[str]:
    return list(evidence.metrics["observation_governance_generation_integrity_reasons_json"])


def test_normal_v2_posterior_generations_are_verified() -> None:
    evidence = evaluate_posterior_governance(_normal_records(), _summary())

    assert evidence.metrics["observation_governance_generation_integrity"] is True
    assert evidence.metrics["observation_governance_generation_contract_status"] == "verified"
    assert evidence.metrics["d1_posterior_generation"] == 3
    assert evidence.metrics["d1_full_posterior_publication_count"] == 3
    assert evidence.metrics["d2_consumed_d1_posterior_generation"] == 3
    assert evidence.metrics["d2_posterior_consumption_count"] == 2
    assert evidence.metrics["d2_association_publication_count"] == 2
    assert evidence.metrics["d2_pre_tick_posterior_merge_count"] == 1
    assert (
        evidence.metrics["d2_finalize_unchanged_posterior_skip_count"]
        == 0
    )
    assert evidence.metrics["d2_pending_generation_empty"] is True
    assert evidence.failure_reasons == ()


def test_repeated_d2_consumption_fails_closed() -> None:
    records = [_d1(1, 1), _d2(1, 2), _d2(1, 3)]
    evidence = evaluate_posterior_governance(
        records,
        _summary(d1_generation=1, d2_generation=1, consumption_count=2, merge_count=0),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert any("not_strictly_increasing" in reason for reason in _reasons(evidence))
    assert evidence.failure_reasons


def test_unknown_d1_generation_reference_fails_closed() -> None:
    records = [_d1(1, 1), _d2(2, 2)]
    evidence = evaluate_posterior_governance(
        records,
        _summary(d1_generation=1, d2_generation=2, consumption_count=1, merge_count=0),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert "d2_source_generation_not_previously_published:2" in _reasons(evidence)
    assert any("exceeds_d1" in reason for reason in _reasons(evidence))


def test_non_monotonic_d2_generation_fails_closed() -> None:
    records = [_d1(1, 1), _d1(2, 2), _d2(2, 3), _d2(1, 4)]
    evidence = evaluate_posterior_governance(
        records,
        _summary(d1_generation=2, d2_generation=1, consumption_count=2, merge_count=0),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert any("not_strictly_increasing" in reason for reason in _reasons(evidence))


def test_pending_generation_must_be_drained() -> None:
    evidence = evaluate_posterior_governance(
        _normal_records(),
        _summary(pending=3),
    )

    assert evidence.metrics["d2_pending_generation_empty"] is False
    assert "pending_generation_not_drained" in _reasons(evidence)
    assert evidence.metrics["observation_governance_generation_contract_status"] == "failed_closed"


def test_pending_empty_requires_consumed_generation_to_equal_d1() -> None:
    records = [_d1(1, 1), _d2(1, 2), _d1(2, 3)]
    evidence = evaluate_posterior_governance(
        records,
        _summary(
            d1_generation=2,
            d2_generation=1,
            consumption_count=1,
            merge_count=1,
            pending=None,
        ),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert any(
        reason.startswith(
            "d2_final_consumed_generation_not_equal_d1_when_pending_empty:"
        )
        for reason in _reasons(evidence)
    )


def test_consumption_plus_pre_tick_merge_must_equal_d1_generation() -> None:
    records = [_d1(1, 1), _d1(2, 2), _d2(2, 3)]
    evidence = evaluate_posterior_governance(
        records,
        _summary(
            d1_generation=2,
            d2_generation=2,
            consumption_count=1,
            merge_count=0,
            pending=None,
        ),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert any(
        reason.startswith(
            "d2_consumption_plus_pre_tick_merge_plus_verified_finalize_skip_"
            "not_equal_d1:"
        )
        for reason in _reasons(evidence)
    )


def test_equal_public_posterior_without_complete_signature_fails_closed() -> None:
    records = [
        _d1_noop_tail(1, 1),
        _d2(1, 2),
        _d1_noop_tail(2, 3),
        _d1_noop_tail(3, 4),
    ]
    evidence = evaluate_posterior_governance(
        records,
        _summary(
            d1_generation=3,
            d2_generation=1,
            consumption_count=1,
            merge_count=1,
            finalize_skip_count=1,
        ),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert evidence.metrics["observation_governance_generation_contract_status"] == (
        "failed_closed"
    )
    assert (
        "d2_finalize_unchanged_skip_complete_input_equivalence_unproven:"
        "versioned_complete_d2_input_digest_missing"
        in _reasons(evidence)
    )
    assert evidence.failure_reasons


def test_finalize_skip_with_new_tail_evidence_fails_closed() -> None:
    records = [
        _d1_noop_tail(1, 1),
        _d2(1, 2),
        _d1_noop_tail(2, 3, accepted_observation_count=1),
    ]
    evidence = evaluate_posterior_governance(
        records,
        _summary(
            d1_generation=2,
            d2_generation=1,
            consumption_count=1,
            merge_count=0,
            finalize_skip_count=1,
        ),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert any(
        reason.startswith("d2_finalize_unchanged_skip_tail_has_new_evidence:")
        for reason in _reasons(evidence)
    )


def test_finalize_skip_with_changed_track_set_fails_closed() -> None:
    records = [
        _d1_noop_tail(1, 1),
        _d2(1, 2),
        _d1_noop_tail(2, 3, track_ids=("global_track_002",)),
    ]
    evidence = evaluate_posterior_governance(
        records,
        _summary(
            d1_generation=2,
            d2_generation=1,
            consumption_count=1,
            merge_count=0,
            finalize_skip_count=1,
        ),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert (
        "d2_finalize_unchanged_skip_tail_track_set_changed:generation=2"
        in _reasons(evidence)
    )


def test_finalize_skip_with_changed_state_covariance_or_time_fails_closed() -> None:
    records = [
        _d1_noop_tail(1, 1),
        _d2(1, 2),
        _d1_noop_tail(
            2,
            3,
            position_north_m=100.25,
            covariance_scale=1.5,
            timestamp=1.2,
        ),
    ]
    evidence = evaluate_posterior_governance(
        records,
        _summary(
            d1_generation=2,
            d2_generation=1,
            consumption_count=1,
            merge_count=0,
            finalize_skip_count=1,
        ),
    )

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    reason = next(
        reason
        for reason in _reasons(evidence)
        if reason.startswith(
            "d2_finalize_unchanged_skip_full_posterior_not_equivalent:"
        )
    )
    assert "max_state_abs_delta=0.25" in reason
    assert "max_covariance_abs_delta=0.5" in reason
    assert "max_timestamp_delta_s=0.2" in reason
    assert any(
        item.startswith(
            "d2_final_consumed_generation_not_equal_d1_when_pending_empty:"
        )
        for item in _reasons(evidence)
    )
    assert any(
        item.startswith(
            "d2_consumption_plus_pre_tick_merge_plus_verified_finalize_skip_"
            "not_equal_d1:"
        )
        for item in _reasons(evidence)
    )


def test_missing_finalize_skip_count_fails_closed() -> None:
    summary = _summary()
    del summary["module_final_diagnostics"]["observation_governance"][
        "d2_finalize_unchanged_posterior_skip_count"
    ]

    evidence = evaluate_posterior_governance(_normal_records(), summary)

    assert evidence.metrics["observation_governance_generation_integrity"] is False
    assert (
        "invalid_summary_count:d2_finalize_unchanged_posterior_skip_count"
        in _reasons(evidence)
    )


def test_runtime_v1_generation_evidence_is_unavailable_not_zero() -> None:
    evidence = evaluate_posterior_governance(
        [],
        _summary(schema=OBSERVATION_GOVERNANCE_RUNTIME_V1),
    )

    assert evidence.metrics["observation_governance_runtime_schema"] == OBSERVATION_GOVERNANCE_RUNTIME_V1
    assert evidence.metrics["observation_governance_generation_integrity"] is None
    assert evidence.metrics["observation_governance_generation_integrity_availability"] == "unavailable"
    assert evidence.metrics["d1_posterior_generation"] is None
    assert evidence.metrics["d2_posterior_consumption_count"] is None
    assert evidence.failure_reasons == ()


def test_module_performance_registry_is_descriptive_only(tmp_path: Path) -> None:
    d1_path = tmp_path / "d1.json"
    d5_path = tmp_path / "d5.json"
    d1_path.write_text(json.dumps({"schema_version": "d1.performance.v1"}))
    d5_path.write_text(json.dumps({"schema_version": "d5-performance-v1"}))

    registry = register_module_performance_evidence((d1_path, d5_path))

    assert registry["evidence_count"] == 2
    assert {record["module"] for record in registry["records"]} == {"D1", "D5"}
    assert all(record["full_stack_realtime_claim"] is False for record in registry["records"])
    assert all(record["control_effect_claim"] is False for record in registry["records"])


def test_chinese_report_renders_v2_audit_and_descriptive_boundary() -> None:
    evidence = evaluate_posterior_governance(_normal_records(), _summary())
    row = {
        "scenario_name": "nominal",
        "scenario_version": "v1",
        "target_count": 2,
        "resource_count": 2,
        "recon_count": 1,
        "camera_count": 3,
        "seed": 7,
        **evidence.metrics,
    }
    aggregate = aggregate_scalable_3d_episodes((row,), bootstrap_resamples=10)
    aggregate["module_performance_evidence"] = {
        "records": [
            {
                "module": "D1",
                "source_schema_version": "d1.performance.v1",
                "sha256": "a" * 64,
                "evidence_class": "descriptive_standalone_module_performance",
                "full_stack_realtime_claim": False,
            }
        ]
    }

    report = render_scalable_3d_offline_markdown(
        (row,),
        aggregate,
        title="后验代次评估",
        plot_name="timing.png",
    )

    assert "D1-D2 后验代次审计" in report
    assert SCALABLE_3D_OFFLINE_EVALUATION_DATE == "2026-07-31"
    assert "评估日期：2026-07-31" in report
    assert "v1 没有这些字段，结果保持 unavailable，不按 0 处理" in report
    assert "不等同于 D1-D7 全栈实时能力" in report


def test_non_d1_d5_performance_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"schema_version": "main-full-stack-v1"}))

    with pytest.raises(ValueError, match="only D1/D5"):
        register_module_performance_evidence((path,))
