from __future__ import annotations

import csv
import json

from d6_evaluation_metrics.dense_crossing_evaluation import (
    DENSE_CROSSING_EVALUATION_SCHEMA_VERSION,
    DenseCrossingEvaluationInputs,
    DenseCrossingEvaluationReportGenerator,
    load_dense_crossing_source,
)


def _row(
    seed: int,
    *,
    role: str,
    candidate_id: str,
    idsw: int,
    identity: float,
    coverage: float = 0.95,
    false_tracks: int = 10,
    latency: float = 0.02,
    implementation: str = "GNNHungarianAssociator",
    implementation_kind: str = "end_to_end_replay",
    selected: bool = False,
) -> dict:
    return {
        "seed": seed,
        "comparison_role": role,
        "candidate_id": candidate_id,
        "implementation": implementation,
        "implementation_kind": implementation_kind,
        "selected_candidate": selected,
        "scenario_id": "dense-crossing",
        "scenario_version": "v1",
        "target_count": 5,
        "truth_metrics_available": True,
        "continuity_available": True,
        "id_switch_count": idsw,
        "identity_continuity": identity,
        "coverage_continuity": coverage,
        "false_track_count": false_tracks,
        "rmse": 1.2,
        "nis": {"available": True, "mean": 1.9, "count": 50},
        "nees": {"available": True, "mean": 3.8, "count": 50},
        "mean_initialization_latency_s": 0.4,
        "p95_loop_latency_s": latency,
        "online_truth_leakage_count": 0,
    }


def _inputs() -> DenseCrossingEvaluationInputs:
    screening = {
        "schema_version": "d2-dense-crossing-screening/v1",
        "runs": [
            {
                "configuration": {
                    "comparison_role": "baseline",
                    "candidate_id": "gnn-baseline",
                    "implementation": "GNNHungarianAssociator",
                },
                "per_seed": [
                    _row(
                        seed,
                        role="baseline",
                        candidate_id="gnn-baseline",
                        idsw=10,
                        identity=0.70,
                    )
                    for seed in range(10)
                ],
            },
            {
                "configuration": {
                    "comparison_role": "candidate",
                    "candidate_id": "gnn-quality-gate",
                    "implementation": "GNNHungarianAssociator",
                    "selected_candidate": True,
                },
                "per_seed": [
                    _row(
                        seed,
                        role="candidate",
                        candidate_id="gnn-quality-gate",
                        idsw=6,
                        identity=0.82,
                        selected=True,
                    )
                    for seed in range(10)
                ],
            },
            {
                "configuration": {
                    "comparison_role": "candidate",
                    "candidate_id": "light-jpda",
                    "implementation": "d2_jpda_research_adapter",
                    "implementation_kind": "end_to_end_replay_research_adapter",
                },
                "per_seed": [
                    _row(
                        seed,
                        role="candidate",
                        candidate_id="light-jpda",
                        idsw=6,
                        identity=0.83,
                        implementation="d2_jpda_research_adapter",
                        implementation_kind="end_to_end_replay_research_adapter",
                    )
                    for seed in range(10)
                ],
            },
        ],
    }
    confirmation = {
        "schema_version": "d2-dense-crossing-confirmation/v1",
        "p95_loop_latency_budget_s": 0.03,
        "runs": [
            {
                "configuration": {
                    "comparison_role": "baseline",
                    "candidate_id": "gnn-baseline",
                    "implementation": "GNNHungarianAssociator",
                },
                "per_seed": [
                    _row(
                        seed,
                        role="baseline",
                        candidate_id="gnn-baseline",
                        idsw=10,
                        identity=0.70,
                    )
                    for seed in range(20)
                ],
            },
            {
                "configuration": {
                    "comparison_role": "candidate",
                    "candidate_id": "gnn-quality-gate",
                    "implementation": "GNNHungarianAssociator",
                },
                "per_seed": [
                    _row(
                        seed,
                        role="candidate",
                        candidate_id="gnn-quality-gate",
                        idsw=6,
                        identity=0.82,
                        false_tracks=11,
                    )
                    for seed in range(20)
                ],
            },
            {
                "configuration": {
                    "comparison_role": "candidate",
                    "candidate_id": "light-jpda",
                    "implementation": "d2_jpda_research_adapter",
                    "implementation_kind": "end_to_end_replay_research_adapter",
                },
                "per_seed": [
                    _row(
                        seed,
                        role="candidate",
                        candidate_id="light-jpda",
                        idsw=6,
                        identity=0.83,
                        false_tracks=8,
                        latency=0.04,
                        implementation="d2_jpda_research_adapter",
                        implementation_kind="end_to_end_replay_research_adapter",
                    )
                    for seed in range(20)
                ],
            },
        ],
    }
    return DenseCrossingEvaluationInputs(
        d1_governed_manifest={
            "schema_version": "d1.governed_replay_manifest.v1",
            "metadata": {"online_truth_policy": "stripped"},
        },
        d1_offline_truth_summary={
            "schema_version": "d1.long_replay_offline_truth.v1",
            "target_count": 5,
        },
        d2_screening=screening,
        d2_confirmation=confirmation,
    )


