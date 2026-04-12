# gui/standard_mode.py
import tkinter as tk
from tkinter import ttk, scrolledtext

class StandardMode:
    def __init__(self, parent, app, aspect_ratio_map):
        self.app = app
        self.aspect_ratio_map = aspect_ratio_map
        self.frame = tk.Frame(parent)

        # 五个标签页
        self.notebook = ttk.Notebook(self.frame)
        self.text_widgets = {}
        self.create_tabs()

        # 工作流和分辨率选择区域
        self.config_frame = tk.Frame(self.frame)
        # self.create_config_area()

        # 按钮区域
        self.button_frame = tk.Frame(self.frame)
        self.create_buttons()

        # 打包所有控件
        self.pack_widgets()

    def create_tabs(self):
        tab_titles = ["人物设定", "场景设定", "故事大纲", "口播稿"]
        keys = ["persona", "scene", "story", "script", "extra"]
        for title, key in zip(tab_titles, keys):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=title)
            text_widget = scrolledtext.ScrolledText(frame, wrap='word', font=('微软雅黑', 10))
            text_widget.pack(fill='both', expand=True, padx=5, pady=5)
            self.text_widgets[key] = text_widget

    def create_buttons(self):
        # 分割段落按钮（替代原来的开始处理）
        self.split_btn = tk.Button(self.button_frame, text="分割段落", command=self.app.split_paragraphs, width=10)
        self.split_btn.pack(side='left', padx=2)

        # 预览段落按钮（新增）
        self.preview_btn = tk.Button(self.button_frame, text="预览段落", command=self.app.preview_paragraphs, width=10, state='disabled')
        self.preview_btn.pack(side='left', padx=2)

        # 其他按钮（设置、历史、日志、系统医生、继续）保持不变
        self.settings_btn = tk.Button(self.button_frame, text="设置", command=self.app.open_settings, width=6)
        self.settings_btn.pack(side='left', padx=2)

        self.history_btn = tk.Button(self.button_frame, text="打开历史", command=self.app.open_history_project, width=8)
        self.history_btn.pack(side='left', padx=2)

        self.open_log_btn = tk.Button(self.button_frame, text="打开日志", command=self.app.open_log_folder, width=8)
        self.open_log_btn.pack(side='left', padx=2)

        self.continue_btn = tk.Button(self.button_frame, text="继续", command=self.app.continue_generation, state='disabled', width=8)
        self.continue_btn.pack(side='left', padx=2)

    def pack_widgets(self):
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        # self.config_frame.pack(fill='x', padx=5, pady=2)
        self.button_frame.pack(fill='x', padx=5, pady=5)

    def on_aspect_ratio_change(self, event=None):
        aspect = self.aspect_ratio_var.get()
        if aspect in self.aspect_ratio_map:
            resolutions = self.aspect_ratio_map[aspect]
            self.resolution_combo['values'] = resolutions
            if resolutions:
                self.resolution_var.set(resolutions[0])
            else:
                self.resolution_var.set("")
        else:
            self.resolution_combo['values'] = []
            self.resolution_var.set("")