@echo off
chcp 65001 >nul
echo ===================================
echo   重庆二手房分析系统 - 一键启动
echo ===================================
echo.

REM 切到项目目录
cd /d "%~dp0"

REM 杀掉已有的 python 进程（避免端口占用）
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *web*app.py*" 2>nul

REM 启动 Flask 后台
start "Flask Web" /B python web/app.py

REM 等 3 秒启动
timeout /t 3 /nobreak >nul

REM 打开总控面板
start "" "http://localhost:5000/control"

echo.
echo ✅ 已启动，浏览器已打开
echo 📍 关闭服务请到总控面板点"⛔ 一键关闭"
pause