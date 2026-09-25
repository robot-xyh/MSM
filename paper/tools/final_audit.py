#!/usr/bin/env python3
"""Final strict audit - only flag REAL problems, not LaTeX/pseudocode blocks."""
import re
from pathlib import Path

HALLUCINATION_PATTERNS = [
    "I appreciate", "I need to clarify", "I notice", "I cannot translate",
    "Please provide", "you've provided", "you've asked",
    "could you share", "If you have the", "To provide you with",
    "I'll translate", "Here is the translation", "Here's the translation",
    "Let me translate", "I'm Kiro", "Would you like me to",
]

def audit():
    md_files = sorted(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
               sorted(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
    
    print(f"Final audit of {len(md_files)} files...\n")
    
    total_issues = 0
    clean_count = 0
    
    for fpath in md_files:
        content = fpath.read_text(encoding="utf-8")
        lines = content.split('\n')
        paragraphs = content.split('\n\n')
        issues = []
        
        # 1. Model hallucinations (CRITICAL)
        for i, line in enumerate(lines):
            for pat in HALLUCINATION_PATTERNS:
                if pat in line:
                    issues.append(f"  ❗ LINE {i+1}: MODEL HALLUCINATION: '{line[:80]}...'")
                    break
        
        # 2. Untranslated figure captions (CRITICAL)
        for i, line in enumerate(lines):
            if line.strip().startswith("**图") and "Fig." in line:
                after = re.sub(r'\*\*图 \d+[A-Za-z]?\*\*：', '', line)
                chinese = sum(1 for c in after if '\u4e00' <= c <= '\u9fff')
                english = sum(1 for c in after if 'a' <= c.lower() <= 'z')
                if chinese < 3 and english > 30:
                    issues.append(f"  ⚠️  LINE {i+1}: UNTRANSLATED CAPTION: '{line[:80]}...'")
        
        # 3. Real untranslated prose (not formulas/pseudocode/references)
        for i, p in enumerate(paragraphs):
            p_s = p.strip()
            if not p_s:
                continue
            # Skip things that shouldn't be translated
            if (p_s.startswith('![') or p_s.startswith('#') or p_s.startswith('>') or
                p_s.startswith('---') or p_s.startswith('|') or
                p_s.startswith('$$') or p_s.startswith('$') or
                p_s.startswith('```') or
                '\\leftarrow' in p_s or '\\begin{' in p_s or '\\frac' in p_s or
                '\\mathbf' in p_s or '\\partial' in p_s or '\\sum' in p_s or
                '\\boldsymbol' in p_s or '\\hat{' in p_s or '\\text{' in p_s or
                '\\Gamma' in p_s or '\\varrho' in p_s or
                re.match(r'^\d+:', p_s) or  # pseudocode lines
                re.match(r'^[-*]\s*\$', p_s) or  # bullet with formula
                'leftarrow' in p_s.lower() or
                '← ' in p_s or '→ ' in p_s or
                'for ' in p_s[:20].lower() and ('do' in p_s.lower() or '←' in p_s) or
                'while ' in p_s[:20].lower() and '←' in p_s or
                re.search(r'^\[\d+\]', p_s)):  # references
                continue
            
            letters = sum(1 for c in p_s if 'a' <= c.lower() <= 'z')
            chinese = sum(1 for c in p_s if '\u4e00' <= c <= '\u9fff')
            
            if letters > 200 and chinese < letters * 0.1:
                preview = p_s[:100].replace('\n', ' ')
                issues.append(f"  ⚠️  ENGLISH BLOCK ({letters}L/{chinese}C): '{preview}...'")
        
        # 4. Control characters
        for i, line in enumerate(lines):
            for ch in line:
                if ord(ch) < 32 and ch not in ('\t', '\n', '\r'):
                    issues.append(f"  ❗ LINE {i+1}: CONTROL CHAR \\x{ord(ch):02x}")
                    break
        
        # 5. Broken images
        for m in re.finditer(r'!\[.*?\]\((.*?)\)', content):
            img = m.group(1)
            if not img.startswith('http'):
                full = fpath.parent / img
                if not full.exists():
                    issues.append(f"  ❗ BROKEN IMAGE: {img}")
        
        if issues:
            print(f"❌ {fpath.name}:")
            for iss in issues:
                print(iss)
            print()
            total_issues += len(issues)
        else:
            clean_count += 1
    
    print(f"\n{'='*60}")
    print(f"✅ Clean files: {clean_count}/{len(md_files)}")
    print(f"❌ Files with issues: {len(md_files) - clean_count}")
    print(f"Total issues: {total_issues}")

audit()
