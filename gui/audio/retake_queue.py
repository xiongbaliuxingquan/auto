# gui/audio/retake_queue.py
import tkinter as tk
from tkinter import ttk

class RetakeQueuePanel(ttk.Frame):
    def __init__(self, parent, generation_controller):
        super().__init__(parent)
        self.generation_controller = generation_controller
        self.items = []          # 存储队列中的行信息
        self.on_play_requested = None   # 外部回调，用于播放音频
        self.on_confirm_requested = None # 外部回调，用于确认替换
        self._init_ui()

    def _init_ui(self):
        # 创建滚动区域
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind("<MouseWheel>", _on_mousewheel)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def add_pending(self, original_index, final_text, problem_desc):
        """添加一个生成中的项"""
        row_frame = ttk.Frame(self.scrollable_frame)
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

        info = {
            'original_index': original_index,
            'final_text': final_text,
            'problem_desc': problem_desc,
            'row_frame': row_frame,
            'label_desc': label_desc,
            'play_btn': play_btn,
            'confirm_btn': confirm_btn,
            'status_label': status_label,
            'audio_path': None,
            'duration': None,
            'new_text': None
        }
        self.items.append(info)

        # 将生成任务加入控制器队列
        def callback(idx, success, audio_path, duration):
            if success:
                self._on_generation_success(info, audio_path, duration)
            else:
                self._on_generation_failure(info)

        if self.generation_controller:
            self.generation_controller.add_task(original_index, final_text, callback)
        else:
            # 如果没有控制器，直接失败
            self._on_generation_failure(info)

    def _on_generation_success(self, info, audio_path, duration):
        info['audio_path'] = audio_path
        info['duration'] = duration
        info['new_text'] = info['final_text']  # 最终文本（可能由 AI 修改，此处先使用 final_text）
        # 更新 UI
        preview = info['new_text'][:30] + '...' if len(info['new_text']) > 30 else info['new_text']
        info['label_desc'].config(text=preview)
        info['status_label'].config(text="已生成", foreground='green')
        info['play_btn'].config(state='normal', command=lambda: self._play_audio(audio_path))
        info['confirm_btn'].config(state='normal', command=lambda: self._confirm_item(info))

    def _on_generation_failure(self, info):
        info['status_label'].config(text="失败", foreground='red')

    def _play_audio(self, path):
        if self.on_play_requested:
            self.on_play_requested(path)

    def _confirm_item(self, info):
        if self.on_confirm_requested:
            self.on_confirm_requested(info['original_index'], info['new_text'], info['audio_path'], info['duration'])
        # 移除该行
        info['row_frame'].destroy()
        self.items.remove(info)

    def clear(self):
        """清空队列"""
        for info in self.items:
            info['row_frame'].destroy()
        self.items.clear()