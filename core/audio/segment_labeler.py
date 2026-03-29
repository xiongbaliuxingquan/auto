# core/audio/segment_labeler.py
import os
import json
import threading
from core.audio_labeler import label_audio

class SegmentLabeler:
    def __init__(self, work_dir, log_callback=None):
        self.work_dir = work_dir
        self.log = log_callback or (lambda msg: print(msg))

    def generate_segments(self, paragraphs, on_complete):
        """
        异步生成润色片段，完成后回调 on_complete(segments)
        """
        def task():
            try:
                full_text = "\n\n".join(paragraphs)
                temp_script_path = os.path.join(self.work_dir, "temp_script.txt")
                with open(temp_script_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)
                segments = label_audio(self.work_dir, temp_script_path)
                on_complete(segments)
            except Exception as e:
                self.log(f"段落润色异常: {e}")
                on_complete(None)

        threading.Thread(target=task, daemon=True).start()