# core/omnivoice_tts.py
"""
OmniVoice 语音克隆模块：调用 ComfyUI 工作流（OmniVoice克隆API.json）生成音频。
支持情绪标签、多音字注音、语速调节，适合长文本快速合成。
"""

import os
import json
import re
import time
import random
import requests
import urllib.parse
from typing import Optional

# 导入主应用的配置管理器
from utils import config_manager

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "workflow_templates",
    "OmniVoice克隆API.json"
)
def sanitize_filename(text: str) -> str:
    """清洗文本用于文件名"""
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9_]', '_', text)
    text = re.sub(r'_+', '_', text)
    return text[:30]


def upload_audio(api_url: str, local_file_path: str) -> Optional[str]:
    """上传参考音频到 ComfyUI input 目录，返回服务器上的文件名"""
    if not os.path.exists(local_file_path):
        raise FileNotFoundError(f"本地文件不存在: {local_file_path}")
    url = f"{api_url.rstrip('/')}/upload/image"
    # 生成安全文件名（替换空格和特殊字符）
    safe_filename = re.sub(r'[^\w\.\-]', '_', os.path.basename(local_file_path))
    with open(local_file_path, 'rb') as f:
        files = {'image': (safe_filename, f, 'audio/mpeg')}
        try:
            resp = requests.post(url, files=files, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('name', safe_filename)
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


def wait_for_audio(api_url: str, prompt_id: str, output_node: str = "6", timeout: int = 600, log_callback=None) -> Optional[str]:
    """等待音频生成完成，返回音频文件的访问 URL（相对路径）"""
    url = f"{api_url.rstrip('/')}/history/{prompt_id}"
    start = time.time()
    last_log = start
    while time.time() - start < timeout:
        if log_callback and (time.time() - last_log) >= 10:
            elapsed = int(time.time() - start)
            log_callback(f"正在生成音频（OmniVoice），已等待 {elapsed} 秒...")
            last_log = time.time()
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                history = resp.json()
                if prompt_id in history:
                    outputs = history[prompt_id].get('outputs', {})
                    if output_node in outputs:
                        node_out = outputs[output_node]
                        if 'audio' in node_out:
                            audio_info = node_out['audio'][0]
                            filename = audio_info.get('filename')
                            subfolder = audio_info.get('subfolder', '')
                            audio_url = f"/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type=output"
                            return audio_url
            time.sleep(2)
        except Exception as e:
            print(f"查询状态异常: {e}")
            time.sleep(2)
    return None


def download_audio(api_url: str, audio_url: str, save_path: str, max_retries: int = 3) -> bool:
    """下载音频，使用临时文件避免占用冲突"""
    temp_path = save_path + ".tmp"
    full_url = f"{api_url.rstrip('/')}{audio_url}"
    try:
        resp = requests.get(full_url, stream=True, timeout=120)
        if resp.status_code != 200:
            print(f"下载失败: {resp.status_code}")
            return False
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        # 写入临时文件
        with open(temp_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        # 尝试替换原文件
        for attempt in range(max_retries):
            try:
                if os.path.exists(save_path):
                    os.remove(save_path)
                os.rename(temp_path, save_path)
                return True
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(1)  # 等待1秒后重试
                else:
                    print(f"无法覆盖被占用的文件，临时文件保留为: {temp_path}")
                    # 可在此处记录日志或提示用户
        return False
    except Exception as e:
        print(f"下载异常: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return False

def generate_single_omnivoice(
    text: str,
    index: int,
    output_dir: str,
    ref_audio_filename: str,
    speed: float = 1.0,
    log_callback=None
) -> Optional[str]:
    """
    生成单个音频片段（OmniVoice）
    :param text: 带标签的文本
    :param index: 片段序号（用于文件命名）
    :param output_dir: 输出目录
    :param ref_audio_filename: 参考音频在 ComfyUI 服务器上的文件名
    :param speed: 语速因子
    :param log_callback: 日志回调
    :return: 本地音频路径
    """
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"模板不存在: {TEMPLATE_PATH}")

    api_url = config_manager.COMFYUI_API_URL   # 使用专属地址

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 节点1：参考音频（已在服务器上，直接用文件名）
    workflow["1"]["inputs"]["audio"] = ref_audio_filename

    # 节点4：文本
    workflow["4"]["inputs"]["prompt"] = text

    # 节点5：种子和语速
    workflow["5"]["inputs"]["seed"] = random.randint(0, 2147483647)
    workflow["5"]["inputs"]["speed"] = speed

    # 提交工作流
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        return None

    audio_url = wait_for_audio(api_url, prompt_id, output_node="6", log_callback=log_callback)
    if not audio_url:
        return None

    save_path = os.path.join(output_dir, f"segment_{index:03d}.mp3")
    if download_audio(api_url, audio_url, save_path):
        return save_path
    return None


def generate_omnivoice_audio(
    text: str,
    ref_audio_path: str,
    work_dir: str,
    speed: float = 1.0,
    seed: int = None,
    log_callback=None
) -> Optional[str]:
    """
    调用 OmniVoice 工作流生成音频。

    :param text: 要合成的文本（可包含情绪标签如 [laughter]，多音字注音如 ZHE2）
    :param ref_audio_path: 参考音频本地路径（用于音色克隆）
    :param work_dir: 工作目录，音频将保存为 预览_序号_描述.mp3
    :param speed: 语速因子，>1.0 为加快，<1.0 为减慢。推荐范围 0.8~1.5
    :param seed: 随机种子，不传则自动生成
    :param log_callback: 日志回调函数
    :return: 成功返回本地音频文件路径，失败返回 None
    """
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"工作流模板不存在: {TEMPLATE_PATH}")

    api_url = config_manager.COMFYUI_API_URL   # 使用专属地址
    if not api_url or api_url == "请配置API地址":
        raise ValueError("OmniVoice API 地址未配置，请在设置中填写")

    # 1. 上传参考音频
    if log_callback:
        log_callback(f"上传参考音频: {os.path.basename(ref_audio_path)}")
    uploaded_name = upload_audio(api_url, ref_audio_path)
    if not uploaded_name:
        raise Exception("参考音频上传失败")

    # 2. 加载工作流模板
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 3. 设置节点参数
    workflow["1"]["inputs"]["audio"] = uploaded_name
    workflow["4"]["inputs"]["prompt"] = text

    if seed is None:
        seed = random.randint(0, 2147483647)
    workflow["5"]["inputs"]["seed"] = seed
    workflow["5"]["inputs"]["speed"] = speed

    # 4. 提交工作流
    if log_callback:
        log_callback("提交 OmniVoice 工作流...")
    prompt_id = submit_workflow(api_url, workflow)
    if not prompt_id:
        raise Exception("提交工作流失败")

    if log_callback:
        log_callback(f"工作流已提交，prompt_id={prompt_id}")

    # 5. 等待音频生成
    audio_url = wait_for_audio(api_url, prompt_id, output_node="6", log_callback=log_callback)
    if not audio_url:
        raise Exception("等待音频生成超时或失败")

    # 6. 生成唯一文件名
    import glob
    existing = glob.glob(os.path.join(work_dir, "预览_*.mp3"))
    max_idx = 0
    for f in existing:
        match = re.match(r'预览_(\d+)_.*\.mp3', os.path.basename(f))
        if match:
            max_idx = max(max_idx, int(match.group(1)))
    next_idx = max_idx + 1
    base_desc = os.path.splitext(os.path.basename(ref_audio_path))[0]
    desc_sanitized = sanitize_filename(base_desc)
    filename = f"预览_{next_idx:02d}_{desc_sanitized}.mp3"
    save_path = os.path.join(work_dir, filename)

    # 7. 下载音频
    if log_callback:
        log_callback("下载音频文件...")
    if download_audio(api_url, audio_url, save_path):
        if log_callback:
            log_callback(f"OmniVoice 音频已保存: {save_path}")
        return save_path
    else:
        raise Exception("下载音频失败")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("用法: python omnivoice_tts.py <文本> <参考音频路径> <工作目录> [语速]")
        sys.exit(1)
    text = sys.argv[1]
    ref_audio = sys.argv[2]
    work_dir = sys.argv[3]
    speed = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
    result = generate_omnivoice_audio(text, ref_audio, work_dir, speed=speed, log_callback=print)
    if result:
        print(f"生成成功: {result}")
    else:
        print("生成失败")