import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import threading
import json
import time
import re
import shutil
import winsound
from datetime import datetime

from utils import config_manager, process_runner
from gui import step_manager, countdown_timer, settings_dialog
from gui.shot_editor import ShotEditorWindow
from core import comfyui_manager
from gui.simple_mode import SimpleMode
from gui.log_viewer import LogViewer
from gui.standard_mode import StandardMode
from gui.common_widgets import CommonWidgets
from gui.top_toolbar import TopToolbar
from gui.audio_panel import AudioPanel
from tkinter import scrolledtext
from gui.image_panel import ImagePanel

ASPECT_RATIO_MAP = {
    "16:9": ["640x360", "854x480", "1280x720", "1920x1080", "2560x1440"],
    "4:3": ["640x480", "800x600", "1024x768", "1280x960", "1440x1080", "1600x1200", "2048x1536"],
    "2.35:1": ["1280x544", "1920x816", "3840x1640"],
    "2:1": ["1280x640", "1920x960", "3840x1920"],
    "1.85:1": ["1280x690", "1920x1038", "3840x2076"],
    "9:16": ["540x960", "720x1280", "1080x1920", "1440x2560"],
    "3:4": ["480x640", "720x960", "1080x1440", "1440x1920"],
    "1:1": ["640x640", "1024x1024", "1080x1080", "1200x1200"]
}

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("分镜生成助手 - 总控台")
        # 获取屏幕尺寸
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = 1400
        window_height = 900
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(1000, 700)
        self._updating_slider = False
        self.continue_mode = False
        self.remaining_shots = None
        self._work_dir_set = None
        self.video_generation_callbacks = []   # 存储回调函数

        # 初始化临时目录
        self.temp_dir = os.path.join(os.path.dirname(__file__), "temp_uploads")
        os.makedirs(self.temp_dir, exist_ok=True)
        for f in os.listdir(self.temp_dir):
            try:
                os.remove(os.path.join(self.temp_dir, f))
            except:
                pass

        # 日志文件
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = os.path.join(log_dir, f"运行日志_{log_timestamp}.txt")
        with open(self.log_file_path, 'w', encoding='utf-8') as f:
            f.write(f"=== 运行日志 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

        # 加载 API 配置
        self.api_key, self.model = config_manager.load_config()
        if not self.api_key:
            self.api_key = ''
            self.model = 'deepseek-chat'
        else:
            os.environ.pop('DEEPSEEK_API_KEY', None)
            os.environ['DEEPSEEK_API_KEY'] = self.api_key
            print(f"已从配置文件加载 API Key: {self.api_key[:8]}...")

        # 日志查看器
        self.log_viewer = LogViewer(self.root, self.log_file_path)

        # 顶部工具栏
        self.toolbar = TopToolbar(self.root, self)
        self.workflow_var = self.toolbar.workflow_var
        self.aspect_ratio_var = self.toolbar.aspect_ratio_var
        self.resolution_var = self.toolbar.resolution_var
        self.toolbar.pack(fill='x', padx=5, pady=5)
        self.toolbar.mode_var.trace('w', self.on_video_mode_change)

        # 主布局：侧边栏 + 内容区
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 左侧侧边栏
        self.sidebar = ttk.Frame(main_paned, width=120)
        main_paned.add(self.sidebar, weight=0)
        self.create_sidebar()

        # 右侧内容区
        self.content_frame = ttk.Frame(main_paned)
        main_paned.add(self.content_frame, weight=1)

        # 创建各模块的框架
        self.story_frame = ttk.Frame(self.content_frame)
        self.audio_frame = ttk.Frame(self.content_frame)
        self.video_frame = ttk.Frame(self.content_frame)
        self.edit_frame = ttk.Frame(self.content_frame)
        self.image_frame = ttk.Frame(self.content_frame)   # 新增
        
        # 创建图像面板
        from gui.image_panel import ImagePanel
        self.image_panel = ImagePanel(self.image_frame, self)
        self.image_panel.pack(fill='both', expand=True)
        self.image_frame.pack_forget()

        # 故事模块：包含标准模式和一键成片面板
        self.standard_mode = StandardMode(self.story_frame, self, ASPECT_RATIO_MAP)
        self.simple_mode = SimpleMode(self.story_frame, self)

        # 默认显示标准模式
        self.standard_mode.frame.pack(fill='both', expand=True)
        self.simple_mode.frame.pack_forget()

        # 音频模块
        self.audio_panel = AudioPanel(self.audio_frame, work_dir=None, app=self, log_callback=self.log)
        self.audio_panel.on_subtitle_generated = self.on_subtitle_generated

        # 视频模块
        self.create_video_panel()

        # 剪辑模块（占位）
        self.create_edit_panel()

        # 初始显示故事模块
        self.current_module = "故事"
        self.show_story()

        # 底部状态栏
        self.create_status_bar()

        # 其他初始化
        self.runner = process_runner.ProcessRunner(
            log_callback=self.log,
            error_callback=self._handle_fatal_error
        )
        self.step_mgr = step_manager.StepManager(
            runner=self.runner,
            log_callback=self.log,
            progress_callback=self.set_progress,
            processing_failed_callback=self.processing_failed,
            mode=self.toolbar.text_type_var.get()
        )
        self.timer = countdown_timer.CountdownTimer(
            root=self.root,
            update_callback=self.update_countdown_display,
            timeout_callback=self.run_workflow
        )

        self.work_dir = None
        self.story_title = None
        self.processing = False
        self.is_history_project = False
        self.shots_info = None
        self.selected_shots_ids = None
        self.edited_prompts = {}
        self.temp_subtitle_path = None

        # 绑定模式切换事件
        self.toolbar.mode_type_var.trace('w', lambda *args: self.on_mode_type_change())
        self.toolbar.text_type_var.trace('w', lambda *args: self._update_preset_label())
        self.toolbar.mode_var.trace('w', self.on_video_mode_change)

        self._resize_timer = None
        self.root.bind('<Configure>', self._on_window_configure)
        self.root.bind('<ButtonRelease-1>', self._on_window_release)

    def _on_window_configure(self, event):
        if event.widget == self.root:  # 仅根窗口
            if self._resize_timer:
                self.root.after_cancel(self._resize_timer)
            self._resize_timer = self.root.after(200, self._delayed_refresh)

    def _on_window_release(self, event):
        if self._resize_timer:
            self.root.after_cancel(self._resize_timer)
        self._delayed_refresh()

    def show_image(self):
        self.hide_all_modules()
        self.image_frame.pack(fill='both', expand=True)
        self.current_module = "图像"
        if self.work_dir:
            self.image_panel.set_work_dir(self.work_dir)
        else:
            self.image_panel.set_work_dir(None)
        self.image_panel.refresh()

    def _delayed_refresh(self):
        self.root.update_idletasks()
        # 如果有 canvas 需要刷新滚动区域，可以调用
        # 例如：self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_video_mode_change(self, *args):
        """当视频模式（文生/图生）改变时，如果当前是一键成片模式，则通知 simple_mode 切换"""
        if self.toolbar.mode_type_var.get() == "一键成片":
            is_i2v = (self.toolbar.mode_var.get() == "图生视频")
            self.simple_mode.set_i2v_mode(is_i2v)

    def register_video_generation_callback(self, callback):
        """注册视频生成回调，当有镜头生成时调用"""
        self.video_generation_callbacks.append(callback)

    def on_subtitle_generated(self, srt_path):
        """字幕生成后自动设置为有字幕模式"""
        self.toolbar.subtitle_mode_var.set("有字幕")
        self.standard_mode.upload_subtitle_btn.config(state='disabled')
        # self.standard_mode.apply_duration_btn.config(state='normal')
        # self.standard_mode.optimize_and_continue_btn.config(state='normal')
        self.log("字幕已生成，可点击「应用字幕时长」或「优化并继续」")

    # ---------- 侧边栏 ----------
    def create_sidebar(self):
        ttk.Button(self.sidebar, text="📖 故事", command=self.show_story).pack(fill='x', padx=10, pady=5)
        ttk.Button(self.sidebar, text="🎵 音频", command=self.show_audio).pack(fill='x', padx=10, pady=5)
        ttk.Button(self.sidebar, text="🖼️ 图像", command=self.show_image).pack(fill='x', padx=10, pady=5)
        ttk.Button(self.sidebar, text="🎬 视频", command=self.show_video).pack(fill='x', padx=10, pady=5)
        ttk.Button(self.sidebar, text="✂️ 剪辑", command=self.show_edit).pack(fill='x', padx=10, pady=5)

    def show_story(self):
        self.hide_all_modules()
        self.story_frame.pack(fill='both', expand=True)
        self.current_module = "故事"

    def show_audio(self):
        self.hide_all_modules()
        self.audio_frame.pack(fill='both', expand=True)
        if not hasattr(self, 'audio_panel') or self.audio_panel is None:
            self.audio_panel = AudioPanel(self.audio_frame, work_dir=self.work_dir, app=self, log_callback=self.log)
        else:
            if self.work_dir is not None and self.audio_panel.work_dir != self.work_dir:
                print("[DEBUG] show_audio: calling audio_panel.set_work_dir")
                self.audio_panel.set_work_dir(self.work_dir)
                print("[DEBUG] show_audio: after set_work_dir")
        self.audio_panel.pack(fill='both', expand=True)

        # 如果是新项目（尚未设置工作目录或未加载过），才同步口播稿
        if not self.work_dir or not self.is_history_project:
            self.sync_script_to_audio()
        # 注意：历史项目的数据已经在 open_history_project 中通过 set_work_dir 加载完毕，
        # 这里不再重复加载，避免重复扫描音频文件。

        self.current_module = "音频"

    def show_video(self):
        self.hide_all_modules()
        self.video_frame.pack(fill='both', expand=True)
        self.current_module = "视频"

    def show_edit(self):
        self.hide_all_modules()
        self.edit_frame.pack(fill='both', expand=True)
        self.current_module = "剪辑"

    def hide_all_modules(self):
        self.story_frame.pack_forget()
        self.audio_frame.pack_forget()
        self.video_frame.pack_forget()
        self.edit_frame.pack_forget()
        self.image_frame.pack_forget()

    def sync_script_to_audio(self):
        """将当前口播稿文本同步到音频面板"""
        script = ""
        if self.toolbar.mode_type_var.get() == "标准模式":
            # 从标准模式的口播稿标签页获取文本
            script_widget = self.standard_mode.text_widgets.get('script')
            if script_widget:
                script = script_widget.get('1.0', 'end-1c').strip()
        else:
            # 一键成片模式：从预览文本框获取
            script = self.simple_mode.story_tab.text_widget.get('1.0', 'end-1c').strip()
        self.audio_panel.set_script(script)

    # ---------- 视频模块 ----------
    def create_video_panel(self):
        """创建视频模块控件（仅保留按钮和视频列表）"""
        # 按钮区域
        btn_frame = ttk.Frame(self.video_frame)
        btn_frame.pack(fill='x', padx=5, pady=5)

        ttk.Button(btn_frame, text="运行工作流", command=self.run_workflow, width=12).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="选择或编辑视频提示词", command=self.open_shot_editor, width=16).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="视频精确裁剪", command=self.run_video_align, width=12).pack(side='left', padx=2)

        self.continue_btn = ttk.Button(btn_frame, text="继续", command=self.continue_generation, state='disabled', width=8)
        self.continue_btn.pack(side='left', padx=2)

        from gui.standard_video_panel import StandardVideoPanel
        self.video_panel = StandardVideoPanel(self.video_frame, self)
        self.video_panel.frame.pack(fill='both', expand=True, padx=5, pady=5)

    def create_edit_panel(self):
        """创建剪辑模块（占位）"""
        ttk.Label(self.edit_frame, text="后期剪辑功能开发中...", font=('微软雅黑', 14)).pack(expand=True)

    # ---------- 底部状态栏 ----------
    def create_status_bar(self):
        status_frame = ttk.Frame(self.root)
        status_frame.pack(side='bottom', fill='x', padx=5, pady=2)

        self.dir_label = ttk.Label(status_frame, text="", anchor='w')
        self.dir_label.pack(side='left', padx=5)

        self.progress = ttk.Progressbar(status_frame, length=200, mode='determinate')
        self.progress.pack(side='left', padx=5)

        self.status_label = ttk.Label(status_frame, text="就绪", anchor='w')
        self.status_label.pack(side='left', fill='x', expand=True, padx=5)

        # 日志折叠按钮
        self.log_visible = True
        self.log_toggle_btn = ttk.Button(status_frame, text="▲ 收起日志", command=self.toggle_log)
        self.log_toggle_btn.pack(side='right', padx=5)

        # 日志文本框（初始显示）
        self.log_text = scrolledtext.ScrolledText(self.root, height=8, state='disabled')
        self.log_text.pack(side='bottom', fill='x', padx=5, pady=2)

    def toggle_log(self):
        if self.log_visible:
            self.log_text.pack_forget()
            self.log_toggle_btn.config(text="▼ 展开日志")
            self.log_visible = False
        else:
            self.log_text.pack(side='bottom', fill='x', padx=5, pady=2)
            self.log_toggle_btn.config(text="▲ 收起日志")
            self.log_visible = True

    def _load_script_from_history(self, work_dir):
        """从历史工作目录加载口播稿文本（优先匹配与目录名相同的 txt 文件）"""
        dir_name = os.path.basename(work_dir)  # 例如 "人口变量_20260322_1145"
        
        # 1. 优先查找与目录名完全同名的 .txt 文件
        target_file = os.path.join(work_dir, f"{dir_name}.txt")
        if os.path.exists(target_file):
            with open(target_file, 'r', encoding='utf-8') as f:
                content = f.read()
            # 尝试提取 "口播稿扩展" 之后的部分（如果存在）
            import re
            match = re.search(r'口播稿扩展\n(.*)', content, re.DOTALL)
            if match:
                return match.group(1).strip()
            else:
                # 如果没有该标记，返回整个文件内容（可能包含其他设定）
                return content.strip()
        
        # 2. 如果找不到精确同名，尝试匹配以目录名开头的 txt 文件（例如带额外后缀）
        import glob
        candidates = glob.glob(os.path.join(work_dir, f"{dir_name}*.txt"))
        # 排除系统文件
        exclude = {'header.txt', 'shots.txt', 'style_params.json', 'input.json'}
        for f in candidates:
            basename = os.path.basename(f)
            if basename not in exclude:
                with open(f, 'r', encoding='utf-8') as fp:
                    content = fp.read()
                match = re.search(r'口播稿扩展\n(.*)', content, re.DOTALL)
                if match:
                    return match.group(1).strip()
                else:
                    # 如果文件内容较少（<500字）且包含"口播稿扩展"未匹配，则返回整体
                    if len(content) < 2000:  # 小文件可能是纯口播稿
                        return content.strip()
        
        # 3. 回退：从 input.json 的 segments 中提取所有 content
        input_json = os.path.join(work_dir, "input.json")
        if os.path.exists(input_json):
            try:
                with open(input_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                segments = data.get('segments', [])
                script = '\n\n'.join(seg.get('content', '') for seg in segments)
                if script:
                    return script
            except Exception as e:
                self.log(f"从 input.json 读取口播稿失败: {e}")
        
        # 4. 如果都没有，返回 None
        return None

    # ---------- 公共方法 ----------
    def log(self, message):
        self.log_text.config(state='normal')
        timestamp = datetime.now().strftime("[%H:%M:%S] ")
        self.log_text.insert('end', timestamp + message + '\n')
        self.log_text.see('end')
        self.log_text.config(state='disabled')
        try:
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(timestamp + message + '\n')
        except:
            pass

    def set_progress(self, value):
        self.progress['value'] = value

    def update_countdown_display(self, remaining):
        self.status_label.config(text=f"倒计时：{remaining}秒后自动运行工作流")
        if self.toolbar.mode_type_var.get() == "一键成片":
            self.simple_mode.show_countdown(remaining)

    def open_log_folder(self):
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        if os.path.exists(log_dir):
            os.startfile(log_dir)
        else:
            messagebox.showerror("错误", "日志文件夹不存在")

    def open_settings(self):
        settings_dialog.show_settings(self.root)
        # 重新加载 API 配置（因为用户可能在设置中修改了）
        self.api_key, self.model = config_manager.load_config()
        if self.api_key:
            os.environ['DEEPSEEK_API_KEY'] = self.api_key
        else:
            os.environ.pop('DEEPSEEK_API_KEY', None)

    def _update_preset_label(self):
        mode = self.toolbar.text_type_var.get()
        if not mode:
            self.toolbar.preset_label.config(text="人设卡: 未选择")
            return
        if mode == "情感故事":
            preset = config_manager.PRESET_EMOTIONAL
        elif mode == "文明结构":
            preset = config_manager.PRESET_CIVIL
        elif mode == "动画默剧":
            preset = config_manager.PRESET_MIME
        else:
            preset = "未知"
        self.toolbar.preset_label.config(text=f"人设卡: {preset}")

    def open_preset_manager(self):
        from gui.preset_manager import PresetManagerWindow
        current_mode = self.toolbar.text_type_var.get()
        win = PresetManagerWindow(self.root, current_mode)
        self.root.wait_window(win.win)
        if hasattr(win, 'result') and win.result:
            self._update_preset_label()

    def on_subtitle_mode_change(self, event=None):
        mode = self.toolbar.subtitle_mode_var.get()
        # 由于字幕功能仍在标准模式中，此处保留
        if mode == "有字幕":
            self.standard_mode.upload_subtitle_btn.config(state='normal')
        else:
            self.standard_mode.upload_subtitle_btn.config(state='disabled')
            if self.temp_subtitle_path and os.path.exists(self.temp_subtitle_path):
                try:
                    os.remove(self.temp_subtitle_path)
                except:
                    pass
                self.temp_subtitle_path = None

    def on_mode_type_change(self, event=None):
        mode = self.toolbar.mode_type_var.get()
        if not self._updating_slider:
            self._updating_slider = True
            if mode == "标准模式":
                self.toolbar.mode_slider.set(0)
            else:
                self.toolbar.mode_slider.set(1)
            self._updating_slider = False

        if mode == "一键成片":
            self.standard_mode.frame.pack_forget()
            self.simple_mode.frame.pack(fill='both', expand=True)
            # 确保底部日志框不被覆盖
            self.log_text.pack(side='bottom', fill='x', padx=5, pady=2)
            self.log_text.lift()
            self.root.update_idletasks()   # 强制刷新布局
            self.toolbar.extra_left_frame.pack_forget()
            is_i2v = (self.toolbar.mode_var.get() == "图生视频")
            self.simple_mode.set_i2v_mode(is_i2v)
            # 修复日志框被覆盖的问题
            if hasattr(self, 'log_text') and self.log_text:
                self.log_text.pack_forget()
                self.log_text.pack(side='bottom', fill='x', padx=5, pady=2)
                self.log_text.lift()
                self.root.update_idletasks()
        else:
            self.simple_mode.frame.pack_forget()
            self.standard_mode.frame.pack(fill='both', expand=True)
            self.toolbar.extra_left_frame.pack(side='left', after=self.toolbar.title_entry)

        self.sync_script_to_audio()

    # ---------- 业务方法 ----------
    def open_history_project(self):
        folder = filedialog.askdirectory(title="选择历史工作目录")
        if not folder:
            return
        # 检测项目类型：如果存在 story.txt 或 metadata.json，则为一键成片项目
        if os.path.exists(os.path.join(folder, "story.txt")) or os.path.exists(os.path.join(folder, "metadata.json")):
            # 切换模式
            self.toolbar.mode_type_var.set("一键成片")
            self.on_mode_type_change()  # 触发界面切换
            # 加载项目
            self.simple_mode.load_project(folder)
            self.work_dir = folder
            self.status_label.config(text=f"已加载历史项目: {os.path.basename(folder)}")
            self.dir_label.config(text=f"工作目录: {folder}")
            self.log(f"已加载一键成片历史项目: {folder}")
        else:
            if not folder:
                return
            header_path = os.path.join(folder, "header.txt")
            shots_path = os.path.join(folder, "shots.txt")
            para_path = os.path.join(folder, "paragraphs.json")
            # 新流程：存在 header.txt 且 (shots.txt 或 paragraphs.json)
            if not os.path.exists(header_path) or (not os.path.exists(shots_path) and not os.path.exists(para_path)):
                messagebox.showerror("错误", "所选目录不是有效的工作目录（缺少 header.txt 且缺少 shots.txt 或 paragraphs.json）")
                return

            try:
                with open(header_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("project:"):
                            self.story_title = line.split(":", 1)[1].strip()
                            break
                if not self.story_title:
                    self.story_title = os.path.basename(folder)
            except Exception:
                self.story_title = os.path.basename(folder)
            self.work_dir = folder
            self.is_history_project = True
            self.status_label.config(text=f"已加载历史项目: {self.story_title}")
            self.dir_label.config(text=f"工作目录: {self.work_dir}")

            # 字幕文件检测
            srt_path = os.path.join(self.work_dir, "input.srt")
            if os.path.exists(srt_path):
                self.toolbar.subtitle_mode_var.set("有字幕")
                self.standard_mode.upload_subtitle_btn.config(state='disabled')
                # 若有字幕，可以启用对齐等按钮
                # self.standard_mode.apply_duration_btn.config(state='normal')
                # self.standard_mode.optimize_and_continue_btn.config(state='normal')
                self.log("检测到已存在的字幕文件，可点击「应用字幕时长」或「优化并继续」")
            else:
                self.toolbar.subtitle_mode_var.set("无字幕")
                self.standard_mode.upload_subtitle_btn.config(state='normal')
                # self.standard_mode.apply_duration_btn.config(state='disabled')
                # self.standard_mode.optimize_and_continue_btn.config(state='disabled')

            # 尝试从易读版分镜文件获取镜头信息（如果有）
            temp_manager = comfyui_manager.ComfyUIManager("", "")
            readable_file = temp_manager.get_latest_readable_file(self.work_dir)
            if readable_file:
                self.shots_info = temp_manager.get_shots_info(readable_file)
                if self.shots_info:
                    self.standard_mode.select_edit_btn.config(state='normal')
                    self.log(f"找到 {len(self.shots_info)} 个镜头（来自易读版），可点击「选择或编辑提示词」进行筛选")
                else:
                    self.shots_info = None
                    self.standard_mode.select_edit_btn.config(state='disabled')
            else:
                # 如果没有易读版，尝试从 shots.txt 解析（旧项目）
                if os.path.exists(shots_path):
                    self.shots_info = self._parse_shots_from_txt(shots_path)
                    if self.shots_info:
                        self.standard_mode.select_edit_btn.config(state='normal')
                        self.log(f"找到 {len(self.shots_info)} 个镜头（来自 shots.txt），但尚未生成详细分镜，编辑功能可能受限")
                    else:
                        self.shots_info = None
                        self.standard_mode.select_edit_btn.config(state='disabled')
                else:
                    # 新流程：只有 paragraphs.json，尚未生成分镜
                    self.shots_info = None
                    self.standard_mode.select_edit_btn.config(state='disabled')
                    self.log("未找到分镜文件，请先通过音频模块生成字幕和分镜。")

            # 根据项目类型启用对应按钮
            self.standard_mode.run_workflow_btn.config(state='normal', text="运行工作流")
            self.standard_mode.first_frame_btn.config(state='normal')
            self.standard_mode.align_btn.config(state='normal')
            self.log(f"已加载历史工作目录: {self.work_dir}")

            # 加载口播稿或段落到音频面板
            if os.path.exists(para_path):
                # 新项目，加载段落
                print("[DEBUG] open_history_project: calling audio_panel.set_work_dir")
                self.audio_panel.set_work_dir(self.work_dir)
                print("[DEBUG] open_history_project: after set_work_dir")
                # self.audio_panel.load_paragraphs(self.work_dir)
                self.log("已加载段落，可进行音频生成")
                # 启用预览段落按钮
                self.standard_mode.preview_btn.config(state='normal')
            else:
                # 旧项目，尝试加载口播稿
                script = self._load_script_from_history(self.work_dir)
                if script:
                    self.audio_panel.set_script(script)
                    self.log("已自动加载口播稿到音频面板")
                else:
                    self.log("未找到口播稿，请手动加载或生成")
            if hasattr(self, 'video_panel'):
                self.video_panel.set_work_dir(self.work_dir)

    def _parse_shots_from_txt(self, shots_path):
        shots = []
        with open(shots_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('【镜头') and '：' in line:
                match = re.match(r'【镜头(\d+-\d+)：([^】]+)】', line)
                if match:
                    shot_id = match.group(1)
                    title = match.group(2)
                    duration = 10
                    emotion = ""
                    visual = ""
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith('【镜头') and not lines[i].strip().startswith('==========================='):
                        subline = lines[i].strip()
                        if subline.startswith('- 时长：'):
                            dur_match = re.search(r'(\d+)', subline)
                            if dur_match:
                                duration = int(dur_match.group(1))
                        elif subline.startswith('- 情绪基调：'):
                            emotion = subline.split('：', 1)[-1].strip()
                        elif subline.startswith('- 视觉描述：'):
                            visual = subline.split('：', 1)[-1].strip()
                        i += 1
                    shots.append({
                        'id': shot_id,
                        'title': title,
                        'prompt': visual,
                        'duration': duration
                    })
                    continue
            i += 1
        return shots

    def start_processing(self):
        if self.processing:
            return
        title = self.toolbar.title_entry.get().strip()
        if not title:
            messagebox.showerror("错误", "请输入故事标题")
            return
        mode = self.toolbar.text_type_var.get()
        if not mode:
            messagebox.showerror("错误", "请先选择文本类型")
            return
        subtitle_mode = self.toolbar.subtitle_mode_var.get()
        if not subtitle_mode:
            messagebox.showerror("错误", "请先选择字幕模式（有字幕/无字幕）")
            return
        api_key = self.toolbar.api_key_entry.get().strip()
        if not api_key:
            messagebox.showerror("错误", "请输入 API Key")
            return
        os.environ['DEEPSEEK_API_KEY'] = api_key

        if subtitle_mode == "有字幕" and not self.temp_subtitle_path:
            messagebox.showerror("错误", "您选择了有字幕模式，但尚未上传字幕文件。请先点击「上传字幕」按钮选择字幕文件。")
            return

        self.story_title = title
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        folder_name = f"{title}_{timestamp}"
        base_dir = config_manager.OUTPUT_ROOT_DIR
        self.work_dir = os.path.join(base_dir, folder_name)
        os.makedirs(self.work_dir, exist_ok=True)
        self.log(f"工作目录: {self.work_dir}")
        self.dir_label.config(text=f"工作目录: {self.work_dir}")
        self.is_history_project = False
        self.shots_info = None
        self.selected_shots_ids = None
        self.edited_prompts = {}
        self.standard_mode.select_edit_btn.config(state='disabled')

        if subtitle_mode == "有字幕" and self.temp_subtitle_path and os.path.exists(self.temp_subtitle_path):
            dest = os.path.join(self.work_dir, "input.srt")
            shutil.move(self.temp_subtitle_path, dest)
            self.temp_subtitle_path = None
            self.log(f"字幕文件已移动到: {dest}")
            # self.standard_mode.apply_duration_btn.config(state='normal')
            # self.standard_mode.optimize_and_continue_btn.config(state='normal')
        else:
            # self.standard_mode.apply_duration_btn.config(state='disabled')
            # self.standard_mode.optimize_and_continue_btn.config(state='disabled')
            pass

        persona = self.standard_mode.text_widgets['persona'].get("1.0", 'end-1c').strip()
        scene = self.standard_mode.text_widgets['scene'].get("1.0", 'end-1c').strip()
        story = self.standard_mode.text_widgets['story'].get("1.0", 'end-1c').strip()
        script = self.standard_mode.text_widgets['script'].get("1.0", 'end-1c').strip()

        content = ""
        if persona:
            content += "★人物设定开始★\n" + persona + "\n★人物设定结束★\n\n"
        if scene:
            content += "★场景设定开始★\n" + scene + "\n★场景设定结束★\n\n"
        if story:
            content += "★故事大纲开始★\n" + story + "\n★故事大纲结束★\n\n"
        if script:
            content += "★口播稿开始★\n" + script + "\n★口播稿结束★\n\n"

        input_filename = f"{title}_{timestamp}.txt"
        input_file_path = os.path.join(self.work_dir, input_filename)
        with open(input_file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        self.log(f"已生成输入文件: {input_file_path}")

        self.standard_mode.start_btn.config(state='disabled')
        self.processing = True
        self.status_label.config(text="正在执行第一步...")
        self.set_progress(0)

        self.step_mgr.mode = mode

        thread = threading.Thread(target=self._run_steps_thread, args=(input_filename,))
        thread.daemon = True
        thread.start()

    def upload_subtitle(self):
        file_path = filedialog.askopenfilename(
            title="选择字幕文件",
            filetypes=[("SRT files", "*.srt"), ("All files", "*.*")]
        )
        if not file_path:
            return
        try:
            if self.work_dir and os.path.exists(self.work_dir):
                dest = os.path.join(self.work_dir, "input.srt")
                shutil.copy2(file_path, dest)
                self.log(f"字幕文件已复制至: {dest}")
                # self.standard_mode.apply_duration_btn.config(state='normal')
                # self.standard_mode.optimize_and_continue_btn.config(state='normal')
                messagebox.showinfo("成功", "字幕上传成功，可点击「应用字幕时长」或「优化并继续」")
            else:
                base_name = os.path.basename(file_path)
                temp_dest = os.path.join(self.temp_dir, base_name)
                if os.path.exists(temp_dest):
                    name, ext = os.path.splitext(base_name)
                    temp_dest = os.path.join(self.temp_dir, f"{name}_{int(time.time())}{ext}")
                shutil.copy2(file_path, temp_dest)
                self.temp_subtitle_path = temp_dest
                self.log(f"字幕文件已暂存至临时目录: {temp_dest}")
                if not self.toolbar.subtitle_mode_var.get():
                    self.toolbar.subtitle_mode_var.set("有字幕")
                    self.standard_mode.upload_subtitle_btn.config(state='normal')
                messagebox.showinfo("成功", "字幕已暂存，开始处理时将自动移动到工作目录。")
        except Exception as e:
            messagebox.showerror("错误", f"上传失败: {e}")

    def apply_subtitle_duration(self):
        if not self.work_dir:
            messagebox.showerror("错误", "工作目录不存在")
            return
        srt_path = os.path.join(self.work_dir, "input.srt")
        if not os.path.exists(srt_path):
            messagebox.showerror("错误", "未找到字幕文件，请先上传")
            return

        # self.standard_mode.apply_duration_btn.config(state='disabled', text="优化中...")
        self.log("\n========== 应用字幕优化镜头 ==========")

        def run_task():
            try:
                script_path = os.path.join(os.path.dirname(__file__), "core", "refine_shots_by_srt.py")
                cmd = [sys.executable, '-u', script_path, self.work_dir]
                rc, success = self.runner.run(cmd)
                if success:
                    refined_path = os.path.join(self.work_dir, "input_refined.json")
                    if os.path.exists(refined_path):
                        self.root.after(0, lambda: self.log("优化完成，生成 input_refined.json"))
                    else:
                        self.root.after(0, lambda: self.log("优化执行完成但未找到输出文件"))
                else:
                    self.root.after(0, lambda: self.log("字幕优化失败，请检查日志"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"优化过程异常: {e}"))
            finally:
                # self.root.after(0, lambda: self.standard_mode.apply_duration_btn.config(state='normal', text="应用字幕时长"))
                pass
        thread = threading.Thread(target=run_task)
        thread.daemon = True
        thread.start()

    def optimize_and_continue(self):
        if not self.work_dir:
            messagebox.showerror("错误", "工作目录不存在")
            return

        refined_path = os.path.join(self.work_dir, "input_refined.json")
        if not os.path.exists(refined_path):
            self.log("未找到优化文件，正在运行字幕优化...")
            script_path = os.path.join(os.path.dirname(__file__), "core", "refine_shots_by_srt.py")
            cmd = [sys.executable, '-u', script_path, self.work_dir]
            rc, success = self.runner.run(cmd)
            if not success or not os.path.exists(refined_path):
                self.log("字幕优化失败")
                messagebox.showerror("错误", "优化失败，请检查日志")
                return
            self.log("字幕优化完成")

        answer = messagebox.askyesno("替换确认",
                                     "将用优化后的文件 input_refined.json 替换原有的 input.json，并继续生成分镜和提示词。\n是否继续？")
        if not answer:
            return

        shutil.copy2(refined_path, os.path.join(self.work_dir, "input.json"))
        self.log("已用优化文件替换 input.json")

        self.log("\n========== 继续生成分镜和提示词 ==========")
        project_root = os.path.dirname(__file__)
        steps = [
            (os.path.join(project_root, "core", "auto_split_deepseek.py"), [self.work_dir]),
            (os.path.join(project_root, "core", "extract_prompts.py"), [self.work_dir])
        ]
        for script, args in steps:
            cmd = [sys.executable, script] + args
            rc, success = self.runner.run(cmd, cwd=project_root)
            if not success:
                self.log(f"步骤 {os.path.basename(script)} 失败")
                messagebox.showerror("错误", f"步骤 {os.path.basename(script)} 执行失败")
                return
        self.log("分镜和提示词生成完成")

        temp_manager = comfyui_manager.ComfyUIManager("", "")
        readable_file = temp_manager.get_latest_readable_file(self.work_dir)
        shots_info = temp_manager.get_shots_info(readable_file) if readable_file else None
        self._update_after_optimize(shots_info)

    def _update_after_optimize(self, shots_info):
        if shots_info:
            self.shots_info = shots_info
            self.standard_mode.select_edit_btn.config(state='normal')
            self.log(f"找到 {len(shots_info)} 个镜头，可点击「选择或编辑提示词」")
        self.standard_mode.run_workflow_btn.config(state='normal', text="运行工作流 (20s)")
        self.standard_mode.first_frame_btn.config(state='normal')
        self.timer.start(20000)
        messagebox.showinfo("成功", "优化并继续完成，可进行后续操作")

    def split_paragraphs(self):
        title = self.toolbar.title_entry.get().strip()
        if not title:
            messagebox.showerror("错误", "请输入故事标题")
            return
        mode = self.toolbar.text_type_var.get()
        if not mode:
            messagebox.showerror("错误", "请选择文本类型")
            return

        # 获取当前工作目录（若尚未创建，则创建）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        folder_name = f"{title}_{timestamp}"
        base_dir = config_manager.OUTPUT_ROOT_DIR
        self.work_dir = os.path.join(base_dir, folder_name)
        os.makedirs(self.work_dir, exist_ok=True)

        # 保存原始文稿
        persona = self.standard_mode.text_widgets['persona'].get("1.0", 'end-1c').strip()
        scene = self.standard_mode.text_widgets['scene'].get("1.0", 'end-1c').strip()
        story = self.standard_mode.text_widgets['story'].get("1.0", 'end-1c').strip()
        script = self.standard_mode.text_widgets['script'].get("1.0", 'end-1c').strip()

        content = ""
        if persona:
            content += "★人物设定开始★\n" + persona + "\n★人物设定结束★\n\n"
        if scene:
            content += "★场景设定开始★\n" + scene + "\n★场景设定结束★\n\n"
        if story:
            content += "★故事大纲开始★\n" + story + "\n★故事大纲结束★\n\n"
        if script:
            content += "★口播稿开始★\n" + script + "\n★口播稿结束★\n\n"

        input_filename = f"{title}_{timestamp}.txt"
        input_file_path = os.path.join(self.work_dir, input_filename)
        with open(input_file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        self.log(f"原始文稿已保存至: {input_file_path}")

        # 禁用分割段落按钮，防止重复点击
        self.standard_mode.split_btn.config(state='disabled')
        self.log("正在分割段落,每3000字大约1分钟...")

        def run_split():
            cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "core", "paragraph_splitter.py"),
                input_file_path, self.work_dir, "--mode", mode]
            rc, success = self.runner.run(cmd, cwd=os.path.dirname(__file__))
            if success:
                para_path = os.path.join(self.work_dir, "paragraphs.json")
                header_path = os.path.join(self.work_dir, "header.txt")
                if os.path.exists(para_path) and os.path.exists(header_path):
                    self.root.after(0, lambda: self.log("段落分割完成，已生成 paragraphs.json 和 header.txt"))
                    self.root.after(0, lambda: self.standard_mode.preview_btn.config(state='normal'))
                    # 可选：自动打开预览窗口
                    # self.root.after(0, self.preview_paragraphs)
                else:
                    self.root.after(0, lambda: self.log("段落分割失败，未找到输出文件"))
                    self.root.after(0, lambda: messagebox.showerror("错误", "段落分割失败，请查看日志"))
            else:
                self.root.after(0, lambda: self.log("段落分割失败"))
                self.root.after(0, lambda: messagebox.showerror("错误", "段落分割失败，请查看日志"))
            self.root.after(0, lambda: self.standard_mode.split_btn.config(state='normal'))

        thread = threading.Thread(target=run_split)
        thread.daemon = True
        thread.start()

    def preview_paragraphs(self):
        """预览并编辑段落"""
        if not self.work_dir:
            messagebox.showerror("错误", "请先分割段落")
            return
        para_path = os.path.join(self.work_dir, "paragraphs.json")
        if not os.path.exists(para_path):
            messagebox.showerror("错误", "未找到 paragraphs.json，请先分割段落")
            return

        # 创建弹窗
        win = tk.Toplevel(self.root)
        win.title("段落预览与编辑")
        win.geometry("800x600")
        win.transient(self.root)
        win.grab_set()

        # 读取段落
        with open(para_path, 'r', encoding='utf-8') as f:
            paragraphs = json.load(f)

        # 使用 Treeview 或列表显示段落，此处简单用 Text 控件
        text = scrolledtext.ScrolledText(win, wrap='word')
        text.pack(fill='both', expand=True, padx=10, pady=10)

        # 将段落用空行分隔显示
        display_text = "\n\n".join(paragraphs)
        text.insert('1.0', display_text)

        def save_paragraphs():
            new_text = text.get('1.0', 'end-1c')
            # 按空行分割段落（保留用户手动分割的空行）
            new_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', new_text) if p.strip()]
            if not new_paragraphs:
                messagebox.showerror("错误", "段落不能为空")
                return
            # 保存回文件
            with open(para_path, 'w', encoding='utf-8') as f:
                json.dump(new_paragraphs, f, ensure_ascii=False, indent=2)
            self.log(f"段落已更新，共 {len(new_paragraphs)} 个段落")
            win.destroy()
            messagebox.showinfo("成功", "段落已更新")

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="保存", command=save_paragraphs).pack(side='left', padx=5)
        tk.Button(btn_frame, text="取消", command=win.destroy).pack(side='left', padx=5)

    # def _reset_optimize_buttons(self):
        # self.standard_mode.optimize_and_continue_btn.config(state='normal', text="优化并继续")
        # self.standard_mode.apply_duration_btn.config(state='normal')

    def _run_steps_thread(self, input_filename):
        success = self.step_mgr.run_steps(self.work_dir, self.story_title, input_filename)
        if success:
            self.root.after(0, self.processing_done)

    def processing_failed(self):
        self.processing = False
        self.standard_mode.split_btn.config(state='normal')   # 原 start_btn
        self.status_label.config(text="处理失败，请查看日志")
        messagebox.showerror("错误", "处理过程中出现错误，请查看日志")

    def _handle_fatal_error(self, error_msg):
        self.processing = False
        self.timer.stop()
        self.standard_mode.split_btn.config(state='disabled')
        self.standard_mode.run_workflow_btn.config(state='disabled')
        self.standard_mode.first_frame_btn.config(state='disabled')
        self.standard_mode.select_edit_btn.config(state='disabled')
        self.standard_mode.upload_subtitle_btn.config(state='disabled')
        messagebox.showerror("致命错误", f"处理过程中发生错误，已暂停。\n\n错误详情：{error_msg}")
        self.status_label.config(text="已暂停（发生错误）")

    def processing_done(self):
        self.processing = False
        self.status_label.config(text="倒计时：20秒后自动运行工作流")
        self.standard_mode.run_workflow_btn.config(state='normal', text="运行工作流 (20s)")
        self.standard_mode.first_frame_btn.config(state='normal')
        
        # 强制重新加载镜头信息（从易读版文件）
        temp_manager = comfyui_manager.ComfyUIManager("", "")
        readable_file = temp_manager.get_latest_readable_file(self.work_dir)
        if readable_file:
            self.shots_info = temp_manager.get_shots_info(readable_file)
            if self.shots_info:
                self.standard_mode.select_edit_btn.config(state='normal')
                self.log(f"找到 {len(self.shots_info)} 个镜头，可点击「选择或编辑提示词」进行调整")
        
        if self.toolbar.mode_type_var.get() == "一键成片":
            self.simple_mode.show_countdown(20)
            if hasattr(self.simple_mode, 'edit_btn'):
                self.simple_mode.edit_btn.config(state='normal')
            if hasattr(self.simple_mode, 'run_workflow_btn'):
                self.simple_mode.run_workflow_btn.config(state='normal')
        
        self.timer.start(20000)
        
        # 刷新视频面板（延迟执行，确保文件已完全写入）
        if hasattr(self, 'video_panel'):
            self.video_panel.set_work_dir(self.work_dir)
            self.root.after(500, self.video_panel.refresh)

    def open_shot_editor(self):
        # 强制重新从易读版文件加载镜头信息，确保提示词是最新的
        if self.work_dir:
            temp_manager = comfyui_manager.ComfyUIManager("", "")
            readable_file = temp_manager.get_latest_readable_file(self.work_dir)
            if readable_file:
                new_shots_info = temp_manager.get_shots_info(readable_file)
                if new_shots_info:
                    self.shots_info = new_shots_info
                    self.log(f"已从易读版文件重新加载镜头信息，共 {len(self.shots_info)} 个镜头")
                else:
                    self.log("警告：从易读版文件加载镜头信息失败")
            else:
                self.log("警告：未找到易读版分镜文件")

        if not self.shots_info:
            messagebox.showerror("错误", "没有镜头信息，请先完成前三步或打开历史项目")
            return

        was_paused = False
        if hasattr(self, 'timer') and self.timer and not self.timer.paused:
            self.timer.pause()
            was_paused = True
            self.log("倒计时已暂停（进入镜头编辑）")
            if self.toolbar.mode_type_var.get() == "一键成片":
                self.simple_mode.set_paused()

        current_selections = None
        if self.selected_shots_ids is not None:
            id_to_index = {shot['id']: i for i, shot in enumerate(self.shots_info)}
            current_selections = [False] * len(self.shots_info)
            for sid in self.selected_shots_ids:
                if sid in id_to_index:
                    current_selections[id_to_index[sid]] = True
        else:
            current_selections = [True] * len(self.shots_info)

        editor = ShotEditorWindow(self.root, self.shots_info,
                                  existing_selections=current_selections,
                                  existing_edits=self.edited_prompts)
        self.root.wait_window(editor.win)

        if was_paused and self.timer and self.timer.remaining > 0:
            self.timer.resume()
            self.log("倒计时已恢复")
            if self.toolbar.mode_type_var.get() == "一键成片":
                self.simple_mode.show_countdown(self.timer.remaining)

        if editor.result_selections is not None:
            self.selected_shots_ids = [shot['id'] for i, shot in enumerate(self.shots_info) if editor.result_selections[i]]
            self.edited_prompts = editor.result_edits
            self.log(f"已保存选择 {len(self.selected_shots_ids)}/{len(self.shots_info)} 个镜头")
            self.status_label.config(text=f"已选择 {len(self.selected_shots_ids)}/{len(self.shots_info)} 个镜头")
        else:
            self.log("取消编辑")

    def run_workflow(self):
        mode = self.toolbar.mode_var.get()
        if not messagebox.askyesno("确认", f"当前模式为【{mode}】，是否继续生成视频？"):
            return
        # 如果是图生视频模式，调用视频面板的专用方法
        if self.toolbar.mode_var.get() == "图生视频":
            # 调用视频面板的图生视频方法
            self.video_panel.run_i2v_workflow(
                work_dir=self.work_dir,
                shots_info=self.shots_info,
                resolution=self.resolution_var.get(),
                log_callback=self.log,
                on_finish=self.workflow_done
            )
            # 禁用相关按钮
            self.standard_mode.run_workflow_btn.config(state='disabled', text="运行工作流")
            self.standard_mode.first_frame_btn.config(state='disabled')
            self.standard_mode.select_edit_btn.config(state='disabled')
            self.status_label.config(text="正在生成视频...")
            self.log("\n========== 图生视频 ==========")
            return

        # 以下是原有的文生视频逻辑（保持不变）
        if not self.shots_info:
            messagebox.showwarning("提示", "请先点击生成口播稿点击后口播稿预览窗出现内容后,再点击下方确认并生成视频,待倒计时时点击我才能进入流程。")
            return
        resolution = self.resolution_var.get()
        if not resolution:
            messagebox.showerror("错误", "请先选择分辨率")
            return
        workflow = self.workflow_var.get()
        if workflow == "WAN2.2":
            template_file = "video_wan2_2_14B_t2v.json"
        else:
            template_file = "LTX2.3文生API.json"
        template_path = os.path.join(os.path.dirname(__file__), "workflow_templates", template_file)

        self.timer.stop()
        if self.toolbar.mode_type_var.get() == "一键成片":
            self.simple_mode.hide_countdown()

        self.standard_mode.run_workflow_btn.config(state='disabled', text="运行工作流")
        self.standard_mode.first_frame_btn.config(state='disabled')
        self.standard_mode.select_edit_btn.config(state='disabled')
        if self.continue_mode and self.remaining_shots:
            selected_ids = self.remaining_shots
            self.continue_btn.config(state='disabled')
            self.log("继续模式：将生成剩余镜头")
        elif self.selected_shots_ids is not None:
            selected_ids = self.selected_shots_ids
        else:
            selected_ids = None

        self.status_label.config(text="正在生成视频...")
        self.log("\n========== 4/4: 生成视频 ==========")

        api_url = config_manager.COMFYUI_API_URL
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_folder_name = "视频"
        output_dir = os.path.join(self.work_dir, video_folder_name)
        os.makedirs(output_dir, exist_ok=True)

        def on_shot_done(shot_id):
            for cb in self.video_generation_callbacks:
                try:
                    cb(shot_id)
                except Exception as e:
                    self.log(f"视频生成回调执行失败: {e}")

        is_simple_mode = (self.toolbar.mode_type_var.get() == "一键成片")
        manager = comfyui_manager.ComfyUIManager(
            api_url=api_url,
            output_base_dir=output_dir,
            on_shot_generated=on_shot_done,
            auto_trim=is_simple_mode
        )
        manager.set_log_callback(self.log)

        def thread_func():
            try:
                success, msg = manager.run(self.story_title, self.work_dir, resolution, template_path,
                                        selected_shots=selected_ids)
                if success:
                    self.root.after(0, self.workflow_done)
                else:
                    if msg and msg.startswith("ComfyUI服务异常:"):
                        manifest_path = os.path.join(self.work_dir, "镜头清单.txt")
                        if os.path.exists(manifest_path):
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            import re
                            success_ids = set(re.findall(r'【镜头([\d-]+)】', content))
                        else:
                            success_ids = set()
                        all_shot_ids = [s['id'] for s in self.shots_info]
                        if selected_ids is not None:
                            all_shot_ids = selected_ids
                        remaining = [sid for sid in all_shot_ids if sid not in success_ids]
                        if remaining:
                            self.remaining_shots = remaining
                            self.continue_mode = True
                            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
                            self.log(f"检测到 ComfyUI 服务异常，已暂停。剩余 {len(remaining)} 个镜头待生成，请检查服务后点击「继续」按钮。")
                            self.root.after(0, lambda: self.continue_btn.config(state='normal'))
                            self.root.after(0, lambda: messagebox.showwarning("服务异常", f"ComfyUI 服务异常，已暂停生成。\n\n错误信息：{msg}\n\n请检查服务状态后点击「继续」按钮。"))
                        else:
                            self.root.after(0, lambda: messagebox.showerror("生成失败", f"视频生成失败：{msg}"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("生成失败", f"视频生成失败：{msg}"))
                    self.root.after(0, self.workflow_failed)
            except Exception as e:
                self.log(f"工作流执行异常: {e}")
                self.root.after(0, self.workflow_failed)

        thread = threading.Thread(target=thread_func)
        thread.daemon = True
        thread.start()

    def retake_single_shot(self, shot_id):
        """标准模式重试单个镜头"""
        if not self.work_dir or not self.shots_info:
            messagebox.showerror("错误", "未加载项目或镜头信息")
            return
        # 找到目标镜头
        target_shot = None
        for s in self.shots_info:
            if s['id'] == shot_id:
                target_shot = s
                break
        if not target_shot:
            messagebox.showerror("错误", f"未找到镜头 {shot_id}")
            return

        # 临时设置 selected_shots_ids 为当前镜头
        self.selected_shots_ids = [shot_id]
        self.continue_mode = False
        self.remaining_shots = None
        # 调用 run_workflow（会使用 self.selected_shots_ids）
        self.run_workflow()

    def continue_generation(self):
        if not self.work_dir or not self.remaining_shots:
            self.continue_btn.config(state='disabled')
            return
        # 重置重试选择
        self.selected_shots_ids = None
        # 刷新标准模式视频面板
        if hasattr(self, 'video_panel'):
            self.video_panel.refresh()
        self.log("手动恢复生成，继续生成剩余镜头...")
        self.run_workflow()

    def workflow_done(self):
        self.status_label.config(text="全部流程完成")
        self.log("=== 全部流程完成 ===")
        self._reset_buttons()
        self.continue_mode = False
        self.remaining_shots = None
        self.continue_btn.config(state='disabled')
        # 刷新一键成片模式的视频标签页（如果存在）
        if hasattr(self, 'simple_mode') and hasattr(self.simple_mode, 'video_tab'):
            self.simple_mode.video_tab.refresh_video_list()
        # 刷新标准模式视频面板
        if hasattr(self, 'video_panel'):
            self.video_panel.refresh()

    def workflow_failed(self):
        self.status_label.config(text="生成视频失败")
        self.log("=== 生成视频失败 ===")
        self._reset_buttons()

    def _reset_buttons(self):
        self.standard_mode.split_btn.config(state='normal')  # 原 start_btn 改为 split_btn
        self.standard_mode.run_workflow_btn.config(state='normal', text="运行工作流")
        self.standard_mode.first_frame_btn.config(state='normal')
        self.standard_mode.select_edit_btn.config(state='normal')

    def run_first_frame_generation(self):
        if not self.work_dir:
            messagebox.showerror("错误", "尚未生成工作目录")
            return
        def thread_func():
            self.log("\n========== 生成首帧提示词 ==========")
            script_path = os.path.join(os.path.dirname(__file__), "core", "generate_first_frame_prompts.py")
            cmd = [sys.executable, script_path, self.work_dir]
            rc, success = self.runner.run(cmd)
            if success:
                self.log("首帧提示词生成完成")
            else:
                self.log("首帧提示词生成失败")
        thread = threading.Thread(target=thread_func)
        thread.daemon = True
        thread.start()

    def run_video_align(self):
        if not self.work_dir:
            messagebox.showerror("错误", "尚未加载工作目录，请先打开历史项目或生成新项目。")
            return
        video_dir = filedialog.askdirectory(title="请选择视频文件所在的目录（即生成视频的文件夹）")
        if not video_dir:
            return
        def thread_func():
            from core import align_videos
            align_videos.main(self.work_dir, video_dir, self.log)
        threading.Thread(target=thread_func, daemon=True).start()

    def on_aspect_ratio_change(self, event=None):
        aspect = self.aspect_ratio_var.get()
        if aspect in ASPECT_RATIO_MAP:
            resolutions = ASPECT_RATIO_MAP[aspect]
            self.resolution_combo['values'] = resolutions
            if resolutions:
                self.resolution_var.set(resolutions[0])
            else:
                self.resolution_var.set("")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()