# core/comfyui_manager_simple.py
"""
一键成片专用视频生成器，封装 ComfyUIManager 并启用自动裁剪。
"""

from .comfyui_manager import ComfyUIManager

class SimpleVideoGenerator:
    def __init__(self, api_url, output_base_dir, fps=24, max_duration=20, on_shot_generated=None):
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
        self.manager.set_log_callback(callback)

    def get_shots_info(self, readable_file):
        return self.manager.get_shots_info(readable_file)

    def run(self, story_title, work_dir, resolution, template_path, selected_shots=None, edits=None):
        return self.manager.run(story_title, work_dir, resolution, template_path, selected_shots, edits)