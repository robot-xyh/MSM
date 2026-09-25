#!/usr/bin/env python3
"""Polish LaTeX aligned environments and remove double backslashes."""

import glob
from pathlib import Path

def polish_file(p: Path):
    content = p.read_text(encoding="utf-8")
    orig = content
    content = content.replace("\\\\begin{aligned}", "\\begin{aligned}")
    content = content.replace("\\\\end{aligned}", "\\end{aligned}")
    content = content.replace("\\tag{6A} \\\n", "\\tag{6A} \\\\\n")
    content = content.replace("\\tag{6B} \\\n", "\\tag{6B} \\\\\n")
    content = content.replace("\\tag{6C} \\\n", "\\tag{6C} \\\\\n")
    if content != orig:
        p.write_text(content, encoding="utf-8")
        print(f"Polished: {p.name}")

if __name__ == "__main__":
    for f in Path("/home/linux/Documents/MSM/paper").glob("**/中文翻译/*.md"):
        polish_file(f)
