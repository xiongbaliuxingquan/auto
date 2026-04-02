"""
================================================================================
【重要修改提示】
本文件的所有节点ID均从 workflow_config.json 读取，不得在此处硬编码！
如需修改节点映射，请直接编辑 workflow_config.json 中的对应模板配置。
任何修改前，务必与用户确认当前使用的模板及对应节点ID。

新增功能：
- 支持从 user_settings.json 读取 MAX_RETRIES（最大重试次数）和 RETRY_DELAY（重试间隔秒数）。
- 视频生成分为两阶段：
    1. 初次运行：依次生成所有选中的镜头，记录失败的镜头（任何异常或下载失败）。
    2. 重试阶段：根据设置对失败的镜头进行重试，重试间按指定间隔等待。
- 日志中会明确显示失败镜头列表和重试进度。
- 生成镜头清单（纯文本）和 FFmpeg 合并列表，方便剪辑和合成。
- 健康检查：每10秒检查 ComfyUI 服务是否存活，异常时立即返回失败。
- 等待日志：每10秒输出一次等待进度。
- 记录每个镜头的生成时间。
================================================================================
"""
import os
import re
import requests
import json
import time
import urllib.parse
from datetime import datetime

# 导入配置管理，用于读取重试参数
from utils import config_manager
from utils.error_logger import log_error

