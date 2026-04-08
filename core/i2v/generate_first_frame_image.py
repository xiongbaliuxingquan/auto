#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成分镜首帧图（图生图批量）
根据 first_frame_prompts.json 中的提示词和角色定妆照，一次性生成所有镜头的首帧图。
"""

import os
import sys
import json
import time
import random
import urllib.parse
import requests
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils import config_manager
from utils.error_logger import log_error

# 工作流模板路径（分镜图片制作）
WORKFLOW_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "workflow_templates",
    "分镜图片制作.json"
)

MAX_BATCH_SIZE = 12  # 工作流单次最多支持12个镜头


def upload_image(api_url: str, local_path: str) -> Optional[str]:
    """上传本地图片到 ComfyUI input 目录，返回服务器上的文件名"""
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
    """等待工作流完成，返回 history 字典"""
    url = f"{api_url.rstrip('/')}/history/{prompt_id}"
    start_time = time.time()
    last_log_time = start_time
    timeout = 600
    history = None
    while time.time() - start_time < timeout:
        elapsed = time.time() - start_time
        if time.time() - last_log_time >= 10:
            msg = f"正在生成分镜图，已等待 {int(elapsed)} 秒..."
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
            last_log_time = time.time()
        url = f"{api_url.rstrip('/')}/history/{prompt_id}"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if prompt_id in data:
                    history = data
                    break
        except Exception as e:
            if log_callback:
                log_callback(f"查询异常: {e}")
            else:
                print(f"查询异常: {e}")
        time.sleep(2)
    return None


def download_image(api_url: str, output_info: dict, save_path: str) -> bool:
    """下载单张图片"""
    filename = output_info.get('filename')
    subfolder = output_info.get('subfolder', '')
    img_url = f"{api_url.rstrip('/')}/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type=output"
    try:
        resp = requests.get(img_url, stream=True, timeout=60)
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


def get_character_asset_path(work_dir: str) -> Optional[str]:
    """获取第一个角色的定妆照路径（用于节点21）"""
    # 从 assets_global.txt 解析角色名
    global_path = os.path.join(work_dir, "assets_global.txt")
    if not os.path.exists(global_path):
        return None
    with open(global_path, 'r', encoding='utf-8') as f:
        content = f.read()
    import re
    match = re.search(r'【[^】]*\s+([^】]+)】', content)
    if not match:
        return None
    character_name = match.group(1).strip()
    asset_path = os.path.join(work_dir, "images", f"{character_name}.png")
    if os.path.exists(asset_path):
        return asset_path
    return None


def load_prompts(work_dir: str) -> List[tuple]:
    """加载 first_frame_prompts.json，返回 [(shot_id, prompt), ...]"""
    prompts_path = os.path.join(work_dir, "first_frame_prompts.json")
    if not os.path.exists(prompts_path):
        raise FileNotFoundError(f"未找到首帧图提示词文件: {prompts_path}")
    with open(prompts_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [(item['shot_id'], item['prompt']) for item in data]


def generate_batch(
    work_dir: str,
    asset_image_path: str,
    prompts: List[tuple],
    api_url: Optional[str] = None,
    log_callback=None,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> List[str]:
    if api_url is None:
        api_url = config_manager.COMFYUI_API_URL

    if not os.path.exists(WORKFLOW_TEMPLATE):
        raise FileNotFoundError(f"工作流模板不存在: {WORKFLOW_TEMPLATE}")

    uploaded_name = upload_image(api_url, asset_image_path)
    if not uploaded_name:
        raise Exception(f"定妆照上传失败: {asset_image_path}")

    with open(WORKFLOW_TEMPLATE, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 设置节点21：加载定妆照
    workflow["21"]["inputs"]["image"] = uploaded_name

    # 设置分辨率（如果提供）
    if width is not None and height is not None:
        if "18" in workflow and workflow["18"]["class_type"] == "EmptyFlux2LatentImage":
            workflow["18"]["inputs"]["width"] = width
            workflow["18"]["inputs"]["height"] = height
            if log_callback:
                log_callback(f"设置分镜图分辨率: {width}x{height}")
        else:
            if log_callback:
                log_callback("警告：工作流中未找到节点18（EmptyFlux2LatentImage），无法设置分辨率")

    # 设置节点35：拼接提示词
    prompt_lines = [p[1] for p in prompts]
    combined_prompt = "\n".join(prompt_lines)
    workflow["35"]["inputs"]["prompt"] = combined_prompt

    if "2" in workflow and "inputs" in workflow["2"]:
        workflow["2"]["inputs"]["noise_seed"] = random.randint(0, 2**64 - 1)
        if log_callback:
            log_callback(f"[DEBUG] 设置随机种子: {workflow['2']['inputs']['noise_seed']}")
        else:
            print(f"[DEBUG] 设置随机种子: {workflow['2']['inputs']['noise_seed']}")
    else:
        if log_callback:
            log_callback("[DEBUG] 未找到节点2，无法设置随机种子")
        else:
            print("[DEBUG] 未找到节点2，无法设置随机种子")

    if log_callback:
        log_callback("[DEBUG] 提交分镜图生成工作流...")
    else:
        print("[DEBUG] 提交分镜图生成工作流...")
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        raise Exception("提交工作流失败")
    if log_callback:
        log_callback(f"[DEBUG] 工作流已提交，prompt_id={prompt_id}")
    else:
        print(f"[DEBUG] 工作流已提交，prompt_id={prompt_id}")

    start_time = time.time()
    last_log_time = start_time
    timeout = 600
    history = None
    while time.time() - start_time < timeout:
        elapsed = time.time() - start_time
        if time.time() - last_log_time >= 10:
            msg = f"正在生成分镜图，已等待 {int(elapsed)} 秒..."
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
            last_log_time = time.time()
        url = f"{api_url.rstrip('/')}/history/{prompt_id}"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if prompt_id in data:
                    history = data
                    break
        except Exception as e:
            if log_callback:
                log_callback(f"查询异常: {e}")
            else:
                print(f"查询异常: {e}")
        time.sleep(2)

    if not history:
        raise Exception("等待超时或任务失败")

    outputs = history[prompt_id].get('outputs', {})
    if "27" not in outputs:
        raise Exception("未找到节点27的输出")
    images_output = outputs["27"].get('images', [])
    if len(images_output) != len(prompts):
        if log_callback:
            log_callback(f"警告：生成图片数量({len(images_output)})与镜头数({len(prompts)})不匹配")
        else:
            print(f"警告：生成图片数量({len(images_output)})与镜头数({len(prompts)})不匹配")

    saved_paths = []
    images_dir = os.path.join(work_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    for idx, (shot_id, _) in enumerate(prompts):
        if idx >= len(images_output):
            break
        img_info = images_output[idx]
        save_path = os.path.join(images_dir, f"{shot_id}.png")
        if download_image(api_url, img_info, save_path):
            saved_paths.append(save_path)
            if log_callback:
                log_callback(f"已保存镜头 {shot_id} 首帧图: {save_path}")
            else:
                print(f"已保存镜头 {shot_id} 首帧图: {save_path}")
        else:
            saved_paths.append("")
    return saved_paths


def generate_all_first_frames(work_dir: str, log_callback=None, width: Optional[int] = None, height: Optional[int] = None) -> List[str]:
    """
    生成所有镜头的首帧图
    返回生成的图片路径列表
    """
    # 1. 获取定妆照路径
    asset_path = get_character_asset_path(work_dir)
    if not asset_path:
        if log_callback:
            log_callback("错误：未找到角色定妆照，请先生成资产图")
        return []

    # 2. 加载提示词
    try:
        prompts = load_prompts(work_dir)
    except Exception as e:
        if log_callback:
            log_callback(f"加载提示词失败: {e}")
        return []
    if not prompts:
        if log_callback:
            log_callback("提示词列表为空")
        return []

    if log_callback:
        log_callback(f"共 {len(prompts)} 个镜头，开始批量生成首帧图...")

    # 3. 分批处理（每批最多12个）
    all_saved = []
    for i in range(0, len(prompts), MAX_BATCH_SIZE):
        batch = prompts[i:i+MAX_BATCH_SIZE]
        if log_callback:
            log_callback(f"正在生成第 {i//MAX_BATCH_SIZE + 1} 批（{len(batch)} 个镜头）...")
        try:
            saved = generate_batch(work_dir, asset_path, batch, log_callback=log_callback, width=width, height=height)
            all_saved.extend(saved)
        except Exception as e:
            if log_callback:
                log_callback(f"批量生成失败: {e}")
            return all_saved
        time.sleep(2)

    if log_callback:
        success_count = sum(1 for p in all_saved if p)
        log_callback(f"首帧图生成完成，成功 {success_count}/{len(prompts)}")
    return all_saved


def generate_single_frame(work_dir: str, shot_id: str, prompt: str, log_callback=None) -> Optional[str]:
    """重新生成单个镜头的首帧图（占位，暂不实现，因为批量生成更高效）"""
    # 本函数暂时不实现，因为单张生成可复用批量逻辑但需要单独调用工作流
    # 实际上可以使用批量生成函数，只传一个镜头
    asset_path = get_character_asset_path(work_dir)
    if not asset_path:
        if log_callback:
            log_callback("错误：未找到角色定妆照")
        return None
    try:
        saved = generate_batch(work_dir, asset_path, [(shot_id, prompt)])
        if saved and saved[0]:
            return saved[0]
    except Exception as e:
        if log_callback:
            log_callback(f"重新生成失败: {e}")
    return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    args = parser.parse_args()
    generate_all_first_frames(args.work_dir, log_callback=print)