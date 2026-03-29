import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import glob
import shutil
from utils import config_manager

class PresetManagerWindow:
    def __init__(self, parent, current_mode):
        self.parent = parent
        self.current_mode = current_mode  # 当前选中的文稿类型，如"情感故事"
        self.result = False  # 用于标记是否修改了设置

        self.win = tk.Toplevel(parent)
        self.win.title("人设卡管理")
        self.win.geometry("700x500")
        self.win.transient(parent)
        self.win.grab_set()

        # 预设文件夹路径
        self.preset_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompt_presets")
        os.makedirs(self.preset_dir, exist_ok=True)

        # 加载现有预设列表
        self.preset_files = self._scan_presets()

        # 创建界面
        self.create_widgets()

        # 根据当前模式默认选中对应下拉框
        self._set_initial_selection()

    def _scan_presets(self):
        """扫描预设文件夹，返回文件名列表（不含扩展名）"""
        files = glob.glob(os.path.join(self.preset_dir, "*.txt"))
        return [os.path.splitext(os.path.basename(f))[0] for f in files]

    def create_widgets(self):
        # 说明标签
        tk.Label(self.win, text="为每种文稿类型选择对应的人设卡预设文件。预设文件存放在 prompt_presets 文件夹中。",
                 fg='gray', justify='left').pack(pady=5)

        # 创建三个设置行
        self.vars = {}
        rows = [
            ("情感故事", "PRESET_EMOTIONAL", tk.StringVar()),
            ("文明结构", "PRESET_CIVIL", tk.StringVar()),
            ("动画默剧", "PRESET_MIME", tk.StringVar())
        ]
        for i, (label, key, var) in enumerate(rows):
            frame = tk.Frame(self.win)
            frame.pack(fill='x', padx=10, pady=5)

            tk.Label(frame, text=label, width=10, anchor='w').pack(side='left')

            # 下拉框
            combo = ttk.Combobox(frame, textvariable=var, values=self.preset_files, state='readonly', width=25)
            combo.pack(side='left', padx=5)

            # 设置当前值
            current = getattr(config_manager, key, "")
            var.set(current if current in self.preset_files else "")

            self.vars[key] = (var, combo)

            # 按钮：编辑、新建、删除
            tk.Button(frame, text="编辑", command=lambda k=key: self.edit_preset(k)).pack(side='left', padx=2)
            tk.Button(frame, text="新建", command=lambda k=key: self.new_preset(k)).pack(side='left', padx=2)
            tk.Button(frame, text="删除", command=lambda k=key: self.delete_preset(k)).pack(side='left', padx=2)

        # 刷新按钮
        tk.Button(self.win, text="刷新列表", command=self.refresh_presets).pack(pady=5)

        # 底部按钮
        btn_frame = tk.Frame(self.win)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="保存", command=self.save_settings, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text="取消", command=self.win.destroy, width=10).pack(side='left', padx=5)

    def _set_initial_selection(self):
        """根据当前文稿类型，让对应的下拉框获得焦点（可选）"""
        mode_map = {
            "情感故事": "PRESET_EMOTIONAL",
            "文明结构": "PRESET_CIVIL",
            "动画默剧": "PRESET_MIME"
        }
        key = mode_map.get(self.current_mode)
        if key and key in self.vars:
            # 可以高亮该行，但简单起见，只是聚焦下拉框（可选）
            pass

    def edit_preset(self, key):
        """编辑当前选中的预设文件"""
        var, combo = self.vars[key]
        filename = var.get()
        if not filename:
            messagebox.showwarning("警告", "请先选择一个预设文件")
            return
        filepath = os.path.join(self.preset_dir, filename + ".txt")
        if not os.path.exists(filepath):
            messagebox.showerror("错误", "文件不存在")
            return

        # 打开编辑窗口
        self.open_editor(filepath)

    def new_preset(self, key):
        """新建预设文件"""
        # 弹出输入对话框，要求输入文件名
        from tkinter import simpledialog
        name = simpledialog.askstring("新建预设", "请输入预设名称（英文、数字、下划线）：",
                                       parent=self.win)
        if not name:
            return
        # 检查合法性（简单限制）
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', name):
            messagebox.showerror("错误", "名称只能包含英文字母、数字和下划线")
            return
        filepath = os.path.join(self.preset_dir, name + ".txt")
        if os.path.exists(filepath):
            messagebox.showerror("错误", "该名称已存在")
            return
        # 创建空白文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# 在此输入人设卡规则，一行一条\n")
        # 刷新列表
        self.refresh_presets()
        # 自动选中新建的文件
        var, combo = self.vars[key]
        var.set(name)

    def delete_preset(self, key):
        """删除选中的预设文件"""
        var, combo = self.vars[key]
        filename = var.get()
        if not filename:
            messagebox.showwarning("警告", "请先选择一个预设文件")
            return
        filepath = os.path.join(self.preset_dir, filename + ".txt")
        if not os.path.exists(filepath):
            messagebox.showerror("错误", "文件不存在")
            return
        if messagebox.askyesno("确认删除", f"确定要删除 {filename} 吗？"):
            os.remove(filepath)
            # 如果当前选中的就是被删除的，则清空选择
            if var.get() == filename:
                var.set("")
            self.refresh_presets()

    def refresh_presets(self):
        """刷新预设列表并更新下拉框"""
        self.preset_files = self._scan_presets()
        for key, (var, combo) in self.vars.items():
            current = var.get()
            combo['values'] = self.preset_files
            # 如果当前值不在新列表中，清空
            if current not in self.preset_files:
                var.set("")

    def open_editor(self, filepath):
        """打开文本编辑器（用默认记事本）"""
        import subprocess
        try:
            # Windows下用 start 命令打开
            subprocess.run(['start', '', filepath], shell=True, check=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法打开编辑器: {e}")

    def save_settings(self):
        """保存设置到 config_manager 并更新配置文件"""
        # 收集新值
        new_settings = {}
        for key, (var, combo) in self.vars.items():
            new_settings[key] = var.get()
        # 读取当前所有用户设置
        current = config_manager.load_user_settings()
        # 更新预设字段
        current.update(new_settings)
        # 保存
        config_manager.save_user_settings(current)
        # 重新加载 config_manager 中的变量（简单方式：重新导入模块）
        import importlib
        importlib.reload(config_manager)
        self.result = True
        messagebox.showinfo("成功", "人设卡设置已保存")
        self.win.destroy()