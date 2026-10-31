"""Preserve hash-attested evidence and inspect imports without executing it."""

from __future__ import annotations

import ast
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
EXP = ROOT / "research_modules/independent_experiments"
DUAL = EXP / "dual_optical_online_benchmark"
CENTER = EXP / "center_terminal_cv_campaign"
DUAL_RUN = DUAL / "outputs/report_replay_20260819_v2"
CENTER_RUN = CENTER / "outputs/center_handover_sensor_error_20260820"
SEARCH_RUN = CENTER / "outputs/offline_search_100pct_cues_20260819"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"empty register: {path}")
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def git(*args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, timeout=30, check=False
    )
    return result


def checked_git(*args: str) -> str:
    result = git(*args)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout.decode()


def python_file(stem: Path) -> Path | None:
    for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
        if candidate.is_file():
            return candidate.resolve()
    return None


def inspect_imports(path: Path, roots: list[Path]) -> tuple[list[dict], list[dict]]:
    """Conservative file-level imports, including unexecuted branches/functions."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    edges, dynamic = [], []

    def resolve_absolute(name: str) -> Path | None:
        for root in roots:
            found = python_file(root.joinpath(*name.split(".")))
            if found:
                return found
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [(item.name, resolve_absolute(item.name)) for item in node.names]
            else:
                name = "." * node.level + (node.module or "")
                if node.level:
                    base = path.parent
                    for _ in range(node.level - 1):
                        base = base.parent
                    stem = base.joinpath(*(node.module or "").split("."))
                    resolved = python_file(stem)
                else:
                    resolved = resolve_absolute(node.module or "")
                    stem = None
                names = [(name, resolved)]
                for item in node.names:
                    if item.name == "*":
                        continue
                    child = (
                        python_file(stem / item.name) if stem is not None
                        else resolve_absolute(f"{node.module}.{item.name}")
                    )
                    if child:
                        names.append((name + "." + item.name, child))
            for name, resolved in names:
                kind = "local" if resolved else (
                    "unresolved_relative" if name.startswith(".") else
                    "stdlib" if name.split(".")[0] in sys.stdlib_module_names
                    else "external_or_unresolved"
                )
                edges.append({"line": node.lineno, "import": name,
                              "target": str(resolved) if resolved else "", "kind": kind})
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name in {"__import__", "exec", "eval"} or name.split(".")[-1] in {
                "import_module", "spec_from_file_location"
            } or name.startswith("sys.path."):
                dynamic.append({"line": node.lineno, "call": name})
    return edges, dynamic


def local_closure(entry: Path, roots: list[Path], limit: int = 200):
    pending, visited, edges, dynamic = [entry], set(), [], []
    while pending:
        path = pending.pop().resolve()
        if path in visited:
            continue
        if not path.is_relative_to(ROOT / "research_modules"):
            raise ValueError(f"unexpected local source: {path}")
        visited.add(path)
        if len(visited) > limit:
            raise RuntimeError("static source budget exceeded")
        found, calls = inspect_imports(path, roots)
        for item in found:
            edges.append({"source": str(path.relative_to(ROOT)), **item})
            if item["target"]:
                target = Path(item["target"])
                pending.append(target)
        for item in calls:
            dynamic.append({"source": str(path.relative_to(ROOT)), **item})
        for parent in path.parents:
            if parent == ROOT / "research_modules" or not parent.is_relative_to(ROOT):
                break
            init = parent / "__init__.py"
            if init.is_file() and init != path:
                edges.append({"source": str(path.relative_to(ROOT)), "line": 0,
                              "import": "parent_package", "target": str(init), "kind": "local"})
                pending.append(init)
    for item in edges:
        if item["target"]:
            item["target"] = str(Path(item["target"]).relative_to(ROOT))
    return sorted(visited), edges, dynamic


def verified_payload(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError(f"historical hash mismatch: {path}")
    return data


def main() -> None:
    if (OUT / "PROVENANCE_FOLLOWUP.json").exists() or (OUT / "ATTESTED_EVIDENCE.zip").exists():
        raise SystemExit("Existing audit artifacts: use a new batch; nothing overwritten.")
    started = datetime.now(timezone.utc).isoformat()
    dual = read_json(DUAL_RUN / "reproduction_manifest.json")
    center = read_json(CENTER_RUN / "reproduction_manifest.json")
    center_index = read_json(CENTER_RUN / "source_snapshot/source_files.json")
    search = read_json(SEARCH_RUN / "reproduction_manifest.json")
    watched, attested, evidence, members, payloads = {}, [], {}, [], {}

    def watch(path: Path) -> bytes:
        data = path.read_bytes()
        watched[str(path.relative_to(ROOT))] = sha(data)
        return data

    def preserve(path: Path, name: str, expected: str | None, role: str):
        data = watch(path)
        if expected and sha(data) != expected:
            raise ValueError(f"historical hash mismatch: {path}")
        payloads[name] = data
        members.append({"member": name, "source": str(path.relative_to(ROOT)),
                        "role": role, "bytes": len(data), "sha256": sha(data),
                        "historical_expected_sha256": expected or "",
                        "attestation": "historical_hash_match" if expected else "current_capture_only"})

    for item in dual["inputs"]:
        if item["role"] == "source_file":
            path = ROOT / item["path"]
            preserve(path, "dual/" + item["path"], item["sha256"], "source")
            attested.append({"batch": "dual", "path": item["path"], "sha256": item["sha256"]})
    for item in center_index:
        path = CENTER_RUN / item["snapshot_path"]
        preserve(path, "center/" + item["repository_path"], item["sha256"], "source")
        attested.append({"batch": "center", "path": item["repository_path"], "sha256": item["sha256"]})
    for label, folder in (("dual", DUAL_RUN), ("center", CENTER_RUN), ("search", SEARCH_RUN)):
        preserve(folder / "reproduction_manifest.json", label + "/reproduction_manifest.json",
                 None, "historical_record_current_capture")
    for item in center["inputs"]:
        if item["role"] == "algorithm_source_snapshot" and item["path"].endswith(".py"):
            continue
        path = CENTER_RUN / item["path"]
        data = verified_payload(path, item["sha256"])
        watched[str(path.relative_to(ROOT))] = sha(data)
        evidence.setdefault("center_artifacts", []).append({**item, "bytes": len(data), "match": True})
        if item["role"] != "model":
            preserve(path, "center/" + item["path"], item["sha256"], item["role"])
    for key, item in (("protocol", center["scenario"]), ("environment", center["runtime"]["dependency_lock"])):
        path_key, hash_key = ("config_path", "config_sha256") if key == "protocol" else ("path", "sha256")
        preserve(CENTER_RUN / item[path_key], "center/" + item[path_key], item[hash_key], key)
    preserve(CENTER_RUN / "metrics_contract.json", "center/metrics_contract.json", None, "metric_record")
    preserve(DUAL_RUN / "campaign_config.json", "dual/campaign_config.json", None, "config_record")

    roots = [EXP, ROOT, ROOT / "research_modules"]
    entries = {
        "dual": DUAL / "report_matrix_replay.py",
        "center": CENTER / "exp_center_handover/run_error_matrix.py",
        "search": CENTER / "exp_search/run_offline_matrix.py",
    }
    versions, all_edges, dynamic_calls, closures = [], [], [], {}
    expected = {(r["batch"], r["path"]): r["sha256"] for r in attested}
    base = dual["source"]["git_commit"]
    if center["source"]["git_commit"] != base or search["git_revision"] != base:
        raise ValueError("unexpected differing bases")
    for label, entry in entries.items():
        files, edges, dynamic = local_closure(entry, roots)
        all_edges.extend({"batch": label, **row} for row in edges)
        dynamic_calls.extend({"batch": label, **row} for row in dynamic)
        rows = []
        for path in files:
            relative = str(path.relative_to(ROOT))
            current_hash = sha(watch(path))
            old = git("show", f"{base}:{relative}")
            old_hash = sha(old.stdout) if old.returncode == 0 else ""
            historical_hash = expected.get((label, relative), "")
            status = (
                "historical_file_hash_match" if historical_hash == current_hash else
                "historical_file_hash_mismatch" if historical_hash else
                "same_as_base_commit_only" if old_hash == current_hash else
                "different_from_base_commit" if old_hash else "absent_from_base_commit"
            )
            row = {"batch": label, "path": relative, "current_sha256": current_hash,
                   "historical_expected_sha256": historical_hash, "base_commit_sha256": old_hash,
                   "base_lookup_returncode": old.returncode, "status": status}
            rows.append(row)
        versions.extend(rows)
        closures[label] = {"entry": str(entry.relative_to(ROOT)), "local_file_count": len(files),
                           "status_counts": dict(Counter(r["status"] for r in rows)),
                           "dynamic_call_count": len(dynamic),
                           "external_imports": sorted({r["import"].split(".")[0] for r in edges
                                                       if r["kind"] == "external_or_unresolved"}),
                           "unresolved_relative": [r for r in edges if r["kind"] == "unresolved_relative"]}
    write_csv(OUT / "STATIC_SOURCE_REGISTER.csv", versions)
    write_csv(OUT / "STATIC_IMPORT_EDGES.csv", all_edges)
    write_json(OUT / "DYNAMIC_IMPORT_NOTES.json", dynamic_calls)

    history = []
    for path in [*entries.values(), CENTER / "exp_search/offline_replay.py"]:
        relative = str(path.relative_to(ROOT))
        log = checked_git("log", "--all", "--follow", "--format=%H|%aI|%s", "--", relative)
        commits = []
        for line in log.splitlines():
            commit, date, title = line.split("|", 2)
            blob = git("show", f"{commit}:{relative}")
            commits.append({"commit": commit, "author_date": date, "subject": title,
                            "file_sha256": sha(blob.stdout) if blob.returncode == 0 else None,
                            "matches_current": blob.returncode == 0 and sha(blob.stdout) == sha(path.read_bytes())})
        history.append({"path": relative, "history": commits})
    evidence["entry_histories"] = history

    configs = []
    for path in sorted((SEARCH_RUN / "runs").glob("*/evidence_manifest.json")):
        data = watch(path)
        item = json.loads(data)
        configs.append({"run_id": path.parent.name, "path": str(path.relative_to(ROOT)),
                        "sha256": sha(data), "config": item.get("config"),
                        "source_keys_present": sorted(set(item) & {
                            "source", "git_revision", "git_commit", "source_sha256", "source_snapshot"
                        })})
        preserve(path, "search/runs/" + path.parent.name + "/evidence_manifest.json", None, "config_record")
    patch = (CENTER_RUN / "source_snapshot/tracked_worktree.patch").read_text()
    evidence["search_config_evidence"] = {
        "count": len(configs), "records": configs,
        "center_patch_contains_search_entry": "exp_search/run_offline_matrix.py" in patch,
        "center_patch_contains_search_dependency": "exp_search/offline_replay.py" in patch,
        "search_scope": "entry-specific reachable Git history; 45 saved manifests; center frozen patch",
        "not_searched": "external backups, other hosts, private session history, unreachable Git objects",
    }

    report_names = [
        "双光电多目标轨迹配准与交汇定位试验报告_CN",
        "协同搜索试验报告_CN", "末端目标配准试验报告_CN",
        "中心航迹与拦截无人机目标配准试验报告_CN",
    ]
    for name in report_names:
        for suffix in (".md", ".docx"):
            watch(ROOT / "deliverables/leadership_report" / (name + suffix))
    with zipfile.ZipFile(OUT / "ATTESTED_EVIDENCE.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(OUT / "ATTESTED_EVIDENCE.zip") as archive:
        if archive.testzip() is not None:
            raise ValueError("archive CRC failure")
        for row in members:
            if sha(archive.read(row["member"])) != row["sha256"]:
                raise ValueError("archive hash mismatch")
    write_csv(OUT / "PRESERVED_MEMBERS.csv", members)
    unchanged = all(sha((ROOT / path).read_bytes()) == digest for path, digest in watched.items())
    if not unchanged:
        raise RuntimeError("input changed during audit")
    write_json(OUT / "INPUT_FINGERPRINTS.json", watched)
    result = {
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        "head": checked_git("rev-parse", "HEAD").strip(),
        "branch": checked_git("branch", "--show-current").strip(), "recorded_base": base,
        "scope": "metadata, literal static imports, byte hashes and saved configuration records only",
        "algorithm_execution": False, "model_loaded": False, "original_files_unchanged": unchanged,
        "watched_file_count": len(watched), "closures": closures,
        "preserved_source_count": len(attested), "preserved_member_count": len(members),
        "archive_bytes": (OUT / "ATTESTED_EVIDENCE.zip").stat().st_size,
        "archive_sha256": sha((OUT / "ATTESTED_EVIDENCE.zip").read_bytes()),
        "limits": [
            "Static imports include optional and unexecuted paths; they are not an execution trace.",
            "External/dynamic imports, resources and runtime resolution are not a verified dependency closure.",
            "Matching a dirty run's base commit does not attest that run's actual file.",
            "The new ZIP is an audit evidence copy, not the historical execution package or a full backup.",
            "No raw labels were rescored and no reproducibility run was performed.",
        ], **evidence,
    }
    write_json(OUT / "PROVENANCE_FOLLOWUP.json", result)
    print(json.dumps({key: result[key] for key in (
        "head", "closures", "preserved_source_count", "preserved_member_count",
        "archive_bytes", "original_files_unchanged", "watched_file_count"
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
