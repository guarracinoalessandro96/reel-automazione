@echo off
cd /d "%~dp0tiktok_app"
python -m pip install --quiet requests
python server.py
pause
