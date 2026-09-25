#!/usr/bin/env python3
"""Test extraction and translation pipeline on sample papers."""

import os, sys, re
from pathlib import Path
import pymupdf

def test_paper(pdf_path, detail_path, asset_dir):
    doc = pymupdf.open(str(pdf_path))
    print(f"\n==========================================")
    print(f"Testing {pdf_path.name} ({len(doc)} pages)")
    print(f"Detail: {detail_path.name}")
    print(f"Asset dir: {asset_dir.name}")
    
    # 1. Images in asset dir
    images = list(asset_dir.glob("fig_*.*"))
    print(f"Figures extracted: {len(images)} -> {[img.name for img in images[:6]]}")
    
    # 2. Extract sections & headers from text
    full_text = ""
    for pno in range(len(doc)):
        full_text += f"\n--- Page {pno+1} ---\n" + doc[pno].get_text("text")
        
    print(f"Total extracted text length: {len(full_text)} characters")

test_paper(
    Path("/home/linux/Documents/MSM/paper/papers/16_Fast_Iterative_Region_Inflation.pdf"),
    Path("/home/linux/Documents/MSM/paper/papers/中文详解/16_FIRI快速凸安全区域膨胀.md"),
    Path("/home/linux/Documents/MSM/paper/papers/中文翻译/assets/16_FIRI快速凸安全区域膨胀")
)
test_paper(
    Path("/home/linux/Documents/MSM/paper/other-paper/A Decoupled and Linear Framework for Global Outlier Rejection over Planar Pose Graph.pdf"),
    Path("/home/linux/Documents/MSM/paper/other-paper/中文详解/01_平面位姿图全局外点剔除解耦线性框架.md"),
    Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译/assets/01_平面位姿图全局外点剔除解耦线性框架")
)
