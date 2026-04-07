# parsers/free_parser.py
import sys
import os
import re
import json
import concurrent.futures
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from .base_parser import BaseParser
from utils import config_manager, settings
from utils.error_logger import log_error


class FreeParser(BaseParser):
    """
    自由模式解析器：将故事文本转化为结构化剧本。
    采用两阶段 AI 调用：
    1. 分段AI：切分段落并提取全局/局部资产（纯文本输出，代码解析）
    2. 并发生成：为每个段落生成镜头剧本（镜头编号格式：段落ID-序号）
    """
    def __init__(self, call_deepseek, story_title=None, mode=None):
        super().__init__(call_deepseek, story_title, mode)
        self.metadata = None
        self.work_dir = None
        self.global_assets_text = ""   # 存储全局资产纯文本
        self.log_callback = None
        self.verbose = False

    def parse(self, raw_text: str, metadata: Optional[Dict] = None, work_dir: Optional[str] = None,
              log_callback: Optional[callable] = None, verbose: bool = False) -> Dict:
        """
        主入口：执行两阶段剧本生成，返回 {"scenes": [...]}
        log_callback: 接收字符串的回调，用于输出进度信息
        verbose: 是否输出详细日志（调试用）
        """
        self.metadata = metadata or {}
        self.work_dir = work_dir
        self.log_callback = log_callback
        self.verbose = verbose
        # 提取目标时长（分钟）
        self.target_duration_minutes = 5  # 默认5分钟
        if metadata and "目标时长" in metadata:
            dur_str = str(metadata["目标时长"])
            match = re.search(r'(\d+)', dur_str)
            if match:
                self.target_duration_minutes = int(match.group(1))
            # 删除 self.log 这一行，改为下面这样（可选）
            if log_callback:
                log_callback(f"目标总时长: {self.target_duration_minutes} 分钟")

        def log(msg, level='info'):
            if self.log_callback:
                if level == 'detail' and not self.verbose:
                    return
                prefix = "[详细] " if level == 'detail' else ""
                self.log_callback(prefix + msg)

        # 阶段一：段落切分 + 资产提取
        log("正在调用分段AI，将故事切分为逻辑段落并提取资产...")
        paragraphs_with_assets = self._extract_paragraphs_with_assets(raw_text, log)
        if not paragraphs_with_assets:
            log("分段AI失败，使用降级方案（一次性生成剧本）...")
            return self._fallback_parse(raw_text, log)

        log(f"分段完成，共 {len(paragraphs_with_assets)} 个段落")

        # 阶段二：并发生成剧本
        log("开始并发生成每个段落的剧本...")
        scenes = self._generate_scripts_parallel(paragraphs_with_assets, log)

        # 重新编号场次
        for idx, scene in enumerate(scenes, start=1):
            scene['id'] = idx

        log(f"剧本生成完成，共 {len(scenes)} 个场次")
        return {"scenes": scenes}

    # ===================== 阶段一：段落切分 =====================
    def _extract_paragraphs_with_assets(self, raw_text: str, log) -> Optional[List[Dict]]:
        prompt = self._build_segmentation_prompt(raw_text)
        result = None
        try:
            log("正在请求分段AI...")
            result = self.call_deepseek(prompt, temperature=0.3, max_tokens=8000)
            log("分段AI响应完成，开始解析...")
            if self.verbose:
                log(f"分段AI响应内容（前200字符）: {result[:200]}...", 'detail')
        except Exception as e:
            log_error('free_parser', '分段AI调用失败', str(e))
            log(f"分段AI调用失败: {e}")
            return None

        # 保存完整响应（调试用）
        if self.work_dir:
            full_path = os.path.join(self.work_dir, "segmentation_ai_response.txt")
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(result)

        # 提取并保存全局资产库文本
        global_pattern = re.compile(r'【全局资产库】\s*(.*?)(?=\n\s*【段落 \d+】|\Z)', re.DOTALL)
        global_match = global_pattern.search(str(result))
        if global_match:
            self.global_assets_text = global_match.group(1).strip()
            if self.work_dir:
                global_path = os.path.join(self.work_dir, "assets_global.txt")
                with open(global_path, 'w', encoding='utf-8') as f:
                    f.write(self.global_assets_text)
        else:
            self.global_assets_text = ""

        # 按段落分割，提取每个段落的文本和局部资产文本
        blocks = re.split(r'\n\s*【段落 \d+】\s*\n', str(result))
        paragraphs = []
        para_idx = 1
        for block in blocks:
            block = block.strip()
            if not block or block.startswith('【全局资产库】'):
                continue
            parts = re.split(r'\n\s*【局部资产】\s*\n', block, maxsplit=1)
            if len(parts) < 2:
                if self.log_callback:
                    self.log_callback(f"警告：段落{para_idx}缺少局部资产块，跳过")
                continue
            text = parts[0].strip()
            local_assets_text = parts[1].strip()   # 原始文本
            # 解析建议时长
            duration_match = re.search(r'- 建议时长：\s*(\d+)', local_assets_text)
            suggested_duration = int(duration_match.group(1)) if duration_match else 0
            paragraphs.append({
                "text": text,
                "local_assets_text": local_assets_text,
                "suggested_duration": suggested_duration   # 新增
            })
            # 保存段落局部资产到文件
            if self.work_dir:
                local_path = os.path.join(self.work_dir, f"assets_paragraph_{para_idx}.txt")
                with open(local_path, 'w', encoding='utf-8') as f:
                    f.write(local_assets_text)
            para_idx += 1

        log(f"成功解析 {len(paragraphs)} 个段落及局部资产")
        return paragraphs

    def _build_segmentation_prompt(self, raw_text: str) -> str:
        """构建分段AI的提示词（纯文本输出）"""
        meta = self.metadata
        meta_text = ""
        if meta:
            meta_text = "【创作元数据】\n"
            for k, v in meta.items():
                if v and v != "无特殊" and v != "无":
                    meta_text += f"- {k}：{v}\n"
            meta_text += "\n"

        # 提取目标时长（分钟）
        target_duration_min = 0
        if meta and "目标时长" in meta:
            dur_str = str(meta["目标时长"])   # 改为 str()
            # 假设格式为 "5分钟" 或 "5"
            match = re.search(r'(\d+)', dur_str)
            if match:
                target_duration_min = int(match.group(1))

        # 构建时长控制说明
        duration_instruction = ""
        if target_duration_min > 0:
            target_seconds = target_duration_min * 60
            duration_instruction = f"""
**重要：根据创作元数据，本次故事的目标总时长为 {target_seconds} 秒（{target_duration_min} 分钟）。**
在生成段落时，你需要为每个段落估算一个合理的时长（秒），并记录在【局部资产】的“建议时长”字段中。所有段落的建议时长总和应接近目标总时长。
"""

        prompt = f"""
你是一个专业的剧本分析助手。请完成以下任务：

{meta_text}
{duration_instruction}

1. 将以下故事按语义分割成若干逻辑段落，每个段落应围绕一个相对独立的场景或事件。
2. 从全文提取全局资产库：角色的固定属性（如外貌、气质、核心设定）、整体视觉风格。全局资产库用文本列表形式，每个资产项以“- 键：值”格式输出，放在“【全局资产库】”下方。

   **重要：角色固定属性必须严格按照以下格式输出，每个字段都要包含，且描述必须明确、肯定，不得使用“或”等模棱两可的词语。性别字段只能为“男”或“女”。如果原文没有明确，请根据上下文推断最可能的一种，并直接写出。**
   格式：
   【种族 角色名】 性别：X，年龄：X，发型：X，发色：X，脸型：X，身高：X，体型：X，惯用着装：X，气质描述：X。
   注意：种族可以是“人类”、“熊猫”、“机器人”、“精灵”等，必须写在角色名前面，用空格分隔。

   示例：
   - 角色固定属性：
     【人类 阿铁】 性别：男，年龄：少年，发型：短发，发色：黑，脸型：圆脸，身高：中等，体型：瘦削，惯用着装：深色短打工匠服，气质描述：坚韧、热血、对锻造充满纯粹热爱。
     【熊猫 阿六】 性别：男，年龄：青年，发型：短圆耳，发色：黑白相间，脸型：圆脸，身高：中等，体型：圆润敦实，惯用着装：磨损的深色背带工装裤，肩部有简易护甲，左前肢为机械义肢，佩戴护目镜，气质描述：沉稳、坚韧、沉默中带着不容动摇的执着。

3. 为每个段落提取局部资产库：该段落的场景、角色服装变化、道具、当前情绪、时间、地域等。局部资产也用文本列表形式，每个资产项以“- 键：值”格式输出。

   如果指定了目标总时长，请在【局部资产】中添加一行“- 建议时长：X秒”，表示该段落应该占用的时长。

请严格按照以下格式输出，不要添加任何额外解释：

【全局资产库】
- 整体视觉风格：...
- 角色固定属性：
  【种族 角色名】 种族：...，性别：...，年龄：...，发型：...，发色：...，脸型：...，身高：...，体型：...，惯用着装：...，气质描述：...

【段落 X】
段落文本内容...（注意：提及角色时必须使用完整名称，如“熊猫阿六”）

【局部资产】
- 场景：具体场景描述
- 角色服装：角色名：描述（如“阿铁：满脸煤灰，围裙脏旧”）
- 道具：道具1，道具2
- 时间：白天/夜晚等
- 地域：国家·时代
- 情绪：当前情绪基调
- 建议时长：X秒   （如果指定了目标总时长）

注意：
- 段落之间用空行分隔。
- 局部资产中的键名固定为：场景、角色服装、道具、时间、地域、情绪、建议时长。如果某个资产不存在，可以不写。
- 角色服装可以是多个角色的描述，用分号分隔。
- 在所有输出中，提及角色时必须使用“种族+名字”的完整形式，例如“熊猫阿六”，不得省略种族。

故事内容：
{raw_text}
"""
        return prompt

    # ===================== 阶段二：并发生成剧本 =====================
    def _generate_scripts_parallel(self, paragraphs_with_assets: List[Dict], log) -> List[Dict]:
        """并发生成每个段落的场次数据"""
        total = len(paragraphs_with_assets)
        tasks = []
        for idx, p in enumerate(paragraphs_with_assets):
            # 构建上一个段落的摘要
            prev_summary = ""
            if idx > 0:
                prev_text = paragraphs_with_assets[idx-1]['text']
                prev_summary = prev_text[:100] + "..." if len(prev_text) > 100 else prev_text
            tasks.append((idx, p['text'], p['local_assets_text'], prev_summary, p.get('suggested_duration', 0), self.target_duration_minutes))

        results = [None] * total
        with concurrent.futures.ThreadPoolExecutor(max_workers=settings.MAX_WORKERS) as executor:
            future_to_idx = {
                executor.submit(self._generate_script_for_paragraph, idx, text, local_assets, prev_summary, suggested_duration, target_duration_minutes, log): idx
                for idx, text, local_assets, prev_summary, suggested_duration, target_duration_minutes in tasks
            }
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    scene = future.result()
                    results[idx] = scene
                    if log:
                        log(f"段落 {idx+1}/{total} 生成成功")
                except Exception as e:
                    log_error('free_parser', f'段落{idx+1}生成失败', str(e))
                    if log:
                        log(f"段落 {idx+1}/{total} 生成失败: {e}")
                    results[idx] = None

        # 合并结果，对失败段落使用后备场次
        all_scenes = []
        for i, scene in enumerate(results):
            if scene is not None:
                all_scenes.append(scene)
            else:
                fallback = self._create_fallback_scene(paragraphs_with_assets[i]['text'])
                all_scenes.append(fallback)
                if log:
                    log(f"段落 {i+1} 使用后备场次")
        return all_scenes

    def _generate_script_for_paragraph(self, idx: int, text: str, local_assets_text: str, prev_summary: str, suggested_duration: int, target_duration_minutes: int, log) -> Dict:
        """为单个段落生成场次数据"""
        paragraph_index = idx + 1  # 1-based，用于镜头编号
        prompt = self._build_paragraph_prompt(text, local_assets_text, prev_summary, paragraph_index, suggested_duration, target_duration_minutes)
        try:
            if log:
                log(f"段落 {paragraph_index} 正在调用剧本AI...")
            result = self.call_deepseek(prompt, temperature=0.7, max_tokens=4000)
            if log:
                log(f"段落 {paragraph_index} AI响应完成，开始解析...")
            if self.verbose:
                log(f"段落 {paragraph_index} AI响应（前200字符）: {result[:200]}...", 'detail')
        except Exception as e:
            log_error('free_parser', f'段落{paragraph_index} AI调用失败', str(e))
            raise
        scene = self._parse_single_scene(result, paragraph_index)
        if not scene:
            raise ValueError(f"解析场次失败: {result[:200]}")
        scene['paragraph_index'] = idx
        for shot in scene.get('shots', []):
            shot['paragraph_index'] = idx
        return scene

    def _build_paragraph_prompt(self, text: str, local_assets_text: str, prev_summary: str, paragraph_index: int, suggested_duration: int = 0, target_duration_minutes: int = 5) -> str:
        """构建单个段落的剧本生成提示词（纯文本输出）"""
        # 计算整个故事的总字数上限（中文约 200 字/分钟）
        max_total_chars = target_duration_minutes * 200
        
        global_duration_instruction = f"""
**重要：整个故事的目标总时长为 {target_duration_minutes} 分钟，因此所有段落的旁白/对白总字数不应超过 {max_total_chars} 字。**
请你在生成以下段落的分镜头剧本时，严格遵循这一总字数限制，合理分配本段落的旁白/对白字数。如果本段落分配的字数过多，请精简文本。
"""
        meta = self.metadata
        meta_text = ""
        if meta:
            meta_text = "【创作元数据】\n"
            for k, v in meta.items():
                if v and v != "无特殊" and v != "无":
                    meta_text += f"- {k}：{v}\n"
            meta_text += "\n"

        global_text = self.global_assets_text if hasattr(self, 'global_assets_text') and self.global_assets_text else "无"
        local_text = local_assets_text if local_assets_text else "无"

        duration_instruction = ""
        if suggested_duration > 0:
            duration_instruction = f"""
**重要：此段落的目标时长配额为 {suggested_duration} 秒。**
请生成该段落的分镜头剧本，确保所有镜头的时长总和接近此配额（允许小幅偏差）。每个镜头时长必须在5-15秒之间，根据剧情需要合理分配。
"""
        else:
            duration_instruction = """
**重要：每个镜头的时长必须在5-15秒之间**，根据剧情需要合理分配。
"""

        dialogue_rule = """
【对白与时长匹配规则】（必须严格遵守）
- 中文对白/旁白：按平均语速 3.5 字/秒 计算所需最小秒数。
- 公式：最小时长 = ceil(对白/旁白总字数 / 3.5)
- 每个镜头的最终时长必须 >= 最小时长，且不超过 15 秒。
- 如果某个镜头的对白/旁白为空，时长可在 5-15 秒之间自由分配。
- 示例：对白“你好吗”（3字）→ 最小时长 1 秒，但镜头时长应至少 5 秒；对白“这是一句很长的旁白，大约有二十八个字”（28字）→ 最小时长 8 秒，则镜头时长必须 >=8 秒。
"""

        prompt = f"""
你是一位专业的影视编剧。请根据以下信息，为这一段故事生成分镜头剧本。注意：镜头编号格式为“【镜头{paragraph_index}-{{序号}}：标题】”。

{meta_text}
{global_duration_instruction}   # 新增
【全局资产库】（角色固定属性、整体风格）
{global_text}

【当前段落的局部资产】（场景、角色服装变化、道具等）
{local_text}

【上一段落的简要摘要】（用于剧情衔接）
{prev_summary}

【当前段落的故事文本】
{text}

{duration_instruction}
{dialogue_rule}

请严格按照以下格式输出，每个镜头单独一块，用空行分隔。镜头顺序按故事发展排列。

【镜头{paragraph_index}-1：标题】
- 场景：地点，时间，环境
- 角色：本镜头出现的角色列表，必须使用完整名称（种族+名字），例如“熊猫阿六”、“人类李雷”。可多个，用逗号分隔。
- 动作：人物的具体动作描述
- 对白：角色A：“台词” / 角色B：“台词” （多个对白用 / 分隔）
- 视觉描述：关键画面描述，包括光影、色调、氛围等
- 时长：X秒（必须满足上述对白时长规则，且范围 5-15 秒）
- 情绪基调：XX
- 地域：国家·时代（例如“中国·唐朝”或“全球·无明确时代”）

【镜头{paragraph_index}-2：标题】
...

注意：
- 对白中的引号使用中文引号“”。
- 输出中不要有任何额外解释，只输出镜头块。
- 如果局部资产中提到了特定服装、道具，请在镜头中体现。
- 请根据对白字数合理设置时长，避免旁白念不完。
**重要：请严格按照对白时长规则计算每个镜头的时长，确保旁白/对白能够完整朗读，不得过短。**
"""
        return prompt

    def _parse_single_scene(self, text: str, paragraph_index: int) -> Optional[Dict]:
        """解析单个段落的镜头块，返回场次字典"""
        # 直接解析镜头块，不依赖场次标题
        shot_blocks = re.split(r'\n\s*【镜头\d+-\d+：', str(text))
        shots = []
        for block in shot_blocks:
            if not block.strip():
                continue
            # 可能第一个块之前有文本，忽略
            if block.startswith('【镜头'):
                block = '【镜头' + block
            shot = self._parse_shot(block)
            if shot:
                shots.append(shot)
        if not shots:
            return None
        title = f"段落{paragraph_index}"
        return {
            'id': 0,
            'title': title,
            'shots': shots
        }

    def _create_fallback_scene(self, text: str) -> Dict:
        return {
            "id": 0,
            "title": "段落生成失败",
            "shots": [
                {
                    "scene": "未知",
                    "roles": [],
                    "action": "（由于AI生成失败，此镜头为默认内容）",
                    "dialogue": "",
                    "visual": "请根据原始故事手动编辑",
                    "duration": 10.0,
                    "emotion": "中性",
                    "region": "全球·无明确时代"
                }
            ]
        }

    # ===================== 降级方案 =====================
    def _fallback_parse(self, raw_text: str, log) -> Dict:
        prompt = self._build_script_prompt(raw_text)
        try:
            log("正在调用剧本AI（降级模式）...")
            result = self.call_deepseek(prompt, temperature=0.7, max_tokens=8000)
            if self.verbose:
                log(f"降级AI响应（前200字符）: {result[:200]}...", 'detail')
        except Exception as e:
            log_error('free_parser', '降级AI调用失败', str(e))
            raise
        script_data = self._parse_script(result)
        for idx, scene in enumerate(script_data, start=1):
            scene['id'] = idx
        return {"scenes": script_data}

    def _build_script_prompt(self, story_text: str) -> str:
        meta = self.metadata
        meta_text = ""
        if meta:
            meta_text = "【创作元数据】\n"
            for k, v in meta.items():
                if v and v != "无特殊" and v != "无":
                    meta_text += f"- {k}：{v}\n"
            meta_text += "\n"

        prompt = f"""
你是一位专业的影视编剧。请将以下故事改编成一份分场分镜剧本，适合用于视频制作。

{meta_text}
故事内容：
{story_text}

请严格按照以下格式输出，每个场次用 `【场次X：标题】` 分隔，每个镜头用 `【镜头X】` 分隔。其中 X 从 1 开始递增，不要重复使用同一个数字。每个镜头包含以下字段：
- 场景：地点，时间，环境
- 角色：本镜头出现的角色列表（可多个）
- 动作：人物的具体动作描述
- 对白：角色A：“台词” / 角色B：“台词” （多个对白用 / 分隔）
- 视觉描述：关键画面描述，包括光影、色调、氛围等
- 时长：X秒（建议5-15秒）
- 情绪基调：XX
- 地域：国家·时代（例如“中国·宋朝”或“全球·无明确时代”）

注意：
- 输出中不要有任何额外解释，只输出剧本。
- 对白中的引号使用中文引号“”。
- 每个字段一行，格式为 `- 字段名：值`。

示例：
【场次1：开篇】
【镜头1】
- 场景：云中谷地·训练场，黄昏
- 角色：小翼，灰烬（幼龙）
- 动作：小翼蹲下，轻轻抚摸灰烬的头
- 对白：小翼：“别听他们的。” / 灰烬：“（发出一声微弱的呜咽）”
- 视觉描述：金色余晖洒落，灰烬的鳞片暗淡无光，小翼的眼神充满关切
- 时长：8秒
- 情绪基调：忧伤、坚定
- 地域：全球·无明确时代
【镜头2】
...

请开始输出：
"""
        return prompt

    def _parse_script(self, text: str) -> List[Dict]:
        scenes = []
        scene_blocks = re.split(r'\n\s*【场次[^】]+：', str(text))
        for block in scene_blocks:
            if not block.strip():
                continue
            if not block.startswith('【场次'):
                lines = block.strip().split('\n')
                title = lines[0].strip() if lines else "未命名场次"
                block = '【场次1：' + title + '】' + '\n'.join(lines[1:])
            header_match = re.match(r'【场次[^】]+：([^】]+)】', block)
            if not header_match:
                continue
            scene_title = header_match.group(1).strip()
            shot_blocks = re.split(r'\n\s*【镜头\d+】', block)
            shots = []
            for shot_block in shot_blocks:
                if not shot_block.strip() or shot_block.startswith('【场次'):
                    continue
                shot = self._parse_shot(shot_block)
                if shot:
                    shots.append(shot)
            scenes.append({
                'id': 0,
                'title': scene_title,
                'shots': shots
            })
        return scenes

    def _parse_shot(self, shot_block: str) -> Dict:
        shot = {
            'scene': '',
            'title': '',
            'roles': [],
            'action': '',
            'dialogue': '',
            'visual': '',
            'duration': 10,
            'emotion': '',
            'region': '全球·无明确时代'
        }
        lines = shot_block.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith('- 场景：'):
                shot['scene'] = line.split('：', 1)[-1].strip()
            elif line.startswith('- 角色：'):
                roles_str = line.split('：', 1)[-1].strip()
                shot['roles'] = [r.strip() for r in roles_str.split(',')]
            elif line.startswith('- 动作：'):
                shot['action'] = line.split('：', 1)[-1].strip()
            elif line.startswith('- 对白：'):
                shot['dialogue'] = line.split('：', 1)[-1].strip()
            elif line.startswith('- 视觉描述：'):
                shot['visual'] = line.split('：', 1)[-1].strip()
            elif line.startswith('- 时长：'):
                dur_str = line.split('：', 1)[-1].strip()
                try:
                    shot['duration'] = float(dur_str.replace('秒', ''))
                except:
                    pass
            elif line.startswith('- 情绪基调：'):
                shot['emotion'] = line.split('：', 1)[-1].strip()
            elif line.startswith('- 地域：'):
                shot['region'] = line.split('：', 1)[-1].strip()
        return shot