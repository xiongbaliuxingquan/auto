# core/audio/final_combine.py
import subprocess
import os
import json
import threading
from utils.audio_utils import FFMPEG

class FinalAudioCombine:
    def __init__(self, work_dir, log_callback=None):
        self.work_dir = work_dir
        self.log = log_callback or (lambda msg: print(msg))

    def combine(self, confirmed_segments, callback):
        """
        异步合成最终音频，callback 参数 (success, final_audio_path)
        confirmed_segments: 已确认的片段列表，每个片段应包含 'audio_file' (路径), 'index', 'text', 'duration' 等。
        """
        def run():
            # 生成 concat.txt
            concat_file = os.path.join(self.work_dir, "concat.txt")
            with open(concat_file, 'w', encoding='utf-8') as f:
                for seg in confirmed_segments:
                    audio_file = seg.get('audio_file')
                    if not audio_file:
                        self.log(f"警告：片段 {seg.get('index')} 没有音频文件，跳过")
                        continue
                    audio_file = audio_file.replace('\\', '/')
                    if not os.path.exists(audio_file):
                        self.log(f"警告：音频文件不存在 {audio_file}，跳过")
                        continue
                    rel_path = os.path.relpath(audio_file, self.work_dir).replace('\\', '/')
                    f.write(f"file '{rel_path}'\n")

            final_audio = os.path.join(self.work_dir, "final_audio.mp3")
            cmd = [str(FFMPEG), '-y', '-f', 'concat', '-safe', '0', '-i', concat_file, '-ar', '16000', '-c:a', 'libmp3lame', '-b:a', '128k', final_audio]
            self.log("正在合成最终音频（ffmpeg），请稍候...")
            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=self.work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    encoding='utf-8',
                    errors='replace'
                )
                for line in process.stdout:
                    if line.strip():
                        self.log(line.rstrip())
                process.wait()
                if process.returncode == 0 and os.path.exists(final_audio):
                    self.log(f"最终音频已保存: {final_audio}")
                    # 生成时间轴
                    timeline = self._generate_timeline(confirmed_segments)
                    timeline_path = os.path.join(self.work_dir, "audio_timeline.json")
                    with open(timeline_path, 'w', encoding='utf-8') as f:
                        json.dump(timeline, f, ensure_ascii=False, indent=2)
                    self.log(f"时间轴已保存: {timeline_path}")
                    callback(True, final_audio)
                else:
                    self.log(f"ffmpeg 合成失败，返回码: {process.returncode}")
                    callback(False, None)
            except Exception as e:
                self.log(f"合成异常: {e}")
                callback(False, None)

        threading.Thread(target=run, daemon=True).start()

    def _generate_timeline(self, confirmed_segments):
        timeline = []
        total_ms = 0
        for seg in confirmed_segments:
            duration_ms = int(seg.get('duration', 0) * 1000)
            timeline.append({
                "index": seg.get('index'),
                "text": seg.get('text', ''),
                "start_ms": total_ms,
                "end_ms": total_ms + duration_ms,
                "duration_ms": duration_ms,
                "file": os.path.basename(seg.get('audio_file', ''))
            })
            total_ms += duration_ms
        return timeline