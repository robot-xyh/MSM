"""Collect repository and document metadata without running experiment code."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
import subprocess
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args]).decode()


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def git_state(root: Path) -> dict:
    entries = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    changes = []
    index = 0
    while index < len(entries):
        value = entries[index]
        index += 1
        if not value:
            continue
        row = {"status": value[:2], "path": value[3:]}
        if "R" in value[:2] or "C" in value[:2]:
            row["old_path"] = entries[index]
            index += 1
        changes.append(row)
    return {
        "head": git(root, "rev-parse", "HEAD").strip(),
        "branch": git(root, "branch", "--show-current").strip(),
        "local_upstream_difference": git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").strip(),
        "remote_fetched_this_audit": False,
        "tracked_changes": sum(row["status"] != "??" for row in changes),
        "untracked_entries_including_nested_repositories": sum(row["status"] == "??" for row in changes),
        "staged_entries": sum(row["status"][0] not in " ?" for row in changes),
        "untracked_entries_excluding_this_audit": sum(row["status"] == "??" and not row["path"].startswith("deliverables/project_audits/") for row in changes),
        "changes_by_area": dict(Counter("/".join(row["path"].split("/")[:2]) for row in changes)),
        "changes": changes,
        "worktrees": git(root, "worktree", "list", "--porcelain"),
        "recent_commits": git(root, "log", "-15", "--date=iso-strict", "--format=%h %ad %s").splitlines(),
    }


def document_metadata(root: Path, path: Path) -> dict:
    word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    math = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    result = {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest(path)}
    with zipfile.ZipFile(path) as archive:
        result["zip_crc_failure"] = archive.testzip()
        names = set(archive.namelist())
        tree = ET.fromstring(archive.read("word/document.xml"))
        paragraphs = ["".join(t.text or "" for t in p.iter(word + "t")) for p in tree.iter(word + "p")]
        text = "\n".join(paragraphs)
        result["paragraphs"] = len(paragraphs)
        result["tables"] = len(list(tree.iter(word + "tbl")))
        result["equations"] = len(list(tree.iter(math + "oMath")))
        result["embedded_media"] = sum(name.startswith("word/media/") and not name.endswith("/") for name in names)
        result["numbered_headings"] = [s for s in paragraphs if re.match(r"^\d+(?:\.\d+)+\s", s)]
        missing = []
        external = []
        for name in names:
            if not name.endswith(".rels"):
                continue
            base = posixpath.dirname(posixpath.dirname(name))
            for relation in ET.fromstring(archive.read(name)):
                target = relation.attrib.get("Target", "")
                if relation.attrib.get("TargetMode") == "External":
                    external.append(target)
                    continue
                resolved = posixpath.normpath(posixpath.join(base, unquote(target))).lstrip("/")
                if resolved not in names:
                    missing.append({"relationship_file": name, "target": target})
        result["missing_internal_relationships"] = missing
        result["external_relationships"] = external
    markdown = path.with_suffix(".md")
    if markdown.exists():
        content = markdown.read_text()
        headings = [s.lstrip("# ").strip() for s in content.splitlines() if s.startswith("##")]
        image_paths = re.findall(r"!\[[^\]]*\]\(([^\n]+?)\)", content)
        absent = []
        for raw in image_paths:
            target = raw.strip().strip("<>")
            if re.match(r"^[a-zA-Z]+:", target):
                continue
            if not (markdown.parent / unquote(target.split("#", 1)[0])).exists():
                absent.append(target)
        result["markdown_pair"] = {
            "path": str(markdown.relative_to(root)),
            "sha256": digest(markdown),
            "headings": headings,
            "headings_not_verbatim_in_docx": [h for h in headings if h not in text],
            "inline_image_count": len(image_paths),
            "missing_inline_images": absent,
            "check_limit": "Headings and inline local image paths only; not semantic or rendered-layout equivalence.",
        }
    return result


def manifest_metadata(root: Path, path: Path) -> dict:
    manifest = json.loads(path.read_text())
    results = []

    def hashed_files(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
                yield value
            if isinstance(value.get("paths"), dict) and isinstance(value.get("sha256"), dict):
                for name, target in value["paths"].items():
                    if name in value["sha256"]:
                        yield {"path": target, "sha256": value["sha256"][name], "role": name}
            for nested in value.values():
                yield from hashed_files(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from hashed_files(nested)

    for item in hashed_files(manifest):
        candidate = Path(item["path"])
        resolution = "absolute"
        if not candidate.is_absolute():
            possible = [base / candidate for base in (root, path.parent)]
            existing = [p for p in possible if p.is_file()]
            if len(existing) > 1 and existing[0].resolve() != existing[1].resolve():
                results.append({"path": item["path"], "status": "ambiguous_relative_path"})
                continue
            candidate = existing[0] if existing else possible[0]
            resolution = "repository" if candidate == possible[0] else "manifest_parent"
        status = "missing"
        actual = None
        if candidate.is_file():
            actual = digest(candidate)
            status = "match" if actual == item["sha256"] else "mismatch"
        results.append({"path": item["path"], "role": item.get("role"), "resolved_path": str(candidate), "path_base": resolution, "expected": item["sha256"], "actual": actual, "status": status})
    return {
        "path": str(path.relative_to(root)), "sha256": digest(path),
        "source": manifest.get("source"), "runtime": manifest.get("runtime"),
        "reproduction": manifest.get("reproduction"),
        "legacy_provenance": {key: manifest.get(key) for key in ("git_revision", "working_tree_dirty", "command") if key in manifest},
        "check_limit": "Checks explicit path/sha256 records recursively; does not interpret every schema-specific hash field.",
        "input_check_counts": dict(Counter(row["status"] for row in results)),
        "input_checks": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    report = {
        "audit_time_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root), "scope": "Administrative evidence audit; no experiment execution, model loading, or capability validation.",
        "git": git_state(root),
    }
    paths = []
    for folder in ("deliverables/leadership_report", "deliverables/patents", "deliverables/project_proposals"):
        paths.extend(sorted((root / folder).glob("*.docx")))
    report["documents"] = []
    for path in paths:
        try:
            report["documents"].append(document_metadata(root, path))
        except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
            report["documents"].append({"path": str(path.relative_to(root)), "error": str(exc)})
    experiments = root / "research_modules/independent_experiments"
    relative_roots = (
        "dual_optical_online_benchmark/outputs/report_replay_20260819_v2",
        "center_terminal_cv_campaign/outputs/offline_search_100pct_cues_20260819",
        "center_terminal_cv_campaign/outputs/terminal_gnn_diagnostic_selection_20260819_v2",
        "center_terminal_cv_campaign/outputs/center_handover_sensor_error_20260820",
    )
    report["evidence_roots"] = []
    for relative in relative_roots:
        folder = experiments / relative
        entry = {"path": str(folder.relative_to(root)), "exists": folder.is_dir(), "top_level_files": [], "manifests": [], "csv_row_counts": {}}
        if folder.is_dir():
            entry["top_level_files"] = sorted(p.name for p in folder.iterdir())
            manifests = sorted(folder.glob("*manifest*.json")) + sorted((folder / "manifests").glob("*.json"))
            for path in manifests:
                entry["manifests"].append(manifest_metadata(root, path))
            for path in sorted(folder.glob("*.csv")):
                with path.open(newline="") as stream:
                    entry["csv_row_counts"][path.name] = sum(1 for _ in csv.DictReader(stream))
        report["evidence_roots"].append(entry)
    report["nested_repositories"] = []
    for folder in sorted((root / "paper").iterdir()):
        if folder.is_dir() and (folder / ".git").exists():
            report["nested_repositories"].append({"path": str(folder.relative_to(root)), "head": git(folder, "rev-parse", "HEAD").strip(), "status": git(folder, "status", "--short"), "remote": git(folder, "remote", "-v")})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "documents": len(report["documents"]), "tracked_changes": report["git"]["tracked_changes"], "untracked_entries": report["git"]["untracked_entries_including_nested_repositories"], "evidence_roots": [{"path": e["path"], "csv_rows": e["csv_row_counts"], "manifest_checks": [m["input_check_counts"] for m in e["manifests"]]} for e in report["evidence_roots"]]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
