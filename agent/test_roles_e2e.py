"""E2E test VAI TRÒ (leader / follower / 2 chiều) của agent Linux — không gõ phím vào desktop.

1 agent thật + các "máy khác" giả lập bằng client WebSocket. Bàn phím ảo của agent bị GRAB (phím agent bấm chỉ tới test),
bàn phím giả chỉ bấm F24.
Cần: quyền nhóm 'input' + ghi /dev/uinput, server TEST đang chạy (PORT=17010 npm start).
Chạy:  python3 agent/test_roles_e2e.py agent ws://127.0.0.1:17010/ws
"""
import json, os, re, subprocess, sys, tempfile, threading, time, urllib.request
import evdev
from evdev import ecodes as e
import websocket

if len(sys.argv) < 3:
    sys.exit(__doc__)
AGENT_DIR, URL, PY = os.path.abspath(sys.argv[1]), sys.argv[2], sys.executable
sys.path.insert(0, AGENT_DIR)
import linux_input as li

CH, UI = "ck-role-test", 17081
ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok = ok and cond


class Peer:
    """Một 'máy khác' trong kênh."""
    def __init__(self, name, role="both"):
        self.name, self.got, self.rosters = name, [], []
        self.ws = websocket.WebSocket()
        self.ws.connect(URL)
        self.ws.send(json.dumps({"type": "join", "name": name, "channel": CH, "role": role}))
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            try:
                m = json.loads(self.ws.recv())
            except Exception:
                break
            if m.get("type") == "roster":
                self.rosters.append(m)
            elif m.get("type") == "sync":
                self.got.append(m)

    def keys(self):
        return [json.loads(m["value"]) for m in self.got if m.get("key") == "keystroke"]

    def ops(self):
        return [json.loads(m["value"]).get("op") for m in self.got if m.get("key") == "role"]

    def send_key(self, ch, role="both"):
        self.ws.send(json.dumps({"type": "sync", "key": "keystroke", "ts": 0,
                                 "value": json.dumps({"s": {"k": "char", "v": ch}, "role": role})}))

    def send_op(self, op):
        self.ws.send(json.dumps({"type": "sync", "key": "role", "ts": 0, "value": json.dumps({"op": op})}))

    def close(self):
        self.ws.close()


