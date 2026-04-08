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
        # 上部：定妆照区域（左右分栏：左侧单个预览+提示词，右侧所有角色缩略图）
        top_frame = ttk.LabelFrame(self.frame, text="角色定妆照", padding=5)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        # 左侧：当前选中的角色预览和提示词编辑
        left_frame = ttk.Frame(top_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        self.asset_preview = tk.Label(left_frame, bg='gray', width=150, height=150)
        self.asset_preview.pack()
        self.asset_preview.bind('<Button-1>', self._preview_asset)
        self.asset_status = ttk.Label(left_frame, text="", foreground='gray')
        self.asset_status.pack()
        
        ttk.Label(left_frame, text="定妆照提示词：").pack(anchor='w', pady=(5,0))
        self.asset_prompt_text = tk.Text(left_frame, height=5, wrap='word')
        self.asset_prompt_text.pack(fill='both', expand=True)
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill='x', pady=5)
        ttk.Button(btn_frame, text="重新生成定妆照", command=self.regenerate_asset).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="上传替换", command=self.upload_asset).pack(side='left', padx=2)
        
        # 右侧：所有角色的缩略图列表（横向滚动）
        right_frame = ttk.LabelFrame(top_frame, text="所有角色", padding=5)
        right_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        self.asset_canvas = tk.Canvas(right_frame, highlightthickness=0, height=180)
        self.asset_scrollbar = ttk.Scrollbar(right_frame, orient='horizontal', command=self.asset_canvas.xview)
        self.asset_scrollable = ttk.Frame(self.asset_canvas)
        self.asset_scrollable.bind("<Configure>", lambda e: self.asset_canvas.configure(scrollregion=self.asset_canvas.bbox("all")))
        self.asset_canvas.create_window((0, 0), window=self.asset_scrollable, anchor='nw')
        self.asset_canvas.configure(xscrollcommand=self.asset_scrollbar.set)
        self.asset_canvas.pack(side='top', fill='x')
        self.asset_scrollbar.pack(side='bottom', fill='x')
        
        self.asset_items = []  # 存储 (frame, label, name)
        
        # 下部：镜头列表（滚动区域）
        bottom_frame = ttk.LabelFrame(self.frame, text="镜头首帧图", padding=5)
        bottom_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(bottom_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(bottom_frame, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self._on_mousewheel)
        
        self.shot_frames = []
        self.current_character = None
        
        self.refresh()
    
    def set_work_dir(self, work_dir):
        self.work_dir = work_dir
        self.images_dir = os.path.join(work_dir, "images")
        self.refresh()

    def _preview_asset(self, event=None):
        if self.current_character:
            path = os.path.join(self.images_dir, f"{self.current_character}.png")
            if os.path.exists(path):
                self._preview_image(path)
    
    def refresh(self):
        if not self.work_dir:
            return
        self._refresh_asset_list()
        self._refresh_shots()
    
    def _get_all_characters(self):
        if not self.work_dir:
            return []
        global_path = os.path.join(self.work_dir, "assets_global.txt")
        if not os.path.exists(global_path):
            return []
        with open(global_path, 'r', encoding='utf-8') as f:
            content = f.read()
        import re
        matches = re.findall(r'【[^】]*\s+([^】]+)】', content)
        return matches
    
    def _refresh_asset_list(self):
        for widget in self.asset_scrollable.winfo_children():
            widget.destroy()
        self.asset_items.clear()
        
        characters = self._get_all_characters()
        if not characters:
            self.asset_preview.config(image='')
            self.asset_status.config(text="未找到角色", foreground='red')
            self.asset_prompt_text.delete('1.0', 'end')
            self.asset_prompt_text.insert('1.0', "未找到角色信息，请先生成剧本")
            return
        
        for name in characters:
            frame = ttk.Frame(self.asset_scrollable)
            frame.pack(side='left', padx=5, pady=5)
            asset_path = os.path.join(self.images_dir, f"{name}.png")
            if os.path.exists(asset_path):
                img = Image.open(asset_path)
                img.thumbnail((80, 80))
                photo = ImageTk.PhotoImage(img)
                label = tk.Label(frame, image=photo)
                label.image = photo
                label.pack()
            else:
                label = tk.Label(frame, text="未生成", bg='gray', width=10, height=5)
                label.pack()
            ttk.Label(frame, text=name).pack()
            label.bind('<Button-1>', lambda e, n=name: self._select_character(n))
            self.asset_items.append((frame, label, name))
        
        if characters:
            self._select_character(characters[0])
    
    def _select_character(self, name):
        self.current_character = name
        asset_path = os.path.join(self.images_dir, f"{name}.png")
        if os.path.exists(asset_path):
            img = Image.open(asset_path)
            img.thumbnail((150, 150))
            photo = ImageTk.PhotoImage(img)
            self.asset_preview.config(image=photo)
            self.asset_preview.image = photo
            self.asset_status.config(text="已生成", foreground='green')
        else:
            self.asset_preview.config(image='')
            self.asset_status.config(text="未生成", foreground='red')
        
        prompt_path = os.path.join(self.images_dir, f"{name}_prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt = f.read()
            self.asset_prompt_text.delete('1.0', 'end')
            self.asset_prompt_text.insert('1.0', prompt)
        else:
            self.asset_prompt_text.delete('1.0', 'end')
            self.asset_prompt_text.insert('1.0', "（提示词文件未找到）")
    
    def _get_asset_path(self):
        if self.current_character:
            return os.path.join(self.images_dir, f"{self.current_character}.png")
        return None
    
    def _refresh_shots(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.shot_frames.clear()
        
        prompts_path = os.path.join(self.work_dir, "first_frame_prompts.json")
        if not os.path.exists(prompts_path):
            ttk.Label(self.scrollable_frame, text="未找到首帧图提示词，请先生成").pack(pady=20)
            return
        
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)
        for item in prompts_data:
            self._add_shot_row(item['shot_id'], item['prompt'])
    
    def _add_shot_row(self, shot_id, prompt):
        row_frame = ttk.Frame(self.scrollable_frame)
        row_frame.pack(fill='x', pady=5, padx=5)
        
        ttk.Label(row_frame, text=shot_id, width=8).pack(side='left')
        prompt_text = tk.Text(row_frame, height=3, wrap='word')
        prompt_text.insert('1.0', prompt)
        prompt_text.pack(side='left', fill='both', expand=True, padx=5)
        
        img_label = tk.Label(row_frame, bg='gray', width=100, height=100)
        img_label.pack(side='left', padx=5)
        
        btn_frame = ttk.Frame(row_frame)
        btn_frame.pack(side='left', padx=5)
        ttk.Button(btn_frame, text="保存提示词", command=lambda sid=shot_id, txt=prompt_text: self._save_prompt(sid, txt)).pack(pady=2)
        ttk.Button(btn_frame, text="重新生成", command=lambda sid=shot_id, txt=prompt_text: self._regenerate_shot(sid, txt)).pack(pady=2)
        ttk.Button(btn_frame, text="上传替换", command=lambda sid=shot_id: self._upload_shot_image(sid)).pack(pady=2)
        
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
        self._save_prompt(shot_id, text_widget)
        if hasattr(self.controller, 'regenerate_single_frame'):
            self.controller.regenerate_single_frame(shot_id)
        else:
            messagebox.showwarning("提示", "重新生成功能未实现")
    
    def _upload_shot_image(self, shot_id):
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
    
    def regenerate_asset(self):
        custom_prompt = self.asset_prompt_text.get('1.0', 'end-1c').strip()
        if hasattr(self.controller, 'regenerate_asset_with_prompt'):
            self.controller.regenerate_asset_with_prompt(custom_prompt)
        else:
            messagebox.showwarning("提示", "重新生成定妆照功能未实现")
    
    def upload_asset(self):
        if not self.current_character:
            messagebox.showerror("错误", "未选中任何角色")
            return
        file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if not file_path:
            return
        import shutil
        target = os.path.join(self.images_dir, f"{self.current_character}.png")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(file_path, target)
        self._refresh_asset_list()
        self._select_character(self.current_character)
        messagebox.showinfo("成功", "定妆照已替换")
    
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
    
    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")