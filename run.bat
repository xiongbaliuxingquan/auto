@echo off
cd /d %~dp0
call venv311\Scripts\activate
echo 正在清理 core 文件夹中的旧日志...
if exist core\ai_raw_responses.log del /f /q core\ai_raw_responses.log
if exist core\api_stats.log del /f /q core\api_stats.log
echo 正在启动GUI...
python gui_launcher.py
pause