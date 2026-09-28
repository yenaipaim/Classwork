@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Pet Hospital AI System
cd /d "%~dp0"
python start.py
pause
