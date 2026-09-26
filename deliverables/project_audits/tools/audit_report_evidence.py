"""Read-only document/evidence checks; writes new administrative metadata only."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from markdown_it import MarkdownIt

from audit_workspace_metadata import digest, manifest_metadata


WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", value)


def inline_text(token) -> str:
    return "".join(child.content if child.type not in {"softbreak", "hardbreak"}
                   else " " for child in (token.children or [])
                   if child.type in {"text", "code_inline", "softbreak", "hardbreak"})


def read_markdown(path: Path) -> dict:
    tokens = MarkdownIt("commonmark").enable("table").parse(path.read_text())
    result = {"headings": [], "paragraphs": [], "tables": [], "images": []}
    section = ""
    current = None
    row = None
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            section = inline_text(tokens[index + 1])
            result["headings"].append(section)
        elif token.type == "table_open":
            current = {"section": section, "line": token.map[0] + 1, "rows": [],
                       "index": len(result["tables"]) + 1}
        elif token.type == "tr_open":
            row = []
        elif token.type == "tr_close":
            current["rows"].append(row)
            row = None
        elif token.type == "table_close":
            result["tables"].append(current)
            current = None
        elif token.type == "inline":
            content = inline_text(token)
            if row is not None:
                row.append(content)
            elif content:
                result["paragraphs"].append(content)
            for child in token.children or []:
                if child.type == "image":
                    result["images"].append({"path": child.attrGet("src"),
                                             "caption": child.content,
                                             "line": token.map[0] + 1 if token.map else None})
    return result


def read_word(path: Path) -> dict:
    result = {"headings": [], "paragraphs": [], "tables": [], "media": []}
    with zipfile.ZipFile(path) as archive:
        tree = ET.fromstring(archive.read("word/document.xml"))
        body = tree.find(WORD + "body")
        section = ""
        for child in body:
            if child.tag == WORD + "p":
                content = "".join(node.text or "" for node in child.iter(WORD + "t"))
                style = child.find("./" + WORD + "pPr/" + WORD + "pStyle")
                style_name = style.get(WORD + "val", "") if style is not None else ""
                if content:
                    result["paragraphs"].append(content)
                if content and (style_name.lower().startswith("heading")
                                or re.match(r"^(?:\d+(?:\.\d+)*[. ]|[一二三四五六七八九十]+、)", content)):
                    section = content
                    result["headings"].append(content)
            elif child.tag == WORD + "tbl":
                rows = []
                for tr in child.findall(WORD + "tr"):
                    rows.append(["".join(node.text or "" for node in tc.iter(WORD + "t"))
                                 for tc in tr.findall(WORD + "tc")])
                result["tables"].append({"section": section, "line": None, "rows": rows,
                                         "index": len(result["tables"]) + 1})
        for name in sorted(archive.namelist()):
            if name.startswith("word/media/") and not name.endswith("/"):
                content = archive.read(name)
                result["media"].append({"member": name, "bytes": len(content),
                                        "sha256": hashlib.sha256(content).hexdigest()})
    return result


def table_signature(table: dict) -> tuple:
    return tuple(tuple(normalized(cell) for cell in row) for row in table["rows"])


def compare_documents(markdown: dict, word: dict) -> dict:
    word_counts = Counter(table_signature(table) for table in word["tables"])
    matched = []
    missing = []
    for table in markdown["tables"]:
        signature = table_signature(table)
        if word_counts[signature] > 0:
            word_counts[signature] -= 1
            matched.append(table["index"])
        else:
            missing.append({"index": table["index"], "section": table["section"],
                            "headers": table["rows"][0] if table["rows"] else []})
    word_texts = {normalized(value) for value in word["paragraphs"]}
    md_texts = {normalized(value) for value in markdown["paragraphs"]}
    return {
        "comparison_scope": "Extracted headings, paragraph text and table cells; not layout or semantic equivalence.",
        "markdown_heading_count": len(markdown["headings"]),
        "word_heading_count": len(word["headings"]),
        "markdown_headings_not_in_word": [value for value in markdown["headings"]
                                          if normalized(value) not in word_texts],
        "word_headings_not_in_markdown": [value for value in word["headings"]
                                          if normalized(value) not in md_texts],
        "markdown_table_count": len(markdown["tables"]),
        "word_table_count": len(word["tables"]),
        "identical_table_count": len(matched),
        "markdown_tables_not_identical_in_word": missing,
        "word_tables_not_identical_count": sum(word_counts.values()),
        "markdown_paragraphs_not_exact_in_word": sum(normalized(p) not in word_texts for p in markdown["paragraphs"]),
        "word_paragraphs_not_exact_in_markdown": sum(normalized(p) not in md_texts for p in word["paragraphs"]),
    }


def git_file_status(root: Path, path: Path, tracked: set[str]) -> str:
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return "outside_repository"
    if relative in tracked:
        return "tracked"
    check = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", relative],
                           check=False, capture_output=True)
    if check.returncode not in (0, 1):
        raise RuntimeError(check.stderr.decode())
    return "ignored" if check.returncode == 0 else "untracked"


def image_records(root: Path, document: Path, parsed: dict, tracked: set[str]) -> list[dict]:
    records = []
    for image in parsed["images"]:
        row = {"document": document.relative_to(root).as_posix(), **image}
        uri = urlsplit(image["path"])
        if uri.scheme or uri.netloc:
            row.update(status="external_not_fetched", git_status="not_applicable")
        else:
            target = (document.parent / unquote(uri.path)).resolve()
            row.update(resolved_path=str(target), status="present" if target.is_file() else "missing",
                       git_status=git_file_status(root, target, tracked))
            if target.is_file():
                row.update(sha256=digest(target), bytes=target.stat().st_size)
        records.append(row)
    return records


def lookup(value, pointer: str):
    if not pointer:
        return value
    for part in pointer.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def render_cell(row: dict, rule: dict) -> tuple[str, dict]:
    if "literal" in rule:
        return str(rule["literal"]), {}
    fields = rule.get("fields", [rule["field"]] if "field" in rule else [])
    values = {name: lookup(row, name) for name in fields}
    if "template" in rule:
        formats = rule.get("formats", [""] * len(fields))
        parts = [format(float(values[name]), fmt) if fmt else str(values[name])
                 for name, fmt in zip(fields, formats)]
        return rule["template"].format(*parts), values
    value = values[fields[0]]
    if "map" in rule:
        value = rule["map"][str(value)]
    if "format" in rule:
        value = format(float(value), rule["format"])
    return str(value) + rule.get("suffix", ""), values


def check_table(document: str, table: dict, binding: dict, sources: dict) -> list[dict]:
    source = sources[binding["source"]]
    candidates = [(index, row) for index, row in enumerate(source["rows"])
                  if all(lookup(row, key) == value for key, value in binding.get("where", {}).items())]
    columns = table["rows"][0]
    rules = binding["columns"]
    checks = []
    for row_number, report_row in enumerate(table["rows"][1:], 1):
        if len(report_row) != len(columns):
            raise ValueError(f"Malformed table in {document}: {table['index']}")
        cells = dict(zip(columns, report_row))
        if cells.get(columns[0]) in binding.get("skip_rows", []):
            continue
        row_rules = binding.get("row_rules", {}).get(cells[columns[0]])
        selected_rules = {columns[1]: row_rules} if row_rules else rules
        matches = [(index, row) for index, row in candidates
                   if all(normalized(render_cell(row, rules[key])[0]) == normalized(cells[key])
                          for key in binding.get("keys", []))]
        for column, rule in selected_rules.items():
            if column not in cells or column in binding.get("keys", []):
                continue
            record = {"document": document, "table_index": table["index"],
                      "section": table["section"], "table_line": table["line"],
                      "row": row_number, "column": column, "reported": cells[column],
                      "source": source["path"], "selector": source.get("selector", ""),
                      "source_row": None, "source_fields": [], "source_values": {},
                      "expected": None, "status": "missing_source_row"}
            if len(matches) == 1:
                source_index, original = matches[0]
                expected, values = render_cell(original, rule)
                location = source["locations"][source_index]
                record.update(source_row=source_index, source_fields=list(values),
                              source=location["path"], selector=location["selector"],
                              source_values=values, expected=expected,
                              status="match" if normalized(expected) == normalized(cells[column]) else "mismatch")
            elif len(matches) > 1:
                record["status"] = "ambiguous_source_rows"
            checks.append(record)
    return checks


def read_source(root: Path, config: dict) -> dict:
    rows, locations, files = [], [], []
    for name in config.get("paths", [config.get("path")]):
        path = root / name
        files.append({"path": name, "sha256": digest(path)})
        if config["kind"] == "csv":
            with path.open(encoding="utf-8-sig", newline="") as stream:
                items = list(csv.DictReader(stream))
            rows.extend(items)
            locations.extend({"path": name, "selector": f"data_row:{index + 1}"}
                             for index in range(len(items)))
        else:
            content = json.loads(path.read_text())
            for selector in config.get("selectors", [config.get("selector", "")]):
                value = lookup(content, selector)
                items = value if isinstance(value, list) else [value]
                rows.extend(items)
                locations.extend({"path": name, "selector": f"{selector}.{index}".lstrip(".")
                                  if isinstance(value, list) else selector}
                                 for index in range(len(items)))
    return {**config, "path": files[0]["path"], "files": files, "row_count": len(rows),
            "rows": rows, "locations": locations}


def expand_bindings(spec: dict) -> list[dict]:
    result = []
    for entry in spec["bindings"]:
        template = spec.get("templates", {}).get(entry.get("template"), {})
        binding = {**template, **entry}
        binding["columns"] = {**template.get("columns", {}), **entry.get("columns", {})}
        stem = spec["reports"][entry["report"]]
        for suffix in entry.get("formats", ["md", "docx"]):
            result.append({**binding, "document": stem + "." + suffix})
    return result


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list))
                             else value for key, value in row.items()})


def run(root: Path, spec_path: Path, output: Path, *, check_only: bool = False) -> dict:
    root = root.resolve()
    output = output.resolve()
    if not output.is_relative_to(root / "deliverables/project_audits"):
        raise ValueError("Output must be a new directory under deliverables/project_audits.")
    if output.exists():
        raise FileExistsError(output)
    spec = json.loads(spec_path.read_text())
    bindings = expand_bindings(spec)
    snapshot = json.loads((root / spec["document_snapshot"]).read_text())
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    tracked = set(subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"]).decode().split("\0"))
    sources = {key: read_source(root, value) for key, value in spec["sources"].items()}
    checks, images, documents, comparisons, tables = [], [], [], [], []
    all_media = []
    for markdown_path in [item["markdown_pair"]["path"] for item in snapshot["documents"]
                          if item.get("markdown_pair")]:
        md_path = root / markdown_path
        word_path = md_path.with_suffix(".docx")
        markdown = read_markdown(md_path)
        word = read_word(word_path)
        images.extend(image_records(root, md_path, markdown, tracked))
        comparisons.append({"markdown": markdown_path, "word": word_path.relative_to(root).as_posix(),
                            **compare_documents(markdown, word)})
        for member in word["media"]:
            all_media.append({"document": word_path.relative_to(root).as_posix(), **member})
        for path, parsed in ((md_path, markdown), (word_path, word)):
            name = path.relative_to(root).as_posix()
            documents.append({"path": name, "sha256": digest(path), "table_count": len(parsed["tables"]),
                              "heading_count": len(parsed["headings"])})
            for table in parsed["tables"]:
                selected = [binding for binding in bindings
                            if binding["document"] == name
                            and table["section"].startswith(binding.get("section_prefix", ""))
                            and all(header in table["rows"][0] for header in binding["headers"])]
                if len(selected) > 1:
                    raise ValueError(f"Ambiguous table binding: {name}, {table['index']}")
                table_checks = check_table(name, table, selected[0], sources) if selected else []
                checks.extend(table_checks)
                tables.append({"document": name, "index": table["index"], "section": table["section"],
                               "line": table["line"], "headers": table["rows"][0],
                               "data_rows": len(table["rows"]) - 1,
                               "source": sources[selected[0]["source"]]["path"] if selected else None,
                               "checked_cells": len(table_checks),
                               "check_counts": dict(Counter(item["status"] for item in table_checks)),
                               "status": "source_bound" if selected else "not_bound"})
    for member in all_media:
        member["matching_markdown_images"] = sorted({row["resolved_path"] for row in images
                                                     if row.get("sha256") == member["sha256"]})
    manifests = [manifest_metadata(root, root / path) for path in spec.get("manifests", [])]
    fingerprints = {row["path"]: row["sha256"] for row in documents}
    fingerprints.update({item["path"]: item["sha256"] for source in sources.values() for item in source["files"]})
    changed = [path for path, sha in fingerprints.items() if digest(root / path) != sha]
    if changed:
        raise RuntimeError(f"Sources changed during read: {changed}")
    summary = {
        "schema": "msm-report-evidence-index-v1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "audit_head": head, "historical_execution_revision_inferred_from_audit_head": False,
        "spec": str(spec_path.resolve()), "spec_sha256": digest(spec_path),
        "scope": "Read existing reports and saved summaries only; no simulation, model loading, rescoring, or report rewriting.",
        "documents": documents, "document_comparisons": comparisons, "tables": tables,
        "sources": {key: {k: v for k, v in value.items() if k not in {"rows", "locations"}} for key, value in sources.items()},
        "manifests": manifests, "embedded_media": all_media,
        "counts": {"documents": len(documents), "table_cells": len(checks),
                   "cell_statuses": dict(Counter(item["status"] for item in checks)),
                   "image_references": len(images),
                   "image_statuses": dict(Counter(item["status"] for item in images)),
                   "image_git_statuses": dict(Counter(item["git_status"] for item in images))},
        "boundaries": ["Table equality verifies transcription, not experimental validity.",
                       "Unbound tables and prose conclusions require separate review.",
                       "Images are checked by path and bytes, not by chart interpretation or rendered layout.",
                       "Current content hashes do not establish historical execution provenance."]}
    if not check_only:
        output.mkdir(parents=True, exist_ok=False)
        (output / "REPORT_EVIDENCE_INDEX.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        write_csv(output / "TABLE_VALUE_CHECKS.csv", checks,
                  ["document", "table_index", "section", "table_line", "row", "column", "reported",
                   "source", "selector", "source_row", "source_fields", "source_values", "expected", "status"])
        write_csv(output / "IMAGE_ASSET_REGISTER.csv", images,
                  ["document", "line", "caption", "path", "resolved_path", "status", "git_status", "sha256", "bytes"])
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    run(args.root, args.spec, args.output_dir, check_only=args.check_only)


if __name__ == "__main__":
    main()
