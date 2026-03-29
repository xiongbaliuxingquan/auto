import subprocess
import sys
import threading

class ProcessRunner:
    """封装子进程调用，实时输出到日志回调函数，并支持错误弹窗"""

    def __init__(self, log_callback=None, error_callback=None):
        """
        log_callback: 接收字符串的函数，用于实时输出日志
        error_callback: 接收错误消息的函数，用于 GUI 弹窗
        """
        self.log_callback = log_callback
        self.error_callback = error_callback

    def _log(self, message):
        if self.log_callback:
            self.log_callback(message)
        else:
            print(message)

    def _error(self, message):
        """触发错误回调（如果有）"""
        if self.error_callback:
            self.error_callback(message)
        else:
            print(f"错误：{message}")

    def run(self, cmd, cwd=None, env=None):
        try:
            process = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            for line in iter(process.stdout.readline, ''):
                self._log(line.rstrip())
                # 同时输出到控制台，便于实时查看
                print(line.rstrip())
            process.wait()
            if process.returncode == 0:
                return process.returncode, True
            else:
                error_msg = f"进程退出码: {process.returncode}"
                self._log(error_msg)
                print(error_msg)
                self._error(error_msg)
                return process.returncode, False
        except Exception as e:
            error_msg = f"执行异常: {e}"
            self._log(error_msg)
            print(error_msg)
            self._error(error_msg)
            return -1, False