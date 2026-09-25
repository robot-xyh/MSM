import re
import sys
import os

files = [
    "/home/linux/Documents/MSM/paper/papers/中文翻译/06_传感运动策略精准激进机动_原文翻译.md",
    "/home/linux/Documents/MSM/paper/papers/中文翻译/14_隐式扫掠体SDF连续避碰_原文翻译.md",
    "/home/linux/Documents/MSM/paper/papers/中文翻译/20_可变形四旋翼形状自适应规划与控制_原文翻译.md",
    "/home/linux/Documents/MSM/paper/papers/中文翻译/28_FLAP受限视场主动感知规划_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/05_非结构化环境下自动驾驶车辆高效时空轨迹规划器_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/11_DPNet多普勒激光雷达高动态环境运动规划_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/17_动态场景多目标测速与感知增强规划飞行_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/23_LF-VISLAM负成像平面超大视场相机视觉惯导SLAM_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/29_实时空中停泊轨迹规划_原文翻译.md",
    "/home/linux/Documents/MSM/paper/other-paper/中文翻译/35_差速驱动机器人族通用轨迹优化框架_原文翻译.md",
]

for fpath in files:
    if not os.path.exists(fpath):
        print(f"Not found: {fpath}")
        continue
    with open(fpath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    in_math = False
    in_code = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code:
            # We are looking for lines that have a lot of english or start with Fig.
            clean = re.sub(r'\$.*?\$', '', line) # remove inline math
            clean = re.sub(r'\[\d+\]', '', clean) # remove reference numbers
            clean = re.sub(r'!\[.*?\]\(.*?\)', '', clean) # remove images
            clean = re.sub(r'\[.*?\]\(.*?\)', '', clean) # remove links
            
            # Match "Fig. X:" or mostly english text
            if re.search(r'\bFig\.\s*\d+:', line) or re.search(r'^\*\*图 \d+\*\*：Fig\.\s*\d+:', line):
                print(f"{os.path.basename(fpath)}:{i+1}: {line.strip()}")
            elif re.search(r'[a-zA-Z]{5,}', clean):
                # if there are multiple english words (more than 3 words)
                words = re.findall(r'[a-zA-Z]{3,}', clean)
                if len(words) >= 5 and "http" not in line and "arXiv" not in line and not line.startswith(">"):
                    # heuristic to skip bibliography titles
                    if not re.match(r'^\s*\[\d+\].*', line):
                        print(f"{os.path.basename(fpath)}:{i+1}: {line.strip()}")

