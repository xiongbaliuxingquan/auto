"""
================================================================================
【重要修改提示】
本文件涉及与外部系统的关键交互，任何修改前请务必：
1. 核对当前使用的模板及节点ID（见 workflow_config.json）。
2. 在小范围（如单个镜头）测试验证，确认无误后再批量运行。
3. 若修改涉及节点ID或 API 参数，请先与用户确认实际值，切勿凭经验猜测。
================================================================================
"""
# step_manager.py
import os
import sys
from utils import process_runner

class StepManager:
    """管理子脚本的串行执行，并更新进度"""

    def __init__(self, runner, log_callback, progress_callback, processing_failed_callback, mode):
        self.runner = runner
        self.log = log_callback
        self.set_progress = progress_callback
        self.processing_failed = processing_failed_callback
        self.mode = mode

    def run_steps(self, work_dir, story_title, input_filename):
        print(f"[DEBUG] StepManager.mode = {self.mode}")
        project_root = os.path.dirname(os.path.dirname(__file__))  # 项目根目录

        # 基础步骤列表
        base_steps = [
            (os.path.join(project_root, "core", "txt_to_json.py"), "1/3: 转换文稿为JSON", [os.path.join(work_dir, input_filename), story_title, self.mode, work_dir]),
            (os.path.join(project_root, "core", "auto_split_deepseek.py"), "2/3: 生成分镜设计", [work_dir]),
            (os.path.join(project_root, "core", "extract_prompts.py"), "3/3: 提取提示词并翻译", [work_dir])
        ]

        # 检查是否有字幕文件，如果有，则在第一步后插入字幕优化步骤
        srt_path = os.path.join(work_dir, "input.srt")
        has_subtitle = os.path.exists(srt_path)

        # 动态构建步骤列表
        steps = []
        for step in base_steps:
            steps.append(step)
            if step[1] == "1/3: 转换文稿为JSON" and has_subtitle:
                # 在第一步之后插入字幕优化
                steps.insert(len(steps), (os.path.join(project_root, "core", "refine_shots_by_srt.py"), "字幕优化: 根据字幕调整镜头", [work_dir]))

        total_steps = len(steps)
        for idx, (script_path, desc, args) in enumerate(steps, start=1):
            self.log(f"\n========== {desc} ==========")
            self.log(f"正在执行 {os.path.basename(script_path)} ...")
            cmd = [sys.executable, script_path] + args
            rc, success = self.runner.run(cmd, cwd=project_root)
            if not success:
                self.log(f"错误：{os.path.basename(script_path)} 执行失败")
                self.processing_failed()
                return False
            self.log(f"{os.path.basename(script_path)} 执行完成。")

            # 检查第一步生成的必需文件
            if desc == "1/3: 转换文稿为JSON":
                header_path = os.path.join(work_dir, "header.txt")
                shots_path = os.path.join(work_dir, "shots.txt")
                if not os.path.exists(header_path) or not os.path.exists(shots_path):
                    self.log("错误：第一步未生成 header.txt 或 shots.txt")
                    self.processing_failed()
                    return False

            progress = idx / total_steps * 100
            self.set_progress(progress)

        return True