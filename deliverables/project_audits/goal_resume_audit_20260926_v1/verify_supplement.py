"""Validate audit tables and inspect saved provenance without running algorithms."""

import csv
import hashlib
import json
from pathlib import Path
import subprocess


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    with (OUT / "GOAL_REQUIREMENT_EVIDENCE.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 60
    assert len({r["requirement_id"] for r in rows}) == 60
    for row in rows:
        assert None not in row and all(v is not None for v in row.values()), row
        assert row["status"] in {"已完成", "部分完成", "未完成", "证据不足"}, row
        for path in row["existing_implementation"].split(";"):
            assert (ROOT / path).exists(), path
    lines = ["# 原Goal逐项证据明细", "", "核查日期：2026年9月26日。原文出处中的附件1、附件2及E01至E12见[主报告](原Goal逐项状态对照_CN.md)。本表由同目录CSV生成；历史结果没有在本轮重新运行。", "", "| 编号与原文位置 | 原要求 | 已有实现 | 原始结果与证据 | 后续变化 | 当前状态 | 未完成事项 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        links = "；".join(f"[{p.rsplit('/', 1)[-1]}]({ROOT / p})" for p in r["existing_implementation"].split(";"))
        cells = [r["requirement_id"] + "：" + r["original_origin"], r["requirement"], links, r["original_result"] + "（" + r["evidence"] + "）", r["subsequent_change"], r["status"], r["outstanding"]]
        lines.append("| " + " | ".join(v.replace("|", "\\|") for v in cells) + " |")
    (OUT / "逐项证据明细_CN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    base = ROOT / "research_modules/airsim_runtime/baselines/d5_long_range_20target_20260810"
    manifest = json.loads((base / "baseline_manifest.json").read_text())
    fixture_checks = []
    for filename, expected in manifest["frozen_fixture_sha256"].items():
        actual = sha(base / filename)
        fixture_checks.append({"path": str(base / filename), "expected": expected, "actual": actual, "match": actual == expected})
    original_checks = []
    for filename, expected in manifest["source_artifact_sha256"].items():
        path = Path(manifest["source_directory"]) / filename
        actual = sha(path) if path.is_file() else None
        original_checks.append({"path": str(path), "expected": expected, "actual": actual, "match": actual == expected})
    inventory_rel = "research_modules/d2_data_association/docs/formal_r0_identity_causal_pack_summary_20260731/artifact_inventory.json"
    first_blob = subprocess.check_output(["git", "show", "5d5c174:" + inventory_rel], cwd=ROOT)
    source_status = json.loads((OUT / "SOURCE_DIRECTORY_STATUS.json").read_text())
    source_audit = json.loads(Path("/home/linux/Documents/MSM-source-audit-result-20260803-v3/source_audit.json").read_text())
    source_explanations = []
    payload_checks = []
    for source in source_status:
        result = Path(source["source_root"]) / "generation_result.json"
        historical = source_audit["sources"][source["module"]]
        inventory = json.loads(result.read_text())["artifact_inventory"]
        module_checks = []
        for item in inventory["files"]:
            path = Path(source["source_root"]) / item["path"]
            assert path.resolve().is_relative_to(Path(source["source_root"]).resolve())
            actual = sha(path) if path.is_file() else ""
            actual_size = path.stat().st_size if path.is_file() else -1
            expected = item["sha256"].removeprefix("sha256:")
            module_checks.append({"module": source["module"], "path": str(path), "expected_bytes": item["size_bytes"], "actual_bytes": actual_size, "expected_sha256": expected, "actual_sha256": actual, "match": actual == expected and actual_size == item["size_bytes"]})
        payload_checks.extend(module_checks)
        source_explanations.append({"module": source["module"], "extra_file_count": source["file_count_now"] - source["historical_file_count"], "extra_bytes": source["bytes_now"] - source["historical_bytes"], "generation_result_bytes": result.stat().st_size, "historical_source_bytes_read_scope": historical["source_bytes_read_scope"], "current_total_equals_historical_read_scope": source["bytes_now"] == historical["source_bytes_read_scope"], "manifest_tree_matches_historical_audit": inventory["tree_sha256"] == historical["inventory_tree_sha256"], "inventory_members_checked": len(module_checks), "inventory_member_matches": sum(x["match"] for x in module_checks), "interpretation": "Inventory members byte-hashed against generation_result; semantic leakage and model quality audit not repeated."})
        print(f"{source['module']}: {len(module_checks)} inventory files hashed", flush=True)
    with (OUT / "SOURCE_PAYLOAD_HASH_CHECKS.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(payload_checks[0]))
        writer.writeheader()
        writer.writerows(payload_checks)
    imports = json.loads((OUT / "STATIC_IMPORT_EVIDENCE.json").read_text())["imports"]
    direct = [r for r in imports if r["file"].startswith("research_modules/scalable_3d_simulation/") and "independent_experiments" in r["import"]]
    supplemental = {"requirement_rows": len(rows), "goal_query_current": None, "goal_query_note": "Current get_goal call returned goal=null during this audit", "baseline_manifest_sha256": sha(base / "baseline_manifest.json"), "baseline_fixture_checks": fixture_checks, "baseline_original_artifact_checks": original_checks, "first_committed_inventory_sha256": hashlib.sha256(first_blob).hexdigest(), "cited_inventory_sha256_in_historical_report": "c9bf5e479526cded07aa3d170540aa389b8083af3ec801496f41d620d4ffb68f", "source_directory_size_explanations": source_explanations, "scalable_direct_independent_imports": direct, "static_import_parse_errors": [r for r in imports if r["line"] == 0], "limitations": ["No dynamic execution proof inferred from imports", "Source payload byte hashes checked but semantic leakage audit not repeated", "No remote artifact search", "Current goal query is not a historical completion decision"], "additional_plan_hash_search": {"roots": ["/home/linux/Documents", "/home/linux/Downloads", "/dev/shm"], "patterns": ["*manifest*.json", "*plan*.json", "*aggregate*.json", "*SHA256*"], "query": "b922ff5f95864345efa583da7256935694e5c675529989a659716522a0d7590e", "match_count": 0, "exit_code": 2, "limitation": "Two unrelated PX4 mavlink directories unreadable; see ARCHIVE_SEARCH.json"}}
    (OUT / "SUPPLEMENTAL_CHECKS.json").write_text(json.dumps(supplemental, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"requirements": len(rows), "fixture_matches": sum(r["match"] for r in fixture_checks), "original_artifact_matches": sum(r["match"] for r in original_checks), "static_main_imports_of_independent_packages": len(direct), "parse_errors": len(supplemental["static_import_parse_errors"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
