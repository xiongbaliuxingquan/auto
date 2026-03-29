# utils/align_video_duration.py
"""
视频时长对齐模块：根据 shot_subtitle_map.json 中的时间信息，将每个镜头视频变速到精确时长。
使用帧数对齐，确保每个片段的帧数精确匹配目标，消除累积误差。
"""

import os
import sys
import json
import subprocess
import re
from typing import Optional, Dict, List, Tuple

# 将项目根目录加入路径，以便导入 utils
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# 查找 FFmpeg 路径
def get_ffmpeg_path():
    project_root = os.path.dirname(os.path.dirname(__file__))
    local_ffmpeg = os.path.join(project_root, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    return 'ffmpeg'

FFMPEG_CMD = get_ffmpeg_path()

def get_video_info(filepath: str) -> Tuple[int, float]:
    """
    使用 ffmpeg 获取视频的帧数和帧率。
    返回 (总帧数, 帧率)
    """
    cmd = [FFMPEG_CMD, '-i', filepath, '-f', 'null', '-']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stderr
        # 提取帧率: 常见格式 "25 fps", "24 tbr", 或 "fps=24"
        fps_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:fps|tbr|fps=)', output)
        fps = float(fps_match.group(1)) if fps_match else 24.0
        # 提取总帧数: 最后一行类似 "frame=  123"
        frame_match = re.search(r'frame=\s*(\d+)', output)
        total_frames = int(frame_match.group(1)) if frame_match else None
        if total_frames is None:
            # 尝试从时长估算（备用）
            dur_match = re.search(r'Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d{2})', output)
            if dur_match:
                h, m, s = dur_match.groups()
                duration = int(h) * 3600 + int(m) * 60 + float(s)
                total_frames = int(round(duration * fps))
            else:
                raise RuntimeError("无法获取视频帧数")
        return total_frames, fps
    except Exception as e:
        raise RuntimeError(f"无法获取视频信息: {filepath}, 错误: {e}")

