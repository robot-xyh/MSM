#!/usr/bin/env python3
"""Fix the remaining specific issues found by audit."""
import os
import re
import asyncio
from pathlib import Path

for k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(k, None)

from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://hone.vvvv.ee/v1")
)
MODEL = "claude-haiku-4-5-20251001"

HALLUCINATION_PATTERNS = [
    "I appreciate", "I need to clarify", "I notice", "I cannot translate",
    "Please provide", "you've provided", "you've asked",
    "could you share", "If you have the",
    "To provide you with",
]

async def translate_text(text: str) -> str:
    prompt = (
        "你是专业学术翻译。将以下英文翻译为学术中文。\n"
        "规则：1.保留LaTeX公式原样 2.只输出翻译 3.不加解释\n\n"
        "原文：\n" + text
    )
    for attempt in range(3):
        try:
            r = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=2048
            )
            result = r.choices[0].message.content.strip()
            for pat in HALLUCINATION_PATTERNS:
                if pat in result:
                    return None  # Flag for deletion
            return result
        except Exception as e:
            if attempt == 2:
                return text
            await asyncio.sleep(2)
    return text

async def main():
    # 1. Fix model broke character lines
    fixes = {
        "papers/中文翻译/06_传感运动策略精准激进机动_原文翻译.md": {
            "broke_lines": [759],
        },
        "papers/中文翻译/02_强化学习反应式特技飞行_原文翻译.md": {
            "fig_captions": ["**图 2**：Fig. 2: The training framework."],
        },
        "other-paper/中文翻译/13_自主隐式神经重建的高效视点路径规划_原文翻译.md": {
            "fig_captions": [
                "**图 2**：Fig. 2: The pipeline of our proposed method.",
                "**图 5**：Fig. 5: The experiment on a real scene.",
            ],
        },
        "other-paper/中文翻译/24_LiDAR-VGGT跨模态粗到精融合全局一致米制稠密建图_原文翻译.md": {
            "fig_captions": [],
        },
        "papers/中文翻译/24_FLOAT全驱同轴交互无人机_原文翻译.md": {
            "fig_captions": ["**图 7**：Fig. 7. Upgraded FLOAT Drone prototype."],
        },
        "papers/中文翻译/11_SEB-Naver崎岖地形局部导航_原文翻译.md": {
            "fig_captions": ["**图 4**：Fig. 4: Local mapping process in SE(2) space."],
        },
        "other-paper/中文翻译/33_Star-Searcher复杂未知环境自主目标搜索系统_原文翻译.md": {
            "broke_lines": [75],
        },
        "other-paper/中文翻译/03_动态场景下四旋翼自适应跟踪与停泊_原文翻译.md": {
            "hallucination_text": "I notice the text provided is quite brief",
        },
        "other-paper/中文翻译/17_动态场景多目标测速与感知增强规划飞行_原文翻译.md": {
            "english_para": "To efficiently solve the optimization problem, we need the gradients",
        },
    }
    
    base = Path("/home/linux/Documents/MSM/paper")
    
    for rel_path, fix_info in fixes.items():
        fpath = base / rel_path
        if not fpath.exists():
            continue
        content = fpath.read_text(encoding="utf-8")
        changed = False
        
        # Fix figure captions
        for cap in fix_info.get("fig_captions", []):
            if cap in content:
                fig_match = re.match(r'(\*\*图\s*\d+[A-Za-z]?\*\*：)Fig\.?\s*\d+[A-Za-z]?[:\.]?\s*(.*)', cap, re.S)
                if fig_match:
                    prefix = fig_match.group(1)
                    eng_text = fig_match.group(2).strip()
                    if eng_text:
                        translated = await translate_text(eng_text)
                        if translated and translated != eng_text:
                            content = content.replace(cap, f"{prefix}{translated}")
                            changed = True
                            print(f"  Fixed caption in {fpath.name}")
        
        # Remove hallucination paragraphs
        if "hallucination_text" in fix_info:
            paragraphs = content.split('\n\n')
            new_paras = []
            for p in paragraphs:
                if fix_info["hallucination_text"] in p:
                    print(f"  Removed hallucination from {fpath.name}")
                    changed = True
                    continue
                new_paras.append(p)
            if changed:
                content = '\n\n'.join(new_paras)
        
        # Fix broke character lines
        for line_no in fix_info.get("broke_lines", []):
            lines = content.split('\n')
            if line_no - 1 < len(lines):
                line = lines[line_no - 1]
                is_bad = False
                for pat in HALLUCINATION_PATTERNS:
                    if pat in line:
                        is_bad = True
                        break
                if is_bad:
                    # Find the entire paragraph containing this line
                    paragraphs = content.split('\n\n')
                    new_paras = []
                    for p in paragraphs:
                        skip = False
                        for pat in HALLUCINATION_PATTERNS:
                            if pat in p:
                                skip = True
                                break
                        if skip:
                            chinese = sum(1 for c in p if '\u4e00' <= c <= '\u9fff')
                            if chinese < 20:
                                print(f"  Removed broke-character paragraph from {fpath.name}")
                                changed = True
                                continue
                        new_paras.append(p)
                    content = '\n\n'.join(new_paras)
        
        # Translate remaining English paragraphs
        if "english_para" in fix_info:
            paragraphs = content.split('\n\n')
            new_paras = []
            for p in paragraphs:
                if fix_info["english_para"] in p:
                    translated = await translate_text(p.strip())
                    if translated:
                        new_paras.append(translated)
                        changed = True
                        print(f"  Translated English paragraph in {fpath.name}")
                    else:
                        new_paras.append(p)
                else:
                    new_paras.append(p)
            if changed:
                content = '\n\n'.join(new_paras)
        
        if changed:
            fpath.write_text(content, encoding="utf-8")

    # Also do a global sweep for any remaining hallucination paragraphs
    print("\n=== Global hallucination sweep ===")
    all_files = sorted(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
                sorted(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
    
    for fpath in all_files:
        content = fpath.read_text(encoding="utf-8")
        paragraphs = content.split('\n\n')
        new_paras = []
        changed = False
        for p in paragraphs:
            skip = False
            for pat in HALLUCINATION_PATTERNS:
                if pat in p:
                    chinese = sum(1 for c in p if '\u4e00' <= c <= '\u9fff')
                    if chinese < 20:
                        skip = True
                        break
            if skip:
                print(f"  Removed hallucination from {fpath.name}")
                changed = True
                continue
            new_paras.append(p)
        if changed:
            content = '\n\n'.join(new_paras)
            fpath.write_text(content, encoding="utf-8")
    
    print("\nDone!")

asyncio.run(main())
