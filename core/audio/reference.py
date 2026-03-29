# core/audio/reference.py
import os
import json
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from core.fish_tts import extract_reference_text
from core.qwen_tts import generate_reference_audio

class ReferenceAudioManager:
    def __init__(self, work_dir, log_callback=None):
        self.work_dir = work_dir
        self.log = log_callback or (lambda msg: print(msg))
        self.ref_audio_filename = None
        self.ref_text = None
        self.ref_audio_path = tk.StringVar()
        self._load_cache()

    def _load_cache(self):
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                self.ref_audio_filename = cache.get("audio_filename")
                self.ref_text = cache.get("reference_text")
                if self.ref_audio_filename and self.ref_text:
                    self.log("已从缓存加载参考音频信息")
            except Exception as e:
                self.log(f"加载参考缓存失败: {e}")

    def upload_local(self):
        file_path = filedialog.askopenfilename(filetypes=[("Audio files", "*.mp3 *.wav")])
        if file_path:
            self.ref_audio_path.set(file_path.replace('\\', '/'))
            self.log("已选择参考音频: " + self.ref_audio_path.get())
            self._extract_text()

    def _extract_text(self):
        ref_audio_local = self.ref_audio_path.get()
        if not ref_audio_local:
            return
        self.log("正在上传参考音频并提取文本...")
        try:
            cache = extract_reference_text(self.work_dir, ref_audio_local)
            if cache:
                self.ref_audio_filename = cache["audio_filename"]
                self.ref_text = cache["reference_text"]
                self.log("参考文本提取成功")
            else:
                self.log("参考文本提取失败")
        except Exception as e:
            self.log(f"提取参考文本异常: {e}")

    def ai_generate(self, parent_window=None):
        """弹出AI生成参考音频窗口"""
        import re
        if not self.work_dir:
            messagebox.showerror("错误", "请先设置工作目录")
            return

        # 加载原始口播稿文本
        para_path = os.path.join(self.work_dir, "paragraphs.json")
        if os.path.exists(para_path):
            with open(para_path, 'r', encoding='utf-8') as f:
                paragraphs = json.load(f)
            raw_text = "\n\n".join(paragraphs)
        else:
            messagebox.showerror("错误", "未找到原始口播稿文件 paragraphs.json")
            return

        # 提取前几句作为预览文本
        sentences = re.split(r'[。！？]', raw_text)
        if len(sentences) >= 3:
            preview_text = '。'.join(sentences[:3]) + '。'
        else:
            preview_text = raw_text[:200]

        # 创建窗口
        win = tk.Toplevel(parent_window)
        win.title("AI生成参考音频")
        win.geometry("700x600")
        win.update_idletasks()
        screen_width = win.winfo_screenwidth()
        screen_height = win.winfo_screenheight()
        x = (screen_width - 700) // 2
        y = (screen_height - 600) // 2
        win.geometry(f"+{x}+{y}")
        win.transient(parent_window)
        win.grab_set()

        # 语音描述输入
        ttk.Label(win, text="语音描述（如“语速很快，中年男性，声音干练”）:").pack(anchor='w', padx=10, pady=5)
        voice_entry = ttk.Entry(win, width=60)
        voice_entry.pack(fill='x', padx=10, pady=5)

        # 文本预览
        ttk.Label(win, text="朗读文本（自动从口播稿提取前几句）:").pack(anchor='w', padx=10, pady=5)
        text_edit = scrolledtext.ScrolledText(win, height=8, wrap='word')
        text_edit.insert('1.0', preview_text)
        text_edit.pack(fill='both', expand=True, padx=10, pady=5)

        # 生成结果区域
        result_frame = ttk.LabelFrame(win, text="生成结果", padding=5)
        result_frame.pack(fill='x', padx=10, pady=10)

        status_var = tk.StringVar(value="未生成")
        ttk.Label(result_frame, textvariable=status_var, foreground='blue').pack(anchor='w')
        audio_path_var = tk.StringVar()
        ttk.Entry(result_frame, textvariable=audio_path_var, state='readonly', width=60).pack(fill='x', padx=5, pady=2)

        btn_row = ttk.Frame(result_frame)
        btn_row.pack(pady=5)
        play_btn = ttk.Button(btn_row, text="播放", state='disabled', command=lambda: self._play_audio(audio_path_var.get()))
        play_btn.pack(side='left', padx=5)

        def open_history():
            if not self.work_dir:
                messagebox.showerror("错误", "工作目录未设置")
                return
            file_path = filedialog.askopenfilename(
                title="选择预览音频文件",
                initialdir=self.work_dir,
                filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")]
            )
            if file_path:
                self.ref_audio_path.set(file_path)
                audio_path_var.set(file_path)
                status_var.set("已加载历史预览")
                play_btn.config(state='normal')

        history_btn = ttk.Button(btn_row, text="打开历史预览", command=open_history)
        history_btn.pack(side='left', padx=5)

        def do_generate():
            voice_desc = voice_entry.get().strip()
            if not voice_desc:
                messagebox.showwarning("提示", "请填写语音描述")
                return
            text_to_read = text_edit.get('1.0', 'end-1c').strip()
            if not text_to_read:
                messagebox.showwarning("提示", "朗读文本不能为空")
                return
            gen_btn.config(state='disabled', text="生成中...")
            status_var.set("正在生成音频，请稍候...")
            win.update()

            def run():
                try:
                    audio_path = generate_reference_audio(text_to_read, voice_desc, self.work_dir)
                    if audio_path:
                        audio_path_var.set(audio_path)
                        status_var.set("生成成功！")
                        play_btn.config(state='normal')
                        self.log("AI生成参考音频成功: " + audio_path)
                        # 更新内部变量
                        self.ref_audio_filename = os.path.basename(audio_path)
                        self.ref_text = text_to_read
                        self._save_cache()
                    else:
                        status_var.set("生成失败，请检查日志")
                except Exception as e:
                    status_var.set(f"生成异常: {e}")
                finally:
                    win.after(0, lambda: gen_btn.config(state='normal', text="生成"))

            threading.Thread(target=run, daemon=True).start()

        gen_btn = ttk.Button(win, text="生成", command=do_generate)
        gen_btn.pack(pady=5)

        def confirm():
            path = audio_path_var.get()
            if not path:
                messagebox.showwarning("提示", "尚未生成或生成失败，无法确认")
                return
            # 上传音频并提取文本（调用 Whisper）
            from core.fish_tts import extract_reference_text
            cache = extract_reference_text(self.work_dir, path)
            if cache:
                self.ref_audio_filename = cache["audio_filename"]  # 服务器文件名
                self.ref_text = cache["reference_text"]
                self._save_cache()
                self.log("参考音频已上传并提取文本")
            else:
                self.log("警告：参考音频上传或文本提取失败，使用本地文件名（可能导致后续失败）")
                self.ref_audio_filename = os.path.basename(path)
                self.ref_text = text_edit.get('1.0', 'end-1c').strip()
                self._save_cache()
            self.ref_audio_path.set(path)
            self.log("已使用AI生成的参考音频: " + path)
            win.destroy()

        ttk.Button(win, text="确认使用", command=confirm).pack(pady=5)
        ttk.Button(win, text="取消", command=win.destroy).pack(pady=5)

    def _play_audio(self, path):
        # 这里需要调用外部播放器，可以通过回调实现
        if hasattr(self, 'on_play_requested'):
            self.on_play_requested(path)

    def get_ref_audio_filename(self):
        return self.ref_audio_filename

    def get_ref_text(self):
        return self.ref_text

    def get_ref_audio_path(self):
        return self.ref_audio_path.get()
    
    def _save_cache(self):
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        cache = {"audio_filename": self.ref_audio_filename, "reference_text": self.ref_text}
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)