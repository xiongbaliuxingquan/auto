# parsers/free_parser.py
"""
自由解析器：不加载人设卡，完全根据故事内容生成镜头，并自动识别整体风格。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from .base_batch_parser import BatchParser

# 语速设置：字/秒
WORDS_PER_SECOND = 4.5

class FreeParser(BatchParser):
    def parse(self, raw_text):
        # 调用AI识别整体风格
        style = self._identify_style(raw_text)

        default_global = {
            "style": style,
            "seed": 12345
        }

        print("正在自由解析文稿，生成视觉描述...")
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
                    "visual": item.get("visual", ""),
                    "duration": item.get("duration", 10),
                    "emotion": item.get("emotion", "")
                }])
            })

        output_data = {
            "project": self.story_title or "自由创作",
            "global": default_global,
            "persona": {},
            "scene": {},
            "segments": segments
        }
        return output_data

    def _identify_style(self, text):
        """让AI分析文稿的整体视觉风格"""
        prompt = f"""
请根据以下故事内容，分析并概括它的整体视觉风格。风格描述应简短、精炼，例如“电影感、写实、自然光影”、“水墨动画、留白、意境”、“赛博朋克、霓虹、未来都市”等。直接输出风格描述，不要任何额外内容。

故事内容：
{text}
"""
        try:
            style = self.call_deepseek(prompt, temperature=0.3, max_tokens=100)
            return style.strip()
        except Exception as e:
            print(f"风格识别失败，使用默认风格: {e}")
            return "电影感、写实、自然光影"

    def _build_batch_prompt(self, batch_text, batch_index):
        """构建自由模式的批量 prompt，包含地域要求"""
        prompt = f"""
你是一位视觉导演。请根据以下故事内容，将其拆分成多个独立的视频镜头。
每个镜头时长控制在 5 到 15 秒之间。对于每个镜头，输出以下内容，每个镜头之间用 `===========================` 分隔：

【镜头{{段落ID}}-{{镜头序号}}：{{标题}}】
- 时长：{{duration}}秒
- 情绪基调：{{emotion}}
- 地域：{{region}} （根据当前镜头内容，推断最可能的地理位置（国家/地区）及对应的时代背景（如“中国·宋朝”、“美国·当代”）。优先基于本段内容判断；若本段内容缺乏明确时空线索，则参考之前已经出现过的地域（即上文）。输出格式为“国家/地区·时代”，例如“中国·宋朝”或“美国·当代”。若无法推断任何地域，则输出“全球·无明确时代”。）
- 视觉描述：{{visual}} （一段描述，用于 AI 生成画面。描述应包含场景、主体、动作、光影、色调、时代背景等，但不得包含镜头运动、焦距、快门等技术细节。格式自由，需清晰明确。）

注意：
- 段落ID从当前批的第一段开始递增。
- 每个段落内镜头序号从1开始递增。
- 不要输出任何其他内容，只输出这些镜头描述。

故事内容：
{batch_text}
"""
        return prompt