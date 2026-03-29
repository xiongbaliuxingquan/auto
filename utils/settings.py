# settings.py
import os
import json

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "user_settings.json")

# 默认参数
DEFAULT_SETTINGS = {
    "GLOBAL_THRESHOLD": 2000,   # 启用并发处理的文本阈值（字符数）
    "CHUNK_SIZE": 300,           # 每个块的最大字符数
    "MAX_WORKERS": 8,             # 最大并发线程数
    "BATCH_SIZE": 3   # 新增
}

def load_settings():
    """从 JSON 文件加载设置，若文件不存在则返回默认值"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
            # 只合并存在的键，缺失的键使用默认值
            return {**DEFAULT_SETTINGS, **user_settings}
        except Exception:
            return DEFAULT_SETTINGS.copy()
    else:
        return DEFAULT_SETTINGS.copy()

# 加载设置
_settings = load_settings()

# 导出为模块级变量，方便其他脚本导入
GLOBAL_THRESHOLD = _settings["GLOBAL_THRESHOLD"]
CHUNK_SIZE = _settings["CHUNK_SIZE"]
MAX_WORKERS = _settings["MAX_WORKERS"]
BATCH_SIZE = _settings["BATCH_SIZE"]   # 新增导出