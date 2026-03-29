# parsers/ai_response_cleaner.py
import re
import json
import os
from datetime import datetime

def clean(raw: str) -> str:
    """
    主清洗函数，返回清洗后的 JSON 字符串（仍为字符串，但保证可被 json.loads 解析）
    """
    # 1. 去除首尾空白
    raw = raw.strip()

    # 2. 循环去除 markdown 代码块标记，直到不再变化
    while True:
        original = raw
        # 去除开头的 ```json 或 ```
        if raw.startswith('```json'):
            raw = raw[7:].lstrip()
        elif raw.startswith('```'):
            raw = raw[3:].lstrip()
        # 去除结尾的 ```
        if raw.endswith('```'):
            raw = raw[:-3].rstrip()
        if raw == original:
            break
    raw = raw.strip()

    # 3. 提取第一个 [ 到最后一个 ] 之间的内容（如果找不到，尝试提取第一个 { 到最后一个 }）
    #    同时支持数组和对象
    match = re.search(r'(\[.*\])', raw, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # 尝试提取 JSON 对象
        match = re.search(r'(\{.*\})', raw, re.DOTALL)
        if not match:
            raise ValueError("未找到 JSON 数组或对象，清洗失败")
        json_str = match.group(1)


    # 4. 修复中文引号（关键修复）
    #    将中文双引号 “ ” 替换为英文双引号 "
    json_str = json_str.replace('“', '"').replace('”', '"')
    #    将中文单引号 ‘ ’ 替换为英文单引号 '（虽然 JSON 标准不允许单引号，但有些 AI 可能误用）
    json_str = json_str.replace('‘', "'").replace('’', "'")

    # 5. 修复字符串中未转义的双引号（原逻辑保留）
    def fix_value_quotes(m):
        part = m.group(0)
        colon_idx = part.find(':')
        if colon_idx == -1:
            return part
        key_part = part[:colon_idx+1]
        value_part = part[colon_idx+1:].strip()
        if value_part.startswith('"') and value_part.endswith('"'):
            inner = value_part[1:-1]
            inner_fixed = inner.replace('"', '“')
            return key_part + '"' + inner_fixed + '"'
        return part

    json_str = re.sub(r'"[^"]+"\s*:\s*"[^"]*"', fix_value_quotes, json_str, flags=re.DOTALL)

    # 6. 修复多余的逗号
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)

    return json_str

def validate_structure(data):
    """验证解析后的数据是否符合预期的结构（原逻辑不变）"""
    if not isinstance(data, list):
        return False, "根不是数组"
    for i, seg in enumerate(data):
        if not isinstance(seg, dict):
            return False, f"segments[{i}] 不是字典"
        if 'title' not in seg or not isinstance(seg['title'], str):
            return False, f"segments[{i}] 缺少 title 或类型错误"
        if 'content' not in seg or not isinstance(seg['content'], str):
            return False, f"segments[{i}] 缺少 content 或类型错误"
        if 'shots' not in seg or not isinstance(seg['shots'], list):
            return False, f"segments[{i}] 缺少 shots 或不是数组"
        for j, shot in enumerate(seg['shots']):
            if not isinstance(shot, dict):
                return False, f"segments[{i}].shots[{j}] 不是字典"
            if 'visual' not in shot or not isinstance(shot['visual'], str):
                return False, f"segments[{i}].shots[{j}] 缺少 visual 或类型错误"
            if 'duration' not in shot or not isinstance(shot['duration'], int):
                return False, f"segments[{i}].shots[{j}] 缺少 duration 或不是整数"
            if 'emotion' not in shot or not isinstance(shot['emotion'], str):
                return False, f"segments[{i}].shots[{j}] 缺少 emotion 或类型错误"
    return True, ""

def clean_and_parse(raw):
    """清洗并解析，同时进行结构校验，若格式异常则保存文件"""
    cleaned = clean(raw)
    try:
        parsed = json.loads(cleaned)
        valid, msg = validate_structure(parsed)
        if not valid:
            # 保存异常文件
            debug_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
            os.makedirs(debug_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(debug_dir, f"structure_error_{timestamp}.json")
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(json.dumps(parsed, ensure_ascii=False, indent=2))
            print(f"⚠️ 解析后的 JSON 结构异常，已保存至 {filename}，请检查清洗模块。错误：{msg}")
        return parsed
    except json.JSONDecodeError as e:
        # 保存原始失败内容到 logs 目录，带时间戳
        debug_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
        os.makedirs(debug_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(debug_dir, f"json_error_{timestamp}.json")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(raw)  # 保存原始响应
        raise ValueError(f"JSON 解析失败，原始内容已保存至 {filename}，错误：{e}")