def speed_video(input_path: str, output_path: str, speed_factor: float) -> None:
    """
    使用 ffmpeg 变速视频，保持高质量。
    speed_factor = 原时长 / 目标时长，>1 表示快进，<1 表示慢放。
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pts_factor = 1.0 / speed_factor
    # 视频滤镜
    video_filter = f'setpts={pts_factor}*PTS'
    # 音频滤镜：使用 atempo 调整速度（因子范围 0.5~2.0）
    # 如果超出范围，可使用 asetpts 或多次 atempo，这里简化使用 asetpts
    if 0.5 <= speed_factor <= 2.0:
        audio_filter = f'atempo={speed_factor}'
    else:
        audio_filter = f'asetpts=PTS/{speed_factor}'
    # 构建命令
    cmd = [
        FFMPEG_CMD, '-i', input_path,
        '-filter:v', video_filter,
        '-filter:a', audio_filter,
        '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
        '-c:a', 'aac', '-b:a', '192k',
        '-y', output_path
    ]
    # 如果输入视频没有音频，去掉音频相关滤镜和编码参数
    # 简单处理：先检查是否有音频流（通过 ffmpeg 输出），但为了简化，先运行命令，如果失败再尝试不带音频
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        # 如果因为音频问题失败，尝试不带音频滤镜
        cmd_no_audio = [
            FFMPEG_CMD, '-i', input_path,
            '-filter:v', video_filter,
            '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
            '-an', '-y', output_path
        ]
        subprocess.run(cmd_no_audio, check=True, capture_output=True, text=True)

def find_video_file(work_dir: str, shot_id: str) -> Optional[str]:
    """
    查找镜头对应的视频文件，不依赖固定前缀。
    在工作目录及常见子目录（aligned_clips, output, videos）中
    扫描包含 shot_id（如 "1-1"）且扩展名为视频格式的文件。
    优先返回包含 'trimmed' 或 '裁剪' 的文件（表示裁剪后的），否则返回第一个匹配。
    """
    extensions = ['.mp4', '.gif', '.mov', '.avi']
    search_dirs = [work_dir]
    for subdir in ['aligned_clips', 'output', 'videos']:
        candidate = os.path.join(work_dir, subdir)
        if os.path.isdir(candidate):
            search_dirs.append(candidate)

    candidates = []
    for base_dir in search_dirs:
        for f in os.listdir(base_dir):
            for ext in extensions:
                if f.endswith(ext) and shot_id in f:
                    candidates.append(os.path.join(base_dir, f))
                    break
    if not candidates:
        return None
    for c in candidates:
        if 'trimmed' in c or '裁剪' in c:
            return c
    return candidates[0]

def get_total_audio_ms(work_dir: str) -> int:
    """从 input.srt 获取总音频时长（最后一条字幕的结束时间，毫秒）"""
    srt_path = os.path.join(work_dir, "input.srt")
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"未找到字幕文件: {srt_path}")

    from utils.subtitle_utils import parse_srt
    subs = parse_srt(srt_path)
    if not subs:
        raise ValueError("字幕文件解析为空")
    return subs[-1][1]

def align_videos(work_dir: str, total_audio_ms: Optional[int] = None) -> Dict[str, float]:
    if total_audio_ms is None:
        total_audio_ms = get_total_audio_ms(work_dir)

    map_path = os.path.join(work_dir, "shot_subtitle_map.json")
    if not os.path.exists(map_path):
        raise FileNotFoundError(f"未找到 {map_path}，请先运行 refine_shots_by_srt.py。")

    with open(map_path, 'r', encoding='utf-8') as f:
        shot_map = json.load(f)

    shot_map.sort(key=lambda x: x['start_ms'])
    n = len(shot_map)
    results = {}
    log_lines = []

    for i, item in enumerate(shot_map):
        shot_id = item['shot_id']
        start_ms = item['start_ms']
        if i + 1 < n:
            next_start_ms = shot_map[i+1]['start_ms']
            target_duration = (next_start_ms - start_ms) / 1000.0
        else:
            target_duration = (total_audio_ms - start_ms) / 1000.0
        if target_duration <= 0:
            print(f"警告：镜头 {shot_id} 的目标时长 <=0 ({target_duration}s)，跳过")
            continue

        video_file = find_video_file(work_dir, shot_id)
        if not video_file:
            print(f"警告：未找到镜头 {shot_id} 的视频文件，跳过")
            continue

        # 获取原视频信息
        actual_frames, fps = get_video_info(video_file)
        target_frames = int(round(target_duration * fps))
        speed_factor = actual_frames / target_frames
        aligned_duration = target_frames / fps

        print(f"处理镜头 {shot_id}: 原帧数={actual_frames}, 目标帧数={target_frames}, 变速因子={speed_factor:.4f}")

        if abs(actual_frames - target_frames) < 1:
            results[shot_id] = aligned_duration
            log_lines.append(f"{shot_id}: 已对齐 (原帧数={actual_frames}, 目标帧数={target_frames}, 时长={aligned_duration:.2f}s)")
            continue

        output_path = os.path.join(os.path.dirname(video_file), f"对齐_{shot_id}.mp4")
        speed_video(video_file, output_path, speed_factor)
        results[shot_id] = aligned_duration
        log_lines.append(f"{shot_id}: {actual_frames}帧 -> {target_frames}帧 (变速因子: {speed_factor:.3f})")

    # 写入对齐报告
    report_path = os.path.join(work_dir, "对齐报告.txt")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(log_lines))
    print(f"对齐完成，报告已保存至: {report_path}")

    return results

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("用法:")
        print("  python align_video_duration.py <工作目录>")
        print("  python align_video_duration.py <工作目录> <总音频时长毫秒>")
        sys.exit(1)
    work_dir = sys.argv[1]
    total_audio_ms = None
    if len(sys.argv) == 3:
        total_audio_ms = int(sys.argv[2])
    try:
        align_videos(work_dir, total_audio_ms)
        print("视频时长对齐完成。")
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)