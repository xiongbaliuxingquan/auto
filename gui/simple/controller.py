# gui/simple/controller.py
import threading
import os
import re
import tkinter as tk
from tkinter import messagebox
import json
import subprocess
import sys
import glob
from datetime import datetime
from utils import config_manager

class SimpleModeController:
    def __init__(self, ui, data, app):
        self.ui = ui
        self.data = data
        self.app = app

    def open_wizard(self):
        from gui.story_wizard import StoryWizard
        def on_finish(script, metadata):
            # 创建项目目录
            title = self.ui.title_entry.get().strip() or "未命名故事"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = f"{title}_{timestamp}"
            base_dir = config_manager.OUTPUT_ROOT_DIR
            work_dir = os.path.join(base_dir, folder_name)
            os.makedirs(work_dir, exist_ok=True)
            self.ui.work_dir = work_dir

            # 保存故事文本
            story_path = os.path.join(work_dir, "story.txt")
            with open(story_path, 'w', encoding='utf-8') as f:
                f.write(script)

            # 保存元数据
            metadata_path = os.path.join(work_dir, "metadata.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)

            # 将故事文本放入故事标签页
            self.ui.story_tab.text_widget.delete('1.0', 'end')
            self.ui.story_tab.text_widget.insert('1.0', script)
            self.ui.story_tab.update_word_count()
            self.data.story_text = script
            self.data.metadata = metadata
            self.app.log(f"项目已保存至: {work_dir}")
        StoryWizard(self.app.root, self.app, on_finish)

    def _run_auto_split(self, work_dir):
        # 从当前文件向上三级到项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = os.path.join(project_root, "core", "auto_split_simple.py")

        # 检查脚本是否存在
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"未找到脚本文件: {script_path}")

        # 检查必需文件是否存在
        global_assets = os.path.join(work_dir, "assets_global.txt")
        if not os.path.exists(global_assets):
            raise FileNotFoundError("缺少全局资产文件，请先生成剧本")
        para_assets = glob.glob(os.path.join(work_dir, "assets_paragraph_*.txt"))
        if not para_assets:
            raise FileNotFoundError("缺少段落资产文件，请先生成剧本")
        
        cmd = [sys.executable, script_path, work_dir]
        self.app.log("正在生成视频提示词，请稍候...")
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,      # 捕获错误输出
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            # 实时输出 stdout
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.app.log(line)
            # 等待进程结束
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                self.app.log(f"脚本执行失败，返回码 {process.returncode}")
                if stderr:
                    self.app.log(f"错误详情:\n{stderr}")
                raise Exception(f"脚本执行失败，返回码 {process.returncode}")
        except Exception as e:
            self.app.log(f"生成提示词失败: {e}")
            raise

        # 查找最新生成的易读版分镜文件
        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        if not files:
            raise FileNotFoundError("未找到生成的易读版分镜文件")
        latest = max(files, key=os.path.getmtime)
        return latest

    def _parse_prompts_from_readable(self, readable_path):
        """从易读版分镜文件中提取每个镜头的提示词，返回列表"""
        with open(readable_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # 按等号线分割成镜头块
        blocks = re.split(r'\n\s*={5,}\s*\n', content.strip())
        prompts = []
        for block in blocks:
            if not block.strip():
                continue
            # 查找“- 提示词：”的位置
            idx = block.find('- 提示词：')
            if idx != -1:
                # 从该行之后开始提取
                after_prompt = block[idx + len('- 提示词：'):].lstrip()
                # 提示词是最后一个字段，后面没有其他“- ”行，直接取到块结束
                # 但可能有多余空行，去除首尾空白
                prompt_text = after_prompt.strip()
                prompts.append(prompt_text)
            else:
                prompts.append("[未找到提示词]")
        return prompts
    def on_story_changed(self, content):
        self.data.story_text = content

    def on_style_changed(self, content):
        self.data.style_preset = content

    def on_assets_changed(self, key, value):
        self.data.assets[key] = value

    def generate_script(self):
        """步骤1：生成剧本"""
        if not self.data.story_text.strip():
            messagebox.showwarning("提示", "请先输入故事内容")
            return

        if not self.ui.work_dir:
            messagebox.showerror("错误", "请先通过高级向导创建项目，或打开历史项目")
            return

        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="生成中...")
        self.app.log("正在生成剧本，请稍候...")

        def task():
            try:
                from parsers.free_parser import FreeParser
                from utils.ai_utils import call_deepseek

                parser = FreeParser(call_deepseek, story_title=self.app.toolbar.title_entry.get(), mode="自由模式")
                result = parser.parse(self.data.story_text, metadata=self.data.metadata, work_dir=self.ui.work_dir,
                                    log_callback=self.app.log, verbose=True)   # 测试时开启
                scenes = result.get("scenes", [])
                self.data.script_data = scenes

                # 保存 shots.txt
                self._write_shots_to_file(self.ui.work_dir, scenes)

                # 更新 UI
                self.app.root.after(0, self._on_script_generated, scenes)
            except Exception as e:
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"生成剧本失败：{e}"))
                self.app.root.after(0, self._reset_buttons)

        threading.Thread(target=task, daemon=True).start()

    def _write_shots_to_file(self, work_dir, scenes):
        shots_path = os.path.join(work_dir, "shots.txt")
        with open(shots_path, 'w', encoding='utf-8') as f:
            for scene in scenes:
                for idx, shot in enumerate(scene['shots'], start=1):
                    shot_id = f"{scene['id']}-{idx}"
                    # 镜头标题：优先使用 shot 中的 title，否则使用场次标题
                    title = shot.get('title', scene['title'])
                    f.write(f"【镜头{shot_id}：{title}】\n")
                    # 严格按顺序输出
                    f.write(f"- 场景：{shot.get('scene', '')}\n")
                    f.write(f"- 角色：{', '.join(shot.get('roles', []))}\n")
                    f.write(f"- 动作：{shot.get('action', '')}\n")
                    f.write(f"- 对白：{shot.get('dialogue', '')}\n")
                    f.write(f"- 视觉描述：{shot.get('visual', '')}\n")
                    f.write(f"- 时长：{shot['duration']:.1f}秒\n")
                    f.write(f"- 情绪基调：{shot['emotion']}\n")
                    f.write(f"- 地域：{shot['region']}\n")
                    f.write("===========================\n")
        self.app.log(f"剧本已保存至 {shots_path}")

    def _on_script_generated(self, scenes):
        """剧本生成完成后的UI更新"""
        self.ui.script_tab.display_scenes(scenes)
        self.ui.set_button_state('normal', 'normal', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="1. 生成剧本")
        self.app.log("剧本生成完成")
        # 刷新资产库面板
        if hasattr(self.ui, 'assets_tab'):
            self.ui.assets_tab.work_dir = self.ui.work_dir
            self.ui.assets_tab.refresh_file_list()
        # 切换到剧本标签页
        self.ui.notebook.select(self.ui.script_tab.frame)

    def _format_scenes_to_text(self, scenes):
        """将 scenes 数据格式化为可读文本"""
        lines = []
        for scene in scenes:
            lines.append(f"【场次{scene['id']}：{scene['title']}】")
            for idx, shot in enumerate(scene['shots'], start=1):
                lines.append(f"  镜头{idx}")
                lines.append(f"    - 场景：{shot.get('scene', '')}")
                lines.append(f"    - 角色：{', '.join(shot.get('roles', []))}")
                lines.append(f"    - 动作：{shot.get('action', '')}")
                lines.append(f"    - 对白：{shot.get('dialogue', '')}")
                lines.append(f"    - 视觉描述：{shot.get('visual', '')}")
                lines.append(f"    - 时长：{shot.get('duration', 10)}秒")
                lines.append(f"    - 情绪：{shot.get('emotion', '')}")
                lines.append(f"    - 地域：{shot.get('region', '')}")
                lines.append("")
            lines.append("")
        return "\n".join(lines)

    def _extract_assets_from_script(self, script_data):
        """从剧本数据中提取人物、场景、风格"""
        persona = set()
        scene_desc = set()
        # 遍历所有镜头，收集角色和场景
        for scene in script_data['scenes']:
            for shot in scene['shots']:
                # 角色
                for role in shot.get('roles', []):
                    if role.strip():
                        persona.add(role)
                # 场景描述（取第一个镜头的场景作为参考，可聚合）
                if shot.get('scene'):
                    scene_desc.add(shot['scene'])
        # 格式化
        persona_text = "\n".join([f"- {r}" for r in persona]) if persona else "无"
        scene_text = "\n".join([f"- {s}" for s in scene_desc]) if scene_desc else "无"
        style = self.data.style_preset or "电影感、写实、自然光影"
        return {
            'persona': persona_text,
            'scene': scene_text,
            'style': style
        }

    def generate_prompts(self):
        """步骤3：生成提示词"""
        if not self.data.assets:
            messagebox.showwarning("提示", "请先提取资产")
            return

        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return

        # 检查必需文件
        global_assets = os.path.join(work_dir, "assets_global.txt")
        if not os.path.exists(global_assets):
            messagebox.showerror("错误", "缺少全局资产文件，请先生成剧本")
            return
        para_assets = glob.glob(os.path.join(work_dir, "assets_paragraph_*.txt"))
        if not para_assets:
            messagebox.showerror("错误", "缺少段落资产文件，请先生成剧本")
            return

        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.ui.gen_prompts_btn.config(text="生成中...")
        self.app.log("正在生成视频提示词...")

        def task():
            try:
                readable_path = self._run_auto_split(work_dir)
                self.app.log(f"生成易读版文件: {readable_path}")
                prompts = self._parse_prompts_from_readable(readable_path)
                self.app.log(f"成功解析 {len(prompts)} 条提示词")
                self.data.prompts = prompts
                # 在主线程中更新 UI
                self.app.root.after(0, lambda: self.ui.prompts_tab.display_prompts(prompts))
                self.app.root.after(0, self._on_prompts_generated)
            except Exception as e:
                self.app.log(f"生成提示词失败: {e}")
                import traceback
                traceback.print_exc()
                self.app.root.after(0, self._reset_buttons)

        threading.Thread(target=task, daemon=True).start()

        def task():
            try:
                readable_path = self._run_auto_split(work_dir)
                prompts = self._parse_prompts_from_readable(readable_path)
                # 保存提示词列表到数据模型
                self.data.prompts = prompts
                # 在提示词标签页显示
                self.app.root.after(0, lambda: self.ui.prompts_tab.display_prompts(prompts))
                self.app.root.after(0, self._on_prompts_generated)
            except Exception as e:
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"生成提示词失败：{e}"))
                self.app.root.after(0, self._reset_buttons)

        threading.Thread(target=task, daemon=True).start()

    def _on_prompts_generated(self):
        self.ui.set_button_state('normal', 'normal', 'normal', 'disabled')
        self.ui.gen_prompts_btn.config(text="2. 生成提示词")
        self.app.log("提示词生成完成")
        self.ui.notebook.select(self.ui.prompts_tab.frame)

    def confirm_and_generate(self):
        """生成视频"""
        # 复用原来的逻辑，但按钮改为“生成视频”
        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return
        # 查找最新易读版文件
        import glob
        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        if not files:
            messagebox.showerror("错误", "未找到易读版分镜文件，请先生成提示词")
            return
        readable_file = max(files, key=os.path.getmtime)
        from core.comfyui_manager import ComfyUIManager
        temp_manager = ComfyUIManager("", "")
        shots_info = temp_manager.get_shots_info(readable_file)
        if not shots_info:
            messagebox.showerror("错误", "解析镜头信息失败")
            return
        self.app.shots_info = shots_info
        self.app.work_dir = work_dir
        title = os.path.basename(work_dir).split('_')[0]
        self.app.story_title = title
        self.app.selected_shots_ids = None
        self.app.edited_prompts = {}
        # 运行视频生成
        self.app.run_workflow()
        # 生成完成后刷新视频标签页（通过回调，需要 app 在完成时调用 self.ui.video_tab.refresh_video_list）
        # 此处先注册回调（假设 app 有方法可以注册）
        # 简单起见，我们可以在视频生成线程中手动调用，或者定时刷新，但用户可手动点击刷新按钮

    def merge_videos(self):
        """合并视频（占位）"""
        messagebox.showinfo("提示", "合并视频功能待实现")

    def _reset_buttons(self):
        """重置按钮状态"""
        self.ui.set_button_state('normal', 'disabled', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="1. 生成剧本")
        self.ui.gen_prompts_btn.config(text="2. 生成提示词")
        self.ui.gen_video_btn.config(text="3. 生成视频")

    def open_style_preset(self):
        from gui.preset_manager import PresetManagerWindow
        current_mode = self.app.toolbar.text_type_var.get()
        win = PresetManagerWindow(self.app.root, current_mode)
        self.app.root.wait_window(win.win)
        if hasattr(win, 'result') and win.result:
            self.app._update_preset_label()

    def generate_style(self, story, style_text_widget):
        if not story:
            messagebox.showwarning("提示", "请先输入故事内容")
            return
        try:
            from utils.style_generator import generate_style_from_story
            style = generate_style_from_story(story)
            style_text_widget.delete('1.0', 'end')
            style_text_widget.insert('1.0', style)
            # 触发字数更新（需要 style_text_widget 有 update_word_count 方法）
            if hasattr(style_text_widget, 'update_word_count'):
                style_text_widget.update_word_count()
        except Exception as e:
            messagebox.showerror("错误", f"生成风格失败：{e}")

    def save_style_preset(self, style):
        if not style:
            messagebox.showwarning("提示", "风格人设卡为空，无需保存")
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("保存预设", "请输入预设名称：", parent=self.app.root)
        if not name:
            return
        try:
            from utils.config_manager import save_style_preset as save_preset
            save_preset(name, style)
            messagebox.showinfo("成功", f"预设“{name}”已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")