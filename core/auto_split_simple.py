#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
auto_split_simple.py
一键成片模式：从资产库和 shots.txt 生成英文视频提示词（LTX 2.3 格式）。
输入：工作目录
输出：易读版分镜文件（含提示词）、shot_data.json
"""

import sys
import os
import io
import re
import json
import argparse
import traceback
import time
import hashlib
from datetime import datetime
from typing import List, Dict

# 强制控制台输出 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import settings, concurrent_utils
from utils.ai_utils import call_deepseek
from utils.error_logger import log_error

# 日志目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ===================== 带时间戳的日志 =====================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ===================== 重复检测 =====================
def has_repetition(text: str) -> bool:
    """检测文本中是否存在大量重复字符"""
    if re.search(r'([\u4e00-\u9fa5])\1{4,}', text):   # 连续5个相同中文字符
        return True
    if re.search(r'\b(\w+)\s+\1\s+\1\b', text):       # 英文单词重复3次
        return True
    return False

# ===================== 翻译辅助 =====================
def translate_chunk(text: str, cache_file: str) -> str:
    """翻译一段中文文本为英文，使用文件缓存"""
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()
    try:
        prompt = f"请将以下中文翻译成英文，只输出英文翻译，不要添加任何解释或额外内容：\n\n{text}"
        result = call_deepseek(prompt, temperature=0.3, max_tokens=2000)
        result = result.strip()
        # 保存缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(result)
        return result
    except Exception as e:
        log(f"翻译失败: {e}，使用原文")
        return text

def translate_global_assets(work_dir: str) -> str:
    """读取 assets_global.txt，翻译其中的描述性内容，返回英文版文本"""
    global_path = os.path.join(work_dir, "assets_global.txt")
    if not os.path.exists(global_path):
        return ""

    with open(global_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否已经翻译过（通过缓存文件）
    cache_path = os.path.join(work_dir, "assets_global_en.txt")
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            return f.read()

    # 解析整体视觉风格（第一行）
    style_match = re.search(r'- 整体视觉风格：\s*(.*?)(?=\n-|\n\Z)', content, re.DOTALL)
    overall_style = ""
    if style_match:
        original_style = style_match.group(1).strip()
        if re.search(r'[\u4e00-\u9fa5]', original_style):
            overall_style = translate_chunk(original_style, os.path.join(work_dir, "trans_cache_style.txt"))
        else:
            overall_style = original_style

    # 解析角色固定属性块（从“- 角色固定属性：”之后开始）
    char_block_match = re.search(r'- 角色固定属性：\s*\n(.*?)(?=\n-|\n\Z)', content, re.DOTALL)
    char_lines = []
    if char_block_match:
        char_block = char_block_match.group(1)
        # 按行分割，每行是一个角色描述（以“  【”开头）
        for line in char_block.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 匹配角色描述行
            match = re.search(r'【.*?】\s*性别：[^，]+，年龄：[^，]+，发型：[^，]+，发色：[^，]+，脸型：[^，]+，身高：[^，]+，体型：[^，]+，惯用着装：[^，]+，气质描述：([^，]+)', line)
            if match:
                original_trait = match.group(1).strip()
                if re.search(r'[\u4e00-\u9fa5]', original_trait):
                    # 为每个角色生成独立缓存文件（基于原文哈希）
                    hash_key = hashlib.md5(line.encode()).hexdigest()[:8]
                    cache_trait = os.path.join(work_dir, f"trans_cache_char_{hash_key}.txt")
                    translated_trait = translate_chunk(original_trait, cache_trait)
                    line = line.replace(f"气质描述：{original_trait}", f"气质描述：{translated_trait}")
                char_lines.append(f"  {line}")
            else:
                # 如果不是角色描述行（如空行或注释），跳过
                pass

    # 组装英文版资产文本
    en_content = f"- 整体视觉风格：{overall_style}\n"
    if char_lines:
        en_content += "- 角色固定属性：\n"
        en_content += "\n".join(char_lines)

    # 保存缓存
    with open(cache_path, 'w', encoding='utf-8') as f:
        f.write(en_content)
    return en_content

# ===================== 镜头解析 =====================
def parse_shots_file(shots_path: str) -> List[Dict]:
    """解析 shots.txt，返回镜头列表"""
    shots = []
    with open(shots_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    total = len(lines)
    while i < total:
        line = lines[i].strip()
        if line.startswith('【镜头') and '：' in line:
            match = re.match(r'【镜头(\d+)-(\d+)：([^】]*)】', line)
            if not match:
                match_old = re.match(r'【镜头(\d+)：([^】]*)】', line)
                if match_old:
                    seg_id = 1
                    shot_idx = int(match_old.group(1))
                    title = match_old.group(2).strip()
                else:
                    i += 1
                    continue
            else:
                seg_id = int(match.group(1))
                shot_idx = int(match.group(2))
                title = match.group(3).strip()

            shot = {
                'seg_id': seg_id,
                'shot_idx': shot_idx,
                'title': title,
                'scene': '',
                'roles': [],
                'action': '',
                'dialogue': '',
                'visual': '',
                'duration': 10.0,
                'emotion': '',
                'region': '全球·无明确时代'
            }

            i += 1
            while i < total and not lines[i].strip().startswith('【镜头') and not lines[i].strip().startswith('==========================='):
                subline = lines[i].strip()
                if subline.startswith('- 场景：'):
                    shot['scene'] = subline.split('：', 1)[-1].strip()
                elif subline.startswith('- 角色：'):
                    roles_str = subline.split('：', 1)[-1].strip()
                    shot['roles'] = [r.strip() for r in roles_str.split(',')]
                elif subline.startswith('- 动作：'):
                    shot['action'] = subline.split('：', 1)[-1].strip()
                elif subline.startswith('- 对白：'):
                    shot['dialogue'] = subline.split('：', 1)[-1].strip()
                elif subline.startswith('- 视觉描述：'):
                    shot['visual'] = subline.split('：', 1)[-1].strip()
                elif subline.startswith('- 时长：'):
                    dur_str = subline.split('：', 1)[-1].strip()
                    try:
                        shot['duration'] = float(dur_str.replace('秒', ''))
                    except:
                        pass
                elif subline.startswith('- 情绪基调：'):
                    shot['emotion'] = subline.split('：', 1)[-1].strip()
                elif subline.startswith('- 地域：'):
                    shot['region'] = subline.split('：', 1)[-1].strip()
                i += 1
            shots.append(shot)
        else:
            i += 1
    return shots

# ===================== 读取资产文件 =====================
def read_asset_file(filepath: str) -> str:
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""

# ===================== 构建单个镜头的 prompt =====================
def build_shot_prompt(shot: Dict, global_assets: str, local_assets: str) -> str:
    """构建提示词，global_assets 已经是英文版"""
    roles_str = ', '.join(shot['roles']) if shot['roles'] else '无'

    # 从全局资产中提取整体视觉风格（英文）
    overall_style = ""
    if global_assets:
        style_match = re.search(r'- 整体视觉风格：\s*(.*?)(?=\n-|\n\Z)', global_assets, re.DOTALL)
        if style_match:
            overall_style = style_match.group(1).strip()

    style_instruction = ""
    if overall_style:
        style_instruction = f"""
