"""Check only report text changes, retained payloads and rendered note text."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile

import pymupdf
from lxml import etree

from report_sync import ROOT, OUT, NS, sha, structure


def main():
    destination = OUT / "REPORT_VALIDATION.json"
    if destination.exists():
        raise SystemExit("Report validation already recorded.")
    before = json.loads((OUT / "REPORTS_BEFORE.json").read_text())
    spec = json.loads((OUT / "REPORT_TEXT_CHANGES.json").read_text())
    specs = {v["name"]: v for v in spec}
    results, rendered = [], []
    with ZipFile(OUT / "REPORTS_BEFORE.zip") as original_archive:
        for row in before["documents"]:
            path = ROOT / row["path"]
            old = original_archive.read(row["member"])
            if sha(old) != row["sha256"]:
                raise ValueError("original snapshot mismatch")
            data = path.read_bytes()
            item = {"path": row["path"], "before_sha256": row["sha256"], "after_sha256": sha(data)}
            if path.suffix == ".md":
                content = data.decode()
                item["table_lines_unchanged"] = row["table_lines"] == [s for s in content.splitlines() if s.startswith("|")]
                item["images_unchanged"] = row["images"] == re.findall(r"!\[[^\]]*\]\([^\n]+\)", content)
                if not item["table_lines_unchanged"] or not item["images_unchanged"]:
                    raise ValueError(f"Markdown table or image changed: {path}")
            else:
                with ZipFile(path) as z:
                    parts = {n: sha(z.read(n)) for n in z.namelist()}
                    changed = [n for n in parts if parts[n] != row["parts"].get(n)]
                    item["changed_parts"] = changed
                    if set(parts) != set(row["parts"]) or changed != ["word/document.xml"]:
                        raise ValueError(f"unexpected changed DOCX part: {path}")
                    xml = z.read("word/document.xml")
                    if structure(xml) != row["structure"]:
                        raise ValueError("table/drawing/section changed")
                    tree = etree.fromstring(xml)
                    flat = "".join(tree.xpath("//w:t/text()", namespaces=NS))
                    for op in specs[path.stem]["operations"]:
                        if op["kind"] != "replace" and flat.count(op["text"]) != 1:
                            raise ValueError("new note missing or duplicated")
                    item["tables_drawings_sections_unchanged"] = True
                pdf = OUT / "rendered_reports" / (path.stem + ".pdf")
                with pymupdf.open(pdf) as document:
                    page_texts = ["".join(page.get_text().split()) for page in document]
                    all_text = "".join(page_texts)
                    notes, preview_pages = [], []
                    for op in specs[path.stem]["operations"]:
                        fragments = ([op["text"]] if op["kind"] != "replace" else
                                     [r["new"] for r in op["replacements"]])
                        for fragment in fragments:
                            normalized = "".join(fragment.split())
                            if normalized not in all_text:
                                raise ValueError(f"rendered text missing: {path} {fragment[:20]}")
                            pages = [i + 1 for i, t in enumerate(page_texts) if normalized in t]
                            notes.append({"text_prefix": fragment[:32], "pages": pages})
                            preview_pages.extend(pages[:1])
                    preview_page = preview_pages[0]
                    image = OUT / "rendered_reports" / (path.stem + f"_p{preview_page:02d}.png")
                    document[preview_page - 1].get_pixmap(matrix=pymupdf.Matrix(1, 1)).save(image)
                    rendered.append({"path": str(pdf.relative_to(ROOT)), "page_count": len(document),
                                     "new_text_found": True, "notes": notes,
                                     "preview": str(image.relative_to(ROOT))})
            results.append(item)
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(OUT),
                            "-p", "test_report_sync.py", "-v"], cwd=ROOT,
                           capture_output=True, text=True, timeout=30)
    if tests.returncode:
        raise RuntimeError(tests.stderr)
    value = {"created_at": datetime.now(timezone.utc).isoformat(), "passed": True,
             "documents": results, "rendered": rendered,
             "unit_tests": tests.stdout + tests.stderr,
             "scope": "Text edits and structural integrity; rendering confirms new text is present, not a complete visual layout review."}
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"passed": True, "documents": len(results), "rendered": len(rendered)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
