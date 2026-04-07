import sys
import tkinter as tk
sys.path.insert(0, '.')

try:
    from gui.story_wizard import StoryWizardNew
except Exception as e:
    print("导入错误:", e)
    sys.exit(1)

def on_finish(script, metadata):
    print("用户选择：", metadata)
    print("故事内容：", script[:100])

root = tk.Tk()
root.title("测试根窗口")  # 不隐藏，观察根窗口是否出现
# root.withdraw()   # 注释掉隐藏

try:
    wizard = StoryWizardNew(root, None, on_finish)
    root.mainloop()
except Exception as e:
    print("运行错误:", e)
    import traceback
    traceback.print_exc()