【整体视觉风格】（必须严格遵循，不得偏离）
{overall_style}
"""

    # 从全局资产中提取角色固定特征（英文）
    character_desc = ""
    if global_assets:
        match = re.search(
            r'【.*?】\s*性别：[^，]+，年龄：[^，]+，发型：[^，]+，发色：[^，]+，脸型：[^，]+，身高：[^，]+，体型：[^，]+，惯用着装：[^，]+，气质描述：[^，]+',
            global_assets
        )
        if match:
            character_desc = match.group(0).strip()

    # 从局部资产中提取临时服装描述（中文）
    temp_clothing = ""
    if local_assets:
        clothing_match = re.search(r'角色服装：\s*([^\n]+)', local_assets)
        if clothing_match:
            temp_clothing = clothing_match.group(1).strip()

    guidance = ""
    if character_desc:
        guidance += f"""
【角色固定特征】（必须保留，描述人物的发型、发色、脸型、身高、体型、惯用着装等）
{character_desc}

**重要：角色固定属性中的名称格式为“种族 角色名”，例如“熊猫 阿六”。在生成 Subject + Action 时，必须根据种族选择正确的英文名词，例如：
- 种族为“熊猫” → “a panda named A-Liu”
- 种族为“人类” → “a young man named A-Liu” 或 “a young woman named A-Liu”
- 种族为“机器人” → “a robot named A-Liu”
- 如果未指定种族，则默认为人类。
请严格遵守此规则，不要将熊猫描述为人类。**
"""
    if temp_clothing:
        guidance += f"""
