# parsers/base_parser.py
from abc import ABC, abstractmethod

class BaseParser(ABC):
    def __init__(self, call_deepseek, story_title=None, mode=None):
        self.call_deepseek = call_deepseek  # 保存传入的函数
        self.story_title = story_title
        self.mode = mode  # 新增：文稿类型（如"情感故事"、"文明结构"）

    @abstractmethod
    def parse(self, raw_text):
        pass