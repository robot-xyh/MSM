"""Checks for read-only preservation inventories."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_preservation_register import discover_output_roots, file_record, group_path, prepare, walk_files


class PreservationTests(unittest.TestCase):
    def test_hash_and_original_content_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.bin"
            path.write_bytes(b"original")
            expected = hashlib.sha256(b"original").hexdigest()
            record = file_record(path, True, {expected})
            self.assertEqual(record["sha256"], expected)
            self.assertTrue(record["matches_recorded_hashes"])
            self.assertEqual(path.read_bytes(), b"original")

    def test_wrong_expected_hash_is_visible(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.bin"
            path.write_bytes(b"original")
            self.assertFalse(file_record(path, True, {"0" * 64})["matches_recorded_hashes"])

    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target").write_bytes(b"outside")
            (root / "link").symlink_to(root / "target")
            record = file_record(root / "link", True)
            self.assertEqual(record["hash_status"], "not_followed")
            self.assertNotIn("sha256", record)

    def test_output_discovery_and_cache_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "research_modules" / "module" / "outputs"
            (output / "cache").mkdir(parents=True)
            (output / "cache" / "data.json").write_text("{}")
            (output / "__pycache__").mkdir()
            (output / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
            self.assertEqual(discover_output_roots(root), [output])
            errors = []
            self.assertEqual(list(walk_files(output, errors)), [output / "cache" / "data.json"])
            self.assertEqual(errors, [])

    def test_metadata_only_and_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data"
            path.write_bytes(b"original")
            self.assertEqual(file_record(path, False)["hash_status"], "metadata_only")
            self.assertEqual(file_record(path.parent / "absent", True)["hash_status"], "read_error")

    def test_group_does_not_flatten_distinct_runs(self):
        root = Path("/tmp/example/outputs")
        self.assertEqual(group_path(root, root / "run_a" / "model.pt"), str(root / "run_a"))
        self.assertEqual(group_path(root, root / "summary.csv"), str(root))

    def test_changed_file_has_no_stable_hash(self):
        import os

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.bin"
            path.write_bytes(b"original")
            original_fstat = os.fstat
            calls = 0

            def change_after_read(fd):
                nonlocal calls
                calls += 1
                if calls == 2:
                    path.write_bytes(b"updated and longer")
                return original_fstat(fd)

            with patch("prepare_preservation_register.os.fstat", side_effect=change_after_read):
                record = file_record(path, True)
            self.assertEqual(record["hash_status"], "changed_during_read")
            self.assertNotIn("sha256", record)

    def test_empty_inventory_writes_headers_and_no_backup_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "research_modules").mkdir()
            snapshot = root / "snapshot.json"
            snapshot.write_text(json.dumps({"evidence_roots": []}))
            output = root / "register"
            with patch("prepare_preservation_register.SIBLINGS", ()), patch(
                "prepare_preservation_register.subprocess.check_output", side_effect=[b"test-head\n", b""]
            ):
                summary = prepare(root, output, snapshot)
            self.assertFalse(summary["backup_created"])
            self.assertEqual(summary["errors"], [])
            self.assertEqual(summary["group_count"], 0)
            self.assertEqual(len((output / "PRESERVATION_GROUPS.csv").read_text().splitlines()), 1)

    def test_experiment_cannot_be_inventory_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "research_modules" / "example" / "outputs"
            output.mkdir(parents=True)
            snapshot = root / "snapshot.json"
            snapshot.write_text(json.dumps({"evidence_roots": []}))
            with self.assertRaises(ValueError):
                prepare(root, output / "register", snapshot)
            self.assertFalse((output / "register").exists())

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "research_modules").mkdir()
            snapshot = root / "snapshot.json"
            snapshot.write_text(json.dumps({"evidence_roots": []}))
            output = root / "register"
            output.mkdir()
            marker = output / "keep.txt"
            marker.write_text("keep")
            with self.assertRaises(FileExistsError):
                prepare(root, output, snapshot)
            self.assertEqual(marker.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
