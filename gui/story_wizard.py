import tkinter as tk
from tkinter import ttk
import json
import os
import threading
from utils.ai_utils import call_deepseek
from datetime import datetime

class StoryWizard:
    def __init__(self, parent, app, on_finish):
        self.parent = parent
        self.app = app
        self.on_finish = on_finish
        self.win = tk.Toplevel(parent)
        self.win.title("故事创作向导")
        self.win.geometry("1400x900")
        self.win.update_idletasks()
        x = (self.win.winfo_screenwidth() - 1400) // 2
        y = (self.win.winfo_screenheight() - 900) // 2
        self.win.geometry(f"+{x}+{y}")
        self.win.transient(parent)
        self.win.grab_set()
        self.duration_var = "2"   # 改为字符串

        self.data = self.load_data()
        self.rules = self.data.get("匹配规则", {})

        self.selections = {}
        self.title_var = tk.StringVar()
        self.idea_text = None

        self.create_widgets()

    def load_data(self):
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        files = {
            "影片类型": "story_types.json",
            "视觉风格": "visual_styles.json",
            "情感基调": "emotional_tones.json",
            "叙事结构": "narrative_structures.json",
            "世界观": "worldviews.json",
            "角色设定": "character_settings.json",
            "匹配规则": "matching_rules.json"
        }
        data = {}
        for key, filename in files.items():
            path = os.path.join(data_dir, filename)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data[key] = json.load(f)
            else:
                data[key] = {}
        return data

    def create_widgets(self):
        main_frame = ttk.Frame(self.win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # 顶部信息
        info_frame = ttk.LabelFrame(main_frame, text="故事信息", padding=5)
        info_frame.pack(fill='x', padx=5, pady=5)

        row0 = ttk.Frame(info_frame)
        row0.pack(fill='x', pady=2)
        ttk.Label(row0, text="故事标题：").pack(side='left', padx=5)
        ttk.Entry(row0, textvariable=self.title_var, width=50).pack(side='left', fill='x', expand=True, padx=5)

        row1 = ttk.Frame(info_frame)
        row1.pack(fill='x', pady=2)
        ttk.Label(row1, text="一句话需求：").pack(side='left', padx=5)
        self.idea_text = tk.Text(row1, height=3, wrap='word')
        self.idea_text.pack(side='left', fill='both', expand=True, padx=5)
        self._add_placeholder(self.idea_text, "可选择输入一句话主题，并点击智能导入，也可自行输入故事标题后逐一选择下方参数")
        # 创建智能导入按钮并保存引用
        self.smart_import_btn = ttk.Button(row1, text="智能导入", command=self.smart_import)
        self.smart_import_btn.pack(side='right', padx=5)

        # 在 row1 之后添加 row2
        row2 = ttk.Frame(info_frame)
        row2.pack(fill='x', pady=2)
        ttk.Label(row2, text="目标时长：").pack(side='left', padx=5)

        # 滑动条 1-10 分钟
        self.duration_scale = ttk.Scale(row2, from_=1, to=10, orient='horizontal', length=200)
        self.duration_scale.pack(side='left', padx=5)
        self.duration_label = ttk.Label(row2, text="5分钟", width=8)
        self.duration_label.pack(side='left', padx=5)

        # 输入框 1-120 分钟
        self.duration_entry = ttk.Entry(row2, width=6)
        self.duration_entry.pack(side='left', padx=5)
        ttk.Label(row2, text="分钟（可输入1-120）").pack(side='left')

        # 联动函数
        def on_scale_changed(event=None):
            if self.duration_entry.get().strip() == "":
                val = int(self.duration_scale.get())
                self.duration_label.config(text=f"{val}分钟")
                self.duration_var = str(val)

        def on_entry_changed(event=None):
            try:
                val = int(self.duration_entry.get().strip())
                if val < 1:
                    val = 1
                elif val > 120:
                    val = 120
                self.duration_entry.delete(0, tk.END)
                self.duration_entry.insert(0, str(val))
                self.duration_scale.set(val if val <= 10 else 10)
                self.duration_label.config(text=f"{val}分钟")
                self.duration_var = str(val)   # 转为字符串
            except ValueError:
                pass

        self.duration_scale.bind("<ButtonRelease-1>", on_scale_changed)
        self.duration_entry.bind("<KeyRelease>", on_entry_changed)

        # 初始化
        self.duration_scale.set(2)
        self.duration_label.config(text="2分钟")
        self.duration_var = "2"

        # 左右分栏
        paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned.pack(fill='both', expand=True, pady=5)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        self.create_left_panel(left_frame)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        self.create_right_panel(right_frame)

        # 底部按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=10)
        ttk.Button(btn_frame, text="生成故事", command=self.generate).pack(side='right', padx=5)
        ttk.Button(btn_frame, text="取消", command=self.win.destroy).pack(side='right', padx=5)
        self.gen_button = ttk.Button(btn_frame, text="生成故事", command=self.generate)
        self.gen_button.pack(side='right', padx=5)

    def create_left_panel(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 保存 canvas 以便其他方法使用
        self.left_canvas = canvas

        # 定义统一的滚轮处理函数
        def _on_mousewheel(event):
            # 滚动 canvas
            self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"  # 阻止事件继续传播

        # 递归绑定所有子控件的滚轮事件，但对 Combobox 需要特殊处理（在创建时单独绑定）
        def bind_recursive(widget):
            try:
                widget.bind("<MouseWheel>", _on_mousewheel, add=True)
                widget.bind("<Button-4>", _on_mousewheel, add=True)   # Linux
                widget.bind("<Button-5>", _on_mousewheel, add=True)   # Linux
            except:
                pass
            for child in widget.winfo_children():
                bind_recursive(child)

        # 绑定 canvas 自身
        canvas.bind("<MouseWheel>", _on_mousewheel, add=True)
        canvas.bind("<Button-4>", _on_mousewheel, add=True)
        canvas.bind("<Button-5>", _on_mousewheel, add=True)
        # 绑定现有控件
        bind_recursive(scrollable)

        # 创建各个区块
        self.create_genre_section(scrollable)
        self.create_visual_style_section(scrollable)
        self.create_emotional_tone_section(scrollable)
        self.create_narrative_structure_section(scrollable)
        self.create_worldview_section(scrollable)

    def create_right_panel(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=scrollable, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            return "break"  # 阻止事件继续传播

        # 绑定 canvas
        canvas.bind("<MouseWheel>", _on_mousewheel, add=True)

        # 递归绑定所有子控件
        def bind_recursive(widget):
            try:
                widget.bind("<MouseWheel>", _on_mousewheel, add=True)
            except:
                pass
            for child in widget.winfo_children():
                bind_recursive(child)

        # 先创建控件
        self.create_character_steps(scrollable)
        # 再绑定所有子控件（包括动态创建的）
        bind_recursive(scrollable)

    # ========== 影片类型 ==========
    def create_genre_section(self, parent):
        frame = ttk.LabelFrame(parent, text="影片类型", padding=5)
        frame.pack(fill='x', padx=5, pady=5)

        row1 = ttk.Frame(frame)
        row1.pack(fill='x', pady=2)
        ttk.Label(row1, text="主类型：").pack(side='left', padx=5)
        self.main_genre_var = tk.StringVar()
        main_genres = list(self.data["影片类型"].keys())
        self.main_genre_combo = ttk.Combobox(row1, textvariable=self.main_genre_var, values=main_genres, state='readonly')
        self._bind_combobox_scroll(self.main_genre_combo)
        self.main_genre_combo.pack(side='left', fill='x', expand=True, padx=5)
        self.main_genre_combo.bind('<<ComboboxSelected>>', self.on_main_genre_change)
        
        row2 = ttk.Frame(frame)
        row2.pack(fill='x', pady=2)
        ttk.Label(row2, text="子类型：").pack(side='left', padx=5)
        self.sub_genre_var = tk.StringVar()
        self.sub_genre_combo = ttk.Combobox(row2, textvariable=self.sub_genre_var, state='readonly')
        self._bind_combobox_scroll(self.sub_genre_combo)
        self.sub_genre_combo.pack(side='left', fill='x', expand=True, padx=5)
        self.sub_genre_combo.bind('<<ComboboxSelected>>', self.on_sub_genre_change)

        row3 = ttk.Frame(frame)
        row3.pack(fill='x', pady=2)
        ttk.Label(row3, text="细分类别：").pack(side='left', padx=5)
        self.detail_genre_var = tk.StringVar()
        self.detail_genre_combo = ttk.Combobox(row3, textvariable=self.detail_genre_var, state='readonly')
        self._bind_combobox_scroll(self.detail_genre_combo)
        self.detail_genre_combo.pack(side='left', fill='x', expand=True, padx=5)

    def on_main_genre_change(self, event=None):
        main = self.main_genre_var.get()
        if main and main in self.data["影片类型"]:
            sub_types = list(self.data["影片类型"][main]["子类型"].keys())
            self.sub_genre_combo['values'] = sub_types
            self.sub_genre_var.set('')
            self.detail_genre_combo['values'] = []
            self.detail_genre_var.set('')
            self.update_recommendations(main)

    def on_sub_genre_change(self, event=None):
        main = self.main_genre_var.get()
        sub = self.sub_genre_var.get()
        if main and sub:
            details = self.data["影片类型"][main]["子类型"][sub]
            self.detail_genre_combo['values'] = details
            self.detail_genre_var.set('')
            # 如果主类型是“动画”（需要根据您的 JSON 结构调整），则记录流派
            if main == "动画" and sub:  # 这里“动画”需与您的影片类型主类型名称一致
                self.current_animation_genre = sub
                # 如果已经选择了视觉风格，则刷新细化参数
                if hasattr(self, 'visual_refinement_text'):
                    self._apply_visual_refinement()

    def create_visual_style_section(self, parent):
        frame = ttk.LabelFrame(parent, text="视觉风格", padding=5)
        frame.pack(fill='x', padx=5, pady=5)

        # 加载流派映射表（用于2D动画）
        mappings_path = os.path.join(os.path.dirname(__file__), "data", "style_mappings.json")
        self.style_mappings = {}
        if os.path.exists(mappings_path):
            with open(mappings_path, 'r', encoding='utf-8') as f:
                self.style_mappings = json.load(f)

        # 预处理视觉风格数据：移除每个大类下的 "子类" 层
        raw_visual_data = self.data["视觉风格"]
        processed_data = {}
        for category, content in raw_visual_data.items():
            if isinstance(content, dict) and "子类" in content:
                processed_data[category] = content["子类"]
            else:
                processed_data[category] = content
        self.visual_data = processed_data

        # 存储当前选择
        self.visual_selections = []      # 每级选中的值
        self.visual_widgets = []         # 每级的 (row_frame, combo, var)
        # 用于2D动画的特殊数据
        self.available_crafts = []       # 所有制作工艺列表（从 visual_data["2D动画"] 的键获取）
        self.current_genre = None        # 当前选中的流派

        # 容器：所有级联选择行
        self.visual_choices_container = ttk.Frame(frame)
        self.visual_choices_container.pack(fill='x', padx=5, pady=5)

        # 细化参数文本框
        refinement_frame = ttk.Frame(frame)
        refinement_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(refinement_frame, text="视觉细化参数：").pack(anchor='w')
        self.visual_refinement_text = tk.Text(refinement_frame, height=3, wrap='word')
        self.visual_refinement_text.pack(fill='x')
        self._add_placeholder(self.visual_refinement_text, "细化参数将自动填入，可修改")

        # 开始构建第一级
        self._rebuild_visual_choices()

    def _rebuild_visual_choices(self):
        """根据 self.visual_selections 重建所有级联选择行"""
        for row_frame, _, _ in self.visual_widgets:
            row_frame.destroy()
        self.visual_widgets.clear()

        if not self.visual_selections:
            first_level_data = self.visual_data
            self._add_visual_level(first_level_data, 0)
            return

        main_category = self.visual_selections[0]

        # 通用非2D动画处理（三级结构）
        if main_category != "2D动画":
            current_data = self.visual_data
            for idx, key in enumerate(self.visual_selections):
                self._add_visual_level(current_data, idx, selected_key=key)
                if isinstance(current_data, dict) and key in current_data:
                    current_data = current_data[key]
                else:
                    break
            # 如果当前数据是字典且还有下一级，则添加未选中的下一级
            if isinstance(current_data, dict) and len(current_data) > 0:
                self._add_visual_level(current_data, len(self.visual_selections))
            # 如果当前数据已经是列表（质感列表），且用户还没有选质感，则添加质感列表
            elif isinstance(current_data, list) and len(self.visual_selections) < 3:
                self._add_visual_level(current_data, len(self.visual_selections))
            elif isinstance(current_data, list):
                self._apply_visual_refinement()
            return

        # 2D动画四层结构（保持不变）
        self._add_visual_level(self.visual_data, 0, selected_key="2D动画")
        if len(self.visual_selections) >= 2:
            genre = self.visual_selections[1]
            self.current_genre = genre
            all_genres = list(self.style_mappings.keys())
            self._add_visual_level(all_genres, 1, selected_key=genre)
        else:
            all_genres = list(self.style_mappings.keys())
            self._add_visual_level(all_genres, 1)
            return

        crafts = list(self.visual_data["2D动画"].keys())
        if len(self.visual_selections) >= 3:
            craft = self.visual_selections[2]
            self._add_visual_level(crafts, 2, selected_key=craft)
        else:
            if self.current_genre and self.current_genre in self.style_mappings:
                recommended_craft = self.style_mappings[self.current_genre].get("推荐制作工艺", "")
                if "或" in recommended_craft:
                    recommended_craft = recommended_craft.split("或")[0].strip()
                if recommended_craft in crafts:
                    self.visual_selections.append(recommended_craft)
                    self._add_visual_level(crafts, 2, selected_key=recommended_craft)
                else:
                    self._add_visual_level(crafts, 2)
            else:
                self._add_visual_level(crafts, 2)
            return

        current_craft = self.visual_selections[2]
        textures = self.visual_data["2D动画"].get(current_craft, [])
        if len(self.visual_selections) >= 4:
            texture = self.visual_selections[3]
            self._add_visual_level(textures, 3, selected_key=texture)
        else:
            if self.current_genre and self.current_genre in self.style_mappings:
                recommended_texture = self.style_mappings[self.current_genre].get("推荐视觉质感", "")
                if recommended_texture and recommended_texture in textures:
                    self.visual_selections.append(recommended_texture)
                    self._add_visual_level(textures, 3, selected_key=recommended_texture)
                else:
                    self._add_visual_level(textures, 3)
            else:
                self._add_visual_level(textures, 3)

        self._apply_visual_refinement()

    def _add_visual_level(self, data, level, selected_key=None):
        """在容器底部添加一行选择控件，data 可以是 dict、list 或普通列表"""
        row_frame = ttk.Frame(self.visual_choices_container)
        row_frame.pack(fill='x', pady=2)

        # 动态确定标签文本
        if level == 0:
            label_text = "大类："
        else:
            # 判断当前是否处于2D动画路径下
            is_2d = (len(self.visual_selections) > 0 and self.visual_selections[0] == "2D动画")
            if is_2d:
                if level == 1:
                    label_text = "流派："
                elif level == 2:
                    label_text = "制作工艺："
                elif level == 3:
                    label_text = "视觉质感："
                else:
                    label_text = f"第{level+1}级："
            else:
                if level == 1:
                    label_text = "子类："
                elif level == 2:
                    label_text = "质感："
                else:
                    label_text = f"第{level+1}级："

        ttk.Label(row_frame, text=label_text, width=10).pack(side='left', padx=5)

        if isinstance(data, dict):
            options = list(data.keys())
        elif isinstance(data, list):
            options = data
        else:
            options = []

        var = tk.StringVar()
        combo = ttk.Combobox(row_frame, textvariable=var, values=options, state='readonly', width=50)
        self._bind_combobox_scroll(combo)
        combo.pack(side='left', fill='x', expand=True, padx=5)

        if selected_key and selected_key in options:
            var.set(selected_key)

        combo.bind('<<ComboboxSelected>>', lambda e, lvl=level: self._on_visual_select(lvl, var.get()))
        self.visual_widgets.append((row_frame, combo, var))

    def _on_visual_select(self, level, selected_value):
        """用户在某级下拉框中选择了值"""
        # 截断后面的选择
        self.visual_selections = self.visual_selections[:level]
        self.visual_selections.append(selected_value)

        # 特殊处理：如果更改的是流派，则需要重置制作工艺和视觉质感为推荐值
        if level == 1 and self.visual_selections[0] == "2D动画":
            # 清除后面的选择
            self.visual_selections = self.visual_selections[:2]
            # 重新构建，会自动设置推荐工艺和质感
            self._rebuild_visual_choices()
            return

        # 如果更改的是制作工艺（2D动画的第三级），则需要清除第四级选择
        if level == 2 and self.visual_selections[0] == "2D动画":
            self.visual_selections = self.visual_selections[:3]
            self._rebuild_visual_choices()
            return

        self._rebuild_visual_choices()

    def _apply_visual_refinement(self):
        """根据当前选择的视觉风格路径，自动填入细化参数"""
        # 细化参数仅对 2D动画 有效
        if not self.visual_selections or self.visual_selections[0] != "2D动画":
            return

        # 期望路径: [大类, 流派, 制作工艺, 视觉质感]
        if len(self.visual_selections) < 2:
            return

        genre = self.visual_selections[1]
        if genre in self.style_mappings:
            params = self.style_mappings[genre].get("细化参数", "")
            self.visual_refinement_text.delete('1.0', 'end')
            self.visual_refinement_text.insert('1.0', params)
            self.visual_refinement_text.config(fg='black')   # 添加这一行
        else:
            self.visual_refinement_text.delete('1.0', 'end')
            
    # ========== 情感基调 ==========
    def create_emotional_tone_section(self, parent):
        frame = ttk.LabelFrame(parent, text="情感基调", padding=5)
        frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(frame, text="（绿色为推荐，黄色为允许，最多可选3个）", foreground='gray').pack(anchor='w', padx=5, pady=2)

        self.tone_listbox = tk.Listbox(frame, selectmode='multiple', height=8)
        self.tone_listbox.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.tone_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.tone_listbox.config(yscrollcommand=scrollbar.set)

        # 记录上一次选中的值，用于恢复
        self._prev_selection = []

        def on_select(event):
            current = self.tone_listbox.curselection()
            if len(current) > 3:
                # 超过3个，恢复到之前的选择
                self.tone_listbox.selection_clear(0, tk.END)
                for idx in self._prev_selection:
                    self.tone_listbox.selection_set(idx)
            else:
                # 更新记录
                self._prev_selection = list(current)

        self.tone_listbox.bind('<<ListboxSelect>>', on_select)

        all_tones = []
        for category in self.data["情感基调"].values():
            all_tones.extend(category)
        for tone in all_tones:
            self.tone_listbox.insert(tk.END, tone)
        self.all_tones = all_tones

    def update_emotional_tones(self, recommended, allowed):
        for i in range(self.tone_listbox.size()):
            self.tone_listbox.itemconfig(i, bg='white', fg='black')
        for tone in recommended:
            for i in range(self.tone_listbox.size()):
                if self.tone_listbox.get(i) == tone:
                    self.tone_listbox.itemconfig(i, bg='lightgreen')
        for tone in allowed:
            for i in range(self.tone_listbox.size()):
                if self.tone_listbox.get(i) == tone:
                    self.tone_listbox.itemconfig(i, bg='lightyellow')

    # ========== 叙事结构 ==========
    def create_narrative_structure_section(self, parent):
        frame = ttk.LabelFrame(parent, text="叙事结构", padding=5)
        frame.pack(fill='x', padx=5, pady=5)

        self.struct_var = tk.StringVar()
        self.struct_combo = ttk.Combobox(frame, textvariable=self.struct_var, state='readonly')
        self._bind_combobox_scroll(self.struct_combo)
        self.struct_combo.pack(fill='x', padx=5, pady=5)

        all_structs = []
        for category in self.data["叙事结构"].values():
            all_structs.extend(category)
        self.all_structs = all_structs
        self.struct_combo['values'] = all_structs

    def update_narrative_structures(self, rec):
        self.struct_combo['values'] = rec if rec else self.all_structs

    # ========== 世界观 ==========
    def create_worldview_section(self, parent):
        frame = ttk.LabelFrame(parent, text="世界观", padding=5)
        frame.pack(fill='x', padx=5, pady=5)

        self.worldview_main_var = tk.StringVar()
        worldview_mains = list(self.data["世界观"].keys())
        self.worldview_main_combo = ttk.Combobox(frame, textvariable=self.worldview_main_var, values=worldview_mains, state='readonly')
        self._bind_combobox_scroll(self.worldview_main_combo)
        self.worldview_main_combo.pack(fill='x', padx=5, pady=2)
        self.worldview_main_combo.bind('<<ComboboxSelected>>', self.on_worldview_main_change)

        self.worldview_sub_var = tk.StringVar()
        self.worldview_sub_combo = ttk.Combobox(frame, textvariable=self.worldview_sub_var, state='readonly')
        self._bind_combobox_scroll(self.worldview_sub_combo)
        self.worldview_sub_combo.pack(fill='x', padx=5, pady=2)
        self.worldview_sub_combo.bind('<<ComboboxSelected>>', self.on_worldview_sub_change)

        self.worldview_detail_var = tk.StringVar()
        self.worldview_detail_combo = ttk.Combobox(frame, textvariable=self.worldview_detail_var, state='readonly')
        self._bind_combobox_scroll(self.worldview_detail_combo)
        self.worldview_detail_combo.pack(fill='x', padx=5, pady=2)

    def on_worldview_main_change(self, event=None):
        main = self.worldview_main_var.get()
        if not main:
            return
        data = self.data["世界观"][main]
        if isinstance(data, dict):
            subs = list(data.keys())
            self.worldview_sub_combo['values'] = subs
            self.worldview_sub_var.set('')
            self.worldview_detail_combo['values'] = []
            self.worldview_detail_var.set('')
        elif isinstance(data, list):
            self.worldview_sub_combo.pack_forget()
            self.worldview_sub_var.set('')
            self.worldview_detail_combo['values'] = data
            self.worldview_detail_var.set('')
        else:
            self.worldview_sub_combo['values'] = []
            self.worldview_detail_combo['values'] = []

    def on_worldview_sub_change(self, event=None):
        main = self.worldview_main_var.get()
        sub = self.worldview_sub_var.get()
        if not main or not sub:
            return
        data = self.data["世界观"][main]
        if isinstance(data, dict) and sub in data:
            details = data[sub]
            self.worldview_detail_combo['values'] = details
            self.worldview_detail_var.set('')

    def update_recommendations(self, main_type):
        rule = self.rules.get(main_type, {})
        recommended_tones = rule.get("推荐情感基调", [])
        allowed_tones = rule.get("允许情感基调", [])
        if hasattr(self, 'update_emotional_tones'):
            self.update_emotional_tones(recommended_tones, allowed_tones)
        recommended_structs = rule.get("推荐叙事结构", [])
        if hasattr(self, 'update_narrative_structures'):
            self.update_narrative_structures(recommended_structs)

    # ========== 角色设定 ==========
    def create_character_steps(self, parent):
        # 第1步
        step1 = ttk.LabelFrame(parent, text="第1步：角色数量与主角身份", padding=5)
        step1.pack(fill='x', padx=5, pady=5)

        row1_1 = ttk.Frame(step1)
        row1_1.pack(fill='x', pady=2)
        ttk.Label(row1_1, text="角色数量：").pack(side='left', padx=5)
        self.role_count_var = tk.StringVar()
        role_counts = self.data["角色设定"]["角色数量"]
        ttk.Combobox(row1_1, textvariable=self.role_count_var, values=role_counts, state='readonly', width=20).pack(side='left', padx=5)

        row1_2 = ttk.Frame(step1)
        row1_2.pack(fill='x', pady=2)
        ttk.Label(row1_2, text="主角身份：").pack(side='left', padx=5)
        self.role_identity_var = tk.StringVar()
        human_roles = self.data["角色设定"]["角色类型"]["人类"]
        ttk.Combobox(row1_2, textvariable=self.role_identity_var, values=human_roles, state='readonly', width=20).pack(side='left', padx=5)
        # 在第1步中，主角身份之后添加主角年龄
        row1_3 = ttk.Frame(step1)
        row1_3.pack(fill='x', pady=2)
        ttk.Label(row1_3, text="主角年龄：").pack(side='left', padx=5)
        self.age_var = tk.StringVar(value="青年")
        age_options = ["少年", "青年", "中年", "老年", "不限"]
        ttk.Combobox(row1_3, textvariable=self.age_var, values=age_options, state='readonly', width=10).pack(side='left', padx=5)

        # 第2步
        step2 = ttk.LabelFrame(parent, text="第2步：主角核心驱动与性格", padding=5)
        step2.pack(fill='x', padx=5, pady=5)

        row2_1 = ttk.Frame(step2)
        row2_1.pack(fill='x', pady=2)
        ttk.Label(row2_1, text="欲望：").pack(side='left', padx=5)
        self.desire_var = tk.StringVar()
        ttk.Entry(row2_1, textvariable=self.desire_var, width=40).pack(side='left', padx=5)

        row2_2 = ttk.Frame(step2)
        row2_2.pack(fill='x', pady=2)
        ttk.Label(row2_2, text="恐惧：").pack(side='left', padx=5)
        self.fear_var = tk.StringVar()
        ttk.Entry(row2_2, textvariable=self.fear_var, width=40).pack(side='left', padx=5)

        row2_3 = ttk.Frame(step2)
        row2_3.pack(fill='x', pady=2)
        ttk.Label(row2_3, text="性格（多选）：").pack(side='left', padx=5)
        traits_frame = ttk.Frame(row2_3)
        traits_frame.pack(side='left', fill='x', expand=True, padx=5)
        self.traits_vars = {}
        traits = self.data["角色设定"]["性格特质"]
        for i, trait in enumerate(traits[:20]):
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(traits_frame, text=trait, variable=var)
            cb.grid(row=i//4, column=i%4, sticky='w', padx=2)
            self.traits_vars[trait] = var

        # 第3步
        step3 = ttk.LabelFrame(parent, text="第3步：外形风格", padding=5)
        step3.pack(fill='x', padx=5, pady=5)

        row3_1 = ttk.Frame(step3)
        row3_1.pack(fill='x', pady=2)
        ttk.Label(row3_1, text="风格：").pack(side='left', padx=5)
        self.appearance_var = tk.StringVar()
        appearance_options = []
        for cat in self.data["角色设定"]["外形风格"].values():
            appearance_options.extend(cat)
        ttk.Combobox(row3_1, textvariable=self.appearance_var, values=appearance_options, state='readonly', width=30).pack(side='left', padx=5)

        # 第4步
        step4 = ttk.LabelFrame(parent, text="第4步：盟友与对手", padding=5)
        step4.pack(fill='x', padx=5, pady=5)

        row4_1 = ttk.Frame(step4)
        row4_1.pack(fill='x', pady=2)
        ttk.Label(row4_1, text="盟友数量：").pack(side='left', padx=5)
        self.allies_count_var = tk.StringVar(value="0")
        ttk.Combobox(row4_1, textvariable=self.allies_count_var, values=[str(i) for i in range(4)], state='readonly', width=5).pack(side='left', padx=5)

        row4_2 = ttk.Frame(step4)
        row4_2.pack(fill='x', pady=2)
        ttk.Label(row4_2, text="对手数量：").pack(side='left', padx=5)
        self.enemies_count_var = tk.StringVar(value="0")
        ttk.Combobox(row4_2, textvariable=self.enemies_count_var, values=[str(i) for i in range(4)], state='readonly', width=5).pack(side='left', padx=5)

        # 折叠区
        self.detail_frame_visible = False
        self.detail_frame = ttk.Frame(step4)
        self.detail_frame.pack(fill='x', pady=5)
        self.detail_frame.pack_forget()

        ttk.Button(step4, text="▼ 详细设定关系网", command=self.toggle_detail_frame).pack(pady=5)

        ttk.Label(self.detail_frame, text="盟友列表（每行一个名称）：").pack(anchor='w', padx=5, pady=2)
        self.allies_detail_text = tk.Text(self.detail_frame, height=4, width=40)
        self.allies_detail_text.pack(fill='x', padx=5, pady=2)

        ttk.Label(self.detail_frame, text="对手列表（每行一个名称）：").pack(anchor='w', padx=5, pady=2)
        self.enemies_detail_text = tk.Text(self.detail_frame, height=4, width=40)
        self.enemies_detail_text.pack(fill='x', padx=5, pady=2)

        ttk.Label(self.detail_frame, text="关系网描述（可选）：").pack(anchor='w', padx=5, pady=2)
        self.relations_detail_text = tk.Text(self.detail_frame, height=6, width=40)
        self.relations_detail_text.pack(fill='x', padx=5, pady=2)

        # 第5步
        step5 = ttk.LabelFrame(parent, text="第5步：特殊要求（可选）", padding=5)
        step5.pack(fill='x', padx=5, pady=5)

        self.special_req_text = tk.Text(step5, height=3, width=60)
        self.special_req_text.pack(fill='x', padx=5, pady=5)
        self._add_placeholder(self.special_req_text, "例如：主角戴眼镜、故事发生在雨天、要求有猫等")

    def toggle_detail_frame(self):
        if self.detail_frame_visible:
            self.detail_frame.pack_forget()
            self.detail_frame_visible = False
        else:
            self.detail_frame.pack(fill='x', pady=5)
            self.detail_frame_visible = True

    def _add_placeholder(self, text_widget, placeholder):
        def on_focus_in(event):
            if text_widget.get('1.0', 'end-1c') == placeholder:
                text_widget.delete('1.0', 'end')
                text_widget.config(fg='black')
        def on_focus_out(event):
            if not text_widget.get('1.0', 'end-1c').strip():
                text_widget.delete('1.0', 'end')
                text_widget.insert('1.0', placeholder)
                text_widget.config(fg='gray')
        text_widget.insert('1.0', placeholder)
        text_widget.config(fg='gray')
        text_widget.bind('<FocusIn>', on_focus_in)
        text_widget.bind('<FocusOut>', on_focus_out)

    def _bind_combobox_scroll(self, combo):
        """强制 Combobox 忽略鼠标滚轮，转而滚动左侧面板"""
        def on_wheel(event):
            if hasattr(self, 'left_canvas'):
                self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        combo.bind("<MouseWheel>", on_wheel, add=True)
        combo.bind("<Button-4>", on_wheel, add=True)
        combo.bind("<Button-5>", on_wheel, add=True)

    def smart_import(self):
        idea = self.idea_text.get('1.0', 'end-1c').strip()
        if not idea:
            from tkinter import messagebox
            messagebox.showwarning("提示", "请先输入一句话需求")
            return

        self.smart_import_btn.config(state='disabled', text="解析中...")
        self.win.update_idletasks()

        def task():
            try:
                # 第一步：获取顶层信息
                step1_data = self._call_ai_step1(idea)
                if not step1_data:
                    raise Exception("第一步解析失败")
                # 第二步：根据主类型获取子类型和细分类别
                step2_data = self._call_ai_step2(idea, step1_data)
                # 合并数据
                final_data = {**step1_data, **step2_data}
                self.win.after(0, lambda: self._apply_import_data(final_data))
            except Exception as e:
                self.win.after(0, lambda: self._show_import_error(str(e)))
            finally:
                self.win.after(0, lambda: self.smart_import_btn.config(state='normal', text="智能导入"))

        threading.Thread(target=task, daemon=True).start()

    def _call_ai_step1(self, idea):
        all_genres = list(self.data["影片类型"].keys())
        all_tones = self.all_tones
        all_traits = self.data["角色设定"]["性格特质"]
        all_structures = self.all_structs
        all_worldview_mains = list(self.data["世界观"].keys())
        all_visual_mains = list(self.data["视觉风格"].keys())

        prompt = f"""你是一个专业的影视策划。请根据用户的一句话需求，解析出故事的基本设定，输出 JSON 格式。
    用户需求：{idea}

    你必须严格从以下给定的选项中选择，不要创造新值。

    主类型：{all_genres}
    情感基调（最多3个）：{all_tones}
    性格特质（最多3个）：{all_traits}
    叙事结构：{all_structures}
    世界观大类：{all_worldview_mains}
    视觉风格大类：{all_visual_mains}

    请输出以下结构的 JSON，不要包含任何额外解释：
    {{
        "story_title": "故事标题（5-10个字）",
        "duration_minutes": 2,  // 根据用户需求推测，默认2分钟
        "main_genre": "主类型",
        "emotional_tones": ["基调1", "基调2", "基调3"],
        "character_traits": ["性格1", "性格2", "性格3"],
        "narrative_structure": "叙事结构",
        "worldview_main": "世界观大类",
        "visual_main": "视觉风格大类",
        "desire": "主角的欲望（一句话）",
        "fear": "主角的恐惧（一句话）",
        "role_count": "角色数量（单主角/双主角/三人核心/四人核心/五人及以上群像/独角戏/无角色）",
        "role_identity": "主角身份（从人类角色列表中选，如'英雄'）",
        "appearance": "外形风格（如'真人比例'）",
        "allies_count": 0,  // 根据故事类型推测盟友数量（0-3）
        "enemies_count": 0  // 根据故事类型推测对手数量（0-3）
    }}

    注意：情感基调和性格特质必须从上面列表中选取。只输出 JSON。"""
        result = call_deepseek(prompt, temperature=0.5, max_tokens=2000)
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        return json.loads(result)

    def _call_ai_step2(self, idea, step1_data):
        main_genre = step1_data.get("main_genre")
        visual_main = step1_data.get("visual_main")
        worldview_main = step1_data.get("worldview_main")
        if not main_genre:
            return {}

        genre_sub = self.data["影片类型"].get(main_genre, {}).get("子类型", {})
        visual_sub_data = self.data["视觉风格"].get(visual_main, {}).get("子类", {}) if visual_main else {}
        worldview_data = self.data["世界观"].get(worldview_main, {})
        worldview_subs = list(worldview_data.keys()) if isinstance(worldview_data, dict) else worldview_data

        prompt = f"""请根据用户需求，从以下选项中选择合适的子类型和细分类别。
    用户需求：{idea}
    主类型：{main_genre}
    子类型列表：{list(genre_sub.keys())}
    细分类别列表（按子类型）：{genre_sub}

    视觉风格大类：{visual_main}
    视觉风格子类列表：{list(visual_sub_data.keys()) if visual_sub_data else []}
    视觉风格具体风格列表（按子类）：{visual_sub_data}

    世界观大类：{worldview_main}
    世界观子类/具体列表：{worldview_subs}

    请输出以下 JSON，只包含选中的值：
    {{
        "genre_sub": "子类型",
        "genre_detail": "细分类别",
        "visual_sub": "视觉风格子类",
        "visual_detail": "具体风格",
        "worldview_sub": "世界观子类（如果有）",
        "worldview_detail": "世界观具体（如果有）"
    }}
    如果某项无法确定，输出空字符串。"""
        result = call_deepseek(prompt, temperature=0.5, max_tokens=800)
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        step2_data = json.loads(result)
        return {
            "genre": {
                "main": main_genre,
                "sub": step2_data.get("genre_sub", ""),
                "detail": step2_data.get("genre_detail", "")
            },
            "visual_style": {
                "main": visual_main,
                "sub": step2_data.get("visual_sub", ""),
                "detail": step2_data.get("visual_detail", "")
            },
            "worldview": {
                "main": worldview_main,
                "sub": step2_data.get("worldview_sub", ""),
                "detail": step2_data.get("worldview_detail", "")
            },
            "story_title": step1_data.get("story_title", ""),
            "emotional_tones": step1_data.get("emotional_tones", []),
            "narrative_structure": step1_data.get("narrative_structure", ""),
            "character": {
                "count": step1_data.get("role_count", ""),
                "identity": step1_data.get("role_identity", ""),
                "desire": step1_data.get("desire", ""),
                "fear": step1_data.get("fear", ""),
                "traits": step1_data.get("character_traits", []),
                "appearance": step1_data.get("appearance", ""),
                "allies_count": step1_data.get("allies_count", 0),
                "enemies_count": step1_data.get("enemies_count", 0)
            }
        }

    def _apply_import_data(self, data):
        """根据解析结果自动填写界面控件"""
        try:
            # 故事标题
            if 'story_title' in data:
                self.title_var.set(data['story_title'])

            # 影片类型
            genre = data.get('genre', {})
            if 'main' in genre:
                self.main_genre_var.set(genre['main'])
                self.on_main_genre_change()  # 触发更新子类型下拉
                self.win.update_idletasks()
            if 'sub' in genre:
                self.sub_genre_var.set(genre['sub'])
                self.on_sub_genre_change()
                self.win.update_idletasks()
            if 'detail' in genre:
                self.detail_genre_var.set(genre['detail'])

            # 视觉风格
            visual = data.get('visual_style', {})
            if visual:
                main_cat = visual.get('main', '')
                sub = visual.get('sub', '')
                detail = visual.get('detail', '')
                if main_cat:
                    # 清除现有选择
                    self.visual_selections = []
                    self.visual_selections.append(main_cat)
                    if main_cat == "2D动画" and sub:
                        # 流派
                        self.visual_selections.append(sub)
                        # 获取推荐工艺和质感（如果存在）
                        if sub in self.style_mappings:
                            craft = self.style_mappings[sub].get("推荐制作工艺", "")
                            texture = self.style_mappings[sub].get("推荐视觉质感", "")
                            if craft:
                                self.visual_selections.append(craft)
                            if texture:
                                self.visual_selections.append(texture)
                    else:
                        # 非2D动画：子类、质感
                        if sub:
                            self.visual_selections.append(sub)
                        if detail:
                            self.visual_selections.append(detail)
                    # 重建视觉风格界面
                    self._rebuild_visual_choices()
                    self.win.update_idletasks()

            # 叙事结构
            if 'narrative_structure' in data:
                self.struct_var.set(data['narrative_structure'])

            # 世界观
            worldview = data.get('worldview', {})
            if 'main' in worldview:
                self.worldview_main_var.set(worldview['main'])
                self.on_worldview_main_change()
                self.win.update_idletasks()
            if 'sub' in worldview:
                self.worldview_sub_var.set(worldview['sub'])
                self.on_worldview_sub_change()
                self.win.update_idletasks()
            if 'detail' in worldview:
                self.worldview_detail_var.set(worldview['detail'])

            # 角色设定
            char = data.get('character', {})
            if 'count' in char:
                self.role_count_var.set(char['count'])
            if 'identity' in char:
                self.role_identity_var.set(char['identity'])
            if 'desire' in char:
                self.desire_var.set(char['desire'])
            if 'fear' in char:
                self.fear_var.set(char['fear'])
            if 'traits' in char:
                # 清空原有选择
                for var in self.traits_vars.values():
                    var.set(False)
                for trait in char['traits']:
                    if trait in self.traits_vars:
                        self.traits_vars[trait].set(True)
            if 'appearance' in char:
                self.appearance_var.set(char['appearance'])
            if 'allies_count' in char:
                self.allies_count_var.set(str(char['allies_count']))
            if 'enemies_count' in char:
                self.enemies_count_var.set(str(char['enemies_count']))

            # 目标时长
            if 'duration_minutes' in data:
                try:
                    dur = int(data['duration_minutes'])
                    dur = max(1, min(120, dur))  # 限制1-120
                    self.duration_var = dur
                    self.duration_scale.set(dur if dur <= 10 else 10)
                    self.duration_entry.delete(0, tk.END)
                    self.duration_entry.insert(0, str(dur))
                    self.duration_label.config(text=f"{dur}分钟")
                except:
                    pass

            from tkinter import messagebox
            messagebox.showinfo("成功", "智能导入完成，请检查并修改选项")
        except Exception as e:
            self._show_import_error(f"应用数据时出错: {e}")

    def _show_import_error(self, error_msg):
        from tkinter import messagebox
        messagebox.showerror("智能导入失败", f"解析失败：{error_msg}\n请检查网络或稍后重试")

    def generate(self):
        # 收集所有选择到 self.selections
        self.selections['故事标题'] = self.title_var.get()
        self.selections['一句话需求'] = self.idea_text.get('1.0', 'end-1c').strip()
        self.selections['目标时长'] = self.duration_var
        self.selections['影片类型'] = {
            '主类型': self.main_genre_var.get(),
            '子类型': self.sub_genre_var.get(),
            '细分类别': self.detail_genre_var.get()
        }
        # 视觉风格（使用修正后的完整结构）
        if hasattr(self, 'visual_selections') and self.visual_selections:
            path = self.visual_selections
            visual_category = path[0] if len(path) >= 1 else ''
            if visual_category == "2D动画" and len(path) >= 4:
                visual_genre = path[1]
                visual_craft = path[2]
                visual_texture = path[3]
                visual_sub = ''  # 2D动画不使用子类字段
            else:
                # 非2D动画：大类 -> 子类 -> 质感
                visual_sub = path[1] if len(path) >= 2 else ''
                visual_texture = path[2] if len(path) >= 3 else (path[1] if len(path) >= 2 else '')
                visual_genre = ''
                visual_craft = ''
        else:
            visual_category = visual_sub = visual_genre = visual_craft = visual_texture = ''
        visual_refinement = self.visual_refinement_text.get('1.0', 'end-1c').strip()
        if visual_refinement == "细化参数将自动填入，可修改":
            visual_refinement = ""
        self.selections['视觉风格'] = {
            '大类': visual_category,
            '子类': visual_sub,
            '流派': visual_genre,
            '制作工艺': visual_craft,
            '视觉质感': visual_texture,
            '视觉细化参数': visual_refinement
        }
        selected_tones = [self.tone_listbox.get(i) for i in self.tone_listbox.curselection()]
        if len(selected_tones) > 3:
            tk.messagebox.showerror("错误", "情感基调最多只能选择3个")
            return
        self.selections['情感基调'] = selected_tones
        self.selections['叙事结构'] = self.struct_var.get()
        self.selections['世界观'] = {
            '大类': self.worldview_main_var.get(),
            '子类': self.worldview_sub_var.get(),
            '具体': self.worldview_detail_var.get()
        }
        allies_count = int(self.allies_count_var.get())
        enemies_count = int(self.enemies_count_var.get())
        allies_detail = self.allies_detail_text.get('1.0', 'end-1c').strip()
        enemies_detail = self.enemies_detail_text.get('1.0', 'end-1c').strip()
        relations_detail = self.relations_detail_text.get('1.0', 'end-1c').strip()
        special_req = self.special_req_text.get('1.0', 'end-1c').strip()
        if allies_detail or enemies_detail or relations_detail:
            allies = [name.strip() for name in allies_detail.split('\n') if name.strip()]
            enemies = [name.strip() for name in enemies_detail.split('\n') if name.strip()]
        else:
            allies = [f"盟友{i+1}" for i in range(allies_count)] if allies_count > 0 else []
            enemies = [f"对手{i+1}" for i in range(enemies_count)] if enemies_count > 0 else []
        self.selections['角色设定'] = {
            '角色数量': self.role_count_var.get(),
            '主角身份': self.role_identity_var.get(),
            '欲望': self.desire_var.get(),
            '恐惧': self.fear_var.get(),
            '性格': [t for t, var in self.traits_vars.items() if var.get()],
            '外形风格': self.appearance_var.get(),
            '盟友': allies,
            '对手': enemies,
            '关系网': relations_detail if relations_detail else "",
            '特殊要求': special_req if special_req and special_req != "例如：主角戴眼镜、故事发生在雨天、要求有猫等" else "",
            '主角年龄': self.age_var.get()   # 已添加
        }

        # 安全记录日志
        def log(msg):
            if self.app and hasattr(self.app, 'log'):
                self.app.log(msg)
            else:
                print(msg)

        def convert_ints_to_str(obj):
            if isinstance(obj, dict):
                return {k: convert_ints_to_str(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_ints_to_str(v) for v in obj]
            elif isinstance(obj, (int, float)):
                return str(obj)
            else:
                return obj

        self.selections = convert_ints_to_str(self.selections)

        log("正在生成故事和标题，请稍候...")

        # 将整个 selections 转为易读的文本
        selections_text = json.dumps(self.selections, ensure_ascii=False, indent=2)

        prompt = f"""
    你是一位专业的故事撰稿人。请根据以下用户选择的完整设定，生成一个完整的故事口播稿，并同时生成一个简洁有力的故事标题。

    【用户核心创意】（一句话需求，必须严格遵循，不得偏离）
    {self.selections.get('一句话需求', '')}

    【完整设定参数】
    {selections_text}

    【输出要求】
    - 输出一个 JSON 对象，包含两个字段：title 和 content。
    - title：故事标题，5-10个字，简洁有力，能概括核心。
    - content：故事口播稿正文，直接输出，无额外说明，语言生动，适合视频旁白。
    - 全文约{str(self.selections.get('目标时长', 5))}分钟的朗读量（约每分钟200字），严格按照目标时长控制篇幅。

    输出格式示例：
    {{"title": "废土花开", "content": "在荒芜的废土上，熊猫阿六..."}}
    """

        # 禁用生成按钮
        if hasattr(self, 'gen_button'):
            self.gen_button.config(state='disabled', text="生成中...")

        def do_generate():
            try:
                # 确保工作目录存在（按项目命名规则）
                story_title = self.title_var.get().strip() or "未命名故事"
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                folder_name = f"{story_title}_{timestamp}"
                base_output = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
                work_dir = os.path.join(base_output, folder_name)
                os.makedirs(work_dir, exist_ok=True)
                # 将工作目录保存到实例变量，供后续使用
                self.current_work_dir = work_dir
                if self.app:
                    self.app.work_dir = work_dir

                # 打印传入 AI 的完整设定（不保存文件）
                selections_json = json.dumps(self.selections, ensure_ascii=False, indent=2)
                print("\n" + "="*60)
                print("传入 AI 的完整设定：")
                print(selections_json)
                print("="*60 + "\n")

                # 调用 AI 生成故事
                print("Prompt type:", type(prompt))
                print("Prompt first 200 chars:", prompt[:200])
                from utils.ai_utils import call_deepseek
                result = call_deepseek(prompt, temperature=0.7, max_tokens=3000)
                result = result.strip()
                if result.startswith("```json"):
                    result = result[7:]
                if result.startswith("```"):
                    result = result[3:]
                if result.endswith("```"):
                    result = result[:-3]
                result = result.strip()
                data = json.loads(result)
                title = data.get("title", "未命名故事")
                content = data.get("content", "")
                self.win.after(0, lambda: self._on_generate_success(title, content))
            except Exception as e:
                self.win.after(0, lambda: self._on_generate_error(str(e)))

        threading.Thread(target=do_generate, daemon=True).start()

    def _on_generate_success(self, title, content):
        """生成成功后的UI更新"""
        # 先更新UI和按钮状态
        if hasattr(self, 'gen_button'):
            self.gen_button.config(state='normal', text="生成故事")
        print("=" * 60)
        print("生成的故事标题：", title)
        print("生成的故事内容：")
        print(content)
        print("=" * 60)

        # 自动填入主界面（仅当 app 存在且有一键成片模式时）
        if self.app:
            if hasattr(self.app, 'toolbar') and hasattr(self.app.toolbar, 'title_entry'):
                self.app.toolbar.title_entry.delete(0, tk.END)
                self.app.toolbar.title_entry.insert(0, title)
            if hasattr(self.app, 'simple_mode') and hasattr(self.app.simple_mode, 'title_entry'):
                self.app.simple_mode.title_entry.delete(0, tk.END)
                self.app.simple_mode.title_entry.insert(0, title)
            if hasattr(self.app, 'simple_mode') and hasattr(self.app.simple_mode, 'story_tab'):
                self.app.simple_mode.story_tab.text_widget.delete('1.0', 'end')
                self.app.simple_mode.story_tab.text_widget.insert('1.0', content)

        # 保存故事和元数据到工作目录
        if hasattr(self, 'current_work_dir') and self.current_work_dir:
            story_path = os.path.join(self.current_work_dir, "story.txt")
            with open(story_path, 'w', encoding='utf-8') as f:
                f.write(content)
            meta_path = os.path.join(self.current_work_dir, "metadata.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(self.selections, f, ensure_ascii=False, indent=2)
            print(f"故事已保存至：{story_path}")
            print(f"元数据已保存至：{meta_path}")

        # 调用回调（如果存在）
        if self.on_finish:
            self.on_finish(content, self.selections)

        tk.messagebox.showinfo("成功", "故事生成完成，已填入一键成片的故事标签页")
        self.win.destroy()

    def _on_generate_error(self, error_msg):
        """生成失败后的UI更新"""
        if hasattr(self, 'gen_button'):
            self.gen_button.config(state='normal', text="生成故事")
        tk.messagebox.showerror("错误", f"生成故事失败：{error_msg}")