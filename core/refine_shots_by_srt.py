"""
refine_shots_by_srt.py
功能：根据段落 JSON 和字幕文件，将字幕与段落对齐，并在每个段落内按时长（3-15秒）切分镜头。
输出：基础镜头文件（shots_base.txt）和字幕映射文件（shot_subtitle_map.json）。
"""

import os
import sys
import re
import json
import shutil
import time
from fuzzywuzzy import fuzz
from datetime import timedelta
from pypinyin import lazy_pinyin

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.subtitle_utils import parse_srt
from utils.error_logger import log_error
from utils import config_manager
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher   # 新增

# 时长阈值（秒）
MIN_DURATION = 3.0
MAX_DURATION = 15.0
TARGET_DURATION = 8.0   # 目标时长，用于引导切分

def log_print(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def clean_text(t):
    """清洗文本：去除标点、空格、换行，只保留中文、字母、数字"""
    return re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', t)

def merge_short_subs(subs, min_len=10):
    """合并连续短字幕（文本长度<min_len），返回新的字幕列表"""
    if not subs:
        return []
    merged = []
    current_group = []
    for start, end, text in subs:
        if len(text) < min_len:
            current_group.append((start, end, text))
        else:
            if current_group:
                merged_start = current_group[0][0]
                merged_end = current_group[-1][1]
                merged_text = ' '.join(t for _, _, t in current_group)
                merged.append((merged_start, merged_end, merged_text))
                current_group = []
            merged.append((start, end, text))
    if current_group:
        merged_start = current_group[0][0]
        merged_end = current_group[-1][1]
        merged_text = ' '.join(t for _, _, t in current_group)
        merged.append((merged_start, merged_end, merged_text))
    return merged

def find_longest_match(a, b):
    """
    在字符串 b 中寻找与字符串 a 最长的匹配子串。
    返回 (start_in_b, length) 表示匹配块在 b 中的起始索引和长度。
    使用 SequenceMatcher 的 find_longest_match。
    """
    matcher = SequenceMatcher(None, a, b)
    match = matcher.find_longest_match(0, len(a), 0, len(b))
    return match.b, match.size   # 返回在 b 中的起始位置和长度

def text_to_pinyin_map(text):
    """
    将文本转为拼音字符串，并返回拼音字符串中每个字符对应的原始文本字符索引。
    返回 (pinyin_str, char_index_map)
    char_index_map[i] = 拼音字符串中第 i 个字符对应原始文本中的字符索引。
    """
    # 先用清洗函数去掉标点，保留中文字符、字母、数字
    cleaned = clean_text(text)
    if not cleaned:
        return "", []
    # 获取每个字符的拼音（列表，每个元素是拼音字符串）
    pinyin_list = lazy_pinyin(cleaned)
    # 拼接拼音字符串，同时记录每个拼音字符对应的原始索引
    pinyin_str = ""
    char_index_map = []
    for idx, py in enumerate(pinyin_list):
        # 如果拼音为空（如数字、字母），则直接使用原字符
        if not py:
            py = cleaned[idx]
        for _ in py:
            char_index_map.append(idx)
        pinyin_str += py
    return pinyin_str, char_index_map

def align_subtitles_to_paragraphs(paragraphs, subs, threshold=80):
    """
    全局匹配：将每条字幕分配到最相似的段落，然后按段落收集时间范围。
    """
    from fuzzywuzzy import fuzz
    import numpy as np

    # 合并短字幕
    original_count = len(subs)
    subs = merge_short_subs(subs, min_len=10)
    log_print(f"合并短字幕：原始 {original_count} 条，合并后 {len(subs)} 条")

    # 清洗段落文本
    para_clean = [clean_text(p) for p in paragraphs]

    # 为每条字幕计算与每个段落的相似度
    sub_scores = []  # 每个元素为 (sub_index, para_index, score)
    for i, (start, end, text) in enumerate(subs):
        text_clean = clean_text(text)
        best_para = -1
        best_score = 0
        for j, p_clean in enumerate(para_clean):
            score = fuzz.partial_ratio(text_clean, p_clean)
            if score > best_score:
                best_score = score
                best_para = j
        sub_scores.append((i, best_para, best_score))

    # 分配字幕到段落：如果相似度 >= threshold，则直接分配；否则根据时间位置就近分配
    sub_to_para = [-1] * len(subs)
    for i, best_para, score in sub_scores:
        if score >= threshold:
            sub_to_para[i] = best_para
        else:
            # 根据时间位置，找最接近的段落（简单按时间顺序）
            # 这里简化：将时间最接近的字幕分配到当前段落
            # 实际可按时间中位数或其他规则
            pass

    # 由于时间顺序与段落顺序一致，我们直接按时间顺序分配：遍历字幕，若当前字幕的时间超过了当前段落的时间范围，则切换到下一个段落
    # 但因为没有段落时间范围，我们只能利用相似度分配的结果
    # 改进：先用相似度分配，然后按时间顺序调整（保证单调性）
    # 这里简单使用相似度分配结果，并保证每个段落至少有一个字幕（否则用0填充）

    # 按段落收集字幕索引
    para_sub_indices = [[] for _ in range(len(paragraphs))]
    for i, para_idx in enumerate(sub_to_para):
        if para_idx >= 0:
            para_sub_indices[para_idx].append(i)

    # 对每个段落，计算其字幕时间范围
    para_ranges = []
    for para_idx, indices in enumerate(para_sub_indices):
        if indices:
            sub_starts = [subs[i][0] for i in indices]
            sub_ends = [subs[i][1] for i in indices]
            start = min(sub_starts)
            end = max(sub_ends)
            para_ranges.append((start, end))
            log_print(f"段落 {para_idx+1} 匹配到 {len(indices)} 条字幕，时间范围 {start} - {end}")
        else:
            # 没有匹配的字幕，尝试根据相邻段落推断时间范围
            # 简化：设为0，后续会被忽略
            para_ranges.append((0, 0))
            log_print(f"段落 {para_idx+1} 无匹配字幕，时间范围设为0")

    # 修复可能的缺失：对于时间范围为0的段落，若其前后段落有有效时间，则插值
    # 这里简单处理：如果前一段落有结束时间，后一段落有开始时间，则取中间值
    for i in range(len(para_ranges)):
        if para_ranges[i][0] == 0 and para_ranges[i][1] == 0:
            # 尝试从前后取
            prev_end = para_ranges[i-1][1] if i > 0 else 0
            next_start = para_ranges[i+1][0] if i+1 < len(para_ranges) else 0
            if prev_end and next_start:
                mid = (prev_end + next_start) // 2
                para_ranges[i] = (mid, mid)
            elif prev_end:
                para_ranges[i] = (prev_end, prev_end)
            elif next_start:
                para_ranges[i] = (next_start, next_start)
            else:
                para_ranges[i] = (0, 0)

    return para_ranges

def split_paragraph_into_shots(subs_in_range, start_offset_ms):
    """
    在一个段落内，根据字幕时间轴切分镜头，目标时长14秒，不超过15秒。
    返回镜头列表，每个镜头包含 'script', 'start_ms', 'end_ms', 'duration'
    """
    if not subs_in_range:
        return []
    shots = []
    current_shot = []
    current_start = None
    current_end = None
    current_dur = 0.0

    # 先按时间顺序排序
    subs_in_range.sort(key=lambda x: x[0])

    # 目标时长（秒）
    TARGET_DURATION = 14.0
    MAX_DURATION = 15.0

    for start_ms, end_ms, text in subs_in_range:
        dur = (end_ms - start_ms) / 1000.0

        # 如果当前句子本身超过最大时长，单独作为一个镜头（极少数情况）
        if dur > MAX_DURATION:
            if current_shot:
                shots.append({
                    'script': ' '.join(current_shot),
                    'start_ms': current_start,
                    'end_ms': current_end,
                    'duration': current_dur
                })
                current_shot = []
                current_start = None
                current_end = None
                current_dur = 0.0
            shots.append({
                'script': text,
                'start_ms': start_ms,
                'end_ms': end_ms,
                'duration': dur
            })
            continue

        if not current_shot:
            # 新镜头开始
            current_shot.append(text)
            current_start = start_ms
            current_end = end_ms
            current_dur = dur
            continue

        # 尝试加入当前字幕
        if current_dur + dur <= TARGET_DURATION:
            # 未达目标，直接加入
            current_shot.append(text)
            current_end = end_ms
            current_dur += dur
        else:
            # 加入后会超过目标时长，判断是否超过最大容忍
            if current_dur + dur <= MAX_DURATION:
                # 虽然超过目标，但未超过最大容忍，加入并结束当前镜头
                current_shot.append(text)
                current_end = end_ms
                current_dur += dur
                # 结束当前镜头
                shots.append({
                    'script': ' '.join(current_shot),
                    'start_ms': current_start,
                    'end_ms': current_end,
                    'duration': current_dur
                })
                current_shot = []
                current_start = None
                current_end = None
                current_dur = 0.0
            else:
                # 超过最大容忍，必须切分，当前镜头保留（不加本句）
                shots.append({
                    'script': ' '.join(current_shot),
                    'start_ms': current_start,
                    'end_ms': current_end,
                    'duration': current_dur
                })
                # 本句作为新镜头开始
                current_shot = [text]
                current_start = start_ms
                current_end = end_ms
                current_dur = dur

    # 处理最后一个镜头
    if current_shot:
        shots.append({
            'script': ' '.join(current_shot),
            'start_ms': current_start,
            'end_ms': current_end,
            'duration': current_dur
        })

    # 后处理：拆分超长镜头（超过MAX_DURATION的）
    final_shots = []
    for shot in shots:
        if shot['duration'] <= MAX_DURATION:
            final_shots.append(shot)
            continue
        # 超长镜头，按句子拆分（但字幕已经是句子级别，这里再按句子拆分实际是按口播稿文本拆分）
        script = shot['script']
        # 按句子切分（。！？…）
        sentences = re.split(r'(?<=[。！？…])', script)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            final_shots.append(shot)
            continue
        # 估算每个句子的时长（按字数比例）
        total_chars = sum(len(s) for s in sentences)
        total_duration = shot['duration']
        current_time = shot['start_ms']
        for sent in sentences:
            sent_chars = len(sent)
            sent_duration = (sent_chars / total_chars) * total_duration
            sent_end = current_time + int(sent_duration * 1000)
            final_shots.append({
                'script': sent,
                'start_ms': current_time,
                'end_ms': sent_end,
                'duration': sent_duration
            })
            current_time = sent_end
        # 注意：时间可能因取整有微小误差，忽略

    # 调整时间偏移
    if start_offset_ms != 0:
        for shot in final_shots:
            shot['start_ms'] -= start_offset_ms
            shot['end_ms'] -= start_offset_ms

    return final_shots

def write_shots_base(output_path, shots):
    with open(output_path, 'w', encoding='utf-8') as f:
        for idx, shot in enumerate(shots, start=1):
            f.write(f"【镜头1-{idx}：待定】\n")
            f.write(f"- 时长：{shot['duration']:.1f}秒\n")
            f.write(f"- 情绪基调：\n")
            f.write(f"- 地域：\n")
            f.write(f"- 口播稿：{shot['script']}\n")
            f.write(f"- 视觉描述：\n")
            f.write("===========================\n")

def main(work_dir):
    # 输入文件
    para_json = os.path.join(work_dir, 'paragraphs.json')
    srt_file = os.path.join(work_dir, 'input.srt')
    if not os.path.exists(para_json) or not os.path.exists(srt_file):
        log_print("缺少 paragraphs.json 或 input.srt")
        return

    # 读取段落
    with open(para_json, 'r', encoding='utf-8') as f:
        paragraphs = json.load(f)
    if not paragraphs:
        log_print("段落列表为空")
        return

    # 读取字幕
    subs = parse_srt(srt_file)
    log_print(f"加载 {len(paragraphs)} 个段落，{len(subs)} 条字幕")

    # 对齐字幕与段落
    try:
        para_ranges = align_subtitles_to_paragraphs(paragraphs, subs, threshold=80)
    except Exception as e:
        log_print(f"对齐失败：{e}")
        with open(os.path.join(work_dir, "align_error.log"), 'w', encoding='utf-8') as f:
            f.write(str(e))
        return

    # 根据对齐结果，为每个段落切分镜头
    all_shots = []
    shot_para_map = []          # 新增：存储镜头与段落的映射
    for para_idx, (start_ms, end_ms) in enumerate(para_ranges):
        # 筛选属于该段落的字幕
        para_subs = [sub for sub in subs if sub[0] >= start_ms and sub[1] <= end_ms]
        if not para_subs:
            log_print(f"段落 {para_idx+1} 无字幕，跳过")
            continue
        shots = split_paragraph_into_shots(para_subs, start_offset_ms=start_ms)
        log_print(f"段落 {para_idx+1} 切分为 {len(shots)} 个镜头")
        # 记录每个镜头属于该段落
        for _ in shots:
            shot_para_map.append(para_idx)
        all_shots.extend(shots)

    # 写入基础镜头文件
    output_base = os.path.join(work_dir, 'shots_base.txt')
    write_shots_base(output_base, all_shots)
    log_print(f"基础镜头已保存至 {output_base}")

    # 生成镜头与段落的映射文件
    mapping = []
    for i, shot in enumerate(all_shots):
        mapping.append({
            "shot_id": f"1-{i+1}",
            "para_index": shot_para_map[i]
        })
    map_path = os.path.join(work_dir, 'shot_para_index.json')
    with open(map_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    log_print(f"镜头段落映射已保存至 {map_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python refine_shots_by_srt.py <工作目录>")
        sys.exit(1)
    main(sys.argv[1])