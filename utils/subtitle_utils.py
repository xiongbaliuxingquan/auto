"""
subtitle_utils.py
提供 SRT 字幕文件的解析函数，返回带时间轴的字幕条目列表。
"""
import re

def parse_srt(srt_path):
    """
    解析 SRT 文件，返回列表，每个元素为 (start_ms, end_ms, text)
    时间格式：00:00:00,000 --> 00:00:05,000
    """
    def time_to_ms(t):
        t = t.replace(',', '.')
        h, m, s = t.split(':')
        return int(h) * 3600000 + int(m) * 60000 + int(float(s) * 1000)

    entries = []
    with open(srt_path, 'r', encoding='utf-8-sig') as f:
        content = f.read().strip()
        blocks = re.split(r'\n\s*\n', content)
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
            time_line = lines[1]
            match = re.match(r'(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})', time_line)
            if not match:
                continue
            start_str, end_str = match.groups()
            start_ms = time_to_ms(start_str)
            end_ms = time_to_ms(end_str)
            text = '\n'.join(lines[2:]).strip()
            # 清洗：去除多余空白
            text = re.sub(r'\s+', ' ', text).strip()
            entries.append((start_ms, end_ms, text))
    return entries