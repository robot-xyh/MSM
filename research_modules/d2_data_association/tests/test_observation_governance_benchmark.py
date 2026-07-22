from __future__ import annotations

import pytest

from d2_data_association import (
    OBSERVATION_GOVERNANCE_BENCHMARK_SCHEMA_VERSION,
    ObservationClaimLedgerConfig,
    run_observation_governance_benchmark,
)


@pytest.mark.parametrize("target_count", [3, 12])
def test_offline_governance_benchmark_preserves_legal_close_targets(
    target_count: int,
) -> None:
    report = run_observation_governance_benchmark(
        target_count=target_count,
        frame_count=16,
        separation_m=0.75,
        observation_claim_config=ObservationClaimLedgerConfig(
            retention_seconds=1.0,
            max_count=target_count * 8,
            max_lateness_seconds=0.5,
        ),
    )
    payload = report.to_dict()

    assert payload["schema_version"] == (
        OBSERVATION_GOVERNANCE_BENCHMARK_SCHEMA_VERSION
    )
    assert payload["legitimate_false_suppression_count"] == 0
    assert payload["legitimate_false_suppression_rate"] == 0.0
    assert payload["nearby_independent_target_recall"] == 1.0
    assert payload["erroneous_coalescence_count"] == 0
    assert payload["confirmation_latency_mean_seconds"] == 0.25
    assert all(
        value == 0.25
        for value in payload["confirmation_latency_seconds_by_truth"].values()
    )
    assert payload["offline_identity_metrics"]["id_switch_count_available"] is True
    assert payload["offline_identity_metrics"]["id_switch_count"] == 0
    assert payload["online_truth_used"] is False
    assert payload["truth_scope"] == "offline_evaluator_only"
    assert payload["ledger_summary"]["peak_count"] <= target_count * 8
