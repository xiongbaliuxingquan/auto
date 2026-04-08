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
from core.comfyui_manager_simple import SimpleVideoGenerator
from core.i2v.cfy_i2v import generate_single_video
from core.i2v.generate_asset_image import generate_all_assets
from core.i2v.generate_asset_image import generate_asset_image_with_prompt, parse_global_assets, parse_paragraph1_assets

class SimpleModeController:
    def __init__(self, ui, data, app):
        self.ui = ui
        self.data = data
        self.app = app

    def to_1080p(self, resolution: str):
        """将用户选择的分辨率按比例转换为1080P（最小边1080）"""
        try:
            w, h = map(int, resolution.split('x'))
            if w / h > 1.7:  # 16:9 或更宽
                return 1920, 1080
            elif h / w > 1.7:  # 9:16 或更高
                return 1080, 1920
            else:
                return w, h
        except:
            return None, None

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

    def generate_asset_images(self):
        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return

        shots_path = os.path.join(work_dir, "shots.txt")
        if not os.path.exists(shots_path):
            messagebox.showerror("错误", "未找到剧本文件，请先生成剧本")
            return

        # 获取分辨率
        resolution = self.app.resolution_var.get()
        width, height = self.to_1080p(resolution)

        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.ui.gen_asset_img_btn.config(text="生成中...")
        self.app.log("开始生成角色资产图（定妆照），请稍候...")

        def task():
            try:
                generated = generate_all_assets(work_dir, log_callback=self.app.log, width=width, height=height)
                if generated:
                    self.app.log(f"资产图生成完成，共 {len(generated)} 张")
                    if hasattr(self.ui, 'storyboard_tab') and self.ui.storyboard_tab:
                        self.ui.storyboard_tab.refresh()
                else:
                    self.app.log("资产图生成失败，请检查日志")
            except Exception as e:
                self.app.log(f"资产图生成异常: {e}")
            finally:
                self.app.root.after(0, self._reset_asset_buttons)

        threading.Thread(target=task, daemon=True).start()

    def _reset_asset_buttons(self):
        self.ui.set_button_state('normal', 'normal', 'normal', 'disabled')
        self.ui.gen_asset_img_btn.config(text="2. 生成资产图")

    def generate_storyboard(self):
        """生成所有镜头的首帧图（如果提示词文件不存在则自动生成）"""
        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return
        # 获取分辨率
        resolution = self.app.resolution_var.get()
        width, height = self.to_1080p(resolution)

        prompts_path = os.path.join(work_dir, "first_frame_prompts.json")
        
        # 禁用按钮
        self._disable_buttons()
        
        def task():
            # 如果提示词文件不存在，先调用生成脚本
            if not os.path.exists(prompts_path):
                self.app.log("未找到首帧图提示词，正在生成...")
                script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                        "core", "i2v", "generate_first_frame_prompt.py")
                try:
                    result = subprocess.run([sys.executable, script_path, work_dir], 
                                            capture_output=True, text=True, timeout=300)
                    if result.returncode != 0:
                        error_msg = result.stderr or "未知错误"
                        self.app.root.after(0, lambda: self.app.log(f"生成首帧图提示词失败: {error_msg}"))
                        self.app.root.after(0, messagebox.showerror, "错误", f"生成首帧图提示词失败\n{error_msg}")
                        self.app.root.after(0, self._enable_buttons)
                        return
                    self.app.root.after(0, lambda: self.app.log("首帧图提示词生成完成"))
                except subprocess.TimeoutExpired:
                    self.app.root.after(0, lambda: self.app.log("生成首帧图提示词超时"))
                    self.app.root.after(0, messagebox.showerror, "错误", "生成首帧图提示词超时")
                    self.app.root.after(0, self._enable_buttons)
                    return
                except Exception as e:
                    self.app.root.after(0, lambda: self.app.log(f"生成首帧图提示词异常: {e}"))
                    self.app.root.after(0, messagebox.showerror, "错误", f"生成首帧图提示词异常: {e}")
                    self.app.root.after(0, self._enable_buttons)
                    return

            # 生成首帧图图片
            from core.i2v.generate_first_frame_image import generate_all_first_frames
            self.app.root.after(0, lambda: self.app.log("开始生成首帧图，请稍候..."))
            try:
                generate_all_first_frames(work_dir, log_callback=self.app.log, width=width, height=height)
                self.app.root.after(0, self._on_storyboard_done)
            except Exception as e:
                self.app.root.after(0, lambda: self.app.log(f"生成首帧图失败: {e}"))
                self.app.root.after(0, self._enable_buttons)
        
        threading.Thread(target=task, daemon=True).start()

    def _disable_buttons(self):
        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.ui.gen_storyboard_btn.config(text="生成中...")

    def _enable_buttons(self):
        self.ui.set_button_state('normal', 'normal', 'normal', 'disabled')
        self.ui.gen_storyboard_btn.config(text="3. 生成分镜图")

    def regenerate_asset_with_prompt(self, custom_prompt):
        work_dir = self.ui.work_dir
        if not work_dir:
            self.app.log("工作目录未设置")
            return
        # 获取角色信息
        style, characters = parse_global_assets(work_dir)
        if not characters:
            self.app.log("未找到角色信息")
            return
        # 取第一个角色（简化，实际可让用户选择）
        char_name, char_desc = list(characters.items())[0]
        scene = parse_paragraph1_assets(work_dir)
        self.app.log("正在重新生成定妆照...")
        def task():
            try:
                result = generate_asset_image_with_prompt(work_dir, char_name, char_desc, scene, style, custom_prompt)
                if result:
                    self.app.log("定妆照更新成功")
                    self.app.root.after(0, lambda: self.ui.storyboard_tab.refresh())
                else:
                    self.app.log("定妆照更新失败")
            except Exception as e:
                self.app.log(f"更新定妆照失败: {e}")
        threading.Thread(target=task, daemon=True).start()

    def _on_storyboard_done(self):
        self.app.log("首帧图生成完成")
        if hasattr(self.ui, 'storyboard_tab') and self.ui.storyboard_tab:
            self.ui.storyboard_tab.refresh()
        self._enable_buttons()

    def regenerate_single_frame(self, shot_id):
        """重新生成单个镜头的首帧图"""
        work_dir = self.ui.work_dir
        if not work_dir:
            return
        # 从 first_frame_prompts.json 读取该镜头的提示词
        prompts_path = os.path.join(work_dir, "first_frame_prompts.json")
        import json
        with open(prompts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        prompt = None
        for item in data:
            if item['shot_id'] == shot_id:
                prompt = item['prompt']
                break
        if not prompt:
            self.app.log(f"未找到镜头 {shot_id} 的提示词")
            return
        # 调用单个生成函数
        from core.i2v.generate_first_frame_image import generate_single_frame
        self.app.log(f"正在重新生成镜头 {shot_id}...")
        def task():
            try:
                generate_single_frame(work_dir, shot_id, prompt, log_callback=self.app.log)
                self.app.root.after(0, lambda: self.ui.storyboard_tab.refresh())
            except Exception as e:
                self.app.root.after(0, lambda: self.app.log(f"重绘失败: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def regenerate_asset(self):
        """重新生成定妆照"""
        work_dir = self.ui.work_dir
        if not work_dir:
            return
        from core.i2v.generate_asset_image import generate_all_assets
        self.app.log("正在重新生成定妆照...")
        def task():
            try:
                generate_all_assets(work_dir, log_callback=self.app.log)
                self.app.root.after(0, lambda: self.ui.storyboard_tab.refresh())
            except Exception as e:
                self.app.root.after(0, lambda: self.app.log(f"生成定妆照失败: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def _run_auto_split(self, work_dir):
        # 从当前文件向上三级到项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        script_path = os.path.join(project_root, "core", "auto_split_simple.py")

        if not os.path.exists(script_path):
            raise FileNotFoundError(f"未找到脚本文件: {script_path}")

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
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.app.log(line)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                self.app.log(f"脚本执行失败，返回码 {process.returncode}")
                if stderr:
                    self.app.log(f"错误详情:\n{stderr}")
                raise Exception(f"脚本执行失败，返回码 {process.returncode}")
        except Exception as e:
            self.app.log(f"生成提示词失败: {e}")
            raise

        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        if not files:
            raise FileNotFoundError("未找到生成的易读版分镜文件")
        latest = max(files, key=os.path.getmtime)
        return latest

    def _parse_prompts_from_readable(self, readable_path):
        with open(readable_path, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = re.split(r'\n\s*={5,}\s*\n', content.strip())
        prompts = []  # 每个元素为 (shot_id, prompt)
        for block in blocks:
            if not block.strip():
                continue
            # 提取镜头ID
            header_match = re.search(r'【镜头(\d+-\d+)：', block)
            shot_id = header_match.group(1) if header_match else "未知"
            idx = block.find('- 提示词：')
            if idx != -1:
                after_prompt = block[idx + len('- 提示词：'):].lstrip()
                prompt_text = after_prompt.strip()
                prompts.append((shot_id, prompt_text))
            else:
                prompts.append((shot_id, "[未找到提示词]"))
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
                                    log_callback=self.app.log, verbose=True)
                scenes = result.get("scenes", [])
                self.data.script_data = scenes

                self._write_shots_to_file(self.ui.work_dir, scenes)

                self.app.root.after(0, self._on_script_generated, scenes)
            except Exception as e:
                error_msg = str(e)
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"生成剧本失败：{error_msg}"))
                self.app.root.after(0, self._reset_buttons)

        threading.Thread(target=task, daemon=True).start()

    def _write_shots_to_file(self, work_dir, scenes):
        shots_path = os.path.join(work_dir, "shots.txt")
        with open(shots_path, 'w', encoding='utf-8') as f:
            for scene in scenes:
                for idx, shot in enumerate(scene['shots'], start=1):
                    shot_id = f"{scene['id']}-{idx}"
                    title = shot.get('title', scene['title'])
                    f.write(f"【镜头{shot_id}：{title}】\n")
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
        self.ui.script_tab.display_scenes(scenes)
        self.ui.set_button_state('normal', 'normal', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="1. 生成剧本")
        self.app.log("剧本生成完成")
        if hasattr(self.ui, 'assets_tab'):
            self.ui.assets_tab.work_dir = self.ui.work_dir
            self.ui.assets_tab.refresh_file_list()
        self.ui.notebook.select(self.ui.script_tab.frame)

    def save_prompt_edit(self, shot_id, new_prompt):
        """保存编辑后的提示词到易读版分镜文件"""
        work_dir = self.ui.work_dir
        if not work_dir:
            return
        
        # 找到最新的易读版分镜文件
        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        if not files:
            self.app.log("未找到易读版分镜文件，无法保存")
            return
        readable_file = max(files, key=os.path.getmtime)
        
        # 读取文件内容
        with open(readable_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 替换对应镜头的提示词
        import re
        # 匹配模式：【镜头shot_id：标题】... - 提示词：旧内容（到下一个【镜头或文件结尾）
        pattern = r'(【镜头' + re.escape(shot_id) + r'：.*?)(- 提示词：)(.*?)(?=\n【镜头|\Z)'
        def replacer(match):
            prefix = match.group(1)
            keyword = match.group(2)
            # 保留原有格式，只替换内容
            return f"{prefix}{keyword}{new_prompt}"
        
        new_content = re.sub(pattern, replacer, content, flags=re.DOTALL)
        
        # 写回文件
        with open(readable_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        # 同时更新内存中的 prompts 数据（如果存在）
        if hasattr(self.ui, 'prompts_tab') and hasattr(self.ui.prompts_tab, 'prompts_data'):
            self.ui.prompts_tab._update_prompt_in_ui(shot_id, new_prompt)
        
        self.app.log(f"镜头 {shot_id} 的提示词已保存到 {os.path.basename(readable_file)}")

    def _format_scenes_to_text(self, scenes):
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
        persona = set()
        scene_desc = set()
        for scene in script_data['scenes']:
            for shot in scene['shots']:
                for role in shot.get('roles', []):
                    if role.strip():
                        persona.add(role)
                if shot.get('scene'):
                    scene_desc.add(shot['scene'])
        persona_text = "\n".join([f"- {r}" for r in persona]) if persona else "无"
        scene_text = "\n".join([f"- {s}" for s in scene_desc]) if scene_desc else "无"
        style = self.data.style_preset or "电影感、写实、自然光影"
        return {
            'persona': persona_text,
            'scene': scene_text,
            'style': style
        }

    def generate_prompts(self):
        """步骤3：生成视频提示词（文生视频用）"""
        if not self.data.assets:
            messagebox.showwarning("提示", "请先提取资产")
            return

        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return

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
                print("DEBUG: prompts =", prompts)
                self.app.root.after(0, lambda: self.ui.prompts_tab.display_prompts(prompts))
                self.app.root.after(0, self._on_prompts_generated)
            except Exception as e:
                self.app.log(f"生成提示词失败: {e}")
                import traceback
                traceback.print_exc()
                self.app.root.after(0, self._reset_buttons)

        threading.Thread(target=task, daemon=True).start()

    def _on_prompts_generated(self):
        self.ui.set_button_state('normal', 'normal', 'normal', 'disabled')
        self.ui.gen_prompts_btn.config(text="2. 生成提示词")
        self.app.log("提示词生成完成")
        self.ui.notebook.select(self.ui.prompts_tab.frame)

    # ========== 视频生成 ==========
    def confirm_and_generate(self):
        """生成视频（根据模式分流）"""
        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return

        if self.ui.is_i2v_mode:
            self._generate_i2v_videos(work_dir)
        else:
            self._generate_t2v_videos(work_dir)

    def _generate_t2v_videos(self, work_dir):
        """文生视频批量生成（原 confirm_and_generate 逻辑）"""
        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        if not files:
            messagebox.showerror("错误", "未找到易读版分镜文件，请先生成提示词")
            return
        readable_file = max(files, key=os.path.getmtime)
        from core.comfyui_manager_simple import SimpleVideoGenerator
        temp_manager = SimpleVideoGenerator("", "")
        shots_info = temp_manager.get_shots_info(readable_file)
        if not shots_info:
            messagebox.showerror("错误", "解析镜头信息失败")
            return

        video_dir = os.path.join(work_dir, "视频")
        os.makedirs(video_dir, exist_ok=True)
        self.ui.current_video_dir = video_dir

        existing_videos = set()
        for f in os.listdir(video_dir):
            if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                shot_id = f[2:].rsplit('.', 1)[0]
                existing_videos.add(shot_id)

        all_shot_ids = [shot['id'] for shot in shots_info]
        missing_shots = [sid for sid in all_shot_ids if sid not in existing_videos]
        if not missing_shots:
            messagebox.showinfo("提示", "所有镜头均已生成，无需重复生成")
            return

        self.app.log(f"共 {len(all_shot_ids)} 个镜头，已有 {len(existing_videos)} 个，将生成剩余 {len(missing_shots)} 个镜头")

        if hasattr(self.ui, 'video_tab'):
            self.ui.video_tab.set_video_dir(video_dir)

        resolution = self.app.resolution_var.get()
        if not resolution:
            messagebox.showerror("错误", "请先选择分辨率")
            return
        workflow = self.app.workflow_var.get()
        if workflow == "WAN2.2":
            template_file = "video_wan2_2_14B_t2v.json"
        else:
            template_file = "LTX2.3文生API.json"
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        template_path = os.path.join(project_root, "workflow_templates", template_file)

        api_url = config_manager.COMFYUI_API_URL
        def on_shot_generated(shot_id):
            self.app.log(f"镜头 {shot_id} 生成完成，刷新视频面板")
            if hasattr(self.ui, 'video_tab'):
                self.ui.video_tab.on_video_generated(shot_id)

        manager = SimpleVideoGenerator(api_url=api_url, output_base_dir=video_dir, auto_trim=True)
        manager.set_log_callback(self.app.log)

        title = os.path.basename(work_dir).split('_')[0]
        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.app.log("正在生成视频，请稍候...")

        def task():
            try:
                success, msg = manager.run(title, work_dir, resolution, template_path, selected_shots=missing_shots)
                if success:
                    self.app.log("视频生成完成")
                else:
                    self.app.log(f"视频生成失败: {msg}")
                    self.app.root.after(0, lambda: messagebox.showerror("错误", f"视频生成失败：{msg}"))
                self.app.root.after(0, lambda: self._on_video_generated(video_dir))
            except Exception as e:
                self.app.log(f"视频生成异常: {e}")
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"视频生成异常：{e}"))
            finally:
                self.app.root.after(0, lambda: self.ui.set_button_state('normal', 'normal', 'normal', 'disabled'))

        threading.Thread(target=task, daemon=True).start()

    def _generate_i2v_videos(self, work_dir):
        """图生视频批量生成"""
        # 获取镜头信息
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

        video_dir = os.path.join(work_dir, "视频")
        os.makedirs(video_dir, exist_ok=True)
        self.ui.current_video_dir = video_dir

        # 跳过已生成的视频
        existing_videos = set()
        for f in os.listdir(video_dir):
            if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                shot_id = f[2:].rsplit('.', 1)[0]
                existing_videos.add(shot_id)

        # 分辨率
        resolution = self.app.resolution_var.get()
        if not resolution:
            messagebox.showerror("错误", "请先选择分辨率")
            return
        try:
            width, height = map(int, resolution.split('x'))
        except:
            width, height = 1280, 720

        # 禁用按钮
        self._disable_buttons()
        self.app.log(f"共 {len(shots_info)} 个镜头，已有 {len(existing_videos)} 个，将生成剩余镜头...")

        def task():
            success_count = 0
            total_new = len([s for s in shots_info if s['id'] not in existing_videos])
            processed = 0
            for shot in shots_info:
                shot_id = shot['id']
                if shot_id in existing_videos:
                    continue
                processed += 1
                self.app.log(f"已提交 {processed}/{total_new}，剩余 {total_new - processed} 个镜头")
                image_path = os.path.join(work_dir, "images", f"{shot_id}.png")
                if not os.path.exists(image_path):
                    self.app.log(f"镜头 {shot_id} 首帧图不存在，跳过")
                    continue
                prompt = shot.get('prompt', '')
                if not prompt:
                    self.app.log(f"镜头 {shot_id} 提示词为空，跳过")
                    continue
                duration = shot.get('duration', 10)
                self.app.log(f"正在生成镜头 {shot_id}...")
                try:
                    video_path = generate_single_video(
                        work_dir=work_dir,
                        shot_id=shot_id,
                        image_path=image_path,
                        prompt=prompt,
                        duration=duration,
                        width=width,
                        height=height,
                        log_callback=self.app.log,
                        auto_trim=True
                    )
                    if video_path:
                        success_count += 1
                        self.app.log(f"镜头 {shot_id} 生成成功")
                        if hasattr(self.ui, 'video_tab'):
                            self.app.root.after(0, lambda sid=shot_id: self.ui.video_tab.on_video_generated(sid))
                    else:
                        self.app.log(f"镜头 {shot_id} 生成失败")
                except Exception as e:
                    self.app.log(f"镜头 {shot_id} 异常: {e}")
            self.app.log(f"视频生成完成，成功 {success_count}/{total_new} 个新镜头")
            self.app.root.after(0, self._enable_buttons)

        threading.Thread(target=task, daemon=True).start()

    def _on_video_generated(self, video_dir):
        if hasattr(self.ui, 'video_tab'):
            self.ui.video_tab.set_video_dir(video_dir)
        self.app.log("视频面板已刷新")

    def retake_single_shot(self, shot_id):
        """重试生成单个镜头（根据当前模式选择文生或图生）"""
        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return
        video_dir = self.ui.current_video_dir
        if not video_dir or not os.path.isdir(video_dir):
            video_dir = os.path.join(work_dir, "视频")
            if not os.path.isdir(video_dir):
                messagebox.showerror("错误", "未找到视频文件夹，请先生成视频")
                return

        resolution = self.app.resolution_var.get()
        if not resolution:
            messagebox.showerror("错误", "请先选择分辨率")
            return
        try:
            width, height = map(int, resolution.split('x'))
        except:
            width, height = 1280, 720

        if self.ui.is_i2v_mode:
            # 图生视频重试：调用 generate_single_video
            # 获取镜头信息
            pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
            files = glob.glob(pattern)
            if not files:
                messagebox.showerror("错误", "未找到易读版分镜文件")
                return
            readable_file = max(files, key=os.path.getmtime)
            from core.comfyui_manager import ComfyUIManager
            temp_manager = ComfyUIManager("", "")
            shots_info = temp_manager.get_shots_info(readable_file)
            shot_info = next((s for s in shots_info if s['id'] == shot_id), None)
            if not shot_info:
                messagebox.showerror("错误", f"未找到镜头 {shot_id} 的信息")
                return
            image_path = os.path.join(work_dir, "images", f"{shot_id}.png")
            if not os.path.exists(image_path):
                messagebox.showerror("错误", f"首帧图不存在: {image_path}")
                return
            prompt = shot_info.get('prompt', '')
            duration = shot_info.get('duration', 10)
            if hasattr(self.ui, 'video_tab'):
                self.ui.video_tab.set_retake_button_state(False)
            def task():
                try:
                    video_path = generate_single_video(
                        work_dir=work_dir,
                        shot_id=shot_id,
                        image_path=image_path,
                        prompt=prompt,
                        duration=duration,
                        width=width,
                        height=height,
                        log_callback=self.app.log,
                        auto_trim=True
                    )
                    if video_path:
                        self.app.log(f"镜头 {shot_id} 重试成功")
                        self.app.root.after(0, lambda: self._refresh_video_tab())
                    else:
                        self.app.log(f"镜头 {shot_id} 重试失败")
                except Exception as e:
                    self.app.log(f"重试异常: {e}")
                finally:
                    self.app.root.after(0, lambda: self.ui.video_tab.set_retake_button_state(True))
            threading.Thread(target=task, daemon=True).start()
        else:
            # 文生视频重试
            workflow = self.app.workflow_var.get()
            if workflow == "WAN2.2":
                template_file = "video_wan2_2_14B_t2v.json"
            else:
                template_file = "LTX2.3文生API.json"
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            template_path = os.path.join(project_root, "workflow_templates", template_file)
            api_url = config_manager.COMFYUI_API_URL
            manager = SimpleVideoGenerator(api_url=api_url, output_base_dir=video_dir)
            manager.set_log_callback(self.app.log)
            title = os.path.basename(work_dir).split('_')[0]
            if hasattr(self.ui, 'video_tab'):
                self.ui.video_tab.set_retake_button_state(False)
            def task():
                try:
                    success, msg = manager.run(title, work_dir, resolution, template_path, selected_shots=[shot_id])
                    if success:
                        self.app.log(f"镜头 {shot_id} 重试成功")
                    else:
                        self.app.log(f"镜头 {shot_id} 重试失败: {msg}")
                        self.app.root.after(0, lambda: messagebox.showerror("错误", f"重试失败：{msg}"))
                    self.app.root.after(0, lambda: self._refresh_video_tab())
                except Exception as e:
                    self.app.log(f"重试异常: {e}")
                    self.app.root.after(0, lambda: messagebox.showerror("错误", f"重试异常：{e}"))
                finally:
                    self.app.root.after(0, lambda: self.ui.video_tab.set_retake_button_state(True))
            threading.Thread(target=task, daemon=True).start()

    def _refresh_video_tab(self):
        if hasattr(self.ui, 'video_tab'):
            self.ui.video_tab.refresh_video_list()

    def merge_videos(self):
        messagebox.showinfo("提示", "合并视频功能待实现")

    def continue_generation(self):
        """意外断开后继续生成未完成的镜头（文生视频用）"""
        work_dir = self.ui.work_dir
        if not work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return

        video_dir = os.path.join(work_dir, "视频")
        if not os.path.isdir(video_dir):
            messagebox.showerror("错误", "视频文件夹不存在，请先生成视频")
            return

        import re
        existing_shots = set()
        for f in os.listdir(video_dir):
            if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                match = re.search(r'镜头(\d+-\d+)', f)
                if match:
                    existing_shots.add(match.group(1))

        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        if not files:
            messagebox.showerror("错误", "未找到易读版分镜文件，请先生成提示词")
            return
        readable_file = max(files, key=os.path.getmtime)
        from core.comfyui_manager import ComfyUIManager
        temp_manager = ComfyUIManager("", "")
        all_shots = temp_manager.get_shots_info(readable_file)
        all_shot_ids = [shot['id'] for shot in all_shots]

        missing_shots = [sid for sid in all_shot_ids if sid not in existing_shots]
        if not missing_shots:
            messagebox.showinfo("提示", "所有镜头均已生成，无需继续")
            return

        self.pending_missing_shots = missing_shots
        self.confirm_and_generate()

    def _reset_buttons(self):
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