# 🔑 Keystroke Sync Agent (đồng bộ gõ phím, KHÔNG cần web)

Agent chạy nền trên **mỗi máy**. Khi bạn bấm phím (vd `R`) trên máy 1 → máy 2 **tự động bấm phím đó ở cấp hệ điều hành** (toàn cục, mọi ứng dụng). Không cần mở trình duyệt.

```
[Máy 1: agent.py] --ws--> [Server Ubuntu: server.js] --ws--> [Máy 2: agent.py]
```

---

## 1. Yêu cầu
- **Python 3.8+** (tải tại https://python.org ; khi cài nhớ tick *Add Python to PATH*).
- Server `server.js` đã chạy trên Ubuntu (xem README gốc).

## 2. Cài đặt thư viện
Trong thư mục `agent/`:
```bash
pip install -r requirements.txt
```
> - **Linux**: thư viện `evdev` build từ nguồn → cần `gcc` + header Python:
>   Ubuntu/Debian `sudo apt install gcc python3-dev` · Fedora/Nobara `sudo dnf install gcc python3-devel`.
>   Sau đó cấp quyền 1 lần (xem **mục 6**). Không muốn cài Python → dùng binary Linux dựng sẵn (mục 📦).
> - **macOS**: cấp quyền *Accessibility* cho Terminal (System Settings → Privacy → Accessibility).

## 3. Cấu hình
Sửa [`config.json`](config.json):
```json
{
  "server": "ws://<IP_SERVER_UBUNTU>:7000/ws",
  "channel": "room1",
  "name": "May-A",
  "backend": "auto",
  "relay_keys": true,
  "auto_inject": true,
  "echo_suppress_ms": 90,
  "only_keys": [],
  "ignore_keys": [],
  "pause_key": "insert",
  "resume_key": "delete",
  "start_paused": false,
  "ui_port": 7071,
  "open_ui": true
}
```
- `server`: địa chỉ WebSocket của server Ubuntu.
- `channel`: **2 máy phải cùng kênh** mới đồng bộ.
- `name`: tên máy (máy 1 = `May-A`, máy 2 = `May-B`).
- `backend`: `auto` (mặc định: Linux → `evdev`, Windows/macOS → `pynput`). Trên Linux X11 có thể ép `pynput` nếu không muốn cấp quyền nhóm `input` (không chạy trên Wayland).
- `only_keys`: để rỗng = relay **tất cả** phím. Nếu chỉ muốn vài phím, vd chỉ `R` và `Enter`:
  ```json
  "only_keys": ["r", "R", "enter"]
  ```
- `ignore_keys`: các phím bỏ qua.
- `pause_key`: phím **TẮT** đồng bộ / tạm dừng (mặc định `insert` = phím **Ins**). `""` = không dùng.
- `resume_key`: phím **BẬT** lại đồng bộ (mặc định `delete` = phím **Del**). `""` = không dùng.
  Đặt 2 phím **giống nhau** → 1 phím bật/tắt luân phiên.
- `start_paused`: `true` = mở agent lên ở trạng thái tạm dừng (bấm Del để bật).
- `ui_port`: cổng giao diện web `http://127.0.0.1:7071/` (`0` = tắt giao diện).
- `open_ui`: `true` = tự mở giao diện trong trình duyệt khi chạy agent.

### ⏸ Tắt / bật đồng bộ (Ins / Del)
- Bấm **Ins** trên máy nào → **máy đó** tạm dừng: không gửi phím đi, không tự bấm phím nhận về
  (các máy khác vẫn chạy). Bấm Ins thêm lần nữa vẫn là tắt.
- Bấm **Del** → bật lại đồng bộ.
- Agent kêu "bíp" (chuông console) và in `[⏸] TẠM DỪNG` / `[▶] ĐÃ BẬT`.
- Ins / Del là phím điều khiển nên **không bao giờ được đồng bộ** sang máy khác (máy kia bấm Ins/Del cũng không gõ theo).
  Cần đồng bộ Ins/Del thì đổi `pause_key` / `resume_key` sang phím khác, vd `"f11"` / `"f12"`.
- Tên phím hợp lệ: chữ/số như `r`, hoặc `f1`…`f24`, `insert`, `delete`, `home`, `end`, `pause`, `scroll_lock`…
- Linux: dùng Ins/Del ở cụm phím chính — Ins/Del trên **bàn phím số** (NumLock tắt) chưa được nhận.

## 🖥️ Giao diện web
Chạy agent → trình duyệt tự mở **http://127.0.0.1:7071/** (chỉ máy này truy cập được):

- Trạng thái lớn **ĐANG ĐỒNG BỘ / TẠM DỪNG** + nút tắt/bật (giống phím Ins/Del).
- Kết nối server, **các máy đang online** trong kênh.
- **Phím gửi / nhận gần nhất** (kèm máy gửi) + bộ đếm, nhật ký trực tiếp (lọc "chỉ phím").
- Công tắc **Gửi phím đi** / **Tự bấm phím nhận về**.
- Sửa **server / kênh / tên máy / phím tắt-bật** → *Lưu & kết nối lại* (ghi vào `config.json`).
- Cảnh báo thiếu quyền (Linux) kèm lệnh sửa; nút **Thoát agent** (khi chạy không có terminal).

Mở agent lần 2 khi đang chạy → chỉ mở lại giao diện, không chạy thêm bản nữa.
Tham số: `--no-ui` (không chạy giao diện), `--no-browser` (chạy giao diện nhưng không tự mở trình duyệt).

## 4. Chạy
Máy 1 (cũng có thể ghi đè tham số):
```bash
python agent.py May-A room1 ws://<IP>:7000/ws
```
Máy 2:
```bash
python agent.py May-B room1 ws://<IP>:7000/ws
```
Khi thấy `Đang nghe phím toàn cục` → bấm phím trên máy 1 → máy 2 bấm theo.

## 5. Chạy nền (Windows)
```bash
start /B pythonw agent.py
```
Hoặc tạo shortcut chạy `pythonw agent.py`, đặt vào thư mục Startup để tự khởi động cùng Windows.

## 6. Linux (X11 + Wayland)
Trên Linux agent đọc/bấm phím trực tiếp qua **evdev** (`/dev/input` + `/dev/uinput`), nên chạy được cả **Wayland** (KDE, GNOME…) — nơi cách bắt phím kiểu X11 không hoạt động.

Cấp quyền **1 lần** cho mỗi máy (nạp module `uinput`, udev rule, thêm user vào nhóm `input`):
```bash
sudo ./setup-linux.sh
# rồi ĐĂNG XUẤT / đăng nhập lại
```
Kiểm tra: `id | grep input` và `ls -l /dev/uinput` (nhóm `input`, quyền `rw`).

Chạy:
```bash
python3 agent.py May-B room1 ws://<IP>:7000/ws      # từ mã nguồn
./clickdongbo-agent                                   # hoặc binary dựng sẵn (đọc config.json cạnh file)
```
Khi chạy sẽ in `Backend : evdev` và danh sách `Nghe bàn phím: ...`. Agent tự nhận bàn phím cắm thêm.

- Thiếu quyền → agent in hướng dẫn và vẫn chạy phần còn dùng được (vd chỉ nhận mà không gửi).
- Ký tự quy đổi theo **layout US**; máy dùng layout khác có thể ra ký tự khác với ký tự đặc biệt.
- ⚠️ User trong nhóm `input` đọc được **mọi** phím gõ trên máy (kể cả mật khẩu) — chỉ cấp cho tài khoản tin cậy.

## ⚠️ Lưu ý quan trọng
- **Chống lặp vòng**: Windows/macOS dùng cửa sổ thời gian `echo_suppress_ms`. Nếu gõ quá nhanh ngay sau khi nhận phím, một phím cục bộ hiếm khi có thể bị bỏ qua — tăng/giảm giá trị cho phù hợp. Linux (evdev) không nghe bàn phím ảo của chính agent nên không cần, `echo_suppress_ms` bị bỏ qua.
- **Phím bổ trợ** (Shift/Ctrl/Alt) không relay riêng để tránh nhân đôi; chữ in hoa/ký tự đặc biệt vẫn đúng vì đi kèm theo ký tự.
- **Quyền hệ điều hành**: mô phỏng phím toàn cục cần quyền — Windows thường OK; macOS/Linux cần cấp quyền như đã nêu.

## 📦 Đóng gói thành app .exe (KHÔNG cần cài Python trên máy nhận)

Để người khác chỉ cần **tải về và chạy** (không cài Python):

```bash
# cài công cụ đóng gói (chỉ làm 1 lần)
pip install pyinstaller

# Windows:
agent\build.bat
# Linux/Mac:
cd agent && bash build.sh
```

Kết quả trong `agent/dist/`:
- `clickdongbo-agent.exe` (Windows) — file chạy độc lập.
- `config.json` — đặt cạnh `.exe`, sửa `server`/`channel`/`name` tại đây.

→ Copy 2 file này sang máy khác (Windows) và chạy `clickdongbo-agent.exe` là xong.

**AppImage (Linux, khuyên dùng)**: 1 file chạy trên hầu hết distro, double-click là chạy.
```bash
cd agent && ./build-appimage.sh          # -> dist/ClickDongBo-x86_64.AppImage
```
Dùng:
```bash
chmod +x ClickDongBo-x86_64.AppImage
./ClickDongBo-x86_64.AppImage --setup    # 1 lần: cấp quyền (hỏi mật khẩu admin), rồi đăng xuất/đăng nhập lại
./ClickDongBo-x86_64.AppImage            # hoặc double-click -> mở giao diện web
```
`config.json` được tạo **cạnh file .AppImage** (thư mục đó không ghi được → `~/.config/clickdongbo/config.json`).

**Linux (binary rời)**: `build.sh` ra `dist/clickdongbo-agent` + `config.json` + `setup-linux.sh`. GitHub Actions cũng build sẵn cả 2 bản mỗi lần push: tab **Actions** → run mới nhất → artifact `clickdongbo-agent-exe` (Windows) / `clickdongbo-agent-linux` / `clickdongbo-agent-appimage` (tar.gz, build trên Ubuntu 22.04 nên chạy được trên distro có glibc ≥ 2.35).

> Lưu ý: file `.exe` được tạo riêng cho từng hệ điều hành. Build trên Windows ra `.exe` cho Windows; build trên Linux ra binary cho Linux.

## Khắc phục
| Hiện tượng | Xử lý |
|---|---|
| `[!] Thiếu thư viện` | chạy lại `pip install -r requirements.txt` |
| `Mất kết nối` liên tục | kiểm tra `server`, cổng 7000, firewall |
| Máy kia không bấm | 2 máy khác `channel`, hoặc `auto_inject=false`, hoặc thiếu quyền OS |
| Phím bị lặp đi lặp lại (Windows/macOS) | tăng `echo_suppress_ms` lên 120–150 |
| Linux: `Không đọc được bàn phím` / `Không ghi được /dev/uinput` | `sudo ./setup-linux.sh` rồi đăng xuất/đăng nhập lại |
| Linux: `Thiếu thư viện evdev` hoặc build `evdev` lỗi `Python.h` | cài `gcc` + `python3-dev`/`python3-devel`, hoặc dùng binary dựng sẵn |
| Linux: bấm phím 2 lần | phần mềm remap/macro tạo bàn phím ảo phát lại phím; agent đã lọc trùng 30 ms — nếu vẫn lặp, tắt phần mềm đó |
