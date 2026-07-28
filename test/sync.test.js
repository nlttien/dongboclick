'use strict';
// Kiểm thử end-to-end: giả lập 2 máy kết nối, đồng bộ ấn nút + chia sẻ danh sách nút.
const WebSocket = require('ws');
const URL = 'ws://192.168.2.113:3000/ws';

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
  let pass = true;
  console.log('--- Test đồng bộ giữa Máy A & Máy B ---');
  const a = await makeClient('Máy A', 'room-test');
  const b = await makeClient('Máy B', 'room-test');
  await new Promise((r) => setTimeout(r, 300));

  // ---- (1) Đồng bộ ấn nút ----
  let syncReceived = null;
  b.on('json', (m) => {
    if (m.type === 'sync') {
      syncReceived = m;
      console.log('  [Máy B nhận sync]', JSON.stringify(m));
    }
  });
  a.send(JSON.stringify({ type: 'sync', key: 'btn-start', value: 'press', ts: Date.now() }));
  console.log('  [Máy A gửi] ấn btn-start');
  await new Promise((r) => setTimeout(r, 300));

  if (syncReceived && syncReceived.from === 'Máy A' && syncReceived.key === 'btn-start') {
    console.log('✅ (1) Đồng bộ ấn nút: THÀNH CÔNG');
  } else {
    console.log('❌ (1) Đồng bộ ấn nút: THẤT BẠI');
    pass = false;
  }

  // ---- (2) Chia sẻ danh sách nút (buttons) ----
  let buttonsReceived = null;
  b.removeAllListeners('json');
  b.on('json', (m) => {
    if (m.type === 'buttons') {
      buttonsReceived = m;
      console.log('  [Máy B nhận buttons]', JSON.stringify(m));
    }
  });
  const sentButtons = [
    { id: 'start', label: 'Bắt đầu', key: '' },
    { id: 'b_xyz', label: 'Nút của A', key: 'R' }
  ];
  a.send(JSON.stringify({ type: 'buttons', buttons: sentButtons }));
  console.log('  [Máy A gửi] danh sách nút (' + sentButtons.length + ' nút)');
  await new Promise((r) => setTimeout(r, 300));

  if (buttonsReceived &&
      Array.isArray(buttonsReceived.buttons) &&
      buttonsReceived.buttons.length === 2 &&
      buttonsReceived.buttons[1].label === 'Nút của A') {
    console.log('✅ (2) Đồng bộ danh sách nút: THÀNH CÔNG');
  } else {
    console.log('❌ (2) Đồng bộ danh sách nút: THẤT BẠI');
    pass = false;
  }

  console.log(pass ? '\n🎉 TẤT CẢ TEST ĐẠT.' : '\n⚠️ CÓ TEST THẤT BẠI.');
  a.close(); b.close();
  process.exit(pass ? 0 : 1);
})();
