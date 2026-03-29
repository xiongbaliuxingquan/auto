# translation_utils.py
import os
import requests
import time
from . import config_manager   # 相对导入

# ===== 配置区域 =====
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
if not DEEPSEEK_API_KEY:
    raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置，请在 GUI 中配置 API Key")
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"
# ===================

def translate_text(text, target_lang="English"):
    """调用 DeepSeek API 翻译文本，返回翻译后的结果或错误信息"""
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
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            return f"[翻译失败] HTTP {response.status_code}: {response.text}"
    except Exception as e:
        return f"[翻译失败] 异常: {str(e)}"