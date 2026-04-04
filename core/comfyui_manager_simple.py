# core/comfyui_manager_simple.py
"""
一键成片专用视频生成器，封装 ComfyUIManager 并启用自动裁剪。
"""

from .comfyui_manager import ComfyUIManager

class SimpleVideoGenerator:
    def __init__(self, api_url, output_base_dir, fps=24, max_duration=20, on_shot_generated=None):
        """
        初始化视频生成器，自动启用 auto_trim=True。
        """
        self.manager = ComfyUIManager(
            api_url=api_url,
            output_base_dir=output_base_dir,
            fps=fps,
            max_duration=max_duration,
            on_shot_generated=on_shot_generated,
            auto_trim=True
        )
        self.log_callback = None

    def set_log_callback(self, callback):
        """设置日志回调"""
        self.manager.set_log_callback(callback)

    def run(self, story_title, work_dir, resolution, template_path, selected_shots=None, edits=None):
        """
        生成视频，参数与 ComfyUIManager.run 相同。
        """
        return self.manager.run(story_title, work_dir, resolution, template_path, selected_shots, edits)