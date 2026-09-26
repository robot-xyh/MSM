"""Filesystem-only checks for cleanup recommendations; no deletion is performed."""

from pathlib import Path
import tempfile
import unittest
import zipfile

from audit_cleanup_candidates import archive_record, cache_record, duplicate_pdfs, reference_scan, safe_zip_member


class CleanupTests(unittest.TestCase):
    def test_bytecode_requires_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache = root / "__pycache__"
            cache.mkdir()
            binary = cache / "example.cpython-311.pyc"
            binary.write_bytes(b"bytecode")
            self.assertEqual(cache_record(cache, set())["status"], "review_required")
            (root / "example.py").write_text("pass\n")
            self.assertEqual(cache_record(cache, set())["status"], "regenerable_cache")
            self.assertEqual(cache_record(cache, {binary})["status"], "review_required")

    def test_duplicates_are_content_not_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root / name for name in ("a.pdf", "b.pdf", "c.pdf")]
            for path, data in zip(paths, (b"same", b"same", b"diff")):
                path.write_bytes(data)
            groups = duplicate_pdfs(paths, {paths[1]}, {})
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["suggested_keep"], str(paths[1]))
            self.assertEqual(len(groups[0]["files"]), 2)

    def test_pytest_bytecode_requires_matching_test_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "test_example.cpython-312-pytest-7.4.4.pyc").write_bytes(b"bytecode")
            self.assertEqual(cache_record(cache, set())["status"], "review_required")
            (root / "test_example.py").write_text("pass\n")
            self.assertEqual(cache_record(cache, set())["status"], "regenerable_cache")

    def test_archive_requires_every_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "data.zip"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("a.txt", b"abc")
                stream.writestr("b.txt", b"defg")
            a = root / "a.txt"
            a.write_bytes(b"abc")
            record = archive_record(archive, {3: [a]}, set(), {})
            self.assertEqual(record["missing_payload_files"], 1)
            self.assertEqual(record["status"], "review_required")
            b = root / "b.txt"
            b.write_bytes(b"defg")
            record = archive_record(archive, {3: [a], 4: [b]}, set(), {})
            self.assertEqual(record["status"], "all_payloads_present_optional_archive_cleanup")
            self.assertTrue(record["original_layout_preserved"])
            self.assertTrue(archive.exists())

    def test_renamed_archive_payload_is_not_original_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "data.zip"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("original.pdf", b"abc")
            renamed = root / "renamed.pdf"
            renamed.write_bytes(b"abc")
            record = archive_record(archive, {3: [renamed]}, set(), {})
            self.assertEqual(record["missing_payload_files"], 0)
            self.assertFalse(record["original_layout_preserved"])

    def test_unsafe_archive_members_are_rejected(self):
        for name in ("../file", "/file", "C:/file", "folder\\file"):
            self.assertFalse(safe_zip_member(name))
        self.assertTrue(safe_zip_member("folder/file.pdf"))

    def test_nested_archive_can_match_existing_zip_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / "inner.zip"
            nested.write_bytes(b"nested archive bytes")
            archive = root / "outer.zip"
            with zipfile.ZipFile(archive, "w") as stream:
                stream.writestr("inner.zip", nested.read_bytes())
            record = archive_record(archive, {nested.stat().st_size: [nested]}, {nested}, {})
            self.assertEqual(record["missing_payload_files"], 0)
            self.assertEqual(record["members"][0]["match"], str(nested))

    def test_tracked_archive_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "data.zip"
            archive.write_bytes(b"not opened")
            self.assertEqual(archive_record(archive, {}, {archive}, {})["status"], "keep_tracked_archive")

    def test_self_reference_does_not_count_as_external(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "old_run"
            run.mkdir()
            own = run / "summary.json"
            own.write_text('{"run": "old_run"}')
            report = root / "report.md"
            report.write_text("source: old_run")
            item = {"path": str(run)}
            errors = []
            reference_scan([own, report], [item], errors)
            self.assertEqual(item["reference_file_count"], 1)
            self.assertEqual(item["reference_files"], [str(report)])
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
