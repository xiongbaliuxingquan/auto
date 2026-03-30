# gui/simple/data.py
class SimpleModeData:
    def __init__(self):
        self.story_text = ""          # 原始故事文本
        self.style_preset = ""        # 风格人设卡（可选）
        self.script_data = None       # 剧本数据（结构化，后续可改为dict或列表）
        self.assets = {
            "persona": "",            # 人物设定文本
            "scene": "",              # 场景设定文本
            "style": ""               # 视觉风格文本
        }
        self.prompts = []             # 提示词列表（每个镜头一个字符串）