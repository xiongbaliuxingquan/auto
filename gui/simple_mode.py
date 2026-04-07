# gui/simple_mode.py
import tkinter as tk
from tkinter import ttk
import os
import json
import glob
import re
from datetime import datetime
from utils import config_manager

class SimpleMode:
    def __init__(self, parent_frame, app):
        self.app = app
        self.frame = tk.Frame(parent_frame)
        self.work_dir = None

        # 先初始化属性
        self.storyboard_tab = None
        self.is_i2v_mode = False
        self.gen_asset_img_btn = None
        self.gen_storyboard_btn = None

        # 创建数据模型和控制器
        from gui.simple.data import SimpleModeData
        from gui.simple.controller import SimpleModeController

        self.data = SimpleModeData()
        self.controller = SimpleModeController(self, self.data, self.app)

        self.create_ui()
        self.frame.pack_propagate(False)
        self.frame.config(height=600)
        self.frame.pack(fill='both', expand=True)
        self.current_video_dir = None

    def _parse_shots_to_scenes(self, shots_path):
        """解析 shots.txt 为 scenes 列表"""
        import re
        with open(shots_path, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = re.split(r'\n\s*={5,}\s*\n', content.strip())
        scenes_dict = {}
        for block in blocks:
            if not block.strip():
                continue
            header_match = re.search(r'【镜头(\d+)-(\d+)：([^】]*)】', block)
            if not header_match:
                continue
            scene_id = int(header_match.group(1))
            shot_id = int(header_match.group(2))
            title = header_match.group(3).strip()
            shot = {
                'title': title,
                'scene': '',
                'roles': [],
                'action': '',
                'dialogue': '',
                'visual': '',
                'duration': 10.0,
                'emotion': '',
                'region': '全球·无明确时代'
            }
            lines = block.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('- 场景：'):
                    shot['scene'] = line.split('：', 1)[-1].strip()
                elif line.startswith('- 角色：'):
                    roles_str = line.split('：', 1)[-1].strip()
                    shot['roles'] = [r.strip() for r in roles_str.split(',')]
                elif line.startswith('- 动作：'):
                    shot['action'] = line.split('：', 1)[-1].strip()
                elif line.startswith('- 对白：'):
                    shot['dialogue'] = line.split('：', 1)[-1].strip()
                elif line.startswith('- 视觉描述：'):
                    shot['visual'] = line.split('：', 1)[-1].strip()
                elif line.startswith('- 时长：'):
                    dur_str = line.split('：', 1)[-1].strip()
                    try:
                        shot['duration'] = float(dur_str.replace('秒', ''))
                    except:
                        pass
                elif line.startswith('- 情绪基调：'):
                    shot['emotion'] = line.split('：', 1)[-1].strip()
                elif line.startswith('- 地域：'):
                    shot['region'] = line.split('：', 1)[-1].strip()
            if scene_id not in scenes_dict:
                scenes_dict[scene_id] = {'id': scene_id, 'title': f"场次{scene_id}", 'shots': []}
            scenes_dict[scene_id]['shots'].append(shot)
        scenes = [scenes_dict[k] for k in sorted(scenes_dict.keys())]
        return scenes

    def load_project(self, folder):
        """从历史项目目录加载数据"""
        self.work_dir = folder
        # 加载故事文本
        story_path = os.path.join(folder, "story.txt")
        if os.path.exists(story_path):
            with open(story_path, 'r', encoding='utf-8') as f:
                story = f.read()
            self.story_tab.text_widget.delete('1.0', 'end')
            self.story_tab.text_widget.insert('1.0', story)
            self.story_tab.update_word_count()
            self.data.story_text = story

        # 加载元数据
        metadata_path = os.path.join(folder, "metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                self.data.metadata = json.load(f)

        # 加载剧本（shots.txt）
        shots_path = os.path.join(folder, "shots.txt")
        if os.path.exists(shots_path):
            scenes = self._parse_shots_to_scenes(shots_path)
            if scenes:
                self.script_tab.update_script_data(scenes)
            else:
                with open(shots_path, 'r', encoding='utf-8') as f:
                    shots_content = f.read()
                self.script_tab.display_raw_text(shots_content)
        else:
            self.script_tab.tree.delete(*self.script_tab.tree.get_children())
            self.script_tab.tree.insert('', 'end', values=('', '', '未找到 shots.txt', '请先生成剧本'))

        # 加载资产库（纯文本文件）
        if hasattr(self, 'assets_tab'):
            self.assets_tab.work_dir = folder
            self.assets_tab.refresh_file_list()

        # 启用相应按钮
        self.set_button_state('normal', 'disabled', 'disabled', 'disabled')

        # 如果资产库文件存在（即已生成剧本），启用生成提示词按钮
        global_assets = os.path.join(folder, "assets_global.txt")
        para_assets = glob.glob(os.path.join(folder, "assets_paragraph_*.txt"))
        if os.path.exists(global_assets) and para_assets:
            self.gen_prompts_btn.config(state='normal')

        # 尝试加载历史提示词
        pattern = os.path.join(folder, "分镜结果_易读版_*.txt")
        readable_files = glob.glob(pattern)
        if readable_files:
            latest = max(readable_files, key=os.path.getmtime)
            try:
                with open(latest, 'r', encoding='utf-8') as f:
                    content = f.read()
                blocks = re.split(r'\n\s*={5,}\s*\n', content.strip())
                prompts = []  # 存储 (shot_id, prompt)
                for block in blocks:
                    if not block.strip():
                        continue
                    # 提取镜头ID
                    header_match = re.search(r'【镜头(\d+-\d+)：', block)
                    shot_id = header_match.group(1) if header_match else "未知"
                    idx = block.find('- 提示词：')
                    if idx != -1:
                        prompt_text = block[idx + len('- 提示词：'):].strip()
                        prompts.append((shot_id, prompt_text))
                    else:
                        prompts.append((shot_id, "[未找到提示词]"))
                self.data.prompts = prompts
                self.prompts_tab.display_prompts(prompts)
                self.app.log(f"已加载历史提示词（共 {len(prompts)} 个镜头）")
                self.gen_prompts_btn.config(state='normal')
                self.gen_video_btn.config(state='normal')
            except Exception as e:
                self.app.log(f"加载历史提示词失败: {e}")
                
        # 刷新视频面板
        if hasattr(self, 'video_tab'):
            self.video_tab.set_work_dir(folder)

        # 同步分镜图库的工作目录
        if self.storyboard_tab:
            self.storyboard_tab.set_work_dir(self.work_dir)

        self.current_video_dir = os.path.join(self.work_dir, "视频")
    
    def create_ui(self):
        # 顶部：标题输入和高级向导
        top_frame = tk.Frame(self.frame)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        tk.Label(top_frame, text="故事标题：").pack(side='left')
        self.title_entry = tk.Entry(top_frame, width=30)
        self.title_entry.pack(side='left', padx=5)
        
        self.wizard_btn = tk.Button(top_frame, text="故事创作向导", command=self.controller.open_wizard)
        self.wizard_btn.pack(side='left', padx=5)
        
        # 先创建按钮栏，固定在底部
        self.btn_frame = tk.Frame(self.frame)
        self.btn_frame.pack(side='bottom', fill='x', padx=5, pady=5)

        # 标签页
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        from gui.simple.story_tab import StoryTab
        self.story_tab = StoryTab(self.notebook, self.controller)
        self.notebook.add(self.story_tab.frame, text="故事")
        
        from gui.simple.script_tab import ScriptTab
        self.script_tab = ScriptTab(self.notebook, self.controller)
        self.notebook.add(self.script_tab.frame, text="剧本")
        
        from gui.simple.assets_tab import AssetsTab
        self.assets_tab = AssetsTab(self.notebook, self.controller)
        self.notebook.add(self.assets_tab.frame, text="资产库")
        
        from gui.simple.prompts_tab import PromptsTab
        self.prompts_tab = PromptsTab(self.notebook, self.controller)
        self.notebook.add(self.prompts_tab.frame, text="提示词")

        from gui.simple.video_tab import VideoTab
        self.video_tab = VideoTab(self.notebook, self.controller, self.app)
        self.notebook.add(self.video_tab.frame, text="视频")

      
        self.gen_script_btn = tk.Button(self.btn_frame, text="1. 生成剧本", command=self.controller.generate_script, width=15)
        self.gen_script_btn.pack(side='left', padx=2)

        self.gen_asset_img_btn = tk.Button(self.btn_frame, text="2. 生成资产图", command=self.controller.generate_asset_images, width=15)
        self.gen_asset_img_btn.pack_forget()  # 初始隐藏

        self.gen_storyboard_btn = tk.Button(self.btn_frame, text="3. 生成分镜图", command=self.controller.generate_storyboard, width=15)
        self.gen_storyboard_btn.pack_forget()  # 初始隐藏

        self.gen_prompts_btn = tk.Button(self.btn_frame, text="2. 生成提示词", command=self.controller.generate_prompts, width=15)
        self.gen_prompts_btn.pack(side='left', padx=2)

        self.gen_video_btn = tk.Button(self.btn_frame, text="3. 生成视频", command=self.controller.confirm_and_generate, width=20)
        self.gen_video_btn.pack(side='left', padx=2)

        self.merge_video_btn = tk.Button(self.btn_frame, text="4. 合并视频", command=self.controller.merge_videos, width=15)
        self.merge_video_btn.pack(side='left', padx=2)

        self.continue_btn = tk.Button(self.btn_frame, text="意外断开继续生成", command=self.controller.continue_generation, state='disabled', width=16)
        self.continue_btn.pack(side='right', padx=2)
        
        # 倒计时标签（初始不显示）
        self.countdown_label = tk.Label(self.frame, text="", font=('Arial', 16, 'bold'), fg='red')
        # 不 pack

    def set_i2v_mode(self, is_i2v):
        if self.is_i2v_mode == is_i2v:
            return
        self.is_i2v_mode = is_i2v

        if is_i2v:
            # 图生模式：显示资产图和分镜图按钮，并插入到提示词按钮之前
            self.gen_asset_img_btn.pack(side='left', padx=2, before=self.gen_prompts_btn)
            self.gen_storyboard_btn.pack(side='left', padx=2, before=self.gen_prompts_btn)
            self.gen_prompts_btn.config(text="4. 生成视频提示词")
            self.gen_video_btn.config(text="5. 生成视频")
            # 添加分镜图库标签页
            if self.storyboard_tab is None:
                from gui.simple.i2v.storyboard_tab import StoryboardTab
                self.storyboard_tab = StoryboardTab(self.notebook, self.controller)
                asset_index = self.notebook.index(self.assets_tab.frame)
                self.notebook.insert(asset_index + 1, self.storyboard_tab.frame, text="分镜图库")
                if self.work_dir:
                    self.storyboard_tab.set_work_dir(self.work_dir)
        else:
            # 文生模式：隐藏资产图和分镜图按钮
            self.gen_asset_img_btn.pack_forget()
            self.gen_storyboard_btn.pack_forget()
            self.gen_prompts_btn.config(text="2. 生成提示词")
            self.gen_video_btn.config(text="3. 生成视频")
            # 移除分镜图库标签页
            if self.storyboard_tab is not None:
                self.notebook.forget(self.storyboard_tab.frame)
                self.storyboard_tab = None

    # 以下方法供控制器调用，用于更新 UI 状态
    def set_button_state(self, gen_script_state, gen_prompts_state, gen_video_state, merge_state):
        self.gen_script_btn.config(state=gen_script_state)
        self.gen_prompts_btn.config(state=gen_prompts_state)
        self.gen_video_btn.config(state=gen_video_state)
        self.merge_video_btn.config(state=merge_state)
        if hasattr(self, 'continue_btn'):
            self.continue_btn.config(state='normal')
    
    def show_countdown(self, seconds):
        self.countdown_label.pack_forget()
        self.countdown_label.config(text=f"⏳ {seconds}秒后自动运行工作流，点击「选择或编辑提示词」可暂停")
        self.countdown_label.pack(before=self.gen_script_btn, pady=(5,0))
    
    def hide_countdown(self):
        self.countdown_label.pack_forget()
    
    def set_paused(self):
        self.countdown_label.config(text="⏸️ 已暂停，请编辑后手动运行工作流", fg='orange')