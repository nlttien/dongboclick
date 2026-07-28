#!/usr/bin/env python3
"""Kiểm tra protocol của agent qua server (không động vào bàn phím thật)."""
import json, time, threading
import websocket

URL = "ws://192.168.2.113:3000/ws"
results = {}

def make(name, channel, on_msg):
    ws = websocket.WebSocket()
    ws.connect(URL)
    ws.send(json.dumps({"type": "join", "name": name, "channel": channel}))

    def loop():
        while True:
            try:
                raw = ws.recv()
            except Exception:
                break
            if not raw:
                break
            on_msg(json.loads(raw))
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return ws

received = {}
def on_b(msg):
    if msg.get("type") == "sync" and msg.get("key") == "keystroke":
        received.update(msg)
        print("  [May-B nhan]", json.dumps(msg, ensure_ascii=False))

a = make("May-A", "room-agent-test", lambda m: None)
b = make("May-B", "room-agent-test", on_b)
time.sleep(0.5)

# May-A gửi phím 'R' y hệt agent.py
a.send(json.dumps({
    "type": "sync",
    "key": "keystroke",
    "value": json.dumps({"s": {"k": "char", "v": "R"}}),
    "ts": int(time.time()*1000)
}))
print("  [May-A gui] phim R")
time.sleep(0.6)

ok = (received.get("from") == "May-A"
      and json.loads(received.get("value","{}")).get("s", {}).get("v") == "R")
print("KET QUA:", "THANH CONG" if ok else "THAT BAI")
a.close(); b.close()
import sys; sys.exit(0 if ok else 1)
