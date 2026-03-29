# utils/subtitle_generator.py
"""
字幕生成模块：使用 faster-whisper 将音频文件转换为 SRT 字幕文件。
支持 GPU 加速、VAD 过滤。
"""

import os
import sys
import time
import argparse
from typing import Optional
from datetime import timedelta

def format_srt_time(seconds: float) -> str:
    td = timedelta(seconds=seconds)
    hours = td.seconds // 3600
    minutes = (td.seconds % 3600) // 60
    secs = td.seconds % 60
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_subtitle(audio_path: str, srt_path: str, model_size: str = "small", language: str = "zh",
                      device: Optional[str] = None) -> bool:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("请先安装 faster-whisper: pip install faster-whisper")
        return False

    if device is None:
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    compute_type = "int8_float16" if device == "cuda" else "int8"

    print(f"[{time.strftime('%H:%M:%S')}] 加载模型 {model_size} (设备: {device}, 计算类型: {compute_type})")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print(f"[{time.strftime('%H:%M:%S')}] 开始转写音频: {audio_path}")
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,                # 启用 VAD
    )

    print(f"[{time.strftime('%H:%M:%S')}] 检测语言: {info.language} (概率 {info.language_probability:.2f})")

    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, start=1):
            start = format_srt_time(segment.start)
            end = format_srt_time(segment.end)
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{segment.text.strip()}\n\n")
            print(f"[{time.strftime('%H:%M:%S')}] 写入片段 {i}: [{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text[:50]}...")

    print(f"[{time.strftime('%H:%M:%S')}] 字幕生成完成，保存至: {srt_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="使用 faster-whisper 生成字幕")
    parser.add_argument("audio", help="输入音频文件路径")
    parser.add_argument("-o", "--output", help="输出 SRT 文件路径", default=None)
    parser.add_argument("-m", "--model", default="turbo",
                        choices=["tiny", "base", "small", "medium", "large", "turbo", "distil-large-v3"],
                        help="模型大小")
    parser.add_argument("-l", "--language", default="zh", help="语言代码 (如 zh, en)")
    parser.add_argument("-d", "--device", default=None, choices=["cpu", "cuda"], help="设备 (自动检测)")
    args = parser.parse_args()

    audio_file = args.audio
    if not os.path.exists(audio_file):
        print(f"错误: 音频文件不存在: {audio_file}")
        sys.exit(1)

    if args.output is None:
        base = os.path.splitext(audio_file)[0]
        srt_file = base + ".srt"
    else:
        srt_file = args.output

    success = generate_subtitle(audio_file, srt_file, args.model, args.language, args.device)
    sys.exit(0 if success else 1)