#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模块1：段落分割 + 全局信息提取（复用 AnalysisParser 的分段逻辑）
输入：原始文稿文件路径，输出目录，模式（可选）
输出：paragraphs.json，header.txt
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils.ai_utils import call_deepseek
from parsers.analysis_parser import AnalysisParser

def call_deepseek_with_log(prompt, temperature=0.3, max_tokens=8000):
    """包装 call_deepseek，增加打印日志"""
    print("正在请求 DeepSeek API...")
    return call_deepseek(prompt, temperature, max_tokens)

def extract_global_info(raw_text, story_title=None, mode=None):
    """提取全局信息：project, style, persona, scene，可根据模式加载人设卡"""
    # 加载人设卡
    preset_text = ""
    if mode:
        preset_map = {
            "情感故事": "emotional_default.txt",
            "文明结构": "civil_default.txt",
            "动画默剧": "mime_default.txt"
        }
        preset_file = preset_map.get(mode)
        if preset_file:
            preset_path = os.path.join(os.path.dirname(__file__), "..", "prompt_presets", preset_file)
            if os.path.exists(preset_path):
                with open(preset_path, 'r', encoding='utf-8') as f:
                    preset_text = f.read().strip()
                print(f"已加载人设卡预设: {preset_file}")

    prompt = f"""
你是一个专业的剧本分析助手。请从以下文稿中提取关键信息，输出为 JSON 格式，包含以下字段：
- project: 项目标题（若原文未明确给出，可根据内容推断一个简洁标题）
- style: 整体视觉风格（如“电影感、写实、自然光影”）
- persona: 人物设定（如果有主要人物，描述其特征；若无，则输出空对象）
- scene: 场景设定（如果有主要场景，描述其特征；若无，则输出空对象）

注意：
1. 如果原文没有提到人物或场景，对应字段输出空对象 {{}}。
2. 输出必须是一个合法的 JSON 对象，不要添加任何额外内容。
3. 如果提供了人设卡规则，请在提取人物和场景设定时参考并遵循这些规则。

人设卡规则（如果有）：
{preset_text}

文稿内容：
{raw_text}
"""
    response = call_deepseek_with_log(prompt, temperature=0.3, max_tokens=2000)
    # 清洗
    cleaned = response.strip()
    if cleaned.startswith('```json'):
        cleaned = cleaned[7:]
    if cleaned.startswith('```'):
        cleaned = cleaned[3:]
    if cleaned.endswith('```'):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    try:
        info = json.loads(cleaned)
        info.setdefault('project', story_title or "未知")
        info.setdefault('style', "电影感、写实、自然光影")
        info.setdefault('persona', {})
        info.setdefault('scene', {})
        return info
    except Exception as e:
        print(f"全局信息提取失败: {e}")
        return {
            'project': story_title or "未知",
            'style': "电影感、写实、自然光影",
            'persona': {},
            'scene': {}
        }

def write_header(header_path, info):
    with open(header_path, 'w', encoding='utf-8') as f:
        f.write(f"project: {info['project']}\n")
        f.write(f"style: {info['style']}\n")
        f.write(f"seed: 12345\n")
        f.write(f"persona: {json.dumps(info['persona'], ensure_ascii=False)}\n")
        f.write(f"scene: {json.dumps(info['scene'], ensure_ascii=False)}\n")

def main():
    parser = argparse.ArgumentParser(description="模块1：段落分割 + 全局信息提取")
    parser.add_argument("input_file", help="输入文稿文件路径")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("--mode", default="文明结构", help="文稿类型（情感故事/文明结构/动画默剧）")
    args = parser.parse_args()

    input_file = args.input_file
    output_dir = args.output_dir
    mode = args.mode

    os.makedirs(output_dir, exist_ok=True)

    with open(input_file, 'r', encoding='utf-8') as f:
        raw_text = f.read()

    # 创建 AnalysisParser 实例，传入带日志的 call_deepseek
    parser_inst = AnalysisParser(call_deepseek_with_log, story_title=None, mode=mode)

    print("正在分割段落...")
    try:
        paragraphs = parser_inst._split_into_paragraphs(raw_text)
        print(f"成功分割为 {len(paragraphs)} 个段落")
    except Exception as e:
        print(f"分割失败: {e}")
        sys.exit(1)

    # 保存段落 JSON
    para_path = os.path.join(output_dir, 'paragraphs.json')
    with open(para_path, 'w', encoding='utf-8') as f:
        json.dump(paragraphs, f, ensure_ascii=False, indent=2)
    print(f"段落已保存至 {para_path}")

    # 提取全局信息
    print("正在提取全局信息...")
    base_name = os.path.splitext(os.path.basename(input_file))[0]
    info = extract_global_info(raw_text, base_name, mode=mode)
    header_path = os.path.join(output_dir, 'header.txt')
    write_header(header_path, info)
    print(f"全局信息已保存至 {header_path}")

if __name__ == "__main__":
    main()