# -*- mode: python ; coding: utf-8 -*-
"""跨平台打包配置。
- macOS  : 生成 dist/SpiderPet.app (窗口程序, 无 Dock 图标, 靠右键菜单退出)
- Windows: 生成 dist/SpiderPet.exe (单文件, 双击运行, 无控制台窗口)

打包命令 (在对应系统上执行):
    python -m PyInstaller pet.spec
"""
import sys

APP_NAME = "SpiderPet"

a = Analysis(
    ["pet.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],   # 把动画帧一起打进去
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    # macOS: onedir + .app 包
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name=APP_NAME,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,        # universal2 (随解释器)
    )
    coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=None,
        bundle_identifier="com.example.spiderpet",
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": "蜘蛛侠桌宠",
            "NSHighResolutionCapable": True,
            # 桌宠:不在 Dock 显示图标,右键菜单退出
            "LSUIElement": True,
        },
    )
else:
    # Windows / Linux: 单文件 exe
    # 把 binaries/datas 直接塞进 EXE => 单文件模式
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name=APP_NAME,
        console=False,           # 不弹黑色命令行窗口
        disable_windowed_traceback=False,
    )