def start_agent(role):
    d = tempfile.mkdtemp(prefix="clickdongbo-role-")
    for f in ("agent.py", "linux_input.py", "ui_server.py", "ui.html"):
        subprocess.run(["cp", os.path.join(AGENT_DIR, f), d], check=True)
    json.dump({"server": URL, "channel": CH, "name": "Agent", "role": role, "only_keys": ["f24", "R"],
               "ui_port": UI, "open_ui": False, "extra_keyboards": [FAKE]}, open(os.path.join(d, "config.json"), "w"))
    before = set(virtual_paths())             # bàn phím ảo của agent KHÁC đang chạy (vd AppImage thật) → không đụng
    proc = subprocess.Popen([PY, "-u", os.path.join(d, "agent.py")], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    log = []
    threading.Thread(target=lambda: [log.append(l.rstrip()) for l in proc.stdout], daemon=True).start()
    virt = None
    for _ in range(60):                       # GRAB bàn phím ảo ngay khi xuất hiện
        new = [p for p in virtual_paths() if p not in before]
        if new:
            virt = evdev.InputDevice(new[0])
        if virt:
            break
        time.sleep(0.1)
    if virt:
        virt.grab()
    time.sleep(4)                             # kết nối + quét bàn phím (RESCAN 3s)
    page = urllib.request.urlopen("http://127.0.0.1:%d/" % UI).read().decode()
    token = re.search(r"const TOKEN = '([^']+)'", page).group(1)
    return proc, virt, log, token


def virtual_paths():
    out = []
    for p in evdev.list_devices():
        try:
            dv = evdev.InputDevice(p)
        except OSError:
            continue
        if dv.name == li.VIRTUAL_NAME:
            out.append(p)
        dv.close()
    return out


def state():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d/api/state" % UI).read())


def action(token, **kw):
    req = urllib.request.Request("http://127.0.0.1:%d/api/action" % UI, data=json.dumps(kw).encode(),
                                 headers={"X-Agent-Token": token, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def drain(virt):
    out = []
    try:
        for ev in virt.read():
            if ev.type == e.EV_KEY and ev.value == 1:
                out.append(ev.code)
    except BlockingIOError:
        pass
    return out


def stop_agent(proc, virt):
    proc.terminate()
    proc.wait(5)
    if virt:
        try:
            virt.close()
        except OSError:
            pass
    time.sleep(0.5)


# CHỈ có F24 (không A-Z) → agent thật đang chạy trên máy KHÔNG coi là bàn phím, không gửi gì ra kênh thật;
# agent của test nghe nó nhờ "extra_keyboards"
FAKE = "ckd-test-f24"
fake = evdev.UInput({e.EV_KEY: [e.KEY_F24]}, name=FAKE)


def tap_f24():
    fake.write(e.EV_KEY, e.KEY_F24, 1); fake.syn(); fake.write(e.EV_KEY, e.KEY_F24, 0); fake.syn()
    time.sleep(0.6)


try:
    # ── A. FOLLOWER: chỉ làm theo leader, không gửi ──
    peer, lead = Peer("May-Khac"), Peer("May-Leader", "leader")
    proc, virt, log, token = start_agent("follower")
    check("A: agent tạo bàn phím ảo", virt is not None)
    check("A: state role = follower", state()["role"] == "follower")
    drain(virt)
    peer.send_key("R", role="both"); time.sleep(0.6)
    check("A: follower KHÔNG bấm phím của máy không phải leader", drain(virt) == [])
    lead.send_key("R", role="leader"); time.sleep(0.6)
    check("A: follower BẤM phím của leader", e.KEY_R in drain(virt))
    peer.got.clear(); tap_f24()
    check("A: follower KHÔNG gửi phím đi", peer.keys() == [])
    st = state()
    check("A: roster có vai trò từ server", st["roles"].get("May-Leader") == "leader" and st["roles"].get("Agent") == "follower")
    check("A: state biết leader", st["leader"] == "May-Leader")
    stop_agent(proc, virt); peer.close(); lead.close()
    time.sleep(1)

    # ── B. 2 CHIỀU → máy khác nhận leader → follower → trả quyền → 2 chiều ──
    peer = Peer("May-Khac")
    proc, virt, log, token = start_agent("both")
    check("B: state role = both", state()["role"] == "both")
    peer.send_op("claim"); time.sleep(0.8)
    check("B: máy khác nhận leader → agent thành follower", state()["role"] == "follower")
    peer.send_op("release"); time.sleep(0.8)
    check("B: leader trả quyền → agent về 2 chiều", state()["role"] == "both")
    late = Peer("May-Leader-Moi", "leader"); time.sleep(0.8)
    check("B: leader vào sau (server báo vai trò) → agent thành follower", state()["role"] == "follower")
    stop_agent(proc, virt); peer.close(); late.close()
    time.sleep(1)

    # ── C. LEADER: chỉ điều khiển ──
    peer = Peer("May-Khac")
    proc, virt, log, token = start_agent("both")
    action(token, action="set_role", role="leader"); time.sleep(0.8)
    check("C: đổi vai trò qua giao diện → leader", state()["role"] == "leader")
    check("C: máy khác nhận được 'claim'", "claim" in peer.ops())
    peer.got.clear(); tap_f24()
    ks = peer.keys()
    check("C: leader GỬI phím, kèm role=leader", any(k["s"]["v"] == "f24" and k.get("role") == "leader" for k in ks))
    drain(virt)
    peer.send_key("R", role="both"); time.sleep(0.6)
    check("C: leader KHÔNG bị máy khác điều khiển", drain(virt) == [])
    action(token, action="set_role", role="both"); time.sleep(0.8)
    check("C: thôi leader → máy khác nhận 'release'", "release" in peer.ops())
    action(token, action="set_role", role="leader"); time.sleep(0.8)
    newcomer = Peer("May-Moi"); time.sleep(1.0)
    check("C: máy vào sau nhận được 'claim' (cả server cũ không báo vai trò)", "claim" in newcomer.ops())
    stop_agent(proc, virt); peer.close(); newcomer.close()
finally:
    fake.close()

print("\n--- log agent (lần cuối) ---"); print("\n".join(l for l in log if "Vai trò" in l or "[i]" in l)[-1500:])
print("\nKET QUA:", "DAT" if ok else "THAT BAI")
sys.exit(0 if ok else 1)
