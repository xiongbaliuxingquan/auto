# core/txt_to_json.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import requests
import time
from datetime import datetime
from utils import settings, concurrent_utils, config_manager
from utils.error_logger import log_error

print("========== 使用最新版 txt_to_json ==========")

# 全局变量，用于存储当前运行的日志文件路径（带时间戳）
CURRENT_STEP1_LOG = None

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
API_TIMEOUT = config_manager.API_TIMEOUT

def call_deepseek(prompt, temperature=0.3, max_tokens=8000):
    """
    调用 DeepSeek API，将响应记录到日志文件。
    日志文件由全局变量 CURRENT_STEP1_LOG 指定，若未指定则使用默认的 ai_step1_raw.log。
    """
    global CURRENT_STEP1_LOG
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        # 尝试从配置加载
        api_key, _ = config_manager.load_config()
        if api_key:
            os.environ['DEEPSEEK_API_KEY'] = api_key
        else:
            raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置，请在 GUI 中配置 API Key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是一个专业的剧本分析助手，能够从原始文稿中提取结构化信息。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    start_time = time.time()

    # 确定日志文件路径
    if CURRENT_STEP1_LOG is None:
        # 未设置时使用默认（无时间戳）
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "ai_step1_raw.log")
    else:
        log_file = CURRENT_STEP1_LOG
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    print("正在请求 DeepSeek API...")
    sys.stdout.flush()

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=API_TIMEOUT)
        elapsed = time.time() - start_time
        status = response.status_code
        response_text = response.text

        print(f"API 响应耗时 {elapsed:.2f}s，状态码 {status}")
        sys.stdout.flush()

        # 写入日志
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now()} 耗时:{elapsed:.2f}s 状态码:{status} ---\n")
            f.write(f"Prompt预览: {prompt[:200]}...\n")
            f.write(response_text + "\n")

        if status == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            raise Exception(f"API调用失败: {status} {response_text}")

    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        error_msg = f"API 请求超时（超过 {API_TIMEOUT} 秒）"
        print(error_msg)
        log_error('txt_to_json', error_msg, f"耗时: {elapsed:.2f}s")
        raise Exception(error_msg)

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"API 请求异常: {str(e)}")
        log_error('txt_to_json', 'API请求异常', str(e))
        raise

PARSER_MAP = {
    "情感故事": "story_parser.StoryParser",
    "文明结构": "analysis_parser.AnalysisParser",
    "动画默剧": "mime_parser.MimeParser",
    "自由模式": "free_parser.FreeParser"   # 新增
}

def parse_txt_to_json(txt_path, output_dir, story_title=None, mode="情感故事"):
    """
    读取文本文件，调用对应模式的解析器生成结构化数据，保存为 header.txt 和 shots.txt。
    :param txt_path: 输入文本文件路径
    :param output_dir: 输出目录（将在此目录下生成 header.txt 和 shots.txt）
    :param story_title: 故事标题
    :param mode: 文稿类型
    """
    global CURRENT_STEP1_LOG

    # 生成带时间戳的日志文件路径
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    CURRENT_STEP1_LOG = os.path.join(log_dir, f"ai_step1_raw_{timestamp}.log")

    print(f"开始解析文本文件: {txt_path}")
    sys.stdout.flush()

    with open(txt_path, 'r', encoding='utf-8') as f:
        raw_text = f.read()
    print(f"文本长度: {len(raw_text)} 字符")
    sys.stdout.flush()

    # ==================== 新增：提取口播稿原文 ====================
    import re
    pattern = r'★口播稿开始★\s*(.*?)\s*★口播稿结束★'
    match = re.search(pattern, raw_text, re.DOTALL)
    oral_text = match.group(1).strip() if match else ""
    # 这里可以将 oral_text 保存到临时文件或作为后续参数，目前只做提取
    # ============================================================

    if mode not in PARSER_MAP:
        raise ValueError(f"未知模式: {mode}")

    module_path, class_name = PARSER_MAP[mode].split('.')
    print(f"正在导入解析器: {module_path}.{class_name}")
    sys.stdout.flush()
    module = __import__(f"parsers.{module_path}", fromlist=[class_name])
    ParserClass = getattr(module, class_name)

    parser = ParserClass(call_deepseek, story_title=story_title, mode=mode)
    print(f"使用解析器: {mode}")
    sys.stdout.flush()

    print("正在调用 AI 生成结构化数据，请稍候...")
    sys.stdout.flush()
    try:
        output_data = parser.parse(raw_text)
    except Exception as e:
        log_error('txt_to_json', 'AI解析失败', str(e))
        raise
    print("AI 解析完成")
    sys.stdout.flush()

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 生成 header.txt
    header_path = os.path.join(output_dir, "header.txt")
    with open(header_path, 'w', encoding='utf-8') as f:
        f.write(f"project: {output_data.get('project', story_title or '未知')}\n")
        f.write(f"style: {output_data['global'].get('style', '电影感、写实、自然光影')}\n")
        f.write(f"seed: {output_data['global'].get('seed', 12345)}\n")
        # persona 和 scene 可能为空对象，直接写入 {}，后续用 json.loads 解析
        f.write(f"persona: {json.dumps(output_data.get('persona', {}), ensure_ascii=False)}\n")
        f.write(f"scene: {json.dumps(output_data.get('scene', {}), ensure_ascii=False)}\n")
    print(f"已生成 {header_path}")
    sys.stdout.flush()

    # 生成 shots.txt
    shots_path = os.path.join(output_dir, "shots.txt")
    with open(shots_path, 'w', encoding='utf-8') as f:
        for seg in output_data['segments']:
            seg_id = seg['id']
            content = seg.get('content', '')  # 段落的原始文本
            for shot_idx, shot in enumerate(seg['shots'], start=1):
                print(f"shot dict: {shot}")
                print("shot keys:", shot.keys())
                print(f"[DEBUG] shot: {shot}")
                f.write(f"【镜头{seg_id}-{shot_idx}：{seg['title']}】\n")
                f.write(f"- 时长：{shot['duration']}秒\n")
                f.write(f"- 情绪基调：{shot['emotion']}\n")
                region = shot.get('region', '全球')
                f.write(f"- 地域：{region}\n")
                # 写入从段落内容获取的口播稿
                f.write(f"- 口播稿：{shot.get('script', '')}\n")
                f.write(f"- 视觉描述：{shot['visual']}\n")
                f.write("===========================\n")
    print(f"已生成 {shots_path}")
    sys.stdout.flush()

    # 不再生成 input.json，但为了兼容后续可能需要的风格参数文件，仍生成 style_params.json
    style_params = {
        "style": output_data['global'].get('style', '电影感、写实、自然光影'),
        "film_simulation": "柯达2383",
        "shutter_angle": 180,
        "frame_rate": 24,
        "motion_blur": "natural",
        "lighting": "自然光影",
        "color_tone": "冷静的蓝灰色调",
        "contrast": "高对比度",
        "grain": "轻微胶片颗粒",
        "safety": "无文字，无频闪",
        "camera_motion": "匀速缓慢推近"
    }
    style_path = os.path.join(output_dir, "style_params.json")
    with open(style_path, 'w', encoding='utf-8') as f:
        json.dump(style_params, f, ensure_ascii=False, indent=2)
    print(f"已生成 {style_path}")
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("用法: python txt_to_json.py <输入文件路径> <故事标题> <模式> <输出目录>")
        sys.exit(1)

    input_txt = sys.argv[1]
    title = sys.argv[2]
    mode = sys.argv[3]
    out_dir = sys.argv[4]

    parse_txt_to_json(input_txt, out_dir, story_title=title, mode=mode)