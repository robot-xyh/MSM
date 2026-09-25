#!/usr/bin/env python3
"""Thoroughly fix all LaTeX keywords and math expressions across all Markdown files using direct string replacement."""

import os
from pathlib import Path

# Direct string replacements
DIRECT_REPLACEMENTS = [
    # Broken environments
    ("egin{aligned}", r"\begin{aligned}"),
    ("end{aligned}", r"\end{aligned}"),
    (r"\f\forall", r"\forall"),
    (r"\f \forall", r"\forall"),
    
    # Broken math symbols
    ("pprox", r"\approx"),
    (r"\\approx", r"\approx"),
    (r"\\forall", r"\forall"),
    (r"\\exists", r"\exists"),
    (r"\\beta", r"\beta"),
    (r"\\alpha", r"\alpha"),
    (r"\\theta", r"\theta"),
    (r"\\tau", r"\tau"),
    (r"\\rho", r"\rho"),
    (r"\\phi", r"\phi"),
    (r"\\psi", r"\psi"),
    (r"\\omega", r"\omega"),
    (r"\\sigma", r"\sigma"),
    (r"\\lambda", r"\lambda"),
    (r"\\gamma", r"\gamma"),
    (r"\\delta", r"\delta"),
    (r"\\epsilon", r"\epsilon"),
    (r"\\varepsilon", r"\varepsilon"),
    (r"\\zeta", r"\zeta"),
    (r"\\eta", r"\eta"),
    (r"\\mu", r"\mu"),
    (r"\\nu", r"\nu"),
    (r"\\xi", r"\xi"),
    (r"\\pi", r"\pi"),
    
    # Broken latex formatting commands
    (r"\\frac", r"\frac"),
    (r"\\text", r"\text"),
    (r"\\tag", r"\tag"),
    (r"\\mathbf", r"\mathbf"),
    (r"\\mathcal", r"\mathcal"),
    (r"\\mathbb", r"\mathbb"),
    (r"\\mathrm", r"\mathrm"),
    (r"\\sum", r"\sum"),
    (r"\\int", r"\int"),
    (r"\\infty", r"\infty"),
    (r"\\partial", r"\partial"),
    (r"\\nabla", r"\nabla"),
    (r"\\times", r"\times"),
    (r"\\cdot", r"\cdot"),
    (r"\\dots", r"\dots"),
    (r"\\le", r"\le"),
    (r"\\ge", r"\ge"),
    (r"\\ne", r"\ne"),
    (r"\\in", r"\in"),
    (r"\\notin", r"\notin"),
    (r"\\subset", r"\subset"),
    (r"\\subseteq", r"\subseteq"),
    (r"\\left", r"\left"),
    (r"\\right", r"\right"),
    (r"\\quad", r"\quad"),
    (r"\\qquad", r"\qquad"),
    
    # Specific typo cleanups
    (r"\text{ g}", r"\text{ g}"),
    (r"\text{ rad/s}", r"\text{ rad/s}"),
    (r"\text{ m}", r"\text{ m}"),
    (r"\text{ s}", r"\text{ s}"),
]

def clean_file(p: Path):
    content = p.read_text(encoding="utf-8", errors="ignore")
    orig = content
    
    # 1. Clean control bytes
    chars = []
    for c in content:
        code = ord(c)
        if code < 32 and c not in ('\n', '\r', '\t'):
            continue
        chars.append(c)
    content = "".join(chars)
    
    # 2. Apply direct replacements
    for src, dst in DIRECT_REPLACEMENTS:
        content = content.replace(src, dst)
        
    if content != orig:
        p.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"Fixed: {p.name}")

if __name__ == "__main__":
    for f in sorted(Path("/home/linux/Documents/MSM/paper").glob("**/中文翻译/*.md")):
        clean_file(f)
