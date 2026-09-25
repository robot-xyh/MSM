import os
import glob
from pathlib import Path

def clean_files():
    md_files = list(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
               list(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
    
    for fpath in md_files:
        content = fpath.read_text(encoding="utf-8")
        clean_content = "".join(c for c in content if ord(c) >= 32 or c in ('\t', '\n', '\r'))
        if content != clean_content:
            fpath.write_text(clean_content, encoding="utf-8")
            print(f"Cleaned {fpath.name}")

if __name__ == "__main__":
    clean_files()
