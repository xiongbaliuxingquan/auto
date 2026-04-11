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
import glob

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
from gui.tts_tutorial import TUTORIAL_CONTENT
from core.audio.segment_labeler import SegmentLabeler
from core.audio.final_combine import FinalAudioCombine
from gui.audio.retake_manager import RetakeManager

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
        self.paragraphs = []
        self.running = False
        self.stop_requested = False
        self.reminder_window = None
        self.language_var = tk.StringVar(value="auto")
        self._work_dir_set = None
        self._loaded = False
        self.has_labeled_segments = False
        self.reference_manager = None
        self.segment_labeler = None
        self.retake_manager = None

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

        # 新增：TTS 引擎选择变量和语速变量
        self.tts_engine_var = tk.StringVar(value="omnivoice")
        self.speed_var = tk.DoubleVar(value=1.0)

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
                    # self.show_reminder(index)
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
            # ===== 以下内容已注释，不再执行翻译步骤 =====
            # self.log("开始提取并翻译提示词...")
            # cmd5 = [sys.executable, os.path.join(project_root, "core", "extract_prompts.py"), self.work_dir]
            # rc5, success5 = run_cmd(cmd5, cwd=project_root)
            # if not success5:
            #     self.app.root.after(0, lambda: self.log("extract_prompts.py 执行失败"))
            #     self.app.root.after(0, lambda: self.align_btn.config(state='normal', text="生成视频提示词"))
            #     return
            # =============================================
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

    def _on_retake_confirm(self, original_index, audio_path, duration, new_text):
        for seg in self.segments:
            if seg['index'] == original_index:
                # 如果当前播放的就是这个片段，立即停止并卸载文件
                if self.current_playing == seg.get('audio_file'):
                    self.playback.stop()
                    self.current_playing = None
                    self.play_pause_btn.config(text="▶ 播放")
                    self.progress_scale.set(0)
                # 更新片段信息
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
        self.check_all_confirmed()

    def set_work_dir(self, work_dir):
        if self.work_dir == work_dir:
            print("[DEBUG] Already set, skipping")
            return
        self.work_dir = work_dir

        self.subtitle_generator = SubtitleGenerator(work_dir, log_callback=self.log)
        self.reference_manager = ReferenceAudioManager(work_dir, log_callback=self.log)
        self.segment_labeler = SegmentLabeler(work_dir, log_callback=self.log)
        self.final_combiner = FinalAudioCombine(work_dir, log_callback=self.log)
        self.ref_audio_path.set(self.reference_manager.get_ref_audio_path() or "")
        self.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
        self.ref_text = self.reference_manager.get_ref_text()

        # 创建控制器时传入 engine 和 speed
        self.gen_controller = AudioGenerationController(
            work_dir=self.work_dir,
            ref_audio_filename=self.reference_manager.get_ref_audio_filename(),
            ref_text=self.reference_manager.get_ref_text(),
            language=self.language_var.get(),
            engine=self.tts_engine_var.get(),
            speed=self.speed_var.get(),
            log_callback=self.log
        )
        self.gen_controller.set_progress_callback(self._on_generation_progress)
        self.gen_controller.start()

        self.retake_manager = RetakeManager(
            work_dir,
            self.ref_audio_filename,
            self.ref_text,
            self.language_var.get(),
            self.log,
            self.play_audio,
            engine=self.tts_engine_var.get(),
            speed=self.speed_var.get(),
            get_ref_audio_filename=lambda: self.ref_audio_filename,
            stop_playback_callback=lambda: self.playback.stop(),
            get_speed=lambda: self.speed_var.get()   # 新增
        )
        self.retake_manager.set_retake_scrollable(self.retake_scrollable)
        self.retake_manager.on_segment_updated = self._on_retake_confirm

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

    # ---------- 引擎切换回调 ----------
    def _on_engine_change(self, event=None):
        if self.tts_engine_var.get() == "omnivoice":
            self.speed_frame.pack(fill='x', pady=2, before=self.row2)
        else:
            self.speed_frame.pack_forget()

    # ---------- 界面构建 ----------
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

        # 引擎选择行
        row_engine = ttk.Frame(control_frame)
        row_engine.pack(fill='x', pady=2)
        ttk.Label(row_engine, text="TTS引擎:").pack(side='left', padx=5)
        engine_combo = ttk.Combobox(row_engine, textvariable=self.tts_engine_var,
                                    values=["fish", "omnivoice"], state="readonly", width=10)
        engine_combo.pack(side='left', padx=5)
        engine_combo.bind('<<ComboboxSelected>>', self._on_engine_change)

        # 语速控件（默认隐藏，OmniVoice 时显示）
        self.speed_frame = ttk.Frame(control_frame)
        self.speed_frame.pack(fill='x', pady=2)
        ttk.Label(self.speed_frame, text="语速:").pack(side='left', padx=5)
        self.speed_scale = ttk.Scale(self.speed_frame, from_=0.5, to=2.0, variable=self.speed_var,
                                     orient='horizontal', length=200)
        self.speed_scale.pack(side='left', padx=5)
        self.speed_label = ttk.Label(self.speed_frame, text="1.0x")
        self.speed_label.pack(side='left')

        def update_speed_label(*args):
            self.speed_label.config(text=f"{self.speed_var.get():.1f}x")
        self.speed_var.trace('w', update_speed_label)
        self.speed_frame.pack_forget()  # 初始隐藏

        # 保存 row2 的引用，供 _on_engine_change 使用
        self.row2 = ttk.Frame(control_frame)
        self.row2.pack(fill='x', pady=5)
        self.gen_seg_btn = ttk.Button(self.row2, text="段落自动润色", command=self.generate_segments_manual)
        self.gen_seg_btn.pack(side='left', padx=2)
        self.start_btn = ttk.Button(self.row2, text="开始生成音频", command=self.start_generation)
        self.start_btn.pack(side='left', padx=2)
        self.stop_btn = ttk.Button(self.row2, text="停止生成音频", command=self.stop_generation, state='disabled')
        self.stop_btn.pack(side='left', padx=2)
        self.align_btn = ttk.Button(self.row2, text="生成视频提示词", command=self.auto_align_duration)
        self.align_btn.pack(side='left', padx=2)
        self.advanced_btn = ttk.Button(self.row2, text="▼ 高级选项", command=self.show_advanced_dialog)
        self.advanced_btn.pack(side='right', padx=5)

        # 段落列表区域
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
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self._on_mousewheel = _on_mousewheel
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        self._on_engine_change()

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
        file_path = filedialog.askopenfilename(filetypes=[("Audio files", "*.mp3 *.wav")])
        if not file_path:
            return

        self.ref_audio_path.set(file_path)
        self._save_local_path_to_cache(file_path)   # 新增：保存本地路径到缓存

        # OmniVoice 引擎：无需转录，仅保存路径
        if self.tts_engine_var.get() == "omnivoice":
            self.ref_audio_filename = None
            self.ref_text = ""
            if self.retake_manager:
                self.retake_manager.ref_audio_filename = None
            self.log("参考音频已选择（OmniVoice 模式，无需转录）")
            return

        # Fish 引擎：上传并转录
        self.log("正在上传参考音频并提取文本，请稍候...")
        def task():
            success = self.reference_manager.set_from_local(file_path)
            self.after(0, lambda: self._on_ref_audio_uploaded(success, file_path))
        threading.Thread(target=task, daemon=True).start()

    def _on_ref_audio_uploaded(self, success, file_path):
        if success:
            # 更新 UI 变量
            self.ref_audio_path.set(file_path)
            self.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
            self.ref_text = self.reference_manager.get_ref_text()
            self.log("参考音频已成功上传并提取文本")
            # 保存本地路径到缓存
            self._save_local_path_to_cache(file_path)
        else:
            self.log("参考音频上传或文本提取失败")

    def ai_generate_audio(self):
        """弹出AI生成参考音频窗口"""
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return
        if not hasattr(self, 'script_text') or not self.script_text:
            messagebox.showerror("错误", "请先加载口播稿")
            return

        win = tk.Toplevel(self)
        win.title("AI生成参考音频")
        win.geometry("700x600")
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - 700) // 2
        y = (screen_height - 600) // 2
        win.geometry(f"+{x}+{y}")
        win.transient(self)
        win.grab_set()

        # 语音描述输入
        ttk.Label(win, text="语音描述（如“语速很快，中年男性，声音干练”）:").pack(anchor='w', padx=10, pady=5)
        voice_entry = ttk.Entry(win, width=60)
        voice_entry.pack(fill='x', padx=10, pady=5)

        # 教程按钮
        btn_frame_tutorial = ttk.Frame(win)
        btn_frame_tutorial.pack(fill='x', padx=10, pady=2)
        ttk.Button(btn_frame_tutorial, text="提示词详细教程", command=self.open_tts_tutorial).pack(side='right')

        # 朗读文本编辑框
        ttk.Label(win, text="朗读文本（自动从口播稿提取前几句）:").pack(anchor='w', padx=10, pady=5)
        text_edit = scrolledtext.ScrolledText(win, height=8, wrap='word')
        sentences = re.split(r'[。！？]', self.script_text)
        if len(sentences) >= 3:
            preview_text = '。'.join(sentences[:3]) + '。'
        else:
            preview_text = self.script_text[:200]
        text_edit.insert('1.0', preview_text)
        text_edit.pack(fill='both', expand=True, padx=10, pady=5)

        # 生成结果区域
        result_frame = ttk.LabelFrame(win, text="生成结果", padding=5)
        result_frame.pack(fill='x', padx=10, pady=10)
        status_var = tk.StringVar(value="未生成")
        ttk.Label(result_frame, textvariable=status_var, foreground='blue').pack(anchor='w')
        audio_path_var = tk.StringVar()
        ttk.Entry(result_frame, textvariable=audio_path_var, state='readonly', width=60).pack(fill='x', padx=5, pady=2)

        btn_row = ttk.Frame(result_frame)
        btn_row.pack(pady=5)
        play_btn = ttk.Button(btn_row, text="播放", state='disabled',
                            command=lambda: self.play_audio(audio_path_var.get()))
        play_btn.pack(side='left', padx=5)

        def open_history():
            if not self.work_dir:
                messagebox.showerror("错误", "工作目录未设置")
                return
            file_path = filedialog.askopenfilename(
                title="选择预览音频文件",
                initialdir=self.work_dir,
                filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")]
            )
            if file_path:
                audio_path_var.set(file_path)
                status_var.set("已加载历史预览")
                play_btn.config(state='normal')

        history_btn = ttk.Button(btn_row, text="打开历史预览", command=open_history)
        history_btn.pack(side='left', padx=5)

        def do_generate():
            voice_desc = voice_entry.get().strip()
            if not voice_desc:
                messagebox.showwarning("提示", "请填写语音描述")
                return
            text_to_read = text_edit.get('1.0', 'end-1c').strip()
            if not text_to_read:
                messagebox.showwarning("提示", "朗读文本不能为空")
                return
            gen_btn.config(state='disabled', text="生成中...")
            status_var.set("正在生成音频，约1分钟，请稍候...")
            win.update()

            def run():
                try:
                    audio_path = generate_reference_audio(text_to_read, voice_desc, self.work_dir)
                    if audio_path:
                        audio_path_var.set(audio_path)
                        status_var.set("生成成功！")
                        play_btn.config(state='normal')
                        self.log("AI生成参考音频成功: " + audio_path)
                    else:
                        status_var.set("生成失败，请检查日志")
                except Exception as e:
                    status_var.set(f"生成异常: {e}")
                finally:
                    win.after(0, lambda: gen_btn.config(state='normal', text="生成"))

            threading.Thread(target=run, daemon=True).start()

        gen_btn = ttk.Button(win, text="生成", command=do_generate)
        gen_btn.pack(pady=5)

        def confirm():
            path = audio_path_var.get()
            if not path:
                messagebox.showwarning("提示", "尚未生成或生成失败，无法确认")
                return
            self._save_local_path_to_cache(path)   # 新增：保存本地路径
            win.destroy()
            # OmniVoice 引擎：仅保存路径
            self._save_local_path_to_cache(path)
            if self.tts_engine_var.get() == "omnivoice":
                self.ref_audio_path.set(path)
                self.ref_audio_filename = None
                self.ref_text = ""
                self.log("参考音频已选择（OmniVoice 模式，无需转录）")
                return
            # Fish 引擎：上传并转录
            self.log("正在上传参考音频并提取文本...")
            def task():
                success = self.reference_manager.set_from_local(path)
                self.after(0, lambda: self._on_ref_audio_uploaded(success, path))
            threading.Thread(target=task, daemon=True).start()

        ttk.Button(win, text="确认使用", command=confirm).pack(pady=5)
        ttk.Button(win, text="取消", command=win.destroy).pack(pady=5)

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

        def on_complete(segments):
            if segments:
                self.app.root.after(0, self.load_segments_from_json)
                self.app.root.after(0, lambda: self.log("段落润色完成"))
                self.app.root.after(0, lambda: setattr(self, 'has_labeled_segments', True))
                self.app.root.after(0, lambda: self.gen_seg_btn.config(text="重新润色"))
            else:
                self.app.root.after(0, lambda: self.log("段落润色失败"))

        # 传入当前选择的引擎
        self.segment_labeler.generate_segments(self.paragraphs, on_complete, engine=self.tts_engine_var.get())
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
        # 自动恢复上次使用的参考音频路径
        cache_path = os.path.join(work_dir, "reference_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                # 恢复本地路径（若存在且文件未丢失）
                local_path = cache.get("local_path")
                if local_path and os.path.exists(local_path):
                    self.ref_audio_path.set(local_path)
                    self.log(f"已从缓存恢复参考音频路径: {local_path}")
                else:
                    # 可选：若路径无效，可尝试根据 audio_filename 模糊查找，但您已明确不需要
                    pass
                # 原有 audio_filename 和 reference_text 恢复逻辑保持不变
                self.ref_audio_filename = cache.get("audio_filename")
                self.ref_text = cache.get("reference_text")
                if self.ref_audio_filename and self.ref_text:
                    self.log("已从缓存加载参考音频信息")
            except Exception as e:
                self.log(f"加载参考缓存失败: {e}")
        if self.running:
            self.log("已有生成任务在运行")
            return
        # OmniVoice 引擎：确保参考音频已上传到 ComfyUI 服务器
        if self.tts_engine_var.get() == "omnivoice" and not self.ref_audio_filename:
            ref_path = self.ref_audio_path.get()
            if not ref_path:
                messagebox.showerror("错误", "请先选择参考音频")
                return
            from core.omnivoice_tts import upload_audio
            api_url = config_manager.COMFYUI_API_URL
            self.log("正在上传参考音频到 OmniVoice 服务器...")
            uploaded = upload_audio(api_url, ref_path)
            if not uploaded:
                messagebox.showerror("错误", "参考音频上传失败，请检查网络或地址")
                return
            self.ref_audio_filename = uploaded
            self.gen_controller.ref_audio_filename = uploaded   # 关键：更新控制器中的文件名
            self.retake_manager.ref_audio_filename = uploaded
            self.log(f"参考音频已上传，服务器文件名: {uploaded}")

        if self.gen_controller:
            # OmniVoice 引擎在上传后已经设置了 ref_audio_filename，无需再从 reference_manager 获取
            if self.tts_engine_var.get() != "omnivoice":
                self.ref_audio_filename = self.reference_manager.get_ref_audio_filename()
                self.ref_text = self.reference_manager.get_ref_text()
                self.gen_controller.ref_audio_filename = self.ref_audio_filename
                self.gen_controller.ref_text = self.ref_text
                self.gen_controller.language = self.language_var.get()
            # 以下两行对两个引擎都有效
            self.gen_controller.engine = self.tts_engine_var.get()
            self.gen_controller.speed = self.speed_var.get()
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
        # 强制设置播放位置
        self.playback.seek(pos_sec)
        # 立即更新进度条显示，防止弹回
        self.progress_scale.set(pos_ms)
        self.time_label.config(text=f"{self._format_time(pos_sec)} / {self._format_time(self.playback.current_total_duration)}")

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
        # 如果是 OmniVoice 且尚未上传参考音频，则先上传
        if self.tts_engine_var.get() == "omnivoice" and not self.ref_audio_filename:
            ref_path = self.ref_audio_path.get()
            if not ref_path:
                messagebox.showerror("错误", "请先选择参考音频")
                return
            from core.omnivoice_tts import upload_audio
            api_url = config_manager.COMFYUI_API_URL
            self.log("正在上传参考音频到 OmniVoice 服务器...")
            uploaded = upload_audio(api_url, ref_path)
            if not uploaded:
                messagebox.showerror("错误", "参考音频上传失败，请检查网络或地址")
                return
            self.ref_audio_filename = uploaded
            if self.gen_controller:
                self.gen_controller.ref_audio_filename = uploaded
            if self.retake_manager:
                self.retake_manager.ref_audio_filename = uploaded
            self.log(f"参考音频已上传，服务器文件名: {uploaded}")
        
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

        submit = self.retake_manager.request_retake(idx, seg, text_edit, problem_entry, win)

        ttk.Button(btn_frame, text="提交", command=submit).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=lambda: (win.destroy(), setattr(self, '_retake_dialog_win', None))).pack(side='left', padx=5)
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
    def check_all_confirmed(self):
        if all(seg.get('confirmed', False) for seg in self.segments):
            self.log("所有片段已确认，开始合成最终音频...")
            threading.Thread(target=self.combine_audio, daemon=True).start()
    def combine_audio(self):
        confirmed = [seg for seg in self.segments if seg.get('confirmed')]
        confirmed.sort(key=lambda x: x.get('index', 0))
        if not confirmed:
            self.log("没有已确认的片段，无法合成")
            return
        self.final_combiner.combine(confirmed, self._on_combine_done)

    def _on_combine_done(self, success, final_audio_path):
        if success:
            self.final_audio_status.set("已生成")
            self.final_play_btn.config(state='normal')
        else:
            self.log("最终音频合成失败")

    def _save_local_path_to_cache(self, local_path):
        """将参考音频本地路径保存到 reference_cache.json"""
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        try:
            cache = {}
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
            cache['local_path'] = local_path
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存本地路径到缓存失败: {e}")
    def stop_generation(self):
        if self.gen_controller:
            self.gen_controller.cancel_all()
            self.gen_controller.stop()
        self.running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.log("已停止生成")