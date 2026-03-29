import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os

from utils import config_manager
from core import txt_to_json

class ShotEditorWindow:
    def __init__(self, parent, shots_info, existing_selections=None, existing_edits=None):
        self.parent = parent
        self.shots_info = shots_info
        self.existing_selections = existing_selections if existing_selections is not None else [True] * len(shots_info)
        self.edits = existing_edits if existing_edits is not None else {}
        self.result_selections = None
        self.result_edits = None
        self.ai_processing = False
        self.selected_indices = set()  # 当前选中的索引集合
        self.row_frames = []            # 保存每行的 frame 引用，用于更新样式

        # 创建窗口
        self.win = tk.Toplevel(parent)
        self.win.title("选择或编辑提示词")
        self.win.geometry("1500x1100")
        self.win.transient(parent)
        self.win.grab_set()

        # 主布局：Canvas + 内部Frame（实现滚动）
        # 创建一个顶部容器 Frame，用于放置 Canvas 和滚动条
        top_frame = tk.Frame(self.win)
        top_frame.pack(fill='both', expand=True)   # 顶部 Frame 填满剩余空间

        self.canvas = tk.Canvas(top_frame, highlightthickness=0)
        self.v_scrollbar = tk.Scrollbar(top_frame, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=self.v_scrollbar.set)

        self.canvas.pack(side='left', fill='both', expand=True)
        self.v_scrollbar.pack(side='right', fill='y')
                # 绑定鼠标滚轮事件
        def _on_mousewheel(event):
            """处理鼠标滚轮滚动"""
            # Windows 用 event.delta, Linux 用 event.num
            if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
                self.canvas.yview_scroll(1, "units")

        # 绑定到 Canvas 及其子控件（确保滚轮在内部也能触发）
        self.canvas.bind("<MouseWheel>", _on_mousewheel)       # Windows
        self.canvas.bind("<Button-4>", _on_mousewheel)         # Linux 向上
        self.canvas.bind("<Button-5>", _on_mousewheel)         # Linux 向下
        # 同时绑定到内部 frame，防止焦点不在 canvas 时无法滚动
        self.scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
        self.scrollable_frame.bind("<Button-4>", _on_mousewheel)
        self.scrollable_frame.bind("<Button-5>", _on_mousewheel)

        # 表头（三列）
        header_frame = tk.Frame(self.scrollable_frame, bg='lightgray', height=30)
        header_frame.pack(fill='x', pady=(0, 2))
        header_frame.pack_propagate(False)

        # 列宽分配：镜号+标题 300px，提示词 900px，操作 100px（剩余弹性）
        tk.Label(header_frame, text="镜号 + 标题", bg='lightgray', font=('微软雅黑', 10, 'bold')).place(x=5, y=5, width=300)
        tk.Label(header_frame, text="提示词", bg='lightgray', font=('微软雅黑', 10, 'bold')).place(x=310, y=5, width=900)
        tk.Label(header_frame, text="操作", bg='lightgray', font=('微软雅黑', 10, 'bold')).place(x=1220, y=5, width=100)

        # 填充数据行
        self.populate_rows()

        # 底部按钮栏（强制放在窗口底部）
        btn_frame = tk.Frame(self.win)
        btn_frame.pack(side='bottom', fill='x', padx=5, pady=5)   # side='bottom' 确保在底部

        ttk.Button(btn_frame, text="全选", command=self.select_all, width=8).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="全不选", command=self.select_none, width=8).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="AI重写选中", command=self.ai_rewrite_selected, width=12).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="确定", command=self.on_ok, width=8).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="取消", command=self.on_cancel, width=8).pack(side='left', padx=2)
         
        # 初始化选中状态
        self.init_selection()

        self.win.protocol("WM_DELETE_WINDOW", self.on_cancel)

    def _on_mousewheel(self, event):
        """处理鼠标滚轮滚动，使Canvas滚动"""
        # Windows 用 event.delta, Linux 用 event.num
        if event.num == 4 or (hasattr(event, 'delta') and event.delta > 0):
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            self.canvas.yview_scroll(1, "units")

    def populate_rows(self):
        for idx, shot in enumerate(self.shots_info):
            row_frame = tk.Frame(self.scrollable_frame, bg='white', height=100)
            row_frame.pack(fill='x', pady=1)
            row_frame.pack_propagate(False)  # 固定高度

            # 绑定点击事件
            row_frame.bind('<Button-1>', lambda e, i=idx: self.toggle_selection(i))

            # A列：镜号+标题
            id_title = f"【{shot['id']}】 {shot['title']}"
            label_a = tk.Label(row_frame, text=id_title, bg='white', anchor='nw', justify='left', wraplength=280)
            label_a.grid(row=0, column=0, padx=(5,2), pady=2, sticky='nsew')
            label_a.bind('<Button-1>', lambda e, i=idx: self.toggle_selection(i))
            # 绑定鼠标滚轮
            label_a.bind("<MouseWheel>", self._on_mousewheel)
            label_a.bind("<Button-4>", self._on_mousewheel)
            label_a.bind("<Button-5>", self._on_mousewheel)

            # B列：提示词（只读Text）
            prompt_text = self.edits.get(shot['id'], shot['prompt'])
            text_b = tk.Text(row_frame, wrap='word', bg='white', borderwidth=0, highlightthickness=0,
                             font=('微软雅黑', 9), height=4)
            text_b.insert('1.0', prompt_text)
            text_b.config(state='disabled')
            text_b.grid(row=0, column=1, padx=2, pady=2, sticky='nsew')
            text_b.bind('<Button-1>', lambda e, i=idx: self.toggle_selection(i))
            # 绑定鼠标滚轮
            text_b.bind("<MouseWheel>", self._on_mousewheel)
            text_b.bind("<Button-4>", self._on_mousewheel)
            text_b.bind("<Button-5>", self._on_mousewheel)

            # C列：编辑按钮
            btn_c = tk.Button(row_frame, text="编辑", command=lambda i=idx: self.edit_shot(i))
            btn_c.grid(row=0, column=2, padx=5, pady=30, sticky='n')
            btn_c.bind('<Button-1>', lambda e, i=idx: self.toggle_selection(i))
            # 绑定鼠标滚轮
            btn_c.bind("<MouseWheel>", self._on_mousewheel)
            btn_c.bind("<Button-4>", self._on_mousewheel)
            btn_c.bind("<Button-5>", self._on_mousewheel)
            
            # 列权重分配
            row_frame.columnconfigure(0, weight=1, minsize=300)
            row_frame.columnconfigure(1, weight=4, minsize=900)
            row_frame.columnconfigure(2, weight=0, minsize=100)

            self.row_frames.append(row_frame)

        # 强制更新画布滚动区域
        self.scrollable_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def toggle_selection(self, idx):
        """切换指定行的选中状态，并更新背景色"""
        if idx in self.selected_indices:
            self.selected_indices.remove(idx)
            self.row_frames[idx].configure(bg='white')
            # 同时修改内部所有子控件的背景色（Label和Text）
            for child in self.row_frames[idx].winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg='white')
                elif isinstance(child, tk.Text):
                    child.configure(bg='white', fg='black')
                # 按钮不改变背景
        else:
            self.selected_indices.add(idx)
            self.row_frames[idx].configure(bg='lightblue')
            for child in self.row_frames[idx].winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(bg='lightblue')
                elif isinstance(child, tk.Text):
                    child.configure(bg='lightblue', fg='black')
                # 按钮保持原样

    def init_selection(self):
        """根据 existing_selections 初始化选中行"""
        for idx, selected in enumerate(self.existing_selections):
            if selected:
                self.toggle_selection(idx)

    def select_all(self):
        """全选"""
        for idx in range(len(self.shots_info)):
            if idx not in self.selected_indices:
                self.toggle_selection(idx)

    def select_none(self):
        """全不选"""
        # 复制一份，因为遍历时不能修改集合
        for idx in list(self.selected_indices):
            self.toggle_selection(idx)

    def edit_shot(self, idx):
        """编辑指定索引的镜头"""
        shot = self.shots_info[idx]
        current_prompt = self.edits.get(shot['id'], shot['prompt'])

        edit_win = tk.Toplevel(self.win)
        edit_win.title(f"编辑镜头 {shot['id']}")
        edit_win.geometry("600x400")
        edit_win.transient(self.win)
        edit_win.grab_set()

        tk.Label(edit_win, text="提示词：").pack(anchor='w', padx=5, pady=5)
        text_widget = scrolledtext.ScrolledText(edit_win, wrap='word', height=15)
        text_widget.pack(fill='both', expand=True, padx=5, pady=5)
        text_widget.insert('1.0', current_prompt)

        def save_edit():
            new_prompt = text_widget.get('1.0', 'end-1c').strip()
            if new_prompt:
                self.edits[shot['id']] = new_prompt
                # 更新该行的提示词显示
                for child in self.row_frames[idx].winfo_children():
                    if isinstance(child, tk.Text):
                        child.config(state='normal')
                        child.delete('1.0', 'end')
                        child.insert('1.0', new_prompt)
                        child.config(state='disabled')
                        break
            edit_win.destroy()

        tk.Button(edit_win, text="保存", command=save_edit, width=10).pack(pady=5)

    def ai_rewrite_selected(self):
        """对选中的镜头执行 AI 重写"""
        if not self.selected_indices:
            messagebox.showwarning("警告", "请至少选中一个镜头")
            return

        req_win = tk.Toplevel(self.win)
        req_win.title("AI 重写要求")
        req_win.geometry("400x200")
        req_win.transient(self.win)
        req_win.grab_set()

        tk.Label(req_win, text="请输入对提示词的修改要求：").pack(pady=5)
        entry = tk.Text(req_win, height=5)
        entry.pack(fill='both', expand=True, padx=5, pady=5)

        def start_rewrite():
            requirement = entry.get('1.0', 'end-1c').strip()
            if not requirement:
                messagebox.showwarning("警告", "请输入修改要求")
                return
            req_win.destroy()
            self._do_ai_rewrite(list(self.selected_indices), requirement)

        tk.Button(req_win, text="开始重写", command=start_rewrite, width=12).pack(pady=5)

    def _do_ai_rewrite(self, indices, requirement):
        if self.ai_processing:
            return
        self.ai_processing = True

        selected_shots = [self.shots_info[i] for i in indices]
        total = len(selected_shots)

        progress_win = tk.Toplevel(self.win)
        progress_win.title("AI 重写中")
        progress_win.geometry("300x100")
        tk.Label(progress_win, text="正在重写，请稍候...").pack(pady=10)
        progress_bar = ttk.Progressbar(progress_win, mode='indeterminate')
        progress_bar.pack(pady=5, padx=10, fill='x')
        progress_bar.start()

        def worker():
            api_key = os.environ.get('DEEPSEEK_API_KEY')
            if not api_key:
                api_key, _ = config_manager.load_config()
                if api_key:
                    os.environ['DEEPSEEK_API_KEY'] = api_key
                else:
                    self.win.after(0, lambda: messagebox.showerror("错误", "API Key 未配置，请在总控台中保存配置"))
                    progress_win.destroy()
                    self.ai_processing = False
                    return

            prompt_template = """
你是一个专业的提示词优化助手。请根据以下原始提示词和修改要求，生成一个新的提示词。
要求：保留原始提示词的核心意象和人物特征，但按照用户要求进行调整。
直接输出新的提示词，不要有任何额外解释。

原始提示词：
{original}

修改要求：
{requirement}
"""
            success = 0
            for shot in selected_shots:
                shot_id = shot['id']
                original = shot['prompt']
                prompt = prompt_template.format(original=original, requirement=requirement)
                try:
                    new_prompt = txt_to_json.call_deepseek(prompt, temperature=0.7, max_tokens=800)
                    self.edits[shot_id] = new_prompt
                    # 更新对应行的提示词显示
                    idx = self.shots_info.index(shot)
                    for child in self.row_frames[idx].winfo_children():
                        if isinstance(child, tk.Text):
                            child.config(state='normal')
                            child.delete('1.0', 'end')
                            child.insert('1.0', new_prompt)
                            child.config(state='disabled')
                            break
                    success += 1
                except Exception as e:
                    print(f"AI 重写镜头 {shot_id} 失败: {e}")
            progress_win.after(0, progress_win.destroy)
            self.win.after(0, lambda: self._ai_rewrite_done(success, total))
            self.ai_processing = False

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()

    def _ai_rewrite_done(self, success, total):
        messagebox.showinfo("完成", f"AI 重写完成，成功 {success}/{total} 个镜头")

    def on_ok(self):
        """确定：保存选择结果和编辑结果"""
        self.result_selections = [i in self.selected_indices for i in range(len(self.shots_info))]
        self.result_edits = self.edits.copy()
        self.win.destroy()

    def on_cancel(self):
        self.result_selections = None
        self.result_edits = None
        self.win.destroy()