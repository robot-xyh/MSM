from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from audit_report_evidence import (
    check_table, compare_documents, expand_bindings, read_markdown, read_source,
    read_word, render_cell, run, write_csv,
)
from audit_stage2_provenance import csv_metadata, hash_check
from audit_workspace_metadata import digest


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_markdown_tables_use_parser_not_pipe_split(self):
        path = self.root / "sample.md"
        path.write_text("### 3.1 Results\n\n| name | value |\n|---|---|\n| a\\|b | **90%** |\n")
        table = read_markdown(path)["tables"][0]
        self.assertEqual(table["rows"][1], ["a|b", "90%"])
        self.assertEqual(table["section"], "3.1 Results")
        self.assertEqual(table["line"], 3)

    def test_image_reference_and_space_path(self):
        path = self.root / "sample.md"
        path.write_text("![inline](<assets/a b.png>)\n\n![reference][pic]\n\n[pic]: assets/c.png\n")
        self.assertEqual([i["path"] for i in read_markdown(path)["images"]],
                         ["assets/a%20b.png", "assets/c.png"])

    def test_word_table_and_embedded_media(self):
        path = self.root / "sample.docx"
        xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               '<w:body><w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>'
               '<w:r><w:t>3.1 Results</w:t></w:r></w:p>'
               '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>value</w:t></w:r></w:p></w:tc>'
               '</w:tr></w:tbl></w:body></w:document>')
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
            archive.writestr("word/media/image1.png", b"not-a-real-image")
        parsed = read_word(path)
        self.assertEqual(parsed["tables"][0]["section"], "3.1 Results")
        self.assertEqual(parsed["tables"][0]["rows"], [["value"]])
        self.assertEqual(len(parsed["media"][0]["sha256"]), 64)

    def test_document_comparison_counts_duplicate_tables(self):
        table = {"index": 1, "section": "", "rows": [["a"], ["1"]]}
        left = {"tables": [table, {**table, "index": 2}], "headings": [], "paragraphs": []}
        right = {"tables": [table], "headings": [], "paragraphs": []}
        result = compare_documents(left, right)
        self.assertEqual(result["identical_table_count"], 1)
        self.assertEqual(result["markdown_tables_not_identical_in_word"][0]["index"], 2)

    def test_display_format_and_fields_preserved(self):
        display, values = render_cell({"a": 0.125, "b": 1.0},
                                      {"fields": ["a", "b"], "formats": [".1%", ".1%"],
                                       "template": "{0}/{1}"})
        self.assertEqual(display, "12.5%/100.0%")
        self.assertEqual(values, {"a": 0.125, "b": 1.0})

    def fixture(self, rows):
        source = {"path": "source.json", "rows": rows,
                  "locations": [{"path": "source.json", "selector": f"rows.{i}"} for i in range(len(rows))]}
        table = {"index": 1, "line": 3, "section": "3.1 Results",
                 "rows": [["name", "score"], ["A", "90.0%"]]}
        binding = {"source": "test", "keys": ["name"],
                   "columns": {"name": {"field": "name"}, "score": {"field": "score", "format": ".1%"}}}
        return table, binding, {"test": source}

    def test_matching_cell_keeps_json_location(self):
        args = self.fixture([{"name": "A", "score": 0.9}])
        result = check_table("report.md", *args)[0]
        self.assertEqual(result["status"], "match")
        self.assertEqual(result["selector"], "rows.0")
        self.assertEqual(result["source_values"], {"score": 0.9})

    def test_mismatch_not_silently_tolerated(self):
        args = self.fixture([{"name": "A", "score": 0.89}])
        self.assertEqual(check_table("report.md", *args)[0]["status"], "mismatch")

    def test_missing_source_row_is_not_zero(self):
        args = self.fixture([])
        result = check_table("report.md", *args)[0]
        self.assertEqual(result["status"], "missing_source_row")
        self.assertIsNone(result["expected"])

    def test_duplicate_keys_are_ambiguous(self):
        args = self.fixture([{"name": "A", "score": 0.9}] * 2)
        self.assertEqual(check_table("report.md", *args)[0]["status"], "ambiguous_source_rows")

    def test_transposed_metric_table(self):
        table, binding, sources = self.fixture([{"score": 0.9}])
        table["rows"] = [["metric", "value"], ["precision", "90.0%"]]
        binding.update(keys=[], columns={}, row_rules={"precision": {"field": "score", "format": ".1%"}})
        self.assertEqual(check_table("report.md", table, binding, sources)[0]["status"], "match")

    def test_json_selector_union_preserves_original_locations(self):
        (self.root / "data.json").write_text(json.dumps({"a": [{"n": 1}], "b": [{"n": 2}]}))
        result = read_source(self.root, {"path": "data.json", "kind": "json", "selectors": ["a", "b"]})
        self.assertEqual([row["n"] for row in result["rows"]], [1, 2])
        self.assertEqual([row["selector"] for row in result["locations"]], ["a.0", "b.0"])

    def test_csv_bom_and_multiple_sources(self):
        for name in ("a.csv", "b.csv"):
            (self.root / name).write_bytes(b"\xef\xbb\xbfcount,value\r\n20,0.9\r\n")
        result = read_source(self.root, {"paths": ["a.csv", "b.csv"], "kind": "csv"})
        self.assertEqual(result["rows"][0]["count"], "20")
        self.assertEqual(result["locations"][1], {"path": "b.csv", "selector": "data_row:1"})

    def test_template_and_format_boundaries(self):
        spec = {"reports": {"r": "report"}, "templates": {"t": {"columns": {"a": {"field": "x"}}}},
                "bindings": [{"report": "r", "template": "t", "formats": ["md"],
                              "columns": {"b": {"field": "y"}}}]}
        result = expand_bindings(spec)
        self.assertEqual(result[0]["document"], "report.md")
        self.assertEqual(set(result[0]["columns"]), {"a", "b"})
        self.assertEqual(len(result), 1)

    def test_existing_output_is_never_overwritten(self):
        output = self.root / "deliverables/project_audits/existing"
        output.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            run(self.root, self.root / "missing.json", output)

    def test_output_cannot_enter_experiment_tree(self):
        with self.assertRaises(ValueError):
            run(self.root, self.root / "missing.json", self.root / "research_modules/outputs/new")

    def test_csv_output_uses_lf(self):
        path = self.root / "result.csv"
        write_csv(path, [{"name": "example", "value": {"n": 1}}], ["name", "value"])
        self.assertNotIn(b"\r\n", path.read_bytes())

    def test_metadata_distinguishes_rows_from_seeds(self):
        path = self.root / "rows.csv"
        path.write_text("seed,value\n1,a\n1,b\n2,c\n")
        result = csv_metadata(path, self.root)
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["distinct_values"]["seed"], ["1", "2"])

    def test_hash_check_does_not_load_model(self):
        path = self.root / "model.pt"
        payload = b"arbitrary bytes, not an executable checkpoint"
        path.write_bytes(payload)
        self.assertEqual(hash_check(path, digest(path), self.root, "test")["status"], "match")
        self.assertEqual(path.read_bytes(), payload)

    def test_missing_hash_file_is_reported(self):
        result = hash_check(self.root / "absent.pt", "0" * 64, self.root, "test")
        self.assertEqual(result["status"], "missing")
        self.assertIsNone(result["actual"])


if __name__ == "__main__":
    unittest.main()