def test_dense_crossing_bundle_applies_strict_promotion_rules(tmp_path) -> None:
    paths = DenseCrossingEvaluationReportGenerator().write_report_bundle(
        tmp_path, inputs=_inputs()
    )

    assert set(paths) == {"per_seed_csv", "aggregate_json", "markdown", "plot"}
    assert all(path.exists() for path in paths.values())
    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))
    assert aggregate["schema_version"] == DENSE_CROSSING_EVALUATION_SCHEMA_VERSION
    assert aggregate["best_gnn_candidate_id"] == "gnn-quality-gate"
    assert aggregate["d1_truth_isolation"]["online_truth_leak_count"] == 0

    gnn, jpda = aggregate["recommendations"]
    assert gnn["status"] == "passed"
    assert gnn["promote"] is True
    assert gnn["checks"]["id_switch_reduction"]["value"] == 0.4
    assert gnn["checks"]["identity_continuity_gain"]["value"] >= 0.1
    assert gnn["checks"]["false_track_limit"]["passed"] is True
    assert jpda["status"] == "failed"
    assert jpda["promote"] is False
    assert jpda["checks"]["p95_loop_latency_budget"]["passed"] is False

    rows = list(csv.DictReader(paths["per_seed_csv"].open(encoding="utf-8")))
    assert len(rows) == 90
    assert {row["variant_class"] for row in rows} == {
        "gnn_baseline",
        "gnn_candidate",
        "lightweight_jpda",
    }
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "轻量研究近似" in markdown
    assert "20-seed confirmation" in markdown


def test_adapter_smoke_is_audited_but_never_promoted(tmp_path) -> None:
    inputs = _inputs()
    confirmation = dict(inputs.d2_confirmation)
    confirmation["runs"] = list(confirmation["runs"]) + [
        {
            "implementation": "stonesoup_detection_object_adapter",
            "implementation_kind": "object_adapter_smoke_only",
            "end_to_end_tracker_implemented": False,
            "results": [
                {
                    "implementation": "stonesoup_detection_object_adapter",
                    "implementation_kind": "object_adapter_smoke_only",
                    "end_to_end_tracker_implemented": False,
                    "executed": True,
                    "latency_seconds": 0.01,
                }
            ],
        }
    ]
    paths = DenseCrossingEvaluationReportGenerator().write_report_bundle(
        tmp_path,
        inputs=DenseCrossingEvaluationInputs(
            d1_governed_manifest=inputs.d1_governed_manifest,
            d1_offline_truth_summary=inputs.d1_offline_truth_summary,
            d2_screening=inputs.d2_screening,
            d2_confirmation=confirmation,
        ),
    )
    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))

    assert any(
        item["variant_class"] == "adapter_smoke"
        for item in aggregate["excluded_evidence"]
    )
    assert all(
        recommendation["candidate_variant_id"]
        != "adapter_smoke:confirmation"
        for recommendation in aggregate["recommendations"]
    )


def test_missing_confirmation_metrics_remain_unavailable(tmp_path) -> None:
    inputs = _inputs()
    confirmation = dict(inputs.d2_confirmation)
    candidate = dict(confirmation["runs"][1])
    candidate["per_seed"] = [
        {
            "seed": seed,
            "comparison_role": "candidate",
            "candidate_id": "gnn-quality-gate",
            "implementation": "GNNHungarianAssociator",
            "truth_metrics_available": False,
            "continuity_available": False,
        }
        for seed in range(8)
    ]
    confirmation["runs"] = [confirmation["runs"][0], candidate]
    paths = DenseCrossingEvaluationReportGenerator().write_report_bundle(
        tmp_path,
        inputs=DenseCrossingEvaluationInputs(
            d1_governed_manifest=inputs.d1_governed_manifest,
            d1_offline_truth_summary=inputs.d1_offline_truth_summary,
            d2_screening=inputs.d2_screening,
            d2_confirmation=confirmation,
            p95_loop_latency_budget_s=0.03,
        ),
    )
    aggregate = json.loads(paths["aggregate_json"].read_text(encoding="utf-8"))
    gnn = aggregate["recommendations"][0]

    assert gnn["status"] == "unavailable"
    assert gnn["promote"] is False
    assert gnn["checks"]["candidate_seed_count"]["status"] == "failed"
    assert gnn["checks"]["id_switch_reduction"]["status"] == "unavailable"
    rows = list(csv.DictReader(paths["per_seed_csv"].open(encoding="utf-8")))
    candidate_rows = [
        row
        for row in rows
        if row["phase"] == "confirmation"
        and row["variant_id"] == "gnn-quality-gate"
    ]
    assert all(row["id_switch_count"] == "" for row in candidate_rows)
    assert all(
        row["id_switch_count_availability"] == "unavailable"
        for row in candidate_rows
    )


