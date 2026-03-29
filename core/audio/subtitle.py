# core/audio/subtitle.py
import threading
import os
from utils.aliyun_file_trans import generate_subtitle as aliyun_generate

class SubtitleGenerator:
    def __init__(self, work_dir, log_callback=None):
        self.work_dir = work_dir
        self.log = log_callback or (lambda msg: print(msg))

    def generate(self, audio_path, callback):
        """
        异步生成字幕，完成后调用 callback(success, srt_path)
        """
        def on_done(success, srt_path):
            callback(success, srt_path)
        aliyun_generate(audio_path, self.work_dir, on_done)