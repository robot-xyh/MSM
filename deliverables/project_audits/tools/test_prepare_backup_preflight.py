"""Backup preparation must not copy payloads, follow links or hide gaps."""

import gzip
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from prepare_backup_preflight import GIB, destination_check, preflight, required_bytes, scan_tree


class BackupPreflightTests(unittest.TestCase):
    def test_reserve_uses_integer_round_up(self):
        self.assertEqual(required_bytes(0), GIB)
        self.assertEqual(required_bytes(1), GIB + 2)
        self.assertEqual(required_bytes(100), GIB + 110)

    def test_missing_destination_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "missing"
            self.assertEqual(destination_check(target, [], 1)["status"], "existing_destination_directory_required")
            self.assertFalse(target.exists())

    def test_absent_destination_never_claims_ready(self):
        result = destination_check(None, [], 1)
        self.assertEqual(result["status"], "destination_not_specified")
        self.assertFalse(result["copy_started"])
        self.assertFalse(result["independence_verified"])

    def test_source_destination_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            child = source / "backup"
            child.mkdir(parents=True)
            for dest in (root, source, child):
                self.assertEqual(destination_check(dest, [source], 1)["status"], "source_destination_overlap")

    def test_same_filesystem_is_not_an_independent_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / "source", Path(folder) / "target"
            source.mkdir()
            target.mkdir()
            with patch("prepare_backup_preflight.command_metadata", return_value={}):
                result = destination_check(target, [source], 1)
            self.assertEqual(result["status"], "same_filesystem_not_independent")
            self.assertFalse(result["write_probe_performed"])
            self.assertEqual(list(target.iterdir()), [])

    def test_scan_includes_git_cache_empty_directories_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("ref: refs/heads/main")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "file.pyc").write_bytes(b"abc")
            (root / "empty").mkdir()
            os.link(root / ".git" / "HEAD", root / "hardlink")
            rows = list(scan_tree(root, root / "excluded"))
            by_path = {r["relative_path"]: r for r in rows}
            self.assertIn(".git/HEAD", by_path)
            self.assertIn("__pycache__/file.pyc", by_path)
            self.assertEqual(by_path["empty"]["kind"], "directory")
            self.assertEqual(by_path["hardlink"]["inode"], by_path[".git/HEAD"]["inode"])

    def test_symlink_and_broken_symlink_are_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "target").mkdir()
            (root / "target" / "data").write_text("data")
            (root / "link").symlink_to(root / "target", target_is_directory=True)
            (root / "broken").symlink_to(root / "missing")
            rows = list(scan_tree(root, root / "excluded"))
            links = [row for row in rows if row.get("kind") == "symlink"]
            self.assertEqual(len(links), 2)
            self.assertTrue(all(not row["target_followed"] for row in links))
            self.assertFalse(any(row["relative_path"] == "link/data" for row in rows))

    def test_missing_source_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "missing"
            rows = list(scan_tree(root, root / "excluded"))
            self.assertEqual(len(rows), 1)
            self.assertIn("error", rows[0])

    def test_special_file_is_not_opened(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            os.mkfifo(root / "pipe")
            rows = list(scan_tree(root, root / "excluded"))
            self.assertEqual(next(row for row in rows if row["relative_path"] == "pipe")["kind"], "special")

    def test_output_tree_excluded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "audit"
            output.mkdir()
            (output / "record").write_text("ignore")
            self.assertEqual([r["relative_path"] for r in scan_tree(root, output)], ["."])

    def test_output_outside_audit_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for output in (root / "research_modules" / "outputs", root / "deliverables" / "project_audits"):
                with self.assertRaises(ValueError):
                    preflight(root, output)
                self.assertFalse(output.exists())

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "deliverables" / "project_audits" / "existing"
            output.mkdir(parents=True)
            (output / "marker").write_text("keep")
            with self.assertRaises(FileExistsError):
                preflight(root, output)
            self.assertEqual((output / "marker").read_text(), "keep")

    def test_minimal_preflight_is_metadata_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root / "data.bin"
            data.write_bytes(b"original")
            output = root / "deliverables" / "project_audits" / "new"
            with patch("prepare_backup_preflight.SIBLINGS", ()), patch(
                "prepare_backup_preflight.command_metadata", return_value={"returncode": 0, "stdout": ""}
            ):
                summary = preflight(root, output)
            self.assertFalse(summary["backup_created"])
            self.assertFalse(summary["source_payload_hashed"])
            self.assertEqual(summary["totals"]["logical_bytes"], len(b"original"))
            self.assertEqual(summary["errors"], [])
            self.assertEqual(data.read_bytes(), b"original")
            with gzip.open(output / "BACKUP_SOURCE_FILES.jsonl.gz", "rt") as stream:
                rows = [json.loads(line) for line in stream]
            self.assertFalse(any(r["path"].startswith(str(output)) for r in rows))
            self.assertTrue(all("sha256" not in r for r in rows))

    def test_overlapping_sources_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repository"
            root.mkdir()
            output = root / "deliverables" / "project_audits" / "new"
            with patch("prepare_backup_preflight.SIBLINGS", ("repository",)):
                with self.assertRaises(ValueError):
                    preflight(root, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
