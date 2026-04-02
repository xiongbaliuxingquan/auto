# gui/simple/script_tab.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import os
import re

class ScriptTab:
    def __init__(self, parent, controller):
        self.controller = controller
        self.frame = tk.Frame(parent)
        self.work_dir = None
        self.current_shots_data = []  # 存储完整的镜头数据

        # 左右分栏
        self.paned = ttk.PanedWindow(self.frame, orient=tk.HORIZONTAL)
        self.paned.pack(fill='both', expand=True, padx=5, pady=5)

        # 左侧：表格
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=3)

        columns = ('scene', 'shot', 'description', 'action')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings')
        self.tree.heading('scene', text='场次')
        self.tree.heading('shot', text='镜头序号')
        self.tree.heading('description', text='场景描述')
        self.tree.heading('action', text='镜头描述')
        self.tree.column('scene', width=80, anchor='center')
        self.tree.column('shot', width=80, anchor='center')
        self.tree.column('description', width=250)
        self.tree.column('action', width=350)

        scrollbar = ttk.Scrollbar(left_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 右侧：按钮区域
        right_frame = ttk.Frame(self.paned, width=100)
        self.paned.add(right_frame, weight=1)

        self.edit_btn = tk.Button(right_frame, text="编辑镜头", command=self.edit_shot, width=12)
        self.edit_btn.pack(pady=5)
        self.add_btn = tk.Button(right_frame, text="新增镜头", command=self.add_shot, width=12)
        self.add_btn.pack(pady=5)
        self.del_btn = tk.Button(right_frame, text="删除镜头", command=self.delete_shot, width=12)
        self.del_btn.pack(pady=5)

        self.status_label = tk.Label(right_frame, text="", fg='gray')
        self.status_label.pack(pady=10)

    def update_script_data(self, script_data):
        """由控制器调用，更新表格数据"""
        self.current_shots_data = script_data
        self._refresh_tree()

    def _refresh_tree(self):
        """根据 current_shots_data 刷新表格"""
        self.tree.delete(*self.tree.get_children())
        for scene in self.current_shots_data:
            scene_id = scene.get('id')
            for idx, shot in enumerate(scene.get('shots', []), start=1):
                shot_id = f"{scene_id}-{idx}"
                scene_desc = shot.get('scene', '')[:50]
                action_desc = shot.get('visual', '')[:50]
                self.tree.insert('', 'end', values=(scene_id, shot_id, scene_desc, action_desc),
                                 tags=(scene_id, idx-1))

    def _get_selected_shot(self):
        """获取当前选中的镜头，返回 (scene_index, shot_index, scene_dict, shot_dict)"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先选中一个镜头")
            return None, None, None, None
        item = selection[0]
        values = self.tree.item(item, 'values')
        scene_id = values[0]
        # 找到场景索引
        for s_idx, scene in enumerate(self.current_shots_data):
            if str(scene.get('id')) == str(scene_id):
                # 找到镜头索引
                shot_id_full = values[1]
                try:
                    shot_idx = int(shot_id_full.split('-')[1]) - 1
                except:
                    continue
                if 0 <= shot_idx < len(scene['shots']):
                    return s_idx, shot_idx, scene, scene['shots'][shot_idx]
        messagebox.showerror("错误", "未找到对应镜头")
        return None, None, None, None

    def edit_shot(self):
        """编辑当前选中的镜头"""
        s_idx, sh_idx, scene, shot = self._get_selected_shot()
        if shot is None:
            return

        win = tk.Toplevel(self.frame)
        win.title(f"编辑镜头 {scene['id']}-{sh_idx+1}")
        win.geometry("700x600")
        win.transient(self.frame)
        win.grab_set()

        # 居中显示
        parent = self.frame.winfo_toplevel()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        win_w = 700
        win_h = 600
        x = parent_x + (parent_w // 2) - (win_w // 2)
        y = parent_y + (parent_h // 2) - (win_h // 2)
        win.geometry(f"+{x}+{y}")

        main_frame = tk.Frame(win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        fields = [
            ('场景', 'scene'),
            ('角色', 'roles'),
            ('动作', 'action'),
            ('对白', 'dialogue'),
            ('视觉描述', 'visual'),
            ('时长', 'duration'),
            ('情绪基调', 'emotion'),
            ('地域', 'region')
        ]
        entries = {}
        row = 0
        for label, key in fields:
            tk.Label(main_frame, text=label + "：", anchor='w').grid(row=row, column=0, sticky='w', pady=2)
            if key in ('visual', 'dialogue', 'action'):
                text_widget = scrolledtext.ScrolledText(main_frame, height=5, wrap='word')
                text_widget.grid(row=row, column=1, sticky='ew', pady=2)
                if key == 'roles':
                    value = ', '.join(shot.get(key, []))
                else:
                    value = shot.get(key, '')
                text_widget.insert('1.0', value)
                entries[key] = text_widget
            else:
                entry = tk.Entry(main_frame, width=50)
                entry.grid(row=row, column=1, sticky='w', pady=2)
                if key == 'duration':
                    entry.insert(0, str(shot.get(key, 10)))
                else:
                    entry.insert(0, shot.get(key, ''))
                entries[key] = entry
            row += 1

        def save():
            new_shot = shot.copy()
            for key, widget in entries.items():
                if isinstance(widget, tk.Entry):
                    value = widget.get().strip()
                else:
                    value = widget.get('1.0', 'end-1c').strip()
                if key == 'roles':
                    new_shot[key] = [r.strip() for r in value.split(',') if r.strip()]
                elif key == 'duration':
                    try:
                        new_shot[key] = float(value)
                    except:
                        new_shot[key] = 10.0
                else:
                    new_shot[key] = value
            self.current_shots_data[s_idx]['shots'][sh_idx] = new_shot
            self._refresh_tree()
            self._save_shots_to_file()
            win.destroy()
            self.status_label.config(text="镜头已更新", fg='green')
            self.frame.after(3000, lambda: self.status_label.config(text=""))

        tk.Button(win, text="保存", command=save, width=10).pack(pady=10)
        win.columnconfigure(1, weight=1)

    def add_shot(self):
        """在当前选中场次末尾新增一个镜头"""
        s_idx, _, scene, _ = self._get_selected_shot()
        if scene is None:
            return
        new_shot = {
            'scene': '',
            'roles': [],
            'action': '',
            'dialogue': '',
            'visual': '',
            'duration': 10.0,
            'emotion': '',
            'region': '全球·无明确时代'
        }
        self.current_shots_data[s_idx]['shots'].append(new_shot)
        self._refresh_tree()
        self._select_last_shot(s_idx)
        self.edit_shot()

    def _select_last_shot(self, scene_idx):
        """选中指定场次的最后一个镜头"""
        scene = self.current_shots_data[scene_idx]
        shot_count = len(scene['shots'])
        if shot_count == 0:
            return
        shot_id = f"{scene['id']}-{shot_count}"
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            if values[1] == shot_id:
                self.tree.selection_set(item)
                self.tree.see(item)
                break

    def delete_shot(self):
        """删除当前选中的镜头"""
        s_idx, sh_idx, scene, shot = self._get_selected_shot()
        if shot is None:
            return
        if not messagebox.askyesno("确认删除", f"确定要删除镜头 {scene['id']}-{sh_idx+1} 吗？"):
            return
        del self.current_shots_data[s_idx]['shots'][sh_idx]
        self._refresh_tree()
        self._save_shots_to_file()
        self.status_label.config(text="镜头已删除", fg='red')
        self.frame.after(3000, lambda: self.status_label.config(text=""))

    def _save_shots_to_file(self):
        """将 current_shots_data 保存为 shots.txt"""
        if not self.work_dir:
            if hasattr(self.controller, 'ui') and hasattr(self.controller.ui, 'work_dir'):
                self.work_dir = self.controller.ui.work_dir
            elif hasattr(self.controller, 'app') and hasattr(self.controller.app, 'work_dir'):
                self.work_dir = self.controller.app.work_dir
        if not self.work_dir:
            return
        shots_path = os.path.join(self.work_dir, "shots.txt")
        with open(shots_path, 'w', encoding='utf-8') as f:
            for scene in self.current_shots_data:
                for idx, shot in enumerate(scene.get('shots', []), start=1):
                    shot_id = f"{scene['id']}-{idx}"
                    title = shot.get('title', f"镜头{shot_id}")
                    f.write(f"【镜头{shot_id}：{title}】\n")
                    f.write(f"- 场景：{shot.get('scene', '')}\n")
                    roles_str = ', '.join(shot.get('roles', []))
                    f.write(f"- 角色：{roles_str}\n")
                    f.write(f"- 动作：{shot.get('action', '')}\n")
                    f.write(f"- 对白：{shot.get('dialogue', '')}\n")
                    f.write(f"- 视觉描述：{shot.get('visual', '')}\n")
                    f.write(f"- 时长：{shot.get('duration', 10):.1f}秒\n")
                    f.write(f"- 情绪基调：{shot.get('emotion', '')}\n")
                    f.write(f"- 地域：{shot.get('region', '全球·无明确时代')}\n")
                    f.write("===========================\n")

    def display_raw_text(self, text):
        """兼容旧接口：直接显示文本（不推荐）"""
        self.tree.delete(*self.tree.get_children())
        self.tree.insert('', 'end', values=('', '', '旧格式文本', text[:100] + '...'))

    def display_scenes(self, scenes):
        """由控制器调用，更新表格（与 update_script_data 类似）"""
        self.update_script_data(scenes)