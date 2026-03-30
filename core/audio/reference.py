# core/audio/reference.py
import os
import json
import time
from typing import Optional

# 导入底层 TTS 相关函数
from core.fish_tts import extract_reference_text
from core.qwen_tts import generate_reference_audio


class ReferenceAudioManager:
    """
    参考音频管理器：管理参考音频的上传、转录、缓存。
    不处理 UI，只提供同步方法，调用方需自行处理线程。
    """

    def __init__(self, work_dir: str, log_callback=None):
        self.work_dir = work_dir
        self.log = log_callback or (lambda msg: print(msg))

        self._ref_audio_filename = None   # 服务器上的文件名（如 "中年干练连珠炮.mp3"）
        self._ref_text = None              # 参考文本
        self._ref_audio_path = None        # 本地文件路径（用于界面显示）

        self._load_cache()

    # ------------------ 公共接口 ------------------
    def get_ref_audio_filename(self) -> Optional[str]:
        return self._ref_audio_filename

    def get_ref_text(self) -> Optional[str]:
        return self._ref_text

    def get_ref_audio_path(self) -> Optional[str]:
        return self._ref_audio_path

    def set_from_local(self, local_path: str) -> bool:
        """
        从本地音频文件设置参考音频（上传并转录）。
        返回是否成功。
        """
        if not os.path.exists(local_path):
            self.log(f"文件不存在: {local_path}")
            return False

        self.log(f"正在上传并转录参考音频: {local_path}")
        try:
            cache = extract_reference_text(self.work_dir, local_path)
            if cache:
                self._ref_audio_filename = cache["audio_filename"]
                self._ref_text = cache["reference_text"]
                self._ref_audio_path = local_path
                self._save_cache()
                self.log("参考音频上传并转录成功")
                return True
            else:
                self.log("参考音频上传或转录失败")
                return False
        except Exception as e:
            self.log(f"参考音频处理异常: {e}")
            return False

    def clear(self):
        """清除当前参考音频信息并删除缓存文件"""
        self._ref_audio_filename = None
        self._ref_text = None
        self._ref_audio_path = None
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                self.log("已删除参考音频缓存")
            except Exception as e:
                self.log(f"删除缓存文件失败: {e}")

    # ------------------ 私有方法 ------------------
    def _load_cache(self):
        """从工作目录加载缓存文件"""
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        if not os.path.exists(cache_path):
            return

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._ref_audio_filename = data.get("audio_filename")
            self._ref_text = data.get("reference_text")
            # 注意：本地路径不在缓存中，需要尝试推导
            if self._ref_audio_filename:
                # 尝试在 input 目录下找，但这里无法获取，先置为 None
                # 实际路径可由调用方另行提供
                self._ref_audio_path = None
            self.log("已加载参考音频缓存")
        except Exception as e:
            self.log(f"加载参考音频缓存失败: {e}")

    def _save_cache(self):
        """保存当前参考音频信息到缓存文件"""
        cache = {
            "audio_filename": self._ref_audio_filename,
            "reference_text": self._ref_text
        }
        cache_path = os.path.join(self.work_dir, "reference_cache.json")
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
            self.log("参考音频缓存已保存")
        except Exception as e:
            self.log(f"保存参考音频缓存失败: {e}")


# 为了与旧代码兼容，提供一些辅助函数（可选）
def extract_reference_text_wrapper(work_dir, audio_path):
    """包装 extract_reference_text，用于旧代码迁移"""
    return extract_reference_text(work_dir, audio_path)


def generate_reference_audio_wrapper(text, voice_description, work_dir):
    """包装 generate_reference_audio，用于旧代码迁移"""
    return generate_reference_audio(text, voice_description, work_dir)