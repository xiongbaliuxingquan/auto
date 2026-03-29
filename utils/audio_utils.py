# audio_utils.py
import os
import subprocess
import re
import requests
from pathlib import Path

# 设置 ffmpeg 路径：优先使用 audio 目录下的 tools
BASE_DIR = Path(__file__).resolve().parent
# 优先 audio 目录内的 tools
LOCAL_TOOLS = BASE_DIR / "tools" / "ffmpeg" / "bin"
FFMPEG = LOCAL_TOOLS / "ffmpeg.exe"
FFPROBE = LOCAL_TOOLS / "ffprobe.exe"
if not FFMPEG.exists():
    # 尝试主应用目录
    MAIN_DIR = BASE_DIR.parent
    MAIN_TOOLS = MAIN_DIR / "tools" / "ffmpeg" / "bin"
    FFMPEG = MAIN_TOOLS / "ffmpeg.exe"
    FFPROBE = MAIN_TOOLS / "ffprobe.exe"
if not FFMPEG.exists():
    # 回退到系统 PATH
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        FFMPEG = ffmpeg_path
    else:
        FFMPEG = "ffmpeg"
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        FFPROBE = ffprobe_path
    else:
        FFPROBE = "ffprobe"
print(f"[DEBUG] FFMPEG 路径: {FFMPEG}")

def get_audio_duration(filepath: str) -> float:
    """使用 ffmpeg 获取音频时长（秒）"""
    cmd = [str(FFMPEG), '-i', filepath, '-f', 'null', '-']
    print(f"[DEBUG] get_audio_duration cmd: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=False, check=False)
        print(f"[DEBUG] ffmpeg 返回码: {result.returncode}")
        # 将 stderr 用 utf-8 解码，忽略错误
        stderr = result.stderr.decode('utf-8', errors='ignore')
        print(f"[DEBUG] ffmpeg stderr 前500字符: {stderr[:500]}")
        match = re.search(r'Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d{2})', stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
        else:
            raise ValueError("无法解析时长")
    except FileNotFoundError as e:
        raise RuntimeError(f"ffmpeg 可执行文件未找到: {FFMPEG}, 请检查路径")
    except Exception as e:
        raise RuntimeError(f"获取音频时长失败: {filepath}, 错误: {e}")

from utils import config_manager

def call_deepseek(prompt, temperature=0.7, max_tokens=4000):
    api_key, _ = config_manager.load_config()
    if not api_key:
        raise ValueError("未找到 API Key，请先配置")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            raise Exception(f"API 调用失败: {response.status_code} {response.text}")
    except Exception as e:
        raise Exception(f"DeepSeek API 异常: {e}")