#!/usr/bin/env python3
"""Clean and sanitize LaTeX syntax and remove corrupt escape codes from Markdown files."""

import glob
import re
from pathlib import Path

# Mapping of corrupted strings (caused by escape sequence interpretation) to proper LaTeX
REPLACEMENTS = [
    ("\t", " "),  # Convert literal tabs to spaces
    ("\x0c", " "), # Convert literal form feeds
    ("rac{", r"\frac{"),
    (r"\frac", r"\frac"),
    (r"\\frac", r"\frac"),
    (r"\text", r"\text"),
    (r"\\text", r"\text"),
    (r"\tag", r"\tag"),
    (r"\\tag", r"\tag"),
    (r"\tau", r"\tau"),
    (r"\\tau", r"\tau"),
    (r"\theta", r"\theta"),
    (r"\\theta", r"\theta"),
    (r"\times", r"\times"),
    (r"\\times", r"\times"),
    (r"\forall", r"\forall"),
    (r"\\forall", r"\forall"),
    (r"\exists", r"\exists"),
    (r"\\exists", r"\exists"),
    (r"\mathbb", r"\mathbb"),
    (r"\\mathbb", r"\mathbb"),
    (r"\mathbf", r"\mathbf"),
    (r"\\mathbf", r"\mathbf"),
    (r"\mathcal", r"\mathcal"),
    (r"\\mathcal", r"\mathcal"),
    (r"\mathrm", r"\mathrm"),
    (r"\\mathrm", r"\mathrm"),
]

def clean_file(file_path: Path):
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    orig = content
    
    # 1. Clean control bytes
    cleaned_chars = []
    for ch in content:
        code = ord(ch)
        if code < 32 and ch not in ('\n', '\r', '\t'):
            continue
        cleaned_chars.append(ch)
    content = "".join(cleaned_chars)
    
    # 2. Fix broken LaTeX patterns
    # Replace literal tab followed by latex commands
    content = content.replace("\text{", r"\text{")
    content = content.replace("\tag{", r"\tag{")
    content = content.replace("\theta", r"\theta")
    content = content.replace("\tau", r"\tau")
    content = content.replace("\times", r"\times")
    content = content.replace(" orall ", r" \forall ")
    content = content.replace("orall t", r"\forall t")
    content = content.replace("	ext{", r"\text{")
    content = content.replace("	ag{", r"\tag{")
    content = content.replace("	heta", r"\theta")
    content = content.replace("	au", r"\tau")
    content = content.replace("	imes", r"\times")
    content = content.replace("	op", r"\top")
    content = content.replace("	ilde", r"\tilde")
    
    # Fix double backslashes before common latex keywords in equations
    content = re.sub(r'\\\\(mathbf|mathcal|mathbb|mathrm|frac|text|tag|theta|tau|omega|sigma|lambda|alpha|beta|gamma|delta|epsilon|nabla|partial|sum|int|infty|left|right|quad|qquad)', r'\\\1', content)
    
    # Fix broken \frac where \f was eaten
    content = re.sub(r'(?<=[=\s(,\[{+*/-])rac\{', r'\\frac{', content)
    
    # Clean multiple consecutive blank lines
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    if content != orig:
        file_path.write_text(content, encoding="utf-8")
        print(f"Sanitized: {file_path.name}")

if __name__ == "__main__":
    for p in Path("/home/linux/Documents/MSM/paper").glob("**/中文翻译/*.md"):
        clean_file(p)
