# gui/simple/assets_tab.py
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

class AssetsTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)

        # 获取工作目录（通过 controller 或 app）
        self.work_dir = None
        self.current_file = None  # 当前选中的文件路径
        self.file_listbox = None
        self.text_edit = None

        # 左右分栏
        self.paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.paned.pack(fill='both', expand=True, padx=5, pady=5)

        # 左侧：文件列表
        left_frame = ttk.Frame(self.paned, width=200)
        self.paned.add(left_frame, weight=1)
        ttk.Label(left_frame, text="资产文件", font=('微软雅黑', 10, 'bold')).pack(anchor='w', padx=5, pady=2)
        self.file_listbox = tk.Listbox(left_frame, height=20)
        self.file_listbox.pack(fill='both', expand=True, padx=5, pady=2)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_selected)

        # 右侧：编辑区域
        right_frame = ttk.Frame(self.paned)
        self.paned.add(right_frame, weight=3)
        self.text_edit = scrolledtext.ScrolledText(right_frame, wrap='word', font=('微软雅黑', 10))
        self.text_edit.pack(fill='both', expand=True, padx=5, pady=5)

        # 保存按钮
        btn_frame = tk.Frame(right_frame)
        btn_frame.pack(fill='x', padx=5, pady=5)
        self.save_btn = tk.Button(btn_frame, text="保存当前资产", command=self.save_current_asset, state='disabled')
        self.save_btn.pack(side='right', padx=5)

        # 刷新按钮
        self.refresh_btn = tk.Button(btn_frame, text="刷新列表", command=self.refresh_file_list)
        self.refresh_btn.pack(side='right', padx=5)

    def update_assets(self, assets=None):
        """刷新资产文件列表（assets参数已废弃）"""
        # 尝试获取 work_dir
        if hasattr(self.controller, 'ui') and hasattr(self.controller.ui, 'work_dir'):
            self.work_dir = self.controller.ui.work_dir
        elif hasattr(self.controller, 'app') and hasattr(self.controller.app, 'work_dir'):
            self.work_dir = self.controller.app.work_dir
        elif hasattr(self.controller, 'data') and hasattr(self.controller.data, 'work_dir'):
            self.work_dir = self.controller.data.work_dir
        self.refresh_file_list()

    def refresh_file_list(self):
        """刷新左侧文件列表"""
        if not self.work_dir or not os.path.isdir(self.work_dir):
            self.file_listbox.delete(0, tk.END)
            self.file_listbox.insert(tk.END, "未打开项目")
            self.text_edit.delete('1.0', 'end')
            self.text_edit.insert('1.0', "请先打开一个项目")
            self.save_btn.config(state='disabled')
            return

        self.file_listbox.delete(0, tk.END)
        # 列出所有资产文件
        files = []
        # 全局资产
        global_path = os.path.join(self.work_dir, "assets_global.txt")
        if os.path.exists(global_path):
            files.append(("全局资产库", global_path))
        # 段落局部资产
        para_files = []
        for f in os.listdir(self.work_dir):
            if f.startswith("assets_paragraph_") and f.endswith(".txt"):
                para_files.append(f)
        para_files.sort(key=lambda x: int(x.split('_')[2].split('.')[0]))
        for f in para_files:
            files.append((f.replace("assets_paragraph_", "段落 ").replace(".txt", ""), os.path.join(self.work_dir, f)))

        if not files:
            self.file_listbox.insert(tk.END, "无资产文件")
            self.text_edit.delete('1.0', 'end')
            self.text_edit.insert('1.0', "未找到资产文件，请先生成剧本")
            self.save_btn.config(state='disabled')
            return

        for name, path in files:
            self.file_listbox.insert(tk.END, name)
            # 存储路径到 listbox 的 item 中（使用字典映射）
            if not hasattr(self, '_file_map'):
                self._file_map = {}
            self._file_map[name] = path

    def on_file_selected(self, event):
        """当选中文件时，加载内容到右侧编辑器"""
        selection = self.file_listbox.curselection()
        if not selection:
            return
        name = self.file_listbox.get(selection[0])
        if name == "未打开项目" or name == "无资产文件":
            self.text_edit.delete('1.0', 'end')
            self.text_edit.insert('1.0', "请先打开一个项目" if name == "未打开项目" else "未找到资产文件，请先生成剧本")
            self.save_btn.config(state='disabled')
            return

        if hasattr(self, '_file_map') and name in self._file_map:
            filepath = self._file_map[name]
        else:
            # 兼容旧方式：直接构造路径（不推荐）
            if name == "全局资产库":
                filepath = os.path.join(self.work_dir, "assets_global.txt")
            elif name.startswith("段落 "):
                idx = name.split(" ")[1]
                filepath = os.path.join(self.work_dir, f"assets_paragraph_{idx}.txt")
            else:
                return

        if not os.path.exists(filepath):
            self.text_edit.delete('1.0', 'end')
            self.text_edit.insert('1.0', f"文件不存在：{filepath}")
            self.save_btn.config(state='disabled')
            return

        self.current_file = filepath
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            self.text_edit.delete('1.0', 'end')
            self.text_edit.insert('1.0', content)
            self.save_btn.config(state='normal')
        except Exception as e:
            messagebox.showerror("错误", f"读取文件失败：{e}")
            self.save_btn.config(state='disabled')

    def save_current_asset(self):
        """保存当前编辑的内容到文件"""
        if not self.current_file:
            messagebox.showwarning("提示", "未选中任何资产文件")
            return
        content = self.text_edit.get('1.0', 'end-1c')
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(content)
            messagebox.showinfo("成功", f"已保存：{os.path.basename(self.current_file)}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    # 保留原有的兼容方法（如果其他地方调用）
    def on_persona_changed(self, event=None):
        pass

    def on_scene_changed(self, event=None):
        pass

    def on_style_changed(self, event=None):
        pass