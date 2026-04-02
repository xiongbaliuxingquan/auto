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
from datetime import datetime
from typing import List, Dict


# 导入公共工具
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
# ===================== 镜头解析（复制自 auto_split_deepseek，但简化） =====================
def parse_shots_file(shots_path: str) -> List[Dict]:
    """
    解析 shots.txt，返回镜头列表，每个镜头包含字段：
    scene, roles, action, dialogue, visual, duration, emotion, region, title
    以及段落ID和镜头序号（从镜头头中提取）
    """
    shots = []
    with open(shots_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    total = len(lines)
    while i < total:
        line = lines[i].strip()
        if line.startswith('【镜头') and '：' in line:
            # 匹配新格式 【镜头X-Y：标题】 或旧格式 【镜头X：标题】
            match = re.match(r'【镜头(\d+)-(\d+)：([^】]*)】', line)
            if not match:
                # 尝试旧格式（视为段落1）
                match_old = re.match(r'【镜头(\d+)：([^】]*)】', line)
                if match_old:
                    shot_id_num = int(match_old.group(1))
                    seg_id = 1
                    shot_idx = shot_id_num
                    title = match_old.group(2).strip()
                else:
                    i += 1
                    continue
            else:
                seg_id = int(match.group(1))
                shot_idx = int(match.group(2))
                title = match.group(3).strip()

            # 初始化镜头字典
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
            # 读取本镜头的字段
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
    """读取文本文件内容，不存在返回空字符串"""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""


# ===================== 构建单个镜头的 prompt =====================
def build_shot_prompt(shot: Dict, global_assets: str, local_assets: str) -> str:
    """
    构建一个镜头的 AI 提示词，要求生成英文结构化视频提示词。
    """
    # 处理角色列表
    roles_str = ', '.join(shot['roles']) if shot['roles'] else '无'

    # 从全局资产中提取整体视觉风格
    overall_style = ""
    if global_assets:
        import re
        # 匹配类似 "- 整体视觉风格：..." 的行
        style_match = re.search(r'- 整体视觉风格：\s*(.*?)(?=\n-|\n\Z)', global_assets, re.DOTALL)
        if style_match:
            overall_style = style_match.group(1).strip()

    # 构建风格强制指令
    style_instruction = ""
    if overall_style:
        style_instruction = f"""
【整体视觉风格】（必须严格遵循，不得偏离）
{overall_style}
"""

    # 从全局资产中提取角色固定特征（已实现的代码保持不变）
    character_desc = ""
    if global_assets:
        match = re.search(
            r'【.*?】\s*性别：[^，]+，年龄：[^，]+，发型：[^，]+，发色：[^，]+，脸型：[^，]+，身高：[^，]+，体型：[^，]+，惯用着装：[^，]+，气质描述：[^，]+',
            global_assets
        )
        if match:
            character_desc = match.group(0).strip()

    # 从局部资产中提取临时服装描述
    temp_clothing = ""
    if local_assets:
        clothing_match = re.search(r'角色服装：\s*([^\n]+)', local_assets)
        if clothing_match:
            temp_clothing = clothing_match.group(1).strip()

    # 构建角色融合引导语
    guidance = ""
    if character_desc:
        guidance += f"""
【角色固定特征】（必须保留，描述人物的发型、发色、脸型、身高、体型、惯用着装等）
{character_desc}
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
"""

    # 构建完整的 prompt
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
Visual Style:  （必须基于【整体视觉风格】中的描述，用英文书写，并保持风格一致）
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
- 所有内容用英文书写，但对白部分可以保留中文，并用中文引号“”包裹。
- 对白应放在 Subject + Action 中，格式如：某人说：“对白内容”。
- 如果对白字段为空，则不要在 Subject + Action 中加入对白。
- 严格基于提供的视觉描述、角色、动作等信息，可以适当丰富技术细节，但不得改变核心意象。
- 防护条件固定为“No text, no flicker, no logo.”。
- 不要添加任何额外解释，只输出上述标签和内容。

请开始输出："""
    return prompt


# ===================== 并发工作函数 =====================
def process_shot(shot: Dict, global_assets: str, local_assets_by_seg: Dict[int, str]) -> Dict:
    seg_id = shot['seg_id']
    local_assets = local_assets_by_seg.get(seg_id, "")
    prompt_text = build_shot_prompt(shot, global_assets, local_assets)
    try:
        result = call_deepseek(prompt_text, temperature=0.7, max_tokens=2000)
        result = result.strip()
        if result.startswith("```"):
            result = re.sub(r'```\w*\n?', '', result).strip()
        shot['prompt'] = result
    except Exception as e:
        print(f"\n❌ 镜头 {shot['seg_id']}-{shot['shot_idx']} 生成失败:")
        traceback.print_exc()  # 打印完整堆栈
        log_error('auto_split_simple', f'镜头{shot["seg_id"]}-{shot["shot_idx"]}生成失败', str(e))
        shot['prompt'] = shot['visual']  # 后备
        shot['_error'] = str(e)  # 标记错误
    return shot


# ===================== 主函数 =====================
def main():
    parser = argparse.ArgumentParser(description="一键成片模式：生成英文视频提示词")
    parser.add_argument("work_dir", help="工作目录")
    args = parser.parse_args()
    work_dir = args.work_dir

    # 检查必要文件
    shots_path = os.path.join(work_dir, "shots.txt")
    if not os.path.exists(shots_path):
        print(f"错误：未找到 {shots_path}")
        sys.exit(1)

    # 读取全局资产
    global_assets = read_asset_file(os.path.join(work_dir, "assets_global.txt"))

    # 读取所有段落局部资产
    local_assets_by_seg = {}
    for f in os.listdir(work_dir):
        if f.startswith("assets_paragraph_") and f.endswith(".txt"):
            seg_id_str = f.split('_')[2].split('.')[0]
            try:
                seg_id = int(seg_id_str)
                local_assets_by_seg[seg_id] = read_asset_file(os.path.join(work_dir, f))
            except ValueError:
                continue

    # 解析镜头
    shots = parse_shots_file(shots_path)
    if not shots:
        print("错误：未解析到任何镜头")
        sys.exit(1)

    print(f"共解析到 {len(shots)} 个镜头，开始并发处理...")

    # 并发处理每个镜头
    items = [(shot, global_assets, local_assets_by_seg) for shot in shots]
    results, errors = concurrent_utils.concurrent_process(
        items,
        lambda item, _: process_shot(item[0], item[1], item[2]),
        max_workers=settings.MAX_WORKERS,
        ordered=True,
        progress_callback=lambda idx, res, success: print(f"镜头 {idx+1}/{len(shots)} 处理完成")
    )
    if errors:
        for idx, err in errors.items():
            log_error('auto_split_simple', f'镜头{idx+1}处理失败', err)
            print(f"警告：镜头 {idx+1} 处理失败，已使用后备提示词")

    # 更新 shots 中的 prompt 字段
    for i, res in enumerate(results):
        if res is not None:
            shots[i] = res

    # ---------- 新增：统计失败的镜头 ----------
    failed_shots = [s for s in shots if s.get('_error')]
    if failed_shots:
        print(f"\n⚠️ 共有 {len(failed_shots)} 个镜头生成失败，已使用视觉描述作为后备提示词。")
        for s in failed_shots[:5]:  # 只显示前5个
            print(f"  - 镜头 {s['seg_id']}-{s['shot_idx']}: {s['_error'][:100]}")
        print("  详细错误请查看控制台输出的堆栈信息或 logs/error_log.txt。")
    # ---------- 统计结束 ----------

    # 保存 shot_data.json（结构化数据）
    timestamp = datetime.now().strftime("%m%d_%H%M")
    shot_data_file = os.path.join(work_dir, f"shot_data_{timestamp}.json")
    with open(shot_data_file, 'w', encoding='utf-8') as f:
        json.dump(shots, f, ensure_ascii=False, indent=2)
    print(f"镜头结构化数据已保存至 {shot_data_file}")

    # 生成易读版分镜文件（包含提示词）
    def format_shot(shot):
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
{shot['prompt']}"""

    readable_parts = [format_shot(shot) for shot in shots]
    readable_file = os.path.join(work_dir, f"分镜结果_易读版_{timestamp}.txt")
    with open(readable_file, 'w', encoding='utf-8') as f:
        f.write('\n\n===========================\n\n'.join(readable_parts))
    print(f"易读版分镜文件已生成：{readable_file}")

    print("处理完成。")


if __name__ == "__main__":
    main()