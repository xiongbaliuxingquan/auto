# gui/audio/retake_manager.py
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import re
from core.fish_tts import generate_single
from utils.audio_utils import call_deepseek, get_audio_duration

class RetakeManager:
    def __init__(self, work_dir, ref_audio_filename, ref_text, language, log_callback, play_audio_callback, engine='fish', speed=1.0, get_ref_audio_filename=None, stop_playback_callback=None, get_speed=None):
        self.stop_playback = stop_playback_callback
        self.work_dir = work_dir
        self.ref_audio_filename = ref_audio_filename
        self.ref_text = ref_text
        self.language = language
        self.log = log_callback
        self.play_audio = play_audio_callback
        self.retake_queue = []
        # self.next_retake_index = 0
        self.retake_thread_running = True
        self.retake_thread = threading.Thread(target=self._process_retake_queue, daemon=True)
        self.retake_thread.start()
        self.retake_scrollable = None
        self.on_segment_updated = None
        self.engine = engine
        self.speed = speed
        self.get_speed = get_speed  # 保存回调
        self.get_ref_audio_filename = get_ref_audio_filename

    def set_retake_scrollable(self, scrollable_frame):
        self.retake_scrollable = scrollable_frame

    def request_retake(self, idx, seg, text_edit, problem_entry, win):
        def submit():
            new_text = text_edit.get('1.0', 'end-1c').strip()
            problem = problem_entry.get().strip()
            if new_text == seg['text'] and not problem:
                messagebox.showwarning("提示", "请修改原文或输入修改意见")
                return
            win.destroy()
            final_text = new_text if new_text != seg['text'] else None
            self._add_retake_pending_item(seg['index'], final_text, problem, seg['text'])
        return submit

    def _add_retake_pending_item(self, original_index, final_text, problem_desc, original_text):
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

        pending_info = {
            'original_index': original_index,
            'final_text': final_text,
            'problem_desc': problem_desc,
            'original_text': original_text,
            'status_label': status_label,
            'play_btn': play_btn,
            'confirm_btn': confirm_btn,
            'label_desc': label_desc,
            'row_frame': row_frame,
            'error_msg': None
        }
        row_frame.pending_info = pending_info

        self.retake_queue.append({
            'original_index': original_index,
            'original_text': original_text,
            'problem_desc': problem_desc,
            'new_text': final_text,
            'row_frame': row_frame,
            'pending_info': pending_info
        })

    def _process_retake_queue(self):
        while self.retake_thread_running:
            if not self.retake_queue:
                import time
                time.sleep(0.5)
                continue
            item = self.retake_queue.pop(0)
            self.log(f"开始重录片段 {item['original_index']} ...")
            if item['new_text'] is not None:
                final_text = item['new_text']
            else:
                final_text = self._ai_modify_text(item['original_text'], item['problem_desc'])
            original_index = item['original_index']

            error_msg = None
            try:
                if self.stop_playback:
                    self.stop_playback()
                if self.get_speed:
                    current_speed = self.get_speed()
                if self.engine == 'omnivoice':
                    from core.omnivoice_tts import generate_single_omnivoice
                    # 动态获取最新的参考音频文件名
                    current_ref = self.ref_audio_filename
                    if self.get_ref_audio_filename:
                        current_ref = self.get_ref_audio_filename()
                    print(f"[DEBUG] Retake OmniVoice: ref_audio_filename = {current_ref}")
                    audio_path = generate_single_omnivoice(
                        text=final_text,
                        index=original_index,
                        output_dir=self.work_dir,
                        ref_audio_filename=current_ref,
                        speed=current_speed,   # 使用动态获取的速度
                        log_callback=self.log
                    )
                else:
                    audio_path = generate_single(
                        text=final_text,
                        index=original_index,
                        output_dir=self.work_dir,
                        ref_audio_filename=self.ref_audio_filename,
                        ref_text=self.ref_text,
                        language=self.language,
                        log_callback=self.log
                    )
                if audio_path:
                    duration = get_audio_duration(audio_path)
                    self._on_generation_success(item, audio_path, duration, final_text)
                    continue
                else:
                    error_msg = "生成失败，返回空路径"
            except Exception as e:
                error_msg = str(e)
            self._on_generation_failure(item, error_msg)

    def _ai_modify_text(self, original_text, problem_desc):
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

    def _on_generation_success(self, item, audio_path, duration, new_text):
        original_index = item['original_index']
        self.log(f"重录完成（原片段{original_index}）: {new_text[:30]}... 时长 {duration:.2f}s")
        row_frame = item['row_frame']
        info = row_frame.pending_info

        # 清除可能存在的错误标签、重试按钮、提示标签等额外控件
        for child in row_frame.winfo_children():
            # 保留原片段标签、描述标签、播放按钮、确认按钮、状态标签
            if child in (info['play_btn'], info['confirm_btn'], info['status_label'], info['label_desc']):
                continue
            if isinstance(child, ttk.Label) and child.cget('text').startswith('原片段'):
                continue
            child.destroy()

        # 更新 UI
        preview = new_text[:30] + '...' if len(new_text) > 30 else new_text
        info['label_desc'].config(text=preview)
        info['status_label'].config(text="已生成", foreground='green')
        info['play_btn'].config(state='normal', command=lambda: self.play_audio(audio_path))
        info['confirm_btn'].config(state='normal', command=lambda: self._confirm_retake(item, audio_path, duration, new_text, row_frame))
        row_frame.retake_result = {
            'audio_path': audio_path,
            'duration': duration,
            'new_text': new_text,
            'original_index': original_index   # 改为存原始序号
        }

    def _on_generation_failure(self, item, error_msg):
        self.log(f"重录失败: {error_msg}")
        row_frame = item['row_frame']
        info = row_frame.pending_info
        info['status_label'].config(text="失败", foreground='red')
        info['error_msg'] = error_msg

        # 判断错误类型，给出友好提示
        lower_msg = error_msg.lower()
        if "空路径" in lower_msg or "404" in lower_msg or "connection" in lower_msg:
            error_display = "错误：ComfyUI无法连接"
            hint_text = "请打开ComfyUI后重试"
        else:
            error_display = f"错误: {error_msg[:50]}"
            hint_text = "请检查日志后重试"

        error_label = ttk.Label(row_frame, text=error_display, foreground='red', font=('微软雅黑', 8))
        error_label.pack(side='left', padx=5)

        retry_btn = ttk.Button(row_frame, text="重试", command=lambda: self._retry_retake(item))
        retry_btn.pack(side='left', padx=2)

        hint_label = ttk.Label(row_frame, text=hint_text, foreground='gray', font=('微软雅黑', 8))
        hint_label.pack(side='left', padx=5)

    def _retry_retake(self, item):
        row_frame = item['row_frame']
        info = row_frame.pending_info

        # 清除所有额外控件（错误标签、重试按钮、提示标签）
        for child in row_frame.winfo_children():
            if child in (info['play_btn'], info['confirm_btn'], info['status_label'], info['label_desc']):
                continue
            if isinstance(child, ttk.Label) and child.cget('text').startswith('原片段'):
                continue
            child.destroy()

        # 恢复状态
        info['status_label'].config(text="生成中...", foreground='blue')
        # 重新加入队列
        self.retake_queue.append(item)
        self.log(f"已重新加入重录队列: 片段 {item['original_index']}")

    def _confirm_retake(self, item, audio_path, duration, new_text, row_frame):
        self.log(f"确认重录片段（原序号{item['original_index']}）: 新音频 {audio_path}")
        if self.on_segment_updated:
            self.on_segment_updated(item['original_index'], audio_path, duration, new_text)
        row_frame.destroy()
    def clear(self):
        for item in self.retake_queue:
            if item.get('row_frame'):
                item['row_frame'].destroy()
        self.retake_queue.clear()