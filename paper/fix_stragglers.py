import re
import os
import glob

files = glob.glob("/home/linux/Documents/MSM/paper/papers/中文翻译/*_原文翻译.md") + \
        glob.glob("/home/linux/Documents/MSM/paper/other-paper/中文翻译/*_原文翻译.md")

replacements = {
    "control effort": "控制代价",
    "The kinematic bicycle model.": "运动学自行车模型。",
    "Failure mode analysis.": "故障模式分析。",
    "Doppler调谐模型预测控制(DT-MPC)框架": "多普勒调谐模型预测控制(DT-MPC)框架",
}

for fpath in files:
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig_content = content
    
    for eng, chi in replacements.items():
        content = content.replace(eng, chi)
    
    if content != orig_content:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {fpath}")

