"""Artificial-file tests; no experiment modules are imported."""

import tempfile
from pathlib import Path
import unittest

from audit_provenance import inspect_imports, verified_payload


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.package = self.root / "sample"
        self.package.mkdir()
        (self.package / "__init__.py").write_text("raise RuntimeError('must not execute')\n")
        (self.package / "child.py").write_text("raise RuntimeError('must not execute')\n")
        self.entry = self.package / "entry.py"

    def inspect(self, source):
        self.entry.write_text(source)
        return inspect_imports(self.entry, [self.root])

    def test_relative_module(self):
        edges, _ = self.inspect("from .child import value\n")
        self.assertEqual(edges[0]["target"], str(self.package / "child.py"))

    def test_relative_package_child(self):
        edges, _ = self.inspect("from . import child\n")
        self.assertEqual({e["target"] for e in edges}, {
            str(self.package / "__init__.py"), str(self.package / "child.py")})

    def test_absolute_package_child(self):
        edges, _ = self.inspect("from sample import child\n")
        self.assertEqual(len(edges), 2)
        self.assertTrue(all(e["kind"] == "local" for e in edges))

    def test_unknown_relative(self):
        edges, _ = self.inspect("from .missing import value\n")
        self.assertEqual(edges[0]["kind"], "unresolved_relative")

    def test_stdlib_and_external(self):
        edges, _ = self.inspect("import json\nimport imaginary_external\n")
        self.assertEqual([e["kind"] for e in edges], ["stdlib", "external_or_unresolved"])

    def test_dynamic_call_not_executed(self):
        _, calls = self.inspect("__import__('unavailable')\nsys.path.insert(0, 'x')\n")
        self.assertEqual(len(calls), 2)

    def test_unexecuted_branch_included(self):
        edges, _ = self.inspect("if False:\n    import sample.child\n")
        self.assertEqual(edges[0]["kind"], "local")

    def test_model_eval_is_not_dynamic_import(self):
        _, calls = self.inspect("model.eval()\nmodel.cpu().eval()\n")
        self.assertEqual(calls, [])

    def test_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            verified_payload(self.package / "child.py", "0" * 64)


if __name__ == "__main__":
    unittest.main()
