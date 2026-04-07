#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generate_first_frame_prompt.py
功能：根据已有的剧本（shots.txt）和资产文件，为每个镜头生成首帧图提示词（静态画面）。
输出：first_frame_prompts.json，每个镜头一条中文提示词。
"""

import os
import sys
import json
import re
import argparse
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# 将项目根目录加入路径
# 将项目根目录加入路径
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)
from utils.ai_utils import call_deepseek
from utils import settings
from utils.error_logger import log_error


def parse_shots(shots_path: str) -> List[Dict]:
    """
    解析 shots.txt，返回镜头列表，每个镜头包含：
    - id: 镜头ID (如 "1-1")
    - scene: 场景描述
    - roles: 角色列表
    - action: 动作描述
    - dialogue: 对白
    - visual: 视觉描述
    - duration: 时长（秒）
    - emotion: 情绪基调
    - region: 地域
    """
    shots = []
    with open(shots_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    total = len(lines)
    while i < total:
        line = lines[i].strip()
        if line.startswith('【镜头') and '：' in line:
            # 提取镜头ID
            match = re.search(r'【镜头(\d+-\d+)：', line)
            if not match:
                i += 1
                continue
            shot_id = match.group(1)
            # 解析段落号（用于加载局部资产）
            para_id = int(shot_id.split('-')[0]) if '-' in shot_id else 1

            shot = {
                'id': shot_id,
                'para_id': para_id,
                'scene': '',
                'roles': [],
                'action': '',
                'dialogue': '',
                'visual': '',
                'duration': 10.0,
                'emotion': '',
                'region': ''
            }
            i += 1
            while i < total and not lines[i].strip().startswith('==========================='):
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


def load_global_assets(work_dir: str) -> str:
    """读取全局资产文件内容"""
    path = os.path.join(work_dir, "assets_global.txt")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""


def load_local_assets(work_dir: str, para_id: int) -> str:
    """读取指定段落的局部资产文件"""
    path = os.path.join(work_dir, f"assets_paragraph_{para_id}.txt")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return ""


def build_prompt(shot: Dict, global_assets: str, local_assets: str) -> str:
    """构建首帧图提示词生成的 prompt"""
    roles_str = ', '.join(shot['roles']) if shot['roles'] else '无'
    prompt = f"""你是一位专业的AI图像生成提示词工程师。请根据以下镜头信息，生成一个高质量的**静态图像**提示词（中文），用于后续图生视频的首帧图生成。

【重要定义】
- 首帧图 = 镜头开始瞬间的第一帧画面。
- 此时动作**尚未开始**，人物处于**起始姿态**（例如：准备说话但未开口、即将移动但未动、情绪刚浮现但未爆发）。
- 严禁描述任何正在进行的动作、运动、变化、时间推移（如“推近”、“摇摄”、“逐渐”、“开始”、“正在”等）。
- 画面应体现“即将发生某事”的瞬间感，但画面本身是静止的。

【要求】
1. 严格基于【视觉描述】和【场景】中的核心意象，可以适当细化构图、光影、色彩、质感，但不得改变核心元素。
2. 聚焦于**静态画面**，描述应体现“第一帧”的起始状态。
3. 输出应为一段连贯的中文描述，不要添加任何额外格式或标记。
4. 如果提供了全局资产或局部资产，请融入角色的固定特征、服装、道具等。

【全局资产参考】
{global_assets if global_assets else "无"}

【段落局部资产参考】
{local_assets if local_assets else "无"}

【当前镜头信息】
- 镜头ID：{shot['id']}
- 场景：{shot['scene']}
- 角色：{roles_str}
- 动作：{shot['action']}  ← 这是整个镜头的动作概述，首帧图中动作**尚未开始**
- 对白：{shot['dialogue']}
- 视觉描述：{shot['visual']}
- 情绪基调：{shot['emotion']}
- 地域：{shot['region']}
- 目标时长：{shot['duration']}秒（仅作参考，首帧图不体现时长）

请直接输出首帧图提示词（仅描述第一帧静态画面）："""
    return prompt


def generate_single_prompt(shot: Dict, global_assets: str, local_assets_by_para: Dict[int, str]) -> Optional[Dict]:
    """为单个镜头生成首帧图提示词"""
    para_id = shot['para_id']
    local_assets = local_assets_by_para.get(para_id, "")
    prompt_text = build_prompt(shot, global_assets, local_assets)
    try:
        result = call_deepseek(prompt_text, temperature=0.6, max_tokens=800)
        result = result.strip()
        # 清洗可能的标记
        result = re.sub(r'^首帧图提示词[：:]\s*', '', result)
        result = re.sub(r'^```.*\n?', '', result)
        result = re.sub(r'```$', '', result)
        return {"shot_id": shot['id'], "prompt": result}
    except Exception as e:
        log_error('generate_first_frame_prompt', f"镜头 {shot['id']} 生成失败", str(e))
        print(f"❌ 镜头 {shot['id']} 生成失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="为每个镜头生成首帧图提示词")
    parser.add_argument("work_dir", help="工作目录（包含 shots.txt 和 assets 文件）")
    parser.add_argument("--max_workers", type=int, default=settings.MAX_WORKERS, help="并发线程数")
    args = parser.parse_args()

    work_dir = args.work_dir
    shots_path = os.path.join(work_dir, "shots.txt")
    if not os.path.exists(shots_path):
        print(f"错误：未找到 {shots_path}")
        sys.exit(1)

    # 解析镜头
    shots = parse_shots(shots_path)
    if not shots:
        print("错误：未能解析任何镜头")
        sys.exit(1)
    print(f"共解析 {len(shots)} 个镜头")

    # 加载全局资产
    global_assets = load_global_assets(work_dir)
    # 加载所有段落局部资产
    local_assets_by_para = {}
    para_ids = set(shot['para_id'] for shot in shots)
    for pid in para_ids:
        local = load_local_assets(work_dir, pid)
        if local:
            local_assets_by_para[pid] = local

    # 并发生成
    print(f"开始生成首帧图提示词，并发数 {args.max_workers}...")
    results = []
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_shot = {
            executor.submit(generate_single_prompt, shot, global_assets, local_assets_by_para): shot
            for shot in shots
        }
        for future in as_completed(future_to_shot):
            shot = future_to_shot[future]
            try:
                res = future.result()
                if res:
                    results.append(res)
                    print(f"[成功] 镜头 {shot['id']} 生成完成")
                else:
                    print(f"[失败] 镜头 {shot['id']} 生成失败")
            except Exception as e:
                print(f"[失败] 镜头 {shot['id']} 异常: {e}")

    # 按 shot_id 排序（例如 "1-1", "1-2", "2-1" 等）
    results.sort(key=lambda x: [int(part) for part in x['shot_id'].split('-')])
    # 保存结果
    output_path = os.path.join(work_dir, "first_frame_prompts.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"首帧图提示词已保存至 {output_path} (成功 {len(results)}/{len(shots)})")

    if len(results) < len(shots):
        print("警告：部分镜头生成失败，请检查日志。")
        sys.exit(1)


if __name__ == "__main__":
    main()