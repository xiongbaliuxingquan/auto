"""
================================================================================
【重要修改提示】
本文件涉及与外部系统的关键交互，任何修改前请务必：
1. 核对当前使用的模板及节点ID（见 workflow_config.json）。
2. 在小范围（如单个镜头）测试验证，确认无误后再批量运行。
3. 若修改涉及节点ID或 API 参数，请先与用户确认实际值，切勿凭经验猜测。
================================================================================
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import re
import requests
import json
import time
import glob
from datetime import datetime
from utils import settings, concurrent_utils, config_manager
from utils.error_logger import log_error

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
if not DEEPSEEK_API_KEY:
    raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置，请在 GUI 中配置 API Key")
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
API_TIMEOUT = config_manager.API_TIMEOUT

def clean_text(text):
    """移除不可见控制字符（保留换行、回车、制表符）"""
    import re
    # 保留 \n \r \t，移除其他控制字符
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return cleaned

def get_latest_readable_file(output_dir, pattern="分镜结果_易读版_*.txt"):
    """在 output_dir 中查找最新的易读版文件"""
    full_pattern = os.path.join(output_dir, pattern)
    files = glob.glob(full_pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def extract_prompts_by_keyword(readable_file):
    with open(readable_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    prompts = []
    i = 0
    total = len(lines)

    while i < total:
        line = lines[i].strip()
        if '提示词' in line:
            colon_pos = line.find('：')
            if colon_pos == -1:
                colon_pos = line.find(':')
            if colon_pos != -1:
                after_colon = line[colon_pos+1:].strip()
                if after_colon:
                    prompts.append(after_colon)
                    i += 1
                    continue
                else:
                    i += 1
                    content_lines = []
                    while i < total:
                        next_line = lines[i].strip()
                        if (next_line.startswith('##') or 
                            next_line.startswith('---') or 
                            next_line.startswith('==========') or 
                            next_line == ''):
                            break
                        content_lines.append(next_line)
                        i += 1
                    prompt = ' '.join(content_lines).strip()
                    if prompt:
                        prompts.append(prompt)
                    continue
            else:
                i += 1
                content_lines = []
                while i < total:
                    next_line = lines[i].strip()
                    if (next_line.startswith('##') or 
                        next_line.startswith('---') or 
                        next_line.startswith('==========') or 
                        next_line == ''):
                        break
                    content_lines.append(next_line)
                    i += 1
                prompt = ' '.join(content_lines).strip()
                if prompt:
                    prompts.append(prompt)
                continue
        i += 1
    return prompts

def translate_text(text, target_lang="English"):
    prompt = f"请将以下中文提示词翻译成{target_lang}，只输出翻译结果，不要添加任何额外内容：\n\n{text}"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业翻译助手。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 500
    }
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            return f"[翻译失败] HTTP {response.status_code}: {response.text}"
    except Exception as e:
        log_error('extract_prompts', '翻译异常', str(e))
        return f"[翻译失败] 异常: {str(e)}"

def check_prompts_language(prompts):
    english_indicators = []
    for i, p in enumerate(prompts):
        if re.search(r'[a-zA-Z]{4,}', p) and len(re.findall(r'[a-zA-Z]', p)) > len(p) * 0.3:
            english_indicators.append(i+1)
    return english_indicators

def clean_prompt(prompt):
    """清洗单条提示词"""
    cleaned = prompt.replace('；', ',').replace(';', ',')
    cleaned = cleaned.rstrip(';')
    return cleaned + ';'

def save_prompts(prompts, chinese_file, english_file, bilingual_file=None):
    # 清洗并保存中文列表
    with open(chinese_file, 'w', encoding='utf-8') as f:
        for p in prompts:
            cleaned = clean_text(p)  # 清洗
            f.write(cleaned + '\n')
    print(f"中文提示词已保存至：{chinese_file}")
    sys.stdout.flush()

    total = len(prompts)
    print(f"正在翻译 {total} 条提示词，并发数 {settings.MAX_WORKERS}...")
    sys.stdout.flush()

    def worker(item, idx):
        result = translate_text(item)
        return clean_prompt(result)

    def progress_callback(idx, res, success):
        if success:
            print(f"翻译第 {idx+1}/{total} 条完成。")
        else:
            print(f"翻译第 {idx+1}/{total} 条失败: {res}")
        sys.stdout.flush()

    raw_results, errors = concurrent_utils.concurrent_process(
        prompts, worker, max_workers=settings.MAX_WORKERS, ordered=True,
        progress_callback=progress_callback
    )

    english_prompts = raw_results

    if errors:
        print(f"警告：以下位置的提示词翻译失败: {list(errors.keys())}")
        sys.stdout.flush()
        for idx, err in errors.items():
            log_error('extract_prompts', f'翻译失败（索引{idx+1}）', err)
            print(f"  第 {idx+1} 条: {err}")
            sys.stdout.flush()

    with open(english_file, 'w', encoding='utf-8') as f:
        for eng in english_prompts:
            f.write(eng + '\n')
    print(f"英文提示词已保存至：{english_file}")
    sys.stdout.flush()

    if bilingual_file:
        with open(bilingual_file, 'w', encoding='utf-8') as f:
            # 双语文件的中文部分也进行清洗
            for p in prompts:
                f.write(clean_text(p) + '\n')
            f.write('\n==============\n\n')
            for eng in english_prompts:
                f.write(eng + '\n')
        print(f"双语合并文件已保存至：{bilingual_file}")
        sys.stdout.flush()

def check_storyboard_integrity(output_dir, readable_file):
    """检查易读版分镜文件中的镜头数量是否与 input.json 中的 shots 总数一致"""
    input_json = os.path.join(output_dir, "input.json")
    if not os.path.exists(input_json):
        print("警告：找不到 input.json，无法进行完整性检查。")
        sys.stdout.flush()
        return

    with open(input_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    expected_shots = sum(len(seg.get('shots', [])) for seg in data.get('segments', []))

    with open(readable_file, 'r', encoding='utf-8') as f:
        content = f.read()
    actual_shots = len(re.findall(r'【镜头\d+-\d+：', content))

    if actual_shots == expected_shots:
        print(f"完整性检查通过：易读版中共 {actual_shots} 个镜头，与 input.json 一致。")
    else:
        print(f"⚠️ 警告：易读版镜头数 ({actual_shots}) 与预期镜头数 ({expected_shots}) 不符！请检查 output.json 中的错误记录。")
    sys.stdout.flush()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python extract_prompts.py <输出目录>")
        sys.stdout.flush()
        sys.exit(1)
    output_dir = sys.argv[1]

    readable_file = get_latest_readable_file(output_dir)
    if readable_file is None:
        print(f"在 {output_dir} 中未找到任何易读版文件（分镜结果_易读版_*.txt），请检查目录。")
        sys.stdout.flush()
        sys.exit(1)

    print(f"使用文件：{readable_file}")
    sys.stdout.flush()

    prompts = extract_prompts_by_keyword(readable_file)
    if not prompts:
        print("未找到任何提示词，请检查文件格式。")
        sys.stdout.flush()
        sys.exit(1)

    print(f"找到 {len(prompts)} 条提示词。")
    sys.stdout.flush()

    english_indices = check_prompts_language(prompts)
    if english_indices:
        print(f"警告：以下位置的提示词可能为英文（索引从1开始）：{english_indices}")
    else:
        print("所有提示词均为中文，语言检查通过。")
    sys.stdout.flush()

    timestamp = datetime.now().strftime("%m%d_%H%M")
    chinese_file = os.path.join(output_dir, f"prompts_chinese_{timestamp}.txt")
    english_file = os.path.join(output_dir, f"prompts_english_{timestamp}.txt")
    bilingual_file = os.path.join(output_dir, f"prompts_bilingual_{timestamp}.txt")

    save_prompts(prompts, chinese_file, english_file, bilingual_file)

    # 完整性检查
    check_storyboard_integrity(output_dir, readable_file)