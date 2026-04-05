@echo off
chcp 65001 >nul
echo ================================================
echo   启动 Edge 远程调试模式
echo ================================================
echo.

:: 先关闭所有 Edge 进程（调试模式必须无其他Edge实例）
taskkill /f /im msedge.exe >nul 2>&1
timeout /t 1 /nobreak >nul

set EDGE1="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
set EDGE2="C:\Program Files\Microsoft\Edge\Application\msedge.exe"

if exist %EDGE1% (
    start "" %EDGE1% --remote-debugging-port=9222 --no-first-run https://x.com/login
    goto :done
)
if exist %EDGE2% (
    start "" %EDGE2% --remote-debugging-port=9222 --no-first-run https://x.com/login
    goto :done
)

echo 未找到 Edge，请手动运行：
echo msedge.exe --remote-debugging-port=9222 https://x.com/login
pause
exit /b

:done
echo Edge 已启动（调试端口：9222）
echo 请在打开的 Edge 窗口中登录 X，然后回到 X Tool 点击【开始运行】
echo.
echo 此窗口可以关闭。
timeout /t 3 /nobreak >nul