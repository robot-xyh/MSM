"""Apply explicit record checks to saved tables; never compute research metrics."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from audit_record_validation import read_strict_json
from audit_report_evidence import lookup, read_source, write_csv
from audit_workspace_metadata import digest


def run(root: Path, spec_path: Path, output: Path) -> dict:
    root, spec_path, output = root.resolve(), spec_path.resolve(), output.resolve()
    audit_root = root / "deliverables/project_audits"
    if output == audit_root or not output.is_relative_to(audit_root):
        raise ValueError("Output must be a new subdirectory of deliverables/project_audits")
    if output.exists():
        raise FileExistsError(output)
    spec_hash = digest(spec_path)
    spec = read_strict_json(spec_path)
    if (not isinstance(spec, dict) or spec.get("schema") != "saved-table-record-audit-v1"
            or not isinstance(spec.get("sources"), dict) or not spec["sources"]):
        raise ValueError("Expected a nonempty saved-table-record-audit-v1 sources mapping")

    results, files, missing, groups = [], [], [], []
    started = datetime.now(timezone.utc).isoformat()
    for name, config in spec["sources"].items():
        result = {"source": name, "status": "failed", "errors": [], "config": config}
        source_files = []
        try:
            if "record_contract" not in config:
                raise ValueError("An explicit record_contract is required")
            paths = config.get("paths", [config.get("path")])
            if not isinstance(paths, list) or not paths or any(not isinstance(p, str) or not p.strip() for p in paths):
                raise ValueError("Source paths must be a nonempty list")
            for relative in paths:
                path = (root / relative).resolve()
                if not path.is_relative_to(root) or path.is_relative_to(output):
                    raise ValueError(f"Source path outside repository or inside output: {relative}")
                source_files.append({"source": name, "path": relative, "before_sha256": digest(path)})
            source = read_source(root, config)
            validation = source["record_validation"]
            result.update(record_validation=validation, row_count=source["row_count"])
            expected = config.get("expected", {})
            if set(expected) - {"rows", "groups", "seeds_per_group"}:
                raise ValueError("Unknown expected-count option")
            if any(type(value) is not int or value < 0 for value in expected.values()):
                raise ValueError("Expected counts must be nonnegative integers")
            actual = {"rows": source["row_count"], "groups": len(validation["groups"])}
            for field in ("rows", "groups"):
                if field in expected and actual[field] != expected[field]:
                    result["errors"].append(f"{field}: expected {expected[field]}, got {actual[field]}")
            if "seeds_per_group" in expected and (not validation["groups"] or any(
                    group["distinct_seed_count"] != expected["seeds_per_group"] for group in validation["groups"])):
                result["errors"].append("seeds_per_group does not match the declared groups")

            contract = config["record_contract"]
            rows = source["rows"]
            columns = set().union(*(row.keys() for row in rows))
            checked = set(contract["unique_key"]) | set(contract.get("numeric_fields", []))
            result["unchecked_column_types"] = sorted(columns - checked)
            result["file_record_counts"] = dict(Counter(item["path"] for item in source["locations"]))
            seed_field = contract.get("seed_field")
            result["distinct_seed_ids_count"] = len({lookup(row, seed_field) for row in rows}) if seed_field else None
            for index, (row, location) in enumerate(zip(rows, source["locations"]), 1):
                for field in contract.get("nullable_fields", []):
                    value = lookup(row, field)
                    if value is None or (isinstance(value, str) and not value.strip()):
                        missing.append({"source": name, **location, "combined_record_index": index,
                                        "field": field, "classification": "allowed_missing",
                                        "record_key": {key: lookup(row, key) for key in contract["unique_key"]}})
            groups.extend({"source": name, **group} for group in validation["groups"])
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            result["errors"].append(str(exc))
        finally:
            for item in source_files:
                try:
                    item["after_sha256"] = digest(root / item["path"])
                except OSError:
                    item["after_sha256"] = None
                item["unchanged"] = item["before_sha256"] == item["after_sha256"]
                if not item["unchanged"]:
                    result["errors"].append(f"Source changed during check: {item['path']}")
            files.extend(source_files)
        result["status"] = "failed" if result["errors"] else "passed"
        results.append(result)

    spec_unchanged = digest(spec_path) == spec_hash
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    script_paths = [Path(__file__), Path(__file__).with_name("audit_record_validation.py"),
                    Path(__file__).with_name("audit_report_evidence.py"), Path(__file__).with_name("audit_workspace_metadata.py")]
    summary = {"schema": "saved-table-record-audit-result-v1", "started_at_utc": started,
               "finished_at_utc": datetime.now(timezone.utc).isoformat(),
               "passed": spec_unchanged and all(item["status"] == "passed" for item in results),
               "audit_head": revision.stdout.strip() if revision.returncode == 0 else None,
               "historical_execution_revision_inferred": False,
               "spec": str(spec_path), "spec_sha256": spec_hash, "spec_unchanged": spec_unchanged,
               "sources": results, "file_hash_checks": files,
               "allowed_missing_cell_count": len(missing),
               "audited_record_count": sum(item.get("row_count", 0) for item in results),
               "checker_files": [{"path": str(path.resolve()), "sha256": digest(path)} for path in script_paths],
               "scope": "Saved record structure and declared counts only. Rows may overlap across sources; not independent experiment counts.",
               "experiments_run": False, "metrics_recomputed": False, "source_writes_performed": False}
    encoded = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=False)
    (output / "VALIDATION_RECORD.json").write_text(encoded, encoding="utf-8")
    write_csv(output / "NULL_FIELD_LOCATIONS.csv", missing,
              ["source", "path", "selector", "combined_record_index", "field", "classification", "record_key"])
    write_csv(output / "GROUP_RECORD_COUNTS.csv", groups, ["source", "group", "record_count", "distinct_seed_count"])
    write_csv(output / "FILE_HASH_CHECKS.csv", files, ["source", "path", "before_sha256", "after_sha256", "unchanged"])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root, args.spec, args.output_dir)
    print(json.dumps({"passed": result["passed"], "sources": len(result["sources"]),
                      "audited_record_count": result["audited_record_count"],
                      "allowed_missing_cells": result["allowed_missing_cell_count"]}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
