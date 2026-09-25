#!/usr/bin/env python3
"""
Complete retranslation of all 59 paper translations.
Fixes:
1. Translates ALL figure captions (Fig. X: ... -> 图 X：中文翻译)
2. Translates ALL remaining English paragraphs
3. Removes any model "broke character" hallucinations
4. Preserves LaTeX math, markdown formatting, image links
"""
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
sem = asyncio.Semaphore(80)

# Patterns that indicate the model broke character
HALLUCINATION_PATTERNS = [
    "I appreciate your request",
    "I need to clarify",
    "I'll translate",
    "Here is the translation",
    "Here's the translation",
    "Let me translate",
    "Please provide",
    "you've provided",
    "This looks like",
    "For diagram labels",
    "However, if this is extracted",
    "please provide the complete",
    "If you have the actual academic text",
    "If you have the full paper text",
    "I notice you've provided",
    "I'm Kiro",
    "Consulting with domain experts",
    "Would you like me to",
    "If you'd like me to",
    "complete reference entries",
]

async def translate_text(text: str, context: str = "body") -> str:
    """Translate a block of text from English to Chinese."""
    if not text.strip() or len(text.strip()) < 10:
        return text

    if context == "caption":
        prompt = (
            "你是一位专业的机器人学、无人机、轨迹优化和SLAM领域的学术翻译专家。\n"
            "请将以下英文图注翻译为严谨、专业、忠实的学术中文。\n\n"
            "要求：\n"
            "1. 不要更改任何LaTeX公式（如 $...$, $$...$$）\n"
            "2. 保持所有markdown格式\n"
            "3. 只输出翻译结果，不要加任何解释性文字\n"
            "4. 如果内容是图表标注或坐标轴标签，也要翻译\n\n"
            "待翻译文本：\n" + text
        )
    else:
        prompt = (
            "你是一位专业的机器人学、无人机、轨迹优化和SLAM领域的学术翻译专家。\n"
            "请将以下英文学术文本翻译为严谨、专业、忠实的学术中文。\n\n"
            "要求：\n"
            "1. 不要更改任何LaTeX公式（如 $...$, $$...$$），保持原样\n"
            "2. 保持所有markdown格式（加粗、列表、标题等）\n"
            "3. 只输出翻译结果，不要加任何解释性文字、评论或对话\n"
            "4. 翻译必须忠实于原文，不要遗漏内容\n"
            "5. 专业术语要准确\n\n"
            "待翻译文本：\n" + text
        )

    async with sem:
        for attempt in range(5):
            try:
                response = await client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=4096
                )
                result = response.choices[0].message.content.strip()
                # Check if the model broke character
                for pat in HALLUCINATION_PATTERNS:
                    if pat in result:
                        # Retry with stronger prompt
                        response2 = await client.chat.completions.create(
                            model=MODEL,
                            messages=[
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": result},
                                {"role": "user", "content": "你的回复包含了解释性文字。请只输出中文翻译，不要加任何其他内容。直接翻译原文。"}
                            ],
                            temperature=0.1,
                            max_tokens=4096
                        )
                        result = response2.choices[0].message.content.strip()
                        break
                return result if result else text
            except Exception as e:
                if attempt == 4:
                    print(f"    ERROR: {e}")
                    return text
                await asyncio.sleep(2 ** attempt)
    return text


def needs_translation(text: str) -> bool:
    """Check if a text block is English and needs translation."""
    text = text.strip()
    if not text:
        return False
    letters = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return letters > 30 and letters > chinese * 2


def is_hallucination(text: str) -> bool:
    """Check if text contains model hallucinations."""
    for pat in HALLUCINATION_PATTERNS:
        if pat in text:
            return True
    return False


