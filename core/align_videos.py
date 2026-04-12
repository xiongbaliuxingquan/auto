"""
align_videos.py
功能：根据字幕映射文件，对已生成的视频进行精确裁剪，使每个镜头时长等于目标时长。
输出：裁剪后的视频文件存放在工作目录下的 `对齐后视频/` 子目录中，并生成合并列表。
"""

import os
import sys
import json
import subprocess
import re
import shutil
from datetime import datetime

def get_ffmpeg_path():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    print(f"DEBUG: base_dir = {base_dir}")
    local_ffmpeg = os.path.join(base_dir, 'tools', 'ffmpeg', 'bin', 'ffmpeg.exe')
    print(f"DEBUG: local_ffmpeg = {local_ffmpeg}")
    print(f"DEBUG: exists = {os.path.exists(local_ffmpeg)}")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    old_path = os.path.join(base_dir, 'tools', 'ffmpeg', 'ffmpeg.exe')
    if os.path.exists(old_path):
        return old_path
    return 'ffmpeg'

def get_video_duration(video_path, ffmpeg_path):
    """使用 ffmpeg 获取视频实际时长（秒），返回浮点数"""
    cmd = [ffmpeg_path, '-i', video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d+)', result.stderr)
    if match:
        h, m, s = match.groups()
        return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0

def trim_video(input_path, output_path, start_sec, duration_sec, ffmpeg_path):
    """
    极简流复制裁剪：仅截取前 target_frames 帧，不重新编码，不改变时间戳。
    """
    target_frames = round(duration_sec * 24)
    cmd = [
        ffmpeg_path, '-y',
        '-i', input_path,
        '-frames:v', str(target_frames),
        '-c', 'copy',
        '-map', '0',
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode == 0:
        return True
    else:
        print(f"裁剪失败: {result.stderr}")
        return False

def main(work_dir, video_dir=None, log_callback=None):
    """
    work_dir: 文字结果目录（包含 shot_subtitle_map.json）
    video_dir: 视频文件所在目录（如果为 None，则默认为 work_dir）
    log_callback: 可选日志回调，用于 GUI 显示
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        sys.stdout.flush()

    ffmpeg_path = get_ffmpeg_path()
    log(f"ffmpeg 路径: {ffmpeg_path}")

    log(f"\n========== 视频后处理对齐开始 ==========")
    log(f"文字目录: {work_dir}")
    log(f"视频目录: {video_dir if video_dir else work_dir}")

    # 1. 读取字幕映射
    map_file = os.path.join(work_dir, "shot_subtitle_map.json")
    if not os.path.exists(map_file):
        log(f"错误：未找到字幕映射文件 {map_file}，请先运行 refine_shots_by_srt.py 生成。")
        return False
    with open(map_file, 'r', encoding='utf-8') as f:
        shot_map = json.load(f)
    log(f"读取到 {len(shot_map)} 个镜头映射。")

    # 2. 定位 ffmpeg
    ffmpeg_path = get_ffmpeg_path()
    log(f"使用 ffmpeg: {ffmpeg_path}")

    # 3. 创建输出目录
    out_dir = os.path.join(work_dir, "对齐后视频")
    os.makedirs(out_dir, exist_ok=True)
    log(f"输出目录: {out_dir}")

    # 4. 扫描视频文件（从 video_dir 中查找）
    video_dir = video_dir if video_dir is not None else work_dir
    video_files = {}
    for fname in os.listdir(video_dir):
        if fname.startswith("镜头") and (fname.endswith(".mp4") or fname.endswith(".gif")):
            # 提取镜头ID（去掉 "镜头" 和扩展名）
            shot_id = fname[2:].rsplit('.', 1)[0]
            video_files[shot_id] = os.path.join(video_dir, fname)
    log(f"在视频目录中找到 {len(video_files)} 个视频文件。")

    # 5. 处理每个镜头
    trimmed_files = []
    for item in shot_map:
        shot_id = item['shot_id']
        target_duration_ms = item['target_duration_ms']
        target_sec = target_duration_ms / 1000.0

        video_path = video_files.get(shot_id)
        if not video_path:
            log(f"警告：镜头 {shot_id} 未找到视频文件，跳过。")
            continue

        # 获取实际时长
        actual_sec = get_video_duration(video_path, ffmpeg_path)
        log(f"镜头 {shot_id}: 目标时长 {target_sec:.3f}s, 实际时长 {actual_sec:.3f}s")

        # 输出文件名
        out_filename = f"trimmed_{shot_id}.mp4"
        out_path = os.path.join(out_dir, out_filename)

        if actual_sec <= target_sec + 0.05:  # 允许微小误差
            log(f"  实际时长 <= 目标时长，直接复制原文件。")
            shutil.copy2(video_path, out_path)
        else:
            # 改为只从尾部裁剪，起始点固定为0，时长即为目标时长
            log(f"  需要裁剪，多余 {actual_sec - target_sec:.3f}s，将丢弃尾部多余部分")
            success = trim_video(video_path, out_path, 0.0, target_sec, ffmpeg_path)
            if success:
                log(f"  裁剪成功: {out_path}")
            else:
                log(f"  裁剪失败，将复制原文件。")
                shutil.copy2(video_path, out_path)

        trimmed_files.append(out_path)

    # 6. 生成 concat 列表（用于后续合并）
    concat_list = os.path.join(work_dir, "concat_list_aligned.txt")
    with open(concat_list, 'w', encoding='utf-8') as f:
        for path in trimmed_files:
            f.write(f"file '{path}'\n")
    log(f"生成 concat 列表: {concat_list}")

    # 7. 可选：合并视频（默认不自动合并，只生成列表，方便手动执行）
    log("提示：如需合并所有片段，请手动运行以下命令：")
    log(f"ffmpeg -f concat -safe 0 -i {concat_list} -c copy {os.path.join(work_dir, 'final_aligned.mp4')}")

    log("\n视频后处理对齐完成。")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python align_videos.py <文字目录> [视频目录]")
        sys.exit(1)
    work_dir = sys.argv[1]
    video_dir = sys.argv[2] if len(sys.argv) > 2 else None
    main(work_dir, video_dir)