import re
import os
import glob

files = glob.glob("/home/linux/Documents/MSM/paper/papers/中文翻译/*_原文翻译.md") + \
        glob.glob("/home/linux/Documents/MSM/paper/other-paper/中文翻译/*_原文翻译.md")

replacements = {
    "time regularization": "时间正则化",
    "active perception": "主动感知",
    "The real-world experiment site.": "真实世界实验场地。",
    "The experimental platform.": "实验平台。",
    "Doppler velocity rectiﬁcation.": "多普勒速度校正。",
    "Doppler LiDAR:": "多普勒激光雷达：",
    "Nominal Trajectory": "标称轨迹",
}

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig_content = content
    
    # Apply specific phrase replacements
    for eng, chi in replacements.items():
        content = content.replace(eng, chi)
    
    # Fix "Fig. X: english caption"
    def fix_fig_caption(m):
        # m.group(0) is like "**图 2**：Fig. 2: Planning framework."
        # We want to translate "Planning framework."
        full_match = m.group(0)
        # This requires translation, let's just do known ones
        if "Planning framework" in full_match:
            return full_match.replace("Fig. 2: Planning framework.", "规划框架。")
        elif "Ablation study" in full_match:
            return full_match.replace("Fig. 6: Ablation study", "消融实验")
        # For bare "Fig. X." or "Fig. X"
        return re.sub(r'Fig\.\s*\d+\.?:?\s*', '', full_match)
        
    content = re.sub(r'\*\*图 \d+\*\*：Fig\.\s*\d+\.?:?\s*.*', fix_fig_caption, content)
    
    # Fix inline "Fig. X" -> "图 X"
    content = re.sub(r'(?<!\*\*)Fig\.\s*(\d+)', r'图 \1', content)
    
    if content != orig_content:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {fpath}")

