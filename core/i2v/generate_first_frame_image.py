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

# 工作流模板路径（分镜图片制作，按角色数量区分）
TEMPLATE_BY_CHAR_COUNT = {
    1: os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workflow_templates", "分镜图片制作_1图.json"),
    2: os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workflow_templates", "分镜图片制作_2图.json"),
    3: os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "workflow_templates", "分镜图片制作_3图.json"),
}

def extract_characters_from_prompt(prompt: str, all_characters: List[str]) -> List[str]:
    """
    从提示词中提取出现的角色名（按 all_characters 中的顺序，主角优先）
    返回角色名列表，例如 ["琪琪", "妈妈"]
    """
    found = []
    for char in all_characters:
        if char in prompt:
            found.append(char)
    return found

def group_prompts_by_characters(prompts: List[tuple], all_characters: List[str]) -> Dict[tuple, List[tuple]]:
    """
    将提示词按角色组合分组
    prompts: [(shot_id, prompt), ...]
    all_characters: 所有角色名列表（顺序重要，第一个为主角）
    返回 {角色组合元组: [(shot_id, prompt), ...]}
    """
    groups = {}
    for shot_id, prompt in prompts:
        chars = extract_characters_from_prompt(prompt, all_characters)
        if not chars and all_characters:
            chars = [all_characters[0]]   # 默认使用主角
        # 确保主角始终在第一个（如果主角出现在列表中）
        if all_characters and all_characters[0] in chars:
            # 将主角移到最前
            chars.remove(all_characters[0])
            chars.insert(0, all_characters[0])
        key = tuple(chars)
        groups.setdefault(key, []).append((shot_id, prompt))
    
    # ========== 添加分组打印 ==========
    print(f"\n[分组] 共 {len(groups)} 个角色组合:")
    for chars, lst in groups.items():
        shot_ids = [sid for sid, _ in lst]
        print(f"  组合 {chars} 包含 {len(lst)} 个镜头: {shot_ids}")
    # ================================
    
    return groups

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
    height: Optional[int] = None,
    characters: Optional[List[str]] = None
) -> List[str]:
    """
    生成一批首帧图（最多12个）
    characters: 该批次中所有镜头涉及的角色列表（去重后的），顺序为 [主角, 配角1, 配角2]
    """
    # 处理单角色模式（兼容旧调用）
    if not characters:
        if asset_image_path:
            base = os.path.basename(asset_image_path)
            char_name = os.path.splitext(base)[0]
            characters = [char_name]
        else:
            # 尝试从工作目录解析角色列表
            from core.i2v.generate_asset_image import parse_global_assets
            _, chars_dict = parse_global_assets(work_dir)
            if chars_dict:
                characters = [list(chars_dict.keys())[0]]
            else:
                raise ValueError("未提供任何角色图片，无法生成首帧图")
    
    if api_url is None:
        api_url = config_manager.COMFYUI_API_URL

    # 打印批次信息
    print(f"\n[批量] 角色组合 {characters}, 共 {len(prompts)} 个镜头: {[sid for sid,_ in prompts]}")
    if log_callback:
        log_callback(f"角色组合 {characters}，镜头数 {len(prompts)}")

    # 准备角色图片路径
    images_dir = os.path.join(work_dir, "images")
    character_image_paths = {}
    for char in characters:
        path = os.path.join(images_dir, f"{char}.png")
        if not os.path.exists(path):
            raise FileNotFoundError(f"角色 {char} 的定妆照不存在: {path}")
        character_image_paths[char] = path

    # 上传所有需要的角色定妆照
    uploaded_names = {}
    for char, path in character_image_paths.items():
        uploaded_name = upload_image(api_url, path)
        if not uploaded_name:
            raise Exception(f"定妆照上传失败: {char} ({path})")
        uploaded_names[char] = uploaded_name
        print(f"[上传] 角色 {char} 定妆照上传成功: {uploaded_name}")
        if log_callback:
            log_callback(f"已上传角色 {char} 定妆照: {uploaded_name}")

    # 根据角色数量选择模板
    char_count = len(characters)
    if char_count not in TEMPLATE_BY_CHAR_COUNT:
        raise ValueError(f"不支持的角色数量: {char_count}，仅支持1-3个角色")
    workflow_template = TEMPLATE_BY_CHAR_COUNT[char_count]
    print(f"[模板] 使用模板: {os.path.basename(workflow_template)}")
    if log_callback:
        log_callback(f"使用模板: {os.path.basename(workflow_template)}")

    # 加载工作流模板
    with open(workflow_template, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 设置节点21（主角图片）
    main_char = characters[0]
    workflow["21"]["inputs"]["image"] = uploaded_names[main_char]
    print(f"[工作流] 设置节点21图片: {main_char}")
    if log_callback:
        log_callback(f"设置节点21为主角: {main_char}")

    # 如果有第二个角色，设置节点41
    if char_count >= 2:
        char2 = characters[1]
        workflow["41"]["inputs"]["image"] = uploaded_names[char2]
        print(f"[工作流] 设置节点41图片: {char2}")
        if log_callback:
            log_callback(f"设置节点41为配角: {char2}")

    # 如果有第三个角色，设置节点47
    if char_count >= 3:
        char3 = characters[2]
        workflow["47"]["inputs"]["image"] = uploaded_names[char3]
        print(f"[工作流] 设置节点47图片: {char3}")
        if log_callback:
            log_callback(f"设置节点47为配角: {char3}")

    # 设置分辨率
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

    # 随机化种子
    if "2" in workflow and "inputs" in workflow["2"]:
        workflow["2"]["inputs"]["noise_seed"] = random.randint(0, 2**64 - 1)
        if log_callback:
            log_callback(f"[DEBUG] 设置随机种子: {workflow['2']['inputs']['noise_seed']}")
    else:
        if log_callback:
            log_callback("[DEBUG] 未找到节点2，无法设置随机种子")

    # 提交工作流
    if log_callback:
        log_callback("[DEBUG] 提交分镜图生成工作流...")
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        raise Exception("提交工作流失败")
    if log_callback:
        log_callback(f"[DEBUG] 工作流已提交，prompt_id={prompt_id}")

    # 等待完成（带进度日志）
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

def generate_all_first_frames(work_dir: str, log_callback=None, width: Optional[int] = None, height: Optional[int] = None, all_characters: Optional[List[str]] = None) -> List[str]:
    """
    生成所有镜头的首帧图
    返回生成的图片路径列表
    """
    # 1. 加载提示词
    try:
        prompts = load_prompts(work_dir)
        print(f"[DEBUG] 待处理镜头总数: {len(prompts)}, 列表: {[sid for sid, _ in prompts]}")
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

    # 2. 如果提供了角色列表，则按角色组合分组
    if all_characters:
        # 按角色组合分组
        groups = group_prompts_by_characters(prompts, all_characters)
        if log_callback:
            log_callback(f"角色组合分组: {list(groups.keys())}")
        all_saved = []
        for chars, group_prompts in groups.items():
            # 计算批次数
            num_batches = (len(group_prompts) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE
            print(f"\n[总进度] 正在处理角色组合 {chars}，共 {len(group_prompts)} 个镜头，分 {num_batches} 批")
            if log_callback:
                log_callback(f"正在生成角色组合 {chars} 的 {len(group_prompts)} 个镜头...")
            # 分批处理（每组可能超过12个）
            for i in range(0, len(group_prompts), MAX_BATCH_SIZE):
                batch = group_prompts[i:i+MAX_BATCH_SIZE]
                try:
                    # 注意：asset_image_path 参数不再使用，传空字符串即可
                    saved = generate_batch(work_dir, "", batch, log_callback=log_callback, width=width, height=height, characters=list(chars))
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
    else:
        # 无角色信息时，回退到旧逻辑（单角色）
        asset_path = get_character_asset_path(work_dir)
        if not asset_path:
            if log_callback:
                log_callback("错误：未找到角色定妆照，请先生成资产图")
            return []
        # 打印总体进度
        num_batches = (len(prompts) + MAX_BATCH_SIZE - 1) // MAX_BATCH_SIZE
        print(f"\n[总进度] 无角色列表，使用单角色模式，共 {len(prompts)} 个镜头，分 {num_batches} 批")
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

def generate_single_frame(
    work_dir: str,
    shot_id: str,
    prompt: str,
    log_callback=None,
    all_characters: Optional[List[str]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> Optional[str]:
    """
    重新生成单个镜头的首帧图
    根据提示词提取角色，选择对应模板，上传图片，提交工作流，下载图片
    """
    # 打印接收到的分辨率
    print(f"[DEBUG] generate_single_frame 收到分辨率: width={width}, height={height}")

    # 1. 获取角色列表（如果未提供，则从全局资产解析）
    if not all_characters:
        from core.i2v.generate_asset_image import parse_global_assets
        _, chars_dict = parse_global_assets(work_dir)
        all_characters = list(chars_dict.keys()) if chars_dict else []
    if not all_characters:
        if log_callback:
            log_callback("错误：未找到任何角色信息")
        return None

    # 2. 从提示词中提取角色
    chars = extract_characters_from_prompt(prompt, all_characters)
    if not chars:
        # 默认使用主角
        chars = [all_characters[0]]
    # 确保主角在第一位
    if all_characters and all_characters[0] in chars:
        chars.remove(all_characters[0])
        chars.insert(0, all_characters[0])
    characters = chars

    # 3. 准备图片路径
    images_dir = os.path.join(work_dir, "images")
    char_paths = {}
    for char in characters:
        path = os.path.join(images_dir, f"{char}.png")
        if not os.path.exists(path):
            if log_callback:
                log_callback(f"角色 {char} 的定妆照不存在: {path}")
            return None
        char_paths[char] = path

    # 4. 上传图片
    api_url = config_manager.COMFYUI_API_URL
    uploaded_names = {}
    for char, path in char_paths.items():
        uploaded_name = upload_image(api_url, path)
        if not uploaded_name:
            if log_callback:
                log_callback(f"上传角色 {char} 定妆照失败")
            return None
        uploaded_names[char] = uploaded_name
        if log_callback:
            log_callback(f"已上传角色 {char} 定妆照")

    # 5. 选择模板
    char_count = len(characters)
    if char_count not in TEMPLATE_BY_CHAR_COUNT:
        if log_callback:
            log_callback(f"不支持的角色数量: {char_count}")
        return None
    workflow_template = TEMPLATE_BY_CHAR_COUNT[char_count]
    with open(workflow_template, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 6. 设置节点图片
    workflow["21"]["inputs"]["image"] = uploaded_names[characters[0]]
    if char_count >= 2:
        workflow["41"]["inputs"]["image"] = uploaded_names[characters[1]]
    if char_count >= 3:
        workflow["47"]["inputs"]["image"] = uploaded_names[characters[2]]

    # 7. 设置提示词（节点35）
    workflow["35"]["inputs"]["prompt"] = prompt

    # 8. 设置分辨率（如果提供了宽高）
    if width is not None and height is not None:
        # 使用节点18设置分辨率
        if "18" in workflow and workflow["18"]["class_type"] == "EmptyFlux2LatentImage":
            workflow["18"]["inputs"]["width"] = width
            workflow["18"]["inputs"]["height"] = height
            if log_callback:
                log_callback(f"设置分镜图分辨率: {width}x{height}")
        else:
            if log_callback:
                log_callback("警告：工作流中未找到节点18（EmptyFlux2LatentImage），无法设置分辨率")

    # 9. 随机种子（节点2）
    if "2" in workflow:
        workflow["2"]["inputs"]["noise_seed"] = random.randint(0, 2**64 - 1)

    # 10. 提交工作流
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        if log_callback:
            log_callback("提交工作流失败")
        return None

    # 11. 内联轮询等待结果
    if log_callback:
        log_callback(f"等待镜头 {shot_id} 生成，prompt_id={prompt_id}")
    start_time = time.time()
    last_log_time = start_time
    timeout = 600
    history = None
    while time.time() - start_time < timeout:
        elapsed = time.time() - start_time
        if time.time() - last_log_time >= 10:
            msg = f"正在生成镜头 {shot_id}，已等待 {int(elapsed)} 秒..."
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
        if log_callback:
            log_callback("等待超时或任务失败")
        return None

    # 12. 提取输出图片
    outputs = history[prompt_id].get('outputs', {})
    if "27" not in outputs:
        if log_callback:
            log_callback("未找到节点27的输出")
        return None
    images_output = outputs["27"].get('images', [])
    if not images_output:
        if log_callback:
            log_callback("没有生成图片")
        return None

    img_info = images_output[0]
    save_path = os.path.join(images_dir, f"{shot_id}.png")
    if download_image(api_url, img_info, save_path):
        if log_callback:
            log_callback(f"已保存镜头 {shot_id} 首帧图: {save_path}")
        return save_path
    else:
        if log_callback:
            log_callback("下载图片失败")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("work_dir")
    args = parser.parse_args()
    generate_all_first_frames(args.work_dir, log_callback=print)