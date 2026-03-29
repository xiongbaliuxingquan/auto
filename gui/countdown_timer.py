# countdown_timer.py
import tkinter as tk

class CountdownTimer:
    """管理倒计时，支持暂停/恢复，超时后执行回调"""

    def __init__(self, root, update_callback, timeout_callback):
        """
        root: tkinter root 对象
        update_callback: 接收剩余秒数的函数，用于更新按钮文本等
        timeout_callback: 倒计时结束时调用的函数
        """
        self.root = root
        self.update_callback = update_callback
        self.timeout_callback = timeout_callback
        self.remaining = 0
        self.paused = False
        self.after_id = None

    def start(self, seconds):
        """开始倒计时"""
        self.remaining = seconds
        self.paused = False
        self._tick()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

    def _tick(self):
        if self.remaining <= 0:
            self.timeout_callback()
            return
        if not self.paused:
            self.update_callback(self.remaining)
            self.remaining -= 1
            self.after_id = self.root.after(1000, self._tick)
        else:
            # 暂停状态，继续每秒检查但不变更剩余时间
            self.after_id = self.root.after(1000, self._tick)