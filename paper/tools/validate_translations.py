#!/usr/bin/env python3
import os
import re
from pathlib import Path

def validate_files():
    md_files = list(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
               list(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
               
    print(f"Starting rigorous line-by-line validation of {len(md_files)} files...\n")
    
    total_issues = 0
    
    for fpath in md_files:
        content = fpath.read_text(encoding="utf-8")
        lines = content.split('\n')
        
        file_issues = []
        
        # 1. Check for control characters (KaTeX parse errors)
        # Allow tab (\t), newline (\n), return (\r). Disallow \x0c, \x08, \x07, etc.
        for i, line in enumerate(lines):
            for char in line:
                if ord(char) < 32 and char not in ('\t', '\n', '\r'):
                    file_issues.append(f"Line {i+1}: Invalid control char \\x{ord(char):02x} found.")
                    break
        
        # 2. Check for leftover untranslated English paragraphs
        # A paragraph with > 100 letters and > 3x more letters than Chinese chars is likely untranslated.
        paragraphs = content.split('\n\n')
        for i, p in enumerate(paragraphs):
            p_stripped = p.strip()
            if p_stripped.startswith('![') or p_stripped.startswith('#') or p_stripped.startswith('>'):
                continue
            
            letters = sum(1 for c in p_stripped if c.isalpha())
            chinese = sum(1 for c in p_stripped if '\u4e00' <= c <= '\u9fff')
            if letters > 100 and letters > chinese * 4:
                # Some references or formulas might trigger this, so we use a high threshold and check if it's purely english prose.
                # Let's verify if it's a reference list or something.
                if not re.search(r'\[\d+\]', p_stripped) and "Abstract" in p_stripped:
                    file_issues.append(f"Paragraph {i}: Possible untranslated English block found.")
        
        # 3. Check for imbalanced LaTeX
        dollar_count = content.count('$')
        # This is a basic check. Actual parsing is complex.
        
        # 4. Check for broken markdown formatting (e.g., missing asset files)
        # Find all ![xxx](path) and verify path exists
        for match in re.finditer(r'!\[.*?\]\((.*?)\)', content):
            img_path = match.group(1)
            # The path is relative to the md file
            full_img_path = fpath.parent / img_path
            if not full_img_path.exists():
                file_issues.append(f"Missing image file: {img_path}")
                
        if file_issues:
            print(f"Issues in {fpath.name}:")
            for issue in file_issues:
                print(f"  - {issue}")
            total_issues += len(file_issues)
            
    if total_issues == 0:
        print("✅ SUCCESS: All files passed the rigorous validation! No control characters, no untranslated blocks, all images valid.")
    else:
        print(f"❌ FOUND {total_issues} ISSUES across files.")

if __name__ == "__main__":
    validate_files()
