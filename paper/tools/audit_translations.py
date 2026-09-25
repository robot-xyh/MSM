#!/usr/bin/env python3
"""Deep audit of all translation files - find every type of problem."""
import re
from pathlib import Path

def audit():
    md_files = sorted(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
               sorted(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
    
    print(f"Auditing {len(md_files)} files...\n")
    
    for fpath in md_files:
        content = fpath.read_text(encoding="utf-8")
        lines = content.split('\n')
        paragraphs = content.split('\n\n')
        issues = []
        
        # 1. Model broke character - chatting instead of translating
        chat_patterns = [
            "I appreciate", "I need to clarify", "I'll translate", 
            "Here is the translation", "Here's the translation",
            "Let me translate", "Please provide", "you've provided",
            "This looks like", "For diagram labels",
            "However, if this is extracted",
            "please provide the complete",
        ]
        for i, line in enumerate(lines):
            for pat in chat_patterns:
                if pat in line:
                    issues.append(f"  LINE {i+1}: MODEL BROKE CHARACTER: '{line[:80]}...'")
                    break
        
        # 2. Figure captions left in English (Fig. X: ... without Chinese)
        for i, line in enumerate(lines):
            if line.strip().startswith("**图") and "Fig." in line:
                # Check if caption is purely English after "Fig."
                after_fig = re.sub(r'\*\*图 \d+\*\*：', '', line)
                chinese_count = sum(1 for c in after_fig if '\u4e00' <= c <= '\u9fff')
                if chinese_count < 3 and len(after_fig) > 30:
                    issues.append(f"  LINE {i+1}: UNTRANSLATED FIGURE CAPTION: '{line[:80]}...'")
        
        # 3. Long English-only paragraphs (untranslated)
        for i, p in enumerate(paragraphs):
            p_s = p.strip()
            if not p_s or p_s.startswith('![') or p_s.startswith('#') or p_s.startswith('>') or p_s.startswith('---'):
                continue
            if p_s.startswith('$$') and p_s.endswith('$$'):
                continue
            
            letters = sum(1 for c in p_s if 'a' <= c.lower() <= 'z')
            chinese = sum(1 for c in p_s if '\u4e00' <= c <= '\u9fff')
            
            # If more than 200 english letters and less than 10% chinese, flag it
            if letters > 200 and chinese < letters * 0.1:
                # Skip reference lists
                if re.search(r'^\[\d+\]', p_s) or re.match(r'^\d+\.?\s+[A-Z]', p_s):
                    continue
                preview = p_s[:100].replace('\n', ' ')
                issues.append(f"  PARA ~line: UNTRANSLATED ENGLISH BLOCK ({letters} letters, {chinese} chinese): '{preview}...'")
        
        # 4. Control characters
        for i, line in enumerate(lines):
            for ch in line:
                if ord(ch) < 32 and ch not in ('\t', '\n', '\r'):
                    issues.append(f"  LINE {i+1}: CONTROL CHAR \\x{ord(ch):02x}")
                    break
        
        # 5. Broken image links
        for m in re.finditer(r'!\[.*?\]\((.*?)\)', content):
            img = m.group(1)
            if not img.startswith('http'):
                full = fpath.parent / img
                if not full.exists():
                    issues.append(f"  BROKEN IMAGE: {img}")
        
        if issues:
            print(f"❌ {fpath.name}:")
            for iss in issues:
                print(iss)
            print()

audit()