【当前镜头临时变化】（服装状态、污渍等）
{temp_clothing}
"""
    guidance += """
请生成英文视频提示词，其中 Subject + Action 部分必须：
- 包含角色的固定特征（发型、脸型、身高、体型、惯用着装等）
- 融入临时变化（如污渍、特殊服装）
- 结合当前动作
- **重要：不要使用任何方括号占位符（如 [发型]），必须写出具体描述，例如“short black hair, round face”。**
"""

    prompt = f"""你是一位专业的视频分镜设计师。请根据以下信息，为这个镜头生成一个高质量的英文视频提示词，严格遵循 LTX 2.3 格式。

{style_instruction}

{guidance}

【当前镜头原始信息】
- 场景：{shot['scene']}
- 角色：{roles_str}
- 动作：{shot['action']}
- 对白：{shot['dialogue']}
- 视觉描述：{shot['visual']}
- 时长：{shot['duration']}秒
- 情绪：{shot['emotion']}
- 地域：{shot['region']}

请生成一个英文视频提示词，必须包含以下标签（英文），按顺序输出，每个标签占一行，标签后跟冒号和内容：

Overall Atmosphere:
Setting:
Subject + Action:
Lens + Focal Length:
Visual Style:  （必须基于【整体视觉风格】中的描述，用英文书写，并保持风格一致，禁止出现任何中文字符）
Movement / Time:
Protection Conditions: No text, no flicker, no logo.

**重要**：请严格模仿以下示例的格式和语言风格，特别是 Visual Style 部分要使用英文描述（如 "Soft, delicate colors, dreamlike lighting"），不要使用中文。对白部分保留中文引号。

示例：
Overall Atmosphere: A vast, lonely, and melancholic scene at dusk, with a sense of suppressed longing.
Setting: At the foot of the Great Wall in the Qin Dynasty, on a loess slope during the golden hour of sunset.
Subject + Action: The silhouette of a sturdy young laborer named Shi, sitting alone on the slope, facing the distant horizon. He is slightly hunched over, head bowed.
Lens + Focal Length: Wide-angle lens, low angle to exaggerate scale, strong backlighting.
Visual Style: Studio Ghibli-style 2D animation. Soft, delicate colors, dreamlike lighting, painterly quality.
Movement / Time: Extremely slow push-in on the static subject over 10 seconds, dust particles moving gently in backlight.
Protection Conditions: No text, no flicker, no logo.

要求：
- 所有内容用英文书写，但对白、旁白部分必须保留中文，并用中文引号“”包裹。
- 对白应放在 Subject + Action 中，格式如：某人说：“对白内容”。
- 如果对白字段为空，则不要在 Subject + Action 中加入对白。
- 严格基于提供的视觉描述、角色、动作等信息，可以适当丰富技术细节，但不得改变核心意象。
- 防护条件固定为“No text, no flicker, no logo.”。
- 不要添加任何额外解释，只输出上述标签和内容。

