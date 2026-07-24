'use strict';

/* ============================================================
 *  CLICK-DONGBO — Client logic
 *  Kết nối WebSocket tới server Ubuntu, đồng bộ ấn nút realtime.
 *
 *  Hành vi chính:
 *   - Người dùng ấn nút trên MÁY NÀY  -> gửi sự kiện tới server
 *   - Khi MÁY KHÁC ấn -> máy này TỰ ẤN nút tương ứng (ấn thật:
 *     hiệu ứng nhấn + (tuỳ chọn) âm thanh + (tuỳ chọn) mô phỏng phím)
 *     NHƯNG KHÔNG gửi lại để tránh lặp vòng vô hạn.
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
const elNewBtnKey = $('newBtnKey');
const elAddBtn = $('addBtn');
const elSound = $('soundToggle');
const elAutoPress = $('autoPressToggle');

// ---- Trạng thái ----
let ws = null;
let connected = false;
let myName = '';
let myChannel = '';
let buttons = [];            // [{ id, label, key }]
let remoteTimers = new Map(); // id -> timeout (xoá class remote)
let pingInterval = null;
let lastPing = 0;
let soundOn = true;
let autoPressRemote = true;  // máy nhận có tự "ấn" nút hay không
let audioCtx = null;

// ---- Nút mặc định ban đầu ----
const DEFAULT_BUTTONS = [
  { id: 'start', label: 'Bắt đầu',  key: '' },
  { id: 'stop',  label: 'Dừng',      key: '' },
  { id: 'next',  label: 'Tiếp theo', key: '' },
  { id: 'alert', label: 'Cảnh báo',  key: '' }
];

// ---- Lưu/đọc cấu hình từ localStorage ----
function loadConfig() {
  try {
    const saved = JSON.parse(localStorage.getItem('clickdongbo') || '{}');
    elName.value = saved.name || guessName();
    elChannel.value = saved.channel || 'room1';
    elServer.value = saved.server || guessServer();
    buttons = (saved.buttons && saved.buttons.length) ? saved.buttons : DEFAULT_BUTTONS.slice();
    soundOn = (typeof saved.soundOn === 'boolean') ? saved.soundOn : true;
    autoPressRemote = (typeof saved.autoPressRemote === 'boolean') ? saved.autoPressRemote : true;
  } catch {
    buttons = DEFAULT_BUTTONS.slice();
    elName.value = guessName();
    elChannel.value = 'room1';
    elServer.value = guessServer();
  }
  if (elSound) elSound.checked = soundOn;
  if (elAutoPress) elAutoPress.checked = autoPressRemote;
  renderButtons();
}

function saveConfig() {
  localStorage.setItem('clickdongbo', JSON.stringify({
    name: elName.value.trim(),
    channel: elChannel.value.trim(),
    server: elServer.value.trim(),
    buttons: buttons,
    soundOn: soundOn,
    autoPressRemote: autoPressRemote
  }));
}

function guessName() {
  return 'Máy-' + Math.floor(1000 + Math.random() * 9000);
}
function guessServer() {
  // Mặc định dùng cùng host đang mở trang (nếu chạy client ngay trên server)
  const loc = window.location;
  if (loc.protocol.startsWith('http')) {
    return (loc.protocol === 'https:' ? 'wss' : 'ws') + '://' + loc.hostname + ':3000/ws';
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
    const keyBadge = b.key ? '<span class="key">⌨ ' + escapeHtml(b.key) + '</span>' : '';
    btn.innerHTML =
      '<span class="label">' + escapeHtml(b.label) + '</span>' + keyBadge +
      '<span class="by"></span>' +
      '<span class="del" title="Xoá nút" role="button">×</span>';

    // Người dùng ấn nút trên MÁY NÀY -> gửi đi + phản hồi cục bộ
    btn.addEventListener('click', () => onLocalPress(b));

    // Nút xoá
    const del = btn.querySelector('.del');
    if (del) del.addEventListener('click', (e) => {
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

// escape đơn giản cho selector (id an toàn kiểu ASCII)
function cssEscape(s) {
  return String(s).replace(/["\\]/g, '\\$&');
}

// ===================================================================
//  XỬ LÝ ẤN NÚT
// ===================================================================

// (A) Người dùng ấn nút THẬT trên máy này -> phát hiệu ứng + gửi đi
function onLocalPress(b) {
  performPress(b, { from: 'me' });
  logEvent('me', 'Bạn ấn "' + b.label + '"' + (b.key ? ' (⌨ ' + b.key + ')' : ''));
  sendSync(b.id, 'press');
}

// (B) "Ấn" một nút (dùng chung cho ấn tại chỗ và máy khác nhận được).
//     QUAN TRỌNG: hàm này KHÔNG gửi sync -> tránh lặp vòng vô hạn.
function performPress(b, opts) {
  opts = opts || {};
  const from = opts.from || 'me';
  const remote = (from !== 'me');
  const el = elButtons.querySelector('.sync-btn[data-id="' + cssEscape(b.id) + '"]');

  if (el) {
    // Động cơ ấn thật: nhấn xuống rồi nẩy lên
    el.classList.add('pressed');
    setTimeout(() => el.classList.remove('pressed'), 140);

    if (remote) {
      // Nhấn đến từ máy khác -> thêm viền nổi bật
      el.classList.add('remote');
      const by = el.querySelector('.by');
      if (by) by.textContent = from ? ('← ' + from) : '';
      if (remoteTimers.has(b.id)) clearTimeout(remoteTimers.get(b.id));
      remoteTimers.set(b.id, setTimeout(() => {
        el.classList.remove('remote');
        const by2 = el.querySelector('.by');
        if (by2) by2.textContent = '';
      }, 600));
    }
  }

  // Âm thanh (tuỳ chọn)
  if (soundOn) beep(remote);

  // Mô phỏng phím nếu nút có gắn phím (chỉ ảnh hưởng trong trang web)
  if (b.key) dispatchKey(b.key);
}

// (C) Khi tắt chế độ "tự ấn": chỉ phát sáng, không thực sự ấn
function flashOnly(id, from) {
  const el = elButtons.querySelector('.sync-btn[data-id="' + cssEscape(id) + '"]');
  if (!el) return;
  el.classList.add('remote');
  const by = el.querySelector('.by');
  if (by) by.textContent = from ? ('← ' + from) : '';
  if (remoteTimers.has(id)) clearTimeout(remoteTimers.get(id));
  remoteTimers.set(id, setTimeout(() => {
    el.classList.remove('remote');
    const by2 = el.querySelector('.by');
    if (by2) by2.textContent = '';
  }, 600));
}

// ---- Âm thanh "bíp" khi ấn ----
function beep(remote) {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const o = audioCtx.createOscillator();
    const g = audioCtx.createGain();
    o.connect(g);
    g.connect(audioCtx.destination);
    o.type = 'sine';
    o.frequency.value = remote ? 880 : 660; // máy khác cao hơn một chút
    const t = audioCtx.currentTime;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.15, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.12);
    o.start(t);
    o.stop(t + 0.13);
  } catch (e) {
    // trình duyệt không hỗ trợ / chưa cho phép âm thanh
  }
}

// ---- Mô phỏng phím (chỉ trong trang web) ----
function dispatchKey(key) {
  // Ghi chú: trình duyệt KHÔNG cho phép điều khiển app ngoài OS.
  // Phím này chỉ tác động tới chính trang web (vd: input đang focus,
  // hoặc các thành phần lắng nghe keydown trong trang).
  try {
    const opts = { key: key, code: key, bubbles: true, cancelable: true };
    document.dispatchEvent(new KeyboardEvent('keydown', opts));
    document.dispatchEvent(new KeyboardEvent('keyup', opts));
  } catch (e) {
    // bỏ qua
  }
}

// ===================================================================
//  NHẬT KÝ
// ===================================================================
function logEvent(kind, text) {
  const li = document.createElement('li');
  li.className = kind; // 'me' | 'remote'
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const ss = String(now.getSeconds()).padStart(2, '0');
  li.innerHTML = '<span>' + escapeHtml(text) + '</span><span class="time">' + hh + ':' + mm + ':' + ss + '</span>';
  elLog.prepend(li);
  while (elLog.children.length > 60) elLog.removeChild(elLog.lastChild);
}

// ===================================================================
//  WEBSOCKET
// ===================================================================
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
    ws.send(JSON.stringify({ type: 'join', name: myName, channel: myChannel }));
    startPing();
    logEvent('me', 'Đã kết nối kênh "' + myChannel + '"');
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
      elRoster.textContent = 'Online (' + msg.count + '): ' + list;
      break;
    }

    case 'sync': {
      // Máy khác vừa ấn nút -> máy này cũng phải "ấn" nút tương ứng
      const b = buttons.find((x) => x.id === msg.key);
      const btnObj = b || { id: msg.key, label: msg.key, key: '' };
      const label = b ? b.label : msg.key;

      if (autoPressRemote) {
        // THỰC SỰ ấn nút trên máy này (nhưng không gửi lại -> không lặp vòng)
        performPress(btnObj, { from: msg.from });
        logEvent('remote', msg.from + ' ấn "' + label + '"' +
          (b && b.key ? ' (⌨ ' + b.key + ')' : ''));
      } else {
        // Chế độ chỉ xem: không tự ấn
        flashOnly(msg.key, msg.from);
        logEvent('remote', msg.from + ' ấn "' + label + '" (chỉ xem)');
      }
      break;
    }

    case 'pong': {
      const rtt = Date.now() - lastPing;
      elPing.textContent = '· ' + rtt + ' ms';
      break;
    }
  }
}

// ---- Gửi sự kiện đồng bộ ----
function sendSync(key, value) {
  if (!connected || !ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'sync', key: key, value: value, ts: Date.now() }));
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

// ---- Thêm nút mới (có thể gắn phím mô phỏng) ----
function addCustomButton() {
  const label = elNewBtnLabel.value.trim();
  if (!label) return;
  const key = elNewBtnKey ? elNewBtnKey.value.trim() : '';
  const id = 'b' + Date.now().toString(36);
  buttons.push({ id: id, label: label, key: key });
  elNewBtnLabel.value = '';
  if (elNewBtnKey) elNewBtnKey.value = '';
  saveConfig();
  renderButtons();
}

// ---- Khởi tạo ----
loadConfig();
elConnect.addEventListener('click', connect);
elDisconnect.addEventListener('click', disconnect);
elAddBtn.addEventListener('click', addCustomButton);
elNewBtnLabel.addEventListener('keydown', (e) => { if (e.key === 'Enter') addCustomButton(); });
elNewBtnKey.addEventListener('keydown', (e) => { if (e.key === 'Enter') addCustomButton(); });

if (elSound) {
  elSound.addEventListener('change', () => {
    soundOn = elSound.checked;
    saveConfig();
    if (soundOn) beep(false); // thử tiếng bíp
  });
}
if (elAutoPress) {
  elAutoPress.addEventListener('change', () => {
    autoPressRemote = elAutoPress.checked;
    saveConfig();
  });
}

// Tự ngắt khi đóng trang
window.addEventListener('beforeunload', () => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.close();
});
