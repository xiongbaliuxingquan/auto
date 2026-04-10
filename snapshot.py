import os
import fnmatch

# 配置
output_file = "project_snapshot.txt"
exclude_dirs = {'.git', '__pycache__', 'venv', 'venv311', 'env', 'node_modules', 'output', 'logs', 'tools', '.git', '.vscode'}  # 添加了要排除的文件夹
include_extensions = ['*.py', '*.json', '*.md', '*.txt', '*.yaml', '*.ini', '*.cfg']  # 需要包含的文件类型

def should_include(filepath):
    """检查文件是否应该被包含"""
    # 排除隐藏文件（以.开头）
    if os.path.basename(filepath).startswith('.'):
        return False
    # 检查扩展名
    for pattern in include_extensions:
        if fnmatch.fnmatch(filepath, pattern):
            return True
    return False

def walk_and_collect(root_dir):
    """遍历目录，收集符合条件的文件"""
    collected = []
    for root, dirs, files in os.walk(root_dir):
        # 排除指定目录
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, root_dir)
            if should_include(rel_path):
                collected.append((rel_path, full_path))
    return collected

def generate_snapshot(root_dir, output_file):
    files = walk_and_collect(root_dir)
    with open(output_file, 'w', encoding='utf-8') as out:
        out.write(f"# Project Snapshot\n")
        out.write(f"Generated: {__import__('datetime').datetime.now()}\n\n")
        out.write(f"## Project Structure\n")
        for rel_path, _ in files:
            out.write(f"- {rel_path}\n")
        out.write("\n## File Contents\n\n")
        for rel_path, full_path in files:
            out.write(f"### {rel_path}\n")
            out.write("```")
            ext = os.path.splitext(rel_path)[1]
            if ext in ['.py', '.json', '.yaml', '.ini', '.cfg']:
                out.write(ext[1:])  # 添加语言标识，如 python, json
            out.write("\n")
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    out.write(f.read())
            except Exception as e:
                out.write(f"[Error reading file: {e}]")
            out.write("\n```\n\n")

if __name__ == "__main__":
    root = os.getcwd()  # 当前目录
    generate_snapshot(root, output_file)
    print(f"项目快照已生成：{output_file}")