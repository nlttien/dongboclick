#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
  CLICK-DONGBO — Native keystroke-sync agent (KHÔNG cần mở web)
====================================================================
  Chạy nền trên mỗi máy. Khi bạn gõ một phím (vd "R") trên máy này,
  máy kia trong cùng kênh sẽ TỰ ĐỘNG bấm phím đó ở cấp hệ điều hành
  (toàn cục, ảnh hưởng tới mọi ứng dụng đang mở).

  Kiến trúc:
    Máy 1 (agent) --ws--> Server Ubuntu (Node) --ws--> Máy 2 (agent)
                         (đã có server.js)

  Cài đặt:  pip install -r requirements.txt
  Chạy:     python agent.py
  Cấu hình: sửa file config.json cùng thư mục
====================================================================
"""

import json
import os
import sys
import time
import threading

try:
    import websocket          # websocket-client
    from pynput import keyboard
    from pynput.keyboard import Key, Controller
except ImportError:
    print("[!] Thiếu thư viện. Cài đặt trước:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

# ------------------------------------------------------------------
#  CẤU HÌNH
# ------------------------------------------------------------------
# Khi đóng gói bằng PyInstaller, dùng thư mục chứa file .exe để config.json
# nằm cạnh exe (người dùng có thể sửa được).
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "server": "ws://localhost:3000/ws",
    "channel": "room1",
    "name": "May-A",
    "relay_keys": True,        # có nghe & gửi phím đi không
    "auto_inject": True,       # máy nhận có tự bấm phím không
    "echo_suppress_ms": 90,    # khoảng thời gian chống lặp vòng (ms)
    "only_keys": [],           # nếu khác rỗng: CHỈ relay các phím này
    "ignore_keys": []          # các phím bỏ qua
}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        print("[i] Đã tạo file cấu hình mặc định: config.json")
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print("[!] config.json lỗi (%s) -> dùng mặc định" % e)
        cfg = {}
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


cfg = load_config()

# Cho phép ghi đè bằng tham số dòng lệnh: python agent.py [name] [channel] [server]
if len(sys.argv) >= 2:
    cfg["name"] = sys.argv[1]
if len(sys.argv) >= 3:
    cfg["channel"] = sys.argv[2]
if len(sys.argv) >= 4:
    cfg["server"] = sys.argv[3]

# ------------------------------------------------------------------
#  TRẠNG THÁI
# ------------------------------------------------------------------
kbd = Controller()
ws_app = None
lock = threading.Lock()
last_inject_time = 0.0   # thời điểm gần nhất agent tự bấm phím (chống echo)
connected = False        # đang kết nối tới server hay không

# Các phím bổ trợ — KHÔNG relay riêng để tránh nhân đôi shift/ctrl khi gõ chữ
MODIFIERS = {
    "shift", "shift_l", "shift_r",
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "cmd", "cmd_l", "cmd_r",
    "fn", "caps_lock", "num_lock", "scroll_lock"
}

# Ánh xạ tên phím đặc biệt -> đối tượng Key của pynput
SPECIAL = {
    "space": Key.space, "enter": Key.enter, "return": Key.enter,
    "tab": Key.tab, "backspace": Key.backspace,
    "esc": Key.esc, "escape": Key.esc,
    "delete": Key.delete, "insert": Key.insert,
    "home": Key.home, "end": Key.end,
    "page_up": Key.page_up, "page_down": Key.page_down,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "caps_lock": Key.caps_lock,
    "shift": Key.shift, "shift_l": Key.shift_l, "shift_r": Key.shift_r,
    "ctrl": Key.ctrl, "ctrl_l": Key.ctrl_l, "ctrl_r": Key.ctrl_r,
    "alt": Key.alt, "alt_l": Key.alt_l, "alt_r": Key.alt_r,
    "cmd": Key.cmd,
}
for _i in range(1, 13):
    SPECIAL["f" + str(_i)] = getattr(Key, "f" + str(_i))


# ------------------------------------------------------------------
#  SERIALIZE / DESERIALIZE phím
# ------------------------------------------------------------------
def serialize(key):
    """pynput key -> dict có thể gửi qua mạng."""
    # Phím thường có thuộc tính char
    if hasattr(key, "char") and key.char is not None:
        return {"k": "char", "v": key.char}
    # Phím đặc biệt có thuộc tính name
    if hasattr(key, "name"):
        return {"k": "special", "v": key.name}
    return None


def deserialize(obj):
    """dict -> đối tượng key để bấm."""
    if not obj:
        return None
    if obj.get("k") == "char":
        return obj.get("v")
    if obj.get("k") == "special":
        name = obj.get("v")
        return SPECIAL.get(name)
    return None


def key_label(obj):
    """Nhãn hiển thị của phím (cho log)."""
    if not obj:
        return "?"
    if obj.get("k") == "char":
        return obj.get("v")
    return obj.get("v")


def should_relay(obj):
    if obj is None:
        return False
    name = key_label(obj)

    # Bỏ qua phím bổ trợ (gửi kèm theo chữ rồi)
    if obj.get("k") == "special" and name in MODIFIERS:
        return False

    # only_keys: nếu đặt, chỉ relay các phím trong danh sách
    if cfg.get("only_keys"):
        want = set(str(x).lower() for x in cfg["only_keys"])
        if str(name).lower() not in want:
            return False

    # ignore_keys
    ignore = set(str(x).lower() for x in cfg.get("ignore_keys", []))
    if str(name).lower() in ignore:
        return False

    return True


# ------------------------------------------------------------------
#  CHỐNG LẶP VÒNG (echo suppression)
# ------------------------------------------------------------------
def is_echo():
    """Trả về True nếu vừa tự bấm phím (sự kiện này là tiếng vang)."""
    global last_inject_time
    window = cfg.get("echo_suppress_ms", 90) / 1000.0
    with lock:
        return (time.time() - last_inject_time) < window


def mark_inject():
    global last_inject_time
    with lock:
        last_inject_time = time.time()


# ------------------------------------------------------------------
#  GỬI & BẨM PHÍM
# ------------------------------------------------------------------
def send_event(obj):
    global ws_app, connected
    if ws_app is None or not connected:
        return  # chưa kết nối server -> bỏ qua im lặng (không in lỗi spam)
    try:
        payload = {
            "type": "sync",
            "key": "keystroke",
            "value": json.dumps({"s": obj}),
            "ts": int(time.time() * 1000)
        }
        ws_app.send(json.dumps(payload))
    except Exception:
        pass  # im lặng; vòng lặp kết nối lại sẽ xử lý


def inject_key(obj):
    """Bấm phím ở cấp hệ điều hành (toàn cục)."""
    key_obj = deserialize(obj)
    if key_obj is None:
        return
    mark_inject()  # ĐÁNH DẤU để bỏ qua tiếng vang của chính mình
    try:
        kbd.press(key_obj)
        kbd.release(key_obj)
    except Exception as e:
        print("[inject err]", e)


# ------------------------------------------------------------------
#  LẮNG NGHE PHÍM TOÀN CỤC
# ------------------------------------------------------------------
def on_press(key):
    if not cfg.get("relay_keys", True):
        return
    if is_echo():
        return  # sự kiện do chính máy vừa bấm (để tránh lặp vòng)
    obj = serialize(key)
    if not should_relay(obj):
        return
    send_event(obj)
    # Chỉ in khi đã kết nối (tránh spam khi mất mạng)
    if connected:
        try:
            print("  [gửi] phím:", key_label(obj))
        except Exception:
            pass


def start_listener():
    listener = keyboard.Listener(on_press=on_press)
    listener.daemon = True
    listener.start()
    return listener


# ------------------------------------------------------------------
#  WEBSOCKET
# ------------------------------------------------------------------
def on_open(ws):
    global connected
    connected = True
    print("[+] Đã kết nối server:", cfg["server"])
    try:
        ws.send(json.dumps({
            "type": "join",
            "name": cfg["name"],
            "channel": cfg["channel"]
        }))
    except Exception as e:
        print("[join err]", e)
    print("[i] Đang nghe phím toàn cục. Bấm phím bất kỳ để đồng bộ.")
    print("[i] Ctrl+C để thoát.")


def on_message(ws, message):
    try:
        msg = json.loads(message)
    except Exception:
        return

    if msg.get("type") != "sync":
        return
    if msg.get("key") != "keystroke":
        return
    if not cfg.get("auto_inject", True):
        return

    try:
        data = json.loads(msg.get("value") or "{}")
    except Exception:
        return

    obj = data.get("s")
    if not should_relay(obj):
        return

    src = msg.get("from", "?")
    print("  [nhận] %s bấm phím: %s" % (src, key_label(obj)))
    inject_key(obj)


def on_error(ws, error):
    # Im lặng: on_close đã thông báo. Tránh spam "WinError 10061" lặp lại.
    pass


def on_close(ws, *args):
    global connected
    connected = False
    print("[-] Chưa kết nối được server (" + cfg["server"] + ").")
    print("    -> Hãy chắc chắn server đang chạy:  npm start")
    print("    -> Và 'server' trong config.json trỏ đúng IP/cổng. Đang thử lại...")


def main():
    print("=" * 60)
    print("  CLICK-DONGBO — Keystroke Sync Agent")
    print("=" * 60)
    print("  Tên máy : %s" % cfg["name"])
    print("  Kênh     : %s" % cfg["channel"])
    print("  Server   : %s" % cfg["server"])
    print("-" * 60)

    listener = start_listener()

    # Vòng lặp kết nối lại nếu rớt
    while True:
        global ws_app
        ws_app = websocket.WebSocketApp(
            cfg["server"],
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        try:
            ws_app.run_forever(ping_interval=5, ping_timeout=3)
        except KeyboardInterrupt:
            print("\n[!] Thoát.")
            break
        except Exception as e:
            print("[run err]", e)
        time.sleep(2)  # chờ rồi kết nối lại


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Thoát.")