async def process_file(fpath: Path) -> dict:
    """Process a single file: retranslate all English content."""
    content = fpath.read_text(encoding="utf-8")
    paragraphs = content.split('\n\n')
    
    tasks = []
    task_info = []  # (index, context_type)
    new_paragraphs = []
    
    for i, p in enumerate(paragraphs):
        p_stripped = p.strip()
        
        # Remove pure hallucination paragraphs
        if is_hallucination(p_stripped) and not p_stripped.startswith('**图'):
            # Check if it's mostly hallucination
            chinese = sum(1 for c in p_stripped if '\u4e00' <= c <= '\u9fff')
            if chinese < 20:
                new_paragraphs.append(None)  # will be removed
                continue
        
        # Skip structural elements that don't need translation
        if (p_stripped.startswith('![') or 
            p_stripped.startswith('# ') or
            p_stripped.startswith('## ') or
            p_stripped.startswith('---') or
            p_stripped.startswith('> ') or
            (p_stripped.startswith('$$') and p_stripped.endswith('$$'))):
            new_paragraphs.append(p)
            continue
        
        # Handle figure captions: **图 X**：Fig. X: English text...
        fig_match = re.match(r'(\*\*图\s*\d+[A-Za-z]?\*\*：)(Fig\.?\s*\d+[A-Za-z]?[:\.]?\s*)(.*)', p_stripped, re.S)
        if fig_match:
            prefix = fig_match.group(1)
            caption_text = fig_match.group(3).strip()
            if caption_text and needs_translation(caption_text):
                tasks.append(translate_text(caption_text, "caption"))
                task_info.append((i, "caption", prefix))
                new_paragraphs.append(None)  # placeholder
                continue
            else:
                new_paragraphs.append(p)
                continue
        
        # Handle regular text paragraphs
        if needs_translation(p_stripped):
            tasks.append(translate_text(p_stripped, "body"))
            task_info.append((i, "body", None))
            new_paragraphs.append(None)  # placeholder
        else:
            new_paragraphs.append(p)
    
    if not tasks:
        return {"file": fpath.name, "translated": 0, "removed": 0}
    
    results = await asyncio.gather(*tasks)
    
    translated_count = 0
    for (idx, ctx, prefix), result in zip(task_info, results):
        if ctx == "caption":
            new_paragraphs[idx] = f"{prefix}{result}"
            translated_count += 1
        else:
            new_paragraphs[idx] = result
            translated_count += 1
    
    # Remove None entries (hallucinations that were deleted)
    removed = sum(1 for p in new_paragraphs if p is None)
    final_paragraphs = [p for p in new_paragraphs if p is not None]
    
    final_content = '\n\n'.join(final_paragraphs)
    
    # Clean any remaining control characters
    final_content = "".join(c for c in final_content if ord(c) >= 32 or c in ('\t', '\n', '\r'))
    
    fpath.write_text(final_content, encoding="utf-8")
    return {"file": fpath.name, "translated": translated_count, "removed": removed}


async def main():
    md_files = sorted(Path("/home/linux/Documents/MSM/paper/papers/中文翻译").glob("*_原文翻译.md")) + \
               sorted(Path("/home/linux/Documents/MSM/paper/other-paper/中文翻译").glob("*_原文翻译.md"))
    
    # Skip paper 01 which was manually translated
    md_files = [f for f in md_files if not f.name.startswith("01_释放四旋翼特技飞行潜能")]
    
    print(f"=== Retranslating {len(md_files)} files ===\n")
    
    # Process 10 files at a time
    batch_size = 10
    total_translated = 0
    total_removed = 0
    
    for i in range(0, len(md_files), batch_size):
        batch = md_files[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(md_files) - 1) // batch_size + 1
        print(f"Batch {batch_num}/{total_batches} ({len(batch)} files)...")
        
        results = await asyncio.gather(*[process_file(f) for f in batch])
        
        for r in results:
            total_translated += r["translated"]
            total_removed += r["removed"]
            status = f"  {r['file']}: {r['translated']} translated, {r['removed']} hallucinations removed"
            print(status)
        
        print()
    
    print(f"=== DONE ===")
    print(f"Total blocks translated: {total_translated}")
    print(f"Total hallucinations removed: {total_removed}")


if __name__ == "__main__":
    asyncio.run(main())
