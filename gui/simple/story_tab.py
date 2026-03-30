# gui/simple/story_tab.py
import tkinter as tk
from tkinter import scrolledtext

class StoryTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        
        # 故事文本编辑区
        tk.Label(self.frame, text="你的故事（请用讲故事的口吻写下来，越详细越好）").pack(anchor='w', padx=5, pady=(10,0))
        
        story_frame = tk.Frame(self.frame)
        story_frame.pack(fill='both', expand=True, padx=5, pady=2)
        
        self.text_widget = scrolledtext.ScrolledText(story_frame, wrap='word', height=15)
        self.text_widget.pack(side='left', fill='both', expand=True)
        
        # 字数统计
        self.word_count_label = tk.Label(story_frame, text="0字", anchor='e', width=10)
        self.word_count_label.pack(side='right', padx=5)
        self.text_widget.bind('<KeyRelease>', self.update_word_count)
        
        # 风格人设卡
        tk.Label(self.frame, text="风格人设卡（可选）").pack(anchor='w', padx=5, pady=(10,0))
        style_frame = tk.Frame(self.frame)
        style_frame.pack(fill='x', padx=5, pady=2)
        
        self.style_text = scrolledtext.ScrolledText(style_frame, wrap='word', height=3)
        self.style_text.pack(side='left', fill='both', expand=True)
        
        self.style_word_count = tk.Label(style_frame, text="0字", anchor='e', width=10)
        self.style_word_count.pack(side='right', padx=5)
        self.style_text.bind('<KeyRelease>', self.update_style_word_count)
        
        # 人设卡管理按钮
        btn_frame = tk.Frame(self.frame)
        btn_frame.pack(fill='x', padx=5, pady=2)
        tk.Button(btn_frame, text="▼预设", command=self.open_preset).pack(side='left', padx=2)
        tk.Button(btn_frame, text="✨一键生成", command=self.generate_style).pack(side='left', padx=2)
        tk.Button(btn_frame, text="💾保存", command=self.save_preset).pack(side='left', padx=2)
        
        # 绑定数据同步
        self.text_widget.bind('<<Modified>>', self.on_story_changed)
        self.style_text.bind('<<Modified>>', self.on_style_changed)
    
    def update_word_count(self, event=None):
        content = self.text_widget.get('1.0', 'end-1c')
        count = len(content)
        self.word_count_label.config(text=f"{count:,}字")
    
    def update_style_word_count(self, event=None):
        content = self.style_text.get('1.0', 'end-1c')
        count = len(content)
        self.style_word_count.config(text=f"{count:,}字")
    
    def on_story_changed(self, event=None):
        self.text_widget.edit_modified(False)
        content = self.text_widget.get('1.0', 'end-1c')
        self.controller.on_story_changed(content)
    
    def on_style_changed(self, event=None):
        self.style_text.edit_modified(False)
        content = self.style_text.get('1.0', 'end-1c')
        self.controller.on_style_changed(content)
    
    def open_preset(self):
        # 调用控制器的方法
        self.controller.open_style_preset()
    
    def generate_style(self):
        story = self.text_widget.get('1.0', 'end-1c').strip()
        self.controller.generate_style(story, self.style_text)
    
    def save_preset(self):
        style = self.style_text.get('1.0', 'end-1c').strip()
        self.controller.save_style_preset(style)