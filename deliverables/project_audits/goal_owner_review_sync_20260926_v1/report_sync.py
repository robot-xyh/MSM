"""Capture originals and make narrowly scoped OOXML text changes only."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from lxml import etree


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
REPORTS = ROOT / "deliverables/leadership_report"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_new(path, obj):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def text(element):
    return "".join(element.xpath(".//w:t/text()", namespaces=NS))


def structure(data):
    doc = etree.fromstring(data)
    return {
        "table_sha256": [sha(etree.tostring(t, method="c14n"))
                         for t in doc.xpath("//w:tbl", namespaces=NS)],
        "drawing_sha256": [sha(etree.tostring(t, method="c14n"))
                           for t in doc.xpath("//w:drawing", namespaces=NS)],
        "section_sha256": [sha(etree.tostring(t, method="c14n"))
                           for t in doc.xpath("//w:sectPr", namespaces=NS)],
    }


def capture(spec):
    destination = OUT / "REPORTS_BEFORE.zip"
    if destination.exists() or (OUT / "REPORTS_BEFORE.json").exists():
        raise SystemExit("Original capture already exists; refusing overwrite.")
    records = []
    with ZipFile(destination, "x", compression=ZIP_DEFLATED) as archive:
        for item in spec:
            for ext in (".md", ".docx"):
                path = REPORTS / (item["name"] + ext)
                payload = path.read_bytes()
                archive.writestr(path.name, payload)
                record = {"path": str(path.relative_to(ROOT)), "member": path.name,
                          "sha256": sha(payload), "bytes": len(payload)}
                if ext == ".md":
                    lines = payload.decode().splitlines()
                    record["table_lines"] = [s for s in lines if s.startswith("|")]
                    record["images"] = re.findall(r"!\[[^\]]*\]\([^\n]+\)", payload.decode())
                else:
                    with ZipFile(path) as z:
                        record["parts"] = {n: sha(z.read(n)) for n in z.namelist()}
                        record["structure"] = structure(z.read("word/document.xml"))
                records.append(record)
    save_new(OUT / "REPORTS_BEFORE.json", {
        "archive_sha256": sha(destination.read_bytes()), "documents": records,
        "scope": "Original eight documents before this batch's edits; not a project backup."
    })
    print(f"Captured {len(records)} original documents.")


def replace_run_text(paragraph, old, new):
    nodes = paragraph.xpath(".//w:t", namespaces=NS)
    value = "".join(n.text or "" for n in nodes)
    if value.count(old) != 1:
        raise ValueError(f"expected unique replacement: {old}")
    start = value.index(old)
    end = start + len(old)
    offset, inserted = 0, False
    for node in nodes:
        value = node.text or ""
        right = offset + len(value)
        if offset < end and right > start:
            prefix = value[:max(0, start - offset)]
            suffix = value[max(0, end - offset):]
            node.text = prefix + ("" if inserted else new) + suffix
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            inserted = True
        offset = right


def insert_paragraph(anchor, value, before=False):
    paragraph = etree.Element(W + "p")
    properties = anchor.find(W + "pPr")
    if properties is not None:
        paragraph.append(copy.deepcopy(properties))
    run = etree.SubElement(paragraph, W + "r")
    run_properties = anchor.find(".//" + W + "rPr")
    if run_properties is not None:
        run.append(copy.deepcopy(run_properties))
    node = etree.SubElement(run, W + "t")
    node.text = value
    if before:
        anchor.addprevious(paragraph)
    else:
        anchor.addnext(paragraph)


def apply_docx(spec):
    if (OUT / "REPORT_SYNC_RESULT.json").exists():
        raise SystemExit("Synchronization already recorded; refusing repeat.")
    before = json.loads((OUT / "REPORTS_BEFORE.json").read_text())
    frozen = {r["path"]: r for r in before["documents"]}
    planned = []
    for item in spec:
        path = REPORTS / (item["name"] + ".docx")
        original = frozen[str(path.relative_to(ROOT))]
        if sha(path.read_bytes()) != original["sha256"]:
            raise ValueError(f"document changed after capture: {path}")
        with ZipFile(path) as z:
            parts = [(info, z.read(info.filename)) for info in z.infolist()]
        xml = dict((i.filename, d) for i, d in parts)["word/document.xml"]
        doc = etree.fromstring(xml)
        for operation in item["operations"]:
            found = [p for p in doc.xpath("/w:document/w:body/w:p", namespaces=NS)
                     if operation["anchor"] in text(p)]
            if len(found) != 1:
                raise ValueError(f"ambiguous paragraph: {item['name']} {operation['anchor']}")
            paragraph = found[0]
            if operation["kind"] == "replace":
                for replacement in operation["replacements"]:
                    replace_run_text(paragraph, replacement["old"], replacement["new"])
            else:
                insert_paragraph(paragraph, operation["text"], operation["kind"] == "insert_before")
        modified = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
        if structure(modified) != original["structure"]:
            raise ValueError(f"table, drawing or page settings changed: {path}")
        planned.append((path, parts, modified, item))
    results = []
    for path, parts, modified, item in planned:
        with tempfile.NamedTemporaryFile(suffix=".docx", dir=OUT, delete=False) as handle:
            temp = Path(handle.name)
        try:
            with ZipFile(temp, "w") as z:
                for info, data in parts:
                    z.writestr(info, modified if info.filename == "word/document.xml" else data)
            with ZipFile(temp) as z:
                if z.testzip() is not None:
                    raise ValueError("DOCX CRC error")
            temp.replace(path)
        finally:
            if temp.exists():
                temp.unlink()
        results.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes()),
                        "operation_count": len(item["operations"]), "changed_part": "word/document.xml"})
    save_new(OUT / "REPORT_SYNC_RESULT.json", results)
    print(f"Updated text in {len(results)} Word documents; tables and images preserved.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "apply-docx"))
    args = parser.parse_args()
    spec = json.loads((OUT / "REPORT_TEXT_CHANGES.json").read_text())
    if args.action == "capture":
        capture(spec)
    else:
        apply_docx(spec)


if __name__ == "__main__":
    main()
