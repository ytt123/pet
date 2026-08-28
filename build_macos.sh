#!/usr/bin/env bash
# ============================================================
#  蜘蛛侠桌宠 - macOS 打包脚本
#  在 macOS 上运行:  bash build_macos.sh
#  产物:  dist/SpiderPet.app  (拖进「应用程序」即可, 双击运行)
# ============================================================
set -e
cd "$(dirname "$0")"

echo "[1/2] 安装依赖 (PySide6 + PyInstaller) ..."
python3 -m pip install --upgrade pip
python3 -m pip install PySide6 pyinstaller

echo "[2/2] 开始打包 ..."
python3 -m PyInstaller --noconfirm --clean pet.spec

echo
echo "============================================================"
echo " 完成!  应用在:  dist/SpiderPet.app"
echo " 首次打开若提示「无法验证开发者」: 右键 App -> 打开 -> 打开,"
echo " 或到 系统设置 > 隐私与安全性 点「仍要打开」。"
echo "============================================================"
