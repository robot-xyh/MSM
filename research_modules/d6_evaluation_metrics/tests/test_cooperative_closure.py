from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from d6_evaluation_metrics.cooperative_closure import (
    COOPERATIVE_CLOSURE_SCHEMA_VERSION,
    CooperativeClosureInputs,
    CooperativeClosureReportGenerator,
    load_cooperative_rows,
)


REAL_40_CASE_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "p1_m5n2_cooperative_40case_20260713.json"
)


def _rows(seed_count: int = 10) -> list[dict[str, object]]:
    rows = []
    for seed in range(seed_count):
        for target_index in range(2):
            for primary_index in (1, 2):
                physical = not (seed == 9 and target_index == 0 and primary_index == 2)
                rows.append(
                    {
                        "case": "m5n2",
                        "seed": seed,
                        "profile": "baseline",
                        "resource_id": f"R{target_index * 2 + primary_index}",
                        "target_id": f"T{target_index + 1}",
                        "member_role": f"primary_{primary_index}",
                        "member_order": primary_index,
                        "plan_owner": "center",
                        "plan_version": 3,
                        "coalition_owner": "center",
                        "coalition_version": 2,
                        "coalition_epoch": 1,
                        "assigned": True,
                        "visible": True,
                        "associated": True,
                        "contract_allowed": True,
                        "control_allowed": True,
                        "mode_switched": True,
                        "physical_intercept": physical,
                        "closest_range_m": 3.0 if physical else 7.0,
                        "arrival_error_s": float(primary_index - 1),
                        "member_separation_m": 8.0,
                        "common_lock": True,
                        "first_failure_reason": None if physical else "timeout",
                        "global_track_id_rewrite_count": 0,
                        "online_truth_use_count": 0,
                    }
                )
        rows.append(
            {
                "case": "m5n2",
                "seed": seed,
                "profile": "baseline",
                "resource_id": "R5",
                "target_id": "T1",
                "member_role": "reserve",
                "assigned": True,
                "reserve_activated": False,
                "reserve_unauthorized": False,
                "global_track_id_rewrite_count": 0,
                "online_truth_use_count": 0,
            }
        )
    return rows


def test_report_has_independent_denominators_and_acceptance(tmp_path: Path) -> None:
    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        tmp_path,
        inputs=CooperativeClosureInputs(
            rows=_rows(),
            d4_communication={
                "cases": [
                    {
                        "case": "packet_loss",
                        "communication_fault": "packet_loss_30pct",
                        "communication_passed": True,
                        "fail_closed": True,
                    }
                ]
            },
        ),
    )

    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["schema_version"] == COOPERATIVE_CLOSURE_SCHEMA_VERSION
    assert aggregate["funnels"]["pair"]["physical_intercept"]["available"] == 40
    assert aggregate["funnels"]["target"]["physical_intercept"]["available"] == 20
    assert aggregate["funnels"]["coalition"]["physical_intercept"]["available"] == 20
    assert aggregate["funnels"]["pair"]["physical_intercept"]["passed"] == 39
    assert aggregate["funnels"]["target"]["physical_intercept"]["passed"] == 19
    assert aggregate["second_primary"]["failure_distribution"] == {"timeout": 1}
    assert aggregate["first_failure_distribution"] == {"timeout": 1}
    assert aggregate["common_lock"]["rate"] == 1.0
    assert aggregate["arrival_dispersion"]["mean_s"] == 1.0
    assert aggregate["closest_range"]["minimum_m"] == 3.0
    assert aggregate["provenance"]["coalition_epoch"] == [1]
    assert aggregate["communication_faults"]["by_fault"]["packet_loss_30pct"]["pass_rate"] == 1.0
    checks = aggregate["acceptance"]["checks"]
    assert checks["coalition_at_least_8_of_10"]["value"] is True
    assert checks["reserve_unauthorized_zero"]["value"] is True
    assert checks["global_track_id_rewrite_zero"]["value"] is True
    assert checks["online_truth_use_zero"]["value"] is True
    assert aggregate["acceptance"]["all_passed"] is True
    assert outputs["plot"].stat().st_size > 0
    assert "不参与分配或控制" in outputs["markdown"].read_text(encoding="utf-8")

    with outputs["per_seed_csv"].open(newline="", encoding="utf-8") as stream:
        per_seed = list(csv.DictReader(stream))
    assert len(per_seed) == 10
    assert per_seed[0]["resource_count"] == "5"
    assert per_seed[0]["target_count"] == "2"
    assert per_seed[0]["coalition_owners"] == '["center"]'


