# Click Đồng Bộ ⇄

Công cụ **đồng bộ truyền dữ liệu & ấn nút giữa 2 máy** theo thời gian thực, chạy qua một **server Ubuntu** trung gian (WebSocket relay).

> Khi máy A ấn một nút → máy B lập tức nhận & hiển thị sự kiện đó (và ngược lại).

---

## 🧩 Kiến trúc

```
  [ Máy A (trình duyệt) ]  ──┐                       ┌──  [ Máy B (trình duyệt) ]
         ấn nút              │      Server Ubuntu     │            nhận & nhấp nháy
                             └──►  (Node.js + WS)  ◄──┘
                                   phục vụ cả giao diện web + relay WebSocket
```

- **Server** ([`server.js`](server.js)): máy chủ Node.js, vừa phục vụ trang web client (HTTP), vừa mở WebSocket (`/ws`) để relay dữ liệu. Ghép các máy theo **kênh (channel)**.
- **Client** ([`public/index.html`](public/index.html) + [`public/app.js`](public/app.js) + [`public/style.css`](public/style.css)): giao diện web mở trên **cả 2 máy**. Kết nối tới server, gửi/nhận sự kiện ấn nút realtime.

---

## 🚀 Cài đặt trên server Ubuntu

### 1. Cài Node.js (nếu chưa có)
```bash
# Ubuntu 20.04 / 22.04 / 24.04
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node -v   # kiểm tra
```

### 2. Tải code & cài dependency
```bash
# Copy thư mục dự án lên server, sau đó trong thư mục gốc:
npm install
```

### 3. Chạy thử
```bash
npm start
# Mặc định chạy ở cổng 3000.
# Đổi cổng: PORT=8080 npm start
```

Màn hình sẽ hiện:
```
  Giao diện (client):  http://<IP_UBUNTU>:3000/
  WebSocket (ws):      ws://<IP_UBUNTU>:3000/ws
```

### 4. Mở cổng tường lửa (UFW)
```bash
sudo ufw allow 3000/tcp
```
> Nếu dùng VPS cloud (AWS/GCP/DigitalOcean…), nhớ mở cổng **3000** ở Security Group/Firewall của nhà cung cấp.

---

## 🖥️ Chạy nền + tự khởi động (systemd)

File [`deploy/clickdongbo.service`](deploy/clickdongbo.service) giúp server chạy nền và tự khởi động lại.

```bash
# 1. Sửa đường dẫn trong file service cho đúng chỗ đặt code
sudo nano deploy/clickdongbo.service
#    -> đổi /opt/clickdongbo thành thư mục thật của bạn

# 2. Cài service
sudo cp deploy/clickdongbo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clickdongbo

# 3. Xem log
sudo journalctl -u clickdongbo -f
```

---

## 🖱️ Cách sử dụng (trên 2 máy)

1. Mở trình duyệt trên **cả 2 máy**, truy cập:
   ```
   http://<IP_UBUNTU>:3000/
   ```
2. Trên mỗi máy điền:
   - **Tên máy của bạn** (vd: `Máy A`, `Máy B`)
   - **Kênh (channel)** — *phải giống nhau* trên cả 2 máy (vd: `room1`)
   - **Địa chỉ server** — `ws://<IP_UBUNTU>:3000/ws`
3. Bấm **Kết nối** trên cả 2 máy. Khi trạng thái chuyển sang **Đã kết nối**, ấn nút bất kỳ → máy kia sẽ **nhấp nháy + hiện log**.
4. Có thể **thêm nút tuỳ chỉnh** (Tên nút mới → + Thêm nút). Cấu hình được lưu lại trong trình duyệt.

> Mẹo: kênh hoạt động như "phòng riêng". Nhiều cặp máy có thể dùng song song bằng các kênh khác nhau.

---

## 📡 Giao thức tin nhắn (WebSocket)

| Hướng | type | Trường | Ý nghĩa |
|------|------|--------|---------|
| Client → Server | `join` | `name`, `channel` | Tham gia kênh |
| Client → Server | `sync` | `key`, `value`, `ts` | Gửi sự kiện đồng bộ (ấn nút) |
| Client → Server | `ping` | — | Đo độ trễ |
| Server → Client | `joined` | `channel`, `name` | Xác nhận đã vào kênh |
| Server → Client | `roster` | `clients`, `count` | Danh sách máy online trong kênh |
| Server → Client | `sync` | `from`, `key`, `value`, `ts` | Relay sự kiện từ máy khác |
| Server → Client | `pong` | `t` | Phản hồi đo độ trễ |

→ Bạn có thể dùng chính giao thức này để đồng bộ **bất kỳ dữ liệu nào** (nút, giá trị số, trạng thái bật/tắt…) chứ không chỉ nút bấm.

---

## 🔧 Tuỳ biến cổng

```bash
PORT=8080 npm start
```
Nhớ mở cổng tương ứng ở tường lửa.

---

## ❓ Khắc phục sự cố

| Triệu chứng | Nguyên nhân & cách xử lý |
|-------------|--------------------------|
| "Đang kết nối…" mãi không xong | Sai địa chỉ server / cổng chưa mở / `ws://` vs `wss://` |
| Đã kết nối nhưng ấn nút máy kia không nhận | 2 máy nhập **khác kênh (channel)** |
| Không truy cập được trang `http://<ip>:3000` | Tường lửa/VPC chưa mở cổng 3000 |
| Muốn chạy cùng HTTPS | Đặt nginx/caddy ngược proxy + dùng `wss://` |

---

## 📁 Cấu trúc thư mục
```
clickdongbo/
├── package.json
├── server.js            # máy chủ WebSocket + static
├── public/
│   ├── index.html       # giao diện
│   ├── style.css        # giao diện
│   └── app.js           # logic client (kết nối, đồng bộ)
├── deploy/
│   ├── clickdongbo.service   # systemd unit
│   └── nginx.conf             # ví dụ reverse proxy (tuỳ chọn)
└── README.md
```
