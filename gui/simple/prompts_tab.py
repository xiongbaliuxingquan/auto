# gui/simple/prompts_tab.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

class PromptsTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        
        self.canvas = tk.Canvas(self.frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.frame, orient='vertical', command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # 滚轮事件处理函数
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            return "break"  # 阻止事件继续传播
        
        # 绑定 canvas 本身
        self.canvas.bind("<MouseWheel>", _on_mousewheel)
        self.canvas.bind("<Button-4>", _on_mousewheel)
        self.canvas.bind("<Button-5>", _on_mousewheel)
        
        # 递归绑定所有子控件，确保滚轮在任何位置都能滚动 canvas
        def bind_recursive(widget):
            try:
                widget.bind("<MouseWheel>", _on_mousewheel)
                widget.bind("<Button-4>", _on_mousewheel)
                widget.bind("<Button-5>", _on_mousewheel)
            except:
                pass
            for child in widget.winfo_children():
                bind_recursive(child)
        
        bind_recursive(self.scrollable_frame)
        
        self.prompts_data = []

    def _on_canvas_configure(self, event):
        """当画布大小改变时，调整内部框架宽度"""
        self.canvas.itemconfig(self.canvas_window_id, width=event.width)
        
    def _on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        
    def display_prompts(self, prompts_list):
        """prompts_list 格式: [(shot_id, prompt), ...]"""
        # 清空原有内容
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.prompts_data.clear()
        
        for shot_id, prompt in prompts_list:
            self._add_prompt_row(shot_id, prompt)
    
    def _add_prompt_row(self, shot_id, prompt):
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(fill='x', expand=True, pady=8, padx=5)
        
        # 镜头标题
        title_label = ttk.Label(frame, text=f"【镜头{shot_id}】", font=('微软雅黑', 10, 'bold'))
        title_label.pack(anchor='w')
        
        # 提示词内容（使用 Label 自动换行，只读）
        prompt_label = ttk.Label(frame, text=prompt, wraplength=700, justify='left', font=('微软雅黑', 9))
        prompt_label.pack(fill='x', padx=5, pady=2)
        
        # 编辑按钮
        edit_btn = ttk.Button(frame, text="编辑", command=lambda sid=shot_id: self._edit_prompt(sid))
        edit_btn.pack(anchor='e', padx=5, pady=2)
        
        self.prompts_data.append({
            'shot_id': shot_id,
            'prompt': prompt,
            'frame': frame,
            'prompt_label': prompt_label
        })
    
    def _edit_prompt(self, shot_id):
        # 从 prompts_data 中查找当前提示词
        current_prompt = None
        for item in self.prompts_data:
            if item['shot_id'] == shot_id:
                current_prompt = item['prompt']
                break
        if current_prompt is None:
            messagebox.showerror("错误", f"未找到镜头 {shot_id} 的提示词数据")
            return
        
        win = tk.Toplevel(self.frame)
        win.title(f"编辑镜头 {shot_id} 的提示词")
        win.geometry("800x600")
        win.minsize(600, 400)
        win.resizable(True, True)
        win.transient(self.frame)
        win.grab_set()
        
        # 居中显示
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (win.winfo_width() // 2)
        y = (win.winfo_screenheight() // 2) - (win.winfo_height() // 2)
        win.geometry(f"+{x}+{y}")
        
        ttk.Label(win, text="提示词：", font=('微软雅黑', 10)).pack(anchor='w', padx=10, pady=5)
        text_edit = scrolledtext.ScrolledText(win, wrap='word', font=('Consolas', 9))
        text_edit.insert('1.0', current_prompt)
        text_edit.pack(fill='both', expand=True, padx=10, pady=5)
        
        def save():
            new_prompt = text_edit.get('1.0', 'end-1c').strip()
            if not new_prompt:
                messagebox.showwarning("提示", "提示词不能为空")
                return
            # 调用控制器的方法保存（写回易读版文件）
            if self.controller and hasattr(self.controller, 'save_prompt_edit'):
                self.controller.save_prompt_edit(shot_id, new_prompt)
            else:
                # 降级：仅更新界面
                self._update_prompt_in_ui(shot_id, new_prompt)
            win.destroy()
            messagebox.showinfo("成功", f"镜头 {shot_id} 提示词已更新\n请在视频面板重试该镜头")
        
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="保存", command=save).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side='left', padx=5)
    
    def _update_prompt_in_ui(self, shot_id, new_prompt):
        for item in self.prompts_data:
            if item['shot_id'] == shot_id:
                item['prompt_label'].config(text=new_prompt)
                item['prompt'] = new_prompt
                break