def test_json_jsonl_and_csv_sources_are_supported(tmp_path) -> None:
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps({"rows": [{"seed": 1}]}), encoding="utf-8")
    jsonl_path = tmp_path / "input.jsonl"
    jsonl_path.write_text('{"seed": 2}\n', encoding="utf-8")
    csv_path = tmp_path / "input.csv"
    csv_path.write_text("seed\n3\n", encoding="utf-8")

    assert load_dense_crossing_source(json_path)["rows"][0]["seed"] == 1
    assert load_dense_crossing_source(jsonl_path)["rows"][0]["seed"] == 2
    assert load_dense_crossing_source(csv_path)["rows"][0]["seed"] == "3"


def test_current_d2_full_report_shape_is_split_by_stage(tmp_path) -> None:
    def result(config_id: str, *, baseline: bool, associator: str, count: int) -> dict:
        return {
            "associator": associator,
            "config": {"config_id": config_id, "is_baseline": baseline},
            "per_seed": [
                {
                    "seed": seed,
                    "id_switch_count": 10 if baseline else 6,
                    "identity_continuity": 0.7 if baseline else 0.82,
                    "coverage_continuity": 0.95,
                    "false_track_count": 10,
                    "rmse": 1.0,
                    "mean_initialization_latency_s": 0.3,
                    "nis_available": True,
                    "nees_available": True,
                    "p95_loop_latency_s": 0.02,
                    "online_truth_leakage_count": 0,
                }
                for seed in range(count)
            ],
        }

    report = {
        "schema_version": "d2-p1-identity-calibration/v1",
        "screening": {
            "best_config_id": "gnn-best",
            "results": [
                result(
                    "gnn-baseline",
                    baseline=True,
                    associator="GNNHungarianAssociator",
                    count=10,
                ),
                result(
                    "gnn-best",
                    baseline=False,
                    associator="GNNHungarianAssociator",
                    count=10,
                ),
            ],
        },
        "confirmation": {
            "best_config_id": "gnn-best",
            "results": [
                result(
                    "gnn-baseline",
                    baseline=True,
                    associator="GNNHungarianAssociator",
                    count=20,
                ),
                result(
                    "gnn-best",
                    baseline=False,
                    associator="GNNHungarianAssociator",
                    count=20,
                ),
            ],
        },
        "jpda_comparison": {
            "same_budget_p95_loop_latency_s": 0.03,
            "screening": {
                "executed": True,
                "result": result(
                    "gnn-best",
                    baseline=False,
                    associator="JPDAAssociatorResearchAdapter",
                    count=10,
                ),
            },
            "confirmation": {
                "executed": True,
                "result": result(
                    "gnn-best",
                    baseline=False,
                    associator="JPDAAssociatorResearchAdapter",
                    count=20,
                ),
            },
        },
    }
    inputs = _inputs()
    outputs = DenseCrossingEvaluationReportGenerator().write_report_bundle(
        tmp_path,
        inputs=DenseCrossingEvaluationInputs(
            d1_governed_manifest=inputs.d1_governed_manifest,
            d1_offline_truth_summary=inputs.d1_offline_truth_summary,
            d2_screening=report,
            d2_confirmation=report,
        ),
    )
    aggregate = json.loads(outputs["aggregate_json"].read_text(encoding="utf-8"))

    assert aggregate["latency_budget_s"] == 0.03
    assert aggregate["best_gnn_candidate_id"] == "gnn-best"
    classes = {(group["phase"], group["variant_class"]) for group in aggregate["groups"]}
    assert ("screening", "gnn_baseline") in classes
    assert ("confirmation", "gnn_candidate") in classes
    assert ("confirmation", "lightweight_jpda") in classes
    assert aggregate["recommendations"][0]["status"] == "passed"
