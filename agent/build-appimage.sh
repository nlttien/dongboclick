#!/usr/bin/env bash
# ==================================================================
#  Đóng gói agent thành AppImage:  dist/ClickDongBo-x86_64.AppImage
#  Yêu cầu: pip install -r requirements.txt  (đã có pyinstaller)
#  appimagetool được tải tự động nếu chưa có (đặt APPIMAGETOOL=/đường/dẫn để dùng bản có sẵn).
#  Muốn AppImage chạy được trên distro cũ: build trên distro cũ (CI dùng Ubuntu 22.04).
# ==================================================================
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
ARCH="$(uname -m)"
OUT="dist/ClickDongBo-${ARCH}.AppImage"

echo "[1/3] PyInstaller (onedir) ..."
rm -rf build/onedir dist/onedir
CLICKDONGBO_ONEDIR=1 "$PY" -m PyInstaller --noconfirm --distpath dist/onedir --workpath build/onedir clickdongbo-agent.spec

echo "[2/3] Dựng AppDir ..."
APPDIR=build/AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/clickdongbo"
cp -a dist/onedir/clickdongbo-agent "$APPDIR/usr/lib/"
cp appimage/AppRun "$APPDIR/AppRun"
cp appimage/clickdongbo-agent.desktop appimage/clickdongbo-agent.svg "$APPDIR/"
ln -sf clickdongbo-agent.svg "$APPDIR/.DirIcon"
cp setup-linux.sh config.json "$APPDIR/usr/share/clickdongbo/"
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/share/clickdongbo/setup-linux.sh"

echo "[3/3] appimagetool ..."
TOOL="${APPIMAGETOOL:-build/appimagetool-${ARCH}.AppImage}"
if [ ! -x "$TOOL" ]; then
  curl -fL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$TOOL"
fi
mkdir -p dist
# APPIMAGE_EXTRACT_AND_RUN: chạy được cả khi máy build không có FUSE (vd CI, container)
APPIMAGE_EXTRACT_AND_RUN=1 ARCH="$ARCH" "$TOOL" --no-appstream "$APPDIR" "$OUT"

echo
echo "XONG: $OUT"
echo "  Chạy:        ./$(basename "$OUT")             (config.json tạo cạnh file .AppImage)"
echo "  Cấp quyền:   ./$(basename "$OUT") --setup     (1 lần, rồi đăng xuất/đăng nhập lại)"
