import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.subtitle_utils import parse_srt
from fuzzywuzzy import fuzz
from fuzzywuzzy import process

def load_shot_sentences(shots_path):
    """从 shots.txt 提取每个镜头的口播稿，并按句子切分成短句列表，每个短句带上镜头ID"""
    sentences = []  # (镜头ID, 短句文本)
    with open(shots_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('【镜头') and '：' in line:
            # 提取镜头ID
            shot_id = re.search(r'【镜头(\d+-\d+)', line).group(1)
            i += 1
            script = ""
            while i < len(lines) and not lines[i].strip().startswith('==========================='):
                subline = lines[i].strip()
                if subline.startswith('- 口播稿：'):
                    script = subline.split('：', 1)[-1].strip()
                    break
                i += 1
            if script:
                # 按句子切分（。！？）
                # 注意：这里简单用正则切分，可能不完美，但够用
                parts = re.split(r'(?<=[。！？])', script)
                for part in parts:
                    if part.strip():
                        sentences.append((shot_id, part.strip()))
            # 跳过分隔线
            while i < len(lines) and lines[i].strip().startswith('==========================='):
                i += 1
        else:
            i += 1
    return sentences

def clean_subtitle_text_with_info(sub_text, shot_sentences, threshold=85):
    """返回 (清洗后的文本, 最高相似度, 匹配到的短句, 匹配到的镜头ID)"""
    if not shot_sentences:
        return sub_text, 0, None, None
    # 提取所有短句文本
    sentences_text = [s[1] for s in shot_sentences]
    match = process.extractOne(sub_text, sentences_text, scorer=fuzz.partial_ratio)
    if match:
        best_text, best_score = match[0], match[1]
        if best_score >= threshold:
            # 找到对应的镜头ID
            for sid, stext in shot_sentences:
                if stext == best_text:
                    return best_text, best_score, best_text, sid
    return sub_text, 0, None, None

def format_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def clean_srt(srt_path, shots_path, output_path, threshold=85):
    # 解析原始字幕
    subs = parse_srt(srt_path)
    # 加载镜头短句列表
    shot_sentences = load_shot_sentences(shots_path)
    if not shot_sentences:
        print("警告：未找到任何镜头的口播稿短句，无法清洗。")
        return False

    cleaned_subs = []
    not_cleaned = []  # 记录未清洗的字幕 (序号, 原文)
    for idx, (start, end, text) in enumerate(subs, start=1):
        cleaned_text, score, matched_sentence, shot_id = clean_subtitle_text_with_info(text, shot_sentences, threshold)
        cleaned_subs.append((start, end, cleaned_text))
        if cleaned_text == text:  # 未清洗
            not_cleaned.append((idx, text))
        else:
            print(f"  字幕 {idx}: 匹配到镜头 {shot_id}，原文'{text}' -> 清洗后'{cleaned_text}'")

    # 输出统计
    total = len(subs)
    cleaned_cnt = total - len(not_cleaned)
    print(f"清洗完成，共 {total} 条字幕，成功清洗 {cleaned_cnt} 条，未清洗 {len(not_cleaned)} 条。")
    if not_cleaned:
        print("\n未清洗的字幕列表（相似度低于阈值）:")
        for idx, txt in not_cleaned:
            print(f"  {idx}: {txt[:80]}")
        # 保存到文件
        uncleaned_file = output_path + ".uncleaned.txt"
        with open(uncleaned_file, 'w', encoding='utf-8') as f:
            for idx, txt in not_cleaned:
                f.write(f"{idx}: {txt}\n")
        print(f"\n未清洗字幕已保存至 {uncleaned_file}")

    # 写回清洗后的 SRT
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, (start, end, text) in enumerate(cleaned_subs, start=1):
            f.write(f"{idx}\n")
            f.write(f"{format_srt_time(start)} --> {format_srt_time(end)}\n")
            f.write(f"{text}\n\n")

    print(f"清洗后的字幕已保存至 {output_path}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python clean_subtitles.py <字幕.srt> <shots.txt> <输出.srt> [阈值]")
        print("示例: python clean_subtitles.py input.srt shots.txt input_cleaned.srt 85")
        sys.exit(1)
    srt_in = sys.argv[1]
    shots_file = sys.argv[2]
    srt_out = sys.argv[3]
    threshold = int(sys.argv[4]) if len(sys.argv) > 4 else 85
    clean_srt(srt_in, shots_file, srt_out, threshold)