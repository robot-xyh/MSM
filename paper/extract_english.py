import re
from pathlib import Path

files = [
    "papers/中文翻译/05_安全屏蔽强化学习高速飞行_原文翻译.md",
    "papers/中文翻译/13_Tracailer牵引挂车轨迹规划_原文翻译.md",
    "papers/中文翻译/19_Ring-Rotor可伸缩环形四旋翼_原文翻译.md",
    "papers/中文翻译/26_FastViDAR全向深度估计_原文翻译.md",
    "other-paper/中文翻译/04_包含碰撞的高动态机动运动规划_原文翻译.md",
    "other-paper/中文翻译/10_紧密协作下的高性价比无人机集群导航系统_原文翻译.md",
    "other-paper/中文翻译/16_FastSim模块化即插即用空中机器人仿真平台_原文翻译.md",
    "other-paper/中文翻译/22_LEMON-Mapping大规模多时序点云融合与回环增强优化_原文翻译.md",
    "other-paper/中文翻译/28_Primitive-Swarm超轻量高扩展大规模无人机集群规划器_原文翻译.md",
    "other-paper/中文翻译/34_复兴超声波传感构建鲁棒自主系统_原文翻译.md"
]

def contains_english(text):
    letters = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return letters > 30 and letters > chinese * 2

for f in files:
    path = Path("/home/linux/Documents/MSM/paper") / f
    if not path.exists(): continue
    content = path.read_text(encoding="utf-8")
    paragraphs = content.split('\n\n')
    print(f"--- {f} ---")
    for i, p in enumerate(paragraphs):
        p_stripped = p.strip()
        if p_stripped.startswith('**图') and 'Fig' in p_stripped:
            print(f"[{i}] CAPTION: {p_stripped}")
        elif p_stripped.startswith('**表') and 'Table' in p_stripped:
            print(f"[{i}] TABLE: {p_stripped}")
        elif contains_english(p_stripped) and not p_stripped.startswith('$$') and not p_stripped.startswith('![') and not p_stripped.startswith('#'):
            print(f"[{i}] TEXT: {p_stripped[:100]}...")
            
