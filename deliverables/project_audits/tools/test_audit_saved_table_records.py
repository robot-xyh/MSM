"""Saved-table audit regression tests using temporary, fabricated CSVs."""

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from audit_report_evidence import read_source
from audit_saved_table_records import run


class SavedTableAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.table = self.root / "records.csv"
        self.table.write_text("group,seed,round,value\na,1,1,\na,1,2,0\n", encoding="utf-8")
        self.spec_path = self.root / "spec.json"
        self.output = self.root / "deliverables/project_audits/new"
        self.contract = {"unique_key": ["group", "seed", "round"], "group_by": ["group"],
                         "seed_field": "seed", "numeric_fields": ["value"], "nullable_fields": ["value"]}
        self.source = {"path": "records.csv", "kind": "csv", "record_contract": self.contract,
                       "expected": {"rows": 2, "groups": 1, "seeds_per_group": 1}}
        self.spec = {"schema": "saved-table-record-audit-v1", "sources": {"test": self.source}}

    def execute(self):
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        return run(self.root, self.spec_path, self.output)

    def test_checks_saved_source_and_preserves_its_bytes(self):
        original = self.table.read_bytes()
        result = self.execute()
        self.assertTrue(result["passed"])
        self.assertEqual(result["audited_record_count"], 2)
        self.assertEqual(result["sources"][0]["distinct_seed_ids_count"], 1)
        self.assertEqual(result["allowed_missing_cell_count"], 1)
        self.assertEqual(result["sources"][0]["record_validation"]["groups"][0]["distinct_seed_count"], 1)
        self.assertEqual(self.table.read_bytes(), original)
        self.assertTrue(result["file_hash_checks"][0]["unchanged"])
        self.assertFalse(result["metrics_recomputed"])
        with (self.output / "NULL_FIELD_LOCATIONS.csv").open(newline="") as stream:
            missing = list(csv.DictReader(stream))
        self.assertEqual(missing[0]["selector"], "data_row:1")
        self.assertEqual(json.loads(missing[0]["record_key"])["round"], "1")

    def test_duplicate_record_is_failure_without_deduplication(self):
        self.table.write_text("group,seed,round,value\na,1,1,0\na,1,1,0\n")
        before = self.table.read_bytes()
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertIn("Duplicate record key", result["sources"][0]["errors"][0])
        self.assertEqual(self.table.read_bytes(), before)
        self.assertTrue((self.output / "VALIDATION_RECORD.json").exists())

    def test_missing_contract_is_failure(self):
        del self.source["record_contract"]
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertIn("record_contract", result["sources"][0]["errors"][0])

    def test_expected_counts_are_checked_not_assumed(self):
        self.source["expected"] = {"rows": 3, "groups": 2, "seeds_per_group": 2}
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["sources"][0]["errors"]), 3)

    def test_invalid_expected_option_is_failure(self):
        self.source["expected"]["typo"] = 2
        self.assertFalse(self.execute()["passed"])

    def test_invalid_expected_count_type_is_failure(self):
        self.source["expected"]["rows"] = True
        self.assertFalse(self.execute()["passed"])

    def test_unchecked_text_columns_are_disclosed(self):
        self.table.write_text("group,seed,round,value,note\na,1,1,0,text\na,1,2,0,text\n")
        result = self.execute()
        self.assertTrue(result["passed"])
        self.assertEqual(result["sources"][0]["unchecked_column_types"], ["note"])

    def test_missing_source_is_reported(self):
        self.source["path"] = "missing.csv"
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertIn("missing.csv", result["sources"][0]["errors"][0])

    def test_hash_change_during_read_is_detected(self):
        def changed_read(root, config):
            result = read_source(root, config)
            self.table.write_text(self.table.read_text() + "a,2,1,0\n")
            return result
        with patch("audit_saved_table_records.read_source", side_effect=changed_read):
            result = self.execute()
        self.assertFalse(result["passed"])
        self.assertFalse(result["file_hash_checks"][0]["unchanged"])

    def test_existing_output_is_preserved(self):
        self.output.mkdir(parents=True)
        sentinel = self.output / "sentinel.txt"
        sentinel.write_text("keep")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(sentinel.read_text(), "keep")

    def test_output_cannot_enter_research_or_replace_audit_root(self):
        for output in [self.root / "research_modules/new", self.root / "deliverables/project_audits"]:
            with self.subTest(output=output), self.assertRaises(ValueError):
                run(self.root, self.spec_path, output)

    def test_source_cannot_escape_repository(self):
        self.source["path"] = "../outside.csv"
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertIn("outside repository", result["sources"][0]["errors"][0])

    def test_empty_sources_rejected_before_output(self):
        self.spec["sources"] = {}
        with self.assertRaises(ValueError):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_empty_table_does_not_meet_expected_counts(self):
        self.table.write_text("group,seed,round,value\n")
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertEqual(result["audited_record_count"], 0)

    def test_header_errors_fail_without_modifying_source(self):
        self.table.write_text("group,seed,seed\na,1,2\n")
        before = self.table.read_bytes()
        result = self.execute()
        self.assertFalse(result["passed"])
        self.assertIn("Duplicate CSV header", result["sources"][0]["errors"][0])
        self.assertEqual(self.table.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
