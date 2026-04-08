#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图生视频专用管理器（LTX 2.3）
支持单镜头生成：输入首帧图路径、提示词、时长、分辨率等，提交 ComfyUI 工作流，下载视频。
"""

import os
import sys
import json
import time
import random
import urllib.parse
import requests
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils import config_manager
from utils.error_logger import log_error

# 工作流模板路径
WORKFLOW_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "workflow_templates",
    "LTX2.3图生API.json"
)

# 默认分辨率（可根据需要调整）
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 24


def upload_image(api_url: str, local_path: str) -> Optional[str]:
    """上传图片到 ComfyUI input 目录，返回服务器上的文件名"""
    url = f"{api_url.rstrip('/')}/upload/image"
    with open(local_path, 'rb') as f:
        files = {'image': (os.path.basename(local_path), f, 'image/png')}
        try:
            resp = requests.post(url, files=files, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('name', os.path.basename(local_path))
            else:
                print(f"上传失败: {resp.status_code} {resp.text}")
                return None
        except Exception as e:
            print(f"上传异常: {e}")
            return None


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
            log_callback(f"正在生成视频，已等待 {elapsed} 秒...")
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
    """下载生成的视频文件"""
    # 输出节点82（VHS_VideoCombine）的输出可能包含 'videos' 列表
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


def trim_video(input_path, output_path, target_duration):
    """使用 ffmpeg 裁剪视频至目标时长（从头开始裁剪）"""
    from utils.audio_utils import FFMPEG
    cmd = [str(FFMPEG), '-y', '-i', input_path, '-t', str(target_duration), '-c', 'copy', output_path]
    try:
        import subprocess
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"视频裁剪失败: {e}")
        return False


def generate_single_video(
    work_dir: str,
    shot_id: str,
    image_path: str,
    prompt: str,
    duration: int,  # 秒
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    api_url: Optional[str] = None,
    log_callback=None,
    auto_trim: bool = True
) -> Optional[str]:
    """
    生成单个镜头的图生视频
    :param work_dir: 工作目录（用于确定输出文件夹）
    :param shot_id: 镜头ID（用于命名视频文件）
    :param image_path: 首帧图本地路径
    :param prompt: 英文提示词
    :param duration: 目标时长（秒）
    :param width, height: 视频分辨率（默认1280x720）
    :param api_url: ComfyUI API地址
    :param log_callback: 日志回调
    :param auto_trim: 是否自动裁剪到目标时长（工作流生成的时长可能不精确）
    :return: 保存的视频路径，失败返回 None
    """
    if api_url is None:
        api_url = config_manager.COMFYUI_API_URL

    if not os.path.exists(WORKFLOW_TEMPLATE):
        raise FileNotFoundError(f"工作流模板不存在: {WORKFLOW_TEMPLATE}")

    # 上传首帧图
    if log_callback:
        log_callback(f"上传首帧图: {os.path.basename(image_path)}")
    uploaded_name = upload_image(api_url, image_path)
    if not uploaded_name:
        raise Exception(f"首帧图上传失败: {image_path}")

    # 加载工作流
    with open(WORKFLOW_TEMPLATE, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 设置节点10：加载首帧图
    workflow["10"]["inputs"]["image"] = uploaded_name

    # 设置节点5：正面提示词
    workflow["5"]["inputs"]["text"] = prompt

    # 设置节点83：时长（秒） -> 转换为帧数？工作流中节点83直接作为时长（秒），后续节点11计算总帧数
    # 节点83是一个 INTConstant，直接设置 value
    workflow["83"]["inputs"]["value"] = duration

    # 随机化种子节点40和74（两个采样器分支）
    seed = random.randint(0, 2**32 - 1)
    workflow["40"]["inputs"]["noise_seed"] = seed
    workflow["74"]["inputs"]["noise_seed"] = seed
    if log_callback:
        log_callback(f"设置随机种子: {seed}")

    # 设置分辨率（节点54 TTResolutionSelector）
    if width is not None and height is not None:
        if "54" in workflow and workflow["54"]["class_type"] == "TTResolutionSelector":
            custom_w = width // 2
            custom_h = height // 2
            workflow["54"]["inputs"]["use_custom_resolution"] = True
            workflow["54"]["inputs"]["custom_width"] = custom_w
            workflow["54"]["inputs"]["custom_height"] = custom_h
            if log_callback:
                log_callback(f"设置图生视频分辨率: {width}x{height} -> custom {custom_w}x{custom_h}")
        else:
            if log_callback:
                log_callback("警告：工作流中未找到节点54（TTResolutionSelector），无法设置分辨率")
    print(f"节点54设置: use_custom_resolution={workflow['54']['inputs'].get('use_custom_resolution')}, custom_width={workflow['54']['inputs'].get('custom_width')}, custom_height={workflow['54']['inputs'].get('custom_height')}")

    # 提交工作流
    if log_callback:
        log_callback("提交图生视频工作流...")

    # 提交工作流
    if log_callback:
        log_callback("提交图生视频工作流...")
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        raise Exception("提交工作流失败")
    if log_callback:
        log_callback(f"工作流已提交，prompt_id={prompt_id}")

    # 等待完成
    history = wait_for_history(api_url, prompt_id, timeout=600, log_callback=log_callback)
    if not history:
        raise Exception("等待超时或任务失败")

    # 提取输出视频（节点82 VHS_VideoCombine）
    outputs = history[prompt_id].get('outputs', {})
    if "82" not in outputs:
        raise Exception("未找到节点82的输出")
    node_out = outputs["82"]

    # 确定输出文件夹（工作目录/视频）
    video_dir = os.path.join(work_dir, "视频")
    os.makedirs(video_dir, exist_ok=True)
    temp_video_path = os.path.join(video_dir, f"temp_{shot_id}.mp4")
    final_video_path = os.path.join(video_dir, f"镜头{shot_id}.mp4")

    # 下载视频
    if log_callback:
        log_callback("下载视频文件...")
    if download_video(api_url, node_out, temp_video_path):
        # 裁剪到目标时长
        if auto_trim:
            if log_callback:
                log_callback(f"裁剪视频至 {duration} 秒...")
            if trim_video(temp_video_path, final_video_path, duration):
                os.remove(temp_video_path)
                if log_callback:
                    log_callback(f"镜头 {shot_id} 视频已保存: {final_video_path}")
                return final_video_path
            else:
                # 裁剪失败，保留原文件
                os.rename(temp_video_path, final_video_path)
                if log_callback:
                    log_callback(f"裁剪失败，保留原始视频: {final_video_path}")
                return final_video_path
        else:
            os.rename(temp_video_path, final_video_path)
            if log_callback:
                log_callback(f"镜头 {shot_id} 视频已保存（未裁剪）: {final_video_path}")
            return final_video_path
    else:
        raise Exception("下载视频失败")


if __name__ == "__main__":
    # 测试示例（需要提供有效的参数）
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    parser.add_argument("shot_id")
    parser.add_argument("image_path")
    parser.add_argument("prompt")
    parser.add_argument("duration", type=int)
    args = parser.parse_args()
    generate_single_video(
        work_dir=args.work_dir,
        shot_id=args.shot_id,
        image_path=args.image_path,
        prompt=args.prompt,
        duration=args.duration,
        log_callback=print
    )