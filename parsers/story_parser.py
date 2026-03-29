# parsers/story_parser.py
"""
情感故事解析器：继承 BatchParser，实现特定的 prompt 构建逻辑。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from .base_batch_parser import BatchParser
from utils import config_manager

WORDS_PER_SECOND = 4.5

class StoryParser(BatchParser):
    def parse(self, raw_text):
        default_global = {
            "style": "电影感、写实、自然光影",
            "seed": 12345
        }

        print("正在分析情感故事文稿、识别风格并生成视觉描述...")
        segments_data = self._generate_segments(raw_text)
        print(f"文稿已分割为 {len(segments_data)} 个逻辑镜头")

        # 根据每个段落的字数重新计算时长
        for item in segments_data:
            content = item.get("content", "")
            raw_duration = max(5, min(20, int(len(content) / WORDS_PER_SECOND)))
            item["duration"] = raw_duration

        segments = []
        for i, item in enumerate(segments_data, start=1):
            segments.append({
                "id": i,
                "title": item["title"],
                "content": item["content"],
                "shots": item.get("shots", [{
                    "visual": item.get("visual", "中景 + 自然景观 + 黄昏暖光 + 理性 + 固定镜头 + 无文字"),
                    "duration": item.get("duration", 10),
                    "emotion": item.get("emotion", "")
                }])
            })

        output_data = {
            "project": self.story_title or "情感故事",
            "global": default_global,
            "persona": {},
            "scene": {},
            "segments": segments
        }
        return output_data

    def _build_batch_prompt(self, batch_text, batch_index):
        """构建情感故事模式的批量 prompt"""
        # 读取人设卡预设
        preset_name = config_manager.PRESET_EMOTIONAL
        preset_text = ""
        if preset_name:
            import os
            preset_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompt_presets", preset_name + ".txt")
            if os.path.exists(preset_path):
                with open(preset_path, 'r', encoding='utf-8') as f:
                    preset_text = f.read().strip()
                print(f"已加载人设卡预设: {preset_name}")
            else:
                print(f"人设卡预设文件不存在: {preset_path}")

        # 构建 prompt（注意：输出格式中包含地域字段）
        prompt = f"""
你是一位擅长情感故事、人物刻画的视觉导演。请根据以下演讲稿完成两项任务：

第一项：风格识别
- 阅读全文，检查文稿开头或全文是否明确提到整体风格（如“纪录片”、“电影”、“动画”、“专题片”等关键词）。如果存在明确风格声明，则必须严格遵循该风格。
- 如果文稿中没有提到任何风格关键词，则由你根据文章的内容、语气、主题，推断最适合的整体视觉风格（偏向情感细腻、人物真实、光影温暖的电影感）。
- 在生成每个镜头的视觉描述时，必须严格遵循最终确定的风格。

第二项：严格按照原文顺序划分逻辑段落并生成镜头列表
- 必须严格遵循演讲稿中文字出现的先后顺序划分段落，不得对原文内容进行重新排序、合并或拆分。
- 每个段落应围绕一个相对独立的主题或情感节点。
- 对于每个段落，你需要将其拆分成多个独立的镜头（每个镜头时长应控制在 5 到 15 秒之间）。镜头的划分应依据该段落内部的逻辑转折、情感变化或关键动作。
- 对于每个镜头，输出以下内容，每个镜头之间用 `===========================` 分隔：
   【镜头{{段落ID}}-{{镜头序号}}：{{标题}}】
   - 时长：{{duration}}秒
   - 情绪基调：{{emotion}}
   - 地域：{{region}} （根据当前镜头内容，推断最可能的地理位置（国家/地区）及对应的时代背景（如“中国·宋朝”、“美国·当代”）。优先基于本段内容判断；若本段内容缺乏明确时空线索，则参考之前已经出现过的地域（即上文）。输出格式为“国家/地区·时代”，例如“中国·宋朝”或“美国·当代”。若无法推断任何地域，则输出“全球·无明确时代”。）
   - 视觉描述：{{visual}} （一段描述，用于 AI 生成画面。该描述必须只包含核心意象、风格、情绪、时代背景，不得包含任何镜头运动、焦距、快门等技术细节。格式自由，但需清晰明确。）

   请严格使用上述格式，每个镜头之间必须用 `===========================` 隔开。

注意：
- 段落ID从当前批的第一段开始递增。
- 每个段落内镜头序号从1开始递增。
- 不要输出任何其他内容，只输出这些镜头描述。
- 每个镜头的内容必须严格按照上述格式。

**人设卡附加规则**（情感故事适用）：
{preset_text}

演讲稿：
{batch_text}
"""
        return prompt