# gui/standard_video_panel.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import glob
import re

from utils import config_manager
from core.i2v.cfy_i2v import generate_single_video

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
        self.tree.bind('<Double-1>', lambda event: self.preview_shot())

        # 注册视频生成回调
        if hasattr(app, 'register_video_generation_callback'):
            app.register_video_generation_callback(self.on_video_generated)

    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.video_dir = os.path.join(work_dir, "视频")
        self.refresh()

    def run_i2v_workflow(self, work_dir, shots_info, resolution, log_callback, on_finish=None, selected_shots=None):
        if selected_shots:
            shots_info = [shot for shot in shots_info if shot['id'] in selected_shots]
            if not shots_info:
                log_callback("没有选中的镜头，请先选择")
                return False
            log_callback(f"将生成 {len(shots_info)} 个选中的镜头")
        import threading
        import os
        import time
        from tkinter import messagebox
        from utils import config_manager
        import core.i2v.cfy_i2v as cfy_i2v

        try:
            width, height = map(int, resolution.split('x'))
        except:
            log_callback("分辨率格式错误")
            return False

        video_dir = os.path.join(work_dir, "视频")
        os.makedirs(video_dir, exist_ok=True)

        # 检查首帧图
        images_dir = os.path.join(work_dir, "images")
        missing_shots = []
        for shot in shots_info:
            shot_id = shot['id']
            img_path = os.path.join(images_dir, f"{shot_id}.png")
            if not os.path.exists(img_path):
                missing_shots.append(shot_id)
        if missing_shots:
            log_callback(f"以下镜头缺少首帧图：{', '.join(missing_shots)}")
            messagebox.showerror("错误", "缺少首帧图，请先在图像面板生成")
            return False

        # 工作流模板
        workflow = self.app.workflow_var.get()
        if workflow == "WAN2.2":
            log_callback("WAN2.2 暂不支持图生视频，请选择 LTX2.3")
            messagebox.showerror("错误", "WAN2.2 不支持图生视频")
            return False
        else:
            template_file = "LTX2.3图生API.json"

        api_url = config_manager.COMFYUI_API_URL
        total = len(shots_info)
        completed = 0
        errors = []

        # 重试配置
        MAX_RETRIES = 3
        RETRY_DELAY = 2  # 秒

        def generate_with_retry(shot):
            shot_id = shot['id']
            image_path = os.path.join(images_dir, f"{shot_id}.png")
            prompt = shot.get('prompt', '')
            if not prompt:
                log_callback(f"镜头 {shot_id} 缺少提示词，跳过")
                return False
            duration = shot.get('duration', 10)
            for attempt in range(MAX_RETRIES):
                try:
                    video_path = cfy_i2v.generate_single_video(
                        work_dir=work_dir,
                        shot_id=shot_id,
                        image_path=image_path,
                        prompt=prompt,
                        duration=duration + 1,# 补偿 1 秒
                        target_duration=duration,   # 裁剪回原始时长
                        width=width,
                        height=height,
                        api_url=api_url,
                        log_callback=log_callback,
                        auto_trim=True
                    )
                    if video_path:
                        return True
                    else:
                        log_callback(f"镜头 {shot_id} 生成失败，第 {attempt+1} 次重试...")
                        time.sleep(RETRY_DELAY)
                except Exception as e:
                    log_callback(f"镜头 {shot_id} 异常: {e}，第 {attempt+1} 次重试...")
                    time.sleep(RETRY_DELAY)
            log_callback(f"镜头 {shot_id} 重试 {MAX_RETRIES} 次后仍然失败")
            return False

        def task():
            nonlocal completed
            for idx, shot in enumerate(shots_info, start=1):
                shot_id = shot['id']
                log_callback(f"💗💗💗正在生成镜头 {idx}/{total}：{shot_id}...")
                success = generate_with_retry(shot)
                if success:
                    completed += 1
                    log_callback(f"镜头 {shot_id} 生成成功")
                else:
                    errors.append(shot_id)
            log_callback(f"图生视频完成，成功 {completed}/{total}，失败: {errors}")
            if on_finish:
                on_finish()
            if errors:
                messagebox.showwarning("部分失败", f"以下镜头生成失败：{', '.join(errors)}")

        threading.Thread(target=task, daemon=True).start()
        return True

    def refresh(self):
        """刷新视频列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 确保工作目录已设置（优先使用 self.work_dir，否则从 app 获取）
        work_dir = self.work_dir or (self.app.work_dir if hasattr(self.app, 'work_dir') else None)
        if not work_dir:
            self.tree.insert('', 'end', values=('', '未设置工作目录', ''))
            return

        # 确保视频目录存在
        video_dir = os.path.join(work_dir, "视频")
        if not os.path.isdir(video_dir):
            self.tree.insert('', 'end', values=('', '未找到视频文件夹', ''))
            return

        # 强制重新从易读版文件读取镜头信息（确保最新，不依赖 app.shots_info 缓存）
        pattern = os.path.join(work_dir, "分镜结果_易读版_*.txt")
        files = glob.glob(pattern)
        shots_info = None
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
        for f in os.listdir(video_dir):
            if f.startswith("镜头") and (f.endswith(".mp4") or f.endswith(".gif")):
                shot_id = f[2:].rsplit('.', 1)[0]
                video_files[shot_id] = os.path.join(video_dir, f)

        self.shots = []
        for shot in shots_info:
            shot_id = shot['id']
            description = shot.get('visual', '')[:60]   # 视觉描述（用于列表显示）
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