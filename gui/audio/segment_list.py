# gui/audio/segment_list.py
import tkinter as tk
from tkinter import ttk
import re

class SegmentListPanel(ttk.Frame):
    def __init__(self, parent, on_play_requested, on_retake_requested, on_confirm_requested):
        super().__init__(parent)
        self.on_play_requested = on_play_requested
        self.on_retake_requested = on_retake_requested
        self.on_confirm_requested = on_confirm_requested
        self.segments = []          # 存储每个段落的字典
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

        # 定义滚轮处理函数并保存为实例方法
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self._on_mousewheel = _on_mousewheel

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def clear(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.segments = []

    def add_segment(self, idx, text):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill='x', pady=2)

        ttk.Label(row_frame, text=str(idx), width=4).pack(side='left')
        preview = text[:60] + '...' if len(text) > 60 else text
        preview_label = ttk.Label(row_frame, text=preview, width=60, wraplength=400)
        preview_label.pack(side='left', padx=5)

        status_var = tk.StringVar(value="待生成")
        ttk.Label(row_frame, textvariable=status_var, width=10).pack(side='left')

        play_btn = ttk.Button(row_frame, text="播放", state='disabled')
        play_btn.pack(side='left', padx=2)
        retake_btn = ttk.Button(row_frame, text="重录", state='disabled')
        retake_btn.pack(side='left', padx=2)
        confirm_btn = ttk.Button(row_frame, text="确认", state='disabled')
        confirm_btn.pack(side='left', padx=2)

        seg = {
            'index': idx,
            'text': text,
            'status_var': status_var,
            'play_btn': play_btn,
            'retake_btn': retake_btn,
            'confirm_btn': confirm_btn,
            'audio_file': None,
            'duration': None,
            'confirmed': False,
            'preview_label': preview_label,
            'row_frame': row_frame
        }
        self.segments.append(seg)

        # 绑定滚轮事件
        row_frame.bind("<MouseWheel>", self._on_mousewheel)
        for child in row_frame.winfo_children():
            child.bind("<MouseWheel>", self._on_mousewheel)

        # 绑定按钮命令（使用 lambda 捕获当前 idx）
        play_btn.config(command=lambda p=idx: self.on_play_requested(p))
        retake_btn.config(command=lambda p=idx: self.on_retake_requested(p))
        confirm_btn.config(command=lambda p=idx: self.on_confirm_requested(p))

        return seg

    def update_segment(self, idx, **kwargs):
        for seg in self.segments:
            if seg['index'] == idx:
                for key, value in kwargs.items():
                    if key in seg:
                        seg[key] = value
                # 更新 UI
                if 'text' in kwargs:
                    new_text = kwargs['text']
                    preview = new_text[:60] + '...' if len(new_text) > 60 else new_text
                    seg['preview_label'].config(text=preview)
                if 'status' in kwargs:
                    seg['status_var'].set(kwargs['status'])
                if 'audio_file' in kwargs:
                    seg['audio_file'] = kwargs['audio_file']
                if 'duration' in kwargs:
                    seg['duration'] = kwargs['duration']
                if 'confirmed' in kwargs:
                    seg['confirmed'] = kwargs['confirmed']
                if 'play_btn_state' in kwargs:
                    seg['play_btn'].config(state=kwargs['play_btn_state'])
                if 'retake_btn_state' in kwargs:
                    seg['retake_btn'].config(state=kwargs['retake_btn_state'])
                if 'confirm_btn_state' in kwargs:
                    seg['confirm_btn'].config(state=kwargs['confirm_btn_state'])
                break

    def get_segment(self, idx):
        for seg in self.segments:
            if seg['index'] == idx:
                return seg
        return None