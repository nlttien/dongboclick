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
> Trên Linux/Mac có thể cần thêm:
> - Linux: `sudo apt install python3-tk python3-dev` và quyền truy cập X11.
> - macOS: cấp quyền *Accessibility* cho Terminal (System Settings → Privacy → Accessibility).

## 3. Cấu hình
Sửa [`config.json`](config.json):
```json
{
  "server": "ws://<IP_SERVER_UBUNTU>:3000/ws",
  "channel": "room1",
  "name": "May-A",
  "relay_keys": true,
  "auto_inject": true,
  "echo_suppress_ms": 90,
  "only_keys": [],
  "ignore_keys": []
}
```
- `server`: địa chỉ WebSocket của server Ubuntu.
- `channel`: **2 máy phải cùng kênh** mới đồng bộ.
- `name`: tên máy (máy 1 = `May-A`, máy 2 = `May-B`).
- `only_keys`: để rỗng = relay **tất cả** phím. Nếu chỉ muốn vài phím, vd chỉ `R` và `Enter`:
  ```json
  "only_keys": ["r", "R", "enter"]
  ```
- `ignore_keys`: các phím bỏ qua.

## 4. Chạy
Máy 1 (cũng có thể ghi đè tham số):
```bash
python agent.py May-A room1 ws://<IP>:3000/ws
```
Máy 2:
```bash
python agent.py May-B room1 ws://<IP>:3000/ws
```
Khi thấy `Đang nghe phím toàn cục` → bấm phím trên máy 1 → máy 2 bấm theo.

## 5. Chạy nền (Windows)
```bash
start /B pythonw agent.py
```
Hoặc tạo shortcut chạy `pythonw agent.py`, đặt vào thư mục Startup để tự khởi động cùng Windows.

## ⚠️ Lưu ý quan trọng
- **Chống lặp vòng**: dùng cửa sổ thời gian `echo_suppress_ms`. Nếu gõ quá nhanh ngay sau khi nhận phím, một phím cục bộ hiểnếm có thể bị bỏ qua — tăng/giảm giá trị cho phù hợp.
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

> Lưu ý: file `.exe` được tạo riêng cho từng hệ điều hành. Build trên Windows ra `.exe` cho Windows; build trên Linux ra binary cho Linux.

## Khắc phục
| Hiện tượng | Xử lý |
|---|---|
| `[!] Thiếu thư viện` | chạy lại `pip install -r requirements.txt` |
| `Mất kết nối` liên tục | kiểm tra `server`, cổng 3000, firewall |
| Máy kia không bấm | 2 máy khác `channel`, hoặc `auto_inject=false`, hoặc thiếu quyền OS |
| Phím bị lặp đi lặpng | tăng `echo_suppress_ms` lên 120–150 |
