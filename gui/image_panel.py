# gui/image_panel.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import json
import threading
import subprocess
from PIL import Image, ImageTk

class ImagePanel(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.work_dir = None
        self.prompts_data = []  # 存储每个镜头的 {shot_id, prompt, image_path, widget_frame, text_widget, img_label}
        
        self.create_widgets()
    
    def create_widgets(self):
        # 顶部按钮区域
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill='x', padx=5, pady=5)
        ttk.Button(btn_frame, text="生成首帧提示词", command=self.generate_prompts).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="生成首帧图", command=self.generate_images).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="刷新", command=self.refresh).pack(side='left', padx=2)
        
        # 滚动区域
        self.canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # 绑定滚轮
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
    
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.refresh()
    
    def refresh(self):
        """刷新整个面板：根据 first_frame_prompts.json 重建所有镜头行"""
        # 清除原有内容
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.prompts_data.clear()
        
        if not self.work_dir:
            return
        
        prompts_path = os.path.join(self.work_dir, "first_frame_prompts.json")
        if not os.path.exists(prompts_path):
            label = ttk.Label(self.scrollable_frame, text="未找到首帧提示词文件，请点击「生成首帧提示词」")
            label.pack(pady=20)
            return
        
        with open(prompts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        images_dir = os.path.join(self.work_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        
        for item in data:
            shot_id = item['shot_id']
            prompt = item['prompt']
            image_path = os.path.join(images_dir, f"{shot_id}.png")
            self._add_row(shot_id, prompt, image_path)
    
    def _add_row(self, shot_id, prompt, image_path):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill='x', pady=5, padx=5)
        
        # 镜号
        ttk.Label(row_frame, text=shot_id, width=8).pack(side='left')
        
        # 提示词文本框
        text_widget = tk.Text(row_frame, height=4, wrap='word', font=('微软雅黑', 9))
        text_widget.insert('1.0', prompt)
        text_widget.pack(side='left', fill='both', expand=True, padx=5)
        
        # 缩略图容器（固定大小 100x100）
        thumb_frame = tk.Frame(row_frame, width=100, height=100, bg='lightgray')
        thumb_frame.pack(side='left', padx=5)
        thumb_frame.pack_propagate(False)  # 禁止子控件改变容器大小
        img_label = tk.Label(thumb_frame, bg='lightgray')
        img_label.pack(fill='both', expand=True)
        
        # 按钮区域
        btn_frame = ttk.Frame(row_frame)
        btn_frame.pack(side='left', padx=5)
        ttk.Button(btn_frame, text="保存提示词", command=lambda sid=shot_id, txt=text_widget: self._save_prompt(sid, txt)).pack(pady=2)
        ttk.Button(btn_frame, text="重新生成", command=lambda sid=shot_id, txt=text_widget: self._regenerate_single(sid, txt)).pack(pady=2)
        ttk.Button(btn_frame, text="上传替换", command=lambda sid=shot_id: self._upload_image(sid)).pack(pady=2)
        
        # 加载缩略图（如果存在）
        if os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                img.thumbnail((100, 100))
                photo = ImageTk.PhotoImage(img)
                img_label.config(image=photo)
                img_label.image = photo
                img_label.bind('<Button-1>', lambda e, p=image_path: self._preview_image(p))
            except Exception as e:
                print(f"加载缩略图失败 {shot_id}: {e}")
        else:
            # 未生成图片时，显示灰色占位，并绑定单击事件（可提示未生成）
            img_label.bind('<Button-1>', lambda e: messagebox.showinfo("提示", f"镜头 {shot_id} 首帧图未生成，请先生成"))
        
        self.prompts_data.append({
            'shot_id': shot_id,
            'prompt': prompt,
            'image_path': image_path,
            'row_frame': row_frame,
            'text_widget': text_widget,
            'img_label': img_label
        })
    
    def _save_prompt(self, shot_id, text_widget):
        new_prompt = text_widget.get('1.0', 'end-1c').strip()
        if not new_prompt:
            messagebox.showwarning("提示", "提示词不能为空")
            return
        prompts_path = os.path.join(self.work_dir, "first_frame_prompts.json")
        with open(prompts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for item in data:
            if item['shot_id'] == shot_id:
                item['prompt'] = new_prompt
                break
        with open(prompts_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.app.log(f"镜头 {shot_id} 提示词已保存")
        # 更新内存中的数据
        for d in self.prompts_data:
            if d['shot_id'] == shot_id:
                d['prompt'] = new_prompt
                break
    
    def _regenerate_single(self, shot_id, text_widget):
        """重新生成单个镜头的首帧图"""
        # 先保存提示词
        self._save_prompt(shot_id, text_widget)
        # 然后调用生成函数
        self.app.log(f"正在重新生成镜头 {shot_id} 首帧图...")
        # 获取分辨率
        resolution = self.app.resolution_var.get()
        try:
            width, height = map(int, resolution.split('x'))
        except:
            width, height = 1024, 1024
        from core.i2v.generate_asset_image import generate_asset_image
        # 使用临时角色名，传入自定义提示词
        def task():
            generate_asset_image(
                work_dir=self.work_dir,
                character_name="tmp",
                character_desc="",
                scene_desc="",
                style_desc="",
                custom_prompt=text_widget.get('1.0', 'end-1c').strip(),
                width=width,
                height=height,
                output_filename=f"{shot_id}.png",
                log_callback=self.app.log
            )
            self.app.root.after(0, self.refresh)
        threading.Thread(target=task, daemon=True).start()
    
    def _upload_image(self, shot_id):
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if not file_path:
            return
        import shutil
        target = os.path.join(self.work_dir, "images", f"{shot_id}.png")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(file_path, target)
        self.refresh()
        self.app.log(f"镜头 {shot_id} 首帧图已手动替换")
    
    def _preview_image(self, path):
        win = tk.Toplevel(self)
        win.title("图片预览")
        win.geometry("800x600")
        win.attributes('-topmost', True)
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (win.winfo_width() // 2)
        y = (win.winfo_screenheight() // 2) - (win.winfo_height() // 2)
        win.geometry(f"+{x}+{y}")
        
        canvas = tk.Canvas(win, highlightthickness=0)
        canvas.pack(fill='both', expand=True)
        original_img = Image.open(path)
        img_label = tk.Label(canvas)
        canvas.create_window((0, 0), window=img_label, anchor='nw')
        
        resize_after_id = None
        def resize(event=None):
            nonlocal resize_after_id
            if resize_after_id:
                win.after_cancel(resize_after_id)
            resize_after_id = win.after(200, do_resize)
        
        def do_resize():
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w <= 1 or h <= 1:
                return
            iw, ih = original_img.size
            scale = min(w / iw, h / ih)
            nw = int(iw * scale)
            nh = int(ih * scale)
            resized = original_img.resize((nw, nh), Image.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            img_label.config(image=photo)
            img_label.image = photo
            xo = (w - nw) // 2
            yo = (h - nh) // 2
            canvas.coords(canvas.find_all()[0], xo, yo)
            canvas.configure(scrollregion=(0, 0, w, h))
        
        win.bind('<Configure>', resize)
        win.after(100, do_resize)
    
    def generate_prompts(self):
        if not self.work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return
        shots_path = os.path.join(self.work_dir, "shots.txt")
        if not os.path.exists(shots_path):
            messagebox.showerror("错误", "未找到 shots.txt，请先生成剧本")
            return

        self.app.log("正在生成首帧提示词，请稍候...")
        script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "generate_first_frame_prompts.py")
        
        def run():
            try:
                # 强制无缓冲
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"   # 强制 UTF-8
                process = subprocess.Popen(
                    [sys.executable, script_path, self.work_dir],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace',
                    env=env
                )
                self.app.log("子进程已启动，等待输出...")
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.app.log(line)
                process.wait()
                self.app.log(f"子进程结束，返回码: {process.returncode}")
                if process.returncode != 0:
                    self.app.root.after(0, lambda: messagebox.showerror("错误", f"生成首帧提示词失败，返回码 {process.returncode}"))
                else:
                    self.app.root.after(0, self.refresh)
            except Exception as e:
                self.app.root.after(0, lambda: self.app.log(f"生成首帧提示词异常: {e}"))
        
        threading.Thread(target=run, daemon=True).start()
    
    def generate_images(self):
        """批量生成所有未生成的首帧图"""
        if not self.work_dir:
            messagebox.showerror("错误", "未设置工作目录")
            return
        prompts_path = os.path.join(self.work_dir, "first_frame_prompts.json")
        if not os.path.exists(prompts_path):
            messagebox.showerror("错误", "未找到首帧提示词文件，请先生成")
            return
        
        # 确认分辨率
        resolution = self.app.resolution_var.get()
        width, height = self.app.simple_mode.controller.to_1080p(resolution)  # 添加转换
        if not resolution:
            messagebox.showerror("错误", "请先选择分辨率")
            return
        try:
            width, height = map(int, resolution.split('x'))
        except:
            width, height = 1024, 1024
        
        with open(prompts_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        images_dir = os.path.join(self.work_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        pending = []
        for item in data:
            shot_id = item['shot_id']
            img_path = os.path.join(images_dir, f"{shot_id}.png")
            if not os.path.exists(img_path):
                pending.append((shot_id, item['prompt']))
        
        if not pending:
            messagebox.showinfo("提示", "所有镜头首帧图已生成")
            return
        
        self.app.log(f"开始生成 {len(pending)} 个镜头的首帧图，请稍候...")
        
        from core.i2v.generate_asset_image import generate_asset_image
        
        def task():
            success_count = 0
            for shot_id, prompt in pending:
                self.app.log(f"正在生成镜头 {shot_id}...")
                result = generate_asset_image(
                    work_dir=self.work_dir,
                    character_name="tmp",
                    character_desc="",
                    scene_desc="",
                    style_desc="",
                    custom_prompt=prompt,
                    width=width,
                    height=height,
                    output_filename=f"{shot_id}.png",
                    log_callback=self.app.log
                )
                if result:
                    success_count += 1
            self.app.log(f"首帧图生成完成，成功 {success_count}/{len(pending)} 个")
            self.app.root.after(0, self.refresh)
        
        threading.Thread(target=task, daemon=True).start()