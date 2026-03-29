import os
import time
import requests
from . import config_manager

API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
API_TIMEOUT = config_manager.API_TIMEOUT

def call_deepseek(prompt, temperature=0.3, max_tokens=8000):
    """
    调用 DeepSeek API，返回响应文本。
    此函数不处理日志，由调用者自行记录。
    """
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
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
            {"role": "system", "content": "你是一个专业的视频分镜设计师，必须严格遵循给定的人物和场景设定生成内容。所有输出（包括提示词）必须使用中文，不得使用英文或其他语言。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=API_TIMEOUT)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            error_detail = f"HTTP {status}: {response.text}"
            raise Exception(error_detail)
    except requests.exceptions.Timeout:
        error_msg = f"API 请求超时（超过 {API_TIMEOUT} 秒）"
        raise Exception(error_msg)
    except Exception as e:
        raise