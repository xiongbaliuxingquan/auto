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
        self.create_config_area()

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

    def create_config_area(self):
        tk.Label(self.config_frame, text="工作流：").pack(side='left')
        self.workflow_var = tk.StringVar(value="LTX2.3")
        workflow_combo = ttk.Combobox(self.config_frame, textvariable=self.workflow_var,
                                       values=["WAN2.2", "LTX2.3"], state="readonly", width=10)
        workflow_combo.pack(side='left', padx=5)

        tk.Label(self.config_frame, text="宽高比：").pack(side='left', padx=(20,0))
        self.aspect_ratio_var = tk.StringVar(value="16:9")
        aspect_combo = ttk.Combobox(self.config_frame, textvariable=self.aspect_ratio_var,
                                     values=list(self.aspect_ratio_map.keys()), state="readonly", width=10)
        aspect_combo.pack(side='left', padx=5)
        aspect_combo.bind('<<ComboboxSelected>>', self.app.on_aspect_ratio_change)

        tk.Label(self.config_frame, text="分辨率：").pack(side='left', padx=(5,0))
        self.resolution_var = tk.StringVar()
        self.resolution_combo = ttk.Combobox(self.config_frame, textvariable=self.resolution_var,
                                             values=self.aspect_ratio_map["16:9"], state="readonly", width=12)
        self.resolution_combo.pack(side='left', padx=5)
        self.resolution_var.set("1280x720")

    def create_buttons(self):
        # 分割段落按钮（替代原来的开始处理）
        self.split_btn = tk.Button(self.button_frame, text="分割段落", command=self.app.split_paragraphs, width=10)
        self.split_btn.pack(side='left', padx=2)

        # 预览段落按钮（新增）
        self.preview_btn = tk.Button(self.button_frame, text="预览段落", command=self.app.preview_paragraphs, width=10, state='disabled')
        self.preview_btn.pack(side='left', padx=2)

        # 其他按钮（初始禁用）
        self.run_workflow_btn = tk.Button(self.button_frame, text="运行工作流", state='disabled',
                                        command=self.app.run_workflow, width=12)
        self.run_workflow_btn.pack(side='left', padx=2)

        self.select_edit_btn = tk.Button(self.button_frame, text="选择或编辑提示词", state='disabled',
                                        command=self.app.open_shot_editor, width=16)
        self.select_edit_btn.pack(side='left', padx=2)

        self.first_frame_btn = tk.Button(self.button_frame, text="生成首帧提示词", state='disabled',
                                        command=self.app.run_first_frame_generation, width=14)
        self.first_frame_btn.pack(side='left', padx=2)

        self.align_btn = tk.Button(self.button_frame, text="视频精确对齐", command=self.app.run_video_align, width=14)
        self.align_btn.pack(side='left', padx=2)

        self.upload_subtitle_btn = tk.Button(self.button_frame, text="上传字幕测试", command=self.app.upload_subtitle, width=12, state='normal')
        self.upload_subtitle_btn.pack(side='left', padx=2)

        # 其他按钮（设置、历史、日志、系统医生、继续）保持不变
        self.settings_btn = tk.Button(self.button_frame, text="设置", command=self.app.open_settings, width=6)
        self.settings_btn.pack(side='left', padx=2)

        self.history_btn = tk.Button(self.button_frame, text="打开历史", command=self.app.open_history_project, width=8)
        self.history_btn.pack(side='left', padx=2)

        self.open_log_btn = tk.Button(self.button_frame, text="打开日志", command=self.app.open_log_folder, width=8)
        self.open_log_btn.pack(side='left', padx=2)

        self.doctor_btn = tk.Button(self.button_frame, text="系统医生", command=self.app.run_system_doctor, width=8)
        self.doctor_btn.pack(side='left', padx=2)

        self.continue_btn = tk.Button(self.button_frame, text="继续", command=self.app.continue_generation, state='disabled', width=8)
        self.continue_btn.pack(side='left', padx=2)

    def pack_widgets(self):
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        self.config_frame.pack(fill='x', padx=5, pady=2)
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