# gui/simple/prompts_tab.py
import tkinter as tk
from tkinter import scrolledtext

class PromptsTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        
        self.text_widget = scrolledtext.ScrolledText(self.frame, wrap='word', height=20)
        self.text_widget.pack(fill='both', expand=True, padx=5, pady=5)
        self.text_widget.config(state='disabled')
    
    def display_prompts(self, prompts_list):
        """显示提示词列表"""
        self.text_widget.config(state='normal')
        self.text_widget.delete('1.0', 'end')
        for idx, prompt in enumerate(prompts_list, 1):
            self.text_widget.insert('end', f"【镜头 {idx}】\n")
            self.text_widget.insert('end', f"{prompt}\n\n")
        self.text_widget.config(state='disabled')
        # 不再调用 self.app.log，避免属性错误