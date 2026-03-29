# gui/simple_mode.py
import tkinter as tk
from tkinter import scrolledtext, messagebox
import os
import json
import threading
import re
from datetime import datetime
from utils import config_manager

class SimpleMode:
    def __init__(self, parent_frame, app):
        self.app = app
        self.frame = tk.Frame(parent_frame)
        self.create_ui()
        self.frame.pack_forget()  # 初始隐藏

    def create_ui(self):
        frame = self.frame

        # 你的故事
        tk.Label(frame, text="你的故事（请用讲故事的口吻写下来，越详细越好）").pack(anchor='w', padx=5, pady=(10,0))
        story_frame = tk.Frame(frame)
        story_frame.pack(fill='x', padx=5, pady=2)
        self.story_text = scrolledtext.ScrolledText(story_frame, wrap='word', height=8)
        self.story_text.pack(side='left', fill='both', expand=True)
        self.story_word_count = tk.Label(story_frame, text="0字", anchor='e', width=10)
        self.story_word_count.pack(side='right', padx=5)
        self.story_text.bind('<KeyRelease>', lambda e: self.update_word_count(self.story_text, self.story_word_count))

        # 风格人设卡（可选）
        tk.Label(frame, text="风格人设卡（可选）").pack(anchor='w', padx=5, pady=(10,0))
        style_frame = tk.Frame(frame)
        style_frame.pack(fill='x', padx=5, pady=2)
        self.style_text = scrolledtext.ScrolledText(style_frame, wrap='word', height=3)
        self.style_text.pack(side='left', fill='both', expand=True)
        self.style_word_count = tk.Label(style_frame, text="0字", anchor='e', width=10)
        self.style_word_count.pack(side='right', padx=5)
        self.style_text.bind('<KeyRelease>', lambda e: self.update_word_count(self.style_text, self.style_word_count))

        # 人设卡管理按钮
        btn_frame = tk.Frame(frame)
        btn_frame.pack(fill='x', padx=5, pady=2)
        tk.Button(btn_frame, text="▼预设", command=self.open_style_preset).pack(side='left', padx=2)
        tk.Button(btn_frame, text="✨一键生成", command=self.generate_style).pack(side='left', padx=2)
        tk.Button(btn_frame, text="💾保存", command=self.save_style_preset).pack(side='left', padx=2)

        # 一致性开关
        self.consistency_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="严格保持人物/场景一致性（开启后，AI将自动从故事中提取设定，确保视频一致性）",
                       variable=self.consistency_var).pack(anchor='w', padx=5, pady=5)
        
        # 生成口播稿按钮
        self.generate_btn = tk.Button(frame, text="生成口播稿", command=self.generate_script, width=15)
        self.generate_btn.pack(pady=5)

        # 选择或编辑提示词按钮（初始禁用）
        self.edit_btn = tk.Button(frame, text="选择或编辑提示词", command=self.app.open_shot_editor, width=16, state='disabled')
        self.edit_btn.pack(pady=5)
        self.run_workflow_btn = tk.Button(frame, text="运行工作流", command=self.run_workflow_manually, width=14, state='disabled')
        self.run_workflow_btn.pack(pady=5)

        # 口播稿预览
        tk.Label(frame, text="口播稿预览（可直接编辑）").pack(anchor='w', padx=5, pady=(10,0))
        preview_frame = tk.Frame(frame)
        preview_frame.pack(fill='both', expand=True, padx=5, pady=2)
        self.preview_text = scrolledtext.ScrolledText(preview_frame, wrap='word', height=10)
        self.preview_text.pack(side='left', fill='both', expand=True)
        self.preview_word_count = tk.Label(preview_frame, text="0字", anchor='e', width=10)
        self.preview_word_count.pack(side='right', padx=5)
        self.preview_text.bind('<KeyRelease>', lambda e: self.update_preview_stats())
        # 一致性设定显示（只读）
        tk.Label(frame, text="人物/场景设定（AI提取，不可编辑）").pack(anchor='w', padx=5, pady=(10,0))
        consistency_frame = tk.Frame(frame)
        consistency_frame.pack(fill='x', padx=5, pady=2)
        self.consistency_text = scrolledtext.ScrolledText(consistency_frame, wrap='word', height=5)
        self.consistency_text.pack(side='left', fill='both', expand=True)
        self.consistency_text.config(state='disabled')  # 设为只读

        # 预估时长
        self.duration_label = tk.Label(frame, text="预估时长：--分--秒（按4.0字/秒预估，仅供参考）", anchor='w')
        self.duration_label.pack(anchor='w', padx=5, pady=2)

        # 确认并生成视频按钮
        self.confirm_btn = tk.Button(frame, text="✅ 确认并生成视频", command=self.confirm_and_generate, width=20)
        self.confirm_btn.pack(pady=10)

        # 倒计时标签（初始隐藏）
        self.countdown_label = tk.Label(frame, text="", font=('Arial', 16, 'bold'), fg='red')
        self.countdown_label.pack(pady=(5,0))
        self.countdown_label.pack_forget()

    def run_workflow_manually(self):
        """手动运行工作流，停止倒计时并调用 app.run_workflow"""
        if self.app.timer:
            self.app.timer.stop()
        self.hide_countdown()
        self.app.run_workflow()

    def update_word_count(self, text_widget, label_widget):
        content = text_widget.get('1.0', 'end-1c')
        count = len(content)
        label_widget.config(text=f"{count:,}字")

    def update_preview_stats(self):
        content = self.preview_text.get('1.0', 'end-1c')
        count = len(content)
        self.preview_word_count.config(text=f"{count:,}字")
        seconds = count / 4.0
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        self.duration_label.config(text=f"预估时长：{minutes}分{secs}秒（按4.0字/秒预估，仅供参考）")

    def generate_style(self):
        story = self.story_text.get('1.0', 'end-1c').strip()
        if not story:
            messagebox.showwarning("提示", "请先输入故事内容")
            return
        try:
            from utils.style_generator import generate_style_from_story
            style = generate_style_from_story(story)
            self.style_text.delete('1.0', 'end')
            self.style_text.insert('1.0', style)
            self.update_word_count(self.style_text, self.style_word_count)
        except Exception as e:
            messagebox.showerror("错误", f"生成风格失败：{e}")

    def save_style_preset(self):
        style = self.style_text.get('1.0', 'end-1c').strip()
        if not style:
            messagebox.showwarning("提示", "风格人设卡为空，无需保存")
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("保存预设", "请输入预设名称：", parent=self.app.root)
        if not name:
            return
        try:
            from utils.config_manager import save_style_preset as save_preset
            save_preset(name, style)
            messagebox.showinfo("成功", f"预设“{name}”已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    def open_style_preset(self):
        # 待实现
        messagebox.showinfo("提示", "此功能待实现")

    def generate_script(self):
        story = self.story_text.get('1.0', 'end-1c').strip()
        if not story:
            messagebox.showwarning("提示", "请先输入故事内容")
            return
        style = self.style_text.get('1.0', 'end-1c').strip()

        self.generate_btn.config(state='disabled', text="生成中...")
        self.app.log("正在生成口播稿，请稍候...")

        def task():
            try:
                from utils.story_to_script import generate_script as gen_script
                script = gen_script(story, style)
                self.app.root.after(0, self._on_script_generated, script)
            except Exception as e:
                self.app.root.after(0, self._on_script_error, str(e))

        threading.Thread(target=task, daemon=True).start()

    def _on_script_generated(self, script):
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', script)
        self.update_preview_stats()
        self.generate_btn.config(state='normal', text="生成口播稿")
        self.app.log("口播稿生成完成")

    def _on_script_error(self, error_msg):
        messagebox.showerror("错误", f"生成口播稿失败：{error_msg}")
        self.generate_btn.config(state='normal', text="生成口播稿")
        self.app.log(f"口播稿生成失败：{error_msg}")

    def confirm_and_generate(self):
        """确认并生成视频（异步执行，避免假死）"""
        script = self.preview_text.get('1.0', 'end-1c').strip()
        if not script:
            messagebox.showwarning("提示", "口播稿为空，无法生成视频")
            return

        # 禁用按钮，防止重复点击
        self.confirm_btn.config(state='disabled', text="处理中...")
        self.app.log("正在准备生成视频，请稍候...")

        def task():
            try:
                self._do_confirm_generate(script)
            except Exception as e:
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"生成视频过程中出错：{e}"))
            finally:
                self.app.root.after(0, lambda: self.confirm_btn.config(state='normal', text="✅ 确认并生成视频"))

        threading.Thread(target=task, daemon=True).start()

    def _do_confirm_generate(self, script):
        """实际执行生成视频的工作（在子线程中运行）"""
        title = self.app.toolbar.title_entry.get().strip()
        if not title:
            title = f"一键成片_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"{title}_{timestamp}"
        base_dir = config_manager.OUTPUT_ROOT_DIR
        work_dir = os.path.join(base_dir, folder_name)
        os.makedirs(work_dir, exist_ok=True)

        # 通过 after 更新 UI 上的工作目录显示
        self.app.root.after(0, lambda: self._update_work_dir_display(work_dir, title))

        script_filename = f"口播稿_{timestamp}.txt"
        script_path = os.path.join(work_dir, script_filename)
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script)
        self.app.log(f"口播稿已保存至: {script_path}")

        # 如果开启一致性，提取设定并写入 header.txt
        if self.consistency_var.get():
            self.app.log("正在提取人物/场景设定（开启一致性），请稍候...")
            try:
                from utils.extract_persona_scene import extract_from_story
                story_text = self.story_text.get('1.0', 'end-1c').strip()
                extracted = extract_from_story(story_text)
                self.app.log("人物/场景设定提取完成")
                header_path = os.path.join(work_dir, "header.txt")
                with open(header_path, 'w', encoding='utf-8') as f:
                    f.write(f"project: {title}\n")
                    style_preset = self.style_text.get('1.0', 'end-1c').strip()
                    style = style_preset if style_preset else "电影感、写实、自然光影"
                    f.write(f"style: {style}\n")
                    f.write(f"seed: 12345\n")
                    # 写入人物设定
                    f.write("persona:\n")
                    import re
                    persona_match = re.search(r'【人物设定】\s*(.*?)(?=【场景设定】|\Z)', extracted, re.DOTALL)
                    if persona_match:
                        persona_part = persona_match.group(1).strip()
                        f.write(persona_part + "\n")
                    # 写入场景设定
                    f.write("scene:\n")
                    scene_match = re.search(r'【场景设定】\s*(.*?)(?=\Z)', extracted, re.DOTALL)
                    if scene_match:
                        scene_part = scene_match.group(1).strip()
                        f.write(scene_part + "\n")
                self.app.log("已根据故事生成人物/场景设定并写入 header.txt")
                # 更新一致性显示区域，直接使用提取的纯文本
                self.app.root.after(0, lambda: self._update_consistency_display(extracted))
            except Exception as e:
                self.app.root.after(0, lambda e=e: messagebox.showerror("错误", f"提取人物/场景设定失败：{e}"))
                return

        input_filename = f"{title}_{timestamp}.txt"
        input_file_path = os.path.join(work_dir, input_filename)
        with open(input_file_path, 'w', encoding='utf-8') as f:
            f.write("口播稿扩展\n")
            f.write(script + "\n\n")
        self.app.log(f"已生成输入文件: {input_file_path}")

        # 设置模式
        self.app.toolbar.mode_var.set("文生视频")
        self.app.toolbar.subtitle_mode_var.set("有字幕")

        # 更新状态
        self.app.root.after(0, lambda: self.app.standard_mode.start_btn.config(state='disabled'))
        self.app.root.after(0, lambda: self.app.common.set_status("正在执行第一步..."))
        self.app.root.after(0, lambda: self.app.set_progress(0))

        # 启动流程
        self.app.step_mgr.mode = "自由模式"  # 使用新解析器
        self.app.root.after(0, lambda: threading.Thread(target=self.app._run_steps_thread, args=(input_filename,), daemon=True).start())

    def _update_work_dir_display(self, work_dir, title):
        """在主线程中更新工作目录显示"""
        self.app.work_dir = work_dir
        self.app.story_title = title
        self.app.common.set_dir(f"工作目录: {work_dir}")
        self.app.log(f"一键成片工作目录: {work_dir}")

    def _update_consistency_display(self, text):
        """在主线程中更新一致性显示区域"""
        self.consistency_text.config(state='normal')
        self.consistency_text.delete('1.0', 'end')
        self.consistency_text.insert('1.0', text)
        self.consistency_text.config(state='disabled')

    # ---------- 倒计时相关方法 ----------
    def show_countdown(self, seconds):
        self.countdown_label.config(text=f"⏳ {seconds}秒后自动运行工作流，点击「选择或编辑提示词」可暂停")
        self.countdown_label.pack(before=self.generate_btn, pady=(5,0))

    def hide_countdown(self):
        self.countdown_label.pack_forget()

    def set_paused(self):
        self.countdown_label.config(text="⏸️ 已暂停，请编辑后手动运行工作流", fg='orange')