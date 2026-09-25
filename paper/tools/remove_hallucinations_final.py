#!/usr/bin/env python3
"""Remove all model hallucination paragraphs from translation files."""
import re
from pathlib import Path

HALLUCINATION_PATTERNS = [
    "I appreciate", "I need to clarify", "I notice", "I cannot translate",
    "Please provide", "you've provided", "you've asked", "I'm Kiro",
    "could you share", "If you have the", "To provide you with",
    "I'll translate", "Here is the translation", "Here's the translation",
    "Let me translate", "Would you like me to", "I'm ready to",
    "I can't assist", "I can't translate", "I can't help",
    "Translation work", "For this task, I'd recommend",
    "Could you provide", "Could you please provide",
    "What I can do:", "What I'd recommend",
    "Changes made:", "falls outside my c",
    "While I can assist", "While I have expertise",
    "professional academic translat",
    "specialized academic translation",
    "I'm designed to help with cod",
    "I'm an AI development environment",
    "I'm an AI-powered development",
    "If you're working on a project",
    "surrounding prose",
]

def clean_file(fpath):
    content = fpath.read_text(encoding="utf-8")
    paragraphs = content.split('\n\n')
    new_paras = []
    removed = 0
    
    for p in paragraphs:
        skip = False
        for pat in HALLUCINATION_PATTERNS:
            if pat in p:
                # Only skip if it's mostly English/hallucination, not legitimate translated content
                chinese = sum(1 for c in p if '\u4e00' <= c <= '\u9fff')
                if chinese < 30:
                    skip = True
                    break
        if skip:
            removed += 1
        else:
            new_paras.append(p)
    
    if removed > 0:
        content = '\n\n'.join(new_paras)
        fpath.write_text(content, encoding="utf-8")
        print(f"  Cleaned {fpath.name}: removed {removed} hallucination paragraphs")
    return removed

# Target the specific problematic files
problem_files = [
    "/home/linux/Documents/MSM/paper/papers/中文翻译/05_安全屏蔽强化学习高速飞行_原文翻译.md",
    "/home/linux/Documents/MSM/paper/papers/中文翻译/13_Tracailer牵引挂车轨迹规划_原文翻译.md",
    "/home/linux/Documents/MSM/paper/papers/中文翻译/19_Ring-Rotor可伸缩环形四旋翼_原文翻译.md",
    "/home/linux/Documents/MSM/paper/papers/中文翻译/26_FastViDAR全向深度估计_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/10_紧密协作下的高性价比无人机集群导航系统_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/16_FastSim模块化即插即用空中机器人仿真平台_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/22_LEMON-Mapping大规模多时序点云融合与回环增强优化_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/28_Primitive-Swarm超轻量高扩展大规模无人机集群规划器_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/34_复兴超声波传感构建鲁棒自主系统_原文翻译.md",
]

total = 0
for f in problem_files:
    p = Path(f)
    if p.exists():
        total += clean_file(p)

print(f"\nTotal removed: {total}")
