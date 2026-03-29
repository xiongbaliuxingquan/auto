# gui/common_widgets.py
import tkinter as tk
from datetime import datetime
from gui.ui_components import ProgressBar, LogText

class CommonWidgets:
    def __init__(self, parent):
        self.parent = parent

        # 进度条
        self.progress = ProgressBar(parent)
        self.progress.frame.pack(fill='x', padx=5, pady=2)

        # 状态标签
        self.status_label = tk.Label(parent, text="就绪", anchor='w')
        self.status_label.pack(fill='x', padx=5)

        # 目录标签
        self.dir_label = tk.Label(parent, text="", anchor='w', fg='gray')
        self.dir_label.pack(fill='x', padx=5)

        # 底部日志框
        self.log_widget = LogText(parent)
        self.log_widget.text.pack(fill='both', expand=True, padx=5, pady=5)

    def set_progress(self, value):
        self.progress.set(value)

    def log(self, message):
        # 添加时间戳
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.log_widget.log(formatted_message)

    def set_status(self, text):
        self.status_label.config(text=text)

    def set_dir(self, text):
        self.dir_label.config(text=text)