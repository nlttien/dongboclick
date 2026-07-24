'use strict';
// Kiểm thử end-to-end: giả lập 2 máy kết nối & đồng bộ ấn nút.
const WebSocket = require('ws');
const URL = 'ws://localhost:3000/ws';

function makeClient(name, channel) {
  const ws = new WebSocket(URL);
  return new Promise((resolve) => {
    ws.on('open', () => {
      ws.send(JSON.stringify({ type: 'join', name, channel }));
      resolve(ws);
    });
    ws.on('message', (d) => ws.emit('json', JSON.parse(d.toString())));
    ws.on('error', (e) => { console.log('  [err]', e.message); });
  });
}

(async () => {
  console.log('--- Test đồng bộ giữa Máy A & Máy B ---');
  const a = await makeClient('Máy A', 'room-test');
  const b = await makeClient('Máy B', 'room-test');

  // Chờ server gửi roster
  await new Promise((r) => setTimeout(r, 300));

  // Máy B lắng nghe sự kiện sync
  let received = null;
  b.on('json', (m) => {
    if (m.type === 'sync') {
      received = m;
      console.log('  [Máy B nhận]', JSON.stringify(m));
    }
  });

  // Máy A ấn nút
  a.send(JSON.stringify({ type: 'sync', key: 'btn-start', value: 'press', ts: Date.now() }));
  console.log('  [Máy A gửi] ấn btn-start');

  await new Promise((r) => setTimeout(r, 400));

  if (received && received.from === 'Máy A' && received.key === 'btn-start') {
    console.log('\n✅ KẾT QUẢ: ĐỒNG BỘ THÀNH CÔNG — Máy B đã nhận nút từ Máy A.');
  } else {
    console.log('\n❌ KẾT QUẢ: THẤT BẠI — Máy B không nhận được sự kiện.');
  }

  a.close(); b.close();
  process.exit(0);
})();
