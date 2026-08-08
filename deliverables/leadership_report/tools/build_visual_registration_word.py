#!/usr/bin/env python3
"""Build the visual-registration Word report through the shared builder."""

from __future__ import annotations

from build_search_visual_assignment_word import REPORTS, build_document, validate_document


def main() -> None:
    spec = next(item for item in REPORTS if item.source_name == "VISUAL_REGISTRATION_SECTION_CN.md")
    output = build_document(spec)
    metrics = validate_document(spec, output)
    print(
        f"{output.name}: paragraphs={metrics['paragraphs']}, "
        f"images={metrics['images']}, bytes={metrics['bytes']}"
    )


if __name__ == "__main__":
    main()
