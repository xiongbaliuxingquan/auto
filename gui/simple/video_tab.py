# gui/simple/video_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import glob
import re
import json  # 添加缺失的导入

class VideoTab:
    def __init__(self, parent, controller, app):
        self.controller = controller
        self.app = app
        self.frame = tk.Frame(parent)
        self.work_dir = None
        self.video_dir = None  # 明确初始化
        self.shots = []  # 存储每个镜头的完整信息

        # 表格
        columns = ('shot_id', 'description', 'status')
        self.tree = ttk.Treeview(self.frame, columns=columns, show='headings', height=15)
        self.tree.heading('shot_id', text='镜号')
        self.tree.heading('description', text='镜头描述')
        self.tree.heading('status', text='状态')
        self.tree.column('shot_id', width=80, anchor='center')
        self.tree.column('description', width=400)
        self.tree.column('status', width=80, anchor='center')

        scrollbar = ttk.Scrollbar(self.frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 按钮区域
        btn_frame = tk.Frame(self.frame)
        btn_frame.pack(fill='x', pady=5)

        self.preview_btn = tk.Button(btn_frame, text="预览", command=self.preview_shot, state='disabled')
        self.preview_btn.pack(side='left', padx=2)

        self.retake_btn = tk.Button(btn_frame, text="重试", command=self.retake_shot, state='disabled')
        self.retake_btn.pack(side='left', padx=2)

        self.refresh_btn = tk.Button(btn_frame, text="刷新", command=self.refresh_video_list)
        self.refresh_btn.pack(side='left', padx=2)

        # 绑定选中事件
        self.tree.bind('<<TreeviewSelect>>', self.on_select)

        # 注册视频生成回调
        if hasattr(app, 'register_video_generation_callback'):
            app.register_video_generation_callback(self.on_video_generated)

    def set_retake_button_state(self, enabled):
        """设置重试按钮的状态"""
        state = 'normal' if enabled else 'disabled'
        if hasattr(self, 'retake_btn'):
            self.retake_btn.config(state=state)

    def set_video_dir(self, video_dir):
        """设置当前视频文件夹路径并刷新"""
        self.video_dir = video_dir
        self.refresh_video_list()

    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        # 直接设置为工作目录下的“视频”文件夹
        self.video_dir = os.path.join(work_dir, "视频")
        self.refresh_video_list()

    def _get_shot_description(self, shot_id):
        """从易读版分镜文件中获取指定镜头的视觉描述"""
        pattern = os.path.join(self.work_dir, "分镜结果_易读版_*.txt")
        readable_files = glob.glob(pattern)
        if not readable_files:
            return ""
        readable_file = max(readable_files, key=os.path.getmtime)
        shots_info = self._parse_readable_file(readable_file)
        for shot in shots_info:
            if shot['id'] == shot_id:
                return shot['visual'][:60]
        return ""

    def _scan_video_files(self):
            # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 获取易读版文件
        readable_path = self._get_latest_readable()
        if not readable_path:
            self.app.log("[ERROR] 未找到易读版分镜文件")
            self.tree.insert('', 'end', values=('', '未找到易读版分镜文件', ''))
            return
        
        shots_info = self._parse_readable_file(readable_path)
        if not shots_info:
            self.app.log("[ERROR] 解析易读版文件失败，无镜头信息")
            self.tree.insert('', 'end', values=('', '解析易读版文件失败', ''))
            return
        
        # 扫描视频文件
        video_files = {}
        if os.path.isdir(self.video_dir):
            for f in os.listdir(self.video_dir):
                if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                    shot_id = f[2:].rsplit('.', 1)[0]
                    video_files[shot_id] = os.path.join(self.video_dir, f)
        
        self.shots = []
        for shot in shots_info:
            shot_id = shot['id']
            description = shot.get('visual', '')[:60]
            video_path = video_files.get(shot_id)
            exists = video_path is not None and os.path.exists(video_path)
            status = "已生成" if exists else "待生成"
            self.shots.append({
                'id': shot_id,
                'description': description,
                'video_path': video_path if exists else None,
                'status': status
            })
            self.tree.insert('', 'end', values=(shot_id, description, status))

    def _get_latest_readable(self):
        if not self.work_dir:
            return None
        pattern = os.path.join(self.work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        return max(files, key=os.path.getmtime) if files else None

    def refresh_video_list(self):
        # 检查 video_dir 是否存在
        if not hasattr(self, 'video_dir') or self.video_dir is None:
            return
        if not os.path.isdir(self.video_dir):
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.tree.insert('', 'end', values=('', '未找到视频文件夹', ''))
            return

        # 直接扫描文件夹，不依赖 manifest
        self._scan_video_files()

    def _parse_readable_file(self, readable_path):
        """解析易读版分镜文件，返回镜头列表，每个镜头包含 id, visual"""
        shots = []
        if not readable_path or not os.path.exists(readable_path):
            return shots
        with open(readable_path, 'r', encoding='utf-8') as f:
            content = f.read()
        blocks = re.split(r'\n\s*={5,}\s*\n', content.strip())
        for block in blocks:
            if not block.strip():
                continue
            header_match = re.search(r'【镜头(\d+-\d+)：', block)
            if not header_match:
                continue
            shot_id = header_match.group(1)
            visual_match = re.search(r'- 视觉描述：\s*(.*?)(?=\n-|\Z)', block, re.DOTALL)
            visual = visual_match.group(1).strip() if visual_match else ""
            shots.append({'id': shot_id, 'visual': visual})
        return shots

    def on_select(self, event):
        selection = self.tree.selection()
        if selection:
            self.preview_btn.config(state='normal')
            self.retake_btn.config(state='normal')
        else:
            self.preview_btn.config(state='disabled')
            self.retake_btn.config(state='disabled')

    def preview_shot(self):
        selection = self.tree.selection()
        if not selection:
            return
        index = self.tree.index(selection[0])
        if index >= len(self.shots):
            return
        shot = self.shots[index]
        if shot['video_path'] and os.path.exists(shot['video_path']):
            os.startfile(shot['video_path'])
        else:
            # 文件不存在，提示并刷新列表
            messagebox.showwarning("提示", f"镜头 {shot['id']} 视频文件不存在，可能已被移动或删除。\n请尝试点击「刷新」按钮。")
            self.refresh_video_list()

    def retake_shot(self):
        selection = self.tree.selection()
        if not selection:
            return
        index = self.tree.index(selection[0])
        if index >= len(self.shots):
            return
        shot = self.shots[index]
        if not shot['id']:
            return
        if hasattr(self.controller, 'retake_single_shot'):
            self.controller.retake_single_shot(shot['id'])
        else:
            messagebox.showwarning("提示", "重试功能未实现")

    def on_video_generated(self, shot_id):
        if hasattr(self, '_refresh_after_id'):
            self.frame.after_cancel(self._refresh_after_id)
        # 立即刷新一次
        self.refresh_video_list()
        # 延迟再刷新一次，确保文件系统同步
        self._refresh_after_id = self.frame.after(1000, self.refresh_video_list)