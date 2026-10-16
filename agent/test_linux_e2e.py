"""E2E test agent Linux (evdev), không gõ phím vào desktop.

Cần: quyền nhóm 'input' + ghi /dev/uinput (setup-linux.sh), server đang chạy.
Chạy:  PORT=17010 npm start   rồi   python3 agent/test_linux_e2e.py agent ws://127.0.0.1:17010/ws
⚠️ Chỉ dùng server TEST: agent trong test gửi/nhận phím thật trong kênh "ck-linux-test".

- Gửi: bàn phím giả 'ckd-test-kbd' bấm F24 -> agent -> server -> client test nhận special f24.
- Nhận: client test gửi 'R', '!', enter -> agent bấm qua bàn phím ảo; test GRAB bàn phím ảo đó
  nên phím chỉ tới test, không tới compositor.
"""
import json, os, subprocess, sys, tempfile, threading, time
import evdev
from evdev import ecodes as e
import websocket

if len(sys.argv) < 3:
    sys.exit(__doc__)
AGENT_DIR, URL, PY = os.path.abspath(sys.argv[1]), sys.argv[2], sys.executable
sys.path.insert(0, AGENT_DIR)
import linux_input as li

ok = True
def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond

# ---- 1. translate (thuần) ----
check("translate a", li.translate(e.KEY_A) == {"k": "char", "v": "a"})
check("translate shift+a", li.translate(e.KEY_A, shift=True) == {"k": "char", "v": "A"})
check("translate caps+a", li.translate(e.KEY_A, caps=True) == {"k": "char", "v": "A"})
check("translate caps+1 (không đổi)", li.translate(e.KEY_1, caps=True) == {"k": "char", "v": "1"})
check("translate shift+1", li.translate(e.KEY_1, shift=True) == {"k": "char", "v": "!"})
check("translate enter", li.translate(e.KEY_ENTER) == {"k": "special", "v": "enter"})
check("translate kp5", li.translate(e.KEY_KP5) == {"k": "char", "v": "5"})

# ---- 1b. lọc trùng giữa 2 thiết bị ----
class _Dev:
    def __init__(self, path): self.path = path
    def leds(self): return []
class _Ev:
    def __init__(self, code, value): self.type, self.code, self.value = e.EV_KEY, code, value
seen = []
L = li.Listener(seen.append)
L.handle(_Dev("/real"), _Ev(e.KEY_B, 1)); L.handle(_Dev("/virt"), _Ev(e.KEY_B, 1))
check("lọc trùng: cùng phím từ thiết bị ảo bị bỏ", seen == [{"k": "char", "v": "b"}])
L.handle(_Dev("/real"), _Ev(e.KEY_B, 0)); L.handle(_Dev("/real"), _Ev(e.KEY_B, 1))
check("lọc trùng: gõ lại trên cùng thiết bị vẫn nhận", len(seen) == 2)

# ---- 2. agent thật: relay on, inject on ----
cfg_dir = tempfile.mkdtemp(prefix="clickdongbo-e2e-")
for f in ("agent.py", "linux_input.py", "ui_server.py", "ui.html"):
    subprocess.run(["cp", os.path.join(AGENT_DIR, f), cfg_dir], check=True)
json.dump({"server": URL, "channel": "ck-linux-test", "name": "Agent-Linux",
           "backend": "auto", "only_keys": ["f24", "R", "!", "enter", "f23", "f22"], "pause_key": "f23", "resume_key": "f22", "ui_port": 0},
          open(os.path.join(cfg_dir, "config.json"), "w"))

