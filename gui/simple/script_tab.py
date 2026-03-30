# gui/simple/script_tab.py
import tkinter as tk
from tkinter import scrolledtext

class ScriptTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        
        # 使用文本框显示剧本（后续可改为树形结构）
        self.text_widget = scrolledtext.ScrolledText(self.frame, wrap='word', height=20)
        self.text_widget.pack(fill='both', expand=True, padx=5, pady=5)
        self.text_widget.config(state='disabled')
    
    def display_script(self, script_text):
        """更新剧本显示"""
        self.text_widget.config(state='normal')
        self.text_widget.delete('1.0', 'end')
        self.text_widget.insert('1.0', script_text)
        self.text_widget.config(state='disabled')