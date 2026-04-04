# gui/standard_video_panel.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import glob
import re

class StandardVideoPanel:
    def __init__(self, parent, app):
        self.app = app
        self.frame = tk.Frame(parent)
        self.work_dir = None
        self.video_dir = None
        self.shots = []

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

        self.refresh_btn = tk.Button(btn_frame, text="刷新", command=self.refresh)
        self.refresh_btn.pack(side='left', padx=2)

        self.tree.bind('<<TreeviewSelect>>', self.on_select)

        # 注册视频生成回调
        if hasattr(app, 'register_video_generation_callback'):
            app.register_video_generation_callback(self.on_video_generated)

    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.video_dir = os.path.join(work_dir, "视频")
        self.refresh()

    def refresh(self):
        """刷新视频列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.work_dir or not os.path.isdir(self.video_dir):
            self.tree.insert('', 'end', values=('', '未找到视频文件夹', ''))
            return

        # 获取镜头信息（优先从 app.shots_info）
        shots_info = self.app.shots_info
        if not shots_info:
            # 降级：从易读版分镜文件读取
            pattern = os.path.join(self.work_dir, "分镜结果_易读版_*.txt")
            files = glob.glob(pattern)
            if files:
                readable_file = max(files, key=os.path.getmtime)
                from core.comfyui_manager import ComfyUIManager
                temp_manager = ComfyUIManager("", "")
                shots_info = temp_manager.get_shots_info(readable_file)

        if not shots_info:
            self.tree.insert('', 'end', values=('', '未找到镜头信息', ''))
            return

        # 扫描视频文件
        video_files = {}
        for f in os.listdir(self.video_dir):
            if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                shot_id = f[2:].rsplit('.', 1)[0]
                video_files[shot_id] = os.path.join(self.video_dir, f)

        self.shots = []
        for shot in shots_info:
            shot_id = shot['id']
            description = shot.get('visual', '')[:60]  # 使用视觉描述
            video_path = video_files.get(shot_id)
            status = "已生成" if video_path else "待生成"
            self.shots.append({
                'id': shot_id,
                'description': description,
                'video_path': video_path,
                'status': status
            })
            self.tree.insert('', 'end', values=(shot_id, description, status))

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
            messagebox.showwarning("提示", f"镜头 {shot['id']} 未找到视频文件")

    def retake_shot(self):
        selection = self.tree.selection()
        if not selection:
            return
        index = self.tree.index(selection[0])
        if index >= len(self.shots):
            return
        shot = self.shots[index]
        if hasattr(self.app, 'retake_single_shot'):
            self.app.retake_single_shot(shot['id'])
        else:
            messagebox.showwarning("提示", "重试功能未实现")

    def on_video_generated(self, shot_id):
        if hasattr(self, '_refresh_after_id'):
            self.frame.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.frame.after(500, self.refresh)