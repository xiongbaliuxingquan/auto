import os
import re
import sys
from datetime import datetime
from collections import defaultdict

# 错误日志路径（统一由 error_logger 写入）
ERROR_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "logs", "error_log.txt")

# 常见错误类型及其解决方案
KNOWN_ERRORS = {
    "Timeout": {
        "pattern": r"超时|timeout",
        "solution": "增加 API 超时时间（修改 user_settings.json 中的 API_TIMEOUT）或检查网络/服务器负载。"
    },
    "JSONDecodeError": {
        "pattern": r"JSON.*?decode|json\.loads.*?failed",
        "solution": "AI 返回的格式不符合预期，请检查对应模块的 prompt 或解析正则表达式。"
    },
    "NameError": {
        "pattern": r"name '.*?' is not defined",
        "solution": "代码中存在未定义的变量，请检查变量名拼写或作用域。"
    },
    "KeyError": {
        "pattern": r"KeyError: '.*?'",
        "solution": "字典中缺少预期的键，请检查数据结构或配置项（如 workflow_config.json）。"
    },
    "FileNotFound": {
        "pattern": r"FileNotFoundError|No such file",
        "solution": "工作目录中缺少必需文件（如 shots.txt、input.srt），请检查文件是否存在。"
    },
    "PermissionError": {
        "pattern": r"Permission denied",
        "solution": "文件或目录权限不足，尝试以管理员身份运行或修改文件夹权限。"
    },
    "ConnectionError": {
        "pattern": r"ConnectionError|Failed to connect",
        "solution": "网络连接失败，检查 ComfyUI 服务是否运行或 API URL 是否正确。"
    },
    "APILimit": {
        "pattern": r"429|rate limit",
        "solution": "API 调用达到速率限制，请降低并发数或稍后再试。"
    }
}

def read_error_log(max_lines=200):
    """读取错误日志文件，返回最近 max_lines 行"""
    if not os.path.exists(ERROR_LOG_PATH):
        return []
    with open(ERROR_LOG_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # 只保留最近 max_lines 行（避免日志过大）
    return lines[-max_lines:]

def parse_errors(lines):
    """
    解析错误日志行，返回按模块分组的错误列表。
    每条错误格式示例：
    [2026-03-17 22:14:33] txt_to_json: API 请求超时
    详情: 耗时: 60.5s
    ------------------------------------------------------------
    """
    errors_by_module = defaultdict(list)
    current_error = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 新错误开始（时间戳开头）
        if re.match(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]', line):
            if current_error:
                # 保存上一条错误
                module = current_error.get('module', 'unknown')
                errors_by_module[module].append(current_error)
            # 解析当前行
            match = re.match(r'\[(.*?)\] (.*?): (.*)', line)
            if match:
                timestamp, module, msg = match.groups()
                current_error = {
                    'timestamp': timestamp,
                    'module': module,
                    'message': msg,
                    'details': []
                }
            else:
                current_error = {}
        elif line.startswith('详情:'):
            if current_error:
                current_error['details'].append(line[4:].strip())
        elif line.startswith('-' * 60):
            if current_error:
                # 结束符，保存并清空
                module = current_error.get('module', 'unknown')
                errors_by_module[module].append(current_error)
                current_error = {}
        else:
            # 普通行（可能是多行详情）
            if current_error and 'details' in current_error:
                current_error['details'].append(line)
    # 最后一条
    if current_error:
        module = current_error.get('module', 'unknown')
        errors_by_module[module].append(current_error)
    return errors_by_module

def suggest_fix(error_msg, details=""):
    """根据错误消息匹配已知错误类型，返回解决方案"""
    for err_type, info in KNOWN_ERRORS.items():
        if re.search(info['pattern'], error_msg, re.IGNORECASE):
            return f"[{err_type}] {info['solution']}"
    return "未知错误类型，建议查看日志上下文或联系开发者。"

def print_report(errors_by_module):
    """打印诊断报告"""
    print("\n" + "="*60)
    print("【系统医生诊断报告】")
    print("="*60)
    if not errors_by_module:
        print("🎉 错误日志为空，系统运行正常！")
        return

    for module, err_list in errors_by_module.items():
        print(f"\n📁 模块: {module}")
        print("-" * 40)
        for err in err_list[-3:]:  # 每个模块最多显示最近3条
            print(f"  🕒 {err['timestamp']}")
            print(f"  ❌ {err['message']}")
            if err['details']:
                print(f"  📌 详情: {err['details'][0][:200]}")
            fix = suggest_fix(err['message'], ' '.join(err['details']))
            print(f"  💡 建议: {fix}")
            print()

def main():
    print("=== 系统医生启动 ===")
    print(f"正在读取错误日志: {ERROR_LOG_PATH}")
    lines = read_error_log()
    if not lines:
        print("错误日志为空，请先运行一次流程以产生错误记录。")
        return

    errors = parse_errors(lines)
    print_report(errors)

    print("\n提示：如果问题仍未解决，请将错误日志内容复制给我，我们可以一起深入分析。")

if __name__ == "__main__":
    main()