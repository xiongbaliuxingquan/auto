# core/i2v/digital_human.py
"""
LTX 2.3 数字人视频生成模块。
根据参考图像和最终音频，按固定时长分段生成数字人说话视频。
"""

import os
import sys
import json
import time
import random
import urllib.parse
import requests
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils import config_manager
from utils.error_logger import log_error
from utils.audio_utils import get_audio_duration

# 工作流模板路径
WORKFLOW_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "workflow_templates",
    "LTX2.3数字人API.json"
)

DEFAULT_FPS = 24
DEFAULT_SEGMENT_SECONDS = 30   # 每段视频时长（秒）


def upload_image(api_url: str, local_path: str) -> Optional[str]:
    """上传图片到 ComfyUI input 目录，返回服务器上的文件名"""
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"本地文件不存在: {local_path}")
    url = f"{api_url.rstrip('/')}/upload/image"
    with open(local_path, 'rb') as f:
        files = {'image': (os.path.basename(local_path), f, 'image/png')}
        try:
            resp = requests.post(url, files=files, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('name', os.path.basename(local_path))
            else:
                print(f"上传图片失败: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            print(f"上传图片异常: {e}")
            return None


def upload_audio(api_url: str, local_path: str) -> Optional[str]:
    """上传音频到 ComfyUI input 目录，返回服务器上的文件名"""
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"本地文件不存在: {local_path}")
    url = f"{api_url.rstrip('/')}/upload/image"
    with open(local_path, 'rb') as f:
        files = {'image': (os.path.basename(local_path), f, 'audio/mpeg')}
        try:
            resp = requests.post(url, files=files, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('name', os.path.basename(local_path))
            else:
                print(f"上传音频失败: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            print(f"上传音频异常: {e}")
            return None

def prompt_for_script(default_prompt: str) -> str:
    from tkinter import simpledialog, Tk
    root = Tk()
    root.withdraw()
    result = simpledialog.askstring("确认提示词", "请确认或修改数字人提示词（请保留尾部英文防护条件）：", initialvalue=default_prompt)
    root.destroy()
    return result if result is not None else default_prompt

def submit_workflow(api_url: str, workflow: dict) -> Optional[str]:
    """提交工作流，返回 prompt_id"""
    url = f"{api_url.rstrip('/')}/prompt"
    payload = {"prompt": workflow}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            return resp.json()['prompt_id']
        else:
            print(f"提交失败: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"提交异常: {e}")
        return None


def wait_for_history(api_url: str, prompt_id: str, timeout: int = 600, log_callback=None) -> Optional[dict]:
    """等待工作流完成，返回 history 字典，每10秒输出等待时间"""
    url = f"{api_url.rstrip('/')}/history/{prompt_id}"
    start = time.time()
    last_log = start
    while time.time() - start < timeout:
        if log_callback and (time.time() - last_log >= 10):
            elapsed = int(time.time() - start)
            log_callback(f"正在生成数字人视频，已等待 {elapsed} 秒...")
            last_log = time.time()
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                history = resp.json()
                if prompt_id in history:
                    return history
            time.sleep(2)
        except Exception as e:
            print(f"查询状态异常: {e}")
            time.sleep(2)
    return None


def download_video(api_url: str, output_info: dict, save_path: str) -> bool:
    """下载生成的视频文件（节点140输出）"""
    if 'videos' in output_info:
        video_info = output_info['videos'][0]
    elif 'gifs' in output_info:
        video_info = output_info['gifs'][0]
    else:
        print("未找到视频输出")
        return False
    filename = video_info.get('filename')
    subfolder = video_info.get('subfolder', '')
    video_url = f"{api_url.rstrip('/')}/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type=output"
    try:
        resp = requests.get(video_url, stream=True, timeout=120)
        if resp.status_code == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        else:
            print(f"下载失败: {resp.status_code}")
            return False
    except Exception as e:
        print(f"下载异常: {e}")
        return False


def generate_digital_human_segment(
    work_dir: str,
    image_path: str,
    audio_path: str,
    start_seconds: float,
    duration_seconds: float,
    prompt: str = "",
    seed: Optional[int] = None,
    api_url: Optional[str] = None,
    log_callback=None, 
    current: Optional[int] = None,    # 新增
    total: Optional[int] = None       # 新增
) -> Optional[str]:
    """
    生成单个数字人视频片段。
    :param work_dir: 工作目录
    :param image_path: 数字人形象图片本地路径
    :param audio_path: 最终音频文件本地路径
    :param start_seconds: 音频截取起始时间（秒）
    :param duration_seconds: 截取时长（秒）
    :param prompt: 正面提示词（默认使用内置提示词）
    :param seed: 随机种子
    :param api_url: ComfyUI API 地址
    :param log_callback: 日志回调
    :return: 视频保存路径，失败返回 None
    """
    if api_url is None:
        api_url = config_manager.COMFYUI_API_URL

    if not os.path.exists(WORKFLOW_TEMPLATE):
        raise FileNotFoundError(f"工作流模板不存在: {WORKFLOW_TEMPLATE}")

    # 1. 上传图像和音频
    if log_callback:
        log_callback(f"上传参考图像: {os.path.basename(image_path)}")
    uploaded_image = upload_image(api_url, image_path)
    if not uploaded_image:
        raise Exception("参考图像上传失败")

    if log_callback:
        log_callback(f"上传音频: {os.path.basename(audio_path)}")
    uploaded_audio = upload_audio(api_url, audio_path)
    if not uploaded_audio:
        raise Exception("音频上传失败")

    # 2. 加载工作流
    with open(WORKFLOW_TEMPLATE, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 3. 设置节点
    # 节点167：加载图像
    workflow["167"]["inputs"]["image"] = uploaded_image
    # 节点378：加载音频
    workflow["378"]["inputs"]["audio"] = uploaded_audio
    # 节点379：音频截取
    workflow["379"]["inputs"]["start_time"] = format_time(start_seconds)
    workflow["379"]["inputs"]["end_time"] = format_time(start_seconds + duration_seconds)
    # 无论 prompt 是否为空，都直接传入（空字符串也是有效的输入）
    final_prompt = prompt if prompt is not None else ""
    if log_callback:
        log_callback(f"[DEBUG] 最终使用的提示词: {final_prompt}")
    print(f"[DEBUG] 最终使用的提示词: {final_prompt}")
    workflow["121"]["inputs"]["text"] = final_prompt
    # 节点391：种子
    if seed is None:
        seed = random.randint(0, 2147483647)
    workflow["391"]["inputs"]["seed"] = seed
    if log_callback:
        log_callback(f"设置随机种子: {seed}")

    # 4. 提交工作流
    if log_callback:
        progress_str = f"（{current}/{total}）" if current and total else ""
        log_callback(f"提交数字人工作流 (片段 {format_time(start_seconds)} - {format_time(start_seconds + duration_seconds)}){progress_str}...")
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        raise Exception("提交工作流失败")

    # 5. 等待完成
    history = wait_for_history(api_url, prompt_id, timeout=600, log_callback=log_callback)
    if not history:
        raise Exception("等待超时或任务失败")

    # 6. 提取输出视频（节点140）
    outputs = history[prompt_id].get('outputs', {})
    if "140" not in outputs:
        raise Exception("未找到节点140的输出")
    node_out = outputs["140"]

    # 7. 下载视频
    video_dir = os.path.join(work_dir, "数字人视频")
    os.makedirs(video_dir, exist_ok=True)
    # 文件名包含时间范围
    segment_name = f"digital_human_{format_time(start_seconds).replace(':', '-')}_{format_time(start_seconds + duration_seconds).replace(':', '-')}.mp4"
    save_path = os.path.join(video_dir, segment_name)

    if log_callback:
        log_callback(f"下载视频: {segment_name}")
    if download_video(api_url, node_out, save_path):
        # ===== 新增：精确裁剪视频为20秒（最后一段按实际时长） =====
        target_duration = min(duration_seconds, 20)   # 裁剪目标时长
        if target_duration < duration_seconds:
            from utils.audio_utils import FFMPEG
            import subprocess
            trimmed_path = save_path.replace('.mp4', '_trimmed.mp4')
            cmd = [
                str(FFMPEG), '-y', '-i', save_path,
                '-t', str(target_duration),
                '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
                '-c:a', 'aac', '-b:a', '192k',
                trimmed_path
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                os.remove(save_path)
                os.rename(trimmed_path, save_path)
                if log_callback:
                    log_callback(f"视频已裁剪为 {target_duration} 秒")
            except Exception as e:
                if log_callback:
                    log_callback(f"裁剪失败，保留原始视频: {e}")
        # =====================================================
        if log_callback:
            log_callback(f"数字人视频片段已保存: {save_path}")
        return save_path
    else:
        raise Exception("下载视频失败")


def generate_digital_human_full(
    work_dir: str,
    image_path: str,
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
    prompt: str = "",
    seed: Optional[int] = None,
    api_url: Optional[str] = None,
    log_callback=None
) -> List[str]:
    """
    将最终音频按固定时长分段，依次生成数字人视频。
    """
    # 3. 继续原有音频检查、分段、生成逻辑
    final_audio = os.path.join(work_dir, "final_audio.mp3")
    if not os.path.exists(final_audio):
        raise FileNotFoundError(f"未找到最终音频文件: {final_audio}")

    total_duration = get_audio_duration(final_audio)
    if log_callback:
        log_callback(f"最终音频总时长: {total_duration:.2f} 秒，将按 {segment_seconds} 秒分段生成")

    video_paths = []
    total_segments = int((total_duration + step - 1) // step) + 1   # 新增
    segment_duration = 21          # 每段目标时长
    step = 20                      # 每次起始时间增量（重叠1秒）
    start = 0.0
    segment_idx = 1
    base_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

    max_retries = 3
    retry_delay = 5

    while start < total_duration:
        end = min(start + segment_duration, total_duration)
        current_duration = end - start
        if log_callback:
            log_callback(f"生成第 {segment_idx} 段: {format_time(start)} - {format_time(end)} (时长 {current_duration:.2f} 秒)")

        current_seed = base_seed + segment_idx - 1
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                video_path = generate_digital_human_segment(
                    work_dir=work_dir,
                    image_path=image_path,
                    audio_path=final_audio,
                    start_seconds=start,
                    duration_seconds=current_duration,
                    prompt=prompt,
                    seed=current_seed,
                    api_url=api_url,
                    log_callback=log_callback,
                    current=segment_idx,
                    total=total_segments
                )
                if video_path:
                    video_paths.append(video_path)
                    success = True
                    break
                else:
                    if log_callback:
                        log_callback(f"第 {segment_idx} 段第 {attempt} 次尝试失败，返回空路径")
            except Exception as e:
                if log_callback:
                    log_callback(f"第 {segment_idx} 段第 {attempt} 次尝试异常: {e}")
            if attempt < max_retries:
                time.sleep(retry_delay)
        if not success:
            if log_callback:
                log_callback(f"第 {segment_idx} 段重试 {max_retries} 次后仍然失败，跳过")

        start += step
        segment_idx += 1

    if log_callback:
        log_callback(f"数字人视频生成完成，成功 {len(video_paths)}/{segment_idx-1} 段")
    return video_paths


def format_time(seconds: float) -> str:
    """将秒数转换为 H:MM:SS 或 M:SS 格式（整数秒）"""
    total_seconds = int(round(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="生成数字人视频")
    parser.add_argument("work_dir", help="工作目录")
    parser.add_argument("image_path", help="数字人形象图片")
    parser.add_argument("--segment", type=int, default=30, help="每段时长（秒）")
    parser.add_argument("--prompt", default="", help="正面提示词")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    args = parser.parse_args()

    generate_digital_human_full(
        work_dir=args.work_dir,
        image_path=args.image_path,
        segment_seconds=args.segment,
        prompt=args.prompt,
        seed=args.seed,
        log_callback=print
    )