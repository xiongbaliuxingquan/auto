import os
import json

BASE_DIR = os.path.dirname(__file__)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USER_SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")

DEFAULT_USER_SETTINGS = {
    "GLOBAL_THRESHOLD": 2000,
    "CHUNK_SIZE": 300,
    "MAX_WORKERS": 8,
    "COMFYUI_API_URL": "https://u882129-773232801368.bjb2.seetacloud.com:8443",
    "VIDEO_OUTPUT_BASE_DIR": "D:/001视频提取",
    "OUTPUT_ROOT_DIR": BASE_DIR,
    "API_TIMEOUT": 120,
    "MAX_RETRIES": 3,
    "RETRY_DELAY": 5,
    "FUZZY_MATCH_THRESHOLD": 80,   # 新增
    "PRESET_EMOTIONAL": "emotional_default",
    "PRESET_CIVIL": "civil_default",
    "PRESET_MIME": "mime_default"
}

def load_config():
    """每次调用都重新读取 config.json，返回 (api_key, model)"""
    if not os.path.exists(CONFIG_FILE):
        return None, None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('api_key', ''), data.get('model', 'deepseek-chat')
    except Exception:
        return None, None

def save_config(api_key, model):
    data = {'api_key': api_key, 'model': model}
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def load_user_settings():
    if not os.path.exists(USER_SETTINGS_FILE):
        return DEFAULT_USER_SETTINGS.copy()
    try:
        with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            user = json.load(f)
            user['GLOBAL_THRESHOLD'] = int(user.get('GLOBAL_THRESHOLD', 2000))
            user['CHUNK_SIZE'] = int(user.get('CHUNK_SIZE', 300))
            user['MAX_WORKERS'] = int(user.get('MAX_WORKERS', 8))
            user['API_TIMEOUT'] = int(user.get('API_TIMEOUT', 120))
            return {**DEFAULT_USER_SETTINGS, **user}
    except Exception:
        return DEFAULT_USER_SETTINGS.copy()

def save_user_settings(settings):
    with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)

_settings = load_user_settings()
PRESET_EMOTIONAL = _settings.get("PRESET_EMOTIONAL", "emotional_default")
PRESET_CIVIL = _settings.get("PRESET_CIVIL", "civil_default")
PRESET_MIME = _settings.get("PRESET_MIME", "mime_default")
GLOBAL_THRESHOLD = _settings["GLOBAL_THRESHOLD"]
CHUNK_SIZE = _settings["CHUNK_SIZE"]
MAX_WORKERS = _settings["MAX_WORKERS"]
COMFYUI_API_URL = _settings["COMFYUI_API_URL"]
VIDEO_OUTPUT_BASE_DIR = _settings["VIDEO_OUTPUT_BASE_DIR"]
OUTPUT_ROOT_DIR = _settings["OUTPUT_ROOT_DIR"]
API_TIMEOUT = _settings["API_TIMEOUT"]
MAX_RETRIES = _settings.get("MAX_RETRIES", 3)          # 默认3次
RETRY_DELAY = _settings.get("RETRY_DELAY", 5)          # 默认5秒
FUZZY_MATCH_THRESHOLD = _settings.get("FUZZY_MATCH_THRESHOLD", 80)

def load_style_presets():
    """从 user_settings.json 加载风格预设字典"""
    settings = load_user_settings()
    return settings.get("STYLE_PRESETS", {})

def save_style_preset(name, content):
    """保存一个风格预设到 user_settings.json"""
    settings = load_user_settings()
    if "STYLE_PRESETS" not in settings:
        settings["STYLE_PRESETS"] = {}
    settings["STYLE_PRESETS"][name] = content
    save_user_settings(settings)