def test_missing_evidence_is_unavailable_not_zero(tmp_path: Path) -> None:
    rows = [
        {
            "case": "legacy",
            "seed": 1,
            "resource_id": "R1",
            "target_id": "T1",
            "member_role": "primary",
            "assigned": True,
        }
    ]
    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        tmp_path, inputs=CooperativeClosureInputs(rows=rows)
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["funnels"]["pair"]["visible"] == {
        "available": 0,
        "passed": None,
        "rate": None,
        "status": "unavailable",
        "unavailable": 1,
    }
    assert aggregate["common_lock"]["status"] == "unavailable"
    assert aggregate["arrival_dispersion"]["status"] == "unavailable"
    assert aggregate["communication_faults"]["status"] == "unavailable"
    assert aggregate["acceptance"]["all_passed"] is None
    coalition = aggregate["acceptance"]["checks"]["coalition_at_least_8_of_10"]
    assert coalition["passed_seed_count"] is None
    assert coalition["available_seed_count"] == 0
    assert coalition["unavailable_seed_count"] == 1
    assert coalition["by_profile"]["NA"]["passed_seed_count"] is None
    assert aggregate["acceptance"]["checks"]["online_truth_use_zero"]["count"] is None
    assert all(
        item["status"] == "unavailable"
        for item in aggregate["optional_evidence_manifest"].values()
    )


