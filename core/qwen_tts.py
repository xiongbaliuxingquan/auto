# qwen_tts.py
"""
千问 TTS 生成参考音频模块：调用 ComfyUI 工作流，根据文本和语音描述生成音频。
"""

import os
import json
import re
from typing import Optional

# 从 core.fish_tts 导入（因为 fish_tts 在 core 目录）
from core.fish_tts import submit_workflow, wait_for_audio, download_audio
from utils import config_manager

API_URL = config_manager.COMFYUI_API_URL
QWEN_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflow_templates", "QwenTTS.json")

def sanitize_filename(text):
    """清洗文本，用于文件名（仅保留中文、字母、数字、下划线）"""
    # 保留中文字符、字母、数字、下划线，其他替换为下划线
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_]', '_', text)
    # 去除多余下划线
    text = re.sub(r'_+', '_', text)
    # 限制长度，避免文件名过长
    return text[:30]

def get_next_preview_index(work_dir):
    """扫描工作目录，返回下一个可用的预览序号（1开始）"""
    import glob
    pattern = os.path.join(work_dir, "预览_*.mp3")
    existing = glob.glob(pattern)
    max_idx = 0
    for f in existing:
        base = os.path.basename(f)
        # 格式：预览_01_描述.mp3
        match = re.match(r'预览_(\d+)_.*\.mp3', base)
        if match:
            idx = int(match.group(1))
            if idx > max_idx:
                max_idx = idx
    return max_idx + 1

def generate_reference_audio(text: str, voice_description: str, work_dir: str) -> Optional[str]:
    """
    调用千问 TTS 工作流生成参考音频。
    参数:
        text: 要朗读的文本（建议20-30秒内）
        voice_description: 语音描述，如“语速很快，中年男性，声音干练”
        work_dir: 工作目录，音频将保存为 预览_{序号}_{描述}.mp3
    返回:
        成功返回本地音频文件路径，失败返回 None
    """
    # 检查模板文件是否存在
    if not os.path.exists(QWEN_TEMPLATE_PATH):
        raise FileNotFoundError(f"千问 TTS 模板不存在: {QWEN_TEMPLATE_PATH}")

    # 加载工作流模板
    with open(QWEN_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 修改节点5的输入
    workflow["5"]["inputs"]["text"] = text
    workflow["5"]["inputs"]["instruct"] = voice_description
    # 节点6保持不变

    # 提交工作流
    prompt_id = submit_workflow(API_URL, workflow)
    if not prompt_id:
        print("提交千问 TTS 工作流失败")
        return None

    # 等待音频生成，输出节点为7
    audio_url = wait_for_audio(API_URL, prompt_id, "7")
    if not audio_url:
        print("等待千问 TTS 音频生成失败")
        return None

    # 生成唯一文件名
    next_idx = get_next_preview_index(work_dir)
    desc_sanitized = sanitize_filename(voice_description)
    if desc_sanitized:
        filename = f"预览_{next_idx:02d}_{desc_sanitized}.mp3"
    else:
        filename = f"预览_{next_idx:02d}.mp3"
    save_path = os.path.join(work_dir, filename)

    # 下载音频
    if download_audio(API_URL, audio_url, save_path):
        print(f"千问 TTS 音频下载成功: {save_path}")
        return save_path
    else:
        print("千问 TTS 音频下载失败")
        return None

if __name__ == "__main__":
    # 简单测试
    import sys
    if len(sys.argv) < 4:
        print("用法: python qwen_tts.py <文本> <语音描述> <输出目录>")
        sys.exit(1)
    text = sys.argv[1]
    desc = sys.argv[2]
    out_dir = sys.argv[3]
    result = generate_reference_audio(text, desc, out_dir)
    if result:
        print(f"生成成功: {result}")
    else:
        print("生成失败")