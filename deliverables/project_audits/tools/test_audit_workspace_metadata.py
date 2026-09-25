"""Unit tests for the administrative metadata reader."""

import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from audit_workspace_metadata import digest, document_metadata, manifest_metadata


class MetadataTests(unittest.TestCase):
    def test_repository_and_manifest_relative_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "run"
            run.mkdir()
            data = run / "payload.bin"
            data.write_bytes(b"evidence")
            manifest = run / "manifest.json"
            manifest.write_text(json.dumps({"inputs": [
                {"path": "run/payload.bin", "sha256": digest(data)},
                {"path": "payload.bin", "sha256": digest(data)},
            ]}))
            result = manifest_metadata(root, manifest)
            self.assertEqual(result["input_check_counts"], {"match": 2})

    def test_named_hashes_and_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "run"
            run.mkdir()
            data = run / "payload.bin"
            data.write_bytes(b"evidence")
            manifest = run / "manifest.json"
            manifest.write_text(json.dumps({
                "paths": {"valid": "payload.bin", "changed": "payload.bin", "absent": "absent.bin"},
                "sha256": {"valid": digest(data), "changed": "0" * 64, "absent": "1" * 64},
            }))
            self.assertEqual(manifest_metadata(root, manifest)["input_check_counts"], {"match": 1, "mismatch": 1, "missing": 1})

    def test_ambiguous_base_is_not_silently_chosen(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "run"
            run.mkdir()
            (root / "payload").write_bytes(b"first")
            (run / "payload").write_bytes(b"second")
            manifest = run / "manifest.json"
            manifest.write_text(json.dumps({"inputs": [{"path": "payload", "sha256": "0" * 64}]}))
            self.assertEqual(manifest_metadata(root, manifest)["input_check_counts"], {"ambiguous_relative_path": 1})

    def test_word_relationship_and_markdown_heading(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "report.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>1.1 Current</w:t></w:r></w:p></w:body></w:document>')
                archive.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="image" Target="media/test.png"/><Relationship Id="r2" Type="image" Target="media/missing.png"/></Relationships>')
                archive.writestr("word/media/test.png", b"fixture")
            path.with_suffix(".md").write_text("## 1.1 Current\n## 1.2 Old\n![missing](missing.png)\n")
            result = document_metadata(root, path)
            self.assertIsNone(result["zip_crc_failure"])
            self.assertEqual(len(result["missing_internal_relationships"]), 1)
            self.assertEqual(result["markdown_pair"]["headings_not_verbatim_in_docx"], ["1.2 Old"])
            self.assertEqual(result["markdown_pair"]["missing_inline_images"], ["missing.png"])


if __name__ == "__main__":
    unittest.main()