def test_acceptance_uses_declared_profile_without_hiding_other_profiles(
    tmp_path: Path,
) -> None:
    rows = _rows()
    candidate = []
    for item in _rows():
        copied = dict(item)
        copied["profile"] = "candidate"
        if copied.get("member_role") == "primary_2" and int(copied["seed"]) >= 6:
            copied["physical_intercept"] = False
            copied["first_failure_reason"] = "candidate_timeout"
        candidate.append(copied)
    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        tmp_path,
        inputs=CooperativeClosureInputs(
            rows={
                "pair_rows": rows + candidate,
                "best_candidate_profile": "candidate",
            }
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    coalition = aggregate["acceptance"]["checks"]["coalition_at_least_8_of_10"]
    assert coalition["by_profile"]["baseline"]["value"] is True
    assert coalition["by_profile"]["candidate"]["value"] is False
    assert coalition["selected_profile"] == "candidate"
    assert coalition["profile_selection_source"] == (
        "source_summary.best_candidate_profile"
    )
    assert coalition["value"] is False
    assert aggregate["acceptance"]["all_passed"] is False


def test_real_40_case_summary_aggregates_acceptance_by_profile(
    tmp_path: Path,
) -> None:
    source = json.loads(REAL_40_CASE_FIXTURE.read_text(encoding="utf-8"))
    assert source["case_count"] == 40
    assert len(source["cases"]) == 40
    assert len(source["aggregates"]) == 4

    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        tmp_path,
        inputs=CooperativeClosureInputs(rows=REAL_40_CASE_FIXTURE),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    check = aggregate["acceptance"]["checks"]["coalition_at_least_8_of_10"]

    assert aggregate["seed_group_count"] == 40
    assert aggregate["funnels"]["coalition"]["physical_intercept"] == {
        "available": 40,
        "passed": 8,
        "rate": 0.2,
        "status": "available",
        "unavailable": 0,
    }
    assert check["selected_profile"] == source["best_candidate_profile"]
    assert check["profile_selection_source"] == (
        "source_summary.best_candidate_profile"
    )
    assert check["status"] == "available"
    assert check["value"] is False
    assert check["passed_seed_count"] == 5
    assert check["failed_seed_count"] == 5
    assert check["available_seed_count"] == 10
    assert check["unavailable_seed_count"] == 0

    source_counts = {
        item["profile"]: item["coalition_completion_count"]
        for item in source["aggregates"]
    }
    assert {
        profile: item["passed_seed_count"]
        for profile, item in check["by_profile"].items()
    } == source_counts
    assert all(
        item["available_seed_count"] == 10
        for item in check["by_profile"].values()
    )

    with outputs["per_seed_csv"].open(newline="", encoding="utf-8") as stream:
        seed_rows = list(csv.DictReader(stream))
    assert len(seed_rows) == 40
    assert {
        profile: len({row["seed"] for row in seed_rows if row["profile"] == profile})
        for profile in source_counts
    } == {profile: 10 for profile in source_counts}


def test_optional_evidence_overlays_only_missing_fields(tmp_path: Path) -> None:
    base = [
        {
            "case": "case-a",
            "seed": 4,
            "profile": "candidate",
            "resource_id": "R1",
            "target_id": "T1",
            "member_role": "primary",
            "assigned": True,
            "visible": False,
        }
    ]
    d5 = {
        "rows": [
            {
                "case": "case-a",
                "seed": 4,
                "resource_id": "R1",
                "target_id": "T1",
                "visible": True,
                "associated": True,
                "global_track_id_rewrite_count": 0,
                "online_truth_use_count": 0,
            }
        ]
    }
    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        tmp_path,
        inputs=CooperativeClosureInputs(rows=base, d5_visibility=d5),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["funnels"]["pair"]["visible"]["passed"] == 0
    assert aggregate["funnels"]["pair"]["associated"]["passed"] == 1
    assert aggregate["optional_evidence_manifest"]["d5_visibility"]["status"] == "available"
    assert aggregate["optional_evidence_manifest"]["d5_visibility"]["matched_row_count"] == 1


def test_loader_supports_jsonl_csv_and_rejects_invalid_lines(tmp_path: Path) -> None:
    jsonl = tmp_path / "rows.jsonl"
    jsonl.write_text(
        json.dumps({"case": "a", "seed": 1, "assigned": True}) + "\n",
        encoding="utf-8",
    )
    assert load_cooperative_rows(jsonl)[0]["case"] == "a"

    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("case,seed,assigned\nb,2,true\n", encoding="utf-8")
    assert load_cooperative_rows(csv_path)[0]["seed"] == "2"

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a JSON object"):
        load_cooperative_rows(invalid)


def _real_d4_communication_report(monkeypatch):
    research_modules = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(
        str(research_modules / "d4_distributed_fallback")
    )
    from d4_distributed_fallback.communication_fault_replay import (
        CommunicationReplayConfig,
        run_p1_communication_fault_matrix,
    )

    return run_p1_communication_fault_matrix(
        CommunicationReplayConfig(
            member_ids=("R1", "R2"),
            secondary_node_ids=("S1",),
        ),
        seeds=(0,),
    )


def test_real_d4_dataclass_contract_uses_scenario_and_passed_aliases(
    tmp_path: Path, monkeypatch
) -> None:
    report = _real_d4_communication_report(monkeypatch)
    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        tmp_path,
        inputs=CooperativeClosureInputs(
            rows=_rows(seed_count=1),
            d4_communication=report,
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    communication = aggregate["communication_faults"]

    assert communication["status"] == "available"
    assert communication["case_count"] == 6
    for scenario_id in ("normal", "delay_0_5s"):
        scenario = communication["by_fault"][scenario_id]
        assert scenario["pass_available_count"] == 1
        assert scenario["passed_count"] == 1
        assert scenario["pass_rate"] == 1.0
        assert scenario["fail_closed_available_count"] == 1


def test_real_d4_to_dict_json_cases_contract_keeps_pass_and_fail_closed(
    tmp_path: Path, monkeypatch
) -> None:
    report = _real_d4_communication_report(monkeypatch)
    json_path = tmp_path / "d4_communication_fault_report.json"
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = tmp_path / "report"
    outputs = CooperativeClosureReportGenerator().write_report_bundle(
        output_dir,
        inputs=CooperativeClosureInputs(
            rows=_rows(seed_count=1),
            d4_communication=json_path,
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))
    communication = aggregate["communication_faults"]

    assert communication["by_fault"]["normal"]["pass_rate"] == 1.0
    delay = communication["by_fault"]["delay_0_5s"]
    assert delay["pass_available_count"] == 1
    assert delay["pass_rate"] == 1.0
    assert delay["fail_closed_available_count"] == 1
    assert delay["fail_closed_count"] in {0, 1}
