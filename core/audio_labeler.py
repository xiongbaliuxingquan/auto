# audio_labeler.py
"""
文本标签生成：调用 AI 将原始文稿转换为带 Fish S2 标签的文本，并保存为 segments_info.json。
"""

import os
import sys
import json
import re
from typing import List, Dict, Optional

# 从 utils.audio_utils 导入（因为 audio_utils 在 utils 目录）
from utils.audio_utils import call_deepseek

def label_audio(work_dir: str, script_path: str, max_retries: int = 2) -> Optional[List[Dict]]:
    """生成带标签的分段信息，返回 segments 列表，并保存到工作目录"""
    with open(script_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    prompt = f"""你是一个专业的语音合成标签设计师。请将以下口播稿文本转换为适合 Fish S2 语音合成模型的标签文本。

要求：
1. 根据语义，将全文分割为若干自然段落，每段不超过 350 字（中文）。
2. 你已理解文档，请按照文档叙述类型模拟出全文朗读需换气位置，在需换气位置加入[inhale]。换气应模拟人类朗读的自然呼吸停顿，不要在每个自然段都加，而是根据语义、情感和句子长度合理放置。
3. 根据情感变化，在适当位置插入情感标签（如 `[激昂]`、`[冷静]`、`[严肃]`、`[自豪]` 等）。情感标签应放在该句或该段之前，且每个标签不超过 4 个字。
4. 对于突发情感变化（如大喊），应在该句前单独添加标签（如 `[大喊]`）。
5. 输出格式：纯文本，标签用方括号，文本正常书写。整个文本应为一个连续的字符串，**段落之间用且仅用一个空行分隔**，每个段落内部不要出现空行。标签与文字之间用空格分隔即可。

原始文本：
{raw_text}

请输出处理后的文本："""

    for attempt in range(max_retries):
        try:
            result = call_deepseek(prompt, temperature=0.7, max_tokens=4000)
            # 按两个及以上换行符分割，但只取非空段落
            raw_paragraphs = re.split(r'\n\s*\n', result.strip())
            # 去除空段落并去重（相邻相同）
            unique_paragraphs = []
            for p in raw_paragraphs:
                p = p.strip()
                if not p:
                    continue
                if not unique_paragraphs or p != unique_paragraphs[-1]:
                    unique_paragraphs.append(p)
            segments = []
            idx = 1
            for para in unique_paragraphs:
                # 如果段落超过 350 字，强制按句子切分
                if len(para) > 350:
                    sentences = re.split(r'(?<=[。！？])', para)
                    current = ""
                    for sent in sentences:
                        if len(current) + len(sent) <= 350:
                            current += sent
                        else:
                            if current:
                                segments.append({"index": idx, "text": current.strip()})
                                idx += 1
                            current = sent
                    if current:
                        segments.append({"index": idx, "text": current.strip()})
                        idx += 1
                else:
                    segments.append({"index": idx, "text": para.strip()})
                    idx += 1
            # 保存 segments_info.json
            segments_path = os.path.join(work_dir, "segments_info.json")
            with open(segments_path, 'w', encoding='utf-8') as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
            # 同时保存 labeled_text.txt 预览
            labeled_path = os.path.join(work_dir, "labeled_text.txt")
            with open(labeled_path, 'w', encoding='utf-8') as f:
                # 将每个段落内部的换行符替换为空格，使其成为单行
                cleaned_paragraphs = [re.sub(r'\n+', ' ', seg["text"]) for seg in segments]
                # 用两个换行符分隔段落
                f.write("\n\n".join(cleaned_paragraphs))
            return segments
        except Exception as e:
            print(f"尝试 {attempt+1} 失败: {e}")
            if attempt == max_retries - 1:
                raise
    return None

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python audio_labeler.py <工作目录> <文本文件>")
        sys.exit(1)
    work_dir = sys.argv[1]
    script_file = sys.argv[2]
    label_audio(work_dir, script_file)