# fish_tts.py
"""
Fish S2 语音合成模块：单段生成模式。
"""

import os
import sys
import json
import time
import random
import requests
import urllib.parse
from typing import Optional, Dict

# 导入主应用的配置管理器
from utils import config_manager

API_URL = config_manager.COMFYUI_API_URL
TTS_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflow_templates", "FishS2Clone.json")

# 工作流模板路径
WHISPER_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "workflow_templates",
    "Wisper.json"
)
TTS_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "workflow_templates",
    "FishS2Clone.json"
)

def upload_file(api_url: str, local_file_path: str) -> Optional[str]:
    """上传本地音频文件到 ComfyUI 的 input 目录，返回服务器上的文件名"""
    if not os.path.exists(local_file_path):
        raise FileNotFoundError(f"本地文件不存在: {local_file_path}")
    url = f"{api_url.rstrip('/')}/upload/image"
    with open(local_file_path, 'rb') as f:
        files = {'image': (os.path.basename(local_file_path), f, 'audio/mpeg')}
        try:
            resp = requests.post(url, files=files, timeout=30)
            if resp.status_code == 200:
                return resp.json().get('name', os.path.basename(local_file_path))
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

def wait_for_history(api_url: str, prompt_id: str, timeout: int = 300, log_callback=None) -> Optional[dict]:
    """等待工作流完成，返回 history 字典，每10秒输出等待日志"""
    url = f"{api_url.rstrip('/')}/history/{prompt_id}"
    start = time.time()
    last_log = start
    while time.time() - start < timeout:
        if log_callback and (time.time() - last_log) >= 10:
            elapsed = int(time.time() - start)
            log_callback(f"正在生成音频，已等待 {elapsed} 秒...")
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

def wait_for_audio(api_url: str, prompt_id: str, output_node: str, timeout: int = 300, log_callback=None) -> Optional[str]:
    """等待音频生成完成，返回音频文件的访问 URL（相对路径），支持日志回调"""
    history = wait_for_history(api_url, prompt_id, timeout, log_callback=log_callback)
    if not history:
        return None
    outputs = history[prompt_id].get('outputs', {})
    if output_node in outputs:
        node_out = outputs[output_node]
        if 'audio' in node_out:
            audio_info = node_out['audio'][0]
            filename = audio_info.get('filename')
            subfolder = audio_info.get('subfolder', '')
            audio_url = f"/view?filename={urllib.parse.quote(filename)}&subfolder={urllib.parse.quote(subfolder)}&type=output"
            return audio_url
    return None

def download_audio(api_url: str, audio_url: str, save_path: str) -> bool:
    """下载音频文件到本地"""
    full_url = f"{api_url.rstrip('/')}{audio_url}"
    try:
        resp = requests.get(full_url, stream=True, timeout=60)
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

def generate_single(text: str, index: int, output_dir: str, ref_audio_filename: str, ref_text: str, language: str = "zh", log_callback=None) -> Optional[str]:
    """生成单个音频片段，返回文件路径，失败返回 None"""
    with open(TTS_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        workflow = json.load(f)

    # 修改节点
    workflow["14"]["inputs"]["audio"] = ref_audio_filename
    workflow["12"]["inputs"]["reference_text"] = ref_text
    workflow["12"]["inputs"]["seed"] = random.randint(0, 2147483647)
    workflow["12"]["inputs"]["language"] = language
    workflow["26"]["inputs"]["positive"] = text

    # 提交
    prompt_id = submit_workflow(API_URL, workflow)
    if not prompt_id:
        print("提交工作流失败")
        return None

    # 等待
    audio_url = wait_for_audio(API_URL, prompt_id, "29", log_callback=log_callback)
    if not audio_url:
        print("等待音频生成失败")
        return None

    # 下载
    save_path = os.path.join(output_dir, f"segment_{index:03d}.mp3")
    success = download_audio(API_URL, audio_url, save_path)
    if success:
        print(f"下载成功: {save_path}")
        return save_path
    else:
        print(f"下载失败: {audio_url}")
        return None

def extract_reference_text(work_dir: str, ref_audio_path: str) -> Optional[Dict]:
    print("开始提取参考文本...")
    # 上传音频
    print(f"上传音频: {ref_audio_path}")
    ref_filename = upload_file(API_URL, ref_audio_path)
    if not ref_filename:
        print("上传失败：ref_filename 为空")
        return None
    print(f"上传成功，文件名: {ref_filename}")

    # 加载 Whisper 工作流模板
    with open(WHISPER_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        whisper_workflow = json.load(f)
    whisper_workflow["14"]["inputs"]["audio"] = ref_filename
    print("已设置 Whisper 工作流音频节点")

    # 提交
    prompt_id = submit_workflow(API_URL, whisper_workflow)
    if not prompt_id:
        print("提交工作流失败")
        return None
    print(f"提交成功，prompt_id: {prompt_id}")

    # 等待完成
    history = wait_for_history(API_URL, prompt_id, timeout=120)
    if not history:
        print("等待历史超时或无结果")
        return None
    print(f"获取到历史记录: {history.keys()}")

    # 提取文本
    outputs = history[prompt_id]['outputs']
    if "36" in outputs:
        text = outputs["36"]["text"][0]
        print("从节点36提取文本成功")
    elif "13" in outputs and 'text' in outputs["13"]:
        text = outputs["13"]["text"][0]
        print("从节点13提取文本成功")
    else:
        print("无法从输出中提取文本，outputs内容:", outputs)
        return None

    # 保存缓存
    cache = {"audio_filename": ref_filename, "reference_text": text}
    cache_path = os.path.join(work_dir, "reference_cache.json")
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"参考文本已缓存: {cache_path}")
    return cache

if __name__ == "__main__":
    # 示例用法
    if len(sys.argv) < 6:
        print("用法: python fish_tts.py <文本> <序号> <输出目录> <参考音频文件名> <参考文本> [语言]")
        sys.exit(1)
    text = sys.argv[1]
    idx = int(sys.argv[2])
    out_dir = sys.argv[3]
    ref_audio = sys.argv[4]
    ref_text = sys.argv[5]
    lang = sys.argv[6] if len(sys.argv) > 6 else "zh"
    result = generate_single(text, idx, out_dir, ref_audio, ref_text, lang)
    if result:
        print(f"生成成功: {result}")
    else:
        print("生成失败")