# core/audio/loader.py
import os
import json
import re
from utils.audio_utils import get_audio_duration

class AudioProjectLoader:
    def __init__(self, work_dir, log_callback=None):
        self.work_dir = work_dir
        self.log = log_callback or (lambda msg: print(msg))

    def load_paragraphs(self):
        """从 paragraphs.json 加载原始段落列表"""
        para_path = os.path.join(self.work_dir, "paragraphs.json")
        if not os.path.exists(para_path):
            return []
        with open(para_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_segments_from_labeled_text(self):
        """从 labeled_text.txt 加载润色后的段落（按空行分割）"""
        labeled_path = os.path.join(self.work_dir, "labeled_text.txt")
        if not os.path.exists(labeled_path):
            return []
        with open(labeled_path, 'r', encoding='utf-8') as f:
            content = f.read()
        raw_paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
        return raw_paragraphs

    def load_segments_from_json(self):
        """从 segments_info.json 加载带标签的片段"""
        json_path = os.path.join(self.work_dir, "segments_info.json")
        if not os.path.exists(json_path):
            return []
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_existing_audio_files(self, segments):
        """为每个片段检查对应的音频文件是否存在，返回更新后的 segments 列表"""
        for seg in segments:
            idx = seg.get('index')
            if idx is None:
                continue
            audio_path = os.path.join(self.work_dir, f"segment_{idx:03d}.mp3")
            if os.path.exists(audio_path):
                try:
                    duration = get_audio_duration(audio_path)
                    seg['audio_file'] = audio_path
                    seg['duration'] = duration
                except Exception as e:
                    self.log(f"获取音频时长失败: {audio_path}, {e}")
        return segments

    def load_reference_cache(self):
        """加载参考音频缓存"""
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def save_reference_cache(self, audio_filename, reference_text):
        """保存参考音频缓存"""
        cache = {"audio_filename": audio_filename, "reference_text": reference_text}
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)