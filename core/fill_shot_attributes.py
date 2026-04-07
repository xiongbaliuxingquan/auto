#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模块3：为镜头填充属性（标题、情绪、地域、视觉描述）
输入：paragraphs.json, shots_base.txt, shot_para_index.json
输出：shots.txt
"""

import sys
import os
import json
import re
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.ai_utils import call_deepseek
from parsers.analysis_parser import AnalysisParser

def call_deepseek_with_log(prompt, temperature=0.3, max_tokens=8000):
    """包装 call_deepseek，增加打印日志"""
    print("正在请求 DeepSeek API...")
    return call_deepseek(prompt, temperature, max_tokens)

def parse_shots_base(shots_base_path):
    """
    解析基础镜头文件，返回镜头列表，每个镜头包含：
    - id: 镜号（如 "1-1"）
    - script: 口播稿
    - duration: 时长（秒）
    """
    shots = []
    with open(shots_base_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('【镜头') and '：' in line:
            # 提取镜号
            shot_id = re.search(r'【镜头(\d+-\d+)', line).group(1)
            i += 1
            duration = 0.0
            script = ""
            while i < len(lines) and not lines[i].strip().startswith('==========================='):
                subline = lines[i].strip()
                if subline.startswith('- 时长：'):
                    dur_match = re.search(r'([\d.]+)', subline)
                    if dur_match:
                        duration = float(dur_match.group(1))
                elif subline.startswith('- 口播稿：'):
                    script = subline.split('：', 1)[-1].strip()
                i += 1
            shots.append({
                'id': shot_id,
                'duration': duration,
                'script': script
            })
            # 跳过分隔线
            while i < len(lines) and lines[i].strip().startswith('==========================='):
                i += 1
        else:
            i += 1
    return shots

def write_shots(shots_path, shots):
    """写入最终 shots.txt"""
    with open(shots_path, 'w', encoding='utf-8') as f:
        for shot in shots:
            f.write(f"【镜头{shot['id']}：{shot['title']}】\n")
            f.write(f"- 时长：{shot['duration']:.1f}秒\n")
            f.write(f"- 情绪基调：{shot['emotion']}\n")
            f.write(f"- 地域：{shot['region']}\n")
            f.write(f"- 口播稿：{shot['script']}\n")
            f.write(f"- 视觉描述：{shot['visual']}\n")
            f.write("===========================\n")

def main():
    if len(sys.argv) < 4:
        print("用法: python fill_shot_attributes.py <paragraphs.json> <shots_base.txt> <output_shots.txt>")
        sys.exit(1)
    para_json = sys.argv[1]
    shots_base = sys.argv[2]
    output_shots = sys.argv[3]

    # 读取段落
    with open(para_json, 'r', encoding='utf-8') as f:
        paragraphs = json.load(f)
    if not paragraphs:
        print("段落列表为空")
        sys.exit(1)

    # 读取基础镜头
    shots = parse_shots_base(shots_base)
    if not shots:
        print("基础镜头为空")
        sys.exit(1)

    print(f"加载了 {len(paragraphs)} 个段落，{len(shots)} 个镜头")

    # 读取镜头段落映射（模块2生成）
    map_path = os.path.join(os.path.dirname(output_shots), 'shot_para_index.json')
    if not os.path.exists(map_path):
        print("错误：未找到 shot_para_index.json，请先运行模块2")
        sys.exit(1)
    with open(map_path, 'r', encoding='utf-8') as f:
        shot_para_map = json.load(f)

    # 确保镜头数量与映射一致
    if len(shots) != len(shot_para_map):
        print("错误：镜头数量与映射文件数量不一致")
        sys.exit(1)

    # 按段落分组镜头，同时记录每个镜头在段落内的序号
    para_shots = [[] for _ in range(len(paragraphs))]
    for shot, mapping in zip(shots, shot_para_map):
        para_idx = mapping['para_index']
        if 0 <= para_idx < len(paragraphs):
            para_shots[para_idx].append(shot)
        else:
            print(f"警告：镜头 {shot.get('id', '?')} 段落索引 {para_idx} 无效，跳过")

    # 创建 AnalysisParser 实例
    parser = AnalysisParser(call_deepseek, story_title=None, mode="文明结构")

    # 存储更新后的镜头（按顺序）
    updated_shots = []

    for para_idx, shot_list in enumerate(para_shots):
        if not shot_list:
            continue
        scripts = [shot['script'] for shot in shot_list]
        print(f"段落 {para_idx+1}: 为 {len(scripts)} 个镜头生成属性...")
        try:
            generated = parser._generate_shot_attributes(paragraphs[para_idx], scripts)
        except Exception as e:
            print(f"生成失败: {e}，保留原镜头属性")
            generated = []
        # 合并结果，并重新生成镜头ID
        for i, shot in enumerate(shot_list):
            if i < len(generated):
                gen = generated[i]
                shot.update({
                    'title': gen.get('title', shot.get('title', '')),
                    'emotion': gen.get('emotion', shot.get('emotion', '')),
                    'region': gen.get('region', shot.get('region', '全球')),
                    'visual': gen.get('visual', shot.get('visual', ''))
                })
            else:
                print(f"警告：段落 {para_idx+1} 镜头 {i+1} 无生成结果，保留原属性")
            # 生成新的镜头ID：段落索引+1 和 段落内序号
            shot['id'] = f"{para_idx+1}-{i+1}"
        updated_shots.extend(shot_list)

    # 写入最终文件
    write_shots(output_shots, updated_shots)
    # 生成 shot_subtitle_map.json
    work_dir = os.path.dirname(output_shots)
    map_path = os.path.join(work_dir, 'shot_subtitle_map.json')
    
    # 读取镜头真实时间文件（如果存在）
    shot_times_path = os.path.join(work_dir, 'shot_times.json')
    shot_times = []
    if os.path.exists(shot_times_path):
        with open(shot_times_path, 'r', encoding='utf-8') as f:
            shot_times = json.load(f)
        if len(shot_times) != len(updated_shots):
            print(f"警告：镜头时间文件数量({len(shot_times)})与镜头数量({len(updated_shots)})不一致，将使用0")
            shot_times = []
    
    shot_map = []
    for idx, shot in enumerate(updated_shots):
        start_ms = 0
        end_ms = 0
        if shot_times and idx < len(shot_times):
            start_ms = shot_times[idx].get('start_ms', 0)
            end_ms = shot_times[idx].get('end_ms', 0)
        shot_map.append({
            "shot_id": shot['id'],
            "start_ms": start_ms,
            "end_ms": end_ms,
            "target_duration_ms": int(shot['duration'] * 1000)
        })
    with open(map_path, 'w', encoding='utf-8') as f:
        json.dump(shot_map, f, ensure_ascii=False, indent=2)
    print(f"字幕映射文件已生成 {map_path}")
    print(f"完成，最终镜头数: {len(updated_shots)}，已保存至 {output_shots}")

if __name__ == "__main__":
    main()