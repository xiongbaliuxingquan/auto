# gui/simple_mode.py
import tkinter as tk
from tkinter import ttk

class SimpleMode:
    def __init__(self, parent_frame, app):
        self.app = app
        self.frame = tk.Frame(parent_frame)
        
        # 创建数据模型和控制器
        from gui.simple.data import SimpleModeData
        from gui.simple.controller import SimpleModeController
        
        self.data = SimpleModeData()
        self.controller = SimpleModeController(self, self.data, self.app)
        
        self.create_ui()
        self.frame.pack(fill='both', expand=True)
    
    def create_ui(self):
        # 顶部：标题输入和高级向导
        top_frame = tk.Frame(self.frame)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        tk.Label(top_frame, text="故事标题：").pack(side='left')
        self.title_entry = tk.Entry(top_frame, width=30)
        self.title_entry.pack(side='left', padx=5)
        
        self.wizard_btn = tk.Button(top_frame, text="高级向导", command=self.controller.open_wizard)
        self.wizard_btn.pack(side='left', padx=5)
        
        # 标签页
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 故事标签页
        from gui.simple.story_tab import StoryTab
        self.story_tab = StoryTab(self.notebook, self.controller)
        self.notebook.add(self.story_tab.frame, text="故事")
        
        # 剧本标签页
        from gui.simple.script_tab import ScriptTab
        self.script_tab = ScriptTab(self.notebook, self.controller)
        self.notebook.add(self.script_tab.frame, text="剧本")
        
        # 资产库标签页
        from gui.simple.assets_tab import AssetsTab
        self.assets_tab = AssetsTab(self.notebook, self.controller)
        self.notebook.add(self.assets_tab.frame, text="资产库")
        
        # 提示词标签页
        from gui.simple.prompts_tab import PromptsTab
        self.prompts_tab = PromptsTab(self.notebook, self.controller)
        self.notebook.add(self.prompts_tab.frame, text="提示词")
        
        # 底部按钮栏
        btn_frame = tk.Frame(self.frame)
        btn_frame.pack(fill='x', padx=5, pady=5)
        
        self.gen_script_btn = tk.Button(btn_frame, text="1. 生成剧本", command=self.controller.generate_script, width=15)
        self.gen_script_btn.pack(side='left', padx=2)
        
        self.extract_assets_btn = tk.Button(btn_frame, text="2. 提取资产", command=self.controller.extract_assets, width=15, state='disabled')
        self.extract_assets_btn.pack(side='left', padx=2)
        
        self.gen_prompts_btn = tk.Button(btn_frame, text="3. 生成提示词", command=self.controller.generate_prompts, width=15, state='disabled')
        self.gen_prompts_btn.pack(side='left', padx=2)
        
        self.confirm_btn = tk.Button(btn_frame, text="✅ 确认并生成视频", command=self.controller.confirm_and_generate, width=20, state='disabled')
        self.confirm_btn.pack(side='left', padx=2)
        
        # 倒计时标签（原有，用于显示倒计时）
        self.countdown_label = tk.Label(self.frame, text="", font=('Arial', 16, 'bold'), fg='red')
        self.countdown_label.pack(pady=(5,0))
        self.countdown_label.pack_forget()
    
    # 以下方法供控制器调用，用于更新 UI 状态
    def set_button_state(self, gen_script_state, extract_assets_state, gen_prompts_state, confirm_state):
        self.gen_script_btn.config(state=gen_script_state)
        self.extract_assets_btn.config(state=extract_assets_state)
        self.gen_prompts_btn.config(state=gen_prompts_state)
        self.confirm_btn.config(state=confirm_state)
    
    def show_countdown(self, seconds):
        self.countdown_label.config(text=f"⏳ {seconds}秒后自动运行工作流，点击「选择或编辑提示词」可暂停")
        self.countdown_label.pack(before=self.gen_script_btn, pady=(5,0))
    
    def hide_countdown(self):
        self.countdown_label.pack_forget()
    
    def set_paused(self):
        self.countdown_label.config(text="⏸️ 已暂停，请编辑后手动运行工作流", fg='orange')