#!/usr/bin/env python3
"""Regenerate the visual-registration figures from the shared report builder."""

from __future__ import annotations

from PIL import Image

from build_search_visual_assignment_figures import (
    build_closed_loop,
    build_sparse_registration,
)


def main() -> None:
    for builder in (build_sparse_registration, build_closed_loop):
        path = builder()
        with Image.open(path) as image:
            print(f"{path.name}: {image.width}x{image.height}, dpi={image.info.get('dpi')}")


if __name__ == "__main__":
    main()
