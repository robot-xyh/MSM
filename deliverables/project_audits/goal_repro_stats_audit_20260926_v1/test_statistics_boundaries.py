"""Probe only isolated arithmetic helpers using fabricated, non-spatial records."""

import ast
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import unittest

import numpy as np


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
BASE = ROOT / "research_modules/independent_experiments"
FILES = {
    "dual": BASE / "dual_optical_online_benchmark/report_matrix_replay.py",
    "center": BASE / "center_terminal_cv_campaign/exp_center_handover/run_error_matrix.py",
    "search": BASE / "center_terminal_cv_campaign/exp_search/run_offline_matrix.py",
}


def helpers(path, names):
    tree = ast.parse(path.read_text())
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in selected} == set(names)
    for node in ast.walk(ast.Module(body=selected, type_ignores=[])):
        assert not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "exec", "eval", "compile", "__import__"}
    body = ast.parse("from __future__ import annotations").body + selected
    namespace = {"defaultdict": defaultdict, "math": math, "np": np}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def ordinary_row(seed=1, output=1, correct=1):
    return {
        "profile": "toy", "target_count": 10, "seed": seed,
        "condition": "toy", "route_name": "toy", "round_index": 1,
        "output_match_count": output, "correct_match_count": correct,
        "correct_unique_target_count": correct,
        "on_time_correct_unique_target_count": correct,
        "single_station_dominant_observation_count": 1,
        "single_station_labeled_observation_count": 1,
        "single_station_correct_identity_count": 1,
        "single_station_identity_opportunity_count": 20,
        "single_station_duplicate_track_count": 0,
        "single_station_mixed_track_count": 0,
        "dual_station_residual_loss_count": 0,
        "latency_ms": 1.0, "timed_out": False,
        "evidence_status": "toy", "protocol_bridge_applied": False,
    }


def center_row(seed=1, precision=1.0):
    return {"target_count": 10, "handover_mode": "toy", "attitude_mode": "toy", "navigation_mode": "toy", "detection_mode": "toy", "backend": "toy", "seed": seed, "binding_precision": precision, "binding_recall": 0.5, "runtime_s": 0.1, "final_hint_validation_rate": None, "gnn_scale_status": "toy"}


class StatisticsBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dual = helpers(FILES["dual"], ["_final_rows", "_summarize", "_percentile_nearest_rank"])
        cls.center = helpers(FILES["center"], ["aggregate_rows", "_mean"])
        cls.search = helpers(FILES["search"], ["_mean"])

    def test_final_round_selection(self):
        old, new = ordinary_row(), ordinary_row()
        new["round_index"] = 2
        self.assertEqual(self.dual["_final_rows"]([new, old])[0]["round_index"], 2)

    def test_conflicting_equal_round_is_order_dependent(self):
        a, b = ordinary_row(correct=1), ordinary_row(correct=0)
        self.assertEqual(self.dual["_final_rows"]([a, b])[0]["correct_match_count"], 1)
        self.assertEqual(self.dual["_final_rows"]([b, a])[0]["correct_match_count"], 0)

    def test_pooled_precision_is_not_mean_precision(self):
        rows = [ordinary_row(1, 1, 1), ordinary_row(2, 9, 1)]
        actual = self.dual["_summarize"](rows)[0]["offline_completed_precision"]
        self.assertAlmostEqual(actual, 0.2)
        self.assertNotAlmostEqual(actual, statistics.mean([1.0, 1.0 / 9]))

    def test_zero_output_precision_is_missing(self):
        result = self.dual["_summarize"]([ordinary_row(output=0, correct=0)])[0]
        self.assertIsNone(result["offline_completed_precision"])
        self.assertEqual(result["offline_completed_coverage"], 0.0)

    def test_zero_labeled_denominator_is_coerced_to_zero(self):
        row = ordinary_row()
        row["single_station_dominant_observation_count"] = 0
        row["single_station_labeled_observation_count"] = 0
        self.assertEqual(self.dual["_summarize"]([row])[0]["single_station_precision"], 0.0)

    def test_timeout_keeps_quality_but_not_timely_count(self):
        row = ordinary_row()
        row.update(timed_out=True, latency_ms=2000.0, on_time_correct_unique_target_count=0)
        result = self.dual["_summarize"]([row])[0]
        self.assertEqual(result["offline_completed_coverage"], 0.1)
        self.assertEqual(result["on_time_coverage"], 0.0)

    def test_duplicate_seed_is_counted_twice_in_center_aggregate(self):
        row = center_row()
        result = self.center["aggregate_rows"]([row, dict(row)])[0]
        self.assertEqual(result["seed_count"], 2)
        self.assertEqual(len({row["seed"]}), 1)

    def test_missing_center_precision_is_not_accepted(self):
        with self.assertRaises(TypeError):
            self.center["aggregate_rows"]([center_row(precision=None)])

    def test_search_mean_excludes_none(self):
        self.assertEqual(self.search["_mean"]([{"x": None}, {"x": 2.0}], "x"), 2.0)

    def test_all_missing_search_mean_produces_nonstandard_json(self):
        value = self.search["_mean"]([{"x": None}], "x")
        self.assertTrue(math.isnan(value))
        with self.assertRaises(ValueError):
            json.dumps({"x": value}, allow_nan=False)

    def test_population_std_is_not_sample_std(self):
        result = self.center["aggregate_rows"]([center_row(1, 0.0), center_row(2, 1.0)])[0]
        self.assertAlmostEqual(result["binding_precision_std"], 0.5)
        self.assertNotAlmostEqual(result["binding_precision_std"], statistics.stdev([0.0, 1.0]))

    def test_elapsed_fields_prevent_bytewise_result_equality(self):
        a, b = {"count": 2, "runtime_s": 0.1}, {"count": 2, "runtime_s": 0.2}
        self.assertNotEqual(json.dumps(a), json.dumps(b))
        self.assertEqual(a["count"], b["count"])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(StatisticsBoundaries)
    names = [test.id() for test in suite]
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    record = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "test_names": names, "scope": "Pure statistics helpers extracted via AST; fabricated records only; no module initialization, model, association or simulation executed", "meaning": "Passing risk-reproduction tests confirms observed boundary behavior; it does not mean the production statistics code is free of issues", "source_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in FILES.values()}}
    (OUT / "STATISTICS_BOUNDARY_TESTS.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
