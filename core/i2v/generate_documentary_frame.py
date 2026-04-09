#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
纪录片/文明结构专用：纯文生图，无角色定妆照
"""

import sys
import os
import json
import time
import random
import requests
from typing import List, Optional, Tuple
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils import config_manager
from .generate_asset_image import upload_image, submit_workflow, download_image, wait_for_history

def generate_documentary_frames(
    work_dir: str,
    prompts: List[Tuple[str, str]],  # [(shot_id, prompt), ...]
    width: int = 1920,
    height: int = 1080,
    log_callback=None
) -> List[str]:
    """
    为纪录片生成首帧图（无角色，直接文生图）
    返回保存的图片路径列表
    """
    api_url = config_manager.COMFYUI_API_URL
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "workflow_templates",
        "qwenimage文生图.json"
    )
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"模板不存在: {template_path}")

    with open(template_path, 'r', encoding='utf-8') as f:
        base_workflow = json.load(f)

    # 设置全局分辨率
    if "25" in base_workflow and base_workflow["25"]["class_type"] == "EmptyLatentImage":
        base_workflow["25"]["inputs"]["width"] = width
        base_workflow["25"]["inputs"]["height"] = height
        if log_callback:
            log_callback(f"设置分辨率: {width}x{height}")
    else:
        if log_callback:
            log_callback("警告：工作流中未找到节点25")

    saved_paths = []
    images_dir = os.path.join(work_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    for idx, (shot_id, prompt) in enumerate(prompts):
        if log_callback:
            log_callback(f"正在生成镜头 {shot_id} 首帧图 ({idx+1}/{len(prompts)})...")
        workflow = json.loads(json.dumps(base_workflow))
        # 设置提示词
        if "24" in workflow and workflow["24"]["class_type"] == "CLIPTextEncode":
            workflow["24"]["inputs"]["text"] = prompt
        else:
            if log_callback:
                log_callback("错误：工作流中未找到节点24")
            continue
        # 随机种子
        if "21" in workflow and "inputs" in workflow["21"]:
            workflow["21"]["inputs"]["seed"] = random.randint(0, 2**64 - 1)
        # 提交
        prompt_id = submit_workflow(api_url, workflow)
        if not prompt_id:
            if log_callback:
                log_callback(f"提交工作流失败: {shot_id}")
            continue
        # 等待
        history = wait_for_history(api_url, prompt_id, log_callback=log_callback)
        if not history:
            if log_callback:
                log_callback(f"等待超时: {shot_id}")
            continue
        outputs = history[prompt_id].get('outputs', {})
        if "19" not in outputs:
            if log_callback:
                log_callback(f"未找到节点19的输出: {shot_id}")
            continue
        images_output = outputs["19"].get('images', [])
        if not images_output:
            if log_callback:
                log_callback(f"没有生成图片: {shot_id}")
            continue
        img_info = images_output[0]
        save_path = os.path.join(images_dir, f"{shot_id}.png")
        if download_image(api_url, img_info, save_path):
            saved_paths.append(save_path)
            if log_callback:
                log_callback(f"已保存镜头 {shot_id} 首帧图: {save_path}")
        else:
            if log_callback:
                log_callback(f"下载失败: {shot_id}")
    return saved_paths