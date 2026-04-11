#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
角色定妆照生成模块（图生视频专用）
根据全局资产和段落1资产生成角色全身像（文生图）。
"""

import os
import sys
import json
import re
import time
import random
import urllib.parse
import requests
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from utils import config_manager
from utils.error_logger import log_error

# 工作流模板路径（文生图）
WORKFLOW_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "workflow_templates",
    "qwenimage文生图.json"
)

# 默认提示词模板（强制正面全身+目视镜头）
DEFAULT_POSITIVE_TEMPLATE = (
    "超高清，超高细节，{character_desc}"
    "环境：{scene_desc}"
    "{era_constraint}"
    "全身像，正面面对镜头，眼睛直视镜头，必须完整显示人物从头到脚，且脚底位于画面底部。"
    "站在场景中，{style_desc}"
    "禁止侧脸、背影、低头、闭眼，"
)

def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name[:50]

print("准备提交工作流...")
def submit_workflow(api_url: str, workflow: dict) -> Optional[str]:
    url = f"{api_url.rstrip('/')}/prompt"
    payload = {"prompt": workflow}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            print(f"[DEBUG] Workflow submitted successfully. Full API response: {result}") # <--- 添加这一行
            return result.get('prompt_id')
        else:
            print(f"提交失败: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"提交异常: {e}")
        return None
print(f"模板路径: {WORKFLOW_TEMPLATE}, 存在: {os.path.exists(WORKFLOW_TEMPLATE)}")

def download_image(api_url: str, output_info: dict, save_path: str) -> bool:
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


def parse_global_assets(work_dir: str) -> Tuple[str, Dict[str, str]]:
    """解析 assets_global.txt，返回 (整体视觉风格, {角色名: 完整描述})"""
    global_path = os.path.join(work_dir, "assets_global.txt")
    style = "电影质感，自然光影"
    characters = {}
    if not os.path.exists(global_path):
        print(f"警告: 未找到 {global_path}")
        return style, characters

    with open(global_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取整体视觉风格
    style_match = re.search(r'- 整体视觉风格：\s*(.*?)(?=\n-|\Z)', content, re.DOTALL)
    if style_match:
        style = style_match.group(1).strip()

    # 提取角色固定属性块
    block_match = re.search(r'- 角色固定属性：\s*\n(.*?)(?=\n-|\Z)', content, re.DOTALL)
    if block_match:
        block = block_match.group(1)
        lines = block.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 匹配新格式：【角色名】 种族：...，...
            match = re.match(r'【([^】]+)】\s+(.*)', line)
            if match:
                role_name = match.group(1).strip()
                raw_desc = match.group(2).strip()
                
                # --- 新增：清理字段标签，仅保留值 ---
                # 去掉类似 "种族："、"性别："、"年龄：" 等标签，只保留后面的值
                cleaned_desc = re.sub(r'[^，,]*?[：:]\s*', '', raw_desc)
                # 去掉开头可能多余的逗号或空格
                cleaned_desc = re.sub(r'^[\s,，]+', '', cleaned_desc)
                # --- 清理结束 ---
                
                characters[role_name] = cleaned_desc
    return style, characters

def parse_paragraph1_assets(work_dir: str) -> str:
    """解析 assets_paragraph_1.txt，提取场景描述"""
    para_path = os.path.join(work_dir, "assets_paragraph_1.txt")
    scene = "默认场景"
    if not os.path.exists(para_path):
        print(f"警告: 未找到 {para_path}")
        return scene
    with open(para_path, 'r', encoding='utf-8') as f:
        content = f.read()
    scene_match = re.search(r'- 场景：\s*(.*?)(?=\n-|\Z)', content, re.DOTALL)
    if scene_match:
        scene = scene_match.group(1).strip()
    return scene


def generate_asset_image(
    work_dir: str,
    character_name: str,
    character_desc: str,
    scene_desc: str,
    style_desc: str,
    api_url: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    log_callback=None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    output_filename: Optional[str] = None,   # 新增参数
    max_retries: int = 2                     # 重试次数
) -> Optional[str]:
    """生成单个角色定妆照，支持自定义提示词"""
    if api_url is None:
        api_url = config_manager.COMFYUI_API_URL

    # 重试循环
    for attempt in range(max_retries + 1):
        try:
            # 构建提示词
            if custom_prompt:
                positive_prompt = custom_prompt
            else:
                positive_prompt = DEFAULT_POSITIVE_TEMPLATE.format(
                    character_desc=character_desc,
                    scene_desc=scene_desc,
                    style_desc=style_desc,
                    era_constraint=""  # 临时占位，稍后会覆盖
                )

            # 读取世界观信息，生成时代约束（无论是否自定义提示词，都读取）
            era_constraint = ""
            metadata_path = os.path.join(work_dir, "metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    worldview = meta.get("世界观", {})
                    category = worldview.get("大类", "")
                    sub = worldview.get("子类", "")
                    
                    if category == "历史年代":
                        import re
                        match = re.search(r'[（(]([^）)]+)[）)]', sub)
                        dynasty = match.group(1) if match else "古代"
                        era_constraint = f"所有人物、建筑、服饰、道具必须严格符合{dynasty}时期特征。背景人群必须穿着该朝代平民服饰，"
                    elif category == "现实当代":
                        era_constraint = "现代都市风格，当代服饰与场景，自然真实。"
                    elif category in ["近未来", "远未来"]:
                        era_constraint = "科幻未来风格，高科技感，允许未来服饰与建筑。"
                    elif category == "奇幻异世界":
                        era_constraint = "奇幻架空风格，无现代科技，魔法与冷兵器时代。"
                    elif category == "现代都市奇幻":
                        era_constraint = "现代都市背景，允许当代科技与魔法、超自然元素共存，保持都市现实感。"
                    else:
                        era_constraint = "请根据场景描述推断时代特征，避免出现明显不协调的现代元素。"
                except Exception as e:
                    print(f"读取世界观失败: {e}")

            # 如果不是自定义提示词，需要重新格式化以加入 era_constraint
            if not custom_prompt:
                positive_prompt = DEFAULT_POSITIVE_TEMPLATE.format(
                    character_desc=character_desc,
                    scene_desc=scene_desc,
                    style_desc=style_desc,
                    era_constraint=era_constraint
                )
            if log_callback:
                log_callback(f"[DEBUG] 正面提示词: {positive_prompt[:100]}...")
            else:
                print(f"[DEBUG] 正面提示词: {positive_prompt[:100]}...")

            # 确定保存路径（根据是否提供 output_filename 决定）
            if output_filename:
                save_path = os.path.join(work_dir, "images", output_filename)
                prompt_save_path = save_path.replace('.png', '_prompt.txt')
            else:
                safe_name = sanitize_filename(character_name)
                save_path = os.path.join(work_dir, "images", f"{safe_name}.png")
                prompt_save_path = save_path.replace('.png', '_prompt.txt')
            
            os.makedirs(os.path.dirname(prompt_save_path), exist_ok=True)
            with open(prompt_save_path, 'w', encoding='utf-8') as pf:
                pf.write(positive_prompt)
            if log_callback:
                log_callback(f"[DEBUG] 提示词已保存到: {prompt_save_path}")
            else:
                print(f"[DEBUG] 提示词已保存到: {prompt_save_path}")

            # 如果 API URL 为空或明显无效，直接返回（提示词已保存）
            if not api_url or api_url == "请配置API地址":
                msg = "错误：ComfyUI API 地址未配置，已保存提示词文件，请配置后重新生成"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                return None

            if not os.path.exists(WORKFLOW_TEMPLATE):
                raise FileNotFoundError(f"模板不存在: {WORKFLOW_TEMPLATE}")
            with open(WORKFLOW_TEMPLATE, 'r', encoding='utf-8') as f:
                workflow = json.load(f)

            # 替换提示词节点
            if "24" in workflow and workflow["24"]["class_type"] == "CLIPTextEncode":
                workflow["24"]["inputs"]["text"] = positive_prompt
            else:
                msg = "错误：工作流中未找到节点24（CLIPTextEncode）"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                raise Exception(msg)   # 改为抛出异常，以便重试
            
            # 设置分辨率（如果提供）
            if width is not None and height is not None:
                if "25" in workflow and workflow["25"]["class_type"] == "EmptyLatentImage":
                    workflow["25"]["inputs"]["width"] = width
                    workflow["25"]["inputs"]["height"] = height
                    print(f"[DEBUG] 工作流节点25实际设置: width={workflow['25']['inputs']['width']}, height={workflow['25']['inputs']['height']}")
                    if log_callback:
                        log_callback(f"设置资产图分辨率: {width}x{height}")
                else:
                    if log_callback:
                        log_callback("警告：工作流中未找到节点25（EmptyLatentImage），无法设置分辨率")

            # 随机化种子
            if "21" in workflow and "inputs" in workflow["21"]:
                workflow["21"]["inputs"]["seed"] = random.randint(0, 2**64 - 1)
                if log_callback:
                    log_callback(f"[DEBUG] 设置随机种子: {workflow['21']['inputs']['seed']}")
                else:
                    print(f"[DEBUG] 设置随机种子: {workflow['21']['inputs']['seed']}")
            else:
                if log_callback:
                    log_callback("[DEBUG] 未找到节点21，无法设置随机种子")
                else:
                    print("[DEBUG] 未找到节点21，无法设置随机种子")

            # 提交任务
            if log_callback:
                log_callback("[DEBUG] 提交工作流...")
            else:
                print("[DEBUG] 提交工作流...")
            prompt_id = submit_workflow(api_url, workflow)
            if not prompt_id:
                msg = "错误：提交工作流失败（提示词已保存）"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                raise Exception(msg)   # 改为抛出异常
            
            if log_callback:
                log_callback(f"[DEBUG] 工作流已提交，prompt_id={prompt_id}")
            else:
                print(f"[DEBUG] 工作流已提交，prompt_id={prompt_id}")

            # 轮询结果
            start_time = time.time()
            last_log_time = start_time
            timeout = 300
            history = None
            while time.time() - start_time < timeout:
                elapsed = time.time() - start_time
                if time.time() - last_log_time >= 10:
                    msg = f"正在生成资产图，已等待 {int(elapsed)} 秒..."
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
                    msg = f"查询异常: {e}"
                    if log_callback:
                        log_callback(msg)
                    else:
                        print(msg)
                    import traceback
                    traceback.print_exc()
                    # 继续重试，不要 break
                time.sleep(3)

            if not history:
                msg = "错误：等待超时或任务失败（提示词已保存）"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                raise Exception(msg)   # 改为抛出异常

            outputs = history[prompt_id].get('outputs', {})
            if log_callback:
                log_callback(f"[DEBUG] 输出节点列表: {list(outputs.keys())}")
            else:
                print(f"[DEBUG] 输出节点列表: {list(outputs.keys())}")
            if "19" not in outputs:
                msg = "错误：未找到节点19的输出"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                raise Exception(msg)   # 改为抛出异常
            node_out = outputs["19"]
            if 'images' not in node_out or not node_out['images']:
                msg = "错误：节点19没有 images 字段或为空"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                raise Exception(msg)   # 改为抛出异常

            img_info = node_out['images'][0]
            if download_image(api_url, img_info, save_path):
                if log_callback:
                    log_callback(f"资产图已保存: {save_path}")
                else:
                    print(f"资产图已保存: {save_path}")
                return save_path
            else:
                msg = "错误：下载图片失败（提示词已保存）"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                raise Exception(msg)   # 改为抛出异常

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries:
                if log_callback:
                    log_callback(f"⚠️ 生成失败（{error_msg}），正在进行第 {attempt+1} 次重试...")
                time.sleep(2)
                continue
            else:
                if log_callback:
                    log_callback(f"❌ 生成失败，已达最大重试次数: {error_msg}")
                return None

def generate_asset_image_with_prompt(
    work_dir: str,
    character_name: str,
    character_desc: str,
    scene_desc: str,
    style_desc: str,
    custom_prompt: str,
    api_url: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> Optional[str]:
    """生成资产图，使用自定义提示词（便捷函数）"""
    return generate_asset_image(work_dir, character_name, character_desc, scene_desc, style_desc, api_url, custom_prompt, width=width, height=height)


def generate_all_assets(work_dir: str, log_callback=None, width: Optional[int] = None, height: Optional[int] = None) -> List[str]:
    """批量生成所有角色的资产图（使用默认提示词）"""
    style, characters = parse_global_assets(work_dir)
    print(f"DEBUG: characters = {characters}")
    if not characters:
        print("DEBUG: characters is empty, exiting")
        if log_callback:
            log_callback("未从全局资产中提取到任何角色")
        return []

    scene = parse_paragraph1_assets(work_dir)
    generated = []
    for name, desc in characters.items():
        if log_callback:
            log_callback(f"正在生成角色 {name} 的资产图...")
        path = generate_asset_image(work_dir, name, desc, scene, style, log_callback=log_callback, width=width, height=height)
        if path:
            generated.append(path)
            if log_callback:
                log_callback(f"✅ {name} 资产图已保存: {path}")
        else:
            if log_callback:
                log_callback(f"❌ {name} 资产图生成失败")
    return generated

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    args = parser.parse_args()
    generate_all_assets(args.work_dir, log_callback=print)