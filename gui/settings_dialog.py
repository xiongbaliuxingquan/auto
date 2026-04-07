# gui/settings_dialog.py
import tkinter as tk
import os
from tkinter import ttk, messagebox, filedialog
from utils import config_manager

def show_settings(parent):
    current = config_manager.load_user_settings()
    # 加载 API 配置
    api_key, model = config_manager.load_config()
    
    win = tk.Toplevel(parent)
    win.title("参数设置")
    win.geometry("650x550")  # 增加高度
    win.update_idletasks()
    x = (win.winfo_screenwidth() // 2) - (win.winfo_width() // 2)
    y = (win.winfo_screenheight() // 2) - (win.winfo_height() // 2)
    win.geometry(f"+{x}+{y}")
    win.transient(parent)
    win.grab_set()

    # 变量绑定
    api_key_var = tk.StringVar(value=api_key or "")
    model_var = tk.StringVar(value=model or "deepseek-chat")
    threshold_var = tk.IntVar(value=current.get("GLOBAL_THRESHOLD", 2000))
    chunk_var = tk.IntVar(value=current.get("CHUNK_SIZE", 300))
    workers_var = tk.IntVar(value=current.get("MAX_WORKERS", 8))
    api_url_var = tk.StringVar(value=current.get("COMFYUI_API_URL", ""))
    video_dir_var = tk.StringVar(value=current.get("VIDEO_OUTPUT_BASE_DIR", "D:/001视频提取"))
    output_root_var = tk.StringVar(value=current.get("OUTPUT_ROOT_DIR", config_manager.BASE_DIR))
    timeout_var = tk.IntVar(value=current.get("API_TIMEOUT", 120))
    max_retries_var = tk.IntVar(value=current.get("MAX_RETRIES", 3))
    retry_delay_var = tk.IntVar(value=current.get("RETRY_DELAY", 5))
    fuzzy_threshold_var = tk.IntVar(value=current.get("FUZZY_MATCH_THRESHOLD", 80))
    batch_size_var = tk.IntVar(value=current.get("BATCH_SIZE", 1))

    row = 0
    # API Key
    tk.Label(win, text="API Key：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=api_key_var, width=50, show='*').grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    row += 1
    
    # 模型
    tk.Label(win, text="模型：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    ttk.Combobox(win, textvariable=model_var, values=["deepseek-chat", "gpt-4"], state='readonly', width=30).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1
    
    ttk.Separator(win, orient='horizontal').grid(row=row, column=0, columnspan=2, sticky='ew', pady=10)
    row += 1

    # 原有设置项
    tk.Label(win, text="启用并发处理的文本阈值（字符数）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=threshold_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="每个块的最大字符数：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=chunk_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="最大并发线程数：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=workers_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="分镜处理批次大小（镜头数）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=batch_size_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="ComfyUI API 地址：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=api_url_var, width=60).grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    row += 1

    tk.Label(win, text="字幕模糊匹配阈值（70-90）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=fuzzy_threshold_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="视频输出根目录：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    entry_video = tk.Entry(win, textvariable=video_dir_var, width=50)
    entry_video.grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    tk.Button(win, text="浏览", command=lambda: browse_folder(video_dir_var)).grid(row=row, column=2, padx=5)
    row += 1

    tk.Label(win, text="中间文件输出根目录：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    entry_root = tk.Entry(win, textvariable=output_root_var, width=50)
    entry_root.grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    tk.Button(win, text="浏览", command=lambda: browse_folder(output_root_var)).grid(row=row, column=2, padx=5)
    row += 1

    tk.Label(win, text="API 超时时间（秒）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=timeout_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="最大重试次数：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=max_retries_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    tk.Label(win, text="重试间隔（秒）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=retry_delay_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    def browse_folder(var):
        folder = filedialog.askdirectory(title="选择输出根目录")
        if folder:
            var.set(folder)

    def save():
        # 保存 API 配置
        new_api_key = api_key_var.get().strip()
        new_model = model_var.get().strip()
        config_manager.save_config(new_api_key, new_model)
        # 更新环境变量
        os.environ.pop('DEEPSEEK_API_KEY', None)
        if new_api_key:
            os.environ['DEEPSEEK_API_KEY'] = new_api_key
        # 更新 app 中的变量（如果存在）
        if hasattr(win, 'master') and hasattr(win.master, 'api_key'):
            win.master.api_key = new_api_key
            win.master.model = new_model
        
        # 保存其他用户设置
        new_settings = {
            "GLOBAL_THRESHOLD": threshold_var.get(),
            "CHUNK_SIZE": chunk_var.get(),
            "MAX_WORKERS": workers_var.get(),
            "COMFYUI_API_URL": api_url_var.get().strip(),
            "VIDEO_OUTPUT_BASE_DIR": video_dir_var.get().strip(),
            "OUTPUT_ROOT_DIR": output_root_var.get().strip(),
            "MAX_RETRIES": max_retries_var.get(),
            "RETRY_DELAY": retry_delay_var.get(),
            "FUZZY_MATCH_THRESHOLD": fuzzy_threshold_var.get(),
            "BATCH_SIZE": batch_size_var.get(),
            "API_TIMEOUT": timeout_var.get()
        }
        try:
            config_manager.save_user_settings(new_settings)
            messagebox.showinfo("成功", "参数已保存，将在下次运行时生效。")
            win.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    btn_frame = tk.Frame(win)
    btn_frame.grid(row=row, column=0, columnspan=3, pady=10)
    tk.Button(btn_frame, text="保存", command=save, width=10).pack(side='left', padx=5)
    tk.Button(btn_frame, text="取消", command=win.destroy, width=10).pack(side='left', padx=5)

    win.columnconfigure(1, weight=1)