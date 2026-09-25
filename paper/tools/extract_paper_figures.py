#!/usr/bin/env python3
"""Figure extractor and PDF analyzer for academic paper translations."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pymupdf


def extract_figures_for_doc(
    doc: pymupdf.Document,
    asset_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    """
    Extract figures from PDF into asset_dir.
    Removes old whole-page screenshots (page-*.jpg) and saves individual figures (fig_*.png/jpg).
    Returns a dict: {fig_key: {'image_file': filename, 'caption_en': text, 'page': pno}}
    """
    asset_dir.mkdir(parents=True, exist_ok=True)
    
    # Remove old page-*.jpg screenshots
    for old_file in asset_dir.glob("page-*.jpg"):
        try:
            old_file.unlink()
        except OSError:
            pass
    for marker in asset_dir.glob(".page-order*"):
        try:
            marker.unlink()
        except OSError:
            pass

    # 1. Scan all pages for figure captions
    raw_captions = []
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = page.get_text("blocks")
        for b in blocks:
            text = b[4].strip()
            # Match figure captions: "Fig. 1", "Figure 1", "Fig. 1.", "Fig. 1:", "Figure 2:", "Fig. 1 (a)", "Fig. 1A"
            m = re.match(r'^(?:Fig(?:ure|\.)?\s*(\d+[A-Za-z]?))\b[:\.]?\s*(.*)', text, re.I | re.S)
            if m:
                fig_num = m.group(1).upper()
                raw_captions.append({
                    'pno': pno,
                    'fig_num': fig_num,
                    'bbox': pymupdf.Rect(b[:4]),
                    'text': text,
                })

    # Deduplicate captions by fig_num, keeping the one with longer text
    unique_captions: Dict[str, Dict[str, Any]] = {}
    for c in raw_captions:
        num = c['fig_num']
        if num not in unique_captions or len(c['text']) > len(unique_captions[num]['text']):
            unique_captions[num] = c

    def sort_key(k: str) -> Tuple[int, str]:
        m = re.match(r'(\d+)([A-Za-z]*)', k)
        if m:
            return (int(m.group(1)), m.group(2))
        return (999, k)

    sorted_fig_keys = sorted(unique_captions.keys(), key=sort_key)
    results: Dict[str, Dict[str, Any]] = {}
    
    # 2. Extract or crop image for each figure caption
    for fig_key in sorted_fig_keys:
        cap_info = unique_captions[fig_key]
        pno = cap_info['pno']
        page = doc[pno]
        cap_bbox = cap_info['bbox']
        
        candidate_pages = [pno]
        if pno > 0:
            candidate_pages.append(pno - 1)
        if pno + 1 < len(doc):
            candidate_pages.append(pno + 1)
            
        saved_img_name = None
        
        # Method A: Try to find a substantial embedded bitmap image
        best_img = None
        min_dist = 999999.0
        
        for cand_pno in candidate_pages:
            cand_page = doc[cand_pno]
            img_infos = cand_page.get_image_info(xrefs=True)
            for img in img_infos:
                w, h = img['width'], img['height']
                if w >= 220 and h >= 140:
                    r = pymupdf.Rect(img['bbox'])
                    if cand_pno == pno:
                        if r.y1 <= cap_bbox.y0 + 20: # above caption
                            dist = cap_bbox.y0 - r.y1
                        elif r.y0 >= cap_bbox.y1 - 20: # below caption
                            dist = r.y0 - cap_bbox.y1
                        else:
                            dist = abs(r.y0 - cap_bbox.y0)
                    else:
                        dist = 1000.0 + abs(cand_pno - pno) * 500
                    
                    if dist < min_dist:
                        min_dist = dist
                        best_img = (cand_page, img)
                        
        if best_img and min_dist < 450.0:
            cand_page, img = best_img
            xref = img['xref']
            try:
                bimg = doc.extract_image(xref)
                ext = bimg['ext']
                out_name = f"fig_{fig_key.lower()}.{ext}"
                out_path = asset_dir / out_name
                with open(out_path, "wb") as f:
                    f.write(bimg['image'])
                saved_img_name = out_name
            except Exception:
                pass

        # Method B: If no bitmap or it's a vector plot/diagram, crop from page at 300 DPI
        if not saved_img_name:
            drawings = page.get_drawings()
            rects = [d['rect'] for d in drawings if d['rect'].y1 <= cap_bbox.y0 + 15 and d['rect'].y0 >= max(page.rect.y0 + 30, cap_bbox.y0 - 450)]
            if rects:
                crop_rect = pymupdf.Rect(rects[0])
                for r in rects[1:]:
                    crop_rect |= r
                crop_rect = pymupdf.Rect(
                    max(page.rect.x0 + 30, crop_rect.x0 - 5),
                    max(page.rect.y0 + 30, crop_rect.y0 - 5),
                    min(page.rect.x1 - 30, crop_rect.x1 + 5),
                    min(page.rect.y1 - 30, crop_rect.y1 + 5),
                )
            else:
                crop_rect = pymupdf.Rect(
                    page.rect.x0 + 40,
                    max(page.rect.y0 + 40, cap_bbox.y0 - 280),
                    page.rect.x1 - 40,
                    cap_bbox.y0 - 5
                )
            
            try:
                pix = page.get_pixmap(clip=crop_rect, dpi=300)
                out_name = f"fig_{fig_key.lower()}.png"
                out_path = asset_dir / out_name
                pix.save(str(out_path))
                saved_img_name = out_name
            except Exception:
                pass

        if saved_img_name:
            results[fig_key] = {
                'image_file': saved_img_name,
                'caption_en': cap_info['text'],
                'pno': pno + 1,
            }
            
    # Fallback if no captions matched: extract all standalone large images
    if not results:
        for pno in range(len(doc)):
            page = doc[pno]
            img_infos = page.get_image_info(xrefs=True)
            for idx, img in enumerate(img_infos):
                w, h = img['width'], img['height']
                if w >= 300 and h >= 200:
                    xref = img['xref']
                    try:
                        bimg = doc.extract_image(xref)
                        out_name = f"fig_p{pno+1}_{idx+1}.{bimg['ext']}"
                        out_path = asset_dir / out_name
                        with open(out_path, "wb") as f:
                            f.write(bimg['image'])
                        results[f"p{pno+1}_{idx+1}"] = {
                            'image_file': out_name,
                            'caption_en': f"Figure on page {pno+1}",
                            'pno': pno + 1,
                        }
                    except Exception:
                        pass
                        
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        pdf_path = Path(sys.argv[1])
        asset_dir = Path(sys.argv[2])
        doc = pymupdf.open(str(pdf_path))
        figs = extract_figures_for_doc(doc, asset_dir)
        print(f"Extracted {len(figs)} figures to {asset_dir}:")
        for k, v in figs.items():
            print(f"  Fig {k}: {v['image_file']} (page {v['pno']})")
