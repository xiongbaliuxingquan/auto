# gui/simple/video_tab.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import glob
import re

class VideoTab:
    def __init__(self, parent, controller, app):
        self.controller = controller
        self.app = app
        self.frame = tk.Frame(parent)
        self.work_dir = None
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

    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.refresh_video_list()

    def refresh_video_list(self):
        """刷新视频列表"""
        if not self.work_dir:
            return
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 1. 解析易读版分镜文件，获取镜头ID和描述
        pattern = os.path.join(self.work_dir, "分镜结果_易读版_*.txt")
        readable_files = glob.glob(pattern)
        if not readable_files:
            self.tree.insert('', 'end', values=('', '未找到易读版分镜文件', ''))
            return
        readable_file = max(readable_files, key=os.path.getmtime)
        shots_info = self._parse_readable_file(readable_file)

        # 2. 扫描视频文件
        video_dir = os.path.join(self.work_dir, "视频")
        video_files = {}
        if os.path.isdir(video_dir):
            for f in os.listdir(video_dir):
                if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                    shot_id = f[2:].rsplit('.', 1)[0]
                    video_files[shot_id] = os.path.join(video_dir, f)

        # 3. 合并数据并显示
        self.shots = []
        for shot in shots_info:
            shot_id = shot['id']
            description = shot.get('visual', '')[:60]  # 取视觉描述前60字
            video_path = video_files.get(shot_id)
            status = "已生成" if video_path else "待生成"
            self.shots.append({
                'id': shot_id,
                'description': description,
                'video_path': video_path,
                'status': status
            })
            self.tree.insert('', 'end', values=(shot_id, description, status))

        # 如果没有视频，则显示提示
        if not video_files:
            self.tree.insert('', 'end', values=('', '未找到视频文件，请先生成视频', ''))

    def _parse_readable_file(self, readable_path):
        """解析易读版分镜文件，返回镜头列表，每个镜头包含 id, visual"""
        shots = []
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
            # 提取视觉描述
            visual_match = re.search(r'- 视觉描述：\s*(.*?)(?=\n-|\Z)', block, re.DOTALL)
            visual = visual_match.group(1).strip() if visual_match else ""
            shots.append({'id': shot_id, 'visual': visual})
        return shots

    def on_select(self, event):
        """选中某行时启用预览和重试按钮"""
        selection = self.tree.selection()
        if selection:
            self.preview_btn.config(state='normal')
            self.retake_btn.config(state='normal')
        else:
            self.preview_btn.config(state='disabled')
            self.retake_btn.config(state='disabled')

    def preview_shot(self):
        """预览当前选中的镜头视频"""
        selection = self.tree.selection()
        if not selection:
            return
        index = self.tree.index(selection[0])
        if index >= len(self.shots):
            return
        shot = self.shots[index]
        if shot['video_path'] and os.path.exists(shot['video_path']):
            # 使用系统默认播放器打开
            os.startfile(shot['video_path'])
        else:
            messagebox.showwarning("提示", f"镜头 {shot['id']} 未找到视频文件")

    def retake_shot(self):
        """重试生成当前选中的镜头"""
        selection = self.tree.selection()
        if not selection:
            return
        index = self.tree.index(selection[0])
        if index >= len(self.shots):
            return
        shot = self.shots[index]
        # TODO: 调用单个镜头重试逻辑
        messagebox.showinfo("提示", f"镜头 {shot['id']} 重试功能待实现")

    def on_video_generated(self, shot_id):
        """当镜头生成完成时调用，刷新列表（带防抖）"""
        if hasattr(self, '_refresh_after_id'):
            self.frame.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.frame.after(500, self.refresh_video_list)