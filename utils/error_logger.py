import os
import sys
from datetime import datetime

ERROR_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "error_log.txt")

def log_error(module_name, error_msg, details=None):
    """
    统一错误记录函数
    :param module_name: 发生错误的模块名（如 'txt_to_json'）
    :param error_msg: 错误简要描述
    :param details: 可选，详细错误信息（如异常堆栈）
    """
    os.makedirs(os.path.dirname(ERROR_LOG_FILE), exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {module_name}: {error_msg}\n")
        if details:
            f.write(f"详情: {details}\n")
        f.write("-" * 60 + "\n")
    # 同时打印到控制台，方便实时查看
    print(f"[ERROR] {module_name}: {error_msg}")