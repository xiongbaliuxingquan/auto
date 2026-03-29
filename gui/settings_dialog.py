import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from utils import config_manager

def show_settings(parent):
    current = config_manager.load_user_settings()
    win = tk.Toplevel(parent)
    win.title("参数设置")
    win.geometry("600x480")  # 适当增加高度
    win.transient(parent)
    win.grab_set()

    # 变量绑定
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
    # 0: 并发阈值
    tk.Label(win, text="启用并发处理的文本阈值（字符数）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=threshold_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # 1: 块大小
    tk.Label(win, text="每个块的最大字符数：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=chunk_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # 2: 最大并发线程数
    tk.Label(win, text="最大并发线程数：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=workers_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # AUTO文件每次并发处理分镜数
    tk.Label(win, text="分镜处理批次大小（镜头数）：").grid(row=4, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=batch_size_var, width=10).grid(row=4, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # 3: ComfyUI API 地址
    tk.Label(win, text="ComfyUI API 地址：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=api_url_var, width=60).grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    row += 1

    # 4: 字幕模糊匹配阈值
    tk.Label(win, text="字幕模糊匹配阈值（70-90）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=fuzzy_threshold_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # 5: 视频输出根目录
    tk.Label(win, text="视频输出根目录：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    entry_video = tk.Entry(win, textvariable=video_dir_var, width=50)
    entry_video.grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    tk.Button(win, text="浏览", command=lambda: browse_folder(video_dir_var)).grid(row=row, column=2, padx=5)
    row += 1

    # 6: 中间文件输出根目录
    tk.Label(win, text="中间文件输出根目录：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    entry_root = tk.Entry(win, textvariable=output_root_var, width=50)
    entry_root.grid(row=row, column=1, padx=5, pady=5, sticky='ew')
    tk.Button(win, text="浏览", command=lambda: browse_folder(output_root_var)).grid(row=row, column=2, padx=5)
    row += 1

    # 7: API超时时间
    tk.Label(win, text="API 超时时间（秒）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=timeout_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # 8: 最大重试次数
    tk.Label(win, text="最大重试次数：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=max_retries_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    # 9: 重试间隔（秒）
    tk.Label(win, text="重试间隔（秒）：").grid(row=row, column=0, padx=5, pady=5, sticky='w')
    tk.Entry(win, textvariable=retry_delay_var, width=10).grid(row=row, column=1, padx=5, pady=5, sticky='w')
    row += 1

    def browse_folder(var):
        folder = filedialog.askdirectory(title="选择输出根目录")
        if folder:
            var.set(folder)

    def save():
        new = {
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
            config_manager.save_user_settings(new)
            messagebox.showinfo("成功", "参数已保存，将在下次运行脚本时生效。")
            win.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    # 按钮行
    btn_frame = tk.Frame(win)
    btn_frame.grid(row=row, column=0, columnspan=3, pady=10)
    tk.Button(btn_frame, text="保存", command=save, width=10).pack(side='left', padx=5)
    tk.Button(btn_frame, text="取消", command=win.destroy, width=10).pack(side='left', padx=5)

    win.columnconfigure(1, weight=1)