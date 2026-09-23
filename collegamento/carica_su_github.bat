@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install --quiet google-auth-oauthlib google-api-python-client requests pynacl
python carica_su_github.py
