#!/usr/bin/env bash
# ==================================================================
#  Cấp quyền 1 lần cho agent trên Linux (X11 + Wayland):
#   - đọc bàn phím  : /dev/input/event*  (nhóm "input")
#   - bấm phím ảo   : /dev/uinput        (module uinput + udev rule cho nhóm "input")
#  Chạy:  sudo ./setup-linux.sh   rồi ĐĂNG XUẤT / đăng nhập lại.
#
#  Lưu ý: user trong nhóm "input" đọc được MỌI phím gõ trên máy (kể cả mật khẩu).
#  Chỉ thêm tài khoản bạn tin cậy.
# ==================================================================
set -e

if [ "$(id -u)" -ne 0 ]; then
  echo "Cần quyền root:  sudo $0"
  exit 1
fi

TARGET_USER="${1:-$SUDO_USER}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
  echo "Không xác định được user. Chạy:  sudo $0 <ten_user>"
  exit 1
fi

echo "[1/3] Nạp module uinput (và tự nạp khi khởi động)"
modprobe uinput
echo uinput > /etc/modules-load.d/clickdongbo-uinput.conf

echo "[2/3] Cho nhóm 'input' ghi /dev/uinput"
cat > /etc/udev/rules.d/99-clickdongbo-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
udevadm control --reload-rules
udevadm trigger --sysname-match=uinput || true

echo "[3/3] Thêm '$TARGET_USER' vào nhóm 'input'"
usermod -aG input "$TARGET_USER"

echo
echo "XONG. Đăng xuất rồi đăng nhập lại (hoặc reboot) để nhóm 'input' có hiệu lực."
echo "Kiểm tra sau khi đăng nhập:  id | grep input  &&  ls -l /dev/uinput"