fake = evdev.UInput({e.EV_KEY: [e.KEY_A, e.KEY_Z, e.KEY_F24, e.KEY_F23, e.KEY_F22]}, name="ckd-test-kbd")
agent = subprocess.Popen([PY, "-u", os.path.join(cfg_dir, "agent.py")],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
log = []
threading.Thread(target=lambda: [log.append(l.rstrip()) for l in agent.stdout], daemon=True).start()

# chờ bàn phím ảo của agent xuất hiện rồi GRAB ngay
virt = None
for _ in range(50):
    for p in evdev.list_devices():
        d = evdev.InputDevice(p)
        if d.name == li.VIRTUAL_NAME:
            virt = d
            break
        d.close()
    if virt:
        break
    time.sleep(0.1)
check("agent tạo bàn phím ảo", virt is not None)
virt.grab()

got = []
client = websocket.WebSocket()
client.connect(URL)
client.send(json.dumps({"type": "join", "name": "Tester", "channel": "ck-linux-test"}))
def recv_loop():
    while True:
        try:
            m = json.loads(client.recv())
        except Exception:
            break
        if m.get("type") == "sync" and m.get("key") == "keystroke":
            got.append(json.loads(m["value"])["s"])
threading.Thread(target=recv_loop, daemon=True).start()
time.sleep(4)  # agent kết nối + quét bàn phím (RESCAN 3s)

# Gửi: bàn phím giả bấm F24
fake.write(e.EV_KEY, e.KEY_F24, 1); fake.syn()
fake.write(e.EV_KEY, e.KEY_F24, 0); fake.syn()
time.sleep(0.8)
check("gửi: F24 từ bàn phím giả tới client", {"k": "special", "v": "f24"} in got)

# Nhận: client gửi phím -> agent bấm trên bàn phím ảo (đã grab)
for s in ({"k": "char", "v": "R"}, {"k": "char", "v": "!"}, {"k": "special", "v": "enter"}):
    client.send(json.dumps({"type": "sync", "key": "keystroke",
                            "value": json.dumps({"s": s}), "ts": 0}))
time.sleep(1)
evs = []
try:
    for ev in virt.read():
        if ev.type == e.EV_KEY:
            evs.append((ev.code, ev.value))
except BlockingIOError:
    pass
expect = [(e.KEY_LEFTSHIFT, 1), (e.KEY_R, 1), (e.KEY_R, 0), (e.KEY_LEFTSHIFT, 0),
          (e.KEY_LEFTSHIFT, 1), (e.KEY_1, 1), (e.KEY_1, 0), (e.KEY_LEFTSHIFT, 0),
          (e.KEY_ENTER, 1), (e.KEY_ENTER, 0)]
check("nhận: agent bấm R, !, enter đúng thứ tự", evs == expect)
check("không echo: phím agent tự bấm không bị gửi lại",
      not any(x.get("v") in ("R", "!", "enter") for x in got))

# ---- Tạm dừng ----
def tap_fake(code):
    fake.write(e.EV_KEY, code, 1); fake.syn(); fake.write(e.EV_KEY, code, 0); fake.syn()
def drain():
    out = []
    try:
        for ev in virt.read():
            if ev.type == e.EV_KEY: out.append((ev.code, ev.value))
    except BlockingIOError:
        pass
    return out
got.clear(); drain()
tap_fake(e.KEY_F23); time.sleep(0.3)
tap_fake(e.KEY_F23); time.sleep(0.3)   # bấm Ins lần 2: vẫn TẮT (không đảo trạng thái)
tap_fake(e.KEY_F24); time.sleep(0.5)
check("Ins tắt: không gửi F24, không gửi chính phím Ins", got == [])
client.send(json.dumps({"type": "sync", "key": "keystroke",
                        "value": json.dumps({"s": {"k": "char", "v": "R"}}), "ts": 0}))
time.sleep(0.6)
check("Ins tắt: không tự bấm phím nhận về", drain() == [])
tap_fake(e.KEY_F22); time.sleep(0.3)
tap_fake(e.KEY_F22); time.sleep(0.3)   # bấm Del lần 2: vẫn BẬT
tap_fake(e.KEY_F24); time.sleep(0.5)
check("Del bật: gửi lại F24, không gửi chính phím Del", got == [{"k": "special", "v": "f24"}])
client.send(json.dumps({"type": "sync", "key": "keystroke",
                        "value": json.dumps({"s": {"k": "char", "v": "R"}}), "ts": 0}))
time.sleep(0.6)
check("Del bật: bấm lại phím nhận về", (e.KEY_R, 1) in drain())
for nm in ("f23", "f22"):
    client.send(json.dumps({"type": "sync", "key": "keystroke",
                            "value": json.dumps({"s": {"k": "special", "v": nm}}), "ts": 0}))
time.sleep(0.6)
check("không bấm Ins/Del nhận từ máy khác", drain() == [])

agent.terminate(); agent.wait(3)
fake.close(); client.close()
print("--- log agent ---"); print("\n".join(log[-14:]))
print("\nKET QUA:", "DAT" if ok else "THAT BAI")
sys.exit(0 if ok else 1)
