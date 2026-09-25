#!/usr/bin/env python3
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
sem = asyncio.Semaphore(150)

async def translate_chunk(text: str) -> str:
    if not text.strip() or len(text.strip()) < 20:
        return text
    prompt = (
        "You are an expert academic translator specializing in robotics, UAVs, trajectory optimization, and SLAM.\n"
        "Please translate the following English academic text into highly rigorous, professional, and faithful academic Chinese.\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. DO NOT change or translate any LaTeX math formulas (e.g., $...$, $$...$$). Keep them EXACTLY as they are.\n"
        "2. Keep all markdown formatting (bolding, lists, headers) intact.\n"
        "3. Output ONLY the translated text, do not add introductory words.\n\n"
        "Text to translate:\n" + text
    )
    async with sem:
        for attempt in range(5):
            try:
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=4000
                )
                translated = response.choices[0].message.content.strip()
                return translated if translated else text
            except Exception as e:
                if attempt == 4:
                    print(f"Error translating chunk: {e}")
                    return text
                await asyncio.sleep(2 ** attempt)
        return text

async def process_file(file_path: Path):
    content = file_path.read_text(encoding="utf-8")
    paragraphs = content.split('\n\n')
    translated_paragraphs = []
    tasks = []
    task_indices = []
    
    for i, p in enumerate(paragraphs):
        p_stripped = p.strip()
        if (p_stripped.startswith('![') or 
            p_stripped.startswith('#') or 
            p_stripped.startswith('---') or 
            p_stripped.startswith('>') or
            (p_stripped.startswith('$$') and p_stripped.endswith('$$')) or
            p_stripped.startswith('**图')):
            translated_paragraphs.append(p)
            continue
            
        letters = sum(1 for c in p_stripped if c.isalpha())
        chinese = sum(1 for c in p_stripped if '\u4e00' <= c <= '\u9fff')
        
        if letters > 30 and letters > chinese * 2:
            tasks.append(translate_chunk(p))
            task_indices.append(i)
            translated_paragraphs.append(None)
        else:
            translated_paragraphs.append(p)
            
    if not tasks:
        return False
        
    results = await asyncio.gather(*tasks)
    for idx, trans_res in zip(task_indices, results):
        translated_paragraphs[idx] = trans_res
        
    final_content = '\n\n'.join(translated_paragraphs)
    file_path.write_text(final_content, encoding="utf-8")
    return True

async def main():
    md_files = list(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
               list(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
    
    md_files = [f for f in md_files if not f.name.startswith("01_释放四旋翼特技飞行潜能")]
    print(f"Found {len(md_files)} files to translate.")
    
    batch_size = 15
    for i in range(0, len(md_files), batch_size):
        batch = md_files[i:i+batch_size]
        print(f"Batch {i//batch_size+1}/{(len(md_files)-1)//batch_size+1} ({len(batch)} files)...")
        tasks = [process_file(f) for f in batch]
        await asyncio.gather(*tasks)
        print(f"  -> Batch complete.")

if __name__ == "__main__":
    asyncio.run(main())
