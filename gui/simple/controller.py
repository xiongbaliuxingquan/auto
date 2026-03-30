# gui/simple/controller.py
import threading
import tkinter as tk
from tkinter import messagebox

class SimpleModeController:
    def __init__(self, ui, data, app):
        self.ui = ui          # SimpleMode 实例（提供UI更新方法）
        self.data = data      # SimpleModeData 实例
        self.app = app        # 主应用实例（用于日志等）

    def open_wizard(self):
        """打开高级向导（弹出窗口）"""
        from gui.story_wizard import StoryWizard
        def on_finish(script):
            # 将生成的脚本设置到故事文本
            self.data.story_text = script
            self.ui.story_tab.text_widget.delete('1.0', 'end')
            self.ui.story_tab.text_widget.insert('1.0', script)
            self.ui.story_tab.update_word_count()
            # 可选：自动生成剧本？
            # self.generate_script()
        StoryWizard(self.app.root, self.app, on_finish)

    def on_story_changed(self, content):
        self.data.story_text = content

    def on_style_changed(self, content):
        self.data.style_preset = content

    def generate_script(self):
        """步骤1：生成剧本"""
        if not self.data.story_text.strip():
            messagebox.showwarning("提示", "请先输入故事内容")
            return
        
        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="生成中...")
        self.app.log("正在生成剧本，请稍候...")
        
        def task():
            try:
                # 调用剧本生成函数（临时使用 story_to_script，后续替换）
                from utils.story_to_script import generate_script
                script = generate_script(self.data.story_text, self.data.style_preset)
                # 更新数据
                self.data.script_data = script
                # 更新UI
                self.app.root.after(0, self._on_script_generated, script)
            except Exception as e:
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"生成剧本失败：{e}"))
                self.app.root.after(0, self._reset_buttons)
        threading.Thread(target=task, daemon=True).start()
    
    def _on_script_generated(self, script):
        """剧本生成完成后的UI更新"""
        # 显示到剧本标签页
        self.ui.script_tab.display_script(script)
        # 启用下一步按钮
        self.ui.set_button_state('normal', 'normal', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="1. 生成剧本")
        self.app.log("剧本生成完成")
        # 自动切换到剧本标签页
        self.ui.notebook.select(self.ui.script_tab.frame)
    
    def extract_assets(self):
        """步骤2：提取资产库"""
        if not self.data.story_text.strip():
            messagebox.showwarning("提示", "请先输入故事内容")
            return
        
        self.ui.set_button_state('disabled', 'disabled', 'disabled', 'disabled')
        self.ui.extract_assets_btn.config(text="提取中...")
        self.app.log("正在提取资产库（人物、场景、风格），请稍候...")
        
        def task():
            try:
                from utils.extract_persona_scene import extract_from_story
                extracted = extract_from_story(self.data.story_text)
                # 解析提取的文本，分离人物、场景、风格（简单处理，全部放入人物设定）
                # 后续可优化
                self.data.assets["persona"] = extracted
                self.data.assets["scene"] = ""  # 暂时留空
                self.data.assets["style"] = self.data.style_preset or "电影感、写实、自然光影"
                self.app.root.after(0, self._on_assets_extracted)
            except Exception as e:
                self.app.root.after(0, lambda: messagebox.showerror("错误", f"提取资产失败：{e}"))
                self.app.root.after(0, self._reset_buttons)
        threading.Thread(target=task, daemon=True).start()
    
    def _on_assets_extracted(self):
        """资产提取完成后的UI更新"""
        # 更新资产库标签页显示
        self.ui.assets_tab.display_assets(self.data.assets)
        self.ui.set_button_state('normal', 'normal', 'normal', 'disabled')
        self.ui.extract_assets_btn.config(text="2. 提取资产")
        self.app.log("资产提取完成")
        # 切换到资产库标签页
        self.ui.notebook.select(self.ui.assets_tab.frame)
    
    def generate_prompts(self):
        """步骤3：生成提示词"""
        # 待实现
        messagebox.showinfo("提示", "此功能待实现")
        # 暂时启用确认按钮
        # self.ui.set_button_state('normal', 'normal', 'normal', 'normal')
    
    def confirm_and_generate(self):
        """步骤4：确认并生成视频"""
        # 待实现
        messagebox.showinfo("提示", "此功能待实现")
    
    def _reset_buttons(self):
        """重置按钮状态"""
        self.ui.set_button_state('normal', 'disabled', 'disabled', 'disabled')
        self.ui.gen_script_btn.config(text="1. 生成剧本")
        self.ui.extract_assets_btn.config(text="2. 提取资产")
        self.ui.gen_prompts_btn.config(text="3. 生成提示词")
        self.ui.confirm_btn.config(text="✅ 确认并生成视频")
    
    def open_style_preset(self):
        """打开人设卡管理窗口"""
        from gui.preset_manager import PresetManagerWindow
        current_mode = self.app.toolbar.text_type_var.get()
        win = PresetManagerWindow(self.app.root, current_mode)
        self.app.root.wait_window(win.win)
        if hasattr(win, 'result') and win.result:
            # 刷新人设卡显示
            self.app._update_preset_label()
    
    def generate_style(self, story, style_text_widget):
        """根据故事一键生成风格描述"""
        if not story:
            messagebox.showwarning("提示", "请先输入故事内容")
            return
        try:
            from utils.style_generator import generate_style_from_story
            style = generate_style_from_story(story)
            style_text_widget.delete('1.0', 'end')
            style_text_widget.insert('1.0', style)
            style_text_widget.update_word_count()
        except Exception as e:
            messagebox.showerror("错误", f"生成风格失败：{e}")

    def on_assets_changed(self, key, value):
        self.data.assets[key] = value
        # 可选：自动保存或做其他处理    
    def save_style_preset(self, style):
        """保存风格人设卡"""
        if not style:
            messagebox.showwarning("提示", "风格人设卡为空，无需保存")
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("保存预设", "请输入预设名称：", parent=self.app.root)
        if not name:
            return
        try:
            from utils.config_manager import save_style_preset as save_preset
            save_preset(name, style)
            messagebox.showinfo("成功", f"预设“{name}”已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")