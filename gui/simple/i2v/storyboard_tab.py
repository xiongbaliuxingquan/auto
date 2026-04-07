# gui/simple/i2v/storyboard_tab.py
"""
分镜图库标签页：显示定妆照 + 每个镜头的首帧图
支持预览、修改提示词、重新生成、上传替换
"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import threading
import json

class StoryboardTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        self.work_dir = None
        self.images_dir = None
        
        # 创建主布局：上下两部分
        # 上部：定妆照区域
        top_frame = ttk.LabelFrame(self.frame, text="角色定妆照", padding=5)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        # 左侧预览图
        preview_frame = ttk.Frame(top_frame)
        preview_frame.pack(side='left', padx=5)
        self.asset_preview = tk.Label(preview_frame, bg='gray', width=150, height=150)
        self.asset_preview.pack()
        self.asset_preview.bind('<Button-1>', self._preview_asset)  # 点击预览
        self.asset_status = ttk.Label(preview_frame, text="", foreground='gray')
        self.asset_status.pack()
        
        # 右侧提示词编辑区
        prompt_frame = ttk.Frame(top_frame)
        prompt_frame.pack(side='left', fill='both', expand=True, padx=10)
        ttk.Label(prompt_frame, text="定妆照提示词：").pack(anchor='w')
        self.asset_prompt_text = tk.Text(prompt_frame, height=5, wrap='word')
        self.asset_prompt_text.pack(fill='both', expand=True)
        btn_frame = ttk.Frame(prompt_frame)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="重新生成定妆照", command=self.regenerate_asset).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="上传替换", command=self.upload_asset).pack(side='left', padx=2)
        
        # 下部：镜头列表（滚动区域）
        bottom_frame = ttk.LabelFrame(self.frame, text="镜头首帧图", padding=5)
        bottom_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 创建画布+滚动条
        self.canvas = tk.Canvas(bottom_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(bottom_frame, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # 绑定滚轮
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        
        self.shot_frames = []  # 存储每个镜头的UI组件引用
        
        # 定时刷新
        self.refresh()
    
    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.images_dir = os.path.join(work_dir, "images")
        self.refresh()

    def _preview_asset(self, event=None):
        asset_path = self._get_asset_path()
        if asset_path and os.path.exists(asset_path):
            self._preview_image(asset_path)
    
    def refresh(self):
        """刷新显示：定妆照 + 所有镜头"""
        if not self.work_dir:
            return
        # 刷新定妆照
        self._refresh_asset()
        # 刷新镜头列表
        self._refresh_shots()

    def _get_character_name(self):
        """从 assets_global.txt 解析第一个角色名"""
        if not self.work_dir:
            return None
        global_path = os.path.join(self.work_dir, "assets_global.txt")
        if not os.path.exists(global_path):
            return None
        with open(global_path, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        match = re.search(r'【[^】]*\s+([^】]+)】', content)
        if match:
            return match.group(1).strip()
        return None
    
    def _refresh_asset(self):
        """刷新定妆照显示，并加载对应的提示词（即使图片不存在也要加载提示词）"""
        # 获取角色名
        character_name = self._get_character_name()
        if not character_name:
            self.asset_preview.config(image='')
            self.asset_status.config(text="未找到角色", foreground='red')
            self.asset_prompt_text.delete('1.0', 'end')
            self.asset_prompt_text.insert('1.0', "未找到角色信息，请先生成剧本")
            return

        # 构建图片和提示词路径
        asset_path = os.path.join(self.images_dir, f"{character_name}.png") if self.images_dir else None
        prompt_path = os.path.join(self.images_dir, f"{character_name}_prompt.txt") if self.images_dir else None

        # 先处理提示词（无论图片是否存在）
        if prompt_path and os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt = f.read()
            self.asset_prompt_text.delete('1.0', 'end')
            self.asset_prompt_text.insert('1.0', prompt)
        else:
            self.asset_prompt_text.delete('1.0', 'end')
            self.asset_prompt_text.insert('1.0', "（提示词文件未找到，请手动输入或重新生成）")

        # 再处理图片
        if asset_path and os.path.exists(asset_path):
            img = Image.open(asset_path)
            img.thumbnail((150, 150))
            photo = ImageTk.PhotoImage(img)
            self.asset_preview.config(image=photo)
            self.asset_preview.image = photo
            self.asset_status.config(text="已生成", foreground='green')
        else:
            self.asset_preview.config(image='')
            self.asset_status.config(text="未生成", foreground='red')
    
    def _get_asset_path(self):
        """获取定妆照路径（第一个角色的图片）"""
        if not self.work_dir:
            return None
        # 从 assets_global.txt 解析角色名
        global_path = os.path.join(self.work_dir, "assets_global.txt")
        if not os.path.exists(global_path):
            return None
        with open(global_path, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        match = re.search(r'【[^】]*\s+([^】]+)】', content)
        if not match:
            return None
        character_name = match.group(1).strip()
        asset_path = os.path.join(self.work_dir, "images", f"{character_name}.png")
        if os.path.exists(asset_path):
            return asset_path
        return None
    
    def _refresh_shots(self):
        """刷新镜头列表"""
        # 清除原有内容
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.shot_frames.clear()
        
        # 加载提示词和图片
        prompts_path = os.path.join(self.work_dir, "first_frame_prompts.json")
        if not os.path.exists(prompts_path):
            label = ttk.Label(self.scrollable_frame, text="未找到首帧图提示词，请先生成")
            label.pack(pady=20)
            return
        
        import json
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)  # [{"shot_id": "1-1", "prompt": "..."}]
        
        for item in prompts_data:
            shot_id = item['shot_id']
            prompt = item['prompt']
            self._add_shot_row(shot_id, prompt)
    
    def _add_shot_row(self, shot_id, prompt):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill='x', pady=5, padx=5)

        # 镜号
        ttk.Label(row_frame, text=shot_id, width=8).pack(side='left')

        # 提示词文本框，占用剩余空间
        prompt_text = tk.Text(row_frame, height=3, wrap='word')
        prompt_text.insert('1.0', prompt)
        prompt_text.pack(side='left', fill='both', expand=True, padx=5)

        # 缩略图（固定宽高）
        img_label = tk.Label(row_frame, bg='gray', width=100, height=100)
        img_label.pack(side='left', padx=5)

        # 按钮区域
        btn_frame = ttk.Frame(row_frame)
        btn_frame.pack(side='left', padx=5)
        ttk.Button(btn_frame, text="保存提示词",
                command=lambda sid=shot_id, txt=prompt_text: self._save_prompt(sid, txt)).pack(pady=2)
        ttk.Button(btn_frame, text="重新生成",
                command=lambda sid=shot_id, txt=prompt_text: self._regenerate_shot(sid, txt)).pack(pady=2)
        ttk.Button(btn_frame, text="上传替换",
                command=lambda sid=shot_id: self._upload_shot_image(sid)).pack(pady=2)

        # 加载缩略图
        img_path = os.path.join(self.images_dir, f"{shot_id}.png") if self.images_dir else None
        if img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img.thumbnail((100, 100))
                photo = ImageTk.PhotoImage(img)
                img_label.config(image=photo)
                img_label.image = photo
                img_label.bind('<Button-1>', lambda e, p=img_path: self._preview_image(p))
            except Exception as e:
                print(f"加载缩略图失败 {shot_id}: {e}")

        self.shot_frames.append({
            'shot_id': shot_id,
            'row_frame': row_frame,
            'prompt_text': prompt_text,
            'img_label': img_label
        })
    
    def _save_prompt(self, shot_id, text_widget):
        """保存修改后的提示词到 first_frame_prompts.json"""
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
        messagebox.showinfo("成功", "提示词已保存")
    
    def _regenerate_shot(self, shot_id, text_widget):
        """重新生成单个镜头的首帧图"""
        # 先保存提示词
        self._save_prompt(shot_id, text_widget)
        # 调用控制器的方法重新生成
        if hasattr(self.controller, 'regenerate_single_frame'):
            self.controller.regenerate_single_frame(shot_id)
        else:
            messagebox.showwarning("提示", "重新生成功能未实现")
    
    def _upload_shot_image(self, shot_id):
        """手动上传替换该镜头的首帧图"""
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if not file_path:
            return
        import shutil
        target = os.path.join(self.images_dir, f"{shot_id}.png")
        os.makedirs(self.images_dir, exist_ok=True)
        shutil.copy2(file_path, target)
        self.refresh()
        messagebox.showinfo("成功", "图片已替换")
    
    def _preview_image(self, path):
        win = tk.Toplevel(self.frame)
        win.title("图片预览")
        win.attributes('-topmost', True)
        win.geometry("800x600")
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
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            if canvas_width <= 1 or canvas_height <= 1:
                return
            img_width, img_height = original_img.size
            # 等比例缩放，使图片完全显示在窗口内（留白）
            scale = min(canvas_width / img_width, canvas_height / img_height)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            resized = original_img.resize((new_width, new_height), Image.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            img_label.config(image=photo)
            img_label.image = photo
            # 居中显示
            x_offset = (canvas_width - new_width) // 2
            y_offset = (canvas_height - new_height) // 2
            canvas.coords(canvas.find_all()[0], x_offset, y_offset)
            canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))

        win.bind('<Configure>', resize)
        win.after(100, do_resize)
    
    def regenerate_asset(self):
        custom_prompt = self.asset_prompt_text.get('1.0', 'end-1c').strip()
        if hasattr(self.controller, 'regenerate_asset_with_prompt'):
            self.controller.regenerate_asset_with_prompt(custom_prompt)
        else:
            messagebox.showwarning("提示", "重新生成定妆照功能未实现")
    
    def upload_asset(self):
        """手动上传替换定妆照"""
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if not file_path:
            return
        asset_path = self._get_asset_path()
        if not asset_path:
            messagebox.showerror("错误", "未找到角色信息，请先生成资产图")
            return
        import shutil
        os.makedirs(os.path.dirname(asset_path), exist_ok=True)
        shutil.copy2(file_path, asset_path)
        self._refresh_asset()
        messagebox.showinfo("成功", "定妆照已替换")
    
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")