class ComfyUIManager:
    def __init__(self, api_url, output_base_dir, fps=24, max_duration=20, on_shot_generated=None):
        self.api_url = api_url
        self.output_base_dir = output_base_dir
        self.fps = fps
        self.max_duration = max_duration
        self.log_callback = None
        self.config = self._load_workflow_config()
        self.max_retries = config_manager.MAX_RETRIES
        self.retry_delay = config_manager.RETRY_DELAY
        self.on_shot_generated = on_shot_generated   # 新增回调

    def _load_workflow_config(self):
        config_path = os.path.join(os.path.dirname(__file__), '..', 'workflow_config.json')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"警告：无法加载 workflow_config.json，请确保文件存在且格式正确。{e}")
            log_error('comfyui_manager', '加载workflow_config失败', str(e))
            return {}

    def set_log_callback(self, callback):
        self.log_callback = callback

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def get_latest_readable_file(self, work_dir, pattern="分镜结果_易读版_*.txt"):
        import glob
        full_pattern = os.path.join(work_dir, pattern)
        files = glob.glob(full_pattern)
        if not files:
            return None
        return max(files, key=os.path.getmtime)

    def get_shots_info(self, readable_file):
        """从易读版分镜文件中提取所有镜头信息"""
        with open(readable_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        shots = []
        i = 0
        total = len(lines)
        while i < total:
            line = lines[i].strip()
            # 尝试匹配多种括号格式，贪婪取到行尾
            match = re.search(r'[\[【\(]镜头.*?(\d+-\d+)[：:](.*)', line)
            if match:
                shot_id = match.group(1)
                title = match.group(2).rstrip('】)').strip()
            else:
                # 如果仍不匹配，尝试旧格式（严格中文括号）
                match = re.match(r'【镜头(\d+-\d+)：([^】]+)】', line)
                if match:
                    shot_id = match.group(1)
                    title = match.group(2)
                else:
                    i += 1
                    continue

            # 匹配成功后，读取本镜头的后续内容
            content_lines = []
            i += 1
            while i < total and not lines[i].strip().startswith('【镜头'):
                content_lines.append(lines[i].rstrip('\n'))
                i += 1
            body = '\n'.join(content_lines)

            duration_match = re.search(r'时长[：:]\s*(\d+)', body)
            if not duration_match:
                continue
            duration = int(duration_match.group(1))

            prompt_lines = []
            prompt_started = False
            for line in content_lines:
                stripped = line.strip()
                if stripped.startswith('提示词：') or stripped.startswith('- 提示词：'):
                    prompt_started = True
                    colon_pos = line.find('：')
                    if colon_pos == -1:
                        colon_pos = line.find(':')
                    if colon_pos != -1:
                        after_colon = line[colon_pos+1:].strip()
                        if after_colon:
                            prompt_lines.append(after_colon)
                elif prompt_started:
                    if stripped.startswith('-') and not stripped.startswith('- 提示词：'):
                        break
                    prompt_lines.append(line.strip())
            if not prompt_lines:
                continue
            prompt = ' '.join(prompt_lines).strip()

            shots.append({
                'id': shot_id,
                'title': title,
                'prompt': prompt,
                'duration': duration
            })

        print(f"找到 {len(shots)} 个镜头")
        return shots

    def download_video(self, output_info, save_path):
        """下载视频/动图，自动重命名"""
        video_url = output_info.get('url') or output_info.get('filename')
        if not video_url:
            self._log("未找到媒体文件下载链接")
            return False

        if video_url.startswith('http'):
            url = video_url
        else:
            params = {'filename': video_url}
            if 'subfolder' in output_info and output_info['subfolder']:
                params['subfolder'] = output_info['subfolder']
            if 'type' in output_info:
                params['type'] = output_info['type']
            url = f"{self.api_url}/view?{urllib.parse.urlencode(params)}"

        self._log(f"下载 URL: {url}")

        base, ext = os.path.splitext(save_path)
        final_path = save_path
        counter = 1
        while os.path.exists(final_path):
            final_path = f"{base}_{counter}{ext}"
            counter += 1
        self._log(f"目标文件: {final_path}")

        try:
            resp = requests.get(url, stream=True, timeout=60)
            self._log(f"下载响应状态码: {resp.status_code}")
            resp.raise_for_status()
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            with open(final_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            file_size = os.path.getsize(final_path)
            self._log(f"文件大小: {file_size} 字节")
            if file_size == 0:
                self._log("错误：文件大小为0，下载失败")
                return False
            if file_size < 1024 * 1024:
                self._log("提示：文件小于1MB，但已成功下载（可能为短视频）")
            self._log(f"文件已保存至: {final_path}")
            return True
        except requests.exceptions.RequestException as e:
            self._log(f"下载请求异常: {e}")
            log_error('comfyui_manager', f'下载请求异常 ({save_path})', str(e))
            return False
        except Exception as e:
            self._log(f"下载过程中发生未知异常: {e}")
            log_error('comfyui_manager', f'下载未知异常 ({save_path})', str(e))
            return False

    def _generate_single_shot(self, shot, workflow_template, width, height, output_dir,
                              frame_count_node, fps_node, prompt_node, resolution_node, sampler_node, output_node, current=0, total=0):
        """
        内部方法：生成单个镜头，返回 (成功, 镜头ID, 扩展名, 生成时间字符串) 或 (失败, 错误信息, None, None)
        """
        shot_id = shot['id']
        prompt = shot['prompt']
        self._log(f"正在生成镜头 {shot_id} ...")

        workflow = json.loads(json.dumps(workflow_template))

        # 替换节点
        if prompt_node in workflow:
            workflow[prompt_node]['inputs']['prompt'] = prompt
            self._log(f"节点 {prompt_node} 提示词: {prompt[:30]}...")
        else:
            self._log(f"警告：模板中无节点 {prompt_node}")

        if resolution_node in workflow:
            workflow[resolution_node]['inputs']['width'] = width
            workflow[resolution_node]['inputs']['height'] = height
            self._log(f"节点 {resolution_node} 分辨率: {width}x{height}")
        else:
            self._log(f"警告：模板中无节点 {resolution_node}")

        if sampler_node in workflow:
            workflow[sampler_node]['inputs']['seed'] = int(time.time() * 1000) % 2**32
            self._log(f"节点 {sampler_node} 种子已更新")
        else:
            self._log(f"警告：模板中无节点 {sampler_node}")

        if output_node in workflow:
            workflow[output_node]['inputs']['filename_prefix'] = f"shot_{shot_id}"
            self._log(f"节点 {output_node} 文件名前缀: shot_{shot_id}")
        else:
            self._log(f"警告：模板中无节点 {output_node}")

        # 设置帧数节点
        if frame_count_node and frame_count_node in workflow:
            duration = shot.get('duration', 10)
            import math
            target_frames = math.ceil(duration * self.fps)
            base_frames = ((target_frames - 1 + 7) // 8) * 8 + 1
            final_frames = base_frames + 24
            workflow[frame_count_node]['inputs']['value'] = final_frames
            self._log(f"节点 {frame_count_node} 帧数: {final_frames} (目标帧数 {target_frames}, 基础 {base_frames})")

        # 提交任务
        payload = {"prompt": workflow}
        try:
            resp = requests.post(f"{self.api_url}/prompt", json=payload, timeout=30)
            if resp.status_code != 200:
                error_msg = f"提交失败: {resp.status_code} {resp.text}"
                self._log(error_msg)
                return False, error_msg, None, None
            prompt_id = resp.json()['prompt_id']
            self._log(f"镜头 {shot_id} 提交成功，prompt_id: {prompt_id}")
            if total > 0:
                self._log(f"共{total}条，已提交{current}条，剩余{total-current}条")

            start_wait = time.time()
            timeout = 900  # 超时时间（秒）
            last_health_check = start_wait
            last_log_time = start_wait

            while time.time() - start_wait < timeout:
                # 每 10 秒检查服务状态
                if time.time() - last_health_check >= 10:
                    last_health_check = time.time()
                    try:
                        health_resp = requests.get(f"{self.api_url}/system_stats", timeout=5)
                        if health_resp.status_code != 200:
                            self._log(f"镜头 {shot_id} ComfyUI 服务异常，状态码: {health_resp.status_code}")
                            return False, "ComfyUI服务异常: 服务响应异常", None, None
                    except requests.exceptions.Timeout:
                        self._log(f"镜头 {shot_id} ComfyUI 健康检查超时")
                        return False, "ComfyUI服务异常: 健康检查超时", None, None
                    except requests.exceptions.ConnectionError:
                        self._log(f"镜头 {shot_id} ComfyUI 连接失败")
                        return False, "ComfyUI服务异常: 无法连接", None, None
                    except Exception as e:
                        self._log(f"镜头 {shot_id} ComfyUI 健康检查异常: {e}")
                        return False, f"ComfyUI服务异常: {e}", None, None

                # 每 10 秒输出等待日志
                if time.time() - last_log_time >= 10:
                    self._log(f"正在等待镜头 {shot_id} 生成...（已等待 {int(time.time() - start_wait)} 秒）")
                    last_log_time = time.time()

                time.sleep(2)
                history_resp = requests.get(f"{self.api_url}/history/{prompt_id}", timeout=30)
                if history_resp.status_code == 200:
                    history = history_resp.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get('outputs', {})
                        if output_node in outputs:
                            node_out = outputs[output_node]
                            media_files = []
                            if 'videos' in node_out:
                                media_files = node_out['videos']
                            elif 'gifs' in node_out:
                                media_files = node_out['gifs']
                            if media_files:
                                media_info = media_files[0]
                                filename = media_info.get('filename', '')
                                ext = os.path.splitext(filename)[1] or '.gif'
                                save_path = os.path.join(output_dir, f"镜头{shot_id}{ext}")
                                if self.download_video(media_info, save_path):
                                    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    if self.on_shot_generated:
                                        self.on_shot_generated(shot_id)
                                    return True, shot_id, ext, gen_time
                                else:
                                    return False, "下载失败", None, None
                            else:
                                self._log(f"节点 {output_node} 输出中无 videos 或 gifs")
                        else:
                            # 遍历所有输出
                            for out_node in outputs.values():
                                media_files = []
                                if 'videos' in out_node:
                                    media_files = out_node['videos']
                                elif 'gifs' in out_node:
                                    media_files = out_node['gifs']
                                if media_files:
                                    media_info = media_files[0]
                                    filename = media_info.get('filename', '')
                                    ext = os.path.splitext(filename)[1] or '.gif'
                                    save_path = os.path.join(output_dir, f"镜头{shot_id}{ext}")
                                    if self.download_video(media_info, save_path):
                                        gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                        return True, shot_id, ext, gen_time
                                    else:
                                        return False, "下载失败", None, None
                            # 没有找到任何媒体文件
                            self._log(f"未在输出中找到媒体文件")
                            return False, "未找到媒体文件", None, None
                time.sleep(1)
            # 超时
            self._log(f"镜头 {shot_id} 等待超时")
            return False, "等待超时", None, None
        except Exception as e:
            self._log(f"镜头 {shot_id} 生成异常: {e}")
            log_error('comfyui_manager', f'镜头{shot_id}生成异常', str(e))
            return False, str(e), None, None

    def run(self, story_title, work_dir, resolution, template_path, selected_shots=None, edits=None):
        """
        生成视频（支持失败重试）
        :param story_title: 故事标题
        :param work_dir: 工作目录
        :param resolution: 分辨率，如 "1280x720"
        :param template_path: 模板路径
        :param selected_shots: 可选，要生成的镜头ID列表
        :param edits: 可选，编辑过的提示词字典 {id: new_prompt}
        :return: (success, message)
        """
        # 获取节点映射
        workflow_name = "LTX2.3"  # 可扩展
        nodes = self.config.get(workflow_name, {})
        prompt_node = nodes.get('prompt_node')
        resolution_node = nodes.get('resolution_node')
        sampler_node = nodes.get('sampler_node')
        output_node = nodes.get('output_node')
        frame_count_node = nodes.get('frame_count_node')
        fps_node = nodes.get('fps_node')

        if not all([prompt_node, resolution_node, sampler_node, output_node]):
            self._log(f"错误：配置文件缺少 {workflow_name} 的节点映射")
            return False, "节点配置缺失"

        try:
            width, height = map(int, resolution.split('x'))
        except:
            self._log(f"分辨率格式错误: {resolution}")
            log_error('comfyui_manager', '分辨率格式错误', resolution)
            return False, "分辨率格式错误"

        output_dir = self.output_base_dir
        os.makedirs(output_dir, exist_ok=True)
        self._log(f"视频将保存至: {output_dir}")

        readable_file = self.get_latest_readable_file(work_dir)
        if not readable_file:
            self._log("未找到分镜结果易读版文件")
            return False, "未找到分镜文件"

        all_shots = self.get_shots_info(readable_file)
        if not all_shots:
            self._log("未提取到镜头信息")
            return False, "未提取到镜头信息"

        if selected_shots is not None:
            shots_to_generate = [s for s in all_shots if s['id'] in selected_shots]
            if not shots_to_generate:
                self._log("未选中任何有效镜头")
                return False, "未选中任何镜头"
            self._log(f"共选中 {len(shots_to_generate)} 个镜头进行生成")
        else:
            shots_to_generate = all_shots
            self._log(f"共 {len(shots_to_generate)} 个镜头，全部生成")

        with open(template_path, 'r', encoding='utf-8') as f:
            template = json.load(f)

        # ---------- 第一阶段：初次运行 ----------
        self._log("\n===== 开始初次生成 =====\n")
        manifest = [None] * len(shots_to_generate)
        id_to_index = {shot['id']: idx for idx, shot in enumerate(shots_to_generate)}
        failed_shots = []
        success_count = 0

        service_fail_count = 0
        MAX_SERVICE_FAIL = 5

        for idx, shot in enumerate(shots_to_generate):
            if edits and shot['id'] in edits:
                shot = shot.copy()
                shot['prompt'] = edits[shot['id']]
            current = idx + 1
            total = len(shots_to_generate)
            success, result, ext, gen_time = self._generate_single_shot(
                shot, template, width, height, output_dir,
                frame_count_node, fps_node, prompt_node, resolution_node, sampler_node, output_node,
                current=current, total=total
            )
            if success:
                success_count += 1
                manifest[idx] = {
                    "order": success_count,
                    "id": shot['id'],
                    "file": f"镜头{shot['id']}{ext}",
                    "duration": shot.get('duration', 10),
                    "prompt": shot['prompt'],
                    "time": gen_time
                }
                self._log(f"镜头 {shot['id']} 生成成功，进度：{success_count}/{total}")
                service_fail_count = 0  # 成功一次，重置计数
            else:
                # 检查是否是服务异常
                if result and result.startswith("ComfyUI服务异常:"):
                    service_fail_count += 1
                    self._log(f"检测到服务异常 ({service_fail_count}/{MAX_SERVICE_FAIL})")
                    if service_fail_count >= MAX_SERVICE_FAIL:
                        self._log("连续多次服务异常，终止生成")
                        return False, "ComfyUI服务异常: 连续多次连接失败，请检查服务是否运行"
                failed_shots.append((shot, result))
                self._log(f"镜头 {shot['id']} 初次生成失败: {result}")

        self._log(f"\n初次生成完成，成功 {success_count}/{len(shots_to_generate)} 个镜头")
        if not failed_shots:
            self._log("所有镜头生成成功，无需重试")
            self._write_manifest(manifest, output_dir)
            self._append_video_info_to_readable(work_dir, manifest)
            return True, f"成功 {success_count}/{len(shots_to_generate)}"

        # ---------- 第二阶段：重试 ----------
        self._log(f"\n===== 开始重试失败镜头，最大重试次数 {self.max_retries}，间隔 {self.retry_delay} 秒 =====\n")
        retry_service_fail_count = 0
        for attempt in range(1, self.max_retries + 1):
            if not failed_shots:
                break
            self._log(f"\n--- 第 {attempt} 次重试（共 {self.max_retries} 次）---")
            next_failed = []
            for shot, last_error in failed_shots:
                self._log(f"重试镜头 {shot['id']}，上次错误: {last_error}")
                success, result, ext, gen_time = self._generate_single_shot(
                    shot, template, width, height, output_dir,
                    frame_count_node, fps_node, prompt_node, resolution_node, sampler_node, output_node
                )
                if success:
                    success_count += 1
                    self._log(f"镜头 {shot['id']} 重试成功")
                    idx = id_to_index[shot['id']]
                    manifest[idx] = {
                        "order": success_count,
                        "id": shot['id'],
                        "file": f"镜头{shot['id']}{ext}",
                        "duration": shot.get('duration', 10),
                        "prompt": shot['prompt'],
                        "time": gen_time
                    }
                else:
                    self._log(f"镜头 {shot['id']} 重试失败: {result}")
                    # 检查服务异常
                    if result and result.startswith("ComfyUI服务异常:"):
                        retry_service_fail_count += 1
                        self._log(f"重试阶段检测到服务异常 ({retry_service_fail_count}/{MAX_SERVICE_FAIL})")
                        if retry_service_fail_count >= MAX_SERVICE_FAIL:
                            self._log("重试阶段连续多次服务异常，终止生成")
                            return False, "ComfyUI服务异常: 连续多次连接失败，请检查服务是否运行"
                    next_failed.append((shot, result))
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
            failed_shots = next_failed

        # ---------- 最终结果 ----------
        self._log(f"\n===== 生成完成 =====")
        if failed_shots:
            self._log(f"仍有 {len(failed_shots)} 个镜头失败，列表如下：")
            for shot, err in failed_shots:
                self._log(f"  {shot['id']}: {err}")
            self._write_manifest(manifest, output_dir)
            return False, f"部分镜头失败，成功 {success_count}/{len(shots_to_generate)}"
        else:
            self._log(f"所有镜头生成成功，共 {success_count} 个")
            self._write_manifest(manifest, output_dir)
            return True, f"成功 {success_count}/{len(shots_to_generate)}"
    def _append_video_info_to_readable(self, work_dir, manifest):
        """将视频信息追加到易读版分镜文件中"""
        import re
        readable_file = self.get_latest_readable_file(work_dir)
        if not readable_file:
            self._log("未找到易读版分镜文件，无法追加视频信息。")
            return

        self._log(f"正在为易读版追加视频信息：{readable_file}")
        with open(readable_file, 'r', encoding='utf-8') as f:
            content = f.read()

        blocks = re.split(r'\n\s*={5,}\s*\n', content.strip())

        shot_info = {}
        for item in manifest:
            if item is None:
                continue
            shot_id = item['id']
            shot_info[shot_id] = (item['file'], item['time'])

        new_blocks = []
        for block in blocks:
            header_match = re.search(r'【镜头(\d+-\d+)：', block)
            if header_match:
                shot_id = header_match.group(1)
                file_name, gen_time = shot_info.get(shot_id, (None, None))
                lines = block.split('\n')
                new_lines = []
                inserted = False
                for line in lines:
                    new_lines.append(line)
                    if not inserted and (line.startswith('- 提示词：') or line.startswith('- 分镜设计：')):
                        if file_name:
                            new_lines.append(f'- 视频文件：{file_name}')
                        if gen_time:
                            new_lines.append(f'- 生成时间：{gen_time}')
                        inserted = True
                if not inserted:
                    if file_name:
                        new_lines.append(f'- 视频文件：{file_name}')
                    if gen_time:
                        new_lines.append(f'- 生成时间：{gen_time}')
                new_blocks.append('\n'.join(new_lines))
            else:
                new_blocks.append(block)

        new_content = '\n===========================\n'.join(new_blocks)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_readable = os.path.join(work_dir, f"分镜结果_易读版_最终_{timestamp}.txt")
        with open(final_readable, 'w', encoding='utf-8') as f:
            f.write(new_content)
        self._log(f"最终易读版已生成：{final_readable}")

    def _write_manifest(self, manifest, output_dir):
        """写入 FFmpeg 合并列表（不再生成镜头清单）"""
        success_items = [item for item in manifest if item is not None]

        # 生成 FFmpeg 合并列表
        concat_path = os.path.join(output_dir, "concat_list.txt")
        with open(concat_path, 'w', encoding='utf-8') as f:
            for item in success_items:
                f.write(f"file '{item['file']}'\n")
        self._log(f"FFmpeg 合并列表已保存至: {concat_path}")