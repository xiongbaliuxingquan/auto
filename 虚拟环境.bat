@echo off
cd /d %~dp0
call venv311\Scripts\activate
echo 已进入 Python 3.11 虚拟环境，您可以手动运行命令。
cmd /k