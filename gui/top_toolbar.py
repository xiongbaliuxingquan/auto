# gui/top_toolbar.py
import tkinter as tk
from tkinter import ttk

# 复制 ASPECT_RATIO_MAP 定义
ASPECT_RATIO_MAP = {
    "16:9": ["1280x720", "1920x1080", "2560x1440", "640x360", "854x480", ],
    "9:16": ["720x1280", "1080x1920", "1440x2560", "360x640", "480x854"],
    "4:3": ["640x480", "800x600", "1024x768", "1280x960", "1440x1080", "1600x1200", "2048x1536"],
    "3:4": ["480x640", "720x960", "1080x1440", "1440x1920"],
    "2.35:1": ["1280x544", "1920x816", "3840x1640"],
    "2:1": ["1280x640", "1920x960", "3840x1920"],
    "1.85:1": ["1280x690", "1920x1038", "3840x2076"],
    "1:1": ["640x640", "1024x1024", "1080x1080", "1200x1200"]
}

class TopToolbar:
    def __init__(self, parent, app):
        self.app = app
        self.frame = tk.Frame(parent)

        # ========== 第一行：故事标题 + 模式选择 + 日志 ==========
        row1 = tk.Frame(self.frame)
        row1.pack(fill='x', pady=2)

        # 故事标题
        tk.Label(row1, text="故事标题：").pack(side='left')
        self.title_entry = tk.Entry(row1, width=20)
        self.title_entry.pack(side='left', padx=5)

        # 模式类型（标准/一键）
        tk.Label(row1, text="模式类型：").pack(side='left', padx=(20,0))
        self.mode_type_var = tk.StringVar(value="标准模式")
        self.mode_type_menu = ttk.Combobox(row1, textvariable=self.mode_type_var,
                                            values=["标准模式", "一键成片"], state="readonly", width=10)
        self.mode_type_menu.pack(side='left', padx=5)
        self.mode_type_menu.bind('<<ComboboxSelected>>', self.app.on_mode_type_change)

        # 滑块
        self.mode_slider = ttk.Scale(row1, from_=0, to=1, orient='horizontal',
                                      length=100, value=0, command=self.on_slider_move)
        self.mode_slider.pack(side='left', padx=5)

        # 模式（文生/图生）
        tk.Label(row1, text="模式：").pack(side='left', padx=(20,0))
        self.mode_var = tk.StringVar(value="图生视频")
        mode_menu = ttk.Combobox(row1, textvariable=self.mode_var,
                                 values=["文生视频", "图生视频"], state="readonly", width=12)
        mode_menu.pack(side='left', padx=5)

        # 右侧大日志按钮
        right_frame = tk.Frame(row1)
        right_frame.pack(side='right', padx=10)
        self.log_window_btn = tk.Button(right_frame, text="📄 大日志", command=self.app.log_viewer.show, width=8)
        self.log_window_btn.pack(side='left', padx=2)

        # ========== 第二行：全局视频设定 + 其他扩展控件 ==========
        row2 = tk.Frame(self.frame)
        row2.pack(fill='x', pady=2)

        # 工作流
        tk.Label(row2, text="工作流：").pack(side='left')
        self.workflow_var = tk.StringVar(value="LTX2.3")
        workflow_combo = ttk.Combobox(row2, textvariable=self.workflow_var,
                                       values=["WAN2.2", "LTX2.3"], state="readonly", width=8)
        workflow_combo.pack(side='left', padx=5)

        # 宽高比
        tk.Label(row2, text="宽高比：").pack(side='left', padx=(10,0))
        self.aspect_ratio_var = tk.StringVar(value="16:9")
        aspect_combo = ttk.Combobox(row2, textvariable=self.aspect_ratio_var,
                                     values=list(ASPECT_RATIO_MAP.keys()), state="readonly", width=6)
        aspect_combo.pack(side='left', padx=5)
        aspect_combo.bind('<<ComboboxSelected>>', self.on_aspect_ratio_change)

        # 分辨率
        tk.Label(row2, text="分辨率：").pack(side='left', padx=(10,0))
        self.resolution_var = tk.StringVar()
        self.resolution_combo = ttk.Combobox(row2, textvariable=self.resolution_var,
                                             values=ASPECT_RATIO_MAP["16:9"], state="readonly", width=10)
        self.resolution_combo.pack(side='left', padx=5)
        self.resolution_var.set("1280x720")

        # 文本类型
        tk.Label(row2, text="文本类型：").pack(side='left', padx=(20,0))
        self.text_type_var = tk.StringVar(value="")
        self.text_type_menu = ttk.Combobox(row2, textvariable=self.text_type_var,
                                            values=["情感故事", "文明结构", "动画默剧"], state="readonly", width=10)
        self.text_type_menu.pack(side='left', padx=5)
        self.text_type_menu.bind('<<ComboboxSelected>>', lambda e: self.app._update_preset_label())

        # 人设卡
        self.preset_label = tk.Label(row2, text="人设卡: 默认", fg='blue')
        self.preset_label.pack(side='left', padx=(10,2))
        self.preset_btn = tk.Button(row2, text="管理", command=self.app.open_preset_manager, width=4)
        self.preset_btn.pack(side='left', padx=2)

        # 字幕模式
        tk.Label(row2, text="字幕模式：").pack(side='left', padx=(20,0))
        self.subtitle_mode_var = tk.StringVar(value="")
        self.subtitle_mode_menu = ttk.Combobox(row2, textvariable=self.subtitle_mode_var,
                                                values=["无字幕", "有字幕"], state="readonly", width=8)
        self.subtitle_mode_menu.pack(side='left', padx=5)
        self.subtitle_mode_menu.bind('<<ComboboxSelected>>', self.app.on_subtitle_mode_change)

        self.extra_left_frame = tk.Frame(self.frame)

    def on_slider_move(self, value):
        val = round(float(value))
        if val == 0:
            self.mode_type_var.set("标准模式")
        else:
            self.mode_type_var.set("一键成片")
        self.app.on_mode_type_change()

    def on_aspect_ratio_change(self, event=None):
        aspect = self.aspect_ratio_var.get()
        if aspect in ASPECT_RATIO_MAP:
            resolutions = ASPECT_RATIO_MAP[aspect]
            self.resolution_combo['values'] = resolutions
            if resolutions:
                self.resolution_var.set(resolutions[0])
            else:
                self.resolution_var.set("")

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def pack_forget(self):
        self.frame.pack_forget()