# gui/simple/data.py
class SimpleModeData:
    def __init__(self):
        self.story_text = ""          # 原始故事文本
        self.style_preset = ""        # 风格人设卡
        self.script_data = None       # 剧本数据（结构化）
        self.assets = {
            "persona": "",            # 人物设定文本
            "scene": "",              # 场景设定文本
            "style": ""               # 视觉风格文本
        }
        self.prompts = []             # 提示词列表（每个镜头一个字符串）
        self.current_tab = 0          # 当前标签页索引
        self.metadata = {}            # 高级向导生成的元数据
        self.prompts = []