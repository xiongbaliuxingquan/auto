# gui/log_viewer.py
import tkinter as tk
import threading
import time
import os

class LogViewer:
    def __init__(self, master, log_file_path):
        self.master = master
        self.log_file_path = log_file_path
        self.window = None
        self.text_widget = None
        self._stop_flag = False
        self._last_size = 0
        self._last_position = 0  # 上次读取到的位置

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            return

        self.window = tk.Toplevel(self.master)
        self.window.title("日志监控 - 大窗口")
        self.window.geometry("900x600")
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        # 文本显示区域
        text_frame = tk.Frame(self.window)
        text_frame.pack(fill='both', expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side='right', fill='y')

        self.text_widget = tk.Text(
            text_frame,
            wrap='word',
            yscrollcommand=scrollbar.set,
            font=('Consolas', 12),
            background='#1e1e1e',
            foreground='#d4d4d4'
        )
        self.text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.text_widget.yview)

        # 配置颜色标签
        self.text_widget.tag_config('error', foreground='#ff6b6b', font=('Consolas', 12, 'bold'))
        self.text_widget.tag_config('warning', foreground='#f9ca7f', font=('Consolas', 12))
        self.text_widget.tag_config('info', foreground='#d4d4d4')

        # 加载已有内容
        self._load_initial_content()

        # 启动监控线程
        self._stop_flag = False
        self._monitor_thread = threading.Thread(target=self._monitor_log, daemon=True)
        self._monitor_thread.start()

    def _on_close(self):
        self._stop_flag = True
        self.window.destroy()
        self.window = None
        self.text_widget = None

    def _load_initial_content(self):
        """加载已有内容到文本控件"""
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.text_widget.delete('1.0', 'end')
            self.text_widget.insert('1.0', content)
            self._colorize()
            self._last_size = os.path.getsize(self.log_file_path)
            self._last_position = self._last_size
            # 初始滚动到底部
            self.text_widget.see('end')
        except Exception:
            pass

    def _colorize(self):
        """为日志文本添加颜色标签（全量重设）"""
        self.text_widget.tag_remove('error', '1.0', 'end')
        self.text_widget.tag_remove('warning', '1.0', 'end')
        content = self.text_widget.get('1.0', 'end')
        lines = content.split('\n')
        for i, line in enumerate(lines):
            line_start = f"{i+1}.0"
            line_end = f"{i+1}.end"
            if re.search(r'错误|失败|exception|error|fail|traceback', line, re.IGNORECASE):
                self.text_widget.tag_add('error', line_start, line_end)
            elif re.search(r'警告|warn', line, re.IGNORECASE):
                self.text_widget.tag_add('warning', line_start, line_end)

    def _monitor_log(self):
        """监控日志文件变化，增量追加"""
        import re  # 用于颜色高亮，已在开头导入
        while not self._stop_flag:
            try:
                current_size = os.path.getsize(self.log_file_path)
                if current_size > self._last_size:
                    # 有新增内容
                    with open(self.log_file_path, 'r', encoding='utf-8') as f:
                        f.seek(self._last_position)
                        new_content = f.read()
                    self._last_position = f.tell()
                    self._last_size = current_size

                    # 在 GUI 线程中追加文本
                    if new_content:
                        self.window.after(0, self._append_text, new_content)
                elif current_size < self._last_size:
                    # 文件被截断（例如日志轮转），重置状态
                    self.window.after(0, self._reload_all)
            except Exception:
                pass
            time.sleep(0.5)  # 轮询间隔

    def _append_text(self, new_content):
        """追加新内容到文本控件"""
        if not self.text_widget:
            return
        # 判断当前是否在底部
        scroll_pos = self.text_widget.yview()
        at_bottom = scroll_pos[1] >= 0.99

        # 插入新内容
        self.text_widget.insert('end', new_content)
        # 对新插入的行应用颜色标签（简单方法：全量重新着色）
        self._colorize()

        # 如果之前在底部，则滚动到底部
        if at_bottom:
            self.text_widget.see('end')

    def _reload_all(self):
        """完全重新加载（文件被截断时）"""
        if not self.text_widget:
            return
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.text_widget.delete('1.0', 'end')
            self.text_widget.insert('1.0', content)
            self._colorize()
            self._last_position = len(content)
            self._last_size = os.path.getsize(self.log_file_path)
            # 滚动到底部
            self.text_widget.see('end')
        except Exception:
            pass