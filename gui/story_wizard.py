# gui/story_wizard.py
import tkinter as tk
from tkinter import ttk, messagebox
import json

class StoryWizard:
    def __init__(self, parent, app, on_finish):
        self.parent = parent
        self.app = app
        self.on_finish = on_finish  # 回调函数，接收生成的口播稿文本
        self.win = tk.Toplevel(parent)
        self.win.title("故事创作向导")
        self.win.geometry("600x500")
        self.win.transient(parent)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self.cancel)

        # 存储答案的字典
        self.answers = {}

        # 当前页码 (0,1,2)
        self.current_page = 0
        self.pages = [self.create_page1, self.create_page2, self.create_page3]
        self.page_frames = []

        self.create_widgets()
        self.show_page(0)

    def create_widgets(self):
        # 顶部标题
        self.title_label = ttk.Label(self.win, text="第一步：宏观设定", font=('微软雅黑', 12, 'bold'))
        self.title_label.pack(pady=10)

        # 内容区域
        self.content_frame = ttk.Frame(self.win)
        self.content_frame.pack(fill='both', expand=True, padx=10, pady=5)

        # 底部按钮
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(pady=10)
        self.prev_btn = ttk.Button(btn_frame, text="上一步", command=self.prev_page, state='disabled')
        self.prev_btn.pack(side='left', padx=5)
        self.next_btn = ttk.Button(btn_frame, text="下一步", command=self.next_page)
        self.next_btn.pack(side='left', padx=5)
        self.cancel_btn = ttk.Button(btn_frame, text="取消", command=self.cancel)
        self.cancel_btn.pack(side='left', padx=5)

    def create_page1(self, frame):
        """第一页：宏观设定"""
        # 1. 形式
        ttk.Label(frame, text="1. 形式：").pack(anchor='w', pady=(5,0))
        self.form_var = tk.StringVar()
        form_frame = ttk.Frame(frame)
        form_frame.pack(anchor='w', fill='x', pady=2)
        options = ["真人实拍", "2D动画", "3D动画", "其他"]
        for opt in options:
            rb = ttk.Radiobutton(form_frame, text=opt, variable=self.form_var, value=opt)
            rb.pack(side='left', padx=5)
        self.form_other_entry = ttk.Entry(form_frame, width=20, state='disabled')
        self.form_other_entry.pack(side='left', padx=5)

        def on_form_change():
            if self.form_var.get() == "其他":
                self.form_other_entry.config(state='normal')
            else:
                self.form_other_entry.config(state='disabled')
        self.form_var.trace('w', lambda *a: on_form_change())

        # 2. 世界观
        ttk.Label(frame, text="2. 世界观：").pack(anchor='w', pady=(5,0))
        self.world_var = tk.StringVar()
        world_frame = ttk.Frame(frame)
        world_frame.pack(anchor='w', fill='x', pady=2)
        world_options = ["现实世界", "历史背景", "奇幻架空", "科幻未来", "其他"]
        for opt in world_options:
            rb = ttk.Radiobutton(world_frame, text=opt, variable=self.world_var, value=opt)
            rb.pack(side='left', padx=5)
        self.world_other_entry = ttk.Entry(world_frame, width=20, state='disabled')
        self.world_other_entry.pack(side='left', padx=5)

        def on_world_change():
            if self.world_var.get() == "其他":
                self.world_other_entry.config(state='normal')
            else:
                self.world_other_entry.config(state='disabled')
        self.world_var.trace('w', lambda *a: on_world_change())

        # 3. 情感基调
        ttk.Label(frame, text="3. 情感基调：").pack(anchor='w', pady=(5,0))
        self.emotion_var = tk.StringVar()
        emotion_frame = ttk.Frame(frame)
        emotion_frame.pack(anchor='w', fill='x', pady=2)
        emotion_options = ["温馨治愈", "热血励志", "悬疑烧脑", "幽默喜剧", "伤感悲剧", "其他"]
        for opt in emotion_options:
            rb = ttk.Radiobutton(emotion_frame, text=opt, variable=self.emotion_var, value=opt)
            rb.pack(side='left', padx=5)
        self.emotion_other_entry = ttk.Entry(emotion_frame, width=20, state='disabled')
        self.emotion_other_entry.pack(side='left', padx=5)

        def on_emotion_change():
            if self.emotion_var.get() == "其他":
                self.emotion_other_entry.config(state='normal')
            else:
                self.emotion_other_entry.config(state='disabled')
        self.emotion_var.trace('w', lambda *a: on_emotion_change())

    def create_page2(self, frame):
        """第二页：风格与时长（动态）"""
        # 动态创建内容，但先占位
        self.page2_frame = frame
        self.page2_widgets = {}  # 存储动态创建的变量
        self.refresh_page2()

    def refresh_page2(self):
        """根据第一轮答案刷新页面2"""
        # 清除原有内容
        for widget in self.page2_frame.winfo_children():
            widget.destroy()

        form = self.form_var.get()
        if form == "其他":
            form = self.form_other_entry.get().strip() or "其他"
        world = self.world_var.get()
        if world == "其他":
            world = self.world_other_entry.get().strip() or "其他"

        # 1. 风格细化
        ttk.Label(self.page2_frame, text="1. 风格细化：").pack(anchor='w', pady=(5,0))
        style_frame = ttk.Frame(self.page2_frame)
        style_frame.pack(anchor='w', fill='x', pady=2)
        self.style_var = tk.StringVar()
        style_options = []
        if form == "真人实拍":
            style_options = ["电影质感", "纪录片风格", "网剧质感", "文艺片"]
        elif form == "2D动画":
            style_options = ["宫崎骏", "新海诚", "中国水墨", "迪士尼"]
        elif form == "3D动画":
            style_options = ["皮克斯", "写实CG", "赛博朋克"]
        else:
            # 其他形式，显示输入框
            style_options = ["其他"]
        for opt in style_options:
            rb = ttk.Radiobutton(style_frame, text=opt, variable=self.style_var, value=opt)
            rb.pack(side='left', padx=5)
        if "其他" in style_options or not style_options:
            self.style_other_entry = ttk.Entry(style_frame, width=20, state='normal')
            self.style_other_entry.pack(side='left', padx=5)
            self.style_var.set("其他")
        else:
            self.style_other_entry = None
            # 默认选中第一个
            if style_options:
                self.style_var.set(style_options[0])

        # 2. 时代/背景细化
        ttk.Label(self.page2_frame, text="2. 时代/背景细化：").pack(anchor='w', pady=(5,0))
        era_frame = ttk.Frame(self.page2_frame)
        era_frame.pack(anchor='w', fill='x', pady=2)
        self.era_var = tk.StringVar()
        era_options = []
        if world == "历史背景":
            era_options = ["秦朝", "唐朝", "宋朝", "明朝", "民国"]
        elif world == "奇幻架空":
            era_options = ["魔法", "龙", "蒸汽朋克", "神话"]
        elif world == "科幻未来":
            era_options = ["赛博朋克", "太空歌剧", "后启示录"]
        elif world == "现实世界":
            era_options = ["现代", "近未来", "过去十年"]
        else:
            era_options = ["其他"]
        for opt in era_options:
            rb = ttk.Radiobutton(era_frame, text=opt, variable=self.era_var, value=opt)
            rb.pack(side='left', padx=5)
        if "其他" in era_options or not era_options:
            self.era_other_entry = ttk.Entry(era_frame, width=20, state='normal')
            self.era_other_entry.pack(side='left', padx=5)
            self.era_var.set("其他")
        else:
            self.era_other_entry = None
            if era_options:
                self.era_var.set(era_options[0])

        # 3. 核心看点
        ttk.Label(self.page2_frame, text="3. 核心看点：").pack(anchor='w', pady=(5,0))
        core_frame = ttk.Frame(self.page2_frame)
        core_frame.pack(anchor='w', fill='x', pady=2)
        self.core_var = tk.StringVar()
        core_options = ["一场奇遇", "一段旅程", "一次成长", "一个秘密", "其他"]
        for opt in core_options:
            rb = ttk.Radiobutton(core_frame, text=opt, variable=self.core_var, value=opt)
            rb.pack(side='left', padx=5)
        self.core_other_entry = ttk.Entry(core_frame, width=20, state='disabled')
        self.core_other_entry.pack(side='left', padx=5)

        def on_core_change():
            if self.core_var.get() == "其他":
                self.core_other_entry.config(state='normal')
            else:
                self.core_other_entry.config(state='disabled')
        self.core_var.trace('w', lambda *a: on_core_change())
        self.core_var.set(core_options[0])

        # 4. 目标时长
        ttk.Label(self.page2_frame, text="4. 目标时长（分钟）：").pack(anchor='w', pady=(5,0))
        self.duration_var = tk.IntVar(value=5)
        duration_scale = ttk.Scale(self.page2_frame, from_=1, to=10, orient='horizontal',
                                   variable=self.duration_var, length=300)
        duration_scale.pack(anchor='w', fill='x', pady=2)
        self.duration_label = ttk.Label(self.page2_frame, text="5分钟")
        self.duration_label.pack(anchor='w')
        def on_duration(*args):
            self.duration_label.config(text=f"{self.duration_var.get()}分钟")
        self.duration_var.trace('w', on_duration)

    def create_page3(self, frame):
        """第三页：细节设定"""
        # 1. 主角设定
        ttk.Label(frame, text="1. 主角设定：").pack(anchor='w', pady=(5,0))
        gender_frame = ttk.Frame(frame)
        gender_frame.pack(anchor='w', fill='x', pady=2)
        self.gender_var = tk.StringVar(value="不限")
        ttk.Radiobutton(gender_frame, text="男", variable=self.gender_var, value="男").pack(side='left')
        ttk.Radiobutton(gender_frame, text="女", variable=self.gender_var, value="女").pack(side='left')
        ttk.Radiobutton(gender_frame, text="不限", variable=self.gender_var, value="不限").pack(side='left')

        age_frame = ttk.Frame(frame)
        age_frame.pack(anchor='w', fill='x', pady=2)
        self.age_var = tk.StringVar(value="不限")
        ttk.Radiobutton(age_frame, text="少年", variable=self.age_var, value="少年").pack(side='left')
        ttk.Radiobutton(age_frame, text="青年", variable=self.age_var, value="青年").pack(side='left')
        ttk.Radiobutton(age_frame, text="中年", variable=self.age_var, value="中年").pack(side='left')
        ttk.Radiobutton(age_frame, text="老年", variable=self.age_var, value="老年").pack(side='left')
        ttk.Radiobutton(age_frame, text="不限", variable=self.age_var, value="不限").pack(side='left')

        ttk.Label(frame, text="性格（可多选）：").pack(anchor='w', pady=(5,0))
        self.traits_vars = {}
        traits_frame = ttk.Frame(frame)
        traits_frame.pack(anchor='w', fill='x', pady=2)
        traits = ["热血", "冷静", "内向", "幽默", "沉稳"]
        for t in traits:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(traits_frame, text=t, variable=var)
            cb.pack(side='left', padx=5)
            self.traits_vars[t] = var
        self.trait_other_entry = ttk.Entry(traits_frame, width=20)
        self.trait_other_entry.pack(side='left', padx=5)

        # 2. 关键情节
        ttk.Label(frame, text="2. 关键情节（可多选，最多3个）：").pack(anchor='w', pady=(5,0))
        self.plot_vars = {}
        plot_frame = ttk.Frame(frame)
        plot_frame.pack(anchor='w', fill='x', pady=2)
        plots = ["浪漫邂逅", "逆境成长", "团队合作", "复仇反转", "拯救世界"]
        for p in plots:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(plot_frame, text=p, variable=var)
            cb.pack(side='left', padx=5)
            self.plot_vars[p] = var
        self.plot_other_entry = ttk.Entry(plot_frame, width=20)
        self.plot_other_entry.pack(side='left', padx=5)

        # 3. 情绪走向
        ttk.Label(frame, text="3. 情绪走向：").pack(anchor='w', pady=(5,0))
        self.tone_var = tk.StringVar()
        tone_frame = ttk.Frame(frame)
        tone_frame.pack(anchor='w', fill='x', pady=2)
        tones = ["先抑后扬", "一路热血", "温馨治愈", "虐心伤感", "幽默搞笑", "其他"]
        for t in tones:
            rb = ttk.Radiobutton(tone_frame, text=t, variable=self.tone_var, value=t)
            rb.pack(side='left', padx=5)
        self.tone_other_entry = ttk.Entry(tone_frame, width=20, state='disabled')
        self.tone_other_entry.pack(side='left', padx=5)
        def on_tone_change():
            if self.tone_var.get() == "其他":
                self.tone_other_entry.config(state='normal')
            else:
                self.tone_other_entry.config(state='disabled')
        self.tone_var.trace('w', lambda *a: on_tone_change())
        self.tone_var.set(tones[0])

        # 4. 特殊要求
        ttk.Label(frame, text="4. 特殊要求（可多选）：").pack(anchor='w', pady=(5,0))
        self.special_vars = {}
        special_frame = ttk.Frame(frame)
        special_frame.pack(anchor='w', fill='x', pady=2)
        specials = ["加入动物角色", "加入旁白/诗歌", "加入音乐元素", "加入科幻设定"]
        for s in specials:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(special_frame, text=s, variable=var)
            cb.pack(side='left', padx=5)
            self.special_vars[s] = var
        self.special_other_entry = ttk.Entry(special_frame, width=20)
        self.special_other_entry.pack(side='left', padx=5)

    def show_page(self, page):
        # 销毁当前内容
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        # 创建新页面
        frame = ttk.Frame(self.content_frame)
        frame.pack(fill='both', expand=True)
        self.page_frames.append(frame)
        self.pages[page](frame)
        # 更新标题
        titles = ["第一步：宏观设定", "第二步：风格与时长", "第三步：细节设定"]
        self.title_label.config(text=titles[page])
        # 更新按钮状态
        self.prev_btn.config(state='normal' if page > 0 else 'disabled')
        if page == len(self.pages)-1:
            self.next_btn.config(text="完成")
        else:
            self.next_btn.config(text="下一步")

    def next_page(self):
        if self.current_page == 0:
            # 收集第一页答案
            form = self.form_var.get()
            if form == "其他":
                form = self.form_other_entry.get().strip()
                if not form:
                    messagebox.showwarning("提示", "请输入其他形式")
                    return
            world = self.world_var.get()
            if world == "其他":
                world = self.world_other_entry.get().strip()
                if not world:
                    messagebox.showwarning("提示", "请输入其他世界观")
                    return
            emotion = self.emotion_var.get()
            if emotion == "其他":
                emotion = self.emotion_other_entry.get().strip()
                if not emotion:
                    messagebox.showwarning("提示", "请输入其他情感基调")
                    return
            self.answers.update({
                "形式": form,
                "世界观": world,
                "情感基调": emotion
            })
        elif self.current_page == 1:
            # 收集第二页答案
            style = self.style_var.get()
            if style == "其他" and self.style_other_entry:
                style = self.style_other_entry.get().strip()
                if not style:
                    messagebox.showwarning("提示", "请输入其他风格")
                    return
            era = self.era_var.get()
            if era == "其他" and self.era_other_entry:
                era = self.era_other_entry.get().strip()
                if not era:
                    messagebox.showwarning("提示", "请输入其他时代/背景")
                    return
            core = self.core_var.get()
            if core == "其他":
                core = self.core_other_entry.get().strip()
                if not core:
                    messagebox.showwarning("提示", "请输入其他核心看点")
                    return
            duration = self.duration_var.get()
            self.answers.update({
                "风格细化": style,
                "时代背景": era,
                "核心看点": core,
                "目标时长": f"{duration}分钟"
            })
        elif self.current_page == 2:
            # 收集第三页答案
            gender = self.gender_var.get()
            age = self.age_var.get()
            traits = [t for t, var in self.traits_vars.items() if var.get()]
            if self.trait_other_entry.get().strip():
                traits.append(self.trait_other_entry.get().strip())
            plots = [p for p, var in self.plot_vars.items() if var.get()]
            if self.plot_other_entry.get().strip():
                plots.append(self.plot_other_entry.get().strip())
            tone = self.tone_var.get()
            if tone == "其他":
                tone = self.tone_other_entry.get().strip()
                if not tone:
                    messagebox.showwarning("提示", "请输入其他情绪走向")
                    return
            specials = [s for s, var in self.special_vars.items() if var.get()]
            if self.special_other_entry.get().strip():
                specials.append(self.special_other_entry.get().strip())

            self.answers.update({
                "主角性别": gender,
                "主角年龄": age,
                "主角性格": "、".join(traits) if traits else "无特殊",
                "关键情节": "、".join(plots) if plots else "无",
                "情绪走向": tone,
                "特殊要求": "、".join(specials) if specials else "无"
            })
            # 生成人设卡并调用 API
            self.generate_script()
            return

        self.current_page += 1
        self.show_page(self.current_page)

    def prev_page(self):
        self.current_page -= 1
        self.show_page(self.current_page)

    def generate_script(self):
        """将答案拼成人设卡，调用 API 生成口播稿"""
        # 构建人设卡文本
        preset = f"""
你是一位专业的故事撰稿人。请根据以下要求生成一个完整的故事口播稿，用于视频制作。

【主题】{self.app.toolbar.title_entry.get() or "未提供主题"}

【创作要求】
- 形式：{self.answers.get("形式")}
- 世界观：{self.answers.get("世界观")}
- 情感基调：{self.answers.get("情感基调")}
- 风格细化：{self.answers.get("风格细化")}
- 时代背景：{self.answers.get("时代背景")}
- 核心看点：{self.answers.get("核心看点")}
- 目标时长：{self.answers.get("目标时长")}
- 主角性别：{self.answers.get("主角性别")}
- 主角年龄：{self.answers.get("主角年龄")}
- 主角性格：{self.answers.get("主角性格")}
- 关键情节：{self.answers.get("关键情节")}
- 情绪走向：{self.answers.get("情绪走向")}
- 特殊要求：{self.answers.get("特殊要求")}

【输出要求】
- 口播稿应直接输出，无额外说明。
- 开篇要有引人入胜的引子，结尾要有回味。
- 语言生动，适合视频旁白。
- 全文约{self.answers.get("目标时长")}的朗读量（约每分钟200字）。
"""
        self.win.destroy()
        # 调用现有的故事生成函数
        from utils.story_to_script import generate_script
        try:
            script = generate_script(preset, "")
            self.on_finish(script)
        except Exception as e:
            messagebox.showerror("错误", f"生成故事失败：{e}")

    def cancel(self):
        self.win.destroy()