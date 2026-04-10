import os
import fnmatch
from datetime import datetime

# ===================== 配置 =====================
OUTPUT_FILE = "精简快照.txt"

# 排除所有臃肿目录（日志、缓存、临时文件、输出）
EXCLUDE_DIRS = {
    '__pycache__', '.git', 'venv', '.vscode', 'logs', 'temp', 'tmp',
    'cache', 'outputs', 'audios_temp', 'videos_temp', 'srt_temp'
}

# 仅保留核心文件类型
INCLUDE_EXTS = ['*.py', '*.json', '*.txt', '*.md']
EXCLUDE_FILES = ['*.log', '*.tmp']
# =================================================

def is_included(file_path):
    """过滤无效文件"""
    name = os.path.basename(file_path)
    if name.startswith('.'):
        return False
    if any(fnmatch.fnmatch(name, p) for p in EXCLUDE_FILES):
        return False
    return any(fnmatch.fnmatch(name, p) for p in INCLUDE_EXTS)

def get_file_summary(full_path):
    """🔥 核心：只提取文件摘要，不读全文！"""
    rel = os.path.basename(full_path)
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            # 只读前30行，提取核心，超长直接截断
            lines = f.readlines()[:30]
            content = ''.join([l.strip() for l in lines if l.strip() and not l.strip().startswith('#')])
            # 只保留关键代码，不保留冗余
            if len(content) > 500:
                content = content[:500] + "..."
        return f"核心摘要：{content}"
    except:
        return "核心摘要：二进制/无法读取"

def generate_snapshot(root_dir):
    """生成极简快照（只留结构+摘要，无全文）"""
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"# 分镜生成助手 - 极简快照\n生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write("="*40 + "项目结构" + "="*40 + "\n")

        # 遍历文件，只写结构+摘要
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), root_dir)
                if is_included(file):
                    # 只写文件路径 + 极简摘要，不写全文！
                    f.write(f"📄 {rel_path}\n  {get_file_summary(os.path.join(root, file))}\n\n")

if __name__ == "__main__":
    generate_snapshot(os.getcwd())
    print(f"✅ 极简快照生成完成：{OUTPUT_FILE}")
    print(f"🔥 已彻底精简：无全文复制、无冗余内容、体积极小")