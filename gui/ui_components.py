import tkinter as tk
from tkinter import ttk, scrolledtext

class LogText:
    """带自动滚动的日志文本框组件"""
    def __init__(self, parent, height=12):
        self.text = scrolledtext.ScrolledText(parent, height=height, state='disabled')
        self.text.pack(fill='both', expand=True, padx=5, pady=5)

    def log(self, message):
        self.text.config(state='normal')
        self.text.insert('end', message + '\n')
        self.text.see('end')
        self.text.config(state='disabled')

    def clear(self):
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.config(state='disabled')


class ProgressBar:
    """带百分比显示的进度条"""
    def __init__(self, parent, length=400):
        self.frame = tk.Frame(parent)
        self.frame.pack(fill='x', padx=5, pady=2)

        self.label = tk.Label(self.frame, text="整体进度：")
        self.label.pack(side='left')

        self.bar = ttk.Progressbar(self.frame, length=length, mode='determinate')
        self.bar.pack(side='left', padx=5)

        self.percent = tk.Label(self.frame, text="0%")
        self.percent.pack(side='left')

    def set(self, value):
        """设置进度值（0-100）"""
        self.bar['value'] = value
        self.percent.config(text=f"{int(value)}%")