```
自动化视频分镜生成系统/
│
├── gui_launcher.py                 # 主窗口启动与模式切换
├── concurrent_utils.py             # 并发处理工具
├── snapshot.py                     # 生成项目快照脚本
├── user_settings.json              # 用户设置（并发、API地址等）
├── workflow_config.json            # 工作流节点配置
├── input.json                      # 输入数据示例
├── gui_log.txt                     # GUI运行日志
├── import_log.txt                  # 导入日志
│
├── core/                            # 核心业务逻辑
│   ├── auto_split_deepseek.py       # AI生成分镜设计
│   ├── comfyui_manager.py           # ComfyUI视频生成管理
│   ├── extract_prompts.py           # 提取并翻译提示词
│   ├── generate_first_frame_prompts.py # 生成首帧提示词
│   ├── refine_shots_by_srt.py       # 根据字幕优化镜头
│   └── txt_to_json.py               # 原始文稿转结构化文本
│
├── examples/                         # 示例文件
│   ├── 更新记录.txt                  # 功能对照表
│   └── 测试.txt                      # 测试文稿示例
│
├── gui/                               # 界面层模块
│   ├── countdown_timer.py            # 倒计时器
│   ├── preset_manager.py             # 人设卡管理窗口
│   ├── prompt_editor.py              # 提示词编辑器
│   ├── settings_dialog.py            # 设置对话框
│   ├── shot_editor.py                # 镜头编辑器
│   ├── step_manager.py               # 步骤管理器
│   ├── ui_components.py              # 可复用UI组件
│   ├── workflow_executor.py          # 工作流执行器
│   ├── log_viewer.py                 # 大日志窗口
│   ├── simple_mode.py                # 一键成片模式界面
│   ├── standard_mode.py              # 标准模式界面
│   ├── top_toolbar.py                # 顶部工具栏
│   └── common_widgets.py             # 公共组件
│
├── parsers/                           # 文稿解析器
│   ├── ai_response_cleaner.py        # AI响应清洗
│   ├── ai_response_debug.json        # 调试用AI响应示例
│   ├── analysis_parser.py            # 文明结构解析器
│   ├── base_parser.py                # 解析器基类
│   ├── mime_parser.py                # 动画默剧解析器
│   └── story_parser.py               # 情感故事解析器
│
├── prompt_presets/                    # 人设卡预设（纯文本）
│   ├── civil_default.txt             # 文明结构默认人设卡
│   ├── emotional_default.txt         # 情感故事默认人设卡
│   ├── mime2.txt                     # 动画默剧备用
│   └── mime_default.txt              # 动画默剧默认人设卡
│
├── tools/ffmpeg/                      # ffmpeg工具
│   └── LICENSE.txt                    # 许可证文件
│
├── utils/                              # 工具函数库
│   ├── concurrent_utils.py            # 并发工具
│   ├── config.json                    # API配置
│   ├── config_manager.py              # 配置管理
│   ├── process_runner.py              # 进程运行器
│   ├── settings.py                    # 设置加载
│   ├── subtitle_utils.py              # 字幕解析工具
│   ├── system_doctor.py               # 系统医生
│   ├── translation_utils.py           # 翻译工具
│   ├── user_settings.json             # 用户设置
│   ├── error_logger.py                # 错误日志模块
│   ├── ai_utils.py                    # AI调用统一接口
│   ├── style_generator.py             # 风格人设卡生成
│   ├── story_to_script.py             # 故事转口播稿
│   └── extract_persona_scene.py       # 提取人物/场景
│
├── workflow_templates/                 # ComfyUI工作流模板
│   ├── LTX2.3文生API.json             # LTX2.3模板
│   └── video_wan2_2_14B_t2v.json      # WAN2.2模板
│
├── logs/                                # 运行日志目录
├── temp_uploads/                        # 字幕临时存放
└── results/                             # 项目输出目录
```