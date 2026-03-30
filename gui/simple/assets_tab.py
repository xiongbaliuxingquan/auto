# gui/simple/assets_tab.py
import tkinter as tk
from tkinter import ttk, scrolledtext

class AssetsTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        
        # 创建垂直可调整的 PanedWindow
        self.paned = ttk.PanedWindow(self.frame, orient=tk.VERTICAL)
        self.paned.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 人物设定区域
        persona_frame = ttk.Frame(self.paned)
        self.paned.add(persona_frame, weight=1)
        ttk.Label(persona_frame, text="人物设定").pack(anchor='w', padx=5, pady=(5,0))
        self.persona_text = scrolledtext.ScrolledText(persona_frame, wrap='word', height=8)
        self.persona_text.pack(fill='both', expand=True, padx=5, pady=2)
        self.persona_text.config(state='normal')
        self.persona_text.bind('<<Modified>>', self.on_persona_changed)
        
        # 场景设定区域
        scene_frame = ttk.Frame(self.paned)
        self.paned.add(scene_frame, weight=1)
        ttk.Label(scene_frame, text="场景设定").pack(anchor='w', padx=5, pady=(5,0))
        self.scene_text = scrolledtext.ScrolledText(scene_frame, wrap='word', height=6)
        self.scene_text.pack(fill='both', expand=True, padx=5, pady=2)
        self.scene_text.config(state='normal')
        self.scene_text.bind('<<Modified>>', self.on_scene_changed)
        
        # 视觉风格区域
        style_frame = ttk.Frame(self.paned)
        self.paned.add(style_frame, weight=1)
        ttk.Label(style_frame, text="视觉风格").pack(anchor='w', padx=5, pady=(5,0))
        self.style_text = scrolledtext.ScrolledText(style_frame, wrap='word', height=4)
        self.style_text.pack(fill='both', expand=True, padx=5, pady=2)
        self.style_text.config(state='normal')
        self.style_text.bind('<<Modified>>', self.on_style_changed)
        
    def update_content(self, persona, scene, style):
        """更新三个区域的内容"""
        self.persona_text.config(state='normal')
        self.persona_text.delete('1.0', 'end')
        self.persona_text.insert('1.0', persona)
        self.persona_text.config(state='normal')  # 保持可编辑
        self.persona_text.edit_modified(False)
        
        self.scene_text.config(state='normal')
        self.scene_text.delete('1.0', 'end')
        self.scene_text.insert('1.0', scene)
        self.scene_text.config(state='normal')
        self.scene_text.edit_modified(False)
        
        self.style_text.config(state='normal')
        self.style_text.delete('1.0', 'end')
        self.style_text.insert('1.0', style)
        self.style_text.config(state='normal')
        self.style_text.edit_modified(False)
    
    def on_persona_changed(self, event=None):
        self.persona_text.edit_modified(False)
        content = self.persona_text.get('1.0', 'end-1c')
        self.controller.on_assets_changed('persona', content)
    
    def on_scene_changed(self, event=None):
        self.scene_text.edit_modified(False)
        content = self.scene_text.get('1.0', 'end-1c')
        self.controller.on_assets_changed('scene', content)
    
    def on_style_changed(self, event=None):
        self.style_text.edit_modified(False)
        content = self.style_text.get('1.0', 'end-1c')
        self.controller.on_assets_changed('style', content)