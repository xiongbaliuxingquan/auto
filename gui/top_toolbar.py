# gui/top_toolbar.py
import tkinter as tk
from tkinter import ttk

class TopToolbar:
    def __init__(self, parent, app):
        self.app = app
        self.frame = tk.Frame(parent)

        # 故事标题（始终显示）
        tk.Label(self.frame, text="故事标题：").pack(side='left')
        self.title_entry = tk.Entry(self.frame, width=30)
        self.title_entry.pack(side='left', padx=5)

        # 创建一个 Frame 存放一键成片模式下需要隐藏的控件
        self.extra_left_frame = tk.Frame(self.frame)
        self.extra_left_frame.pack(side='left')

        # 文本类型
        tk.Label(self.extra_left_frame, text="文本类型：").pack(side='left', padx=(20,0))
        self.text_type_var = tk.StringVar(value="")
        self.text_type_menu = ttk.Combobox(self.extra_left_frame, textvariable=self.text_type_var,
                                            values=["情感故事", "文明结构", "动画默剧"], state="readonly", width=10)
        self.text_type_menu.pack(side='left', padx=5)
        self.text_type_menu.bind('<<ComboboxSelected>>', lambda e: self.app._update_preset_label())

        # 人设卡显示和按钮
        self.preset_label = tk.Label(self.extra_left_frame, text="人设卡: 默认", fg='blue')
        self.preset_label.pack(side='left', padx=(10,2))
        self.preset_btn = tk.Button(self.extra_left_frame, text="管理", command=self.app.open_preset_manager, width=4)
        self.preset_btn.pack(side='left', padx=2)

        # 字幕模式
        tk.Label(self.extra_left_frame, text="字幕模式：").pack(side='left', padx=(20,0))
        self.subtitle_mode_var = tk.StringVar(value="")
        self.subtitle_mode_menu = ttk.Combobox(self.extra_left_frame, textvariable=self.subtitle_mode_var,
                                                values=["无字幕", "有字幕"], state="readonly", width=8)
        self.subtitle_mode_menu.pack(side='left', padx=5)
        self.subtitle_mode_menu.bind('<<ComboboxSelected>>', self.app.on_subtitle_mode_change)
        
        # 模式类型选择（标准模式/一键成片）——下拉菜单
        tk.Label(self.frame, text="模式类型：").pack(side='left', padx=(20,0))
        self.mode_type_var = tk.StringVar(value="标准模式")
        self.mode_type_menu = ttk.Combobox(self.frame, textvariable=self.mode_type_var,
                                            values=["标准模式", "一键成片"], state="readonly", width=10)
        self.mode_type_menu.pack(side='left', padx=5)
        self.mode_type_menu.bind('<<ComboboxSelected>>', self.app.on_mode_type_change)

        # 滑块（与下拉菜单联动）
        self.mode_slider = ttk.Scale(self.frame, from_=0, to=1, orient='horizontal',
                                      length=100, value=0, command=self.on_slider_move)
        self.mode_slider.pack(side='left', padx=5)

        # 模式（文生/图生）
        tk.Label(self.frame, text="模式：").pack(side='left', padx=(20,0))
        self.mode_var = tk.StringVar(value="文生视频")
        mode_menu = ttk.Combobox(self.frame, textvariable=self.mode_var,
                                 values=["文生视频", "图生视频"], state="readonly", width=12)
        mode_menu.pack(side='left', padx=5)

        # 右侧区域：只保留日志按钮和系统医生
        right_frame = tk.Frame(self.frame)
        right_frame.pack(side='right', padx=10)

        self.log_window_btn = tk.Button(right_frame, text="📄 大日志", command=self.app.log_viewer.show, width=8)
        self.log_window_btn.pack(side='left', padx=2)

    def on_slider_move(self, value):
        val = round(float(value))
        if val == 0:
            self.mode_type_var.set("标准模式")
        else:
            self.mode_type_var.set("一键成片")
        self.app.on_mode_type_change()

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def pack_forget(self):
        self.frame.pack_forget()