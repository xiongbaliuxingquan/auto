# generate_first_frame_prompts.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # 将项目根目录加入路径
import re
import json
import glob
import time
import requests
from datetime import datetime

from utils import settings, concurrent_utils, translation_utils
from utils.error_logger import log_error

def extract_paragraphs(shots_file):
    """
    从 shots.txt 中提取镜头信息。
    返回一个列表，每个元素为 (段落ID, 镜头索引, 原文段落, 视觉描述, 时长, 情绪)
    原文段落留空。
    """
    tasks = []
    with open(shots_file, 'r', encoding='utf-8') as f:
        content = f.read()
    # 按分隔符拆分
    blocks = re.split(r'\n\s*===========================\s*\n', content)
    for block in blocks:
        if not block.strip():
            continue
        # 匹配镜头头
        header_match = re.match(r'【镜头(\d+)-(\d+)：([^】]+)】', block.strip(), re.DOTALL)
        if not header_match:
            continue
        seg_id = int(header_match.group(1))
        shot_id = int(header_match.group(2))
        title = header_match.group(3).strip()
        # 提取时长
        duration_match = re.search(r'- 时长[：:]\s*(\d+)', block)
        duration = int(duration_match.group(1)) if duration_match else 10
        # 提取情绪
        emotion_match = re.search(r'- 情绪基调[：:]\s*([^\n]+)', block)
        emotion = emotion_match.group(1).strip() if emotion_match else ""
        # 提取视觉描述
        visual_match = re.search(r'- 视觉描述[：:]\s*(.*?)(?=\n|$)', block, re.DOTALL)
        visual = visual_match.group(1).strip() if visual_match else ""
        # 原文段落留空
        tasks.append((seg_id, shot_id, "", visual, duration, emotion))
    return tasks

def generate_first_frame_prompt(visual, duration, emotion):
    """调用 AI 生成一个镜头的首帧提示词（中文）"""
    prompt = f"""
请为以下镜头生成一个高质量的静态图像提示词，用于后续图生视频。

【视觉核心参考】：{visual}
【镜头时长】：{duration}秒
【原始情绪】：{emotion}

【生成要求】：
1. 必须严格基于【视觉核心参考】中的描述，可以适当细化，但不得改变核心意象、风格和情绪。
2. 聚焦于静态画面，突出构图、光影、细节、情绪。
3. 不要包含任何关于镜头运动、时间推移的词语。
4. 输出的提示词应为纯净文本，无任何额外标记。

请输出首帧提示词：
"""
    headers = {
        "Authorization": f"Bearer {translation_utils.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 500
    }
    try:
        response = requests.post(translation_utils.API_URL, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"].strip()
            # 清洗常见标记
            result = re.sub(r'\*\*首帧提示词：\*\*', '', result)
            result = re.sub(r'\*\*', '', result)
            result = re.sub(r'首帧提示词[：:]', '', result)
            return result.strip()
        else:
            return f"[生成失败] HTTP {response.status_code}"
    except Exception as e:
        log_error('generate_first_frame', '生成首帧提示词异常', str(e))
        return f"[生成失败] 异常: {str(e)}"

def worker(item, idx):
    """
    并发工作函数：处理一个镜头，返回 (para_id, shot_idx, original_content, video_prompt, chinese, english)
    """
    para_id, shot_idx, original_content, visual, duration, emotion = item
    video_prompt = ""
    chinese = generate_first_frame_prompt(visual, duration, emotion)
    english = translation_utils.translate_text(chinese)
    return (para_id, shot_idx, original_content, video_prompt, chinese, english)

def main():
    if len(sys.argv) < 2:
        print("用法: python generate_first_frame_prompts.py <工作目录>")
        sys.exit(1)
    work_dir = sys.argv[1]
    os.chdir(work_dir)

    shots_file = "shots.txt"
    if not os.path.exists(shots_file):
        print("未找到 shots.txt")
        return

    tasks = extract_paragraphs(shots_file)

    total_tasks = len(tasks)
    print(f"共提取 {total_tasks} 个镜头，并发数 {settings.MAX_WORKERS}")

    def progress_callback(idx, result, success):
        if success:
            print(f"镜头 {result[0]}-{result[1]} 生成完成")
        else:
            print(f"镜头 {idx+1} 生成失败: {result}")

    results, errors = concurrent_utils.concurrent_process(
        tasks, worker, max_workers=settings.MAX_WORKERS, ordered=True,
        progress_callback=progress_callback
    )

    if errors:
        print(f"警告：以下镜头生成失败: {list(errors.keys())}")
        for idx, err in errors.items():
            log_error('generate_first_frame', f'镜头{idx}生成失败', err)
            print(f"  镜头 {idx}: {err}")

    csv_rows = []
    for res in results:
        if res is None:
            continue
        para_id, shot_idx, original_content, video_prompt, chinese, english = res
        csv_rows.append({
            "序号": f"{para_id}-{shot_idx}",
            "段落": original_content,  # 现在为空
            "视频提示词": video_prompt,
            "中文首帧提示词": chinese,
            "英文首帧提示词": english
        })

    # 按序号排序（段落-镜头）
    csv_rows.sort(key=lambda x: [int(part) for part in x["序号"].split('-')])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    csv_file = f"首帧提示词对照表_{timestamp}.csv"
    with open(csv_file, 'w', encoding='utf-8-sig') as f:
        f.write('\ufeff')
        header = ["序号", "段落", "视频提示词", "中文首帧提示词", "英文首帧提示词"]
        f.write(','.join(f'"{h}"' for h in header) + '\n')
        for row in csv_rows:
            line = []
            for h in header:
                cell = row[h].replace('"', '""')
                line.append(f'"{cell}"')
            f.write(','.join(line) + '\n')
    print(f"CSV 文件已生成: {csv_file}")

    txt_file = f"首帧提示词列表_{timestamp}.txt"
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write("中文首帧提示词列表：\n")
        for row in csv_rows:
            f.write(row["中文首帧提示词"] + ';\n')
        f.write("\n英文首帧提示词列表：\n")
        for row in csv_rows:
            f.write(row["英文首帧提示词"] + ';\n')
    print(f"纯文本列表已生成: {txt_file}")

if __name__ == "__main__":
    main()