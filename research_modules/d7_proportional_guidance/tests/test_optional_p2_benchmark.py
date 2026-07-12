from __future__ import annotations

from dataclasses import asdict

import pytest

from d7_proportional_guidance import (
    DEFAULT_OPTIONAL_P2_LAWS,
    P2_OPTIONAL_BENCHMARK_BOUNDARY,
    OptionalP2GuidanceLaw,
    generate_optional_p2_target_replay,
    run_optional_p2_benchmark_suite,
    run_optional_p2_point_mass_benchmark,
    run_optional_p2_replay_benchmark,
    select_runtime_guidance_law,
    summarize_optional_p2_benchmark,
)


def test_optional_p2_suite_reports_all_laws_for_fixed_seeds() -> None:
    results = run_optional_p2_benchmark_suite(seeds=(7, 17))
    summary = summarize_optional_p2_benchmark(results)

    assert len(results) == 8
    assert {row.guidance_law for row in results} == {
        law.value for law in DEFAULT_OPTIONAL_P2_LAWS
    }
    assert all(row.hit for row in results)
    assert all(row.min_miss_distance_m >= 0.0 for row in results)
    assert all(row.control_effort_mps > 0.0 for row in results)
    assert all(row.compute_time_s >= 0.0 for row in results)
    assert summary["boundary"] == P2_OPTIONAL_BENCHMARK_BOUNDARY
    assert summary["row_count"] == 8
    assert summary["seed_count"] == 2
    assert summary["guidance_law_count"] == 4
    assert summary["benchmark_only"] is True
    assert summary["default_runtime_path_replaced"] is False
    assert summary["png_guidance_delivery_modified"] is False
    assert summary["d3_d4_d5_gate_bypassed"] is False


def test_optional_p2_fixed_seed_metrics_are_deterministic() -> None:
    first = run_optional_p2_point_mass_benchmark(
        guidance_law=OptionalP2GuidanceLaw.TRUE_PN,
        seed=7,
    )
    second = run_optional_p2_point_mass_benchmark(
        guidance_law=OptionalP2GuidanceLaw.TRUE_PN,
        seed=7,
    )

    assert first.hit is True
    assert first.min_miss_distance_m == pytest.approx(4.655028, abs=1e-5)
    assert first.control_effort_mps == pytest.approx(46.048224, abs=1e-5)
    assert first.min_miss_distance_m == pytest.approx(second.min_miss_distance_m)
    assert first.control_effort_mps == pytest.approx(second.control_effort_mps)
    assert first.control_energy_m2ps3 == pytest.approx(second.control_energy_m2ps3)
    assert first.sample_count == second.sample_count


def test_frpn_result_is_explicitly_marked_as_research_approximation() -> None:
    result = run_optional_p2_point_mass_benchmark(
        guidance_law=OptionalP2GuidanceLaw.FRPN_APPROX,
        seed=17,
    )
    summary = summarize_optional_p2_benchmark((result,))

    assert result.guidance_law == "frpn_research_approximation"
    assert result.research_approximation is True
    assert "not a canonical" in result.approximation_note
    assert result.benchmark_only is True
    assert result.default_runtime_path_replaced is False
    assert summary["frpn_is_research_approximation"] is True
    assert summary["laws"][result.guidance_law]["research_approximation"] is True


def test_optional_p2_replay_accepts_serialized_samples() -> None:
    generated = generate_optional_p2_target_replay(seed=27)
    replay = [asdict(sample) for sample in generated]
    result = run_optional_p2_replay_benchmark(
        replay,
        guidance_law="apn",
        seed=27,
        source="fixed_seed_serialized_replay",
    )

    assert result.source == "fixed_seed_serialized_replay"
    assert result.hit is True
    assert result.min_miss_distance_m == pytest.approx(4.153398, abs=1e-5)
    assert result.metadata["target_truth_used_offline_only"] is True


@pytest.mark.parametrize("law", ["pn_3d", "true_pn", "apn", "frpn_research_approximation"])
def test_optional_p2_laws_are_not_registered_in_runtime_selector(law: str) -> None:
    with pytest.raises(ValueError, match="guidance law must be one of"):
        select_runtime_guidance_law(law)
