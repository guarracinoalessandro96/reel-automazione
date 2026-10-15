@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install --quiet requests pynacl
python collega_telegram.py
