'use strict';

/* ============================================================
 *  CLICK-DONGBO — Client logic
 *  Kết nối WebSocket tới server Ubuntu, đồng bộ ấn nút realtime.
 * ============================================================ */

// ---- Tham chiếu DOM ----
const $ = (id) => document.getElementById(id);
const elName = $('nameInput');
const elChannel = $('channelInput');
const elServer = $('serverInput');
const elConnect = $('connectBtn');
const elDisconnect = $('disconnectBtn');
const elConnDot = $('connDot');
const elConnText = $('connText');
const elPing = $('pingText');
const elRoster = $('roster');
const elButtons = $('buttons');
const elLog = $('log');
const elNewBtnLabel = $('newBtnLabel');
const elAddBtn = $('addBtn');

// ---- Trạng thái ----
let ws = null;
let connected = false;
let myName = '';
let myChannel = '';
let buttons = []; // mảng cấu hình nút: { id, label }
let remoteTimers = new Map(); // id -> timeout (xoá class remote)
let pingInterval = null;
let lastPing = 0;

// ---- Nút mặc định ban đầu ----
const DEFAULT_BUTTONS = [
  { id: 'start', label: 'Bắt đầu' },
  { id: 'stop', label: 'Dừng' },
  { id: 'next', label: 'Tiếp theo' },
  { id: 'alert', label: 'Cảnh báo' }
];

// ---- Lưu/đọc cấu hình từ localStorage ----
function loadConfig() {
  try {
    const saved = JSON.parse(localStorage.getItem('clickdongbo') || '{}');
    elName.value = saved.name || guessName();
    elChannel.value = saved.channel || 'room1';
    elServer.value = saved.server || guessServer();
    buttons = (saved.buttons && saved.buttons.length) ? saved.buttons : DEFAULT_BUTTONS.slice();
  } catch {
    buttons = DEFAULT_BUTTONS.slice();
    elName.value = guessName();
    elChannel.value = 'room1';
    elServer.value = guessServer();
  }
  renderButtons();
}
function saveConfig() {
  const cfg = {
    name: elName.value.trim(),
    channel: elChannel.value.trim(),
    server: elServer.value.trim(),
    buttons
  };
  localStorage.setItem('clickdongbo', JSON.stringify(cfg));
}

function guessName() {
  return 'Máy-' + Math.floor(1000 + Math.random() * 9000);
}
function guessServer() {
  // Mặc định dùng cùng host đang mở trang (nếu chạy client ngay trên server)
  const loc = window.location;
  if (loc.protocol.startsWith('http')) {
    return `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.hostname}:3000/ws`;
  }
  return 'ws://localhost:3000/ws';
}

// ---- Trạng thái kết nối (UI) ----
function setConnState(state) {
  const map = {
    off: { cls: 'off', text: 'Đã ngắt kết nối' },
    connecting: { cls: 'connecting', text: 'Đang kết nối…' },
    on: { cls: 'on', text: 'Đã kết nối' }
  };
  const s = map[state] || map.off;
  elConnDot.className = 'dot ' + s.cls;
  elConnText.textContent = s.text;
  connected = (state === 'on');
  elConnect.disabled = connected;
  elDisconnect.disabled = !connected;
}

// ---- Render danh sách nút ----
function renderButtons() {
  elButtons.innerHTML = '';
  buttons.forEach((b) => {
    const btn = document.createElement('button');
    btn.className = 'sync-btn';
    btn.dataset.id = b.id;
    btn.innerHTML = `<span class="label">${escapeHtml(b.label)}</span>
                     <span class="by"></span>
                     <button class="del" title="Xoá nút">×</button>`;

    // Sự kiện ấn (gửi đi + phản hồi cục bộ)
    btn.addEventListener('pointerdown', () => handlePress(b));
    btn.addEventListener('click', () => handlePress(b));

    // Nút xoá
    btn.querySelector('.del').addEventListener('click', (e) => {
      e.stopPropagation();
      buttons = buttons.filter((x) => x.id !== b.id);
      saveConfig();
      renderButtons();
    });

    elButtons.appendChild(btn);
  });
}

function escapeHtml(s) {
  // Dùng charCode để dựng thực thể tại runtime (tránh literal dễ bị biến dạng)
  var map = { 38: 'amp', 60: 'lt', 62: 'gt', 34: 'quot', 39: '#39' };
  return String(s).replace(/[&<>"']/g, function (c) {
    return '&' + map[c.charCodeAt(0)] + ';';
  });
}

// ---- Xử lý ấn nút ----
function handlePress(b) {
  flashLocal(b.id);
  logEvent('me', `Bạn ấn "${b.label}"`);
  sendSync(b.id, 'press');
}

