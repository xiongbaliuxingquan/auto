# workflow_executor.py
import os
import sys
import threading
from utils import process_runner
from core import comfyui_manager

class WorkflowExecutor:
    """执行工作流（调用 comfyui_submit.py）"""

    def __init__(self, root, runner, log_callback, done_callback, failed_callback):
        self.root = root
        self.runner = runner
        self.log = log_callback
        self.done_callback = done_callback
        self.failed_callback = failed_callback

    def run(self, story_title, work_dir):
        """在新线程中启动工作流"""
        self.log("\n========== 4/4: 生成视频 ==========")
        script_path = os.path.join(os.path.dirname(__file__), "comfyui_submit.py")
        cmd = [sys.executable, script_path, story_title, work_dir]
        thread = threading.Thread(target=self._run_thread, args=(cmd,))
        thread.daemon = True
        thread.start()

    def _run_thread(self, cmd):
        rc, success = self.runner.run(cmd)
        if success:
            self.root.after(0, self.done_callback)
        else:
            self.root.after(0, self.failed_callback)