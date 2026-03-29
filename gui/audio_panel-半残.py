# gui/audio_panel.py
"""
音频生成面板：嵌入主应用，用于分段生成、音频生成、试听和重录。
"""

import shutil
import sys
import os
import json
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
import re

# 导入主应用的工具
from utils import config_manager
from utils.error_logger import log_error
from utils import process_runner
from core import comfyui_manager

# 导入音频模块核心函数
from core.audio_labeler import label_audio
from core.fish_tts import generate_single, extract_reference_text
from core.qwen_tts import generate_reference_audio
from utils.audio_utils import get_audio_duration, call_deepseek, FFMPEG
from core.audio.playback import PlaybackController
from core.audio.subtitle import SubtitleGenerator
from core.audio.reference import ReferenceAudioManager
from core.audio.generation import AudioGenerationController

# 尝试导入 pygame 用于播放
try:
    import pygame
    pygame.init()
    pygame.mixer.init()
    PLAYER_AVAILABLE = True
except ImportError:
    PLAYER_AVAILABLE = False

class AudioPanel(ttk.Frame):

    def _on_playback_position(self, current, total):
        self.progress_scale.set(current * 1000)
        self.time_label.config(text=f"{self._format_time(current)} / {self._format_time(total)}")

    def _on_playback_start(self, total_duration):
        """播放开始时设置进度条最大值（毫秒）"""
        self.progress_scale.config(to=total_duration * 1000)

    def _on_playback_end(self):
        self.play_pause_btn.config(text="▶ 播放")
        self.progress_scale.set(0)
        self.time_label.config(text="00:00 / 00:00")

    def play_audio(self, filepath):
        if not filepath or not os.path.exists(filepath):
            self.log(f"音频文件不存在: {filepath}")
            return
        if self.playback.play(filepath):
            self.current_playing = filepath
            self.current_label.config(text=os.path.basename(filepath))
            self.play_pause_btn.config(state='normal', text="⏸ 暂停")
        else:
            self.log("播放失败，请检查 pygame 是否正常")
            
    def __init__(self, parent, work_dir=None, app=None, log_callback=None):
        super().__init__(parent)
        self.work_dir = work_dir
        self.app = app
        self.log_callback = log_callback
        self.raw_script_path = None
        self.ref_audio_filename = None
        self.ref_text = None
        self.segments = []
        self.retake_queue = []
        self.paragraphs = []
        self.retake_thread = None
        self.running = False
        self.stop_requested = False
        self.next_retake_index = 0
        self.reminder_window = None
        self.language_var = tk.StringVar(value="auto")
        self._work_dir_set = None
        self._loaded = False
        self.has_labeled_segments = False
        self.retake_thread_running = True
        # self.retake_thread = threading.Thread(target=self._process_retake_queue, daemon=True)
        # self.retake_thread.start()

        # 播放器相关
        self.player_available = PLAYER_AVAILABLE
        self.current_playing = None
        self.current_duration = 0
        self.gen_controller = None

        self.playback = PlaybackController(
            on_play_start=self._on_playback_start,
            on_position_update=self._on_playback_position,
            on_playback_end=self._on_playback_end
        )

        self.create_widgets()

    def set_script(self, script):
        """设置口播稿文本（用于AI生成参考音频等）"""
        self.script_text = script
        self.log("已设置口播稿文本")

    def load_segments_from_labeled_text(self, work_dir):
        """从工作目录的 labeled_text.txt 加载已有分段，并关联已生成的音频文件"""
        labeled_path = os.path.join(work_dir, "labeled_text.txt")
        if not os.path.exists(labeled_path):
            return False

        with open(labeled_path, 'r', encoding='utf-8') as f:
            content = f.read()

        raw_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
        print(f"[DEBUG] raw_paragraphs count: {len(raw_paragraphs)}")

        if not raw_paragraphs:
            return False

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.segments = []

        for idx, para in enumerate(raw_paragraphs, start=1):
            seg = {
                'index': idx,
                'text': para,
                'clean_text': re.sub(r'\[[^\]]*\]', '', para).strip(),
                'status_var': tk.StringVar(value="待生成"),
                'play_btn': None,
                'retake_btn': None,
                'confirm_btn': None,
                'audio_file': None,
                'duration': None,
                'confirmed': False
            }
            seg = self.add_segment_row(idx, seg)
            self.segments.append(seg)

        for seg in self.segments:
            idx = seg['index']
            audio_path = os.path.join(work_dir, f"segment_{idx:03d}.mp3")
            if os.path.exists(audio_path):
                try:
                    duration = get_audio_duration(audio_path)
                    seg['audio_file'] = audio_path
                    seg['duration'] = duration
                    seg['status_var'].set("已生成")
                    seg['play_btn'].config(state='normal', command=lambda p=audio_path: self.play_audio(p))
                    seg['retake_btn'].config(state='normal', command=lambda i=idx: self.request_retake(i))
                    seg['confirm_btn'].config(state='normal', command=lambda i=idx: self.confirm_segment(i))
                    self.log(f"已自动关联片段 {idx} 的音频文件")
                except Exception as e:
                    self.log(f"关联片段 {idx} 音频文件失败: {e}")

        self.log(f"已从 labeled_text.txt 加载 {len(self.segments)} 个段落")
        self.has_labeled_segments = True
        self.gen_seg_btn.config(text="重新润色")
        self.script_text = "\n\n".join([seg["text"] for seg in self.segments])
        self.log("已加载口播稿文本，可用于AI生成参考音频")

        final_audio = os.path.join(work_dir, "final_audio.mp3")
        if os.path.exists(final_audio):
            self.final_audio_status.set("已生成")
            self.final_play_btn.config(state='normal')
        else:
            self.final_audio_status.set("未生成")
            self.final_play_btn.config(state='disabled')

        for seg in self.segments:
            if seg.get('audio_file') and seg.get('duration'):
                self.gen_controller.sync_existing_segment(seg['index'], seg['audio_file'], seg['duration'])

        return True
    
    def _on_generation_progress(self, completed, total):
        if total > 0:
            percent = int(completed / total * 100)
            self.app.set_progress(percent)
            self.app.status_label.config(text=f"音频生成进度: {completed}/{total}")

    def _on_segment_generated(self, index, success, audio_path, duration):
        self.after(0, lambda: self._update_segment_ui(index, success, audio_path, duration))

    def _update_segment_ui(self, index, success, audio_path, duration):
        for seg in self.segments:
            if seg['index'] == index:
                if success:
                    seg['audio_file'] = audio_path
                    seg['duration'] = duration
                    seg['status_var'].set("已生成")
                    seg['play_btn'].config(state='normal', command=lambda p=audio_path: self.play_audio(p))
                    seg['retake_btn'].config(state='normal', command=lambda i=index: self.request_retake(i))
                    seg['confirm_btn'].config(state='normal', command=lambda i=index: self.confirm_segment(i))
                    self.log(f"片段 {index} 生成完成，时长 {duration:.2f}s")
                    self.show_reminder(index)
                else:
                    seg['status_var'].set("生成失败")
                    self.log(f"片段 {index} 生成失败")
                break

    def auto_align_duration(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        para_path = os.path.join(self.work_dir, "paragraphs.json")
        srt_path = os.path.join(self.work_dir, "input.srt")
        if not os.path.exists(para_path) or not os.path.exists(srt_path):
            messagebox.showerror("错误", "缺少 paragraphs.json 或 input.srt，请确保已生成字幕")
            return

        self.align_btn.config(state='disabled', text="生成中...")
        self.log("开始生成视频提示词...")

        def run_cmd(cmd, cwd=None):
            import subprocess
            import threading
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            def read_output():
                try:
                    for line in iter(proc.stdout.readline, ''):
                        if not line:
                            break
                        line = line.rstrip()
                        if line:
                            print(line)
                            self.log(line)
                except Exception as e:
                    self.log(f"读取输出异常: {e}")
                finally:
                    proc.stdout.close()
            t = threading.Thread(target=read_output, daemon=True)
            t.start()
            proc.wait()
            t.join(timeout=1)
            return proc.returncode, proc.returncode == 0

        def run():
            project_root = os.path.dirname(os.path.dirname(__file__))
            cmd2 = [sys.executable, os.path.join(project_root, "core", "refine_shots_by_srt.py"), self.work_dir]
            rc2, success2 = run_cmd(cmd2, cwd=project_root)
            if not success2:
                self.app.root.after(0, lambda: self.log("模块2执行失败"))
                self.app.root.after(0, lambda: self.align_btn.config(state='normal', text="生成视频提示词"))
                return
            cmd3 = [sys.executable, os.path.join(project_root, "core", "fill_shot_attributes.py"),
                    os.path.join(self.work_dir, "paragraphs.json"),
                    os.path.join(self.work_dir, "shots_base.txt"),
                    os.path.join(self.work_dir, "shots.txt")]
            rc3, success3 = run_cmd(cmd3, cwd=project_root)
            if not success3:
                self.app.root.after(0, lambda: self.log("模块3执行失败"))
                self.app.root.after(0, lambda: self.align_btn.config(state='normal', text="生成视频提示词"))
                return
            self.log("开始生成高质量视频提示词（auto_split）...")
            cmd4 = [sys.executable, os.path.join(project_root, "core", "auto_split_deepseek.py"), self.work_dir]
            rc4, success4 = run_cmd(cmd4, cwd=project_root)
            if not success4:
                self.app.root.after(0, lambda: self.log("auto_split_deepseek.py 执行失败"))
                self.app.root.after(0, lambda: self.align_btn.config(state='normal', text="生成视频提示词"))
                return
            self.log("开始提取并翻译提示词...")
            cmd5 = [sys.executable, os.path.join(project_root, "core", "extract_prompts.py"), self.work_dir]
            rc5, success5 = run_cmd(cmd5, cwd=project_root)
            if not success5:
                self.app.root.after(0, lambda: self.log("extract_prompts.py 执行失败"))
                self.app.root.after(0, lambda: self.align_btn.config(state='normal', text="生成视频提示词"))
                return
            self.app.root.after(0, lambda: self.log("视频提示词生成完成，可在视频模块中查看"))
            self.app.root.after(0, self._refresh_shots_info)
            self.app.root.after(0, lambda: self.align_btn.config(state='normal', text="生成视频提示词"))

        threading.Thread(target=run, daemon=True).start()

    def _refresh_shots_info(self):
        shots_txt_path = os.path.join(self.work_dir, "shots.txt")
        if os.path.exists(shots_txt_path):
            self.app.shots_info = self.app._parse_shots_from_txt(shots_txt_path)
            if self.app.shots_info:
                self.app.standard_mode.select_edit_btn.config(state='normal')
                self.app.log(f"找到 {len(self.app.shots_info)} 个镜头，可点击「选择或编辑提示词」进行调整")
                return
        from core import comfyui_manager
        temp_manager = comfyui_manager.ComfyUIManager("", "")
        readable_file = temp_manager.get_latest_readable_file(self.work_dir)
        if readable_file:
            self.app.shots_info = temp_manager.get_shots_info(readable_file)
            if self.app.shots_info:
                self.app.standard_mode.select_edit_btn.config(state='normal')
                self.app.log(f"找到 {len(self.app.shots_info)} 个镜头，可点击「选择或编辑提示词」进行调整")
            else:
                self.app.shots_info = None
                self.app.standard_mode.select_edit_btn.config(state='disabled')
        else:
            self.app.shots_info = None
            self.app.standard_mode.select_edit_btn.config(state='disabled')

    def log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
        else:
            timestamp = time.strftime("[%H:%M:%S] ")
            print(timestamp + msg)

    def set_work_dir(self, work_dir):
        if self.work_dir == work_dir:
            print("[DEBUG] Already set, skipping")
            return
        self.work_dir = work_dir

        self.subtitle_generator = SubtitleGenerator(work_dir, log_callback=self.log)
        self.reference_manager = ReferenceAudioManager(work_dir, log_callback=self.log)
        self.reference_manager.on_play_requested = self.play_audio
        self.ref_audio_path.set(self.reference_manager.get_ref_audio_path())
        self.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
        self.ref_text = self.reference_manager.get_ref_text()

        self.gen_controller = AudioGenerationController(
            work_dir=self.work_dir,
            ref_audio_filename=self.reference_manager.get_ref_audio_filename(),
            ref_text=self.reference_manager.get_ref_text(),
            language=self.language_var.get(),
            log_callback=self.log
        )
        self.gen_controller.set_progress_callback(self._on_generation_progress)
        self.gen_controller.start()

        if self.load_segments_from_labeled_text(work_dir):
            self.log("已从历史项目加载已有分段，无需重新润色")
        else:
            self.load_paragraphs(work_dir)
            self.log("已加载原始段落，可点击「段落自动润色」生成分段")

        cache_path = os.path.join(work_dir, "reference_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                self.ref_audio_filename = cache.get("audio_filename")
                self.ref_text = cache.get("reference_text")
                if self.ref_audio_filename and self.ref_text:
                    self.log("已从缓存加载参考音频信息")
            except Exception as e:
                self.log(f"加载参考缓存失败: {e}")

    def load_paragraphs(self, work_dir):
        para_path = os.path.join(work_dir, "paragraphs.json")
        if not os.path.exists(para_path):
            self.log("未找到 paragraphs.json，请先执行段落分割")
            return False

        with open(para_path, 'r', encoding='utf-8') as f:
            self.paragraphs = json.load(f)

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.segments = []

        for idx, para_text in enumerate(self.paragraphs, start=1):
            seg = {
                'index': idx,
                'text': para_text,
                'clean_text': re.sub(r'\[[^\]]*\]', '', para_text).strip(),
                'status_var': tk.StringVar(value="待生成"),
                'play_btn': None,
                'retake_btn': None,
                'confirm_btn': None,
                'audio_file': None,
                'duration': None,
                'confirmed': False
            }
            seg = self.add_segment_row(idx, seg)
            self.segments.append(seg)

        self.log(f"已加载 {len(self.paragraphs)} 个段落")
        return True

    def generate_subtitle(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        final_audio = os.path.join(self.work_dir, "final_audio.mp3")
        if not os.path.exists(final_audio):
            messagebox.showerror("错误", "未找到最终音频文件，请先生成音频")
            return
        self.generate_subtitle_btn.config(state='disabled', text="生成中...")
        self.subtitle_generator.generate(final_audio, self._on_subtitle_done)

    def _on_subtitle_done(self, success, srt_path):
        self.generate_subtitle_btn.config(state='normal', text="生成字幕")
        if success:
            self.log("字幕生成成功")
            self.log(f"字幕文件已保存至 {srt_path}")
            if hasattr(self, 'on_subtitle_generated'):
                self.on_subtitle_generated(srt_path)
        else:
            self.log("字幕生成失败，请检查日志")
            messagebox.showerror("错误", "字幕生成失败，请查看日志")

    def create_widgets(self):
        control_frame = ttk.LabelFrame(self, text="音频生成控制", padding=5)
        control_frame.pack(fill='x', padx=5, pady=5)

        row1 = ttk.Frame(control_frame)
        row1.pack(fill='x', pady=2)
        ttk.Label(row1, text="参考音频:").pack(side='left', padx=5)
        self.upload_btn = ttk.Button(row1, text="上传本地", command=self.upload_ref_audio)
        self.upload_btn.pack(side='left', padx=2)
        self.ref_audio_path = tk.StringVar()
        ttk.Entry(row1, textvariable=self.ref_audio_path, width=40).pack(side='left', fill='x', expand=True, padx=5)
        self.ai_gen_btn = ttk.Button(row1, text="AI生成", command=self.ai_generate_audio)
        self.ai_gen_btn.pack(side='left', padx=2)

        row2 = ttk.Frame(control_frame)
        row2.pack(fill='x', pady=5)
        self.gen_seg_btn = ttk.Button(row2, text="段落自动润色", command=self.generate_segments_manual)
        self.gen_seg_btn.pack(side='left', padx=2)
        self.start_btn = ttk.Button(row2, text="开始生成音频", command=self.start_generation)
        self.start_btn.pack(side='left', padx=2)
        self.stop_btn = ttk.Button(row2, text="停止生成音频", command=self.stop_generation, state='disabled')
        self.stop_btn.pack(side='left', padx=2)
        self.align_btn = ttk.Button(row2, text="生成视频提示词", command=self.auto_align_duration)
        self.align_btn.pack(side='left', padx=2)
        self.advanced_btn = ttk.Button(row2, text="▼ 高级选项", command=self.show_advanced_dialog)
        self.advanced_btn.pack(side='right', padx=5)

        list_frame = ttk.LabelFrame(self, text="段落列表", padding=5)
        list_frame.pack(side='top', fill='both', expand=True, padx=5, pady=5)

        final_audio_frame = ttk.Frame(list_frame)
        final_audio_frame.pack(fill='x', pady=2)
        ttk.Label(final_audio_frame, text="最终", width=4).pack(side='left')
        ttk.Label(final_audio_frame, text="合并后的完整音频", width=60).pack(side='left', padx=5)
        self.final_audio_status = tk.StringVar(value="未生成")
        ttk.Label(final_audio_frame, textvariable=self.final_audio_status, width=10).pack(side='left')
        self.final_play_btn = ttk.Button(final_audio_frame, text="播放", command=self.play_final_audio, state='disabled')
        self.final_play_btn.pack(side='left', padx=2)
        ttk.Button(final_audio_frame, text="重录", state='disabled').pack(side='left', padx=2)
        ttk.Button(final_audio_frame, text="确认", state='disabled').pack(side='left', padx=2)

        self.canvas = tk.Canvas(list_frame, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.retake_frame = ttk.LabelFrame(self, text="重录队列", padding=5)
        self.retake_frame.pack(side='top', fill='x', padx=5, pady=5)
        self.retake_toggle_btn = ttk.Button(self.retake_frame, text="▲ 折叠", command=self.toggle_retake_queue, width=6)
        self.retake_toggle_btn.pack(anchor='e', padx=5, pady=2)

        self.retake_canvas = tk.Canvas(self.retake_frame, borderwidth=0, highlightthickness=0, height=150)
        retake_scrollbar = ttk.Scrollbar(self.retake_frame, orient="vertical", command=self.retake_canvas.yview)
        self.retake_scrollable = ttk.Frame(self.retake_canvas)

        self.retake_scrollable.bind("<Configure>", lambda e: self.retake_canvas.configure(scrollregion=self.retake_canvas.bbox("all")))
        self.retake_canvas.create_window((0, 0), window=self.retake_scrollable, anchor="nw")
        self.retake_canvas.configure(yscrollcommand=retake_scrollbar.set)

        self.retake_canvas.pack(side="left", fill="both", expand=True)
        retake_scrollbar.pack(side="right", fill="y")
        self.retake_canvas_visible = True

        control_frame2 = ttk.LabelFrame(self, text="播放控制", padding=5)
        control_frame2.pack(side='bottom', fill='x', padx=5, pady=5)

        self.current_label = ttk.Label(control_frame2, text="无", width=30, anchor='w')
        self.current_label.pack(side='left', padx=5)

        self.progress_scale = ttk.Scale(control_frame2, from_=0, to=100, orient='horizontal', length=300)
        self.progress_scale.pack(side='left', fill='x', expand=True, padx=5)
        self.progress_scale.bind("<ButtonRelease-1>", self._on_scale_release)

        self.time_label = ttk.Label(control_frame2, text="00:00 / 00:00", width=15)
        self.time_label.pack(side='left', padx=5)

        self.play_pause_btn = ttk.Button(control_frame2, text="▶ 播放", command=self.toggle_play_pause, state='disabled')
        self.play_pause_btn.pack(side='left', padx=2)
        self.generate_subtitle_btn = ttk.Button(control_frame2, text="生成字幕", command=self.generate_subtitle)
        self.generate_subtitle_btn.pack(side='left', padx=5)

        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self._on_mousewheel = _on_mousewheel
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)

    def play_final_audio(self):
        final_audio_path = os.path.join(self.work_dir, "final_audio.mp3")
        if not os.path.exists(final_audio_path):
            self.log("最终音频文件不存在")
            return
        self.play_audio(final_audio_path)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def show_advanced_dialog(self):
        win = tk.Toplevel(self)
        win.title("高级选项")
        win.geometry("400x200")
        win.transient(self)
        win.grab_set()
        win.update_idletasks()
        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        parent_w = self.winfo_width()
        parent_h = self.winfo_height()
        win_w = win.winfo_reqwidth()
        win_h = win.winfo_reqheight()
        x = parent_x + (parent_w // 2) - (win_w // 2)
        y = parent_y + (parent_h // 2) - (win_h // 2)
        win.geometry(f"+{x}+{y}")
        ttk.Label(win, text="语言（ISO 代码）:").pack(anchor='w', padx=10, pady=5)
        common_langs = ["auto", "zh", "en", "ja", "ko", "es", "pt", "ar", "ru", "fr", "de"]
        lang_combo = ttk.Combobox(win, textvariable=self.language_var, values=common_langs, width=15)
        lang_combo.pack(padx=10, pady=5, fill='x')
        ttk.Label(win, text="提示：支持 80+ 种语言，可手动输入其他 ISO 代码",
                foreground='gray', font=('微软雅黑', 8)).pack(pady=2)
        ttk.Label(win, text="常用代码: zh/en/ja/ko/es/pt/ar/ru/fr/de/...",
                foreground='gray', font=('微软雅黑', 8)).pack(pady=2)
        ttk.Label(win, text="（auto 自动检测，通常无需修改）", foreground='gray').pack(pady=5)
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=10)

    def toggle_retake_queue(self):
        if self.retake_canvas_visible:
            self.retake_canvas.pack_forget()
            self.retake_toggle_btn.config(text="▼ 展开")
            self.retake_canvas_visible = False
        else:
            self.retake_canvas.pack(side="left", fill="both", expand=True)
            self.retake_toggle_btn.config(text="▲ 折叠")
            self.retake_canvas_visible = True

    def upload_ref_audio(self):
        if not self.reference_manager:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        self.reference_manager.upload_local()
        self.ref_audio_path.set(self.reference_manager.get_ref_audio_path())
        self.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
        self.ref_text = self.reference_manager.get_ref_text()

    def ai_generate_audio(self):
        """弹出AI生成参考音频窗口"""
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        self.reference_manager.ai_generate(parent_window=self)
        # 窗口关闭后，强制同步参考音频路径到界面
        path = self.reference_manager.get_ref_audio_path()
        if path:
            self.ref_audio_path.set(path)
            self.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
            self.ref_text = self.reference_manager.get_ref_text()
            self.log(f"已同步参考音频: {path}")
        else:
            self.log("未获取到参考音频路径")

    def open_tts_tutorial(self):
        win = tk.Toplevel(self)
        win.title("Qwen3-TTS 声音设计参考")
        win.geometry("800x600")
        win.transient(self)
        win.grab_set()
        text_widget = scrolledtext.ScrolledText(win, wrap='word', font=('微软雅黑', 10))
        text_widget.pack(fill='both', expand=True)
        text_widget.insert('1.0', TUTORIAL_CONTENT)
        text_widget.config(state='disabled')
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=5)

    def generate_segments_manual(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        if not self.paragraphs and not self.has_labeled_segments:
            messagebox.showerror("错误", "未加载段落，请先执行段落分割")
            return
        if self.has_labeled_segments:
            answer = messagebox.askyesno("确认", "已有润色后的段落，重新润色将覆盖现有音频片段，是否继续？\n")
            if not answer:
                return
            labeled_path = os.path.join(self.work_dir, "labeled_text.txt")
            json_path = os.path.join(self.work_dir, "segments_info.json")
            if os.path.exists(labeled_path):
                os.remove(labeled_path)
            if os.path.exists(json_path):
                os.remove(json_path)
            self.has_labeled_segments = False
            self.gen_seg_btn.config(text="段落自动润色")
            self.load_paragraphs(self.work_dir)
        self.log("正在对段落进行润色和切分，请稍候...")
        threading.Thread(target=self._generate_segments_async, daemon=True).start()

    def _generate_segments_async(self):
        try:
            full_text = "\n\n".join(self.paragraphs)
            temp_script_path = os.path.join(self.work_dir, "temp_script.txt")
            with open(temp_script_path, 'w', encoding='utf-8') as f:
                f.write(full_text)
            from core.audio_labeler import label_audio
            segments = label_audio(self.work_dir, temp_script_path)
            if segments:
                self.app.root.after(0, self.load_segments_from_json)
                self.app.root.after(0, lambda: self.log("段落润色完成"))
                self.app.root.after(0, lambda: setattr(self, 'has_labeled_segments', True))
                self.app.root.after(0, lambda: self.gen_seg_btn.config(text="重新润色"))
            else:
                self.app.root.after(0, lambda: self.log("段落润色失败"))
        except Exception as e:
            self.app.root.after(0, lambda: self.log(f"段落润色异常: {e}"))

    def load_segments_from_json(self):
        json_path = os.path.join(self.work_dir, "segments_info.json")
        if not os.path.exists(json_path):
            self.log("未找到 segments_info.json")
            return
        with open(json_path, 'r', encoding='utf-8') as f:
            segments = json.load(f)
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.segments = []
        for idx, seg in enumerate(segments, start=1):
            seg.setdefault('index', idx)
            seg.setdefault('text', seg.get('text', ''))
            seg.setdefault('clean_text', re.sub(r'\[[^\]]*\]', '', seg['text']).strip())
            seg.setdefault('status_var', tk.StringVar(value="待生成"))
            seg.setdefault('play_btn', None)
            seg.setdefault('retake_btn', None)
            seg.setdefault('confirm_btn', None)
            seg.setdefault('audio_file', None)
            seg.setdefault('duration', None)
            seg.setdefault('confirmed', False)
            seg = self.add_segment_row(idx, seg)
            self.segments.append(seg)
        self.log(f"已加载 {len(segments)} 个段落")
        for seg in self.segments:
            idx = seg['index']
            audio_path = os.path.join(self.work_dir, f"segment_{idx:03d}.mp3").replace('\\', '/')
            if os.path.exists(audio_path):
                try:
                    duration = get_audio_duration(audio_path)
                    seg['audio_file'] = audio_path
                    seg['duration'] = duration
                    seg['status_var'].set("已生成")
                    seg['play_btn'].config(state='normal', command=lambda p=audio_path: self.play_audio(p))
                    seg['retake_btn'].config(state='normal', command=lambda i=idx: self.request_retake(i))
                    seg['confirm_btn'].config(state='normal', command=lambda i=idx: self.confirm_segment(i))
                    self.log(f"已自动关联片段 {idx} 的音频文件")
                except Exception as e:
                    self.log(f"关联片段 {idx} 音频文件失败: {e}")
        self.next_retake_index = len(segments) + 1

    def add_segment_row(self, idx, seg):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill='x', pady=2)
        ttk.Label(row_frame, text=str(idx), width=4).pack(side='left')
        text_preview = seg['text'][:60] + '...' if len(seg['text']) > 60 else seg['text']
        preview_label = ttk.Label(row_frame, text=text_preview, width=60, wraplength=400)
        preview_label.pack(side='left', padx=5)
        status_var = tk.StringVar(value=seg.get('status', "待生成"))
        ttk.Label(row_frame, textvariable=status_var, width=10).pack(side='left')
        play_btn = ttk.Button(row_frame, text="播放", state='disabled')
        play_btn.pack(side='left', padx=2)
        retake_btn = ttk.Button(row_frame, text="重录", state='disabled')
        retake_btn.pack(side='left', padx=2)
        confirm_btn = ttk.Button(row_frame, text="确认", state='disabled')
        confirm_btn.pack(side='left', padx=2)
        seg['row_frame'] = row_frame
        seg['status_var'] = status_var
        seg['play_btn'] = play_btn
        seg['retake_btn'] = retake_btn
        seg['confirm_btn'] = confirm_btn
        seg['preview_label'] = preview_label
        seg['confirmed'] = False
        seg['audio_file'] = None
        seg['duration'] = None
        seg['clean_text'] = re.sub(r'\[[^\]]*\]', '', seg['text']).strip()
        row_frame.bind("<MouseWheel>", self._on_mousewheel)
        for child in row_frame.winfo_children():
            child.bind("<MouseWheel>", self._on_mousewheel)
        return seg

    def start_generation(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        if not self.segments:
            messagebox.showerror("错误", "请先生成分段")
            return
        if not self.ref_audio_path.get():
            messagebox.showerror("错误", "请先选择或生成参考音频")
            return
        if self.running:
            self.log("已有生成任务在运行")
            return
        if self.gen_controller:
            self.gen_controller.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
            self.gen_controller.ref_text = self.reference_manager.get_ref_text()
            self.gen_controller.language = self.language_var.get()
        else:
            self.log("错误：控制器未初始化")
            return
        self.running = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.log("开始添加生成任务...")
        for seg in self.segments:
            if seg.get('confirmed'):
                continue
            if seg.get('audio_file') and seg.get('duration'):
                self.gen_controller.sync_existing_segment(seg['index'], seg['audio_file'], seg['duration'])
                continue
            self.gen_controller.add_task(seg['index'], seg['text'], self._on_segment_generated)
        self.log("任务已添加，等待生成...")

    def reset_generation_state(self):
        self.running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

    def _process_retake_queue(self):
        while self.retake_thread_running:
            if not self.retake_queue:
                time.sleep(0.5)
                continue
            item = self.retake_queue.pop(0)
            self.log(f"开始重录片段 {item['original_index']} ...")
            if item['new_text'] is not None:
                final_text = item['new_text']
            else:
                final_text = self.ai_modify_text(item['original_text'], item['problem_desc'])
            retake_idx = self.next_retake_index
            self.next_retake_index += 1
            audio_path = generate_single(
                text=final_text,
                index=retake_idx,
                output_dir=self.work_dir,
                ref_audio_filename=self.ref_audio_filename,
                ref_text=self.ref_text,
                language=self.language_var.get()
            )
            if audio_path:
                duration = get_audio_duration(audio_path)
                self.after(0, lambda: self.add_retake_item(item, audio_path, duration, final_text, retake_idx))
            else:
                self.log(f"重录失败: {item['original_text'][:30]}...")
                row_frame = item.get('row_frame')
                if row_frame and hasattr(row_frame, 'pending_info'):
                    row_frame.pending_info['status_label'].config(text="失败", foreground='red')

    def ai_modify_text(self, original_text, problem_desc):
        prompt = f"""
原始文本（带 Fish S2 标签）：
{original_text}

用户反馈：{problem_desc}

请根据反馈修改文本，保持原有结构（仍包含 `[标签]` 和 `[inhale]`），只修改语气、语速、情感等相关内容。输出修改后的文本。
"""
        try:
            new_text = call_deepseek(prompt, temperature=0.7)
            return new_text
        except Exception as e:
            self.log(f"AI修改文本失败: {e}")
            return original_text

    def add_retake_item(self, item, audio_path, duration, new_text, retake_idx):
        self.log(f"重录完成（序号{retake_idx}）: {new_text[:30]}... 时长 {duration:.2f}s")
        row_frame = item.get('row_frame')
        if row_frame and hasattr(row_frame, 'pending_info'):
            info = row_frame.pending_info
            preview = new_text[:30] + '...' if len(new_text) > 30 else new_text
            info['label_desc'].config(text=preview)
            info['status_label'].config(text="已生成", foreground='green')
            info['play_btn'].config(state='normal', command=lambda p=audio_path: self.play_audio(p))
            info['confirm_btn'].config(state='normal', command=lambda: self.confirm_retake(item, audio_path, duration, new_text, retake_idx, row_frame))
            row_frame.retake_result = {
                'audio_path': audio_path,
                'duration': duration,
                'new_text': new_text,
                'retake_idx': retake_idx
            }
        else:
            self._add_retake_row(item, audio_path, duration, new_text, retake_idx)

    def _add_retake_row(self, item, audio_path, duration, new_text, retake_idx):
        self.log(f"重录完成（序号{retake_idx}）: {new_text[:30]}... 时长 {duration:.2f}s")
        row_frame = ttk.Frame(self.retake_scrollable)
        row_frame.pack(fill='x', pady=2)
        ttk.Label(row_frame, text=f"原片段{item['original_index']}", width=12).pack(side='left')
        problem = item['problem_desc'][:30] + '...' if len(item['problem_desc']) > 30 else item['problem_desc']
        ttk.Label(row_frame, text=problem, width=40, wraplength=300).pack(side='left', padx=5)
        play_btn = ttk.Button(row_frame, text="播放", command=lambda: self.play_audio(audio_path))
        play_btn.pack(side='left', padx=2)
        confirm_btn = ttk.Button(row_frame, text="确认", command=lambda: self.confirm_retake(item, audio_path, duration, new_text, retake_idx, row_frame))
        confirm_btn.pack(side='left', padx=2)
        row_frame.retake_info = {
            'item': item,
            'audio_path': audio_path,
            'duration': duration,
            'new_text': new_text,
            'retake_idx': retake_idx
        }

    def update_segment_status(self, idx, status):
        for seg in self.segments:
            if seg.get('index') == idx:
                seg['status_var'].set(status)
                break

    def on_segment_generated(self, idx, audio_path, duration):
        for seg in self.segments:
            if seg.get('index') == idx:
                seg['audio_file'] = audio_path
                seg['duration'] = duration
                seg['status_var'].set("已生成")
                seg['play_btn'].config(state='normal', command=lambda p=audio_path: self.play_audio(p))
                seg['retake_btn'].config(state='normal', command=lambda i=idx: self.request_retake(i))
                seg['confirm_btn'].config(state='normal', command=lambda i=idx: self.confirm_segment(i))
                break
        self.log(f"片段 {idx} 生成完成，时长 {duration:.2f}s")
        self.show_reminder(idx)

    def on_segment_failed(self, idx):
        for seg in self.segments:
            if seg.get('index') == idx:
                seg['status_var'].set("生成失败")
                break
        self.log(f"片段 {idx} 生成失败")

    def show_reminder(self, idx):
        if self.reminder_window is not None:
            try:
                self.reminder_window.destroy()
            except:
                pass
            self.reminder_window = None
        win = tk.Toplevel(self)
        win.title("提醒")
        win.geometry("400x150")
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - 400) // 2
        y = (screen_height - 150) // 2
        win.geometry(f"+{x}+{y}")
        win.transient(self)
        win.attributes('-topmost', True)
        try:
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
        except:
            pass
        label = ttk.Label(win, text=f"片段 {idx} 已生成，请到段落列表中试听并确认。")
        label.pack(pady=20)
        def close():
            win.destroy()
            self.reminder_window = None
        ttk.Button(win, text="知道了", command=close).pack(pady=10)
        win.protocol("WM_DELETE_WINDOW", close)
        self.reminder_window = win

    def _on_scale_release(self, event):
        if not self.current_playing:
            return
        pos_ms = self.progress_scale.get()
        pos_sec = pos_ms / 1000.0
        self.playback.seek(pos_sec)

    def _format_time(self, seconds):
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def toggle_play_pause(self):
        if not self.current_playing:
            return
        if self.playback.is_paused:
            self.playback.resume()
            self.play_pause_btn.config(text="⏸ 暂停")
        else:
            self.playback.pause()
            self.play_pause_btn.config(text="▶ 播放")

    def stop_playback(self):
        self.playback.stop()
        self.current_playing = None
        self.current_label.config(text="无")
        self.play_pause_btn.config(text="▶ 播放")
        self.progress_scale.set(0)
        self.time_label.config(text="00:00 / 00:00")

    def request_retake(self, idx):
        for seg in self.segments:
            if seg.get('index') == idx:
                self._show_retake_dialog(seg['index'], seg)
                break

    def _show_retake_dialog(self, idx, seg):
        if hasattr(self, '_retake_dialog_win') and self._retake_dialog_win is not None:
            try:
                self._retake_dialog_win.destroy()
            except:
                pass
        win = tk.Toplevel(self)
        win.title("重录片段")
        win.geometry("700x600")
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - 700) // 2
        y = (screen_height - 600) // 2
        win.geometry(f"+{x}+{y}")
        win.transient(self)
        win.grab_set()
        self._retake_dialog_win = win
        ttk.Label(win, text="带标签的原文（可直接修改）:").pack(anchor='w', padx=10, pady=5)
        text_edit = scrolledtext.ScrolledText(win, height=12, wrap='word')
        text_edit.insert('1.0', seg['text'])
        text_edit.pack(fill='both', expand=True, padx=10, pady=5)
        ttk.Label(win, text="修改意见（如“语速太慢”、“语气不够激昂”）:").pack(anchor='w', padx=10, pady=5)
        problem_entry = ttk.Entry(win, width=60)
        problem_entry.pack(fill='x', padx=10, pady=5)
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        def submit():
            new_text = text_edit.get('1.0', 'end-1c').strip()
            problem = problem_entry.get().strip()
            if new_text == seg['text'] and not problem:
                messagebox.showwarning("提示", "请修改原文或输入修改意见")
                return
            win.destroy()
            self._retake_dialog_win = None
            final_text = new_text if new_text != seg['text'] else None
            self._add_retake_pending_item(seg['index'], final_text, problem)
        ttk.Button(btn_frame, text="提交", command=submit).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: (win.destroy(), setattr(self, '_retake_dialog_win', None))).pack(side='left', padx=5)

    def _add_retake_pending_item(self, original_index, final_text, problem_desc):
        row_frame = ttk.Frame(self.retake_scrollable)
        row_frame.pack(fill='x', pady=2)
        ttk.Label(row_frame, text=f"原片段{original_index}", width=12).pack(side='left')
        label_desc = ttk.Label(row_frame, text="生成中...", width=40, wraplength=300)
        label_desc.pack(side='left', padx=5)
        play_btn = ttk.Button(row_frame, text="播放", state='disabled')
        play_btn.pack(side='left', padx=2)
        confirm_btn = ttk.Button(row_frame, text="确认", state='disabled')
        confirm_btn.pack(side='left', padx=2)
        status_label = ttk.Label(row_frame, text="生成中...", foreground='blue')
        status_label.pack(side='left', padx=5)
        row_frame.pending_info = {
            'original_index': original_index,
            'final_text': final_text,
            'problem_desc': problem_desc,
            'status_label': status_label,
            'play_btn': play_btn,
            'confirm_btn': confirm_btn,
            'label_desc': label_desc
        }
        self.retake_queue.append({
            'original_index': original_index,
            'original_text': self.segments[original_index-1]['text'],
            'problem_desc': problem_desc,
            'new_text': final_text,
            'row_frame': row_frame
        })

    def confirm_segment(self, idx):
        for seg in self.segments:
            if seg.get('index') == idx:
                seg['confirmed'] = True
                seg['status_var'].set("已确认")
                seg['retake_btn'].config(state='disabled')
                seg['confirm_btn'].config(state='disabled')
                self.log(f"片段 {idx} 已确认")
                break
        self.check_all_confirmed()

    def confirm_retake(self, item, audio_path, duration, new_text, retake_idx, row_frame):
        self.log(f"确认重录片段（原序号{item['original_index']}）: 新音频 {audio_path}")
        for seg in self.segments:
            if seg.get('index') == item['original_index']:
                seg['audio_file'] = audio_path
                seg['duration'] = duration
                seg['text'] = new_text
                seg['confirmed'] = True
                seg['status_var'].set("已确认")
                seg['play_btn'].config(state='normal', command=lambda p=audio_path: self.play_audio(p))
                seg['retake_btn'].config(state='disabled')
                seg['confirm_btn'].config(state='disabled')
                preview = new_text[:60] + '...' if len(new_text) > 60 else new_text
                seg['preview_label'].config(text=preview)
                break
        row_frame.destroy()
        self.check_all_confirmed()

    def check_all_confirmed(self):
        all_original_confirmed = all(seg.get('confirmed', False) for seg in self.segments)
        if all_original_confirmed and not self.retake_queue:
            self.log("所有片段已确认，开始合成最终音频...")
            threading.Thread(target=self.combine_audio, daemon=True).start()

    def combine_audio(self):
        confirmed = [seg for seg in self.segments if seg.get('confirmed')]
        confirmed.sort(key=lambda x: x.get('index', 0))
        if not confirmed:
            self.log("没有已确认的片段，无法合成")
            return
        concat_file = os.path.join(self.work_dir, "concat.txt")
        with open(concat_file, 'w', encoding='utf-8') as f:
            for seg in confirmed:
                audio_file = seg['audio_file']
                if not audio_file:
                    self.log(f"警告：片段 {seg.get('index')} 没有音频文件，跳过")
                    continue
                audio_file = audio_file.replace('\\', '/')
                if not os.path.exists(audio_file):
                    self.log(f"警告：音频文件不存在 {audio_file}，跳过")
                    continue
                rel_path = os.path.relpath(audio_file, self.work_dir).replace('\\', '/')
                print(f"[DEBUG] 写入 concat 相对路径: {rel_path}")
                f.write(f"file '{rel_path}'\n")
        final_audio = os.path.join(self.work_dir, "final_audio.mp3")
        cmd = [str(FFMPEG), '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-ar', '16000', '-c:a', 'libmp3lame', '-b:a', '128k', 'final_audio.mp3']
        self.log("正在合成最终音频（ffmpeg），请稍候...")
        try:
            process = subprocess.Popen(
                cmd,
                cwd=self.work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )
            for line in process.stdout:
                self.log(line.rstrip())
            process.wait()
            if process.returncode == 0:
                self.log(f"最终音频已保存: {final_audio}")
                self.generate_timeline(confirmed, final_audio)
                self.after(0, lambda: self.final_audio_status.set("已生成"))
                self.after(0, lambda: self.final_play_btn.config(state='normal'))
            else:
                self.log(f"ffmpeg 合成失败，返回码: {process.returncode}")
        except Exception as e:
            self.log(f"合成异常: {e}")

    def generate_timeline(self, confirmed_segments, final_audio_path):
        timeline = []
        total_ms = 0
        for seg in confirmed_segments:
            duration_ms = int(seg['duration'] * 1000)
            timeline.append({
                "index": seg['index'],
                "text": seg['text'],
                "start_ms": total_ms,
                "end_ms": total_ms + duration_ms,
                "duration_ms": duration_ms,
                "file": os.path.basename(seg['audio_file'])
            })
            total_ms += duration_ms
        timeline_path = os.path.join(self.work_dir, "audio_timeline.json")
        with open(timeline_path, 'w', encoding='utf-8') as f:
            json.dump(timeline, f, ensure_ascii=False, indent=2)
        self.log(f"时间轴已保存: {timeline_path}")
        self.log("全部完成！")

    def stop_generation(self):
        if self.gen_controller:
            self.gen_controller.cancel_all()
            self.gen_controller.stop()
        self.running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.log("已停止生成")