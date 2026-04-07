# core/audio/generation.py
import threading
import time
import os
import json
from core.fish_tts import generate_single
from utils.audio_utils import get_audio_duration

class AudioGenerationController:
    """音频生成控制器：管理队列、状态、重试、持久化、暂停/恢复/取消"""
    def __init__(self, work_dir, ref_audio_filename, ref_text, language="auto", log_callback=None):
        self.work_dir = work_dir
        self.ref_audio_filename = ref_audio_filename
        self.ref_text = ref_text
        self.language = language
        self.log = log_callback or (lambda msg: print(msg))
        
        # 队列相关
        self.queue = []              # 每个元素为 (index, text, callback)
        self.lock = threading.Lock()
        
        # 状态管理
        self.status = {}             # index -> {"status": str, "retries": int, "audio_path": str, "duration": float}
        self.max_retries = 3         # 最大重试次数
        self.retry_delay = 2         # 重试间隔（秒）
        
        # 控制标志
        self.running = False
        self.paused = False
        self.cancelled = False
        self.thread = None
        
        # 进度回调
        self.progress_callback = None  # 接收参数 (completed, total)
        
        # 持久化文件路径
        self.status_file = os.path.join(work_dir, "segments_info.json")
        self._load_status()            # 加载已有状态

    def set_progress_callback(self, callback):
        """设置进度回调，参数 (completed, total)"""
        self.progress_callback = callback

    def set_max_retries(self, max_retries):
        self.max_retries = max_retries

    def set_retry_delay(self, delay):
        self.retry_delay = delay

    def _load_status(self):
        """从 segments_info.json 加载已有状态"""
        if os.path.exists(self.status_file):
            try:
                with open(self.status_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 期望 data 是列表，每个元素包含 index, text, audio_file, duration 等
                    for item in data:
                        idx = item.get('index')
                        if idx is not None:
                            self.status[idx] = {
                                'status': 'generated' if item.get('audio_file') else 'pending',
                                'retries': 0,
                                'audio_path': item.get('audio_file'),
                                'duration': item.get('duration')
                            }
                self.log(f"已加载 {len(self.status)} 个片段的持久化状态")
            except Exception as e:
                self.log(f"加载状态文件失败: {e}")

    def _save_status(self):
        """保存当前状态到 segments_info.json（仅保存已生成成功的片段）"""
        # 只保存成功生成的片段
        success_list = []
        for idx, info in self.status.items():
            if info['status'] == 'success' and info.get('audio_path'):
                success_list.append({
                    'index': idx,
                    'audio_file': info['audio_path'],
                    'duration': info['duration']
                })
        # 注意：原始 segments_info.json 可能还包含 text 字段，但这里我们只保存音频信息
        # 为了兼容，可以读取原有文件合并，但简单起见，只写成功片段
        try:
            with open(self.status_file, 'w', encoding='utf-8') as f:
                json.dump(success_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存状态文件失败: {e}")

    def start(self):
        """启动工作线程"""
        if self.running:
            return
        self.running = True
        self.paused = False
        self.cancelled = False
        self.thread = threading.Thread(target=self._worker)
        self.thread.daemon = True
        self.thread.start()
        self.log("音频生成控制器已启动")

    def reset_segment(self, index):
        """重置指定片段的状态，允许重新生成（用于重录）"""
        with self.lock:
            if index in self.status:
                # 如果该片段正在生成中，不能重置
                if self.status[index]['status'] in ('generating', 'retrying'):
                    self.log(f"片段 {index} 正在生成中，无法重置")
                    return False
                # 清除成功状态，重置为 pending
                self.status[index] = {
                    'status': 'pending',
                    'retries': 0,
                    'audio_path': None,
                    'duration': None
                }
                self.log(f"已重置片段 {index} 的状态，可重新生成")
                # 可选：从持久化文件中移除该片段？不需要，下次保存时会覆盖
                return True
            else:
                # 不存在则创建 pending 状态
                self.status[index] = {
                    'status': 'pending',
                    'retries': 0,
                    'audio_path': None,
                    'duration': None
                }
                return True

    def sync_existing_segment(self, index, audio_path, duration):
        """同步已存在的音频片段到控制器（用于加载历史项目）"""
        with self.lock:
            self.status[index] = {
                'status': 'success',
                'retries': 0,
                'audio_path': audio_path,
                'duration': duration
            }
            self.log(f"已同步现有片段 {index}，音频: {audio_path}")
            self._update_progress()

    def pause(self):
        """暂停：不再从队列取新任务"""
        self.paused = True
        self.log("音频生成已暂停")

    def resume(self):
        """恢复：继续取任务"""
        self.paused = False
        self.log("音频生成已恢复")

    def cancel_all(self):
        """取消所有待处理任务，清空队列"""
        with self.lock:
            self.queue.clear()
        self.cancelled = True
        self.paused = False  # 取消时也恢复暂停状态，以便后续重新添加任务
        self.log("已取消所有待生成任务")

    def stop(self):
        """停止控制器（等待当前任务完成）"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.log("音频生成控制器已停止")

    def add_task(self, index, text, callback):
        """
        添加生成任务
        :param index: 片段序号（整数）
        :param text: 带标签的文本
        :param callback: 回调函数，签名 callback(index, success, audio_path, duration)
        """
        with self.lock:
            # 如果该片段已成功，直接回调成功，不重复生成
            if index in self.status and self.status[index]['status'] == 'success':
                info = self.status[index]
                self.log(f"片段 {index} 已存在音频文件，跳过生成")
                callback(index, True, info['audio_path'], info['duration'])
                return
            # 否则加入队列
            self.queue.append((index, text, callback))
            # 初始化状态
            if index not in self.status:
                self.status[index] = {'status': 'pending', 'retries': 0, 'audio_path': None, 'duration': None}
        self.log(f"已添加片段 {index} 到生成队列")

    def _update_progress(self):
        """更新进度：统计已成功数量 vs 总任务数（包括已成功和待处理）"""
        total = len(self.status)  # 总片段数（所有已添加过的片段）
        completed = sum(1 for info in self.status.values() if info['status'] == 'success')
        if self.progress_callback:
            self.progress_callback(completed, total)

    def _worker(self):
        """工作线程主循环"""
        while self.running:
            # 检查暂停标志
            if self.paused:
                time.sleep(0.5)
                continue
            # 取任务
            task = None
            with self.lock:
                if self.queue:
                    task = self.queue.pop(0)
            if task:
                idx, text, cb = task
                # 更新状态为 generating
                self.status[idx]['status'] = 'generating'
                self._update_progress()
                # 执行生成（支持重试）
                success, audio_path, duration = self._generate_with_retry(idx, text)
                if success:
                    self.status[idx]['status'] = 'success'
                    self.status[idx]['audio_path'] = audio_path
                    self.status[idx]['duration'] = duration
                    # self.log(f"片段 {idx} 生成成功，时长 {duration:.2f}s")
                    # 保存状态到文件
                    self._save_status()
                    cb(idx, True, audio_path, duration)
                else:
                    self.status[idx]['status'] = 'failed'
                    self.log(f"片段 {idx} 最终生成失败，已放弃")
                    cb(idx, False, None, None)
                self._update_progress()
            else:
                time.sleep(0.5)

    def _generate_with_retry(self, index, text):
        """
        带重试的生成逻辑
        返回 (success, audio_path, duration)
        """
        retries = 0
        while retries <= self.max_retries:
            if retries > 0:
                self.log(f"片段 {index} 重试第 {retries} 次...")
                time.sleep(self.retry_delay)
            # 更新状态为 retrying（仅用于显示）
            self.status[index]['status'] = 'retrying' if retries > 0 else 'generating'
            try:
                audio_path = generate_single(
                    text=text,
                    index=index,
                    output_dir=self.work_dir,
                    ref_audio_filename=self.ref_audio_filename,
                    ref_text=self.ref_text,
                    language=self.language,
                    log_callback=self.log
                )
                if audio_path:
                    # 等待文件写入完成
                    for _ in range(30):
                        if os.path.exists(audio_path):
                            break
                        time.sleep(1)
                    if os.path.exists(audio_path):
                        duration = get_audio_duration(audio_path)
                        return True, audio_path, duration
                    else:
                        self.log(f"片段 {index} 生成文件超时不存在: {audio_path}")
                else:
                    self.log(f"片段 {index} 生成返回空路径")
            except Exception as e:
                self.log(f"片段 {index} 生成异常: {e}")
            retries += 1
        return False, None, None