"""Pure metadata tests, without research imports or environment installation."""

import unittest

from audit_material_gaps import dependency_evidence, metadata_fields


class MaterialGapTests(unittest.TestCase):
    def edge(self, module, kind="external_or_unresolved"):
        return {"batch": "toy", "import": module, "source": "sample.py", "line": "4", "kind": kind}

    def test_alias_maps_import_to_distribution(self):
        result = dependency_evidence([self.edge("sklearn.linear_model")], {"toy": {"scikit-learn": "1.0"}})
        self.assertEqual(result[0]["distribution"], "scikit-learn")
        self.assertEqual(result[0]["recorded_version"], "1.0")

    def test_missing_version_stays_missing(self):
        result = dependency_evidence([self.edge("sample_lib")], {})
        self.assertIsNone(result[0]["recorded_version"])
        self.assertFalse(result[0]["actual_runtime_import_proven"])

    def test_repeated_submodules_keep_witnesses_not_extra_packages(self):
        result = dependency_evidence([self.edge("sample_lib.one"), self.edge("sample_lib.two")], {})
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["static_witnesses"]), 2)

    def test_stdlib_and_local_imports_excluded(self):
        self.assertEqual(dependency_evidence([self.edge("json", "stdlib"), self.edge("local", "local")], {}), [])

    def test_nested_metadata_fields_detected(self):
        result = metadata_fields({"records": [{"environment": {"python_version": "3.x"}}]})
        self.assertEqual(result, ["records[0].environment", "records[0].environment.python_version"])

    def test_parameter_schema_and_trajectory_hash_are_not_code_provenance(self):
        self.assertEqual(metadata_fields({"schema_version": "v1", "config": {"seed": 1},
                                          "trajectory_source": {"sha256": "abc"}}), [])


if __name__ == "__main__":
    unittest.main()
