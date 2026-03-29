# parsers/analysis_parser.py
"""
================================================================================
【重要修改提示】
本文件已重构，实现：
1. 第一次处理：按规则切分原文为镜头片段（按完整句子，时长控制在3~15秒）。
2. 第二次 AI 调用：为每个镜头生成标题、时长、情绪、地域、视觉描述（口播稿由规则切分提供）。
================================================================================
"""
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from .base_batch_parser import BatchParser
from utils import config_manager
from utils.concurrent_utils import concurrent_process
from utils import settings

# 语速设置：字/秒
WORDS_PER_SECOND = 4.5
MIN_DURATION = 3.0
MAX_DURATION = 15.0

class AnalysisParser(BatchParser):
    def parse(self, raw_text):
        default_global = {
            "style": "电影感、写实、自然光影",
            "seed": 12345
        }

        # 1. 全局语义分段
        print("正在将全文分割为逻辑段落...")
        paragraphs = self._split_into_paragraphs(raw_text)
        if not paragraphs:
            # 如果分割失败，使用后备方案（按空行分割）
            print("全局分段失败，使用后备方案（按空行分割）")
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', raw_text) if p.strip()]
        print(f"共分割为 {len(paragraphs)} 个逻辑段落")

        # 2. 规则切分：将每个段落按句子切分为镜头片段
        print("开始规则切分（按完整句子+时长约束）...")
        all_scripts = []  # 每个元素为 (para_text, list_of_scripts)
        for idx, para in enumerate(paragraphs, start=1):
            scripts = self._split_into_shot_segments(para)
            print(f"段落 {idx} 切分为 {len(scripts)} 个镜头")
            all_scripts.append((para, scripts))

        # 3. 对每个段落的每个镜头，进行第二次 AI 调用（生成属性）
        print("开始第二次 AI 调用（生成镜头属性）...")
        all_segments = []
        for idx, (para, scripts) in enumerate(all_scripts, start=1):
            if not scripts:
                print(f"段落 {idx} 无有效镜头，跳过")
                continue
            print(f"处理段落 {idx} 的 {len(scripts)} 个镜头...")
            shots = self._generate_shot_attributes(para, scripts)
            all_segments.append({
                "id": idx,
                "title": f"段落{idx}",
                "content": para,
                "shots": shots
            })

        # 4. 构建最终输出
        output_data = {
            "project": self.story_title or "文明结构分析",
            "global": default_global,
            "persona": {},
            "scene": {},
            "segments": all_segments
        }
        return output_data

    def _split_into_paragraphs(self, raw_text, max_chars=300):
        """
        调用 AI 将整篇文稿分割成逻辑段落。
        返回段落列表，每个段落是一个字符串。
        """
        prompt = f"""
你是一个专业的文本分析助手。请将以下整篇文稿，按语义分割成若干个逻辑段落。

要求：
1. 每个段落应围绕一个相对独立的主题或观点。
2. 段落的长度应尽量控制在 {max_chars} 字以内。
3. 段落必须在句号、问号、感叹号等完整句子结束处断开，不能在逗号、顿号等中间断开。
4. 保持原文的文字顺序，不得打乱。
5. 不要添加任何额外说明，只输出一个 JSON 数组，每个元素是一个段落的文本。

文稿内容：
{raw_text}
"""
        response = self.call_deepseek(prompt, temperature=0.3, max_tokens=8000)
        import json
        try:
            clean = response.strip()
            if clean.startswith('```json'):
                clean = clean[7:]
            if clean.startswith('```'):
                clean = clean[3:]
            if clean.endswith('```'):
                clean = clean[:-3]
            clean = clean.strip()
            paragraphs = json.loads(clean)
            if isinstance(paragraphs, list):
                return paragraphs
            else:
                raise ValueError("返回的不是数组")
        except Exception as e:
            print(f"全局分段失败: {e}")
            return None

    def _split_into_shot_segments(self, text):
        """
        规则切分：将文本按完整句子拆分成若干片段，每个片段时长控制在 [MIN_DURATION, MAX_DURATION] 秒。
        返回片段列表（每个片段是字符串）。
        """
        # 1. 按句子切分（。！？…）保留标点
        sentences = re.split(r'(?<=[。！？…])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return []

        # 2. 估算每个句子的时长（秒）
        word_counts = [len(s) for s in sentences]
        durations = [wc / WORDS_PER_SECOND for wc in word_counts]

        # 3. 合并过短句子，避免拆分过长句子
        segments = []
        current_seg = []
        current_dur = 0.0

        for i, (sent, dur) in enumerate(zip(sentences, durations)):
            # 如果当前句子本身超过最大时长，强制拆分（但这种情况很少见，因为按句子切分后通常不会超过）
            if dur > MAX_DURATION:
                # 如果当前有未结束的片段，先结束
                if current_seg:
                    segments.append(''.join(current_seg))
                    current_seg = []
                    current_dur = 0.0
                # 超过最大时长的句子直接作为一个片段（不再切分句子，因为按完整句子原则）
                segments.append(sent)
                continue

            # 尝试将当前句子加入当前片段
            if current_dur + dur <= MAX_DURATION:
                current_seg.append(sent)
                current_dur += dur
            else:
                # 当前片段已满，保存
                if current_seg:
                    segments.append(''.join(current_seg))
                # 开始新片段
                current_seg = [sent]
                current_dur = dur

            # 如果当前片段时长已经达到或超过最小时长，且下一个句子加上后可能超限，也可以立即保存（但上面已处理）
            # 这里额外处理：如果当前片段已满足最小时长，且下一个句子加入后会超过最大时长，则提前保存
            if current_dur >= MIN_DURATION:
                # 检查下一个句子（如果存在）加入后是否会超过 MAX_DURATION
                if i + 1 < len(durations) and current_dur + durations[i+1] > MAX_DURATION:
                    segments.append(''.join(current_seg))
                    current_seg = []
                    current_dur = 0.0

        # 处理最后的片段
        if current_seg:
            segments.append(''.join(current_seg))

        # 4. 后处理：合并时长不足最小值的片段（将过短片段并入前一个或后一个）
        merged = []
        for seg in segments:
            dur = len(seg) / WORDS_PER_SECOND
            if not merged:
                merged.append(seg)
                continue
            # 如果当前片段太短，且合并后不超过最大时长，则合并到上一个片段
            if dur < MIN_DURATION:
                prev_dur = len(merged[-1]) / WORDS_PER_SECOND
                if prev_dur + dur <= MAX_DURATION:
                    merged[-1] += seg
                else:
                    merged.append(seg)
            else:
                merged.append(seg)
        # 最终确保所有片段时长不低于 MIN_DURATION（如果仍然有低于的，直接保留）
        return merged

    def _generate_shot_attributes(self, para_text, scripts):
        """
        第二次 AI 调用：为每个镜头生成属性（标题、时长、情绪、地域、视觉描述）。
        传入整个段落原文作为上下文。
        返回镜头列表，每个镜头包含 script（口播稿）和其他属性。
        """
        # 读取人设卡
        preset_name = config_manager.PRESET_CIVIL
        preset_text = ""
        if preset_name:
            preset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompt_presets", preset_name + ".txt")
            if os.path.exists(preset_path):
                with open(preset_path, 'r', encoding='utf-8') as f:
                    preset_text = f.read().strip()
                print(f"已加载人设卡预设: {preset_name}")

        # 构建 prompt 模板
        base_prompt = f"""
你是一位精通历史、建筑、服饰的视觉导演。请根据以下演讲稿完成两项任务：

第一项：风格识别
- 阅读全文，检查文稿开头或全文是否明确提到整体风格（如“纪录片”、“电影”、“动画”、“专题片”等关键词）。如果存在明确风格声明，则必须严格遵循该风格。
- 如果文稿中没有提到任何风格关键词，则由你根据文章的内容、语气、主题，推断最适合的整体视觉风格（可以是纪录片、专题报道、科教片、历史片、新闻纪实等）。
- 在生成每个镜头的视觉描述时，必须严格遵循最终确定的风格。

第二项：为以下每个镜头生成属性。
- 对于每个镜头，你将获得该镜头的口播稿原文片段。请结合全文的语境，为每个镜头生成标题、时长（秒）、情绪基调、地域、视觉描述。
- 输出格式：每个镜头单独输出，不要包含任何分隔符，直接输出以下字段：
   【镜头{{序号}}：{{标题}}】
   - 时长：{{duration}}秒
   - 情绪基调：{{emotion}}
   - 地域：{{region}}（根据当前镜头口播稿原文内容，推断出文中出现的所有地理位置（国家/地区）及其对应的时代背景（如“中国·宋朝”、“美国·当代”）。请严格按口播稿中地域出现的先后顺序输出，多个地域之间用顿号“、”连接。例如，如果口播稿先提到德国后提到中国，则输出“德国·当代、中国·当代”。若全文未提及任何明确地域，则输出“全球·无明确时代”。）
   - 视觉描述：{{visual}}（一段描述，用于 AI 生成画面。该描述必须只包含核心意象、风格、情绪、时代背景，不得包含任何镜头运动、焦距、快门等技术细节。如果地域字段中包含多个地域，请在视觉描述中自然地融合这些地域的视觉元素。格式自由，但需清晰明确。注意：视觉描述中禁止使用双引号（"），请用逗号或中文标点代替。）
- 注意：不要输出口播稿字段，因为口播稿已在代码中处理。

**人设卡附加规则**（文明结构适用）：
{preset_text}

全文演讲稿：
{para_text}

请为以下镜头分别生成属性：
"""
        # 为每个镜头单独构建 prompt，并并发调用
        def process_shot(shot_data):
            idx, script = shot_data
            prompt = base_prompt + f"\n镜头 {idx} 的口播稿原文：\n{script}\n\n请输出该镜头的属性块："
            result = self.call_deepseek(prompt, temperature=0.4, max_tokens=800)
            block = result.strip()
            # 提取标题
            header_match = re.search(r'【镜头\d+[：:]([^】]+)】', block)
            if not header_match:
                print(f"警告：镜头 {idx} 解析失败，跳过")
                return None
            title = header_match.group(1).strip()
            # 提取时长
            dur_match = re.search(r'时长[：:]\s*([\d.]+)', block)
            duration = float(dur_match.group(1)) if dur_match else 10.0
            # 提取情绪
            emo_match = re.search(r'情绪基调[：:]\s*([^\n]+)', block)
            emotion = emo_match.group(1).strip() if emo_match else ""
            # 提取地域
            reg_match = re.search(r'地域[：:]\s*([^\n]+)', block)
            region = reg_match.group(1).strip() if reg_match else "全球"
            # 提取视觉描述
            vis_match = re.search(r'视觉描述[：:]\s*(.*?)(?=\n\s*\[?镜头|\Z)', block, re.DOTALL)
            visual = vis_match.group(1).strip() if vis_match else ""
            return {
                "script": script,
                "title": title,
                "duration": duration,
                "emotion": emotion,
                "region": region,
                "visual": visual
            }

        # 准备任务列表
        tasks = [(i+1, script) for i, script in enumerate(scripts)]
        # 并发执行
        results, errors = concurrent_process(
            tasks,
            lambda task, _: process_shot(task),
            max_workers=settings.MAX_WORKERS,
            ordered=True
        )
        # 收集有效结果
        shots = []
        for i, res in enumerate(results):
            if res is not None:
                shots.append(res)
            else:
                print(f"警告：段落中第 {i+1} 个镜头生成失败，跳过")
        return shots