请开始输出："""
    return prompt

# ===================== 并发工作函数（带重试和重复检测） =====================
def process_shot(shot: Dict, global_assets: str, local_assets_by_seg: Dict[int, str]) -> Dict:
    seg_id = shot['seg_id']
    local_assets = local_assets_by_seg.get(seg_id, "")
    prompt_text = build_shot_prompt(shot, global_assets, local_assets)

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            temperature = 0.7 + (attempt - 1) * 0.1
            result = call_deepseek(prompt_text, temperature=temperature, max_tokens=3000)
            result = result.strip()
            if result.startswith("```"):
                result = re.sub(r'```\w*\n?', '', result).strip()

            # 提取“- 提示词：”后面的内容
            prompt_match = re.search(r'-\s*提示词：\s*(.*)', result, re.DOTALL)
            if prompt_match:
                candidate = prompt_match.group(1).strip()
            else:
                candidate = result

            if has_repetition(candidate):
                print(f"⚠️ 镜头 {shot['seg_id']}-{shot['shot_idx']} 第{attempt}次尝试检测到重复，重试...")
                if attempt == max_retries:
                    shot['_error'] = "重复字符异常（多次重试后仍失败）"
                    shot['prompt'] = ""
                    return shot
                time.sleep(2)
                continue

            shot['prompt'] = candidate
            shot['_error'] = None
            return shot
        except Exception as e:
            print(f"❌ 镜头 {shot['seg_id']}-{shot['shot_idx']} 第{attempt}次尝试失败:")
            traceback.print_exc()
            if attempt == max_retries:
                log_error('auto_split_simple', f'镜头{shot["seg_id"]}-{shot["shot_idx"]}生成失败', str(e))
                shot['prompt'] = ""
                shot['_error'] = str(e)
                return shot
            time.sleep(2)

    return shot

# ===================== 主函数 =====================
def main():
    parser = argparse.ArgumentParser(description="一键成片模式：生成英文视频提示词")
    parser.add_argument("work_dir", help="工作目录")
    args = parser.parse_args()
    work_dir = args.work_dir

    shots_path = os.path.join(work_dir, "shots.txt")
    if not os.path.exists(shots_path):
        print(f"错误：未找到 {shots_path}")
        sys.exit(1)

    # 读取并翻译全局资产
    global_assets_en = translate_global_assets(work_dir)

    # 读取所有段落局部资产（保持中文）
    local_assets_by_seg = {}
    for f in os.listdir(work_dir):
        if f.startswith("assets_paragraph_") and f.endswith(".txt"):
            seg_id_str = f.split('_')[2].split('.')[0]
            try:
                seg_id = int(seg_id_str)
                local_assets_by_seg[seg_id] = read_asset_file(os.path.join(work_dir, f))
            except ValueError:
                continue

    shots = parse_shots_file(shots_path)
    if not shots:
        print("错误：未解析到任何镜头")
        sys.exit(1)

    print(f"共解析到 {len(shots)} 个镜头，开始并发处理...")

    items = [(shot, global_assets_en, local_assets_by_seg) for shot in shots]
    results, errors = concurrent_utils.concurrent_process(
        items,
        lambda item, _: process_shot(item[0], item[1], item[2]),
        max_workers=settings.MAX_WORKERS,
        ordered=True,
        progress_callback=lambda idx, res, success: print(f"镜头 {idx+1}/{len(shots)} 处理完成")
    )

    for i, res in enumerate(results):
        if res is not None:
            shots[i] = res

    failed_shots = [s for s in shots if s.get('_error')]
    if failed_shots:
        print(f"\n⚠️ 共有 {len(failed_shots)} 个镜头生成失败（提示词为空），请稍后重试。")
        for s in failed_shots[:5]:
            print(f"  - 镜头 {s['seg_id']}-{s['shot_idx']}: {s['_error'][:100]}")
        print("  详细错误请查看控制台输出的堆栈信息或 logs/error_log.txt。")
    else:
        print("所有镜头提示词生成成功！")

    timestamp = datetime.now().strftime("%m%d_%H%M")
    shot_data_file = os.path.join(work_dir, f"shot_data_{timestamp}.json")
    with open(shot_data_file, 'w', encoding='utf-8') as f:
        json.dump(shots, f, ensure_ascii=False, indent=2)
    print(f"镜头结构化数据已保存至 {shot_data_file}")

    def format_shot(shot):
        prompt = shot.get('prompt', '')
        if not prompt:
            prompt = "[生成失败，请重试]"
        return f"""【镜头{shot['seg_id']}-{shot['shot_idx']}：{shot['title']}】
- 场景：{shot['scene']}
- 角色：{', '.join(shot['roles'])}
- 动作：{shot['action']}
- 对白：{shot['dialogue']}
- 视觉描述：{shot['visual']}
- 时长：{shot['duration']:.1f}秒
- 情绪基调：{shot['emotion']}
- 地域：{shot['region']}
- 提示词：
{prompt}"""

    readable_parts = [format_shot(shot) for shot in shots]
    readable_file = os.path.join(work_dir, f"分镜结果_易读版_{timestamp}.txt")
    with open(readable_file, 'w', encoding='utf-8') as f:
        f.write('\n\n===========================\n\n'.join(readable_parts))
    print(f"易读版分镜文件已生成：{readable_file}")

    print("处理完成。")

if __name__ == "__main__":
    main()