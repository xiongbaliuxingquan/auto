# gui/story_wizard.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import re

from utils.ai_utils import call_deepseek


class StoryWizard:
    def __init__(self, parent, app, on_finish):
        self.parent = parent
        self.app = app
        self.on_finish = on_finish  # 回调函数，接收生成的口播稿文本和metadata
        self.win = tk.Toplevel(parent)
        self.win.title("故事创作向导")
        self.win.geometry("600x500")
        self.win.transient(parent)
        self.win.grab_set()
        self.win.protocol("WM_DELETE_WINDOW", self.cancel)
        self.pending_metadata = None   # 存储智能导入的解析结果

        # 窗口居中
        screen_width = self.win.winfo_screenwidth()
        screen_height = self.win.winfo_screenheight()
        win_width = 600
        win_height = 500
        x = (screen_width - win_width) // 2
        y = (screen_height - win_height) // 2
        self.win.geometry(f"{win_width}x{win_height}+{x}+{y}")

        # 存储答案的字典
        self.answers = {}

        # 当前页码 (0,1,2)
        self.current_page = 0

        self.create_widgets()

        # 创建三个页面的 Frame（但只显示第一个）
        self.page1_frame = ttk.Frame(self.content_frame)
        self.page2_frame = ttk.Frame(self.content_frame)
        self.page3_frame = ttk.Frame(self.content_frame)
        self.create_page1(self.page1_frame)
        self.create_page2(self.page2_frame)
        self.create_page3(self.page3_frame)

        self.show_page(0)

    # ------------------------------------------------------------
    # 智能导入相关方法
    # ------------------------------------------------------------
    def _parse_idea_to_metadata(self, idea_text):
        """调用AI解析一句话需求，返回metadata字典"""
        prompt = f"""
你是一个故事创作助手。请根据用户的一句话需求，提取以下信息，输出一个 JSON 对象。
如果某项信息无法从需求中推断，则输出 null。

用户需求：{idea_text}

输出 JSON 格式如下：
{{
    "form": "2D动画|3D动画|真人实拍|其他",
    "worldview": "现实世界|历史背景|奇幻架空|科幻未来|其他",
    "emotion": "温馨治愈|热血励志|悬疑烧脑|幽默喜剧|伤感悲剧|其他",
    "style_detail": "宫崎骏|新海诚|中国水墨|迪士尼|皮克斯|写实CG|赛博朋克|电影质感|纪录片风格|网剧质感|文艺片|其他",
    "era_detail": "秦朝|唐朝|宋朝|明朝|民国|魔法|龙|蒸汽朋克|神话|赛博朋克|太空歌剧|后启示录|现代|近未来|过去十年|其他",
    "core": "一场奇遇|一段旅程|一次成长|一个秘密|其他",
    "duration_minutes": 数字（分钟）,
    "gender": "男|女|不限",
    "age": "少年|青年|中年|老年|不限",
    "personality": ["热血","冷静","内向","幽默","沉稳"],
    "plots": ["浪漫邂逅","逆境成长","团队合作","复仇反转","拯救世界"],
    "tone": "先抑后扬|一路热血|温馨治愈|虐心伤感|幽默搞笑|其他",
    "special": ["加入动物角色","加入旁白/诗歌","加入音乐元素","加入科幻设定"]
}}
注意：
- 风格细化(style_detail)要根据形式(form)来推断合理值。
- 时代背景(era_detail)要根据世界观(worldview)来推断。
- 如果用户提到了具体风格如“宫崎骏”，则 form 应为“2D动画”，style_detail 为“宫崎骏”。
- 如果用户提到了“迪士尼”，则 form 应为“2D动画”或“3D动画”，style_detail 为“迪士尼”。
- 时长单位是分钟，如“1分钟”则输出 1。
- 只输出 JSON，不要有任何额外文字。
"""
        try:
            result = call_deepseek(prompt, temperature=0.3, max_tokens=2000)
            # 清洗可能的 markdown 代码块
            result = result.strip()
            if result.startswith("```json"):
                result = result[7:]
            if result.startswith("```"):
                result = result[3:]
            if result.endswith("```"):
                result = result[:-3]
            result = result.strip()
            metadata = json.loads(result)
            return metadata
        except Exception as e:
            raise Exception(f"AI解析失败: {e}\n原始返回: {result[:200]}")

    def import_idea(self):
        idea = self.idea_entry.get().strip()
        if not idea:
            messagebox.showwarning("提示", "请输入一句话需求")
            return
        self.user_idea = idea
        self.import_btn.config(state='disabled', text="解析中...")

        def task():
            try:
                metadata = self._parse_idea_to_metadata(idea)
                # 保存到 pending，等进入第二页时再应用
                self.pending_metadata = metadata
                self.win.after(0, lambda: self._apply_first_page(metadata))
                self.win.after(0, lambda: messagebox.showinfo("成功", "智能导入完成，请检查各页选项"))
            except Exception as e:
                self.win.after(0, lambda: messagebox.showerror("错误", f"解析失败：{e}"))
            finally:
                self.win.after(0, lambda: self.import_btn.config(state='normal', text="智能导入"))

        threading.Thread(target=task, daemon=True).start()

    def _apply_first_page(self, meta):
        """只设置第一页的控件，第二页等进入时再设"""
        if meta.get('form'):
            self.form_var.set(meta['form'])
            self._on_form_change()
        if meta.get('worldview'):
            self.world_var.set(meta['worldview'])
            self._on_world_change()
        if meta.get('emotion'):
            self.emotion_var.set(meta['emotion'])
            self._on_emotion_change()
        # 不刷新第二页，等进入第二页时再处理

    def _set_page2_values(self, meta):
        """设置第二页的控件值（在 refresh_page2 之后调用）"""
        if hasattr(self, 'style_var') and meta.get('style_detail'):
            # 检查该选项是否存在，若不存在则设为“其他”并填入输入框
            if self.style_var.get() != meta['style_detail']:
                # 尝试在下拉选项中找到该值
                found = False
                for widget in self.style_frame.winfo_children():
                    if isinstance(widget, ttk.Radiobutton) and widget.cget('text') == meta['style_detail']:
                        found = True
                        break
                if found:
                    self.style_var.set(meta['style_detail'])
                else:
                    self.style_var.set("其他")
                    if hasattr(self, 'style_other_entry') and self.style_other_entry:
                        self.style_other_entry.delete(0, tk.END)
                        self.style_other_entry.insert(0, meta['style_detail'])
        if hasattr(self, 'era_var') and meta.get('era_detail'):
            found = False
            for widget in self.era_frame.winfo_children():
                if isinstance(widget, ttk.Radiobutton) and widget.cget('text') == meta['era_detail']:
                    found = True
                    break
            if found:
                self.era_var.set(meta['era_detail'])
            else:
                self.era_var.set("其他")
                if hasattr(self, 'era_other_entry') and self.era_other_entry:
                    self.era_other_entry.delete(0, tk.END)
                    self.era_other_entry.insert(0, meta['era_detail'])
        if hasattr(self, 'core_var') and meta.get('core'):
            if meta['core'] in ["一场奇遇", "一段旅程", "一次成长", "一个秘密", "其他"]:
                self.core_var.set(meta['core'])
            else:
                self.core_var.set("其他")
                if hasattr(self, 'core_other_entry'):
                    self.core_other_entry.delete(0, tk.END)
                    self.core_other_entry.insert(0, meta['core'])
        print(f"[DEBUG] duration_minutes from meta: {meta.get('duration_minutes')}")
        if meta.get('duration_minutes') is not None:
            try:
                duration = int(meta['duration_minutes'])
                duration = max(1, min(10, duration))
                self.duration_var.set(duration)
                self.duration_label.config(text=f"{duration}分钟")
                print(f"[DEBUG] after set: {self.duration_var.get()}")
            except (ValueError, TypeError):
                pass

    def _set_page3_values(self, meta):
        """设置第三页的控件值"""
        if meta.get('gender'):
            self.gender_var.set(meta['gender'])
        if meta.get('age'):
            self.age_var.set(meta['age'])
        if meta.get('personality'):
            for trait in meta['personality']:
                if trait in self.traits_vars:
                    self.traits_vars[trait].set(True)
                elif trait.strip():
                    # 不在预设列表中的，填入“其他”输入框
                    current = self.trait_other_entry.get().strip()
                    if current:
                        self.trait_other_entry.insert(0, trait + "，" + current)
                    else:
                        self.trait_other_entry.insert(0, trait)
        if meta.get('plots'):
            for plot in meta['plots']:
                if plot in self.plot_vars:
                    self.plot_vars[plot].set(True)
                elif plot.strip():
                    current = self.plot_other_entry.get().strip()
                    if current:
                        self.plot_other_entry.insert(0, plot + "，" + current)
                    else:
                        self.plot_other_entry.insert(0, plot)
        if meta.get('tone'):
            if meta['tone'] in ["先抑后扬", "一路热血", "温馨治愈", "虐心伤感", "幽默搞笑", "其他"]:
                self.tone_var.set(meta['tone'])
            else:
                self.tone_var.set("其他")
                self.tone_other_entry.delete(0, tk.END)
                self.tone_other_entry.insert(0, meta['tone'])
        if meta.get('special'):
            for spec in meta['special']:
                if spec in self.special_vars:
                    self.special_vars[spec].set(True)
                elif spec.strip():
                    current = self.special_other_entry.get().strip()
                    if current:
                        self.special_other_entry.insert(0, spec + "，" + current)
                    else:
                        self.special_other_entry.insert(0, spec)

    # ------------------------------------------------------------
    # UI 创建
    # ------------------------------------------------------------
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

    # ------------------- 第一页 -------------------
    def create_page1(self, frame):
        # 智能导入区域
        idea_frame = ttk.Frame(frame)
        idea_frame.pack(fill='x', pady=5)
        ttk.Label(idea_frame, text="一句话需求：").pack(side='left')
        self.idea_entry = ttk.Entry(idea_frame, width=40)
        self.idea_entry.pack(side='left', padx=5, fill='x', expand=True)
        self.import_btn = ttk.Button(idea_frame, text="智能导入", command=self.import_idea)
        self.import_btn.pack(side='left')
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=5)

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
        self.form_var.trace('w', lambda *a: self._on_form_change())

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
        self.world_var.trace('w', lambda *a: self._on_world_change())

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
        self.emotion_var.trace('w', lambda *a: self._on_emotion_change())

    def _on_form_change(self):
        if self.form_var.get() == "其他":
            self.form_other_entry.config(state='normal')
        else:
            self.form_other_entry.config(state='disabled')

    def _on_world_change(self):
        if self.world_var.get() == "其他":
            self.world_other_entry.config(state='normal')
        else:
            self.world_other_entry.config(state='disabled')

    def _on_emotion_change(self):
        if self.emotion_var.get() == "其他":
            self.emotion_other_entry.config(state='normal')
        else:
            self.emotion_other_entry.config(state='disabled')

    # ------------------- 第二页 -------------------
    def create_page2(self, frame):
        self.page2_frame = frame
        # 内容动态生成，先占位，在 refresh_page2 中填充
        self.refresh_page2()

    def refresh_page2(self):
        """根据第一页的选择，重新生成第二页的内容"""
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
        self.style_frame = ttk.Frame(self.page2_frame)
        self.style_frame.pack(anchor='w', fill='x', pady=2)
        self.style_var = tk.StringVar()
        style_options = []
        if form == "真人实拍":
            style_options = ["电影质感", "纪录片风格", "网剧质感", "文艺片"]
        elif form == "2D动画":
            style_options = ["宫崎骏", "新海诚", "中国水墨", "迪士尼"]
        elif form == "3D动画":
            style_options = ["皮克斯", "写实CG", "赛博朋克"]
        else:
            style_options = ["其他"]
        for opt in style_options:
            rb = ttk.Radiobutton(self.style_frame, text=opt, variable=self.style_var, value=opt)
            rb.pack(side='left', padx=5)
        if "其他" in style_options or not style_options:
            self.style_other_entry = ttk.Entry(self.style_frame, width=20, state='normal')
            self.style_other_entry.pack(side='left', padx=5)
            self.style_var.set("其他")
        else:
            self.style_other_entry = None
            if style_options:
                self.style_var.set(style_options[0])

        # 2. 时代/背景细化
        ttk.Label(self.page2_frame, text="2. 时代/背景细化：").pack(anchor='w', pady=(5,0))
        self.era_frame = ttk.Frame(self.page2_frame)
        self.era_frame.pack(anchor='w', fill='x', pady=2)
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
            rb = ttk.Radiobutton(self.era_frame, text=opt, variable=self.era_var, value=opt)
            rb.pack(side='left', padx=5)
        if "其他" in era_options or not era_options:
            self.era_other_entry = ttk.Entry(self.era_frame, width=20, state='normal')
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

    # ------------------- 第三页 -------------------
    def create_page3(self, frame):
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

    # ------------------------------------------------------------
    # 页面切换与数据收集
    def show_page(self, page):
        # 隐藏所有页面
        self.page1_frame.pack_forget()
        self.page2_frame.pack_forget()
        self.page3_frame.pack_forget()
        
        if page == 0:
            self.page1_frame.pack(fill='both', expand=True)
        elif page == 1:
            # 刷新第二页
            self.refresh_page2()
            # 如果有待应用的 metadata，则设置值
            if self.pending_metadata:
                self._set_page2_values(self.pending_metadata)
                # 第三页也一并设置
                self._set_page3_values(self.pending_metadata)
                # 清空，避免重复应用
                self.pending_metadata = None
            self.page2_frame.pack(fill='both', expand=True)
        else:
            self.page3_frame.pack(fill='both', expand=True)

        # 更新标题和按钮...
        titles = ["第一步：宏观设定", "第二步：风格与时长", "第三步：细节设定"]
        self.title_label.config(text=titles[page])
        self.prev_btn.config(state='normal' if page > 0 else 'disabled')
        if page == 2:
            self.next_btn.config(text="完成")
        else:
            self.next_btn.config(text="下一步")
        self.current_page = page

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
            self.current_page = 1
            self.show_page(1)
        elif self.current_page == 1:
            # 收集第二页答案
            style = self.style_var.get()
            if style == "其他" and hasattr(self, 'style_other_entry') and self.style_other_entry:
                style = self.style_other_entry.get().strip()
                if not style:
                    messagebox.showwarning("提示", "请输入其他风格")
                    return
            era = self.era_var.get()
            if era == "其他" and hasattr(self, 'era_other_entry') and self.era_other_entry:
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
            self.current_page = 2
            self.show_page(2)
        elif self.current_page == 2:
            # 收集第三页答案
            gender = self.gender_var.get()
            age = self.age_var.get()
            traits = [t for t, var in self.traits_vars.items() if var.get()]
            other_trait = self.trait_other_entry.get().strip()
            if other_trait:
                traits.append(other_trait)
            plots = [p for p, var in self.plot_vars.items() if var.get()]
            other_plot = self.plot_other_entry.get().strip()
            if other_plot:
                plots.append(other_plot)
            tone = self.tone_var.get()
            if tone == "其他":
                tone = self.tone_other_entry.get().strip()
                if not tone:
                    messagebox.showwarning("提示", "请输入其他情绪走向")
                    return
            specials = [s for s, var in self.special_vars.items() if var.get()]
            other_special = self.special_other_entry.get().strip()
            if other_special:
                specials.append(other_special)

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

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.show_page(self.current_page)

    # ------------------------------------------------------------
    # 生成剧本
    def generate_script(self):
        """将答案拼成人设卡，调用 API 生成口播稿和标题"""
        user_idea = getattr(self, 'user_idea', '')
        preset = f"""
    你是一位专业的故事撰稿人。请根据以下要求生成一个完整的故事口播稿，并同时生成一个简洁有力的故事标题。

    【用户核心创意】（必须严格遵循，不得偏离）
    {user_idea}

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
    - 输出一个 JSON 对象，包含两个字段：title 和 content。
    - title：故事标题，5-10个字，简洁有力，能概括核心。
    - content：故事口播稿正文，直接输出，无额外说明，语言生动，适合视频旁白。
    - 全文约{self.answers.get("目标时长")}的朗读量（约每分钟200字），严格按照目标时长控制篇幅。

    输出格式示例：
    {{"title": "废土花开", "content": "在荒芜的废土上，熊猫阿六..."}}
    """

        metadata = {
            "形式": self.answers.get("形式"),
            "世界观": self.answers.get("世界观"),
            "情感基调": self.answers.get("情感基调"),
            "风格细化": self.answers.get("风格细化"),
            "时代背景": self.answers.get("时代背景"),
            "核心看点": self.answers.get("核心看点"),
            "目标时长": self.answers.get("目标时长"),
            "主角性别": self.answers.get("主角性别"),
            "主角年龄": self.answers.get("主角年龄"),
            "主角性格": self.answers.get("主角性格"),
            "关键情节": self.answers.get("关键情节"),
            "情绪走向": self.answers.get("情绪走向"),
            "特殊要求": self.answers.get("特殊要求")
        }

        self.app.log("高级向导：正在生成故事和标题，请稍候...")
        self.win.destroy()

        def task():
            from utils.ai_utils import call_deepseek
            try:
                result = call_deepseek(preset, temperature=0.7, max_tokens=3000)
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
                self.app.root.after(0, lambda: self._on_generation_done(title, content, metadata))
            except Exception as e:
                self.app.root.after(0, lambda: self._on_generation_error(e))

        threading.Thread(target=task, daemon=True).start()

    def _on_generation_done(self, title, script, metadata):
        # 设置主界面顶部的标题框
        self.app.toolbar.title_entry.delete(0, tk.END)
        self.app.toolbar.title_entry.insert(0, title)
        # 设置一键成片模式自己的标题输入框（重要！）
        if hasattr(self.app, 'simple_mode') and hasattr(self.app.simple_mode, 'title_entry'):
            self.app.simple_mode.title_entry.delete(0, tk.END)
            self.app.simple_mode.title_entry.insert(0, title)
        # 同时设置 app 的 story_title 变量（备用）
        self.app.story_title = title
        
        # 元数据注释部分不变...
        meta_lines = ["<!-- 元数据开始"]
        for k, v in metadata.items():
            if v and v != "无特殊" and v != "无":
                meta_lines.append(f"{k}：{v}")
        meta_lines.append("元数据结束 -->")
        meta_text = "\n".join(meta_lines) + "\n\n"
        full_script = meta_text + script
        self.app.log("高级向导：故事生成完成")
        try:
            self.on_finish(full_script, metadata)
        except Exception as e:
            self.app.log(f"高级向导回调失败: {e}")

    def _on_generation_error(self, e):
        self.app.log(f"高级向导：生成故事失败 - {e}")
        messagebox.showerror("错误", f"生成故事失败：{e}")

    def cancel(self):
        self.win.destroy()