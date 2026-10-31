"""Fabricated administrative records only; no experiment modules are imported."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from audit_record_validation import read_strict_csv, read_strict_json, validate_records
from audit_report_evidence import read_source, render_cell, write_csv


class RecordValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.contract = {"unique_key": ["group", "seed"], "group_by": ["group"],
                         "seed_field": "seed", "numeric_fields": ["value"],
                         "nullable_fields": ["value"]}

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def row(self, seed=1, value=0.0, group="sample"):
        return {"group": group, "seed": seed, "value": value}

    def test_json_bom_null_and_zero_preserved(self):
        path = self.write("rows.json", '\ufeff[{"value":null},{"value":0}]')
        self.assertEqual(read_strict_json(path), [{"value": None}, {"value": 0}])

    def test_json_rejects_duplicate_members_at_any_depth(self):
        for text in ['{"a":1,"a":2}', '{"x":{"a":1,"a":1}}']:
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "Duplicate JSON member"):
                read_strict_json(self.write("rows.json", text))

    def test_json_rejects_nonfinite_and_overflow(self):
        for value in ["NaN", "Infinity", "-Infinity", "1e400"]:
            path = self.write("rows.json", '{"value":' + value + '}')
            original = path.read_bytes()
            with self.subTest(value=value), self.assertRaises(ValueError):
                read_strict_json(path)
            self.assertEqual(path.read_bytes(), original)

    def test_csv_bom_and_quoted_newline(self):
        path = self.write("rows.csv", '\ufeffname,value\n"a\nb",0\n')
        self.assertEqual(read_strict_csv(path), [{"name": "a\nb", "value": "0"}])

    def test_csv_duplicate_or_blank_headers_rejected(self):
        for text in ["a,a\n1,2\n", "a, \n1,2\n", "", "\n"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_strict_csv(self.write("rows.csv", text))

    def test_csv_malformed_rows_rejected(self):
        for text in ['a,b\n1\n', 'a,b\n1,2,3\n', 'a,b\n"unfinished,2\n', 'a,b\n\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_strict_csv(self.write("rows.csv", text))

    def test_csv_header_only_is_empty_not_one_missing_record(self):
        self.assertEqual(read_strict_csv(self.write("rows.csv", "a,b\n")), [])

    def test_identical_and_conflicting_duplicates_both_rejected(self):
        for second in [self.row(), self.row(value=0.8)]:
            for rows in [[self.row(), second], [second, self.row()]]:
                with self.subTest(rows=rows), self.assertRaisesRegex(ValueError, "Duplicate record key"):
                    validate_records(rows, self.contract)

    def test_same_seed_in_distinct_groups_is_allowed(self):
        result = validate_records([self.row(group="a"), self.row(group="b")], self.contract)
        self.assertEqual([group["distinct_seed_count"] for group in result["groups"]], [1, 1])

    def test_round_records_are_not_distinct_seeds(self):
        config = {**self.contract, "unique_key": ["group", "seed", "round"]}
        rows = [{**self.row(), "round": 1}, {**self.row(), "round": 2}]
        result = validate_records(rows, config)
        self.assertEqual(result["groups"][0]["record_count"], 2)
        self.assertEqual(result["groups"][0]["distinct_seed_count"], 1)

    def test_explicit_missing_kept_separate_from_zero(self):
        rows = [self.row(1, None), self.row(2, 0.0), self.row(3, " ")]
        before = deepcopy(rows)
        result = validate_records(rows, self.contract)
        self.assertEqual(result["numeric_fields"]["value"],
                         {"valid_count": 1, "missing_count": 2, "all_missing": False})
        self.assertEqual(rows, before)

    def test_all_missing_is_explicit_and_strict_json_serializable(self):
        result = validate_records([self.row(value=None)], self.contract)
        self.assertTrue(result["numeric_fields"]["value"]["all_missing"])
        json.dumps(result, allow_nan=False)
        self.assertNotIn("mean", result)

    def test_empty_dataset_is_not_all_missing(self):
        result = validate_records([], self.contract)
        self.assertEqual(result["record_count"], 0)
        self.assertFalse(result["numeric_fields"]["value"]["all_missing"])

    def test_absent_field_is_not_treated_as_explicit_null(self):
        row = self.row()
        del row["value"]
        with self.assertRaisesRegex(ValueError, "missing numeric field"):
            validate_records([row], self.contract)

    def test_null_requires_explicit_permission(self):
        config = {**self.contract, "nullable_fields": []}
        with self.assertRaisesRegex(ValueError, "null is not allowed"):
            validate_records([self.row(value=None)], config)

    def test_numeric_values_reject_booleans_nonfinite_and_objects(self):
        for value in [True, False, "NaN", "Infinity", "1e400", float("nan"), {}, [], 10**400]:
            with self.subTest(value=str(value)), self.assertRaisesRegex(ValueError, "finite number"):
                validate_records([self.row(value=value)], self.contract)

    def test_key_fields_reject_missing_blank_and_non_identifiers(self):
        for value in [None, " ", True, 1.0, [], {}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_records([self.row(seed=value)], self.contract)
        row = self.row()
        del row["seed"]
        with self.assertRaisesRegex(ValueError, "missing key field"):
            validate_records([row], self.contract)

    def test_mixed_key_types_rejected_without_coercion(self):
        with self.assertRaisesRegex(ValueError, "inconsistent key type"):
            validate_records([self.row(seed=1), self.row(seed="1")], self.contract)

    def test_nested_fields(self):
        config = {"unique_key": ["meta.seed"], "numeric_fields": ["data.0.value"]}
        result = validate_records([{"meta": {"seed": 1}, "data": [{"value": 2}]}], config)
        self.assertEqual(result["numeric_fields"]["data.0.value"]["valid_count"], 1)

    def test_bad_contracts_do_not_silently_skip_checks(self):
        for config in [None, {}, {"unique_key": []}, {"unique_key": "seed"},
                       {"unique_key": ["seed", "seed"]}, {"unique_key": ["seed"], "typo": 1},
                       {"unique_key": ["seed"], "seed_field": "missing"},
                       {"unique_key": ["seed"], "group_by": []},
                       {"unique_key": ["seed"], "nullable_fields": ["value"]},
                       {"unique_key": ["seed"], "seed_field": None}]:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_records([self.row()], config)

    def test_nonobject_record_rejected(self):
        with self.assertRaisesRegex(ValueError, "not an object"):
            validate_records([1], self.contract)

    def test_source_without_contract_does_not_claim_key_validation(self):
        self.write("rows.json", json.dumps([self.row()]))
        result = read_source(self.root, {"path": "rows.json", "kind": "json"})
        self.assertEqual(result["record_validation"]["status"], "not_configured")

    def test_empty_or_malformed_source_list_is_explicit_error(self):
        for paths in [[], "rows.json", [None], [""]]:
            with self.subTest(paths=paths), self.assertRaisesRegex(ValueError, "Source paths"):
                read_source(self.root, {"paths": paths, "kind": "json"})

    def test_unknown_source_kind_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported source kind"):
            read_source(self.root, {"path": "rows.bin", "kind": "binary"})

    def test_source_contract_checks_union_of_input_files(self):
        for name in ["a.json", "b.json"]:
            self.write(name, json.dumps([self.row()]))
        with self.assertRaisesRegex(ValueError, "Duplicate record key"):
            read_source(self.root, {"paths": ["a.json", "b.json"], "kind": "json",
                                    "record_contract": self.contract})

    def test_repeated_selector_cannot_double_count(self):
        self.write("rows.json", json.dumps({"items": [self.row()]}))
        with self.assertRaisesRegex(ValueError, "Duplicate record key"):
            read_source(self.root, {"path": "rows.json", "kind": "json", "selectors": ["items", "items"],
                                    "record_contract": self.contract})

    def test_source_contract_preserves_values_and_locations(self):
        path = self.write("rows.csv", "group,seed,value\nsample,1,\nsample,2,0\n")
        before = path.read_bytes()
        result = read_source(self.root, {"path": "rows.csv", "kind": "csv", "record_contract": self.contract})
        self.assertEqual(result["rows"][0]["value"], "")
        self.assertEqual(result["record_validation"]["numeric_fields"]["value"]["missing_count"], 1)
        self.assertEqual(result["locations"][1]["selector"], "data_row:2")
        self.assertEqual(path.read_bytes(), before)

    def test_missing_display_requires_explicit_rule(self):
        with self.assertRaisesRegex(ValueError, "missing_text"):
            render_cell({"value": None}, {"field": "value", "format": ".1%"})

    def test_missing_display_preserves_source_null(self):
        result = render_cell({"value": None}, {"field": "value", "format": ".1%", "missing_text": "unavailable"})
        self.assertEqual(result, ("unavailable", {"value": None}))

    def test_partial_missing_template_and_zero_display(self):
        rule = {"fields": ["a", "b"], "template": "{0}/{1}", "missing_text": "unavailable"}
        self.assertEqual(render_cell({"a": 0, "b": None}, rule)[0], "unavailable")
        self.assertEqual(render_cell({"a": 0, "b": 1}, rule)[0], "0/1")

    def test_csv_nested_json_does_not_emit_nan(self):
        with self.assertRaises(ValueError):
            write_csv(self.root / "out.csv", [{"value": {"x": float("nan")}}], ["value"])


if __name__ == "__main__":
    unittest.main()
