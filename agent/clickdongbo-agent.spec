# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec cho agent (dùng bởi build.bat, build.sh, build-appimage.sh và CI build-exe.yml).
# Mặc định ra 1 file duy nhất: dist/clickdongbo-agent(.exe); config.json được copy ra cạnh file sau khi build.
# CLICKDONGBO_ONEDIR=1 -> ra thư mục dist/clickdongbo-agent/ (dùng cho AppImage: khởi động nhanh,
# không phải giải nén vào /tmp mỗi lần chạy).

# pynput chọn backend theo OS lúc chạy (import động) -> PyInstaller không tự thấy, phải khai báo.
import os
import sys

if sys.platform == 'win32':
    hidden = ['pynput.keyboard._win32', 'pynput.mouse._win32', 'pynput._util.win32']
elif sys.platform == 'darwin':
    hidden = ['pynput.keyboard._darwin', 'pynput.mouse._darwin', 'pynput._util.darwin']
else:
    # Linux dùng evdev (linux_input.py); pynput xorg chỉ khi config "backend": "pynput"
    hidden = ['linux_input', 'evdev', 'pynput.keyboard._xorg', 'pynput.mouse._xorg', 'pynput._util.xorg']

hidden += ['ui_server']

a = Analysis(
    ['agent.py'],
    pathex=[],
    binaries=[],
    datas=[('ui.html', '.')],  # trang giao diện web (ui_server đọc qua sys._MEIPASS)
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

if os.environ.get('CLICKDONGBO_ONEDIR'):
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='clickdongbo-agent',
        debug=False,
        strip=False,
        upx=False,
        console=True,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='clickdongbo-agent')
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='clickdongbo-agent',
        debug=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=True,  # giữ cửa sổ console để xem log gửi/nhận phím
    )