function flashLocal(id) {
  const el = elButtons.querySelector(`.sync-btn[data-id="${cssEscape(id)}"]`);
  if (!el) return;
  el.classList.add('pressed');
  setTimeout(() => el.classList.remove('pressed'), 140);
}

// ---- Phản hồi khi nhận từ máy khác ----
function flashRemote(id, fromName) {
  const el = elButtons.querySelector(`.sync-btn[data-id="${cssEscape(id)}"]`);
  if (!el) return;
  el.classList.add('remote');
  const by = el.querySelector('.by');
  if (by) by.textContent = fromName ? '← ' + fromName : '';

  // xoá class remote sau 600ms
  if (remoteTimers.has(id)) clearTimeout(remoteTimers.get(id));
  remoteTimers.set(id, setTimeout(() => {
    el.classList.remove('remote');
    if (by) by.textContent = '';
  }, 600));
}

// escape đơn giản cho selector (id an toàn kiểu ASCII)
function cssEscape(s) {
  return String(s).replace(/["\\]/g, '\\$&');
}

// ---- Nhật ký ----
function logEvent(kind, text) {
  const li = document.createElement('li');
  li.className = kind; // 'me' | 'remote'
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  li.innerHTML = `<span>${escapeHtml(text)}</span><span class="time">${hh}:${mm}:${ss}</span>`;
  elLog.prepend(li);
  // giới hạn 60 dòng
  while (elLog.children.length > 60) elLog.removeChild(elLog.lastChild);
}

// ---- WebSocket: kết nối ----
function connect() {
  const name = elName.value.trim() || 'Máy không tên';
  let url = elServer.value.trim();
  if (!url) { alert('Vui lòng nhập địa chỉ server (ws://...)'); return; }

  myName = name;
  myChannel = elChannel.value.trim() || 'room1';
  saveConfig();

  setConnState('connecting');
  try {
    ws = new WebSocket(url);
  } catch (e) {
    setConnState('off');
    alert('Địa chỉ WebSocket không hợp lệ:\n' + e.message);
    return;
  }

  ws.addEventListener('open', () => {
    setConnState('on');
    // Gửi gói tham gia kênh
    ws.send(JSON.stringify({ type: 'join', name: myName, channel: myChannel }));
    startPing();
    logEvent('me', `Đã kết nối kênh "${myChannel}"`);
  });

  ws.addEventListener('message', (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    handleMessage(msg);
  });

  ws.addEventListener('close', () => {
    setConnState('off');
    stopPing();
    elPing.textContent = '';
    elRoster.textContent = 'Chưa có máy nào online';
    logEvent('remote', 'Mất kết nối với server');
  });

  ws.addEventListener('error', () => {
    // close event sẽ xử lý trạng thái
  });
}

function disconnect() {
  if (ws) { ws.close(); ws = null; }
  setConnState('off');
  stopPing();
}

// ---- Xử lý message nhận được ----
function handleMessage(msg) {
  switch (msg.type) {
    case 'joined':
      // server xác nhận đã vào kênh
      break;

    case 'roster': {
      const list = (msg.clients || []).join(', ') || '(chỉ mình bạn)';
      elRoster.textContent = `Online (${msg.count}): ${list}`;
      break;
    }

    case 'sync': {
      // Nhận sự kiện đồng bộ từ máy khác
      const b = buttons.find((x) => x.id === msg.key);
      const label = b ? b.label : msg.key;
      flashRemote(msg.key, msg.from);
      logEvent('remote', `${msg.from} ấn "${label}"${msg.value ? ' (' + msg.value + ')' : ''}`);
      break;
    }

    case 'pong': {
      const rtt = Date.now() - lastPing;
      elPing.textContent = `· ${rtt} ms`;
      break;
    }
  }
}

// ---- Gửi sự kiện đồng bộ ----
function sendSync(key, value) {
  if (!connected || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'sync', key, value, ts: Date.now() }));
}

// ---- Ping/Pong định kỳ đo độ trễ ----
function startPing() {
  stopPing();
  pingInterval = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      lastPing = Date.now();
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, 3000);
}
function stopPing() {
  if (pingInterval) { clearInterval(pingInterval); pingInterval = null; }
}

// ---- Thêm nút mới ----
function addCustomButton() {
  const label = elNewBtnLabel.value.trim();
  if (!label) return;
  const id = 'b' + Date.now().toString(36);
  buttons.push({ id, label });
  elNewBtnLabel.value = '';
  saveConfig();
  renderButtons();
}

// ---- Khởi tạo ----
loadConfig();
elConnect.addEventListener('click', connect);
elDisconnect.addEventListener('click', disconnect);
elAddBtn.addEventListener('click', addCustomButton);
elNewBtnLabel.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') addCustomButton();
});

// Tự ngắt khi đóng trang
window.addEventListener('beforeunload', () => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.close();
});
