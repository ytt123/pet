@echo off
REM ============================================================
REM  蜘蛛侠桌宠 - Windows 打包脚本
REM  在【Windows 电脑】上双击本文件即可生成 dist\SpiderPet.exe
REM  前提: 已安装 Python 3.10+ (勾选 "Add Python to PATH")
REM  下载: https://www.python.org/downloads/windows/
REM ============================================================
setlocal
cd /d "%~dp0"

echo [1/3] 升级 pip ...
python -m pip install --upgrade pip
if errorlevel 1 goto :err

echo [2/3] 安装依赖 (PySide6 + PyInstaller) ...
python -m pip install PySide6 pyinstaller
if errorlevel 1 goto :err

echo [3/3] 开始打包 ...
python -m PyInstaller --noconfirm --clean pet.spec
if errorlevel 1 goto :err

echo.
echo ============================================================
echo  完成!  单文件程序在:  dist\SpiderPet.exe
echo  双击即可运行;右键桌宠 -^> 退出 关闭。
echo ============================================================
pause
exit /b 0

:err
echo.
echo [出错] 打包失败,请把上面的红色/错误信息发给我。
echo 常见原因: 没装 Python、或没勾选 Add Python to PATH。
pause
exit /b 1
