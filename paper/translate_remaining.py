import re
import os
import asyncio
from pathlib import Path

# Provide standard proxy-free setup
for k in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]:
    os.environ.pop(k, None)

from openai import AsyncOpenAI
client = AsyncOpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url=os.environ.get("OPENAI_BASE_URL", "https://hone.vvvv.ee/v1")
)
MODEL = "claude-haiku-4-5-20251001"

async def translate_text(text: str) -> str:
    prompt = (
        "You are an expert academic translator specializing in robotics, UAVs, trajectory optimization, and SLAM.\n"
        "Translate the following English academic text into professional, faithful academic Chinese.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. DO NOT change or translate any LaTeX math formulas (e.g., $...$, $$...$$). Keep them EXACTLY as they are.\n"
        "2. Keep all markdown formatting intact.\n"
        "3. Output ONLY the translated text, do not add introductory words or conversational AI fillers.\n"
        "4. If it's a figure/table caption like '**图 X**：Fig. X: English text...', translate the English text but keep the '**图 X**：' prefix.\n"
        "5. For references, keep the paper title in English.\n\n"
        "Text to translate:\n" + text
    )
    for _ in range(3):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            await asyncio.sleep(1)
    return text

def is_mostly_english(text):
    letters = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return letters > 30 and letters > chinese * 2

async def process_file(fpath):
    path = Path("/home/linux/Documents/MSM/paper") / fpath
    if not path.exists(): return
    content = path.read_text(encoding="utf-8")
    
    # We will split by \n\n
    paragraphs = content.split('\n\n')
    new_paragraphs = []
    changed = False
    
    for i, p in enumerate(paragraphs):
        ps = p.strip()
        # Find english figure/table captions
        is_english_caption = False
        if ps.startswith('**图') and 'Fig' in ps:
            is_english_caption = True
        elif ps.startswith('**表') and 'Table' in ps:
            is_english_caption = True
            
        # Or large english text blocks
        is_eng_text = False
        if not is_english_caption:
            if is_mostly_english(ps) and not ps.startswith('![') and not ps.startswith('$$') and not ps.startswith('#'):
                # Ignore reference lists (often starts with [1]) unless they are clearly paragraphs
                if not re.match(r'^\[\d+\]', ps):
                    is_eng_text = True
                    
        if is_english_caption or is_eng_text:
            print(f"Translating in {path.name}: {ps[:50]}...")
            trans = await translate_text(p)
            new_paragraphs.append(trans)
            changed = True
        else:
            new_paragraphs.append(p)
            
    if changed:
        path.write_text('\n\n'.join(new_paragraphs), encoding="utf-8")
        print(f"Updated {path.name}")

async def main():
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
    tasks = [process_file(f) for f in files]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
