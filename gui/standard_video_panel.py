# gui/standard_video_panel.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import glob
import re
import threading
import shutil
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
from core.i2v.digital_human import generate_digital_human_full
from core.i2v.generate_asset_image import generate_asset_image

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

        # 缩略图显示区域（放在按钮下方）
        thumb_frame = tk.Frame(self.frame, height=120)
        thumb_frame.pack(fill='x', padx=5, pady=(0,5))
        thumb_frame.pack_propagate(False)

        tk.Label(thumb_frame, text="数字人形象预览:", anchor='w').pack(anchor='w')
        self.thumb_label = tk.Label(thumb_frame, bg='lightgray', width=20, height=6)
        self.thumb_label.pack(fill='both', expand=True, pady=2)

        self.digital_human_image_path = None

    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.video_dir = os.path.join(work_dir, "视频")
        self.refresh()
        self._load_existing_dh_image()

    def _load_existing_dh_image(self):
        """加载工作目录中可能已存在的数字人图片"""
        if not self.work_dir:
            return
        img_path = os.path.join(self.work_dir, "digital_human.png")
        if os.path.exists(img_path):
            self.digital_human_image_path = img_path
            self._update_thumbnail(img_path)
            self.app.start_dh_btn.config(state='normal')
        else:
            self.thumb_label.config(image='', text="未上传")
            self.digital_human_image_path = None
            self.app.start_dh_btn.config(state='disabled')

    def _update_thumbnail(self, img_path):
        """更新缩略图显示"""
        try:
            img = Image.open(img_path)
            img.thumbnail((160, 90))
            photo = ImageTk.PhotoImage(img)
            self.thumb_label.config(image=photo, text="")
            self.thumb_label.image = photo
        except Exception as e:
            self.thumb_label.config(image='', text="加载失败")
            print(f"缩略图加载失败: {e}")

    def upload_digital_human_image(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先打开或创建项目")
            return
        file_path = filedialog.askopenfilename(
            title="选择数字人形象图片",
            filetypes=[("Image files", "*.png *.jpg *.jpeg")]
        )
        if not file_path:
            return
        target_path = os.path.join(self.work_dir, "digital_human.png")
        shutil.copy2(file_path, target_path)
        self.digital_human_image_path = target_path
        self._update_thumbnail(target_path)
        self.app.start_dh_btn.config(state='normal')
        self.app.log("数字人图片已设置")

    def make_digital_human_image(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先打开或创建项目")
            return
        full_prompt = self._prompt_digital_human_image()
        if not full_prompt:
            return
        self.app.make_dh_img_btn.config(state='disabled', text="生成中...")
        self.app.log("正在生成数字人形象图片，请稍候...")
        def task():
            try:
                save_path = os.path.join(self.work_dir, "digital_human.png")
                result = generate_asset_image(
                    work_dir=self.work_dir,
                    character_name="digital_human",
                    character_desc="",
                    scene_desc="",
                    style_desc="",
                    custom_prompt=full_prompt,
                    width=1024,
                    height=1024,
                    output_filename="digital_human.png",
                    log_callback=self.app.log
                )
                if result:
                    self.digital_human_image_path = save_path
                    self.frame.after(0, lambda: self._update_thumbnail(save_path))
                    self.frame.after(0, lambda: self.app.start_dh_btn.config(state='normal'))
                    self.frame.after(0, lambda: self.app.log("数字人形象图片生成成功"))
                else:
                    self.frame.after(0, lambda: messagebox.showerror("错误", "生成失败，请查看日志"))
            except Exception as e:
                self.frame.after(0, lambda: self.app.log(f"生成异常: {e}"))
            finally:
                self.frame.after(0, lambda: self.app.make_dh_img_btn.config(state='normal', text="制作数字人图片"))
        threading.Thread(target=task, daemon=True).start()

    def _prompt_digital_human_prompt(self):
        """弹出提示词编辑对话框，返回 (prompt, cancelled)"""
        from core.i2v.digital_human import WORKFLOW_TEMPLATE
        default_prompt = ""
        try:
            with open(WORKFLOW_TEMPLATE, 'r', encoding='utf-8') as f:
                wf = json.load(f)
            default_prompt = wf.get("121", {}).get("inputs", {}).get("text", "")
        except:
            default_prompt = "一只熊猫对着镜头讲故事，动作表情丰富，固定镜头，There were no words, no flashing, and no logos."

        dialog = tk.Toplevel(self.frame)
        dialog.title("确认提示词")
        dialog.geometry("600x400")
        dialog.transient(self.frame)
        dialog.grab_set()
        dialog.update_idletasks()
        x = dialog.winfo_screenwidth() // 2 - 300
        y = dialog.winfo_screenheight() // 2 - 200
        dialog.geometry(f"+{x}+{y}")

        ttk.Label(dialog, text="请确认或修改数字人提示词（请保留尾部英文防护条件）：", anchor='w').pack(fill='x', padx=10, pady=(10,0))
        text_widget = tk.Text(dialog, height=10, wrap='word')
        text_widget.pack(fill='both', expand=True, padx=10, pady=5)
        text_widget.insert('1.0', default_prompt)

        result = {'prompt': None, 'cancelled': False}

        def on_ok():
            new_prompt = text_widget.get('1.0', 'end-1c').strip()
            result['prompt'] = new_prompt
            try:
                with open(WORKFLOW_TEMPLATE, 'r', encoding='utf-8') as f:
                    wf = json.load(f)
                wf["121"]["inputs"]["text"] = new_prompt
                with open(WORKFLOW_TEMPLATE, 'w', encoding='utf-8') as f:
                    json.dump(wf, f, ensure_ascii=False, indent=2)
            except:
                pass
            dialog.destroy()

        def on_cancel():
            result['cancelled'] = True
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确定", command=on_ok, width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side='left', padx=5)

        dialog.wait_window()
        return result['prompt'], result['cancelled']

    def start_digital_human(self):
        if not self.work_dir:
            messagebox.showerror("错误", "请先打开或创建项目")
            return
        if not self.digital_human_image_path or not os.path.exists(self.digital_human_image_path):
            messagebox.showerror("错误", "请先上传或生成数字人图片")
            return
        final_audio = os.path.join(self.work_dir, "final_audio.mp3")
        if not os.path.exists(final_audio):
            messagebox.showerror("错误", "未找到最终音频文件 final_audio.mp3，请先在音频面板合成音频")
            return

        prompt, cancelled = self._prompt_digital_human_prompt()
        if cancelled or prompt is None:
            self.app.log("用户取消了数字人视频制作")
            return

        # 用户确认后，再启动后台线程进行生成
        self.app.start_dh_btn.config(state='disabled', text="制作中...")
        self.app.log("开始制作数字人视频，请稍候...")

        def task():
            try:
                video_paths = generate_digital_human_full(
                    work_dir=self.work_dir,
                    image_path=self.digital_human_image_path,
                    segment_seconds=21,
                    prompt=prompt,
                    seed=None,
                    api_url=config_manager.COMFYUI_API_URL,
                    log_callback=self.app.log
                )
                if video_paths:
                    self.app.log(f"数字人视频生成完成，共 {len(video_paths)} 个片段")
                else:
                    self.app.log("数字人视频生成失败或没有输出")
            except Exception as e:
                self.app.log(f"数字人视频生成异常: {e}")
            finally:
                self.frame.after(0, lambda: self.app.start_dh_btn.config(state='normal', text="开始制作数字人"))
                self.frame.after(0, self.refresh)

        threading.Thread(target=task, daemon=True).start()

    def _prompt_digital_human_image(self):
        """弹出双输入框对话框，返回拼接后的完整提示词"""
        dialog = tk.Toplevel(self.frame)
        dialog.title("制作数字人图片")
        dialog.geometry("600x400")
        dialog.transient(self.frame)
        dialog.grab_set()

        # 居中显示
        dialog.update_idletasks()
        x = dialog.winfo_screenwidth() // 2 - 300
        y = dialog.winfo_screenheight() // 2 - 200
        dialog.geometry(f"+{x}+{y}")

        # 上方：形象描述
        tk.Label(dialog, text="形象描述（例如：中年男性，国字脸，短发，西装）:", anchor='w').pack(fill='x', padx=10, pady=(10,0))
        desc_text = tk.Text(dialog, height=5, wrap='word')
        desc_text.pack(fill='both', expand=True, padx=10, pady=5)
        # 设置灰色占位文字
        placeholder = "输入数字人的形象描述"
        desc_text.insert('1.0', placeholder)
        desc_text.config(fg='gray')
        def on_desc_focus_in(event):
            if desc_text.get('1.0', 'end-1c') == placeholder:
                desc_text.delete('1.0', 'end')
                desc_text.config(fg='black')
        def on_desc_focus_out(event):
            if not desc_text.get('1.0', 'end-1c').strip():
                desc_text.insert('1.0', placeholder)
                desc_text.config(fg='gray')
        desc_text.bind('<FocusIn>', on_desc_focus_in)
        desc_text.bind('<FocusOut>', on_desc_focus_out)

        # 下方：固定后缀
        tk.Label(dialog, text="固定后缀（可修改）:", anchor='w').pack(fill='x', padx=10, pady=(10,0))
        suffix_text = tk.Text(dialog, height=4, wrap='word')
        suffix_text.pack(fill='both', expand=True, padx=10, pady=5)
        default_suffix = "全身像，脚底在画面底部，完全无阴影，无环境光，商用图，纯蓝背景。"
        suffix_text.insert('1.0', default_suffix)

        result = {'prompt': None}

        def on_ok():
            desc = desc_text.get('1.0', 'end-1c').strip()
            if desc == placeholder:
                desc = ""
            suffix = suffix_text.get('1.0', 'end-1c').strip()
            full_prompt = f"{desc} {suffix}".strip()
            result['prompt'] = full_prompt
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="确定", command=on_ok, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side='left', padx=5)

        dialog.wait_window()
        return result['prompt']

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
            duration_raw = shot.get('duration', 10)           # 原始目标时长，例如 12 秒
            duration_compensated = duration_raw + 1           # 补偿1秒，应对LTX生成不足
            for attempt in range(MAX_RETRIES):
                try:
                    video_path = cfy_i2v.generate_single_video(
                        work_dir=work_dir,
                        shot_id=shot_id,
                        image_path=image_path,
                        prompt=prompt,
                        duration=duration_compensated,        # 13秒
                        target_duration=duration_raw,         # 裁剪回12秒
                        width=width,
                        height=height,
                        api_url=api_url,
                        log_callback=log_callback,
                        auto_trim=False                        # 启用自动裁剪
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
        # 扫描数字人视频文件夹
        dh_video_dir = os.path.join(work_dir, "数字人视频")
        if os.path.isdir(dh_video_dir):
            dh_files = glob.glob(os.path.join(dh_video_dir, "digital_human_*-*_*-*.mp4"))
            # 按文件名排序（时间顺序）
            dh_files.sort()
            for idx, fpath in enumerate(dh_files, start=1):
                fname = os.path.basename(fpath)
                # 解析时间范围：digital_human_0-00_0-21.mp4
                match = re.search(r'digital_human_([\d\-]+)_([\d\-]+)\.mp4', fname)
                if match:
                    start_str = match.group(1).replace('-', ':')
                    end_str = match.group(2).replace('-', ':')
                    description = f"{start_str}~{end_str}"
                else:
                    description = f"数字人片段{idx}"
                shot_id = f"DH{idx}"
                self.shots.append({
                    'id': shot_id,
                    'description': description,
                    'video_path': fpath,
                    'status': "已生成"
                })
                self.tree.insert('', 'end', values=(shot_id, description, "已生成"))

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
        shot_id = shot['id']
        # 数字人条目重试
        if shot_id.startswith('DH'):
            self.retake_digital_human(shot)
            return
        # 原有镜头重试逻辑保持不变
        if hasattr(self.app, 'retake_single_shot'):
            self.app.retake_single_shot(shot_id)
        else:
            messagebox.showwarning("提示", "重试功能未实现")

    def retake_digital_human(self, shot):
        if not self.work_dir or not self.digital_human_image_path:
            messagebox.showerror("错误", "工作目录或数字人图片未设置")
            return
        # 解析时间范围（保持不变）
        desc = shot.get('description', '')
        match = re.match(r'(\d+:\d+)\s*~\s*(\d+:\d+)', desc)
        if not match:
            messagebox.showerror("错误", "无法解析片段的时间范围")
            return
        start_str, end_str = match.groups()
        def to_seconds(t):
            parts = t.split(':')
            return int(parts[0]) * 60 + int(parts[1])
        start_sec = to_seconds(start_str)
        end_sec = to_seconds(end_str)
        duration = end_sec - start_sec

        # 弹出提示词对话框
        prompt, cancelled = self._prompt_digital_human_prompt()
        if cancelled or prompt is None:
            self.app.log("用户取消了重录操作")
            return

        self.retake_btn.config(state='disabled')
        self.app.log(f"开始重录数字人片段: {desc}")
        def task():
            try:
                from core.i2v.digital_human import generate_digital_human_segment
                video_path = generate_digital_human_segment(
                    work_dir=self.work_dir,
                    image_path=self.digital_human_image_path,
                    audio_path=os.path.join(self.work_dir, "final_audio.mp3"),
                    start_seconds=start_sec,
                    duration_seconds=duration,
                    prompt=prompt,
                    seed=None,
                    api_url=config_manager.COMFYUI_API_URL,
                    log_callback=self.app.log
                )
                if video_path:
                    self.app.log(f"数字人片段重录成功: {video_path}")
                    self.frame.after(0, self.refresh)
                else:
                    self.app.log("数字人片段重录失败")
            except Exception as e:
                self.app.log(f"数字人片段重录异常: {e}")
            finally:
                self.frame.after(0, lambda: self.retake_btn.config(state='normal'))
        threading.Thread(target=task, daemon=True).start()

    def on_video_generated(self, shot_id):
        if hasattr(self, '_refresh_after_id'):
            self.frame.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.frame.after(500, self.refresh)