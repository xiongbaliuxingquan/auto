# core/audio/playback.py
import pygame
import threading
from utils.audio_utils import get_audio_duration

class PlaybackController:
    def __init__(self, on_play_start=None, on_position_update=None, on_playback_end=None):
        self.on_play_start = on_play_start
        self.on_position_update = on_position_update
        self.on_playback_end = on_playback_end
        self.current_file = None
        self.current_total_duration = 0
        self.is_paused = False
        self._stop_flag = False
        self._update_id = None
        self._player_available = self._check_pygame()

    def _check_pygame(self):
        try:
            pygame.init()
            pygame.mixer.init()
            return True
        except:
            return False

    def play(self, filepath):
        if not self._player_available:
            return False
        if self.current_file == filepath and pygame.mixer.music.get_busy():
            # 同一文件，暂停/恢复
            if self.is_paused:
                pygame.mixer.music.unpause()
                self.is_paused = False
                self._start_position_update()
                return True
            else:
                pygame.mixer.music.pause()
                self.is_paused = True
                self._stop_position_update()
                return True
        else:
            # 停止当前，播放新文件
            pygame.mixer.music.stop()
            self._stop_position_update()
            try:
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.play()
                self.current_file = filepath
                self.is_paused = False
                self.current_total_duration = get_audio_duration(filepath)
                # 通知 UI 播放开始，传递总时长
                if self.on_play_start:
                    self.on_play_start(self.current_total_duration)
                if self.on_position_update:
                    self.on_position_update(0, self.current_total_duration)
                self._start_position_update()
                return True
            except Exception as e:
                print(f"播放失败: {e}")
                return False

    def pause(self):
        if self._player_available and pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self.is_paused = True
            self._stop_position_update()
            return True
        return False
    
    def seek(self, seconds):
        """跳转到指定秒数（仅支持部分音频格式）"""
        if not self._player_available or not pygame.mixer.music.get_busy():
            return False
        try:
            pygame.mixer.music.set_pos(seconds)
            # 更新进度
            if self.on_position_update:
                self.on_position_update(seconds, self.current_total_duration)
            return True
        except Exception as e:
            print(f"Seek 失败: {e}")
            return False

    def resume(self):
        if self._player_available and self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            self._start_position_update()
            return True
        return False

    def stop(self):
        if self._player_available:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()   # 显式卸载文件
            self._stop_position_update()
            self.current_file = None
            self.is_paused = False
            if self.on_position_update:
                self.on_position_update(0, 0)
            if self.on_playback_end:
                self.on_playback_end()
            return True
        return False

    def _start_position_update(self):
        self._stop_flag = False
        self._update_position()

    def _stop_position_update(self):
        self._stop_flag = True
        if self._update_id:
            self._update_id.cancel()

    def _update_position(self):
        if not self._player_available or self._stop_flag:
            return
        if pygame.mixer.music.get_busy():
            pos = pygame.mixer.music.get_pos() / 1000.0
            if self.on_position_update:
                self.on_position_update(pos, self.current_total_duration)
            self._update_id = threading.Timer(0.1, self._update_position)
            self._update_id.start()
        else:
            if self.on_playback_end:
                self.on_playback_end()
            self._stop_position_update()