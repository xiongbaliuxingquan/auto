"""
story_to_script.py
功能：根据故事内容和风格人设卡生成口播稿。
"""
from .ai_utils import call_deepseek

def generate_script(story_text, style_preset=""):
    """
    生成口播稿。
    story_text: 用户输入的故事
    style_preset: 风格人设卡（可选）
    返回生成的文本（字符串）。
    """
    style_instruction = f"请使用以下风格：{style_preset}" if style_preset else ""
    prompt = f"""
请根据以下故事内容，生成一份完整、自然的口播稿。口播稿应当适合朗读，语言流畅，保留故事的核心情节和情感。
{style_instruction}

故事：
{story_text}

请只输出口播稿文本，不要包含任何额外内容。
"""
    result = call_deepseek(prompt, temperature=0.5, max_tokens=2000)
    return result.strip()