'use strict';

/**
 * ============================================================
 *  CLICK-DONGBO — Máy chủ đồng bộ thời gian thực (WebSocket)
 * ============================================================
 *  Chạy trên server Ubuntu. Đóng vai trò trung gian relay:
 *  - Phục vụ trang web client (static) tại  http://<ip>:PORT/
 *  - Mở WebSocket tại ws://<ip>:PORT/ để 2 máy trao đổi realtime
 *
 *  Khi máy A ấn nút -> gửi event tới server -> server broadcast
 *  cho tất cả máy khác trong cùng "kênh" (channel) -> máy B nhận.
 * ============================================================
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

// ---- Cấu hình -----------------------------------------------------------
const PORT = process.env.PORT || 3000;
const PUBLIC_DIR = path.join(__dirname, 'public');

// Bảng MIME cho static server
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml'
};

// ---- HTTP server phục vụ file tĩnh (giao diện client) ------------------
const server = http.createServer((req, res) => {
  // Vệ trì đường dẫn, mặc định về index.html
  let urlPath = decodeURIComponent(req.url.split('?')[0]);
  if (urlPath === '/') urlPath = '/index.html';

  // Chống path traversal
  const filePath = path.join(PUBLIC_DIR, urlPath);
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    return res.end('403 Forbidden');
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      return res.end('404 Not Found');
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

// ---- WebSocket server (relay dữ liệu đồng bộ) ---------------------------
const wss = new WebSocketServer({ server, path: '/ws' });

/**
 * Lưu trữ client theo kênh (channel) để ghép đôi các máy cùng nhóm.
 * Map<channelName, Set<WebSocket>>
 */
const channels = new Map();

function getClients(channel) {
  if (!channels.has(channel)) channels.set(channel, new Set());
  return channels.get(channel);
}

/** Gửi JSON an toàn tới một ws */
function safeSend(ws, obj) {
  if (ws.readyState === ws.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

/** Broadcast một message tới tất cả client KHÁC trong cùng kênh */
function broadcast(ws, channel, message) {
  const members = getClients(channel);
  for (const member of members) {
    if (member !== ws && member.readyState === member.OPEN) {
      member.send(JSON.stringify(message));
    }
  }
}

/** Cập nhật danh sách máy online trong kênh gửi cho toàn bộ thành viên */
function sendRoster(channel) {
  const members = getClients(channel);
  const roster = [...members]
    .map((m) => m.meta && m.meta.name)
    .filter(Boolean);
  const msg = { type: 'roster', clients: roster, count: roster.length };
  for (const m of members) safeSend(m, msg);
}

wss.on('connection', (ws, req) => {
  // Mặc định kênh chung nếu client chưa chỉ định
  ws.meta = { name: 'Ẩn danh', channel: 'default', joinedAt: Date.now() };

  const ip = req.socket.remoteAddress;
  console.log(`[+] Kết nối mới từ ${ip}`);

  // ---- Nhận message từ client ----
  ws.on('message', (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch (e) {
      return; // bỏ qua message không hợp lệ
    }

    switch (msg.type) {
      // Client tham gia kênh + khai báo tên máy
      case 'join': {
        // rời kênh cũ
        const old = getClients(ws.meta.channel);
        old.delete(ws);
        sendRoster(ws.meta.channel);

        const newChannel = (msg.channel && String(msg.channel).trim()) || 'default';
        const name = (msg.name && String(msg.name).trim()) || 'Máy không tên';

        ws.meta.channel = newChannel;
        ws.meta.name = name;
        getClients(newChannel).add(ws);

        console.log(`    → "${name}" gia nhập kênh "${newChannel}"`);
        safeSend(ws, { type: 'joined', channel: newChannel, name: name });
        sendRoster(newChannel);
        break;
      }

      // Sự kiện đồng bộ tổng quát (ấn nút, thay đổi giá trị, v.v.)
      case 'sync': {
        // Gắn thông tin người gửi rồi relay tới các máy khác trong kênh
        const payload = {
          type: 'sync',
          from: ws.meta.name,
          key: msg.key,            // id của nút/dữ liệu (vd: "btn-start")
          value: msg.value,        // giá trị tùy chọn (vd: "press", true/false, số...)
          ts: msg.ts || Date.now() // timestamp của máy gửi
        };
        broadcast(ws, ws.meta.channel, payload);
        break;
      }

      // Đo độ trễ (ping/pong)
      case 'ping': {
        safeSend(ws, { type: 'pong', t: Date.now() });
        break;
      }

      default:
        // Không nhận diện — bỏ qua
        break;
    }
  });

  // ---- Ngắt kết nối ----
  ws.on('close', () => {
    const ch = getClients(ws.meta.channel);
    ch.delete(ws);
    console.log(`[-] "${ws.meta.name}" rời kênh "${ws.meta.channel}"`);
    sendRoster(ws.meta.channel);
  });

  ws.on('error', (err) => {
    console.error('    [ws error]', err.message);
  });
});

// ---- Khởi động ----------------------------------------------------------
server.listen(PORT, () => {
  console.log('============================================================');
  console.log('  CLICK-DONGBO — Máy chủ đồng bộ đã chạy');
  console.log('============================================================');
  console.log(`  Giao diện (client):  http://<IP_UBUNTU>:${PORT}/`);
  console.log(`  WebSocket (ws):      ws://<IP_UBUNTU>:${PORT}/ws`);
  console.log(`  Đang lắng nghe cổng: ${PORT}`);
  console.log('------------------------------------------------------------');
  console.log('  Mở trang web trên CẢ 2 máy và dùng chung 1 kênh (channel).');
  console.log('============================================================');
});
