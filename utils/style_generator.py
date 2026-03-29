"""
style_generator.py
功能：根据故事内容，一键生成风格人设卡描述。
"""
from .ai_utils import call_deepseek

def generate_style_from_story(story_text):
    """
    根据故事内容生成风格人设卡描述。
    返回生成的文本（字符串）。
    """
    prompt = f"""
请根据以下故事内容，推荐一个适合生成口播稿的“风格人设卡”。
要求：输出简短、精炼的风格描述，可直接用于AI生成口播稿。
例如：“用董宇辉的风格，娓娓道来，带点知识分子的真诚”
或“幽默风趣，像和朋友聊天一样”
或“官方新闻播报，严肃正式”

故事：{story_text}

请只输出风格描述，不要包含任何额外内容。
"""
    result = call_deepseek(prompt, temperature=0.5, max_tokens=200)
    return result.strip()